import os
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from fastmcp import Client


# ============================================================
# APP
# ============================================================

app = FastAPI()

templates = Jinja2Templates(directory="templates")


# ============================================================
# CONFIGURATION
# ============================================================

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

CLIENT_ID = os.getenv(
    "MCP_CLIENT_ID",
    "demo-mcp-client",
)

CLIENT_SECRET = os.getenv(
    "MCP_CLIENT_SECRET",
    "demo-mcp-secret",
)

CHAT_PUBLIC_URL = os.getenv(
    "CHAT_PUBLIC_URL",
    "http://localhost:10000",
).rstrip("/")


# ============================================================
# OAUTH ENDPOINTS
# ============================================================

AUTHORIZE_URL = f"{AUTH_SERVER_URL}/authorize"
TOKEN_URL = f"{AUTH_SERVER_URL}/token"

REDIRECT_URI = f"{CHAT_PUBLIC_URL}/oauth/callback"


# ============================================================
# PKCE HELPERS
# ============================================================

def create_code_verifier() -> str:
    """
    Create the PKCE code_verifier.
    """
    return secrets.token_urlsafe(64)


def create_code_challenge(code_verifier: str) -> str:
    """
    Create the PKCE S256 code_challenge.
    """
    digest = hashlib.sha256(
        code_verifier.encode("utf-8")
    ).digest()

    return base64.urlsafe_b64encode(
        digest
    ).rstrip(b"=").decode("utf-8")


# ============================================================
# HOME / CHAT PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):

    access_token = request.cookies.get("access_token")

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "request": request,
            "authenticated": bool(access_token),
        },
    )


# ============================================================
# LOGIN
# ============================================================

@app.get("/login")
async def login(request: Request):

    state = secrets.token_urlsafe(32)

    code_verifier = create_code_verifier()

    code_challenge = create_code_challenge(
        code_verifier
    )

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "products",
    }

    authorization_url = (
        AUTHORIZE_URL
        + "?"
        + urlencode(params)
    )

    response = RedirectResponse(
        authorization_url,
        status_code=303,
    )

    # Store OAuth state and PKCE verifier
    # temporarily in secure HTTP-only cookies.
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
    )

    response.set_cookie(
        key="oauth_code_verifier",
        value=code_verifier,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
    )

    return response


# ============================================================
# OAUTH CALLBACK
# ============================================================

@app.get("/oauth/callback")
async def oauth_callback(request: Request):

    code = request.query_params.get("code")

    state = request.query_params.get("state")

    error = request.query_params.get("error")

    if error:
        return JSONResponse(
            {
                "error": error,
                "description": request.query_params.get(
                    "error_description"
                ),
            },
            status_code=400,
        )

    if not code:
        return JSONResponse(
            {
                "error": "missing_authorization_code"
            },
            status_code=400,
        )

    if not state:
        return JSONResponse(
            {
                "error": "missing_state"
            },
            status_code=400,
        )

    # --------------------------------------------------------
    # Validate state
    # --------------------------------------------------------

    saved_state = request.cookies.get(
        "oauth_state"
    )

    if not saved_state:
        return JSONResponse(
            {
                "error": "missing_oauth_state"
            },
            status_code=400,
        )

    if not secrets.compare_digest(
        state,
        saved_state,
    ):
        return JSONResponse(
            {
                "error": "invalid_oauth_state"
            },
            status_code=400,
        )

    # --------------------------------------------------------
    # Get PKCE verifier
    # --------------------------------------------------------

    code_verifier = request.cookies.get(
        "oauth_code_verifier"
    )

    if not code_verifier:
        return JSONResponse(
            {
                "error": "missing_code_verifier"
            },
            status_code=400,
        )

    # --------------------------------------------------------
    # Exchange authorization code for access token
    # --------------------------------------------------------

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(
        timeout=20.0
    ) as client:

        token_response = await client.post(
            TOKEN_URL,
            data=token_data,
        )

    if token_response.status_code != 200:

        return JSONResponse(
            {
                "error": "token_exchange_failed",
                "status_code": token_response.status_code,
                "response": token_response.text,
            },
            status_code=400,
        )

    token_json = token_response.json()

    access_token = token_json.get(
        "access_token"
    )

    if not access_token:

        return JSONResponse(
            {
                "error": "access_token_missing",
                "response": token_json,
            },
            status_code=400,
        )

    # --------------------------------------------------------
    # Store access token in secure HTTP-only cookie
    # --------------------------------------------------------

    response = RedirectResponse(
        "/",
        status_code=303,
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
    )

    # OAuth temporary values are no longer needed.
    response.delete_cookie(
        "oauth_state"
    )

    response.delete_cookie(
        "oauth_code_verifier"
    )

    return response


# ============================================================
# MCP CLIENT
# ============================================================

async def call_mcp_tool(
    access_token: str,
    tool_name: str,
):

    async with Client(
        MCP_SERVER_URL,
        auth=access_token,
    ) as client:

        result = await client.call_tool(
            tool_name
        )

    return result.data


# ============================================================
# CONNECT / WHO AM I
# ============================================================

@app.get("/connect")
async def connect_mcp(
    request: Request,
):

    access_token = request.cookies.get(
        "access_token"
    )

    if not access_token:

        return JSONResponse(
            {
                "authenticated": False,
                "message": "Please authenticate first.",
                "login": "/login",
            },
            status_code=401,
        )

    try:

        result = await call_mcp_tool(
            access_token,
            "who_am_i",
        )

        return {
            "authenticated": True,
            "user": result,
        }

    except Exception as exc:

        return JSONResponse(
            {
                "authenticated": False,
                "error": str(exc),
            },
            status_code=401,
        )


# ============================================================
# PRODUCTS
# ============================================================

@app.get("/products")
async def get_products(
    request: Request,
):

    access_token = request.cookies.get(
        "access_token"
    )

    if not access_token:

        return JSONResponse(
            {
                "error": "Not authenticated",
                "login": "/login",
            },
            status_code=401,
        )

    try:

        result = await call_mcp_tool(
            access_token,
            "get_products",
        )

        return result

    except Exception as exc:

        return JSONResponse(
            {
                "error": str(exc)
            },
            status_code=401,
        )


# ============================================================
# LOGOUT
# ============================================================

@app.get("/logout")
async def logout():

    response = RedirectResponse(
        "/",
        status_code=303,
    )

    response.delete_cookie(
        "access_token"
    )

    response.delete_cookie(
        "oauth_state"
    )

    response.delete_cookie(
        "oauth_code_verifier"
    )

    return response