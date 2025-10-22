"""Module which implements prediction actions."""

from datetime import datetime

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.query_api_async import QueryApiAsync

from src.application.generate_events import PredictionActionsBase
from src.infrastructure.azureml.feature_generation import get_features_between_dates
from src.infrastructure.azureml.predictions import get_predictions_for_features
from src.models.predicted_load import PredictedGridAssetLoad


class PredictionActionsInfluxDB(PredictionActionsBase[QueryApiAsync]):
    """Implementation of the prediction actions using influxDB.

    This is implemented seperately in the infrastructure layer to promote decoupling of business
    logic for infrastructure concerns and changes.

    Args:
        PredictionActionsBase: Base class for actions
    """

    def __init__(self, client: InfluxDBClientAsync) -> None:
        """Initializes the PredictionActionsInfluxDB.

        Args:
            client (InfluxDBClient): The influx DB client to use in these actions.
        """
        self.client = client
        super().__init__()

    def get_query_api(self) -> QueryApiAsync:
        """Retrieve a read-only connection for the database."""
        return self.client.query_api()

    async def get_predicted_grid_asset_load(
        self, query_api: QueryApiAsync, from_date: datetime, to_date: datetime
    ) -> list[PredictedGridAssetLoad]:
        """Retrieve predicted trafo load from the database between the given times.

        Args:
            query_api (QueryApi): The read-only connection to the database.
            from_date (datetime): The start time (inclusive) from which to fetch predicted trafo load.
            to_date (datetime): The end time (exclusive) from which to fetch predicted trafo load.

        Returns:
            list[TransformerLoad]: The list of predicted transformer loads.
        """
        features_for_time_range = await get_features_between_dates(
            query_api=query_api,
            start_date_inclusive=from_date,
            end_date_inclusive=to_date,
        )
        return get_predictions_for_features(features=features_for_time_range)
