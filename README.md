# UCLG-Discord-Bot
Very simple to set up and use bot for UCLG. Bot can set up small shops with manual check of payments and create parent voice chats.
# Getting Started
Before using make sure to create an app at Discord Developer Portal (https://discord.com/developers/)
## .env
Create .env file in the same directory as the python file with\
discord_token = token\
shop_channel_id = 00000000000000000\
admin_channel_id = 00000000000000000\
category_id = 00000000000000000\
sort_code = 00-00-00\
account_number = 00000000\
name_on_account = Oliver Sykes\
command_prefix = pdg!\
Channel and category ids can be copied via Discord UI with developer mode enabled.
## Sync command
After starting the bot use <prefix>sync to upload commands to Discord Client and restart it (Ctrl/Cmd + R). Rest of the commands can be used via Discourd UI with /