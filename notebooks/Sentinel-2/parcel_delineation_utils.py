import gc
import sys
from functools import lru_cache
from random import sample, seed
from typing import Dict, Tuple

import dask.array as da
import numpy as np
import onnxruntime as ort
import xarray as xr
from dask.base import compute
from dask.delayed import delayed
from dask.diagnostics.progress import ProgressBar
from skimage import graph, segmentation
from skimage.filters import sobel
from xarray import DataArray

sys.path.insert(1, "onnx_deps")

model_names = [
    "BelgiumCropMap_unet_3BandsGenerator_Network1.onnx",
    "BelgiumCropMap_unet_3BandsGenerator_Network2.onnx",
    "BelgiumCropMap_unet_3BandsGenerator_Network3.onnx",
]


@lru_cache(maxsize=1)
def load_ort_sessions(names):
    return [ort.InferenceSession(f"onnx_models/{name}") for name in names]


def inspect(message):
    print(message)


def preprocess_datacube(
    cubearray: xr.DataArray, min_images: int
) -> tuple[bool, xr.DataArray]:
    # If 'bands' dimension exists, select the first band; otherwise, use the array as is
    if "bands" in cubearray.dims:
        nvdi_stack = cubearray.isel(bands=0)
    else:
        nvdi_stack = cubearray
    # Clamp NDVI values to [-0.08, 0.92] and shift by 0.08
    nvdi_stack = nvdi_stack.where(lambda x: x < 0.92, 0.92)
    nvdi_stack = nvdi_stack.where(lambda x: x > -0.08)
    nvdi_stack += 0.08
    # Count invalid pixels per time step
    sum_invalid = nvdi_stack.isnull().sum(dim=["x", "y"])
    sum_invalid_mean = nvdi_stack.isnull().mean(dim=["x", "y"])
    # Fill invalid pixels with 0
    nvdi_stack_data = nvdi_stack.fillna(0)

    # Check if data is valid (at least min_images time steps with <100% invalid pixels)
    if (sum_invalid_mean.data < 1).sum() <= min_images:
        inspect("Input data is invalid for this window -> skipping!")
        nan_data = xr.zeros_like(nvdi_stack.isel(t=0, drop=True))
        nan_data = nan_data.where(lambda x: x > 1)  # Creates NaN array
        return True, nan_data

    # Select valid data
    if (sum_invalid.data == 0).sum() >= min_images:
        good_data = nvdi_stack_data.sel(
            t=sum_invalid["t"].values[sum_invalid.values == 0]
        )
    else:
        good_data = nvdi_stack_data.sel(
            t=sum_invalid.sortby(sum_invalid).t[:min_images]
        )
    return False, good_data.transpose("x", "y", "t")


# Prediction function from udf_segmentation.py
def process_window_onnx(ndvi_stack: xr.DataArray, patch_size=128) -> xr.DataArray:
    ort_sessions = load_ort_sessions(
        tuple(model_names)
    )  # Convert list to tuple for caching
    predictions_per_model = 4
    no_rand_images = 3
    no_images = ndvi_stack.sizes["t"]
    images_range = range(no_images)
    prediction = []

    for ort_session in ort_sessions:
        for i in range(predictions_per_model):
            seed(i)  # Reproducible random selection
            idx = sample(images_range, k=no_rand_images)
            # Check if selected images span different weeks (optional logging)
            weeks = set(ndvi_stack.isel(t=idx).t.dt.isocalendar().week.values)
            if len(weeks) != no_rand_images:
                inspect(
                    "Time difference is not larger than a week for good parcel delineation"
                )
            # Prepare input data
            input_data = ndvi_stack.isel(t=idx).data.reshape(
                1, patch_size * patch_size, no_rand_images
            )
            if input_data.ndim == 3:
                input_data = input_data[
                    np.newaxis, ...
                ]  # shape: (1, C, H, W) or (1, H, W, C)

            if isinstance(input_data, da.Array):
                input_data = input_data.compute()

            if input_data.dtype != np.float32:
                input_data = input_data.astype(np.float32)

            if len(input_data.shape) == 4:
                input_data = np.squeeze(
                    input_data, axis=0
                )  # Remove singleton dimension if present

            ort_inputs = {ort_session.get_inputs()[0].name: input_data}
            ort_outputs = ort_session.run(None, ort_inputs)
            prediction.append(ort_outputs[0].reshape((patch_size, patch_size)))

    gc.collect()  # Free memory

    # Create DataArray of predictions and take median
    all_predictions = xr.DataArray(
        prediction,
        dims=["predict", "x", "y"],
        coords={
            "predict": range(len(prediction)),
            "x": ndvi_stack.coords["x"],
            "y": ndvi_stack.coords["y"],
        },
    )
    return all_predictions.median(dim="predict")


# Main function to apply segmentation locally
def apply_segmentation(ndvi: xr.DataArray) -> xr.DataArray:
    # Add a dummy 't' dimension if missing (required by downstream functions)
    if "time" in ndvi.dims:
        ndvi = ndvi.rename({"time": "t"})

    # Pad the array with 32 pixels on each side
    padded = ndvi.pad(x=(32, 32), y=(32, 32), mode="constant", constant_values=0)

    # Define block parameters
    block_size = 128  # Size of each block (pixels)
    stride = 64  # Stride between blocks (pixels)

    # Calculate number of blocks along each dimension
    nx = (
        padded.sizes["x"] - block_size
    ) // stride + 1  # e.g., (457 - 128) // 64 + 1 = 6
    ny = (
        padded.sizes["y"] - block_size
    ) // stride + 1  # e.g., (414 - 128) // 64 + 1 = 5

    predictions = []
    for i in range(nx):
        for j in range(ny):
            # Calculate start indices
            start_x = i * stride
            start_y = j * stride

            # Extract block using integer indices with isel
            block = padded.isel(
                x=slice(start_x, start_x + block_size),
                y=slice(start_y, start_y + block_size),
            )

            # Process the block (assuming these functions are defined)
            invalid_data, ndvi_stack = preprocess_datacube(block, min_images=4)
            if invalid_data:
                prediction = ndvi_stack
            else:
                prediction = process_window_onnx(ndvi_stack, patch_size=block_size)

            # Extract central 64x64 pixels from the prediction
            central_prediction = prediction.isel(x=slice(32, 96), y=slice(32, 96))
            predictions.append(central_prediction)

    # Combine all central predictions into a single DataArray
    output = xr.combine_by_coords(predictions)

    # Mimic OpenEO output format (optional)
    year = ndvi.time.dt.year.values[0] if "time" in ndvi.coords else 0
    output = output.expand_dims(dim={"time": [year], "bands": ["prediction"]})

    return output


@delayed
def process_block(
    block: xr.DataArray, i: int, j: int, block_size: int, min_images: int = 4
) -> xr.DataArray:
    invalid_data, ndvi_stack = preprocess_datacube(block, min_images=min_images)
    if invalid_data:
        prediction = ndvi_stack
    else:
        prediction = process_window_onnx(ndvi_stack, patch_size=block_size)
    # Extract central prediction
    central_prediction = prediction.isel(x=slice(32, 96), y=slice(32, 96))
    # Add metadata for merging
    central_prediction.attrs["block_indices"] = (i, j)
    return central_prediction


def apply_segmentation_parallel(ndvi: xr.DataArray) -> xr.DataArray:
    if "time" in ndvi.dims:
        ndvi = ndvi.rename({"time": "t"})

    padded = ndvi.pad(x=(32, 32), y=(32, 32), mode="constant", constant_values=0)
    block_size, stride = 128, 64
    nx = (padded.sizes["x"] - block_size) // stride + 1
    ny = (padded.sizes["y"] - block_size) // stride + 1

    delayed_predictions = []
    for i in range(nx):
        for j in range(ny):
            start_x = i * stride
            start_y = j * stride
            block = padded.isel(
                x=slice(start_x, start_x + block_size),
                y=slice(start_y, start_y + block_size),
            )
            delayed_prediction = process_block(block, i, j, block_size)
            delayed_predictions.append(delayed_prediction)

    # Compute all blocks in parallel
    with ProgressBar():
        computed_predictions = compute(*delayed_predictions)

    # Reconstruct output array
    merged = xr.combine_by_coords(computed_predictions, combine_attrs="override")

    # Add time/band dimension
    year = ndvi.t.dt.year.values[0] if "t" in ndvi.coords else 0
    merged = merged.expand_dims(dim={"time": [year], "bands": ["prediction"]})

    return merged


def apply_filter(cube: DataArray, context: dict) -> DataArray:
    inspect(message=f"Dimensions of the final datacube {cube.dims}")
    # get the underlying array without the bands and t dimension
    image_data = cube.squeeze("time", drop=True).values
    # compute edges
    edges = sobel(image_data)
    # Perform felzenszwalb segmentation
    segment = segmentation.felzenszwalb(
        image_data, scale=120, sigma=0.0, min_size=30, channel_axis=None
    )
    # Perform the rag boundary analysis and merge the segments
    bgraph = graph.rag_boundary(segment, edges)
    # merging segments
    mergedsegment = graph.cut_threshold(segment, bgraph, 0.15, in_place=False)
    # create a data cube and perform masking operations
    output_arr = DataArray(
        mergedsegment.reshape(cube.shape), dims=cube.dims, coords=cube.coords
    )
    output_arr = output_arr.where(
        cube >= 0.3
    )  # Mask the output pixels based on the cube values <0.3
    output_arr = output_arr.where(
        output_arr >= 0
    )  # Mask all values less than or equal to zero
    return output_arr
