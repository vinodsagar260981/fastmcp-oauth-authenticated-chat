import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from fastmcp import Client
from fastmcp.client.auth import OAuth


app = FastAPI()

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# PRODUCTION CONFIG
# ============================================================

MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
    "https://fastmcp-mcp-server-n8r6.onrender.com",
).rstrip("/")

if not MCP_SERVER_URL.endswith("/mcp"):
    MCP_SERVER_URL += "/mcp"


CLIENT_ID = os.getenv(
    "MCP_CLIENT_ID",
    "demo-mcp-client",
)

CLIENT_SECRET = os.getenv(
    "MCP_CLIENT_SECRET",
    "demo-mcp-secret",
)


# ============================================================
# MCP CLIENT
# ============================================================

def create_mcp_client():

    oauth = OAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["products"],
    )

    client = Client(
        MCP_SERVER_URL,
        auth=oauth,
    )

    return oauth, client


oauth, mcp_client = create_mcp_client()


# ============================================================
# CHAT PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "request": request,
        },
    )


# ============================================================
# CONNECT
# ============================================================

@app.get("/connect")
async def connect_mcp():

    async with mcp_client:

        result = await mcp_client.call_tool(
            "who_am_i"
        )

    return {
        "authenticated": True,
        "user": result.data,
    }


# ============================================================
# PRODUCTS
# ============================================================

@app.get("/products")
async def get_products():

    async with mcp_client:

        result = await mcp_client.call_tool(
            "get_products"
        )

    return result.data


# ============================================================
# LOGOUT
# ============================================================

@app.get("/logout")
async def logout():

    global oauth
    global mcp_client

    oauth, mcp_client = create_mcp_client()

    return {
        "success": True,
        "message": "Logged out. Authenticate again.",
    }