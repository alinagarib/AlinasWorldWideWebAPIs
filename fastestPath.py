from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from collections import deque
import time
import random
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="Wikipedia Path Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------
class WikiPathRequest(BaseModel):
    start: str 
    end: str    


def get_wikipedia_links(url):
    headers = {
        "User-Agent": "FastestWikiRaceBot/1.0 (https://www.alinasworldwideweb.com; alinahgarib@gmail.com)"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return []

    time.sleep(random.uniform(1, 3))
    soup = BeautifulSoup(response.text, 'html.parser')
    links = []

    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        if href.startswith('/wiki/') and not (':' in href or '#' in href or '?' in href) and "en.wikipedia.org" in url:
            full_url = "https://en.wikipedia.org" + href
            links.append(full_url)

    return list(set(links))


def find_wikipedia_path(start, end):
    queue = deque([(start, [start])])
    visited = set([start])

    while queue:
        current, path = queue.popleft()

        links = get_wikipedia_links(current)
        for link in links:
            if link == end:
                return path + [end]  

            if link not in visited:
                visited.add(link)
                queue.append((link, path + [link]))

    return None

# ---------- API Endpoint ----------
@app.post("/find-path")
def find_path(request: WikiPathRequest):
    start = request.start
    end = request.end

    path = find_wikipedia_path(start, end)
    if path:
        return {"path": path, "length": len(path)}
    else:
        raise HTTPException(status_code=404, detail="No path found")