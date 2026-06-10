# from tools import toolsNets
import numpy


# re-order asset/nets (pkl file) according to the variale ID ('tabledata3'),
# then, build the different nets using makeNets function
def makeNetVars(asset, numNets, variableNum):
    filtered_features = [
        ff
        for ff in asset["features"]
        if ff["properties"]["tabledata3"] == variableNum + 1
    ]
    netVars = [makeNets(filtered_features, netNum) for netNum in range(numNets)]
    return netVars


# read coefficients of a network from pkl files ./nets
def getCoefs(netData, ind):
    return netData["properties"]["tabledata%s" % (ind)]


# parse the pkl file to buit SL2P nets for the different vegetation variables
# assume a two hidden layer network with tansig functions but allow for variable nodes per layer
def makeNets(feature, M):
    # get the requested network and initialize the created network
    netData = feature[M]
    net = {}

    # input slope
    num = 6
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["inpSlope"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # input offset
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["inpOffset"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # hidden layer 1 weight
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["h1wt"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # hidden layer 1 bias
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["h1bi"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # hidden layer 2 weight
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["h2wt"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # hidden layer 2 bias
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["h2bi"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # output slope
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["outSlope"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]

    # output offset
    num = end + 1
    start = num + 1
    end = num + netData["properties"]["tabledata%s" % (num)]
    net["outBias"] = [getCoefs(netData, ind) for ind in range(start, end + 1)]
    return [net]


# Generates a network ID corresponding to a given image based on landcover and network mapping.
def makeIndexLayer(image, legend, Network_Ind):

    landcover = [ff["properties"]["Value"] for ff in legend["features"]]
    landcover_name = [ff["properties"]["SL2P Network"] for ff in legend["features"]]
    networkIDs = [Network_Ind["features"][0]["properties"][nn] for nn in landcover_name]
    return networkIDs[landcover.index(image)]


# select the appropriate net for a given 'variable', then apply it by using applyNet function
def wrapperNNets(network, netOptions, imageInput, method):
    netList = network[netOptions["variable"] - 1]
    return applyNet(imageInput, netList)


# ibid, but for CCRS
def wrapperNNets_CCRS(network, netOptions, colOptions, imageInput, partition=0):

    # FYI: imageInput is a numpy array at this point in the code

    netList = network[netOptions["variable"] - 1]
    Network_Ind = makeIndexLayer(
        partition, colOptions["legend"], colOptions["Network_Ind"]
    )
    return applyNet_CCRS(imageInput, netList, Network_Ind), numpy.repeat(
        Network_Ind, imageInput.shape[1]
    )


# apply net on a 3D dataset (K.N.M) of Surface reflectance and acquisition geometry
# to have an estimate of a vegetation variable/uncertainty
def applyNet(inp, net):

    # FYI: inp is a numpy array at this point in the code

    [d0, d1, d2] = inp.shape
    inp = inp.reshape(d0, d1 * d2)
    inpSlope = numpy.array(net[0][0]["inpSlope"])
    inpOffset = numpy.array(net[0][0]["inpOffset"])
    h1wt = numpy.array(net[0][0]["h1wt"])
    h2wt = numpy.array(net[0][0]["h2wt"])
    h1bi = numpy.array(net[0][0]["h1bi"])
    h2bi = numpy.array(net[0][0]["h2bi"])
    outBias = numpy.array(net[0][0]["outBias"])
    outSlope = numpy.array(net[0][0]["outSlope"])

    # input scaling
    l1inp2D = (inp * inpSlope[:, None]) + inpOffset[:, None]

    # hidden layers
    l12D = (
        numpy.matmul(numpy.reshape(h1wt, [len(h1bi), len(inpOffset)]), l1inp2D)
        + h1bi[:, None]
    )

    # apply tansig 2/(1+exp(-2*n))-1
    l2inp2D = 2 / (1 + numpy.exp(-2 * l12D)) - 1

    # purlin hidden layers
    l22D = numpy.sum(l2inp2D * h2wt[:, None], axis=0) + h2bi

    # output scaling
    outputBand = (l22D - outBias[:, None]) / outSlope[:, None]

    outputBand = outputBand.reshape(d1, d2)

    return outputBand


# Specific function for CCRS method
def applyNet_CCRS(inp, net, Network_Ind):

    # FYI: inp is a numpy array at this point in the code

    [d0, d1, d2] = inp.shape
    inp = inp.reshape(d0, d1 * d2)
    inpSlope = numpy.array(net[Network_Ind][0]["inpSlope"])
    inpOffset = numpy.array(net[Network_Ind][0]["inpOffset"])
    h1wt = numpy.array(net[Network_Ind][0]["h1wt"])
    h2wt = numpy.array(net[Network_Ind][0]["h2wt"])
    h1bi = numpy.array(net[Network_Ind][0]["h1bi"])
    h2bi = numpy.array(net[Network_Ind][0]["h2bi"])
    outBias = numpy.array(net[Network_Ind][0]["outBias"])
    outSlope = numpy.array(net[Network_Ind][0]["outSlope"])

    # input scaling
    l1inp2D = (inp * inpSlope[:, None]) + inpOffset[:, None]
    print("Input scaling (l1inp2D):", l1inp2D)
    print("Shape of l1inp2D:", l1inp2D.shape)
    print("Data type of l1inp2D:", l1inp2D.dtype)

    # hidden layers
    l12D = (
        numpy.matmul(numpy.reshape(h1wt, [len(h1bi), len(inpOffset)]), l1inp2D)
        + h1bi[:, None]
    )
    print("Hidden layer 1 (l12D):", l12D)
    print("Shape of l12D:", l12D.shape)
    print("Data type of l12D:", l12D.dtype)

    # apply tansig 2/(1+exp(-2*n))-1
    l2inp2D = 2 / (1 + numpy.exp(-2 * l12D)) - 1
    print("Tansig activation (l2inp2D):", l2inp2D)
    print("Shape of l2inp2D:", l2inp2D.shape)
    print("Data type of l2inp2D:", l2inp2D.dtype)

    # purlin hidden layers
    l22D = numpy.sum(l2inp2D * h2wt[:, None], axis=0) + h2bi
    print("Hidden layer 2 (l22D):", l22D)
    print("Shape of l22D:", l22D.shape)
    print("Data type of l22D:", l22D.dtype)

    # output scaling
    outputBand = (l22D - outBias[:, None]) / outSlope[:, None]
    print("Output scaling (outputBand):", outputBand)
    print("Shape of outputBand:", outputBand.shape)
    print("Data type of outputBand:", outputBand.dtype)

    outputBand = outputBand.reshape(d1, d2)
    print("Final output (outputBand reshaped):", outputBand)
    print("Shape of final outputBand:", outputBand.shape)
    print("Data type of final outputBand:", outputBand.dtype)

    return outputBand.flatten()
