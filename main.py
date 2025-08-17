from fastapi import FastAPI
from WikiRaceAPI.fastestPath import app as wiki_race_app
from SpotifyAPI.spotifyStats import app as spotify_stats_app
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

main_app = FastAPI()

main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],    
    allow_headers=["*"],
)

main_app.include_router(wiki_race_app.router, prefix="/wiki-race", tags=["WikiRace"])
main_app.include_router(spotify_stats_app.router, prefix="/spotify-stats", tags=["SpotifyStats"])

if __name__ == "__main__":
    uvicorn.run(main_app, host="0.0.0.0", port=8000)
