# Lock Ordering and Deadlock Formation in PostgreSQL

## 1. Why Can Two Valid Transactions Lock Each Other Forever?

In transactional systems, a single request often needs to modify **multiple rows**: debiting a source account and crediting a destination account, reserving multiple resources, updating an order and inventory, or modifying multiple records in a batch.

Suppose there are two accounts A and B:

- **Transaction T1:** transfers money from A to B; modifies A first, then B.
- **Transaction T2:** transfers money from B to A; modifies B first, then A.

If both transactions run concurrently:

```text
T1 locks A                      T2 locks B
    |                               |
T1 needs lock B                 T2 needs lock A
    |                               |
    +--- waits for T2    waits for T1 ---+
                  \       /
                  WAIT CYCLE
```

T1 does not release A because it has not finished. T2 does not release B because it has not finished. Each needs a resource held by the other. This is a **deadlock**.

PostgreSQL does not wait forever when it detects such a wait cycle: it chooses one transaction to abort, raises an error typically with SQLSTATE **`40P01`** (*deadlock_detected*), and lets the other transaction proceed.

Key insight: **the exact same business outcome can be achieved without deadlocking** if transactions acquire locks in the **same deterministic order**.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **lock wait**, **lock contention**, and **deadlock**.
2. Explain common PostgreSQL lock types at row and table levels.
3. Construct a **wait-for graph** with a dependency cycle.
4. Reproduce a deadlock using two independent PostgreSQL sessions and read SQLSTATE `40P01`.
5. Understand how PostgreSQL handles a deadlocked transaction.
6. Design **consistent lock-ordering** rules for transfers, reservations, and multi-table updates.
7. Know when `SELECT ... FOR UPDATE` is needed and why isolated locks are insufficient.
8. Identify deadlocks caused by **lock upgrades**, foreign keys, triggers, DDL, and advisory locks.
9. Use `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids()` to diagnose waiting sessions.
10. Distinguish `deadlock_timeout`, `lock_timeout`, and `statement_timeout`.
11. Retry the **entire transaction** after `40P01` while avoiding duplicate external side effects.
12. Design barrier-based concurrency tests and operational practices to reduce contention.

## 2. Locks in PostgreSQL: Purpose and Lifecycle

PostgreSQL uses **MVCC** to allow concurrent read queries without forcing every plain `SELECT` to wait for every `UPDATE`. However, potentially conflicting operations still require locking.

For example:

- Two `UPDATE`s modifying the same row must coordinate rather than blindly overwriting each other's version.
- `DELETE` can conflict with a transaction holding a row lock.
- `SELECT ... FOR UPDATE` requests row locks to protect subsequent steps.
- Some DDL commands need stronger table locks than regular DML.
- Foreign keys, unique constraints, and triggers can introduce additional lock requirements.

### 2.1. Row Locks and Table Locks Are Not the Same

PostgreSQL has multiple lock categories, of which two are central to this lesson:

**Row-level locks**: associated with specific rows, such as during `UPDATE` or `SELECT FOR UPDATE`.

**Table-level locks**: associated with the entire relation, with modes such as `ACCESS SHARE`, `ROW SHARE`, `ROW EXCLUSIVE`, `SHARE`, and `ACCESS EXCLUSIVE`.

An `UPDATE` acquires a table-level `ROW EXCLUSIVE` lock to coordinate DML/DDL, **while also** locking the modified rows. Two `UPDATE`s on **different rows** of the same table do not conflict simply because both hold `ROW EXCLUSIVE` table locks: that mode is compatible with itself. Deadlocks in transfer examples arise mainly from **row locks**, not because the table-lock mode name includes the word "EXCLUSIVE."

### 2.2. Row-Lock Modes with SELECT

PostgreSQL provides:

| Syntax | General meaning |
|---|---|
| `FOR UPDATE` | Strong row lock for operations that may modify/delete or need exclusivity |
| `FOR NO KEY UPDATE` | Row lock for updates not changing keys relevant to FKs |
| `FOR SHARE` | Shared lock preventing conflicting updates/deletes |
| `FOR KEY SHARE` | Lighter lock protecting key values from conflicting changes/deletion |

Each mode has its **own conflict matrix**. Do not guess based solely on "SHARE/UPDATE" in the name; consult the PostgreSQL documentation when deciding lock modes.

An `UPDATE` uses row-level locking equivalent to `FOR NO KEY UPDATE` or `FOR UPDATE` depending on which key columns change. `DELETE` uses a strong lock. These locks cause waits when the row is already locked by another transaction in an incompatible mode.

### 2.3. How Long Are Locks Held?

Row locks acquired by a transaction are normally held until the **transaction ends** via `COMMIT` or `ROLLBACK`. With savepoints/subtransactions, locks acquired after a savepoint are released when rolling back to that savepoint per PostgreSQL rules.

Therefore:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- If the transaction stays open long, locks on modified rows remain held.

COMMIT;
```

An `UPDATE` statement finishing does not mean its locks are released while the transaction remains open.

**Operational principle:** keep transactions short; never hold a transaction open while waiting on user input, calling slow HTTP APIs, or doing unnecessary work.

## 3. Wait, Contention, and Deadlock: Three Different Phenomena

### 3.1. Normal Lock Wait

```text
T1 holds lock A
T2 needs A, must wait
T1 COMMITs
T2 proceeds
```

This is a normal **lock wait**. There is no wait cycle.

### 3.2. Lock Contention

Many transactions frequently compete for the same row or resource, such as a global counter. They may queue for a long time without ever creating a deadlock.

```text
T1 holds A
T2 waits for A
T3 waits for A
T4 waits for A
...
```

This is a performance/latency problem; it does not automatically imply a deadlock.

### 3.3. Deadlock

```text
T1 holds A -> waits for B held by T2
T2 holds B -> waits for A held by T1
```

There is a **cycle in the wait-for relationship**, so neither transaction can make progress by waiting for the other.

### 3.4. Why Distinguish Them?

| Phenomenon | Wait cycle? | Typical symptom |
|---|---|---|
| Lock wait | Not required | Ends when holder releases lock; or timeout/cancel |
| Contention | Not required | High latency, reduced throughput |
| Deadlock | Yes | PostgreSQL detects and aborts one transaction |
| Serialization failure | Not necessarily a lock wait cycle | Transaction rejected because schedule is not serializable |

Error `40P01` is a deadlock. Error `40001` is a serialization failure; both may be retried at the transaction level, yet their **root causes differ**.

## 4. Conditions for a Deadlock

A classic model describes deadlock through four conditions:

1. **Mutual exclusion:** a resource/lock cannot be held concurrently by requests with conflicting modes.
2. **Hold and wait:** a transaction holds locks it already acquired while waiting for another lock.
3. **No arbitrary preemption:** PostgreSQL cannot simply strip a lock from a live transaction and hand it to another while preserving semantics; a transaction must end/abort to release its locks.
4. **Circular wait:** a cycle of transactions waiting on one another exists.

In SQL applications, the easiest condition to break is **circular wait** via a **consistent lock acquisition order**, alongside shortening lock hold times and retrying when conflicts still happen.

## 5. Setting Up the Lab Database

Run only in a practice database. The following examples alter balances and intentionally trigger deadlocks; **never run on real financial data**.

### 5.1. Creating the Schema and Accounts Table

```sql
CREATE SCHEMA IF NOT EXISTS deadlock240;

CREATE TABLE deadlock240.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance bigint NOT NULL CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Initial data:

```sql
INSERT INTO deadlock240.accounts(account_id, owner_name, balance)
VALUES
    (10, 'Account A', 1000),
    (20, 'Account B', 1000);
```

Verify:

```sql
SELECT account_id, owner_name, balance
FROM deadlock240.accounts
ORDER BY account_id;
```

| account_id | owner_name | balance |
|---:|---|---:|
| 10 | Account A | 1000 |
| 20 | Account B | 1000 |

To focus on locking, `balance` is an integer representing **the smallest currency unit**. Real monetary systems need currency modeling, precision, transaction states, audits, and business constraints; do not treat two example `UPDATE`s as a full production transfer system.

### 5.2. Two Independent Sessions

Open two `psql` windows or two independent SQL connections to the same database:

- **Session A:** transaction T1, transfers 100 from account 10 to 20.
- **Session B:** transaction T2, transfers 50 from account 20 to 10.

You can label the sessions for observation:

**Session A:**

```sql
SET application_name = 'deadlock240_A';
SELECT pg_backend_pid() AS pid_a;
```

**Session B:**

```sql
SET application_name = 'deadlock240_B';
SELECT pg_backend_pid() AS pid_b;
```

Note the PIDs if you want to cross-check against `pg_stat_activity`/`pg_locks`.

### 5.3. Safety Rules While Practicing

- The two sessions must truly be **two separate connections**; a single connection cannot run two independent concurrent transactions this way.
- Do not run a script executing all commands at once from the start, because **manual interleaving** is required.
- After hitting a deadlock, one session will be in an aborted transaction state; run `ROLLBACK` before continuing.
- Reset data only after both test transactions have finished.
- Never kill PostgreSQL OS processes to simulate this; the server has built-in deadlock detection.

## 6. Correct Sequential Transfers

A transaction transferring 100 from A to B:

```sql
BEGIN;

UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100;

UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20;

COMMIT;
```

Starting from the initial state, balances become:

```text
A (10) = 900
B (20) = 1100
Total A+B = 2000
```

A reverse transfer of 50 from B to A running **afterward**:

```sql
BEGIN;

UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50;

UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10;

COMMIT;
```

Final result:

```text
A (10) = 950
B (20) = 1050
Total A+B = 2000
```

Both transactions are valid when run sequentially. **Differing update orders** only become a problem when they overlap in time and hold locks concurrently.

In production, always check the affected row count after debiting; if 0 rows (insufficient funds or missing account), roll back the transaction instead of continuing to credit the target account.

## 7. Deadlock Experiment: T1 Locks A First, T2 Locks B First

This is the core walkthrough. Start with each account at 1000 and neither session in an open transaction.

### Step 1 — Session A Opens Transaction, Locks A

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100
RETURNING account_id, balance;
```

Expected output: one row for account 10 with balance=900.

**Do not COMMIT.** Session A keeps the update lock on account 10.

### Step 2 — Session B Opens Transaction, Locks B

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50
RETURNING account_id, balance;
```

Output: one row for account 20 with balance=950 inside transaction B.

**Do not COMMIT.** B holds the lock on account 20.

Current state:

| Transaction | Held row lock |
|---|---|
| A | account 10 |
| B | account 20 |

No deadlock yet because neither is waiting for the other.

### Step 3 — Session A Tries to Lock B and Blocks

**Session A:**

```sql
UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20
RETURNING account_id, balance;
```

This statement **does not return immediately** because row 20 is locked by Session B's uncommitted `UPDATE`.

Now:

```text
A holds account 10
A waits for account 20 (held by B)
B holds account 20
```

So far this is only a **lock wait**, not yet a deadlock.

**Operational note:** terminal A is blocked on its `UPDATE`. Switch to **terminal B** to perform Step 4.

### Step 4 — Session B Tries to Lock A, Creating a Cycle

**Session B:**

```sql
UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10
RETURNING account_id, balance;
```

Row 10 is locked by A. B must wait for A, while A is waiting for B.

```text
A holds account 10  ---- needs account 20 ----> B
^                                               |
|                                               |
+---- needs account 10 ---- B holds account 20 -+
```

The wait cycle is now complete.

### Step 5 — PostgreSQL Detects and Breaks the Deadlock

After waiting through the check interval, PostgreSQL reports in **one** of the sessions:

```text
ERROR: deadlock detected
DETAIL: Process ... waits for ShareLock on transaction ...
SQLSTATE: 40P01
```

Exact lock names/DETAIL and PIDs vary by environment. This is a sample message, not live output from your run.

**There is no guarantee whether A or B will be chosen as the victim.** PostgreSQL selects one transaction to abort to break the cycle. The errored transaction did not commit.

The surviving session can proceed once locks are released by the victim transaction's rollback.

### Step 6 — Cleanly Ending Both Transactions

If Session B received the error, run in B:

```sql
ROLLBACK;
```

Then A completes its waiting `UPDATE`, and afterward:

```sql
COMMIT;
```

If A received the error, **swap roles**: A runs `ROLLBACK`, and B completes its `UPDATE` and runs `COMMIT`.

In `psql`, after an error inside a transaction, the prompt indicates an aborted transaction state and subsequent statements return:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

You must run `ROLLBACK` (or roll back to an appropriate savepoint if one was set) before starting another transaction.

### Step 7 — Inspecting Data After Both Finish

```sql
SELECT account_id, balance
FROM deadlock240.accounts
ORDER BY account_id;

SELECT SUM(balance) AS total_balance
FROM deadlock240.accounts;
```

If only A committed, the result is A=900, B=1100. If only B committed, the result is A=1050, B=950. **The total remains 2000** for valid transactions.

Do not expect both transfers to have completed; the transaction that hit `40P01` must be **retried from the beginning** by the application if the business operation still needs to execute.

## 8. Wait-for Graph: Modeling Deadlocks

A **wait-for graph** represents:

- Each node as a transaction.
- Each edge `T1 → T2` meaning **T1 is waiting for a lock held by T2** in a conflicting mode.

At Step 3:

```text
T1 ---- waits for ----> T2

T2 is not waiting for T1
=> No cycle, just a lock wait.
```

At Step 4:

```text
         waits
    T1 ---------> T2
     ^             |
     |             |
     +-------------+
         waits

=> Cycle T1 -> T2 -> T1 exists.
=> Deadlock.
```

This mental model applies across row locks, table locks, and advisory locks whenever transactions wait on shared resources.

### 8.1. Resource Tracking Table

| Point in time | T1 holds | T1 waits for | T2 holds | T2 waits for | Conclusion |
|---|---|---|---|---|---|
| After Step 1 | A | — | — | — | No wait |
| After Step 2 | A | — | B | — | No wait |
| After Step 3 | A | B | B | — | One-way wait |
| After Step 4 | A | B | B | A | Deadlock |
| After aborting victim | Depends on victim | Released | Depends on victim | Released | Cycle broken |

### 8.2. What Causes Inconsistent Lock Ordering?

T1 requests resources in order:

```text
A -> B
```

T2 requests:

```text
B -> A
```

Opposite ordering enables a wait cycle. If every transaction acquires:

```text
A -> B
```

then the later transaction may **wait right at A**, and can never hold B while waiting for A under the same protocol.

This is the foundation of the **total order** rule in locking design.

## 9. Primary Solution: Acquire Locks in a Fixed Order

When a transaction touches multiple accounts, enforce:

> For every transfer, **lock the smaller `account_id` first and the larger `account_id` second**, regardless of which account is the source and which is the destination.

In the lab:

```text
account_id 10 first
account_id 20 second
```

Both transfer 10 → 20 and transfer 20 → 10 must acquire locks in order **10 → 20**. Balance arithmetic still follows the actual transfer direction; **lock order does not mean cash-flow order**.

### 9.1. T1 Locks 10 Then 20

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 20
FOR UPDATE;
```

A now holds both locks. After verifying sufficient funds, perform DML:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 100, updated_at = now()
WHERE account_id = 10
  AND balance >= 100
RETURNING balance;

UPDATE deadlock240.accounts
SET balance = balance + 100, updated_at = now()
WHERE account_id = 20
RETURNING balance;

COMMIT;
```

In a real application, inspect `RETURNING` or the affected row count of the debit. If 0 rows, `ROLLBACK` and **never execute the credit**.

### 9.2. T2 Also Locks 10 Then 20

**Session B**, even though transferring **from 20 to 10**, still does:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 20
FOR UPDATE;
```

While A holds account 10, B blocks **immediately when trying to lock 10**. Because B has not locked account 20 yet, it holds no resource A needs. No T1↔T2 cycle can form over this pair of accounts.

When A commits, B locks 10 then 20 in turn, reads the updated state, and only then runs:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 50, updated_at = now()
WHERE account_id = 20
  AND balance >= 50
RETURNING balance;

UPDATE deadlock240.accounts
SET balance = balance + 50, updated_at = now()
WHERE account_id = 10
RETURNING balance;

COMMIT;
```

Starting from 1000/1000 with both transfers valid, the final balances are 950/1050.

### 9.3. Why Use Two Separate SELECT FOR UPDATE Statements in the Example?

These two statements illustrate **explicit** lock order independent of transfer direction:

```sql
SELECT ... WHERE account_id = 10 FOR UPDATE;
SELECT ... WHERE account_id = 20 FOR UPDATE;
```

Real applications can use queries locking multi-row sets in order, provided you understand how the planner, joins, `LIMIT`, and locking clauses affect lock timing. For a protocol where you want to **prove lock acquisition order**, acquiring sequentially over a sorted key list is easy to reason about and test.

**Remember:** in the two statements above, do not start the second transfer with account 20 simply because it is the source; every writer must follow the same rule.

## 10. Lock Order Is Not Business Order

Suppose transfer 20 → 10:

- **Lock order:** 10 then 20.
- **Balance update order:** you can debit 20 then credit 10, as long as both rows are already locked and the transaction is atomic.

This distinction prevents a very common mistake:

> "I always lock the source account first because I have to debit the source first."

When two transfers run in opposite directions, "source first" reverses the lock order and invites deadlocks.

A clean rule:

```text
lock_order = sort(unique(all_accounts_in_transaction))
for account in lock_order:
    SELECT account FOR UPDATE

after holding all required locks:
    validate business rules
    apply debits/credits
    COMMIT
```

Taking `unique` also prevents attempting to lock the same account twice if source and destination coincide. Self-transfers should be handled by explicit business rules.

## 11. Be Careful with IN (...), JOIN, and Planner Ordering

You might write:

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;
```

In simple cases, `ORDER BY account_id` defines output order and the plan often locks in sorted order. That is useful in many practical scenarios.

However, note the limitations:

1. `IN (10,20)` **does not dictate** processing 10 before 20.
2. Simply writing `UPDATE ... WHERE id IN (...)` **does not guarantee** rows are updated/locked in the order listed inside `IN`.
3. PostgreSQL has no general `UPDATE ... ORDER BY id` syntax as many developers assume.
4. With `JOIN`s, subqueries, triggers, FKs, or multiple target tables, actual lock order can differ from a naive reading of the SQL.
5. Under `READ COMMITTED`, `SELECT ... ORDER BY ... FOR UPDATE` has caveats when sort columns are updated concurrently while waiting; returned order can deviate from intuition if sorting by mutable columns.

**Recommendation:** use **immutable/stable keys** such as primary keys for lock order. When correctness requires strict ordering across steps, acquire locks **one key at a time in sorted order** or verify the execution plan/protocol rather than assuming multi-row `UPDATE` obeys an imagined `ORDER BY`.

### 11.1. Application Pattern for Locking Multiple Resources

```text
ids = distinct([fromAccountId, toAccountId])
ids = sortAscending(ids)

BEGIN
for id in ids:
    SELECT ... FROM accounts WHERE account_id = id FOR UPDATE

Read/validate data once all locks are held
Execute necessary UPDATEs
COMMIT
```

For very large key counts, issuing individual `SELECT`s increases round trips. Then consider batch-locking designs, actual execution order, contention, and retries—without trading away correctness just to save a few network hops.

## 12. When SELECT FOR UPDATE Is Not Enough

`SELECT ... FOR UPDATE` is a row-locking tool, **not a guarantee that transactions can never deadlock**.

### 12.1. Locking in Opposite Order Still Deadlocks

If A runs:

```sql
SELECT * FROM deadlock240.accounts
WHERE account_id = 10 FOR UPDATE;

SELECT * FROM deadlock240.accounts
WHERE account_id = 20 FOR UPDATE;
```

while B runs 20 then 10, a wait cycle still occurs. Replacing the first `UPDATE` with `SELECT FOR UPDATE` **does not fix wrong lock ordering**.

### 12.2. Row Locks Do Not Protect Rows That Might Be Inserted Later

If a transaction reads a predicate like "all confirmed bookings," other transactions can `INSERT` new matching rows. Locking existing rows with `FOR UPDATE` does not automatically lock "the absence of rows" across all models.

This relates to phantom reads / write skew and may require `SERIALIZABLE`, unique/exclusion constraints, a quota row, or a resource guard lock.

### 12.3. Do Not Lock Unless Needed

Over-broad locking creates heavy contention, hurts throughput, and raises deadlock risk across complex workflows. Lock only the necessary rows/granularity, inside short transactions, in a consistent order.

## 13. Deadlocks from Lock Upgrades on the Same Row

Deadlocks do not happen only with two rows A and B. Two transactions can **both hold a shared lock**, and then each tries to upgrade to a stronger lock.

### 13.1. Experiment with FOR SHARE

Once all previous transactions have ended, keep row account 10 intact.

**Session A:**

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR SHARE;
```

**Session B:**

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR SHARE;
```

Two `FOR SHARE` locks are compatible, so both A and B hold share locks on the same row.

**A** tries to update:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id = 10;
```

A waits for B to release its share lock.

**B** also tries to update the same row:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id = 10;
```

B needs a lock incompatible with A. Both transactions hold share locks and want to upgrade, creating a deadlock.

### 13.2. Solution for Read-Then-Update

If a transaction **knows in advance** it will update a row, acquire the appropriate update lock from the start:

```sql
BEGIN;

SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

-- Check business rules, then UPDATE.

COMMIT;
```

The second transaction waits right at `SELECT FOR UPDATE`, rather than both holding `SHARE` and deadlocking on upgrade.

**You do not always need `FOR UPDATE`.** Pick the lock mode based on the actual operation and concurrency profile; overly strong locks also have costs.

## 14. Multi-Table Deadlocks

Suppose a workflow touches two tables:

```text
orders
inventory
```

One endpoint:

```text
T1:
    lock order
    lock inventory
```

Another job:

```text
T2:
    lock inventory
    lock order
```

Even though each table has clean primary keys, reversing the order across **resource types** still forms a wait cycle.

### 14.1. Defining a Global Order

Example project convention:

```text
1. tenant guard
2. order header
3. inventory rows, ascending SKU
4. order items, ascending item_id
5. audit/outbox rows
```

There is no single universal order for every system; choose one based on your workflows and contention hotspots. What matters is that **every relevant code path** follows the same order.

### 14.2. Account for Triggers and Foreign Keys

Even when application code says:

```text
update orders first
update inventory second
```

a trigger or foreign key can cause PostgreSQL to read/lock rows in other tables. When investigating deadlocks, inspect **all constraints and triggers**, not just the two `UPDATE` statements visible in the service method.

### 14.3. Within-Table Order Still Matters Too

If modifying two orders or multiple SKUs, table-level ordering alone is not enough. Also enforce:

- Ascending order IDs.
- Ascending SKUs within inventory.
- When spanning tenants, tenant ID first then resource ID.
- Deduplicating potentially repeated rows before locking.

Only a **sufficiently detailed global order** eliminates cycles introduced by your own protocol.

## 15. Table-Level Locks Can Also Cause Deadlocks

Do not assume deadlocks happen only on rows.

PostgreSQL has multiple table lock modes:

| Situation | Typical lock mode |
|---|---|
| Plain `SELECT` | `ACCESS SHARE` |
| `SELECT FOR UPDATE/SHARE` | `ROW SHARE` on locked table, in addition to row locks |
| `INSERT` / `UPDATE` / `DELETE` | `ROW EXCLUSIVE` |
| Some index builds / maintenance | Modes such as `SHARE`/`SHARE UPDATE EXCLUSIVE` depending on command |
| Strong DDL such as table structural changes | May require `ACCESS EXCLUSIVE` |

Mode names alone are not enough to infer conflicts; PostgreSQL defines a **conflict matrix** for these modes.

For example, one migration locks table A then B while another locks B then A in conflicting modes. Even without touching any shared business rows, they can deadlock.

### 15.1. Migrations Need Separate Coordination

- Avoid running concurrent migrations that acquire strong locks in opposite table order whenever possible.
- Identify DDL statements that take `ACCESS EXCLUSIVE` or modes conflicting with live workloads.
- Use maintenance windows, reasonable `lock_timeout`, or migration tooling with serialization.
- DDL can queue behind open read/write transactions; an `idle in transaction` session holding old locks makes this harder to spot.

**Rule:** never assume a syntactically simple `ALTER TABLE` avoids heavy locks.

## 16. Deadlock Detection Timing

PostgreSQL has a `deadlock_timeout` setting: once a lock wait lasts long enough, the engine checks whether a deadlock exists.

Check the current setting:

```sql
SHOW deadlock_timeout;
```

In typical setups, the default is **1 second**; actual values may have been customized by an administrator.

### 16.1. Why Not Check for Cycles Immediately on Every Lock Wait?

Deadlock detection has overhead. Most lock waits are brief and resolve as soon as the holder commits. Waiting a short interval before running the detector avoids wasting CPU checking normal, transient waits.

### 16.2. deadlock_timeout Is Not a Query Deadline

This parameter controls **when deadlock detection runs**, not canceling an SQL query simply because it waited longer than that duration **without a deadlock**.

For example, if T1 holds a lock for 30 seconds and T2 waits for it with no cycle, T2 keeps waiting well past `deadlock_timeout`.

### 16.3. Do Not Blindly Lower deadlock_timeout Server-Wide

Setting it too low increases overhead from frequent deadlock checks. In production, tuning parameters and lock logging should reflect workload, permissions, and DBA runbooks.

## 17. lock_timeout, statement_timeout, and NOWAIT

Time-bounding and non-waiting mechanisms serve different purposes:

| Mechanism | Purpose |
|---|---|
| `deadlock_timeout` | Wait time before running deadlock detection |
| `lock_timeout` | Max time to wait to acquire a lock |
| `statement_timeout` | Max total execution time of an SQL statement |
| `NOWAIT` | Locking clause fails immediately if lock is unavailable |
| `SKIP LOCKED` | Locking row selection skips currently locked rows |

### 17.1. Configuring Timeouts in a Lab Transaction

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';

SELECT account_id
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

COMMIT;
```

`SET LOCAL` applies only to the current transaction. If the lock is not acquired within the limit, the statement errors. On an aborted transaction, the application must roll back properly.

### 17.2. NOWAIT

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
```

If the row holds a conflicting lock, the query returns `lock_not_available` with SQLSTATE `55P03` instead of waiting.

This is not a `40P01` deadlock. The application must decide whether to return "busy, retry" or schedule a retry per business rules.

### 17.3. SKIP LOCKED

```sql
SELECT account_id, balance
FROM deadlock240.accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

If one account is locked, the query **skips that account**. That is useful for **job queues**, yet **wrong for silently skipping an account** in a money transfer that requires both source and destination.

`SKIP LOCKED` intentionally gives an incomplete view relative to the full matching rows. Never use it to "fix deadlocks" in a transaction where all resources are mandatory.

## 18. Work Queue: Where SKIP LOCKED Shines

Example job table:

```sql
CREATE TABLE deadlock240.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('READY', 'RUNNING', 'DONE')),
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO deadlock240.jobs(status, payload)
VALUES
    ('READY', 'job-A'),
    ('READY', 'job-B'),
    ('READY', 'job-C');
```

A worker can pick a job not currently locked by another worker:

```sql
WITH picked AS (
    SELECT job_id
    FROM deadlock240.jobs
    WHERE status = 'READY'
    ORDER BY job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE deadlock240.jobs AS j
SET status = 'RUNNING'
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING j.job_id, j.payload, j.status;
```

Independent workers pick distinct jobs instead of piling up behind a locked job.

However:

- You need lease/recovery if a worker dies after claiming a job.
- `SKIP LOCKED` does not guarantee strict fairness; a job can be skipped repeatedly.
- It does not replace task idempotency.
- Deadlocks can still happen if workers later acquire additional locks in opposite orders.
- A work queue needs dedicated retry, state transition, and transaction boundary design.

## 19. Observing Waiting Sessions with pg_stat_activity

Open a **third session** as an observer while A or B is blocked. Inspect:

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

A session waiting on a lock may show:

```text
wait_event_type = Lock
wait_event      = transactionid / tuple / ... (depending on scenario)
blocking_pids   = {PID of blocking session}
```

These are **illustrative** values, not measured output.

### 19.1. Why application_name Helps

If in the lab you set:

```sql
SET application_name = 'deadlock240_A';
```

then in the observer it is easy to tell which transaction belongs to A vs. B instead of anonymous PIDs.

In production, `application_name` should identify the service/workload cleanly, without PII or sensitive data.

### 19.2. idle in transaction

A session may run no SQL at the moment of observation while sitting in:

```text
state = idle in transaction
```

It may still hold locks from prior statements, making other sessions wait. Inspect `xact_start` and transaction age during diagnosis:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Never automatically kill every long transaction without evaluating business impact and operational authority.

## 20. pg_blocking_pids(): Finding Who Is Blocking Whom

`pg_blocking_pids(pid)` returns the list of PIDs blocking the queried backend according to PostgreSQL's lock manager.

Example finding currently blocked sessions:

```sql
SELECT
    a.pid AS waiting_pid,
    a.application_name AS waiting_app,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 120) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
```

Expand with `LATERAL unnest(...)` to display waiter/blocker pairs:

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    b.pid AS blocking_pid,
    b.application_name AS blocking_app,
    w.wait_event,
    left(w.query, 100) AS waiting_sql,
    left(b.query, 100) AS blocker_last_sql
FROM pg_stat_activity AS w
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(w.pid)
) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
    ON b.pid = p.blocking_pid
WHERE w.datname = current_database()
ORDER BY w.pid, b.pid;
```

Remember that `query` on a holding session is its **most recent SQL statement**, not necessarily the exact first statement that acquired the lock; a transaction may take a lock in an earlier statement and then sit idle.

### 20.1. Point-in-Time Inspection Is Not Full History

A deadlock cycle can exist very briefly before the detector aborts one transaction. An observer query may **miss** catching both edges simultaneously.

Therefore combine:

- Database logs on deadlock detection.
- PID/`application_name`.
- Query and transaction timelines.
- Lock wait metrics.
- Application SQLSTATEs.

Do not conclude "there was no deadlock" just because a single `SELECT` on `pg_stat_activity` happened not to catch a cycle.

## 21. pg_locks: Inspecting Lock Types

`pg_locks` exposes locks tracked by PostgreSQL. An investigative query:

```sql
SELECT
    l.pid,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.pid, l.granted, l.locktype, l.mode;
```

Important columns:

| Column | Meaning |
|---|---|
| `pid` | Backend holding/waiting for the lock |
| `locktype` | Lock target type such as `relation`, `transactionid`, `tuple` |
| `mode` | Lock mode |
| `granted` | `TRUE` if held, `FALSE` if waiting |
| `relation` | Table/index OID when lock applies to a relation |
| `transactionid` | Transaction ID when lock applies to a transaction |
| `virtualxid` | Virtual transaction ID in certain lock types |

### 21.1. Why Are Row Locks Not Always Visible in pg_locks?

PostgreSQL tracks row locking in tuple headers/versions rather than displaying every held row lock as its own row in `pg_locks`.

When a transaction waits on a row modified by another transaction, observers usually see a **wait on `transactionid`** or coordination locks rather than a neat "row X belongs to T1" row.

Therefore:

- `pg_locks` is very useful for diagnosis.
- `pg_blocking_pids()` is usually handier for finding current blockers.
- Never assume "no row locks exist" just because you don't see a `tuple` lock row.
- Do not rely on a naive join of `pg_locks` rows to always reconstruct the complete wait graph accurately.

## 22. Deadlock Logs and deadlock_timeout

When a deadlock is detected, PostgreSQL logs details of the involved processes and SQL queries depending on configuration.

Example message format:

```text
ERROR: deadlock detected
DETAIL:
  Process 1111 waits for ShareLock on transaction ...;
  blocked by process 2222.
  Process 2222 waits for ShareLock on transaction ...;
  blocked by process 1111.
HINT: See server log for query details.
SQLSTATE: 40P01
```

These PIDs and lock modes are illustrative only. Never copy them into a runbook as fixed constants.

### 22.1. log_lock_waits

The `log_lock_waits` setting helps log prolonged lock waits per configuration.

```sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
```

Changing these in production requires admin privileges and evaluation of log volume/overhead. Do not alter global server settings casually while analyzing a single application issue.

### 22.2. Logging Enough to Correlate Events

Applications should log with care:

- Transaction/request correlation ID.
- Normalized or anonymized account IDs/resource keys where needed.
- Expected lock list and acquisition order.
- Isolation level.
- SQLSTATE and exception class.
- Retry attempt count.
- Transaction duration and lock wait time.
- Commit/rollback outcome.

Avoid logging real bank account numbers, tokens, sensitive payloads, or raw SQL containing PII.

## 23. Deadlocks Also Occur with Foreign Keys and Unique Constraints

Even when an application issues a single-table `INSERT` or `UPDATE`, PostgreSQL may need to lock or check multiple objects.

### 23.1. Foreign Keys

When inserting a child row referencing a parent row, PostgreSQL verifies the parent row exists in a valid state, which can acquire row locks such as `FOR KEY SHARE` on the referenced row.

In another transaction, deleting or updating the parent row's key conflicts. If both transactions also hold other locks in opposite order, a deadlock cycle can form.

**Lesson:** when investigating, examine foreign keys, `ON UPDATE`/`ON DELETE` actions, and all triggered statements.

### 23.2. Unique Constraints / ON CONFLICT

Two transactions inserting competing unique keys must wait for the other's outcome. An `UPSERT` may also acquire update locks on existing rows.

If each transaction writes multiple unique keys in **different orders**, deadlock risk increases.

Illustration with two keys:

```text
T1: insert key X, then key Y
T2: insert key Y, then key X
```

If uniqueness checks cross-wait, a deadlock can occur. When writing batches of keys, sort lists consistently and build retries rather than assuming `ON CONFLICT` resolves all concurrency conflicts.

### 23.3. Triggers

A trigger can update audit tables, counters, or parent resources not called directly by service code. Two workflows acquiring locks in opposite table order **via triggers** can still deadlock.

Therefore, inspect not only endpoint SQL, but also triggers and dependent relations executing inside the transaction.

## 24. Advisory Locks Need Ordering Too

PostgreSQL supports application-defined advisory locks keyed by integers.

Transaction-scoped example:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(240, 10);
SELECT pg_advisory_xact_lock(240, 20);

-- Process corresponding resources.

COMMIT;
```

The pair `(240, account_id)` is an illustrative key. Transaction-level advisory locks are released when the transaction ends.

### 24.1. Advisory Locks Are Not Immune to Deadlocks

If A acquires:

```text
advisory(240,10) -> advisory(240,20)
```

and B acquires:

```text
advisory(240,20) -> advisory(240,10)
```

a wait cycle still occurs. PostgreSQL can detect deadlocks involving advisory locks, so applications must avoid opposite locking protocols.

### 24.2. Transaction-Level vs. Session-Level

- `pg_advisory_xact_lock(...)`: transaction lifetime.
- `pg_advisory_lock(...)`: session lifetime until explicitly unlocked or the connection closes—not released on `COMMIT`.

With connection pools, session-level advisory locks easily leak unless release is strictly managed. Prefer transaction-level locks for short workflows.

### 24.3. Try-Lock

```sql
SELECT pg_try_advisory_xact_lock(240, 10);
```

Returns a boolean indicating whether the lock was acquired immediately. Skipping waits alone does not guarantee correctness; the application must handle the `false` case and avoid running half a workflow.

## 25. Combining Lock Ordering with Isolation Levels

### 25.1. READ COMMITTED

At PostgreSQL's common default, a transaction may wait for a row modified by another transaction. Once released, `UPDATE` re-evaluates its condition against the latest committed row version.

Example:

```sql
UPDATE deadlock240.accounts
SET balance = balance - 100
WHERE account_id = 10
  AND balance >= 100
RETURNING balance;
```

Conditional `UPDATE` prevents certain read–modify–write bugs when multiple requests hit one account.

Yet whenever a transfer spans two rows, **consistent lock ordering** is still needed to prevent deadlocks.

### 25.2. REPEATABLE READ

A transaction-wide snapshot triggers serialization errors if a row it tries to update was modified by another transaction since the snapshot. This **does not eliminate** deadlock possibilities across arbitrary lock schedules.

Never treat "enabling `REPEATABLE READ`" as a lock-ordering strategy.

### 25.3. SERIALIZABLE

PostgreSQL aborts transactions with `40001` to preserve serializability. Yet `SERIALIZABLE` **does not guarantee `40P01` cannot happen** if the application still acquires locks in a cycle-inducing order.

You may need to handle both:

- `40001` — serialization failure.
- `40P01` — deadlock detected.

Both typically require retrying the **entire transaction** when business logic permits, while logging and measuring separately to tell lock-order deadlocks apart from SSI dependency aborts.

## 26. Retrying After a Deadlock Must Cover the Entire Transaction

When PostgreSQL raises `40P01` in a normal transaction, the failed transaction must be rolled back. **Do not retry only the failing `UPDATE` statement** inside the aborted transaction.

Transfer example:

```text
BEGIN
    debit 100 from A   <-- succeeded provisionally
    credit 100 to B    <-- hits 40P01
ROLLBACK
```

After `ROLLBACK`, the provisional debit is not committed. The retry must execute again from scratch:

```text
new BEGIN
    lock A/B in consistent order
    verify sufficient balance
    debit source
    credit target
COMMIT
```

### 26.1. Retry Rules

1. Catch SQLSTATE `40P01`.
2. Roll back the entire transaction.
3. Obtain a clean transaction per your transaction manager.
4. Re-read business data since state may have changed.
5. Re-run all required steps.
6. Use bounded retries with jittered backoff where appropriate.
7. If max attempts are exceeded, return a transient error or enqueue per requirements.
8. Never repeat external side effects already emitted outside the transaction.

### 26.2. Common Error Codes

| SQLSTATE | Meaning | Handling direction |
|---|---|---|
| `40P01` | Deadlock detected | Roll back, typically retry entire transaction |
| `40001` | Serialization failure | Roll back, retry entire transaction |
| `55P03` | Lock not available | Check `NOWAIT`/`lock_timeout`; apply appropriate retry policy |
| `57014` | Query canceled | Likely `statement_timeout` or explicit cancel; diagnose cause |
| `23505` | Unique violation | Check data/logic; do not blindly retry |
| `23514` | Check violation | Invalid data condition; fix logic/input |

**Do not rely on exception message text** to distinguish deadlocks from timeouts because wording varies by version and locale. Always use SQLSTATE.

## 27. JDBC/Java: Ordered Locking and Retries

The sample below uses an application-configured `DataSource`. The two account IDs are sorted **before acquiring locks**. Requires Java text blocks.

### 27.1. Transfer Method with Explicit Lock Ordering

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(int sourceId, int targetId, long amount)
            throws SQLException {
        if (sourceId == targetId || amount <= 0) {
            throw new IllegalArgumentException(
                "Invalid source/target or amount");
        }

        int[] ids = {sourceId, targetId};
        Arrays.sort(ids);

        try (Connection c = dataSource.getConnection()) {
            c.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);

            try {
                // Lock by sorted ID, not cash-flow direction.
                String lockSql = """
                    SELECT account_id
                    FROM deadlock240.accounts
                    WHERE account_id = ?
                    FOR UPDATE
                    """;

                for (int id : ids) {
                    try (PreparedStatement ps =
                             c.prepareStatement(lockSql)) {
                        ps.setInt(1, id);
                        try (ResultSet rs = ps.executeQuery()) {
                            if (!rs.next()) {
                                throw new SQLException(
                                    "Account not found: " + id);
                            }
                        }
                    }
                }

                String debitSql = """
                    UPDATE deadlock240.accounts
                    SET balance = balance - ?,
                        updated_at = now()
                    WHERE account_id = ?
                      AND balance >= ?
                    RETURNING balance
                    """;

                try (PreparedStatement ps =
                         c.prepareStatement(debitSql)) {
                    ps.setLong(1, amount);
                    ps.setInt(2, sourceId);
                    ps.setLong(3, amount);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException(
                                "Insufficient balance or account not found");
                        }
                    }
                }

                String creditSql = """
                    UPDATE deadlock240.accounts
                    SET balance = balance + ?,
                        updated_at = now()
                    WHERE account_id = ?
                    """;

                try (PreparedStatement ps =
                         c.prepareStatement(creditSql)) {
                    ps.setLong(1, amount);
                    ps.setInt(2, targetId);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                            "Could not update target account");
                    }
                }

                c.commit();

            } catch (SQLException | RuntimeException ex) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }
}
```

Here:

- Lock order is **min(`account_id`) then max(`account_id`)**.
- Both accounts are locked before running `UPDATE`s.
- The debit checks sufficient balance atomically in the same `UPDATE`.
- Any failure rolls back the entire transaction.
- Success is reported only after `commit()`.

This is a **locking learning sample**, not a full production money system. Real systems require double-entry ledgers, idempotency keys, multi-source double-spend protection, overflow checks, authorization, and reconciliation.

### 27.2. Wrapping the Transaction with an Outer Retry Loop

A service can wrap the entire operation:

```java
public void transferWithRetry(
        int sourceId, int targetId, long amount)
        throws SQLException {

    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            // Opens a fresh transaction on each call.
            transfer(sourceId, targetId, amount);
            return;
        } catch (SQLException ex) {
            String state = ex.getSQLState();
            boolean retryable =
                "40P01".equals(state) || "40001".equals(state);

            if (!retryable || attempt == maxAttempts) {
                throw ex;
            }

            // In production: bounded backoff/jitter.
            // Never hold a transaction open while waiting to retry.
        }
    }
}
```

This illustrates retrying outside the transaction boundary. With Spring or a transaction framework, let the framework open/rollback/commit a new transaction on each attempt; avoid accidentally retrying inside **the same failed transaction**.

### 27.3. Side Effects Outside PostgreSQL

Never do:

```text
BEGIN
  debit money
  send email "transfer succeeded"
  credit money -> deadlock 40P01
ROLLBACK
```

The email went out even though the DB rolled back.

To publish events safely, consider the **transactional outbox**: write business records and outbox records in the same transaction, and publish after commit. Retries require idempotency so requests are not processed twice if the client disconnects around `COMMIT`.

## 28. Spring and Transaction Boundaries

When using Spring or similar frameworks:

- Ensure **one retry attempt = one brand-new transaction**.
- Never catch `40P01` and swallow it inside a transaction already marked rollback-only.
- Avoid self-invocation that bypasses transaction/retry proxies.
- Only retry classified retryable exceptions with **idempotent semantics**.
- Never hold locks during network API calls.
- Unwrap nested exceptions to inspect the underlying `SQLException`'s SQLSTATE.

Conceptual structure:

```text
retry boundary
    |
    +-- begin transaction
          |
          +-- sort keys
          +-- lock keys in order
          +-- validate
          +-- update source and target
          |
       commit
    |
if 40P01/40001:
    retry new transaction
```

If a service runs inside an outer transaction, audit lock ordering across **the entire outer transaction**, not only the transfer method. A method with proper ordering can still deadlock if a parent transaction already locked other resources in reverse order.

## 29. Lock Ordering for Complex Workflows

### 29.1. Order Placement

A system might touch:

```text
customer
order
inventory
coupon
payment_intent
outbox
```

Establish an order by **resource type** and **key within each type**, for example:

```text
(tenant_id)
    -> customer_id
    -> order_id
    -> ascending SKU
    -> coupon_id
    -> outbox
```

This is just a **policy example**, not a PostgreSQL-mandated order. Actual design must fit foreign keys, triggers, and workload characteristics.

### 29.2. Multi-Item Orders

If two orders both need SKUs X and Y:

```text
Order 1: X -> Y
Order 2: Y -> X
```

a wait cycle can form. Sorting SKUs:

```text
Order 1: X -> Y
Order 2: X -> Y
```

eliminates reverse-order deadlocks on inventory rows.

### 29.3. Parent/Child Table Updates

If one transaction locks parent then child while another locks child then parent, deadlock risk rises. Align operations under a global convention and check indirect locks from FKs and triggers.

### 29.4. Bulk Updates

Never assume:

```sql
UPDATE deadlock240.accounts
SET updated_at = now()
WHERE account_id IN (10, 20);
```

locks 10 before 20 just because `IN` was written that way. For high-contention batches, explicitly collect and lock primary keys in order or shard batches so workers avoid cross-contention.

### 29.5. Avoid Overly Large Transactions

The more locks a transaction holds and the longer it holds them, the higher the chance of hitting a resource held by another transaction. Do the following:

- Keep batches bounded.
- Avoid starting transactions before DB work is actually needed.
- Perform concurrency-insensitive reads and calculations before entering the critical section when safe.
- Do not split an atomic invariant into separate commits just to dodge locks.
- Maintain stable lock ordering within every batch.

## 30. Deadlock vs. Write Skew

Both involve concurrent transactions, yet their nature differs:

**Deadlock:**

```text
A holds row 10, waits for row 20
B holds row 20, waits for row 10
=> PostgreSQL detects wait cycle
=> One transaction fails with 40P01
```

**Write skew:**

```text
A reads "2 doctors on call", updates DR_A
B reads "2 doctors on call", updates DR_B
A and B update different rows
=> Neither waits for the other
=> Both commit under REPEATABLE READ
=> Invariant "at least 1 doctor on call" is broken
```

Comparison:

| Attribute | Deadlock | Write skew |
|---|---|---|
| Lock wait cycle | Yes | Not required |
| Typical SQLSTATE | `40P01` | May succeed with no error under `REPEATABLE READ` |
| Direct consequence | One transaction aborted to break cycle | Invalid data invariant committed |
| Primary solution | Consistent lock ordering, short transactions, retries | `SERIALIZABLE` + retries, guard locks, proper constraints |
| Visible in logs | Usually logs deadlock error | May produce zero errors |

**Having no deadlocks does not prove transactions are correct.** Systems must still enforce business invariants and use appropriate isolation levels.

## 31. Deterministically Testing Deadlock Reproduction

A unit test calling two methods sequentially will never reproduce a deadlock. You need **two concurrent transactions** and a synchronization barrier:

```text
Test runner
    |
    +--- Conn A: BEGIN
    |
    +--- Conn B: BEGIN
    |
    +--- A: UPDATE account 10 -----+
    |                              |
    +--- B: UPDATE account 20 -----+--> BARRIER
                                           |
                                  release both
                                           |
                       A UPDATE 20   B UPDATE 10
                             |              |
                          waits             waits
                             \              /
                         one gets 40P01
                                           |
                              rollback victim
                              commit winner
                                           |
                              assert total = 2000
```

### 31.1. Deadlock Test Assertions

In the **deliberately reversed-order scenario**:

- Two independent connections.
- Both complete their first row update and hold transactions open before the barrier.
- Both second updates contend, forming a wait cycle.
- One transaction receives `40P01`.
- No negative balances when `CHECK` and `UPDATE` conditions hold.
- Victim rolls back; winner commits.
- Total balance remains conserved per lab data.

In the **fixed same-order scenario**:

- Lock waits may occur.
- No A↔B deadlock cycle should occur from those two accounts alone.
- Both transfers succeed sequentially if balances suffice.
- Final balances and sum are accurate.

### 31.2. Why Not Just Use pg_sleep?

`pg_sleep(0.2)` increases overlap probability, but does not guarantee both sessions have acquired their first lock. A test-runner barrier (waiting until both A and B report "first account locked") is deterministic and reliable.

### 31.3. Testing Retries

After one transaction hits `40P01`, have the application retry the full transaction and verify:

- Final balances reflect both successful transfers.
- No duplicate transfer audit records exist.
- No confirmation emails/events were emitted for the rolled-back attempt.
- No aborted-transaction connection is returned to the pool.
- Retries stop cleanly when the cap is reached.

## 32. Multiple Lock Types: Global Ordering and Limits

An ascending lock-ordering rule **sharply reduces** deadlock risk, yet is not a silver bullet guaranteeing zero deadlocks in every PostgreSQL transaction.

Why can deadlocks still occur?

1. A trigger locks auxiliary tables/rows outside the application's expected order.
2. Foreign keys and unique checks introduce indirect locks.
3. Other code paths do not follow the convention.
4. A caller transaction already acquired locks before invoking the service.
5. DDL/migrations interleave with DML.
6. Lock upgrades from `SHARE` to `UPDATE`.
7. Advisory locks acquired in a different order.
8. Multi-row execution plans locking rows in an unexpected order.
9. Long transactions touching resources whose workflows cannot be ordered simply without redesign.

Therefore, production strategy needs **two layers**:

- **Prevention:** lock ordering, short transactions, minimal lock scope, consistent protocols.
- **Recovery:** catching `40P01`, rolling back, and bounded idempotent retries.

## 33. Practical Question: Should You Manually Kill Blocking Sessions?

During investigation, a query may point to a blocking PID. Yet calling:

```sql
SELECT pg_cancel_backend(<pid>);
```

or:

```sql
SELECT pg_terminate_backend(<pid>);
```

is an **impactful operational action**, not normal application deadlock handling. Above, `<pid>` is a placeholder, not runnable SQL.

- `pg_cancel_backend` requests canceling the backend's active query.
- `pg_terminate_backend` requests terminating the session, rolling back its transaction.
- Execution requires appropriate roles/permissions.
- Killing the wrong transaction can disrupt live requests or system workflows.

PostgreSQL already has a deadlock detector. For `40P01`, **prioritize fixing lock ordering and retries**; intervene manually on a PID only under DBA procedures after verifying the blocker and impact.

## 34. Common Mistakes

### Mistake 1 — Locking "Source First, Destination Second"

Two opposite transfers create A→B and B→A orders.

**Fix:** lock by immutable identifier keys (min ID then max ID), not source/destination roles.

### Mistake 2 — Thinking Single-Row UPDATE Statements Cannot Deadlock

A transaction can run multiple `UPDATE`s and retain locks from earlier statements.

**Fix:** analyze the entire transaction, not one statement in isolation.

### Mistake 3 — Using SELECT FOR UPDATE in Opposite Order

`FOR UPDATE` still waits and can form wait cycles.

**Fix:** enforce consistent order across all writers.

### Mistake 4 — Using WHERE id IN (...) and Assuming IN Order Equals Lock Order

SQL makes no such guarantee.

**Fix:** establish explicit ordered locking by sorted keys.

### Mistake 5 — Confusing deadlock_timeout with lock_timeout

`deadlock_timeout` sets when deadlock detection runs; `lock_timeout` limits how long to wait for a lock.

### Mistake 6 — Assuming Every Long Lock Wait Is a Deadlock

A transaction holding a lock without waiting for anyone else can block many sessions without any wait cycle.

**Fix:** use `pg_blocking_pids`, `pg_stat_activity`, and logs to distinguish them.

### Mistake 7 — Retrying Only the UPDATE That Hit 40P01

After the error, the transaction must roll back; earlier reads/decisions may be stale.

**Fix:** retry the entire transaction.

### Mistake 8 — Emitting External Side Effects Before COMMIT

The transaction may still roll back on a deadlock.

**Fix:** emit after `COMMIT`, using an outbox and idempotency.

### Mistake 9 — Upgrading from FOR SHARE to UPDATE Across Concurrent Sessions

Two sessions holding `SHARE` and then wanting stronger locks create a wait cycle.

**Fix:** if you know you will update, acquire `FOR UPDATE` from the start.

### Mistake 10 — Ignoring Triggers and Foreign Keys

The application locks in order, yet a trigger updates another table outside the protocol.

**Fix:** audit all locks taken across the full transaction.

### Mistake 11 — Using SKIP LOCKED for Money Transfers

Skipping a locked account leaves a transfer missing its source or target.

**Fix:** use `SKIP LOCKED` only where temporarily skipping items is valid, such as job queues.

### Mistake 12 — Keeping Transactions Open While Waiting on Network APIs

Holds locks longer, worsening lock waits and deadlock risk.

**Fix:** keep critical sections short; perform external effects after commit or via outbox.

### Mistake 13 — Seeing No Tuple Row in pg_locks and Concluding No Row Lock Exists

Row locks do not always appear as simple rows there.

**Fix:** combine blocker PIDs, `transactionid` waits, and logs.

### Mistake 14 — Testing Only on One Connection

Cannot produce two concurrent independent transactions.

**Fix:** use two connections and a synchronization barrier.

### Mistake 15 — Swallowing 40P01 as Success

The transaction failed and must never return a success response.

**Fix:** roll back, retry, or surface an error once retries exhaust.

### Mistake 16 — Thinking SERIALIZABLE Eliminates Deadlocks

`SERIALIZABLE` can raise `40001`, yet transactions can still experience lock waits and `40P01` deadlocks.

### Mistake 17 — Using a Global Lock Instead of Resource-Scoped Locks

Even unrelated transfers or shifts end up waiting on each other.

**Fix:** lock per account/resource/tenant appropriately instead of creating a single hotspot.

### Mistake 18 — Not Logging SQLSTATE and Transaction ID

Makes it hard to tell deadlocks apart from timeouts or serialization failures.

**Fix:** safely log correlation IDs, lock order, and SQLSTATE.

### Mistake 19 — Sorting by Mutable Values

If lock order depends on mutable columns, concurrent updates make order unpredictable.

**Fix:** sort by immutable identifiers like primary keys.

### Mistake 20 — Failing to Check Debited Row Count Before Crediting

Even without deadlocks, a transfer can credit money without debiting if 0 rows is ignored.

**Fix:** verify row count / `RETURNING` and roll back the entire transaction if business conditions fail.

## 35. Exercises with Solutions

The exercises below use `deadlock240.accounts`. Some modify data; test inside lab transactions or reset the fixture once all sessions finish.

### Exercise 1. Distinguishing Lock Wait and Deadlock

**Prompt:** T1 holds A; T2 waits for A; T1 waits for nothing.

**Answer:** This is a lock wait, not a deadlock, because there is no wait cycle.

### Exercise 2. Drawing a Wait-for Graph

**Prompt:** T1 holds A and waits for B; T2 holds B and waits for A.

**Answer:**

```text
T1 -> T2 -> T1
```

There is a cycle; deadlock.

### Exercise 3. Reproducing a Two-Row Deadlock

**Short solution:**

```text
Session A: BEGIN; UPDATE account 10;
Session B: BEGIN; UPDATE account 20;
Session A: UPDATE account 20;  -- waits
Session B: UPDATE account 10;  -- wait cycle
```

PostgreSQL aborts one transaction with `40P01`.

### Exercise 4. Is Session B Guaranteed to Be the Victim?

**Answer:** No. Never rely on terminal ordering to predict the victim; application code must handle errors in any transaction.

### Exercise 5. What Is Error 40P01?

**Answer:** `deadlock_detected`. Usually requires rollback and retrying the entire transaction when business logic allows.

### Exercise 6. Fixing Lock Order for Transfer 20 → 10

**Answer:** still lock account 10 first, account 20 second, then debit 20 and credit 10.

### Exercise 7. Why Is "Source First" Wrong?

**Answer:** opposite-direction transfers have different sources, creating A→B and B→A lock orders.

### Exercise 8. Should You Write UPDATE ... ORDER BY account_id?

**Answer:** PostgreSQL does not offer general `UPDATE ... ORDER BY` syntax like `SELECT`. Enforce lock ordering explicitly with `FOR UPDATE` or a controlled protocol.

### Exercise 9. Does SELECT FOR UPDATE Release Its Lock Immediately After SELECT?

**Answer:** in a normal transaction, locks are held until `COMMIT`/`ROLLBACK`, not released just because `SELECT` returned.

### Exercise 10. Why Can Two FOR SHARE Followed by UPDATE Deadlock?

**Answer:** two transactions hold compatible shared locks; when both try to upgrade to a conflicting update mode, each waits for the other to release `SHARE`.

### Exercise 11. Setting a Lock Wait Limit in a Transaction

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT account_id
FROM deadlock240.accounts
WHERE account_id = 10
FOR UPDATE;

COMMIT;
```

**Solution:** errors if lock acquisition exceeds the timeout; do not confuse with `40P01` deadlock detection.

### Exercise 12. Checking Which PID Is Blocking

```sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

**Solution:** returns current blockers; never use a single `pg_stat_activity` snapshot to infer full history.

### Exercise 13. Why Doesn't pg_locks List Every Row Lock?

**Answer:** PostgreSQL stores row-lock state in tuple versions; lock waits show up via `transactionid`/`tuple` and lock manager entries rather than one row per locked table row in `pg_locks`.

### Exercise 14. What Does deadlock_timeout = 1s Mean?

**Answer:** the wait threshold before PostgreSQL checks for deadlocks; it does not abort every lock wait longer than 1 second.

### Exercise 15. Does SERIALIZABLE Eliminate Deadlocks Automatically?

**Answer:** No. `SERIALIZABLE` enforces serializability and can raise `40001`, yet lock waits and `40P01` deadlocks can still happen.

### Exercise 16. Does ON CONFLICT Guarantee No Deadlocks?

**Answer:** No. Concurrent transactions upserting multiple keys in opposite orders can cross-wait. Consistent ordering and retries are still needed.

### Exercise 17. How Do Foreign Keys Increase Lock Footprint?

**Answer:** FK checks/actions can lock parent or child rows, causing one statement to lock resources beyond the table directly targeted by application code.

### Exercise 18. Can SKIP LOCKED Be Used for a Job Queue?

**Answer:** Yes, if workers are allowed to temporarily skip locked jobs; you still need retries, leases/recovery, and idempotency.

### Exercise 19. Can SKIP LOCKED Be Used for a Two-Account Transfer?

**Answer:** No. Skipping a locked account leaves the transfer missing a mandatory account.

### Exercise 20. Why Does a Retry Need a New Transaction?

**Answer:** the `40P01` transaction has failed; prior reads and decisions may now be stale. You must roll back and start fresh.

### Exercise 21. When Is Lock Ordering Not Enough?

**Answer:** when triggers, FKs, DDL, advisory locks, or other code paths acquire locks outside the protocol; applications must still handle deadlocks.

### Exercise 22. Fixing a Long Transaction

**Prompt:** `BEGIN` → 10s HTTP call → `SELECT FOR UPDATE` → update → send email → `COMMIT`.

**Solution:** move network calls and prep outside the critical section when possible; open the transaction only for read/lock/write and `COMMIT` promptly; use an outbox to send email after commit.

### Exercise 23. Why Does Consistent Lock Ordering Only Cause a Wait?

**Answer:** the later transaction waits on the first lock before acquiring any later lock needed by the earlier transaction, preventing a cycle on that resource pair.

### Exercise 24. What Should Total Balance Be After One Deadlock Rollback?

**Answer:** starting from 1000+1000, if one valid atomic transfer commits and one rolls back, the total remains 2000; individual balances depend on which transfer succeeded.

## 36. Design, Testing, and Operations Checklist

| Question | Risk if skipped |
|---|---|
| How many resources can one transaction lock? | Hidden cycles go unnoticed |
| Is there a global lock order across resource types? | Endpoints acquire locks in opposite orders |
| Are keys locked in ascending immutable ID order? | Batches/transfers easily reverse order |
| Are rows locked before computing on data needing consistency? | Stale decisions |
| Are `UPDATE`/`RETURNING` row counts checked? | One-sided business writes |
| Do triggers and FKs take indirect locks? | Actual lock order differs from expected |
| Are there `idle in transaction` sessions? | Locks held too long |
| Are appropriate timeouts configured? | Requests wait indefinitely |
| Are `40P01`/`40001` retried across the full transaction? | Transient conflict causes permanent failure |
| Are retried requests idempotent? | Duplicate side effects |
| Are SQLSTATE and `application_name` logged? | Hard to diagnose |
| Are `pg_blocking_pids` and lock waits monitored? | Hotspots stay invisible |
| Are two-session barrier tests in place? | Sequential tests miss deadlocks |
| Are lock-upgrade scenarios tested? | Single-row deadlocks missed |
| Are migrations coordinated with DML? | Table lock conflicts |
| Are business invariants verified after commit? | Avoided deadlock but corrupted data |

## 37. Official PostgreSQL Documentation by Version

- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock modes, conflict matrices, row-level locking, deadlocks, advisory locks.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, observing backends and waits.
- [System View pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): interpreting `pg_locks`.
- [Lock Management Functions](https://www.postgresql.org/docs/current/functions-admin.html): helper functions including `pg_blocking_pids()`.
- [Runtime Configuration: Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html): deadlock and lock monitoring parameters.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): `lock_timeout` and `statement_timeout`.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): MVCC, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `40P01`, `40001`, `55P03`, and related codes.

Check your environment's version and settings:

```sql
SHOW server_version;
SHOW transaction_isolation;
SHOW deadlock_timeout;
SHOW lock_timeout;
SHOW statement_timeout;
```

## 38. Summary

Deadlocks occur when transactions **hold locks and wait on each other in a cycle**. Transfer example:

```text
T1 transfers 10 -> 20:
    locks account 10
    waits for account 20

T2 transfers 20 -> 10:
    locks account 20
    waits for account 10

T1 <---- cross-wait ----> T2
=> Deadlock
=> PostgreSQL aborts one transaction (40P01)
```

Instead of locking "source first, destination second," the application enforces:

```text
Every transfer:
    lock min(account_id)
    lock max(account_id)
    validate business rules
    update source/destination
    COMMIT
```

When all writers adhere to the same order, wait cycles on those account pairs drop sharply. Yet you must still account for indirect locks from FKs/triggers/DDL and **be ready to retry**.

Core principles:

1. **A lock wait is not a deadlock.** Only a wait cycle is a deadlock; a slow wait may simply be contention.
2. **Locks live for the transaction.** An `UPDATE` finishing does not release locks until `COMMIT`/`ROLLBACK`.
3. **Lock order matters more than cash-flow order.** Lock by stable keys, not source/destination roles.
4. **`FOR UPDATE` does not fix reverse lock ordering.** It locks proactively, yet can still deadlock if ordered inconsistently.
5. **Do not trust `IN(...)` or `UPDATE` to lock in written order.** Design an explicit multi-row locking protocol.
6. **Deadlocks can arise from multiple tables, triggers, foreign keys, `UNIQUE`, advisory locks, and lock upgrades.**
7. **PostgreSQL breaks deadlocks by aborting one transaction.** Catch SQLSTATE `40P01`, roll back, and retry **the entire transaction**.
8. **`SERIALIZABLE` does not eliminate deadlocks**, and `40001` serialization failures are a distinct condition.
9. **Observe using `pg_stat_activity`, `pg_blocking_pids()`, `pg_locks`, and logs**—never guess from response time alone.
10. **Prevention plus recovery:** consistent lock ordering, short transactions, bounded waits, concurrency testing, and idempotent retries.

**One sentence to remember:** two transactions both needing A and B will easily deadlock if one takes A→B while the other takes B→A; standardize a single lock order across all transactions and always handle `40P01` cleanly.
