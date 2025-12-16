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
def filter_sets(sets_obj, query="", mono_type="", paren_filter=""):
    """
    Filter sets by query, mono_type, and/or paren_filter.
    - query: matches set name (without parentheses, case-insensitive)
    - mono_type: matches type in parentheses like "(Psychic)"
    - paren_filter: matches ability, item, moves, set name, or parentheses content
    """
    q = query.lower()
    mt = mono_type.lower().strip()
    pf = paren_filter.lower().strip()
    
    for name, data in iterate_sets("species", sets_obj):
        lname = name.lower()
        
        # Check query match (non-parentheses part)
        if q and q not in lname:
            continue
        
        # Check mono_type match (specific type filter)
        if mt and f"({mt})" not in lname:
            continue
        
        # Check paren_filter match (set name, ability, item, moves, or parentheses content)
        if pf:
            match_found = False
            
            # Check set name
            if pf in lname:
                match_found = True
            
            # Check ability
            if not match_found and data.get("ability"):
                ability = str(data["ability"]).lower()
                if pf in ability:
                    match_found = True
            
            # Check item
            if not match_found and data.get("item"):
                item = data["item"]
                if isinstance(item, list):
                    item_str = " ".join(str(i) for i in item).lower()
                else:
                    item_str = str(item).lower()
                if pf in item_str:
                    match_found = True
            
            # Check moves
            if not match_found and data.get("moves"):
                moves = data["moves"]
                for move in moves:
                    if isinstance(move, list):
                        move_str = " ".join(str(m) for m in move).lower()
                    else:
                        move_str = str(move).lower()
                    if pf in move_str:
                        match_found = True
                        break
            
            # Check parentheses content in set name
            if not match_found:
                paren_match = re.search(r'\(([^)]+)\)', lname)
                if paren_match:
                    paren_content = paren_match.group(1).lower()
                    if pf in paren_content:
                        match_found = True
            
            if not match_found:
                continue
        
        yield name, data

#   FORMAT MOVESET
def format_moveset(species: str, set_name: str, data: dict, include_header: bool = True):
    def fmt_evs(ev_obj):
        order = [
            ("hp", "HP"),
            ("atk", "Atk"),
            ("def", "Def"),
            ("spa", "SpA"),
            ("spd", "SpD"),
            ("spe", "Spe"),
        ]
        if isinstance(ev_obj, dict):
            parts = []
            for key, label in order:
                v = ev_obj.get(key)
                if isinstance(v, int) and v > 0:
                    parts.append(f"{v} {label}")
            return " / ".join(parts)
        return str(ev_obj)
    items = data.get("item")
    slug = species.lower().replace(" ", "-")

    if items and items.endswith("ite"):
        slug += "-mega"


    items = data.get("item")
    item_str = ""
    if isinstance(items, list):
        item_str = " / ".join(str(i) for i in items)
    elif isinstance(items, str):
        item_str = items

    # ---- Sprite + Pokémon header (only once) ----
    header_html = ""
    if include_header:
        header_html = f"""
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" style="padding-bottom: .5rem;">
      <img src="https://www.smogon.com/dex/media/sprites/xy/{slug}.gif"
           alt="{species}" width="96" height="96">
    </td>
  </tr>
</table>
""".strip()

    # ---- Set body ----
    body_parts = []

    if item_str:
        body_parts.append(f"<div><b>{species}</b> @ {item_str}</div>")
    else:
        body_parts.append(f"<div><b>{species}</b></div>")

    if data.get("ability"):
        body_parts.append(f"<div>Ability: {data['ability']}</div>")

    evs = data.get("evs", {})
    ev_str = fmt_evs(evs)
    if ev_str:
        body_parts.append(f"<div>EVs: {ev_str}</div>")

    nature = data.get("nature")
    if nature:
        body_parts.append(f"<div>{nature} Nature</div>")

    tera = data.get("teratypes")
    if tera:
        if isinstance(tera, list):
            body_parts.append(f"<div>Tera Type: {' / '.join(tera)}</div>")
        else:
            body_parts.append(f"<div>Tera Type: {tera}</div>")

    ivs = data.get("ivs", {})
    if isinstance(ivs, dict):
        iv_str = " / ".join(
            f"{v} {k.upper()}" for k, v in ivs.items()
            if isinstance(v, int) and v < 31
        )
        if iv_str:
            body_parts.append(f"<div>IVs: {iv_str}</div>")

    moves = data.get("moves", [])
    if moves:
        for m in moves:
            if isinstance(m, list):
                body_parts.append(f"<div>- {' / '.join(m)}</div>")
            else:
                body_parts.append(f"<div>- {m}</div>")

    body_html = "\n".join(body_parts)

    # ---- Set container ----
    set_html = f"""
<div style="margin-bottom: 1rem;">
  <div style="border: .125rem solid #000; border-bottom: none; padding: .5rem; font-weight: bold; text-align: center;">
    {set_name}
  </div>
  <div style="border: .125rem solid #000; padding: 1rem;">
    {body_html}
  </div>
</div>
""".strip()

    return header_html + "\n" + set_html


def parse_command_and_get_sets(command_string, room=""):
    """
    Parse a command string like:
    - 'meow show set Gallade gen9monotype (Psychic)'
    - 'meow show set Latias gen9monotype (Scarf)'
    
    Only filters in parentheses are accepted (aside from format).
    
    Args:
        command_string (str): The full command string to parse
        room (str): The room name for default format selection
        
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
        pokemon = " ".join(pokemon_parts)
        
        # Determine default format based on room
        if room.lower() == "monotype":
            format_name = "gen9monotype"
        elif room.lower() == "nationaldexmonotype":
            format_name = "gen9nationaldexmonotype"
        else:
            format_name = "gen9monotype"
        mono_filter = ""
        paren_filter = ""
    else:
        pokemon = " ".join(pokemon_parts)
        format_name = remaining_parts[format_idx] if format_idx < len(remaining_parts) else "gen9monotype"
        
        mono_filter = ""
        paren_filter = ""
        
        # detect filters in parentheses after format
        for arg in remaining_parts[format_idx + 1:]:
            if arg.startswith("(") and arg.endswith(")"):
                # Content in parentheses - could be type OR set filter
                filter_content = arg.strip("()")
                
                # List of known Pokemon types for monotype filtering
                known_types = [
                    "normal", "fire", "water", "electric", "grass", "ice",
                    "fighting", "poison", "ground", "flying", "psychic", "bug",
                    "rock", "ghost", "dragon", "dark", "steel", "fairy"
                ]
                
                # Check if it's a type (case-insensitive match)
                if filter_content.lower() in known_types:
                    mono_filter = filter_content
                else:
                    # Otherwise treat as general set filter
                    paren_filter = filter_content

    print(f"[INFO] Using format: {format_name}")
    print(f"[INFO] Searching for: {pokemon}")
    if mono_filter:
        print(f"[INFO] Filtering by type: {mono_filter}")
    if paren_filter:
        print(f"[INFO] Filtering by parentheses content: {paren_filter}")

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

    matched = list(filter_sets(sets_obj, query="", mono_type=mono_filter, paren_filter=paren_filter))
    if not matched:
        print("[ERROR] No matching sets with given filters.")
        return None

    formatted_sets = []
    for i, (set_name, set_data) in enumerate(matched):
        formatted = format_moveset(species, set_name, set_data, include_header=(i == 0))
        formatted_sets.append(formatted)
    
    return formatted_sets


def main():
    # Test with different filter styles
    test_commands = [
        "meow show set sandslash-alola gen9monotype (slush rush)",
        "meow show set sandslash-alola gen9monotype (boots)",
        "meow show set sandslash-alola gen9monotype (rapid spin)",
        "meow show set latias gen9monotype (scarf)",
        "meow show set gallade gen9monotype (Psychic)"
    ]
    
    for command_string in test_commands:
        print(f"\n{'='*60}")
        print(f"Testing: {command_string}")
        print('='*60)
        
        formatted_sets = parse_command_and_get_sets(command_string)

        if formatted_sets:
            for formatted_set in formatted_sets:
                print(formatted_set)
                print()
        else:
            print("No sets found.")

if __name__ == "__main__":
    main()