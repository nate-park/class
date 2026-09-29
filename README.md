# Sample task manager

This repository demonstrates how a small team can plan and build a task-management API. You can create tasks, list them, update their titles or status, and delete them. It includes SQLite persistence, shared input validation, automated tests, and GitHub Actions.

Runnable sample implementation for issues [#1](https://github.com/nate-park/class/issues/1), [#2](https://github.com/nate-park/class/issues/2), [#3](https://github.com/nate-park/class/issues/3), and [#4](https://github.com/nate-park/class/issues/4).

## Get started

Python 3.11+ and its standard library are sufficient. No dependency installation or secrets required.

```sh
git clone https://github.com/nate-park/class.git
cd class
python -m unittest discover -s tests -v
python -m src.server
```

The sample server listens on localhost:8000 and creates `tasks.sqlite3`. This is a local teaching example with no authentication; the built-in server is not a production deployment.

Stop the server with Ctrl+C. Tasks persist in the local database between runs. Tests use separate in-memory databases and do not modify that file.

### Try it from PowerShell

With the server running, open a second terminal:

```powershell
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/tasks -ContentType 'application/json' -Body '{"title":"Review assignment"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/tasks
Invoke-RestMethod -Method Patch -Uri "http://127.0.0.1:8000/api/tasks/$($task.id)" -ContentType 'application/json' -Body '{"status":"in_review"}'
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8000/api/tasks/$($task.id)"
```

## Repository structure

| Location | Purpose |
|---|---|
| `src/server.py` | Local HTTP server entry point |
| `src/api/tasks.py` | CRUD routes and persistence operations |
| `src/shared/taskValidation.py` | Shared title, status, UUID, and pagination validation |
| `src/database.py` | Database connections and migration helpers |
| `db/migrations/` | Schema creation and disposable-database rollback |
| `tests/test_tasks.py` | Validation, schema, and API integration tests |
| `.github/workflows/test.yml` | Automated tests on pushes and pull requests |

## Team workflow

Use the [project board](https://github.com/users/nate-park/projects/3) and [Sprint 1 milestone](https://github.com/nate-park/class/milestone/1) to track work. The board tracks GitHub issues; the API's task records are separate local data.

1. Choose an issue, confirm its assignee, and read its requirements, edge cases, acceptance criteria, and ownership notes.
2. Move the issue from **Todo** to **In Progress** and create a branch, for example `git switch -c feature/issue-2-validation`.
3. Keep changes within the issue's ownership boundaries. Coordinate changes to API contracts, shared utilities, or database schemas with the owners of dependent issues first.
4. Run `python -m unittest discover -s tests -v`, push the branch, and open a pull request linking the issue. Describe the behavior changed and test results.
5. Move the issue to **In Review**. Ask another collaborator to review it and check GitHub Actions.
6. After acceptance criteria, review, and tests pass, merge the pull request, close the issue, and move its card to **Done** if needed.

Use the `feature` label for implementation work and `test` for testing/CI work. Keep each issue assigned to the sprint milestone. The initial sample is already on `main`; follow-up changes should use branches and pull requests. This workflow is a team convention, not an enforced branch-protection rule.

## Tests

The test command runs 11 tests with additional input cases. It checks schema defaults and rollback, title/status validation, the CRUD lifecycle, invalid requests, pagination, unique IDs, and sanitized database failures. Every database test gets a fresh in-memory database, cleaned up after the test. CI runs the same command on Python 3.11, 3.12, and 3.13.

## Routes

| Method | Route | Success |
|---|---|---|
| POST | /api/tasks | 201, task object |
| GET | /api/tasks?limit=20&offset=0 | 200, `{ "tasks": [] }` |
| GET | /api/tasks/:id | 200, task object |
| PATCH | /api/tasks/:id | 200, updated task |
| DELETE | /api/tasks/:id | 204, empty body |

Create body: `{"title":"Review assignment"}`. Update body: `{"status":"in_review"}`. Statuses: todo, in_progress, in_review, done. Titles are trimmed, 1–200 Unicode code points, without NUL. Unknown fields, null values, invalid UUIDs/JSON and pagination produce 400. Missing records produce 404; repeated deletion produces 404. Database errors return sanitized 500 responses. Error envelope: `{"error":{"code":"invalid_input","fields":{"title":"..."}}}`; 404/405/500 omit fields.

## Acceptance criteria and ownership

All workstreams currently belong to @nate-park. A contributor should claim the relevant issue before editing its files. Cross-boundary changes require coordination with the owning issue.

### #1 Database
- [ ] Clean initialization and repeated migration succeed without losing rows.
- [ ] Required titles and allowed statuses are enforced; status defaults to todo and timestamps are UTC.
- [ ] UUIDs generated by the API are unique; rollback removes the sample table in an isolated database.
- Owner files: `db/migrations/*`, `src/database.py`; tests: `DatabaseTests` and `APITests.test_pagination_and_unique_ids`.
- Rollback is destructive: only for disposable sample databases. From Python, call `rollback(connection)` from `src.database`; call `migrate(connection)` to recreate. Normal application writes go through validation; SQLite stores UUIDs as text.

### #2 Shared validation
- [ ] Create/update validation trims titles, rejects invalid inputs and unknown fields, and accepts all four statuses.
- [ ] Empty updates and explicit nulls fail; omitted update fields remain unchanged.
- [ ] Unicode and 1/200-character boundaries pass; validation does not mutate inputs.
- Owner file: `src/shared/taskValidation.py`; tests: `ValidationTests`.

### #3 API
- [ ] All five routes return the documented statuses and JSON shapes.
- [ ] Pagination is deterministic; updates preserve created_at and change updated_at.
- [ ] Invalid requests return 400, missing resources 404, and database failures sanitized 500 with no partial write.
- Owner files: `src/api/tasks.py`, `src/server.py`; tests: `APITests`.
- Depends on #1 and #2. Schema and utility changes must be coordinated with those owners.

### #4 Tests and CI
- [ ] One command runs all tests with a fresh in-memory database per test and no production configuration.
- [ ] CI runs on pushes and pull requests for Python 3.11–3.13.
- [ ] Full suite passes; a deliberate failing assertion makes the test command fail.
- [ ] Review GitHub Actions results before moving issues to Done.
- Owner files: `tests/test_tasks.py`, `.github/workflows/test.yml`. Schema tests are in DatabaseTests, utility tests in ValidationTests, integration tests in APITests; coordinate edits by class.

Checkboxes are review gates, not a claim of external review. Keep issues open until review and remote CI are complete.
