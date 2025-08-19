import asyncio
import datetime
import pytz
import json
import os
from dotenv import load_dotenv
from pm_handler import handle_pmmessages, get_random_cat_url
import time
import random
from potd import send_potd
load_dotenv()
last_showcat = {}
USERNAME = os.getenv("PS_USERNAME")
# Timezone for tour scheduling.
TIMEZONE = pytz.timezone('US/Eastern')

# The key date for Week A. All odd-numbered weeks after this date are Week B.
START_DATE = datetime.date(2025, 2, 10)

# Load tour schedules from tours.json.
def load_tour_data():
    with open('tours.json', 'r') as f:
        data = json.load(f)
    
    tour_schedules = {}
    for tour in data:
        tour_schedules[tour['Tour']] = tour['Code']
    return tour_schedules

TOUR_COMMANDS = load_tour_data()

# Tour schedules for Week A and Week B.
# Day of week (0=Mon, 6=Sun) -> List of (hour, minute, format) tuples
TOUR_SCHEDULE_A = {
    4: [(12, 0, 'SV'), (1, 0, 'Tera'), (2, 0, 'ORAS'), (18, 0, 'LC'), (19, 0, 'BW'), (20, 0, 'Monotype-Wildcard')],
    1: [(9, 0, 'SV'), (10, 0, 'BW'), (11, 0, 'SS'), (21, 0, 'SM'), (22, 0, 'ORAS'), (23, 0, 'SV')],
    2: [(9, 0, 'UU'), (10, 0, 'SM'), (11, 0, 'SV'), (21, 0, 'SV'), (22, 0, 'SS'), (23, 0, 'NatDex')],
    3: [(9, 0, 'ORAS'), (10, 0, 'SV'), (11, 0, 'Random Monothreat Type'), (21, 0, 'CAP'), (22, 0, 'SV'), (23, 0, 'BW')]
}

TOUR_SCHEDULE_B = {
    4: [(12, 0, 'SV'), (1, 0, 'Tera'), (2, 0, 'SS'), (18, 0, 'LC'), (19, 0, 'SM'), (20, 0, 'Monotype-Wildcard')],
    1: [(9, 0, 'SM'), (10, 0, 'ORAS'), (11, 0, 'SV'), (21, 0, 'SV'), (22, 0, 'BW'), (23, 0, 'SS')],
    2: [(9, 0, 'SV'), (10, 0, 'SS'), (11, 0, 'NatDex'), (21, 0, 'UU'), (22, 0, 'SM'), (23, 0, 'SV')],
    3: [(9, 0, 'CAP'), (10, 0, 'SV'), (11, 0, 'BW'), (21, 0, 'ORAS'), (22, 0, 'SV'), (23, 0, 'Random Monothreat Type')]
}

# The queue for storing the random type.
random_type_queue = asyncio.Queue()


def get_current_tour_schedule():
    """Determines if it's Week A or Week B based on the current date."""
    today = datetime.date.today()
    weeks_passed = (today - START_DATE).days // 7
    
    if weeks_passed % 2 == 0:
        print("It's currently Week A.")
        return TOUR_SCHEDULE_A
    else:
        print("It's currently Week B.")
        return TOUR_SCHEDULE_B

async def listen_for_messages(ws, ROOM):
    """Listens for and processes messages from the WebSocket."""
    print("Starting message listener...")
    while True:
        try:
            global last_showcat
            msg = await ws.recv()
            #print(f"Received: {msg}")
            if f"|pm|" in msg:
                await handle_pmmessages(ws, USERNAME,msg)
            elif f"|c:|" in msg:
                # Syntax example: |c:|1755238230| ArkenCiel|ltranc are you here
                parts = msg.split("|")
                user    = parts[3].strip()     # "ArkenCiel"
                msg_text = parts[4].strip()    # "ltranc are you here"
                prefix  = user[:1]             # "A"
                if "meow" in msg_text.lower():
                    if prefix in ('%', '@', '#'):  # auth check
                        print(f"Received: {msg} from {user} with message: {msg_text}")

                        if msg_text.lower().startswith("meow start"):
                            # Extract tour_name after "meow start"
                            _, _, tour_name = msg_text.partition("meow start")
                            tour_name = tour_name.strip()

                            # Make lookup case-insensitive
                            lower_map = {k.lower(): k for k in TOUR_COMMANDS.keys()}

                            if tour_name.lower() in lower_map:
                                lookup_key = lower_map[tour_name.lower()]
                                tour_commands = TOUR_COMMANDS[lookup_key].split('\n')
                                for command in tour_commands:
                                    await ws.send(f"{ROOM}|{command.strip()}")
                            else:
                                # Send available tour names
                                available = ", ".join(TOUR_COMMANDS.keys())
                                await ws.send(f"{ROOM}|Meow couldn’t find '{tour_name}'. Available tours: {available}")
                        elif msg_text.lower().startswith("meow show potd"):
                                send_potd(ws, ROOM)
                                await ws.send(f"{ROOM}|Meow sent the Pokémon of the day!")
                        else:
                            await ws.send(f"{ROOM}|Meow :3")
                if "You cannot have a tournament until" in msg:
                    await ws.send(f"{ROOM}|There's a tour going on right meow...")
            
            else:
                pass

        except Exception as e:
            print(f"Error in message listener: {e}")
            await asyncio.sleep(1) # Wait a bit before retrying

async def scheduled_tours(ws, ROOM):
    """Checks the time and starts a tour based on the schedule."""
    print("Starting tour scheduler...")
    last_check_minute = -1
    while True:
        now = datetime.datetime.now(TIMEZONE)
        today_weekday = now.weekday()
        current_hour = now.hour
        current_minute = now.minute
        # print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} (Weekday: {today_weekday}, Hour: {current_hour}, Minute: {current_minute})")

        # Only check once per minute to avoid duplicate triggers
        if current_minute == last_check_minute:
            await asyncio.sleep(1)
            continue
        last_check_minute = current_minute

        current_schedule = get_current_tour_schedule()
        
        if today_weekday in current_schedule:
            for tour_schedule in current_schedule[today_weekday]:
                tour_hour, tour_minute, tour_name = tour_schedule
                
                if (current_hour, current_minute) == (tour_hour, tour_minute):
                    print(f"It's {tour_hour:02}:{tour_minute:02} on {now.strftime('%A')}. Sending tour commands.")

                    if tour_name == "Random Monothreat Type":
                        monothreat_keys = [key for key in TOUR_COMMANDS.keys() if key.startswith("Monothreat")]
                        if monothreat_keys:
                            lookup_key = random.choice(monothreat_keys)
                        else:
                            # fallback if something goes wrong
                            await ws.send(f"{ROOM}|Meow wasnt able to pick a random type. Please tell Neko that meow did the dumb.")
                            lookup_key = "Monothreat Fairy"

                        # Double-check the key exists in TOUR_COMMANDS
                        if lookup_key in TOUR_COMMANDS:
                            tour_commands = TOUR_COMMANDS[lookup_key].split('\n')
                            for command in tour_commands:
                                await ws.send(f"{ROOM}|{command.strip()}")
                        else:
                            # Final fallback if even the chosen key isn't valid
                            await ws.send(f"{ROOM}|Meow wasnt able to get the monothreat commands. Meow cant start the tour, ask an auth to start it meow.")
                            await ws.send(f"{ROOM}|Also tell this to Neko meow ;w;")
                    else:
                        if tour_name in TOUR_COMMANDS:
                            tour_commands = TOUR_COMMANDS[tour_name].split('\n')
                            for command in tour_commands:
                                await ws.send(f"{ROOM}|{command.strip()}")
                        else:
                            print(f"Error: No command found for '{tour_name}'.")
                            await ws.send(f"{ROOM}|Meow tried to create a tour for {tour_name}, but I couldnt read it or Neko is being stinky. Please tell this to Neko.")

        await asyncio.sleep(59)

async def main(ws, ROOM):
    """The main entry point for the bot's tasks."""
    await asyncio.gather(
        scheduled_tours(ws, ROOM),
        listen_for_messages(ws, ROOM)
    )