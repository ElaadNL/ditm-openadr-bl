from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import holidays
import pandas as pd

from influxdb_client.client.query_api_async import QueryApiAsync
from src.infrastructure.influxdb.dalidata.query_dali_data import retrieve_dali_data_between
from src.infrastructure.influxdb.standard_profiles.query_standard_profiles import retrieve_standard_profiles_between_dates
from src.infrastructure.weather_data.weather_forecast import WeatherForecastData

def _get_weather_features_for_dates(start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    """Get weather features for each date between the given datetime range.

    Args:
        start_date_inclusive (datetime): The start date (inclusive)
        end_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: The dataframe containing weather forecasts for the date range.
    """
    weather_forecast = WeatherForecastData()
    weather_forecasts = weather_forecast.etl_weather_forecast_data(start_date_inclusive, end_date_inclusive)
    return weather_forecasts.rename(columns={"date_time": "datetime"})

def _get_time_features_for_dates(start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    """Get time features for each date between the given datetime range.

    Args:
        start_date_inclusive (datetime): The start date (inclusive)
        end_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: The dataframe containing time features for the date range.
    """
    predict_datetimes_df = pd.DataFrame({
        "datetime": pd.date_range(
            start=start_date_inclusive,
            end=end_date_inclusive,
            freq="15min",
            tz=ZoneInfo("Europe/Amsterdam"),
            inclusive="left",
        )
    })

    predict_datetimes_df["year"] = predict_datetimes_df["datetime"].dt.year
    predict_datetimes_df["month"] = predict_datetimes_df["datetime"].dt.month
    predict_datetimes_df["day"] = predict_datetimes_df["datetime"].dt.day
    predict_datetimes_df["hour"] = predict_datetimes_df["datetime"].dt.hour
    predict_datetimes_df["minute"] = predict_datetimes_df["datetime"].dt.minute
    predict_datetimes_df["dayofyear"] = predict_datetimes_df["datetime"].dt.dayofyear
    predict_datetimes_df["dayofweek"] = predict_datetimes_df["datetime"].dt.dayofweek
    predict_datetimes_df["weekofyear"] = predict_datetimes_df["datetime"].dt.isocalendar().week

    weekend_cutoff = 5
    predict_datetimes_df["is_weekend"] = predict_datetimes_df["datetime"].dt.dayofweek.apply(func=lambda x: 1 if x >= weekend_cutoff else 0)
    
    nl_holidays = holidays.country_holidays(country="NL")
    predict_datetimes_df["is_holiday"] = predict_datetimes_df["datetime"].apply(func=lambda x: 1 if x.date() in nl_holidays else 0)
    return predict_datetimes_df

async def _get_lag_features_for_dates(query_api: QueryApiAsync, start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    """Get time features for each date between the given datetime range.

    Args:
        query_api (QueryApi): The read-only connection to the influx database.
        start_date_inclusive (datetime): The start date (inclusive)
        end_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: The dataframe containing time features for the date range.
    """
    predict_datetimes_df = pd.DataFrame({
        "datetime": pd.date_range(
            start=start_date_inclusive,
            end=end_date_inclusive,
            freq="15min",
            tz=ZoneInfo("Europe/Amsterdam"),
            inclusive="left",
        )
    })

    # Retrieve the dalidata starting from a year ago, since we account for the lag a year ago.
    start_date_year_ago = start_date_inclusive - timedelta(days=366)
    # Retrieve up to 1 day before the end_date
    end_date_day_ago = end_date_inclusive - timedelta(days=1)

    dalidata_df = await retrieve_dali_data_between(query_api=query_api, start_date_inclusive=start_date_year_ago, end_date_inclusive=end_date_day_ago)

    dalidata_df["datetime"] = pd.to_datetime(dalidata_df["datetime"], utc=True)
    dalidata_df = dalidata_df.set_index("datetime")

    lag_1_year_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(years=1))
    lag_1_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=1))
    lag_2_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=2))
    lag_3_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=3))
    lag_4_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=4))
    lag_5_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=5))
    lag_6_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=6))
    lag_7_day_dt = predict_datetimes_df["datetime"].apply(lambda dt: dt - pd.DateOffset(days=7))

    predict_datetimes_df["lag_1_year"] = dalidata_df.reindex(lag_1_year_dt)["value"].values
    predict_datetimes_df["lag_1_days"] = dalidata_df.reindex(lag_1_day_dt)["value"].values
    predict_datetimes_df["lag_2_days"] = dalidata_df.reindex(lag_2_day_dt)["value"].values
    predict_datetimes_df["lag_3_days"] = dalidata_df.reindex(lag_3_day_dt)["value"].values
    predict_datetimes_df["lag_4_days"] = dalidata_df.reindex(lag_4_day_dt)["value"].values
    predict_datetimes_df["lag_5_days"] = dalidata_df.reindex(lag_5_day_dt)["value"].values
    predict_datetimes_df["lag_6_days"] = dalidata_df.reindex(lag_6_day_dt)["value"].values
    predict_datetimes_df["lag_7_days"] = dalidata_df.reindex(lag_7_day_dt)["value"].values

    return predict_datetimes_df

def _get_mock_standard_profile_features(start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    predict_datetimes_df = pd.DataFrame({
        "datetime": pd.date_range(
            start=start_date_inclusive,
            end=end_date_inclusive,
            freq="15min",
            tz=ZoneInfo("Europe/Amsterdam"),
            inclusive="left",
        )
    })

    predict_datetimes_df["scaled_profile"] = 0

    return predict_datetimes_df

async def get_features_between_dates(query_api: QueryApiAsync, start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    """Get features for the prediction model between the start date (inclusive) and end date (inclusive).

    Args:
        query_api (QueryApi): The read-only connection to the influx database.
        start_date_inclusive (datetime): The start date (inclusive)
        start_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: A dataframe containing all the features for the given time range.
    """
    time_features = _get_time_features_for_dates(start_date_inclusive, end_date_inclusive)
    lag_features = await _get_lag_features_for_dates(query_api, start_date_inclusive, end_date_inclusive)
    weather_features = _get_weather_features_for_dates(start_date_inclusive, end_date_inclusive)
    # standard_profiles = await retrieve_standard_profiles_between_dates(query_api, start_date_inclusive, end_date_inclusive)
    standard_profiles = _get_mock_standard_profile_features(start_date_inclusive, end_date_inclusive)

    return pd.concat([time_features, lag_features, weather_features, standard_profiles], axis=1)
