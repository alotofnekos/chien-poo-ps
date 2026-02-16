import asyncio
import random
import os
from dotenv import load_dotenv
from pm_handler import handle_pmmessages
from pokepaste import generate_html, get_pokepaste_from_url
from potd import send_potd
import time
import re
from tn import generate_monthly_tour_schedule_html,get_next_tournight, get_current_tour_schedule, cancel_next_tour, is_tour_cancelled, uncancel_last_cancelled
from tour_creator import get_tour_bans_for_html, add_tour_bans, remove_tour_bans, get_tour_info, build_tour_code, get_all_tours   
import datetime
from pm_handler import get_random_cat_url
from set_handler import parse_command_and_get_sets
load_dotenv()
from db import save_tournament_results, get_leaderboard_html,process_tourlogs, add_points
USERNAME = os.getenv("PS_USERNAME")
CURRENT_TOUR_EXISTS = {}  
TRACK_OFFICIAL_TOUR = {}  
TOURNAMENT_STATE = {}     
PROCESSED_MESSAGES = {}
async def listen_for_messages(ws):
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
                    
                    await handle_tournament_message(line, current_room,ws)
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

                    if "meow" in msg_text.lower() and prefix in ('+','%', '@', '#', '~'):
                        print(f"Received from {user} in {current_room}: {msg_text}")
                        if msg_text.lower().startswith("meow official"):
                            if CURRENT_TOUR_EXISTS.get(current_room, False):
                                await ws.send(f"{current_room}|Tracking official tour in {current_room}, Nya >:3")
                                TRACK_OFFICIAL_TOUR[current_room] = True
                                TOURNAMENT_STATE[current_room] = []
                            else:
                                await ws.send(f"{current_room}| Nyo active tournament in {current_room}, ignoring 'meow official'. Stop bullying >:(")
                        elif msg_text.lower().startswith("meow cancel next tn"):
                            nx_schedule = get_current_tour_schedule(current_room)
                            next_tour = get_next_tournight(nx_schedule)
                                
                            if next_tour is None:
                                await ws.send(f"{current_room}|Meow, there are no scheduled tournights for this room ;w;")
                            else:
                                cancel_success = cancel_next_tour(current_room)
                                if cancel_success:
                                    await ws.send(f"{current_room}|Meow cancelled the next tournight: {next_tour['name'].title()} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4).")
                                else:
                                     await ws.send(f"{current_room}|Meow, failed to cancel the next tournight. It may have already started or there was an error ;w;")

                        elif msg_text.lower().startswith("meow uncancel next tn"):
                            nx_schedule = get_current_tour_schedule(current_room)
                            next_tour = get_next_tournight(nx_schedule)
                            if next_tour is None:
                                await ws.send(f"{current_room}|Meow, there are no scheduled tournights for this room ;w;")
                            else:
                                if not is_tour_cancelled(current_room, next_tour['hour'], next_tour['minute']):
                                    await ws.send(f"{current_room}|Meow, the next tournight isn't cancelled ;w;")
                                else:
                                    uncancel_success = uncancel_last_cancelled(current_room)
                                    if uncancel_success:
                                        await ws.send(f"{current_room}|Meow got it! Will do this next tournight: {next_tour['name'].title()} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4)! >:3")
                                    else:
                                        await ws.send(f"{current_room}|Meow, failed to uncancel the next tournight. Maybe the time already passed or something, meowdk ;w;")

                        elif msg_text.lower().startswith("meow unofficial"):
                            await ws.send(f"{current_room}| Meow stopped tracking this tour in {current_room}")
                            TRACK_OFFICIAL_TOUR[current_room] = False
                            TOURNAMENT_STATE.pop(current_room, None)

                        elif msg_text.lower().startswith("meow start"):
                            tour_name = msg_text[len("meow start"):].strip()
                            
                            if not tour_name:
                                await ws.send(f"{current_room}|Meow, please specify a tour to start! Usage: meow start <tourname>")
                            else:
                                tour_code = build_tour_code(current_room, tour_name.lower())
                                tour_info = get_tour_info(current_room, tour_name.lower())
                                
                                if not tour_code or not tour_info:
                                    available_tours = get_all_tours(current_room)
                                    
                                    if available_tours:
                                        tours_list = ", ".join(available_tours)
                                        await ws.send(f"{current_room}|Meow couldn't find a tour called '{tour_name}'! Available tours: {tours_list}")
                                    else:
                                        await ws.send(f"{current_room}|Meow couldn't find a tour called '{tour_name}' and I can't find any available tours either... ;w;")
                                else:
                                    # Send tour commands
                                    await ws.send(f"{current_room}|/tour end")
                                    await asyncio.sleep(2)
                                    
                                    tour_commands = tour_code.split('\n')
                                    for command in tour_commands:
                                        await ws.send(f"{current_room}|{command.strip()}")
                                    
                                    # Set tour name
                                    display_name = tour_info.get('tour_name') or tour_name.replace('-', ' ').title()
                                    if "Monotype" in display_name or "Monothreat" in display_name or "NatDex" or "National Dex OU" in display_name:
                                        await ws.send(f"{current_room}|/tour name {display_name}")
                                    else:
                                        await ws.send(f"{current_room}|/tour name {display_name} {current_room.title()}")
                                    
                                    await ws.send(f"{current_room}|/tour scouting off")
                                    await ws.send(f"{current_room}|Meow started the {display_name} tour! >:3")
                        elif msg_text.lower().startswith("meow show potd"):
                            await send_potd(ws, current_room)
                        elif msg_text.lower().startswith("meow show tours"):
                            tours = get_all_tours(current_room)
                            if tours:
                                tours_list = ", ".join(tours)
                                await ws.send(f"{current_room}|Meow, the available tours are: {tours_list} >:3")
                            else:
                                await ws.send(f"{current_room}|Meow, there are no available tours in {current_room} ;w;")
                        elif msg_text.lower().startswith("meow show bans"):
                            tn = msg_text[len("meow show bans"):].strip()
                            message = get_tour_bans_for_html(current_room, tn)
                            if message is None:
                                await ws.send(f"{current_room}|Meow, no bans found for {tn} in {current_room}. Maybe it doesnt exist? ;w;")
                            else:
                                await ws.send(f"{current_room}|/addhtmlbox {message}")
                        elif msg_text.lower().startswith("meow show set"):
                            msg_id = f"{current_room}:{user}:{ts}:{msg_text}"
                            
                            if msg_id in PROCESSED_MESSAGES:
                                continue
                            
                            PROCESSED_MESSAGES[msg_id] = time.time()
                            
                            # Clean old entries without reassignment
                            current_time = time.time()
                            old_keys = [k for k, v in PROCESSED_MESSAGES.items() if current_time - v >= 60]
                            for k in old_keys:
                                del PROCESSED_MESSAGES[k]
                            
                            sets_output = parse_command_and_get_sets(msg_text, current_room)
                            if sets_output:
                                # Send each set as a separate message
                                for set_str in sets_output:
                                    await ws.send(f"{current_room}|/addhtmlbox {set_str}")
                                
                                await ws.send(f"{current_room}|Meow sent the set info!")
                            else:
                                await ws.send(f"{current_room}|Meow couldn't find any sets for this mon, sorry ;w;. Usage: meow show set <pokemon> [format] (type/item/move [optional])")
                        elif msg_text.lower().startswith("meow show lb"):
                            await ws.send(f"{current_room}|/addhtmlbox {get_leaderboard_html(current_room)}")

                        elif msg_text.lower().startswith("meow show schedule"):
                            now = datetime.datetime.now()
                            html_schedule = generate_monthly_tour_schedule_html(now.month, now.year, room=current_room)
                            
                            if html_schedule and "Invalid room" not in html_schedule:
                                await ws.send(f"{current_room}|/addhtmlbox {html_schedule}")
                            else:
                                await ws.send(f"{current_room}|Meow, this room doesn't have scheduled tournights ;w;")
                        
                        elif msg_text.lower().startswith("meow who made you"):
                            await ws.send(f"{current_room}|Meow was made by Neko >:3")    
                        
                        elif msg_text.lower().startswith("meow next tn"):
                            nx_schedule = get_current_tour_schedule(current_room)
                            next_tour = get_next_tournight(nx_schedule)
                            
                            if next_tour is None:
                                await ws.send(f"{current_room}|Meow, there are no scheduled tournights for this room ;w;")
                            else:
                                await ws.send(f"{current_room}|Meow, the next tournight is {next_tour['name'].title()} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4). Its in {next_tour['minutes_until']} minute(s)!")
                        elif msg_text.lower().startswith("meow what time"):
                            now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=4)
                            await ws.send(f"{current_room}|Meow, the current time is {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT-4)")
                        elif msg_text.lower().startswith("meow help"):
                            help_msg = ("'meow start [tour name]', 'meow show potd', "
                                        "'meow show schedule', 'meow help', 'meow show cat', 'meow uptime', 'meow next tn',"
                                        "'meow show set', 'meow show bans [tour name]', 'meow show tours', 'meow show paste [pokepaste]', "
                                        "'meow cancel next tn', 'meow uncancel next tn', 'meow add rule [tour name] [bans]', 'meow remove rule [tour name] [bans]'")
                            await ws.send(f"{current_room}|Meow, here are the commands! {help_msg}")
                        elif msg_text.lower().startswith("meow show paste") or msg_text.lower().startswith("meow show pokepaste"):
                            url = msg_text.strip().split()[3]
                            try:
                                paste_content = get_pokepaste_from_url(url, strip_nicknames=True, strip_title=False)
                                html = generate_html(paste_content)
                                await ws.send(f"{current_room}|/addhtmlbox {html}")

                            except Exception as e:
                                await ws.send(f"{current_room}| Meow couldn't fetch the pokepaste :<")

                        elif prefix in ('%', '@', '#', '~'):
                            if msg_text.lower().startswith("meow add rule"):
                                if prefix not in ('#'):
                                    await ws.send(f"{current_room}|Meow, only room owners can add bans >:3c")
                                else:
                                    parts = msg_text[len("meow add rule"):].strip().split(None, 1)
                                    
                                    if len(parts) < 2:
                                        await ws.send(f"{current_room}|Meow, please use: meow add rule <tourname> <bans>. Please note that meow can't discern bans from unbans, so add it as it appears in /tour rules (i.e. -Flutter Mane, +Chien-Pao ) :<")
                                    else:
                                        tour_name = parts[0].lower()
                                        bans_str = parts[1].lower()
                                        
                                        # Add the bans
                                        added = add_tour_bans(current_room, tour_name, bans_str)
                                        
                                        if added:
                                            await ws.send(f"{current_room}|Meow added these rule(s): {', '.join(added)} to {tour_name} >:3")
                                        else:
                                            await ws.send(f"{current_room}|Meow, those rules already exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")
                            elif msg_text.lower().startswith("meow remove rule"):
                                if prefix not in ('#'):
                                    await ws.send(f"{current_room}|Meow, only room owners can remove rules ;w;")
                                else:
                                    parts = msg_text[len("meow remove rule"):].strip().split(None, 1)
                                    
                                    if len(parts) < 2:
                                        await ws.send(f"{current_room}|Meow, please use: meow remove rule <tourname> <bans> >:c")
                                    else:
                                        tour_name = parts[0].lower()
                                        bans_str = parts[1].lower()
                                        
                                        removed = remove_tour_bans(current_room, tour_name, bans_str)
                                        
                                        if removed:
                                            await ws.send(f"{current_room}|Meow removed ban(s): {', '.join(removed)} from {tour_name} >:3")
                                        else:
                                            await ws.send(f"{current_room}|Meow, those rules don't exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")
                            elif msg_text.lower().startswith("meow show cat"):
                                cat = await get_random_cat_url()
                                print(f"Fetched cat URL: {cat}")
                                if cat:
                                    await ws.send(f'{current_room}|/addhtmlbox <img src="{cat}" height="0" width="0" style="max-height: 350px; height: auto; width: auto;">')
                                else:
                                    await ws.send(f"{current_room}|Meow, couldn't find a cat right meow ;w;")
                            elif msg_text.lower().startswith("meow uptime"):
                                uptime_msg = get_uptime(listener_start_time)
                                await ws.send(f"{current_room}|{uptime_msg}")
                            
                            elif msg_text.lower().startswith("meow add points"):
                                try:
                                    # Strip command part
                                    args = msg_text[len("meow add points"):].strip()

                                    # Expect format: "username, points"
                                    if "," not in args:
                                        await ws.send(f"{current_room}|Invalid format meow. Use: meow add points <username>, <points> >:(")
                                        raise ValueError(f"{current_room}| Invalid format. Use: meow add points <username>, <points>")

                                    username, pts_str = [a.strip() for a in args.split(",", 1)]
                                    points = int(pts_str)
                                    new_total = add_points(current_room, username, points)

                                    await ws.send(f"{current_room}| Added {points} points to {username} in {current_room}. New total: {new_total}")
                                except Exception as e:
                                    await ws.send(f"{current_room}| Error adding points: {e} ;w;")
                            elif re.search(r"\bmeow\b", msg_text, re.IGNORECASE):
                                # Generic meow response if no specific command matched
                                emotion_bank = [
                                    ":3", ":3c", ":<", ":c", ";w;", "'w'", "awa", "uwu",
                                    "owo", "TwT", ">:(", ">:3", ">:3c", ">:c", "Mrrp", 
                                    "Meoo", "^w^", "Mrao"
                                ]
                                emotion = random.choice(emotion_bank)
                                await ws.send(f"{current_room}|Meow {emotion}")
                        elif re.search(r"\bmeow\b", msg_text, re.IGNORECASE):
                            # Generic meow response for voice users if no specific command matched
                            emotion_bank = [
                                ":3", ":3c", ":<", ":c", ";w;", "'w'", "awa", "uwu",
                                "owo", "TwT", ">:(", ">:3", ">:3c", ">:c", "Mrrp", 
                                "Meoo", "^w^", "Mrao"
                            ]
                            emotion = random.choice(emotion_bank)
                            await ws.send(f"{current_room}|Meow {emotion}")
                    if "You cannot have a tournament until" in line:
                        await ws.send(f">{current_room}|There's a tour going on right meow...")
                    
        except Exception as e:
            print(f"Error in message listener: {e}")
            raise

async def handle_tournament_message(line: str, room: str,ws):
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
                save_tournament_results(room, logs)
                await ws.send(f"{room}|/addhtmlbox {get_leaderboard_html(room)}")
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
