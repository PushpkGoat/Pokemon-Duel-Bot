# pokemon_api.py
import aiohttp
import json
import asyncio
import os
from typing import Dict, List, Optional, Tuple

# Pokemon API base URL
POKEAPI_BASE = "https://pokeapi.co/api/v2/"

# Cache for Pokemon data to reduce API calls
pokemon_cache = {}

# Legendary Pokemon list (incomplete, add more as needed)
LEGENDARY_POKEMON = [
    "articuno", "zapdos", "moltres", "mewtwo", "mew",
    "raikou", "entei", "suicune", "lugia", "ho-oh", "celebi",
    "regirock", "regice", "registeel", "latias", "latios", "kyogre", "groudon", "rayquaza", "jirachi", "deoxys",
    "uxie", "mesprit", "azelf", "dialga", "palkia", "heatran", "regigigas", "giratina", "cresselia", "darkrai", "shaymin", "arceus",
    "victini", "cobalion", "terrakion", "virizion", "tornadus", "thundurus", "reshiram", "zekrom", "landorus", "kyurem", "keldeo", "meloetta", "genesect",
    "xerneas", "yveltal", "zygarde", "diancie", "hoopa", "volcanion",
    "tapu koko", "tapu lele", "tapu bulu", "tapu fini", "cosmog", "cosmoem", "solgaleo", "lunala", "nihilego", "buzzwole", "pheromosa", "xurkitree", "celesteela", "kartana", "guzzlord", "necrozma", "magearna", "marshadow", "poipole", "naganadel", "stakataka", "blacephalon", "zeraora", "meltan", "melmetal",
    "zacian", "zamazenta", "eternatus", "kubfu", "urshifu", "zarude", "regieleki", "regidrago", "glastrier", "spectrier", "calyrex"
]

async def get_pokemon_data(pokemon_name: str) -> Optional[Dict]:
    """Get Pokemon data from PokeAPI with caching"""
    # Normalize the name
    normalized_name = pokemon_name.strip().lower().replace(" ", "-")
    
    # Check cache first
    if normalized_name in pokemon_cache:
        return pokemon_cache[normalized_name]
    
    try:
        async with aiohttp.ClientSession() as session:
            # First try the exact name
            async with session.get(f"{POKEAPI_BASE}pokemon/{normalized_name}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Extract relevant data
                    pokemon_data = {
                        'name': data['name'].title(),
                        'api_name': data['name'],
                        'id': data['id'],
                        'hp': data['stats'][0]['base_stat'],
                        'attack': data['stats'][1]['base_stat'],
                        'defense': data['stats'][2]['base_stat'],
                        'special_attack': data['stats'][3]['base_stat'],
                        'special_defense': data['stats'][4]['base_stat'],
                        'speed': data['stats'][5]['base_stat'],
                        'types': [t['type']['name'].title() for t in data['types']],
                        'image_url': data['sprites']['other']['official-artwork']['front_default'] or data['sprites']['front_default'],
                        'height': data['height'] / 10,  # Convert to meters
                        'weight': data['weight'] / 10   # Convert to kilograms
                    }
                    
                    # Cache the data
                    pokemon_cache[normalized_name] = pokemon_data
                    return pokemon_data
                
                # If not found, try searching for alternative forms
                elif resp.status == 404:
                    # Handle special forms (e.g., "Deoxys Attack" -> "deoxys-attack")
                    if " " in pokemon_name:
                        form_name = pokemon_name.replace(" ", "-").lower()
                        async with session.get(f"{POKEAPI_BASE}pokemon/{form_name}") as form_resp:
                            if form_resp.status == 200:
                                form_data = await form_resp.json()
                                
                                pokemon_data = {
                                    'name': form_data['name'].replace("-", " ").title(),
                                    'api_name': form_data['name'],
                                    'id': form_data['id'],
                                    'hp': form_data['stats'][0]['base_stat'],
                                    'attack': form_data['stats'][1]['base_stat'],
                                    'defense': form_data['stats'][2]['base_stat'],
                                    'special_attack': form_data['stats'][3]['base_stat'],
                                    'special_defense': form_data['stats'][4]['base_stat'],
                                    'speed': form_data['stats'][5]['base_stat'],
                                    'types': [t['type']['name'].title() for t in form_data['types']],
                                    'image_url': form_data['sprites']['other']['official-artwork']['front_default'] or form_data['sprites']['front_default'],
                                    'height': form_data['height'] / 10,
                                    'weight': form_data['weight'] / 10
                                }
                                
                                pokemon_cache[normalized_name] = pokemon_data
                                return pokemon_data
                    
                    # If still not found, try searching for the base form
                    base_name = pokemon_name.split(" ")[0].lower()
                    async with session.get(f"{POKEAPI_BASE}pokemon/{base_name}") as base_resp:
                        if base_resp.status == 200:
                            base_data = await base_resp.json()
                            
                            pokemon_data = {
                                'name': base_data['name'].title(),
                                'api_name': base_data['name'],
                                'id': base_data['id'],
                                'hp': base_data['stats'][0]['base_stat'],
                                'attack': base_data['stats'][1]['base_stat'],
                                'defense': base_data['stats'][2]['base_stat'],
                                'special_attack': base_data['stats'][3]['base_stat'],
                                'special_defense': base_data['stats'][4]['base_stat'],
                                'speed': base_data['stats'][5]['base_stat'],
                                'types': [t['type']['name'].title() for t in base_data['types']],
                                'image_url': base_data['sprites']['other']['official-artwork']['front_default'] or base_data['sprites']['front_default'],
                                'height': base_data['height'] / 10,
                                'weight': base_data['weight'] / 10
                            }
                            
                            pokemon_cache[normalized_name] = pokemon_data
                            return pokemon_data
    except Exception as e:
        print(f"Error fetching Pokemon data: {e}")
    
    return None

async def is_legendary(pokemon_name: str) -> bool:
    """Check if a Pokemon is legendary"""
    return pokemon_name.lower() in LEGENDARY_POKEMON

async def get_evolution_stage(pokemon_name: str) -> int:
    """Get the evolution stage of a Pokemon (1, 2, or 3)"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get species data
            async with session.get(f"{POKEAPI_BASE}pokemon-species/{pokemon_name}") as resp:
                if resp.status == 200:
                    species_data = await resp.json()
                    
                    # Get evolution chain URL
                    evolution_chain_url = species_data['evolution_chain']['url']
                    
                    # Get evolution chain data
                    async with session.get(evolution_chain_url) as chain_resp:
                        if chain_resp.status == 200:
                            chain_data = await chain_resp.json()
                            
                            # Traverse evolution chain to find the Pokemon
                            def find_evolution_stage(chain, target_name, stage=1):
                                if chain['species']['name'] == target_name:
                                    return stage
                                
                                for evolution in chain['evolves_to']:
                                    result = find_evolution_stage(evolution, target_name, stage + 1)
                                    if result:
                                        return result
                                
                                return None
                            
                            stage = find_evolution_stage(chain_data['chain'], pokemon_name)
                            return stage if stage else 1  # Default to 1 if not found
    except:
        pass
    
    # Fallback: use simple heuristic based on name or ID
    # This is a simplified approach since the evolution chain API can be complex
    return 1  # Default to first stage