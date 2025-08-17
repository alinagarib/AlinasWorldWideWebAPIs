from fastapi import FastAPI
from WikiRaceAPI.fastestPath import app as wiki_race_app
from SpotifyAPI.spotifyAuth import app as spotify_auth_app
from SpotifyAPI.spotifyStats import app as spotify_stats_app

# Create the main FastAPI app
main_app = FastAPI()

# Include routers from individual APIs
main_app.include_router(wiki_race_app.router, prefix="/wiki-race", tags=["WikiRace"])
main_app.include_router(spotify_auth_app.router, prefix="/spotify-auth", tags=["SpotifyAuth"])
main_app.include_router(spotify_stats_app.router, prefix="/spotify-stats", tags=["SpotifyStats"])

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main_app, host="0.0.0.0", port=8000)
