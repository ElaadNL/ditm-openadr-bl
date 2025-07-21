from abc import ABC, abstractmethod
from datetime import datetime
from openadr3_client.models.event.event import Event, NewEvent
from openadr3_client.models.common.interval import Interval
from openadr3_client.models.common.interval_period import IntervalPeriod
from openadr3_client.models.event.event_payload import (
    EventPayload,
    EventPayloadType,
    EventPayloadDescriptor,
)
from openadr3_client.models.common.unit import Unit

from src.logger import logger
from src.config import MAX_CAPACITY, PROGRAM_ID
from src.models.predicted_load import PredictedGridAssetLoad


class PredictionActionsBase[ReadOnlySession](ABC):
    """Abstract class which contains methods used by this workflow.

    These methods are implemented on a higher level and provided to the functions of this
    workflow.
    """

    @abstractmethod
    def get_query_api(self) -> ReadOnlySession:
        """Retrieve a read-only session to the database."""

    @abstractmethod
    async def get_predicted_grid_asset_load(
        self, query_api: ReadOnlySession, from_date: datetime, to_date: datetime
    ) -> list[PredictedGridAssetLoad]:
        """Retrieve predicted grid asset load between the given times.

        Args:
            query_api (ReadOnlySession): The read-only connection to the database.
            from_date (datetime): The start time (inclusive) from which to fetch predicted grid asset load.
            to_date (datetime): The end time (exclusive) from which to fetch predicted grid asset load.

        Returns:
            list[PredictedGridAssetLoad]: The list of predicted grid asset loads.
        """


def _generate_capacity_limitation_intervals(
    interval_id: int,
    predicted_grid_asset_loads: PredictedGridAssetLoad,
    max_capacity: float,
) -> Interval[EventPayload]:
    """Generate a capacity limitation interval for the given predicted grid asset load.

    Args:
        interval_id (int): The interval ID.
        predicted_grid_asset_loads (PredictedGridAssetLoad): The predicted grid asset loads.
        max_capacity (float): The maximum capacity allowed for the grid asset.

    Returns:
        Interval[EventPayload]: The capacity limitation interval.
    """
    return Interval(
        id=interval_id,
        interval_period=IntervalPeriod(
            start=predicted_grid_asset_loads.time,
            duration=predicted_grid_asset_loads.duration,
        ),
        payloads=(
            EventPayload(
                type=EventPayloadType.IMPORT_CAPACITY_LIMIT,
                values=(
                    predicted_grid_asset_loads.flex_capacity_required(max_capacity),
                ),
            ),
        ),
    )


def _generate_capacity_limitation_event(
    predicted_grid_asset_loads: list[PredictedGridAssetLoad], max_capacity: float
) -> Event:
    """Generate a capacity limitation event for the given predicted grid asset load.

    Args:
        predicted_grid_asset_loads (list[PredictedGridAssetLoad]): The predicted grid asset loads.
        max_capacity (float): The maximum capacity allowed for the grid asset.

    Returns:
        Event: The capacity limitation event.
    """
    intervals = [
        _generate_capacity_limitation_intervals(
            interval_id, predicted_grid_asset_load, max_capacity
        )
        for interval_id, predicted_grid_asset_load in enumerate(
            predicted_grid_asset_loads
        )
    ]

    return NewEvent(
        programID=PROGRAM_ID,
        event_name=f"bl-generated-event-{datetime.now().strftime('%d-%m-%Y')}",
        payload_descriptor=(
            EventPayloadDescriptor(
                payload_type=EventPayloadType.IMPORT_CAPACITY_LIMIT, units=Unit.KW
            ),
        ),
        intervals=tuple(intervals),
    )


async def get_capacity_limitation_event(
    actions: PredictionActionsBase, from_date: datetime, to_date: datetime
) -> Event | None:
    """Retrieve OpenADR3 capacity limitation events between the given times.

    Args:
        actions (PredictionActionsBase): The actions to use.
        from_date (datetime): The start time (inclusive) from which to fetch OpenADR events.
        to_date (datetime): The end time (exclusive) from which to fetch OpenADR events.

    Returns:
        Event | None: The OpenADR3 capacity limitation event. None if no data to base the event on could be retrieved.
    """
    query_api = await actions.get_query_api()
    predicted_grid_asset_loads = await actions.get_predicted_grid_asset_load(
        query_api, from_date, to_date
    )

    # If no predictions could be retrieved, return None.
    if not predicted_grid_asset_loads:
        logger.warning(
            "get_capacity_limitation_event: No predictions could be retrieved, returning None."
        )
        return None

    return _generate_capacity_limitation_event(predicted_grid_asset_loads, MAX_CAPACITY)
