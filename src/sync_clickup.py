#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.json'
ALIASES = {
    'CHO': 'CHORRILLOS',
    'MA': 'MAE',
    'TT': 'TOTTUS',
    'JP': 'JP',
    'UTP': 'UTP',
    'PM': 'PM',
}
STOP = {'EL','LA','LOS','LAS','DE','DEL','Y','EN','SU','QUE','SE','A','AL','LO','YA','UN','UNA','POR','PARA','CON'}


def load_config(config_path: Path):
    return json.loads(config_path.read_text())


def token_path(config):
    return Path(config['clickup']['token_path'])


def state_path(config):
    return Path(config['paths']['state_path'])


def api_base(config):
    return config['clickup'].get('api', 'https://api.clickup.com/api/v2').rstrip('/')


def load_token(config):
    return token_path(config).read_text().strip()


def api(config, method, path, data=None):
    token = load_token(config)
    body = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(api_base(config) + path, data=body, method=method, headers={
        'Authorization': token,
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def api_bytes(config, method, path, body: bytes, headers: dict):
    token = load_token(config)
    req_headers = {'Authorization': token, **headers}
    req = urllib.request.Request(api_base(config) + path, data=body, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def normalize_text(s: str) -> str:
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = s.replace('&', ' AND ')
    s = re.sub(r'[^A-Z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def norm_tokens(s: str):
    toks = []
    for tok in normalize_text(s).split():
        tok = ALIASES.get(tok, tok)
        if tok in STOP:
            continue
        toks.append(tok)
    return toks


def extract_body(raw: str, allowed_emojis):
    for line in raw.splitlines():
        if any(emoji in line for emoji in allowed_emojis):
            return line.strip()
    return raw.strip()


def clean_body(raw: str):
    body = raw.replace('*', ' ').strip()
    body = re.sub(r'^COMUNICADO\s*[📢📣]?\s*', '', body, flags=re.I)
    body = body.replace('📢', ' ').replace('📣', ' ')
    body = re.sub(r'\s+', ' ', body).strip(' ,.-')
    return body


def sanitize_filename(value: str) -> str:
    value = (value or '').strip()
    value = value.replace(' ', '_')
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', value)
    return value.strip('._-') or 'attachment'


def guess_extension(mime_type: str) -> str:
    ext = mimetypes.guess_extension((mime_type or '').split(';', 1)[0].strip())
    return ext or ''


def attachment_filename(message_id: str, attachment: dict, position: int) -> str:
    existing = attachment.get('filename') or attachment.get('name')
    if existing:
        name = sanitize_filename(existing)
        if '.' in name:
            return name
        return name + guess_extension(attachment.get('mime_type') or attachment.get('mimeType') or '')
    return f"{sanitize_filename(message_id)}-attachment-{position}{guess_extension(attachment.get('mime_type') or attachment.get('mimeType') or '')}"


def decode_attachment_bytes(attachment: dict) -> bytes:
    if attachment.get('data'):
        return base64.b64decode(attachment['data'])
    if attachment.get('path'):
        return Path(attachment['path']).read_bytes()
    if attachment.get('url'):
        with urllib.request.urlopen(attachment['url'], timeout=60) as response:
            return response.read()
    raise ValueError('attachment_without_content')


def upload_task_attachment(config, task_id: str, attachment: dict, *, message_id: str, position: int):
    filename = attachment_filename(message_id, attachment, position)
    mime_type = attachment.get('mime_type') or attachment.get('mimeType') or 'application/octet-stream'
    file_bytes = decode_attachment_bytes(attachment)
    boundary = f"----ProyectoDBoundary{datetime.now(timezone.utc).timestamp():.6f}".replace('.', '')
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="attachment"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode('utf-8')
    tail = f"\r\n--{boundary}--\r\n".encode('utf-8')
    body = head + file_bytes + tail
    response = api_bytes(config, 'POST', f'/task/{task_id}/attachment', body, {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Accept': 'application/json',
        'Content-Length': str(len(body)),
    })
    return {
        'filename': filename,
        'mime_type': mime_type,
        'size_bytes': len(file_bytes),
        'response': response,
    }


def create_task_comment(config, task_id: str, comment_text: str):
    if not comment_text:
        return None
    return api(config, 'POST', f'/task/{task_id}/comment', {'comment_text': comment_text})


def summarize_attachments(message_id: str, attachments: list[dict]):
    lines = []
    for position, attachment in enumerate(attachments or [], start=1):
        lines.append(
            f"- {attachment_filename(message_id, attachment, position)} ({attachment.get('mime_type') or attachment.get('mimeType') or attachment.get('type') or 'archivo'})"
        )
    return lines


def build_context_block(*, sender: str | None, timestamp: str | None, message_id: str, body: str, attachments: list[dict], target_status: str | None):
    lines = [
        'PROYECTO D · EVENTO WHATSAPP',
        f'- message_id: {message_id}',
    ]
    if sender:
        lines.append(f'- remitente: {sender}')
    if timestamp:
        lines.append(f'- timestamp: {timestamp}')
    if target_status:
        lines.append(f'- status detectado: {target_status}')
    lines.append('- mensaje original:')
    lines.append(body)
    if attachments:
        lines.append('- adjuntos:')
        lines.extend(summarize_attachments(message_id, attachments))
    return '\n'.join(lines)


PROJECT_SPLIT_MARKERS = [
    ' SE REACTIVA ',
    ' RECIBIMOS ',
    ' RECIBIMOS LAS RESPUESTAS ',
    ' RESPUESTAS A CONSULTAS ',
    ' NOS LLEGO ',
    ' YA LLEGO ',
    ' LLEGO LAS RESPUESTAS ',
    ' LLEGARON LAS RESPUESTAS ',
    ' ACABAMOS DE RECIBIR ',
    ' RECIEN NOS COMPARTIERON ',
    ' RECIEN ENTRO INFO NUEVA ',
    ' YA PUEDEN REVISAR ',
    ' REVISAR SU CARPETA ',
    ' REVISAR LA CARPETA ',
    ' SE ENCUENTRA ',
    ' EL PROYECTO ',
    ' EL PROCESO ',
    ' QUEDA ',
    ' QUEDO ',
    ' PAUSADO ',
    ' ESTA PAUSADO ',
    ' POR AHORA ',
    ' TERMINO DE DESCARGARSE ',
    ' YA SE TERMINO DE DESCARGAR ',
    ' YA QUEDO LISTA LA DESCARGA ',
    ' SE VUELVE A MOVER ',
    ' DEJARON EN SU CARPETA ',
    ' ENTRO INFO NUEVA ',
    ' PASA A METRADO Y COTIZACIONES ',
    ' ENTRA A METRADO Y COTIZACIONES ',
    ' PASA A METRADO ',
    ' ENTRA A METRADO ',
    ' PASA A COTIZACION ',
    ' PASA A COTIZACIONES ',
    ' ENTRA A COTIZACION ',
    ' ENTRA A COTIZACIONES ',
    ' PASA A PRESUPUESTO ',
    ' ENTRA A PRESUPUESTO ',
    ' PROYECTO CERRADO ',
    ' CIERRE DEFINITIVO ',
    ' DAR POR CERRADO ',
    ' LA COTIZACION ',
    ' LA PROPUESTA ',
    ' FUE ENTREGADA ',
    ' REVISADO ',
    ' AVANZA ',
]


ACTION_STARTERS = {
    'SE', 'RECIBIMOS', 'RESPUESTAS', 'NOS', 'YA', 'LLEGO', 'LLEGARON', 'ACABAMOS',
    'RECIEN', 'REVISAR', 'QUEDA', 'QUEDO', 'ESTA', 'POR', 'TERMINO', 'DEJARON', 'ENTRO',
    'PAUSADO', 'REVISADO', 'AVANZA'
}


def split_project_and_rest(body: str):
    normalized = f" {normalize_text(body)} "
    best_idx = None
    best_marker = None
    for marker in PROJECT_SPLIT_MARKERS:
        idx = normalized.find(marker)
        if idx != -1 and (best_idx is None or idx < best_idx):
            best_idx = idx
            best_marker = marker
    if best_idx is not None:
        project = normalized[1:best_idx].strip(' -')
        rest = normalized[best_idx + 1:].strip()
        return project, rest

    tokens = normalize_text(body).split()
    if not tokens:
        return '', ''
    project_tokens = []
    for i, token in enumerate(tokens):
        remaining = tokens[i:]
        pair = ' '.join(remaining[:2])
        triplet = ' '.join(remaining[:3])
        if project_tokens and (
            triplet in {'EL PROYECTO QUEDA', 'EL PROCESO ESTA', 'POR AHORA MEJOR'}
            or pair in {'SE REACTIVA', 'YA PUEDEN', 'POR AHORA', 'ESTA PAUSADO', 'EL PROYECTO', 'EL PROCESO'}
            or token in ACTION_STARTERS
        ):
            break
        project_tokens.append(token)
    project = ' '.join(project_tokens).strip(' -')
    rest = ' '.join(tokens[len(project_tokens):]).strip()
    return project, rest


def parse_message(raw: str, allowed_emojis):
    body = extract_body(raw, allowed_emojis)
    if not any(emoji in body for emoji in allowed_emojis):
        return None
    body = clean_body(body)
    project, rest = split_project_and_rest(body)
    return {
        'body': body,
        'project_raw': project or normalize_text(body),
        'rest': rest or normalize_text(body),
    }


def classify_status(text: str):
    n = normalize_text(text)
    if any(x in n for x in [
        'CLOSED', 'CERRADO', 'SE CERRO', 'SE CERRO EL PROYECTO', 'DAR POR CERRADO',
        'PROYECTO CERRADO', 'CERRAR EL PROYECTO', 'CIERRE DEFINITIVO'
    ]):
        return 'Closed'
    if any(x in n for x in [
        'ENTREGADO', 'YA FUE ENTREGADO', 'SE ENTREGO', 'SE ENTREGO AL CLIENTE',
        'FUE ENTREGADA AL CLIENTE', 'FUE ENTREGADO AL CLIENTE', 'PROPUESTA ENTREGADA', 'COTIZACION ENTREGADA', 'DOCUMENTACION ENTREGADA',
        'SE ENVIO AL CLIENTE', 'ENVIADO AL CLIENTE', 'YA SE ENTREGO'
    ]):
        return 'entregado'
    if any(x in n for x in [
        'METRADO Y COTIZACIONES', 'PASA A METRADO Y COTIZACIONES', 'ENTRA A METRADO Y COTIZACIONES',
        'PASA A METRADO', 'ENTRA A METRADO', 'MANDAR A METRADO', 'INICIAR METRADO',
        'PARA COTIZAR', 'PASA A COTIZACION', 'PASA A COTIZACIONES', 'ENTRA A COTIZACION',
        'ENTRA A COTIZACIONES', 'INICIAR COTIZACION', 'INICIAR COTIZACIONES',
        'EMPEZAR COTIZACION', 'EMPEZAR COTIZACIONES', 'ELABORAR COTIZACION', 'ELABORAR COTIZACIONES',
        'PASA A PRESUPUESTO', 'ENTRA A PRESUPUESTO'
    ]):
        return 'metrado y cotizaciones'
    if any(x in n for x in [
        'PAUSADO', 'EN ESPERA', 'FALTAN RESPONDER CONSULTAS', 'SIGUEN TRABAJANDO EN LAS RESPUESTAS',
        'QUEDA PAUSADO', 'ESTA PAUSADO', 'HASTA QUE RESPONDAN LAS CONSULTAS', 'DEJENLO EN PAUSA',
        'POR AHORA MEJOR DEJENLO EN PAUSA', 'QUEDO PENDIENTE'
    ]):
        return 'en espera'
    if any(x in n for x in [
        'PRELIMINAR', 'TERMINAN DE COMPLETAR', 'INFORMACION QUE ESTABA PENDIENTE', 'INFORMACION PENDIENTE',
        'HEMOS RECIBIDO UNA INVITACION', 'INFORMACION SE ENCUENTRA EN SU CARPETA', 'NOS LLEGO LA INVITACION',
        'YA LLEGO LA INVITACION', 'YA ESTA EN SU CARPETA', 'ESTA EN SU CARPETA', 'RECIEN NOS COMPARTIERON LA INFORMACION INICIAL', 'DOCUMENTACION PRELIMINAR',
        'ENTRO INFO NUEVA', 'DEJARON EN SU CARPETA', 'NOS COMPARTIERON LA INFORMACION INICIAL'
    ]):
        return 'revisión inicial'
    if any(x in n for x in [
        'SE REACTIVA', 'RESPUESTAS A CONSULTAS', 'REVISAR SU CARPETA', 'REVISAR LA CARPETA', 'YA PUEDEN REVISAR',
        'SE TERMINO DE DESCARGAR', 'YA SE TERMINO DE DESCARGAR', 'YA QUEDO LISTA LA DESCARGA', 'TERMINO DE DESCARGARSE',
        'SE VUELVE A MOVER', 'SUBIERON RESPUESTAS', 'LLEGO LAS RESPUESTAS', 'LLEGARON LAS RESPUESTAS',
        'RECIBIMOS LAS RESPUESTAS', 'RECIBIMOS RESPUESTAS'
    ]):
        return 'revisión interna'
    return None


def existing_tasks(config):
    list_id = config['clickup']['list_id']
    data = api(config, 'GET', f'/list/{list_id}/task?include_closed=true&subtasks=true')
    return data.get('tasks', [])


def score_match(project_raw: str, task_name: str):
    p_tokens = norm_tokens(project_raw)
    t_tokens = norm_tokens(task_name)
    if not p_tokens or not t_tokens:
        return 0.0
    p_num = p_tokens[0] if p_tokens and p_tokens[0].isdigit() else None
    t_num = t_tokens[0] if t_tokens and t_tokens[0].isdigit() else None
    inter = len(set(p_tokens) & set(t_tokens))
    base = inter / max(1, len(set(p_tokens)))
    if p_num and t_num and p_num == t_num:
        base += 1.0
    return base


def find_match(project_raw: str, tasks):
    scored = []
    for t in tasks:
        s = score_match(project_raw, t.get('name', ''))
        scored.append((s, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.5:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.2 and scored[0][0] < 1.5:
        return None
    return scored[0][1]


def canonical_name(project_raw: str):
    cleaned = normalize_text(project_raw)
    if not cleaned:
        return 'XX SIN NOMBRE'
    parts = cleaned.split()
    if parts and parts[0].isdigit():
        return cleaned
    return 'XX ' + cleaned


def append_note(desc: str, note: str):
    block = f'\n\n{note}'
    desc = desc or ''
    if note in desc:
        return desc
    return (desc + block).strip()


def load_state(config):
    p = state_path(config)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {'processed_ids': []}


def save_state(config, state):
    p = state_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def process_message(config, message_id: str, body: str, *, sender: str | None = None, timestamp: str | None = None, attachments: list[dict] | None = None):
    state = load_state(config)
    if message_id in state['processed_ids']:
        return {
            'status': 'duplicate',
            'message_id': message_id,
            'clickup_action': 'duplicate',
        }

    allowed_emojis = config['routing'].get('allowed_emojis', ['📢', '📣'])
    parsed = parse_message(body, allowed_emojis)
    if not parsed:
        state['processed_ids'].append(message_id)
        state['processed_ids'] = state['processed_ids'][-500:]
        save_state(config, state)
        return {
            'status': 'ignored',
            'reason': 'no_emoji',
            'clickup_action': 'ignored',
        }

    target_status = classify_status(parsed['rest'])
    attachments = attachments or []
    context_block = build_context_block(
        sender=sender,
        timestamp=timestamp,
        message_id=message_id,
        body=parsed['body'],
        attachments=attachments,
        target_status=target_status,
    )
    tasks = existing_tasks(config)
    match = find_match(parsed['project_raw'], tasks)
    comment = None
    comment_error = None
    if match:
        current_desc = match.get('description') or ''
        update = {'description': append_note(current_desc, context_block)}
        if target_status:
            update['status'] = target_status
        res = api(config, 'PUT', f"/task/{match['id']}", update)
        try:
            comment = create_task_comment(config, res.get('id') or match['id'], context_block)
        except Exception as err:
            comment_error = str(err)
        out = {
            'status': 'updated',
            'task_id': res.get('id'),
            'name': res.get('name'),
            'new_status': res.get('status', {}).get('status'),
            'clickup_action': 'updated',
            'project_guess': parsed['project_raw'],
            'clickup_target_status': target_status,
            'comment_id': (comment or {}).get('id'),
        }
    else:
        name = canonical_name(parsed['project_raw'])
        create = {'name': name, 'description': context_block}
        if target_status:
            create['status'] = target_status
        list_id = config['clickup']['list_id']
        res = api(config, 'POST', f'/list/{list_id}/task', create)
        out = {
            'status': 'created',
            'task_id': res.get('id'),
            'name': res.get('name'),
            'new_status': res.get('status', {}).get('status'),
            'clickup_action': 'created',
            'project_guess': parsed['project_raw'],
            'clickup_target_status': target_status,
        }

    uploaded_attachments = []
    attachment_errors = []
    for position, attachment in enumerate(attachments, start=1):
        try:
            uploaded_attachments.append(upload_task_attachment(
                config,
                out['task_id'],
                attachment,
                message_id=message_id,
                position=position,
            ))
        except Exception as err:
            attachment_errors.append({
                'filename': attachment_filename(message_id, attachment, position),
                'error': str(err),
            })

    out['attachment_uploads'] = uploaded_attachments
    if attachment_errors:
        out['attachment_errors'] = attachment_errors
    out['attachment_count'] = len(uploaded_attachments)
    if comment is not None:
        out['comment_id'] = comment.get('id')
    if comment_error:
        out['comment_error'] = comment_error

    state['processed_ids'].append(message_id)
    state['processed_ids'] = state['processed_ids'][-500:]
    save_state(config, state)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument('--message-id', required=True)
    ap.add_argument('--body', required=True)
    args = ap.parse_args()
    config = load_config(Path(args.config))
    print(json.dumps(process_message(config, args.message_id, args.body), ensure_ascii=False))


if __name__ == '__main__':
    main()
