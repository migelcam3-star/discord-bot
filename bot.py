import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import time
import re
import json
import asyncio
from collections import defaultdict
from datetime import timedelta, datetime, timezone
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================== CONFIG ========================
OWNER_ID = 1464526568293531763
TICKET_CHANNEL_ID = 1534939950061977661
PING_ROLE_ID = 1541525446959702146

SECURITY_LOG = {
    1534640056592105652: 1536339631753273404,  # Nexora
    1535315054898057338: 1552260303155105812,  # Полиция
    1535320463008600197: 1561703963903139942,  # ОПГ
}

XP_LOG = {
    1535315054898057338: 1552261343413936181,
    1535320463008600197: 1561703963903139942,
}

XP_ENABLED = set(XP_LOG.keys())
XP_MAX_SINGLE = 1_000_000

XP_ROLE_LIMITS = {
    1535315054898057338: {
        1562098410901999636: 1500,
        1562098805330149488: 5000,
        1562099103163359312: 15000,
    },
    1535320463008600197: {
        1558402556659630180: 15000,
    },
}

STAFF_ROLES = [
    1540009967040602232, 1534841235167117352, 1549116304659710115,
    1541494617290309793, 1550202959898353836, 1550202161575624885,
    1536095886793252874,
]

PERM_BAN_IDS = {
    953962723568386049, 1474709890743144448, 1416328122651119749,
    1261075830117892150, 1446108507505037425, 1284485012158283790,
    1555253548646670428, 1467173693917499405, 1549017207084949554,
}

WHITELIST_BOTS = {310848622642069504}

BANNED_WORDS = ["ленвилль", "смелдар", "orbix studio"]
NSFW_WORDS = [
    "хуй", "хуя", "хуе", "пизд", "ебан", "ебат", "ебл", "бляд", "сука",
    "мудил", "дроч", "член", "вагин", "секс", "порн", "fuck", "shit",
    "bitch", "cock", "dick", "pussy",
]
EVERYONE_RE = re.compile(r"@(everyone|here)", re.I)
SUSPICIOUS_BOT_PATTERNS = [
    r"crash", r"crasher", r"nuker", r"nuke", r"raider", r"raid",
    r"destroyer", r"wizz", r"token", r"selfbot", r"massban",
    r"server.?nuke", r"raidbot", r"spam.?bot",
]

CHANNEL_DELETE_LIMIT, CHANNEL_DELETE_WINDOW = 2, 1
ROLE_DELETE_LIMIT, ROLE_DELETE_WINDOW = 3, 12
MASS_BAN_LIMIT, MASS_BAN_WINDOW = 3, 15
SPAM_LIMIT, SPAM_WINDOW, SPAM_MUTE_MIN = 8, 6, 10
WEBHOOK_EVERYONE_LIMIT, WEBHOOK_WINDOW = 2, 1
XP_FILE = "xp_data.json"
# ========================================================

channel_deletes = defaultdict(list)
role_deletes = defaultdict(list)
mass_bans = defaultdict(list)
msg_spam = defaultdict(list)
webhook_hits = defaultdict(list)
_xp_lock = asyncio.Lock()

def load_xp():
    try:
        with open(XP_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {int(g): {int(u): int(v) for u, v in users.items()} for g, users in raw.items()}
    except Exception:
        return {}

xp_data = load_xp()

async def save_xp_async():
    async with _xp_lock:
        data = {str(g): {str(u): v for u, v in users.items()} for g, users in xp_data.items()}
        try:
            await asyncio.to_thread(_write_xp, data)
        except Exception as e:
            print(f"xp save error: {e}")

def _write_xp(data):
    with open(XP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def is_owner(m):
    return m is not None and m.id == OWNER_ID

def is_staff(m):
    if m is None:
        return False
    if m.id == OWNER_ID:
        return True
    return any(r.id in STAFF_ROLES for r in getattr(m, "roles", []))

def ticket_roles_ok(guild):
    if guild is None:
        return False
    if guild.get_role(PING_ROLE_ID) is None:
        return False
    return any(guild.get_role(rid) is not None for rid in STAFF_ROLES)

async def blog(guild, text, color=0xED4245):
    if guild is None:
        return
    cid = SECURITY_LOG.get(guild.id)
    if not cid:
        return
    emb = discord.Embed(description=text, color=color, timestamp=datetime.now(timezone.utc))
    emb.set_footer(text=f"Nexora Security • {guild.name}")
    try:
        ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
        await ch.send(embed=emb)
    except Exception:
        pass

async def xp_log(guild, embed: discord.Embed):
    cid = XP_LOG.get(guild.id)
    if not cid:
        return
    try:
        ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
        await ch.send(embed=embed)
    except Exception:
        pass

def get_xp(guild_id, user_id):
    return xp_data.get(guild_id, {}).get(user_id, 0)

async def set_xp(guild_id, user_id, value):
    xp_data.setdefault(guild_id, {})[user_id] = max(0, int(value))
    await save_xp_async()

def max_xp_allowed(member: discord.Member) -> int:
    if member.id == OWNER_ID:
        return XP_MAX_SINGLE
    limits = XP_ROLE_LIMITS.get(member.guild.id)
    if not limits:
        return 0
    limit = 0
    for rid, lim in limits.items():
        if any(r.id == rid for r in member.roles):
            limit = max(limit, lim)
    return limit

async def perm_ban(guild, user_id, reason="PERM BAN list"):
    try:
        user = await bot.fetch_user(user_id)
        await guild.ban(user, reason=reason, delete_message_seconds=0)
        await blog(guild, f"⛔ PERM BAN `{user_id}` — {reason}")
    except Exception as e:
        await blog(guild, f"❌ perm ban fail `{user_id}`: {e}")

async def get_audit_member(guild, action, target_id):
    try:
        async for e in guild.audit_logs(limit=5, action=action):
            if e.target and e.target.id == target_id:
                return guild.get_member(e.user.id)
    except Exception:
        pass
    return None

def suspicious_bot(member):
    if member.id == bot.user.id or member.id in WHITELIST_BOTS:
        return False, ""
    name = f"{member.name} {member.display_name}".lower()
    for p in SUSPICIOUS_BOT_PATTERNS:
        if re.search(p, name, re.I):
            return True, f"name: {p}"
    created = member.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created).days
    if age < 7:
        return True, f"account < 7 days ({age})"
    return True, "not in whitelist"

@bot.event
async def on_ready():
    print(f"Nexora {bot.user} online!")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🛡️ Nexora Studio")
    )
    bot.add_view(TicketView())
    bot.add_view(TicketControlView())

@bot.event
async def on_guild_remove(guild):
    await blog(guild, f"⚠️ Bot removed from **{guild.name}** (`{guild.id}`)", 0xFEE75C)

@bot.event
async def on_member_join(member):
    if member.id in PERM_BAN_IDS:
        await perm_ban(member.guild, member.id, "PERM BAN (join)")
        return
    if member.bot:
        adder = None
        try:
            async for e in member.guild.audit_logs(limit=4, action=discord.AuditLogAction.bot_add):
                if e.target and e.target.id == member.id:
                    adder = member.guild.get_member(e.user.id)
                    break
        except Exception:
            pass
        bad, why = suspicious_bot(member)
        await blog(
            member.guild,
            f"🤖 Bot **{member}** (`{member.id}`)\nAdded by: {adder}\nStatus: {why if bad else 'OK (whitelist)'}",
            0xED4245 if bad else 0x57F287,
        )
        if bad:
            try:
                await member.kick(reason=f"Nexora: {why}")
                await blog(member.guild, f"👢 Kicked bot **{member}** — {why}")
            except Exception as e:
                await blog(member.guild, f"❌ Kick bot failed: {e}")
            if adder and adder.id not in (OWNER_ID, bot.user.id):
                try:
                    await adder.ban(reason=f"added dangerous bot {member}", delete_message_seconds=0)
                    await blog(member.guild, f"⛔ Banned {adder.mention} — dangerous bot")
                except Exception as e:
                    await blog(member.guild, f"❌ Ban adder failed: {e}")
        return
    try:
        emb = discord.Embed(
            title="👋 Добро пожаловать в Nexora Studio!",
            description=(
                "💫 Здесь ты можешь найти новых друзей, создать свою фракцию или клан "
                "и стать частью нашего комьюнити.\n\n"
                "📈 С каждым днём мы растём и становимся всё больше, "
                "и именно ты можешь стать частью нашей истории!\n\n"
                "<:emoji_25:1561092761489514717> Рады видеть тебя среди нас!"
            ),
            color=0x5865F2,
        )
        emb.set_footer(text=f"Nexora Studio • {member.guild.name}")
        await member.send(embed=emb)
    except Exception:
        pass

@bot.event
async def on_member_unban(guild, user):
    if user.id in PERM_BAN_IDS:
        await asyncio.sleep(0.4)
        await perm_ban(guild, user.id, "PERM BAN (re-ban)")

@bot.event
async def on_guild_channel_delete(channel):
    m = await get_audit_member(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    if m is None or m.id in (OWNER_ID, bot.user.id):
        return
    if m.bot:
        try:
            await m.kick(reason="bot deletes channels")
            await blog(channel.guild, f"👢 Bot {m.mention} kicked — channel delete")
        except Exception:
            pass
        return
    now = time.time()
    channel_deletes[m.id] = [t for t in channel_deletes[m.id] if now - t < CHANNEL_DELETE_WINDOW]
    channel_deletes[m.id].append(now)
    await blog(channel.guild, f"🗑️ Channel **#{channel.name}** deleted — {m.mention}")
    if len(channel_deletes[m.id]) >= CHANNEL_DELETE_LIMIT:
        try:
            await m.ban(reason="mass channel delete", delete_message_seconds=0)
            await blog(channel.guild, f"⛔ Banned {m.mention} — mass channel delete")
        except Exception:
            pass

@bot.event
async def on_guild_role_delete(role):
    m = await get_audit_member(role.guild, discord.AuditLogAction.role_delete, role.id)
    if m is None or m.id in (OWNER_ID, bot.user.id):
        return
    if m.bot:
        try:
            await m.kick(reason="bot deletes roles")
        except Exception:
            pass
        return
    now = time.time()
    role_deletes[m.id] = [t for t in role_deletes[m.id] if now - t < ROLE_DELETE_WINDOW]
    role_deletes[m.id].append(now)
    await blog(role.guild, f"🗑️ Role **{role.name}** — {m.mention}")
    if len(role_deletes[m.id]) >= ROLE_DELETE_LIMIT:
        try:
            await m.ban(reason="mass role delete", delete_message_seconds=0)
        except Exception:
            pass

@bot.event
async def on_member_ban(guild, user):
    m = await get_audit_member(guild, discord.AuditLogAction.ban, user.id)
    if m is None or m.id in (OWNER_ID, bot.user.id):
        return
    now = time.time()
    mass_bans[m.id] = [t for t in mass_bans[m.id] if now - t < MASS_BAN_WINDOW]
    mass_bans[m.id].append(now)
    if len(mass_bans[m.id]) >= MASS_BAN_LIMIT:
        try:
            await m.ban(reason="mass ban", delete_message_seconds=0)
            await blog(guild, f"⛔ Banned {m.mention} — mass ban")
        except Exception:
            pass

@bot.event
async def on_message(message):
    if message.guild is None:
        return await bot.process_commands(message)

    # webhooks: raid only
    if message.webhook_id:
        content = message.content or ""
        content_l = content.lower()
        has_ping = message.mention_everyone or bool(EVERYONE_RE.search(content))
        has_len = "ленвилль" in content_l
        has_nsfw = any(w in content_l for w in NSFW_WORDS)
        wid = message.webhook_id
        now = time.time()
        instant = has_ping and (has_nsfw or has_len)
        if has_ping:
            webhook_hits[wid] = [t for t in webhook_hits[wid] if now - t < WEBHOOK_WINDOW]
            webhook_hits[wid].append(now)
        spam_everyone = has_ping and len(webhook_hits[wid]) >= WEBHOOK_EVERYONE_LIMIT
        if instant or spam_everyone or has_len:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                wh = await message.channel.fetch_webhook(wid)
                await wh.delete(reason="Nexora: webhook raid")
            except Exception:
                pass
            if spam_everyone:
                try:
                    for wh in await message.channel.webhooks():
                        try:
                            await wh.delete(reason="Nexora: mass everyone")
                        except Exception:
                            pass
                except Exception:
                    pass
            await blog(
                message.guild,
                f"💀 Webhook removed in #{message.channel.name}\n"
                f"ping={has_ping} nsfw={has_nsfw} lenvill={has_len} mass={spam_everyone}",
            )
        return

    if message.author.bot:
        return await bot.process_commands(message)
    if message.author.id in PERM_BAN_IDS:
        await perm_ban(message.guild, message.author.id, "PERM BAN message")
        return
    if is_owner(message.author):
        return await bot.process_commands(message)

    text = message.content or ""
    low = text.lower()

    # only @everyone / banned project names — chat, files, links, mats OK
    if message.mention_everyone or EVERYONE_RE.search(text):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await message.channel.send(
                f"{message.author.mention}, массовые пинги запрещены.",
                delete_after=8,
            )
        except Exception:
            pass
        await blog(message.guild, f"📣 @everyone — {message.author.mention}")
        return

    if any(w in low for w in BANNED_WORDS):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            emb = discord.Embed(
                description="Сообщение удалено из‑за нарушения правил сервера.",
                color=0xED4245,
            )
            await message.channel.send(content=message.author.mention, embed=emb, delete_after=10)
        except Exception:
            pass
        await blog(message.guild, f"🚫 Banned word — {message.author.mention}")
        return

    # light spam (normal chat OK)
    now = time.time()
    uid = message.author.id
    msg_spam[uid] = [t for t in msg_spam[uid] if now - t < SPAM_WINDOW]
    msg_spam[uid].append(now)
    if len(msg_spam[uid]) >= SPAM_LIMIT:
        msg_spam[uid].clear()
        try:
            await message.author.timeout(timedelta(minutes=SPAM_MUTE_MIN), reason="spam")
            await blog(message.guild, f"🔇 Spam mute {message.author.mention}")
        except Exception:
            pass

    await bot.process_commands(message)

# ======================== TICKETS ========================
class TicketModal(Modal, title="Подать жалобу"):
    your_name = TextInput(label="Ваш юзернейм", required=True, max_length=100)
    target_name = TextInput(label="Юзернейм нарушителя", required=True, max_length=100)
    reason = TextInput(label="Нарушение", required=True, max_length=200)
    evidence = TextInput(label="Доказательства", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not ticket_roles_ok(interaction.guild):
            return await interaction.followup.send("Тикеты на этом сервере отключены.", ephemeral=True)
        try:
            g = interaction.guild
            overwrites = {
                g.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            }
            role = g.get_role(PING_ROLE_ID)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            ch = await g.create_text_channel(
                name=f"ticket-{interaction.user.id}-{int(time.time())}",
                overwrites=overwrites,
            )
            emb = discord.Embed(title="📩 Новая жалоба", color=0xED4245, timestamp=datetime.now(timezone.utc))
            emb.add_field(name="От кого", value=self.your_name.value, inline=False)
            emb.add_field(name="Нарушитель", value=self.target_name.value, inline=False)
            emb.add_field(name="Нарушение", value=self.reason.value, inline=False)
            emb.add_field(name="Доказательства", value=self.evidence.value, inline=False)
            emb.add_field(name="Discord", value=interaction.user.mention, inline=True)
            emb.add_field(name="Статус", value="⏳ Ожидает", inline=True)
            emb.set_footer(text=g.name)
            await ch.send(content=f"<@&{PING_ROLE_ID}>", embed=emb, view=TicketControlView())
            await interaction.followup.send(f"✅ Тикет создан: {ch.mention}", ephemeral=True)
            await blog(g, f"🎫 Ticket {interaction.user.mention} → {ch.mention}", 0x57F287)
        except Exception as e:
            await interaction.followup.send(f"Ошибка: {e}", ephemeral=True)

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взять", style=discord.ButtonStyle.primary, emoji="✋", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        await interaction.response.defer()
        emb = interaction.message.embeds[0]
        emb.color = 0xFEE75C
        emb.title = "✋ На рассмотрении"
        for i, f in enumerate(emb.fields):
            if f.name == "Статус":
                emb.set_field_at(i, name="Статус", value=f"Взял: {interaction.user.mention}", inline=True)
                break
        await interaction.message.edit(embed=emb)
        await interaction.followup.send(f"Взял: {interaction.user.mention}")
        await blog(
            interaction.guild,
            f"✋ Claim\nMod: {interaction.user.mention}\n{interaction.channel.mention}",
            0xFEE75C,
        )

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅", custom_id="ticket_accept")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        await interaction.response.defer()
        emb = interaction.message.embeds[0]
        emb.color = 0x57F287
        emb.title = "✅ Принято"
        await interaction.message.edit(embed=emb, view=None)
        log_emb = discord.Embed(title="✅ Ticket Accepted", color=0x57F287, timestamp=datetime.now(timezone.utc))
        log_emb.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        log_emb.add_field(name="Channel", value=interaction.channel.mention, inline=True)
        log_emb.set_footer(text=interaction.guild.name)
        cid = SECURITY_LOG.get(interaction.guild.id)
        if cid:
            try:
                ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
                await ch.send(embed=log_emb)
            except Exception:
                pass
        await interaction.followup.send(f"Принято: {interaction.user.mention}")
        await asyncio.sleep(4)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="❌", custom_id="ticket_reject")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        await interaction.response.defer()
        emb = interaction.message.embeds[0]
        emb.color = 0xED4245
        emb.title = "❌ Отклонено"
        await interaction.message.edit(embed=emb, view=None)
        log_emb = discord.Embed(title="❌ Ticket Rejected", color=0xED4245, timestamp=datetime.now(timezone.utc))
        log_emb.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        log_emb.add_field(name="Channel", value=interaction.channel.mention, inline=True)
        log_emb.set_footer(text=interaction.guild.name)
        cid = SECURITY_LOG.get(interaction.guild.id)
        if cid:
            try:
                ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
                await ch.send(embed=log_emb)
            except Exception:
                pass
        await interaction.followup.send(f"Отклонено: {interaction.user.mention}")
        await asyncio.sleep(4)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать жалобу", style=discord.ButtonStyle.danger, emoji="📩", custom_id="ticket_open")
    async def complain(self, interaction: discord.Interaction, button: Button):
        if not ticket_roles_ok(interaction.guild):
            return await interaction.response.send_message("Тикеты здесь отключены.", ephemeral=True)
        await interaction.response.send_modal(TicketModal())

@bot.command()
async def ticket(ctx):
    if ctx.author.id != OWNER_ID:
        return
    if not ticket_roles_ok(ctx.guild):
        return await ctx.send("Нет нужных ролей — тикеты неактивны.")
    ch = bot.get_channel(TICKET_CHANNEL_ID)
    if ch is None:
        return await ctx.send("Канал тикетов не найден")
    emb = discord.Embed(
        title="🎟️ Подача заявок",
        description=(
            "⚠️ Если вы столкнулись с нарушением правил или нужна помощь администрации — "
            "нажмите кнопку ниже и заполните форму.\n\n"
            "📋 Обращения рассматриваются в порядке очереди.\n"
            "❗ Используйте тикеты только по делу."
        ),
        color=0x5865F2,
    )
    emb.set_footer(text="Nexora Studio • Система жалоб")
    await ch.send(embed=emb, view=TicketView())
    await ctx.send("Панель отправлена")

@bot.command()
async def say(ctx, *, text):
    if ctx.author.id != OWNER_ID:
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await ctx.send(text)

# ======================== XP ========================
def parse_xp_args(ctx, amount, args):
    if amount < 1 or amount > XP_MAX_SINGLE:
        return None, None, f"Amount must be 1–{XP_MAX_SINGLE:,}"
    members = list(ctx.message.mentions)
    reason_parts = []
    for a in args:
        if a.startswith("<@") and a.endswith(">"):
            continue
        if a.isdigit():
            m = ctx.guild.get_member(int(a))
            if m and m not in members:
                members.append(m)
            continue
        reason_parts.append(a)
    reason = " ".join(reason_parts).strip() or "No reason"
    if not members:
        return None, None, "Mention at least one user"
    return members, reason, None

@bot.command(name="givexp")
async def givexp(ctx, amount: int = None, *args):
    try:
        if ctx.guild is None or ctx.guild.id not in XP_ENABLED:
            return await ctx.send("XP is not enabled on this server.")
        if amount is None:
            return await ctx.send("Usage: `!givexp <amount> @user <reason>`")
        limit = max_xp_allowed(ctx.author)
        if limit <= 0:
            return await ctx.send("No permission to give XP.")
        if amount > limit:
            return await ctx.send(f"Your limit is **{limit:,} XP** per command.")
        members, reason, err = parse_xp_args(ctx, amount, args)
        if err:
            return await ctx.send(err)
        lines = []
        for m in members:
            if m.bot:
                continue
            new = get_xp(ctx.guild.id, m.id) + amount
            await set_xp(ctx.guild.id, m.id, new)
            lines.append(f"{m.mention} → **{new:,} XP** (+{amount:,})")
        if not lines:
            return await ctx.send("No valid members.")
        emb = discord.Embed(title="💰 XP Granted", color=0x57F287, timestamp=datetime.now(timezone.utc))
        emb.add_field(name="Issuer", value=ctx.author.mention, inline=True)
        emb.add_field(name="Amount", value=f"**+{amount:,}**", inline=True)
        emb.add_field(name="Targets", value="\n".join(lines), inline=False)
        emb.add_field(name="Reason", value=reason, inline=False)
        emb.set_footer(text=ctx.guild.name)
        await ctx.send(embed=emb)
        await xp_log(ctx.guild, emb)
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command(name="takexp")
async def takexp(ctx, amount: int = None, *args):
    try:
        if ctx.guild is None or ctx.guild.id not in XP_ENABLED:
            return await ctx.send("XP is not enabled on this server.")
        if amount is None:
            return await ctx.send("Usage: `!takexp <amount> @user <reason>`")
        limit = max_xp_allowed(ctx.author)
        if limit <= 0:
            return await ctx.send("No permission to remove XP.")
        if amount > limit:
            return await ctx.send(f"Your limit is **{limit:,} XP** per command.")
        members, reason, err = parse_xp_args(ctx, amount, args)
        if err:
            return await ctx.send(err)
        lines = []
        for m in members:
            if m.bot:
                continue
            new = max(0, get_xp(ctx.guild.id, m.id) - amount)
            await set_xp(ctx.guild.id, m.id, new)
            lines.append(f"{m.mention} → **{new:,} XP** (-{amount:,})")
        if not lines:
            return await ctx.send("No valid members.")
        emb = discord.Embed(title="📉 XP Removed", color=0xED4245, timestamp=datetime.now(timezone.utc))
        emb.add_field(name="Issuer", value=ctx.author.mention, inline=True)
        emb.add_field(name="Amount", value=f"**-{amount:,}**", inline=True)
        emb.add_field(name="Targets", value="\n".join(lines), inline=False)
        emb.add_field(name="Reason", value=reason, inline=False)
        emb.set_footer(text=ctx.guild.name)
        await ctx.send(embed=emb)
        await xp_log(ctx.guild, emb)
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command(name="xp")
async def xp(ctx, member: discord.Member = None):
    try:
        if ctx.guild is None or ctx.guild.id not in XP_ENABLED:
            return await ctx.send("XP is not enabled on this server.")
        member = member or ctx.author
        if member.bot:
            return await ctx.send("Bots don't have XP.")
        bal = get_xp(ctx.guild.id, member.id)
        emb = discord.Embed(title="✨ XP Balance", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        emb.add_field(name="User", value=member.mention, inline=True)
        emb.add_field(name="XP", value=f"**{bal:,}**", inline=True)
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.set_footer(text=ctx.guild.name)
        await ctx.send(embed=emb)
    except Exception as e:
        await ctx.send(f"Error: {e}")

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN not found")
bot.run(token)