# test_bfs.py
import time
import asyncio
from fastestPath import find_wikipedia_path

if __name__ == "__main__":
    start_page = "https://en.wikipedia.org/wiki/Combination"
    end_page = "https://en.wikipedia.org/wiki/Guppy"

    start = time.time()
    path = asyncio.run(find_wikipedia_path(start_page, end_page))
    end = time.time()
    print(f"Search completed in {end - start:.2f} seconds.")

    if path:
        print("\nPath found:")
        for step in path:
            print(f" → {step}")
        print(f"\nLength: {len(path) - 1} steps")
    else:
        print("\nNo path found.")
