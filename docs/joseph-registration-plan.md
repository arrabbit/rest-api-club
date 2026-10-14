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

All rules live in `app/routes/registrations.py`: `parse_participant_id`
validates the body (swap for Precious's `validation.py` once it exists),
`require_event` gives the standard 404, and `check_registration_allowed`
applies the rules in order (event, participant, duplicate, started, full).
Start times may be ISO strings with an offset or MySQL datetimes without one
(treated as UTC, matching the connection's `time_zone="+00:00"`).

Unit tests in `tests/unit/test_registration_routes.py` call the real routes
through Flask's test client. `FakeRepository` is an in-memory class with the
agreed repository signatures, and `build_client(repo, now=...)` fixes the
clock, so start-time tests never depend on the real date.

| Case | Expected behavior | Unit test |
| --- | --- | --- |
| List an event | 200 with only that event's rows and names | `test_list_returns_only_that_events_registrations_with_names` |
| List empty event | 200, `{"data": []}` | `test_list_empty_event_returns_empty_data` |
| List missing event | 404 standard error | `test_list_missing_event_returns_404` |
| Repository failure | Generic 500, no internal details | `test_repository_failure_returns_generic_500` |
| Non-integer path IDs | JSON 404 | `test_non_integer_path_ids_return_json_404` |
| Valid booking | 201, one more row | `test_book_creates_registration` |
| Bad body (11 cases) | 400, no row | `test_book_rejects_invalid_body` |
| Malformed JSON / not JSON | 400 / 415 JSON error | `test_book_rejects_malformed_or_non_json` |
| Missing event or participant | 404, no row | `test_book_missing_event_or_participant_returns_404` |
| Duplicate booking | 409, count unchanged | `test_book_duplicate_returns_409` |
| Full event | 409 `EVENT_FULL` | `test_book_full_event_returns_409` |
| 1 s before / at / after start | 201 / 409 / 409 | `test_book_closes_at_start_time` |
| Offset string and MySQL start times | Same boundary | `test_book_reads_offset_and_mysql_start_times` |
| Two rules broken at once | Earlier rule's code | `test_book_reports_earlier_rule_when_two_fail` |
| Cancel | 204, row removed | `test_cancel_deletes_registration` |
| Repeated cancel | 404, no extra place | `test_cancel_twice_does_not_free_extra_place` |
| Other event's registration | 404, row kept | `test_cancel_registration_of_other_event_returns_404` |
| Cancel under missing event | 404 `EVENT_NOT_FOUND` | `test_cancel_under_missing_event_returns_404` |
| Cancel after start | 204 (assumption) | `test_cancel_allowed_after_event_starts` |
| Capacity-2 walkthrough | Two book, third fails, cancel, third books | `test_capacity_two_walkthrough` |
| Rebook after cancel | 201, new registration | `test_rebook_after_cancel` |

Integration versions (against MySQL) of duplicate, full, after-start, double
cancel, rebook and the walkthrough are still planned; they need Darren's
separate, resettable test database fixture.

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
Tests: `test_cancel_twice_does_not_free_extra_place`,
`test_cancel_registration_of_other_event_returns_404`, `test_capacity_two_walkthrough`.

## Defect log

| Date | Found by | Defect | Fix |
| --- | --- | --- | --- |
| 2026-10-14 | `test_book_rejects_invalid_body[None]` | The test meant to send the JSON literal `null`, but Flask's test client treats `json=None` as "no body", so the request had no content type and correctly got 415 instead of the 400 being tested. The `null` case was silently untested. | Encode the body with `json.dumps` and set `application/json` explicitly. This is a defect in a test, not in the route. |

## Local verification results (2026-10-14)

- `python -m pytest tests/unit -q`: 47 passed (after simplification).
- Branch coverage of `app/routes/registrations.py`: 100%.
- `scripts/demo_deployed.sh` against a local server using the fake repository:
  all 5 steps returned the expected status; a second run also passed, and a
  missing event makes it stop with FAILED.

