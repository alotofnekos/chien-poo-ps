import asyncio
from pathlib import Path
from aiohttp import web
from aiohttp_session import get_session
from meow_token import consume_token
from tour_creator import get_all_tours
from meow_supabase import get_async_supabase, supabase as sync_supabase  # ← import both from here
import os
from dotenv import load_dotenv
load_dotenv()

DIST = Path(__file__).parent / "web" / "dist"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_auth(handler):
    async def wrapper(request):
        session = await get_session(request)
        if "user" not in session:
            return web.json_response({"error": "Unauthorized"}, status=401)
        return await handler(request)
    return wrapper


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

async def handle_auth(request):
    token  = request.rel_url.query.get("token", "")
    result = await consume_token(token, sync_supabase)

    if not result:
        raise web.HTTPFound("/login?error=invalid_token")

    session = await get_session(request)
    session.clear()
    session["pending_user"] = result["ps_username"]
    session["pending_room"]  = result["room"]
    raise web.HTTPFound("/confirm")


async def handle_confirm(request):
    session = await get_session(request)
    pending = session.get("pending_user")
    room    = session.get("pending_room")
    print(f"[DEBUG] confirm hit — pending_user={pending}, pending_room={room}")

    if not pending or not room:
        return web.json_response({"error": "No pending session"}, status=400)

    data    = await request.json()
    claimed = (data.get("username") or "").strip().lower()

    if claimed != pending.lower():
        session.pop("pending_user", None)
        session.pop("pending_room", None)
        return web.json_response({"error": "Username mismatch"}, status=403)

    session.pop("pending_user")
    session.pop("pending_room")
    session["user"] = pending
    session["room"] = room
    return web.json_response({"ok": True, "user": pending, "room": room})


async def handle_me(request):
    session = await get_session(request)
    if "user" in session:
        return web.json_response({
            "authenticated": True,
            "user": session["user"],
            "room": session["room"],
        })
    if "pending_user" in session:
        return web.json_response({"authenticated": False, "pending": True})
    return web.json_response({"authenticated": False, "pending": False})


async def handle_logout(request):
    session = await get_session(request)
    session.clear()
    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# Tours
# ---------------------------------------------------------------------------

@require_auth
async def handle_get_tours(request):
    session = await get_session(request)
    room    = session["room"]

    # get_all_tours is sync so still needs executor
    loop          = asyncio.get_event_loop()
    internalnames = await loop.run_in_executor(None, lambda: get_all_tours(room))
    tours         = [{"tour_internalname": t, "tour_name": t} for t in internalnames]
    return web.json_response(tours)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@require_auth
async def handle_get_schedule(request):
    session = await get_session(request)
    room    = session["room"]
    db      = await get_async_supabase()

    result = await db.rpc("get_schedule", {"p_room": room}).execute()
    return web.json_response(result.data)


@require_auth
async def handle_save_schedule(request):
    session  = await get_session(request)
    room     = session["room"]
    username = session["user"]
    slots    = await request.json()
    db       = await get_async_supabase()

    result = await db.rpc("save_schedule", {
        "p_room":       room,
        "p_slots":      slots,
        "p_changed_by": username
    }).execute()

    if not result or result.data is not True:
        return web.json_response({"error": "failed to save schedule"}, status=400)

    # Invalidate tn.py's cache so the bot picks up changes immediately
    from tn import invalidate_schedule_cache
    invalidate_schedule_cache(room)

    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# Serve React
# ---------------------------------------------------------------------------

async def handle_react(request):
    index = DIST / "index.html"
    if not index.exists():
        return web.Response(
            text="Dashboard not built yet. Run: cd web && npm run build",
            status=503
        )
    return web.FileResponse(index)


# ---------------------------------------------------------------------------
# Register routes
# ---------------------------------------------------------------------------

def setup_routes(app: web.Application):
    app.router.add_get ("/auth",          handle_auth)
    app.router.add_post("/confirm",        handle_confirm)
    app.router.add_get ("/me",             handle_me)
    app.router.add_post("/logout",         handle_logout)
    app.router.add_get ("/api/tours",      handle_get_tours)
    app.router.add_get ("/api/schedule",   handle_get_schedule)
    app.router.add_post("/api/schedule",   handle_save_schedule)

    if DIST.exists():
        app.router.add_static("/assets", DIST / "assets")

    app.router.add_get("/{path_info:.*}", handle_react)