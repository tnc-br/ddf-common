from dataclasses import dataclass
from sklearn.metrics import precision_recall_curve
import raster
import scipy.stats
import math
import pandas as pd
import numpy as np

_TREE_CODE_COLUMN_NAME = 'Code'
_LONGITUDE_COLUMN_NAME = 'long'
_LATITUDE_COLUMN_NAME = 'lat'
_FRAUDULENT_COLUMN_NAME = 'fraud'


@dataclass
class HypothesisTest:
    '''
    Represents a hypothesis test of a sample to an isoscape
    '''
    longitude: float
    latitude: float
    p_value: float
    p_value_threshold: float

@dataclass
class FraudMetrics:
    '''
    Collection of metrics for fraud detection
    '''
    isotope_column_names: list[str]
    accuracy: float
    precision: float
    recall: float

def sample_ttest(longitude: float,
                 latitude: float,
                 isotope_values: list[float],
                 means_isoscape: raster.AmazonGeoTiff,
                 variances_isoscape: raster.AmazonGeoTiff,
                 sample_size_per_location: int,
                 p_value_target: float) -> HypothesisTest:
    '''
    longitude: Of the sample
    latitude: Of the sample
    isotope_values: Of the sample
    means_isoscape: Isoscape that maps geographic coordinates to a mean isotope value.
    variances_isoscape: Isoscape that maps geographic coordinates to the variance of
                        isotope valuesat that location.
    sample_size_per_location: Number of samples per geographic location used to calculate
                              mean and variance in isoscapes.
    p_value_target: desired p_value for the t-test (e.sample_data: 0.05)
    '''
    if len(isotope_values) <= 1:
        raise ValueError  # Isotope values needs to be more than 1.

    isotope_mean = np.mean(isotope_values)
    isotope_variance = np.var(isotope_values)*(len(isotope_values) /
                                               (len(isotope_values) - 1))
    isotope_sample_count = len(isotope_values)

    # Values from prediction.
    predicted_isotope_mean = raster.get_data_at_coords(
        means_isoscape, longitude, latitude, 0)
    predicted_isotope_variance = raster.get_data_at_coords(
        variances_isoscape, longitude, latitude, 0)
    predicted_isotope_sample_count = sample_size_per_location

    # t-student Test
    _, p_value = scipy.stats.ttest_ind_from_stats(
        mean1=predicted_isotope_mean,
        std1=math.sqrt(predicted_isotope_variance),
        nobs1=predicted_isotope_sample_count,
        mean2=isotope_mean,
        std2=math.sqrt(isotope_variance),
        nobs2=isotope_sample_count,
        equal_var=False, alternative="two-sided"
    )

    return HypothesisTest(longitude, latitude, p_value, p_value_target)

def get_predictions(sample_data: pd.DataFrame,
                    isotope_column_names: list[str],
                    means_isoscapes: list[raster.AmazonGeoTiff],
                    variances_isoscapes: list[raster.AmazonGeoTiff],
                    sample_size_per_location: int):
  '''
  Calculates the p values of a hypothesis test for the elements specified by
  isotope_column_names using values from means_isoscapes and variances_isoscapes.

  sample_data: pd.DataFrame with lat, long, isotope_value and fraudulent columns
  means_isoscape: Isoscape that maps geographic coordinates to a mean isotope value.
  variances_isoscape: Isoscape that maps geographic coordinates to the variance of
                      isotope valuesat that location.
  sample_size_per_location: Number of samples per geographic location used to calculate
                            mean and variance in isoscapes.
  '''
  sample_data = sample_data.groupby([
      _TREE_CODE_COLUMN_NAME,
      _LONGITUDE_COLUMN_NAME,
      _LATITUDE_COLUMN_NAME,
      _FRAUDULENT_COLUMN_NAME])[isotope_column_names]
  predictions = pd.DataFrame()

  for group_key, isotope_values in sample_data:
    if isotope_values.shape[0] <= 1:
      continue

    p_values = []
    for i, isotope_column_name in enumerate(isotope_column_names):
      hypothesis_test = sample_ttest(longitude=group_key[1],
                                     latitude=group_key[2],
                                     isotope_values=isotope_values[isotope_column_name],
                                     means_isoscape=means_isoscapes[i],
                                     variances_isoscape=variances_isoscapes[i],
                                     sample_size_per_location=sample_size_per_location,
                                     p_value_target=None)
      p_values.append(hypothesis_test.p_value)
    combined_p_value = np.array(p_values).prod()
    if np.isnan(combined_p_value):
      continue

    row = {"Code": [group_key[0]],
            "lat": [group_key[1]],
            "long": [group_key[2]],
            "fraud": [group_key[3]],
            "predicted_fraud": [combined_p_value]}
    predictions = pd.concat([predictions, pd.DataFrame(row)], ignore_index=True)

  return predictions

def fraud_metrics(sample_data: pd.DataFrame,
                  isotope_column_names: list[str],
                  means_isoscapes: list[raster.AmazonGeoTiff],
                  variances_isoscapes: list[raster.AmazonGeoTiff],
                  sample_size_per_location: int,
                  p_value_target: float):
    '''
    Calculates the accuracy, precision, recall based on true positives and negatives,
    and the false positive and negatives. (go/ddf-glossary)

    sample_data: pd.DataFrame with lat, long, isotope_value and fraudulent columns
    means_isoscape: Isoscape that maps geographic coordinates to a mean isotope value.
    variances_isoscape: Isoscape that maps geographic coordinates to the variance of
                        isotope valuesat that location.
    sample_size_per_location: Number of samples per geographic location used to calculate
                              mean and variance in isoscapes.
    p_value_target: desired p_value for the t-test (e.sample_data: 0.05)
    '''
    predictions = get_predictions(sample_data,
                  isotope_column_names,
                  means_isoscapes,
                  variances_isoscapes,
                  sample_size_per_location)
    y_true = predictions['fraud']
    y_pred = predictions['predicted_fraud']
    precision, recall, thresholds = precision_recall_curve(
      y_true, y_pred)
    
    idx = np.where(thresholds == p_value_target)
    accuracy = predictions[
      predictions['fraud'] == predictions['predicted_fraud']].shape[0] / predictions.shape[0]

    return FraudMetrics(isotope_column_names, accuracy, precision[idx], recall[idx])