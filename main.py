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
from tn import scheduled_tours, load_tour_data
from potd import build_daily_potd
from pm_handler import get_random_cat_url
from rc_handler import listen_for_messages

load_dotenv()

USERNAME = os.getenv("PS_USERNAME")
PASSWORD = os.getenv("PS_PASSWORD")
ROOMS = ["monotype", "nationaldexmonotype"]
SERVER = "wss://sim3.psim.us/showdown/websocket"
PORT = int(os.environ.get("PORT", 10000))
RECONNECT_DELAY = 5  # seconds to wait before reconnecting

# Global connection status and backoff
connection_status = "Disconnected"
backoff = RECONNECT_DELAY

KEEP_ALIVE_URL = "https://meow-bot-ps.onrender.com/keep-alive"


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
            print(f"[DEBUG] Received message: {msg[:100]}...")
            if "|challstr|" in msg:
                print("[DEBUG] Found challstr.")
                challstr = msg.split("|challstr|")[1].strip()
                break
            else:
                print("[DEBUG] Challstr not in this message, waiting for next...")

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


async def room_logic(ws, room_name):
    """Encapsulates the logic for a single room."""
    await ws.send(f"|/join {room_name}")
    print(f"Joined room: {room_name}")

    # Run room-specific tasks in the background
    asyncio.create_task(scheduled_tours(ws, room_name))
    asyncio.create_task(build_daily_potd(ws, room_name))
    print(f"Started background tasks for room: {room_name}")


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
            async with websockets.connect(
                SERVER,
                ping_interval=30,   # send a ping every 30s
                ping_timeout=15     # if no pong within 15s, close the connection
            ) as ws:
                success = await login(ws)
                if not success:
                    raise ConnectionRefusedError("Login failed")

                await ws.send(f"|/avatar pokekidf-gen8")
                await ws.send(f"|/status Send 'meow' in PMs :3c")

                for room in ROOMS:  
                    await room_logic(ws, room)
                    room_commands_map = {room: load_tour_data(room) for room in ROOMS}
                asyncio.create_task(listen_for_messages(ws,room_commands_map))
                backoff = RECONNECT_DELAY
                connection_status = "Connected to Pokemon Showdown!"

                # Keep the connection alive forever
                await asyncio.Future()  # prevents exiting the `with` block

        except ConnectionClosed as e:
            if e.reason is None and e.code == 1006:  # Abnormal close, often from missed heartbeat
                reason = "missed heartbeat (Meow didnt get a response from PS in time?)"
            else:
                reason = e.reason or "No reason given"
            print(f"PS closed the connection: code={e.code}, reason={reason}. Retrying in {backoff}s...")
            connection_status = f"Disconnected: {reason} retrying in {backoff}s..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)

        except ConnectionRefusedError as e:
            print(f"Connection refused: {e}, Retrying in {backoff}s...")
            connection_status = f"PS refused meow connection, retrying in {backoff}s..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)

        except Exception as e:
            import traceback
            print(f"Unexpected error: {e}\n{traceback.format_exc()}")
            connection_status = "Error, reconnecting..."
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300) + random.randint(0, 5)



# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
async def main():
    async with aiohttp.ClientSession() as session:
        asyncio.create_task(start_web_server())
        asyncio.create_task(keep_alive_loop(session))
        await main_bot_logic()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Bot crashed: {e}")
