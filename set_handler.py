import sys
import requests
import re
import time

#   CACHE
sets_cache = {}
CACHE_DURATION = 30 * 60  # 30 minutes

#   NORMALIZATION
def normalize_name(name: str):
    return re.sub(r"[^a-z0-9]", "", name.lower())

#   FETCH SETS
def fetch_sets_data(format_name: str):
    # cache
    entry = sets_cache.get(format_name)
    if entry and (time.time() - entry["timestamp"] < CACHE_DURATION):
        return entry["data"]

    url = f"https://pkmn.github.io/smogon/data/sets/{format_name}.json"
    print(f"[INFO] Fetching sets: {url}")

    try:
        r = requests.get(url)
        if not r.ok:
            print(f"[ERROR] Format '{format_name}' not found (HTTP {r.status_code})")
            return None
        
        data = r.json()
        
        sets_cache[format_name] = {
            "timestamp": time.time(),
            "data": data
        }
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch format '{format_name}': {e}")
        return None
    except ValueError as e:
        print(f"[ERROR] Invalid JSON response for format '{format_name}': {e}")
        return None

#   FIND POKÉMON
def find_pokemon_sets(sets_data, name: str):
    target = normalize_name(name)
    for species, sets in sets_data.items():
        if normalize_name(species) == target or target in normalize_name(species):
            return {"species": species, "sets": sets}
    return None

#   URL BUILDER
def get_smogon_gen_code(gen: int):
    mapping = {
        9: "sv",
        8: "ss",
        7: "sm",
        6: "xy",
        5: "bw",
        4: "dp",
        3: "rs",
        2: "gs",
        1: "rb"
    }
    return mapping.get(gen, "sv")


def build_smogon_url(species: str, format_name: str):
    m = re.match(r"^gen(\d)([a-z0-9]+)$", format_name, re.I)
    if not m:
        return None
    gen = int(m.group(1))
    tier = m.group(2).lower()
    gen_code = get_smogon_gen_code(gen)
    slug = species.lower().replace(" ", "-").replace("'", "")
    return f"https://www.smogon.com/dex/{gen_code}/pokemon/{slug}/{tier}/"

#   ITERATE SETS
def iterate_sets(species: str, sets_obj):
    if isinstance(sets_obj, dict):
        for name, data in sets_obj.items():
            yield name, data
    elif isinstance(sets_obj, list):
        for i, data in enumerate(sets_obj, start=1):
            name = data.get("name") or f"Set {i}"
            yield name, data

#   FILTER SETS
def filter_sets(sets_obj, query="", mono_type=""):
    q = query.lower()
    mt = mono_type.lower().strip()
    for name, data in iterate_sets("species", sets_obj):
        lname = name.lower()
        if q and q not in lname:
            continue
        if mt and f"({mt})" not in lname:
            continue
        yield name, data

#   FORMAT MOVESET
def format_moveset(species: str, set_name: str, data: dict, include_header: bool = True):
    def fmt_evs(ev_obj):
        order = ["hp", "atk", "def", "spa", "spd", "spe"]
        if isinstance(ev_obj, dict):
            parts = []
            for k in order:
                v = ev_obj.get(k)
                if isinstance(v, int) and v > 0:
                    parts.append(f"{v} {k.upper()}")
            return " / ".join(parts)
        return str(ev_obj)

    # Items go after species on same line separated by ' / '
    items = data.get("item")
    item_str = ""
    if isinstance(items, list):
        item_str = " / ".join(str(i) for i in items)
    elif isinstance(items, str):
        item_str = items

    lines = []
    if include_header:
        lines.append("!code")
    
    if item_str:
        lines.append(f"{species} @ {item_str}")
    else:
        lines.append(f"{species} ({set_name})")

    # Ability
    if data.get("ability"):
        lines.append(f"Ability: {data['ability']}")

    # EVs
    evs = data.get("evs", {})
    ev_lines = []
    if isinstance(evs, list) and evs:
        # multiple EV spreads
        for ev in evs:
            ev_lines.append(fmt_evs(ev))
        if ev_lines:
            lines.append(f"EVs: {' OR '.join(ev_lines)}")
    else:
        ev_line = fmt_evs(evs)
        if ev_line:
            lines.append(f"EVs: {ev_line}")

    # Nature
    nature = data.get("nature")
    if nature:
        if isinstance(nature, list):
            lines.append(" / ".join([f"({n}) Nature" for n in nature]))
        else:
            lines.append(f"{nature} Nature")

    # Tera Type
    tera = data.get("teratypes")
    if tera:
        if isinstance(tera, list):
            lines.append(f"Tera Type: {' / '.join(tera)}")
        else:
            lines.append(f"Tera Type: {tera}")

    # IVs
    ivs = data.get("ivs", {})
    iv_line = ""
    if isinstance(ivs, dict):
        iv_line = " / ".join(f"{v} {k.upper()}" for k, v in ivs.items() if isinstance(v, int) and v < 31)
    elif isinstance(ivs, list):
        iv_line = " / ".join(str(v) for v in ivs)
    if iv_line:
        lines.append(f"IVs: {iv_line}")

    # Moves
    moves = data.get("moves", [])
    for m in moves:
        if isinstance(m, list):
            lines.append("- " + " / ".join(m))
        else:
            lines.append(f"- {m}")

    return "\n".join(lines)

def parse_command_and_get_sets(command_string, room=""):
    """
    Parse a command string like 'meow show set Gallade gen9monotype (Psychic)'
    and return formatted movesets.
    
    Args:
        command_string (str): The full command string to parse
        
    Returns:
        list: List of formatted moveset strings, or None if error
    """
    parts = command_string.split()
    
    if len(parts) < 4:
        # Missing arguments
        return None

    cmd = parts[0].lower()
    action1 = parts[1].lower()
    action2 = parts[2].lower()

    if cmd != "meow" or action1 != "show" or action2 != "set":
        # Invalid command
        return None
    
    # Find where the pokemon name ends by looking for format indicators
    remaining_parts = parts[3:]
    pokemon_parts = []
    format_idx = None
    
    for i, part in enumerate(remaining_parts):
        # Check if this part starts with "gen" or is a filter in parentheses
        if part.lower().startswith("gen") or part.startswith("("):
            format_idx = i
            break
        pokemon_parts.append(part)
    
    # If no format found, all remaining parts are pokemon name
    if format_idx is None:
        # Check if the last part could be a filter instead of part of pokemon name
        if len(pokemon_parts) > 1:
            # Check if last part looks like a type filter (capitalized, single word, not a pokemon name component)
            last_part = pokemon_parts[-1]
            if last_part[0].isupper() and len(pokemon_parts) > 1:
                # Treat last part as a potential mono_filter
                pokemon = " ".join(pokemon_parts[:-1])
                mono_filter = last_part
            else:
                pokemon = " ".join(pokemon_parts)
                mono_filter = ""
        else:
            pokemon = " ".join(pokemon_parts)
            mono_filter = ""
        
        # Determine default format based on room
        if room.lower() == "monotype":
            format_name = "gen9monotype"
        elif room.lower() == "nationaldexmonotype":
            format_name = "gen9nationaldexmonotype"
        else:
            format_name = "gen9monotype"
        set_filter = ""
    else:
        pokemon = " ".join(pokemon_parts)
        format_name = remaining_parts[format_idx] if format_idx < len(remaining_parts) else "gen9monotype"
        
        set_filter = ""
        mono_filter = ""
        
        # detect additional filters after format
        for arg in remaining_parts[format_idx + 1:]:
            if arg.startswith("(") and arg.endswith(")"):
                mono_filter = arg.strip("()")
            else:
                set_filter = arg

    print(f"[INFO] Using format: {format_name}")
    print(f"[INFO] Searching for: {pokemon}")
    if mono_filter:
        print(f"[INFO] Filtering by type: {mono_filter}")

    sets_data = fetch_sets_data(format_name)
    if not sets_data:
        return None

    result = find_pokemon_sets(sets_data, pokemon)

    if not result:
        print(f"[ERROR] No sets found for '{pokemon}' in {format_name}")
        return None

    species = result["species"]
    sets_obj = result["sets"]

    url = build_smogon_url(species, format_name)
    if url:
        print(f"Smogon URL: {url}\n")

    matched = list(filter_sets(sets_obj, query=set_filter, mono_type=mono_filter))
    if not matched:
        print("[ERROR] No matching sets with given filters.")
        return None

    formatted_sets = []
    for i, (set_name, set_data) in enumerate(matched):
        formatted = format_moveset(species, set_name, set_data, include_header=(i == 0))
        formatted_sets.append(formatted)
    
    return formatted_sets


def main():
    if len(sys.argv) < 4:
        print("Usage: meow show set <pokemon> [format] [set filter] [monotype]")
        return

    # Reconstruct command string from argv
    command_string = " ".join(sys.argv[1:])
    
    formatted_sets = parse_command_and_get_sets(command_string)
    
    if formatted_sets:
        for formatted_set in formatted_sets:
            print(formatted_set)
            print()

if __name__ == "__main__":
    main()