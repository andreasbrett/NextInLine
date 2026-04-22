# NextInLine
Discover new music with NextInLine. A simple Python script that fetches your top artists from Last.fm, finds similar artists, and generates playlists in Music Assistant. Fully configurable via a YAML file, this tool helps you discover new tracks your ears will love.

## Features

- fetches your top artists from [Last.fm](https://www.last.fm/)
- builds a graph of similar artists based on your top artists
- filters out any artists that are already in your library
- retrieves popular tracks from artists in the graph
- creates a playlist in [Music Assistant](https://www.music-assistant.io/)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/andreasbrett/NextInLine.git
cd NextInLine
```

2. Create a virtual environment:
```bash
python -m venv .venv
# Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a config file based on `config.yaml.example`

## Usage

Run the script:
```bash
python generate_playlist.py
```
