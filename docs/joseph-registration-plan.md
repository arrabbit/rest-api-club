# Joseph: registration contract and implementation plan

Owner: Joseph (GitHub: JD-d3v; branch: JD)
Drafted: October 14, 2026

Status: proposed contract based on Assignment 1 and the team plan. This is
Joseph's contribution for Jordan to incorporate into the shared API contract,
not evidence that the team has approved every detail below.

## Scope and progress

- [x] Draft the three registration operations and test checklist.
- [x] Implement registration listing with isolated route tests.
- [ ] Implement booking and its unit tests.
- [ ] Implement cancellation and its unit tests.
- [ ] Connect shared validation, repository functions, and application factory.
- [ ] Run booking integration tests against the separate MySQL test database.
- [ ] Write and run the deployed API demonstration script.
- [ ] Supply report notes and perform the fresh-clone README walkthrough.

Events, participant management, SQL implementation, and deployment configuration
remain with their respective owners. Concurrency control is outside assignment
scope; demonstrate sequential requests.

## Endpoint contract

All paths begin with `/api/v1`. IDs identify individual resources. JSON uses
camelCase; Python variable and function names use snake_case. Timestamps use
ISO 8601 UTC with trailing `Z`.

| Operation | Method and path | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| Register | POST `/api/v1/events/{eventId}/registrations` | JSON object containing `participantId` | 201 with registration object | 400 invalid JSON/input; 415 unsupported media type; 404 missing event/participant; 409 duplicate, full, or started event |
| List | GET `/api/v1/events/{eventId}/registrations` | Event ID in path; no body | 200 with `{"data": [...]}` | 404 missing event |
| Cancel | DELETE `/api/v1/events/{eventId}/registrations/{registrationId}` | Both IDs in path; no body | 204 with no body | 404 missing event or registration, including registration belonging to another event |

An existing event with zero registrations returns 200 and `{"data": []}`.
Unexpected failures use the existing generic 500 JSON error handler.

Booking request:

```json
{"participantId": 3}
```

Registration representation (also used within the list's `data` array):

```json
{
  "id": 7,
  "eventId": 4,
  "participantId": 3,
  "participantName": "Maya Okafor",
  "registeredAt": "2026-10-14T18:00:00Z"
}
```

Missing-event response currently implemented for listing:

```json
{
  "error": {
    "code": "EVENT_NOT_FOUND",
    "message": "Event 99 does not exist.",
    "details": {"eventId": 99}
  }
}
```

## Rules and proposed decisions

- Require a positive integer participant ID; reject booleans, floats, strings,
  null, missing IDs, non-object bodies, and unknown fields.
- The event and participant must exist before a registration can be created.
- Reject an existing event/participant booking, a full event, and a started event.
- Proposed boundary: reject when current UTC time is greater than or equal to
  the event start time. Confirm the exact-start interpretation with Jordan.
- Proposed precedence when several conditions fail: validate input, check event,
  check participant, check duplicate, check start time, check capacity.
- The server sets the registration timestamp; clients cannot supply it.
- Cancellation deletes the row. Available places are capacity minus registration
  count, never an independently incremented/decremented stored counter.
- A repeated cancellation returns 404. Rebooking is allowed if open and not full.
- Allow cancellation after start, as proposed in the team plan.
- List order is unspecified in this draft; clients/tests must not rely on it.
- Invalid or nonpositive path IDs receive 404; GET rejects zero explicitly.

Proposed booking error codes for confirmation: `BAD_REQUEST`, `EVENT_NOT_FOUND`,
`PARTICIPANT_NOT_FOUND`, `DUPLICATE_REGISTRATION`, `EVENT_FULL`, `EVENT_STARTED`,
and `REGISTRATION_NOT_FOUND`. Reuse `ApiError` and the existing shared handlers.
Do not introduce a separate error response format.

Confirm with Jordan how to provide the proposed POST `Location` header: the team
plan asks for one, but the assignment does not require a single-registration GET
endpoint. Do not add a ninth operation to resolve this without discussion.

## Repository interface to confirm with Darren

| Function | Expected result |
| --- | --- |
| `get_event(event_id)` | Event dictionary, or `None` if absent |
| `get_participant(participant_id)` | Participant dictionary, or `None` |
| `find_registration(event_id, participant_id)` | Registration dictionary, or `None` |
| `count_registrations(event_id)` | Integer count for that event |
| `create_registration(event_id, participant_id)` | Newly created registration dictionary |
| `delete_registration(event_id, registration_id)` | True if a matching row was deleted, otherwise False |
| `list_registrations_with_names(event_id)` | List of registration dictionaries including participant names |

For the listing milestone, the repository returns JSON-ready camelCase records
with UTC string timestamps, consistent with the team plan's repository translation
rule. It filters by event ID and joins participant names. Confirm datetime and
field representations before implementing booking's time comparisons.

`create_registration_blueprint(repository)` accepts a module or object exposing
the repository functions. This lets isolated tests supply controlled responses
without importing an unfinished database module or contacting MySQL.

Once the real repository exists, Precious can wire it in `create_app()`:

```python
from app import repository
from app.routes.registrations import create_registration_blueprint

app.register_blueprint(create_registration_blueprint(repository))
```

The current production application factory is unchanged. The new endpoint is
registered only in the isolated tests until this handoff is complete. There is
no in-memory production fallback.

## Test checklist

| Case | Expected behavior | Status/test |
| --- | --- | --- |
| List populated event | 200, registration records include names | `test_list_registrations_includes_participant_names` |
| List empty event | 200, empty data array | `test_list_registrations_returns_empty_list` |
| List missing event | 404 standard error; do not query registrations | `test_list_registrations_rejects_missing_event` |
| Invalid event path ID | 404; no repository calls | `test_list_registrations_rejects_invalid_event_id` (parameterized) |
| List different events sequentially | Each request uses its own event ID | `test_list_registrations_keeps_events_separate` |
| Repository failure | Generic 500 without internal details | `test_list_registrations_hides_repository_errors` |
| Valid booking | 201, server timestamp, one additional row | Planned unit + integration |
| Bad participant ID/body | 400, no insertion | Planned parameterized unit |
| Malformed JSON/wrong media type | 400/415 shared JSON error | Planned unit |
| Missing event/participant | 404, no insertion | Planned unit + integration |
| Duplicate booking | 409, count unchanged | Planned unit + integration |
| Count capacity minus one / at capacity | Final place succeeds / next fails | Planned unit + integration |
| Before / exactly at / after start | Success / rejection / rejection (boundary proposed) | Planned unit using controlled time |
| Successful cancellation | 204, row removed, one place available | Planned unit + integration |
| Missing or wrong-event registration | 404, no unrelated row deleted | Planned unit + integration |
| Repeated cancellation | 404, no extra capacity | Planned unit + integration |
| Rebook after cancel | Success if open and space remains | Planned unit + integration |
| Capacity-2 walkthrough | Two book, third fails, cancel, third succeeds | Planned unit + integration |
| Cancellation after start | Allowed under team-plan assumption | Planned unit + integration |

Integration tests must use Darren's separate, resettable test database fixture.
Unit tests must run without MySQL, credentials, or a deployed API.

## Local verification

Environment: macOS terminal. Working directory: repository root.
The virtual environment lives outside the repository because its parent directory
contains a colon, which Python does not allow in a virtual environment path.

```bash
source /Users/joseph/Documents/python-envs/rest-api-club/bin/activate
python -m pytest tests/unit/test_registration_routes.py -v
python -m pytest tests/unit -v
python -m black --check app/routes tests/unit/test_registration_routes.py
```

The shared `unit` pytest marker is not registered yet; Precious owns that setup.

## Report and remaining handoffs

- Jordan: incorporate endpoint/error decisions and requirement-to-test mapping.
- Darren: confirm repository return values and supply the integration fixture.
- Precious: connect the blueprint, validators and shared unit-test fixtures.
- Anna: supply deployed base URL and suitable demo data with the team.
- Joseph: record actual test evidence, write cancellation explanation, prepare
  demo script, review database work, and perform the fresh-clone walkthrough.

Confidence-building test already included: sequential listing of two different
events proves the route passes the current request's event ID on every call;
no previous selection is retained in a server session. This does not establish
SQL filtering or persistence; the real database integration tests must do that.

No discovered defect is claimed in this initial milestone. Record real failures
and fixes as they occur. Use October 17 for the fresh-clone walkthrough, following
the team plan's timeline (the role card separately mentions October 16).
