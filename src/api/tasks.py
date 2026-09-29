import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import parse_qs
from src.shared.taskValidation import Invalid, validate, task_id, pagination


class API:
    def __init__(self, connection):
        self.db = connection

    def __call__(self, environ, start_response):
        try:
            status, data = self.dispatch(environ)
        except Invalid as error:
            status, data = 400, {'error': {'code': 'invalid_input', 'fields': error.fields}}
        except sqlite3.Error:
            self.db.rollback()
            status, data = 500, {'error': {'code': 'internal_error'}}
        reasons = {200: 'OK', 201: 'Created', 204: 'No Content', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed', 500: 'Internal Server Error'}
        body = b'' if status == 204 else json.dumps(data).encode()
        start_response(f'{status} {reasons[status]}', [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
        return [body]

    def dispatch(self, env):
        method, path = env['REQUEST_METHOD'], env.get('PATH_INFO', '')
        collection = path == '/api/tasks'
        if not collection and (not path.startswith('/api/tasks/') or '/' in path[len('/api/tasks/'):]):
            return 404, {'error': {'code': 'not_found'}}
        identifier = None if collection else task_id(path[len('/api/tasks/'):])
        if method not in (('GET', 'POST') if collection else ('GET', 'PATCH', 'DELETE')):
            return 405, {'error': {'code': 'method_not_allowed'}}
        if method in ('POST', 'PATCH'):
            try:
                length = int(env.get('CONTENT_LENGTH') or '0')
                if not 0 < length <= 65536:
                    raise ValueError()
                payload = json.loads(env['wsgi.input'].read(length))
            except (ValueError, UnicodeError):
                raise Invalid({'body': 'Invalid JSON or body size'}) from None
            values = validate(payload, update=method == 'PATCH')
        if collection and method == 'GET':
            limit, offset = pagination(parse_qs(env.get('QUERY_STRING', ''), keep_blank_values=True))
            rows = self.db.execute('SELECT * FROM tasks ORDER BY created_at, id LIMIT ? OFFSET ?', (limit, offset))
            return 200, {'tasks': [dict(row) for row in rows]}
        if method == 'POST':
            identifier = str(uuid4())
            with self.db:
                self.db.execute('INSERT INTO tasks(id,title,status) VALUES (?,?,?)', (identifier, values['title'], values['status']))
            return 201, self.get(identifier)
        existing = self.get(identifier)
        if existing is None:
            return 404, {'error': {'code': 'not_found'}}
        if method == 'GET':
            return 200, existing
        if method == 'DELETE':
            with self.db:
                self.db.execute('DELETE FROM tasks WHERE id=?', (identifier,))
            return 204, None
        values['updated_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        assignments = ','.join(f'{key}=?' for key in values)
        with self.db:
            self.db.execute(f'UPDATE tasks SET {assignments} WHERE id=?', (*values.values(), identifier))
        return 200, self.get(identifier)

    def get(self, identifier):
        row = self.db.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
        return dict(row) if row else None
