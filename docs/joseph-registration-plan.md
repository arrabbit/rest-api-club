# Joseph: registration contract and implementation plan

Owner: Joseph (GitHub: JD-d3v; branch: JD)
Drafted: October 14, 2026

Status: proposed contract based on Assignment 1 and the team plan. This is
Joseph's contribution for Jordan to incorporate into the shared API contract,
not evidence that the team has approved every detail below.

## Scope and progress

- [x] Draft the three registration operations and test checklist.
- [x] Implement registration listing with isolated route tests.
- [x] Implement independent resource, duplicate, capacity, and start-time checks.
- [x] Implement booking and its unit tests (stateful fake repository, fixed clock).
- [x] Implement cancellation and its unit tests.
- [x] Capacity-2 walkthrough and rebook scenarios as unit tests.
- [x] Write the demo script (`scripts/demo_deployed.sh`); verified locally only.
- [x] Draft report notes: cancellation approach and defect log (below).
- [ ] Connect shared validation, repository functions, and application factory.
      Blocked: Precious (`validation.py`, `create_app()`), Darren (`repository.py`).
- [ ] Run booking integration tests against the separate MySQL test database.
      Blocked: Darren's schema, seed, and integration fixture.
- [ ] Run the demo script against the deployed API. Blocked: Anna's VM + seed data.
- [ ] Decide the POST `Location` header with Jordan (open question below).
- [ ] Perform the fresh-clone README walkthrough (Oct 17). Blocked: everyone.

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

Independent booking-rule checks are now implemented in Joseph's registration
module. They take ordinary booleans, integers, and timezone-aware datetimes;
they make no database calls and require no Flask application/request context.
The module still imports Flask for its existing route definitions.

- `get_registration_rejection(...)` checks existence and duplicates. Its return
  strings are internal reasons, not committed public API error codes. Routes
  will translate them into the agreed `ApiError` responses later.
- `has_available_capacity(...)` compares a validated capacity with the current
  registration count. It assumes a positive integer capacity and nonnegative
  integer count; shared validation and repository code provide those values.
- `has_event_started(...)` takes both times explicitly, so tests do not depend
  on the actual date or system timezone. It refuses timezone-naive datetime
  objects, including two naive objects that Python would otherwise compare.

Existence/duplicate precedence remains the proposed order in this draft. The
exact-start policy has its own clearly named test so it can be changed without
rewriting tests for before/after start. Equivalent instants with different UTC
offsets are tested as well. String parsing and external field names are left to
the future route/validation connection.

The POST and DELETE routes call these helpers. Unit route tests use
`FakeRegistrationRepository` (in the test file), an in-memory class with the
agreed repository signatures, and an injected clock (`create_registration_blueprint(
repository, clock)`) so start-time tests never depend on the real date.
`parse_participant_id` is a local validator; swap it for Precious's
`validation.py` function once that exists. `to_utc_datetime` accepts an ISO
string with a timezone or a MySQL datetime (naive is treated as UTC, matching
the connection's `time_zone="+00:00"`), so either repository choice works.

| Independent rule | Executable tests |
| --- | --- |
| Event/participant existence and duplicates | `test_registration_rejection_checks_existence_and_duplicates` |
| Empty event, final place, full/overfull event | `test_available_capacity_checks_last_place_and_full_event` |
| Just before/after start | `test_event_start_checks_before_and_after_boundary` |
| Exact-start provisional policy | `test_event_start_rejects_exact_start_under_proposed_policy` |
| Equivalent instants in different timezones | `test_event_start_compares_instants_across_timezones` |
| Reject naive datetimes | `test_event_start_rejects_datetimes_without_timezone` |

The endpoint checklist below remains separate: helper checks alone do not prove
that an HTTP request is validated, a database write occurs, or a write is avoided.

| Case | Expected behavior | Status/test |
| --- | --- | --- |
| List populated event | 200, registration records include names | `test_list_registrations_includes_participant_names` |
| List empty event | 200, empty data array | `test_list_registrations_returns_empty_list` |
| List missing event | 404 standard error; do not query registrations | `test_list_registrations_rejects_missing_event` |
| Invalid event path ID | 404; no repository calls | `test_list_registrations_rejects_invalid_event_id` (parameterized) |
| List different events sequentially | Each request uses its own event ID | `test_list_registrations_keeps_events_separate` |
| Repository failure | Generic 500 without internal details | `test_list_registrations_hides_repository_errors` |
| Two rules broken at once | Earlier rule's code wins | `test_register_reports_rules_in_agreed_order` |
| Valid booking | 201, server timestamp, one additional row | `test_register_creates_registration`; integration planned |
| Bad participant ID/body | 400, no insertion | `test_register_rejects_invalid_body` (13 cases) |
| Malformed JSON/wrong media type | 400/415 shared JSON error | `test_register_rejects_malformed_json`, `test_register_rejects_non_json_content_type` |
| Missing event/participant | 404, no insertion | `test_register_rejects_missing_records`, `test_register_rejects_invalid_event_path`; integration planned |
| Duplicate booking | 409, count unchanged | `test_register_rejects_duplicate`; integration planned |
| Count capacity minus one / at capacity | Final place succeeds / next fails | `test_register_rejects_full_event`; integration planned |
| Before / exactly at / after start | Success / rejection / rejection (boundary proposed) | `test_register_checks_start_time_boundary`, `test_register_accepts_naive_mysql_start_time` |
| Successful cancellation | 204, row removed, one place available | `test_cancel_removes_registration`; integration planned |
| Missing or wrong-event registration | 404, no unrelated row deleted | `test_cancel_rejects_registration_from_other_event`, `test_cancel_rejects_missing_event`, `test_cancel_rejects_invalid_or_unknown_registration`; integration planned |
| Repeated cancellation | 404, no extra capacity | `test_cancel_twice_does_not_release_extra_place`; integration planned |
| Rebook after cancel | Success if open and space remains | `test_rebook_after_cancel_creates_new_registration`; integration planned |
| Capacity-2 walkthrough | Two book, third fails, cancel, third succeeds | `test_capacity_two_walkthrough`; integration planned |
| Cancellation after start | Allowed under team-plan assumption | `test_cancel_allowed_after_event_starts`; integration planned |

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

## Report notes (draft for Precious)

**Cancellation approach.** `DELETE /api/v1/events/{eventId}/registrations/{registrationId}`
deletes the registration row and returns 204. Places left are always computed as
`capacity - COUNT(registrations)`; nothing is stored as a counter. A second
cancel finds no row and returns 404 `REGISTRATION_NOT_FOUND`, so it cannot
release a place twice. The registration must belong to the event in the path,
so one event's URL cannot cancel another event's booking. Cancelling after the
event starts is allowed (assumption: the spec only blocks registering after start).
Tests: `test_cancel_twice_does_not_release_extra_place`,
`test_cancel_rejects_registration_from_other_event`, `test_capacity_two_walkthrough`.

## Defect log

| Date | Found by | Defect | Fix |
| --- | --- | --- | --- |
| 2026-10-14 | `test_register_rejects_invalid_body[None]` | The test meant to send the JSON literal `null`, but Flask's test client treats `json=None` as "no body", so the request had no content type and correctly got 415 instead of the 400 being tested. The `null` case was silently untested. | Encode the body with `json.dumps` and set `application/json` explicitly. This is a defect in a test, not in the route. |

## Local verification results (2026-10-14)

- `python -m pytest tests/unit -q`: 94 passed.
- Branch coverage of `app/routes/registrations.py`: 100%.
- `scripts/demo_deployed.sh` against a local server using the fake repository:
  all 7 steps returned the expected status; a second run also passed.

