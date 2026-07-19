import discord
import os
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
import json
from pathlib import Path

# Get information from .env file
load_dotenv()
token = os.getenv('discord_token')
main_channel_id = int(os.getenv('shop_channel_id'))
admin_channel_id = int(os.getenv('admin_channel_id'))
category_id = int(os.getenv('category_id'))
sort_code = os.getenv('sort_code')
account_number = os.getenv('account_number')
name_on_account = os.getenv('name_on_account')
# Get information from lobby_channels.json file if it exists
LOBBY_DATA_FILE = "lobby_channels.json"
def save_lobby_channels():
    # Save lobby channels to JSON file in case of a failure or restart
    with open(LOBBY_DATA_FILE, 'w') as f:
        json.dump(lobby_channels, f, indent=2)
def load_lobby_channels():
    # Load lobby channels from JSON file if it exists to restore state after a bot restart
    global lobby_channels
    if Path(LOBBY_DATA_FILE).exists():
        with open(LOBBY_DATA_FILE, 'r') as f:
            lobby_channels = json.load(f)
            # Convert string keys back to integers (JSON keys are always strings)
            lobby_channels = {int(k): v for k, v in lobby_channels.items()}

# Basically used only for sync command and then Discord UI can be used for everything else
bot = commands.Bot(command_prefix="pdg!", intents=discord.Intents.all())

lobby_channels = {}  # Maps lobby channel IDs to role IDs
temp_channels = {}   # Maps temporary channel IDs to their corresponding lobby channel IDs


# Payment confirmation button
class PaymentConfirmationView(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Payment Completed", style=discord.ButtonStyle.green, emoji="✅", custom_id="payment_completed")
    async def confirm_payment_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin_channel = interaction.client.get_channel(admin_channel_id)
        if admin_channel:
            await admin_channel.send(
                f"<@{self.admin_user_id}>, member {interaction.user.mention} has just paid for **{self.item_name}**.\n"
                f"Check their proof of payment here: {interaction.channel.mention}"
            )
            await interaction.response.send_message("Thank you for your purchase! Admin has been notified.", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("Error: Admin channel could not be found.", ephemeral=True)

# Delivery address input form
class DeliveryAddressView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, item_name: str, admin_user_id: int):
        super().__init__(timeout=None)
        self.channel = channel
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Add Delivery Address", style=discord.ButtonStyle.blurple, emoji="📍", custom_id="add_delivery_address")
    async def delivery_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = DeliveryAddressModal(self.channel, self.item_name, self.admin_user_id)
        await interaction.response.send_modal(modal)

# Payment button
class EmbedItemPage(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.blurple, emoji="🛍️", custom_id="buy_button")
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
        
        await interaction.response.send_message(f"Order channel created: {new_channel.mention}", ephemeral=True)
        
        # Show delivery address form embed with button
        delivery_embed = discord.Embed(
            title=f"🛍️ Order for {self.item_name}",
            description="Please provide your delivery address to continue.",
            color=discord.Color.blue()
        )
        delivery_view = DeliveryAddressView(new_channel, self.item_name, self.admin_user_id)
        await new_channel.send(content=user.mention, embed=delivery_embed, view=delivery_view)


# Startup + debug notifications
@bot.event
async def on_ready():  
    global lobby_channels
    print('Bot online')

    bot.add_view(EmbedItemPage("temp", 0))
    bot.add_view(PaymentConfirmationView("temp", 0))
    bot.add_view(VerificationButton())
    bot.add_view(VerificationForm(None))
    bot.add_view(DeliveryAddressView(None, "temp", 0))

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
                print(f"Parent voice channel {channel_id} not found, removing from memory")
        # Remove deleted channels
        for channel_id in channels_to_remove:
            lobby_channels.pop(channel_id, None)
    # Save the cleaned-up list
    save_lobby_channels()
    
    channel = bot.get_channel(main_channel_id)
    if channel:
        await channel.send(f"Bot online. Loaded {len(lobby_channels)} parent voice channels.")
        for vc in lobby_channels.keys():
            await channel.send(f"Parent voice channel ID: {vc} is being tracked.")


# Create an item command in the shop channel
@app_commands.command(name="create_item", description="Create an item in shop channel")
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


# Create a parent voice channel for a certain role command
@app_commands.command(name="setup_vc", description="Create a parent voice channel for a role")
@app_commands.checks.has_permissions(manage_channels=True)
async def setup_vc(
    interaction: discord.Interaction,
    role: discord.Role,
    category: discord.CategoryChannel
):
    # Creates a parent voice channel that is only visible/joinable by a specific role
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


# Verification button
class VerificationButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Membership", style=discord.ButtonStyle.green, emoji="✅", custom_id="verify_membership")
    async def verify_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild = interaction.guild
        
        # Create private verification channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        
        verif_channel = await guild.create_text_channel(
            name=f"{user.name}'s-verification",
            overwrites=overwrites,
            category=guild.get_channel(category_id)
        )
        
        await interaction.response.send_message(f"Verification channel created: {verif_channel.mention}", ephemeral=True)
        
        # Send form to verification channel
        verif_embed = discord.Embed(
            title="Membership Verification",
            description="Please provide your name and surname so admin can verify your membership status.",
            color=discord.Color.blue()
        )
        verif_form = VerificationForm(verif_channel)
        await verif_channel.send(content=user.mention, embed=verif_embed, view=verif_form)

# Verification submition form
class VerificationForm(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Submit Name & Surname", style=discord.ButtonStyle.blurple, emoji="📝", custom_id="submit_verification")
    async def submit_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NameSurnameModal(self.channel))

class NameSurnameModal(discord.ui.Modal, title="Membership Verification"):
    name = discord.ui.TextInput(label="First Name", placeholder="Enter your first name", required=True)
    surname = discord.ui.TextInput(label="Last Name", placeholder="Enter your last name", required=True)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        admin_channel = interaction.client.get_channel(admin_channel_id)
        
        if admin_channel:
            await admin_channel.send(
                f"**New Verification Request**\n"
                f"User: {user.mention}\n"
                f"Name: {self.name.value}\n"
                f"Surname: {self.surname.value}\n"
                f"Verification Channel: {self.channel.mention}"
            )
        
        await interaction.response.send_message(
            "Your information has been submitted. Admin will verify your membership shortly.",
            ephemeral=True
        )

# Delivery address form create button
class DeliveryAddressModal(discord.ui.Modal, title="Delivery Address"):
    first_name = discord.ui.TextInput(
        label="First Name",
        placeholder="John",
        required=True
    )
    last_name = discord.ui.TextInput(
        label="Last Name",
        placeholder="Doe",
        required=True
    )
    street_address = discord.ui.TextInput(
        label="Address",
        placeholder="27-28 Gordon Sq",
        required=True,
        style=discord.TextStyle.paragraph
    )
    apartment = discord.ui.TextInput(
        label="Apartment, Suite, Etc.",
        placeholder="Apartment, Suite, Floor, etc. (Leave blank if not applicable)",
        required=False
    )
    zip_code = discord.ui.TextInput(
        label="ZIP Code",
        placeholder="WC1H 0AW",
        required=True
    )

    def __init__(self, channel: discord.TextChannel, item_name: str, admin_user_id: int):
        super().__init__()
        self.channel = channel
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        
        # Format address
        apartment_line = f"\n{self.apartment.value}" if self.apartment.value else ""
        full_address = f"{self.first_name.value} {self.last_name.value}\n{self.street_address.value}{apartment_line}\n{self.zip_code.value}"
        
        # Save address in channel
        address_embed = discord.Embed(
            title="📦 Delivery Address",
            color=discord.Color.green()
        )
        address_embed.add_field(name="Name", value=f"{self.first_name.value} {self.last_name.value}", inline=False)
        address_embed.add_field(name="Address", value=self.street_address.value, inline=False)
        if self.apartment.value:
            address_embed.add_field(name="Apartment/Suite", value=self.apartment.value, inline=False)
        address_embed.add_field(name="ZIP Code", value=self.zip_code.value, inline=False)
        
        address_message = await self.channel.send(embed=address_embed)
        await address_message.pin()
        
        # Send payment button embed
        payment_embed = discord.Embed(
            title=f"💸 Payment for {self.item_name}",
            description=(
                "Your delivery address has been saved. Now proceed with payment.\n\n"
                f"**Sort code:** {sort_code}\n"
                f"**Account number:** {account_number}\n"
                f"**Name**: {name_on_account}\n\n"
                "Once paid, upload proof of payment and press the button below."
            ),
            color=discord.Color.gold()
        )
        payment_view = PaymentConfirmationView(self.item_name, self.admin_user_id)
        await self.channel.send(embed=payment_embed, view=payment_view)
        
        await interaction.response.send_message("✅ Address saved! Payment details sent to channel.", ephemeral=True)

# Create verification embed command in a given channel command
@app_commands.command(name="create_verif", description="Create a verification button in a channel")
async def create_verif(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="Membership Verification",
        description="Click the button below to verify your membership status.",
        color=discord.Color.gold()
    )
    view = VerificationButton()
    
    try:
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Verification button posted to {channel.mention}", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"Bot doesn't have permission to send messages in {channel.mention}.", ephemeral=True)
bot.tree.add_command(create_verif)


# Check for already created parent voice channels in case of a restart/failure
@bot.event
async def on_voice_state_update(member, before, after):
    # Case 1: User joins the Parent voice channel
    if after.channel and after.channel.id in lobby_channels:
        lobby_vc = after.channel
        allowed_role_id = lobby_channels[lobby_vc.id]
        role = member.guild.get_role(allowed_role_id)
        
        if not role:
            return

        # Double check if the user actually has the role
        if role in member.roles:
            # Overwrites for the temporary channel so only that role can access it
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
                role: discord.PermissionOverwrite(view_channel=True, connect=True),
                member.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, move_members=True, manage_channels=True)
            }
            
            temp_name = f"{member.name}'s {role.name.lower()} vc"
            
            # Create the temporary channel in the same category as the parent channel
            temp_vc = await member.guild.create_voice_channel(
                name=temp_name,
                category=lobby_vc.category,
                overwrites=overwrites
            )

            # Record it in tracker
            temp_channels[temp_vc.id] = lobby_vc.id
            # Move the user to the created temporary voice channel
            await member.move_to(temp_vc)

    # Case 2: User leaves a temporary voice channel
    if before.channel and before.channel.id in temp_channels:
        temp_vc = before.channel
        # Check if the channel is now completely empty
        if len(temp_vc.members) == 0:
            try:
                await temp_vc.delete()
                # Clean up tracker
                temp_channels.pop(temp_vc.id, None)
            except discord.NotFound:
                pass  # Channel was already deleted


# Sync slash commands with Discord client command
@bot.command()
async def sync(ctx):
    # Sync slash commands with Discord client
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")


# Initialisation
bot.run(token)