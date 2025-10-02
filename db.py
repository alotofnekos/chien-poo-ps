import math
from collections import defaultdict
from supabase import create_client
import os
import json
from datetime import datetime



# ---------- CONFIG ----------
BASE_POINTS = 10
INCREMENT = 2

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- HELPERS ----------
def round_points(round_number: int) -> int:
    return BASE_POINTS + (round_number - 1) * INCREMENT


# ---------- TOURNAMENT STATE ----------
class TournamentState:
    def __init__(self, room: str):
        self.room = room
        self.reset()

    def reset(self):
        self.matches = []
        self.points = defaultdict(int)
        self.round_counter = defaultdict(int)
        self.rounds_survived = defaultdict(int)
        self.players = set()
        self.player_count = 0
        self.total_rounds = 0
        self.finished = False

    def handle_line(self, line: str):
        parts = line.strip().split("|")

        if "|tournament|create|" in line:
            self.reset()

        elif "|tournament|join|" in line:
            player = parts[3]
            self.players.add(player)

        elif "|tournament|leave|" in line:
            player = parts[3]
            self.players.discard(player)  # safer than remove()

        elif "|tournament|start|" in line:
            self.player_count = int(parts[3])
            self.total_rounds = math.ceil(math.log2(self.player_count))

        elif "|tournament|battlestart|" in line:
            p1, p2 = parts[3], parts[4]
            self.matches.append({
                "p1": p1,
                "p2": p2,
                "winner": None,
                "loser": None,
                "round": None
            })

        elif "|tournament|battleend|" in line:
            p1, p2, result = parts[3], parts[4], parts[5]
            for m in self.matches:
                if {m["p1"], m["p2"]} == {p1, p2} and m["winner"] is None:
                    winner = p1 if result == "win" else p2
                    loser = p2 if result == "win" else p1
                    m["winner"], m["loser"] = winner, loser

                    round_num = max(self.round_counter[winner],
                                    self.round_counter[loser]) + 1
                    m["round"] = round_num

                    self.round_counter[winner] = round_num
                    self.round_counter[loser] = round_num

                    # Give points for advancing
                    self.points[winner] += round_points(round_num)

                    # Track survival depth
                    self.rounds_survived[winner] = max(self.rounds_survived[winner], round_num)
                    self.rounds_survived[loser] = max(self.rounds_survived[loser], round_num)
                    break

        elif "|tournament|end|" in line:
            self.finished = True

            # ✅ Award placement bonuses
            if self.matches:
                final_match = max(self.matches, key=lambda m: m["round"] or 0)
                if final_match["winner"] and final_match["loser"]:
                    champ = final_match["winner"]
                    runner_up = final_match["loser"]

                    # Bonus for 1st place
                    self.points[champ] += 10  

                    # Bonus for 2nd place
                    self.points[runner_up] += 5


    def apply_resistance(self):
        for m in self.matches:
            if m["winner"] and m["loser"]:
                loser, opp = m["loser"], m["winner"]
                wr = self.rounds_survived[opp] / self.total_rounds if self.total_rounds > 0 else 0
                resistance_points = int(round_points(1) * wr * 0.5)
                self.points[loser] += resistance_points

    def get_scoreboard(self):
        """Return scoreboard with points and resistance (0–1 only)."""
        resistance = defaultdict(float)

        for player in self.points.keys() | self.players:
            opps = []
            for m in self.matches:
                if m["winner"] is None:
                    continue
                if m["p1"] == player:
                    opps.append(m["p2"])
                elif m["p2"] == player:
                    opps.append(m["p1"])

            if opps and self.total_rounds > 0:
                # normalized opponent WRs (always between 0 and 1)
                wrs = [
                    self.rounds_survived[o] / self.total_rounds
                    for o in opps
                    if self.total_rounds > 0
                ]
                resistance[player] = round(sum(wrs) / len(wrs), 2)
            else:
                resistance[player] = 0.0

        # build scoreboard as [player, points, resistance]
        scoreboard = [
            [player, self.points[player], resistance[player]]
            for player in self.points.keys() | self.players
        ]
        scoreboard.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return scoreboard

# ----------- PARTBOTLIKE BEHAV -----
def apply_placement_points_from_json(state: TournamentState, line: str):
    """
    #Apply placement-only points using the `bracketData` JSON from
    #the |tournament|end| line itself.

    #Champion = +3
    #Runner-up = +2
    #Semifinalists = +1 each
    """
    try:
        data = json.loads(line.split("|tournament|end|", 1)[1])
    except Exception as e:
        print("⚠️ Could not parse tournament end JSON:", e)
        return

    bracket = data.get("bracketData", {}).get("rootNode")
    if not bracket:
        return

    # Champion = rootNode["team"] if marked win
    champ = data.get("results", [[None]])[0][0]
    if not champ:
        return

    state.points[champ] += 3

    # Runner-up = opponent in the final match
    children = bracket.get("children", [])
    if len(children) == 2:
        left, right = children
        runner_up = (
            left.get("team") if left.get("team") != champ else right.get("team")
        )
        if runner_up:
            state.points[runner_up] += 2

        # Semifinalists = losers of the two semifinals
        semifinalists = []
        for child in children:
            if "children" in child:
                # semifinal match
                for sf in child["children"]:
                    if sf.get("team") and sf.get("team") != child.get("team"):
                        semifinalists.append(sf["team"])

        for sf in semifinalists:
            state.points[sf] += 1


# ---------- SUPABASE ----------
def update_db(scoreboard, room):
    for player, pts, res in scoreboard:
        # Add points using the existing helper
        new_points = add_points(room, player, pts)

        # Fetch current resistance for weighted average
        resp = supabase.table("tour_lb") \
            .select("resistance") \
            .eq("username", player) \
            .eq("room", room) \
            .execute()

        current_res = resp.data[0]["resistance"] if resp.data else 0.0

        # Weighted average: old res weighted by old points, new res weighted by new points just added
        if new_points > 0:
            # current_points = new_points - pts
            current_points = new_points - pts
            weighted_res = ((current_res * current_points) + (res * pts)) / new_points
        else:
            weighted_res = res

        # Update only the resistance
        supabase.table("tour_lb").update({
            "resistance": weighted_res
        }).eq("username", player).eq("room", room).execute()

def add_points(room: str, username: str, points: int):
    """
    Add points to a user's total in a given room.
    If the user doesn't exist yet, they are inserted.
    """
    # Fetch current points for this user in this room
    resp = supabase.table("tour_lb") \
        .select("points") \
        .eq("username", username) \
        .eq("room", room) \
        .execute()

    current_points = resp.data[0]["points"] if resp.data else 0
    new_points = current_points + points

    # Upsert back into the table
    supabase.table("tour_lb").upsert({
        "username": username,
        "room": room,
        "points": new_points
    }).execute()

    return new_points

def archive_monthly_results(room: str):
    """
    Move all records for this month in a given room
    from tour_lb → tour_lb_archive,
    tagging them with a YYYYMM month,
    then delete them from tour_lb.
    """
    now = datetime.utcnow()
    month_tag = now.strftime("%Y%m")  # e.g. "202509"

    # 1. Fetch all rows for the room
    resp = supabase.table("tour_lb") \
        .select("username, room, points") \
        .eq("room", room) \
        .execute()

    rows = resp.data or []
    if not rows:
        print(f"⚠️ No rows found for room {room}, nothing to archive.")
        return

    # 2. Add month field
    archive_rows = [{**r, "month": month_tag} for r in rows]

    # 3. Insert into the archive table
    supabase.table("tour_lb_archive").upsert(archive_rows).execute()

    # 4. Delete from main table
    supabase.table("tour_lb").delete().eq("room", room).execute()

    print(f"✅ Archived {len(rows)} rows for room '{room}' into tour_lb_archive (month={month_tag}), then cleared from tour_lb.")

# ---------- MULTI-ROOM MANAGER ----------
class TournamentManager:
    def __init__(self):
        self.states = {}

    def handle_line(self, room: str, line: str):
        if room not in self.states:
            self.states[room] = TournamentState(room)

        state = self.states[room]
        state.handle_line(line)

        if state.finished:
            state.apply_resistance()
            scoreboard = state.get_scoreboard()
            update_db(scoreboard, room)
            print(f"Tournament in {room} finished. Final scoreboard:")
            for row in scoreboard:
                print(row)
            state.reset()


def get_leaderboard_html(room: str, limit: int = 20) -> str:
    """Fetch leaderboard from Supabase and return as styled HTML table (per-room only, inline styles)."""
    resp = supabase.table("tour_lb") \
        .select("*") \
        .eq("room", room) \
        .order("points", desc=True) \
        .limit(limit) \
        .execute()

    rows = resp.data or []

    html = [
        f"<h2>Leaderboard — {room}</h2>",
        "<table border='1' cellpadding='5' cellspacing='0'>",
        "<thead><tr><th>Rank</th><th>User</th><th>Points</th></tr></thead>",
        "<tbody>"
    ]

    for i, row in enumerate(rows, start=1):
        html.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{row['username']}</td>"
            f"<td>{row['points']}</td>"
            "</tr>"
        )

    html.append("</tbody></table>")
    return "\n".join(html)




def process_tourlogs(room: str, log_lines: list[str]):
    """
    Process a complete set of tournament logs and return the final scoreboard.
    """
    manager = TournamentManager()

    for line in log_lines:
        manager.handle_line(room, line)

    state = manager.states.get(room)
    if state and state.finished:
        state.apply_resistance()
        return state.get_scoreboard()

    return []


def save_tournament_results(room: str, log_lines: list[str]):
    """
    Process logs and immediately save the final scoreboard to Supabase.
    """
    scoreboard = process_tourlogs(room, log_lines)
    if scoreboard:
        update_db(scoreboard, room)
        print(f"✅ Saved tournament results for room {room}")
    else:
        print(f"⚠️ No results to save for room {room}")
    return scoreboard
