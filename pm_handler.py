import aiohttp

async def get_random_cat_url():
    url = "https://api.thecatapi.com/v1/images/search"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data[0]["url"]  
    return None


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

                if "meow" in message.lower():
                    print(f"Received Meow PM from {from_user}: {message}")
                    cat_url = await get_random_cat_url()
                    if cat_url:
                        pm_response = f'|/pm {from_user}, /addhtmlbox <img src="{cat_url}">'
                        await ws.send(pm_response)
                        pm_response = f"|/pm {from_user}, Meow! Look at this car :3c"
                        await ws.send(pm_response)
                        print(f"Sent cat image: {pm_response}")
                else:
                    pm_response = f"|/pm {from_user}, Meow! I'm still in progress!"
                    await ws.send(pm_response)
                    print(f"Sent auto PM response: {pm_response}")

