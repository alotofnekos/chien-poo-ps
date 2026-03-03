import re

import aiohttp
from set_handler import parse_command_and_get_sets
from better_profanity import profanity

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

                if "meow" in message.lower():
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
                    pm_response = f"|/pm {from_user}, Meow! I'm still in progress!"
                    await ws.send(pm_response)
                    print(f"Sent auto PM response: {pm_response}")
async def main():
    print(await get_random_cat_url())
    print(await get_random_cat_saying("hewwo"))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

