from openadr3_client.bl.http_factory import BusinessLogicHttpClientFactory
from openadr3_client.bl._client import BusinessLogicClient

from src.config import VTN_BASE_URL


def initialize_bl_client() -> BusinessLogicClient:
    """Initialize the BL client with the base URL of the VTN.

    Returns:
        BusinessLogicClient: The BL client.
    """
    bl_client = BusinessLogicHttpClientFactory.create_http_bl_client(
        vtn_base_url=VTN_BASE_URL
    )
    return bl_client


def generate_events() -> None:
    """Generate events for the VTN.

    Returns:
        list[Event]: The list of events.

    Raises:
        Exception: If the VTN is not reachable.
    """
    _ = initialize_bl_client()


if __name__ == "__main__":
    generate_events()
