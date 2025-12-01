from decouple import config

# The base URL of the VTN.
VTN_BASE_URL = config("VTN_BASE_URL")

# The name of the VEN to target the capacity limitation events generated from this BL to.
VEN_NAMES = config("VEN_NAMES", cast=str)
MOCK_EAN_NUMBER = config("MOCK_EAN_NUMBER", cast=str)

# The program ID of the OpenADR3 program to write the capacity limitation events to.
# This program ID must exist in the VTN before hand.
PROGRAM_ID = config("PROGRAM_ID", cast=str)

# The maximum capacity of the grid asset. This is used to calculate the flex capacity required based on the predicted load.
MAX_CAPACITY = config("MAX_CAPACITY", cast=float)

# INFLUXDB parameters
INFLUXDB_ORG = config("INFLUXDB_ORG")
INFLUXDB_BUCKET = config("INFLUXDB_BUCKET")

# INFLUXDB parameters (secrets)
INFLUXDB_TOKEN = config("INFLUXDB_TOKEN")
INFLUXDB_URL = config("INFLUXDB_URL")

PREDICTED_TRAFO_LOAD_BUCKET = config(
    "PREDICTED_TRAFO_LOAD_BUCKET", default="ditm_model_output"
)
STANDARD_PROFILES_BUCKET_NAME = config(
    "STANDARD_PROFILES_BUCKET_NAME", default="ditm_standard_profiles"
)
DALIDATA_BUCKET_NAME = config(
    "DALIDATA_BUCKET_NAME", default="ditm-dali-data-processed"
)

# External services URLs
WEATHER_FORECAST_API_URL = config("WEATHER_FORECAST_API_URL")

# Authentication to Azure ML managed endpoint for prediction model
DITM_MODEL_API_URL = config("DITM_MODEL_API_URL")
DITM_MODEL_API_CLIENT_ID = config("DITM_MODEL_API_CLIENT_ID")
DITM_MODEL_API_CLIENT_SECRET = config("DITM_MODEL_API_CLIENT_SECRET")
DITM_MODEL_API_TOKEN_URL = config("DITM_MODEL_API_TOKEN_URL")

OAUTH_CLIENT_ID = config("OAUTH_CLIENT_ID")
OAUTH_CLIENT_SECRET = config("OAUTH_CLIENT_SECRET")
OAUTH_TOKEN_ENDPOINT = config("OAUTH_TOKEN_ENDPOINT")
OAUTH_SCOPES = config("OAUTH_SCOPES")
