import os
import logging
from datetime import datetime
import discord
from discord.ext import commands
from flask import Flask
import threading
import asyncio

# ---------------- CONFIG ----------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1411582058282876972
WELCOME_CHANNEL_ID = 1411583450112069672
LOG_CHANNEL_ID = 1412769718162423843

# Roles
MEMBER_ROLE_ID = 1413518414697463818
MALE_ROLE_ID = 1414269022945677353
FEMALE_ROLE_ID = 1414269196543721502
UNVERIFIED_ROLE_ID = 1425815375714455622
DOJ_ROLE_ID = 1413810618359615488
OWNER_ID = int(os.getenv("OWNER_ID"))

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s: %(message)s"
)

# ---------------- FLASK SETUP ----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title="🌿 Welcome!",
        description=(
            f"Welcome to **Ahlus-Sunnah Wal-Jamā'ah┃ٱلسُّنَّة**, {member.mention}!\n\n"
            f"👤 **User:** {member}\n"
            f"🆔 **ID:** {member.id}\n"
            f"📊 **Members Now:** {member.guild.member_count}"
        ),
        color=0x00ff00,  # Green
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title="🍃 Member Left",
        description=(
            f"{member.mention} has left **Ahlus-Sunnah Wal-Jamā'ah┃ٱلسُّنَّة**.\n\n"
            f"👤 **User:** {member}\n"
            f"🆔 **ID:** {member.id}\n"
            f"📊 **Members Now:** {member.guild.member_count}"
        ),
        color=0xff6666,  # Peaceful red
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(
        title="✏️ Message Edited",
        color=0xffcc00,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="User", value=f"{before.author.mention}", inline=False)
    embed.add_field(name="Channel", value=f"{before.channel.mention}", inline=False)
    embed.add_field(name="Before", value=before.content[:1000], inline=False)
    embed.add_field(name="After", value=after.content[:1000], inline=False)
    await channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(
        title="🗑️ Message Deleted",
        color=0xff3333,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="User", value=f"{message.author.mention}", inline=False)
    embed.add_field(name="Channel", value=f"{message.channel.mention}", inline=False)
    embed.add_field(name="Content", value=message.content[:1000], inline=False)
    await channel.send(embed=embed)

# ---------------- COMMANDS ----------------

# !say <server_id> <channel_id> #<hex_color> [message]
@bot.command()
async def say(ctx, guild_id: int, channel_id: int, color_hex: str, *, message: str):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ You do not have permission to use this command.")
        return
    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            await ctx.send("❌ Guild not found.")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Channel not found.")
            return

        color_hex = color_hex.lstrip("#")
        color_value = int(color_hex, 16)

        embed = discord.Embed(
            description=message,
            color=color_value,
            timestamp=datetime.utcnow()
        )
        await channel.send(embed=embed)
        await ctx.send(f"✅ Message sent to {channel.mention} in **{guild.name}**.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# Verification commands
@bot.command()
@commands.has_role(DOJ_ROLE_ID)
async def vm(ctx, member: discord.Member):
    member_role = ctx.guild.get_role(MEMBER_ROLE_ID)
    male_role = ctx.guild.get_role(MALE_ROLE_ID)
    unverified_role = ctx.guild.get_role(UNVERIFIED_ROLE_ID)

    if not all([member_role, male_role, unverified_role]):
        await ctx.send("❌ One or more roles are missing.")
        return

    await member.add_roles(member_role, male_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"{member.mention} successfully verified.")

@bot.command()
@commands.has_role(DOJ_ROLE_ID)
async def vf(ctx, member: discord.Member):
    member_role = ctx.guild.get_role(MEMBER_ROLE_ID)
    female_role = ctx.guild.get_role(FEMALE_ROLE_ID)
    unverified_role = ctx.guild.get_role(UNVERIFIED_ROLE_ID)

    if not all([member_role, female_role, unverified_role]):
        await ctx.send("❌ One or more roles are missing.")
        return

    await member.add_roles(member_role, female_role)
    await member.remove_roles(unverified_role)
    await ctx.send(f"{member.mention} successfully verified.")

# Error handling
@vm.error
@vf.error
async def verify_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ You do not have permission to use this command.")
    else:
        raise error

# ---------------- RUN BOTH ----------------
def start_bot():
    asyncio.run(bot.start(TOKEN))

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    start_bot()