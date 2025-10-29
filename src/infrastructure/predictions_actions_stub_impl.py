"""Module which implements prediction actions."""

import random

from datetime import datetime, timedelta

from src.application.generate_events import PredictionActionsBase

from src.models.predicted_load import PredictedGridAssetLoad


class PredictionActionsStub(PredictionActionsBase[None, None]):
    """Stub implementation of the prediction actions, generates predicted grid asset loads when called.

    Args:
        PredictionActionsBase: Base class for actions
    """

    def __init__(self) -> None:
        """Initializes the PredictionActionsStub."""
        super().__init__()

    def get_query_api(self) -> None:
        """Retrieve a read-only connection for the database."""
        return None

    def get_write_api(self) -> None:
        """Retrieve a write connection for the database."""
        return None

    async def get_predicted_grid_asset_load(
        self, query_api: None, from_date: datetime, to_date: datetime
    ) -> list[PredictedGridAssetLoad]:
        """Generate predicted grid asset loads within this stub between the given times.

        Args:
            query_api (None): The read-only connection.
            from_date (datetime): The start time (inclusive) from which to generate predicted grid asset loads.
            to_date (datetime): The end time (exclusive) from which to generate predicted grid asset loads.

        Returns:
            list[TransformerLoad]: The list of predicted transformer loads.
        """
        predicted_grid_asset_loads = []

        # Step through the time range in 15 minute steps.
        step = timedelta(minutes=15)

        current_time = from_date

        while current_time < to_date:
            # Generate a predicted grid asset load for the current time.
            predicted_grid_asset_load = PredictedGridAssetLoad(
                time=current_time,
                load=random.randint(20, 150),
            )
            predicted_grid_asset_loads.append(predicted_grid_asset_load)
            current_time += step

        return predicted_grid_asset_loads

    async def audit_predicted_grid_asset_loads(
        self,
        write_api: None,
        predicted_grid_asset_loads: list[PredictedGridAssetLoad],
    ) -> None:
        """Stub implementation of auditing predicted grid asset loads.

        Args:
            write_api (None): The write connection.
            predicted_grid_asset_loads (list[PredictedGridAssetLoad]): The list of predicted grid asset loads to audit.
        """
        # In this stub implementation, we do nothing.
        pass
