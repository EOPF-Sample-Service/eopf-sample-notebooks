"""
Lightweight helpers for working with xarray-style objects inside the SL2P pipeline.

- Provides a minimal fallback implementation when xarray is not installed
  (useful for offline development). If real xarray is available, it is used.
- Utilities to convert the existing Sentinel-2 dictionaries to datasets,
  clip datasets to AOIs, wrap model outputs as datasets, and write GeoTIFFs.
"""

from __future__ import annotations

import os
import types
import re
import time
import gc
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import rasterio
from rasterio.transform import Affine
from scipy import ndimage
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom
import fiona

try:  # pragma: no cover - optional dependency
    import xarray as xr  # type: ignore

    HAS_XARRAY = True
except ImportError:  # pragma: no cover - fallback stub
    HAS_XARRAY = False

    class DataArray:
        def __init__(
            self, data, dims: Sequence[str], coords=None, attrs=None, name=None
        ):
            self.data = np.asarray(data)
            self.dims = tuple(dims)
            self.coords = coords or {}
            self.attrs = attrs or {}
            self.name = name

        @property
        def values(self):
            return self.data

        @property
        def shape(self):
            return self.data.shape

        def astype(self, dtype, copy: bool = True):
            return DataArray(
                self.data.astype(dtype, copy=copy),
                dims=self.dims,
                coords=self.coords,
                attrs=self.attrs,
                name=self.name,
            )

        # Minimal arithmetic to behave like numpy arrays
        def _binop(self, other, op):
            other_arr = other.data if isinstance(other, DataArray) else other
            return DataArray(
                op(self.data, other_arr),
                dims=self.dims,
                coords=self.coords,
                attrs=self.attrs,
                name=self.name,
            )

        def __sub__(self, other):
            return self._binop(other, np.subtract)

        def __rsub__(self, other):
            return DataArray(
                np.subtract(other, self.data),
                dims=self.dims,
                coords=self.coords,
                attrs=self.attrs,
                name=self.name,
            )

        def __add__(self, other):
            return self._binop(other, np.add)

        def __radd__(self, other):
            return self.__add__(other)

        def __mul__(self, other):
            return self._binop(other, np.multiply)

        def __rmul__(self, other):
            return self.__mul__(other)

        def __truediv__(self, other):
            return self._binop(other, np.divide)

        def __abs__(self):
            return DataArray(
                np.abs(self.data),
                dims=self.dims,
                coords=self.coords,
                attrs=self.attrs,
                name=self.name,
            )

        def __array__(self, dtype=None):
            return np.asarray(self.data, dtype=dtype)

    class Dataset:
        def __init__(
            self, data_vars: Dict[str, DataArray] | None = None, coords=None, attrs=None
        ):
            self.data_vars = data_vars or {}
            self.coords = coords or {}
            self.attrs = attrs or {}

        def __getitem__(self, key):
            return self.data_vars[key]

        def __setitem__(self, key, value):
            self.data_vars[key] = value

        def __contains__(self, key):
            return key in self.data_vars

        def keys(self):
            return self.data_vars.keys()

        @property
        def dims(self):
            dims: Dict[str, int] = {}
            for da in self.data_vars.values():
                for dim, size in zip(da.dims, da.shape):
                    dims[dim] = size
            return dims

    xr = types.SimpleNamespace(DataArray=DataArray, Dataset=Dataset)  # type: ignore


ArrayLike = np.ndarray


def _coords_from_shape(shape: Tuple[int, int], dims: Sequence[str]):
    ydim, xdim = dims
    return {ydim: np.arange(shape[0]), xdim: np.arange(shape[1])}


def dict_to_dataset(s2_dict: Dict, dims: Tuple[str, str] = ("y", "x")):

    profile = dict(s2_dict.get("profile", {}))

    # Default coords from profile (if present)
    prof_h = profile.get("height")
    prof_w = profile.get("width")

    data_vars = {}
    for name, array in s2_dict.items():
        if name == "profile":
            continue
        arr = np.asarray(array)
        # Choose dims/coords per variable to avoid conflicts
        if (
            prof_h is not None
            and prof_w is not None
            and arr.shape[:2] == (prof_h, prof_w)
        ):
            var_dims = dims
        else:
            var_dims = (f"{dims[0]}_{arr.shape[0]}", f"{dims[1]}_{arr.shape[1]}")
        arr_coords = _coords_from_shape(arr.shape[:2], var_dims)
        data_vars[name] = xr.DataArray(arr, dims=var_dims, coords=arr_coords)

    ds = xr.Dataset(data_vars)
    print("***********************************************")
    print("***********************************************")
    print(type(ds))
    ds.attrs["profile"] = profile
    return ds


def merge_datasets(base_ds, extra_ds):
    """Merge variables from ``extra_ds`` into ``base_ds`` without overwriting."""
    for name, da in extra_ds.data_vars.items():
        if name in base_ds.data_vars:
            continue
        base_ds[name] = da
    return base_ds


def stack_dataset(ds, band_names: Iterable[str] | None = None):
    """Stack Dataset variables into a 3D numpy array (band, y, x)."""
    names = list(band_names) if band_names is not None else list(ds.data_vars.keys())
    arrays: List[np.ndarray] = []
    dims: Tuple[str, str] | None = None
    for name in names:
        da = ds[name]
        arr = np.asarray(getattr(da, "values", da))
        arrays.append(arr)
        if dims is None:
            dims = getattr(da, "dims", None) or ("y", "x")
    if dims is None:
        raise ValueError("Dataset contains no variables to stack")
    stack = np.stack(arrays).astype(np.float32, copy=False)
    return stack, names, dims


def clip_dataset(
    ds, aoi_path: str, crop: bool = True, all_touched: bool = False, nodata=np.nan
):
    """Clip a Dataset to an AOI shapefile using rasterio.mask."""
    profile = dict(ds.attrs.get("profile", {}))
    if not profile:
        raise ValueError("Dataset missing 'profile' attribute required for clipping")

    with fiona.open(aoi_path, "r") as shp:
        shapes = [feat["geometry"] for feat in shp if feat.get("geometry") is not None]
        shp_crs = shp.crs_wkt or shp.crs
    if not shapes:
        raise ValueError("AOI shapefile contains no geometries")

    stack, names, dims = stack_dataset(ds)
    stack_dtype = rasterio.dtypes.get_minimum_dtype(stack)
    if hasattr(stack_dtype, "name"):
        stack_dtype = stack_dtype.name
    else:
        stack_dtype = str(stack_dtype)

    mem_profile = profile.copy()
    mem_profile.update(
        {
            "count": stack.shape[0],
            "dtype": stack_dtype,
        }
    )

    with MemoryFile() as memfile:
        with memfile.open(**mem_profile) as src:
            src.write(stack)
            dst_crs = src.crs
            geoms_dst = (
                [
                    transform_geom(shp_crs, dst_crs.to_string(), g, precision=6)
                    for g in shapes
                ]
                if shp_crs and dst_crs
                else shapes
            )

            out_img, out_transform = rio_mask(
                src,
                geoms_dst,
                crop=crop,
                all_touched=all_touched,
                nodata=nodata,
            )
            out_profile = src.profile.copy()
            out_profile.update(
                height=out_img.shape[1],
                width=out_img.shape[2],
                transform=out_transform,
                nodata=nodata,
            )

    coords = _coords_from_shape(out_img.shape[1:], dims)
    data_vars = {
        name: xr.DataArray(out_img[i], dims=dims, coords=coords)
        for i, name in enumerate(names)
    }
    clipped = xr.Dataset(data_vars)
    clipped.attrs["profile"] = out_profile
    return clipped


def coords_from_template(template, profile=None):
    """Extract spatial dims + coords from a DataArray/Dataset or profile."""
    dims = None
    coords = None
    if template is not None:
        dims_obj = getattr(template, "dims", None)
        if dims_obj:
            # Dataset.dims is mapping; DataArray.dims is tuple
            if isinstance(dims_obj, dict):
                dims_items = list(dims_obj.items())
                if profile and "height" in profile and "width" in profile:
                    h, w = profile["height"], profile["width"]
                    candidates = [d for d, size in dims_items if size == h or size == w]
                    if len(candidates) >= 2:
                        dims = tuple(candidates[:2])
                if dims is None and len(dims_items) >= 2:
                    dims = tuple([d for d, _ in dims_items][-2:])
            else:
                try:
                    dims_list = list(dims_obj)
                    if len(dims_list) >= 2:
                        dims = tuple(dims_list[-2:])
                except TypeError:
                    dims = None
            if dims:
                coords = {
                    d: getattr(getattr(template, "coords", {}), "get", lambda *_: None)(
                        d
                    )
                    for d in dims
                }
    if dims is None:
        dims = ("y", "x")
    if coords is None:
        coords = {}
    if profile:
        h = profile.get("height")
        w = profile.get("width")
        coords.setdefault(dims[0], np.arange(h) if h is not None else None)
        coords.setdefault(dims[1], np.arange(w) if w is not None else None)
    for d in dims:
        if coords.get(d) is None and profile:
            if d == dims[0]:
                coords[d] = np.arange(profile.get("height", 0))
            elif d == dims[1]:
                coords[d] = np.arange(profile.get("width", 0))
    return dims, coords


def varmap_to_dataset(varmap_dict: Dict[str, ArrayLike], template=None, profile=None):
    """Wrap model outputs (numpy arrays) into a Dataset aligned to a template."""
    dims, coords = coords_from_template(template, profile)
    data_vars = {
        name: xr.DataArray(np.asarray(values), dims=dims, coords=coords)
        for name, values in varmap_dict.items()
    }
    ds = xr.Dataset(data_vars)
    if profile:
        ds.attrs["profile"] = dict(profile)
    return ds


def write_varmap_geotiff(
    varmap, output_path: str, profile: Dict, band_order: Sequence[str]
):
    """Write a varmap Dataset/dict to GeoTIFF following the provided band order."""
    profile = dict(profile)
    profile.update(
        {
            "count": len(band_order),
            "dtype": "float32",
            "driver": "GTiff",
        }
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def _get_band(data, name):
        if isinstance(data, dict):
            arr = data[name]
        else:
            arr = data[name].values if hasattr(data[name], "values") else data[name]
        return np.asarray(arr, dtype=np.float32)

    with rasterio.open(output_path, "w", **profile) as dst:
        for idx, name in enumerate(band_order, start=1):
            dst.write(_get_band(varmap, name), idx)

    return output_path


def parse_date_from_name(path: str) -> str:
    m = re.search(r"MSIL2A_(\d{8})", os.path.basename(path))
    return m.group(1) if m else "00000000"


def parse_baseline_from_name(path: str) -> int:
    m = re.search(r"_N(\d{4})", os.path.basename(path))
    return int(m.group(1)[1:2]) if m else 5


def ensure_angle_cosines(ds: xr.Dataset) -> xr.Dataset:
    if "cosSZA" not in ds and "SZA" in ds:
        ds["cosSZA"] = np.cos(np.deg2rad(ds["SZA"]))
    if "cosVZA" not in ds and "VZA" in ds:
        ds["cosVZA"] = np.cos(np.deg2rad(ds["VZA"]))
    if "cosRAA" not in ds:
        if "RAA" in ds:
            ds["cosRAA"] = np.cos(np.deg2rad(ds["RAA"]))
        elif "SAA" in ds and "VAA" in ds:
            ds["cosRAA"] = np.cos(np.deg2rad(np.abs(ds["SAA"] - ds["VAA"])))
    missing = [c for c in ["cosSZA", "cosVZA", "cosRAA"] if c not in ds]
    if missing:
        raise ValueError(f"Dataset missing required angular cosines: {missing}")
    return ds


def _infer_transform_from_coords(ds: xr.Dataset, ydim: str, xdim: str):
    if xdim not in ds.coords or ydim not in ds.coords:
        return None

    x = np.asarray(ds.coords[xdim].values, dtype=np.float64)
    y = np.asarray(ds.coords[ydim].values, dtype=np.float64)
    if x.ndim != 1 or y.ndim != 1 or x.size < 2 or y.size < 2:
        return None

    dx = float(np.median(np.diff(x)))
    dy = float(np.median(np.diff(y)))
    if not np.isfinite(dx) or not np.isfinite(dy) or dx == 0.0 or dy == 0.0:
        return None

    # x/y coordinates are pixel centers; convert to upper-left pixel corner.
    return Affine.translation(
        float(x[0]) - dx / 2.0, float(y[0]) - dy / 2.0
    ) * Affine.scale(dx, dy)


def _infer_crs(ds: xr.Dataset):
    if "spatial_ref" in ds:
        spatial_ref_attrs = getattr(ds["spatial_ref"], "attrs", {})
        crs_wkt = spatial_ref_attrs.get("crs_wkt") or spatial_ref_attrs.get(
            "spatial_ref"
        )
        if crs_wkt:
            return crs_wkt
        epsg = spatial_ref_attrs.get("epsg_code") or spatial_ref_attrs.get("epsg")
        if epsg:
            epsg = str(epsg)
            return epsg if epsg.upper().startswith("EPSG:") else f"EPSG:{epsg}"
    return ds.attrs.get("horizontal_CRS_code") or ds.attrs.get("crs")


def infer_profile(ds: xr.Dataset, ref_band: str, required_inputs: list) -> dict:
    profile = dict(ds.attrs.get("profile", {}))
    ref_da = ds[ref_band]
    ydim, xdim = ref_da.dims[-2], ref_da.dims[-1]

    h = profile.get("height") or ref_da.shape[-2]
    w = profile.get("width") or ref_da.shape[-1]
    profile["height"] = int(h)
    profile["width"] = int(w)

    transform = profile.get("transform")
    if transform is not None and not isinstance(transform, Affine):
        transform = Affine(*transform)
    if transform is None:
        transform = _infer_transform_from_coords(ds, ydim, xdim)
    if transform is None:
        raise ValueError(
            "Unable to infer raster transform from profile or x/y coordinates."
        )
    profile["transform"] = transform

    profile.setdefault("crs", profile.get("crs") or _infer_crs(ds))
    if profile["crs"] is None:
        raise ValueError(
            "Unable to infer CRS from profile, spatial_ref, or dataset attributes."
        )
    profile.setdefault("driver", "GTiff")
    profile.setdefault("dtype", "float32")
    profile.setdefault("count", len(required_inputs))
    profile.setdefault("nodata", np.nan)
    return profile


def clip_cube_to_aoi(ds: xr.Dataset, ref_band: str, aoi_path: str, required_inputs):
    """Clip an already aligned xarray cube using the raster profile inferred from the reference band."""
    ds_for_clip = ds.copy()
    ds_for_clip.attrs["profile"] = infer_profile(ds_for_clip, ref_band, required_inputs)
    clipped = clip_dataset(ds_for_clip, aoi_path)
    clipped_profile = dict(clipped.attrs.get("profile", {}))
    if not clipped_profile:
        raise ValueError("AOI clipping did not return a raster profile.")
    return clipped, clipped_profile


def _resample_to_ref(arr: np.ndarray, target_shape: Tuple[int, int]) -> np.ndarray:
    if arr.shape == target_shape:
        return arr
    fy = target_shape[0] / arr.shape[0]
    fx = target_shape[1] / arr.shape[1]
    return ndimage.zoom(arr, (fy, fx), order=0)


def build_sl2p_input(
    ds: xr.Dataset, net_opts: dict, PRESCALED_INPUT
) -> Tuple[np.ndarray, Tuple[str, str]]:
    missing = [b for b in net_opts["inputBands"] if b not in ds]
    if missing:
        raise ValueError(f"Dataset missing required variables: {missing}")

    ref_band = next(b for b in net_opts["inputBands"] if b in ds)
    ref_da = ds[ref_band]
    ref_shape = ref_da.shape
    dims = getattr(ref_da, "dims", ("y", "x"))

    stack = []
    for idx, name in enumerate(net_opts["inputBands"]):
        arr = ds[name].values if hasattr(ds[name], "values") else np.asarray(ds[name])
        arr = arr.astype(np.float32, copy=False)
        if arr.shape != ref_shape:
            arr = _resample_to_ref(arr, ref_shape)
        if isinstance(name, str) and name.startswith("B"):
            arr = arr.copy()
            arr[arr == 0] = np.nan
        if PRESCALED_INPUT:
            scaled = arr  # reflectance already applied in preprocessing
        else:
            scaled = (arr + net_opts["inputOffset"][idx]) * net_opts["inputScaling"][
                idx
            ]
        if isinstance(name, str) and name.startswith("B"):
            scaled[scaled < 0] = np.nan
        stack.append(scaled)
    return np.stack(stack), dims


def export_varmap(varmap, template_profile, output_path, variable_name):
    band_order = [
        variable_name,
        f"{variable_name}_uncertainty",
        "sl2p_inputFlag",
        "sl2p_outputFlag",
    ]
    write_varmap_geotiff(varmap, output_path, template_profile, band_order)
