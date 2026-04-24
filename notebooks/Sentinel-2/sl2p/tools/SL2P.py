from tools import toolsNets
from tools import dictionariesSL2P
from tools import SL2PV0 as algorithm

# from tools import read_sentinel2_safe_image
from tools.xarray_utils import dict_to_dataset, varmap_to_dataset, xr

import numpy
import pandas as pd
from datetime import datetime


# Main SL2P function
def SL2P(sl2p_inp, variableName, imageCollectionName, method, outPath=None):
    networkOptions = dictionariesSL2P.make_net_options()
    collectionOptions = dictionariesSL2P.make_collection_options(algorithm)
    netOptions = networkOptions[variableName][imageCollectionName]
    colOptions = collectionOptions[imageCollectionName]

    # prepare SL2P networks
    SL2P, errorsSL2P = makeModel(algorithm, imageCollectionName, variableName, method)

    # generate sl2p input data flag
    inputs_flag = invalidInput(sl2p_inp, netOptions, colOptions)

    # run SL2P
    # print('Run SL2P...\nSL2P start: %s' %(datetime.now()))
    estimate = toolsNets.wrapperNNets(SL2P, netOptions, sl2p_inp, method)
    uncertainty = toolsNets.wrapperNNets(errorsSL2P, netOptions, sl2p_inp, method)
    # print('SL2P end: %s' %(datetime.now()))

    # generate sl2p output product flag
    output_flag = invalidOutput(estimate, variableName)
    # print('Done')
    # returning a dictionary containing the estimate, uncertainty, input flag, and output flag.
    return {
        variableName: estimate,
        variableName + "_uncertainty": uncertainty,
        "sl2p_inputFlag": inputs_flag,
        "sl2p_outputFlag": output_flag,
    }


# Build SL2P needed models (SL2P_nets and errorsSL2P_nets) using toolsNets.py
def makeModel(algorithm, imageCollectionName, variableName, method):
    if method == "SL2P":
        collectionOptions = dictionariesSL2P.make_collection_options(algorithm)
        # networkOptions = dictionariesSL2P.make_net_options()
    elif method == "SL2PCCRS":
        collectionOptions = dictionariesSL2P.make_collection_options_CCRS(algorithm)
        # networkOptions = (
        #    dictionariesSL2P.make_net_options_CCRS()
        # )
        # # collectionOptions is a dictionary like: S2_SR': {"name": 'S2_SR', "description": 'Sentinel 2A',

    colOptions = collectionOptions[
        imageCollectionName
    ]  # LA RIGA INCRIMINATA #colOptions is a dictionary with only the lines pertaining to the imageCollectionName
    # netOptions = networkOptions[variableName][imageCollectionName]
    """
    Example of colOptions ----        
    'S2_SR': {
        "name": 'S2_SR',
        "description": 'Sentinel 2A',
        "sza": 'MEAN_SOLAR_ZENITH_ANGLE',
        "vza": 'MEAN_INCIDENCE_ZENITH_ANGLE_B8A',
        "saa": 'MEAN_SOLAR_AZIMUTH_ANGLE', 
        "vaa": 'MEAN_INCIDENCE_AZIMUTH_ANGLE_B8A',
        "Collection_SL2P": fc.s2_createFeatureCollection_estimates(),   
        "Collection_SL2Perrors": fc.s2_createFeatureCollection_errors(),        
        "sl2pDomain": fc.s2_createFeatureCollection_domains(),   
        "Network_Ind": fc.s2_createFeatureCollection_Network_Ind(),      
        "numVariables": 7,
        "exportRes": 20,
    """

    ## Compute numNets
    numNets = len(
        {
            k: v
            for k, v in (colOptions["Network_Ind"]["features"][0]["properties"]).items()
            if k != "Feature Index"
        }
    )
    SL2P_nets = [
        toolsNets.makeNetVars(colOptions["Collection_SL2P"], numNets, netNum)
        for netNum in range(colOptions["numVariables"])
    ]
    errorsSL2P_nets = [
        toolsNets.makeNetVars(colOptions["Collection_SL2Perrors"], numNets, netNum)
        for netNum in range(colOptions["numVariables"])
    ]

    return SL2P_nets, errorsSL2P_nets


# Same as above but for CCRS
def makeModel_CCRS(algorithm, netOptions, colOptions):
    numNets = len(
        {
            k: v
            for k, v in (colOptions["Network_Ind"]["features"][0]["properties"]).items()
            if k not in ["Feature Index", "lon"]
        }
    )
    SL2P_nets = [
        toolsNets.makeNetVars(colOptions["Collection_SL2P"], numNets, netNum)
        for netNum in range(colOptions["numVariables"])
    ]
    errorsSL2P_nets = [
        toolsNets.makeNetVars(colOptions["Collection_SL2Perrors"], numNets, netNum)
        for netNum in range(colOptions["numVariables"])
    ]
    return SL2P_nets, errorsSL2P_nets


# prepare the sentinel-2 data (dict or Dataset) to be input to SL2P:
# 1) resample view/sun angles, 2) compute RAA, 3) compute cosines,
# 4) scale SR data, and 5) build a 3D-ordered data cube.
def prepare_sl2p_inp(
    s2,
    variableName,
    imageCollectionName,
    method,
    count,
    date,
    pb=4.0,
    to_10m=False,
    mask_10m=None,
):
    if method == "SL2P":
        networkOptions = dictionariesSL2P.make_net_options()
    elif method == "SL2PCCRS":
        networkOptions = dictionariesSL2P.make_net_options_CCRS()

    netOptions = networkOptions[variableName][imageCollectionName]

    # Accept dict or Dataset
    ds = dict_to_dataset(s2) if isinstance(s2, dict) else s2

    # ---- (0) Choose a 10 m reference band (fallbacks if B03 missing)
    ref_candidates = [b for b in ["B03", "B02", "B04", "B08"] if b in ds]
    if not ref_candidates:
        ref_candidates = [k for k in ds.keys() if k.startswith("B")]
        if not ref_candidates:
            raise ValueError(
                "No spectral bands found in input to define a reference grid."
            )
    ref_band = ref_candidates[0]
    ref_h, ref_w = ds[ref_band].shape
    dims = ds[ref_band].dims if hasattr(ds[ref_band], "dims") else ("y", "x")

    # ---- (1) Resample sun and view angles to reference grid (bilinear)
    print("Resample sun and view (sensor) angles")
    target_shape = (ref_h, ref_w)
    for ang_name in ["SZA", "SAA", "VZA", "VAA"]:
        if ang_name not in ds:
            continue
        arr = ds[ang_name].values
        arr_interp = read_sentinel2_safe_image.interpolate_angle_grid(  # noqa: F821
            arr, target_shape
        )
        ds[ang_name] = xr.DataArray(arr_interp, dims=dims)

    # ---- (2) Relative azimuth
    ds["RAA"] = numpy.absolute(ds["SAA"] - ds["VAA"])

    # ---- (3) Cosines
    print("Computing cosSZA, cosVZA and cosRAA")
    ds["cosSZA"] = numpy.cos(numpy.deg2rad(ds["SZA"]))
    ds["cosVZA"] = numpy.cos(numpy.deg2rad(ds["VZA"]))
    ds["cosRAA"] = numpy.cos(numpy.deg2rad(ds["RAA"]))

    # ---- (4) Optional: resample spectral bands to 10 m (nearest-neighbor)
    if to_10m:
        print("Resampling spectral bands to 10 m (nearest neighbor)")
    for band in netOptions["inputBands"]:
        if isinstance(band, str) and band.startswith("B") and (band in ds):
            arr = ds[band].values

            if to_10m and (arr.shape != (ref_h, ref_w)):
                factor_y = ref_h / arr.shape[0]
                factor_x = ref_w / arr.shape[1]
                arr = read_sentinel2_safe_image.resample_image(  # noqa: F821
                    arr, (factor_y, factor_x), interpolation="nearest"
                )
                if arr.shape != (ref_h, ref_w):
                    arr = arr[:ref_h, :ref_w]
                    if arr.shape != (ref_h, ref_w):
                        pad_y = max(0, ref_h - arr.shape[0])
                        pad_x = max(0, ref_w - arr.shape[1])
                        arr = numpy.pad(
                            arr, ((0, pad_y), (0, pad_x)), constant_values=numpy.nan
                        )

            if arr.dtype != numpy.float32:
                arr = arr.astype(numpy.float32, copy=False)

            if mask_10m is not None:
                numpy.multiply(arr, mask_10m, out=arr)

            ds[band] = xr.DataArray(arr, dims=dims)

    # ---- (5) Scaling SR + cleaning
    print("Scaling Sentinel-2 bands\nSelecting sl2p input bands")
    sl2p_inp = {}

    for band_id, band in enumerate(netOptions["inputBands"]):
        is_spectral = isinstance(band, str) and band.startswith("B")

        band_arr = ds[band].values if hasattr(ds[band], "values") else ds[band]
        if is_spectral:
            band_arr = band_arr.copy()
            band_arr[band_arr == 0] = numpy.nan

        if pb >= 4:
            sl2p_inp[band] = (
                band_arr + netOptions["inputOffset"][band_id]
            ) * netOptions["inputScaling"][band_id]
        else:
            sl2p_inp[band] = (
                band_arr + netOptions["inputOffset_before"][band_id]
            ) * netOptions["inputScaling_before"][band_id]

        if is_spectral:
            sl2p_inp[band][sl2p_inp[band] < 0] = numpy.nan

    # ---- (6) Stack to (bands, H, W)
    sl2p_inp = numpy.stack([sl2p_inp[k] for k in sl2p_inp.keys()])
    print("Done!")
    return sl2p_inp


# determine if inputs fall in domain of algorithm
def invalidInput(image, netOptions, colOptions):
    print("Generating sl2p input data flag")
    [d0, d1, d2] = image.shape
    sl2pDomain = numpy.sort(
        numpy.array(
            [
                row["properties"]["DomainCode"]
                for row in colOptions["sl2pDomain"]["features"]
            ]
        )
    )
    bandList = {
        b: netOptions["inputBands"].index(b)
        for b in netOptions["inputBands"]
        if b.startswith("B")
    }
    image = image.reshape(image.shape[0], image.shape[1] * image.shape[2])[
        list(bandList.values()), :
    ]

    # Image formatting
    image_format = numpy.sum(
        (numpy.uint8(numpy.ceil(image * 10) % 10))
        * numpy.array([10**value for value in range(len(bandList))])[:, None],
        axis=0,
    )

    flag = numpy.isin(image_format, sl2pDomain, invert=True)

    return flag.reshape(d1, d2)


# ibid but for CCRS
def invalidInput_CCRS(image, netOptions, colOptions):
    print("Generating sl2p input data flag")
    [d0, d1, d2] = image.shape
    sl2pDomain = numpy.sort(
        numpy.array(
            [
                row["properties"]["DomainCode"]
                for row in colOptions["sl2pDomain"]["features"]
            ]
        )
    )
    bandList = {
        b: netOptions["inputBands"].index(b)
        for b in netOptions["inputBands"]
        if b.startswith("B")
    }
    image = image.reshape(image.shape[0], image.shape[1] * image.shape[2])[
        list(bandList.values()), :
    ]

    # Image formatting
    image_format = numpy.sum(
        (numpy.uint8(numpy.ceil(image * 10) % 10))
        * numpy.array([10**value for value in range(len(bandList))])[:, None],
        axis=0,
    )

    # Comparing image to sl2pDomain
    flag = numpy.isin(image_format, sl2pDomain, invert=True).astype(int)

    return flag.reshape(d1, d2)


# determine if outputs fall in the nominal variation range of the variable
def invalidOutput(estimate, variableName):
    print("Generating sl2p output product flag")
    var_range = dictionariesSL2P.make_outputParams()[variableName]
    return numpy.where(
        estimate < var_range["outputOffset"],
        1,
        numpy.where(estimate > var_range["outputMax"], 1, 0),
    )


# ibid but for CCRS
def invalidOutput_CCRS(estimate, netOptions):
    print("Generating sl2p output product flag")
    return numpy.where(
        (estimate < netOptions["outmin"]) | (estimate > netOptions["outmax"]), 1, 0
    )


# Secondary function of SL2P for CCRS, preparing the SL2P model and running it through the neural network
def apply_net(
    array_input, variableName, imageCollectionName, algorithm, method, partition=1
):

    sl2p_inp = array_input.T
    sl2p_inp = numpy.reshape(
        sl2p_inp, (sl2p_inp.shape[0], sl2p_inp.shape[1], -1)
    )  # reshaping the input array sl2p_inp so that it has: 1st dim the same as shape[0],
    # 2nd dim same as shape[1], 3rd dim inferred

    networkOptions = dictionariesSL2P.make_net_options_CCRS()
    collectionOptions = dictionariesSL2P.make_collection_options_CCRS(algorithm)

    # Network specific options (scaling, offset, column and band names, etc.)
    netOptions = networkOptions[variableName][imageCollectionName]
    # Collection specific options (NN weights, biases, etc.)
    colOptions = collectionOptions[imageCollectionName]

    # prepare SL2P networks
    SL2P, errorsSL2P = makeModel_CCRS(
        algorithm, netOptions, colOptions
    )  # specific function for CCRS

    # Run SL2P (actual NN application part)
    print("Run SL2P...\nSL2P start: %s" % datetime.now())
    estimate, networkID = toolsNets.wrapperNNets_CCRS(
        SL2P, netOptions, colOptions, sl2p_inp, partition=partition
    )
    error, uncertainty = toolsNets.wrapperNNets_CCRS(
        errorsSL2P, netOptions, colOptions, sl2p_inp, partition=partition
    )
    print("SL2P end: %s" % datetime.now())

    # Generate sl2p I/O data flag
    qc_input = invalidInput_CCRS(sl2p_inp, netOptions, colOptions)
    qc_output = invalidOutput_CCRS(estimate, netOptions)

    # Stack the results into a single array
    out_array = numpy.stack(
        [estimate, networkID, error, qc_input.flatten(), qc_output], axis=1
    )

    return out_array


def SL2PCCRS(samples_array, variableName, imageCollectionName, tile, method):
    # Print a message indicating the start of the SL2P-CCRS estimation process
    print(
        "Estimating %s from %s data using SL2P-CCRS"
        % (variableName, imageCollectionName)
    )

    # Import the SL2PV1 algorithm module, which will be used for the estimation
    from tools import SL2PV1 as algorithm

    # Generate collection options specific to the SL2PV1 algorithm e.g., "Collection_SL2P": fc.s2_createFeatureCollection_estimates() with fc = algorithm
    # collectionOptions = dictionariesSL2P.make_collection_options(algorithm)

    partition_array = make_partition(
        tile, (samples_array.shape[1], samples_array.shape[2])
    )

    # Check if partition exists / is valid
    if partition_array is None or partition_array.shape[:2] != samples_array.shape[1:]:
        raise ValueError(
            "You should provide a valid partition array when using SL2P-CCRS!!\n"
        )

    bands, H, W = samples_array.shape
    samples_flat = samples_array.reshape(bands, -1).T  # (H*W, bands)
    partition_flat = partition_array.flatten()  # (H*W,)

    # Initialize arrays to store outputs and indices
    outputs = []
    indices = []

    # For each unique value in column partition...
    for partition_value in numpy.unique(partition_flat):
        # ...Filter the input DataFrame to include only rows corresponding to the current partition
        mask = (
            partition_flat == partition_value
        )  # Creates a mask to filter the samples_array based on the current partition value
        selected_inputs = samples_flat[
            mask
        ]  # Applies the mask to the samples_array to get the rows corresponding to the current partition

        # Apply the SL2P algorithm to the filtered DataFrame for the current partition
        out_values = apply_net(
            selected_inputs,
            variableName,
            imageCollectionName,
            algorithm,
            method,
            partition=partition_value,
        )

        # Ensure output is array
        if isinstance(out_values, pd.DataFrame):
            out_values = out_values.to_numpy()

        # Append partition and index info for sorting
        partition_column = numpy.full((out_values.shape[0], 1), partition_value)
        indexed_output = numpy.hstack((out_values, partition_column))

        outputs.append(indexed_output)
        indices.append(numpy.where(mask)[0])

    # Concatenate all results
    all_outputs = numpy.vstack(outputs)
    all_indices = numpy.concatenate(indices)

    # Sort with original index
    sorted_idx = numpy.argsort(all_indices)
    final_output = all_outputs[sorted_idx]

    return final_output


# Given a tile and its shape, returns a partition array. Could be substituted with a more complex partitioning logic.
def make_partition(tile, tile_shape):
    """
    LAND COVER CLASSES INFORMATION
    {'close_cropland': 1,
    'deciduous_broadleaf_forest': 2,
    'evergreen_needleaf_forest': 3,
    'grassland_pasture': 4,
    'invalid': 0,
    'lichen_feathermoss': 5,
    'lon': 0, ?????
    'mixed_forest': 11,
    'polar_grassland': 6,
    'polar_shrubland': 7,
    'shrublands': 8,
    'sparse_cropland': 9,
    'sphagnum_feathermoss': 10}
    """

    if tile is None:
        partition = None

    elif tile == "TEST":  # Only used for development purposes
        partition = numpy.random.choice([2, 3, 4], size=(tile_shape), replace=True)

    elif tile == "T32TPS":  # Needs fixing
        partition = None

    return partition
