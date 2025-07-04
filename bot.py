
import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone
from discord.ext import tasks, commands

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

img_dir = "./img/"
if not os.path.exists(img_dir):
    os.makedirs(img_dir)

# For simplicity, placeholders for game info
game_titles = ["", ""]
game_urls = ["", ""]
switch_date = None
switch_moment = ""

# Helper function to get current UTC ISO format time
def iso_now():
    return datetime.now(timezone.utc).isoformat()

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

# Fetch info from Epic Games - simplified placeholder version
async def get_info():
    global game_titles, game_urls, switch_date, switch_moment
    url = "https://graphql.epicgames.com/graphql"
    query = '''
    query promotionsQuery($namespace: String!, $country: String!) {
      Catalog {
        catalogOffers(namespace: $namespace, params: {category: "freegames", country: $country, sortBy: "effectiveDate", sortDir: "asc"}) {
          elements {
            title
            keyImages {
              type
              url
            }
            promotions {
              promotionalOffers {
                promotionalOffers {
                  startDate
                  endDate
                }
              }
              upcomingPromotionalOffers {
                promotionalOffers {
                  startDate
                  endDate
                }
              }
            }
          }
        }
      }
    }
    '''
    variables = {"namespace": "epic", "country": "US"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"query": query, "variables": variables}) as resp:
            if resp.status != 200:
                print(f"Error fetching info: {resp.status}")
                return
            data = await resp.json()

            elements = data["data"]["Catalog"]["catalogOffers"]["elements"]
            # Titles
            new_title_0 = elements[0]["title"]
            if new_title_0 != game_titles[0]:
                # Clear images if title changed (simplified)
                for f in os.listdir(img_dir):
                    if f != ".gitkeep":
                        os.remove(os.path.join(img_dir, f))
            game_titles[0] = new_title_0
            game_titles[1] = elements[1]["title"] if len(elements) > 1 else ""

            # URLs (look for ComingSoon type)
            def get_url(index):
                for img in elements[index]["keyImages"]:
                    if img["type"] == "ComingSoon":
                        return img["url"]
                return ""

            game_urls[0] = get_url(0)
            game_urls[1] = get_url(1)

            # Switch date from upcoming promotional offers
            try:
                switch_date = elements[1]["promotions"]["upcomingPromotionalOffers"][0]["promotionalOffers"][0]["startDate"]
                dt = datetime.fromisoformat(switch_date.replace('Z', '+00:00'))
                delta = dt - datetime.now(timezone.utc)
                hours_left = int(delta.total_seconds() // 3600)
                switch_moment = f"in {hours_left} hours"
            except Exception as e:
                print(f"Error parsing switch date: {e}")
                switch_date = None
                switch_moment = ""

async def send_info(guild_id, channel):
    if guilds[guild_id]["operationRunning"]:
        return

    guilds[guild_id]["operationRunning"] = True
    print(f"Task started for server: {guilds[guild_id]['setGuild']} - #{guilds[guild_id]['setChannel']}")

    await get_info()

    # Send messages with current and upcoming offers
    try:
        msg1 = await channel.send(f"The current free game on Epic Store is: **{game_titles[0]}**")
        msg2 = await channel.send(f"The next free game is: **{game_titles[1]}**")
        msg3 = await channel.send(f"The next game will be available **{switch_moment}** ({switch_date[:10] if switch_date else 'N/A'})")

        guilds[guild_id]["messagesToPin"] = [msg1, msg2, msg3]

        for msg in guilds[guild_id]["messagesToPin"]:
            if msg:
                await msg.pin()
    except Exception as e:
        print(f"Error sending info messages: {e}")

    guilds[guild_id]["operationRunning"] = False

@bot.event
async def on_guild_join(guild):
    print(f"New guild joined: {guild.name}")
    guilds_setup()

@bot.command(name="set")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    guild_id = ctx.guild.id
    guilds[guild_id]["setChannel"] = ctx.channel.name
    await ctx.send(f"Operating channel set to: **#{ctx.channel.name}**")
    await send_info(guild_id, ctx.channel)

@tasks.loop(seconds=60)
async def poll_date():
    # Check if alert is needed
    now = datetime.now(timezone.utc)
    if switch_date:
        dt = datetime.fromisoformat(switch_date.replace('Z', '+00:00'))
        delta = dt - now
        if delta.total_seconds() < alert_hours * 3600:
            for guild_id in guilds:
                if not guilds[guild_id]["alerted"] and guilds[guild_id]["setChannel"]:
                    guild = bot.get_guild(guild_id)
                    if guild:
                        channel = discord.utils.get(guild.text_channels, name=guilds[guild_id]["setChannel"])
                        if channel:
                            await channel.send(f"ALERT! Game selection will change in {int(delta.total_seconds() // 3600)} hours")
                            guilds[guild_id]["alerted"] = True

bot.run(TOKEN)
