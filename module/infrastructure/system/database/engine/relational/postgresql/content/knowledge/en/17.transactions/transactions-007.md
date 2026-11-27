# Dirty Reads, Nonrepeatable Reads, Phantoms, and Other Anomalies to Distinguish in PostgreSQL

When multiple connections concurrently read and modify a database, the correctness of each individual SQL statement **is not enough** to guarantee the correctness of the overall business operation. Two requests can check inventory simultaneously and both place orders; a report can read balances at two different moments; or two on-call staff can both see the other is on duty and both go off duty, leaving nobody covering the shift.

These situations belong to **concurrency anomalies**. Common names include **dirty read**, **nonrepeatable read**, **phantom read**, **lost update**, **read skew**, **write skew**, and **serialization anomaly**. Each phenomenon has its own cause and remedy. Notably, **PostgreSQL does not implement every isolation level identically to the SQL standard's minimum definitions**: `READ UNCOMMITTED` behaves like `READ COMMITTED`, and PostgreSQL's `REPEATABLE READ` prevents traditional phantom reads yet still does not guarantee serializability in every scenario.

This lesson belongs to the **Transactions** chapter of the *Database Engine Relational PostgreSQL* module. After this lesson, you will be able to:

- Identify each anomaly from an interleaved schedule of two transactions T1 and T2.
- Distinguish **uncommitted values**, **committed values that change between reads**, and **changes to the set of rows matching a predicate**.
- Understand the roles of MVCC, snapshots, and the three practical isolation levels in PostgreSQL.
- Practice each scenario using two independent `psql` sessions.
- Analyze lost updates, read skew, and write skew, which are often confused with phantoms.
- Know when to use constraints, atomic conditional updates, row locks, optimistic locking, or `SERIALIZABLE`.
- Design proper retry handling for `SQLSTATE 40001` instead of re-running only the last SQL statement.

> Key rule: **An isolation level defines what a transaction can observe and which concurrent outcomes are allowed to commit; it does not replace business invariants, constraints, and transaction protocols.**

## 1. Transactions and Interleaved Execution Schedules

A **transaction** is a group of operations sharing a commit/rollback boundary:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

This example illustrates transferring funds between two accounts, assuming `accounts` already exists. If both UPDATEs run inside one transaction and the transaction rolls back, neither update is committed.

However, while T1 is running, T2 may also read or update data. An interleaved schedule might look like:

~~~text
Time       T1                              T2
---------  ------------------------------  -------------------------
t1         BEGIN
t2         SELECT balance ...
t3                                         BEGIN
t4                                         UPDATE balance ...
t5                                         COMMIT
t6         SELECT balance ...
t7         COMMIT
~~~

What T1 observes at t2 and t6 depends on the isolation level, snapshots, and statement types.

### 1.1. Notation Used

| Notation | Meaning |
|---|---|
| T1, T2 | Two independent transactions |
| R1(X) | T1 reads value X |
| W2(X) | T2 writes value X |
| C1, C2 | T1 or T2 commits |
| A1, A2 | T1 or T2 rolls back / aborts |
| Snapshot | Logical view of row versions visible to a statement or transaction |
| Predicate | Condition selecting a row set, e.g., `WHERE status='confirmed'` |
| Serialization | Outcome equivalent to some serial execution order of transactions |

You do not need to memorize symbols, yet practice stating precisely **who read what, who wrote what, and when each committed** before concluding an anomaly occurred.

### 1.2. Isolation Differs from Atomicity

- **Atomicity**: operations within the same transaction succeed together or roll back together.
- **Isolation**: how concurrent transactions affect one another's visibility and outcomes.
- **Consistency**: invariants and constraints are preserved alongside correct application logic.
- **Durability**: committed changes persist according to the system's durability mechanisms.

An atomic transaction can still participate in **write skew** or a **lost update** under insufficient isolation. Atomicity does not automatically serialize concurrent operations.

## 2. Dirty Read: Reading Uncommitted Changes

A **dirty read** occurs when T1 reads a value written by T2 while **T2 has not yet committed**. T2 might subsequently roll back, leaving T1 acting on data that never became committed state.

Conceptual schedule in an engine that permits dirty reads:

~~~text
Initial state: balance = 1000

T2                                T1
--------------------------------  -------------------------------
BEGIN
UPDATE balance = 900
                                  SELECT balance -> 900
                                  T1 makes decisions based on 900
ROLLBACK

Actual committed value remains 1000.
~~~

The defining feature is that **the read occurs before the `COMMIT` of the transaction producing that value**.

### 2.1. Why Are Dirty Reads Dangerous?

If a billing, alerting, or inventory-dispatch task acts on uncommitted data, it can trigger real-world actions that cannot be "rolled back" alongside the database.

Example:

- T2 temporarily lowers a balance and later rolls back.
- T1 sees the lowered balance and sends a false alert.
- T2 rolls back, yet the alert email has already been sent.

### 2.2. Does PostgreSQL Have Dirty Reads?

**No.** PostgreSQL never lets ordinary transactions read uncommitted row versions written by other transactions. This holds **even when `READ UNCOMMITTED` is specified**: PostgreSQL treats that level identically to `READ COMMITTED`.

This is an important distinction between **the minimum anomalies allowed by the SQL standard** and **PostgreSQL's actual behavior**.

### 2.3. Reading Your Own Changes Is Not a Dirty Read

Inside one transaction:

~~~sql
BEGIN;

UPDATE accounts
SET balance = 900
WHERE account_id = 1;

SELECT balance
FROM accounts
WHERE account_id = 1;

ROLLBACK;
~~~

T1 sees changes made by **T1 itself** prior to commit. That is normal behavior (*read your own writes*), not a dirty read between two transactions.

## 3. Nonrepeatable Read: Re-Reading the Same Row Returns a Different Value

A **nonrepeatable read** occurs when T1 reads a row, T2 commits an update to that row, and T1 reads **the same row** again within **the same transaction** and sees a different value.

~~~text
Initial: account(1).balance = 1000

T1                                     T2
-------------------------------------  -------------------------
BEGIN
SELECT balance -> 1000
                                       BEGIN
                                       UPDATE balance = 900
                                       COMMIT
SELECT balance -> 900
COMMIT
~~~

Both values read by T1 were committed at the time of each statement. Therefore, **a nonrepeatable read is not a dirty read**.

### 3.1. The "Same Transaction" Scope Matters

If T1 reads a row, commits, and later starts a new transaction that sees the updated value, that is normal progression between **two separate transactions**, not the standard definition of a nonrepeatable read.

### 3.2. PostgreSQL READ COMMITTED Permits This Phenomenon

Under `READ COMMITTED`, each normal query statement uses a snapshot as of **the start of that statement**. Two separate SELECT statements inside the same transaction can observe two different committed states.

### 3.3. PostgreSQL REPEATABLE READ Prevents Nonrepeatable Reads

Under `REPEATABLE READ`, normal reads inside the same transaction share a stable transaction snapshot. If T2 commits a modification after T1's snapshot is established, T1 continues seeing the older version on subsequent SELECTs.

This does not block T2 from modifying the row or freeze the entire database. T2 commits normally; T1 simply retains a **consistent snapshot view**.

## 4. Phantom Read: The Set of Matching Rows Changes

A **phantom read** happens when T1 runs a query using a **row-set predicate**, T2 commits a change altering the membership/count of rows matching that predicate, and T1 re-runs the query within the same transaction and gets a different set.

~~~text
Initial:
  SELECT COUNT(*) FROM bookings
  WHERE room_id = 10 AND status = 'confirmed'
  -> 2

T1                                      T2
--------------------------------------  ----------------------------
BEGIN
COUNT(*) -> 2
                                        BEGIN
                                        INSERT matching booking
                                        COMMIT
COUNT(*) -> 3
COMMIT
~~~

### 4.1. How Does a Phantom Differ from a Nonrepeatable Read?

- **Nonrepeatable read:** the value of an already-read row changes.
- **Phantom read:** **the set of rows** matching a predicate changes due to an INSERT/DELETE/UPDATE.

Example:

~~~sql
SELECT *
FROM bookings
WHERE room_id = 10
  AND status = 'confirmed';
~~~

A newly added row appearing in the result set after the first SELECT is a phantom.

### 4.2. Phantoms Do Not Only Come from INSERT

The matching set can change because:

- T2 INSERTs a new row matching the predicate.
- T2 DELETEs a row that previously matched the predicate.
- T2 UPDATEs a non-matching row so it now matches the predicate.
- T2 UPDATEs a matching row so it no longer matches the predicate.

The essence is that **the predicate's result set changes between two reads**.

### 4.3. PostgreSQL REPEATABLE READ Prevents Traditional Phantoms

In PostgreSQL, `REPEATABLE READ` implements snapshot isolation. Two SELECTs with the same predicate inside one transaction will not see new rows committed by other transactions after the snapshot was taken.

This is **stronger than the SQL standard's minimum requirement for REPEATABLE READ**. Still, it is **not enough to prevent every serialization anomaly**, especially write skew.

## 5. Comparison Table of the Three Classic Phenomena

| Question | Dirty Read | Nonrepeatable Read | Phantom Read |
|---|---|---|---|
| Reads another transaction's uncommitted data? | Yes | Not required; typically committed | Not required; typically committed |
| A known row changes value between two reads? | Not the main trait | Yes | Possible, though focus is row set |
| Set of rows matching WHERE changes? | Not the main trait | Not the main trait | Yes |
| Example | Reading balance=900 before writer rolls back | Reading balance 1000 then 900 | `COUNT(bookings)` goes from 2 to 3 |
| PostgreSQL READ COMMITTED? | Prevented | Possible | Possible |
| PostgreSQL REPEATABLE READ? | Prevented | Prevented for snapshot reads | Prevented for snapshot reads |
| PostgreSQL SERIALIZABLE? | Prevented | Prevented | Prevented in valid committed schedules |

**Phantoms and nonrepeatable reads can overlap descriptively when an UPDATE changes whether a row satisfies a predicate.** Classify them to understand causes and controls, rather than forcing complex schedules into a single label.

## 6. MVCC: How PostgreSQL Enables Concurrent Reads and Writes

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. When data is updated, the engine manages row versions alongside transaction and snapshot visibility metadata.

Conceptual model:

~~~text
One account, two logical versions

Version A: balance=1000  [visible to older snapshot]
Version B: balance=900   [visible to newer snapshot after commit]

T1 took snapshot before T2's COMMIT -> sees A
T3 starts query after T2's COMMIT   -> sees B
~~~

This illustrates logical semantics, not the full physical layout of heap tuples, transaction IDs, visibility maps, or VACUUM.

### 6.1. A Snapshot Is Not a Physical Copy of the Database

PostgreSQL does not duplicate the entire database in RAM on every `BEGIN`. A snapshot is lightweight visibility metadata determining which row versions are visible to a transaction or statement.

### 6.2. MVCC Ensures Reads Do Not Block Writes by Default

A standard SELECT can read committed versions without waiting on another transaction currently updating the same row.

Conversely, concurrent updates to the same row wait on **row locks** and undergo isolation-specific concurrency checks.

### 6.3. Isolation Governs Snapshot Scope

- `READ COMMITTED`: fresh snapshot per normal statement.
- `REPEATABLE READ`: transaction-wide snapshot fixed once established.
- `SERIALIZABLE`: snapshot model augmented with dependency tracking to prevent non-serializable committed schedules.

### 6.4. Long-Running Transactions Have Operational Costs

A transaction holding a snapshot open for too long forces PostgreSQL to retain old row versions, hurting VACUUM and causing bloat. **Never turn REPEATABLE READ into a multi-hour transaction just to "freeze results."**

## 7. Isolation Levels Actually Supported by PostgreSQL

PostgreSQL accepts all four SQL standard isolation names, yet implements **three distinct practical behaviors**:

| Requested Isolation | PostgreSQL Behavior | Primary Snapshot / Trait |
|---|---|---|
| `READ UNCOMMITTED` | Equivalent to READ COMMITTED | No dirty reads; per-statement snapshot |
| `READ COMMITTED` | READ COMMITTED | Nonrepeatable/phantom reads possible across statements |
| `REPEATABLE READ` | Snapshot isolation | Stable snapshot reads; no traditional phantoms; write skew possible |
| `SERIALIZABLE` | Serializable Snapshot Isolation (SSI) | Allows commits only when equivalent to a serial order; may abort with 40001 |

### 7.1. Anomaly Matrix

| Phenomenon | READ UNCOMMITTED in PG | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|---|
| Dirty read | No | No | No | No |
| Nonrepeatable read | Possible | Possible | No in snapshot reads | No in valid committed schedules |
| Traditional phantom read | Possible | Possible | No in snapshot reads | No in valid committed schedules |
| Read skew across SELECTs | Possible | Possible | Prevented by stable snapshot | Prevented in valid committed schedules |
| Write skew / serialization anomaly | Possible | Possible | **Possible** | Detected/prevented by abort when needed |
| Unchecked stale read-modify-write | Possible | Possible | Same-row conflict check exists, does not replace all business rules | Needs proper transaction and retries |

Never treat this matrix as a promise that **every operation** becomes automatically safe under higher isolation: constraints, error handling, retries, and multi-step protocols still matter.

### 7.2. READ COMMITTED Is the Standard Default

PostgreSQL defaults to `READ COMMITTED` for normal transactions unless overridden by configuration or statement.

Check:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

`default_transaction_isolation` shows the session default for new transactions; `transaction_isolation` shows the current transaction's level.

### 7.3. Setting Isolation at Transaction Start

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) FROM some_table;

COMMIT;
~~~

Structural example assuming `some_table` exists.

Or:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Queries executed after setting isolation.
COMMIT;
~~~

Set the isolation level **before executing data queries** that share the snapshot. Do not change isolation mid-transaction after running queries/writes that freeze the mode.

## 8. Preparing the Two-Session psql Lab

Practice on a **test PostgreSQL database**, never in production. You need **two separate connections/sessions**, called **Session A (T1)** and **Session B (T2)**. In `psql`, open two terminals connected to the same database.

Use a dedicated schema to avoid colliding with real data. If `isolation_lab` already exists, use another test database or rename the schema rather than deleting non-lab data.

### 8.1. Creating the Schema and Accounts Table

~~~sql
CREATE SCHEMA isolation_lab;

CREATE TABLE isolation_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance NUMERIC(12, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO isolation_lab.accounts (
    account_id, owner_name, balance
)
VALUES
    (1, 'Alice', 1000.00),
    (2, 'Bob',   1000.00);
~~~

### 8.2. Bookings Table for Observing Phantoms

~~~sql
CREATE TABLE isolation_lab.bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL,
    booking_day DATE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'cancelled'))
);
~~~

### 8.3. Inventory Table

~~~sql
CREATE TABLE isolation_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

INSERT INTO isolation_lab.inventory (sku, stock)
VALUES ('BOOK-001', 10);
~~~

### 8.4. On-Call Schedule Table for Write Skew

~~~sql
CREATE TABLE isolation_lab.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO isolation_lab.on_call (
    doctor_id, doctor_name, on_call
)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE);
~~~

Hypothetical business rule: **at least one doctor must always remain on call**. The table above intentionally **has no multi-row constraint enforcing that rule**, so we can observe write skew.

### 8.5. Lab Operating Rules

- Each session starts its own transaction with `BEGIN`; do not execute all steps sequentially in one connection.
- Follow the exact A1 → B1 → A2... order for each example; proceed only after the preceding step finishes.
- If a session blocks on a lock, let the other session COMMIT/ROLLBACK as instructed.
- After every scenario, COMMIT or ROLLBACK all open transactions.
- Reset data only when no lab transaction is actively using it.
- Certain results depend on commit ordering; preserve the interleaving deliberately to observe the phenomenon.
- In GUI tools with connection pooling, confirm Session A and Session B truly use **two independent backend connections**, not two tabs sharing one connection.

## 9. Dirty Read Lab: PostgreSQL Hides Uncommitted Writes

Ensure account 1 has `balance=1000` by resetting **outside lab transactions**:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 9.1. Session A / T1: Write Without Committing

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

-- Do not COMMIT or ROLLBACK yet.
~~~

### 9.2. Session B / T2: Read While T1 Is Open

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
~~~

**Expected result:** T2 sees **1000**, not 900. T2 reads the committed version matching its SELECT snapshot.

### 9.3. Session A Rolls Back

~~~sql
ROLLBACK;
~~~

### 9.4. Session B Reads Again

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

COMMIT;
~~~

The result remains 1000.

### 9.5. Testing READ UNCOMMITTED

Repeat A writing 900 without committing, while Session B uses:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

COMMIT;
~~~

PostgreSQL still **disallows dirty reads**. Practically, this level behaves like READ COMMITTED.

**Never lower isolation to READ UNCOMMITTED expecting to inspect another transaction's uncommitted data in PostgreSQL.**

## 10. Nonrepeatable Read Lab Under READ COMMITTED

Reset data when no transactions are open:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 10.1. Session A / T1 First Read

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Expected: 1000
~~~

### 10.2. Session B / T2 Commits a Change

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

### 10.3. Session A / T1 Reads Again

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Expected: 900

COMMIT;
~~~

Two SELECTs inside **the same transaction T1** return two different values. This is a **nonrepeatable read**.

### 10.4. Did T1 Read Dirty Data?

No. The value 900 was already COMMITTED by T2 before T1's second SELECT. T1 never read uncommitted data.

### 10.5. Why Can One SELECT Differ from the Next SELECT?

Because under READ COMMITTED, each normal SELECT builds a fresh snapshot reflecting transactions committed by the time that statement starts. `BEGIN` does not "freeze" data for the whole transaction.

## 11. Nonrepeatable Read Lab Under REPEATABLE READ

Reset account 1 back to 1000 before running:

~~~sql
UPDATE isolation_lab.accounts
SET balance = 1000
WHERE account_id = 1;
~~~

### 11.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Expected: 1000
~~~

### 11.2. Session B / T2

~~~sql
BEGIN;

UPDATE isolation_lab.accounts
SET balance = 900
WHERE account_id = 1;

COMMIT;
~~~

### 11.3. Session A / T1 Reads Again

~~~sql
SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;
-- Still 1000 in T1's snapshot.

COMMIT;
~~~

Repeating the read still returns 1000. However, **after T1 ends and a new transaction opens**, queries see 900.

### 11.4. When Is the Snapshot Taken?

Under REPEATABLE READ, the snapshot is established when the transaction runs its first statement requiring a snapshot per PostgreSQL rules, **not necessarily at the instant `BEGIN` is sent**. When staging a test, run T1's first SELECT before T2 commits to pin the desired snapshot.

### 11.5. What If T1 Tries to UPDATE the Row Modified by T2?

Under REPEATABLE READ, PostgreSQL rejects the transaction with an error such as:

~~~text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
~~~

Thus, "T1 reads an older snapshot" **does not mean** T1 can blindly overwrite the newer version of the same row and commit. MVCC reads and concurrent writes obey distinct rules.

## 12. Phantom Read Lab Under READ COMMITTED

Ensure no test bookings remain from prior runs (run only after both sessions closed their transactions):

~~~sql
DELETE FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14';
~~~

### 12.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Expected: 0
~~~

### 12.2. Session B / T2

~~~sql
BEGIN;

INSERT INTO isolation_lab.bookings (
    room_id, booking_day, status
)
VALUES (10, DATE '2026-11-14', 'confirmed');

COMMIT;
~~~

### 12.3. Session A / T1 Queries the Same Predicate

~~~sql
SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Expected: 1

COMMIT;
~~~

The set of rows matching `WHERE room_id=10 AND booking_day=... AND status='confirmed'` gained a new member. This is a **phantom read**.

### 12.4. Spotting Phantoms in Reports

A report might:

1. Count 10 approved orders.
2. T2 inserts another approved order.
3. T1 fetches the detail list and sees 11 orders.
4. T1 pairs "count=10" with "list of 11" in the same report output.

If a report runs **multiple SELECTs** that must share one slice of data, READ COMMITTED may be insufficient. Consider REPEATABLE READ for read-only transactions with short scopes.

## 13. Phantom Read Lab Under REPEATABLE READ

Reset test booking data after all old transactions finish:

~~~sql
DELETE FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14';
~~~

### 13.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Expected: 0
~~~

### 13.2. Session B / T2

~~~sql
BEGIN;

INSERT INTO isolation_lab.bookings (
    room_id, booking_day, status
)
VALUES (10, DATE '2026-11-14', 'confirmed');

COMMIT;
~~~

### 13.3. Session A / T1 Reads Again

~~~sql
SELECT COUNT(*) AS confirmed_count
FROM isolation_lab.bookings
WHERE room_id = 10
  AND booking_day = DATE '2026-11-14'
  AND status = 'confirmed';
-- Still 0 in T1's snapshot.

COMMIT;
~~~

This practical demo shows **PostgreSQL REPEATABLE READ prevents traditional phantom reads**.

### 13.4. Did the First SELECT Lock the Predicate?

No. Normal SELECTs under REPEATABLE READ **do not block** T2 from inserting. T2 commits freely; T1 simply does not see T2's row in its earlier snapshot.

This highlights the difference between **snapshot isolation** and imagining "locking every possible row that could match WHERE."

## 14. Phantoms from DELETE or UPDATE

INSERT is not the only statement that shifts a result set.

Suppose T1 reads:

~~~sql
SELECT booking_id
FROM isolation_lab.bookings
WHERE status = 'confirmed';
~~~

Then T2 runs:

~~~sql
UPDATE isolation_lab.bookings
SET status = 'cancelled'
WHERE booking_id = 1;

COMMIT;
~~~

Once T2 commits and T1 re-runs its SELECT under READ COMMITTED, that booking **disappears** from the result set.

Likewise, an UPDATE from `status='draft'` to `'confirmed'` makes a row **appear** in the previously observed predicate.

### 14.1. Never Define a Phantom Narrowly as "Only a Newly Inserted Row"

Any committed change causing the set matching a predicate to change between two reads fits the phantom concept.

### 14.2. Separate Read Semantics from Write Semantics

Under REPEATABLE READ, T1 still sees the old set on reads, yet an UPDATE trying to modify a row changed after T1's snapshot can trigger a conflict. Read stability is not a license to overwrite newer committed data.

## 15. Read Skew: Reading Values from Different Snapshots

**Read skew** (*inconsistent analysis*) happens when a transaction reads logically related data at **different snapshot instants**, producing an aggregate result that never existed in any single consistent committed state.

Suppose:

~~~text
Alice balance = 1000
Bob balance   = 1000
System total  = 2000
~~~

T2 transfers 100 from Alice to Bob **inside one transaction**:

~~~text
Alice = 900
Bob   = 1100
Total = 2000
~~~

### 15.1. Interleaving Causing Read Skew Under READ COMMITTED

~~~text
Time        T1 reading report          T2 transferring funds
----------  ------------------------   --------------------------
t1          BEGIN READ COMMITTED
t2          SELECT Alice -> 1000
t3                                     BEGIN
t4                                     UPDATE Alice -> 900
t5                                     UPDATE Bob -> 1100
t6                                     COMMIT
t7          SELECT Bob -> 1100
t8          T1 sums 1000 + 1100 = 2100
t9          COMMIT
~~~

At no instant did the committed state of both accounts sum to 2100. T1 read **Alice before the transfer** and **Bob after the transfer**.

### 15.2. Is This a Dirty Read?

No. Both `Alice=1000` and `Bob=1100` were committed values at the moment of each of T1's SELECTs.

### 15.3. Is This Related to Nonrepeatable Reads?

Yes. The underlying mechanism is multiple statements in one transaction seeing different snapshots. Read skew specifically emphasizes **multiple pieces of a combined output coming from mismatched points in time**, even without T1 re-reading the same row twice.

### 15.4. Using One Consistent SELECT or REPEATABLE READ

If the report only needs the total balance once, let PostgreSQL compute it in **one statement**:

~~~sql
SELECT SUM(balance) AS total_balance
FROM isolation_lab.accounts;
~~~

A single normal SELECT under READ COMMITTED uses one consistent snapshot for that statement.

If a report needs multiple queries or separate app steps sharing one snapshot, REPEATABLE READ is typically better suited:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 1;

SELECT balance
FROM isolation_lab.accounts
WHERE account_id = 2;

COMMIT;
~~~

Both SELECTs share the same transaction snapshot, avoiding mixing pre- and post-commit states from T2.

## 16. Lost Update: One Task's Update Overwrites Another's

A **lost update** occurs when two tasks start from the same initial value, and one later update **overwrites** the other's change, losing an intended modification.

Suppose initial stock is 10, and two requests both sell one unit.

### 16.1. Unsafe Approach: SELECT Then Write an Absolute Number

~~~text
Initial: stock=10

T1                                 T2
---------------------------------  -----------------------------
SELECT stock -> 10                 SELECT stock -> 10
Compute new stock = 9              Compute new stock = 9
UPDATE stock = 9
COMMIT
                                   UPDATE stock = 9
                                   COMMIT

Outcome: stock=9, despite two sales.
~~~

The flaw is that each request **computes the new value in the app from a stale snapshot** and writes back an absolute constant.

### 16.2. Lost Updates Are Not Nonrepeatable Reads

- Nonrepeatable reads concern **what values are read**.
- Lost updates concern **changes lost** across two writes.

Both can occur in the same workflow, yet they are distinct definitions.

### 16.3. PostgreSQL READ COMMITTED Does Not Prevent Stale Assignments by Default

If two requests follow "read `stock=10`, compute 9, write `SET stock=9`," the second request under READ COMMITTED waits for the lock and then writes 9, losing one decrement.

### 16.4. PostgreSQL REPEATABLE READ Adds Protection for Same-Row Updates

If two REPEATABLE READ transactions start with snapshots before either modifies the row, and then both try to UPDATE the same row, PostgreSQL detects the concurrent update and raises a serialization failure on the second transaction.

**Never claim that same-row lost updates always commit silently under every isolation level.** Specify the DBMS, isolation level, and update SQL pattern.

## 17. Preventing Lost Updates with Atomic UPDATEs

For inventory, a safer pattern **puts the math inside a conditional UPDATE**:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING sku, stock;
~~~

If one row returns, decrementing by one succeeded inside the statement's transaction. If 0 rows return, the SKU does not exist or stock was insufficient.

### 17.1. Why Does This Differ from SELECT Then SET stock=9?

`SET stock = stock - 1` reads and updates the current row version at UPDATE execution time under PostgreSQL's locking/concurrency rules.

Under READ COMMITTED, when an UPDATE waits on another transaction modifying the row, PostgreSQL resolves the row update and re-evaluates the condition against the updated committed row. Thus two decrements of 1 yield 9 and then 8, rather than both writing 9.

### 17.2. CHECK Remains Important

The lab includes:

~~~sql
stock INTEGER NOT NULL CHECK (stock >= 0)
~~~

The constraint rejects negative values if another writer omits `stock >= 1`. Still, CHECK does not track **which order received which stock**, whether a retry duplicated an allocation, or multi-warehouse totals.

### 17.3. Grouping Multiple Changes in One Transaction

When stock allocation must accompany order creation and allocation logging, use a transaction:

~~~sql
BEGIN;

UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;

-- Verify a row was updated before inserting the order.
-- Create order/history rows per real schema.

COMMIT;
~~~

Never commit an order as "successful" when the stock UPDATE affected 0 rows.

### 17.4. Atomic Updates Do Not Replace All Isolation Controls

A single safe row UPDATE does not enforce complex multi-table, multi-row invariants. Rules like "always keep one doctor on call" require different solutions.

## 18. Optimistic Locking: Using Version Columns Against Stale Overwrites

A common technique adds a **version column**. Our lab table has:

~~~sql
version BIGINT NOT NULL DEFAULT 0
~~~

The application reads:

~~~sql
SELECT sku, stock, version
FROM isolation_lab.inventory
WHERE sku = 'BOOK-001';
~~~

Suppose it receives `stock=10` and `version=0`. When writing based on what it read:

~~~sql
UPDATE isolation_lab.inventory
SET stock = 9,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND version = 0
RETURNING stock, version;
~~~

If another transaction incremented `version` first, the UPDATE returns **0 rows** instead of overwriting with stale state.

### 18.1. Every Write Path Must Respect Version

Optimistic locking only works if **every protected writer** checks and increments `version` per protocol. A batch job updating stock directly without incrementing `version` breaks the contract.

### 18.2. What to Do When 0 Rows Return?

- Reload current data.
- Re-evaluate business rules against the new values.
- Decide whether to retry or report a conflict.
- Never blindly resend `stock=9` forever.

### 18.3. Version Is Different from Identity

An identity is a record's identifier. A version is a **logical revision counter** detecting stale updates. Never repurpose an identity column as a version or use `MAX(id)` to infer whether a row changed.

## 19. SELECT FOR UPDATE: Locking Rows When Decisions Depend on Reads

Some workflows must read multiple columns of a row, run logic, and then update. You can use:

~~~sql
BEGIN;

SELECT sku, stock
FROM isolation_lab.inventory
WHERE sku = 'BOOK-001'
FOR UPDATE;

-- Apply logic on the locked row.
-- Then UPDATE within the same transaction.

COMMIT;
~~~

`FOR UPDATE` acquires row locks on selected rows. Other transactions attempting conflicting updates on those rows wait until the lock is released.

### 19.1. Keep Everything in the Same Transaction

If `SELECT FOR UPDATE` runs in one transaction and `UPDATE` runs after that transaction committed, the lock was already released and protection is lost.

### 19.2. Never Hold Locks During External API Calls

Never hold row locks while waiting on a payment provider, email service, or multi-second remote call. That spikes contention and deadlock/timeout risk.

### 19.3. Row Locks Do Not Lock "Future Rows"

If a query:

~~~sql
SELECT *
FROM isolation_lab.bookings
WHERE room_id = 10
FOR UPDATE;
~~~

selects only currently visible existing rows, row locks on those rows **do not prevent another transaction from INSERTing a new booking** for the same `room_id`.

Therefore, `SELECT ... FOR UPDATE` is not a universal substitute for predicate locking or serializability to protect "no rows matching X exist" rules.

### 19.4. Locking a Shared Coordinator Row

One pattern uses a parent/guard row representing the shared resource being protected. If **every writer** locks that coordinator row before checking and writing, operations serialize per protocol.

Details still depend on isolation: under REPEATABLE READ, a fixed snapshot will not see newer changes even after waiting on an unmodified guard row. When using a guard row under READ COMMITTED, acquire the lock **before the decision-making read**; at higher snapshot levels, update the guard row or retry appropriately rather than assuming waiting on a lock refreshes your snapshot.

## 20. Write Skew: Two Transactions Edit Different Rows and Break a Shared Invariant

**Write skew** is a classic serialization anomaly under **snapshot isolation**.

Suppose a hospital has two doctors, An and Bình. Policy: **at least one doctor must be on call**. Both are currently on call.

~~~text
doctor_id=1, An,   on_call=true
doctor_id=2, Bình, on_call=true

Invariant: COUNT(*) WHERE on_call=true >= 1
~~~

Either doctor may go off call if **another doctor** remains on call. Two concurrent transactions run:

~~~text
T1 / An                               T2 / Bình
-----------------------------------   --------------------------------
BEGIN REPEATABLE READ                 BEGIN REPEATABLE READ
COUNT(on_call) -> 2                   COUNT(on_call) -> 2
UPDATE doctor_id=1 -> false           UPDATE doctor_id=2 -> false
COMMIT                                COMMIT

Outcome: both have on_call=false.
~~~

The two UPDATEs touch **two different rows**, so they do not conflict on same-row updates. Both read valid snapshots, each assuming the other would remain on call.

### 20.1. This Is Not a Dirty Read

Neither transaction read uncommitted data from the other.

### 20.2. This Is Not a Nonrepeatable Read or Snapshot Phantom

Each transaction could read once—or re-read and keep seeing its snapshot. Each transaction individually saw internally consistent data.

### 20.3. This Is Not a Same-Row Lost Update

No single row was overwritten by two UPDATEs. Each transaction edited its own row. **A multi-row invariant** was broken.

### 20.4. Why Does REPEATABLE READ Allow It?

PostgreSQL's REPEATABLE READ is snapshot isolation—stronger than READ COMMITTED yet not full serializability. Two transactions reading shared state and writing to **disjoint rows** can produce an outcome incompatible with any valid serial order.

## 21. Write Skew Lab Under REPEATABLE READ

Reset data with no open transactions:

~~~sql
UPDATE isolation_lab.on_call
SET on_call = TRUE
WHERE doctor_id IN (1, 2);
~~~

### 21.1. Session A / T1

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Expected: 2

-- Do not UPDATE/COMMIT yet.
~~~

### 21.2. Session B / T2

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Expected: 2
~~~

**Both SELECTs must complete before either transaction commits**, so both T1 and T2 hold snapshots seeing two doctors on call.

### 21.3. Session A Takes An Off Call

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 21.4. Session B Takes Bình Off Call

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

Both transactions update disjoint rows. Under REPEATABLE READ in this experiment, both commit successfully.

### 21.5. Verifying the Outcome

After both finish:

~~~sql
SELECT doctor_id, doctor_name, on_call
FROM isolation_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining_on_call
FROM isolation_lab.on_call
WHERE on_call;
~~~

Expected `remaining_on_call = 0`: **the "at least one on call" invariant was violated**.

This critical experiment prevents the false conclusion that "REPEATABLE READ prevents phantoms, so all multi-row business rules are safe."

## 22. SERIALIZABLE: Ensuring Outcomes Match Serial Execution

In PostgreSQL, **`SERIALIZABLE`** guarantees that the outcomes of **committed** transactions are equivalent to some serial execution order, provided applications perform proper checks and updates inside their transactions.

PostgreSQL uses **Serializable Snapshot Isolation (SSI)**, tracking read/write dependencies that could produce non-serializable schedules.

### 22.1. Not a Full-Database Lock

Do not picture SERIALIZABLE as running every transaction one by one with zero concurrency. PostgreSQL still runs transactions concurrently; when it detects a dangerous dependency pattern, one transaction is aborted instead of letting both commit.

### 22.2. Serialization Failure Is an Expected Outcome

In a conflicting schedule, PostgreSQL raises:

~~~text
ERROR: could not serialize access due to read/write dependencies
       among transactions
SQLSTATE: 40001
~~~

Exact message wording varies by code path and version; **SQLSTATE 40001** is the reliable signal for applications to recognize serialization failures.

### 22.3. Not Every SERIALIZABLE Transaction Errors

When no dangerous dependency cycle forms, transactions commit normally. When a conflict arises, one transaction aborts so the remaining ones stay serializable.

### 22.4. SERIALIZABLE Does Not Fix Broken Logic Inside a Transaction

If an application **skips checking** how many doctors remain on call and blindly updates both to off call, the database cannot deduce an unexpressed "at least one doctor" invariant from business language.

Isolation ensures schedule equivalence; it does not replace business checks or schema constraints.

## 23. Write Skew Lab Under SERIALIZABLE

Reset the table:

~~~sql
UPDATE isolation_lab.on_call
SET on_call = TRUE
WHERE doctor_id IN (1, 2);
~~~

Run two sessions, changing the isolation level.

### 23.1. Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Expected: 2
~~~

### 23.2. Session B

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;
-- Expected: 2
~~~

### 23.3. Session A Updates An

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
~~~

### 23.4. Session B Updates Bình

~~~sql
UPDATE isolation_lab.on_call
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
~~~

With both reads happening before either update commits, PostgreSQL **prevents both transactions from committing in a way that breaks this write-skew invariant**. One transaction fails with SQLSTATE `40001` at UPDATE or COMMIT depending on interleaving.

### 23.5. Handling the Failed Transaction

If Session B fails, run `ROLLBACK` as needed to return the connection to normal state. Then start a **new transaction** and re-read the on-call count:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_call_count
FROM isolation_lab.on_call
WHERE on_call;

-- If count is only 1, do not take the last doctor off call.
ROLLBACK;
~~~

When the application re-reads and applies the rule properly, the second doctor cannot leave, preserving the invariant.

### 23.6. Critical Condition: Every Write Path Must Follow the Protocol

If one service checks the rule under SERIALIZABLE while another job updates the table directly without checking the invariant, business rules can still break even though transactions are serializable. All writers must share the contract; whenever possible, express invariants directly with constraints.

## 24. SSI and Predicate Locks in PostgreSQL

An easily misunderstood detail: PostgreSQL Serializable Snapshot Isolation tracks **read/write conflicts**, recorded via **predicate locks** shown as `SIReadLock`.

### 24.1. SIReadLock Differs from FOR UPDATE Row Locks

- `SELECT ... FOR UPDATE`: acquires blocking row locks that can make competing writes wait.
- `SIReadLock`: tracks read rows or predicate ranges to detect serialization dependencies; it does not block writers from INSERTing/UPDATEing in that range.

### 24.2. Predicate Locks Can Operate at Multiple Granularities

Depending on query plans and lock memory, PostgreSQL tracks conflicts at row, page, or relation granularity. Thus query plans and indexing can affect serialization abort rates in a workload.

### 24.3. Do Indexes Help Reduce Serialization Failures?

Proper indexes can narrow the rows touched by a query, reducing unnecessary false-positive conflicts and improving performance. Still, indexes **never eliminate the need for retries** and cannot guarantee `40001` will never occur.

### 24.4. Avoid "Turning SERIALIZABLE into FOR UPDATE Everywhere"

Row locking works well for certain rules, yet cannot cover arbitrary predicates—especially when protected rows **do not exist yet**. PostgreSQL SSI detects complex read/write conflict graphs beyond single-row locks.

## 25. Retrying the Entire Transaction on SQLSTATE 40001

This is a **mandatory design requirement** whenever an application relies on SERIALIZABLE and expects to recover from serialization failures.

### 25.1. Why Retry the Whole Transaction?

Suppose the initial transaction:

1. Read `on_call` count = 2.
2. Decided to take doctor A off call.
3. Ran `UPDATE A`.
4. Hit `40001` at `COMMIT`.

If you only replay step 3's UPDATE, the decision "another doctor is still on call" rested on a stale snapshot—the exact reason the abort happened.

Proper retry must:

1. Start a **new** transaction.
2. Re-read current data under a fresh snapshot.
3. Re-check business preconditions.
4. Recompute the operation.
5. Execute SQL and COMMIT.
6. Retry with a cap if `40001` recurs.

### 25.2. Pseudocode

~~~text
for attempt = 1 .. MAX_ATTEMPTS:
    begin SERIALIZABLE transaction
    try:
        read current state
        verify business preconditions
        apply changes
        COMMIT
        return success
    catch SQLSTATE 40001:
        ROLLBACK if needed
        backoff with jitter
        continue with a NEW transaction
    catch other error:
        ROLLBACK
        propagate or handle as appropriate

raise "transaction could not complete after retries"
~~~

### 25.3. Bounded Retries

Never loop infinitely under heavy contention. Require:

- A maximum attempt count.
- Backoff with jitter.
- An overall request deadline.
- Monitoring of `40001` rates.
- Reviewing overly long transactions or hot contention spots.

### 25.4. Catching Errors at COMMIT

A serialization failure can surface **at commit time**, even when all prior SELECT/UPDATE statements succeeded without error. Transaction wrapper code must catch errors around the **entire transaction including COMMIT**.

### 25.5. Never Blindly Retry External Side Effects

If an email was sent, a payment API was called, or a non-idempotent event was emitted before COMMIT failed, retrying the whole workflow can duplicate external actions.

Use patterns such as:

- Idempotency keys.
- Outbox/inbox patterns.
- Emitting external side effects post-commit when appropriate.
- Webhook/retry handling with business keys.
- Reconciliation between PostgreSQL and external systems.

A PostgreSQL rollback **never undoes** an already sent email or an external payment charge.

## 26. Deadlocks vs. Serialization Failures

Another distinct scenario is a **deadlock**:

~~~text
T1 holds lock on row A, waits for row B.
T2 holds lock on row B, waits for row A.
Neither can proceed without intervention.
~~~

PostgreSQL detects deadlocks and aborts one transaction.

### 26.1. Distinct SQLSTATE Codes

| Scenario | SQLSTATE | Meaning |
|---|---|---|
| Serialization failure | `40001` | Cannot commit transaction while preserving serializability / snapshot guarantees |
| Deadlock detected | `40P01` | Lock wait cycle prevents progress |
| Lock not available | `55P03` | Could not acquire lock under `NOWAIT` / `lock_timeout` |
| Unique violation | `23505` | Unique constraint/index collision |
| Exclusion violation | `23P01` | Exclusion constraint violation |

### 26.2. Deadlocks Can Occur Across Many Isolation Levels

Using READ COMMITTED does not make you immune to deadlocks. Two UPDATEs locking rows in opposite orders can deadlock.

### 26.3. Reducing Deadlocks with Consistent Lock Ordering

For concurrent A→B and B→A transfers, a protocol can require locking the lower account ID first, then the higher ID. That eliminates a common deadlock source.

### 26.4. Retrying Deadlocks

Applications often need bounded full-transaction retries for `40P01` when safe and idempotent. Still, **never retry every SQLSTATE**: a unique violation from an intentionally duplicated key requires business error handling rather than endless retries.

## 27. Dirty Writes: Two Transactions Overwriting Uncommitted Data

A **dirty write** happens if T2 overwrites a value **being written by an uncommitted T1**, corrupting rollback or write ordering.

In PostgreSQL, concurrent UPDATEs/DELETEs on the same row are coordinated via row locking. A transaction cannot simply overwrite another transaction's uncommitted row version while both commit or roll back freely.

### 27.1. Lock-Wait Scenario

~~~text
T1: BEGIN
T1: UPDATE account(1)
    (holds row lock)

T2: BEGIN
T2: UPDATE account(1)
    (must wait for T1)

T1: COMMIT or ROLLBACK
T2: proceeds or errors depending on isolation/concurrency
~~~

### 27.2. Dirty Writes Differ from Lost Updates

- **Dirty write:** overwriting **uncommitted** data.
- **Lost update:** losing an already-applied change when a task overwrites using stale values.

PostgreSQL prevents dirty writes directly via locking, yet unsafe read–modify–write logic under READ COMMITTED can still cause lost updates.

## 28. Read-Only Transactions Also Need Appropriate Isolation

Read-only (SELECT-only) transactions are not immune to concurrency issues.

### 28.1. READ COMMITTED for a Single Standalone Query

If an API executes only:

~~~sql
SELECT SUM(balance)
FROM isolation_lab.accounts;
~~~

and returns one result, READ COMMITTED's per-statement snapshot gives a consistent point-in-time slice for that query.

### 28.2. REPEATABLE READ for Multi-Step Reports

If an API runs multiple SELECTs to assemble a point-in-time consistent report:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*)
FROM isolation_lab.accounts;

SELECT SUM(balance)
FROM isolation_lab.accounts;

COMMIT;
~~~

Both queries share one snapshot, avoiding read skew across statements.

### 28.3. READ ONLY Still Has Operational Impact

Long read-only transactions still pin snapshots and delay VACUUM. For heavy reporting, consider data modeling, batching, and dedicated analytics replicas/pipelines.

### 28.4. SERIALIZABLE READ ONLY DEFERRABLE

PostgreSQL supports:

~~~sql
BEGIN TRANSACTION
ISOLATION LEVEL SERIALIZABLE
READ ONLY
DEFERRABLE;

SELECT COUNT(*)
FROM isolation_lab.accounts;

COMMIT;
~~~

Such a transaction may **wait until a safe snapshot is available**. Once established, it executes read-only queries with serializable guarantees without encountering normal serialization failures.

This is not a flag to enable on every SELECT. It fits read-only reports needing a serializable snapshot that can tolerate an initial wait.

## 29. READ COMMITTED and UPDATE Behavior Under Contention

Under READ COMMITTED, SELECT and UPDATE do not always behave like a frozen snapshot scan.

Suppose two transactions both decrement stock:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;
~~~

When an UPDATE waits because another transaction is modifying the row, PostgreSQL fetches the newly committed row version and **re-evaluates the WHERE condition** before updating.

That makes atomic updates behave very differently from:

~~~text
1. SELECT stock into app.
2. Compute new_stock from read value.
3. UPDATE stock = new_stock.
~~~

### 29.1. Do Not Assume "READ COMMITTED Protects Every Update"

It coordinates concurrent updates on the same row, yet does not know business intent. `SET stock=9` still overwrites another transaction's decrement if code computes from stale reads.

### 29.2. Do Not Assume Every Part of an UPDATE Statement Refreshes to a New Snapshot

UPDATE statements follow specific visibility and row-conflict rules. If a query mixes multi-table reads, subqueries, and contended row updates, check PostgreSQL semantics carefully and test real interleaving.

For sensitive workflows, favor simple protocols with explicit constraints, locks, and concurrency tests over guessing planner behavior.

## 30. When Constraints Are Stronger Than Raising Isolation

Many data invariants belong directly in PostgreSQL constraints:

### 30.1. Preventing Duplicate Order Codes

~~~sql
CREATE TABLE isolation_lab.external_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT NOT NULL UNIQUE
);
~~~

If two transactions insert the same `external_code`, the `UNIQUE` constraint prevents duplicates. Application pre-checks never replace `UNIQUE` under concurrency.

### 30.2. Non-Negative Inventory

The lab already has:

~~~sql
stock INTEGER NOT NULL CHECK (stock >= 0)
~~~

CHECK enforces the bound, though it does not replace atomic UPDATEs or order allocation tracking.

### 30.3. Referential Integrity

Foreign keys ensure orders reference existing customers even with concurrent writers. Still, FKs do not enforce authorization or workflow completeness.

### 30.4. Preventing Overlapping Booking Ranges

PostgreSQL supports **exclusion constraints** with range types/GiST to enforce "no two confirmed bookings overlap for the same room" when modeled appropriately.

An application-side `SELECT COUNT(*) WHERE NOT EXISTS ...` cannot prevent races on its own. Exclusion constraints outperform hand-rolled select-then-insert checks.

### 30.5. No Single-Row Constraint Covers Every Multi-Row Invariant

"At least one doctor on call" depends on **multiple rows**. A single-row CHECK on `on_call` cannot express the table-wide invariant.

When needed, combine serializable transactions, guard-row locking protocols, or schema redesign to anchor the invariant on a stronger entity/constraint.

## 31. SERIALIZABLE Does Not Replace Authorization or Idempotency

A serializable schedule only ensures outcomes match some valid serial order. It **never verifies whether a user is authorized to perform an action**.

For instance, if a service lets any user update someone else's `account_id`, SERIALIZABLE will happily commit an unauthorized update unless permission checks exist.

Similarly, retrying a "create order" request can create two orders unless an idempotency key or unique business key exists.

### 31.1. Authorization

Validate user/tenant/role at the API/domain layer, reinforced with PostgreSQL RLS/`GRANT`.

### 31.2. Idempotency

When a request is retried after a timeout, you need a way to recognize "already processed" and avoid duplicate writes. A unique constraint on `idempotency_key` forms part of the solution.

### 31.3. External Systems

Payment providers, email, message buses, and third-party APIs sit outside PostgreSQL's commit/rollback scope. Use outboxes, event replay, and reconciliation.

### 31.4. Domain Correctness

A serializable transaction can still apply a buggy discount formula. Isolation never replaces domain logic testing.

## 32. Isolation Levels and Latency/Throughput

Stronger isolation increases safety for certain workloads, though raising isolation is not free.

| Level | Primary Benefit | Costs / Risks to Weigh |
|---|---|---|
| READ COMMITTED | Flexible, standard, per-statement snapshots | Susceptible to nonrepeatable/phantom/read skew across statements |
| REPEATABLE READ | Stable transaction snapshot; prevents traditional phantoms | Long snapshots; UPDATE conflicts; write skew still possible |
| SERIALIZABLE | Detects serialization anomalies; serializable commits | May abort with 40001; needs retries; contention and SSI overhead |
| SERIALIZABLE READ ONLY DEFERRABLE | Safe snapshot for read-only reports | Initial wait for a safe snapshot |

### 32.1. SERIALIZABLE Can Increase Retries

When many transactions read an overlapping predicate and write related rows, SSI may abort transactions frequently. Without retries, users see transient failures.

### 32.2. Long Transactions Amplify Contention

A transaction reading and processing for minutes accumulates read/write dependencies, increasing contention and hurting VACUUM. Keep transactions **short, scoped strictly to atomic steps, and free of external service calls while holding locks**.

### 32.3. Never Lower Isolation to Hide Data Races

Dropping from REPEATABLE READ to READ COMMITTED may reduce `40001` errors, yet if the business requires serializable correctness, doing so merely hides bugs by allowing invalid outcomes to commit.

Base decisions on invariants and concurrency strategy, not simply current error counts.

## 33. Observing Locks and Transactions in PostgreSQL

With sufficient privileges, inspect live activity:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

### 33.1. Signals to Watch

- Prolonged `state='idle in transaction'`.
- `wait_event_type='Lock'` indicating a backend waiting on a lock.
- Many long-lived open transactions.
- `40001` or `40P01` rates in application logs and metrics.

### 33.2. pg_locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
~~~

This gives a simple view of **the current backend's** locks, not a full lock-wait dependency analyzer.

### 33.3. Identifying Blocking Backends

PostgreSQL provides:

~~~sql
SELECT pg_blocking_pids(pg_backend_pid()) AS blockers;
~~~

When run in an **unblocked** session, it returns an empty array. During debugging, invoke it for the target blocked PID when permissions allow.

### 33.4. Deadlock Counter

~~~sql
SELECT
    datname,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`deadlocks` tracks cumulative deadlocks, not SSI serialization failures. Track `40001` via application logs/metrics.

### 33.5. Do Not Misread pg_stat_database_conflicts

Recovery/standby conflict statistics are not a count of primary SSI serialization failures. Use the right observability source for the question.

## 34. Concurrency Test Scenarios Worth Having

Sequential unit tests miss concurrency anomalies. Add **integration tests using at least two real PostgreSQL connections**.

### 34.1. Dirty Read Test

T1 writes without committing; T2 runs SELECT under READ UNCOMMITTED / READ COMMITTED. Assert T2 does not see T1's uncommitted change.

### 34.2. Nonrepeatable Read Test

T1 under READ COMMITTED reads a row; T2 updates and commits; T1 reads again. Assert the two values differ.

Repeat under REPEATABLE READ with the same snapshot ordering: T1 does not see the newer version in normal SELECTs.

### 34.3. Phantom Test

T1 counts rows matching a predicate; T2 inserts and commits a matching row; T1 counts again. Assert READ COMMITTED sees the change while REPEATABLE READ does not within its snapshot.

### 34.4. Lost Update Test

Two workers read `stock=10` and both write `stock=9`. Verify the test catches `stock=9` after two accepted orders under an unsafe protocol.

Then switch to atomic conditional UPDATE and verify `stock=8` or that one request fails cleanly for insufficient stock, depending on initial quantity.

### 34.5. Write Skew Test

T1 and T2 both read `on_call=2` and update disjoint rows. Verify REPEATABLE READ lets both commit while SERIALIZABLE prevents both from committing an invariant-breaking schedule.

### 34.6. Retry Test

Induce a `40001` schedule; verify the app retries the entire transaction and re-evaluates preconditions. Test retry limits, idempotency, and COMMIT exceptions.

### 34.7. Deadlock Test

Two transactions lock two rows in opposite orders to verify `40P01` handling. Never run deadlock tests on shared or production databases.

## 35. A Systematic Process for Real-World Concurrency Design

When facing concurrency bugs, never pick isolation by intuition. Follow these steps:

1. **State the invariant.** E.g., non-negative stock, non-overlapping bookings, at least one doctor on call.
2. **Identify the observation scope.** Single row, row set, or multiple tables?
3. **Draw the T1/T2 schedule.** Who reads what, who writes what, and when do commits occur?
4. **Classify the anomaly.** Dirty/nonrepeatable/phantom read, lost update, read skew, or write skew?
5. **Look for direct constraints.** `UNIQUE`, `FK`, `CHECK`, `EXCLUDE` where applicable.
6. **Consider one atomic SQL statement.** `UPDATE ... WHERE condition RETURNING` often handles single-row stock cleanly.
7. **Consider optimistic versioning** when UI/services read a record and edit over a longer window.
8. **Consider row locks** when checking and updating known rows with a shared writer protocol.
9. **Use REPEATABLE READ** for reports or repeated reads requiring a stable snapshot.
10. **Use SERIALIZABLE** when multi-row invariants risk write skew and simpler mechanisms do not fit.
11. **Design retries** for `40001`/`40P01`, covering COMMIT and external side effects.
12. **Measure latency/contention** and bound transaction duration.
13. **Write two-session integration tests** to lock in expectations.
14. **Audit every write path**: APIs, workers, batch imports, admin scripts.
15. **Monitor production** and alert on spikes in retries, deadlocks, or idle transactions.

The best design is not "highest isolation everywhere," but the **simplest solution that protects the invariant under real load and operations**.

## 36. Common Misconceptions

### 36.1. "READ UNCOMMITTED in PostgreSQL Allows Reading Uncommitted Data"

**False.** PostgreSQL treats it like READ COMMITTED; cross-transaction dirty reads do not happen.

### 36.2. "No Dirty Reads Means All Reports Are Consistent"

**False.** READ COMMITTED still allows nonrepeatable reads, phantoms, and read skew across multiple SELECTs.

### 36.3. "A Nonrepeatable Read Reads Uncommitted Values"

**False.** In a classic nonrepeatable read, the second read sees a **committed** value from another transaction.

### 36.4. "Phantoms Only Come from INSERT"

**Incomplete.** DELETE or UPDATE changing predicate membership also produces phantoms.

### 36.5. "PostgreSQL REPEATABLE READ Has Phantoms Like the SQL Standard Minimum"

**False for PostgreSQL.** Its snapshot isolation prevents traditional phantoms.

### 36.6. "Because REPEATABLE READ Prevents Phantoms, It Equals SERIALIZABLE"

**False.** Write skew can still happen.

### 36.7. "A Single SELECT Under READ COMMITTED Reads Rows at Arbitrary Commit Times"

**False as usually misunderstood.** One SELECT uses one statement-start snapshot; read skew typically occurs across **multiple statements**.

### 36.8. "BEGIN REPEATABLE READ Always Fixes the Snapshot Before the First SELECT"

**Not necessarily.** The snapshot is established when the transaction executes its first snapshot-needing operation per PostgreSQL semantics.

### 36.9. "READ COMMITTED Prevents Lost Updates Because of Row Locks"

**Insufficient.** Stale read–modify–write assigning absolute values still loses updates.

### 36.10. "READ COMMITTED Always Causes Two SET stock=stock-1 Statements to Overwrite Each Other"

**False.** Atomic relative UPDATEs use current row values and recheck predicates under row locking, unlike writing stale app-computed constants.

### 36.11. "SELECT FOR UPDATE Locks Nonexistent Future Rows"

**False.** Row locks on existing rows are not predicate locks blocking future INSERTs.

### 36.12. "Dirty Writes and Lost Updates Are the Same Anomaly"

**False.** Dirty writes overwrite uncommitted changes; lost updates drop committed updates via unsafe update protocols.

### 36.13. "Write Skew Requires Two Transactions Writing the Same Row"

**False.** A hallmark of write skew is reading a shared dependency yet writing **disjoint rows**.

### 36.14. "SERIALIZABLE Executes Every Transaction Serially on Disk"

**False.** PostgreSQL runs transactions concurrently using SSI and aborts only when necessary.

### 36.15. "SQLSTATE 40001 Is a PostgreSQL Bug"

**False.** It is an expected concurrency signal applications must handle under snapshot/serializable isolation.

### 36.16. "On 40001, Just Re-Run the Final UPDATE"

**False.** Business decisions came from an obsolete snapshot; retry the **entire transaction**.

### 36.17. "Serialization Failures and Deadlocks Are Identical"

**False.** They map to `40001` and `40P01` respectively with different causes, even though both often warrant retries.

### 36.18. "Read-Only Transactions Need No Isolation Thought"

**False.** Multi-SELECT reports can suffer read skew under READ COMMITTED.

### 36.19. "Constraints Are Unnecessary Once SERIALIZABLE Is Enabled"

**False.** Isolation does not infer valid domains, unique keys, or foreign keys.

### 36.20. "Retrying Transactions Means Payment APIs Can Be Called Infinitely"

**False.** External side effects require idempotency and dedicated integration patterns.

### 36.21. "Higher Isolation Always Increases Throughput and Reduces Lock Waits"

**False.** Stronger isolation can increase aborts, retries, and tracking overhead. Benchmark real workloads.

### 36.22. "Single-Connection Unit Tests Suffice to Catch Concurrency Bugs"

**False.** Multi-connection interleaving is needed to reproduce anomalies.

## 37. Hands-On Exercises

### Exercise 1 — Classifying Dirty Reads

T2 updates `balance=900` without committing. T1 reads 900, and then T2 rolls back. What is this phenomenon called?

**Answer:** Dirty read.

### Exercise 2 — Dirty Reads in PostgreSQL

Does `BEGIN ISOLATION LEVEL READ UNCOMMITTED` let T1 see T2's uncommitted UPDATE?

**Answer:** No. In PostgreSQL, that level behaves like READ COMMITTED.

### Exercise 3 — Nonrepeatable Read

T1 reads `balance=1000`. T2 updates to 900 and commits. T1 re-reads `balance=900` in the same transaction. What phenomenon is this?

**Answer:** Nonrepeatable read.

### Exercise 4 — Distinguishing Reads Across Two Transactions

T1 runs SELECT and commits; later, a new transaction runs SELECT and sees a different value. Is this a classic nonrepeatable read?

**Hint:** No, because the second read occurred in a different transaction.

### Exercise 5 — Phantoms

T1 runs `SELECT COUNT(bookings WHERE confirmed)=5`. T2 inserts a confirmed booking and commits. T1 re-runs and sees 6. What phenomenon is this?

**Answer:** Phantom read.

### Exercise 6 — Phantoms via UPDATE

T2 updates a booking's status from `draft` to `confirmed`, increasing the row count seen by T1's `confirmed` predicate SELECT. Can this be a phantom?

**Hint:** Yes.

### Exercise 7 — PostgreSQL REPEATABLE READ

Does PostgreSQL REPEATABLE READ see a newly committed booking created after T1's snapshot on a second SELECT?

**Answer:** Not in normal SELECTs within the same transaction.

### Exercise 8 — Distinguishing REPEATABLE READ and SERIALIZABLE

REPEATABLE READ prevents traditional phantoms; why is it still insufficient for all multi-row invariants?

**Hint:** Write skew and serialization anomalies can still occur.

### Exercise 9 — Read Skew

T1 reads Alice's balance before a transfer and Bob's balance after the transfer; the sum never existed in any consistent committed state. Name the anomaly.

**Answer:** Read skew.

### Exercise 10 — One SELECT or Two SELECTs?

For a total balance report, why does a single `SELECT SUM(balance)` avoid read skew that occurs when an app reads each account in two separate queries?

**Hint:** A single normal SELECT uses one statement snapshot.

### Exercise 11 — Lost Update

Two requests read `stock=10`, both compute `stock_new=9`, and both write 9. Why is ending at `stock=9` wrong if both sales succeeded?

**Hint:** One decrement was lost.

### Exercise 12 — Atomic Update

Write SQL to decrement stock by one only if sufficient stock exists:

~~~sql
UPDATE isolation_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock >= 1
RETURNING stock;
~~~

**Hint:** Rely on `RETURNING` row count rather than assuming every UPDATE succeeded.

### Exercise 13 — Optimistic Locking

An application reads `version=2`. Another writer incremented it to `version=3`. What will an UPDATE with `WHERE version=2` do?

**Hint:** Returns 0 rows if no matching row remains, letting the application handle the conflict.

### Exercise 14 — FOR UPDATE

Does `SELECT ... FOR UPDATE` prevent a new INSERT from creating a matching row if no row existed beforehand?

**Answer:** Not automatically.

### Exercise 15 — Dirty Write

T1 is updating a row without committing; T2 tries to update the same row. Does PostgreSQL let T2 overwrite directly without waiting on locks?

**Hint:** No; row locking coordinates concurrent updates.

### Exercise 16 — On-Call Write Skew

Both An and Bình are on call. Each reads `count=2` and updates their own row to `false`. Why do two commits under REPEATABLE READ break the invariant?

**Hint:** Both transactions acted on stale snapshots and wrote disjoint rows.

### Exercise 17 — SERIALIZABLE Write Skew

Repeat Exercise 16 under SERIALIZABLE. What must happen so PostgreSQL does not let both commit a non-serializable schedule?

**Hint:** At least one transaction is aborted with `40001`.

### Exercise 18 — Proper Retry

If `40001` happens at COMMIT after reading data and running an UPDATE, is retrying only the UPDATE enough?

**Answer:** No. Retry the entire transaction, re-read, and re-decide.

### Exercise 19 — External Side Effects

A transaction sends an email and then COMMIT fails with `40001`. Why can uncontrolled retries send two emails?

**Hint:** Emails do not roll back with the database; use outbox/idempotency.

### Exercise 20 — Deadlocks

T1 locks A and waits for B; T2 locks B and waits for A. What phenomenon is this, and what is its typical SQLSTATE?

**Answer:** Deadlock, SQLSTATE `40P01`.

### Exercise 21 — UNIQUE

Two transactions check that an order code does not exist and then INSERT. Why is pre-checking with SELECT alone insufficient?

**Hint:** Race condition; use a `UNIQUE` constraint and handle `23505`.

### Exercise 22 — SSI

Does `SIReadLock` under SERIALIZABLE always block other transactions from INSERTing matching rows immediately?

**Hint:** No; it tracks conflict dependencies to detect non-serializable schedules.

### Exercise 23 — READ ONLY DEFERRABLE

When should you consider `SERIALIZABLE READ ONLY DEFERRABLE`?

**Hint:** Read-only reports needing a safe serializable snapshot and willing to wait initially.

### Exercise 24 — Long Transactions

Why can a long-open REPEATABLE READ transaction impact VACUUM?

**Hint:** Old snapshots force retaining dead row versions still visible to them.

### Exercise 25 — Lock Ordering

If two transactions transfer between accounts 1 and 2, why does agreeing to always lock the smaller ID first help?

**Hint:** Reduces lock-wait cycles that cause deadlocks.

### Exercise 26 — Isolation Level by Goal

Pick the main solution for each scenario:

| Scenario | Suggestion |
|---|---|
| One UPDATE decrementing single-row stock | Atomic UPDATE + CHECK |
| Reading multiple report sections from one slice | REPEATABLE READ READ ONLY |
| Two transactions protecting a complex multi-row invariant | SERIALIZABLE or proper locking protocol |
| Preventing duplicate emails | UNIQUE |
| UI submitting edits from stale reads | Optimistic version |
| Calling an external payment provider | Idempotency + workflow/outbox |

### Exercise 27 — Matching SQLSTATE Codes

Match `40001`, `40P01`, `23505`, and `55P03` to serialization, deadlock, unique violation, and lock not available.

### Exercise 28 — Writing a Schedule

Write a T1/T2 timeline illustrating a nonrepeatable read under READ COMMITTED, including BEGIN, SELECT, UPDATE, and COMMIT. Mark the point where T2 commits before T1's second SELECT.

### Exercise 29 — Two Real Sessions

Why does running A1, B1, A2 sequentially inside **the same connection** fail to demonstrate two independent concurrent transactions?

**Hint:** One connection cannot represent two concurrent transactions interleaved that way.

### Exercise 30 — Protecting Every Writer

If an API uses SERIALIZABLE while an admin script bypasses invariant checks with a raw UPDATE, is the rule fully protected?

**Hint:** No. Every write path must obey the same rules and permissions; express invariants as DB constraints whenever possible.

## 38. Quick Reference Table

| Topic | Key Point |
|---|---|
| Dirty read | Reading uncommitted data from another transaction |
| Does PostgreSQL allow dirty reads? | No, even under READ UNCOMMITTED |
| Nonrepeatable read | Re-reading the same row in one transaction sees a different value |
| Phantom read | Row set matching a predicate changes between reads |
| Read skew | Multiple values read from different commit slices |
| Lost update | A change lost due to overwriting from stale data |
| Dirty write | Overwriting another transaction's uncommitted change |
| Write skew | Transactions read shared condition, write disjoint rows, break invariant |
| PostgreSQL READ UNCOMMITTED | Behaves like READ COMMITTED |
| PostgreSQL READ COMMITTED | Per-statement snapshot |
| PostgreSQL REPEATABLE READ | Transaction snapshot, prevents traditional phantoms |
| Does PostgreSQL REPEATABLE READ allow write skew? | Possible |
| PostgreSQL SERIALIZABLE | SSI; disallows commits violating serializability |
| Serialization failure | SQLSTATE 40001 |
| Deadlock | SQLSTATE 40P01 |
| Lock not available | SQLSTATE 55P03 |
| Unique violation | SQLSTATE 23505 |
| Row lock FOR UPDATE | Locks selected rows, does not block all future phantoms |
| Atomic stock update | `UPDATE stock=stock-qty WHERE stock>=qty RETURNING` |
| Optimistic locking | `WHERE version=old_version`, check row count |
| Multi-SELECT consistent report | REPEATABLE READ READ ONLY |
| Serializable read-only safe snapshot | SERIALIZABLE READ ONLY DEFERRABLE |
| Retrying after 40001 | Retry **entire transaction** and re-decide |
| External effects | Idempotency / outbox / reconciliation |
| Protecting uniqueness | UNIQUE constraint, not pre-check alone |
| Complex multi-row invariants | SERIALIZABLE or proper synchronization protocol |
| Long transactions | Snapshot / lock contention / VACUUM impact |
| Testing anomalies | Two real sessions with intentional interleaving |

---

## Summary

**Dirty reads, nonrepeatable reads, and phantom reads** describe three distinct **data-visibility** issues when transactions interleave. Dirty reads read uncommitted values; nonrepeatable reads see the same row change between reads; phantom reads see **the set of rows** matching a predicate change. PostgreSQL disallows dirty reads even under READ UNCOMMITTED, while READ COMMITTED still allows nonrepeatable reads and phantoms across statements.

Under **REPEATABLE READ**, PostgreSQL provides a transaction-wide snapshot preventing nonrepeatable reads and traditional phantoms. However, that is **not equivalent to SERIALIZABLE**: **write skew** can still occur when two transactions read a shared invariant and update disjoint rows. **SERIALIZABLE/SSI** eliminates that class of serialization anomaly by running transactions concurrently and aborting one when necessary, typically via **SQLSTATE 40001**.

In real applications, combine isolation levels with **constraints, atomic UPDATEs, optimistic versions, row locks, full-transaction retries, and idempotency**. For single-row rules, conditional SQL can be simpler and faster than pushing the whole workload to SERIALIZABLE; for multi-row invariants hard to express as constraints, SERIALIZABLE or a strict coordination protocol may be required.

Above all, **identify which data must always hold true after COMMIT, trace interleaved transaction schedules, and test on independent connections**. Understanding MVCC, snapshots, and anomalies beyond the classic three lets you choose the right mechanisms so PostgreSQL and your application stay consistent under concurrent load.
