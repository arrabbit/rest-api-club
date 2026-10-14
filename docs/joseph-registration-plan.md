# Joseph: registration contract and implementation plan

Owner: Joseph (GitHub: JD-d3v; branch: JD)
Drafted: October 14, 2026

Status: code and tests now follow Jordan's docs/api-contract.md (error codes,
check order, Location header, snake_case repository rows).

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
- [x] Match docs/api-contract.md: VALIDATION_ERROR, specific 404s, Location header.
- [ ] Paste the registration section below into docs/api-contract.md.
- [ ] Perform the fresh-clone README walkthrough (Oct 17). Blocked: everyone.

Events, participant management, SQL implementation, and deployment configuration
remain with their respective owners. Concurrency control is outside assignment
scope; demonstrate sequential requests.

## Registration routes in detail (copy into docs/api-contract.md)

### Registration

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Server-assigned |
| `eventId` | integer | From the path |
| `participantId` | integer | From the request body |
| `participantName` | string | Joined from participants |
| `registeredAt` | string | ISO 8601 UTC with `Z`, set by the server |

```json
{
  "id": 7,
  "eventId": 4,
  "participantId": 3,
  "participantName": "Maya Okafor",
  "registeredAt": "2026-10-14T18:00:00Z"
}
```

### POST /api/v1/events/{eventId}/registrations: register a participant

- **Request body:** exactly `{"participantId": <positive integer>}`. Any other field is a 400. JSON `true`, `"3"`, `1.0` and `null` are rejected.
- **Success:** `201`, body is the registration, header `Location: /api/v1/events/{eventId}/registrations/{id}` (the URL used to cancel it).
- **Check order:** body (400), event (404), participant (404), duplicate (409), started (409), full (409).
- **Rules:**
  - Registration closes exactly at `startTime` (now >= startTime gives 409).
  - Full means `count_registrations(eventId) >= capacity`.
- **Errors:** `400 VALIDATION_ERROR`, `404 EVENT_NOT_FOUND`, `404 PARTICIPANT_NOT_FOUND`, `409 DUPLICATE_REGISTRATION`, `409 EVENT_STARTED`, `409 EVENT_FULL`.

Request: `{"participantId": 3}`. Response `201`: the registration sample above.

Error example, `409`:
```json
{ "error": { "code": "EVENT_FULL", "message": "Event 4 has no spots left.",
  "details": { "eventId": 4, "capacity": 2 } } }
```

Error example, `400`:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Request body is invalid.",
  "details": { "errors": [
    { "field": "participantID", "reason": "unknown field" },
    { "field": "participantId", "reason": "must be a positive integer" } ] } } }
```

Flow: `get_json(silent=True)`, validate body, parse event ID, `get_event`, `get_participant`, `find_registration`, compare now with `start_time`, `count_registrations`, `create_registration`, return 201.

### GET /api/v1/events/{eventId}/registrations: list registrations

- **Success:** `200 {"data": [registration, ...]}` including `participantName`. An event with no registrations returns `{"data": []}`.
- **Errors:** `404 EVENT_NOT_FOUND`.

Flow: parse event ID, `get_event` (404), `list_registrations_with_names` (SQL JOIN on participants), serialize each.

### DELETE /api/v1/events/{eventId}/registrations/{registrationId}: cancel

- **Success:** `204`, empty body. The row is deleted, which frees one place.
- **Rules:**
  - Places are always `capacity - COUNT(registrations)`, never a stored counter. A second cancel finds no row and returns 404, so it cannot free a place twice.
  - The registration must belong to the event in the path.
  - Cancelling after the event starts is allowed.
- **Errors:** `404 EVENT_NOT_FOUND`, `404 REGISTRATION_NOT_FOUND` (missing, already cancelled, or belongs to another event).

Flow: parse event ID, `get_event` (404), parse registration ID, `delete_registration(event_id, registration_id)` returns False (404), return 204.

### Repository rows used by the registration routes (for Darren)

| Function | Returns |
| --- | --- |
| `get_event(event_id)` | row with `start_time` (naive-UTC or aware `datetime`) and `capacity`, or `None` |
| `get_participant(participant_id)` | row with `name`, or `None` |
| `find_registration(event_id, participant_id)` | row or `None` |
| `count_registrations(event_id)` | int |
| `create_registration(event_id, participant_id)` | row with `id`, `event_id`, `participant_id`, `registered_at` |
| `delete_registration(event_id, registration_id)` | `True` if a row matching both IDs was deleted |
| `list_registrations_with_names(event_id)` | rows as above plus `participant_name` |

Registration unit tests: `tests/unit/test_registration_routes.py` (marker `unit`, fake repository).

## Test checklist

All rules live in `app/routes/registrations.py`. `parse_participant_id`
validates the body, `require_event` parses the path ID and gives the 404,
`check_registration_allowed` applies the rules in contract order, and
`registration_to_json` turns snake_case rows into camelCase with `Z` times.

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
| Bad path IDs (`abc`, `0`, `-1`, `1.5`) | 404 `EVENT_NOT_FOUND` / `REGISTRATION_NOT_FOUND` | `test_invalid_path_ids_return_specific_404` |
| Valid booking | 201, row, `Location` header | `test_book_creates_registration_with_location` |
| Bad body (12 cases) | 400 `VALIDATION_ERROR` listing each problem, no row | `test_book_rejects_invalid_body` |
| Malformed JSON / not JSON / no body | 400 `VALIDATION_ERROR` (`field: body`) | `test_book_rejects_malformed_or_non_json` |
| Missing event or participant | 404, no row | `test_book_missing_event_or_participant_returns_404` |
| Duplicate booking | 409, count unchanged | `test_book_duplicate_returns_409` |
| Full event | 409 `EVENT_FULL` | `test_book_full_event_returns_409` |
| 1 s before / at / after start | 201 / 409 / 409 | `test_book_closes_at_start_time` |
| Aware (non-UTC) start time | Same boundary | `test_book_reads_timezone_aware_start_time` |
| Several rules broken at once | Contract order: 400, 404, 409 | `test_book_follows_contract_check_order` |
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
| 2026-10-14 | `test_book_rejects_invalid_body[None]` | The test meant to send the JSON literal `null`, but Flask's test client treats `json=None` as "no body", so the request had no content type and got 415 instead of the 400 being tested (before the contract moved body errors to 400). The `null` case was silently untested. | Encode the body with `json.dumps` and set `application/json` explicitly. This is a defect in a test, not in the route. |

## Local verification results (2026-10-14)

- `python -m pytest tests/unit -q`: 50 passed.
- Branch coverage of `app/routes/registrations.py`: 100%.
- `scripts/demo_deployed.sh` against a local server using the fake repository:
  all 5 steps returned the expected status; a second run also passed, and a
  missing event makes it stop with FAILED.

