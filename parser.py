"""HTML parsing utilities for extracting streaming data."""

import html
import logging
import requests
from datetime import date, datetime
from typing import List

from bs4 import BeautifulSoup

from database import SongRow


logger = logging.getLogger(__name__)


def parse_int(value: str) -> int:
    """Convert a comma-separated integer string to int."""
    try:
        return int(value.replace(",", "").strip())
    except ValueError as exc:
        logger.error(f"Invalid integer value: {value}")
        raise ValueError(f"Invalid integer value: {value}") from exc


def clean_title(title: str) -> str:
    """Decode HTML entities and remove asterisks."""
    # Properly decode HTML entities
    title = html.unescape(title)
    # Remove asterisks
    title = title.replace("*", "")
    return title.strip()


def fetch_html(url: str) -> str:
    """Fetch HTML from URL with proper encoding handling."""
    try:
        logger.info(f"Fetching HTML from {url}")
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        # Ensure proper encoding - handle potential encoding issues
        response.encoding = response.apparent_encoding or 'utf-8'
        logger.info(f"Successfully fetched HTML from {url}")
        return response.text
    except requests.RequestException as exc:
        logger.error(f"Failed to fetch page from {url}: {exc}")
        raise RuntimeError(f"Failed to fetch page: {exc}") from exc


def extract_last_updated(soup: BeautifulSoup, platform: str = "spotify") -> date:
    """
    Extracts last updated date from HTML.
    Spotify: Looks for 'Last updated: YYYY/MM/DD'
    YouTube: Uses current date since YouTube doesn't provide update timestamps
    """
    try:
        if platform == "youtube":
            # YouTube doesn't provide a last updated date, so use today
            logger.info("YouTube data - using current date as snapshot")
            return datetime.now().date()
        
        # Spotify format
        text = soup.find(string=lambda s: s and "Last updated:" in s)
        if not text:
            logger.warning("Last updated date not found in HTML")
            raise ValueError("Last updated date not found")

        date_str = text.split("Last updated:")[1].strip()
        parsed_date = datetime.strptime(date_str, "%Y/%m/%d").date()
        logger.info(f"Extracted last updated date: {parsed_date}")
        return parsed_date
    except Exception as exc:
        logger.error(f"Failed to parse last updated date: {exc}")
        raise RuntimeError("Failed to parse last updated date") from exc


def parse_song_table(soup: BeautifulSoup) -> List[SongRow]:
    """
    Parse Spotify song table from HTML.
    Columns: title, total_streams, daily_streams
    Extracts track_id from the song href URL.
    """
    try:
        table = soup.find("table", class_="addpos")
        if not table:
            logger.warning("Song table not found in HTML")
            raise ValueError("Song table not found")

        rows: List[SongRow] = []

        for tr in table.tbody.find_all("tr", recursive=False):
            tds = tr.find_all("td")
            if len(tds) != 3:
                logger.warning(f"Skipping row with {len(tds)} columns (expected 3)")
                continue

            title_tag = tds[0].find("a")
            if not title_tag:
                logger.warning("Skipping row with no title link")
                continue

            title = clean_title(title_tag.text)
            
            # Extract track_id from href URL
            href = title_tag.get("href", "")
            track_id = None
            if href:
                # URL format: https://open.spotify.com/track/273dCMFseLcVsoSWx59IoE
                parts = href.rstrip('/').split('/')
                if len(parts) > 0:
                    track_id = parts[-1]
                    logger.debug(f"Extracted track_id '{track_id}' from URL: {href}")
            
            if not track_id:
                logger.warning(f"Skipping row '{title}' - could not extract track_id from URL: {href}")
                continue
            
            total_count = parse_int(tds[1].text)
            daily_count = parse_int(tds[2].text)

            rows.append(
                SongRow(
                    title=title,
                    total_count=total_count,
                    daily_count=daily_count,
                    platform_id=track_id,
                )
            )

        if not rows:
            logger.warning("No songs were parsed from the table")
            raise ValueError("No songs parsed")

        logger.info(f"Successfully parsed {len(rows)} Spotify songs")
        return rows

    except Exception as exc:
        logger.error(f"Failed to parse Spotify songs: {exc}")
        raise RuntimeError("Failed to parse Spotify songs") from exc


def parse_video_table(soup: BeautifulSoup) -> List[SongRow]:
    """
    Parse YouTube video table from HTML.
    Columns: title, total_views, yesterday_views, published_date (YYYY/MM)
    Extracts video_id from the video href URL.
    """
    try:
        table = soup.find("table", class_="addpos")
        if not table:
            logger.warning("Video table not found in HTML")
            raise ValueError("Video table not found")

        rows: List[SongRow] = []

        for tr in table.tbody.find_all("tr", recursive=False):
            tds = tr.find_all("td")
            if len(tds) != 4:
                logger.warning(f"Skipping row with {len(tds)} columns (expected 4)")
                continue

            title_tag = tds[0].find("a")
            if not title_tag:
                continue

            title = clean_title(title_tag.text)
            
            # Extract video_id from href URL
            href = title_tag.get("href", "")
            video_id = None
            if href:
                # Handle URL formats:
                # 1. kworb.net (full): https://kworb.net/youtube/video/yfWgXcrNQIw.html
                # 2. kworb.net (relative): ../video/yfWgXcrNQIw.html
                # 3. youtube.com: https://www.youtube.com/watch?v=-ddfFsLHNQs
                
                if "/video/" in href:
                    # Extract video_id from kworb.net format (full or relative)
                    parts = href.rstrip('/').split('/')
                    if len(parts) > 0:
                        filename = parts[-1]
                        if filename.endswith('.html'):
                            video_id = filename[:-5]  # Remove .html
                            logger.debug(f"Extracted video_id '{video_id}' from kworb.net URL: {href}")
                elif "youtube.com" in href:
                    # Extract video_id from youtube.com format
                    if "v=" in href:
                        video_id = href.split("v=")[1].split("&")[0]
                        logger.debug(f"Extracted video_id '{video_id}' from YouTube URL: {href}")
            
            if not video_id:
                logger.warning(f"Skipping row '{title}' - could not extract video_id from URL: {href}")
                continue
            
            # Extract and validate counts, skip if empty
            total_text = tds[1].text.strip()
            daily_text = tds[2].text.strip()

            if daily_text == "":
                daily_text = "0"
            
            if not total_text or not daily_text:
                logger.warning(f"Skipping row '{title}' - empty count columns")
                continue
            
            total_count = parse_int(total_text)
            daily_count = parse_int(daily_text)
            
            # Extract published date from column 3 (format: YYYY/MM)
            published_date = None
            try:
                date_str = tds[3].text.strip()
                if date_str:  # Only parse if not empty
                    # Parse YYYY/MM format and set day to 1
                    published_date = datetime.strptime(f"{date_str}/1", "%Y/%m/%d").date()
                    logger.debug(f"Parsed published date for '{title}': {published_date}")
            except Exception as e:
                logger.warning(f"Failed to parse published date '{date_str}' for '{title}': {e}")

            rows.append(
                SongRow(
                    title=title,
                    total_count=total_count,
                    daily_count=daily_count,
                    platform_id=video_id,
                    published_date=published_date,
                )
            )

        if not rows:
            logger.warning("No videos were parsed from the table")
            raise ValueError("No videos parsed")

        logger.info(f"Successfully parsed {len(rows)} YouTube videos")
        return rows

    except Exception as exc:
        logger.error(f"Failed to parse YouTube videos: {exc}")
        raise RuntimeError("Failed to parse YouTube videos") from exc
