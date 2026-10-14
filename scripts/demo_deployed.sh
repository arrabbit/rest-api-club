#!/usr/bin/env bash
# demo_deployed.sh
# Purpose: Shows a successful booking, a rejected booking, retrieval and
#          cancellation on a running API, stopping if any status is wrong.
#          It cancels its own booking, so it can be rerun.
# Authors: Joseph (JD-d3v)
# Date created: 2026-10-14
#
# Environment: bash, curl and python3. Working directory: repository root.
#   BASE_URL=http://<VM-IP>:5000 EVENT_ID=1 PARTICIPANT_ID=1 bash scripts/demo_deployed.sh
# EVENT_ID must be a future event with a free place; PARTICIPANT_ID must not
# already be registered for it.

set -euo pipefail

URL="${BASE_URL:-http://localhost:5000}/api/v1/events/${EVENT_ID:-1}/registrations"
BOOKING="{\"participantId\": ${PARTICIPANT_ID:-1}}"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

# step TITLE EXPECTED_STATUS CURL_ARGS... : print the response, fail on a wrong status.
step() {
    local title="$1" expected="$2"
    shift 2
    echo "== $title"
    echo "\$ curl $*"
    local status
    status="$(curl -sS -o "$BODY" -w '%{http_code}' "$@")"
    echo "HTTP $status"
    cat "$BODY"
    echo
    [[ "$status" == "$expected" ]] || { echo "FAILED: expected $expected" >&2; exit 1; }
}

JSON=(-H 'Content-Type: application/json' -d "$BOOKING")
step "1. Successful booking" 201 -X POST "$URL" "${JSON[@]}"
REGISTRATION_ID="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])' < "$BODY")"
step "2. Rejected booking (same participant again)" 409 -X POST "$URL" "${JSON[@]}"
step "3. Retrieve registrations" 200 "$URL"
step "4. Cancel the booking" 204 -X DELETE "$URL/$REGISTRATION_ID"
step "5. Retrieve registrations after cancelling" 200 "$URL"
echo "Demo finished: every step returned the expected status."
