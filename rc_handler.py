import asyncio
import random
import os
from dotenv import load_dotenv
from pm_handler import handle_pmmessages
from pokepaste import generate_html, get_pokepaste_from_url
from potd import send_potd
import time
import re
from tn import generate_monthly_tour_schedule_html,get_next_tournight, get_current_tour_schedule
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
    
    async def handle_meow_command(ws, current_room, user, msg_text, prefix, ts):
        """Dispatch meow commands to appropriate handlers."""
        msg_lower = msg_text.lower()
        
        # Create message ID for deduplication (only for 'show set')
        if "meow show set" in msg_lower:
            msg_id = f"{current_room}:{user}:{ts}:{msg_text}"
            if msg_id in PROCESSED_MESSAGES:
                return
            PROCESSED_MESSAGES[msg_id] = time.time()
            
            # Clean old entries
            current_time = time.time()
            old_keys = [k for k, v in PROCESSED_MESSAGES.items() if current_time - v >= 60]
            for k in old_keys:
                del PROCESSED_MESSAGES[k]
        
        # Command routing based on auth permissions
        if prefix in ('+', '%', '@', '#', '~'):
            if msg_lower.startswith("meow official"):
                await cmd_official_tour(ws, current_room)
            
            elif msg_lower.startswith("meow unofficial"):
                await cmd_unofficial_tour(ws, current_room)
            
            elif msg_lower.startswith("meow start"):
                await cmd_start_tour(ws, current_room, msg_text)
            
            elif msg_lower.startswith("meow show potd"):
                await send_potd(ws, current_room)
            
            elif msg_lower.startswith("meow show tours"):
                await cmd_show_tours(ws, current_room)
            
            elif msg_lower.startswith("meow show bans"):
                await cmd_show_bans(ws, current_room, msg_text)
            
            elif msg_lower.startswith("meow show set"):
                await cmd_show_set(ws, current_room, msg_text)
            
            elif msg_lower.startswith("meow show lb"):
                await ws.send(f"{current_room}|/addhtmlbox {get_leaderboard_html(current_room)}")
            
            elif msg_lower.startswith("meow show schedule"):
                await cmd_show_schedule(ws, current_room)
            
            elif msg_lower.startswith("meow who made you"):
                await ws.send(f"{current_room}|Meow was made by Neko >:3")
            
            elif msg_lower.startswith("meow next tn"):
                await cmd_next_tournight(ws, current_room)
            
            elif msg_lower.startswith("meow what time"):
                await cmd_what_time(ws, current_room)
            
            elif msg_lower.startswith("meow help"):
                await cmd_help(ws, current_room)
            
            elif msg_lower.startswith("meow show paste") or msg_lower.startswith("meow show pokepaste"):
                await cmd_show_paste(ws, current_room, msg_text)
            
            # Driver+ commands (% and above)
            elif prefix in ('%', '@', '#', '~'):
                if msg_lower.startswith("meow show cat"):
                    await cmd_show_cat(ws, current_room)
                
                elif msg_lower.startswith("meow uptime"):
                    await cmd_uptime(ws, current_room, listener_start_time)
                
                elif msg_lower.startswith("meow add points"):
                    await cmd_add_points(ws, current_room, msg_text)
                
                # Room owner only commands (#)
                elif prefix in ('#',):
                    if msg_lower.startswith("meow add rule"):
                        await cmd_add_rule(ws, current_room, msg_text)
                    
                    elif msg_lower.startswith("meow remove rule"):
                        await cmd_remove_rule(ws, current_room, msg_text)
                
                # Generic meow response 
                elif re.search(r"\bmeow\b", msg_lower, re.IGNORECASE):
                    await cmd_meow(ws, current_room)
    
    # Main listener loop
    while True:
        try:
            raw = await ws.recv()
            lines = raw.split("\n")

            current_room = None
            for line in lines:
                if not line:
                    continue

                # Room designation
                if line.startswith(">"):
                    current_room = line[1:].strip()
                    continue

                # Private messages
                if line.startswith("|pm|"):
                    await handle_pmmessages(ws, USERNAME, line)
                
                # Tournament messages
                elif line.startswith("|tournament|") and current_room:
                    await handle_tournament_message(line, current_room, ws)
                
                # Chat messages
                elif line.startswith("|c:|") and current_room:
                    parts = line.split("|")
                    if len(parts) < 5:
                        continue
                    
                    ts = int(parts[2].strip())
                    user = parts[3].strip()
                    msg_text = parts[4].strip()
                    prefix = user[:1]
                    
                    # Skip old messages
                    if ts < listener_start_time:
                        continue

                    # Handle meow commands
                    if "meow" in msg_text.lower() and prefix in ('+', '%', '@', '#', '~'):
                        print(f"Received from {user} in {current_room}: {msg_text}")
                        await handle_meow_command(ws, current_room, user, msg_text, prefix, ts)
                
                # Tour cooldown message
                if "You cannot have a tournament until" in line:
                    await ws.send(f">{current_room}|There's a tour going on right meow...")
        
        except Exception as e:
            print(f"Error in message listener: {e}")
            continue


# Command handler functions
async def cmd_official_tour(ws, room):
    """Handle 'meow official' command."""
    if CURRENT_TOUR_EXISTS.get(room, False):
        await ws.send(f"{room}|Tracking official tour in {room}, Nya >:3")
        TRACK_OFFICIAL_TOUR[room] = True
        TOURNAMENT_STATE[room] = []
    else:
        await ws.send(f"{room}| Nyo active tournament in {room}, ignoring 'meow official'. Stop bullying >:(")


async def cmd_unofficial_tour(ws, room):
    """Handle 'meow unofficial' command."""
    await ws.send(f"{room}| Meow stopped tracking this tour in {room}")
    TRACK_OFFICIAL_TOUR[room] = False
    TOURNAMENT_STATE.pop(room, None)


async def cmd_start_tour(ws, room, msg_text):
    """Handle 'meow start <tourname>' command."""
    tour_name = msg_text[len("meow start"):].strip()
    
    if not tour_name:
        await ws.send(f"{room}|Meow, please specify a tour to start! Usage: meow start <tourname>")
        return
    
    tour_code = build_tour_code(room, tour_name.lower())
    tour_info = get_tour_info(room, tour_name.lower())
    
    if not tour_code or not tour_info:
        available_tours = get_all_tours(room)
        
        if available_tours:
            tours_list = ", ".join(available_tours)
            await ws.send(f"{room}|Meow couldn't find a tour called '{tour_name}'! Available tours: {tours_list}")
        else:
            await ws.send(f"{room}|Meow couldn't find a tour called '{tour_name}' and I can't find any available tours either... ;w;")
        return
    
    # Send tour commands
    await ws.send(f"{room}|/tour end")
    await asyncio.sleep(2)
    
    tour_commands = tour_code.split('\n')
    for command in tour_commands:
        await ws.send(f"{room}|{command.strip()}")
    
    # Set tour name
    display_name = tour_info.get('tour_name') or tour_name.replace('-', ' ').title()
    if "Monotype" in display_name or "Monothreat" in display_name or "NatDex" in display_name:
        await ws.send(f"{room}|/tour name {display_name}")
    else:
        await ws.send(f"{room}|/tour name {display_name} {room.title()}")
    
    await ws.send(f"{room}|/tour scouting off")
    await ws.send(f"{room}|Meow started the {display_name} tour! >:3")


async def cmd_show_tours(ws, room):
    """Handle 'meow show tours' command."""
    tours = get_all_tours(room)
    if tours:
        tours_list = ", ".join(tours)
        await ws.send(f"{room}|Meow, the available tours are: {tours_list} >:3")
    else:
        await ws.send(f"{room}|Meow, there are no available tours in {room} ;w;")


async def cmd_show_bans(ws, room, msg_text):
    """Handle 'meow show bans <tourname>' command."""
    tn = msg_text[len("meow show bans"):].strip()
    message = get_tour_bans_for_html(room, tn)
    
    if message is None:
        await ws.send(f"{room}|Meow, no bans found for {tn} in {room}. Maybe it doesnt exist? ;w;")
    else:
        await ws.send(f"{room}|/addhtmlbox {message}")


async def cmd_show_set(ws, room, msg_text):
    """Handle 'meow show set <pokemon> [format]' command."""
    sets_output = parse_command_and_get_sets(msg_text, room)
    
    if sets_output:
        for set_str in sets_output:
            await ws.send(f"{room}|/addhtmlbox {set_str}")
        await ws.send(f"{room}|Meow sent the set info!")
    else:
        await ws.send(f"{room}|Meow couldn't find any sets for this mon, sorry ;w;. Usage: meow show set <pokemon> [format] (type/item/move [optional])")


async def cmd_show_schedule(ws, room):
    """Handle 'meow show schedule' command."""
    now = datetime.datetime.now()
    html_schedule = generate_monthly_tour_schedule_html(now.month, now.year, room=room)
    
    if html_schedule and "Invalid room" not in html_schedule:
        await ws.send(f"{room}|/addhtmlbox {html_schedule}")
    else:
        await ws.send(f"{room}|Meow, this room doesn't have scheduled tournights ;w;")


async def cmd_next_tournight(ws, room):
    """Handle 'meow next tn' command."""
    nx_schedule = get_current_tour_schedule(room)
    next_tour = get_next_tournight(nx_schedule)
    
    if next_tour is None:
        await ws.send(f"{room}|Meow, there are no scheduled tournights for this room ;w;")
    else:
        await ws.send(f"{room}|Meow, the next tournight is {next_tour['name'].title()} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4). Its in {next_tour['minutes_until']} minute(s)!")


async def cmd_what_time(ws, room):
    """Handle 'meow what time' command."""
    now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=4)
    await ws.send(f"{room}|Meow, the current time is {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT-4)")


async def cmd_help(ws, room):
    """Handle 'meow help' command."""
    help_msg = ("'meow start [tour name]', 'meow show potd', "
                "'meow show schedule', 'meow help', 'meow show cat', 'meow uptime', "
                "'meow next tn','meow show set', 'meow show bans [tour name]', 'meow show tours', 'meow show paste [pokepaste]', 'meow add/remove rule [tourname] [bans]'. ")
    await ws.send(f"{room}|Meow, here are the commands! {help_msg}")

async def cmd_show_paste(ws, room, msg_text):
    """
    Handle 'meow show pokepaste <url>' command.
    """
    # Extract URL (4th word)
    url = msg_text.strip().split()[3]

    try:
        # Fetch the Pokepaste content
        paste_content = get_pokepaste_from_url(url, strip_nicknames=True, strip_title=False)

        # Generate HTML from the content
        html = generate_html(paste_content)

        # Send HTML to the room
        await ws.send(f"{room}|/addhtmlbox {html}")

    except Exception as e:
        await ws.send(f"{room}|Error fetching or displaying Pokepaste: {e}")


async def cmd_show_cat(ws, room):
    """Handle 'meow show cat' command"""
    cat = await get_random_cat_url()
    print(f"Fetched cat URL: {cat}")
    
    if cat:
        await ws.send(f'{room}|/addhtmlbox <img src="{cat}" height="0" width="0" style="max-height: 350px; height: auto; width: auto;">')
    else:
        await ws.send(f"{room}|Meow, couldn't find a cat right meow ;w;")


async def cmd_uptime(ws, room, listener_start_time):
    """Handle 'meow uptime' command (mod only)."""
    uptime_msg = get_uptime(listener_start_time)
    await ws.send(f"{room}|{uptime_msg}")


async def cmd_add_points(ws, room, msg_text):
    """Handle 'meow add points <username>, <points>' command (mod only)."""
    try:
        args = msg_text[len("meow add points"):].strip()

        if "," not in args:
            await ws.send(f"{room}|Invalid format meow. Use: meow add points <username>, <points> >:(")
            return

        username, pts_str = [a.strip() for a in args.split(",", 1)]
        points = int(pts_str)

        new_total = add_points(room, username, points)
        await ws.send(f"{room}| Added {points} points to {username} in {room}. New total: {new_total}")
    
    except Exception as e:
        await ws.send(f"{room}| Error adding points: {e} ;w;")


async def cmd_add_rule(ws, room, msg_text):
    """Handle 'meow add rule <tourname> <bans>' command (room owner only)."""
    parts = msg_text[len("meow add rule"):].strip().split(None, 1)
    
    if len(parts) < 2:
        await ws.send(f"{room}|Meow, please use: meow add rule <tourname> <bans>. Please note that meow can't discern bans from unbans, so add it as it appears in /tour rules (i.e. -Flutter Mane, +Chien-Pao ) :<")
        return
    
    tour_name = parts[0].lower()
    bans_str = parts[1].lower()
    
    added = add_tour_bans(room, tour_name, bans_str)
    
    if added:
        await ws.send(f"{room}|Meow added these rule(s): {', '.join(added)} to {tour_name} >:3")
    else:
        await ws.send(f"{room}|Meow, those rules already exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")


async def cmd_remove_rule(ws, room, msg_text):
    """Handle 'meow remove rule <tourname> <bans>' command (room owner only)."""
    parts = msg_text[len("meow remove rule"):].strip().split(None, 1)
    
    if len(parts) < 2:
        await ws.send(f"{room}|Meow, please use: meow remove rule <tourname> <bans> >:c")
        return
    
    tour_name = parts[0].lower()
    bans_str = parts[1].lower()
    
    removed = remove_tour_bans(room, tour_name, bans_str)
    
    if removed:
        await ws.send(f"{room}|Meow removed ban(s): {', '.join(removed)} from {tour_name} >:3")
    else:
        await ws.send(f"{room}|Meow, those rules don't exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")


async def cmd_meow(ws, room):
    """Handle generic 'meow' mentions (mod only)."""
    emotion_bank = [
        ":3", ":3c", ":<", ":c", ";w;", "'w'", "awa", "uwu",
        "owo", "TwT", ">:(", ">:3", ">:3c", ">:c"
    ]
    emotion = random.choice(emotion_bank)
    await ws.send(f"{room}|Meow {emotion}")


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

