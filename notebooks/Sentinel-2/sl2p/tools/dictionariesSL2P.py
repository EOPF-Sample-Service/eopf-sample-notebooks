# from tools import toolsS2


def define_input_resolution():
    RESOLUTION_OPTIONS = {
        "S2_10m": 10,  # Sentinel 2 resampled to 10 m bands:
        "S2_SR": 20,  # Sentinel 2 using 20 m bands:
    }
    return RESOLUTION_OPTIONS


def make_collection_options(fc):
    COLLECTION_OPTIONS = {
        # Sentinel 2 using 20 m bands:
        "S2_SR": {
            "name": "S2_SR",
            "description": "Sentinel 2A",
            "sza": "MEAN_SOLAR_ZENITH_ANGLE",
            "vza": "MEAN_INCIDENCE_ZENITH_ANGLE_B8A",
            "saa": "MEAN_SOLAR_AZIMUTH_ANGLE",
            "vaa": "MEAN_INCIDENCE_AZIMUTH_ANGLE_B8A",
            "Collection_SL2P": fc.s2_createFeatureCollection_estimates(),
            "Collection_SL2Perrors": fc.s2_createFeatureCollection_errors(),
            "sl2pDomain": fc.s2_createFeatureCollection_domains(),
            "Network_Ind": fc.s2_createFeatureCollection_Network_Ind(),
            "numVariables": 7,
            "exportRes": 20,
        },
        # Sentinel 2 using 20 m bands resampled to 10m:
        "S2_10m": {
            "name": "S2_SR",
            "description": "Sentinel 2A",
            "sza": "MEAN_SOLAR_ZENITH_ANGLE",
            "vza": "MEAN_INCIDENCE_ZENITH_ANGLE_B8A",
            "saa": "MEAN_SOLAR_AZIMUTH_ANGLE",
            "vaa": "MEAN_INCIDENCE_AZIMUTH_ANGLE_B8A",
            "Collection_SL2P": fc.s2_createFeatureCollection_estimates(),
            "Collection_SL2Perrors": fc.s2_createFeatureCollection_errors(),
            "sl2pDomain": fc.s2_createFeatureCollection_domains(),
            "Network_Ind": fc.s2_createFeatureCollection_Network_Ind(),
            "numVariables": 7,
            "exportRes": 10,
        },
    }
    return COLLECTION_OPTIONS


def make_net_options():
    NET_OPTIONS = {
        "LAI": {
            "S2_SR": {
                "Name": "LAI",
                "description": "Leaf area index",
                "variable": 1,
                "inputBands": [
                    "cosVZA",
                    "cosSZA",
                    "cosRAA",
                    "B03",
                    "B04",
                    "B05",
                    "B06",
                    "B07",
                    "B8A",
                    "B11",
                    "B12",
                ],
                "inputScaling": [
                    1,
                    1,
                    1,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                ],
                "inputOffset": [
                    0,
                    0,
                    0,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                ],
                "inputScaling_before": [
                    1,
                    1,
                    1,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                ],
                "inputOffset_before": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            },
            "S2_10m": {
                "Name": "LAI",
                "description": "Leaf area index",
                "variable": 1,
                "inputBands": [
                    "cosVZA",
                    "cosSZA",
                    "cosRAA",
                    "B03",
                    "B04",
                    "B05",
                    "B06",
                    "B07",
                    "B8A",
                    "B11",
                    "B12",
                ],
                "inputScaling": [
                    1,
                    1,
                    1,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                ],
                "inputOffset": [
                    0,
                    0,
                    0,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                ],
                "inputScaling_before": [
                    1,
                    1,
                    1,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                    0.0001,
                ],
                "inputOffset_before": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            },
            "S2_SR_10m": {
                "Name": "LAI",
                "description": "Leaf area index",
                "variable": 1,
                "inputBands": [
                    "cosVZA",
                    "cosSZA",
                    "cosRAA",
                    "B02",
                    "B03",
                    "B04",
                    "B08",
                ],
                "inputScaling": [1, 1, 1, 0.0001, 0.0001, 0.0001, 0.0001],
                "inputOffset": [
                    0,
                    0,
                    0,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                    -1000,
                ],
                "inputScaling_before": [1, 1, 1, 0.0001, 0.0001, 0.0001, 0.0001],
                "inputOffset_before": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            },
        }
    }
    return NET_OPTIONS


def make_outputParams():
    # output parameters
    outputParams = {
        "LAI": {"outputOffset": 0, "outputMax": 8},
        "DASF": {"outputOffset": 0, "outputMax": 1},
    }
    return outputParams
