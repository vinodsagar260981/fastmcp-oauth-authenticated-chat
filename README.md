# MCP FastAPI OAuth Demo

## Architecture

Browser
  -> http://localhost:9000
  -> chat_app running on Windows

Docker:
  auth_server :8000
  mcp_server  :8001

The FastMCP OAuth helper starts a local callback server in the same process as chat_app.
Therefore chat_app is intentionally NOT containerized in this demo.

## 1. Build and start Docker services

docker compose down
docker compose build --no-cache
docker compose up

## 2. Run chat_app on Windows

Open a second PowerShell:

uvicorn chat_app:app --reload --port 9000

Open:

http://localhost:9000

## Credentials

Username: vinod
Password: password123

## Expected OAuth flow

localhost:9000
 -> chat_app
 -> mcp.localhost:8001/mcp
 -> auth.localhost:8000/authorize
 -> login
 -> local FastMCP callback
 -> auth.localhost:8000/token
 -> access token
 -> MCP server
 -> auth_server:8000/introspect
 -> get_products

## Important

Do not change MCP_SERVER_URL to localhost:8001/mcp.

It must match the MCP server public base_url:

http://mcp.localhost:8001
