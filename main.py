import asyncio
import websockets
import os
import requests
from dotenv import load_dotenv
import json
from tn import main as tours_main, listen_for_messages as tours_listen, scheduled_tours as tours_schedule

load_dotenv()

USERNAME = os.getenv("PS_USERNAME")
PASSWORD = os.getenv("PS_PASSWORD")
ROOM = os.getenv("ROOM", "monotype")
SERVER = "wss://sim3.psim.us/showdown/websocket"

ws = None

# The HTML box content to send
HTML_BOX_MESSAGE = '/addhtmlbox <a href="#" target="_blank" style="text-decoration: none; color: #000; background: linear-gradient(135deg, #EE99AC 0%, #705898 100%); padding: 1rem; border: .125rem solid transparent; border-radius: .25rem; display: flex;"><table cellpadding="0" cellspacing="0" width="100%"><tr><td style="background-color: rgba(255, 255, 255, 75%); padding: 1rem; border-radius: .25rem; font-size: .875rem;" valign="middle">Flutter Mane is the Pokemon of the day! What sets do you like using on it? How would you support it on its respective typings?</td><td style="width: 1rem;"></td><td valign="middle" style="padding: 1.5rem; border-radius: 100rem; border: .125rem solid #00d4ff;"><img src="https://www.smogon.com/dex/media/sprites//xy/flutter_mane.gif" width="90" height="82" style="vertical-align: middle"></td></tr></table></a>'

async def login():
    global ws
    print("Connecting to Pokemon Showdown...")
    ws = await websockets.connect(SERVER)

    while True:
        try:
            msg = await ws.recv()
            print(f"Received: {msg[:100]}...")  # Debug output

            if "|challstr|" in msg:
                challstr = msg.split("|challstr|")[1].strip()
                print(f"Got challstr: {challstr[:20]}...")

                # Login request
                resp = requests.post("https://play.pokemonshowdown.com/action.php", data={
                    'act': 'login',
                    'name': USERNAME,
                    'pass': PASSWORD,
                    'challstr': challstr
                })

                if resp.status_code != 200:
                    print(f"Login request failed with status: {resp.status_code}")
                    continue

                response_text = resp.text.strip()
                print(f"Login response: {response_text[:100]}...")

                if response_text.startswith(']'):
                    response_text = response_text[1:]

                try:
                    response_data = json.loads(response_text)
                    if 'assertion' not in response_data:
                        print(f"Login failed: {response_data}")
                        continue
                    assertion = response_data['assertion']
                    print("Successfully parsed JSON response")
                except json.JSONDecodeError:
                    if response_text.startswith(';;'):
                        print(f"Login error: {response_text}")
                        continue
                    elif len(response_text) > 10:
                        assertion = response_text
                        print("Using response text as assertion")
                    else:
                        print(f"Unexpected response format: {response_text}")
                        continue

                await ws.send(f"|/trn {USERNAME},0,{assertion}")
                print("Login command sent")
                break

        except websockets.exceptions.ConnectionClosed:
            print("Connection closed during login")
            raise
        except Exception as e:
            print(f"Error during login: {e}")
            raise

async def join_room():
    await ws.send(f"|/join {ROOM}")
    print(f"Joined room: {ROOM}")
    await asyncio.sleep(0.5)
    await ws.send(f"|/avatar pokekidf-gen8") # Set avatar
    print(f"Set avatar for {USERNAME}")

async def send_html_box():
    """Sends the HTML box message to the room."""
    # Try the correct format for room commands
    await ws.send(f"{ROOM}|{HTML_BOX_MESSAGE}")
    print(f"Sent HTML box to room: {ROOM}")

async def send_test_message():
    """Sends a simple test message to verify room messaging works."""
    test_msg = "Meow!"
    await ws.send(f"{ROOM}|{test_msg}")
    print(f"Sent test message to room: {ROOM}")

#async def scheduled_tasks():
#    """Schedules the initial and repeating HTML box messages."""
#    # Send a test message first
#    await asyncio.sleep(5)  
#    await send_test_message()
#    print(f"Sent initial test message to room: {ROOM}")
    
#    await asyncio.sleep(1 * 60)  
#    await send_html_box()
#    print(f"Sent initial HTML box to room: {ROOM}")

#    while True:
#        await asyncio.sleep(120 * 60) 
#        await send_html_box()

async def handle_messages():
    print("Starting message handler...")
    while True:
        try:
            msg = await ws.recv()
            
            # Debug: Print all messages to see what we're receiving
            if f">{ROOM}" in msg:
                print(f"Room message received: {msg}")
            
            # Check if it's a chat message in our room
            if f">{ROOM}" in msg and "|c|" in msg:
                lines = msg.split('\n')
                for line in lines:
                    if line.startswith(f">{ROOM}") and "|c|" in line:
                        parts = line.split("|")
                        if len(parts) >= 4 and parts[1] == "c":
                            user = parts[2].strip()
                            message = "|".join(parts[3:]).strip()
                            
                            print(f"Chat from {user}: {message}")
            
            # Handle private messages
            elif "|pm|" in msg:
                lines = msg.split('\n')
                for line in lines:
                    if "|pm|" in line:
                        parts = line.split("|")
                        if len(parts) >= 5 and parts[1] == "pm":
                            from_user = parts[2].strip()
                            to_user = parts[3].strip()
                            message = "|".join(parts[4:]).strip()
                            
                            # Prevent the bot from replying to itself
                            if from_user.lower() == USERNAME.lower():
                                continue

                            else:
                                pm_response = f"|/pm {from_user}, Meow! I'm still in progress!"
                                await ws.send(pm_response)
                                print(f"Sent auto PM response: {pm_response}")

        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
            break
        except Exception as e:
            print(f"Error in message handler: {e}")
            break

async def main():
    try:
        await login()
        await asyncio.sleep(1)
        await join_room()
        
        await asyncio.gather(
            tours_schedule(ws, ROOM),
            tours_listen(ws, ROOM), 
            #scheduled_tasks(),
        )

    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        if ws:
            await ws.close()
            print("WebSocket connection closed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Bot crashed: {e}")