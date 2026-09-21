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
prefix = os.getenv('command_prefix', 'pdg!')  # Default prefix if not set in .env

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


GUILD_SETTINGS_FILE = "guild_settings.json"

def save_guild_settings():
    # Save guild settings to JSON file
    with open(GUILD_SETTINGS_FILE, 'w') as f:
        json.dump(guild_settings, f, indent=2)

def load_guild_settings():
    # Load guild settings from JSON file
    global guild_settings
    if Path(GUILD_SETTINGS_FILE).exists():
        with open(GUILD_SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            guild_settings = {int(k): v for k, v in data.items()}

def get_guild_setting(guild_id, setting_key, default=None):
    # Get a specific setting for a guild
    if guild_id in guild_settings:
        return guild_settings[guild_id].get(setting_key, default)
    return default


# Basically used only for sync command and then Discord UI can be used for everything else
bot = commands.Bot(command_prefix=prefix, intents=discord.Intents.all())

lobby_channels = {}  # Maps lobby channel IDs to role IDs
temp_channels = {}   # Maps temporary channel IDs to their corresponding lobby channel IDs
guild_settings = {}  # Maps guild IDs to their settings


# Payment confirmation button
class PaymentConfirmationView(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.admin_user_id = admin_user_id

    @discord.ui.button(label="Payment Completed", style=discord.ButtonStyle.green, emoji="✅", custom_id="payment_completed")
    async def confirm_payment_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        admin_channel_id = get_guild_setting(guild_id, "admin_channel_id")
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


class VariantSelect(discord.ui.Select):
    def __init__(self, variants: dict):
        self.variants = variants
        options = [
            discord.SelectOption(label=name, description=f"View {name} variant")
            for name in list(variants.keys())[:25] # Hard cap at 25 options
        ]
        super().__init__(
            placeholder="🎨 Choose a colour or variant...", 
            min_values=1, 
            max_values=1, 
            options=options,
            row=0 # Places the dropdown above the Buy button
        )

    async def callback(self, interaction: discord.Interaction):
        # Get the URL associated with the selected variant name
        selected_name = self.values[0]
        url1, url2 = self.variants[selected_name]

        embeds = interaction.message.embeds
        embeds[0].set_image(url=url1)

        if url2:
            if len(embeds) > 1:
                embeds[1].set_image(url=url2)
            else:
                second_embed = discord.Embed(color=discord.Color.blue(), url=embeds[0].url)
                second_embed.set_image(url=url2)
                embeds.append(second_embed)
        elif len(embeds) > 1:
            embeds = [embeds[0]]
        await interaction.response.edit_message(embeds=embeds)


# Payment button
class EmbedItemPage(discord.ui.View):
    def __init__(self, item_name: str, admin_user_id: int, variants: dict = None):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.admin_user_id = admin_user_id

        if variants:
            self.add_item(VariantSelect(variants))

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.blurple, emoji="🛍️", custom_id="buy_button", row=1)
    async def my_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        guild_id = guild.id
        category_id = get_guild_setting(guild_id, "category_id")
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = guild.get_channel(category_id)
        safe_item_name = self.item_name.lower().replace(" ", "-")
        channel_name = f"≫・{user.name}'s-order-{safe_item_name}"
        new_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category)
        
        await interaction.followup.send(f"Order channel created: {new_channel.mention}", ephemeral=True)
        
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
    print('Updated 21.09.26 13:20')

    bot.add_view(EmbedItemPage("temp", 0))
    bot.add_view(PaymentConfirmationView("temp", 0))
    bot.add_view(VerificationButton())
    bot.add_view(VerificationForm(None))
    bot.add_view(DeliveryAddressView(None, "temp", 0))

    # Load saved lobby channels
    load_lobby_channels()
    load_guild_settings()

    # Verify all saved channels still exist in Discord
    channels_to_remove = []
    for channel_id in list(lobby_channels.keys()):
        channel = bot.get_channel(channel_id)
        if channel is None:
            # Channel was deleted, remove from tracking
            channels_to_remove.append(channel_id)
            print(f"Parent voice channel {channel_id} not found, removing from memory")
        # Remove deleted channels
        for channel_id in channels_to_remove:
            lobby_channels.pop(channel_id, None)
    # Save the cleaned-up list
    save_lobby_channels()
    
    print(f"Bot ready. Loaded {len(lobby_channels)} parent voice channels.")


# Create an item command in the shop channel
@app_commands.command(name="create_item", description="Create an item in shop channel")
@app_commands.checks.has_permissions(administrator=True)
async def create_item(
    interaction: discord.Interaction,
    admin_user: discord.User,
    shop_channel: discord.TextChannel,
    item_name: str,
    price: float,
    description: str,
    main_image_url: str,
    second_image_url: str = None,
    variants: str = None
):
    # Parse the input string: "Red|url1.png, Blue|url2.png"
    variant_dict = {}
    if variants:
        pairs = variants.split(',')
        for pair in pairs:
            parts = pair.split('|')
            if len(parts) >= 2:
                name = parts[0].strip()
                url1 = parts[1].strip()
                url2 = parts[2].strip() if len(parts) >= 3 else None
                variant_dict[name] = (url1, url2)
    gallery_url = f"https://item.local/{item_name.lower().replace(' ', '-')}"

    embed = discord.Embed(title=item_name, color=discord.Color.blue(), url=gallery_url)
    embed.add_field(name="Price", value=f"£{price}", inline=False)
    embed.add_field(name="Description", value=description, inline=False)
    embed.set_image(url=main_image_url)

    embeds = [embed]
    if second_image_url:
        second_embed = discord.Embed(color=discord.Color.blue(), url=gallery_url)
        second_embed.set_image(url=second_image_url)
        embeds.append(second_embed)

    view = EmbedItemPage(item_name=item_name, admin_user_id=admin_user.id, variants=variant_dict)

    try:
        await shop_channel.send(embeds=embeds, view=view)
        await interaction.response.send_message(f"Item posted to **{shop_channel.mention}**")
    except discord.Forbidden:
        await interaction.response.send_message(f"Bot doesn't have permission to send messages in **{shop_channel.mention}**.", ephemeral=True)
bot.tree.add_command(create_item)


# Create a parent voice channel for a certain role command
@app_commands.command(name="setup_vc", description="Create a parent voice channel for a role")
@app_commands.checks.has_permissions(administrator=True)
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

    vc_name = f"≫・create {role.name.lower()} vc"
    
    lobby_channel = await interaction.guild.create_voice_channel(
        name=vc_name,
        category=category,
        overwrites=overwrites
    )
    
    lobby_channels[lobby_channel.id] = role.id
    save_lobby_channels()
    await interaction.response.send_message(f"Created parent voice chat **{lobby_channel.mention}** in category **{category.name}** for role **{role.name}**.")
bot.tree.add_command(setup_vc)


# Verification button
class VerificationButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Membership", style=discord.ButtonStyle.green, emoji="✅", custom_id="verify_membership")
    async def verify_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        guild_id = guild.id
        
        # Get category from guild settings
        category_id = get_guild_setting(guild_id, "category_id")
        if not category_id:
            await interaction.followup.send(
                "Server not configured. Admin needs to run `/configure_bot` first.",
                ephemeral=False
            )
            return
        
        # Create private verification channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        
        verif_channel = await guild.create_text_channel(
            name=f"≫・{user.name}'s-verification",
            overwrites=overwrites,
            category=guild.get_channel(category_id)
        )
        
        await interaction.followup.send(f"Verification channel created: {verif_channel.mention}", ephemeral=True)
        
        # Send form to verification channel
        verif_embed = discord.Embed(
            title="Membership Verification",
            description="Please provide your full name so admin can verify your membership status.",
            color=discord.Color.blue()
        )
        verif_form = VerificationForm(verif_channel)
        await verif_channel.send(content=user.mention, embed=verif_embed, view=verif_form)

# Verification submition form
class VerificationForm(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Submit Full Name", style=discord.ButtonStyle.blurple, emoji="📝", custom_id="submit_verification")
    async def submit_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FullNameModal(self.channel))

class FullNameModal(discord.ui.Modal, title="Membership Verification"):
    full_name = discord.ui.TextInput(label="Full Name", placeholder="Oliver Sykes", required=True)

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        guild_id = interaction.guild.id
        
        # Get admin channel from guild settings
        admin_channel_id = get_guild_setting(guild_id, "admin_channel_id")
        if not admin_channel_id:
            await interaction.response.send_message(
                "Server not configured. Admin needs to run `/configure_bot` first.",
                ephemeral=False
            )
            return
        
        admin_channel = interaction.client.get_channel(admin_channel_id)
        
        if admin_channel:
            await admin_channel.send(
                f"**New Verification Request**\n"
                f"User: {user.mention}\n"
                f"Full Name: {self.full_name.value}\n"
                f"Verification Channel: {interaction.channel.mention}"
            )
        
        await interaction.response.send_message(
            "Your information has been submitted. Admin will verify your membership shortly.",
            ephemeral=True
        )

# Delivery address form create button
class DeliveryAddressModal(discord.ui.Modal, title="Delivery Address"):
    full_name = discord.ui.TextInput(
        label="Full Name",
        placeholder="Oliver Sykes",
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
        guild_id = interaction.guild.id
        
        sort_code = get_guild_setting(guild_id, "sort_code")
        account_number = get_guild_setting(guild_id, "account_number")
        name_on_account = get_guild_setting(guild_id, "name_on_account")
        
        # Save address in channel
        address_embed = discord.Embed(
            title="📦 Delivery Address",
            color=discord.Color.green()
        )
        address_embed.add_field(name="Name", value=self.full_name.value, inline=False)
        address_embed.add_field(name="Address", value=self.street_address.value, inline=False)
        if self.apartment.value:
            address_embed.add_field(name="Apartment/Suite", value=self.apartment.value, inline=False)
        address_embed.add_field(name="ZIP Code", value=self.zip_code.value, inline=False)
        
        address_message = await interaction.channel.send(embed=address_embed)
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
        await interaction.channel.send(embed=payment_embed, view=payment_view)
        
        await interaction.response.send_message("Address saved. Payment details sent to channel.", ephemeral=True)

# Create verification embed command in a given channel command
@app_commands.command(name="create_verif", description="Create a verification button in a channel")
@app_commands.checks.has_permissions(administrator=True)
async def create_verif(interaction: discord.Interaction, channel: discord.TextChannel):
    print(f"[CREATE_VERIF] interaction_id={interaction.id} user={interaction.user.id}")
    embed = discord.Embed(
        title="Membership Verification",
        description="Click the button below to verify your membership status.",
        color=discord.Color.gold()
    )
    view = VerificationButton()
    
    try:
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Verification button posted to **{channel.mention}**")
    except discord.Forbidden:
        await interaction.response.send_message(f"Bot doesn't have permission to send messages in **{channel.mention}**.", ephemeral=True)
bot.tree.add_command(create_verif)


# Check for already created parent voice channels in case of a restart/failure
@bot.event
async def on_voice_state_update(member, before, after):
    print(f"[VC EVENT] member={member.id} before={before.channel.id if before.channel else None} after={after.channel.id if after.channel else None} case1_match={after.channel.id in lobby_channels if after.channel else False} case2_match={before.channel.id in temp_channels if before.channel else False} lobby_keys={list(lobby_channels.keys())}")
    # Case 1: User joins the Parent voice channel
    if after.channel and after.channel.id in lobby_channels:
        lobby_vc = after.channel
        allowed_role_id = lobby_channels[lobby_vc.id]
        role = member.guild.get_role(allowed_role_id)
        
        if not role:
            return

        # Overwrites for the temporary channel: the role and the creator can access it
        # regardless of whether the creator actually holds the role
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            role: discord.PermissionOverwrite(view_channel=True, connect=True),
            member: discord.PermissionOverwrite(view_channel=True, connect=True),
            member.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, move_members=True, manage_channels=True)
        }

        temp_name = f"≫・{member.name}'s {role.name.lower()} vc"

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


@app_commands.command(name="configure_bot", description="Configure bot settings for this server")
@app_commands.checks.has_permissions(administrator=True)
async def configure_bot(
    interaction: discord.Interaction,
    shop_channel: discord.TextChannel,
    admin_channel: discord.TextChannel,
    category: discord.CategoryChannel,
):
    # Admin command to configure bot per server
    guild_id = interaction.guild.id
    
    # Create or update settings
    if guild_id not in guild_settings:
        guild_settings[guild_id] = {}
    
    guild_settings[guild_id] = {
        "shop_channel_id": shop_channel.id,
        "admin_channel_id": admin_channel.id,
        "category_id": category.id,
    }
    
    save_guild_settings()
    
    await interaction.response.send_message(
        f"Bot configured for this server\n"
        f"Shop Channel: {shop_channel.mention}\n"
        f"Admin Channel: {admin_channel.mention}\n"
        f"Category: {category.mention}",
        ephemeral=False
    )
bot.tree.add_command(configure_bot)

@app_commands.command(name="configure_payment", description="Set payment details for this server")
@app_commands.checks.has_permissions(administrator=True)
async def configure_payment(
    interaction: discord.Interaction,
    sort_code: str,
    account_number: str,
    name_on_account: str
):
    # Admin command to configure payment details per server
    guild_id = interaction.guild.id
    
    # Update existing settings or create new ones
    if guild_id not in guild_settings:
        guild_settings[guild_id] = {}
    
    guild_settings[guild_id].update({
        "sort_code": sort_code,
        "account_number": account_number,
        "name_on_account": name_on_account
    })
    
    save_guild_settings()
    
    await interaction.response.send_message(
        f"Payment details configured\n"
        f"Sort Code: {sort_code}\n"
        f"Account Number: {account_number}\n"
        f"Name on Account: {name_on_account}",
        ephemeral=False
    )
bot.tree.add_command(configure_payment)

# Sync slash commands with Discord client command
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    # Sync slash commands with Discord client
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")


# Initialisation
bot.run(token)