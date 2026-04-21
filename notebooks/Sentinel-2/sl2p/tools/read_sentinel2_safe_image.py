import numpy, os, re
import rasterio
import xml.etree.ElementTree as ET 
from tqdm import tqdm
import zipfile
import scipy.ndimage 
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree
import shutil
 
# read Sentinel-2 image in SAFE format and return it as a dictionarry
def read_s2(safe,res):
    extracted_dir = '/tmp/safe_extracted'
    if safe.endswith('.SAFE'):
        inpath=safe+'/GRANULE/'+os.listdir(safe+'/GRANULE/')[0]+'/IMG_DATA/R%sm/'%(str(res))
        MTD_TL=safe+'/GRANULE/%s/MTD_TL.xml'%(os.listdir(safe+'/GRANULE/')[0])
    elif safe.endswith('.zip'):
        with zipfile.ZipFile(safe, 'r') as zip_ref:
            zip_ref.extractall(extracted_dir)
        safe = extracted_dir + '/' + os.path.basename(safe).replace('.zip', '.SAFE')
        inpath=safe+'/GRANULE/'+os.listdir(safe+'/GRANULE/')[0]+'/IMG_DATA/R%sm/'%(str(res))
        MTD_TL=safe+'/GRANULE/%s/MTD_TL.xml'%(os.listdir(safe+'/GRANULE/')[0])

    
    s2={}
    print('Reading Sentinel-2 image')
    # TL;DR: fn è il path completo di ogni file jp2
    for fn in tqdm([os.path.join(inpath,f) for f in os.listdir(inpath) if f.endswith('.jp2')]): 
        with rasterio.open(fn) as src:
            # update the dictionary with the metadata of the image
            s2.update({'profile':src.profile})
            # reads the first (and only) band of the .jp2 image, using a part of the file name as dictionary key
            s2.update({fn.split('_')[-2]:src.read(1)})  
           
    #add geometry of acquisition
    (SZA, SAA, colstep,rowstep)=extract_sun_angles(MTD_TL)
    (VZA, VAA, colstep,rowstep)=extract_sensor_angles(MTD_TL)
    s2.update({'SZA':SZA,'SAA':SAA,'VZA':VZA,'VAA':VAA})
    s2['profile'].update({'count':len(s2)-1})

    if extracted_dir and os.path.isdir(extracted_dir):
        shutil.rmtree(extracted_dir)

    return s2

# FILTER IF DOUBLE IMAGE, CHOOSE HIGHEST BASELINE
def select_highest_baseline(folder_path, image_names):
    best_per_acquisition = {}
    
    for name in image_names:
        try:
            # Split at the baseline indicator 
            prefix, after_n = name.split("_N", 1)
            # Extract the numeric baseline (from 0509 to 509)
            baseline_str = after_n.split("_", 1)[0]
            baseline = int(baseline_str)
        except (ValueError, IndexError):
            # If name doesn't follow the expected pattern, keep it by default
            best_per_acquisition.setdefault(name, (name, -1))
            continue
        
        # If this prefix is new or we've found a higher baseline, update
        current_best = best_per_acquisition.get(prefix)
        if current_best is None or baseline > current_best[1]:
            best_per_acquisition[prefix] = (name, baseline)
    
    # Return only the folder names (discard the baseline integers)
    return [entry[0] for entry in best_per_acquisition.values()]

def select_highest_baseline_unique(folder_path, image_names):
    """
    Selects the highest baseline image for each unique acquisition date.

    Parameters:
        folder_path (str): Path to the folder containing the images.
        image_names (list): List of image file names to process. If empty, all files in the folder will be used.

    Returns:
        list: Filtered list of image names, keeping only the highest baseline image for each unique date.
    """

    # If no list of image names is provided, read all files in the folder
    if not image_names:
        try:
            image_names = [f for f in os.listdir(folder_path)
                           if os.path.isfile(os.path.join(folder_path, f))]
        except Exception as e:
            raise RuntimeError(f"Failed to list files in {folder_path}: {e}")

    # Define a regex pattern to extract unique acquisition dates from image names
    # Example: Extracts "20230101" from "S2A_MSIL2A_20230101T123456_N0500.zip"
    date_pattern = re.compile(r"S2[AB]_MSIL2A_(\d{8})T")
    unique_dates = set()

    # Collect all unique acquisition dates from the image names
    for name in image_names:
        m = date_pattern.search(name)
        if m:
            unique_dates.add(m.group(1))

    filtered = []
    
    # Define a regex pattern to extract the baseline value from image names
    # Example: Extracts "0500" from "S2A_MSIL2A_20230101T123456_N0500.zip"
    baseline_pattern = re.compile(r"_N0(\d{3})")

    # Loop over each unique acquisition date
    for date in unique_dates:
        # Find all images that match the current date
        matches = [name for name in image_names if date in name]
        if len(matches) == 1:
            # If only one image matches the date, add it to the filtered list
            filtered.append(matches[0])
        else:
            # If multiple images match the date, select the one with the highest baseline
            best = matches[0]
            best_value = -1
            for name in matches:
                m = baseline_pattern.search(name)
                if m:
                    val = int(m.group(1))  # Convert the baseline value to an integer
                    if val > best_value:
                        # Update the best image and its baseline value
                        best_value = val
                        best = name
            filtered.append(best)  # Add the best image for the current date to the filtered list

    return filtered

# KEEP ONLY VALID IMAGES (THAT CAN BE OPENED)
def filter_valid_images(folder_path, image_names):
    valid_images = []

    for name in image_names:
        full_path = os.path.join(folder_path, name)
        try:
            if name.lower().endswith('.zip'):
                # Try opening the ZIP and ensure it contains at least one file
                with zipfile.ZipFile(full_path, 'r') as zf:
                    if not zf.namelist():
                        raise ValueError("empty archive")
            
            elif name.lower().endswith('.safe'):
                # Check directory exists and is non-empty
                if not os.path.isdir(full_path) or not os.listdir(full_path):
                    raise ValueError("missing or empty SAFE folder")
                # Try parsing at least one metadata XML to catch corruption
                # (MTD_MSIL1C.xml or MTD_MSIL2A.xml)
                xml_files = [f for f in os.listdir(full_path) if f.upper().startswith('MTD_') and f.endswith('.xml')]
                if not xml_files:
                    raise ValueError("no metadata XML found in SAFE folder")
                # parse the first metadata file
                ET.parse(os.path.join(full_path, xml_files[0]))
            
            else:
                # Unknown extension: skip it
                raise ValueError("unsupported extension")
        
        except (zipfile.BadZipFile, zipfile.LargeZipFile, ET.ParseError, ValueError, OSError) as e:
            # Could not open / parse / folder missing – drop this image
            # (you could log e if desired)
            continue
        
        # If we reach here, image looks valid
        valid_images.append(name)
    
    return valid_images


# Filter out unnecessary Sentinel-2 images based on tile, level, and baseline
def process_image_names(folder_path, tile, year):

    # Extract file names ending with .zip or .SAFE
    image_names = [file for file in os.listdir(folder_path) if file.endswith(('.zip', '.SAFE'))]
    print(f"Number of elements in folder: {len(image_names)}")

    # Filter the images by level
    image_names = [name for name in image_names if name.split('_')[1] == "MSIL2A"]
    print(f"\nFiltered image names for level MSIL2A")
    print(f"New number of elements: {len(image_names)}")

    # Filter the images by tile
    image_names = [name for name in image_names if name.split('_')[5] == tile]
    print(f"\nFiltered image names for tile {tile}")
    print(f"New number of elements: {len(image_names)}")

    # Filter out images that cannot be opened
    image_names = filter_valid_images(folder_path, image_names)
    print("\nFiltered image names that can be opened")
    print(f"New number of elements: {len(image_names)}")

    # Filter the images by baseline
    image_names = select_highest_baseline_unique(folder_path, image_names)
    print("\nFiltered image names by baseline")
    print(f"New number of elements: {len(image_names)}")

    # Extract Processing Baseline
    pbs = [int(re.search(r'_N(\d{4})', image_name).group(1)[1:2]) for image_name in image_names]

    return image_names, pbs


# extract sun view and azimuth angles from xml file saved in Sentinel-2 SAFE data
def extract_sun_angles(xml):
    """Extract Sentinel-2 solar angle bands values from MTD_TL.xml.
    Parameters:
       xml (str): path to MTD_TL.xml.
    Returns:
       str, str: sz_path, sa_path: path to solar zenith image, path to solar azimuth image, respectively.
    """
    solar_zenith_values = numpy.empty((23,23,)) * numpy.nan #initiates matrix
    solar_azimuth_values = numpy.empty((23,23,)) * numpy.nan

    # Parse the XML file
    tree = ET.parse(xml)
    root = tree.getroot()

    # Find the angles
    for child in root:
        if child.tag[-14:] == 'Geometric_Info':
            geoinfo = child

    for segment in geoinfo:
        if segment.tag == 'Tile_Angles':
            angles = segment

    for angle in angles:
        if angle.tag == 'Sun_Angles_Grid':
            for bset in angle:
                if bset.tag == 'Zenith':
                    zenith = bset
                if bset.tag == 'Azimuth':
                    azimuth = bset
            for field in zenith:
                if field.tag == 'Values_List':
                    zvallist = field
            for field in azimuth:
                if field.tag == 'Values_List':
                    avallist = field
                
                if field.tag == 'COL_STEP':
                    colstep= float(field.text)   
                if field.tag == 'ROW_STEP':
                    rowstep= float(field.text)   
                    
            for rindex in range(len(zvallist)):
                zvalrow = zvallist[rindex]
                avalrow = avallist[rindex]
                zvalues = zvalrow.text.split(' ')
                avalues = avalrow.text.split(' ')
                values = list(zip(zvalues, avalues)) #row of values
                for cindex in range(len(values)):
                    if ( values[cindex][0] != 'NaN' and values[cindex][1] != 'NaN'):
                        zen = float(values[cindex][0])
                        az = float(values[cindex][1])
                        solar_zenith_values[rindex,cindex] = zen
                        solar_azimuth_values[rindex,cindex] = az
    return (solar_zenith_values, solar_azimuth_values,colstep,rowstep)

# extract sensor view and azimuth angles from xml file saved in Sentinel-2 SAFE data
def extract_sensor_angles(xml):
    """Extract Sentinel-2 view (sensor) angle bands values from MTD_TL.xml.
    Parameters:
       xml (str): path to MTD_TL.xml.
    Returns:
       str, str: path to view (sensor) zenith image and path to view (sensor) azimuth image, respectively.
    """
    numband = 13
    sensor_zenith_values = numpy.empty((numband,23,23)) * numpy.nan #initiates matrix
    sensor_azimuth_values = numpy.empty((numband,23,23)) * numpy.nan

    # Parse the XML file
    tree = ET.parse(xml)
    root = tree.getroot()

    # Find the angles
    for child in root:
        if child.tag[-14:] == 'Geometric_Info':
            geoinfo = child

    for segment in geoinfo:
        if segment.tag == 'Tile_Angles':
            angles = segment

    for angle in angles:
        if angle.tag == 'Viewing_Incidence_Angles_Grids':
            bandId = int(angle.attrib['bandId'])
            for bset in angle:
                if bset.tag == 'Zenith':
                    zenith = bset
                if bset.tag == 'Azimuth':
                    azimuth = bset
            for field in zenith:
                if field.tag == 'Values_List':
                    zvallist = field
            for field in azimuth:
                if field.tag == 'Values_List':
                    avallist = field  
                if field.tag == 'COL_STEP':
                    colstep= float(field.text)
                if field.tag == 'ROW_STEP':
                    rowstep= float(field.text)    
                    
            for rindex in range(len(zvallist)):
                zvalrow = zvallist[rindex]
                avalrow = avallist[rindex]
                zvalues = zvalrow.text.split(' ')
                avalues = avalrow.text.split(' ')
                values = list(zip(zvalues, avalues )) #row of values
                for cindex in range(len(values)):
                    if (values[cindex][0] != 'NaN' and values[cindex][1] != 'NaN'):
                        zen = float(values[cindex][0])
                        az = float(values[cindex][1])
                        sensor_zenith_values[bandId, rindex,cindex] = zen
                        sensor_azimuth_values[bandId, rindex,cindex] = az
    sensor_zenith_values = sensor_zenith_values[7]
    sensor_azimuth_values = sensor_azimuth_values[7]
    return(sensor_zenith_values, sensor_azimuth_values,colstep,rowstep)

# resample a given image (2D numpy-array) considering a resampeling factor and an interpolation algo 
def resample_image(img,factor,interpolation='nearest'):
    if interpolation=='nearest':
        order=0
    elif interpolation=='bilinear':
        order=1
    elif interpolation=='cubic':
        order=2  
    else:
        raise ValueError("interpolation algorithm must be one of the following:  nearest, bilinear, cubic ")
    return scipy.ndimage.zoom(img, factor, order=order)


def interpolate_angle_grid(angle_grid, target_shape):
    """Interpolate a coarse Sentinel-2 angle grid onto a target raster size."""
    if angle_grid.shape == target_shape:
        return angle_grid

    def _fill_nan_with_nearest(grid):
        mask = ~numpy.isfinite(grid)
        if not mask.any():
            return grid
        # get coordinates of valid samples
        coords = numpy.array(numpy.nonzero(~mask)).T
        if coords.size == 0:
            raise ValueError("Angle grid does not contain any valid samples")
        values = grid[~mask]
        missing = numpy.array(numpy.nonzero(mask)).T
        tree = cKDTree(coords)
        nearest_idx = tree.query(missing, k=1)[1]
        filled = grid.copy()
        filled[mask] = values[nearest_idx]
        return filled

    rows, cols = angle_grid.shape
    filled_grid = _fill_nan_with_nearest(angle_grid)
    grid_y = numpy.linspace(0.0, 1.0, rows)
    grid_x = numpy.linspace(0.0, 1.0, cols)
    target_y = numpy.linspace(0.0, 1.0, target_shape[0])
    target_x = numpy.linspace(0.0, 1.0, target_shape[1])

    interpolator = RegularGridInterpolator((grid_y, grid_x), filled_grid, bounds_error=False, fill_value=None)

    mesh_y, mesh_x = numpy.meshgrid(target_y, target_x, indexing='ij')
    sample_points = numpy.stack([mesh_y.ravel(), mesh_x.ravel()], axis=-1)
    return interpolator(sample_points).reshape(target_shape)

"""
def interpolate_angle_grid(angle_grid, target_shape):
    """"""Interpolate a coarse Sentinel-2 angle grid to the requested shape.

    The SAFE metadata provides solar/viewing angles on a sparse 23x23 grid.
    This helper upsamples that grid to the spatial resolution of a reference
    spectral band by performing bilinear interpolation in the normalized grid
    coordinates so that smooth gradients (e.g., sloped terrain) are preserved.
    """"""
    if angle_grid.shape == target_shape:
        return angle_grid

    rows, cols = angle_grid.shape #23x23
    print("Interpolating angle grid from %s to %s" % (angle_grid.shape, target_shape))
    print("rows: %s, cols: %s" % (rows, cols)) #23x23

    # normalized coordinates of the coarse grid nodes and target pixels
    grid_y = numpy.linspace(0.0, 1.0, rows)
    grid_x = numpy.linspace(0.0, 1.0, cols)
    target_y = numpy.linspace(0.0, 1.0, target_shape[0]) #height is 10980*10980
    target_x = numpy.linspace(0.0, 1.0, target_shape[1]) 

    interpolator = RegularGridInterpolator((grid_y, grid_x), angle_grid, bounds_error=False, fill_value=None)

    mesh_y, mesh_x = numpy.meshgrid(target_y, target_x, indexing='ij')
    sample_points = numpy.stack([mesh_y.ravel(), mesh_x.ravel()], axis=-1)
    return interpolator(sample_points).reshape(target_shape)
"""


#def extract_boa_add_offset_values(xml): 
#     # Parse the XML file
#     tree = ET.parse(xml)
#     root = tree.getroot()
#     # Find the angles
#     for child in root:
#         if child.tag[-12:] == 'General_Info':
#             general_info = child       
#     for segment in general_info:
#         if segment.tag == 'Product_Image_Characteristics':
#             image_characteristics = segment
#     for sub_segment in image_characteristics: 
#         if sub_segment.tag == 'BOA_ADD_OFFSET_VALUES_LIST':  
#             BOA_ADD_OFFSET={'band_%s'%(value.attrib ['band_id']):float(value.text) for value in sub_segment if value.tag[:14]=='BOA_ADD_OFFSET'} 
#     return BOA_ADD_OFFSET

# def extract_quantification_values(xml):
#     # Parse the XML file
#     tree = ET.parse(xml)
#     root = tree.getroot()
#     # Find the angles
#     for child in root:
#         if child.tag[-12:] == 'General_Info':
#             general_info = child       
#     for segment in general_info:
#         if segment.tag == 'Product_Image_Characteristics':
#             image_characteristics = segment
#     for sub_segment in image_characteristics: 
#         if sub_segment.tag == 'QUANTIFICATION_VALUES_LIST':
#             QUANTIFICATION={value.tag:float(value.text) for value in sub_segment}
#     return QUANTIFICATION
