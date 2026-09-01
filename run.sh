#!/usr/bin/env bash

set -Eeuo pipefail

readonly call_timeout=20
startup_complete=false

require_success() {
    local description="$1"
    shift
    local output

    printf '[pika-start] %s\n' "${description}"
    if ! output=$(timeout "${call_timeout}" "$@" 2>&1); then
        printf '%s\n' "${output}" >&2
        return 1
    fi
    printf '%s\n' "${output}"
    grep -q 'success=True' <<<"${output}"
}

set_arm_enable() {
    local hand="$1"
    local value="$2"
    require_success "Setting ${hand} Piper enable=${value}" \
        ros2 service call "/${hand}_arm/enable_agx_arm" \
        std_srvs/srv/SetBool "{data: ${value}}"
}

rollback() {
    local exit_code=$?
    trap - ERR INT TERM
    set +e
    if [[ "${startup_complete}" != true ]]; then
        printf '\n[pika-start] Startup failed; disabling both Pipers.\n' >&2
        timeout 8 ros2 service call /left_arm/control_enable \
            std_srvs/srv/SetBool '{data: false}' >/dev/null 2>&1 || true
        timeout 8 ros2 service call /right_arm/control_enable \
            std_srvs/srv/SetBool '{data: false}' >/dev/null 2>&1 || true
        timeout 8 ros2 service call /left_arm/enable_agx_arm \
            std_srvs/srv/SetBool '{data: false}' >/dev/null 2>&1 || true
        timeout 8 ros2 service call /right_arm/enable_agx_arm \
            std_srvs/srv/SetBool '{data: false}' >/dev/null 2>&1 || true
    fi
    exit "${exit_code}"
}

trap rollback ERR INT TERM

printf '%s\n' \
    '[pika-start] Official direct teleop path: IK -> /control/joint_states -> Piper.' \
    '[pika-start] This script does not establish teleop zero poses.'

# The official launch auto-enables both arms.  Calling the official services
# here makes startup completion explicit before teleoperation is toggled on.
set_arm_enable left true
set_arm_enable right true

startup_complete=true
trap - ERR INT TERM
printf '%s\n' \
    '[pika-start] Both Pipers are enabled.' \
    '[pika-start] Double-click the RIGHT Sense gripper to establish both zero poses and start teleoperation.' \
    '[pika-start] Run ./stop.sh before stopping the teleop container.'
