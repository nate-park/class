import io
import json
import sqlite3
import unittest
from uuid import UUID, uuid4
from src.database import connect, migrate, rollback
from src.api.tasks import API
from src.shared.taskValidation import validate, Invalid, STATUSES


class ValidationTests(unittest.TestCase):
    def test_normalization_and_no_mutation(self):
        original = {'title': '  日本語 😀  '}
        self.assertEqual(validate(original), {'title': '日本語 😀', 'status': 'todo'})
        self.assertEqual(original, {'title': '  日本語 😀  '})
        self.assertEqual(validate(original), validate(original))

    def test_invalid_payloads(self):
        for value in [None, [], {}, {'title': None}, {'title': 42}, {'title': '  '}, {'title': 'a'*201}, {'title': 'x', 'extra': 1}, {'title': 'x', 'status': None}, {'title': 'x', 'status': []}, {'title': '\x00'}]:
            with self.subTest(value=value), self.assertRaises(Invalid):
                validate(value)

    def test_boundaries_and_statuses(self):
        for length in [1, 200]:
            self.assertEqual(len(validate({'title': 'x'*length})['title']), length)
        for status in STATUSES:
            self.assertEqual(validate({'status': status}, update=True), {'status': status})
        for payload in [{}, {'title': None}, {'status': 'invalid'}]:
            with self.assertRaises(Invalid):
                validate(payload, update=True)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        self.addCleanup(self.db.close)
        migrate(self.db)

    def test_defaults_and_repeatable_migration(self):
        self.db.execute('INSERT INTO tasks(id,title) VALUES (?,?)', (str(uuid4()), 'Task'))
        migrate(self.db)
        row = self.db.execute('SELECT * FROM tasks').fetchone()
        self.assertEqual(row['status'], 'todo')
        self.assertTrue(row['created_at'].endswith('Z'))
        self.assertTrue(row['updated_at'].endswith('Z'))

    def test_constraints(self):
        for title, status in [('', 'todo'), (' x ', 'todo'), ('x'*201, 'todo'), ('x', 'bad'), (None, 'todo')]:
            with self.subTest(title=title), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO tasks(id,title,status) VALUES (?,?,?)', (str(uuid4()), title, status))

    def test_rollback(self):
        rollback(self.db)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='tasks'").fetchone())
        migrate(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)


class APITests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        self.addCleanup(self.db.close)
        migrate(self.db)
        self.app = API(self.db)

    def request(self, method, path='/api/tasks', data=None, query='', raw=None):
        body = raw if raw is not None else json.dumps(data).encode()
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': query, 'CONTENT_LENGTH': str(len(body)), 'wsgi.input': io.BytesIO(body)}
        captured = []
        result = b''.join(self.app(env, lambda status, headers: captured.append((status, headers))))
        self.assertEqual(dict(captured[0][1])['Content-Length'], str(len(result)))
        return int(captured[0][0].split()[0]), json.loads(result) if result else None

    def test_crud_lifecycle(self):
        self.assertEqual(self.request('GET'), (200, {'tasks': []}))
        status, task = self.request('POST', data={'title': '  Hello 😀  '})
        self.assertEqual(status, 201)
        UUID(task['id'])
        self.assertEqual(task['title'], 'Hello 😀')
        self.assertEqual(task['status'], 'todo')
        path = '/api/tasks/' + task['id']
        self.assertEqual(self.request('GET', path), (200, task))
        status, updated = self.request('PATCH', path, {'status': 'in_review'})
        self.assertEqual(status, 200)
        self.assertEqual(updated['created_at'], task['created_at'])
        self.assertNotEqual(updated['updated_at'], task['updated_at'])
        self.assertEqual(updated['status'], 'in_review')
        self.assertEqual(self.request('DELETE', path), (204, None))
        self.assertEqual(self.request('DELETE', path)[0], 404)
        self.assertEqual(self.request('GET', path)[0], 404)

    def test_validation_errors(self):
        for raw in [b'{', b'null', b'[]', b'\xff', b'{}', b'{"title":""}']:
            self.assertEqual(self.request('POST', raw=raw)[0], 400)
        self.assertEqual(self.request('GET', '/api/tasks/bad')[0], 400)
        for method in ['GET', 'PATCH', 'DELETE']:
            self.assertEqual(self.request(method, '/api/tasks/'+str(uuid4()), {'title':'x'})[0], 404)
        _, task = self.request('POST', data={'title':'x'})
        for payload in [{}, {'status':'bad'}, {'title':None}, {'id':'bad'}]:
            self.assertEqual(self.request('PATCH', '/api/tasks/'+task['id'], payload)[0], 400)

    def test_pagination_and_unique_ids(self):
        tasks = [self.request('POST', data={'title': str(i)})[1] for i in range(3)]
        self.assertEqual(len({task['id'] for task in tasks}), 3)
        expected = sorted(tasks, key=lambda t: (t['created_at'], t['id']))
        self.assertEqual(self.request('GET', query='limit=1&offset=1')[1]['tasks'], expected[1:2])
        for query in ['limit=0', 'limit=101', 'offset=-1', 'limit=x', 'limit=', 'limit=1&limit=2', 'extra=1', 'offset='+('9'*30)]:
            self.assertEqual(self.request('GET', query=query)[0], 400)

    def test_status_filter(self):
        _, a = self.request('POST', data={'title': 'a'})
        _, b = self.request('POST', data={'title': 'b'})
        self.request('PATCH', '/api/tasks/' + b['id'], {'status': 'done'})
        self.assertEqual([t['id'] for t in self.request('GET', query='status=todo')[1]['tasks']], [a['id']])
        self.assertEqual([t['id'] for t in self.request('GET', query='status=done')[1]['tasks']], [b['id']])
        self.assertEqual(len(self.request('GET')[1]['tasks']), 2)
        for query in ['status=bad', 'status=', 'status=todo&status=done']:
            self.assertEqual(self.request('GET', query=query)[0], 400)

    def test_database_failure_is_sanitized_and_atomic(self):
        self.db.execute("CREATE TRIGGER fail_insert AFTER INSERT ON tasks BEGIN SELECT RAISE(ABORT, 'secret database detail'); END")
        self.assertEqual(self.request('POST', data={'title': 'x'}), (500, {'error': {'code': 'internal_error'}}))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)

    def test_unknown_routes_and_methods(self):
        self.assertEqual(self.request('GET', '/other')[0], 404)
        self.assertEqual(self.request('PUT')[0], 405)


if __name__ == '__main__':
    unittest.main()
