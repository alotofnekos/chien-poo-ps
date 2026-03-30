import inspect

async def create_token(ps_username: str, room: str, supabase) -> str:
    query = supabase.rpc("create_auth_token", {
        "p_ps_username": ps_username[1:],
        "p_room": room,
    }).execute()

    # If async client, await it
    if inspect.isawaitable(query):
        result = await query
    else:
        result = query

    if not result or result.data is None:
        raise Exception("Failed to create token")

    return result.data


async def consume_token(token: str, supabase) -> dict | None:
    query = supabase.rpc("consume_auth_token", {
        "p_token": token
    }).execute()

    if inspect.isawaitable(query):
        result = await query
    else:
        result = query

    if not result or not result.data:
        return None

    return result.data[0]