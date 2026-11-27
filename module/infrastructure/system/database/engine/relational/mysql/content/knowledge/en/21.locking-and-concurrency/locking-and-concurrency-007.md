# Changing gap lock strategies by isolation level and operation type

## Objectives

After this lesson, you will be able to:

- Explain gap locks, record locks, next-key locks, and insert intention locks in InnoDB.
- Distinguish the locking behavior of `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`.
- Identify differences among consistent reads, locking reads, `UPDATE`, `DELETE`, and `INSERT`.
- Predict when a range query can block new row inserts.
- Understand why a lookup by unique key generally locks more narrowly than a range scan or a condition on a non-unique column.
- Design indexes and transactions to reduce lock footprint while protecting business rules.
- Inspect gap locks using two sessions, `EXPLAIN`, and lock tables in `performance_schema`.
- Choose an isolation level and locking read mode based on actual read/write workloads.

## 1. What problem do gap locks solve?

InnoDB uses gap locks to prevent other transactions from inserting index records into an empty interval in an index. This mechanism is important when a transaction needs to protect a range of data, including rows that do not yet exist at query time.

For example, a transaction reads all jobs with status `READY` and decides how to assign them. If another transaction could insert an additional `READY` job into the same range before the first transaction finishes, a subsequent read could see a new row (a phantom). Gap locks and next-key locks allow InnoDB to protect the scanned index range when required.

A gap lock locks the empty space between index records. Boundary gaps of the index can also be protected, including the interval before the first record and the interval after the last record (associated with the supremum pseudo-record). It does not lock an existing data row in the usual sense; its main goal is to prevent inserting index records into that gap.

### 1.1. Three lock types to distinguish

| Lock type | Scope | Main effect |
|---|---|---|
| Record lock | An existing index record | Prevents other transactions from modifying/deleting the record in a conflicting way |
| Gap lock | Empty space between index records | Prevents other transactions from inserting index records into the empty space |
| Next-key lock | An index record plus the gap immediately before that record | Combines record protection with preventing inserts into the associated gap |

InnoDB locks index records. In an InnoDB table, the primary key is the clustered index; secondary indexes have their own entries containing the primary key to locate rows. Therefore, when reading a locking plan, you must understand the index the optimizer actually uses, not just the column names in `WHERE`.

### 1.2. Special properties of gap locks

Gap locks are inhibitive: their purpose is to stop another transaction from placing a new index record into the gap. Gap locks from different transactions can coexist on the same gap, even when metadata displays them as shared or exclusive gap locks. They do not conflict with one another the way standard shared/exclusive locks on records do.

An INSERT operation requires an insert intention lock before inserting an index record. An insert intention lock signals that a transaction wants to insert at a specific position within the gap. It can be blocked by an existing gap lock.

Two transactions inserting different values at two different positions within the same gap can usually proceed concurrently; insert intention locks are designed so that inserts at different positions do not block each other merely because they share the same gap.

## 2. Gap lock strategy depends on isolation level

A gap lock is not an independent switch that an application turns on or off per statement. Behavior depends on the isolation level, operation type, indexes, and access path used by InnoDB.

### 2.1. READ COMMITTED

Under `READ COMMITTED` (RC):

- Each regular consistent read creates a new read view at the start of the statement, so two SELECT statements in the same transaction can see different newly committed changes.
- Gap locking for regular searches/index scans is disabled; InnoDB primarily locks only the necessary index records.
- Important exceptions can still use gap locks, specifically foreign key checks and duplicate-key checks.
- For `UPDATE`, InnoDB can use semi-consistent reads to pass the latest committed version to MySQL to evaluate the `WHERE` condition; if a row matches, InnoDB re-reads and locks the row for updating.
- Record locks on rows that no longer match the condition can be released after evaluating the predicate.

RC generally reduces how often INSERTs wait on gap locks from range scans, though it does not eliminate all lock waits. UPDATE/DELETE still must lock modified rows; foreign key and unique key checks can still require locks.

MySQL requires row-based binary logging for `READ COMMITTED`. Before changing the isolation level in a system with replication/binlog, check the `binlog_format` configuration, topology, and documentation for your exact server version.

### 2.2. REPEATABLE READ

`REPEATABLE READ` (RR) is InnoDB's common default isolation level:

- A plain `SELECT` is a consistent read using the transaction's snapshot and places no record/gap locks merely for reading.
- Locking reads such as `SELECT ... FOR UPDATE` or `SELECT ... FOR SHARE` typically use next-key locks when scanning ranges.
- `UPDATE` and `DELETE` normally lock scanned index records; with range predicates, the associated gaps can be protected by next-key locks.
- A lookup using a full unique key to find an existing record usually requires only a record lock, without locking the gap before that record.

RR balances stable read snapshots with range protection for locking reads/writes. A plain SELECT in RR does not lock a range to prevent INSERTs; if business logic needs range protection against concurrent writes, choose a locking read or another protection mechanism.

### 2.3. SERIALIZABLE

Under `SERIALIZABLE`, InnoDB increases read protection:

- When `autocommit` is disabled or a plain `SELECT` runs inside an explicit transaction, InnoDB treats the SELECT as a shared locking read.
- Range scans can acquire next-key/gap locks to prevent new rows from appearing in the protected range.
- Shared locks on records can make UPDATE/DELETE wait; gap locks can make INSERTs into the range wait.
- When `autocommit = 1` and a plain SELECT is a standalone read transaction, there is no multi-statement transaction holding shared locks across subsequent statements.

SERIALIZABLE can increase lock waits and deadlocks. Do not promote an entire workload to SERIALIZABLE just to avoid phantoms; identify the specific business scope that genuinely needs protection.

### 2.4. Quick comparison table

| Scenario | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Plain SELECT | Per-statement snapshot, does not lock read rows | Stable snapshot within transaction, does not lock read rows | Inside an explicit transaction, becomes a shared locking read |
| SELECT ... FOR SHARE / FOR UPDATE on a range | Usually locks records; no gap-locking for regular searches | Can use next-key/gap locks | Can use next-key/gap locks |
| Range-based UPDATE/DELETE | Locks rows to update/delete; regular gap locking is disabled | Can place next-key locks on the scanned index range | Can place next-key locks on the scanned index range |
| INSERT into a gap protected by a gap lock | Usually not blocked by regular search gap locks; FK/duplicate exceptions still apply | May have to wait | May have to wait |
| FK/duplicate-key checking | Can still use gap/record locks | Locks per InnoDB rules | Locks per InnoDB rules |
| Read/write contention level | Usually lower | Moderate depending on locking queries | Usually higher for overlapping read/write transactions |

This table describes typical behavior, not an exact lock guarantee for every query. Chosen indexes, search conditions, existing data, statement type, and MySQL version can all change the lock footprint.

## 3. Operation type determines locking behavior

You cannot look solely at the isolation level and conclude every SQL statement uses the same gap lock strategy. You must distinguish operation types.

### 3.1. Plain consistent SELECT

In RR, a regular SELECT reads from an MVCC snapshot. It acquires neither record locks nor gap locks merely for reading data:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY';

-- This SELECT reads a snapshot; it does not lock gaps to prevent INSERT.
```

Another transaction can INSERT a `READY` row and commit. The reading transaction still sees the initial snapshot when reading again via consistent read in the same RR transaction.

In RC, each statement gets a new read view; a subsequent SELECT can see newly committed rows. In SERIALIZABLE within an explicit transaction, a plain SELECT is converted into a shared locking read.

### 3.2. SELECT ... FOR SHARE and SELECT ... FOR UPDATE

These are locking reads. `FOR SHARE` acquires shared locks; `FOR UPDATE` acquires exclusive locks on matching records. For range scans in RR/SERIALIZABLE, InnoDB can acquire next-key locks to protect the gaps as well.

```sql
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Process the locked jobs then COMMIT/ROLLBACK.
```

In RC, regular searches for locking reads mainly lock records without locking gaps; however, foreign key checks and duplicate-key checks remain exceptions. Thus, an INSERT at a new position in the range can proceed under RC while an UPDATE/DELETE on already locked records must still wait.

### 3.3. UPDATE and DELETE

UPDATE/DELETE are write operations, so InnoDB needs to lock modified rows. Under RR, range predicates can produce next-key locks over the scanned index range, preventing INSERTs from creating phantoms inside the range.

Example:

```sql
UPDATE jobs
SET status = 'PROCESSING'
WHERE status = 'READY';
```

In RR, InnoDB may lock index records and gaps across the `status = 'READY'` range per the access path. An INSERT adding a new job with status `READY` may have to wait.

In RC, gap locking for regular searches is disabled; rows actually updated are still locked, whereas inserting a new matching row is generally not blocked by a gap lock from this UPDATE. FK/duplicate-key exceptions still apply.

Range-based DELETE follows the same principle: deleted rows need locks; in RR, gaps of the scanned index range can be protected by next-key locks.

### 3.4. INSERT and insert intention locks

During INSERT, InnoDB must place a new index record at the right position in the index. Before inserting, it uses an insert intention lock on the corresponding gap. If another transaction holds a gap/next-key lock blocking inserts at that position, the INSERT must wait.

Example:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (9001, 'READY', CURRENT_TIMESTAMP);
```

An INSERT does not automatically lock every gap in the table. It locks the target insertion slot and creates the new record. Duplicate-key checks and foreign key checks can generate additional locks.

## 4. Indexes and access paths determine lock footprint

InnoDB locks the index records traversed during query execution. The `WHERE` clause describes the logical filter; indexes and the execution plan decide how rows are found and the scope of records/gaps locked.

### 4.1. Appropriate indexes narrow the scan range

Example jobs table:

```sql
CREATE TABLE jobs (
    job_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    payload VARCHAR(200) NULL,
    PRIMARY KEY (job_id),
    KEY idx_jobs_status (status)
) ENGINE = InnoDB;
```

Query fetching pending jobs:

```sql
SELECT job_id, status, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY status, job_id
FOR UPDATE;
```

The `status` index lets InnoDB locate the `READY` status slice instead of scanning the entire table. InnoDB secondary indexes automatically append the primary key as a suffix to locate rows; thus `job_id` already participates in the index ordering without repeating it in this index definition. In RR, the scanned index slice and related gaps can be locked to prevent new rows from being inserted into the range.

### 4.2. Missing indexes can create a large lock scope

If a query lacks a suitable index, the optimizer may have to scan many records or the entire clustered index. For a locking read or UPDATE/DELETE, the number of examined and locked records can be larger than desired, increasing blocking and reducing concurrency.

Example:

```sql
EXPLAIN
SELECT job_id, status
FROM jobs
WHERE payload LIKE '%urgent%'
FOR UPDATE;
```

Search predicates with a leading wildcard normally cannot use a standard B-tree index. If many rows must be scanned, a locking read can acquire a broad lock footprint. Consider another search model or an index suited to the query pattern.

### 4.3. Unique point lookups can avoid gap locks

In RR, if an equality condition uses an entire unique index to find a single existing record, InnoDB typically locks only that record without locking the gap before it:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;
```

This requires `account_id` to be a primary key or unique key and the predicate to specify the entire unique key. For a composite unique index `(tenant_id, external_id)`, only a condition specifying both columns qualifies as a unique point lookup.

If you filter only on part of a composite unique index or use a non-unique column, the query can become a range scan and lock a wider scope.

If a unique point lookup finds no record, InnoDB may lock the gap where the record would be inserted to protect the search under RR. Thus, the rule "unique lookup only uses a record lock" applies when a unique record is found; do not generalize it to empty results.

### 4.4. Inspecting with EXPLAIN

```sql
EXPLAIN
SELECT job_id, status, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY status, job_id
FOR UPDATE;
```

Observe:

- `key`: selected index.
- `type`: access type such as `const`, `ref`, `range`, or `ALL`.
- `rows`: estimated rows to read.
- `Extra`: filtering, sorting, or additional execution details.

`EXPLAIN` reveals the access path, though it does not list every actual lock. To verify locks, combine it with observing `performance_schema.data_locks`, `performance_schema.data_lock_waits`, and InnoDB status on supported versions.

## 5. Unique keys, non-unique keys, and gap locks

An important distinction in RR is unique lookups versus non-unique lookups.

| Condition | Typical locking behavior in an RR locking read |
|---|---|
| `WHERE primary_key = existing_value FOR UPDATE` | Record lock on the found record |
| `WHERE unique_key = existing_value FOR UPDATE` with full unique key | Record lock on the found record |
| `WHERE non_unique_key = value FOR UPDATE` | Can lock matching records and related gaps via next-key locks |
| `WHERE indexed_key BETWEEN low AND high FOR UPDATE` | Range scan, can use next-key locks over the range |
| Unique lookup finding no row | Can lock a gap at the insertion slot to prevent phantoms |
| Lookup without a suitable index | Can scan many records and create a broad lock footprint |

Do not overlook collation and NULL when evaluating unique keys. A unique index on a nullable column can allow multiple NULL values; an `IS NULL` predicate is not necessarily a unique point lookup.

## 6. Exceptions in READ COMMITTED: foreign key and duplicate-key checks

The rule "RC disables gap locks" applies only to regular searches/index scans. InnoDB can still use gap locks in certain data-integrity operations.

### 6.1. Foreign key checks

When inserting or updating a child row, InnoDB must verify that the referenced parent row exists. Foreign key verification can place locks on the relevant index to protect referential integrity, even under RC.

Consequently, an INSERT under RC can still wait for another transaction when foreign keys are involved. Never assume RC makes every insert immune to gap/record lock blocking.

### 6.2. Duplicate-key checks

When inserting into a unique index, InnoDB must check whether the new value duplicates an existing value or a value concurrently being written by another transaction. Duplicate-key checking can use record/gap locking and cause lock waits.

Statements such as `INSERT ... ON DUPLICATE KEY UPDATE` have their own locking paths because they can turn into an update when a duplicate is detected. Do not assume their behavior matches a plain INSERT.

### 6.3. Why are these exceptions necessary?

Disabling gap locks for regular searches in RC reduces blocking between range-reading transactions and INSERTs. Yet InnoDB still must enforce constraints like foreign keys and unique keys; otherwise, two transactions could both pass validation and create data violating uniqueness or referential integrity.

## 7. Hands-on example: range lock blocking INSERT under REPEATABLE READ

### 7.1. Preparing the test table

Run once in a test schema:

```sql
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    job_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_jobs_status (status)
) ENGINE = InnoDB;

INSERT INTO jobs (job_id, status, created_at)
VALUES
    (1, 'READY', '2026-01-01 09:00:00'),
    (2, 'READY', '2026-01-01 09:05:00'),
    (3, 'RUNNING', '2026-01-01 09:10:00'),
    (4, 'DONE', '2026-01-01 09:15:00');
```

### 7.2. Session A: locking the READY range under RR

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Not yet committed; keep transaction open.
```

Because `status` is non-unique and the query uses the `status` index, InnoDB can use next-key locks to protect the records/gaps belonging to the `READY` range. InnoDB secondary indexes append the primary key as a secondary key suffix, so this index is also ordered by `job_id` among entries sharing the same `status`.

### 7.3. Session B: inserting a new job into the same range

In another connection:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (5, 'READY', '2026-01-01 09:20:00');
```

The INSERT can wait on Session A because the new index position falls inside the locked gap range. Leave Session B waiting to observe it.

Return to Session A:

```sql
COMMIT;
```

Once Session A ends its transaction, Session B can proceed if there are no other conflicts.

Exact behavior depends on the access path, index order, and existing data. If the optimizer does not choose the expected index, lock scope may differ; check `EXPLAIN` before testing.

## 8. Comparing the same operation under READ COMMITTED

Finish the previous test transactions first. Switch Session A to RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Keep transaction open.
```

Session B inserts a READY row with a new `job_id`:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (6, 'READY', '2026-01-01 09:25:00');
```

Under RC, gap locking for regular searches/index scans is disabled, so this INSERT normally does not wait on a gap lock from the locking read. Existing READY rows still hold record locks; if Session B updates one of those rows, it still must wait.

End Session A with `COMMIT` or `ROLLBACK`. If the INSERT still waits, investigate other causes such as unique keys, foreign keys, primary key locks, or another transaction. RC does not eliminate every form of locking.

## 9. Comparing plain SELECT under RR and RC

### 9.1. REPEATABLE READ: same snapshot within the transaction

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

Session B:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (7, 'READY', CURRENT_TIMESTAMP);
COMMIT;
```

Session A runs the plain SELECT again:

```sql
SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

Within the same RR transaction, consistent reads continue using the initial snapshot, so Session B's newly committed row is not seen. The plain SELECT does not hold gap locks simply for reading.

### 9.2. READ COMMITTED: fresh snapshot per statement

Repeat with RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

After Session B inserts and commits, Session A runs the SELECT again. Under RC, each new statement creates a new read view and can see the newly committed row.

This difference stems from consistent reads and snapshots, not because SELECT in RR locked the range. To block inserts while a transaction is processing, you need a locking read or an appropriate protection mechanism.

## 10. Range-based UPDATE/DELETE: what changes when changing isolation?

Suppose Session A runs:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE jobs
SET status = 'PROCESSING'
WHERE status = 'READY';

-- Keep transaction open.
```

In RR, the operation can place next-key locks over the scanned index range. Session B inserting a new row with `status = 'READY'` may be blocked by a gap lock.

If Session A uses RC, gap locking for regular searches is disabled. Rows actually updated still hold exclusive record locks, while inserting a new row with the same status value is generally not blocked by a gap lock from that UPDATE.

Points to remember:

- UPDATE only locks rows actually updated; under RC, locks on rows that fail the predicate evaluation can be released early.
- DELETE still needs to lock deleted records.
- Foreign key cascades/checks and duplicate-key checks can add locks.
- A query lacking a suitable index can scan many rows, increasing lock overhead even though RC disables regular gap locks.
- If the update condition relies on a range invariant, reducing gap locks can alter application logic correctness.

## 11. Insert intention locks and concurrent inserts

Create a test table with two index records, 10 and 20:

```sql
DROP TABLE IF EXISTS indexed_values;

CREATE TABLE indexed_values (
    value_key INT NOT NULL,
    PRIMARY KEY (value_key)
) ENGINE = InnoDB;

INSERT INTO indexed_values (value_key) VALUES (10), (20);
```

The gap between the two index records is `(10, 20)`. Two transactions want to insert 13 and 17:

```sql
-- Session A
START TRANSACTION;
INSERT INTO indexed_values (value_key) VALUES (13);
-- Not yet committed.

-- Session B
START TRANSACTION;
INSERT INTO indexed_values (value_key) VALUES (17);
-- Insertion position differs from Session A, so it does not wait on A's insert intention lock.
COMMIT;

-- Session A
COMMIT;
```

The two inserts can proceed concurrently because their insertion positions differ within the same gap; insert intention locks do not block each other simply for targeting the same interval.

After both inserts finish, Session C can lock a range:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT value_key
FROM indexed_values
WHERE value_key > 10
  AND value_key < 20
FOR UPDATE;
```

Session D tries to insert a new value inside the range:

```sql
INSERT INTO indexed_values (value_key) VALUES (15);
```

The INSERT may have to wait for Session C to end its transaction because the corresponding gap is protected. This is why a gap lock can affect many new values even when no corresponding records exist in the table yet.

Do not confuse insert intention locks with regular gap locks: an insert intention signals intent to insert at a specific position; a regular gap lock protects the interval against conflicting inserts.

## 12. Choosing a strategy by business scenario

No single isolation level is optimal for all workloads. Start from business rules and operation types.

| Business scenario | Potentially suitable strategy | Notes |
|---|---|---|
| Displaying lists without locking data | Plain SELECT in RR or RC | Relies on MVCC; no gap locks needed just to read |
| Reading then updating one row by primary key | `SELECT ... FOR UPDATE` or conditional UPDATE | Unique point lookup keeps lock scope narrow |
| Fetching a batch of rows for sequential processing | `FOR UPDATE` with an index matching the filter | RR may next-key lock the range; RC reduces gap locks while still locking records |
| Inserting new rows into a status/range currently being processed | Evaluate RR locking read or SERIALIZABLE if phantoms must be prevented | Must verify gap locks and index access path |
| Avoiding unnecessary INSERT blocking in write-heavy workloads | Consider RC | Accept per-statement snapshots and FK/duplicate exceptions |
| Protecting a unique business code | UNIQUE constraint/index | Do not rely on gap locks as the sole uniqueness guard |
| Checking a count before deciding to insert rows | Constraints, atomic counters, locking strategy, or SERIALIZABLE | Do not rely on a plain SELECT snapshot if range protection is needed |
| Updating rows based on a quantity condition | Conditional UPDATE such as `WHERE quantity >= ?` | Check affected rows instead of separating read and write |

### 12.1. Prefer constraints whenever possible

If a rule can be expressed via `PRIMARY KEY`, `UNIQUE`, `CHECK`, or foreign keys, let the database enforce that invariant. Constraints apply across every write path with table access, whereas application-only checks can be bypassed by another client.

### 12.2. Use locking reads for ranges needing protection

If a transaction must read a group of rows and then update that group, `SELECT ... FOR UPDATE` explicitly signals locking intent. Under RR, range scans can use next-key locks for phantom protection. Under RC, gap locks are usually disabled for regular searches; evaluate whether invariants still hold.

### 12.3. Use READ COMMITTED when reducing gap locks is an explicit goal

RC can fit high-concurrency write workloads where INSERT blocking caused by gap locks creates heavy contention and the application accepts per-statement snapshot semantics. However, verify:

- Do queries depend on a stable snapshot across multiple statements?
- Is there "read count then decide to write" logic requiring range protection?
- Do unique/FK checks still create lock waits?
- Are binary logging and replication configurations compatible?
- Do concurrency tests show actual throughput/latency improvements?

Switching isolation levels just to make lock waits disappear without reviewing business logic can introduce race conditions.

## 13. Reducing lock footprint through query design

### 13.1. Use index-friendly predicates

Prefer sargable predicates, for example:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
```

rather than wrapping the column in a function if doing so prevents index usage:

```sql
WHERE DATE(created_at) = '2026-01-01'
```

The second query can force MySQL to scan many more records without a matching functional index. For locking reads/UPDATE/DELETE, wider scans can bring more locks.

### 13.2. Lock only the columns/rows needed

Do not run a locking read across the whole table if only one row is needed:

```sql
SELECT job_id, status
FROM jobs
WHERE job_id = 101
FOR UPDATE;
```

With a primary key lookup, lock footprint is normally narrower than a range scan by status.

### 13.3. Claiming batches of work by stable keys

If workers need to claim a batch of jobs to process, `FOR UPDATE SKIP LOCKED` can be used on supported versions:

```sql
START TRANSACTION;

SELECT job_id
FROM jobs
WHERE status = 'READY'
ORDER BY job_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Update the selected jobs to PROCESSING in the same transaction.

COMMIT;
```

`SKIP LOCKED` skips rows currently locked by other transactions instead of waiting for them. It is useful for multi-worker queues, though it returns an inconsistent data view and does not suit every business flow. It does not globally disable gap locks; verify locking behavior, indexes, and query semantics on your MySQL version.

`NOWAIT` can be used when you want the query to error immediately instead of waiting if a lock cannot be acquired. Both `NOWAIT` and `SKIP LOCKED` adjust lock-wait handling for locking reads; they do not replace isolation levels or constraints.

### 13.4. Keep transactions short

Even with proper indexes and isolation levels, long transactions hold locks longer. Avoid calling HTTP endpoints, sending emails, waiting for users, or running heavy CPU work while a transaction holds locks. Perform off-database work beforehand if safe, then open a short transaction to re-read/verify and write.

## 14. Observing gap locks and lock waits

### 14.1. Viewing open transactions

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
```

This query helps identify long-running transactions, waiting transactions, and the latest recorded SQL statement. Appropriate privileges are required to read metadata.

### 14.2. Viewing data locks in MySQL 8.0

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, INDEX_NAME, LOCK_STATUS;
```

`LOCK_MODE` values may include tokens such as `S`, `X`, `GAP`, `REC_NOT_GAP`, or `INSERT_INTENTION`, depending on lock type and version. Read it alongside `INDEX_NAME` and `LOCK_DATA` to understand which record/gap is involved.

### 14.3. Viewing lock wait relationships

```sql
SELECT
    requesting.ENGINE_TRANSACTION_ID AS waiting_trx,
    requesting.OBJECT_NAME,
    requesting.INDEX_NAME,
    requesting.LOCK_MODE AS waiting_lock_mode,
    blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
    blocking.LOCK_MODE AS blocking_lock_mode,
    blocking.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS requesting
  ON requesting.ENGINE = waits.ENGINE
 AND requesting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

Metadata columns can vary across versions; verify the `performance_schema` schema on your target server. Do not rely on a single `LOCK_DATA` value to deduce the entire gap scope without checking the index and access path.

### 14.4. SHOW ENGINE INNODB STATUS

```sql
SHOW ENGINE INNODB STATUS;
```

The `TRANSACTIONS` and `LATEST DETECTED DEADLOCK` sections provide details on waiting transactions and the most recent deadlock. Output is a point-in-time snapshot; a newer deadlock can overwrite earlier details.

## 15. Deadlocks and lock waits when changing gap locks

Reducing gap locks in RC does not mean eliminating deadlocks. Transactions can still conflict when updating the same records, acquiring locks in different orders, or checking unique keys or foreign keys.

When encountering a deadlock:

1. Log the error and transaction details.
2. Roll back the entire failed transaction.
3. If the business operation is safe to retry, start a new transaction and re-run the entire unit of work.
4. Cap the retry count and use appropriate backoff.
5. Inspect row access order, indexes, lock scope, and transaction duration.

Lock wait timeout differs from deadlock. Depending on `innodb_rollback_on_timeout`, a timeout may roll back only the current statement or the entire transaction. Applications should roll back the full transaction before reusing the connection unless a clear alternative handling flow exists.

Never retry infinitely, and never re-run only the last SQL statement in a failed transaction. Earlier reads and business decisions may need to be re-executed.

## 16. Common mistakes

| Mistake/misconception | Consequence | Resolution |
|---|---|---|
| Thinking every SELECT acquires gap locks | Plain consistent SELECTs in RR/RC normally read via MVCC without gap-locking | Distinguish consistent reads from locking reads |
| Thinking READ COMMITTED has zero gap locks | FK and duplicate-key checks can still use gap/record locks | Check operation types and constraints |
| Thinking REPEATABLE READ always locks on read | Plain SELECT is a consistent read, not a locking read | Use `FOR SHARE`/`FOR UPDATE` when locks are needed |
| Thinking unique equality always locks only a record | Condition must use the full unique key and the row must exist; missing-key lookups can lock a gap | Verify cardinality and found/missing status |
| Guessing locks solely from WHERE | Optimizer may use a different index or full scan | Inspect EXPLAIN and `data_locks` |
| Disabling gap locks for speed without checking logic | Can allow phantoms/race conditions in range-read-then-write workflows | Verify invariants and test concurrency before switching to RC |
| Adding indexes arbitrarily | Increases write cost without guaranteed lock-footprint reduction | Design around actual access paths |
| Leaving transactions open too long | Lock waits and deadlocks increase | Keep transactions short, avoid waiting on external tasks |
| Thinking SKIP LOCKED eliminates all gap locks | It only changes how already-locked rows are handled in locking reads | Evaluate index and lock semantics separately |

## 17. Workflow for choosing a gap lock strategy

1. **Identify the operation:** plain SELECT, locking read, UPDATE, DELETE, or INSERT?
2. **Identify invariants:** do you need to stop new rows from appearing in a range, or only lock existing rows?
3. **Choose isolation level:** RR for stable snapshots; RC to reduce regular gap locks; SERIALIZABLE when broader serializability is required.
4. **Check indexes:** determine the access path, unique/non-unique lookup, and scanned range.
5. **Inspect constraints:** foreign keys and unique keys can create locks even under RC.
6. **Narrow scope:** use sargable predicates, suitable indexes, and lock only rows needing processing.
7. **Simulate two sessions:** test whether UPDATE/DELETE/INSERT wait on each other.
8. **Observe locks:** use `performance_schema.data_locks`, `data_lock_waits`, and InnoDB status.
9. **Measure under load:** track latency, throughput, deadlocks, and lock wait timeouts.
10. **Verify replication:** check row-based binary logging requirements when using RC.

## 18. Pre-production checklist

- [ ] Distinguished consistent reads from locking reads.
- [ ] Understood gap lock differences across RC, RR, and SERIALIZABLE.
- [ ] Reviewed SELECT, UPDATE, DELETE, INSERT, and constraint checks separately.
- [ ] Verified the optimizer-chosen index with EXPLAIN.
- [ ] Confirmed whether unique lookups use the full unique key and whether records exist.
- [ ] Checked foreign key and duplicate-key exceptions under RC.
- [ ] Protected invariants using appropriate constraints or locking strategies.
- [ ] Tested two concurrent sessions on production-representative data.
- [ ] Kept transactions short and accessed records in a consistent order.
- [ ] Implemented deadlock, lock wait timeout, and full-transaction retry handling.
- [ ] Verified row-based binlog/replication when choosing READ COMMITTED.
- [ ] Monitored lock waits, deadlocks, throughput, and latency after deployment.

## 19. Conclusion

Gap locks protect empty intervals in an index to prevent other transactions from inserting records into a protected range. In InnoDB, gap lock strategies vary by isolation level and operation type: RC disables gap locks for regular searches/index scans while preserving foreign key and duplicate-key exceptions; RR typically uses next-key locks for locking reads and range-based writes; SERIALIZABLE additionally converts plain SELECTs inside explicit transactions into shared locking reads.

Indexes and access paths determine which records/gaps are scanned, thereby influencing lock waits and concurrency. Distinguish consistent reads from locking reads, use unique keys and indexed predicates where appropriate, keep transactions short, and validate with two-session tests. Choose RC to reduce gap locks only when business logic and replication configuration accept its semantics; when range protection is required, use constraints or a locking strategy that satisfies the exact invariant.
