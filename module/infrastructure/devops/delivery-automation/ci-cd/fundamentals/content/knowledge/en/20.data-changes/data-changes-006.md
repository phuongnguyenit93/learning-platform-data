# Controlling Locking, Duration, and Rerunability of Data Tasks

A data task may run for seconds or for many hours. It may read millions of records, transform data, write to a target table, update indexes, or sync to another system. Meanwhile, a scheduler might trigger the next run, an operator might click rerun, a runner might be terminated, or the database connection might drop right after a transaction commits.

Without concurrency control, two runs can process the same data simultaneously, overwrite results, or hold locks long enough to stall the system. Without duration control, a job can wait indefinitely for a lock, overrun a maintenance window, or exhaust resources. Without designing for rerunability, error recovery can create duplicate records, drop rows, or leave corrupt state.

In CI/CD and data operations, three mechanisms must be designed together:

- **Locking:** defines who is permitted to process a data scope or task at a given time.
- **Duration:** bounds wait time, execution time, lock hold duration, and completion deadlines.
- **Rerunability (rerun/resume):** ensures a task can resume or re-execute without producing erroneous side effects.

This guide covers choosing lock scopes, managing leases and fencing tokens, batching, checkpointing, handling timeouts, designing safe queries, and operating recoverable data jobs.

## 1. Identifying risks of data tasks

Data tasks appear across many stages of the CI/CD lifecycle:

- Schema migrations before or after application deployment.
- Data backfills for new columns or structures.
- Data synchronization across databases, data warehouses, and external systems.
- Reindexing, rebuilding materialized views, or generating reports.
- Queue and event processing.
- Purging expired records or archiving historical data.
- Retrying failed batches or reprocessing historical data.

A task can encounter these situations:

| Situation | Risk |
|---|---|
| Two schedulers trigger the same job | The same records are processed concurrently |
| Operator clicks rerun while old job still runs | Two processes contend for resources |
| Worker dies mid-write | Only partial work completes |
| Connection drops after database commit | Caller does not know whether data committed |
| Transaction holds locks too long | Other requests block, deadlock, or time out |
| Job exceeds maintenance window | Impacts peak traffic or the next release |
| Checkpoint updates before data | Subsequent run skips uncommitted data |
| Checkpoint updates after data non-atomically | May reprocess duplicates if interrupted between steps |
| Lease expires while old worker stays alive | Two workers mutate the same scope concurrently |

A solid design must answer: which scope requires exclusivity, how long locks persist, what happens when a worker dies, and how the next run determines remaining work.

## 2. Distinguishing locks, transactions, and checkpoints

These three mechanisms relate closely yet solve different problems.

**Locks** control concurrent access. For example, only one worker processes partition `orders-2026-11`.

**Transactions** guarantee that a group of data operations commits or rolls back within boundaries supported by the database. Transactions prevent partial writes inside the transaction scope, yet do not automatically stop another logical job from running in parallel unless both contend on the same lockable resource.

**Checkpoints** record durable progress so a task can resume after interruption. Checkpoints must reflect completed data, not merely data read.

| Mechanism | Question answered | Example |
|---|---|---|
| Lock | Who may process this scope right now? | Job-level or partition-level lock |
| Transaction | Which changes must succeed together? | Writing target and marking source in one transaction |
| Checkpoint | How far has completion reached? | Last committed batch |
| Idempotency | Does reprocessing identical input create duplicate effects? | Upsert by business key |
| Timeout/deadline | How long may the task wait and run? | 10-second lock wait, 30-minute job deadline |

Do not use a global lock as a substitute for transactions, nor use checkpoints while assuming two workers cannot run concurrently. Each mechanism must operate in its proper scope.

## 3. Choosing the right lock scope

Overly broad locks hurt parallelism; overly narrow locks may fail to protect data invariants.

### Job-wide lock

Only one instance of a logical job runs at a time. Suitable when the job modifies a shared dataset whose parts cannot be partitioned independently.

Example: allowing only one `rebuild-customer-index` run at a time within an environment.

The advantage is simplicity and strong protection. The drawback is that one slow partition blocks the entire job even when other parts do not conflict.

### Resource or dataset lock

The lock binds to the modified resource—such as a database, table, tenant, or data category. This prevents incompatible tasks from modifying the same resource concurrently.

For instance, `customer-backfill` and `customer-deduplicate` may share a dataset lock because they mutate the same rows, whereas `invoice-export` may run independently if reading a snapshot.

### Partition or shard lock

Split data into independent ranges and grant separate locks per range:

- By tenant.
- By day or month.
- By hash bucket.
- By region or shard.
- By primary key range.

For example, worker A processes tenants 1–100 while worker B processes tenants 101–200. If data and side effects are genuinely independent, both workers run in parallel.

### Business key lock

For tasks touching a single business entity, lock by customer ID, account ID, or order ID. Explicitly identify which operations must share the same lock to protect invariants.

Do not lock on different technical IDs if two operations can still update the same business entity.

### Scope selection matrix

| Scope | Parallelism | Best suited when |
|---|---|---|
| System-wide | Low | Exclusive tasks with broad blast radius |
| Per job | Medium | Same-type runs must not overlap |
| Per dataset/table | Medium | Multiple jobs may conflict on shared data |
| Per partition/tenant | Higher | Data divides cleanly with explicit boundaries |
| Per record/business key | High | Task processes independent entities |

Start from the invariant that needs protection, then pick the smallest lock scope that still preserves that invariant. Never shrink lock scope solely for throughput if doing so breaks consistency.

## 4. Common types of locks

### Row locks and table locks in databases

Databases provide row locks, table locks, or internal lock levels. These protect data mutations inside transactions.

For example, a transaction can lock a job-control record before transitioning status from `READY` to `RUNNING`. Once the transaction ends, the lock releases.

The benefit is tying lock lifetime to the transaction so the database cleans up automatically on connection drop or rollback. The limitation is that long transactions hold many locks, causing blocking, deadlocks, and heavy database pressure.

### Advisory locks

Some databases support advisory locks: the application defines a logical lock via a number or string mapped to a number. These help coordinate jobs that do not map cleanly to a single data row.

For instance, PostgreSQL offers session-level and transaction-level advisory locks. Transaction-scoped advisory locks release when the transaction ends; session-scoped locks bind to the session and require care with connection pools since connections get reused.

Advisory locks only work if every participating worker honors the same locking protocol. They do not automatically block another application writing to the table without acquiring that lock.

### Distributed locks

Distributed locks coordinate workers across multiple hosts or nodes. Locks can reside in a database, Redis, a coordination service, or an orchestration system.

Understand clearly:

- Atomic acquisition semantics.
- Lease duration and renewal behavior.
- Behavior during network partitions.
- Owner identification.
- Preventing a stale owner from writing after its lease expires.
- Releasing the lock when the job finishes or cancels.

A distributed lock is only safe when both the protocol and the target system enforce write authorization. Holding a Redis lock while the database never checks owner or fencing tokens still allows a stale worker to write after losing its lease.

### Scheduler locks or concurrency controls

Some schedulers and CI platforms provide job concurrency controls, such as concurrency groups, resource groups, or worker limits. These help prevent duplicate triggers from the same scheduler.

However, they only protect jobs launched through that same coordinator. An operator running a manual script or another system hitting the same database can still conflict. Critical invariants must also be enforced at the data layer or owning service.

## 5. Lock acquire, renew, and release lifecycle

A locking protocol must specify the full lifecycle.

~~~text
             Request lock
                  |
                  v
          +---------------+
          | Acquire result|
          +-------+-------+
                  |
          +-------+-------+
          |               |
       Granted          Busy
          |               |
          v               v
   Start work       Wait / skip / queue
          |
          v
   Renew if needed
          |
      +---+---+
      |       |
   Renew OK  Lease lost
      |       |
      v       v
   Continue  Stop writes
      |
      v
  Commit work
      |
      v
 Release lock
~~~

### Acquire

Acquisition must be atomic. Two workers requesting the same lock must never both receive success.

If the lock is busy, define a clear policy:

- Wait up to a bounded duration.
- Enqueue the job.
- Skip duplicate runs if an active run exists.
- Fail fast so the scheduler retries later.
- Partition work to another slice if possible.

Never wait indefinitely. Lock acquisition must enforce its own wait timeout.

### Renew lease

With time-bound leases, workers must renew before expiration. Renewal succeeds only if the worker remains the valid owner.

If renewal fails, the worker must stop writing and transition to a reconciliation-needed state. Never keep processing assuming you still hold the lock.

### Release

Upon completion, the worker releases the lock. Release must verify owner identity so a stale worker never deletes a lock acquired by a newer worker.

If a worker crashes abruptly, lease expiration or connection closure reclaims the lock. Still, reclaiming a lock does not prove prior work finished or rolled back cleanly; transactions and checkpoints still require verification.

## 6. Leases, heartbeats, and fencing tokens

A lease grants lock ownership for a bounded window. For example, a worker receives a 60-second lease and sends heartbeats every 20 seconds. If heartbeats stop, the system treats the lease as expired and grants it to another worker.

Leases solve lock reclamation when a worker disappears, yet introduce a tricky scenario:

1. Worker A acquires a lease and starts processing.
2. A freezes or loses connectivity longer than the lease duration.
3. The lease expires; Worker B acquires a new lease.
4. A wakes up and resumes writing data.
5. A and B mutate the dataset concurrently.

### Fencing tokens

A fencing token is a monotonically increasing sequence number issued whenever a new owner acquires a lock. The target system stores the highest seen token and rejects operations carrying older tokens.

Example:

| Worker | Fencing token | Outcome |
|---|---:|---|
| A | 41 | Accepted while 41 is the latest token |
| B acquires lease next | 42 | Token 42 supersedes 41 |
| A wakes up, writes with 41 | Rejected |
| B writes with 42 | Accepted |

Tokens must be issued by a monotonically increasing source and verified at the write target. Logging a token without checking it at the target database or service provides zero fencing protection.

### Heartbeats do not replace timeouts

A heartbeat merely proves the worker can still talk to the coordinator. It does not prove the worker is making progress or free from deadlocks. Also monitor progress markers, processed row counts, and time since the last commit.

## 7. Database locks: short transactions and clear scopes

Database locks are often ideal when data and progress reside in the same database. However, locks persist only for the transaction or session lifetime depending on lock type.

### Row locking with SELECT FOR UPDATE

PostgreSQL example:

~~~sql
BEGIN;

SELECT job_id, status
FROM data_jobs
WHERE job_id = 'daily-customer-rollup'
FOR UPDATE;

-- Verify status and update within the same transaction.
UPDATE data_jobs
SET status = 'RUNNING',
    started_at = CURRENT_TIMESTAMP
WHERE job_id = 'daily-customer-rollup'
  AND status IN ('READY', 'RETRYABLE');

COMMIT;
~~~

In practice, check the updated row count and handle cases where the job is already `RUNNING` or completed. Row locks hold until transaction end. Never hold this transaction open across a task processing millions of rows.

### Transaction-scoped advisory locks in PostgreSQL

Use `pg_try_advisory_xact_lock` to acquire a logical lock within a transaction:

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(202611, 6) AS acquired;

-- Execute protected work only if acquired = true.

COMMIT;
~~~

The numeric pair represents an application-defined logical lock key. If `false`, the worker does not hold the lock. When the transaction ends, the lock releases automatically.

Do not hold transactions open for hours merely to hold an advisory lock. For long tasks, consider lease-backed lock records or splitting work into short-transaction batches.

### Session locks and connection pools

PostgreSQL also offers session-level advisory locks. These persist across transactions until explicitly released or session end. With connection pools, a connection can return to the pool with a session lock still held, preventing other workers from acquiring the lock or leaking lock state to subsequent sessions.

If using session locks, guarantee release on every code path and reset connections before returning to the pool. For typical data jobs, transaction-scoped locks are usually easier to manage.

## 8. Avoiding deadlocks and lock contention

Deadlocks happen when transactions hold locks and wait cyclically for each other's locks. Databases typically detect cycles and abort one transaction to break the wait.

Example:

- Transaction A locks row 1, then waits for row 2.
- Transaction B locks row 2, then waits for row 1.
- Neither transaction can proceed.

### Ways to reduce deadlocks

- Always acquire locks in a consistent order, such as ascending primary key.
- Keep transactions short.
- Never call external APIs while holding row locks.
- Lock only the rows strictly needed.
- Use proper indexes to avoid unintended range scans and extra locks.
- Pick the isolation level matching consistency needs, never higher than required.
- Retry transactions aborted for deadlock only when the entire transaction can safely re-run.

### Lock contention

Lock contention happens when many workers wait on the same lock. Symptoms include rising wait times, falling throughput, and jobs overrunning estimates.

Reduce contention by:

- Splitting datasets into partitions.
- Processing smaller batches.
- Shortening transaction duration.
- Separating read workloads from write workloads where appropriate.
- Coordinating via queues instead of multiple workers polling one resource.
- Tuning worker concurrency to database capacity.

Do not raise timeouts merely to mask lock contention. If transactions frequently hold locks too long, investigate root causes and fix scope or processing logic.

## 9. Managing duration: distinct timeout types

A data job needs more than a single timeout. Distinguish:

| Limit | What it controls | Example |
|---|---|---|
| Queue timeout | How long a job may wait for a worker | Wait up to 5 minutes |
| Lock acquisition timeout | How long to wait to acquire a lock | Wait up to 10 seconds |
| Lease duration | Lock ownership validity window | 60 seconds with heartbeat |
| Connection timeout | Time allowed to establish a connection | 5 seconds |
| Statement/query timeout | Execution limit for one SQL statement | 30 seconds |
| Transaction timeout | Lifetime limit for a transaction | Per DB policy |
| Job deadline | Total wall-clock budget from start to finish | 45 minutes |
| Shutdown grace period | Time allowed to wrap up a batch on stop | 30 seconds |

Numbers above are illustrative. Choose values based on data size, SLAs, database capacity, and operational windows.

### Overall deadline vs. per-step timeouts

An overall deadline bounds total task runtime. Per-step timeouts bound individual calls or batches. Configuring only an HTTP client timeout without an overall deadline lets a job retry repeatedly and run far past expectations.

Propagate remaining deadline budgets across steps. As the deadline approaches, workers must not start a new batch without enough time to finish and commit safely.

### Distinguishing timeouts from cancellation

A timeout stops the caller from waiting, yet does not necessarily halt server-side queries or workers. Cancellation must propagate to the underlying system and confirm stoppage or arrival at a safe boundary.

When canceling a job, do not kill the process mid-write in an indeterminate state. Prefer stopping new batch claims, finishing or rolling back the active transaction, persisting the checkpoint, and exiting.

## 10. Splitting long tasks into batches

A transaction running for hours holds numerous row locks, bloats WAL/undo logs, ties up connections, and makes rollbacks very expensive. Split large tasks into batches.

For example, backfilling 10 million records in groups of 1,000 or 5,000 rows. Each batch:

1. Selects a deterministic range of records.
2. Reads and transforms data.
3. Writes results to the target table.
4. Updates status or checkpoint.
5. Commits.
6. Releases locks.
7. Advances to the next batch.

### Choosing batch size

Batches too large:

- Long transactions.
- Prolonged locks.
- Costly rollbacks.
- Elevated memory and log pressure.
- Hard to stop promptly.

Batches too small:

- Excessive round trips.
- High commit overhead.
- Heavy scheduler and checkpoint overhead.
- Potentially low throughput.

Measure runtime and resource usage to tune batch size. Start moderate, observe p95 batch duration, lock waits, and database load, then adjust.

### Keyset batching instead of large OFFSET

On large tables, high `OFFSET` pagination skips many rows and degrades progressively. Keyset pagination resumes cleanly via a stable key:

~~~sql
SELECT id, payload
FROM source_records
WHERE id > :last_committed_id
ORDER BY id
LIMIT :batch_size;
~~~

This works well when IDs increase monotonically and the dataset is clearly bounded. If records can be inserted or updated mid-run, use snapshots, watermarks, or late-arriving rules to avoid missing rows.

## 11. Checkpoints must align with committed data

Checkpoints track completed progress. Wrong checkpoint ordering is a classic cause of lost or duplicated data.

### Updating checkpoints before data is unsafe

Suppose a worker sets `last_id = 5000` before writing target rows. If the process crashes after saving the checkpoint yet before writing target rows, the next run starts at `5001` and skips uncommitted records.

### Updating checkpoints after data in a separate transaction

If the target write commits and the process crashes before updating the checkpoint, the next run re-reads the old batch. This is safe only if target writes are idempotent or deduplicated.

### Best practice: data and checkpoint in the same transaction

When source, target, and checkpoint reside in the same database supporting shared transactions:

~~~sql
BEGIN;

-- Write or upsert batch data.
INSERT INTO target_records (source_id, payload)
SELECT source_id, payload
FROM staging_batch
ON CONFLICT (source_id)
DO UPDATE SET payload = EXCLUDED.payload;

-- Update checkpoint for that exact batch.
UPDATE data_job_checkpoint
SET last_committed_id = :batch_end_id,
    updated_at = CURRENT_TIMESTAMP
WHERE job_name = 'customer-backfill';

COMMIT;
~~~

If the transaction rolls back, neither data nor checkpoint changes. If commit succeeds yet the caller loses the response, the next run sees the advanced checkpoint and avoids redoing finished work.

When source and target live in separate systems without a shared transaction, use idempotency keys, outbox/inbox tables, batch ledgers, or reconciliation to bridge the gap between commits.

## 12. Job control and checkpoint tables

A data job system can store operational state in dedicated tables.

Conceptual schema example:

~~~sql
CREATE TABLE data_job_runs (
    run_id           UUID PRIMARY KEY,
    job_name         TEXT NOT NULL,
    scope_key        TEXT NOT NULL,
    status           TEXT NOT NULL,
    owner_id         TEXT,
    fencing_token    BIGINT,
    lease_until      TIMESTAMPTZ,
    started_at       TIMESTAMPTZ,
    heartbeat_at     TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    last_error       TEXT
);

CREATE TABLE data_job_checkpoint (
    job_name             TEXT NOT NULL,
    scope_key            TEXT NOT NULL,
    last_committed_key   TEXT,
    batch_number         BIGINT NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_name, scope_key)
);
~~~

This schema is illustrative; adapt data types, statuses, and constraints to your actual database.

### Essential fields

- `job_name`: logical task name.
- `scope_key`: lock scope, e.g., tenant or partition.
- `run_id`: unique run identifier.
- `status`: state such as `READY`, `RUNNING`, `SUCCEEDED`, `FAILED`, or `UNKNOWN`.
- `owner_id`: worker currently holding the lease.
- `fencing_token`: monotonic owner sequence number.
- `lease_until`: lease expiration timestamp.
- `heartbeat_at`: last timestamp the worker reported liveness.
- `last_committed_key`: committed data watermark/position.
- `batch_number`: completed batch count.
- `last_error`: error summary scrubbed of secrets.

Do not store just a single `last_processed_id` if a job spans multiple partitions. Each scope needs its own checkpoint.

## 13. Safely claiming batches with multiple workers

When multiple workers pull from a queue, use row locks with `SKIP LOCKED` if supported by the database. Each worker claims an unclaimed slice of work; other workers skip locked rows.

PostgreSQL example:

~~~sql
BEGIN;

WITH picked AS (
    SELECT id
    FROM data_tasks
    WHERE status = 'READY'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE data_tasks AS task
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE task.id = picked.id
RETURNING task.id, task.payload;

COMMIT;
~~~

The worker receives claimed tasks and processes them. If a worker crashes after committing the claim, rows can stay stuck in `RUNNING`. Therefore, add a lease or `claimed_at` plus expired-claim detection.

When reclaiming expired tasks, prevent the old worker from writing stale results. Use a fencing token or task version checked during the commit update.

### Never hold row locks while calling external services

After claiming tasks, commit the claim transaction before invoking external APIs or doing heavy processing. Holding open transactions and row locks across external calls inflates lock durations and deadlock risk.

When saving results, open a new transaction and update only if the owner/token remains valid.

## 14. Designing safely rerunable tasks

Rerunability means a job can restart after failure, cancellation, or operator request without corrupting data.

### Using unique business keys

If each target row represents one source entity, enforce a unique constraint on source ID or business key. When reprocessing, upsert or skip existing rows per defined rules.

Example:

~~~sql
INSERT INTO customer_summary (
    customer_id,
    total_orders,
    calculated_at
)
VALUES (
    :customer_id,
    :total_orders,
    :calculated_at
)
ON CONFLICT (customer_id)
DO UPDATE SET
    total_orders = EXCLUDED.total_orders,
    calculated_at = EXCLUDED.calculated_at;
~~~

Upserts prevent duplicate rows for the same customer. However, if each rerun increments `total_orders` rather than assigning an idempotently computed total, rerunning remains unsafe. Compute deterministic state from source data and assign target state cleanly.

### Conditional row updates

For backfills, update only rows not yet processed:

~~~sql
UPDATE customer_records
SET normalized_name = normalize_name(raw_name),
    normalization_version = 2
WHERE normalization_version < 2;
~~~

Version predicates prevent re-applying the same migration. Define behavior if another business flow modifies a row during backfill; version checks or optimistic locking may be needed.

### Distinguishing same-input reruns from new-input runs

Matching job names alone do not make two runs identical operations. Tie each run to:

- Source snapshot or watermark.
- Algorithm/transform version.
- Input parameters.
- Scope or partition.
- Batch definition.

If transformation code changes, start a fresh backfill under a new version rather than resuming an old checkpoint. Never reuse an old algorithm's checkpoint if data semantics changed.

## 15. Watermarks, late-arriving data, and consistent snapshots

For time-based sync tasks, checkpoints are often watermarks marking how far data has been processed.

For instance, a job processes events by `created_at` up to 12:00. The next run can start from that watermark. Yet late-arriving events or rows updated with older timestamps may be missed if relying solely on time checkpoints.

### Lookback watermarks

One technique re-reads an overlap window prior to the watermark:

- Committed watermark: 12:00.
- Next run starts reading from 11:55.
- Duplicates are deduplicated by event ID or business key.
- New watermark advances only after the batch completes.

Overlap captures late-arriving data, requiring deduplication to prevent duplicate target records.

### Snapshots and stable ordering

If source data mutates mid-run, ID pagination can observe an inconsistent dataset. Choose a strategy:

- Database snapshots or suitable transaction isolation.
- Immutable source watermarks.
- CDC offsets or log sequences.
- Stable version/cursors.
- A fixed cutoff timestamp saved in run metadata.

Do not evaluate a fresh `CURRENT_TIMESTAMP` in every batch as a shifting cutoff if the entire run must cover one consistent data slice.

## 16. Distributed and multi-system data tasks

When source and target reside in different databases, local transactions cannot commit both atomically.

Suppose a pipeline reads from Database A, writes to Warehouse B, and sends a message to Broker C. If writing B succeeds yet sending to C fails, the next run must know B already succeeded to avoid duplicating data or emitting duplicate messages uncontrollably.

Common mechanisms:

- Stable batch IDs.
- Event IDs or source offsets.
- A ledger table recording applied batches.
- Idempotent upserts at targets.
- Transactional outbox/inbox patterns at respective boundaries.
- Reconciliation between source and target.
- Per-sink checkpoints if required.

### Batch ledger

A ledger table can record:

| Field | Meaning |
|---|---|
| `batch_id` | Stable batch identifier |
| `source_range` | Source data range |
| `transform_version` | Transformation logic version |
| `target` | Target system |
| `status` | PENDING, RUNNING, COMMITTED, FAILED |
| `checksum/count` | Evidence of processed data |
| `committed_at` | Confirmation timestamp |

When retrying the same batch ID, check both ledger and target before rewriting. If ledger and target cannot share a transaction, reconcile cases where target committed before the ledger updated.

## 17. Planning duration and throughput capacity

Runtime estimates cannot rely on record counts alone. Account for payload size, transform complexity, indexes, network, contention, and resource limits.

Measure:

- Records per second.
- Mean and p95 batch duration.
- Lock wait time.
- Query duration.
- Retry counts.
- Read/write data volume.
- CPU, memory, I/O, and network.
- Commit and checkpoint overhead.
- Queue wait time before job start.

### Estimating expected duration

~~~text
estimated_runtime =
  total_records / measured_records_per_second
  + commit_overhead
  + expected_retry_time
  + lock_wait_budget
  + verification_time
~~~

This is only an initial model. For workloads varying by partition or skewed data distributions, benchmark each scope separately and use percentiles rather than averages alone.

### Deadlines and operational windows

If a job must finish before 06:00, budget scheduler wait time, lock acquisition, processing, retries, verification, and cleanup. Never start a new batch when remaining time cannot cover the batch and a safe commit.

Configure:

- Job deadline.
- Batch deadline.
- Query timeout.
- Lock wait timeout.
- Graceful shutdown period.
- Maximum retry budget.

Coordinate these limits. A statement timeout longer than the job deadline will not help the job finish; it merely leaves the database working after the caller has already abandoned the call.

## 18. Task cancellation and crash recovery

Canceling a job does not roll back previously committed batches. In batch processing, every committed batch is an independent unit of completion.

### Graceful shutdown

Upon receiving a stop signal:

1. Stop claiming new batches.
2. Complete or roll back the active batch.
3. Update the checkpoint only if batch data committed.
4. Record `PAUSED` or `INTERRUPTED` status.
5. Release lock/lease if still the valid owner.
6. Close connections and free resources.
7. Allow the scheduler to resume from the checkpoint.

### Crash recovery

If the process dies without running cleanup:

- Open database transactions typically roll back once connection drop is detected.
- Leases expire and another worker takes over.
- `RUNNING` job records can transition to `STALE`/`RECOVERABLE` after heartbeat checks.
- Checkpoints reveal the last committed batch.
- Batch ledgers confirm whether targets received data.

Do not blindly mark every overdue `RUNNING` job as `FAILED` and restart it. The worker may still be running with temporarily dropped heartbeats. Require lease expiration, fencing, or owner verification before reclaiming.

## 19. Migrations and backfills in release pipelines

Data migrations frequently accompany application deployments. Old and new versions may access the database simultaneously during rolling deployments.

A controlled sequence:

1. Inspect schema and data before migration.
2. Acquire a database/schema migration lock.
3. Record migration ID and source version.
4. Apply backward-compatible changes (expand).
5. Run checkpointed batched backfill.
6. Validate row counts, checksums, and data invariants.
7. Deploy the application version using the new structure.
8. Monitor errors and performance.
9. Contract/remove old structures only after no dependent versions remain.
10. Release the lock and retain audit records.

### Do not hold a global migration lock across long backfills

A brief lock ensures only one migration coordinator alters the schema at a time. Yet multi-hour backfills should rely on checkpoints and short batch transactions. Depending on the database, holding a schema transaction/lock across an entire backfill can block live application access.

Separate synchronized schema alterations from incremental data movement.

### Pre- and post-checks

Migrations should have concrete verification criteria:

- Source vs. target row counts.
- Missing or duplicate row counts.
- Partition checksums.
- Unique and foreign key constraints.
- Nullability and value domains.
- Version/marker states.
- Query latencies and workload impact.

Never rely solely on the migration command returning exit code 0.

## 20. Observing locks and duration in operations

To troubleshoot slow or stuck jobs, logs must show what a worker is waiting on and how far it has progressed.

Every run should log:

- Job name, run ID, and scope key.
- Owner ID, lease ID, or fencing token.
- Timestamps for lock request, acquisition, renewal, and release.
- Lock wait duration and acquisition outcome.
- Batch ID, key range, and row count.
- Query, transform, write, and commit durations.
- Checkpoint before and after each batch.
- Retry counts and error categories.
- Remaining deadline budget.
- Final status and stop reason.

Never log personal data or secrets just for debugging. Log IDs, counts, and checksums as appropriate.

### Metrics to monitor

| Metric | Meaning |
|---|---|
| `job_duration_seconds` | Total job duration |
| `batch_duration_seconds` | Duration of each batch |
| `lock_wait_seconds` | Time spent waiting for locks |
| `lock_acquire_failures_total` | Failed lock acquisition count |
| `active_job_runs` | Number of active runs |
| `lease_renewal_failures_total` | Failed lease renewal count |
| `records_processed_total` | Total records processed |
| `checkpoint_lag` | Distance between latest source data and checkpoint |
| `retry_attempts_total` | Total retry attempts |
| `stale_runs_total` | Runs detected as stale |
| `deadlocks_total` | Deadlock count |
| `data_validation_failures_total` | Failed data validation count |

Track metrics by job and scope to spot abnormally slow tenants or partitions. Base alerts on operational thresholds and SLOs, not just whether one run exceeded the average.

## 21. Example resumable backfill workflow

Suppose we need to normalize customer names across 5 million records. It can be designed as follows:

~~~text
Scheduler
   |
   v
Acquire lock: customer-normalization / partition-03
   |
   v
Load checkpoint and transform version
   |
   v
Claim next batch (stable key range)
   |
   v
Read source snapshot
   |
   v
Normalize and validate
   |
   v
BEGIN TRANSACTION
   |-- Upsert target by customer_id
   |-- Mark source rows/version
   |-- Update committed checkpoint
   v
COMMIT
   |
   v
Record metrics and heartbeat
   |
   +------ More rows? ------+
   |                        |
  Yes                      No
   |                        |
   v                        v
Next batch             Verify counts/checksum
                            |
                            v
                     Mark SUCCEEDED
                            |
                            v
                       Release lock
~~~

If the worker dies before `COMMIT`, the current batch rolls back and the checkpoint does not advance. The next run reprocesses that batch. If the worker dies after `COMMIT` yet before logging completion, the checkpoint has already advanced; the next run resumes from the following batch.

Conditions making this flow safe:

- Target has a unique key on customer ID.
- Upsert assigns the normalized value rather than accumulating side effects.
- Source marker and checkpoint share the same transaction when in the same database.
- Transform version is stored alongside the run.
- Lock scope is bounded to `partition-03`.
- Leases and fencing prevent stale workers from writing after losing ownership.
- Final verification confirms zero missing or duplicate records.

## 22. Testing locks, timeouts, and rerunability

Do not test only the happy path. Simulate contention and interruptions.

### Lock tests

- Two workers acquire the same scope simultaneously: only one succeeds.
- Two workers acquire different partitions: both run in parallel.
- Worker dies while holding lease: another worker takes over after lease expiry.
- Stale worker wakes up: fencing token blocks writes.
- Stale owner releases lock: does not delete the new owner's lock.
- Lock contention: job waits or fails per configured timeout.

### Duration tests

- Query exceeds statement timeout.
- Job exceeds overall deadline.
- Lock fails to release on schedule.
- Heartbeats drop while worker continues running.
- Shutdown arrives mid-batch.
- Retry budget exhausted.
- Slow database or connection pool exhaustion.

### Rerun and checkpoint tests

- Crash before target write.
- Crash after target write but before checkpoint.
- Crash after commit before returning response.
- Rerunning the same batch ID.
- Rerunning the same job with a new transform version.
- Late-arriving source records.
- Two workers claiming the same batch.
- Missing checkpoint or mismatch against batch ledger.

Verify final data state, side effect counts, and checkpoints—not merely job exit codes.

## 23. Common anti-patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| No locking for exclusive jobs | Two runs mutate the same data | Lock by job/dataset/partition |
| Using a global lock for every task | Loses all parallelism | Pick smallest scope protecting invariants |
| Holding transactions open for hours | Blocking, deadlocks, massive rollbacks | Split into batches with short transactions |
| Waiting for locks indefinitely | Jobs hang with unclear cause | Set lock acquisition timeouts |
| Leases without fencing | Stale worker can write after losing lease | Enforce fencing tokens at write target |
| Treating heartbeats as progress proof | Hung jobs appear healthy | Track progress markers and commit times |
| Updating checkpoint before data | Skips uncommitted records | Commit data and checkpoint atomically |
| Separate checkpoint transaction with non-idempotent target | Retries duplicate data | Upserts, unique keys, or ledgers |
| Large OFFSET on huge tables | Queries slow progressively | Keyset pagination or partitioning |
| Retrying every error | Repeats unrecoverable failures | Classify errors and cap retry budgets |
| Rerunning new transform version with old checkpoint | Skips rows needing reprocessing | Bind checkpoints to transform version |
| Deleting job state to restart from scratch | Loses auditability and duplicates side effects | Resume/reconcile from run records |
| Relying solely on CI concurrency groups | Jobs from external systems still overlap | Enforce protection at database/service level |
| Marking job succeeded immediately on enqueue | Data may not be processed yet | Wait for terminal state and verify |

## 24. Operational checklist for data tasks

### Locking and concurrency

- [ ] Identified data invariants requiring protection.
- [ ] Selected lock scope by job, dataset, partition, or business key.
- [ ] Lock acquisition uses atomic operations.
- [ ] Lock wait timeout and busy-lock policy are defined.
- [ ] Leases include heartbeat/renewal and safe release.
- [ ] Fencing or version checks prevent stale workers from writing.
- [ ] Avoided holding transactions across API calls or external processing.
- [ ] Controls handle deadlocks, lock contention, and concurrent runs.

### Duration

- [ ] Defined queue timeout, lock timeout, query timeout, and job deadline.
- [ ] Capped retry counts and total retry duration.
- [ ] Batch duration is measured and tuned.
- [ ] Graceful shutdown period is configured.
- [ ] Jobs do not start new batches without sufficient time to commit.
- [ ] Lease duration aligns with heartbeats and batch runtime.
- [ ] Alerts fire when jobs or checkpoints stall.

### Rerunability

- [ ] Every run, scope, and batch has a stable identifier.
- [ ] Target writes enforce unique keys or deduplication.
- [ ] Upserts assign target state rather than accumulating unintended side effects.
- [ ] Checkpoints advance only after data commits.
- [ ] Data and checkpoints share a transaction whenever possible.
- [ ] Cross-system tasks use ledgers, outbox/inbox, or reconciliation.
- [ ] Checkpoints bind to source snapshots and transform versions.
- [ ] Late-arriving data and backfills are handled.
- [ ] Reruns with identical inputs produce no duplicate side effects.

### Verification and audit

- [ ] Counts, checksums, and invariants validate outcomes.
- [ ] Run ID, batch ID, lock owner, and fencing token are recorded.
- [ ] Timestamps capture acquire, wait, process, commit, and release.
- [ ] Failure injection tests cover critical interruption points.
- [ ] Procedures handle `UNKNOWN` or stale run states.
- [ ] Secrets and sensitive data are excluded from logs.

## Conclusion

Safe data tasks require managing concurrency, duration, and progress as one unified design. Choose locks based on invariants at the smallest valid scope; bound lock waits, queries, batches, and jobs with timeouts and deadlines; use leases and fencing tokens across distributed workers; break long work into short-transaction batches; and advance checkpoints only when corresponding data commits. Combining unique keys, upserts, batch ledgers, snapshots/watermarks, and reconciliation lets jobs restart or resume after crashes without losing or duplicating data. Finally, monitor lock waits, batch duration, checkpoint lag, and retries to spot bottlenecks early before they impact pipelines or production systems.
