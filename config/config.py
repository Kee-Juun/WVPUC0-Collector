"""
Configuration management for WVPUC0 Document Collector.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_file: str = 'config.json'):
        self.config_file = config_file
        self.config_path = self._resolve_local_config_path()
        self.packaged_config_path = self._resolve_packaged_config_path()
        self.config = self.load_config()

    def _resolve_local_config_path(self) -> Path:
        """Resolve the writable config path deterministically."""
        requested = Path(self.config_file)
        if requested.is_absolute():
            return requested

        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).resolve().parent
        else:
            base_path = Path(__file__).resolve().parent.parent
        return (base_path / requested).resolve()

    def _resolve_packaged_config_path(self) -> Path | None:
        """Resolve the read-only packaged config path when bundled."""
        meipass = getattr(sys, '_MEIPASS', None)
        if not meipass:
            return None
        return (Path(meipass) / self.config_file).resolve()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """Return the canonical default configuration."""
        return {
            'headless': True,
            'download_path': 'Downloads/WVPUC0 Collections',
            'sf_view_url': 'file://fntd5bdata09/pclprod/sf-view/PROD/team10/wvpuc0/',
            'main_url': 'https://www.psc.state.wv.us/scripts/orders/OrdersByMonth.cfm',
            'include_keywords': [
                'Recommended Decision',
                'Mediation Final Order',
                'Commission Final Order',
                'Interim Recommended Decision',
                'Recommended Decision',
                'Administrative Law Judge Final Order',
                'Commission Order',
                'Commission Corrective Order',
                'Commission Procedure Order',
                'Commission Procedural Order',
            ],
            'exclude_keywords': [
                'Procedural Order',
                'Scheduling Order',
                'Notice of Filing',
                'Commission Order Extending Answer Due Date',
                'Commission Order Extending Administrative Law Judge Decision Due Date',
                'Commission Order extending the ALJ Decision Due Date',
                'Commission Order Denying Request to Extend Administrative Law Judge Decision Due Date',
            ],
            'listing_exclude_keywords': [
                'Procedural Order',
                'Scheduling Order',
                'Commission Order Extending Answer Due Date',
                'Commission Order Extending Administrative Law Judge Decision Due Date',
                'Commission Order extending the ALJ Decision Due Date',
                'Commission Order Denying Request to Extend Administrative Law Judge Decision Due Date',
            ],
            'max_duplicates': 5,
            'file_naming_format': 'LDC_SMD_{case_number}_{date}_E2E',
            'tracker_enabled': True,
            'tracker_fail_open': False,
            'tracker_retry_attempts': 3,
            'tracker_retry_backoff_seconds': 5,
            'tracker_retry_max_backoff_seconds': 30,
            'tracker_url': 'https://tcfabprod.lexisnexis.com/ws/TrackerReport/',
            'tracker_court_code': 'STWVPUC0',
            'tracker_use_query_wizard': True,
            'tracker_case_regex': '\\d{2}-\\d{4}-[A-Z0-9-]+',
            'tracker_date_regex': '\\d{8}',
            'tracker_rows_xpath': '//table[2]//tr',
            'tracker_case_column_index': 3,
            'tracker_date_column_index': 5,
            'tracker_date_window_days_before': 15,
            'tracker_date_window_days_after': 15,
            'tracker_match_with_date': True,
            'content_filter_enabled': True,
            'prefetch_pdf_links': False,
            'use_new_tab_downloads': True,
            'bulk_tab_downloads': True,
            'download_max_wait_seconds': 30,
            'download_stable_seconds': 2,
            'content_exclude_keywords': [
                'Procedural Order',
                'Scheduling Order',
                'Notice of Filing',
                'Commission Order Extending Answer Due Date',
                'Commission Order Extending Administrative Law Judge Decision Due Date',
                'Commission Order extending the ALJ Decision Due Date',
                'Commission Order Denying Request to Extend Administrative Law Judge Decision Due Date',
            ],
            'content_max_pages': 5,
            'content_min_text_length': 50,
            'ocr_enabled': True,
            'ocr_language': 'eng',
            'ocr_dpi': 250,
            'ocr_min_native_chars': 50,
            'ocr_page_timeout_seconds': 30,
        }

    def _merge_with_defaults(self, loaded_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge a loaded config over the current defaults."""
        merged = self._default_config()
        merged.update(loaded_config or {})
        return merged

    def _read_json(self, path: Path) -> Dict[str, Any]:
        with path.open('r', encoding='utf-8') as file_handle:
            return json.load(file_handle)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from a deterministic local path or packaged fallback."""
        if self.config_path.exists():
            loaded = self._read_json(self.config_path)
            merged = self._merge_with_defaults(loaded)
            if merged != loaded:
                self.save_config(merged)
            return merged

        if self.packaged_config_path and self.packaged_config_path.exists():
            loaded = self._read_json(self.packaged_config_path)
            merged = self._merge_with_defaults(loaded)
            self.save_config(merged)
            return merged

        default_config = self._default_config()
        self.save_config(default_config)
        return default_config

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to the resolved local config path."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open('w', encoding='utf-8') as file_handle:
            json.dump(config, file_handle, indent=4)

    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value) -> None:
        """Set configuration value and persist it."""
        self.config[key] = value
        self.save_config(self.config)
