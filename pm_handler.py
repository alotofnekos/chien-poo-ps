import re
import aiohttp
from set_handler import parse_command_and_get_sets
from better_profanity import profanity
from tn import get_current_tour_schedule, get_next_tournight
from tour_creator import supabase
from meow_token import create_token

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

async def get_random_cat_url():
    url = "https://cataas.com/cat?json=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None) 
                return data["url"]
    return "No cat found :("

async def determine_if_message_is_ok(text):
    # Check if the message is profane
    text = text.lower()
    text = re.sub(r'(.)\1+', r'\1', text)
    chinese_badwords = ['cnm', 'nmsl', 'sb', 'sao', 'smd', 'sbh', 'sbl', 'sbd', 'sbm', 'sbj', 'sbp', 'sbz', 'sbq']
    profanity.load_censor_words(chinese_badwords)
    is_profane = profanity.contains_profanity(text)
    return is_profane

async def get_random_cat_saying(message):
    if await determine_if_message_is_ok(message) == False:
        url = f"https://cataas.com/cat/says/{message}?position=center&json=true&font=Impact&fontSize=30&fontColor=%23fff&fontBackground=none"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data['url']
    else:
        return "Meow! I dont think I should say that :3c"

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
    print(await get_random_cat_saying("hewwo"))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

