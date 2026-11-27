# Atomicity, Consistency, Isolation, and Durability in PostgreSQL

## 1. A Fund Transfer Must Succeed as One Unit of Work

Suppose a banking application has two accounts:

| Account | Account Owner | Initial Balance |
| --- | --- | ---: |
| 101 | An | 500.00 |
| 202 | Bình | 200.00 |

An wants to transfer 100.00 to Bình. The application must perform three related changes:

1. Deduct 100.00 from An's account.
2. Add 100.00 to Bình's account.
3. Record a transfer history entry.

If the system performs only step 1 and hits a network failure before step 2, the data becomes wrong: the source account lost money while the destination account never received it. If both balance updates succeed yet the transfer history is not recorded, reporting and reconciliation become inconsistent. If two people withdraw from the same account at the same time, an unsafe update pattern can allow overdrawing the balance.

PostgreSQL solves most of these problems through **transactions**. A transaction groups related SQL operations into a single unit of processing.

The four properties are commonly abbreviated as **ACID**:

| Letter | Term | Practical Meaning |
| --- | --- | --- |
| **A** | **Atomicity** | Either all changes belonging to the transaction are confirmed as one unit, or none of the transaction's changes are kept |
| **C** | **Consistency** | A transaction must move data from one valid state to another valid state, obeying defined constraints and business invariants |
| **I** | **Isolation** | Concurrent transactions are controlled to limit or eliminate unwanted interactions according to the chosen isolation level |
| **D** | **Durability** | After `COMMIT` is confirmed under appropriate durability settings, changes can be recovered across crashes via storage/WAL mechanisms |

ACID does not mean "every SQL statement is always right," "every application automatically has zero race conditions," or "data can never be lost in any disaster." Each letter has its own guarantee scope, configuration requirements, and design responsibilities.

> **Foundational mindset:** transactions guarantee that a database unit of work has a clear boundary. However, the application must still correctly define what needs to change, what constitutes a valid state, and how concurrent conflicts are handled.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain the four ACID properties using concrete business scenarios.
2. Use `BEGIN`, `COMMIT`, and `ROLLBACK` to manage PostgreSQL transactions.
3. Write a fund transfer that validates success at every step.
4. Distinguish between statement errors, transaction errors, and `SAVEPOINT`.
5. Distinguish database constraints from business invariants that cannot be enforced by a simple `CHECK` alone.
6. Explain MVCC and read behavior across multiple concurrent sessions.
7. Differentiate PostgreSQL's `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` levels.
8. Understand anomalies such as dirty reads, nonrepeatable reads, phantom reads, lost updates, and write skew.
9. Know when to use row locks, atomic conditional updates, or full-transaction retries.
10. Understand the roles of WAL, `fsync`, `synchronous_commit`, backups, and replication in durability.
11. Apply transactions in Java/JDBC and recognize boundaries when operations extend outside a single database.
12. Inspect open transactions, lock waits, and risky operational habits.

## 3. Setting Up the Lab Dataset

Run these examples in a **test database**. Some sections require opening **two independent connections** or intentionally triggering errors/rollbacks; never run them directly against production data.

### 3.1. Creating the Schema and Accounts Table

```sql
CREATE SCHEMA IF NOT EXISTS acid_lab;

CREATE TABLE acid_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0)
);
```

Key design decisions:

- `account_id` is the primary key, uniquely identifying each account.
- `balance` uses `numeric(14,2)` for exact decimal monetary values rather than `float`.
- `NOT NULL` forbids missing balances.
- `CHECK (balance >= 0)` prevents a row from storing a negative balance at the table level.
- These constraints protect individual pieces of data, but do not yet express every rule of a transfer.

Load data:

```sql
INSERT INTO acid_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

A third account is included for practicing multi-transaction concurrency scenarios.

### 3.2. Transfer History Table

```sql
CREATE TABLE acid_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    from_account_id bigint NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    CONSTRAINT chk_distinct_accounts
        CHECK (from_account_id <> to_account_id)
);
```

The `transfers` table stores history, while `accounts` stores balances. Both tables must be updated in **the same transaction** when business rules require them to stay consistent.

To inspect balances:

```sql
SELECT account_id, owner_name, balance
FROM acid_lab.accounts
ORDER BY account_id;
```

With the freshly loaded data, the total balance is 800.00:

```sql
SELECT SUM(balance) AS total_balance
FROM acid_lab.accounts;
```

**Experiment note:** some following examples use `ROLLBACK` to preserve sample data, while others use `COMMIT` to illustrate confirmed state. If you want exact starting numbers again, use a fresh test database or explicitly restore the dataset before each scenario.

## 4. Lifecycle of a PostgreSQL Transaction

An explicit transaction looks like:

```sql
BEGIN;

-- One or more SQL statements belonging to the same transaction.
UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

COMMIT;
```

Or, to discard uncommitted changes:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

ROLLBACK;
```

Key commands:

| Command | Effect |
| --- | --- |
| `BEGIN` or `START TRANSACTION` | Starts an explicit transaction |
| `COMMIT` | Requests confirmation of the transaction |
| `ROLLBACK` | Discards the transaction's uncommitted changes |
| `SAVEPOINT name` | Sets a partial-recovery marker inside the transaction |
| `ROLLBACK TO SAVEPOINT name` | Reverts to the marker without aborting the whole transaction |
| `RELEASE SAVEPOINT name` | Removes a savepoint marker that is no longer needed |
| `SET TRANSACTION ISOLATION LEVEL ...` | Sets the isolation level while still valid to configure |

### 4.1. What Happens Without `BEGIN`?

In many tools and drivers in **autocommit** mode, an individual SQL statement is executed in its own transaction and committed upon success. For example:

```sql
UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 202;
```

If the tool runs each statement under autocommit, **these two UPDATEs do not form a shared transaction**. If the second statement fails, the first may already be committed.

Therefore, never assume that "two SQL statements placed next to each other in a file" are automatically atomic together.

### 4.2. `COMMIT` Is Different from a Successful `UPDATE`

An `UPDATE` reporting one row updated means the statement succeeded **inside the current transaction**. It does not mean the transaction has been committed.

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101
RETURNING account_id, balance;

-- The result in the same session already reflects the change.
ROLLBACK;
```

After `ROLLBACK`, the +50.00 change is not retained.

### 4.3. A Transaction Belongs to One Connection

An explicit transaction is bound to **a single PostgreSQL session/connection**. You cannot run `BEGIN` on Connection A and expect an `UPDATE` on Connection B to automatically join that same transaction.

This is crucial when applications use a **connection pool**, multiple Java threads, or multiple services. Every operation that must be atomic together must execute within a **properly managed transaction scope**.

### 4.4. A Transaction Can Fail at `COMMIT`

Not every successful `UPDATE` guarantees that `COMMIT` will succeed. Certain errors are only detected at transaction end, for example:

- Violations of `DEFERRABLE` constraints deferred until `COMMIT`.
- Serialization failures when `SERIALIZABLE` transactions conflict.
- Certain I/O errors or dropped connections during confirmation.

Applications must handle the **result of COMMIT**, not just the results of preceding SQL statements.

## 5. Atomicity: All or Nothing

**Atomicity** requires that a transaction's changes be treated as **one unit** when deciding to commit or roll back.

For a transfer, the three changes are:

```text
Debit source
     |
     v
Credit destination
     |
     v
Record transfer history
     |
     +--> COMMIT: confirm all changes together
     |
     +--> ROLLBACK: keep none of the transaction's changes
```

### 5.1. Simple Example Using One Transaction

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 202;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, 100.00);

-- Use ROLLBACK in this exercise to avoid altering sample data.
ROLLBACK;
```

All three operations share the same transaction, so `ROLLBACK` cancels all three.

**However, this example is still not safe enough for production.** If an account ID does not exist, `UPDATE` can match **0 rows** without raising an error. A transaction can commit even though the business condition was never satisfied if the developer forgets to check.

### 5.2. Step-by-Step Checked Transfer Using PL/pgSQL

The example below executes the transfer logic and intentionally rolls back for practice:

```sql
BEGIN;

DO $transfer$
DECLARE
    v_amount numeric(14,2) := 100.00;
BEGIN
    -- Step 1: debit source without letting balance drop below 0.
    UPDATE acid_lab.accounts
    SET balance = balance - v_amount
    WHERE account_id = 101
      AND balance >= v_amount;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Source account does not exist or has insufficient funds';
    END IF;

    -- Step 2: credit the exact destination account.
    UPDATE acid_lab.accounts
    SET balance = balance + v_amount
    WHERE account_id = 202;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Destination account does not exist';
    END IF;

    -- Step 3: record history.
    INSERT INTO acid_lab.transfers
        (from_account_id, to_account_id, amount)
    VALUES
        (101, 202, v_amount);
END;
$transfer$;

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

ROLLBACK;
```

In PL/pgSQL, the `FOUND` variable after `UPDATE` indicates whether any row was updated. If either the debit or credit fails to update the required row, `RAISE EXCEPTION` fails the statement and puts the transaction in an error state; the application/session must roll back rather than committing as if it succeeded.

If every step succeeds and you replace `ROLLBACK` with `COMMIT`:

- An goes from 500.00 down to 400.00.
- Bình goes from 200.00 up to 300.00.
- `transfers` gains one row.
- The combined balance of the two accounts remains 700.00.

**You must also ensure the application does not unintentionally send the same transfer request multiple times.** An atomic transaction cannot by itself recognize two duplicate HTTP requests; the idempotency section explains this further.

### 5.3. What Does `balance >= amount` Solve?

Suppose the source account holds only 100.00, and two requests simultaneously try to transfer 80.00.

If the application reads the balance and computes it itself:

```text
SELECT balance --> 100
App computes   --> 20
UPDATE balance = 20
```

both requests can read 100 before writing, leading to a logic bug—especially if the write lacks both a condition and proper locking.

A safer pattern:

```sql
UPDATE acid_lab.accounts
SET balance = balance - 80.00
WHERE account_id = 101
  AND balance >= 80.00
RETURNING balance;
```

PostgreSQL checks the predicate and modifies the row **in a single statement**. When multiple transactions compete on the same row, row locking and predicate re-evaluation under the appropriate isolation level prevent overdrawing. The application must still verify **whether exactly one row was returned**.

### 5.4. Atomicity Does Not Make SQL Business-Correct Automatically

A transaction like this can still commit:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 101;

-- Developer forgot to credit the destination account.
COMMIT;
```

The database cannot guess that the application "meant to include one more step." Atomicity ensures **the statements actually executed in the transaction** commit or roll back together; it does not add omitted steps.

## 6. Atomicity When a Statement Errors

### 6.1. A Constraint Error Prevents the Transaction from Continuing Normally

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 5.00
WHERE account_id = 101;

-- Violates CHECK (balance >= 0).
UPDATE acid_lab.accounts
SET balance = -1.00
WHERE account_id = 202;

-- In the same transaction, subsequent SQL typically fails with:
-- current transaction is aborted, commands ignored ...
SELECT * FROM acid_lab.accounts;

ROLLBACK;
```

After the second `UPDATE` errors, the transaction is in a failed state. You cannot continue running normal commands and commit successfully simply by ignoring the error.

`ROLLBACK` ends the transaction and also discards the earlier `+5.00` change.

### 6.2. `ROLLBACK` and `COMMIT` Are Not Interchangeable Choices

Applications should:

- `COMMIT` when **all conditions have succeeded** and the transaction is not in an error state.
- `ROLLBACK` when an error occurs or business rules are not satisfied.
- Never blindly call `COMMIT` inside a `finally` block without knowing whether earlier steps succeeded or failed.

If the connection drops while sending `COMMIT`, the application can enter an uncertain state where it **does not know whether the server committed or not**. This is why critical workflows need idempotency and reconciliation instead of assuming "connection lost means not committed."

## 7. `SAVEPOINT`: Partial Undo Within a Transaction

`SAVEPOINT` creates a marker to roll back changes made after that marker while keeping valid changes made before it.

Example:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

SAVEPOINT before_optional_step;

-- Optional operation fails due to CHECK:
UPDATE acid_lab.accounts
SET balance = -5.00
WHERE account_id = 202;

-- After the error, revert the transaction to the savepoint:
ROLLBACK TO SAVEPOINT before_optional_step;

-- Now execution can continue:
SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

-- Keep initial lab data unchanged.
ROLLBACK;
```

In this example:

- The `+10.00` change happened **before** the savepoint.
- The invalid statement happened **after** the savepoint.
- `ROLLBACK TO SAVEPOINT` restores state to right after the `+10.00` change.
- The final `ROLLBACK` cancels the entire transaction, leaving the test dataset untouched.

In a real workflow, `RELEASE SAVEPOINT` can discard a marker once no longer needed. However, **a savepoint does not create an independent transaction that commits on its own**: if the parent transaction rolls back, even changes "kept past the savepoint" are discarded.

### 7.1. Do Not Use Savepoints to Mask Mandatory Business Errors

In a fund transfer, **crediting the destination account** must never be treated as optional. If that step fails, the entire transfer transaction must roll back. Savepoints fit operations that are genuinely optional by business rules—such as an optional secondary note—not bypassing consistency violations.

### 7.2. Distinguishing Statement Rollback from Transaction Rollback

PostgreSQL ensures a regular data statement does not leave **partial table changes** behind when that statement fails. Yet if an error happens inside an explicit transaction, the transaction becomes aborted until rolled back or reverted to a valid savepoint.

In applications using a transaction manager, catching an exception does not automatically restore the connection to a healthy state; proper rollback coordination is still required.

## 8. Operations That Do Not Roll Back the Way Beginners Expect

Atomicity applies to **transactional data changes**, but you should not assume *every* side effect or counter reverts as if nothing happened.

### 8.1. Sequences Do Not Return Allocated Numbers

PostgreSQL uses sequences, such as via `GENERATED ... AS IDENTITY`, to generate IDs. Values already drawn from a sequence **are not returned** just because a transaction rolls back.

For example, `transfers` uses identity:

```sql
BEGIN;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES (101, 202, 1.00)
RETURNING transfer_id;

ROLLBACK;
```

The inserted row is canceled. Yet the allocated identity number may **not be reused**, leaving gaps in IDs.

**Do not treat an ID sequence as proof that no rollbacks occurred**, and do not require IDs to be contiguous. If a business rule requires gap-free regulatory document numbers, design a dedicated numbering mechanism aligned with those compliance rules.

### 8.2. Many DDL Statements Roll Back, but Not All

PostgreSQL supports transactional DDL for many operations:

```sql
BEGIN;

CREATE TABLE acid_lab.temporary_demo (
    id integer PRIMARY KEY
);

ROLLBACK;
```

After `ROLLBACK`, the table created inside the transaction is not kept.

However, commands such as `CREATE DATABASE`, `VACUUM`, or `CREATE INDEX CONCURRENTLY` **cannot run inside an explicit transaction block**. Do not generalize that every schema or administrative command rolls back like an `INSERT`.

### 8.3. Effects Outside the Database Do Not Automatically Roll Back

If a transaction sends an email, calls a payment API, or writes a file to an external system before committing, PostgreSQL's `ROLLBACK` **cannot recall the email**, reverse the API call, or delete that file.

PostgreSQL transactions guarantee the scope managed by the database. External side effects must be coordinated through system design, such as a **transactional outbox**, idempotency, or compensating actions.

## 9. Consistency: Valid Data State Before and After a Transaction

**Consistency** does not simply mean "everyone sees the same data at every instant." In ACID, **Consistency** refers to satisfying **constraints and invariants** whenever a transaction succeeds.

Examples of invariants:

- Every account has a unique primary key.
- Balances are non-negative.
- Transfer records have positive amounts.
- Referenced source/destination accounts actually exist.
- In an internal transfer, source + destination balance total remains unchanged.
- A paid order cannot transition into an illegal state.

PostgreSQL helps enforce many invariants via:

- Accurate data types.
- `PRIMARY KEY`.
- `UNIQUE`.
- `NOT NULL`.
- `CHECK`.
- `FOREIGN KEY`.
- `EXCLUDE` constraints where applicable.
- Locking, triggers, or transactional logic when a rule cannot be expressed as a simple constraint.

### 9.1. `CHECK` Prevents Negative Balances

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = -100.00
WHERE account_id = 101;

-- PostgreSQL reports a CHECK violation.
ROLLBACK;
```

`CHECK (balance >= 0)` stops an invalid row from being saved. Still, it cannot by itself verify that debits and credits balance across two accounts.

### 9.2. `FOREIGN KEY` Prevents Dangling References

```sql
BEGIN;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 999999, 10.00);

-- Foreign key violation on to_account_id.
ROLLBACK;
```

If account 999999 does not exist, PostgreSQL rejects the transfer log row referencing it.

### 9.3. A Single-Row `CHECK` Cannot Enforce Multi-Table Invariants

A rule like:

```text
SUM(balance across all accounts)
must equal
the total funds legitimately recorded by the system.
```

spans multiple rows and possibly multiple tables. You cannot treat `CHECK (balance >= 0)` as protecting that aggregate invariant.

A transaction could even update an arbitrary incorrect amount while still passing every single-row `CHECK`.

To protect multi-row or multi-table invariants, you may need:

- Application logic within **a single transaction**.
- Atomic conditional updates.
- Appropriate row locks or business-level locks.
- A suitable isolation level, sometimes `SERIALIZABLE`.
- Triggers or normalized schemas with fewer redundant states.
- Reconciliation processes to detect discrepancies caused by external systems.

### 9.4. ACID Consistency Depends on Declared and Enforced Rules

PostgreSQL does not know a business's definition of a "valid order" unless that rule lives in the schema or executed logic.

Two distinct outcomes:

- **Database rejects** a value violating `CHECK`/`FK`: the constraint is protected.
- **Application forgets** a verification step yet commits schema-valid changes: business integrity can be violated even though the database raised no error.

Thus, **Consistency is a shared responsibility of the data model, transactions, and application**, not a single configuration toggle.

## 10. Constraints That Can Be Deferred Until `COMMIT`

PostgreSQL allows **certain constraint types** to be declared `DEFERRABLE`, meaning evaluation can be postponed until the end of the transaction.

Example:

```sql
CREATE TABLE acid_lab.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE acid_lab.employees (
    employee_id integer PRIMARY KEY,
    employee_name text NOT NULL,
    department_id integer NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES acid_lab.departments(department_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Then test a transaction:

```sql
BEGIN;

SET CONSTRAINTS fk_employee_department DEFERRED;

-- Temporarily reference department 50 before it exists:
INSERT INTO acid_lab.employees
    (employee_id, employee_name, department_id)
VALUES
    (1, 'An', 50);

-- Create that department in the same transaction:
INSERT INTO acid_lab.departments
    (department_id, department_name)
VALUES
    (50, 'Research');

-- Before COMMIT, the FK is satisfied.
ROLLBACK;
```

Use `ROLLBACK` to preserve lab data. If replaced with `COMMIT` and all constraints hold at evaluation time, the transaction succeeds.

**Important notes:**

- Only constraints **declared `DEFERRABLE`** can be deferred.
- `CHECK` and `NOT NULL` cannot be deferred this way in PostgreSQL.
- For FKs, `NO ACTION` can be deferred when the constraint is `DEFERRABLE`; `RESTRICT` checks immediately and is not equivalent to a deferred `NO ACTION`.
- When a deferred constraint fails at `COMMIT`, the transaction is not committed.

This example shows an **intermediate state** inside a transaction may temporarily not satisfy a deferred FK, yet the committed state must satisfy the final rule. Do not use deferred constraints if the application cannot control intermediate states safely.

## 11. Isolation: Why Concurrent Transactions Are Harder Than Single Transactions

Suppose two transactions operate on the same table simultaneously. The issue is not only whether each transaction commits or rolls back, but also **when each transaction sees the other's changes** and **how their final outcomes interact**.

Example:

```text
T1: Read balance 100
T2: Read balance 100
T1: Decide to withdraw 80
T2: Decide to withdraw 80
T1: Write change
T2: Write change
```

If the application treats both reads of 100 as independent proof that both withdrawals are valid, the design is flawed.

**Isolation** is the set of rules governing visibility and conflicts among concurrent transactions. PostgreSQL provides multiple isolation levels; higher levels prevent more anomalies at the cost of overhead and potential **retries**.

### 11.1. Commonly Discussed Anomalies

| Anomaly | Brief Description |
| --- | --- |
| Dirty read | T1 reads uncommitted changes made by T2 |
| Nonrepeatable read | T1 reads the same row twice and sees different values because T2 committed in between |
| Phantom read | T1 repeats a predicate query and sees the matching row set change because T2 committed |
| Lost update | An update based on stale data overwrites or loses another concurrent update's intent |
| Write skew | Two transactions read a shared invariant, update **different rows**, and both commit into a state violating the invariant |
| Serialization anomaly | Concurrent execution results are not equivalent to any valid serial ordering of the transactions |

Not all anomalies behave identically across isolation levels, and database implementations differ from purely theoretical textbook examples.

### 11.2. PostgreSQL Uses MVCC

**Multi-Version Concurrency Control (MVCC)** lets PostgreSQL maintain multiple versions of data so reads can observe an appropriate snapshot without always waiting on every write transaction.

Conceptually:

```text
T1 reading data at snapshot A
                |
                v
  [Value committed before A]

T2 updates the same row
                |
                v
           [New version]
                |
                +-- Uncommitted: T1 does not dirty-read this version
                |
                +-- Committed: whether T1's later read sees it
                    depends on isolation level
```

MVCC does not mean transactions never need locks. `UPDATE`, `DELETE`, and `SELECT ... FOR UPDATE` still use appropriate locking mechanisms; they can block or trigger conflicts.

## 12. PostgreSQL Isolation Levels

PostgreSQL accepts four standard SQL names, though `READ UNCOMMITTED` **behaves equivalently to `READ COMMITTED`**.

| PostgreSQL Level | Dirty Read | Nonrepeatable Read | Phantom Read | Serialization Anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` (acts like READ COMMITTED) | No | Possible | Possible | Possible |
| `READ COMMITTED` | No | Possible | Possible | Possible |
| `REPEATABLE READ` | No | No | No in PostgreSQL | Still possible, e.g., write skew |
| `SERIALIZABLE` | No | No | No | Prevented via SSI tracking; a transaction may have to rollback/retry |

This table shows **what can occur**, not that every schedule necessarily triggers an anomaly. How an application uses locks, conditional updates, and constraints also shapes real-world outcomes.

### 12.1. Default Level

In PostgreSQL, the default isolation level is normally **`READ COMMITTED`**.

Check it:

```sql
SHOW default_transaction_isolation;
```

Inspecting the setting does not change the isolation level of an already running transaction.

### 12.2. Setting the Isolation Level at Transaction Start

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT account_id, balance
FROM acid_lab.accounts
ORDER BY account_id;

ROLLBACK;
```

Or:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM acid_lab.accounts;

ROLLBACK;
```

The isolation level must be set **before the transaction performs operations that disallow changing isolation**; in PostgreSQL, `SET TRANSACTION ISOLATION LEVEL` must run before the transaction's first query or data-modifying statement. Do not open a transaction, read data, and then expect to upgrade isolation retroactively for earlier reads.

### 12.3. Each Transaction Chooses Its Own Isolation Level

Isolation level is not a system-wide switch controlled by a single request's wish. If a workflow requires serializable guarantees across multiple participants, you must ensure the participating transactions follow the corresponding model; one transaction alone running at `SERIALIZABLE` cannot automatically make every other transaction business-safe.

## 13. `READ COMMITTED`: Each Statement Normally Sees a New Snapshot

Under `READ COMMITTED`, a normal `SELECT` sees changes **committed before that statement began** according to that statement's snapshot.

Within the same transaction, two `SELECT` statements run at different times can observe different results if another transaction commits between them.

### 13.1. Two-Session Experiment: Nonrepeatable Read

Open **Session A** and **Session B** using two `psql` connections or two separate clients.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- Suppose the initial result is 500.00.
```

Keep Session A open.

**Session B:**

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
```

Return to **Session A:**

```sql
SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- This read can now see 550.00.

ROLLBACK;
```

When A reads before B commits, then reads again after B commits, A's two reads differ.

**This is a nonrepeatable read**, not a dirty read. A only saw B's change **after B committed**.

This experiment **intentionally modified data** in Session B. To reset back to 500.00, use a fresh test database or perform a controlled reversal of `+50.00` once the test sessions are done.

### 13.2. Read Committed Does Not Dirty-Read

If Session B updates a row and **has not committed yet**, Session A does not see that uncommitted value with a standard `SELECT`.

PostgreSQL does not expose true dirty reads merely by specifying `READ UNCOMMITTED`. In PostgreSQL, it behaves like `READ COMMITTED`.

### 13.3. Read Committed Can Also Observe Phantoms

Suppose A counts:

```sql
SELECT COUNT(*)
FROM acid_lab.accounts
WHERE balance >= 200.00;
```

B then inserts a matching account or updates an account into the filter range and commits. When A re-runs `COUNT` inside the same `READ COMMITTED` transaction, it can see a different count.

This is a **phantom read**: the set of rows matching a predicate changes between reads.

### 13.4. Statement Snapshots Do Not Mean the Whole Transaction Is Stable

`READ COMMITTED` fits many standard applications, yet if a business process needs to read multiple tables and reason over **one consistent point-in-time snapshot across multiple statements**, it may be insufficient.

Never pick an isolation level based on "the default must be safe for every report" without identifying the invariants that need protection.

## 14. `REPEATABLE READ`: A More Stable Snapshot

In PostgreSQL, a `REPEATABLE READ` transaction uses a stable snapshot for normal reads throughout the transaction, starting when the snapshot is established under PostgreSQL rules.

### 14.1. Two-Session Experiment

Start from a known state, e.g., account 101 at 500.00.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- 500.00
```

**Session B:**

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
```

**Session A:**

```sql
SELECT balance
FROM acid_lab.accounts
WHERE account_id = 101;
-- In A's snapshot, this is still 500.00.

ROLLBACK;
```

A new transaction opened afterwards will see 550.00.

**Key detail:** A must run the read that establishes its snapshot **before B commits**. Merely sending `BEGIN` and not reading anything until after B commits does not guarantee A's snapshot precedes B's commit.

### 14.2. PostgreSQL's Repeatable Read Prevents Phantom Reads

In PostgreSQL, `REPEATABLE READ` is implemented on top of snapshot isolation, so repeated queries inside a transaction do not see new rows committed by other transactions after the snapshot was taken. This is stronger than the minimum requirement some SQL textbooks attach to the name Repeatable Read.

Even so, `REPEATABLE READ` is still **not equivalent to `SERIALIZABLE`** in all scenarios.

### 14.3. Conflict When Writing the Same Row

If Transaction A under `REPEATABLE READ` already holds a snapshot, Transaction B modifies a row and commits, and A later tries to `UPDATE` that exact row, PostgreSQL can raise:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

A must roll back and retry per workflow policy. Do not assume "because A's snapshot is stable, PostgreSQL will just overwrite the newer value."

On the other hand, anomalies involving **different rows**—such as write skew—can still happen.

## 15. Write Skew: Two Transactions Both Valid When Reading, Both Wrong When Committing

This is a classic scenario illustrating the difference between `REPEATABLE READ` and `SERIALIZABLE`.

Suppose an on-call shift must always have **at least one doctor on duty**.

### 15.1. Creating the Demonstration Table

```sql
CREATE TABLE acid_lab.on_call (
    doctor_id bigint PRIMARY KEY,
    doctor_name text NOT NULL,
    on_duty boolean NOT NULL
);

INSERT INTO acid_lab.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'Doctor A', TRUE),
    (2, 'Doctor B', TRUE);
```

Business invariant:

```text
Count of doctors with on_duty = TRUE must be >= 1
```

A row constraint `CHECK (on_duty IN (TRUE,FALSE))` only validates each row individually and **cannot enforce the total number of doctors on duty**.

### 15.2. Two Transactions Under `REPEATABLE READ`

Suppose both doctors want to go off duty, each willing to leave only if **the other remains on duty**.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS available_doctors
FROM acid_lab.on_call
WHERE on_duty = TRUE;
-- 2
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS available_doctors
FROM acid_lab.on_call
WHERE on_duty = TRUE;
-- 2
```

**Session A** updates doctor 1:

```sql
UPDATE acid_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
```

**Session B** updates doctor 2:

```sql
UPDATE acid_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
```

Then both sessions `COMMIT`.

Because they update **two disjoint rows**, this execution can allow both to commit under `REPEATABLE READ`, leaving the final table as:

| doctor_id | on_duty |
| ---: | --- |
| 1 | FALSE |
| 2 | FALSE |

Both doctors went off duty even though the rule requires at least one on duty.

### 15.3. Why Isn't This a Regular Lost Update?

Neither row was overwritten by the other transaction. Each transaction edited a different row, yet both relied on a **conclusion drawn from a set of rows**: "two doctors are currently on duty."

Each transaction saw a valid snapshot for its own read, yet the combined outcome **violates a multi-row invariant**.

This is **write skew**, a serialization anomaly that snapshot isolation allows.

### 15.4. Retrying with `SERIALIZABLE`

Reset the practice table so both doctors are on duty, then run both transactions at:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

using the same pattern: both read the on-duty count, A updates row 1, B updates row 2.

PostgreSQL uses **Serializable Snapshot Isolation (SSI)** to track read/write dependencies that could produce serialization anomalies. In this conflicting schedule, the system prevents both transactions from committing into an outcome impossible under any valid serial ordering. One transaction can be aborted with `SQLSTATE 40001`.

**After that error, the application must retry the entire transaction**, starting from reading the on-duty count. The retry will see one doctor already off duty and refuse to let the remaining doctor leave when the invariant check runs.

**Do not think `SERIALIZABLE` somehow infers "at least one doctor must stay on duty" on its own.** PostgreSQL prevents non-serializable concurrent schedules; the application must still **execute the invariant check** inside the transaction.

### 15.5. Alternative: Locking According to the Business Rule

If you do not want to rely solely on SSI retries, you can introduce a coordinator row or use `SELECT ... FOR UPDATE` to lock the relevant rows in a consistent order before deciding on updates.

However, never run a plain `SELECT COUNT(*)` thinking it locks the entire row set. `COUNT` does not acquire row locks preventing other doctors from being updated. For multi-row rules, define an explicit **lock target** or choose `SERIALIZABLE` properly.

## 16. `SERIALIZABLE`: Outcomes Must Match Some Serial Ordering

Practical definition:

> If all participating transactions execute at `SERIALIZABLE` and handle retries properly, PostgreSQL coordinates them so that **committed** transactions produce an outcome equivalent to some valid serial execution order, even though their actual execution overlapped.

This does not mean PostgreSQL runs only one transaction at a time. It still uses MVCC and SSI to allow concurrency; when it detects a dangerous dependency cycle, it can **abort one transaction** to preserve correctness.

### 16.1. Example Starting a Serializable Transaction

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM acid_lab.on_call
WHERE on_duty = TRUE;

-- Check business conditions and then run appropriate UPDATEs.

COMMIT;
```

This is an **illustrative skeleton**. Real business logic must stay inside the transaction and must never split the `SELECT` into Transaction A and the `UPDATE` into Transaction B.

### 16.2. Serialization Failures Are Part of the Contract

A serializable transaction can fail with:

```text
SQLSTATE 40001: serialization_failure
```

This is not necessarily a PostgreSQL bug. It is normally the consistency-protection mechanism under concurrent contention.

The application must:

1. Detect the SQLSTATE.
2. Roll back the current transaction.
3. Start a **new transaction**.
4. Re-read data and recompute business decisions.
5. Attempt to commit again.
6. Bound retries with backoff/jitter and surface an appropriate error if contention persists.

### 16.3. Never Retry Only the Failing Statement

Wrong idea:

```text
BEGIN
SELECT count of on-duty doctors
UPDATE doctor A
COMMIT -> serialization_failure
Re-run only UPDATE doctor A
```

The second update attempt is no longer grounded in the previously checked snapshot/condition. You must retry **the entire business logic** from the beginning.

### 16.4. SERIALIZABLE Does Not Replace Data Validation

If a serializable transaction deliberately runs:

```sql
UPDATE acid_lab.accounts
SET balance = balance + 1000000
WHERE account_id = 101;
```

the isolation level has no idea whether that money is legitimate. It only prevents anomalies arising from **concurrency**, without validating the source of funds.

Constraints, permissions, business validation, and auditing are still required.

## 17. Retries, SQLSTATE, and Error Handling

Transactional applications must distinguish multiple error categories.

| Code/Group | Example | High-Level Handling |
| --- | --- | --- |
| `40001` | Serialization failure | Usually retry the **entire transaction** after rollback |
| `40P01` | Deadlock detected | Usually rollback and retry the entire transaction if idempotent and policy permits |
| `23505` | Unique violation | May be bad input or contention; **do not** blindly retry |
| `23503` | Foreign key violation | Inspect referenced data and business rules |
| `23514` | Check constraint violation | Fix input/logic causing invariant violation |
| `55P03` | Lock not available | Handle `NOWAIT`/lock timeout, define retry policy |
| `57014` | Query canceled | May be timeout or explicit cancel; do not treat automatically as serialization conflict |

**Note:** a `23505` error in certain concurrent races can be handled with business-level retry/lookup, but never lump all unique violations into "retrying will fix it." A value may genuinely already exist permanently, and the user should receive a duplicate error.

### 17.1. Retries Need Bounds

```text
for attempt = 1..maxAttempts:
    open a new transaction
    re-read business conditions
    perform changes
    COMMIT
    if succeeded: return
    if SQLSTATE 40001/40P01:
        ROLLBACK
        backoff + jitter and retry
    if other error:
        ROLLBACK
        handle by error category
after maxAttempts: return observable, debuggable error
```

This is **pseudocode**, not runnable SQL. If the workflow calls external systems, keep external side effects out of the retry loop or guarantee idempotency; otherwise, retries could send emails or charge cards multiple times even though the database committed only once.

### 17.2. Errors After Client Connection Loss

If the connection drops right at `COMMIT`, the client may not know whether the server committed or not. Never automatically resend a transfer in a way that creates a new transfer record. Use a **unique business request ID** to look up and reconcile before causing another effect.

This is a critical boundary between **ACID transactions** and **exactly-once semantics** at the distributed application layer.

## 18. Row Locking: `SELECT ... FOR UPDATE`

Not every problem requires `SERIALIZABLE`. For operations needing coordination over **a specific set of rows**, row locking can make the design simpler to reason about.

Example:

```sql
BEGIN;

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- After locking the target rows, check balances
-- and execute corresponding UPDATEs inside the same transaction.

ROLLBACK;
```

`FOR UPDATE` requests locks on the selected rows; another transaction trying to perform conflicting updates or locks on those rows may have to wait.

### 18.1. Row Locks Do Not Lock "Future Inserted Rows"

If a business rule governs a dynamic set—such as "at most N open orders allowed"—locking **currently existing rows** does not necessarily stop another transaction from **inserting a new row** matching the same predicate.

That involves phantoms and predicate-level invariants. You may need dedicated constraints, `SERIALIZABLE`, or an explicitly locked parent/coordinator row.

### 18.2. `FOR UPDATE` Is Not `LOCK TABLE`

`SELECT ... FOR UPDATE` locks **the selected rows** via PostgreSQL's row-locking mechanism, not every row in the table. PostgreSQL still acquires table-level lock modes accompanying query execution, but you should not equate a row-locking query with an exclusive full-table lock.

To reason accurately, distinguish **row-level locks**, **table-level locks**, and MVCC reads.

### 18.3. Preventing Deadlocks with Consistent Lock Ordering

Suppose Transaction A transfers from 101 to 202 while Transaction B transfers from 202 to 101. If A locks 101 first and B locks 202 first, then both try to lock the other row, a deadlock can occur.

A common strategy is locking accounts in a **consistent order**, such as ascending `account_id`, before performing updates. This reduces deadlock risk when applied consistently across all relevant code paths.

However, lock ordering and complex query plans must be evaluated in real systems; never treat a single `ORDER BY` as an absolute guarantee that no workflow can ever deadlock.

### 18.4. `NOWAIT` and `SKIP LOCKED`

PostgreSQL supports variants:

```sql
SELECT account_id
FROM acid_lab.accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;
```

If the row holds an incompatible lock, `NOWAIT` errors immediately instead of waiting.

`SKIP LOCKED` skips currently locked rows and is commonly useful for **worker queues** picking unclaimed jobs.

For fund transfers, however, **never use `SKIP LOCKED` and silently skip a locked account**, as the system could then process an incomplete dataset. Match locking modes to business semantics.

## 19. Lost Updates: How You Write SQL Affects Outcomes

An application might read inventory quantity:

```text
T1 reads quantity = 10
T2 reads quantity = 10
T1 computes quantity = 9
T2 computes quantity = 9
T1 writes quantity = 9
T2 writes quantity = 9
```

After two sales, stock remains 9 instead of 8. This is an example of a lost update caused by **read–modify–write on a stale value** in a design lacking concurrency control.

### 19.1. Creating the Inventory Table

```sql
CREATE TABLE acid_lab.inventory (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0)
);

INSERT INTO acid_lab.inventory
    (product_id, available)
VALUES (1001, 10);
```

### 19.2. Avoid Sending Stale Absolute Values Computed in the App

Race-prone pattern:

```sql
-- In transaction A:
SELECT available
FROM acid_lab.inventory
WHERE product_id = 1001;

-- In the app: compute 10 - 1 = 9.
UPDATE acid_lab.inventory
SET available = 9
WHERE product_id = 1001;
```

If multiple requests read 10 and write 9, the result fails to reflect two sales.

### 19.3. Relative Updates and Condition Checks in One Statement

```sql
BEGIN;

UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING product_id, available;

ROLLBACK;
```

Under `READ COMMITTED`, PostgreSQL locks the row during the UPDATE; the second transaction handles the conflict appropriately and re-evaluates the predicate against the updated row version after waiting.

When only 1 item remains, two concurrent decrements will not both go negative and commit when `available >= 1` is enforced. One request updates 1 row, while the other updates **0 rows**, which the application must detect to report "out of stock."

### 19.4. Optimistic Concurrency with a Version Column

Another strategy stores a `version` and updates only if the version is unchanged:

```sql
CREATE TABLE acid_lab.stock_versions (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0),
    version bigint NOT NULL DEFAULT 0
);

INSERT INTO acid_lab.stock_versions
    (product_id, available, version)
VALUES
    (1001, 10, 0);
```

After the application reads `available = 10, version = 0`:

```sql
UPDATE acid_lab.stock_versions
SET available = 9,
    version = version + 1
WHERE product_id = 1001
  AND version = 0
RETURNING available, version;
```

If another request already incremented `version`, the UPDATE affects 0 rows; the application must re-read and decide whether to retry, rather than treating "0 rows" as success.

Versioning is useful when update logic is complex, though it does not replace transactions when an operation spans multiple tables.

## 20. Durability: Why `COMMIT` Needs the Write-Ahead Log

**Durability** describes keeping committed changes intact across crashes according to storage guarantees and chosen configuration.

PostgreSQL uses **Write-Ahead Logging (WAL)**:

1. Before data changes are considered durable, recovery information is written to WAL.
2. When a transaction commits, PostgreSQL records the commit in the log per applicable rules.
3. Under default durability settings, the server waits for the required WAL records to be flushed to durable storage before confirming commit to the client.
4. After a crash, PostgreSQL uses WAL to recover a consistent state; not every modified data page needs to be flushed to data files at the exact instant of commit.

High-level flow:

```text
Application sends COMMIT
         |
         v
PostgreSQL writes WAL for changes/commit
         |
         v
Sync WAL to storage per configuration
         |
         v
Return COMMIT success
         |
         v
After crash: recover data from required WAL
```

**Do not confuse WAL with backups:** WAL is part of crash recovery and PITR when configured, yet a WAL directory on the same failed disk does not by itself provide a safe backup.

### 20.1. Why Not Flush Every Data Page Before COMMIT?

A transaction can modify many pages scattered across multiple files. Forcing every data page to disk before every commit can be very expensive. WAL lets PostgreSQL ensure enough recovery information exists on crash while data pages are flushed lazily at other times.

`CHECKPOINT` flushes modified pages and advances recovery state, but it is not required for **a newly committed transaction** to be durable under the default WAL mechanism.

### 20.2. `fsync`

Check:

```sql
SHOW fsync;
```

With `fsync = on` and hardware/OS honoring disk sync guarantees, PostgreSQL performs necessary flushes to protect data across power or OS crashes.

Disabling `fsync` can strip the system of consistent crash recovery and even cause corruption. **Never disable `fsync` in production just for throughput** unless you explicitly accept data loss and corruption risks.

### 20.3. `synchronous_commit`

Check:

```sql
SHOW synchronous_commit;
```

Commonly `on`. Without special synchronous replication rules, standard synchronous commit waits for the commit's WAL record to flush locally before confirming the transaction.

With `synchronous_commit = off`, PostgreSQL can confirm commit before flushing the commit WAL record to disk. This improves throughput and reduces latency in certain workloads, yet **some recently acknowledged transactions near a crash may be lost**.

**Distinction:** `synchronous_commit = off` does not mean every crash corrupts the database; the main risk is losing a small window of recently acknowledged transactions. Disabling `fsync`, by contrast, carries far graver risks including inconsistent or corrupted database state after a crash.

### 20.4. Durability Is Conditional on Hardware and Configuration

No single DBMS guarantees data survival across every possible catastrophe, such as:

- Simultaneous loss of all disks holding database files and WAL.
- Hardware bugs ignoring flush commands.
- Operational mistakes deleting committed data.
- Ransomware or total site loss.
- Missing or unrestorable backups.

Meeting business RPO/RTO targets also requires **backups, replication, restore testing, and infrastructure design**.

## 21. Durability, Replication, and Backups Are Distinct Concepts

### 21.1. Asynchronous Replication Can Lag

PostgreSQL can use streaming replication to send WAL to one or more standbys.

With **asynchronous replication**, a transaction can be acknowledged on the primary before a standby receives or applies that WAL. If the primary is permanently lost right after commit and failover promotes a lagging standby, transactions the client saw as successful **may be missing on that standby**.

Thus, durable commit **on the primary** does not automatically mean "every replica already has the data."

### 21.2. Synchronous Replication Depends on Configuration

Options like `synchronous_standby_names` combined with `synchronous_commit` modes can require standby acknowledgment before the primary confirms commit.

However:

- Waiting for a standby to **receive WAL** differs from waiting for it to **flush WAL**.
- Waiting for WAL **flush** differs from waiting for the standby to **apply** it and make changes visible to readers.
- Exact guarantees depend on replication setup, quorum, and configuration.

Do not assume from `synchronous_commit = on` alone that every replica has applied the transaction. Inspect the full synchronous replication configuration.

### 21.3. Backups and Point-in-Time Recovery

To recover from logic errors or system loss, a backup plan typically includes:

- Consistent base backups.
- WAL archiving if point-in-time recovery is required.
- Retention policies.
- Regular restore drills.
- Access control, encryption, and integrity verification for backups.
- Practiced recovery runbooks before incidents occur.

**PITR** (Point-in-Time Recovery) can restore a database to a past timestamp given the required backup and WAL chain. It is not an automatic switch "turned on just because PostgreSQL has WAL." It requires explicit setup and testing.

### 21.4. RPO and RTO

| Term | Meaning |
| --- | --- |
| RPO – Recovery Point Objective | Maximum acceptable data loss measured in time |
| RTO – Recovery Time Objective | Target maximum time to restore service |

A correct ACID transaction cannot by itself choose a business's RPO/RTO. Replication, backup, and disaster-recovery policies determine whether those objectives are met.

## 22. ACID in Java/JDBC

In Java applications, PostgreSQL is commonly accessed via a JDBC driver. A key detail is that **JDBC `Connection` has an autocommit setting**.

### 22.1. Never Use Multiple Connections for One Transfer

Flawed design:

```java
// Unsafe pattern:
try (Connection a = dataSource.getConnection()) {
    // Debit source account.
}
try (Connection b = dataSource.getConnection()) {
    // Credit destination account.
}
```

If each connection auto-commits independently, the two steps are not in the same transaction.

Ensure **one transaction manager or one connection** governs all three operations.

### 22.2. JDBC Example Checking Updated Row Counts

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            long fromAccountId,
            long toAccountId,
            BigDecimal amount
    ) throws Exception {

        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException(
                "Source and destination accounts must differ"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be greater than 0"
            );
        }

        try (Connection conn = dataSource.getConnection()) {
            conn.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
            );
            conn.setAutoCommit(false);

            try {
                int changedSource;
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE acid_lab.accounts " +
                        "SET balance = balance - ? " +
                        "WHERE account_id = ? AND balance >= ?"
                )) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, fromAccountId);
                    ps.setBigDecimal(3, amount);
                    changedSource = ps.executeUpdate();
                }

                if (changedSource != 1) {
                    throw new IllegalStateException(
                        "Source account does not exist or has insufficient balance"
                    );
                }

                int changedTarget;
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE acid_lab.accounts " +
                        "SET balance = balance + ? " +
                        "WHERE account_id = ?"
                )) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, toAccountId);
                    changedTarget = ps.executeUpdate();
                }

                if (changedTarget != 1) {
                    throw new IllegalStateException(
                        "Destination account does not exist"
                    );
                }

                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO acid_lab.transfers " +
                        "(from_account_id, to_account_id, amount) " +
                        "VALUES (?, ?, ?)"
                )) {
                    ps.setLong(1, fromAccountId);
                    ps.setLong(2, toAccountId);
                    ps.setBigDecimal(3, amount);
                    ps.executeUpdate();
                }

                conn.commit();
            } catch (Exception ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
```

Key highlights:

1. `setAutoCommit(false)` keeps all steps on the same connection in one transaction.
2. `PreparedStatement` passes values via bind parameters rather than concatenating user values into SQL.
3. `BigDecimal` maps cleanly to `numeric` for exact decimal currency math.
4. `executeUpdate()` must affect exactly one row on both source and destination.
5. `commit()` runs only after **all** steps succeed.
6. On failure, `rollback()` cancels the transaction; if rollback itself fails, the secondary exception is preserved for diagnostics.
7. `try-with-resources` closes statements and the connection on exit.

This is a transaction learning example, **not a complete production payment system**: it still lacks idempotency keys, duplicate-request protection, SQLSTATE-aware retries, consistent lock ordering, security auditing, and handling of "uncertain commit outcomes."

### 22.3. Connection Pools Must Enforce Clean Connection Return

A connection stuck in a failed or uncommitted transaction must never be accidentally handed to another request. Connection pool libraries typically offer reset/rollback hooks on return, yet applications should still enforce clear transaction boundaries rather than relying on unverified pool behavior.

When using a framework transaction manager, opening/committing/rolling back is handled by that manager; do not mix manual control on the same connection unless you understand how the framework operates.

### 22.4. Java Retries Must Wrap the Entire Logic

Upon receiving a `SQLException` with SQLSTATE `40001` or `40P01`, the application can re-run the **entire transactional method** with a fresh connection/transaction after backoff and within a retry limit.

However, if the transaction triggered external side effects outside the database, retries must not repeat those side effects. On ambiguous commit outcomes, query by idempotency key before issuing another transfer.

## 23. Transactional Outbox: Coordinating the Database with External Systems

Suppose an application needs to:

1. Mark an order as paid in PostgreSQL.
2. Publish an `OrderPaid` event to a message broker.

If you do:

```text
UPDATE orders
COMMIT
publish OrderPaid
```

the database may commit and the service crash before publishing: no event is emitted.

If you do:

```text
publish OrderPaid
UPDATE orders
COMMIT
```

the message may be published while the database rolls back: the event announces a state that does not exist.

**PostgreSQL transactions do not automatically span message brokers.**

### 23.1. Transactional Outbox Persists Both State Change and Event Intent

Illustrative schema:

```sql
CREATE TABLE acid_lab.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID'))
);

CREATE TABLE acid_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz
);

INSERT INTO acid_lab.orders (order_id, status)
VALUES (5001, 'NEW');
```

Update status and write the outbox row in the **same transaction**:

```sql
BEGIN;

UPDATE acid_lab.orders
SET status = 'PAID'
WHERE order_id = 5001
  AND status = 'NEW'
RETURNING order_id, status;

-- In real apps: only INSERT the event if UPDATE
-- confirmed the status transition succeeded.
INSERT INTO acid_lab.outbox_events
    (event_type, aggregate_id, payload)
VALUES
    (
        'OrderPaid',
        5001,
        '{"order_id":5001,"status":"PAID"}'::jsonb
    );

ROLLBACK;
```

This example uses `ROLLBACK` to keep lab data untouched. When verified and committed with `COMMIT`:

- The order is in `PAID` status.
- The outbox row exists.

Both commit or roll back together. A separate worker reads the outbox, publishes to the broker, and updates `delivered_at` per policy.

### 23.2. An Outbox Does Not Automatically Provide Exactly-Once Delivery

A worker may publish an event successfully and crash before recording `delivered_at`. On restart, it may send **the same event again**.

Accordingly, outbox architectures usually pair with:

- Stable `event_id` or `request_id`.
- **Idempotent** consumers.
- Retries with backoff.
- Backlog and attempt-count monitoring.
- Dead-letter / poison-message handling.

**PostgreSQL ACID** ensures the order update and outbox row share a transaction; how the broker and consumer process events is a **distributed systems coordination** concern.

## 24. Idempotency: Avoiding Executing the Same Request Twice

For a transfer API, a client may resend a request after a timeout. Even though the first request committed, the client might never have received the response.

If every incoming request creates a brand-new transfer, two separate ACID transactions can still deduct funds **twice**. Atomicity alone does not prevent that.

### 24.1. Using a Unique Request Key

You can add an idempotency tracking table:

```sql
CREATE TABLE acid_lab.transfer_requests (
    request_id text PRIMARY KEY,
    from_account_id bigint NOT NULL,
    to_account_id bigint NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    transfer_id bigint UNIQUE
        REFERENCES acid_lab.transfers(transfer_id),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

A request carries a fixed `request_id`, such as `'req-abc-123'`. Every retry of **the same business action** must use the exact same ID and payload.

### 24.2. Sound Design Requirements

A production flow needs to:

1. Define who generates `request_id` and its uniqueness scope.
2. Check whether the request was already processed inside an appropriate transaction.
3. Protect `request_id` with `UNIQUE/PRIMARY KEY` so concurrent requests cannot treat it as two distinct actions.
4. If the previous request succeeded, return the **stored outcome** instead of transferring again.
5. If the ID collides with a different payload, return an explicit error.
6. Combine the transfer and idempotency record **within one transaction**.

Creating the table above alone does not complete the idempotency algorithm. You must handle concurrent races, uncertain commit outcomes, and proper retries.

**Remember:** PostgreSQL protects the atomicity of **one transaction**; idempotency protects the semantics of "one business request" across **multiple transactions/retries**.

## 25. Single-Statement vs. Multi-Statement Isolation

Some rules are best enforced by expressing them inside **a single SQL statement**.

Inventory decrement example:

```sql
UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING available;
```

This is a single atomic conditional statement, so in many simple cases you do not need a multi-step transaction just to run **one update**.

However, if decrementing stock must simultaneously:

- Create an order.
- Deduct inventory.
- Record a stock movement entry.
- Insert an outbox event.

then those operations must be coordinated inside **one transaction** or an appropriate distributed pattern.

### 25.1. An Atomic Statement Does Not Mean an Atomic Workflow

```text
INSERT order        -> autocommit succeeds
UPDATE inventory    -> autocommit succeeds
INSERT outbox       -> fails
```

Each statement may be atomic on its own, yet **the overall workflow** is non-atomic when executed as three separate transactions.

### 25.2. A Multi-Statement Transaction Is Not Necessarily Isolated Enough

```text
BEGIN READ COMMITTED
SELECT a multi-row invariant
UPDATE several rows
COMMIT
```

The steps share one transaction, yet races or anomalies can still occur if isolation and locking do not enforce the invariant. Keep **Atomicity** distinct from **Isolation**.

## 26. Deadlocks and Waiting Transactions

A deadlock occurs when transactions form a cyclic lock-wait dependency.

Example:

```text
T1 holds lock on row 101
T2 holds lock on row 202

T1 wants lock on 202 -> waits for T2
T2 wants lock on 101 -> waits for T1

Neither can make progress on its own.
```

PostgreSQL detects deadlocks and aborts one transaction with:

```text
SQLSTATE 40P01: deadlock_detected
```

### 26.1. Two-Session Scenario

**Session A:**

```sql
BEGIN;
UPDATE acid_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

**Session B:**

```sql
BEGIN;
UPDATE acid_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;
```

Next, A attempts to update 202 and B attempts to update 101. Both wait on each other, and the server detects a deadlock.

**Never induce deadlocks in production just to test.** Practice with lab data and two separate sessions; once the server aborts one transaction, roll it back cleanly and finish the remaining session.

### 26.2. Prevention

Common practices:

- Keep transactions **short**.
- Acquire locks on resources in a **consistent order**.
- Avoid unnecessary queries while holding locks.
- Add appropriate indexes so UPDATE/DELETE statements do not scan and lock excessive rows.
- Avoid external API calls while holding a transaction open.
- Implement bounded retries for `40P01` when business rules allow.

A deadlock does not mean the database is broken; it is a normal possibility in lock-contending workloads. What matters is **minimizing frequency and handling the error properly**.

## 27. Operations: Avoiding `idle in transaction`

A connection that issues `BEGIN` and sits idle without committing or rolling back can hold snapshots, locks, and resources longer than necessary.

Bad behavior example:

```text
BEGIN
SELECT/UPDATE ...
Application waits 15 minutes for a user button click
COMMIT
```

During that wait, the database suffers:

- Other transactions block on locks.
- VACUUM cannot remove old row versions still needed by the long-lived snapshot.
- Pool connections remain tied up.
- Operators struggle to trace which request holds the transaction.

### 27.1. Viewing Open Transactions

Sample monitoring query:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    now() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Depending on privileges, you may not be able to view full queries or details of other sessions.

In multi-tenant or sensitive environments, `query` may contain confidential data; do not copy or log raw queries without access controls.

### 27.2. Useful Timeouts

Settings worth knowing:

- `statement_timeout`: limits execution time of a single statement.
- `lock_timeout`: limits time spent waiting for a lock.
- `idle_in_transaction_session_timeout`: terminates sessions stuck idle inside a transaction for too long.

Lab transaction example:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '2s';

SELECT account_id, balance
FROM acid_lab.accounts
WHERE account_id = 101;

ROLLBACK;
```

`SET LOCAL` applies only within the current transaction. Setting timeouts too low can cause false failures under load spikes; size them to SLAs and query patterns.

### 27.3. Measuring Commit/Rollback Totals

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
```

These counters show operational trends, though rising `xact_rollback` does not by itself prove business errors—rollbacks can also be intentional. Similarly, high commit counts do not prove every transaction is business-correct.

## 28. Checking ACID-Related Configuration

Useful configuration checks:

```sql
SHOW default_transaction_isolation;
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
SHOW idle_in_transaction_session_timeout;
```

General meaning:

| Setting | Relevance |
| --- | --- |
| `default_transaction_isolation` | Default transaction isolation level |
| `fsync` | Controls OS/storage data synchronization guarantees |
| `synchronous_commit` | Controls when commits are acknowledged relative to WAL/standby |
| `full_page_writes` | Protects against partial page writes during WAL crash recovery |
| `wal_level` | Amount of WAL information recorded for replication/recovery needs |
| `idle_in_transaction_session_timeout` | Mitigates idle-in-transaction sessions holding resources too long |

**Never tweak settings just because a value "looks slow."** Some changes weaken durability or impair recovery. Evaluate RPO/RTO requirements, replication, actual load, PostgreSQL version, and operational procedures first.

## 29. Common Misconceptions About ACID

| Misconception | Reality in PostgreSQL |
| --- | --- |
| "BEGIN makes everything automatically safe" | You still need valid SQL, constraints, and proper isolation |
| "Atomicity = every statement is written correctly" | Only commits/rolls back operations actually placed in the transaction |
| "A successful UPDATE means it is committed" | Still depends on whether the transaction commits successfully |
| "A SQL file with many statements is always one transaction" | Each statement may auto-commit unless wrapped in BEGIN |
| "SAVEPOINT is a separate transaction that commits independently" | Savepoints are only partial rollback markers inside the parent transaction |
| "Rollback returns sequence IDs" | Sequences generally do not roll back |
| "Consistency means every session always sees the same value" | That is isolation/visibility; ACID consistency concerns data invariants |
| "CHECK balance >= 0 guarantees all transfers balance" | It does not verify totals or updates in other tables |
| "READ UNCOMMITTED allows dirty reads in PostgreSQL" | PostgreSQL treats it equivalently to READ COMMITTED |
| "REPEATABLE READ is always serializable" | Write skew and serialization anomalies can still occur |
| "SERIALIZABLE never fails" | It can raise `40001` and require retries |
| "Retrying only the UPDATE is enough after serialization failure" | You must retry the entire transaction and recompute decisions from a fresh snapshot |
| "No lost updates if you SELECT before UPDATE" | Read–compute–write on stale values can still fail |
| "SELECT FOR UPDATE locks the whole table" | It locks only the selected rows |
| "SKIP LOCKED works for all concurrent operations" | It skips locked rows, usually inappropriate for transfers |
| "COMMIT always means every replica has applied it" | Depends on synchronous/asynchronous replication and wait modes |
| "Having WAL means automatic backups" | Backups/PITR require separate configuration and testing |
| "synchronous_commit = off is just as safe as on" | Recently acknowledged commits near a crash can be lost |
| "fsync = off only affects speed" | It can cause data loss or corruption after crashes |
| "ACID protects external brokers/email/APIs" | PostgreSQL transactions do not roll back external side effects |
| "ACID ensures an HTTP request never executes twice" | Separate idempotency is required |
| "Connection drop during COMMIT definitely rolled back" | Commit outcome can be ambiguous to the client |
| "Longer open transactions are safer" | Holding locks/snapshots causes blocking and hurts VACUUM |

## 30. Guided Exercises and Answers

Exercises use the `acid_lab` schema and tables created earlier. For two-session exercises, use two separate connections and verify starting data before comparing values.

### Exercise 1. Write a Transaction Updating Two Accounts and Roll Back

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance = balance - 20.00
WHERE account_id = 101;

UPDATE acid_lab.accounts
SET balance = balance + 20.00
WHERE account_id = 202;

ROLLBACK;
```

**Answer:** both balances remain unchanged after rollback. This illustrates atomicity, though it still lacks row-count checks if an account does not exist.

### Exercise 2. Why Don't Two Auto-Committed UPDATEs Form an Atomic Transfer?

**Answer:** each statement can commit before the next starts. If the credit fails, the already committed debit is not automatically rolled back. Both need a shared transaction and error handling.

### Exercise 3. Why Is an `UPDATE` Affecting 0 Rows Still Dangerous?

```sql
UPDATE acid_lab.accounts
SET balance = balance + 100
WHERE account_id = 999999;
```

**Answer:** the statement succeeds without changing any row. If a transfer system ignores `ROW_COUNT` or `RETURNING`, it could record a successful transfer history even though the destination account does not exist.

### Exercise 4. Checking Insufficient Funds Inside One UPDATE

```sql
UPDATE acid_lab.accounts
SET balance = balance - 1000.00
WHERE account_id = 101
  AND balance >= 1000.00
RETURNING balance;
```

**Answer:** with the initial 500.00 balance, zero rows are returned and the balance is untouched. The application must treat "0 rows" as failing the condition.

### Exercise 5. Using SAVEPOINT When an Optional Operation Fails

```sql
BEGIN;

SAVEPOINT optional_step;

INSERT INTO acid_lab.transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, -1.00);

ROLLBACK TO SAVEPOINT optional_step;

SELECT COUNT(*) FROM acid_lab.accounts;

ROLLBACK;
```

**Answer:** inserting a negative amount violates CHECK, yet after `ROLLBACK TO SAVEPOINT` the SELECT executes normally. No invalid transfer is persisted.

### Exercise 6. When Does Rollback Not Return Identity/Sequence Numbers?

**Answer:** sequence values allocated via `nextval` or identity are consumed even if the transaction containing the INSERT rolls back. Gaps in IDs are normal.

### Exercise 7. How Does Consistency Differ from Atomicity?

**Answer:** Atomicity ensures a transaction's changes commit or roll back together; Consistency requires committed data to satisfy constraints and invariants. A transaction can be atomic yet commit a broken business rule if a developer forgot a check.

### Exercise 8. Does `CHECK (balance >= 0)` Guarantee Transfers Never Create Money?

**Answer:** no. It only stops a single row's balance from going negative; you could still credit the wrong amount or forget the debit. Proper transfer logic and sum/relational checks are required.

### Exercise 9. Can `CHECK` and `NOT NULL` Always Be Deferred Until COMMIT?

**Answer:** no. PostgreSQL supports deferring certain constraints like FK/UNIQUE when declared accordingly; `CHECK` and `NOT NULL` do not use `SET CONSTRAINTS ... DEFERRED` in that way.

### Exercise 10. Do Dirty Reads Happen in PostgreSQL `READ UNCOMMITTED`?

**Answer:** no. PostgreSQL implements `READ UNCOMMITTED` with `READ COMMITTED` behavior, so standard SELECTs never dirty-read uncommitted changes from other transactions.

### Exercise 11. Repeating SELECT in `READ COMMITTED`

Session A reads balance 500; Session B adds 50 and commits; A reads again.

**Answer:** A can see 550 on the second read because each statement gets a fresh snapshot in `READ COMMITTED`. This is a nonrepeatable read.

### Exercise 12. Repeating SELECT in `REPEATABLE READ`

Session A reads balance 500 to establish a snapshot; Session B adds 50 and commits; A reads again.

**Answer:** A keeps seeing 500 within its transaction snapshot; once A finishes, a new transaction sees 550.

### Exercise 13. Why Doesn't PostgreSQL `REPEATABLE READ` Allow Standard Phantom Reads?

**Answer:** the transaction snapshot is fixed, so repeated queries do not see new rows committed by other transactions after the snapshot was taken. Yet write skew can still occur, so it is not equivalent to SERIALIZABLE.

### Exercise 14. Which Invariant Can Two Doctors Going Off Duty Violate?

**Answer:** "always keep at least one doctor on duty." Under REPEATABLE READ, two transactions can both read two doctors on duty, update two separate rows to FALSE, and both commit, breaking the invariant. This is write skew.

### Exercise 15. Why Does SERIALIZABLE Need Retries?

**Answer:** to disallow schedules not equivalent to a serial order, PostgreSQL can abort a transaction with `40001`. The application must roll back and re-run the **entire transaction**, re-reading conditions and recomputing decisions.

### Exercise 16. How Do `40001` and `40P01` Differ?

**Answer:** `40001` indicates serialization failure; `40P01` indicates deadlock. Both commonly lead to rolling back and retrying the entire transaction when safe and bounded, though their underlying causes differ.

### Exercise 17. What Does `SELECT ... FOR UPDATE` Solve?

**Answer:** it locks selected rows to coordinate with transactions attempting conflicting operations on those same rows. It does not lock future rows matching a predicate, nor does it replace multi-row invariant logic.

### Exercise 18. Why Can `SKIP LOCKED` Be Wrong for Fund Transfers?

**Answer:** it skips locked rows. If a required account is skipped, the application could process an incomplete set of accounts; `SKIP LOCKED` fits worker queues where skipping claimed jobs is intentional.

### Exercise 19. Preventing Lost Updates When Decrementing Inventory

```sql
UPDATE acid_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING available;
```

**Answer:** condition and update live in one statement. When two transactions contend, PostgreSQL handles row locking and predicate checks properly; the app checks the affected row count to know whether stock remained.

### Exercise 20. What Does a JDBC Transfer Transaction Require?

**Answer:** a single `Connection`, `setAutoCommit(false)`, `PreparedStatement`s, affected row-count checks, `commit()` only when all steps succeed, and `rollback()` on failure. Add idempotency and retries for critical contended workflows.

### Exercise 21. Is WAL the Same as a Backup?

**Answer:** no. WAL enables crash recovery and combines with backups for PITR, yet backups, retention, and restore procedures require separate design. If all data and WAL on the same storage are lost, local WAL is not a backup.

### Exercise 22. What Does `synchronous_commit = off` Trade Off?

**Answer:** it reduces WAL flush wait latency, yet some recently acknowledged transactions can be lost if the server crashes before WAL is durably flushed. It is not equivalent to `fsync = off`, which carries broader and more severe corruption risks.

### Exercise 23. Has an Async Replica Definitely Received Every Recent Commit?

**Answer:** no. Replicas can lag; failing over to a replica missing recent WAL can lose transactions committed on the primary. Align RPO targets with replication configuration.

### Exercise 24. Can a PostgreSQL Transaction Roll Back a Sent Email?

**Answer:** no. Email is an external side effect. Use a transactional outbox to record the intent inside the same DB transaction and send it afterward.

### Exercise 25. Why Does an Outbox Still Need an Idempotent Consumer?

**Answer:** a worker may publish successfully and crash before marking the event delivered, causing a redelivery. Consumers must recognize duplicate `event_id`s so side effects aren't applied twice.

### Exercise 26. Does Dropping Connection at COMMIT Guarantee Rollback?

**Answer:** no. The server may have already committed while the response was lost. Query via an idempotency/request ID or reconciliation before retrying.

### Exercise 27. What Problems Does `idle in transaction` Cause?

**Answer:** it holds locks, snapshots, and pool connections while blocking VACUUM cleanup of old tuple versions. Keep transactions short and configure appropriate timeouts.

### Exercise 28. How Do You Inspect Open Transactions?

```sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

**Answer:** this query reveals sessions with open transactions, subject to permissions. Protect sensitive monitoring output and avoid jumping to conclusions from a single snapshot.

### Exercise 29. When Should You Use One UPDATE Instead of SELECT Then UPDATE?

**Answer:** when the full condition and state change can be safely expressed in one statement, such as conditional inventory decrement or balance debit. This reduces the race window and network round-trips, though multi-table workflows still need explicit transactions.

### Exercise 30. Give a Concise Definition of ACID

**Answer:**

- **Atomicity:** commit or roll back as one unit.
- **Consistency:** committed state satisfies invariants and constraints.
- **Isolation:** concurrent transactions interact safely per the chosen level.
- **Durability:** committed changes survive crashes per WAL/storage/configuration guarantees.

## 31. Production Transaction Design Checklist

| Question | Action Needed |
| --- | --- |
| How many database changes belong to one business operation? | Define clear transaction boundaries |
| Are multiple connections used? | Keep atomic steps inside one managed transaction |
| Are UPDATE row counts checked? | Check `RETURNING` or affected row count |
| What if rows are missing or balance is insufficient? | Enforce conditions and raise business errors |
| Are proper schema constraints present? | PK, FK, UNIQUE, NOT NULL, CHECK, proper types |
| Are there multi-row invariants? | Evaluate locks, SSI, or data modeling |
| Can other transactions update the same rows? | Guard against lost updates and lock contention |
| Is write skew possible? | Consider SERIALIZABLE or coordinator locks |
| What isolation level is active? | Verify settings and specify explicitly when needed |
| Is there retry logic for 40001/40P01? | Retry full transaction with backoff and bounds |
| Are APIs/emails/brokers called inside the transaction? | Avoid non-rollbackable side effects; consider outbox |
| Can client requests be retried? | Add idempotency keys and reconciliation |
| What if COMMIT loses its response? | Handle unknown state instead of blind retries |
| Are transactions held open waiting on users? | Never; keep transactions short |
| Is lock ordering consistent? | Reduce deadlocks across related workflows |
| Are UPDATE/DELETE predicates indexed? | Inspect indexes and locked row counts |
| How are `fsync`/`synchronous_commit` configured? | Understand durability vs. latency trade-offs |
| Is replication sync or async? | Understand commit-loss risks on failover |
| Have backups/PITR been restore-tested? | Meet real-world RPO/RTO targets |
| Are long transactions and deadlocks monitored? | Track pg_stat_activity, logs, and metrics |
| Was mid-workflow failure tested? | Test rollback and correctness |
| Were two concurrent sessions tested? | Test races and conflicts |
| Are constraint violations handled properly? | Do not blindly retry every SQLSTATE |
| Do monetary fields use exact types? | Prefer numeric/BigDecimal per currency rules |
| Are workflow ACID limits documented? | DB transactions do not cover external systems |

## 32. Summary: Understanding ACID to Design Systems, Not Just Memorize Definitions

The four ACID letters form the foundation of PostgreSQL transactions:

1. **Atomicity:** a transaction commits or rolls back as one unit. Use `BEGIN`, `COMMIT`, `ROLLBACK`, and `SAVEPOINT` deliberately; check errors at every step.
2. **Consistency:** confirmed state must satisfy constraints and invariants. PostgreSQL provides PK, FK, UNIQUE, CHECK, and more, yet applications must still define and enforce multi-row/multi-table rules.
3. **Isolation:** concurrent transactions must be controlled. `READ COMMITTED` is the common default, `REPEATABLE READ` offers a stable snapshot yet still allows write skew, and `SERIALIZABLE` uses SSI to prevent non-serializable schedules by aborting conflicting transactions for retry.
4. **Durability:** WAL, flushing, and settings like `fsync`/`synchronous_commit` recover committed changes across crashes within configured guarantees. Replication and backups address additional infrastructure risks rather than being implied by a single COMMIT.

A transaction can be both **atomic** and **business-wrong** if steps are missing; **row-consistent** yet **wrong under concurrency** if multi-row invariants go unchecked; and **committed on the primary** yet absent on an asynchronous replica.

For critical business workflows, ask five questions before shipping:

1. **Which unit of work must commit or roll back together?**
2. **Which constraints and invariants must always hold?**
3. **Which concurrent transactions can run and conflict with one another?**
4. **When commit fails or loses its response, how will the app roll back, retry, or reconcile?**
5. **How is committed data protected against crashes, disk failures, machine loss, and operational mistakes?**

Answering these five questions lets you use ACID as a **practical tool for designing system correctness**, rather than merely memorizing four textbook definitions.
