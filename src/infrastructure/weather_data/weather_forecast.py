"""Module for retrieving and processing weather forecasting data.

This module provides:
- _call_weather_forecast_api: Function that calls the Open-Meteo API to fetch hourly forecast data.
- _interpolate_hourly_data_to_quarterly: Function that interpolates the hourly values data to quarterly values.
- etl_weather_forecast_data: Function that extracts, transforms and loads weather forecast data.
"""

from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests
from pandas import concat

from src.config import WEATHER_FORECAST_API_URL


class WeatherForecastData:
    """Class for weather forecast data from Open Meteo."""

    def __init__(self) -> None:
        """Initializes the weather forecast data class."""
        self.om_weather_forecast_vars = {
            "temperature_2m": "temperature",
            "shortwave_radiation": "irradiation",
            "sunshine_duration": "irradiation_duration",
            "cloud_cover": "cloud_coverage",
            "rain": "rain",
            "relative_humidity_2m": "humidity",
            "snowfall": "snow",
        }

    def _call_weather_forecast_api(self, forecast_date: date) -> dict:
        """Calls the Open-Meteo API to retrieve hourly weather forecast data.

        Args:
            forecast_date: Date for which to fetch weather forecast.

        Returns:
            JSON response containing weather forecast data.
        """
        start_time = forecast_date.strftime(format="%Y-%m-%dT00:00")
        end_time = forecast_date.strftime(format="%Y-%m-%dT23:45")

        params: dict[str, Any] = {
            "latitude": 52.7481819,
            "longitude": 6.5663292,
            "hourly": list(self.om_weather_forecast_vars.keys()),
            "models": "knmi_seamless",
            "start_hour": start_time,
            "end_hour": end_time,
        }

        response = requests.get(url=WEATHER_FORECAST_API_URL, params=params, timeout=10)
        return response.json()

    def _interpolate_hourly_data_to_quarterly(self, weather_var: str) -> None:
        """."""
        match weather_var:
            case "temperature":
                self.weather_data[weather_var] = self.weather_data[weather_var].interpolate(
                    method="linear", limit=3, limit_direction="forward"
                )

            case "irradiation" | "irradiation_duration" | "rain" | "humidity":
                self.weather_data[weather_var] = (
                    self.weather_data[weather_var]
                    .interpolate(method="linear", limit=3, limit_direction="forward")
                    .clip(lower=0)
                )

            case "cloud_coverage" | "snow":
                self.weather_data[weather_var] = self.weather_data[weather_var].ffill()

    def etl_weather_forecast_data(self, forecast_date: date) -> pd.DataFrame:
        """Extracts, transforms, and loads weather forecast data.

        - Extracts and transforms the forecast data.
        - Reindexes data to 15-minute intervals to maintain consitency.
        - Interpolates temperature and irradiation to 15-minute intervals.

        Args:
            forecast_date: Date for which to fetch and process weather forecast.

        Returns:
            Processed DataFrame with interpolated weather data at 15-minute intervals.
        """
        forecast_dict = self._call_weather_forecast_api(forecast_date=forecast_date)

        weather_data = pd.DataFrame({"datetime": forecast_dict["hourly"]["time"][:-1]})
        weather_data = concat(
            objs=[
                weather_data,
                pd.DataFrame(
                    {value: forecast_dict["hourly"][key] for key, value in self.om_weather_forecast_vars.items()}
                ),
            ],
            axis=1,
        )
        weather_data["datetime"] = pd.to_datetime(arg=weather_data["datetime"], utc=True)
        weather_data["snow"] = weather_data["snow"].apply(func=lambda x: (x > 0) * 1)
        weather_data["cloud_coverage"] = weather_data["cloud_coverage"].apply(func=lambda x: int(x / 100 * 9))
        weather_data["irradiation_duration"] = weather_data["irradiation_duration"].apply(
            func=lambda x: x / 3600 if x != -1 else x
        )  # Irradiation duration is in 0.1 hours, converted to seconds
        weather_data["irradiation"] = weather_data["irradiation"].apply(
            func=lambda x: x * 0.36 if x != -1 else x
        )  # Irradiation duration is in 0.1 hours, converted to seconds

        # Generate 15-minute intervals over the date range
        full_date_range = pd.date_range(
            start=weather_data["datetime"].iloc[0].tz_localize(None),
            end=weather_data["datetime"].iloc[-1].tz_localize(None).date() + timedelta(days=1),
            freq="15min",
            tz="UTC",
        )

        # Reindex and interpolate missing values
        self.weather_data = (
            weather_data.set_index("datetime")
            .reindex(full_date_range)
            .iloc[:-1]
            .reset_index()
            .rename(columns={"index": "datetime"})
        ).fillna(0)

        # Interpolate values of features to 15 min interval
        for weather_var in self.om_weather_forecast_vars.values():
            self._interpolate_hourly_data_to_quarterly(weather_var=weather_var)

        return self.weather_data
