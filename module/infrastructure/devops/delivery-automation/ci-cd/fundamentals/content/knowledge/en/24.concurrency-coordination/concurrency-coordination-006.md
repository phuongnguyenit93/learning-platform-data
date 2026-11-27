# Designing Locks and Timeouts with Failure-Safe Release

A pipeline may start two deployments simultaneously, two migrations may alter the same schema concurrently, or multiple workers may process the same data partition. Without coordination, processes can overwrite state, create duplicate resources, hold database locks for too long, or let an older operation overwrite a newer release.

Locks restrict authority to perform an operation on a shared resource. However, lock design is not just "acquire lock, then run." A reliable protocol must define atomic acquisition, maximum wait time, ownership duration, renewal, safe release on both success and failure, and how to stop an old process from continuing to write after losing authority.

In CI/CD, failures can occur at any moment: cancelled jobs, disconnected runners, killed processes, database restarts, network partitions, or pipeline timeouts. Therefore, locks must be designed for **bounded waiting, explicit ownership, safe release, and verifiable recovery**.

This article focuses on lock lifecycles and timeouts in deployment, migration, and data jobs. Topics include lock scope, acquire/release, timeouts, leases, heartbeats, fencing tokens, failure handling, database and CI examples, and testing interrupted processes.

## 1. Why Are Locks Needed in CI/CD?

A pipeline can run from many triggers: pushes, pull requests, schedules, tag releases, or manual triggers. Two runs can target the exact same resource:

- Two workflows deploying the same service to production simultaneously.
- A new migration starting before the previous migration finishes.
- Two jobs updating the same configuration file or release state concurrently.
- Multiple workers processing the same partition in a data table.
- An older pipeline continuing to run after a newer pipeline has already started.
- A rollback job and a new deployment job modifying an environment's state at the same time.

Not all concurrent work is dangerous. Builds and unit tests in separate workspaces can usually run in parallel. Conflicts arise when multiple processes modify the same resource or perform operations where order matters.

Locks help enforce invariants such as:

- Only one migration coordinator modifies the schema at a time.
- Only one deployment operation controls a service/environment.
- At most one worker is permitted to commit to a partition at a time.
- An older release cannot overwrite a newer release.
- Only the current owner has authority to release the lock.

Locks are a coordination mechanism. They do not replace transactions, idempotency, authorization, or actual state checks.

## 2. Defining Resources and Lock Scope

Before picking a technology, identify exactly which resources need protection and which operations can conflict.

### System-Wide Locks

Only one task across the entire system is permitted to run. Suitable for rare, broad-impact, or indivisible operations such as restructuring shared infrastructure.

The downside is reduced concurrency. One slow task blocks every other task even when they do not conflict.

### Per-Job Locks

Only prevents two instances of the same job type from running concurrently—for example, allowing only one `nightly-index-rebuild` run in an environment.

This scope is simple, yet two differently named jobs can still modify the same resource. Map out the relationship between job names and actual underlying resources.

### Per-Resource or Per-Environment Locks

Lock by service/environment, database/schema, registry namespace, or a specific resource. Examples:

~~~text
deploy:order-api:production
migration:orders-db:public-schema
backfill:customer:partition-03
~~~

Two jobs sharing a resource key contend for the lock; independent resources continue running in parallel.

### Per-Partition or Per-Tenant Locks

For large datasets, scope can be split by tenant, shard, date, or primary key range—provided partitions are genuinely independent in data and side effects.

Never choose a lock key based solely on job name if two distinct jobs still update the same table or business entity.

### Scope Selection Rule

Choose the smallest scope that still preserves the invariant. If a lock is too broad, throughput drops and queues lengthen. If a lock is too narrow, two operations can mutate shared state inconsistently.

A lock requires a clear namespace—for example, project, service, environment, and resource. Naming must be deterministic across runs and contain no secrets.

## 3. Properties of a Safe Lock Protocol

A lock protocol should answer the following questions:

| Property | Question to answer |
|---|---|
| Mutual exclusion | Can two owners be granted the lock simultaneously? |
| Ownership | Who holds the lock and what is the proof of ownership? |
| Atomic acquire | Are checking availability and claiming the lock a single atomic operation? |
| Bounded wait | What is the maximum time a worker will wait? |
| Lease/expiry | When an owner disappears, is authority reclaimed? |
| Renewal | How does the owner extend the lock? |
| Safe release | Can an old owner delete a new owner's lock? |
| Fencing | Can an old process write after losing the lock? |
| Recovery | After a crash, how does a new worker determine job progress? |
| Observability | Can operators see who holds the lock, wait duration, and why? |

Mutual exclusion is only part of the picture. In distributed systems, a lease can expire while the old process is still alive. If the write target does not verify current authority, two processes can still mutate concurrently even after the lock service grants the lock to a new owner.

## 4. Distinguishing Locks, Leases, Transactions, and Semaphores

These mechanisms are often used together, yet they are not the same.

- **Lock:** exclusive or coordinated access authority over a resource.
- **Lease:** a time-bounded lock; ownership expires if not renewed.
- **Transaction:** a group of data mutations committed or rolled back within a database boundary.
- **Semaphore:** a cap on the number of processes permitted to use a resource simultaneously.
- **Mutex:** an exclusive lock allowing only a single owner at a time.
- **Queue:** ordering work rather than having workers contend directly for a lock.

For example, a deployment might use a semaphore capping concurrent production deployments at one, while a schema migration uses an exclusive mutex. A data job might use a lease so a crashed worker does not hold the lock forever.

Never hold a long-lived database transaction in place of a lease for tasks lasting hours. Transactions should remain short to reduce lock contention and database pressure.

## 5. Lock Acquisition Must Be Atomic

A common bug is splitting acquisition into two separate steps:

1. Check whether the lock exists.
2. If not, create the lock.

Two workers can both check, both see "does not exist," and both create the lock. That is a race condition.

Acquisition must use an atomic primitive provided by the coordination system, such as:

- A unique constraint or conditional update in a database.
- A row lock inside a transaction.
- `SET` if-not-exists with expiry in Redis.
- Compare-and-set in a coordination store.
- Scheduler resource groups or concurrency controls.

### Example Claiming a Lock Record in a Database

Suppose a lock table has one row per resource key with a unique constraint on `lock_key`. A worker can use a conditional update:

~~~sql
UPDATE job_locks
SET owner_id = :owner_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
    fencing_token = fencing_token + 1
WHERE lock_key = :lock_key
  AND lease_until < CURRENT_TIMESTAMP
RETURNING owner_id, lease_until, fencing_token;
~~~

If no rows are returned, the lock has not expired or is held by another owner. Initial creation of the lock row must use an insert backed by a unique constraint with conflict handling. The entire claim must run inside an appropriate transaction.

Never read `lease_until` and then update it in two independent requests without compare-and-set or locking, as another worker can claim ownership between the two steps.

## 6. Wait Times During Acquisition

A worker must never wait indefinitely for a lock. Every acquire request needs an explicit timeout or deadline.

Example policy:

- Wait at most 30 seconds to acquire the deploy lock.
- Poll every 1–3 seconds with jitter.
- On deadline expiration, return `LOCK_BUSY` or `ACQUIRE_TIMEOUT`.
- Record the current owner and wait duration if available.
- Never start operations without confirming acquisition succeeded.

### Fixed Wait or Backoff?

Polling every 100 ms can overload the lock service when many workers wait simultaneously. Waiting too long at fixed intervals increases response latency.

Use exponential backoff and jitter:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait = random(0, delay)
~~~

For example, start at 250 ms, ramp up to 3 seconds, with a total wait cap of 30 seconds. Actual values depend on latency, worker count, and SLAs.

If the system supports notifications or blocking acquire with a timeout, prefer that over continuous polling.

### Choosing Behavior When a Lock Is Busy

Depending on job type, when a lock is busy you can:

- Wait within the deadline and retry.
- Place the work into a queue.
- Skip duplicate triggers if an equivalent run is already active.
- Fail fast so the scheduler reschedules later.
- Surface the waiting state for operator visibility.

Waiting is not always right. A new release may need to supersede an older waiting release, though cancellation must respect policy and the older operation's state.

## 7. Distinguishing Timeout Types

There is no single timeout covering the entire lock lifecycle.

| Timeout | Meaning | Example |
|---|---|---|
| Acquire timeout | Maximum time spent waiting for the lock | 30 seconds |
| Lease duration | Duration an owner holds authority before renewal is required | 60 seconds |
| Heartbeat interval | Interval between lease renewals/keepalives | 20 seconds |
| Operation timeout | Maximum duration for a single protected operation | 20 minutes |
| Query timeout | Maximum duration for a single database query | 30 seconds |
| Job deadline | Total wall-clock time a job is permitted to run | 45 minutes |
| Shutdown grace period | Soft stop window to finish the current batch | 30 seconds |
| Cleanup timeout | Time allocated for lock release/cleanup | 5 seconds |

Numbers are illustrative. Configure leases safely longer than heartbeat intervals with headroom for jitter and network delays. Meanwhile, job deadlines must bound total runtime to avoid infinite retries.

### Acquire Timeout Differs from Lease Duration

Acquire timeout bounds only the wait before acquiring the lock. Lease duration bounds ownership duration after acquisition succeeds.

A worker might wait 20 seconds, receive a 60-second lease, and process for 10 minutes by renewing periodically. Never infer allowed job runtime from acquire timeout.

### Job Deadline Differs from Query Timeout

Job deadline bounds the entire process. Query timeout bounds one SQL statement. If query timeout exceeds the job's remaining time, a query can keep running after the caller gives up unless cancellation propagates properly.

Propagate remaining deadlines to each step and never start a new operation without enough time left to finish or stop safely.

## 8. Leases and Heartbeats

Leases enable reclaiming authority when an owner dies or becomes unreachable. A worker receives a time-limited lease and must renew before expiration.

Example:

~~~text
Lease duration: 60 seconds
Heartbeat interval: 20 seconds

t=00  Worker A acquires lease
t=20  A renews lease
t=40  A renews lease
t=60  A renews lease
...
~~~

Renewal must validate the owner ID or token. A worker must never renew a lock that already belongs to another worker.

If renewal fails:

1. Stop claiming new work.
2. Do not start new write transactions.
3. If inside a transaction, finish or roll back at a safe boundary.
4. Mark the operation as needing reconciliation.
5. Never keep writing under the assumption the lease is still valid.

Heartbeats only prove the worker can send signals; they do not prove work is making progress. Also record progress markers, committed batches, and last commit timestamps to detect hung workers.

## 9. Fencing Tokens Stop Stale Owners from Writing Data

Lease expiration does not automatically terminate the old process. A worker can pause or lose network connectivity and later resume after another worker acquired the lock.

For example:

1. Worker A receives a lease with token 101.
2. A hangs longer than the lease duration.
3. The lease expires; Worker B acquires the lock with token 102.
4. A wakes up and sends a write command with token 101.
5. The target system rejects token 101 because the newest token is 102.

A fencing token is a monotonically increasing sequence number issued whenever a new owner acquires the lock. The write target must validate the token; merely logging the token provides no protection.

### Example Fencing Token Check

~~~sql
UPDATE deployment_state
SET version = :new_version,
    last_fencing_token = :token
WHERE service_name = :service
  AND environment = :environment
  AND COALESCE(last_fencing_token, 0) < :token;
~~~

If 0 rows are updated, the token is stale or the resource does not exist. The caller must read state and stop writing as a valid owner.

Design token issuance from a monotonic source. Never use worker-generated timestamps as fencing tokens, as clocks across machines can drift.

## 10. Safe Lock Release

Once work completes, the owner must release the lock. Release must verify ownership to prevent an old worker from deleting a new worker's lock.

### Never Delete a Lock Solely by Resource Key

Suppose A holds a lock, A's lease expires, and B acquires the new lock. If A wakes up and deletes the lock by `lock_key` alone, A can mistakenly delete B's lock.

Every release operation must compare the owner token:

~~~sql
DELETE FROM job_locks
WHERE lock_key = :lock_key
  AND owner_id = :owner_id
  AND fencing_token = :fencing_token;
~~~

If no rows are deleted, the caller no longer holds the lock. This is not necessarily an error; the lease may have expired or another worker may have taken over.

### Redis Locks

With Redis, a common pattern is `SET key token NX PX ttl` to create a time-bounded lock with a random owner token. On release, execute a Lua script checking the current token before calling `DEL`:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
~~~

Never call `DEL` directly by key alone. Checking the owner token prevents accidentally deleting another process's lock.

Redis lock patterns must be evaluated alongside persistence, replication, and failover settings. In high-consistency environments, a Redis lock does not automatically provide fencing for databases or cloud APIs. Write targets still need version/token checks or a coordination mechanism with matching guarantees.

## 11. Releasing Locks on Error: `finally` and Cleanup

For live processes, release should sit inside a cleanup block guaranteed to run whether the operation succeeds or throws an exception.

Java example using `AutoCloseable`:

~~~java
try (LockHandle lock = lockProvider.acquire(
        "deploy:order-api:production",
        Duration.ofSeconds(30),
        Duration.ofSeconds(60))) {

    deploymentService.applyDesiredVersion(
        "order-api",
        "production",
        "sha256:abc123"
    );

    deploymentService.verifyRollout("order-api", "production");
}
~~~

`LockHandle.close()` must release by owner token and handle cases where the lease was already lost. `close()` must never delete another owner's lock.

If `acquire` fails to obtain the lock, never execute the protected body. Use exceptions or an `Optional`/`Result` return type to distinguish acquired from timed out.

### Cleanup Must Not Mask the Original Error

If deployment fails and lock release also fails, logs must preserve both errors. Never let a cleanup exception silently swallow the original exception without recording the primary cause.

Handling pattern:

~~~java
LockHandle lock = lockProvider.acquire(...);
try {
    runProtectedOperation();
} finally {
    try {
        lock.release();
    } catch (Exception releaseError) {
        logger.error("Could not release lock", releaseError);
    }
}
~~~

This is a conceptual example; in production code, ensure acquisition succeeded before entering `try/finally` and record cleanup status for reconciliation.

### `finally` Cannot Handle Every Crash Mode

`finally` runs only when the runtime has a chance to unwind the stack. It is not guaranteed to run when:

- The process receives `kill -9` or is forcibly terminated.
- The machine loses power.
- The container runtime or host crashes.
- The JVM halts abnormally.
- A network partition prevents the process from reaching the lock service.
- The OS stops the process without a grace period.

Therefore, active cleanup must be paired with lease expiry, connection cleanup, and recovery processes.

## 12. Releasing Locks When Database Connections Drop

For transaction-scoped locks, the database releases them automatically on transaction commit/rollback or session end. For session-scoped advisory locks, locks persist until explicitly unlocked or the session closes.

This is critical when using connection pools:

- Never return a connection to the pool while it still holds a session lock.
- Always release session locks in cleanup.
- If release fails, reset or discard the connection instead of reusing it blindly.
- Never assume a client-side connection timeout means the server closed the session.
- Monitor active sessions and lock holders when jobs hang.

If a network partition disconnects a client while the database keeps the session open, a session lock can persist until the server detects the dead connection or a TCP timeout fires. Configure keepalives and timeouts at appropriate layers, but never rely solely on network timeouts for instant recovery.

For long-running tasks, a lock record with leases and heartbeats is usually far easier to observe than keeping a database transaction open for hours.

## 13. Locks in PostgreSQL

PostgreSQL provides row-level locks, table-level locks, and advisory locks.

### Transaction-Scoped Advisory Locks

Example:

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(202611, 6) AS acquired;

-- Execute protected mutations only if acquired = true.

COMMIT;
~~~

The lock releases when the transaction ends. Suitable for short operations fitting inside one transaction. Never hold a transaction open across a long backfill job solely to keep an advisory lock.

### Session-Scoped Advisory Locks

Session locks can span multiple transactions:

~~~sql
SELECT pg_try_advisory_lock(202611, 6);
-- Protected work
SELECT pg_advisory_unlock(202611, 6);
~~~

Ensure unlocking occurs on the exact same session. With connection pools, sessions get reused, so cleanup must be airtight and locked connections must never re-enter the pool.

### Row Locks for Job Control

You can lock a job record row using `SELECT FOR UPDATE` in a short transaction to transition its state from `READY` to `RUNNING`. After recording owner/lease, commit the transaction and process batches outside it. Each batch opens its own transaction to write data and checkpoints.

Avoid holding row locks while calling external services or waiting for human approval.

## 14. Distributed Locks and TTL Limitations

Distributed locks are useful when workers run across multiple machines. A lock service can store the owner and lease expiration. However, TTL is only a delayed reclamation mechanism; it does not halt an old process.

Risks to evaluate:

- Worker pauses longer than TTL.
- Network partition between worker and lock service.
- Clock drift if expiry relies on client time.
- Lock service failover losing the most recent update.
- Old worker continuing to send requests to the target system.
- Delayed release arriving after a new owner already acquired the lock.

To increase safety:

- Use atomic primitives from the lock service.
- Use a unique owner token per acquisition.
- Conditionally renew by owner.
- Conditionally release by owner.
- Enforce fencing tokens at the target system whenever possible.
- Keep protected operations bounded in duration.
- Reconcile resource state after lease loss.

Never claim that a single Redis lock or TTL guarantees absolute mutual exclusion across all failure modes. Guarantee strength depends on lock service architecture and whether the write target enforces write authority.

## 15. Preventing Deadlocks via Lock Acquisition Ordering

Deadlocks occur when two transactions hold different locks and wait on each other's lock.

Example:

~~~text
Transaction A              Transaction B
-------------              -------------
Lock resource 1            Lock resource 2
Wait for resource 2        Wait for resource 1
       |                          |
       +---------- DEADLOCK ------+
~~~

Ways to reduce deadlocks:

- Acquire multiple locks in the same global order across the system.
- Keep transactions short.
- Never wait for user approvals or external API calls while holding row locks.
- Lock only the exact resources required.
- Use timeouts to detect excessive waits.
- Retry transactions aborted by the database due to deadlock if the entire operation can safely rerun.

If a job needs both a service lock and a database lock, define a fixed order—for instance, acquire the deployment lock first, then open a short DB transaction. Every job must obey the same order to prevent circular waits.

## 16. Cancellation and Graceful Shutdown

When a pipeline is cancelled, the runner normally sends a stop signal first before terminating the process after a grace period.

Jobs should handle graceful shutdown:

1. Stop accepting new work.
2. Do not start new batches.
3. Finish or roll back the current transaction.
4. Persist checkpoints after data commits.
5. Record `PAUSED`/`INTERRUPTED` status.
6. Release the lock if still the valid owner.
7. Close connections and resources.
8. Exit before the grace period expires.

If time runs out, let the lease expire and let a recovery worker take over. Never try to hold a lock indefinitely simply because cleanup has not finished.

### Cancelling a Job Does Not Mean the Operation Stopped

A CI job can be cancelled while the backend server continues processing the request—for example, a deploy command already sent to the Kubernetes API or a deployment service. After cancellation, query operation status and observed state before re-running.

Never rely solely on CI job status to conclude a lock or side effect has been cleared.

## 17. Locks in GitHub Actions and GitLab CI

CI platforms provide concurrency features at the workflow or resource level. These are useful for coordinating jobs routed through the same platform, but do not replace database/service locks if external systems also access the resource.

### GitHub Actions Concurrency Groups

Example:

~~~yaml
name: deploy

on:
  push:
    branches: [main]

concurrency:
  group: deploy-order-api-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-24.04
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh
~~~

Concurrency groups restrict workflows sharing the same group. For production deployments, `cancel-in-progress: false` is usually safer if aborting an active workflow could leave unclear state. Queuing and pending-run replacement depend on platform policy; do not treat groups as distributed locks across repositories or systems outside GitHub.

When strict serialization and resource state validation are required, the deployment service or database should still maintain its own locks/operation state.

### GitLab `resource_group`

Example:

~~~yaml
deploy_production:
  stage: deploy
  resource_group: order-api-production
  script:
    - ./scripts/deploy.sh
~~~

Resource groups serialize jobs sharing the same `resource_group` within a GitLab project. Configure process mode and verify execution ordering to fit your needs. If jobs arrive from other projects or outside GitLab, `resource_group` does not protect against those sources.

## 18. When a Lock Expires or Cannot Be Released

Never manually delete a lock record just because an old job no longer appears active on a dashboard. Verify:

- Current owner ID and run ID.
- Lease expiry and latest heartbeat.
- Whether the process/runner is still active.
- Whether any server-side transactions or requests are still running.
- Latest fencing token.
- How far resource state has changed.
- Whether the old operation can be resumed or reconciled.

Once confirmed that the owner is dead and the lease has expired, a recovery worker can atomically claim a new lock with a higher token, then inspect checkpoint/operation state before continuing.

If a lock has no lease, administrative intervention may be required to reclaim it. Force-unlocking must include an audit record, reason, and before/after resource verification; otherwise, an old worker may keep running and cause split-brain.

## 19. Observability for Locks and Wait Times

Locks are hard to operate if you only see a job stuck in "pending." Log enough metadata to identify owners and causes of contention.

Every acquisition should log:

- Lock key or resource scope.
- Owner ID, run ID, and attempt.
- Request/acquire/release timestamps.
- Acquire wait duration.
- Lease expiry and heartbeat timestamps.
- Fencing token.
- Renewal/release outcomes.
- Protected operation ID.
- Reason for release or lease loss.
- Job deadline and remaining time.

Useful metrics:

| Metric | Meaning |
|---|---|
| `lock_acquire_wait_seconds` | Time spent waiting to acquire |
| `lock_acquire_failures_total` | Count of failed acquisitions |
| `active_locks` | Number of currently held locks |
| `lock_lease_renew_failures_total` | Count of failed lease renewals |
| `lock_expired_total` | Count of expired leases |
| `lock_release_failures_total` | Count of failed releases |
| `lock_contention_total` | Count of lock contentions |
| `lock_holder_duration_seconds` | Duration owners hold locks |
| `stale_owner_write_rejections_total` | Count of stale-owner writes rejected by fencing |
| `job_deadline_exceeded_total` | Count of jobs exceeding their deadline |

Never log secrets or authentication tokens. Owner tokens may be logged as non-sensitive IDs/fingerprints for investigation.

## 20. Testing Failure Paths of a Lock Protocol

A lock protocol must be tested on failure scenarios, not only the happy path.

### Acquisition Tests

- Two workers acquire the same key simultaneously: only one succeeds.
- Two workers acquire different keys: neither blocks the other.
- Lock is busy: acquire times out accurately at the deadline.
- Lock record does not exist yet: racing inserts never produce two owners.
- Worker disconnects during acquire: queries state before resending if the result is unclear.

### Lease and Fencing Tests

- Worker renews before expiration: lease extends.
- Worker renews after ownership changed: rejected.
- Lease expires and new worker receives a higher token.
- Old worker wakes up: target system rejects the stale token.
- Old owner releases: does not delete the new owner's lock.

### Release and Crash Tests

- Operation succeeds: release executes.
- Operation throws an exception: cleanup still runs.
- Release service temporarily errors: error is logged and recovery works.
- Process is hard-killed: lease expires and a new worker takes over.
- Database connection closes: transaction locks release per DB semantics.
- Session locks with connection pools: connections never return to the pool while holding a lock.

### Duration Tests

- Lock wait exceeds timeout.
- Query exceeds statement timeout.
- Job deadline hits mid-batch.
- Heartbeats are delayed.
- Network partition lasts longer than lease.
- Graceful shutdown runs out of time.
- Multiple jobs retrying acquire concurrently cause contention.

Tests must confirm that only one valid owner can write, locks are never deleted mistakenly, jobs never wait indefinitely, and resources end in a reconcilable state.

## 21. Common Anti-Patterns

| Anti-pattern | Consequence | Remedy |
|---|---|---|
| Splitting check-then-set into two operations | Two workers both claim the lock | Use atomic acquire/compare-and-set |
| Waiting indefinitely for a lock | Jobs hang and tie up runners | Enforce acquire timeout/deadline |
| TTL too short | Lease expires while owner is still processing | Measure batch duration and renew appropriately |
| TTL too long | Slow recovery after crashes | Choose reasonable leases with heartbeats |
| Releasing solely by lock key | Old owner deletes new owner's lock | Compare owner token/fencing token |
| Relying on `finally` for every crash | Hard-killed processes never release | Pair with lease expiry and recovery |
| Holding DB transactions for hours | Blocking, deadlocks, massive rollbacks | Short transactions, checkpoints, and leases |
| No fencing | Old workers write after losing lease | Validate tokens at write targets |
| Using CI concurrency as the sole lock | Jobs outside CI can still conflict | Protect at the service/database layer |
| Force-deleting lock records unverified | Split-brain and data overwrites | Verify owner, operation, and resource |
| Cleanup masking original error | Hard to diagnose root cause | Log operation failures and release failures separately |
| Treating heartbeats as progress | Hung workers still keep locks | Track batch/commit progress |
| Retrying acquire too aggressively | Lock service overload | Use backoff, jitter, and queues |

## 22. Safe Lock Design Checklist

### Scope and Ownership

- [ ] Resources and invariants requiring protection are identified.
- [ ] Lock scope is chosen by job/resource/environment/partition.
- [ ] Lock keys have a stable namespace.
- [ ] Acquisition is atomic.
- [ ] Ownership uses explicit owner IDs and tokens.
- [ ] No write path bypasses the lock protocol when exclusivity is required.

### Timeouts and Leases

- [ ] Acquire timeouts and busy-lock policies are defined.
- [ ] Distributed workers use lease durations.
- [ ] Heartbeat intervals fit lease durations and network delays.
- [ ] Job deadlines, query timeouts, and shutdown grace periods exist.
- [ ] No unbounded waits or infinite retries.
- [ ] Renewals succeed only for the current owner.
- [ ] Fencing tokens/version checks exist at write targets.

### Release and Recovery

- [ ] Release checks owner tokens.
- [ ] Cleanup runs on both success and exceptions.
- [ ] Release failures do not hide original errors.
- [ ] Lease expiry or reclamation mechanisms handle dead processes.
- [ ] Connection pools never reuse sessions still holding locks.
- [ ] Reconciliation procedures run before force-unlocking.
- [ ] New workers inspect operation/checkpoint state before resuming.

### Operations and Testing

- [ ] Lock key, owner, run ID, wait duration, and fencing token are logged.
- [ ] Metrics cover acquire wait, lease expiry, and renew/release failures.
- [ ] Simultaneous acquisition by two workers is tested.
- [ ] Old owner reviving after lease expiry is tested.
- [ ] Process kills and database/network failures are tested.
- [ ] Deadlocks, timeouts, and graceful shutdowns are tested.
- [ ] Auditing exists for force-unlock actions.

## Conclusion

A lock is only useful when its ownership and lifecycle are clearly defined. Scope locks to the resource needing protection, acquire atomically, bound wait times, use leases and heartbeats for distributed workers, and validate fencing tokens at write targets so stale owners cannot keep mutating state. Releases must verify owner tokens and execute in cleanup wherever possible; lease expiry and recovery handle dead processes or lost connections. Combined with timeouts, short transactions, graceful shutdown, observability, and failure-path testing, pipelines can recover from faults without holding locks forever or deleting another process's lock.
