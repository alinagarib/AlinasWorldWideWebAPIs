import requests
import urllib.parse
import base64
import os

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SCOPE = " ".join([
    "user-read-playback-state",
    "user-read-currently-playing",
    "streaming",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-read-private",
    "user-top-read",
    "user-read-recently-played",
    "user-read-playback-position"
])


params = {
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE
}
print("Go to this URL and log in:\n")
print("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params))


AUTH_CODE = input("Enter the code from the URL: ")

auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
headers = {"Authorization": f"Basic {auth_header}"}
data = {
    "grant_type": "authorization_code",
    "code": AUTH_CODE,
    "redirect_uri": REDIRECT_URI
}

res = requests.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
print(res.json())
