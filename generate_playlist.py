import os
import random
import sys
from collections import Counter

import pylast
import requests
import yaml

# --- DEFAULT CONFIG VALUES ---
DEFAULT_CONFIG = {
    "debug": False,
    "lastfm": {
        "api_key": "",
        "api_secret": "",
        "username": "",
    },
    "music_assistant": {
        "url": "",
        "token": "",
        "playlist": "Last.fm Recommendations",
    },
    "recommendation_strategy": {
        "max_top_artists": 30,
        "max_similar_artists_per_artist": 10,
        "max_similar_artists_total": 50,
        "max_tracks_per_similar_artist": 2,
    },
}


# --- FUNCTIONS ---
def api_request(command, args):
    url = f"{MASS_URL}/api"
    headers = {
        "Authorization": f"Bearer {MASS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"command": command, "args": args}

    response = requests.post(url, headers=headers, json=payload)

    if DEBUG:
        print("---------------------------------")
        print(f"Request URL: {url}")
        print(f"Request Payload: {payload}")
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Content: {response.text}")
        print("---------------------------------")
        print("")

    return response.json() if response.status_code == 200 else None


# Search for a track by name and artist (optional album)
def search_track(artist, title, album=None):
    args = {"track_name": title, "artist_name": artist}

    if album:
        args["album_name"] = album

    results = api_request("music/track_by_name", args)
    return results if results else None


# Search for a playlist by name
def search_playlist(name):
    args = {"search_query": name, "media_types": ["playlist"], "limit": 1}
    results = api_request("music/search", args)

    if results and "playlists" in results and results["playlists"]:
        return results["playlists"][0]

    return None


# Empty the playlist (clear all tracks)
def empty_playlist(playlist):
    args = {
        "item_id": playlist["item_id"],
        "provider_instance_id_or_domain": playlist["provider"],
    }
    tracks = api_request("music/playlists/playlist_tracks", args)

    if tracks:
        positions_to_remove = [str(i) for i in range(len(tracks))]

        remove_args = {
            "db_playlist_id": playlist["item_id"],
            "positions_to_remove": positions_to_remove,
        }
        return api_request("music/playlists/remove_playlist_tracks", remove_args)

    return None


# Create a playlist (empty existing playlists)
def create_playlist(name):
    existing_playlist = search_playlist(name)

    if existing_playlist:
        empty_playlist(existing_playlist)
        return existing_playlist["item_id"]

    args = {"name": name}
    results = api_request("music/playlists/create_playlist", args)
    return results.get("playlist_id", None) if results else None


# Add tracks to a playlist
def add_tracks_to_playlist(playlist_id, track_uris):
    args = {"db_playlist_id": playlist_id, "uris": track_uris}

    return api_request("music/playlists/add_playlist_tracks", args)


# --- LOAD CONFIG ---
CONFIG_FILE = "config.yaml"

if not os.path.exists(CONFIG_FILE):
    print(f"Warning: Config file '{CONFIG_FILE}' not found. Using default values.")
    config = DEFAULT_CONFIG
else:
    try:
        with open(CONFIG_FILE, "r") as file:
            config = yaml.safe_load(file) or {}
    except Exception as e:
        print(f"Error reading config file: {e}")
        print("Using default values.")
        config = {}


# --- MERGE DEFAULTS WITH LOADED CONFIG ---
def merge_dicts(default, override):
    """Recursively merge two dictionaries"""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


config = merge_dicts(DEFAULT_CONFIG, config)


# --- CONFIG VARIABLES ---
DEBUG = config.get("debug", False)

LASTFM_API_KEY = config["lastfm"]["api_key"]
LASTFM_API_SECRET = config["lastfm"]["api_secret"]
LASTFM_USERNAME = config["lastfm"]["username"]

MASS_URL = config["music_assistant"]["url"]
MASS_TOKEN = config["music_assistant"]["token"]
MASS_PLAYLIST = config["music_assistant"]["playlist"]

MAX_TOP_ARTISTS = config["recommendation_strategy"]["max_top_artists"]
MAX_SIMILAR_ARTISTS_PER_ARTIST = config["recommendation_strategy"][
    "max_similar_artists_per_artist"
]
MAX_SIMILAR_ARTISTS_TOTAL = config["recommendation_strategy"][
    "max_similar_artists_total"
]
MAX_TRACKS_PER_SIMILAR_ARTIST = config["recommendation_strategy"][
    "max_tracks_per_similar_artist"
]

# --- CHECK CRITICAL VALUES ---
critical_values = [
    ("LASTFM_API_KEY", LASTFM_API_KEY),
    ("LASTFM_API_SECRET", LASTFM_API_SECRET),
    ("USERNAME", LASTFM_USERNAME),
    ("MA_URL", MASS_URL),
    ("MA_TOKEN", MASS_TOKEN),
]

missing = [name for name, val in critical_values if not val]
if missing:
    print(f"Error: Missing critical config values: {missing}")
    sys.exit(1)

if DEBUG:
    print("Config loaded successfully:")
    print(config)


# --- LAST.FM AUTH ---
network = pylast.LastFMNetwork(
    api_key=LASTFM_API_KEY,
    api_secret=LASTFM_API_SECRET,
)

user = network.get_user(LASTFM_USERNAME)

# --- STEP 1: GET USER'S TOP ARTISTS ---
print("Fetching user's top artists...")
top_artists = user.get_top_artists(limit=MAX_TOP_ARTISTS)
seed_artists = [a.item for a in top_artists]

# --- STEP 2: BUILD SIMILAR ARTIST GRAPH ---
print("Expanding similar artists...")
similar_counter = Counter()

for artist in seed_artists:
    try:
        similars = artist.get_similar(limit=MAX_SIMILAR_ARTISTS_PER_ARTIST)
        for sim, score in similars:
            similar_counter[sim.name] += score
    except Exception:
        continue

# --- STEP 3: FILTER ---
print("Filtering out known artists...")
known_artists = set(a.item.name for a in top_artists)

filtered_artists = [
    artist
    for artist, score in similar_counter.most_common()
    if artist not in known_artists
]

# take top N
filtered_artists = filtered_artists[:MAX_SIMILAR_ARTISTS_TOTAL]

# --- STEP 4: GET TRACKS ---
print("Fetching tracks...")
tracks = []

for artist_name in filtered_artists:
    try:
        artist = network.get_artist(artist_name)
        top_tracks = artist.get_top_tracks(limit=MAX_TRACKS_PER_SIMILAR_ARTIST)
        for t in top_tracks:
            tracks.append((artist_name, t.item.title))
    except Exception:
        continue

# shuffle to avoid clustering
random.shuffle(tracks)

# --- STEP 5: PREPARE SENDING TO MUSIC ASSISTANT ---
print("Resolving tracks in Music Assistant...")
track_uris = []

for artist, title in tracks:
    track = search_track(artist, title)
    if track:
        track_uris.append(track["uri"])

# --- STEP 6: SEND TO MUSIC ASSISTANT ---
print("Sending tracks to playlist in Music Assistant...")

# create playlist fresh each time (simplest)
playlist_id = create_playlist(MASS_PLAYLIST)
add_tracks_to_playlist(playlist_id, track_uris)

print(f"Done. Added {len(track_uris)} tracks.")
