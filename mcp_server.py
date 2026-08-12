import os

from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import AnyHttpUrl


# ============================================================
# PRODUCTION CONFIGURATION
# ============================================================

CLIENT_ID = os.getenv(
    "MCP_CLIENT_ID",
    "demo-mcp-client",
)

CLIENT_SECRET = os.getenv(
    "MCP_CLIENT_SECRET",
    "demo-mcp-secret",
)

AUTH_SERVER_URL = os.getenv(
    "AUTH_SERVER_URL",
    "https://fastmcp-oauth-authenticated-chat.onrender.com",
).rstrip("/")

MCP_SERVER_PUBLIC_URL = os.getenv(
    "MCP_SERVER_PUBLIC_URL",
    "https://fastmcp-mcp-server-n8r6.onrender.com",
).rstrip("/")


# ============================================================
# TOKEN VERIFICATION
# ============================================================

token_verifier = IntrospectionTokenVerifier(
    introspection_url=f"{AUTH_SERVER_URL}/introspect",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    required_scopes=["products"],
)


# ============================================================
# REMOTE AUTH
# ============================================================

auth = RemoteAuthProvider(
    token_verifier=token_verifier,
    authorization_servers=[
        AnyHttpUrl(AUTH_SERVER_URL)
    ],
    base_url=MCP_SERVER_PUBLIC_URL,
)


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP(
    "Product MCP Server",
    auth=auth,
)


# ============================================================
# DEMO PRODUCTS
# ============================================================

products = [
    {"id": 1, "name": "MacBook Pro", "price": 150000},
    {"id": 2, "name": "iPhone 17", "price": 90000},
    {"id": 3, "name": "AirPods Pro", "price": 25000},
    {"id": 4, "name": "iPad Air", "price": 60000},
]


# ============================================================
# TOOL: WHO AM I
# ============================================================

@mcp.tool
def who_am_i():
    token = get_access_token()

    if token is None:
        return {
            "error": "Not authenticated"
        }

    return {
        "username": token.claims.get("sub"),
        "client_id": token.client_id,
        "scopes": token.scopes,
    }


# ============================================================
# TOOL: GET PRODUCTS
# ============================================================

@mcp.tool
def get_products():
    token = get_access_token()

    if token is None:
        return {
            "error": "Not authenticated"
        }

    return {
        "authenticated_user": token.claims.get("sub"),
        "products": products,
    }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8001,
    )