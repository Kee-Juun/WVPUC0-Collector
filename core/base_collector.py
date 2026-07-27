"""
Base collector class based on NonCCSAutoCollectors architecture
Handles downloads via requests (more reliable than browser downloads)
"""
from __future__ import annotations
import logging
import hashlib
import mimetypes
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse, urlunparse
import html as ihtml

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

CHUNK = 1024 * 128  # 128KB


@dataclass
class DocumentCandidate:
    url: str
    title: str | None
    published_at: Optional[datetime]
    referrer: str | None
    ext: str | None
    case_number: str | None = None  # Add case number for WVPUC0


class BaseCollector(ABC):
    """Base class for collectors - handles downloads via requests"""
    
    name: str = "BaseCollector"
    base_url: str = ""
    
    def __init__(self, config: dict, log_signal=None):
        self.config = config
        self.log_signal = log_signal or (lambda msg: logger.info(msg))
        self.db_path = Path(config.get('db_path', 'state.db'))
        self._init_db()
        
        # Create requests session for downloads
        self.requests = requests.Session()
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        
        self.polite_delay_sec = config.get('polite_delay_sec', 2)
        self.run_output_dir: Optional[Path] = None
        
    def _init_db(self):
        """Initialize database tables"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                collector TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                ext TEXT,
                sha1 TEXT,
                published_at TEXT,
                saved_path TEXT,
                first_seen TEXT,
                last_updated TEXT
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS collector_state (
                collector TEXT PRIMARY KEY,
                last_successful_run TEXT
            );
            """)
            con.commit()
    
    def _canonicalize_url(self, url: str) -> str:
        """Canonicalize URL"""
        try:
            url = url.replace("&amp;", "&")
            p = urlparse(url)
            scheme = "https" if p.scheme in ("http", "https") else p.scheme
            netloc = p.netloc.lower()
            if netloc.endswith(":80"):
                netloc = netloc[:-3]
            if netloc.endswith(":443"):
                netloc = netloc[:-4]
            return urlunparse((scheme, netloc, p.path or "/", "", p.query, ""))
        except Exception:
            return url
    
    def _sha1_of_bytes(self, b: bytes) -> str:
        return hashlib.sha1(b).hexdigest()
    
    def _sanitize_filename(self, name: str) -> str:
        name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
        return name.strip()[:180]
    
    def _guess_extension(self, url: str, content_type: Optional[str]) -> Optional[str]:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext:
            return ext
        if content_type:
            return mimetypes.guess_extension(content_type.split(";")[0].strip())
        return None
    
    def _db_url_exists(self, url: str) -> bool:
        """Check if URL already exists in database"""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT 1 FROM documents WHERE collector=? AND url=? LIMIT 1", (self.name, url))
            return cur.fetchone() is not None
    
    def _db_sha1_exists(self, sha1_hex: str) -> Optional[str]:
        """Check if SHA1 already exists, return saved path if found"""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT saved_path FROM documents WHERE collector=? AND sha1=? LIMIT 1", (self.name, sha1_hex))
            row = cur.fetchone()
            return row[0] if row else None
    
    def _db_insert_document(self, candidate: DocumentCandidate, sha1_hex: str, saved_path: Path):
        """Insert or update document in database"""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("""
            INSERT INTO documents (collector, url, title, ext, sha1, published_at, saved_path, first_seen, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                ext=excluded.ext,
                sha1=excluded.sha1,
                published_at=excluded.published_at,
                saved_path=excluded.saved_path,
                last_updated=excluded.last_updated
            """, (
                self.name, candidate.url, candidate.title, candidate.ext, sha1_hex,
                candidate.published_at.isoformat() if candidate.published_at else None,
                str(saved_path), now_iso, now_iso
            ))
            con.commit()
    
    def _download_bytes(self, url: str, timeout: int = 30, referrer: Optional[str] = None) -> Tuple[bytes, Optional[str]]:
        """Download file using requests library"""
        tries = 3
        last_exc = None
        headers = {}
        if referrer:
            headers['Referer'] = referrer
        
        for attempt in range(tries):
            try:
                with self.requests.get(url, timeout=timeout, stream=True, allow_redirects=True, headers=headers) as resp:
                    resp.raise_for_status()
                    ct = resp.headers.get("Content-Type")
                    data = bytearray()
                    for chunk in resp.iter_content(chunk_size=CHUNK):
                        if chunk:
                            data.extend(chunk)
                    return bytes(data), ct
            except Exception as e:
                last_exc = e
                if attempt < tries - 1:
                    time.sleep(1)
        raise last_exc
    
    @abstractmethod
    def search(self, driver: webdriver.Chrome, start_date: Optional[datetime], end_date: Optional[datetime]) -> Iterable[DocumentCandidate]:
        """Search and yield DocumentCandidate objects. Must be implemented by subclasses."""
        ...
    
    def download_and_save(self, candidate: DocumentCandidate) -> Optional[Path]:
        """Download and save a document candidate"""
        # Canonicalize URL
        can_url = self._canonicalize_url(candidate.url)
        candidate.url = can_url
        
        # Skip if already exists
        if self._db_url_exists(can_url):
            self.log_signal(f'Skipping already-saved URL: {can_url}')
            return None
        
        # Download
        try:
            data, content_type = self._download_bytes(can_url, referrer=candidate.referrer)
        except Exception as e:
            self.log_signal(f'Download failed for {can_url}: {str(e)}')
            return None
        
        # Check SHA1
        sha1_hex = self._sha1_of_bytes(data)
        existing_path = self._db_sha1_exists(sha1_hex)
        if existing_path:
            self.log_signal(f'Skipping identical content (sha1 match). URL={can_url} existing={existing_path}')
            return None
        
        # Determine extension
        ext = candidate.ext or self._guess_extension(can_url, content_type) or ".pdf"
        if not ext.startswith("."):
            ext = "." + ext
        
        # Create filename
        title_part = self._sanitize_filename(candidate.title or "document").strip()
        if not title_part:
            title_part = "document"
        title_part = title_part.rstrip(" ._")
        
        # Ensure filename fits
        MAX_TOTAL = 240
        out_dir_str = str(self.run_output_dir.resolve())
        budget = MAX_TOTAL - len(out_dir_str) - 1 - len(ext)
        if budget < 40:
            budget = 40
        if len(title_part) > budget:
            title_part = title_part[:budget].rstrip(" ._") or "document"
        
        filename = f"{title_part}{ext}"
        final_path = self.run_output_dir / filename
        
        # Handle duplicates
        if final_path.exists():
            suffix = f".{sha1_hex[:10]}"
            budget2 = MAX_TOTAL - len(out_dir_str) - 1 - len(ext) - len(suffix)
            if budget2 < 30:
                budget2 = 30
            base_name = self._sanitize_filename(candidate.title or "document")[:budget2].rstrip(" ._") or "document"
            final_path = self.run_output_dir / f"{base_name}{suffix}{ext}"
        
        # Save file
        with open(final_path, "wb") as f:
            f.write(data)
        
        # Update database
        self._db_insert_document(candidate, sha1_hex, final_path)
        self.log_signal(f'Saved: {final_path}')
        return final_path
    
    def run(self, driver: webdriver.Chrome, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, output_dir: Optional[Path] = None) -> int:
        """Run the collector"""
        self.run_output_dir = output_dir or Path.home() / self.config.get('download_path', 'Downloads/WVPUC0 Collections')
        self.run_output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_count = 0
        try:
            for cand in self.search(driver, start_date, end_date):
                out_path = self.download_and_save(cand)
                if out_path is not None:
                    saved_count += 1
                
                time.sleep(self.polite_delay_sec)
        except Exception as e:
            self.log_signal(f'Run failed: {str(e)}')
            logger.exception(f'Run failed: {str(e)}')
        
        return saved_count

