import discord
import os
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
import json
from pathlib import Path

load_dotenv()

token = os.getenv('discord_token')
main_channel_id = int(os.getenv('shop_channel_id'))
admin_channel_id = int(os.getenv('admin_channel_id'))
category_id = int(os.getenv('category_id'))
sort_code = os.getenv('sort_code')
account_number = os.getenv('account_number')
name_on_account = os.getenv('name_on_account')

LOBBY_DATA_FILE = "lobby_channels.json"

def save_lobby_channels():
    """Save lobby channels to JSON file"""
    with open(LOBBY_DATA_FILE, 'w') as f:
        json.dump(lobby_channels, f, indent=2)

def load_lobby_channels():
    """Load lobby channels from JSON file"""
    global lobby_channels
    if Path(LOBBY_DATA_FILE).exists():
        with open(LOBBY_DATA_FILE, 'r') as f:
            lobby_channels = json.load(f)
            # Convert string keys back to integers (JSON keys are always strings)
            lobby_channels = {int(k): v for k, v in lobby_channels.items()}

bot = commands.Bot(command_prefix="pdg!", intents=discord.Intents.all())

lobby_channels = {}  # Maps lobby channel IDs to role IDs
temp_channels = {}   # Maps temporary channel IDs to their corresponding lobby channel IDs

class PaymentConfirmationView(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Payment Completed", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_payment_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin_channel = interaction.client.get_channel(admin_channel_id)
        if admin_channel:
            await admin_channel.send(
                f"🔔<@{self.admin_user_id}>, member {interaction.user.mention} has just paid for **{self.item_name}**.\n"
                f"Check their proof of payment here: {interaction.channel.mention}"
            )
            await interaction.response.send_message("Thank you for your purchase! Admin has been notified.", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("Error: Admin channel could not be found.", ephemeral=True)

class EmbedItemPage(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int):
        super().__init__() # Timeout is 180 seconds by default
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.blurple, emoji="🛍️")
    async def my_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = guild.get_channel(category_id)
        safe_item_name = self.item_name.lower().replace(" ", "-")
        channel_name = f"{user.name}'s-order-{safe_item_name}"
        new_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category)
        # 3. What happens when the button is clicked
        await interaction.response.send_message(f"Open {new_channel.mention}", ephemeral=True)
        welcome_embed = discord.Embed(
            title=f"Welcome to your order, {user.display_name}!",
            description=(
                f"To purchase **{self.item_name}**, please proceed with the payment. "
                "Once done, please provide proof of payment here and press the button below.\n\n"
                f"**Sort code:** {sort_code}\n"
                f"**Account number:** {account_number}\n"
                f"**Name**: {name_on_account}"
            ),
            color=discord.Color.gold()
        )
        payment_view = PaymentConfirmationView(self.item_name, self.admin_user_id)
        await new_channel.send(content=user.mention, embed=welcome_embed, view=payment_view)

@bot.event
async def on_ready():  
    global lobby_channels
    print('Bot is ready')
    
    # Load saved lobby channels
    load_lobby_channels()
    
    # Verify all saved channels still exist in Discord
    for guild in bot.guilds:
        channels_to_remove = []
        for channel_id in list(lobby_channels.keys()):
            channel = guild.get_channel(channel_id)
            if channel is None:
                # Channel was deleted, remove from tracking
                channels_to_remove.append(channel_id)
                print(f"Lobby channel {channel_id} not found, removing from memory")
        
        # Remove deleted channels
        for channel_id in channels_to_remove:
            lobby_channels.pop(channel_id, None)
    
    # Save the cleaned-up list
    save_lobby_channels()
    
    channel = bot.get_channel(main_channel_id)
    if channel:
        await channel.send(f"Bot online! Loaded {len(lobby_channels)} lobby channels")

@app_commands.command(name="create_item", description="Create a shop item")
async def create_item(
    interaction: discord.Interaction,
    admin_user: discord.User,
    shop_channel: discord.TextChannel,
    item_name: str,
    price: float,
    image_url: str,
    description: str
):
    embed = discord.Embed(title=item_name, color=discord.Color.blue())
    embed.add_field(name="Price", value=f"£{price}", inline=False)
    embed.add_field(name="Description", value=description, inline=False)
    embed.set_image(url=image_url)
    view = EmbedItemPage(item_name=item_name, admin_user_id=admin_user.id)

    try:
        await shop_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Item posted to {shop_channel.mention}", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"Bot doesn't have permission to send messages in {shop_channel.mention}.", ephemeral=True)

bot.tree.add_command(create_item)

@app_commands.command(name="setup_vc", description="Create a lobby voice channel for a role")
@app_commands.checks.has_permissions(manage_channels=True)
async def setup_vc(
    interaction: discord.Interaction,
    role: discord.Role,
    category: discord.CategoryChannel
):
    """Creates a lobby channel that is only visible/joinable by a specific role."""
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
        role: discord.PermissionOverwrite(view_channel=True, connect=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, move_members=True, manage_channels=True)
    }

    vc_name = f"Create {role.name.lower()} vc"
    
    lobby_channel = await interaction.guild.create_voice_channel(
        name=vc_name,
        category=category,
        overwrites=overwrites
    )
    
    lobby_channels[lobby_channel.id] = role.id
    save_lobby_channels()
    
    await interaction.response.send_message(f"Created parent voice chat {lobby_channel.mention} in category **{category.name}** for role **{role.name}**.", ephemeral=True)

bot.tree.add_command(setup_vc)

@bot.event
async def on_voice_state_update(member, before, after):
    # Case 1: User joins the Lobby voice channel
    if after.channel and after.channel.id in lobby_channels:
        lobby_vc = after.channel
        allowed_role_id = lobby_channels[lobby_vc.id]
        role = member.guild.get_role(allowed_role_id)
        
        if not role:
            return

        # Double check if the user actually has the role (optional, since permission should prevent them joining)
        if role in member.roles:
            # Overwrites for the temporary channel so only that role can access it
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                role: discord.PermissionOverwrite(view_channel=True, connect=True),
                member.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, move_members=True, manage_channels=True)
            }
            
            temp_name = f"{member.name}'s {role.name.lower()} vc"
            
            # Create the temporary channel in the same category as the lobby
            temp_vc = await member.guild.create_voice_channel(
                name=temp_name,
                category=lobby_vc.category,
                overwrites=overwrites
            )
            
            # Record it in our tracker
            temp_channels[temp_vc.id] = lobby_vc.id
            
            # Move the user instantly
            await member.move_to(temp_vc)

    # Case 2: User leaves or switches out of a temporary voice channel
    if before.channel and before.channel.id in temp_channels:
        temp_vc = before.channel
        
        # Check if the channel is now completely empty
        if len(temp_vc.members) == 0:
            try:
                await temp_vc.delete()
                # Clean up our tracker
                temp_channels.pop(temp_vc.id, None)
            except discord.NotFound:
                pass  # Channel was already deleted

@bot.command()
async def sync(ctx):
    """Sync slash commands with Discord"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")

bot.run(token)