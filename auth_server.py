import base64
import os
import secrets
import time
from hashlib import sha256
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


app = FastAPI()
templates = Jinja2Templates(directory="templates")

AUTH_SERVER_PUBLIC_URL = os.getenv(
    "AUTH_SERVER_PUBLIC_URL",
    "http://auth.localhost:8000"
).rstrip("/")

# ==================================================
# CONFIGURATION
# ==================================================

USERNAME = os.getenv("DEMO_USERNAME", "vinod")
PASSWORD = os.getenv("DEMO_PASSWORD", "password123")

CLIENT_ID = os.getenv("MCP_CLIENT_ID", "demo-mcp-client")
CLIENT_SECRET = os.getenv("MCP_CLIENT_SECRET", "demo-mcp-secret")

AUTH_SERVER_URL = os.getenv(
    "AUTH_SERVER_URL",
    "http://auth.localhost:8000",
).rstrip("/")

CHAT_PUBLIC_URL = os.getenv(
    "CHAT_PUBLIC_URL",
    "http://localhost:9000",
).rstrip("/")

ALLOWED_REDIRECT_URI = f"{CHAT_PUBLIC_URL}/oauth/callback"


# ==================================================
# DEMO PRODUCTS
# ==================================================

products = [
    {"id": 1, "name": "MacBook Pro", "price": 150000},
    {"id": 2, "name": "iPhone 17", "price": 90000},
    {"id": 3, "name": "AirPods Pro", "price": 25000},
    {"id": 4, "name": "iPad Air", "price": 60000},
]


# ==================================================
# IN-MEMORY TOKEN STORAGE
# ==================================================

authorization_codes = {}
access_tokens = {}
revoked_tokens = set()


# ==================================================
# HEALTH
# ==================================================

@app.get("/")
async def root():
    return {
        "service": "FastMCP OAuth Authentication Server",
        "status": "ok",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }


# ==================================================
# NORMAL WEBSITE LOGIN
# ==================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "error": None,
        },
    )


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username != USERNAME or password != PASSWORD:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Invalid username or password",
            },
            status_code=401,
        )

    response = RedirectResponse(
        "/home",
        status_code=303,
    )

    response.set_cookie(
        "demo_user",
        username,
        httponly=True,
        secure=bool(os.getenv("RENDER")),
        samesite="lax",
    )

    return response


@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    user = request.cookies.get("demo_user")

    if user != USERNAME:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "request": request,
            "username": user,
            "products": products,
        },
    )


# ==================================================
# OAUTH DISCOVERY
# ==================================================

@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata():
    return {
        "issuer": AUTH_SERVER_PUBLIC_URL,
        "authorization_endpoint": f"{AUTH_SERVER_PUBLIC_URL}/authorize",
        "token_endpoint": f"{AUTH_SERVER_PUBLIC_URL}/token",
        "registration_endpoint": f"{AUTH_SERVER_PUBLIC_URL}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["products"],
    }


# ==================================================
# CLIENT REGISTRATION
# ==================================================

@app.post("/register")
async def register(request: Request):
    data = await request.json()

    return {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "client_name": data.get(
            "client_name",
            "FastMCP OAuth Chat",
        ),
    }


# ==================================================
# OAUTH AUTHORIZE
# ==================================================

@app.get("/authorize", response_class=HTMLResponse)
async def authorize(
    request: Request,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    state: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str = "products",
):
    if client_id != CLIENT_ID:
        return HTMLResponse(
            "Unknown client",
            status_code=400,
        )

    if response_type != "code":
        return HTMLResponse(
            "Unsupported response type",
            status_code=400,
        )

    if code_challenge_method != "S256":
        return HTMLResponse(
            "Unsupported PKCE method",
            status_code=400,
        )

    if redirect_uri != ALLOWED_REDIRECT_URI:
        return HTMLResponse(
            "Invalid redirect_uri",
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "error": None,
            "oauth": True,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": response_type,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "scope": scope,
        },
    )


@app.post("/authorize")
async def authorize_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form(...),
    state: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    scope: str = Form("products"),
):
    if client_id != CLIENT_ID:
        return HTMLResponse(
            "Unknown client",
            status_code=400,
        )

    if redirect_uri != ALLOWED_REDIRECT_URI:
        return HTMLResponse(
            "Invalid redirect_uri",
            status_code=400,
        )

    if response_type != "code":
        return HTMLResponse(
            "Unsupported response type",
            status_code=400,
        )

    if code_challenge_method != "S256":
        return HTMLResponse(
            "Unsupported PKCE method",
            status_code=400,
        )

    if username != USERNAME or password != PASSWORD:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Invalid username or password",
                "oauth": True,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": response_type,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "scope": scope,
            },
            status_code=401,
        )

    code = secrets.token_urlsafe(32)

    authorization_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "username": username,
        "scope": scope,
        "expires_at": time.time() + 300,
    }

    redirect_url = redirect_uri + "?" + urlencode(
        {
            "code": code,
            "state": state,
        }
    )

    return RedirectResponse(
        redirect_url,
        status_code=303,
    )


# ==================================================
# TOKEN
# ==================================================

@app.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str = Form(...),
):
    if grant_type != "authorization_code":
        return JSONResponse(
            {
                "error": "unsupported_grant_type",
            },
            status_code=400,
        )

    oauth_code = authorization_codes.get(code)

    if not oauth_code:
        return JSONResponse(
            {
                "error": "invalid_grant",
            },
            status_code=400,
        )

    if time.time() > oauth_code["expires_at"]:
        authorization_codes.pop(code, None)

        return JSONResponse(
            {
                "error": "invalid_grant",
            },
            status_code=400,
        )

    if client_id != oauth_code["client_id"]:
        return JSONResponse(
            {
                "error": "invalid_client",
            },
            status_code=401,
        )

    if redirect_uri != oauth_code["redirect_uri"]:
        return JSONResponse(
            {
                "error": "invalid_grant",
            },
            status_code=400,
        )

    calculated_challenge = (
        base64.urlsafe_b64encode(
            sha256(
                code_verifier.encode()
            ).digest()
        )
        .rstrip(b"=")
        .decode()
    )

    if calculated_challenge != oauth_code["code_challenge"]:
        return JSONResponse(
            {
                "error": "invalid_grant",
            },
            status_code=400,
        )

    authorization_codes.pop(code, None)

    access_token = secrets.token_urlsafe(32)

    access_tokens[access_token] = {
        "username": oauth_code["username"],
        "client_id": client_id,
        "scope": oauth_code["scope"],
        "expires_at": time.time() + 3600,
    }

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": oauth_code["scope"],
    }


# ==================================================
# TOKEN INTROSPECTION
# ==================================================

@app.post("/introspect")
async def introspect(request: Request):
    authorization = request.headers.get(
        "Authorization",
        "",
    )

    expected = (
        "Basic "
        + base64.b64encode(
            f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
        ).decode()
    )

    if authorization != expected:
        return {
            "active": False,
        }

    form = await request.form()
    token_value = form.get("token")

    if token_value in revoked_tokens:
        return {
            "active": False,
        }

    token_data = access_tokens.get(token_value)

    if not token_data:
        return {
            "active": False,
        }

    if time.time() > token_data["expires_at"]:
        access_tokens.pop(
            token_value,
            None,
        )

        return {
            "active": False,
        }

    return {
        "active": True,
        "client_id": token_data["client_id"],
        "username": token_data["username"],
        "scope": token_data["scope"],
        "sub": token_data["username"],
    }


# ==================================================
# LOGOUT / TOKEN REVOCATION
# ==================================================

@app.get("/logout")
async def logout():
    response = RedirectResponse(
        "/login",
        status_code=303,
    )

    response.delete_cookie("demo_user")

    return response


@app.post("/oauth/logout")
async def oauth_logout(request: Request):
    form = await request.form()
    token_value = form.get("token")

    if token_value:
        revoked_tokens.add(token_value)
        access_tokens.pop(
            token_value,
            None,
        )

    return {
        "success": True,
    }