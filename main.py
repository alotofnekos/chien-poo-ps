import asyncio
import websockets
import os
import requests
from dotenv import load_dotenv
import json
import aiohttp
from aiohttp import web
import random
from websockets.exceptions import ConnectionClosed
from tn import listen_for_messages, scheduled_tours
from potd import build_daily_potd
from pm_handler import get_random_cat_url

load_dotenv()

USERNAME = os.getenv("PS_USERNAME")
PASSWORD = os.getenv("PS_PASSWORD")
ROOM = os.getenv("ROOM", "monotype")
SERVER = "wss://sim3.psim.us/showdown/websocket"
PORT = int(os.environ.get("PORT", 10000))
RECONNECT_DELAY = 5  # seconds to wait before reconnecting

# Global connection status and backoff
connection_status = "Disconnected"
backoff = RECONNECT_DELAY

KEEP_ALIVE_URL = f"https://meow-bot-ps.onrender.com/keep-alive"


# -----------------------------------------------------------------------------
# Web server endpoints
# -----------------------------------------------------------------------------
async def handle_root(request):
    cat = await get_random_cat_url()
    global connection_status, backoff
    refresh_time = max(backoff, 30)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meow Bot Status</title>
        <meta http-equiv="refresh" content="{backoff}">
        <style>
            body {{ font-family: sans-serif; text-align: center; margin-top: 50px; }}
            .status {{ font-size: 2em; font-weight: bold; }}
            .connected {{ color: green; }}
            .disconnected {{ color: red; }}
        </style>
    </head>
    <body>
        <h1>Meow Bot Status</h1>
        <img class="cat-photo" src="{cat}" alt="Random Cat" height="200"/>
        <p class="status {('connected' if 'Connected' in connection_status else 'disconnected')}">
            {connection_status}
        </p>
        <p>The web server shows the status of Meow. If it's down and this page isn't down, it means the bot has trouble connecting to PS.</p>
        <p>If you can't see this page, contact Neko immediately.</p>
        <p>This page automatically refreshes every {refresh_time} seconds.</p>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html")


async def handle_keep_alive(request):
    global connection_status
    return web.json_response({"status": connection_status})


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/keep-alive', handle_keep_alive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"Web server started on port {PORT}")
    await asyncio.Event().wait()


# -----------------------------------------------------------------------------
# Pokémon Showdown login + room join
# -----------------------------------------------------------------------------
async def login(ws):
    """Login to PS using the provided websocket connection."""
    global connection_status
    connection_status = "Trying to connect to Pokemon Showdown..."
    print(connection_status)

    try:
        # Loop to find the challstr message
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"[DEBUG] Received message: {msg[:100]}...")  # Added for debugging
            if "|challstr|" in msg:
                print("[DEBUG] Found challstr.")  # Added for debugging
                challstr = msg.split("|challstr|")[1].strip()
                break  # Exit the loop once challstr is found
            else:
                print("[DEBUG] Challstr not in this message, waiting for next...")  # Added for debugging

        # Rest of your login logic
        resp = requests.post(
            "https://play.pokemonshowdown.com/action.php",
            data={
                'act': 'login',
                'name': USERNAME,
                'pass': PASSWORD,
                'challstr': challstr
            }
        )

        print(f"[DEBUG] Login HTTP response code: {resp.status_code}")
        print(f"[DEBUG] Raw login response text: {resp.text[:300]}... (truncated)")

        if resp.status_code != 200:
            connection_status = "Login failed: HTTP error"
            return False

        response_text = resp.text.strip()
        if response_text.startswith(']'):
            response_text = response_text[1:]
        print(f"[DEBUG] Cleaned response text: {response_text[:300]}... (truncated)")

        response_data = json.loads(response_text)
        print(f"[DEBUG] Parsed response JSON: {response_data}")

        if 'assertion' not in response_data:
            connection_status = "Login failed: No assertion"
            print("[DEBUG] Assertion missing in response JSON")
            return False

        assertion = response_data['assertion']
        print(f"[DEBUG] Got assertion: {assertion[:100]}... (truncated)")

        await ws.send(f"|/trn {USERNAME},0,{assertion}")
        print(f"[DEBUG] Sent /trn command for user {USERNAME}")

        await asyncio.sleep(2)  # short wait for PS to process
        connection_status = "Connected to Pokemon Showdown!"
        print("[DEBUG] Login successful")
        return True

    except Exception as e:
        print(f"[DEBUG] Exception during login: {e}")
        connection_status = "Login failed"
        return False


async def join_room(ws):
    """Joins the room and sets avatar/status."""
    await ws.send(f"|/join {ROOM}")
    await asyncio.sleep(0.5)
    await ws.send(f"|/avatar pokekidf-gen8")
    await ws.send(f"|/status Send 'meow' in PMs :3c")
    print(f"Joined room {ROOM} as {USERNAME}")


# -----------------------------------------------------------------------------
# Keep-alive pinger
# -----------------------------------------------------------------------------
async def keep_alive_loop(session: aiohttp.ClientSession):
    while True:
        try:
            async with session.get(KEEP_ALIVE_URL) as resp:
                print(f"Keep-alive ping sent, status: {resp.status}")
        except Exception as e:
            print(f"Keep-alive failed: {e}")

        await asyncio.sleep(random.randint(1, 14) * 60)


# -----------------------------------------------------------------------------
# Bot main loop
# -----------------------------------------------------------------------------
async def main_bot_logic():
    global connection_status, backoff
    backoff = RECONNECT_DELAY

    while True:
        try:
            async with websockets.connect(SERVER) as ws:
                success = await login(ws)
                if not success:
                    raise ConnectionRefusedError("Login failed")

                await join_room(ws)
                backoff = RECONNECT_DELAY  # reset on success

                await asyncio.gather(
                    scheduled_tours(ws, ROOM),
                    listen_for_messages(ws, ROOM),
                    build_daily_potd(ws, ROOM)
                )

        except ConnectionClosed as e:
            print(f"PS closed the connection: code={e.code}, reason={e.reason}. Retrying in {backoff}s...")
            connection_status = f"Disconnected: {e.reason or 'No reason given'} retrying in {backoff}s..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)

        except ConnectionRefusedError as e:
            print(f"Connection refused: {e}, Retrying in {backoff}s...")
            connection_status = f"PS refused meow connection, retrying in {backoff}s..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)

        except Exception as e:
            print(f"Unexpected error: {e}. Retrying in {backoff}s...")
            connection_status = "Error, reconnecting..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
async def main():
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            start_web_server(),
            main_bot_logic(),
            keep_alive_loop(session)
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Bot crashed: {e}")
