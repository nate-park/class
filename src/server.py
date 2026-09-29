from wsgiref.simple_server import make_server
from src.database import connect, migrate
from src.api.tasks import API

if __name__ == '__main__':
    db = connect('tasks.sqlite3')
    migrate(db)
    with make_server('127.0.0.1', 8000, API(db)) as server:
        print('Sample API: http://127.0.0.1:8000/api/tasks')
        server.serve_forever()
