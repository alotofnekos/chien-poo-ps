import re
import aiohttp
from set_handler import parse_command_and_get_sets
from better_profanity import profanity
from tn import get_current_tour_schedule, get_next_tournight
from tour_creator import supabase
from meow_token import create_token
from PIL import Image, ImageDraw, ImageFont
import textwrap
import io
import asyncio
SUPABASE_BUCKET = "cat-images"
AUTH_RANKS = {"@", "#", "~"} 
BASE_URL = "https://chien-poo-ps.onrender.com"

async def room_schedule_editor(room: str, sender: str, rank: str, ws):
    """
    meow edit schedule inside a room.
    PMs the link so only the auth sees it.
    """
    if rank not in AUTH_RANKS:
        return

    token = await create_token(sender, room, supabase)
    link  = f"{BASE_URL}/auth?token={token}"
    await ws.send(f"|/pm {sender}, Meow, here's your login link for the schedule (expires 10 mins, one-time use): {link}")

async def cleanup_cat_images():
    """Delete all files in the cat-images bucket older than 12 hour."""
    while True:
        await asyncio.sleep(43200)  # 12hrs
        try:
            files = supabase.storage.from_(SUPABASE_BUCKET).list()
            if not files:
                continue
            to_delete = [f["name"] for f in files]
            if to_delete:
                supabase.storage.from_(SUPABASE_BUCKET).remove(to_delete)
                print(f"[cleanup] Deleted {len(to_delete)} cat images")
        except Exception as e:
            print(f"[cleanup] Error: {e}")

def add_bottom_caption(img, text):
    img = img.convert("RGB")
    width, height = img.size

    font_size = max(20, width // 10)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
            font_size,
        )
    except Exception:
        font = ImageFont.load_default(size=font_size)

    # Wrap text
    chars_per_line = max(8, width // (font_size))
    wrapped = textwrap.fill(text.upper(), width=chars_per_line)

    # Measure text height
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    text_h = bbox[3] - bbox[1]
    caption_height = text_h + font_size  # padding above/below text

    white_border = max(6, width // 80)  # thin white border around image
    black_padding = max(16, width // 20)  # black gap between image and caption

    canvas_w = width + white_border * 2
    canvas_h = height + white_border * 2 + black_padding + caption_height + black_padding

    canvas = Image.new("RGB", (canvas_w, canvas_h), "black")

    # White border
    white_bg = Image.new("RGB", (width + white_border * 2, height + white_border * 2), "white")
    canvas.paste(white_bg, (0, 0))
    canvas.paste(img, (white_border, white_border))

    draw = ImageDraw.Draw(canvas)

    # Center caption
    x = canvas_w // 2
    y = height + white_border * 2 + black_padding + caption_height // 2

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill="white",
        anchor="mm",
        align="center",
    )

    return canvas

async def get_random_cat_url():
    url = "https://api.thecatapi.com/v1/images/search"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data[0]["url"]
    return "No cat found :("

async def determine_if_message_is_not_ok(text):
    # Check if the message is profane
    text = text.lower()
    chinese_badwords = ['cnm', 'nmsl', 'sb', 'sao', 'smd', 'sbh', 'sbl', 'sbd', 'sbm', 'sbj', 'sbp', 'sbz', 'sbq','niga','niger']
    is_profane = profanity.contains_profanity(text)
    if not is_profane:
        normalized = re.sub(r'(.)\1{2,}', r'\1\1', text)
        profanity.add_censor_words(chinese_badwords)
        is_profane = profanity.contains_profanity(normalized)
    if not is_profane:
        normalized_1 = re.sub(r'(.)\1+', r'\1', text)
        is_profane = profanity.contains_profanity(normalized_1)
    print(f"Checked message: '{text}' | Profane: {is_profane}")
    return is_profane

async def ensure_bucket_exists():
    try:
        supabase.storage.get_bucket(SUPABASE_BUCKET)
    except Exception:
        supabase.storage.create_bucket(SUPABASE_BUCKET, options={"public": True})

async def get_random_cat_saying(message):
    if await determine_if_message_is_not_ok(message) == True:
        return "Meow! I dont think I should say that :3c"

    try:
        await ensure_bucket_exists()

        # Fetch cat image
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.thecatapi.com/v1/images/search") as resp:
                data = await resp.json()
                img_url = data[0]["url"]
            async with session.get(img_url) as resp:
                img_bytes = await resp.read()

        # Add caption
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = add_bottom_caption(img, message)

        # Save to bytes
        output = io.BytesIO()
        fmt = "JPEG" if img_url.endswith((".jpg", ".jpeg")) else "PNG"

        img.save(output, format=fmt)
        output.seek(0)

        # Upload to Supabase Storage
        filename = f"cat_{int(asyncio.get_event_loop().time() * 1000)}.{fmt.lower()}"
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            filename,
            output.read(),
            file_options={"content-type": f"image/{fmt.lower()}"}
        )
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
        return public_url

    except Exception as e:
        print(f"[cat_saying] Error: {e}")
        return "No cat found :("

async def handle_pmmessages(ws, USERNAME, msg):
    lines = msg.split('\n')
    for line in lines:
        if "|pm|" in line:
            parts = line.split("|")
            if len(parts) >= 5 and parts[1] == "pm":
                from_user = parts[2].strip()
                to_user = parts[3].strip()
                message = "|".join(parts[4:]).strip()
                
                # Skip if the PM is from ourselves
                if from_user.lower() == USERNAME.lower():
                    return
                
                if "meow show set" in message.lower():
                    sets_output = parse_command_and_get_sets(message)
                    if sets_output:
                        # Send each set as a separate message
                        for set_str in sets_output:
                            pm_response = f"|/pm {from_user}, {set_str}"
                            await ws.send(pm_response)
                        
                        # Send confirmation message
                        pm_response = f"|/pm {from_user}, Meow sent the set info!"
                        await ws.send(pm_response)
                    else:
                        pm_response = f"|/pm {from_user}, Meow couldn't find any sets this mon, sorry ;w;. Usage: meow show set <pokemon> [format] [set filter] [extra filters]"
                        await ws.send(pm_response)
                elif "meow next tn" in message.lower():
                    room = message.lower().split("meow next tn")[-1].strip()
                    if not room:
                        await ws.send(f"|/pm {from_user}, Meo...could you tell me which room you're asking about? Usage: meow next tn <room>")
                        continue

                    nx_schedule = get_current_tour_schedule(room)
                    next_tour = get_next_tournight(nx_schedule)

                    if next_tour is None:
                        await ws.send(f"|/pm {from_user}, Meow, I couldn't find any upcoming tournights for that room right now ;w;")
                    else:
                        minutes = next_tour['minutes_until']

                        # Convert minutes into a nicer format
                        if minutes >= 1440:  # 1 day+
                            days = minutes // 1440
                            hours = (minutes % 1440) // 60
                            time_str = f"{days} day(s) and {hours} hour(s)"
                        elif minutes >= 120:  # 2 hours+
                            hours = minutes // 60
                            time_str = f"{hours} hour(s)"
                        else:
                            time_str = f"{minutes} minute(s)"

                        await ws.send(
                            f"|/pm {from_user}, Meow, the next tournight is {next_tour['name'].title()} "
                            f"at {next_tour['hour']:02d}:{next_tour['minute']:02d} (GMT-4). "
                            f"That's in about {time_str}! >:3"
                        )
                elif "meow help" in message.lower():
                    pm_response = f"|/pm {from_user}, Meow! Here are the commands you can use: meow, meow next tn <room>, meow help"
                    await ws.send(pm_response)
                elif "meow" in message.lower():
                    print(f"Received Meow PM from {from_user}: {message}")
                    cat_url = await get_random_cat_url()
                    if cat_url:
                        pm_response = f'|/pm {from_user}, /show {cat_url}'
                        await ws.send(pm_response)
                        pm_response = f'|/pm {from_user}, I tried to send this link {cat_url}'
                        await ws.send(pm_response)
                        pm_response = f"|/pm {from_user}, Meow! Look at this car :3c"
                        await ws.send(pm_response)
                        print(f"Sent cat image: {pm_response}")
                else:
                    pm_response = f"|/pm {from_user}, Meow! I don't understand that command yet, but I'm learning new things every day :3c. You can try Meow help maybe?"
                    await ws.send(pm_response)
                    print(f"Sent auto PM response: {pm_response}")
async def main():
    print(await get_random_cat_url())
    print(await get_random_cat_saying("Its flutter manes fault meow"))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

