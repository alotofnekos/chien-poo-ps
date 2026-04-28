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


#   FORMAT ALIAS NORMALIZATION
GEN_ALIASES = {
    # numeric shorthand
    "gen1": 1, "gen2": 2, "gen3": 3, "gen4": 4,
    "gen5": 5, "gen6": 6, "gen7": 7, "gen8": 8, "gen9": 9,
    # game codes
    "rb": 1, "rby": 1,
    "gs": 2, "gsc": 2,
    "rs": 3, "rse": 3, "adv": 3,
    "dp": 4, "dpp": 4,
    "bw": 5, "bw2": 5,
    "xy": 6, "oras": 6,
    "sm": 7, "usum": 7,
    "ss": 8, "swsh": 8,
    "sv": 9, "scarlet": 9, "violet": 9,
}

# gen prefix used in format names
GEN_PREFIX = {
    1: "gen1", 2: "gen2", 3: "gen3", 4: "gen4",
    5: "gen5", 6: "gen6", 7: "gen7", 8: "gen8", 9: "gen9",
}

# Smogon dex gen codes for URLs
SMOGON_GEN_CODE = {
    1: "rb", 2: "gs", 3: "rs", 4: "dp",
    5: "bw", 6: "xy", 7: "sm", 8: "ss", 9: "sv",
}

# Sprite folder names on smogon.com/dex/media/sprites/<folder>/
SPRITE_FOLDER = {
    1: ("rb",  "png"),
    2: ("c",  "gif"), # for some reason, gsc sprite folder is just c
    3: ("rs",  "png"),
    4: ("dp",  "png"),
    5: ("bw",   "gif"),
    6: ("xy",   "gif"),
    7: ("xy",   "gif"),   # gen 7+ dex sprites live in the xy folder
    8: ("xy",   "gif"),
    9: ("xy",   "gif"),
}

KNOWN_TYPES = {
    "normal","fire","water","electric","grass","ice","fighting","poison",
    "ground","flying","psychic","bug","rock","ghost","dragon","dark","steel","fairy"
}


def get_sprite_url(mon: str, gen: int) -> str:
    """Return smogon dex sprite URL for a given mon and gen."""
    folder, ext = SPRITE_FOLDER.get(gen, ("xy", "gif"))
    return f"https://www.smogon.com/dex/media/sprites/{folder}/{mon}.{ext}"


def normalize_format(raw: str, default_tier: str = "monotype") -> str:
    """
    Convert any user-supplied format string into the canonical pkmn.github.io
    format name, e.g.:
        'xy monotype'  -> 'gen6monotype'
        'gen6monotype' -> 'gen6monotype'
        'bw ou'        -> 'gen5ou'
        'bw'           -> 'gen5<default_tier>'  
        'gen9'         -> 'gen9<default_tier>'  

    Pass default_tier based on room so 'bw' in the monotype room
    becomes 'gen5monotype' instead of 'gen5ou'.
    """
    import re

    s = raw.strip().lower().replace(" ", "").replace("-", "")

    result = resolve_natdex("gen9", s, default_tier)
    if result:
        return result

    if re.match(r"^gen\d.+$", s):
        return s

    matched_alias = None
    matched_gen = None

    for alias, gen in sorted(GEN_ALIASES.items(), key=lambda x: -len(x[0])):
        if s.startswith(alias):
            matched_alias = alias
            matched_gen = gen
            break

    if matched_gen is None:
        return raw.strip().lower().replace(" ", "")

    gen_prefix = GEN_PREFIX[matched_gen]

    remainder = s[len(matched_alias):]

    if not remainder:
        remainder = default_tier

    if remainder == "mono":
        remainder = "monotype"

    result = resolve_natdex(gen_prefix, remainder, default_tier)
    if result:
        return result

    return f"{gen_prefix}{remainder}"

def resolve_natdex(gen: str, s: str, default_tier: str) -> str | None:
    nd_prefixes = (
        "nationaldexmonotype", "natdexmonotype", "ndmonotype", "ndmono",
        "nationaldex", "natdex", "nd",
    )

    for ndp in nd_prefixes:
        if s.startswith(ndp):
            tier_part = s[len(ndp):]

            if "monotype" in ndp:
                return f"{gen}nationaldexmonotype"

            if not tier_part:
                tier_part = default_tier

            if tier_part == "monotype":
                return f"{gen}nationaldexmonotype"

            # no "ou" suffix for natdex OU
            if tier_part in ("ou", ""):
                return f"{gen}nationaldex"

            return f"{gen}nationaldex{tier_part}"

    return None

# 
#   ALL FORMATS TO SEARCH AS FALLBACK
# 

FALLBACK_FORMAT_ORDER = [
    "gen9monotype", "gen9ou", "gen9uu", "gen9ru", "gen9nu",
    "gen9pu", "gen9lc", "gen9ubers",
    "gen9nationaldex", "gen9nationaldexmonotype",
    "gen9nationaldex", "gen9nationaldexuu", "gen9nationaldexubers",
    "gen8nationaldex", "gen8nationaldexmonotype", "gen8nationaldexag",
    "gen8monotype", "gen8ou", "gen8uu", "gen8ru", "gen8nu",
    "gen8pu", "gen8lc", "gen8ubers",
    "gen7monotype", "gen7ou", "gen7uu", "gen7ru", "gen7nu",
    "gen7pu", "gen7lc", "gen7ubers",
    "gen6monotype", "gen6ou", "gen6uu", "gen6ru", "gen6nu",
    "gen6pu", "gen6lc", "gen6ubers",
    "gen5ou", "gen5uu", "gen5ru", "gen5nu", "gen5lc", "gen5ubers",
    "gen4ou", "gen4uu", "gen4nu", "gen4lc", "gen4ubers",
    "gen3ou", "gen3uu", "gen3nu", "gen3lc", "gen3ubers",
    "gen2ou", "gen2uu",
    "gen1ou", "gen1uu",
]


#   FETCH SETS
def fetch_sets_data(format_name: str):
    # cache
    entry = sets_cache.get(format_name)
    if entry and (time.time() - entry["timestamp"] < CACHE_DURATION):
        return entry["data"]

    url = f"https://pkmn.github.io/smogon/data/sets/{format_name}.json"
    #print(f"[INFO] Fetching sets: {url}")

    try:
        r = requests.get(url)
        if not r.ok:
            print(f"[WARN] Format '{format_name}' not found (HTTP {r.status_code})")
            return None

        data = r.json()
        sets_cache[format_name] = {"timestamp": time.time(), "data": data}
        return data

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch format '{format_name}': {e}")
        return None
    except ValueError as e:
        print(f"[ERROR] Invalid JSON response for format '{format_name}': {e}")
        return None


#   FIND POKEMON
def normalize_mega_name(name: str) -> list[str]:
    candidates = [name]
    lower = name.lower().strip()

    mega_xy = re.match(r"^mega (.+) ([xyz])$", lower)
    if mega_xy:
        base = mega_xy.group(1)
        suffix = mega_xy.group(2)
        candidates.append(f"{base}-mega-{suffix}")  
        candidates.append(base)                      
        return candidates

    for prefix in ("mega ", "primal ", "mega-"):
        if lower.startswith(prefix):
            base = name[len(prefix):]
            tag = prefix.strip().strip("-")
            candidates.append(f"{base}-{tag}")
            candidates.append(base)
            break

    return candidates


def find_pokemon_sets(sets_data, name: str):
    candidates = normalize_mega_name(name)
    for candidate in candidates:
        target = normalize_name(candidate)
        for species, sets in sets_data.items():
            if normalize_name(species) == target or target in normalize_name(species):
                return {"species": species, "sets": sets}
    return None

#   SEARCH ALL FORMATS FOR A POKEMON (fallback)
def find_pokemon_in_any_format(pokemon: str, skip_format: str = None):
    """
    Returns (species, sets_obj, format_name) for the first format where
    the pokemon has sets, skipping `skip_format`.
    """
    for fmt in FALLBACK_FORMAT_ORDER:
        if fmt == skip_format:
            continue
        data = fetch_sets_data(fmt)
        if not data:
            continue
        result = find_pokemon_sets(data, pokemon)
        if result:
            return result["species"], result["sets"], fmt
    return None, None, None


#   URL BUILDER
def build_smogon_url(species: str, format_name: str):
    m = re.match(r"^gen(\d)([a-z0-9]+)$", format_name, re.I)
    if not m:
        return None
    gen = int(m.group(1))
    tier = m.group(2).lower()
    gen_code = SMOGON_GEN_CODE.get(gen, "sv")
    mon = species.lower().replace(" ", "-").replace("'", "")
    return f"https://www.smogon.com/dex/{gen_code}/pokemon/{mon}/{tier}/"


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
def filter_sets(sets_obj, query="", monotype="", paren_filter=""):
    """
    Filter sets by query, monotype, and/or paren_filter.
    - query: matches set name (without parentheses, case-insensitive)
    - monotype: matches type in parentheses like "(Psychic)"
    - paren_filter: matches ability, item, moves, set name, or parentheses content
    """
    q = query.lower()
    mt = monotype.lower().strip()
    pf = paren_filter.lower().strip()

    for name, data in iterate_sets("species", sets_obj):
        lname = name.lower()

        if q and q not in lname:
            continue

        if mt and f"({mt})" not in lname:
            continue

        if pf:
            match_found = False

            if pf in lname:
                match_found = True

            if not match_found and data.get("ability"):
                if pf in str(data["ability"]).lower():
                    match_found = True

            if not match_found and data.get("item"):
                item = data["item"]
                item_str = " ".join(str(i) for i in item).lower() if isinstance(item, list) else str(item).lower()
                if pf in item_str:
                    match_found = True

            if not match_found and data.get("moves"):
                for move in data["moves"]:
                    move_str = " ".join(str(m) for m in move).lower() if isinstance(move, list) else str(move).lower()
                    if pf in move_str:
                        match_found = True
                        break

            if not match_found:
                paren_match = re.search(r'\(([^)]+)\)', lname)
                if paren_match and pf in paren_match.group(1).lower():
                    match_found = True

            if not match_found:
                continue

        yield name, data


#   FORMAT MOVESET
def format_moveset(species: str, set_name: str, data: dict,
                   include_header: bool = True, note: str = "", gen: int = 9, dex_url = ""):
    def fmt_evs(ev_obj):
        order = [("hp","HP"),("atk","Atk"),("def","Def"),
                 ("spa","SpA"),("spd","SpD"),("spe","Spe")]
        if isinstance(ev_obj, dict):
            parts = [f"{ev_obj[k]} {label}" for k, label in order
                     if isinstance(ev_obj.get(k), int) and ev_obj[k] > 0]
            return " / ".join(parts)
        return str(ev_obj)

    items = data.get("item")
    mon = species.lower().replace(" ", "-").replace("'", "")
    print(f"[DEBUG] items={items!r} mon before={mon!r}")
    if items:
        item_check = items if isinstance(items, str) else next(
            (i for i in items if isinstance(i, str) and ("ite" in i.lower() or i.lower().endswith("orb"))), None
        )

        if item_check and isinstance(item_check, str):
            xy_match = re.match(r".+ite\s+([xyz])$", item_check, re.I)
            if xy_match:
                mon += f"-mega-{xy_match.group(1).lower()}"
            elif item_check.lower().endswith("ite"):
                mon += "-mega"
            elif item_check.lower().endswith("orb"):
                mon += "-primal"

    item_str = " / ".join(str(i) for i in items) if isinstance(items, list) else (items or "")

    #  Sprite + header 
    header_html = ""
    if include_header:
        sprite_url = get_sprite_url(mon, gen)
        header_html = f"""
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" style="padding-bottom: .5rem;">
        <a href = {dex_url}>
            <img src="{sprite_url}"
                alt="{species}" width="96" height="96">
        </a>
    </td>
  </tr>
</table>""".strip()

    #  Optional tier note banner 
    note_html = ""
    if note:
        note_html = f"""
<div style="border: .125rem solid #c08000; background: #fff8e1; padding: .4rem .75rem;
            margin-bottom: .5rem; font-size: .85rem; color: #7a5000;">
  {note}
</div>""".strip()

    #  Set body 
    body_parts = []
    if item_str:
        body_parts.append(f"<div><b>{species}</b> @ {item_str}</div>")
    else:
        body_parts.append(f"<div><b>{species}</b></div>")

    # Ability: list -> slash-separated options
    ability = data.get("ability")
    if ability:
        if isinstance(ability, list):
            body_parts.append(f"<div>Ability: {' / '.join(str(a) for a in ability)}</div>")
        else:
            body_parts.append(f"<div>Ability: {ability}</div>")

    # EVs: list of dicts -> each spread on its own line joined by " OR "
    evs = data.get("evs", {})
    if isinstance(evs, list):
        ev_parts = [fmt_evs(e) for e in evs if e]
        ev_str = " OR ".join(p for p in ev_parts if p)
    else:
        ev_str = fmt_evs(evs)
    if ev_str:
        body_parts.append(f"<div>EVs: {ev_str}</div>")

    # Nature: list -> slash-separated options
    nature = data.get("nature")
    if nature:
        if isinstance(nature, list):
            body_parts.append(f"<div>{' / '.join(str(n) for n in nature)} Nature</div>")
        else:
            body_parts.append(f"<div>{nature} Nature</div>")

    tera = data.get("teratypes")
    if tera:
        tera_str = " / ".join(tera) if isinstance(tera, list) else tera
        body_parts.append(f"<div>Tera Type: {tera_str}</div>")

    # IVs: list of dicts -> same OR treatment as EVs
    ivs = data.get("ivs", {})
    if isinstance(ivs, list):
        iv_parts = []
        for iv_obj in ivs:
            if isinstance(iv_obj, dict):
                s = " / ".join(
                    f"{v} {k.upper()}" for k, v in iv_obj.items()
                    if isinstance(v, int) and v < 31
                )
                if s:
                    iv_parts.append(s)
        if iv_parts:
            body_parts.append(f"<div>IVs: {' OR '.join(iv_parts)}</div>")
    elif isinstance(ivs, dict):
        iv_str = " / ".join(
            f"{v} {k.upper()}" for k, v in ivs.items()
            if isinstance(v, int) and v < 31
        )
        if iv_str:
            body_parts.append(f"<div>IVs: {iv_str}</div>")

    for m in data.get("moves", []):
        if isinstance(m, list):
            body_parts.append(f"<div>- {' / '.join(m)}</div>")
        else:
            body_parts.append(f"<div>- {m}</div>")

    body_html = "\n".join(body_parts)

    set_html = f"""
<div style="margin-bottom: 1rem;">
  <div style="border: .125rem solid #000; border-bottom: none; padding: .5rem;
              font-weight: bold; text-align: center;">
    {set_name}
  </div>
  <div style="border: .125rem solid #000; padding: 1rem;">
    {body_html}
  </div>
</div>""".strip()

    return "\n".join(filter(None, [header_html, note_html, set_html]))


def try_peel_format(pokemon: str, default_tier: str = "ou"):
    """
    Given a pokemon string that may have a trailing format embedded in it
    (e.g. "latios mix and mega", "iron valiant ou", "great tusk monotype"),
    progressively peel words off the end and check if they are
    a real format on pkmn.github.io.

    Returns (trimmed_pokemon, format_name) on the first hit, or (None, None).
    """
    words = pokemon.split()
    for peel in range(min(4, len(words) - 1), 0, -1):  
        candidate_name   = " ".join(words[:-peel])
        candidate_format = " ".join(words[-peel:])
        if not candidate_name:
            continue
        fmt = normalize_format(candidate_format, default_tier=default_tier)
        if not re.match(r"^gen\d", fmt) and not fmt.startswith("nationaldex"):
            fmt = f"gen9{fmt}"
        #print(f"[INFO] Trying peeled format: pokemon={candidate_name!r} fmt={fmt!r}")
        data = fetch_sets_data(fmt)
        if not data:
            continue
        return candidate_name, fmt
    return None, None


def parse_command_and_get_sets(command_string, room=""):
    """
    Accepts commands like:
        meow show set Gallade gen9monotype (Psychic)
        meow show set Latias gen9monotype (Scarf)
        meow show set Latias (Scarf)
        meow show set Latias xy monotype (Scarf)
        meow show set Darkrai bw
        meow show set Sandslash-Alola oras monotype (boots)

    Format aliases accepted: xy, bw, bw2, oras, sm, usum, ss, swsh, sv,
                              gen6, gen6monotype, etc.

    Fallback: if the pokemon has no sets in the requested format, we search
              all known formats and return results with a tier note.

    Returns:
        list of HTML strings, or None on hard error / pokemon not found anywhere
    """
    parts = command_string.split()

    if len(parts) < 4:
        return None

    cmd, action1, action2 = parts[0].lower(), parts[1].lower(), parts[2].lower()
    if cmd != "meow" or action1 != "show" or action2 not in ("set", "sets"):
        return None

    remaining = parts[3:]
    pokemon_parts = []
    format_raw = None
    paren_args = []
    i = 0

    while i < len(remaining):
        part = remaining[i]
        part_lower = part.lower()

        if part.startswith("("):
            # Collect rest of parenthesised tokens if split across spaces
            token = part
            while not token.endswith(")") and i + 1 < len(remaining):
                i += 1
                token += " " + remaining[i]
            paren_args.append(token.strip("()"))
            i += 1
            continue

        # Try to match a two-word format like "xy monotype" or single like "gen9monotype"
        alias_hit = None
        for alias in sorted(GEN_ALIASES.keys(), key=lambda x: -len(x)):
            if part_lower == alias or part_lower.startswith(alias) and len(part_lower) > len(alias):
                alias_hit = part_lower
                break

        if alias_hit is not None and not pokemon_parts:
            pass

        if alias_hit is not None and pokemon_parts:
            fmt_token = part_lower
            # Check if next token is a tier word (not a paren, not another alias)
            if i + 1 < len(remaining) and not remaining[i+1].startswith("("):
                next_tok = remaining[i+1].lower()
                # If next token is not itself a pokemon-name-like thing, absorb it
                is_tier_word = not next_tok.startswith("gen") and \
                               next_tok not in GEN_ALIASES and \
                               not next_tok.startswith("(")
                if is_tier_word and re.match(r'^[a-z0-9]+$', next_tok):
                    fmt_token = part_lower + next_tok
                    i += 1
            format_raw = fmt_token
            i += 1
            continue

        # Otherwise it's part of the pokemon name
        pokemon_parts.append(part)
        i += 1

    pokemon = " ".join(pokemon_parts)
    if not pokemon:
        return None
    

    room_lower = room.lower()
    if room_lower == "monotype":
        default_tier   = "monotype"
        default_format = "gen9monotype"
    elif room_lower == "nationaldexmonotype":
        default_tier   = "nationaldexmonotype"
        default_format = "gen9nationaldexmonotype"
    elif room_lower == "nationaldexou":
        default_tier   = "nationaldex"
        default_format = "gen9nationaldex"
    else:
        default_tier   = "ou"
        default_format = "gen9ou"

    # Determine format 
    if format_raw:
        # Pass room-derived default_tier so a bare alias like "bw" becomes
        # "gen5monotype" instead of "gen5ou" when in the monotype room.
        format_name = normalize_format(format_raw, default_tier=default_tier)
    else:
        format_name = default_format

    mono_filter = ""
    paren_filter = ""
    for arg in paren_args:
        if arg.lower() in KNOWN_TYPES:
            mono_filter = arg
        else:
            paren_filter = arg

    #print(f"[INFO] Format   : {format_name}")
    #print(f"[INFO] Pokemon  : {pokemon}")
    #if mono_filter:
    #    print(f"[INFO] Type     : {mono_filter}")
    #if paren_filter:
    #    print(f"[INFO] Filter   : {paren_filter}")

    #  Fetch target format 
    fallback_note = ""
    sets_data = fetch_sets_data(format_name)
    result = find_pokemon_sets(sets_data, pokemon) if sets_data else None

    if not result:
        #  if no explicit format was given and pokemon has spaces,
        #  try peeling trailing words as a format before bruteforcing
        if not format_raw and " " in pokemon:
            peeled_pokemon, peeled_fmt = try_peel_format(pokemon, default_tier=default_tier)
            if peeled_pokemon:
                print(f"[INFO] Peeled format {peeled_fmt!r} for pokemon {peeled_pokemon!r}")
                pokemon     = peeled_pokemon          
                format_name = peeled_fmt
                result      = find_pokemon_sets(
                    fetch_sets_data(format_name) or {}, pokemon
                )

    if not result:
        # search all known formats
        #print(f"[WARN] '{pokemon}' not in {format_name}, searching other formats…")
        species, sets_obj, found_fmt = find_pokemon_in_any_format(pokemon, skip_format=format_name)

        if species is None:
            #print(f"[ERROR] '{pokemon}' has no sets in any known format.")
            return None 

        fallback_note = (
            f"Nyo sets found for <b>{species}</b> in <b>{format_name}</b>. ;w;"
            f"Showing sets from <b>{found_fmt}</b> instead."
        )
        print(f"[INFO] Falling back to {found_fmt}")
        format_name = found_fmt
        result = {"species": species, "sets": sets_obj}

    species = result["species"]
    sets_obj = result["sets"]

    url = build_smogon_url(species, format_name)
    if url:
        print(f"[INFO] Smogon URL: {url}")

    gen_match = re.match(r"^gen(\d)", format_name)
    sprite_gen = int(gen_match.group(1)) if gen_match else 9
    #for zard-x
    mega_xy = re.match(r"^mega .+ ([xyz])$", pokemon.lower().strip())
    if mega_xy and not paren_filter:
        paren_filter = f"ite {mega_xy.group(1)}"
    matched = list(filter_sets(sets_obj, monotype=mono_filter, paren_filter=paren_filter))
    if not matched:
        #print("[WARN] Nyo sets matched filters. Returning all sets.")
        matched = list(filter_sets(sets_obj))
        if matched and (mono_filter or paren_filter):
            filter_desc = " / ".join(filter(None, [mono_filter, paren_filter]))
            fallback_note = (
                (fallback_note + " " if fallback_note else "") +
                f"Nyo sets matched filter <b>({filter_desc})</b>; showing all sets. ;w;"
            )

    if not matched:
        #print(f"[ERROR] '{pokemon}' exists but has no sets at all.")
        return None

    formatted = []
    for idx, (set_name, set_data) in enumerate(matched):
        note = fallback_note if idx == 0 else ""
        formatted.append(
            format_moveset(species, set_name, set_data,
                           include_header=(idx == 0), note=note, gen=sprite_gen, dex_url=url)
        )
    return formatted

def main():
    test_commands = [
        # Standard
        "meow show set darkrai",
        # Filter by item (boots)
        "meow show set sandslash-alola gen9monotype (boots)",
        # Filter by move
        "meow show set sandslash-alola gen9monotype (rapid spin)",
        #nd
        "meow show set mega charizard x nd monotype",
        "meow show set tapu lele ssndou",
        #sm
        "meow show set mega gallade sm monotype",
        "meow show set diancie mega sm monotype",
        # oras
        "meow show set latias xy monotype (scarf)",
        "meow show set gallade gen6monotype (Psychic)",
        # bw
        "meow show set excadrill bw monotype",
        # dpp 
        "meow show set jirachi dpp",
        # adv 
        "meow show set charizard adv",
        # gsc
        "meow show set moltres gs",
        # rby
        "meow show set mewtwo rb ubers",
        # Format that won't have the mon
        "meow show set rattata gen9monotype",
        # OMs
        "meow show set latios godly gift",
        # Completely non-existent mon 
        "meow show set asdfxyz",
    ]

    for cmd in test_commands:
        print(f"\n{'='*60}")
        print(f"Testing: {cmd}")
        print("="*60)

        results = parse_command_and_get_sets(cmd)
        if results is None:
            print("No sets")
        else:
            for html in results:
                print(html)
                print()


if __name__ == "__main__":
    main()