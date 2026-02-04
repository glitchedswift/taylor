"""Configuration settings for the Taylor Swift streaming data collector."""

# Database configuration
DB_PATH: str = "db/taylor_swift_streams.sqlite"

# Artist and platform configuration
ARTIST_CONFIGS = {
    "Taylor Swift": {
        "spotify": "https://kworb.net/spotify/artist/06HL4z0CvFAxyc27GXpf02_songs.html",
        "youtube": "https://kworb.net/youtube/artist/taylorswift.html",
    }
}

# Platforms to load data for
PLATFORMS = ["spotify", "youtube"]

# Logging configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(filename)s:%(funcName)s:%(lineno)d] - %(message)s'
