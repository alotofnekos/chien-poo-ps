import asyncio
import websockets
import os
import requests
from dotenv import load_dotenv
import json
import aiohttp
import random
from aiohttp import web
from tn import listen_for_messages, scheduled_tours

load_dotenv()

USERNAME = os.getenv("PS_USERNAME")
PASSWORD = os.getenv("PS_PASSWORD")
ROOM = os.getenv("ROOM", "monotype")
SERVER = "wss://sim3.psim.us/showdown/websocket"
PORT = int(os.getenv("PORT", 8080))
RECONNECT_DELAY = 5  # seconds to wait before reconnecting

# Shared WebSocket connection object
ws = None
# URL for the keep-alive endpoint
KEEP_ALIVE_URL = f"https://meow-bot-ps.onrender.com/keep-alive"
# -----------------------------------------------------------------------------
# Bot Logic Functions
# -----------------------------------------------------------------------------

async def login():
    """Handles the login process and sets the global WebSocket object."""
    global ws
    print("Connecting to Pokemon Showdown...")
    
    try:
        ws = await websockets.connect(SERVER)
    except Exception as e:
        print(f"Failed to connect to WebSocket: {e}")
        return False
        
    while True:
        try:
            msg = await ws.recv()
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
                    return False
                
                response_text = resp.text.strip()
                if response_text.startswith(']'):
                    response_text = response_text[1:]
                
                try:
                    response_data = json.loads(response_text)
                    if 'assertion' not in response_data:
                        print(f"Login failed: {response_data}")
                        return False
                    assertion = response_data['assertion']
                except json.JSONDecodeError:
                    print(f"Unexpected response format: {response_text}")
                    return False
                
                await ws.send(f"|/trn {USERNAME},0,{assertion}")
                print("Login command sent")
                await asyncio.sleep(1)
                break
        except Exception as e:
            print(f"Error during login: {e}")
            return False
    return True

async def join_room():
    """Joins the room and sets the bot's avatar."""
    await ws.send(f"|/join {ROOM}")
    print(f"Joined room: {ROOM}")
    await asyncio.sleep(0.5)
    await ws.send(f"|/avatar pokekidf-gen8")
    print(f"Set avatar for {USERNAME}")

async def handle_keep_alive(request):
    """Simple handler for the keep-alive endpoint."""
    return web.Response(text="I'm awake!")

async def start_web_server():
    """Starts the web server."""
    app = web.Application()
    app.router.add_get('/keep-alive', handle_keep_alive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"Web server started on port {PORT}")
    await asyncio.Event().wait()

async def keep_alive_loop():
    """A loop that sends a request to the server every few minutes."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(KEEP_ALIVE_URL) as resp:
                    print(f"Keep-alive ping sent, status: {resp.status}")
        except Exception as e:
            print(f"Keep-alive failed: {e}")
        
        await asyncio.sleep(random.randint(1, 15) * 60) 


async def run_bot():
    """The main function to run the bot's tasks after login."""
    global ws
    await join_room()

    await asyncio.gather(
        start_web_server(),
        keep_alive_loop(),
        scheduled_tours(ws, ROOM),
        listen_for_messages(ws, ROOM),
    )

async def main_reconnection_loop():
    """Main loop with reconnection logic."""
    while True:
        try:
            success = await login()
            if success:
                await run_bot()
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"Connection closed, attempting to reconnect in {RECONNECT_DELAY} seconds... Error: {e}")
            if ws and not ws.closed:
                await ws.close()
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            print(f"An unexpected error occurred, attempting to reconnect in {RECONNECT_DELAY} seconds... Error: {e}")
            if ws and not ws.closed:
                await ws.close()
            await asyncio.sleep(RECONNECT_DELAY)

if __name__ == "__main__":
    try:
        asyncio.run(main_reconnection_loop())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Bot crashed: {e}")