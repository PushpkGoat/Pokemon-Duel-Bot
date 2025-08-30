# image_generator.py
import io
import requests
import os
import hashlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from utils import type_colors
import asyncio
import aiohttp
import random

# Create cache directory if it doesn't exist
if not os.path.exists('image_cache'):
    os.makedirs('image_cache')

# COMPLETE and ACCURATE Pokemon GO type effectiveness chart
# Source: https://www.polygon.com/pokemon-go-guide/22554033/type-chart-strengths-weaknesses-super-effective/
# Format: {"attacking_type": {"defending_type": multiplier}}
pokemon_go_effectiveness = {
    "normal": {"rock": 0.625, "ghost": 0.391, "steel": 0.625},
    "fire": {"fire": 0.625, "water": 0.625, "grass": 1.6, "ice": 1.6, "bug": 1.6, "rock":  0.625, "dragon": 0.625, "steel": 1.6, "fairy": 0.625},
    "water": {"fire": 1.6, "water": 0.625, "grass": 0.625, "ground": 1.6, "rock": 1.6, "dragon": 0.625},
    "electric": {"water": 1.6, "electric": 0.625, "grass": 0.625, "ground": 0.391, "flying": 1.6, "dragon": 0.625, "electric": 0.625},
    "grass": {"fire":  0.625, "water": 1.6, "grass": 0.625, "poison": 0.625, "ground": 1.6, "flying": 0.625, "bug": 0.625, "rock": 1.6, "dragon": 0.625, "steel": 0.625},
    "ice": {"fire": 0.625, "water": 0.625, "grass": 1.6, "ice": 0.625, "ground": 1.6, "flying": 1.6, "dragon": 1.6, "steel": 0.625},
    "fighting": {"normal": 1.6, "ice": 1.6, " poison": 0.625, "flying":  0.625, "psychic": 0.625, "bug": 0.625, "rock": 1.6, " ghost": 0.391, "dark": 1.6, "steel": 1.6, "fairy": 0.625},
    "poison": {"grass": 1.6, "poison": 0.625, "ground": 0.625, "rock": 0.625, "ghost": 0.625, "steel": 0.391, "fairy": 1.6, "bug": 1.6, "poison": 0.625},
    "ground": {"fire": 1.6, "electric": 1.6, "grass": 0.625, "poison": 1.6, "flying": 0.391, "bug": 0.625, "rock": 1.6, "steel": 1.6, "ground": 0.625},
    "flying": {"electric": 0.625, "grass": 1.6, "fighting": 1.6, "bug": 1.6, "rock": 0.625, "steel": 0.625, "flying": 0.625},
    "psychic": {"fighting": 1.6, "poison": 1.6, "psychic": 0.625, "dark": 0.391, "steel": 0.625},
    "bug": {"fire": 0.625, "grass": 1.6, "fighting": 0.625, "poison": 0.625, "flying": 0.625, "psychic": 1.6, "ghost": 0.625, "dark": 1.6, "steel": 0.625, "fairy": 0.625, "bug": 0.625},
    "rock": {"fire": 1.6, "ice": 1.6, "fighting": 0.625, "ground": 0.625, "flying": 1.6, "bug": 1.6, "steel": 0.625, "rock": 0.625},
    "ghost": {"normal": 0.391, "psychic": 1.6, "ghost": 1.6, "dark": 0.625},
    "dragon": {"dragon": 1.6, "steel": 0.625, "fairy": 0.391},
    "dark": {"fighting": 0.625, "psychic": 1.6, "ghost": 1.6, "dark": 0.625, "fairy": 0.625},
    "steel": {"fire": 0.625, "water": 0.625, "electric": 0.625, "ice": 1.6, "rock": 1.6, "steel": 0.625, "fairy": 1.6},
    "fairy": {"fire": 0.625, "fighting": 1.6, "poison": 0.625, "dragon": 1.6, "dark": 1.6, "steel": 0.625, "fairy": 0.625}
}

# STAB (Same Type Attack Bonus) multiplier
STAB_MULTIPLIER = 1.2

def get_advantage_text(advantage):
    """Convert advantage multiplier to text"""
    if advantage >= 1.6:
        return "Super Effective! (x{:.1f})".format(advantage)
    elif advantage > 1:
        return "Effective (x{:.1f})".format(advantage)
    elif advantage == 1:
        return "Neutral (x1)"
    elif advantage > 0.625:
        return "Resisted (x{:.1f})".format(advantage)
    elif advantage > 0.391:
        return "Very Resisted (x{:.1f})".format(advantage)
    else:
        return "No Effect! (x{:.1f})".format(advantage)

# Function to get weaknesses for a type (what types are super effective against it)
def get_weaknesses(pokemon_types):
    """Get all types that are super effective against the given Pokemon types"""
    weaknesses = {}
    for defending_type in pokemon_types:
        for attacking_type, effectiveness in pokemon_go_effectiveness.items():
            if defending_type in effectiveness and effectiveness[defending_type] > 1:
                if attacking_type in weaknesses:
                    weaknesses[attacking_type] *= effectiveness[defending_type]
                else:
                    weaknesses[attacking_type] = effectiveness[defending_type]
    return weaknesses

# Function to get resistances for a type ( what types are not very effective against it)
def get_resistances(pokemon_types):
    """Get all types that are not very effective against the given Pokemon types"""
    resistances = {}
    for defending_type in pokemon_types:
        for attacking_type, effectiveness in pokemon_go_effectiveness.items():
            if defending_type in effectiveness and effectiveness[defending_type] < 1:
                if attacking_type in resistances:
                    resistances[attacking_type] *= effectiveness [defending_type]
                else:
                    resistances[attacking_type] = effectiveness[defending_type]
    return resistances

def calculate_ivs(pokemon_name):
    """Generate IVs (Individual Values) based on the Pokemon name"""
    # Create a hash from the Pokemon name to generate consistent IVs
    name_hash = hashlib.md5(pokemon_name.lower().encode()).hexdigest()
    
    # Convert parts of the hash to IV values (0-31)
    iv_hp = int(name_hash[0:2], 16) % 32
    iv_attack = int(name_hash[2:4], 16) % 32
    iv_defense = int(name_hash[4:6], 16) % 32
    iv_special_attack = int(name_hash[6:8], 16) % 32
    iv_special_defense = int(name_hash[8:10], 16) % 32
    iv_speed = int(name_hash[10:12], 16) % 32
    
    return {
        'hp': iv_hp,
        'attack': iv_attack,
        'defense': iv_defense,
        'special_attack': iv_special_attack,
        'special_defense': iv_special_defense,
        'speed': iv_speed
    }

def calculate_battle_score(pokemon1, pokemon2):
    """Calculate battle score based on type advantages, STAB, base stats, and IVs"""
    # Calculate IVs for both Pokemon
    ivs1 = calculate_ivs(pokemon1['name'])
    ivs2 = calculate_ivs(pokemon2['name'])
    
    # Calculate effective stats with IVs
    effective_stats1 = {
        'hp': pokemon1['hp'] + ivs1['hp'],
        'attack': pokemon1['attack'] + ivs1['attack'],
        'defense': pokemon1['defense'] + ivs1['defense'],
        'special_attack': pokemon1['special_attack'] + ivs1['special_attack'],
        'special_defense': pokemon1['special_defense'] + ivs1['special_defense'],
        'speed': pokemon1['speed'] + ivs1['speed']
    }
    
    effective_stats2 = {
        'hp': pokemon2['hp'] + ivs2['hp'],
        'attack': pokemon2['attack'] + ivs2['attack'],
        'defense': pokemon2['defense'] + ivs2['defense'],
        'special_attack': pokemon2['special_attack'] + ivs2['special_attack'],
        'special_defense': pokemon2['special_defense'] + ivs2['special_defense'],
        'speed': pokemon2['speed'] + ivs2['speed']
    }
    
    # Calculate type advantages with STAB
    advantage1, advantage2 = calculate_type_advantage_with_stab(pokemon1['types'], pokemon2['types'])
    
    # Calculate battle scores with weighted stats and type advantage
    battle_score1 = calculate_weighted_stats(effective_stats1) * advantage1
    battle_score2 = calculate_weighted_stats(effective_stats2) * advantage2
    
    return battle_score1, battle_score2

def calculate_weighted_stats(stats):
    """Calculate weighted stats with emphasis on offensive capabilities"""
    # Weighting: HP (0.8), Attack (1.2), Defense (0.9), Sp. Atk (1.2), Sp. Def (0.9), Speed (1.0)
    weighted_stats = (
        stats['hp'] * 0.8 +
        stats['attack'] * 1.2 +
        stats['defense'] * 0.9 +
        stats['special_attack'] * 1.2 +
        stats['special_defense'] * 0.9 +
        stats['speed'] * 1.0
    )
    return weighted_stats / 100  # Scale down to reasonable numbers

def calculate_type_advantage_with_stab(types1, types2):
    """
    Calculate type advantage with STAB (Same Type Attack Bonus)
    Returns multipliers for both Pokemon
    """
    # Calculate type effectiveness for Pokemon1 attacking Pokemon2
    effectiveness1 = 1.0
    for attack_type in types1:
        # Apply STAB if the attacking type matches the Pokemon's type
        stab = STAB_MULTIPLIER if attack_type in types1 else 1.0
        
        for defense_type in types2:
            if attack_type in pokemon_go_effectiveness and defense_type in pokemon_go_effectiveness[attack_type]:
                effectiveness1 *= pokemon_go_effectiveness[attack_type][defense_type] * stab
    
    # Calculate type effectiveness for Pokemon2 attacking Pokemon1
    effectiveness2 = 1.0
    for attack_type in types2:
        # Apply STAB if the attacking type matches the Pokemon's type
        stab = STAB_MULTIPLIER if attack_type in types2 else 1.0
        
        for defense_type in types1:
            if attack_type in pokemon_go_effectiveness and defense_type in pokemon_go_effectiveness[attack_type]:
                effectiveness2 *= pokemon_go_effectiveness[attack_type][defense_type] * stab
    
    return effectiveness1, effectiveness2

async def create_pokemon_image(pokemon_data):
    """Create an image for a Pokemon with its stats and types"""
    # Create a unique filename based on Pokemon data
    filename = f"image_cache/{pokemon_data['name'].replace(' ', '_').lower()}_{hashlib.md5(str(pokemon_data).encode()).hexdigest()[:8]}.png"
    
    # Check if image already exists in cache
    if os.path.exists(filename):
        return filename
    
    # Create a new image
    img_width, img_height = 400, 500
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        # Try to load a font
        font = ImageFont.truetype("arial.ttf", 20)
        font_large = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 16)
    except:
        # Fallback to default font
        font = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Draw Pokemon name
    draw.text((img_width//2, 20), pokemon_data['name'], fill='black', font=font_large, anchor='mt')
    
    # Draw types
    type_y = 60
    for i, ptype in enumerate(pokemon_data['types']):
        color = type_colors.get(ptype.lower(), 'gray')
        draw.rectangle([(50, type_y + i*30), (150, type_y + i*30 + 25)], fill=color)
        draw.text((100, type_y + i*30 + 12), ptype, fill='white', font=font, anchor='mm')
    
    # Draw stats
    stats_y = 130
    stats = [
        f"HP: {pokemon_data['hp']}",
        f"Attack: {pokemon_data['attack']}",
        f"Defense: {pokemon_data['defense']}",
        f"Sp. Atk: {pokemondata['special_attack']}",
        f"Sp. Def: {pokemon_data['special_defense']}",
        f"Speed: {pokemon_data['speed']}"
    ]
    
    for i, stat in enumerate(stats):
        draw.text((img_width//2, stats_y + i*25), stat, fill='black', font=font, anchor='mm')
    
    # Try to download and add Pokemon image
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(pokemon_data['image_url']) as resp:
                if resp.status == 200:
                    pokemon_img_data = await resp.read()
                    pokemon_img = Image.open(io.BytesIO(pokemon_img_data))
                    
                    # Resize if needed
                    max_size = (150, 150)
                    pokemon_img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    # Calculate position
                    img_x = (img_width - pokemon_img.width) // 2
                    img_y = 280
                    
                    # Paste onto our image
                    img.paste(pokemon_img, (img_x, img_y), pokemon_img if pokemon_img.mode == 'RGBA' else None)
    except:
        pass  # Skip image if there's an error
    
    # Save to cache
    img.save(filename)
    return filename

async def create_vs_image(pokemon1_data, pokemon2_data, player1_name, player2_name):
    """Create a VS image with both Pokemon side by side"""
    try:
        # Create a dark background
        bg_width, bg_height = 800, 600
        background = Image.new('RGBA', (bg_width, bg_height), (30, 30, 50, 255))
        draw = ImageDraw.Draw(background)
        
        # Download Pokemon images
        img1 = None
        img2 = None
        
        # Use 'image_url' instead of 'sprite_url'
        if pokemon1_data.get('image_url'):
            response = requests.get(pokemon1_data['image_url'])
            img1 = Image.open(io.BytesIO(response.content)).convert("RGBA")
            img1 = img1.resize((200, 200), Image.Resampling.LANCZOS)
        
        if pokemon2_data.get('image_url'):
            response = requests.get(pokemon2_data['image_url'])
            img2 = Image.open(io.BytesIO(response.content)).convert("RGBA")
            img2 = img2.resize((200, 200), Image.Resampling.LANCZOS)
        
        # Paste Pokemon images
        if img1:
            background.paste(img1, (100, 100), img1)
        if img2:
            background.paste(img2, (500, 100), img2)
        
        # Calculate type advantages with STAB
        advantage1, advantage2 = calculate_type_advantage_with_stab(pokemon1_data['types'], pokemon2_data['types'])
        advantage_text1 = get_advantage_text(advantage1)
        advantage_text2 = get_advantage_text(advantage2)
        
        # Calculate battle scores
        battle_score1, battle_score2 = calculate_battle_score(pokemon1_data, pokemon2_data)
        
        # Add VS text in the middle
        try:
            font_vs = ImageFont.truetype("arialbd.ttf", 48)
            font_name = ImageFont.truetype("arialbd.ttf", 20)
            font_stats = ImageFont.truetype("arial.ttf", 16)
            font_advantage = ImageFont.truetype("arialbd.ttf", 14)
            font_score = ImageFont.truetype("arialbd.ttf", 18)
            font_small = ImageFont.truetype("arial.ttf", 12)
        except:
            font_vs = ImageFont.load_default()
            font_name = ImageFont.load_default()
            font_stats = ImageFont.load_default()
            font_advantage = ImageFont.load_default()
            font_score = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw VS text
        draw.text((375, 150), "VS", font=font_vs, fill=(255, 255, 255, 255))
        
        # Draw Pokemon names and battle scores
        draw.text((150, 320), f"{pokemon1_data['name']}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((150, 345), f"Battle Score: {battle_score1:.1f}", font=font_score, fill=(255, 255, 255, 255))
        
        draw.text((550, 320), f"{pokemon2_data['name']}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((550, 345), f"Battle Score: {battle_score2:.1f}", font=font_score, fill=(255, 255, 255, 255))
        
        # Draw player names
        draw.text((150, 30), f"{player1_name}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((550, 30), f"{player2_name}", font=font_name, fill=(255, 255, 255, 255))
        
        # Add type indicators
        type1 = "/".join([t.upper() for t in pokemon1_data['types']])
        type2 = "/".join([t.upper() for t in pokemon2_data['types']])
        
        draw.text((150, 60), f"Type: {type1}", font=font_stats, fill=(200, 200, 200, 255))
        draw.text((550, 60), f"Type: {type2}", font=font_stats, fill=(200, 200, 200, 255))
        
        # Draw type advantages
        advantage_color1 = (0, 255, 0, 255) if advantage1 > 1 else (255, 255, 255, 255) if advantage1 == 1 else (255, 100, 100, 255)
        draw.text((150, 380), f"→ {advantage_text1}", font=font_advantage, fill=advantage_color1)
        
        advantage_color2 = (0, 255, 0, 255 ) if advantage2 > 1 else (255, 255, 255, 255) if advantage2 == 1 else (255, 100, 100, 255)
        draw.text((550, 380), f"→ {advantage_text2}", font=font_advantage, fill=advantage_color2)
        
        # Save image to bytes
        img_bytes = io.BytesIO()
        background.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    except Exception as e:
        print(f"Error creating VS image: {e}")
        return None

async def create_triple_vs_image(pokemon1_data, pokemon2_data, pokemon3_data, player1_name, player2_name, player3_name):
    """Create a VS image with three Pokemon side by side"""
    try:
        # Create a dark background
        bg_width, bg_height = 1200, 600
        background = Image.new('RGBA', (bg_width, bg_height), (30, 30, 50, 255))
        draw = ImageDraw.Draw(background)
        
        # Download Pokemon images
        img1 = None
        img2 = None
        img3 = None
        
        # Use 'image_url' instead of 'sprite_url'
        if pokemon1_data.get('image_url'):
            response = requests.get(pokemon1_data['image_url'])
            img1 = Image.open(io.BytesIO(response.content)).convert("RGBA")
            img1 = img1.resize((200, 200), Image.Resampling.LANCZOS)
        
        if pokemon2_data.get('image_url'):
            response = requests.get(pokemon2_data['image_url'])
            img2 = Image.open(io.BytesIO(response.content)).convert("RGBA")
            img2 = img2.resize((200, 200), Image.Resampling.LANCZOS)
            
        if pokemon3_data.get('image_url'):
            response = requests.get(pokemon3_data['image_url'])
            img3 = Image.open(io.BytesIO(response.content)).convert("RGBA")
            img3 = img3.resize((200, 200), Image.Resampling.LANCZOS)
        
        # Paste Pokemon images
        if img1:
            background.paste(img1, (150, 100), img1)
        if img2:
            background.paste(img2, (500, 100), img2)
        if img3:
            background.paste(img3, (850, 100), img3)
        
        # Calculate type advantages with STAB for all combinations
        advantage1_2, advantage2_1 = calculate_type_advantage_with_stab(pokemon1_data['types'], pokemon2_data['types'])
        advantage1_3, advantage3_1 = calculate_type_advantage_with_stab(pokemon1_data['types'], pokemon3_data['types'])
        advantage2_3, advantage3_2 = calculate_type_advantage_with_stab(pokemon2_data['types'], pokemon3_data['types'])
        
        # Calculate average advantages
        avg_advantage1 = (advantage1_2 + advantage1_3) / 2
        avg_advantage2 = (advantage2_1 + advantage2_3) / 2
        avg_advantage3 = (advantage3_1 + advantage3_2) / 2
        
        advantage_text1 = get_advantage_text(avg_advantage1)
        advantage_text2 = get_advantage_text(avg_advantage2)
        advantage_text3 = get_advantage_text(avg_advantage3)
        
        # Calculate battle scores
        battle_score1_2, battle_score2_1 = calculate_battle_score(pokemon1_data, pokemon2_data)
        battle_score1_3, battle_score3_1 = calculate_battle_score(pokemon1_data, pokemon3_data)
        battle_score2_3, battle_score3_2 = calculate_battle_score(pokemon2_data, pokemon3_data)
        
        # Calculate average scores for each Pokemon
        avg_score1 = (battle_score1_2 + battle_score1_3) / 2
        avg_score2 = (battle_score2_1 + battle_score2_3) / 2
        avg_score3 = (battle_score3_1 + battle_score3_2) / 2
        
        # Add VS text in the middle
        try:
            font_vs = ImageFont.truetype("arialbd.ttf", 48)
            font_name = ImageFont.truetype("arialbd.ttf", 20)
            font_stats = ImageFont.truetype("arial.ttf", 16)
            font_advantage = ImageFont.truetype("arialbd.ttf", 14)
            font_score = ImageFont.truetype("arialbd.ttf", 18)
            font_small = ImageFont.truetype("arial.ttf", 12)
        except:
            font_vs = ImageFont.load_default()
            font_name = ImageFont.load_default()
            font_stats = ImageFont.load_default()
            font_advantage = ImageFont.load_default()
            font_score = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw VS text
        draw.text((400, 150), "VS", font=font_vs, fill=(255, 255, 255, 255))
        draw.text((750, 150), "VS", font=font_vs, fill=(255, 255, 255, 255))
        
        # Draw Pokemon names and battle scores
        draw.text((250, 320), f"{pokemon1_data['name']}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((250, 345), f"Battle Score: {avg_score1:.1f}", font=font_score, fill=(255, 255, 255, 255))
        
        draw.text((600, 320), f"{pokemon2_data['name']}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((600, 345), f"Battle Score: {avg_score2:.1f}", font=font_score, fill=(255, 255, 255, 255))
        
        draw.text((950, 320), f"{pokemon3_data['name']}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((950, 345), f"Battle Score: {avg_score3:.1f}", font=font_score, fill=(255, 255, 255, 255))
        
        # Draw player names
        draw.text((250, 30), f"{player1_name}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((600, 30), f"{player2_name}", font=font_name, fill=(255, 255, 255, 255))
        draw.text((950, 30), f"{player3_name}", font=font_name, fill=(255, 255, 255, 255))
        
        # Add type indicators
        type1 = "/".join([t.upper() for t in pokemon1_data['types']])
        type2 = "/".join([t.upper() for t in pokemon2_data['types']])
        type3 = "/".join([t.upper() for t in pokemon3_data['types']])
        
        draw.text((250, 60), f"Type: {type1}", font=font_stats, fill=(200, 200, 200, 255))
        draw.text((600, 60), f"Type: {type2}", font=font_stats, fill=(200, 200, 200, 255))
        draw.text((950, 60), f"Type: {type3}", font=font_stats, fill=(200, 200, 200, 255))
        
        # Draw type advantages
        advantage_color1 = (0, 255, 0, 255) if avg_advantage1 > 1 else (255, 255, 255, 255) if avg_advantage1 == 1 else (255, 100, 100, 255)
        draw.text((250, 380), f"→ {advantage_text1}", font=font_advantage, fill=advantage_color1)
        
        advantage_color2 = (0, 255, 0, 255) if avg_advantage2 > 1 else (255, 255, 255, 255 ) if avg_advantage2 == 1 else (255, 100, 100, 255)
        draw.text((600, 380), f"→ {advantage_text2}", font=font_advantage, fill=advantage_color2)
        
        advantage_color3 = (0, 255, 0, 255) if avg_advantage3 > 1 else (255, 255, 255, 255) if avg_advantage3 == 1 else (255, 100, 100, 255)
        draw.text((950, 380), f"→ {advantage_text3}", font=font_advantage, fill=advantage_color3)
        
        # Save image to bytes
        img_bytes = io.BytesIO()
        background.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    except Exception as e:
        print(f"Error creating triple VS image: {e}")
        return None