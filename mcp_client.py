import asyncio

from fastmcp import Client
from fastmcp.client.auth import OAuth


async def main():
    oauth = OAuth(
        client_id="demo-mcp-client",
        client_secret="demo-mcp-secret",
        scopes=["products"],
    )

    async with Client(
        "http://mcp.localhost:8001/mcp",
        auth=oauth,
    ) as client:

        user = await client.call_tool("who_am_i")
        print("User:")
        print(user.data)

        products = await client.call_tool("get_products")
        print("\nProducts:")
        print(products.data)


if __name__ == "__main__":
    asyncio.run(main())
