from __future__ import annotations

import sqlite3
import logging
from bs4 import BeautifulSoup

from config import DB_PATH, ARTIST_CONFIGS, PLATFORMS, LOG_LEVEL, LOG_FORMAT
from database import init_db, daily_data_exists, upsert_data, verify_daily_data_count
from parser import fetch_html, extract_last_updated, parse_song_table, parse_video_table

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting data collection")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            init_db(conn)

            for artist_name, platforms in ARTIST_CONFIGS.items():
                logger.info(f"Processing artist: {artist_name}")
                for platform in PLATFORMS:
                    url = platforms.get(platform)
                    if not url:
                        logger.info(f"Skipping {artist_name} - {platform}: no URL configured")
                        continue

                    try:
                        logger.info(f"Processing {artist_name} ({platform})")
                        html = fetch_html(url)
                        soup = BeautifulSoup(html, "html.parser")

                        snapshot_date = extract_last_updated(soup, platform)
                        
                        # Call appropriate parser based on platform
                        if platform == "spotify":
                            songs = parse_song_table(soup)
                        elif platform == "youtube":
                            songs = parse_video_table(soup)
                        else:
                            logger.error(f"Unknown platform: {platform}")
                            continue

                        if daily_data_exists(conn, snapshot_date, platform):
                            logger.info(f"Daily data for {artist_name} ({platform}) on {snapshot_date} already exists. Skipping.")
                            continue

                        logger.info(f"Inserting songs for {artist_name} ({platform}) on snapshot date {snapshot_date}")
                        upsert_data(conn, snapshot_date, songs, artist_name, platform)

                        verify_daily_data_count(conn, snapshot_date, len(songs), platform)

                    except Exception as exc:
                        logger.error(f"Error loading {artist_name} - {platform}: {exc}")
        
        logger.info("Data collection completed successfully")
    except Exception as exc:
        logger.critical(f"Critical error during main execution: {exc}")
        raise

if __name__ == "__main__":
    main()
