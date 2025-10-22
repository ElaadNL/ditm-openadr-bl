"""Module which contains functions to retrieve predicted trafo load from an external database."""

from influxdb_client.client.write_api_async import WriteApiAsync
import pandas as pd

from src.config import PREDICTED_TRAFO_LOAD_BUCKET
from src.models.predicted_load import PredictedGridAssetLoad


async def store_predictions_for_audit(
    write_api: WriteApiAsync, predicted_loads: list[PredictedGridAssetLoad]
) -> None:
    """Write predicted transformer loads to the database for auditing purposes.

    Args:
        write_api (WriteApi): The write connection to the database.
        predicted_loads (list[PredictedGridAssetLoad]): List of predicted transformer loads to write to the database.
    """
    df = pd.DataFrame(
        [(tl.time, tl.load) for tl in predicted_loads], columns=["datetime", "WAARDE"]
    )

    await write_api.write(
        bucket=PREDICTED_TRAFO_LOAD_BUCKET,
        record=df,
        data_frame_measurement_name="predictions",
        data_frame_timestamp_column="datetime",
    )
