# ACID, Data Integrity, and Application Responsibilities in PostgreSQL

When an application writes data, the goal is more than "an SQL statement ran without throwing an error." A business operation can involve multiple statements, multiple conditions, and multiple systems. For example, transferring money between two accounts requires debiting the sender, crediting the receiver, and recording history. If the system stops halfway, the two accounts must never be left in a "debited but not credited" state. If two users spend from one balance simultaneously, the total balance must not turn negative. If a client disconnects after sending a request, the system needs to know whether the previous transfer completed before retrying.

PostgreSQL helps solve a large share of these problems through **transactions**, **ACID guarantees**, **integrity constraints**, **concurrency control**, and the **WAL recovery log**. However, a database cannot infer every business rule on its own. The application must still decide what is valid, structure transaction boundaries, handle errors, prevent duplicate processing, and coordinate systems outside the database.

This lesson clearly explains **what PostgreSQL guarantees**, **the conditions required for those guarantees to hold**, and **which responsibilities remain with the application**.

After studying this lesson, you will be able to:

- Accurately interpret the four ACID properties: Atomicity, Consistency, Isolation, Durability.
- Distinguish transactions, single SQL statements, constraints, MVCC, and write-ahead logs.
- Use `BEGIN`, `COMMIT`, `ROLLBACK`, and `SAVEPOINT` in PostgreSQL.
- Define `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, and `CHECK` constraints to protect data.
- Understand the effects of `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` when multiple transactions run concurrently.
- Design a transfer operation with balance guards and a key preventing duplicate requests.
- Handle failures, retries, deadlocks, serialization errors, and external side effects outside the database.

The examples use standard PostgreSQL syntax. Only run table creation or deletion commands on a **dedicated test database**.

---

## 1. Why Does a Business Operation Need Multiple Guarantees?

Consider transferring 250,000 units from account A to account B. Assume the system stores money in **the smallest integer currency unit** (never using binary floating-point numbers to represent money).

Before transfer:

| Account | Balance |
| --- | ---: |
| A | 1,000,000 |
| B | 300,000 |
| **Total** | **1,300,000** |

After a valid transfer:

| Account | Balance |
| --- | ---: |
| A | 750,000 |
| B | 550,000 |
| **Total** | **1,300,000** |

At least four distinct requirements exist here:

1. **No partial transfers:** debiting A and crediting B must succeed together or be canceled together.
2. **Valid balances:** A must have sufficient funds; balances must never become negative.
3. **Concurrent requests:** two concurrent transactions must not overwrite each other or overspend the same balance.
4. **Failures:** when PostgreSQL reports a successful commit per configured durability policies, data must be recoverable appropriately after a crash.

Additional requirements are defined by the **application**, such as verified accounts, daily limits, fraud prevention, account ownership authorization, duplicate-request protection, and sending completion notifications reliably.

Think of the division of responsibilities like this:

```text
Client request
        |
        v
Application: authentication, authorization, business validation
        |
        v
PostgreSQL transaction
  +--------------------------------------+
  | Check conditions and constraints     |
  | Write affected rows                  |
  | Coordinate concurrent access         |
  | Commit or roll back                  |
  +--------------------------------------+
        |
        v
Application: confirm outcome, retry when appropriate,
             manage idempotency and external side effects
```

Never call the entire system "strictly ACID" simply because its tables reside in PostgreSQL. ACID primarily describes **transactions executed by the database**—it does not automatically extend to emails, HTTP APIs, message queues, or operations on external systems.

## 2. Transactions Are the Foundational Unit

A transaction groups multiple database operations into one logical unit. In PostgreSQL, you can open an explicit transaction:

```sql
BEGIN;

UPDATE some_table
SET some_value = 'new value'
WHERE id = 1;

INSERT INTO audit_log(entity_id, action_name)
VALUES (1, 'updated');

COMMIT;
```

This is an **illustrative syntax pattern**; the `some_table` and `audit_log` tables are not part of the lab setup yet.

Core commands:

| Command | Role |
| --- | --- |
| `BEGIN` | Starts an explicit transaction |
| `COMMIT` | Requests confirming the transaction as successful |
| `ROLLBACK` | Discards uncommitted changes in the current transaction |
| `SAVEPOINT name` | Marks a position within the transaction |
| `ROLLBACK TO SAVEPOINT name` | Reverts to the marked position without aborting the entire transaction |
| `RELEASE SAVEPOINT name` | Releases the savepoint while keeping changes made in the transaction |

Without an explicit transaction, PostgreSQL normally treats **each successful SQL statement as its own transaction** under client autocommit mode. That is unsuitable when two statements must succeed together as a single business action.

An error-prone example:

```sql
-- Two independent statements when client is in autocommit mode:
UPDATE accounts SET balance_cents = balance_cents - 25000
WHERE account_id = 1;

UPDATE accounts SET balance_cents = balance_cents + 25000
WHERE account_id = 2;
```

If the first statement commits and the second fails, PostgreSQL **does not automatically undo an already committed prior transaction**. To transfer money as one unit, both steps must sit in the same transaction and handle the outcome of each step properly.

### 2.1. Errors Inside a PostgreSQL Transaction

When an SQL statement fails inside a transaction, PostgreSQL marks the current transaction as **aborted**. Subsequent SQL statements are rejected until you issue `ROLLBACK` or roll back to an appropriate savepoint.

Common message:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

This differs from the idea of "just keep running the next statement and ignore the failed one." Applications must include exception handling, roll back cleanly, and never return a connection in a failed transaction state to a connection pool.

### 2.2. Not Every Effect Can Be Rolled Back

PostgreSQL supports transactional execution for many DDL operations such as `CREATE TABLE` and `ALTER TABLE`, yet **not every utility command can run inside a transaction block**; for example, `CREATE DATABASE` and `VACUUM` have their own restrictions.

Furthermore:

- Values fetched from a sequence via `nextval()` are **not reverted** when a transaction rolls back; IDs can have gaps.
- An email already sent, file written, or HTTP request dispatched is **not automatically rolled back by PostgreSQL**.
- Effects already committed in another database or external service do not automatically participate in the current transaction.

Therefore, "Atomicity" must be understood within its true scope.

---

## 3. A — Atomicity: Either All Changes Commit, or None Do

**Atomicity** requires that changes belonging to a transaction either commit or abort as a single unit.

Example:

```text
BEGIN
  |
  +-- Debit account A
  |
  +-- Credit account B
  |
  +-- Insert transaction history
  |
  +-- COMMIT succeeds ------> all changes confirmed together
  |
  +-- ROLLBACK / error -----> transaction changes are discarded
```

Transactions prevent partial steps from committing **when all steps execute within the same PostgreSQL transaction**.

Atomicity **does not automatically detect business errors**. For instance, `UPDATE ... WHERE account_id = 9999` affects 0 rows without throwing an SQL error. If the application fails to check the affected row count, it might still commit the remaining steps. The transaction remains atomic over the statements executed, yet the business state becomes wrong.

Key point:

> **The application must define what "success" means.** A SQL statement running without error does not mean the business transaction is valid.

### 3.1. `SAVEPOINT` Is Not a Partial Commit

A savepoint lets you undo part of the work inside a transaction:

```sql
BEGIN;

SAVEPOINT before_optional_action;

-- Illustrative statement that may need canceling:
-- INSERT INTO ...

ROLLBACK TO SAVEPOINT before_optional_action;

-- Changes before the savepoint remain inside the transaction.
COMMIT;
```

Rolling back to a savepoint does not create an independent durable transaction. Remaining changes still depend on the final `COMMIT`.

---

## 4. C — Consistency: Data State Must Stay Valid Under Declared Rules

**Consistency** in ACID means a transaction transitions the database from one state satisfying established invariants to another state still satisfying those invariants, assuming rules are modeled and transactions are written correctly.

PostgreSQL provides multiple constraint tools:

| Constraint | What It Protects | Example |
| --- | --- | --- |
| `PRIMARY KEY` | Every row has a unique, non-`NULL` identifier key | `account_id` |
| `UNIQUE` | Values or combinations of values cannot duplicate per unique rules | `request_key` of a transfer request |
| `NOT NULL` | A column always holds a non-`NULL` value | `balance_cents` |
| `CHECK` | An expression validating each row's values | `balance_cents >= 0` |
| `FOREIGN KEY` | Referenced values must match rows in the referenced table | `from_account_id` referencing `accounts` |
| `EXCLUDE` | Prevents pairs of rows satisfying a conflict operator | Prevents overlapping booking time slots when properly designed |

Some rules can be enforced via **database constraints**, while others must be enforced by application or transaction logic.

### 4.1. A Single `CHECK` Does Not Understand All Business Rules

Example:

```sql
balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
```

This constraint protects non-negative balances on **each individual row**. It does not guarantee that the total money transferred between two accounts is conserved. That conservation invariant requires checked debit/credit updates inside a transaction.

Also remember that PostgreSQL considers a `CHECK` satisfied when its expression evaluates to **TRUE or NULL**. If a column permits `NULL`, a condition like `CHECK (amount > 0)` will not reject `NULL`; add `NOT NULL` whenever business rules require a value.

### 4.2. Never Rely Solely on Application Checks Instead of Constraints

An application might check before inserting:

```text
SELECT whether request_key = 'abc' exists?
If not: INSERT ...
```

However, two concurrent requests can both observe "does not exist" and both attempt to insert. If the database has `UNIQUE(request_key)`, PostgreSQL mediates the race so two rows with the same key can never commit.

Principle:

- **Database constraints** are the final line of defense for data rules expressible at the database level.
- **The application** validates early to return friendly errors and drive business workflows.
- The two layers **complement each other**—never omit constraints just because the API already validates input.

### 4.3. Not All Consistency Is Automatic

PostgreSQL does not know rules such as "VIP customers get waived fees," "a user can refund at most three times a day," or "transfers require account-owner confirmation" unless you model them.

In practice, system correctness also depends on:

- Declared schemas and constraints.
- Transaction boundaries.
- How business rules are encoded.
- Isolation levels and locking strategies.
- How the application reacts when SQL returns 0 rows or raises an error.
- External systems outside the transaction.

This is why "PostgreSQL supports ACID" **does not mean "every business flow written on PostgreSQL is automatically correct."**

---

## 5. I — Isolation: Concurrent Transactions Must Not Corrupt Results

**Isolation** governs how transactions behave when multiple connections execute concurrently.

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)** to manage row versions and read snapshots. Simply put, queries can read a data version matching their snapshot rather than forcing every `SELECT` to block on another transaction's `UPDATE`.

However, **different isolation levels provide different guarantees**. Never interpret isolation as "all transactions always run one by one" under every configuration.

### 5.1. PostgreSQL Isolation Levels

| Isolation Level | Practical Meaning in PostgreSQL |
| --- | --- |
| `READ UNCOMMITTED` | PostgreSQL executes it identically to `READ COMMITTED`; dirty reads are not allowed despite the name |
| `READ COMMITTED` | Default; each statement gets a fresh snapshot at statement start, so a subsequent `SELECT` may see newer committed data |
| `REPEATABLE READ` | Same snapshot across appropriate queries in one transaction; prevents many read anomalies, though **serialization anomalies** can still occur |
| `SERIALIZABLE` | Guarantees outcomes equivalent to a serial execution order; may abort a transaction with a serialization error requiring retry |

Specify the isolation level when starting:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
-- Execute SQL statements...
COMMIT;

BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Execute SQL statements...
COMMIT;

BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Execute SQL statements...
COMMIT;
```

These are three **separate transactions illustrating syntax**; do not change the isolation level mid-transaction after queries have already run unless PostgreSQL's conditions allow it.

### 5.2. `READ COMMITTED`: Two Reads Can Differ

Suppose account 1 has balance 1,000,000. Two connections run:

**Session A**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance_cents
FROM acid_lab.accounts
WHERE account_id = 1;

-- Wait for Session B to commit...

SELECT balance_cents
FROM acid_lab.accounts
WHERE account_id = 1;

COMMIT;
```

**Session B**

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 10000
WHERE account_id = 1
  AND balance_cents >= 10000;
```

If B commits between A's two `SELECT` statements, A reads two different values. This is a **non-repeatable read**, which is allowed under `READ COMMITTED`.

Do not treat this as a PostgreSQL bug: it is the permitted behavior of the default isolation level. If business logic needs a stable snapshot across multiple queries, choose an appropriate mechanism.

### 5.3. `REPEATABLE READ` and Snapshot Isolation

Under `REPEATABLE READ`, PostgreSQL uses a transaction-wide snapshot (established on the first appropriate query). Re-reading within the same transaction sees a consistent version per that snapshot, rather than taking a new snapshot per statement.

This avoids many read anomalies, yet does not protect every multi-row invariant when two transactions read and then modify **different** rows.

For example, suppose two doctors are on call and the rule states **at least one doctor must remain on call**. Both transactions read "2 doctors on call," and each removes a different doctor from the schedule. Because they update different rows without an invariant guard, both can commit under snapshot isolation, leaving **nobody on call**. This anomaly is called *write skew*.

Thus `REPEATABLE READ` should never be described as "equivalent to SERIALIZABLE for all business rules."

### 5.4. `SERIALIZABLE` Does Not Mean Errors Never Happen

PostgreSQL implements serializable isolation using **Serializable Snapshot Isolation (SSI)**. It detects dangerous concurrency patterns and aborts a transaction to prevent outcomes that cannot match any valid serial schedule.

The application may receive SQLSTATE `40001` (`serialization_failure`).

When that happens, you must:

1. `ROLLBACK` the failed transaction.
2. Retry **the entire transaction logic**, including queries that determined which data to update.
3. Bound retry attempts, use appropriate backoff with jitter, and report failure if retries exhaust.

Re-running only the **final SQL statement** is insufficient because earlier decisions relied on an invalidated snapshot.

### 5.5. Row Locks and Atomic UPDATEs

When multiple transactions update the same row, PostgreSQL uses row locks to coordinate them. Under `READ COMMITTED`, a statement like:

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 10000
WHERE account_id = 1
  AND balance_cents >= 10000
RETURNING account_id, balance_cents;
```

can be far safer than:

```text
SELECT balance_cents in application
Application computes new_balance = old_balance - 10000
UPDATE accounts SET balance_cents = new_balance
```

With an unguarded read–compute–write pattern, two requests can both read an old balance and overwrite values based on stale data. In `UPDATE ... SET balance_cents = balance_cents - ... WHERE balance_cents >= ...`, PostgreSQL performs the condition check and deduction as a single conditional update; it waits on concurrent updates and re-evaluates the row version per isolation rules.

Even so, the application **must check the `RETURNING` row count**: 0 rows means no funds were deducted because the account does not exist or has insufficient balance. That itself is not an SQL error.

### 5.6. Deadlocks and Lock Ordering

Two transactions can update two accounts in opposite order:

```text
Transaction T1: locks A, then needs lock on B
Transaction T2: locks B, then needs lock on A
                        |
                        v
                 Circular wait (deadlock)
```

PostgreSQL detects deadlocks and aborts one transaction, typically with SQLSTATE `40P01`. This is a system protection mechanism, not a promise that applications can skip error handling.

To reduce deadlock risk:

- Lock/update multiple rows in a **consistent order** across all code paths.
- Keep transactions short; avoid waiting on network calls or user input while holding locks.
- Ensure row-lookup predicates have appropriate indexes when needed.
- Implement bounded retries for deadlock errors when business semantics permit.

---

## 6. D — Durability: Committed Changes Must Be Recoverable

**Durability** means committed changes remain recoverable across crashes within PostgreSQL's configured storage guarantees.

PostgreSQL uses a **Write-Ahead Log (WAL)**. Rather than forcing every modified data page out to main data files before acknowledging each commit, the system writes sufficient recovery records to WAL under the write-ahead principle.

A simplified model:

```text
UPDATE / INSERT / DELETE
          |
          v
Data modified in memory and affected pages
          |
          v
Recovery records written to WAL
          |
          v
COMMIT and WAL durability flush per configuration
          |
          v
Data pages flushed to data files later
          |
          v
If a crash occurs: WAL and durable data restore consistent state
```

WAL does not mean the database automatically backs up all history. It is part of crash recovery; **backups and WAL archiving for point-in-time recovery** are a separate, required operational strategy.

### 6.1. Parameters Affecting Durability Guarantees

Key PostgreSQL parameters:

- `fsync`: controls synchronizing writes to durable storage. Disabling `fsync` in production destroys crash recovery guarantees—never use it as a "performance trick."
- `synchronous_commit`: controls when a transaction is considered committed relative to WAL flushing/acknowledgment. When disabled, recent commits right before a crash can be lost even though the client received success.
- `full_page_writes`: protects recovery against torn/partially written pages.
- Replication and WAL-retention settings govern how much data exists on replicas and failover safety.

Inspect current settings:

```sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
```

`SHOW` commands are **read-only**. This lesson does not ask you to change settings on a live server.

### 6.2. A Commit Succeeding on the Primary Has Not Necessarily Reached Every Replica

With **asynchronous replication**, a transaction can commit on the primary before replicas receive and apply it. Failing over to a lagging replica can lose the most recent commits.

Synchronous replication strengthens guarantees per policy at the cost of latency and availability; never assume every PostgreSQL topology is synchronous simply because replication is enabled.

Keep these separate:

| Concept | What It Solves |
| --- | --- |
| WAL and recovery | Recovering durably recorded commits after a crash |
| Replication | Maintaining copies on other servers per topology policy |
| Backup | Restoring data after accidental deletes, logic bugs, hardware loss, or broader disasters |
| Monitoring | Detecting latency, write errors, replication lag, and warning signs |

A replica does not replace backups: an erroneous `DELETE` on the primary replicates straight to the replica.

---

## 7. Building a Money Transfer Data Model to Practice ACID

The following example uses a test database where your account has schema-creation privileges. If not, use an assigned schema and adjust the `acid_lab.` prefix accordingly.

> **Do not run on a database with real data.** The `DROP TABLE` statements below delete practice tables of the same names along with all existing data. They are strictly for a resettable lab database.

### 7.1. Create Two Tables and Constraints

```sql
CREATE SCHEMA IF NOT EXISTS acid_lab;

DROP TABLE IF EXISTS acid_lab.transfer_requests;
DROP TABLE IF EXISTS acid_lab.accounts;

CREATE TABLE acid_lab.accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance_cents BIGINT NOT NULL
        CHECK (balance_cents >= 0)
);

CREATE TABLE acid_lab.transfer_requests (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    from_account_id INTEGER NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT different_accounts
        CHECK (from_account_id <> to_account_id)
);

INSERT INTO acid_lab.accounts
    (account_id, owner_name, balance_cents)
VALUES
    (1, 'An',   100000),
    (2, 'Binh',  30000),
    (3, 'Chi',      0);

SELECT *
FROM acid_lab.accounts
ORDER BY account_id;
```

Design rationale:

- `BIGINT` stores money in the **smallest unit** (e.g., cents or dong), avoiding `real`/`double precision` rounding errors during arithmetic.
- `accounts.account_id` uniquely identifies each account.
- `CHECK (balance_cents >= 0)` rejects negative balances directly in the database.
- `transfer_requests.request_key UNIQUE` guards against recording the same request key twice.
- Two foreign keys ensure both sender and receiver accounts exist when recording history.
- `amount_cents > 0` and `from_account_id <> to_account_id` enforce intra-row invariants on transfer records.
- `created_at TIMESTAMPTZ` stores a time-zone-aware timestamp in PostgreSQL; display formatting depends on the session time zone.

Verify initial total:

```sql
SELECT SUM(balance_cents) AS total_cents
FROM acid_lab.accounts;
```

Initial result: `130000`.

### 7.2. Small Datasets Illustrate Behavior, Not Concurrent Load

Three sample rows suffice to demonstrate rollback, constraints, and transfers. To observe concurrency, you need **two independent PostgreSQL connections**; running statements sequentially in one session does not simulate real contention.

This lab does not replace a full banking system: it omits multi-currency handling, fees, limits, approvals, reconciliation, immutable ledgers, and per-owner access permissions.

---

## 8. Testing Atomicity with `BEGIN` and `ROLLBACK`

First, run a test transfer of 25,000 units from account 1 to 2, then intentionally roll back:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 25000
WHERE account_id = 1
  AND balance_cents >= 25000
RETURNING account_id, balance_cents;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 25000
WHERE account_id = 2
RETURNING account_id, balance_cents;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;
```

Inside the transaction, temporary balances are `75000` and `55000`. After `ROLLBACK`, balances return to `100000` and `30000`. Uncommitted changes are normally invisible to other transactions.

In this example, each `UPDATE` returns one row because the accounts exist and funds suffice. **If a `RETURNING` clause yields 0 rows, you must actively roll back rather than proceeding.** The lab data was chosen to succeed; real programs must enforce that check branch.

### 8.1. Transfer and `COMMIT`

Run a valid transfer:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 25000
WHERE account_id = 1
  AND balance_cents >= 25000
RETURNING account_id, balance_cents;

-- Continue only if the statement above returned exactly one row.
UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 25000
WHERE account_id = 2
RETURNING account_id, balance_cents;

-- Continue only if the statement above returned exactly one row.
INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('demo-transfer-001', 1, 2, 25000)
RETURNING transfer_id, request_key;

COMMIT;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

SELECT transfer_id, request_key, amount_cents
FROM acid_lab.transfer_requests
ORDER BY transfer_id;
```

Balances after commit: account 1 has `75000`, account 2 has `55000`; the total remains `130000`. The log contains `demo-transfer-001`.

**Important:** In an SQL client executing a batch script, the statements above **do not automatically halt** if the first `UPDATE` returns 0 rows. The `-- Continue only ...` comment represents flow-control logic required in application code. Production code must check row counts and roll back via application logic or an exception-handling SQL function/procedure; never treat this SQL block as a safe blind-run transfer API.

### 8.2. Demonstrating Constraint Protection

Try:

```sql
-- Execute outside the previous transfer transaction.
UPDATE acid_lab.accounts
SET balance_cents = -1
WHERE account_id = 3;
```

PostgreSQL rejects this for violating `CHECK (balance_cents >= 0)`.

Next:

```sql
INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('bad-missing-account', 999, 2, 1000);
```

Rejected because `from_account_id = 999` has no matching row in `accounts`.

These examples illustrate a key boundary: **constraints block invalid data even when an application forgets to validate**.

---

## 9. Protecting Balances Under Concurrent Requests

Suppose two clients simultaneously try to debit 60,000 from account 1, which holds `75000` after Section 8.1.

Never rely solely on an application-side read value:

```text
Client A: SELECT balance -> 75000
Client B: SELECT balance -> 75000
Client A: app computes 75000 - 60000 = 15000
Client B: app also computes 75000 - 60000 = 15000
Client A: UPDATE balance = 15000
Client B: UPDATE balance = 15000
```

Without proper concurrency control, two debits can be recorded in business logic while the balance decreases only once. This is a classic **lost update / stale read** hazard.

Let the database perform a conditional update:

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 60000
WHERE account_id = 1
  AND balance_cents >= 60000
RETURNING account_id, balance_cents;
```

With two concurrent requests, PostgreSQL serializes updates to the same row using locks and `READ COMMITTED` rules. After the first request succeeds and leaves `15000`, the second request can no longer debit 60,000 while satisfying the predicate and returns **0 rows**. The application must interpret 0 rows as "cannot fulfill request in current state," rather than blindly retrying infinitely.

**Do not run this 60,000 debit if you want to keep the sample data intact for subsequent exercises.** It is shown to explain behavior; recreate the sample tables if testing directly.

### 9.1. When Multiple Rows Must Be Checked Before Writing

If a workflow must inspect multiple accounts and decide based on that row set, locking the relevant rows may be necessary:

```sql
BEGIN;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Application checks conditions, updates rows, and inserts history.
-- Once all steps pass:
COMMIT;
```

`FOR UPDATE` locks the selected rows for the transaction. Other transactions attempting to update those rows must wait.

Establish a **consistent lock acquisition order** to minimize deadlocks. Never hold a transaction open while waiting on user interaction or slow external APIs. Locking existing rows also does not automatically guard against newly inserted rows or transactions that bypass the locking protocol.

---

## 10. Idempotency: Preventing Double Transfers on Client Retries

A realistic scenario:

1. Client sends a transfer request with `request_key = 'order-pay-123'`.
2. PostgreSQL commits successfully.
3. The connection between the app server and client drops before the client receives the response.
4. Client resends the exact same request.

If the API re-runs the debit/credit without checking, it may **transfer money twice**.

### 10.1. `UNIQUE(request_key)` Is a Critical Safeguard

The lab's `transfer_requests` table includes:

```sql
request_key TEXT NOT NULL UNIQUE
```

PostgreSQL guarantees no two committed rows share the same `request_key`. If an application tries inserting a duplicate inside the same transaction after updating balances, the unique violation prevents those updates from committing (unless intentionally caught via savepoints/exception handlers).

The following example reuses an existing key **solely to observe the error**—never use this pattern as a production API call:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 1000
WHERE account_id = 1
  AND balance_cents >= 1000;

INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('demo-transfer-001', 1, 2, 1000);

-- Duplicate UNIQUE INSERT raises an error and aborts the transaction.
ROLLBACK;
```

Never blindly use `ON CONFLICT DO NOTHING` **after deducting money** and still commit: if the history insert is skipped due to a key collision while the balance update remains, business state corrupts. Idempotency must guard the **entire operation**, not just one log row.

### 10.2. Application-Layer Idempotency Workflow

A common design:

- Client generates or supplies a unique `request_key` for **one business intent**.
- Application validates payload correctness and caller authorization.
- Inside a transaction, the application **registers or locks the key** using a database-enforced uniqueness mechanism.
- If the key was already processed, verify the payload matches the prior request and return the stored outcome (or appropriate status) **without repeating the transfer**.
- If the key is new, execute the transfer, persist the outcome in the database, and commit.
- If the connection drops around commit with an unknown outcome, query by key before initiating another attempt.

**A unique key alone is insufficient** to deliver a complete idempotent API: you must also store request status, outcome, comparison payload, and handle concurrent requests arriving with the same key.

Reusing a key with a different payload must be rejected or handled explicitly; never assume two requests are identical solely because the key string matches.

### 10.3. `INSERT ... ON CONFLICT` Helps, but Does Not Replace Design

PostgreSQL provides:

```sql
INSERT INTO some_table (unique_key, value)
VALUES ('abc', 'payload')
ON CONFLICT (unique_key) DO NOTHING;
```

This is a **syntax pattern**; `some_table` is not in the lab. `ON CONFLICT` helps handle contention on a unique key, yet the application must still determine: does the existing row belong to the same request or a conflicting one? What result should be returned? Should remaining steps execute?

---

## 11. The Application Must Manage the Transaction Lifecycle

Applications interact with PostgreSQL via a driver or ORM; a transaction lives on **one connection** or explicit transaction context.

Application flow:

```text
request
  |
  v
Acquire connection from pool
  |
  v
BEGIN
  |
  +-- Validate relevant state
  +-- Read/lock rows as needed
  +-- UPDATE ... RETURNING
  +-- Check returned row count
  +-- INSERT history / outbox
  |
  +-- Success -----> COMMIT
  |
  +-- Any error ---> ROLLBACK
  |
  v
Return connection to pool in a clean state
```

Core responsibilities:

1. **Start transactions** in the right place, before operations that must be atomic together.
2. **Reuse the same transaction/connection** for SQL statements that belong together. Two repository methods accidentally acquiring different connections will not share a transaction.
3. **Inspect affected row counts** and business conditions, not only database exceptions.
4. **Roll back on error paths**, including timeouts, serialization failures, deadlocks, and unique violations.
5. **Avoid unnecessarily long transactions:** never open a transaction and wait seconds for user OTP input or external HTTP calls.
6. **Never return a connection in an aborted transaction state** to the pool without rolling back.
7. **Never retry infinitely:** distinguish transient errors, business errors, and ambiguous commit outcomes.
8. **Observe transactions** via logs and metrics to track error causes, retry counts, and database vs. external latency.

### 11.1. Pseudocode for Handling a Transfer Transaction

Language-agnostic example:

```text
function transfer(requestKey, fromId, toId, amount):
    validate amount > 0
    validate fromId != toId
    authorize caller to debit fromId

    for attempt in boundedRetries:
        begin database transaction
        try:
            acquire/register idempotency key safely
            if prior completed request with same payload:
                rollback/finish according to design
                return prior result

            optionally lock relevant account rows in stable order

            debit = UPDATE accounts
                    SET balance = balance - amount
                    WHERE id = fromId AND balance >= amount
                    RETURNING id

            if debit has not exactly one row:
                rollback
                return insufficient_funds_or_not_found

            credit = UPDATE accounts
                     SET balance = balance + amount
                     WHERE id = toId
                     RETURNING id

            if credit has not exactly one row:
                rollback
                return destination_not_found

            write transfer history and durable result
            write outbox event if needed
            commit
            return success

        catch retryable concurrency error:
            rollback
            backoff with jitter
            retry whole transaction

        catch any other error:
            rollback
            report or map error appropriately
            stop

    report bounded retry exhaustion
```

This pseudocode illustrates **responsibilities and boundaries**, not production-ready code handling every edge case around idempotency races, integer overflow, timeouts, and ambiguous commit failures. Production code must enforce concrete request-key generation, payload/result storage, and language-specific driver error handling.

**Especially important:** if the driver reports a lost connection during `COMMIT`, do not assume the transaction failed. The server may have committed while the client missed the response. Saving a business key and querying status after reconnecting is far safer than "blindly" retrying.

---

## 12. Classifying PostgreSQL Errors: Not Every Error Should Be Retried

PostgreSQL returns structured **SQLSTATE** codes. Important codes include:

| SQLSTATE | Common Name | Handling Direction |
| --- | --- | --- |
| `23505` | `unique_violation` | Check key collision/idempotency; do not retry blindly |
| `23503` | `foreign_key_violation` | Invalid reference or concurrent change; handle per business rules |
| `23514` | `check_violation` | `CHECK` constraint violated; fix data/business flow |
| `23502` | `not_null_violation` | Missing required value |
| `40001` | `serialization_failure` | Retry **entire transaction** when business logic permits |
| `40P01` | `deadlock_detected` | Roll back, bounded retry, and review lock ordering |
| `55P03` | `lock_not_available` | Can appear with `NOWAIT` or lock acquisition failure; wait/retry per SLA |
| `57014` | `query_canceled` | May come from `statement_timeout` or user cancel; inspect cause before retrying |

Never build logic purely by parsing **error message text**, since locale and wording can change. Rely on SQLSTATE fields and structured driver metadata.

### 12.1. Why Retry the Entire Transaction?

Suppose a transaction reads remaining order quota, decides to create a new order, and updates the quota. If error `40001` were handled by re-running only the final `INSERT`, earlier quota decisions might no longer hold. Retrying the entire transaction ensures business-decision queries re-evaluate against fresh state.

Also distinguish **retrying a transaction aborted by the database** from **retrying a request after an ambiguous commit outcome**. The latter requires idempotency and a status-verification lookup.

---

## 13. Multi-Table Integrity Rules and Constraint Limits

In the lab, `CHECK(balance_cents >= 0)` is a **single-row** invariant. More complex rules include:

- Total funds across all accounts must be conserved during a transfer.
- No more than N bookings may exist for the same time slot.
- An order must have at least one line item before transitioning to `PAID`.
- Daily transaction totals per customer must not exceed a limit.

PostgreSQL does not allow an ordinary `CHECK` constraint to query other tables like an aggregate subquery. Multi-row/multi-table invariants typically use one of these patterns:

1. **Schema design** expressing rules as constraints (foreign keys, unique, exclusion constraints).
2. **Concurrency-controlled transactions**, such as locking a parent/aggregate row representing the managed resource.
3. **Serializable isolation** paired with retries.
4. **Database triggers or functions** when clearly justified and concurrency impacts are understood.
5. **Application workflows** validating conditions and handling errors alongside database constraints.

### 13.1. Constraints Can Be Deferred in Certain Cases

PostgreSQL supports `DEFERRABLE` for eligible constraints such as foreign keys, unique, primary key, and exclusion constraints, allowing check timing to be adjusted within a transaction.

Example idea: temporarily passing through an intermediate state while swapping unique keys, provided the end of the transaction is valid. Where appropriate, a constraint can be declared `DEFERRABLE INITIALLY DEFERRED`.

Not all constraints are deferrable. Ordinary `NOT NULL` and `CHECK` constraints do not support `DEFERRABLE` in the same way. Deferring checks is appropriate only when end-of-transaction invariants still hold and write flows are designed accordingly.

### 13.2. Check Timing and Safety

The database can reject `COMMIT` when a deferred constraint fails at transaction end. Therefore, applications must handle errors **at commit time**, not solely at individual `INSERT` or `UPDATE` calls.

A vital rule: temporary write results inside an open transaction are **not final** until `COMMIT` succeeds.

---

## 14. ACID and Side Effects Outside PostgreSQL

Real-world application transactions often also:

- Send confirmation emails.
- Publish events to a message broker.
- Call external payment gateways.
- Upload files to object storage.
- Send push notifications or invoke webhooks.

These actions are not automatically part of a PostgreSQL transaction.

### 14.1. The "Commit Then Send Message" Problem

Example:

```text
BEGIN
UPDATE orders SET status='PAID'
COMMIT

send message "OrderPaid"
```

If the application crashes **after commit but before sending the message**, the database shows a paid order while downstream systems never receive notification.

Reversing the order carries its own risk:

```text
send message "OrderPaid"

BEGIN
UPDATE orders SET status='PAID'
ROLLBACK
```

Downstream consumers may process an event for a change that never committed.

### 14.2. Transactional Outbox

A common approach is writing an **outbox event in the same PostgreSQL transaction** as the business update:

```text
BEGIN
  UPDATE business_data ...
  INSERT INTO outbox_events (...) VALUES (...)
COMMIT
        |
        v
Worker reads committed outbox events
        |
        v
Dispatches to broker/API
        |
        v
Marks delivery status and retries if needed
```

Writing business data and outbox rows in one transaction avoids the "order committed without an event to publish" state.

However, an outbox **does not guarantee exactly-once delivery to external parties**. A worker can publish a message successfully and crash before marking it sent, causing redelivery. Consumers should be **idempotent** and store processed event keys when needed.

### 14.3. Distributed Transactions Do Not Magically Appear with PostgreSQL

If an operation must commit across PostgreSQL and an external service, a local database transaction cannot guarantee atomicity across both. Patterns like sagas, outbox/inbox, idempotency, or distributed coordination must be chosen per business requirements.

Never hold a database transaction open waiting on a slow external service hoping to achieve cross-system "atomicity."

---

## 15. Access Control Is Also an Application Responsibility

ACID focuses on transactions and data correctness; it **does not replace authentication and authorization**.

For example, if the application's PostgreSQL service account holds `UPDATE acid_lab.accounts`, the database knows that connection is allowed to update the table—it does not automatically know whether the HTTP user making the request owns that account unless the architecture encodes that check.

Layers should be separated:

| Layer | Example Responsibilities |
| --- | --- |
| Client/API | Input validation, formatting, feature access checks |
| Application service | User authentication, ownership checks, limits, idempotency, transaction orchestration |
| PostgreSQL roles/GRANT | Restrict which schemas, tables, columns, or functions a service can read/write/execute |
| PostgreSQL constraints | Block modeled invalid data states |
| PostgreSQL transactions/isolation | Coordinate multi-statement execution and concurrent access |
| Logging/monitoring | Tracing, error detection, latency tracking, and operations |

PostgreSQL also offers **Row-Level Security (RLS)** to enforce row-level access policies when the architecture fits. However, enabling RLS does not solve end-user authentication by itself; you must pass identity into sessions securely and audit role privileges, table ownership, and bypass rules.

Never grant administrative privileges or `DROP` schema permissions to the runtime application account just for deployment convenience. Separating migration accounts from runtime accounts limits the blast radius of application bugs.

---

## 16. Transaction Duration and Operability

Long-running transactions cause multiple operational issues even when their SQL is valid:

- Holding row locks, forcing other transactions to wait.
- Preventing PostgreSQL from reclaiming old row versions promptly, affecting VACUUM and storage footprint.
- Increasing deadlock probability when touching multiple rows.
- Increasing complexity when connections drop or time out.
- Making it harder for operators to distinguish active work from "idle in transaction" sessions.

Queries to observe session state:

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    wait_event_type,
    wait_event,
    LEFT(query, 150) AS query_text
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Visible output depends on the observer account's privileges; SQL text from other sessions may be restricted. Some fields may contain sensitive data, so never expose raw output publicly in production.

To bound execution times, configure appropriate session or role timeouts such as `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout`. These are **operational safeguards**, not substitutes for clean transaction design.

Example strictly for a test session:

```sql
SET statement_timeout = '5s';
SET lock_timeout = '2s';
```

If a statement is canceled by a timeout inside a transaction, the application must handle the resulting transaction state (typically rolling back), rather than issuing more SQL expecting the transaction to still be healthy.

---

## 17. Common Misconceptions About ACID and PostgreSQL

| Misconception | More Accurate Reality |
| --- | --- |
| "Running multiple `UPDATE` statements sequentially is atomic." | Only when wrapped in the **same transaction** with proper error handling. |
| "A transaction succeeded if no exception occurred." | `UPDATE ... WHERE ...` can affect **0 rows**; business conditions must be checked. |
| "Atomicity rolls back emails or HTTP calls." | PostgreSQL rollback does not undo external system side effects. |
| "PostgreSQL automatically knows all consistency rules." | Constraints and business workflows must be explicitly defined. |
| "`CHECK(amount > 0)` always forbids `NULL`." | `CHECK` passes on `NULL` expressions; pair with `NOT NULL`. |
| "The app already checked for duplicates, so `UNIQUE` isn't needed." | Two concurrent requests can both pass pre-checks; database unique constraints stop races. |
| "`READ UNCOMMITTED` allows dirty reads in PostgreSQL." | PostgreSQL treats it as `READ COMMITTED`. |
| "`READ COMMITTED` keeps the same snapshot throughout a transaction." | Each statement typically receives a fresh snapshot. |
| "`REPEATABLE READ` guarantees all multi-row invariants." | Snapshot isolation can still permit serialization anomalies / write skew. |
| "`SERIALIZABLE` means no concurrency errors ever occur." | Transactions can abort with `40001` and require retrying the entire transaction. |
| "Row locking makes business logic right without extra checks." | You must still define the target row set, lock ordering, potential new rows, and invariants. |
| "`COMMIT` means every replica has caught up." | Depends on replication topology and synchronous commit settings. |
| "WAL is a complete backup." | Crash recovery/WAL and backup strategies serve different goals. |
| "Sequences stay gapless if transactions roll back." | `nextval()` does not roll back; ID gaps are normal. |
| "Client disconnect after `COMMIT` means the transaction failed." | The outcome is **ambiguous to the client**; verify using an idempotency key. |
| "Retrying every PostgreSQL error is safe." | Only retry appropriate transient errors; constraint/business errors need different handling. |

---

## 18. Self-Practice Exercises

### Exercise 1 — Identify ACID Properties

For each scenario, identify the relevant property and the application's responsibility:

1. Two SQL statements debit and credit accounts; the credit statement throws an error.
2. Two users order the very last item remaining in stock simultaneously.
3. The database restarts after commit before data pages finish flushing to data files.
4. An application tries inserting two records with the same request key.
5. A client retries a request after losing network connectivity right at commit time.

**Hint:** Scenarios can involve more than one property; for example, #5 also requires idempotency rather than answering only "Durability."

### Exercise 2 — Try `ROLLBACK`

Recreate the Section 7 data and run:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 5000
WHERE account_id = 1 AND balance_cents >= 5000;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 5000
WHERE account_id = 2;

ROLLBACK;

SELECT account_id, balance_cents
FROM acid_lab.accounts
ORDER BY account_id;
```

Explain why balances are unchanged after rollback, and why running the two `UPDATE` statements independently under autocommit differs from wrapping them in one transaction.

### Exercise 3 — Failure Without an Exception

Still using the lab data:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 5000000
WHERE account_id = 1
  AND balance_cents >= 5000000
RETURNING account_id;

-- No rows returned by RETURNING.
ROLLBACK;
```

Did the `UPDATE` fail with an SQL error? Why must the application still roll back and return a business error instead of proceeding to credit the destination account?

### Exercise 4 — Constraints and `NULL`

Explain the difference between:

```sql
amount BIGINT CHECK (amount > 0)
```

and:

```sql
amount BIGINT NOT NULL CHECK (amount > 0)
```

Which form forbids `NULL`? If you want to prohibit transferring 0 units, which form should you pick?

### Exercise 5 — Two-Session Transactions

Use two separate PostgreSQL connections and `acid_lab.accounts`. In session A, start a transaction and `UPDATE` an account without committing; in session B, try updating the same account. Observe the wait state, then roll back session A to release the lock.

Use timeout settings on your **lab session** to avoid waiting indefinitely. Explain why holding locks longer increases latency for other requests.

### Exercise 6 — Distinguish `READ COMMITTED` from `REPEATABLE READ`

Design an experiment where transaction A reads the same balance twice while transaction B updates and commits between A's reads. Compare expected results between:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
```

and:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
```

Explain how "same snapshot" differs from "nobody else can update data."

### Exercise 7 — Classified Error Handling

An application receives codes `23505`, `23514`, `40001`, and `40P01`. Classify which typically indicate data/business violations, which allow retrying the full transaction, and how retry attempts should be bounded.

### Exercise 8 — Side Effects Outside the Transaction

A system must update an order and publish an event to a message broker. Describe the risks of both orderings:

1. Commit the database first, then publish the event.
2. Publish the event first, then commit the database.

Then sketch how to use a transactional outbox and explain why consumers still need idempotency.

---

## 19. Checklist for Designing a Reliable Write Operation

Before deploying critical business logic on PostgreSQL, answer these questions:

| Question | What to Specify |
| --- | --- |
| Where are transaction boundaries? | Which database statements must commit/roll back together? |
| Which data must always be valid? | Which constraints can be declared directly in PostgreSQL? |
| Which business conditions must be checked? | Ownership, status, balances, limits, approval workflows |
| Is the isolation level sufficient? | `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, or appropriate row locks |
| Is there a read–compute–write pattern? | Conditions may change between SQL calls; use conditional `UPDATE` or locking |
| What if `UPDATE`/`DELETE` affects 0 rows? | Explicit business branch and rollback |
| Is there contention on a unique key? | `UNIQUE` plus conflict/idempotency handling |
| Which errors are retryable? | SQLSTATE checks, full-transaction retries, retry caps, and backoff |
| What if commit fails or outcome is unknown? | Request key and verification query path |
| Are emails/events/external APIs involved? | Outbox or cross-system consistency strategy |
| Does the connection account have right privileges? | Least privilege for runtime app; separate migration/admin roles |
| Is it observable and recoverable? | Logs, metrics, backups, restore drills, replication lag monitoring |

**Not every write operation needs `SERIALIZABLE` or `SELECT FOR UPDATE`.** Choose mechanisms matching your invariants and contention level, then validate with realistic concurrency testing. Stronger mechanisms can increase transaction aborts/retries, lock contention, or reduce throughput.

---

## Conclusion

ACID is a foundational pillar of PostgreSQL:

- **Atomicity:** changes inside a transaction commit or abort as a single unit.
- **Consistency:** the database enforces declared integrity constraints; applications must still model and guard complex business rules.
- **Isolation:** PostgreSQL coordinates concurrent transactions using MVCC, locking, and isolation levels; stricter isolation levels may require retry handling.
- **Durability:** WAL and storage mechanisms support recovering committed transactions per durability settings, yet do not replace backups or guarantee all replicas are synchronous.

What determines application quality is not merely "using PostgreSQL," but **setting proper transaction boundaries, defining constraints, performing conditional updates, handling errors/retries, and coordinating external side effects**. When each layer fulfills its role, the system preserves data consistency while withstanding real-world concurrency and failures.
