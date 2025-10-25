import os
import logging
import asyncio
import traceback
from datetime import datetime

import discord
from discord.ext import commands
import asyncpg

# ---------------- CONFIG ----------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1411582058282876972
MOD_LOG_CHANNEL_ID = 1411631150304329728
LOG_CHANNEL_ID = 1412769718162423843
WELCOME_CHANNEL_ID = 1411583450112069672

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

# ---------------- DATABASE SETUP ----------------
db_pool: asyncpg.pool.Pool = None  # global pool

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),  # e.g., Render Postgres URL
        min_size=1,
        max_size=10
    )
    async with db_pool.acquire() as conn:
        # Cases table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                case_id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                user_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                reason TEXT,
                duration TEXT,
                timestamp TIMESTAMPTZ DEFAULT now()
            );
        """)
        # Tempbans table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tempbans (
                user_id BIGINT PRIMARY KEY,
                unban_ts DOUBLE PRECISION NOT NULL
            );
        """)
        # Tempmutes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tempmutes (
                user_id BIGINT PRIMARY KEY,
                unmute_ts DOUBLE PRECISION NOT NULL
            );
        """)
        # Temp timeouts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS temptimeouts (
                user_id BIGINT PRIMARY KEY,
                untimeout_ts DOUBLE PRECISION NOT NULL
            );
        """)

# Call this in your main async entry point
# await init_db()

# ---------------- CASE HELPERS ----------------

async def add_case_record(
    action: str,
    user_id: int,
    moderator_id: int,
    reason: str,
    duration: str | None = None
) -> dict:
    """
    Insert a new moderation case into the database.
    Returns the inserted case as a dict including case_id and timestamp.
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO cases (action, user_id, moderator_id, reason, duration)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING case_id, action, user_id, moderator_id, reason, duration, timestamp;
        """, action, user_id, moderator_id, reason, duration)
        return dict(row)


async def find_case(case_id: int) -> dict | None:
    """
    Fetch a single case by case_id.
    Returns dict or None if not found.
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cases WHERE case_id=$1;", case_id)
        return dict(row) if row else None


async def get_user_cases(user_id: int) -> list[dict]:
    """
    Fetch all cases for a specific user, ordered by case_id.
    Returns a list of dicts.
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM cases WHERE user_id=$1 ORDER BY case_id;", user_id)
        return [dict(r) for r in rows]

# ---------------- TEMP PUNISHMENT HELPERS ----------------

# ---------------- TEMPBAN ----------------
async def set_tempban(user_id: int, unban_ts: float):
    """Set or update a temporary ban for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tempbans (user_id, unban_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET unban_ts = EXCLUDED.unban_ts;
        """, user_id, unban_ts)


async def remove_tempban(user_id: int):
    """Remove a temporary ban for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tempbans WHERE user_id=$1;", user_id)


async def get_all_tempbans() -> list[dict]:
    """Fetch all temporary bans."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tempbans;")
        return [dict(r) for r in rows]


# ---------------- TEMPMUTE ----------------
async def set_tempmute(user_id: int, unmute_ts: float):
    """Set or update a temporary mute for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tempmutes (user_id, unmute_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET unmute_ts = EXCLUDED.unmute_ts;
        """, user_id, unmute_ts)


async def remove_tempmute(user_id: int):
    """Remove a temporary mute for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tempmutes WHERE user_id=$1;", user_id)


async def get_all_tempmutes() -> list[dict]:
    """Fetch all temporary mutes."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tempmutes;")
        return [dict(r) for r in rows]


# ---------------- TIMEOUT ----------------
async def set_timeout(user_id: int, untimeout_ts: float):
    """Set or update a temporary timeout for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO temptimeouts (user_id, untimeout_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET untimeout_ts = EXCLUDED.untimeout_ts;
        """, user_id, untimeout_ts)


async def remove_timeout(user_id: int):
    """Remove a temporary timeout for a user."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM temptimeouts WHERE user_id=$1;", user_id)


async def get_all_timeouts() -> list[dict]:
    """Fetch all temporary timeouts."""
    async with db_pool.acquire() as conn:
        rows = await db_pool.fetch("SELECT * FROM temptimeouts;")
        return [dict(r) for r in rows]

# ---------------- UTIL HELPERS ----------------

# ---------------- CASE RECORD HELPERS ----------------
async def add_case_record_db(action: str, user_id: int, moderator_id: int, reason: str, duration: str | None = None) -> dict:
    """Add a new case to the database and return it."""
    return await add_case_record(action, user_id, moderator_id, reason, duration)


async def find_case_db(case_id: int) -> dict | None:
    """Fetch a case by ID from the database."""
    return await find_case(case_id)


async def get_user_cases_db(user_id: int) -> list[dict]:
    """Fetch all cases for a given user."""
    return await get_user_cases(user_id)


# ---------------- CHANNEL & DM HELPERS ----------------
async def safe_send_channel(channel_id: int, embed_or_msg) -> bool:
    """Send a message or embed to a channel, safely."""
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


async def send_dm(user: discord.User, action: str, reason: str, duration: str | None = None):
    """Send a DM to a user about an action taken against them."""
    try:
        description = f"You have been {action} on Ahlus-Sunnah Wal-Jamā'ah.\n\nReason: {reason}"
        if duration:
            description += f"\nDuration: {duration}"
        emb = discord.Embed(description=description, color=discord.Color.red())
        await user.send(embed=emb)
    except Exception:
        pass


# ---------------- MANUAL LOGGING ----------------
async def log_action_manual(
    action_name: str,
    target,
    reason: str,
    color_hex: int = 0x00FF00,
    moderator: discord.Member | None = None,
    duration: str | None = None
) -> int | None:
    """
    Logs an action manually (without ctx), stores it in DB, and posts embed to MOD_LOG_CHANNEL.
    Returns the case_id.
    """
    try:
        moderator_id = moderator.id if moderator else bot.user.id if bot.user else 0
        user_id = getattr(target, "id", int(target) if isinstance(target, (str, int)) else 0)
        
        # Add to DB
        rec = await add_case_record_db(action_name, user_id, moderator_id, reason, duration)

        # Resolve objects for embed
        moderator_obj = moderator or bot.user
        try:
            if isinstance(target, (discord.User, discord.Member)):
                user_obj = target
            else:
                user_obj = await bot.fetch_user(user_id)
        except Exception:
            user_obj = moderator_obj or None

        emb = create_case_embed(
            action_name,
            moderator_obj,
            user_obj or moderator_obj,
            reason,
            color_hex,
            rec["case_id"],
            duration,
            timestamp=rec.get("timestamp")  # optional, from DB
        )
        await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)
        return rec["case_id"]
    except Exception:
        logger.exception("log_action_manual failed")
        return None

# ---------------- EMBED FORMATTING ----------------
def create_case_embed(action, moderator, user_obj, reason, color_hex, case_id, duration=None, timestamp=None):
    """
    Create an embed for a moderation case.
    If timestamp is provided, use it (from DB); otherwise, fallback to UTC now.
    """
    timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M UTC") if timestamp else datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    desc = (
        f"User: {user_obj.mention} — {user_obj} ({user_obj.id})\n"
        f"Reason: {reason}\n"
        f"Moderator: {moderator.mention} — {moderator} ({moderator.id})\n"
        f"Time: {timestamp_str}"
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


# ---------------- PERMISSION LOGIC ----------------
def _has_role_obj(member, role_name):
    return discord.utils.get(member.roles, name=role_name) is not None


def can_moderate(executor: discord.Member, target: discord.Member, action_name: str):
    """
    Checks if executor can perform an action on target.
    Returns (bool, reason_str_or_None)
    """
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

# ---------------- ACTION LOGGER (ASYNC DB VERSION) ----------------
async def log_action(ctx, action_name, member: discord.Member, reason, color, duration=None):
    allowed, msg = can_moderate(ctx.author, member, action_name)
    if not allowed:
        await ctx.send(msg)
        return None

    try:
        # Add record to DB
        rec = await add_case_record(
            action=action_name,
            user_id=member.id,
            moderator_id=ctx.author.id,
            reason=reason,
            duration=duration
        )

        # Create embed using DB timestamp
        emb = create_case_embed(
            action=action_name,
            moderator=ctx.author,
            user_obj=member,
            reason=reason,
            color_hex=color,
            case_id=rec["case_id"],
            duration=duration,
            timestamp=rec.get("timestamp")  # DB timestamp
        )

        # Send to mod log channel
        await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)

        # DM the user
        await send_dm(member, action_name, reason, duration)

        return rec["case_id"]

    except Exception:
        logger.exception("Failed to log action")
        await ctx.send("An error occurred while logging the action.")
        return None

# ---------------- MOD COMMANDS (DB Version) ----------------
from datetime import datetime, timezone, timedelta

@bot.command()
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Warn", member, reason, 0x001F54)
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully warned. {case_text}")


@bot.command()
async def mute(ctx, member: discord.Member, duration_minutes: int = None, *, reason="No reason provided"):
    duration_str = f"{duration_minutes} minutes" if duration_minutes else None
    case_id = await log_action(ctx, "Mute", member, reason, 0xFF0000, duration_str)
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role and mute_role not in member.roles:
        await member.add_roles(mute_role, reason=reason)

    if duration_minutes:
        unmute_ts = datetime.now(timezone.utc).timestamp() + duration_minutes * 60
        await set_tempmute(member.id, unmute_ts)
        asyncio.create_task(schedule_unmute_task(member.id, unmute_ts))

    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully muted. {case_text}")


@bot.command()
async def timeout(ctx, member: discord.Member, duration_minutes: int = None, *, reason="No reason provided"):
    duration_str = f"{duration_minutes} minutes" if duration_minutes else None
    case_id = await log_action(ctx, "Timeout", member, reason, 0xFFFF00, duration_str)
    if not case_id:
        return

    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes else None
        await member.edit(timed_out_until=until, reason=reason)

        if duration_minutes:
            untimeout_ts = datetime.now(timezone.utc).timestamp() + duration_minutes * 60
            await set_timeout(member.id, untimeout_ts)
            asyncio.create_task(schedule_timeout_task(member.id, untimeout_ts))

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
    except discord.Forbidden:
        await ctx.send("I don’t have permission to kick this member.")
        return
    except Exception:
        logger.exception("Kick failed")
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully kicked. {case_text}")


@bot.command()
@commands.has_role(1413810618359615488)
async def vm(ctx, member: discord.Member):
    male_role = ctx.guild.get_role(1414269022945677353)
    member_role = ctx.guild.get_role(1413518414697463818)
    unverified_role = ctx.guild.get_role(1425815375714455622)
    await member.add_roles(male_role, member_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"✅ {member.mention} successfully verified as **Male**.")


@bot.command()
@commands.has_role(1413810618359615488)
async def vf(ctx, member: discord.Member):
    female_role = ctx.guild.get_role(1414269196543721502)
    member_role = ctx.guild.get_role(1413518414697463818)
    unverified_role = ctx.guild.get_role(1425815375714455622)
    await member.add_roles(female_role, member_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"✅ {member.mention} successfully verified as **Female**.")


@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = await log_action(ctx, "Ban", member, reason, 0x8A0303)
    try:
        await member.ban(reason=reason)
    except discord.Forbidden:
        await ctx.send("I don’t have permission to ban this member.")
        return
    except Exception:
        logger.exception("Ban failed")
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully banned. {case_text}")


@bot.command()
async def tempban(ctx, member: discord.Member, duration_minutes: int, *, reason="No reason provided"):
    duration_str = f"{duration_minutes} minutes"
    case_id = await log_action(ctx, "TempBan", member, reason, 0xFF0000, duration_str)
    try:
        await member.ban(reason=reason)
    except discord.Forbidden:
        await ctx.send("I don’t have permission to ban this member.")
        return
    except Exception:
        logger.exception("Tempban failed")

    unban_ts = datetime.now(timezone.utc).timestamp() + duration_minutes * 60
    await set_tempban(member.id, unban_ts)
    asyncio.create_task(schedule_unban_task(member.id, unban_ts))

    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully temp-banned for {duration_minutes} minutes. {case_text}")


@bot.command()
async def unmute(ctx, member: discord.Member):
    case_id = await log_action(ctx, "Unmute", member, "Action executed", 0x00FF00)
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role and mute_role in member.roles:
        await member.remove_roles(mute_role, reason="Unmute executed")
    await remove_tempmute(member.id)
    case_text = f"(Case #{case_id})" if case_id else "(Case #N/A)"
    await ctx.send(f"{member.mention} successfully unmuted. {case_text}")


@bot.command()
async def removetimeout(ctx, member: discord.Member):
    case_id = await log_action(ctx, "TimeoutRemoved", member, "Action executed", 0x00FF00)
    await member.edit(timed_out_until=None, reason="Timeout removed by moderator")
    await remove_timeout(member.id)
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
    except discord.Forbidden:
        await ctx.send("I don’t have permission to unban this user.")
        return
    except Exception:
        logger.exception("Unban failed")

    rec = await add_case_record("Unban", user.id, ctx.author.id, "Action executed")
    emb = create_case_embed("Unban", ctx.author, user, "Action executed", 0x00FF00, rec["case_id"])
    await safe_send_channel(MOD_LOG_CHANNEL_ID, emb)
    await send_dm(user, "Unban", "Action executed")
    case_text = f"(Case #{rec['case_id']})"
    await ctx.send(f"{user.mention} successfully unbanned. {case_text}")

# ---------------- TEMP PUNISHMENT SCHEDULERS (Postgres Async) ----------------

# TEMPBAN
async def schedule_unban_task(user_id: int, unban_ts: float):
    try:
        now_ts = datetime.utcnow().timestamp()
        sleep_time = max(0, unban_ts - now_ts)
        await asyncio.sleep(sleep_time)

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        user = await bot.fetch_user(user_id)
        if user:
            try:
                await guild.unban(user, reason="Temporary ban expired")
                async with db_pool.acquire() as conn:
                    await conn.execute("DELETE FROM tempbans WHERE user_id=$1", user_id)

                case_id = await log_action_manual("Unban", user, "Temporary ban expired", 0x00FF00)
                await safe_send_channel(MOD_LOG_CHANNEL_ID, f"{user.mention} automatically unbanned. (Case #{case_id})")
            except discord.NotFound:
                async with db_pool.acquire() as conn:
                    await conn.execute("DELETE FROM tempbans WHERE user_id=$1", user_id)
            except discord.Forbidden:
                logger.warning(f"Cannot unban user {user_id}, missing permissions.")
    except Exception:
        logger.exception(f"Failed unban scheduler for {user_id}")


# TEMPMUTE
async def schedule_unmute_task(member_id: int, unmute_ts: float):
    try:
        sleep_time = max(0, unmute_ts - datetime.utcnow().timestamp())
        await asyncio.sleep(sleep_time)

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        member = guild.get_member(member_id)
        if member:
            mute_role = discord.utils.get(guild.roles, name="Muted")
            if mute_role and mute_role in member.roles:
                await member.remove_roles(mute_role, reason="Temporary mute expired")

            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM tempmutes WHERE user_id=$1", member_id)

            case_id = await log_action_manual("Unmute", member, "Temporary mute expired", 0x00FF00)
            await safe_send_channel(MOD_LOG_CHANNEL_ID, f"{member.mention} automatically unmuted. (Case #{case_id})")
    except Exception:
        logger.exception(f"Failed unmute scheduler for {member_id}")


# TIMEOUT
async def schedule_timeout_task(member_id: int, timeout_ts: float):
    try:
        sleep_time = max(0, timeout_ts - datetime.utcnow().timestamp())
        await asyncio.sleep(sleep_time)

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        member = guild.get_member(member_id)
        if member:
            await member.edit(timed_out_until=None, reason="Temporary timeout expired")

            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM temptimeouts WHERE user_id=$1", member_id)

            case_id = await log_action_manual("TimeoutRemoved", member, "Temporary timeout expired", 0x00FF00)
            await safe_send_channel(MOD_LOG_CHANNEL_ID, f"{member.mention} timeout automatically removed. (Case #{case_id})")
    except Exception:
        logger.exception(f"Failed timeout scheduler for {member_id}")


# ---------------- RESTORE TASKS ----------------
async def restore_tempbans():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, unban_ts FROM tempbans")
    for user_id, unban_ts in rows:
        asyncio.create_task(schedule_unban_task(user_id, max(unban_ts, datetime.utcnow().timestamp())))

async def restore_tempmutes():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, unmute_ts FROM tempmutes")
    for user_id, unmute_ts in rows:
        asyncio.create_task(schedule_unmute_task(user_id, max(unmute_ts, datetime.utcnow().timestamp())))

async def restore_timeouts():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, untimeout_ts FROM temptimeouts")
    for user_id, timeout_ts in rows:
        asyncio.create_task(schedule_timeout_task(user_id, max(timeout_ts, datetime.utcnow().timestamp())))


# ---------------- ADD TASK FUNCTIONS ----------------
async def add_tempban(user_id: int, unban_ts: float):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tempbans(user_id, unban_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET unban_ts = EXCLUDED.unban_ts
        """, user_id, unban_ts)
    asyncio.create_task(schedule_unban_task(user_id, unban_ts))

async def add_tempmute(user_id: int, unmute_ts: float):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tempmutes(user_id, unmute_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET unmute_ts = EXCLUDED.unmute_ts
        """, user_id, unmute_ts)
    asyncio.create_task(schedule_unmute_task(user_id, unmute_ts))

async def add_timeout(user_id: int, timeout_ts: float):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO temptimeouts(user_id, untimeout_ts)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET untimeout_ts = EXCLUDED.untimeout_ts
        """, user_id, timeout_ts)
    asyncio.create_task(schedule_timeout_task(user_id, timeout_ts))

COOL_ROLE_ID = 1413810618359615488  # Only members with this role can use case commands

def has_cool_role(member: discord.Member):
    return member.get_role(COOL_ROLE_ID) is not None

# ---------------- CASE COMMANDS (DB VERSION) ----------------

@bot.command()
async def cases(ctx, member: discord.Member):
    """Show all case IDs for a user"""
    if not has_cool_role(ctx.author):
        await ctx.send("❌ You do not have permission to use this command.")
        return

    user_cases = await get_user_cases_db(member.id)  # fetch from DB
    if not user_cases:
        await ctx.send(f"No cases found for {member.mention}.")
        return

    lines = [f"{i+1}. Case #{c['case_id']}" for i, c in enumerate(user_cases)]
    emb = discord.Embed(
        title=f"Cases for {member}",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    await ctx.send(embed=emb)


@bot.command()
async def caseinfo(ctx, case_id: int):
    """Show detailed info for a single case"""
    if not has_cool_role(ctx.author):
        await ctx.send("❌ You do not have permission to use this command.")
        return

    case = await find_case_db(case_id)
    if not case:
        await ctx.send(f"No case found with ID {case_id}.")
        return

    guild = ctx.guild
    try:
        user = guild.get_member(case["user_id"]) or await bot.fetch_user(case["user_id"])
    except Exception:
        user = None
    try:
        mod = guild.get_member(case["moderator_id"]) or await bot.fetch_user(case["moderator_id"])
    except Exception:
        mod = None

    emb = create_case_embed(
        action=case["action"],
        moderator=mod or ctx.guild.me,
        user_obj=user or ctx.guild.me,
        reason=case["reason"],
        color_hex=discord.Color.orange(),
        case_id=case["case_id"],
        duration=case.get("duration")
    )
    await ctx.send(embed=emb)


@bot.command()
async def deletecase(ctx, case_id: int):
    """Delete a case from the DB (staff only)"""
    if not has_cool_role(ctx.author):
        await ctx.send("❌ You do not have permission to use this command.")
        return

    case = await find_case_db(case_id)
    if not case:
        await ctx.send(f"No case found with ID {case_id}.")
        return

    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM cases WHERE case_id=$1;", case_id)

    await ctx.send(f"✅ Case #{case_id} has been deleted successfully.")

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
from flask import Flask
from threading import Thread
import os
import discord
from discord.ext import commands
import logging
import asyncio
import traceback

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.getenv("PORT", 8080))  # Render sets PORT automatically
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

@bot.event
async def on_ready():
    try:
        logger.info(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

        # Restore from DB
        await restore_tempbans_from_db()
        await restore_tempmutes_from_db()
        await restore_timeouts_from_db()

        for cid in (MOD_LOG_CHANNEL_ID, LOG_CHANNEL_ID, WELCOME_CHANNEL_ID):
            ch = bot.get_channel(cid)
            logger.info(f"Channel {cid} resolves to: {ch}")

    except Exception:
        logger.exception("Unhandled exception in on_ready")
        traceback.print_exc()

# ---- actually start the bot ----
if __name__ == "__main__":
    bot.run(TOKEN)