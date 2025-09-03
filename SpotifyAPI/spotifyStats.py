from fastapi import APIRouter, Query
import requests
import os
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
import time


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
def recent_summary(limit: int = 3, days: int = 3):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Make cutoff_time timezone-aware (UTC)
    cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days)
    items = []
    before_ts = None
    batch_count = 0

    while True:
        batch_count += 1
        # Build URL with before parameter for pagination
        if before_ts:
            url = f"https://api.spotify.com/v1/me/player/recently-played?before={before_ts}&limit=50"
        else:
            url = f"https://api.spotify.com/v1/me/player/recently-played?limit=50"
        
        print(f"🔄 Batch {batch_count}: {url}")
        response = requests.get(url, headers=headers)

        if response.status_code == 429:  
            retry_after = int(response.headers.get("Retry-After", "1"))
            time.sleep(retry_after)
            continue

        response.raise_for_status()
        batch = response.json().get("items", [])
        
        if not batch:
            print(f"❌ No more items returned, stopping pagination")
            break

        # Check if we've gone back far enough in time
        oldest_in_batch = min(isoparse(item["played_at"]) for item in batch)
        newest_in_batch = max(isoparse(item["played_at"]) for item in batch)
        
        print(f"📅 Batch {batch_count}: {len(batch)} items")
        print(f"   Oldest: {oldest_in_batch}")
        print(f"   Newest: {newest_in_batch}")
        print(f"   Cutoff: {cutoff_time}")
        print(f"   Oldest < Cutoff? {oldest_in_batch < cutoff_time}")
        
        if oldest_in_batch < cutoff_time:
            # Filter out items older than our cutoff and add the rest
            valid_items = [
                item for item in batch 
                if isoparse(item["played_at"]) >= cutoff_time
            ]
            print(f"✅ Found cutoff point, adding {len(valid_items)} valid items from this batch")
            items.extend(valid_items)
            break
        
        # All items in this batch are within our time range
        items.extend(batch)
        print(f"➕ Added all {len(batch)} items from batch {batch_count}")
        
        # Set before_ts to the oldest item's timestamp for next iteration
        before_ts = int(oldest_in_batch.timestamp() * 1000)
        print(f"⏭️  Next before_ts: {before_ts}")

    print(f"🏁 Pagination complete: {batch_count} batches, {len(items)} total items")

    # Remove duplicates (same track played at same time)
    seen = set()
    unique_items = []
    for item in items:
        key = (item["track"]["id"], item["played_at"])
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    # Calculate total listening time from unique items only
    total_ms = sum(item["track"]["duration_ms"] for item in unique_items)
    total_minutes = round(total_ms / 60000)

    # Count track plays and collect track info
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

    # Debug prints for server logs
    print(f"🎵 Spotify Summary Debug:")
    print(f"  - Total items fetched: {len(items)}")
    print(f"  - Unique items after dedup: {len(unique_items)}")
    print(f"  - Total unique tracks: {len(track_counts)}")
    print(f"  - Cutoff time: {cutoff_time.isoformat()}")
    print(f"  - Top 10 track play counts:")
    for track_id, count in track_counts.most_common(10):
        track_name = track_info[track_id]["name"]
        artist = track_info[track_id]["artist"]
        print(f"    * '{track_name}' by {artist}: {count} plays")

    top_tracks = [
        {**track_info[track_id], "plays": count}
        for track_id, count in track_counts.most_common(limit)
    ]

    # Optional: Add debug info (remove in production)
    debug_info = {
        "total_items_fetched": len(items),
        "unique_items_after_dedup": len(unique_items),
        "cutoff_time": cutoff_time.isoformat()
    }

    return {
        "minutes_played": total_minutes,
        "days": days,
        "top_tracks": top_tracks,
        "debug": debug_info  # Remove this in production
    }