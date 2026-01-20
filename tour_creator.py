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


def get_tour_bans(room: str, tour: str):
    """
    Get tour bans as a comma-separated string
    """
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
        resp = supabase.rpc(
            "add_ban",
            {
                "p_room_name": room,
                "p_tour_name": tour,
                "p_ban_name": ban
            }
        ).execute()

        # Check if resp.data is truthy (RPC returns True/False)
        if resp.data:
            added.append(ban)
        else:
            # RPC failed (likely already exists or some DB error)
            print(f"Failed to add ban '{ban}': {resp.data}")

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


def get_tour_bans_for_html(room: str, tour: str):
    """
    Get tour bans and format as HTML.
    Returns None if the tour does not exist.
    """

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

        if "clause" in lower_value:
            clauses.append(value)
        elif value.startswith("-"):
            bans.append(value[1:])
        elif value.startswith("+"):
            unbans.append(value[1:])

    # If absolutely nothing to show, return nothing
    if not clauses and not bans and not unbans:
        return None

    def render_section(title, items, bg, border):
        if not items:
            return ""
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
            {', '.join(sorted(set(items)))}
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



def main():
    room = "monotype"
    tour = "ubers"
    bans = "-Flutter Mane"
    success = remove_tour_ban(room, tour, bans)
    print("Ban removed:", success)
    bans_list = get_tour_bans(room, tour)

if __name__ == "__main__":
    main()