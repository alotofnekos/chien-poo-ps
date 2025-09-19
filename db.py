import math
from collections import defaultdict
from supabase import create_client
import os

# ---------- CONFIG ----------
BASE_POINTS = 15
INCREMENT = 3

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

        elif "|tournament|start|" in line:
            self.player_count = int(parts[3])
            self.total_rounds = math.ceil(math.log2(self.player_count))

        elif "|tournament|battlestart|" in line:
            p1, p2 = parts[3], parts[4]
            self.matches.append({"p1": p1, "p2": p2, "winner": None, "loser": None, "round": None})

        elif "|tournament|battleend|" in line:
            p1, p2, result = parts[3], parts[4], parts[5]
            for m in self.matches:
                if {m["p1"], m["p2"]} == {p1, p2} and m["winner"] is None:
                    winner = p1 if result == "win" else p2
                    loser = p2 if result == "win" else p1
                    m["winner"], m["loser"] = winner, loser

                    round_num = max(self.round_counter[winner], self.round_counter[loser]) + 1
                    m["round"] = round_num
                    self.round_counter[winner] = round_num
                    self.round_counter[loser] = round_num

                    self.points[winner] += round_points(round_num)
                    self.rounds_survived[winner] = max(self.rounds_survived[winner], round_num)
                    self.rounds_survived[loser] = max(self.rounds_survived[loser], round_num)
                    break

        elif "|tournament|end|" in line:
            self.finished = True

    def apply_resistance(self):
        for m in self.matches:
            if m["winner"] and m["loser"]:
                loser, opp = m["loser"], m["winner"]
                wr = self.rounds_survived[opp] / self.total_rounds if self.total_rounds > 0 else 0
                resistance_points = int(round_points(1) * wr * 0.5)
                self.points[loser] += resistance_points

    def get_scoreboard(self):
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
                wrs = [self.rounds_survived[o] / self.total_rounds for o in opps]
                resistance[player] = sum(wrs) / len(wrs) if wrs else 0.0
            else:
                resistance[player] = 0.0

        scoreboard = [
            [player, self.points[player], round(resistance[player], 2)]
            for player in self.points.keys() | self.players
        ]
        scoreboard.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return scoreboard


# ---------- SUPABASE ----------
def update_db(scoreboard, room):
    supabase.table("results").upsert([
        {
            "username": player,
            "points": pts,
            "resistance": res,
            "room": room
        }
        for player, pts, res in scoreboard
    ]).execute()


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
    resp = supabase.table("results") \
        .select("*") \
        .eq("room", room) \
        .order("points", desc=True) \
        .limit(limit) \
        .execute()

    rows = resp.data or []

    html = [
        f"""
        <div style="width:75%;margin:2em auto;font-family:Arial,sans-serif;text-align:center;">
            <div style="background:linear-gradient(90deg,#6c63ff,#8e7dff);color:white;
                        font-size:1.5em;font-weight:bold;padding:10px;
                        border-radius:8px 8px 0 0;margin-bottom:0;">
                Leaderboard — {room}
            </div>
            <table style="border-collapse:collapse;width:100%;margin:0 auto;">
                <thead>
                    <tr style="background-color:#6c63ff;color:white;">
                        <th style="border:1px solid #ccc;padding:8px 12px;">Rank</th>
                        <th style="border:1px solid #ccc;padding:8px 12px;">User</th>
                        <th style="border:1px solid #ccc;padding:8px 12px;">Points</th>
                        <th style="border:1px solid #ccc;padding:8px 12px;">Resistance</th>
                    </tr>
                </thead>
                <tbody>
        """
    ]

    for i, row in enumerate(rows, start=1):
        bg_color = "#e6f0ff" if i % 2 == 0 else "#f3e6ff"
        html.append(
            f"<tr style='background-color:{bg_color};'>"
            f"<td style='border:1px solid #ccc;padding:8px 12px;text-align:center;'>{i}</td>"
            f"<td style='border:1px solid #ccc;padding:8px 12px;text-align:center;'>{row['user']}</td>"
            f"<td style='border:1px solid #ccc;padding:8px 12px;text-align:center;'>{row['points']}</td>"
            f"<td style='border:1px solid #ccc;padding:8px 12px;text-align:center;'>{round(row['resistance'], 2)}</td>"
            "</tr>"
        )

    html.append("</tbody></table></div>")
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
