from pathlib import Path
from decouple import config

# The base URL of the VTN.
VTN_BASE_URL = config("VTN_BASE_URL")

# The program ID of the OpenADR3 program to write the capacity limitation events to.
# This program ID must exist in the VTN before hand.
PROGRAM_ID = config("PROGRAM_ID", cast=int)

# The maximum capacity of the grid asset. This is used to calculate the flex capacity required based on the predicted load.
MAX_CAPACITY = config("MAX_CAPACITY", cast=float)

# INFLUXDB parameters
INFLUXDB_ORG = config("INFLUXDB_ORG")
INFLUXDB_BUCKET = config("INFLUXDB_BUCKET")

# INFLUXDB parameters (secrets)
INFLUXDB_TOKEN_FILE = config("INFLUXDB_TOKEN_FILE")
INFLUXDB_URL_FILE = config("INFLUXDB_URL_FILE")

with Path.open(INFLUXDB_TOKEN_FILE) as f:
    INFLUXDB_TOKEN = f.read().strip()

with Path.open(INFLUXDB_URL_FILE) as f:
    INFLUXDB_URL = f.read().strip()
