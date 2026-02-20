import asyncio
import datetime
import json
import os
import random
import hashlib
import re
from html import unescape
from zoneinfo import ZoneInfo

import aiohttp
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# Cache for monothreat tours to avoid repeated database queries
monothreat_tours_cache = {}

def get_tour_info(room: str, tour: str):
    """
    Get tour information (type, name, misc_commands) for a specific tour.
    Returns a dict with tour info or None if not found.
    """
    if room == "monotypeom":
        room = "monotype"  # monotypeom shares same tours as monotype
    try:
        resp = supabase.rpc(
            "get_tour_info",
            {
                "p_room_name": room,
                "p_tour_name": tour
            }
        ).execute()
        
        # RPC returns a list, get first item or None
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"Failed to get tour info for '{tour}': {e}")
        return None
    
def get_tour_bans(room: str, tour: str):
    """
    Get tour bans as a comma-separated string
    """
    if room == "monotypeom":
        room = "monotype"  # monotypeom shares same tours as monotype
    resp = supabase.rpc(
        'get_bans_for_tour_room',
        {'room_name': room, 'tour_name': tour}
    ).execute()
    
    if resp.data:
        return ', '.join(b['ban'] for b in resp.data)
    return ''  

def add_tour_bans(room: str, tour: str, bans_str: str):
    """
    Add one or multiple bans to a tour.
    `bans_str` can be comma-separated for multiple bans.
    Returns a list of successfully added bans.
    """
    if not bans_str:
        return []

    bans_list = [b.strip() for b in bans_str.split(",") if b.strip()]
    added = []

    for ban in bans_list:
        try:
            resp = supabase.rpc(
                "add_ban",
                {
                    "p_room_name": room,
                    "p_tour_name": tour,
                    "p_ban_name": ban
                }
            ).execute()

            # Check if resp.data is true
            if resp.data:
                added.append(ban)
            else:
                print(f"Failed to add ban '{ban}': {resp.data}")
        except Exception as e:
            # Catch foreign key violations and other errors
            if "23503" in str(e) or "foreign key constraint" in str(e).lower():
                print(f"Error: Tour '{tour}' does not exist in room '{room}'. Cannot add ban '{ban}'.")
            else:
                print(f"Failed to add ban '{ban}': {e}")

    return added

def remove_tour_ban(room: str, tour: str, ban: str):
    """
    Remove a single ban from a tour.
    Returns True if the ban was removed, False if it didn't exist.
    """
    try:
        resp = supabase.rpc(
            "remove_ban",
            {
                "p_room_name": room,
                "p_tour_name": tour,
                "p_ban_name": ban
            }
        ).execute()

        return resp.data  # True if removed, False if not found
    except Exception as e:
        print(f"Failed to remove ban '{ban}': {e}")
        return False


def remove_tour_bans(room: str, tour: str, bans_str: str):
    """
    Remove one or multiple bans from a tour.
    `bans_str` can be comma-separated for multiple bans.
    Returns a list of successfully removed bans.
    """
    if not bans_str:
        return []

    bans_list = [b.strip() for b in bans_str.split(",") if b.strip()]
    removed = []

    for ban in bans_list:
        if remove_tour_ban(room, tour, ban):
            removed.append(ban)
        else:
            print(f"Ban '{ban}' not found or failed to remove")

    return removed

def get_all_tours(room: str):
    """
    Get all tour internal names for a room.
    Returns a list of tour_internalname strings.
    """
    if room == "monotypeom":
        room = "monotype"  # monotypeom shares same tours as monotype
    try:
        resp = supabase.rpc(
            "get_all_tours",
            {
                "p_room_name": room
            }
        ).execute()
        
        return [tour['tour_internalname'] for tour in resp.data] if resp.data else []
    except Exception as e:
        print(f"Failed to get all tours for room '{room}': {e}")
        return []

def get_monothreat_tours(room: str):
    """
    Get all monothreat tour names from the database for random selection.
    Caches results to avoid repeated queries.
    """
    global monothreat_tours_cache
    if room == "monotypeom":
        room = "monotype"  # monotypeom shares same tours as monotype
    if room in monothreat_tours_cache:
        return monothreat_tours_cache[room]
    
    all_tours = get_all_tours(room)
    
    if all_tours:
        monothreat_tours = [t for t in all_tours if t.startswith('monothreat')]
        monothreat_tours_cache[room] = monothreat_tours
        return monothreat_tours
    
    return []

def get_tour_bans_for_html(room: str, tour: str):
    """
    Get tour bans and format as HTML.
    Returns None if the tour does not exist.
    """
    if room == "monotypeom":
        room = "monotype"  # monotypeom shares same tours as monotype
    bans_data = get_tour_bans(room, tour)

    # If tour does not exist → return nothing
    if bans_data is None:
        return None

    # Normalize bans_data into list[str]
    if isinstance(bans_data, str):
        bans_data = [b.strip() for b in bans_data.split(",") if b.strip()]

    clauses = []
    bans = []
    unbans = []

    for value in bans_data:
        value = value.strip()
        lower_value = value.lower()
        if value.startswith("-"):
            bans.append(value[1:])
        elif value.startswith("+"):
            unbans.append(value[1:])
        else:
            clauses.append(value)

    # If absolutely nothing to show, return nothing
    if not clauses and not bans and not unbans:
        return None

    def render_section(title, items, bg, border):
        if not items:
            return ""
        # Title case each item in the list
        titled_items = [item.title() for item in sorted(set(items))]
        return f"""
        <div style="
            margin-bottom: 0.75rem;
            padding: 0.6rem 0.75rem;
            border: 1px solid {border};
            border-radius: 4px;
            background: {bg};
        ">
          <strong>{title}</strong><br>
          <div style="margin-top: 0.3rem;">
            {', '.join(titled_items)}
          </div>
        </div>
        """

    header = f"{tour.capitalize()} {room.capitalize()}"

    body_html = (
        render_section("Clauses", clauses, "rgba(59, 130, 246, 0.15)", "rgba(59, 130, 246, 0.3)")
        + render_section("Bans", bans, "rgba(239, 68, 68, 0.15)", "rgba(239, 68, 68, 0.3)")
        + render_section("Unbans", unbans, "rgba(34, 197, 94, 0.15)", "rgba(34, 197, 94, 0.3)")
    )

    return f"""
    <div style="margin-bottom: 1rem;">
      <div style="
          border: .125rem solid rgba(128, 128, 128, 0.4);
          border-bottom: none;
          padding: .5rem;
          font-weight: bold;
          text-align: center;
          background: rgba(128, 128, 128, 0.1);
      ">
        {header}
      </div>
      <div style="border: .125rem solid rgba(128, 128, 128, 0.4); padding: 1rem;">
        {body_html}
      </div>
    </div>
    """.strip()

def build_tour_code(room: str, tour: str) -> str:
    """
    Build the tour code string for a given room and tour.
    Returns the formatted code string or None if tour not found.
    """
    
    tour_info = get_tour_info(room, tour)
    if not tour_info:
        return None
    
    bans = get_tour_bans(room, tour)
    
    # Build the code string
    code_parts = []
    
    # Line 1: /tour new
    code_parts.append(
        f"/tour new {tour_info['tour_type']}, elim,,,{tour_info['tour_name']}"
    )
    
    # Line 2: misc_commands (if exists)
    if tour_info['misc_commands']:
        code_parts.append(tour_info['misc_commands'])
    
    # Line 3: /tour rules (if bans exist)
    if bans:
        code_parts.append(f"/tour rules {bans}")
    
    # Line 4: .official
    excluded_tours = ("National Dex OU", "Monotype Cats")

    if not any(x in tour_info["tour_name"] for x in excluded_tours):
        code_parts.append(".official")

    
    # Join with \n
    return "\n".join(code_parts)

def main():
    room = "monotype"
    code = get_monothreat_tours(room)
    selected_tour = random.choice(code)
    get_html=get_tour_bans_for_html(room, selected_tour)
    print(get_html)

if __name__ == "__main__":
    main()