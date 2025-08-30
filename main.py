# main.py
import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime
from duel_manager import DuelManager
from PIL import Image, ImageDraw, ImageFont
import io

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)
duel_manager = DuelManager()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name="Pokemon Duels | !help"))

@bot.command(name='duel')
async def duel_start(ctx, opponent: discord.Member, rounds: int = 3, duel_type: str = "normal"):
    """Start a duel with another player"""
    await duel_manager.start_duel(ctx, [opponent], rounds, duel_type)

@bot.command(name='tripleduel')
async def triple_duel_start(ctx, opponent1: discord.Member, opponent2: discord.Member, rounds: int = 3, duel_type: str = "normal"):
    """Start a triple duel with two other players"""
    await duel_manager.start_duel(ctx, [opponent1, opponent2], rounds, duel_type)

@bot.command(name='history')
async def duel_history(ctx, player: discord.Member = None):
    """Show duel history for a player"""
    if player is None:
        player = ctx.author
    
    history = duel_manager.get_player_history(player.id)
    
    if not history:
        if player == ctx.author:
            await ctx.send("You don't have any duel history yet!")
        else:
            await ctx.send(f"{player.name} doesn't have any duel history yet!")
        return
    
    # Sort history by timestamp (newest first)
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Get only the last 5 duels
    recent_history = history[:5]
    
    # Create embed
    embed = discord.Embed(
        title=f"⚔️ Duel History for {player.name}",
        color=discord.Color.blue()
    )
    
    wins = 0
    losses = 0
    
    for duel in recent_history:
        is_triple = duel.get('is_triple', False)
        
        if is_triple:
            # Handle triple duel history
            is_player = str(player.id) in [str(duel['player1']), str(duel['player2']), str(duel['player3'])]
            if not is_player:
                continue
                
            # Determine if player won
            player_won = str(player.id) == str(duel['winner'])
            if player_won:
                wins += 1
                result = "🏆 WIN"
                color = 0x00ff00
            else:
                losses += 1
                result = "💥 LOSS"
                color = 0xff0000
            
            # Get opponent names
            opponent_names = []
            for pid in ['player1', 'player2', 'player3']:
                if str(duel[pid]) != str(player.id):
                    opponent_names.append(duel[f'{pid}_name'])
            
            # Format score
            score_parts = []
            for pid in ['player1', 'player2', 'player3']:
                if str(duel[pid]) == str(player.id):
                    score_parts.insert(0, str(duel[f'score{pid[-1]}']))
                else:
                    score_parts.append(str(duel[f'score{pid[-1]}']))
            
            score = "-".join(score_parts)
        else:
            # Handle regular duel history
            is_player1 = str(player.id) == str(duel['player1'])
            opponent_id = duel['player2'] if is_player1 else duel['player1']
            opponent_name = duel['player2_name'] if is_player1 else duel['player1_name']
            
            # Determine if player won
            player_won = str(player.id) == str(duel['winner'])
            if player_won:
                wins += 1
                result = "🏆 WIN"
                color = 0x00ff00
            else:
                losses += 1
                result = "💥 LOSS"
                color = 0xff0000
            
            # Format score
            if is_player1:
                score = f"{duel['score1']}-{duel['score2']}"
            else:
                score = f"{duel['score2']}-{duel['score1']}"
            
            opponent_names = [opponent_name]
        
        # Format timestamp
        duel_time = datetime.fromisoformat(duel['timestamp']).strftime("%Y-%m-%d %H:%M")
        
        embed.add_field(
            name=f"{result} vs {', '.join(opponent_names)}",
            value=f"Score: {score} | Type: {duel['duel_type']} | {duel_time}",
            inline=False
        )
    
    # Add win/loss stats
    total_duels = wins + losses
    win_rate = (wins / total_duels * 100) if total_duels > 0 else 0
    
    embed.set_footer(text=f"Record: {wins}-{losses} | Win Rate: {win_rate:.1f}%")
    
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def player_stats(ctx, player: discord.Member = None):
    """Show player stats with a cool image"""
    if player is None:
        player = ctx.author
    
    history = duel_manager.get_player_history(player.id)
    
    if not history:
        await ctx.send(f"{player.name} doesn't have any duel stats yet!")
        return
    
    # Calculate stats
    wins = 0
    losses = 0
    win_streak = 0
    current_streak = 0
    
    # Sort history by timestamp (oldest first)
    history.sort(key=lambda x: x['timestamp'])
    
    for duel in history:
        is_triple = duel.get('is_triple', False)
        
        if is_triple:
            # Triple duel
            player_won = str(player.id) == str(duel['winner'])
        else:
            # Regular duel
            player_won = str(player.id) == str(duel['winner'])
        
        if player_won:
            wins += 1
            current_streak += 1
            win_streak = max(win_streak, current_streak)
        else:
            losses += 1
            current_streak = 0
    
    total_duels = wins + losses
    win_rate = (wins / total_duels * 100) if total_duels > 0 else 0
    
    # Create stats image
    try:
        image = await create_stats_image(player, wins, losses, win_rate, win_streak)
        file = discord.File(image, filename="stats.png")
        await ctx.send(file=file)
    except Exception as e:
        print(f"Error creating stats image: {e}")
        # Fallback to embed if image creation fails
        embed = discord.Embed(
            title=f"📊 {player.name}'s Duel Stats",
            color=discord.Color.blue()
        )
        embed.add_field(name="Wins", value=str(wins), inline=True)
        embed.add_field(name="Losses", value=str(losses), inline=True)
        embed.add_field(name="W/L Ratio", value=f"{win_rate:.1f}%", inline=True)
        embed.add_field(name="Win Streak", value=str(win_streak), inline=True)
        embed.add_field(name="Total Duels", value=str(total_duels), inline=True)
        await ctx.send(embed=embed)

async def create_stats_image(player, wins, losses, win_rate, win_streak):
    """Create a stats image similar to the provided design"""
    # Create image with dark background
    width, height = 600, 400
    img = Image.new('RGB', (width, height), color=(40, 40, 60))
    draw = ImageDraw.Draw(img)
    
    try:
        # Try to load fonts
        title_font = ImageFont.truetype("arialbd.ttf", 24)
        header_font = ImageFont.truetype("arialbd.ttf", 20)
        stat_font = ImageFont.truetype("arialbd.ttf", 18)
        small_font = ImageFont.truetype("arial.ttf", 14)
    except:
        # Fallback to default fonts
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        stat_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Draw title
    draw.text((20, 20), f"{player.name}'s Duel Stats", font=title_font, fill=(255, 255, 255))
    
    # Draw divider line
    draw.line([(20, 60), (width - 20, 60)], fill=(100, 100, 150), width=2)
    
    # Draw stats in a table format similar to the reference image
    y_position = 80
    
    # Wins
    draw.text((50, y_position), "Wins", font=header_font, fill=(200, 200, 200))
    draw.text((250, y_position), str(wins), font=stat_font, fill=(255, 255, 255))
    y_position += 40
    
    # Losses
    draw.text((50, y_position), "Losses", font=header_font, fill=(200, 200, 200))
    draw.text((250, y_position), str(losses), font=stat_font, fill=(255, 255, 255))
    y_position += 40
    
    # W/L Ratio
    draw.text((50, y_position), "W/L Ratio", font=header_font, fill=(200, 200, 200))
    draw.text((250, y_position), f"{win_rate:.1f}%", font=stat_font, fill=(255, 255, 255))
    y_position += 40
    
    # Win Streak
    draw.text((50, y_position), "Win Streak", font=header_font, fill=(200, 200, 200))
    draw.text((250, y_position), str(win_streak), font=stat_font, fill=(255, 255, 255))
    y_position += 40
    
    # Total Duels
    draw.text((50, y_position), "Total Duels", font=header_font, fill=(200, 200, 200))
    draw.text((250, y_position), str(wins + losses), font=stat_font, fill=(255, 255, 255))
    
    # Draw another divider line
    draw.line([(20, height - 80), (width - 20, height - 80)], fill=(100, 100, 150), width=2)
    
    # Draw footer with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.text((20, height - 50), f"Generated: {timestamp}", font=small_font, fill=(150, 150, 150))
    
    # Save image to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes

@bot.command(name='leaderboard')
async def duel_leaderboard(ctx):
    """Show the top duelists"""
    # This would require additional functionality in DuelManager
    # For now, let's just show a placeholder
    embed = discord.Embed(
        title="🏆 Duel Leaderboard",
        description="Leaderboard functionality coming soon!",
        color=discord.Color.gold()
    )
    
    # Placeholder top players
    embed.add_field(name="1. Trainer Red", value="15-2 (88.2%)", inline=False)
    embed.add_field(name="2. Trainer Blue", value="12-5 (70.6%)", inline=False)
    embed.add_field(name="3. Trainer Green", value="10-3 (76.9%)", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='forms')
async def show_forms(ctx):
    """Show available Pokemon forms"""
    from utils import special_forms
    
    embed = discord.Embed(
        title="Available Pokemon Forms",
        description="Here are some of the special forms you can use:",
        color=discord.Color.blue()
    )
    
    forms_list = [
        "Deoxys (Normal, Attack, Defense, Speed)",
        "Giratina (Altered, Origin)",
        "Shaymin (Land, Sky)",
        "Castform (Normal, Sunny, Rainy, Snowy)",
        "Darmanitan (Standard, Zen)",
        "Tornadus/Thundurus/Landorus (Incarnate, Therian)",
        "Keldeo (Ordinary, Resolute)",
        "Meloetta (Aria, Pirouette)",
        "Aegislash (Shield, Blade)",
        "Lycanroc (Midday, Midnight, Dusk)",
        "Toxtricity (Amped, Low Key)",
        "Indeedee (Male, Female)",
        "Urshifu (Single Strike, Rapid Strike)",
        "Calyrex (Ice Rider, Shadow Rider)"
    ]
    
    for form in forms_list:
        embed.add_field(name="\u200b", value=form, inline=False)
    
    embed.set_footer(text="Use the form name after the Pokemon name (e.g., 'Deoxys Attack')")
    
    await ctx.send(embed=embed)

@bot.command(name='dueltypes')
async def show_duel_types(ctx):
    """Show available duel types"""
    embed = discord.Embed(
        title="Available Duel Types",
        description="Choose a duel type when starting a duel:",
        color=discord.Color.blue()
    )
    
    duel_types = [
        "**1st-evolution** - Only Pokemon that are first in their evolution line",
        "**2nd-evolution** - Only Pokemon that are second in their evolution line", 
        "**normal** - All Pokemon except legendaries",
        "**legendaries** - Only legendary Pokemon"
    ]
    
    for duel_type in duel_types:
        embed.add_field(name="\u200b", value=duel_type, inline=False)
    
    embed.set_footer(text="Example: !duel @opponent 5 legendaries")
    
    await ctx.send(embed=embed)

@bot.command(name='howto')
async def how_to_play(ctx):
    """Instructions on how to use the bot"""
    embed = discord.Embed(
        title="Pokemon 1v1 Duel Bot",
        description="Battle against other players using Pokemon stats!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Starting a Duel",
        value="Use `!duel @opponent rounds duel-type`\nExample: `!duel @JohnDoe 5 legendaries`\n\nFor triple duels: `!tripleduel @opponent1 @opponent2 rounds duel-type`\nExample: `!tripleduel @JohnDoe @JaneDoe 5 normal`",
        inline=False
    )
    
    embed.add_field(
        name="Duel Types",
        value="Use `!dueltypes` to see available duel types",
        inline=False
    )
    
    embed.add_field(
        name="Checking Stats",
        value="Use `!stats @username` to see duel stats with image\nUse `!stats` to see your own stats",
        inline=False
    )
    
    embed.add_field(
        name="Checking History",
        value="Use `!history @username` to see duel history\nUse `!history` to see your own history",
        inline=False
    )
    
    embed.add_field(
        name="Leaderboard",
        value="Use `!leaderboard` to see top duelists",
        inline=False
    )
    
    embed.add_field(
        name="How it Works",
        value="1. A private channel will be created for your duel\n"
              "2. All players react with ✅ when ready\n"
              "3. When prompted, each player sends a Pokemon name (hidden from opponents)\n"
              "4. The bot will compare average base stats\n"
              "5. The Pokemon with higher stats wins the round\n"
              "6. First to win the majority of rounds wins the duel!",
        inline=False
    )
    
    embed.add_field(
        name="Special Forms",
        value="Use `!forms` to see available Pokemon forms like Deoxys Attack, Giratina Origin, etc.",
        inline=False
    )
    
    embed.add_field(
        name="Note",
        value="Completed duel channels are locked and preserved for viewing",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.event
async def on_reaction_add(reaction, user):
    """Check if all players are ready"""
    if user.bot:
        return
    await duel_manager.handle_reaction(reaction, user)

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # Check if message is in a duel channel
    if await duel_manager.handle_message(message):
        await bot.process_commands(message)
        return
    
    await bot.process_commands(message)

# Run the bot
bot.run('BOT-TOKEN')