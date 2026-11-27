# NOWAIT, SKIP LOCKED, and the table-based job-claiming problem

When multiple workers dequeue jobs from a queue table concurrently, each worker needs to claim a subset of rows without competing for the exact same jobs as other workers. InnoDB provides locking reads with `NOWAIT` and `SKIP LOCKED` to control how a query reacts when the rows it needs to read are currently locked by another transaction.

- `NOWAIT` tells MySQL to return an error immediately if the required lock cannot be acquired, rather than waiting for the lock wait timeout.
- `SKIP LOCKED` skips rows that are currently locked and returns only the rows that can be locked immediately.

These two options are especially useful for table-backed job-claiming systems: multiple workers can concurrently select ready jobs, lock the chosen rows, transition their status to processing, and commit quickly. They should be combined with transactions, proper indexes, and a recovery mechanism for when workers fail.

## 1. Locking reads with `FOR UPDATE`

In InnoDB, `SELECT ... FOR UPDATE` is a locking read. The query reads matching rows and acquires exclusive locks on the selected rows so the current transaction can update them. Another transaction attempting to modify or acquire a conflicting lock on the same rows must wait, or follow whichever lock-wait option it uses.

Example locking an order before changing its status:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 7001
FOR UPDATE;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 7001;

COMMIT;
```

Locks are held until the transaction commits or rolls back. As a result, two transactions cannot concurrently execute the read-check-update sequence on the same row as though each owned it exclusively.

`FOR UPDATE` must be used inside an explicit transaction, such as after `START TRANSACTION`, or in a session with autocommit disabled. If each statement runs in its own implicit transaction because autocommit is enabled, the lock acquired by `SELECT` is released as soon as that statement ends; the subsequent `UPDATE` is then no longer protected by the lock from the read.

## 2. `NOWAIT`: fail fast when a row is locked

By default, a locking read may wait for another transaction to release its lock. Add `NOWAIT` to instruct MySQL to report an error immediately when a lock cannot be obtained:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 7001
FOR UPDATE NOWAIT;

COMMIT;
```

If another transaction holds a conflicting lock on the row `order_id = 7001`, the query returns a lock-not-available error (MySQL error `3572`, `ER_LOCK_NOWAIT`) instead of waiting. The application can roll back the transaction and decide to retry later, return a busy message, or pick another task.

`NOWAIT` fits well when latency matters and the application knows how to handle contention. It prevents a worker from hanging for a long time over a single busy row. However, avoid tight immediate retries; cap the retry count and consider backoff to avoid adding load during contention.

## 3. `SKIP LOCKED`: skip rows that are locked

Add `SKIP LOCKED` so the query skips rows with conflicting locks instead of waiting:

```sql
START TRANSACTION;

SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY available_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;

COMMIT;
```

If another worker is locking some matching rows, the query returns up to 10 remaining rows that can be locked. When all matching rows are currently locked, the query can return an empty result set even though the table still contains unprocessed jobs.

`SKIP LOCKED` is helpful for queues because each worker can claim different rows with minimal waiting on one another. However, the result is an inconsistent view of the row set: locked rows are skipped even though they match the query predicate. Therefore, do not use `SKIP LOCKED` for reporting queries or business flows that need a complete and consistent view of all matching rows.

`NOWAIT` and `SKIP LOCKED` are two distinct options for the same locking clause. Use `NOWAIT` when you want an immediate error; use `SKIP LOCKED` when busy rows can be skipped to continue with others.

## 4. Designing a queue table

A simple queue table can store status, availability time, attempt count, and info about the worker holding the job:

```sql
CREATE TABLE job_queue (
    job_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    status ENUM('READY', 'RUNNING', 'DONE', 'FAILED') NOT NULL DEFAULT 'READY',
    available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    worker_id VARCHAR(100) NULL,
    claim_token CHAR(36) NULL,
    locked_at DATETIME NULL,
    lease_until DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id),
    KEY idx_job_ready (status, available_at, job_id),
    KEY idx_job_lease (status, lease_until)
) ENGINE = InnoDB;
```

Meaning of the main columns:

- `status`: whether the job is ready, running, completed, or failed.
- `available_at`: earliest timestamp when the job is eligible to be claimed, useful for delayed retries.
- `attempts`: number of times the job has been claimed for processing.
- `worker_id`: the worker owning the current processing attempt.
- `claim_token`: a unique token for the claim attempt, used to prevent an old worker from mistakenly updating a newer attempt.
- `lease_until`: expiration time of the processing lease; the job can be reclaimed if the worker dies and the lease expires.

The `idx_job_ready (status, available_at, job_id)` index supports filtering by status, bounding by availability time, and scanning in chronological and primary key order. The `idx_job_lease` index helps find runs whose leases have expired. Actual indexes should be verified with `EXPLAIN` against your system's data size and distribution.

## 5. Job-claiming workflow using `SKIP LOCKED`

A claim operation must hold locks from row selection until the status update. A worker must not commit right after `SELECT`, as doing so would release locks before the job is marked `RUNNING`.

The workflow consists of these steps:

1. Start a transaction.
2. Select a batch of `READY` jobs that are due for execution using `FOR UPDATE SKIP LOCKED`.
3. Within the same transaction, update the selected rows to `RUNNING`, recording the worker, claim token, lock timestamp, and lease deadline.
4. Commit immediately after claiming.
5. Process the payload outside the transaction, then update the result with a predicate verifying ownership of the claim attempt.

SQL example for the selection step:

```sql
START TRANSACTION;

SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

The application collects the returned `job_id` list, generates a random `claim_token` for this claim, and executes the update on the **same connection before committing**. For the selected ID list, the application generates the corresponding number of placeholders and binds the IDs via a prepared statement:

```sql
UPDATE job_queue
SET status = 'RUNNING',
    worker_id = ?,
    claim_token = ?,
    locked_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL 5 MINUTE,
    attempts = attempts + 1
WHERE status = 'READY'
  AND job_id IN (?, ?, ?, ?);

COMMIT;
```

Four placeholders are shown in the example for illustration; the application must generate the exact number of placeholders matching the selected IDs and bind each value. Never concatenate user input directly into SQL. If no rows are selected, commit the empty transaction and wait or poll again after a suitable interval.

If the updated row count differs from the number of selected IDs, roll back and investigate rather than processing an incomplete claim batch. Under normal conditions, the newly selected rows remain locked by the current transaction, so the `UPDATE` must modify those exact rows.

After `COMMIT`, the worker can process each payload. Do not keep a transaction open while calling APIs, sending emails, processing files, or running long-lived work; doing so holds locks too long and reduces other workers' ability to claim jobs.

## 6. Illustrating a multi-worker flow

Suppose the queue contains jobs J1 through J6. Workers A and B concurrently run the query to claim up to three rows:

| Step | Worker A | Worker B |
|---|---|---|
| 1 | Locks J1, J2, J3 using `SKIP LOCKED` |  |
| 2 |  | Skips locked J1, J2, J3; locks J4, J5, J6 |
| 3 | Updates J1-J3 to `RUNNING`, commits | Updates J4-J6 to `RUNNING`, commits |
| 4 | Processes J1-J3 after commit | Processes J4-J6 after commit |

The two workers claim distinct batches without waiting on each other over locked rows. If Worker A rolls back before claiming completes, the locks are released and those rows can be picked up by another worker on the next poll.

Actual outcomes depend on transaction timing and lock order. `SKIP LOCKED` does not strictly guarantee which worker gets the oldest job in every scenario; it prioritizes lockable rows in query order.

## 7. Completion updates and ownership checks

After processing succeeds, the worker marks the job done. The statement must verify `worker_id` and `claim_token` for that specific claim:

```sql
UPDATE job_queue
SET status = 'DONE',
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL
WHERE job_id = ?
  AND status = 'RUNNING'
  AND worker_id = ?
  AND claim_token = ?;
```

If the statement updates one row, the worker still owned the claim and finalized the status. If it updates `0` rows, the lease may have expired and another worker reclaimed the job, or the status changed. The stale worker must not overwrite the outcome of a newer attempt.

If processing fails transiently, the job can be returned to `READY` with a future retry time:

```sql
UPDATE job_queue
SET status = 'READY',
    available_at = CURRENT_TIMESTAMP + INTERVAL 30 SECOND,
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL
WHERE job_id = ?
  AND status = 'RUNNING'
  AND worker_id = ?
  AND claim_token = ?;
```

Unrecoverable errors can transition to `FAILED` once the `attempts` limit is reached. Retry policies should distinguish transient errors (timeouts, busy external services) from non-recoverable business errors (invalid data).

## 8. Leases and recovery when a worker crashes

A worker can crash after claiming a job but before marking it `DONE`. Without a recovery mechanism, the row would remain stuck in `RUNNING` forever. The `lease_until` column lets you detect expired processing ownership:

```sql
UPDATE job_queue
SET status = 'READY',
    worker_id = NULL,
    claim_token = NULL,
    locked_at = NULL,
    lease_until = NULL,
    available_at = CURRENT_TIMESTAMP
WHERE status = 'RUNNING'
  AND lease_until < CURRENT_TIMESTAMP;
```

A periodic task can run this statement to return lease-expired jobs to the queue. Long-running workers should renew their lease using a statement conditioned on `job_id`, `worker_id`, `claim_token`, and `status = 'RUNNING'`. If the renewal update affects zero rows, the worker has lost ownership and should abort processing if possible.

Choose a lease duration long enough for normal jobs, and extend it via heartbeats for long tasks. If the lease is too short, healthy workers can lose jobs while still working. If the lease is too long, stuck jobs take a long time to recover.

A lease does not guarantee exactly-once execution. A worker may complete an external side effect and crash before writing `DONE`; after the lease expires, the job will run again. Therefore, handlers should be idempotent or use an idempotency key/unique business key to prevent duplicate effects. For critical writes, consider an outbox/inbox design or unique constraints to protect correctness.

## 9. When to use `NOWAIT` vs. `SKIP LOCKED`

| Situation | Choice | How the application handles it |
|---|---|---|
| Need to lock a specific record and do not want to wait | `FOR UPDATE NOWAIT` | Catch lock-not-available error, roll back, and report busy or retry with backoff |
| Multiple workers claiming distinct rows from a queue | `FOR UPDATE SKIP LOCKED` | Claim unlocked rows, update status, and commit quickly |
| Need to read a complete row set for reporting or reconciliation | Appropriate consistent read, no `SKIP LOCKED` | Choose isolation level and snapshot per consistency requirements |
| Row is locked but caller should wait its turn | Standard `FOR UPDATE` | Wait up to configured timeout and handle timeouts/deadlocks |

Do not use `NOWAIT` and `SKIP LOCKED` as substitutes for proper transaction design. They only govern behavior when a locking read encounters a conflicting lock.

## 10. Limitations and operational notes

- `NOWAIT` and `SKIP LOCKED` apply to row-level locks. They do not bypass table-level locks or all other waits; for example, metadata locks can still cause statements to wait.
- An engine supporting row-level locking such as InnoDB is required. Verify the engine of the queue table and related tables.
- `SKIP LOCKED` can repeatedly skip older rows that remain locked, creating a starvation risk. Monitor the age of long-waiting jobs, processing duration, and retry counts.
- Filter predicates and sort orders need suitable indexes. If the query has to scan too many locked `READY` rows or not-yet-due rows, the benefit of `SKIP LOCKED` diminishes.
- Keep claim transactions short and process payloads after commit. Never call external services while holding row locks inside a transaction.
- Statements using `SKIP LOCKED` are unsafe for statement-based replication. When using replication, choose and verify an appropriate binary log/replication format—typically row-based—per your MySQL version configuration.
- Monitor deadlocks and lock waits via InnoDB logs/metrics. `SKIP LOCKED` reduces waiting on locked rows but does not eliminate all deadlock possibilities in other transaction operations.

## 11. Self-check

1. How does `NOWAIT` differ from the default lock-waiting behavior of `SELECT ... FOR UPDATE`?
2. Why is `SKIP LOCKED` suitable for queue tables but unsuitable for reporting queries needing a complete dataset?
3. Why must `SELECT ... FOR UPDATE SKIP LOCKED` and the status-changing `UPDATE` run inside the same transaction?
4. If the queue query returns empty, can you conclude the queue has no remaining jobs? Why or why not?
5. How does `claim_token` prevent a stale worker from writing results onto a new claim attempt?
6. How do leases handle mid-flight worker crashes, and why is idempotency still required?
7. Which types of locks or waits are not skipped by `SKIP LOCKED`?
