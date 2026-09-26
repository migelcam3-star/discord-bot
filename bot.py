import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import time
import asyncio
from collections import defaultdict
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
    1536095886793252874,
]

ticket_times = defaultdict(list)

def is_staff(member):
    if member.id == OWNER_ID:
        return True
    return any(role.id in STAFF_ROLES for role in member.roles)

def is_muted(member):
    try:
        return member.timed_out_until is not None and member.timed_out_until > discord.utils.utcnow()
    except Exception:
        return False

def check_spam(user_id):
    now = time.time()
    ticket_times[user_id] = [t for t in ticket_times[user_id] if now - t < 10]
    if len(ticket_times[user_id]) >= 4:
        ticket_times[user_id].append(now)
        return True
    ticket_times[user_id].append(now)
    return False
class TicketModal(Modal, title="Подать жалобу"):
    your_name = TextInput(label="Ваш юзернейм", placeholder="Пример: mrmigelll", required=True, max_length=100)
    target_name = TextInput(label="Юзернейм нарушителя", placeholder="Пример: denis014883", required=True, max_length=100)
    reason = TextInput(label="Нарушение", placeholder="Пример: оскорбление", required=True, max_length=200)
    evidence = TextInput(label="Доказательства", placeholder="Скрины, видео, ссылки", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if is_muted(interaction.user):
            return await interaction.followup.send("Вы в мьюте и не можете подать жалобу.", ephemeral=True)

        if check_spam(interaction.user.id):
            try:
                await interaction.user.timeout(timedelta(minutes=30), reason="Спам тикетами")
            except Exception as e:
                print(f"Mute error: {e}")
            return await interaction.followup.send("Слишком много тикетов. Мьют на 30 минут.", ephemeral=True)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        role = interaction.guild.get_role(PING_ROLE_ID)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel_name = f"ticket-{interaction.user.id}-{int(time.time())}"
        try:
            channel = await interaction.guild.create_text_channel(name=channel_name, overwrites=overwrites)
        except Exception as e:
            print(f"Channel error: {e}")
            return await interaction.followup.send(f"Ошибка создания канала: {e}", ephemeral=True)

        emb = discord.Embed(title="Новая жалоба", color=0xED4245)
        emb.add_field(name="От кого", value=self.your_name.value, inline=False)
        emb.add_field(name="Нарушитель", value=self.target_name.value, inline=False)
        emb.add_field(name="Нарушение", value=self.reason.value, inline=False)
        emb.add_field(name="Доказательства", value=self.evidence.value, inline=False)
        emb.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
        emb.add_field(name="Статус", value="Ожидает", inline=False)
        emb.set_footer(text=f"ID: {interaction.user.id}")

        await channel.send(content=f"<@&{PING_ROLE_ID}>", embed=emb, view=TicketControlView())
        await interaction.followup.send(f"Жалоба отправлена: {channel.mention}", ephemeral=True)
class TicketControlView(View):
    def init(self):
        super().init(timeout=None)

    @discord.ui.button(label="Взять на рассмотрение", style=discord.ButtonStyle.primary, emoji="✋")
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0xFEE75C
        emb.title = "На рассмотрении"
        for i, field in enumerate(emb.fields):
            if field.name == "Статус":
                emb.set_field_at(i, name="Статус", value=f"Взял: {interaction.user.mention}", inline=False)
                break
        await interaction.message.edit(embed=emb)
        await interaction.response.send_message(f"Тикет взял: {interaction.user.mention}")

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0x57F287
        emb.title = "Жалоба принята"
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
        emb.title = "Жалоба отклонена"
        await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message(f"Отклонено: {interaction.user.mention}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

class TicketView(View):
    def init(self):
        super().init(timeout=None)

    @discord.ui.button(label="Подать жалобу", style=discord.ButtonStyle.danger, emoji="📩")
    async def complain(self, interaction: discord.Interaction, button: Button):
        if is_muted(interaction.user):
            return await interaction.response.send_message(
                "Вы в мьюте и не можете подать жалобу.",
                ephemeral=True
            )
        await interaction.response.send_modal(TicketModal())
@bot.event
async def on_ready():
    print(f"Bot {bot.user} online!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="NexStudio"
        )
    )

@bot.command()
async def say(ctx, *, text):
    if ctx.author.id != OWNER_ID:
        return
    try:
        await ctx.message.delete()
    except Exception:
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
        title="🎟️ Подача заявок",
        description=(
            "⚠️ Если вы столкнулись с нарушением правил или вам нужна помощь администрации, "
            "нажмите кнопку ниже и заполните форму заявки.\n\n"
            "📋 Все обращения рассматриваются администрацией в порядке очереди.\n"
            "❗ Просим использовать систему тикетов только по назначению и не создавать обращения без причины."
        ),
        color=0x5865F2
    )
    emb.set_footer(text="Система жалоб • NexStudio")
    await channel.send(embed=emb, view=TicketView())
    await ctx.send("Панель отправлена")

bot.run(os.getenv("DISCORD_TOKEN"))