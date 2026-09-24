import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os
import time
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

OWNER_ID = 1464526568293531763
TICKET_CHANNEL_ID = 1534939950061977661
PING_ROLE_ID = 1541525446959702146

STAFF_ROLES = [
    1540009967040602232,
    1534841235167117352,
    1549116304659710115,
    1541494617290309793,
    1550202959898353836,
    1550202161575624885,
    1536095886793252874
]

ARCHIVE_ROLES = [
    1541494617290309793,
    1550202959898353836,
    1550202161575624885,
    1551180719265681418,
    1536095886793252874
]

ARCHIVE_FILE = "tickets_archive.json"

def load_archive():
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_archive(data):
    try:
        with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass

def is_staff(member):
    if member.id == OWNER_ID:
        return True
    return any(r.id in STAFF_ROLES for r in member.roles)

def can_archive(member):
    if member.id == OWNER_ID:
        return True
    return any(r.id in ARCHIVE_ROLES for r in member.roles)

class TicketModal(Modal, title="Подать заявку"):
    your_name = TextInput(label="Ваш юзернейм в дискорде", placeholder="Пример: mrmigelll", required=True, max_length=100)
    target_name = TextInput(label="Юзернейм нарушителя", placeholder="Пример: denis014883", required=True, max_length=100)
    reason = TextInput(label="Нарушение", placeholder="Пример: оскорбление", required=True, max_length=200)
    evidence = TextInput(label="Док. Материалы", placeholder="Скрины, видео, файлы", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        role = interaction.guild.get_role(PING_ROLE_ID)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel_name = f"ticket-{interaction.user.id}-{int(time.time())}"

        try:
            channel = await interaction.guild.create_text_channel(name=channel_name, overwrites=overwrites)
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка создания канала: {e}", ephemeral=True)

        emb = discord.Embed(title="📩 Новая жалоба", color=0xED4245)
        emb.add_field(name="От кого", value=self.your_name.value, inline=False)
        emb.add_field(name="Нарушитель", value=self.target_name.value, inline=False)
        emb.add_field(name="Нарушение", value=self.reason.value, inline=False)
        emb.add_field(name="Доказательства", value=self.evidence.value, inline=False)
        emb.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
        emb.add_field(name="Статус", value="⏳ Ожидает", inline=False)
        emb.set_footer(text=f"ID: {interaction.user.id}")

        msg = await channel.send(content=f"<@&{PING_ROLE_ID}>", embed=emb, view=TicketControlView())

        archive = load_archive()
        archive.insert(0, {
            "name": channel.name,
            "url": msg.jump_url,
            "user": str(interaction.user),
            "reason": self.reason.value[:80],
            "time": int(time.time())
        })
        save_archive(archive[:50])

        await interaction.followup.send(f"✅ Жалоба отправлена! Тикет: {channel.mention}", ephemeral=True)

@discord.ui.button(label="Архив тикетов", style=discord.ButtonStyle.secondary, emoji="📁")
    async def archive(self, interaction: discord.Interaction, button: Button):
        if not can_archive(interaction.user):
            return await interaction.response.send_message("Нет прав на архив", ephemeral=True)

        data = load_archive()
        if not data:
            return await interaction.response.send_message("Архив пуст", ephemeral=True)

        options = []
        for t in data[:25]:
            label = f"{t.get('user', '?')[:30]} — {t.get('reason', '')[:40]}"
            options.append(discord.SelectOption(
                label=label[:100],
                value=t.get("url", "нет"),
                description=str(t.get("name", ""))[:50]
            ))

        emb = discord.Embed(
            title="📁 Архив тикетов",
            description="Выберите тикет, чтобы получить ссылку.\nПисать нельзя — только просмотр.",
            color=0x5865F2
        )
        await interaction.response.send_message(embed=emb, view=ArchiveView(options), ephemeral=True)

@bot.event
async def on_ready():
    print(f'Bot {bot.user} online!')

@bot.command()
async def say(ctx, *, text):
    if ctx.author.id != OWNER_ID:
        return
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(text)

@bot.command()
async def ticket(ctx):
    if ctx.author.id != OWNER_ID:
        return
    channel = bot.get_channel(TICKET_CHANNEL_ID)
    if not channel:
        return await ctx.send("Канал не найден")

    emb = discord.Embed(
        title="📩 Подача тикета на участника или команду проекта",
        description=(
            "Если вы столкнулись с нарушением правил со стороны участника или команды проекта, "
            "вы можете подать жалобу, нажав на кнопку ниже — 「Пожаловаться」.\n\n"
            "Все обращения рассматриваются администрацией в порядке очереди. "
            "Просим использовать систему тикетов только по назначению и не создавать обращения без причины."
        ),
        color=0x5865F2
    )
    emb.set_footer(text="Система жалоб")
    await channel.send(embed=emb, view=TicketView())
    await ctx.send("✅ Панель отправлена")

bot.run(os.getenv('DISCORD_TOKEN'))