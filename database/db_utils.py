"""
Database utilities for tracking collected documents and preventing duplicates.
Based on the colleague's approach for persistent duplicate detection.
"""
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    """
    Normalize URLs to handle variations (http/https, ports, etc.)
    This ensures the same document with different URL formats is recognized as duplicate.
    """
    try:
        # Unescape HTML entities
        url = url.replace("&amp;", "&")
        
        # Parse URL
        p = urlparse(url)
        
        # Prefer https over http
        scheme = "https" if p.scheme in ("http", "https") else p.scheme
        
        # Lowercase hostname
        netloc = p.netloc.lower()
        
        # Strip default ports
        if netloc.endswith(":80"):
            netloc = netloc[:-3]
        if netloc.endswith(":443"):
            netloc = netloc[:-4]
        
        # Reconstruct URL (remove query and fragment for consistency)
        return urlunparse((scheme, netloc, p.path or "/", "", p.query, ""))
    except Exception:
        return url


def sha1_of_bytes(data: bytes) -> str:
    """Calculate SHA1 hash of bytes."""
    return hashlib.sha1(data).hexdigest()


def init_db(db_path: Path) -> None:
    """
    Initialize the SQLite database with required tables.
    Creates tables if they don't exist.
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        
        # Documents table - tracks all collected documents
        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collector TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            ext TEXT,
            sha1 TEXT,
            published_at TEXT,
            saved_path TEXT,
            first_seen TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            UNIQUE(collector, url)
        );
        """)
        
        # Collector state table - tracks last successful run
        cur.execute("""
        CREATE TABLE IF NOT EXISTS collector_state (
            collector TEXT PRIMARY KEY,
            last_successful_run TEXT
        );
        """)
        
        # Create indexes for faster lookups
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_collector_url 
        ON documents(collector, url);
        """)
        
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_collector_title 
        ON documents(collector, title);
        """)
        
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_collector_sha1 
        ON documents(collector, sha1);
        """)
        
        con.commit()


def db_url_exists(db_path: Path, collector: str, url: str) -> bool:
    """
    Check if a URL already exists in the database for this collector.
    Uses canonicalized URL for comparison.
    """
    can_url = canonicalize_url(url)
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM documents WHERE collector=? AND url=? LIMIT 1",
            (collector, can_url)
        )
        return cur.fetchone() is not None


def db_title_exists(db_path: Path, collector: str, title: str) -> bool:
    """
    Check if a title already exists in the database for this collector.
    Useful when URLs change but the document is the same.
    """
    if not title:
        return False
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM documents WHERE collector=? AND title=? LIMIT 1",
            (collector, title)
        )
        return cur.fetchone() is not None


def db_sha1_saved_path(db_path: Path, collector: str, sha1_hex: str) -> Optional[str]:
    """
    Check if a SHA1 hash already exists in the database.
    Returns the saved_path if found, None otherwise.
    This catches duplicate content even when URLs/titles differ.
    """
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT saved_path FROM documents WHERE collector=? AND sha1=? LIMIT 1",
            (collector, sha1_hex)
        )
        row = cur.fetchone()
        return row[0] if row else None


def db_sha1_with_date(db_path: Path, collector: str, sha1_hex: str) -> Optional[tuple]:
    """
    Check if a SHA1 hash already exists in the database.
    Returns (saved_path, published_at) if found, None otherwise.
    This allows date-based comparison to distinguish different consolidated groups.
    """
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT saved_path, published_at FROM documents WHERE collector=? AND sha1=? LIMIT 1",
            (collector, sha1_hex)
        )
        row = cur.fetchone()
        if row:
            return (row[0], row[1])  # (saved_path, published_at)
        return None


def db_insert_or_update_document(
    db_path: Path,
    collector: str,
    url: str,
    title: Optional[str] = None,
    ext: Optional[str] = None,
    sha1_hex: Optional[str] = None,
    published_at: Optional[datetime] = None,
    saved_path: Optional[Path] = None
) -> None:
    """
    Insert or update a document record in the database.
    Uses canonicalized URL and handles conflicts gracefully.
    """
    can_url = canonicalize_url(url)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    published_at_iso = None
    if published_at:
        if isinstance(published_at, datetime):
            if not published_at.tzinfo:
                published_at = published_at.replace(tzinfo=timezone.utc)
            published_at_iso = published_at.isoformat()
        else:
            published_at_iso = str(published_at)
    
    saved_path_str = str(saved_path) if saved_path else None
    
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""
        INSERT INTO documents (collector, url, title, ext, sha1, published_at, saved_path, first_seen, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(collector, url) DO UPDATE SET
            title=excluded.title,
            ext=excluded.ext,
            sha1=excluded.sha1,
            published_at=excluded.published_at,
            saved_path=excluded.saved_path,
            last_updated=excluded.last_updated
        """, (
            collector,
            can_url,
            title,
            ext,
            sha1_hex,
            published_at_iso,
            saved_path_str,
            now_iso,
            now_iso
        ))
        con.commit()


def db_get_last_run(db_path: Path, collector: str) -> Optional[datetime]:
    """Get the last successful run timestamp for a collector."""
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT last_successful_run FROM collector_state WHERE collector=?",
            (collector,)
        )
        row = cur.fetchone()
        if row and row[0]:
            try:
                return datetime.fromisoformat(row[0])
            except (ValueError, TypeError):
                return None
    return None


def db_set_last_run(db_path: Path, collector: str, when: Optional[datetime] = None) -> None:
    """Set the last successful run timestamp for a collector."""
    when = when or datetime.now(timezone.utc)
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""
        INSERT INTO collector_state (collector, last_successful_run)
        VALUES (?, ?)
        ON CONFLICT(collector) DO UPDATE SET last_successful_run=excluded.last_successful_run
        """, (collector, when.isoformat()))
        con.commit()


def get_db_path(config_manager) -> Path:
    """
    Get the database path from config or use default location.
    Database will be stored next to the config file or in the project root.
    """
    # Try to get from config first
    db_path_str = config_manager.get('db_path')
    if db_path_str:
        return Path(db_path_str).resolve()
    
    # Default: store in project root as state.db
    import sys
    if getattr(sys, 'frozen', False):
        # Running as executable - use executable's directory
        base_path = Path(sys.executable).parent
    else:
        # Running as script - use current working directory
        base_path = Path.cwd()
    
    return base_path / "state.db"

