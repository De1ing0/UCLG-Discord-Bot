# UCLG-Discord-Bot
Very simple to set up and use bot for UCLG. Bot can set up small shops with manual check of payments and create parent voice chats.
# Getting Started
Before using make sure to create an app at Discord Developer Portal (https://discord.com/developers/)
## .env
Create .env file in the same directory as the python file with\
discord_token = token\
command_prefix = pdg!\
Channel and category ids can be copied via Discord UI with developer mode enabled.
## Sync command
After starting the bot use <prefix>sync to upload commands to Discord Client and restart it (Ctrl/Cmd + R). Then use server setup command via Discord UI with /. Rest of the commands can also be seen there