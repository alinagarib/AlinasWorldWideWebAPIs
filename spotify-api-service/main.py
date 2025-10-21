from dotenv import load_dotenv
load_dotenv() 

from fastapi import FastAPI
from mangum import Mangum
from fastapi import FastAPI
from mangum import Mangum
from fastapi import Query
import requests
import os
import base64
import boto3

# Create FastAPI app
app = FastAPI()
handler = Mangum(app)


# Health check endpoint
@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "Lambda is working"}

# ----------- Environment Variables ----------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
RECENT_SUMMARY_TABLE = os.environ.get("RECENT_SUMMARY_TABLE")
LISTENING_HISTORY_TABLE = os.environ.get("LISTENING_HISTORY_TABLE")
dynamodb = boto3.resource('dynamodb')
recent_summary_table = dynamodb.Table(RECENT_SUMMARY_TABLE)
listening_history_table = dynamodb.Table(LISTENING_HISTORY_TABLE)

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
@app.get("/now-playing")
def now_playing():
    token = get_access_token()
    url = "https://api.spotify.com/v1/me/player/currently-playing?additional_types=track,episode"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 204 or response.status_code >= 400:
        return {"is_playing": False}
    
    response.raise_for_status()
    data = response.json()

    currently_playing_type = data.get("currently_playing_type", "track")
    item = data.get("item")

    if not item:
        return {"is_playing": False}

    if currently_playing_type == "episode":
        return {
            "is_playing": data["is_playing"],
            "type": "episode",
            "name": item["name"],
            "show_name": item["show"]["name"],
            "publisher": item["show"]["publisher"],
            "description": item.get("description", ""),
            "image": item["images"][0]["url"] if item.get("images") else None,
            "progress_ms": data.get("progress_ms"),
            "duration_ms": item["duration_ms"]
    }
    else:
        return {
            "is_playing": data["is_playing"],
            "song": data["item"]["name"],
            "artist": ", ".join([artist["name"] for artist in data["item"]["artists"]]),
            "album": data["item"]["album"]["name"],
            "album_art": data["item"]["album"]["images"][0]["url"],
            "progress_ms": data.get("progress_ms"),
            "duration_ms": data["item"]["duration_ms"] if data.get("item") else None
        }


@app.get("/profile")
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



@app.get("/top-tracks")
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


@app.get("/top-artists")
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


@app.get("/recent-summary")
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

@app.get("/listening-history")
def get_listening_history(limit: int = Query(10, ge=1, le=100)):
    try:
        response = listening_history_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq('alinagrb'),
            ScanIndexForward=False,  # Get most recent first
            Limit=limit
        )
        
        tracks = response.get('Items', [])
        
        if not tracks:
            return {"message": "No listening history found.", "tracks": []}
        
        formatted_tracks = [
            {
                "track_name": track.get('track_name'),
                "artist_name": track.get('artist_name'),
                "album": track.get('album'),
                "album_art": track.get('album_art'),
                "played_at": track.get('played_at'),
                "duration_ms": int(track.get('duration_ms', 0)),
                "preview_url": track.get('preview_url')
            }
            for track in tracks
        ]
        
        return {
            "count": len(formatted_tracks),
            "tracks": formatted_tracks
        }
    
    except Exception as e:
        print(f"Error fetching listening history: {e}")
        return {"error": "Could not retrieve listening history data."}

@app.get("/recent-listening")
def get_recent_listening(limit: int = Query(10, ge=1, le=50)):
    token = get_access_token()
    url = f"https://api.spotify.com/v1/me/player/recently-played?limit={limit}"    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    recent_tracks = []
    
    for item in data.get("items", []):
        track_details = item.get("track")
        
        if not track_details:
            continue
            
        try:
            recent_tracks.append({
                'track_id': track_details["id"],
                'track_name': track_details["name"],
                'artist_name': ", ".join([a["name"] for a in track_details["artists"]]),
                'album': track_details["album"]["name"],
                'album_art': track_details["album"]["images"][0]["url"] if track_details["album"]["images"] else None,
                'preview_url': track_details["preview_url"]
            })
        except KeyError as e:
            print(f"Warning: Track item missing key: {e} in {track_details.get('id')}")
            continue

    return recent_tracks
