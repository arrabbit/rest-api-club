# Campus Events API: Contract and Event Routes

COMP 4633, Fall 2026, Assignment 1

Base path: `/api/v1`. All bodies are JSON (`Content-Type: application/json`). The API is stateless: every request carries the IDs it needs, and nothing is remembered between requests except what is stored in MySQL.

## 1. Conventions

| Topic          | Rule                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| JSON names     | camelCase in JSON, snake_case in MySQL                                                                                    |
| Timestamps     | ISO 8601 UTC ending in `Z`, e.g. `2026-12-05T18:00:00Z`. Anything without `Z` (no zone, or a `+hh:mm` offset) is rejected |
| Lists          | Wrapped as `{"data": [...]}`                                                                                              |
| Create         | `201` with the new resource and a `Location` header                                                                       |
| Delete         | `204` with no body                                                                                                        |
| Derived fields | `registeredCount` and `spotsLeft` are computed on every read (`spotsLeft = capacity - registeredCount`), never stored     |
| Check order    | 400 (body/field validation), then 404 (resource missing), then 409 (business rule)                                        |

### Error shape (every 4xx and 5xx)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request body is invalid.",
    "details": { "errors": [ { "field": "capacity", "reason": "must be a positive integer" } ] }
  }
}
```

`details` is optional. `app/errors.py` includes it only when the route passes one and leaves it out otherwise, so clients must not assume it exists.

### Error codes

| Status | Code                                                    | Used when                                                                                                                                               |
| ------ | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 400    | `VALIDATION_ERROR`                                      | Malformed JSON, body not an object, missing or wrong-type field, empty text, non-positive capacity, bad or past `startTime`, empty PATCH, unknown field |
| 404    | `EVENT_NOT_FOUND`                                       | No event with that ID (including a non-numeric ID in the path)                                                                                          |
| 404    | `PARTICIPANT_NOT_FOUND`                                 | Registration route                                                                                                                                      |
| 404    | `REGISTRATION_NOT_FOUND`                                | Registration route                                                                                                                                      |
| 404    | `NOT_FOUND`                                             | Unknown URL                                                                                                                                             |
| 405    | `METHOD_NOT_ALLOWED`                                    | Wrong method for a URL                                                                                                                                  |
| 409    | `CAPACITY_BELOW_REGISTRATIONS`                          | PATCH sets capacity below current registrations                                                                                                         |
| 409    | `EVENT_HAS_REGISTRATIONS`                               | DELETE on an event that has registrations                                                                                                               |
| 409    | `DUPLICATE_REGISTRATION`, `EVENT_FULL`, `EVENT_STARTED` | Registration route                                                                                                                                      |
| 500    | `INTERNAL_ERROR`                                        | Anything unexpected. Generic message, no SQL, no stack trace                                                                                            |
| 400    | `BAD_REQUEST`                                           | Raised by Flask itself, for example `request.get_json()` on malformed JSON. Event routes avoid it: they read the body with `get_json(silent=True)` and raise `VALIDATION_ERROR` instead |
| 409    | `CONFLICT`                                              | Backstop for a MySQL `IntegrityError` (UNIQUE or foreign key) that slipped past a route check. Generic message, no SQL text |
| 415    | `UNSUPPORTED_MEDIA_TYPE`                                | Raised by Flask when a body is read strictly with the wrong `Content-Type` |
| any    | `HTTP_ERROR`                                            | Any other Flask HTTP error not listed above |

## 2. Endpoint table (all eight operations)

| Method | Path | Body | Success | Errors | Owner |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/events` | title, location, startTime, capacity | 201 event + `Location` | 400 `VALIDATION_ERROR` | A |
| GET | `/api/v1/events` | none | 200 `{data:[event]}` | none | A |
| GET | `/api/v1/events/{eventId}` | none | 200 event | 404 `EVENT_NOT_FOUND` | A |
| PATCH | `/api/v1/events/{eventId}` | any of title, location, startTime, capacity | 200 event | 400 `VALIDATION_ERROR`, 404 `EVENT_NOT_FOUND`, 409 `CAPACITY_BELOW_REGISTRATIONS` | A |
| DELETE | `/api/v1/events/{eventId}` | none | 204 | 404 `EVENT_NOT_FOUND`, 409 `EVENT_HAS_REGISTRATIONS` | A |
| POST | `/api/v1/events/{eventId}/registrations` | participantId | 201 registration + `Location` | 400, 404 `EVENT_NOT_FOUND` / `PARTICIPANT_NOT_FOUND`, 409 `DUPLICATE_REGISTRATION` / `EVENT_FULL` / `EVENT_STARTED` | B |
| GET | `/api/v1/events/{eventId}/registrations` | none | 200 `{data:[registration]}` with `participantName` | 404 `EVENT_NOT_FOUND` | B |
| DELETE | `/api/v1/events/{eventId}/registrations/{registrationId}` | none | 204 | 404 `EVENT_NOT_FOUND` / `REGISTRATION_NOT_FOUND` | B |

The registration rows are summarized for completeness. Joseph's detailed section is added to this file by Joseph.

## 3. Resource representations

### Event

| Field             | Type    | Notes                                                                                                         |
| ----------------- | ------- | ------------------------------------------------------------------------------------------------------------- |
| `id`              | integer | Server-assigned, read-only                                                                                    |
| `title`           | string  | Required. Trimmed, 1 to 100 characters **[proposal]**                                                         |
| `location`        | string  | Required. Trimmed, 1 to 200 characters **[proposal]**                                                         |
| `startTime`       | string  | Required. ISO 8601 UTC with `Z`. Must be in the future when set or changed                                    |
| `capacity`        | integer | Required. 1 to 10000 (upper bound is sanity check). JSON `true`/`false`, `"3"`, `2.5` and `null` are rejected |
| `registeredCount` | integer | Read-only, computed                                                                                           |
| `spotsLeft`       | integer | Read-only, computed                                                                                           |

```json
{
  "id": 4,
  "title": "Wheel-throwing basics",
  "location": "Art Studio B, Room 214",
  "startTime": "2026-12-05T18:00:00Z",
  "capacity": 2,
  "registeredCount": 0,
  "spotsLeft": 2
}
```

## 4. Event routes in detail

### 4.1 POST /api/v1/events: create an event

- **Request body:** `title`, `location`, `startTime`, `capacity`, all required. Any other field (including `id`, `registeredCount`, `spotsLeft`) is a 400 
- **Success:** `201`, body is the event, header `Location: /api/v1/events/{id}`.
- **Errors:** `400 VALIDATION_ERROR`. All field problems are reported together in `details.errors`.

Request:
```json
{ "title": "Wheel-throwing basics", "location": "Art Studio B, Room 214",
  "startTime": "2026-12-05T18:00:00Z", "capacity": 2 }
```
Response `201 Created`: the event sample in section 3 (`registeredCount` 0, `spotsLeft` 2).

Error example, `400`:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Request body is invalid.",
  "details": { "errors": [
    { "field": "title", "reason": "must not be empty" },
    { "field": "capacity", "reason": "must be a positive integer" } ] } } }
```

Flow: parse JSON, `validate_event_create(body)`, `repository.create_event(title, location, start_time, capacity)`, serialize, return 201.

### 4.2 GET /api/v1/events: list events

- **Success:** `200 {"data": [event, ...]}`. An empty list is `{"data": []}`, not a 404.
- **Order:** `startTime` ascending, then `id`. Past events are included.
- **Errors:** none expected (500 only for unexpected failures).

Flow: `repository.list_events()`, serialize each.

### 4.3 GET /api/v1/events/{eventId}: retrieve one event

- **Success:** `200`, body is the event.
- **Errors:** `404 EVENT_NOT_FOUND`.

Flow: parse the ID, `repository.get_event(id)`; `None` raises `ApiError(404, "EVENT_NOT_FOUND", ...)`.

### 4.4 PATCH /api/v1/events/{eventId}: update event details

- **Request body:** any non-empty subset of `title`, `location`, `startTime`, `capacity`. Each provided field follows the same rules as create. Only provided fields change.
- **Rules:**
  - Empty body `{}` or an unknown field (including read-only ones) gives `400`.
  - A provided `startTime` must be in the future. Fields that are not provided are not re-checked, so renaming an event that has already started is allowed.
  - `capacity` below the current registration count gives `409 CAPACITY_BELOW_REGISTRATIONS`. Equal to the count is allowed.
- **Success:** `200`, body is the updated event.
- **Errors:** `400 VALIDATION_ERROR`, `404 EVENT_NOT_FOUND`, `409 CAPACITY_BELOW_REGISTRATIONS`.

Request: `{ "capacity": 1 }` on an event with 2 registrations returns `409`:
```json
{ "error": { "code": "CAPACITY_BELOW_REGISTRATIONS",
  "message": "Event 4 already has 2 registrations; capacity cannot be 1.",
  "details": { "eventId": 4, "registeredCount": 2, "requestedCapacity": 1 } } }
```

Flow: parse JSON, `validate_event_patch(body)` (400), `get_event` (404), if `capacity` provided compare with `count_registrations` (409), `repository.update_event(id, changes)`, re-read and return 200.

### 4.5 DELETE /api/v1/events/{eventId}: delete an event

- **Rule:** only allowed when the event has no registrations.
- **Success:** `204`, empty body.
- **Errors:** `404 EVENT_NOT_FOUND`, `409 EVENT_HAS_REGISTRATIONS`.

Error example, `409`:
```json
{ "error": { "code": "EVENT_HAS_REGISTRATIONS",
  "message": "Event 1 has 2 registrations and cannot be deleted.",
  "details": { "eventId": 1, "registeredCount": 2 } } }
```

Flow: `get_event` (404), `count_registrations` (409 if > 0), `delete_event`, return 204. The foreign key (`ON DELETE RESTRICT`) is the database backstop; if it ever fires, `handle_integrity_error` in `app/errors.py` returns `409 CONFLICT` with a generic message and no SQL text. The specific `EVENT_HAS_REGISTRATIONS` code comes only from the route's own `count_registrations` check.

## 5. Implementation notes for `app/routes/events.py`

- Blueprint `events_bp` with `url_prefix="/api/v1/events"`; Precious (owner of `app/__init__.py`) registers it in `create_app()`, at the placeholder comment below `register_error_handlers(app)`, which must stay.
- Use a string path parameter (`<event_id>`), then parse it as a positive integer. A value like `abc` or `0` returns `404 EVENT_NOT_FOUND`. Flask's `<int:...>` converter would return Anna's generic `NOT_FOUND` instead.
- Read the body with `request.get_json(silent=True)`. `None` or a non-dict value raises `ApiError(400, "VALIDATION_ERROR", ...)` with `field: "body"`. This covers malformed JSON and a missing `Content-Type`.
- Call Precious' validators (names assumed, to be confirmed with Precious): `validate_event_create(body) -> dict` and `validate_event_patch(body) -> dict`. They return clean values (trimmed text, `startTime` as a timezone-aware `datetime`) or raise `ApiError` with every problem listed in `details.errors`.
- Raise errors only with Anna's `ApiError`: `from app.errors import ApiError`, then `raise ApiError(<status>, "<ERROR_CODE>", "<message>", {<optional details>})`, for example `raise ApiError(404, "EVENT_NOT_FOUND", "No event with id 4.", {"eventId": 4})`. The fourth argument is optional and is a dict. The routes never build error responses by hand; `register_error_handlers(app)` in `create_app()` turns every `ApiError` into the JSON error shape from section 1.
- Serialize with one helper, `event_to_json(row)`: snake_case to camelCase, `datetime` to `YYYY-MM-DDTHH:MM:SSZ`, and `spotsLeft = capacity - registeredCount`.
- Routes talk to MySQL only through `repository.py` and never write SQL.
- Follow the README standards: a file header (purpose, authors, date), a docstring on every function (purpose, parameters, return value), inline comments for tricky logic, snake_case names, and functions under about 25 to 30 lines. In practice each route handler stays short and the work moves into small helpers such as `parse_event_id`, `read_json_body` and `event_to_json`.
- Git policy: work on your own branch and merge to `main` at a milestone, with the group told about the merge. No `__pycache__` or other compiled files in the merge.

### Team setup and shared files

Anna's first files are in the team repo (`rest-api-club`). After pulling, run `pip install -r requirements.txt` (Flask 3.1.3, mysql-connector-python 8.4.0, python-dotenv, gunicorn, pytest, pytest-cov).

| File | Owner | What it gives the event routes |
| --- | --- | --- |
| `app/errors.py` | Anna | `ApiError(status, code, message, details=None)` and `register_error_handlers(app)`. Handles `ApiError`, Flask's own HTTP errors (JSON instead of HTML), MySQL `IntegrityError` (409 `CONFLICT`) and any other exception (500 `INTERNAL_ERROR`, with the stack trace logged on the server only) |
| `app/config.py` | Anna | `get_db_settings()`, which reads the database settings from `.env`. Only the repository layer (Darren) uses it; routes never connect to MySQL. Also `is_debug_enabled()`, which is off unless `FLASK_DEBUG=1` |
| `app/__init__.py` | Precious | `create_app()`, which already registers the error handlers and serves `GET /api`. A placeholder comment marks where the blueprints are registered |
| `requirements.txt` | Anna | If an event route or test needs a new package, ask Anna to add it (or tell her if you had to add it yourself) so edits do not overwrite each other |
| `tests/unit/test_errors.py` | Anna | Tests for the error handlers (`ApiError`, unknown route, wrong method, malformed JSON, `IntegrityError`, unexpected crash). Event tests do not need to repeat those |

Local database settings: copy `.env.example` to `.env` and fill in `MYSQL_USER`, `MYSQL_PASSWORD` and `MYSQL_DATABASE` (`MYSQL_HOST`, `MYSQL_PORT` and `FLASK_DEBUG` have defaults in the example). `.env` is gitignored. On the VM, `ENV_FILE` points to a `.env` kept outside the repo.

### Requests to the other roles

| To       | Request                                                                                                                                                                                                              |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Darren   | `list_events()` and `get_event()` rows include `registered_count` (a `COUNT` subquery or `LEFT JOIN`), so a list does not need one `count_registrations` call per event. `update_event` returns the full updated row |
| Darren   | Row keys are snake_case (`start_time` as a naive-UTC or aware `datetime`); `event_to_json` does the camelCase conversion. Confirm this split                                                                         |
| Anna     | None open. `ApiError` and the handlers were checked against `app/errors.py`, and this contract now matches them (`details` optional, `CONFLICT` for the `IntegrityError` backstop) |
| Precious | Validator names and signatures above; reject `bool` for integer fields (`isinstance(True, int)` is true in Python). Register `events_bp` in `create_app()` (the placeholder is already in `app/__init__.py`) |
| Joseph   | Reuse the same `ApiError` codes and `event_to_json`; add B's registration section to this file                                                                                                                       |

## 6. Event test plan (feeds `docs/requirements-to-tests.md`)

Unit tests (`tests/unit/test_event_routes.py`, fake repository, marker `unit`):

| Test name | Requirement / contract line | Expect |
| --- | --- | --- |
| `test_create_event_returns_201_and_location` | Create event | 201, `Location` header, `spotsLeft == capacity` |
| `test_create_event_missing_field_400` | Validate required fields | 400, field named in `details.errors` |
| `test_create_event_reports_all_errors_together` | Consistent errors | 400, two errors in one response |
| `test_create_event_bool_capacity_400` | Positive integer capacity | 400 for `true` |
| `test_create_event_capacity_zero_and_negative_400` | Positive integer capacity | 400 for 0 and -1 |
| `test_create_event_capacity_string_or_float_400` | Types | 400 for `"3"` and `2.5` |
| `test_create_event_blank_title_400` | Empty text | 400 for `""` and `"   "` |
| `test_create_event_start_in_past_400` | Future start time | 400 |
| `test_create_event_start_without_timezone_400` | Consistent date format | 400 for no `Z` and for `+00:00` |
| `test_create_event_malformed_json_400` | JSON error handling | 400 JSON error, not HTML |
| `test_create_event_unknown_field_400` | Contract | 400 |
| `test_list_events_returns_data_wrapper` | List events | 200, `{"data": [...]}`, ordered by `startTime` |
| `test_list_events_empty` | List events | 200, `{"data": []}` |
| `test_get_event_ok` | Retrieve one event | 200, all seven fields |
| `test_get_event_not_found_404` | Missing resource | 404 `EVENT_NOT_FOUND` |
| `test_get_event_non_numeric_id_404` | Missing resource | 404 `EVENT_NOT_FOUND` |
| `test_patch_event_partial_update_200` | Update details | Only the sent field changes |
| `test_patch_event_empty_body_400` | Contract | 400 |
| `test_patch_event_unknown_field_400` | Contract | 400, including `registeredCount` |
| `test_patch_event_start_in_past_400` | Future start time | 400 |
| `test_patch_event_not_found_404` | Missing resource | 404 |
| `test_patch_event_capacity_below_count_409` | Capacity rule | 409 `CAPACITY_BELOW_REGISTRATIONS` |
| `test_patch_event_capacity_equal_to_count_200` | Capacity boundary | 200 |
| `test_delete_event_204` | Delete event | 204, empty body |
| `test_delete_event_not_found_404` | Missing resource | 404 |
| `test_delete_event_with_registrations_409` | Delete rule | 409 `EVENT_HAS_REGISTRATIONS` |
| `test_events_url_wrong_method_returns_json_405` | Error shape | 405 `METHOD_NOT_ALLOWED` in the standard JSON shape, from an events URL. Unknown route, malformed JSON and crash cases are already covered by Anna's `tests/unit/test_errors.py` |

Integration tests (`tests/integration/test_event_rules.py`, real MySQL test database, marker `integration`):

| Test name | Expect |
| --- | --- |
| `test_create_then_get_round_trip` | Stored values match what was sent |
| `test_patch_capacity_below_registrations_409_and_unchanged` | 409, and a follow-up GET shows the old capacity |
| `test_patch_capacity_equal_to_registrations_ok` | 200 |
| `test_delete_event_with_registrations_409_and_event_still_exists` | 409, event and registrations intact |
| `test_delete_event_without_registrations_removes_it` | 204, then GET returns 404 |
| `test_registered_count_and_spots_left_follow_bookings` | Counts change after a register and a cancel |

Every documented error code for events (`VALIDATION_ERROR`, `EVENT_NOT_FOUND`, `CAPACITY_BELOW_REGISTRATIONS`, `EVENT_HAS_REGISTRATIONS`) has at least one test above.

## 7. Assumptions to carry into the report

1. All timestamps are UTC and must end in `Z`.
2. Event text is trimmed before it is checked for emptiness.
3. Capacity has a sanity upper limit of 10000.
4. PATCH does not re-validate fields that are not sent, so a started event can be renamed.
5. Events that have started or passed stay visible in the list.
6. Only unauthenticated, sequential use is supported. There is no concurrency control, as the assignment allows.

## 8. Demo requests (local; replace the base URL for the VM)

```bash
BASE=http://127.0.0.1:5000/api/v1
curl -i -X POST $BASE/events -H 'Content-Type: application/json' \
  -d '{"title":"Wheel-throwing basics","location":"Art Studio B, Room 214","startTime":"2026-12-05T18:00:00Z","capacity":2}'
curl -i $BASE/events
curl -i $BASE/events/4
curl -i -X PATCH $BASE/events/4 -H 'Content-Type: application/json' -d '{"capacity":3}'
curl -i -X DELETE $BASE/events/4
```
