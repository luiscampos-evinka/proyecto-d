#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import re
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.json'
STATE_PATH = PROJECT_ROOT / 'state' / 'watcher_state.json'
ROUTER = str(PROJECT_ROOT / 'src' / 'router.py')
PAYLOAD_DIR = PROJECT_ROOT / 'state' / 'payloads'
CONVERSATION_INFO_RE = re.compile(r'Conversation info \(untrusted metadata\):\n```json\n(.*?)\n```', re.S)


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def normalize_sender(value: str) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return f'+{digits}' if digits else ''


def load_config():
    return load_json(CONFIG_PATH, {})


def sanitize_token(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value or '').strip())
    return cleaned.strip('._-') or 'attachment'


def extract_text_blocks(msg):
    return '\n'.join(c.get('text', '') for c in msg.get('content', []) if c.get('type') == 'text')


def parse_conversation_info(text):
    m = CONVERSATION_INFO_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def extract_original_body(text):
    lines = text.splitlines()
    cleaned = []
    in_code = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        if (
            line.startswith('Conversation info')
            or line.startswith('Sender (untrusted metadata):')
            or line.startswith('[Bootstrap')
            or line.startswith('Replied message')
            or line.startswith('[Queued messages while agent was busy]')
            or line.startswith('---')
            or line.startswith('Queued #')
        ):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def guess_filename(message_id: str, index: int, block: dict) -> str:
    raw_name = block.get('filename') or block.get('fileName') or block.get('name') or block.get('title')
    if raw_name:
        return sanitize_token(raw_name)
    ext = mimetypes.guess_extension(block.get('mimeType') or '') or ''
    return f"{sanitize_token(message_id)}-attachment-{index}{ext}"


def extract_attachments(msg: dict, message_id: str):
    attachments = []
    for index, block in enumerate(msg.get('content', []) or [], start=1):
        block_type = block.get('type')
        if block_type == 'text':
            continue
        data = block.get('data')
        url = block.get('url') or block.get('href')
        path = block.get('path')
        if not data and not url and not path:
            continue
        attachment = {
            'index': index,
            'type': block_type,
            'mime_type': block.get('mimeType') or 'application/octet-stream',
            'filename': guess_filename(message_id, index, block),
        }
        if data:
            attachment['data'] = data
        if url:
            attachment['url'] = url
        if path:
            attachment['path'] = path
        attachments.append(attachment)
    return attachments


def payload_path(message_id: str) -> Path:
    return PAYLOAD_DIR / f"{sanitize_token(message_id)}.json"


def write_payload(payload: dict) -> Path:
    path = payload_path(payload.get('message_id', 'message'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


def session_registry_paths():
    env_root = os.getenv('OPENCLAW_AGENTS_ROOT', '/root/.openclaw/agents')
    roots = [Path(env_root)]
    out = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.glob('*/sessions/sessions.json'):
            key = str(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def session_files_from_registries():
    files = []
    seen = set()
    for registry in session_registry_paths():
        data = load_json(registry, {})
        for session in data.values():
            session_file = session.get('sessionFile')
            if not session_file:
                continue
            if session_file in seen:
                continue
            seen.add(session_file)
            files.append(Path(session_file))
    return files


def process_session_file(session_file: Path, state: dict, allowed_senders: set[str], allowed_emojis: tuple[str, ...]):
    if not session_file.exists():
        return 0
    processed = 0
    seen = set(state.get('processed_message_ids', []))
    with session_file.open() as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get('type') != 'message':
                continue
            msg = obj.get('message', {})
            if msg.get('role') != 'user':
                continue
            text = extract_text_blocks(msg)
            info = parse_conversation_info(text)
            if not info:
                continue
            sender = normalize_sender(info.get('sender_id'))
            message_id = info.get('message_id')
            if not sender or sender not in allowed_senders:
                continue
            if not message_id or message_id in seen:
                continue
            body = extract_original_body(text)
            if not body or not any(e in body for e in allowed_emojis):
                continue
            attachments = extract_attachments(msg, message_id)
            payload = {
                'sender': sender,
                'message_id': message_id,
                'body': body,
                'timestamp': info.get('timestamp'),
                'attachments': attachments,
            }
            payload_file = write_payload(payload)
            try:
                subprocess.run([
                    'python3',
                    ROUTER,
                    '--payload-file', str(payload_file),
                ], check=False)
            finally:
                try:
                    payload_file.unlink()
                except FileNotFoundError:
                    pass
            seen.add(message_id)
            processed += 1
    state['processed_message_ids'] = list(seen)[-2000:]
    return processed


def run_once():
    config = load_config()
    routing = config.get('routing') or {}
    allowed_senders = {normalize_sender(v) for v in routing.get('allowed_senders', [])}
    allowed_emojis = tuple(routing.get('allowed_emojis', ['📢', '📣']))
    state = load_json(STATE_PATH, {'processed_message_ids': []})
    processed = 0
    for session_file in session_files_from_registries():
        processed += process_session_file(session_file, state, allowed_senders, allowed_emojis)
    save_json(STATE_PATH, state)
    print(json.dumps({'ok': True, 'processed': processed}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--sleep-seconds', type=float, default=3.0)
    args = ap.parse_args()

    if args.once:
        run_once()
        return

    while True:
        run_once()
        time.sleep(args.sleep_seconds)


if __name__ == '__main__':
    main()
