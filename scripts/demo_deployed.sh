#!/usr/bin/env bash
# demo_deployed.sh
# Purpose: Demonstrates the registration endpoints against a running API:
#          retrieval, a successful booking, a rejected (duplicate) booking,
#          cancellation, a repeated cancellation, and retrieval again.
#          Each step checks the HTTP status and stops on a mismatch.
#          The booking it creates is cancelled again, so it can be rerun.
# Authors: Joseph (JD-d3v)
# Date created: 2026-10-14
#
# Environment: any machine with bash, curl and python3.
# Working directory: repository root.
#   bash scripts/demo_deployed.sh                          # local, port 5000
#   BASE_URL=http://<VM-IP>:5000 bash scripts/demo_deployed.sh
# Optional: EVENT_ID and PARTICIPANT_ID (defaults 1 and 1) must name a seeded,
# future event with a free place and a participant not yet registered for it.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"
EVENT_ID="${EVENT_ID:-1}"
PARTICIPANT_ID="${PARTICIPANT_ID:-1}"
REGISTRATIONS_URL="$BASE_URL/api/v1/events/$EVENT_ID/registrations"
BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

# request STEP EXPECTED_STATUS METHOD URL [JSON_BODY]
# Prints the request and response; exits 1 if the status is not EXPECTED_STATUS.
request() {
    local step="$1" expected="$2" method="$3" url="$4" body="${5:-}"
    local curl_args=(-sS -o "$BODY_FILE" -w '%{http_code}' -X "$method" "$url")
    if [[ -n "$body" ]]; then
        curl_args+=(-H 'Content-Type: application/json' -d "$body")
    fi

    echo "== $step"
    echo "\$ curl -X $method $url ${body:+-d '$body'}"
    local status
    status="$(curl "${curl_args[@]}")"
    echo "HTTP $status"
    cat "$BODY_FILE"
    echo
    if [[ "$status" != "$expected" ]]; then
        echo "FAILED: expected HTTP $expected, got $status" >&2
        exit 1
    fi
    echo
}

request "1. Retrieve registrations before booking" 200 GET "$REGISTRATIONS_URL"

request "2. Successful booking" 201 POST "$REGISTRATIONS_URL" \
    "{\"participantId\": $PARTICIPANT_ID}"
REGISTRATION_ID="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])' < "$BODY_FILE")"

request "3. Rejected booking (same participant again)" 409 POST "$REGISTRATIONS_URL" \
    "{\"participantId\": $PARTICIPANT_ID}"

request "4. Retrieve registrations including the new booking" 200 GET "$REGISTRATIONS_URL"

request "5. Cancel the booking" 204 DELETE "$REGISTRATIONS_URL/$REGISTRATION_ID"

request "6. Repeated cancellation is rejected" 404 DELETE "$REGISTRATIONS_URL/$REGISTRATION_ID"

request "7. Retrieve registrations after cancellation" 200 GET "$REGISTRATIONS_URL"

echo "Demo finished: all steps returned the expected status."
