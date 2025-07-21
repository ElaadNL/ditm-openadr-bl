"""Module containing logic to retrieve predictions from the InfluxDB database."""

from datetime import datetime
from influxdb_client.client.query_api_async import QueryApiAsync
from src.models.predicted_load import PredictedGridAssetLoad


async def retrieve_predicted_grid_asset_load(
    query_api: QueryApiAsync, bucket: str, from_date: datetime, to_date: datetime
) -> list[PredictedGridAssetLoad]:
    """Retrieve predicted grid asset load from the database between the given times.

    Args:
        query_api (QueryApiAsync): The InfluxDB query API to use.
        bucket (str): The influxDB bucket to use.
        from_date (datetime): The start date of the predictions.
        to_date (datetime): The end date of the predictions.

    Returns:
        list[PredictedGridAssetLoad]: The predicted grid asset load.
    """
    from_date_str = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date_str = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    query = f"""from(bucket: "{bucket}")
    |> range(start: {from_date_str}, stop: {to_date_str})
    |> filter(fn: (r) => r["_measurement"] == "predictions")
    |> filter(fn: (r) => r["_field"] == "value")
    |> sort(columns: ["_time"])
    """

    predicted_loads = await query_api.query(query=query)
    flattened_predicted_loads = predicted_loads.to_values(columns=["_time", "_value"])

    return [
        PredictedGridAssetLoad(time=predicted_load[0], load=predicted_load[1])  # type: ignore[arg-type]
        for predicted_load in flattened_predicted_loads
    ]
