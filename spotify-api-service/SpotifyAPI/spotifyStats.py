from fastapi import APIRouter, Query
import requests
import os
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
import boto3
import time


router = APIRouter()

# ----------- Environment Variables ----------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
RECENT_SUMMARY_TABLE = os.environ.get("RECENT_SUMMARY_TABLE")
dynamodb = boto3.resource('dynamodb')
recent_summary_table = dynamodb.Table(RECENT_SUMMARY_TABLE)

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



@router.get("/recent-summary")
def get_recent_summary():
    """Fetches the pre-aggregated recent summary from DynamoDB."""
    try:
        response = recent_summary_table.get_item(
            Key={
                'summary_id': 'recent'
            }
        )
        item = response.get('Item')
        
        if not item:
            return {"message": "No recent summary data found. Please wait for the ingestion process to run."}
        
        if 'total_minutes' in item:
            item['total_minutes'] = int(item['total_minutes'])
        
        return {
            "minutes_played": item.get('total_minutes'),
            "top_tracks": item.get('on_repeat_tracks'),
            "artist": item.get('top_artist'),
            "unique_artists": item.get('unique_artists'),
            "last_updated": item.get('last_updated_timestamp') 
        }

    except Exception as e:
        print(f"Error fetching recent summary from DynamoDB: {e}")
        return {"error": "Could not retrieve recent summary data."}