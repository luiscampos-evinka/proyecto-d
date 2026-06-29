#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from supabase_store import create_store
from sync_clickup import DEFAULT_CONFIG_PATH, load_config, process_message


def normalize_sender(value: str) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return f'+{digits}' if digits else ''


def append_audit(log_path: Path, payload: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({
        'ts': datetime.now(timezone.utc).isoformat(),
        **payload,
    }, ensure_ascii=False)
    with log_path.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_payload_file(path: str | None):
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build_base_message_row(config: dict, sender: str, message_id: str, body: str):
    allowed_emojis = config['routing'].get('allowed_emojis', ['📢', '📣'])
    return {
        'project_key': config.get('project_key', 'proyecto_d'),
        'source_channel': 'whatsapp',
        'sender': sender,
        'message_id': message_id,
        'raw_body': body,
        'normalized_body': body.strip(),
        'has_trigger_emoji': any(emoji in body for emoji in allowed_emojis),
        'visible_output': config['routing'].get('visible_output', 'NO_REPLY'),
        'received_at': now_iso(),
        'result_status': 'received',
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument('--payload-file')
    ap.add_argument('--sender')
    ap.add_argument('--message-id')
    ap.add_argument('--body')
    args = ap.parse_args()

    config = load_config(Path(args.config))
    payload = load_payload_file(args.payload_file)
    sender = normalize_sender(payload.get('sender') or args.sender)
    message_id = payload.get('message_id') or args.message_id
    body = payload.get('body') or args.body
    timestamp = payload.get('timestamp')
    attachments = payload.get('attachments') or []
    if not sender or not message_id or body is None:
        raise SystemExit('sender, message-id y body son requeridos')
    allowed = {normalize_sender(v) for v in config['routing'].get('allowed_senders', [])}
    audit_log_path = Path(config['paths']['audit_log_path'])
    store = create_store(config)

    base_row = build_base_message_row(config, sender, message_id, body)
    if store:
        store.safe_upsert_inbound_message(base_row)

    if sender not in allowed:
        result = {'status': 'ignored', 'reason': 'sender_not_allowed'}
        append_audit(audit_log_path, {
            'project': config.get('project_key'),
            'sender': sender,
            'message_id': message_id,
            'result': 'ignored_sender',
        })
        if store:
            store.safe_finalize_inbound_message(message_id, {
                'result_status': 'ignored_sender',
                'error_text': 'sender_not_allowed',
                'result_payload': result,
                'processed_at': now_iso(),
            })
        print(json.dumps(result, ensure_ascii=False))
        return

    try:
        result = process_message(
            config,
            message_id,
            body,
            sender=sender,
            timestamp=timestamp,
            attachments=attachments,
        )
    except Exception as err:
        append_audit(audit_log_path, {
            'project': config.get('project_key'),
            'sender': sender,
            'message_id': message_id,
            'result': 'error',
            'error': str(err),
        })
        if store:
            payload = {
                'message_id': message_id,
                'sender': sender,
                'stage': 'process_message',
                'error_text': str(err),
                'payload': {
                    'body': body,
                    'attachments': [{
                        'filename': item.get('filename'),
                        'mime_type': item.get('mime_type'),
                        'type': item.get('type'),
                    } for item in attachments],
                },
            }
            store.safe_log_processing_error(payload)
            store.safe_finalize_inbound_message(message_id, {
                'result_status': 'error',
                'error_text': str(err),
                'processed_at': now_iso(),
            })
        raise

    append_audit(audit_log_path, {
        'project': config.get('project_key'),
        'sender': sender,
        'message_id': message_id,
        'result': result,
    })

    if store:
        store.safe_finalize_inbound_message(message_id, {
            'normalized_body': body.strip(),
            'project_guess': result.get('project_guess'),
            'result_status': result.get('status'),
            'clickup_action': result.get('clickup_action'),
            'clickup_task_id': result.get('task_id'),
            'clickup_task_name': result.get('name'),
            'clickup_target_status': result.get('clickup_target_status') or result.get('new_status'),
            'result_payload': result,
            'error_text': result.get('reason'),
            'processed_at': now_iso(),
        })
        if result.get('status') in {'created', 'updated'}:
            store.safe_log_clickup_event({
                'message_id': message_id,
                'event_type': result.get('clickup_action') or result.get('status'),
                'clickup_task_id': result.get('task_id'),
                'clickup_task_name': result.get('name'),
                'clickup_status': result.get('new_status') or result.get('clickup_target_status'),
                'payload': result,
            })

    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
