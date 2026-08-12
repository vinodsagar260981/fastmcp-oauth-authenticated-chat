from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import AnyHttpUrl


CLIENT_ID = "demo-mcp-client"
CLIENT_SECRET = "demo-mcp-secret"

token_verifier = IntrospectionTokenVerifier(
    introspection_url="http://auth_server:8000/introspect",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    required_scopes=["products"],
)

auth = RemoteAuthProvider(
    token_verifier=token_verifier,
    authorization_servers=[
        AnyHttpUrl("http://auth.localhost:8000")
    ],
    base_url="http://mcp.localhost:8001",
)

mcp = FastMCP(
    "Product MCP Server",
    auth=auth,
)

products = [
    {"id": 1, "name": "MacBook Pro", "price": 150000},
    {"id": 2, "name": "iPhone 17", "price": 90000},
    {"id": 3, "name": "AirPods Pro", "price": 25000},
    {"id": 4, "name": "iPad Air", "price": 60000},
]


@mcp.tool
def get_products():
    token = get_access_token()

    if token is None:
        return {"error": "Not authenticated"}

    return {
        "authenticated_user": token.claims.get("sub"),
        "products": products,
    }


@mcp.tool
def who_am_i():
    token = get_access_token()

    if token is None:
        return {"error": "Not authenticated"}

    return {
        "username": token.claims.get("sub"),
        "client_id": token.client_id,
        "scopes": token.scopes,
    }


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8001,
    )
