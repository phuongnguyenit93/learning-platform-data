# SAVEPOINT, ROLLBACK TO, and Partial Error Handling in PostgreSQL

A PostgreSQL transaction ensures that a group of data operations is confirmed (`commit`) or discarded (`rollback`) according to transaction rules. However, real-world applications often face a subtler requirement: **an optional step fails, yet valid earlier steps must still be kept so the transaction can continue**.

For example, suppose a system imports 100 rows of data: 97 rows are valid, two have duplicate keys, and one references a nonexistent customer. If every row runs in a single transaction, a failing statement puts the transaction into a state where it cannot continue executing. Rolling back everything loses all 97 valid rows; ignoring the error and continuing with `INSERT` makes PostgreSQL report that the transaction is aborted.

**`SAVEPOINT`** solves this problem by placing a marker inside the transaction. When an operation after that marker fails, you can run **`ROLLBACK TO SAVEPOINT`** to discard changes made after the marker, restore the transaction to a runnable state, and preserve the valid changes made beforehand. If the step succeeds, you can run **`RELEASE SAVEPOINT`** to drop the unneeded marker.

The most important point:

> **SAVEPOINT lets you roll back part of a transaction's work, but it does not create an independent transaction and does not independently commit any part.** All remaining changes still depend on the final `COMMIT` or `ROLLBACK`.

This lesson covers savepoint syntax, lifecycle, behavior on SQL errors, nested markers, row-by-row import handling, usage in Java/JDBC and PL/pgSQL, interactions with constraints, locks, sequences, and errors that require retrying the entire transaction.

## 1. Reviewing a Transaction's Lifecycle

PostgreSQL typically operates with two ways of grouping statements:

- **Autocommit / implicit transactions:** if the client has not opened an explicit transaction, each SQL statement normally runs in its own transaction.
- **Explicit transactions:** statements between `BEGIN` and `COMMIT` or `ROLLBACK` belong to the same transaction and share the same confirmation or discard boundary.

Example:

```sql
BEGIN;

UPDATE some_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE some_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

`some_accounts` above is a hypothetical table. A later section builds a runnable lab schema.

If both `UPDATE` statements are valid and `COMMIT` succeeds, the changes are confirmed together. If the application calls `ROLLBACK` before committing, all changes since `BEGIN` are discarded.

### 1.1. What Happens When a SQL Statement Errors?

In PostgreSQL, when a statement raises a normal SQL error **inside an explicit transaction**, the transaction transitions to a **failed/aborted** state. Subsequent SQL statements cannot proceed normally until the client rolls back the transaction or rolls back to a valid savepoint.

Example sequence:

```text
BEGIN
  |
  +-- valid INSERT                  -> OK
  |
  +-- INSERT duplicate unique key   -> ERROR 23505
  |
  +-- subsequent SELECT or UPDATE   -> ERROR 25P02
  |
  +-- ROLLBACK                      -> abort transaction
```

The second error typically reads:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

SQLSTATE `25P02` means **in_failed_sql_transaction**. It is rarely the original root cause; the root cause may be `unique_violation`, `foreign_key_violation`, or another earlier error.

**Do not just fix the SQL statement and resend it inside the same failed transaction.** You must recover transaction state using `ROLLBACK TO SAVEPOINT` (when a valid savepoint exists) or discard the whole transaction with `ROLLBACK`.

### 1.2. Statement Atomicity Differs from Full-Transaction Rollback

A multi-row `INSERT` statement is still **a single SQL statement**. If one row in that statement violates a constraint without conflict handling, PostgreSQL does not keep earlier rows from the same statement and drop only the bad row.

Savepoints mark boundaries **between operations within a transaction**. They do not turn a failing `INSERT ... VALUES (...), (...), (...)` into an automatic filter that inserts valid rows. To handle rows individually, you need separate appropriately guarded statements, staging/import pipelines, `ON CONFLICT`, PL/pgSQL handlers, and so on.

## 2. Basic Syntax of SAVEPOINT, ROLLBACK TO, and RELEASE

Three commands to remember:

```sql
SAVEPOINT savepoint_name;

ROLLBACK TO SAVEPOINT savepoint_name;

RELEASE SAVEPOINT savepoint_name;
```

PostgreSQL also accepts the shorthand `ROLLBACK TO name` and `RELEASE name`, though the full forms make the intent clear for readers.

### 2.1. SAVEPOINT: Setting a Marker

```sql
BEGIN;
SAVEPOINT before_optional_step;
-- Perform operations that may need to be undone.
```

`SAVEPOINT` creates a named point inside the current transaction. It **does not commit** prior changes, nor does it start an independent transaction.

### 2.2. ROLLBACK TO SAVEPOINT: Reverting to a Marker

```sql
ROLLBACK TO SAVEPOINT before_optional_step;
```

PostgreSQL undoes the rollbackable effects of operations performed **after the savepoint**, while preserving changes made **before the savepoint** within the transaction.

Once the rollback to the marker succeeds, the transaction can accept new SQL commands again.

### 2.3. RELEASE SAVEPOINT: Dropping the Marker Without Committing

```sql
RELEASE SAVEPOINT before_optional_step;
```

`RELEASE` removes the savepoint marker and keeps the changes performed since that marker **within the still-open transaction**. It **does not confirm changes externally**.

If `ROLLBACK;` is called later, the changes "kept" by `RELEASE` are still discarded along with the entire transaction.

### 2.4. Comparing the Three Commands

| Command | Data Changes After Marker | Savepoint | Outer Transaction |
| --- | --- | --- | --- |
| `SAVEPOINT s` | No data change merely from placing marker. | Creates marker `s`. | Remains open. |
| `ROLLBACK TO SAVEPOINT s` | Discards rollbackable changes after `s`. | `s` **still exists**; newer markers are destroyed. | Restored so execution can continue. |
| `RELEASE SAVEPOINT s` | Keeps changes in transaction without committing. | Drops `s` and any savepoints created after it. | Remains open. |
| `ROLLBACK` | Discards all uncommitted transaction changes. | All savepoints expire. | Ends by aborting. |
| `COMMIT` | Confirms remaining changes if valid. | All savepoints expire. | Ends by committing. |

`ROLLBACK TO` and `RELEASE` are valid only for an active savepoint inside an open transaction. Otherwise, PostgreSQL raises an error.

## 3. Diagram of Partial Rollback

Suppose a transaction executes three steps, where B is optional:

```text
BEGIN
  |
  +-- A: write main order                    [keep]
  |
  +-- SAVEPOINT before_B                     [place marker]
  |
  +-- B1: debit funds                        [discard on failure]
  +-- B2: write log with duplicate key       [ERROR]
  |
  +-- ROLLBACK TO SAVEPOINT before_B         [recover]
  |
  +-- C: update valid information            [keep]
  |
  +-- COMMIT                                 [A and C are committed]
```

Logical result:

```text
Before SAVEPOINT:  A  ----------- kept ----------------+
After SAVEPOINT:   B1 + B2 ----- discarded ------------|
After ROLLBACK TO: C  ----------- kept ----------------+
                                                   COMMIT
```

If `ROLLBACK` is called at the end instead of `COMMIT`, **both A and C are also discarded**. That is why a savepoint must never be called a "mini-commit."

## 4. Creating an Independent Lab Dataset

We will use a simulated transfer schema to observe clearly which changes survive partial rollback.

**Safe scope:** run the DDL and DML below only in a practice database. This is a teaching model, **not a production transfer implementation**; real financial systems require concurrency controls, permissions, idempotency, reconciliation, auditing, and stricter ledger mechanics.

### 4.1. Creating the Schema, Accounts Table, and Transfer History Table

```sql
CREATE SCHEMA IF NOT EXISTS savepoint_lab;

CREATE TABLE savepoint_lab.accounts (
    account_id bigint PRIMARY KEY,
    account_name text NOT NULL,
    balance numeric(14, 2) NOT NULL
        CHECK (balance >= 0)
);

CREATE TABLE savepoint_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key text NOT NULL UNIQUE,
    from_account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id),
    to_account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_account_id <> to_account_id)
);

INSERT INTO savepoint_lab.accounts
    (account_id, account_name, balance)
VALUES
    (1, 'An Account',   1000.00),
    (2, 'Bình Account',  500.00),
    (3, 'Chi Account',   100.00);
```

Initial accounts table:

| account_id | account_name | balance |
| ---: | --- | ---: |
| 1 | An Account | 1000.00 |
| 2 | Bình Account | 500.00 |
| 3 | Chi Account | 100.00 |

The initial total balance is **1600.00**.

### 4.2. Checking State Before the Exercise

```sql
SELECT account_id, account_name, balance
FROM savepoint_lab.accounts
ORDER BY account_id;

SELECT transfer_id, request_key, amount
FROM savepoint_lab.transfers
ORDER BY transfer_id;
```

If `transfers` is non-empty or balances differ from the sample dataset, predicted outputs in the following sections will differ. Use a fresh lab schema or reset the data through a controlled script; never run ad-hoc bulk deletes on a database holding real data.

## 5. Complete Experiment: One Step Fails Yet the Transaction Commits

Simulated requirements:

1. Transfer 100 from account 1 to 2 (mandatory, succeeds).
2. Attempt another transfer of 100 from account 1 to 3 but intentionally reuse a duplicate `request_key` (invalid step, must be undone).
3. Transfer 50 from account 2 to 3 (valid step).
4. Commit only the valid operations.

### 5.1. Step A: Open Transaction and Transfer 100 from 1 to 2

Run in **the same connection/session**:

```sql
BEGIN;

UPDATE savepoint_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE savepoint_lab.accounts
SET balance = balance + 100
WHERE account_id = 2;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 2, 100.00);
```

Inside the open transaction, the provisional balances are:

```text
Account 1: 900
Account 2: 600
Account 3: 100
```

These changes are **not committed yet**. Other transactions cannot see them merely because `UPDATE` or `INSERT` succeeded.

### 5.2. Step B: Place a Marker Right Before the Risky Operation

```sql
SAVEPOINT before_optional_transfer;

UPDATE savepoint_lab.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE savepoint_lab.accounts
SET balance = balance + 100
WHERE account_id = 3;
```

Provisional balances inside the transaction right now:

```text
Account 1: 800
Account 2: 600
Account 3: 200
```

Next, **intentionally run a failing statement**:

```sql
INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 3, 100.00);
```

`transfer-A` was already inserted in Step A, so the unique constraint on `request_key` is violated:

```text
ERROR: duplicate key value violates unique constraint ...
SQLSTATE: 23505 (unique_violation)
```

Because the error occurred **after the savepoint**, we can revert to the marker and undo both balance changes made in Step B.

### 5.3. Recovery Step: ROLLBACK TO SAVEPOINT

Once the client receives the error on the INSERT, run:

```sql
ROLLBACK TO SAVEPOINT before_optional_transfer;
```

The transaction returns to active state; both `UPDATE` statements run after the savepoint are undone. Now:

```sql
SELECT account_id, balance
FROM savepoint_lab.accounts
ORDER BY account_id;
```

Result:

| account_id | balance |
| ---: | ---: |
| 1 | 900.00 |
| 2 | 600.00 |
| 3 | 100.00 |

Notice that **Step A remains**, while Step B's changes vanished. There was no need to roll back the entire transaction.

### 5.4. Step C: Continue with Valid Operations

```sql
UPDATE savepoint_lab.accounts
SET balance = balance - 50
WHERE account_id = 2;

UPDATE savepoint_lab.accounts
SET balance = balance + 50
WHERE account_id = 3;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-B', 2, 3, 50.00);

RELEASE SAVEPOINT before_optional_transfer;

COMMIT;
```

`RELEASE` here is a cleanup step demonstrating the lifecycle. Even without `RELEASE` before `COMMIT`, the savepoint automatically ends with the transaction.

### 5.5. Result After COMMIT

```sql
SELECT account_id, balance
FROM savepoint_lab.accounts
ORDER BY account_id;

SELECT request_key, from_account_id, to_account_id, amount
FROM savepoint_lab.transfers
ORDER BY request_key;
```

Balances result:

| account_id | balance |
| ---: | ---: |
| 1 | 900.00 |
| 2 | 550.00 |
| 3 | 150.00 |

Only two valid request keys exist: `transfer-A` and `transfer-B`. The total balance remains **1600.00**.

This experiment demonstrates:

- Updates before the savepoint can still commit.
- Updates after the savepoint roll back if the step fails.
- Updates after the rollback-to can continue and commit.
- There is no independent commit of a savepoint.

### 5.6. Running the Experiment in a Real Client

**Important:** do not send the entire sequence from `BEGIN` to `COMMIT` as a single batch to a tool configured to "stop on error," or expect a batch client to keep running statements after an error.

Run it step by step in the same interactive session: Step A → create savepoint and run both UPDATEs → run the intentionally failing INSERT alone → observe the error → run `ROLLBACK TO SAVEPOINT` → Step C → commit.

- In `psql`, depending on `ON_ERROR_STOP`, a script may halt immediately when a SQL command errors.
- If `psql`'s `ON_ERROR_ROLLBACK` is enabled, the client may automatically insert implicit savepoints before each statement inside a transaction, making behavior differ from manual testing.
- GUIs/IDEs may auto-rollback or auto-commit depending on mode. Check your tool to verify commands genuinely run on **the same connection and transaction**.

If the client already rolled back the whole transaction on error, you cannot recover via a savepoint from the dead transaction; reset the lab and test in a controlled interactive mode.

## 6. What Happens Without SAVEPOINT?

Independent example, run only when `transfer-A` already exists in the table:

```sql
BEGIN;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('transfer-A', 1, 3, 50.00);
```

The statement reports `23505`. If you immediately run:

```sql
SELECT COUNT(*) FROM savepoint_lab.accounts;
```

PostgreSQL reports that the transaction is aborted, typically with SQLSTATE `25P02`.

To exit:

```sql
ROLLBACK;
```

Without a valid savepoint prior to the error, there is no `ROLLBACK TO ...` option to recover only that portion.

### 6.1. Distinguishing Root Error from Cascading Error

| Execution | Possible SQLSTATE | Meaning |
| --- | --- | --- |
| Duplicate `request_key` `INSERT` | `23505` | Unique constraint violated. |
| `SELECT` right after error before rollback | `25P02` | Transaction is already in aborted state. |
| `ROLLBACK` | Succeeds if connection is still alive. | Aborts entire transaction and returns to ready state for a new transaction. |

In application logs, **never retain only the `25P02` error**. Capture the original failing statement's error, because `25P02` is merely a consequence.

## 7. SAVEPOINT Must Live Inside a Transaction

Valid example:

```sql
BEGIN;
SAVEPOINT step_one;
SELECT 1;
RELEASE SAVEPOINT step_one;
COMMIT;
```

Out-of-scope invalid example:

```sql
-- No explicit transaction open:
-- SAVEPOINT outside_tx;
```

PostgreSQL cannot persist a savepoint outside the current transaction boundary. After `COMMIT` or `ROLLBACK`, old savepoints cannot be used in a subsequent transaction.

### 7.1. Savepoint Names and Scope

Savepoint names are SQL identifiers. Descriptive names like `before_import_row` or `before_optional_invoice` are far easier to read than a single letter `s` in long scripts.

```sql
BEGIN;
SAVEPOINT before_import_row;
-- ...
ROLLBACK TO SAVEPOINT before_import_row;
RELEASE SAVEPOINT before_import_row;
COMMIT;
```

If a name requires uppercase or special characters, PostgreSQL applies standard quoted-identifier rules just like other SQL objects. Example:

```sql
BEGIN;
SAVEPOINT "BeforeStep";
RELEASE SAVEPOINT "BeforeStep";
ROLLBACK;
```

Never build savepoint names by concatenating untrusted user strings into SQL; identifiers are not bound like ordinary value parameters.

## 8. ROLLBACK TO Keeps the Chosen Savepoint Alive

A subtle detail often missed: after:

```sql
ROLLBACK TO SAVEPOINT s1;
```

savepoint `s1` **still exists**. You can roll back to that same marker again:

```sql
BEGIN;

SAVEPOINT s1;

SELECT 'attempt 1' AS attempt;
ROLLBACK TO SAVEPOINT s1;

SELECT 'attempt 2' AS attempt;
ROLLBACK TO SAVEPOINT s1;

RELEASE SAVEPOINT s1;
COMMIT;
```

These `SELECT` statements only illustrate scope; to observe data rollback, use `INSERT`/`UPDATE` in the lab schema as in Section 5.

### 8.1. RELEASE Removes the Ability to Return to That Marker

```sql
BEGIN;
SAVEPOINT s1;
SELECT 1;
RELEASE SAVEPOINT s1;

-- Invalid because s1 no longer exists:
-- ROLLBACK TO SAVEPOINT s1;

COMMIT;
```

Once released, **you cannot return to that point** using the old name, unless an earlier savepoint with the same name was shadowed under duplicate-naming rules (Section 10).

### 8.2. You Cannot RELEASE a Savepoint While the Transaction Is Aborted

If a statement after a savepoint raises a SQL error and puts the transaction in the aborted state, `RELEASE SAVEPOINT s` will not recover it. Run `ROLLBACK TO SAVEPOINT s` first.

`RELEASE` is for when a step succeeded and you no longer need the ability to roll back to that marker. After an error, you must clear the failed state first.

## 9. Nested Savepoints and Ordered Markers

You can create multiple savepoints within the same transaction.

```sql
BEGIN;

SAVEPOINT s1;
-- Operation group A

SAVEPOINT s2;
-- Operation group B

SAVEPOINT s3;
-- Operation group C

ROLLBACK TO SAVEPOINT s2;
-- Undoes B and C; s3 is gone, s2 still exists.

RELEASE SAVEPOINT s2;
-- s1 still exists.

RELEASE SAVEPOINT s1;
COMMIT;
```

Diagram:

```text
BEGIN
  |
  +-- SAVEPOINT s1
       |
       +-- operation A
       |
       +-- SAVEPOINT s2
            |
            +-- operation B
            |
            +-- SAVEPOINT s3
                 |
                 +-- operation C
                 |
                 +-- ROLLBACK TO s2

After ROLLBACK TO s2:
  - A remains in transaction
  - B and C are discarded
  - s1 remains
  - s2 remains
  - s3 is destroyed
```

**Rolling back to an older marker destroys all savepoints created after it.** You cannot roll back to `s3` after rolling back to `s2`.

### 9.1. Releasing an Outer Marker Also Releases Inner Markers

If you create `s1`, then `s2`, and then call `RELEASE SAVEPOINT s1`, PostgreSQL releases `s1` along with any savepoints created after it. Data changes remain inside the transaction, though the released markers can no longer be used.

Do not think of savepoints as a stack of transactions committing from inside out. They are **recovery markers within the same transaction**, where rollback-to and release prune newer markers.

### 9.2. Why Clear Structure Matters

In a large application:

```text
Service-level transaction
  +-- Savepoint processing invoice
         +-- Savepoint checking attachment
  +-- Savepoint sending optional audit
```

If one library creates and releases an outer savepoint on its own, it can wipe out inner savepoints. Therefore, layers sharing a single JDBC connection must agree on **who owns savepoint boundaries**, avoiding a helper library releasing a marker it does not own.

## 10. PostgreSQL Allows Reusing Savepoint Names

PostgreSQL permits creating a new savepoint with a name already in use in the same transaction:

```sql
BEGIN;

SAVEPOINT checkpoint;
-- Some early-stage changes.

SAVEPOINT checkpoint;
-- Some later-stage changes.

ROLLBACK TO SAVEPOINT checkpoint;
-- Reverts to the most recently created checkpoint.

RELEASE SAVEPOINT checkpoint;
-- Releases the newest checkpoint; the older checkpoint becomes visible again.

RELEASE SAVEPOINT checkpoint;
COMMIT;
```

Rather than "overwriting" and deleting the old marker, PostgreSQL **retains the earlier same-named marker while shadowing it**. Once the newer one is released, the older same-named marker becomes targetable again.

This behavior can surprise code that generates savepoint names automatically. For maintainability, prefer distinct descriptive names per scope or let the driver manage `Savepoint` objects instead of relying on shadowed names.

## 11. SAVEPOINT Is Not an Independent "Nested Transaction"

Database engines and ORMs sometimes refer to savepoints as **subtransactions** or "nested transactions." While useful for describing recovery mechanics, that phrasing easily causes business-logic misunderstandings.

| Property | Main Transaction | Savepoint |
| --- | --- | --- |
| Can `COMMIT` independently? | Yes, for the whole transaction. | **No**. |
| Can roll back its scope? | Yes, the entire transaction. | Yes, back to the savepoint marker. |
| Changes visible to other transactions after RELEASE? | Not caused by RELEASE. | **No**. |
| Completely isolated identity/sequence scope? | No; some non-rollbackable effects exist. | No. |
| Survives outer transaction COMMIT/ROLLBACK? | Transaction ends. | No. |
| Suitable for an optional step inside a transaction? | Possible via savepoints. | **Yes**. |

Releasing a savepoint **does not make data durable**. When the outer transaction rolls back, all uncommitted changes from released steps are discarded too.

### 11.1. Two Perspectives on Atomicity

- The overall transaction is the atomic unit for committed data.
- Savepoints provide the ability to **selectively keep or discard sub-operations before deciding to commit the whole transaction**.

Thus, "partial error handling" does not break PostgreSQL's final transaction atomicity. It simply lets you decide **which valid set of operations** gets confirmed together.

## 12. A Failing Statement Does Not Mean All Prior Data Already Rolled Back

A common misconception:

> PostgreSQL threw a unique constraint error, so the earlier UPDATEs in my transaction must already be rolled back.

Do not assume that. After a failing statement, the transaction is marked aborted. Earlier uncommitted changes are neither committed nor completely rolled back at the instant of the error; the transaction still needs to be **terminated or recovered to a savepoint** according to the rules.

If you roll back to a mid-transaction savepoint:

- Changes before the savepoint remain inside the transaction.
- Changes after the savepoint are discarded.

If you roll back the whole transaction:

- All uncommitted changes of the transaction are discarded.

Only when `COMMIT` succeeds can you say the remaining changes are confirmed.

## 13. Handling Partial Data Imports with Savepoints

One of the clearest use cases is importing rows from a file or external service.

Suppose four rows arrive:

```text
row 1: source_key = new-1     account_id = 1    -> valid
row 2: source_key = dup-A     account_id = 2    -> duplicate key
row 3: source_key = bad-ref   account_id = 999  -> bad foreign key
row 4: source_key = new-2     account_id = 3    -> valid
```

Goal: import the valid rows, log errors for rejected rows, and finally commit one transaction holding the **accepted outcome**.

### 13.1. Creating the Import Table and Error Log Table

```sql
CREATE TABLE savepoint_lab.import_records (
    import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key text NOT NULL UNIQUE,
    account_id bigint NOT NULL
        REFERENCES savepoint_lab.accounts(account_id)
);

CREATE TABLE savepoint_lab.import_errors (
    error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_row_no integer NOT NULL,
    source_key text,
    sqlstate_code text NOT NULL,
    error_message text NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT statement_timestamp()
);

INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1);
```

`import_records` has a unique key on `source_key`, and `account_id` has a foreign key. `import_errors` is an illustrative error log table; real systems may also store `batch_id`, error type, redacted payloads, attempt counts, and ingestion timestamps.

### 13.2. Application-Tier Workflow

Pseudocode:

```text
BEGIN

FOR EACH input_row:
    SAVEPOINT before_row

    TRY:
        INSERT input_row
        RELEASE SAVEPOINT before_row

    CATCH recoverable_db_error:
        ROLLBACK TO SAVEPOINT before_row
        RELEASE SAVEPOINT before_row
        INSERT import_errors (... error details ...)

    CATCH unexpected_error:
        ROLLBACK entire transaction
        surface error for handling

COMMIT if policy allows partial-processing outcome
```

This is logical pseudocode, not directly executable PL/pgSQL syntax. The key is that **errors must be caught by the client**, followed by `ROLLBACK TO SAVEPOINT` before sending the next SQL command. If you try to log the error **before rolling back to the savepoint**, PostgreSQL returns `25P02` instead of inserting the log row.

### 13.3. Manual SQL Walkthrough for Small Datasets

```sql
BEGIN;

SAVEPOINT before_row_1;
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('new-1', 1);
RELEASE SAVEPOINT before_row_1;

SAVEPOINT before_row_2;
-- Run this statement alone; it will fail with unique_violation:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

After the error, run:

```sql
ROLLBACK TO SAVEPOINT before_row_2;
RELEASE SAVEPOINT before_row_2;

INSERT INTO savepoint_lab.import_errors (
    source_row_no, source_key, sqlstate_code, error_message
)
VALUES (
    2, 'dup-A', '23505', 'Duplicate source_key; skipped input row'
);
```

Continue:

```sql
SAVEPOINT before_row_3;

-- Run alone, expecting foreign_key_violation:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('bad-ref', 999);
```

Recover:

```sql
ROLLBACK TO SAVEPOINT before_row_3;
RELEASE SAVEPOINT before_row_3;

INSERT INTO savepoint_lab.import_errors (
    source_row_no, source_key, sqlstate_code, error_message
)
VALUES (
    3, 'bad-ref', '23503', 'account_id does not exist'
);

SAVEPOINT before_row_4;
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('new-2', 3);
RELEASE SAVEPOINT before_row_4;

COMMIT;
```

Outcome:

- Rows `new-1` and `new-2` are saved.
- `dup-A` keeps only the initial seed row.
- `bad-ref` is not saved.
- Two rows appear in `import_errors` for source rows 2 and 3.

**Note:** intentionally failing SQL statements must be run in an interactive client session that continues; not all script runners automatically support mid-script error recovery. For automation, use your driver's transaction API or PL/pgSQL `EXCEPTION` blocks.

## 14. Alternative: PL/pgSQL EXCEPTION and Automatic Subtransactions

In PL/pgSQL, a `BEGIN ... EXCEPTION ... END` block can handle errors for part of the work. PostgreSQL implements blocks with exception handlers via an internal subtransaction mechanism similar to savepoints: when an exception occurs, database changes inside that block are rolled back before the handler runs, while work outside the block can continue.

The convenience is that you **do not need to manually write `SAVEPOINT` and `ROLLBACK TO` inside each PL/pgSQL block**.

### 14.1. Example Row-by-Row Import with EXCEPTION

To keep this example independent of `new-1`/`new-2` above, use fresh keys:

```sql
BEGIN;

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT *
        FROM (
            VALUES
                (11, 'batch2-A'::text, 1::bigint),
                (12, 'dup-A'::text,    2::bigint),
                (13, 'batch2-B'::text, 999::bigint),
                (14, 'batch2-C'::text, 3::bigint)
        ) AS input(source_row_no, source_key, account_id)
        ORDER BY source_row_no
    LOOP
        BEGIN
            INSERT INTO savepoint_lab.import_records (
                source_key, account_id
            )
            VALUES (item.source_key, item.account_id);

        EXCEPTION
            WHEN unique_violation OR foreign_key_violation THEN
                INSERT INTO savepoint_lab.import_errors (
                    source_row_no,
                    source_key,
                    sqlstate_code,
                    error_message
                )
                VALUES (
                    item.source_row_no,
                    item.source_key,
                    SQLSTATE,
                    SQLERRM
                );
        END;
    END LOOP;
END;
$$;

SELECT source_key, account_id
FROM savepoint_lab.import_records
WHERE source_key LIKE 'batch2-%'
ORDER BY source_key;

SELECT source_row_no, source_key, sqlstate_code
FROM savepoint_lab.import_errors
WHERE source_row_no BETWEEN 11 AND 14
ORDER BY source_row_no;

ROLLBACK;
```

When initial lab data is intact:

- `batch2-A` and `batch2-C` succeed and are visible within the transaction before `ROLLBACK`.
- `dup-A` triggers `23505`; the handler logs it.
- `batch2-B` with account 999 triggers `23503`; the handler logs it.
- The final `ROLLBACK` lets you **test without persisting** exercise changes to the database.

If you replace `ROLLBACK` with `COMMIT`, the valid rows and error log entries are confirmed together in the same transaction, assuming no other errors occur.

### 14.2. SQLSTATE and SQLERRM Inside Handlers

Inside a PL/pgSQL `EXCEPTION` branch:

- `SQLSTATE` holds the current SQLSTATE error code.
- `SQLERRM` holds the error message text.

Error codes are reliable for programmatic branching, while message strings help humans investigate. Never drive logic by exact-matching English error strings because translations, settings, or versions may vary.

Common codes:

| SQLSTATE | Error Name | Example |
| --- | --- | --- |
| `23505` | `unique_violation` | Duplicate `request_key`. |
| `23503` | `foreign_key_violation` | References nonexistent account 999. |
| `23502` | `not_null_violation` | Missing required column. |
| `23514` | `check_violation` | `balance < 0` or invalid amount. |
| `22P02` | `invalid_text_representation` | Casting `'abc'` to integer. |
| `25P02` | `in_failed_sql_transaction` | Sending SQL while transaction is aborted. |
| `40001` | `serialization_failure` | Conflict under serializable isolation. |
| `40P01` | `deadlock_detected` | Deadlock between transactions. |

Not every error should be swallowed in `EXCEPTION`. Errors indicating broken invariants, transaction contention, or system failures require different policies.

### 14.3. EXCEPTION Blocks Create Rollback Boundaries

Table-free example:

```sql
DO $$
DECLARE
    value_before integer := 1;
BEGIN
    BEGIN
        value_before := 2;
        PERFORM 1 / 0;
    EXCEPTION WHEN division_by_zero THEN
        RAISE NOTICE 'Caught; variable value = %', value_before;
    END;
END;
$$;
```

When the exception is caught, **database** changes made inside the failing block are rolled back by the subtransaction; however, PL/pgSQL local variables like `value_before` retain the value assigned before the error (2 in this example).

**Distinguish PL/pgSQL variable state from database table changes.** Never look at a variable's value after an exception handler and assume a prior `UPDATE` survived.

### 14.4. Use Caution with WHEN OTHERS

```sql
-- Illustrative skeleton; do not blindly swallow every error:
-- EXCEPTION
--     WHEN OTHERS THEN
--         RAISE NOTICE 'Error occurred: %', SQLERRM;
```

An overly broad `WHEN OTHERS` can mask programming bugs or dangerous data conditions. Catch **specific error classes known to be recoverable**, log thoroughly, and let unexpected errors propagate to the layer that owns the transaction.

In PL/pgSQL, `OTHERS` also excludes certain conditions such as `QUERY_CANCELED` and `ASSERT_FAILURE` per PostgreSQL rules. Never rely on `OTHERS` to catch every system failure at all costs.

### 14.5. Do Not Issue COMMIT Inside an EXCEPTION Block

In PL/pgSQL, an `EXCEPTION` block establishes a subtransaction boundary; PostgreSQL forbids ending the transaction with `COMMIT` or `ROLLBACK` **inside that exception handler/subtransaction** as a "row-by-row commit" trick.

Controlling transactions from procedures or top-level `DO` blocks is also subject to PostgreSQL's specific call-context rules. In these examples, the outer transaction is controlled via `BEGIN`/`COMMIT`/`ROLLBACK` by the client; the handler only rolls back the sub-unit and continues.

## 15. Java/JDBC: Savepoint API and SQLSTATE

In Java applications, avoid managing savepoints by concatenating raw SQL strings when JDBC provides a dedicated API:

- `Connection.setAutoCommit(false)` for explicit transaction control.
- `Connection.setSavepoint()` or `setSavepoint(name)` to place a marker.
- `Connection.rollback(savepoint)` to revert to a marker.
- `Connection.releaseSavepoint(savepoint)` to release it.
- `Connection.commit()` or `Connection.rollback()` to end the entire transaction.

### 15.1. Example Helper for an Optional INSERT

Assuming the connection already has an open transaction managed by an outer service:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;

public final class OptionalImport {
    public static boolean tryInsert(
            Connection connection,
            String sourceKey,
            long accountId
    ) throws SQLException {
        if (connection.getAutoCommit()) {
            throw new SQLException(
                "Call inside a transaction with autoCommit=false"
            );
        }

        Savepoint savepoint = connection.setSavepoint("optional_import");

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "INSERT INTO savepoint_lab.import_records " +
                     "(source_key, account_id) VALUES (?, ?)"
                 )) {
            statement.setString(1, sourceKey);
            statement.setLong(2, accountId);
            statement.executeUpdate();

            connection.releaseSavepoint(savepoint);
            return true;

        } catch (SQLException error) {
            String sqlState = error.getSQLState();
            boolean recoverable =
                "23505".equals(sqlState) ||
                "23503".equals(sqlState);

            if (!recoverable) {
                // Caller must rollback entire transaction.
                throw error;
            }

            // Restore connection to a usable transaction state.
            connection.rollback(savepoint);
            connection.releaseSavepoint(savepoint);

            // Caller may record the rejected row if policy allows.
            return false;
        }
    }
}
```

What this code illustrates:

1. Sets a savepoint before the risky statement.
2. On success, releases it and returns `true`.
3. For the two allowed error codes, rolls back to the savepoint, releases it, and returns `false`.
4. All other errors propagate so the outer caller can handle the full transaction.

**Never swallow errors from `connection.rollback(savepoint)`.** If rolling back to the marker fails, the connection may no longer be usable; let the exception propagate so the transaction layer rolls back everything or evicts the connection.

### 15.2. The Transaction-Owning Layer Decides COMMIT

Skeleton example:

```java
connection.setAutoCommit(false);

try {
    // Mandatory operations before the optional step.
    // ...

    boolean imported = OptionalImport.tryInsert(
        connection, "new-request", 1L
    );

    if (!imported) {
        // Record partial-processing status if appropriate.
        // Never assume the optional step succeeded.
    }

    // Mandatory operations after the optional step.
    // ...

    connection.commit();
} catch (SQLException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
} finally {
    connection.setAutoCommit(true);
}
```

Here `connection` is assumed to come from a lifecycle-managed source; in real applications ensure the connection is properly closed/returned to the pool and rolled back on all error paths. Calling `setAutoCommit(true)` while a transaction is still active can affect the transaction depending on the driver; hence the `try/catch` block must ensure the transaction finishes before returning the connection to the pool.

Key design principle: **`tryInsert` never calls `commit()` itself**. The service-level transaction makes the final decision on whether all outcomes are confirmed.

### 15.3. Never Catch Every SQLException and Continue

Anti-pattern:

```java
// Do NOT do this:
// try {
//     insertSomething();
// } catch (SQLException ignored) {
//     // ignored without rolling back savepoint
// }
// insertNextSomething(); // likely hits SQLSTATE 25P02
```

Once PostgreSQL marks a transaction failed, catching the exception in Java **does not restore the server-side transaction state**. You must call `rollback(savepoint)` or `rollback()`.

### 15.4. ORMs and Frameworks Managing Nested Transactions

Some frameworks implement `NESTED` transactions on top of JDBC savepoints; others only support propagation that opens a separate transaction on a new connection, or disallow nested semantics in certain contexts.

Never assume an annotation named `NESTED` behaves identically across all databases and transaction managers. Specifically check:

- Does the transaction manager support JDBC savepoints?
- Is the same connection reused, or is a new connection opened?
- Does the framework roll back to the savepoint or mark the outer transaction `rollback-only`?
- Was the exception handled at the right layer?
- Could an outer layer release the savepoint prematurely?

In particular, a framework may mark the outer transaction **rollback-only** on an error even if lower-level code caught it; in that case, the final `COMMIT` still fails or rolls back. Understand your transaction manager's semantics, not just raw SQL.

## 16. Savepoints and INSERT ... ON CONFLICT

If a duplicate-key error is a **normal, frequently expected case**, creating a savepoint per row can be unnecessarily complex and expensive.

PostgreSQL supports handling unique conflicts directly via `INSERT ... ON CONFLICT`.

### 16.1. Skipping Duplicates by Unique Key

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1)
ON CONFLICT (source_key) DO NOTHING;
```

If `source_key='dup-A'` already exists, PostgreSQL skips the conflicting row and **does not abort the transaction** for that handled unique conflict.

No separate savepoint is needed for this conflict case.

### 16.2. When ON CONFLICT Does Not Replace SAVEPOINT

`ON CONFLICT` handles eligible unique/exclusion conflicts matched by its syntax. It **does not handle other errors** such as:

- Foreign key violations.
- Check constraint violations.
- Not-null violations.
- Invalid type casts.
- Errors raised by triggers or other functions.

If an ingestion pipeline must catch and log multiple error categories per row and keep going, savepoints or exception handlers still have a role.

### 16.3. DO UPDATE Cases

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2)
ON CONFLICT (source_key)
DO UPDATE SET account_id = EXCLUDED.account_id;
```

This statement intentionally **updates the existing row** per upsert semantics rather than skipping duplicates. Evaluate whether overwriting `account_id` is business-valid. `DO UPDATE` can still fail on other errors and does not bypass every constraint.

To keep lab data predictable, do not run this updating upsert example unless you specifically intend to test that effect.

## 17. When to Choose Savepoints, ON CONFLICT, or Staging?

| Scenario | Typically Appropriate Approach |
| --- | --- |
| Simply ignore `INSERT` duplicate unique keys | `INSERT ... ON CONFLICT DO NOTHING`. |
| Update existing row on unique key conflict per clear rule | `ON CONFLICT DO UPDATE`. |
| Optional step may fail and all its DML must be undone | `SAVEPOINT` / `ROLLBACK TO` or PL/pgSQL `EXCEPTION`. |
| Bulk import of many rows with diverse error types | Staging table, set-based validation, and inserting valid rows; combine with savepoints if needed. |
| Error makes transaction untrustworthy or breaks key invariant | Roll back the entire transaction and handle at the service layer. |
| Deadlock / serialization failure | Retry the **entire transaction** per policy, rather than skipping the failing step. |
| Secondary action must commit even if main transaction rolls back | Separate transaction, outbox, or workflow design; savepoints **do not** commit independently. |

A high-throughput pipeline importing millions of rows should generally favor **set-based** processing with staging tables, constraints, and idempotency rather than one savepoint per row; measure on realistic workloads.

## 18. Partial Error Handling Does Not Mean Ignoring Business Errors

Never see `23505` and assume every key collision is benign. A unique violation could mean:

- Client retried an identical request that already succeeded → handle idempotently.
- Two genuinely distinct requests collided on the same request key → serious logic bug.
- A broken ID generator → stop and investigate.

Similarly, `23503` could mean:

- A staging row references a code not yet onboarded → route to a pending/review queue.
- A fund transfer references a nonexistent account → never treat that financial transaction as successful.

**Selection rule:** roll back to a savepoint and continue only when business policy explicitly permits recovering from that error class and all invariants remain intact.

### 18.1. Reporting Partial-Processing Outcomes

An import API might return:

```json
{
  "batchId": "batch-2026-11-14-A",
  "received": 4,
  "accepted": 2,
  "rejected": 2,
  "rejections": [
    {"row": 2, "code": "DUPLICATE_SOURCE_KEY"},
    {"row": 3, "code": "UNKNOWN_ACCOUNT"}
  ]
}
```

This is an illustrative response payload, not auto-generated SQL output. Be explicit about **whether the entire batch actually committed**, because "accepted rows" before commit can still roll back if a later mandatory step fails.

### 18.2. Never Send Success Notifications Before Commit

If an application sends an "import succeeded" email or webhook right after releasing a savepoint, and the outer transaction later rolls back, the recipient receives a false notification.

For external events, use a transactional outbox or emit only after commit succeeds. Savepoints cannot roll back sent emails or HTTP requests already processed by a partner.

## 19. Side Effects That Do Not Roll Back Like DML

Most transactional table changes in PostgreSQL roll back with transactions and savepoints. However, not **every observable effect** reverts.

### 19.1. Sequences and Identity Columns Do Not Roll Back Allocated Numbers

`nextval(...)` advances sequences, and allocated values **do not revert** when a transaction or savepoint rolls back.

That is why IDs in a table using `GENERATED ... AS IDENTITY` can develop **gaps** after a failed INSERT.

Illustrative example using the identity-backed `transfers` table:

```sql
BEGIN;
SAVEPOINT before_probe;

INSERT INTO savepoint_lab.transfers (
    request_key, from_account_id, to_account_id, amount
)
VALUES ('temporary-probe', 1, 2, 1.00)
RETURNING transfer_id;

ROLLBACK TO SAVEPOINT before_probe;
RELEASE SAVEPOINT before_probe;

ROLLBACK;
```

The `temporary-probe` row rolled back. Yet the identity value consumed during INSERT can leave the next ID **non-contiguous**.

**Never use contiguous IDs to prove a transaction or savepoint never encountered errors.** Sequences prioritize concurrent throughput and do not promise gap-free numbering.

### 19.2. Effects Outside the Database

Actions such as sending HTTP requests, emails, writing external files, or calling remote services from the application **are not rolled back by PostgreSQL** on `ROLLBACK TO SAVEPOINT`.

Never place an external side effect between SQL statements and expect a savepoint to provide cross-system atomicity. For multi-system consistency, design events/outboxes, idempotency, and workflow compensation.

### 19.3. Locks Acquired After a Savepoint

When rolling back to a savepoint, PostgreSQL generally releases locks acquired after the savepoint per subtransaction rules, while locks held prior to the savepoint remain until the outer transaction ends.

Example:

```text
BEGIN
  |
  +-- UPDATE account 1       -> may hold lock from before savepoint
  |
  +-- SAVEPOINT s
  |
  +-- UPDATE account 2       -> acquires lock after savepoint
  |
  +-- ROLLBACK TO s          -> discards account 2 change
  |
  +-- transaction still open -> account 1 still uncommitted
```

Savepoints are not a tool to clear all transaction locks. **Long-running transactions still cause blocking**, even after many partial rollbacks.

## 20. Deferred Constraints: Errors Can Surface Late

Certain PostgreSQL constraints can be declared `DEFERRABLE`, postponing validation until later in the transaction. This directly affects where you place savepoints and where errors surface.

### 20.1. Creating a Deferrable Foreign Key

```sql
CREATE TABLE savepoint_lab.parent_keys (
    parent_id bigint PRIMARY KEY
);

CREATE TABLE savepoint_lab.child_keys (
    child_id bigint PRIMARY KEY,
    parent_id bigint NOT NULL,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES savepoint_lab.parent_keys(parent_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

This foreign key can be checked at transaction end instead of immediately on every INSERT, depending on the active constraint mode.

### 20.2. Errors May Not Appear at INSERT Time

```sql
BEGIN;

SAVEPOINT before_child;

INSERT INTO savepoint_lab.child_keys (child_id, parent_id)
VALUES (1, 999);

-- If the constraint is deferred, INSERT may not error yet.
```

Suppose parent 999 does not exist; PostgreSQL **temporarily accepts the insert inside the transaction** because the foreign key is deferred.

If you `RELEASE SAVEPOINT before_child;` and proceed to `COMMIT`, the constraint violation may only surface at commit time. Once `COMMIT` fails, **it is too late to roll back to a savepoint as if the transaction were still alive**.

### 20.3. Forcing Validation Before Release

To ensure errors surface while a savepoint can still recover, use `SET CONSTRAINTS ... IMMEDIATE` inside the transaction:

```sql
SET CONSTRAINTS ALL IMMEDIATE;
```

With the child row pointing to missing parent 999, this raises `23503`. While `before_child` is still active, recover with:

```sql
ROLLBACK TO SAVEPOINT before_child;
RELEASE SAVEPOINT before_child;
COMMIT;
```

Because `SET CONSTRAINTS ALL IMMEDIATE` affects all eligible deferrable constraints broadly, in real code prefer naming the specific constraint whenever possible and understand its impact on other tables in the transaction.

**Note:** switching constraint checking mode to immediate is itself transactional. If `SET CONSTRAINTS` fails, the prior mode is preserved per PostgreSQL rules, and rolling back to the savepoint also restores changes within that savepoint scope.

### 20.4. Not Every Constraint Can Be Deferred

PostgreSQL does not support deferring all constraint types equally. For instance, `CHECK` and `NOT NULL` are checked immediately; `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, and `EXCLUDE` support deferral when defined appropriately, with certain restrictions around `ON CONFLICT`.

Therefore, do not assume every error waits until `COMMIT` or every error happens right at `INSERT`. Read the actual table and constraint DDL.

## 21. Handling Deadlocks or Serialization Failures

An expected input error like a duplicate `source_key` differs fundamentally from **concurrency coordination failures between competing transactions**.

Two such codes:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

In these cases, the standard solution is **rolling back and retrying the entire transaction**, not rolling back to a savepoint and skipping the failing statement.

### 21.1. Why Retry the Whole Transaction?

At `SERIALIZABLE` isolation, business decisions before the error may rest on reads/observations incompatible with concurrent execution history. To preserve serializable semantics, you must re-execute **the transaction's decision logic** in a fresh transaction with a new snapshot, not just replay the final SQL statement.

For deadlocks, PostgreSQL deliberately aborts one transaction to break the wait cycle; the application should perform bounded retries with backoff.

### 21.2. Service-Layer Retry Pattern

```text
for attempt = 1..maxRetries:
    BEGIN transaction
    try:
        read data
        validate business rules
        write changes
        COMMIT
        return SUCCESS
    catch SQLSTATE 40001 or 40P01:
        ROLLBACK if connection is still usable
        wait with backoff and jitter
        retry ENTIRE logic in a new transaction
    catch non-retryable error:
        ROLLBACK
        report failure
```

This is application-layer pseudocode, not complete PostgreSQL syntax. Retry count, backoff, idempotency, and event emission must match the workload.

**Important:** never blindly retry transactions that already triggered external side effects without idempotency keys. Full-transaction database retries still require protection against double emails or double charges.

### 21.3. Connection Failures

If the connection drops near the `COMMIT` boundary, the application may not know whether the server committed or not. You cannot simply issue `ROLLBACK TO` on the dead connection.

Systems need request/idempotency keys and post-reconnect status lookup. Savepoints do not resolve **uncertain commit outcomes** across connection loss.

## 22. Timeouts and Statement Cancellations

PostgreSQL scenarios include:

- `statement_timeout`: a statement ran too long and was canceled.
- `lock_timeout`: waiting for a lock exceeded the limit.
- User/client query cancellation.

These raise statement errors and put the current transaction into the failed state unless caught inside an appropriate boundary such as a savepoint or exception block.

Should you roll back to a savepoint and keep going?

**It depends on the goal and health of the transaction.** If it was an isolated optional step and the connection remains healthy, some failures may be recovered by design. If a timeout signals system overload or a mandatory step failed, abort the transaction and retry or reject according to policy.

Never equate "a SQL error can be rolled back to a savepoint" with "the application should ignore failures and push ahead."

## 23. Verifying Savepoints with Data Changes

To contrast `ROLLBACK TO` with `ROLLBACK`, use a small test table:

```sql
CREATE TABLE savepoint_lab.test_marks (
    mark_id integer PRIMARY KEY,
    note text NOT NULL
);
```

Run:

```sql
BEGIN;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (1, 'Before marker');

SAVEPOINT s1;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (2, 'After marker');

ROLLBACK TO SAVEPOINT s1;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (3, 'After rollback-to');

SELECT mark_id, note
FROM savepoint_lab.test_marks
ORDER BY mark_id;

ROLLBACK;
```

Inside the transaction right before the final `ROLLBACK`, the result is:

| mark_id | note |
| ---: | --- |
| 1 | Before marker |
| 3 | After rollback-to |

Mark 2 is absent. After the final `ROLLBACK`, neither mark 1 nor mark 3 remains in the table (assuming the table started empty).

### 23.1. Testing RELEASE Followed by ROLLBACK

```sql
BEGIN;

SAVEPOINT s;

INSERT INTO savepoint_lab.test_marks (mark_id, note)
VALUES (4, 'Released, not committed');

RELEASE SAVEPOINT s;

ROLLBACK;
```

Mark 4 **does not exist after rollback**. This directly disproves the misconception that "releasing a savepoint commits it separately."

### 23.2. Testing Repeated Rollback to the Same Marker

```sql
BEGIN;

SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (5, 'First try');
ROLLBACK TO SAVEPOINT s;

INSERT INTO savepoint_lab.test_marks VALUES (6, 'Second try');
ROLLBACK TO SAVEPOINT s;

SELECT * FROM savepoint_lab.test_marks
WHERE mark_id IN (5, 6);

RELEASE SAVEPOINT s;
ROLLBACK;
```

Neither mark 5 nor 6 appears in `SELECT` because both rollbacks returned to the same marker `s`.

## 24. Partial Rollback and Business Consistency

A transaction might include steps:

```text
A. Save order               (mandatory)
B. Reserve inventory        (mandatory)
C. Write secondary audit    (optional)
D. Create internal note     (optional)
E. Confirm order            (mandatory)
```

If `B` fails due to insufficient stock, you must **not** roll back only B and commit A and E as if the order were valid.

Conversely, if `C` only inserts a non-critical statistics row and policy allows failing without affecting the order, place a savepoint before C, roll back to it on error, and continue with D/E.

### 24.1. Step Criticality

| Step | Skippable on Error? | Handling |
| --- | --- | --- |
| Verify sufficient funds before transfer | No | Roll back entire transaction if mandatory condition fails. |
| Reserve inventory on sale | Usually no | Roll back entire order-creation workflow on failure. |
| Write optional analytics field | Possibly | Savepoint before step, roll back to it, and log failure. |
| Import independent row in partial-success batch | Possibly | Per-row savepoint or PL/pgSQL exception. |
| Send external email outside database | Cannot roll back via savepoint | Outbox / post-commit workflow / idempotency. |

**Transaction correctness is not merely the absence of SQL errors.** You must preserve business invariants across whatever outcome you commit.

### 24.2. Can Every Row Always Be Treated Independently?

Suppose input rows have dependencies:

```text
Row 1: create customer
Row 2: create order for row 1's customer
Row 3: create order_item for row 2's order
```

If row 2 fails while row 3 proceeds, a naive "skip only the failing row" policy breaks relational dependencies.

Align rollback scope with **independent business units**: an order and its `order_items` likely form one unit that succeeds or aborts together, rather than wrapping every single SQL statement in its own savepoint.

## 25. Savepoints in Large Batches: Cost and Operations

Creating many savepoints/subtransactions carries management overhead. At very high counts, they can increase transaction-management overhead and degrade throughput.

### 25.1. Is One Savepoint per Row Always Good?

No. When importing millions of rows, "one row → SAVEPOINT → INSERT → RELEASE" can be slow and complex.

Consider:

1. Load raw data into a staging table via `COPY` or batched inserts per policy.
2. Validate data with set-based queries to detect formatting and reference errors.
3. Separate valid rows, using `ON CONFLICT` strategies where collisions are expected.
4. Log rejected rows.
5. Insert valid rows into target tables within time- and size-bounded transactions.

Savepoints remain valuable for small steps or clear business boundaries, yet **do not replace optimized bulk-loading strategies**.

### 25.2. Long-Running Transactions Have Their Own Costs

Even with partial rollbacks, the outer transaction still holds locks and affects MVCC/vacuum in practice. A multi-hour batch using tens of thousands of savepoints is rarely a good default architecture.

If business rules allow chunked commits, consider splitting into smaller transactions, each with idempotency and retry support. Trade-off: the overall batch is no longer atomic as one unit; that is a **change in business contract** that must be explicitly approved.

### 25.3. Structured Logging

A partial-error handling log should capture:

- Batch/request ID.
- Rejected unit of work.
- SQLSTATE and business error code.
- Retry attempt count.
- Final outer transaction commit status.
- Necessary context without leaking secrets or unnecessary sensitive data.

Never log just a generic `ERROR` without knowing which steps rolled back and which eventually committed.

## 26. SAVEPOINT and Isolation Levels

PostgreSQL supports isolation levels including `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. Savepoints **do not change a transaction's isolation level**.

### 26.1. Snapshots and Rollback-To

`ROLLBACK TO SAVEPOINT` undoes changes after the marker, but it does not turn a `REPEATABLE READ` transaction into a brand-new transaction with a fresh snapshot.

If a read observed data under the active snapshot, rolling back to a savepoint does not mean earlier decisions were re-evaluated against the latest committed database state.

### 26.2. Serializable and Retry Risk

Under `SERIALIZABLE`, when PostgreSQL raises `40001`, the application normally must restart the entire transaction. Savepoints help structure operations, yet cannot replace business-logic retries under a fresh transaction.

### 26.3. Visibility to Other Sessions

After `ROLLBACK TO` and before `COMMIT`, remaining changes made prior to the savepoint are still **uncommitted**. Other sessions do not see them as committed or durable.

Likewise, `RELEASE SAVEPOINT` does not change visibility to other sessions. Confirmation visibility is still governed solely by the outer transaction.

## 27. Practical Questions When Designing with Savepoints

**Can I create a savepoint before every UPDATE?** You can if appropriate, though it is usually unnecessary. Place savepoints at **independently abortable business step** boundaries rather than mechanically before every SQL command.

**Can a savepoint survive across two connection-pool borrows?** Not by default. Savepoints belong to a transaction on one connection; if a later call receives a different connection or the transaction ended, the old marker is gone.

**Can you partially commit after RELEASE?** No. RELEASE only removes the rollback marker; the outer transaction can still roll back everything.

**Do I need to recreate a savepoint after ROLLBACK TO?** Not required; the target marker remains alive. Release it once you finish deciding.

**On a unique constraint error, should I always roll back to savepoint and continue?** Only if business policy permits skipping or handling that step separately; if it violates a core invariant, roll back the whole transaction.

**If COMMIT raises a deferred constraint error, can I roll back to a savepoint?** Usually at that point the transaction has already failed/rolled back because `COMMIT` failed; to catch errors while partial recovery is still possible, validate early—for example via `SET CONSTRAINTS ... IMMEDIATE` while the savepoint still exists.

**Does an error inside a transaction auto-commit earlier DML?** No. A SQL error is not a commit; prior changes remain governed by rollback/recovery and outer transaction commit.

**Can ROLLBACK TO return allocated identity numbers?** No. Sequences/identities can still leave gaps.

**Why does JDBC still hit 25P02 after catching SQLException?** Because catching an exception in Java does not roll back the failed transaction state on the PostgreSQL server.

**Should HTTP/email calls run inside a savepoint block?** Savepoints only manage transactional changes inside PostgreSQL; they cannot roll back effects already executed in external systems.

## 28. Common Mistakes

### Mistake 1. Creating SAVEPOINT Outside a Transaction

Without an active transaction block, markers cannot persist as expected. Start an explicit transaction or use the driver's transaction API.

### Mistake 2. Forgetting Rollback-To After a Failing SQL Statement

The application catches the error and keeps sending `SELECT`/`INSERT`, hitting `25P02`. Roll back to a valid savepoint or roll back the entire transaction.

### Mistake 3. Using RELEASE to Fix an Aborted State

`RELEASE` does not recover a failed transaction. Run `ROLLBACK TO SAVEPOINT` first.

### Mistake 4. Thinking RELEASE Means Commit

A final `ROLLBACK` still discards released changes. Savepoints have no independent commit.

### Mistake 5. Rolling Back to an Older Marker and Trying to Use a Newer One

`ROLLBACK TO s1` destroys any savepoints created after `s1`. Track which markers remain alive when nesting.

### Mistake 6. Confusion from Reused Savepoint Names

PostgreSQL retains multiple same-named markers and targets the newest one. Use clear naming and ownership to avoid acting on an unexpected marker.

### Mistake 7. Swallowing All SQL Exceptions

Expected data errors differ from deadlocks, serialization failures, and system crashes. Only handle explicitly permitted recoverable codes rather than catching everything.

### Mistake 8. Treating SQLSTATE 25P02 as the Root Cause

Find the first failing statement; `25P02` is a symptom of an already aborted transaction.

### Mistake 9. Logging Errors to a Table Before Rolling Back to Savepoint

In a failed transaction, the log INSERT itself is rejected. Roll back to the savepoint first, then INSERT the log or use a PL/pgSQL exception handler.

### Mistake 10. Trying to Keep Valid Rows from a Failing Multi-Row INSERT

A failing SQL statement does not split itself into per-row sub-statements. Use set-based staging/validation, `ON CONFLICT`, or per-row handling when needed.

### Mistake 11. Using Savepoints to Fix Missing Transaction Locking

If two clients transfer money concurrently, you need proper locking, conditional updates, and isolation. Savepoints do not replace concurrency control.

### Mistake 12. Ignoring Deferred Constraints Until Commit

Errors may surface only at `COMMIT` when savepoints are gone. Understand constraint timing and force checks before releasing if partial recovery is required.

### Mistake 13. Assuming Sequences Roll Back with Rows

`nextval`/identity can advance even when rows roll back, leaving ID gaps.

### Mistake 14. Creating Unbounded Savepoints in Large Batches

Overhead can grow significantly. Consider staging, bulk loading, set-based validation, or chunking.

### Mistake 15. Assuming Clients Keep Running After a SQL Error

Script runners may halt, and frameworks may auto-rollback. Controlled error-testing requires managing client connection and error-stop modes.

### Mistake 16. Creating the Savepoint After the Risky Operation

If the error occurs **before the savepoint was created**, you cannot roll back to a marker placed afterward. Place savepoints **before** the risky unit.

### Mistake 17. Rolling Back to Savepoint Without Preserving Invariants

Undoing half a transfer while keeping the other half before the savepoint corrupts balances. Place boundaries around operations that **must succeed together**.

### Mistake 18. Ignoring Driver rollback(savepoint) Errors

If savepoint recovery fails, do not continue as if the transaction is healthy. Abort the whole transaction and report the failure.

### Mistake 19. Mixing Core Transactions with External Side Effects

Rollback does not cancel emails, HTTP requests, or external payment calls. Use idempotency, outboxes, and compensation rules.

### Mistake 20. Treating Savepoints as a Substitute for Full-Transaction Retries

For `40001`/`40P01`, you normally must roll back and retry the entire transaction. Concurrency conflicts are not skippable row-import errors.

## 29. Hands-On Exercises

The following exercises use the `savepoint_lab` schema from Sections 4, 13, and 23. Run on a clean lab schema or change IDs/keys if prior write examples remain. For error-triggering exercises, run statements one by one in **the same interactive session** without letting the client abort or skip blindly.

### Exercise 1. Placing a Savepoint

Open a transaction, create marker `before_test`, run `SELECT 1`, release the marker, and roll back the transaction. Explain why nothing is committed.

### Exercise 2. Partial Rollback

Insert mark 11 before a savepoint; insert mark 12 after the savepoint; roll back to the marker; insert mark 13; select the marks and then roll back the whole transaction. Which marks appear in the SELECT before the final rollback?

### Exercise 3. Unique-Key Error Step

In `import_records`, `source_key='dup-A'` already exists. Place a savepoint before inserting this key again, observe `23505`, roll back to the marker, and run a valid SELECT.

### Exercise 4. Without a Savepoint

Open a transaction, perform an INSERT with a duplicate unique key without a savepoint, and then try a SELECT. Explain `25P02` and how to recover.

### Exercise 5. RELEASE Is Not COMMIT

Insert mark 21 after a savepoint, release it, and roll back the outer transaction. Check for mark 21 afterward; why is it gone?

### Exercise 6. Reusing a Savepoint

Create `s`, insert mark 31, roll back to `s`, insert mark 32, and roll back to `s` again. Does savepoint `s` still exist, and which marks are kept?

### Exercise 7. Nested Savepoints

Create `s1`, insert mark 41; create `s2`, insert mark 42; create `s3`, insert mark 43; roll back to `s2`. Which marks remain? Which savepoints were dropped?

### Exercise 8. Duplicate Marker Names

Create two savepoints both named `checkpoint`. Which marker does a rollback-to target? What happens after releasing the newest marker?

### Exercise 9. Row-by-Row Import Handling

Import four rows `new-X`, `dup-A`, `bad-ref`, and `new-Y`, with account IDs 1, 2, 999, and 3 respectively. Use per-row savepoints or PL/pgSQL exceptions. Which rows are accepted?

### Exercise 10. Classifying SQLSTATE Codes

Match `23505`, `23503`, `23514`, `25P02`, `40001`, and `40P01` to their error names and suggest initial handling.

### Exercise 11. ON CONFLICT

Write `INSERT ... ON CONFLICT (source_key) DO NOTHING` to skip `dup-A`. Is rollback-to needed here? Does this automatically handle foreign key 999?

### Exercise 12. PL/pgSQL Variables and Data Rollback

Inside a `BEGIN ... EXCEPTION` block, assign variable `x := 2` and then trigger division by zero. After the handler runs, what value does `x` hold? Is DML performed on tables before the error inside that same block kept or discarded?

### Exercise 13. JDBC Savepoints

Write the sequence `setAutoCommit(false)` → `setSavepoint()` → INSERT → `rollback(savepoint)` on expected error → `releaseSavepoint()` → `commit()`. Who must decide the final commit?

### Exercise 14. Deferred Foreign Key

In `child_keys` with a deferred FK, insert a child pointing to a nonexistent parent after a savepoint. Why might the INSERT not raise an error immediately? How do you detect the error before releasing?

### Exercise 15. Sequences and Identity

Inside a savepoint, insert a row using an identity column and then roll back to the savepoint. Should you expect the next INSERT to reuse the exact rolled-back ID?

### Exercise 16. Choosing the Right Rollback Scope

An order and `order_item` must be saved together, while a secondary statistics insert is allowed to fail. Before which operation should you place the savepoint? What should happen if `order_item` fails?

### Exercise 17. Serializable Retry

A `SERIALIZABLE` transaction reports SQLSTATE `40001` after several reads and writes. Should you roll back to a savepoint and continue with the previously read data?

### Exercise 18. Reconciliation After Partial Rollback

After the transfer example in Section 5, predict the three account balances, total balance, and list of committed request keys.

### Exercise 19. Transactions Across Connections

Why can't you create a savepoint on Connection A and roll back to that savepoint on Connection B from a pool?

### Exercise 20. Safe Error Logging

An application wants to write to `import_errors` right after an INSERT fails with a foreign key error. Why must it roll back to the savepoint before logging? If logging the error also fails, what should the system do?

## 30. Suggested Solutions

### Answer 1

```sql
BEGIN;
SAVEPOINT before_test;
SELECT 1;
RELEASE SAVEPOINT before_test;
ROLLBACK;
```

`RELEASE` only frees the marker; it does not commit data.

### Answer 2

```sql
BEGIN;

INSERT INTO savepoint_lab.test_marks VALUES (11, 'Before');

SAVEPOINT before_optional;
INSERT INTO savepoint_lab.test_marks VALUES (12, 'Discarded');
ROLLBACK TO SAVEPOINT before_optional;

INSERT INTO savepoint_lab.test_marks VALUES (13, 'After marker');

SELECT mark_id, note
FROM savepoint_lab.test_marks
WHERE mark_id IN (11, 12, 13)
ORDER BY mark_id;

ROLLBACK;
```

Before the final rollback, the result contains marks 11 and 13, without mark 12. After the final rollback, assuming they did not exist beforehand, none remain.

### Answer 3

```sql
BEGIN;
SAVEPOINT before_duplicate;

-- Run alone to observe error 23505:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

After receiving the error:

```sql
ROLLBACK TO SAVEPOINT before_duplicate;
SELECT COUNT(*) FROM savepoint_lab.import_records;
RELEASE SAVEPOINT before_duplicate;
ROLLBACK;
```

SELECT works again because the transaction was restored to the savepoint.

### Answer 4

```sql
BEGIN;
-- Fails with 23505 if dup-A already exists:
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 2);
```

After the error, SELECT cannot proceed normally and returns `25P02`. Without a savepoint to roll back to, call `ROLLBACK;` to end the transaction.

### Answer 5

```sql
BEGIN;
SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (21, 'Temporary');
RELEASE SAVEPOINT s;
ROLLBACK;
```

Mark 21 is discarded because releasing is not committing.

### Answer 6

```sql
BEGIN;
SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (31, 'First');
ROLLBACK TO SAVEPOINT s;
INSERT INTO savepoint_lab.test_marks VALUES (32, 'Second');
ROLLBACK TO SAVEPOINT s;
RELEASE SAVEPOINT s;
ROLLBACK;
```

`s` remains alive after each `ROLLBACK TO` until released; both marks 31 and 32 are discarded.

### Answer 7

```sql
BEGIN;
SAVEPOINT s1;
INSERT INTO savepoint_lab.test_marks VALUES (41, 'A');
SAVEPOINT s2;
INSERT INTO savepoint_lab.test_marks VALUES (42, 'B');
SAVEPOINT s3;
INSERT INTO savepoint_lab.test_marks VALUES (43, 'C');
ROLLBACK TO SAVEPOINT s2;
SELECT mark_id FROM savepoint_lab.test_marks
WHERE mark_id IN (41,42,43);
ROLLBACK;
```

Only mark 41 remains before the outer rollback; `s3` was dropped, while `s1` and `s2` remain.

### Answer 8

PostgreSQL targets the newest `checkpoint`; once the newer marker is released, the older one becomes accessible again. Avoid relying on duplicate names in multi-layered code.

### Answer 9

Valid rows `new-X` and `new-Y` are accepted if not already present; `dup-A` is rejected for uniqueness, `bad-ref` for foreign key. The transaction still must commit at the end for accepted rows to persist durably.

### Answer 10

| SQLSTATE | Meaning | Suggested Response |
| --- | --- | --- |
| `23505` | Unique violation | If genuinely expected, handle via `ON CONFLICT` or rollback-to. |
| `23503` | Foreign key violation | Inspect missing relation and policy; possibly reject staging row. |
| `23514` | Check violation | Data violates invariant; normally should not be blindly skipped. |
| `25P02` | Transaction already aborted | Find root error, roll back to savepoint or roll back entire transaction. |
| `40001` | Serialization failure | Retry entire transaction per policy. |
| `40P01` | Deadlock detected | Retry entire transaction per policy. |

### Answer 11

```sql
INSERT INTO savepoint_lab.import_records (source_key, account_id)
VALUES ('dup-A', 1)
ON CONFLICT (source_key) DO NOTHING;
```

The expected unique conflict is handled directly, so no savepoint is needed just for that case. This does not automatically handle a foreign key error on a row referencing 999.

### Answer 12

```sql
DO $$
DECLARE
    x integer := 1;
BEGIN
    BEGIN
        x := 2;
        PERFORM 1 / 0;
    EXCEPTION WHEN division_by_zero THEN
        RAISE NOTICE 'x=%', x;
    END;
END;
$$;
```

The variable holds 2; database changes made inside the failing block rolled back via the subtransaction. Distinguish variable state from row state.

### Answer 13

```java
connection.setAutoCommit(false);
Savepoint savepoint = connection.setSavepoint();

try {
    // Execute optional SQL with this connection.
    connection.releaseSavepoint(savepoint);
} catch (SQLException error) {
    connection.rollback(savepoint);
    connection.releaseSavepoint(savepoint);
    // Continue only if this error is explicitly recoverable.
}

// The outer service owns connection.commit() or connection.rollback().
```

This is an API outline; production code must classify errors and roll back the entire transaction on unexpected errors, as shown in the full example in Section 15.

### Answer 14

A `DEFERRABLE INITIALLY DEFERRED` FK can defer validation until later. Call `SET CONSTRAINTS ALL IMMEDIATE` while the savepoint still exists to force checking, and `ROLLBACK TO SAVEPOINT` if it errors.

### Answer 15

No. Sequences/identities are not guaranteed to revert after rollback-to, so IDs may skip forward.

### Answer 16

Order and `order_item` form a mandatory group and must roll back the entire unit of work if either fails. A savepoint can wrap the **optional statistics** step; if statistics fail, roll back to that savepoint and continue when policy permits.

### Answer 17

No. For `40001`, retry the entire transaction and re-read data / recompute decisions in a fresh transaction; never rely on stale reads after a savepoint.

### Answer 18

Committed balances: account 1 = 900.00, account 2 = 550.00, account 3 = 150.00; total = 1600.00. Only `transfer-A` and `transfer-B` are persisted.

### Answer 19

Savepoints belong to Connection A's transaction, not a global object on the database or JVM. Connection B has a different transaction and cannot roll back to A's marker.

### Answer 20

You must `ROLLBACK TO SAVEPOINT` first so the transaction exits the aborted state before inserting into `import_errors`. If logging the error also fails, follow the outer transaction's policy: usually roll back everything or log through a safe out-of-band mechanism outside the transaction. Never silently pretend the error log succeeded.

## 31. Checklist Before Using SAVEPOINT in Applications

1. **Business boundary:** is the rolled-back step genuinely independent of the succeeded portion?
2. **Transaction scope:** are all statements guaranteed to share the same connection and transaction?
3. **Marker placed before error:** was the savepoint created before every risky statement?
4. **Correct recovery order:** on a SQL error, roll back to the savepoint before issuing any subsequent DML.
5. **SQLSTATE:** are allowed partial-recovery error codes explicitly identified?
6. **Invariants:** after rollback-to, do balances, inventory, and relational invariants still hold?
7. **Nested markers:** could rolling back to an older marker wipe out markers needed by another layer?
8. **Release vs. commit:** which code layer owns committing the outer transaction?
9. **Constraint timing:** can deferred errors surface only at COMMIT?
10. **Sequences/gaps:** have you avoided assuming contiguous IDs or rollback of external side effects?
11. **Concurrency:** do deadlocks and serialization failures have a full-transaction retry path?
12. **Connection pool:** does code return connections to the pool only after properly ending/rolling back the transaction?
13. **Observability:** do logs record batch ID, row ID, SQLSTATE, and final commit status?
14. **Bulk performance:** is per-row savepoint needed, or are staging/`ON CONFLICT` better?
15. **Client behavior:** does your GUI, psql, or framework auto-stop or auto-rollback on error?
16. **Testing:** have you tested success, expected errors, unexpected errors, and commit-time failures?

## 32. Summary

In PostgreSQL, `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, and `RELEASE SAVEPOINT` let applications **handle the failure of a single step without necessarily aborting the entire transaction**:

- **`SAVEPOINT s`** creates a marker before a group of operations that may need recovery.
- **`ROLLBACK TO SAVEPOINT s`** undoes rollbackable changes after the marker, recovers the transaction from an error within scope, and **keeps marker `s` alive for reuse**.
- **`RELEASE SAVEPOINT s`** frees the marker once individual rollback is no longer needed; it **does not commit**.
- Markers can be nested; rolling back to or releasing an older marker discards markers created after it. PostgreSQL permits duplicate marker names, though they require care.
- A normal SQL error inside a transaction causes subsequent SQL statements to return **`25P02`** until the transaction is recovered or rolled back. Catching an exception in Java alone is not enough.
- **PL/pgSQL `EXCEPTION`** uses subtransactions to handle block-scoped errors; **JDBC `Savepoint`** provides the corresponding application-layer API.
- **`INSERT ... ON CONFLICT`** can be simpler for expected duplicate unique keys; set-based staging and validation fit large batches.
- Savepoints do not roll back sequences, emails, or HTTP calls, do not replace concurrency control, and do not enable independent partial commits.
- For **`40001`/`40P01`**, you generally must retry the entire transaction; for deferred constraints, understand when errors are detected prior to `COMMIT`.

The essential design question is: **"If this step fails and I roll back to the savepoint, is the remaining work still business-valid and safe to commit?"** If you cannot answer yes with certainty, rolling back the entire transaction is usually the safer choice over keeping partial data.
