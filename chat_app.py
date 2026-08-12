import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fastmcp import Client


app = FastAPI()
templates = Jinja2Templates(directory="templates")


# ==================================================
# CONFIGURATION
# ==================================================

AUTH_SERVER_URL = os.getenv(
    "AUTH_SERVER_URL",
    "http://auth.localhost:8000",
).rstrip("/")

MCP_SERVER_URL = (
    os.getenv(
        "MCP_SERVER_URL",
        "http://mcp.localhost:8001",
    ).rstrip("/")
    + "/mcp"
)

CHAT_PUBLIC_URL = os.getenv(
    "CHAT_PUBLIC_URL",
    "http://localhost:9000",
).rstrip("/")

CLIENT_ID = os.getenv(
    "MCP_CLIENT_ID",
    "demo-mcp-client",
)

CLIENT_SECRET = os.getenv(
    "MCP_CLIENT_SECRET",
    "demo-mcp-secret",
)


# ==================================================
# TEMPORARY PKCE STATE
# ==================================================

oauth_states = {}


# ==================================================
# HELPERS
# ==================================================

def create_pkce_pair():
    verifier = secrets.token_urlsafe(64)

    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                verifier.encode()
            ).digest()
        )
        .rstrip(b"=")
        .decode()
    )

    return verifier, challenge


def create_mcp_client(access_token: str):
    return Client(
        MCP_SERVER_URL,
        auth=access_token,
    )


# ==================================================
# HEALTH
# ==================================================

@app.get("/")
async def chat_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "request": request,
        },
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }


# ==================================================
# START OAUTH LOGIN
# ==================================================

@app.get("/connect")
async def connect_mcp():
    state = secrets.token_urlsafe(32)

    code_verifier, code_challenge = create_pkce_pair()

    oauth_states[state] = {
        "code_verifier": code_verifier,
    }

    redirect_uri = (
        f"{CHAT_PUBLIC_URL}/oauth/callback"
    )

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "products",
    }

    authorization_url = (
        f"{AUTH_SERVER_URL}/authorize?"
        + urlencode(params)
    )

    return RedirectResponse(
        authorization_url,
        status_code=303,
    )


# ==================================================
# OAUTH CALLBACK
# ==================================================

@app.get("/oauth/callback")
async def oauth_callback(
    request: Request,
):
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            f"OAuth error: {error}",
            status_code=400,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        return HTMLResponse(
            "Missing OAuth code or state",
            status_code=400,
        )

    oauth_state = oauth_states.pop(
        state,
        None,
    )

    if oauth_state is None:
        return HTMLResponse(
            "Invalid or expired OAuth state",
            status_code=400,
        )

    code_verifier = oauth_state["code_verifier"]

    redirect_uri = (
        f"{CHAT_PUBLIC_URL}/oauth/callback"
    )

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(
        timeout=20.0
    ) as http_client:

        response = await http_client.post(
            f"{AUTH_SERVER_URL}/token",
            data=token_data,
        )

    if response.status_code != 200:
        return HTMLResponse(
            f"Token exchange failed: {response.text}",
            status_code=400,
        )

    token_response = response.json()

    access_token = token_response.get(
        "access_token"
    )

    if not access_token:
        return HTMLResponse(
            "No access token returned",
            status_code=400,
        )

    response = RedirectResponse(
        "/",
        status_code=303,
    )

    response.set_cookie(
        "mcp_access_token",
        access_token,
        httponly=True,
        secure=bool(os.getenv("RENDER")),
        samesite="lax",
        max_age=3600,
    )

    return response


# ==================================================
# CALL MCP: WHO AM I
# ==================================================

@app.get("/connect-status")
async def connect_status(
    request: Request,
):
    access_token = request.cookies.get(
        "mcp_access_token"
    )

    if not access_token:
        return {
            "authenticated": False,
        }

    try:
        client = create_mcp_client(
            access_token
        )

        async with client:
            result = await client.call_tool(
                "who_am_i"
            )

        return {
            "authenticated": True,
            "user": result.data,
        }

    except Exception as exc:
        return {
            "authenticated": False,
            "error": str(exc),
        }


# ==================================================
# GET PRODUCTS THROUGH MCP
# ==================================================

@app.get("/products")
async def get_products(
    request: Request,
):
    access_token = request.cookies.get(
        "mcp_access_token"
    )

    if not access_token:
        return {
            "authenticated": False,
            "error": "Please login first",
        }

    try:
        client = create_mcp_client(
            access_token
        )

        async with client:
            result = await client.call_tool(
                "get_products"
            )

        return result.data

    except Exception as exc:
        return {
            "authenticated": False,
            "error": str(exc),
        }


# ==================================================
# LOGOUT
# ==================================================

@app.get("/logout")
async def logout(
    request: Request,
):
    access_token = request.cookies.get(
        "mcp_access_token"
    )

    if access_token:
        try:
            async with httpx.AsyncClient(
                timeout=10.0
            ) as http_client:

                await http_client.post(
                    f"{AUTH_SERVER_URL}/oauth/logout",
                    data={
                        "token": access_token,
                    },
                )

        except Exception:
            pass

    response = RedirectResponse(
        "/",
        status_code=303,
    )

    response.delete_cookie(
        "mcp_access_token"
    )

    return response