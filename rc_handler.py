import asyncio
import random
import os
from dotenv import load_dotenv
from pm_handler import handle_pmmessages
from potd import send_potd
import time
from tn import generate_monthly_tour_schedule_html
import datetime

load_dotenv()
USERNAME = os.getenv("PS_USERNAME")


async def listen_for_messages(ws, room_commands_map):
    """Listens for and processes ALL messages from the WebSocket, dispatching by room."""
    print("Starting global message listener...")
    listener_start_time = int(time.time())
    while True:
        try:
            raw = await ws.recv()
            lines = raw.split("\n")

            current_room = None
            for line in lines:
                if not line:
                    continue

                # If this line specifies a room
                if line.startswith(">"):
                    current_room = line[1:].strip()
                    continue

                # PMs
                if line.startswith("|pm|"):
                    await handle_pmmessages(ws, USERNAME, line)

                # chat messages
                elif line.startswith("|c:|") and current_room:

                    parts = line.split("|")
                    if len(parts) < 5:
                        continue
                    ts = int(parts[2].strip())
                    user = parts[3].strip()
                    msg_text = parts[4].strip()
                    prefix = user[:1]
                    if ts < listener_start_time:
                        continue

                    if "meow" in msg_text.lower() and prefix in ('+','%', '@', '#'):
                        print(f"Received from {user} in {current_room}: {msg_text}")

                        TOUR_COMMANDS = room_commands_map.get(current_room, {})

                        if msg_text.lower().startswith("meow start"):
                            tour_name = msg_text[len("meow start"):].strip()

                            lower_map = {k.lower(): k for k in TOUR_COMMANDS.keys()}
                            if tour_name.lower() in lower_map:
                                lookup_key = lower_map[tour_name.lower()]
                                tour_commands = TOUR_COMMANDS[lookup_key].split('\n')
                                for command in tour_commands:
                                    await ws.send(f"{current_room}|{command.strip()}")
                            else:
                                available = ", ".join(TOUR_COMMANDS.keys())
                                await ws.send(f"{current_room}|Meow couldn’t find '{tour_name}'. "
                                              f"Available tours: {available}")

                        elif msg_text.lower().startswith("meow show potd"):
                            await send_potd(ws, current_room)
                            await ws.send(f"{current_room}|Meow sent the Pokémon of the day!")

                        elif msg_text.lower().startswith("meow show schedule"):
                            now = datetime.datetime.now()
                            html_schedule = generate_monthly_tour_schedule_html(now.month, now.year, room=current_room)
                            await ws.send(f"{current_room}|/addhtmlbox {html_schedule}")
                        
                        elif msg_text.lower().startswith("meow help"):
                            help_msg = ("Meow commands: 'meow start [tour name]', 'meow show potd', "
                                        "'meow show schedule', 'meow help'")
                            await ws.send(f"{current_room}|Meow, here are the commands! {help_msg}")

                        elif prefix in ('%', '@', '#'):
                            emotion_bank = [
                                ":3", ":3c", ":<", ":c", ";w;", "'w'", "awa", "uwu",
                                "owo", "TwT", ">:(", ">:3", ">:3c", ">:c"
                            ]
                            emotion = random.choice(emotion_bank)
                            await ws.send(f"{current_room}|Meow {emotion}")
                        else:
                            pass
                    if "You cannot have a tournament until" in line:
                        await ws.send(f">{current_room}|There's a tour going on right meow...")

        except Exception as e:
            print(f"Error in message listener: {e}")
            await asyncio.sleep(1)

