import discord
import os
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

token = os.getenv('discord_token')
main_channel_id = int(os.getenv('shop_channel_id'))
admin_user_id = int(os.getenv('admin_user_id'))
admin_channel_id = int(os.getenv('admin_channel_id'))
category_id = int(os.getenv('category_id'))
sort_code = os.getenv('sort_code')
account_number = os.getenv('account_number')
name_on_account = os.getenv('name_on_account')

bot = commands.Bot(command_prefix="pdg!", intents=discord.Intents.all())

class PaymentConfirmationView(discord.ui.View):
    def __init__(self, item_name: str):
        super().__init__(timeout=None)
        self.item_name = item_name

    @discord.ui.button(label="Payment Completed", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_payment_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        admin_channel = interaction.client.get_channel(admin_channel_id)
        if admin_channel:
            await admin_channel.send(
                f"🔔<@{admin_user_id}>, member {interaction.user.mention} has just paid for **{self.item_name}**.\n"
                f"Check their proof of payment here: {interaction.channel.mention}"
            )
            await interaction.response.send_message("Thank you for your purchase! Admin has been notified.", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("Error: Admin channel could not be found.", ephemeral=True)

class EmbedItemPage(discord.ui.View):
    def __init__(self, item_name: str):
        super().__init__() # Timeout is 180 seconds by default
        self.item_name = item_name

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
        payment_view = PaymentConfirmationView(self.item_name)
        await new_channel.send(content=user.mention, embed=welcome_embed, view=payment_view)

#@bot.event
#async def on_ready():  
#    print('Im ready epta')
#    channel = bot.get_channel(main_channel_id)
#    await channel.send("Im ready epta")

@bot.command()
async def create_item(ctx, price: float, name: str, image_url: str, *description: str):
    embed = discord.Embed(title=name, color=discord.Color.blue())
    embed.add_field(name="Price", value=f"£{price}", inline=False)
    embed.add_field(name="Description", value=' '.join(description), inline=False)
    embed.set_image(url=image_url)
    view = EmbedItemPage(item_name=name)
    await ctx.send(embed=embed, view=view)

bot.run(token)