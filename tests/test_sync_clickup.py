import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve()
MODULE_CANDIDATES = [
    HERE.parents[1] / 'sync_clickup.py',
    HERE.parents[1] / 'src' / 'sync_clickup.py',
]
MODULE_PATH = next(path for path in MODULE_CANDIDATES if path.exists())
MODULE_DIR = MODULE_PATH.parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

sync_clickup = importlib.import_module('sync_clickup')


class SyncClickupTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            'existing_tasks': sync_clickup.existing_tasks,
            'api': sync_clickup.api,
            'create_task_comment': sync_clickup.create_task_comment,
            'upload_task_attachment': sync_clickup.upload_task_attachment,
        }

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(sync_clickup, name, value)

    def make_config(self, root: Path):
        token_path = root / 'secrets' / 'proyecto_d_clickup_token'
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text('fake-token', encoding='utf-8')
        state_dir = root / 'state'
        state_dir.mkdir(parents=True, exist_ok=True)
        return {
            'project_key': 'proyecto_d',
            'clickup': {
                'token_path': str(token_path),
                'list_id': 'test-list',
                'api': 'https://api.clickup.test',
            },
            'routing': {
                'allowed_emojis': ['📢', '📣'],
            },
            'paths': {
                'state_path': str(state_dir / 'whatsapp_state.json'),
                'audit_log_path': str(state_dir / 'audit.log'),
                'supabase_error_log_path': str(state_dir / 'supabase_errors.log'),
            },
        }

    def test_clean_body_removes_comunicado_with_or_without_leading_emoji(self):
        self.assertEqual(
            sync_clickup.clean_body('Comunicado 📢 120 UTP BREÑA pasa a metrado'),
            '120 UTP BREÑA pasa a metrado',
        )
        self.assertEqual(
            sync_clickup.clean_body('📣 COMUNICADO 120 UTP BREÑA pasa a metrado'),
            '120 UTP BREÑA pasa a metrado',
        )

    def test_parse_message_does_not_leave_comunicado_in_project_name(self):
        parsed = sync_clickup.parse_message('📣 COMUNICADO 120 UTP BREÑA pasa a metrado y cotizaciones', ['📢', '📣'])
        self.assertIsNotNone(parsed)
        self.assertNotIn('COMUNICADO', parsed['project_raw'])
        self.assertEqual(parsed['project_raw'], '120 UTP BRENA')
        self.assertEqual(sync_clickup.classify_status(parsed['rest']), 'metrado y cotizaciones')

    def test_process_message_creates_task_and_uploads_attachment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            captured = {}

            sync_clickup.existing_tasks = lambda cfg: []

            def fake_api(cfg, method, path, data=None):
                captured['request'] = {'method': method, 'path': path, 'data': data}
                self.assertEqual(method, 'POST')
                self.assertTrue(path.startswith('/list/'))
                return {
                    'id': 'task-create-1',
                    'name': data['name'],
                    'status': {'status': data.get('status')},
                }

            sync_clickup.api = fake_api
            sync_clickup.create_task_comment = lambda cfg, task_id, comment_text: {'id': 'comment-1'}
            sync_clickup.upload_task_attachment = lambda cfg, task_id, attachment, **kwargs: {
                'filename': sync_clickup.attachment_filename(kwargs['message_id'], attachment, kwargs['position']),
                'mime_type': attachment.get('mime_type'),
                'size_bytes': 4,
            }

            result = sync_clickup.process_message(
                config,
                'msg-create-1',
                '📢 COMUNICADO 120 UTP BREÑA pasa a metrado y cotizaciones',
                sender='+51936005850',
                timestamp='2026-06-29T16:00:00Z',
                attachments=[{'filename': 'foto.jpg', 'mime_type': 'image/jpeg', 'data': 'ZmFrZQ=='}],
            )

            self.assertEqual(result['status'], 'created')
            self.assertEqual(result['clickup_target_status'], 'metrado y cotizaciones')
            self.assertEqual(result['attachment_count'], 1)
            self.assertNotIn('comment_id', result)
            self.assertNotIn('COMUNICADO', captured['request']['data']['name'])
            self.assertIn('adjuntos', captured['request']['data']['description'])

            state = json.loads(Path(config['paths']['state_path']).read_text(encoding='utf-8'))
            self.assertIn('msg-create-1', state['processed_ids'])

    def test_duplicate_message_can_backfill_attachments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            Path(config['paths']['state_path']).write_text(json.dumps({'processed_ids': ['msg-dup-1']}), encoding='utf-8')

            sync_clickup.existing_tasks = lambda cfg: [{
                'id': 'task-dup-1',
                'name': '120 UTP BREÑA',
                'description': 'PROYECTO D · EVENTO WHATSAPP\n- message_id: msg-dup-1',
                'status': {'status': 'revisión inicial'},
            }]
            sync_clickup.upload_task_attachment = lambda cfg, task_id, attachment, **kwargs: {
                'filename': sync_clickup.attachment_filename(kwargs['message_id'], attachment, kwargs['position']),
                'mime_type': attachment.get('mime_type'),
                'size_bytes': 4,
            }

            result = sync_clickup.process_message(
                config,
                'msg-dup-1',
                '📣 COMUNICADO 120 UTP BREÑA la información ya se encuentra en su carpeta',
                attachments=[{'filename': 'plano.pdf', 'mime_type': 'application/pdf', 'data': 'ZmFrZQ=='}],
            )

            self.assertEqual(result['status'], 'duplicate')
            self.assertTrue(result.get('duplicate_attachment_backfill'))
            self.assertEqual(result['attachment_count'], 1)
            self.assertEqual(result['task_id'], 'task-dup-1')


if __name__ == '__main__':
    unittest.main()
