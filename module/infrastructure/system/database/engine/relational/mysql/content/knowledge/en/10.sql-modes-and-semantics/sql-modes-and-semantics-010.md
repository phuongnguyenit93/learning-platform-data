# sql_safe_updates and How It Differs from sql_mode Flags

## Objectives

After this lesson, you will be able to:

- Explain how `sql_safe_updates` protects `UPDATE` and `DELETE` statements.
- Distinguish `sql_safe_updates` from the `sql_mode` variable and modes such as `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, and `ANSI_QUOTES`.
- Inspect and change `sql_safe_updates` at the SESSION or GLOBAL scope.
- Understand why a statement with a key or `LIMIT` can still affect too many rows.
- Write a pre-check workflow before updating/deleting data and handle error 1175.
- Recognize the impact of SQL clients, connection pools, and deployment environments on safe updates mode.

## 1. What Is sql_safe_updates Used For?

`sql_safe_updates` is a MySQL system variable that restricts certain update or delete statements with an unclear scope. When enabled, MySQL rejects `UPDATE` or `DELETE` statements if they neither use a key column in the `WHERE` clause nor specify a `LIMIT` clause.

The goal is to reduce the risk of accidentally executing a statement that affects an entire table, such as forgetting a filter condition:

```sql
-- Could affect every row in the table without safe updates
UPDATE employees
SET status = 'INACTIVE';

-- Could delete every row in the table without safe updates
DELETE FROM employees;
```

When `sql_safe_updates = 1`, statements like the ones above that have neither a `WHERE` using a key nor a `LIMIT` are rejected. This mechanism typically returns MySQL error 1175 with a message referencing safe update mode.

Remember: `sql_safe_updates` is a guardrail against overly broad accidental operations. It does not replace transactions, backups, privilege management, SQL reviews, or checking affected row counts.

## 2. sql_safe_updates Is Not a Flag Inside sql_mode

The two concepts have similar names, yet they are two independent system variables:

| Component | Nature | Example |
|---|---|---|
| `sql_mode` | System variable containing a comma-separated list of modes; each mode alters part of SQL syntax or semantics | `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `ANSI_QUOTES` |
| `sql_safe_updates` | Boolean toggle system variable controlling certain `UPDATE`/`DELETE` statements lacking key conditions or `LIMIT` | `0` = off, `1` = on |

The name `sql_safe_updates` starts with `sql_`, but that does not make it a member of the `sql_mode` list. You will not find `SAFE_UPDATES` in the `@@sql_mode` string, nor can you enable it by appending `'SAFE_UPDATES'` to `sql_mode`.

Inspect both separately:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.sql_safe_updates AS session_safe_updates;

SHOW SESSION VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_safe_updates';
```

The `sql_mode` output is a string like `ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,...` depending on version and configuration. `sql_safe_updates` returns its own on/off value.

### 2.1. Some Common sql_mode Flags

The following modes are examples of actual members of `sql_mode`:

| Mode | General Impact |
|---|---|
| `STRICT_TRANS_TABLES` | Applies strict validation to invalid or missing data on transactional tables; behavior with non-transactional tables has certain differences |
| `STRICT_ALL_TABLES` | Applies broader strict handling across table types; details depend on operation type and engine |
| `ONLY_FULL_GROUP_BY` | Controls selecting non-aggregated columns in `GROUP BY` queries |
| `ANSI_QUOTES` | Uses double quotes to quote identifiers instead of string literals |
| `NO_ENGINE_SUBSTITUTION` | Raises an error when the requested engine is unavailable instead of silently substituting another engine in cases governed by the mode |
| `ERROR_FOR_DIVISION_BY_ZERO` | Affects how division by zero is handled in contexts defined by MySQL |

Default mode lists and support status can change between MySQL versions. Some legacy modes have been merged, altered, or removed. Check the exact `@@SESSION.sql_mode` string of the server you are using along with the documentation for that version.

### 2.2. Both Variables Can Be Configured Independently

For example, a session with strict mode enabled but safe updates disabled:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES';
SET SESSION sql_safe_updates = 0;
```

Or a session enabling safe updates without modifying the SQL mode list:

```sql
SET SESSION sql_safe_updates = 1;
```

In real applications, avoid reassigning the entire `sql_mode` just to change one flag, as doing so can accidentally drop needed modes. `sql_safe_updates` is managed via its own separate variable.

## 3. Checking Safe Updates Status

### 3.1. Viewing SESSION and GLOBAL Values

```sql
SELECT
    @@GLOBAL.sql_safe_updates AS global_safe_updates,
    @@SESSION.sql_safe_updates AS session_safe_updates;
```

- `@@GLOBAL.sql_safe_updates` is the server-level default used to initialize new sessions.
- `@@SESSION.sql_safe_updates` is the value currently applied to the current connection.

The two values can differ. If a client connected before GLOBAL was changed, that session typically retains its old value. Therefore, after changing GLOBAL configuration, re-check new connections and active connection pools.

### 3.2. Using SHOW VARIABLES

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_safe_updates';
SHOW SESSION VARIABLES LIKE 'sql_safe_updates';
```

If an administrative tool only displays the session value, do not assume it is the global configuration. When investigating differences between two environments, capture both values along with `VERSION()` and `@@SESSION.sql_mode`.

### 3.3. Default Value

In MySQL, `sql_safe_updates` typically defaults to `OFF` (`0`). Client tools may enable this variable automatically for their sessions, so the value observed from MySQL Workbench or another client can differ between connections even when server configuration has not changed.

Do not rely on an installation's default value. Inspect the session used by the application or tool directly.

## 4. Enabling and Disabling sql_safe_updates

### 4.1. Enabling for the Current Session

This is appropriate for testing or protecting an administrative connection:

```sql
SET SESSION sql_safe_updates = 1;

SELECT @@SESSION.sql_safe_updates;
```

The value `1` enables safe updates for the current connection. Other sessions are unaffected.

Shorthand syntax:

```sql
SET sql_safe_updates = ON;
```

In `SET` statements, session scope is the default if `GLOBAL` is not specified.

### 4.2. Disabling for the Current Session

```sql
SET SESSION sql_safe_updates = 0;
```

Disable it only with a clear reason, after confirming the exact table and data scope, previewing the target rows, and preparing a recovery plan. Do not make disabling safe updates a reflex whenever error 1175 appears.

If you need to disable it temporarily in a session, save the original value to restore later:

```sql
SET @previous_safe_updates = @@SESSION.sql_safe_updates;

-- Execute only after verifying the statement and data scope
SET SESSION sql_safe_updates = 0;

-- Run the verified administrative operation here

-- Restore the initial state in the same connection
SET SESSION sql_safe_updates = @previous_safe_updates;
```

If the operation fails partway or the client disconnects, open a new session and verify state before continuing. User variable `@previous_safe_updates` exists only within the session that created it.

### 4.3. Setting the GLOBAL Value

Accounts with appropriate system variable administration privileges can set the default for new sessions:

```sql
SET GLOBAL sql_safe_updates = 1;
```

This change does not automatically enable safe updates on already open sessions. New connections inherit the GLOBAL value at session creation time unless the client or application overrides it via session configuration.

To persist changes across restarts, configure it in `my.cnf`/`my.ini` or use a persistent configuration mechanism supported by your version. Example in the server configuration file:

```ini
[mysqld]
sql_safe_updates = ON
```

MySQL 8.0 supports `SET PERSIST` for eligible system variables:

```sql
SET PERSIST sql_safe_updates = ON;
```

`SET GLOBAL` changes runtime; `SET PERSIST` both changes runtime and saves the configuration to apply after restarts. Verify version, privileges, and configuration management policy before using it. In cloud or container environments, update the service's canonical configuration source to prevent overrides upon redeployment.

## 5. Blocked vs. Permitted Statements

Suppose we have the table:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_login DATETIME NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE = InnoDB;
```

Enable safe updates in the session:

```sql
SET SESSION sql_safe_updates = 1;
```

### 5.1. UPDATE Without WHERE or LIMIT

```sql
UPDATE employees
SET status = 'INACTIVE';
```

The statement has neither a `WHERE` condition nor a `LIMIT`, so it is rejected by safe update mode.

### 5.2. DELETE Without WHERE or LIMIT

```sql
DELETE FROM employees;
```

This statement is also rejected because it could delete every row in the table.

### 5.3. WHERE Using a Key

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id = 105;

DELETE FROM employees
WHERE employee_id = 105;
```

`employee_id` is the primary key, used in the filter condition in a way that supports key lookup. These statements satisfy the key condition of safe updates.

Another example using the index on `department_id`:

```sql
UPDATE employees
SET status = 'REVIEW'
WHERE department_id = 20;
```

The condition uses an indexed column. However, if department 20 holds nearly all employees, the statement can still affect a huge number of rows. Safe updates only checks a technical condition; it does not understand business intent.

### 5.4. WHERE Without a Key and Without LIMIT

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01';
```

Assume `last_login` has no index. This condition neither uses a key nor specifies `LIMIT`, so safe update mode can reject it. If business queries frequently filter by `last_login`, evaluate adding an index, but do not create indexes solely to bypass safe updates. Consider overall workload and query plans.

### 5.5. LIMIT Can Satisfy Safe Updates

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01'
LIMIT 100;
```

The `LIMIT` clause satisfies the guardrail even though `WHERE` does not use a key. However, it only caps the number of updated rows; without `ORDER BY`, do not assume which exact rows will be chosen. The statement can still modify 100 unintended rows.

For batch tasks, specify explicit ordering and conditions:

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01'
ORDER BY last_login, employee_id
LIMIT 100;
```

Even better, if the target primary key set can be determined beforehand, capture the target ID list and update by those IDs. `LIMIT` is a row-count cap, not proof that the right data was selected.

## 6. Safe Updates Does Not Guarantee Business-Safe Statements

A statement can pass safe update mode and still be severely wrong.

Example:

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id > 0;
```

The condition uses the primary key, yet if all IDs are positive, the statement still updates nearly the entire table. Safe updates does not evaluate estimated row counts, does not understand business goals, and does not require confirming the affected count.

Similarly:

```sql
DELETE FROM employees
WHERE department_id = 20
LIMIT 1000;
```

The statement has an index and `LIMIT`, yet it could still delete 1,000 valid rows the operator did not intend to delete.

Therefore, use an independent verification workflow:

1. Write the `WHERE` condition using keys or exact business criteria.
2. Run `SELECT` with the same condition to inspect target rows.
3. Count the rows expected to be affected.
4. Verify before/after values and primary keys.
5. Execute inside a transaction if the engine and operation permit.
6. Check the affected row count and commit when the result is right.

Example with InnoDB:

```sql
START TRANSACTION;

SELECT employee_id, status
FROM employees
WHERE employee_id BETWEEN 100 AND 120
ORDER BY employee_id
FOR UPDATE;

UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id BETWEEN 100 AND 120;

SELECT ROW_COUNT() AS affected_rows;

-- If row count and data are correct:
COMMIT;

-- Otherwise, replace COMMIT with ROLLBACK before ending the transaction.
```

This example illustrates locking and inspecting the row set inside a transaction. In real operations, do not submit both `COMMIT` and `ROLLBACK` together as a fixed batch; the operator chooses one after reviewing the output. Transactions should be kept short to avoid holding locks too long.

## 7. Procedure for Handling Error 1175

Error 1175 typically occurs when safe update mode is enabled and an `UPDATE`/`DELETE` statement does not satisfy the key or `LIMIT` requirement.

When encountering this error:

### Step 1: Confirm the Session Has It Enabled

```sql
SELECT @@SESSION.sql_safe_updates;
```

If the result is `1`, safe updates is active for the current connection.

### Step 2: Review the Statement and Data Target

Do not merely slap on `LIMIT 1` or turn off safe updates to make the error disappear. Identify the table, condition, and business row count meant to change.

### Step 3: Inspect Target Rows with SELECT

```sql
SELECT employee_id, last_login, status
FROM employees
WHERE last_login < '2025-01-01'
ORDER BY last_login, employee_id;

SELECT COUNT(*) AS target_rows
FROM employees
WHERE last_login < '2025-01-01';
```

If the count is too large or wrong, fix the condition. If the query does not use an index, use `EXPLAIN SELECT` to understand the access path:

```sql
EXPLAIN
SELECT employee_id
FROM employees
WHERE last_login < '2025-01-01';
```

### Step 4: Choose the Appropriate Execution Approach

- If exact keys are known, use the key in `WHERE`.
- If batching is needed, use `ORDER BY` and `LIMIT` deliberately while tracking progress.
- If the filter condition is frequent and performance-critical, evaluate adding an appropriate index.
- If a non-key operation is genuinely needed, disable safe updates only in that specific session after review and with other safeguards in place.

### Step 5: Restore Configuration

If `sql_safe_updates` was temporarily disabled, re-enable it or restore the prior value in the same session. Re-verify `@@SESSION.sql_safe_updates` before finishing.

## 8. Impact of SQL Clients and MySQL Workbench

`sql_safe_updates` is a MySQL Server variable, yet a client can enable it upon opening a connection. MySQL Workbench has a Safe Updates option under SQL Editor Preferences. When enabled, Workbench can set safe update mode for the session it uses.

Consequently, this situation can occur:

- A terminal connection runs an `UPDATE` statement successfully.
- Running the same statement in Workbench hits error 1175.
- `@@GLOBAL.sql_safe_updates` is still `0`, while Workbench's `@@SESSION.sql_safe_updates` is `1`.

When encountering discrepancies, check the SESSION variable from the exact tab/connection running the statement. If changing the Safe Updates option in Workbench, you may need to reconnect for the new setting to take effect on a new session; exact behavior depends on the Workbench version.

Do not disable server-wide protections just to stop one client from erroring. If only one admin tool needs different behavior, adjust at the client/session level while retaining data verification workflows.

## 9. Connection Pools and Session State

`sql_safe_updates` has SESSION scope. If an application uses a connection pool, each physical connection can retain its own value. For example, one connection may be initialized with `sql_safe_updates = 1`, while another may be `0` due to different configuration or manual alteration.

For consistent behavior:

- Set the session value during pool connection initialization.
- Do not arbitrarily modify session variables during a request and return the connection to the pool without restoring it.
- If the pool supports resetting session state, verify whether this variable gets reset.
- Inspect `@@SESSION.sql_safe_updates` on the actual connection when debugging errors.
- Do not assume GLOBAL changes update existing physical connections inside the pool.

For business applications, safe updates is often configured as an extra safeguard for administrative accounts or operational tools. Do not use it as a replacement for privilege control: application accounts still need minimal `UPDATE`/`DELETE` privileges scoped by table and function.

## 10. Comparing sql_safe_updates with Other Safeguard Mechanisms

| Mechanism | What It Protects | Limitations |
|---|---|---|
| `sql_safe_updates` | Blocks certain UPDATE/DELETE statements lacking a key in WHERE and lacking LIMIT | Does not understand business logic, does not stop all broad statements, and does not replace access privileges |
| Strict `sql_mode` | Controls certain missing or invalid data | Does not prevent syntactically valid bulk updates/deletes |
| Primary key/foreign key/unique/check | Protects identity and certain data integrity rules | Cannot tell whether the user intended to modify the chosen set of rows |
| InnoDB transactions | Allows committing/rolling back a group of changes and controls concurrency | Requires proper scope, locking, and error handling; cannot rescue already committed operations |
| GRANT/REVOKE | Restricts which objects an account may read/write | Table-level UPDATE privilege can still allow accidentally updating many rows |
| Backups and point-in-time recovery | Supports data restoration after incidents | Time-consuming and no substitute for pre-operation checks |
| Review/preview with SELECT | Helps operators confirm the target row set | Depends on process discipline and operator care |

These mechanisms complement one another. A sound operational workflow combines least-privilege permissions, safe updates for admin sessions, data previews, appropriate transactions, and restorable backups.

## 11. Scenarios Not to Misunderstand

### 11.1. SELECT Is Not Blocked by Safe Updates

`sql_safe_updates` focuses on `UPDATE` and `DELETE`. It is not a general cap on `SELECT` queries and does not prevent a query from reading an entire table.

### 11.2. INSERT Does Not Use This Mechanism

`INSERT`, `REPLACE`, `TRUNCATE TABLE`, `DROP TABLE`, and other DDL statements have their own rules; do not rely on `sql_safe_updates` to protect them. In particular, `TRUNCATE TABLE` is not a `DELETE` with `WHERE` and is not guarded by safe updates like a normal DELETE statement.

### 11.3. Having a Key Does Not Mean Few Rows

A condition like `WHERE id > 0` uses a key column yet can match almost the whole table. Safe updates is not a row-count estimator and does not replace running `SELECT COUNT(*)` or inspecting target data.

### 11.4. Having LIMIT Does Not Mean the Right Rows

`LIMIT 100` caps the number of processed rows, yet without deterministic ordering, the affected row set can be unstable. Pair `ORDER BY` with a stable key and business conditions, then monitor each batch.

### 11.5. Safe Updates Does Not Replace Database Privileges

If an account lacks `UPDATE` or `DELETE` privileges, enabling safe updates grants no extra permissions. Conversely, an account with write privileges can still execute any operation permitted by safe updates. Design `GRANT` rules under the principle of least privilege.

## 12. Quick Inspection Query Set

```sql
-- Server version and SQL mode / safe updates status
SELECT
    VERSION() AS server_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_safe_updates AS global_safe_updates,
    @@SESSION.sql_safe_updates AS session_safe_updates;

-- Check individual sql_mode flags
SELECT
    FIND_IN_SET('STRICT_TRANS_TABLES', @@SESSION.sql_mode) > 0
        AS strict_trans_tables_enabled,
    FIND_IN_SET('ONLY_FULL_GROUP_BY', @@SESSION.sql_mode) > 0
        AS only_full_group_by_enabled,
    FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0
        AS ansi_quotes_enabled;

-- Enable safe updates for the current session
SET SESSION sql_safe_updates = 1;

-- Re-verify
SELECT @@SESSION.sql_safe_updates;

-- Preview an update operation before executing
SELECT employee_id, status, last_login
FROM employees
WHERE employee_id BETWEEN 100 AND 120
ORDER BY employee_id;

SELECT COUNT(*) AS rows_to_update
FROM employees
WHERE employee_id BETWEEN 100 AND 120;
```

The statements above use the illustrative table name `employees`; substitute your actual schema and run read-only preview queries before building data-modification statements.

## 13. Checklist Before UPDATE or DELETE

- [ ] Confirmed the exact server, database, and active session.
- [ ] Checked `@@SESSION.sql_safe_updates` and `@@SESSION.sql_mode`.
- [ ] Clearly defined the business target and `WHERE` condition.
- [ ] Ran `SELECT` with the same condition and inspected affected primary keys.
- [ ] Counted expected rows to be modified/deleted.
- [ ] If using a key, verified it is the appropriate key/index and the condition is not overly broad.
- [ ] If using `LIMIT`, chose a stable ordering and batching plan.
- [ ] Considered transactions, locking, and execution duration.
- [ ] Verified backups/recovery capability commensurate with risk level.
- [ ] If temporarily disabling safe updates, saved old state and included a re-enable step.
- [ ] Verified affected row counts and resulting data after the operation.

## 14. Conclusion

`sql_safe_updates` is a system variable independent of `sql_mode`. It helps block certain `UPDATE`/`DELETE` statements lacking both a key-based condition and a `LIMIT`, thereby reducing the risk of accidentally affecting an entire table. It can be enabled per session, defaulted at GLOBAL scope, or stored in server configuration.

Distinguish it from the flags that actually belong to `sql_mode`, inspect the SESSION value from the exact connection, and never treat safe updates as an absolute safety guarantee. Before any write/delete operation, still preview the row set, confirm row counts, use transactions where appropriate, and maintain data recovery plans.
