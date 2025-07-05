import discord
import aiohttp
import asyncio
import json
import hashlib
import os
from datetime import datetime, timezone
from discord.ext import tasks, commands
from collections import defaultdict

# Load token from token.json
with open("token.json", "r") as f:
    data = json.load(f)
    TOKEN = data["token"]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

guilds = {}

alert_hours = 24
cooldown_time = 60  # in seconds
clear_time = 60  # seconds

# Helper function to get current UTC ISO format time
def iso_now():
    return datetime.now(timezone.utc).isoformat()
	
last_info_hash = None  # global variable to track last info hash

def log_action(guild_name, action):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] [{guild_name}] {action}")

def compute_info_hash(info):
    # Serialize relevant info to JSON string and hash it
    # Only include titles and start/end dates to detect meaningful changes
    summary = {
        "current": [
            {"title": g["title"], "start": g["start"].isoformat(), "end": g["end"].isoformat()}
            for g in info.get("current", [])
        ],
        "upcoming": [
            {"title": g["title"], "start": g["start"].isoformat(), "end": g["end"].isoformat()}
            for g in info.get("upcoming", [])
        ]
    }
    summary_str = json.dumps(summary, sort_keys=True)
    return hashlib.sha256(summary_str.encode()).hexdigest()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    guilds_setup()
    poll_date.start()  # start background task

def guilds_setup():
    print("Parsing bot guild list")
    for guild in bot.guilds:
        if guild.id not in guilds:
            guilds[guild.id] = {
                "setChannel": None,
                "setGuild": guild.name,
                "messagesToPin": [None, None, None],
                "alerted": False,
                "operationRunning": False,
                "cooldown": 0,
                "onCooldown": False,
                "clearSystemMessages": False,
                "systemMessageClearTimer": 0,
            }
            print(f" -> Found server {guild.name}")
			
def summarize_info(info):
    def summarize_games(games):
        return sorted([
            (game["title"], game["start"].strftime("%Y-%m-%d"), game["end"].strftime("%Y-%m-%d"))
            for game in games
        ])
    if not info:
        return None
    return {
        "current": summarize_games(info.get("current", [])),
        "upcoming": summarize_games(info.get("upcoming", [])),
    }

async def get_info():
    url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=FI&allowCountries=FI"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"Failed to fetch data, status code: {resp.status}")
                    return

                data = await resp.json()
    except Exception as e:
        print(f"Exception fetching data: {e}")
        return

    elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
    if not elements:
        print("No game elements found.")
        return

    current_free = []
    upcoming_free = []

    now = datetime.now(timezone.utc)

    for el in elements:
        # Skip non-game items
        categories = el.get("categories", [])
        if not any(cat.get("path") == "games" for cat in categories):
            continue

        title = el.get("title", "Unknown Title")
        game_id = el.get("id", None)

        # Extract store URL if available (use urlSlug)
        url_slug = el.get("urlSlug")
        store_url = f"https://www.epicgames.com/store/en-US/p/{url_slug}" if url_slug else None

        # Find main image (OfferImageWide) and thumbnail URL in one pass
        main_image_url = None
        thumbnail_url = None
        key_images = el.get("keyImages", [])

        for img in key_images:
            if img.get("type") == "OfferImageWide" and not main_image_url:
                main_image_url = img.get("url")
            elif img.get("type") == "Thumbnail" and not thumbnail_url:
                thumbnail_url = img.get("url")

        # Fallback if no thumbnail found
        if not thumbnail_url and key_images:
            thumbnail_url = key_images[0].get("url", "")

        promotions = el.get("promotions") or {}

        # Current promotional offers
        promo_offers = promotions.get("promotionalOffers") or []
        for promo_block in promo_offers:
            for offer in promo_block.get("promotionalOffers", []):
                start = datetime.fromisoformat(offer["startDate"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(offer["endDate"].replace("Z", "+00:00"))
                if start <= now <= end:
                    current_free.append({
                        "id": game_id,
                        "title": title,
                        "thumbnail_url": thumbnail_url,
                        "main_image_url": main_image_url,
                        "store_url": store_url,
                        "start": start,
                        "end": end
                    })

        # Upcoming promotional offers
        upcoming_promos = promotions.get("upcomingPromotionalOffers") or []
        for promo_block in upcoming_promos:
            for offer in promo_block.get("promotionalOffers", []):
                start = datetime.fromisoformat(offer["startDate"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(offer["endDate"].replace("Z", "+00:00"))
                upcoming_free.append({
                    "id": game_id,
                    "title": title,
                    "thumbnail_url": thumbnail_url,
                    "main_image_url": main_image_url,
                    "store_url": store_url,
                    "start": start,
                    "end": end
                })

    # Remove upcoming games that are currently free
    current_titles = {game["title"] for game in current_free}
    filtered_upcoming = [game for game in upcoming_free if game["title"] not in current_titles]

    # Group upcoming games by title with earliest start and latest end
    grouped_upcoming = defaultdict(lambda: {
        "start": None,
        "end": None,
        "thumbnail_url": None,
        "main_image_url": None,
        "store_url": None,
        "id": None
    })

    for game in filtered_upcoming:
        title = game["title"]
        start = game["start"]
        end = game["end"]
        thumbnail_url = game["thumbnail_url"]
        main_image_url = game["main_image_url"]
        store_url = game["store_url"]
        game_id = game["id"]

        if (grouped_upcoming[title]["start"] is None) or (start < grouped_upcoming[title]["start"]):
            grouped_upcoming[title]["start"] = start
        if (grouped_upcoming[title]["end"] is None) or (end > grouped_upcoming[title]["end"]):
            grouped_upcoming[title]["end"] = end
        if not grouped_upcoming[title]["thumbnail_url"]:
            grouped_upcoming[title]["thumbnail_url"] = thumbnail_url
        if not grouped_upcoming[title]["main_image_url"]:
            grouped_upcoming[title]["main_image_url"] = main_image_url
        if not grouped_upcoming[title]["store_url"]:
            grouped_upcoming[title]["store_url"] = store_url
        if not grouped_upcoming[title]["id"]:
            grouped_upcoming[title]["id"] = game_id

    return {
        "current": current_free,
        "upcoming": [
            {"title": title, **details}
            for title, details in grouped_upcoming.items()
        ],
    }


async def send_info(info, channel, guild_id):
    if not info or (not info.get("current") and not info.get("upcoming")):
        await channel.send("No free games found at the moment.")
        log_action(channel.guild.name, "No free games found, message sent.")
        return

    new_current = info.get("current", [])
    new_upcoming = info.get("upcoming", [])

    def simplified_games(games):
        return [
            {
                "title": g["title"],
                "start": g["start"].isoformat(),
                "end": g["end"].isoformat(),
                "store_url": g.get("store_url"),
            }
            for g in games
        ]

    last_info = guilds[guild_id].get("last_info", {})
    if (
        last_info.get("current") == simplified_games(new_current)
        and last_info.get("upcoming") == simplified_games(new_upcoming)
    ):
        log_action(channel.guild.name, "Free games info unchanged, skipping sending.")
        return

    guilds[guild_id]["last_info"] = {
        "current": simplified_games(new_current),
        "upcoming": simplified_games(new_upcoming),
    }

    # Unpin old bot-pinned messages
    try:
        pinned = await channel.pins()
        for msg in pinned:
            if msg.author == channel.guild.me:
                await msg.unpin()
        log_action(channel.guild.name, "Unpinned old bot messages.")
    except Exception as e:
        print(f"Error unpinning old messages: {e}")

    messages_to_pin = []

    # Send CURRENT free games
    if new_current:
        header_msg = await channel.send("🎉 **Current Free Games:**")
        messages_to_pin.append(header_msg)
        for game in new_current:
            start_str = game["start"].strftime("%Y-%m-%d")
            end_str = game["end"].strftime("%Y-%m-%d")
            embed = discord.Embed(
                title=game["title"],
                url=game.get("store_url", None),
                description=f"**From:** {start_str}\n**Until:** {end_str}",
                color=discord.Color.green(),
            )
            if game.get("main_image_url"):
                embed.set_image(url=game["main_image_url"])
            elif game.get("thumbnail_url"):
                embed.set_thumbnail(url=game["thumbnail_url"])

            msg = await channel.send(embed=embed)
            messages_to_pin.append(msg)

    # Send UPCOMING free games
    if new_upcoming:
        header_msg = await channel.send("⏳ **Upcoming Free Games:**")
        messages_to_pin.append(header_msg)
        for game in new_upcoming:
            start_str = game["start"].strftime("%Y-%m-%d")
            end_str = game["end"].strftime("%Y-%m-%d")
            embed = discord.Embed(
                title=game["title"],
                url=game.get("store_url", None),
                description=f"**From:** {start_str}\n**Until:** {end_str}",
                color=discord.Color.gold(),
            )
            if game.get("main_image_url"):
                embed.set_image(url=game["main_image_url"])
            elif game.get("thumbnail_url"):
                embed.set_thumbnail(url=game["thumbnail_url"])

            msg = await channel.send(embed=embed)
            messages_to_pin.append(msg)

    # Pin messages in reverse order for chronological pinned list
    for msg in reversed(messages_to_pin):
        try:
            await msg.pin(reason="Updating free games info")
            log_action(channel.guild.name, f"Pinned message ID {msg.id}")
        except Exception as e:
            print(f"Failed to pin message: {e}")

    # Delete the system "pinned a message" notifications
    try:
        async for message in channel.history(limit=50):
            if (
                message.type == discord.MessageType.pins_add
                and message.author == channel.guild.me
            ):
                await message.delete()
                log_action(channel.guild.name, f"Deleted pin notification message ID {message.id}")
    except Exception as e:
        print(f"Failed to delete pin notification messages: {e}")

    log_action(channel.guild.name, "Completed sending and pinning free games info.")


async def delete_pin_notification(channel):
    async for msg in channel.history(limit=10):
        if msg.type == discord.MessageType.pins_add:
            try:
                await msg.delete()
            except Exception:
                pass

async def clear_bot_pins(channel):
    pinned_messages = await channel.pins()
    for msg in pinned_messages:
        if msg.author == channel.guild.me:  # Only unpin messages sent by your bot
            try:
                await msg.unpin()
            except Exception as e:
                print(f"Failed to unpin message: {e}")

@bot.event
async def on_guild_join(guild):
    print(f"New guild joined: {guild.name}")
    guilds_setup()


@bot.command(name="set")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    guild_id = ctx.guild.id

    # Initialize full guild dict if missing for consistent structure
    if guild_id not in guilds:
        guilds[guild_id] = {
            "setChannel": None,
            "setGuild": ctx.guild.name,
            "messagesToPin": [],
            "alerted": False,
            "operationRunning": False,
            "cooldown": 0,
            "onCooldown": False,
            "clearSystemMessages": False,
            "systemMessageClearTimer": 0,
        }

    guilds[guild_id]["setChannel"] = ctx.channel.id
    await ctx.send(f"Channel set to {ctx.channel.mention}, initiating")

    # Clear all pins created by the bot in this channel before sending new info
    await clear_bot_pins(ctx.channel)

    # Fetch the free games info
    info = await get_info()

    # Send new info and pin the messages
    await send_info(info, ctx.channel, guild_id)


@tasks.loop(seconds=cooldown_time)
async def poll_date():
    now = datetime.now(timezone.utc)

    for guild_id, guild_data in guilds.items():
        if not guild_data["setChannel"]:
            continue

        channel = bot.get_channel(guild_data["setChannel"])
        if channel is None:
            continue

        if guild_data["onCooldown"]:
            # Cooldown active, decrease counter
            guild_data["cooldown"] -= cooldown_time
            if guild_data["cooldown"] <= 0:
                guild_data["onCooldown"] = False
            continue

        # Calculate hours until switch moment (hardcoded switch at 5 AM UTC)
        switch_hour = 5
        switch_time = now.replace(hour=switch_hour, minute=0, second=0, microsecond=0)
        if now.hour < switch_hour:
            # If before switch hour, switch time is today at 5 AM
            pass
        else:
            # If after or equal to switch hour, next switch is tomorrow 5 AM
            switch_time = switch_time.replace(day=now.day + 1)

        time_until_switch = (switch_time - now).total_seconds() / 3600

        # If within alert window before switch, send alert
        if alert_hours >= time_until_switch > 0 and not guild_data["alerted"]:
            info = await get_info()
            if info:
                await send_info(info, channel, guild_id)
                guild_data["alerted"] = True
                guild_data["onCooldown"] = True
                guild_data["cooldown"] = cooldown_time

        # Reset alerted flag after switch time passed
        if time_until_switch <= 0:
            guild_data["alerted"] = False


bot.run(TOKEN)
