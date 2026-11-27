# Verifying SQL Behavior When Changing Versions or Session Configuration

An SQL statement does not always produce the same result across every MySQL server. Its behavior can vary with the MySQL version, `sql_mode`, time zone, character set, collation, isolation level, `autocommit`, and session-bound configuration variables. Therefore, when upgrading servers, altering configuration, or moving an application onto a connection pool, actual behavior must be verified using a repeatable test suite.

In the `DATABASE_MYSQL` module, this relates directly to table design, data types, SQL querying, transactions, and operations. A configuration change can cause previously accepted data to be rejected, alter how strings are compared, change how data is grouped, or shift how timestamps are read. The goal of this lesson is to help you capture environment fingerprints, isolate individual variables, build test cases with expected outcomes, and deploy changes safely.

## 1. Why Can the Same SQL Statement Produce Different Results?

There are four main groups of factors:

1. **Server version:** MySQL may change supported syntax, default values, data validation rules, optimizer behavior, and function semantics across versions.
2. **Global configuration:** global variables set defaults for new sessions or govern server-wide behavior. Global changes generally do not automatically update already open sessions.
3. **Session configuration:** each connection can have its own `sql_mode`, `time_zone`, charset/collation, isolation level, and transaction state.
4. **Previously created objects:** stored procedures, functions, triggers, and events can retain the `sql_mode` from creation time; changing a client's session does not necessarily change how those objects execute.

For example, an `INSERT` writing a string longer than `VARCHAR` may be rejected in strict mode, yet truncated with a warning in non-strict mode. An aggregate query may run on a server without `ONLY_FULL_GROUP_BY` enabled yet be rejected on a server with that mode enabled. The exact same `TIMESTAMP` value may display differently when two connections use different `time_zone` settings.

## 2. Capturing the Environment Fingerprint Before Testing

Before comparing two servers or two configurations, record the version and key variables. Without a fingerprint, it is hard to tell whether a difference originates from the server or from the application session.

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    CONNECTION_ID() AS connection_id;

SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@GLOBAL.autocommit AS global_autocommit,
    @@SESSION.autocommit AS session_autocommit,
    @@character_set_client AS character_set_client,
    @@character_set_connection AS character_set_connection,
    @@collation_connection AS collation_connection;

SHOW VARIABLES LIKE 'transaction_isolation';
SHOW VARIABLES LIKE 'tx_isolation';
SHOW VARIABLES LIKE 'innodb_strict_mode';
```

`transaction_isolation` is the variable name used in MySQL 8.0; MySQL 5.7 releases typically use `tx_isolation`. Using `SHOW VARIABLES` helps check which name exists on the running version. `innodb_strict_mode` is an InnoDB-specific setting, not a component of `sql_mode`.

Save the fingerprint output alongside the application version, schema migration state, and test timestamp. When comparing dev, test, staging, and production, inspect both the server and sessions created by the driver or connection pool.

## 3. Distinguishing GLOBAL and SESSION

Many MySQL variables have two scopes:

- `GLOBAL`: server-level value. When changed, it generally serves as the default for connections opened afterward.
- `SESSION`: value of the current connection. Changes affect only the currently running session.

Check both scopes separately:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

Configure the current connection:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

Set the global default for new connections (requires appropriate administrative privileges):

```sql
SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

After `SET GLOBAL`, open a new connection to verify the new default was inherited. Existing running connections must be inspected separately; do not assume their `@@SESSION.sql_mode` updates automatically.

### Changing One Mode Without Accidentally Dropping Others

Assigning `SET SESSION sql_mode = '...'` directly replaces the session's entire mode list. If you only want to add or remove a single mode, you can use helpers in the `sys` schema if installed in the environment:

```sql
SET SESSION sql_mode = sys.list_add(@@SESSION.sql_mode, 'ANSI_QUOTES');
SET SESSION sql_mode = sys.list_drop(@@SESSION.sql_mode, 'ANSI_QUOTES');
```

If `sys.list_add()` or `sys.list_drop()` is unavailable, read the current list, construct the new list deliberately, and verify after assignment. Avoid ad-hoc string concatenation that can duplicate or accidentally drop modes.

## 4. Temporary vs. Persistent SQL Mode Changes

### Temporary Change Within a Session

This is the appropriate way to test behavior without affecting other connections:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;

-- Run test cases here.

SET SESSION sql_mode = @saved_sql_mode;
```

The `@saved_sql_mode` variable is a user variable on the current connection. If the client stops mid-way or the connection closes, the session ends; however, test scripts should always include a restore step so subsequent statements are not unexpectedly affected.

### Runtime Change at the Server Level

`SET GLOBAL` changes the global value in memory, but does not automatically write it to startup configuration. After a restart, the value may revert to the option file or another configuration source.

### Persisting Configuration Across Restarts

In MySQL 8.0.11 and later, `SET PERSIST` can alter a dynamic global variable and save the value to the persisted configuration file to survive restarts:

```sql
SET PERSIST sql_mode =
    'STRICT_TRANS_TABLES,ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION';
```

`SET PERSIST_ONLY` saves the value for the next startup without applying a runtime change; this command is useful for variables that can only be changed at startup. Not every variable supports the same scopes or modification methods. Check the documentation for the specific variable and version before using it.

In production environments, configuration should be managed via controlled deployment processes (configuration management, option files, or management platforms). Avoid having the same variable set differently across multiple sources without knowing which source takes precedence.

## 5. SQL Modes That Can Change Query Behavior

`sql_mode` is a list of modes affecting how MySQL parses SQL and validates data. Several key modes include:

| SQL mode | Behavior That Can Change | Risks to Check |
|---|---|---|
| `STRICT_TRANS_TABLES` | Rejects many invalid or truncated values for transactional tables; certain cases on non-transactional tables have different rules | Legacy data imports may start failing. |
| `STRICT_ALL_TABLES` | Applies strict validation to non-transactional tables as well per mode rules | Batch inserts may halt or leave partial writes in non-transactional engines. |
| `ONLY_FULL_GROUP_BY` | Validates non-aggregated columns in grouped queries | Previously running reporting queries may be rejected. |
| `ANSI_QUOTES` | `"` is interpreted as an identifier quote rather than a string literal | Dynamic SQL or statements using double quotes for strings may break. |
| `NO_BACKSLASH_ESCAPES` | Backslash is no longer an escape character inside string literals | Literals and application-generated SQL may change meaning. |
| `PIPES_AS_CONCAT` | `||` is interpreted as string concatenation instead of logical OR | Legacy expressions may return different results. |
| `NO_ENGINE_SUBSTITUTION` | Does not silently substitute the storage engine when the requested engine is unavailable | DDL may error instead of creating the table with another default engine. |
| `ALLOW_INVALID_DATES` | Relaxes certain day/month checks within the mode's permitted scope | Invalid date data can enter the system. |

Supported mode lists and deprecation statuses vary by version. Some older modes have been removed or no longer behave as before; never copy an `sql_mode` list verbatim from another version's guide without checking the target server.

### Strict Mode and Invalid Data

Strict mode helps catch bad data early rather than silently truncating or coercing values. However, `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES` are not completely identical when operating on non-transactional engines or multi-row batches. `INSERT IGNORE` and `UPDATE IGNORE` can also downgrade certain errors to warnings, so test actual statements rather than checking modes alone.

### `ONLY_FULL_GROUP_BY`

This mode requires columns in the `SELECT` list of an aggregate query to be aggregated, present in `GROUP BY`, or proven functionally dependent on the grouping columns according to MySQL rules. If an application relies on arbitrarily picking one value from a group, the result can be nondeterministic and will be rejected when the mode is enabled.

## 6. Verifying Strict Mode with Test Data

Create a table in a dedicated testing schema:

```sql
CREATE TABLE mode_probe (
    id INT NOT NULL PRIMARY KEY,
    label VARCHAR(4) NOT NULL
) ENGINE=InnoDB;
```

Save the current mode and then run the `INSERT` statement individually in strict mode. This statement is expected to error because `label` exceeds the column limit:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES';
```

Run the following statement separately; this is an expected error:

```sql
INSERT INTO mode_probe (id, label)
VALUES (1, 'ABCDE');
```

Immediately after the error, read the statement's warnings/errors:

```sql
SHOW WARNINGS;
```

After recording the strict-mode error, run the non-strict part in the same connection:

```sql
SET SESSION sql_mode = '';

INSERT INTO mode_probe (id, label)
VALUES (2, 'ABCDE');

SHOW WARNINGS;

SELECT id, label, CHAR_LENGTH(label) AS label_length
FROM mode_probe
ORDER BY id;

SET SESSION sql_mode = @saved_sql_mode;
```

In strict mode, values exceeding column length are typically rejected. In non-strict mode, MySQL may truncate the value to the allowed length and emit a warning. `SHOW WARNINGS` must be executed immediately after the statement being checked because the next SQL statement can overwrite the current warning list.

Do not run this example on business tables: the objective is to observe the difference between errors and warnings in a disposable test table.

## 7. Verifying `ONLY_FULL_GROUP_BY`

Create sample data:

```sql
CREATE TABLE sales_mode_probe (
    customer_id INT NOT NULL,
    region VARCHAR(30) NOT NULL,
    amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales_mode_probe (customer_id, region, amount)
VALUES
    (1, 'North', 100.00),
    (1, 'North', 150.00),
    (2, 'South', 200.00);
```

The query may be rejected when `ONLY_FULL_GROUP_BY` is enabled. Save the mode first, then run the `SELECT` statement separately to record the error:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = 'ONLY_FULL_GROUP_BY';

SELECT customer_id, region, SUM(amount)
FROM sales_mode_probe
GROUP BY customer_id;
```

After recording the expected error, restore the mode:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

`region` is neither in `GROUP BY` nor aggregated. If business logic wants to display the region, the data relationship must be clearly defined. If each customer has only one region, model it with appropriate keys and relationships; do not disable the mode to fetch an arbitrary value.

A more deterministic query:

```sql
SELECT customer_id, region, SUM(amount) AS total_amount
FROM sales_mode_probe
GROUP BY customer_id, region;
```

This query groups by both customer and region, so the result has clear semantics. When a representative row is needed based on specific criteria, use an appropriate aggregate function, subquery, or window function depending on version, rather than relying on an arbitrary value.

## 8. Verifying Modes That Affect Literal Syntax

### `ANSI_QUOTES`

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
SELECT "hello" AS result;

SET SESSION sql_mode = 'ANSI_QUOTES';
```

Run the following statement separately to observe the identifier error when there is no column named `hello`:

```sql
SELECT "hello" AS result;
```

After recording the result, restore the mode:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

In the first mode, double quotes can be used for string literals. When `ANSI_QUOTES` is enabled, double quotes are used to quote identifiers; if no column or identifier named `hello` exists, the second statement raises an error. Use single quotes for string literals and MySQL backticks when object names need quoting.

### `NO_BACKSLASH_ESCAPES`

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
SELECT HEX('a\nb') AS default_escaped_value;

SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES';
SELECT HEX('a\nb') AS literal_backslash_value;
SET SESSION sql_mode = @saved_sql_mode;
```

In default mode, `\n` in a literal is interpreted as a newline character; when `NO_BACKSLASH_ESCAPES` is enabled, the backslash and the letter `n` are preserved literally. Thus the two `HEX()` outputs differ. This is especially important for SQL built via string concatenation. Applications should use prepared statements instead of manually escaping data under assumptions about the mode.

When testing syntax modes, restore `sql_mode` after the test and re-run on the exact driver/server version used by the application.

## 9. Other Session Settings That Also Require Verification

Checking `sql_mode` alone is not enough. The variables below can cause the same SQL statement or the same data to be interpreted differently:

| Setting | Typical Scope | Affected Behavior |
|---|---|---|
| `time_zone` | Global and session | `TIMESTAMP` display/storage, time functions, and timezone conversions. |
| `character_set_client` | Session | Charset the server uses to interpret bytes sent by the client. |
| `character_set_connection` | Session | Intermediate charset for literals and string expressions. |
| `collation_connection` | Session | Comparison rules for connection-related string expressions. |
| `transaction_isolation` / `tx_isolation` | Global and session; name depends on version | Snapshots, locking, and visibility of concurrent changes. |
| `autocommit` | Global and session | Whether each statement auto-commits or remains in an open transaction. |
| `foreign_key_checks` | Global and session | Foreign key constraint enforcement during write operations. |
| `innodb_strict_mode` | Global and session | Checks on certain InnoDB configurations and operations. |
| `optimizer_switch` | Global and session | Certain optimizer choices and execution plans. |

Inspect session configuration before running tests:

```sql
SELECT
    @@SESSION.time_zone,
    @@SESSION.autocommit,
    @@SESSION.foreign_key_checks,
    @@SESSION.innodb_strict_mode,
    @@SESSION.optimizer_switch,
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.collation_connection;
```

For isolation level, you can use:

```sql
SHOW SESSION VARIABLES LIKE '%isolation%';
```

Then select the variable matching your version and verify its current value. Never assume a specific variable name or default value exists across every MySQL version.

## 10. Connection Pools Can Expose Session Configuration Bugs

In Java applications or backend services, a connection pool holds physical connections for reuse. Each connection has its own session state. If request A changes `sql_mode`, `time_zone`, `autocommit`, or isolation level and returns the connection to the pool without resetting, request B may receive a connection with non-default state.

Example of a request altering session state:

```sql
SET SESSION time_zone = '+07:00';
SET SESSION sql_mode = 'ANSI_QUOTES';
```

The next request could unexpectedly run under that session time zone or SQL mode if the pool does not restore state. Some pools/drivers reset certain states upon returning a connection, yet you should never assume every custom variable is reset.

Principles when using pools:

1. Establish standard baseline state when physical connections are created, such as UTC session time zone and standardized `sql_mode`.
2. Avoid modifying session variables in business code. If unavoidable, save and restore values before returning the connection.
3. Check the pool's reset configuration and verify with a borrow-return-borrow test.
4. Never share a single JDBC `Connection` concurrently across multiple requests or threads.
5. Set transaction isolation and autocommit via verified pool/driver configuration.
6. Log session fingerprints in diagnostic logs at an appropriate level; never log secrets.

A simple test is to borrow connection A, modify a session variable, return it to the pool, and then borrow a connection again. Check `CONNECTION_ID()` to see if the same physical session was reused, and re-read the variables. If the connection ID differs, the pool may have created a new connection; if identical, verify that state was reset according to policy.

## 11. Stored Programs Retain Creation-Time SQL Mode

MySQL stores the `sql_mode` in effect when creating a stored procedure, function, trigger, or event. When the object runs, the server uses the mode stored with that object instead of simply adopting the calling client's entire current `@@SESSION.sql_mode`.

This means changing `SET GLOBAL sql_mode` or the application's session mode alone is not guaranteed to change the behavior of existing stored programs. When upgrading or standardizing SQL modes, audit objects created under older modes.

You can inspect a procedure definition:

```sql
SHOW CREATE PROCEDURE learning_shop.create_order;
```

The output includes the `sql_mode` attached to the routine. For triggers, use:

```sql
SHOW CREATE TRIGGER learning_shop.orders_after_insert;
```

If an object needs to use the new mode, the standard procedure is to script out its definition, recreate the object in a session with the desired `sql_mode`, and test before deployment. Store DDL in migrations/version control so objects can be reproduced accurately.

## 12. Building a Repeatable Behavior Test Suite

A good test suite must verify both results and how the server responds. For each test case, record:

- MySQL version and distribution.
- Relevant global/session variables.
- Schema, engine, DDL, and input data.
- SQL statements and execution order.
- Returned results, affected row counts, and transaction status.
- SQLSTATE, error codes, and warnings if any.
- Final values stored in the database, not just the driver's response.

### Recommended Test Matrix

| Category | Variants to Compare | What to Confirm |
|---|---|---|
| Version | Current running version vs. upgrade target | Syntax, default modes, warnings/errors, and query results. |
| Strictness | Strict vs. non-strict | Whether bad data is rejected or converted/truncated with warnings. |
| Grouping | With and without `ONLY_FULL_GROUP_BY` | Whether aggregate queries are deterministic and compatible. |
| Literals | With/without `ANSI_QUOTES`, `NO_BACKSLASH_ESCAPES` | Whether static literals and dynamic SQL change meaning. |
| Time zone | UTC vs. business time zone | Whether `TIMESTAMP`, time functions, and date boundaries remain accurate. |
| Charset/collation | Old vs. new configuration | Whether comparisons, unique indexes, joins, and sorting change. |
| Transactions | Expected isolation levels and autocommit settings | Whether commit, rollback, snapshots, and locking meet requirements. |
| Connection pool | New vs. reused connections | Whether session state is initialized/reset properly. |
| Stored programs | Routines created under old vs. new mode | Whether the stored object mode alters behavior. |

### Test Case Template

```text
Test ID: SQLMODE-STRICT-001
Server: MySQL <version>
Session sql_mode: STRICT_TRANS_TABLES
Schema: isolated_test_schema
Table: mode_probe (InnoDB, label VARCHAR(4))
Input: 'ABCDE'
Expected: statement rejected; row count unchanged
Capture: SQLSTATE, error code, SHOW WARNINGS, SELECT after attempt
```

This template turns a vague observation like "strict mode causes an error" into an automated test case comparable across versions.

## 13. Verification Workflow When Upgrading MySQL or Changing Configuration

### Before the Change

1. Capture server and session fingerprints in the current environment.
2. Back up global settings, option files, and driver/pool configurations.
3. Save relevant DDL, migrations, stored routines, triggers, and events.
4. Gather critical queries, representative data, and current outputs.
5. Identify which variables will change and the global/session scope of each.

### In the Test Environment

1. Provision the target server version with the planned configuration.
2. Restore anonymized schemas and data or an equivalent fixture set.
3. Run the regression test suite using the exact driver and connection pool.
4. Compare results, warnings, SQLSTATE, row counts, transaction outcomes, and execution plans.
5. Verify stored programs recreated under the expected mode.
6. Test migration rollback or snapshot restoration if results fail.

### During Rollout

1. Put configuration into the official configuration management source and record before/after values.
2. Apply in the proper sequence: server configuration, restart if required, create new connections, update stored programs, and deploy the application.
3. Verify fingerprints on new connections and pool-reused connections.
4. Monitor SQL errors, warnings, rollback rates, deadlocks, latency, and data errors.
5. Maintain a rollback plan for configuration or data restoration if the change alters semantics incorrectly.

Do not change multiple variables at once without evidence that they must change together. When errors appear, isolate variables and reproduce on a test schema to identify the root cause.

## 14. Common Mistakes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Recording only the server version | Missing differing SQL modes or session states | Collect fingerprints for both the server and individual connections. |
| Thinking `SET GLOBAL` changes open sessions | Running applications keep using old configuration | Open new connections or set session state explicitly. |
| Assigning a new `sql_mode` without keeping old modes | Accidentally dropping strictness or other required modes | Diff the list and add/remove modes intentionally. |
| Relying on version defaults | Behavior shifts after an upgrade | Explicitly declare required configuration and test on the target version. |
| Ignoring warnings | Data may have been truncated or converted | Read `SHOW WARNINGS` immediately after statements and verify stored data. |
| Thinking changing client session updates legacy stored procedures | Routines keep running under creation-time `sql_mode` | Inspect `SHOW CREATE` and recreate routines via migration if needed. |
| Assuming pools always reset every session variable | Previous request state leaks into subsequent requests | Check pool configuration and test borrow/return cycles. |
| Testing only with valid data | Missing differences in strict mode, grouping, or charset | Include boundary values, malformed data, and duplicate cases. |
| Checking only application responses | Unsure whether the database performed partial writes | Verify row counts, warnings, transaction state, and final stored data. |

## 15. Practice Exercises

### Exercise A — Fingerprint Two Environments

1. Run the fingerprint query on two MySQL servers or two sessions with different configurations.
2. Compare version, `sql_mode`, time zone, charset/collation, autocommit, and isolation.
3. Document which variables differ and which SQL statements each variable affects.
4. Propose a standardized configuration for the application.

### Exercise B — Verify Strict Mode and Grouping

1. Create `mode_probe` and `sales_mode_probe` in an isolated schema.
2. Attempt to insert oversized values in strict and non-strict modes.
3. Record errors, warnings, and final stored data.
4. Run aggregate queries with `ONLY_FULL_GROUP_BY` enabled/disabled.
5. Rewrite queries for deterministic semantics so they run under strict enforcement.

### Exercise C — Verify Session State Through a Pool

1. Borrow a connection and record `CONNECTION_ID()` and `@@SESSION.sql_mode`.
2. Change `sql_mode` and `time_zone`, then return the connection to the pool.
3. Borrow a connection again and check its ID, mode, and time zone.
4. Determine whether the pool reset state.
5. Configure appropriate initialization/reset settings and re-run.

### Exercise D — Verify Stored Routines After Mode Changes

1. Create a procedure in a session with a specific `sql_mode`.
2. Change the client's session mode and call the procedure.
3. Use `SHOW CREATE PROCEDURE` to inspect the stored mode.
4. Recreate the procedure under the new mode and compare outputs.
5. Place the procedure definition into a migration for reproducibility.

### Exercise E — Version Upgrade Rehearsal

1. Select a current MySQL version and a target version in a test environment.
2. Capture fingerprints, DDL, routines, and fixtures on the current version.
3. Run the same test suite on the target version.
4. Compare SQLSTATE, warnings, post-write data, and query results.
5. Categorize discrepancies by version, SQL mode, session variable, or driver.
6. Write a rollout checklist and rollback plan.

You complete this lesson when you can reproduce a behavioral difference with a clear test case, identify global/session scope, explain mode impacts, verify session state through a pool, and build a regression test suite for MySQL upgrades.

## 16. Key Principles to Remember

- Always record the MySQL version along with server and session configuration fingerprints.
- Distinguish `GLOBAL` from `SESSION`; global changes do not automatically update open connections.
- `SET SESSION sql_mode` replaces the current mode list; add or remove modes in a controlled manner.
- Strict mode, `ONLY_FULL_GROUP_BY`, `ANSI_QUOTES`, and syntax modes can change results or raise errors on legacy SQL.
- Verify warnings, SQLSTATE, error codes, row counts, and final stored data alike.
- `time_zone`, charset/collation, isolation, and autocommit are also part of session state requiring verification.
- Connection pools must initialize and reset session state intentionally.
- Stored programs can retain creation-time `sql_mode`; audit and recreate them via migrations when necessary.
- Test on the exact target version, driver, and representative data before rolling out new configuration.

With a repeatable verification suite, MySQL version upgrades or configuration changes can be evaluated with concrete evidence. You will know which SQL statements change behavior, which sessions hold which values, and where to adjust schemas, queries, routines, or deployment procedures.
