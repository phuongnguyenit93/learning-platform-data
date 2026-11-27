# User Variables, System Variables, and Session-Scoped Parameters

When working with MySQL, a connection can maintain state throughout its lifetime: temporary user-assigned values, SQL mode, time zone, transaction isolation level, connection character set, and many other settings. Understanding the scope of each variable type helps you write predictable scripts, tune the behavior of a session, and avoid letting state from a prior run affect subsequent requests.

MySQL has two common SQL-level variable groups: **user-defined variables** (names starting with `@`) and **system variables** (typically read via `@@`). System variables can have server-wide scope (`GLOBAL`), current-connection scope (`SESSION`), or both. In addition, there are prepared statement parameters, local variables in stored programs, and routine parameters; these follow their own rules and should not be conflated with the two groups above.

This lesson focuses on reading, assigning, modifying, and managing state within the scope of a MySQL session.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish user-defined variables `@name` from system variables `@@GLOBAL.name` and `@@SESSION.name`.
- Initialize, assign, and read user-defined variables within a connection; understand their lifecycle and limitations.
- Read system variable values with `SELECT` and `SHOW`, and identify which variables support session scope.
- Modify parameters such as `time_zone`, `sql_mode`, `autocommit`, and transaction isolation for the current connection.
- Distinguish session changes from global changes and configuration that persists across server restarts.
- Manage connection state safely, especially when applications use connection pools or prepared statements.

## 1. What Is a MySQL Session?

Every time a client successfully connects to MySQL, the server creates a session for that connection. The session holds dedicated working state, such as:

- User-defined variables created by SQL statements, such as `@current_customer_id`.
- Session values of system variables, such as `@@SESSION.time_zone` or `@@SESSION.sql_mode`.
- Any open transaction, the isolation level applied to the next transaction, and `autocommit` state.
- Connection-bound objects such as temporary tables, server-side prepared statements, and session-level locks.

If two terminal windows open two separate connections, each window has its own session. Changing a user variable or session parameter in window A does not automatically appear in window B. When a connection closes, the state bound to that session is released.

```text
Client A                         MySQL Server                         Client B
session A                                                            session B
  @step = 1  ----------------->  holds @step in A
  time_zone = '+00:00' ------->  holds time_zone of A

                                                               @step is unassigned
                                                               time_zone uses B's default
```

Key point: **a session is scoped to a single connection**, not necessarily to a logged-in user or an application window. One application can open multiple connections, each with different state.

## 2. User-Defined Variables (`@variable`)

User-defined variables are temporary variables created by a client in the current session. Variable names begin with `@`, such as `@quantity`, `@subtotal`, or `@current_order_id`. You do not need to declare a data type beforehand.

### 2.1. Initializing and Reading Variables

You can assign variables with `SET`:

```sql
SET @unit_price = 125000.00;
SET @quantity = 3;
SET @discount_rate = 0.10;

SELECT
    @unit_price AS unit_price,
    @quantity AS quantity,
    @unit_price * @quantity AS subtotal,
    @unit_price * @quantity * (1 - @discount_rate) AS amount_after_discount;
```

`SET` can assign multiple variables in a single statement:

```sql
SET @min_price = 100000.00,
    @max_price = 500000.00,
    @category_code = 'ACCESSORY';

SELECT @min_price, @max_price, @category_code;
```

An unassigned variable evaluates to `NULL` in the session. Consequently, arithmetic on an uninitialized variable typically yields `NULL`:

```sql
SELECT @counter AS counter_before_initialization;
SELECT @counter + 1 AS result_before_initialization;

SET @counter = 0;
SET @counter = @counter + 1;

SELECT @counter AS counter_after_initialization;
```

The final result is `1`. Always initialize variables before using them in calculations or conditions.

### 2.2. Assigning Values from a Query

You can store the result of a query into a variable using `SELECT ... INTO`:

```sql
SELECT COUNT(*)
INTO @table_count
FROM information_schema.tables
WHERE table_schema = DATABASE();

SELECT @table_count AS table_count_in_current_database;
```

The query above counts tables in the currently selected database. `DATABASE()` returns `NULL` if the session has not selected a database via `USE` or connection configuration.

`SELECT ... INTO @variable` must return at most one row. If zero rows are returned, MySQL emits a warning and the variable retains its prior value; if more than one row is returned, the statement raises an error. Use aggregate functions such as `COUNT(*)` or unique-key predicates when you need to guarantee a single row.

### 2.3. Data Types and Conversion

User-defined variables can hold numeric, string, binary, or `NULL` values. The value's type depends on the assigned expression; MySQL may convert types when the variable is used in subsequent expressions. Do not rely on implicit conversion when calculations demand exact precision or specific formatting.

```sql
SET @price = CAST('125000.50' AS DECIMAL(12,2));
SET @quantity = CAST('2' AS UNSIGNED);

SELECT
    @price AS price,
    @quantity AS quantity,
    CAST(@price * @quantity AS DECIMAL(14,2)) AS line_total;
```

User-defined variable names are case-insensitive. Use meaningful names consistently and avoid collisions with other variables in scripts for easier reading and maintenance.

### 2.4. Scope and Lifecycle

A user-defined variable exists only in the session that created it. For instance, running `SET @run_id = 42` in connection A does not allow connection B to read `42`. When connection A closes, the variable and its value disappear.

User-defined variables are not durable storage. They are not written to tables, not shared across connections, and not a mechanism for passing data between servers. Nor are they transactional: `ROLLBACK` does not undo `@variable` assignments.

Example:

```sql
SET @marker = 'created-before-rollback';

START TRANSACTION;
SET @marker = 'changed-inside-transaction';
ROLLBACK;

SELECT @marker AS marker_after_rollback;
```

The result remains `changed-inside-transaction`, because session variable assignment is not part of InnoDB data transactions.

### 2.5. Notes When Using Variables in Queries

You can read user-defined variables in expressions, conditions, or calculations:

```sql
SET @minimum_total = 250000.00;

SELECT @minimum_total AS configured_threshold;
```

However, user-defined variables cannot substitute for table names, column names, or SQL identifiers. For example, `SELECT * FROM @table_name` is not valid syntax for dynamically choosing a table from a variable. To build dynamic SQL, use prepared statements and strictly validate identifiers joined into the statement.

Avoid reading and assigning the same variable within a single `SELECT` expression while relying on evaluation order. Evaluation order for expressions referencing and updating the same variable is not guaranteed. Legacy syntax such as `SELECT @n := @n + 1` outside `SET` is also deprecated in modern MySQL 8.0 releases. Split such logic into explicit statements:

```sql
SET @n = 0;
SET @n = @n + 1;
SELECT @n;
```

## 3. System Variables (`@@GLOBAL` and `@@SESSION`)

System variables are settings provided by MySQL to control server or session behavior—for example, maximum connections, SQL mode, time zone, connection character set, `autocommit`, and transaction isolation level.

### 3.1. Reading System Variables

Use the `@@` prefix to read system variables. Specify the scope explicitly to avoid ambiguity:

```sql
SELECT
    @@GLOBAL.max_connections AS server_connection_limit,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit,
    @@SESSION.transaction_isolation AS session_transaction_isolation;
```

`@@GLOBAL.name` reads the server-wide value. `@@SESSION.name` reads the value for the current connection. `@@LOCAL.name` is a synonym for `@@SESSION.name`.

With the shorthand `@@variable_name` without scope, MySQL returns the session value if the variable supports session scope; if the variable is global-only, it returns the global value. In operational documentation and maintainable scripts, write `@@GLOBAL` or `@@SESSION` explicitly.

You can also use `SHOW VARIABLES`:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW SESSION VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'time_zone';
```

If you omit `GLOBAL` or `SESSION` in `SHOW VARIABLES`, MySQL defaults to displaying session values. To inspect a server-wide setting, explicitly request `SHOW GLOBAL VARIABLES`.

### 3.2. Scope of System Variables

Not every system variable supports both scopes. Some variables are global-only, some are session-only, and some support both.

| Scope | Meaning | Example |
|---|---|---|
| `GLOBAL` | A server-level value affecting overall behavior or defaults for new connections | `max_connections` |
| `SESSION` | Value dedicated to the current connection; some variables exist only in this scope and may be read-only | `in_transaction` (current transaction state) |
| `GLOBAL` and `SESSION` | Has both a server-wide value and a per-connection value | `sql_mode`, `time_zone`, `autocommit` |

When a new connection opens, variables supporting both global and session scope typically initialize their session value from the global value at connect time. Thereafter, session changes affect only that connection. If a variable does not support session scope and you attempt to read `@@SESSION.variable_name`, MySQL raises an error. Check documentation for each variable rather than assuming every variable supports both scopes.

### 3.3. Distinguishing User Variables from System Variables

| Criterion | User Variable | System Variable |
|---|---|---|
| Syntax | `@my_value` | `@@SESSION.sql_mode`, `@@GLOBAL.max_connections` |
| Defined by | The SQL author | Provided by MySQL |
| Purpose | Hold temporary values within a session | Configure server or session behavior |
| Data type | Undeclared; inferred from assigned expression | Type and allowed domain defined by MySQL |
| Assignment | `SET @my_value = ...` | `SET SESSION ...` or `SET GLOBAL ...` if supported |
| Scope | Current session | Global, session, or both depending on the variable |

The two syntaxes look similar, but are not interchangeable:

```sql
SET @time_zone_note = 'Time zone used in test';
SET SESSION time_zone = '+00:00';

SELECT
    @time_zone_note AS user_variable,
    @@SESSION.time_zone AS system_variable;
```

`@time_zone_note` is merely a temporary value stored by the script; it does not change the time zone. `@@SESSION.time_zone` is the actual setting MySQL uses for the session.

## 4. Changing Session-Scoped Parameters

To modify a system variable for the current connection, use `SET SESSION` or `SET @@SESSION.variable_name`:

```sql
SET SESSION time_zone = '+00:00';
-- Equivalent:
SET @@SESSION.time_zone = '+00:00';

SELECT @@SESSION.time_zone;
```

This setting applies only to the current connection. Once the connection closes, session changes are not retained for new connections.

### 4.1. Changing Session Time Zone

Session time zone affects functions returning the current time and how MySQL converts `TIMESTAMP` values during reads and writes. Example:

```sql
SET SESSION time_zone = '+00:00';

SELECT
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    CURRENT_TIMESTAMP() AS session_current_timestamp,
    UTC_TIMESTAMP() AS utc_now;
```

`NOW()` and `CURRENT_TIMESTAMP()` use the session time zone. `UTC_TIMESTAMP()` returns UTC time. `DATETIME` stores and returns literal date/time components without converting by session time zone; `TIMESTAMP` is converted between the session time zone and UTC on write/read. Therefore, applications should standardize time zone conventions at both the connection and business layers.

### 4.2. Changing SQL Mode for the Session

`sql_mode` controls how MySQL handles specific syntax and data validation, such as strict mode or requiring full `GROUP BY` columns. You can inspect it before changing:

```sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
```

Setting `sql_mode` at the session level replaces the session's entire current mode list:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

The list above is illustrative only. In real applications, do not copy this exact list blindly, as you might drop modes required by your environment. Read the current value, agree on the desired mode list, and verify after making the change.

### 4.3. Changing Query Safety Parameters

`sql_safe_updates` helps reduce the risk of accidentally running `UPDATE` or `DELETE` on too many rows without key-based conditions or an appropriate limit:

```sql
SET SESSION sql_safe_updates = 1;
SELECT @@SESSION.sql_safe_updates;
```

This is a convenience safety guard for interactive sessions, not an authorization mechanism or security boundary. It does not replace transactions, backups, least privilege, or reviewing statements before execution.

### 4.4. Setting Transaction Isolation Level

You can set the default isolation level for subsequent transactions in the session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT @@SESSION.transaction_isolation;
```

Common levels are `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. MySQL InnoDB defaults to `REPEATABLE READ` in typical configurations. Changing isolation levels changes how transactions see data and how locks are acquired; evaluate it against your application's consistency requirements and concurrency load.

If you want to apply an isolation level only to the very next transaction, use `SET TRANSACTION ISOLATION LEVEL ...` without the `SESSION` keyword. Using `SET SESSION TRANSACTION ...` makes it the default for subsequent transactions in that session.

### 4.5. Setting Connection Character Set

`SET NAMES` sets the client, connection, and results character sets for the session, and optionally selects the corresponding connection collation:

```sql
SET NAMES utf8mb4;
-- Or specify collation explicitly:
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
```

In applications, configure the character set in the driver or connection string so every connection initializes properly. Do not rely on manually running `SET NAMES` in one terminal window when an application opens its own connections.

## 5. Changing Global Variables and Impact on Existing Sessions

Global variables apply at the server level. If a variable supports dynamic updates, a sufficiently privileged account can use `SET GLOBAL`:

```sql
SET GLOBAL max_connections = 300;
SELECT @@GLOBAL.max_connections;
```

`max_connections` is a server-level connection limit. The example requires appropriate administrative privileges—typically the dynamic `SYSTEM_VARIABLES_ADMIN` privilege in MySQL 8.0; older versions may use `SUPER`. Exact privilege names and rules depend on version.

A global change does not automatically overwrite session values already initialized on active connections. For dual-scope variables, new connections inherit the current global value as their initial value; existing sessions retain their own session values until they explicitly change them or disconnect.

```text
Time T1: GLOBAL time_zone = SYSTEM
  Connection A opens -> SESSION A gets SYSTEM
  Connection B opens -> SESSION B gets SYSTEM

Time T2: GLOBAL time_zone changes to +00:00
  Connection A still keeps SESSION A = SYSTEM
  Connection B still keeps SESSION B = SYSTEM
  Connection C opens -> SESSION C gets +00:00
```

This is why a global change does not force all existing sessions to adopt the new setting immediately.

`SET GLOBAL` changes the running value in server memory. Normally, that change does not survive a MySQL restart. For persistent configuration, update the configuration file or use a persistence mechanism supported by your version and operational policy.

Since MySQL 8.0.11, `SET PERSIST` can change a running global value and write it to a persisted config file so it applies after the next restart:

```sql
-- Illustrative example; execute only with operational approval
SET PERSIST max_connections = 300;
```

`SET PERSIST_ONLY` writes the persisted value without altering the current runtime value, useful for variables that can only be configured at startup. `SET PERSIST` and `SET PERSIST_ONLY` require appropriate administrative privileges and must follow change-management procedures. Never use them to test ordinary session parameters.

Not every variable can be changed dynamically or persisted with `SET PERSIST`. Some variables are read-only or startup-only; in those cases, update the configuration file and schedule a restart according to operational procedures.

## 6. Privileges and Limits When Modifying Variables

Reading variables and modifying variables are distinct capabilities. Many common session variables can be changed by users in their own sessions, though certain variables are restricted and require additional privileges. Modifying global variables requires administrative privileges. Persisted operations require privileges to modify persisted configuration.

Before making changes:

1. Read the current value in the right scope (`GLOBAL` or `SESSION`).
2. Confirm the variable supports that scope and is dynamically modifiable in your MySQL version.
3. Check account privileges and blast radius.
4. Record the original value if you need to restore the session after testing.
5. Make the smallest-scoped change possible, then re-read the variable to verify.

Example saving and restoring a session setting within the same connection:

```sql
SET @old_time_zone = @@SESSION.time_zone;

SET SESSION time_zone = '+00:00';
SELECT @@SESSION.time_zone;

-- Restore the value saved in the user variable
SET SESSION time_zone = @old_time_zone;
SELECT @@SESSION.time_zone;
```

This example only works within the same session. If the connection drops midway, `@old_time_zone` is lost as well; a new session initializes from the current global value.

## 7. User Variables, Local Variables, and Prepared Statement Parameters

The three mechanisms below are frequently confused because all can hold or pass values, yet their scope and purpose differ.

| Mechanism | Syntax | Scope | Purpose |
|---|---|---|---|
| User-defined variable | `@customer_id` | Connection session | Hold temporary values across SQL statements |
| Local variable in stored program | `DECLARE v_total DECIMAL(12,2)` | `BEGIN ... END` block or routine | Typed temporary variable inside a procedure/function |
| Prepared statement parameter | `?` | Single prepared statement execution | Bind input values into a prepared SQL statement |

Example prepared statement parameter on the application side:

```sql
SELECT customer_id, email
FROM customer
WHERE customer_id = ?;
```

The application sends the prepared statement and passes `customer_id` via the driver's parameter-binding API. Never concatenate user input into SQL strings to build filter predicates. Parameter marker `?` represents a data value, not a table name or column name.

In an SQL client, server-side prepared statements can use user variables to supply values to `EXECUTE ... USING`:

```sql
SET @customer_id = 101;
SET @sql_text =
    'SELECT customer_id, email FROM customer WHERE customer_id = ?';

PREPARE customer_lookup FROM @sql_text;
EXECUTE customer_lookup USING @customer_id;
DEALLOCATE PREPARE customer_lookup;
```

Here `@customer_id` is a session variable supplying the value for the placeholder. The placeholder still only represents a data value; if table or column names must vary, validate identifiers against an allowlist and construct the statement safely.

## 8. Connection Pools and Session State

In web applications or backend services, a connection pool keeps a set of open connections for reuse. Request 1 may borrow connection A, set `@request_id` or alter `time_zone`, and return the connection to the pool. Request 2 may later receive that exact same connection A.

If the pool does not reset session state, Request 2 may observe user variables or session settings left behind by Request 1. This causes hard-to-reproduce bugs because results depend on which physical connection the pool happened to hand out.

Measures to apply:

- Apply mandatory settings during connection initialization, such as character set and time zone per application conventions.
- Reset the session to a clean baseline before returning connections to the pool, or enable connection-reset mechanisms supported by the driver/pool.
- Never rely on `@name` variables to pass data between two independent requests.
- End transactions cleanly with `COMMIT` or `ROLLBACK` before returning the connection.
- Do not leave temporary tables, server-side prepared statements, or session-level locks alive beyond their required lifetime.
- Test the scenario where a single connection is reused across two requests requiring different settings.

A useful rule of thumb is to treat any connection borrowed from a pool as a session that might carry prior state. Each request must explicitly configure what it needs and clean up state it creates according to the pool's contract.

## 9. Hands-On Workflow: Observing and Modifying Sessions

You can perform the following exercise in a sandbox database. You do not need to create tables or modify data to observe session variables.

**Step 1: inspect initial state.**

```sql
SELECT
    CONNECTION_ID() AS connection_id,
    DATABASE() AS current_database,
    @@GLOBAL.max_connections AS global_max_connections,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone,
    @@SESSION.autocommit AS session_autocommit;
```

Record `connection_id` and the session values.

**Step 2: create user variables.**

```sql
SET @exercise_label = 'mysql-session-lab';
SET @expected_rows = 5;

SELECT @exercise_label, @expected_rows;
```

**Step 3: change time zone and verify.**

```sql
SET SESSION time_zone = '+00:00';

SELECT
    CONNECTION_ID() AS connection_id,
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

`connection_id` should remain unchanged on the same connection. The current session's `time_zone` should now be `+00:00`.

**Step 4: compare with a second connection.**

Open a second MySQL connection and run:

```sql
SELECT
    CONNECTION_ID() AS second_connection_id,
    @exercise_label AS user_variable_in_second_session,
    @@SESSION.time_zone AS second_session_time_zone;
```

The second connection has a different `connection_id`. `@exercise_label` evaluates to `NULL` because the variable was created in the first session. The second session's time zone initializes from the current global value and does not inherit the first connection's session change.

**Step 5: close the test connection.**

Close the first connection, reopen it, and check `@exercise_label`. The variable is gone because the old session ended. If using a connection pool, closing an application window does not necessarily close the physical connection immediately; rely on the pool's reset mechanism or actual lifecycle.

## 10. Common Mistakes

- Using `@variable` without initializing it, causing expressions to return `NULL`.
- Thinking `SET SESSION` changes server-wide configuration; it affects only the current connection.
- Reading `SHOW VARIABLES` and assuming it displays global values; by default it displays session values.
- Running `SET GLOBAL` and expecting already-running sessions to pick up the new value automatically.
- Assuming `SET GLOBAL` survives a server restart; ordinary runtime changes are not automatically persisted.
- Believing `ROLLBACK` undoes user-variable assignments; session variables are outside data transactions.
- Using user variables to substitute table/column names or concatenating user input into SQL, creating syntax errors or SQL injection risks.
- Letting a connection pool reuse sessions without resetting modified variables, open transactions, or altered settings.
- Assuming every system variable supports session scope and dynamic modification; scope, privileges, and mutability depend on each variable and MySQL version.

## 11. Checklist for Managing Variables and Session Parameters

- Identified whether the value to store is a script-created temporary variable or a MySQL-managed system variable.
- Used the exact syntax `@name`, `@@SESSION.name`, or `@@GLOBAL.name`.
- Initialized user variables before reading or computing with them.
- Verified values, types, and query outputs after assignment.
- Confirmed the system variable supports the intended scope and is dynamically modifiable.
- Read the existing value before changing it and know how to restore baseline settings after testing.
- Understood that session changes affect only the current connection; global changes follow separate rules for new vs. active connections.
- Checked required privileges before modifying global or persisted variables.
- Configured and reset session state per the connection pool's contract.
- Used driver parameter binding for application inputs rather than SQL string concatenation.

User variables hold temporary values within a connection; system variables govern MySQL behavior at global or session scope; and prepared statement parameters let applications pass data safely into prepared SQL. When you distinguish these three mechanisms accurately and manage connection lifecycles properly, you can tailor session behavior without accidentally leaking state across requests or altering configurations beyond your intended scope.
