# duel_manager.py
import discord
from discord.ext import commands
import asyncio
import aiohttp
import time
import json
import os
import hashlib
from datetime import datetime
from pokemon_api import get_pokemon_data, is_legendary, get_evolution_stage
from image_generator import create_pokemon_image, create_vs_image, calculate_battle_score, create_triple_vs_image

class Duel:
    def __init__(self, players, rounds, channel, duel_type="normal"):
        self.players = players  # List of players (2 or 3)
        self.rounds = rounds
        self.channel = channel
        self.duel_type = duel_type
        self.scores = {player.id: 0 for player in players}
        self.current_round = 0
        self.ready_status = {player.id: False for player in players}
        self.pokemon = {player.id: None for player in players}
        self.ready_message = None
        self.countdown_active = False
        self.selection_phase = False
        self.used_pokemon = set()  # Track used Pokemon to prevent reuse
        self.duel_ended = False  # Track if duel has ended
        self.last_selection_time = 0
        self.selection_cooldown = 3  # seconds between selections
        self.waiting_for_selection = False  # Track if we're waiting for selections
        self.round_history = []  # Track round history for summary
        self.is_triple_duel = len(players) == 3  # Flag for 3-player duels

class DuelManager:
    def __init__(self):
        self.active_duels = {}
        self.completed_duels = {}
        self.duel_history_file = "duel_history.json"
        self.duel_history = self.load_duel_history()
    
    def load_duel_history(self):
        """Load duel history from JSON file"""
        if os.path.exists(self.duel_history_file):
            try:
                with open(self.duel_history_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_duel_history(self):
        """Save duel history to JSON file"""
        with open(self.duel_history_file, 'w') as f:
            json.dump(self.duel_history, f, indent=2)
    
    def add_to_history(self, duel, winner_id, losers):
        """Add a completed duel to history"""
        timestamp = datetime.now().isoformat()
        
        # For 3-player duels, we need to handle the structure differently
        if duel.is_triple_duel:
            player1, player2, player3 = duel.players
            duel_record = {
                "timestamp": timestamp,
                "player1": player1.id,
                "player2": player2.id,
                "player3": player3.id,
                "player1_name": player1.name,
                "player2_name": player2.name,
                "player3_name": player3.name,
                "score1": duel.scores[player1.id],
                "score2": duel.scores[player2.id],
                "score3": duel.scores[player3.id],
                "rounds": duel.rounds,
                "duel_type": duel.duel_type,
                "winner": winner_id,
                "losers": [loser.id for loser in losers],
                "is_triple": True
            }
        else:
            player1, player2 = duel.players
            duel_record = {
                "timestamp": timestamp,
                "player1": player1.id,
                "player2": player2.id,
                "player1_name": player1.name,
                "player2_name": player2.name,
                "score1": duel.scores[player1.id],
                "score2": duel.scores[player2.id],
                "rounds": duel.rounds,
                "duel_type": duel.duel_type,
                "winner": winner_id,
                "loser": losers[0].id if losers else None,
                "is_triple": False
            }
        
        # Add to each player's history
        for player in duel.players:
            if str(player.id) not in self.duel_history:
                self.duel_history[str(player.id)] = []
            self.duel_history[str(player.id)].append(duel_record)
        
        # Keep only the last 20 duels per player
        for player in duel.players:
            player_id = str(player.id)
            if len(self.duel_history[player_id]) > 20:
                self.duel_history[player_id] = self.duel_history[player_id][-20:]
        
        self.save_duel_history()
    
    def get_player_history(self, player_id):
        """Get duel history for a player"""
        return self.duel_history.get(str(player_id), [])
    
    async def start_duel(self, ctx, opponents, rounds: int = 3, duel_type: str = "normal"):
        """Start a duel with one or two opponents"""
        if rounds not in [3, 5, 7]:
            await ctx.send("Please specify a valid number of rounds: 3, 5, or 7")
            return
        
        if duel_type not in ["1st-evolution", "2nd-evolution", "normal", "legendaries"]:
            await ctx.send("Please specify a valid duel type: 1st-evolution, 2nd-evolution, normal, or legendaries")
            return
        
        # Check if any opponent is the author
        if ctx.author in opponents:
            await ctx.send("You can't duel yourself!")
            return
        
        # Check if any opponent is a bot
        for opponent in opponents:
            if opponent.bot:
                await ctx.send("You can't duel a bot!")
                return
        
        # Check for duplicate opponents
        if len(opponents) != len(set(opponents)):
            await ctx.send("You can't specify the same opponent multiple times!")
            return
        
        # Create player list
        players = [ctx.author] + opponents
        is_triple_duel = len(players) == 3
        
        # Create a new channel for the duel
        guild = ctx.guild
        category = discord.utils.get(guild.categories, name="Pokemon Duels")
        
        if not category:
            # Create category if it doesn't exist
            category = await guild.create_category("Pokemon Duels")
        
        # Create channel
        if is_triple_duel:
            channel_name = f"triple-duel-{ctx.author.name}-vs-{opponents[0].name}-vs-{opponents[1].name}"
        else:
            channel_name = f"duel-{ctx.author.name}-vs-{opponents[0].name}"
        
        channel = await guild.create_text_channel(channel_name, category=category)
        
        # Set permissions
        await channel.set_permissions(guild.default_role, read_messages=False)
        for player in players:
            await channel.set_permissions(player, read_messages=True, send_messages=True)
        
        # Create duel object
        duel = Duel(players, rounds, channel, duel_type)
        self.active_duels[channel.id] = duel
        
        # Send welcome message with embed
        embed = discord.Embed(
            title="🎉 Pokemon 1v1 Duel 🎉" if not is_triple_duel else "🎉 Pokemon Triple Duel 🎉",
            color=discord.Color.gold()
        )
        
        if is_triple_duel:
            embed.add_field(name="Players", value=f"{ctx.author.mention} vs {opponents[0].mention} vs {opponents[1].mention}", inline=False)
        else:
            embed.add_field(name="Players", value=f"{ctx.author.mention} vs {opponents[0].mention}", inline=False)
            
        embed.add_field(name="Format", value=f"Best of {rounds} rounds", inline=False)
        embed.add_field(name="Duel Type", value=duel_type.replace("-", " ").title(), inline=False)
        embed.add_field(
            name="How to Play", 
            value="1. All players react with ✅ when ready\n2. When prompted, send a Pokemon name (hidden from opponents)\n3. The bot will calculate battle scores based on type advantages\n4. Highest battle score wins the round!", 
            inline=False
        )
        embed.set_footer(text="Pokemon selections are hidden until all players have chosen")
        
        await channel.send(embed=embed)
        
        # Send ready message with reaction
        duel.ready_message = await channel.send("**READY?**")
        await duel.ready_message.add_reaction('✅')
        
        # Notify players in original channel
        await ctx.send(f"Your duel has started! Head over to {channel.mention}")
    
    async def handle_reaction(self, reaction, user):
        """Check if all players are ready"""
        # Check if this is a ready message in a duel channel
        if reaction.message.channel.id in self.active_duels and reaction.emoji == '✅':
            duel = self.active_duels[reaction.message.channel.id]
            
            # Check if duel has ended
            if duel.duel_ended:
                return
            
            # Check if user is a participant
            if user.id not in duel.ready_status:
                return  # Not a duel participant
            
            duel.ready_status[user.id] = True
            
            # Update ready message
            ready_text = "**READY?**\n\n"
            for player in duel.players:
                ready_text += f"{player.name}: {'✅' if duel.ready_status[player.id] else '❌'}\n"
            
            await duel.ready_message.edit(content=ready_text)
            
            # If all players are ready, start the countdown
            if all(duel.ready_status.values()) and not duel.countdown_active:
                duel.countdown_active = True
                countdown_msg = await reaction.message.channel.send("All players are ready! Starting in...")
                
                for i in range(3, 0, -1):
                    countdown_msg = await reaction.message.channel.send(f"**{i}...**")
                    await asyncio.sleep(1)
                
                go_msg = await reaction.message.channel.send(f"**GO!**\n\nAll players, please send your Pokemon's name!\n\n**Duel Type: {duel.duel_type.replace('-', ' ').title()}**\nYour selection will be hidden from your opponents.")
                
                # Start selection phase
                duel.selection_phase = True
                duel.ready_status = {player.id: False for player in duel.players}
                duel.waiting_for_selection = True
    
    async def send_ephemeral_message(self, channel, target, message):
        """Send an ephemeral message that only the target can see"""
        try:
            # Use Discord's built-in ephemeral messages
            await channel.send(f"{target.mention} {message}", delete_after=10)
        except:
            # Fallback to regular message if ephemeral fails
            await channel.send(f"{target.mention} {message}", delete_after=10)
    
    async def validate_pokemon_for_duel(self, pokemon_data, duel_type, used_pokemon, author, opponents):
        """Validate if a Pokemon is allowed for the current duel type"""
        pokemon_name = pokemon_data['name'].lower()
        
        # Check if Pokemon was already used
        if pokemon_name in used_pokemon:
            return False, "This Pokemon has already been used in this duel!"
        
        # Get the base form name for legendary checks
        base_name = pokemon_data['api_name'].split('-')[0]  # Extract base name from API name
        
        # Check based on duel type
        if duel_type == "1st-evolution":
            evolution_stage = await get_evolution_stage(pokemon_data['api_name'])
            if evolution_stage != 1:
                return False, "Only 1st evolution Pokemon are allowed in this duel!"
        
        elif duel_type == "2nd-evolution":
            evolution_stage = await get_evolution_stage(pokemon_data['api_name'])
            if evolution_stage != 2:
                return False, "Only 2nd evolution Pokemon are allowed in this duel!"
        
        elif duel_type == "legendaries":
            # Check if either the specific form or base form is legendary
            is_leg_specific = await is_legendary(pokemon_data['api_name'])
            is_leg_base = await is_legendary(base_name)
            if not (is_leg_specific or is_leg_base):
                return False, "Only Legendary Pokemon are allowed in this duel!"
        
        elif duel_type == "normal":
            # Check if either the specific form or base form is legendary
            is_leg_specific = await is_legendary(pokemon_data['api_name'])
            is_leg_base = await is_legendary(base_name)
            if is_leg_specific or is_leg_base:
                return False, "Legendary Pokemon are not allowed in normal duels!"
        
        return True, "Valid"
    
    async def create_duel_summary(self, duel):
        """Create a summary embed of the duel"""
        if duel.is_triple_duel:
            title = f"📊 Triple Duel Summary"
            description = f"Complete history of {duel.players[0].name} vs {duel.players[1].name} vs {duel.players[2].name}"
        else:
            title = f"📊 Duel Summary"
            description = f"Complete history of {duel.players[0].name} vs {duel.players[1].name}"
            
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.purple()
        )
        
        # Add round-by-round details
        for i, round_data in enumerate(duel.round_history, 1):
            if duel.is_triple_duel:
                round_text = f"**{duel.players[0].name}**: {round_data['pokemon1']} ({round_data['score1']:.1f})\n"
                round_text += f"**{duel.players[1].name}**: {round_data['pokemon2']} ({round_data['score2']:.1f})\n"
                round_text += f"**{duel.players[2].name}**: {round_data['pokemon3']} ({round_data['score3']:.1f})\n"
                round_text += f"**Winner**: {round_data['winner']}"
            else:
                round_text = f"**{duel.players[0].name}**: {round_data['pokemon1']} ({round_data['score1']:.1f})\n"
                round_text += f"**{duel.players[1].name}**: {round_data['pokemon2']} ({round_data['score2']:.1f})\n"
                round_text += f"**Winner**: {round_data['winner']}"
                
            embed.add_field(
                name=f"Round {i}",
                value=round_text,
                inline=False
            )
        
        # Add final score
        if duel.is_triple_duel:
            score_text = f"**{duel.players[0].name}**: {duel.scores[duel.players[0].id]}\n"
            score_text += f"**{duel.players[1].name}**: {duel.scores[duel.players[1].id]}\n"
            score_text += f"**{duel.players[2].name}**: {duel.scores[duel.players[2].id]}"
        else:
            score_text = f"**{duel.players[0].name}**: {duel.scores[duel.players[0].id]}\n"
            score_text += f"**{duel.players[1].name}**: {duel.scores[duel.players[1].id]}"
            
        embed.add_field(
            name="Final Result",
            value=score_text,
            inline=False
        )
        
        # Add duel type
        embed.set_footer(text=f"Duel Type: {duel.duel_type.replace('-', ' ').title()}")
        
        return embed
    
    async def showdown_mode(self, duel, channel):
        """Start a 7-second showdown mode where players can trash talk"""
        showdown_msg = await channel.send("🎤 **SHOWDOWN MODE!** 🎤\n\nYou have 7 seconds to trash talk each other!\n\n**GO!**")
        
        # Enable message sending for all players (but keep read permissions for everyone)
        for player in duel.players:
            await channel.set_permissions(player, read_messages=True, send_messages=True)
        
        # Wait for 7 seconds
        await asyncio.sleep(7)
        
        # Disable message sending after showdown (but keep read permissions)
        for player in duel.players:
            await channel.set_permissions(player, read_messages=True, send_messages=False)
        
        # End showdown
        await channel.send("⏰ **Showdown mode ended!** The channel is now locked for new messages.")
    
    async def end_duel(self, duel, message):
        """End the duel and lock the channel for new messages but keep it readable"""
        # Determine winner and losers
        winner_id = max(duel.scores, key=duel.scores.get)
        winner = next(player for player in duel.players if player.id == winner_id)
        losers = [player for player in duel.players if player.id != winner_id]
        
        # Add to history
        self.add_to_history(duel, winner_id, losers)
        
        # Send final score in large text
        if duel.is_triple_duel:
            score_text = f"# FINAL SCORE: {duel.scores[duel.players[0].id]} - {duel.scores[duel.players[1].id]} - {duel.scores[duel.players[2].id]}"
        else:
            score_text = f"# FINAL SCORE: {duel.scores[duel.players[0].id]} - {duel.scores[duel.players[1].id]}"
            
        await message.channel.send(score_text)
        
        # Create winner embed with avatar
        winner_embed = discord.Embed(
            title=f"🏆 Duel Champion! 🏆",
            description=f"{winner.mention} has won the duel!",
            color=discord.Color.gold()
        )
        winner_embed.set_thumbnail(url=winner.avatar.url if winner.avatar else winner.default_avatar.url)
        
        if duel.is_triple_duel:
            winner_embed.add_field(name="Final Score", value=f"{duel.scores[duel.players[0].id]}-{duel.scores[duel.players[1].id]}-{duel.scores[duel.players[2].id]}", inline=False)
        else:
            winner_embed.add_field(name="Final Score", value=f"{duel.scores[duel.players[0].id]}-{duel.scores[duel.players[1].id]}", inline=False)
            
        winner_embed.add_field(name="Winner", value=winner.mention, inline=True)
        
        if duel.is_triple_duel:
            loser_text = f"{losers[0].mention} and {losers[1].mention}"
        else:
            loser_text = losers[0].mention
            
        winner_embed.add_field(name="Loser(s)", value=loser_text, inline=True)
        winner_embed.add_field(name="Duel Type", value=duel.duel_type.replace("-", " ").title(), inline=False)
        
        await message.channel.send(embed=winner_embed)
        
        # Send duel summary
        summary_embed = await self.create_duel_summary(duel)
        await message.channel.send(embed=summary_embed)
        
        # Start showdown mode
        await self.showdown_mode(duel, message.channel)
        
        # Lock the channel for new messages but keep it readable
        guild = message.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
        }
        
        # Add read permissions for all players (but no sending)
        for player in duel.players:
            overwrites[player] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        
        # Apply the permission overwrites
        await message.channel.edit(overwrites=overwrites)
        
        # Rename channel to indicate it's completed
        if duel.is_triple_duel:
            await message.channel.edit(name=f"completed-triple-{duel.players[0].name}-vs-{duel.players[1].name}-vs-{duel.players[2].name}")
        else:
            await message.channel.edit(name=f"completed-{duel.players[0].name}-vs-{duel.players[1].name}")
        
        # Store completed duel
        self.completed_duels[message.channel.id] = duel
        
        # Mark duel as ended
        duel.duel_ended = True
        
        # Remove from active duels
        if message.channel.id in self.active_duels:
            del self.active_duels[message.channel.id]
    
    async def handle_message(self, message):
        """Handle messages in duel channels"""
        # Check if message is in a duel channel
        if message.channel.id in self.active_duels:
            duel = self.active_duels[message.channel.id]
            
            # Check if duel has ended
            if duel.duel_ended:
                return False
            
            # Only accept messages from the duel participants
            if message.author not in duel.players:
                return False
            
            # Check if we're in the selection phase and waiting for selections
            if duel.selection_phase and duel.waiting_for_selection:
                current_time = time.time()
                if current_time - duel.last_selection_time < duel.selection_cooldown:
                    # Still in cooldown, ignore message
                    return True
                
                # Delete the message immediately to prevent cheating
                try:
                    await message.delete()
                except:
                    pass  # Message might already be deleted
                
                # Process Pokemon selection
                if duel.pokemon[message.author.id] is None:
                    # Get Pokemon data
                    pokemon_data = await get_pokemon_data(message.content)
                    if pokemon_data is None:
                        await self.send_ephemeral_message(message.channel, message.author, 
                            f"I couldn't find that Pokemon. Please try again.\n\nUse forms like: `Deoxys Attack`, `Giratina Origin`, etc.")
                        return True
                    
                    # Validate Pokemon for duel type
                    is_valid, error_msg = await self.validate_pokemon_for_duel(
                        pokemon_data, duel.duel_type, duel.used_pokemon, message.author, 
                        [p for p in duel.players if p != message.author]
                    )
                    
                    if not is_valid:
                        # Award points to opponents for invalid selection
                        for opponent in duel.players:
                            if opponent != message.author:
                                duel.scores[opponent.id] += 1
                        
                        await message.channel.send(
                            f"❌ {message.author.mention} selected an invalid Pokemon for {duel.duel_type.replace('-', ' ')} duel!\n"
                            f"**All opponents gain 1 point!**\n\n"
                            f"Reason: {error_msg}"
                        )
                        
                        # Check if duel is over after penalty
                        needed_wins = (duel.rounds // 2) + 1
                        if any(score >= needed_wins for score in duel.scores.values()):
                            await self.end_duel(duel, message)
                            return True
                        
                        # Reset for next round
                        duel.pokemon = {player.id: None for player in duel.players}
                        duel.countdown_active = False
                        duel.selection_phase = False
                        duel.waiting_for_selection = False
                        
                        # Send ready message for next round
                        ready_text = "**READY FOR NEXT ROUND?**\n\n"
                        for player in duel.players:
                            ready_text += f"{player.name}: ❌\n"
                            
                        duel.ready_message = await message.channel.send(ready_text)
                        await duel.ready_message.add_reaction('✅')
                        return True
                    
                    duel.pokemon[message.author.id] = pokemon_data
                    duel.used_pokemon.add(pokemon_data['name'].lower())
                    # await self.send_ephemeral_message(message.channel, message.author, f"You've selected **{pokemon_data['name']}**!")
                
                # If all players have selected their Pokemon, compare them
                if all(duel.pokemon.values()):
                    # Calculate battle scores
                    if duel.is_triple_duel:
                        # For triple duels, calculate scores for all combinations
                        pokemon_list = [duel.pokemon[player.id] for player in duel.players]
                        battle_scores = []
                        
                        for i, pokemon in enumerate(pokemon_list):
                            # Calculate average score against both opponents
                            score1, score2 = calculate_battle_score(pokemon, pokemon_list[(i+1)%3])
                            score3, score4 = calculate_battle_score(pokemon, pokemon_list[(i+2)%3])
                            avg_score = (score1 + score3) / 2
                            battle_scores.append(avg_score)
                    else:
                        # For 1v1 duels, use the standard calculation
                        pokemon1 = duel.pokemon[duel.players[0].id]
                        pokemon2 = duel.pokemon[duel.players[1].id]
                        battle_score1, battle_score2 = calculate_battle_score(pokemon1, pokemon2)
                        battle_scores = [battle_score1, battle_score2]
                    
                    # Record round history
                    if duel.is_triple_duel:
                        round_data = {
                            'pokemon1': duel.pokemon[duel.players[0].id]['name'],
                            'pokemon2': duel.pokemon[duel.players[1].id]['name'],
                            'pokemon3': duel.pokemon[duel.players[2].id]['name'],
                            'score1': battle_scores[0],
                            'score2': battle_scores[1],
                            'score3': battle_scores[2],
                            'winner': None
                        }
                        
                        # Determine winner
                        max_score = max(battle_scores)
                        winners = [i for i, score in enumerate(battle_scores) if score == max_score]
                        
                        if len(winners) == 1:
                            round_data['winner'] = duel.players[winners[0]].name
                            duel.scores[duel.players[winners[0]].id] += 1
                        else:
                            round_data['winner'] = "Tie (no points awarded)"
                    else:
                        round_data = {
                            'pokemon1': duel.pokemon[duel.players[0].id]['name'],
                            'pokemon2': duel.pokemon[duel.players[1].id]['name'],
                            'score1': battle_scores[0],
                            'score2': battle_scores[1],
                            'winner': None
                        }
                        
                        if battle_scores[0] > battle_scores[1]:
                            round_data['winner'] = duel.players[0].name
                            duel.scores[duel.players[0].id] += 1
                        elif battle_scores[1] > battle_scores[0]:
                            round_data['winner'] = duel.players[1].name
                            duel.scores[duel.players[1].id] += 1
                        else:
                            round_data['winner'] = "Tie (no points awarded)"
                    
                    duel.round_history.append(round_data)
                    duel.waiting_for_selection = False  # Stop accepting selections
                    await asyncio.sleep(1)  # Brief pause for suspense
                    
                    # End selection phase
                    duel.selection_phase = False
                    
                    # Create and send VS image
                    if duel.is_triple_duel:
                        vs_image = await create_triple_vs_image(
                            duel.pokemon[duel.players[0].id], 
                            duel.pokemon[duel.players[1].id], 
                            duel.pokemon[duel.players[2].id],
                            duel.players[0].name, 
                            duel.players[1].name,
                            duel.players[2].name
                        )
                    else:
                        vs_image = await create_vs_image(
                            duel.pokemon[duel.players[0].id], 
                            duel.pokemon[duel.players[1].id], 
                            duel.players[0].name, 
                            duel.players[1].name
                        )
                        
                    if vs_image:
                        file = discord.File(vs_image, filename="vs_battle.png")
                        
                        if duel.is_triple_duel:
                            vs_text = f"**Round {duel.current_round + 1} Results**\n"
                            vs_text += f"**{duel.pokemon[duel.players[0].id]['name']}** (Battle Score: {battle_scores[0]:.1f}) vs "
                            vs_text += f"**{duel.pokemon[duel.players[1].id]['name']}** (Battle Score: {battle_scores[1]:.1f}) vs "
                            vs_text += f"**{duel.pokemon[duel.players[2].id]['name']}** (Battle Score: {battle_scores[2]:.1f})"
                        else:
                            vs_text = f"**Round {duel.current_round + 1} Results**\n"
                            vs_text += f"**{duel.pokemon[duel.players[0].id]['name']}** (Battle Score: {battle_scores[0]:.1f}) vs "
                            vs_text += f"**{duel.pokemon[duel.players[1].id]['name']}** (Battle Score: {battle_scores[1]:.1f})"
                            
                        await message.channel.send(vs_text, file=file)
                    
                    await asyncio.sleep(2)
                    
                    # Announce winner
                    if round_data['winner'] != "Tie (no points awarded)":
                        winner = next(player for player in duel.players if player.name == round_data['winner'])
                        
                        # Create win embed with player avatar
                        win_embed = discord.Embed(
                            title=f"🏆 Round Winner!",
                            description=f"{winner.mention} wins this round with **{duel.pokemon[winner.id]['name']}**!",
                            color=discord.Color.green()
                        )
                        win_embed.set_thumbnail(url=winner.avatar.url if winner.avatar else winner.default_avatar.url)
                        win_embed.add_field(name="Pokemon", value=duel.pokemon[winner.id]['name'], inline=True)
                        
                        if duel.is_triple_duel:
                            win_embed.add_field(name="Battle Score", value=f"{battle_scores[0]:.1f} vs {battle_scores[1]:.1f} vs {battle_scores[2]:.1f}", inline=True)
                        else:
                            win_embed.add_field(name="Battle Score", value=f"{battle_scores[0]:.1f} vs {battle_scores[1]:.1f}", inline=True)
                            
                        await message.channel.send(embed=win_embed)
                    else:
                        await message.channel.send("**It's a tie!** No points awarded this round.")
                    
                    duel.current_round += 1
                    
                    # Send current score in large text
                    if duel.is_triple_duel:
                        score_text = f"# {duel.scores[duel.players[0].id]} - {duel.scores[duel.players[1].id]} - {duel.scores[duel.players[2].id]}"
                    else:
                        score_text = f"# {duel.scores[duel.players[0].id]} - {duel.scores[duel.players[1].id]}"
                        
                    await message.channel.send(score_text)
                    
                    # Check if duel is over
                    needed_wins = (duel.rounds // 2) + 1
                    if any(score >= needed_wins for score in duel.scores.values()):
                        await self.end_duel(duel, message)
                    else:
                        # Reset for next round
                        duel.pokemon = {player.id: None for player in duel.players}
                        duel.countdown_active = False
                        duel.waiting_for_selection = True
                        
                        # Send ready message for next round
                        ready_text = "**READY FOR NEXT ROUND?**\n\n"
                        for player in duel.players:
                            ready_text += f"{player.name}: ❌\n"
                            
                        duel.ready_message = await message.channel.send(ready_text)
                        await duel.ready_message.add_reaction('✅')
            
            return True
        
        return False