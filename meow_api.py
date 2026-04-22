import asyncio
from pathlib import Path
from aiohttp import web
from aiohttp_session import get_session
from meow_token import consume_token
from tour_creator import (
    get_all_tours, get_tour_info, get_tour_bans,
    add_tour, remove_tour,
    add_tour_bans, remove_tour_bans,
    add_misc_commands, remove_misc_commands,
)
from meow_supabase import get_async_supabase, supabase as sync_supabase
import os
from dotenv import load_dotenv
from tn import invalidate_schedule_cache
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


async def _run(fn, *args):
    """Run a sync function in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args))

async def _log_tour_action(room, tour, action, changed_by, detail=None):
    db = await get_async_supabase()
    await db.table("tour_audit_log").insert({
        "room":       room,
        "tour":       tour,
        "action":     action,
        "changed_by": changed_by,
        "detail":     detail or {},
    }).execute()

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
    session["pending_rank"] = result["rank"] 
    raise web.HTTPFound("/confirm")

async def handle_confirm(request):
    session = await get_session(request)
    pending = session.get("pending_user")
    room    = session.get("pending_room")

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
    session["rank"] = session.pop("pending_rank", "+")  
    return web.json_response({"ok": True, "user": pending, "room": room, "rank": session["rank"]})  


async def handle_me(request):
    session = await get_session(request)
    if "user" in session:
        return web.json_response({
            "authenticated": True,
            "user": session["user"],
            "room": session["room"],
            "rank": session.get("rank", "+"), 
        })
    if "pending_user" in session:
        return web.json_response({"authenticated": False, "pending": True})
    return web.json_response({"authenticated": False, "pending": False})


async def handle_logout(request):
    session = await get_session(request)
    session.clear()
    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# Tours list 
# ---------------------------------------------------------------------------

@require_auth
async def handle_get_tours(request):
    session       = await get_session(request)
    room          = session["room"]
    internalnames = await _run(get_all_tours, room)
    tours         = [{"tour_internalname": t, "tour_name": t} for t in internalnames]
    return web.json_response(tours)


# ---------------------------------------------------------------------------
# Tour manager — single tour CRUD
# ---------------------------------------------------------------------------

@require_auth
async def handle_get_tour(request):
    session = await get_session(request)
    room    = session["room"]
    name    = request.match_info["name"]

    info = await _run(get_tour_info, room, name)
    if not info:
        return web.json_response({"error": "tour not found"}, status=404)
    return web.json_response(info)


@require_auth
async def handle_get_tour_bans(request):
    session = await get_session(request)
    room    = session["room"]
    name    = request.match_info["name"]

    raw = await _run(get_tour_bans, room, name)
    if isinstance(raw, str):
        items = [b.strip() for b in raw.split(",") if b.strip()]
    else:
        items = raw or []
    return web.json_response([{"ban": b} for b in items])


@require_auth
async def handle_create_tour(request):
    session = await get_session(request)
    room    = session["room"]
    body    = await request.json()

    internalname  = (body.get("tour_internalname") or "").strip()
    tour_type     = (body.get("tour_type") or "").strip()
    tour_name     = (body.get("tour_name") or "").strip()
    bans          = body.get("bans", [])
    misc_commands = body.get("misc_commands", [])

    if not internalname or not tour_type or not tour_name:
        return web.json_response(
            {"error": "tour_internalname, tour_type, and tour_name are required"},
            status=400,
        )

    ok = await _run(add_tour, room, internalname, tour_type, tour_name)
    if not ok:
        return web.json_response(
            {"error": f"'{internalname}' may already exist"},
            status=409,
        )

    if bans:
        await _run(add_tour_bans, room, internalname, ", ".join(bans))
    if misc_commands:
        await _run(add_misc_commands, room, internalname, ", ".join(misc_commands))
    await _log_tour_action(room, internalname, "create", session["user"])
    return web.json_response({"ok": True, "tour_internalname": internalname})


@require_auth
async def handle_update_tour(request):
    session = await get_session(request)
    room    = session["room"]
    name    = request.match_info["name"]
    body    = await request.json()

    info = await _run(get_tour_info, room, name)
    if not info:
        return web.json_response({"error": "tour not found"}, status=404)

    # tour_type and tour_name are immutable — only bans and misc are editable
    new_bans = body.get("bans", [])
    new_misc = body.get("misc_commands", [])

    # sync bans
    raw = await _run(get_tour_bans, room, name)
    current_bans = [b.strip() for b in raw.split(",") if b.strip()] if isinstance(raw, str) else (raw or [])

    to_remove = [b for b in current_bans if b not in new_bans]
    to_add    = [b for b in new_bans    if b not in current_bans]
    if to_remove:
        await _run(remove_tour_bans, room, name, ", ".join(to_remove))
    if to_add:
        await _run(add_tour_bans, room, name, ", ".join(to_add))

    # sync misc commands
    old_misc = info.get("misc_commands") or []
    if isinstance(old_misc, str):
        old_misc = [m.strip() for m in old_misc.split(",") if m.strip()]

    misc_remove = [m for m in old_misc if m not in new_misc]
    misc_add    = [m for m in new_misc  if m not in old_misc]
    if misc_remove:
        await _run(remove_misc_commands, room, name, ", ".join(misc_remove))
    if misc_add:
        await _run(add_misc_commands, room, name, ", ".join(misc_add))

    await _log_tour_action(room, name, "update", session["user"], {
        "bans_added": to_add, "bans_removed": to_remove,
        "misc_added": misc_add, "misc_removed": misc_remove,
    })
    return web.json_response({"ok": True})


@require_auth
async def handle_delete_tour(request):
    session = await get_session(request)
    room    = session["room"]
    name    = request.match_info["name"]

    ok = await _run(remove_tour, room, name)
    if not ok:
        return web.json_response(
            {"error": f"could not delete '{name}' — it may have dependent schedule rows or doesn't exist"},
            status=409,
        )
    await _log_tour_action(room, name, "delete", session["user"])
    return web.json_response({"ok": True})


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
    app.router.add_get   ("/auth",                  handle_auth)
    app.router.add_post  ("/confirm",               handle_confirm)
    app.router.add_get   ("/me",                    handle_me)
    app.router.add_post  ("/logout",                handle_logout)

    # tours list (existing)
    app.router.add_get   ("/api/tours",             handle_get_tours)

    # tour manager CRUD
    app.router.add_get   ("/api/tour/{name}/bans",  handle_get_tour_bans) 
    app.router.add_get   ("/api/tour/{name}",       handle_get_tour)
    app.router.add_post  ("/api/tour",              handle_create_tour)
    app.router.add_put   ("/api/tour/{name}",       handle_update_tour)
    app.router.add_delete("/api/tour/{name}",       handle_delete_tour)

    # schedule
    app.router.add_get   ("/api/schedule",          handle_get_schedule)
    app.router.add_post  ("/api/schedule",          handle_save_schedule)

    if DIST.exists():
        app.router.add_static("/assets", DIST / "assets")

    app.router.add_get("/{path_info:.*}", handle_react)