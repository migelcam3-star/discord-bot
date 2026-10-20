import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import time
import re
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

# ======================== НАСТРОЙКИ ========================
OWNER_ID = 1464526568293531763
TICKET_CHANNEL_ID = 1534939950061977661
PING_ROLE_ID = 1541525446959702146

LOG_CHANNEL_IDS = [
    1536339631753273404,
    1552260303155105812,
    1561703963903139942,
]

STAFF_ROLES = [
    1540009967040602232,
    1534841235167117352,
    1549116304659710115,
    1541494617290309793,
    1550202959898353836,
    1550202161575624885,
    1536095886793252874,
]

PERM_BAN_IDS = {
    953962723568386049,
    1474709890743144448,
    1416328122651119749,
    1261075830117892150,
    1446108507505037425,
    1284485012158283790,
    1555253548646670428,
    1467173693917499405,
    1549017207084949554,
}

WHITELIST_BOTS = set()

BANNED_WORDS = ["ленвилль", "смелдар", "orbix studio"]
INVITE_RE = re.compile(r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[^\s]+", re.I)
EVERYONE_RE = re.compile(r"@(everyone|here)", re.I)

SUSPICIOUS_BOT_PATTERNS = [
    r"crash", r"crasher", r"nuker", r"nuke", r"raider", r"raid",
    r"destroyer", r"wizz", r"token", r"selfbot", r"massban",
    r"server.?nuke", r"raidbot", r"spam.?bot",
]

CHANNEL_DELETE_LIMIT, CHANNEL_DELETE_WINDOW = 3, 12
ROLE_DELETE_LIMIT, ROLE_DELETE_WINDOW = 3, 12
MASS_BAN_LIMIT, MASS_BAN_WINDOW = 3, 15
SPAM_LIMIT, SPAM_WINDOW, SPAM_MUTE_MIN = 6, 8, 15
WEBHOOK_EVERYONE_LIMIT, WEBHOOK_WINDOW = 2, 10
# ===========================================================

channel_deletes = defaultdict(list)
role_deletes = defaultdict(list)
mass_bans = defaultdict(list)
msg_spam = defaultdict(list)
webhook_hits = defaultdict(list)

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
    emb = discord.Embed(
        description=text,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    name = guild.name if guild else "—"
    emb.set_footer(text=f"Nexora Security • {name}")
    for cid in LOG_CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if ch is None:
            try:
                ch = await bot.fetch_channel(cid)
            except Exception:
                continue
        try:
            await ch.send(embed=emb)
        except Exception:
            pass

async def perm_ban(guild, user_id, reason="PERM BAN list"):
    try:
        user = await bot.fetch_user(user_id)
        await guild.ban(user, reason=reason, delete_message_seconds=0)
        await blog(guild, f"⛔ PERM BAN `{user_id}` — {reason}")
    except Exception as e:
        await blog(guild, f"❌ perm ban fail `{user_id}`: {e}")

async def get_audit_member(guild, action, target_id):
    try:
        async for e in guild.audit_logs(limit=6, action=action):
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
            return True, f"имя: {p}"
    created = member.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created).days
    if age < 7:
        return True, f"аккаунт < 7 дней ({age})"
    return True, "не в whitelist"

@bot.event
async def on_ready():
    print(f"Nexora {bot.user} online!")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🛡️ Nexora Studio")
    )

@bot.event
async def on_member_join(member):
    if member.id in PERM_BAN_IDS:
        await perm_ban(member.guild, member.id, "PERM BAN list (join)")
        return

    if member.bot:
        adder = None
        try:
            async for e in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if e.target and e.target.id == member.id:
                    adder = member.guild.get_member(e.user.id)
                    break
        except Exception:
            pass
        bad, why = suspicious_bot(member)
        await blog(
            member.guild,
            f"🤖 Бот **{member}** (`{member.id}`)\nДобавил: {adder}\nСтатус: {why}",
            0xED4245 if bad else 0x57F287,
        )
        if bad:
            try:
                await member.kick(reason=f"Nexora: {why}")
                await blog(member.guild, f"👢 Кикнут бот **{member}** — {why}")
            except Exception as e:
                await blog(member.guild, f"❌ Не кикнул бота: {e}")
            if adder and adder.id not in (OWNER_ID, bot.user.id):
                try:
                    await adder.ban(reason=f"добавил опасного бота {member}", delete_message_seconds=0)
                    await blog(member.guild, f"⛔ Бан {adder.mention} — добавил опасного бота")
                except Exception as e:
                    await blog(member.guild, f"❌ Не забанил добавившего: {e}")
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
        emb.set_footer(text="Nexora Studio")
        ch = member.guild.system_channel
        if ch is None:
            ch = bot.get_channel(TICKET_CHANNEL_ID)
        if ch is not None:
            await ch.send(content=member.mention, embed=emb)
    except Exception:
        pass

@bot.event
async def on_member_unban(guild, user):
    if user.id in PERM_BAN_IDS:
        await asyncio.sleep(0.5)
        await perm_ban(guild, user.id, "PERM BAN list (auto re-ban)")

@bot.event
async def on_guild_channel_delete(channel):
    m = await get_audit_member(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    if m is None or m.id in (OWNER_ID, bot.user.id):
        return
    if m.bot:
        try:
            await m.kick(reason="бот удаляет каналы")
            await blog(channel.guild, f"👢 Бот {m.mention} кикнут — удалял каналы")
        except Exception:
            pass
        return
    now = time.time()
    channel_deletes[m.id] = [t for t in channel_deletes[m.id] if now - t < CHANNEL_DELETE_WINDOW]
    channel_deletes[m.id].append(now)
    await blog(channel.guild, f"🗑️ Канал **#{channel.name}** удалён — {m.mention}")
    if len(channel_deletes[m.id]) >= CHANNEL_DELETE_LIMIT:
        try:
            await m.ban(reason="снос каналов", delete_message_seconds=0)
            await blog(channel.guild, f"⛔ Бан {m.mention} — снос каналов")
        except Exception:
            pass

@bot.event
async def on_guild_role_delete(role):
    m = await get_audit_member(role.guild, discord.AuditLogAction.role_delete, role.id)
    if m is None or m.id in (OWNER_ID, bot.user.id):
        return
    if m.bot:
        try:
            await m.kick(reason="бот удаляет роли")
        except Exception:
            pass
        return
    now = time.time()
    role_deletes[m.id] = [t for t in role_deletes[m.id] if now - t < ROLE_DELETE_WINDOW]
    role_deletes[m.id].append(now)
    await blog(role.guild, f"🗑️ Роль **{role.name}** — {m.mention}")
    if len(role_deletes[m.id]) >= ROLE_DELETE_LIMIT:
        try:
            await m.ban(reason="снос ролей", delete_message_seconds=0)
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
            await m.ban(reason="масс-бан", delete_message_seconds=0)
            await blog(guild, f"⛔ Бан {m.mention} — масс-бан")
        except Exception:
            pass

@bot.event
async def on_message(message):
    if message.guild is None:
        return await bot.process_commands(message)

    # ----- вебхуки -----
    if message.webhook_id:
        content_l = (message.content or "").lower()
        has_ping = message.mention_everyone or bool(EVERYONE_RE.search(message.content or ""))
        has_len = "ленвилль" in content_l
        if has_ping or has_len:
            wid = message.webhook_id
            now = time.time()
            webhook_hits[wid] = [t for t in webhook_hits[wid] if now - t < WEBHOOK_WINDOW]
            webhook_hits[wid].append(now)
            if has_len or len(webhook_hits[wid]) >= WEBHOOK_EVERYONE_LIMIT:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    wh = await message.channel.fetch_webhook(wid)
                    await wh.delete(reason="Nexora: webhook raid")
                    await blog(message.guild, f"💀 Вебхук удалён в #{message.channel.name}")
                except Exception as e:
                    await blog(message.guild, f"❌ webhook delete: {e}")
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

    # @everyone / @here
    if message.mention_everyone or EVERYONE_RE.search(text):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await message.channel.send(
                f"{message.author.mention}, вы нарушаете правила нашего проекта. Массовые пинги запрещены.",
                delete_after=10,
            )
        except Exception:
            pass
        await blog(message.guild, f"📣 Пинг everyone — {message.author.mention}")
        return

    # запрещённые слова
    if any(w in low for w in BANNED_WORDS):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            emb = discord.Embed(
                description="Ваше сообщение было удалено из‑за нарушения правил сервера.",
                color=0xED4245,
            )
            await message.channel.send(content=message.author.mention, embed=emb, delete_after=12)
        except Exception:
            pass
        await blog(message.guild, f"🚫 Запрещённое слово — {message.author.mention}")
        return

    # инвайты и файлы
    if INVITE_RE.search(text) or message.attachments:
        try:
            await message.delete()
        except Exception:
            pass
        try:
            emb = discord.Embed(
                description=(
                    "Сообщение удалено.\n"
                    "На сервере запрещены ссылки-приглашения и загрузка файлов без разрешения."
                ),
                color=0xFEE75C,
            )
            await message.channel.send(content=message.author.mention, embed=emb, delete_after=12)
        except Exception:
            pass
        return

    # спам
    now = time.time()
    uid = message.author.id
    msg_spam[uid] = [t for t in msg_spam[uid] if now - t < SPAM_WINDOW]
    msg_spam[uid].append(now)
    if len(msg_spam[uid]) >= SPAM_LIMIT:
        msg_spam[uid].clear()
        try:
            await message.channel.purge(limit=12, check=lambda m: m.author.id == uid)
        except Exception:
            pass
        try:
            await message.author.timeout(timedelta(minutes=SPAM_MUTE_MIN), reason="спам")
            await blog(message.guild, f"🔇 Спам-мьют {message.author.mention}")
        except Exception:
            pass

    await bot.process_commands(message)

# ======================== ТИКЕТЫ ========================
class TicketModal(Modal, title="Подать жалобу"):
    your_name = TextInput(label="Ваш юзернейм", required=True, max_length=100)
    target_name = TextInput(label="Юзернейм нарушителя", required=True, max_length=100)
    reason = TextInput(label="Нарушение", required=True, max_length=200)
    evidence = TextInput(label="Доказательства", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not ticket_roles_ok(interaction.guild):
            return await interaction.followup.send(
                "Тикеты на этом сервере отключены (нет нужных ролей).", ephemeral=True
            )
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
            emb = discord.Embed(title="Новая жалоба", color=0xED4245)
            emb.add_field(name="От кого", value=self.your_name.value, inline=False)
            emb.add_field(name="Нарушитель", value=self.target_name.value, inline=False)
            emb.add_field(name="Нарушение", value=self.reason.value, inline=False)
            emb.add_field(name="Доказательства", value=self.evidence.value, inline=False)
            emb.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
            emb.add_field(name="Статус", value="Ожидает", inline=False)
            await ch.send(content=f"<@&{PING_ROLE_ID}>", embed=emb, view=TicketControlView())
            await interaction.followup.send(f"Жалоба отправлена: {ch.mention}", ephemeral=True)
            await blog(g, f"🎫 Тикет от {interaction.user.mention} → {ch.mention}", 0x57F287)
        except Exception as e:
            await interaction.followup.send(f"Ошибка: {e}", ephemeral=True)

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Взять", style=discord.ButtonStyle.primary, emoji="✋")
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0xFEE75C
        emb.title = "На рассмотрении"
        for i, f in enumerate(emb.fields):
            if f.name == "Статус":
                emb.set_field_at(i, name="Статус", value=f"Взял: {interaction.user.mention}", inline=False)
                break
        await interaction.message.edit(embed=emb)
        await interaction.response.send_message(f"Взял: {interaction.user.mention}")

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0x57F287
        emb.title = "Принято"
        await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message(f"Принято: {interaction.user.mention}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0xED4245
        emb.title = "Отклонено"
        await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message(f"Отклонено: {interaction.user.mention}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать жалобу", style=discord.ButtonStyle.danger, emoji="📩")
    async def complain(self, interaction: discord.Interaction, button: Button):
        if not ticket_roles_ok(interaction.guild):
            return await interaction.response.send_message("Тикеты здесь отключены.", ephemeral=True)
        await interaction.response.send_modal(TicketModal())

@bot.command()
async def ticket(ctx):
    if ctx.author.id != OWNER_ID:
        return
    if not ticket_roles_ok(ctx.guild):
        return await ctx.send("На сервере нет нужных ролей — тикеты не активны.")
    ch = bot.get_channel(TICKET_CHANNEL_ID)
    if ch is None:
        return await ctx.send("Канал тикетов не найден")
    emb = discord.Embed(
        title="🎟️ Подача заявок",
        description=(
            "⚠️ Если вы столкнулись с нарушением правил или вам нужна помощь администрации, "
            "нажмите кнопку ниже и заполните форму заявки.\n\n"
            "📋 Все обращения рассматриваются в порядке очереди.\n"
            "❗ Используйте тикеты только по назначению."
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

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN не найден в .env")
bot.run(token)