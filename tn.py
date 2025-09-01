import asyncio
import datetime
import pytz
import json
import os
from dotenv import load_dotenv
import random
from calendar import monthrange
load_dotenv()
last_showcat = {}
USERNAME = os.getenv("PS_USERNAME")
# Timezone for tour scheduling.
TIMEZONE = pytz.timezone('US/Eastern')

# The key date for Week A. All odd-numbered weeks after this date are Week B.
START_DATE = datetime.date(2025, 2, 10)

# Load tour schedules from tours.json.
def load_tour_data(ROOM):
    try:
        with open(f'tours_{ROOM}.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: The file tours_{ROOM}.json was not found.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from tours_{ROOM}.json. The file might be corrupted.")
        return {}
    tour_schedules = {}
    for tour in data:
        tour_schedules[tour['Tour']] = tour['Code']
    return tour_schedules



# Tour schedules for Week A and Week B.
# Day of week (0=Mon, 6=Sun) -> List of (hour, minute, format) tuples

# MONOTYPE
TOUR_SCHEDULE_A = {
    0: [(9, 0, 'SV'), (10, 0, 'Tera'), (11, 0, 'ORAS'), (21, 0, 'LC'), (22, 0, 'BW'), (23, 0, 'Monotype-Wildcard')],
    4: [(9, 0, 'SV'), (10, 0, 'BW'), (11, 0, 'SS'), (21, 0, 'SM'), (22, 0, 'ORAS'), (23, 0, 'SV')],
    5: [(9, 0, 'UU'), (10, 0, 'SM'), (11, 0, 'SV'), (21, 0, 'SV'), (22, 0, 'SS'), (23, 0, 'NatDex')],
    6: [(9, 0, 'ORAS'), (10, 0, 'SV'), (11, 0, 'Random Monothreat Type'), (21, 0, 'CAP'), (22, 0, 'SV'), (23, 0, 'BW')]
}


# September 1 prep
TOUR_SCHEDULE_B = {
    0: [(9, 0, 'SV'), (10, 0, 'Tera'), (11, 0, 'SS'), (21, 0, 'LC'), (22, 0, 'SM'), (23, 0, 'Monotype-Wildcard')],
    4: [(9, 0, 'SM'), (10, 0, 'ORAS'), (11, 0, 'SV'), (21, 0, 'SV'), (22, 0, 'BW'), (23, 0, 'SS')],
    5: [(9, 0, 'SV'), (10, 0, 'SS'), (11, 0, 'NatDex'), (21, 0, 'UU'), (22, 0, 'SM'), (23, 0, 'SV')],
    6: [(9, 0, 'CAP'), (10, 0, 'SV'), (11, 0, 'BW'), (21, 0, 'ORAS'), (22, 0, 'SV'), (23, 0, 'Random Monothreat Type')]
}


# National Dex Monotype
TOUR_SCHEDULE_NDM = {
    0: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    1: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    2: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    3: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    4: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    5: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
    6: [(8,0,'NatDex'), (10,0,'Random Monothreat Type'), (12,0,'NatDex'),(14,0,'Z-less'),(16,0,'NatDex'),(18,0,'RU'),(20,0,'NatDex'),(22,0,'SS NatDex'),(0,0,'NatDex'),(2,0,'Ubers')],
}

# The queue for storing the random type.
random_type_queue = asyncio.Queue()

def get_current_tour_schedule(ROOM):
    """Determines if it's Week A or Week B based on the current date."""
    today = datetime.date.today()
    if ROOM == "monotype":
        weeks_passed = (today - START_DATE).days // 7
        
        if weeks_passed % 2 == 0:
            #print("It's currently Week A.")
            return TOUR_SCHEDULE_A
        else:
            #print("It's currently Week B.")
            return TOUR_SCHEDULE_B
    elif ROOM == "nationaldexmonotype":
        #print("NDM schedule is ready")
        return TOUR_SCHEDULE_NDM
    
def get_next_tournight(schedule, search_horizon_days=7):
    """
    Returns a dict describing the next tour from 'now', scanning up to 'search_horizon_days'.
    Shape:
      {
        "name": str,
        "hour": int,
        "minute": int,
        "weekday": int,        # 0=Mon..6=Sun
        "day_offset": int,     # 0=today, 1=tomorrow, ...
        "scheduled_at": datetime.datetime,
        "minutes_until": int
      }
    or None if no tours found.
    """
    if not schedule:
        return None
    now = datetime.datetime.now(TIMEZONE)
    tz = now.tzinfo
    today_weekday = now.weekday()
    best = None

    for day_offset in range(search_horizon_days + 1):
        weekday = (today_weekday + day_offset) % 7
        tours = schedule.get(weekday, [])
        if not tours:
            continue

        # Sort tours by time of day
        for tour_hour, tour_minute, tour_name in sorted(tours, key=lambda t: t[0]*60 + t[1]):
            # Build the candidate datetime in the same timezone as 'now'
            candidate_date = (now.date() + datetime.timedelta(days=day_offset))
            candidate_dt = datetime.datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                tour_hour, tour_minute, tzinfo=tz
            )

            # Skip past tours today
            if candidate_dt < now:
                continue

            minutes_until = int((candidate_dt - now).total_seconds() // 60)

            cand = {
                "name": tour_name,
                "hour": tour_hour,
                "minute": tour_minute,
                "weekday": weekday,
                "day_offset": day_offset,
                "scheduled_at": candidate_dt,
                "minutes_until": minutes_until,
            }

            if best is None or cand["scheduled_at"] < best["scheduled_at"]:
                best = cand

        if best:
            break

    return best

async def scheduled_tours(ws, ROOM):
    """Continuously checks the schedule and triggers tours at the right time."""
    print(f"Starting tour scheduler for {ROOM}...")
    TOUR_COMMANDS = load_tour_data(ROOM)
    last_check_minute = -1

    while True:
        now = datetime.datetime.now(TIMEZONE)
        today_weekday = now.weekday()
        current_hour, current_minute = now.hour, now.minute

        # Check only once per minute
        if current_minute == last_check_minute:
            await asyncio.sleep(1)
            continue
        last_check_minute = current_minute

        # Get current schedule
        current_schedule = get_current_tour_schedule(ROOM)
        next_tour = get_next_tournight(current_schedule, today_weekday, current_hour, current_minute)

        if next_tour:
            next_tour_time, next_tour_name = next_tour
            tour_hour, tour_minute = divmod(next_tour_time, 60)

            # 5-minute warning
            if current_hour * 60 + current_minute == next_tour_time - 5:
                await ws.send(f"{ROOM}|Meow, there will be a {next_tour_name} tour in 5 minutes! Get ready nya!")

            # Start the tour
            if (current_hour, current_minute) == (tour_hour, tour_minute):
                print(f"It's {tour_hour:02}:{tour_minute:02} on {now.strftime('%A')}. Sending tour commands.")

                if next_tour_name == "Random Monothreat Type":
                    monothreat_keys = [key for key in TOUR_COMMANDS.keys() if key.startswith("Monothreat")]
                    lookup_key = random.choice(monothreat_keys) if monothreat_keys else "Monothreat Fairy"

                    if lookup_key in TOUR_COMMANDS:
                        await ws.send(f"{ROOM}|/tour end")
                        await asyncio.sleep(2)
                        for cmd in TOUR_COMMANDS[lookup_key].split('\n'):
                            await ws.send(f"{ROOM}|{cmd.strip()}")
                        if "Monotype" in lookup_key or "Monothreat" in lookup_key:
                            await ws.send(f"{ROOM}|/tour name {lookup_key} Tour Nights")
                        else:
                            await ws.send(f"{ROOM}|/tour name {lookup_key} {current_room.title()} Tour Nights")
                    else:
                        await ws.send(f"{ROOM}|Meow couldnt get the monothreat commands. Ask an auth meow.")
                else:
                    if next_tour_name in TOUR_COMMANDS:
                        for cmd in TOUR_COMMANDS[next_tour_name].split('\n'):
                            await ws.send(f"{ROOM}|{cmd.strip()}")
                    else:
                        print(f"Error: No command found for '{next_tour_name}'.")
                        await ws.send(f"{ROOM}|Meow tried to create {next_tour_name}, but no commands found.")

        await asyncio.sleep(58)


def generate_monthly_tour_schedule_html(month: int, year: int, room: str):


    color_sets = [
        ("#F5F5F5", "#FFC0CB"),
        ("#F0E68C", "#D3D3D3")
    ]
    header_color = "#B0C4DE"
    text_color = "#0A0A0A"
    num_days = monthrange(year, month)[1]
    schedule = get_current_tour_schedule(room)
    if schedule is None:
        return f"<p style='color:{text_color};'>Invalid room specified</p>"

    html = []

    # Full-width header
    html.append(
        f"<div style='width:100%; background:{header_color}; text-align:center; font-weight:bold; padding:5px; color:{text_color};'>"
        f"{room.capitalize()} Events ({datetime.date(year, month, 1).strftime('%B-%Y')})</div>"
    )
    html.append(
        f"<div style='width:100%; text-align:center; background:#f0f0f0; font-size:12px; padding:3px; color:{text_color};'>"
        f"Event Information Recorded in: (GMT-4)</div>"
    )

    # Flex container with fixed height
    html.append(
        f"<div style='display:flex; width:100%; border:1px solid #ccc; font-family:Arial; font-size:11px; color:{text_color}; height:390px;'>"
    )

    # Scrollable table container
    html.append(f"<div style='overflow-y:auto; width:60%;'>")
    html.append(
        f"<table style='border-collapse:collapse; text-align:left; border:1px solid #ccc; color:{text_color}; width:100%;'>"
    )

    row_toggle = 0
    for day in range(1, num_days + 1):
        current_date = datetime.date(year, month, day)
        weekday = current_date.weekday()
        if weekday not in schedule:
            continue

        events = schedule[weekday]
        if not events:
            continue

        morning_events = [f"{hour:02}:{minute:02} {tour}" for hour, minute, tour in events if hour <= 12]
        night_events = [f"{hour:02}:{minute:02} {tour}" for hour, minute, tour in events if hour > 12]

        morning_color, night_color = color_sets[row_toggle]

        html.append(
            f"<tr>"
            f"<td style='background:{header_color}; text-align:center; padding:4px; font-weight:bold; width:15%; border:1px solid #ccc; color:{text_color};'>{current_date.strftime('%m/%d')}</td>"
            f"<td style='background:{morning_color}; padding:4px; width:42.5%; border:1px solid #ccc; color:{text_color};'>{'<br>'.join(morning_events) if morning_events else ''}</td>"
            f"<td style='background:{night_color}; padding:4px; width:42.5%; border:1px solid #ccc; color:{text_color};'>{'<br>'.join(night_events) if night_events else ''}</td>"
            f"</tr>"
        )

        row_toggle = 1 - row_toggle

    html.append("</table>")
    html.append("</div>")  # close scrollable container

    # Image side stays fixed
    html.append(
        f"<div style='width:40%; display:flex; align-items:center; justify-content:center; background:#fafafa; border-left:1px solid #ccc; color:{text_color};'>"
        f"""<img src="https://i.ibb.co/zHt57cMy/209.png" height="750" width="900" style="height: auto; width: auto;">"""
        f"</div>"
    )

    html.append("</div>")  # close flex container
    return "\n".join(html)

async def main(ws, ROOM):
    await scheduled_tours(ws, ROOM)

# Debug output
if __name__ == "__main__":
    html_schedule = generate_monthly_tour_schedule_html(8, 2025, "monotype")
    print(html_schedule)
    Sched = get_current_tour_schedule("nationaldexmonotype")
    next_tour = get_next_tournight(Sched)
    print(f"m|Meow, the next tournight is {next_tour['name']} at {next_tour['hour']}:{next_tour['minute']} (GMT-4). Its in {next_tour['minutes_until']} minute(s)!")