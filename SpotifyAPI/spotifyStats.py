from fastapi import APIRouter, Query
import requests
import os
import base64
from collections import Counter
from datetime import datetime, timedelta
from dateutil.parser import isoparse


router = APIRouter()

# ----------- Environment Variables ----------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

# ---------- Helper Functions ----------
def get_access_token():
    url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN
    }
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=payload, headers=headers)
    response.raise_for_status()
    return response.json()["access_token"]

# ---------- API Endpoints ----------
@router.get("/now-playing")
def now_playing():
    token = get_access_token()
    url = "https://api.spotify.com/v1/me/player/currently-playing"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 204 or response.status_code >= 400:
        return {"is_playing": False}
    
    response.raise_for_status()
    data = response.json()

    return {
        "is_playing": data["is_playing"],
        "song": data["item"]["name"],
        "artist": ", ".join([artist["name"] for artist in data["item"]["artists"]]),
        "album": data["item"]["album"]["name"],
        "album_art": data["item"]["album"]["images"][0]["url"],
        "progress_ms": data.get("progress_ms"),
        "duration_ms": data["item"]["duration_ms"] if data.get("item") else None
    }


@router.get("/profile")
def get_profile():
    token = get_access_token()
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    return {
        "display_name": data.get("display_name"),
        "id": data.get("id"),
        "profile_image": data.get("images")[0]["url"] if data.get("images") else None,
    }



@router.get("/top-tracks")
def top_tracks(time_range: str = Query("medium_term", enum=["short_term", "medium_term", "long_term"]), limit: int = 10):

    # time_range: short_term (~4 weeks), medium_term (~6 months), long_term (~years)

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/me/top/tracks?time_range={time_range}&limit={limit}"
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    return [
        {
            "name": track["name"],
            "artist": ", ".join([a["name"] for a in track["artists"]]),
            "album": track["album"]["name"],
            "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
            "preview_url": track["preview_url"]
        }
        for track in data.get("items", [])
    ]


@router.get("/top-recent")
def top_recent(limit: int = 3, days: int = 7):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    after_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    items = []

    for _ in range(8):
        url = f"https://api.spotify.com/v1/me/player/recently-played?after={after_ts}&limit=50"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        batch = response.json().get("items", [])
        if not batch:
            break
        items.extend(batch)

        earliest_ts = min(item["played_at"] for item in batch)
        after_ts = int(isoparse(earliest_ts).timestamp() * 1000) - 1


    seen = set()
    unique_items = []
    for item in items:
        key = (item["track"]["id"], item["played_at"])
        if key not in seen:
            seen.add(key)
            unique_items.append(item)


    track_counts = Counter()
    track_info = {}
    for item in unique_items:
        track = item["track"]
        track_id = track["id"]
        track_counts[track_id] += 1
        track_info[track_id] = {
            "name": track["name"],
            "artist": ", ".join([a["name"] for a in track["artists"]]),
            "album": track["album"]["name"],
            "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
            "preview_url": track["preview_url"]
        }

    top_tracks = [
        {**track_info[track_id], "plays": count}
        for track_id, count in track_counts.most_common(limit)
    ]

    return top_tracks


@router.get("/top-artists")
def top_artists(time_range: str = Query("medium_term", enum=["short_term", "medium_term", "long_term"]), limit: int = 10):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/me/top/artists?time_range={time_range}&limit={limit}"
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    return [
        {
            "name": artist["name"],
            "genres": artist["genres"],
            "popularity": artist["popularity"],
            "image": artist["images"][0]["url"] if artist["images"] else None,
            "spotify_url": artist["external_urls"]["spotify"]
        }
        for artist in data.get("items", [])
    ]

@router.get("/minutes-played")
def minutes_played(days: int = 7):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    after_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    items = []

    while True:
        url = f"https://api.spotify.com/v1/me/player/recently-played?after={after_ts}&limit=50"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        batch = response.json().get("items", [])
        if not batch:
            break

        items.extend(batch)

        earliest_ts = min(item["played_at"] for item in batch)
        after_ts = int(isoparse(earliest_ts).timestamp() * 1000) + 1

    seen = set()
    unique_items = []
    for item in items:
        key = (item["track"]["id"], item["played_at"])
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    total_ms = sum(item["track"]["duration_ms"] for item in unique_items)
    total_minutes = round(total_ms / 60000)

    return {"minutes_played": total_minutes, "days": days}
