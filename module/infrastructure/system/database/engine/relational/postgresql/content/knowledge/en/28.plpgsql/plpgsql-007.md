# RAISE, Message Levels, SQLSTATE, and Exception Handling in PL/pgSQL

When writing logic in **PL/pgSQL** in PostgreSQL, the question is not only "how do I execute a calculation successfully?" A function or procedure must also answer: **when data is invalid, a constraint is violated, or the database hits an error, what does the system report, at what severity, how does the application recognize it, and which changes are preserved?**

For example, an ordering feature needs to deduct inventory. If a user orders 15 units when only 8 remain in stock, silently returning 0 or logging a vague message makes it hard for Java code to distinguish "out of stock" from "database outage." Conversely, if an error occurs after several `UPDATE` statements have run, the application must know whether those changes were rolled back.

PostgreSQL provides these primary tools:

- **`RAISE`**: emits messages at levels such as `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING`, and `EXCEPTION`.
- **SQLSTATE**: a five-character SQL status code letting programs identify error categories without depending on message wording.
- **`EXCEPTION WHEN ... THEN`**: catches specific errors inside a PL/pgSQL block, handles expected situations, or rethrows the error.
- **`GET STACKED DIAGNOSTICS`**: retrieves the error code, message, detail, hint, constraint, and context of the caught error.
- **`RAISE;`**: rethrows the original error from an exception handler without constructing a new error that loses the original code and context.

Short example:

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Starting inventory check';

    RAISE EXCEPTION USING
        ERRCODE = 'PZ001',
        MESSAGE = 'Requested quantity exceeds stock',
        DETAIL  = 'Requested 15, available 8',
        HINT    = 'Reduce quantity or wait for restock';
END;
$do$;
```

A `NOTICE` message informs the caller or session. `EXCEPTION` is an actual error: unless caught by an appropriate handler, the statement fails and the transaction is affected under PostgreSQL rules.

**Important:** `RAISE WARNING` does not roll back a transaction. A `WARNING`-level message is a notification, not an exception caught by `EXCEPTION WHEN`. To reject an operation due to a business-rule violation, use `RAISE EXCEPTION` or let a database constraint raise an error.

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **PL/pgSQL**, and covers emitting messages, designing SQLSTATEs, catching and rethrowing exceptions, rollback scope, batch error handling, Java/JDBC integration, and safe application design patterns.

---

## 1. Learning Objectives

After this lesson, you can:

1. Write `RAISE` statements in `DO` blocks, functions, trigger functions, and PL/pgSQL procedures.
2. Distinguish the six levels: `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING`, and `EXCEPTION`.
3. Explain `client_min_messages`, `log_min_messages`, and special handling rules for certain message levels.
4. Use `%` and `%%` placeholders in `RAISE` format literals.
5. Use `RAISE ... USING MESSAGE, DETAIL, HINT, ERRCODE` and related object-metadata fields.
6. Understand the **five-character SQLSTATE** structure, separating error class from specific condition code.
7. Recognize common codes: `23505`, `23503`, `23514`, `23502`, `22012`, `22023`, `40001`, `40P01`, `57014`, and `P0001`.
8. Define custom business error codes without colliding with system errors.
9. Write `BEGIN ... EXCEPTION WHEN ... THEN ... END` and understand the automatic rollback scope of the block.
10. Write handlers by condition name and by `SQLSTATE`.
11. Understand the limits of `WHEN OTHERS`, especially `query_canceled` and `assert_failure`.
12. Read `SQLSTATE`, `SQLERRM`, and `GET STACKED DIAGNOSTICS` inside an exception handler.
13. Rethrow original errors with `RAISE;`, preserving SQLSTATE and context.
14. Understand why an exception handler is not an autonomous transaction and does not auto-`COMMIT` error logs.
15. Distinguish expected business conditions from infrastructure errors that must surface to the application.
16. Design inventory operations to avoid race conditions without replacing every `WHERE` condition with exceptions.
17. Process batch rows using inner exception blocks when appropriate while accounting for subtransaction overhead.
18. Retry deadlocks and serialization failures at the **transaction boundary**.
19. Read `SQLSTATE` from `SQLException.getSQLState()` in Java instead of matching localized error text.
20. Systematically test error paths: success, NULL inputs, constraint violations, missing data, retryable errors, and errors that must not be swallowed.

**Scope:** Modern PostgreSQL with `LANGUAGE plpgsql`. DDL and DML examples in this lesson are strictly for a mutable lab database. Logging settings, role privileges, and driver behaviors may vary by version and deployment configuration.

---

## 2. What Is an Exception in PL/pgSQL?

An **exception** is an error event that interrupts normal execution flow.

Examples that raise errors:

- `INSERT` violating `UNIQUE`.
- `UPDATE` violating `CHECK`.
- `SELECT INTO STRICT` returning 0 rows or more than 1 row.
- Division by zero.
- Invalid data type cast.
- Deadlock or serialization failure.
- An error explicitly raised with `RAISE EXCEPTION`.
- A failing SQL statement inside a function or trigger.

A PL/pgSQL block with `EXCEPTION` can catch matching errors:

```sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Example error raised';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Caught error raised by RAISE';
    END;
END;
$do$;
```

Here:

1. `RAISE EXCEPTION` raises an error with the default code for `RAISE EXCEPTION` when no code is specified.
2. The `WHEN raise_exception` handler catches it.
3. The handler emits a `NOTICE` and finishes normally.
4. The outer block continues after the inner block.

This does not mean every error should be caught. Catching and ignoring a serious failure can report "success" to the application even though the business operation failed.

### 2.1. Messages vs. Exceptions

`RAISE NOTICE` and `RAISE WARNING` do not transfer control to `EXCEPTION WHEN`. They emit diagnostic or informational messages.

`RAISE EXCEPTION` actively raises an error.

### 2.2. SQLSTATE vs. Message Text

A message like `'Invalid quantity'` is for human readers. A code like `PZ002` is for programs to branch on.

**Never build Java error-handling logic by matching human-readable error strings**, because wording or localization may change while the error semantics stay the same.

### 2.3. Exceptions Are Not Normal Return Values

A function returning `INTEGER` might return `0` for a well-defined business outcome. However, if the function cannot fulfill its contract due to missing input or a broken constraint, an exception with a clear SQLSTATE often expresses the failure better.

There is no rule that "every failure must throw": distinguish **expected outcomes representable as data** from **contract-breaking errors**.

---

## 3. Basic RAISE Syntax

Common forms:

```sql
RAISE [level] 'format' [, expression [, ...]]
    [USING option = expression [, ...]];

RAISE [level] condition_name
    [USING option = expression [, ...]];

RAISE [level] SQLSTATE 'sqlstate'
    [USING option = expression [, ...]];

RAISE [level] USING option = expression [, ...];

RAISE;
```

Where:

- `level` is the message severity; if omitted, it defaults to **EXCEPTION**.
- `'format'` is a string literal containing `%` placeholders.
- `condition_name` is a PostgreSQL-recognized error condition name.
- `SQLSTATE 'xxxxx'` specifies the 5-character error code.
- `USING` adds message, detail, hint, error code, or object metadata.
- `RAISE;` with no arguments **rethrows the active exception**, valid only inside an exception handler.

### 3.1. Simple RAISE NOTICE

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Executing task...';
END;
$do$;
```

### 3.2. RAISE WARNING

```sql
DO $do$
BEGIN
    RAISE WARNING 'Loaded data is missing an optional field';
    RAISE NOTICE 'Task still continues';
END;
$do$;
```

`WARNING` reports a noteworthy issue without throwing an exception or stopping the block.

### 3.3. RAISE EXCEPTION

```sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Invalid request';
END;
$do$;
```

This statement fails unless caught by an enclosing handler.

### 3.4. Omitting Level Means EXCEPTION

```sql
RAISE 'Invalid request';
```

is shorthand for raising at `EXCEPTION` level. In team codebases, writing `RAISE EXCEPTION` explicitly is easier to read.

---

## 4. The Six Message Levels

PostgreSQL supports these levels with `RAISE` in PL/pgSQL:

| Level | Primary Role | Automatically Fails Statement? | Typical Usage |
|---|---|---|---|
| `DEBUG` | Detailed debugging info | No | Tracing execution paths when needed |
| `LOG` | Log-targeted info | No | Operational events per logging policy |
| `INFO` | Operational info | No | Reporting step status |
| `NOTICE` | Notable behavioral info | No | Informing interactive users of progress |
| `WARNING` | Warns of a problem and continues | No | Non-fatal data anomalies |
| `EXCEPTION` | Actual error | **Yes**, unless caught | Contract violations / rejection conditions |

### 4.1. DEBUG

```sql
DO $do$
DECLARE
    v_attempt INTEGER := 2;
BEGIN
    RAISE DEBUG 'Current attempt: %', v_attempt;
END;
$do$;
```

`DEBUG` messages may not appear at the client due to filtering settings. Never conclude from a silent client that `RAISE DEBUG` did not execute.

### 4.2. LOG

```sql
DO $do$
BEGIN
    RAISE LOG 'Started periodic aggregation job';
END;
$do$;
```

`LOG` has special level ordering between client and server settings. Do not rely on whether an SQL client displays `LOG` to infer how the server log is configured.

### 4.3. INFO

```sql
DO $do$
BEGIN
    RAISE INFO 'Finished reading input data';
END;
$do$;
```

For client-side reporting, PostgreSQL treats `INFO` specially: `INFO` messages are sent to the client regardless of `client_min_messages`. Thus `INFO` does not behave identically to standard threshold-filtered levels.

### 4.4. NOTICE

```sql
DO $do$
BEGIN
    RAISE NOTICE 'Skipped duplicate record per policy';
END;
$do$;
```

`NOTICE` works well for informing operators in `psql`, migrations, or maintenance scripts. Never emit millions of `NOTICE`s inside a hot OLTP query.

### 4.5. WARNING

```sql
DO $do$
BEGIN
    RAISE WARNING 'Using fallback configuration parameter';
END;
$do$;
```

If the fallback is still valid, `WARNING` makes sense. If missing configuration makes calculations wrong, raise `EXCEPTION` instead of proceeding with fabricated defaults.

### 4.6. EXCEPTION

```sql
DO $do$
DECLARE
    v_quantity INTEGER := -2;
BEGIN
    IF v_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be greater than 0';
    END IF;
END;
$do$;
```

An unhandled `EXCEPTION` puts an open transaction into an aborted state requiring `ROLLBACK` before any further commands can run.

---

## 5. client_min_messages and log_min_messages

Not every `RAISE NOTICE` or `RAISE DEBUG` reaches every client or server log. PostgreSQL filters messages using configuration thresholds.

### 5.1. client_min_messages

This setting controls which message levels are sent to the client according to PostgreSQL's severity ordering.

Inspect the current value:

```sql
SHOW client_min_messages;
```

Test at `WARNING` level inside a lab transaction:

```sql
BEGIN;

SET LOCAL client_min_messages = warning;

DO $do$
BEGIN
    RAISE DEBUG   'DEBUG demo';
    RAISE NOTICE  'NOTICE demo';
    RAISE WARNING 'WARNING demo';
    RAISE INFO    'INFO demo';
END;
$do$;

ROLLBACK;
```

Typically `NOTICE` and `DEBUG` are suppressed at `WARNING` level, while `WARNING` passes through. `INFO` reaches the client due to its special client-delivery rule noted earlier.

**Note:** Exactly which messages appear also depends on the client driver, SQL tool UI, configuration, and PostgreSQL version.

### 5.2. log_min_messages

This setting controls which message levels are written to the server log:

```sql
SHOW log_min_messages;
```

Depending on privileges and setup, ordinary users cannot alter this system setting.

### 5.3. Do Not Confuse the Two Settings

- `client_min_messages`: threshold for messages sent to the session/client.
- `log_min_messages`: threshold for messages written to the server log.
- `log_min_error_statement` and `log_error_verbosity` further govern statement and error-detail logging.

A `NOTICE` may appear in `psql` yet be absent from server logs, or vice versa, depending on configuration.

### 5.4. INFO and LOG Have Special Rules

The relative priority of `INFO` and `LOG` differs between client and server ordering; PostgreSQL applies specific rules. When designing an enterprise logging policy, consult the documentation for your **running server version** and test with your actual log collector.

### 5.5. Message Filtering Must Not Affect Correctness

If `NOTICE`s are suppressed, the function must still behave identically. Never make business control flow depend on whether a client received a `NOTICE`.

### 5.6. Never Use RAISE as Your Sole Audit System

Server logs can be rotated, filtered, or redirected and do not provide transactional durability guarantees. When durable structured auditing is required, use audit tables, event streams, or logging pipelines designed for durability and transaction semantics.

---

## 6. Placeholders in RAISE

PL/pgSQL uses `%` inside `RAISE` format literals to interpolate expressions.

```sql
DO $do$
DECLARE
    v_sku TEXT := 'SKU-100';
    v_requested INTEGER := 12;
    v_available INTEGER := 8;
BEGIN
    RAISE NOTICE
        'SKU %, requested %, available %',
        v_sku,
        v_requested,
        v_available;
END;
$do$;
```

Output looks like:

```text
NOTICE: SKU SKU-100, requested 12, available 8
```

### 6.1. Every % Requires a Matching Expression

```sql
RAISE NOTICE 'Order % has status %', v_order_id, v_status;
```

has two placeholders and two expressions.

A mismatch between placeholder count and expression count is caught by PL/pgSQL when compiling/validating the function.

### 6.2. %% Prints a Literal Percent Sign

```sql
DO $do$
DECLARE
    v_percent INTEGER := 75;
BEGIN
    RAISE NOTICE 'Progress %%%', v_percent;
END;
$do$;
```

`%%%` here consists of one `%` placeholder followed by `%%` for a literal percent sign, producing `"Progress 75%"`.

### 6.3. The Format Must Be a Literal in RAISE Format Syntax

Do not pass a dynamic expression in place of the literal format string in `RAISE`:

```sql
-- Invalid as RAISE format syntax:
-- RAISE NOTICE format('SKU %s', v_sku);
```

To use a dynamically formatted message, write:

```sql
RAISE NOTICE USING
    MESSAGE = format('SKU %s', v_sku);
```

### 6.4. RAISE Format Differs from format()

- In `RAISE '...%', x`, the placeholder is a bare `%`.
- In SQL's `format('...%s...', x)` function, specifiers include `%s`, `%I`, and `%L`.

Do not mix their syntax rules expecting identical formatting.

### 6.5. Beware Logging Sensitive Data in Messages

Never log passwords, tokens, API keys, payment card numbers, or unnecessary personal data via `RAISE`. Messages can surface to clients, server logs, and monitoring tools with varying access scopes.

---

## 7. USING: MESSAGE, DETAIL, and HINT

Raising a structured error:

```sql
DO $do$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'PZ001',
        MESSAGE = 'Cannot fulfill request',
        DETAIL  = 'Requested quantity exceeds available stock',
        HINT    = 'Reduce quantity or retry after restock';
END;
$do$;
```

Available fields:

| Field | Role |
|---|---|
| `MESSAGE` | Concise primary error message |
| `DETAIL` | Specific diagnostic context |
| `HINT` | Actionable suggestion for resolution |
| `ERRCODE` | Five-character SQLSTATE or condition name |
| `SCHEMA` | Related schema name metadata, if applicable |
| `TABLE` | Related table name metadata, if applicable |
| `COLUMN` | Related column name metadata, if applicable |
| `CONSTRAINT` | Related constraint name metadata, if applicable |
| `DATATYPE` | Related data type name metadata, if applicable |

### 7.1. MESSAGE Is Not an Error Code

Applications can render friendlier localized UI messages than the database's message; `SQLSTATE` is the stable channel for error classification.

### 7.2. DETAIL Helps Debugging, but Avoid Data Leaks

For example:

```sql
DETAIL = format(
    'sku=%s, requested=%s, available=%s',
    v_sku, v_requested, v_available
)
```

is helpful when values are non-sensitive and authorized for the caller.

Never dump entire rows, passwords, credentials, or another tenant's data into `DETAIL` merely for "easy debugging."

### 7.3. HINT Is Advisory

```sql
HINT = 'Check the SKU and try again'
```

should guide operators or callers on next steps; never leak secrets such as internal server names in `HINT` to untrusted clients.

### 7.4. Mixing Format Strings and USING

```sql
DO $do$
DECLARE
    v_sku TEXT := 'SKU-100';
BEGIN
    RAISE EXCEPTION 'SKU % cannot be ordered', v_sku
        USING
            ERRCODE = 'PZ002',
            HINT = 'Check product status';
END;
$do$;
```

### 7.5. Do Not Embed SQLSTATE Inside MESSAGE

Never write client parsers like `"if message starts with [PZ002]..."`. Read the dedicated `SQLSTATE` field returned by PostgreSQL and the driver.

---

## 8. What Is SQLSTATE?

**SQLSTATE** is a **five-character** SQL status code used to classify success, warning, and error conditions.

Example:

```text
23505
  ||---
  ||  condition: unique_violation
  |
  +-- class 23: integrity_constraint_violation
```

The first two characters identify the **class**; the remaining three characters identify the specific condition within that class.

### 8.1. Common Codes to Know

| SQLSTATE | PostgreSQL Condition Name | Common Scenario |
|---|---|---|
| `00000` | `successful_completion` | Success |
| `22012` | `division_by_zero` | Division by zero |
| `22023` | `invalid_parameter_value` | Invalid parameter value |
| `23502` | `not_null_violation` | NOT NULL violation |
| `23503` | `foreign_key_violation` | FOREIGN KEY violation |
| `23505` | `unique_violation` | UNIQUE/PRIMARY KEY violation |
| `23514` | `check_violation` | CHECK violation |
| `40001` | `serialization_failure` | Serialization conflict |
| `40P01` | `deadlock_detected` | Deadlock detected |
| `55P03` | `lock_not_available` | Lock unavailable (`NOWAIT`) |
| `57014` | `query_canceled` | Query canceled |
| `P0001` | `raise_exception` | Default `RAISE EXCEPTION` |
| `P0002` | `no_data_found` | 0 rows in `STRICT` context |
| `P0003` | `too_many_rows` | >1 row in `STRICT` context |
| `P0004` | `assert_failure` | `ASSERT` failed |

These codes are far more reliable than error message text, especially in multilingual applications.

### 8.2. SQLSTATE Is Not an HTTP Status Code

`23505` is not HTTP 409, and `PZ001` is not HTTP 400. Your API layer must define how SQLSTATEs map to HTTP statuses and responses according to business rules.

For example, an "out of stock" code might map to HTTP 409 Conflict in one API, but that is an application convention, not a PostgreSQL rule.

### 8.3. Do Not Catch by Class Alone When Precision Matters

Class `23` encompasses NOT NULL, FOREIGN KEY, UNIQUE, and CHECK violations. Catching the whole class and reporting "SKU already exists" can mask an FK or CHECK error.

Use specific condition names or inspect constraint metadata when making logic decisions.

### 8.4. SQLSTATE Is More Stable Than Message Text

Messages can change across PostgreSQL versions, localization settings, or context. PostgreSQL recommends using `SQLSTATE` and metadata fields—not string matching—to identify error types.

---

## 9. Defining Custom Business SQLSTATEs

You can raise a custom SQLSTATE:

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ001',
    MESSAGE = 'Missing SKU';
```

This illustrates an application-defined code. Whenever defining custom codes, maintain a documented error registry.

### 9.1. Code Selection Rules

- Must be **exactly 5 characters**.
- Use digits and uppercase ASCII letters per PostgreSQL SQLSTATE rules.
- Never use `00000` (successful completion) for an error.
- Avoid codes ending in `000` so they are not confused with class-level codes.
- Avoid hijacking standard PostgreSQL codes for unrelated meanings.
- Maintain clear ownership and versioning for custom codes.

Example custom codes under a `PZ` convention:

| Example Code | Business Meaning |
|---|---|
| `PZ001` | Invalid SKU |
| `PZ002` | Invalid quantity |
| `PZ003` | Product not found |
| `PZ004` | Insufficient stock |
| `PZ005` | Input row cannot be applied |
| `PZ006` | Business operation rejected |

These codes are **a convention for this lesson**, not built-in PostgreSQL codes.

### 9.2. When to Use Standard Codes?

If an error is genuinely a natural constraint violation, let the database emit `23505`, `23503`, or `23514` rather than wrapping everything in obscure custom codes.

### 9.3. When to Use Custom Codes?

When business logic needs to distinguish a condition with no clear standard code—such as "insufficient stock"—a custom SQLSTATE with `MESSAGE`/`DETAIL`/`HINT` enables consistent handling in applications.

### 9.4. Do Not Create Too Many Codes per Message Variant

If every phrasing variation gets a new SQLSTATE, you end up with hundreds of unmaintainable codes. Each code should represent **a distinct error category handled differently by consumers**.

---

## 10. Default RAISE EXCEPTION and P0001

When no code is specified via condition name, `SQLSTATE`, or `ERRCODE`:

```sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Example business error';
END;
$do$;
```

raises SQLSTATE **`P0001`** (`raise_exception`).

### 10.1. P0001 Does Not Distinguish Causes

If every function writes:

```sql
RAISE EXCEPTION 'Product not found';
RAISE EXCEPTION 'Insufficient stock';
RAISE EXCEPTION 'Duplicate SKU';
```

then all three default to the same SQLSTATE `P0001`. Applications cannot tell them apart without parsing message text.

### 10.2. Clearer Approach

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ004',
    MESSAGE = 'Insufficient stock';
```

Clients can branch cleanly on `PZ004`.

### 10.3. Do Not Use P0001 for Everything

If the database itself raises `unique_violation`, preserve `23505` and constraint metadata. When raising application-level business errors, use documented custom codes.

### 10.4. P0001 Still Has Its Place

In operational scripts or quick exercises that simply need to abort without fine-grained client branching, default `RAISE EXCEPTION` is fine. Production APIs, however, usually need richer contracts.

---

## 11. Raising by Condition Name and SQLSTATE

You can use a PostgreSQL condition name:

```sql
DO $do$
BEGIN
    RAISE division_by_zero
        USING MESSAGE = 'Cannot perform this division';
END;
$do$;
```

Or specify a code directly:

```sql
DO $do$
BEGIN
    RAISE SQLSTATE '22012'
        USING MESSAGE = 'Denominator must not be 0';
END;
$do$;
```

Both examples raise code `22012` intentionally, which **does not mean an SQL division actually ran**. In logs and metrics, distinguish engine-generated errors from errors raised explicitly by code.

### 11.1. Raising a Custom Code via SQLSTATE

```sql
DO $do$
BEGIN
    RAISE SQLSTATE 'PZ002'
        USING MESSAGE = 'Requested quantity is invalid';
END;
$do$;
```

### 11.2. Raising via ERRCODE

```sql
DO $do$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'PZ002',
        MESSAGE = 'Requested quantity is invalid';
END;
$do$;
```

These syntaxes provide different ways to control the error code.

### 11.3. Do Not Fake unique_violation Out of Habit

If a manual `IF exists(...)` check finds duplicate data, raising `23505` manually can mislead clients into thinking a specific unique constraint failed while masking a race condition. Enforce uniqueness with real `UNIQUE` constraints and handle database-emitted `23505`, or use a custom business code when the semantics differ.

---

## 12. Lab Dataset: Products, Inventory, and Movement History

The main exercises use a products table and a stock-movements table so we can test:

- Non-rollback notifications.
- Function-level business errors.
- Database-level `UNIQUE`, `CHECK`, and `FOREIGN KEY` errors.
- Rollback inside `EXCEPTION` blocks.
- Constraint diagnostics via `GET STACKED DIAGNOSTICS`.
- Per-row batch processing.
- Calling from Java using `SQLSTATE`.

> **Warning:** The following `DROP SCHEMA ... CASCADE` deletes every object in the practice schema. Run only in a resettable lab database. Never run in production.

### 12.1. Create Schema

```sql
DROP SCHEMA IF EXISTS plpgsql_errors_lab CASCADE;

CREATE SCHEMA plpgsql_errors_lab;
```

### 12.2. Products Table

```sql
CREATE TABLE plpgsql_errors_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
        CONSTRAINT products_stock_nonnegative CHECK (stock >= 0),
    price NUMERIC(12,2) NOT NULL
        CONSTRAINT products_price_nonnegative CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

We explicitly name the two `CHECK` constraints for clearer diagnostics. The `UNIQUE` constraint on `sku` gets PostgreSQL's default generated name unless specified otherwise.

### 12.3. Stock Movements Table

```sql
CREATE TABLE plpgsql_errors_lab.stock_movements (
    movement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES plpgsql_errors_lab.products(product_id),
    delta INTEGER NOT NULL
        CONSTRAINT stock_movements_delta_nonzero
        CHECK (delta <> 0),
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Meaning:

- `delta > 0`: stock increase.
- `delta < 0`: stock deduction.
- `reason`: business reason.
- Foreign key ensures movements always reference an existing product.

### 12.4. Seed Data

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES
    ('SKU-100', 'Keyboard',  8,  450000.00),
    ('SKU-200', 'Mouse',    20,  180000.00),
    ('SKU-300', 'Monitor',   3, 2500000.00);
```

Verify:

```sql
SELECT product_id, sku, stock, price
FROM plpgsql_errors_lab.products
ORDER BY product_id;
```

### 12.5. The Lab Intentionally Uses Real Constraints

In real systems, PL/pgSQL input validation produces friendly messages, while **table constraints** remain the final defense if callers bypass functions and write directly.

---

## 13. Input Validation Function with RAISE EXCEPTION

Write a function validating SKU and quantity.

```sql
CREATE FUNCTION plpgsql_errors_lab.validate_reservation(
    p_sku TEXT,
    p_quantity INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF p_sku IS NULL OR BTRIM(p_sku) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ001',
            MESSAGE = 'SKU must not be blank',
            HINT = 'Pass a valid SKU code';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ002',
            MESSAGE = 'Quantity must be greater than 0',
            DETAIL = format(
                'quantity=%s',
                COALESCE(p_quantity::TEXT, '<NULL>')
            ),
            HINT = 'Choose a positive integer';
    END IF;
END;
$fn$;
```

### 13.1. Valid Call

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    'SKU-100', 2
);
```

The function returns `VOID` with no business payload.

### 13.2. Missing SKU Call

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    NULL::TEXT, 2
);
```

Raises SQLSTATE `PZ001`.

### 13.3. Invalid Quantity Call

```sql
SELECT plpgsql_errors_lab.validate_reservation(
    'SKU-100', 0
);
```

Raises SQLSTATE `PZ002`.

### 13.4. Why Not Use RAISE WARNING Alone?

A quantity of 0 violates the order contract. Emitting only a `WARNING` and continuing risks creating meaningless orders or corrupting data.

### 13.5. CHECK Constraints Are Still Necessary

If another path executes directly:

```sql
UPDATE plpgsql_errors_lab.products
SET stock = -5
WHERE sku = 'SKU-100';
```

the table's `CHECK` constraint rejects it. Function validation **never replaces `CHECK` constraints** when multiple write paths exist.

---

## 14. Ordering Function: Atomic Stock Deduction with Coded Errors

A simple, concurrency-safe pattern for deducting stock is a conditional `UPDATE`:

```sql
UPDATE products
SET stock = stock - requested
WHERE sku = requested_sku
  AND stock >= requested
RETURNING product_id;
```

Avoid the race-prone pattern:

```text
SELECT stock
IF stock >= quantity
    UPDATE stock = old_stock - quantity
```

without proper locking or transaction discipline, because two sessions can read the same stale stock simultaneously.

### 14.1. reserve_stock Function

```sql
CREATE FUNCTION plpgsql_errors_lab.reserve_stock(
    p_sku TEXT,
    p_quantity INTEGER
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $fn$
DECLARE
    v_product_id BIGINT;
    v_available INTEGER;
    v_movement_id BIGINT;
BEGIN
    PERFORM plpgsql_errors_lab.validate_reservation(
        p_sku, p_quantity
    );

    UPDATE plpgsql_errors_lab.products AS p
    SET
        stock = p.stock - p_quantity,
        updated_at = clock_timestamp()
    WHERE p.sku = p_sku
      AND p.stock >= p_quantity
    RETURNING p.product_id
      INTO v_product_id;

    IF NOT FOUND THEN
        SELECT p.stock
          INTO v_available
        FROM plpgsql_errors_lab.products AS p
        WHERE p.sku = p_sku;

        IF NOT FOUND THEN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ003',
                MESSAGE = 'SKU not found',
                DETAIL = format('sku=%s', p_sku),
                HINT = 'Verify the product code';
        END IF;

        RAISE EXCEPTION USING
            ERRCODE = 'PZ004',
            MESSAGE = 'Insufficient stock for reservation',
            DETAIL = format(
                'sku=%s, requested=%s, available_at_check=%s',
                p_sku, p_quantity, v_available
            ),
            HINT = 'Reduce quantity or wait for restock';
    END IF;

    INSERT INTO plpgsql_errors_lab.stock_movements (
        product_id, delta, reason
    )
    VALUES (
        v_product_id,
        -p_quantity,
        'RESERVATION'
    )
    RETURNING movement_id INTO v_movement_id;

    RETURN v_movement_id;
END;
$fn$;
```

### 14.2. Why VOLATILE?

The function executes `UPDATE` and `INSERT`, producing side effects. It cannot honestly be marked `STABLE` or `IMMUTABLE`.

### 14.3. Why a Conditional UPDATE?

PostgreSQL evaluates update predicates at execution time under the active isolation level's concurrency rules. With a single conditional `UPDATE` checking `stock >= p_quantity`, two concurrent requests cannot both deduct from the same stale stock past zero.

Still test under real isolation levels and workloads; this pattern alone does not solve distributed inventory systems.

### 14.4. Why Run a Follow-Up SELECT After UPDATE Fails?

To distinguish:

- SKU does not exist → `PZ003`.
- SKU exists, insufficient stock at check time → `PZ004`.

**Limitation:** under concurrency, data can change between the failed `UPDATE` and the diagnostic `SELECT`. Hence `available_at_check` reflects the diagnostic read, **not a guaranteed snapshot at the instant of the `UPDATE`**. Callers handle contention with appropriate retries if business rules allow.

### 14.5. Why Log Movements in the Same Transaction?

Because both stock deduction and `stock_movements` insertion run in one function inside one transaction, if the movement `INSERT` fails unhandled, the entire statement/transaction rolls back. Never deduct stock and ignore movement-logging errors.

### 14.6. Functions Do Not Self-Commit

The function executes within the caller's transaction. Even after it `RETURN`s `movement_id`, the application must wait for `COMMIT` to succeed before confirming the order.

---

## 15. Testing Success and Failure Paths

### 15.1. Reserve 2 Units Inside a Transaction and Roll Back

```sql
BEGIN;

SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', 2
) AS movement_id;

SELECT sku, stock
FROM plpgsql_errors_lab.products
WHERE sku = 'SKU-100';

SELECT *
FROM plpgsql_errors_lab.stock_movements
ORDER BY movement_id DESC
LIMIT 5;

ROLLBACK;
```

Inside the transaction, `SKU-100` stock drops from 8 to 6. After `ROLLBACK`, the change is undone.

### 15.2. Ordering Too Many Units

Run separately:

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', 999
);
```

Raises business error `PZ004`, with `DETAIL` showing `available_at_check`.

### 15.3. Nonexistent SKU

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-NOT-FOUND', 1
);
```

Expected error code: `PZ003`.

### 15.4. Invalid Input

```sql
SELECT plpgsql_errors_lab.reserve_stock(
    'SKU-100', -1
);
```

Expected error code: `PZ002`.

### 15.5. Where Are Errors Raised?

- `PZ001` and `PZ002` come from validation.
- `PZ003` and `PZ004` come from business branches after the `UPDATE`.
- `23505`, `23514`, and `23503` come directly from database constraints without faking them in function code.

---

## 16. EXCEPTION WHEN: Syntax for Catching Exceptions

A PL/pgSQL block can include an exception section:

```sql
BEGIN
    -- Statements that might raise errors.
EXCEPTION
    WHEN condition_name THEN
        -- Handle recognized condition.
    WHEN SQLSTATE 'xxxxx' THEN
        -- Handle by error code.
    WHEN OTHERS THEN
        -- Handle remaining errors within OTHERS scope.
END;
```

Example:

```sql
DO $do$
BEGIN
    BEGIN
        PERFORM plpgsql_errors_lab.reserve_stock(
            'SKU-100', 999
        );

        RAISE NOTICE 'Reservation succeeded';
    EXCEPTION
        WHEN SQLSTATE 'PZ004' THEN
            RAISE NOTICE 'Insufficient stock; prompt user to adjust';
    END;
END;
$do$;
```

Because `PZ004` is a custom code, use `WHEN SQLSTATE 'PZ004'`.

### 16.1. Which Statements Does a Handler Cover?

A handler catches errors raised inside **the block's statements before `EXCEPTION`**, including errors propagated from functions called there.

### 16.2. The First Matching Handler Executes

When multiple handlers could match the same error, list specific handlers before broader ones.

### 16.3. Never Catch Every Error Just to Keep Running

A `23505` could come from a duplicate SKU—or from an unrelated unique constraint. Catch and continue only when you know the exact error and safe recovery path.

### 16.4. Errors Inside a Handler Are Not Re-Caught by That Same Handler List

If code inside a `WHEN ... THEN` handler raises a new error, the same block's `EXCEPTION` section does not catch it again. An outer block or the caller must handle it.

---

## 17. Catching Errors by Condition Name

PostgreSQL provides readable condition names:

```sql
DO $do$
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Duplicate SKU', 1, 1000);
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Product with this SKU already exists';
    END;
END;
$do$;
```

### 17.1. Common Condition Names

| Condition Name | SQLSTATE | Meaning |
|---|---|---|
| `unique_violation` | 23505 | UNIQUE / PRIMARY KEY conflict |
| `foreign_key_violation` | 23503 | FOREIGN KEY violation |
| `not_null_violation` | 23502 | NULL written to NOT NULL column |
| `check_violation` | 23514 | CHECK evaluated to FALSE |
| `division_by_zero` | 22012 | Division by zero |
| `invalid_parameter_value` | 22023 | Invalid parameter value |
| `serialization_failure` | 40001 | Transaction failed serialization |
| `deadlock_detected` | 40P01 | Deadlock detected |
| `raise_exception` | P0001 | Default `RAISE EXCEPTION` |
| `no_data_found` | P0002 | 0 rows in `STRICT` context |
| `too_many_rows` | P0003 | Multiple rows in `STRICT` context |

### 17.2. Condition Names Improve Readability

```sql
WHEN unique_violation THEN ...
```

reads more clearly than:

```sql
WHEN SQLSTATE '23505' THEN ...
```

while `SQLSTATE` codes remain essential for custom codes and database-driver interfaces.

### 17.3. Catching by Class Is Possible

A class condition name (such as `integrity_constraint_violation`) covers multiple child conditions. Never catch an entire class if your application must distinguish UNIQUE from FK or NOT NULL.

---

## 18. UNIQUE, CHECK, and FOREIGN KEY Errors

Table constraints are a critical source of errors.

### 18.1. UNIQUE — 23505

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-100', 'A duplicate SKU', 1, 1000);
```

Because `sku` has a `UNIQUE` constraint, this fails with `23505`.

### 18.2. CHECK — 23514

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-NEG-STOCK', 'Negative stock', -1, 1000);
```

Violates `products_stock_nonnegative`, code `23514`.

### 18.3. FOREIGN KEY — 23503

```sql
INSERT INTO plpgsql_errors_lab.stock_movements (
    product_id, delta, reason
)
VALUES (999999999, -1, 'UNKNOWN_PRODUCT');
```

When no matching `product_id` exists, raises `23503`.

### 18.4. NOT NULL — 23502

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES (NULL, 'Missing code', 2, 1000);
```

Raises `23502`.

### 18.5. Constraint Metadata Enables Exact Classification

The same `23505` code could come from `sku` or another unique index. `GET STACKED DIAGNOSTICS ... CONSTRAINT_NAME` tells the handler exactly which constraint failed.

Never parse message text like `duplicate key value violates unique constraint ...` to extract constraint names.

---

## 19. GET STACKED DIAGNOSTICS: Inspecting the Caught Error

Inside an exception handler, PostgreSQL provides:

```sql
GET STACKED DIAGNOSTICS
    variable_1 = diagnostic_item_1,
    variable_2 = diagnostic_item_2,
    ...;
```

Common items:

| Diagnostic Item | Meaning |
|---|---|
| `RETURNED_SQLSTATE` | Error's SQLSTATE code |
| `MESSAGE_TEXT` | Primary error message |
| `PG_EXCEPTION_DETAIL` | Error `DETAIL` |
| `PG_EXCEPTION_HINT` | Error `HINT` |
| `PG_EXCEPTION_CONTEXT` | Execution call stack where the error occurred |
| `SCHEMA_NAME` | Related schema name, if any |
| `TABLE_NAME` | Related table name, if any |
| `COLUMN_NAME` | Related column name, if any |
| `CONSTRAINT_NAME` | Related constraint name, if any |
| `PG_DATATYPE_NAME` | Related data type name, if any |

### 19.1. Example: Retrieving SQLSTATE and Constraint Name

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_constraint TEXT;
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Duplicate SKU demo', 1, 1000);
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE
            'state=%, constraint=%, message=%',
            v_state, v_constraint, v_message;
    END;
END;
$do$;
```

### 19.2. Metadata May Be Absent

Not every error populates `TABLE_NAME`, `COLUMN_NAME`, or `CONSTRAINT_NAME`. Never assume every error populates all fields, and never treat empty metadata as meaning the `SQLSTATE` is wrong.

### 19.3. GET STACKED DIAGNOSTICS Only Works on a Caught Error

It inspects the active exception inside a handler. Never use it outside exception-handling scope to query "the session's last error."

### 19.4. Capture Everything for Diagnostics, Expose Only What Is Safe

`PG_EXCEPTION_CONTEXT` contains function names, line numbers, and execution context. It belongs in controlled operational logs—rarely verbatim in public HTTP responses.

---

## 20. SQLSTATE and SQLERRM Inside Exception Handlers

Inside a handler, PL/pgSQL provides two built-in variables:

- `SQLSTATE`: the error code.
- `SQLERRM`: the error message.

Example:

```sql
DO $do$
BEGIN
    BEGIN
        PERFORM 10 / 0;
    EXCEPTION
        WHEN division_by_zero THEN
            RAISE NOTICE
                'Caught state=% and message=%',
                SQLSTATE, SQLERRM;
    END;
END;
$do$;
```

### 20.1. When Are They Enough?

If the handler only needs brief classification and logging:

```sql
RAISE NOTICE 'SQLSTATE=%', SQLSTATE;
```

they can suffice.

### 20.2. When Is GET STACKED DIAGNOSTICS Needed?

Whenever you need `CONSTRAINT_NAME`, `DETAIL`, `HINT`, or the original `PG_EXCEPTION_CONTEXT`, use `GET STACKED DIAGNOSTICS`.

### 20.3. SQLERRM Does Not Replace SQLSTATE

Message wording can change; drivers and applications should check error codes. Never write:

```text
IF SQLERRM contains 'duplicate key' THEN ...
```

to identify unique constraint violations.

### 20.4. SQLSTATE Is Not a Global SQL Variable

`SQLSTATE` and `SQLERRM` are PL/pgSQL variables scoped to exception handlers. Never assume you can run `SELECT SQLSTATE` in a plain SQL session outside a handler.

---

## 21. RAISE; Rethrows the Original Error

A handler may need to log or gather context **without recovering from the failure**. In that case, rethrow the error:

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;
    EXCEPTION
        WHEN division_by_zero THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE WARNING
                'Calculation failed: state=%, message=%',
                v_state, v_message;

            RAISE;
    END;
END;
$do$;
```

`RAISE;` rethrows the caught error so the caller receives the original `SQLSTATE` and metadata.

### 21.1. Never Replace with RAISE EXCEPTION SQLERRM

The following **loses the original error code**:

```sql
-- Do NOT rethrow this way if you want to preserve error info:
-- RAISE EXCEPTION '%', SQLERRM;
```

Because a fresh `RAISE EXCEPTION` defaults to `P0001` and creates a new error context, it obscures the original exception.

### 21.2. When to Translate Errors Intentionally?

If the database is an API boundary and you intentionally want to map an internal failure to a safe business error code, raise a new error **deliberately**:

```sql
RAISE EXCEPTION USING
    ERRCODE = 'PZ006',
    MESSAGE = 'Request could not be completed',
    HINT = 'Please verify input data';
```

Still log the underlying cause securely and avoid masking retryable infrastructure errors.

### 21.3. RAISE; Is Only Valid Inside a Handler

Never call `RAISE;` outside an exception handler to raise a default error. It requires an active exception in handler scope.

---

## 22. EXCEPTION Blocks Are Subtransactions

This is the most important point regarding data consistency.

When a PL/pgSQL block with `EXCEPTION` catches an error, PostgreSQL manages database changes inside the block body using a **subtransaction**. When an error occurs and is caught, **persistent database changes made inside that block body** are rolled back to the start of the block.

However:

- PL/pgSQL variables retain their values as of the moment the error occurred.
- Database changes made before entering the inner block remain in the outer transaction.
- Changes made **inside the handler** after the inner block rolls back are kept if the outer transaction later commits.
- If the outer transaction rolls back, handler changes to normal logged tables also roll back.
- Messages already sent to clients or server logs are not "recalled" on rollback.
- Sequences and external non-DB side effects do not roll back like transactional DML; never assume an exception block undoes everything.

### 22.1. Runnable Example

```sql
BEGIN;

INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES (
    'SKU-OUTER',
    'Created in outer transaction',
    1,
    1000
);

DO $do$
DECLARE
    v_stage TEXT := 'unprocessed';
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES (
            'SKU-INNER',
            'Created in inner block',
            1,
            1000
        );

        v_stage := 'inserted SKU-INNER';

        RAISE EXCEPTION 'Simulated failure in inner block';

    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE
                'Handler sees v_stage=%', v_stage;
    END;
END;
$do$;

SELECT sku
FROM plpgsql_errors_lab.products
WHERE sku IN ('SKU-OUTER','SKU-INNER')
ORDER BY sku;

ROLLBACK;
```

### 22.2. Predicting State Inside the Transaction

Before the final `ROLLBACK`:

- `SKU-OUTER` exists in the transaction because it was inserted **before the inner block**.
- `SKU-INNER` **does not exist**, because the inner block's INSERT rolled back when the exception was caught.
- `v_stage` inside the handler still holds `'inserted SKU-INNER'`, because PL/pgSQL variables do not revert like table rows.

After `ROLLBACK`, the outer transaction change is also discarded.

### 22.3. Why Do Variables and Tables Behave Differently?

PL/pgSQL variables live in execution memory, while table changes live under the transaction/subtransaction engine. Catching an exception rolls back database state without rewinding local program variables.

### 22.4. Never Swallow Errors and Assume an Earlier UPDATE Stayed

If an `UPDATE` ran **inside the same `EXCEPTION` block** and that block raised an error, the `UPDATE` rolled back even if a counter variable was incremented. In batch processing, increment success counters **after** all fallible steps or adjust variables accurately.

---

## 23. Block Scope Determines What Rolls Back

Compare two structures.

### 23.1. EXCEPTION Block Wrapping All Work

```sql
BEGIN
    UPDATE ...;  -- A
    INSERT ...;  -- B, might fail
EXCEPTION WHEN OTHERS THEN
    -- Both A and B in the block body roll back
END;
```

If `B` fails, `A` inside the same block rolls back too.

### 23.2. Wrapping Only the Fallible Step

```sql
BEGIN
    UPDATE ...;  -- A in outer block

    BEGIN
        INSERT ...;  -- B in inner block
    EXCEPTION WHEN unique_violation THEN
        -- Only DB changes inside the inner block roll back.
    END;
END;
```

If `B` fails and is caught in the inner block, `A` in the outer block remains intact (subject to the outer transaction).

### 23.3. Design Rule

Place `EXCEPTION` block boundaries around **the exact unit of work allowed to roll back**. Never wrap an entire function in `WHEN OTHERS` just to log if doing so muddies error handling and subtransaction boundaries.

### 23.4. Handlers Never Commit Independently

A handler cannot turn an `INSERT INTO error_log` into an independent committed transaction separate from its caller. If the caller subsequently rolls back, normal error_log inserts roll back as well.

If error audits **must persist even when business transactions roll back**, use out-of-transaction logging or an appropriate external architecture—not just an `INSERT` inside a handler.

---

## 24. Nested EXCEPTION: Where Do Errors Inside Handlers Go?

Consider:

```sql
DO $do$
BEGIN
    BEGIN
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ001',
                MESSAGE = 'Initial error';
        EXCEPTION WHEN SQLSTATE 'PZ001' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'PZ002',
                MESSAGE = 'New error from handler';
        END;

    EXCEPTION WHEN SQLSTATE 'PZ002' THEN
        RAISE NOTICE 'Outer block caught PZ002';
    END;
END;
$do$;
```

The inner block's handler does not catch `PZ002` raised by itself. The error propagates to the enclosing block, where the `PZ002` handler catches it.

### 24.1. When to Use Nested Handlers?

- A small unit of work has an ignorable error.
- An inner handler intentionally translates an error type.
- An outer block implements a broader abort/retry policy.
- A batch processes items independently while still letting fatal system errors abort the whole batch.

### 24.2. Avoid Excessive Nesting

Deeply nested handlers make rollback scopes and error paths hard to trace. When workflows grow complex, split functions, redesign return contracts, or move retries to the application transaction layer.

---

## 25. WHEN OTHERS: Useful Yet Dangerous

A handler:

```sql
EXCEPTION WHEN OTHERS THEN
    ...
```

catches most error types not matched by earlier branches.

### 25.1. OTHERS Does Not Catch Literally Everything

In PostgreSQL, `OTHERS` **does not catch** `query_canceled` or `assert_failure` by default; catching them requires naming them explicitly.

Never document "`WHEN OTHERS` catches every error with no exceptions."

### 25.2. Dangerous Anti-Pattern: Swallowing Errors

```sql
-- Anti-pattern: NEVER USE IN CRITICAL BUSINESS LOGIC.
--
-- EXCEPTION WHEN OTHERS THEN
--     RAISE NOTICE 'Error occurred, continuing';
--     RETURN TRUE;
```

If an `INSERT` hits a unique violation, deadlock, or bad SQL, the function returns `TRUE` despite failing.

### 25.3. Log-and-Rethrow Pattern

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE WARNING
            'Unhandled error state=%, message=%',
            v_state, v_message;

        RAISE;
    END;
END;
$do$;
```

This is much safer when you need diagnostic context without a safe recovery strategy.

### 25.4. When Is Swallowing an Error Acceptable?

Only when it is **an explicitly defined business policy**—for example, skipping a malformed batch import row, recording it in a rejected-rows table, and continuing valid rows.

Document clearly:

- Which error codes may be skipped.
- Which changes roll back.
- Whether logging is durable/transactional.
- How failed row counts are reported.
- Which errors must still abort the whole batch.

### 25.5. Never Catch Deadlock/Serialization and Return Success

Codes `40P01` and `40001` require retrying the transaction cleanly at the caller boundary. Catching them and returning 0 tricks the application into treating an aborted operation as complete.

---

## 26. Catching UNIQUE Must Identify the Exact Constraint

A function may touch multiple tables with multiple unique constraints. A handler:

```sql
EXCEPTION WHEN unique_violation THEN
    -- "Duplicate SKU" ?
```

does not prove `products.sku` was the violated constraint.

### 26.1. Use CONSTRAINT_NAME

```sql
DO $do$
DECLARE
    v_constraint TEXT;
BEGIN
    BEGIN
        INSERT INTO plpgsql_errors_lab.products (
            sku, display_name, stock, price
        )
        VALUES ('SKU-100', 'Duplicate SKU', 1, 1000);

    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        IF v_constraint = 'products_sku_key' THEN
            RAISE NOTICE 'SKU already exists';
        ELSE
            RAISE;
        END IF;
    END;
END;
$do$;
```

In our lab schema, the `UNIQUE` constraint on `sku` normally gets the default name `products_sku_key`. If DDL names it differently or changes, verify and update the constraint name.

### 26.2. Always Name Constraints Explicitly

In production, explicit constraint names stay stable for diagnostics and error mapping. Never rely blindly on PostgreSQL's auto-generated names without recording them in migrations.

### 26.3. Do Not Treat Every UNIQUE Violation as Retryable

A unique conflict on an idempotency key may mean a retried request already succeeded; on SKU it means duplicate catalog data; on transaction ID it may indicate a logic bug. `SQLSTATE` only identifies the constraint kind—policy depends on business semantics.

### 26.4. ON CONFLICT Can Beat Exception Handling

When insert-if-absent is normal behavior, prefer:

```sql
INSERT INTO plpgsql_errors_lab.products (
    sku, display_name, stock, price
)
VALUES ('SKU-100', 'Keyboard', 8, 450000)
ON CONFLICT (sku) DO NOTHING;
```

This avoids overwriting existing products. For idempotent inserts where no error needs raising, `ON CONFLICT` is clearer and avoids per-row `unique_violation` handler overhead.

---

## 27. SELECT INTO STRICT and P0002 / P0003

PL/pgSQL supports:

```sql
SELECT ...
INTO STRICT variable
FROM ...
WHERE ...;
```

`STRICT` requires **exactly one row**.

### 27.1. No Rows: no_data_found

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    BEGIN
        SELECT product_id
          INTO STRICT v_product_id
        FROM plpgsql_errors_lab.products
        WHERE sku = 'SKU-UNKNOWN';

    EXCEPTION WHEN no_data_found THEN
        RAISE NOTICE 'Product not found';
    END;
END;
$do$;
```

Raises code `P0002`.

### 27.2. Multiple Rows: too_many_rows

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    BEGIN
        SELECT product_id
          INTO STRICT v_product_id
        FROM plpgsql_errors_lab.products
        WHERE stock >= 0;

    EXCEPTION WHEN too_many_rows THEN
        RAISE NOTICE 'Query returned more than one product';
    END;
END;
$do$;
```

With multiple products in the lab, raises code `P0003`.

### 27.3. Omit STRICT When 0 Rows Is Normal

When a missing row is an expected business branch, use non-STRICT `SELECT INTO` and inspect `FOUND`:

```sql
DO $do$
DECLARE
    v_product_id BIGINT;
BEGIN
    SELECT product_id
      INTO v_product_id
    FROM plpgsql_errors_lab.products
    WHERE sku = 'SKU-UNKNOWN';

    IF NOT FOUND THEN
        RAISE NOTICE 'SKU not present';
    END IF;
END;
$do$;
```

### 27.4. Non-STRICT Picks an Arbitrary First Row on Multi-Row Queries

If a non-STRICT `SELECT` returns multiple rows, PL/pgSQL picks whichever row the plan emits first. Never treat that as a reliable "first record" without explicit `ORDER BY` and `LIMIT`.

---

## 28. FOUND and ROW_COUNT Are Not Exception Mechanisms

Many "no matching row" situations do not warrant an `EXCEPTION`.

### 28.1. FOUND

After qualifying SQL statements in PL/pgSQL, `FOUND` indicates whether any rows were found or affected.

Example:

```sql
DO $do$
BEGIN
    UPDATE plpgsql_errors_lab.products
    SET updated_at = updated_at
    WHERE sku = 'SKU-UNKNOWN';

    IF NOT FOUND THEN
        RAISE NOTICE 'No rows to update';
    END IF;
END;
$do$;
```

### 28.2. GET DIAGNOSTICS ROW_COUNT

```sql
DO $do$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE plpgsql_errors_lab.products
    SET updated_at = updated_at
    WHERE sku IN ('SKU-100','SKU-200');

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'Affected rows: %', v_affected;
END;
$do$;
```

`ROW_COUNT` holds the number of rows processed by the immediately preceding SQL command.

### 28.3. GET DIAGNOSTICS vs. GET STACKED DIAGNOSTICS

- `GET DIAGNOSTICS ... ROW_COUNT`: inspects normal-execution command metadata.
- `GET STACKED DIAGNOSTICS ... RETURNED_SQLSTATE`: inspects caught-error metadata inside an exception handler.

Never confuse the two statements.

### 28.4. Do Not Turn Every "0 Rows Updated" into an Exception

An `UPDATE` matching zero rows is valid SQL, not an error. If business rules require at least one row to update, inspect `FOUND` or `ROW_COUNT` and explicitly raise a business error code.

---

## 29. Exception Blocks Have Overhead

PostgreSQL's documentation notes that **entering and exiting a PL/pgSQL block with `EXCEPTION` is more expensive than a block without one** due to subtransaction setup.

This matters especially inside loops processing millions of rows.

### 29.1. High-Exception-Rate Loop Pattern

```sql
FOR r IN SELECT ... LOOP
    BEGIN
        INSERT INTO ...;
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END LOOP;
```

If most rows collide, triggering the exception path repeatedly consumes significant CPU and WAL/transaction metadata.

### 29.2. Replace with Set-Based SQL When Appropriate

```sql
INSERT INTO target_table (...)
SELECT ...
FROM staging_table
ON CONFLICT (unique_key)
DO NOTHING;
```

A single set-based statement with `ON CONFLICT` is cleaner and faster for expected duplicates.

### 29.3. When Per-Row Exceptions Make Sense

- Imported rows are independent of one another.
- Errors are rare.
- Each failure needs structured recording.
- Valid rows should proceed.
- Each row's side effects must roll back independently within the outer transaction.

### 29.4. No Universal Constant Overhead Number

Actual cost depends on row counts, failure rate, indexes, constraints, storage, PostgreSQL version, and transaction length. Never claim a fixed percentage slowdown without benchmarking.

---

## 30. Batch Processing: Preparing Request and Rejection Tables

We create a small batch setup illustrating independent per-row processing while the caller still owns the outer transaction.

### 30.1. Requests Table

```sql
CREATE TABLE plpgsql_errors_lab.stock_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    sku TEXT,
    quantity INTEGER,
    processed BOOLEAN NOT NULL DEFAULT FALSE
);
```

### 30.2. Rejections Table

```sql
CREATE TABLE plpgsql_errors_lab.rejected_requests (
    rejection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    request_id BIGINT NOT NULL,
    error_state TEXT NOT NULL,
    error_message TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

This is a business log table **inside the database transaction**. If the caller rolls back the outer transaction, rows inserted into `rejected_requests` roll back too.

### 30.3. Sample Data

```sql
INSERT INTO plpgsql_errors_lab.stock_requests (
    batch_id, sku, quantity
)
VALUES
    (1, 'SKU-100', 1),
    (1, 'SKU-200', 3),
    (1, 'SKU-300', 999),
    (1, 'SKU-UNKNOWN', 1),
    (1, 'SKU-200', 0);
```

In this batch:

- The first two requests are valid.
- One request lacks sufficient stock.
- One request has a nonexistent SKU.
- One request has quantity 0.

### 30.4. Business Requirements

- Attempt each request.
- On success: mark `processed`.
- On business errors `PZ001`–`PZ004`: roll back that request's changes, record the rejection, and continue.
- On any other system error: never swallow it; let it propagate to the caller.
- Return counts of processed and rejected requests.
- Caller decides `COMMIT` or `ROLLBACK` for the batch.

---

## 31. Batch Function with Per-Item Exception Handling

```sql
CREATE FUNCTION plpgsql_errors_lab.process_stock_batch(
    p_batch_id INTEGER
)
RETURNS TABLE (
    processed_count INTEGER,
    rejected_count INTEGER
)
LANGUAGE plpgsql
VOLATILE
AS $fn$
DECLARE
    v_request RECORD;
    v_processed INTEGER := 0;
    v_rejected INTEGER := 0;
    v_state TEXT;
    v_message TEXT;
BEGIN
    FOR v_request IN
        SELECT
            r.request_id,
            r.sku,
            r.quantity
        FROM plpgsql_errors_lab.stock_requests AS r
        WHERE r.batch_id = p_batch_id
          AND NOT r.processed
        ORDER BY r.request_id
    LOOP
        BEGIN
            PERFORM plpgsql_errors_lab.reserve_stock(
                v_request.sku,
                v_request.quantity
            );

            UPDATE plpgsql_errors_lab.stock_requests
            SET processed = TRUE
            WHERE request_id = v_request.request_id;

            v_processed := v_processed + 1;

        EXCEPTION
            WHEN SQLSTATE 'PZ001'
              OR SQLSTATE 'PZ002'
              OR SQLSTATE 'PZ003'
              OR SQLSTATE 'PZ004'
            THEN
                GET STACKED DIAGNOSTICS
                    v_state = RETURNED_SQLSTATE,
                    v_message = MESSAGE_TEXT;

                INSERT INTO plpgsql_errors_lab.rejected_requests (
                    batch_id, request_id, error_state, error_message
                )
                VALUES (
                    p_batch_id,
                    v_request.request_id,
                    v_state,
                    v_message
                );

                v_rejected := v_rejected + 1;
        END;
    END LOOP;

    RETURN QUERY
    SELECT v_processed, v_rejected;
END;
$fn$;
```

### 31.1. Why Catch Only Known Business Error Codes?

If a failure is caused by a deadlock, broken constraint, or database issue, turning it into a "rejected request" and blindly continuing is dangerous. Only catch errors explicitly designed for recovery and let everything else propagate.

### 31.2. Why Is the UPDATE processed Inside the Inner Block?

Keeping `reserve_stock` and marking `processed` inside the same block ensures that any caught error rolls back both changes together—preventing stock from being deducted while the request stays unprocessed, or vice versa.

### 31.3. Why Record the Rejection Inside the Handler?

Upon entering the handler, persistent changes from the inner block's body have already rolled back. The `INSERT` into `rejected_requests` runs outside that rolled-back scope and commits alongside the outer transaction.

### 31.4. Watch Counter Variables

PL/pgSQL variables do not roll back with subtransactions, so increment `v_processed` only after all fallible statements succeed. Incrementing early would leave the wrong count if a later statement raised an error.

### 31.5. Dry-Run Without Committing

```sql
BEGIN;

SELECT *
FROM plpgsql_errors_lab.process_stock_batch(1);

SELECT
    request_id, sku, quantity, processed
FROM plpgsql_errors_lab.stock_requests
WHERE batch_id = 1
ORDER BY request_id;

SELECT
    request_id, error_state, error_message
FROM plpgsql_errors_lab.rejected_requests
WHERE batch_id = 1
ORDER BY rejection_id;

SELECT sku, stock
FROM plpgsql_errors_lab.products
ORDER BY sku;

ROLLBACK;
```

Starting from clean lab data, expect:

- `processed_count = 2`.
- `rejected_count = 3`.
- The first two valid requests marked `processed = true` inside the transaction.
- Three rejection rows logged with `PZ004`, `PZ003`, and `PZ002` in order.
- After `ROLLBACK`, everything returns to its initial state.

### 31.6. Idempotency Limitations

This lab demonstrates exception handling. Production batch processors also need:

- Request idempotency keys.
- Batch-level and item-level retry rules.
- Unique constraints on rejections if duplicate logging must be prevented.
- Concurrency locking if multiple workers claim the same batch.
- Durable `failed`/`processed` states and selection queries.
- Synchronization between inventory and external systems.
- Crash recovery and transaction restart handling.

A bare `processed BOOLEAN` column alone does not cover those risks.

---

## 32. Subtlety: Error Logs and Outer Rollback

Suppose the batch function catches an item error and inserts into `rejected_requests`. If the caller runs:

```sql
BEGIN;

SELECT *
FROM plpgsql_errors_lab.process_stock_batch(1);

ROLLBACK;
```

both inventory deductions and rejection records written in that transaction roll back.

### 32.1. When Are Logs Preserved?

When the caller successfully commits the transaction:

```sql
BEGIN;
SELECT * FROM plpgsql_errors_lab.process_stock_batch(1);
COMMIT;
```

### 32.2. There Is No Simple "Autonomous Transaction" Inside PL/pgSQL Functions

An exception handler inside a function cannot independently `COMMIT` error logs outside the caller's transaction the way autonomous transactions work in some other databases.

### 32.3. RAISE LOG/NOTICE Is a Separate Channel

Messages sent to clients or server logs are not transactional DML rows and do not roll back with transactions. However, log channels have separate durability, retention, and security properties—never assume they satisfy legal audit requirements automatically.

### 32.4. When Failure Audits Must Survive Business Rollbacks

Design an out-of-transaction logging/audit component or an appropriate architecture—such as the application recording failures to a separate audit store upon receiving an `SQLSTATE`, with proper safety, idempotency, and network-failure handling.

---

## 33. RAISE Inside Trigger Functions

PL/pgSQL frequently uses trigger functions to validate and reject data modifications.

Example rejecting blank product names:

```sql
CREATE FUNCTION plpgsql_errors_lab.reject_blank_name()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.display_name IS NULL
       OR BTRIM(NEW.display_name) = ''
    THEN
        RAISE EXCEPTION USING
            ERRCODE = 'PZ006',
            MESSAGE = 'Product name must not be blank',
            HINT = 'Enter a valid display_name';
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_reject_blank_product_name
BEFORE INSERT OR UPDATE OF display_name
ON plpgsql_errors_lab.products
FOR EACH ROW
EXECUTE FUNCTION plpgsql_errors_lab.reject_blank_name();
```

### 33.1. What Does RAISE EXCEPTION in a Trigger Do?

If a trigger raises an uncaught `EXCEPTION`, the triggering DML statement fails under transaction rules and the row change is not applied.

### 33.2. Why Prefer CHECK Over Triggers When Possible?

For a simple rule like:

```sql
CHECK (BTRIM(display_name) <> '')
```

a `CHECK` constraint is clearer and cheaper than a custom trigger. Reserve triggers for logic needing context that constraints cannot express. Never write triggers for rules that `CHECK`/`UNIQUE`/`FK` already handle cleanly.

### 33.3. Never Use a Trigger Just to Warn and Allow Bad Data

If a trigger function detects a serious invariant violation, logs only a `WARNING`, and still returns `NEW`, corrupt data gets written. Reject invalid data with constraints or `EXCEPTION`.

### 33.4. Triggers Also Run Inside the Caller's Transaction

Triggers never self-`COMMIT`. All database work in a trigger obeys the triggering DML statement's transaction.

### 33.5. Privileges and Error Messages

Trigger error messages can surface to end users when `INSERT`/`UPDATE` fails. Never leak sensitive details from other rows in `DETAIL` or `HINT`.

---

## 34. Deferrable Constraints and When Errors Surface

Not every constraint violation occurs immediately on the DML statement that wrote the data.

PostgreSQL supports **`DEFERRABLE`** constraints whose validation can be deferred until transaction `COMMIT`.

### 34.1. Why Does This Matter?

Suppose a function runs DML and returns normally, yet a deferred constraint is checked at `COMMIT`. The error happens **after the function has already finished**.

An exception handler inside the function cannot catch an error that only fires later at `COMMIT`.

### 34.2. Which Constraints Can Be Deferred?

`FOREIGN KEY`, `UNIQUE`, `PRIMARY KEY`, and `EXCLUDE` constraints support `DEFERRABLE` under PostgreSQL syntax rules. `CHECK` and `NOT NULL` do not share that arbitrary commit-time deferral mechanism in standard PostgreSQL.

### 34.3. SET CONSTRAINTS ... IMMEDIATE

Where appropriate, a transaction can force early checking of deferred constraints via `SET CONSTRAINTS ... IMMEDIATE`. Errors then surface on that statement, though you should not use it blindly since it alters transaction state.

### 34.4. Application Contracts Must Wait for COMMIT

Even after a function returns a movement ID, never report business success until `COMMIT` completes cleanly.

---

## 35. Deadlocks and Serialization Failures Require Transaction-Boundary Retries

Certain errors stem from concurrency:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

In most systems, the right policy is to **retry the entire transaction** provided operations are idempotent or guarded by idempotency keys.

### 35.1. Why Not Resume the Remainder of the Failed Transaction?

After a concurrency abort, the transaction's snapshot and prior reads are invalid. PostgreSQL recommends that serialization-failure retry loops re-run **the entire transaction**, including all reads and decisions.

### 35.2. Application-Layer Retry Pseudocode

```text
for attempt in 1..maxAttempts:
    BEGIN TRANSACTION
    try:
        perform entire business transaction
        COMMIT
        return success
    catch SQLSTATE 40001 or 40P01:
        ROLLBACK
        if attempt < maxAttempts:
            sleep with bounded backoff/jitter
            retry whole transaction
        else:
            report retry exhausted
    catch any other error:
        ROLLBACK
        propagate/map error
```

### 35.3. Avoid Infinite Retries

Enforce max attempts, timeouts, backoff, and metrics, and separate transient errors from permanent ones. Never blindly retry `23505` or `PZ002`.

### 35.4. Idempotency Is Critical

If a transaction calls a payment gateway or sends an email, retrying the whole transaction must not duplicate external side effects. PostgreSQL cannot roll back an already-sent HTTP request.

### 35.5. Deadlocks Differ from Insufficient Stock

Insufficient stock is a user-explainable business condition. A deadlock is a concurrency/infrastructure condition needing retries. Never map both to a generic error code.

---

## 36. Query Canceled and Assert Failure

Two special conditions to remember when using `WHEN OTHERS`:

### 36.1. query_canceled — 57014

A query may be canceled by the user, timeout, or an operator. PostgreSQL represents this as `query_canceled` (`57014`).

`WHEN OTHERS` does not catch it by default.

When an application cancels work, silently ignoring the cancellation causes unexpected behavior. Never catch `query_canceled` and keep computing without a strict, intentional reason.

### 36.2. assert_failure — P0004

PL/pgSQL provides `ASSERT` to verify internal invariants when enabled:

```sql
DO $do$
DECLARE
    v_count INTEGER := 2;
BEGIN
    ASSERT v_count >= 0, 'Count assumed non-negative';
END;
$do$;
```

If an assertion fails while assertion checking is enabled, PostgreSQL raises `P0004`.

### 36.3. ASSERT Does Not Replace Business RAISE EXCEPTION

`ASSERT` detects programming bugs and broken internal assumptions—not invalid user input. Configuration can disable assertions, so never rely on `ASSERT` for critical business invariants.

### 36.4. WHEN OTHERS Does Not Catch Either Condition

Never assume:

```sql
EXCEPTION WHEN OTHERS THEN
    RETURN TRUE;
```

will catch cancellation or assertion failures. Even more importantly, neither should normally be swallowed anyway.

---

## 37. Structured Messages and Observability

A handler can log diagnostic fields:

```sql
DO $do$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_context TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;

    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE WARNING
            'Error state=% message=% detail=% hint=%',
            v_state,
            v_message,
            v_detail,
            v_hint;

        -- Send context to controlled logs if genuinely needed;
        -- never expose verbatim to untrusted clients.
        RAISE;
    END;
END;
$do$;
```

### 37.1. Which Fields Should Be Logged?

- `SQLSTATE`.
- Function name / operation purpose.
- Non-sensitive request / correlation ID.
- Constraint name where applicable.
- Retry / attempt number.
- Transaction outcome (`commit`/`rollback`).
- Timestamps and tenant ID protected according to policy.

### 37.2. Do Not Stuff Arbitrary JSON into MESSAGE

For structured logs, configure your application or logging pipeline with explicit fields, types, masking, and retention. A long `MESSAGE` string does not create queryable structured telemetry.

### 37.3. Avoid Duplicate Multi-Layer Error Logging

An error might pass through a DB handler, JDBC layer, service layer, and HTTP middleware. If every layer logs `ERROR` with a full stack trace, alert counts multiply. Decide which layer owns primary error logging and let other layers enrich context and rethrow.

### 37.4. RAISE NOTICE Is Not a Metrics Table

Emitting `NOTICE`s does not automatically aggregate `PZ004` counts per SKU. Use proper monitoring pipelines or SQL telemetry tables for dashboards.

---

## 38. GET STACKED DIAGNOSTICS and PG_EXCEPTION_CONTEXT

Two easily confused context items:

- `PG_EXCEPTION_CONTEXT`: call stack where **the error originated**.
- `PG_CONTEXT` (with `GET DIAGNOSTICS`): call stack at **the current execution point**.

### 38.1. Demonstration of the Difference

```sql
DO $do$
DECLARE
    v_error_context TEXT;
    v_current_context TEXT;
BEGIN
    BEGIN
        PERFORM 1 / 0;

    EXCEPTION WHEN division_by_zero THEN
        GET STACKED DIAGNOSTICS
            v_error_context = PG_EXCEPTION_CONTEXT;

        GET DIAGNOSTICS
            v_current_context = PG_CONTEXT;

        RAISE NOTICE 'Error context: %', v_error_context;
        RAISE NOTICE 'Handler context: %', v_current_context;
    END;
END;
$do$;
```

### 38.2. Why Distinguish Them?

When a handler sits in an outer function calling deeper functions, the error's origin stack differs from the handler's current stack. Logging only the handler location misses where the failure actually happened.

### 38.3. Never Treat Stack Text as a Stable API

Context strings are for diagnostics; function names, line numbers, and formatting can change across migrations and PostgreSQL versions. Use `SQLSTATE` and constraint metadata for structured branching.

---

## 39. RAISE Inside Loops: Choosing Severity and Reducing Noise

A large batch may iterate over hundreds of thousands of rows. Running:

```sql
RAISE NOTICE 'Processing request %', v_request_id;
```

for every row creates massive message volume, causing:

- Formatting and transmission overhead.
- Log noise.
- Increased server-to-client network traffic.
- Important errors buried in noise.
- Significant job slowdowns.

### 39.1. Milestone Progress Pattern

In batches, emit `NOTICE` every 1,000 rows or at completion:

```sql
IF v_processed > 0
   AND v_processed % 1000 = 0 THEN
    RAISE NOTICE 'Processed % rows', v_processed;
END IF;
```

### 39.2. DEBUG for Detailed Diagnostics

Temporary diagnostics can use `DEBUG` filtered by session settings, still keeping message-creation cost and data privacy in mind.

### 39.3. WARNING Does Not Replace a Rejected-Rows Table

If each bad input row must be tracked for remediation, insert structured rejection records in the appropriate transaction. `WARNING` is only a notification stream, not a queryable table.

### 39.4. EXCEPTION for Fatal Errors

Never downgrade a rollback-worthy error to `WARNING` just to keep a job "green" if continuing corrupts data. Failing loudly is essential operational behavior.

---

## 40. Java/JDBC Interface: Reading SQLSTATE Instead of Parsing Messages

In Java, PostgreSQL's JDBC driver surfaces database errors via `SQLException` or appropriate subclasses.

Example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class InventoryRepository {

    public long reserve(
            Connection connection,
            String sku,
            int quantity
    ) throws SQLException {

        String sql = """
            SELECT plpgsql_errors_lab.reserve_stock(?, ?)
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {

            ps.setString(1, sku);
            ps.setInt(2, quantity);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Function did not return a movement id"
                    );
                }
                return rs.getLong(1);
            }
        }
    }
}
```

### 40.1. Classifying by SQLSTATE

```java
try {
    long movementId = repository.reserve(conn, sku, quantity);
    // Report success only after the transaction commits.

} catch (SQLException e) {
    String state = e.getSQLState();

    if ("PZ001".equals(state) || "PZ002".equals(state)) {
        // Validation error: invalid input data.
    } else if ("PZ003".equals(state)) {
        // SKU does not exist.
    } else if ("PZ004".equals(state)) {
        // Insufficient stock.
    } else if ("23505".equals(state)) {
        // UNIQUE violation: inspect constraint semantics.
    } else if ("40001".equals(state)
            || "40P01".equals(state)) {
        // Bounded full-transaction retry may be appropriate.
    } else {
        // Unmapped error: propagate and alert.
        throw e;
    }
}
```

This snippet illustrates error classification, **not a complete transaction manager**.

### 40.2. Roll Back the Transaction After an Error

In JDBC with `autoCommit=false`, once a statement fails unhandled on the server, the connection enters a failed transaction state. The application must `rollback()` per policy before running any new transaction.

### 40.3. Never Classify Errors Using getMessage()

`e.getMessage()` mixes detail, hint, and version- or locale-dependent text. Use `getSQLState()` for stable classification.

### 40.4. JDBC Driver Metadata Extensions

PgJDBC exposes driver-specific APIs for server error fields such as `DETAIL`, `HINT`, and constraint name. If used, isolate driver-specific dependencies and never leak sensitive fields into HTTP responses.

### 40.5. HTTP Status Mapping Belongs to the API Layer

One reasonable mapping:

| SQLSTATE | Illustrative API Handling |
|---|---|
| `PZ001`/`PZ002` | Clear input error, e.g., HTTP 400 |
| `PZ003` | Product not found, e.g., HTTP 404 |
| `PZ004` | Stock conflict, e.g., HTTP 409 |
| `23505` | Conflict when uniqueness is genuinely violated |
| `40001`/`40P01` | Retry whole transaction; report transient failure if exhausted |
| Unknown SQLSTATE | Hide internal details; log/alert and return appropriate 5xx |

This is an **application design choice**, not a built-in PostgreSQL mapping.

---

## 41. Java Transaction Retry: Never Catch and Re-Run One SELECT

For `40001` or `40P01`, retries must start a fresh transaction.

Java pseudocode:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);

        try {
            // All business logic must stay in one transaction.
            // Never trigger non-idempotent external side effects
            // before commit is guaranteed.
            performBusinessWork(conn);

            conn.commit();
            return;

        } catch (SQLException e) {
            try {
                conn.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            String state = e.getSQLState();
            boolean retryable =
                    "40001".equals(state)
                 || "40P01".equals(state);

            if (!retryable || attempt == maxAttempts) {
                throw e;
            }

            // Real applications add bounded backoff and jitter.
        }
    }
}
```

### 41.1. Retry All Business Decisions

If the transaction reads stock, selects a warehouse, creates a reservation, and writes logs, all of those steps must re-run together on retry—never re-run only the final statement with stale decisions.

### 41.2. Timeouts and Cancellation

If the request was canceled, do not retry endlessly. Cancellation has different semantics from deadlocks and serialization failures.

### 41.3. Ensure Safe Idempotent Retries

Idempotency keys, unique constraints, and the outbox pattern prevent creating duplicate orders or double-sending messages when a client is uncertain whether the previous attempt committed.

### 41.4. Never Retry Input Errors

`PZ002` will not become valid after three retries if the client keeps sending a negative quantity. Return a clear error to the caller immediately.

---

## 42. Error Boundary Between Database and Application

A clean layered design:

```text
Request / Java / API
        |
        | bind parameters, authenticate tenant
        v
Application service / transaction boundary
        |
        | call PL/pgSQL function
        v
PostgreSQL function
        |
        +-- validate input -> PZ001/PZ002
        +-- data operations -> constraints, 23xxx
        +-- business state -> PZ003/PZ004
        +-- deadlock/serialization -> 40xxx
        |
        v
SQLException / SQLSTATE / structured error fields
        |
        +-- input error  -> guide user
        +-- out of stock -> handle conflict
        +-- transient    -> bounded transaction retry
        +-- unexpected   -> rollback + alert
```

### 42.1. What Is the Database Responsible For?

- Enforcing invariants with `PK`/`UNIQUE`/`CHECK`/`FK`.
- Validating business rules close to data where designed.
- Emitting meaningful `SQLSTATE`s.
- Maintaining transactional consistency.

### 42.2. What Is the Application Responsible For?

- Authentication and authorization.
- Early input validation for good UX.
- Transaction management and retries.
- Mapping errors to HTTP/UI responses.
- Logging, tracing, monitoring, and redaction.
- Idempotency across external systems.

### 42.3. Never Strip SQLSTATE Across Layers

If a repository catches `SQLException` and throws a bare `RuntimeException("Database error")` with no cause or error code, the service layer cannot tell whether to retry.

When wrapping exceptions, preserve the cause and expose a classification code.

### 42.4. Never Reuse One Business Code for Unrelated Errors

`PZ004` should consistently mean `"insufficient stock"` or one error family with uniform handling. Never reuse `PZ004` for `"invalid login"` or `"expired token"`.

---

## 43. Security of Error Messages

Detailed error messages aid debugging, yet also create a data-leakage surface.

### 43.1. Never Expose Another Tenant's Row Data

A handler might emit:

```sql
DETAIL = format(
    'User % owns account %, balance %',
    v_user, v_account, v_balance
)
```

If the caller is unauthorized to view those details, the error message itself leaks sensitive data. Never assume a transaction rollback hides an already-emitted error message.

### 43.2. Separate Public Messages from Internal Logs

An API can return:

```text
errorCode: INVENTORY_UNAVAILABLE
message: Product currently out of stock
```

while internal logs store `SQLSTATE`, request ID, and policy-approved non-sensitive context. Never return raw `PG_EXCEPTION_CONTEXT` to untrusted clients.

### 43.3. SECURITY DEFINER Functions

When a function executes with elevated owner privileges, audit all queries, `DETAIL`, and `HINT` text carefully. Enforce authorization not only on returned rows, but also on **data leaked via error messages**.

### 43.4. search_path and Called Functions

In `SECURITY DEFINER` code, schema-qualify all key objects and set a safe `search_path` per PostgreSQL documentation. Resolving an unintended object can cause errors or execute untrusted code.

### 43.5. Input Sanitization

`RAISE` does not replace input validation or prepared statements. When echoing user input into logs or messages, avoid blindly injecting raw untrusted or sensitive strings.

---

## 44. When to Use RAISE NOTICE vs. SELECT Result Sets?

Suppose a batch function wants to report counts:

```text
Processed 2 rows
Skipped 3 rows
```

Two channels exist:

1. **Result data** — `RETURNS TABLE(processed_count, rejected_count)`.
2. **Notification** — `RAISE NOTICE 'Processed ...'`.

### 44.1. Primary Data Should Be Structured Output

Whenever the application branches on `processed_count`, return values or table outputs are far more reliable and programmatic than parsing `NOTICE` text.

### 44.2. NOTICE Fits Human Operators

In migrations, `psql` scripts, and maintenance tasks, `NOTICE` helps operators observe progress.

### 44.3. NOTICEs Can Be Filtered or Ignored by Drivers

Clients, drivers, and message filters vary in how they surface notices. Never build a business protocol requiring a `NOTICE` string to always reach the UI.

### 44.4. WARNING Is a Signal, Not an Error Contract

If 10 input rows were rejected while the batch completed per policy, `rejected_count` and the `rejected_requests` table form the contract; `WARNING` is merely supplementary.

---

## 45. Observing and Testing PL/pgSQL Error Handling

A lab should verify at least these scenarios:

| Scenario | How to Trigger | Expected Outcome |
|---|---|---|
| Success | `reserve` SKU-100, quantity=1 | Movement ID returned, stock reduced in transaction |
| NULL SKU | `reserve(NULL, 1)` | `PZ001` |
| Quantity=0 | `reserve(SKU-100, 0)` | `PZ002` |
| Missing SKU | `reserve(SKU-UNKNOWN, 1)` | `PZ003` |
| Insufficient stock | `reserve(SKU-300, 99)` | `PZ004` |
| Duplicate SKU | `INSERT` SKU-100 | `23505` |
| Negative stock | `INSERT` product `stock=-1` | `23514` |
| Invalid FK | `INSERT` movement with nonexistent `product_id` | `23503` |
| Missing `SELECT STRICT` | `SELECT INTO STRICT` missing SKU | `P0002` |
| Multi-row `SELECT STRICT` | `SELECT INTO STRICT` without unique filter | `P0003` |
| Divide by zero | `PERFORM 1/0` | `22012` |
| Default `RAISE EXCEPTION` | `RAISE EXCEPTION '...'` | `P0001` |
| `RAISE NOTICE` | `RAISE NOTICE '...'` | Does not fail statement |
| `RAISE WARNING` | `RAISE WARNING '...'` | Does not fail statement |
| `RAISE;` | Catch error then `RAISE;` | Original code preserved |
| Block rollback | `INSERT` then `RAISE` in inner block | Inner `INSERT` rolls back |
| Variable retention | Variable incremented before `RAISE` | Variable keeps value at error |
| Handler logging | `INSERT` rejection in handler | Persists if outer transaction commits |
| Outer rollback | `ROLLBACK` after batch | All normal DML in transaction rolls back |
| Query cancel | Cancel a running query | Not swallowed by `OTHERS` by default |
| Assert failure | `ASSERT false` when enabled | `P0004`; not caught by `OTHERS` by default |

### 45.1. Using Test Transactions

For temporary DML experiments:

```sql
BEGIN;
-- Run test statements.
ROLLBACK;
```

When an unhandled statement errors, PostgreSQL requires `ROLLBACK` before running subsequent statements in that transaction. Never lump independent error tests into one transaction assuming isolation.

### 45.2. Test with Both psql and JDBC

Errors may render differently across `psql`, GUI tools, and JDBC. Verify that **`SQLSTATE` and transaction semantics** never depend on client formatting.

### 45.3. Test Under Target Isolation Levels

For inventory-modifying functions under concurrency, test at actual concurrency and isolation levels (`READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` as designed). Single-session sequential tests never prove race-freeness.

---

## 46. Common Design Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using `WARNING` instead of `EXCEPTION` for invalid data | Statement still succeeds | `RAISE EXCEPTION` or constraint |
| Using `P0001` for every error | Clients cannot distinguish causes | Custom or standard `SQLSTATE` |
| Parsing `SQLERRM` to identify `UNIQUE` violations | Fragile across text/locale changes | `SQLSTATE 23505` + `CONSTRAINT_NAME` |
| Raising `23505` for all input errors | Misleads consumers about constraints | Appropriate custom `SQLSTATE` |
| Custom `SQLSTATE`s without a registry | Collisions and inconsistent meanings | Maintain an error code registry |
| Using `00000` for `EXCEPTION` | Success code, invalid for errors | Choose valid 5-char code |
| Custom codes ending in `000` | Confused with class codes | Avoid `000` suffix |
| Wrong dynamic `RAISE` format syntax | Function fails to compile | `USING MESSAGE = format(...)` |
| Missing expression for `%` placeholder | Invalid format | Match placeholders and arguments |
| Putting tokens/PII into `DETAIL` | Leaks data via errors/logs | Redact and minimize |
| Using `NOTICE` to return business data | Clients can filter or ignore it | `RETURN` / `RETURNS TABLE` |
| Thinking hidden `NOTICE` means function didn't run | Confuses logging config with execution | Check `client_min_messages` |
| Treating `INFO` like `NOTICE` for filtering | `INFO` has special client rules | Understand client delivery rules |
| Assuming `LOG` always goes to clients | Server vs. client thresholds differ | Check logging configuration |
| Catching `OTHERS` and returning `TRUE` | Swallows data/infra errors | Catch specifically or `RAISE;` |
| Assuming `OTHERS` catches `query_canceled`/`assert_failure` | False assumption | Handle per specific rules |
| Catching `23505` and assuming "duplicate SKU" | Could be another unique constraint | Inspect `CONSTRAINT_NAME` |
| Swallowing `40001`/`40P01` as business errors | Skips transaction retry | Retry full transaction |
| Retrying input errors infinitely | Wastes resources and still fails | Classify retryable errors |
| `RAISE EXCEPTION SQLERRM` instead of `RAISE;` | Loses original `SQLSTATE`/context | Use `RAISE;` |
| Logging the same error at every layer | Duplicate noisy alerts | Define logging ownership |
| Thinking `EXCEPTION` rolls back the entire transaction | Confuses subtransaction scope | Scope blocks explicitly |
| Assuming local variables roll back | Counters report wrong numbers | Increment after fallible steps |
| Assuming `INSERT error_log` in handler auto-commits | Outer `ROLLBACK` deletes logs | Use out-of-transaction auditing |
| Per-row exception blocks in huge batches | Subtransaction overhead | Use set-based / `ON CONFLICT` |
| `SELECT stock` then unguarded `UPDATE` | Race condition | Conditional `UPDATE` / locking |
| Assuming diagnostic `SELECT` shares `UPDATE`'s snapshot | Concurrency can change stock | Label `available_at_check` |
| Dropping constraints because functions validate | Other write paths bypass functions | Keep `CHECK`/`UNIQUE`/`FK` |
| Non-STRICT `SELECT INTO` expecting 1 row | Picks arbitrary row on duplicates | `STRICT` or unique + `ORDER BY` |
| Using `STRICT` when 0 rows is normal | Unnecessary exception overhead | Inspect `FOUND` |
| Confusing `GET DIAGNOSTICS` with `GET STACKED DIAGNOSTICS` | Reads wrong context | Use the right command |
| Expecting a handler to catch errors thrown by itself | Wrong scope | Use an outer block if needed |
| Thinking functions self-`COMMIT` | Reporting success before `COMMIT` | Keep transaction boundary in caller |
| Catching `COMMIT` errors inside a function handler | Deferred constraints fail after return | Handle `COMMIT` in application |
| Misusing `ASSERT` for input validation | Can be disabled, wrong purpose | Use `RAISE`/constraints |
| `SECURITY DEFINER` leaking data in `DETAIL` | Error-channel data leak | Guard permissions and messages |
| Using `RAISE LOG` as durable compliance audit | May not meet retention policies | Dedicated audit pipeline/table |
| Treating HTTP status = `SQLSTATE` | Two separate code systems | Explicit mapping layer |
| Using `getMessage` instead of `getSQLState` | Fragile | Inspect `SQLSTATE` field |
| Skipping `ROLLBACK` after JDBC errors | Connection stays in aborted state | Manage transaction cleanup |
| Testing with only one session | Misses concurrency bugs | Test concurrently |
| Skipping `COMMIT`-time error tests | Misses deferred constraints | Test full transaction lifecycle |
| Unbounded retries | Infinite retry loops | Enforce max attempts and backoff |
| Missing idempotency | Retries duplicate side effects | Idempotency keys / outbox |

---

## 47. Practice Exercises

### Exercise 1 — RAISE NOTICE

Write a `DO` block emitting a `NOTICE` with product code and quantity using `%` placeholders. Why does `NOTICE` not fail the statement?

### Exercise 2 — RAISE WARNING

Emit a `WARNING` when an optional value is missing while letting the block continue. Contrast this with `EXCEPTION`.

### Exercise 3 — Six Message Levels

Write a `DO` block emitting `DEBUG`, `LOG`, `INFO`, `NOTICE`, and `WARNING` in sequence. Experiment with `SET LOCAL client_min_messages` inside a transaction and observe which levels appear at the client.

### Exercise 4 — Special INFO Behavior

Explain why `INFO` does not follow the same client-side filtering as every other level. Never mistake it for `EXCEPTION`.

### Exercise 5 — Formatting % and %%

Emit `"Progress 75%"` using a `RAISE` format literal and a variable holding `75`.

### Exercise 6 — Dynamic MESSAGE

Use `RAISE NOTICE USING MESSAGE = format(...)` to construct a message with SKU and quantity. Why is `RAISE NOTICE format(...)` invalid?

### Exercise 7 — DETAIL and HINT

Raise a simulated `"insufficient stock"` error with `MESSAGE`, `DETAIL`, `HINT`, and `ERRCODE`.

### Exercise 8 — Default Code P0001

Emit `RAISE EXCEPTION 'demo'` without specifying an SQLSTATE, catch it with `WHEN raise_exception`, and inspect the code. Why is `P0001` insufficient to classify all business errors?

### Exercise 9 — Custom SQLSTATE

Define `PZ010` for a new internal error type. Write `RAISE EXCEPTION USING ERRCODE` and a `WHEN SQLSTATE 'PZ010'` handler.

### Exercise 10 — SQLSTATE Classes

Explain the first two characters and last three characters of `23505`. Name two other errors in class `23`.

### Exercise 11 — UNIQUE

Attempt inserting `SKU-100` a second time inside an `EXCEPTION` block, catch `unique_violation`, and read `CONSTRAINT_NAME`.

### Exercise 12 — CHECK

Attempt inserting a product with `stock = -1`. Capture the `SQLSTATE` and constraint name without parsing message text.

### Exercise 13 — FOREIGN KEY

Attempt inserting a movement with a nonexistent `product_id`. Catch the appropriate error and explain why the transaction must not still record the movement.

### Exercise 14 — NOT NULL

Attempt inserting a product with `sku = NULL`. How do you distinguish its `SQLSTATE` from a `CHECK` violation?

### Exercise 15 — SELECT INTO STRICT: No Rows

Run `SELECT INTO STRICT` for a nonexistent SKU and catch `no_data_found`. Contrast with non-STRICT `SELECT INTO` and `FOUND`.

### Exercise 16 — SELECT INTO STRICT: Multiple Rows

Run `SELECT INTO STRICT product_id` across all products and catch `too_many_rows`. How do you fix the query so the "exactly one product" contract holds?

### Exercise 17 — FOUND and ROW_COUNT

Run an `UPDATE` for a nonexistent SKU, then check `FOUND` and `GET DIAGNOSTICS ROW_COUNT`. Why is 0 rows not automatically an SQL error?

### Exercise 18 — GET STACKED DIAGNOSTICS

From a `CHECK` error, retrieve `RETURNED_SQLSTATE`, `MESSAGE_TEXT`, `PG_EXCEPTION_DETAIL`, `PG_EXCEPTION_HINT`, and `CONSTRAINT_NAME`.

### Exercise 19 — PG_EXCEPTION_CONTEXT

Inside a handler, compare `PG_EXCEPTION_CONTEXT` with `GET DIAGNOSTICS PG_CONTEXT`. Which one describes where the error actually originated?

### Exercise 20 — Rethrowing with RAISE;

Catch `division_by_zero`, emit a `NOTICE` showing `SQLSTATE`, then execute `RAISE;` to propagate the error to the caller. Why must you not replace `RAISE;` with `RAISE EXCEPTION '%', SQLERRM`?

### Exercise 21 — Error Inside a Handler

Write a handler catching `PZ001` and raising `PZ002`. Only an outer block catches `PZ002`. Trace the control flow.

### Exercise 22 — WHEN OTHERS

Write an `OTHERS` handler that logs and runs `RAISE;`, and name two conditions `OTHERS` does not catch by default.

### Exercise 23 — Inner Block Rollback

Inside a lab transaction, `INSERT` one row outside an exception block, `INSERT` a second row inside the inner block, then raise an `EXCEPTION`. Verify the second row rolls back while the first row remains visible until the outer `ROLLBACK`.

### Exercise 24 — Variables Do Not Roll Back

Increment a PL/pgSQL variable in an inner block before raising an error, then print it in the handler. Explain why the variable still holds the incremented value.

### Exercise 25 — Logging Inside a Handler

Inside an exception handler, `INSERT` into `rejected_requests`. Inspect the table before and after an outer `ROLLBACK`. Does a handler auto-commit?

### Exercise 26 — Successful reserve_stock

Run `reserve_stock('SKU-100', 2)` inside a transaction, inspect stock and movements, then `ROLLBACK`. Why should you confirm success only after `COMMIT`?

### Exercise 27 — Insufficient Stock

Call `reserve_stock` with `quantity = 999`. Inspect code `PZ004` and `DETAIL`. Why is `available_at_check` only a diagnostic snapshot under concurrency?

### Exercise 28 — Missing SKU

Call `reserve_stock` for `SKU-UNKNOWN`. Why is `PZ003` better than `"23505 duplicate key"`?

### Exercise 29 — NULL Inputs

Call `validate_reservation(NULL, 1)` and `validate_reservation('SKU-100', NULL)`. Predict the `SQLSTATE` for each.

### Exercise 30 — Checking Race Conditions

Describe two concurrent sessions each trying to reserve 7 units when only 8 exist. Why is a conditional `UPDATE` checking `stock >= quantity` better than `SELECT` followed by `UPDATE` using stale values?

### Exercise 31 — Batch Per-Row Exceptions

Run `process_stock_batch(1)` inside a transaction and `ROLLBACK`. Predict `processed_count` and `rejected_count` on clean baseline data.

### Exercise 32 — Never Swallow System Errors

Modify the batch function so an `OTHERS` handler logs and runs `RAISE;` instead of treating every error as a rejected request. Why must `40001` never be swallowed?

### Exercise 33 — ON CONFLICT

Replace a product `INSERT` using an `EXCEPTION WHEN unique_violation` block with `INSERT ... ON CONFLICT(sku) DO NOTHING`. Which business scenario fits best?

### Exercise 34 — Exception Overhead

Describe a benchmark of 1 million rows with 0%, 1%, and 50% error rates comparing per-row exception handlers against set-based SQL. Which metrics should you measure?

### Exercise 35 — Triggers

Create the trigger blocking blank `display_name` values. Compare it against `CHECK(BTRIM(display_name) <> '')` in simplicity, performance, and applicability.

### Exercise 36 — Deferred Constraints

A transaction using a deferred foreign key can fail at `COMMIT`. Why can a function that already `RETURN`ed not catch an error that had not occurred yet?

### Exercise 37 — Deadlocks and Serialization Failures

Design a retry policy for `40P01` and `40001`. Why must you retry the whole transaction rather than only the last statement?

### Exercise 38 — Query Cancellation

Explain `query_canceled` (`57014`) and why `WHEN OTHERS` ignores it by default. Should client cancel requests ever be ignored?

### Exercise 39 — ASSERT

Use `ASSERT` to check an internal invariant. Explain why `ASSERT` should not replace `CHECK` constraints or `RAISE EXCEPTION` for business inputs.

### Exercise 40 — JDBC getSQLState

Write a Java `PreparedStatement` calling `reserve_stock`, catching `SQLException`, and distinguishing `PZ002`, `PZ004`, `23505`, `40001`, and `40P01` via `getSQLState()`.

### Exercise 41 — HTTP Error Mapping

Design a mapping from `PZ001`/`PZ002`/`PZ003`/`PZ004` to HTTP `400`/`404`/`409` per an API contract. Why can HTTP codes not be universally inferred from `SQLSTATE` alone?

### Exercise 42 — Safe Messages

Propose `MESSAGE`, `DETAIL`, and `HINT` for an `"unauthorized account access"` error without leaking whether the account exists or another user's balance.

### Exercise 43 — Durable Auditing

A system must retain failure logs even when the business transaction rolls back. Why does an `INSERT` into a log table inside a handler fall short? Propose an out-of-transaction logging/audit approach.

### Exercise 44 — Versioned Custom Error Codes

Create a specification table for codes `PZ001`–`PZ006`, detailing ownership, retryability, public message, and permitted log metadata.

### Exercise 45 — RAISE LOG/NOTICE in Large Jobs

A job processes 500,000 rows. Design a milestone notification policy, severity choices, and metrics to avoid emitting 500,000 `NOTICE`s.

### Exercise 46 — Full Workflow

Design a production ordering workflow: validate inputs, deduct stock atomically, log movement, record idempotency key, `COMMIT`, handle `SQLSTATE` in Java, retry transactions appropriately, and alert on unexpected errors. Specify which steps belong in the DB transaction and which belong in external systems.

---

## 48. PL/pgSQL Exception-Handling Checklist

| Question | How to Verify |
|---|---|
| Are notices distinguished from real errors? | `NOTICE`/`WARNING` vs. `EXCEPTION` |
| Is the message level right? | `DEBUG`/`LOG`/`INFO`/`NOTICE`/`WARNING`/`EXCEPTION` |
| Are clients guaranteed to see notices? | `client_min_messages`/driver |
| Does the server log record messages? | `log_min_messages`/log configuration |
| Does logic depend on `NOTICE` visibility? | Never use messages for control flow |
| Is `RAISE` format syntax valid? | `%`/`%%` placeholders match arguments |
| Are messages structured? | `MESSAGE`/`DETAIL`/`HINT` |
| Is `ERRCODE` set when classification is needed? | Standard or custom `SQLSTATE` |
| Is `SQLSTATE` 5 valid characters? | Valid format, never `00000` |
| Do custom codes have a registry? | No collisions, stable semantics |
| Are messages parsed for error types? | Use `SQLSTATE`, never text parsing |
| Is constraint metadata inspected? | `CONSTRAINT_NAME` where appropriate |
| Do handlers match specific conditions? | `unique_violation`/`check_violation`/... |
| Is `WHEN OTHERS` present? | Justify why, and check if it rethrows |
| Remember `OTHERS` skips cancel/assert? | `query_canceled`/`assert_failure` |
| Is `RAISE;` used to preserve original errors? | Avoid accidentally turning into `P0001` |
| Are `SQLSTATE`/`SQLERRM` only used in handlers? | Valid handler scope |
| Is `GET STACKED DIAGNOSTICS` used? | `RETURNED_SQLSTATE`/`DETAIL`/`HINT`/`CONTEXT` |
| Is `GET DIAGNOSTICS ROW_COUNT` understood? | Distinct from stacked diagnostics |
| Is `FOUND` understood? | 0 rows is not necessarily an exception |
| Is `SELECT INTO STRICT` used appropriately? | `P0002`/`P0003` |
| Is block rollback scope clear? | Subtransaction covers only `EXCEPTION` block |
| Do variables change before errors? | Variables do not roll back |
| Does the handler insert error logs? | Commit still depends on outer transaction |
| Are there external non-DB side effects? | Rollback does not undo external effects |
| Could deferred constraints fail at `COMMIT`? | Catch at transaction boundary |
| Does the app commit before confirming success? | Never confuse function return with commit |
| Are underlying table constraints present? | `PK`/`UNIQUE`/`CHECK`/`FK` guard all writes |
| Are concurrency checks strong enough? | Conditional `UPDATE`/locking |
| Are business errors separated from infra errors? | `PZxxx` vs. `40xxx`/`23xxx` |
| Are full transactions retried? | `40001`/`40P01` |
| Are retries bounded with backoff? | No infinite loops |
| Is idempotency enforced? | Prevent duplicate side effects |
| Are per-row handlers justified? | Only when needed and benchmarked |
| Could `ON CONFLICT` replace handlers? | Expected duplicates |
| Is tenant access enforced? | Auth/RLS/privileges |
| Are PII/secrets kept out of errors? | Redaction and safe public messages |
| Tested with real non-superuser roles? | Never test only as superuser |
| Does JDBC use `getSQLState()`? | Never parse `getMessage()` |
| Does JDBC roll back after errors? | Clean transaction state |
| Is HTTP mapping defined separately? | `SQLSTATE` differs from HTTP status |
| Are events/metrics recorded? | Observable error rates |
| Tested cancel and assert paths? | Never swallow operational signals |
| Tested NULL, negative, and duplicate inputs? | Negative test paths |
| Tested concurrent requests? | Races/deadlocks/serialization |
| Verified log visibility? | Client and server visibility |
| Is the `SQLSTATE` contract documented? | Ownership/versioning |
| Checked post-migration impact? | Constraints and handlers |
| Deployment and rollback plan ready? | Transactions and versioning |

## Conclusion

**`RAISE`, message levels, `SQLSTATE`, and `EXCEPTION`** let PL/pgSQL communicate clearly with users, applications, and operational tooling. Beyond formatting nicer error messages, these features form a core part of your data contract, access control, and transactional consistency.

Core principles:

1. **`RAISE` has multiple levels, but only `EXCEPTION` raises a catchable failure.** `NOTICE`/`WARNING` do not roll back data.
2. **`SQLSTATE` is the programmatic error-classification channel.** Never branch by parsing mutable error text.
3. **Use `MESSAGE`, `DETAIL`, and `HINT` appropriately.** Messages must be helpful without leaking secrets or unauthorized data.
4. **Define custom error codes deliberately.** Preserve standard PostgreSQL codes for DB errors and register custom codes like `PZ001`–`PZ006` clearly.
5. **Scope handlers tightly.** Catch specific errors when safe recovery exists; never use `WHEN OTHERS` to return fake success.
6. **`RAISE;` preserves the original error.** When logging diagnostics before propagating, rethrow rather than generating a new `P0001`.
7. **`EXCEPTION` blocks use subtransaction semantics.** DML inside the block body rolls back when caught; PL/pgSQL variables do not revert, and the outer transaction still controls `COMMIT`/`ROLLBACK`.
8. **`GET STACKED DIAGNOSTICS` delivers structured metadata.** Inspect `RETURNED_SQLSTATE` and `CONSTRAINT_NAME` instead of guessing from prose.
9. **Do not use exceptions for routine expected paths.** `FOUND`, `ROW_COUNT`, `ON CONFLICT`, and conditional `UPDATE`s are often clearer and faster.
10. **Put retries at the right layer.** For `40001` and `40P01`, retry the entire transaction with bounded attempts and idempotency.
11. **Never confirm success before `COMMIT`.** Deferred constraints and transaction failures can surface after a function returns.
12. **Design the full database–application flow.** PostgreSQL emits codes, Java reads `getSQLState()`, services roll back/retry/map errors, and logging/audit pipelines protect privacy and durability.

A reliable PostgreSQL system is not one that "never encounters errors," but one that **detects errors accurately, emits stable codes, rolls back the right scope, never hides data corruption, and lets the application choose the next action safely**.
