import asyncio
import inspect
import random
import os
from dotenv import load_dotenv
from meow_supabase import supabase
from pm_handler import get_random_cat_saying, handle_pmmessages
from pokepaste import generate_html, get_pokepaste_from_url
from potd import send_potd, room_logs
from collections import deque  
import time
import re
from tn import generate_monthly_tour_schedule_html,get_next_tournight, get_current_tour_schedule, cancel_next_tour, is_tour_cancelled, uncancel_last_cancelled
from tour_creator import add_misc_commands, get_tour_bans_for_html, add_tour_bans, remove_misc_commands, remove_tour_bans, get_tour_info, build_tour_code, get_all_tours, add_tour, remove_tour   
import datetime
from pm_handler import get_random_cat_url, room_schedule_editor
from set_handler import parse_command_and_get_sets
load_dotenv()

from db import save_tournament_results, get_leaderboard_html,process_tourlogs, add_points
USERNAME = os.getenv("PS_USERNAME")
CURRENT_TOUR_EXISTS = {}  
TRACK_OFFICIAL_TOUR = {}  
TOURNAMENT_STATE = {}     
PROCESSED_MESSAGES = {}

def record_meow(room, user, msg_text):
    """Record a meow log in the database."""
    try:
        supabase.rpc('add_meow_log', {
            'p_username': user,
            'p_content': msg_text,
            'p_room': room
        }).execute()
        print(f"Recorded meow from {user} in {room}")
    except Exception as e:
        print(f"Failed to record meow: {e}")

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
                    # Rolling buffer for Potd
                    if current_room not in room_logs:
                        room_logs[current_room] = deque(maxlen=20)
                    room_logs[current_room].append(msg_text)
                    prefix = user[:1]
                    if ts < listener_start_time:
                        continue

                    if "meow" in msg_text.lower() and prefix in ('+','%', '@', '#', '~'):
                        record_meow(current_room, user, msg_text);
                        print(f"Received from {user} in {current_room}: {msg_text}")
                        if msg_text.lower().startswith("meow official"):
                            if CURRENT_TOUR_EXISTS.get(current_room, False):
                                await ws.send(f"{current_room}|Tracking official tour in {current_room}, Nya >:3")
                                TRACK_OFFICIAL_TOUR[current_room] = True
                                TOURNAMENT_STATE[current_room] = []
                            else:
                                await ws.send(f"{current_room}| Nyo active tournament in {current_room}, ignoring 'meow official'. Stop bullying >:(")
                        elif msg_text.lower().startswith("meow cancel next tn"):
                            await cancel_next_tn(current_room, ws)

                        elif msg_text.lower().startswith("meow uncancel next tn"):
                            await uncancel_next_tn(current_room, ws)

                        elif msg_text.lower().startswith("meow unofficial"):
                            await ws.send(f"{current_room}| Meow stopped tracking this tour in {current_room}")
                            TRACK_OFFICIAL_TOUR[current_room] = False
                            TOURNAMENT_STATE.pop(current_room, None)
                        elif msg_text.lower().startswith("meow diagnostic"):
                            await meow_diagnostic(current_room, ws)
                        elif msg_text.lower().startswith("meow start"):
                            await start_tour(msg_text, current_room, ws)

                        elif msg_text.lower().startswith("meow show potd"):
                            await send_potd(ws, current_room)

                        elif msg_text.lower().startswith("meow show tours"):
                            tours = get_all_tours(current_room)
                            if tours:
                                tours_list = ", ".join(tours)
                                await ws.send(f"{current_room}|Meow, the available tours are: {tours_list} >:3")
                            else:
                                await ws.send(f"{current_room}|Meow, there are no available tours in {current_room} ;w;")

                        elif msg_text.lower().startswith("meow show rules"):
                            tn = msg_text[len("meow show rules"):].strip()
                            message = get_tour_bans_for_html(current_room, tn)
                            if message is None:
                                await ws.send(f"{current_room}|Meow, no bans found for {tn} in {current_room}. Maybe it doesnt exist? ;w;")
                            else:
                                await ws.send(f"{current_room}|/addhtmlbox {message}")

                        elif msg_text.lower().startswith("meow show set"):
                            await show_set(current_room, user, ts, msg_text, ws)

                        elif msg_text.lower().startswith("meow show lb"):
                            await ws.send(f"{current_room}|/addhtmlbox {get_leaderboard_html(current_room)}")

                        elif msg_text.lower().startswith("meow show schedule"):
                            now = datetime.datetime.now()
                            html_schedule = generate_monthly_tour_schedule_html(now.month, now.year, room=current_room)
                            if html_schedule and "Invalid room" not in html_schedule and "No schedule found" not in html_schedule:
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
                                minutes = next_tour['minutes_until']
                                # Convert minutes into a nicer format
                                if minutes >= 1440:  # 1 day+
                                    days = minutes // 1440
                                    hours = (minutes % 1440) // 60
                                    time_str = f"{days} day(s) and {hours} hour(s)"
                                elif minutes >= 120:  # 2 hours+
                                    hours = minutes // 60
                                    time_str = f"{hours} hour(s)"
                                else:
                                    time_str = f"{minutes} minute(s)"
                                await ws.send(f"{current_room}|Meow, the next tournight is {next_tour['name'].title()} at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4). Its in around {time_str}! >:3")
                        elif msg_text.lower().startswith("meow what time"):
                            now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=4)
                            await ws.send(f"{current_room}|Meow, the current time is {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT-4)")
                        elif msg_text.lower().startswith("meow help"):
                            help_msg = ("'meow start [tour name]', 'meow show potd', "
                                        "'meow show schedule', 'meow help', 'meow show cat', 'meow say [message]', 'meow uptime', 'meow next tn',"
                                        "'meow show set', 'meow show rules [tour name]', 'meow show tours', 'meow show paste [pokepaste]', "
                                        "'meow cancel next tn', 'meow uncancel next tn', 'meow add rule [tour name] [bans]', 'meow remove rule [tour name] [bans]', "
                                        "'meow add tour [internalname] using [tour type] [as name]', 'meow remove tour [internalname]', 'meow add misc command [tour name] [commands]', "
                                        "'meow remove misc command [tour name] [commands]'")
                            await ws.send(f"{current_room}|Meow, here are the commands! {help_msg}")
                        elif msg_text.lower().startswith("meow show paste") or msg_text.lower().startswith("meow show pokepaste"):
                            url = msg_text.strip().split()[3]
                            try:
                                paste_content = get_pokepaste_from_url(url, strip_nicknames=True, strip_title=False)
                                html = generate_html(paste_content)
                                await ws.send(f"{current_room}|/addhtmlbox {html}")

                            except Exception as e:
                                await ws.send(f"{current_room}| Meow couldn't fetch the pokepaste :<")
                        elif msg_text.lower().startswith("meow show cat"):
                            cat = await get_random_cat_url()
                            print(f"Fetched cat URL: {cat}")
                            if cat:
                                await ws.send(f'{current_room}|/addhtmlbox <img src="{cat}" height="0" width="0" style="max-height: 350px; height: auto; width: auto;">')
                            else:
                                await ws.send(f"{current_room}|Meow, couldn't find a cat right meow ;w;")
                        elif msg_text.lower().startswith("meow say"):
                            say_message = msg_text[len("meow say"):].strip()
                            if say_message:
                                catmessage = await get_random_cat_saying(say_message)
                                if catmessage.startswith("Meow! I dont think I should say that"):
                                    await ws.send(f"{current_room}|{catmessage}")
                                else:
                                    await ws.send(f'{current_room}|/addhtmlbox <img src="{catmessage}" height="0" width="0" style="max-height: 350px; height: auto; width: auto;">')
                            else:
                                await ws.send(f"{current_room}|Meow, you didn't tell me what to say! Usage: meow say <message> >:3")
                        elif prefix in ('%', '@', '#', '~'):
                            if msg_text.lower().startswith("meow add tour"):
                                if prefix not in ('#'):
                                    await ws.send(f"{current_room}|Meow, only room owners can add tours >:3c")
                                else:
                                    await meow_add_tour(msg_text, current_room, ws)
                            if msg_text.lower().startswith("meow remove tour"):
                                if prefix not in ('#'):
                                    await ws.send(f"{current_room}|Meow, only room owners can remove tours >:c")
                                else:
                                    await meow_remove_tour(msg_text, current_room, ws)
                            if msg_text.lower() == "meow edit schedule":
                                await room_schedule_editor(current_room, user, prefix, ws)
                            if msg_text.lower().startswith("meow add rule"):
                                if prefix not in ('#', '@'):
                                    await ws.send(f"{current_room}|Meow, only room owners and mods can add bans >:3c")
                                else:
                                    await meow_add_rule(msg_text, current_room, ws)
                            elif msg_text.lower().startswith("meow remove rule"):
                                if prefix not in ('#', '@'):
                                    await ws.send(f"{current_room}|Meow, only room owners and mods can remove rules ;w;")
                                else:
                                    await meow_remove_rule(msg_text, current_room, ws)
                            elif msg_text.lower().startswith("meow add misc command"):
                                if prefix not in ('@','#'):
                                    await ws.send(f"{current_room}|Meow, only room owners and mods can add misc commands >:3c")
                                else:
                                    await meow_add_misc_command(msg_text, current_room, ws)
                            elif msg_text.lower().startswith("meow remove misc command"):
                                if prefix not in ('@','#'):
                                    await ws.send(f"{current_room}|Meow, only room owners and mods can remove misc commands ;w;")
                                else:
                                    await meow_remove_misc_command(msg_text, current_room, ws)
                            elif msg_text.lower().startswith("meow uptime"):
                                uptime_msg = get_uptime(listener_start_time)
                                await ws.send(f"{current_room}|{uptime_msg}")

                            elif msg_text.lower().startswith("meow add points"):
                                try:
                                    await meow_add_points(msg_text, current_room, ws)
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

async def meow_diagnostic(current_room, ws):
    results = []
    phase1_passed = True

    # --- Phase 1: Check if callable ---
    funcs = [
        ("meow cancel next tn", cancel_next_tn),
        ("meow uncancel next tn", uncancel_next_tn),
        ("meow start", start_tour),
        ("meow show set", show_set),
        ("meow add tour", meow_add_tour),
        ("meow remove tour", meow_remove_tour),
        ("meow add rule", meow_add_rule),
        ("meow remove rule", meow_remove_rule),
        ("meow add misc command", meow_add_misc_command),
        ("meow remove misc command", meow_remove_misc_command),
        ("meow add points", meow_add_points),
    ]

    for label, func in funcs:
        try:
            if callable(func) and inspect.iscoroutinefunction(func):
                results.append(f"[PASS] {label}: OK")
            elif callable(func):
                results.append(f"[WARN] {label}: Found but not async")
                phase1_passed = False
            else:
                results.append(f"[FAIL] {label}: Not callable")
                phase1_passed = False
        except Exception as e:
            results.append(f"[FAIL] {label}: {e}")
            phase1_passed = False

    if not phase1_passed:
        results.append(f"[SKIP] Functional tests skipped due to phase 1 failures")
    else:
        results.append(f"--- Functional Tests ---")

        # Test: meow add tour / meow remove tour
        try:
            dummy_tour = "_diag_test_tour"
            added = add_tour(current_room, dummy_tour, "gen9ou", "Diagnostic Test Tour")
            if added:
                removed = remove_tour(current_room, dummy_tour)
                if removed:
                    results.append(f"[PASS] meow add tour / meow remove tour: OK")
                else:
                    results.append(f"[WARN] meow add tour / meow remove tour: Added but failed to remove, clean up manually")
            else:
                results.append(f"[WARN] meow add tour / meow remove tour: Could not create throwaway tour")
        except Exception as e:
            results.append(f"[FAIL] meow add tour / meow remove tour: {e}")

        # Test: meow add rule / meow remove rule (uses throwaway tour)
        try:
            dummy_tour = "_diag_test_tour"
            added_tour = add_tour(current_room, dummy_tour, "gen9ou", "Diagnostic Test Tour")
            if added_tour:
                added = add_tour_bans(current_room, dummy_tour, "-_diagtestmon")
                if added:
                    removed = remove_tour_bans(current_room, dummy_tour, "-_diagtestmon")
                    if removed:
                        results.append(f"[PASS] meow add rule / meow remove rule: OK")
                    else:
                        results.append(f"[WARN] meow add rule / meow remove rule: Added but failed to remove")
                else:
                    results.append(f"[WARN] meow add rule: Could not add dummy ban")
                remove_tour(current_room, dummy_tour)
            else:
                results.append(f"[WARN] meow add rule / meow remove rule: Skipped, could not create throwaway tour")
        except Exception as e:
            results.append(f"[FAIL] meow add rule / meow remove rule: {e}")

        # Test: meow add misc command / meow remove misc command (dummy tour)
        try:
            dummy_tour = "_diag_test_tour"
            added_tour = add_tour(current_room, dummy_tour, "gen9ou", "Diagnostic Test Tour")
            if added_tour:
                added = add_misc_commands(current_room, dummy_tour, "/diag_test_cmd")
                if added:
                    removed = remove_misc_commands(current_room, dummy_tour, "/diag_test_cmd")
                    if removed:
                        results.append(f"[PASS] meow add misc command / meow remove misc command: OK")
                    else:
                        results.append(f"[WARN] meow add misc command / meow remove misc command: Added but failed to remove")
                else:
                    results.append(f"[WARN] meow add misc command: Could not add dummy command")
                remove_tour(current_room, dummy_tour)
            else:
                results.append(f"[WARN] meow add misc command / meow remove misc command: Skipped, could not create throwaway tour")
        except Exception as e:
            results.append(f"[FAIL] meow add misc command / meow remove misc command: {e}")

        # Test: meow cancel next tn / meow uncancel next tn
        try:
            schedule = get_current_tour_schedule(current_room)
            next_tour = get_next_tournight(schedule)
            if next_tour:
                cancelled = cancel_next_tour(current_room)
                if cancelled:
                    uncancelled = uncancel_last_cancelled(current_room)
                    if uncancelled:
                        results.append(f"[PASS] meow cancel next tn / meow uncancel next tn: OK")
                    else:
                        results.append(f"[WARN] meow cancel next tn / meow uncancel next tn: Cancelled but failed to uncancel")
                else:
                    results.append(f"[WARN] meow cancel next tn: Could not cancel next tournight")
            else:
                results.append(f"[WARN] meow cancel next tn / meow uncancel next tn: Skipped, no upcoming tournight to test with")
        except Exception as e:
            results.append(f"[FAIL] meow cancel next tn / meow uncancel next tn: {e}")

    # Build and send HTML report
    rows = "".join(f"<tr><td style='padding:4px 8px;font-family:monospace'>{r}</td></tr>" for r in results)
    html = (
        f"<b>Meow, I tested my functions, and here are the results :3c</b><br>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
    )
    await ws.send(f"{current_room}|/addhtmlbox {html}")

async def meow_add_points(msg_text, current_room, ws):
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

async def meow_remove_misc_command(msg_text, current_room, ws):
    parts = msg_text[len("meow remove misc command"):].strip().split(None, 1)
    if len(parts) < 2:
        await ws.send(f"{current_room}|Meow, please use: meow remove misc command <tourname> <commands> >:c")
    else:
        tour_name = parts[0].lower()
        commands_str = parts[1].lower()    
        removed = remove_misc_commands(current_room, tour_name, commands_str)  
        if removed:
            await ws.send(f"{current_room}|Meow removed misc command(s): {', '.join(removed)} from {tour_name} >:3")
        else:
            await ws.send(f"{current_room}|Meow, those misc commands don't exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")

async def meow_add_misc_command(msg_text, current_room, ws):
    parts = msg_text[len("meow add misc command"):].strip().split(None, 1)                                
    if len(parts) < 2:
        await ws.send(f"{current_room}|Meow, please use: meow add misc command <tourname> <commands>. Please note that meow can't discern commands from unbans, so add it as it appears in /tour rules (i.e. -Flutter Mane, +Chien-Pao ) :<")
    else:
        tour_name = parts[0].lower()
        commands_str = parts[1].lower()                                
        # Add the commands
        added = add_misc_commands(current_room, tour_name, commands_str)                                
        if added:
            await ws.send(f"{current_room}|Meow added these misc command(s): {', '.join(added)} to {tour_name} >:3")
        else:
            await ws.send(f"{current_room}|Meow, those misc commands already exist or the tour doesn't exist. Idk meow, I'm just a cat ;w;")

async def meow_remove_rule(msg_text, current_room, ws):
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

async def meow_add_rule(msg_text, current_room, ws):
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

async def meow_remove_tour(msg_text, current_room, ws):
    tour_internalname = msg_text[len("meow remove tour"):].strip()
    if not tour_internalname:
        await ws.send(f"{current_room}|Usage: meow remove tour <internalname>")
    else:
        success = remove_tour(current_room, tour_internalname)
        if success:
            await ws.send(f"{current_room}|Tour '{tour_internalname}' removed successfully!")
        else:
            await ws.send(f"{current_room}|Meow, couldn't remove tour '{tour_internalname}'. Maybe it doesn't exist or still has bans, commands, or is part of this room's tour schedule meow? ;w;")       

async def meow_add_tour(msg_text, current_room, ws):
    prefix = "meow add tour"

    if not msg_text.lower().startswith(prefix):
        return

    remainder = msg_text[len(prefix):].strip()

    # check for complete params
    if " using " not in remainder.lower():
        await ws.send(
            f"{current_room}|Usage: meow add tour <internalname> using <tour type> as <name>"
        )
        return

    parts = remainder.split(" using ", 1)
    tour_internalname = parts[0].strip()
    after_using = parts[1].strip()

    if " as " not in after_using.lower():
        await ws.send(
            f"{current_room}|Usage: meow add tour <internalname> using <tour type> as <name>"
        )
        return

    type_part, name_part = after_using.split(" as ", 1)
    tour_type = type_part.strip()
    tour_name = name_part.strip()

    if not tour_internalname or not tour_type or not tour_name:
        await ws.send(
            f"{current_room}|Usage: meow add tour <internalname> using <tour type> as <name>"
        )
        return

    success = add_tour(current_room, tour_internalname, tour_type, tour_name)

    if success:
        await ws.send(
            f"{current_room}|Tour '{tour_internalname}' added successfully! Use meow start {tour_internalname} to use it mrrp :3"
        )
    else:
        await ws.send(
            f"{current_room}|Meow, couldn't add tour '{tour_internalname}', it might already exist??"
        )

async def show_set(current_room, user, ts, msg_text, ws):
    msg_id = f"{current_room}:{user}:{ts}:{msg_text}"              
    if msg_id not in PROCESSED_MESSAGES:          
        PROCESSED_MESSAGES[msg_id] = time.time()
        current_time = time.time()
        old_keys = [k for k, v in PROCESSED_MESSAGES.items() if current_time - v >= 60]
        for k in old_keys:
            del PROCESSED_MESSAGES[k]
                            
        sets_output = parse_command_and_get_sets(msg_text, current_room)
        if sets_output:
            for set_str in sets_output:
                await ws.send(f"{current_room}|/addhtmlbox {set_str}")    
            await ws.send(f"{current_room}|Meow sent the set info!")
        else:
            await ws.send(f"{current_room}|Meow couldn't find any sets for this mon, sorry ;w;. Usage: meow show set <pokemon> [format] (type/item/move [optional])")

async def start_tour(msg_text, current_room, ws):
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
            if "Monotype" in display_name or "Monothreat" in display_name or "NatDex" in display_name or "National Dex OU" in display_name:
                await ws.send(f"{current_room}|/tour name {display_name}")
            else:
                await ws.send(f"{current_room}|/tour name {display_name} {current_room.title()}")
                                    
            await ws.send(f"{current_room}|/tour scouting off")
            await ws.send(f"{current_room}|Meow started the {display_name} tour! >:3")

async def uncancel_next_tn(current_room: str, ws):
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

async def cancel_next_tn(current_room: str, ws):
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
