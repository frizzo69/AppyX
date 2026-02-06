import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX")
OWNER_ID = int(os.getenv("OWNER_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ---------- DATABASE ----------

def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

forms = load_json("data/forms.json", {})
bans = load_json("data/bans.json", {})
applications = load_json("data/applications.json", {})

# ---------- HELP COMMAND ----------

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Application Bot Help", color=0x2f3136)
    embed.add_field(name="-createform", value="Create new application form", inline=False)
    embed.add_field(name="-createpanel <form_name> <channel>", value="Create panel in channel", inline=False)
    embed.add_field(name="-setrole <form> <role_id>", value="Set accepted role", inline=False)
    embed.add_field(name="-setchannel <form> <channel_id>", value="Set submission channel", inline=False)
    embed.add_field(name="-setcategory <form> <category_id>", value="Set ticket category", inline=False)
    embed.add_field(name="-setcooldown <form> <hours>", value="Set reapply cooldown", inline=False)
    embed.add_field(name="-banapply <user> <hours>", value="Ban user from applying", inline=False)
    embed.add_field(name="-unbanapply <user>", value="Remove ban", inline=False)
    await ctx.send(embed=embed)

# ---------- CREATE FORM ----------

@bot.command()
@commands.has_permissions(administrator=True)
async def createform(ctx, name):
    forms[name] = {
        "questions": [],
        "channel": None,
        "role": None,
        "category": None,
        "cooldown": 24
    }
    save_json("data/forms.json", forms)
    await ctx.send(f"Form `{name}` created.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addquestion(ctx, form, *, question):
    forms[form]["questions"].append(question)
    save_json("data/forms.json", forms)
    await ctx.send("Question added.")

# ---------- APPLICATION PANEL ----------

class ApplyButton(Button):
    def __init__(self, form_name):
        super().__init__(label="Apply", style=discord.ButtonStyle.green)
        self.form_name = form_name

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Check ban
        if user_id in bans:
            if datetime.utcnow() < datetime.fromisoformat(bans[user_id]):
                await interaction.response.send_message("You cannot apply yet.", ephemeral=True)
                return
            else:
                bans.pop(user_id)
                save_json("data/bans.json", bans)

        await interaction.response.send_message("Check your DMs.", ephemeral=True)

        questions = forms[self.form_name]["questions"]
        answers = []

        for q in questions:
            await interaction.user.send(q)
            def check(m):
                return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)
            msg = await bot.wait_for("message", check=check)
            answers.append(msg.content)

        # Save application
        applications[user_id] = {
            "form": self.form_name,
            "answers": answers
        }
        save_json("data/applications.json", applications)

        # Send to staff channel
        channel = bot.get_channel(forms[self.form_name]["channel"])
        embed = discord.Embed(title="New Application", color=0x3498db)
        for i, q in enumerate(questions):
            embed.add_field(name=q, value=answers[i], inline=False)
        embed.set_footer(text=f"User ID: {user_id}")

        view = ReviewButtons(user_id)
        await channel.send(embed=embed, view=view)

class ReviewButtons(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        member = interaction.guild.get_member(int(self.user_id))
        form = applications[self.user_id]["form"]

        role_id = forms[form]["role"]
        role = interaction.guild.get_role(role_id)
        await member.add_roles(role)

        await member.send("Your application has been accepted!")

        # Create ticket
        category = interaction.guild.get_channel(forms[form]["category"])
        ticket = await interaction.guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category
        )
        await ticket.send(f"{member.mention} welcome!")

        bans[self.user_id] = (datetime.utcnow() + timedelta(hours=forms[form]["cooldown"])).isoformat()
        save_json("data/bans.json", bans)

        await interaction.response.send_message("Accepted.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: Button):
        member = interaction.guild.get_member(int(self.user_id))
        await member.send("Your application has been denied.")
        await interaction.response.send_message("Denied.")

# ---------- PANEL COMMAND ----------

@bot.command()
@commands.has_permissions(administrator=True)
async def createpanel(ctx, form, channel: discord.TextChannel):
    view = View()
    view.add_item(ApplyButton(form))
    await channel.send(f"Apply for {form}", view=view)

# ---------- CONFIG COMMANDS ----------

@bot.command()
async def setrole(ctx, form, role: discord.Role):
    forms[form]["role"] = role.id
    save_json("data/forms.json", forms)
    await ctx.send("Role set.")

@bot.command()
async def setchannel(ctx, form, channel: discord.TextChannel):
    forms[form]["channel"] = channel.id
    save_json("data/forms.json", forms)
    await ctx.send("Submission channel set.")

@bot.command()
async def setcategory(ctx, form, category: discord.CategoryChannel):
    forms[form]["category"] = category.id
    save_json("data/forms.json", forms)
    await ctx.send("Ticket category set.")

@bot.command()
async def setcooldown(ctx, form, hours: int):
    forms[form]["cooldown"] = hours
    save_json("data/forms.json", forms)
    await ctx.send("Cooldown updated.")

@bot.command()
async def banapply(ctx, user: discord.Member, hours: int):
    bans[str(user.id)] = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    save_json("data/bans.json", bans)
    await ctx.send("User banned from applying.")

@bot.command()
async def unbanapply(ctx, user: discord.Member):
    bans.pop(str(user.id), None)
    save_json("data/bans.json", bans)
    await ctx.send("User unbanned.")

# ---------- RUN ----------

bot.run(TOKEN)
