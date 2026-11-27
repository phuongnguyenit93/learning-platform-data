# Designing Scripts with Error Checking and Clear Completion States

An automated deployment script is part of the release system. It may fetch artifacts, verify checksums, prepare the environment, update workloads, wait for the application to become ready, run smoke tests, and record results. A script that simply runs commands sequentially and exits with code 0 does not guarantee a successful deployment: a command may only submit an asynchronous request, the application may not be ready yet, or post-deployment verification may never have run.

A reliable script must answer three questions: **which step was reached, where a failure occurred, and what the final state of the deployment is**. It must validate inputs, check command exit codes, enforce timeouts, handle conditional retries, clean up resources, verify actual state, and report success only when every required condition has been met.

This lesson presents how to design scripts with explicit error control and clear completion states in a CI/CD context. The examples use Bash for illustration, but the same principles apply to PowerShell, Python, Node.js, or specialized deployment tools.

## 1. Defining Success for a Deployment

Before writing a script, define what completion means. A command like deployctl apply returning success may only mean the request was accepted. It does not necessarily prove the new workload started, passed readiness checks, or is serving traffic normally.

A deployment typically consists of these steps:

1. Validate parameters, permissions, and target environment.
2. Run pre-deployment checks (preflight).
3. Fetch the artifact at the exact version.
4. Verify digest, signature, or metadata per policy.
5. Record the currently running version to support rollback.
6. Apply the deployment change.
7. Wait for the system to reach readiness.
8. Run smoke tests or post-deployment acceptance checks.
9. Record the new release as the active version.
10. Store the run's result, logs, and metadata.

Only when all required steps complete may the script record the **SUCCEEDED** status. If the deployment command returned 0 but readiness checks failed, the deployment has not succeeded.

~~~mermaid
flowchart TD
    A["Receive deployment request"] --> B["Validate inputs and permissions"]
    B --> C["Preflight: environment, lock, quota"]
    C --> D["Fetch and verify artifact"]
    D --> E["Record current version"]
    E --> F["Apply deployment"]
    F --> G["Wait for readiness within timeout"]
    G --> H{"Application ready?"}
    H -- "No" --> I["Handle failure / rollback if safe"]
    H -- "Yes" --> J["Smoke tests and version verification"]
    J --> K{"Checks passed?"}
    K -- "No" --> I
    K -- "Yes" --> L["Record successful release"]
    L --> M["Save SUCCEEDED status"]
~~~

The definition of success must align with the system's requirements. A web service may require readiness, HTTP smoke tests, and artifact digest verification. A data processing job may require verifying record counts or checkpoints. Do not apply a single generic condition to every workload type.

## 2. Designing Clear Deployment States

A script should manage state as a process with well-defined stages. This helps logs, dashboards, and orchestrators understand where a run stands.

| State | Meaning | Transition Condition |
|---|---|---|
| **PENDING** | Request received but not yet started | Picked up by a runner |
| **RUNNING** | Executing deployment steps | Continues, fails, or is canceled |
| **VALIDATING** | Checking inputs and environment conditions | Preflight passes or fails |
| **DEPLOYING** | Started modifying workload | Apply completes or fails |
| **VERIFYING** | Waiting for readiness and running smoke tests | Verification passes or fails |
| **SUCCEEDED** | All required conditions met | Terminal state |
| **FAILED** | Run failed; rollback not confirmed successful | Terminal state or awaiting handling |
| **ROLLED_BACK** | Previous version restored and rollback verified | Terminal state |
| **ROLLBACK_FAILED** | Rollback did not complete or could not be verified | Requires intervention |
| **CANCELLED** | Run canceled per policy | Terminal state or awaiting verification |

Not every project needs every state. What matters is that states have consistent meaning and success is never recorded prematurely.

### 2.1. Distinguishing Exit Code from Deployment Status

The exit code is the outcome of the script process. Deployment status describes the business outcome of the deployment.

For example:

- Exit code 0 and status **SUCCEEDED**: deployment, readiness, and smoke tests all passed.
- Non-zero exit code and status **FAILED**: a required step failed.
- Non-zero exit code and status **ROLLED_BACK**: candidate deployment failed, but the previous version was restored and verified.
- Non-zero exit code and status **ROLLBACK_FAILED**: both deployment and recovery encountered issues.

A run can return a non-zero exit code while leaving the final environment state stable because rollback succeeded. Both pieces of information must be preserved so the pipeline knows the initial operation failed and the environment was recovered.

### 2.2. Recording Final Status Only After Verification

Do not record **SUCCEEDED** immediately after the apply command. Wait for readiness, run smoke tests, and verify the running release ID or digest. If the deployment pipeline is asynchronous, poll status from the platform until a terminal state or timeout is reached.

The **RUNNING** state should also never persist indefinitely if a runner disconnects. The orchestration system needs job-level timeouts and a mechanism to reconcile actual environment state.

## 3. Validating Inputs and Pre-Deployment Conditions

Validating inputs as early as possible reduces the risk of the script applying changes to the wrong environment or wrong artifact.

Parameters that typically require validation:

- Target environment, such as **staging** or **production**.
- Release ID or version.
- Artifact URI and expected digest.
- Namespace, cluster, region, or application name.
- Required configuration and secret references.
- Timeouts and retry limits.
- Permissions of the executing identity.
- Approval status if required by the environment.

Check required values, data types, formats, and allowlists. For example, the target environment should match an allowlist. Never concatenate strings from untrusted inputs into shell commands, never use **eval**, and always quote variables when passing them as arguments.

### 3.1. Preflight Before Modifying the Environment

Preflight is the set of checks run before the script begins affecting the system:

- Runner is authenticated with the right account or workload identity.
- Caller is authorized to deploy to the target environment.
- Target cluster, namespace, or API is reachable and ready.
- Artifact exists and is readable.
- Digest or signature is valid.
- Quotas and resources are sufficient for rollout.
- No conflicting deployment currently holds the lock.
- Environment configuration is valid and compatible with the artifact.
- A current version exists, or a fallback plan is ready if rollback is impossible.

Preflight does not guarantee every subsequent operation will succeed, but it catches invalid conditions early before mutating state.

### 3.2. Separating Read-Only Checks from Mutating Operations

Organize the script into two groups:

- **Read-only checks:** reading state, checking permissions, verifying artifacts, validating configuration and quotas.
- **Mutating operations:** updating deployments, shifting traffic, modifying configuration, or recording a new release.

Read-only checks can run first and are usually easier to retry. Mutating operations require locking, idempotency, and clear error handling plans.

## 4. Checking Errors and Command Exit Codes

Every external command can fail for many reasons: invalid arguments, missing permissions, network errors, timeouts, unavailable services, or errors from the application itself. The script must check the results of critical commands and preserve exit codes for diagnostics.

### 4.1. Exit Codes in the Shell

By standard Unix convention:

- **0:** command completed successfully.
- **Non-zero:** an error or special result occurred that must be interpreted per tool.

Specific exit codes depend on the program. Never assume every non-zero code represents the same type of failure. Read the documentation of the CLI in use and map important exit codes to pipeline states.

Example:

~~~bash
if deployctl preflight --environment "$TARGET_ENV"; then
  printf '%s\n' "Preflight passed"
else
  rc=$?
  printf 'Preflight failed, exit=%s\n' "$rc" >&2
  exit "$rc"
fi
~~~

The **if command; then ... else rc=$?; ... fi** structure preserves the command's actual exit code. Avoid the **if ! command; then rc=$?** pattern, because inside the `then` branch, **$?** holds the status of the negation operator and is usually 0 rather than the original error code.

### 4.2. Strict Mode in Bash

A Bash script typically starts with:

~~~bash
set -Eeuo pipefail
IFS=$'\n\t'
~~~

Meaning:

- **-e:** instructs the shell to exit when a command fails in contexts where the errexit rule applies.
- **-E:** allows the ERR trap to be inherited by functions and certain sub-contexts.
- **-u:** raises an error when referencing an unset variable.
- **pipefail:** makes a pipeline return the exit code of the failing command rather than only the last command's code.

Strict mode is helpful, but it does not replace explicit error checking. The behavior of **set -e** has exceptions inside **if**, **while**, **&&**, **||**, pipelines, and certain function/subshell contexts. Therefore, critical commands such as deploy, rollback, digest verification, and health checks should be checked explicitly with **if/else** or a wrapper that handles exit codes.

### 4.3. Avoiding Swallowing Errors

Patterns such as **command || true**, **2>/dev/null**, or discarding output can hide failures. Use them only when the error is known not to affect the goal and the reason is documented.

For example, deleting a temporary directory can be best-effort, but failing to verify an artifact cannot. A script should never turn every error into a warning just to keep the pipeline green.

### 4.4. Checking Both Pipelines and Command Substitution

With **pipefail**, a command like **download | sha256sum** can return an error if any stage in the pipeline fails. Without **pipefail**, the shell may report only the status of the final command and mask a download failure.

Command substitutions such as **VERSION=$(deployctl current-version)** must also be checked. If the inner command fails, the script must not continue with an empty string or an unsafe default value.

## 5. A Shared Helper for Checked Command Execution

A wrapper provides consistent logging and preserves exit codes:

~~~bash
run_checked() {
  local description="$1"
  shift

  log INFO "START: $description"

  if "$@"; then
    log INFO "PASS: $description"
    return 0
  else
    local rc=$?
    log ERROR "FAIL: $description (exit=$rc)"
    return "$rc"
  fi
}
~~~

Invocation:

~~~bash
if run_checked "verify artifact" artifactctl verify \
  --uri "$ARTIFACT_URI" \
  --sha256 "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Artifact verification failed"
fi
~~~

The function receives the command and arguments as separate elements. This avoids concatenating command strings and using **eval**, reducing command injection risks and quoting bugs. Never accept an arbitrary command string from a pull request and execute it on a runner with deployment privileges.

A good wrapper logs step name, timestamp, outcome, and exit code. Never write secrets, tokens, or full connection strings to logs.

## 6. Timeouts and Bounded Retries

A deployment command can hang indefinitely if a dependent service stops responding. Every step that may wait needs an appropriate timeout:

- API connection timeout.
- Artifact download timeout.
- Rollout wait timeout.
- Readiness check timeout.
- Smoke test timeout.
- Overall deployment job timeout.

A client-side timeout does not necessarily stop the server-side operation. For instance, the script may time out while the orchestration platform continues rolling out. On timeout, query actual state before issuing a new command or rollback.

### 6.1. Retrying Only Transient Errors

Retries are appropriate for errors likely to resolve on their own, such as network resets, rate limits, or certain transient service errors. Never retry validation failures, missing permissions, artifact digest mismatches, or invalid configuration.

A retry policy should define:

- Which error codes or error classes are retryable.
- Maximum number of attempts.
- Wait interval between attempts.
- Exponential backoff and jitter to avoid many jobs retrying simultaneously.
- Overall timeout.
- Immediate abort conditions for non-retryable errors.

Never retry indefinitely. Excessive retries increase load, mask incidents, and make response times unpredictable.

### 6.2. Retrying Mutating Operations Requires Idempotency

Repeating read-only status commands is generally safer than repeating resource creation or deployment commands. If a request reached the server but the response was lost, the client may not know whether the operation was applied.

For mutating operations, use an idempotency key or stable release ID if supported by the API. Before retrying, query the current state to determine whether the previous request already completed.

## 7. Idempotency and Coordinating Concurrent Deployments

An idempotent script can be re-run with the same inputs without producing invalid state or duplicate resources. This is essential when a runner is interrupted, a pipeline retries, or an operator re-runs manually.

Principles:

- Identify resources by stable names or release IDs.
- Check current state before creating or updating.
- Use declarative desired-state APIs whenever possible.
- Avoid unlocked additive operations, such as creating a new release record on every run.
- Attach idempotency keys to mutating requests.
- Record outcomes so subsequent runs can resume or verify.

Two pipelines can attempt to deploy the same service simultaneously. Without concurrency control, an older run might finish later and overwrite the newer version. Lock per application/environment or use the platform's serialization mechanism.

Example of an OS-level lock:

~~~bash
exec 9>"/var/lock/orders-production-deploy.lock"
if ! flock -n 9; then
  printf '%s\n' "Another deployment is running" >&2
  exit 75
fi
~~~

This example is only suitable when jobs share a filesystem/host supporting **flock**. For distributed runners, use concurrency groups, distributed locks, or the deployment system's built-in locking. Locks must have expiration or reclamation mechanisms to avoid deadlocks if a runner dies.

## 8. Cleanup and Signal Handling

A script may create temporary workspaces, download artifacts, generate metadata files, or launch child processes. These resources must be cleaned up on success, failure, or cancellation.

In Bash, **trap** allows running cleanup when the shell exits or receives signals:

~~~bash
WORK_DIR="$(mktemp -d)"

cleanup() {
  local rc=$?
  if [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]]; then
    if ! rm -rf -- "$WORK_DIR"; then
      printf '%s\n' "WARNING: cleanup failed" >&2
    fi
  fi
}

trap cleanup EXIT
~~~

Cleanup should:

- Delete temporary files and workspaces created by the job.
- Revoke or destroy temporary credentials if possible.
- Stop child processes and temporary containers.
- Release locks.
- Preserve required logs and reports.
- Avoid deleting artifacts or evidence needed for investigation.

Cleanup must not mask the primary error. If deployment fails, cleanup must still run while preserving the original exit code. With ephemeral runners, destroying the entire environment after the job can be more reliable than attempting to clean up individual resources.

### 8.1. Handling SIGTERM and Job Cancellation

The CI platform may send SIGTERM on timeout or when a user cancels the pipeline. The script should handle the signal gracefully: stop starting new operations, record **CANCELLED** or **INTERRUPTED** status, terminate child processes, and inspect the state of any in-progress deployment.

Do not automatically roll back on every cancellation. If mutating changes were partially applied, query environment state and follow recovery policy. Rollback itself is a mutating operation that must be verified.

## 9. Readiness, Health Checks, and Smoke Tests

After the deploy command completes, the script must verify that the application is genuinely ready.

| Check | Question | Timing |
|---|---|---|
| Process/container state | Are the process or containers running? | Immediately after apply |
| Readiness check | Is the application ready to receive traffic? | During rollout |
| Liveness check | Is the process alive and not hung? | After startup |
| Health endpoint | Are essential components functioning? | After readiness |
| Smoke test | Do minimal critical business flows work? | Post-deployment |
| Version/digest check | Does the running version match the released artifact? | Before marking success |

Readiness and liveness serve different purposes. A live process is not necessarily ready to serve requests. A readiness endpoint returning HTTP 200 is also insufficient if it fails to check critical dependencies or returns stubbed results.

Smoke tests should be short, stable, and validate the most critical paths: basic endpoints, authentication, required service connectivity, or a safe business operation. Do not run smoke tests with side effects such as creating real transactions in production unless dedicated test-data isolation exists.

### 9.1. Polling with Timeouts and Intervals

Instead of a fixed sleep that assumes the application is ready, poll the status:

1. Call the readiness endpoint or rollout API.
2. If passing, proceed.
3. If still progressing, wait a short interval and check again.
4. If encountering a transient error, apply bounded retries.
5. If the deadline expires or a terminal error occurs, mark failure and execute the handling policy.

Polling needs an overall timeout and must log attempt counts or elapsed wait time. Avoid overly aggressive polling that adds load to a struggling system.

## 10. Rollback and Post-Failure States

Rollback is part of deployment design, but it is not always safe or automatable.

Before making changes, the script should record the current version, artifact digest, related configuration, and recovery metadata. If the candidate fails after modifying the environment, rollback may proceed when:

- The previous version still exists and is verifiable.
- Configuration and schema remain compatible.
- The operation is reversible.
- Environment policy permits automatic rollback.
- The previous version can be verified healthy again.

Do not roll back blindly after an incompatible data migration or irreversible operation. In those cases, you may need to halt the rollout, preserve the current state, and request operator decision or perform a forward fix.

### 10.1. Distinguishing Final Outcomes

| Outcome | Meaning | Next Action |
|---|---|---|
| **SUCCEEDED** | Candidate deployed and verification passed | Finalize release record |
| **FAILED** | A step failed; previous state not restored | Investigate and decide remediation |
| **ROLLED_BACK** | Candidate failed, but previous version was verified | Record incident and root cause |
| **ROLLBACK_FAILED** | Could not restore or verify recovery | Urgent alert, operator intervention |
| **CANCELLED** | Run was canceled | Reconcile actual state before next run |

A successful rollback does not turn a candidate deployment into a success. It only indicates that the environment was restored to its prior state according to verified criteria.

## 11. Logs, Reports, and Machine-Readable Status

Logs must tell operators which step started, completed, and failed. Each line should include timestamp, level, release ID, environment, and step name. Avoid logging secrets or sensitive data.

Example:

~~~text
2026-11-18T09:00:00Z level=INFO release=rel-2026-11-18-01 env=staging step=preflight status=STARTED
2026-11-18T09:00:03Z level=INFO release=rel-2026-11-18-01 env=staging step=artifact-verify status=PASSED
2026-11-18T09:00:10Z level=INFO release=rel-2026-11-18-01 env=staging step=deploy status=STARTED
2026-11-18T09:01:12Z level=INFO release=rel-2026-11-18-01 env=staging step=readiness status=PASSED
2026-11-18T09:01:20Z level=INFO release=rel-2026-11-18-01 env=staging result=SUCCEEDED
~~~

In addition to logs, produce a machine-readable result for pipelines or observability systems. JSON example:

~~~json
{
  "release_id": "rel-2026-11-18-01",
  "environment": "staging",
  "status": "SUCCEEDED",
  "exit_code": 0,
  "artifact_digest": "sha256:...",
  "previous_release": "rel-2026-11-17-03",
  "started_at": "2026-11-18T09:00:00Z",
  "completed_at": "2026-11-18T09:01:20Z",
  "checks": {
    "artifact_verified": true,
    "readiness": true,
    "smoke_test": true,
    "running_version_verified": true
  }
}
~~~

This result must be written atomically: write to a temporary file and rename within the same filesystem so readers never see partial content. For JSON data, use a library or tool such as jq to escape values properly instead of concatenating strings. Store the result alongside pipeline run ID, commit SHA, and artifact digest.

## 12. Example Bash Script with Error Checking and Completion Status

The example below uses hypothetical CLIs **artifactctl**, **deployctl**, and **smoke-test** to illustrate structure. This is not a ready-to-run script without replacing the tools and policies with your project's platform specifics.

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

: "${TARGET_ENV:?TARGET_ENV is required}"
: "${RELEASE_ID:?RELEASE_ID is required}"
: "${ARTIFACT_URI:?ARTIFACT_URI is required}"
: "${EXPECTED_SHA256:?EXPECTED_SHA256 is required}"
: "${RESULT_FILE:?RESULT_FILE is required}"
: "${ROLLBACK_ALLOWED:?ROLLBACK_ALLOWED must come from trusted release policy}"

case "$TARGET_ENV" in
  staging|production) ;;
  *)
    printf 'Unsupported environment: %s\n' "$TARGET_ENV" >&2
    exit 2
    ;;
esac

case "$ROLLBACK_ALLOWED" in
  true|false) ;;
  *)
    printf '%s\n' "ROLLBACK_ALLOWED must be true or false" >&2
    exit 2
    ;;
esac

RESULT_DIR="$(dirname -- "$RESULT_FILE")"
mkdir -p -- "$RESULT_DIR"
WORK_DIR="$(mktemp -d)"
RESULT_STATUS="RUNNING"
DEPLOYMENT_STARTED="false"
PREVIOUS_RELEASE=""

log() {
  local level="$1"
  shift
  printf '%s level=%s %s\n' "$(date -u +%FT%TZ)" "$level" "$*" >&2
}

write_result() {
  local status="$1"
  local exit_code="$2"
  local result_tmp="${RESULT_FILE}.tmp.$$"

  jq -n \
    --arg status "$status" \
    --arg release "$RELEASE_ID" \
    --arg environment "$TARGET_ENV" \
    --arg digest "$EXPECTED_SHA256" \
    --argjson exit_code "$exit_code" \
    '{
      status: $status,
      release_id: $release,
      environment: $environment,
      artifact_digest: $digest,
      exit_code: $exit_code
    }' > "$result_tmp"

  mv -f -- "$result_tmp" "$RESULT_FILE"
}

cleanup() {
  if [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]]; then
    if ! rm -rf -- "$WORK_DIR"; then
      log WARN "Temporary workspace cleanup failed"
    fi
  fi
}

on_error() {
  local rc=$?
  local line="${BASH_LINENO[0]:-unknown}"
  log ERROR "Unhandled command failure exit=$rc line=$line"

  if [[ "$RESULT_STATUS" == "RUNNING" ]]; then
    RESULT_STATUS="FAILED"
    if ! write_result "$RESULT_STATUS" "$rc"; then
      log ERROR "Could not persist failure result"
    fi
  fi

  exit "$rc"
}

on_signal() {
  local signal="$1"
  local rc=130
  if [[ "$signal" == "SIGTERM" ]]; then
    rc=143
  fi

  log WARN "Received $signal; checking remote deployment state"
  if [[ "$DEPLOYMENT_STARTED" == "true" ]]; then
    if deployctl status --environment "$TARGET_ENV" --release "$RELEASE_ID"; then
      :
    else
      log WARN "Could not query remote deployment state"
    fi
  fi

  RESULT_STATUS="CANCELLED"
  if ! write_result "$RESULT_STATUS" "$rc"; then
    log ERROR "Could not persist cancellation result"
  fi
  exit "$rc"
}

run_checked() {
  local description="$1"
  shift

  log INFO "START: $description"

  if "$@"; then
    log INFO "PASS: $description"
    return 0
  else
    local rc=$?
    log ERROR "FAIL: $description exit=$rc"
    return "$rc"
  fi
}

fail_deployment() {
  local rc="$1"
  shift
  log ERROR "$*"

  local final_status="FAILED"

  if [[ "$DEPLOYMENT_STARTED" == "true" &&
        "$ROLLBACK_ALLOWED" == "true" &&
        -n "$PREVIOUS_RELEASE" ]]; then
    if run_checked "rollback previous release" \
      deployctl rollback \
        --environment "$TARGET_ENV" \
        --release "$PREVIOUS_RELEASE" \
        --idempotency-key "${RELEASE_ID}-rollback"; then
      if run_checked "verify previous release" \
        deployctl verify-current \
          --environment "$TARGET_ENV" \
          --release "$PREVIOUS_RELEASE"; then
        final_status="ROLLED_BACK"
      else
        final_status="ROLLBACK_FAILED"
      fi
    else
      final_status="ROLLBACK_FAILED"
    fi
  fi

  RESULT_STATUS="$final_status"
  if ! write_result "$RESULT_STATUS" "$rc"; then
    log ERROR "Could not persist final deployment result"
  fi

  exit "$rc"
}

trap cleanup EXIT
trap on_error ERR
trap 'on_signal SIGINT' INT
trap 'on_signal SIGTERM' TERM

log INFO "Deployment started release=$RELEASE_ID env=$TARGET_ENV"

if ! command -v jq >/dev/null 2>&1; then
  log ERROR "jq is required to write the result file"
  exit 2
fi

if PREVIOUS_RELEASE="$(deployctl current-release --environment "$TARGET_ENV")"; then
  log INFO "Previous release captured"
else
  rc=$?
  fail_deployment "$rc" "Cannot read current release"
fi

if run_checked "verify artifact" \
  artifactctl verify \
    --uri "$ARTIFACT_URI" \
    --sha256 "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Artifact verification failed"
fi

if run_checked "preflight target" \
  deployctl preflight --environment "$TARGET_ENV"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Deployment preflight failed"
fi

# ROLLBACK_ALLOWED was injected by trusted release policy and validated above.

# Mark the change as started before invoking apply because the remote
# operation may partially succeed even when the client receives an error.
DEPLOYMENT_STARTED="true"

if run_checked "apply release" \
  deployctl apply \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --artifact "$ARTIFACT_URI" \
    --idempotency-key "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Apply operation failed"
fi

if run_checked "wait for readiness" \
  deployctl wait-ready \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --timeout 180s; then
  :
else
  rc=$?
  fail_deployment "$rc" "Readiness check failed"
fi

if run_checked "smoke tests" \
  smoke-test --environment "$TARGET_ENV" --release "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Smoke tests failed"
fi

if run_checked "verify running release" \
  deployctl verify-current \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID" \
    --artifact-digest "$EXPECTED_SHA256"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Running release verification failed"
fi

if run_checked "record current release" \
  deployctl mark-current \
    --environment "$TARGET_ENV" \
    --release "$RELEASE_ID"; then
  :
else
  rc=$?
  fail_deployment "$rc" "Could not record current release"
fi

RESULT_STATUS="SUCCEEDED"
if write_result "$RESULT_STATUS" 0; then
  log INFO "Deployment completed release=$RELEASE_ID env=$TARGET_ENV status=$RESULT_STATUS"
else
  log ERROR "Deployment succeeded but result persistence failed"
  exit 70
fi
~~~

### 12.1. Points to Adjust Before Real-World Use

The example above demonstrates structure and control-flow handling. When adapting it into a real script, you must:

- Replace the hypothetical CLIs with your platform's deployment tools.
- Determine **ROLLBACK_ALLOWED** from a trusted policy and validate rollback compatibility.
- Create the parent directory of **RESULT_FILE** before writing.
- Grant properly scoped write permissions to the result file and protect its contents.
- Configure per-CLI timeouts, not just an overall pipeline timeout.
- Query remote state after a timeout because the operation may continue on the server.
- Add metadata for commit SHA, pipeline run ID, timestamps, and config revision.
- Define handling when no previous version exists or when a migration is irreversible.
- Test all failure branches in a safe environment before enabling production deployments.

**trap ERR** in the example is a catch-all layer for unhandled failures. It does not replace explicit **if/else** branches around critical operations. Commands invoked inside conditions or **&&/||** lists follow special Bash error-handling rules, so you cannot rely solely on **set -e** or traps to determine business state.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only the deploy command exit code | Command was accepted, but application is not ready | Wait for rollout, readiness, and smoke tests |
| Not validating inputs | Deploys to wrong environment or wrong artifact | Validate required fields, allowlists, and digests |
| Using **set -e** as the sole error-handling mechanism | Misses errors in conditionals or pipelines | Explicitly check critical commands |
| Using **! command** and reading **$?** for the error | Gets 0 from the negation operator | Use **if command; then ... else rc=$?** |
| Infinite retries | Increases load and prolongs incidents | Bound attempts, backoff, and timeout |
| Retrying non-idempotent operations | Creates duplicate resources or releases | Idempotency keys and state reconciliation |
| No deployment lock | Two pipelines overwrite each other's versions | Concurrency groups or distributed locks |
| No resource cleanup | Leaks workspaces, processes, and credentials | Trap cleanup or ephemeral runners |
| Marking success right after apply | Reports green even when application is broken | Record **SUCCEEDED** only after verification |
| Unchecked rollback | Can leave state worse off | Verify preconditions and post-rollback state |
| Logging the entire environment | Leaks secrets and tokens | Log via allowlist, redact sensitive data |
| No machine-readable status | Hard to integrate dashboards and investigations | Result JSON linked to release, commit, and digest |

## 14. Sample Scenario: Deployment Fails at the Readiness Step

Suppose a pipeline deploys a new API version to staging. The apply command returns 0 because the platform accepted the request, but a new pod fails to connect to the database.

1. The script records **DEPLOYING** and saves the current release before making changes.
2. The apply command finishes; the script transitions to **VERIFYING**.
3. Readiness checks are polled within the configured timeout.
4. Initial checks return not ready; the script keeps waiting within limits without marking success.
5. When the timeout expires, the script logs the readiness failure and collects diagnostic details.
6. Policy allows rollback, and the previous version exists and is compatible. The script triggers rollback with a dedicated idempotency key.
7. The script waits for the previous version to become ready and verifies the old release ID is running.
8. If verification passes, the final status is **ROLLED_BACK**, while the deployment exit code remains non-zero so the pipeline reports that the candidate release failed.
9. If rollback fails, the status becomes **ROLLBACK_FAILED**, raising an alert requiring operator intervention.
10. Logs and the result record capture the candidate release, previous version, artifact digest, failing step, and rollback outcome.

This scenario shows that the final state must accurately describe what happened. A run should never report **SUCCEEDED** merely because the deployment API accepted the request; at the same time, the system must distinguish a recovered failure from an unrecovered incident.

## 15. Practice Roadmap

You can practice in a staging environment or sample application by following these steps:

1. **Define states:** agree on terminal states such as **SUCCEEDED**, **FAILED**, **ROLLED_BACK**, and **ROLLBACK_FAILED**.
2. **Validate inputs:** require environment, release ID, artifact URI, and digest; reject values outside the allowlist.
3. **Add preflight:** verify permissions, connectivity, artifact, quotas, and current version.
4. **Test exit codes:** create an intentionally failing test command and confirm the script preserves the exact exit code.
5. **Add timeouts:** simulate an unresponsive service and confirm the job stops within the deadline.
6. **Add bounded retries:** simulate transient network errors and permission errors to verify only eligible errors are retried.
7. **Test idempotency:** re-run with the same release ID and confirm no duplicate releases or resources are created.
8. **Control concurrency:** launch two concurrent requests and confirm only one deployment is allowed to modify the environment.
9. **Verify post-deploy:** force readiness or smoke tests to fail in staging and confirm the recorded status is accurate.
10. **Rehearse rollback:** verify the previous version is restored and **ROLLED_BACK** is recorded only after verification.
11. **Test cleanup:** cancel a job mid-run and verify temporary workspaces, processes, locks, and credentials are handled.
12. **Verify reporting:** confirm the result JSON includes release ID, environment, digest, status, exit code, and timestamps.

### Completion Criteria

Learners can consider the exercise complete when they demonstrate that they can:

- Define realistic success criteria for a deployment.
- Distinguish between exit codes and deployment status.
- Validate inputs, permissions, and preflight checks before modifying the environment.
- Handle errors explicitly and preserve accurate exit codes.
- Understand the limitations of **set -e**, **pipefail**, and **trap ERR**.
- Configure timeouts and bounded retries by error class.
- Design idempotent operations and prevent concurrent deployments.
- Clean up resources on success, failure, or cancellation.
- Verify readiness, smoke tests, and the running artifact version.
- Record **SUCCEEDED** only after all required gates pass.
- Distinguish **FAILED**, **ROLLED_BACK**, and **ROLLBACK_FAILED**.
- Persist traceable logs and result records.

## Conclusion

A reliable deployment script must control the entire lifecycle of a change: validating inputs, checking preconditions, executing in a controlled manner, verifying outcomes, and recording final state. The exit code is a process signal; deployment status must reflect the actual state of the environment after readiness, smoke tests, and any rollback.

By combining explicit error handling, timeouts, bounded retries, idempotency, concurrency control, cleanup, and result records, the script becomes an operable and auditable component. This helps the pipeline clearly separate a completed release, a recovered failure, and an incident that still requires intervention.
