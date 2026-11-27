# When SQL Mode Is Captured for Stored Programs

MySQL saves the `sql_mode` value active in the session at the time a stored program is created. When a stored procedure or stored function is called, MySQL executes the program body using the SQL mode stored with the object, rather than simply using the calling session's current SQL mode. After the routine finishes, the calling session's SQL mode is restored.

This means two procedures created at different times under different SQL modes can produce different results or behaviors, even when called from the exact same connection with the exact same `CALL` statement. Changing `@@GLOBAL.sql_mode` or `@@SESSION.sql_mode` after creating a routine does not automatically update the saved SQL mode of existing routines.

In the **DATABASE_MYSQL** module, stored programs encapsulate SQL logic on the server side. To keep procedure/function behavior consistent across development, staging, and production environments, you must control the SQL mode of the connection running DDL, know how to inspect metadata, and maintain a process to recreate routines when changing modes.

## 1. What is SQL mode?

`sql_mode` is a system variable containing one or more modes that affect how MySQL parses statements, validates data, and handles special cases.

Checking session and server SQL modes:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_mode AS global_sql_mode;
```

- `@@SESSION.sql_mode` applies to the current connection.
- `@@GLOBAL.sql_mode` is the default value used when initializing new sessions; changing it does not alter existing sessions automatically.
- Stored programs save the `sql_mode` of the session executing the `CREATE` statement at object creation time.

Do not assume global mode and session mode are always identical. Connection pools may hold older connections, applications may set custom session modes, and migration tools may open a separate connection from the application runtime connection.

### 1.1. Some common SQL modes

| SQL mode | Typical impact |
|---|---|
| `STRICT_TRANS_TABLES` | Strictly rejects invalid values when writing to transactional tables; error behavior depends on statement and storage engine |
| `STRICT_ALL_TABLES` | Applies strict behavior more broadly across storage engines |
| `ANSI_QUOTES` | Double quotes quote identifiers instead of string literals |
| `NO_BACKSLASH_ESCAPES` | Backslash is no longer treated as an escape character inside string literals |
| `PIPES_AS_CONCAT` | `||` is interpreted as string concatenation instead of the logical `OR` operator |
| `ONLY_FULL_GROUP_BY` | Restricts `SELECT`/`HAVING`/`ORDER BY` expressions not grouped or functionally dependent on `GROUP BY` columns per MySQL rules |
| `NO_ENGINE_SUBSTITUTION` | Prevents silently substituting another storage engine when the requested engine is unavailable |

SQL mode is a combined list. A session value can contain multiple comma-separated modes. Default mode sets vary across MySQL versions, so inspect and configure them explicitly instead of relying on machine defaults.

## 2. When SQL mode is saved

When executing `CREATE PROCEDURE` or `CREATE FUNCTION`, MySQL records the `@@SESSION.sql_mode` value of the connection executing the DDL into the routine's metadata.

The lifecycle can be pictured as follows:

1. A migration connection is opened.
2. The session SQL mode is set.
3. `CREATE PROCEDURE` or `CREATE FUNCTION` executes.
4. MySQL saves the SQL mode alongside the routine definition.
5. Another session calls the routine.
6. The routine runs with the SQL mode saved at creation time.
7. When the routine returns, the caller session resumes with its pre-call SQL mode.

For example, procedure A is created with `ANSI_QUOTES`; procedure B is created with an empty mode. When the same connection calls both, A and B each preserve their own saved mode.

SQL mode is saved per stored program. Changing mode for one routine does not change the mode of other routines in the same schema.

### 2.1. SQL mode at creation vs. SQL mode at call time

Suppose:

```sql
-- Connection creating the procedure
SET SESSION sql_mode = 'ANSI_QUOTES';

DELIMITER //
CREATE PROCEDURE p_created_with_ansi()
BEGIN
    SELECT "status" AS result;
END//
DELIMITER ;
```

Later, another connection may use a different mode:

```sql
SET SESSION sql_mode = '';

CALL p_created_with_ansi();
```

The procedure still runs under the mode saved at creation time. With `ANSI_QUOTES`, `"status"` is parsed as an identifier. If there is no column or object named `status` in the `SELECT` context, the statement may report an unknown column error; if such a column exists, it returns the column's value.

Never conclude that running `SET SESSION sql_mode = ''` in the caller will turn `"status"` inside the procedure into a string literal. Stored programs carry their own SQL mode.

## 3. SQL mode affects both parsing and execution

Some modes change how the parser interprets syntax. Others affect data validation and conversion when statements execute.

Examples:

- `ANSI_QUOTES` changes the meaning of double quotes in SQL statements.
- `NO_BACKSLASH_ESCAPES` changes how backslashes are processed in string literals.
- `PIPES_AS_CONCAT` changes the meaning of the `||` operator.
- `STRICT_TRANS_TABLES` affects how MySQL handles invalid values when writing data.
- `ONLY_FULL_GROUP_BY` affects acceptance of certain expressions in grouped queries.

Consequently, changing SQL mode after a routine has been created may not take effect as expected. A routine will keep using its old SQL interpretation until recreated under the new mode.

### 3.1. Example with ANSI_QUOTES

When `ANSI_QUOTES` is disabled:

```sql
SELECT "status" AS result;
```

`"status"` is interpreted as a string literal and the result is the string `status`.

When `ANSI_QUOTES` is enabled:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

SELECT "status" AS result
FROM orders;
```

In this example, the `status` column is explicitly referenced. With `ANSI_QUOTES`, `"status"` is also parsed as the `status` column name. This difference can cause a routine to return different results or raise errors after deploying to an environment with a different mode.

To keep code readable and less mode-dependent, use single quotes for string literals and quote identifiers consistently per project conventions.

```sql
SELECT status AS result
FROM orders
WHERE status = 'PAID';
```

Avoid casually using double quotes if an environment may enable `ANSI_QUOTES`.

## 4. Experiment: two procedures created with different SQL modes

This experiment demonstrates that the mode is captured at `CREATE` time, not re-read from the caller on each `CALL`.

Create a test table:

```sql
CREATE TABLE sql_mode_demo (
    id INT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO sql_mode_demo (id, status)
VALUES (1, 'PAID');
```

Use the MySQL command-line client. `DELIMITER` is a client directive to recognize the routine terminator; it is not an SQL statement sent directly to the server.

Create a procedure with `ANSI_QUOTES`:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

DELIMITER //
CREATE PROCEDURE p_identifier_mode()
BEGIN
    SELECT "status" AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;
```

Create another procedure with `ANSI_QUOTES` disabled:

```sql
SET SESSION sql_mode = '';

DELIMITER //
CREATE PROCEDURE p_literal_mode()
BEGIN
    SELECT "status" AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;
```

Now set the caller session to `ANSI_QUOTES` and call both:

```sql
SET SESSION sql_mode = 'ANSI_QUOTES';

CALL p_identifier_mode();
CALL p_literal_mode();

SELECT @@SESSION.sql_mode;
```

Expected results:

| Procedure | SQL mode at creation | Meaning of `"status"` in routine | Result |
|---|---|---|---|
| `p_identifier_mode` | `ANSI_QUOTES` | Identifier/column `status` | `PAID` |
| `p_literal_mode` | Empty mode | String literal | `status` |

Even though the caller has `ANSI_QUOTES` enabled, `p_literal_mode` still executes under the mode saved at creation time. After each `CALL`, the caller session resumes with its own mode; the final `SELECT` still shows `ANSI_QUOTES`.

When using JDBC or a migration framework instead of the `mysql` client, do not send `DELIMITER` as SQL. Send the full `CREATE PROCEDURE ... BEGIN ... END` as a single statement per driver support.

## 5. Example with strict mode and data conversion

Strict mode can cause one routine to reject invalid values that another routine created in non-strict mode might convert and emit a warning for.

Create a lab table:

```sql
CREATE TABLE sql_mode_insert_demo (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = InnoDB;
```

Create a procedure in strict mode:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

DELIMITER //
CREATE PROCEDURE p_insert_strict()
BEGIN
    INSERT INTO sql_mode_insert_demo (amount)
    VALUES ('not-a-number');
END//
DELIMITER ;
```

Create a procedure with strict mode off:

```sql
SET SESSION sql_mode = 'NO_ENGINE_SUBSTITUTION';

DELIMITER //
CREATE PROCEDURE p_insert_non_strict()
BEGIN
    INSERT INTO sql_mode_insert_demo (amount)
    VALUES ('not-a-number');
END//
DELIMITER ;
```

Call both procedures in a session with strict mode:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

CALL p_insert_strict();
CALL p_insert_non_strict();

SELECT *
FROM sql_mode_insert_demo;
```

With InnoDB, the procedure created under strict mode is expected to raise a data conversion error on the `INSERT`. The procedure created under non-strict mode may convert the invalid string to a default numeric value such as `0` and emit a warning. Check errors/warnings on your exact server version and configuration.

This experiment highlights an operational risk: a routine created in a permissive environment can continue accepting bad data under that behavior after the application moves to a strict environment. Setting strict mode on the migration connection before creating routines is part of schema quality control.

## 6. Session mode vs. global mode during deployment

`SET GLOBAL sql_mode` changes the default for sessions created afterward. It does not change the current connection's mode, nor does it alter the SQL mode saved in existing stored programs.

Example:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;

SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

After `SET GLOBAL`, the two values can differ because the current session retains its previous mode. A new connection normally initializes its session mode from the global mode at connect time, unless the client or connection configuration sets a different value.

To create routines with a chosen mode, set the session mode on the exact connection running `CREATE`:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;

CREATE PROCEDURE ...;
```

Do not just run `SET GLOBAL` and assume the migration connection has picked up the new value.

### 6.1. Connection pools and migration connections

Connection pools often reuse long-lived connections. If a connection was opened before global mode changed, its session may still hold the old mode. A migration tool may also open connections with its own settings.

Reliable procedure:

1. Use a dedicated connection for migrations.
2. Read `@@SESSION.sql_mode` before running DDL.
3. Set the desired mode via `SET SESSION`.
4. Read the value back to confirm.
5. Create the routines on that same connection.
6. Verify the saved SQL mode in metadata.
7. After migration completes, close the connection or restore session mode if reusing the connection.

Never infer a migration connection's mode from an application connection's mode.

## 7. Inspecting a stored program's saved SQL mode

### 7.1. SHOW CREATE PROCEDURE

Command:

```sql
SHOW CREATE PROCEDURE p_identifier_mode;
```

The output includes the `sql_mode` column alongside `Create Procedure`, `character_set_client`, `collation_connection`, and related metadata. The `sql_mode` field shows the mode saved when the routine was created.

For functions:

```sql
SHOW CREATE FUNCTION calculate_total;
```

This is the direct way to inspect a specific routine.

### 7.2. INFORMATION_SCHEMA.ROUTINES

You can inspect routines in the current schema:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    SQL_MODE,
    DEFINER,
    SECURITY_TYPE,
    CREATED,
    LAST_ALTERED
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

The `SQL_MODE` column is routine metadata. Its value may be a comma-separated list of modes or an empty string if the routine was created when the session had no modes enabled.

Metadata visibility depends on the account's privileges. If an object does not appear, check the schema and grants before concluding the routine does not exist.

### 7.3. Never edit system tables directly

In MySQL 8.0, stored program metadata is managed by the data dictionary. Never directly edit internal system tables to change SQL mode. Use supported DDL and verify metadata via `SHOW CREATE` or `INFORMATION_SCHEMA`.

## 8. Can ALTER PROCEDURE change a routine's SQL mode?

There is no `SQL_MODE` clause in `ALTER PROCEDURE` syntax to change the saved mode. `ALTER PROCEDURE` modifies certain characteristics like comments or `SQL SECURITY`; it does not alter the routine body and does not reset the saved SQL mode.

To change SQL mode, recreate the routine under the new session mode:

1. Capture the current definition using `SHOW CREATE PROCEDURE`.
2. Record grants and related dependencies.
3. Prepare the `CREATE` script with the desired definition.
4. Set `@@SESSION.sql_mode` before `CREATE`.
5. Execute a controlled migration.
6. Verify `SHOW CREATE PROCEDURE` and `INFORMATION_SCHEMA.ROUTINES`.
7. Test with a caller holding real privileges.

Example deployment skeleton:

```sql
-- Run on a migration connection with appropriate privileges.
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

-- Use a reviewed full definition to recreate the routine.
-- DROP/CREATE can disrupt callers during migration.
DROP PROCEDURE IF EXISTS p_identifier_mode;

DELIMITER //
CREATE PROCEDURE p_identifier_mode()
BEGIN
    SELECT status AS result
    FROM sql_mode_demo
    WHERE id = 1;
END//
DELIMITER ;

SHOW CREATE PROCEDURE p_identifier_mode;
```

This is an illustrative skeleton. In production, do not run `DROP` before preparing a valid `CREATE` script and rollback plan. Dropping/recreating can affect granted `EXECUTE` privileges and calling applications; inspect and re-grant required privileges after migration.

If you only need to change a comment or another characteristic supported by `ALTER PROCEDURE`, use `ALTER PROCEDURE`. If the goal is changing the saved SQL mode, recreate the object.

## 9. Stored functions, triggers, and events

The SQL mode storage mechanism applies beyond procedures:

- Stored procedures and stored functions save SQL mode when created.
- Triggers save SQL mode at `CREATE TRIGGER` time.
- Events save SQL mode at `CREATE EVENT` time and use that mode when the Event Scheduler executes the event.

Because each object carries its own metadata, do not inspect only procedures while ignoring triggers or events involved in the same data flow.

### 9.1. Inspecting triggers

```sql
SHOW CREATE TRIGGER orders_before_insert;
```

Or:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    SQL_MODE,
    DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY TRIGGER_NAME;
```

If a trigger's SQL mode must change, recreate the trigger in a session set to the desired mode. Re-check metadata after DDL.

### 9.2. Inspecting events

```sql
SHOW CREATE EVENT purge_old_orders;
```

Or:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    STATUS,
    SQL_MODE,
    DEFINER,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
```

Events are executed by the Event Scheduler, not directly by a user session calling a procedure. Thus, you cannot infer an event's mode from the application's `@@SESSION.sql_mode`.

### 9.3. Routines calling other routines

When a stored program calls another routine, each routine keeps its own saved SQL mode. Check the mode of every routine in the call chain, especially when an older procedure calls a newer function or vice versa. Never assume the outer routine's mode becomes the creation mode of inner routines.

Triggers fired by DML inside a routine also have their own SQL mode saved when the trigger was created. This matters when a single `INSERT` flows through a procedure and trigger with different modes.

## 10. SQL mode differs from SQL SECURITY and routine characteristics

Do not confuse `sql_mode` with other stored program attributes.

| Attribute | Role |
|---|---|
| `SQL_MODE` | SQL mode saved at creation time and used during stored program execution |
| `SQL SECURITY DEFINER/INVOKER` | Security context used to check object access privileges |
| `DETERMINISTIC / NOT DETERMINISTIC` | Declares whether the routine returns identical results for identical inputs per routine semantics |
| `CONTAINS SQL`, `READS SQL DATA`, `MODIFIES SQL DATA`, `NO SQL` | Declares routine data-access characteristics |
| `COMMENT` | Routine description |

For instance, a routine can be `SQL SECURITY INVOKER` while still storing `STRICT_TRANS_TABLES` as its SQL mode. The two settings address independent concerns: one governs privileges, the other governs how SQL is processed.

## 11. Standardizing SQL mode across environments

If dev, staging, and production use different SQL modes, the same `CREATE` script can produce routines with different metadata, making runtime behavior unpredictable.

A standardized workflow should:

- Lock down the exact SQL mode list required by the application.
- Set the mode explicitly in migrations before routine DDL.
- Never rely on MySQL version defaults or machine configuration.
- Log `SELECT @@SESSION.sql_mode` in migration output.
- Verify `SQL_MODE` after `CREATE` via `SHOW CREATE` or `INFORMATION_SCHEMA`.
- Include metadata checks in deployment verification steps.
- When changing modes, recreate routines through a controlled process.
- Synchronize related procedures, functions, triggers, and events.
- Test on the target MySQL version since supported modes can change across versions.

Example pre-migration check:

```sql
SELECT
    VERSION() AS mysql_version,
    @@SESSION.sql_mode AS migration_session_sql_mode,
    @@GLOBAL.sql_mode AS server_default_sql_mode;
```

After creating the routine, verify:

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_NAME = 'p_identifier_mode';
```

Do not stop at confirming `CREATE PROCEDURE` succeeded. Verify that the saved mode matches expectations.

## 12. Common mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Thinking a routine uses the caller's current SQL mode | Behavior differs from the saved mode | Check the routine's `SQL_MODE` |
| Only running `SET GLOBAL` before migration | The current connection may retain its old session mode | Run `SET SESSION` on the migration connection itself |
| Changing SQL mode after `CREATE` expecting routines to update | Existing routines keep using the old mode | Recreate routines with the new mode |
| Relying on each environment's default SQL mode | Dev/staging/prod can produce divergent routines | Explicitly set mode inside migrations |
| Checking only procedures while ignoring triggers/events | DML flows still hit objects running under different modes | Check metadata of all related stored programs |
| Confusing `SQL SECURITY` with `SQL_MODE` | Privilege and syntax settings get mixed up | Manage the two attributes independently |
| Using double quotes for string literals | Can be parsed as identifiers when `ANSI_QUOTES` is on | Use single quotes for strings |
| Dropping/recreating without tracking grants | Application accounts may lose `EXECUTE` | Record and re-grant privileges after migration |
| Believing `ALTER PROCEDURE` changes `SQL_MODE` | Metadata does not change as expected | Recreate the routine |
| Skipping MySQL version checks | Some modes may behave differently or be removed | Check `VERSION()` and version-specific docs |

## 13. Stored program deployment checklist

**Before CREATE:**

- Identify target MySQL version and the application's standard SQL mode.
- Use a dedicated migration connection.
- Read `@@SESSION.sql_mode`.
- Run `SET SESSION sql_mode` to the desired configuration.
- Re-check session value before DDL.
- Identify modes affecting quoting, expressions, grouping, and data conversion in the routine.

**After CREATE:**

- Run `SHOW CREATE PROCEDURE` or `SHOW CREATE FUNCTION`.
- Check `INFORMATION_SCHEMA.ROUTINES.SQL_MODE`.
- For triggers/events, run `SHOW CREATE` and inspect corresponding metadata.
- Test calling the routine from a session with a different SQL mode to confirm saved behavior.
- Check errors and warnings during data writes.
- Verify `EXECUTE` privileges and security context separately.

**When changing SQL mode:**

- Prepare the new routine definition.
- Record grants and dependencies.
- Recreate the routine under the new session mode.
- Re-verify metadata and runtime behavior.
- Re-grant privileges if affected.
- Synchronize related triggers/events/functions.
- Prepare a rollback plan in case migration fails.

## 14. Key takeaways

- MySQL saves the connection's `@@SESSION.sql_mode` at the moment a stored program is created.
- Procedures/functions run under their saved SQL mode, not simply the caller's current mode.
- After the routine finishes, the calling session's SQL mode is restored.
- `SET GLOBAL sql_mode` does not alter the current session or update the saved SQL mode of existing routines.
- `ANSI_QUOTES`, `NO_BACKSLASH_ESCAPES`, and `PIPES_AS_CONCAT` can change how SQL is parsed; strict mode affects data handling.
- Two routines created with different modes can behave differently even when called from the same session.
- `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION`, and `INFORMATION_SCHEMA.ROUTINES` reveal the saved mode.
- Triggers and events also capture their own SQL mode at creation time.
- `ALTER PROCEDURE` has no clause to change the saved SQL mode; the routine must be recreated.
- Controlling the migration connection's SQL mode keeps behavior consistent across dev, staging, and production.
- `SQL_MODE` is independent of `SQL SECURITY`, `DETERMINISTIC`, and other routine characteristics.
- Never directly edit system tables to alter stored program metadata.

SQL mode is part of a stored program's operational definition. Set it on the exact session before running `CREATE`, verify metadata afterward, and treat changing modes as a tested migration rather than a retroactive configuration tweak.

## References

- MySQL 8.0 Reference Manual — SQL Modes: https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html
- MySQL 8.0 Reference Manual — Stored Program Restrictions: https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html
- MySQL 8.0 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION Statements: https://dev.mysql.com/doc/refman/8.0/en/create-procedure.html
- MySQL 8.0 Reference Manual — SHOW CREATE PROCEDURE Statement: https://dev.mysql.com/doc/refman/8.0/en/show-create-procedure.html
- MySQL 8.0 Reference Manual — The ROUTINES Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-routines-table.html
- MySQL 8.0 Reference Manual — The TRIGGERS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-triggers-table.html
- MySQL 8.0 Reference Manual — The EVENTS Table: https://dev.mysql.com/doc/refman/8.0/en/information-schema-events-table.html
