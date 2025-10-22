from datetime import datetime

import pandas as pd
from src.config import INFLUXDB_ORG, STANDARD_PROFILES_BUCKET_NAME
from influxdb_client.client.query_api_async import QueryApiAsync


async def retrieve_standard_profiles_between_dates(
    query_api: QueryApiAsync,
    start_date_inclusive: datetime,
    end_date_inclusive: datetime,
) -> pd.DataFrame:
    """Retrieve standard profiles from InfluxDB between the given dates.

    Args:
        start_date_inclusive (datetime): The start date (inclusive)
        end_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: The dataframe containing standard profiles for the date range.
    """
    start_date_str = start_date_inclusive.strftime(format="%Y-%m-%dT%H:%M:%SZ")
    end_date_str = end_date_inclusive.strftime(format="%Y-%m-%dT%H:%M:%SZ")

    query = f"""
        from(bucket: "{STANDARD_PROFILES_BUCKET_NAME}")
            |> range(start: {start_date_str}, stop: {end_date_str})
            |> filter(fn: (r) => r["_measurement"] == "standard_profile")
            |> filter(fn: (r) => "profile")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """

    response = await query_api.query_data_frame(query=query, org=INFLUXDB_ORG)
    return response.rename(columns={"_time": "datumtijd"})
