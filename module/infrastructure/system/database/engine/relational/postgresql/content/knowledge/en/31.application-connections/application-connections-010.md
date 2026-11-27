# SQLSTATE Classification, Retryable Errors, and Idempotency in PostgreSQL

A Java application sends a fund transfer or order creation command to PostgreSQL. The SQL statement can fail because of invalid input data, a missing foreign key, two transactions deadlocking, a conflict at the `SERIALIZABLE` level, connection exhaustion, or a server restart. Those failures **cannot all be handled with a single “catch exception and rerun” rule**.

For example:

```text
23505  unique_violation         → usually duplicate data / idempotency key
23503  foreign_key_violation    → invalid referenced data
40001  serialization_failure    → retry the entire transaction
40P01  deadlock_detected        → can retry the entire transaction
55P03  lock_not_available       → can retry if the contract allows
57014  query_canceled           → must distinguish timeout vs. client cancel
08006  connection_failure       → broken connection, COMMIT outcome may be unknown
```

**SQLSTATE** is a standardized **5-character** error code returned by PostgreSQL. Applications should classify failures by this code instead of matching error message strings that can change across versions or locales. Still, SQLSTATE **alone is not enough** to decide whether any operation may be replayed: you must consider the **transaction stage**, **side effects**, **idempotency**, and **business requirements**.

An especially dangerous scenario is:

```text
Client sends COMMIT
    |
    v
Server may have COMMITted
    |
    X  Connection drops before response reaches client
    |
    v
Client receives network error, final outcome unknown
```

If the client resends “debit 100,000 VND” with a new operation ID, there is a risk of charging **twice**. The safe way to handle this is with a **unique request identifier, a UNIQUE constraint, durable result state, and a controlled lookup/retry protocol**.

This lesson connects three layers: **SQLSTATE classification**, **proper transaction retry decisions**, and **designing operations safe to repeat when the same request arrives multiple times**. Examples use PostgreSQL and JDBC; the same architecture applies to APIs, background jobs, and message consumers.

## 1. Learning Objectives

After this lesson, you can:

1. Read the 5-character SQLSTATE structure and classify by its first two characters.
2. Distinguish non-retryable data errors, retryable transaction errors, timeout/cancel errors, and connection errors with unknown outcomes.
3. Recognize common codes such as `23505`, `23503`, `40001`, `40P01`, `55P03`, `57014`, `08006`, and `25P02`.
4. Explain why `40001`/`40P01` typically require retrying the **entire transaction**, not just the failing SQL statement.
5. Use `SQLException.getSQLState()` in JDBC and avoid depending on message text.
6. Design a bounded retry policy with backoff, jitter, deadlines, logs, and circuit-breaker/overload protection where needed.
7. Separate **connection recovery** from **permission to replay a side-effecting operation**.
8. Use idempotency keys and `UNIQUE`/`ON CONFLICT` to prevent duplicate processing when an API is retried.
9. Understand **commit outcome unknown** and design recovery by querying durable state.
10. Prevent unintended duplication of side effects outside PostgreSQL (sending emails/calling payment providers) via the outbox pattern and receiver-side idempotency.
11. Reproduce deadlock/serialization conflicts in a multi-session lab and observe the SQLSTATE codes.
12. Write negative tests and track retry counts, final outcomes, and system reliability.

## 2. What Is SQLSTATE?

SQLSTATE is a structured error field that PostgreSQL sends to the client over the protocol. For SQL errors fully reported by the server, it typically looks like:

```text
23505
││└──┬──┘
││   └─ Specific condition code (last 3 characters)
└┴───── Error class (first 2 characters: 23)
```

For example:

- `23`: **integrity constraint violation** class.
- `23505`: **unique_violation** condition within class `23`.
- `40`: **transaction rollback** class.
- `40001`: **serialization_failure**.

The code is a **5-character string**, **not an integer**: it can contain letters such as `40P01`, `08P01`, and `22P02`. Never parse SQLSTATE as an integer or match it with a 5-digit-only regex.

### 2.1. Use the Class to Group, the Full Code to Decide

Two-step classification:

1. Check the **first 2 characters** to identify the problem category.
2. Check **all 5 characters** to decide how to handle a specific error.

For example, many codes in `Class 40` relate to transaction rollback, yet you should not automatically replay every operation simply because the code starts with `40`. PostgreSQL gives clear retry guidance for `40001` and `40P01`; other codes require checking their exact meaning.

### 2.2. SQLSTATE Differs from Error Messages

A message may look like:

```text
ERROR: duplicate key value violates unique constraint "orders_pkey"
DETAIL: Key (order_id)=(123) already exists.
SQLSTATE: 23505
```

Clients may see different languages, versions, or formatting details. **`23505`** is a far more stable machine-readable identifier than matching “duplicate key” or constraint substrings in prose.

### 2.3. SQLSTATE Differs from HTTP Status

HTTP `409 Conflict` is an API-layer mapping decision; it is not an SQLSTATE. A backend might map `23505` to HTTP 409 when creating a duplicate resource, or return the prior successful result if it matches **the same idempotency key and payload**.

### 2.4. SQLSTATE Differs from Pure Client-Side Network Errors

Some DNS, TLS, or socket failures happen **before PostgreSQL sends an error response**. The JDBC driver may throw an `SQLException` with a `08`-class SQLSTATE or without a meaningful SQLSTATE. Therefore, a classifier must include an **unknown/null SQLSTATE** branch and inspect driver/connection context rather than assuming every failure carries a specific PostgreSQL code.

### 2.5. Do Not Extract Constraint Names by Parsing Messages

When you need the specific constraint, the PostgreSQL driver can provide structured server error metadata (e.g., `PSQLException.getServerErrorMessage()` and `getConstraint()` when present). Do not do this:

```java
if (e.getMessage().contains("orders_pkey")) {
    // ...
}
```

This logic is fragile; messages can change, constraint metadata is not always populated, and raw PostgreSQL messages should not be exposed to end users.

## 3. Common SQLSTATE Classes

| Class | Category | Examples | Initial Approach |
| --- | --- | --- | --- |
| `00` | Successful Completion | `00000` | Not an error to retry. |
| `01` | Warning | `01000` | Log warning; inspect application contract. |
| `02` | No Data | `02000` | Handle “no data” per business logic. |
| `08` | Connection Exception | `08001`, `08006` | Assess connection loss and unknown COMMIT state. |
| `0A` | Feature Not Supported | `0A000` | Fix SQL/config/version; do not blindly retry. |
| `22` | Data Exception | `22P02`, `22003` | Validate input/type conversion; usually do not retry. |
| `23` | Integrity Constraint Violation | `23505`, `23503` | Handle conflict/constraint per business rules. |
| `25` | Invalid Transaction State | `25P02`, `25006` | Fix transaction flow/rollback. |
| `28` | Invalid Authorization Specification | `28P01` | Fix auth/permission config; do not replay transactions. |
| `3D` | Invalid Catalog Name | `3D000` | Fix database name/config. |
| `3F` | Invalid Schema Name | `3F000` | Fix migration/schema. |
| `40` | Transaction Rollback | `40001`, `40P01` | Usually retry the **entire transaction** for eligible codes. |
| `42` | Syntax Error or Access Rule Violation | `42601`, `42P01`, `42501` | Fix SQL/schema/permissions. |
| `53` | Insufficient Resources | `53100`, `53200`, `53300` | Shed load/fix resources; retry only with strict bounds. |
| `55` | Object Not in Prerequisite State | `55P03`, `55006` | Inspect lock/object state; backoff may apply. |
| `57` | Operator Intervention | `57014`, `57P01`, `57P03` | Distinguish cancel/timeout/shutdown and operation state. |
| `58` | System Error | `58030` | Inspect infrastructure/I/O; do not retry aggressively. |
| `P0` | PL/pgSQL Error | `P0001`, `P0002` | Inspect function/procedure exceptions. |
| `XX` | Internal Error | `XX000` | Investigate/log/involve DBA; do not replay without bounds. |

**No class guarantees 100% “retryable” solely from its 2-character prefix.** For instance, class `08` signals a connection problem, yet if the client does not know whether `COMMIT` succeeded, you cannot automatically replay the same side effect with a new request.

## 4. SQLSTATEs to Memorize and Default Responses

| SQLSTATE | Condition Name | Common Cause | Handling Approach |
| --- | --- | --- | --- |
| `40001` | `serialization_failure` | High isolation level encounters a non-serializable concurrent schedule. | Roll back and retry the **entire transaction** using safe inputs/operation ID. |
| `40P01` | `deadlock_detected` | Two transactions lock resources in conflicting order. | Roll back, back off, retry the entire transaction; also fix lock ordering. |
| `55P03` | `lock_not_available` | `NOWAIT` or `lock_timeout` hits a busy lock. | May retry or return busy per SLA; roll back the failed transaction. |
| `57014` | `query_canceled` | `statement_timeout` or cancellation. | Check root cause/deadline; do not auto-replay if the user canceled. |
| `23505` | `unique_violation` | Insert/Update violates a unique key. | Distinguish duplicate request vs. business conflict; use idempotency/UPSERT. |
| `23503` | `foreign_key_violation` | Missing parent row or operation breaks FK. | Fix ordering and data validity. |
| `23502` | `not_null_violation` | Attempted to write SQL NULL into a NOT NULL column. | Validate input/schema. |
| `23514` | `check_violation` | CHECK constraint violated. | Fix input data/definition. |
| `23P01` | `exclusion_violation` | Exclusion constraint violated. | Handle conflict per business rules. |
| `22P02` | `invalid_text_representation` | Invalid text cast, e.g., `'abc'::integer`. | Fix input; do not retry. |
| `22003` | `numeric_value_out_of_range` | Number exceeds type range. | Fix input/schema. |
| `42501` | `insufficient_privilege` | Missing `GRANT`/role/`USAGE`. | Grant proper privileges; never grant `BYPASSRLS`/superuser indiscriminately. |
| `42P01` | `undefined_table` | Missing table/`search_path`/migration. | Fix migration/configuration. |
| `42703` | `undefined_column` | Wrong column name/schema mismatch. | Fix SQL/migration. |
| `42601` | `syntax_error` | SQL syntax error. | Fix code. |
| `25006` | `read_only_sql_transaction` | Write attempted on read-only transaction/replica. | Route writes to primary; fix transaction mode. |
| `25P02` | `in_failed_sql_transaction` | Continuing SQL after error without rollback. | Roll back or `ROLLBACK TO SAVEPOINT` as appropriate. |
| `08006` | `connection_failure` | Broken connection. | Open new connection; treat **transaction outcome as potentially unknown**. |
| `08003` | `connection_does_not_exist` | Using a connection that no longer exists. | Replace connection; reconcile outcome before replaying. |
| `08001` | `sqlclient_unable_to_establish_sqlconnection` | Failed to establish connection. | Can retry connecting with backoff; do not replay old side effects blindly. |
| `08004` | `sqlserver_rejected_establishment_of_sqlconnection` | Server rejected connection. | Check overload/auth/config, back off. |
| `08P01` | `protocol_violation` | Client/server protocol mismatch. | Investigate driver/proxy; do not hammer retries. |
| `57P01` | `admin_shutdown` | Server shut down by administrator. | Wait for server/reroute; verify outcome. |
| `57P02` | `crash_shutdown` | Server crashed. | Investigate infrastructure and confirm outcome. |
| `57P03` | `cannot_connect_now` | Server not yet ready for connections. | Bounded connect retries. |
| `53300` | `too_many_connections` | Connection slots exhausted. | Cap pools/concurrency, back off, avoid retry storms. |
| `53100` | `disk_full` | Storage exhausted. | Free/expand storage, alert; do not replay en masse. |
| `53200` | `out_of_memory` | Insufficient memory. | Shed load/fix query, alert. |
| `P0001` | `raise_exception` | Default PL/pgSQL `RAISE EXCEPTION`. | Classify per function contract; do not assume transient. |

This list is practical, **not an exhaustive catalog of all PostgreSQL codes**. Official names and codes appear in PostgreSQL documentation *Appendix A — Error Codes*. Do not guess at unfamiliar codes from this table: log the code, look up the official documentation, and handle unrecognized errors conservatively.

## 5. Classifying Errors by Action, Not Just Code

A practical model defines at least five action categories:

| Category | Examples | Action |
| --- | --- | --- |
| **Business/input** | `23505`, `23503`, `23514`, `22P02` | Reject/fix request; map safely to public error responses. |
| **Transient transaction** | `40001`, `40P01` | Roll back then retry the **entire transaction** with a bounded attempt limit. |
| **Conditional contention/timeout** | `55P03`, `57014` | Inspect SLA, cancellation reason, deadline, and retry eligibility. |
| **Connection/unknown outcome** | `08...`, network exceptions | Reconnect; never replay side effects without an idempotent/reconciliation protocol. |
| **Code/config/infrastructure** | `42P01`, `42501`, `53300`, `53100` | Fix deployment/permissions/resources or shed load; never retry indefinitely. |

### 5.1. “Retryable” Is a Property of *Operation + Context*

Two SQL statements raising the same `55P03` may call for different reactions:

- A reporting job acquiring an advisory lock with `NOWAIT`: can wait and retry.
- A checkout request with a 300 ms deadline: lacks time to wait, so return busy/ask client to try later.

Similarly, dropping a connection during `SELECT 1` is completely different from dropping a connection **after sending `COMMIT` for a payment**.

### 5.2. Do Not Turn Every SQLSTATE into HTTP 500

Build an API-layer error taxonomy:

- Invalid input data: return an appropriate client error.
- Duplicate business key: HTTP 409, or the prior confirmed result under idempotency.
- Retry exhaustion due to contention: return a standardized temporary error, optionally with `Retry-After` when appropriate.
- Unknown commit outcome: return a “verification pending / outcome unknown” status with the operation ID so the client can query status instead of assuming failure.

The exact HTTP status depends on your API contract, but **never let the application accidentally trigger duplicate side effects** merely because an HTTP 5xx was returned.

## 6. Safe Retry Decision Model

```text
                 Catch SQLException / DB failure
                             |
                             v
                    Valid SQLSTATE present?
                       /            \
                     Yes             No
                     |                 |
           Classify full code       Check stage + driver
                     |             / network context
       +-------------+-------------+
       |
       +-- Input/schema/privilege → DO NOT auto-retry; fix root cause
       |
       +-- 40001/40P01 → ROLLBACK → retry WHOLE transaction
       |                                (budget/backoff)
       |
       +-- 55P03/57014 → check timeout/cancel/deadline/policy
       |
       +-- Connection failure / lost COMMIT response
                    |
                    v
            Transaction outcome certain?
                /                  \
             Certain              Unknown
              |                       |
        Per situation            Reconcile by operation ID
              |                 + idempotent protocol
              v                       |
        Retry if valid           Never replay blindly
```

**Always separate two questions:**

1. *Can the infrastructure reconnect and re-execute the statement?*
2. *Business-wise, will re-running the operation duplicate results or side effects?*

Answer “yes, retry” only when both technical feasibility and the business contract permit it.

## 7. Lab Dataset: Errors, Transactions, and Idempotency

All examples from here on use a dedicated schema `retry_lab`. Run them on a **practice database**, never on production data. Some demos intentionally trigger errors or deadlocks; they are clearly marked and should be run in two separate `psql` windows.

### 7.1. Create the Schema, Accounts Table, and Data

```sql
CREATE SCHEMA IF NOT EXISTS retry_lab;

CREATE TABLE retry_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_label text NOT NULL,
    balance numeric(14, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO retry_lab.accounts
    (account_id, owner_label, balance)
VALUES
    (1, 'Account A', 1000.00),
    (2, 'Account B',  500.00),
    (3, 'Account C',  200.00);
```

Run the table creation and `INSERT` **once** on a fresh database. If you already created the lab earlier, do not re-run the `INSERT` without an appropriate reset strategy.

### 7.2. Request Table with Idempotency Key

```sql
CREATE TABLE retry_lab.transfer_requests (
    request_id uuid PRIMARY KEY,
    from_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    to_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL
        CHECK (amount > 0),
    status text NOT NULL
        CHECK (
            status IN (
                'processing',
                'applied',
                'insufficient_funds'
            )
        ),
    result_note text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CHECK (from_account <> to_account)
);
```

`request_id` is generated by the client or a trusted service and stays stable **across every retry of the same request**. The `PRIMARY KEY` both blocks duplicate keys and serves as the synchronization anchor for competing concurrent requests.

### 7.3. Ledger Table to Observe Applied Transfers

```sql
CREATE TABLE retry_lab.transfer_ledger (
    ledger_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE
        REFERENCES retry_lab.transfer_requests(request_id),
    from_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    to_account bigint NOT NULL
        REFERENCES retry_lab.accounts(account_id),
    amount numeric(14, 2) NOT NULL
        CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

`UNIQUE(request_id)` on the ledger is a **second line of defense**: one request can never produce two successful transfer entries in the ledger.

### 7.4. Illustrative Outbox Table

```sql
CREATE TABLE retry_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL
        REFERENCES retry_lab.transfer_requests(request_id),
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz,
    UNIQUE (request_id, event_type)
);
```

The outbox only persists events **durably inside the same PostgreSQL transaction**. Delivering events to an external broker or API must be handled by a separate worker and still requires deduplication against double delivery.

### 7.5. Small Table for Testing UNIQUE/FK/CHECK

```sql
CREATE TABLE retry_lab.sample_items (
    item_id integer PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    quantity integer NOT NULL
        CHECK (quantity >= 0)
);

INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES
    (1, 'SKU-A', 10),
    (2, 'SKU-B', 20);
```

### 7.6. Notes on Sample Data

- `accounts` starts with balances `1000/500/200`.
- `transfer_requests`, `transfer_ledger`, and `outbox_events` start empty.
- Examples that execute `COMMIT` mutate state; to replay from scratch, use a fresh lab database or reset data cleanly.
- Error-inducing statements are commented out or marked to run separately because PostgreSQL places an active transaction into a failed state upon error.
- Every SQL statement affects more than raw rows: triggers, foreign keys, locks, WAL, and MVCC remain active.

## 8. Testing Constraint and Data Errors

### 8.1. UNIQUE Violation — `23505`

```sql
-- Run separately to observe the expected error:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (3, 'SKU-A', 5);
```

`sku='SKU-A'` already exists. PostgreSQL can return:

```text
ERROR: duplicate key value violates unique constraint ...
SQLSTATE: 23505
```

**Response:** determine whether two requests share the same identity and should return the existing processed result, or whether two distinct resources genuinely conflict. Do not blindly sleep 100 ms and `INSERT` the same data again.

### 8.2. CHECK Violation — `23514`

```sql
-- Expected error:
-- UPDATE retry_lab.sample_items
-- SET quantity = -3
-- WHERE item_id = 1;
```

There is no reason to retry: `CHECK(quantity >= 0)` will keep rejecting `-3` until the input or rule changes.

### 8.3. NOT NULL — `23502`

```sql
-- Expected error:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (4, NULL, 5);
```

The `sku` field cannot be NULL. Retrying the same payload will never fix it.

### 8.4. FOREIGN KEY — `23503`

```sql
-- Expected error when account_id=999 does not exist in accounts:
-- INSERT INTO retry_lab.transfer_requests (
--     request_id, from_account, to_account, amount, status
-- )
-- VALUES (
--     '00000000-0000-4000-8000-000000000099',
--     999, 2, 10.00, 'processing'
-- );
```

This may be a bad account ID, wrong import order, or a race with parent deletion. Inspect the cause. Only retry waiting on a **legitimate dependency** if the application explicitly implements an eventual-consistency flow; never treat `23503` as transient by default.

### 8.5. Invalid Text Representation — `22P02`

```sql
-- Expected error:
-- SELECT 'not-an-integer'::integer;
```

Validate/fix input beforehand. If it stems from a schema/type mismatch in the application, it is a code defect to fix.

### 8.6. Numeric Out of Range — `22003`

```sql
-- Expected error:
-- SELECT 1000000000000000000000::integer;
```

The value falls outside the representable range of `integer`. Repeating the same SQL serves no purpose.

### 8.7. Viewing SQLSTATE in `psql`

In `psql`, you can enable verbose error output:

```text
\set VERBOSITY verbose
```

After executing a failing SQL statement, `psql` displays the SQLSTATE in verbose output. This is a **`psql` meta-command**, not SQL sent over JDBC.

### 8.8. When to Use `ON CONFLICT`?

If the desired semantics are “insert if absent, otherwise read/skip,” rather than treating `23505` as a transient error, use:

```sql
INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES
    (3, 'SKU-A', 5)
ON CONFLICT (sku) DO NOTHING
RETURNING item_id, sku, quantity;
```

Because `SKU-A` already exists, this statement inserts no new row and `RETURNING` yields 0 rows. **It does not automatically verify whether the payload matches the original request.** If `SKU-A` is a business key, the application must compare other fields or handle conflicts per its contract.

## 9. Failed PostgreSQL Transactions: `25P02`

An essential PostgreSQL behavior: when a statement fails inside a normal transaction block, the transaction enters a **failed state**. Subsequent SQL commands inside that transaction return:

```text
SQLSTATE 25P02
current transaction is aborted, commands ignored
until end of transaction block
```

### 9.1. Lab Test

Open a `psql` session:

```sql
BEGIN;

-- Uncomment to intentionally trigger 23505:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (9, 'SKU-A', 8);

-- If the statement above failed, this statement will fail with 25P02:
SELECT COUNT(*) FROM retry_lab.sample_items;

ROLLBACK;
```

Error-triggering lines are commented out so you can test them selectively. Once you uncomment the `INSERT` and run it inside the same transaction, the subsequent `SELECT` will not “auto-recover.”

### 9.2. Recovery Rules

After an error inside a transaction:

1. Record the **original** SQLSTATE (e.g., `23505` or `40001`).
2. `ROLLBACK` the entire transaction if retrying.
3. With `SAVEPOINT`, you may `ROLLBACK TO SAVEPOINT` when you **intentionally designed** subtransaction error isolation.
4. Never treat `25P02` as the “root cause” and endlessly loop the `SELECT` on the same aborted transaction/connection.

### 9.3. Savepoint for Anticipated Errors

```sql
BEGIN;

SAVEPOINT before_optional_insert;

-- Uncomment to observe 23505:
-- INSERT INTO retry_lab.sample_items
--     (item_id, sku, quantity)
-- VALUES (9, 'SKU-A', 8);

-- If the INSERT above failed, run:
ROLLBACK TO SAVEPOINT before_optional_insert;

SELECT COUNT(*) FROM retry_lab.sample_items;

COMMIT;
```

`ROLLBACK TO SAVEPOINT` restores the outer transaction to a usable state. In practice, if you merely want to skip duplicates on a conflict key, `INSERT ... ON CONFLICT DO NOTHING` is usually cleaner than an exception/savepoint loop.

### 9.4. Savepoints Do Not Replace Full-Transaction Retries

For `40001 serialization_failure`, rolling back to a savepoint and re-running only the failing `UPDATE` **is not a valid retry of the transaction**, because earlier decisions may have relied on a stale snapshot. The recommended approach is retrying the full transaction from the beginning.

### 9.5. JDBC Connections After Errors

If a connection is returned to a pool while stuck in an aborted transaction without rollback, the next request may encounter confusing `25P02` failures. The transaction manager or `try-finally` must always end transactions cleanly (`COMMIT` or `ROLLBACK`), especially on timeouts, cancellations, and exceptions.

## 10. Why `40001` Requires Retrying the Entire Transaction

PostgreSQL supports multiple isolation levels. Under `SERIALIZABLE`, the database can detect concurrent execution schedules that cannot produce results equivalent to any valid serial ordering. One transaction is chosen to roll back and receives:

```text
40001  serialization_failure
```

This **is not necessarily broken SQL**; it is a normal outcome of optimistic/SSI concurrency control. The application is expected to **retry the entire transaction**, including the logic that decides SQL statements and write values.

### 10.1. Why Re-Running Only the Final `UPDATE` Is Insufficient

Suppose:

```text
T1: SELECT remaining inventory in stock
T1: If enough remains, decide to ship 5 items
T2: Updates inventory and COMMITs
T1: UPDATE inventory → 40001
```

If you only repeat the `UPDATE` without re-running the `SELECT` and checking conditions against a fresh snapshot, the earlier decision may no longer hold. When retrying:

```text
BEGIN SERIALIZABLE
  re-read data
  re-evaluate business rules
  recompute values to write
  write changes
COMMIT
```

### 10.2. Keep One Stable Operation ID Across Retries

A business request may execute multiple attempts at the JDBC transaction layer. Its `request_id`/idempotency key must stay **unchanged** across attempts so retries do not become distinct logical operations.

### 10.3. Never Perform External Side Effects Inside a Retryable Transaction

Do not do this:

```text
BEGIN
  UPDATE database
  send real email
  call real payment API
COMMIT  → 40001
retry whole transaction → email/payment executed twice
```

Because a PostgreSQL rollback cannot undo an email already sent or money already transferred via an external provider. Use an outbox and external idempotency instead.

## 11. Two-Session Lab: Producing Serialization Failure `40001`

This is a concurrency demo requiring **two separate `psql` windows** connected to the lab database. Do not run it in production. To avoid mutating the transfer lab's account balances, create a dedicated table:

```sql
CREATE TABLE retry_lab.serial_test (
    id integer PRIMARY KEY,
    value integer NOT NULL
);

INSERT INTO retry_lab.serial_test(id, value)
VALUES (1, 100), (2, 100);
```

### 11.1. Session A

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT SUM(value) AS total
FROM retry_lab.serial_test;
-- Wait for Session B to run its SELECT before continuing.
```

### 11.2. Session B

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT SUM(value) AS total
FROM retry_lab.serial_test;
-- Both transactions initially observe total = 200.
```

### 11.3. Session A Writes the First Row

```sql
UPDATE retry_lab.serial_test
SET value = value + 10
WHERE id = 1;
```

### 11.4. Session B Writes the Second Row

```sql
UPDATE retry_lab.serial_test
SET value = value + 10
WHERE id = 2;
```

### 11.5. Both Sides `COMMIT`

In A:

```sql
COMMIT;
```

In B:

```sql
COMMIT;
```

Both transactions read the entire two-row table and then updated disjoint rows, creating read/write dependencies that can cause PostgreSQL to abort one transaction to preserve serializability. Usually one side receives `40001`, though execution schedule and detection timing depend on concurrency; do not hard-code an assumption that Session B must always be the victim in every run.

### 11.6. Correct Handling

If a transaction receives `40001`, start a fresh `BEGIN ISOLATION LEVEL SERIALIZABLE`, re-run the `SELECT`, re-evaluate decisions and `UPDATE`, and `COMMIT`. Never attempt to re-run `COMMIT` or `UPDATE` on the aborted transaction.

### 11.7. Why Test on a Separate Table?

The experiment may commit one of the two `UPDATE`s. Using the idempotency lab's `accounts` table would alter its starting balances. Keeping the serialization test on `serial_test` keeps the transfer workflow independent.

### 11.8. `SERIALIZABLE` Does Not Eliminate the Need for Retries

Higher isolation enables PostgreSQL to detect and abort non-serializable schedules; it **does not guarantee transactions always succeed on the first try**. An application using `SERIALIZABLE` without proper retry logic will surface unnecessary errors under contention spikes.

## 12. Two-Session Lab: Producing Deadlock `40P01`

A deadlock occurs when two transactions each hold a lock the other needs and neither can proceed. PostgreSQL detects the wait cycle, aborts one transaction as the victim, and reports `40P01`.

### 12.1. Dedicated Table for Deadlocks

```sql
CREATE TABLE retry_lab.deadlock_test (
    id integer PRIMARY KEY,
    value integer NOT NULL
);

INSERT INTO retry_lab.deadlock_test(id, value)
VALUES (1, 10), (2, 20);
```

### 12.2. Session A Locks ID 1

```sql
BEGIN;

UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 1;
-- Keep transaction open.
```

### 12.3. Session B Locks ID 2

```sql
BEGIN;

UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 2;
-- Keep transaction open.
```

### 12.4. Session A Attempts to Update ID 2

```sql
UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 2;
```

This statement will **wait** because Session B holds the row lock on ID 2.

### 12.5. While A Waits, Session B Attempts ID 1

```sql
UPDATE retry_lab.deadlock_test
SET value = value + 1
WHERE id = 1;
```

Now A waits for B and B waits for A. PostgreSQL detects the deadlock and one side receives `40P01`. The surviving transaction can proceed once the victim transaction releases its locks.

### 12.6. Cleanly Closing Both Sessions

The transaction receiving `40P01` must `ROLLBACK`. The surviving transaction can `COMMIT` or `ROLLBACK` if you were only testing. **Never leave sessions hanging or idle in transaction** after the lab.

### 12.7. Preventing Deadlocks at the Source

- Transactions updating multiple rows in common should use a **consistent lock acquisition order**.
- Keep transactions short.
- Avoid holding locks while calling external APIs or waiting for user input.
- Use proper indexes to avoid unnecessarily broad row locking from inefficient scans.
- For queue patterns, consider `FOR UPDATE SKIP LOCKED` when semantically valid.
- Even after reducing risk, keep `40P01` handling in place because complex access patterns can still deadlock.

For example, concurrent transfers A→B and B→A should order locks consistently by `account_id` before updating balances if multi-statement logic locks two accounts.

## 13. `55P03`: `NOWAIT` and `lock_timeout`

`55P03 lock_not_available` typically occurs when a statement requests a lock that cannot be awaited or exceeds the allowed lock wait time.

### 13.1. `FOR UPDATE NOWAIT`

Session A:

```sql
BEGIN;

SELECT *
FROM retry_lab.deadlock_test
WHERE id = 1
FOR UPDATE;
-- Keep transaction open.
```

Session B:

```sql
BEGIN;

-- Expect 55P03 while A still holds the lock:
SELECT *
FROM retry_lab.deadlock_test
WHERE id = 1
FOR UPDATE NOWAIT;

-- If an error occurred, clean up the transaction:
ROLLBACK;
```

`NOWAIT` requests **not waiting** on the row lock where supported, typically returning `55P03` immediately.

### 13.2. `lock_timeout`

```sql
BEGIN;

SET LOCAL lock_timeout = '500ms';

-- Try a command needing a lock held by another session:
-- UPDATE retry_lab.deadlock_test
-- SET value = value + 1 WHERE id = 1;

ROLLBACK;
```

If waiting for the lock exceeds 500 ms, PostgreSQL cancels the statement with `55P03`. Without contention, the `UPDATE` succeeds normally.

### 13.3. Handling According to SLA

`55P03` serves as a “resource busy” signal:

- A maintenance job might wait and retry.
- An interactive API might return a temporary busy error if its deadline is tight.
- A queue worker might pick a different work item instead of contending on the locked one.

If you do retry, roll back the failed transaction, cap attempts, and back off. Never spin-loop retries and add load to the lock manager.

### 13.4. `lock_timeout` and `statement_timeout`

`lock_timeout` measures time waiting to acquire a lock; `statement_timeout` bounds statement execution per PostgreSQL semantics. If `lock_timeout` equals or exceeds `statement_timeout`, `statement_timeout` may fire first, rendering the lock wait limit less useful. Configure both thresholds consistently with your SLA.

## 14. `57014`: `query_canceled` and `statement_timeout`

`57014 query_canceled` can arise either when a client cancels a query or when PostgreSQL cancels a statement due to timeout. **Never infer the cause from the SQLSTATE alone.**

### 14.1. `statement_timeout` Demo

```sql
BEGIN;

SET LOCAL statement_timeout = '1s';

-- The following intentionally runs past the limit:
-- SELECT pg_sleep(2);

ROLLBACK;
```

Uncommenting `SELECT pg_sleep(2)` causes PostgreSQL to cancel the query after roughly one second and return `57014`. The transaction must be rolled back before continuing.

### 14.2. Same Code, Very Different Contexts

- **User clicked Cancel:** do not automatically re-run the query they asked to stop.
- **Service-configured `statement_timeout` per SLA:** retrying only helps if conditions change, budget remains, and the operation is idempotent; do not repeatedly rerun a query that always takes 30 seconds under a 1-second timeout.
- **Admin/job cancellation:** inspect the operational reason; immediate replay may be prohibited.

### 14.3. Connection May Still Be Alive, Even Though the Transaction Failed

A `57014` does not always mean the socket closed. The driver can keep using the connection after an appropriate `ROLLBACK`. Do not “nuke the pool” every time a query cancels; equally, do not treat a failed transaction as healthy.

### 14.4. Multi-Layer Timeouts

Applications often stack:

```text
HTTP/request deadline
   └── JDBC query timeout
          └── PostgreSQL statement_timeout
                 └── PostgreSQL lock_timeout
```

Coordinate limits so inner layers can cleanly stop work before outer layers lose patience. Once the overall deadline has expired, backing off and retrying only prolongs failures and increases load.

## 15. Inspecting Transactions and Blocking in PostgreSQL

### 15.1. `pg_stat_activity`

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    clock_timestamp() - query_start AS query_elapsed,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Under contention, `wait_event_type = 'Lock'` is often a telling signal. Not every slow query is waiting on a lock: it could be CPU, I/O, a poor plan, or external network latency.

### 15.2. Identifying Blocker PIDs

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

### 15.3. `pg_locks`

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
WHERE l.relation = 'retry_lab.deadlock_test'::regclass
ORDER BY l.pid, l.mode;
```

Do not expect every row-level lock to appear directly as an obvious relation lock row; PostgreSQL uses multiple lock types and wait representations. Read `pg_locks` alongside `pg_stat_activity` and `pg_blocking_pids`.

### 15.4. Log the Root Error Before `25P02`

In a sequence where `23505` is followed by `25P02`, the root cause is `23505`. Log the first exception along with the operation ID and transaction attempt. Never log only the trailing error and conclude the server “got stuck in a transaction.”

## 16. `Class 08`: Connection Failure Does Not Mean Safe Operation Replay

`08006`, `08003`, and sibling codes describe the client–server connection path. When a connection breaks:

- A read-only `SELECT` without side effects can generally be re-run on a new connection if deadline remains.
- An explicit transaction that has not yet sent `COMMIT` will roll back when the session terminates; however, the application must still distinguish stages and external side effects.
- If the client already sent an autocommit DML statement or `COMMIT` and lost the response, **you do not know whether the transaction committed**.

### 16.1. A Lost Response Does Not Prove Server Rollback

```text
Client                  Network               PostgreSQL
  |                        |                        |
  |---- COMMIT ----------->|----------------------->|
  |                        |                   commit succeeds
  |                        X<---- response OK -------|
  |<-- connection error ---|
  |
  | App assumes "error", yet DB already applied changes
```

Alternatively, `COMMIT` never reached the server, or the server crashed before committing. From the client's socket error alone, the two branches are indistinguishable without durable outcome tracking.

### 16.2. Never Retry `COMMIT` on a New Connection

The old transaction belonged to the old session/connection. A new connection cannot “resume committing the old transaction” like continuing an unfinished Java function. Recovery requires **reconciling durable state** and, if necessary, re-executing **with the same business operation ID** inside a new transaction under an idempotent protocol.

### 16.3. Connection Pools Do Not Guarantee Idempotency

HikariCP, PgBouncer, or proxies can establish fresh connections, but they do not know whether the business action “transfer 100” succeeded. Pools handle broken sockets; **the application** must handle operation outcomes and duplicates.

### 16.4. Connecting to a Read Replica

If after a disconnect the application queries the operation ID from a read replica experiencing replication lag, it may not yet see the row just committed on the primary. “Not visible on the replica” **does not prove** the operation failed. Reconciliation must read from an adequately consistent source (typically the primary or an explicitly designed consistency path).

### 16.5. Failover and Certainty

Failover can change visible committed state depending on replication and durability settings, particularly with asynchronous replication. Idempotency keys prevent duplicate replay against authoritative state, but failover policy and RPO must still be defined; do not claim every acknowledged commit survives every form of asynchronous failover.

## 17. What Is Idempotency?

An operation is **idempotent** if sending the **same logical operation** multiple times does not apply its business effect again, even if metadata, logs, or timestamps differ.

### 17.1. Comparing Three SQL Statements

```sql
-- Sets the same target value across repeated runs:
UPDATE retry_lab.sample_items
SET quantity = 10
WHERE item_id = 1;

-- Not idempotent in final value:
UPDATE retry_lab.sample_items
SET quantity = quantity + 10
WHERE item_id = 1;

-- New insert risks duplication without uniqueness:
INSERT INTO retry_lab.sample_items
    (item_id, sku, quantity)
VALUES (10, 'SKU-C', 10);
```

This illustrates the concept; running it repeatedly in the lab alters state and the `INSERT` may hit `23505` due to PK/UNIQUE. Repeating `SET quantity = 10` yields the same final quantity, though triggers, `updated_at`, WAL, and audit logs **still fire again**.

### 17.2. Business Idempotency Goes Beyond “SET Same Value”

A transfer API runs `balance = balance - 100`, which is inherently non-idempotent. We introduce a **business operation ID** so the system applies that debit **at most once for that ID**.

```text
POST /transfers
Idempotency-Key: 7c9e... (stable)
Payload: {from:1, to:2, amount:100}

Attempt 1: executes successfully, response lost
Attempt 2: same key and same payload
        → return stored result status
        → DO NOT debit twice
```

### 17.3. Three Design Requirements

1. **Unique, stable key** representing the same logical request across HTTP client, queue consumer, and transaction retries.
2. **Durable result record** protected by uniqueness and committed **in the same transaction** as the business mutation.
3. **Payload comparison**: the same key with a different amount or account is a conflict error—never return blind success or execute a new mutation.

### 17.4. Idempotency Alone Does Not Provide Exactly-Once Delivery

Clients, networks, and brokers can still deliver the same message multiple times. The practical goal is **at-least-once delivery with idempotent processing**, or “effectively once” for a business operation within the designed boundary. Never claim every side effect outside PostgreSQL is strictly once unless the downstream receiver also supports deduplication.

## 18. Designing a Result Table with a Unique Key

The lab table `transfer_requests` has:

```sql
request_id uuid PRIMARY KEY
```

Each key gets at most one row storing:

- `from_account`, `to_account`, `amount`: fields identifying the request.
- `status`: `processing`, `applied`, `insufficient_funds`.
- `result_note`: returnable outcome details.
- `completed_at`: timestamp when the terminal result was recorded.

### 18.1. Same Key, Different Payload Must Be Rejected

Consider two requests:

```text
Request A:
  request_id = 1111...
  from=1, to=2, amount=100

Request B:
  request_id = 1111...
  from=1, to=3, amount=900
```

If you simply run `ON CONFLICT DO NOTHING` and return the stored result, Request B receives a response that does not match what it asked for. Your API contract should return **409 Idempotency-Key Conflict** or an equivalent error whenever an existing key is reused with a mismatched payload.

### 18.2. Payload Canonicalization

If idempotency relies on a request hash, ensure consistent canonicalization:

- Sort/normalize relevant fields; never hash raw JSON strings with arbitrary key ordering.
- Define numeric precision rules (e.g., whether `100.00` and `100` count as identical).
- Scope keys by user/tenant so one tenant's key cannot collide with another's.
- Protect request secrets/tokens in logs.

In the lab, we compare the **three columns directly** (`from_account`, `to_account`, `amount`) to avoid needing a separate canonical hashing scheme.

### 18.3. Scope of `request_id`

With a global UUID `PRIMARY KEY`, two tenants using the same UUID would conflict. That can be fine if UUIDs are sufficiently random and the app authorizes result reads properly. Other systems use `UNIQUE(tenant_id, request_key)` so keys are unique **per tenant**. What matters is keeping security boundaries strict so the backend never leaks another tenant's request results.

### 18.4. Never Infer Retries from Sequence Gaps

PostgreSQL `nextval()` can leave gaps on rollbacks or upsert conflicts. Sequence gaps do not prove a business request ran twice; check **result rows and ledger entries by operation ID**.

## 19. Safe Transfer Protocol Under Retries

We implement **a single PostgreSQL transaction** consisting of:

1. Reserve `request_id` with `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
2. If the key already exists, **do not write again**; read the existing record and compare payloads.
3. If the key is new, debit the source account via `UPDATE ... WHERE balance >= amount`.
4. If funds are insufficient, save terminal status `insufficient_funds` and `COMMIT` without crediting.
5. If debit succeeds, credit the target account, write the ledger row, and insert the outbox row.
6. Set `status = 'applied'` and `COMMIT`.
7. Return success only after `COMMIT` is confirmed; if the connection drops, reconcile by request ID.

### 19.1. Flow Diagram

```text
BEGIN
  |
  v
INSERT request_id ... ON CONFLICT DO NOTHING RETURNING
  |
  +-- 0 rows -> STOP write path
  |             read existing request, compare payload/status
  |             return stored result or report key conflict
  |
  +-- 1 new row
          |
          v
      UPDATE source balance >= amount RETURNING
          |
          +-- 0 rows -> mark insufficient_funds -> COMMIT
          |
          +-- 1 row -> UPDATE target
                         -> INSERT ledger UNIQUE(request_id)
                         -> INSERT outbox UNIQUE(request_id,event_type)
                         -> mark applied -> COMMIT
```

**This is an application-driven state machine**, not a monolithic SQL script to execute unconditionally top-to-bottom. The app must inspect each statement's result and choose the next branch.

### 19.2. Step 1: Reserve the Request ID

Example request:

```text
request_id = 00000000-0000-4000-8000-000000000101
from_account = 1
to_account = 2
amount = 100.00
```

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id,
    from_account,
    to_account,
    amount,
    status
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

If `RETURNING` yields **1 row**, this transaction reserved a fresh key. If it yields **0 rows**, **do not execute the debit/credit steps below**; instead, `ROLLBACK` the current transaction and look up the existing result in an appropriate transaction/query.

### 19.3. Step 2: Conditional Debit Without Negative Balances

Execute only if Step 1 returned 1 row:

```sql
UPDATE retry_lab.accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00
RETURNING account_id, balance;
```

With the initial dataset, this `UPDATE` returns account 1 with balance **900.00**. Evaluating `balance >= 100.00` inside the `UPDATE` with row locking prevents concurrent transactions from overdrawing the account under PostgreSQL semantics.

**If the `UPDATE` returns 0 rows:**

```sql
UPDATE retry_lab.transfer_requests
SET
    status = 'insufficient_funds',
    result_note = 'Insufficient balance',
    completed_at = clock_timestamp()
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

COMMIT;
```

In that branch, do not execute the credit/ledger/outbox success steps. For a request ID already finalized as `insufficient_funds`, retries with the same key return the saved rejection result; if the user deposits more funds and wants to attempt a **new** transfer, the client must generate a new operation key per the API contract.

**Along the happy path in the lab** (debit returned 1 row), **skip the `insufficient_funds` block** and continue to Step 3.

### 19.4. Step 3: Credit the Target Account

```sql
UPDATE retry_lab.accounts
SET balance = balance + 100.00
WHERE account_id = 2
RETURNING account_id, balance;
```

With the initial dataset, account 2 becomes **600.00**. This statement must affect exactly 1 row; if 0 rows or an error occurs, **ROLLBACK the entire transaction**—never commit only the debit.

### 19.5. Step 4: Write a Unique Ledger Row by Request ID

```sql
INSERT INTO retry_lab.transfer_ledger (
    request_id,
    from_account,
    to_account,
    amount
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00
)
RETURNING ledger_id, request_id;
```

The `UNIQUE(request_id)` constraint acts as a **second guard** against writing duplicate ledger rows for the same logical operation. On any unexpected error, **never** swallow it and commit an inconsistent partial debit/credit.

### 19.6. Step 5: Write the Outbox Event

```sql
INSERT INTO retry_lab.outbox_events (
    request_id,
    event_type,
    payload
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    'transfer_applied',
    jsonb_build_object(
        'request_id',
        '00000000-0000-4000-8000-000000000101',
        'from_account', 1,
        'to_account', 2,
        'amount', 100.00
    )
);
```

The event is persisted in the **same DB transaction** as the debit, credit, and ledger entry. It is not yet sent to the broker or received by another service.

### 19.7. Step 6: Record Terminal Result and `COMMIT`

```sql
UPDATE retry_lab.transfer_requests
SET
    status = 'applied',
    result_note = 'Transfer completed',
    completed_at = clock_timestamp()
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

COMMIT;
```

When the server confirms `COMMIT`, the marker, debit, credit, ledger entry, and outbox event are all committed atomically together.

### 19.8. State After a Successful Run

```sql
SELECT account_id, balance
FROM retry_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

SELECT request_id, from_account, to_account,
       amount, status, completed_at
FROM retry_lab.transfer_requests
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';

SELECT COUNT(*) AS ledger_rows
FROM retry_lab.transfer_ledger
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';
```

Assuming an untouched initial dataset and a committed happy path: balances are **900/600**, the marker is `applied`, and the ledger count is **1**.

### 19.9. Why Not `COMMIT` the `'processing'` Marker First?

In this pattern, the marker, balance updates, and terminal status share **a single transaction**. Other transactions cannot observe an uncommitted `processing` marker. If a marker were committed upfront and the worker died, the system could stay stuck in `processing` forever unless a more complex lease/recovery protocol existed.

Committing a `processing` state is not universally forbidden, but two-phase processing requires explicit **lease timeouts, ownership, retries, and compensation**. This lab adopts the simpler atomic protocol.

## 20. Retrying the Same `request_id` After Success

Suppose the transfer with ID `00000000-0000-4000-8000-000000000101` already committed. The client lost the response, so it sends **the same key and payload again**.

### 20.1. Reserve the Key Again

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id,
    from_account,
    to_account,
    amount,
    status
)
VALUES (
    '00000000-0000-4000-8000-000000000101',
    1, 2, 100.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

This returns **0 rows** because the key already exists. That signals **not to run debit/credit again**.

### 20.2. Roll Back the Write Path and Read the Existing Result

```sql
ROLLBACK;

SELECT
    request_id,
    from_account,
    to_account,
    amount,
    status,
    result_note,
    completed_at
FROM retry_lab.transfer_requests
WHERE request_id =
    '00000000-0000-4000-8000-000000000101';
```

The backend compares the three account/amount columns with the incoming request:

- If payloads match and `status = 'applied'` → return the **saved prior transfer result**, without issuing another debit.
- If payloads match and `status = 'insufficient_funds'` → return the stored rejection result.
- If payloads differ → return an idempotency-key reuse error.
- If a committed `processing` state somehow appears outside this design → never treat it as success; apply stale-lease/recovery handling.

### 20.3. Idempotency Does Not Mean “Every Duplicate Succeeds”

Request A uses key K with amount 100; Request B reuses K with amount 900. Request B must be **rejected**, not silently handed Request A's success response. This also protects clients against buggy key reuse.

### 20.4. What If the Key Does Not Exist Yet?

After a connection failure, not finding the key on the primary **does not always prove an in-flight attempt cannot still commit**. The earlier request may still be finishing, its commit may be in flight, or a job may not have started yet. The backend must retry/reconcile under the **same ID** so the `UNIQUE` constraint ensures at most one transaction wins.

### 20.5. When Two Requests with the Same Key Arrive Concurrently

Session A:

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id, from_account, to_account, amount, status
)
VALUES (
    '00000000-0000-4000-8000-000000000202',
    1, 2, 25.00, 'processing'
);
-- Hold transaction open without COMMIT.
```

Session B:

```sql
BEGIN;

INSERT INTO retry_lab.transfer_requests (
    request_id, from_account, to_account, amount, status
)
VALUES (
    '00000000-0000-4000-8000-000000000202',
    1, 2, 25.00, 'processing'
)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id;
```

Session B will **wait** for Transaction A's outcome because the unique key is locked in conflict. If A commits, B gets 0 rows from `RETURNING`. If A rolls back, B inserts the key and becomes the owner of the attempt.

This is a key advantage of a **database `UNIQUE` constraint**; checking `SELECT COUNT(*)` before `INSERT` without uniqueness is unsafe because two concurrent sessions can both observe “not found” and both proceed.

### 20.6. Cleaning Up the Two-Session Demo

Do not execute transfer updates after merely reserving ID `...202` in Sessions A/B; this was purely a `UNIQUE` lock experiment. Clean up with:

```sql
ROLLBACK;
```

in open sessions; if Session B is waiting, end A first, inspect B's result, and then `ROLLBACK` B. If A ever committed a leftover `processing` demo row, clean up test data via admin procedures—do not feed incomplete markers into real business flows.

### 20.7. `READ COMMITTED` and Visibility After `DO NOTHING`

In PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` can detect a conflict against a row committed by a concurrent transaction even when that row is not visible in the snapshot of the **current statement**. Under `READ COMMITTED`, a subsequent `SELECT` statement gets a fresh snapshot and can see the committed row. Therefore, the protocol never assumes `DO NOTHING RETURNING 0` guarantees the conflicting row is selectable within the **same statement**.

For simplicity, the pattern ends the current attempt and reads state in a new statement/transaction once conflict resolution finishes. Under `REPEATABLE READ` or `SERIALIZABLE`, follow the snapshot and retry rules of that isolation level.

## 21. Commit Outcome Unknown: The Third State Beyond Success/Failure

In side-effecting APIs, an attempt's result is not just “success” or “failure.” You must model:

| Client State | Meaning |
| --- | --- |
| **Confirmed success** | Server confirmed `COMMIT`, or reconciliation located the terminal record for that request ID. |
| **Confirmed failure/rollback** | Received an error whose semantics guarantee rollback/no commit, or a terminal business rejection was recorded. |
| **Unknown outcome** | Lost response/network connection before confirming whether the transaction committed. |

### 21.1. Why Unknown Must Never Be Treated as Failed

If the database committed while the response dropped, marking it failed and generating a new request ID to “retry” can execute a brand-new valid transaction and debit the account **a second time**.

### 21.2. Do Not Assert Success Just Because the Connection Recovers

A pool replacing the connection and passing a health ping tells you nothing about the prior transaction. Always query the **business result by ID** from an authoritative store.

### 21.3. Recovery Protocol

```text
Lost response on COMMIT
         |
         v
Keep the same request_id; DO NOT generate a new key
         |
         v
Open a new connection to a consistent source
         |
         v
SELECT transfer_requests WHERE request_id = K
         |
         +-- APPLIED/REJECTED & payload match
         |       -> return stored result
         |
         +-- Key exists with payload mismatch
         |       -> conflict error / security incident
         |
         +-- Not found / unclear
                 -> short wait/backoff or retry
                    the full business operation with K
                    under the atomic UNIQUE protocol
```

### 21.4. Reconciliation Needs a Time Bound

Do not stall the API indefinitely. You can return `202 Accepted` / “pending verification” per contract and expose `GET /transfers/by-request-id/K`, or return a temporary error instructing the client to **retry with the same key**. The API contract should clearly define how clients may safely resend.

### 21.5. Do Not Mistake “Marker Missing on Lagging Replica” for Rollback

Right after the primary commits, an asynchronous replica may not have replayed the WAL yet. Result lookups must match your recovery consistency requirements, typically reading from the primary or authoritative writer.

### 21.6. Connection Codes Cannot Distinguish Every Path

`08006`, `IOException`, connection resets, and socket timeouts may be surfaced differently by drivers and wrappers. Whenever a response is lost around `COMMIT` or an autocommit write, classify it as **outcome ambiguous** even without a specific PostgreSQL SQLSTATE.

## 22. Outbox: Do Not Send Emails or Events Directly Inside Transaction Retries

Suppose every transfer must notify another system. Do not write:

```text
BEGIN
UPDATE accounts
HTTP POST to notification service
COMMIT
```

If `COMMIT` hits `40001`/`40P01` and rolls back, the HTTP POST **cannot roll back with it**. Retrying the entire transaction can send the notification twice.

### 22.1. Transactional Outbox

```text
BEGIN PostgreSQL
  UPDATE accounts
  INSERT ledger
  INSERT transfer_requests result
  INSERT outbox_events
COMMIT
      |
      v
Outbox worker reads unpublished events
      |
      v
Sends event to external broker/API
      |
      v
Marks delivery status / retries
```

This is the principle of **atomic commit in the DB, asynchronous delivery externally**.

### 22.2. Worker Claiming Event Batches

A batch claiming pattern:

```sql
BEGIN;

SELECT event_id, request_id, event_type, payload
FROM retry_lab.outbox_events
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- This is a worker selection/locking step.
-- Without finishing processing, ROLLBACK releases the locks.
ROLLBACK;
```

`SKIP LOCKED` prevents multiple workers from blocking on rows locked by peers, though it **does not** guarantee exactly-once delivery if a worker crashes after the remote side receives the event.

### 22.3. Crash at the Broker Boundary

```text
Worker sends event K -> broker receives and processes it
         |
         X  Worker crashes before UPDATE published_at
         |
         v
New worker sees K still unpublished -> resends K
```

Solution: the receiver must implement **idempotency/consumer deduplication** keyed by `event_id` or `request_id + event_type`. An outbox alone does not magically make delivery exactly-once.

### 22.4. Consumer Idempotency

For example, the consumer stores:

```sql
CREATE TABLE retry_lab.processed_events (
    consumer_name text NOT NULL,
    event_id bigint NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Inside the consumer's transaction, attempt to insert `(consumer_name, event_id)` via `ON CONFLICT DO NOTHING RETURNING`; if 0 rows return, skip re-applying database side effects. If the consumer calls external services too, integrate with their idempotency protocols as well.

### 22.5. Do Not Hold a DB Transaction Open Across Slow External API Calls

Acquiring `FOR UPDATE` and holding the transaction open during multi-second network calls increases lock contention. Production systems typically use a **claim/lease** pattern on the outbox—committing the claim, sending externally, then recording success/failure with timeouts and retries. That is more intricate than the lab snippet and must guard against two workers claiming the same item on lease expiry.

### 22.6. Separate Business Outcome from Delivery Status

A transfer may already be `applied` in PostgreSQL while the `transfer_applied` event has not yet reached a consumer. Do not reverse a transfer simply because a notification was delayed unless the business contract demands it. Track **business commit state** and **notification delivery state** separately.

## 23. Reading SQLSTATE in JDBC

In Java, `java.sql.SQLException` provides:

```java
String sqlState = exception.getSQLState();
int vendorCode = exception.getErrorCode();
String message = exception.getMessage();
```

With pgJDBC, `getSQLState()` is the primary source for PostgreSQL error codes. `getErrorCode()` is a driver/vendor integer (if populated) and **does not replace SQLSTATE** in this model.

### 23.1. Error-Handling Pattern

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class StockReader {
    private final DataSource dataSource;

    public StockReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int readQuantity(int itemId) throws SQLException {
        String sql =
            "SELECT quantity " +
            "FROM retry_lab.sample_items " +
            "WHERE item_id = ?";

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setInt(1, itemId);
            try (var rs = ps.executeQuery()) {
                return rs.next() ? rs.getInt(1) : -1;
            }
        } catch (SQLException ex) {
            String state = ex.getSQLState();
            // Structured logging: state, operation name, correlation ID.
            // Do not expose raw DB details (SQL, keys, constraint values)
            // directly in public responses.
            throw ex;
        }
    }
}
```

This snippet uses Java 10+ `var` inside try-with-resources; on older Java versions, declare `ResultSet` explicitly. The key points are checking `getSQLState()` and never swallowing the exception.

### 23.2. SQLSTATE Can Be Null

When failures originate in the client or network before receiving a server response, SQLSTATE can be `null` or uninformative. Never call `state.startsWith(...)` without a null check.

### 23.3. `SQLException` Chain

`SQLException` exposes `getNextException()`, and frameworks may wrap exceptions via `cause`. When logging, preserve the original exception and relevant nested SQLSTATEs, without blindly grabbing an arbitrary nested code that hides the root failure.

### 23.4. PostgreSQL-Specific Diagnostics

When using pgJDBC, `org.postgresql.util.PSQLException` may carry `ServerErrorMessage`:

```java
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

static void inspectConstraint(SQLException ex) {
    if (ex instanceof PSQLException) {
        PSQLException pgEx = (PSQLException) ex;
        ServerErrorMessage server = pgEx.getServerErrorMessage();
        if (server != null) {
            String constraint = server.getConstraint();
            String table = server.getTable();
            // Use available metadata only for allowlisted logging/categorization;
            // never leak it to public clients.
        }
    }
}
```

Not every failure includes a `ServerErrorMessage` or constraint name; do not rely on it to classify network errors.

### 23.5. Why Avoid Parsing Messages?

Checks like `ex.getMessage().contains("deadlock detected")` are brittle under localization, proxies, driver formatting changes, wording updates, and nested wrappers. `"40P01".equals(ex.getSQLState())` is explicit and reliable.

## 24. Writing an SQLSTATE Classifier

Avoid a single boolean `isRetryable(error)` for all situations. Return a **semantic decision**:

```java
import java.sql.SQLException;

public final class PgErrorClassifier {
    public enum Action {
        RETRY_WHOLE_TRANSACTION,
        RETRY_CONTENTION_IF_DEADLINE,
        RESOLVE_BUSINESS_CONFLICT,
        CHECK_CANCEL_OR_TIMEOUT,
        CONNECTION_OUTCOME_UNKNOWN,
        ROLLBACK_ABORTED_TRANSACTION,
        FIX_INPUT_OR_CONFIGURATION,
        INVESTIGATE
    }

    public static Action classify(SQLException error) {
        String state = error.getSQLState();

        if (state == null || state.length() != 5) {
            return Action.INVESTIGATE;
        }

        switch (state) {
            case "40001": // serialization_failure
            case "40P01": // deadlock_detected
                return Action.RETRY_WHOLE_TRANSACTION;
            case "55P03": // lock_not_available
                return Action.RETRY_CONTENTION_IF_DEADLINE;
            case "57014": // query_canceled
                return Action.CHECK_CANCEL_OR_TIMEOUT;
            case "23505": // unique_violation
            case "23P01": // exclusion_violation
                return Action.RESOLVE_BUSINESS_CONFLICT;
            case "25P02": // in_failed_sql_transaction
                return Action.ROLLBACK_ABORTED_TRANSACTION;
            case "23502":
            case "23503":
            case "23514":
            case "22P02":
            case "22003":
            case "42501":
            case "42P01":
            case "42703":
            case "42601":
                return Action.FIX_INPUT_OR_CONFIGURATION;
            default:
                if (state.startsWith("08")) {
                    return Action.CONNECTION_OUTCOME_UNKNOWN;
                }
                return Action.INVESTIGATE;
        }
    }
}
```

This is a **preliminary classification step**, not a complete retry engine. `CONNECTION_OUTCOME_UNKNOWN` signals that **stage and side effects must be evaluated**: some connection errors happen before any SQL is sent (no commit possible), while others happen after `COMMIT` was transmitted.

### 24.1. Do Not Auto-Retry All of Class `40`

Only explicitly analyzed codes such as `40001` and `40P01` enter the whole-transaction retry branch. If you encounter another `40xxx` code, inspect its meaning rather than blindly replaying.

### 24.2. Do Not Assume Every `SQLTransientException` Is Safe

Java provides transient SQL exception subclasses, yet pgJDBC and frameworks do not necessarily map every SQLSTATE uniformly. “Transient” at the connection layer does not answer whether **side effects already committed**.

### 24.3. Classifiers Need Additional Context

A complete decision function evaluates:

```text
Decision = f(
    SQLSTATE,
    SQL command / operation,
    transaction stage,
    commit attempted?,
    idempotency protocol?,
    request deadline,
    retry attempt count,
    isolation level,
    user cancellation?
)
```

For example, `57014` caused by active user cancellation must be handled differently from `55P03` hit by a background job on a busy lock.

## 25. JDBC Transaction Retry Pattern

A safe retry wrapper should:

1. Open a **new connection and transaction** per attempt.
2. Re-execute the **entire** business SQL sequence, including reads and decision checks.
3. Roll back whenever an attempt fails.
4. Never call external APIs or send emails inside work that can execute repeatedly.
5. Keep the **operation ID fixed** across all attempts.
6. Stop when attempts, deadline, or cancellation limits are reached.
7. If connection fails during commit, switch to **reconciliation** instead of treating the transaction as definitely rolled back.

### 25.1. Java Example: Retrying `40001` and `40P01`

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import java.util.concurrent.ThreadLocalRandom;

public final class SerializableTransactionRunner {
    @FunctionalInterface
    public interface Work<T> {
        T run(Connection c) throws SQLException;
    }

    private final DataSource dataSource;
    private static final int MAX_ATTEMPTS = 4;

    public SerializableTransactionRunner(DataSource ds) {
        this.dataSource = ds;
    }

    public <T> T execute(Work<T> work)
            throws SQLException, InterruptedException {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            boolean retry = false;

            try (Connection c = dataSource.getConnection()) {
                c.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );
                c.setAutoCommit(false);

                try {
                    // May run multiple times: no external non-DB side effects.
                    T result = work.run(c);
                    c.commit();
                    return result;
                } catch (SQLException ex) {
                    try {
                        c.rollback();
                    } catch (SQLException rollbackError) {
                        ex.addSuppressed(rollbackError);
                    }

                    String state = ex.getSQLState();
                    retry = ("40001".equals(state)
                            || "40P01".equals(state))
                            && attempt < MAX_ATTEMPTS;

                    if (!retry) {
                        // For connection errors on COMMIT, caller must
                        // reconcile via request_id/idempotency.
                        throw ex;
                    }
                }
            }

            // Connection closed/returned to pool before sleeping.
            if (retry) {
                long baseMs = Math.min(100L << (attempt - 1), 800L);
                long jitterMs = ThreadLocalRandom.current()
                    .nextLong(0, 100);
                Thread.sleep(baseMs + jitterMs);
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
```

**Important:** This example focuses on `40001`/`40P01` to illustrate the retry loop. Do not deploy it as a complete production transaction manager without adding:

- **Request deadlines** and HTTP/job cancellation checks.
- Connection/pool acquisition error and timeout handling.
- Structured logging/metrics and system-wide retry budgets.
- Reconciliation for **commit outcome unknown**.
- Spring/JTA transaction context coordination and cleanup.
- Rules governing external side effects.

### 25.2. Why Is `rollback()` Still Called After a `COMMIT` Error?

The code attempts a best-effort rollback, yet once `COMMIT` has been sent and the socket drops, calling `rollback()` on a broken connection **cannot prove the prior `COMMIT` failed**. If a class `08` SQLSTATE occurs at the commit stage, the caller must retain the operation ID and reconcile. Never use “rollback did not throw” as proof that it is safe to replay under a new key.

### 25.3. Do Not “Retry” Data Errors

The wrapper retries strictly those two transaction conflict codes. If `work` throws `23505`, `23514`, or `22P02`, the exception propagates to the business layer; it never sleeps and futilely repeats the same bad input.

### 25.4. Beware Retrying Inside the Same Transaction

After `40001`, the old transaction is dead. You must start a fresh transaction and rerun the `SELECT`/decision logic. Never invoke `work.run(c)` again without rolling back on the aborted transaction.

### 25.5. Implications of `Thread.sleep`

In high-throughput services, sleeping on a request thread ties up worker threads and raises latency. High-load systems may use delayed queues, async retries, or worker schedulers for backoff; the synchronous sleep above illustrates the mechanics.

### 25.6. Retrying Does Not Authorize Executing Two Logical Requests

If `work` generates a fresh `UUID.randomUUID()` on **each attempt**, each retry becomes a distinct business key. Generate the key once at the request boundary and pass it into `Work` across every retry. If the operation triggers external side effects, use an outbox or compensation.

## 26. Spring and Transaction Managers: Retry at the Right Boundary

In Spring, `@Transactional` typically wraps a transaction managed by an AOP proxy. A common bug is:

```java
@Transactional
public void pay() {
    try {
        updateAccount();
    } catch (Exception ex) {
        updateAccount(); // Retrying inside the already failed transaction!
    }
}
```

If `updateAccount()` hits a PostgreSQL serialization failure or deadlock, the active transaction is already marked for rollback. Retrying SQL inside the same `@Transactional` method does not open a new transaction or snapshot and will typically fail with `25P02`.

### 26.1. Place Retries Outside the Transaction Boundary

Conceptual structure:

```text
API/controller
    |
    v
Retry coordinator (holds operation ID, deadline)
    |
    +-- Attempt #1 -> Transactional service (BEGIN ... COMMIT/ROLLBACK)
    |                                  |
    |                           SQLSTATE 40001
    |
    +-- backoff
    |
    +-- Attempt #2 -> Transactional service (NEW TRANSACTION)
                                       |
                                 success/commit
```

Spring implementations include having a `RetryService` call another bean annotated with `@Transactional`, or using `TransactionTemplate` so **each attempt opens a fresh transaction scope**. Pay careful attention to interceptor ordering if `@Retryable` and `@Transactional` sit on the same method; never assume annotation order defaults are right.

### 26.2. Self-Invocation Bypassing Spring Proxies

An internal call like `this.transactionalMethod()` bypasses standard AOP proxy transaction advice. Splitting retry and transaction across methods inside the same bean without going through a proxy can silently fail to open separate transactions per attempt.

### 26.3. Frameworks May Translate `SQLException`

Spring can translate `SQLException` into `DataAccessException` subclasses. Which exception class is chosen can vary by translator, driver, or framework version; avoid basing retry logic solely on one concrete Spring exception name. When you need SQLSTATE, unwrap the causal `SQLException` from the exception chain or configure a well-defined translator contract.

### 26.4. Rollback Rules by Exception Type

By default, Spring's `@Transactional` rolls back on unchecked exceptions; checked exceptions may require explicit `rollbackFor` configuration per business rules. If a handler swallows the exception and returns “success,” the transaction manager may commit instead of rolling back as expected.

### 26.5. Never Call External APIs Inside a Retryable Transaction

Even when a Spring transaction cleanly rolls back the DB, an HTTP request already sent to another service cannot unsend itself. Write an outbox event inside the transaction, deliver it after commit, and pair it with receiver idempotency.

### 26.6. JPA/Hibernate Persistence Context

After a transaction failure, the persistence context/`EntityManager` may be left in an invalid state. Proper retry creates a fresh transaction and persistence context scope rather than continuing with cached entities from a rolled-back attempt.

## 27. Backoff, Jitter, and Retry Budgets

Simultaneous retries across hundreds of workers can push an already heavily loaded database **deeper into overload**. Retry policies must therefore pace intensity.

### 27.1. Exponential Backoff

A reference formula:

\[
\text{baseDelay}(n) = \min(D_{\max},D_0\cdot 2^{n-1})
\]

For example, with `D0 = 100ms` and `Dmax = 800ms`:

| Failed Attempt | Base Delay Before Next Attempt |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |

These values are **illustrative only**. Retry counts must be bounded and stay within the request deadline.

### 27.2. Jitter

If 500 clients receive `40P01` simultaneously and all sleep exactly 100 ms, they will collide again in lockstep. Jitter adds a bounded random component:

\[
\text{delay}=\min(D_{\max},D_0\cdot 2^{n-1})+\text{jitter}
\]

Some strategies use full jitter sampled uniformly between 0 and the base delay. No single formula fits every workload; tune according to resources and SLAs.

### 27.3. Per-Request Retry Budget

Suppose an API has a 2-second overall deadline and each attempt can take 1.5 seconds. You cannot try 5 times with 100–800 ms sleeps and still meet the deadline. Allocate budget across:

- Connection acquisition time.
- Query execution and lock wait time.
- `COMMIT` duration.
- Backoff sleep.
- Reconciliation if commit outcome is unknown.

### 27.4. Retry Storms

`53300 too_many_connections` happens when connection slots run out. If every client immediately opens new connections and retries continuously, the outage worsens. Limit pools, queue work, enforce admission control, add backoff/jitter, and trigger infrastructure alerts.

### 27.5. Do Not Retry After User Cancellation

Once the request context is canceled or the deadline has expired, scheduled retries should halt unless the business workflow is a durable background job explicitly decoupled from the HTTP request. Never turn a user's Cancel click into three extra DB attempts.

### 27.6. Circuit Breakers and Bulkheads

During prolonged outages or overload, circuit breakers can temporarily fail fast on non-essential traffic, bulkheads isolate concurrency, and job queues reprioritize work. These are **application/system-level safeguards**, not substitutes for transaction design and idempotency.

## 28. Timeouts: Clarity Across Every Layer

| Layer | Example | Key Reminder |
| --- | --- | --- |
| HTTP | API request deadline | Can expire before or right as DB commits. |
| Connection pool | Acquisition timeout | Whether a connection was acquired is unknown/not obtained; no new SQL was sent by this request yet. |
| Network/socket | Read timeout/reset | Response may drop after a write/`COMMIT`. |
| JDBC | Statement query timeout | Can issue a cancel request, yet transaction context still needs cleanup. |
| PostgreSQL | `statement_timeout` | Can raise `57014` and abort the transaction. |
| PostgreSQL | `lock_timeout` | Can raise `55P03` while waiting for a lock. |
| PostgreSQL | `idle_in_transaction_session_timeout` | Can terminate the connection if idle too long inside a transaction. |

### 28.1. Per-Transaction Timeout Example

```sql
BEGIN;

SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '500ms';

SELECT account_id, balance
FROM retry_lab.accounts
WHERE account_id = 1;

COMMIT;
```

`SET LOCAL` applies only to the current transaction, avoiding leaking session settings to subsequent requests when the connection returns to the pool.

### 28.2. Never Infer SQLSTATE from the HTTP Layer

An HTTP timeout can occur while the DB is still running or has just committed. An HTTP 504 does not prove PostgreSQL executed `ROLLBACK`. When the application cannot confirm the result, preserve the operation ID for recovery.

### 28.3. Async Execution and Lingering Side Effects

In some setups, the client gives up while the backend query has not yet stopped. Never spawn a second job for the same business operation under a new key simply because the HTTP client stopped waiting.

### 28.4. Cancellation Has Business Semantics

If a user cancels an **uncommitted** step, rollback works. Once a transaction has committed, “cancellation” is a separate **compensating operation** (such as a refund), not simply erasing database history.

## 29. Connection/Setup Errors and Resource Exhaustion

### 29.1. Unable to Establish Connection

`08001`, `08004`, and `57P03` can happen before a new request begins DML. Retrying **establishing the connection** with backoff can be sensible, especially during server restarts. However, if an earlier attempt left an unknown `COMMIT`, never transition from “retry connect” into “replay payment under a new ID.”

### 29.2. Authentication/Authorization

A wrong password or missing privilege rarely disappears after 200 ms. `28P01` or `42501` requires fixing credentials, `GRANT`s, or configuration. Tight retry loops flood logs and can trigger account lockout protections.

### 29.3. Too Many Connections

`53300` signals exhausted connection slots. Raising pool sizes across all app instances simultaneously only makes it worse. Check:

- Server `max_connections` and aggregate pool budgets.
- Idle connections and idle-in-transaction sessions.
- Connection leaks.
- PgBouncer where appropriate.
- Workload concurrency and queuing.

### 29.4. Disk Full / Out of Memory

`53100`/`53200` are typically severe resource emergencies; alert operators, free/restore capacity, and prevent retry storms. Never treat them like deadlocks.

### 29.5. Read-Only Transaction

`25006` can result from writing to a read replica or an explicitly read-only transaction. Route writes to the primary endpoint and fix transaction modes and pool routing. Do not infinitely retry writes against a read replica.

### 29.6. Undefined Table/Column

`42P01`/`42703` often come from deploying application code ahead of migrations, a wrong `search_path`, or schema drift. Roll back or run the missing migration and fix version compatibility; do not sleep and retry broken SQL forever.

## 30. Monitoring: Measure Retries Without Hiding Failures

A well-run retry system tracks metrics, not just “attempt 2” text logs.

### 30.1. Suggested Metrics

| Metric | Meaning |
| --- | --- |
| `db_errors_total{sqlstate}` | Errors by SQLSTATE; keep label cardinality bounded. |
| `db_retry_attempts_total{operation,reason}` | Total retry attempts. |
| `db_retry_exhausted_total` | Operations exhausting retry budget. |
| `db_transaction_duration_seconds` | Transaction duration histogram. |
| `db_lock_wait_seconds` | Lock wait time, where measurable. |
| `db_connection_acquire_seconds` | Pool acquisition latency. |
| `idempotency_duplicate_total` | Hits on already-processed request IDs. |
| `idempotency_key_conflict_total` | Hits with same key but mismatched payload. |
| `commit_outcome_unknown_total` | Cases requiring reconciliation. |
| `outbox_lag_seconds` | Delay publishing events out of the DB. |

### 30.2. Structured Log Fields

Log fields such as:

```text
operation_type
request_id / correlation_id (sanitized)
transaction_attempt
sqlstate
error_classification
transaction_stage
retry_decision
backoff_ms
elapsed_ms
result_status
```

Never log raw passwords, full SQL bind parameters containing personal or financial data, or full internal server error details to public channels.

### 30.3. Separate `23505` Business Conflicts from Idempotent Duplicates

These are two distinct counts:

- `business_conflict`: a user submitted an existing SKU or email because the resource genuinely collides.
- `duplicate_request`: the same logical operation was already processed, so the prior outcome is returned.

Lumping both into “SQLSTATE 23505 count” obscures retry design bugs or misclassifies normal client resends as system errors.

### 30.4. Track Retry Success Ratios

Measure attempts and operations succeeding after retry. If most transactions need 3–4 attempts, that warns of broken lock ordering, flawed isolation design, or excessive contention—even if the API eventually returns success.

### 30.5. Alert on Stuck Unknown Outcomes

Operations sitting in “verification pending” for too long represent high business risk. Put bounded reconciliation workers, alerts, and support runbooks in place rather than relying on clients resending forever.

## 31. PL/pgSQL: Catching SQLSTATE and Preserving Root Errors

When debugging procedural logic, PostgreSQL provides `SQLSTATE` and `GET STACKED DIAGNOSTICS` inside `EXCEPTION` blocks.

### 31.1. Lab Example: Catching Unique Violations

```sql
DO $$
DECLARE
    v_state text;
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO retry_lab.sample_items (
            item_id, sku, quantity
        )
        VALUES (99, 'SKU-A', 5);
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE
            'Caught SQLSTATE %, constraint %',
            v_state, v_constraint;
    END;
END;
$$;
```

The `INSERT` intentionally collides on `sku='SKU-A'`, so the handler catches `23505`; structured metadata is captured without parsing message text.

### 31.2. Exception Blocks Have Overhead

PL/pgSQL `BEGIN ... EXCEPTION` blocks use subtransactions to isolate errors. That works well for occasional expected exceptions, yet looping millions of rows with an exception block per row incurs substantial overhead. For duplicate handling in bulk, `ON CONFLICT` or set-based staging validation is usually far better.

### 31.3. Never Swallow Errors and Report Success

Dangerous example:

```sql
-- Anti-pattern:
-- EXCEPTION WHEN OTHERS THEN
--     NULL;
```

The application may believe the transaction succeeded while a vital step failed. If converting an error to a business outcome, **record the state explicitly** and ensure prior side effects roll back or commit strictly per contract.

### 31.4. Custom `RAISE` SQLSTATEs

PL/pgSQL supports `RAISE EXCEPTION USING ERRCODE = ...`. If using custom SQLSTATEs for domain errors, document the registry, avoid colliding with built-in codes, and never lump custom errors into transient DB retries. Usually it is cleaner for the API to carry domain error codes in response payloads while reserving SQLSTATE for database-layer classification.

## 32. Real-World Case Studies

### 32.1. Case A: API Creates Duplicate Orders After Client Timeout

**Context:** A user clicks “Place Order,” the server commits, and the response drops. The browser automatically resends the POST.

**Wrong:** The second request generates a new order ID and inserts another order despite an identical payload.

**Better:** The client retains the `Idempotency-Key` generated on the first attempt. The backend persists `order_requests(tenant_id, request_key, payload_hash, order_id, status)` under a unique constraint, commits atomically with the order, and on key collision verifies payload equality before returning the existing order ID.

**What to test:** two requests with the same key arriving **concurrently**, connection drop right at `COMMIT`, and key reuse with a different payload.

### 32.2. Case B: Opposing Transfers Causing Deadlock

**Context:** Transaction A transfers 1→2 while Transaction B transfers 2→1; each updates two accounts in opposite lock order.

**Symptom:** One transaction receives `40P01`.

**Fix:** Lock accounts in **consistent ID order** before updating; keep transactions brief; retry the whole transaction with a fixed request ID and backoff. Never rerun only the credit statement if the previous attempt's debit rolled back.

### 32.3. Case C: Read-Write Serialization Failure

**Context:** Two `SERIALIZABLE` transactions read overlapping sets and update related rows.

**Symptom:** `40001` at `UPDATE` or `COMMIT`.

**Fix:** Start a new transaction, re-read predicates/aggregates, and recompute the decision. Never retry just `COMMIT`. Contention can sometimes be reduced with atomic single-statement updates, better indexes, or appropriate isolation choices per contract; yet whenever `SERIALIZABLE` is used, retries remain mandatory.

### 32.4. Case D: Canceled Report

**Context:** User clicks Cancel while an analytics query runs; the driver receives `57014`.

**Wrong:** Retry middleware treats every `57xxx` code as transient and restarts the report after cancellation.

**Right:** Track cancellation source and request deadline. If user-canceled, stop work. If `statement_timeout`, inspect query plan/resources and retry only when justified and within budget.

### 32.5. Case E: `23505` During Account Registration

**Context:** Email already exists under a unique constraint.

**Wrong:** Retry `INSERT` 5 times thinking “unique could be a race.”

**Right:** Clarify whether email is unique globally or per tenant; return a clean conflict or guide sign-in/account linking per contract. If the duplicate comes from the **same idempotent signup request**, look up status by idempotency key instead of creating a second account.

### 32.6. Case F: Application Deployed Before Migration

**Context:** New code queries `new_status` before the DB column exists.

**Symptom:** `42703`.

**Wrong:** Retry every 50 ms across 10,000 requests.

**Right:** Fix rollout/migration ordering, maintain a compatibility window, fail fast, alert, and avoid hammering the DB uselessly.

### 32.7. Case G: Too Many Connections

**Context:** Each instance runs a 100-connection pool and autoscales from 5 to 50 instances; PostgreSQL saturates.

**Symptom:** `53300`.

**Right:** Calculate aggregate pool budgets, cap connections per instance, introduce a connection pooler if appropriate, limit concurrency, apply backoff, and alert. Never reflexively raise pool sizes across instances.

### 32.8. Case H: Outbox Worker Delivers Event Twice

**Context:** Broker received event K, then the worker crashed before updating `published_at`.

**Symptom:** Restarted worker republishes event K.

**Right:** Consumer deduplicates by event ID or operation key persisted atomically alongside its side effects. An outbox avoids losing events inside the DB transaction, not duplicate downstream delivery.

### 32.9. Case I: “Failure” Caused by Lost `COMMIT` Response

**Context:** Transfer committed, then JDBC hit a socket timeout awaiting response.

**Wrong:** Generate a new UUID and debit again.

**Right:** Keep the original UUID, query `transfer_requests` from an authoritative primary source, compare payload, and return the prior terminal result. If still absent/uncertain, replay under the **same key** via the atomic `UNIQUE` protocol after backoff—never declare guaranteed failure.

### 32.10. Case J: Preventing Negative Balances Under `READ COMMITTED`

**Context:** Two distinct request IDs debit the same account concurrently.

**Wrong:** Both read balance first via `SELECT` and then issue `SET balance = balance - amount` without a predicate check in the `UPDATE`, risking overdraws or broken invariants if constraints are weak.

**Right:** Use a conditional `UPDATE`:

```sql
UPDATE retry_lab.accounts
SET balance = balance - 700
WHERE account_id = 1
  AND balance >= 700
RETURNING balance;
```

Row-level locking and the `WHERE` predicate inside `UPDATE` stop concurrent transactions from overdrawing under this pattern, reinforced by `CHECK (balance >= 0)` as a database safety barrier. If `UPDATE` returns 0 rows, treat it as a **business rejection**, not an SQL error to retry automatically.

## 33. Common Retry Design Mistakes

### 33.1. Retrying Every `SQLException`

Causes futile loops on bad inputs (`22P02`), missing privileges (`42501`), missing objects (`42P01`), and unique conflicts (`23505`).

### 33.2. Retrying Inside an Already Failed Transaction

After `40001`, `40P01`, or other SQL errors, the transaction must roll back. Re-issuing SQL on a `25P02`-aborted connection accomplishes nothing.

### 33.3. Retrying Only the Last Statement of a Transaction

Decisions based on earlier `SELECT`s may be stale. For serialization failures and deadlocks, re-run the entire transaction's logic.

### 33.4. Generating a New Request ID per Attempt

Turns one logical request into multiple operations. On an unknown outcome, a new key causes double debits or duplicate orders.

### 33.5. Assuming Connection Failure Equals Rollback

`COMMIT` may have finished while its response vanished. Reconcile instead.

### 33.6. Assuming `rollback()` Succeeding Proves Commit Failed

Rolling back on a different or broken connection cannot undo an already durable `COMMIT`.

### 33.7. Replacing a Unique Constraint with `SELECT COUNT(*)` Before `INSERT`

Two concurrent requests can both observe `COUNT = 0`. A database `UNIQUE`/`PRIMARY KEY` constraint is mandatory.

### 33.8. Using `ON CONFLICT DO NOTHING` and Blindly Returning Success

Inserting zero new rows does not guarantee the existing record shares the same payload or succeeded. Always read and verify.

### 33.9. Not Recording Terminal Status in the Same Transaction

If a debit commits first and the status marker commits separately, a crash between them leaves hard-to-reconcile state. Atomic transactions keep business effects and markers aligned.

### 33.10. Committing a `processing` Marker Separately Without Recovery

If the worker dies, the key remains wedged indefinitely. Multi-phase workflows require explicit leases, retries, and state transitions.

### 33.11. Unlimited Attempts or Missing Deadlines

Unbounded retries amplify load, breach SLAs, and prolong outages.

### 33.12. Identical Fixed Backoff Across All Clients

Synchronized retries create thundering herds; add jitter and admission control.

### 33.13. Retrying `57014` After User Cancellation

Violates user intent and wastes capacity. Distinguish cancellation from timeouts.

### 33.14. Assuming Every `55P03` Should Wait and Retry

An API with a 200 ms deadline should fail fast as busy rather than blocking for seconds.

### 33.15. Returning a Failed Connection to the Pool Without Rollback

Leaving a session in a failed transaction causes `25P02` on the next request. Frameworks and pools must clean up transaction state cleanly.

### 33.16. Sending Emails or Calling Payment Gateways Inside a Retryable Transaction

DB rollbacks do not undo external side effects; retries duplicate notifications or charges. Use an outbox or provider idempotency keys.

### 33.17. Believing an Outbox Alone Guarantees Exactly-Once Broker Delivery

A worker crash between publishing and marking `published_at` still causes redelivery. Consumers and providers must be idempotent.

### 33.18. Looking Up Status on a Lagging Replica

Not seeing a result row on a replica does not prove the primary transaction failed. Reconcile against an appropriately consistent source.

### 33.19. Parsing Messages Instead of Reading SQLSTATE

Error wording varies by locale, driver, and major version, breaking classifiers. Rely on SQLSTATE and structured metadata.

### 33.20. Omitting Request IDs from Logs

Makes it impossible to correlate attempts, spot duplicates, or investigate unknown commits. Log safe correlation IDs without sensitive payment details.

### 33.21. “Fixing” Resource Errors by Increasing Concurrency

`53300`/`53200` worsen when clients pile on concurrent retries. Shed load and fix capacity first.

### 33.22. Using Current Account Balance as Proof of a Past Transaction

Balances change from unrelated transfers and never prove operation K executed. Inspect the **request marker and ledger by ID**.

### 33.23. Not Rejecting Same-Key, Different-Payload Requests

A client bug or attacker reusing key K with a different amount could receive a response belonging to an unrelated operation. Verify payload consistency after authenticating tenant/owner.

### 33.24. Confusing Guaranteed Rollback with Unknown Outcome

Server-returned `40001` guarantees transaction rollback per error semantics; a socket drop during `COMMIT` does not. Keep their handling branches distinct.

### 33.25. Failing to Test Race Conditions

Sequential integration tests miss concurrent same-key races. Test real concurrency and inject faults around commit/response boundaries.

## 34. Practice Exercises

Unless noted as Java/API scenarios, exercises use the `retry_lab` schema from Section 7. Never run deadlock demos or interrupt commits in production. If using SQL that modifies data, manage transactions/rollbacks or use a separate lab database so starting data remains intact for later exercises.

### Exercise 1. SQLSTATE Structure

In `23505`, what is the class and what is the condition? Why shouldn't SQLSTATE be stored in an `integer` column?

### Exercise 2. Two Different Classes

Compare classes `23` and `40` in meaning, give common example codes, and describe how to react to each.

### Exercise 3. Classifying `UNIQUE`

An `INSERT` for an already-existing SKU raises `23505`. Should you retry the `INSERT` 5 times with identical data? When can `23505` represent a duplicate idempotent request?

### Exercise 4. Foreign Key

An `INSERT` into transfers uses `from_account = 999`, which has no parent account. What SQLSTATE is expected? Is it automatically retryable?

### Exercise 5. Numeric Conversion

What SQLSTATE does `SELECT 'abc'::integer` raise? How do you fix it?

### Exercise 6. CHECK Constraint

`UPDATE sample_items SET quantity = -1` violates CHECK. What error name and code occur? Why doesn't backoff help?

### Exercise 7. Failed Transaction

After an `INSERT` raises `23505` inside `BEGIN`, the next `SELECT` returns `25P02`. What must you do before continuing?

### Exercise 8. `SAVEPOINT`

Write a transaction using a savepoint to attempt inserting a duplicate SKU, roll back to the savepoint on error, and then run another `SELECT`.

### Exercise 9. `40001`

When receiving `40001`, should you retry only the final SQL statement or the entire transaction? Why?

### Exercise 10. Deadlock

Two sessions update IDs 1→2 and 2→1 in reverse order. Which SQLSTATE can occur, and how do you reduce deadlocks beyond retrying?

### Exercise 11. `NOWAIT`

Session A holds `FOR UPDATE` on row 1; Session B runs `FOR UPDATE NOWAIT`. What error code can occur? Should it retry in an infinite tight loop?

### Exercise 12. `statement_timeout`

A session executes `SET LOCAL statement_timeout = '1s'` and `SELECT pg_sleep(2)`. Which SQLSTATE is returned, and what must happen to the transaction?

### Exercise 13. User Cancel

`57014` occurs because a user clicked Cancel. Is retry middleware automatically re-running the query right or wrong?

### Exercise 14. Connection Failure Before `BEGIN`

The application has sent no DML yet and fails to get a connection (class `08`). Which step may be retried, and what limits still apply?

### Exercise 15. Lost `COMMIT` Response

The app sent `COMMIT` and the socket closed. Can you conclude the transaction rolled back? What is the right recovery path?

### Exercise 16. JDBC Check

Write a Java expression checking an `SQLException` for `40001` or `40P01` without risking a `NullPointerException`.

### Exercise 17. Message Parsing

Why is `e.getMessage().contains("deadlock detected")` an unreliable classifier?

### Exercise 18. Retry Budget

An HTTP request has a 2-second deadline. Why can three attempts with 1-second timeouts each plus 100/200 ms backoffs breach the SLA?

### Exercise 19. Jitter

What problem does jitter solve when 500 clients hit deadlock simultaneously and back off?

### Exercise 20. Spring `@Transactional`

Why does catching `40001` and retrying `UPDATE` inside the same `@Transactional` method risk `25P02`? Where must the retry sit?

### Exercise 21. Debit Row Count

In the transfer pattern, `UPDATE accounts ... WHERE balance >= amount RETURNING` returns 0 rows. Is this `40001`? What should happen?

### Exercise 22. Idempotency Key

A client sends the same transfer command twice because the response dropped. What design guarantees the debit happens only once?

### Exercise 23. Same Key, Different Payload

Original Request K transfers 100 from 1→2. A later request reuses K to transfer 900 from 1→3. How must the system respond?

### Exercise 24. `ON CONFLICT DO NOTHING`

`INSERT ... ON CONFLICT (request_id) DO NOTHING RETURNING request_id` returns 0 rows. May execution continue to debit/credit? Why or why not?

### Exercise 25. Two Clients Contending on the Same Key

Two concurrent transactions insert the same unique UUID while one has not yet committed. How does the unique constraint prevent duplicate processing?

### Exercise 26. `READ COMMITTED` Visibility

Why doesn't `DO NOTHING RETURNING 0` guarantee the conflicting row is immediately visible within the same statement's snapshot?

### Exercise 27. Atomic Marker Persistence

Why should the marker, ledger, debit, credit, and terminal status commit inside one transaction in the lab design?

### Exercise 28. Insufficient Funds

A transfer records `insufficient_funds` and commits the rejection. If the user deposits more money and tries again intentionally, should they reuse the old request key or issue a new one?

### Exercise 29. Outbox

Why shouldn't HTTP notifications be sent directly between `BEGIN` and `COMMIT` of a retryable transaction?

### Exercise 30. Duplicate Event Delivery

An outbox worker sends an event successfully but crashes before updating `published_at`. After restart, what prevents duplicate effects at the receiver?

### Exercise 31. Replica Lag

After an unknown commit outcome, the API checks the request ID on a replica and sees no row. Can it infer the transfer rolled back?

### Exercise 32. Resource SQLSTATE

How does `53300` differ from `23505`? Why is raising pool sizes and having clients retry aggressively a bad response to `53300`?

### Exercise 33. Read-Only Error

An app connects to a replica, attempts an `UPDATE`, and gets `25006`. What needs fixing?

### Exercise 34. Schema Migration

`42P01` and `42703` appear right after deploying a new app version. Name common causes and the right response.

### Exercise 35. PL/pgSQL Diagnostics

Inside `EXCEPTION WHEN unique_violation`, what command retrieves the SQLSTATE and constraint name?

### Exercise 36. Counting Deadlocks

Write SQL to view cumulative deadlocks for the current database from statistics catalogs, and state a limitation of that metric.

### Exercise 37. Effectively-Once

“I use an outbox, so the broker and every consumer will receive each event exactly once”—is this claim true? Why or why not?

### Exercise 38. `SELECT FOR UPDATE SKIP LOCKED`

How does `SKIP LOCKED` help a job queue, and why is it not by itself an end-to-end exactly-once guarantee?

### Exercise 39. Test Suite Design

Propose at least eight test cases for the transfer service covering errors, retries, idempotency, and unknown commit outcomes.

### Exercise 40. End-to-End Architecture

An order-creation API uses PostgreSQL via Spring/JDBC, receives a client request ID, and must send an email after saving the order. Design the transaction, SQLSTATE policy, retry boundary, idempotency, outbox, and recovery path when the `COMMIT` response drops.

## 35. Suggested Solutions

### Answer 1. Structure

`23505` has class `23` (integrity constraint violation) and condition `505` (`unique_violation` within that class). Codes can contain letters such as `40P01` or `22P02`, so store and compare them as **5-character strings**, never integers.

### Answer 2. Constraints vs. Transaction Rollbacks

Class `23` signals constraint violations: `23505` unique, `23503` foreign key, `23514` CHECK—typically requiring input/schema fixes or business conflict handling. Class `40` signals transaction rollbacks: `40001` serialization failure and `40P01` deadlock can usually be retried as a **whole transaction** after rollback.

### Answer 3. Do Not Blindly Retry `UNIQUE`

No. If the SKU legitimately exists under the unique constraint, inserting 5 more times still collides. If the duplicate comes from **retrying an already processed `request_id`**, look up the stored result and verify payload match, or use `ON CONFLICT` per business semantics. Never treat `23505` as a transient network glitch.

### Answer 4. Foreign Key

`23503 foreign_key_violation`. Usually requires correcting `account_id` or ensuring the parent exists beforehand—do not auto-retry. Only retry if part of an explicitly designed async dependency protocol (waiting for a parent known to arrive shortly) with clear deadlines and budgets.

### Answer 5. Invalid Cast

`22P02 invalid_text_representation`. Validate/cast inputs cleanly or fix Java/SQL type mapping. Retrying the string `'abc'` achieves nothing.

### Answer 6. CHECK

`23514 check_violation`. `quantity = -1` violates `CHECK (quantity >= 0)`; sleeping and backing off will never alter the constraint.

### Answer 7. Failed Transaction

You must `ROLLBACK` the full transaction or `ROLLBACK TO SAVEPOINT` created before the failure. Do not keep issuing `SELECT`/`UPDATE` on an aborted transaction; `25P02` is merely a symptom, so log the original `23505`.

### Answer 8. `SAVEPOINT`

```sql
BEGIN;

SAVEPOINT sp_before_insert;

-- Uncomment to trigger expected 23505 error:
-- INSERT INTO retry_lab.sample_items
-- (item_id,sku,quantity)
-- VALUES (88,'SKU-A',10);

-- After duplicate error, roll back the subtransaction:
ROLLBACK TO SAVEPOINT sp_before_insert;

SELECT COUNT(*) FROM retry_lab.sample_items;

COMMIT;
```

With the `INSERT` commented out, the script runs cleanly and rolls back to the savepoint without changing data; uncomment when testing the error. In app code, catch the error and roll back to the savepoint; for simple duplicate-skip cases, `ON CONFLICT` is usually cleaner.

### Answer 9. Retrying `40001`

Retry the **entire transaction** after rollback: re-read data, recompute business rules, execute DML, and `COMMIT`. Retrying only the last `UPDATE` risks acting on decisions made from a stale snapshot.

### Answer 10. Deadlock

`40P01 deadlock_detected`. Reduce deadlocks via **consistent lock ordering** (e.g., always locking the lower account ID first), keeping transactions brief, and avoiding external API waits inside transactions. If one still happens, roll back and retry the entire transaction within budget.

### Answer 11. `NOWAIT`

Typically `55P03 lock_not_available`. Never spin in an infinite retry loop. You may back off with jitter and retry if the SLA permits, or fail fast as busy / pick another work item.

### Answer 12. `statement_timeout`

Usually `57014 query_canceled`. The statement cancels and the transaction enters a failed state; `ROLLBACK` before reusing the connection. Retry only if it was not user-canceled and budget/root cause permit.

### Answer 13. User Cancel

Wrong. Retry middleware must honor user cancellation intent. SQLSTATE `57014` alone is insufficient: inspect cancellation source and request deadline.

### Answer 14. Before Sending DML

You can retry **connecting / acquiring a connection** with bounded attempts, deadlines, and jitter. No new DML side effects occurred yet on that attempt, though you still must avoid retry storms when the DB is overloaded.

### Answer 15. Unknown `COMMIT`

You cannot assume rollback. `COMMIT` may have succeeded while the response dropped. Retain the request ID, reconnect, query result/ledger from a sufficiently consistent source, and if needed retry with the **same business key** through the idempotent `UNIQUE` protocol—never mint a new key.

### Answer 16. JDBC Boolean

```java
String state = exception.getSQLState();
boolean retryWholeTx =
    "40001".equals(state) || "40P01".equals(state);
```

`"constant".equals(state)` is null-safe. The caller must still roll back and open a **fresh transaction**, not simply repeat the statement.

### Answer 17. Message Parsing

Messages vary with locale, driver/proxy, server version, constraint details, and exception wrapping. SQLSTATE is structured for machines. If constraint names are needed, inspect pgJDBC's structured server error metadata when present instead of parsing prose.

### Answer 18. Deadline

Three 1-second timeouts alone can take roughly 3 seconds before counting backoff, connect, and commit time—already breaking a 2-second deadline. Policies must check **remaining total deadline** before starting another attempt.

### Answer 19. Jitter

Prevents clients from retrying in synchronized waves that trigger recurring lock contention and connection spikes after shared failures. Jitter spreads attempts out alongside exponential backoff and a retry budget.

### Answer 20. Spring Transaction Boundary

`@Transactional` wraps the whole method in one transaction. After `40001`, that transaction is aborted/rollback-only; repeating `UPDATE` inside the same scope either hits `25P02` or still rolls back. Place retries **outside** the transactional proxy or use `TransactionTemplate` so each attempt starts a fresh transaction, watching out for self-invocation and interceptor ordering.

### Answer 21. 0-Row Debit

This is not `40001`. With `WHERE account_id = ... AND balance >= amount`, 0 rows means no target matched the predicate at update time, e.g., insufficient funds. In the lab, the FK ensures the account exists once the marker is inserted; production code should still distinguish missing accounts, insufficient funds, and permission/RLS filtering if applicable. On insufficient funds, save `insufficient_funds`, commit the marker, and **do not credit**.

### Answer 22. Idempotency Requirements

Keep the request key stable, put `PRIMARY KEY (request_id)` on `transfer_requests`, reserve the key atomically, let only the key owner perform debit/credit, and commit terminal status plus ledger in one transaction. Duplicate requests compare payloads and return the saved result without debiting again.

### Answer 23. Same Key, Different Payload

Reject key reuse—for instance, HTTP 409 Idempotency-Key Conflict after authorizing caller/tenant. Do not transfer 900, and do not return the 100 success response as if the two payloads matched.

### Answer 24. `ON CONFLICT` Returns 0 Rows

Do not execute debit/credit. Another attempt already claimed or committed the key (or triggered conflict); exit the write path, query the stored record in an appropriate transaction/snapshot, and compare payload/status. Continuing blindly breaks the `UNIQUE` double-debit protection.

### Answer 25. `UNIQUE` Under Concurrency

The `UNIQUE` index/PK forces concurrent sessions sharing a key to serialize at the database. The second `INSERT` waits for the competing transaction; if the first commits, the second skips via `DO NOTHING` and gets 0 rows; if the first rolls back, the second acquires ownership. Only the owner executes side effects.

### Answer 26. Same-Statement Snapshot

Under `READ COMMITTED`, `INSERT ... ON CONFLICT DO NOTHING` can detect conflicts with rows committed by concurrent transactions that are not yet visible in the current statement's starting snapshot. `DO NOTHING` skips inserting, yet the same statement may not see that row in a `SELECT`. A subsequent `SELECT` statement gets a newer snapshot where the committed row is visible.

### Answer 27. Atomic Commit

Keeping the marker, debit, credit, ledger, and outbox in one transaction prevents crash or rollback states like “debited without recording the result.” On commit, everything becomes durable together; if the response drops, request ID and ledger reconcile cleanly. Committing piecewise requires far more complex recovery workflows.

### Answer 28. Retrying After Insufficient Funds

Use a **new request key** for a new transfer attempt after funding the account, because the old key already finalized as `insufficient_funds` and resending it must replay that stored rejection. Never reuse one key for two distinct business attempts.

### Answer 29. Outbox Instead of In-Transaction External Calls

PostgreSQL can roll back after `40001`/`40P01`, but cannot unsend an email or HTTP call. External calls inside retryable transactions duplicate side effects. Persist outbox events in the DB transaction, deliver externally afterward, and rely on consumer idempotency.

### Answer 30. Duplicate Events

A worker crashing after remote delivery but before setting `published_at` causes retransmission. Consumers/providers need durable deduplication keyed by event ID or `(request_id, event_type)`; consumer work and deduplication markers should share a transaction when updating a DB.

### Answer 31. Replica Lag

No. A lagging replica may not yet have replayed the primary's `COMMIT`. Reconcile against an authoritative source with appropriate consistency (usually the primary) or a consistency-enforced read; never replay under a new key simply because a replica missed the row.

### Answer 32. `53300`

`53300 too_many_connections` is a resource/connection limit error; `23505 unique_violation` is a data constraint error. Expanding pools and retrying aggressively during `53300` worsens saturation. Cap concurrency, fix pool budgets, apply backoff/jitter, and alert.

### Answer 33. `25006`

`25006 read_only_sql_transaction`. Route writes to the primary endpoint and fix read-only transaction settings and pool routing; never infinitely retry writes against a read replica.

### Answer 34. `42P01`/`42703`

`42P01 undefined_table` and `42703 undefined_column` stem from missing or out-of-order migrations, wrong `search_path`, or incompatible app/DB versions. Fix rollout/schema/SQL and fail fast/degrade cleanly instead of retrying broken SQL thousands of times.

### Answer 35. `GET STACKED DIAGNOSTICS`

```sql
GET STACKED DIAGNOSTICS
    v_state = RETURNED_SQLSTATE,
    v_constraint = CONSTRAINT_NAME;
```

Runs inside a PL/pgSQL `EXCEPTION` block with declared variables such as `v_state text` and `v_constraint text`, avoiding text message parsing.

### Answer 36. `pg_stat_database`

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

`deadlocks` is a **cumulative database counter since the last statistics reset**, not a per-request SQLSTATE histogram or a list of active deadlocks. Diagnosing causes requires logs, stack/query context, and dedicated monitoring.

### Answer 37. Outbox Alone Is Not Exactly-Once

False. An outbox prevents losing events when the DB transaction commits, yet a worker can still resend after crashes or network errors before recording acks/status. Delivery is typically at-least-once; receivers must deduplicate idempotently and manage external side effects.

### Answer 38. `SKIP LOCKED`

`FOR UPDATE SKIP LOCKED` lets concurrent workers claim distinct queue rows without blocking on locked rows, boosting throughput. It does not guarantee a message runs once if a worker crashes after causing a side effect before committing completion; durable leases/status, retries, and idempotency are still required.

### Answer 39. Eight-Plus Test Cases

A solid baseline set:

1. `23505` on duplicate business key → returns proper conflict/stored result without blind retry.
2. `23514` on negative amount → rejects input without retry.
3. Two `SERIALIZABLE` transactions triggering `40001` → full transaction retries from a fresh snapshot.
4. Deadlock `40P01` → victim rolls back, bounded retry runs, no half-committed transfer.
5. `55P03` via `NOWAIT` → retries within deadline/backoff or returns busy per SLA.
6. `57014` from user cancel → canceled request is not automatically replayed.
7. Two concurrent requests with the same `request_id` and payload → exactly one debit and ledger row.
8. Same key, different amount → rejected as conflict with no extra debit.
9. Response dropped after successful `COMMIT` → retry with same key returns stored result without double debit.
10. Connection dropped before `COMMIT` → transaction rolls back or outcome unknown; key protocol recovers safely.
11. Outbox worker crash after publish before marking `published_at` → consumer deduplication prevents double side effects.
12. Querying status on a lagging replica → never assumes rollback or mints a new key.

Concurrency races and commit response drops require fault injection or coordinated multi-session test harnesses; sequential single-session tests miss them.

### Answer 40. Order API Design

Reference architecture:

```text
Client:
  POST /orders (Idempotency-Key = K, payload P)
              |
              v
Trusted backend authenticates user/tenant
              |
              v
Retry coordinator (budget + deadline + stable K)
              |
              v
PostgreSQL Transaction:
  INSERT operation K UNIQUE / ON CONFLICT DO NOTHING RETURNING
  if already exists: stop write path, compare payload, return stored result
  if new:
      validate stock/price and concurrency
      INSERT order / conditional UPDATE stock
      INSERT outbox 'order_created' UNIQUE(K,type)
      UPDATE operation K terminal(result/order_id)
  COMMIT
              |
              v
Async outbox worker sends email idempotently
```

SQLSTATE policy:

- `40001`/`40P01`: roll back and retry the **entire transaction** under the same K; each attempt gets a fresh transaction scope.
- `23505`: check which key collided; if K, compare payload/status; if another business key, return domain conflict.
- `23503`/`23514`/`22P02`: validate/fix input; never blindly retry.
- `55P03`/`57014`: evaluate lock/cancel/deadline; never retry infinitely.
- `08xxx` or lost socket at `COMMIT`: **unknown outcome**, never mark definitively failed; look up operation K on an authoritative DB and return the stored result or replay the same K under the idempotent protocol.
- `42P01`/`42501`/`53300`: code/config/resource errors; fix root cause and shed load.

Emails go out asynchronously via an outbox worker outside the transaction with consumer/provider deduplication so crashes never send duplicates. Spring retry interceptors sit **outside the transaction boundary** while avoiding self-invocation/proxy bypasses. Monitor operations with K, SQLSTATE, retry count, commit stage, and outbox lag.

## 36. Pre-Deployment Checklist for PostgreSQL Retries

### 36.1. SQLSTATE Classification

1. Do you read `SQLException.getSQLState()` instead of parsing message text?
2. Are SQLSTATEs stored and compared as 5-character strings?
3. Are `null` or malformed SQLSTATE values handled safely?
4. Do you distinguish `40001`, `40P01`, `55P03`, `57014`, and class `08`?
5. Do you avoid automatically retrying `23505`/`23503`/`23514` and `22P02` without business justification?
6. Do you separate configuration errors (`42P01`/`42703`/`42501`) from transient conflicts?
7. Do you preserve the original SQLSTATE preceding trailing `25P02` errors?
8. Do you use structured metadata/constraint names where needed without exposing sensitive values?

### 36.2. Transaction Boundaries

9. Does every `40001`/`40P01` attempt start a fresh transaction and snapshot?
10. Does retry rerun **all `SELECT`s, checks, and business decisions**?
11. Are connections/transactions rolled back and closed cleanly on exceptions?
12. In Spring, does retry wrapping sit **outside** the transactional proxy/`TransactionTemplate`?
13. Do you avoid self-invocation and swallowed exceptions that skip rollback?
14. Are overall deadlines, `statement_timeout`, and `lock_timeout` coordinated together?
15. Do you avoid calling external APIs or sending emails inside rollbackable DB attempts?
16. Have you verified retried statements preserve business invariants under concurrency?

### 36.3. Retry Policy

17. Are max attempts, deadlines, backoff, and jitter configured?
18. Are concurrent retries throttled when the DB is overloaded?
19. Do retries halt upon user cancellation or expired request deadlines?
20. Do resource errors like `53300`/`53100` trigger alerts and overload responses?
21. Are `40001`/`40P01` rates and retry exhaustion measured?
22. Do you avoid sleeping inside a transaction holding locks?
23. Do you have protections against retry storms after outages or failovers?

### 36.4. Idempotency

24. Do business requests carry a key stable **across HTTP, client, and DB attempts**?
25. Is uniqueness enforced in the **database**, rather than relying solely on `SELECT`-before-`INSERT`?
26. Is the key scoped properly by tenant, user, or domain?
27. Are requests with the same key and different payloads rejected?
28. Do duplicate keys return the **stored terminal result** without reapplying side effects?
29. Does the result marker commit atomically alongside business DML?
30. Are transfers, inventory, and balances updated with safe predicates and constraints?
31. If a key is missing right after a connection failure, does recovery reconcile rather than generate a new key?
32. Have you tested **two concurrent requests sharing the same key**?
33. Do you avoid inferring success from sequence gaps or current balances?

### 36.5. Unknown Outcomes and Side Effects

34. Does the system explicitly model **COMMIT outcome unknown**?
35. Are results read from an authoritative consistent source instead of a lagging replica?
36. When a `COMMIT` response drops, is the client guided to retry with the **same key** or poll status?
37. Are pending-verification operations persisted and reconciled within bounds?
38. Are outbox events written in the same transaction as business updates?
39. Does the outbox worker implement retries, leases, timeouts, and downstream deduplication?
40. Are business commit status and notification delivery status tracked separately?
41. Have you tested worker crashes after external publish before marking delivered?
42. Are RPO and consistency implications understood across failovers?

### 36.6. Observability and Testing

43. Do logs capture operation ID, SQLSTATE, attempt, stage, duration, and retry decision?
44. Do metrics separate idempotent duplicates from business unique conflicts?
45. Do you have fault-injection tests for `40001`, `40P01`, `55P03`, and `57014`?
46. Do you test connection resets before/after `COMMIT` and response drops?
47. Do integration tests exercise real pools, proxies, and Spring transaction boundaries?
48. Do you test same-key mismatches in amount or tenant?
49. Do you test retry exhaustion against HTTP/job contracts?
50. Are runbooks documented for deadlocks, pool saturation, and unresolved operations?

## 37. Production Runbook for Spikes in Retry Errors

### Step 1. Identify SQLSTATEs and Transaction Stages

From structured logs, categorize:

- `40001`/`40P01`: transaction conflicts.
- `55P03`: lock unavailable.
- `57014`: timeouts/cancellations.
- `08xxx`/network: broken connections / ambiguous outcomes.
- `23505`/`23503`: data/constraints.
- `53300`: too many connections.

Never enable blanket auto-retries simply because 5xx rates rose.

### Step 2. Check Retry Counts and Total Duration

Verify whether single requests are running 4–5 attempts and saturating request threads or connection pools. Temporarily throttle concurrency or trim retry budgets to stabilize the database.

### Step 3. For Deadlocks/Lock Contention: Inspect Blockers

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY xact_start NULLS LAST;
```

Ensure appropriate monitoring privileges. Never kill a backend based on a single metric; check what the transaction is doing, whether it is already rolling back or committing, and its blast radius on other users.

### Step 4. For Pool/Connection Errors: Shed Load First

Inspect cluster-wide pool sizes, active/idle counts, `max_connections`, leaks, and database restarts/failovers. On `53300`, adding connections or unlimited retries makes saturation worse.

### Step 5. For Unknown Outcomes: Prioritize Reconciliation

Find request IDs logged as “commit started; response lost” with no confirmed terminal state. Query request/ledger rows from the authoritative store and either return the saved result or replay with the **same key** per protocol. Never manually adjust balances before reconciling ledger and idempotency records.

### Step 6. For `23505`: Separate Duplicate Requests

Check constraint names and operation types: is it a genuine business-key collision, or an idempotency marker hit from a client resend? Both require different responses. Never increase `23505` retry counts blindly without finding root cause.

### Step 7. Remediate Safely

Fix lock ordering, indexes, isolation/transaction scope, idempotency protocols, or retry policy based on the root cause. Roll out via canary/load tests and watch SQLSTATE distributions and alerts rather than raising timeouts to mask bottlenecks.

## 38. Quick Reference

| Situation | Do Not | Do Instead |
| --- | --- | --- |
| `40001` | Retry one `UPDATE` in an aborted transaction. | Roll back and retry the entire transaction. |
| `40P01` | Merely raise timeouts without fixing lock order. | Retry whole transaction; fix lock ordering at source. |
| `55P03` | Spin-loop retries forever. | Apply backoff/deadline or return busy. |
| `57014` | Auto-retry after user Cancel. | Check cancellation source and SLA. |
| `23505` | Assume every duplicate is transient. | Handle business conflict or idempotency lookup. |
| `23503` | Infinitely retry missing parents. | Validate FKs/dependencies. |
| `25P02` | Keep sending SQL inside an aborted transaction. | Roll back or roll back to savepoint. |
| `08xxx` at `COMMIT` | Assume rollback occurred. | Unknown outcome → reconcile by request ID. |
| `53300` | Raise pool sizes across all instances. | Reduce concurrency; fix pool budget. |
| `42P01`/`42703` | Retry hoping schema appears by luck. | Fix migration/schema. |
| Two duplicate POSTs | Generate a fresh UUID/row on each POST. | Preserve idempotency key and `UNIQUE` result record. |
| Same key, different payload | Ignore differences. | Reject cleanly as key conflict. |
| Outbox duplicate publish | Trust events send only once. | Deduplicate in consumers/providers. |
| Failed SQL transaction | Return unrolled-back connection to pool. | Perform complete transaction cleanup. |
| Replica lacks marker | Assume transfer rolled back. | Query consistent/authoritative source. |
| Retrying multiple times | Use fixed sleep across every worker. | Enforce budgets, backoff, and jitter. |

## 39. Summary

**A safe PostgreSQL retry policy asks not only “can this error be transient?” but also “if re-executed, could this business effect apply a second time?”**

Core principles:

- **SQLSTATE is a 5-character string** with a 2-character class and detailed condition code. Classify by code, never by parsing messages.
- **`40001` and `40P01`** normally require rolling back and retrying the **entire transaction** with consistent inputs and operation ID—not repeating only the failing statement.
- **`23505`, `23503`, `23514`, and `22P02`** are typically business/input/constraint errors; never blindly retry them.
- **`55P03`** may be retried conditionally when locks are busy and deadline allows; **`57014`** requires distinguishing query timeout from user cancellation.
- **`25P02`** is a consequence of an already failed transaction; roll back or use a savepoint rather than running more SQL on it.
- **Class `08`** reflects connection faults; **losing a `COMMIT` response does not prove rollback**. Treat it as an **unknown outcome** requiring reconciliation.
- **Stable idempotency key + `UNIQUE` constraint + atomic result record** prevents double side effects when clients, JDBC, or brokers resend the same logical request.
- **Same key with different payload must be rejected**; `ON CONFLICT DO NOTHING` alone does not guarantee semantic equivalence.
- **Persist markers, ledger rows, and outbox events in the same transaction** so everything commits or rolls back as one unit.
- **Outboxes prevent lost events**, yet consumers must stay idempotent because workers can resend after crashes.
- **Retry budgets, deadlines, backoff, and jitter** prevent retry storms and latency spikes.
- **Spring/JDBC retries must sit outside transaction boundaries**, opening fresh snapshots and persistence contexts per attempt.
- **Test concurrency races and commit-response drops**, not merely single sequential requests.

Rule of thumb:

> **Classify failures by SQLSTATE; retry at the proper transaction boundary; keep one immutable business identifier; and whenever a `COMMIT` outcome is unknown, verify durable state before permitting any new side effect.**

## 40. References

The official documentation below is helpful for further study; match documentation to your PostgreSQL major version:

- [PostgreSQL Error Codes, Appendix A](https://www.postgresql.org/docs/current/errcodes-appendix.html): catalog of SQLSTATE classes, conditions, and specific codes.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `SERIALIZABLE`, serialization failures, and retry requirements.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks, deadlocks, and lock ordering design.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO NOTHING/UPDATE`, `RETURNING`, and uniqueness.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): conditional `UPDATE`, `WHERE`/`RETURNING`, and updated row handling.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html): creating savepoints.
- [ROLLBACK TO SAVEPOINT](https://www.postgresql.org/docs/current/sql-rollback-to.html): subtransaction recovery.
- [Runtime Configuration — Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): `statement_timeout`, `lock_timeout`, and related timeouts.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_stat_database`, `pg_locks`.
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE` and exception patterns.
- [PL/pgSQL Diagnostics](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-EXCEPTION-DIAGNOSTICS): `GET STACKED DIAGNOSTICS`.
- [JDBC SQLException — Java SE API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): `getSQLState`, `getNextException`, and exception metadata.
- [pgJDBC Documentation](https://jdbc.postgresql.org/documentation/): JDBC connections to PostgreSQL and driver errors.
