# Cleaning Up Resources Using Mechanisms That Always Run on Exit

A CI/CD pipeline often provisions many temporary resources for building and testing: containers, networks, volumes, databases/schemas, Kubernetes namespaces, virtual machines, buckets, test accounts, background processes, port-forwards, or locks. If a job fails midway and skips cleanup, these resources can linger—incurring costs, holding test data, or interfering with subsequent runs.

Therefore, cleanup must be designed as part of the job lifecycle, not an optional command tacked onto the end of a script. You need a finalizer mechanism that runs when the main flow ends regardless of success, failure, or cancellation; resources must have clear identifiers and ownership; deletion must be safe to repeat; and the system must have a way to reclaim orphaned resources if a runner dies or is forcefully terminated.

This lesson focuses on resource cleanup in CI/CD. Examples cover in-process cleanup, pipeline-level finalizers, exit code preservation, cleanup error handling, limits of always-run mechanisms, and TTL-based resource reclaimers (janitors).

## 1. Why must cleanup run on every outcome?

A script is often written sequentially: create environment, run tests, delete environment. That approach cleans up resources only if every preceding command follows the expected happy path.

For example, if tests return a non-zero exit code and the shell exits under fail-fast mode, the deletion command at the bottom of the script may never run. If an operator clicks Cancel, the runner times out, or a deploy step fails, ordinary cleanup can likewise be skipped.

Leftover resources can cause:

- Ongoing cloud or container compute costs.
- Namespaces, databases, or volumes consuming quotas.
- Network ports or background processes colliding with later runs.
- Lingering test data corrupting subsequent test outcomes.
- Unreleased locks forcing other pipelines to wait.
- Temporary credentials remaining active.
- Resources holding sensitive data not being deleted on schedule.
- Shared runners or environments gradually destabilizing.

Reliable cleanup gives each run its own resource boundary. Once work finishes, resources created by that run are released and the run's state is recorded.

## 2. What is a finalizer?

A finalizer is a handler registered to execute when an execution scope terminates, regardless of whether the main outcome succeeded or failed. Depending on the technology, this mechanism goes by different names:

- Shells have `EXIT` traps.
- Java or C# have `finally` and resource-closing blocks.
- GitHub Actions has step conditions using `always()`.
- Jenkins Declarative Pipeline has `post` with `always`.
- GitLab CI has `after_script`.
- Azure Pipelines has `condition: always()`.

These mechanisms operate at different scopes. An `EXIT` trap protects only a single shell process. `finally` protects a programmatic scope. CI finalizers protect steps within a job or pipeline according to platform semantics.

Never assume a finalizer is guaranteed to run in every scenario. Lost runners, host shutdowns, `SIGKILL`, or immediate platform termination can prevent cleanup from executing. Therefore, finalizers must be paired with ownership labels, TTLs, and an independent orphan-reclamation janitor.

## 3. Identifying resources owned by a run

Before provisioning resources, the pipeline must define how each resource is identified and tied to a specific run.

A temporary resource should carry:

- Unique name or ID.
- Run ID or pipeline ID.
- Owning repository/project and service.
- Job or stage that created it.
- Creation timestamp.
- Expiration timestamp (TTL).
- Resource type.
- Environment or namespace.
- Label marking it as an ephemeral CI resource.
- Cleanup policy or responsible owner.

Example logical labels:

```text
owner=ci
service=orders-api
run-id=1842
job=integration-test
created-at=2026-11-18T08:00:00Z
expires-at=2026-11-18T10:00:00Z
```

Names and labels must comply with the target system's constraints. Avoid generic names like `test-db` or `temp-namespace` when multiple pipelines can provision concurrently.

The run ID identifies which run owns which resource. The TTL enables external systems to reclaim resources if the finalizer never runs.

## 4. Inventorying resources that need cleanup

Containers and databases are not the only things requiring cleanup. Inventory everything provisioned or stateful during the job.

| Category | Examples | Cleanup action |
|---|---|---|
| Process | Test server, worker, tunnel, port-forward | Stop process and verify exit |
| Container | Container, network, volume | Stop then remove exact run resources |
| Kubernetes | Namespace, Job, Pod, temporary Secret | Delete by owner label and wait with timeout |
| Database | Database, schema, test rows, temporary role | Drop or delete data within owned scope |
| Cloud | VM, disk, IP, load balancer, bucket | Delete specific resource IDs |
| Lock | Deployment lock, migration lock, lease | Release or let lease expire by design |
| Credential | Token, certificate, temporary account | Revoke or use short expiration |
| File | Temp directory, socket, scratch report | Delete files belonging to workspace/run |
| Network | Proxy, tunnel, temporary firewall rule | Close connections and remove created rules |
| Test data | Tenant, user, order, fixture | Delete by namespace or run ID |

Document this inventory in the job design. If a step provisions a resource without an owner, ID, or deletion path, that resource risks becoming an orphan.

## 5. Registering cleanup at the very start

Register the cleanup handler before provisioning any resources. If registration happens only after creation finishes, a failure between creation and registration can leave unmanaged resources behind.

Safe sequence:

1. Initialize variables holding resource IDs.
2. Register the finalizer.
3. Create resources with owner labels and TTLs.
4. Persist each ID immediately when the API returns it.
5. Execute the main workload.
6. Finalizer reads stored IDs and performs cleanup.
7. Record cleanup outcome.

When resources are created across multiple API calls, store each ID after each successful call. If database creation succeeds but network creation fails, the finalizer still needs to know which database to delete.

If resource creation can complete server-side after a client timeout, look up the resource by run ID or idempotency key. Never assume a timeout means the resource was not created.

## 6. Cleanup must be idempotent

A cleanup operation is idempotent when running it multiple times yields the same final state as running it once. This matters because finalizers may retry, operators may rerun cleanup, or a janitor may later reap the same resource.

Examples:

- Deleting an already-absent resource counts as success.
- Removing an already-removed network rule does not trigger a fatal error.
- Releasing a lock frees only locks belonging to the matching owner.
- Deleting a namespace leaves other runs' namespaces untouched.
- Revoking an already-expired or already-revoked credential handles gracefully.

When an API returns HTTP 404 because the resource does not exist, cleanup can treat that as goal achieved. `401`/`403` errors usually indicate permission problems and should fail clearly rather than retrying indefinitely. `429`, timeouts, or `5xx` errors can use bounded retries if deletion is safe.

Idempotency does not mean ignoring every error. If an API returns `500` or denies access, the resource may still exist. Distinguish "confirmed gone" from "unable to verify."

## 7. Delete only resources belonging to the current run

Cleanup can be more destructive than provisioning if selectors are too broad. Deleting every namespace prefixed with `test-` can accidentally wipe out another pipeline's resources or a shared environment.

Principles:

- Delete by stored resource ID or exact owner label.
- Verify owner/run ID before deleting.
- Restrict cleanup permissions to authorized projects, namespaces, or resource groups.
- Never delete shared resources just because their names resemble temporary ones.
- Never use wildcards without an allowlist.
- Log the ID and rationale before deleting.
- If ownership cannot be confirmed with certainty, stop and error rather than guessing.

Resource names can be reused. An immutable resource ID or API-assigned UID is safer than relying solely on display names.

## 8. Bash example using an EXIT trap

In a Bash script, an `EXIT` trap invokes cleanup whenever the shell exits normally or terminates early due to fail-fast.

Example:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

RESOURCE_ID=""

cleanup() {
  local main_status=$?
  local cleanup_status=0

  trap - EXIT

  if [[ -n "$RESOURCE_ID" ]]; then
    ./scripts/delete-env.sh "$RESOURCE_ID" || cleanup_status=$?
  fi

  if (( main_status != 0 )); then
    if (( cleanup_status != 0 )); then
      printf 'Cleanup failed with status %s\n' "$cleanup_status" >&2
    fi
    exit "$main_status"
  fi

  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

RESOURCE_ID="$(./scripts/create-env.sh --owner "$CI_RUN_ID")"
test -n "$RESOURCE_ID"

./scripts/run-integration-tests.sh
```

How it works:

- The `EXIT` handler is registered before provisioning the environment.
- When the shell exits, `cleanup` captures the original exit status.
- If `RESOURCE_ID` is populated, the script runs the deletion command.
- `trap - EXIT` prevents the handler from recursing when exiting the function.
- If the main workload failed, the script preserves the main failure code.
- If the main workload succeeded but cleanup failed, the script returns the cleanup failure code.
- `INT` and `TERM` are translated into exit codes, triggering the `EXIT` handler to run cleanup.

Adapt this pattern to your actual provision/delete APIs. The creation command should attach owner and TTL from the start. If a resource is created yet the process terminates before printing the ID to stdout, the finalizer will not know the ID; the janitor must reclaim it using owner/run ID labels.

## 9. Preserving the primary failure when cleanup also fails

Two errors can happen in the same run:

1. The main workload fails, e.g., integration tests exit with code `1`.
2. Cleanup also fails, e.g., the database deletion API times out.

If cleanup overwrites the initial exit code, operators may only see the database deletion failure and miss the test failure. Conversely, if cleanup fails after a passing workload without being recorded, resources leak while the pipeline reports green.

Define an explicit policy:

| Main workload outcome | Cleanup outcome | Final status |
|---|---|---|
| Succeeded | Succeeded | Succeeded |
| Failed | Succeeded | Preserve primary failure |
| Failed | Failed | Preserve primary failure and record cleanup failure separately |
| Succeeded | Failed | Fail or warn depending on risk level |
| Cancelled | Succeeded | Preserve cancelled status |
| Cancelled | Failed | Preserve cancelled status and note possible leftover resources |

For high-cost or high-security-risk resources, cleanup failure after a succeeding workload should fail the job or escalate to action-required state. For scratch files inside an ephemeral runner workspace destroyed with the runner, a lower warning level may suffice.

Never mash cleanup status into an unstructured message. Record primary result and cleanup result as separate fields.

## 10. Using try/finally in Java applications or test tooling

When test code provisions resources itself, model the resource as `AutoCloseable` and use `try-with-resources`. Java invokes `close()` on scope exit even if the block throws an exception.

Example:

```java
try (TemporaryEnvironment environment =
         provisioner.create("integration-test")) {
    testClient.runAgainst(environment.endpoint());
}
```

`TemporaryEnvironment` should implement `AutoCloseable`, and `close()` must be safe to call multiple times. If both the block body and `close()` throw exceptions, `try-with-resources` preserves the primary exception and attaches the `close()` exception as a suppressed exception. That prevents cleanup failures from masking test failures.

When resources involve interdependent objects, close them in reverse creation order—for example, stop workers first, close connection pools next, and delete the underlying database or network last.

## 11. Using try/finally in PowerShell

PowerShell supports `try/finally`. The `finally` block runs whenever control leaves `try/catch` along normal execution paths.

Example:

```powershell
$resourceId = $null

try {
    $resourceId = ./scripts/create-env.ps1 -Owner $env:CI_RUN_ID
    ./scripts/run-tests.ps1 -ResourceId $resourceId
}
finally {
    if ($resourceId) {
        ./scripts/delete-env.ps1 -ResourceId $resourceId
    }
}
```

In real scripts, set an appropriate `ErrorActionPreference` and check `$LASTEXITCODE` after native executables. If cleanup can throw, log cleanup errors separately and preserve the original exception. Never use `finally` to swallow exceptions silently.

Just like shell traps, `finally` will not run if the process or host is forcefully terminated before the runtime can execute it.

## 12. GitHub Actions job-level finalizers

Each GitHub Actions step runs in its own process. An `EXIT` trap in one step does not protect subsequent steps and does not replace a job-level finalizer.

Use a step with condition `always()` to run cleanup after preceding steps succeed, fail, or the job is cancelled per platform semantics.

Example:

```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Create temporary environment
        id: environment
        shell: bash
        run: |
          resource_id="$(./scripts/create-env.sh --owner "$GITHUB_RUN_ID")"
          test -n "$resource_id"
          printf 'resource_id=%s\n' "$resource_id" >> "$GITHUB_OUTPUT"

      - name: Run integration tests
        run: ./scripts/run-integration-tests.sh

      - name: Always clean up
        if: ${{ always() }}
        timeout-minutes: 5
        env:
          RESOURCE_ID: ${{ steps.environment.outputs.resource_id }}
        run: |
          if [[ -n "$RESOURCE_ID" ]]; then
            ./scripts/delete-env.sh "$RESOURCE_ID"
          fi
```

`always()` is a GitHub Actions expression placed in the condition field. The provisioning step saves its output to `GITHUB_OUTPUT`, which the cleanup step references. Never rely on shell variables exported in an earlier step because each step spawns a separate process.

Always set a timeout on cleanup so the job cannot hang indefinitely. If the create step is killed after provisioning the resource but before writing the output, the cleanup step will lack the ID. Owner labels and TTLs remain essential so the janitor can find that resource.

## 13. Jenkins Declarative Pipeline with post always

Jenkins Declarative Pipeline provides a `post` block to run actions after stages complete. The `always` condition fits cleanup that must execute regardless of pipeline outcome.

Example:

```groovy
pipeline {
    agent any

    stages {
        stage('Provision') {
            steps {
                script {
                    env.RESOURCE_ID = sh(
                        script: './scripts/create-env.sh --owner "$BUILD_TAG"',
                        returnStdout: true
                    ).trim()
                }
            }
        }

        stage('Test') {
            steps {
                sh './scripts/run-integration-tests.sh'
            }
        }
    }

    post {
        always {
            script {
                if (env.RESOURCE_ID?.trim()) {
                    withEnv(["RESOURCE_ID=${env.RESOURCE_ID}"]) {
                        sh './scripts/delete-env.sh "$RESOURCE_ID"'
                    }
                }
            }
        }
    }
}
```

In this example, the resource ID is passed via Jenkins's `env.RESOURCE_ID`. Use `withEnv` or safe variable passing rather than interpolating IDs directly into shell strings that could be interpreted as code. Validate the resource ID format before using it.

`post { always }` runs after stages according to Jenkins semantics, yet cannot guarantee cleanup if the agent or controller loses execution capability. Configure a cleanup timeout and maintain TTL/janitor protection as a safety net.

## 14. GitLab CI with after_script

GitLab CI provides `after_script` to run commands after the main `script`. An important detail is that `after_script` runs in a separate shell context; shell variables exported in `script` do not automatically exist in `after_script`.

Persist the resource ID to a simple temporary file and read it back inside `after_script`:

```yaml
integration:
  script:
    - RESOURCE_ID="$(./scripts/create-env.sh --owner "$CI_PIPELINE_ID")"
    - printf 'RESOURCE_ID=%s\n' "$RESOURCE_ID" > resource.env
    - ./scripts/run-integration-tests.sh

  after_script:
    - |
      if [ -f resource.env ]; then
        . ./resource.env
        if [ -n "$RESOURCE_ID" ]; then
          ./scripts/delete-env.sh "$RESOURCE_ID"
        fi
      fi

  artifacts:
    when: always
    paths:
      - resource.env
```

`resource.env` should contain only a validated identifier—never tokens or secrets. Never source a file editable by untrusted users. If the file comes from an artifact or mutable workspace, validate ownership and ID format before acting on it.

`after_script` has its own lifecycle and timeout under GitLab Runner configuration. Failures in `after_script` do not necessarily alter the main script's exit status; if cleanup is mandatory for job success, add explicit cleanup verification or adopt a pattern suited to your GitLab version. Check platform and runner documentation for exact behavior on job cancellation and timeouts.

## 15. Azure Pipelines with condition: always()

Azure Pipelines lets you attach conditions to steps. `always()` evaluates the step to run even if earlier steps failed or the job was cancelled, subject to timeouts and agent availability.

Example:

```yaml
steps:
  - bash: |
      resource_id="$(./scripts/create-env.sh --owner "$BUILD_BUILDID")"
      echo "##vso[task.setvariable variable=resourceId]$resource_id"
    displayName: Create temporary environment

  - bash: ./scripts/run-integration-tests.sh
    displayName: Run integration tests

  - bash: |
      if [ -n "$RESOURCE_ID" ]; then
        ./scripts/delete-env.sh "$RESOURCE_ID"
      fi
    displayName: Always clean up
    condition: always()
    timeoutInMinutes: 5
    env:
      RESOURCE_ID: $(resourceId)
```

Task variables are shared through Azure Pipelines' variable mechanism rather than shell exports. When passing values across jobs or stages, use properly scoped output variables and dependency mappings.

`always()` cannot run if the agent is lost or the job is killed hard. Set timeouts and maintain resource TTLs to handle those cases.

## 16. Comparing finalizer mechanisms

| Mechanism | Scope | Notes |
|---|---|---|
| Bash `EXIT` trap | Single shell process | Cannot catch `SIGKILL` or runner loss |
| Java `try-with-resources` | Single resource scope in JVM | Closes in reverse order; tracks suppressed exceptions |
| PowerShell `finally` | Single `try/catch/finally` block | Does not run if process is forcefully terminated |
| GitHub Actions `always()` | Step/job per workflow condition | Must pass resource ID between steps; set timeout |
| Jenkins `post { always }` | Pipeline `post` section | Depends on agent/controller remaining operational |
| GitLab `after_script` | Job post-processing section | Separate shell context; mind timeout and exit-status semantics |
| Azure Pipelines `always()` | Step/job condition | Still depends on agent and cancellation/timeout limits |

No single mechanism guarantees cleanup across every failure mode. The right choice depends on where the resource is created and its lifecycle.

If a resource lives inside one process, use `finally` or an `EXIT` trap. If it spans multiple CI steps, use a job-level finalizer. If it can outlive the runner, add TTLs and an independent janitor.

## 17. Cleaning up in dependency order

Cleanup must respect dependencies between resources. For example, do not delete a network before stopping containers attached to it.

A typical sequence:

1. Stop accepting new work or halt traffic to the temporary environment.
2. Stop test clients, workers, and background processes.
3. Collect logs, reports, and evidence to retain.
4. Close connections, tunnels, and port-forwards.
5. Release locks or leases.
6. Delete test data and temporary credentials.
7. Delete workloads/containers.
8. Delete databases, volumes, networks, or namespaces.
9. Verify resources have been freed.
10. Record cleanup outcome and any remaining resources.

Actual ordering depends on your system. If container logs are needed for debugging, gather them before deleting the container. If database cleanup collides with a running migration process, stop that process first.

Never delete evidence or release artifacts just because they were produced in the same run. Clean up only ephemeral resources owned by the job; retain reports under a separate retention policy.

## 18. Using TTLs to prevent orphaned resources

A TTL (time to live) is the maximum duration a resource may exist unless renewed or deleted earlier. Every temporary resource should carry an expiry timestamp stored where management tooling can query it.

Examples:

- CI namespaces carry a run ID label and `expires-at` annotation.
- Cloud resources carry owner, run ID, and TTL tags.
- Temporary databases/schemas store expiration metadata.
- Test-run object storage prefixes enforce lifecycle rules.
- Temporary credentials are issued with short expirations from the start.

The TTL should match expected job duration plus a safety buffer. If the TTL is too short, the janitor may delete resources while tests are still running. If too long, orphans linger and consume capacity.

For long-running jobs, extend TTLs via heartbeats or leases. Renewals must authenticate ownership and enforce a hard ceiling; never allow a job to hold ephemeral resources indefinitely.

## 19. Independent janitor for reclaiming orphaned resources

A janitor is a background process or scheduled job that periodically locates expired CI resources and reclaims them. It acts as the safety net whenever finalizers fail to run.

A safe janitor should:

- Target only resources carrying managed CI labels.
- Verify `expires-at` has passed.
- Verify owner/run ID and resource type.
- Skip resources with active valid leases.
- Support dry-run or reporting mode before enabling automatic deletion.
- Cap deletions per sweep cycle.
- Audit every deleted resource.
- Use bounded retries on transient errors.
- Alert when deletion fails or resources lack required metadata.

Never delete resources solely because a job ID no longer appears in CI. A job might be paused, or the CI status API might be degraded. TTLs and leases give stronger signals; for high-impact resources, add a grace period and perform a final check before deleting.

The janitor should run under a dedicated identity scoped only to deleting CI-labeled resources within permitted boundaries. Never grant full cloud-account admin rights when cleaning up a single resource group or namespace.

## 20. Handling successful resource creation when the ID is lost

A tricky edge case occurs when the API creates a resource yet the client times out before receiving the response. The pipeline lacks the ID to pass to its finalizer.

Reduce this risk by:

- Sending an idempotency key derived from the run ID when supported by the API.
- Attaching owner/run ID tags in the creation request.
- Using deterministic unique names derivable from the run ID.
- After a timeout, querying by owner label before attempting to recreate.
- Saving the ID immediately upon receiving the response.
- Relying on the janitor to find expired resources by owner and TTL.

Never blindly retry a `create` command if the first call may have succeeded. Retrying creates a second VM, database, or namespace, driving up cost and causing collisions. Query by idempotency key or owner label first.

## 21. Bounded retries for cleanup

Cleanup itself can hit transient errors: API rate limits, network timeouts, busy control planes, or resources still undergoing asynchronous deletion.

Use retries with backoff and jitter:

```text
attempt 1: wait 1 second
attempt 2: wait 2 seconds plus jitter
attempt 3: wait 4 seconds plus jitter
attempt 4: wait 8 seconds plus jitter
stop after the configured deadline
```

These values are illustrative. Total retry duration must fit within the cleanup timeout. Never sleep so long that CI kills the finalizer before it finishes.

Failure classification:

| Error | Handling |
|---|---|
| Resource already absent | Treat as cleaned up |
| Timeout or transient network error | Bounded retry |
| HTTP 429 or 5xx | Backoff; honor retry hints if present |
| 401/403 | Stop and report permission error |
| Resource stuck in `Terminating` | Wait with bounds and recheck |
| Owner mismatch | Do not delete; report mismatch |
| Invalid resource ID | Stop; never guess names to delete |
| Dependency still referencing resource | Stop consumer first, then retry |

Never retry forever and never turn every error into success. Once the deadline expires, record exactly which resources remain so the janitor or operators can handle them.

## 22. Cleanup when jobs are cancelled or time out

Cancellation comes in varying degrees:

- User requests cancel and the runner has time to handle signals.
- Job times out and the platform initiates process termination.
- Agent loses connectivity while external resources keep running.
- Runner is forcefully terminated or host shuts down.
- Process receives `SIGKILL` or is abruptly killed by the OS.

Finalizers have a chance to run on graceful cancellations, yet cannot be guaranteed when runners or processes vanish.

Design defense in depth:

1. `EXIT` trap or `finally` at the process level.
2. Job-level finalizer in the CI workflow.
3. TTLs attached to resources.
4. Independent janitor.
5. Auditing/alerting when cleanup fails to complete.

Configure a dedicated timeout for finalizers. If the main job has a 30-minute timeout, cleanup needs a bounded additional window per platform capabilities. Never assume finalizers get unlimited runtime after cancellation.

## 23. Cleaning up credentials, locks, and background processes

Non-cloud resources also require cleanup.

**Credentials:** revoke tokens or certificates where possible; for short-lived tokens, verify expiration and avoid writing them to persistent files.

**Locks:** release locks only when the owner token or run ID matches. For distributed locks, use expiring leases so dead processes cannot hold locks forever.

**Background processes:** record the PID or process group ID, stop the exact processes belonging to the run, and wait for exit. Never kill by generic process name, which can terminate services from other jobs.

**Port-forwards/tunnels:** track PIDs or handles and close tunnels before tearing down networks.

**Temporary files:** delete only directories created within the workspace/run; never delete paths supplied by untrusted inputs without canonicalization and validation.

For processes running inside containers or dedicated runners, manage by process group or supervisor rather than tracking only the parent PID. Child processes can outlive a parent exit if unmanaged.

## 24. Recording cleanup evidence

Cleanup should emit a separate record showing which resources were reclaimed and which remain.

A record can include:

- Run ID, job ID, and owner.
- Resource type and resource ID.
- `created-at` and `cleanup-started-at`.
- Cleanup attempt count.
- Finalizer source: `trap`, `finally`, CI post step, or `janitor`.
- Outcome: `deleted`, `already-absent`, `failed`, `skipped`, or `orphaned`.
- Sanitized error code and message.
- Completion timestamp.
- Executing principal or workload.

Never put secrets, connection strings, or tokens in cleanup reports. If cleanup failed, the report should state the next action or when the janitor will retry.

Evidence also measures orphan rates, cleanup latency, and permission errors. If repeated runs leak the same resource type, fix how it is provisioned, labeled, or authorized for deletion.

## 25. Testing the cleanup path

Cleanup is a critical code path and must be tested deliberately. Testing only happy-path pipelines does not prove finalizers work on failure.

Scenarios to test:

- Main workload succeeds.
- Unit/integration tests fail.
- Provisioning fails partway through.
- Cleanup is invoked twice.
- Resource was already deleted before the finalizer ran.
- Delete API times out or returns rate limits.
- Cleanup credential lacks permissions.
- Job is cancelled mid-test.
- Runner is killed to confirm the janitor reclaims orphans.
- Two runs execute concurrently with separate resources.
- Resources share a friendly name but have different owners.
- Cleanup times out while a resource stays in `Terminating`.

Verify that the primary failure is preserved, cleanup failures are logged separately, and no other run's resources are touched. Use short-TTL test resources to rehearse janitor sweeps safely.

Never intentionally kill production runners to test cleanup. Use test environments and reproducible resources.

## 26. Common anti-patterns

| Poor practice | Consequence | Better approach |
|---|---|---|
| Placing delete only at the end of the script | Skipped whenever an earlier command fails | Register `trap`/`finally`/finalizer upfront |
| Assuming `always()` is an absolute guarantee | Lost runners still leave resources behind | Pair with TTLs and a janitor |
| Cleaning up by generic name or wildcard | Risk deleting another run's resources | Use exact resource IDs and owner labels |
| Non-idempotent cleanup | Retries raise errors or side effects | Treat already-absent resources as achieved |
| Letting cleanup overwrite primary exit code | Masks original root cause | Track primary and cleanup statuses separately |
| Ignoring cleanup failures after green jobs | Resources leak while pipeline reports green | Enforce fail/warn policy by risk level |
| Exporting shell vars in one step for the next | Variable missing in new step process | Use CI platform outputs/variables/files |
| Relying on main-script shell vars in GitLab `after_script` | Resource ID missing in fresh shell | Persist ID to a safe file or metadata |
| Infinite delete retries | Job hangs or blows past timeout | Bounded backoff and hard deadlines |
| Deleting resources before collecting reports | Loses logs and debugging evidence | Collect required evidence before cleanup |
| Omitting TTLs | Orphans persist indefinitely | Tag expirations and run a janitor |
| Running janitor with broad admin permissions | Selector bug can wipe broad infrastructure | Dedicated identity with least-privilege scope |
| Skipping ownership checks before deletion | May reclaim active resources from another run | Verify run ID/lease/owner |

## 27. Roadmap for adopting cleanup in pipelines

Standardize adoption in stages:

1. **Inventory resources:** list processes, containers, databases, namespaces, cloud resources, credentials, locks, and temp files.
2. **Define ownership:** every resource carries run ID, job ID, resource type, and TTL.
3. **Register finalizers early:** configure traps, `finally`, or CI post steps before provisioning.
4. **Persist resource IDs:** save immediately upon creation and pass via platform-appropriate outputs or files.
5. **Make cleanup idempotent:** delete only matching owner, handle already-absent cleanly, and bound retries.
6. **Preserve primary errors:** separate primary status from cleanup status.
7. **Set timeouts:** bound cleanup execution and async deletion waits.
8. **Deploy a janitor:** locate TTL-expired resources, verify ownership, and reclaim.
9. **Record evidence:** log resources, attempts, outcomes, and errors.
10. **Exercise failure paths:** test failures, cancellations, timeouts, runner loss, and delete API faults.
11. **Monitor orphans:** alert when resources exceed TTL or cleanup failures climb.

Start with a single integration test job that creates a temporary namespace or database. Once stable, apply the same owner/TTL/finalizer convention to all other resource types.

## 28. Measuring cleanup effectiveness

Useful metrics:

- Percentage of runs completing cleanup successfully.
- Resources still alive past TTL.
- Time elapsed from job completion to resource deletion.
- Finalizer failure count broken down by error class.
- Resources reclaimed by the janitor.
- Cost incurred by orphaned resources.
- Cleanup retry success rate.
- Accidental deletions or owner mismatches.
- Jobs failed solely due to cleanup.
- Share of runs with complete resource IDs and owner labels.

Never optimize cleanup success rates by ignoring deletion errors. Measure actual lingering resources alongside recovery behavior when finalizers fail to run.

## 29. Checklist before provisioning ephemeral resources in CI

- [ ] Resources carry a run-unique ID or name.
- [ ] Owner labels and TTLs are attached at creation time.
- [ ] Finalizers are registered before provisioning starts.
- [ ] Resource IDs are persisted immediately upon creation.
- [ ] Cleanup deletes only resources matching the right owner.
- [ ] Cleanup is safe to run multiple times.
- [ ] Already-absent resources are treated as goal achieved.
- [ ] Cleanup errors are recorded separately from primary workload errors.
- [ ] Policy defines whether cleanup failure fails or warns the job.
- [ ] Cleanup timeouts and retry deadlines are bounded.
- [ ] Dependent resources are torn down in the right order.
- [ ] Required reports and logs are collected before deletion.
- [ ] CI finalizer matches platform capabilities and job scope.
- [ ] Variables or resource IDs pass through proper CI mechanisms.
- [ ] TTLs and an independent janitor cover lost-runner scenarios.
- [ ] The janitor verifies owner, lease, and expiration before deleting.
- [ ] Cleanup identity holds least-privilege permissions.
- [ ] Failure, cancellation, retry, and orphan recovery paths are tested.
- [ ] Cleanup evidence contains no secrets or sensitive data.

## Conclusion

Reliable resource cleanup requires layered defenses. Traps, `finally` blocks, and CI finalizers handle ordinary exit paths; idempotent deletion and early ID persistence make cleanup safely repeatable; TTLs and janitors reclaim resources when runners or processes lose the chance to clean up.

Register finalizers before provisioning resources, attach owner/run IDs and TTLs upfront, delete only resources owned by the current run, bound retries, and preserve the primary workload's exit code. Record cleanup outcomes and rehearse failures, cancellations, timeouts, and runner loss. Doing so keeps failure diagnostics intact while preventing orphaned resources and runaway costs.
