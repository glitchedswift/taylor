"""Database operations for the Taylor Swift streaming data collector."""

import sqlite3
import logging
from datetime import date
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SongRow:
    title: str
    total_count: int  # total_streams for Spotify, total_views for YouTube
    daily_count: int  # daily_streams for Spotify, daily_views for YouTube
    platform_id: str = None  # Spotify track ID or YouTube video ID
    published_date: date = None  # YouTube published date (YYYY/MM with day set to 1)


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist_id INTEGER NOT NULL,
                spotify_total_streams INTEGER,
                FOREIGN KEY (artist_id) REFERENCES artists(id),
                UNIQUE(track_id, artist_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                artist_id INTEGER NOT NULL,
                youtube_total_views INTEGER,
                published_date DATE,
                FOREIGN KEY (artist_id) REFERENCES artists(id),
                UNIQUE(watch_id, artist_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS spotify_daily_streams (
                date DATE NOT NULL,
                song_id INTEGER NOT NULL,
                daily_streams INTEGER NOT NULL,
                FOREIGN KEY (song_id) REFERENCES songs(id),
                PRIMARY KEY (date, song_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_daily_views (
                date DATE NOT NULL,
                video_id INTEGER NOT NULL,
                daily_views INTEGER NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id),
                PRIMARY KEY (date, video_id)
            )
        """)

        # Create view for Spotify streams with artist and song names
        conn.execute("""
            CREATE VIEW IF NOT EXISTS spotify_streams_view AS
            SELECT
                s.date,
                a.name AS artist_name,
                so.title AS song_name,
                s.daily_streams,
                so.spotify_total_streams AS total_streams,
                'https://open.spotify.com/track/' || so.track_id AS url
            FROM spotify_daily_streams s
            JOIN songs so ON s.song_id = so.id
            JOIN artists a ON so.artist_id = a.id
            ORDER BY s.date DESC, so.spotify_total_streams DESC
        """)
        
        # Create view for YouTube views with artist and video names
        conn.execute("""
            CREATE VIEW IF NOT EXISTS youtube_daily_views_view AS
            SELECT
                v.date,
                a.name AS artist_name,
                vid.title AS video_name,
                v.daily_views,
                vid.youtube_total_views AS total_views,
                'https://www.youtube.com/watch?v=' || vid.watch_id AS url
            FROM youtube_daily_views v
            JOIN videos vid ON v.video_id = vid.id
            JOIN artists a ON vid.artist_id = a.id
            ORDER BY v.date DESC, vid.youtube_total_views DESC
        """)
        
        conn.commit()
        logger.info("Database schema initialized successfully")
    except Exception as exc:
        logger.error(f"Failed to initialize database schema: {exc}")
        raise


def get_or_create_artist(conn: sqlite3.Connection, artist_name: str) -> int:
    """Get existing artist ID or create new one. Returns artist ID."""
    try:
        cur = conn.execute(
            "SELECT id FROM artists WHERE name = ?",
            (artist_name,),
        )
        result = cur.fetchone()
        if result:
            logger.debug(f"Found existing artist '{artist_name}' with ID {result[0]}")
            return result[0]
        
        cur = conn.execute(
            "INSERT INTO artists (name) VALUES (?)",
            (artist_name,),
        )
        conn.commit()
        artist_id = cur.lastrowid
        logger.info(f"Created new artist '{artist_name}' with ID {artist_id}")
        return artist_id
    except Exception as exc:
        logger.error(f"Failed to get or create artist '{artist_name}': {exc}")
        raise


def get_or_create_song(conn: sqlite3.Connection, platform_id: str, title: str, artist_id: int) -> int:
    """Get existing song ID by platform_id (track_id) or create new one. Returns song ID."""
    try:
        cur = conn.execute(
            "SELECT id FROM songs WHERE track_id = ? AND artist_id = ?",
            (platform_id, artist_id),
        )
        result = cur.fetchone()
        if result:
            logger.debug(f"Found existing song with platform_id '{platform_id}' with ID {result[0]}")
            return result[0]
        
        cur = conn.execute(
            "INSERT INTO songs (track_id, title, artist_id) VALUES (?, ?, ?)",
            (platform_id, title, artist_id),
        )
        conn.commit()
        song_id = cur.lastrowid
        logger.info(f"Created new song '{title}' (platform_id: {platform_id}) with ID {song_id}")
        return song_id
    except Exception as exc:
        logger.error(f"Failed to get or create song with platform_id '{platform_id}': {exc}")
        raise


def get_or_create_video(conn: sqlite3.Connection, platform_id: str, title: str, artist_id: int) -> int:
    """Get existing video ID by platform_id (watch_id) or create new one. Returns video ID."""
    try:
        cur = conn.execute(
            "SELECT id FROM videos WHERE watch_id = ? AND artist_id = ?",
            (platform_id, artist_id),
        )
        result = cur.fetchone()
        if result:
            logger.debug(f"Found existing video with platform_id '{platform_id}' with ID {result[0]}")
            return result[0]
        
        cur = conn.execute(
            "INSERT INTO videos (watch_id, title, artist_id) VALUES (?, ?, ?)",
            (platform_id, title, artist_id),
        )
        conn.commit()
        video_id_result = cur.lastrowid
        logger.info(f"Created new video '{title}' (platform_id: {platform_id}) with ID {video_id_result}")
        return video_id_result
    except Exception as exc:
        logger.error(f"Failed to get or create video with platform_id '{platform_id}': {exc}")
        raise


def daily_data_exists(conn: sqlite3.Connection, snapshot_date: date, platform: str) -> bool:
    """Check if daily data for a specific platform and date already exists."""
    try:
        # Map platform to table name
        if platform == "spotify":
            table_name = "spotify_daily_streams"
        elif platform == "youtube":
            table_name = "youtube_daily_views"
        else:
            logger.error(f"Unknown platform: {platform}")
            raise ValueError(f"Unknown platform: {platform}")
        
        cur = conn.execute(
            f"SELECT 1 FROM {table_name} WHERE date = ? LIMIT 1",
            (snapshot_date.isoformat(),),
        )
        return cur.fetchone() is not None
    except Exception as exc:
        logger.error(f"Failed to check if daily data exists for {platform} on {snapshot_date}: {exc}")
        raise


def upsert_data(
    conn: sqlite3.Connection,
    snapshot_date: date,
    songs: List[SongRow],
    artist_name: str,
    platform: str,
) -> None:
    """Upsert streaming data for a specific artist, platform, and date."""
    try:
        cur = conn.cursor()

        # Get or create artist
        artist_id = get_or_create_artist(conn, artist_name)

        # Map platform to column names and table names
        if platform == "spotify":
            total_col = "spotify_total_streams"
            table_name = "spotify_daily_streams"
            daily_col = "daily_streams"
            item_table = "songs"
            id_col = "song_id"
        elif platform == "youtube":
            total_col = "youtube_total_views"
            table_name = "youtube_daily_views"
            daily_col = "daily_views"
            item_table = "videos"
            id_col = "video_id"
        else:
            logger.error(f"Unknown platform: {platform}")
            raise ValueError(f"Unknown platform: {platform}")

        inserted_count = 0
        for item in songs:
            # Get or create song/video based on platform
            if platform == "spotify":
                item_id = get_or_create_song(conn, item.platform_id, item.title, artist_id)
            else:
                item_id = get_or_create_video(conn, item.platform_id, item.title, artist_id)

            # Update platform-specific total count in songs/videos table
            if platform == "youtube" and item.published_date:
                # For YouTube videos with published date, update both columns at once
                cur.execute(
                    f"""
                    UPDATE {item_table}
                    SET {total_col} = ?, published_date = ?
                    WHERE id = ?
                    """,
                    (item.total_count, item.published_date, item_id),
                )
            else:
                # For Spotify or YouTube without published_date, just update total
                cur.execute(
                    f"""
                    UPDATE {item_table}
                    SET {total_col} = ?
                    WHERE id = ?
                    """,
                    (item.total_count, item_id),
                )

            # Insert daily platform-specific counts (no duplicates due to PK)
            cur.execute(
                f"""
                INSERT OR IGNORE INTO {table_name}
                (date, {id_col}, {daily_col})
                VALUES (?, ?, ?)
                """,
                (
                    snapshot_date.isoformat(),
                    item_id,
                    item.daily_count,
                ),
            )
            inserted_count += 1

        conn.commit()
        logger.info(f"Successfully upserted {inserted_count} items for {artist_name} ({platform}) on {snapshot_date}")
    except Exception as exc:
        logger.error(f"Failed to upsert data for {artist_name} ({platform}): {exc}")
        raise


def verify_daily_data_count(
    conn: sqlite3.Connection,
    snapshot_date: date,
    expected_count: int,
    platform: str,
) -> bool:
    """Verify that the number of records in the database for a specific date matches the expected count."""
    try:
        # Map platform to table name
        if platform == "spotify":
            table_name = "spotify_daily_streams"
        elif platform == "youtube":
            table_name = "youtube_daily_views"
        else:
            logger.error(f"Unknown platform: {platform}")
            raise ValueError(f"Unknown platform: {platform}")
        
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE date = ?",
            (snapshot_date.isoformat(),),
        )
        actual_count = cur.fetchone()[0]
        
        if actual_count == expected_count:
            logger.info(f"Verified: {actual_count} records in database match expected count of {expected_count} for {platform} on {snapshot_date}")
            return True
        else:
            logger.error(f"Verification failed: Expected {expected_count} records for {platform} on {snapshot_date}, but found {actual_count}")
            return False
    except Exception as exc:
        logger.error(f"Failed to verify daily data count for {platform} on {snapshot_date}: {exc}")
        raise
