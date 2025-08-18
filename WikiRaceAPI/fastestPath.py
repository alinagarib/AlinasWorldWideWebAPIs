from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
from collections import deque
import time
import random
import logging
import asyncio
import aiohttp
from async_lru import alru_cache


router = APIRouter()

# ---------- Models ----------
class WikiPathRequest(BaseModel):
    start: str 
    end: str    

# ---------- Logging Configuration ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------- Global Variables ----------
headers = {
    "User-Agent": "FastestWikiRaceBot/1.0 (https://www.alinasworldwideweb.com; alinahgarib@gmail.com)"
}
semaphore = asyncio.Semaphore(20)
MAX_DEPTH = 6  

# ---------- Helper Functions ----------

@alru_cache(maxsize=1000)
async def get_wikipedia_links(url, session):
    start_time = time.time()
    logging.debug(f"Fetching: {url}")

    try:
        async with semaphore:
            async with session.get(url, headers=headers) as response:
                await  asyncio.sleep(random.uniform(0.1, 1.0))
                html = await response.text()
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching URL: {e}")
        return []
    
    elapsed = time.time() - start_time
    logging.debug(f"Fetched {url} in {elapsed:.2f}s")

    soup = BeautifulSoup(html, 'html.parser')
    links = []

    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        if href.startswith('/wiki/') and not (':' in href or '#' in href or '?' in href) and ("en.wikipedia.org" in url or "en.m.wikipedia.org" in url):
            full_url = "https://en.wikipedia.org" + href
            links.append(full_url)

    return list(set(links))

async def wrapped_get_links(url, path, session):
    links = await get_wikipedia_links(url, session)
    return path, links

async def find_wikipedia_path(start, end):
    logger.info(f"Starting BFS from {start} to {end}")
    search_start_time = time.time()

    queue = [(start, [start])]
    visited = set([start])
    steps = 0

    async with aiohttp.ClientSession() as session:
        while queue:
            current_level = queue
            queue = []
            steps += 1

            logger.info(f"Processing BFS depth {steps} with {len(current_level)} nodes")

            tasks = [asyncio.create_task(wrapped_get_links(url, path, session)) for url, path in current_level]

            for coro in asyncio.as_completed(tasks):
                path, links = await coro
                if end in links:
                    logger.info(f"Found path in {time.time() - search_start_time:.2f}s and {steps} steps.")
                    return path + [end]
                
                for link in links:
                    if link not in visited:
                        visited.add(link)
                        queue.append((link, path + [link]))

            if steps >= MAX_DEPTH:
                logger.warning(f"Search terminated after {steps} steps due to excessive depth.")
                return None

    logger.warning(f"No path found after {steps} steps in {time.time() - search_start_time:.2f}s")
    return None

# ---------- API Endpoint ----------
@app.post("/find-path")
async def find_path(request: WikiPathRequest):
    start = request.start
    end = request.end

    path = await find_wikipedia_path(start, end)
    if path:
        return {"path": path, "length": len(path)}
    elif path is None:
        raise HTTPException(status_code=422, detail="Search terminated due to excessive depth")
    else:
        raise HTTPException(status_code=404, detail="No path found")