#!/usr/bin/env bash

set -uo pipefail

readonly call_timeout=12
failures=0

call_set_bool() {
    local description="$1"
    local service="$2"
    local value="$3"
    local output

    printf '[pika-stop] %s\n' "${description}"
    if ! output=$(timeout "${call_timeout}" ros2 service call "${service}" \
        std_srvs/srv/SetBool "{data: ${value}}" 2>&1); then
        printf '%s\n' "${output}" >&2
        failures=$((failures + 1))
        return
    fi
    printf '%s\n' "${output}"
    if ! grep -q 'success=True' <<<"${output}"; then
        failures=$((failures + 1))
    fi
}

# Stop acceptance of the direct IK topics, then disable both motors.  There is
# no joint-command guard or command watchdog in the active teleop path.
call_set_bool 'Closing left official control gate' /left_arm/control_enable false
call_set_bool 'Closing right official control gate' /right_arm/control_enable false
call_set_bool 'Disabling left Piper' /left_arm/enable_agx_arm false
call_set_bool 'Disabling right Piper' /right_arm/enable_agx_arm false

if ((failures > 0)); then
    printf '[pika-stop] Completed with %d failure(s). Use the physical emergency stop if an arm remains enabled.\n' \
        "${failures}" >&2
    exit 1
fi

printf '%s\n' \
    '[pika-stop] Both Pipers are disabled and both control gates are closed.' \
    '[pika-stop] Stop the teleop container with Ctrl+C now.'
