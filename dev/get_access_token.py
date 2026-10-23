#!/usr/bin/env python3
"""Get an access token from Keycloak."""

import base64
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session

load_dotenv()


REALM_URL = "http://localhost:8080/realms/tectora/protocol/openid-connect"
CLIENT_ID = "langgraph-app"
REDIRECT_URI = "http://localhost:3000/callback"

# 1. Initialize session with PKCE enabled in the constructor
oauth = OAuth2Session(
    client_id=CLIENT_ID,
    redirect_uri=REDIRECT_URI,
    scope=["openid", "profile", "email"],
    pkce="S256",  # <--- MUST BE HERE
)

# authorization_url takes only the endpoint and optional state
auth_url, state = oauth.authorization_url(f"{REALM_URL}/auth")

auth_code_url = None


# 2. Local Callback Server
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code_url
        auth_code_url = f"http://localhost:3000{self.path}"
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorization successful. You can close this window.</h1>")


print("Opening browser for authentication...")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 3000), CallbackHandler)
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
    print("\nSuccessfully retrieved Access Token claims:")
    print(json.dumps(decoded_access_token, indent=2, sort_keys=True))
else:
    print(f"\nSuccessfully retrieved Access Token:\n{access_token[:60]}...\n")
