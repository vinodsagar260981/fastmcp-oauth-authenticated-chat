from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from fastmcp import Client
from fastmcp.client.auth import OAuth


app = FastAPI()
templates = Jinja2Templates(directory="templates")

# The MCP server is exposed from Docker to the Windows host.
# This URL MUST match mcp_server.py base_url.
MCP_SERVER_URL = "http://mcp.localhost:8001/mcp"

CLIENT_ID = "demo-mcp-client"
CLIENT_SECRET = "demo-mcp-secret"


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


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"request": request},
    )


@app.get("/connect")
async def connect_mcp():
    async with mcp_client:
        result = await mcp_client.call_tool("who_am_i")

    return {
        "authenticated": True,
        "user": result.data,
    }


@app.get("/products")
async def get_products():
    async with mcp_client:
        result = await mcp_client.call_tool("get_products")

    return result.data


@app.get("/logout")
async def logout():
    global oauth, mcp_client

    oauth, mcp_client = create_mcp_client()

    return {
        "success": True,
        "message": "Logged out. Authenticate again.",
    }
