# Detecting Blocking Chains with pg_locks and pg_blocking_pids

A PostgreSQL query suddenly takes tens of seconds when it normally finishes in milliseconds. CPU is low, `EXPLAIN` does not show a bad plan, and the table only has a few rows. The statement is likely **waiting on a lock** (*lock wait*). The harder part is figuring out **who is blocking whom**: transaction A holds a lock, transaction B waits on A while holding another lock that makes transaction C wait on B. If you only look at C or kill B by mistake, you miss the root cause and trigger unnecessary rollbacks.

PostgreSQL provides two core tools:

- **`pg_catalog.pg_locks`:** a view listing granted and waiting lock requests, along with lock type, lock mode, target object, PID, and related metadata.
- **`pg_catalog.pg_blocking_pids(pid)`:** a function returning an array of PIDs of processes **blocking a given PID** according to the lock manager, including certain soft blockers ahead in the queue.

Combined with **`pg_catalog.pg_stat_activity`**, you can answer: which SQL statement is waiting, since when, whether the blocker is active or `idle in transaction`, whether there are one or multiple blockers, and which backends form the blocking chain.

This lesson teaches you to:

1. Understand **waiter**, **blocker**, **direct blocker**, **upstream/root blocker**, **wait-for graph**, and **blocking chain**.
2. Distinguish PostgreSQL lock types, especially **relation locks**, **transactionid locks**, **tuple locks**, and **advisory locks**.
3. Correctly read `locktype`, `mode`, `granted`, `waitstart`, `pid`, and `fastpath` in `pg_locks`.
4. Use `pg_blocking_pids()` to obtain **direct blocking edges** without guessing wrong from a naive self-join on `pg_locks`.
5. Write queries for a **waiter → blocker graph**, trace **multiple hops** with recursive CTEs, and identify chain endpoints when possible.
6. Reproduce **row-lock contention**, **an A → B → C chain**, **a DDL queue**, and **a deadlock** across multiple sessions.
7. Identify blockers that are **`idle in transaction`**, **prepared transactions**, and **session-level advisory locks**.
8. Decide when to wait, roll back, run `pg_cancel_backend`, run `pg_terminate_backend`, or fix the application.
9. Configure timeouts, monitor with `pg_stat_activity`, and apply best practices in Java/JDBC/connection pools.

> **Operational warning:** These examples intentionally create lock waits and hold transactions open. Run only in a lab database—never on production tables. Never copy PIDs from old screenshots or logs into `pg_terminate_backend`. Terminating a backend rolls back in-flight work, errors applications, and impacts services; it must be verified and authorized under your operational procedures.

## 1. What Is a Lock and Why Do Queries Wait?

PostgreSQL uses multiple locking mechanisms to coordinate concurrent work and protect data correctness. A transaction modifying the same row as another transaction may need to **wait** until the other commits or rolls back. A schema change may require a strong table lock while a read transaction still holds a weaker table lock.

Picture this:

```text
Session A                                    Session B
---------------------------------------      --------------------------------
BEGIN;
UPDATE products SET quantity=8
 WHERE id=1;
-- Keep transaction open
                                             UPDATE products SET quantity=9
                                              WHERE id=1;
                                             -- Waiting
COMMIT;
                                             -- B can proceed
```

**Key point:** A's `UPDATE` finishing does not mean the transaction's locks are released immediately. Many locks are held **until the end of the transaction**. If A opens a transaction and sits waiting for application input, B remains blocked.

### Common Causes of Waiting

- Two transactions concurrently running `UPDATE`/`DELETE` on the same row.
- `SELECT ... FOR UPDATE`/`FOR NO KEY UPDATE` contending on row locks.
- `ALTER TABLE` needing `AccessExclusiveLock` while a query/transaction holds `AccessShareLock`.
- `CREATE INDEX` and DDL coordinating with writers.
- Foreign key or unique constraint checks waiting on another transaction's outcome.
- Advisory locks acquired by the application and not yet released.
- A transaction prepared via `PREPARE TRANSACTION` still holding locks with no active backend.

Not every slowdown is a lock. I/O, network, CPU, buffer contention, and other wait types also slow queries. First identify the **exact wait type**.

## 2. Terminology in a Wait-for Graph

| Term | Meaning |
|---|---|
| **Waiter / blocked backend** | A backend not yet granted a needed lock because of one or more blockers. |
| **Blocker / blocking backend** | A backend holding a conflicting lock or sitting ahead in the wait queue, preventing the waiter from advancing. |
| **Direct blocker** | A backend directly blocking a waiter under lock-manager rules. |
| **Upstream blocker** | A backend blocking another blocker further up the chain. |
| **Root blocker** | The endpoint of a blocking chain, having no upstream blocker **in the observed graph**. |
| **Wait-for graph** | A directed graph of backend nodes with edges `waiter → blocker`. |
| **Blocking chain** | A multi-edge path, such as `C → B → A`. |
| **Deadlock** | A dependency cycle among transactions/locks, such as `A → B → A`. |

A simple chain:

```text
   C ── waits for ──► B ── waits for ──► A
   │                  │                  │
   │                  │                  └── Holds lock blocking B
   │                  └── Waits for A, while holding lock blocking C
   └── C's query is waiting

   Direct blocker of C = B
   Root/upstream blocker of C = A
```

A single waiter can have **multiple direct blockers**, and a single blocker can block **multiple waiters**. Thus the graph is not necessarily a single linear list.

### "Root Blocker" Is Relative to the Observed Graph

If results show A has no blocker, we can call A the **head of the observed chain**. That does not prove A is the "business root cause"; A might be waiting on a remote API, client, network, or a non-heavyweight-lock resource. Fixing it thoroughly requires knowing **why A's transaction has not finished**.

## 3. Distinguishing Lock Waits from Other Wait Types

`pg_stat_activity` includes:

- `state`: backend state, e.g., `active`, `idle`, `idle in transaction`.
- `wait_event_type`: wait event category, such as `Lock`, `IO`, `Client`, `LWLock`, depending on situation and version.
- `wait_event`: specific wait event.

Observation query:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

A backend with:

```text
state = active
wait_event_type = Lock
```

strongly indicates the statement is waiting on a lock managed by the lock manager. Conversely, an `idle in transaction` backend is **not waiting on any lock**, yet can be a **blocker** holding locks from an unfinished transaction.

### Read Both Sides Together

**Waiter:**

```text
state = active
wait_event_type = Lock
query = UPDATE ...
```

**Blocker:**

```text
state = idle in transaction
wait_event_type = Client (often)
query = earlier UPDATE ...
```

The blocking backend may be **waiting for the client to send the next command** while still holding locks. Filtering only `wait_event_type='Lock'` shows the **waiting** side, not necessarily the **holding** side.

## 4. Setting Up the Lab Environment

Create a schema and a small table sufficient to trigger row-level lock contention:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_lockchain;

CREATE TABLE lesson_lockchain.inventory (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO lesson_lockchain.inventory(
    item_id, item_name, quantity
)
VALUES
    (1, 'Keyboard', 10),
    (2, 'Mouse', 20),
    (3, 'Headphones', 30);
```

The examples assume you have:

- **Session A:** one `psql` window, dedicated connection.
- **Session B:** second `psql` window.
- **Session C:** third window when building a chain.
- **Session M:** a **diagnostic** window, never holding blocked lab transactions.

Verify each connection with:

```sql
SELECT current_database(), current_user, pg_backend_pid();
```

Record each session's PID. Never use the same connection or transaction to simulate two backends. Through PgBouncer transaction pooling, client-to-backend mapping can shift outside transactions; use direct connections for this lab.

### Cleaning Up Stuck Sessions

After each experiment:

```sql
ROLLBACK;
```

in sessions with open transactions. If a query is **blocked**, release the blocking transaction in the other session first or cancel safely. Never leave transactions blocking intentionally for minutes just to stare at the graph.

## 5. Reproducing a Row-Lock Wait

### Step 1 — Session A Holds a Lock

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

SELECT pg_backend_pid() AS session_a_pid;
-- Keep transaction open; DO NOT COMMIT or ROLLBACK yet.
```

After the `UPDATE`, A has modified row 1 without committing. Another transaction trying to modify the same row must coordinate/wait on the associated lock.

### Step 2 — Session B Updates the Same Row

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Statement hangs waiting; prompt does not return.
```

While B is waiting, **do not type more commands into connection B**; switch to Session M to inspect.

### Step 3 — Session M Observes

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

B shows `wait_event_type='Lock'`; for typical row-update contention, `wait_event` is `transactionid`. A is in `idle in transaction`.

### Step 4 — Session A Releases the Lock

```sql
ROLLBACK;
```

B's `UPDATE` proceeds. In **Session B**, once the prompt returns:

```sql
ROLLBACK;
```

Two rollbacks restore the lab table to its initial quantities.

## 6. pg_blocking_pids(pid): Fastest Way to Find Direct Blockers

The function:

```sql
SELECT pg_catalog.pg_blocking_pids(<backend_pid>);
```

returns an `integer[]` array containing the PIDs of backends currently blocking the given PID, if any.

In the A-blocks-B scenario:

```text
pg_blocking_pids(B_PID) → {A_PID}
```

In Session M, read PIDs directly from `pg_stat_activity` instead of hardcoding:

```sql
SELECT
    a.pid AS waiting_pid,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

Sample hypothetical output:

| waiting_pid | blocking_pids | wait_event_type | wait_event |
|---:|---|---|---|
| 32102 | `{32101}` | Lock | transactionid |

Never copy those sample PIDs into real commands: PIDs only apply to the live system at sampling time.

### An Empty Array Does Not Mean It Never Waited

`pg_blocking_pids()` returns an empty array if no current blocker is detected. A lock wait may have **just ended** between reading `pg_stat_activity` and evaluating the function. Sampling over time can reveal shifting graphs.

### Function Uses Lock Manager Blocking Semantics

`pg_blocking_pids()` evaluates blocking relationships from the lock manager and is far more accurate than naively comparing `pg_locks` rows with simplistic predicates. It also accounts for **soft blockers** ahead in the wait queue, not only direct conflicting holders.

## 7. Expanding the Blocking PIDs Array into Rows

To turn blockers into relational rows, use `unnest()`:

```sql
SELECT
    a.pid AS waiting_pid,
    b.blocking_pid
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocking_pid)
WHERE a.datname = current_database()
ORDER BY a.pid, b.blocking_pid;
```

Explanation:

1. `pg_stat_activity` supplies backend PIDs.
2. `pg_blocking_pids(a.pid)` finds PIDs directly blocking backend `a`.
3. `unnest` emits **one row per blocker**.
4. `CROSS JOIN LATERAL` lets the right-hand call reference `a.pid`.
5. Unblocked backends return an empty array and are **excluded**.

Example graph:

```text
waiting_pid  blocking_pid
-----------  ------------
32102        32101
32103        32102
```

These two rows form two **edges**:

```text
32103 → 32102 → 32101
```

### One Blocker Can Appear Multiple Times

If three backends wait on one transaction, that blocker PID appears in three rows. If one waiter has multiple blockers, `waiting_pid` repeats. That reflects the many-to-many graph structure, not a bug in `unnest`.

## 8. Comprehensive Waiter and Blocker Monitoring Query

A practical query used across many operational situations:

```sql
SELECT
    waiter.pid AS waiting_pid,
    waiter.usename AS waiting_user,
    waiter.application_name AS waiting_application,
    waiter.state AS waiting_state,
    waiter.wait_event_type,
    waiter.wait_event,
    waiter.query_start AS waiting_query_started_at,
    clock_timestamp() - waiter.query_start AS waiting_query_age,
    blocker_ids.blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_application,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_started_at,
    clock_timestamp() - blocker.xact_start AS blocking_xact_age,
    blocker.state_change AS blocking_state_changed_at,
    waiter.query AS waiting_sql,
    blocker.query AS blocking_last_sql
FROM pg_catalog.pg_stat_activity AS waiter
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(waiter.pid)
) AS blocker_ids(blocking_pid)
LEFT JOIN pg_catalog.pg_stat_activity AS blocker
  ON blocker.pid = blocker_ids.blocking_pid
WHERE waiter.datname = current_database()
ORDER BY waiting_query_age DESC NULLS LAST,
         waiter.pid,
         blocker_ids.blocking_pid;
```

Diagnostic fields:

- **`waiting_query_age`:** elapsed time since statement start—**not necessarily lock wait time**. The statement may have done other work before hitting the lock.
- **`blocking_xact_age`:** elapsed time since the blocker's transaction started, if present.
- **`blocking_state`:** whether the blocker is active or `idle in transaction`.
- **`blocking_last_sql`:** the SQL reported for the blocker. When the blocker is idle, this is its **most recent statement**, not necessarily the statement that took the lock.

### Why Use clock_timestamp()?

`now()` returns transaction start time. If a monitoring connection keeps a transaction open long, `now() - query_start` freezes relative to that transaction start. `clock_timestamp()` reads the live wall clock when called. Even so, run monitoring queries in short transactions.

### Null Blocker Columns

`LEFT JOIN pg_stat_activity` may find no matching backend at sample time (the backend exited, special PID, or permissions/race). Never conclude "no blocker exists" just from `blocking_user IS NULL`; inspect `blocking_pid` and context first.

## 9. Inspecting a Specific PID

When an application log reports a waiting PID:

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.backend_start,
    a.xact_start,
    a.query_start,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers,
    a.query
FROM pg_catalog.pg_stat_activity AS a
WHERE a.pid = 32102;
```

Replace `32102` with the freshly observed PID, not the example number.

**`backend_start` is critical:** OS PIDs can be reused after an old backend exits. Before acting on a PID, re-verify PID, `backend_start`, user, database, `application_name`, and current state.

### Query Text Visibility Limits

`pg_stat_activity.query` may be truncated by `track_activity_query_size` and restricted by monitoring role privileges. Query text can also contain sensitive data if literals were interpolated. Never expose raw user SQL on public dashboards.

## 10. What Is pg_locks?

`pg_catalog.pg_locks` is a view showing lock requests tracked by PostgreSQL's lock manager, including both **granted** locks and **waiting** requests.

Inspecting locks with PIDs:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    waitstart,
    database,
    relation,
    page,
    tuple,
    transactionid,
    virtualxid,
    fastpath
FROM pg_catalog.pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, granted, locktype, mode;
```

**You cannot read a single `pg_locks` row and immediately infer the whole blocking chain.** You must know which key columns each `locktype` uses, which modes conflict, and queue ordering. That is why `pg_blocking_pids` is preferred for **direct blocking relationships**.

### Key Columns

| Column | Meaning |
|---|---|
| `pid` | Backend PID holding/requesting the lock; may be `NULL` e.g. for prepared transactions. |
| `locktype` | Type of lockable object, such as `relation`, `transactionid`, `virtualxid`, `tuple`, `advisory`. |
| `mode` | Requested/held lock mode; consult compatibility matrix for conflicts. |
| `granted` | `true` if held, `false` if still waiting. |
| `waitstart` | Timestamp when lock waiting began, when recorded. |
| `database`, `relation` | Matching database/relation OIDs when used by that `locktype`. |
| `page`, `tuple` | Page/tuple location details for applicable lock types. |
| `transactionid`, `virtualxid` | Transaction identifiers depending on lock type. |
| `classid`, `objid`, `objsubid` | Identifiers used by certain lock types, including object/advisory locks. |
| `fastpath` | Whether the lock was acquired via the lock manager's fast-path mechanism. |

### granted=false May Not Have waitstart Immediately

`waitstart` can briefly be `NULL` right after a process begins waiting because recording it is not strictly atomic with setting wait state. To detect lock waits reliably, combine **`granted=false`**, `wait_event_type='Lock'`, and `pg_blocking_pids`.

## 11. Querying Waiting Lock Requests

To inspect entries with `granted = false`:

```sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.waitstart,
    clock_timestamp() - l.waitstart AS lock_wait_age,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    a.query
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = l.pid
WHERE NOT l.granted
ORDER BY l.waitstart NULLS LAST, l.pid;
```

**`clock_timestamp() - l.waitstart`** is a much closer measure of current lock-wait duration than `clock_timestamp() - query_start`, once `waitstart` is populated.

### Why Do the Two Ages Differ?

A statement might:

1. Start executing at 10:00:00.
2. Scan/filter data for 5 seconds.
3. Hit a lock at 10:00:05.
4. Be observed at 10:00:08.

Then:

```text
query_age = 8 seconds
lock_wait_age = 3 seconds
```

Do not blame all 8 seconds of query duration on lock waiting when analyzing SLAs accurately.

## 12. Why Doesn't pg_locks Always Show Row Locks Directly?

This is one of the easiest PostgreSQL concepts to misunderstand.

When a transaction `UPDATE`s a row, row-level lock state is typically stored **in the tuple on disk**, rather than every held row lock appearing as a `tuple` row with `granted=true` in `pg_locks`.

When transaction B waits for transaction A that updated that row, B's `pg_locks` entry often shows:

```text
locktype      mode        granted   transactionid
------------- ----------- --------- -------------
transactionid ShareLock   false     <A's XID>
```

while A holds the corresponding `transactionid` lock:

```text
locktype      mode           granted
------------- -------------- -------
transactionid ExclusiveLock  true
```

This is a **typical pattern**, not rigid output for every row-lock conflict.

### Debugging Consequence

Never write a query filtering only:

```sql
WHERE locktype = 'tuple'
```

and conclude there is no row-lock contention if it returns 0 rows. The row is locked in the tuple header, while the waiter blocks on a **`transactionid` lock**.

### Why Do tuple Locks Sometimes Appear in pg_locks?

Certain multi-waiter row contention states create transient `locktype='tuple'` entries in `pg_locks`. That does not contradict the fact that **primary row-lock state lives in heap tuples**, rather than every row lock appearing as a relation-like row in `pg_locks`.

**Preferred approach:** use `pg_blocking_pids(waiter_pid)` to find the blocker, then inspect `pg_locks` to see what resource type the waiter is waiting on.

## 13. Common Lock Types

| `locktype` | Typical scenario |
|---|---|
| `relation` | Locks on tables, indexes, sequences, or relations; DML/SELECT/DDL take different modes. |
| `transactionid` | Waiting on another transaction to finish, common in row-update/unique/FK contention. |
| `virtualxid` | Coordination by virtual transaction ID, seen in maintenance operations waiting for other transactions. |
| `tuple` | Certain tuple-level lock requests/waits. |
| `page` | Page-level locks in special cases. |
| `object` | Non-relation database object locks, depending on command. |
| `advisory` | Application-requested advisory locks. |
| `spectoken` | Associated with speculative insertion / unique handling. |
| `extend`, `frozenid`, others | Internal locking mechanisms for specific operations/data regions. |

Not every `locktype` uses `relation`, `transactionid`, or `page`. Irrelevant columns are `NULL`. Filter and join based on **`locktype`**, without forcing every row into a table name.

## 14. Relation Lock Modes

PostgreSQL has eight relation lock modes; names containing "Row" or "Share" **must not be mistaken for row-level locks**.

Common table-level modes:

| Mode | Example commands | Notable conflict behavior |
|---|---|---|
| `AccessShareLock` | Plain `SELECT`. | Conflicts with `AccessExclusiveLock`. |
| `RowShareLock` | `SELECT ... FOR UPDATE/SHARE`. | Conflicts with `ExclusiveLock`, `AccessExclusiveLock`. |
| `RowExclusiveLock` | `INSERT`, `UPDATE`, `DELETE`. | Conflicts with stronger `SHARE`/DDL modes. |
| `ShareUpdateExclusiveLock` | Plain `VACUUM`/`ANALYZE`, `CREATE INDEX CONCURRENTLY`, maintenance. | Self-conflicting; conflicts with stronger modes. |
| `ShareLock` | Regular `CREATE INDEX`. | Conflicts with `RowExclusiveLock` writers and stronger modes. |
| `ShareRowExclusiveLock` | Certain DDL/trigger operations. | Conflicts with many modes, including itself. |
| `ExclusiveLock` | Special tasks excluding strong modes. | Conflicts with most modes except `AccessShareLock`. |
| `AccessExclusiveLock` | Many `ALTER TABLE` commands, `TRUNCATE`, strong DDL. | Conflicts with **all** table-level lock modes. |

This is a directional summary, not a replacement for the official compatibility table of your server version. When checking a pair of locks, verify **modes, target object, and queue state**.

### SELECT Can Block ALTER TABLE

A plain `SELECT` holds `AccessShareLock` on the relation for the transaction, while many `ALTER TABLE` commands need `AccessExclusiveLock`. Because those two conflict, `ALTER TABLE` waits until the `AccessShare` transaction ends.

### Why RowExclusiveLock Is Misleading

`RowExclusiveLock` is a **relation lock mode**; it does not mean "this is a list of locked rows." Row locking uses a separate mechanism, as explained under `tuple`/`transactionid`.

## 15. Resolving Relation Lock Object Names

OIDs in `pg_locks` can be joined to `pg_class` and `pg_namespace` when the relation lives in **the current database**:

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    CASE
        WHEN c.oid IS NOT NULL
        THEN format('%I.%I', n.nspname, c.relname)
        ELSE NULL
    END AS relation_name,
    l.database,
    l.relation,
    l.transactionid
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_class AS c
  ON c.oid = l.relation
 AND l.database = (
     SELECT oid
     FROM pg_catalog.pg_database
     WHERE datname = current_database()
 )
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE l.pid IS NOT NULL
  AND (NOT l.granted OR l.locktype = 'relation')
ORDER BY l.pid, l.granted, l.mode;
```

Why check `l.database`?

- `pg_locks` reports locks from **other databases** on the same cluster.
- `pg_class` only reflects relation catalogs of the connected database.
- A relation OID in another database can collide with a local OID; joining without checking `database` produces **wrong table names**.
- Shared cluster-wide locks have special or `NULL` `database` values and should not be forced into local relations.

When a relation cannot be resolved locally, keep raw `database`/`relation`/`locktype` for inspection instead of guessing table names.

## 16. Why Not Self-Join pg_locks Directly to Find Blockers?

A tempting idea:

```sql
SELECT ...
FROM pg_locks waiter
JOIN pg_locks holder
  ON waiter.relation = holder.relation
WHERE NOT waiter.granted
  AND holder.granted;
```

However, **this sketch query is inaccurate**, because:

1. Two locks on the same relation **may be mode-compatible**.
2. Row-update waits appear as `transactionid`, not `relation`.
3. Locks identify targets via different columns depending on `locktype`.
4. **Soft blockers** sit ahead in the queue without `granted=true`.
5. Relation OIDs must be matched alongside `database`.
6. `pg_locks` collects state across lock-manager partitions without guaranteeing a globally atomic snapshot.
7. Parallel queries and prepared transactions are more complex than simple PID pairs.

That is why PostgreSQL provides **`pg_blocking_pids()`** to answer who is blocking whom directly using lock-manager rules.

**Operational tip:** use `pg_blocking_pids()` to build the graph; use `pg_locks` to interpret **which lock requests are waiting and which resource types are involved**.

## 17. Hard Blockers and Soft Blockers

Two concepts:

- **Hard blocker:** a backend **holding a granted lock** that conflicts with the waiter's request.
- **Soft blocker:** a backend **standing ahead of the waiter in the lock queue** whose requested mode conflicts with the waiter's request. A soft blocker may not have been granted its lock yet.

Example:

```text
Session A: holds AccessShareLock on table inventory
Session B: queued waiting for AccessExclusiveLock to ALTER TABLE
Session C: arrives later, requests AccessShareLock to SELECT
```

In terms of mode compatibility:

- C's `AccessShareLock` **is compatible** with A's `AccessShareLock`.
- Yet B is **waiting for `AccessExclusiveLock`** ahead in the queue.
- The lock manager holds C behind B to preserve fairness and prevent starvation.

Diagram:

```text
        Granted
A [AccessShare]
        │
        │ hard conflict
        ▼
B [AccessExclusive waiting]
        │
        │ soft blocking in queue
        ▼
C [AccessShare waiting]
```

If you only join waiters with `granted=true` holders on the same relation, you fail to explain **why C is waiting**. `pg_blocking_pids(C_PID)` reports **B** as a soft blocker, and the graph reveals C → B → A.

### Behavior of pg_blocking_pids

The function accounts for both hard and soft blocking. Never assume a `blocking_pid` must hold `granted=true` on the exact lock the waiter requested in every scenario.

## 18. DDL Queueing Experiment

This is a three-session experiment—run it quickly on the lab table.

**Session A:**

```sql
BEGIN;

SELECT COUNT(*)
FROM lesson_lockchain.inventory;

-- Keep BEGIN open, holding transaction AccessShareLock.
```

**Session B:**

```sql
ALTER TABLE lesson_lockchain.inventory
ADD COLUMN IF NOT EXISTS demo_note TEXT;
-- Waits for AccessExclusiveLock.
```

**Session C**, while B is waiting:

```sql
SELECT COUNT(*)
FROM lesson_lockchain.inventory;
-- Waits because B sits ahead in the lock queue.
```

**Session M:**

```sql
SELECT
    a.pid AS waiter_pid,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS sql_excerpt
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

**Session A:**

```sql
ROLLBACK;
```

Then B completes `ALTER TABLE` and C finishes. Because `ALTER TABLE` commits automatically under autocommit, to keep the lab schema clean you can either:

- Run `ALTER TABLE` inside `BEGIN ... ROLLBACK` in B, or
- Drop the demo column deliberately afterward.

Never run this experiment on a live production table because requesting `AccessExclusiveLock` creates a **blocking queue** stalling reads and writes.

## 19. Building a Three-Level Blocking Chain A → B → C

Target structure:

```text
C wants to update item 2
  │
  ▼
B holds row lock on item 2,
  while B waits to update item 1
  │
  ▼
A holds row lock on item 1

Wait-for chain: C → B → A
```

### Session A — Hold Item 1

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

-- Keep transaction open.
```

### Session B — Hold Item 2, Then Wait on Item 1

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Waits for A; prompt does not return.
```

### Session C — Wait on Item 2

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
-- Waits for B.
```

### Session M — Observe the Edges

```sql
SELECT
    a.pid AS blocked_pid,
    b.blocker_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 140) AS blocked_sql
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocker_pid)
WHERE a.datname = current_database()
ORDER BY blocked_pid, blocker_pid;
```

Conceptual output:

```text
blocked_pid  blocker_pid
C_PID        B_PID
B_PID        A_PID
```

### Ending the Experiment in Proper Order

1. **Session A:** `ROLLBACK;` → B unblocks.
2. **Session B:** once `UPDATE` finishes, `ROLLBACK;` → C unblocks.
3. **Session C:** once `UPDATE` finishes, `ROLLBACK;`.

Do not try to roll back B while B is blocked on `UPDATE` by typing into the same session: the client will not execute subsequent commands until the waiting statement finishes or is canceled.

## 20. Tracing Multiple Hops with WITH RECURSIVE

The blockers array gives only **one hop**. To walk from C to B to A, materialize the edges in a CTE and recurse:

```sql
WITH RECURSIVE edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
),
paths AS (
    SELECT
        e.waiting_pid AS origin_waiting_pid,
        e.blocker_pid AS current_blocker_pid,
        ARRAY[e.waiting_pid, e.blocker_pid]::integer[] AS pid_chain,
        1 AS depth
    FROM edges AS e

    UNION ALL

    SELECT
        p.origin_waiting_pid,
        e.blocker_pid,
        p.pid_chain || e.blocker_pid,
        p.depth + 1
    FROM paths AS p
    JOIN edges AS e
      ON e.waiting_pid = p.current_blocker_pid
    WHERE p.depth < 16
      AND NOT e.blocker_pid = ANY(p.pid_chain)
)
SELECT
    origin_waiting_pid,
    current_blocker_pid,
    depth,
    pid_chain
FROM paths
ORDER BY origin_waiting_pid, depth, pid_chain;
```

Explanation:

1. `edges` converts `pg_blocking_pids` into `waiting_pid → blocker_pid` edges.
2. The base term of `paths` seeds **two-PID** paths at `depth=1`.
3. The recursive term appends blockers of **`current_blocker_pid`**.
4. `pid_chain` tracks the full visited path.
5. `NOT e.blocker_pid = ANY(p.pid_chain)` prevents revisiting a PID already in the path.
6. `p.depth < 16` caps recursion depth so monitoring queries never run unbounded on large/anomalous graphs.

For the experiment above:

```text
origin_waiting_pid  depth  pid_chain
C_PID               1      {C_PID,B_PID}
C_PID               2      {C_PID,B_PID,A_PID}
B_PID               1      {B_PID,A_PID}
```

### Multiple Blockers Create Multiple Branches

If C is blocked by both B and D, the output yields two paths:

```text
C → B → A
C → D → E
```

Do not collapse results into a single "root PID." Keep all branches and identify each endpoint.

### Limits of the Recursive Query

The lock graph can **change while the query executes**. Although `edges` freezes one snapshot of edges inside the query, calling functions across rows can reflect closely spaced moments rather than a single atomic instant. Treat this as a **diagnostic snapshot**, not an absolute lock history.

## 21. Identifying Chain Endpoints in the Observed Graph

An **endpoint** (terminal blocker) is a blocker for which the current edge set **records no upstream blocker**.

From:

```text
C → B
B → A
```

A is the endpoint of the path starting at C.

Extend the query:

```sql
WITH RECURSIVE edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
),
paths AS (
    SELECT
        e.waiting_pid AS origin_pid,
        e.blocker_pid AS current_pid,
        ARRAY[e.waiting_pid, e.blocker_pid]::integer[] AS path,
        1 AS depth
    FROM edges AS e

    UNION ALL

    SELECT
        p.origin_pid,
        e.blocker_pid,
        p.path || e.blocker_pid,
        p.depth + 1
    FROM paths AS p
    JOIN edges AS e
      ON e.waiting_pid = p.current_pid
    WHERE p.depth < 16
      AND NOT e.blocker_pid = ANY(p.path)
)
SELECT
    p.origin_pid AS blocked_pid,
    p.current_pid AS terminal_blocker_pid,
    p.depth,
    p.path AS observed_path,
    CASE
        WHEN p.current_pid = 0
        THEN 'prepared transaction'
        ELSE 'no upstream blocker in sampled graph'
    END AS terminal_kind
FROM paths AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM edges AS e
    WHERE e.waiting_pid = p.current_pid
)
ORDER BY p.origin_pid, p.depth DESC;
```

**Interpreting results carefully:**

- `terminal_blocker_pid` is the endpoint **within the observed edges**, not necessarily the sole culprit.
- Graphs with **cycles** or exceeding `depth < 16` may lack a simple endpoint, so an affected waiter might not appear in the terminal output.
- **PID 0** can represent a blocker belonging to a **prepared transaction**, not an OS process to terminate.
- A blocker not waiting on any PostgreSQL heavyweight lock may still be waiting on a client, network, or external system.

Never run `pg_terminate_backend(terminal_blocker_pid)` automatically just because a query labeled it terminal.

## 22. Blocking Chains with an idle in transaction Blocker

A very common root cause:

```text
Service A:
BEGIN
UPDATE inventory ...
call HTTP API or wait for user
-- Never COMMITs/ROLLBACKs

Service B:
UPDATE same row → waits

Service C:
UPDATE row held by Service B → waits for B
```

Here:

- A sits in `state='idle in transaction'`.
- B and C sit in `state='active'`, `wait_event_type='Lock'`.
- A **does not have `wait_event_type='Lock'`** because it is not a waiter; it is the holder.

Query to spot idle sessions with open transactions:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    state_change,
    clock_timestamp() - state_change AS idle_state_age,
    left(query, 300) AS last_reported_sql
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
```

This is a **suspect list**, not proof that each listed session blocks another backend. To confirm who is blocking whom, check edges from `pg_blocking_pids`.

### Why Not Automatically Kill Every Idle Transaction?

Some transactions are held intentionally for business/backup workflows without blocking anyone. Terminating them forces rollbacks. Conversely, a very brief idle transaction is completely normal.

Decisions must consider **duration, blocker count, SLA, owning service, and impact**.

## 23. Counting Waiters Affected by a Blocker

A blocker stalling 20 requests has far greater impact than one blocking a single test query.

```sql
WITH edges AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
)
SELECT
    blocker_pid,
    COUNT(DISTINCT waiting_pid) AS directly_blocked_backends
FROM edges
GROUP BY blocker_pid
ORDER BY directly_blocked_backends DESC, blocker_pid;
```

**`COUNT(DISTINCT waiting_pid)`** counts directly blocked backends, not backends waiting **indirectly across multiple hops**. To measure chain-wide blast radius, walk paths with the recursive CTE and count distinct `origin_pid`s per terminal blocker.

### Avoid Double-Counting Indirect Waiters

In multi-branch graphs, one waiter can reach the same blocker via multiple paths. To count unique affected backends, use `COUNT(DISTINCT origin_pid)`, never plain `COUNT(*)` over all paths.

## 24. Inspecting pg_locks for Waiter and Blocker PIDs

Once you have the PID pair, query `pg_locks` to inspect metadata on **both sides**:

```sql
WITH watched_pids AS (
    SELECT
        a.pid AS waiting_pid,
        b.blocker_pid
    FROM pg_catalog.pg_stat_activity AS a
    CROSS JOIN LATERAL unnest(
        pg_catalog.pg_blocking_pids(a.pid)
    ) AS b(blocker_pid)
)
SELECT
    l.pid,
    CASE
        WHEN l.pid IN (
            SELECT waiting_pid FROM watched_pids
        )
        THEN 'WAITING'
        WHEN l.pid IN (
            SELECT blocker_pid FROM watched_pids
        )
        THEN 'BLOCKING'
        ELSE 'OTHER'
    END AS role_in_graph,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    l.fastpath
FROM pg_catalog.pg_locks AS l
WHERE l.pid IN (
    SELECT waiting_pid FROM watched_pids
    UNION
    SELECT blocker_pid FROM watched_pids
)
ORDER BY l.pid, l.granted, l.locktype, l.mode;
```

One PID can be **both WAITING and BLOCKING** (Session B in the three-tier chain). The `CASE` expression above prioritizes the `WAITING` label when a PID is in both sets; that label is just a quick display aid. If you need precision, display **two boolean flags**:

```sql
SELECT
    pid,
    EXISTS (
        SELECT 1 FROM pg_catalog.pg_stat_activity AS a
        WHERE a.pid = l.pid
          AND cardinality(pg_catalog.pg_blocking_pids(a.pid)) > 0
    ) AS is_waiting_on_someone
FROM pg_catalog.pg_locks AS l
WHERE NOT l.granted;
```

Multiple rows per PID are normal because `pg_locks` lists multiple lock requests. When counting PIDs, apply `DISTINCT` as needed.

## 25. pg_locks Across Multiple Databases

`pg_locks` in a PostgreSQL instance contains lock entries from every database in the cluster. Some locks apply to cluster-wide shared objects and have a special or `NULL` database OID.

When resolving `relation` names, **only join the current database's relation catalog** when `l.database` matches. For instance-wide monitoring:

```sql
SELECT
    l.pid,
    d.datname,
    l.locktype,
    l.mode,
    l.granted,
    l.database,
    l.relation
FROM pg_catalog.pg_locks AS l
LEFT JOIN pg_catalog.pg_database AS d
  ON d.oid = l.database
ORDER BY l.pid NULLS LAST, l.granted;
```

Never treat `relation=12345` in database A and database B as the same table. Not every lock has a relation; for `transactionid`/`virtualxid` or `advisory`, inspect the corresponding fields.

## 26. Advisory Locks: Blockers Not Necessarily Tied to Tables

Applications can explicitly take **advisory locks**:

```sql
SELECT pg_catalog.pg_advisory_lock(12345);
```

This is a **session-level advisory lock**. Once acquired, it persists **across `COMMIT`/`ROLLBACK`** until explicitly unlocked or the session ends.

Another transaction/session:

```sql
SELECT pg_catalog.pg_advisory_lock(12345);
-- Waits for the first session to release the lock.
```

Observe:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_catalog.pg_locks
WHERE locktype = 'advisory'
ORDER BY pid, granted;
```

### Releasing Properly

In the session that acquired the advisory lock:

```sql
SELECT pg_catalog.pg_advisory_unlock(12345);
```

For **transaction-level advisory locks**:

```sql
BEGIN;

SELECT pg_catalog.pg_advisory_xact_lock(12345);

-- Perform work...

ROLLBACK;
-- Transaction-level advisory lock is released.
```

### Why Are Advisory Blockers Easy to Miss?

A session-level holder can sit in `state='idle'`, **with no open transaction**, while still holding an advisory lock. Filtering only for `idle in transaction` will **miss** it.

`pg_blocking_pids` still identifies the PID blocking the advisory lock request. Check `pg_locks.locktype='advisory'` and application logic to see why it remains held.

### Do Not Use Advisory Locks as Security Controls

Advisory locks are voluntary coordination among sessions permitted to call them—not replacements for unique constraints, row-level security, or access control.

## 27. Prepared Transactions: Blockers Without a Normal PID

PostgreSQL supports **two-phase commit** via `PREPARE TRANSACTION` when configured. A prepared transaction still **holds its locks** even though no active client backend owns it anymore.

In such cases:

- `pg_locks.pid` for locks held by a prepared transaction is `NULL`.
- `pg_blocking_pids()` reports **0** for a prepared-transaction blocker.
- You **cannot** handle PID 0 with `pg_cancel_backend(0)` or `pg_terminate_backend(0)`.

Inspect:

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

This view lists prepared transactions that must be resolved according to your distributed transaction protocol.

### Never Roll Back a Prepared Transaction Arbitrarily

Commands like:

```sql
-- Example syntax; NEVER run blindly in production:
-- COMMIT PREPARED 'gid-assigned-by-coordinator';
-- ROLLBACK PREPARED 'gid-assigned-by-coordinator';
```

can break distributed transaction atomicity. Always coordinate with the **transaction coordinator**, application, and owner before committing or rolling back. An orphaned prepared transaction is an operational recovery incident, not a simple "kill PID" task.

### What If pg_prepared_xacts Is Empty?

Do not assume every `blocking_pid=0` result is already explained. Re-check statistics visibility, inspect cluster-wide state, and consult your PostgreSQL version's documentation. Still, prepared transactions are always the primary check whenever PID 0 appears.

## 28. Parallel Queries and Blocker PIDs

In parallel queries, PostgreSQL uses a leader and parallel workers. `pg_blocking_pids` applies specific PID mapping rules for parallel queries. Results may:

- Report the **leader PID** representing the parallel session in certain contexts.
- Contain duplicate PIDs when multiple parallel workers are involved.

**Never assume every array element represents a distinct physical backend to handle separately.** To count distinct client sessions, apply `DISTINCT` over leader-normalized PIDs while understanding the function's semantics.

### Why This Matters Before Terminating

Never kill a PID from output without checking whether it is a leader/worker, who owns the query, and whether it belongs to a critical background job.

## 29. Deadlock vs. a Normal Blocking Chain

A chain with an endpoint:

```text
C → B → A
          │
          └── A is working and can COMMIT/ROLLBACK
```

A deadlock has a cycle:

```text
A holds row 1, waits for row 2
  ▲                 │
  │                 ▼
B holds row 2, waits for row 1
  └─────────────────┘

Wait-for cycle: A → B → A
```

PostgreSQL has a **deadlock detector**. After the detection delay, the server chooses one transaction as the victim and returns:

```text
ERROR: deadlock detected
SQLSTATE: 40P01
```

The failed transaction must roll back; the application can retry the **entire transaction** per policy.

### Deadlock Experiment (Lab Only)

**Session A:**

```sql
BEGIN;
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
```

**Session B:**

```sql
BEGIN;
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
```

**Session A:**

```sql
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 2;
-- Waits for B.
```

**Session B:**

```sql
UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;
-- Creates cycle; one transaction receives 40P01.
```

Upon receiving `40P01`, that transaction has failed and must run `ROLLBACK`. The surviving transaction proceeds; run `ROLLBACK` in it too to restore lab state.

### Do Not Expect a Single SELECT to Always Catch the Cycle

The deadlock detector often resolves cycles quickly, so the cyclic graph exists only briefly. When investigating recurring deadlocks, read **server logs** and SQLSTATEs rather than relying on catching the cycle live in a monitoring query.

## 30. deadlock_timeout and log_lock_waits

PostgreSQL provides settings for observing contention:

- `deadlock_timeout`: wait time before running deadlock detection; also governs when lock-wait logs are emitted when enabled.
- `log_lock_waits`: logs lock waits exceeding the threshold.
- `lock_timeout`: caps **lock wait duration** for a statement.
- `statement_timeout`: caps total statement execution time.
- `idle_in_transaction_session_timeout`: terminates sessions left idle in transaction too long.

Inspect runtime settings:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'deadlock_timeout',
    'log_lock_waits',
    'lock_timeout',
    'statement_timeout',
    'idle_in_transaction_session_timeout'
)
ORDER BY name;
```

### Privileges and Changing Settings

Not every parameter can be changed by regular users. Some require superuser or specific privileges per PostgreSQL version. Never run `ALTER SYSTEM` or alter server-wide config just to reproduce a lab example.

### Where log_lock_waits Helps

When brief lock waits happen repeatedly and cannot be caught live manually, server logs provide far better evidence than an ad-hoc `SELECT`. Logs record PID, lock mode, target object/transaction, and wait duration in your configured log format.

Do not leave verbose logging enabled indefinitely without evaluating log volume, sensitive literals, and operational cost.

## 31. lock_timeout and statement_timeout: Avoiding Infinite Waits

In a test transaction:

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

UPDATE lesson_lockchain.inventory
SET quantity = quantity + 1
WHERE item_id = 1;

ROLLBACK;
```

If a blocker holds row 1:

- `lock_timeout` aborts the statement after waiting >1 second for a lock, raising a lock-not-available SQLSTATE.
- `statement_timeout` aborts the statement if total execution exceeds 5 seconds.
- Inside an explicit transaction, a failed statement puts the transaction into **aborted** state. Subsequent statements fail until a valid `ROLLBACK` or `ROLLBACK TO SAVEPOINT`.

### The Two Timeouts Do Not Replace Each Other

`lock_timeout` measures only **lock wait time**; a query spending 10 minutes on CPU/I/O without waiting for any lock is unaffected by `lock_timeout`.

`statement_timeout` bounds total statement time, though a 5-second statement is not necessarily blocked on locks. Use both according to SLAs and actual root causes.

### Do Not Set lock_timeout to 0 to Avoid Waiting

In PostgreSQL, `0` **disables the timeout** rather than meaning "no wait." To fail immediately on a row lock, use `NOWAIT` where supported, or set a small positive timeout.

## 32. Deciding Remediation: Wait, Cancel, or Terminate?

Once the blocker is identified, options include:

1. **Wait for natural release** if the blocker is legitimate, about to commit, and impact is acceptable.
2. **Have the owner/application commit or roll back** if a transaction is sitting idle.
3. **Cancel the statement** with `pg_cancel_backend(pid)` when appropriate.
4. **Terminate the backend** with `pg_terminate_backend(pid)` when authorized and approved.
5. **Resolve prepared transactions** via the 2PC protocol if there is no backend PID.
6. **Fix the root design** to prevent recurrence (short transactions, consistent lock ordering, retries, indexes).

### pg_cancel_backend(pid)

```sql
SELECT pg_catalog.pg_cancel_backend(32101);
```

This is **example syntax**; never run against an illustrative PID. It requests canceling the running query on the target backend when permitted.

**Key limitation:** if the blocker is **`idle in transaction`**, it has no running statement to cancel. Canceling a query does not commit or roll back an open transaction or release held locks.

### pg_terminate_backend(pid)

```sql
SELECT pg_catalog.pg_terminate_backend(32101);
```

Requests terminating the backend. Uncommitted work rolls back as the session exits. Depending on version/signature, the return value reports signal delivery or wait completion; never treat a boolean alone as proof that all downstream cleanup finished instantaneously when the client received the response.

### Risks of Terminating

- Rolls back legitimate transactions.
- Fails in-flight user requests.
- Triggers retry storms.
- Causes HTTP/worker errors and SLA breaches.
- Can hit administrative sessions or critical background services.

Act only after verifying owner and **expected blast radius**—never terminate automatically from a single diagnostic query.

## 33. Permissions for Cancel and Terminate

PostgreSQL restricts who can signal other backends. Regular roles cannot cancel/terminate arbitrary sessions. Privileges such as `pg_signal_backend` membership or superuser have specific rules depending on version and target role.

**Least-privilege principles:**

- Grant backend signaling only to trusted operators/automation.
- Never grant superuser just to read `pg_locks` or `pg_stat_activity`.
- Monitoring roles can use `pg_monitor` or `pg_read_all_stats` as appropriate.
- Separate **observation** privileges from **termination** privileges.
- Audit all incident cancel/terminate actions.

Before signaling a PID, re-verify:

```sql
SELECT
    pid,
    backend_start,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_excerpt
FROM pg_catalog.pg_stat_activity
WHERE pid = 32101;
```

Replace the example PID with the latest observed value; abort if the PID no longer exists or no longer matches the expected session.

## 34. Reading Blocker Query Text in Context

`pg_stat_activity.query` is helpful, yet easily misread.

**If `state='active'`:** `query` represents the statement currently executing.

**If `state='idle in transaction'`:** `query` is the **most recent** statement executed before waiting on the client—not necessarily the statement that acquired the blocking lock.

Example:

```text
BEGIN
UPDATE inventory SET quantity=... WHERE item_id=1   ← holds lock
SELECT 1                                             ← most recent query
[idle in transaction]
```

Monitoring displays `SELECT 1` as blocker A's `query`, yet **the blocking lock actually came from the earlier `UPDATE`**.

Therefore, to find the true cause:

- Check `pg_locks` for lock holders and object types.
- Use application logs/tracing with request IDs, business transaction IDs, or connection IDs.
- Inspect JDBC/Spring transaction lifecycles.
- Never conclude "`SELECT 1` is holding a row lock" solely from `blocking_last_sql`.

### Query Text Can Be Truncated

`track_activity_query_size` caps captured query length. Prepared statements with parameters do not always display bound values either. Use permitted diagnostics and avoid exposing PII/secrets.

## 35. Using Multiple Connections to Reproduce Accurately

A common lab mistake is running:

```sql
BEGIN;
UPDATE ...;
UPDATE ...;
```

**in the same session** and thinking the second `UPDATE` waits on the first. Within one transaction, you do not self-block on the same row lock the way two independent sessions do.

To construct a blocker/waiter pair:

```text
Connection A: transaction T_A
Connection B: transaction T_B
Connection M: monitor, outside T_A and T_B
```

With connection pools, remember:

- Each JDBC `Connection` represents a distinct transaction context when configured directly.
- One request may borrow a connection and hold a transaction across multiple repository calls.
- Frameworks may manage transaction start/end automatically, so identify the transaction owner before testing.

Never leave lock-wait test code inside parallel unit tests against a shared database without timeouts and cleanup.

## 36. JDBC: Setting application_name to Locate Blockers

A Java system with multiple services/workers should set `application_name` so `pg_stat_activity` identifies the connection source.

Illustrative JDBC URL:

```text
jdbc:postgresql://db.example.invalid:5432/demo?ApplicationName=inventory-service
```

Or intentionally within a session/transaction:

```sql
SET application_name = 'inventory-service';
```

Note that `application_name` is a diagnostic label, **not a secure/authenticated identity**. Clients can set it freely per driver rules; never rely on it for authorization.

### Connection Pools

If a pool shares one database role across many services, `usename` looks identical on every session. Combine:

- `application_name`.
- `backend_start` and `pid`.
- Request trace/correlation IDs in logs.
- `xact_start` and `query_start`.
- Service instance metadata where permitted by monitoring.

Never equate a PID with a single HTTP user permanently: one backend handles many requests sequentially.

## 37. Aborted JDBC Transactions After lock_timeout

Java pattern:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (Statement st = connection.createStatement()) {
            st.execute("SET LOCAL lock_timeout = '2s'");
        }

        try (PreparedStatement ps = connection.prepareStatement("""
                UPDATE lesson_lockchain.inventory
                SET quantity = quantity + 1
                WHERE item_id = ?
                """)) {
            ps.setInt(1, 1);
            ps.executeUpdate();
        }

        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Assumes an existing `DataSource`, imports, and method handling `SQLException`. The example highlights **transaction boundaries**:

1. Begin transaction.
2. Set `lock_timeout` locally inside the transaction.
3. Execute SQL.
4. Commit on valid completion.
5. Roll back on error, because a lock timeout inside a transaction puts it into an aborted state.

### SQLSTATE

In PostgreSQL, `lock_timeout`/`NOWAIT` throws lock-related errors such as **`55P03`**; deadlocks throw **`40P01`**; and sending more SQL inside an aborted transaction after an error throws **`25P02`**.

Never write exception handlers matching `"could not obtain lock"` text; rely on `SQLException.getSQLState()`, metadata, and driver semantics.

## 38. JDBC/Spring: Keep Transactions Short

An anti-pattern:

```java
@Transactional
public void updateInventoryAndNotify(long itemId) {
    repository.updateInventory(itemId);   // Holds row lock.
    remoteHttpClient.callSlowService();    // Waits on slow network.
    repository.writeAudit(itemId);
}
```

This is architectural pseudo-code assuming existing components. The row lock from `updateInventory` stays held until the transaction ends. If the HTTP call takes 30 seconds, competing transactions updating that row block for the entire 30 seconds.

### Better Design

Depending on business atomicity needs:

- Move remote I/O **outside** the transaction whenever shared locking is unnecessary.
- Use a **transactional outbox** when reliable post-commit messaging is required.
- Minimize SQL count and elapsed time between `BEGIN` and `COMMIT`.
- Use consistent update ordering when locking multiple rows.
- Use `SELECT FOR UPDATE` only when locking is genuinely needed.
- Consider optimistic locking where appropriate.

**Never send emails or call APIs before commit assuming a database rollback undoes external effects.** If a transaction retries due to a deadlock, side effects must be idempotent.

## 39. Reducing Deadlocks with Consistent Lock Ordering

Suppose two transactions must update item 1 and item 2.

**Inconsistent order:**

```text
T_A: lock item 1 → wait for item 2
T_B: lock item 2 → wait for item 1
      = deadlock
```

**Consistent order:**

```text
T_A: lock item 1 → lock item 2
T_B: lock item 1 → lock item 2
      = may wait, but avoids this cycle
```

Example:

```sql
BEGIN;

SELECT item_id
FROM lesson_lockchain.inventory
WHERE item_id IN (1, 2)
ORDER BY item_id
FOR UPDATE;

-- Apply updates per business rules.

ROLLBACK;
```

`ORDER BY` with row locking must be evaluated under actual query semantics when joins or complex plans exist; the overarching rule is that **all code paths acquire locks in the same order** across contended entities.

### Does Not Guarantee Zero Deadlocks Everywhere

Deadlocks can still arise from FKs, indexes, DDL, mixed lock types, or SQL hidden inside triggers. Consistent lock ordering eliminates one major class of deadlocks—it is not proof that zero deadlocks can occur.

## 40. SELECT FOR UPDATE NOWAIT and SKIP LOCKED

When waiting is unacceptable:

```sql
BEGIN;

SELECT item_id, quantity
FROM lesson_lockchain.inventory
WHERE item_id = 1
FOR UPDATE NOWAIT;

ROLLBACK;
```

If the lock cannot be acquired immediately, the statement fails fast. In an explicit transaction, handle rollback after the error.

For a worker queue:

```sql
BEGIN;

SELECT item_id
FROM lesson_lockchain.inventory
ORDER BY item_id
FOR UPDATE SKIP LOCKED
LIMIT 2;

ROLLBACK;
```

`SKIP LOCKED` skips currently locked rows so a worker can process others. However, it yields an **incomplete** view, unsuitable for reports needing all rows or workflows that must not skip a mandatory entity.

### SKIP LOCKED Does Not Eliminate All Locks

Relation-level locks are still required, and `SKIP LOCKED` does not make every SQL step non-blocking. It applies to row-locking syntax semantics, not as a server-wide setting.

## 41. Batched DELETE/UPDATE and Lock Contention

A single transaction deleting millions of rows holds many locks for a long time, generates huge WAL, and stalls concurrent writers.

A common alternative:

1. Keep work units small.
2. Process in deterministic batches.
3. Commit between batches **when business semantics allow**.
4. Use keys/idempotency for safe retries.
5. Monitor lock waits and affected row counts.

Instead of one giant transaction:

```text
Batch 1: 1000 rows → COMMIT
Batch 2: 1000 rows → COMMIT
Batch 3: 1000 rows → COMMIT
```

The trade-off is that data sits in a **partially completed** state between batches. This is a business trade-off, not an unconditional optimization.

### Indexes Also Affect Lock Duration

An `UPDATE` scanning without a proper index takes longer to locate rows, keeping the transaction open longer. Good indexes shrink scan time; however, indexes alone do not solve contention when **multiple transactions hammer the exact same hot row**.

## 42. Observing and Recording Lock Wait History

A `SELECT` on `pg_locks` shows only **near-current state**. If a 100 ms lock wait disappears, manual snapshots every 10 seconds will miss it.

Combine:

- **`pg_stat_activity`:** state/PID/active query.
- **`pg_blocking_pids`:** current blockers.
- **`pg_locks`:** lock request types and wait start times.
- **`log_lock_waits`:** logs waits exceeding the threshold.
- **Application tracing:** transaction/request boundaries, SQLSTATE, duration.
- **Metrics:** lock-waiting session count, lock wait duration, transaction age, pool wait time.
- **`pg_stat_statements`** when configured: aggregate query timing and frequency; does not directly show live blocking chains.

### Avoid Retaining Unbounded Query Text

Queries may contain customer data or tokens if literals are sent. Dashboards need access controls, redaction, and sane retention windows.

### Meaningful Alert Signals

Instead of alerting only on "query > 5 seconds," alert when:

- `wait_event_type='Lock'` exceeds SLA thresholds.
- One PID blocks many backends simultaneously.
- An `idle in transaction` session persists too long while actively blocking others.
- Lock waits spike after a deploy or migration.
- Multiple `40P01`/`55P03` errors occur.

Exact thresholds depend on workload and SLOs; no single number fits every database.

## 43. Differences Between Locks and MVCC Snapshots

A key connection: **MVCC visibility does not mean writers never wait on each other**.

```text
Plain SELECT
  → reads version visible to its snapshot
  → usually does not wait on row UPDATE just because writer hasn't COMMITted

UPDATE/DELETE/SELECT FOR UPDATE
  → wants to modify/lock a row
  → may have to wait for another transaction

ALTER TABLE
  → needs strong relation lock
  → can block even plain SELECT
```

### Example: Plain SELECT Still Returns Old Data

Session A:

```sql
BEGIN;

UPDATE lesson_lockchain.inventory
SET quantity = 77
WHERE item_id = 1;

-- Not committed yet.
```

Session B:

```sql
SELECT quantity
FROM lesson_lockchain.inventory
WHERE item_id = 1;
-- Sees the previously committed version.
```

B's plain `SELECT` runs immediately reading the visible tuple version, whereas if B tries `UPDATE` on the same row it must wait for A. Conversely, an `ALTER TABLE` holding or queued for a strong relation lock blocks even plain `SELECT`s at the table level.

Never use `pg_blocking_pids` to explain why `SELECT` sees older data: that is **snapshot isolation**, not a lock wait.

## 44. Unusual Symptoms and How to Distinguish Them

| Symptom | Likely cause | Diagnostic tool |
|---|---|---|
| `UPDATE` waiting, `wait_event='transactionid'` | Row conflict / unique / FK or waiting on another transaction. | `pg_blocking_pids` + `pg_locks` + both SQLs. |
| Plain `SELECT` blocked by `ALTER TABLE` | `AccessExclusiveLock` or lock queue. | `pg_locks` relation modes, `pg_blocking_pids`. |
| Blocker is `idle in transaction` | Uncommitted DML or locking `SELECT`. | `pg_stat_activity.xact_start/state` + blockers. |
| Blocker is `idle` yet holds advisory lock | Session-level advisory lock. | `pg_locks.locktype='advisory'`. |
| Blocker PID = 0 | Likely a prepared transaction. | `pg_prepared_xacts` and 2PC procedure. |
| Wait event is not `Lock` | I/O / LWLock / Client / other wait. | `pg_stat_activity.wait_event_type`, targeted diagnostics. |
| Blocker gone on re-query | Lock released or graph shifted. | Sampling / `log_lock_waits`. |
| Fast queries occasionally time out | Burst lock waits or other contention. | Logs, sampling, tracing. |
| Deadlock `40P01` | Lock wait cycle detected by PostgreSQL. | Server logs, SQLSTATE, lock ordering. |
| Transaction fails `25P02` after `lock_timeout` | Earlier statement failed; transaction not rolled back. | First SQLSTATE error and transaction lifecycle. |
| Reading stale data without waiting | MVCC snapshot / replica lag / cache. | Isolation, WAL replay, app cache. |

## 45. Real-World Lock Chain Incident Runbook

Suppose the inventory API suddenly spikes in latency.

### Step 1 — Confirm Whether Lock Waits Exist

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY query_start;
```

### Step 2 — Extract Direct Blocking Edges

```sql
SELECT
    a.pid AS blocked_pid,
    b.blocker_pid
FROM pg_catalog.pg_stat_activity AS a
CROSS JOIN LATERAL unnest(
    pg_catalog.pg_blocking_pids(a.pid)
) AS b(blocker_pid)
WHERE a.datname = current_database();
```

### Step 3 — Check If Blockers Are Also Waiting

If blocker B also appears in `blocked_pid`, it is a **middle hop in the chain**. Run the recursive CTE to trace upstream.

### Step 4 — Inspect Lock Types

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    waitstart,
    relation,
    transactionid
FROM pg_catalog.pg_locks
WHERE NOT granted
ORDER BY waitstart NULLS LAST;
```

### Step 5 — Identify Owner and Duration

Check `usename`, `application_name`, `backend_start`, `xact_start`, `state_change`, and logs/tracing. Distinguish the **waiting** SQL from the **earlier SQL that acquired the lock**.

### Step 6 — Assess Impact

Count how many requests are blocked directly/indirectly, wait durations, API SLOs, and whether the lock involves DDL or a prepared transaction.

### Step 7 — Release Safely

Prefer letting the owner commit/roll back whenever possible. Consider cancel/terminate only after verifying PID and impact. If `blocker=0`, follow prepared-transaction recovery—never kill PID 0.

### Step 8 — Find the Code Root Cause

Common bugs:

- Transaction kept open across HTTP API calls.
- Exception caught without rolling back.
- Read endpoint unnecessarily holding a long transaction/lock.
- DDL deployed during peak traffic.
- Oversized batch updates.
- Code paths acquiring row locks in different orders.
- Unreleased advisory locks.
- Connection pool exhaustion or backends held too long.

### Step 9 — Prevent Recurrence

Set sensible timeouts, shrink transaction scope, clarify ownership, add metrics/alerts, implement deadlock retries, and schedule migrations safely.

## 46. Common Misconceptions

**"A backend with `state='active'` is burning CPU."** No. An active backend can be waiting on `Lock`, `IO`, or other wait events.

**"A blocker must also have `wait_event_type='Lock'`."** No. A blocker can be `idle in transaction` or `idle` while holding an advisory lock.

**"`pg_locks.granted=false` is a blocker."** No. That is a **waiting lock request**. The blocker is in another row or ahead in the queue.

**"Every row lock shows `locktype='tuple'`."** No. Row-update waits normally appear via `transactionid`.

**"Same relation OID means two locks conflict."** No. You must check database, mode, and the lock queue.

**"Every waiter has exactly one blocker."** No. `pg_blocking_pids` returns an **array**; there can be multiple PIDs and branches.

**"`pg_blocking_pids` only returns sessions holding granted locks."** No. It also includes soft blockers ahead in the queue.

**"The root blocker is always the longest-running query."** No. The root can be `idle in transaction`, `idle` holding an advisory lock, or a prepared transaction.

**"PID 0 is a backend to terminate."** No. PID 0 represents a prepared transaction blocker.

**"`pg_cancel_backend` definitely releases locks from an idle transaction."** No. Canceling a statement does not close an open transaction.

**"`pg_terminate_backend` only stops SELECTs without affecting data."** No. Uncommitted work rolls back and affects applications.

**"Remove a lock by deleting from `pg_locks`."** No. `pg_locks` is a read-only diagnostic view, not a mutable table.

**"Lock wait time can be measured accurately from `query_start`."** No. A statement may do work before waiting; prefer `waitstart` when available.

**"`pg_locks` is a strictly atomic snapshot of every lock."** No. Lock states change rapidly and the view reads across lock manager partitions.

**"No blocker found on a second check means the first check was wrong."** No. The transaction may have just committed/rolled back and ended the wait.

**"Seeing `SELECT 1` in `blocker.query` means `SELECT 1` took the row lock."** No. For an idle blocker, `query` is merely the most recent statement, not the lock-acquiring statement.

**"Advisory locks are always released on transaction commit."** No. Session-level advisory locks survive commit/rollback; only transaction-level ones release at transaction end.

**"Raising `lock_timeout` eliminates contention."** No. Timeouts change failure/waiting behavior, not the underlying hot resource.

**"A deadlock is just an unusually slow query."** No. A deadlock is a wait cycle that PostgreSQL detects and breaks by aborting a victim.

**"`SKIP LOCKED` guarantees no SQL statement ever waits."** No. It applies to the row-locking clause scope and other lock types still apply.

**"Every blocker should be killed."** No. Many blockers are valid transactions best left to finish or fixed via code/transaction scope.

## 47. Standard Monitoring Dashboard Checklist

A dashboard or runbook should display:

| Field / metric | Why it matters |
|---|---|
| Waiting PID and `backend_start` | Accurately identify the backend; avoid PID-reuse mistakes. |
| Waiting user, database, `application_name` | Identify affected services. |
| Waiting query and `query_age` | See which statement is waiting and total elapsed time. |
| `wait_event_type`, `wait_event` | Distinguish heavyweight `Lock` from `IO`/`LWLock`/`Client`. |
| `pg_locks.locktype`/`mode`/`granted`/`waitstart` | Inspect lock request types and actual wait start times. |
| Direct blocker PIDs | Edges of the wait-for graph. |
| Blocking chain/path | Locate upstream/terminal blockers. |
| Blocking state/`xact_age` | Spot long `idle in transaction` blockers. |
| Direct/indirect waiter count | Prioritize remediation by blast radius. |
| PID 0 / `prepared_xacts` | Avoid mishandling prepared transactions. |
| Lock timeout / deadlock rates | Track contention trends. |
| Event logs and trace IDs | Trace the exact SQL that took the lock and code path. |

Never build auto-termination off a **single sample**. The graph shifts rapidly; re-verify and require clear policy/authorization.

## 48. Practice Exercises

### Exercise 1 — Observing wait_event

Create two sessions: A runs `BEGIN; UPDATE item_id=1` and stays open; B runs `UPDATE` on the same row. Session M queries `pg_stat_activity`. Record B's `state`, `wait_event_type`, and `wait_event`. How do A and B differ?

### Exercise 2 — Finding the Direct Blocker

In Exercise 1's scenario, use `pg_blocking_pids(B_PID)` to find A's PID. Explain why the function returns an array instead of a single integer.

### Exercise 3 — Unnesting Blocking PIDs

Write a query on `pg_stat_activity` using `CROSS JOIN LATERAL unnest(pg_blocking_pids(pid))` to emit one row per `waiting_pid → blocking_pid` edge.

### Exercise 4 — Reading granted and waitstart

Find `pg_locks` rows with `granted=false`. Compare `clock_timestamp()-waitstart` with the waiter's `clock_timestamp()-query_start`. Why can the two durations differ?

### Exercise 5 — Row Locks Not Showing as tuple

In the lab, observe same-row `UPDATE` contention. Locate the waiter's `locktype='transactionid'` and `mode='ShareLock'` when present. Why does seeing no `granted=true` `tuple` row fail to prove there is no row-level lock?

### Exercise 6 — Relation Lock Modes

Explain why `AccessShareLock` from `SELECT` can block `AccessExclusiveLock` from `ALTER TABLE`, yet two `SELECT`s do not conflict on the same table.

### Exercise 7 — DDL Queue

A holds a transaction open after `SELECT`, B runs `ALTER TABLE` and waits, and C arrives later with a `SELECT`. Observe `pg_blocking_pids` for C. Explain the role of the soft blocker.

### Exercise 8 — Building a Three-Level Chain

A locks item 1; B locks item 2 then waits on item 1; C waits on item 2. Use the direct-edge query to draw `C → B → A` and release all three transactions in safe order.

### Exercise 9 — Recursive CTE

Use a recursive CTE over `edges(waiting_pid,blocker_pid)` to build `pid_chain`. Why are a depth cap and cycle guard needed?

### Exercise 10 — Multiple Blocking Branches

Suppose W is directly blocked by both B1 and B2, and B1 waits on A. Draw the graph and explain why W should not be forced into a single root blocker.

### Exercise 11 — Counting Impact

Write a query counting `COUNT(DISTINCT waiting_pid)` per blocker PID. Distinguish direct waiter count from total unique origin waiters across all hops.

### Exercise 12 — Inspecting an idle in transaction Blocker

Run an `UPDATE` in transaction A followed by `SELECT 1`, then leave A idle. B waits on A's row lock. Why does A's `pg_stat_activity.query` show `SELECT 1` while the actual lock came from the earlier `UPDATE`?

### Exercise 13 — Advisory Locks

A calls `pg_advisory_lock(12345)`; B attempts the same key. Use `pg_locks` and `pg_blocking_pids` to locate the blocker. Release with `pg_advisory_unlock` in A. Compare with `pg_advisory_xact_lock`.

### Exercise 14 — Prepared Transactions

Without creating a real prepared transaction, explain why a PID 0 blocker cannot be handled with terminate, and which view inspects prepared transactions.

### Exercise 15 — Deadlock

Two sessions lock item 1 and item 2 in opposite orders. Observe `40P01` and explain why the victim transaction must roll back before retrying.

### Exercise 16 — lock_timeout

In a lab transaction, set `SET LOCAL lock_timeout = '1s'` and run `UPDATE` on a locked row. Record the first SQLSTATE; then explain why a subsequent `SELECT` returns `25P02` unless rolled back first.

### Exercise 17 — statement_timeout vs. lock_timeout

Give two scenarios: a query slow due to CPU/I/O without waiting on locks, and a query slow due to lock blocking. Which timeout measures each? Why shouldn't `query_age` be equated with `lock_wait_age`?

### Exercise 18 — pg_cancel_backend

A blocker is `idle in transaction` with no active statement. Why does `pg_cancel_backend` fail to release its locks? When is owner rollback or procedural termination needed?

### Exercise 19 — Verifying PID Before Terminating

List fields to verify before signaling a PID: `pid`, `backend_start`, `usename`, `application_name`, `state`, and business target. Why is a PID from an old log unsafe?

### Exercise 20 — Application Logs and Blocker Query

An `idle in transaction` blocker shows `SELECT 1`. Describe how request tracing finds the earlier `UPDATE` that took the lock without guessing from query text.

### Exercise 21 — pg_locks Across Databases

Why can't you join `pg_locks.relation` to the current database's `pg_class.oid` while ignoring `pg_locks.database`? Write the query with the proper database OID filter.

### Exercise 22 — Distinguishing Wait Types

One slow session has `wait_event_type='IO'`, another has `Lock`. When is `pg_blocking_pids` useful? Why shouldn't every wait be called a lock wait?

### Exercise 23 — Connection Pool

A Spring `@Transactional` endpoint updates inventory and then waits 30 seconds on an HTTP API. Explain how a chain forms and propose changes to shorten the transaction.

### Exercise 24 — Alerting by Waiter Count

Design an alert when one blocker directly blocks 10 or more requests for over 5 seconds. Which fields do you pull from `pg_blocking_pids`, `pg_stat_activity`, and `pg_locks`? Why sample multiple times?

### Exercise 25 — Root Blocker Is Not Root Cause

The graph shows C → B → A; A has no blocker, yet is waiting for the client to send `COMMIT`. Distinguish the **head of the lock chain** from the **application root cause**.

### Exercise 26 — Lock Ordering

Two transactions both need to update item 1 and item 2. Describe the inconsistent order that deadlocks, then design a consistent lock order to reduce risk. Which deadlocks can still occur?

### Exercise 27 — SKIP LOCKED

With two workers pulling jobs via `FOR UPDATE SKIP LOCKED`, explain why row contention drops and why the output is unsuitable for a report needing all jobs.

### Exercise 28 — Complete Runbook

Write an 8–10 step runbook for handling lock-induced API timeouts: identifying wait events, finding direct blockers, tracing the chain, classifying locktype/mode, verifying owner/transaction age, assessing impact, releasing safely, rolling back/retrying, and preventing recurrence.

## Conclusion

**`pg_blocking_pids()` and `pg_locks` answer two different, complementary questions.** `pg_blocking_pids(pid)` answers **"which backends are blocking this backend?"** under lock-manager semantics, including hard blockers and queued soft blockers. `pg_locks` answers **"which lock requests exist, of what type, which modes are granted, and which are waiting?"**. Combined with `pg_stat_activity`, you have the core visibility needed to inspect active lock contention.

To understand **blocking chains**, build `waiter → blocker` edges and walk upstream across hops with a recursive CTE instead of stopping at the first waiter. A single backend can be both a **waiter** and a **blocker**; a waiter can have multiple blockers; and the endpoint of the observed graph is not always the business root cause. Cases like **row locks surfacing as `transactionid`**, **queued soft blockers**, **advisory locks**, and **prepared transactions with PID 0** require careful handling rather than guessing from a naive `pg_locks` self-join.

In operations, **prioritize verifying and resolving the transaction owner** before canceling or terminating backends. Inspect `xact_start`, `waitstart`, and application state; remember an `idle in transaction` blocker often displays only its latest statement rather than the statement that took the lock. Combine timeouts, lock-wait logging, short transactions, consistent lock ordering, and bounded deadlock retries. Done right, blocking-chain detection does more than just "unblock one stuck query"—it fixes transaction design to reduce contention and safeguard correctness across your PostgreSQL system.
