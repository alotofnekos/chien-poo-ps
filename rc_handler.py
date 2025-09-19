import asyncio
import random
import os
from dotenv import load_dotenv
from pm_handler import handle_pmmessages
from potd import send_potd
import time
import re
from tn import generate_monthly_tour_schedule_html,get_next_tournight, get_current_tour_schedule
import datetime
from pm_handler import get_random_cat_url
load_dotenv()
from db import save_tournament_results, get_leaderboard_html,process_tourlogs
USERNAME = os.getenv("PS_USERNAME")
CURRENT_TOUR_EXISTS = {}  
TRACK_OFFICIAL_TOUR = {}  
TOURNAMENT_STATE = {}     

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
                
                elif line.startswith("|tournament|") and current_room:
                    # Try to grab the first number in the line as a timestamp
                    match = re.search(r"\d+", line)
                    ts = int(match.group()) if match else 0

                    if ts > listener_start_time:
                        await handle_tournament_message(line, current_room)

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

                    if "meow" in msg_text.lower() and prefix in ('+','%', '@', '#', '~', '*'):
                        print(f"Received from {user} in {current_room}: {msg_text}")

                        TOUR_COMMANDS = room_commands_map.get(current_room, {})
                        if msg_text.lower().startswith("meow official"):
                            if CURRENT_TOUR_EXISTS.get(current_room, False):
                                await ws.send(f"{current_room}|Tracking official tour in {current_room}, Nya >:3")
                                TRACK_OFFICIAL_TOUR[current_room] = True
                                TOURNAMENT_STATE[current_room] = []
                            else:
                                await ws.send(f"{current_room}| Nyo active tournament in {current_room}, ignoring 'meow official'. Stop bullying >:(")

                        elif msg_text.lower().startswith("meow unofficial"):
                            await ws.send(f"{current_room}| Meow stopped tracking this tour in {current_room}")
                            TRACK_OFFICIAL_TOUR[current_room] = False
                            TOURNAMENT_STATE.pop(current_room, None)

                        elif msg_text.lower().startswith("meow start"):
                            tour_name = msg_text[len("meow start"):].strip()

                            lower_map = {k.lower(): k for k in TOUR_COMMANDS.keys()}
                            if tour_name.lower() in lower_map:
                                lookup_key = lower_map[tour_name.lower()]
                                tour_commands = TOUR_COMMANDS[lookup_key].split('\n')
                                for command in tour_commands:
                                    await ws.send(f"{current_room}|{command.strip()}")
                                if "Monotype" in lookup_key or "Monothreat" in lookup_key:
                                    await ws.send(f"{current_room}|/tour name {lookup_key}")
                                else:
                                    await ws.send(f"{current_room}|/tour name {lookup_key} {current_room.title()}")
                            else:
                                available = ", ".join(TOUR_COMMANDS.keys())
                                await ws.send(f"{current_room}|Meow couldn’t find '{tour_name}'. "
                                              f"Available tours: {available}")

                        elif msg_text.lower().startswith("meow show potd"):
                            await send_potd(ws, current_room)
                        
                        elif msg_text.lower().startswith("meow show lb"):
                            await ws.send(f"{current_room}|/addhtmlbox {get_leaderboard_html(current_room)}")

                        elif msg_text.lower().startswith("meow show schedule"):
                            now = datetime.datetime.now()
                            html_schedule = generate_monthly_tour_schedule_html(now.month, now.year, room=current_room)
                            await ws.send(f"{current_room}|/addhtmlbox {html_schedule}")
                        
                        elif msg_text.lower().startswith("meow who made you"):
                            await ws.send(f"{current_room}|Meow was made by Neko >:3")    
                        
                        elif msg_text.lower().startswith("meow next tn"):
                            nx_schedule = get_current_tour_schedule(current_room)
                            next_tour = get_next_tournight(nx_schedule)
                            await ws.send(f"{current_room}|Meow, the next tournight is {next_tour['name']} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4). Its in {next_tour['minutes_until']} minute(s)!")
                        
                        elif msg_text.lower().startswith("meow help"):
                            help_msg = ("'meow start [tour name]', 'meow show potd', "
                                        "'meow show schedule', 'meow help', 'meow show cat', 'meow uptime', 'meow next tn'")
                            await ws.send(f"{current_room}|Meow, here are the commands! {help_msg}")

                        elif prefix in ('%', '@', '#', '~'):
                            if msg_text.lower().startswith("meow show cat"):
                                cat = await get_random_cat_url()
                                print(f"Fetched cat URL: {cat}")
                                if cat:
                                    await ws.send(f'{current_room}|/addhtmlbox <img src="{cat}" height="0" width="0" style="max-height: 350px; height: auto; width: auto;">')
                                else:
                                    await ws.send(f"{current_room}|Meow, couldn't find a cat right meow ;w;")
                            
                            elif msg_text.lower().startswith("meow uptime"):
                                uptime_msg = get_uptime(listener_start_time)
                                await ws.send(f"{current_room}|{uptime_msg}")
                            
                            elif re.search(r"\bmeow\b", msg_text, re.IGNORECASE):
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
            raise

async def handle_tournament_message(line: str, room: str):
    """Logs tournament lines only, between create and end. Processes results if official."""
    if not line.startswith("|tournament|"):
        return  # ignore all non-tournament lines

    # --- Tournament created ---
    if "|tournament|create|" in line:
        if CURRENT_TOUR_EXISTS.get(room, False):
            # Failsafe: reset old unfinished tournament
            print(f"[{room}] Warning: New tournament created before previous ended. Resetting state.")

        CURRENT_TOUR_EXISTS[room] = True
        TOURNAMENT_STATE[room] = [line]  # reset log storage
        print(f"[{room}] Tournament created, logging started.")
        return

    # --- Tournament still active, log lines ---
    if CURRENT_TOUR_EXISTS.get(room, False):
        if room not in TOURNAMENT_STATE:
            TOURNAMENT_STATE[room] = []  # ensure safe init
        TOURNAMENT_STATE[room].append(line)

        # --- Tournament ended ---
        if "|tournament|end|" in line:
            if TRACK_OFFICIAL_TOUR.get(room, False):
                print(f"[{room}] Official tournament ended. Processing results...")
                logs = TOURNAMENT_STATE.pop(room, [])
                results = process_tourlogs(room, logs)
                await save_tournament_results(room, logs)
            else:
                print(f"[{room}] Unofficial tournament ended. Ignoring results.")

            # Always reset flags
            CURRENT_TOUR_EXISTS[room] = False
            TRACK_OFFICIAL_TOUR[room] = False
            print(f"[{room}] Tournament ended, logging stopped.")



def get_uptime(listener_start_time):
    uptime_seconds = time.time() - listener_start_time
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"Meow is up for the last {int(hours)}h(s) {int(minutes)}m(s). Last restart: {datetime.datetime.fromtimestamp(listener_start_time).strftime('%Y-%m-%d %H:%M:%S')}"

