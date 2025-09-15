import os
import requests
import base64
import boto3
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
from collections import Counter
import time
from decimal import Decimal


# ----------- Environment Variables ----------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

MY_USER_ID = "alinagrb"
SKIP_THRESHOLD_SECONDS = 20
SUMMARY_ID = "recent"

LISTENING_HISTORY_TABLE = os.environ.get("LISTENING_HISTORY_TABLE")
ARTISTS_TRACK_TABLE = os.environ.get("ARTISTS__ALBUMS_TRACK_TABLE")
RECENT_SUMMARY_TABLE = os.environ.get("RECENT_SUMMARY_TABLE")

dynamodb = boto3.resource('dynamodb')
listening_history_table = dynamodb.Table(LISTENING_HISTORY_TABLE)
artists_track_table = dynamodb.Table(ARTISTS_TRACK_TABLE)
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

def get_last_played_at():
    """Fetches the played_at timestamp of the last entry from DynamoDB."""
    try:
        response = listening_history_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(MY_USER_ID),
            ScanIndexForward=False,
            Limit=1
        )
        if response['Items']:
            return int(response['Items'][0]['played_at_timestamp'])
        return None
    except Exception as e:
        print(f"Error getting last played_at: {e}")
        return None
    
def get_last_three_days_tracks():
    """Fetches tracks from the last three days of listening history."""
    three_days_ago_timestamp_ms = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp() * 1000)
    last_three_days_tracks = []
    
    query_params = {
        'KeyConditionExpression': boto3.dynamodb.conditions.Key('user_id')
        .eq(MY_USER_ID) & boto3.dynamodb
        .conditions.Key('played_at_timestamp')
        .gte(three_days_ago_timestamp_ms)
    }

    try:
        while True:
            response = listening_history_table.query(**query_params)
            last_three_days_tracks.extend(response.get('Items', []))
            
            if 'LastEvaluatedKey' in response:
                query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
            else:
                break
        
        return last_three_days_tracks

    except Exception as e:
        print(f"Error fetching last 3 days of tracks: {e}")
        return None
    

# ---------- Main Lambda Handler ----------
def lambda_handler(event, context):
    try:
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        last_played_at_timestamp = get_last_played_at()

        base_url = "https://api.spotify.com/v1/me/player/recently-played"
        if last_played_at_timestamp:
            next_url = f"{base_url}?after={last_played_at_timestamp}&limit=50"
        else:
            next_url = f"{base_url}?limit=50"

        new_tracks = []
        while next_url:
            print(f"Fetching: {next_url}")
            response = requests.get(next_url, headers=headers)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "3"))
                print(f"Rate limit hit. Waiting for {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            new_tracks.extend(data.get("items", []))
            
            # The next URL to fetch is provided directly by the API
            next_url = data.get("next")
            if not next_url:
                print("No more pages to fetch. Stopping pagination.")

        new_tracks.sort(key=lambda x: isoparse(x["played_at"]))
        filtered_tracks = []

        if len(new_tracks) > 0:
            filtered_tracks.append(new_tracks[0]) 
            
            for i in range(1, len(new_tracks)):
                current_track = new_tracks[i]
                previous_track = new_tracks[i-1]
                
                current_time = isoparse(current_track["played_at"])
                previous_time = isoparse(previous_track["played_at"])
                
                time_difference = (current_time - previous_time).total_seconds()
                
                # checks if the song is a skip
                if time_difference > SKIP_THRESHOLD_SECONDS:
                    filtered_tracks.append(current_track)
        
        print(f"Found {len(new_tracks)} new tracks to ingest.")
        print(f"Found {len(filtered_tracks)} tracks after filtering for skips.")
    
        # --- Write new tracks to DynamoDB ---
        with listening_history_table.batch_writer() as batch:
            for item in new_tracks:
                track = item["track"]
                batch.put_item(
                    Item={
                        'user_id': MY_USER_ID,
                        'played_at': item["played_at"], # ISO string
                        'played_at_timestamp': int(isoparse(item["played_at"]).timestamp() * 1000), # Unix timestamp in milliseconds, for api calls
                        'track_id': track["id"],
                        'track_name': track["name"],
                        'artist_name': ", ".join([a["name"] for a in track["artists"]]),
                        'duration_ms': track["duration_ms"],
                        'album': track["album"]["name"],
                        'album_art': track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                        'preview_url': track["preview_url"]
                    }
                )

        # Save data to artist album track listening history
        for item in filtered_tracks:
            track = item["track"]
            album_name = track["album"]["name"]
            
            artists = ", ".join([a["name"] for a in track["artists"]])

            pk = f"ARTIST#{artists}"
            sk = f"TRACK#{album_name}#{track['name']}"

            artists_track_table.update_item(
                Key={
                    'PK': pk,
                    'SK': sk
                },
                UpdateExpression='SET artist_name = :artist, album_name = :album, track_name = :track ADD listen_count :inc',
                ExpressionAttributeValues={
                    ':artist': artists,
                    ':album': album_name,
                    ':track': track["name"],
                    ':inc': 1
                }
            )

        # --- Aggregation Logic ---
        last_three_days_data = get_last_three_days_tracks()
        
        if last_three_days_data is not None:
            print(f"Successfully fetched {len(last_three_days_data)} tracks from the last 3 days for aggregation.")
            
            # 1. Calculate total minutes listened
            total_duration_ms = sum([item['duration_ms'] for item in last_three_days_data])
            total_minutes = round(total_duration_ms / 60000)

            # 2. Get the top three most-listened-to tracks
            tracks_counter = Counter([item['track_name'] for item in last_three_days_data])
            on_repeat_tracks = tracks_counter.most_common(3)
            
            # 3. Collect track info for the top tracks from the last 3 days
            track_info_map = {}
            for item in last_three_days_data:
                track_name = item['track_name']
                if track_name not in track_info_map:
                    track_info_map[track_name] = {
                        'track_name': item['track_name'],
                        'artist_name': item['artist_name'],
                        'album_name': item.get('album', 'N/A'),  
                        'album_art': item.get('album_art', 'N/A')
                    }

            formatted_on_repeat_tracks = []
            for track_name, listen_count in on_repeat_tracks:  
                track_details = track_info_map.get(track_name, {})
                formatted_on_repeat_tracks.append({
                    'track_name': track_details.get('track_name'),
                    'artist_name': track_details.get('artist_name'),
                    'album_name': track_details.get('album_name'),
                    'album_art': track_details.get('album_art'),
                    'listen_count': listen_count
                })

            # 4. Save the summary to the recent_summary_table
            recent_summary_table.update_item(
                Key={
                    'summary_id': SUMMARY_ID
                },
                UpdateExpression='SET total_minutes = :minutes, on_repeat_tracks = :tracks, last_updated_timestamp = :timestamp',
                ExpressionAttributeValues={
                    ':minutes': total_minutes,
                    ':tracks': formatted_on_repeat_tracks,
                    ':timestamp': int(datetime.now(timezone.utc).timestamp())
                }
            )
            print("Successfully saved recent summary to DynamoDB.")
            
        else:
            print("Could not retrieve data for aggregation.")
        
    except Exception as e:
        print(f"Error during data ingestion: {e}")
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
        }

    return {
            'statusCode': 200,
            'body': f'Successfully processed {len(new_tracks)} tracks'
        }