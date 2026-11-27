# Why Multiple Row Versions Are Needed for Concurrent Reads and Writes in PostgreSQL

When many users use an application at the same time, the database must solve a seemingly contradictory requirement: **readers need to see consistent data, while writers must still be allowed to update data**. If one transaction is reading an account balance, should another transaction changing the balance cause the running query to read half old state and half new state? If every update had to wait for all readers to finish, how many concurrent requests could the system handle?

PostgreSQL solves an important part of this problem using **MVCC — Multi-Version Concurrency Control**. Instead of keeping only one mutable value at a single logical location, PostgreSQL can store **multiple physical versions of the same logical row** and determine which version is visible based on the **snapshot** of the transaction or statement.

As a result, in many common cases:

- A reading `SELECT` does not need to wait for another transaction performing an `UPDATE` on the same row.
- An `UPDATE` does not have to wait for every normal `SELECT` to finish before modifying a row.
- Readers do not see uncommitted changes made by others (*dirty read*).
- One transaction can continue seeing the old version while another transaction has already committed a new version.
- PostgreSQL still uses **locks**, conflict checks, and isolation rules when two parties write concurrently — MVCC is **not** a mechanism that bypasses all locks.

This lesson belongs to the **MVCC** chapter of the **Database Engine Relational PostgreSQL** module. After completing it, you will be able to explain **why multiple row versions are needed**, observe two `psql` sessions operating in parallel, distinguish `READ COMMITTED` from `REPEATABLE READ`, understand the basic meaning of `xmin`/`xmax`/`ctid`, and know why `VACUUM` along with managing long transactions is an indispensable part of MVCC.

## 1. The Problem If There Were Only One Row Version

Suppose the database stores one row:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | An | 100.00 |

Two operations occur almost simultaneously:

- **Session A** runs a report and needs to read the balance of account 1.
- **Session B** transfers an additional 50 into account 1 and commits.

If the system kept only a single physical copy and let B directly overwrite 100 with 150 without coordination, A could observe data changing mid-calculation. Another implementation might force B to wait for A to finish reading or force A to wait for B to finish writing. With thousands of users, this waiting reduces throughput and increases the risk of bottlenecks.

PostgreSQL chooses another approach: **the old version can be retained for readers that already hold a snapshot**, while a new version is created for the writer's change.

~~~text
Same logical row account_id = 1

                   Time →
                 ┌───────────────────┐
Old version      │ balance = 100     │
                 │ visible to        │
                 │ old snapshot      │
                 └───────────────────┘
                          │ UPDATE + COMMIT
                          ▼
                 ┌───────────────────┐
New version      │ balance = 150     │
                 │ visible to        │
                 │ new snapshot      │
                 └───────────────────┘
~~~

This does not mean every SQL query always reads the same version: PostgreSQL decides based on the snapshot, transaction state, and the isolation level in use.

## 2. MVCC Does Not Create Multiple "Accounts"; It Creates Multiple Versions of One Logical Row

In SQL, the table still has one account with primary key `account_id = 1`. Business data is not considered to have two accounts for An just because storage temporarily holds both the 100 version and the 150 version.

To avoid confusion, distinguish:

| Term | Meaning |
| --- | --- |
| **Logical row** | The entity the application works with, such as account ID 1 |
| **Tuple / row version** | A physical record in the heap, containing values along with metadata for MVCC |
| **Snapshot** | Information that determines which transactions/versions are visible at read time |
| **Transaction** | A group of operations that commit or roll back atomically |
| **Visibility** | The rules that determine whether a tuple is visible to a given snapshot |
| **Dead tuple** | A version no longer needed by any relevant transaction/snapshot and eligible to be reclaimed by cleanup |

A normal `UPDATE` creates a **new tuple version** and marks the old version via transaction metadata. Application `SELECT` queries return only the version allowed to be seen under MVCC rules.

**MVCC is not an audit table:** old versions are not kept forever. Once no snapshot needs them, PostgreSQL can clean them up. To retain multi-year business history, you need a dedicated audit/temporal history design.

## 3. What Is a Snapshot?

A transaction may be committed or uncommitted. When reading a row, PostgreSQL does not simply ask "which value was written most recently?", it also asks:

1. Has the transaction that created this version committed yet?
2. Did the creating transaction commit before the appropriate snapshot boundary?
3. Was this version updated or deleted by another transaction that committed in a way that makes it no longer visible?
4. Are there changes made by the **current transaction itself** that it must see?
5. Does the isolation level specify taking a snapshot per statement or holding it for the transaction?

A snapshot is not just a simple timestamp. PostgreSQL manages transaction IDs and active transactions to determine visibility. Two transactions may start in one order, while commit order matters for many visibility decisions.

### Illustrating a Read

~~~mermaid
sequenceDiagram
    participant A as Session A - Reader
    participant B as Session B - Writer
    participant P as PostgreSQL
    A->>P: SELECT balance (old snapshot)
    P-->>A: 100
    B->>P: UPDATE balance=150
    B->>P: COMMIT
    A->>P: Next SELECT (snapshot depends on isolation)
    alt READ COMMITTED - new statement
        P-->>A: Can see 150
    else REPEATABLE READ - same transaction/snapshot
        P-->>A: Still sees 100
    end
~~~

In both branches, A **never reads uncommitted data** from B. The difference lies in **when the snapshot is refreshed**.

## 4. How Do INSERT, UPDATE, and DELETE Affect Row Versions?

### 4.1. INSERT

`INSERT` creates a new tuple. While the creating transaction has not committed, another transaction normally **cannot see** that tuple yet. Once committed, eligible new snapshots can see it.

~~~sql
INSERT INTO mvcc_lab.accounts
    (account_id, owner_name, balance)
VALUES (5, 'Em', 300.00);
~~~

### 4.2. UPDATE

`UPDATE` creates a new version carrying the modified values and invalidates the old version for eligible snapshots after the updating transaction commits.

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance + 50
WHERE account_id = 1;
~~~

Without special triggers, the new logical value is 150 when starting from 100. **The old version may still exist physically** to serve readers holding an old snapshot.

### 4.3. DELETE

`DELETE` does not mean immediately erasing every byte of the tuple at the moment the statement runs. PostgreSQL marks the version as deleted via metadata; snapshots allowed to see the old version can still continue reading it, while new snapshots after commit no longer see that logical row.

~~~sql
DELETE FROM mvcc_lab.accounts
WHERE account_id = 5;
~~~

Versions that are no longer needed will be cleaned up gradually. That is why **deleting many rows does not necessarily shrink the table file immediately**.

### 4.4. ROLLBACK

If a transaction creates a new version and then rolls back, the new version never becomes committed data visible to other transactions. The old version remains valid under visibility rules.

Rolling back does not require PostgreSQL to "overwrite the old value back in place" in every case. MVCC and the transaction log allow determining which version is effective.

## 5. Creating the Lab Dataset

The examples run on **a PostgreSQL database dedicated to learning**. The setup script contains `DROP SCHEMA ... CASCADE`, so **do not run it on a production system or a shared schema containing data you need to keep**.

~~~sql
-- Run only in a lab database that you manage.
DROP SCHEMA IF EXISTS mvcc_lab CASCADE;
CREATE SCHEMA mvcc_lab;

CREATE TABLE mvcc_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12,2) NOT NULL CHECK (balance >= 0),
    row_version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO mvcc_lab.accounts
    (account_id, owner_name, balance, row_version)
VALUES
    (1, 'An',   100.00, 0),
    (2, 'Binh', 200.00, 0),
    (3, 'Chi',   50.00, 0),
    (4, 'Dung', 120.00, 0);
~~~

Initial data:

| account_id | owner_name | balance | row_version |
| ---: | --- | ---: | ---: |
| 1 | An | 100.00 | 0 |
| 2 | Binh | 200.00 | 0 |
| 3 | Chi | 50.00 | 0 |
| 4 | Dung | 120.00 | 0 |

Here `row_version` is an **application-defined column** used to illustrate optimistic locking later. It is **not** PostgreSQL's `xmin`/`xmax` metadata.

### Preparing Two Sessions

Open **two psql windows** (or two separate connections to the same database):

- **Session A:** used to read or keep a transaction open.
- **Session B:** used to update and commit while A is still active.

All statements apply to `mvcc_lab.accounts`. If you run the experiments in order, some exercises intentionally commit to illustrate snapshots. When you want to return to the initial seed, **only after ending the transactions in both sessions**, you can run in the lab database:

~~~sql
UPDATE mvcc_lab.accounts
SET
    balance = CASE account_id
        WHEN 1 THEN 100.00
        WHEN 2 THEN 200.00
        WHEN 3 THEN 50.00
        WHEN 4 THEN 120.00
    END,
    row_version = 0,
    updated_at = now()
WHERE account_id IN (1, 2, 3, 4);
~~~

This reset operation is **for lab data only**. Do not use it on a real system; do not run it while the two lab sessions are still waiting on each other because it may create additional lock contention.

## 6. Experiment 1: READ COMMITTED Sees New Values Between Two SELECTs

PostgreSQL's default isolation level is **`READ COMMITTED`**. Within a transaction, each statement that reads data normally uses a new snapshot taken at the start of that statement.

Start with Binh's account (ID 2) with balance 200.00.

**Session A — initial read and keep the transaction open:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 2;

-- Initial result: 200.00.
-- Keep transaction A open, switch to session B.
~~~

**Session B — update and commit:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = balance + 25,
    updated_at = now()
WHERE account_id = 2
RETURNING account_id, balance;

COMMIT;
~~~

B has committed `balance = 225.00`.

**Back to Session A:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 2;

COMMIT;
~~~

A's second `SELECT` returns **225.00**, even though both `SELECT` statements were executed inside the same transaction A.

This does not mean PostgreSQL modified data mid-flight while A was reading **a single statement**. The two `SELECT` queries are two separate statements, and **each `READ COMMITTED` statement can have its own snapshot**.

### Why Is This Called a Non-Repeatable Read?

The same query is executed twice within the same transaction, yet returns different results because another transaction committed changes between the two statements. That phenomenon is called a **non-repeatable read** and is permitted under `READ COMMITTED`.

Key points to remember:

- A does not see B's **uncommitted** changes.
- A can see B's **committed** changes in the next statement.
- This is normal behavior of the default isolation level, not an MVCC bug.

## 7. Experiment 2: REPEATABLE READ Still Sees the Old Version

Now use An's account (ID 1) with an initial balance of 100.00.

**Session A — set REPEATABLE READ before the first query:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Result: 100.00.
-- Keep transaction A open.
~~~

**Session B — write and commit normally:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = balance + 50,
    updated_at = now()
WHERE account_id = 1
RETURNING account_id, balance;

COMMIT;
~~~

B has committed balance **150.00**.

**Session A — read again:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Still sees 100.00 under transaction A's snapshot.

COMMIT;

-- Now a new statement after A has ended:
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- Sees 150.00.
~~~

In `REPEATABLE READ`, the snapshot is normally fixed from **the first statement that requires a snapshot** in the transaction, not simply from the time `BEGIN` is sent. Subsequent reads in the transaction continue using that snapshot, while the transaction still sees its own changes according to PostgreSQL semantics.

### The Most Important Takeaway

**B does not wait for A to COMMIT in order to update.** B can write and commit while A is still holding the old snapshot. PostgreSQL retains version 100 long enough for A to continue reading it, while allowing new post-commit snapshots to see 150.

This is the direct reason why **multiple row versions** are needed: if version 100 were overwritten and lost immediately, A could not continue having a consistent `REPEATABLE READ` snapshot without locking/blocking B's update.

~~~mermaid
flowchart LR
    V1["Old tuple: 100"] -->|"A - snapshot before B commit"| A["Session A reads 100"]
    V2["New tuple: 150"] -->|"After B commit"| N["New reader reads 150"]
    V1 -->|"UPDATE creates new version"| V2
~~~

## 8. Comparing READ COMMITTED and REPEATABLE READ

| Question | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| Snapshot used | Usually new for each statement | Fixed for the transaction once established |
| Two SELECTs on the same row after another commit | May see two different values | Still sees the version matching the old snapshot |
| Reads uncommitted data from other transactions? | No | No |
| Can phantom reads occur between two SELECTs? | Yes | PostgreSQL prevents phantoms in its Repeatable Read implementation |
| If updating a row changed by another transaction after the snapshot | May wait and re-process per READ COMMITTED rules | May hit a serialization failure, requiring a full transaction retry |
| Best suited for | Many typical API/OLTP operations | Reports needing a consistent snapshot or multi-statement read logic |

**Note:** PostgreSQL treats `READ UNCOMMITTED` like `READ COMMITTED`, because it does not allow dirty reads as described for "read uncommitted" in some other database systems.

`REPEATABLE READ` is stronger at preserving a snapshot, but it does not prevent every cross-row anomaly. Ensuring complex invariants at a serializable level may require `SERIALIZABLE` and a retry mechanism when PostgreSQL detects a conflict.

## 9. How Does MVCC Prevent Dirty Reads?

Suppose B starts an update but **has not committed yet**:

**Session B:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 70
WHERE account_id = 3
RETURNING account_id, balance;

-- B sees 120.00 within its own transaction.
-- Not yet COMMIT or ROLLBACK.
~~~

**Session A, another connection:**

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 3;

-- Still sees 50.00 if there are no other committed changes.
~~~

A does not see B's pending uncommitted `balance = 120`. A sees the previously committed version permitted by A's snapshot.

Later B can execute:

~~~sql
ROLLBACK;
~~~

Upon rollback, the value 120 never became committed data visible to A.

If the system allowed A to read 120 before commit and then B rolled back, A could make decisions based on a state **that was never actually confirmed**. That is the dirty read problem. PostgreSQL's MVCC prevents this for normal SQL reads.

## 10. How True Is "Readers Don't Block Writers"?

A commonly heard statement is:

> In PostgreSQL, readers don't block writers and writers don't block readers.

This is a **practical rule for normal `SELECT` queries versus `UPDATE`/`DELETE` on the same data**. It does **not** mean queries never wait for locks.

### Typical Case Where It Holds

**Session A:**

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_lab.accounts
WHERE account_id = 1;

-- A keeps the transaction open to illustrate the snapshot, no FOR UPDATE.
~~~

**Session B:**

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance + 10
WHERE account_id = 1
RETURNING balance;
~~~

B can update and commit without waiting for A to finish **just because A ran a normal SELECT**.

### Very Important Exceptions

- `SELECT ... FOR UPDATE`/`FOR SHARE`/... are **locking reads** and can conflict with writers.
- Two transactions executing `UPDATE`/`DELETE` on the same row can wait on each other.
- A normal `SELECT` acquires a relation-level `ACCESS SHARE` lock, which can conflict with DDL requiring `ACCESS EXCLUSIVE`.
- Operations such as `ALTER TABLE`, `TRUNCATE`, `VACUUM FULL`, and other table-level locks can make readers/writers wait.
- Deadlocks, resource pressure, and higher isolation levels can still affect transaction progress.

Therefore, a more accurate statement is: **MVCC reduces the need for blocking locks between normal readers and writers on the same rows; PostgreSQL still uses locking where needed to protect correctness.**

## 11. Experiment 3: Two Writers Modifying the Same Row Must Coordinate

Use Chi's account (ID 3) with an initial balance of 50.00. Two sessions want to add 10 and 20 respectively.

**Session A:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 10
WHERE account_id = 3
RETURNING account_id, balance;

-- A sees 60.00, NOT YET COMMITTED.
~~~

**Session B, run while A keeps its transaction open:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 20
WHERE account_id = 3
RETURNING account_id, balance;

-- B may block waiting for the row lock held by A.
~~~

**Session A continues:**

~~~sql
COMMIT;
~~~

B can proceed after A commits. Under the default `READ COMMITTED` level, PostgreSQL coordinates the update on the appropriate row version; `balance = balance + 20` is applied on top of the new value, yielding **80.00** in this test schedule.

**Session B:**

~~~sql
COMMIT;
~~~

Final result:

~~~sql
SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 3;
~~~

It is **80.00**.

### Why Doesn't MVCC Let Two Writers Write Arbitrarily?

If A and B changed the balance concurrently without coordination, the result could lose one of the two additions. PostgreSQL uses **row-level locking** and conflict checks between writers to preserve correctness.

Under `REPEATABLE READ` or `SERIALIZABLE`, the second writer may receive an error such as **`could not serialize access due to concurrent update`**, instead of automatically applying the change onto the new version. The application must roll back and retry the **entire transaction** according to policy.

**MVCC does not mean lock-free.** The system both retains multiple versions for readers and coordinates writers contending on the same row.

## 12. Read-Then-Write Can Cause Application-Level Lost Updates

Suppose an application executes:

~~~text
SELECT balance;
Application computes new_balance = old_balance - 10;
UPDATE accounts SET balance = new_balance WHERE id = 4;
~~~

If two parties operate concurrently, `new_balance` may be calculated from a stale read.

Example with Dung (ID 4), initial balance 120.00:

**Session A — reads and holds 120 in the application:**

~~~sql
BEGIN;

SELECT balance
FROM mvcc_lab.accounts
WHERE account_id = 4;

-- A receives 120.00, plans to subtract 10 => 110.00.
~~~

**Session B — another transaction adds 25 and commits:**

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance + 25
WHERE account_id = 4;

COMMIT;

-- Committed value: 145.00.
~~~

**Session A — writes the number computed from the stale read:**

~~~sql
UPDATE mvcc_lab.accounts
SET balance = 110.00
WHERE account_id = 4;

COMMIT;
~~~

The final result can be **110.00**: B's +25 addition is overwritten by the hardcoded value A computed from stale data.

This shows that **`READ COMMITTED` + MVCC does not automatically protect every application read–compute–write rule**. Updating with a fixed value calculated from stale data is not equivalent to adding/subtracting on the latest row version.

### Better Pattern for Single-Row Addition/Subtraction

~~~sql
UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 4
  AND balance >= 10
RETURNING account_id, balance;
~~~

The arithmetic is evaluated inside the `UPDATE` on the row version PostgreSQL processes, with a non-negative balance guard. This is a fundamental pattern to avoid **lost updates caused by the application overwriting with stale values** when the operation can be expressed directly in SQL.

For real-money systems, you also need a ledger, multi-row transactions, authorization, and system-wide consistency controls; this example is solely to explain MVCC and concurrency.

## 13. Optimistic Locking: A Version Column Does Not Replace MVCC

Sometimes an application must read multiple fields, let a user edit them, and then save the entire record minutes later. In such cases, **optimistic locking** can be used with an application-managed `row_version` column.

Suppose the row has:

~~~text
account_id = 1
row_version = 0
~~~

The application reads version 0 and then sends:

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = 90.00,
    row_version = row_version + 1,
    updated_at = now()
WHERE account_id = 1
  AND row_version = 0
RETURNING account_id, balance, row_version;

ROLLBACK;
~~~

If the version is still 0, the `UPDATE` returns one row with version 1. If another transaction updated it earlier and incremented the version, `row_version = 0` no longer matches, so the `UPDATE` returns **0 rows**, allowing the application to detect the conflict.

Distinguish between:

- **Internal MVCC:** PostgreSQL manages tuple versions and snapshots to provide visibility/concurrency.
- **Application `row_version`:** a business/technical column used for compare-and-swap, preventing overwrites from stale forms.

Every table does not need a `row_version` column for PostgreSQL to run MVCC. Conversely, having MVCC does not replace all optimistic locking at the API layer.

## 14. SELECT FOR UPDATE Changes the Waiting Model

Sometimes an application needs to **read a value and then perform multiple writes based on it** within a single transaction. In that case, a locking read may be appropriate.

~~~sql
BEGIN;

SELECT account_id, balance
FROM mvcc_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- The transaction holds a row lock to coordinate updates.

UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 1
  AND balance >= 10;

COMMIT;
~~~

`FOR UPDATE` requests a row lock on the selected rows. Another transaction attempting to `UPDATE` the same row may have to wait until the lock is released.

### When Should It Not Be Used?

Do not add `FOR UPDATE` to every `SELECT` just out of worry about concurrency. Doing so increases contention, can reduce throughput, and holds locks longer. For read-only reports or display-only APIs, a normal `SELECT` is usually more suitable.

### NOWAIT and SKIP LOCKED

PostgreSQL supports options for locking reads:

~~~sql
SELECT account_id
FROM mvcc_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

`NOWAIT` raises an error if the row lock cannot be acquired immediately.

~~~sql
SELECT account_id
FROM mvcc_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` skips rows that are currently locked and can be useful for **queue workers**. However, the result can be **an incomplete view**, unsuitable when you need to assert that the entire dataset was read accurately.

**Locking reads must still sit inside a sound transaction design**, not serve as a magic eraser for all concurrency anomalies.

## 15. Transaction Isolation and Read Phenomena

Phenomena commonly discussed when learning concurrency:

| Phenomenon | Short Description |
| --- | --- |
| **Dirty read** | Reading data written by another transaction that has not committed |
| **Non-repeatable read** | Reading the same row twice in a transaction and seeing different values due to a new commit |
| **Phantom read** | Repeating the same search condition and seeing the row count/set change between two reads |
| **Serialization anomaly** | Concurrent execution produces a result not equivalent to any valid serial execution |

In PostgreSQL:

| Isolation | Dirty read | Non-repeatable read | Phantom read | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | No (treated as READ COMMITTED) | Possible | Possible | Possible |
| `READ COMMITTED` | No | Possible | Possible | Possible |
| `REPEATABLE READ` | No | No | No | Possible |
| `SERIALIZABLE` | No | No | No | PostgreSQL prevents; transactions may be aborted and require retry |

This is an overview table under PostgreSQL semantics; do not apply assumptions from other database engines without verifying. PostgreSQL's `REPEATABLE READ` uses snapshot isolation, **prevents phantoms**, yet can still exhibit certain anomalies handled by `SERIALIZABLE`.

## 16. Why Might REPEATABLE READ Not Be Enough for Multi-Row Invariants?

Suppose the system requires: "During a shift, **at least one doctor must remain on call**."

Two transactions can both read the state:

~~~text
Doctor A: on_call = true
Doctor B: on_call = true
~~~

Session A sees B is on call, so it lets A go off call. Session B sees A is on call, so it lets B go off call. Each updates **a different row**. If both use old snapshots under `REPEATABLE READ`, both can commit and the final state is **no doctor on call**.

This is an example of **write skew**: transactions do not contend on the exact same row, yet together they violate a cross-row invariant.

~~~text
Session A                               Session B
-----------------------------------     -----------------------------------
Read A=true, B=true                     Read A=true, B=true
UPDATE A.on_call=false                  UPDATE B.on_call=false
COMMIT                                  COMMIT

Final result: A=false, B=false
Invariant "at least one on call" is violated.
~~~

If the business requires an outcome equivalent to a serial schedule, you can use `SERIALIZABLE`, constraints, or an appropriately designed locking mechanism. In PostgreSQL, `SERIALIZABLE` uses dependency/conflict detection (SSI — Serializable Snapshot Isolation) and may **abort a transaction with a serialization failure** to preserve serializability.

The key lesson here: **multiple versions give readers snapshots, but do not automatically prove every multi-row business invariant holds**.

## 17. What Do the System Columns xmin, xmax, and ctid Tell Us?

In PostgreSQL, heap tables carry metadata related to row versions. You can inspect them via system columns:

~~~sql
SELECT
    account_id,
    balance,
    xmin::text AS creating_xid,
    xmax::text AS xmax_info,
    ctid::text AS physical_location
FROM mvcc_lab.accounts
ORDER BY account_id;
~~~

Introductory meaning:

| Column | Basic Meaning | Common Misconception to Avoid |
| --- | --- | --- |
| `xmin` | Transaction ID that created the tuple version | Not a `created_at` timestamp or a stable business version key |
| `xmax` | Metadata related to deleting/updating or locking the tuple | Non-zero does not automatically mean the row is deleted and invisible |
| `ctid` | Current physical location of the tuple in the heap | Not a primary key; can change after UPDATE or maintenance operations |

**Be careful with `xmax`:** this field can carry row-locking information, or an uncommitted or rolled-back transaction; determining visibility requires checking transaction state and tuple metadata. Do not use `WHERE xmax = 0` as an official method to identify "live rows".

### Observing ctid Before and After UPDATE

~~~sql
BEGIN;

SELECT
    account_id, balance, xmin::text, ctid::text
FROM mvcc_lab.accounts
WHERE account_id = 1;

UPDATE mvcc_lab.accounts
SET balance = balance + 1
WHERE account_id = 1
RETURNING
    account_id, balance, xmin::text, ctid::text;

ROLLBACK;
~~~

When `UPDATE` creates a new version, the new tuple has a new physical location, so the observed `ctid` can change. After rollback, the change is not committed.

Do not rely on specific values of `xmin` or `ctid` in answers: they depend on database state, transaction history, and disk page layout.

### xmin Is Not a Transaction Timestamp

A transaction ID is an identifier for MVCC management, not a number of seconds or a user timestamp. It also undergoes wraparound/freeze maintenance. Do not use `xmin` as a "last updated date" or long-term business version in an uncontrolled way.

## 18. Why Does UPDATE Usually Create a New Version Instead of Modifying In Place?

If an update modified the exact old tuple in place without keeping the prior copy, a reader holding an old snapshot would no longer have a consistent data source to read. With multiple versions, PostgreSQL can:

1. Keep the old version long enough for active snapshots that need it.
2. Write a new version carrying the post-UPDATE values.
3. Wait for the writing transaction to commit or roll back to decide which version is visible.
4. Let old snapshots see the old value and new snapshots see the new value according to isolation.
5. Clean up the old version once it is no longer needed.

~~~mermaid
flowchart TD
    A["Tuple v1: balance=100"] --> B["UPDATE balance=150"]
    B --> C["Tuple v1 keeps expiration metadata per transaction"]
    B --> D["Tuple v2: balance=150"]
    C --> E["Old snapshot can read v1"]
    D --> F["New snapshot after commit can read v2"]
    E --> G["When no reader needs v1"]
    G --> H["VACUUM/pruning reclaims eligible space"]
~~~

This comes with a storage cost. MVCC **trades version management and cleanup overhead** for read–write concurrency and snapshot consistency.

## 19. An UPDATE With the "Same" Value Can Still Create a New Version

For example:

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET balance = balance
WHERE account_id = 1
RETURNING account_id, balance, xmin::text, ctid::text;

ROLLBACK;
~~~

Even though the `balance` value did not change, the statement still processes the row matching `WHERE`. In PostgreSQL, a normal `UPDATE` can create a new tuple version and trigger WAL/index/trigger work, even when the assignment produces the exact same value.

Do not write redundant `UPDATE` statements just to "make sure the data is like that" without a business reason. When you want to avoid unnecessary writes:

~~~sql
UPDATE mvcc_lab.accounts
SET balance = 150.00
WHERE account_id = 1
  AND balance IS DISTINCT FROM 150.00;
~~~

`IS DISTINCT FROM` compares safely even with `NULL`. In the lab table where `balance` is `NOT NULL`, `balance <> 150.00` would also work, but `IS DISTINCT FROM` is the more general pattern for nullable columns.

**Do not equate "UPDATE creates a new version" with "every UPDATE forces updating every index".** PostgreSQL has the **HOT** optimization under certain conditions to reduce index overhead.

## 20. What Is a HOT Update?

**HOT — Heap-Only Tuple** is a PostgreSQL optimization for `UPDATE`. When conditions are met—especially when indexed columns do not change and the heap page has enough free space—PostgreSQL can store the new version on the same heap page and **avoid creating a new index entry** for each version in the usual way.

For example, if only `balance` changes while the table's index is only on `account_id`, an `UPDATE` can be a HOT candidate. However, it still depends on `fillfactor`, free space on the page, index types, and internal conditions.

### What HOT Does Not Do

- It does not turn `UPDATE` into an in-place update that bypasses MVCC.
- It does not eliminate the need for `VACUUM`/pruning.
- It does not guarantee that every `UPDATE` on non-indexed columns becomes HOT.
- It does not make `UPDATE` free in terms of WAL, heap storage, or locks.

HOT is an optimization to reduce **index maintenance cost**, not a replacement for multi-versioning.

## 21. Why Is VACUUM Needed?

Because PostgreSQL keeps tuple versions across `INSERT`/`UPDATE`/`DELETE`, over time there will be versions **no longer needed by any eligible snapshot**. If not reclaimed, they accumulate and cause:

- Table/index bloat.
- Scanning lots of data that is no longer useful.
- Increased I/O and buffer cache overhead.
- Difficulty sustaining performance in write-heavy workloads.
- Transaction ID management risks if the system skips vacuum/freeze for too long.

**`VACUUM`** reclaims space from eligible dead tuples, updates related structures, and assists with transaction ID maintenance. PostgreSQL provides **autovacuum** to perform this work based on configuration and demand.

### What VACUUM Does Not Do Immediately

- It does not necessarily return table file disk space to the operating system right away.
- It cannot reclaim a version still needed by a long-lived snapshot.
- By default, it is not `VACUUM FULL`.
- It does not mean business history has been archived separately.

You can run in the lab database:

~~~sql
VACUUM (ANALYZE) mvcc_lab.accounts;
~~~

A regular `VACUUM` command cannot run inside an explicit `BEGIN ... COMMIT` transaction block. `ANALYZE` updates statistics used by the planner; `VACUUM` cleans up eligible versions and performs other maintenance tasks.

## 22. Why Can Long-Running Read Transactions Increase Bloat?

Return to the `REPEATABLE READ` example: A is reading an old snapshot from before B's updates. B can still commit many times, but PostgreSQL **must not reclaim an old version still needed for A's valid snapshot**.

~~~text
A opens REPEATABLE READ
    ↓
A reads old snapshot
    ↓
B UPDATEs and COMMITs many times
    ↓
Old versions may have to be retained
    ↓
A has not COMMITted/ROLLBACKed yet
    ↓
VACUUM cannot clean all versions still needed by A
    ↓
Dead tuples/bloat and maintenance work increase
~~~

A transaction left open for hours with an old snapshot can put pressure on the system even if it **does not actively UPDATE any rows**. This commonly happens when:

- `BEGIN` is opened and a user steps away.
- A program streams results while keeping the transaction open.
- A reporting job holds a snapshot for too long.
- Connections sit in the **idle in transaction** state.
- Certain replication slots or tasks holding an xmin horizon can also affect cleanup.

### Operational Rules

- Keep transactions **as short as business needs allow**.
- Avoid opening a transaction and waiting on external network/API calls for long periods whenever possible.
- Close `ResultSet`/cursors and commit/roll back promptly.
- Monitor `idle in transaction` sessions and transactions holding old snapshots.
- Tune autovacuum, connection timeouts, and workload management based on real metrics.

**Never disable autovacuum just to reduce I/O without understanding MVCC and transaction ID wraparound consequences.**

## 23. Autovacuum, Freeze, and Transaction ID Wraparound

PostgreSQL uses transaction IDs to determine visibility. These IDs are not an infinite sequence that can grow forever without maintenance. PostgreSQL has a **freezing** mechanism and vacuum processes to manage transaction ID age and prevent wraparound from corrupting visibility semantics.

Key points at this lesson's level:

1. MVCC relies on transaction metadata.
2. Transaction IDs have a lifecycle and finite limits.
3. `VACUUM`/autovacuum plays a role in both **cleaning old tuples** and **protecting the system against wraparound risk**.
4. A transaction/snapshot/slot holding an old state for too long can hinder cleanup and operations.

Do not blindly alter parameters like `autovacuum_freeze_max_age`, disable autovacuum workers, or run disruptive maintenance commands based only on lab examples. For real databases, inspect metrics, table sizes, workloads, and documentation for your exact PostgreSQL version.

## 24. Observing Dead Tuple and Autovacuum Statistics

PostgreSQL provides statistics to diagnose tables that may be accumulating old versions:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
ORDER BY relname;
~~~

Where:

- `n_live_tup` is an **estimate** of live tuples.
- `n_dead_tup` is an **estimate** of dead tuples.
- `last_vacuum`/`last_autovacuum` are the timestamps of the most recent recorded vacuum runs.
- Values may lag slightly and do not reflect every change instantaneously.

**Do not treat `n_dead_tup` as an exact byte count of reclaimable space.** It is an operational indicator, not an absolute physical measurement tool.

### Observing Open Transactions

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Columns to watch:

- `xact_start`: when the current transaction started.
- `state = 'idle in transaction'`: the session is keeping a transaction open without executing a statement.
- `backend_xmin`: an indicator related to the snapshot horizon held by the backend.
- `wait_event_type`/`wait_event`: hints at whether the session is waiting on locks, I/O, or other conditions.

Viewing other sessions' details may be restricted by database privileges. **Do not automatically run `pg_terminate_backend` in production** just because a transaction looks old without identifying its owner and impact.

## 25. How Does VACUUM Differ From VACUUM FULL?

| Aspect | Regular `VACUUM` | `VACUUM FULL` |
| --- | --- | --- |
| Goal | Clean up/redistribute internal space for reuse | Rewrite the table to compact it physically |
| Ability to return space to OS | Limited, depends on layout | Usually able to shrink the file more |
| Locking | Designed to run concurrently with normal workloads | Requires a strong lock (`ACCESS EXCLUSIVE`) on the table |
| Cost | Generally lighter, automated via autovacuum | Can be heavy, needs extra temporary disk space and time |
| When to use | Routine maintenance | Special cases after careful evaluation |

`VACUUM FULL` is not a command to run reflexively whenever `n_dead_tup` looks large. In production, it can cause significant disruption due to its strong lock requirement.

The preferred approach is usually to understand **what generates dead tuples and why autovacuum cannot clean them yet** before deciding to rewrite a table.

## 26. MVCC and WAL: Two Different Mechanisms

Beginners often confuse **MVCC** with **WAL (Write-Ahead Log)** because both relate to data changes.

- **MVCC** primarily solves **visibility and concurrency**: who sees which row version, and when?
- **WAL** primarily supports **durability, crash recovery, and replication**: how to recover committed state after a crash and stream changes?

Example when B updates balance 100 → 150:

~~~text
MVCC:
    Reader A can see version 100 via an old snapshot;
    A new reader can see 150 after commit.

WAL:
    Records the changes needed to recover data
    if the server crashes, via write-ahead logging.
~~~

The two mechanisms work together but do not replace each other. **Having WAL does not create snapshot isolation by itself**, and **having multiple tuple versions does not guarantee durability after power loss**.

## 27. MVCC Is Not a Time-Travel System

A common misconception is: "PostgreSQL keeps multiple versions, so I can SELECT any value from yesterday."

In standard PostgreSQL, old tuple versions are only kept while needed for visibility and are cleaned up by vacuum/pruning. The system **does not provide an arbitrary `AS OF` history by default** to query every past table state.

To support multi-year business history queries, you need a dedicated design such as:

- Audit tables storing before/after states.
- History tables with effective validity ranges.
- Change data capture (CDC) or logical decoding where appropriate.
- Event sourcing when the architecture truly requires it.
- Backups and PITR for recovery needs, not as a substitute for row-level query history.

MVCC is a tool for **consistency under concurrent transactions**, not a free infinite history store.

## 28. Indexes Must Coordinate With Row Versions

Suppose there is an index on `owner_name`:

~~~sql
CREATE INDEX idx_accounts_owner_name
ON mvcc_lab.accounts(owner_name);
~~~

A B-tree index helps locate candidate tuple positions, but finding an index key alone **is not enough** to conclude the row is visible in the current snapshot. PostgreSQL still must check MVCC visibility, usually involving the heap tuple or appropriate optimizations.

Points to understand:

1. One logical row can have multiple physical versions over time.
2. Index entries point to physical data whose visibility the executor evaluates.
3. `UPDATE` can incur additional index maintenance, except for optimizations like HOT when eligible.
4. `VACUUM` cleans up index entries/references that are no longer needed.
5. Index-only scans can reduce heap fetches when the visibility map and other conditions allow.

**Indexes do not bypass MVCC.** An index scan must still respect snapshots and commit/rollback status.

## 29. Impact on API and JDBC Design

A Java repository typically uses multiple connections from a pool, corresponding to multiple PostgreSQL sessions. Distinguish:

- **Autocommit enabled:** each standalone statement is typically its own transaction.
- **Autocommit disabled or managed by a transaction manager:** multiple statements share a transaction, subject to isolation and locks until commit/rollback.
- **ResultSet/cursor:** can keep resources and transactions open too long if not closed properly.

JDBC example illustrating a read transaction with `REPEATABLE READ`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static BigDecimal readBalance(
        Connection connection,
        int accountId
) throws SQLException {

    String sql = """
        SELECT balance
        FROM mvcc_lab.accounts
        WHERE account_id = ?
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setInt(1, accountId);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Account not found");
            }
            return rs.getBigDecimal("balance");
        }
    }
}
~~~

The method above is **read-only**; it does not set isolation or commit by itself. The transaction boundary belongs in the service or transaction manager that owns the connection.

Example of a programmatically managed transaction:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

boolean previousAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );

    var first = readBalance(connection, 1);

    // Other statements can run in the same transaction.
    var second = readBalance(connection, 1);

    connection.commit();

} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
~~~

This is an example of **a connection directly managed by the method**; in Spring or a container with a transaction manager, you should not arbitrarily mutate autocommit/isolation on framework-managed connections. Before returning a connection to a pool, isolation/autocommit state must be reset per the pool contract.

### Avoid Opening a Transaction and Making Long Network Calls

An anti-pattern:

~~~text
BEGIN
SELECT ... (holds snapshot/locks)
Call external service for 30 seconds
Wait for response
UPDATE ...
COMMIT
~~~

This prolongs the transaction and can hold old versions and locks longer than necessary. Consider splitting steps, using an outbox/saga, or adjusting the business workflow to reduce transaction duration.

## 30. When a Serialization Error Occurs, What Must Be Retried?

At higher isolation levels, PostgreSQL may detect that a transaction cannot safely commit under the rules and return:

~~~text
SQLSTATE 40001: serialization_failure
~~~

At that point, you generally need to **roll back and re-run the entire transaction**, including the `SELECT` queries used to make decisions, not just re-run the final `UPDATE`.

Example:

~~~text
Old transaction:
    Read A, B
    Compute sum/condition
    UPDATE some rows
    COMMIT → 40001

Proper retry:
    Start a new transaction
    Re-read A, B under a fresh snapshot
    Recompute condition
    UPDATE
    COMMIT
~~~

For deadlocks, PostgreSQL may return `40P01`; the application also needs a bounded retry mechanism appropriate to the context.

**Never blindly retry a transaction that already called an external system with side effects** (charging via an API, sending an email, physical inventory dispatch) without proper idempotency/reconciliation. PostgreSQL rollback cannot undo external services.

## 31. FAQ: Short Questions About MVCC

### 31.1. Does PostgreSQL really keep two full copies of every row at all times?

No. Multiple versions only appear as updates/deletes/inserts happen and are reclaimed when eligible. Do not interpret "multi-version" as a table always storing exactly two copies of every row.

### 31.2. Does every SELECT copy the entire table?

No. A snapshot is a visibility metadata mechanism, not a full physical copy of every row in the table. The executor uses tuple/transaction metadata to choose visible versions.

### 31.3. After COMMIT, do all transactions see the new value immediately?

No. A `REPEATABLE READ` transaction holding an earlier snapshot can continue seeing the old version. Statements in eligible new transactions/snapshots will see the committed data.

### 31.4. If a writer has not COMMITted, does a reader see the new data?

Readers in other transactions normally do not see uncommitted versions. The writer **sees changes made by its own transaction** per PostgreSQL semantics.

### 31.5. Why can a writer still have to wait despite MVCC?

Because two writers can contend on the same row/lock, and due to locks, foreign keys, unique constraints, or isolation rules. MVCC reduces read–write conflicts; it does not eliminate write–write conflicts.

### 31.6. Can xmin be used as an API version field?

`xmin` is useful for **internal inspection**, but should not be treated as a durable, multi-year business version key due to transaction ID characteristics, freezing/wraparound, and maintenance. An application-controlled `row_version bigint` column usually gives a clearer contract.

### 31.7. Does ROLLBACK immediately delete the new tuple?

Rolling back prevents the uncommitted version from becoming visible data; physical reclamation happens through subsequent cleanup mechanisms. Do not equate "transaction rolled back successfully" with "every physical byte was erased immediately".

### 31.8. Is it a bug if a DELETE committed but the file stays large?

Not necessarily. MVCC and `VACUUM` can reuse internal table space without immediately returning disk space to the OS. Check bloat, vacuum activity, old snapshots, and workload.

### 31.9. Does Serializable mean all transactions run sequentially under one database-wide lock?

No. PostgreSQL uses concurrency control mechanisms, including SSI in `SERIALIZABLE`, to achieve results equivalent to a serial schedule for committed transactions; some transactions may be aborted/retried when conflicts are detected. It does not simply take a global lock for every transaction.

## 32. Common Mistakes

### 32.1. Thinking MVCC means "no locks"

False. Normal readers may not block writers, but concurrent writers on the same row, `FOR UPDATE`, and many DDL statements still use locks.

### 32.2. Thinking UPDATE modifies a single version in place

`UPDATE` normally creates a new tuple version; the old version may need to be kept for older snapshots.

### 32.3. Thinking every SELECT in a transaction always reads the same snapshot

This depends on isolation. `READ COMMITTED` usually takes a new snapshot per statement; `REPEATABLE READ` holds the snapshot across the transaction.

### 32.4. Thinking REPEATABLE READ blocks other writers

Writers can still update and commit if there are no lock conflicts; the reader keeps its old snapshot.

### 32.5. Thinking PostgreSQL allows dirty reads under READ UNCOMMITTED

PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED`.

### 32.6. Thinking a snapshot is a physical copy of the whole table

No. Snapshots use transaction metadata and tuple visibility to determine results.

### 32.7. Unconditionally overwriting with stale client values

Can cause application-level lost updates. Use `SET balance = balance + delta`, state conditions, or optimistic locking.

### 32.8. Thinking an UPDATE setting the same old value has zero cost

It can still create a new tuple version, WAL records, triggers, and maintenance work.

### 32.9. Disabling autovacuum because of CPU usage

This can cause dead tuple accumulation and wraparound risk. Evaluate thoroughly before changing configuration.

### 32.10. Keeping transactions open during long user interactions

Long-lived snapshots/locks hinder vacuum cleanup and increase bloat. Keep transactions short.

### 32.11. Thinking VACUUM deletes committed history that the application needs to query

MVCC is not audit history. If history queries are needed, build dedicated history/event tables; do not rely on old tuple versions.

### 32.12. Using ctid or xmin as a stable ID

`ctid` is a physical location that can change; `xmin` is transaction metadata. Use `PRIMARY KEY` and an appropriate business version.

### 32.13. Reading n_dead_tup as an exact dead row count

It is an estimated statistic and may lag. Combine it with other observations and metrics.

### 32.14. Running VACUUM FULL arbitrarily in production

`VACUUM FULL` requires a strong lock and can cause disruption. It is not a substitute for fixing long transactions and autovacuum.

### 32.15. Confusing MVCC with WAL

MVCC solves version visibility and concurrency; WAL provides durability/recovery/replication.

### 32.16. Thinking SERIALIZABLE never needs retries

The system can abort a transaction to prevent anomalies; the application must handle `40001`.

### 32.17. Thinking the same SQL query always sees a fixed number of rows

Under `READ COMMITTED`, each statement can see newly committed data, so the result set can change between executions. Predicates are subject to concurrency.

### 32.18. Thinking longer transactions are safer

Overly long transactions hold locks/snapshots, cause bloat, and hurt operations. Stronger isolation levels must be paired with short transactions and proper retries.

## 33. Practice Exercises With Answers

Use the `mvcc_lab` schema from section 5. For two-session exercises, run steps in exact A/B order and only reset the lab after both transactions have finished.

### Exercise 1. Explain Why Multiple Versions Are Needed

**Question:** A is reading balance 100, and B needs to update it to 150. If B simply overwrote without keeping old data or blocking B, what could happen?

**Answer:** A might fail to continue reading a consistent snapshot. MVCC allows keeping version 100 for old snapshots and creating 150 for new post-commit snapshots, reducing how often readers and writers wait on each other.

### Exercise 2. Recognizing READ COMMITTED Snapshots

A runs `BEGIN READ COMMITTED` and reads 200. B updates to 225 and commits. A reads again in the same transaction.

**Answer:** A can see 225 on the second `SELECT` because it is a new statement with a new snapshot; this is not a dirty read because B has committed.

### Exercise 3. Recognizing REPEATABLE READ Snapshots

A runs `BEGIN REPEATABLE READ` and reads 100. B updates to 150 and commits. A reads again before ending.

**Answer:** A still sees 100 according to the established transaction snapshot. After A finishes and runs a new `SELECT`, it can see 150.

### Exercise 4. Do Dirty Reads Occur in PostgreSQL READ UNCOMMITTED?

**Answer:** No. PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED`; uncommitted data from another transaction does not appear in normal `SELECT` results.

### Exercise 5. Two Writers and Row Locks

A updates account 3 from 50 to 60 without committing. B tries to `UPDATE` the same row `+20`.

**Answer:** B may have to wait on A's row lock; after A commits, under `READ COMMITTED` B can apply `+20` to the matching row and get 80. Under higher isolation levels, B may need to retry due to a serialization failure.

### Exercise 6. Which Way Limits Lost Updates?

Compare two statements:

~~~sql
-- Value 90 was calculated from an old SELECT in the application.
UPDATE mvcc_lab.accounts
SET balance = 90
WHERE account_id = 1;

-- Subtract directly from the row version processed by UPDATE.
UPDATE mvcc_lab.accounts
SET balance = balance - 10
WHERE account_id = 1 AND balance >= 10;
~~~

**Answer:** The second statement is safer for single-row subtraction under `READ COMMITTED` because the formula and guard live inside the `UPDATE` itself. The first statement can overwrite changes committed after the stale read.

### Exercise 7. Optimistic Locking

~~~sql
BEGIN;

UPDATE mvcc_lab.accounts
SET
    balance = 95,
    row_version = row_version + 1
WHERE account_id = 1
  AND row_version = 0
RETURNING balance, row_version;

ROLLBACK;
~~~

**Answer:** When the version is still 0, `UPDATE` returns one row with new version 1; if another writer already incremented the version, it returns 0 rows.

### Exercise 8. Why Isn't ctid a Primary Key?

**Answer:** `ctid` indicates the physical location of a tuple in the heap, which can change after `UPDATE` or maintenance operations like table rewrites. `account_id` is the logical row identifier.

### Exercise 9. Why Doesn't Non-Zero xmax Always Mean Deleted?

**Answer:** `xmax` metadata can also contain lock information or an uncommitted/rolled-back transaction. Visibility must consider transaction state and other metadata, not just a single number.

### Exercise 10. Why Can UPDATE Cause Table Bloat?

**Answer:** `UPDATE` usually creates a new tuple version. Old versions may have to be retained for active snapshots and reclaimed later by vacuum/pruning. Frequent updates or long transactions holding snapshots can cause dead tuples to accumulate.

### Exercise 11. How Do Long Read Transactions Affect VACUUM?

**Answer:** Old snapshots may still need old tuple versions, preventing `VACUUM` from cleaning everything up. Bloat can grow; transactions and autovacuum must be properly managed.

### Exercise 12. How Do VACUUM and VACUUM FULL Differ?

**Answer:** Regular `VACUUM` cleans/reuses space and maintains MVCC while running concurrently with workloads; `VACUUM FULL` rewrites the table, can shrink files, but requires a strong lock.

### Exercise 13. Does HOT Eliminate MVCC?

**Answer:** No. HOT is an optimization to reduce index maintenance when an `UPDATE` qualifies; tuple versions still exist under MVCC.

### Exercise 14. Viewing Current Versions

~~~sql
SELECT
    account_id,
    balance,
    xmin::text AS creating_xid,
    xmax::text AS xmax_info,
    ctid::text AS location
FROM mvcc_lab.accounts
ORDER BY account_id;
~~~

**Answer:** You can observe metadata of the currently visible tuples. You cannot deduce all old versions or full history from this `SELECT` alone.

### Exercise 15. How Do MVCC and WAL Differ?

**Answer:** MVCC determines which snapshot sees which version and enables concurrent reads/writes. WAL records information needed for durability/crash recovery/replication. Both are related but serve different purposes.

### Exercise 16. Why Can REPEATABLE READ Still Have Write Skew?

**Answer:** Two transactions can read a multi-row invariant and then update two different rows. There is no writer conflict on the same row, yet the final state violates the invariant. `SERIALIZABLE`/constraints/appropriate locks and retries are needed.

### Exercise 17. Why Can SELECT FOR UPDATE Make a Reader Block a Writer?

**Answer:** Because it is a locking read, acquiring a row lock that a writer may have to wait for. It differs from a normal `SELECT` based on MVCC snapshots.

### Exercise 18. When Hit With SQLSTATE 40001, What Should Be Retried?

**Answer:** Usually you must roll back and retry the **entire transaction**, including re-reading data, recomputing decisions, and writing data. Not just repeating the final `UPDATE`.

## 34. Checklist for Applying MVCC in Projects

1. **Specify transaction isolation levels**; do not assume every `SELECT` shares the same snapshot.
2. **Distinguish normal readers from locking reads** such as `FOR UPDATE`.
3. **Keep transactions short** and always commit/roll back promptly.
4. **Avoid stale read–modify–write:** move computations into `UPDATE` or use version checks.
5. **Ensure writers coordinate properly** using row locks, constraints, and transactions.
6. **Identify multi-row invariants** that may require `SERIALIZABLE` or other locking/constraints.
7. **Handle serialization/deadlock retries** across the full transaction with bounds and backoff.
8. **Do not rely on `xmin`/`xmax`/`ctid`** for long-term application identifier contracts.
9. **Monitor autovacuum/dead tuples** and never disable cleanup arbitrarily.
10. **Monitor long transactions and `idle in transaction` sessions**.
11. **Understand `VACUUM` is not `VACUUM FULL`** and does not immediately shrink files.
12. **Do not treat tuple versions as audit history**; build dedicated business history if needed.
13. **Evaluate indexes/HOT/WAL** under high-frequency `UPDATE` workloads.
14. **Test with at least two sessions** to clearly observe concurrency phenomena.
15. **Use a dedicated lab database** for experiments that modify and reset data.
16. **Review transaction boundaries in JDBC/frameworks**, avoiding holding snapshots across long network calls.

## 35. Official PostgreSQL Documentation for Deeper Study

These topics are covered in the PostgreSQL documentation; in real deployments, always check the exact major version of your server:

- [Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) — rationale for multiple versions and snapshot visibility.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — READ COMMITTED, REPEATABLE READ, SERIALIZABLE, and concurrency phenomena.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — table locks, row locks, NOWAIT/SKIP LOCKED, and deadlocks.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — xmin, xmax, ctid.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, autovacuum, cleanup, and freeze.
- [HOT](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuple updates.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity, pg_stat_user_tables, and statistics.
- [Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html) — role of WAL, distinct from MVCC.

The `/current/` path refers to the current release documentation on the website. For systems running older PostgreSQL versions, open the documentation matching that major version to avoid misapplying new behaviors or features.

## 36. Summary

**PostgreSQL needs multiple row versions so readers and writers can work concurrently while still maintaining a consistent view of data.** When B updates balance from 100 to 150, PostgreSQL does not have to destroy version 100 immediately: readers with an old snapshot can continue reading 100, while readers with a new post-commit snapshot can read 150.

Four core principles:

1. **Snapshots determine which version is visible.** `READ COMMITTED` can switch snapshots between statements; `REPEATABLE READ` keeps the snapshot across the transaction.
2. **MVCC reduces blocking between normal readers and writers, rather than eliminating locks.** Two writers on the same row still coordinate; `SELECT FOR UPDATE` can block writers.
3. **Retaining old versions has a cost.** `UPDATE`/`DELETE` create data needing cleanup; `VACUUM`/autovacuum and short transactions are essential operational factors.
4. **MVCC does not automatically solve every business problem.** Application-level lost updates, write skew, idempotency, auditing, and external side effects still require dedicated design.

Once you understand why PostgreSQL does not keep only a single record per logical row, you will better understand **why a `SELECT` may not be blocked by an `UPDATE`, why two transactions can read different values, and why `VACUUM` is a mandatory component of a PostgreSQL system with heavy concurrent writes**.
