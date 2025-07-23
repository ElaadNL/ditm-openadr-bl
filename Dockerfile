# To enable ssh & remote debugging on app service change the base image to the one below
# FROM mcr.microsoft.com/azure-functions/python:4-python3.12-appservice
FROM mcr.microsoft.com/azure-functions/python:4-python3.12

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

# Set up environment variables for Python and Poetry:
# - PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files to disc (equivalent to python -B option)
# - PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr (equivalent to python -u option)
# - POETRY_VIRTUALENVS_IN_PROJECT: Tells Poetry to create the virtual environment in the project folder
# - POETRY_VIRTUALENVS_CREATE: Tells Poetry to create a virtual environment. This ensures that any packages inside the docker image cannot cause
#   weird behaviour in the application.
# - POETRY_CACHE_DIR: Allows deleting the cache directory after installing dependencies.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=0 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN curl -sSL https://install.python-poetry.org | python3 -
    
ENV PATH="$HOME/.local/bin:$PATH"

COPY poetry.lock pyproject.toml ./

RUN poetry install --without dev

COPY ./src /home/site/wwwroot/src

COPY ./function_app.py /home/site/wwwroot
