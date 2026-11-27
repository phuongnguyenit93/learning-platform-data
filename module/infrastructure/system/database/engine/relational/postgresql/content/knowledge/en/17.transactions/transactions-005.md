# Failed Transaction State and Rollback Requirements

When working with PostgreSQL, a SQL error inside an explicit transaction usually has a broader consequence than just that single statement failing. For instance, inside `BEGIN ... COMMIT`, if an `INSERT` violates a unique constraint, the statement fails and **the entire transaction enters a failed/aborted state**. From that point on, you cannot continue running normal `SELECT`, `UPDATE`, or `INSERT` statements as if nothing happened. PostgreSQL typically returns:

```text
ERROR:  current transaction is aborted, commands ignored
        until end of transaction block
SQLSTATE: 25P02
```

Code `25P02` is normally the **consequence** of the first error, not the root cause. To exit the failed state, the application must **roll back the transaction**, or **roll back to a valid savepoint that existed before the error** if business rules allow continuing the remaining work.

This lesson explains:

- How a PostgreSQL transaction transitions from normal state to a failed state.
- Distinguishing **root errors** such as `23505`, `23503`, `22P02` from the cascading error `25P02`.
- Why `ROLLBACK` is typically required, and why issuing `COMMIT` on a failed transaction effectively ends in a rollback.
- When to use **`SAVEPOINT`**, `ROLLBACK TO SAVEPOINT`, and `RELEASE SAVEPOINT`.
- Why error handling differs across `psql` autocommit, explicit transactions, JDBC, and the Spring framework.
- How to retry the **entire transaction** for retryable errors rather than trying to keep running inside a failed transaction.
- How to diagnose issues via SQLSTATE, logs, `pg_stat_activity`, and connection state.

> **Practice safety:** Use a lab database only. The SQL statements below intentionally trigger errors and then roll back for observation. Never execute against production data or connections serving live traffic. In Java applications, always respect the transaction manager owning the connection; do not manually issue `BEGIN`/`ROLLBACK` if a framework manages transactions for you.

## 1. A Transaction Is the Unit of Success or Failure

A transaction lets multiple operations be treated as one unit:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

This is an **illustrative snippet**, not a runnable lab script unless an `accounts` table already exists. When both operations are valid, `COMMIT` ends the transaction and publishes the results. If an error occurs midway, you must not treat only the last command as the issue: **the entire transfer operation must be decided as a commit or a rollback**.

Directly related ACID properties:

| Property | Relation to Failed Transaction State |
|---|---|
| **Atomicity** | Either all changes in the transaction commit, or uncommitted changes are discarded. |
| **Consistency** | Data constraints are checked by PostgreSQL's rules; a failed transaction cannot arbitrarily continue to commit. |
| **Isolation** | Transactions see snapshots and interact concurrently according to the configured isolation level. |
| **Durability** | After a successful commit, PostgreSQL guarantees persistence under the corresponding configuration and operational assumptions. |

**`ROLLBACK` is not "clearing an error off the screen."** It terminates the current transaction, discards its uncommitted changes, and returns the session to a state ready to start a new transaction.

## 2. Preparing the Schema and Sample Data

To simulate errors independently, create a products table and an audit table:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_tx_error;

CREATE TABLE lesson_tx_error.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE lesson_tx_error.audit_events (
    audit_id BIGINT PRIMARY KEY,
    event_name TEXT NOT NULL,
    product_id BIGINT NOT NULL
        REFERENCES lesson_tx_error.products(product_id)
);

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES
    (1, 'SKU-001', 'Keyboard', 10),
    (2, 'SKU-002', 'Mouse', 20);
```

This assumes the schema/tables do not exist yet and the role has creation privileges. Subsequent examples use **new IDs** inside transactions followed by `ROLLBACK` so data state stays clean across exercises.

Inspect the data:

```sql
SELECT product_id, sku, product_name, quantity
FROM lesson_tx_error.products
ORDER BY product_id;
```

Initial output:

| product_id | sku | product_name | quantity |
|---:|---|---|---:|
| 1 | SKU-001 | Keyboard | 10 |
| 2 | SKU-002 | Mouse | 20 |

The `UNIQUE(sku)` constraint is intentionally used to trigger `23505` errors in exercises.

## 3. Conceptual States of a Transaction

A simple state model:

```text
Session ready (not in an explicit transaction)
             │
             │ BEGIN
             ▼
     Normal transaction
     can run SELECT/INSERT/UPDATE/DELETE
             │
       ┌─────┴─────────┐
       │               │
    COMMIT          SQL errors
       │               │
       ▼               ▼
   Completed     Failed transaction
   successfully  (failed / aborted)
                       │
                 ┌─────┴─────────────────┐
                 │                       │
              ROLLBACK          ROLLBACK TO SAVEPOINT
                 │              (if savepoint is valid)
                 ▼                       │
             Transaction                 ▼
             ended          Back to valid transaction
                                       │
                                COMMIT / ROLLBACK
```

In PostgreSQL, an explicit transaction after a normal SQL error **never automatically returns to a runnable state**. You must resolve the transaction boundary.

Conceptual states to distinguish:

- **Idle:** not currently inside an explicit transaction block.
- **In transaction:** `BEGIN` has started and the transaction is able to execute commands.
- **Failed transaction:** an error occurred, marking the transaction as failed.
- **Active:** the backend is actively executing a command at the moment of inspection; this is an execution activity state, not a commit outcome.
- **Connection lost/unknown:** the session was lost or its state cannot be determined; never assume a rollback happened on the server for a commit already in flight.

Different tools represent states differently; later sections show `psql` prompt symbols, libpq status values, and `pg_stat_activity`.

## 4. Classic Scenario: Error 23505 Leading to 25P02

Run these commands **one statement at a time** in a `psql` session to observe the error chain:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 1
WHERE product_id = 1;

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (
    3, 'SKU-001', 'Duplicate SKU product', 5
);
```

The first `UPDATE` succeeds and produces an **uncommitted** change. However, the `INSERT` reuses `SKU-001`, which already exists in the table, so the unique constraint raises an error:

```text
ERROR: duplicate key value violates unique constraint "products_sku_key"
DETAIL: Key (sku)=(SKU-001) already exists.
SQLSTATE: 23505
```

Constraint names and message formatting can vary across environments; the SQLSTATE code is the reliable classification signal.

Now run the next query:

```sql
SELECT quantity
FROM lesson_tx_error.products
WHERE product_id = 1;
```

PostgreSQL responds:

```text
ERROR: current transaction is aborted, commands ignored
       until end of transaction block
SQLSTATE: 25P02
```

Even a trivial `SELECT 1` cannot rescue the transaction:

```sql
SELECT 1;
-- ERROR 25P02 inside the same failed transaction
```

To end it:

```sql
ROLLBACK;

SELECT product_id, quantity
FROM lesson_tx_error.products
WHERE product_id = 1;
```

Product 1's `quantity` is still **10**, because decrementing it to 9 was uncommitted and discarded on rollback.

**Core takeaway of this lesson:** the unique-violating `INSERT` was the root error `23505`; subsequent SQL statements inside the transaction reported `25P02` because the transaction **was already aborted**, and `ROLLBACK` returns the session to a working state.

## 5. Why Doesn't PostgreSQL Continue as If Nothing Happened?

If the first statement adjusts inventory, the next writes an audit row, and the third creates an invoice, a mid-way error could leave business state **half-applied** if the database allowed arbitrary continuation.

PostgreSQL does not guess "skip the bad statement, keep the earlier ones" inside an explicit transaction. Instead, a normal SQL error marks the transaction **aborted**, forcing the client to resolve the boundary explicitly:

- **Roll back everything** when the operation is atomic.
- **Roll back to a savepoint** if the failing step is an independent optional branch that can be discarded while keeping prior work.

This preserves transaction atomicity and ensures errors are handled explicitly at the application layer.

### An Aborted Transaction Does Not Mean Prior Changes Committed

In the example above, the `UPDATE` reported success before the `INSERT` failed. That **does not mean the change was durable**. It remained inside an uncommitted transaction, and rollback discarded it.

Never assume "PostgreSQL returned UPDATE 1 so it is definitely committed" while inside `BEGIN ... COMMIT`.

## 6. SQLSTATE 25P02: Secondary Error Requiring Root-Cause Lookup

The message:

```text
current transaction is aborted, commands ignored until end
of transaction block
```

and SQLSTATE **`25P02`** correspond to condition name **`in_failed_sql_transaction`**.

Example log sequence:

```text
10:00:00 BEGIN
10:00:01 UPDATE ...              -> OK
10:00:02 INSERT duplicate SKU    -> 23505
10:00:03 SELECT ...              -> 25P02
10:00:04 INSERT audit ...        -> 25P02
10:00:05 SELECT current_user     -> 25P02
```

Looking only at the final exception, a developer might waste time "fixing the SELECT" or "fixing the audit insert," when the first failing SQL statement was the `INSERT` at 10:00:02.

### Error-Chain Investigation Procedure

1. Identify the failing request, connection, and transaction.
2. Find the **first SQLSTATE other than 25P02** in the same transaction.
3. Read the SQLSTATE, constraint name, table/column, and detail from that initial error.
4. Diagnose the business or data root cause of that first failing statement.
5. **Roll back the transaction** before retrying or returning the connection to the pool.
6. If retrying, start a brand-new transaction rather than reusing an aborted state.

Do not log hundreds of `25P02` errors while dropping the original message; later errors are merely symptoms of an already failed transaction.

## 7. Root Errors That Commonly Put Transactions into Failed State

| SQLSTATE | Common Error Name | Example |
|---|---|---|
| **`23505`** | `unique_violation` | Inserting an already existing SKU/unique key. |
| **`23503`** | `foreign_key_violation` | Inserting a child row referencing a missing parent ID. |
| **`23502`** | `not_null_violation` | Writing `NULL` into a `NOT NULL` column. |
| **`23514`** | `check_violation` | Negative quantity violating `CHECK(quantity >= 0)`. |
| **`22P02`** | `invalid_text_representation` | Casting `'abc'::integer`. |
| **`22012`** | `division_by_zero` | Division by zero expression. |
| **`42P01`** | `undefined_table` | Querying a nonexistent table. |
| **`42703`** | `undefined_column` | Referencing a nonexistent column. |
| **`42501`** | `insufficient_privilege` | Missing required privileges. |
| **`40001`** | `serialization_failure` | Conflict under serializable/repeatable-read isolation semantics. |
| **`40P01`** | `deadlock_detected` | PostgreSQL detected a lock cycle and chose a victim transaction. |
| **`55P03`** | `lock_not_available` | Failed to acquire lock under `NOWAIT` or `lock_timeout`. |
| **`57014`** | `query_canceled` | SQL canceled explicitly or via `statement_timeout`. |
| **`25P02`** | `in_failed_sql_transaction` | Subsequent command rejected because transaction is already failed. |

These codes classify errors, yet **do not automatically decide whether to retry**. For example, `23505` may be a business conflict requiring HTTP 409 rather than retrying inserts endlessly. `40001` is normally a candidate for retrying the **entire transaction**, subject to retry bounds and ensuring external side effects are not duplicated.

### Errors in Read Statements Also Abort Transactions

Not just `INSERT`/`UPDATE`:

```sql
BEGIN;

SELECT 'not-a-number'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

A failing `SELECT` still puts an explicit transaction into the failed state.

## 8. How Explicit Transactions Differ from Autocommit

### Case A — No BEGIN, psql Default Autocommit

`psql` normally runs with autocommit enabled. Each standalone statement runs in its own implicit transaction:

```sql
INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Duplicate', 5);
-- Error 23505; this statement's transaction is rolled back.

SELECT 1 AS still_working;
-- Usually succeeds: a new implicit transaction.
```

Without explicit `BEGIN`, a statement's failure rolls back only that statement's transaction. The next statement starts a fresh transaction and does not hit `25P02`.

### Case B — With BEGIN

```sql
BEGIN;

SELECT 'abc'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

The transaction remains in a failed state between the error and `ROLLBACK`.

### Autocommit Is Client/Driver Behavior, Not "Transactions Disappearing"

Even when each statement commits or rolls back individually, PostgreSQL still executes every statement with transaction semantics. `autocommit=true` in JDBC means the driver/connection manages each statement under that rule, not that the database disables ACID.

### Mixing Manual BEGIN with JDBC Autocommit Causes Confusion

Do not send raw `BEGIN` via `Statement.execute("BEGIN")` in code that also manipulates `Connection.setAutoCommit(false)` without a clear design. In JDBC, prefer `setAutoCommit(false)`, `commit()`, and `rollback()`, or let a transaction manager own the lifecycle.

## 9. Does COMMIT After a Failed Transaction Commit Data?

A common point of confusion: in PostgreSQL, if an explicit transaction is already aborted, sending `COMMIT` **ends the transaction with a rollback**, and the server typically returns the command tag `ROLLBACK`.

Example:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = 5
WHERE product_id = 1;

SELECT 'bad'::integer;
-- ERROR 22P02

COMMIT;
-- PostgreSQL typically responds: ROLLBACK
```

**`COMMIT` will never salvage changes made before the error.** Setting stock to 5 was rolled back.

### Should You Call COMMIT or ROLLBACK?

Once you know the transaction failed, always issue an explicit **`ROLLBACK`** so intent is unambiguous and misunderstandings are avoided. Never build applications around "just send COMMIT at the end; the server will do the right thing."

### COMMIT Can Raise Errors of Its Own

A distinct case is an error **occurring at COMMIT time**, such as a deferred constraint check or a serialization conflict detected at commit. At that moment, PostgreSQL may have already terminated the transaction via rollback. Inspect the root error and connection state rather than assuming every error leaves an open failed transaction waiting for `ROLLBACK`.

Key application rule: **never report business success unless COMMIT actually succeeded**; check the outcome and open a new transaction if retrying.

## 10. ROLLBACK Discards All Uncommitted Changes

Example:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 2
WHERE product_id = 2;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (900, 'decrement-stock', 2);

ROLLBACK;

SELECT quantity
FROM lesson_tx_error.products
WHERE product_id = 2;

SELECT *
FROM lesson_tx_error.audit_events
WHERE audit_id = 900;
```

After rollback, product 2's `quantity` returns to 20 and audit event 900 does not exist, assuming no outside interference.

### Effects That Rollback Does Not Necessarily Undo

Not every observable effect is transactional:

- Values drawn from a **sequence** via `nextval()` are generally **not returned** on rollback.
- Outbound calls to **email, HTTP APIs, or external systems** already happened and cannot be recalled.
- Application logs, server logs, and metrics emitted outside the transaction still persist.
- Certain operations using external resources or extension side effects follow their own rules.

Therefore, "rolling back the database" **does not equal rolling back the external world**. If external systems are involved, design an outbox, idempotency, or compensating actions.

## 11. SAVEPOINT: Limiting the Rollback Scope

Not every localized error must discard the entire unit of work when business rules permit partial recovery. PostgreSQL supports `SAVEPOINT` inside transactions.

```text
BEGIN
  │
  ├── operation A succeeds
  │
  ├── SAVEPOINT before_optional
  │
  ├── operation B fails
  │      │
  │      └── ROLLBACK TO SAVEPOINT before_optional
  │
  ├── operation C proceeds validly
  │
  └── COMMIT
```

`ROLLBACK TO SAVEPOINT` discards changes made **after the named savepoint**, without aborting the entire transaction. Work prior to the savepoint remains in the transaction and becomes durable only if `COMMIT` ultimately succeeds.

### Complete Example

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = quantity - 1
WHERE product_id = 1;

SAVEPOINT before_optional_insert;

INSERT INTO lesson_tx_error.products (
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Duplicate SKU', 5);
-- ERROR 23505

ROLLBACK TO SAVEPOINT before_optional_insert;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (901, 'inventory-adjusted', 1);

RELEASE SAVEPOINT before_optional_insert;

COMMIT;
```

After this example:

- Product 1's quantity decrement and audit 901 are committed.
- Product 3 was not created because the failing `INSERT` rolled back to the savepoint.

**Note:** unlike earlier examples ending with `ROLLBACK`, this example runs a real `COMMIT` and alters lab data. If you want to practice repeatedly without persisting changes, test in a separate database or change the final line to `ROLLBACK` after verifying recovery.

### Which Commands Are Permitted in Failed State?

Inside an aborted transaction, `ROLLBACK TO SAVEPOINT valid_name` is the supported recovery command **if the savepoint existed before the error and is still valid**. `RELEASE SAVEPOINT` or ordinary SQL statements **cannot substitute** for `ROLLBACK TO SAVEPOINT` in aborted state.

## 12. ROLLBACK TO SAVEPOINT vs. Full ROLLBACK

| Statement | Effect | Can Continue Old Transaction? |
|---|---|---|
| `ROLLBACK;` | Ends transaction, discards all uncommitted changes. | **No**; must start a new transaction to continue. |
| `ROLLBACK TO SAVEPOINT s;` | Discards operations after savepoint `s` and restores transaction state there. | **Yes**, if the savepoint is valid and recovery succeeds. |
| `RELEASE SAVEPOINT s;` | Drops savepoint marker; does not commit transaction. | Yes in normal state; cannot rescue a failed transaction. |
| `COMMIT;` | Commits if valid; if transaction is already aborted, ends by rolling back. | Ends current transaction. |

After `ROLLBACK TO SAVEPOINT s`, savepoint `s` **still exists**; you can subsequently run `RELEASE SAVEPOINT s` or roll back to it again per savepoint rules.

### SAVEPOINT Is Not an Independent Nested Transaction

You cannot independently commit operation B inside a savepoint and guarantee it survives if the outer transaction rolls back. Every change remains inside the **same outer transaction** until the final `COMMIT`.

Do not confuse:

```sql
SAVEPOINT s;
-- changes
RELEASE SAVEPOINT s;
-- NOT a COMMIT yet!
ROLLBACK;
```

with two independent transactions. The final `ROLLBACK` still discards uncommitted changes, including work whose savepoint was released.

## 13. Savepoints Can Be Nested

PostgreSQL supports multiple nested savepoints:

```sql
BEGIN;

SAVEPOINT phase_a;
-- Work belonging to phase A.

SAVEPOINT phase_b;
-- Work belonging to phase B.

ROLLBACK TO SAVEPOINT phase_b;
-- Discards changes after phase_b.

RELEASE SAVEPOINT phase_b;

ROLLBACK TO SAVEPOINT phase_a;
-- Discards remaining changes after phase_a.

ROLLBACK;
```

If you create multiple savepoints with the **same name**, PostgreSQL targets the most recent active savepoint of that name; to avoid confusion, prefer distinct names and clear scoping.

### Do Not Create a Savepoint After an Error to "Rescue" a Transaction

```sql
BEGIN;
SELECT 'broken'::integer;
-- ERROR

SAVEPOINT too_late;
-- Cannot act as a recovery savepoint.
```

Once a transaction is aborted, a new `SAVEPOINT` command cannot execute normally. Savepoints must be placed **before the potentially failing operation**.

To recover the snippet above:

```sql
ROLLBACK;
```

## 14. When Should You Use Savepoints?

Suitable cases when business rules permit:

- Multi-row imports where some bad rows can be **logged and skipped** while valid rows commit.
- An optional step that must not abort the entire workflow.
- Attempting an operation that may violate a constraint, then reverting to prior state and taking an alternative path.
- ORMs/drivers properly supporting **savepoint-based nested transactions**.

However, savepoints **do not make every error ignorable**. If a failing step leaves an order invalid, roll back the entire transaction rather than creating an incomplete invoice.

### Be Careful with Retries Using Savepoints

Error `40001` (serialization failure) normally requires retrying the **entire transaction** including reads and business decisions, not just re-running the failing statement inside the same transaction. `40P01` (deadlock) likewise normally requires rolling back the victim transaction and restarting from scratch. Do not use savepoints as a generic workaround for concurrency failures.

## 15. psql Commands for Observing Failed State

In `psql`, the default prompt reflects transaction state. Common indicators:

```text
postgres=#        -- not inside an explicit BEGIN block
postgres=*#       -- inside a normal active transaction
postgres=!#       -- transaction is failed/aborted
```

These examples show prompts ending with `#` (superuser style); regular roles typically end with `>`. The database name also varies by connection. The `*`/`!` indicator shows transaction state per `psql`'s default prompt configuration.

### Enabling Verbose Error Details

In `psql`:

```text
\set VERBOSITY verbose
```

Right after an error, you can run:

```text
\errverbose
```

to inspect extra diagnostic fields, including SQLSTATE if supplied by the server.

Commands starting with `\` are **`psql` meta-commands**, not SQL statements to send over JDBC.

### Practice Scenario

```sql
BEGIN;
SELECT 1 / 0;
-- ERROR 22012
SELECT 2;
-- ERROR 25P02
ROLLBACK;
SELECT 2;
-- Succeeds
```

Whenever the prompt shows a failed transaction, do not keep issuing normal `SELECT` or `SET` commands. End the transaction with `ROLLBACK` first.

## 16. ON_ERROR_ROLLBACK in psql

`psql` offers its own `ON_ERROR_ROLLBACK` variable for interactive convenience inside transaction blocks:

```text
\set ON_ERROR_ROLLBACK on
```

With this enabled, in interactive contexts `psql` automatically creates an implicit savepoint before each statement in a transaction and rolls back to it if the statement errors. That lets you continue inside the transaction after mistakes without typing `SAVEPOINT` manually before every command.

Illustrative example:

```text
\set ON_ERROR_ROLLBACK on
BEGIN;
SELECT 1;
SELECT 1 / 0;   -- psql recovers via internal savepoint
SELECT 2;       -- can continue
ROLLBACK;
```

**Never mistake this for default PostgreSQL server behavior.** It is a **`psql` client feature**. JDBC, web applications, and migration tools do not inherit this behavior just because you enabled it in a `psql` session.

### ON_ERROR_ROLLBACK vs. ON_ERROR_STOP

- `ON_ERROR_ROLLBACK`: recovers via implicit savepoints in `psql` when appropriate.
- `ON_ERROR_STOP`: tells `psql` to **stop executing a script** on error instead of reading subsequent commands.

These two variables solve opposite problems. If a migration's goal is **stop and roll back everything on error**, wrap in one transaction and stop on error—do not silently skip failed statements and commit the rest.

## 17. Running SQL Scripts Safely with psql

For a migration file designed to run inside one transaction, a solid invocation is:

```powershell
psql -X -v ON_ERROR_STOP=1 --single-transaction -f migration.sql
```

Explanation:

- `-X`: ignores user `psqlrc` startup files, avoiding personal configuration side effects.
- `-v ON_ERROR_STOP=1`: halts immediately on script error.
- `--single-transaction` (short form `-1`): wraps `-f`/`-c` commands in a `psql`-managed transaction.
- `-f migration.sql`: executes the SQL file.

If an error occurs in this mode, `psql` stops running the rest of the migration and terminates the transaction with a rollback.

**Important caveat:** not every PostgreSQL command can run inside a transaction block, such as `CREATE DATABASE`. Scripts containing non-transactional commands cannot use `--single-transaction`; structure migrations according to command rules.

### What Happens in a Script Without a Transaction Wrapper?

If `psql` runs in autocommit mode and continues after an error, **earlier statements may already have committed individually**. Stopping a script on error does not undo previously committed statements.

Therefore, distinguish:

1. **Stopping on error** (`ON_ERROR_STOP`).
2. **Ensuring script-wide atomicity** (a transaction wrapping eligible commands).

A safe workflow needs both when *all-or-nothing* semantics are required.

## 18. Checking Transaction Status via libpq

At the C/libpq client layer, PostgreSQL provides functions such as `PQtransactionStatus()` to query a connection's transaction state.

Common values:

| libpq Status | Meaning |
|---|---|
| `PQTRANS_IDLE` | Connection is not inside a transaction block. |
| `PQTRANS_ACTIVE` | A command is currently in progress. |
| `PQTRANS_INTRANS` | Inside a normal valid transaction block. |
| `PQTRANS_INERROR` | Inside a failed transaction block. |
| `PQTRANS_UNKNOWN` | Status unknown, usually due to a connection error. |

These are **libpq** constants/APIs, not SQL commands:

```c
PGTransactionStatusType status = PQtransactionStatus(conn);

if (status == PQTRANS_INERROR) {
    // Must end the failed transaction or roll back to a savepoint.
}
```

This C snippet is illustrative; it assumes a valid `PGconn *conn` and included libpq headers.

### Does JDBC Use This API Directly?

Standard JDBC does not expose `PQTRANS_*` constants as a cross-driver contract. In JDBC, rely on **application-owned transaction lifecycle**, `SQLException.getSQLState()`, `Connection.rollback()`, and driver/framework error handling. Do not write Java code expecting libpq APIs that do not exist in standard JDBC.

## 19. pg_stat_activity and the "idle in transaction (aborted)" State

When a session has a failed transaction that the client has not rolled back yet, PostgreSQL displays:

```text
idle in transaction (aborted)
```

in `pg_catalog.pg_stat_activity` while the backend waits idle for the next command.

Diagnostic query example:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    state_change,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction (aborted)'
ORDER BY state_change;
```

**Run this from a separate healthy monitoring connection.** Inside the failed transaction itself, even `SELECT pg_stat_activity` fails with `25P02`.

### What Operational Impact Does This State Have?

It indicates a client left a failed transaction **unresolved**. Impacts can include:

- A connection remains occupied and unable to serve normal requests.
- Connection pool exhaustion if many requests leak connections in this state.
- Application loops repeatedly sending SQL and only receiving `25P02`.
- Wasted backend/session resources and obscured root-cause visibility.

Do not assume an aborted transaction still holds every row lock exactly like a healthy transaction; PostgreSQL's abort cleanup can release related locks/resources. The primary issue is **an unhandled transaction and connection lifecycle**.

### Privileges to View pg_stat_activity

Regular roles may have restricted visibility into other sessions' details. Use a monitoring role with least-privilege permissions; never grant superuser just to inspect session state.

## 20. Timeouts, Cancellations, and Transaction State

A SQL statement can fail due to a timeout or cancellation:

```sql
BEGIN;

SET LOCAL statement_timeout = '100ms';

SELECT pg_sleep(1);
-- May raise ERROR 57014 query_canceled due to statement_timeout.

SELECT 1;
-- May raise ERROR 25P02 because transaction is already failed.

ROLLBACK;
```

`SET LOCAL` configures the setting for the current transaction. When `pg_sleep(1)` is canceled by `statement_timeout`, the failing statement puts the explicit transaction into the aborted state, just like other SQL errors.

### Different Types of Timeouts

| Mechanism | Typical Impact |
|---|---|
| `statement_timeout` | Cancels a SQL statement running past the limit. |
| `lock_timeout` | Errors when waiting for a lock exceeds the limit. |
| `idle_in_transaction_session_timeout` | Terminates sessions idle in a transaction too long. |
| JDBC / pool / network timeout | May cancel the statement, drop the connection, or throw client-side errors depending on where it triggers. |

Do not assume all timeouts produce the same SQLSTATE or connection state. If the server **closed the connection**, you cannot run `ROLLBACK` on the dead connection; discard the connection and reconcile business state as verifiable.

### Query Cancel Is Not Automatic Transaction Rollback

When a SQL statement is canceled inside an explicit transaction, the safe reaction is to **identify the error, roll back the transaction or revert to a valid savepoint**, and then start new work. Never just re-send the statement on a failed transaction.

## 21. Deadlocks and Serialization Failures: Roll Back and Retry the Whole Transaction

Two errors commonly classified as **transient** under concurrency:

- `40P01` — deadlock detected.
- `40001` — serialization failure.

They do not mean your SQL syntax is wrong. Two valid transactions simply collided due to concurrent execution timing.

### Why Retrying One Statement Is Wrong

Suppose a transaction runs:

```text
BEGIN
  SELECT current_balance
  Compute transfer decision
  UPDATE accounts
  INSERT transfer_history
COMMIT
```

If `UPDATE` or `COMMIT` hits `40001`, retrying **only the UPDATE** inside the same transaction does not re-evaluate the initial reads and decisions. You must:

1. Ensure the old transaction **ended / rolled back**.
2. Start a **new** transaction.
3. Re-read relevant data.
4. Recompute business decisions.
5. Re-apply all changes.
6. Commit, treating the operation as successful only once commit succeeds.

### Retries Must Be Bounded

- Cap attempts (e.g., 3–5 depending on SLA and workload).
- Use backoff with jitter when multiple workers contend.
- Log the SQLSTATE and attempt count.
- Ensure external side effects are **idempotent** or coordinated via an outbox.
- Once retries are exhausted, return an observable error to the upper tier.

Never retry indefinitely, as it hides design flaws and worsens contention spikes.

## 22. Unique Violation: Roll Back or Handle with ON CONFLICT?

For the goal "insert SKU if not already present," `23505` can be an expected business case. Do not trigger the error and try to continue inside a transaction without a savepoint.

PostgreSQL supports:

```sql
INSERT INTO lesson_tx_error.products(
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Replacement keyboard', 5)
ON CONFLICT (sku) DO NOTHING;
```

When the SKU collides, the command skips inserting and **does not raise `23505` for the handled conflict**. The transaction can continue normally.

If you want to update on conflict:

```sql
INSERT INTO lesson_tx_error.products(
    product_id, sku, product_name, quantity
)
VALUES (3, 'SKU-001', 'Replacement keyboard', 5)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name;
```

Make sure update rules are intentional so you do not accidentally overwrite data. `ON CONFLICT` only handles conflicts matching its syntax; other constraint violations can still fail the transaction.

### Choosing by Business Requirement

| Requirement | Strategy |
|---|---|
| Duplicate key is a **critical error** | Raise `23505`, roll back transaction, return proper business error. |
| Duplicate key can be **ignored** | `ON CONFLICT DO NOTHING` when policy permits. |
| Duplicate key should **conditionally update** | `ON CONFLICT DO UPDATE ... WHERE ...`. |
| Optional item in an import fails | Use a savepoint to skip that item and log the reason. |
| Need to keep every raw submission | Store append-only raw rows and deduplicate in a separate canonical table. |

**Never use `ON CONFLICT` as a blanket trick to hide all data errors.** Specify the exact key/constraint and what a conflict means.

## 23. Foreign Keys and CHECK: The First Error Must Be Handled

Foreign key violation example:

```sql
BEGIN;

INSERT INTO lesson_tx_error.audit_events(
    audit_id, event_name, product_id
)
VALUES (902, 'unknown-product', 999999);
-- ERROR 23503

SELECT 1;
-- ERROR 25P02

ROLLBACK;
```

`CHECK` violation example:

```sql
BEGIN;

UPDATE lesson_tx_error.products
SET quantity = -100
WHERE product_id = 1;
-- ERROR 23514

SELECT product_id
FROM lesson_tx_error.products;
-- ERROR 25P02

ROLLBACK;
```

The fix is never disabling constraints "so the transaction can keep going," unless part of an approved schema change. Constraints protect data invariants; the application layer should validate inputs, handle errors, and roll back cleanly.

## 24. Deferred Constraints: Errors Can Arrive at COMMIT

PostgreSQL supports `DEFERRABLE` constraints for certain unique, foreign key, and exclusion constraints. When marked `INITIALLY DEFERRED` or switched via `SET CONSTRAINTS ... DEFERRED`, checks are postponed until transaction end.

Lab illustration:

```sql
CREATE TABLE lesson_tx_error.deferred_demo (
    id INTEGER PRIMARY KEY,
    group_code TEXT,
    CONSTRAINT uq_deferred_group_code
        UNIQUE (group_code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Test inside a transaction:

```sql
BEGIN;

INSERT INTO lesson_tx_error.deferred_demo(id, group_code)
VALUES (1, 'A'), (2, 'A');

COMMIT;
-- Can fail with 23505 at COMMIT; transaction is not committed.
```

Key takeaway: **the INSERT can report success while COMMIT fails** due to deferred constraints. Always verify the commit outcome rather than only earlier statement executions.

After a commit failure, assess transaction/session state based on actual server/driver status rather than assuming it always mirrors a mid-transaction `23505` inside `BEGIN`.

### Not Every Constraint Is Deferrable

Not every constraint type or unique index supports deferral identically. Design schemas deliberately, and never treat `SET CONSTRAINTS DEFERRED` as a permanent escape hatch: if data still violates the rule at final validation, commit will fail.

## 25. PL/pgSQL EXCEPTION Can Recover Errors Inside a Block

In PL/pgSQL, a block with an `EXCEPTION` clause executes via PostgreSQL's internal **subtransaction** mechanism. When SQL inside the block errors and is caught by a handler, database changes made within that block roll back while the outer transaction **can continue**.

Example:

```sql
CREATE OR REPLACE FUNCTION lesson_tx_error.try_optional_sku()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        INSERT INTO lesson_tx_error.products(
            product_id, sku, product_name, quantity
        )
        VALUES (999, 'SKU-001', 'Intentional duplicate', 1);

        RETURN 'inserted';
    EXCEPTION
        WHEN unique_violation THEN
            RETURN 'duplicate-sku-skipped';
    END;
END;
$$;
```

Call it:

```sql
BEGIN;

SELECT lesson_tx_error.try_optional_sku() AS result;
-- duplicate-sku-skipped

SELECT COUNT(*) FROM lesson_tx_error.products;
-- Can continue; transaction is not aborted by the caught error.

ROLLBACK;
```

**This does not mean PL/pgSQL handlers make every error safe**:

- Only errors genuinely **caught and handled** follow this recovery path.
- If the handler re-raises with `RAISE;`, the caller's transaction can still abort.
- A handler catching `unique_violation` may catch a violation on a constraint **other than the expected SKU**; check the constraint name when precision is needed.
- Never write `WHEN OTHERS THEN NULL` casually, as it hides data bugs, permission errors, and serious faults.

### PL/pgSQL Variables and Database Data

When an exception is caught, persistent database changes in the failing block roll back via the subtransaction. PL/pgSQL local variables follow their own state rules; never mistake variable retention for database persistence or rollback of external state.

## 26. Catching the Exact Constraint in EXCEPTION

Suppose you only want to skip conflicts on `products_sku_key`, while letting any other `unique_violation` propagate.

```sql
CREATE OR REPLACE FUNCTION lesson_tx_error.try_insert_known_sku(
    p_product_id BIGINT,
    p_sku TEXT,
    p_product_name TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_constraint_name TEXT;
BEGIN
    INSERT INTO lesson_tx_error.products(
        product_id, sku, product_name, quantity
    )
    VALUES (p_product_id, p_sku, p_product_name, 0);

    RETURN TRUE;
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint_name = CONSTRAINT_NAME;

        IF v_constraint_name = 'products_sku_key' THEN
            RETURN FALSE;
        END IF;

        RAISE;
END;
$$;
```

This illustrates:

- `GET STACKED DIAGNOSTICS` inspects metadata of the active exception.
- `CONSTRAINT_NAME` separates expected SKU collisions from primary-key violations.
- `RAISE;` inside the handler rethrows unexpected errors.

In practice, **`INSERT ... ON CONFLICT (sku) DO NOTHING`** is usually simpler for "skip if SKU exists." Use exception handlers only when custom branching logic is required.

## 27. JDBC: Failed Transactions Must Roll Back in catch

In JDBC, once `Connection.setAutoCommit(false)` is set, subsequent SQL statements join an application-controlled transaction. A `SQLException` can leave the PostgreSQL transaction aborted.

Core pattern:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement update = connection.prepareStatement("""
                UPDATE lesson_tx_error.products
                SET quantity = quantity - 1
                WHERE product_id = ?
                """)) {
            update.setLong(1, 1L);
            update.executeUpdate();
        }

        try (PreparedStatement insert = connection.prepareStatement("""
                INSERT INTO lesson_tx_error.products(
                    product_id, sku, product_name, quantity
                )
                VALUES (?, ?, ?, ?)
                """)) {
            insert.setLong(1, 3L);
            insert.setString(2, "SKU-001");
            insert.setString(3, "Duplicate product");
            insert.setInt(4, 5);
            insert.executeUpdate();  // May throw SQLException 23505.
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

This snippet illustrates Java inside a method declaring `throws SQLException` with a valid `DataSource dataSource`, using Java text blocks; imports are omitted for brevity.

Key points:

1. **Never commit** if any step failed to execute validly.
2. In `catch`, call `rollback()` to clean up the transaction before closing/returning the connection to the pool.
3. If rollback itself fails, **do not hide the original exception**; attach it via `addSuppressed`.
4. Connections can break or drop; if `rollback()` fails, do not reuse the connection as if it were clean.
5. When a framework manages transactions, use the framework's transaction mechanism instead of manually rolling back a framework-owned connection.

### Should You Restore autoCommit?

In real pool/connection setups, follow your `DataSource`'s state-reset contract. In the snippet above, the connection is borrowed inside `try-with-resources` and closed (returned to the pool if pooled). Never assume **every pool resets all session settings and transaction state**. If you retain a connection across operations manually, rigorously restore auto-commit, isolation, read-only, and session state.

## 28. SQLException.getSQLState(): Never Match Errors by Message Text

Simple classification handler:

```java
try {
    statement.executeUpdate(sql);
} catch (SQLException e) {
    String state = e.getSQLState();

    if ("23505".equals(state)) {
        // Unique constraint violation.
    } else if ("40001".equals(state) || "40P01".equals(state)) {
        // Candidate to retry the entire transaction per policy.
    } else if ("25P02".equals(state)) {
        // Transaction already failed; locate root exception and roll back.
    }

    throw e;
}
```

This sample assumes `statement` and `sql` are defined, illustrating exception classification rather than full transaction control.

### Why Avoid Matching English Message Text?

Error wording can change with locale, server version, or error context:

```java
// Avoid this:
if (e.getMessage().contains("duplicate key")) {
    // ...
}
```

SQLSTATE is a structured code designed for programmatic handling. With pgJDBC, server error objects can also expose constraint, table, and column names via driver-specific APIs; read those structured fields when finer granularity than `23505` is required.

### SQLException Cause Chains

A JDBC failure may carry `getNextException()` or a cause chain. When logging, preserve the SQLSTATE and context of the **first error**. Never log only a trailing `25P02` and discard the earlier cause.

## 29. JDBC Savepoint: Handling Optional Steps

JDBC provides `java.sql.Savepoint` and methods:

- `Connection.setSavepoint()` or `setSavepoint(name)`.
- `Connection.rollback(savepoint)`.
- `Connection.releaseSavepoint(savepoint)`.

Example:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Mandatory business step:
        try (PreparedStatement ps = connection.prepareStatement("""
                UPDATE lesson_tx_error.products
                SET quantity = quantity - 1
                WHERE product_id = ?
                """)) {
            ps.setLong(1, 1L);
            ps.executeUpdate();
        }

        Savepoint optionalInsert = connection.setSavepoint("optional_insert");

        try {
            try (PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO lesson_tx_error.products(
                        product_id, sku, product_name, quantity
                    )
                    VALUES (3, 'SKU-001', 'Duplicate', 5)
                    """)) {
                ps.executeUpdate();
            }
        } catch (SQLException e) {
            if ("23505".equals(e.getSQLState())) {
                connection.rollback(optionalInsert);
                // Discard only the optional step per defined policy.
            } else {
                throw e;
            }
        }

        connection.releaseSavepoint(optionalInsert);
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

Use this pattern only when **any unique violation in the optional step is safe to skip**. If you need to distinguish primary-key collisions from SKU collisions, inspect the **constraint name** via driver APIs or use `ON CONFLICT (sku)`.

### Savepoints Recover Database Errors, Not Broken ORM State

A valid savepoint restores PostgreSQL to a runnable transaction, yet **does not guarantee an ORM's in-memory object/`EntityManager` cache remains consistent** after a failed flush. With Hibernate/JPA, after a persistence exception you should normally roll back and discard the persistence context per framework guidance rather than trying to "salvage" a broken ORM session with manual savepoints.

## 30. Spring @Transactional and rollback-only

In Spring applications, a `@Transactional` method normally runs inside a transaction-manager-controlled transaction:

```java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeInventory(long productId) {
        repository.decrementQuantity(productId);
        repository.insertOptionalRelatedRecord(productId);
    }
}
```

This is an illustrative skeleton, not a complete compilable Java file; repository methods must be defined by the application.

In standard Spring transaction management:

- When a runtime exception escapes a transactional method, the framework marks the transaction for rollback.
- By default in many Spring setups, **unchecked exceptions** and `Error` trigger rollback, whereas **checked exceptions** require `rollbackFor` to trigger rollback.
- If an inner component marks a transaction **`rollback-only`**, an outer caller trying to commit may receive `UnexpectedRollbackException`.
- **Catching and ignoring an exception** never restores a failed PostgreSQL transaction.

### Dangerous Anti-Pattern: Catching a SQL Error and Continuing

```java
@Transactional
public void dangerousWorkflow() {
    try {
        repository.insertDuplicateSku(); // May throw DataAccessException.
    } catch (DataAccessException ignored) {
        // Wrong if assuming the PostgreSQL transaction recovered.
    }

    repository.updateInventory(); // Likely hits SQLSTATE 25P02.
}
```

**The problem:** catching a Java exception is not equivalent to executing `ROLLBACK` or `ROLLBACK TO SAVEPOINT` on PostgreSQL.

### Proper Alternatives

1. If the error invalidates the business operation: **let the exception trigger rollback** and return an appropriate error.
2. If duplicates are valid and expected: use **`ON CONFLICT`** or idempotent design.
3. If an optional step can genuinely roll back independently: use **transaction propagation/savepoints** supported by both the transaction manager and JDBC driver, checking ORM constraints.
4. If independent work needs isolation: consider a separate transaction via `REQUIRES_NEW` aligned with framework semantics and pool sizing.

`PROPAGATION_NESTED` relies on savepoints in supported transaction managers; do not assume every JPA stack supports it. `REQUIRES_NEW` opens an **independent transaction**—not a "stronger savepoint"—and consumes an extra connection.

## 31. Catching an Exception Does Not Mean the Transaction Was Saved

Two pairs of situations to distinguish:

### Case A — Java-Layer Exception Before Sending SQL

```java
if (quantity < 0) {
    throw new IllegalArgumentException("quantity must be >= 0");
}
```

If an error occurs **before any statement is sent** to PostgreSQL, the database has not hit a SQL error. Transaction fate depends on the transaction manager and how the exception is handled.

### Case B — PostgreSQL Already Rejected the Statement

```java
statement.executeUpdate(
    "UPDATE lesson_tx_error.products SET quantity = -1 WHERE product_id = 1"
);
// PostgreSQL returns 23514 and the explicit transaction is aborted.
```

Here, even if Java catches `SQLException` and does not rethrow it, the PostgreSQL transaction **remains failed** until rolled back to a valid savepoint or terminated.

### Case C — PL/pgSQL Handler Resolves Error Internally

A function with `EXCEPTION WHEN ...` recovers via a subtransaction **inside the server**, so the caller's transaction stays healthy if the function returns normally. This mechanism is fundamentally different from a plain **Java catch**.

## 32. Batch Inserts: One Bad Row Can Fail the Whole Batch

With JDBC batching:

```java
try (PreparedStatement ps = connection.prepareStatement("""
        INSERT INTO lesson_tx_error.products(
            product_id, sku, product_name, quantity
        ) VALUES (?, ?, ?, ?)
        """)) {
    // ... addBatch multiple times ...
    ps.executeBatch();
}
```

If one element in the batch errors while the transaction is in manual-commit mode, **do not assume the remaining elements can commit normally**.

Exact behavior regarding which statements in the batch ran/sent, update counts, and exception details depends on the driver and batch optimizations. However, inside an explicit PostgreSQL transaction, an unhandled error from a statement aborts the transaction.

### Designing Imports That Handle Bad Rows

Your options include:

- **All-or-nothing:** if any batch row fails, roll back the entire batch and report failure.
- **Controlled row skipping:** use savepoints per unit or split into smaller transactions, saving an error report.
- **Idempotent upsert:** if expected collisions are the issue, use `ON CONFLICT`.
- **Pre-validation:** reduces errors, though does not replace constraints due to concurrent races.

Never catch `BatchUpdateException`, call `COMMIT`, and hope PostgreSQL keeps "whichever rows succeeded."

## 33. Failed Transactions and Connection Pools

Connection pools (HikariCP, PgBouncer, etc.) **reuse connections** to reduce connection overhead. If an application leaves a failed transaction unfinished, that state breaks subsequent operations on the same backend until rolled back.

```text
Request A
  borrows connection X
  BEGIN
  INSERT -> 23505
  [forgets ROLLBACK]
  returns/leaves connection uncleanly
                   │
                   ▼
Request B
  reuses backend X
  SELECT -> likely receives 25P02
```

Some pools reset or roll back on return, yet **never assume every pool/proxy configuration automatically saves application bugs**. The transaction owner must end it properly; pool cleanup is only a safety net.

### Core Principles

1. Every request/job has an explicit **transaction boundary**.
2. On exception, roll back in `finally`/`catch` or let the framework roll back.
3. Never hold connections open during slow external I/O when no transaction is needed.
4. If rollback fails or the network drops, **evict/discard the untrusted connection** via pool APIs.
5. Never mutate autocommit/session settings across multiple layers without a strict reset contract.
6. Monitor connection leaks, pool exhaustion, and `idle in transaction (aborted)`.

### PgBouncer Does Not Fix Broken SQL Transactions Automatically

PgBouncer supports pooling modes with different backend lifecycles. Even when a proxy manages connection multiplexing, **the active SQL transaction must still be ended cleanly by the application**. Never treat a proxy as a substitute for proper rollback/savepoints.

## 34. Losing Connection During COMMIT: Outcome May Be Unknown

A particularly dangerous edge case:

```text
Client sends COMMIT
       │
       ▼
PostgreSQL may commit
       │
       ├── response reaches client -> client knows success
       │
       └── network drops before response -> client is unsure of outcome
```

If the network drops **after the server committed but before the client received the response**, the client sees an I/O error and cannot tell whether the transaction committed or not. On that broken connection, you cannot send a rollback and assume the work was undone.

### Handling Critical Business Operations

- Use an **idempotency key** backed by a unique constraint for safe retries.
- Support **reconciliation queries** by business transaction ID.
- Never blindly resend a transfer or order creation that could duplicate side effects.
- Distinguish server SQLSTATE errors from client/network errors in logs.
- Never report "definitely rolled back" without proof from the server.

This does not contradict ACID: the database ensured the transaction either committed or rolled back, while **the client lost visibility of the outcome** at that moment.

## 35. Read-Only Transactions Can Also Enter Failed State

Do not assume read-only transactions are immune:

```sql
BEGIN READ ONLY;

SELECT 'abc'::integer;
-- 22P02

SELECT 1;
-- 25P02

ROLLBACK;
```

`READ ONLY` forbids inappropriate writes, yet does not prevent arithmetic, syntax, privilege, or serialization errors. Errors like `42P01`, `42703`, or `57014` also abort explicit read-only transactions.

### BEGIN READ ONLY Does Not Guarantee SELECT Always Succeeds

Missing `SELECT` privileges, RLS rules, and runtime query errors can still fail or return 0 rows. A failed read-only transaction still requires rollback like any other transaction.

## 36. DDL Can Also Abort a Transaction

PostgreSQL supports many DDL operations inside transactions:

```sql
BEGIN;

CREATE TABLE lesson_tx_error.temp_example (
    id INTEGER PRIMARY KEY
);

CREATE TABLE lesson_tx_error.temp_example (
    id INTEGER PRIMARY KEY
);
-- ERROR: relation already exists

SELECT 1;
-- 25P02

ROLLBACK;
```

After rollback, `temp_example` created by the first statement **no longer exists** (assuming no prior table existed). This demonstrates PostgreSQL's **transactional DDL**.

### Not Every DDL Statement Can Run Inside a Transaction Block

Some administrative commands must run outside a transaction block or have special transaction rules. Never blindly wrap an entire migration script in `BEGIN ... COMMIT` assuming every command supports it.

When a supported DDL statement fails inside a transaction, recovery still uses rollback or a valid savepoint, just like DML.

## 37. Similar-Looking SQLSTATE Codes Have Different Meanings

SQLSTATE is a 5-character code. The first two characters indicate the **error class**:

- `23`: integrity constraint violation, such as `23505` or `23503`.
- `22`: data exception, such as `22P02`.
- `25`: invalid transaction state, including `25P02`.
- `40`: transaction rollback, such as `40001` and `40P01`.
- `42`: syntax error or access rule violation.
- `57`: operator intervention, such as `57014`.
- `08`: connection exception.

Do not lump all classes under one retry/error policy. For example:

```text
23505 unique violation
    -> usually data error / duplicate identity

40001 serialization failure
    -> candidate to retry the entire transaction

40P01 deadlock detected
    -> candidate to retry the entire transaction per policy

25P02 in failed SQL transaction
    -> must clean up failed transaction and find root error

08006 connection failure
    -> connection state can no longer be trusted
```

**`25P02` is a state signal telling the app to recover the transaction**, not a reason to retry the single statement that received it.

## 38. Application Error-Handling Flowchart

A decision flow:

```text
Start transaction
        │
        ▼
Execute business logic
        │
        ├── No error ──► COMMIT
        │                   │
        │             Succeeded?
        │                │      │
        │              Yes      No
        │                │        │
        │              Done   Analyze commit error
        │                         │
        └── Error ────────────────┘
                  │
                  ▼
          Valid savepoint exists and
          business permits skipping step?
               │              │
              Yes            No
               │              │
               ▼              ▼
       ROLLBACK TO s       Full ROLLBACK
               │              │
         Continue rest     Retry needed?
         if transaction        │
         is healthy           ├── Yes -> new transaction,
               │              │          redo from start
               ▼              │
             COMMIT           └── No  -> report failure
```

This diagram shows the logical decision flow. For **connection-loss** errors, rollback may be impossible and commit outcome may be uncertain. In that case, discard the connection and perform reconciliation/idempotency checks.

## 39. Common Misconceptions

**"An INSERT error only cancels that INSERT, so I can keep running UPDATEs."** In an explicit PostgreSQL transaction, a normal SQL error aborts **the entire transaction** until you roll back or revert to a valid savepoint.

**"SQLSTATE 25P02 is the initial error."** Rarely; it is the result of sending statements after an error. Find the earlier SQLSTATE.

**"Catching SQLException in Java makes the database forget the error."** No. A Java `catch` does not replace server-side transaction rollback.

**"COMMIT after 25P02 commits the earlier successful statements."** No. PostgreSQL returns `ROLLBACK` and discards uncommitted changes.

**"ROLLBACK TO SAVEPOINT also ends the outer transaction."** No. It reverts to the marker; the outer transaction remains open and still needs `COMMIT`/`ROLLBACK`.

**"RELEASE SAVEPOINT commits a subtransaction."** No. It merely releases the savepoint marker.

**"I can create a SAVEPOINT after an error."** You cannot use a savepoint created too late to rescue an already aborted transaction.

**"psql recovers automatically from errors, so JDBC does too."** No. `ON_ERROR_ROLLBACK` is a `psql` client feature, not a PostgreSQL default for all clients.

**"Rollback returns all allocated sequence numbers."** No. Sequences can advance and do not roll back allocated numbers.

**"Database rollback recalls sent emails."** No. External side effects require idempotency, outboxes, or compensating actions.

**"Savepoints are the standard way to retry 40001 errors."** No. Serialization failures normally require retrying the **entire transaction**.

**"Every SQLSTATE 23505 should be retried."** No. Conflicts are often real business errors needing an error response.

**"Hitting statement_timeout only cancels that query and keeps the transaction healthy."** Not inside an explicit transaction; cancellation errors abort the transaction.

**"Connection.isValid() returning true means the transaction isn't aborted."** No. The socket can be alive while the transaction is failed; track lifecycle/errors and roll back.

**"Calling close() back into a pool guarantees all state is wiped."** Depends on the pool, driver, and transaction manager; applications must still end transactions cleanly.

**"If COMMIT errors, I can always roll back on the same connection."** Not if the connection dropped; commit outcome may be unknown.

**"If a PL/pgSQL function catches an error, the whole outer transaction rolls back."** Not necessarily. An `EXCEPTION` block rolls back internally via a subtransaction and can return normally to the caller.

**"A successful SELECT before an error means data committed."** No; in an explicit transaction, only commit finalizes state.

**"ON CONFLICT ignores every constraint error."** No. It handles specified/supported conflicts; other errors still abort the transaction.

**"Raising the isolation level makes errors disappear."** No; higher isolation can introduce serialization failures requiring proper retries.

## 40. Operational Checklist for Failed Transactions

When an application encounters `25P02` or `idle in transaction (aborted)`:

1. **Locate the first failing statement** in the same request/transaction, inspecting its SQLSTATE and constraint/detail.
2. **Stop sending business SQL** on the failed transaction.
3. Identify the **transaction owner**: raw JDBC code, framework, job runner, or migration tool.
4. Unless a properly managed savepoint exists and business policy allows skipping, **roll back the whole transaction**.
5. If using savepoints, verify the savepoint existed before the error and `rollback(savepoint)` succeeded.
6. Never commit the remainder just because an exception was swallowed.
7. Never return a connection in an untrusted state for another request to reuse.
8. Classify the root error: business validation, conflict, deadlock/serialization, timeout, or network.
9. Retry the entire transaction only when policy permits, with bounded attempts and idempotency.
10. Monitor **root error rates**, aborted/idle backends, pool exhaustion, and slow commits.

For network errors during commit, add a **business-state reconciliation step** before resending any side-effecting operation.

## 41. Hands-On Exercises

### Exercise 1 — Observing 23505 Then 25P02

In `psql`, start `BEGIN`, decrement product 1's `quantity`, then insert a new product with `sku = 'SKU-001'`. Note the SQLSTATE of the `INSERT` error and of a subsequent `SELECT 1`. Run `ROLLBACK` and verify the original quantity is unchanged.

### Exercise 2 — A SELECT Error Also Fails the Transaction

Run `BEGIN; SELECT 'bad'::integer; SELECT 2; ROLLBACK;`. Explain why `SELECT 2` receives `25P02` even though no data was modified.

### Exercise 3 — Autocommit vs. Explicit Transaction

Compare running the failing `'bad'::integer` outside `BEGIN` versus inside `BEGIN`. Why does the next SQL statement run in the first case yet get rejected in the second?

### Exercise 4 — COMMIT After a Failed Transaction

In the lab, modify a quantity before causing an error. After the error, try `COMMIT` instead of `ROLLBACK`; observe PostgreSQL's response and inspect the data. Explain why the `UPDATE` succeeded earlier yet was not committed.

### Exercise 5 — ROLLBACK TO SAVEPOINT

Write a two-step transaction: mandatory inventory decrement, then an optional record insert that might collide on SKU. Create a savepoint before the optional step; on error, run `ROLLBACK TO SAVEPOINT`, then insert an audit row and commit. Run only in the lab, and explain what business rules allow skipping the optional step.

### Exercise 6 — RELEASE SAVEPOINT

Explain why `RELEASE SAVEPOINT` does not commit data, and why `RELEASE` alone cannot rescue a transaction that already hit `23505`.

### Exercise 7 — Multi-Level Savepoints

Create `SAVEPOINT s1`, `SAVEPOINT s2`, then run `ROLLBACK TO s2` and `ROLLBACK TO s1` in a lab transaction. Distinguish which operations survive at each marker.

### Exercise 8 — Analyzing a SQLSTATE Chain

A request log shows `23503`, three `25P02` errors, and a rollback failure due to connection loss. Identify which root error to investigate first, the connection state, and why you cannot conclude rollback succeeded once the network dropped.

### Exercise 9 — Querying pg_stat_activity

Use two PostgreSQL lab sessions: Session A creates a failed transaction and leaves it open; Session B queries `pg_stat_activity` for `idle in transaction (aborted)`. Record the backend PID and `state_change` timestamp. Then roll back in A.

### Exercise 10 — psql ON_ERROR_ROLLBACK

In `psql`, enable `\set ON_ERROR_ROLLBACK on` and trigger `SELECT 1/0` mid-transaction. Compare continuing statements afterward against default mode, and explain why JDBC does not automatically inherit this variable.

### Exercise 11 — Migration Scripts

Design how to execute `migration.sql` with `-v ON_ERROR_STOP=1 --single-transaction`. Why can using `ON_ERROR_STOP` without a wrapping transaction still leave earlier committed changes behind?

### Exercise 12 — Deferred Constraints

Create a lab table with a `DEFERRABLE INITIALLY DEFERRED` unique constraint, insert two rows with the same key, and `COMMIT`. Explain why the error surfaces only at commit and why Java code must inspect `commit()` outcomes too.

### Exercise 13 — JDBC Rollback

Write a JDBC method enabling `setAutoCommit(false)`, running two updates/inserts, committing on success, and rolling back inside `catch(SQLException | RuntimeException)`. If rollback fails, preserve the root exception and attach the rollback exception.

### Exercise 14 — JDBC Savepoints

Use `Connection.setSavepoint`, trigger `23505` in an optional step, call `rollback(savepoint)`, and continue updating in the outer transaction. Explain why you must not ignore all `SQLException`s without filtering by SQLSTATE.

### Exercise 15 — Spring and Swallowed Exceptions

Analyze a `@Transactional` method with a `try/catch(DataAccessException)` followed by another repository call. What happens in PostgreSQL and the transaction manager? Redesign it so errors trigger rollback or use valid savepoints/upserts.

### Exercise 16 — Retrying Serialization Failures

Write retry pseudocode for `getSQLState() == "40001"`. Each attempt must open a new transaction, re-read data, and recompute decisions. Bound the attempts, add backoff, and explain the risk of sending emails inside the retry loop.

### Exercise 17 — Deadlocks

Describe two transactions locking accounts 1 and 2 in opposite orders. When PostgreSQL detects deadlock `40P01`, why can't you just retry the waiting statement inside the aborted victim transaction?

### Exercise 18 — Timeouts and Query Cancellations

In the lab, run `BEGIN; SET LOCAL statement_timeout = '100ms'; SELECT pg_sleep(1);`. Observe the error and the outcome of a subsequent `SELECT 1`. When must you roll back, and how does connection loss differ?

### Exercise 19 — ON CONFLICT

Write `INSERT ... ON CONFLICT (sku) DO NOTHING` for a product with a duplicate SKU. Contrast with a plain `INSERT` raising `23505` inside a transaction. When is ignoring conflicts a valid business choice?

### Exercise 20 — PL/pgSQL EXCEPTION

Create a function with `EXCEPTION WHEN unique_violation`, attempt to insert a duplicate SKU, and return a status string. Call it inside `BEGIN`, then run another `SELECT`. Explain the difference between a server-side exception block and a Java `catch`.

### Exercise 21 — Database Rollback vs. Side Effects

A transaction updates the DB and sends an email to a customer, then hits an error and rolls back. Does the sent email disappear? Propose a transactional outbox protocol or idempotent delivery design.

### Exercise 22 — Network Drop at COMMIT

A client sends `COMMIT` and loses its connection before receiving a response. Analyze both possibilities (server committed vs. did not commit) and design an idempotency key for safe retries without duplicates.

### Exercise 23 — Connection Pools

A request triggers `23505` and returns its connection to the pool without rolling back. Describe how the next request can hit `25P02`, highlighting the transaction owner's responsibility versus the pool's defensive role.

### Exercise 24 — Classifying Retryable Errors

For SQLSTATEs `23505`, `23503`, `40001`, `40P01`, `57014`, `25P02`, and `08006`, propose distinct policies: rollback, business error, full-transaction retry, connection eviction, or commit reconciliation. Explain why there is no valid "retry every error" policy.

## Summary

In PostgreSQL, a SQL error occurring inside an **explicit transaction** normally moves the transaction to **failed/aborted**, and subsequent statements receive **SQLSTATE `25P02`** instead of executing normally. Locate the **first error**—such as `23505`, `23503`, `22P02`, `40001`, or `57014`—to diagnose the cause rather than fixing only the final statement reporting `25P02`.

**`ROLLBACK` is the default recovery path** when a transaction can no longer complete validly. If an individual step is allowed to fail by business policy, a **`SAVEPOINT` created before that step** paired with `ROLLBACK TO SAVEPOINT` discards the failed work and lets the same transaction continue. `RELEASE SAVEPOINT` is not an independent commit, and `COMMIT` on an aborted transaction cannot salvage changes made before the error.

At the application tier, **catching an exception does not replace rollback**. JDBC needs `rollback()` in failure handling; Spring needs proper transaction propagation and rollback rules; `psql ON_ERROR_ROLLBACK` is strictly a client convenience. Concurrency errors like `40001`/`40P01` normally require **retrying a brand-new full transaction**, bounded and idempotent. When the network drops during commit, the outcome may be unknown, requiring reconciliation rather than assuming a rollback occurred.

A resilient workflow **defines clear transaction boundaries, captures the root error, rolls back at the proper scope, never continues on an aborted connection, and starts fresh work only once state is unambiguous**. That is the foundation for maintaining atomicity, avoiding cascading `25P02` errors, and handling transaction failures safely in PostgreSQL applications.
