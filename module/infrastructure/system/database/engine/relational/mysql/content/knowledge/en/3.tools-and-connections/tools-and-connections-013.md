# Reading SQLSTATE, MySQL Error Codes, and Client Error Messages

When an SQL statement fails, MySQL typically returns an error number, an SQLSTATE value, and a descriptive error message. For example, when an application inserts an existing email into a table with a `UNIQUE` constraint, the mysql client may display `ERROR 1062 (23000): Duplicate entry ...`. These three pieces provide different layers of information: code `1062` identifies the specific MySQL error, SQLSTATE `23000` indicates an integrity constraint violation, and the message explains which value or key collided.

Reading these details accurately helps distinguish syntax errors, data errors, privilege errors, transaction conflicts, and connection errors. As a result, applications can handle failures deliberately, operators can pinpoint the failing layer, and development teams avoid coupling logic to message strings that may change across versions.

## 1. Three Components to Read in a MySQL Error

### 1.1. MySQL Error Code

A MySQL error number is an integer identifying a specific error condition defined by MySQL or a client library. For example:

- `1062`: duplicate value for a `PRIMARY KEY` or `UNIQUE` key.
- `1064`: SQL syntax error.
- `1045`: account authentication failure or connection identity not permitted to log in.
- `1146`: referenced table or view does not exist.
- `1213`: InnoDB detected a deadlock and rolled back one transaction.

Error numbers are MySQL-specific. They are useful when consulting documentation, searching logs, and writing driver-specific handling, though they are not universal codes shared across all database engines.

### 1.2. SQLSTATE

SQLSTATE is a status code of exactly five alphanumeric characters designed to classify conditions according to the SQL standard. The first two characters denote the **class** (error or status category); the last three characters denote the **subclass** (a specific condition within that class).

Common classes:

| Class | Meaning | Example Scenario |
|---|---|---|
| `00` | Successful completion | Statement completed normally (`00000`) |
| `01` | Warning | Data was converted or truncated, yet the statement completed under permissive mode |
| `02` | No data | Cursor fetch or operation found no matching rows |
| `08` | Connection exception | Connection or transport encountered an error |
| `0A` | Feature not supported | Requested a feature unsupported by the system/driver |
| `22` | Data exception | Value has invalid format, is too long, or is out of range |
| `23` | Integrity constraint violation | Duplicate key, foreign key violation, or `NOT NULL` violation |
| `24` | Invalid cursor state | Cursor operation issued in an invalid state |
| `25` | Invalid transaction state | Operation incompatible with current transaction state |
| `28` | Invalid authorization specification | Account failed authentication |
| `40` | Transaction rollback | Deadlock or conflict requiring rollback |
| `42` | Syntax error or access rule violation | Malformed SQL or invalid object reference |
| `HY` | General exception reported by implementation/driver | Certain MySQL errors without a more specific class |

Classes categorize errors at a high level. Do not infer every handling detail from the first two characters alone; combine the full SQLSTATE, MySQL error number, and statement context.

### 1.3. Error Message

The message text is the human-readable description of the specific condition, often naming the table, column, constraint, value, or rejected operation. For example, `Duplicate entry 'alice@example.com' for key 'users.email'` identifies both the duplicate email value and the conflicting key.

Message wording can vary across MySQL versions, drivers, locales, settings, and data values. Therefore, use error codes and SQLSTATE for programmatic classification; use the message for logging, diagnostics, and displaying controlled details to operators.

## 2. Reading Message Structure from the mysql Client

A server-returned error is usually displayed by the mysql client in the following format:

```text
ERROR 1062 (23000) at line 8: Duplicate entry 'alice@example.com' for key 'users.email'
```

You can break down each part as follows:

| Component | Example Value | Meaning |
|---|---|---|
| Severity | `ERROR` | The statement failed |
| Error code | `1062` | Specific MySQL error number |
| SQLSTATE | `(23000)` | Integrity constraint violation category |
| Location | `at line 8` | Line in the input file being executed by the client; not always present |
| Text | `Duplicate entry ...` | Specific description of the conflicting value and key |

When a statement is run interactively at the prompt, the message normally omits `at line`. When the client reads an SQL file, the line number helps locate the statement to inspect. In multi-statement scripts, check both the reported line and surrounding statements; an error on one line may stem from schema or data created in an earlier step.

Other examples:

```text
ERROR 1064 (42000): You have an error in your SQL syntax; check the manual...
ERROR 1146 (42S02): Table 'shop.order_items' doesn't exist
ERROR 1045 (28000): Access denied for user 'app_user'@'10.0.0.12'
```

In the first example, `42000` belongs to syntax or access rule errors. The second indicates a missing table (`42S02`). The third belongs to authentication (`28000`). The message text still needs to be read to identify the exact table or connection identity involved.

Not every message printed to a terminal is an SQL error sent by the server. DNS resolution failures, socket errors, missing input files, TLS handshake errors, or invalid command-line flags can originate in the client or operating system. Those may lack a server-assigned SQLSTATE because the server never received an SQL statement.

## 3. Distinguishing Server, Client, and Connection Errors

| Error Source | When It Typically Occurs | Symptoms | Diagnostic Direction |
|---|---|---|---|
| SQL/server | Server already received the statement | Has a MySQL error code and usually an SQLSTATE; e.g., `1062`, `1064`, `1146` | Check SQL, schema, data, privileges, and transaction state |
| Client/tool | Before or while the client processes input | Invalid flags, unreadable file, shell command syntax error, or UI error | Check client invocation command, file paths, versions, and tool logs |
| Network/connection | Before connecting or mid-session | Timeouts, connection refused, server has gone away, lost connection | Check DNS, host/port, firewalls, TLS, server restarts, and timeouts |
| Application/driver | When mapping results or executing application logic | Exceptions, pool config errors, type conversion or data processing errors | Read exception fields, stack traces, and correlated application logs |

For example, `ERROR 2003` when the client cannot reach the server at host/port points to a connection issue; no SQL statement ran. Conversely, `ERROR 1064` means the server parsed the SQL statement and rejected its syntax. The two scenarios require completely different remedies.

Errors like `ERROR 2006: MySQL server has gone away` or `ERROR 2013: Lost connection to MySQL server during query` can appear when the server closes a connection, the network drops, or a timeout is exceeded. They do not prove the transaction rolled back. If the connection drops right during `COMMIT`, the client may not know whether the commit succeeded; reconcile business state before retrying.

## 4. Common SQLSTATE Values and MySQL Error Codes

The table below focuses on scenarios commonly encountered when developing and operating MySQL. Exact messages may vary by version and context.

| MySQL Error Code | Common SQLSTATE | Situation | Initial Response |
|---:|---|---|---|
| `1062` | `23000` | Duplicate primary key or unique key | Inspect existing data, business uniqueness rules, and upsert/idempotency strategy |
| `1048` | `23000` | Assigning `NULL` to a `NOT NULL` column | Check input data, default values, and data contracts |
| `1452` | `23000` | Inserting/updating a child row without a matching parent row | Create or verify the parent row first; check the foreign key |
| `1451` | `23000` | Deleting/updating a parent row referenced by child rows | Clarify business rules, deletion order, or `ON DELETE` behavior |
| `1064` | `42000` | Invalid SQL syntax | Check statement syntax, quotes, commas, keywords, and server version |
| `1054` | `42S22` | Referenced column not found | Check column names, aliases, schema, and migrations |
| `1146` | `42S02` | Table or view not found | Check current schema, object names, and migration order |
| `1045` | `28000` | Account authentication failed | Check username, source host, credentials, and authentication plugin |
| `1213` | `40001` | Deadlock; InnoDB rolled back one transaction | Retry the entire transaction with bounded backoff; review lock acquisition order |
| `1205` | `HY000` | Lock wait exceeded `innodb_lock_wait_timeout` | Find the lock-holding transaction, shorten transaction duration, and decide business rollback |
| `1406` | `22001` | Value too long for column | Check input length and column type/size; never silently truncate |
| `1264` | `22003` | Numeric value out of range for column type | Check value domain, numeric type, and overflow arithmetic |
| `1292` | `22007` | Invalid date/time value or invalid conversion | Check format, timezone, column type, and SQL mode |
| `1136` | `21S01` | Value count does not match column count in `INSERT` | Compare column list against value list |
| `2002` / `2003` | Often `HY000` on client | Cannot open socket or TCP connection to server | Check service status, host, port, socket, and firewall |
| `2006` / `2013` | Often `HY000` | Server closed connection or connection lost during query | Check server logs, network, timeouts, and commit state |

Codes `2002`, `2003`, `2006`, and `2013` typically originate in the client/library or connection layer. The reported SQLSTATE can depend on the failure path and connector. When an application needs exact handling, inspect the properties directly from your actual driver rather than assuming all clients map them identically.

## 5. Reading Warnings and Diagnostics After a Statement

Not every abnormal condition causes a statement to fail. MySQL may complete a statement while raising warnings—for example, converting values or handling data according to the active SQL mode. Warnings still require inspection because they can signal unintended data transformation.

### 5.1. Using SHOW WARNINGS and SHOW ERRORS

The example below uses `INSERT IGNORE` to illustrate how a duplicate-key error is downgraded to a warning in certain contexts:

```sql
INSERT IGNORE INTO users (email)
VALUES ('alice@example.com');

SHOW WARNINGS;
SHOW COUNT(*) WARNINGS;
SHOW ERRORS;
```

`SHOW WARNINGS` lists warning, error, and note conditions from the most recent statement; `SHOW ERRORS` lists only errors. `SHOW COUNT(*) WARNINGS` returns the count of recorded warnings. Run these immediately after the statement being investigated so they are not overwritten by a subsequent statement.

`INSERT IGNORE` is not a default fix for data errors. It can turn several error types into warnings and let execution continue, causing the application to silently skip uninserted rows. Use it only when skipping behavior has been explicitly designed and tested.

### 5.2. Using GET DIAGNOSTICS

Inside stored programs, `GET DIAGNOSTICS` retrieves information from the diagnostics area, including condition count, affected rows, or details of a specific condition.

```sql
GET DIAGNOSTICS
    @condition_count = NUMBER,
    @affected_rows = ROW_COUNT;

SELECT @condition_count, @affected_rows;
```

To read a specific condition:

```sql
GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT @sqlstate, @mysql_errno, @message;
```

`CONDITION 1` is the first condition in the diagnostics area; if there are multiple conditions, check `NUMBER` and select the desired condition. The `@...` variables in this example are user-defined session variables. Inside a stored procedure, you can assign into declared local variables.

Example exception handler inside a stored procedure:

```sql
DELIMITER //

CREATE PROCEDURE create_user(IN p_email VARCHAR(255))
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_errno INT;
    DECLARE v_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        -- Internal logging can be performed here if permitted by design.
        -- RESIGNAL preserves the original error for the caller.
        RESIGNAL;
    END;

    INSERT INTO users (email) VALUES (p_email);
END//

DELIMITER ;
```

Variables are declared before handlers in accordance with stored program declaration order. In this example, the handler reads diagnostics and calls `RESIGNAL` so the original error is not swallowed. If writing logs to a table, carefully design transaction boundaries and handle cases where logging itself fails.

### 5.3. Raising Business Errors Intentionally

`SIGNAL` lets a stored program raise a condition with an application-defined SQLSTATE. SQLSTATE `45000` is commonly used for user-defined exceptions:

```sql
IF p_quantity <= 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Quantity must be greater than zero';
END IF;
```

`RESIGNAL` inside a handler rethrows the condition being handled, optionally modifying condition properties deliberately. Never catch all exceptions and return success; doing so tricks the caller into assuming business work succeeded even when data was not written.

## 6. Retrieving Error Codes and SQLSTATE in Applications

Applications should not parse message strings by searching for words like `Duplicate`, `Access denied`, or `timeout`. Wording can change across versions, locales, or drivers. Extract the structured fields provided by the connector.

### 6.1. Java JDBC

In JDBC, `SQLException` exposes SQLSTATE, the vendor error code, and the message:

```java
try {
    // Execute statement via PreparedStatement.
} catch (SQLException ex) {
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();
    String message = ex.getMessage();

    // Log sqlState and vendorCode along with request/correlation ID.
    // Classify errors by code; do not key logic off the message text.
}
```

An `SQLException` can link to subsequent exceptions via `getNextException()`, especially when a driver reports multiple errors for batch or multi-statement execution. For complete diagnostics, traverse the exception chain and log relevant details without exposing sensitive data.

### 6.2. MySQL C API

With the MySQL C API, common functions include:

```c
unsigned int code = mysql_errno(conn);
const char *state = mysql_sqlstate(conn);
const char *message = mysql_error(conn);
```

These functions read error details on the connection after a failed operation. Copy the message text if you need to retain it beyond the lifetime guaranteed by the API; do not assume the returned pointer's memory is owned by the application.

### 6.3. Other Connectors

Node.js, Python, PHP, and other platforms package exceptions in their own ways. Property names vary across connectors and versions. Consult your driver's documentation to retrieve:

- The MySQL error code or driver-mapped symbolic code.
- SQLSTATE if supplied by the connector.
- The diagnostic message.
- Connection state and transport-layer cause if available.

Do not assume every error populates all three fields. An error occurring before the server replies may contain only a client-side code or OS error detail.

## 7. Classifying Errors to Decide How to Handle Them

An error code is only useful when paired with the right action. Errors can be grouped as follows:

| Category | Examples | Appropriate Action |
|---|---|---|
| Input/business errors | `1062`, `1048`, `1452`, `1406` | Validate input, return validation feedback, or resolve business conflicts |
| SQL/schema errors | `1064`, `1054`, `1146` | Fix SQL, aliases, schema, or migration order; generally do not retry as-is |
| Authentication/privilege errors | `1045`, `1142` | Inspect account, host, grants, and config; do not loop login attempts indefinitely |
| Transaction conflicts | `1213`, `1205` | Roll back cleanly, shorten lock-holding duration, and perform bounded retries when appropriate |
| Connection errors | `2002`, `2003`, `2006`, `2013` | Check network/server and verify commit state before re-sending operations |
| Warnings/data conversions | SQLSTATE class `01` | Inspect `SHOW WARNINGS`, verify SQL mode, and check data quality |

### 7.1. When Is Retrying Safe?

A deadlock (`1213`, SQLSTATE `40001`) is typically a case where retrying the entire transaction is appropriate. InnoDB has already rolled back the victim transaction, so the application should catch the error, wait a short randomized interval (backoff), and re-execute the entire unit of work up to a retry limit.

Lock wait timeouts (`1205`) require greater caution. With `innodb_rollback_on_timeout` disabled by default, a timeout normally rolls back only the timed-out statement, not the entire transaction. The application should explicitly `ROLLBACK` the full business transaction when a step fails, and only then decide whether to retry. Never proceed to `COMMIT` a half-failed transaction.

Never retry indefinitely. Excessive retries amplify load and worsen lock contention. Enforce retry caps, jittered backoff, retry count metrics, and logging to detect persistent problems.

### 7.2. When Should You Avoid Automatic Retries?

- Syntax errors (`1064`), unknown columns (`1054`), or missing tables (`1146`) normally require code fixes or deploying migrations.
- Authentication/privilege errors (`1045`, `1142`) require adjusting configuration or grants; repeated retries will not solve the cause.
- Data violations (`1062`, `1452`, `1406`) require inspecting business rules and payloads. Retrying the exact same data will usually reproduce the same error.
- Connection loss during commit may leave the outcome unknown on the client side. Before resending, query business state using an idempotency key or unique reference key.

For instance, a payment creation API should accept a unique `idempotency_key`. If the client loses its connection after sending the request, a retry can look up the outcome by that key instead of creating a duplicate payment transaction.

## 8. Reading InnoDB Transaction and Lock Errors

When encountering `1213` or `1205`, identify which transaction holds the lock and which statement is waiting. Useful diagnostic steps include:

```sql
SHOW ENGINE INNODB STATUS\G
```

The `LATEST DETECTED DEADLOCK` section typically shows the participating transactions, statements, index records, and which transaction was rolled back most recently. This section is overwritten when a new deadlock occurs, so capture it close to the incident time.

On compatible MySQL versions, Performance Schema and views in `sys` help inspect waiting transactions, lock waits, and statement digests. For example, you can start with `sys.innodb_lock_waits` and `sys.schema_table_lock_waits` if present in your installation.

Measures to reduce deadlocks and lock waits:

- Keep transactions short; avoid waiting on user input or calling external services while holding locks.
- Update multiple rows in a consistent order across threads.
- Create appropriate indexes so `UPDATE`/`DELETE` statements lock only the necessary range instead of scanning overly wide ranges.
- Avoid leaving read/write transactions open longer than business requirements dictate.
- Retry deadlocked transactions with limits and emit metrics to monitor them.

## 9. Error Logs and Information to Capture During Diagnostics

Client-side messages are only part of the evidence. For operational errors, correlate the timestamp of the client error with the MySQL Server error log, application logs, and system metrics.

A useful diagnostic record should include:

- Timestamp and timezone, plus request ID or correlation ID.
- Environment name, logical host, and service name; avoid logging passwords or connection strings containing secrets.
- MySQL error code, SQLSTATE, message, and operation type.
- Statement name or SQL fingerprint/digest; mask sensitive values rather than logging raw payloads.
- Transaction state: whether started, which statements succeeded, whether `COMMIT` or `ROLLBACK` was called, and whether the client received commit confirmation.
- Retry count, wait time, query duration, and connection pool state.
- MySQL Server, connector, and application versions when investigating version differences.

Never log full personal data, tokens, passwords, or payment details. If you need to correlate a value that caused an error, use a reference ID or masked representation.

## 10. Step-by-Step Walkthrough of Reading and Handling a Real Error

Suppose an account-creation API fails when inserting email `alice@example.com`. The mysql client displays:

```text
ERROR 1062 (23000): Duplicate entry 'alice@example.com' for key 'users.email'
```

Investigate in sequence:

1. **Read the structure:** `1062` is the MySQL code for duplicate key; `23000` is the integrity constraint violation class.
2. **Identify the constraint:** the message names key `users.email`; inspect `SHOW CREATE TABLE users` or `SHOW INDEX FROM users` to confirm the unique index.
3. **Assess the business cause:** was the email already registered, or did two signup requests run concurrently? Never rely solely on a pre-`INSERT` `SELECT`, because race conditions can still occur.
4. **Choose the response:** if the email already exists, return an appropriate business error or guide the user to login/account recovery. Do not drop the unique constraint just to silence conflicts.
5. **Consider safe retries:** if requests can be re-sent, use an idempotency key or a mechanism to inspect the already-created result so duplicate records are not produced.
6. **Log:** record SQLSTATE, error code, constraint name, request ID, and required masked context.

The same workflow applies to other errors: read code and SQLSTATE, identify the error source, correlate the message with the statement and transaction state, and then choose whether to fix data, fix SQL, adjust privileges, retry, or investigate connectivity.

## 11. Common Mistakes

- **Parsing messages with brittle substrings:** wording can change; classify by `errno` and SQLSTATE.
- **Treating every error as retryable:** schema, privilege, and data errors require fixing the root cause; retries merely add load.
- **Assuming a timeout means the transaction rolled back:** lock wait timeouts by default may roll back only one statement; losing a connection during commit can also leave client-side status ambiguous.
- **Ignoring warnings:** warnings may signal value conversion or truncation; inspect immediately with `SHOW WARNINGS`.
- **Hiding errors with `INSERT IGNORE`:** the statement may continue while some rows silently fail to insert.
- **Logging only the message without SQLSTATE/error code:** makes grouping errors and tracking trends difficult.
- **Logging raw payloads:** can expose sensitive data; use fingerprints, reference IDs, and masked values.
- **Retrying operations after connection loss without reconciling:** can create duplicate records or transactions if the earlier commit actually succeeded.

## 12. Checklist When Receiving an Error from MySQL

- What is the MySQL error code? What is the full SQLSTATE?
- Did the message originate from the server, client, driver, or network/OS layer?
- Which SQL statement was running, on which host/schema, and under which account?
- Which table, column, index, constraint, or value does the message mention?
- Did the statement fail, or only emit a warning? What does `SHOW WARNINGS` show?
- Did the transaction roll back, remain open, or enter an indeterminate commit state?
- Can the error be resolved by fixing data, SQL, schema, privileges, or connectivity?
- Is it safe to retry the entire transaction? Is an idempotency key needed?
- Do logs capture timestamp, request ID, error code, and versions while masking secrets?

## Conclusion

MySQL error codes identify specific error conditions in MySQL's implementation; SQLSTATE classifies conditions into standard groups; messages provide human-readable context for investigation. When reading errors from the mysql client or a connector, determine whether the error came from the server or the client/connection layer, cross-check all three components, and verify transaction state. In applications, use error codes and SQLSTATE for classification, retry only transactions that are safe to re-execute, and log sufficient diagnostics without exposing sensitive data.
