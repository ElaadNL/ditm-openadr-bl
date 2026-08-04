"""Construction of, and shared queries against, the business logic client."""

from collections.abc import Sequence

from openadr3_client._vtn.interfaces.filters import TargetFilter
from openadr3_client.bl._client import BusinessLogicClient
from openadr3_client.bl.http_factory import BusinessLogicHttpClientFactory
from openadr3_client.models.event.event import ExistingEvent

from src.config import (
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_SCOPES,
    OAUTH_TOKEN_ENDPOINT,
    VTN_BASE_URL,
)


def create_bl_client() -> BusinessLogicClient:
    """Initialize the BL client with the base URL of the VTN.

    Returns:
        BusinessLogicClient: The BL client.
    """
    return BusinessLogicHttpClientFactory.create_http_bl_client(
        vtn_base_url=VTN_BASE_URL,
        client_id=OAUTH_CLIENT_ID,
        client_secret=OAUTH_CLIENT_SECRET,
        token_url=OAUTH_TOKEN_ENDPOINT,
        scopes=OAUTH_SCOPES.split(","),
    )


def fetch_events_for_vens(
    bl_client: BusinessLogicClient, program_id: str, ven_names: Sequence[str]
) -> tuple[ExistingEvent, ...]:
    """Retrieve the events of a program that target the given VENs.

    Args:
        bl_client (BusinessLogicClient): The BL client to query with.
        program_id (str): The program to retrieve events of.
        ven_names (Sequence[str]): The VEN names the events target.

    Returns:
        tuple[ExistingEvent, ...]: The events stored in the VTN.
    """
    return bl_client.events.get_events(
        program_id=program_id,
        pagination=None,
        target=TargetFilter(target_type="VEN_NAME", target_values=list(ven_names)),
    )
