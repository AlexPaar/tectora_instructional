#!/usr/bin/env python3
import webbrowser

from rich.console import Console

console = Console()

REALM_URL = "http://localhost:8080/realms/tectora/protocol/openid-connect"
CLIENT_ID = "langgraph-app"
POST_LOGOUT_REDIRECT = "http://tectora.org/logged_out.html"

logout_url = f"{REALM_URL}/logout?client_id={CLIENT_ID}&post_logout_redirect_uri={POST_LOGOUT_REDIRECT}"

console.print("[dim]Opening Keycloak logout page...[/dim]")

webbrowser.open(logout_url)
