import asyncio
import datetime
import json
import random
import hashlib
import re
from html import unescape
from zoneinfo import ZoneInfo

import aiohttp

# ---------- Data loading ----------
def load_Pokemon(ROOM):
    """Load Pokemon from local JSON file with fields Name, Type (e.g., 'Bug / Dark')."""
    with open(f'pokemon_{ROOM}.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {p['Name']: p['Type'] for p in data}

# ---------- Daily selection ----------
def pick_daily_pokemon(pokemon_list, tz="US/Eastern"):
    """Pick the same Pokémon for the entire day."""
    today = datetime.datetime.now(ZoneInfo(tz)).date().isoformat()
    h = hashlib.sha256(today.encode()).hexdigest()
    index = int(h, 16) % len(pokemon_list)
    name = list(pokemon_list.keys())[index]
    return name, pokemon_list[name]

# ---------- Helpers ----------
def slugify_name(name: str) -> str:
    """Make a slug for Smogon URL/sprite."""
    return (
        name.lower()
            .replace(" ", "-")
            .replace("'", "")
            .replace(".", "")
            .replace(":", "")
    )

def first_sentence(text: str) -> str:
    """Extract the first sentence from plain text."""
    # Split on ., !, ? while keeping punctuation simple
    m = re.split(r'(?<=[.!?])\s+', text.strip())
    s = m[0].strip() if m else text.strip()
    # Ensure it ends with '!'
    if not s.endswith('!'):
        s = s.rstrip('.')
        s += '!'
    return s

def html_to_text(html: str) -> str:
    """Very light HTML scrub -> plain text."""
    # Remove tags
    txt = re.sub(r'<[^>]+>', '', html or '')
    # Unescape entities and condense spaces
    txt = unescape(txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

# ---------- Fetch analysis from data.pkmn.cc ----------
async def fetch_monotype_sentence(mon_name: str, ROOM) -> str | None:
    """
    Fetch a random set's first sentence for mon_name from Gen 9 Monotype analyses.
    Returns None if not available.
    """
    if ROOM == "monotype":
        # Fetch from Monotype analyses
        url = "https://data.pkmn.cc/analyses/gen9monotype.json"
    elif ROOM == "nationaldexmonotype":
        # Fetch from National Dex Monotype analyses
        url = "https://pkmn.github.io/smogon/data/analyses/gen9nationaldexmonotype.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    # Keys are species names -> analysis obj
    analysis = data.get(mon_name)
    if not analysis:
        # Try a couple of simple name variations
        alts = {
            mon_name.replace("’", "'"),
            mon_name.replace(" ", "-"),
            mon_name.replace("-Mega", ""),
        }
        for a in alts:
            if a in data:
                analysis = data[a]
                break

    if not analysis:
        return None

    # Collect set descriptions, but exclude bad intros
    set_descs = []
    sets = analysis.get("sets") or {}
    for set_name, set_obj in sets.items():
        desc_html = (set_obj or {}).get("description")
        if desc_html:
            text = html_to_text(desc_html)
            sent = first_sentence(text)
            if not any(
                bad in sent.lower()
                for bad in ["the given ev", "winning set", "sample set"]
            ):
                set_descs.append(text)

    today = datetime.datetime.now(ZoneInfo("US/Eastern")).date().isoformat()
    seed_int = int(hashlib.sha256(f"{today}:{mon_name}".encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    candidate = None
    if set_descs:
        candidate = rng.choice(set_descs)
    else:
        if analysis.get("overview"):
            text = html_to_text(analysis["overview"])
            sent = first_sentence(text)
            if not any(
                bad in sent.lower()
                for bad in ["the given ev", "winning set", "sample set"]
            ):
                candidate = text

    if not candidate:
        return None

    return first_sentence(candidate)


def load_type_colors(filepath="colors.txt"):
    """
    Parse colors.txt containing rules like:
      .type-poison { color:  
      #A040A0 }
    Returns dict like {"Poison": "#A040A0"}.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        css = f.read()

    # Find blocks like .type-poison { ... color: #A040A0 ... }
    pattern = re.compile(
        r"\.type-([a-z0-9\-]+)\s*\{[^}]*?color\s*:\s*(#[0-9A-Fa-f]{3,8})",
        re.IGNORECASE | re.DOTALL,
    )

    colors = {}
    for type_key, hex_color in pattern.findall(css):
        # Normalize: ".type-poison" -> "Poison"
        type_name = type_key.replace("-", " ").title()
        colors[type_name] = hex_color.upper()

    return colors

def get_gradient_for_types(type1, type2, type_colors):
    """Return a CSS gradient string based on the two types."""
    c1 = type_colors.get(type1.capitalize(), "#0B00E4")  
    c2 = type_colors.get(type2.capitalize(), c1) if type2 else c1
    return f"linear-gradient(135deg, {c1} 0%, {c2} 100%)"


# ---------- Build card ----------
async def build_potw(Pokemon: str, Type1: str | None, Type2: str | None, type_colors, ROOM):
    sentence = await fetch_monotype_sentence(Pokemon, ROOM)
    if not sentence:
        # fallback if no Monotype analysis exists for the mon / we suck at coding
        type_text = f"{Type1}/{Type2}" if Type2 else f"{Type1}"
        sentence = f"{Pokemon} provides useful roles on {type_text} teams!"

    final_text = (
        f"{sentence} What other sets do you like using on it? "
        f"How would you support it on its respective typings?"
    )

    slug = slugify_name(Pokemon)
    if ROOM == "nationaldexmonotype":
        href = f"https://www.smogon.com/dex/sv/pokemon/{slug}/national-dex-monotype/"
    elif ROOM == "monotype":
        href = f"https://www.smogon.com/dex/sv/pokemon/{slug}/monotype/"
    gradient = get_gradient_for_types(Type1, Type2, type_colors)
    potw = f"""
<table cellpadding="0" cellspacing="0" width="100%" style="color: #000; background: {gradient}; padding: 1rem; border: .125rem solid transparent; border-radius: .25rem; display: flex;">
  <tr>
    <td style="background-color: rgba(255, 255, 255, 75%); padding: 1rem; border-radius: .25rem; font-size: .875rem;" valign="middle">
      {final_text}
    </td>
    <td style="width: 1rem;"></td>
    <td valign="middle" style="padding: 1.5rem; border-radius: 100rem; border: .125rem solid #000000;">
      <a href="{href}" target="_blank" style="text-decoration: none;">
        <div width="90" height="90">
            <img src="https://www.smogon.com/dex/media/sprites/xy/{slug}.gif" alt="{Pokemon}">
        </div>
      </a>
    </td>
  </tr>
</table>
""".strip()
    return potw


async def send_potd(ws, ROOM):
    """Build and send the POTD card once to a room via ws."""
    pokemon_list = load_Pokemon(ROOM)
    type_colors = load_type_colors("colors.txt")

    pick, typing = pick_daily_pokemon(pokemon_list, tz="US/Eastern")
    parts = [p.strip() for p in typing.split("/")]

    Type1 = parts[0] if parts else None
    Type2 = parts[1] if len(parts) > 1 else None

    html_card = await build_potw(pick, Type1, Type2, type_colors, ROOM)
    print(f"Sent POTD for {pick} ({Type1}/{Type2}) to {ROOM}")

    await ws.send(f"{ROOM}|/addhtmlbox {html_card}")


async def build_daily_potd(ws, ROOM):
    """Send the POTD card every 2 hours to a room via ws."""
    while True:
        await asyncio.sleep(2 * 60 * 60)  # wait 2 hours
        await send_potd(ws, ROOM)
        
        


