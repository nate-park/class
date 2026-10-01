from uuid import UUID

STATUSES = ('todo', 'in_progress', 'in_review', 'done')


class Invalid(ValueError):
    def __init__(self, fields):
        self.fields = fields


def task_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise Invalid({'id': 'Must be a UUID'}) from None


def validate(payload, update=False):
    if not isinstance(payload, dict):
        raise Invalid({'body': 'Must be an object'})
    errors = {key: 'Unknown field' for key in payload.keys() - {'title', 'status'}}
    result = {}
    if not update or 'title' in payload:
        title = payload.get('title')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200 or '\x00' in title:
            errors['title'] = 'Must contain 1–200 trimmed characters without NUL'
        else:
            result['title'] = title.strip()
    if not update or 'status' in payload:
        status = payload.get('status', 'todo')
        if status not in STATUSES:
            errors['status'] = 'Unsupported status'
        else:
            result['status'] = status
    if update and not payload:
        errors['body'] = 'Update must not be empty'
    if errors:
        raise Invalid(errors)
    return result


def pagination(query):
    result = []
    for name, default, lower, upper in [('limit', '20', 1, 100), ('offset', '0', 0, 9223372036854775807)]:
        values = query.get(name, [default])
        value = values[0]
        if len(values) != 1 or not value.isascii() or not value.isdecimal() or len(value) > 19:
            raise Invalid({name: 'Must be a valid integer'})
        number = int(value)
        if not lower <= number <= upper:
            raise Invalid({name: 'Out of range'})
        result.append(number)
    if query.keys() - {'limit', 'offset', 'status'}:
        raise Invalid({'query': 'Unknown query parameter'})
    status = query.get('status', [None])
    if len(status) != 1 or (status[0] is not None and status[0] not in STATUSES):
        raise Invalid({'status': 'Unsupported status'})
    return [*result, status[0]]
