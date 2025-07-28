import azure.functions as func

from datetime import UTC, datetime, timedelta, timezone
from openadr3_client.bl.http_factory import BusinessLogicHttpClientFactory
from openadr3_client.bl._client import BusinessLogicClient
from openadr3_client.models.event.event import NewEvent

from src.application.generate_events import get_capacity_limitation_event
from src.infrastructure.predictions_actions_stub_impl import PredictionActionsStub
from src.logger import logger
from src.config import VTN_BASE_URL

bp = func.Blueprint()


def _initialize_bl_client() -> BusinessLogicClient:
    """Initialize the BL client with the base URL of the VTN.

    Returns:
        BusinessLogicClient: The BL client.
    """
    bl_client = BusinessLogicHttpClientFactory.create_http_bl_client(
        vtn_base_url=VTN_BASE_URL
    )
    return bl_client


async def _generate_events() -> NewEvent | None:
    """Generate events for tomorrow to be published to the VTN.

    Returns:
        list[Event]: The list of events.
    """
    # Start time is 00:00 tomorrow.
    start_time = (datetime.now(tz=UTC) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # End time is 00:00 the day after tomorrow.
    end_time = start_time + timedelta(days=1)

    # actions = PredictionActionsInfluxDB(client=create_db_client())
    actions = PredictionActionsStub()

    return await get_capacity_limitation_event(
        actions, from_date=start_time, to_date=end_time
    )


@bp.schedule(
    schedule="* 50 21 * * *",
    arg_name="myTimer",
    run_on_startup=True,
    use_monitor=False,
)
async def timer_trigger(myTimer: func.TimerRequest) -> None:
    try:
        logger.info("Triggering BL function at %s", datetime.now(tz=timezone.utc))
        event = await _generate_events()

        if not event:
            logger.warning(
                "No capacity limitation event could be constructed, skipping..."
            )
            return None

        bl_client = _initialize_bl_client()

        try:
            created_event = bl_client.events.create_event(new_event=event)
            logger.info("Created event with id: %s in VTN", created_event.id)
        except Exception as exc:
            logger.warning(
                "Exception occurred during event creation in the VTN", exc_info=exc
            )
    except Exception as exc:
        logger.warning("Exception occurred during function execution", exc_info=exc)

    logger.info("Python timer trigger function executed.")
