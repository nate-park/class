import sqlite3
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / 'db' / 'migrations'


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def migrate(connection):
    connection.executescript((MIGRATIONS / '001_tasks.sql').read_text())


def rollback(connection):
    connection.executescript((MIGRATIONS / '001_tasks.down.sql').read_text())
