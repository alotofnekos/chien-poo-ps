import json

CHAMPION_POINTS = 3
RUNNER_UP_POINTS = 2
SEMIFINALIST_POINTS = 1


def extract_placements(end_line: str) -> dict:
    """
    Parse a `|tournament|end|<json>` line and return placements:

        {
            "champion": "playerA",
            "runner_up": "playerB",
            "semifinalists": ["playerC", "playerD"]
        }

    Assumes single elimination. The bracket is a binary tree where each node
    represents a match: node["team"] is the winner of that match, and
    node["children"] are the two subtrees (matches/players) that fed into it.

        root            -> the final.            root["team"]      = champion
        root["children"] -> the two semifinals.   loser of each     = semifinalist
                                                   winner of each    = one finalist
                                                   (the non-champ one = runner_up)

    This only looks at the top two tree levels, so it works regardless of
    how many earlier rounds exist beneath the semifinals.

    Returns an empty dict if the line can't be parsed or has no bracket data.
    """
    try:
        data = json.loads(end_line.split("|tournament|end|", 1)[1])
    except Exception as e:
        print("⚠️ Could not parse tournament end JSON:", e)
        return {}

    root = data.get("bracketData", {}).get("rootNode")
    if not root:
        return {}

    champ = data.get("results", [[None]])[0][0]
    if not champ:
        return {}

    placements = {
        "champion": champ,
        "runner_up": None,
        "semifinalists": []
    }

    semis = root.get("children", [])
    if len(semis) != 2:
        # No semifinal round to read (e.g. 2-player bracket) — champion only.
        return placements

    for semi in semis:
        semi_winner = semi.get("team")

        if semi_winner != champ:
            # This semifinal's winner went on to lose the final.
            placements["runner_up"] = semi_winner

        # The loser of this semifinal is whichever of its two children
        # did NOT win the semifinal.
        semi_children = semi.get("children", [])
        if len(semi_children) == 2:
            a, b = semi_children
            loser = b.get("team") if a.get("team") == semi_winner else a.get("team")
            if loser:
                placements["semifinalists"].append(loser)

    return placements


def get_points(placements: dict) -> dict:
    """
    Turn a placements dict into {player: points} using fixed values:
        champion -> 3, runner_up -> 2, semifinalist -> 1
    """
    points = {}

    if placements.get("champion"):
        points[placements["champion"]] = CHAMPION_POINTS

    if placements.get("runner_up"):
        points[placements["runner_up"]] = RUNNER_UP_POINTS

    for sf in placements.get("semifinalists", []):
        points[sf] = SEMIFINALIST_POINTS

    return points


def process_tournament_end(end_line: str) -> dict:
    """
    One-shot helper: given the |tournament|end| line, return both
    placements and points together.

        {
            "champion": "...",
            "runner_up": "...",
            "semifinalists": [...],
            "points": {player: pts, ...}
        }
    """
    placements = extract_placements(end_line)
    if not placements:
        return {}

    placements["points"] = get_points(placements)
    return placements