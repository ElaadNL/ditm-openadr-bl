
from datetime import datetime

import pandas as pd

from src.config import INFLUXDB_ORG, DALIDATA_BUCKET_NAME
from influxdb_client.client.query_api_async import QueryApiAsync

async def retrieve_dali_data_between(query_api: QueryApiAsync, start_date_inclusive: datetime, end_date_inclusive: datetime) -> pd.DataFrame:
    """Retrieve standard profiles from InfluxDB between the given dates.
    
    Args:
        start_date_inclusive (datetime): The start date (inclusive)
        end_date_inclusive (datetime): The end date (inclusive)

    Returns:
        pd.DataFrame: The dataframe containing standard profiles for the date range.
    """
    start_date_str = start_date_inclusive.strftime(format="%Y-%m-%dT%H:%M:%SZ")
    end_date_str = end_date_inclusive.strftime(format="%Y-%m-%dT%H:%M:%SZ")

    query = f"""from(bucket: "{DALIDATA_BUCKET_NAME}")
            |> range(start: {start_date_str}, stop: {end_date_str})
            |> filter(fn: (r) => r["_measurement"] == "kinesis_data")
            |> filter(fn: (r) => r["_field"] == "value")
            |> filter(fn: (r) => r["boxid"] == "CVD.091030-1")
            |> filter(fn: (r) => r["description"] == "Trafometing vermogen som 3 fases - gem. 15 min." or r["description"] == "Trafometing_vermogen_som_3_fases_-_gem._15_min.")
            |> group(columns: [])
            |> sort(columns: ["_time"])
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """  # noqa: E501

    df = await query_api.query_data_frame(query=query, org=INFLUXDB_ORG)

    return df.rename(columns={"_time": "datetime"})