import os
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastmcp import Client

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# -------------------------------------------------------------------
# Production URLs
# -------------------------------------------------------------------

AUTH_SERVER_URL = os.getenv(
    "AUTH_SERVER_URL",
    "https://fastmcp-oauth-authenticated-chat.onrender.com",
).rstrip("/")

MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
    "https://fastmcp-mcp-server-n8r6.onrender.com",
).rstrip("/")

if not MCP_SERVER_URL.endswith("/mcp"):
    MCP_SERVER_URL += "/mcp"

CHAT_PUBLIC_URL = os.getenv(
    "CHAT_PUBLIC_URL",
    "https://fastmcp-chat.onrender.com",
).rstrip("/")

CLIENT_ID = os.getenv("MCP_CLIENT_ID", "demo-mcp-client")
CLIENT_SECRET = os.getenv("MCP_CLIENT_SECRET", "demo-mcp-secret")

# Demo session store.
# Tokens are kept server-side and are never put in the browser cookie.
sessions = {}
oauth_states = {}

SESSION_COOKIE = "mcp_session"


def make_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def cleanup():
    now = time.time()

    for state, data in list(oauth_states.items()):
        if now > data["expires_at"]:
            oauth_states.pop(state, None)

    for session_id, data in list(sessions.items()):
        if now > data["expires_at"]:
            sessions.pop(session_id, None)


def get_session(request: Request):
    cleanup()
    session_id = request.cookies.get(SESSION_COOKIE)

    if not session_id:
        return None

    session = sessions.get(session_id)

    if not session:
        return None

    if time.time() > session["expires_at"]:
        sessions.pop(session_id, None)
        return None

    return session


def create_mcp_client(access_token: str):
    return Client(
        MCP_SERVER_URL,
        auth=access_token,
    )


# -------------------------------------------------------------------
# Chat page
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"request": request},
    )


# -------------------------------------------------------------------
# Start OAuth login
# -------------------------------------------------------------------

@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = make_pkce()

    redirect_uri = f"{CHAT_PUBLIC_URL}/oauth/callback"

    oauth_states[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "expires_at": time.time() + 600,
    }

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
        f"{AUTH_SERVER_URL}/authorize?{urlencode(params)}"
    )

    return RedirectResponse(authorization_url, status_code=303)


# -------------------------------------------------------------------
# OAuth callback
# -------------------------------------------------------------------

@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            f"OAuth authorization failed: {error}",
            status_code=400,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        return HTMLResponse(
            "Missing OAuth code or state.",
            status_code=400,
        )

    oauth_data = oauth_states.pop(state, None)

    if not oauth_data:
        return HTMLResponse(
            "Invalid or expired OAuth state. Start login again.",
            status_code=400,
        )

    if time.time() > oauth_data["expires_at"]:
        return HTMLResponse(
            "OAuth request expired. Start login again.",
            status_code=400,
        )

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth_data["redirect_uri"],
        "client_id": CLIENT_ID,
        "code_verifier": oauth_data["code_verifier"],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{AUTH_SERVER_URL}/token",
            data=token_data,
        )

    if response.status_code != 200:
        return JSONResponse(
            {
                "error": "token_exchange_failed",
                "status_code": response.status_code,
                "auth_server_response": response.text,
            },
            status_code=502,
        )

    token_response = response.json()
    access_token = token_response.get("access_token")

    if not access_token:
        return JSONResponse(
            {
                "error": "auth_server_did_not_return_access_token",
                "response": token_response,
            },
            status_code=502,
        )

    # Verify the token immediately through the MCP server.
    try:
        async with create_mcp_client(access_token) as client:
            result = await client.call_tool("who_am_i")
            user = result.data
    except Exception as exc:
        return JSONResponse(
            {
                "error": "mcp_authentication_failed",
                "details": str(exc),
            },
            status_code=502,
        )

    session_id = secrets.token_urlsafe(32)

    sessions[session_id] = {
        "access_token": access_token,
        "user": user,
        "expires_at": time.time() + 3600,
    }

    response = RedirectResponse("/", status_code=303)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
    )

    return response


# -------------------------------------------------------------------
# Authentication status
# -------------------------------------------------------------------

@app.get("/auth/status")
async def auth_status(request: Request):
    session = get_session(request)

    if not session:
        return {
            "authenticated": False,
        }

    return {
        "authenticated": True,
        "user": session["user"],
    }


# -------------------------------------------------------------------
# MCP connection test
# -------------------------------------------------------------------

@app.get("/connect")
async def connect_mcp(request: Request):
    session = get_session(request)

    if not session:
        return JSONResponse(
            {"authenticated": False, "message": "Please login first."},
            status_code=401,
        )

    try:
        async with create_mcp_client(session["access_token"]) as client:
            result = await client.call_tool("who_am_i")

        session["user"] = result.data

        return {
            "authenticated": True,
            "user": result.data,
        }

    except Exception as exc:
        return JSONResponse(
            {
                "authenticated": False,
                "message": "MCP authentication failed.",
                "details": str(exc),
            },
            status_code=401,
        )


# -------------------------------------------------------------------
# Products
# -------------------------------------------------------------------

@app.get("/products")
async def get_products(request: Request):
    session = get_session(request)

    if not session:
        return JSONResponse(
            {"error": "Please login first."},
            status_code=401,
        )

    try:
        async with create_mcp_client(session["access_token"]) as client:
            result = await client.call_tool("get_products")

        return result.data

    except Exception as exc:
        return JSONResponse(
            {
                "error": "MCP request failed",
                "details": str(exc),
            },
            status_code=502,
        )


# -------------------------------------------------------------------
# Logout
# -------------------------------------------------------------------

@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)

    if session_id:
        sessions.pop(session_id, None)

    response = RedirectResponse("/", status_code=303)

    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return response