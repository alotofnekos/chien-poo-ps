import asyncio
import datetime
import pytz
from dotenv import load_dotenv
from tour_creator import build_tour_code, get_tour_info, get_monothreat_tours
from meow_supabase import supabase
import random
from calendar import monthrange
load_dotenv()

TIMEZONE   = pytz.timezone('US/Eastern')
START_DATE = datetime.date(2025, 2, 10)

CANCELLED_TOURS = set()

# ---------------------------------------------------------------------------
# Schedule cache — refreshes every 5 minutes per room
# ---------------------------------------------------------------------------

_schedule_cache: dict[str, dict] = {}   # room -> { "data": schedule, "fetched_at": datetime }
CACHE_TTL = datetime.timedelta(minutes=5)


def _fetch_schedule_from_db(room: str) -> dict | None:
    """
    Fetch raw schedule rows from Supabase and convert to:
    { weekday(int): [(hour, minute, tour_internalname), ...] }
    for the current active week.
    """
    try:
        resp = supabase.rpc("get_schedule", {"p_room": room}).execute()
    except Exception as e:
        print(f"[schedule] DB fetch failed for {room}: {e}")
        return None

    if not resp.data:
        return None

    # Determine which week is active for this room
    has_alternating_weeks = any(row["week"] == 2 for row in resp.data)
    if has_alternating_weeks: #remove monotype hardcoding to allow other tiers who might want 2 weeks
        now = datetime.datetime.now(TIMEZONE)
        weeks_passed = (now.date() - START_DATE).days // 7
        current_week = 1 if weeks_passed % 2 == 0 else 2
    else:
        current_week = 1

    schedule: dict[int, list] = {}
    for row in resp.data:
        if row["week"] != current_week:
            continue
        day = row["day"]
        if day not in schedule:
            schedule[day] = []
        schedule[day].append((row["hour"], 0, row["tour_internalname"]))

    return schedule or None


def get_current_tour_schedule(room: str) -> dict | None:
    """
    Returns the active schedule for a room, using a 5-minute cache.
    Falls back to stale cache if the DB is unreachable.
    """
    now    = datetime.datetime.now(TIMEZONE)
    cached = _schedule_cache.get(room)

    if cached:
        age = now - cached["fetched_at"]
        weeks_at_fetch = (cached["fetched_at"].date() - START_DATE).days // 7
        weeks_now      = (now.date() - START_DATE).days // 7
        week_changed   = weeks_at_fetch != weeks_now

        if age < CACHE_TTL and not week_changed:
            return cached["data"]
        # If week changed, fetch again

    fresh = _fetch_schedule_from_db(room)

    if fresh is not None:
        _schedule_cache[room] = {"data": fresh, "fetched_at": now}
        return fresh

    if cached:
        print(f"[schedule] DB unreachable, using stale cache for {room}")
        return cached["data"]

    return None


def invalidate_schedule_cache(room: str | None = None):
    """
    Force a cache refresh on next access.
    Call this after saving a schedule from the dashboard.
    Pass room=None to invalidate all rooms.
    """
    if room:
        _schedule_cache.pop(room, None)
    else:
        _schedule_cache.clear()


# ---------------------------------------------------------------------------
# Cancellation helpers
# ---------------------------------------------------------------------------

def cancel_next_tour(room):
    schedule  = get_current_tour_schedule(room)
    next_tour = get_next_tournight(schedule)
    if not next_tour:
        return None
    scheduled_at = next_tour['scheduled_at']
    cancel_key   = (room, scheduled_at.date(), scheduled_at.hour, scheduled_at.minute)
    CANCELLED_TOURS.add(cancel_key)
    return {'name': next_tour['name'], 'scheduled_at': scheduled_at, 'minutes_until': next_tour['minutes_until']}


def cancel_all_tours_today(room):
    schedule = get_current_tour_schedule(room)
    if not schedule:
        return []
    now          = datetime.datetime.now(TIMEZONE)
    today        = now.date()
    tours        = schedule.get(now.weekday(), [])
    cancelled    = []
    for tour_hour, tour_minute, tour_name in tours:
        tour_time = datetime.datetime(today.year, today.month, today.day, tour_hour, tour_minute, tzinfo=TIMEZONE)
        if tour_time > now:
            CANCELLED_TOURS.add((room, today, tour_hour, tour_minute))
            tour_info    = get_tour_info(room, tour_name)
            display_name = tour_info['tour_name'] if tour_info and tour_info.get('tour_name') else tour_name
            cancelled.append({'name': display_name, 'time': f"{tour_hour:02}:{tour_minute:02}"})
    return cancelled


def uncancel_last_cancelled(room=None):
    if not CANCELLED_TOURS:
        return None
    candidates = [k for k in CANCELLED_TOURS if k[0] == room] if room else list(CANCELLED_TOURS)
    if not candidates:
        return None
    last_key = sorted(candidates, key=lambda x: (x[1], x[2], x[3]))[-1]
    CANCELLED_TOURS.discard(last_key)
    return {'room': last_key[0], 'date': last_key[1], 'hour': last_key[2], 'minute': last_key[3],
            'datetime_str': f"{last_key[1]} {last_key[2]:02}:{last_key[3]:02}"}


def uncancel_tour(room, hour, minute, date=None):
    if date is None:
        date = datetime.date.today()
    cancel_key = (room, date, hour, minute)
    if cancel_key in CANCELLED_TOURS:
        CANCELLED_TOURS.discard(cancel_key)
        return True
    return False


def clear_all_cancellations(room):
    to_remove = [k for k in CANCELLED_TOURS if k[0] == room]
    for key in to_remove:
        CANCELLED_TOURS.discard(key)
    return len(to_remove)


def is_tour_cancelled(room, hour, minute, date=None):
    if date is None:
        date = datetime.date.today()
    return (room, date, hour, minute) in CANCELLED_TOURS


def get_cancelled_tours(room=None):
    results = [
        {'room': k[0], 'date': k[1], 'hour': k[2], 'minute': k[3],
         'datetime_str': f"{k[1]} {k[2]:02}:{k[3]:02}"}
        for k in CANCELLED_TOURS
        if room is None or k[0] == room
    ]
    return sorted(results, key=lambda x: (x['date'], x['hour'], x['minute']))

def get_next_tournight(schedule, search_horizon_days=7):
    if not schedule:
        return None
    now           = datetime.datetime.now(TIMEZONE)
    today_weekday = now.weekday()
    best          = None

    for day_offset in range(search_horizon_days + 1):
        weekday = (today_weekday + day_offset) % 7
        tours   = schedule.get(weekday, [])
        for tour_hour, tour_minute, tour_name in sorted(tours, key=lambda t: t[0]*60 + t[1]):
            candidate_date = now.date() + datetime.timedelta(days=day_offset)
            candidate_dt   = datetime.datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                tour_hour, tour_minute, tzinfo=now.tzinfo
            )
            if candidate_dt < now:
                continue
            minutes_until = int((candidate_dt - now).total_seconds() // 60)
            cand = {"name": tour_name, "hour": tour_hour, "minute": tour_minute,
                    "weekday": weekday, "day_offset": day_offset,
                    "scheduled_at": candidate_dt, "minutes_until": minutes_until}
            if best is None or cand["scheduled_at"] < best["scheduled_at"]:
                best = cand
        if best:
            break
    return best


# ---------------------------------------------------------------------------
# Tour scheduler loop 
# ---------------------------------------------------------------------------

async def scheduled_tours(ws, ROOM):
    print(f"Starting tour scheduler for {ROOM}...")
    last_check_minute = -1

    while True:
        now             = datetime.datetime.now(TIMEZONE)
        today_weekday   = now.weekday()
        current_hour    = now.hour
        current_minute  = now.minute
        today_date      = now.date()

        if current_minute == last_check_minute:
            await asyncio.sleep(1)
            continue
        last_check_minute = current_minute

        current_schedule = get_current_tour_schedule(ROOM)
        if not current_schedule:
            await asyncio.sleep(58)
            continue

        if today_weekday in current_schedule:
            for tour_hour, tour_minute, tour_internal_name in current_schedule[today_weekday]:
                tour_time    = tour_hour * 60 + tour_minute
                current_time = current_hour * 60 + current_minute

                if is_tour_cancelled(ROOM, tour_hour, tour_minute, today_date):
                    if current_time == tour_time:
                        await ws.send(f"{ROOM}| Skipping cancelled tour: {tour_internal_name} at {tour_hour:02}:{tour_minute:02}")
                    continue

                # 5 minute warning
                if current_time == tour_time - 5:
                    tour_info    = get_tour_info(ROOM, tour_internal_name)
                    display_name = tour_info['tour_name'] if tour_info and tour_info.get('tour_name') else tour_internal_name.replace('-', ' ').title()
                    await ws.send(f"{ROOM}|Meow, there will be a {display_name} tour in 5 minutes! Get ready nya!")

                # Start tour
                if (current_hour, current_minute) == (tour_hour, tour_minute):
                    print(f"It's {tour_hour:02}:{tour_minute:02} on {now.strftime('%A')}. Starting: {tour_internal_name}")

                    if tour_internal_name == "random-monothreat":
                        monothreat_tours = get_monothreat_tours(ROOM)
                        if monothreat_tours:
                            selected_tour = random.choice(monothreat_tours)
                            tour_code     = build_tour_code(ROOM, selected_tour)
                            tour_info     = get_tour_info(ROOM, selected_tour)
                        else:
                            await ws.send(f"{ROOM}|Meow wasnt able to pick a random type. Please tell Neko that meow did the dumb.")
                            continue
                    else:
                        tour_code = build_tour_code(ROOM, tour_internal_name)
                        tour_info = get_tour_info(ROOM, tour_internal_name)

                    if not tour_code or not tour_info:
                        print(f"Error: No tour data for '{tour_internal_name}' in '{ROOM}'.")
                        await ws.send(f"{ROOM}|Meow tried to create a tour for {tour_internal_name}, but I couldnt read it from the database. Please tell this to Neko.")
                        continue

                    await ws.send(f"{ROOM}|/tour end")
                    await asyncio.sleep(2)
                    for command in tour_code.split('\n'):
                        await ws.send(f"{ROOM}|{command.strip()}")

                    display_name = tour_info['tour_name']
                    if "Monotype" in display_name or "Monothreat" in display_name or "NatDex" in display_name:
                        await ws.send(f"{ROOM}|/tour name {display_name} Tour Nights")
                    else:
                        await ws.send(f"{ROOM}|/tour name {display_name} {ROOM.title()} Tour Nights")

                    await ws.send(f"{ROOM}|/tour scouting off")

        await asyncio.sleep(29)


# ---------------------------------------------------------------------------
# Monthly schedule HTML (reads from DB via cache)
# ---------------------------------------------------------------------------

def generate_monthly_tour_schedule_html(month: int, year: int, room: str):
    import datetime
    from calendar import monthrange

    # --- colors & styles ---
    color_sets   = [
        ("rgba(240, 255, 255, 0.15)", "rgba(230, 230, 250, 0.15)"),
        ("rgba(204, 204, 255, 0.15)", "rgba(211, 211, 211, 0.15)")
    ]
    header_color = "rgba(176, 196, 222, 0.2)"
    border_color = "rgba(128, 128, 128, 0.4)"
    subheader_bg = "rgba(240, 240, 240, 0.1)"
    num_days     = monthrange(year, month)[1]

    # --- timezone display ---
    sample_date  = datetime.datetime(year, month, 15, 12, 0, tzinfo=TIMEZONE)
    tz_offset    = int(sample_date.strftime('%z')[:3])
    tz_display   = f"GMT{tz_offset:+d}" if tz_offset != 0 else "GMT"

    # --- fetch schedule ---
    try:
        resp = supabase.rpc("get_schedule", {"p_room": room}).execute()
        raw  = resp.data or []
    except Exception as e:
        return f"<p>No schedule found: {e}</p>"

    if not raw:
        return "<p>No schedule found.</p>"

    # --- organize by week and weekday ---
    schedules = {}
    for row in raw:
        week = row.get("week", 1)
        day  = row.get("day")
        schedules.setdefault(week, {})
        schedules[week].setdefault(day, [])
        schedules[week][day].append((row["hour"], 0, row["tour_internalname"]))

    # --- pre-cache tour info to reduce repeated calls ---
    tour_names = {row["tour_internalname"] for row in raw}
    tour_info_cache = {}
    for t in tour_names:
        info = get_tour_info(room, t) or {}
        tour_info_cache[t] = info.get("tour_name") or t.replace("-", " ").title()

    # --- build HTML ---
    html = [
        f"<div style='width:100%; background:{header_color}; text-align:center; font-weight:bold; padding:5px;'>"
        f"{room.capitalize()} Events ({datetime.date(year, month, 1).strftime('%B-%Y')})</div>",
        f"<div style='width:100%; text-align:center; background:{subheader_bg}; font-size:12px; padding:3px;'>"
        f"Event Information Recorded in: {tz_display}</div>",
        f"<div style='width:100%; border:1px solid {border_color}; font-family:Arial; font-size:11px; height:390px; overflow-y:auto;'>"
        f"<table style='border-collapse:collapse; text-align:left; border:1px solid {border_color}; width:100%;'>"
    ]

    row_toggle = 0
    weeks_sorted = sorted(schedules.keys())
    for day in range(1, num_days + 1):
        current_date = datetime.date(year, month, day)
        weekday      = current_date.weekday()  # 0 = Mon, 6 = Sun

        # --- determine which week to use ---
        if 2 in schedules:
            weeks_passed = (current_date - START_DATE).days // 7
            week_to_use = 1 if weeks_passed % 2 == 0 else 2
        else:
            week_to_use = 1

        schedule = schedules.get(week_to_use) or schedules.get(1)
        if not schedule or weekday not in schedule:
            continue

        events = schedule[weekday]
        if not events:
            continue

        morning_events, night_events = [], []
        for hour, minute, t_internal in events:
            display_name = tour_info_cache.get(t_internal, t_internal)
            event_str = f"{hour:02}:{minute:02} {display_name}"
            if hour <= 12:
                morning_events.append(event_str)
            else:
                night_events.append(event_str)

        morning_color, night_color = color_sets[row_toggle]
        html.append(
            f"<tr>"
            f"<td style='background:{header_color}; text-align:center; padding:4px; font-weight:bold; width:15%; border:1px solid {border_color};'>{current_date.strftime('%m/%d')}</td>"
            f"<td style='background:{morning_color}; padding:4px; width:42.5%; border:1px solid {border_color};'>{'<br>'.join(morning_events)}</td>"
            f"<td style='background:{night_color}; padding:4px; width:42.5%; border:1px solid {border_color};'>{'<br>'.join(night_events)}</td>"
            f"</tr>"
        )
        row_toggle = 1 - row_toggle

    html.append("</table></div>")
    return "\n".join(html)

if __name__ == "__main__":
    html_schedule = generate_monthly_tour_schedule_html(3, 2026, "monotype")
    print(html_schedule)
    sched     = get_current_tour_schedule("nationaldexmonotype")
    next_tour = get_next_tournight(sched)
    if next_tour:
        print(f"Next tour: {next_tour['name']} at {next_tour['hour']}:{next_tour['minute']} — in {next_tour['minutes_until']} minute(s)!")