import asyncio
import json
import math
import os

import discord
import httpx
from discord.ext import commands

from pony.orm import *

intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)
db = Database()

with open("config.json", "r") as f:
    config = json.loads(f.read())

hypixel_slovenija_server = config["discord_server_id"]
guilds = [hypixel_slovenija_server]

hypixel_api_key = os.environ["HYPIXEL_API"]
discord_token = os.environ["BOT_TOKEN"]
hypixel_slovenija_guild_id = config["hypixel_guild_id"]

member_role = config["member_role"]
guild_member_role = config["guild_member_role"]
vip_role = config["vip_role"]
vipp_role = config["vipp_role"]
mvp_role = config["mvp_role"]
mvpp_role = config["mvpp_role"]
mvppp_role = config["mvppp_role"]
veteran_role = config["veteran_role"]
professional_role = config["professional_role"]
nepreverjeni_role = config["nepreverjeni_role"]
admin_notification_channel = config["admin_notification_channel"]


class User(db.Entity):
    minecraft_id = Optional(str)
    minecraft_name = Optional(str)
    discord_id = Required(str)
    veteran = Required(bool)
    professional = Required(bool)


async def zamenjaj_ime(s: User):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://sessionserver.mojang.com/session/minecraft/profile/{s.minecraft_id}")
        if r.status_code != 200:
            raise Exception(f"{r.text} s statusno kodo {r.status_code}")
        s.minecraft_name = r.json()["name"]


async def hypixel_statistika(s: User):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.hypixel.net/player", headers={"API-Key": hypixel_api_key},
                             params={"uuid": s.minecraft_id})
        if r.status_code != 200:
            raise Exception(f"{r.text} s statusno kodo {r.status_code}")
        j = r.json()
        return j


async def hypixel_guild(s: User):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.hypixel.net/guild", headers={"API-Key": hypixel_api_key},
                             params={"player": s.minecraft_id})
        if r.status_code != 200:
            raise Exception(f"{r.text} s statusno kodo {r.status_code}")
        j = r.json()
        return j


async def nastavi_rank(j, discord_user: discord.Member):
    server = bot.get_guild(hypixel_slovenija_server)
    vip = server.get_role(vip_role)
    vipp = server.get_role(vipp_role)
    mvp = server.get_role(mvp_role)
    mvpp = server.get_role(mvpp_role)
    mvppp = server.get_role(mvppp_role)

    player = j["player"]
    monthly_rank = player.get("monthlyPackageRank")
    rank = player.get("newPackageRank")
    if rank == "VIP":
        await discord_user.add_roles(vip)
    elif rank == "VIP_PLUS":
        await discord_user.add_roles(vipp)
    elif rank == "MVP":
        await discord_user.add_roles(mvp)
    elif rank == "MVP_PLUS":
        await discord_user.add_roles(mvpp)

    # MVP++
    if monthly_rank == "SUPERSTAR":
        await discord_user.add_roles(mvppp)
    else:
        await discord_user.remove_roles(mvppp)

    # print(rank)


async def odstrani_role(discord_user: discord.Member):
    server = bot.get_guild(hypixel_slovenija_server)
    member = server.get_role(member_role)
    guild_member = server.get_role(guild_member_role)
    vip = server.get_role(vip_role)
    vipp = server.get_role(vipp_role)
    mvp = server.get_role(mvp_role)
    mvpp = server.get_role(mvpp_role)
    mvppp = server.get_role(mvppp_role)
    veteran = server.get_role(veteran_role)
    professional = server.get_role(professional_role)
    nepreverjeni = server.get_role(nepreverjeni_role)

    await discord_user.remove_roles(member, guild_member, vip, vipp, mvp, mvpp, mvppp, veteran, professional, nepreverjeni)


async def dodaj_nepreverjeni(discord_user: discord.Member):
    server = bot.get_guild(hypixel_slovenija_server)
    nepreverjeni = server.get_role(nepreverjeni_role)
    await discord_user.add_roles(nepreverjeni)


async def nastavi_nick(s: User, stats, discord_user: discord.Member) -> int:
    server = bot.get_guild(hypixel_slovenija_server)
    member = server.get_role(member_role)

    network_experience = stats["player"]["networkExp"]
    network_level = int((math.sqrt((2 * network_experience) + 30625) / 50) - 2.5)

    # print(network_level)

    await discord_user.edit(nick=f"{s.minecraft_name} [{network_level}]")
    await discord_user.add_roles(member)

    return network_level


async def nastavi_guild_role(guild, s: User, discord_user: discord.Member):
    server = bot.get_guild(hypixel_slovenija_server)
    guild_member = server.get_role(guild_member_role)
    c = server.get_channel(admin_notification_channel)

    if guild["_id"] != hypixel_slovenija_guild_id:
        s.professional = False
        s.veteran = False
        return

    for m in guild["members"]:
        if m["uuid"] != s.minecraft_id:
            continue

        await discord_user.add_roles(guild_member)

        if m["rank"] == "Member":
            total = 0
            for i in m["expHistory"].values():
                total += int(i)

            if total >= 100_000:
                await c.send(
                    content=f"Uporabnika {s.minecraft_name} sem posodobil iz Member -> Veteran. Prosimo spremenite "
                            f"rolo tudi na Hypixlu, da bo odražalo trenutno stanje. Uporabnik je zbral {total} guild "
                            f"experienca.")
                s.veteran = True

            break

        s.veteran = True

        if m["rank"] == "Veteran":
            break

        s.professional = True

        break


async def nastavi_veteran_professional(s: User, discord_user: discord.Member):
    server = bot.get_guild(hypixel_slovenija_server)
    veteran = server.get_role(veteran_role)
    professional = server.get_role(professional_role)

    if s.veteran:
        await discord_user.add_roles(veteran)
    if s.professional:
        await discord_user.add_roles(professional)


async def preveri_professional(s: User, player, network_level: int):
    server = bot.get_guild(hypixel_slovenija_server)
    c = server.get_channel(admin_notification_channel)

    if s.veteran and not s.professional:
        stats = player["stats"]
        achievements = player["achievements"]
        assign_professional = False
        if stats.get("Duels") is not None and stats["Duels"].get("wins") is not None:
            assign_professional = assign_professional or int(stats["Duels"].get("wins")) >= 1000
        if achievements.get("bedwars_level") is not None:
            assign_professional = assign_professional or int(achievements["bedwars_level"]) >= 100
        if achievements.get("skywars_you_re_a_star") is not None:
            assign_professional = assign_professional or int(achievements["skywars_you_re_a_star"]) >= 10
        assign_professional = assign_professional or network_level >= 100
        if assign_professional:
            s.professional = True
            await c.send(
                content=f"Uporabnika {s.minecraft_name} sem posodobil iz Veteran -> Professional. Prosimo spremenite "
                        f"rolo tudi na Hypixlu, da bo odražalo trenutno stanje.")


async def ime_v_uuid(ime: str, ctx: discord.ApplicationContext, db_user: User):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.mojang.com/users/profiles/minecraft/{ime}")
        if r.status_code != 200:
            await ctx.interaction.edit_original_response(
                content=f"Napaka ({r.text} s statusno kodo {r.status_code}). Ne najdem uporabnika s takim "
                        f"uporabniškim imenom.")
            return
        j = r.json()
        uid = j["id"]
        ime = j["name"]

        db_user.minecraft_id = uid
        db_user.minecraft_name = ime


async def zahtevek(ctx: discord.ApplicationContext, db_user: User, discord_user: discord.Member):
    j2 = await hypixel_statistika(db_user)
    await nastavi_rank(j2, discord_user)
    network_level = await nastavi_nick(db_user, j2, discord_user)

    j3 = await hypixel_guild(db_user)
    guild = j3.get("guild")
    if guild is None:
        await ctx.interaction.edit_original_response(content="Uspešno preveril uporabnika.")
        return

    await nastavi_guild_role(guild, db_user, discord_user)
    await preveri_professional(db_user, j2, network_level)
    await nastavi_veteran_professional(db_user, discord_user)


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}. Initializing sqlite3 database.")
    db.bind(provider='sqlite', filename='database.sqlite', create_db=True)
    db.generate_mapping(create_tables=True)
    print("Done initializing sqlite3 database.")


@bot.slash_command(guild_ids=guilds)
@commands.has_any_role("Officer", "Master", "Guild Master")
async def preveri(
        ctx: discord.ApplicationContext,
        discord_user: discord.Option(discord.Member, description="Discord uporabnik", required=True),
        ime: discord.Option(str, description="Ime Minecraft računa", required=True),
):
    await ctx.respond("Dodajam uporabnika ...")

    with db_session:
        try:
            s = select(p for p in User if p.discord_id == str(discord_user.id))[:]
            for i in s:
                i.delete()
        except Exception as e:
            print(f"Exception: {e}")
        db_user = User(minecraft_id="", minecraft_name="", discord_id=str(discord_user.id), veteran=False,
                       professional=False)

        await odstrani_role(discord_user)

        try:
            await ime_v_uuid(ime, ctx, db_user)
            await zahtevek(ctx, db_user, discord_user)
        except Exception as e:
            await ctx.interaction.edit_original_response(content=f"Težava pri preverjanju uporabnika: {e}")
            await odstrani_role(discord_user)
            await dodaj_nepreverjeni(discord_user)

    await ctx.interaction.edit_original_response(content="Uspešno dodal uporabnika.")


@bot.slash_command(guild_ids=guilds)
async def posodobi(ctx: discord.ApplicationContext):
    await ctx.respond("Posodabljam uporabnika ...")

    server = bot.get_guild(hypixel_slovenija_server)
    c = server.get_channel(admin_notification_channel)

    with db_session:
        discord_user = ctx.user

        try:
            db_user = select(p for p in User if p.discord_id == str(discord_user.id))[:][0]
        except Exception as e:
            await ctx.interaction.edit_original_response(
                content=f"Ne najdem uporabnika v podatkovni bazi ({e}). Odpreverjam uporabnika ...")
            await odstrani_role(discord_user)
            await dodaj_nepreverjeni(discord_user)
            await c.send(content=f"Uporabnik {ctx.user.name} je bil odpreverjen.")
            return

        await zamenjaj_ime(db_user)
        await zahtevek(ctx, db_user, discord_user)

    await ctx.interaction.edit_original_response(content="Uspešno posodobil uporabnikov profil.")


async def migriraj(ctx: discord.ApplicationContext):
    await ctx.respond("Začenjam veliko migracijo računov ...")

    server = bot.get_guild(hypixel_slovenija_server)
    c = server.get_channel(admin_notification_channel)

    with db_session:
        try:
            async for discord_user in server.fetch_members(limit=None):
                try:
                    s = select(p for p in User if p.discord_id == str(discord_user.id))[:]
                    if len(s) > 0:
                        await c.send(
                            f"Uporabnik <@{discord_user.id}> je bil preskočen zaradi tega, ker je že vnesen v sistem.")
                        continue
                except Exception as e:
                    print(f"Exception: {e}")

                member = discord_user.get_role(member_role)
                if member is None:
                    await c.send(
                        f"Uporabnik <@{discord_user.id}> je bil preskočen zaradi nepreverjenosti na prejšnjem sistemu.")
                    continue

                try:
                    nick = discord_user.nick.split(" ")
                    ime = nick[0]
                except Exception as e:
                    await c.send(
                        f"Uporabnik <@{discord_user.id}> je bil preskočen zaradi neveljavne sestave vzdevka ({e}).")
                    continue

                db_user = User(minecraft_id="", minecraft_name="", discord_id=str(discord_user.id), veteran=False,
                               professional=False)

                try:
                    await odstrani_role(discord_user)
                except Exception as e:
                    await c.send(
                        f"Uporabnik <@{discord_user.id}> je bil preskočen zaradi težave z odstranjevanjem rol ({e}).")
                    db_user.delete()
                    continue

                try:
                    await ime_v_uuid(ime, ctx, db_user)
                except Exception as e:
                    await c.send(
                        f"Uporabnik <@{discord_user.id}> je bil preskočen zaradi težave s pretvarjanjem imena v UUID ({e}).")
                    db_user.delete()
                    continue

                try:
                    await zahtevek(ctx, db_user, discord_user)
                except Exception as e:
                    await c.send(
                        f"Uporabnik <@{discord_user.id}> je bil preskočen generične težave v funkciji zahtevek ({e}).")
                    db_user.delete()
                    continue

                await c.send(f"Uporabnik <@{discord_user.id}> je bil uspešno migriran na nov sistem.")

                commit()
        except Exception as e:
            print(f"Discord fail: {e}")
            return

    await c.send("Migracija računov končana.")


@bot.slash_command(guild_ids=guilds)
@commands.has_permissions(administrator=True)
async def migriraj_racune(ctx: discord.ApplicationContext):
    asyncio.create_task(migriraj(ctx))


bot.run(discord_token)
