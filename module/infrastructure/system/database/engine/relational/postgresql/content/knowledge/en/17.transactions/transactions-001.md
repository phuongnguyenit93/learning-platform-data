# BEGIN, COMMIT, ROLLBACK, and the Transaction Lifecycle in PostgreSQL

## 1. What Problem Do Transactions Solve?

Suppose a system transfers **100 currency units** from account A to account B. From a business perspective, this operation is not a single update statement:

1. Verify that accounts A and B are still valid.
2. Subtract 100 from A's balance.
3. Add 100 to B's balance.
4. Record the transfer history entry.

If the application stops after subtracting the amount but before adding it, a system without a transaction mechanism could leave corrupted data: the total balance across the two accounts drops, while the business transaction remains incomplete.

A **transaction** groups related changes into a single unit of work:

- **`BEGIN`**: opens an explicit transaction.
- **`COMMIT`**: instructs PostgreSQL to finalize the transaction and make its changes effective.
- **`ROLLBACK`**: discards the transaction's uncommitted changes.

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

The snippet above only illustrates transaction boundaries; a **production-safe** transfer also needs to check account existence, balance, affected row counts, concurrent access scenarios, and duplicate request tracking. These steps will be built up gradually throughout this lesson.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between `BEGIN`, `COMMIT`, `ROLLBACK`, and autocommit mode.
2. Explain the **lifecycle** of a transaction from start, statement execution, success or failure, through completion.
3. Recognize the **aborted** transaction state and handle the `current transaction is aborted` error.
4. Use `SAVEPOINT` for valid partial rollbacks.
5. Understand the relationship between transactions, ACID, MVCC, locks, and isolation levels.
6. Test two concurrent sessions to observe uncommitted data and lock waits.
7. Identify the right place to manage transactions in applications/JDBC and connection pools.
8. Avoid long-running transactions, retry bugs, and inconsistency when external systems outside the database are involved.
9. Use hands-on SQL to verify changes after COMMIT and ROLLBACK.

> **Scope:** all data-writing examples must be run in a lab database. Do not use production accounts or real bank accounts; do not experiment with holding locks or blocking transactions in production.

---

## 2. Transactions and the Four ACID Properties

A transaction can be thought of as the **success or failure boundary** of a business unit of work. The four ACID properties are commonly used to describe its key guarantees:

| Property | Practical Meaning | Example |
|---|---|---|
| **Atomicity** | Either all changes in the transaction are accepted, or none of them are kept | Never debit A without also crediting B |
| **Consistency** | A transaction must transition the database from one valid state to another according to **defined constraints** | `CHECK(balance >= 0)` prevents negative balances |
| **Isolation** | Defines how concurrent transactions see and interact with each other | Another session cannot read an uncommitted balance |
| **Durability** | After a successful commit under the system's configured guarantees, data must survive failures covered by those guarantees | A confirmed committed transaction does not vanish just because the client connection closes |

### 2.1. ACID Does Not Replace Business Design

A transaction containing two SQL statements **does not by itself prove** that the transfer logic is correct. If the application:

- Transfers a negative amount.
- Transfers to a nonexistent account.
- Ignores an `UPDATE 0` result.
- Records two duplicate requests with the same `request_key`.
- Reads a balance without locking and then updates based on stale data.

then business invariants can still be violated even when using `BEGIN` and `COMMIT`.

**Consistency** requires database constraints (PK, FK, CHECK, UNIQUE, etc.) combined with application logic, an appropriate isolation level, and proper error handling. PostgreSQL cannot infer every business invariant on its own.

### 2.2. Isolation Does Not Mean Every Transaction Is SERIALIZABLE

PostgreSQL's default isolation level is typically **READ COMMITTED**. It prevents dirty reads, yet two `SELECT` statements within the same transaction can see different results if another session commits between the two reads. For stronger guarantees, you must choose an appropriate isolation level or locking/concurrency-control technique.

### 2.3. Durability Depends on Both Configuration and Infrastructure

PostgreSQL uses WAL and durability mechanisms. However, exact commit guarantees also depend on options such as `synchronous_commit`, replication, storage, and failover policies. Do not interpret "COMMIT succeeded" as meaning **synchronously written to every replica or every external system outside the database**.

---

## 3. Creating Lab Data with Accounts and a Transfer Log

Create an independent schema and tables in the lab database:

~~~sql
CREATE SCHEMA IF NOT EXISTS tx_lab;

CREATE TABLE tx_lab.accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    balance NUMERIC(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tx_lab.transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    from_account_id INTEGER NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES tx_lab.accounts(account_id),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_account_id <> to_account_id)
);
~~~

Load initial data **once**:

~~~sql
INSERT INTO tx_lab.accounts
    (account_id, account_name, balance)
VALUES
    (1, 'Account A', 1000.00),
    (2, 'Account B', 500.00),
    (3, 'Account C', 0.00);
~~~

Verify:

~~~sql
SELECT account_id, account_name, balance
FROM tx_lab.accounts
ORDER BY account_id;
~~~

| account_id | account_name | balance |
|---:|---|---:|
| 1 | Account A | 1000.00 |
| 2 | Account B | 500.00 |
| 3 | Account C | 0.00 |

The initial total is **1500**:

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

> The following examples are written as **separate scenarios**. When trying multiple scenarios, the state after a committed scenario may differ from the initial state. Do not assume the data is still at 1000/500 after practicing a committed transaction.

### 3.1. Writing Test Data Without Persistent Changes

To test adjusting a balance and then reverting the data:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Inside the transaction, the current session sees the balance increased by 10. After `ROLLBACK`, the change **does not persist**; the balance returns to its value before this transaction.

---

## 4. BEGIN, COMMIT, and ROLLBACK Syntax

### 4.1. BEGIN: Opening an Explicit Transaction Block

~~~sql
BEGIN;
~~~

PostgreSQL also supports:

~~~sql
START TRANSACTION;
~~~

Subsequent related SQL statements belong to the same transaction until `COMMIT` or `ROLLBACK` (or an abnormal termination condition).

Example:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 25
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

ROLLBACK;
~~~

### 4.2. COMMIT: Finalizing the Transaction

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 3;

COMMIT;
~~~

When `COMMIT` succeeds, the transaction's changes are confirmed. A subsequent transaction will see those changes according to its isolation rules. You cannot use `ROLLBACK` **after committing** to undo an already completed transaction.

In documentation you may also see `END`, which is equivalent to `COMMIT` in PostgreSQL. Prefer `COMMIT` to express the action clearly.

### 4.3. ROLLBACK: Ending and Discarding Uncommitted Changes

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
~~~

None of the +100 change from this transaction is kept. PostgreSQL also has the `ABORT` keyword, which is equivalent to `ROLLBACK` at the command level.

### 4.4. What Do COMMIT/ROLLBACK Do for SELECT Statements?

A read-only transaction does not modify tables, yet it still has:

- A snapshot / data visibility determined by the isolation level.
- Associated resources, locks, or state.
- A clear start and end point.

A `ROLLBACK` on a read-only transaction does not "erase the returned SELECT results"; it ends the transaction and releases the corresponding resources.

### 4.5. No Nested BEGIN for Nested Transactions

Do not write code assuming this works:

~~~sql
BEGIN;
    UPDATE ...;
    BEGIN;
        UPDATE ...;
    COMMIT;
ROLLBACK;
~~~

In PostgreSQL, `BEGIN` inside an already active transaction **does not create a nested transaction**. You may receive a warning `"there is already a transaction in progress"`. To mark a portion of work that can be rolled back, use **`SAVEPOINT`**.

### 4.6. COMMIT AND CHAIN / ROLLBACK AND CHAIN

PostgreSQL supports:

~~~sql
COMMIT AND CHAIN;
-- Or
ROLLBACK AND CHAIN;
~~~

When used inside a transaction, this statement ends the current transaction and **immediately starts a new transaction** preserving the relevant transaction characteristics according to `AND CHAIN` semantics. This is a specialized form and does not replace the common `COMMIT; BEGIN;` pattern in most applications.

---

## 5. Transaction Lifecycle: A State Machine

From an application perspective, you can visualize it as:

~~~mermaid
flowchart TD
    A["Connection not in an explicit transaction"] -->|"BEGIN"| B["Active transaction"]
    B -->|"Valid SQL"| B
    B -->|"COMMIT succeeds"| C["Committed: changes take effect"]
    B -->|"ROLLBACK"| D["Rolled back: uncommitted changes discarded"]
    B -->|"SQL error while in transaction"| E["Aborted: transaction failed"]
    E -->|"ROLLBACK"| D
    E -->|"ROLLBACK TO SAVEPOINT valid"| B
    E -->|"COMMIT"| D
    B -->|"Connection closes unexpectedly before COMMIT"| D
    C --> A
    D --> A
~~~

This diagram illustrates the **logical states**. Losing the socket right when `COMMIT` was sent can leave the **client uncertain** whether the commit succeeded or not; the "connection closes before COMMIT" transition only applies when the commit was genuinely **not processed**.

### 5.1. Stages

1. **No explicit transaction open:** the application can run each statement in autocommit mode.
2. **BEGIN:** the transaction starts, and isolation/access mode settings take effect.
3. **Statement execution:** SELECT, INSERT, UPDATE, DELETE, and many valid DDL statements can run inside the transaction; locks, snapshots, and WAL writes are managed as needed.
4. **Error occurs:** if a SQL statement raises an error that puts the transaction into the aborted state, subsequent normal SQL statements are rejected until an appropriate rollback occurs.
5. **COMMIT:** PostgreSQL validates and finalizes acceptance of the changes; commit itself can also fail (e.g., deferred constraint or serialization errors).
6. **ROLLBACK:** discards uncommitted changes and ends the transaction.
7. **Return to ready state:** a new transaction can begin.

### 5.2. Common States Seen in pg_stat_activity

With sufficient privileges to observe sessions, the `state` column can show:

| `state` | Operational Meaning |
|---|---|
| `active` | Backend is currently executing a statement |
| `idle` | Waiting for a command, not currently in a transaction |
| `idle in transaction` | Waiting for a command while a transaction remains open |
| `idle in transaction (aborted)` | Transaction failed and the session has not rolled back yet |

In particular, a prolonged `idle in transaction` state can hold resources/snapshots/locks, blocking other sessions and delaying old-row cleanup. This is a state to **avoid** in applications.

---

## 6. Autocommit and Explicit Transactions

### 6.1. Without BEGIN, Does PostgreSQL Still Use Transactions?

PostgreSQL executes every statement inside **a transaction**, even when the client does not issue `BEGIN`. In the autocommit mode commonly used in `psql`, each standalone statement implicitly begins and ends its own transaction.

~~~sql
UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 2;
~~~

In standard autocommit mode, these are **two separate transactions**. If the first statement succeeds and the second fails, the first statement is **not automatically rolled back**.

### 6.2. BEGIN Groups Multiple Statements into One Transaction

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 2;

COMMIT;
~~~

Both statements belong to the **same transaction** and can be accepted or discarded together. This boundary is essential whenever business logic requires two changes to be atomic.

### 6.3. Autocommit Is Client Behavior, Not "Disabling Transactions"

- `psql` normally runs in autocommit mode unless `BEGIN` is issued or configured otherwise.
- JDBC applications can call `Connection.setAutoCommit(false)` to manage transactions via the connection API; in that case, there is no need to manually send raw `BEGIN` strings.
- Frameworks/ORMs may manage transactions via annotations, contexts, or their own unit-of-work abstractions.

**Do not** mix multiple transaction mechanisms inconsistently at the same time. Always know who owns the transaction lifecycle: the library, the framework, or business code.

### 6.4. Transactions Are Bound to a Connection

A PostgreSQL transaction belongs to **a single database session/backend connection**. For example:

~~~text
Connection A: BEGIN → UPDATE → COMMIT
Connection B: SELECT ...
~~~

Connection B does not automatically "join" A's transaction just because both are handling the same HTTP request. If you acquire two connections from a pool and run two UPDATEs on two connections, you **do not** have a shared transaction.

---

## 7. Practicing COMMIT and ROLLBACK with a Safe Scenario

### 7.1. ROLLBACK Scenario

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;
~~~

If the two balances before the transaction were 1000 and 500, then **inside** the transaction you will see 900 and 600; **after ROLLBACK**, they return to 1000 and 500. If the balances were already changed in an earlier exercise, compare the **values before and after ROLLBACK** rather than expecting the exact initial numbers.

### 7.2. COMMIT Scenario

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (request_key, from_account_id, to_account_id, amount)
VALUES
    ('lab-transfer-0001', 1, 2, 100);

COMMIT;
~~~

Changes are persisted once the commit succeeds. The INSERT with `request_key='lab-transfer-0001'` has a UNIQUE constraint; running the exact same script again after committing will raise a duplicate request key error. This is intentional protection against recording two duplicate history entries, though a real application must implement proper **pre-check/reconciliation and retry** logic, which will be covered later.

### 7.3. Measuring Conserved Total Balance

~~~sql
SELECT SUM(balance) AS total_balance
FROM tx_lab.accounts;
~~~

The `-100` and `+100` UPDATEs leave the total balance across accounts unchanged. However, **checking only the sum** is not enough: money could be transferred to the wrong account while the total still matches. You also need FKs, request keys, positive amounts, balance checks, and affected-row verification.

---

## 8. Transactions When a SQL Error Occurs

### 8.1. A Constraint Violation Puts the Transaction in Aborted State

Because `balance` has a non-negative CHECK constraint:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = -10
WHERE account_id = 3;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;
~~~

The UPDATE fails with a `CHECK(balance >= 0)` violation. Inside an explicit transaction, after an unhandled SQL error (not caught via a savepoint), subsequent normal statements typically report:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
~~~

This is not an error with the subsequent SELECT itself; the transaction **was already marked failed** by the previous statement.

Recovery:

~~~sql
ROLLBACK;
~~~

### 8.2. Do Not Keep "Trying to COMMIT" After an Error

If a transaction is in the aborted state, sending `COMMIT` does not make the failed changes valid; PostgreSQL ends the transaction with a rollback (the response may be `ROLLBACK`). The application must handle the error **immediately at the failing SQL statement**, rather than treating `COMMIT` as a way to force success.

### 8.3. Do Constraints Always Apply on Every Statement?

A transaction can execute multiple statements, and a constraint can be checked **immediately when a statement runs** or **deferred until COMMIT** if an eligible constraint is configured as `DEFERRABLE`. Therefore, every `UPDATE` succeeding does not guarantee `COMMIT` will succeed; you must check the commit result.

### 8.4. Always End the Transaction in Every Error Branch

On the client side:

~~~text
BEGIN
  |
  +-- statement succeeds --> ... --> COMMIT
  |
  +-- error at any step ----------> ROLLBACK
~~~

If an application swallows an exception and returns a connection that is still in an aborted transaction to the pool, the next request may keep hitting `25P02` errors or hold resources unnecessarily.

---

## 9. SAVEPOINT: Partial Rollback Within a Transaction

`SAVEPOINT` does not create a completely independent transaction. It marks a point within the current transaction so changes made after that marker can be discarded while keeping changes made before it.

### 9.1. Success and Partial-Discard Example

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT optional_step;

UPDATE tx_lab.accounts
SET balance = balance + 20
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT optional_step;

-- The +20 on B was discarded, while +10 on A remains in the transaction.
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;
~~~

The end of the example uses a full transaction ROLLBACK so no changes remain in the lab. If replaced with COMMIT, the `+10` change before the savepoint would be committed.

### 9.2. Recovering from a Constraint Error

~~~sql
BEGIN;

SAVEPOINT before_risky_update;

UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 3;

-- After the error, recover by rolling back to the valid savepoint:
ROLLBACK TO SAVEPOINT before_risky_update;

-- The transaction can continue:
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id = 3;

RELEASE SAVEPOINT before_risky_update;

ROLLBACK;
~~~

In the scenario above, issuing `ROLLBACK TO SAVEPOINT` after the error returns the transaction to a state where it can continue. If there is no valid savepoint to roll back to, you must `ROLLBACK` the entire transaction.

### 9.3. RELEASE SAVEPOINT Is Not COMMIT

~~~sql
RELEASE SAVEPOINT before_risky_update;
~~~

This only removes the savepoint marker and merges the associated changes into the outer transaction. Those changes **are not committed externally** until `COMMIT` succeeds. After `RELEASE`, you can no longer `ROLLBACK TO` the released savepoint.

### 9.4. Limitations of SAVEPOINT

- There is no independent "nested commit": if the outer transaction rolls back, all uncommitted changes are discarded, including work whose savepoint was released with `RELEASE SAVEPOINT`.
- Some resources/locks have mechanisms to be released upon rolling back to a savepoint according to PostgreSQL semantics, but you should not rely on savepoints to roll back any external resources outside the database.
- Managing many complex savepoints can make application code hard to understand and prone to business-logic mistakes.
- Distinguish between errors that can be safely skipped in an optional step and errors where the entire transaction must abort (for example, in a failed transfer you cannot skip the debit and still perform the credit).

### 9.5. Savepoints and Exceptions in PL/pgSQL

In PL/pgSQL, blocks with an `EXCEPTION` clause use a subtransaction mechanism to handle errors within the block's scope. This is related, though it does not mean arbitrary `COMMIT` calls are permitted from every function. Transaction-control rules in functions/procedures and their calling contexts have specific restrictions.

---

## 10. DDL and Transactions in PostgreSQL

An important strength: many schema changes in PostgreSQL are transactional, unlike some database systems that implicitly commit many DDL statements.

### 10.1. CREATE TABLE Can Be Rolled Back

In the lab database:

~~~sql
BEGIN;

CREATE TABLE tx_lab.experimental_table (
    id INTEGER PRIMARY KEY,
    note TEXT NOT NULL
);

INSERT INTO tx_lab.experimental_table(id, note)
VALUES (1, 'used only inside transaction');

ROLLBACK;
~~~

After the rollback succeeds, `tx_lab.experimental_table` does not exist (assuming it did not exist beforehand). This is convenient when testing transactional DDL migrations.

### 10.2. Many DDL Statements Can Run Inside a Transaction

For example, `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, standard `CREATE INDEX`, and many other schema operations can belong to a transaction, depending on the specific command. However, **not every administrative command** is allowed inside a transaction block.

Example:

~~~sql
-- Example command not allowed inside a transaction block:
BEGIN;
CREATE DATABASE should_not_run_inside_transaction;
ROLLBACK;
~~~

`CREATE DATABASE` cannot be executed inside a transaction block. Do not run this command in a real environment; it only illustrates the restriction.

Operations such as `CREATE INDEX CONCURRENTLY` or `VACUUM` also have rules requiring execution outside a transaction block.

### 10.3. DDL Can Acquire Strong Locks

`ALTER TABLE` can acquire locks that affect concurrent reads and writes, depending on the operation. Wrapping a large migration in `BEGIN` does not by itself guarantee "zero downtime." You must evaluate lock types, execution duration, `lock_timeout`, large tables, and the rollback plan.

### 10.4. Migrations Should Have a Clear Strategy

- Identify which commands support transactions.
- Avoid holding a transaction open while waiting for manual verification.
- Do not run `CREATE INDEX CONCURRENTLY` inside a `BEGIN` block.
- Anticipate locks and test on staging.
- Plan staged rollouts for large schemas.
- Ensure connections are not returned to a pool while a migration transaction is still open.

---

## 11. Why Uncommitted Changes Are Not Visible to Other Sessions

PostgreSQL uses **MVCC (Multi-Version Concurrency Control)** to manage visibility of row versions. When one session modifies a balance without committing:

- That session itself normally **sees its own changes**.
- An independent session reading normally under `READ COMMITTED` will **not dirty-read** the first session's uncommitted changes.
- Other transactions can read the prior version appropriate for their snapshot; a write or locking operation on the same row may have to wait.

### 11.1. Two Connections to Verify

Open **two separate psql windows or two independent connections** to the same lab database.

**Session A:**

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 77
WHERE account_id = 1;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Note the new balance in A, **do not COMMIT yet**.

**Session B:**

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

Under standard READ COMMITTED, B sees **the previously committed balance**, not A's uncommitted `+77`.

**Back to Session A:**

~~~sql
ROLLBACK;
~~~

**Session B reads again:**

~~~sql
SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;
~~~

The `+77` never appears because it was rolled back.

### 11.2. What Does Session B See After COMMIT?

If you repeat the scenario but Session A runs COMMIT instead of ROLLBACK, new SELECT statements in B under READ COMMITTED can see the committed balance. If B is running under REPEATABLE READ with an existing snapshot, what it sees can differ until B's transaction ends.

### 11.3. MVCC Does Not Mean Concurrent Updates Never Block

A plain SELECT usually reads via a snapshot without waiting on row locks for older versions, but `UPDATE`, `DELETE`, or `SELECT FOR UPDATE` on the same row may **wait for the transaction holding the lock**. "Readers don't block writers" should not be misunderstood as "lock waits never happen."

---

## 12. Transaction Isolation Levels: READ COMMITTED to SERIALIZABLE

An isolation level defines the rules for seeing changes made by concurrent transactions. PostgreSQL supports the SQL standard levels, with some implementation-specific behaviors.

### 12.1. Core Levels

| Isolation Level | Core Behavior in PostgreSQL | Common Use Case |
|---|---|---|
| `READ UNCOMMITTED` | PostgreSQL effectively behaves like `READ COMMITTED`; dirty reads are not allowed | Syntax compatibility without dirty reads |
| `READ COMMITTED` | Each statement gets a fresh snapshot when it starts; a later statement can see new commits | Default, many OLTP workloads |
| `REPEATABLE READ` | Reads within the transaction see a consistent transaction snapshot (under PostgreSQL semantics); prevents nonrepeatable reads, though not full serializability | Multi-query reports needing a stable view |
| `SERIALIZABLE` | PostgreSQL detects interactions that may not be equivalent to a serial schedule; some transactions may be aborted with error `40001` | Cross-transaction invariants requiring serializability |

**Key point:** stronger isolation does not eliminate the need for error handling. `SERIALIZABLE` may require the application to **retry the entire transaction** after a serialization failure.

### 12.2. Default Level: READ COMMITTED

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;

-- If another transaction commits between the two SELECTs:

SELECT balance
FROM tx_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

The two SELECT statements can return different values because PostgreSQL acquires an appropriate snapshot for **each statement** in READ COMMITTED.

### 12.3. REPEATABLE READ

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT SUM(balance) AS total_1
FROM tx_lab.accounts;

-- Another transaction may commit changes here.

SELECT SUM(balance) AS total_2
FROM tx_lab.accounts;

COMMIT;
~~~

In this REPEATABLE READ transaction, normal SELECT statements remain based on the **same transaction snapshot**, so they do not start seeing new commits made after the snapshot was established. Remember that the snapshot is typically established when the **first non-transaction-control statement requiring a snapshot executes**, not necessarily at the exact moment `BEGIN` is sent.

### 12.4. SERIALIZABLE and Retries

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Read relevant constraints.
-- Execute required UPDATE/INSERT statements.

COMMIT;
~~~

When PostgreSQL detects an execution schedule conflicting with serializability, the transaction may terminate with:

~~~text
SQLSTATE 40001: serialization_failure
~~~

Do not retry only the final UPDATE statement: business decisions may have been based on earlier SELECTs. **Retry the entire transaction** with a fresh snapshot and a bounded retry limit.

### 12.5. READ ONLY and DEFERRABLE

For reports needing a stable snapshot, you can use:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT account_id, balance
FROM tx_lab.accounts
ORDER BY account_id;

COMMIT;
~~~

In the `SERIALIZABLE READ ONLY DEFERRABLE` combination, the transaction may **wait** to obtain a safe snapshot in order to reduce the risk of serialization failures for this class of query. It does not mean every READ ONLY transaction or every SELECT automatically avoids waiting.

### 12.6. Checking the Current Isolation Level

~~~sql
SHOW transaction_isolation;
SHOW transaction_read_only;
~~~

Inside a transaction before executing data queries, you can use:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT current_setting('transaction_isolation');
ROLLBACK;
~~~

Do not change the isolation level after already running queries that needed a snapshot and expect the new rule to apply retroactively to the whole transaction.

---

## 13. Row Locks: When Two Transactions Update the Same Account

To test this, open two separate connections to the **same lab database**. Run the steps in order; do not run everything automatically unless you can stop sessions manually.

### 13.1. Session A Opens a Transaction and Modifies a Row

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 1;

-- Keep the transaction open temporarily to observe from B.
~~~

Session A holds the locks associated with the UPDATE operation while it remains uncommitted/unrolled back.

### 13.2. Session B Attempts to Modify the Same Row

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

UPDATE tx_lab.accounts
SET balance = balance + 2
WHERE account_id = 1;
~~~

Session B may have to **wait for the lock** held by A. After the configured duration, if still blocked, PostgreSQL raises a lock timeout error. Because the error occurred inside a transaction, B must run:

~~~sql
ROLLBACK;
~~~

### 13.3. Session A Releases the Lock

~~~sql
ROLLBACK;
~~~

In this example, both A and B rolled back, so neither `+1` nor `+2` is persisted.

### 13.4. Why Use lock_timeout in the Lab?

Without a wait limit, accidentally leaving Session A `idle in transaction` can cause Session B to wait for a very long time. Using `SET LOCAL lock_timeout` in exercises allows controlled observation, and the timeout setting automatically disappears when the transaction ends.

### 13.5. SELECT FOR UPDATE

To lock rows that are about to be modified:

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Perform related updates.

ROLLBACK;
~~~

`FOR UPDATE` requests row locks on the selected rows. Other transactions attempting to lock or modify the same rows in a conflicting mode may have to wait.

**Do not** use `SELECT FOR UPDATE` over a broad range if you only need reporting, as it increases contention and can block other work.

---

## 14. Avoiding Deadlocks with Consistent Lock Ordering

A deadlock can occur when two transactions hold different locks and each waits for a lock held by the other.

~~~text
Transaction A                       Transaction B
-------------                       -------------
Holds lock on account 1             Holds lock on account 2
Wants lock on account 2 --X-------> Holds account 2
Holds account 1       <-------X---- Wants lock on account 1

=> Lock wait cycle
~~~

PostgreSQL detects the deadlock and aborts one transaction to break the wait cycle; the application may see:

~~~text
SQLSTATE 40P01: deadlock_detected
~~~

### 14.1. Lock-Ordering Strategy

When transferring between two accounts:

1. Identify the account IDs involved.
2. Always lock in **ascending ID order**.
3. Verify that both rows were retrieved and the balance is sufficient.
4. Execute debit, credit, and transfer record insertion.
5. COMMIT as soon as the unit of work finishes.

Example:

~~~sql
BEGIN;

SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

ROLLBACK;
~~~

A query that acquires locks in a consistent order can help reduce deadlocks in this design, though it **does not guarantee all types of deadlocks disappear**: transactions can still touch multiple tables, indexes, foreign keys, or other access paths.

### 14.2. NOWAIT and SKIP LOCKED Are Not Magic

PostgreSQL provides variants such as:

~~~sql
SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

If the row lock cannot be acquired immediately, the command can error out instead of waiting.

~~~sql
SELECT account_id
FROM tx_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

This can skip rows that are currently locked. `SKIP LOCKED` fits **job queue/worker contention** in certain designs, and is **not** appropriate when a transfer strictly requires acquiring both accounts. Skipping target rows can turn a mandatory transaction into an incomplete operation.

---

## 15. Building a Controlled Transfer Transaction

Goal: transfer 100 from account 1 to account 2 and record a history entry with a unique request key.

### 15.1. Constraints Already in the Database

The lab schema enforces:

- `accounts.account_id` is a PRIMARY KEY.
- `accounts.balance` cannot be negative.
- `transfers.amount > 0`.
- `transfers.from_account_id` and `to_account_id` are foreign keys.
- Source and destination IDs cannot be identical.
- `transfers.request_key` is UNIQUE.

Database constraints protect data when application bugs occur, yet the application still needs to verify **affected row counts** and **transaction outcomes**.

### 15.2. A Practical Transaction

~~~sql
BEGIN;

-- Select and lock both accounts in a consistent order.
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Require UPDATE 1; if UPDATE 0, ROLLBACK.
UPDATE tx_lab.accounts
SET balance = balance - 100,
    updated_at = now()
WHERE account_id = 1
  AND balance >= 100;

-- Require UPDATE 1; if UPDATE 0, ROLLBACK.
UPDATE tx_lab.accounts
SET balance = balance + 100,
    updated_at = now()
WHERE account_id = 2;

INSERT INTO tx_lab.transfers
    (request_key, from_account_id, to_account_id, amount)
VALUES ('lab-transfer-0002', 1, 2, 100);

COMMIT;
~~~

**Important:** the SQL block above should only proceed to commit when the operator/application **has verified**:

1. `SELECT FOR UPDATE` returned both **required accounts**.
2. The debit `UPDATE` returned `UPDATE 1`; `UPDATE 0` means insufficient balance or account not found.
3. The credit `UPDATE` returned `UPDATE 1`.
4. The transfer INSERT succeeded with the right request key.

If any condition is not met, you must **ROLLBACK immediately** and never continue to COMMIT. A script that blindly sends all statements sequentially **without checking row counts** could corrupt business logic if the debit matches 0 rows while the credit still matches 1 row. In application code, these checks are mandatory.

### 15.3. Why Use a Conditional UPDATE with balance >= amount?

~~~sql
UPDATE tx_lab.accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
~~~

This is a **conditional update**. If the balance is below 100, PostgreSQL does not update that row and returns `UPDATE 0`. By checking the condition at UPDATE time, the operation is safer than reading a balance on the client first and updating without re-checking.

Adding `CHECK(balance >= 0)` prevents negative balances if application logic omits the predicate. However, CHECK only prevents negative values; it does not automatically undo other updates in the transaction when the debit returns 0 **without raising an error**. That is why the application must inspect affected rows and decide to roll back.

### 15.4. Checking an Idempotent Request

~~~sql
SELECT transfer_id, request_key,
       from_account_id, to_account_id, amount
FROM tx_lab.transfers
WHERE request_key = 'lab-transfer-0002';
~~~

Never reuse a `request_key` for a brand-new business request. If a client retries the same request after a timeout, look up the transfer with that request key and verify matching source/destination/amount instead of automatically executing another transfer.

### 15.5. Separating Business Transactions from Client-Side Processing

Safe boundary:

~~~text
BEGIN
  ├─ Lock required accounts
  ├─ Verify balances and existence
  ├─ Debit, verify exactly one row
  ├─ Credit, verify exactly one row
  ├─ Insert record with UNIQUE request_key
  └─ COMMIT if all steps are valid

Any step fails ──> ROLLBACK
~~~

Do not commit between debit and credit. Doing so would break the atomicity of the transfer.

---

## 16. SQLSTATE and Classifying Transaction Errors

PostgreSQL provides SQLSTATE codes so applications can identify error categories instead of matching message strings that may vary by locale.

| SQLSTATE | Common Meaning | Handling Approach |
|---|---|---|
| `25P02` | Transaction already aborted; subsequent commands ignored | `ROLLBACK` or roll back to a valid savepoint |
| `23505` | UNIQUE violation | Distinguish duplicate request from data error; check idempotency |
| `23503` | FOREIGN KEY violation | Validate referenced account/entity |
| `23514` | CHECK violation | Data fails constraint |
| `40001` | Serialization failure | Retry the **entire transaction** if appropriate |
| `40P01` | Deadlock detected | ROLLBACK, retry the entire transaction with a bound |
| `55P03` | Lock not available / lock timeout | Handle lock contention, consider retry or busy response |
| `57014` | Query canceled, including statement timeout | ROLLBACK failed transaction; inspect cost and timeout |

### 16.1. Do Not Retry Every Error

A `23514` caused by a negative balance will not become valid merely by re-running it, whereas `40001` can succeed when the transaction is recomputed against a new snapshot.

Define separate policies for:

- **Retryable concurrency errors:** serialization failure, deadlock, and certain timeouts depending on business logic.
- **Business validation errors:** insufficient funds, duplicate request with mismatched payload, missing account.
- **Infrastructure/connection errors:** it may be unknown whether `COMMIT` succeeded or not.

### 16.2. Retries Must Be Bounded

Retrying infinitely when the system is overloaded amplifies contention and cost. You should:

1. Cap the retry count.
2. Use appropriate backoff/jitter.
3. Recompute all data-dependent decisions inside the new transaction.
4. Keep the same request key to avoid duplicate business effects.
5. Log and monitor error rates rather than hiding failures.

### 16.3. COMMIT Itself Can Fail

Even when statements prior to COMMIT reported no errors, commit can be rejected due to:

- A `DEFERRABLE` constraint checked only at transaction end.
- A serialization conflict in a `SERIALIZABLE` transaction.
- I/O, configuration, or infrastructure failures.

Report "completed" to the caller only after receiving a valid commit confirmation, or after resolving an **uncertain** state via a reconciliation mechanism.

---

## 17. Losing Connection Right at COMMIT

This is a critical scenario in real-world systems:

~~~text
Client                            PostgreSQL
  |                                  |
  |------------ COMMIT ------------->|
  |                                  |  Commit may have completed
  X  network lost before response    |
  |                                  |
  ?  Final outcome unknown           |
~~~

If the client **does not receive a COMMIT response**, it cannot assert that the transaction definitely rolled back. Possibilities include:

1. PostgreSQL had not processed the commit yet and aborted the transaction when the connection dropped.
2. PostgreSQL committed successfully, but the response was lost in transit.
3. Other infrastructure conditions requiring verification per operational procedures.

### 17.1. Do Not Blindly Retry

For a money transfer, retrying "transfer 100" with a brand-new request could **transfer twice**.

Instead, design a client-supplied **idempotency key / `request_key`** attached to the business request. After reconnecting:

~~~sql
SELECT transfer_id, from_account_id, to_account_id, amount
FROM tx_lab.transfers
WHERE request_key = 'lab-transfer-0002';
~~~

If it exists and the payload matches, you have a basis to confirm the request was recorded. If it does not exist, verify transaction status / retry under an idempotent protocol while accounting for replication lag, failover, or other side effects; do not infer status solely from a SELECT against a potentially lagging replica.

### 17.2. A UNIQUE request_key Is Part of the Design, Not the Whole Design

A UNIQUE constraint prevents **two records with the same key** in the table; however, you must keep **all balance changes and the key record in the same transaction**, and handle conflicts properly. If a duplicate key is detected after balances were already modified inside the transaction, the UNIQUE error will abort the transaction and roll back those changes.

If the system must handle concurrent retries, design explicit request registration / key claiming inside the transaction with clear states, proper locking/waiting, and outcome verification. Do not rely solely on check-then-insert without UNIQUE, since two concurrent requests can both observe "not present yet."

---

## 18. Transactions and Systems Outside PostgreSQL

A database transaction **does not automatically include** operations outside PostgreSQL such as:

- Sending email/SMS.
- Calling a remote payment API.
- Writing files to object storage.
- Publishing events to a message broker.
- Deleting or modifying data in another database.

### 18.1. Why Sending Email Before COMMIT Can Be Wrong

~~~text
BEGIN
  UPDATE order → status = PAID
  SEND EMAIL "Payment received!"
  Another UPDATE fails
ROLLBACK
~~~

The email was already sent, yet the order data rolled back; the user receives a false notification.

### 18.2. Transactional Outbox (Conceptual Pattern)

A commonly used design pattern:

~~~text
BEGIN
  Update business data
  INSERT outbox event in the same transaction
COMMIT
          |
          v
Independent worker reads committed outbox rows
          |
          v
Send message/email; mark processed with retry/idempotency
~~~

Advantage: the outbox record and the DB state are committed or rolled back **together**. However, the external delivery system still needs **at-least-once / idempotency**, deduplication, or another protocol to prevent duplicate processing.

### 18.3. Do Not Confuse Database Transactions with Distributed Transactions

`BEGIN` on one PostgreSQL connection does not open an atomic transaction across all services. PostgreSQL provides two-phase commit mechanisms (`PREPARE TRANSACTION`, `COMMIT PREPARED`) when configured, but that is a separate administrative and coordination topic with risks of holding prepared transactions and locks if left incomplete. Do not casually use 2PC to solve every microservices workflow.

---

## 19. JDBC Example for Managing Transactions in a Java Application

When connecting via JDBC, a common pattern is **one connection per business unit of work**, disabling autocommit, and calling commit/rollback through the API—rather than manually issuing `BEGIN` on every `PreparedStatement`.

### 19.1. Illustrative Example Checking Row Counts

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            int fromAccountId,
            int toAccountId,
            BigDecimal amount,
            String requestKey) throws SQLException {

        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException("Source and destination accounts must differ");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (requestKey == null || requestKey.isBlank()) {
            throw new IllegalArgumentException("Missing requestKey");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // Lock both accounts in ascending ID order.
                int locked = 0;
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT account_id FROM tx_lab.accounts " +
                        "WHERE account_id IN (?, ?) " +
                        "ORDER BY account_id FOR UPDATE")) {
                    ps.setInt(1, fromAccountId);
                    ps.setInt(2, toAccountId);
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            locked++;
                        }
                    }
                }
                if (locked != 2) {
                    throw new SQLException("Missing transfer account");
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE tx_lab.accounts " +
                        "SET balance = balance - ?, updated_at = now() " +
                        "WHERE account_id = ? AND balance >= ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setInt(2, fromAccountId);
                    ps.setBigDecimal(3, amount);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Insufficient balance");
                    }
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE tx_lab.accounts " +
                        "SET balance = balance + ?, updated_at = now() " +
                        "WHERE account_id = ?")) {
                    ps.setBigDecimal(1, amount);
                    ps.setInt(2, toAccountId);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Destination account not found");
                    }
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO tx_lab.transfers " +
                        "(request_key, from_account_id, to_account_id, amount) " +
                        "VALUES (?, ?, ?, ?)")) {
                    ps.setString(1, requestKey);
                    ps.setInt(2, fromAccountId);
                    ps.setInt(3, toAccountId);
                    ps.setBigDecimal(4, amount);
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
            } finally {
                // Restore connection state only as expected by pool policy.
                connection.setAutoCommit(previousAutoCommit);
            }
        }
    }
}
~~~

### 19.2. Meaning of Each Step

- `setAutoCommit(false)` groups a series of SQL statements into one API-managed transaction.
- `SELECT ... FOR UPDATE` locks the accounts in ascending ID order.
- `executeUpdate() == 1` confirms each modification affected exactly one row.
- `balance >= amount` prevents overdrawing inside the UPDATE itself.
- `INSERT` records the request key in the same transaction.
- `commit()` runs only after every condition succeeds.
- In the catch block, `rollback()` discards uncommitted changes.
- `PreparedStatement` binds parameters, avoiding concatenation of untrusted input into SQL strings.

**Example limitations:** this is an educational sample for a single transaction, **not a complete production transfer implementation**. It does not yet cover full idempotency handling under concurrent retries, business exception translation, timeout/SQLSTATE handling, uncertain commit states, outbox, reconciliation, or pool eviction when rollback/state restoration fails.

### 19.3. Be Careful in finally

Some JDBC drivers treat switching autocommit from `false` back to `true` while a transaction is still open as ending the transaction. In normal execution here, `commit()` or `rollback()` has already run before restoring autocommit.

However, **if rollback fails due to a connection error**, you must not assume the connection is safe to return to the pool. Production implementations need a pool **evict/invalidate broken connection** policy and must not let state-restoration errors mask the original exception. Framework transaction managers typically handle this; avoid reimplementing something that conflicts with existing mechanisms.

### 19.4. Never Use Two Connections for One Transaction

Incorrect transaction boundaries:

~~~text
connA.execute("UPDATE source account")
connB.execute("UPDATE destination account")
connA.commit()
connB.commit()
~~~

Two independent commits can succeed or fail separately. A PostgreSQL transaction must use the **same connection** from start to finish.

---

## 20. Transactions in ORMs/Frameworks and Connection Pools

### 20.1. One Request May Use Multiple Transactions

In a web application:

~~~text
HTTP request
  |
  +-- Validate input, authenticate (no need to hold a DB transaction open)
  |
  +-- Acquire connection from pool
  |     BEGIN / setAutoCommit(false)
  |     SELECT, UPDATE, INSERT
  |     COMMIT or ROLLBACK
  |   Return connection to pool
  |
  +-- Return response or trigger post-commit work
~~~

A transaction should wrap exactly the **database unit of work** that needs atomicity; it should not be held open while waiting for a user click, slow external network calls, or heavy CPU work.

### 20.2. Framework Annotations Are Not Magic

An annotation such as `@Transactional` in Spring (if used in your stack) depends on proxies, propagation, exception rollback rules, transaction manager configuration, and the connection source. For example, self-invocation or catching/swallowing exceptions can prevent rollback from behaving as expected. In any given application, verify how the framework actually establishes transactions and triggers rollbacks.

### 20.3. Returning an Aborted Connection to the Pool

If a request encounters SQLSTATE 25P02 and skips rollback, the backend remains in an aborted transaction. The next connection user may hit cascading errors. The pool or transaction manager must proactively **rollback/reset the connection** before reuse.

### 20.4. Transactions Do Not Magically Follow Threads

A transaction does not automatically propagate to another thread, event handler, or service unless the technology/framework explicitly provides context/connection propagation. Do not offload part of a business operation onto another thread and assume it shares the original request's transaction.

---

## 21. Timeouts and Abandoned Transactions

### 21.1. lock_timeout: Bounding Lock Waits

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SET LOCAL` takes effect **for the current transaction only**, which helps avoid lingering session-level settings in connection pools.

### 21.2. statement_timeout: Bounding Statement Duration

~~~sql
BEGIN;
SET LOCAL statement_timeout = '5s';

SELECT SUM(balance)
FROM tx_lab.accounts;

ROLLBACK;
~~~

A timeout cancels a **statement** exceeding the limit and can put the current transaction into the aborted state unless handled with an appropriate savepoint. Do not simply continue sending normal SQL after a timeout.

### 21.3. idle_in_transaction_session_timeout

PostgreSQL provides `idle_in_transaction_session_timeout` to terminate sessions stuck in **idle in transaction** for too long. This is an operational safety net, not a substitute for application code that always commits/rolls back and returns connections properly.

### 21.4. Workload Tuning Recommendations

- Set application-tier request timeouts.
- Set a sensible `lock_timeout` when contention should fail fast.
- Set `statement_timeout` for queries that could run excessively long.
- Monitor long-running transactions and `idle in transaction` sessions.
- Do not blindly raise timeouts indefinitely to "fix" deadlocks or missing indexes.

### 21.5. Different Timeouts Measure Different Things

`statement_timeout` bounds statement execution time, `lock_timeout` bounds lock wait time, while transaction lifetime includes idle gaps between statements (while the application is doing other work). A transaction can have very fast individual SQL statements yet stay open for minutes while application code waits on an external network call.

---

## 22. Observing Transactions and Locks in PostgreSQL

### 22.1. Checking the Current Session's State

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

`pg_backend_pid()` returns the connection's backend PID. While this query itself is executing, `state` will typically show `active`; to observe a session in `idle in transaction`, inspect it from **another administrative connection**.

### 22.2. Viewing Long-Running Open Transactions

With appropriate privileges:

~~~sql
SELECT
    pid, usename, application_name, state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type, wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

This query helps identify backends with open transactions, though it does not by itself tell you whether a session is **safe to kill**. Visibility into full query details of other sessions may be restricted for regular users.

### 22.3. Seeing Which PID Is Blocking Which Session

~~~sql
SELECT
    a.pid AS blocked_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
~~~

`pg_blocking_pids` helps identify backends holding locks that block a PID. When inspecting sessions in production, ensure proper access permissions, handle sensitive query data carefully, and exercise caution before canceling or terminating backends.

### 22.4. pg_locks

~~~sql
SELECT
    pid, locktype, mode, granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
~~~

Some locks are not tied to a specific relation (for example, transaction ID locks), so `relation_name` may be NULL. Do not conclude from a single row in `pg_locks` that the entire system is blocked; correlate across backends and queries.

### 22.5. Long-Running Transactions Affect Vacuum

A long-lived transaction can hold back old snapshots or delay PostgreSQL's cleanup of obsolete tuple versions, leading to table bloat, heavier VACUUM work, or delayed maintenance. Even an apparently "inactive" session sitting `idle in transaction` can have this impact. Thus, the transaction lifecycle is an **operational concern**, not just a data-correctness concern.

---

## 23. psql and Migration Scripts

### 23.1. psql Executes Individual Statements Independently by Default

Without an explicit transaction, `psql` normally runs in autocommit mode, committing each statement separately on success. To execute changes atomically:

~~~sql
BEGIN;
ALTER TABLE tx_lab.accounts
    ADD COLUMN IF NOT EXISTS description TEXT;
UPDATE tx_lab.accounts
SET description = 'lab account'
WHERE description IS NULL;
COMMIT;
~~~

This is a lab migration example; if you only want to test whether the DDL can be rolled back, replace `COMMIT` with `ROLLBACK`.

### 23.2. Running a psql File in One Transaction

`psql` offers flags such as:

~~~bash
psql -X --set=ON_ERROR_STOP=1 --single-transaction --file=migration.sql
~~~

Where appropriate, `--single-transaction` wraps the file's commands in a single transaction. However:

- The file must not contain transaction-control statements that conflict with the wrapper.
- The file must not contain commands PostgreSQL **forbids inside a transaction block**, such as `CREATE DATABASE` or `CREATE INDEX CONCURRENTLY`.
- `ON_ERROR_STOP` stops the script upon error instead of silently continuing; still verify the exit status and deployment state.
- Do not run on production without evaluating DDL types, locks, duration, and rollback plans.

### 23.3. Transactions for Seeding/Testing

A practical technique:

~~~sql
BEGIN;

INSERT INTO tx_lab.accounts (account_id, account_name, balance)
VALUES (99, 'Test account', 123);

SELECT *
FROM tx_lab.accounts
WHERE account_id = 99;

ROLLBACK;
~~~

Ending with `ROLLBACK` leaves no test account behind. However, **sequence/identity allocations** do not necessarily roll back with `ROLLBACK`. If you INSERT into a table using `GENERATED ... AS IDENTITY` or `SERIAL`, you may observe **ID gaps** after a transaction rollback; never rely on contiguous IDs as a business invariant.

---

## 24. Common Mistakes with Transactions

| Mistake | Risk | Fix |
|---|---|---|
| Two autocommit UPDATEs assumed to be one unit | One UPDATE commits while the other fails | Use a single transaction on the same connection |
| Forgetting COMMIT/ROLLBACK | Locks/snapshots held open, backend idle in transaction | End transactions in every code path |
| Catching an exception and ignoring it | Connection remains aborted, SQLSTATE 25P02 | Roll back or revert to a valid savepoint |
| Sending COMMIT after a SQL error and assuming success | Transaction may roll back | Check each step's result and commit outcome |
| Not checking `UPDATE 0` | Credit may proceed even though debit did not happen | Check affected rows and roll back when wrong |
| Checking balance outside the transaction then updating | Race condition, stale balance read | Use appropriate locking / conditional updates |
| Modifying data across two different connections | Not atomic | Use one connection per transaction |
| Treating nested BEGIN as a nested transaction | Misunderstands commit boundaries | Use SAVEPOINT |
| Using SAVEPOINT to "partially commit" | That work still rolls back if the outer transaction rolls back | Understand RELEASE is not COMMIT |
| Holding a transaction open during slow API calls | Prolonged locks and snapshots | Use outbox or move side effects post-commit |
| Retrying every SQLSTATE | Masks business errors, increases load | Separate retryable vs. non-retryable errors |
| Retrying only the last UPDATE after 40001 | Relies on stale reads, wrong decisions | Retry the entire transaction |
| Losing COMMIT response and retrying with a new request | Can double-transfer funds | Use idempotency keys and reconciliation |
| Assuming UNIQUE alone solves idempotency | Does not validate payload/outcome | Design explicit request states and reconciliation |
| Using READ COMMITTED expecting a fixed snapshot | Two SELECTs can see newer commits | Choose the appropriate isolation level |
| Assuming SERIALIZABLE cannot fail | Transactions can abort on conflicts | Implement bounded retry policies |
| Locking two rows in opposite orders | Deadlock | Enforce consistent lock ordering |
| Using SKIP LOCKED for mandatory accounts | Skips rows that must be updated | Reserve for suitable queue workloads |
| Wrapping CREATE INDEX CONCURRENTLY in BEGIN | PostgreSQL rejects it | Run under separate administrative rules |
| Not monitoring idle in transaction | Bloat, lock contention, delayed VACUUM | Use pg_stat_activity, timeouts, and code cleanup |
| Assuming sending COMMIT means success | Connection loss leaves outcome unknown | Wait for ack or reconcile via request key |
| Relying on a DB transaction to send email exactly once | External side effects do not roll back | Use outbox and idempotent consumers |

---

## 25. Transaction Lifecycle Design Checklist

~~~mermaid
flowchart TD
    A["Business unit requiring atomicity"] --> B["Acquire one connection"]
    B --> C["BEGIN / setAutoCommit(false)"]
    C --> D["Read and lock required data"]
    D --> E["Validate business conditions"]
    E --> F{"Conditions valid?"}
    F -- "No" --> G["ROLLBACK"]
    F -- "Yes" --> H["Execute UPDATE/INSERT"]
    H --> I{"All SQL and row counts valid?"}
    I -- "No" --> G
    I -- "Yes" --> J["COMMIT"]
    J --> K{"Success confirmed?"}
    K -- "Yes" --> L["Return success result"]
    K -- "Explicit error" --> M["Rollback / retry if appropriate"]
    K -- "Connection lost, outcome uncertain" --> N["Reconcile using request key"]
    G --> O["Close/reset connection"]
    L --> O
    M --> O
    N --> O
~~~

Before deploying to production, answer:

1. Which SQL statements belong to the transaction, and **when** does it start and end?
2. Does each SQL statement require an exact affected row count?
3. Should data be protected by UNIQUE, CHECK, FK, triggers, or conditional updates?
4. Which rows face contention? Are locks acquired in a consistent order?
5. Which isolation level is appropriate? Are `40001` or `40P01` possible?
6. Are `SAVEPOINT`s used for skippable secondary errors, or must the whole transaction abort?
7. Is the same connection used throughout the entire business unit of work?
8. Are any external systems called while the transaction is still open?
9. Is there a request key / idempotency mechanism for uncertain commit outcomes?
10. Are timeouts and `idle in transaction` monitoring configured?
11. Are connections returned to the pool in a clean state?
12. Have connection drops, duplicate requests, insufficient funds, and concurrent updates been tested?

---

## 26. Hands-On Exercises

Use `tx_lab.accounts` and `tx_lab.transfers` from Section 3. **Do not run exercises that modify data concurrently on the same lab database**, as a committed exercise changes balances assumed by later exercises. When testing without keeping changes, end with `ROLLBACK`.

### Exercise 1 — Identifying Transaction Boundaries

A program in autocommit mode executes:

~~~sql
UPDATE tx_lab.accounts SET balance = balance + 10 WHERE account_id = 1;
UPDATE tx_lab.accounts SET balance = balance - 10 WHERE account_id = 2;
~~~

If the first UPDATE succeeds and the second fails, what happens? Rewrite it so both changes form **one atomic unit**.

### Exercise 2 — Testing Unpersisted Changes

Write SQL to add 100 to account 3, inspect the balance inside the transaction, and then **discard** the change. Run a subsequent SELECT to prove the +100 was not kept.

### Exercise 3 — COMMIT and Rolling Back After Commit

If an UPDATE has already succeeded with COMMIT, can calling `ROLLBACK` in a **new** transaction undo the old UPDATE? Explain.

### Exercise 4 — Aborted Transaction

Write a scenario that causes `CHECK(balance >= 0)` to fail. After PostgreSQL reports the error, why can a subsequent `SELECT` return `25P02`? How do you recover?

### Exercise 5 — SAVEPOINT

Write a transaction that:

1. Adds 10 to A.
2. Creates savepoint `s1`.
3. Adds 20 to B.
4. Rolls back to `s1`.
5. Verifies A still has the change inside the transaction while B does not.
6. Rolls back the whole transaction to restore the lab data to its prior state.

### Exercise 6 — RELEASE SAVEPOINT

Does `RELEASE SAVEPOINT s1` make changes after `s1` durable? What happens if the outer transaction later executes ROLLBACK?

### Exercise 7 — Nested BEGIN

Once `BEGIN` is active, does calling `BEGIN` again create a true nested subtransaction in PostgreSQL? Which command marks a section that can be partially undone?

### Exercise 8 — Two Sessions Reading Uncommitted Data

Session A adds 77 to A without committing. Session B under READ COMMITTED runs `SELECT balance`. Does Session B see the +77? What changes after A runs COMMIT and B runs a new SELECT?

### Exercise 9 — Lock Wait

Write two SQL scripts for Sessions A and B where A updates account 1 without committing, and B sets `SET LOCAL lock_timeout = '2s'` before trying to update the same account. After the timeout, what must be done in both sessions to return the lab to normal?

### Exercise 10 — Default Isolation Level

Under READ COMMITTED, a transaction runs SELECT on a balance twice, while another transaction commits a new balance in between. Are the two SELECTs guaranteed to match? Compare with REPEATABLE READ.

### Exercise 11 — READ UNCOMMITTED

Does PostgreSQL allow a READ UNCOMMITTED transaction to read dirty writes from an uncommitted transaction? Describe the actual behavior.

### Exercise 12 — SERIALIZABLE

Where can `SQLSTATE 40001` occur? When it happens, should you retry **only the final UPDATE** or the **entire transaction**?

### Exercise 13 — Balance Check

Write a conditional update to deduct 200 from account 1 **only if the balance is at least 200**. If the statement returns `UPDATE 0`, what should the application do while inside the transfer transaction?

### Exercise 14 — Recording a Transfer

State the mandatory sequence of SQL statements and checks to transfer 100 from A to B and record `request_key` in the same transaction. Why shouldn't you COMMIT right after debiting A?

### Exercise 15 — Missing Destination Account

In a transfer transaction, debiting account 1 succeeds, but crediting account 999 returns `UPDATE 0`. Does `UPDATE 0` automatically raise a SQL error? What must be done to avoid losing funds?

### Exercise 16 — Duplicate Request

A request with `request_key='payment-42'` has already committed. If an INSERT with the same key is sent again, which constraint triggers? Why shouldn't the client generate a new `request_key` and transfer again?

### Exercise 17 — Network Drop at COMMIT

The client sent COMMIT, but the socket closed before receiving a response. Can you conclude the transaction definitely rolled back? Propose a reconciliation approach.

### Exercise 18 — Deadlock

Transaction A locks account 1 and then wants account 2; transaction B locks account 2 and then wants account 1. What phenomenon and SQLSTATE can occur? Name two design mitigations.

### Exercise 19 — Transactional DDL

Write SQL to create a test table, INSERT one row, and ROLLBACK so the table no longer exists. Name two types of administrative commands that cannot be placed inside a corresponding transaction block.

### Exercise 20 — Transactions in JDBC

List the basic API sequence: acquiring a connection, `setAutoCommit(false)`, PreparedStatement, row count checks, `commit()`, `rollback()`, and connection pool handling.

### Exercise 21 — SELECT FOR UPDATE

Write a query that locks accounts `1,2` in ascending ID order inside a transaction. Why should `SKIP LOCKED` be avoided in this scenario?

### Exercise 22 — Idle in Transaction

A connection runs BEGIN and SELECT, then the application waits 4 minutes for an HTTP API call without committing. List potential harms and fixes.

### Exercise 23 — Time Limits

Write a transaction with `SET LOCAL lock_timeout='2s'` and `SET LOCAL statement_timeout='5s'`. How do these two timeouts differ in scope?

### Exercise 24 — Observing Backends

Write SQL to inspect the current session's PID and its `pg_stat_activity` state. How do you find which PID is blocking another session when you have sufficient privileges?

### Exercise 25 — Emails and Database Transactions

An order is updated to `PAID`, the application sends an email, and then a subsequent SQL statement fails and rolls back. Why doesn't the sent email disappear automatically? Propose an architectural solution to reduce this inconsistency.

### Exercise 26 — Capstone Exercise

Design a transfer workflow in PostgreSQL that guarantees:

- No negative balances.
- No credit recorded when the debit did not happen.
- No duplicate `request_key` recorded twice.
- Deadlock avoidance for account pairs.
- Recovery from SQLSTATE 40001/40P01.
- No double transfer if the client loses the COMMIT response.
- No connection returned to the pool in an aborted state.

Describe transaction boundaries, validation checks, locking techniques, rollback, retries, and reconciliation.

---

## 27. Suggested Solutions

### Exercise 1

Under autocommit, the first statement can **already be committed** even if the second fails. To execute them as one unit:

~~~sql
BEGIN;

UPDATE tx_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

UPDATE tx_lab.accounts
SET balance = balance - 10
WHERE account_id = 2 AND balance >= 10;

-- Application verifies both statements affected exactly one row.
-- Otherwise, issue ROLLBACK instead of COMMIT.
ROLLBACK;
~~~

This example ends with ROLLBACK to avoid modifying the lab. In production code, when all conditions pass, use COMMIT; if any step fails, roll back.

### Exercise 2

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance + 100
WHERE account_id = 3;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
ROLLBACK;
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
~~~

The SELECT inside the transaction shows +100; the SELECT after rollback returns to the balance before the transaction.

### Exercise 3

No. `ROLLBACK` only discards **uncommitted changes of the current transaction**; a previously completed transaction cannot be "undone" by a new transaction's ROLLBACK. Reversing a committed change requires an appropriate business **compensating transaction**, not pretending rollback rewinds history.

### Exercise 4

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = -1
WHERE account_id = 3;
-- Violates CHECK, transaction becomes aborted.
SELECT balance FROM tx_lab.accounts WHERE account_id = 3;
-- May report 25P02.
ROLLBACK;
~~~

The initial error puts the transaction into the aborted state. Subsequent SQL statements are not processed normally until ROLLBACK or rolling back to a valid savepoint.

### Exercise 5

~~~sql
BEGIN;
UPDATE tx_lab.accounts SET balance = balance + 10 WHERE account_id = 1;
SAVEPOINT s1;
UPDATE tx_lab.accounts SET balance = balance + 20 WHERE account_id = 2;
ROLLBACK TO SAVEPOINT s1;
SELECT account_id, balance FROM tx_lab.accounts
WHERE account_id IN (1,2) ORDER BY account_id;
ROLLBACK;
~~~

Inside the transaction, A keeps the +10 from before the savepoint, while B does not keep +20. The final ROLLBACK discards the +10 as well.

### Exercise 6

`RELEASE SAVEPOINT` does not commit the outer transaction. If the outer transaction runs ROLLBACK after RELEASE, uncommitted changes are still discarded. RELEASE only removes the partial-rollback marker.

### Exercise 7

No. Calling `BEGIN` inside an already active transaction does not create a nested subtransaction. Use `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, and `RELEASE SAVEPOINT`.

### Exercise 8

Session B does not see the uncommitted +77 under READ COMMITTED. After A runs COMMIT, a new SELECT statement in B under READ COMMITTED can see the new value. If B is in REPEATABLE READ and already established a snapshot, it can continue seeing the old version until its transaction ends.

### Exercise 9

**Session A:**

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance + 1
WHERE account_id = 1;
-- Leave A open temporarily, switch to B.
~~~

**Session B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
UPDATE tx_lab.accounts
SET balance = balance + 2
WHERE account_id = 1;
-- If timeout occurs:
ROLLBACK;
~~~

**Back to A:**

~~~sql
ROLLBACK;
~~~

Do not leave A with an open transaction once observation is complete.

### Exercise 10

Under READ COMMITTED, each SELECT can acquire a new snapshot and see commits made between the two SQL statements. Under REPEATABLE READ, normal SELECTs within the transaction use a stable transaction snapshot once the snapshot is established.

### Exercise 11

No. PostgreSQL essentially treats `READ UNCOMMITTED` as `READ COMMITTED` and does not permit dirty reads through that isolation level.

### Exercise 12

`40001` can appear during execution or at COMMIT under Serializable. You must retry the **entire transaction logic**, including earlier SELECTs that drove decisions, using a new snapshot and a bounded retry policy. Do not retry only the last statement.

### Exercise 13

~~~sql
BEGIN;
UPDATE tx_lab.accounts
SET balance = balance - 200
WHERE account_id = 1 AND balance >= 200;
-- If UPDATE 0, ROLLBACK.
ROLLBACK;
~~~

`UPDATE 0` is not by itself a SQL error, but it indicates **failure to satisfy the business condition** when the debit is required. The application must abort the transaction and not apply the credit.

### Exercise 14

Order:

1. BEGIN on a single connection.
2. Lock both accounts in consistent ID order.
3. Verify exactly two rows were returned.
4. Perform conditional debit and check `UPDATE 1`.
5. Perform credit and check `UPDATE 1`.
6. INSERT transfer with UNIQUE request key.
7. COMMIT if every step succeeds, otherwise ROLLBACK.

Never COMMIT immediately after the debit because if the credit fails, the deducted funds can no longer be atomically rolled back.

### Exercise 15

`UPDATE 0` is a SQL statement that **executed successfully without matching rows**; it does not automatically abort the transaction. The application must inspect affected rows and **ROLLBACK** the entire transaction to cancel the debit.

### Exercise 16

The UNIQUE constraint on `transfers.request_key` raises error `23505` when inserting a duplicate key. When retrying the same request, query the request key and verify the payload/outcome; generating a new key risks transferring funds a second time.

### Exercise 17

You cannot tell from a dropped socket that COMMIT rolled back. Reconcile against an up-to-date authoritative source and check `request_key` / business outcome; if absent, retry with the **same idempotency key** under duplicate-prevention safeguards.

### Exercise 18

That is a deadlock; PostgreSQL can raise `40P01` and abort one transaction. Reduce risk through **consistent ID lock ordering** and short transactions; you can also implement bounded full-transaction retries after a deadlock.

### Exercise 19

~~~sql
BEGIN;
CREATE TABLE tx_lab.rollback_demo (
    id INTEGER PRIMARY KEY
);
INSERT INTO tx_lab.rollback_demo(id) VALUES (1);
ROLLBACK;
~~~

The table created inside the transaction is removed on rollback. Example commands that must run outside a transaction block: `CREATE DATABASE` and `CREATE INDEX CONCURRENTLY`.

### Exercise 20

On a single connection:

~~~text
getConnection()
  → setAutoCommit(false)
  → SELECT/UPDATE/INSERT via PreparedStatement
  → verify row counts / constraints
  → commit() if all steps succeed
  → rollback() on SQLException/RuntimeException
  → reset/close or invalidate connection according to pool state
~~~

Do not let pool-state restoration errors hide the original exception; when the connection or rollback fails, discard/invalidate the connection via the pool's mechanism.

### Exercise 21

~~~sql
BEGIN;
SELECT account_id, balance
FROM tx_lab.accounts
WHERE account_id IN (1,2)
ORDER BY account_id
FOR UPDATE;
ROLLBACK;
~~~

`SKIP LOCKED` can skip one of the two accounts if it is locked; this is unacceptable in a transaction that must verify and update **both accounts**.

### Exercise 22

A transaction waiting 4 minutes on HTTP can hold locks and snapshots, delay VACUUM, and leave the backend `idle in transaction`. Fix by shortening transactions, never waiting on external networks inside a transaction, setting appropriate timeouts, using an outbox for side effects needing state synchronization, and rolling back on every error path.

### Exercise 23

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
SELECT account_id
FROM tx_lab.accounts
WHERE account_id = 1
FOR UPDATE;
ROLLBACK;
~~~

`lock_timeout` bounds the **time spent waiting to acquire a lock**, whereas `statement_timeout` bounds the **execution duration of a statement** overall.

### Exercise 24

~~~sql
SELECT pid, state, xact_start, wait_event_type, wait_event
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

With sufficient privileges:

~~~sql
SELECT
    pid AS blocked_pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Do not terminate backends without first identifying ownership and impact.

### Exercise 25

COMMIT/ROLLBACK only governs changes inside the **database transaction**. An email sent via an external system does not automatically un-send when the database rolls back. Use a **transactional outbox** (record the event inside the same DB transaction, send after commit), idempotent/retrying consumers, and reconciliation workflows.

### Exercise 26

A combined design:

~~~text
Client sends stable request_key
        |
        v
Acquire one connection, BEGIN
        |
        v
Ensure UNIQUE/idempotent request_key
        |
        v
Lock accounts in ascending ID order
        |
        v
Verify both accounts exist and amount > 0
        |
        v
UPDATE debit WHERE balance >= amount
   ├─ UPDATE 0 → ROLLBACK
   └─ UPDATE 1
        |
        v
UPDATE credit, require UPDATE 1
   ├─ mismatch → ROLLBACK
   └─ match
        |
        v
Insert transfer / request key, verify success
        |
        v
COMMIT
   ├─ success → return result
   ├─ 40001/40P01 → bounded retry of entire transaction
   └─ connection lost during commit → reconcile request_key before retry
~~~

The database enforces a non-negative balance CHECK, FKs for both accounts, and a UNIQUE request key. Return the connection to the pool only after ending the transaction and resetting state cleanly; if a severe connection error occurs or rollback cannot be confirmed, the pool must discard/invalidate the connection.

This is a **logical design**. Real financial systems also require an immutable ledger, exact balance accounting, concurrent retry handling, multi-account lock ordering, auditing, reconciliation, and corresponding operational safeguards.

---

## 28. Takeaways to Remember

### 28.1. Even a Single SQL Statement Runs in a Transaction

Autocommit does not mean "no transaction"; it means **one transaction per statement**. You only need explicit boundaries with BEGIN/COMMIT or transaction APIs when multiple statements must form one unit.

### 28.2. A Transaction Is Not Guaranteed to Succeed Just Because No Errors Occurred Before COMMIT

Deferred constraints, serialization conflicts, I/O failures, or dropped connections can still affect the final outcome. Always handle errors on commit.

### 28.3. ROLLBACK Only Undoes Uncommitted Changes

Do not rely on rollback to undo an already committed event or a sent email. Reversing business actions requires **compensating transactions** and audit policies.

### 28.4. A SQL Error Can Render the Entire Transaction Unusable

After an error, `25P02` merely tells you the transaction is already aborted; the root cause lies in an earlier statement. Identify the root cause and ROLLBACK or revert to a valid savepoint.

### 28.5. Never Record "COMMIT Succeeded" When Uncertain

When a socket drops immediately after sending COMMIT, the outcome may be unknown. The design needs a request key and reliable reconciliation rather than assuming a timeout means a rollback.

### 28.6. Keep Transactions as Short as Possible, Yet Semantically Complete

Splitting a transaction in two may reduce lock hold time, but it **breaks atomicity** if business rules require both parts to succeed together. Conversely, holding a transaction open during external API calls prolongs locks and risk. Define atomic database scopes alongside outbox/saga architectures when spanning beyond a single database.

---

## 29. Summary

In PostgreSQL, **`BEGIN` starts an explicit transaction, `COMMIT` confirms valid changes, and `ROLLBACK` discards uncommitted changes**. These three commands establish the boundaries of a unit of work and govern when changes become visible to other transactions.

The transaction lifecycle must be understood end-to-end:

- Transaction starts → execute SQL → **COMMIT** or **ROLLBACK**.
- If a SQL statement fails inside a transaction, the transaction typically enters the **aborted** state; `25P02` requires rolling back or reverting to a valid savepoint before proceeding.
- **SAVEPOINT** supports partial rollback, though `RELEASE SAVEPOINT` is not an independent commit.
- PostgreSQL uses **MVCC**, isolation levels, and row locks to coordinate concurrent transactions. READ COMMITTED is not SERIALIZABLE, and SERIALIZABLE may require retries.
- A transaction belongs to **one connection**. When using JDBC or connection pools, ensure commit/rollback happens in every branch and never return a broken session to the pool.
- For operations such as fund transfers, verify **affected row counts**, constraints, lock ordering, request keys, and handle uncertain COMMIT responses.
- Never keep a transaction open while waiting on external network calls; use outbox/idempotency or appropriate distributed patterns when needed.
- Monitor `pg_stat_activity`, lock waits, timeouts, and long-running transactions to protect the system.

Solid implementation mindset: **define the atomic business unit → acquire one connection → BEGIN → validate data and acquire appropriate locks → perform all updates with result checks → COMMIT if completely valid, ROLLBACK on failure → handle retries and uncertain outcomes → release the connection and monitor operations**.
