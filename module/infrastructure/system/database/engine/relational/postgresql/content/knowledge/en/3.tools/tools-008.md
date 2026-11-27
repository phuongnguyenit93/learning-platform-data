# Reading SQLSTATE and Error Messages from the Server

When running SQL on PostgreSQL, applications receive more than just a pass-or-fail outcome. When an error occurs, the server returns a **SQLSTATE code**, **message severity**, **error message**, and in many cases **DETAIL**, **HINT**, SQL statement position, table name, or constraint name. Knowing how to read these fields accurately speeds up root-cause analysis, enables reliable error handling in Java, and avoids writing logic that depends on mutable wording.

For example, if you insert two accounts with the same email into a `UNIQUE` column, PostgreSQL typically returns **SQLSTATE `23505`** with the condition name `unique_violation`. The message `duplicate key value violates unique constraint ...` is helpful for human explanation, but **`23505` is the stable code your program should use to classify the error**. If a subsequent SQL statement fails with `25P02`, the problem may not lie in the new statement itself: the transaction is already in a failed state due to an earlier error.

This lesson focuses on **tools for reading and leveraging PostgreSQL errors**: SQLSTATE format, server response fields, `psql` usage, extracting SQLSTATE via JDBC/pgJDBC, handling errors in PL/pgSQL, distinguishing root errors from downstream consequences, and building a repeatable diagnostic workflow.

> Examples are written for modern PostgreSQL and Java applications using JDBC. Creating tables and triggering intentional errors should be performed only in a **test database**. Exact message text varies by version, locale, object names, and context, so never copy sample message strings verbatim into production checks.

## 1. What does a PostgreSQL error report include?

The PostgreSQL server sends structured responses over the wire protocol. For errors as well as non-error notices, clients may receive a set of **diagnostic fields**. Not every error provides all fields.

| Conceptual field | Example | What is it for? |
|---|---|---|
| **Severity** | `ERROR`, `FATAL`, `WARNING`, `NOTICE` | Severity level of the notice, distinguishing statement errors, session termination, or informational notices. |
| **SQLSTATE** | `23505` | A **5-character code** identifying the condition class without parsing message text. |
| **Message** | `duplicate key value violates unique constraint "uq_accounts_email"` | Primary human-readable description. |
| **Detail** | `Key (email)=(an@example.com) already exists.` | Additional data explaining the cause. |
| **Hint** | `...` | Suggested fix, when supplied by the server. |
| **Position** | `42` | Character position in the offending query; useful for syntax or column-name typos. |
| **Where/Context** | `PL/pgSQL function ... line ...` | Call context inside a function, trigger, or nested SQL. |
| **Schema/Table/Column/Constraint** | `public` / `accounts` / `email` / `uq_accounts_email` | Identifiers of related objects, when supplied. |
| **Internal File/Line/Routine** | PostgreSQL source file and function name | Primarily for deep diagnostics, especially internal server errors. |

Default `psql` output on a duplicate-key insert looks like:

```text
ERROR:  duplicate key value violates unique constraint "uq_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

In default mode, users may **not see SQLSTATE printed**, even though the server sent it. You can ask `psql` to display it or inspect the field directly via the JDBC API.

### The crucial difference between code and message

The **message** provides context for human reading. **SQLSTATE** provides a stable identifier for programmatic decisions. An application should not check:

```java
// Avoid: depends on message wording that can change.
if (ex.getMessage().contains("duplicate key value")) {
    // ...
}
```

Instead, use:

```java
// Better classification when the exception is a SQLException.
if ("23505".equals(ex.getSQLState())) {
    // Unique violation; verify the exact constraint before deciding how to handle.
}
```

Even `23505` alone is not enough to conclude **that it was a duplicate email**, since a table can have multiple unique constraints. When business logic must distinguish specific cases, also inspect the **constraint name**, table name, and statement being executed.

## 2. How is SQLSTATE structured?

A SQLSTATE consists of **5 alphanumeric characters**. In standard classification, the first two characters identify the **class** (condition group), and the remaining three characters identify the **subclass** or specific condition within that group.

```text
SQLSTATE = 23505
           ├─ "23"  → class: integrity constraint violation
           └─ "505" → subclass: unique_violation

Simple layout:
       23        505
      class    subclass
```

For instance, `23505` belongs to class `23` (*integrity constraint violation*), specific condition `unique_violation`. In `42P01`, the first two characters are `42` and the last three are `P01`; **not all SQLSTATE codes are strictly numeric**.

To read them clearly, split them:

```text
23505  →  23 | 505  → integrity constraint violation / unique_violation
23503  →  23 | 503  → integrity constraint violation / foreign_key_violation
40P01  →  40 | P01  → transaction rollback / deadlock_detected
42P01  →  42 | P01  → syntax/access rule / undefined_table
P0001  →  P0 | 001  → PL/pgSQL / raise_exception
```

Code `00000` indicates **successful completion** in the SQLSTATE system. For normal SQL errors, the client receives a code other than `00000`. Notices at `NOTICE` or `WARNING` severity may arrive through a separate notice channel rather than throwing an exception like `ERROR`.

### Why are class prefixes useful?

Codes in the same class suggest an initial direction for investigation:

| Class | Error or condition group | Initial direction |
|---|---|---|
| `00` | Successful completion | Operation succeeded per status code. |
| `01` | Warning | Warning; does not necessarily abort the statement. |
| `02` | No data | No data returned in specific contexts. |
| `08` | Connection exception | Connection or communication stream to the server. |
| `22` | Data exception | Invalid data value or representation. |
| `23` | Integrity constraint violation | Violation of `NOT NULL`, `UNIQUE`, foreign key, or `CHECK`. |
| `25` | Invalid transaction state | Transaction is not in a state permitting the operation. |
| `28` | Invalid authorization specification | Authentication and login privileges. |
| `3D` | Invalid catalog name | Target database does not exist. |
| `40` | Transaction rollback | Requires transaction error handling, often concurrency-related. |
| `42` | Syntax error or access rule violation | Syntax error, wrong table/column name, permissions, or access rules. |
| `55` | Object not in prerequisite state | Object or lock is not in the required state. |
| `57` | Operator intervention | Query cancellation or other administrative intervention. |
| `P0` | PL/pgSQL error | Condition raised by PL/pgSQL. |
| `XX` | Internal error | Internal error or condition requiring special investigation. |

**Note:** The first two characters point you in a direction; they do not replace the full code. For example, `23505` and `23503` share class `23` yet demand different business handling. Likewise, for class `40`, you must never retry every case infinitely.

## 3. Common SQLSTATE codes in PostgreSQL

Here is a practical set of codes useful when reading logs, using `psql`, or handling exceptions in Java:

| SQLSTATE | PostgreSQL condition name | Common scenario |
|---|---|---|
| `23505` | `unique_violation` | Inserting/updating a duplicate unique or primary key value. |
| `23503` | `foreign_key_violation` | Writing a reference to a nonexistent parent row or deleting a referenced parent row. |
| `23502` | `not_null_violation` | Writing `NULL` into a `NOT NULL` column. |
| `23514` | `check_violation` | Value fails a `CHECK` condition. |
| `22P02` | `invalid_text_representation` | String cannot be parsed as `integer`, `uuid`, etc. |
| `22003` | `numeric_value_out_of_range` | Numeric value exceeds the data type's range. |
| `22001` | `string_data_right_truncation` | String exceeds column length where rejected. |
| `22012` | `division_by_zero` | Division by zero in a calculation. |
| `42601` | `syntax_error` | SQL statement has invalid syntax. |
| `42P01` | `undefined_table` | Referenced relation does not exist. |
| `42703` | `undefined_column` | Specified column does not exist. |
| `42501` | `insufficient_privilege` | Account lacks required privilege. |
| `40001` | `serialization_failure` | Transaction could not complete due to isolation-level concurrency conflict. |
| `40P01` | `deadlock_detected` | PostgreSQL detected a circular lock wait. |
| `55P03` | `lock_not_available` | Could not acquire requested lock, e.g., with `NOWAIT`. |
| `57014` | `query_canceled` | Query canceled by user request or an applicable timeout. |
| `25P02` | `in_failed_sql_transaction` | Transaction already failed; subsequent commands are rejected until rollback. |
| `08006` | `connection_failure` | Connection failure; may originate from server or driver. |
| `28P01` | `invalid_password` | Password authentication failed. |
| `3D000` | `invalid_catalog_name` | Requested database does not exist. |
| `P0001` | `raise_exception` | Default exception raised by PL/pgSQL `RAISE EXCEPTION`. |

This list is not exhaustive across all PostgreSQL codes. Always inspect the **actual SQLSTATE returned** for a specific case rather than guessing codes from statement shape alone.

### Three groups deserving special care in application code

**Data/constraint errors:** `22...` and `23...` usually require fixing input, applying duplicate-key rules, or returning a business error. Retrying the exact same request unmodified will normally fail again.

**Transaction/concurrency errors:** `40001`, `40P01`, and `55P03` can reflect contention. Some work well with a bounded retry policy, provided you retry **the right transaction unit** and preserve business safety.

**Connection or cancellation errors:** `08...` and `57014` can leave the application uncertain whether a write committed if the connection dropped at a critical moment. Verify the outcome using business keys or idempotency rather than blindly re-executing.

## 4. Creating intentional error examples in PostgreSQL

The examples below belong in a **dedicated lab** database.

```sql
CREATE TABLE demo_accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
    CONSTRAINT uq_demo_accounts_email UNIQUE (email),
    CONSTRAINT chk_demo_accounts_balance CHECK (balance >= 0)
);

INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 100.00);

-- Error due to existing email: SQLSTATE 23505.
INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 50.00);
```

The first statement creates the table with constraints; the first `INSERT` succeeds, and the last intentionally triggers a **unique violation**.

Sample output with default fields:

```text
ERROR:  duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

Here:

- **ERROR** is the severity.
- **SQLSTATE `23505`** identifies the unique error, even though it is not printed in this output mode.
- **uq_demo_accounts_email** is the name of the violated unique constraint.
- **DETAIL** identifies the specific key and duplicate value.

Do not log `DETAIL` indiscriminately: key values can contain emails, tokens, account identifiers, or sensitive data.

### Trying other errors

```sql
-- 23502: not_null_violation.
INSERT INTO demo_accounts (email, balance)
VALUES (NULL, 25.00);

-- 23514: check_violation.
INSERT INTO demo_accounts (email, balance)
VALUES ('binh@example.com', -1.00);

-- 22P02: invalid_text_representation.
SELECT 'not-a-number'::INTEGER;

-- 22012: division_by_zero.
SELECT 10 / 0;

-- 42P01: undefined_table.
SELECT * FROM demo_table_does_not_exist;
```

When run individually in `psql` under normal autocommit mode, each raises its own error for observation. **If wrapped inside a single `BEGIN ... COMMIT`**, the first error puts the transaction into a failed state; subsequent statements will usually just return `25P02` until `ROLLBACK`. That important behavior is covered later.

## 5. Displaying SQLSTATE in psql with VERBOSITY

`psql` is PostgreSQL's standard command-line client. It supports backslash **meta-commands** to control how errors are displayed.

### 5.1. Default mode

In an interactive `psql` session:

```text
\set VERBOSITY default
```

When triggering `23505`, `psql` typically shows severity `ERROR`, the primary message, and `DETAIL` if sent by the server. Default mode prioritizes human readability.

### 5.2. Verbose mode

```text
\set VERBOSITY verbose
```

Then run:

```sql
INSERT INTO demo_accounts (email, balance)
VALUES ('an@example.com', 50.00);
```

The output may contain:

```text
ERROR:  23505: duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
SCHEMA NAME:  public
TABLE NAME:  demo_accounts
CONSTRAINT NAME:  uq_demo_accounts_email
LOCATION:  ..., ...:...
```

This snippet illustrates the format; exact metadata lines vary by version and specific error. **The key difference** is that `23505` is displayed, along with extra fields such as PostgreSQL source location and related object names when available.

Verbose mode is especially helpful when:

- You must tell `23505` apart from `23503` or `23514` unambiguously.
- You need the exact name of the violated constraint.
- You are diagnosing errors inside triggers, functions, extensions, or complex queries.
- You need to file an incident report with the exact status code.

### 5.3. Terse mode

```text
\set VERBOSITY terse
```

`terse` omits auxiliary details to keep terminal logs cleaner. It is useful when you want brief notices, though not ideal when searching for detailed error codes and metadata.

### 5.4. Sqlstate mode

```text
\set VERBOSITY sqlstate
```

This mode focuses on the **SQLSTATE code** rather than verbose message text. It is useful for concisely observing error categories or comparing behavior across environments with different display locales.

### 5.5. Reviewing the latest error with \errverbose

Inside interactive `psql`:

```text
\errverbose
```

This meta-command reprints **the most recent server error** in full verbose detail, even if `VERBOSITY` is currently set to a shorter format.

Example sequence:

```text
\set VERBOSITY terse
```

```sql
INSERT INTO demo_accounts(email) VALUES ('an@example.com');
```

```text
\errverbose
```

This lets you keep everyday output concise while requesting full diagnostics only when an error needs investigation.

**Do not confuse** `\errverbose` with server-side SQL: it is a `psql` client command and cannot be sent verbatim via JDBC `Statement.execute(...)`.

## 6. SQLSTATE and ERROR variables in psql scripts

`psql` provides special variables to track the outcome of executed SQL commands, notably `SQLSTATE` and `ERROR`.

While working in `psql`, try:

```text
\set VERBOSITY default
```

```sql
SELECT 1;
```

```text
\echo :SQLSTATE
```

The value is typically `00000` after a successful SQL statement. On a failing statement:

```sql
SELECT 'abc'::integer;
```

```text
\echo :SQLSTATE
```

Here `SQLSTATE` updates to the latest SQL error, typically `22P02` for a string that cannot be converted to integer.

### Context limitations to note

- `SQLSTATE` is a **`psql` client-side variable**, not a server system variable that SQL apps can query arbitrarily via `SELECT SQLSTATE`.
- It tracks the outcome of client-processed SQL commands; do not treat its stored value as a complete history of all errors.
- Subsequent meta-commands, queries, and script execution modes affect when you observe it. When needed in automation, capture it immediately after the relevant SQL statement along with context.
- In Java programs, call `SQLException.getSQLState()` instead of relying on `psql` variables.

### Running scripts and stopping on error

When running a SQL file in a pipeline, use:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d appdb \
  -f migration.sql
```

Flags:

- `-X`: skips reading personal `psqlrc` startup files so script behavior depends less on the user's environment.
- `-v ON_ERROR_STOP=1`: stops script execution on SQL errors instead of continuing through remaining statements.
- `-f migration.sql`: executes SQL commands from the file.

When a script stops due to an error under `ON_ERROR_STOP`, `psql` uses exit status **3** for that case. Other failures such as client-side issues or connection errors return different exit statuses depending on context. **Do not interpret exit code = 3 as "SQLSTATE 00003".** These are two independent numbering systems: exit codes belong to the OS `psql` process, whereas SQLSTATE belongs to PostgreSQL statement diagnostics.

Account and host in the command above are illustrative. Never put passwords directly in command-line arguments or CI logs; use an appropriate authentication/secret mechanism.

## 7. Distinguishing root errors from 25P02 inside transactions

This is one of the most frequently misunderstood situations:

```sql
BEGIN;

-- First statement hits error 23505.
INSERT INTO demo_accounts(email)
VALUES ('an@example.com');

-- Second statement is valid on its own,
-- but the transaction is already marked failed.
SELECT COUNT(*) FROM demo_accounts;
```

In PostgreSQL, after an **ERROR** inside a transaction block, the transaction normally enters an **aborted/failed** state. The subsequent `SELECT COUNT(*)` cannot execute normally; PostgreSQL reports:

```text
ERROR:  current transaction is aborted, commands ignored until end of transaction block
```

This error's code is **`25P02` — `in_failed_sql_transaction`**.

Diagram:

```text
BEGIN
  │
  ▼
INSERT duplicate email
  │
  ├── root error: 23505
  │
  ▼
Transaction enters FAILED state
  │
  ▼
Valid SELECT is still rejected
  │
  └── consequence error: 25P02
  │
  ▼
ROLLBACK to exit the failed state
```

### How to handle properly

In interactive `psql`:

```sql
ROLLBACK;

-- After rollback, a new transaction or
-- autocommit statements can execute normally.
SELECT COUNT(*) FROM demo_accounts;
```

**Do not try to "fix" `SELECT COUNT(*)` just because it received `25P02`.** Find **the first error in the transaction**, which is usually the root cause. A late exception appearing in Java/Hibernate may merely be the consequence of an earlier SQL failure that was caught and ignored.

If you encounter `25P02` in an application:

1. Check logs at the start of the transaction for the SQLSTATE that appeared **before** `25P02`.
2. Ensure the transaction is rolled back via JDBC/Spring transaction management.
3. Never return a connection with an aborted transaction to the pool without clearing its state.
4. Retry the entire business unit only if the root error is retryable and write idempotency is assured.

### SAVEPOINT recovers one branch without discarding the whole transaction

In some workflows, you may want to attempt an operation that can expectedly fail while keeping the rest of the transaction alive. Use `SAVEPOINT`:

```sql
BEGIN;

SAVEPOINT before_optional_insert;

-- Intentionally trigger 23505.
INSERT INTO demo_accounts(email)
VALUES ('an@example.com');

-- In interactive psql, the next statement is allowed
-- to restore the transaction back to the savepoint.
ROLLBACK TO SAVEPOINT before_optional_insert;

SELECT COUNT(*) FROM demo_accounts;

RELEASE SAVEPOINT before_optional_insert;
COMMIT;
```

If you run this example with `psql -v ON_ERROR_STOP=1`, the client will **stop at the error** and will not automatically continue to `ROLLBACK TO SAVEPOINT`; in that case, application-level handling or a deliberately designed control flow is required.

SAVEPOINT is not a tool to hide all errors. If an error means the entire business operation must abort, **rolling back the whole transaction** is cleaner. Using many savepoints at the application layer also adds overhead and complexity.

## 8. Reading errors in Java JDBC via SQLException

In Java applications, the PostgreSQL JDBC Driver (*pgJDBC*) exposes SQL errors via `SQLException` and specialized subclasses. The primary API for retrieving the error code is **`SQLException.getSQLState()`**.

Example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class AccountWriter {
    public static void addEmail(Connection connection, String email)
            throws SQLException {
        String sql = "INSERT INTO demo_accounts(email) VALUES (?)";

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, email);
            statement.executeUpdate();
        } catch (SQLException exception) {
            String sqlState = exception.getSQLState();

            if ("23505".equals(sqlState)) {
                // This is unique_violation.
                // Verify the exact constraint before mapping
                // to a duplicate-email business error.
            }

            throw exception;
        }
    }
}
```

In this example, the exception is **rethrown** so the transaction manager/caller can handle it. Catching an error and continuing without rolling back leaves the connection in a failed transaction state and triggers `25P02`.

### Do not confuse SQLSTATE with numeric error codes from other DBMSs

`SQLException` also has `getErrorCode()`. In many MySQL guides, developers check numeric error codes like `1062` to detect duplicate keys. **PostgreSQL classifies errors primarily via 5-character SQLSTATE strings**; do not expect `getErrorCode()` to return PostgreSQL numeric codes analogous to MySQL errors.

Recommended pattern:

```java
if ("23505".equals(exception.getSQLState())) {
    // PostgreSQL unique_violation
}
```

Do not write:

```java
// Incorrect when using pgJDBC and assuming MySQL codes.
if (exception.getErrorCode() == 1062) {
    // ...
}
```

### Cases where the error does not originate directly from the server

Not every `SQLException` comes from a complete PostgreSQL server **ErrorResponse**. Connection-open errors, client errors, pool timeouts, driver bugs, or dropped sockets can be synthesized client-side with varying metadata.

Therefore:

- `getSQLState()` can be `null` in some situations where no code was provided.
- A `SQLSTATE` in class `08` may indicate a connectivity issue with no table or constraint name attached.
- Never assume an exception with `getMessage()` automatically has `DETAIL`, `HINT`, and constraint names populated.
- If you need server-specific fields, verify whether the exception is actually a pgJDBC server exception type.

## 9. Extracting structured diagnostic fields in pgJDBC

When using pgJDBC, server errors are typically represented by `org.postgresql.util.PSQLException`. This class provides `getServerErrorMessage()`, returning a `ServerErrorMessage` object when the driver received a structured server error.

Controlled inspection example:

```java
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

import java.sql.SQLException;

public final class PostgreSqlErrorInfo {
    public static void inspect(SQLException exception) {
        String state = exception.getSQLState();
        System.out.println("SQLSTATE = " + state);

        if (exception instanceof PSQLException pgException) {
            ServerErrorMessage server =
                    pgException.getServerErrorMessage();

            if (server != null) {
                System.out.println("Severity = " + server.getSeverity());
                System.out.println("Constraint = " + server.getConstraint());
                System.out.println("Schema = " + server.getSchema());
                System.out.println("Table = " + server.getTable());
                System.out.println("Column = " + server.getColumn());
                // Avoid printing getDetail() or getMessage() directly in real logs
                // because they may contain user data.
            }
        }
    }
}
```

This Java example depends on **pgJDBC** and `instanceof` pattern matching supported by modern Java releases. On older Java versions, use plain `instanceof` followed by a cast.

In production systems, never `System.out.println` error metadata directly as in the example: send it to a structured logger, apply security policies, and scrub personally identifiable data.

### Common getters

| pgJDBC API | Data typically retrieved |
|---|---|
| `exception.getSQLState()` | SQLSTATE, when the exception carries a code. |
| `server.getSeverity()` | Severity level from the server. |
| `server.getMessage()` | Primary message supplied by PostgreSQL. |
| `server.getDetail()` | Detail, if present. |
| `server.getHint()` | Hint, if present. |
| `server.getPosition()` | Error position inside the SQL text, if supplied by the server. |
| `server.getWhere()` | Error context inside a function or execution stack. |
| `server.getSchema()` | Related schema, if present. |
| `server.getTable()` | Related table, if present. |
| `server.getColumn()` | Related column, if present. |
| `server.getConstraint()` | Related constraint name, if present. |

**Not every error includes a constraint or table name.** A `syntax_error` typically provides message and position, whereas `unique_violation` typically provides a constraint name. Even when present, the application must verify the exact schema/table/constraint against the SQL statement to avoid misrouting business errors.

### Distinguishing unique violations by constraint

Suppose the accounts table has two unique constraints: `uq_demo_accounts_email` and `uq_demo_accounts_external_id`. Either can trigger `23505`.

Better logic:

```java
if ("23505".equals(exception.getSQLState())
        && exception instanceof PSQLException pgException) {
    ServerErrorMessage server =
            pgException.getServerErrorMessage();

    if (server != null
            && "uq_demo_accounts_email".equals(server.getConstraint())) {
        // Only the unique-email case, not every 23505 error.
    }
}
```

When designing APIs, assign **stable constraint names** in migrations if the application layer inspects them. Also account for the impact if you ever rename constraints or alter schemas.

## 10. SQLSTATE and application-layer error handling strategies

Not every error code maps to the same HTTP status or retry policy. Separate reaction categories clearly.

| Code / group | Common handling approach | What to avoid |
|---|---|---|
| `23505` | Check the unique constraint; return a business conflict or handle idempotently. | Automatically assuming every unique error is a duplicate email. |
| `23503` | Return an invalid-reference error or delete conflict. | Trying to delete parent rows by disabling foreign keys carelessly. |
| `23502`, `23514` | Identify violating input or business logic bug; fix input or validation. | Retrying the exact same input endlessly. |
| `22P02` | Check type conversions and validate input. | Concatenating raw SQL strings; handling purely by substring matching on message. |
| `40001` | Typically retry **the whole transaction** with limits, backoff, and idempotency. | Retrying only one statement inside an already-failed transaction. |
| `40P01` | Roll back the transaction; consider bounded retry and consistent lock ordering. | Infinite retries or raising concurrency when deadlocks are already high. |
| `55P03` | Follow NOWAIT/lock-timeout policy; wait, report busy, or retry appropriately. | Treating it as "no matching data row." |
| `57014` | Identify who canceled or which timeout fired; reduce load or tune the query. | Immediately retrying a slow query unchanged. |
| `25P02` | Locate the **first error** in the transaction, roll back, or handle savepoints properly. | Fixing only the final statement that reported `25P02`. |
| `08...` | Inspect connection health, uncertain commit state, and idempotent retry logic. | Assuming every disconnect means the transaction did not commit. |
| `42P01`, `42703` | Check migrations, schema, `search_path`, and table/column names. | Surfacing as a user input error without checking deployment state. |

**This table is a guideline**, not a rigid HTTP mapping or retry rule for every project. For instance, `23505` may map to HTTP 409 on resource creation when it is a true conflict, while an internal service might treat an existing record as an expected idempotent outcome.

### Retrying transactions properly

For `40001` or `40P01`, PostgreSQL requires the current transaction not to proceed as if nothing happened. A meaningful retry loop must:

1. End the failed transaction via rollback or let the transaction manager close it.
2. Start a fresh transaction.
3. **Re-execute the entire logic** whose decisions depend on transactional data: reads, checks, calculations, and writes.
4. Enforce a retry limit and backoff—never an infinite loop.
5. Ensure external side effects outside the database do not duplicate improperly; use idempotency/outbox patterns where appropriate.

Specifically in Java/Spring, retrying **inside the same aborted transaction** only generates `25P02`. When combining `@Transactional` with a retry library, design **interceptor ordering and transaction boundaries** carefully.

## 11. SQLSTATE in PL/pgSQL: catching and re-raising errors

PostgreSQL supports error handling inside `PL/pgSQL` blocks via `EXCEPTION`, alongside diagnostic variables such as `SQLSTATE`, `SQLERRM`, and `GET STACKED DIAGNOSTICS`.

This is a **server-side** mechanism, distinct from how `psql` prints ErrorResponse or how Java handles `SQLException`.

### 11.1. Using EXCEPTION WHEN by condition name

A `DO` block illustrating unique-violation handling:

```sql
DO $$
DECLARE
    v_was_duplicate BOOLEAN := FALSE;
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN unique_violation THEN
        v_was_duplicate := TRUE;
        RAISE NOTICE 'Encountered unique_violation: SQLSTATE=%', SQLSTATE;
    END;

    IF v_was_duplicate THEN
        RAISE NOTICE 'Did not create duplicate email account';
    END IF;
END;
$$;
```

Inside an `EXCEPTION` handler, the special variable `SQLSTATE` holds the code of the error being handled; `SQLERRM` holds the error message. Once the handler finishes without re-raising, the outer block can continue.

**Note:** A PL/pgSQL `BEGIN ... EXCEPTION ... END` block rolls back SQL changes made inside the failing block (implemented via subtransactions). This is not equivalent to MySQL's `CONTINUE HANDLER`; never carry over error-handling assumptions verbatim from another DBMS.

### 11.2. Catching a specific SQLSTATE

In addition to condition names like `unique_violation`, you can write:

```sql
DO $$
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN SQLSTATE '23505' THEN
        RAISE NOTICE 'Caught PostgreSQL SQLSTATE 23505';
    END;
END;
$$;
```

In sound design, swallow an error only when **the fallback action is genuinely valid**. If you do not know which constraint failed or business rules require reporting failure, re-raise instead of continuing with unwritten data.

### 11.3. GET STACKED DIAGNOSTICS

To capture multiple error fields at once:

```sql
DO $$
DECLARE
    v_state   TEXT;
    v_message TEXT;
    v_detail  TEXT;
    v_hint    TEXT;
    v_context TEXT;
BEGIN
    BEGIN
        INSERT INTO demo_accounts(email)
        VALUES ('an@example.com');

    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state   = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_hint    = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'SQLSTATE inside handler: %', v_state;

        -- When there is no valid error-swallowing policy,
        -- re-raise so the caller sees the original error.
        RAISE;
    END;
END;
$$;
```

Fields:

- `RETURNED_SQLSTATE`: condition code, e.g., `23505`.
- `MESSAGE_TEXT`: primary message.
- `PG_EXCEPTION_DETAIL`: additional detail if available.
- `PG_EXCEPTION_HINT`: additional hint if available.
- `PG_EXCEPTION_CONTEXT`: call context where the error originated.

An argumentless `RAISE;` **inside an exception handler** re-raises the active error. This is useful when recording metadata before letting the caller handle the failure. In real applications, avoid printing full `v_message` or `v_detail` if they may expose private information.

### 11.4. RAISE EXCEPTION with intentional ERRCODE

You can intentionally raise business errors with a code:

```sql
CREATE OR REPLACE FUNCTION require_positive_amount(p_amount NUMERIC)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Amount must be greater than 0',
            HINT = 'Check the amount value before calling the function';
    END IF;
END;
$$;

SELECT require_positive_amount(0);
```

`22023` is `invalid_parameter_value`, suitable for invalid input in this example. Calling `RAISE EXCEPTION '...'` without `ERRCODE` defaults to `P0001` (`raise_exception`).

**Do not reuse arbitrary codes already assigned to other PostgreSQL meanings** if JDBC callers expect consistent classification. For domain-specific business errors, establish clear code conventions and supplementary metadata that will not be confused with built-in data or transaction errors.

### 11.5. Do not turn EXCEPTION into a blanket error sink

The following snippet is risky:

```sql
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error occurred but continuing';
```

This is only **a snippet inside a PL/pgSQL block**, not a standalone SQL statement. Applied broadly, it masks constraint violations, schema bugs, and logic flaws, tricking callers into thinking an operation succeeded when data was never written.

Catch only specific errors with clear rules. Whenever a business workflow must halt, **`RAISE;`** preserves the original error for the caller.

## 12. How do NOTICE, WARNING, and ERROR differ?

PostgreSQL defines multiple server message severity levels, including `DEBUG`, `LOG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `FATAL`, and `PANIC`. Distinguish **severity** from **SQLSTATE**:

| Severity | Common practical meaning |
|---|---|
| `NOTICE` | Informational notice, e.g., PL/pgSQL `RAISE NOTICE`. |
| `WARNING` | Warning that may warrant attention without necessarily failing the statement. |
| `ERROR` | Statement or operation error; can abort the active transaction. |
| `FATAL` | Severe error terminating the client session. |
| `PANIC` | Critical server-wide condition, typically terminating processes and triggering recovery. |

**Severity answers "how severe is it?", while SQLSTATE answers "what condition occurred?"** Both fields serve distinct purposes.

### NOTICE example

```sql
DO $$
BEGIN
    RAISE NOTICE 'Checking demo data';
END;
$$;
```

The client receives a `NOTICE` while the `DO` block still completes. In JDBC, non-fatal notices may surface via **`SQLWarning`** or driver-specific warning APIs.

### client_min_messages

The PostgreSQL variable `client_min_messages` controls the threshold for notices sent to the client:

```sql
SHOW client_min_messages;

-- Lab session only; changes visibility threshold for NOTICE.
SET client_min_messages = warning;

DO $$
BEGIN
    RAISE NOTICE 'This notice may not be displayed to the client';
END;
$$;

RESET client_min_messages;
```

Never alter client thresholds to **hide `ERROR` messages** from an operation. Similarly, `log_min_messages` and `log_error_verbosity` govern **server logs**, independent of how `psql` displays ErrorResponse.

### log_error_verbosity

PostgreSQL operators can configure server log detail levels—`terse`, `default`, or `verbose`—via `log_error_verbosity`. Server log `verbose` mode can include SQLSTATE and source code locations for deep analysis.

This is a **server setting**, not the same variable as `psql`'s `\set VERBOSITY verbose` meta-command. Adjusting server logging requires considering log volume, sensitive data exposure, and PostgreSQL configuration management procedures.

## 13. Position, Context, and Hint help fix SQL

Not every error involves data constraints. For example, a SQL query with a misspelled column name:

```sql
SELECT unknown_col
FROM demo_accounts;
```

PostgreSQL returns `42703` (`undefined_column`), a message, and the SQL character position. In `psql`, many errors render a `^` pointer beneath the offending token. When a driver receives `Position`, IDEs or error reporters can highlight the exact spot in the SQL statement.

Another example:

```sql
SELEC id FROM demo_accounts;
```

PostgreSQL returns `42601` (`syntax_error`), typically with the position where invalid syntax was detected.

### HINT is not always present

Some errors include a hint, such as when PostgreSQL suspects a column typo or suggests an explicit type cast. `HINT` is helpful when fixing SQL, though the server does not guarantee a complete fix in every case.

### Context in PL/pgSQL

When an error occurs inside a stored function or trigger, `CONTEXT` or `Where` can report the function name, PL/pgSQL line number, and active SQL statement.

This is particularly helpful when an application simply calls:

```sql
SELECT process_order(123);
```

yet the actual error happens inside a nested `INSERT` or `UPDATE` deep within the function. In such cases, **SQLSTATE plus context** explains the root cause far better than a single isolated error message.

## 14. One table can produce several distinct errors

Add a foreign key table to illustrate why errors in the same class must be distinguished:

```sql
CREATE TABLE demo_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES demo_accounts(id),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0)
);
```

Illustrative statements:

```sql
-- 23503: account_id references a nonexistent row.
INSERT INTO demo_orders(account_id, quantity)
VALUES (999999999, 1);

-- 23502: account_id is NULL.
INSERT INTO demo_orders(account_id, quantity)
VALUES (NULL, 1);

-- 23514: quantity violates CHECK (> 0).
-- Assumes account_id = 1 exists in the lab.
INSERT INTO demo_orders(account_id, quantity)
VALUES (1, 0);
```

Observations:

1. All three belong to **class `23`**.
2. `23503`, `23502`, and `23514` carry different meanings and should not map identically if the application needs accurate user feedback.
3. If a single statement violates multiple constraints, **there is no guarantee the server reports all of them simultaneously**. You typically receive whichever violation the execution path hits first.
4. Error details may contain constraint names and column values; avoid exposing them verbatim in public logs.

To test `23514` reliably, inspect existing account IDs in the lab environment first:

```sql
SELECT id, email FROM demo_accounts ORDER BY id;
```

Then use an existing valid `id`. Do not assume a hardcoded ID when a test database has been reset multiple times and its identity sequence has advanced.

## 15. Reading errors in Spring and SQLException wrappers

Spring JDBC or Spring Data applications typically translate certain `SQLException` instances into framework-level exception classes, such as:

- `DuplicateKeyException` for cases matching unique violations.
- `DataIntegrityViolationException` for broader data-integrity failures.
- Exceptions related to locks, resources, or DB operations per the framework/driver translator.

These abstractions keep business code decoupled from driver specifics, but do not assume every PostgreSQL error has a **single, immutable** mapping across all Spring versions.

When you need the exact SQLSTATE:

1. Inspect the underlying exception or cause chain if the framework wrapped it.
2. Read `SQLException.getSQLState()` once you locate the `SQLException`.
3. If using pgJDBC and needing the constraint name, extract `ServerErrorMessage` when available.
4. Confirm whether the transaction manager has rolled back.
5. Never reuse the same transaction after an unhandled SQL error.

### Example finding SQLException in the cause chain

```java
import java.sql.SQLException;

public final class SqlErrorClassifier {
    public static String findSqlState(Throwable failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof SQLException sqlException) {
                return sqlException.getSQLState();
            }
            current = current.getCause();
        }

        return null;
    }
}
```

This is a minimal illustration. In real systems, `SQLException` also provides **`getNextException()`** to traverse chained JDBC exceptions that do not always appear in `getCause()`. For batches or multi-statement calls, inspect both the exception chain and statement context so important codes are not missed.

Do not blindly turn every JDBC exception into HTTP 500; conversely, never return raw server messages in API responses since that can leak data and schema details. Return application business error codes while keeping SQLSTATE for server-side monitoring and investigation.

## 16. Diagnostic logging without leaking sensitive data

SQLSTATE is ideal for **structured logging** and error-group metrics. A good incident log entry might look like:

```text
timestamp: 2026-11-14T10:20:00Z
service: order-api
operation: create_account
database_role: app_writer
sqlstate: 23505
error_class: 23
constraint: uq_demo_accounts_email
transaction_id: <internal application id>
request_id: <trace id>
retry_count: 0
outcome: failed
```

This is an **illustrative log format**, not a real system event. Request and transaction IDs should follow your application's observability and security policies.

### What should you log?

- **Full SQLSTATE** rather than just the class or message text.
- Business operation and running component name.
- Schema/table/constraint names when helpful and non-sensitive.
- Outcome category: permanent failure, rolled back, retried, or uncertain commit state.
- Correlation/request ID to tie application logs to server logs.

### What should you avoid logging by default?

- Raw SQL strings containing unfiltered sensitive input values.
- Passwords, tokens, or connection strings containing secrets.
- Full `DETAIL` payloads when they expose emails, addresses, or customer data.
- Verbatim PostgreSQL error messages returned directly to public clients.

A message helpful to a DBA is rarely appropriate for an end user. For example, an API may return "Email is already in use" based on code `23505` **plus the matching unique constraint**, without revealing table structure or constraint names.

## 17. End-to-end PostgreSQL error diagnostic workflow

When a query or API call fails, follow this sequence:

```text
Error occurs in application / psql
               │
               ▼
Capture SQLSTATE, severity, and operation
               │
               ▼
Read message, detail, hint, position, context
               │
               ▼
Is the current error 25P02?
           ┌───┴────┐
         Yes        No
          │          │
          ▼          ▼
Find first error    Classify code (22,23,40,42,08...)
in transaction           │
          │              ▼
          └────────► Identify cause / constraint
                         │
                         ▼
                 Check transaction state
                         │
                         ▼
               Rollback / handle savepoint if needed
                         │
                         ▼
         Decide: fix input, fix schema, retry, or fail
                         │
                         ▼
             Log safely and verify outcome
```

### Step 1 — Capture the real root error

In `psql`, run `\errverbose` right after an error to see the code. In Java, read `SQLException.getSQLState()` or unwrap the root exception if a framework wrapped it.

If you only see `25P02`, locate the first failing statement inside the transaction before analyzing the current SQL statement.

### Step 2 — Separate code bugs from input data

`42P01` can mean a missing table from an unapplied migration or an incorrect `search_path`. `23514` can mean invalid input or missing validation logic. Inspect schema, app version, SQL, and input data before returning an error to users.

### Step 3 — Rely on structured diagnostic fields over message prose

SQLSTATE works best for branching, constraint names identify violated rules, `Position` pinpoints syntax errors, and `Context` locates PL/pgSQL lines. Message prose remains helpful for operators, but should not serve as a brittle logic key.

### Step 4 — Determine transaction state and write outcome

If a statement fails inside a transaction, roll back properly. If the connection drops around commit time, do not assume the write failed; verify using business identifiers or a transaction status table.

### Step 5 — Retry only errors designed for retry

For `40001`/`40P01`, a retry policy helps, provided it wraps **the entire transaction**, caps attempts, and applies backoff. For `23502` or `22P02`, retrying identical data only repeats the error.

### Step 6 — Cross-check server logs when needed

When the client lacks enough context, operators can inspect PostgreSQL server logs matching timestamp, process/session, and request. Configure server logging carefully, avoiding unbounded verbosity in environments handling sensitive data.

## 18. Common misconceptions

**"Error messages are stable programmatic codes."** No. Wording can change or be localized; SQLSTATE is the proper classification mechanism.

**"SQLSTATE is always 5 digits."** No. `42P01`, `40P01`, `22P02`, and `P0001` all contain letters.

**"Every 23xxx error is a duplicate key."** No. Class `23` covers several conditions, including foreign key, not-null, and check violations.

**"A 23505 error always means a duplicate email."** No. You must inspect which unique constraint was violated.

**"psql always prints SQLSTATE by default."** No. Change `VERBOSITY` or run `\errverbose` to view detailed codes.

**"A 25P02 error proves the SELECT statement just run is broken."** No. It typically means the transaction already failed due to an **earlier** error.

**"You can continue the same transaction after an error simply by catching the exception in Java."** No. Once a transaction is aborted, you must roll back or use a properly designed savepoint.

**"Catching and swallowing every EXCEPTION in PL/pgSQL makes the system resilient."** No. It can mask data errors, produce false successes, and make failures harder for callers to recover from.

**"SQLException.getErrorCode() identifies PostgreSQL errors just like MySQL 1062."** No. In PostgreSQL, use the 5-character SQLSTATE.

**"Every 40001 error can be fixed by retrying a single statement."** No. For serialization failures, you must retry **the entire transaction**, including reads and business decisions.

**"A connection-drop error guarantees the transaction did not commit."** No. A commit can finish on the server even though the client loses the response.

**"NOTICE is always thrown as a SQLException."** No. Non-error server notices travel via warning/notice channels on the client.

**"getServerErrorMessage is always non-null."** No. Driver-side or connectivity failures may lack a server ErrorResponse.

**"Printing full DETAIL to logs is harmless."** No. DETAIL can leak sensitive column values from rejected rows.

## 19. Practice exercises

### Exercise 1 — Analyzing a unique_violation message

Given the output:

```text
ERROR:  duplicate key value violates unique constraint "uq_demo_accounts_email"
DETAIL:  Key (email)=(an@example.com) already exists.
```

Explain the severity, expected SQLSTATE, constraint name, and why full DETAIL should not be returned in public responses.

### Exercise 2 — Changing verbosity in psql

In `psql`, trigger the duplicate-email error with `\set VERBOSITY default`, `verbose`, `terse`, and `sqlstate`. Run `\errverbose` after an error and note the difference between SQLSTATE and message text. State whether this meta-command can be sent directly over JDBC as SQL.

### Exercise 3 — Finding the root error instead of 25P02

A transaction executes:

```sql
BEGIN;
INSERT INTO demo_accounts(email) VALUES ('an@example.com');
SELECT COUNT(*) FROM demo_accounts;
UPDATE demo_accounts SET balance = 10 WHERE email = 'an@example.com';
```

If the first `INSERT` fails with `23505`, predict the errors on the subsequent statements. Provide the SQL statement to recover the transaction state and explain why modifying only the `UPDATE` will not fix the problem.

### Exercise 4 — Matching SQLSTATEs to business scenarios

Match each scenario to the appropriate code: inserting `NULL` into a `NOT NULL` column, updating a foreign key to a nonexistent parent row, `CHECK` rejecting a negative number, casting string `abc` to integer, and querying a nonexistent table.

*Hint:* `23502`, `23503`, `23514`, `22P02`, `42P01`.

### Exercise 5 — Designing JDBC error handling

Write a Java method accepting a `SQLException` and returning an enum with `DUPLICATE`, `INVALID_INPUT`, `RETRYABLE_TRANSACTION`, and `OTHER` based on SQLSTATE. Explain why you also need the constraint name to turn `DUPLICATE` into a specific business message.

### Exercise 6 — Designing a safe retry

A loyalty-points transfer app hits `40001` inside a transaction that reads balances, checks limits, and updates two accounts. Describe the rollback/retry boundary, maximum attempts, idempotency, and how to ensure external notifications are not sent twice.

### Exercise 7 — Analyzing PL/pgSQL

A function catches `EXCEPTION WHEN unique_violation`, runs `RAISE NOTICE`, and returns normally. Explain when this behavior is valid and when `RAISE;` is needed to propagate the error to the caller. Extend the function to capture `RETURNED_SQLSTATE` and `PG_EXCEPTION_CONTEXT`.

### Exercise 8 — Building a monitoring scheme

Design a log structure containing `timestamp`, `service`, `operation`, `sqlstate`, `constraint`, `request_id`, and `outcome` without exposing sensitive data. Name at least two useful metrics: `23505` error counts per operation and `40P01` counts per unit of time, noting that spikes may stem from workload shifts.

## Conclusion

**SQLSTATE is the key to reading and handling PostgreSQL errors consistently.** The 5-character code identifies the condition class, while **severity, message, DETAIL, HINT, Position, Context, and object names** pinpoint the exact cause. In `psql`, meta-commands `\set VERBOSITY verbose`, `\set VERBOSITY sqlstate`, and `\errverbose` reveal details omitted by default output; in Java, `SQLException.getSQLState()` and pgJDBC's `ServerErrorMessage` provide structured fields for classification.

When investigating incidents, **find the first error**, especially before `25P02`, check transaction state, and choose the right response: fix input, fix schema, roll back, or retry the full transaction when appropriate. Avoid branching on message wording and avoid logging details that could leak sensitive data. Reading SQLSTATE accurately not only speeds up debugging, it forms the foundation for **reliable APIs, observable operations, and safely handled PostgreSQL transactions**.
