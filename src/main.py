import azure.functions as func

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from openadr3_client.bl.http_factory import BusinessLogicHttpClientFactory
from openadr3_client.bl._client import BusinessLogicClient
from openadr3_client.models.event.event import NewEvent
from openadr3_client._vtn.interfaces.filters import TargetFilter

from src.application.generate_events import get_capacity_limitation_event
from src.infrastructure.influxdb._client import create_db_client
from src.infrastructure.prediction_actions_impl import PredictionActionsInfluxDB
from src.logger import logger
from src.config import (
    PROGRAM_ID,
    VEN_NAMES,
    VTN_BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_TOKEN_ENDPOINT,
    OAUTH_SCOPES,
)

bp = func.Blueprint()


def _initialize_bl_client() -> BusinessLogicClient:
    """Initialize the BL client with the base URL of the VTN.

    Returns:
        BusinessLogicClient: The BL client.
    """
    bl_client = BusinessLogicHttpClientFactory.create_http_bl_client(
        vtn_base_url=VTN_BASE_URL,
        client_id=OAUTH_CLIENT_ID,
        client_secret=OAUTH_CLIENT_SECRET,
        token_url=OAUTH_TOKEN_ENDPOINT,
        scopes=OAUTH_SCOPES.split(","),
    )
    return bl_client


async def _generate_events() -> NewEvent | None:
    """Generate events for tomorrow to be published to the VTN.

    Returns:
        list[Event]: The list of events.
    """
    current_time_ams = datetime.now(ZoneInfo("Europe/Amsterdam"))

    # Start time is 12:00 today.
    start_time = current_time_ams.replace(hour=12, minute=0, second=0, microsecond=0)
    # End time is 12:00 24 hours in the future
    end_time = start_time + timedelta(days=1)

    actions = PredictionActionsInfluxDB(client=create_db_client())

    return await get_capacity_limitation_event(
        actions, from_date=start_time, to_date=end_time
    )


async def _clean_up_old_events(bl_client: BusinessLogicClient) -> None:
    """Clean up old events from the VTN targeting the VEN of this BL that are going to be replaced by the new events."""
    # Get all events from the VTN
    events = bl_client.events.get_events(
        program_id=PROGRAM_ID,
        pagination=None,
        target=TargetFilter(target_type="VEN_NAME", target_values=VEN_NAMES.split(",")),
    )

    for event in events:
        bl_client.events.delete_event_by_id(event_id=event.id)
        logger.info("Deleted old event with id replaced by the BL: %s", event.id)


async def main() -> None:
    try:
        logger.info("Triggering BL function at %s", datetime.now(tz=UTC))
        event = await _generate_events()

        if not event:
            logger.warning(
                "No capacity limitation event could be constructed, skipping..."
            )
            return None

        bl_client = _initialize_bl_client()

        try:
            # Clean up the old events in the VTN that are going to be replaced by the new events
            await _clean_up_old_events(bl_client=bl_client)
            # Create the new event in the VTN.
            created_event = bl_client.events.create_event(new_event=event)
            logger.info("Created event with id: %s in VTN", created_event.id)
        except Exception as exc:
            logger.warning(
                "Exception occurred during event creation in the VTN", exc_info=exc
            )
    except Exception as exc:
        logger.warning("Exception occurred during function execution", exc_info=exc)

    logger.info("Python timer trigger function executed.")


# if __name__ == "__main__":
#     asyncio.run(main())


@bp.schedule(
    schedule="0 55 7 * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
async def generate_events_for_tomorrow(myTimer: func.TimerRequest) -> None:
    await main()
