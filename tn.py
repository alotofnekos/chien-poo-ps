import asyncio
import datetime
import pytz
from dotenv import load_dotenv
from tour_creator import build_tour_code, get_tour_info, get_monothreat_tours
import random
from calendar import monthrange
load_dotenv()

# Timezone for tour scheduling.
TIMEZONE = pytz.timezone('US/Eastern')

# Set to track cancelled tours: (room, date, hour, minute)
CANCELLED_TOURS = set()

# The key date for Week A. All odd-numbered weeks after this date are Week B.
START_DATE = datetime.date(2025, 2, 10)

# Tour schedules for Week A and Week B.
# Day of week (0=Mon, 6=Sun) -> List of (hour, minute, tour_internal_name) tuples

# MONOTYPE
TOUR_SCHEDULE_A = {
    0: [(9, 0, 'adv'), (10, 0, 'tera'), (11, 0, 'ubers'), (21, 0, 'lc'), (22, 0, 'doubles'), (23, 0, 'monotype-wildcard')],
    4: [(9, 0, 'sv'), (10, 0, 'bw'), (11, 0, 'ss'), (21, 0, 'sm'), (22, 0, 'oras'), (23, 0, 'sv')],
    5: [(9, 0, 'uu'), (10, 0, 'sm'), (11, 0, 'sv'), (21, 0, 'sv'), (22, 0, 'ss'), (23, 0, 'natdex')],
    6: [(9, 0, 'oras'), (10, 0, 'sv'), (11, 0, 'random-monothreat'), (21, 0, 'cap'), (22, 0, 'sv'), (23, 0, 'bw')]
}

TOUR_SCHEDULE_B = {
    0: [(9, 0, 'lc'), (10, 0, 'doubles'), (11, 0, 'monotype-wildcard'),(21, 0, 'adv'), (22, 0, 'tera'), (23, 0, 'ubers')],
    4: [(9, 0, 'sm'), (10, 0, 'oras'), (11, 0, 'sv'), (21, 0, 'sv'), (22, 0, 'bw'), (23, 0, 'ss')],
    5: [(9, 0, 'sv'), (10, 0, 'ss'), (11, 0, 'natdex'), (21, 0, 'uu'), (22, 0, 'sm'), (23, 0, 'sv')],
    6: [(9, 0, 'cap'), (10, 0, 'sv'), (11, 0, 'bw'), (21, 0, 'oras'), (22, 0, 'sv'), (23, 0, 'random-monothreat')]
}

# National Dex Monotype
TOUR_SCHEDULE_NDM = {
    0: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    1: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    2: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    3: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    4: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    5: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
    6: [(8,0,'natdex'), (10,0,'random-monothreat'), (12,0,'natdex'),(14,0,'z-less'),(16,0,'natdex'),(18,0,'ru'),(20,0,'natdex'),(22,0,'ss-natdex'),(0,0,'natdex'),(2,0,'ubers')],
}

def cancel_next_tour(room):
    """
    Cancels the next scheduled tour for a given room.
    Returns a dict with info about the cancelled tour, or None if no tour found.
    """
    schedule = get_current_tour_schedule(room)
    next_tour = get_next_tournight(schedule)
    
    if not next_tour:
        return None
    
    # Create cancellation key
    scheduled_at = next_tour['scheduled_at']
    cancel_key = (
        room,
        scheduled_at.date(),
        scheduled_at.hour,
        scheduled_at.minute
    )
    
    CANCELLED_TOURS.add(cancel_key)
    
    return {
        'name': next_tour['name'],
        'scheduled_at': scheduled_at,
        'minutes_until': next_tour['minutes_until']
    }

def cancel_all_tours_today(room):
    """
    Cancels all remaining tours today for a given room.
    Returns a list of cancelled tour names.
    """
    schedule = get_current_tour_schedule(room)
    if not schedule:
        return []
    
    now = datetime.datetime.now(TIMEZONE)
    today = now.date()
    today_weekday = now.weekday()
    
    tours = schedule.get(today_weekday, [])
    cancelled = []
    
    for tour_hour, tour_minute, tour_name in tours:
        tour_time = datetime.datetime(
            today.year, today.month, today.day,
            tour_hour, tour_minute, tzinfo=TIMEZONE
        )
        
        # Only cancel future tours
        if tour_time > now:
            cancel_key = (room, today, tour_hour, tour_minute)
            CANCELLED_TOURS.add(cancel_key)
            
            tour_info = get_tour_info(room, tour_name)
            display_name = tour_info['tour_name'] if tour_info and tour_info.get('tour_name') else tour_name
            cancelled.append({
                'name': display_name,
                'time': f"{tour_hour:02}:{tour_minute:02}"
            })
    
    return cancelled

def uncancel_last_cancelled(room=None):
    """
    Removes the most recently cancelled tour from the list (like popping a stack).
    If room is specified, only uncancels from that room.
    Returns the uncancelled tour info or None if no cancelled tours found.
    """
    if not CANCELLED_TOURS:
        return None
    
    # Filter by room if specified
    if room is not None:
        room_cancelled = [key for key in CANCELLED_TOURS if key[0] == room]
        if not room_cancelled:
            return None
        # Get the most recent one (sort by date, then time)
        last_key = sorted(room_cancelled, key=lambda x: (x[1], x[2], x[3]))[-1]
    else:
        # Get the most recent across all rooms
        last_key = sorted(CANCELLED_TOURS, key=lambda x: (x[1], x[2], x[3]))[-1]
    
    CANCELLED_TOURS.discard(last_key)
    
    return {
        'room': last_key[0],
        'date': last_key[1],
        'hour': last_key[2],
        'minute': last_key[3],
        'datetime_str': f"{last_key[1]} {last_key[2]:02}:{last_key[3]:02}"
    }

def uncancel_tour(room, hour, minute, date=None):
    """
    Removes a specific tour from the cancelled list.
    If date is None, uses today's date.
    """
    if date is None:
        date = datetime.date.today()
    
    cancel_key = (room, date, hour, minute)
    
    if cancel_key in CANCELLED_TOURS:
        CANCELLED_TOURS.discard(cancel_key)
        return True
    return False

def clear_all_cancellations(room):
    """
    Clears all cancelled tours
    """
    to_remove = [key for key in CANCELLED_TOURS if key[0] == room]
    for key in to_remove:
        CANCELLED_TOURS.discard(key)
    return len(to_remove)

def is_tour_cancelled(room, hour, minute, date = None):
    """
    Check if a specific tour is cancelled.
    """
    if date is None:
        date = datetime.date.today()
    cancel_key = (room, date, hour, minute)
    return cancel_key in CANCELLED_TOURS

def get_cancelled_tours(room=None):
    """
    Get list of all cancelled tours, optionally filtered by room.
    Returns list of dicts with tour info.
    """
    cancelled_list = []
    
    for cancel_key in CANCELLED_TOURS:
        cancel_room, cancel_date, cancel_hour, cancel_minute = cancel_key
        
        if room is not None and cancel_room != room:
            continue
        
        cancelled_list.append({
            'room': cancel_room,
            'date': cancel_date,
            'hour': cancel_hour,
            'minute': cancel_minute,
            'datetime_str': f"{cancel_date} {cancel_hour:02}:{cancel_minute:02}"
        })
    
    return sorted(cancelled_list, key=lambda x: (x['date'], x['hour'], x['minute']))

def get_current_tour_schedule(ROOM):
    """Determines if it's Week A or Week B based on the current date."""
    today = datetime.date.today()
    if ROOM == "monotype":
        weeks_passed = (today - START_DATE).days // 7
        
        if weeks_passed % 2 == 0:
            return TOUR_SCHEDULE_A
        else:
            return TOUR_SCHEDULE_B
    elif ROOM == "nationaldexmonotype":
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
    """Checks the time and starts a tour based on the schedule."""
    print(f"Starting tour scheduler for {ROOM}...")
    last_check_minute = -1
    
    while True:
        now = datetime.datetime.now(TIMEZONE)
        today_weekday = now.weekday()
        current_hour = now.hour
        current_minute = now.minute
        today_date = now.date()

        # Only check once per minute to avoid duplicate triggers
        if current_minute == last_check_minute:
            await asyncio.sleep(1)
            continue
        last_check_minute = current_minute
        current_schedule = get_current_tour_schedule(ROOM)
        if current_schedule is None:
            continue
        else:
            if today_weekday in current_schedule:
                for tour_schedule in current_schedule[today_weekday]:
                    tour_hour, tour_minute, tour_internal_name = tour_schedule
                    tour_time = tour_hour * 60 + tour_minute
                    current_time = current_hour * 60 + current_minute
                    
                    # Check if this tour is cancelled
                    if is_tour_cancelled(ROOM, tour_hour, tour_minute, today_date):
                        if current_time == tour_time:
                            await ws.send(f"{ROOM}| Skipping cancelled tour: {tour_internal_name} at {tour_hour:02}:{tour_minute:02}")
                        continue
                    
                    # 5 minute warning
                    if current_time == tour_time - 5:
                        # Get the display name from database
                        tour_info = get_tour_info(ROOM, tour_internal_name)
                        if tour_info and tour_info.get('tour_name'):
                            display_name = tour_info['tour_name']
                        else:
                            display_name = tour_internal_name.replace('-', ' ').title()
                        await ws.send(f"{ROOM}|Meow, there will be a {display_name} tour in 5 minutes! Get ready nya!")
                                    
                    # Start tour
                    if (current_hour, current_minute) == (tour_hour, tour_minute):
                        print(f"It's {tour_hour:02}:{tour_minute:02} on {now.strftime('%A')}. Starting tour: {tour_internal_name}")

                        # Handle random monothreat
                        if tour_internal_name == "random-monothreat":
                            monothreat_tours = get_monothreat_tours(ROOM)
                            
                            if monothreat_tours:
                                selected_tour = random.choice(monothreat_tours)
                                tour_code = build_tour_code(ROOM, selected_tour)
                                tour_info = get_tour_info(ROOM, selected_tour)
                            else:
                                await ws.send(f"{ROOM}|Meow wasnt able to pick a random type. Please tell Neko that meow did the dumb.")
                                continue
                        else:
                            # Regular tour
                            tour_code = build_tour_code(ROOM, tour_internal_name)
                            tour_info = get_tour_info(ROOM, tour_internal_name)
                        
                        # Check if we got valid tour data
                        if not tour_code or not tour_info:
                            print(f"Error: No tour data found for '{tour_internal_name}' in room '{ROOM}'.")
                            await ws.send(f"{ROOM}|Meow tried to create a tour for {tour_internal_name}, but I couldnt read it from the database. Please tell this to Neko.")
                            continue
                        
                        # Send tour commands
                        await ws.send(f"{ROOM}|/tour end")
                        await asyncio.sleep(2)
                        
                        tour_commands = tour_code.split('\n')
                        for command in tour_commands:
                            await ws.send(f"{ROOM}|{command.strip()}")
                        
                        # Set tour name
                        display_name = tour_info['tour_name']
                        if "Monotype" in display_name or "Monothreat" in display_name or "NatDex" in display_name:
                            await ws.send(f"{ROOM}|/tour name {display_name} Tour Nights")
                        else:
                            await ws.send(f"{ROOM}|/tour name {display_name} {ROOM.title()} Tour Nights")
                        
                        await ws.send(f"{ROOM}|/tour scouting off")

        await asyncio.sleep(58)


def generate_monthly_tour_schedule_html(month: int, year: int, room: str):
    from calendar import monthrange
    import datetime

    color_sets = [
        ("rgba(240, 255, 255, 0.15)", "rgba(230, 230, 250, 0.15)"),
        ("rgba(204, 204, 255, 0.15)", "rgba(211, 211, 211, 0.15)")
    ]
    header_color = "rgba(176, 196, 222, 0.2)"
    border_color = "rgba(128, 128, 128, 0.4)"
    subheader_bg = "rgba(240, 240, 240, 0.1)"
    num_days = monthrange(year, month)[1]

    if room == "monotype":
        schedules = {"A": TOUR_SCHEDULE_A, "B": TOUR_SCHEDULE_B}
    elif room == "nationaldexmonotype":
        schedules = {"NDM": TOUR_SCHEDULE_NDM}
    else:
        return "<p>Invalid room specified</p>"

    # Get the timezone offset for the given month/year
    sample_date = datetime.datetime(year, month, 15, 12, 0, tzinfo=TIMEZONE)
    tz_offset = sample_date.strftime('%z')
    tz_name = sample_date.tzname()
    
    offset_hours = int(tz_offset[:3])
    tz_display = f"GMT{offset_hours:+d}" if offset_hours != 0 else "GMT"

    html = []

    # Full-width header
    html.append(
        f"<div style='width:100%; background:{header_color}; text-align:center; font-weight:bold; padding:5px;'>"
        f"{room.capitalize()} Events ({datetime.date(year, month, 1).strftime('%B-%Y')})</div>"
    )
    html.append(
        f"<div style='width:100%; text-align:center; background:{subheader_bg}; font-size:12px; padding:3px;'>"
        f"Event Information Recorded in: {tz_display}</div>"
    )

    # Container with fixed height
    html.append(
        f"<div style='width:100%; border:1px solid {border_color}; font-family:Arial; font-size:11px; height:390px; overflow-y:auto;'>"
    )

    # Table takes full width
    html.append(
        f"<table style='border-collapse:collapse; text-align:left; border:1px solid {border_color}; width:100%;'>"
    )

    row_toggle = 0
    for day in range(1, num_days + 1):
        current_date = datetime.date(year, month, day)
        weekday = current_date.weekday()

        if room == "monotype":
            weeks_passed = (current_date - START_DATE).days // 7
            week_type = "A" if weeks_passed % 2 == 0 else "B"
            schedule = schedules[week_type]
        else:
            schedule = schedules["NDM"]

        if weekday not in schedule:
            continue

        events = schedule[weekday]
        if not events:
            continue

        # Get display names from database
        morning_events = []
        night_events = []
        
        for hour, minute, tour_internal_name in events:
            tour_info = get_tour_info(room, tour_internal_name)
            
            if tour_info and tour_info.get('tour_name'):
                display_name = tour_info['tour_name']
            else:
                display_name = tour_internal_name.replace('-', ' ').title()
            
            event_str = f"{hour:02}:{minute:02} {display_name}"
            
            if hour <= 12:
                morning_events.append(event_str)
            else:
                night_events.append(event_str)

        morning_color, night_color = color_sets[row_toggle]

        html.append(
            f"<tr>"
            f"<td style='background:{header_color}; text-align:center; padding:4px; font-weight:bold; width:15%; border:1px solid {border_color};'>{current_date.strftime('%m/%d')}</td>"
            f"<td style='background:{morning_color}; padding:4px; width:42.5%; border:1px solid {border_color};'>{'<br>'.join(morning_events) if morning_events else ''}</td>"
            f"<td style='background:{night_color}; padding:4px; width:42.5%; border:1px solid {border_color};'>{'<br>'.join(night_events) if night_events else ''}</td>"
            f"</tr>"
        )

        row_toggle = 1 - row_toggle

    html.append("</table>")
    html.append("</div>")
    
    return "\n".join(html)

async def main(ws, ROOM):
    await scheduled_tours(ws, ROOM)

# Debug output
if __name__ == "__main__":
    html_schedule = generate_monthly_tour_schedule_html(10, 2025, "monotype")
    print(html_schedule)
    Sched = get_current_tour_schedule("nationaldexmonotype")
    next_tour = get_next_tournight(Sched)
    print(f"Meow, the next tournight is {next_tour['name']} at {next_tour['hour']}:{next_tour['minute']} (GMT-4). Its in {next_tour['minutes_until']} minute(s)!")