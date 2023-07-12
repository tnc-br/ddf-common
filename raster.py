###############################################################################
# MIT License
# 
# Copyright (c) 2023 The Nature Conservancy - Brazil
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
###############################################################################
from dataclasses import dataclass
from osgeo import gdal, gdal_array
import numpy as np
from typing import List
import matplotlib.pyplot as plt
import math
import glob
import os
import matplotlib.animation as animation

GDRIVE_BASE = ""
RASTER_BASE = ""
MODEL_BASE = ""
SAMPLE_DATA_BASE = ""
ANIMATIONS_BASE = ""
TEST_DATA_BASE = ""
MOUNTED = False

# Module for helper functions for manipulating data and datasets.
@dataclass
class AmazonGeoTiff:
  """Represents a geotiff from our dataset."""
  gdal_dataset: gdal.Dataset
  image_value_array: np.ndarray # ndarray of floats
  image_mask_array: np.ndarray # ndarray of uint8
  masked_image: np.ma.masked_array
  yearly_masked_image: np.ma.masked_array

@dataclass
class Bounds:
  """Represents geographic bounds and size information."""
  minx: float
  maxx: float
  miny: float
  maxy: float
  pixel_size_x: float
  pixel_size_y: float
  raster_size_x: float
  raster_size_y: float

def to_matplotlib(self) -> List[float]:
  return [self.minx, self.maxx, self.miny, self.maxy]

def get_raster_path(filename: str) -> str:
  global GDRIVE_BASE
  global RASTER_BASE
  root = GDRIVE_BASE if GDRIVE_BASE else ""
  return f"{root}{RASTER_BASE}{filename}"

def get_model_path(filename: str) -> str:
  global GDRIVE_BASE
  global MODEL_BASE

  root = GDRIVE_BASE if GDRIVE_BASE else ""
  return f"{root}{MODEL_BASE}{filename}"

def get_sample_db_path(filename: str) -> str:
  global GDRIVE_BASE
  global SAMPLE_DATA_BASE

  root = GDRIVE_BASE if GDRIVE_BASE else ""
  return f"{root}{SAMPLE_DATA_BASE}{filename}"

def get_animations_path(filename: str) -> str:
  global GDRIVE_BASE
  global ANIMATIONS_BASE

  root = GDRIVE_BASE if GDRIVE_BASE else ""
  return f"{root}{ANIMATIONS_BASE}{filename}"

def mount_gdrive():
  global MOUNTED
  if not MOUNTED:
    MOUNTED = True
    # Access data stored on Google Drive
    if GDRIVE_BASE:
        from google.colab import drive
        drive.mount(GDRIVE_BASE)

def print_raster_info(raster):
  dataset = raster
  print("Driver: {}/{}".format(dataset.GetDriver().ShortName,
                              dataset.GetDriver().LongName))
  print("Size is {} x {} x {}".format(dataset.RasterXSize,
                                      dataset.RasterYSize,
                                      dataset.RasterCount))
  print("Projection is {}".format(dataset.GetProjection()))
  geotransform = dataset.GetGeoTransform()
  if geotransform:
      print("Origin = ({}, {})".format(geotransform[0], geotransform[3]))
      print("Pixel Size = ({}, {})".format(geotransform[1], geotransform[5]))

  for band in range(dataset.RasterCount):
    band = dataset.GetRasterBand(band+1)
    #print("Band Type={}".format(gdal.GetDataTypeName(band.DataType)))

    min = band.GetMinimum()
    max = band.GetMaximum()
    if not min or not max:
        (min,max) = band.ComputeRasterMinMax(False)
    #print("Min={:.3f}, Max={:.3f}".format(min,max))

    if band.GetOverviewCount() > 0:
        print("Band has {} overviews".format(band.GetOverviewCount()))

    if band.GetRasterColorTable():
        print("Band has a color table with {} entries".format(band.GetRasterColorTable().GetCount()))

def load_raster(path: str, use_only_band_index: int = -1) -> AmazonGeoTiff:
  """
  TODO: Refactor (is_single_band, etc., should be a better design)
  --> Find a way to simplify this logic. Maybe it needs to be more abstract.
  """
  mount_gdrive()
  dataset = gdal.Open(path, gdal.GA_ReadOnly)
  try:
    print_raster_info(dataset)
  except AttributeError as e:
    raise OSError("Failed to print raster. This likely means it did not load properly from "+ path)
  image_datatype = dataset.GetRasterBand(1).DataType
  mask_datatype = dataset.GetRasterBand(1).GetMaskBand().DataType
  image = np.zeros((dataset.RasterYSize, dataset.RasterXSize, 12),
                  dtype=gdal_array.GDALTypeCodeToNumericTypeCode(image_datatype))
  mask = np.zeros((dataset.RasterYSize, dataset.RasterXSize, 12),
                  dtype=gdal_array.GDALTypeCodeToNumericTypeCode(image_datatype))

  if use_only_band_index == -1:
    if dataset.RasterCount != 12 and dataset.RasterCount != 1:
      raise ValueError(f"Expected 12 raster bands (one for each month) or one annual average, but found {dataset.RasterCount}")
    if dataset.RasterCount == 1:
      use_only_band_index = 0

  is_single_band = use_only_band_index != -1

  if is_single_band and use_only_band_index >= dataset.RasterCount:
    raise IndexError(f"Specified raster band index {use_only_band_index}"
    f" but there are only {dataset.RasterCount} rasters")

  for band_index in range(12):
    band = dataset.GetRasterBand(use_only_band_index+1 if is_single_band else band_index+1)
    image[:, :, band_index] = band.ReadAsArray()
    mask[:, :, band_index] = band.GetMaskBand().ReadAsArray()
  masked_image = np.ma.masked_where(mask == 0, image)
  yearly_masked_image = masked_image.mean(axis=2)

  return AmazonGeoTiff(dataset, image, mask, masked_image, yearly_masked_image)

def get_extent(dataset):
  geoTransform = dataset.GetGeoTransform()
  minx = geoTransform[0]
  maxy = geoTransform[3]
  maxx = minx + geoTransform[1] * dataset.RasterXSize
  miny = maxy + geoTransform[5] * dataset.RasterYSize
  return Bounds(minx, maxx, miny, maxy, geoTransform[1], geoTransform[5], dataset.RasterXSize, dataset.RasterYSize)

def plot_band(geotiff: AmazonGeoTiff, month_index, figsize=None):
  if figsize:
    plt.figure(figsize=figsize)
  im = plt.imshow(geotiff.masked_image[:,:,month_index], extent=get_extent(geotiff.gdal_dataset).to_matplotlib(), interpolation='none')
  plt.colorbar(im)

def animate(geotiff: AmazonGeoTiff, nSeconds, fps):
  fig = plt.figure( figsize=(8,8) )

  months = []
  labels = []
  for m in range(12):
    months.append(geotiff.masked_image[:,:,m])
    labels.append(f"Month: {m+1}")
  a = months[0]
  extent = get_extent(geotiff.gdal_dataset).to_matplotlib()
  ax = fig.add_subplot()
  im = fig.axes[0].imshow(a, interpolation='none', aspect='auto', extent = extent)
  txt = fig.text(0.3,0,"", fontsize=24)
  fig.colorbar(im)

  def animate_func(i):
    if i % fps == 0:
      print( '.', end ='' )

    im.set_array(months[i])
    txt.set_text(labels[i])
    return [im, txt]

  anim = animation.FuncAnimation(
                                fig,
                                animate_func,
                                frames = nSeconds * fps,
                                interval = 1000 / fps, # in ms
                                )
  plt.close()

  return anim

def save_numpy_to_geotiff(bounds: Bounds, prediction: np.ma.MaskedArray, path: str):
  """Copy metadata from a base geotiff and write raster data + mask from `data`"""
  driver = gdal.GetDriverByName("GTiff")
  metadata = driver.GetMetadata()
  if metadata.get(gdal.DCAP_CREATE) != "YES":
      raise RuntimeError("GTiff driver does not support required method Create().")
  if metadata.get(gdal.DCAP_CREATECOPY) != "YES":
      raise RuntimeError("GTiff driver does not support required method CreateCopy().")

  dataset = driver.Create(path, bounds.raster_size_x, bounds.raster_size_y, prediction.shape[2], eType=gdal.GDT_Float64)
  dataset.SetGeoTransform([bounds.minx, bounds.pixel_size_x, 0, bounds.maxy, 0, bounds.pixel_size_y])
  dataset.SetProjection('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]')

  #dataset = driver.CreateCopy(path, base.gdal_dataset, strict=0)
  if len(prediction.shape) != 3 or prediction.shape[0] != bounds.raster_size_x or prediction.shape[1] != bounds.raster_size_y:
    raise ValueError("Shape of prediction does not match base geotiff")
  #if prediction.shape[2] > base.gdal_dataset.RasterCount:
  #  raise ValueError(f"Expected fewer than {dataset.RasterCount} bands in prediction but found {prediction.shape[2]}")

  prediction_transformed = np.flip(np.transpose(prediction, axes=[1,0,2]), axis=0)
  for band_index in range(dataset.RasterCount):
    band = dataset.GetRasterBand(band_index+1)
    if band.CreateMaskBand(0) == gdal.CE_Failure:
      raise RuntimeError("Failed to create mask band")
    mask_band = band.GetMaskBand()
    band.WriteArray(np.choose(prediction_transformed[:, :, band_index].mask, (prediction_transformed[:, :, band_index].data,np.array(band.GetNoDataValue()),)))
    mask_band.WriteArray(np.logical_not(prediction_transformed[:, :, band_index].mask))

def coords_to_indices(bounds: Bounds, x: float, y: float):
  if x < bounds.minx or x > bounds.maxx or y < bounds.miny or y > bounds.maxy:
    raise ValueError("Coordinates out of bounds")

  # X => lat, Y => lon
  x_idx = bounds.raster_size_y - int(math.ceil((y - bounds.miny) / abs(bounds.pixel_size_y)))
  y_idx = int((x - bounds.minx) / abs(bounds.pixel_size_x))

  return x_idx, y_idx

def test_coords_to_indices():
  bounds = Bounds(50, 100, 50, 100, 1, 1, 50, 50)
  x, y = coords_to_indices(bounds, 55, 55)
  assert x == 45
  assert y == 5

  bounds = Bounds(-100, -50, -100, -50, 1, 1, 50, 50)
  x, y = coords_to_indices(bounds, -55, -55)
  assert x == 5
  assert y == 45

  bounds = Bounds(-10, 50, -10, 50, 1, 1, 60, 60)
  x, y = coords_to_indices(bounds, -1, 13)
  assert x == 37
  assert y == 9

  bounds = Bounds(minx=-73.97513931345594, maxx=-34.808472803053895, miny=-33.73347244751509, maxy=5.266527396029211, pixel_size_x=0.04166666650042771, pixel_size_y=-0.041666666499513144, raster_size_x=937, raster_size_y=941)
  x, y = coords_to_indices(bounds, -67.14342073173958, -7.273271869467912e-05)
  #print(x)
  assert x == 131 # was: 132
  assert y == 163

# test_coords_to_indices()

def get_data_at_coords(dataset_tif: AmazonGeoTiff, x: float, y: float, month: int) -> float:
  # x = longitude
  # y = latitude
  bounds = get_extent(dataset_tif.gdal_dataset)
  x_idx, y_idx = coords_to_indices(bounds, x, y)
  if month == -1:
    value = dataset_tif.yearly_masked_image[x_idx, y_idx]
  else:
    value = dataset_tif.masked_image[x_idx, y_idx, month]
  if np.ma.is_masked(value):
    raise ValueError("Coordinates are masked")
  else:
    return value

brazil_map_geotiff_ = None
def brazil_map_geotiff() -> AmazonGeoTiff:
  global brazil_map_geotiff_
  if not brazil_map_geotiff_:
    brazil_map_geotiff_ = load_raster(get_raster_path("brasil_clim_raster.tiff"))
  return brazil_map_geotiff_

relative_humidity_geotiff_ = None
def relative_humidity_geotiff() -> AmazonGeoTiff:
  global relative_humidity_geotiff_
  if not relative_humidity_geotiff_:
    relative_humidity_geotiff_ = load_raster(get_raster_path("R.rh_Stack.tif"))
  return relative_humidity_geotiff_

temperature_geotiff_ = None
def temperature_geotiff() -> AmazonGeoTiff:
  global temperature_geotiff_
  if not temperature_geotiff_:
    temperature_geotiff_ = load_raster(get_raster_path("Temperatura_Stack.tif"))
  return temperature_geotiff_

vapor_pressure_deficit_geotiff_ = None
def vapor_pressure_deficit_geotiff() -> AmazonGeoTiff:
  global vapor_pressure_deficit_geotiff_
  if not vapor_pressure_deficit_geotiff_:
    vapor_pressure_deficit_geotiff_ = load_raster(get_raster_path("R.vpd_Stack.tif"))
  return vapor_pressure_deficit_geotiff_

atmosphere_isoscape_geotiff_ = None
def atmosphere_isoscape_geotiff() -> AmazonGeoTiff:
  global atmosphere_isoscape_geotiff_
  if not atmosphere_isoscape_geotiff_:
    atmosphere_isoscape_geotiff_ = load_raster(get_raster_path("Iso_Oxi_Stack.tif"))
  return atmosphere_isoscape_geotiff_

cellulose_isoscape_geotiff_ = None
def cellulose_isoscape_geotiff() -> AmazonGeoTiff:
  global cellulose_isoscape_geotiff_
  if not cellulose_isoscape_geotiff_:
    cellulose_isoscape_geotiff_ = load_raster(get_raster_path("iso_O_cellulose.tif"))
  return cellulose_isoscape_geotiff_



