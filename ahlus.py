import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import json
import os
import logging
import traceback

# ---------------- CONFIG ----------------
import os
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1411582058282876972
MOD_LOG_CHANNEL_ID = 1411631150304329728
LOG_CHANNEL_ID = 1412769718162423843
WELCOME_CHANNEL_ID = 1411583450112069672
CASES_FILE = "cases.json"
TEMPBANS_FILE = "tempbans.json"
TEMPMUTES_FILE = "tempmutes.json"
TEMP_TIMEOUTS_FILE = "temptimeouts.json"

# Roles & IDs
SUPREME_ID = 1261645939337203742
GRAND_JUSTICE_ROLE = "Grand Justice 🏛"
JUSTICE_ROLE = "Justice 🏛"
GUARDIAN_ROLE = "Guardian of Justice ⚖️"

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("secretary")

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- PERSISTENCE HELPERS ----------------
def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=4)

def load_json(path):
    ensure_file(path, {})
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

ensure_file(CASES_FILE, {"case_counter": 0, "cases": []})
ensure_file(TEMPBANS_FILE, {})
ensure_file(TEMPMUTES_FILE, {})
ensure_file(TEMP_TIMEOUTS_FILE, {})

CASE_DATA = load_json(CASES_FILE)
TEMPBAN_DATA = load_json(TEMPBANS_FILE)
TEMPMUTE_DATA = load_json(TEMPMUTES_FILE)
TEMPTIMEOUT_DATA = load_json(TEMP_TIMEOUTS_FILE)

# ---------------- UTIL HELPERS ----------------
def next_case_id():
    CASE_DATA["case_counter"] = CASE_DATA.get("case_counter", 0) + 1
    save_json(CASES_FILE, CASE_DATA)
    return CASE_DATA["case_counter"]

def add_case_record(action, user_id, moderator_id, reason, extra=None):
    cid = next_case_id()
    rec = {
        "case_id": cid,
        "action": action,
        "user_id": user_id,
        "moderator_id": moderator_id,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    if extra:
        rec.update(extra)
    CASE_DATA.setdefault("cases", []).append(rec)
    save_json(CASES_FILE, CASE_DATA)
    return rec

def find_case(case_id):
    for c in CASE_DATA.get("cases", []):
        if c.get("case_id") == case_id:
            return c
    return None

async def safe_send_channel(channel_id, embed_or_msg):
    ch = bot.get_channel(channel_id)
    if ch is None:
        logger.warning(f"Channel {channel_id} not found or bot lacks access")
        return False
    try:
        if isinstance(embed_or_msg, discord.Embed):
            await ch.send(embed=embed_or_msg)
        else:
            await ch.send(embed_or_msg)
        return True
    except Exception:
        logger.exception("Failed to send to channel %s", channel_id)
        return False

async def send_dm(user: discord.User, action: str, reason: str, duration=None):
    try:
        description = f"You have been {action} on Ahlus-Sunnah Wal-Jamā'ah.\n\nReason: {reason}"
        if duration:
            description += f"\nDuration: {duration}"
        emb = discord.Embed(description=description, color=discord.Color.red())
        await user.send(embed=emb)
    except Exception:
        pass

# ---------------- EMBED FORMATTING ----------------
def create_case_embed(action, moderator, user_obj, reason, color_hex, case_id, duration=None):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    desc = (
        f"User: {user_obj.mention} — {user_obj} ({user_obj.id})\n"
        f"Reason: {reason}\n"
        f"Moderator: {moderator.mention} — {moderator} ({moderator.id})\n"
        f"Time: {timestamp}"
    )
    if duration:
        desc += f"\nDuration: {duration}"
    emb = discord.Embed(
        title=f"{action} | Case #{case_id}",
        description=desc,
        color=color_hex
    )
    emb.set_footer(text="Logged by Secretary of Ahlus-Sunnah")
    return emb

def create_simple_embed(title, description, color_hex):
    emb = discord.Embed(title=title, description=description, color=color_hex)
    return emb

# ---------------- TEMPBAN / MUTE / TIMEOUT SCHEDULERS ----------------
# (scheduling functions omitted for brevity in this snippet; same logic as original)

async def schedule_unmute_task(user_id, unmute_ts):
    await asyncio.sleep(max(0, unmute_ts - datetime.utcnow().timestamp()))
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if mute_role in member.roles:
            await member.remove_roles(mute_role, reason="Auto unmute (time expired)")


async def schedule_unban_task(user_id, unban_ts):
    await asyncio.sleep(max(0, unban_ts - datetime.utcnow().timestamp()))
    guild = bot.get_guild(GUILD_ID)
    user = await bot.fetch_user(user_id)
    await guild.unban(user, reason="Auto unban (time expired)")


# ---------------- PERMISSION LOGIC ----------------
def _has_role_obj(member, role_name):
    return discord.utils.get(member.roles, name=role_name) is not None

def can_moderate(executor: discord.Member, target: discord.Member, action_name: str):
    if target.id == SUPREME_ID:
        return False, "You cannot take moderation actions on the Supreme."

    has_justice = _has_role_obj(executor, JUSTICE_ROLE)
    has_grand = _has_role_obj(executor, GRAND_JUSTICE_ROLE)
    has_guardian = _has_role_obj(executor, GUARDIAN_ROLE)
    is_supreme_executor = executor.id == SUPREME_ID
    action = action_name.lower()

    # Justices restrictions
    if has_justice:
        if action in ("kick", "tempban", "unban", "ban", "say"):
            return False, "Justices cannot execute this command."
        if _has_role_obj(target, JUSTICE_ROLE) and target.id != executor.id:
            return False, "Justices cannot take moderation actions on other Justices."
        if _has_role_obj(target, GRAND_JUSTICE_ROLE) and action != "warn":
            return False, "Justices may only warn Grand Justices."

    # Grand Justice restrictions
    if has_grand:
        if action == "ban":
            return False, "Grand Justices are not allowed to ban."
        if _has_role_obj(target, GRAND_JUSTICE_ROLE) and action != "warn":
            return False, "Grand Justices may only warn other Grand Justices."

    # Guardian restrictions
    if action in ("ban", "unban") and not (has_guardian or is_supreme_executor):
        return False, "Only Guardian or Supreme can ban/unban."

    # Supreme can do everything
    return True, None

# ---------------- ACTION LOGGER ----------------
async def log_action(ctx, action_name, member: discord.Member, reason, color, duration=None):
    allowed, msg = can_moderate(ctx.author, member, action_name)
    if not allowed:
        await ctx.send(msg)
        return None

    rec = add_case_record(action_name, member.id, ctx.author.id, reason, extra={"duration": duration})
    emb = create_case_embed(action_name, ctx.author, member, reason, color, rec["case_id"], duration)
    await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)
    await send_dm(member, action_name, reason, duration)
    return rec["case_id"]

# ---------------- MOD COMMANDS (Always Send Verification) ----------------

@bot.command()
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Warn", member, reason, 0x001F54)
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully warned. {case_text}")


@bot.command()
async def mute(ctx, member: discord.Member, duration_minutes: int = None, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Mute", member, reason, 0xFF0000, f"{duration_minutes} minutes" if duration_minutes else None)
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role:
        await member.add_roles(mute_role, reason=reason)
    if duration_minutes:
        unmute_ts = datetime.utcnow().timestamp() + duration_minutes * 60
        TEMPMUTE_DATA[str(member.id)] = unmute_ts
        save_json(TEMPMUTES_FILE, TEMPMUTE_DATA)
        asyncio.create_task(schedule_unmute_task(member.id, unmute_ts))
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully muted. {case_text}")

from datetime import datetime, timedelta

@bot.command()
async def timeout(ctx, member: discord.Member, duration_minutes: int = None, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Timeout", member, reason, 0xFFFF00, f"{duration_minutes} minutes" if duration_minutes else None)
    if not case_id:
        return

    try:
        # make it timezone-aware (important!)
        from datetime import timezone
        until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes else None

        await member.edit(timed_out_until=until, reason=reason)

        if duration_minutes:
            untimeout_ts = datetime.now(timezone.utc).timestamp() + duration_minutes * 60
            TEMPTIMEOUT_DATA[str(member.id)] = untimeout_ts
            save_json(TEMP_TIMEOUTS_FILE, TEMPTIMEOUT_DATA)

        await ctx.send(f"{member.mention} has been timed out. (Case #{case_id})")

    except discord.Forbidden:
        await ctx.send("I don’t have permission to timeout this member.")
    except Exception as e:
        await ctx.send(f"Failed to timeout {member.mention}: `{e}`")
        logger.exception("Timeout error")

@bot.command()
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Kick", member, reason, 0xFF4500)
    try:
        await member.kick(reason=reason)
    except Exception:
        logger.exception("Kick failed")
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully kicked. {case_text}")


@bot.command()
@commands.has_role(1413810618359615488)  # Department of Justice
async def vm(ctx, member: discord.Member):
    male_role = ctx.guild.get_role(1414269022945677353)
    member_role = ctx.guild.get_role(1413518414697463818)
    unverified_role = ctx.guild.get_role(1425815375714455622)
    await member.add_roles(male_role, member_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"✅ {member.mention} successfully verified as **Male** and given the Member role.")


@bot.command()
@commands.has_role(1413810618359615488)  # Department of Justice
async def vf(ctx, member: discord.Member):
    female_role = ctx.guild.get_role(1414269196543721502)
    member_role = ctx.guild.get_role(1413518414697463818)
    unverified_role = ctx.guild.get_role(1425815375714455622)
    await member.add_roles(female_role, member_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"✅ {member.mention} successfully verified as **Female** and given the Member role.")


@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Ban", member, reason, 0x8A0303)
    try:
        await member.ban(reason=reason)
    except Exception:
        logger.exception("Ban failed")
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully banned. {case_text}")


@bot.command()
async def tempban(ctx, member: discord.Member, duration_minutes: int, *, reason="No reason provided"):
    case_id = await log_action(ctx, "TempBan", member, reason, 0xFF0000, f"{duration_minutes} minutes")
    try:
        await member.ban(reason=reason)
    except Exception:
        logger.exception("Tempban ban failed")
    unban_ts = datetime.utcnow().timestamp() + duration_minutes * 60
    TEMPBAN_DATA[str(member.id)] = unban_ts
    save_json(TEMPBANS_FILE, TEMPBAN_DATA)
    asyncio.create_task(schedule_unban_task(member.id, unban_ts))
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully temp-banned for {duration_minutes} minutes. {case_text}")


@bot.command()
async def unmute(ctx, member: discord.Member):
    case_id = await log_action(ctx, "Unmute", member, "Action executed", 0x00FF00)
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role and mute_role in member.roles:
        await member.remove_roles(mute_role, reason="Unmute command executed")
    TEMPMUTE_DATA.pop(str(member.id), None)
    save_json(TEMPMUTES_FILE, TEMPMUTE_DATA)
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully unmuted. {case_text}")


@bot.command()
async def removetimeout(ctx, member: discord.Member):
    case_id = await log_action(ctx, "TimeoutRemoved", member, "Action executed", 0x00FF00)
    await member.edit(timed_out_until=None, reason="Timeout removed by moderator")
    TEMPTIMEOUT_DATA.pop(str(member.id), None)
    save_json(TEMP_TIMEOUTS_FILE, TEMPTIMEOUT_DATA)
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} timeout successfully removed. {case_text}")


@bot.command()
async def unban(ctx, user: discord.User):
    class _Tmp:
        def __init__(self, uid):
            self.id = uid
            self.roles = []

    allowed, msg = can_moderate(ctx.author, _Tmp(user.id), "unban")
    if not allowed:
        await ctx.send(msg)
        return
    try:
        await ctx.guild.unban(user)
    except Exception:
        logger.exception("Unban failed")
    rec = add_case_record("Unban", user.id, ctx.author.id, "Action executed")
    emb = create_case_embed("Unban", ctx.author, user, "Action executed", 0x00FF00, rec["case_id"])
    await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)
    await send_dm(user, "Unban", "Action executed")
    case_text = f"(Case #{rec['case_id']})" if rec else "(Case #N/A)"
    await ctx.send(f"{user.mention} successfully unbanned. {case_text}")


import asyncio
import json

# ---------- TEMPORARY PUNISHMENT RESTORATION ----------

def restore_tempban_tasks():
    """Re-schedule unfinished tempbans after restart."""
    try:
        with open("tempbans.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return

    for ban in data.get("active_bans", []):
        user_id = ban.get("user_id")
        guild_id = ban.get("guild_id")
        end_time = ban.get("end_time")

        if not all([user_id, guild_id, end_time]):
            continue

        remaining = datetime.datetime.fromisoformat(end_time) - datetime.datetime.utcnow()
        if remaining.total_seconds() > 0:
            asyncio.create_task(schedule_unban(guild_id, user_id, remaining.total_seconds()))


def restore_tempmute_tasks():
    """Re-schedule unfinished tempmutes after restart."""
    try:
        with open("tempmutes.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return

    for mute in data.get("active_mutes", []):
        user_id = mute.get("user_id")
        guild_id = mute.get("guild_id")
        end_time = mute.get("end_time")

        if not all([user_id, guild_id, end_time]):
            continue

        remaining = datetime.datetime.fromisoformat(end_time) - datetime.datetime.utcnow()
        if remaining.total_seconds() > 0:
            asyncio.create_task(schedule_unmute(guild_id, user_id, remaining.total_seconds()))


def restore_timeout_tasks():
    """Re-schedule unfinished timeouts after restart."""
    try:
        with open("timeouts.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return

    for timeout in data.get("active_timeouts", []):
        user_id = timeout.get("user_id")
        guild_id = timeout.get("guild_id")
        end_time = timeout.get("end_time")

        if not all([user_id, guild_id, end_time]):
            continue

        remaining = datetime.datetime.fromisoformat(end_time) - datetime.datetime.utcnow()
        if remaining.total_seconds() > 0:
            asyncio.create_task(schedule_timeout_removal(guild_id, user_id, remaining.total_seconds()))

# ---------------- CASE COMMANDS ----------------

@bot.command()
async def cases(ctx, member: discord.Member):
    """Show all case IDs for a user"""
    user_cases = [c for c in CASE_DATA.get("cases", []) if c.get("user_id") == member.id]
    if not user_cases:
        await ctx.send(f"No cases found for {member.mention}.")
        return

    # Build numbered list
    lines = [f"{i+1}. Case {c['case_id']}" for i, c in enumerate(user_cases)]
    msg = "\n".join(lines)

    emb = discord.Embed(
        title=f"Cases for {member}",
        description=msg,
        color=discord.Color.blue()
    )
    await ctx.send(embed=emb)


@bot.command()
async def caseinfo(ctx, case_id: int):
    """Show full info for a case (basically recreate mod-log embed)"""
    case = find_case(case_id)
    if not case:
        await ctx.send(f"No case found with ID {case_id}.")
        return

    guild = ctx.guild
    user = guild.get_member(case["user_id"]) or await bot.fetch_user(case["user_id"])
    mod = guild.get_member(case["moderator_id"]) or await bot.fetch_user(case["moderator_id"])

    emb = create_case_embed(
        action=case["action"],
        moderator=mod,
        user_obj=user,
        reason=case["reason"],
        color_hex=discord.Color.orange(),
        case_id=case["case_id"],
        duration=case.get("duration")
    )
    await ctx.send(embed=emb)


@bot.command()
async def deletecase(ctx, case_id: int):
    """Delete a case from the records (staff only)"""
    case = find_case(case_id)
    if not case:
        await ctx.send(f"No case found with ID {case_id}.")
        return

    # Remove from CASE_DATA
    CASE_DATA["cases"] = [c for c in CASE_DATA["cases"] if c["case_id"] != case_id]
    save_json(CASES_FILE, CASE_DATA)

    await ctx.send(f"Case {case_id} has been deleted successfully.")


# ---------------- WICK AUTOMOD LOGGING (FULL) ----------------
@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
    """
    Logs any moderation action performed by Wick automod or other bots.
    Detects duration for temp-mutes, temp-bans, and timeouts.
    Automatically creates a case and sends an embed to the mod-log channel.
    """
    if not entry.user or not entry.user.bot:
        return

    wick_name = str(entry.user.name).lower()
    if "wick" not in wick_name:
        return

    if entry.guild.id != GUILD_ID:
        return

    target = entry.target
    reason = entry.reason or "No reason provided."

    # Map Discord AuditLogAction to action names
    action_map = {
        discord.AuditLogAction.ban: "Ban",
        discord.AuditLogAction.kick: "Kick",
        discord.AuditLogAction.member_update: "Timeout",
        discord.AuditLogAction.member_role_update: "Mute/Unmute",
        discord.AuditLogAction.message_delete: "Message Delete",
    }

    if entry.action not in action_map:
        return

    action_name = action_map[entry.action]

    target_id = getattr(target, "id", 0)
    target_display = str(target) if target else "Unknown target"

    # Detect duration if applicable
    duration_str = None
    from datetime import datetime, timezone

    if action_name == "Timeout" and isinstance(target, discord.Member):
        if target.timed_out_until:
            now = datetime.now(timezone.utc)
            delta = target.timed_out_until - now
            minutes = int(delta.total_seconds() // 60)
            if minutes > 0:
                duration_str = f"{minutes} minutes"

    elif action_name == "Mute/Unmute" and isinstance(target, discord.Member):
        # Optional: detect temp-mute role and infer duration if stored
        # You can cross-check TEMPMUTE_DATA for temp-mutes
        unmute_ts = TEMPMUTE_DATA.get(str(target.id))
        if unmute_ts:
            now_ts = datetime.now(timezone.utc).timestamp()
            remaining = int((unmute_ts - now_ts) // 60)
            if remaining > 0:
                duration_str = f"{remaining} minutes"

    elif action_name == "Ban" and isinstance(target, discord.User):
        # Check TEMPBAN_DATA for temp-bans
        unban_ts = TEMPBAN_DATA.get(str(target.id))
        if unban_ts:
            now_ts = datetime.now(timezone.utc).timestamp()
            remaining = int((unban_ts - now_ts) // 60)
            if remaining > 0:
                duration_str = f"{remaining} minutes (TempBan)"

    # Add to case system
    rec = add_case_record(
        action=action_name,
        user_id=target_id,
        moderator_id=entry.user.id,
        reason=reason,
        extra={"duration": duration_str}
    )

    # Embed color
    color = discord.Color.orange()
    if action_name == "Ban":
        color = discord.Color.dark_red()
    elif action_name == "Kick":
        color = discord.Color.orange()
    elif action_name in ("Timeout", "Mute/Unmute"):
        color = discord.Color.yellow()

    # Fetch user object
    user_obj = target if isinstance(target, discord.Member) else None
    if not user_obj and target_id:
        try:
            user_obj = await bot.fetch_user(target_id)
        except Exception:
            user_obj = None

    moderator = entry.user

    emb = create_case_embed(
        action=action_name,
        moderator=moderator,
        user_obj=user_obj or moderator,
        reason=reason,
        color_hex=color,
        case_id=rec["case_id"],
        duration=duration_str
    )

    # Send to mod-log
    await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)
    logger.info(f"[Wick Automod] Logged {action_name} for {target_display} (Case #{rec['case_id']}) Duration: {duration_str or 'N/A'}")

# ---------------- SAY COMMAND ----------------

@bot.command()
@commands.is_owner()
async def say(ctx, guild_id: int, channel_id: int, embed_hex: str, *, message: str):
    guild = bot.get_guild(guild_id)
    if not guild:
        await ctx.send("Guild not found.")
        return

    channel = guild.get_channel(channel_id)
    if not channel:
        await ctx.send("Channel not found or bot has no access.")
        return

    try:
        color = int(embed_hex.replace("#", ""), 16)
    except Exception:
        await ctx.send("Invalid hex color.")
        return

    emb = discord.Embed(description=message, color=color)
    await channel.send(embed=emb)
    await ctx.send(f"Message sent to {channel.mention} in {guild.name}")


# ---------------- WELCOME / LEAVE ----------------

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    emb = discord.Embed(
        title="🌿 Welcome!",
        description=(
            f"Welcome to {member.guild.name}, {member.mention}!\n\n"
            f"👤 User: {member.name}#{member.discriminator}\n"
            f"🆔 ID: {member.id}\n"
            f"📊 Members Now: {member.guild.member_count}"
        ),
        color=0x2ecc71
    )
    emb.set_thumbnail(url=(member.avatar.url if member.avatar else member.default_avatar.url))
    emb.set_footer(text="Secretary of Ahlus-Sunnah welcomes you")
    await safe_send_channel(WELCOME_CHANNEL_ID, emb)


@bot.event
async def on_member_remove(member):
    if member.bot:
        return

    emb = discord.Embed(
        title="🍃 Member Left",
        description=(
            f"{member.mention} has left {member.guild.name}.\n\n"
            f"👤 User: {member.name}#{member.discriminator}\n"
            f"🆔 ID: {member.id}\n"
            f"📊 Members Now: {member.guild.member_count}"
        ),
        color=0xe74c3c
    )
    emb.set_thumbnail(url=(member.avatar.url if member.avatar else member.default_avatar.url))
    emb.set_footer(text="Secretary of Ahlus-Sunnah logs departures")
    await safe_send_channel(WELCOME_CHANNEL_ID, emb)


# ---------------- MESSAGE EDIT/DELETE LOGGING ----------------

@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return
    if before.content == after.content and len(before.attachments) == len(after.attachments):
        return

    embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.orange())
    embed.add_field(name="Author", value=f"{before.author.mention} ({before.author})", inline=False)
    embed.add_field(name="Channel", value=before.channel.mention, inline=False)

    if before.content:
        b = before.content if len(before.content) <= 1000 else before.content[:997] + "..."
        embed.add_field(name="Before", value=b, inline=False)
    if after.content:
        a = after.content if len(after.content) <= 1000 else after.content[:997] + "..."
        embed.add_field(name="After", value=a, inline=False)

    if before.attachments or after.attachments:
        old_att = "\n".join([a.url for a in before.attachments]) or "None"
        new_att = "\n".join([a.url for a in after.attachments]) or "None"
        embed.add_field(name="Before Attachments", value=old_att, inline=False)
        embed.add_field(name="After Attachments", value=new_att, inline=False)

    embed.set_footer(text=f"User ID: {before.author.id}")
    embed.timestamp = discord.utils.utcnow()
    await safe_send_channel(LOG_CHANNEL_ID, embed)


@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return

    embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red())
    embed.add_field(name="Author", value=f"{message.author.mention} ({message.author})", inline=False)
    embed.add_field(name="Channel", value=message.channel.mention, inline=False)

    if message.content:
        content = message.content if len(message.content) <= 1000 else message.content[:997] + "..."
        embed.add_field(name="Content", value=content, inline=False)

    if message.attachments:
        attachments = "\n".join([a.url for a in message.attachments])
        embed.add_field(name="Attachments", value=attachments, inline=False)

    embed.set_footer(text=f"User ID: {message.author.id}")
    embed.timestamp = discord.utils.utcnow()
    await safe_send_channel(LOG_CHANNEL_ID, embed)


# ---------------- SECONDARY BOT MESSAGE PROCESSING ----------------

SECONDARY_BOT_ID = 1418222185985867897


@bot.event
async def on_message(message):
    if message.author.bot and message.author.id == SECONDARY_BOT_ID:
        ctx = await bot.get_context(message)
        await bot.invoke(ctx)
        return

    await bot.process_commands(message)


# ---------------- READY & ERROR ----------------

@bot.event
async def on_ready():
    logger.info("[DEBUG] Bot is fully ready!")
    logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    restore_tempban_tasks()
    restore_tempmute_tasks()
    restore_timeout_tasks()

    for cid in (MOD_LOG_CHANNEL_ID, LOG_CHANNEL_ID, WELCOME_CHANNEL_ID):
        logger.info("Channel %s resolves to: %s", cid, bot.get_channel(cid))


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Unhandled exception in event {event}")
    logger.error(traceback.format_exc())


# ---------------- RUN ----------------

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception:
        logger.exception("Failed to start bot")

