import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import time
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

        channel_name = f"тикет-{interaction.user.id}-{int(time.time())}"

        try:
            channel = await interaction.guild.create_text_channel(name=channel_name, overwrites=overwrites)
        except Exception as e:
            return await interaction.followup.send(f"❌ Не удалось создать канал: {e}", ephemeral=True)

        emb = discord.Embed(title="📩 Новая жалоба", color=0xED4245)
        emb.add_field(name="От кого", value=self.your_name.value, inline=False)
        emb.add_field(name="Нарушитель", value=self.target_name.value, inline=False)
        emb.add_field(name="Нарушение", value=self.reason.value, inline=False)
        emb.add_field(name="Доказательства", value=self.evidence.value, inline=False)
        emb.add_field(name="Пользователь", value=interaction.user.mention, inline=False)
        emb.set_footer(text=f"ID: {interaction.user.id}")

        await channel.send(content=f"<@&{PING_ROLE_ID}>", embed=emb, view=TicketControlView())
        await interaction.followup.send(f"✅ Жалоба отправлена! Тикет: {channel.mention}", ephemeral=True)

class TicketControlView(View):
    def init(self):
        super().init(timeout=None)

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: Button):
        if not any(r.id == PING_ROLE_ID for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0x57F287
        emb.title = "✅ Жалоба принята"
        await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message(f"Принято: {interaction.user.mention}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if not any(r.id == PING_ROLE_ID for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Нет прав", ephemeral=True)
        emb = interaction.message.embeds[0]
        emb.color = 0xED4245
        emb.title = "❌ Жалоба отклонена"
        await interaction.message.edit(embed=emb, view=None)
        await interaction.response.send_message(f"Отклонено: {interaction.user.mention}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

class TicketView(View):
    def init(self):
        super().init(timeout=None)

    @discord.ui.button(label="Пожаловаться", style=discord.ButtonStyle.danger, emoji="📩")
    async def complain(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketModal())

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