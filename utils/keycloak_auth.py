#!/usr/bin/env python3
"""Get an access token from Keycloak."""

import base64
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session

load_dotenv()


REALM_URL = "http://localhost:8080/realms/tectora/protocol/openid-connect"
CLIENT_ID = "langgraph-app"
REDIRECT_URI = "http://localhost:3001/callback"
LOGGED_IN_PAGE = Path(__file__).resolve().parent.parent / "site" / "logged_in_self-contained.html"

# 1. Initialize session with PKCE enabled in the constructor
oauth = OAuth2Session(
    client_id=CLIENT_ID,
    redirect_uri=REDIRECT_URI,
    scope=["openid", "profile", "email"],
    pkce="S256",
)

# authorization_url takes only the endpoint and optional state
auth_url, state = oauth.authorization_url(f"{REALM_URL}/auth")

auth_code_url = None


# 2. Local Callback Server
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code_url
        auth_code_url = f"http://localhost:3001{self.path}"
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(LOGGED_IN_PAGE.read_bytes())


def get_access_token() -> dict | None:
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 3001), CallbackHandler)
    while not auth_code_url:
        server.handle_request()
    server.server_close()

    # 3. Exchange code for tokens (the session automatically passes code_verifier)
    token = oauth.fetch_token(
        f"{REALM_URL}/token",
        authorization_response=auth_code_url,
        include_client_id=True,
    )

    access_token = token["access_token"]
    token_parts = access_token.split(".")

    if len(token_parts) == 3:
        payload = token_parts[1] + "=" * (-len(token_parts[1]) % 4)
        decoded_access_token = json.loads(base64.urlsafe_b64decode(payload))
        return decoded_access_token
    else:
        return None
