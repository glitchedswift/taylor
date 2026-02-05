"""Web interface for browsing Taylor Swift streaming data."""

import sqlite3
import json
from flask import Flask, render_template, request, jsonify, redirect
from config import DB_PATH
from datetime import datetime

app = Flask(__name__)


def get_db_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def extract_video_id(url):
    """Extract video ID from YouTube URL."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    return None


@app.route('/')
def index():
    """Main explore page - unified view for songs and videos."""
    conn = get_db_connection()
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    date_filter = request.args.get('date', '')
    sort_by = request.args.get('sort', 'date')
    order = request.args.get('order', 'desc')
    
    # Get Spotify data
    spotify_query = """SELECT so.id as song_id, s.date, a.name AS artist_name, so.title AS song_name,
                              s.daily_streams, so.spotify_total_streams AS total_streams,
                              'https://open.spotify.com/track/' || so.track_id AS url, so.track_id,
                              'spotify' as platform
                       FROM spotify_daily_streams s
                       JOIN songs so ON s.song_id = so.id
                       JOIN artists a ON so.artist_id = a.id"""
    params = []
    
    where_clauses = []
    if search:
        where_clauses.append("(so.title LIKE ? OR a.name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if date_filter:
        where_clauses.append("s.date = ?")
        params.append(date_filter)
    
    if where_clauses:
        spotify_query += " WHERE " + " AND ".join(where_clauses)
    
    if sort_by == 'streams':
        spotify_query += f" ORDER BY s.daily_streams {order.upper()}"
    elif sort_by == 'total':
        spotify_query += f" ORDER BY so.spotify_total_streams {order.upper()}"
    elif sort_by == 'title':
        spotify_query += f" ORDER BY so.title {order.upper()}"
    else:
        spotify_query += f" ORDER BY s.date {order.upper()}"
    
    spotify_query += " LIMIT 200"
    
    spotify_data = [dict(row) for row in conn.execute(spotify_query, params).fetchall()]
    
    # Get YouTube data
    youtube_params = params.copy()
    youtube_query = """SELECT vid.id as video_id, v.date, a.name AS artist_name, vid.title AS video_name,
                              v.daily_views, vid.youtube_total_views AS total_views,
                              'https://www.youtube.com/watch?v=' || vid.watch_id AS url, vid.watch_id,
                              'youtube' as platform
                       FROM youtube_daily_views v
                       JOIN videos vid ON v.video_id = vid.id
                       JOIN artists a ON vid.artist_id = a.id"""
    
    where_clauses = []
    youtube_params = []
    if search:
        where_clauses.append("(vid.title LIKE ? OR a.name LIKE ?)")
        youtube_params.extend([f"%{search}%", f"%{search}%"])
    if date_filter:
        where_clauses.append("v.date = ?")
        youtube_params.append(date_filter)
    
    if where_clauses:
        youtube_query += " WHERE " + " AND ".join(where_clauses)
    
    if sort_by == 'views':
        youtube_query += f" ORDER BY v.daily_views {order.upper()}"
    elif sort_by == 'total':
        youtube_query += f" ORDER BY vid.youtube_total_views {order.upper()}"
    elif sort_by == 'title':
        youtube_query += f" ORDER BY vid.title {order.upper()}"
    else:
        youtube_query += f" ORDER BY v.date {order.upper()}"
    
    youtube_query += " LIMIT 200"
    
    youtube_data = [dict(row) for row in conn.execute(youtube_query, youtube_params).fetchall()]
    
    # Get available dates
    dates = [dict(row) for row in conn.execute(
        "SELECT DISTINCT date FROM spotify_daily_streams UNION SELECT DISTINCT date FROM youtube_daily_views ORDER BY date DESC"
    ).fetchall()]
    
    conn.close()
    
    return render_template('explore.html',
                         spotify_data=spotify_data,
                         youtube_data=youtube_data,
                         dates=dates,
                         current_search=search,
                         current_date=date_filter,
                         current_sort=sort_by,
                         current_order=order)


@app.route('/api/spotify/<int:song_id>/history')
def spotify_history(song_id):
    """API endpoint for Spotify song historical data."""
    conn = get_db_connection()
    
    history = conn.execute(
        """SELECT s.date, s.daily_streams, so.spotify_total_streams as total_streams
           FROM spotify_daily_streams s
           JOIN songs so ON s.song_id = so.id
           WHERE s.song_id = ?
           ORDER BY s.date ASC""",
        (song_id,)
    ).fetchall()
    
    conn.close()
    
    return jsonify([dict(row) for row in history])


@app.route('/api/youtube/<int:video_id>/history')
def youtube_history(video_id):
    """API endpoint for YouTube video historical data."""
    conn = get_db_connection()
    
    history = conn.execute(
        """SELECT v.date, v.daily_views, vid.youtube_total_views as total_views
           FROM youtube_daily_views v
           JOIN videos vid ON v.video_id = vid.id
           WHERE v.video_id = ?
           ORDER BY v.date ASC""",
        (video_id,)
    ).fetchall()
    
    conn.close()
    
    return jsonify([dict(row) for row in history])


@app.route('/spotify')
def spotify():
    """Spotify streams page."""
    pass


@app.route('/youtube')
def youtube():
    """YouTube views page."""
    pass


@app.route('/spotify/<int:song_id>')
def spotify_detail(song_id):
    """Spotify song detail page with historical data."""
    pass


@app.route('/youtube/<int:video_id>')
def youtube_detail(video_id):
    """YouTube video detail page with historical data and embedded video."""
    pass


@app.route('/api/spotify/stats')
def spotify_stats():
    """API endpoint for Spotify statistics."""
    conn = get_db_connection()
    
    # Get top songs by total streams
    top_songs = conn.execute(
        """SELECT song_name, total_streams, url 
           FROM spotify_streams_view 
           GROUP BY song_name 
           ORDER BY total_streams DESC 
           LIMIT 10"""
    ).fetchall()
    
    # Get all-time daily stats
    daily_totals = conn.execute(
        """SELECT date, SUM(daily_streams) as total_daily_streams 
           FROM spotify_streams_view 
           GROUP BY date 
           ORDER BY date"""
    ).fetchall()
    
    conn.close()
    
    return jsonify({
        'top_songs': [dict(row) for row in top_songs],
        'daily_totals': [dict(row) for row in daily_totals]
    })


@app.route('/api/youtube/stats')
def youtube_stats():
    """API endpoint for YouTube statistics."""
    conn = get_db_connection()
    
    # Get top videos by total views
    top_videos = conn.execute(
        """SELECT video_name, total_views, url 
           FROM youtube_daily_views_view 
           GROUP BY video_name 
           ORDER BY total_views DESC 
           LIMIT 10"""
    ).fetchall()
    
    # Get all-time daily stats
    daily_totals = conn.execute(
        """SELECT date, SUM(daily_views) as total_daily_views 
           FROM youtube_daily_views_view 
           GROUP BY date 
           ORDER BY date"""
    ).fetchall()
    
    conn.close()
    
    return jsonify({
        'top_videos': [dict(row) for row in top_videos],
        'daily_totals': [dict(row) for row in daily_totals]
    })


@app.route('/explore')
def explore():
    """Redirect to home page."""
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, port=5000)

