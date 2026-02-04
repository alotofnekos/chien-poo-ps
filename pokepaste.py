import requests
from bs4 import BeautifulSoup
import re

MAX_NAME_LENGTH = 50
MAX_MOVE_LENGTH = 30

def get_pokepaste_from_url(url, strip_nicknames=False, strip_title=False):
    """
    Scrapes Pokemon team data from a Pokepaste URL.
    """
    response = requests.get(url)
    response.raise_for_status()
    
    # Pass the URL into the parser so it can be stored in the result
    data = parse_pokepaste_html(response.text, strip_nicknames=strip_nicknames, strip_title=strip_title)
    data['pokepaste_url'] = url 
    return data

def is_valid_pokemon_line(line):
    """Check if line matches expected Pokemon name patterns."""
    # Remove item if present
    base = line.split('@')[0].strip()
    
    # Should only contain: letters, spaces, hyphens, parentheses
    if not re.match(r'^[A-Za-z\s\-()]+$', base):
        return False
    
    # Check length - minimum 3 characters for a Pokemon name
    if len(base) < 3 or len(base) > MAX_NAME_LENGTH:
        return False
    
    # Check for repeated characters 
    if re.search(r'(.)\1{4,}', base):  # 5+ same char in a row
        return False
    
    words = base.split()
    if len(words) == 1 and len(words[0]) < 4:
        pass
    
    return True

def is_valid_move_line(line):
    """Check if line matches expected move format."""
    move = line.strip()
    
    # Moves are typically 1-3 words, letters/spaces/hyphens only
    if not re.match(r'^[A-Za-z\s\-]+$', move):
        return False
    
    if len(move) > MAX_MOVE_LENGTH: 
        return False
    
    if re.search(r'(.)\1{3,}', move):  # 4+ repeated chars
        return False
    
    return True

def get_pokepaste_text(url, strip_nicknames=False):
    """
    Gets the formatted team text from a Pokepaste URL.
    """
    team_data = get_pokepaste_from_url(url, strip_nicknames=strip_nicknames)
    return team_data['formatted_text']


def parse_pokepaste_html(html, strip_nicknames=False, strip_title=False):
    """
    Parses Pokemon team data from Pokepaste HTML content.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title = soup.find('h1')
    title_text = title.get_text(strip=True) if title else "Untitled"
    if strip_title:
        title_text = ""
    
    # Extract author
    author = soup.find('h2')
    author_text = author.get_text(strip=True).replace('by ', '') if author else "Unknown"
    
    # Extract format
    format_text = "Unknown"
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text.startswith('Format:'):
            format_text = text.replace('Format:', '').strip()
            break
    
    # Extract Pokemon data from code blocks (pre tags)
    pokemon_list = []
    code_blocks = soup.find_all('pre')
    
    for block in code_blocks:
        pokemon_text = block.get_text()
        if pokemon_text and pokemon_text.strip():
            pokemon_list.append(pokemon_text)
    
    # Parse each Pokemon
    parsed_pokemon = []
    for poke_data in pokemon_list:
        parsed = parse_pokemon(poke_data, strip_nickname=strip_nicknames)
        if parsed:  
            parsed_pokemon.append(parsed)
    
    # Create the properly formatted output text
    formatted_text = format_team_output(parsed_pokemon)
    
    return {
        'title': title_text,
        'author': author_text,
        'format': format_text,
        'pokemon': parsed_pokemon,
        'formatted_text': formatted_text,
        'is_valid': len(parsed_pokemon) > 0  
    }


def strip_pokemon_nickname(pokemon_name):
    """
    Removes nickname from Pokemon name.
    """
    pokemon_name = pokemon_name.strip()
    
    if '(' not in pokemon_name:
        return pokemon_name
    
    first_paren_idx = pokemon_name.index('(')
    before_paren = pokemon_name[:first_paren_idx].strip()
    
    if not before_paren:
        return pokemon_name
    
    # Check if first parentheses is just a gender marker
    if re.match(r'^[^(]+\([MF]\)\s*$', pokemon_name):
        return pokemon_name
    
    after_nickname = pokemon_name[first_paren_idx:]
    
    match = re.match(r'^\(([^)]+)\)(.*)$', after_nickname)
    if match:
        species = match.group(1)
        rest = match.group(2).strip()
        return f"{species} {rest}".strip()
    
    return pokemon_name


def parse_pokemon(text, strip_nickname=False):
    """
    Parses a single Pokemon's data with validation to prevent abuse.
    Returns None if the Pokemon entry doesn't meet minimum valid structure.
    """
    lines = [line.rstrip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    
    if not lines:
        return None
    
    pokemon_data = {
        'pokemon': None,
        'item': None,
        'ability': None,
        'tera_type': None,
        'evs': {},
        'ivs': {},
        'nature': None,
        'moves': []
    }
    
    first_line = lines[0].strip()
    
    # Parse Pokemon name and item
    if '@' in first_line:
        parts = first_line.split('@')
        pokemon_name = parts[0].strip()
        pokemon_data['item'] = parts[1].strip()
    else:
        pokemon_name = first_line.strip()

    if strip_nickname:
        pokemon_name = strip_pokemon_nickname(pokemon_name)
    
    # Validate Pokemon name
    if not is_valid_pokemon_line(pokemon_name):
        return None
    
    # Additional name validation: must be at least 3 chars and contain at least one vowel
    # (prevents single letters or pure consonants like "hi", "xx", etc.)
    clean_name = re.sub(r'[^a-zA-Z]', '', pokemon_name.lower())
    if len(clean_name) < 3 or not re.search(r'[aeiou]', clean_name):
        return None
    
    pokemon_data['pokemon'] = pokemon_name
    
    # Parse remaining lines
    for line in lines[1:]:
        line = line.strip()
        
        if line.startswith('Ability:'):
            pokemon_data['ability'] = line.split('Ability:', 1)[1].strip()
        elif line.startswith('Tera Type:'):
            pokemon_data['tera_type'] = line.split('Tera Type:', 1)[1].strip()
        elif line.startswith('EVs:'):
            evs_text = line.split('EVs:', 1)[1].strip()
            pokemon_data['evs'] = parse_stats(evs_text)
        elif line.startswith('IVs:'):
            ivs_text = line.split('IVs:', 1)[1].strip()
            pokemon_data['ivs'] = parse_stats(ivs_text)
        elif line.endswith('Nature'):
            pokemon_data['nature'] = line
        elif line.startswith('-'):
            move = line[1:].strip()
            if move:
                # Validate move
                if is_valid_move_line(move):
                    pokemon_data['moves'].append(move)
    
    # Structure validation: A valid Pokemon should have meaningful data
    # Must have at least 2 of: moves, ability, EVs, nature, tera type
    validity_score = 0
    if pokemon_data['moves']:  # Has at least one move
        validity_score += 1
    if pokemon_data['ability']:
        validity_score += 1
    if pokemon_data['evs']:  
        validity_score += 1
    if pokemon_data['nature']:
        validity_score += 1
    if pokemon_data['tera_type']:
        validity_score += 1
    
    # Require at least 2 fields to be filled (or 1 move minimum)
    if validity_score < 2 and not pokemon_data['moves']:
        return None
    
    return pokemon_data


def parse_stats(stats_text):
    stats = {}
    parts = stats_text.split('/')
    for part in parts:
        part = part.strip()
        match = re.match(r'(\d+)\s+(.+)', part)
        if match:
            value, stat = match.groups()
            stats[stat.strip()] = int(value)
    return stats


def _pokemon_sprite_url(name):
    name = re.sub(r'\s*\([MF]\)\s*$', '', name).strip()

    URSHIFU_FORMS = ['urshifu-rapid-strike', 'urshifu-single-strike']
    if name.lower() in URSHIFU_FORMS:
        name = 'urshifu'

    FORM_MAP = {
        '-Hisui': '-hisui', '-Alola': '-alola', '-Galar': '-galar',
        '-Mega':  '-mega',  '-Mega X': '-megax', '-Mega Y': '-megay', '-Mega Z': '-megaz',
        '-Hisuian': '-hisui', '-Alolan': '-alola', '-Galarian': '-galar',
    }
    suffix = ''
    for display, sd in FORM_MAP.items():
        if name.endswith(display):
            name = name[:-len(display)]
            suffix = sd
            break
    slug = name.lower().replace(' ', '')
    return f'https://play.pokemonshowdown.com/sprites/gen5/{slug}{suffix}.png'


def generate_html(team_data, max_height_px=320):
    """
    Compact, scroll-safe HTML fragment.
    All Pokemon icons link to the Pokepaste URL.
    **Text box now has forced black text on semi-transparent white background.**
    """
    pokemon = team_data.get('pokemon', [])
    paste_url = team_data.get('pokepaste_url', '#')

    if not team_data.get('is_valid', True):
        return (
            '<div style="max-height:' + str(max_height_px) + 'px;'
                        'overflow:auto;'
                        'border:1px solid #d33;'
                        'border-radius:4px;'
                        'background:rgba(248, 200, 220, 0.2);'
                        'padding:20px;'
                        'text-align:center;'
                        'font-family:sans-serif;">'
              '<strong style="color:#d33; font-size:14px;">Malformed Paste</strong><br>'
              '<span style="color:#666; font-size:12px;">Nyo valid Pokémon found. Maybe it isnt a team, meow? ;w; </span>'
            '</div>'
        )
    # --- Pokémon cells (single horizontal row) ---
    mon_cells = ''
    for p in pokemon:
        mon_url  = _pokemon_sprite_url(p['pokemon'])
        name     = p['pokemon']
        mon_cells += (
            '<td style="padding:0; vertical-align:bottom; white-space:nowrap;">'
            f'<a href="{paste_url}" target="_blank" style="text-decoration:none; display:block; padding:4px 5px;">'
                '<div style="display:flex; align-items:center;">'
                    f'<img src="{mon_url}" alt="{name}" width="42" height="42" />'
                '</div>'
            '</a>'
            '</td>'
        )

    mon_row = '<tr>' + mon_cells + '</tr>'

    # --- Scrollable pokepaste content text ---
    text_row = (
        '<tr>'
        '<td colspan="100%" style="padding:6px 8px;">'
          '<div style="max-height:160px; overflow:auto;'
                       'border:1px solid #ccc;'
                       'background:rgba(248, 200, 220, 0.2);'
                       'font-family:monospace;'
                       'font-size:12px;'
                       'white-space:pre-wrap;'
                       'line-height:1.3;'
                       'padding:6px;">'
            + team_data.get('formatted_text', '') +
          '</div>'
        '</td>'
        '</tr>'
    )

    # --- Optional header ---
    title  = team_data.get('title', '')
    author = team_data.get('author', '')
    fmt    = team_data.get('format', '')

    meta = ' · '.join(x for x in [
        f'by {author}' if author else '',
        fmt
    ] if x)

    header = ''
    if title or meta:
        header = (
            '<tr>'
            '<td colspan="100%" style="padding:6px 8px; font-family:sans-serif;">'
              + (f'<strong style="font-size:13px;">{title}</strong> ' if title else '') +
              (f'<span style="font-size:11px; color:#888;">{meta}</span>' if meta else '') +
            '</td>'
            '</tr>'
        )

    return (
        '<div style="max-height:' + str(max_height_px) + 'px;'
                    'overflow:auto;'
                    'border:1px solid #ccc;'
                    'border-radius:4px;">'
          '<table style="border-collapse:collapse; table-layout:fixed; width:auto;">'
            + header +
            mon_row +
            text_row +
          '</table>'
        '</div>'
    )


def format_team_output(pokemon_list):
    """
    Formats the parsed Pokemon list into the standard Showdown format.
    """
    output_lines = []
    
    for pokemon in pokemon_list:
        if pokemon['item']:
            output_lines.append(f"{pokemon['pokemon']} @ {pokemon['item']}")
        else:
            output_lines.append(pokemon['pokemon'])
        
        if pokemon['ability']:
            output_lines.append(f"Ability: {pokemon['ability']}")
        
        if pokemon['tera_type']:
            output_lines.append(f"Tera Type: {pokemon['tera_type']}")
        
        if pokemon['evs']:
            evs_str = ' / '.join([f"{value} {stat}" for stat, value in pokemon['evs'].items()])
            output_lines.append(f"EVs: {evs_str}")
        
        if pokemon['nature']:
            output_lines.append(pokemon['nature'])
        
        if pokemon['ivs']:
            ivs_str = ' / '.join([f"{value} {stat}" for stat, value in pokemon['ivs'].items()])
            output_lines.append(f"IVs: {ivs_str}")
        
        for move in pokemon['moves']:
            output_lines.append(f"- {move}")
        
        output_lines.append('')
    
    return '\n'.join(output_lines)


if __name__ == "__main__":
    url = "https://pokepast.es/0411e4bd9ccd54e8"
    
    try:
        print(generate_html(get_pokepaste_from_url(url, strip_nicknames=True, strip_title=False)))
        
    except Exception as e:
        print(f"Error: {e}")