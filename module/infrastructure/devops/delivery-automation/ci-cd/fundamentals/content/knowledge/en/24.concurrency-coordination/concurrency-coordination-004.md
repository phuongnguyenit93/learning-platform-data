# Cancelling Stale Work Before It Causes Persistent Side Effects

In CI/CD, a new commit can appear while the pipeline for the previous commit is still running. A frequently updated pull request can spawn multiple test runs; a closed branch can leave jobs queued; a new release candidate can render earlier preparation work pointless. Letting every job run to completion wastes runner capacity, lengthens queues, and can produce stale, misleading results.

Cancelling stale work means stopping jobs or pipelines that no longer represent the latest desired state. However, not every job can be cancelled arbitrarily. A job running unit tests can usually stop immediately; a job that has already published packages, executed database migrations, or altered production may have created effects that must be preserved and handled through dedicated procedures.

The core principle is **to cancel work early while it is still safe to cancel, while protecting operations with side effects using checkpoints, idempotency, locks, and mechanisms that prevent stale jobs from continuing to write data**.

## 1. Identifying Stale Work

A job or pipeline becomes stale when the input or goal it represents has been superseded, revoked, or is no longer permitted to execute.

Common scenarios:

- A pull request receives a new commit while tests for the previous commit are still running.
- A user pushes several commits in quick succession; intermediate pipelines are no longer needed.
- A branch or pull request is closed, deleted, or moved into a state no longer requiring checks.
- A pipeline is rerun and the new attempt supersedes the earlier attempt's outcome.
- A new release candidate is created before the publish job for the older candidate starts.
- An upstream dependency job is cancelled or fails.
- An operator requests halting a rollout or revoking a release request.
- Scheduled triggers create overlapping executions where only the latest run remains useful.

Not every older job is stale. For example, a pipeline generating an audit report for an already-shipped release may still need to finish even after a newer release appears. Determine the value of work based on its objective, trigger type, and side-effect state—not merely its start time.

### Freshness and Run Identity

To accurately identify stale work, bind jobs to explicit input identifiers:

- Repository, branch, or pull request ID.
- Commit SHA or immutable revision.
- Pipeline/run ID and attempt number.
- Release ID or artifact digest.
- Environment and deployment target if the job can modify runtime state.
- Request generation/version if the coordination system tracks a latest-version concept.

Do not rely on a branch name or mutable tag as sole proof of what is running. The same branch can point to a different commit after each push; tags can also move if the repository does not protect them. Jobs must record the checked-out commit SHA and re-verify freshness before performing actions with side effects.

## 2. Distinguishing Cancel, Fail, Skip, Timeout, and Rollback

These states carry different operational meanings:

| State/action | Meaning | Example |
|---|---|---|
| Cancel | Actively request stopping a queued or running job/pipeline | Cancelling tests for an old commit when a PR gets a new commit |
| Fail | Job ends due to execution error or unmet condition | Unit tests fail or a build command exits non-zero |
| Skip | Job does not run because a condition or dependency is unmet | Staging deploy job is skipped when the branch is not `main` |
| Timeout | System stops a job for exceeding its time limit | Integration tests do not finish within 20 minutes |
| Rollback | Execute a compensating action to return the system to a previous or stable state | Redeploying an older image digest after a new release causes errors |
| Compensation | Execute a counteracting business operation to handle already-occurred side effects | Cancelling a reservation or refunding a transaction per business workflow |

Cancelling does not automatically undo what a job has already done. If a job already sent an email, provisioned a cloud resource, published a package, or updated a database, stopping the process only prevents subsequent steps; completed effects may persist. Recovery requires intentional rollback or compensation.

Likewise, a cancelled job is not necessarily a product defect. Pipeline reporting must distinguish `cancelled` from `failed`; otherwise failure rates are skewed and developers struggle to tell why work stopped.

## 3. Classifying Work by Cancellation Safety

Before enabling automatic cancellation, determine where a job can stop and what effects may already have occurred.

| Work type | Cancellability | Suggested handling |
|---|---|---|
| Lint, unit tests, static analysis | Usually safe | Cancel immediately when inputs are superseded; record `cancelled` status |
| Building artifacts in a temporary workspace | Usually safe if output has not been published | Stop process, clean temporary workspace and unpublished artifacts |
| Integration tests with ephemeral resources | Safe if cleanup exists | Stop tests, tear down temporary containers/databases, and reclaim test data |
| Benchmark/performance tests | Cancellable, but must stop load generators and clean up | Stop load generation, wait for workers to exit, mark data incomplete |
| Publishing packages/images | Needs control | Verify whether upload completed; use immutable versions/digests and handle partial states |
| Artifact signing or release publishing | Needs control | Protect signing operations, verify state, and avoid half-created releases |
| Database migrations | High risk | Cancel only at safe checkpoints; design resumable or compensatable migrations |
| Production deploy/rollout | High risk | Avoid arbitrary latest-wins; use pause/abort policies and verify runtime state |
| Sending notifications or external operations | Side effects may be irrevocable | Use idempotency keys, outboxes, or appropriate compensation |

Marking a job `interruptible` only tells the orchestrator it can be stopped; it does not prove the underlying scripts handle cleanup or rollback properly. Pipeline designers must establish safe boundaries at the operation level.

## 4. Choosing a Cancellation Policy by Job Objective

Three policies are commonly used:

### Latest Wins — Keep Only the Latest Work

Fits checks validating current state, such as pull request lint/tests. When a new commit arrives, older pipelines are cancelled so runners focus on the newest revision.

Not suitable for all release work. If a pipeline is deploying to production, a new commit arriving does not mean the current deployment should be killed immediately. Mid-flight cancellation can leave a partial rollout or ambiguous runtime state.

### Queue/Serialize — Run Sequentially

Fits migrations, deployments, or operations on a shared resource. Runs are queued or only one run is allowed into the critical section at a time.

Queuing alone does not solve freshness. When a job's turn arrives, it must still check whether its request remains valid or has been superseded by a newer release. If already stale before starting side effects, the job should exit without taking action.

### Deduplicate — Coalesce Duplicate Work

Fits tasks with identical inputs and desired outputs, such as generating reports or computing checksums for the same artifact digest. The system can use idempotency keys or cached results to avoid duplicate execution.

Deduplication must key on input content and resource scope. Two jobs sharing a name but targeting different commits or environments must not be coalesced mistakenly.

| Objective | Typical suitable policy | Example |
|---|---|---|
| Fast PR feedback | Latest wins | Keep tests only for the newest commit |
| Deploy to an environment | Serialize/queue and check freshness | One production deployment at a time |
| Generate artifact reports | Deduplicate by digest | One SBOM per image digest |
| Database migrations | Serialize + lock + checkpoint | Never run two migrations concurrently |
| Nightly batches | Queue or drop older runs per policy | Prevent two overlapping syncs on the same dataset |

## 5. Placing Freshness Checkpoints Before Side Effects

Cancelling a running job is asynchronous. There can be a window between when the system sends the cancel signal and when the process actually terminates. An old job can still execute several commands or continue calling APIs if it does not check state.

Therefore, jobs with side effects must verify for themselves that they are still authorized before every critical boundary.

Example checkpoints:

1. Before fetching or using privileged credentials.
2. Before publishing a package or creating a release tag.
3. Before starting a migration or writing shared data.
4. Before shifting traffic or updating production workloads.
5. Before sending external notifications or triggering downstream workflows.

### Using Generation or Revision Tokens

An orchestration system can assign an incrementing generation to each request. A job may write only if its generation remains the active generation.

Pseudocode logic example:

```text
request = get_current_release_request(service)
my_generation = request.generation

run_tests_and_prepare_candidate()

if get_current_generation(service) != my_generation:
    cancel_without_side_effect()
    return

publish_candidate()

if get_current_generation(service) != my_generation:
    stop_before_deploy()
    record_published_but_superseded()
    return

deploy_approved_digest()
```

Freshness checks must occur close to the time of the side effect. Checking early and then waiting a long time before writing invites a time-of-check to time-of-use (TOCTOU) race if a new request arrives in between. In distributed systems, combine generation tokens with locks or fencing tokens to stop old jobs from writing after losing authority.

### Fencing Tokens

A fencing token is a monotonically increasing version number issued by the system when a worker receives permission to enter a critical section. The target resource stores the highest accepted token and rejects operations carrying a lower token.

For example:

- Worker A receives token 41 but stalls.
- A's lease expires; Worker B receives token 42 and performs the update.
- Worker A wakes up and sends an old command with token 41.
- The resource rejects token 41 because token 42 has already been accepted.

Fencing protects the resource from old workers that keep running after their lease expires. A plain distributed lock does not always guarantee this if an old client can still send requests after losing its lease.

## 6. Cancelling Jobs with Cleanup and Graceful Shutdown

Upon receiving a cancel signal, a job should stop accepting new work, terminate or cancel child processes, reclaim temporary resources, and record its status. Cleanup order depends on the job type.

A graceful cancellation flow typically includes:

1. Receive stop signal from the CI runner or orchestrator.
2. Mark the job as not accepting new requests/tasks.
3. Stop load generators, consumers, or child workers.
4. Allow operations currently inside a short critical section to finish if feasible.
5. Delete temporary workspaces/containers/databases or release job-scoped resources.
6. Revoke temporary credentials and wipe sensitive files per policy.
7. Record `cancelled` status, reason, checkpoint, and completed side effects.
8. Exit within the grace period; otherwise, the runner may forcibly kill the process.

Not all cleanup should run on cancellation. For example, deleting already-published artifacts or dropping a production database is not safe cleanup. Cleanup must be strictly scoped to temporary resources owned and unambiguously identifiable by the job.

### Shell Example for Handling Stop Signals

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

WORK_DIR="${RUNNER_TEMP:-/tmp}/build-${CI_JOB_ID:-local}"
mkdir -p "$WORK_DIR"

cleanup() {
  local exit_code=$?
  trap - EXIT
  ./ci/stop-test-workers.sh || true
  rm -rf -- "$WORK_DIR"
  exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

./ci/run-isolated-tests.sh --work-dir "$WORK_DIR"
```

This example illustrates cleanup for a test workspace and worker processes. In real systems, ensure `stop-test-workers.sh` accurately identifies the process group/containers spawned by the job and never touches shared resources. Runners may send `SIGTERM` followed by `SIGKILL` after a grace period; shells, child processes, and executors do not always handle signals identically. Test cancellation behavior on your actual executor.

## 7. Idempotency and Handling Partial Side Effects

A job can be cancelled after a server receives its request but before the client receives the response. On retry, the job does not know whether the prior operation succeeded. Re-executing without controls can create duplicates.

Useful design patterns:

- **Idempotency key:** attach a unique key to a business request; the server returns the prior outcome when receiving the same key instead of executing twice.
- **Transactional write:** update data and job state within the same transaction whenever possible.
- **Outbox pattern:** write outgoing events to an outbox table within the transaction; a worker delivers them asynchronously and marks them processed.
- **Checkpoint:** persist progress so a new job can resume from a safe step.
- **Compensation:** execute a counteracting action when a side effect has occurred and cannot be directly rolled back.
- **Reconciliation:** read actual state from the target system before deciding to retry or continue.

Image publishing example: if the upload finished but the job was cancelled before writing the report, the new job should query the registry by digest and verify the content already exists rather than re-uploading. Do not generate another version or overwrite tags merely because the previous run was marked `cancelled`.

Email sending example: if the provider already accepted the request before the pipeline lost connectivity, cancelling the job does not recall the email. Use an idempotency key or outbox to prevent duplicate sends.

## 8. Locks and Shared Resource Coordination

When multiple jobs can mutate the same target, serialization or locking is required—for example, two pipelines deploying service `orders` to production or two migrations updating a database schema.

A safe lock requires:

- Clear scope: lock by specific service, environment, database, or resource.
- Owner identity: identify which job/run holds the lock.
- Lease/TTL: locks do not persist forever if a worker dies.
- Renewal: an active worker can extend its lease per policy.
- Fencing token: stops an old worker from writing after its lease expires and the lock moves to another worker.
- Owner-checked release: a job must never release another job's lock.
- Timeout/wait policy: defines how long a job waits and what happens when it fails to acquire the lock.

Avoid using a global lock for every pipeline if only specific resources need serialization; that unnecessarily crushes concurrency. Conversely, overly narrow locks can allow two jobs to mutate a shared resource together.

### Concurrency Groups in GitHub Actions

For pull request checks, older runs can be cancelled when a new run for the same PR appears:

```yaml
name: Pull request checks

on:
  pull_request:

concurrency:
  group: pr-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/verify.sh
```

Here, the concurrency group is keyed to the PR number so runs for the same PR supersede one another. Use a different policy for releases/deployments. GitHub Actions concurrency groups cap active/pending runs in the group; a pending run can be replaced when a newer run arrives, and order is not a strict FIFO queue. Thus, this does not guarantee every release executes in order.

For production deployments, you generally should not blindly enable `cancel-in-progress: true`:

```yaml
name: Production deployment

on:
  workflow_dispatch:

concurrency:
  group: deploy-production-orders
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/check-release-is-current.sh
      - run: ./ci/deploy-approved-digest.sh
      - run: ./ci/verify-deployment.sh
```

This group prevents multiple workflows in the same group from running concurrently, yet does not automatically provide a FIFO queue for every release. The job must still verify the release remains current and use the approved artifact digest. If every release must be processed sequentially, use a queue mechanism with matching semantics.

### Auto-Cancel Redundant Pipelines in GitLab CI

GitLab supports marking jobs interruptible and configuring auto-cancel on new commits. Illustrative example:

```yaml
workflow:
  auto_cancel:
    on_new_commit: interruptible

unit_tests:
  stage: test
  interruptible: true
  script:
    - ./gradlew test --no-daemon

build_candidate:
  stage: build
  interruptible: true
  script:
    - ./gradlew assemble --no-daemon

deploy_production:
  stage: deploy
  interruptible: false
  script:
    - ./ci/deploy-approved-digest.sh
```

`interruptible: true` suits jobs that can stop safely, such as tests and temporary builds. The deploy job is marked `false` so auto-cancelling redundant pipelines will not arbitrarily interrupt it once started. Exact behavior depends on the GitLab version and `workflow:auto_cancel` configuration; check the documentation for your running version. Setting `false` does not replace an intentional deployment pause/abort procedure.

## 9. Avoid Mistakenly Cancelling Work with Effects Worth Keeping

Some steps cross a boundary where safe cancellation is no longer possible. Identify the commit point of each operation.

| Action | Boundary to watch | How to handle a new cancel request |
|---|---|---|
| Workspace build | Before uploading/publishing artifacts | Stop process and clean temporary outputs |
| Package publish | Once registry accepts manifests/layers or versions | Inspect status by digest; finalize metadata or mark candidate superseded |
| Release/tag creation | Once tag or release is published | Never delete arbitrarily; deprecate/yank per policy and record audit |
| Database migration | Once transaction/DDL commits or data is altered | Finish safe step, stop at checkpoint, or run compensation/roll-forward |
| Deploy rollout | Once a subset of replicas receives the new version | Pause rollout and assess state; never kill process and abandon runtime state |
| Sending events/payments | Once target system accepts the request | Use idempotency/reconciliation/compensation |
| Backup/restore | While snapshot or restore operation is active | Use stateful control APIs; never delete files actively in use |

An older job that already published an artifact may no longer be deployed, yet the artifact may still need to be retained for auditing or investigation. "Superseded" does not mean "delete immediately." Separate release status from evidence retention.

## 10. Cancelling Dependent Jobs in a Pipeline DAG

Pipelines are typically dependency graphs (DAGs). When an upstream job is cancelled, downstream jobs must be handled according to dependencies and run conditions.

- Downstream jobs requiring upstream outputs should be skipped/cancelled when dependencies become invalid.
- Cleanup or diagnostics-collection jobs may still need to run when upstream jobs fail/cancel.
- Publish/deploy jobs must never run simply via an `always` condition if required gates have not passed.
- Report-aggregation jobs may need to run on `cancelled` status to preserve reasons and diagnostic artifacts.

GitHub Actions example:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/test.sh

  publish:
    needs: test
    if: needs.test.result == 'success'
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/publish.sh

  collect-diagnostics:
    needs: test
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/collect-diagnostics.sh
```

`publish` runs only when `test` succeeds. `collect-diagnostics` can run to gather info after terminal status, though its script must handle cases where workspaces or artifacts do not exist. Never use `always()` on deploy or publish jobs if it can bypass mandatory gates.

## 11. Event-Based vs. State-Based Cancellation

There are two ways to identify stale jobs:

- **Event-based:** when a new event arrives, send cancel signals to older runs in the same group. This is simple and fits PR checks.
- **State-based:** before performing a side effect, the job queries the current source of truth to verify its request remains the accepted request. This is essential when events can arrive late, be duplicated, or run out of order.

For example, the webhook for commit B can arrive before the webhook for commit A even though A was created first. If the system relies solely on event arrival order, job A might be mistakenly treated as newest. State-based freshness uses the authoritative commit/generation to decide accurately.

For deployments, the source of truth may be an approved release record, desired state in a GitOps repository, or a deployment controller. The job must compare against that source right before mutating the target.

## 12. Tracking Cancellation and Stop Reasons

Cancellation needs metadata to distinguish intentional cancellation, timeouts, disconnected runners, and execution failures.

Record:

- Job/run ID, attempt, and commit SHA.
- Related concurrency group or resource lock.
- Cancel reason: superseded, PR closed, manual stop, timeout, dependency cancelled, or policy.
- Who/what condition requested cancellation.
- Signal sent time, process exit time, and cleanup completion time.
- Completed side effects or state requiring reconciliation.
- Temporary artifacts retained/deleted and resources cleaned up.
- Superseding new job if any, along with its revision/generation.

Useful metrics:

- Count of stale jobs cancelled and runner time reclaimed.
- Ratio of cancellations before vs. after starting side effects.
- Time from cancel request to process termination.
- Count of cleanup failures or leaked temporary resources.
- Count of duplicate side effects from retry/cancel races.
- Count of paused/aborted deployments and time to stabilize targets.

If cancellation rates are excessively high, pipelines may be over-triggered, users may be pushing many small commits, or concurrency groups may be defined too broadly. Investigate root causes rather than merely scaling runner capacity.

## 13. Testing Cancellation Policies

Do not stop at checking whether YAML contains `cancel-in-progress: true`. Test actual race conditions and runtime states.

Scenarios to test:

1. Pushing a new commit while old unit tests run: old job stops and new job runs the exact new SHA.
2. Pushing a new commit while a build creates temp files: process stops, workspace cleans up, no partial artifact is published.
3. Cancel arriving immediately after publish finishes: registry retains the digest artifact and release record reflects actual state.
4. Two jobs deploying the same service: only one enters the critical section; the other waits or is marked superseded per policy.
5. Worker loses lease yet keeps running: fencing token causes stale writes to be rejected.
6. Cancel during migration: system stops at a safe checkpoint or completes/compensates per design.
7. Runner loses connectivity: controller reconciles state without assuming the job cleaned up.
8. Pull request closed: test jobs stop while required audit/diagnostics jobs still save results.
9. New job cancelled after superseding an old job: policy defines whether to re-trigger so no valid job is left missing.
10. Duplicate cancel or duplicate webhook delivery: system handles idempotently without duplicate side effects.

## 14. Common Anti-Patterns

- **Enabling `cancel-in-progress` on every workflow:** can interrupt deployments, migrations, or publishes mid-flight.
- **Treating cancel as rollback:** the process stops, yet already-executed side effects persist.
- **Checking freshness only at job start:** the job can go stale before writing data or deploying.
- **Using branch names instead of commit SHAs:** old jobs can check out or publish undetermined content.
- **Relying on locks without fencing:** old workers can keep writing after their lease expires.
- **Cleanup deleting all outputs:** can wipe already-published artifacts or required evidence.
- **Not stopping child processes:** the shell exits while test servers or load generators keep running.
- **Marking every job interruptible:** the orchestrator may cancel an unsafe step.
- **Using `always()` for downstream side effects:** publish/deploy jobs can execute after gates were cancelled or failed.
- **Treating concurrency groups as FIFO queues:** pending runs can be replaced; ordering is not guaranteed.
- **Not reconciling state after timeouts/cancellations:** the system does not know whether the target accepted the request.
- **Not logging cancellation reasons:** makes distinguishing failed pipelines from legitimately superseded work difficult.

## 15. Checklist for Designing Stale-Work Cancellation

Before enabling auto-cancel, check:

1. What state does the job represent, and when does it become stale?
2. Do freshness identifiers explicitly use commit SHA, run ID, attempt, and target?
3. At which stages can the job cancel safely? Where are the commit/side-effect points?
4. Is the policy latest-wins, queue/serialize, or deduplicate, and why?
5. Does the job re-verify freshness immediately before side effects?
6. Do operations with side effects have idempotency keys, checkpoints, or compensation?
7. Do shared resources have proper locks, leases, and fencing?
8. Does the runner terminate child processes and clean temporary resources within the grace period?
9. Are published artifacts and audit evidence preserved under proper retention?
10. Do downstream jobs have clear skip/cancel conditions, and are diagnostics collected when needed?
11. Do deployments/migrations have dedicated pause/abort procedures instead of arbitrary cancellation?
12. Are cancellation reason, actor, timestamps, and side effects logged?
13. Have races among cancellations, retries, delayed webhooks, and lease losses been tested?
14. Are reclaimed runner time, cleanup failures, and duplicate side effects measured?

Cancelling stale work keeps CI/CD responsive and saves resources, yet is only safe when you understand the job's state and the effects it has already produced. Use latest-wins for discardable checks, queues/locks for shared resources, and freshness/idempotency/fencing for actions with side effects. When stale jobs stop at the right moment, newer pipelines can move forward without leaving half-finished state or overwriting newer outcomes with obsolete work.
