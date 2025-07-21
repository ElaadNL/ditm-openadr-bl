[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

# Reference OpenADR GAC BL Implementation

This repository contains a barebones reference implementation which can be used as a reference for a GAC compliant BL implementation.

## Configuration

For the openadr3-client dependency, you need to configure the following environment variables:

```python
OAUTH_TOKEN_ENDPOINT # The oauth token endpoint to provision access tokens from
OAUTH_CLIENT_ID      # The client ID for OAuth client credential authentication
OAUTH_CLIENT_SECRET  # The client secret for OAuth client credential authentication
OAUTH_SCOPES         # Comma-delimited list of OAuth scope to request (optional)
```
