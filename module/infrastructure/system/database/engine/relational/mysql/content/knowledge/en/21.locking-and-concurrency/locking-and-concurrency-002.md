# Record locks, gap locks, next-key locks, and insert intention locks

InnoDB uses locks to protect data when multiple transactions concurrently read, insert, update, or delete rows. These locks are placed on **index records and the gaps between index records**, so the lock scope depends on the index used by the execution plan. The four concepts to distinguish are `record lock`, `gap lock`, `next-key lock`, and `insert intention lock`.

- **Record lock** locks a specific index record.
- **Gap lock** locks the gap between index records to prevent other transactions from inserting new keys into that interval.
- **Next-key lock** combines a record lock with a gap lock on the gap immediately preceding the index record.
- **Insert intention lock** signals the intent to insert an index record into a gap; transactions inserting at different positions within the same gap do not have to wait for each other.

These mechanisms are especially important at the `REPEATABLE READ` isolation level, where InnoDB uses next-key/gap locking for many locking reads and range-based writes to prevent phantom rows. Understanding lock scope helps explain why an INSERT is blocked even when it does not modify the same row, why a query missing an index can lock too broadly, and why multiple inserts into the same interval can still run concurrently.

## 1. InnoDB locks are tied to indexes

InnoDB organizes data according to a clustered index. If a table has a primary key, the primary key is the clustered index. If no primary key is declared, InnoDB chooses a suitable unique index or creates a hidden clustered index. Secondary indexes store the secondary key alongside the primary key value to locate the corresponding row.

Therefore, when speaking of "locking a row," understand that InnoDB actually locks the relevant index records. A query using a secondary index may lock entries in the secondary index as well as the corresponding record in the clustered index. A lock is not merely a logical label attached to a row displayed in a SELECT result.

This leads to three consequences:

1. The index chosen by the optimizer affects which records and gaps are locked.
2. A query may lock index records scanned to evaluate conditions, even if some rows do not ultimately appear in the result set.
3. Missing a suitable index can cause InnoDB to scan and lock a wider range than expected, increasing contention and lock waits.

Hence, when investigating locks, you must examine the SQL predicates, indexes, execution plan, and isolation level.

## 2. Preparing a practice table

Create an InnoDB table with a primary key and a non-unique secondary index:

```sql
CREATE TABLE lock_demo (
    id BIGINT UNSIGNED NOT NULL,
    code INT NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_lock_demo_code (code)
) ENGINE=InnoDB;

INSERT INTO lock_demo (id, code, note)
VALUES
    (1, 10, 'ten'),
    (2, 20, 'twenty'),
    (3, 30, 'thirty');
```

The `idx_lock_demo_code` index has values 10, 20, and 30. Because the index is non-unique, a single `code` can appear in multiple rows. The gaps between index values can be used to demonstrate gap locks and insert intention locks.

Inspect:

```sql
SELECT id, code, note
FROM lock_demo
ORDER BY code, id;

SHOW INDEX FROM lock_demo;
```

The two-session examples below assume the table uses InnoDB, transactions are opened explicitly, and the isolation level is set as instructed. Run them on a test database because some steps intentionally create lock waits.

## 3. Record lock: locking an index record

A record lock locks a specific index record. With a primary key, an equality query looking up a single row may only need to lock that record if the condition uses the full unique key and the row exists.

Session A example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo
WHERE id = 2
FOR UPDATE;
```

InnoDB places an exclusive record lock on the primary key record `id = 2`. While Session A has not committed, Session B attempts to modify the same row:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'updated by B'
WHERE id = 2;
```

The UPDATE in Session B must wait because Session A holds an incompatible lock on the same record. When Session A runs:

```sql
COMMIT;
```

Session B can proceed. End Session B with `COMMIT` or `ROLLBACK`.

### A record lock does not mean locking only one row in an application sense

A record lock always belongs to an index record. If a query uses a secondary index, InnoDB may lock both the secondary index record and the related clustered record. If a non-unique predicate matches multiple rows, multiple records may be locked.

For an equality lookup across all columns of a unique index when the row is found, InnoDB usually only needs a record lock without locking the gap before that record. This rule does not apply when searching only part of a composite unique key, using a range predicate, or when no row is found.

## 4. Gap lock: locking the empty space between index records

A gap lock locks the interval between index records rather than an existing record itself. Its primary purpose is to prevent other transactions from inserting new index entries into that gap.

With the `code` index in the sample data, the existing values are 10, 20, and 30. You can visualize the intervals as:

```text
(-∞, 10)   10   (10, 20)   20   (20, 30)   30   (30, +∞)
```

A locking read searching for a nonexistent value in a gap can cause InnoDB to lock the gap containing that value under `REPEATABLE READ`.

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

The query returns no rows because `code = 15` does not exist yet. However, because this is a locking read on a non-unique index under `REPEATABLE READ`, InnoDB may place a gap lock on the interval containing 15, between index entries 10 and 20.

Session B attempts to insert into the gap:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (4, 15, 'fifteen');
```

The INSERT may have to wait for the gap lock held by Session A. Only when Session A runs `COMMIT` or `ROLLBACK` can Session B's insert proceed.

### Gap locks do not lock existing records

A gap lock is **inhibitive**: it prevents inserting new index entries into the interval, rather than acting as a read/write lock on an existing record inside the interval, since no record exists there. Multiple transactions can simultaneously hold gap locks on the same gap; a gap lock does not conflict with another gap lock the way S/X record locks conflict. However, an insert intention from a transaction trying to insert into the gap can be blocked.

Do not interpret a gap lock as "locking all rows with values in a range." It locks empty space in the index. For a range query, InnoDB typically combines record locks and gap locks into next-key locks.

At the end of an index, InnoDB uses a pseudo-record named `supremum` to represent the interval after the largest index record. Therefore, lock diagnostics at the end of an index sometimes display `supremum pseudo-record`; this is an internal marker representing the gap, not a data row inserted by the application.

## 5. Next-key lock: record lock plus the gap before the record

A next-key lock is the combination:

```text
next-key lock = record lock on an index record + gap lock immediately before that record
```

If an index has values 10, 20, and 30, the next-key lock associated with record 20 protects record 20 and the gap `(10, 20)`. The next-key lock associated with record 30 protects record 30 and the gap `(20, 30)`.

Visualization:

```text
Gap (-∞,10)  [10]  Gap (10,20)  [20]  Gap (20,30)  [30]  Gap (30,+∞)
                    <------ next-key lock of record 20 ------>
```

Under `REPEATABLE READ`, next-key locking is commonly used for locking range scans to prevent other transactions from inserting phantom rows into the read/locked range.

Session A example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code >= 10
  AND code <= 20
FOR UPDATE;
```

The query reads entries with `code` from 10 to 20 and requests locks for updating. InnoDB uses record/next-key locks on the scanned index range; the associated gaps can cause a new INSERT inside the range to wait. The exact scope depends on the chosen index, boundary predicates, and how InnoDB traverses the index; do not infer it solely from the number of rows returned.

Session B may try:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (5, 15, 'inside range');
```

The INSERT can be blocked by Session A's gap/next-key lock. Once A finishes its transaction, B proceeds.

### Why are next-key locks needed?

Suppose Session A reads orders with `amount` from 100 to 200 to compute a business decision. If another transaction could insert a new row with `amount = 150` before A finishes, a subsequent read could see an extra row in the same range (a phantom). Next-key locking prevents inserts into the relevant gaps under the isolation levels and query types that use it.

Next-key locking is a phantom-prevention mechanism, not a guarantee that every SELECT locks a range. A regular SELECT uses MVCC consistent reads and does not place next-key locks just because it has a WHERE clause.

## 6. Insert intention lock: intent to insert into a gap

Before inserting a new index entry, InnoDB places an insert intention lock on the gap where the entry will be inserted. This is a special type of gap lock signaling that a transaction intends to insert at a specific position.

The key point is that insert intention locks from two transactions intending to insert at **two different positions** within the same gap can coexist without waiting for each other, provided no other gap/next-key lock blocks the insert.

Suppose the index has two values, 10 and 20, so the gap `(10, 20)` is empty. Session B:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (6, 12, 'twelve');
```

Session C, on another connection:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (7, 18, 'eighteen');
```

Both INSERTs can proceed concurrently because they intend to insert at different positions within the gap `(10, 20)`. Each transaction holds a lock on its own newly inserted record and an insert intention at its target insertion position; insert intention locks do not automatically block each other merely for targeting the same gap.

If another transaction holds a gap lock or next-key lock covering `(10, 20)`, the INSERTs may still have to wait. Insert intention is not permission to bypass a gap lock.

### How does an insert intention lock differ from a regular gap lock?

| Lock type | Purpose | Effect on INSERT |
|---|---|---|
| Gap lock | Prevents inserting index entries into a gap | Can block insert intentions in the gap. |
| Insert intention lock | Signals intent to insert at a position within a gap | Two insert intentions at different positions can be compatible. |
| Next-key lock | Locks a record and the gap before the record | Can block insert intentions in the protected gap. |
| Record lock | Locks an existing index record | Blocks incompatible operations on that record; not a pure gap lock. |

## 7. The four lock types in a single index model

For an index with values 10, 20, 30, we can summarize:

| Lock type | Protected object | Main effect |
|---|---|---|
| Record lock | One index record, e.g., record `20` | Prevents incompatible operations on that record. |
| Gap lock | Interval between two index records, e.g., `(10, 20)` | Prevents inserting new entries into the gap. |
| Next-key lock | Record `20` and gap `(10, 20)` | Protects the record and prevents phantoms in the preceding gap. |
| Insert intention lock | Intended insertion position inside a gap | Coordinates concurrent inserts; different positions may not block each other. |

You cannot deduce the lock type solely from the SQL statement without knowing the index used and the isolation level. The same WHERE predicate can produce different lock scopes if the optimizer chooses a different index, if the column has a unique constraint, or if the transaction runs at a different isolation level.

## 8. How isolation levels affect gap and next-key locking

### REPEATABLE READ

`REPEATABLE READ` is InnoDB's commonly used default isolation level. At this isolation level:

- Locking reads (`FOR UPDATE`, `FOR SHARE`) and range-based UPDATE/DELETE statements normally use next-key locking on index scans to prevent phantoms.
- Equality searches on an entire unique index that find a row typically only require a record lock.
- Searches for a nonexistent key or searches on a non-unique index may lock gaps to prevent inserts at that position.
- INSERT requires an insert intention lock before creating the index entry.

### READ COMMITTED

At `READ COMMITTED`, InnoDB generally disables gap locking for searches and index scans, except when required for foreign key checks and duplicate-key checks. Record locks are still used to protect modified or locked rows. Therefore, a locking range read under READ COMMITTED generally allows other transactions to insert new rows into gaps that REPEATABLE READ would protect.

Do not switch to READ COMMITTED merely to reduce lock waits without reviewing isolation requirements and system replication/configuration. Verify whether phantoms are permissible in the business logic.

### Checking the current isolation level

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Some older MySQL versions use the variable name `tx_isolation`. If working with an older version, verify the appropriate variable before running diagnostic queries.

## 9. Unique lookups and lock scope

A unique index can help narrow lock scope when a query looks up exactly one row using the full unique key.

Example:

```sql
CREATE TABLE account_lock_demo (
    account_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_account_lock_demo_email (email)
) ENGINE=InnoDB;

SELECT account_id, balance
FROM account_lock_demo
WHERE email = 'a@example.test'
FOR UPDATE;
```

If a row is found via an equality lookup on the entire unique index, InnoDB typically locks only the matching record rather than locking the gap before the record. This narrows the lock scope compared to range or non-unique key searches.

Non-equivalent cases:

- `WHERE email LIKE 'a%'` is a range/prefix search, not a unique equality lookup.
- For a composite unique index `(tenant_id, email)`, a condition specifying only `email = ...` does not specify the full unique key.
- If the unique key lookup finds no row, InnoDB may lock the gap at the position needing protection, depending on isolation level and query type.
- If the optimizer does not use the unique index, the lock scope may differ from expectations.

Designing unique indexes aligned with business rules both enforces uniqueness and gives the optimizer and InnoDB the opportunity to use narrower lookups.

## 10. Indexes and actual lock scope

Lock scope depends on the index records scanned by the execution plan, not solely on the rows ultimately matching WHERE. Compare two queries:

```sql
EXPLAIN
SELECT id, code, note
FROM lock_demo
WHERE code = 15
FOR UPDATE;

EXPLAIN
SELECT id, code, note
FROM lock_demo IGNORE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

The first query can use the secondary index `idx_lock_demo_code`; the second instructs the optimizer to ignore that index and may scan the clustered index. When scanning more index records, the number of records/gaps that can be locked may also increase.

Do not run `IGNORE INDEX` queries on production tables just to experiment. This example illustrates why indexes and access paths affect locking. Inspect with `EXPLAIN` in a test environment.

### Non-sargable predicates

Wrapping a column in a function or type cast can prevent an index from being used as intended:

```sql
-- More friendly to regular indexes
SELECT *
FROM lock_demo
WHERE code = 15
FOR UPDATE;

-- May lose the ability to do range/ref lookup on the code index
SELECT *
FROM lock_demo
WHERE CAST(code AS CHAR) = '15'
FOR UPDATE;
```

If the optimizer has to scan more records, both lock scope and lock-holding duration can increase. Normalize data types and avoid unnecessary expressions on search columns.

## 11. Gap locks can appear even when SELECT returns zero rows

A common point of confusion is a query returning 0 rows yet still holding locks. Example:

```sql
START TRANSACTION;

SELECT id, code
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

If `code = 15` does not exist, the result is empty. Yet under REPEATABLE READ with a non-unique index, InnoDB may still lock the gap containing 15. Another transaction inserting `code = 15` will wait until the reading transaction finishes.

There is no contradiction here: a locking read protects the search condition, not merely the returned rows. Without locking the gap, another transaction could insert a matching row midway through the current transaction and create a phantom.

Do not infer the number of locks held from the number of returned rows. Check `performance_schema.data_locks` or InnoDB status.

## 12. Foreign key and duplicate-key checks

Even under `READ COMMITTED`, InnoDB may still use gap locking in certain cases required for constraint checking, specifically:

- Foreign key checks when inserting or modifying a child row.
- Duplicate-key checks during INSERT/UPDATE on a unique index.

Thus, the statement "READ COMMITTED has no gap locks" is overly absolute. The accurate phrasing is that gap locking for regular searches/index scans is disabled in READ COMMITTED, except for cases serving foreign key and duplicate-key checks.

When investigating lock waits in READ COMMITTED, inspect both DML operations and table constraints, not only SELECT ... FOR UPDATE.

## 13. Insert intention lock experiment

To observe two INSERTs at different positions in the same gap, you need an initial state with `code` 10 and 20 and no gap lock from other transactions. After ensuring all previous test transactions have ended, clean up the rows inserted in earlier examples:

```sql
DELETE FROM lock_demo
WHERE id IN (4, 5, 6, 7, 8, 9);
```

Keep the original rows with `code` 10, 20, and 30; the gap `(10, 20)` is empty again.

Session B:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (8, 12, 'insert at twelve');
```

Keep transaction B open. Session C:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (9, 18, 'insert at eighteen');
```

Both INSERTs at different positions in the gap `(10, 20)` can complete without waiting for each other. Commit both:

```sql
COMMIT;
```

Run in each respective session. If a prior transaction held a gap lock covering this interval, the outcome would differ: the INSERTs would have to wait for the gap lock to be released.

### Verifying insertion order and index entries

```sql
SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
ORDER BY code, id;
```

Values 12 and 18 are placed between 10 and 20. Insert intention locks prevent inserts at different positions from blocking one another unnecessarily; record locks on the new entries still protect the newly inserted rows themselves.

## 14. Lock waits, deadlocks, and resolution

A lock wait occurs when a transaction needs a lock incompatible with one held by another transaction. The waiting transaction can proceed once the blocker commits/rolls back, or fail when `innodb_lock_wait_timeout` is exceeded.

A deadlock occurs when transactions form a wait cycle. For example:

```text
Transaction A holds lock on row 1, waits for row 2
Transaction B holds lock on row 2, waits for row 1

A ---- waits for ----> B
^                     |
|                     v
<---- waits for ------
```

Two-session example:

Session A:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'A updates row 1'
WHERE id = 1;
```

Session B:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'B updates row 2'
WHERE id = 2;
```

Then Session A:

```sql
UPDATE lock_demo
SET note = 'A updates row 2'
WHERE id = 2;
```

Session A must wait for B. Next, Session B:

```sql
UPDATE lock_demo
SET note = 'B updates row 1'
WHERE id = 1;
```

Now a wait cycle exists. InnoDB detects the deadlock and selects one transaction as the victim to roll back; the other transaction can proceed. The application must catch deadlock errors and retry the entire transaction according to a bounded retry policy, because the victim transaction has already been rolled back.

### Lock wait timeout vs. deadlock

| Situation | Meaning | Handling |
|---|---|---|
| Lock wait timeout (commonly error 1205) | Waiting for a lock beyond the configured timeout | Identify the blocker, reduce lock-holding time, and retry in a controlled way if appropriate. By default InnoDB typically rolls back the timed-out statement, not necessarily the entire transaction. |
| Deadlock (commonly error 1213) | Wait cycle between transactions | InnoDB rolls back the entire chosen victim transaction; the application retries the entire transaction. |

Never retry infinitely. Use randomized backoff, cap the number of attempts, and ensure operations are idempotent or protected by business-level locks.

## 15. Diagnosing locks with Performance Schema

In MySQL 8.0, `performance_schema.data_locks` displays existing locks and `performance_schema.data_lock_waits` links waiting locks to blocking locks.

List locks:

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
  AND OBJECT_NAME = 'lock_demo'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME;
```

Useful columns:

- `INDEX_NAME`: the index being locked; NULL may appear depending on the lock type.
- `LOCK_TYPE`: locked object type, such as TABLE or RECORD.
- `LOCK_MODE`: lock mode and attributes; you may see forms like `X`, `S`, `X,GAP`, `X,REC_NOT_GAP`, or modes with `INSERT_INTENTION`.
- `LOCK_STATUS`: status such as GRANTED or WAITING.
- `LOCK_DATA`: locked index key information if displayable.

Exact mode strings can vary across versions and cases. Read `LOCK_MODE` together with `INDEX_NAME`, `LOCK_TYPE`, `LOCK_STATUS`, and the lock wait graph rather than relying on a single mode string.

### Viewing waiting and blocking transactions

```sql
SELECT
    waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
    waiting.THREAD_ID AS waiting_thread,
    waiting.OBJECT_SCHEMA,
    waiting.OBJECT_NAME,
    waiting.INDEX_NAME,
    waiting.LOCK_MODE AS waiting_lock_mode,
    blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
    blocking.THREAD_ID AS blocking_thread,
    blocking.LOCK_MODE AS blocking_lock_mode,
    blocking.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting
  ON waiting.ENGINE = waits.ENGINE
 AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

From `THREAD_ID`, you can correlate with `performance_schema.threads` or `events_statements_current` to find the connection and running statement, depending on privileges and enabled instrumentation.

### SHOW ENGINE INNODB STATUS

```sql
SHOW ENGINE INNODB STATUS;
```

The `LATEST DETECTED DEADLOCK` section provides details on the most recent deadlock recorded by InnoDB, including the transactions, statements, and locks involved. The TRANSACTIONS section helps inspect active transactions and lock states. This is a diagnostic snapshot at query time, not a complete history of all lock waits.

## 16. Narrowing lock scope in query design

Several practices help limit lock contention:

1. Use primary keys or unique keys when business logic allows looking up a single unique row.
2. Create indexes matching JOIN/WHERE conditions and actual access order.
3. Avoid broad range scans inside write transactions if only a small set of rows is needed.
4. Lock only the rows that need updating; avoid `SELECT ... FOR UPDATE` over an overly wide set.
5. Keep transactions short; do not call APIs, wait for user input, or process files while holding locks.
6. Update multiple rows in a consistent lock order across transactions to reduce deadlock risk.
7. Do not use `LOCK TABLES` as a substitute for row/index locking design without a specific reason.
8. Inspect execution plans because changes in indexes or statistics can alter scan and lock scopes.

Example of a narrow lookup by unique key:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM account_lock_demo
WHERE email = 'a@example.test'
FOR UPDATE;

UPDATE account_lock_demo
SET balance = balance - 10.00
WHERE email = 'a@example.test';

COMMIT;
```

Because `email` has a unique index, the lookup can lock a single record if exactly one row is found. If the business logic has the account ID, using the primary key directly is often even clearer. Ensure the UPDATE predicate matches the exact locked row.

## 17. Workflow for investigating a blocked INSERT

When an INSERT waits even though it is not modifying the same row as another transaction, check in order:

1. Identify the table, index, and key values the INSERT wants to create.
2. Identify the gap in the index where the new value will be placed.
3. Query `performance_schema.data_lock_waits` to find the blocking transaction.
4. Inspect `data_locks` to determine the lock mode, index name, and lock data.
5. Check the isolation level of the transaction holding the lock.
6. Look for earlier locking reads, UPDATEs, or DELETEs over a range.
7. Inspect the execution plan and the actual index used.
8. Determine whether the lock is record, gap, next-key, or insert intention.
9. Finish or adjust the blocking transaction according to business rules.
10. Redesign indexes/predicates to narrow the scope if needed.

An INSERT waiting on a gap lock is not necessarily a bug in the INSERT. A prior transaction may be protecting a range to prevent phantoms. Investigation must start from the lock-holding transaction and why it needs to protect that interval.

## 18. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Thinking a record lock locks a logical row regardless of index | Overlooking locks on secondary/clustered index records | Inspect `INDEX_NAME` and the access path. |
| Thinking a gap lock locks existing records | Misunderstanding scope and conflicts | Gap locks protect empty intervals to prevent inserts. |
| Thinking a gap lock conflicts with all other gap locks | Mispredicting concurrent gap lock holding | Gap locks are inhibitive and can coexist; insert intentions can be blocked. |
| Thinking a next-key lock is only a record lock | Overlooking the preceding gap and phantom protection | Remember next-key = record + preceding gap. |
| Thinking INSERT only needs a new record lock | Failing to understand insert intention and gap lock waits | Check the gap containing the insertion position and blockers. |
| Thinking two INSERTs in the same gap always block each other | Unnecessarily reducing concurrency | Insert intentions at different positions can be compatible if no blocking gap lock exists. |
| Thinking a SELECT returning 0 rows holds no locks | Missing gap locks from locking reads | Check data_locks even when the result set is empty. |
| Thinking READ COMMITTED has zero gap locks | Overlooking FK and duplicate-key checks | Remember constraint-checking exceptions. |
| Using unsuitable or missing indexes | Wide scans/locks and increased waits | Design indexes and check EXPLAIN. |
| Using DISTINCT or altering data to dodge lock waits | Masking symptoms without fixing root cause | Find the blocking transaction, range, and access path. |
| Retrying deadlocks the same way as lock timeouts | Continuing with a rolled-back transaction or inconsistent state | For deadlocks, retry the entire transaction; for timeouts, check transaction state. |

## 19. Practice exercises

### Exercise A — Record lock

1. Create the `lock_demo` table and insert three rows.
2. Session A runs `SELECT ... WHERE id = 2 FOR UPDATE`.
3. Session B runs UPDATE on the same `id = 2`.
4. Observe Session B waiting.
5. Commit Session A and note when Session B resumes.

### Exercise B — Gap lock

1. Set both sessions to `REPEATABLE READ`.
2. Session A looks up `code = 15 FOR UPDATE` when this value does not exist yet.
3. Session B runs INSERT for `code = 15`.
4. Observe the lock wait even though A's SELECT returned 0 rows.
5. Commit/roll back A and verify that the INSERT proceeds.

### Exercise C — Next-key lock

1. Session A runs a locking range read `code BETWEEN 10 AND 20`.
2. Session B tries to INSERT a value inside the range.
3. Try to INSERT outside the range.
4. Observe the blocked range using `data_locks`.
5. Change the index or isolation level in a test environment and compare.

### Exercise D — Insert intention lock

1. Ensure the gap `(10, 20)` has no gap lock.
2. Session B inserts code 12 without committing yet.
3. Session C inserts code 18.
4. Observe that both INSERTs can proceed concurrently.
5. Repeat while Session A holds a gap lock and explain why the result changes.

### Exercise E — Diagnosing deadlocks and lock waits

1. Create a deadlock with two transactions updating two rows in opposite order.
2. Read `SHOW ENGINE INNODB STATUS`.
3. Create a lock wait caused by a gap lock and query `performance_schema.data_lock_waits`.
4. Record the blocker, waiter, index, and lock mode.
5. Propose a consistent update order and a bounded retry strategy.

You complete the lesson when you can distinguish the four lock types, predict when an INSERT will be blocked, explain the role of indexes and isolation levels, and locate lock-holding transactions using MySQL diagnostic tools.

## 20. Key takeaways

- InnoDB locks index records and gaps; indexes/access paths directly affect lock scope.
- A record lock locks a specific index record.
- A gap lock protects the empty space between index records to prevent new inserts; it is inhibitive.
- A next-key lock = a record lock plus the gap immediately before the record.
- An insert intention lock signals intent to insert into a gap; two inserts at different positions may not block each other.
- Locking reads and range DML in REPEATABLE READ normally use next-key locking to prevent phantoms.
- An equality lookup across a full unique index that finds a row typically locks only the record; range/non-unique/missing-key lookups may require gap locks.
- READ COMMITTED disables most gap locking for regular searches/index scans, with exceptions for foreign key and duplicate-key checks.
- A locking read returning 0 rows can still hold a gap lock.
- Do not infer lock scope solely from WHERE or row count; inspect the execution plan and `performance_schema.data_locks`.
- A deadlock normally rolls back the entire victim transaction; a lock wait timeout by default usually rolls back only the timed-out statement.
- Keep transactions short, use appropriate indexes, update in a consistent order, and apply bounded retries.

When you understand record, gap, next-key, and insert intention locks as locks on indexes, you can accurately explain why an operation is blocked, predict the impact of range scans, and design queries with narrower lock scopes. This forms the foundation for reducing lock contention and handling concurrency in InnoDB.
