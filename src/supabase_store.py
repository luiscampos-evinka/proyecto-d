#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import resolve_path


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path: Path):
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


class SupabaseStore:
    def __init__(self, *, url: str, key: str, schema: str, tables: dict, error_log_path: Path | None = None):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.key = key
        self.schema = schema or 'public'
        self.tables = tables or {}
        self.error_log_path = error_log_path

    def _headers(self, prefer: str | None = None):
        headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json',
            'Accept-Profile': self.schema,
            'Content-Profile': self.schema,
        }
        if prefer:
            headers['Prefer'] = prefer
        return headers

    def _append_local_error(self, stage: str, error_text: str, payload: dict | None = None):
        if not self.error_log_path:
            return
        self.error_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            'ts': _now_iso(),
            'stage': stage,
            'error': error_text,
            'payload': payload or {},
        }, ensure_ascii=False)
        with self.error_log_path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')

    def _request(self, path: str, *, method: str = 'GET', body=None, prefer: str | None = None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            f"{self.base_url}/{path}",
            data=data,
            method=method,
            headers=self._headers(prefer),
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            text = res.read().decode('utf-8')
            return json.loads(text) if text else None

    def safe_upsert_inbound_message(self, row: dict):
        table = self.tables.get('inbound_messages')
        if not table:
            return
        try:
            self._request(
                f"{table}?on_conflict=message_id",
                method='POST',
                body=[row],
                prefer='resolution=merge-duplicates,return=representation',
            )
        except Exception as err:
            self._append_local_error('safe_upsert_inbound_message', str(err), row)

    def safe_finalize_inbound_message(self, message_id: str, patch: dict):
        table = self.tables.get('inbound_messages')
        if not table:
            return
        try:
            quoted = urllib.parse.quote(str(message_id), safe='')
            self._request(
                f"{table}?message_id=eq.{quoted}",
                method='PATCH',
                body=patch,
                prefer='return=representation',
            )
        except Exception as err:
            payload = {'message_id': message_id, 'patch': patch}
            self._append_local_error('safe_finalize_inbound_message', str(err), payload)

    def safe_log_clickup_event(self, row: dict):
        table = self.tables.get('clickup_sync_events')
        if not table:
            return
        try:
            self._request(table, method='POST', body=[row], prefer='return=minimal')
        except Exception as err:
            self._append_local_error('safe_log_clickup_event', str(err), row)

    def safe_log_processing_error(self, row: dict):
        table = self.tables.get('processing_errors')
        if not table:
            self._append_local_error('safe_log_processing_error_no_table', 'processing_errors table not configured', row)
            return
        try:
            self._request(table, method='POST', body=[row], prefer='return=minimal')
        except Exception as err:
            self._append_local_error('safe_log_processing_error', str(err), row)


def create_store(config: dict):
    sb = config.get('supabase') or {}
    env_path = resolve_path(sb.get('env_path', ''), config_path=config.get('_config_path')) if sb.get('env_path') else None
    env = load_env_file(env_path) if env_path else {}
    url = env.get('SUPABASE_URL') or os.getenv('SUPABASE_URL')
    key = env.get('SUPABASE_SECRET_KEY') or env.get('SUPABASE_SERVICE_ROLE_KEY') or env.get('SUPABASE_KEY') or os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
    if not url or not key:
        return None
    error_log_path = None
    paths = config.get('paths') or {}
    if paths.get('supabase_error_log_path'):
        error_log_path = resolve_path(paths['supabase_error_log_path'], config_path=config.get('_config_path'))
    return SupabaseStore(
        url=url,
        key=key,
        schema=sb.get('schema', 'public'),
        tables=sb.get('tables') or {},
        error_log_path=error_log_path,
    )
