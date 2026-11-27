# GLOBAL/SESSION Scope of sql_mode and How to Check Effective Configuration

`sql_mode` is a system variable that controls certain syntax rules and how MySQL handles data in SQL statements. It can be set at two scopes: `GLOBAL` as the default value for new connections, and `SESSION` which determines the behavior on the current connection. When an application uses a connection pool, each connection can maintain its own `sql_mode`, so the global value observed from an administrative session is not necessarily the value used by the application's statements.

In the `DATABASE_MYSQL` module, properly understanding the scope and effective configuration of `sql_mode` helps predict how MySQL validates data, handles out-of-range values, evaluates `GROUP BY`, parses quotes, and executes expressions. This is an important part of schema design, SQL querying, transactions, and database operations.

## Objectives

After this lesson, you will be able to:

- Distinguish between `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode`.
- Explain how a session inherits the global value when opening a connection.
- Check the `sql_mode` actually applied on the connection running a query.
- Read the configuration source via Performance Schema and distinguish between runtime configuration and persistent configuration.
- Change modes at the session or global level, or persist them across restarts using the appropriate mechanism.
- Identify modes that affect strict validation, `GROUP BY`, string syntax, and application compatibility.
- Establish a safe rollout and rollback procedure for `sql_mode` changes.

## 1. What is `sql_mode`?

`sql_mode` is a comma-separated list of modes. Each mode adjusts a part of MySQL's behavior, such as:

- Checking whether data is within the column's domain/range.
- Handling invalid dates or division by zero.
- Requiring columns in `SELECT` to conform to `GROUP BY`.
- Interpreting double quotes and escape characters in strings.
- Handling cases where the specified storage engine is unavailable.

For example, two sessions can run the exact same `INSERT` statement yet receive different results if one session has strict mode enabled and the other does not. Similarly, a `SELECT` query might be valid in an older mode but rejected when `ONLY_FULL_GROUP_BY` is enabled.

`sql_mode` is neither an access-control list nor a replacement for schema constraints. It governs how the server interprets and validates statements; `GRANT`, `REVOKE`, transactions, and constraints still serve their own distinct roles.

## 2. GLOBAL and SESSION Scopes

MySQL maintains two values for `sql_mode`:

| Scope | How to Read | Meaning | Impact |
|---|---|---|---|
| Global | `@@GLOBAL.sql_mode` | The server's default value for new connections | Used as the initial value for new sessions; changing it does not modify already open sessions |
| Session | `@@SESSION.sql_mode` | The mode value of the current connection | Controls statements executed on that specific connection |

When a client connects, MySQL initializes the session with the current global value. Afterward, the session can change its own value using `SET SESSION sql_mode = ...`. This change does not affect other connections and does not automatically update the global value.

### 2.1. Illustrating Inheritance on Connection

Suppose the server has a global mode of:

```text
ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

When an application opens a new connection, the session typically starts with that same list. If the connection runs:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';
```

then only the current connection switches to `ANSI_QUOTES`. Other already-open connections keep their previous mode; subsequent connections still receive the global value, unless client/pool initialization configuration alters the session immediately after connecting.

### 2.2. Changing GLOBAL Does Not Update Running Sessions

For example, an administrator runs:

```sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Subsequent new connections will inherit the new global list. A connection that already existed prior to this command keeps its old `@@SESSION.sql_mode` until that connection itself changes its session mode or is closed and recreated.

This point is critical for connection pools: restarting MySQL is not always the only way required to refresh sessions. If the pool holds old connections, you need to recycle/reconnect them or explicitly configure the session on each connection.

## 3. Checking the Effective Value

Do not just check the configuration file or the global value. Read the session value directly on the connection executing the query.

### 3.1. Viewing Both Scopes

```sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@sql_mode AS unqualified_sql_mode,
    CONNECTION_ID() AS connection_id;
```

An unqualified `@@sql_mode` is interpreted as the session value when the variable has session scope. Therefore, in operational scripts and documentation, explicitly write `@@GLOBAL.sql_mode` or `@@SESSION.sql_mode` to avoid confusion.

### 3.2. Using SHOW VARIABLES

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

Running `SHOW VARIABLES LIKE 'sql_mode'` without specifying a scope typically returns the session value of the current connection. When comparing server and connection configuration, use both statements with explicit scopes.

### 3.3. Checking on the Actual Application Connection

If the application uses JDBC, run the verification query through the exact `Connection` obtained from the pool:

```java
String sql = "SELECT CONNECTION_ID(), @@GLOBAL.sql_mode, @@SESSION.sql_mode";

try (PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        long connectionId = resultSet.getLong(1);
        String globalMode = resultSet.getString(2);
        String sessionMode = resultSet.getString(3);
        // Record these values in diagnostic logs; do not log credentials.
    }
}
```

An administrative terminal session and an application connection can have different `SESSION` values. When investigating errors that only occur in a service, log `CONNECTION_ID()` along with `@@SESSION.sql_mode` from the failing connection rather than inferring from another session.

## 4. Reading the Effective Configuration Source

Runtime values show which mode MySQL is currently using. When you need to know where a value came from, you can inspect metadata in Performance Schema.

### 4.1. `performance_schema.variables_info`

On MySQL 8.0 versions that include this table, query:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'sql_mode';
```

This table provides the source of the global variable, the option file path if applicable, the runtime set timestamp, and the user/host that set the variable. `VARIABLE_SOURCE` values can indicate whether the variable came from the compiled default, an option file, the command line, a persisted setting, or a runtime change. The specific set of values and metadata may vary by version.

If Performance Schema is disabled or the table is unavailable in the version in use, you can still check the value via `@@GLOBAL.sql_mode` and `SHOW GLOBAL VARIABLES`. In that case, additionally inspect the server configuration and startup arguments according to your operational access rights.

### 4.2. Checking Persisted Configuration

In MySQL 8.0.11 and later, `SET PERSIST` can save global variables to the self-managed configuration file `mysqld-auto.cnf`. If Performance Schema has the `persisted_variables` table, check:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'sql_mode';
```

The persisted value reflects configuration saved to be applied on server startup. It does not replace checking the current `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode`.

### 4.3. Distinguishing Configuration Sources

| Source | Example | When Effective |
|---|---|---|
| MySQL default | Version-specific default value | When no other configuration overrides it |
| Option file | `sql_mode=...` in the `[mysqld]` section | When the server starts and reads the option file |
| Command line | `--sql-mode=...` at server startup | When the server starts with that argument |
| Persisted setting | `SET PERSIST sql_mode = ...` | Saved to persist across startups; also changes global runtime when using `SET PERSIST` |
| Runtime global | `SET GLOBAL sql_mode = ...` | Immediately for the global value and newly opened connections; not persisted across restarts unless saved elsewhere |
| Runtime session | `SET SESSION sql_mode = ...` | Immediately on the current connection |

When multiple sources configure the same variable, do not guess the final effective source just by reading a single file. Inspect `VARIABLE_SOURCE`/`VARIABLE_PATH` if available, then verify the runtime value. `mysqld-auto.cnf` is managed by MySQL; do not edit this file directly with an editor.

## 5. Changing sql_mode at the SESSION Level

`SET SESSION` changes the mode of the current connection. This is appropriate for experimentation, running scoped migrations, or configuring an application with specific compatibility requirements.

```sql
SET SESSION sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

When assigning a new string, MySQL replaces the entire current list with the specified list. If you accidentally omit a required mode, the session will lose that mode. Therefore, read and save the original value before making changes.

### 5.1. Adding or Removing a Mode

If the MySQL Sys Schema is available, you can use `sys.list_add()` and `sys.list_drop()` to manipulate the list:

```sql
SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SET SESSION sql_mode =
  sys.list_drop(@@SESSION.sql_mode, 'ANSI_QUOTES');
```

These two functions preserve the other modes in the list. If the Sys Schema is absent or unavailable, explicitly assign the full desired mode string.

### 5.2. Saving and Restoring the Value Before Testing

In a lab, you can store the old value in a session variable:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SELECT @@SESSION.sql_mode;

SET SESSION sql_mode = @saved_sql_mode;
```

The `@saved_sql_mode` variable also belongs to the session and persists beyond the statement. If the connection is returned to a pool, both the variable and the session state must be restored before returning the connection. In applications, prefer a fixed pool configuration rather than arbitrarily altering the mode per request.

## 6. Changing sql_mode at the GLOBAL Level

`SET GLOBAL` changes the running global value:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
```

This operation requires appropriate system administration privileges, typically `SYSTEM_VARIABLES_ADMIN` (or the legacy `SUPER` privilege in corresponding versions). Regular users can set the session mode for their own connection if the variable permits it, but cannot arbitrarily change the global setting.

`SET GLOBAL` does not update open sessions, and runtime changes will be lost after a restart unless saved in an option file or persisted setting. Verify existing and new connections separately after making changes.

## 7. Persisting Configuration Across Restarts

There are three common ways to make a mode persist across server restarts. Choose one clear management source to avoid duplicate configurations that are hard to trace.

### 7.1. Configuring in an Option File

In the MySQL configuration file, set `sql_mode` under the `[mysqld]` section:

```ini
[mysqld]
sql_mode=ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

The file path depends on the distribution and installation method, such as `/etc/my.cnf`, `/etc/mysql/my.cnf`, or included files. After editing, restart MySQL according to operational procedures and then verify `@@GLOBAL.sql_mode` and new sessions.

Do not replace the entire default list with a shortened string unless you understand the modes being removed. When creating a new configuration, retrieve the current list, determine which modes to add or remove, and write out the complete desired list.

### 7.2. `SET PERSIST`

MySQL 8.0.11 and later support:

```sql
SET PERSIST sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST` updates the global runtime value and saves the configuration to apply across restarts. This operation requires appropriate administrative privileges. After running it, verify both the global value and the persisted entry if Performance Schema supports it.

### 7.3. `SET PERSIST_ONLY`

If you only want to write the value for the next startup without changing the current global runtime value:

```sql
SET PERSIST_ONLY sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST_ONLY` is suitable when preparing restart configuration ahead of a maintenance window. It does not alter the current `@@GLOBAL.sql_mode`; new sessions opened before the restart still inherit the current global value.

### 7.4. Removing a Persisted Setting

If you need to remove a variable's persisted override:

```sql
RESET PERSIST IF EXISTS sql_mode;
```

This statement clears the persisted configuration of `sql_mode`; it does not automatically revert a global runtime value that was previously changed. If you need to change the running value, set `SET GLOBAL` back to the desired list and verify. After a restart, the server will take its value from the remaining configuration sources.

Do not delete or edit `mysqld-auto.cnf` manually. Use MySQL administrative statements to manage persisted settings.

## 8. Modes That Commonly Affect Applications

The default list of modes depends on the version and build. MySQL 8.0/8.4 typically enable modes such as `ONLY_FULL_GROUP_BY`, `STRICT_TRANS_TABLES`, `NO_ZERO_IN_DATE`, `NO_ZERO_DATE`, `ERROR_FOR_DIVISION_BY_ZERO`, and `NO_ENGINE_SUBSTITUTION`. Always inspect the server's actual value rather than assuming every environment shares the same defaults.

| Mode | Main Impact | What to Check in the Application |
|---|---|---|
| `STRICT_TRANS_TABLES` | Rejects many invalid or out-of-range values for transactional tables; handles non-transactional tables with separate rules | Validate data and handle insert/update errors |
| `STRICT_ALL_TABLES` | Applies broader strict validation even to non-transactional tables; an error mid-way through a multi-row statement may leave previously written rows | Do not assume every engine can roll back a single statement |
| `ONLY_FULL_GROUP_BY` | Requires non-aggregated columns in SELECT/HAVING/ORDER BY to be valid with GROUP BY or functionally dependent on the grouping key | Fix ambiguous aggregate queries; do not disable the mode just to make a query run |
| `NO_ZERO_DATE` | Restricts or rejects zero date values depending on the SQL mode/strict mode combination | Use `NULL` or a valid business value instead of dummy dates |
| `NO_ZERO_IN_DATE` | Restricts dates with a zero month or day | Validate dates before writing |
| `ERROR_FOR_DIVISION_BY_ZERO` | Adjusts handling of division by zero during writes and in certain expression contexts | Check denominators and handle `NULL`/errors per business logic |
| `NO_ENGINE_SUBSTITUTION` | Raises an error if the requested engine is unavailable instead of silently substituting the default engine | Verify installed engines and DDL |
| `ANSI_QUOTES` | Uses double quotes for identifiers; string literals should use single quotes | Find SQL statements using `"text"` to represent literals |
| `NO_BACKSLASH_ESCAPES` | Backslashes no longer escape strings in the default manner | Check literals and SQL generated by legacy code |
| `PIPES_AS_CONCAT` | The `||` operator is interpreted as string concatenation rather than logical OR | Check SQL expressions using `||` |

Some older modes have been deprecated or removed in MySQL 8.0. For example, `NO_AUTO_CREATE_USER` was removed in MySQL 8.0.11; do not copy a mode list verbatim from a MySQL 5.6/5.7 configuration to a new server without checking. Aliases such as `ANSI` or `TRADITIONAL` represent groups of modes; read the effective list after setting them to know which components the server is applying.

### 8.1. Strict Mode and Out-of-Range Data Example

Create a lab table:

```sql
CREATE TABLE mode_quantity (
    id INT NOT NULL PRIMARY KEY,
    quantity TINYINT UNSIGNED NOT NULL
) ENGINE=InnoDB;
```

In a session with strict mode:

```sql
SET SESSION sql_mode =
  sys.list_add(@@SESSION.sql_mode, 'STRICT_TRANS_TABLES');

INSERT INTO mode_quantity (id, quantity)
VALUES (1, 300);
```

`TINYINT UNSIGNED` only accepts values 0–255. With strict mode, the value 300 is rejected instead of silently being stored as the boundary value. Check the error and table state:

```sql
SHOW WARNINGS;
SELECT * FROM mode_quantity;
```

In a non-strict environment, MySQL may adjust out-of-range values and emit a warning. `INSERT IGNORE` can also convert certain errors into warnings and continue processing. Do not rely on clipping or `IGNORE` as a substitute for data validation.

### 8.2. ONLY_FULL_GROUP_BY Example

Suppose the `orders` table has multiple orders per customer. The following query is ambiguous because a customer can have multiple `status` values:

```sql
SELECT customer_id, status, COUNT(*)
FROM orders
GROUP BY customer_id;
```

When `ONLY_FULL_GROUP_BY` is enabled, MySQL rejects this if `status` is neither grouped, aggregated, nor functionally dependent on `customer_id`. Fix the query according to the intended semantics:

```sql
SELECT customer_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status;
```

Or if a single aggregated status is needed, use an intentional aggregate expression like `MAX(status)` only when that selection makes business sense. Do not disable `ONLY_FULL_GROUP_BY` to mask a nondeterministic query.

### 8.3. ANSI_QUOTES Example

When `ANSI_QUOTES` is off, double quotes can be used to enclose strings in some configurations. When enabled, double quotes are used for identifiers:

```sql
SET SESSION sql_mode = sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');

SELECT "customer_name" FROM customer;
SELECT 'customer_name' AS label;
```

In the first statement, `"customer_name"` is interpreted as a column name; in the second, `'customer_name'` is a string literal. For strong compatibility across modes, always use single quotes for string literals and backticks for identifiers that require quoting.

## 9. SQL Mode and Stored Programs

MySQL stores the `sql_mode` in effect when creating a stored procedure, stored function, trigger, or event. When these objects execute, they use the mode recorded at creation time rather than simply adopting the caller's current session mode.

This can cause surprises when an administrator changes the global/session mode, yet an older procedure continues evaluating expressions under the previous rules. When synchronization is needed, consider recreating or altering the object through a tested migration process.

Check the saved mode for routines:

```sql
SELECT ROUTINE_NAME, ROUTINE_TYPE, SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE();
```

Check triggers and events:

```sql
SELECT TRIGGER_NAME, SQL_MODE
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE();

SELECT EVENT_NAME, SQL_MODE
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE();
```

When deploying routines/triggers/events, record the `sql_mode` of the migration connection. If the build pipeline and production have different modes, created objects may store different modes.

## 10. Connection Pools and Per-Application Configuration

For Java applications or multi-worker services, a pool may maintain dozens of connections. Each connection is an independent session, so running `SET SESSION sql_mode` on one connection does not configure the remaining connections.

Practical principles:

- Set the global mode to match the server's general standard.
- Configure session modes consistently when the pool creates or initializes new connections.
- Do not arbitrarily change the session mode per request; if unavoidable, restore it before returning the connection to the pool.
- When changing the global setting, recycle the pool or inspect/reconfigure existing connections if you want them to pick up the new mode as well.
- Log `CONNECTION_ID()` and `@@SESSION.sql_mode` when diagnosing a specific connection.
- Check the mode of migration tools, background jobs, CLIs, and services; they may open sessions with different configurations.

A simple check on a connection obtained from the pool:

```sql
SELECT
    CONNECTION_ID(),
    @@GLOBAL.sql_mode,
    @@SESSION.sql_mode;
```

Do not treat a check query from an administrative terminal as proof that every session in the pool shares the same configuration.

## 11. Safe Procedure for Changing sql_mode

When standardizing the mode for an environment, follow this sequence:

1. Record the MySQL version, `@@GLOBAL.sql_mode`, and `@@SESSION.sql_mode` from both the server and the application connection.
2. Identify the configuration source via `performance_schema.variables_info`, persisted variables, and option files if you have access to inspect them.
3. Locate queries, migrations, stored programs, and triggers that depend on the old mode.
4. Test the target mode in a lab session or staging environment; run tests for boundary data, aggregate queries, and application-generated SQL.
5. If only one application needs a specific mode, configure `SESSION` via the connection pool. If it is a server-wide standard, plan changes for `GLOBAL` and the persistent source.
6. After the change, verify the global setting, open a new connection to confirm inheritance, and then verify recycled pool connections.
7. Monitor SQL errors, warnings, failed jobs, and migration results; retain the before/after mode lists along with a rollback plan.

Example of recording the state before changing:

```sql
SELECT VERSION(), @@GLOBAL.sql_mode, @@SESSION.sql_mode;

SELECT VARIABLE_NAME, VARIABLE_SOURCE, VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'sql_mode';
```

Example of restoring global runtime to the value saved in the change plan:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

The list above is just an example. When rolling back, use the exact list recorded before the change for that environment. If `SET PERSIST` was used, handle the persisted override separately; resetting the global runtime does not automatically remove persisted configuration.

## 12. Hands-on Exercises

Perform on an authorized lab or staging database:

1. Record `VERSION()`, `@@GLOBAL.sql_mode`, `@@SESSION.sql_mode`, and `CONNECTION_ID()`.
2. Open two independent connections. Set different `SESSION sql_mode` values on each and demonstrate that changes on connection A do not affect connection B.
3. Change `GLOBAL sql_mode`, then compare an old session with a new connection to confirm the inheritance mechanism.
4. Use `sys.list_add()` to add `ANSI_QUOTES` and `sys.list_drop()` to remove the mode; verify the list after each operation.
5. Try inserting an out-of-range value into a `TINYINT UNSIGNED` column with strict mode on/off in the lab; read the errors and warnings.
6. Try an aggregate query that violates `ONLY_FULL_GROUP_BY`, then fix it with business-accurate `GROUP BY`/aggregates.
7. Read `performance_schema.variables_info` and `persisted_variables` if the version supports them; identify the global configuration source.
8. Create a stored procedure in a session with a specific mode, then change the session mode and inspect `information_schema.ROUTINES.SQL_MODE`.
9. Use a connection pool in a sample application, acquire multiple connections, and verify each session has the expected mode.
10. Write a short rollout/rollback procedure for a mode change, explicitly addressing old connections, new connections, and persisted settings.

You complete this lesson when you can explain why global and session values can differ, know how to query the effective configuration on the right connection, and can change modes without surprising other applications.

## 13. Key Takeaways

- `@@GLOBAL.sql_mode` is the default for new connections; `@@SESSION.sql_mode` controls the current connection.
- `SET GLOBAL` does not alter open sessions; connection pools may continue holding the old mode.
- `SET SESSION` replaces the current connection's mode list; avoid unintentionally dropping existing modes.
- Use `performance_schema.variables_info` to view the global variable source and `persisted_variables` to view saved configuration when supported by the version.
- `SET PERSIST` changes global runtime and persists across restarts; `SET PERSIST_ONLY` only saves for the next startup.
- `RESET PERSIST` removes a persisted override but does not automatically revert global runtime.
- Default modes vary by version; always check `VERSION()` and the actual value.
- Test strict mode, `ONLY_FULL_GROUP_BY`, and string syntax before changing production.
- Stored programs, triggers, and events can store `sql_mode` at creation time; check metadata when behavior differs from expectations.
- Record before/after state, verify new connections, and recycle pools according to the rollout plan.
