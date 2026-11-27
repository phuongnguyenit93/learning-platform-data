# NOWAIT, WAIT, SKIP LOCKED, and Table-Based Job Claiming in Oracle

## 1. The problem of multiple consumers working on one table

An application may have multiple users editing the same order simultaneously, or multiple workers reading a `JOB_QUEUE` table to process background tasks. If two sessions select the same row and both process it, the system can execute duplicate work, overwrite data, or end up in an inconsistent state.

Oracle provides explicit row locking through `SELECT ... FOR UPDATE`. When acquiring a lock, a session can choose one of the following policies:

- **`NOWAIT`**: if a row to be locked is already locked by another session, return an error immediately.
- **`WAIT n`**: wait up to `n` seconds to acquire the lock; return an error if the timeout expires.
- **`SKIP LOCKED`**: skip rows currently locked by other sessions and continue retrieving available rows.

These three modes serve different scenarios. `NOWAIT` fits interactive operations requiring immediate feedback upon conflict. `WAIT` fits cases where bounded waiting is acceptable. `SKIP LOCKED` is especially useful when multiple workers claim tasks from a queue table.

For example, two workers reading jobs in `READY` status:

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

If worker A has already locked some rows, worker B can skip those rows and claim other unlocked `READY` rows. After claiming a job, the worker must update the job status within the same transaction and `COMMIT` so other workers do not claim the same job again.

This lesson belongs to the **Locking and Concurrency** chapter and covers row locking, `SELECT FOR UPDATE` syntax, differences between `NOWAIT`, `WAIT`, and `SKIP LOCKED`, building a multi-worker queue, job-claiming transactions, leases, retries, handling crashed workers, and considerations for fairness, performance, JDBC, and PL/SQL.

## 2. Row locks and transactions in Oracle

### 2.1. Regular SELECT does not lock rows for reading

Oracle uses multiversion concurrency control (MVCC) and read consistency. A regular SELECT statement normally reads a consistent version of the data without waiting for another transaction merely because that transaction is modifying the row.

Example:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001;
```

If another session is running UPDATE on order 1001 without having COMMITted yet, a regular SELECT can read the previously committed version according to the appropriate snapshot.

### 2.2. SELECT FOR UPDATE proactively locks rows

When an application reads a row to prepare for modification, it can lock the row while reading:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE;
```

The session that acquires the row lock holds it until the transaction ends with `COMMIT` or `ROLLBACK`. Other sessions wanting to lock or UPDATE the same row may have to wait according to that statement's policy.

`SELECT FOR UPDATE` is not merely a SELECT with extra metadata. It is a lock-acquisition operation, so there must be a plan to finish the transaction. Do not open a transaction and leave a user thinking or wait on an external service while still holding locks.

### 2.3. UPDATE also acquires locks automatically

It is not always necessary to run SELECT FOR UPDATE before every UPDATE:

```sql
UPDATE orders
SET status = 'APPROVED'
WHERE order_id = 1001;
```

Oracle automatically acquires the locks needed to execute DML. `SELECT FOR UPDATE` is useful when the application must read data, make a decision based on it, and then update within the same transaction while preventing other sessions from changing the row between the read and write steps.

### 2.4. How long are locks held?

Row locks acquired by `SELECT FOR UPDATE` or DML are held until the transaction ends:

```sql
SELECT *
FROM orders
WHERE order_id = 1001
FOR UPDATE;

-- Perform checks/updates in the same transaction.
UPDATE orders
SET status = 'APPROVED'
WHERE order_id = 1001;

COMMIT;
```

Closing a cursor does not mean releasing locks. Locks are released when the transaction COMMITs or ROLLBACKs. That is why a queue worker must lock, change status, and commit quickly before performing long-running work.

### 2.5. Row locks do not mean locking the entire table

Oracle uses locks at multiple levels. `SELECT FOR UPDATE` primarily acquires row locks on the selected rows and may acquire a table-level lock in a mode compatible with other DML. An UPDATE statement also acquires the row locks and table locks needed to protect the operation.

Do not interpret `SKIP LOCKED` as skipping every type of lock in the database. It handles row lock conflicts per SELECT FOR UPDATE semantics; table locks, DDL locks, other resource locks, or other wait conditions can still cause a session to wait.

## 3. SELECT FOR UPDATE syntax

General syntax:

```sql
SELECT select_list
FROM table_name
WHERE condition
ORDER BY sort_expression
FOR UPDATE
    [OF column_list]
    [NOWAIT | WAIT integer | SKIP LOCKED];
```

Parts:

- `FOR UPDATE`: requests locks on the selected rows.
- `OF column_list`: specifies which tables (identified by listed columns) Oracle should lock in a multi-table query. This is a way of specifying tables, not locking only the listed columns.
- `NOWAIT`: do not wait when encountering an already locked row.
- `WAIT integer`: wait up to the specified number of seconds.
- `SKIP LOCKED`: skip rows currently locked by another transaction.

Basic example:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
FOR UPDATE;
```

If many rows satisfy the predicate, the statement can lock all selected rows. Use a sufficiently selective WHERE clause so you do not inadvertently lock a huge dataset.

### 3.1. Using OF in a JOIN query

When querying multiple tables:

```sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PENDING'
FOR UPDATE OF o.status;
```

`OF o.status` designates the `ORDERS` table as the table whose rows should be locked. Oracle locks the row of the table containing the specified column; it does not mean only the `STATUS` column is locked.

When `OF` is omitted, the locking scope in a multi-table query may be broader. Explicitly specify the table to lock to reduce unnecessary locking and make intent clear.

### 3.2. Limitations of SELECT FOR UPDATE

`FOR UPDATE` cannot be freely combined with every SELECT construct. Certain constructs are restricted, including:

- `DISTINCT`.
- `GROUP BY` and aggregate functions.
- Set operators such as `UNION`, `INTERSECT`, `MINUS`.
- Certain views or inline views that cannot be updated/locked according to Oracle rules.
- Certain complex query forms with version-specific restrictions.

If you need to lock source rows and then compute aggregates, separate the step of locking the appropriate base rows from the aggregation step. Do not attempt to place `FOR UPDATE` directly on a `GROUP BY` result.

### 3.3. ORDER BY is helpful when retrieving rows in order

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

`ORDER BY` defines the priority order among eligible rows. For queues, higher-priority jobs are typically favored first, followed by older jobs. Adding `job_id` as a tie-breaker makes the ordering deterministic when priority and timestamp values match.

Priority ordering does not guarantee strict FIFO when using SKIP LOCKED: an older job currently locked by another worker can be skipped so a worker picks up a newer job.

## 4. NOWAIT — do not wait for locks

### 4.1. Syntax

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE NOWAIT;
```

If the row to be locked is held by another transaction, Oracle immediately returns an error instead of waiting.

Common error:

```text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
```

The message can be used to inform the application that the resource is busy and the user needs to try again later.

### 4.2. When to use NOWAIT?

NOWAIT fits when:

- A user opens a record for editing and needs to know immediately if someone else is working on it.
- An operation must not wait due to fast-response requirements.
- A workflow only wants to attempt acquiring the lock once and then take another branch.
- The application has its own retry/backoff mechanism in the service layer.

Example:

```sql
BEGIN
    SELECT order_id, status
    INTO v_order_id, v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE NOWAIT;

    -- Continue processing within the same transaction.
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
/
```

This is an illustrative PL/SQL skeleton; in production applications, declare variables and handle ORA-00054 specifically. Do not catch every exception and treat all of them as locking errors.

### 4.3. NOWAIT does not resolve business conflicts by itself

If an application receives ORA-00054, that only indicates the requested lock could not be acquired at that moment. It does not indicate whether the lock holder will commit or roll back, nor does it guarantee an immediate retry will succeed.

The application can:

- Return a "record is currently being processed" message.
- Let the user reload the data.
- Retry a bounded number of times with short backoff if the operation can be safely repeated.
- Move on to another row if this is a queue worker.

Do not retry in a tight loop without pauses, as this increases load and creates additional contention.

## 5. WAIT n — wait for a bounded duration

### 5.1. Syntax

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

If the row is already locked, Oracle waits up to 5 seconds to acquire the lock. If the time expires without acquiring it, the statement raises a timeout error, typically:

```text
ORA-30006: resource busy; acquire with WAIT timeout expired
```

### 5.2. When to use WAIT?

WAIT fits when:

- Conflicts are usually brief and the application can wait.
- A business operation needs the lock but must not wait indefinitely.
- There is a specific SLA, such as waiting no more than 3 or 5 seconds.
- A batch process can wait briefly for a resource but must fail cleanly if the timeout is exceeded.

Choose the timeout based on user experience and SLA, rather than arbitrarily picking a large number.

### 5.3. WAIT differs from connection timeout and statement timeout

`WAIT n` on `SELECT FOR UPDATE` is the lock-acquisition wait time in Oracle syntax. It differs from:

- Connection timeout when establishing a connection.
- Statement/query timeout managed by JDBC or the client.
- Timeout of an HTTP request.
- Timeout of an application-level job or transaction.

If a system has multiple timeout layers, configure them consistently. For example, if an HTTP request expires after 3 seconds while the SQL uses `WAIT 30`, the application may return a timeout while the database continues holding the connection and waiting if the driver does not cancel the statement properly.

### 5.4. WAIT does not mean waiting for the other transaction's entire workload

Oracle only waits to acquire the lock according to the specified policy. After acquiring the lock, the transaction still has to perform its work and finish. If the transaction stays open for a long time, other sessions remain impacted.

## 6. SKIP LOCKED — skip rows currently locked

### 6.1. Syntax

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

When a matching row is locked by another transaction, Oracle skips that row and continues searching for other matching rows. The statement does not wait for that row's lock like WAIT does.

This mechanism suits multiple consumers claiming work:

- Worker A locks job 101.
- Worker B runs the same query.
- Worker B skips job 101 and can claim job 102.
- Worker C can claim job 103 if those rows are unlocked.

Workers do not have to queue behind one another waiting for the first row to unlock.

### 6.2. Returning zero rows does not mean the queue is empty

With SKIP LOCKED, a query can return 0 rows because:

1. No jobs match the condition.
2. Matching jobs exist, but all of them are currently locked by other sessions.
3. Jobs exist, but `AVAILABLE_AT` has not yet been reached.

Therefore, a worker should interpret an empty result as **no job currently claimable**. It is not enough to conclude the queue has no remaining jobs. It can wait briefly, listen for a signal from a coordinator, or retry on a polling schedule.

### 6.3. SKIP LOCKED does not skip every kind of lock

SKIP LOCKED is designed to avoid waiting on row locks for rows to be retrieved. It does not skip table-level locks, DDL locks, or other resource waits. A DDL operation or incompatible table lock can still affect the query.

### 6.4. SKIP LOCKED does not guarantee strict FIFO

Suppose job 101 has the highest priority, but it is locked by worker A. Worker B skips job 101 and claims job 102. That means actual execution order can differ from strict priority order.

SKIP LOCKED optimizes parallel progress across multiple workers; it is not a strict fairness guarantee. If a row repeatedly stays locked or ineligible, monitor job age, wait duration, and lease/retry policies.

## 7. Comparing NOWAIT, WAIT, and SKIP LOCKED

| Mode | Behavior when row is locked | Typical Outcome | Suitable Scenario |
|---|---|---|---|
| Unspecified | Waits per Oracle's default behavior | Waits until lock is released or another error occurs | Normal interactions where waiting is acceptable |
| `NOWAIT` | Does not wait | ORA-00054 | UI needing immediate feedback |
| `WAIT n` | Waits up to n seconds | ORA-30006 on timeout | Usually brief conflicts with an SLA |
| `SKIP LOCKED` | Skips locked rows | Returns other available rows; possibly 0 rows | Multi-consumer worker queues |

There is no single best choice for every case. Choose based on the business question: does the user need to know there is a conflict, how long can they wait, or can they take another item while the first row is busy?

## 8. Illustrating two sessions competing for the same row

Suppose table `orders` has `ORDER_ID = 1001`.

### 8.1. Session A acquires the lock

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE;
```

Session A has not COMMITted or ROLLBACKed, so it still holds the lock.

### 8.2. Session B tries NOWAIT

In another connection:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE NOWAIT;
```

Session B receives an error immediately because the row is locked by A.

### 8.3. Session B tries WAIT

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

Session B waits up to 5 seconds. If A COMMITs within the wait window, B can acquire the lock. If A holds the lock past the timeout, B receives a timeout error.

### 8.4. Session B tries SKIP LOCKED

```sql
SELECT order_id, status
FROM orders
WHERE order_id IN (1001, 1002, 1003)
ORDER BY order_id
FOR UPDATE SKIP LOCKED;
```

If A holds the lock on 1001, B can receive 1002 and 1003, depending on the actual lock status of those rows.

### 8.5. Releasing the lock

In Session A:

```sql
COMMIT;
-- Or ROLLBACK if you want to undo changes in the transaction.
```

Once the transaction ends, the lock is released. Session B can retry the earlier row if business logic still requires it.

## 9. Single-table queue model

A table-based queue typically has these states:

```text
READY -> RUNNING -> DONE
                  -> READY (retry)
                  -> FAILED
```

Commonly used columns:

| Column | Meaning |
|---|---|
| `JOB_ID` | Primary key of the job |
| `PAYLOAD` | Content or reference to data to process |
| `STATUS` | READY, RUNNING, DONE, or FAILED |
| `PRIORITY` | Priority level |
| `AVAILABLE_AT` | Timestamp when the job becomes eligible for claiming |
| `ATTEMPTS` | Number of claim/processing attempts so far |
| `MAX_ATTEMPTS` | Maximum allowed attempts |
| `WORKER_ID` | Worker currently holding the job |
| `CLAIM_TOKEN` | Token of the current claim |
| `CLAIMED_AT` | Claim timestamp |
| `LEASE_UNTIL` | Lease expiration timestamp |
| `COMPLETED_AT` | Completion timestamp |
| `LAST_ERROR` | Most recent error if failed |
| `CREATED_AT` | Job creation timestamp |

### 9.1. Creating an illustrative queue table

```sql
CREATE TABLE job_queue (
    job_id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_job_queue PRIMARY KEY,
    payload CLOB NOT NULL,
    status VARCHAR2(16) DEFAULT 'READY' NOT NULL,
    priority NUMBER DEFAULT 0 NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    attempts NUMBER DEFAULT 0 NOT NULL,
    max_attempts NUMBER DEFAULT 5 NOT NULL,
    worker_id VARCHAR2(64),
    claim_token RAW(16),
    claimed_at TIMESTAMP WITH TIME ZONE,
    lease_until TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR2(2000),
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_job_queue_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED')),
    CONSTRAINT ck_job_queue_attempts
        CHECK (attempts >= 0 AND max_attempts > 0)
);
```

Identity columns require Oracle 12c Release 1 or later. On older databases, use a sequence combined with INSERT or a trigger as appropriate.

### 9.2. Adding a job to the queue

```sql
INSERT INTO job_queue (
    payload,
    priority,
    available_at
)
VALUES (
    '{"type":"SEND_EMAIL","customerId":501}',
    10,
    SYSTIMESTAMP
);

COMMIT;
```

In an application, payload can be JSON, CLOB, a reference ID, or structured data stored in a separate table. Choose storage matching size, queryability, and security requirements.

### 9.3. Creating an index for job lookup

A candidate index:

```sql
CREATE INDEX ix_job_queue_claim
ON job_queue (
    status,
    available_at,
    priority DESC,
    created_at,
    job_id
);
```

The optimal index depends on status distribution, selectivity of `AVAILABLE_AT`, priority sorting, and job distribution. Because the timestamp condition is a range predicate, the index above will not necessarily eliminate a sort step. Check execution plans and measure under realistic workloads before finalizing column order.

## 10. Safe job-claiming workflow

A worker should perform three steps in a short transaction:

1. Select one or more READY jobs using `SELECT FOR UPDATE SKIP LOCKED`.
2. Update status to RUNNING, recording worker, token, and lease.
3. COMMIT to release row locks and confirm ownership via the persisted state.

Only after COMMIT does the worker perform the actual work. Never keep a transaction and row locks open while calling APIs, sending emails, processing files, or waiting on external services.

### 10.1. Claiming a single job with a PL/SQL cursor

```sql
DECLARE
    v_worker_id   CONSTANT VARCHAR2(64) := 'worker-A';
    v_job_id      job_queue.job_id%TYPE;
    v_claim_token RAW(16) := SYS_GUID();

    CURSOR c_jobs IS
        SELECT job_id
        FROM job_queue
        WHERE status = 'READY'
          AND available_at <= SYSTIMESTAMP
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c_jobs;
    FETCH c_jobs INTO v_job_id;

    IF c_jobs%FOUND THEN
        UPDATE job_queue
        SET status = 'RUNNING',
            worker_id = v_worker_id,
            claim_token = v_claim_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE,
            attempts = attempts + 1
        WHERE CURRENT OF c_jobs;

        DBMS_OUTPUT.PUT_LINE('JOB_ID=' || v_job_id);
        DBMS_OUTPUT.PUT_LINE('CLAIM_TOKEN=' || RAWTOHEX(v_claim_token));
    ELSE
        DBMS_OUTPUT.PUT_LINE('No currently claimable job');
    END IF;

    CLOSE c_jobs;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_jobs%ISOPEN THEN
            CLOSE c_jobs;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

Key points to note:

- The cursor uses `FOR UPDATE SKIP LOCKED`.
- `FETCH` retrieves an available row and the cursor holds the corresponding row lock.
- `WHERE CURRENT OF c_jobs` updates the exact current row of the cursor.
- `CLAIM_TOKEN` distinguishes this claim attempt from any other claim attempt.
- COMMIT after changing status; the worker processes the payload after this transaction.

This is an illustrative block for running in a lab schema. In real applications, worker ID and token should be passed/returned via procedure parameters or bind outputs instead of being hard-coded and printed only to DBMS_OUTPUT.

### 10.2. Claiming a batch with a cursor

When claiming up to 10 jobs:

```sql
DECLARE
    v_worker_id   CONSTANT VARCHAR2(64) := 'worker-A';
    v_batch_size  CONSTANT PLS_INTEGER := 10;
    v_claim_token RAW(16) := SYS_GUID();
    v_job_id      job_queue.job_id%TYPE;
    v_claimed     PLS_INTEGER := 0;

    CURSOR c_jobs IS
        SELECT job_id
        FROM job_queue
        WHERE status = 'READY'
          AND available_at <= SYSTIMESTAMP
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c_jobs;

    LOOP
        FETCH c_jobs INTO v_job_id;
        EXIT WHEN c_jobs%NOTFOUND;

        UPDATE job_queue
        SET status = 'RUNNING',
            worker_id = v_worker_id,
            claim_token = v_claim_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE,
            attempts = attempts + 1
        WHERE CURRENT OF c_jobs;

        v_claimed := v_claimed + 1;
        EXIT WHEN v_claimed >= v_batch_size;
    END LOOP;

    CLOSE c_jobs;
    COMMIT;

    DBMS_OUTPUT.PUT_LINE('CLAIMED=' || v_claimed);
    DBMS_OUTPUT.PUT_LINE('CLAIM_TOKEN=' || RAWTOHEX(v_claim_token));
EXCEPTION
    WHEN OTHERS THEN
        IF c_jobs%ISOPEN THEN
            CLOSE c_jobs;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

This example uses a cursor and limits FETCH iterations in PL/SQL. Do not assume you can combine any row-limiting syntax such as `FETCH FIRST 10 ROWS ONLY` directly with `FOR UPDATE`; Oracle restricts combining row-limiting clauses with `FOR UPDATE`. The cursor approach provides clean batch control.

After the block completes, the application retrieves the claim token via output/bind parameters and queries the jobs in the batch:

```sql
SELECT job_id, payload, attempts, lease_until
FROM job_queue
WHERE status = 'RUNNING'
  AND claim_token = :claim_token
ORDER BY priority DESC, created_at, job_id;
```

In a real system, do not share a single worker ID across multiple concurrently running processes. The token must be unique per claim or batch to avoid ownership confusion.

### 10.3. Why change status before COMMIT?

If a worker only runs SELECT FOR UPDATE SKIP LOCKED and then COMMITs without changing `STATUS`, the lock is released and the job remains READY. Another worker can immediately claim that same job again.

Updating READY to RUNNING in the same transaction as lock acquisition creates an atomic state transition. After COMMIT, other workers filter `STATUS = 'READY'` and therefore do not pick up the claimed job.

## 11. Processing the job after claiming

After claiming and COMMITting, the worker performs the work outside the short transaction. On success:

```sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = SYSTIMESTAMP,
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Check the number of updated rows. If 1, the worker still owns the current claim and has marked it done. If 0, the job may have been reclaimed or the token is no longer valid; the stale worker must not overwrite the new state.

### 11.1. When processing fails

You can return the job to READY with a future retry timestamp, or transition to FAILED once max attempts are exhausted:

```sql
UPDATE job_queue
SET status = CASE
                 WHEN attempts >= max_attempts THEN 'FAILED'
                 ELSE 'READY'
             END,
    available_at = CASE
                       WHEN attempts >= max_attempts THEN available_at
                       ELSE SYSTIMESTAMP + INTERVAL '1' MINUTE
                   END,
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL,
    last_error = :error_message
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

This shows a fixed one-minute backoff for illustration. Real systems often use exponential backoff, jitter, and retryable/non-retryable error classification.

If the UPDATE affects zero rows, the worker must treat its claim as expired and not overwrite the new worker's state.

### 11.2. Delete or retain results after completion?

Usually, DONE rows should be retained for a period for auditing, metrics, and incident investigation. A job can be moved to an archive table or deleted per retention policy once no longer needed for lookup.

Do not delete rows immediately if the system needs to know whether a job was already processed, requires idempotency tracking, or needs retry analysis.

## 12. Lease: recovering jobs when a worker stops

A worker can be shut down, lose connectivity, or crash after claiming a job. In that case, the row could stay in RUNNING forever without a reclamation mechanism.

A **lease** is the validity window of processing ownership. Upon claiming, the worker sets:

```sql
lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE
```

If the worker neither finishes nor renews before this timestamp, the job can be considered lease-expired and returned to the queue.

### 12.1. Finding and reclaiming lease-expired jobs

A recovery task can run periodically:

```sql
UPDATE job_queue
SET status = 'READY',
    worker_id = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    available_at = SYSTIMESTAMP
WHERE status = 'RUNNING'
  AND lease_until < SYSTIMESTAMP;

COMMIT;
```

This simple example reclaims all RUNNING jobs whose lease has expired. For high-volume workloads, process in batches and measure impact. Monitoring is needed to prevent healthy, normally running jobs from being reclaimed because the lease was too short or a worker paused briefly.

### 12.2. Renewing the lease (heartbeat)

A worker performing long-running processing can extend its lease:

```sql
UPDATE job_queue
SET lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

If the updated row count is 0, the worker no longer owns the current claim. It should stop or transition safely; it must not assume it still holds the lease.

### 12.3. Tokens prevent stale workers from overwriting new workers

Suppose:

1. Worker A claims a job with token A.
2. A hangs for a long time and the lease expires.
3. The recovery job resets the job to READY.
4. Worker B re-claims it with token B.
5. Worker A wakes up and tries to update it to DONE.

The condition `AND claim_token = :claim_token` causes A's UPDATE to match nothing because the current token is B. Thus A cannot overwrite B's state in the queue table.

A token does not by itself stop A from performing an external side effect, such as sending an email or calling an API. To limit duplicate side effects, the job needs an idempotency key, a fencing mechanism at the target system, or a side-effect protocol that supports safe retries.

### 12.4. Leases do not automatically provide exactly-once

A scenario that row locks alone cannot eliminate:

- Worker sends an email successfully.
- Worker crashes before updating status to DONE.
- Lease expires and the job is reassigned.
- New worker sends the email again.

The database cannot automatically know whether an external system already sent the email unless the two systems coordinate via a protocol. Therefore, table-based queues with retries typically provide **at-least-once** semantics; handlers must be idempotent or target services must support idempotency keys.

## 13. Why not hold row locks while processing the job?

An error-prone design:

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;

-- Call external API, process file, wait for response while transaction remains open.
```

If a worker holds a transaction for 2 minutes to call an API:

- The row is locked far longer than necessary.
- Other workers must skip that row throughout processing.
- Connections and transaction resources are tied up.
- If the batch contains multiple rows, those other rows stay locked too.
- Errors or timeouts keep locks held until the transaction terminates.

A better pattern:

```text
Short transaction:
  SELECT FOR UPDATE SKIP LOCKED
  UPDATE READY -> RUNNING + token + lease
  COMMIT

Outside transaction:
  Read payload by claim token
  Execute work

Short transaction:
  RUNNING -> DONE or READY/FAILED
  COMMIT
```

Row locks only need to protect the **claim** operation. The RUNNING status and token represent processing ownership after locks are released.

## 14. Multi-worker queue: step-by-step walkthrough

Suppose there are three READY jobs: 101, 102, 103.

| Time | Worker A | Worker B |
|---|---|---|
| T1 | Locks job 101 using SKIP LOCKED | |
| T2 | Updates 101 to RUNNING | Starts SELECT |
| T3 | Not yet COMMITted | Skips 101, locks 102 |
| T4 | COMMITs | Updates 102 to RUNNING |
| T5 | Starts processing job 101 outside transaction | COMMITs, starts processing 102 |
| T6 | Updates 101 to DONE | Updates 102 to DONE |

Neither worker claims the same row during the two concurrent claim transactions. After commit, the RUNNING status prevents other workers from selecting that row again.

If A rolls back before committing RUNNING status, row 101 returns to READY and can be claimed by another worker.

## 15. Choosing WAIT vs. SKIP LOCKED for user actions and workers

### 15.1. Screen for editing a single order

A user opens an order and wants to know immediately if someone else is editing it:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE order_id = :order_id
FOR UPDATE NOWAIT;
```

If busy, return a conflict message. This is an intuitive use case for NOWAIT.

If the user tolerates a short wait:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = :order_id
FOR UPDATE WAIT 3;
```

### 15.2. Queue-processing worker

A worker does not need to wait on a job already claimed by another worker. It can take a different job:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
  AND available_at <= SYSTIMESTAMP
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

SKIP LOCKED is better suited here because the goal is to increase parallel job throughput rather than reporting a conflict to a user.

### 15.3. When no rows are available

A worker can:

- Sleep briefly and try again.
- Use increasing backoff when the queue is empty.
- Wait on a signal/notification from a coordinator system.
- Inspect READY and RUNNING job counts to monitor load.

Do not loop SELECT SKIP LOCKED continuously without pauses, as it creates unnecessary polling load.

## 16. Considerations for ordering, fairness, and starvation

### 16.1. ORDER BY is a priority preference, not strict FIFO

```sql
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED
```

The worker selects in this order among claimable rows. If the top row in the list is currently locked, the worker skips it and takes the next job.

### 16.2. Jobs can be delayed for a long time

If a job repeatedly fails to be claimed because it is locked for a long time, or is continually preempted by higher-priority jobs, it can wait a long time. Monitor:

- Age of the oldest READY job.
- Latency from CREATED_AT to CLAIMED_AT.
- Time spent in RUNNING status.
- Number of retries.
- Number of lease-expired jobs.
- Number of FAILED jobs.

You can design priority aging, split queues by type, or cap consecutive high-priority jobs to improve fairness.

### 16.3. Large batches reduce flexibility

A worker claiming 1,000 jobs and processing them sequentially can starve other workers even though the first worker can only process a few at a time. Choose a batch size aligned with actual concurrent processing capacity.

Small batches reduce lock duration and allow more flexible work distribution, at the cost of more claim transactions. Measure against your workload.

## 17. Locking in JOIN queries

If the queue needs to read additional customer or job-type details, you can JOIN:

```sql
SELECT q.job_id,
       q.payload,
       q.priority,
       t.type_name
FROM job_queue q
JOIN job_types t
  ON t.type_id = q.type_id
WHERE q.status = 'READY'
ORDER BY q.priority DESC, q.created_at, q.job_id
FOR UPDATE OF q.status SKIP LOCKED;
```

`OF q.status` designates the queue table as the table to lock. The `STATUS` column serves to identify that table; Oracle locks the row in the table containing that column, not just the status column.

Avoid locking the lookup table `JOB_TYPES` if the worker only needs to lock jobs. When JOIN queries are complex, check `FOR UPDATE` restrictions for views, outer joins, aggregates, or other constructs for your Oracle version.

## 18. Common errors and limitations

| Error / Symptom | Common Cause | Resolution |
|---|---|---|
| `ORA-00054` | NOWAIT encountered a busy resource | Report conflict or retry with backoff |
| `ORA-30006` | WAIT timed out | Adjust timeout per SLA or handle timeout |
| `ORA-00060` | Deadlock from sessions locking resources in conflicting order | Lock in consistent order, keep transactions short, controlled retry |
| Queue returns 0 rows | Queue is empty, or all matching rows are locked / not yet due | Treat as no job currently claimable; retry later |
| Job processed twice | SELECT FOR UPDATE then COMMIT without changing status, or retry after crash | Transition READY -> RUNNING in same transaction, use idempotency |
| Job stuck in RUNNING | Worker crashed, no lease recovery | Use leases, heartbeats, and a recovery task |
| Stale worker overwrites new worker | Not checking claim token/version on completion | Guard every update with the current token |
| Low-priority jobs wait too long | SKIP LOCKED does not guarantee fairness | Priority aging, queue partitioning, and monitoring job age |
| `FOR UPDATE` fails with query | Query uses DISTINCT/GROUP BY/set operators/aggregates or non-lockable views | Lock base rows with an appropriate query |
| `SKIP LOCKED` still waits | Table lock or other wait type, not a row lock skipped by SKIP LOCKED | Check lock type and blocker |
| Batch locks too many rows | Claim batch too large or transaction uncommitted | Reduce batch size, commit immediately after claiming |
| Cannot pick up job despite READY rows | `AVAILABLE_AT`, status, or ownership conditions do not match | Check predicates, lease, and metadata |

### 18.1. ORA-00060 and locking order

A deadlock can happen if:

- Session A locks row 1 and waits for row 2.
- Session B locks row 2 and waits for row 1.

A generally useful design rule is for all workflows locking multiple rows to lock them in the same order. This does not eliminate all deadlocks, but reduces the risk. Applications still need to handle errors and retry transactions when appropriate.

### 18.2. SKIP LOCKED does not fix bad data

SKIP LOCKED only coordinates lock contention. It does not validate payloads, guarantee valid business state, or prevent duplicate processing after a worker crashes past a side effect. Queues still need constraints, valid state transitions, idempotency, and monitoring.

## 19. Performance and operational design

### 19.1. Predicates must be selective

The claim query should filter by status and availability time:

```sql
WHERE status = 'READY'
  AND available_at <= SYSTIMESTAMP
```

Without predicates, workers may scan and lock unnecessary rows.

### 19.2. Indexes for queues

Candidate index:

```sql
CREATE INDEX ix_job_queue_status_ready
ON job_queue (status, available_at, priority DESC, created_at, job_id);
```

However, a range predicate on `AVAILABLE_AT` combined with priority ordering may still require Oracle to sort. Depending on data distribution, another index or partitioning may fit better. Evaluate execution plans against realistic data.

### 19.3. Keep claim transactions short

A claim transaction should only:

1. Find rows.
2. Lock rows.
3. Update status and metadata.
4. COMMIT.

Do not call external APIs, send emails, or process files inside this transaction.

### 19.4. Use appropriately sized batches

Large batches reduce claim round-trips but cause one worker to hold more jobs, which can create imbalance if a worker is slow. Small batches increase flexibility at the cost of higher transaction overhead. Choose based on throughput and job processing time.

### 19.5. Monitor stuck rows

Metrics to track:

- READY count by age and priority.
- RUNNING count by worker.
- Jobs past lease expiration.
- Average attempts and count of jobs hitting max attempts.
- Processing latency p50/p95/p99.
- Empty claim counts.
- Lock error and retry counts.

Monitoring helps distinguish insufficient workers, slow workers, bad payloads, lock contention, and unavailable target systems.

### 19.6. Consider Oracle Advanced Queuing

For systems needing rich queue features like consumers, enqueue/dequeue, retries, delays, exception queues, and message management, consider Oracle Advanced Queuing (AQ) or an appropriate messaging solution. A custom table with SKIP LOCKED fits simple workflows needing direct schema control, provided the team builds leases, retries, retention, monitoring, and idempotency themselves.

## 20. Using NOWAIT, WAIT, and SKIP LOCKED in Java/JDBC

### 20.1. NOWAIT with PreparedStatement

```java
String sql =
    "SELECT order_id, status " +
    "FROM orders " +
    "WHERE order_id = ? " +
    "FOR UPDATE NOWAIT";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString("status");
            // Check and update in the same transaction.
        }
    }
}
```

When encountering a lock error, the driver throws `SQLException`; the application should inspect the Oracle error code rather than treating every SQL exception as a conflict.

### 20.2. WAIT n

```java
String sql =
    "SELECT order_id, status " +
    "FROM orders " +
    "WHERE order_id = ? " +
    "FOR UPDATE WAIT 5";
```

`WAIT 5` is SQL syntax. Do not concatenate user-supplied seconds directly into SQL; if dynamic configuration is needed, validate the value against a whitelist/range in the application and construct the appropriate statement.

### 20.3. Claiming from a queue via JDBC

For queues, one implementation approach is calling a PL/SQL procedure that performs the claim in a short transaction and returns the claim token. The procedure should:

- Open a `FOR UPDATE SKIP LOCKED` cursor.
- Fetch up to batch size.
- Transition status to RUNNING and attach token/lease.
- Commit, or let the transaction manager commit after the procedure finishes.
- Return the list of job IDs/token to the worker.

Do not open a `ResultSet` with FOR UPDATE and hold the connection open throughout out-of-database job processing.

### 20.4. JDBC transactions

```java
connection.setAutoCommit(false);

try {
    // Call job-claim procedure; procedure only locks and updates status.
    // Retrieve list of claimed jobs.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}

// Process payload outside the claim transaction.
```

After processing, open another short transaction to update DONE/READY/FAILED conditioned on `job_id`, `status`, and `claim_token`. If a connection pool manages transactions, follow the application's transaction manager instead of committing across multiple layers.

## 21. Comprehensive lab exercise

The following steps create a dedicated table in a lab schema. Run only if you have table creation privileges and avoid colliding with business object names.

### Step 1. Create the queue table

```sql
CREATE TABLE demo_job_queue (
    job_id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_demo_job_queue PRIMARY KEY,
    payload VARCHAR2(200) NOT NULL,
    status VARCHAR2(16) DEFAULT 'READY' NOT NULL,
    priority NUMBER DEFAULT 0 NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    worker_id VARCHAR2(64),
    claim_token RAW(16),
    claimed_at TIMESTAMP WITH TIME ZONE,
    lease_until TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_demo_job_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE'))
);
```

### Step 2. Insert some jobs

```sql
INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job A', 10);

INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job B', 20);

INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job C', 5);

COMMIT;
```

### Step 3. Session A locks the first job

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
FOR UPDATE;
```

Keep the transaction open in Session A to observe conflict.

### Step 4. Session B tries NOWAIT

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE job_id = 2
FOR UPDATE NOWAIT;
```

If Session A is holding the lock on job 2, Session B errors immediately.

### Step 5. Session B tries WAIT

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE job_id = 2
FOR UPDATE WAIT 3;
```

Hold the lock in Session A for over three seconds to observe the timeout, or COMMIT in A during the wait so B acquires the lock.

### Step 6. Session B tries SKIP LOCKED

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
FOR UPDATE SKIP LOCKED;
```

Observe that rows locked by A are skipped and other rows can be returned. After testing, COMMIT or ROLLBACK in both sessions.

### Step 7. Claim and change status in the same transaction

In Session A, run PL/SQL:

```sql
DECLARE
    v_job_id demo_job_queue.job_id%TYPE;
    v_token RAW(16) := SYS_GUID();
    CURSOR c IS
        SELECT job_id
        FROM demo_job_queue
        WHERE status = 'READY'
        ORDER BY priority DESC, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c;
    FETCH c INTO v_job_id;

    IF c%FOUND THEN
        UPDATE demo_job_queue
        SET status = 'RUNNING',
            worker_id = 'worker-lab-A',
            claim_token = v_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '2' MINUTE
        WHERE CURRENT OF c;

        DBMS_OUTPUT.PUT_LINE('JOB_ID=' || v_job_id);
        DBMS_OUTPUT.PUT_LINE('TOKEN=' || RAWTOHEX(v_token));
    END IF;

    CLOSE c;
    COMMIT;
END;
/
```

### Step 8. Inspect claimed jobs

```sql
SELECT job_id,
       payload,
       status,
       worker_id,
       claimed_at,
       lease_until
FROM demo_job_queue
ORDER BY job_id;
```

The claimed job transitions to RUNNING. Another worker filtering READY will not pick up that job again.

### Step 9. Mark completed

Use the job ID and token printed in step 7:

```sql
UPDATE demo_job_queue
SET status = 'DONE',
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = HEXTORAW(:token_hex);

COMMIT;
```

Check the updated row count. If 0, the claim may no longer belong to this worker.

### Step 10. Clean up the lab table

Only when you are sure this is a table you created and no longer need the data:

```sql
DROP TABLE demo_job_queue PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data, bypassing the recycle bin per command behavior; this is DDL with an implicit commit. Do not run on business tables or shared objects.

## 22. Rules to remember

| Need | Choice |
|---|---|
| Read a row and update in the same transaction | `SELECT ... FOR UPDATE` |
| Fail immediately when row is locked | `FOR UPDATE NOWAIT` |
| Wait for lock for a bounded time | `FOR UPDATE WAIT n` |
| Multiple workers taking different available rows | `FOR UPDATE SKIP LOCKED` |
| Lock rows of only one table in a JOIN | `FOR UPDATE OF alias.column` |
| Claim a job safely | Lock + change READY to RUNNING + token/lease + COMMIT |
| Process a long job | Execute after the claim transaction has committed |
| Worker crash | Lease timeout and reclaim mechanism |
| Prevent stale worker from overwriting after reclaim | Claim token/version condition |
| Retry job | Attempts, backoff, max attempts, FAILED status |
| Limit duplicate side effects | Idempotency key or fencing in target system |
| Keep transactions short | Never call external services while holding row locks |

## 23. Self-check questions

**Question 1.** How does `SELECT FOR UPDATE` differ from regular SELECT?

**Answer:** SELECT FOR UPDATE actively acquires row locks on selected rows to protect read-then-update operations within a transaction; regular SELECT uses read consistency and does not lock rows just to read.

**Question 2.** How does NOWAIT behave when a row is locked?

**Answer:** It returns an error immediately, typically ORA-00054, instead of waiting.

**Question 3.** What does `WAIT 5` mean?

**Answer:** Wait up to five seconds to acquire the lock; when the time expires, the statement times out.

**Question 4.** What scenario is SKIP LOCKED best suited for?

**Answer:** Multiple workers/consumers pulling work from a queue where they can skip rows currently being processed by other workers.

**Question 5.** If SKIP LOCKED returns 0 rows, does that guarantee the queue is empty?

**Answer:** No. Matching rows may currently be locked or not yet past their AVAILABLE_AT time.

**Question 6.** How long are locks from SELECT FOR UPDATE held?

**Answer:** Until the transaction's COMMIT or ROLLBACK; closing the cursor does not release locks automatically.

**Question 7.** Why must a worker update READY to RUNNING before COMMIT?

**Answer:** After COMMIT, row locks are released; the RUNNING status prevents other workers from selecting the same job again.

**Question 8.** Why not keep a transaction open while sending an email or calling an API?

**Answer:** Doing so holds row locks and connections too long, increasing contention and wait risks.

**Question 9.** What problem does a lease solve?

**Answer:** Enables job recovery if a worker crashes or fails to finish within the allotted time.

**Question 10.** What is the purpose of a claim token?

**Answer:** Identifies the current claim attempt; a stale worker cannot update status if the token has changed after the job was reclaimed.

**Question 11.** Does a claim token guarantee external side effects happen only once?

**Answer:** No. You need idempotency keys, fencing, or a target-system protocol; queues with retries typically provide at-least-once semantics.

**Question 12.** Does SKIP LOCKED guarantee strict FIFO?

**Answer:** No. A locked high-priority row can be skipped in favor of processing a subsequent row.

**Question 13.** Does `FOR UPDATE OF q.status` lock only the STATUS column, or what does it lock?

**Answer:** It specifies that the table containing the STATUS column is to be locked; Oracle locks the row of that table, not just the individual column.

**Question 14.** Can you always use FETCH FIRST 10 ROWS ONLY together with FOR UPDATE?

**Answer:** Do not assume so. Oracle restricts combining row-limiting clauses with FOR UPDATE; use a cursor and limit FETCH count to control batches.

## 24. Conclusion

`SELECT ... FOR UPDATE` lets an application acquire row locks right when reading data. **`NOWAIT`** returns an error immediately if the lock cannot be acquired; **`WAIT n`** waits for a bounded duration; **`SKIP LOCKED`** skips locked rows to proceed with available ones. NOWAIT and WAIT suit operations needing immediate conflict feedback or bounded waiting, while SKIP LOCKED is a key option for multi-worker table queues.

A safe queue is more than just SELECT SKIP LOCKED. A worker must lock rows, transition READY to RUNNING, record worker/token/lease, and COMMIT in a short transaction. Long work runs afterward; upon success or failure, the worker updates status guarded by the current token. Leases enable recovering abandoned jobs, while idempotency/fencing protect side effects when a job is retried.

SKIP LOCKED increases parallel throughput, but it does not guarantee strict FIFO, does not skip every kind of lock, and does not automatically provide exactly-once delivery. Choose appropriate batch sizes, keep transactions short, monitor leases and job age, design retries with backoff, and verify execution plans and behavior on the exact Oracle version you deploy.
