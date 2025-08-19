import asyncio
import websockets
import os
import requests
from dotenv import load_dotenv
import json
import aiohttp
from aiohttp import web
import random

# Assuming these modules exist.
from tn import listen_for_messages, scheduled_tours
from potd import build_daily_potd


load_dotenv()

USERNAME = os.getenv("PS_USERNAME")
PASSWORD = os.getenv("PS_PASSWORD")
ROOM = os.getenv("ROOM", "monotype")
SERVER = "wss://sim3.psim.us/showdown/websocket"
PORT = int(os.environ.get("PORT", 10000))
RECONNECT_DELAY = 5  # seconds to wait before reconnecting

# Global shared WebSocket connection object and connection status
ws = None
connection_status = "Disconnected"
# URL for the keep-alive endpoint
KEEP_ALIVE_URL = f"https://meow-bot-ps.onrender.com/keep-alive"
# -----------------------------------------------------------------------------
# Bot Logic Functions
# -----------------------------------------------------------------------------
async def handle_root(request):
    """
    Handles the root endpoint and displays the bot's connection status.
    """
    global connection_status
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meow Bot Status</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ font-family: sans-serif; text-align: center; margin-top: 50px; }}
            .status {{ font-size: 2em; font-weight: bold; }}
            .connected {{ color: green; }}
            .disconnected {{ color: red; }}
        </style>
    </head>
    <body>
        <h1>Meow Bot Status</h1>
        <p class="status {('connected' if 'Connected' in connection_status else 'disconnected')}">
            {connection_status}
        </p>
        <p>The web server is running independently of the Pokémon Showdown connection.</p>
        <p>This page automatically refreshes every 5 seconds.</p>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html")

async def login():
    """
    Handles the login process and sets the global WebSocket object.
    Returns True on success, False on failure.
    """
    global ws, connection_status
    connection_status = "Trying to connect to Pokémon Showdown..."
    print(connection_status)

    try:
        ws = await websockets.connect(SERVER)
    except Exception as e:
        print(f"Failed to connect to WebSocket: {e}")
        connection_status = "Failed to connect to PS"
        return False
    
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        print(f"Received: {msg[:100]}...")

        if "|challstr|" in msg:
            challstr = msg.split("|challstr|")[1].strip()
            print(f"Got challstr: {challstr[:20]}...")
            resp = requests.post("https://play.pokemonshowdown.com/action.php", data={
                'act': 'login',
                'name': USERNAME,
                'pass': PASSWORD,
                'challstr': challstr
            })
            
            if resp.status_code != 200:
                print(f"Login request failed with status: {resp.status_code}")
                connection_status = "Login failed: HTTP error"
                return False
            
            response_text = resp.text.strip()
            if response_text.startswith(']'):
                response_text = response_text[1:]
            
            try:
                response_data = json.loads(response_text)
                if 'assertion' not in response_data:
                    print(f"Login failed: {response_data}")
                    connection_status = "Login failed: No assertion"
                    return False
                assertion = response_data['assertion']
            except json.JSONDecodeError:
                print(f"Unexpected response format: {response_text}")
                connection_status = "Login failed: Bad response"
                return False
            
            await ws.send(f"|/trn {USERNAME},0,{assertion}")
            print("Login command sent")
            # Wait for a success message from PS
            await asyncio.sleep(2)
            connection_status = "Connected to Pokémon Showdown!"
            return True
        else:
            print("Did not receive a challstr. Login failed.")
            connection_status = "Login failed: No challstr"
            return False
    except asyncio.TimeoutError:
        print("Timeout waiting for challstr.")
        connection_status = "Login failed: Timeout"
        return False
    except Exception as e:
        print(f"Error during login: {e}")
        connection_status = "Login failed: Unexpected error"
        return False

async def join_room():
    """Joins the room and sets the bot's avatar and status."""
    global ws
    if ws and not ws.closed:
        await ws.send(f"|/join {ROOM}")
        print(f"Joined room: {ROOM}")
        await asyncio.sleep(0.5)
        await ws.send(f"|/avatar pokekidf-gen8")
        await ws.send(f"|/status Send 'meow' in PMs :3c")
        print(f"Set avatar for {USERNAME}")
    else:
        print("WebSocket is not open. Cannot join room.")

async def handle_keep_alive(request):
    """Simple handler for the keep-alive endpoint."""
    return web.Response(text="I'm awake!")

async def start_web_server():
    """Starts the web server."""
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/keep-alive', handle_keep_alive)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"Web server started on port {PORT}")
    
    # Keep the web server running indefinitely
    await asyncio.Event().wait()

async def keep_alive_loop():
    """A loop that sends a request to the keep-alive endpoint."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(KEEP_ALIVE_URL) as resp:
                    print(f"Keep-alive ping sent, status: {resp.status}")
        except Exception as e:
            print(f"Keep-alive failed: {e}")
        
        await asyncio.sleep(random.randint(1, 14) * 60) 

async def main_bot_logic():
    """
    Main loop for the bot's Pokémon Showdown connection and logic.
    Handles reconnection attempts.
    """
    global ws, connection_status
    while True:
        try:
            success = await login()
            if success:
                # If login is successful, start the core bot functions.
                await join_room()
                await asyncio.gather(
                    scheduled_tours(ws, ROOM),
                    listen_for_messages(ws, ROOM),
                    build_daily_potd(ws, ROOM)
                )
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"Connection to Pokémon Showdown closed, attempting to reconnect in {RECONNECT_DELAY} seconds... Error: {e}")
            if ws and not ws.closed:
                await ws.close()
            connection_status = "Disconnected, attempting to reconnect..."
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            print(f"An unexpected error occurred with the bot, attempting to reconnect in {RECONNECT_DELAY} seconds... Error: {e}")
            if ws and not ws.closed:
                await ws.close()
            connection_status = "An error occurred, attempting to reconnect..."
            await asyncio.sleep(RECONNECT_DELAY)

async def main():
    """
    The main entry point for the application.
    Starts the web server and bot logic concurrently.
    """
    await asyncio.gather(
        start_web_server(),
        main_bot_logic(),
        keep_alive_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Bot crashed: {e}")