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

        elif "|tournament|leave|" in line:
            player = parts[3]
            self.players.remove(player)

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
    supabase.table("tour_lb").upsert([
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
        "<thead><tr><th>Rank</th><th>User</th><th>Points</th><th>Resistance</th></tr></thead>",
        "<tbody>"
    ]

    for i, row in enumerate(rows, start=1):
        html.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{row['username']}</td>"
            f"<td>{row['points']}</td>"
            f"<td>{round(row['resistance'], 2)}</td>"
            "</tr>"
        )

    html.append("</tbody></table>")
    return html




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
