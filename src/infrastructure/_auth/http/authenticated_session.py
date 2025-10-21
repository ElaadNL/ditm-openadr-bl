"""Implementation of a HTTP session which has an associated access token that is send to every request."""

from typing import Optional
from requests import PreparedRequest, Session
from requests.auth import AuthBase

from src.config import DITM_MODEL_API_CLIENT_ID, DITM_MODEL_API_CLIENT_SECRET, DITM_MODEL_API_TOKEN_URL
from src.infrastructure._auth.token_manager import OAuthTokenManager, OAuthTokenManagerConfig


class _BearerAuth(AuthBase):
    """AuthBase implementation that includes a bearer token in all requests."""

    def __init__(self, token_manager: OAuthTokenManager) -> None:
        self._token_manager = token_manager

    def __call__(self, r: PreparedRequest) -> PreparedRequest:
        """
        Perform the request.

        Adds the bearer token to the 'Authorization' request header before the call is made.
        If the 'Authorization' was already present, it is replaced.
        """
        # The token manager handles caching internally, so we can safely invoke this
        # for each request.
        r.headers["Authorization"] = "Bearer " + self._token_manager.get_access_token()
        return r


class _BearerAuthenticatedSession(Session):
    """Session that includes a bearer token in all requests made through it."""

    def __init__(self, token_manager: Optional[OAuthTokenManager] = None, scopes: Optional[list[str]] = None) -> None:
        super().__init__()
        if not token_manager:
            token_manager = OAuthTokenManager(
                    OAuthTokenManagerConfig(
                        client_id=DITM_MODEL_API_CLIENT_ID,
                        client_secret=DITM_MODEL_API_CLIENT_SECRET,
                        token_url=DITM_MODEL_API_TOKEN_URL,
                        scopes=scopes,
                        audience=None
                    )
                )
        self.auth = _BearerAuth(token_manager)