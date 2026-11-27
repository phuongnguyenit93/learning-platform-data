# Building Job Queues with Row Locks and Delivery Guarantee Limits in PostgreSQL

When an API needs to send emails, synchronize data, generate thumbnails, or export reports, handling everything inside the HTTP request can keep the user waiting too long and tie the request to external services. One solution is to **store work in a job queue** for workers to execute later.

PostgreSQL can store a queue using a table and provides **row-level locking**, especially `SELECT ... FOR UPDATE SKIP LOCKED`, allowing multiple workers to fetch jobs without waiting together on a locked row.

However, a clear distinction must be made:

- **Exclusively selecting a job within a transaction** does not mean the job will be executed only once.
- **Row locks** exist only for the duration of a transaction; they are not minutes-long processing rights.
- **A lease** is simply application data stored in the table to manage time-bounded processing ownership.
- **Retries** prevent losing jobs after a crash, but can cause side effects to be executed more than once.
- **Exactly-once effect** in systems outside PostgreSQL requires idempotency/fencing or an appropriate integration protocol; it does not come automatically from `SKIP LOCKED` alone.

This lesson belongs to the **Locks** chapter of the *Database Engine Relational PostgreSQL* module, covering queue table design, atomic claims, heartbeats, ack/fail/requeue, reapers, dead-lettering, retries, performance observability, and the limits around ordering, fairness, and reliability.

## 1. What Does a Job Queue Do?

A simple architecture:

~~~text
                 PostgreSQL
HTTP request --> BEGIN
                 INSERT order
                 INSERT queue_job
                 COMMIT
                      |
                      v
                 jobs: pending
                      |
             +--------+--------+
             |        |        |
           Worker A Worker B Worker C
             |        |        |
             +--------+--------+
                      |
                External API
                      |
                ACK succeeded
~~~

The API only writes a committed **job description**. Workers pick up the job, process it, and update the result.

### 1.1. Minimal States

A job can transition through:

~~~text
          +---------+
enqueue ->| pending |<----+
          +----+----+     |
               | claim    | retry/backoff
               v          |
          +---------+     |
          | running |-----+
          +----+----+
               |
        +------+--------+
        |               |
        v               v
   succeeded           dead
~~~

A `cancelled` state can be used when the business workflow allows cancelling a job before execution.

### 1.2. Jobs vs. Events

A queue typically wants **one worker processing one job at a time**. An event log may require multiple consumer groups, each receiving the same event. A simple queue table does not natively provide consumer offsets, replay, fan-out, or partitioned ordering like a dedicated message broker.

### 1.3. When Is PostgreSQL a Good Fit?

It is especially useful when the application already uses PostgreSQL and wants to enqueue within the same business transaction, with workload volume suited to server capacity and a limited number of consumer groups.

## 2. Race Condition When Only Selecting `pending`

Unsafe pattern:

~~~sql
SELECT job_id, payload
FROM jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 1;
~~~

Two workers can `SELECT` before either one runs `UPDATE`:

~~~text
T1 - Worker A                     T2 - Worker B
--------------------------------  -----------------------------
SELECT pending -> job 42          SELECT pending -> job 42
Send email for job 42             Send email for job 42
UPDATE status = succeeded         UPDATE status = succeeded
~~~

The queue has allowed one job to execute twice. A plain `SELECT` does not transfer job ownership.

**Solution:** select the job under a row lock and update its status in the same transaction, or use a single atomic claim statement.

## 3. Row-Level Locks and `FOR UPDATE`

~~~sql
BEGIN;

SELECT job_id, payload
FROM jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 1
FOR UPDATE;

-- UPDATE status immediately within the transaction.

COMMIT;
~~~

`FOR UPDATE` requests row locks on the selected rows.

### 3.1. When Another Worker Selects the Same Row

Worker B also using `FOR UPDATE` on the same row may **have to wait** for Worker A to release the lock. With many workers and one job at the head of the queue, waiting together can cause a bottleneck.

### 3.2. Locks Do Not Modify Data by Themselves

If T1 runs `SELECT FOR UPDATE` and then `ROLLBACK`, the status remains `pending`; there is no durable claim. You must write `status='running'` before `COMMIT` if ownership must be recorded.

### 3.3. Locks End with the Transaction

If a worker runs `SELECT FOR UPDATE` in autocommit mode and returns the connection to the pool, the lock may already be released before the worker begins calling the API. You cannot rely on an expired lock to protect external processing.

### 3.4. `UPDATE` Also Acquires the Needed Locks

To reduce round trips, an `UPDATE ... FROM candidate` statement with a `SELECT FOR UPDATE` CTE is usually cleaner than running `SELECT` followed by `UPDATE` as two separate statements from the application.

## 4. `FOR UPDATE`, `NOWAIT`, and `SKIP LOCKED`

| Syntax | When Encountering a Row with a Conflicting Row Lock | Usage |
|---|---|---|
| `FOR UPDATE` | Wait until the lock is granted | Need the exact selected row |
| `FOR UPDATE NOWAIT` | Fail immediately with an error | Want immediate contention detection |
| `FOR UPDATE SKIP LOCKED` | Skip rows that are currently locked | Queue allows picking a different job |

Example:

~~~sql
SELECT job_id
FROM jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

If job 42 is locked, the worker can pick job 43 instead of waiting.

### 4.1. `SKIP LOCKED` Provides an Inconsistent View

By skipping locked rows, the result set is no longer a complete list under normal snapshot/query semantics. This is an **intentional trade-off** for worker queues, not a desirable property for aggregate reporting.

### 4.2. No FIFO Guarantee

Worker A claims job 42 first, taking 30 seconds; Worker B claims job 43 later, finishing in 200ms. Completion order is 43 then 42.

Even claim order can diverge from priority order at a given moment because `SKIP LOCKED` skips currently locked rows.

### 4.3. Does Not Skip All Table Locks

`SKIP LOCKED` applies to row-level locking under supported mechanisms. `SELECT`/`UPDATE` still require their corresponding table locks and can be blocked by DDL holding stronger locks. Do not assume `SKIP LOCKED` makes a queue immune to all lock waits.

## 5. Two Ways to Execute a Job

### 5.1. Hold Transaction and Lock Throughout Processing

~~~text
BEGIN
SELECT job FOR UPDATE
CALL email service (takes 5 seconds)
UPDATE job succeeded
COMMIT
~~~

Problems:

- Holds row locks and database connections for seconds or minutes.
- Long transactions create MVCC/VACUUM pressure.
- External HTTP side effects do not roll back with PostgreSQL.
- A dead worker or stalled network call makes it harder for other transactions to proceed.
- Connection pool exhaustion can trigger cascading failures.

You should not hold a database transaction across a slow network call by default.

### 5.2. Fast Claim, External Work, Fast Ack

~~~text
BEGIN -> claim pending to running -> COMMIT
           |
           v
       HTTP / CPU work
           |
           v
BEGIN -> ack running to succeeded -> COMMIT
~~~

This is the primary model in this lesson. Row locks are held briefly, but **leases, tokens, heartbeats, retries, and a reaper** are required to recover from worker crashes.

## 6. Queue Schema with Lease Management

The examples use a **test database** and `CREATE SCHEMA` privileges. If `queue_lab` already exists, use another name; do not `DROP` data that does not belong to this lesson.

~~~sql
CREATE SCHEMA queue_lab;

CREATE TABLE queue_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_name TEXT NOT NULL DEFAULT 'default',
    dedupe_key TEXT,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'running', 'succeeded', 'dead', 'cancelled'
        )),

    priority INTEGER NOT NULL DEFAULT 0,
    run_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5
        CHECK (max_attempts >= 1),

    claimed_by TEXT,
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,

    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT uq_queue_dedupe
        UNIQUE (queue_name, dedupe_key),

    CONSTRAINT ck_claim_state
        CHECK (
            (
                status = 'running'
                AND claimed_by IS NOT NULL
                AND claim_token IS NOT NULL
                AND lease_until IS NOT NULL
            )
            OR
            (
                status <> 'running'
                AND claimed_by IS NULL
                AND claim_token IS NULL
                AND lease_until IS NULL
            )
        )
);
~~~

### 6.1. Key Columns Explained

| Column | Role |
|---|---|
| `job_id` | Job identifier |
| `queue_name` | Worker group / queue name |
| `dedupe_key` | Key to prevent duplicate enqueues |
| `job_type` | Execution handler |
| `payload` | Data or reference |
| `status` | Job lifecycle state |
| `priority` | Job selection priority |
| `run_at` | Scheduled readiness timestamp |
| `attempts/max_attempts` | Attempt count management |
| `claimed_by` | Worker owning the claim |
| `claim_token` | Identifier for a specific claim attempt |
| `claim_version` | Monotonically increasing processing ownership version |
| `lease_until` | Claim expiration timestamp |
| `last_error` | Error diagnostics |
| `created_at/updated_at/completed_at` | Observability and retention |

### 6.2. What Does the Constraint Guarantee?

The constraint guarantees that a `running` row has a worker, token, and lease, while a non-`running` row has cleared those claim fields. However, the constraint does not know whether the worker is actually alive, whether the HTTP API was already called, or whether the job was executed exactly once.

### 6.3. `UNIQUE` and `NULL`

With the default unique constraint, multiple rows with `dedupe_key=NULL` are still allowed. To enforce enqueue idempotency, the business contract must require an explicit key or add an appropriate constraint.

## 7. Indexes for Workers

~~~sql
CREATE INDEX idx_jobs_ready
ON queue_lab.jobs (
    queue_name,
    priority DESC,
    run_at ASC,
    job_id ASC
)
WHERE status = 'pending';
~~~

This index helps find `pending` jobs by queue, priority, and scheduled time.

### 7.1. Column Order Trade-Off

Having `priority DESC` before `run_at` can help `ORDER BY`, but if there are many high-priority jobs that are **not yet due**, the query may have to scan many entries. Depending on the data, a different index or priority strategy may be needed.

### 7.2. Expired `running` Jobs

~~~sql
CREATE INDEX idx_jobs_expired
ON queue_lab.jobs (lease_until)
WHERE status = 'running';
~~~

Useful for the reaper to find expired `running` jobs.

### 7.3. Do Not Use Dynamic Time in a Partial Index Predicate

Do not define a partial index with `WHERE run_at <= now()`. Index predicates require expressions with appropriate immutability; current time changes continuously. Index the column and compare against the timestamp when the query runs.

### 7.4. Indexes Have a Cost

Queues update `status` frequently, so extra indexes increase WAL, dead tuples, and maintenance overhead. Create indexes only for actual queries and measure with `EXPLAIN`.

## 8. Enqueueing Jobs

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload, priority
)
VALUES (
    'emails',
    'welcome:user:1001',
    'send_welcome_email',
    '{"user_id":1001, "template":"welcome"}'::jsonb,
    10
)
RETURNING job_id, status, attempts, run_at;
~~~

The result has `status = 'pending'`, `attempts = 0`, and the default execution time.

### 8.1. Scheduled Jobs

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload, run_at
)
VALUES (
    'reports',
    'monthly-report:2026-11',
    'generate_monthly_report',
    '{"month":"2026-11"}'::jsonb,
    TIMESTAMPTZ '2026-12-01 01:00:00+07'
);
~~~

Workers will not claim it before `run_at` if the query enforces the readiness condition properly.

### 8.2. Enqueueing Within the Business Transaction

~~~sql
BEGIN;

-- Example in a real schema:
-- INSERT INTO orders (...) VALUES (...) RETURNING order_id;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails',
    'order-confirmation:ORD-1001',
    'send_order_confirmation',
    '{"order_code":"ORD-1001"}'::jsonb
);

COMMIT;
~~~

If both the order and the job are written in **the same transaction**, both changes commit or roll back together. This is the basis of the transactional outbox in appropriate scenarios.

## 9. Preventing Duplicate Enqueues with `ON CONFLICT`

A client may retry a request due to a lost response even though the first transaction already committed.

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails',
    'welcome:user:1001',
    'send_welcome_email',
    '{"user_id":1001}'::jsonb
)
ON CONFLICT (queue_name, dedupe_key)
DO NOTHING
RETURNING job_id;
~~~

If the key already exists, `INSERT` creates no new row and `RETURNING` returns no rows.

### 9.1. Dedupe Keys Must Carry Business Meaning

Examples:

- `welcome:user:1001` — one welcome email per user.
- `sync-order:1001:v3` — sync a specific order version.
- `report:2026-11` — report for a given period.

Do not use `'email'` as the key for all jobs.

### 9.2. Enqueue Deduplication Is Different from Execution Deduplication

A unique key only prevents creating **two job rows** with the same key. That single job can still be processed multiple times if a worker crashes before ack and the job is retried.

### 9.3. Retention of Dedupe Keys

If `succeeded` rows are kept forever, the same key remains blocked from re-enqueueing. If rows are deleted early, the key becomes available again. The idempotency key retention window must match business rules and the retry window.

## 10. Atomic Claim Statement with `SKIP LOCKED`

A worker claims one job from the `emails` queue:

~~~sql
BEGIN;

WITH candidate AS MATERIALIZED (
    SELECT job_id
    FROM queue_lab.jobs
    WHERE queue_name = 'emails'
      AND status = 'pending'
      AND run_at <= statement_timestamp()
      AND attempts < max_attempts
    ORDER BY priority DESC, run_at ASC, job_id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_lab.jobs AS j
SET status = 'running',
    claimed_by = 'worker-A',
    claim_token = gen_random_uuid(),
    claim_version = j.claim_version + 1,
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    attempts = j.attempts + 1,
    updated_at = statement_timestamp()
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.payload,
    j.claim_token,
    j.claim_version,
    j.attempts,
    j.lease_until;

COMMIT;
~~~

This example uses `MATERIALIZED` (PostgreSQL 12+) and `gen_random_uuid()` (built into modern PostgreSQL; on older versions check the corresponding extension).

### 10.1. Execution Flow

1. Select `pending` jobs in the right queue that are due.
2. Skip jobs that have exceeded `max_attempts`.
3. Order by priority, scheduled time, and `job_id`.
4. Acquire row locks and skip rows that are currently locked.
5. Pick one candidate.
6. Transition to `running`, generate a token, and increment attempt/version.
7. Return payload and ownership information.
8. `COMMIT` quickly to release the row lock.

### 10.2. Why Is `RETURNING` Needed?

The worker must receive the exact **claim_token** for that attempt and use it for heartbeat/ack. Never derive the token from `job_id` or send a fixed token.

### 10.3. When No Job Is Ready

`UPDATE` returns 0 rows. This is normal; the worker can sleep for a short interval before polling again rather than busy-looping continuously.

### 10.4. Why Use `statement_timestamp()`?

`now()` is the transaction start time; a transaction opened earlier can produce an outdated timestamp. `statement_timestamp()` provides the start time of the currently executing SQL statement, which is usually more appropriate for claims/heartbeats performed in very short transactions.

## 11. Lab: Two Workers and Locking the Same Row

Open **two separate PostgreSQL connections**.

### 11.1. Prepare Two More Jobs

~~~sql
INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES
    ('emails', 'lab:mail:A', 'send_mail', '{"to":"A"}'::jsonb),
    ('emails', 'lab:mail:B', 'send_mail', '{"to":"B"}'::jsonb);
~~~

### 11.2. Session A

~~~sql
BEGIN;

SELECT job_id, dedupe_key
FROM queue_lab.jobs
WHERE queue_name = 'emails'
  AND status = 'pending'
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE;

-- Do not COMMIT yet.
~~~

### 11.3. Session B

~~~sql
BEGIN;

SELECT job_id, dedupe_key
FROM queue_lab.jobs
WHERE queue_name = 'emails'
  AND status = 'pending'
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

If another eligible job exists, B typically receives a row **different from the one A has locked** instead of waiting.

### 11.4. Cleanup

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

Because this only ran `SELECT FOR UPDATE` followed by `ROLLBACK`, it was a locking experiment rather than a durable claim.

### 11.5. Test a Real Claim

Have each session run the `UPDATE` claim statement from section 10 with a different `claimed_by`. Verify that the two jobs are claimed separately, or that a worker receives 0 rows when no `pending` jobs remain.

## 12. Claim and Execution Are Two Separate Transactions

A typical worker flow:

~~~text
Transaction A:
  claim pending -> running
  COMMIT

No open DB transaction:
  call HTTP API / process file

Transaction B:
  ack running -> succeeded using token
  COMMIT
~~~

### 12.1. Why Not Hold the Lock Across the HTTP Call?

Long row locks and transactions tie up connections, increase contention, and put pressure on MVCC. External side effects also cannot roll back with PostgreSQL if the HTTP call has already succeeded.

### 12.2. Why Is the `running` Status Needed?

Once the claim `COMMIT`s, the row lock expires. If the job stayed `pending`, another worker could pick it up. `status='running'` is durable state recording that the job has been assigned.

### 12.3. What If the Worker Dies Right After Claiming?

The job would remain stuck in `running` without a lease/reaper. That is why the claim must record a processing deadline and the system needs a recovery mechanism.

## 13. Lease: Time-Bounded Processing Ownership

A lease consists of:

~~~text
job_id:       42
status:       running
claimed_by:   worker-A
claim_token:  token for this claim attempt
lease_until:  timestamp when this claim expires
~~~

### 13.1. A Lease Is Not a PostgreSQL Row Lock

A lease does not hold a lock after the claim transaction commits; it is purely an application-level rule enforced via a timestamp column and token.

### 13.2. Lease Expiration Does Not Prove the Worker Is Dead

The worker might be paused, temporarily disconnected, in a GC pause, or CPU-starved. An expired lease does not mean the old external API call has definitely stopped.

### 13.3. Lease Duration

- Too short: still-running jobs get requeued prematurely, increasing duplicate execution.
- Too long: job recovery takes longer when a worker crashes.
- Appropriate: sized according to P95/P99 job duration, heartbeat cadence, and recovery SLA.

## 14. Heartbeat to Extend a Lease

After receiving the actual `job_id`/token from `RETURNING`, the worker can call:

~~~sql
UPDATE queue_lab.jobs
SET lease_until = statement_timestamp() + INTERVAL '2 minutes',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, lease_until;
~~~

**The UUID and `job_id` in the example are illustrative placeholders**; always bind the actual values returned by the claim. Never use a fixed token for every job.

### 14.1. Why Check the Token?

If A loses its lease and B reclaims the job, B receives a different token. A must not be allowed to extend ownership for an old attempt.

### 14.2. Why Check That `lease_until` Is Still Valid?

A worker waking up after its lease expired should not renew its own lease without a reclaim protocol, because a reaper or another worker may have already begun recovery.

### 14.3. Heartbeat Returns 0 Rows

This indicates the worker **no longer holds valid ownership** or the job has changed state. The worker must re-check rather than blindly proceeding to ack.

## 15. Acking Success with Claim Verification

~~~sql
UPDATE queue_lab.jobs
SET status = 'succeeded',
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    completed_at = statement_timestamp(),
    updated_at = statement_timestamp(),
    last_error = NULL
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, status, completed_at;
~~~

Again: use the actual ID/token from that claim attempt, not the dummy UUID.

### 15.1. `UPDATE` Returns 1 Row

The database applied the ack in the statement. If using an explicit transaction, consider the final outcome successful only after `COMMIT`.

### 15.2. `UPDATE` Returns 0 Rows

This can happen because of a wrong token, the job already transitioned to `succeeded`/`dead`/`cancelled`, the lease expired, another worker reclaimed it, or `job_id` does not exist. Never remove the ownership predicates to "force ack."

### 15.3. An Ack Does Not Prove the Email Was Sent Only Once

The job may have called the external service twice before acking once. The table only records job state; it does not prove the count of external side effects outside the database.

## 16. Retry and Dead-Letter

If a job encounters a transient error, the worker can return it to `pending` with a future `run_at`; if attempts are exhausted, transition it to `dead`.

~~~sql
UPDATE queue_lab.jobs
SET status = CASE
        WHEN attempts >= max_attempts THEN 'dead'
        ELSE 'pending'
    END,
    run_at = CASE
        WHEN attempts >= max_attempts THEN run_at
        ELSE statement_timestamp() + INTERVAL '15 seconds'
    END,
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'HTTP 503 from external service',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'running'
  AND claimed_by = 'worker-A'
  AND claim_token =
      '00000000-0000-0000-0000-000000000001'::uuid
  AND lease_until > statement_timestamp()
RETURNING job_id, status, attempts, max_attempts, run_at;
~~~

### 16.1. `attempts` Is Incremented on Claim

`attempts` in this schema tracks the number of **claim attempts**, not necessarily the number of HTTP calls. A worker might retry calling a service multiple times within a single claim.

### 16.2. Backoff and Jitter

Example:

~~~text
Attempt 1 fails -> retry after 10s
Attempt 2 fails -> retry after 30s
Attempt 3 fails -> retry after 2 minutes
Attempt 4 fails -> retry after 10 minutes
Reached max_attempts -> dead
~~~

Jitter helps prevent many failing jobs from retrying in lockstep at the exact same moment.

### 16.3. Transient vs. Permanent Errors

- HTTP 429/503, timeouts: can be retried.
- Invalid payload, permanently missing prerequisite data: transition to `dead` early when appropriate.
- Network timeout during a payment call: **unknown outcome** — do not simply retry without idempotency/reconciliation.

### 16.4. Dead-Letter Does Not Mean Immediate Deletion

Keep enough error context for investigation, alerting, and controlled replay. Do not infinitely loop a failing job and consume worker capacity.

## 17. Reaper to Recover Expired Leases

If a worker dies after claiming without acking, a `running` job could remain stuck indefinitely. A reaper must run periodically:

~~~sql
UPDATE queue_lab.jobs
SET status = CASE
        WHEN attempts >= max_attempts THEN 'dead'
        ELSE 'pending'
    END,
    run_at = CASE
        WHEN attempts >= max_attempts THEN run_at
        ELSE statement_timestamp() + INTERVAL '5 seconds'
    END,
    claimed_by = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = COALESCE(
        last_error,
        'Lease expired before acknowledgement'
    ),
    updated_at = statement_timestamp()
WHERE status = 'running'
  AND lease_until <= statement_timestamp()
RETURNING job_id, status, attempts, run_at;
~~~

### 17.1. Why Is a Reaper Required?

Row locks from the claim expired after `COMMIT`. An expired lease **does not automatically change the row's status**. An active `UPDATE` is needed to return the job to `pending` or move it to `dead`.

### 17.2. Contention Between Heartbeat and Reaper

If a heartbeat renews the lease before the reaper processes the row, the reaper evaluates the expiration condition against the updated state. If the reaper already reset the row, a stale heartbeat whose token/status no longer matches will return 0 rows.

### 17.3. Running the Reaper in Batches

With millions of jobs, do not hold one giant transaction updating all expired rows. Use a CTE to select a batch with `LIMIT n FOR UPDATE SKIP LOCKED`, then `UPDATE`, `COMMIT`, and loop within a bounded budget.

### 17.4. The Reaper Knows Nothing About External Effects

An email might have been sent successfully before the worker crashed prior to acking. The reaper retries the job, which can send the email again. This is why idempotency must be designed into the handler and destination.

## 18. Stale Workers and Fencing

Timeline:

~~~text
t0: Worker A claims job 42, token A1, version 7.
t1: A is paused or loses network connectivity, stopping heartbeats.
t2: A's lease expires; reaper requeues the job.
t3: Worker B claims job 42, token B1, version 8.
t4: A wakes up and attempts to ack or call the API.
~~~

### 18.1. Tokens Block Stale Acks in PostgreSQL

An ack with `WHERE claim_token=A1` returns 0 rows after B claims the job with token B1. This protects the job state in the database.

### 18.2. Version as a Fencing Number

`claim_version` increases from 7 to 8. If an external resource supports comparing version numbers and rejecting older versions, it can prevent A from executing a stale side effect after B has taken over.

### 18.3. Tokens Do Not Automatically Block External APIs

If the target API does not support idempotency or fencing, A can still complete the external request even though the database rejects its ack. Never confuse database ownership with physical control over an external process or HTTP call.

### 18.4. What Should a Worker Do When It Loses Ownership?

Stop any steps that can be safely aborted, assess what effects may have occurred, and do not commit DB state with the stale token. For non-cancellable operations, an idempotency/reconciliation protocol is required.

## 19. Delivery Semantics: At-Most-Once, At-Least-Once, Exactly-Once

| Term | Practical Meaning | Trade-Off |
|---|---|---|
| At-most-once attempt | Never retry after handing off a job | Can lose jobs if a worker crashes |
| At-least-once attempt | Retry when unacked, within policy/limits | Can execute jobs multiple times |
| Exactly-once effect | Final effect occurs only once | Requires coordination across the entire target system |

### 19.1. The Critical Crash Window

~~~text
Claim job -> COMMIT
Call payment API -> provider already charged
Worker crashes before ACK
Reaper -> pending
Worker B calls payment API again
~~~

If the provider has no idempotency key, there is a risk of double charging.

### 19.2. Why Can't Row Locks Solve This?

A database transaction does not encompass an external provider's commit. A lock on a `jobs` row cannot roll back or intercept a request already sent to the provider.

### 19.3. "At-Least-Once" Also Has Conditions

A design requires durable storage, workers continuing to poll, a reaper, a retry policy, processing capacity, and monitoring. If all workers stop permanently or a job becomes `dead` after `max_attempts`, you cannot promise every job will definitely finish.

### 19.4. Enqueue Deduplication Is Different from Execution Idempotency

A unique dedupe key only prevents creating duplicate jobs. That job can still be claimed multiple times. The handler must be able to tell whether the same operation has already been performed.

## 20. Idempotent Handlers

An idempotent operation for the same **logical operation ID** produces a final result that is not duplicated when repeated.

### 20.1. Wrong Pattern: Direct Balance Deduction

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
~~~

On retry, the balance may be deducted again.

### 20.2. Writing a Ledger with a Unique Operation Key

~~~sql
CREATE TABLE queue_lab.debit_ledger (
    debit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_key TEXT NOT NULL UNIQUE,
    account_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

If the account balance also resides in the same PostgreSQL database, you can structure a transaction to `INSERT` into the ledger and only `UPDATE` the balance if the operation key is new. The ledger entry and the balance change must commit together; on conflict, do not deduct again.

This illustrates the principle, not a complete accounting system solved by a single table.

### 20.3. Idempotency Keys Must Be Stable Across Retries

Pass a business-stable `operation_key` or `dedupe_key` to the external API. Never use `claim_token` as an idempotency key if it changes on every claim, causing the provider to treat retries as brand-new transactions.

### 20.4. Check Key Retention

A provider may only retain idempotency keys for a limited period. If a job retries after that window expires, the side effect can still happen again. The recovery window and key TTL must be compatible.

## 21. Transactional Outbox

A common bug:

~~~text
COMMIT order
Application crashes
Fails to INSERT email job
~~~

If the job is inserted in the **same transaction** as the business data, there is no commit gap between the two steps.

~~~sql
BEGIN;

-- INSERT INTO orders ... RETURNING order_id;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'events',
    'order-created:ORD-1001',
    'publish_order_created',
    '{"order_code":"ORD-1001"}'::jsonb
);

COMMIT;
~~~

### 21.1. Outbox Does Not Automatically Equal Exactly-Once Publishing

A worker that publishes a message to a broker and crashes before acking can still publish it again. Consumers or downstream systems still need idempotency.

### 21.2. When to Separate Outbox and Jobs?

If the application has multiple consumer groups, long replay/retention, or broadcast workflows, the outbox and worker queue may need to be separated into two distinct models.

## 22. Priority, Fairness, and Ordering

The claim query:

~~~sql
ORDER BY priority DESC, run_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED
~~~

only defines **candidate evaluation order**.

### 22.1. No Strict FIFO

An earlier job may be locked, allowing a later job to be claimed first. A faster worker may finish before a slower one. Retries can put an older job back behind newer ones.

### 22.2. Starvation

If high-priority jobs arrive continuously, low-priority jobs can wait indefinitely. You may need aging, quotas, dedicated worker pools per queue/priority, or job age SLAs.

### 22.3. Per-Customer Ordering

If job B for the same customer **must** run after job A, `SKIP LOCKED` across the entire queue does not guarantee this. You need a per-key protocol: sharding/partitioning workers, a guard row, a sequence watermark, or an explicit dependency structure.

### 22.4. `job_id` Is Not Completion Order

`IDENTITY`/sequences can have gaps, and ID allocation order does not prove `COMMIT` or completion order.

## 23. Appropriate Isolation Levels

### 23.1. `READ COMMITTED`

Queue claims typically use `READ COMMITTED` with short transactions. When multiple writers contend, row locks and `UPDATE` predicates work together to prevent two workers from committing claims on the same `pending` row.

### 23.2. `REPEATABLE READ`

Holding a fixed transaction snapshot is often unhelpful for polling queues; concurrent updates after the snapshot started can trigger serialization/concurrent update errors. Do not assume this isolation level makes a queue safer in every respect.

### 23.3. `SERIALIZABLE`

When transactions must preserve multi-row invariants, Serializable Snapshot Isolation may be required, but SQLSTATE `40001` must be retried for **the entire transaction**.

### 23.4. `SKIP LOCKED` Does Not Replace Isolation

It only governs how **an obstructed row lock request** is handled; it does not replace snapshot semantics or guarantee serializability.

## 24. Claiming a Batch

To reduce round trips:

~~~sql
BEGIN;

WITH picked AS MATERIALIZED (
    SELECT job_id
    FROM queue_lab.jobs
    WHERE queue_name = 'emails'
      AND status = 'pending'
      AND run_at <= statement_timestamp()
      AND attempts < max_attempts
    ORDER BY priority DESC, run_at, job_id
    LIMIT 10
    FOR UPDATE SKIP LOCKED
)
UPDATE queue_lab.jobs AS j
SET status = 'running',
    claimed_by = 'worker-B',
    claim_token = gen_random_uuid(),
    claim_version = j.claim_version + 1,
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    attempts = j.attempts + 1,
    updated_at = statement_timestamp()
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING j.job_id, j.job_type, j.payload,
          j.claim_token, j.claim_version;

COMMIT;
~~~

### 24.1. Batch Size Is Bounded by Lease Duration

If you claim 100 jobs, each takes 10s, and they are processed sequentially, jobs near the end will lose their lease before their turn arrives. Claim a batch size matched to worker concurrency slots and heartbeat cadence.

### 24.2. `RETURNING` Does Not Promise Row Order

`UPDATE RETURNING` does not guarantee returning rows in the `ORDER BY` order from `picked`. If payload ordering after claiming matters, sort explicitly in the application.

## 25. Polling and `LISTEN`/`NOTIFY`

A worker can poll:

~~~text
while running:
    claim up to N jobs
    if no job:
        sleep with bounded backoff
    else:
        process jobs
~~~

Do not run tight `SELECT` loops without sleeping on an empty queue, as that wastes CPU and database connections.

### 25.1. `LISTEN`/`NOTIFY` for Faster Wakeups

A worker can run:

~~~sql
LISTEN job_wakeup;
~~~

A producer can run:

~~~sql
BEGIN;

INSERT INTO queue_lab.jobs (
    queue_name, dedupe_key, job_type, payload
)
VALUES (
    'emails', 'lab:wakeup:1',
    'send_mail', '{"to":"demo"}'::jsonb
);

SELECT pg_notify('job_wakeup', 'emails');

COMMIT;
~~~

### 25.2. `NOTIFY` Is Not Durable Like the Queue

If a worker disconnects or is not yet `LISTEN`ing, it can miss notifications. The job row itself remains safely stored in the table once the enqueue transaction commits.

**`NOTIFY` is a wakeup signal; periodic polling must still exist as a fallback for recovery.**

### 25.3. One `NOTIFY` Does Not Correspond 1-to-1 with One Job

Multiple jobs may arrive before a worker wakes up, or a worker may wake up and find no eligible jobs because another worker claimed them. Workers still need to query the queue and handle the actual state.

## 26. Crash Windows

| Crash Point | Possible State | Required Handling |
|---|---|---|
| Before enqueue `COMMIT` | Job not committed | Producer retry with idempotency |
| After enqueue `COMMIT` | `pending` | Workers can claim it |
| During claim transaction before `COMMIT` | Claim rolled back | Job can be claimed again |
| After claim `COMMIT`, before external call | `running` | Lease expires and reaper recovers |
| During external call | `running` | Outcome may be unknown |
| After external effect, before ack | `running` | Retry may repeat the effect |
| During ack transaction, before `COMMIT` | Ack may roll back | Idempotency still required |
| After ack `COMMIT` | `succeeded` | Monitoring and retention |

### 26.1. Crashing After Side Effects Is the Core Scenario

You cannot "lock one more row" to guarantee an email or payment provider never duplicates work across every failure scenario. You need a stable operation ID and deduplication at the target.

### 26.2. Unknown Ack Outcome

A connection can drop after the ack `COMMIT` succeeded but before the client received the response. Workers should not assume an ack failed purely from a dropped packet; check current state or handle idempotently.

## 27. Cancelling Jobs

~~~sql
UPDATE queue_lab.jobs
SET status = 'cancelled',
    updated_at = statement_timestamp()
WHERE job_id = 42
  AND status = 'pending'
RETURNING job_id, status;
~~~

### 27.1. Pending Jobs

If a job has not been claimed yet, the `status` predicate makes cancellation safe against the current state.

### 27.2. Running Jobs

If a job is currently calling an external API, updating the DB status does not stop the thread or abort the HTTP request. You need a cancellation protocol: workers polling a cancellation flag, safe cancel contracts with providers, or compensation logic when cancellation is impossible.

### 27.3. Concurrent Cancel and Claim

Two transactions contend on the same row. Both must inspect the updated/returned row count; never assume both branches succeeded.

## 28. Dead-Lettering and Replay

A repeatedly failing job needs a retry threshold, e.g. `max_attempts=5`. After that:

~~~text
status = dead
~~~

### 28.1. Do Not Delete Dead Jobs Immediately

Retain them long enough to investigate, classify errors, verify external outcomes, and fix payloads or handlers.

### 28.2. Manual Replay Must Be Controlled

Never blindly flip all `dead` jobs back to `pending` without checking whether external side effects already occurred. This is especially critical for payments, marketing emails, and irreversible actions.

### 28.3. Permissions and Auditing

Replay requires least-privilege access, an action reason, an operator audit trail, and bounded retry limits. `payload` and `last_error` may contain sensitive data.

## 29. Performance: Update Churn and `VACUUM`

Queues involve frequent state transitions:

~~~text
pending -> running -> succeeded
pending -> running -> pending -> running -> dead
~~~

Under MVCC, `UPDATE` creates new row versions in many cases. Queue tables can accumulate dead tuples, WAL volume, and index churn.

### 29.1. HOT Updates Are Not Always Possible

When updating indexed columns or changing `status` moves rows into or out of partial indexes, HOT updates often cannot be used. Never treat every status `UPDATE` as free.

### 29.2. Retention

Do not keep all `succeeded` rows forever if they bloat the main table. Archive or delete in batches, avoiding giant cleanup transactions.

### 29.3. Large Payloads

Large `JSONB` values increase I/O, backup size, and processing cost. Store references to external storage instead, with appropriate consistency and access-control rules.

### 29.4. Partitioning

Very large queues may require partitioning by time, tenant, or another key, though partitioning is not free. Partitioning by `status` can turn status updates into row movement across partitions; evaluate constraints, locks, and real throughput.

### 29.5. Dedicated Brokers

If you need hundreds of consumer groups, long-term replay, large fan-out, or complex routing, a dedicated broker may fit better. Even then, a broker alone does not provide exactly-once external side effects.

## 30. Timestamps and Clocks

### 30.1. `TIMESTAMPTZ`

Use `TIMESTAMPTZ` for `run_at`, `claimed_at`, `lease_until`, and `created_at`, because they represent instants in time rather than ambiguous local wall-clock times.

### 30.2. `now()` vs. `statement_timestamp()`

`now()` returns the transaction start timestamp. If `BEGIN` is followed by a long wait, calculating leases with `now()` uses a stale timestamp. `statement_timestamp()` returns the start time of the current statement.

### 30.3. `clock_timestamp()`

`clock_timestamp()` can change even within a single statement. Use it intentionally; a consistent per-statement timestamp makes claim queries easier to reason about.

### 30.4. Worker Clocks

If worker hosts experience clock drift, computing `lease_until` on each host leads to skew. It is generally better to let PostgreSQL compute lease deadlines in SQL.

### 30.5. Synchronized Clocks Do Not Replace Tokens

Even with perfectly accurate clocks, an old worker can still send a side effect after its lease expires. Claim tokens, fencing, or idempotency remain necessary.

## 31. Timeouts and Isolation for Queues

You can set guardrails for the claim transaction:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '400ms';
SET LOCAL statement_timeout = '3s';

-- Claim one job or a batch of jobs here.

COMMIT;
~~~

- `lock_timeout`: bounds lock wait time, not total job execution time.
- `statement_timeout`: bounds a single SQL statement, not the lease.
- `lease_until`: business metadata governing processing ownership across transactions.
- `idle_in_transaction_session_timeout`: protects against sessions idling while holding open transactions.

### 31.1. Error Codes to Distinguish

| SQLSTATE | Context |
|---|---|
| `55P03` | Lock not available / lock timeout / `NOWAIT` |
| `57014` | Query canceled, including statement timeout |
| `40P01` | Deadlock |
| `40001` | Serialization failure |
| `23505` | Unique violation |

Retries should classify errors, roll back the failed transaction, re-evaluate conditions, and bound attempts. Do not retry every error immediately.

## 32. Queue and Worker Observability

### 32.1. Job Counts by Status

~~~sql
SELECT queue_name, status, COUNT(*) AS jobs
FROM queue_lab.jobs
GROUP BY queue_name, status
ORDER BY queue_name, status;
~~~

### 32.2. Ready `pending` Jobs

~~~sql
SELECT queue_name, COUNT(*) AS ready_jobs
FROM queue_lab.jobs
WHERE status = 'pending'
  AND run_at <= statement_timestamp()
GROUP BY queue_name;
~~~

### 32.3. Age of `pending` Jobs

~~~sql
SELECT
    queue_name,
    MIN(created_at) AS oldest_created_at,
    MAX(statement_timestamp() - created_at) AS max_pending_age
FROM queue_lab.jobs
WHERE status = 'pending'
GROUP BY queue_name;
~~~

This measures from creation time, including future-scheduled jobs; if you need **overdue beyond `run_at`**, compute a separate metric.

### 32.4. Jobs with Expired Leases

~~~sql
SELECT COUNT(*) AS expired_running
FROM queue_lab.jobs
WHERE status = 'running'
  AND lease_until <= statement_timestamp();
~~~

### 32.5. Recent Dead Jobs

~~~sql
SELECT
    job_id, queue_name, job_type,
    attempts, max_attempts,
    LEFT(last_error, 200) AS error_excerpt,
    updated_at
FROM queue_lab.jobs
WHERE status = 'dead'
ORDER BY updated_at DESC
LIMIT 100;
~~~

## 33. Observing Locks and Bloat

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

### 33.1. `pg_locks`

~~~sql
SELECT pid, locktype, mode, granted,
       relation::regclass AS relation_name
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

`pg_locks` shows current locks, not the history of which worker processed which job.

### 33.2. Queue Table Statistics

~~~sql
SELECT
    schemaname, relname,
    n_live_tup, n_dead_tup,
    n_tup_ins, n_tup_upd, n_tup_del,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'queue_lab';
~~~

These statistics contain estimates and cumulative totals, not exact point-in-time counts per status.

### 33.3. Metrics to Alert On

- `pending` count / ready age exceeding threshold.
- Rising expired `running` count.
- Rising `dead` jobs.
- Dropping worker throughput.
- Rising retries and failures.
- DB connection pool exhaustion.
- Increasing `55P03`/`57014`/`40001`/`40P01` errors.
- Rapidly growing dead tuples / index size.
- P95/P99 enqueue-to-ack latency breaching SLA.

## 34. Security and Multi-Tenancy

### 34.1. Least Privilege

Producers usually need `INSERT`, workers need controlled `SELECT`/`UPDATE`, reapers need recovery permissions, operators need replay permissions, and DBAs need migration privileges. Never grant superuser to all workers.

### 34.2. Tenant Isolation

If multiple tenants share a table, store `tenant_id` and scope claims by tenant/queue; enforce authorization and consider Row-Level Security according to your design.

### 34.3. Payloads May Be Sensitive

Avoid putting passwords or long-lived access tokens inside JSONB payloads without proper protection. Payloads may appear in backups, logs, metrics, and debug queries.

### 34.4. Handler Registration

Map `job_type` to handlers explicitly registered in code. Never concatenate arbitrary payload data into shell commands or unchecked SQL.

## 35. Common Misconceptions

### 35.1. "`SKIP LOCKED` guarantees exactly-once"

False. It avoids picking currently locked rows during the claim phase; it does not prevent retries after crashes.

### 35.2. "Once the claim commits, the lock stays held until the lease expires"

False. Row locks end with the transaction; a lease is just state stored in the table.

### 35.3. "An expired lease definitely means the worker died"

False. The worker may have been paused or lost network connectivity and later resumed.

### 35.4. "Having a token guarantees emails are never sent twice"

False. A DB token cannot block stale HTTP side effects if the provider does not support idempotency or fencing.

### 35.5. "A unique `dedupe_key` is enough to avoid duplicate emails"

False. It prevents duplicate enqueues, but a single job can still be retried multiple times.

### 35.6. "`SKIP LOCKED` preserves strict FIFO"

False. Locked jobs can be skipped, and completion order also varies with job duration.

### 35.7. "`running` automatically reverts to `pending` when the lease expires"

False. A reaper or active recovery task is required.

### 35.8. "`LISTEN`/`NOTIFY` is a durable queue"

False. Notifications are wakeup signals; jobs live in the table. Workers need fallback polling.

### 35.9. "Every error should be retried immediately"

False. There are permanent errors, invalid inputs, and unknown external outcomes. Classification, backoff, dead-lettering, and reconciliation are required.

### 35.10. "Enabling `SERIALIZABLE` gives exactly-once outside the DB"

False. SSI protects PostgreSQL transaction serializability, not atomic commits with an external payment or email service.

### 35.11. "A worker can hold one transaction open throughout a 30-minute report export"

Technically possible, but usually a poor queue design that increases locks, connection occupation, and MVCC pressure.

### 35.12. "Larger batches are always better"

False. Claiming too many jobs can cause leases to expire before execution begins.

### 35.13. "Updating row status has negligible overhead"

False. Queue churn generates heavy WAL, dead tuples, index writes, and `VACUUM` demand.

### 35.14. "A job with a smaller `job_id` is guaranteed to finish first"

False. Priority, `SKIP LOCKED`, retries, and worker speed all alter ordering.

### 35.15. "Client HTTP timeout means the enqueue failed"

Not necessarily. The transaction may have committed while the response was lost; idempotency keys and status lookups are needed.

## 36. Practice Exercises

### Exercise 1 — Race Condition

Two workers both `SELECT` the same `pending` row without locking. Why can duplicate processing occur?

**Hint:** Both observe `status = 'pending'` before either runs a claim `UPDATE`.

### Exercise 2 — `FOR UPDATE`

How long does `FOR UPDATE` protect a row?

**Answer:** For the duration of the transaction holding the row lock.

### Exercise 3 — `SKIP LOCKED`

Worker A locks the first job, and Worker B wants the next available job without waiting. What syntax is used?

**Answer:** `FOR UPDATE SKIP LOCKED`.

### Exercise 4 — `NOWAIT`

If you must operate on that exact locked row and do not want to wait, what do you use?

**Answer:** `FOR UPDATE NOWAIT` when appropriate.

### Exercise 5 — Atomic Claim

Why combine `SELECT FOR UPDATE SKIP LOCKED` in a CTE with an `UPDATE` of the status?

**Hint:** To select and claim the job within the same transaction.

### Exercise 6 — Claim `COMMIT`

Why avoid holding a transaction open while calling an email provider?

**Hint:** To avoid holding locks/connections for long periods; external effects also cannot roll back with the DB.

### Exercise 7 — Lease

How does a lease differ from a row lock?

**Hint:** A lease is expiration metadata; a row lock is managed by PostgreSQL per transaction.

### Exercise 8 — Stale Ack

Worker A loses its lease, and B reclaims the job. What `WHERE` predicates prevent A from acking?

**Hint:** Check token/status/worker ID and lease validity.

### Exercise 9 — Heartbeat

If a heartbeat `UPDATE` returns 0 rows, what should the worker do?

**Hint:** Assume ownership may have been lost and do not blindly ack.

### Exercise 10 — Reaper

Does a `running` job with an expired lease automatically revert to `pending`?

**Answer:** No, a reaper is required.

### Exercise 11 — Crash

A worker sends an email successfully and crashes before acking. What happens on retry?

**Hint:** The email may be sent again.

### Exercise 12 — Exactly-Once

Does `SKIP LOCKED` guarantee exactly-once external effects?

**Answer:** No.

### Exercise 13 — At-Most-Once

What is the risk of never retrying in order to avoid duplicates?

**Hint:** Jobs can be lost if a worker crashes.

### Exercise 14 — At-Least-Once

What is the trade-off of retrying when an ack is missing?

**Hint:** Execution may be repeated.

### Exercise 15 — Dedupe Key

Why is a unique `dedupe_key` alone insufficient to guarantee a single external effect?

**Hint:** Enqueue deduplication is different from execution retries.

### Exercise 16 — Token with External APIs

Should you pass `claim_token` or a stable `operation_key` as the idempotency key to a provider?

**Answer:** A stable operation key.

### Exercise 17 — Fencing Version

How does incrementing `claim_version` across claims help?

**Hint:** Targets supporting fencing can reject operations carrying stale versions.

### Exercise 18 — Max Attempts

If `attempts` reaches `max_attempts` after an error, which state should the job transition to?

**Hint:** Dead-letter/`dead` according to policy.

### Exercise 19 — Backoff

Why is jitter needed?

**Hint:** To prevent thousands of jobs from retrying simultaneously.

### Exercise 20 — Transactional Outbox

Why should enqueueing a job and inserting an order be in the same transaction when atomicity is required?

**Hint:** To avoid losing the job if the application crashes between two commits.

### Exercise 21 — Scheduling

What condition does the claim query need so jobs do not run ahead of schedule?

**Answer:** `run_at <=` current statement time.

### Exercise 22 — Partial Index

What is the purpose of an index with `WHERE status='pending'`?

**Hint:** To reduce the dataset scanned during claims.

### Exercise 23 — Dynamic Index

Why shouldn't you create a partial index with `WHERE run_at <= now()`?

**Hint:** Index predicates require immutability, whereas `now()` changes over time.

### Exercise 24 — Fairness

If high-priority jobs arrive continuously, what can happen to low-priority jobs?

**Answer:** Starvation.

### Exercise 25 — FIFO

With two workers, is `job_id` 10 guaranteed to finish before `job_id` 11?

**Answer:** No.

### Exercise 26 — Per-Customer Ordering

If jobs for the same customer must run sequentially, what else is needed?

**Hint:** A per-key serialization protocol, partitioning, or a guard row.

### Exercise 27 — Batches

A worker claims 100 jobs, each taking 20s, with a 1-minute lease. What is the risk?

**Hint:** Leases will expire before later jobs are processed.

### Exercise 28 — `LISTEN`/`NOTIFY`

If a worker misses a notification, is a committed job lost?

**Answer:** No; polling will find it in the table.

### Exercise 29 — Cancel

Does changing a `running` job's status to `cancelled` automatically abort its HTTP request?

**Answer:** No.

### Exercise 30 — Clocks

Why might `statement_timestamp()` be better than `now()` if a transaction has been open for a while?

**Hint:** `now()` retains the transaction start timestamp.

### Exercise 31 — Monitoring

Name five metrics to track.

**Hint:** Ready count, pending age, expired leases, dead jobs, throughput/retries.

### Exercise 32 — MVCC

Why can a queue with frequent status updates accumulate bloat?

**Hint:** Dead tuples, index churn, and WAL generation.

### Exercise 33 — RLS

What must a multi-tenant queue protect against?

**Hint:** A worker reading or claiming payloads belonging to another tenant.

### Exercise 34 — Idempotency on Timeout

A client never receives the enqueue response, though the DB may have committed. How do you avoid duplicate jobs?

**Hint:** Stable `dedupe_key` + `UNIQUE` + status lookup.

### Exercise 35 — Architecture Choice

When should you consider a dedicated message broker instead of a pure PostgreSQL queue?

**Hint:** Many consumer groups, large fan-out, replay/retention, or throughput/routing beyond DB capacity.

## 37. Quick Reference Table

| Goal | Tool or Principle |
|---|---|
| Select job with lock | `SELECT ... FOR UPDATE` |
| Do not wait on locked rows | `FOR UPDATE SKIP LOCKED` |
| Fail fast when lock is held | `FOR UPDATE NOWAIT` |
| Atomic claim | `candidate` CTE + `UPDATE ... RETURNING` |
| Release DB lock early | `COMMIT` immediately after claim |
| Record active processing | `status='running'` |
| Crash recovery | Lease + reaper |
| Extend lease | Heartbeat with ownership guard |
| Block stale ack | `WHERE claim_token` + `status` |
| Block stale external effects | Fencing/idempotency at target |
| Prevent duplicate enqueue | `UNIQUE(queue_name, dedupe_key)` |
| Controlled retries | `run_at`, `attempts`, `max_attempts`, backoff |
| Permanent failures | Dead-letter |
| Commit order and job together | Transactional outbox |
| Wake up workers | `LISTEN`/`NOTIFY` + polling |
| Guarantee strict FIFO | `SKIP LOCKED` does not guarantee this |
| Guarantee external exactly-once | Not provided by row locks alone |
| Prevent starvation | Aging / quotas / capacity allocation |
| Avoid DB bloat | Right indexes, `VACUUM`, retention |
| Measure queue health | Status counts, lag, expired leases, dead count |
| Observe locks | `pg_stat_activity`, `pg_locks`, `pg_blocking_pids` |
| Distinguish DB timeout vs. lease | `statement_timeout`/`lock_timeout` differ from `lease_until` |
| Protect payloads | Least privilege, RLS, secrets policy |

---

## Conclusion

PostgreSQL can power an effective job queue using **a `jobs` table, short transactions, and `SELECT ... FOR UPDATE SKIP LOCKED`**. An atomic claim selects an eligible job, skips locked rows, transitions its status to `running`, and returns a token and lease to the worker. After `COMMIT`, the worker performs the work outside the database and writes an ack guarded by ownership checks.

Crucially, **row locks only protect the claim phase**. Leases help detect abandoned attempts, reapers return expired jobs to `pending`, and retries enable recovery after crashes. In return, an old worker may still be running after its lease expires, and a job may be executed more than once. That is why **claim tokens, fencing where supported, stable idempotency keys, heartbeats, dead-lettering, and monitoring** are essential.

`SKIP LOCKED` also deliberately trades full visibility of locked rows for higher throughput. It does not guarantee strict FIFO, fairness across priorities, or completion order. For operations with side effects outside PostgreSQL, **exactly-once cannot be inferred from row locks or database transactions alone**.

A sound queue design must answer two questions at the same time: **"How do we ensure two workers never claim the same job simultaneously?"** and **"If a worker crashes after performing the work, how should retries behave?"**. PostgreSQL row locks solve the first part; retry protocols, idempotency, and coordination with downstream systems solve the second.
