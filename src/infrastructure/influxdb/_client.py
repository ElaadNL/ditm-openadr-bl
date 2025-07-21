
"""Module containing logic for managing database sessions."""

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from src.config import INFLUXDB_ORG, INFLUXDB_TOKEN, INFLUXDB_URL

def create_db_client() -> InfluxDBClientAsync:
    """Creates an InfluxDB client with the appropriate configuration.

    Returns:
        InfluxDBClient: An initialized InfluxDB client.
    """
    return InfluxDBClientAsync(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
