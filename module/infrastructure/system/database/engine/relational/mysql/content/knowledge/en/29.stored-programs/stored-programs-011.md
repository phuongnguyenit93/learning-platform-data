# PREPARE, EXECUTE, DEALLOCATE PREPARE, and Permitted Scope of Dynamic SQL

MySQL allows constructing and executing an SQL statement from a string at runtime. This mechanism is commonly called **dynamic SQL**. With SQL-level prepared statements, the basic lifecycle consists of three statements:

1. `PREPARE` parses the SQL statement and registers a prepared statement in the current session.
2. `EXECUTE` runs the prepared statement, optionally passing values into `?` parameter markers.
3. `DEALLOCATE PREPARE` frees the statement when no longer needed.

Dynamic SQL is useful when statement structure genuinely changes at runtime, such as choosing a table name from an allowed set of tables or choosing sort order from predefined modes. For ordinary input data, use parameter markers instead of concatenating values into SQL strings. Parameter markers protect value positions; they cannot substitute for table names, column names, keywords, or SQL syntax.

In the `DATABASE_MYSQL` module, this lesson helps you understand the prepared statement lifecycle, session scope, restrictions inside stored programs, and how to build controlled dynamic SQL. Examples focus on stored procedures; SQL-level prepared statements cannot be used inside stored functions or triggers because statements have session scope and can outlive the routine.

## 1. Dynamic SQL and prepared statements

An ordinary SQL statement has a fixed structure when sent to the server:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
```

If an application wants to change the tenant or status values, there is no need to build a new SQL string by concatenating values. You can prepare a statement with parameter markers:

```sql
PREPARE stmt_orders FROM
    'SELECT order_id, status, total_amount
     FROM orders
     WHERE tenant_id = ? AND status = ?';

SET @tenant_id = 42;
SET @order_status = 'PAID';

EXECUTE stmt_orders USING @tenant_id, @order_status;
DEALLOCATE PREPARE stmt_orders;
```

The server parses the statement during `PREPARE`; `EXECUTE` supplies values matching the `?` placeholders. Once finished, `DEALLOCATE PREPARE` releases the statement.

### SQL-level prepared statements vs. driver prepared statements

There are two common ways to use prepared statements:

- **SQL-level:** send `PREPARE`, `EXECUTE`, and `DEALLOCATE PREPARE` directly via SQL.
- **Client API/protocol:** use driver APIs such as `prepare()` and `execute()`; the driver communicates with the server via the prepared-statement protocol.

Both approaches share similar goals, yet differ in interface and management scope. This lesson focuses on SQL-level prepared statements inside MySQL and stored procedures. When writing applications, prefer driver parameter binding over concatenating SQL strings yourself.

## 2. Syntax and lifecycle of the three statements

### PREPARE

Syntax:

```sql
PREPARE statement_name FROM preparable_statement;
```

`preparable_statement` is a string literal or user-defined variable holding a preparable SQL statement. Example:

```sql
SET @sql_text =
    'SELECT order_id FROM orders WHERE tenant_id = ?';

PREPARE stmt_find_orders FROM @sql_text;
```

At this step, MySQL parses the SQL statement and creates a prepared statement named `stmt_find_orders` in the current session. If syntax or statement type is unsupported, the error occurs immediately at `PREPARE`.

### EXECUTE

Syntax:

```sql
EXECUTE statement_name
USING @user_variable [, @user_variable] ...;
```

Example:

```sql
SET @tenant_id = 42;
EXECUTE stmt_find_orders USING @tenant_id;
```

The number of variables in `USING` must match the number of `?` parameter markers in the statement, in exact order of appearance. Each user variable's value is bound to its corresponding marker.

### DEALLOCATE PREPARE

Syntax:

```sql
DEALLOCATE PREPARE statement_name;
```

This statement frees the prepared statement in the session. `DROP PREPARE statement_name` is an alias supported by MySQL.

### Overall lifecycle

```text
SQL text (string literal or @user_variable)
                    |
                    v
             PREPARE stmt
                    |
       statement exists in session
                    |
                    v
        EXECUTE stmt USING @value...
                    |
        can EXECUTE multiple times
                    |
                    v
          DEALLOCATE PREPARE stmt
                    |
            statement released
```

Do not keep statements alive longer than needed. Un-deallocated prepared statements continue consuming resources and count toward the server's prepared statement limit.

## 3. Parameter marker `?` is for values

A parameter marker represents a **data value** wherever SQL syntax permits a value. Example:

```sql
SET @sql_text =
    'SELECT order_id, total_amount
     FROM orders
     WHERE tenant_id = ?
       AND status = ?
       AND created_at >= ?
       AND created_at < ?';

PREPARE stmt_orders_by_range FROM @sql_text;

SET @p_tenant = 42;
SET @p_status = 'PAID';
SET @p_from = '2026-01-01 00:00:00';
SET @p_until = '2026-02-01 00:00:00';

EXECUTE stmt_orders_by_range
USING @p_tenant, @p_status, @p_from, @p_until;

DEALLOCATE PREPARE stmt_orders_by_range;
```

`USING` order mapping:

| Parameter marker | User variable |
|---:|---|
| 1st `?` | `@p_tenant` |
| 2nd `?` | `@p_status` |
| 3rd `?` | `@p_from` |
| 4th `?` | `@p_until` |

Parameter markers separate data from SQL structure. Strings containing quotes, backslashes, or user-supplied text are not interpreted as SQL syntax.

### Parameter markers are not general SQL variables

`?` is valid only inside prepared statements and in valid value positions. It cannot replace arbitrary syntax fragments. The following does not mean "pick a table by passed-in value":

```sql
-- Invalid to bind a table name with a parameter marker
SELECT * FROM ?;
```

Similarly, `?` cannot supply a column name or `ASC`/`DESC` keyword:

```sql
-- Does not turn ? into a column name to sort by
SELECT order_id, total_amount
FROM orders
ORDER BY ?;
```

In `ORDER BY ?`, the marker represents an expression value; it is not re-parsed as an identifier. If identifiers or sort directions must vary, select from an allowlist and assemble the controlled syntax fragment into the SQL text.

### Common value positions where markers work

In supported statements, markers can represent:

- Values in `WHERE` or `HAVING` expressions.
- Values in `INSERT ... VALUES`.
- Assigned values in `UPDATE ... SET`.
- `LIMIT` bounds when syntax/version allows.
- Comparison values in `JOIN` conditions or expressions.

Exact capability depends on statement syntax and MySQL version. If a marker is placed in a non-value position, the server raises an error or treats it as an expression value rather than an object name.

## 4. EXECUTE USING requires user-defined variables

With SQL-level `EXECUTE ... USING`, arguments must be user-defined variables (`@variable`). Never pass local variables or stored procedure parameters directly into `USING`.

Example showing local variables cannot be passed directly:

```sql
-- Inside a stored procedure, this is invalid:
-- EXECUTE stmt_find USING p_tenant_id;
```

Copy values from routine parameters/local variables into user-defined variables first:

```sql
SET @sp_tenant_id = p_tenant_id;
EXECUTE stmt_find USING @sp_tenant_id;
```

User-defined variables are session-scoped, not routine-scoped. Therefore, use distinct prefixes to avoid collisions and clear their values upon completion:

```sql
SET @sp_tenant_id = NULL;
```

When a connection returns to a pool, user-defined variables may persist when the connection is reused. Cleanup is part of safe routine design.

## 5. PREPARE accepts a string literal or user variable

SQL text can be supplied directly as a string literal:

```sql
PREPARE stmt_count FROM
    'SELECT COUNT(*) FROM orders WHERE tenant_id = ?';
```

Or via a user variable:

```sql
SET @sql_text =
    'SELECT COUNT(*) FROM orders WHERE tenant_id = ?';
PREPARE stmt_count FROM @sql_text;
```

Inside stored procedures, the common pattern is building the string with `CONCAT()` and assigning it to a user variable:

```sql
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders ',
    'WHERE tenant_id = ?'
);
PREPARE stmt_orders FROM @sql_text;
```

Local variables can help build strings via `CONCAT()`, but the source passed to `PREPARE` must still be a string literal or user variable per SQL-level syntax. Never pass a local variable directly to `PREPARE ... FROM`.

### One PREPARE prepares one statement

The SQL text must be a single preparable statement. Do not concatenate multiple semicolon-separated statements expecting `PREPARE` to run like a script:

```sql
-- Do not use one prepared statement to run two independent statements
SET @sql_text =
    'UPDATE orders SET status = ? WHERE order_id = ?; SELECT * FROM orders';
```

Prepare and execute each statement separately, or design a stored procedure with the needed static SQL statements. Do not enable multi-statements via arbitrary string concatenation.

## 6. Session scope of prepared statements

SQL-level prepared statements belong to the **current session/connection**:

- A connection can prepare and execute its own statements.
- Another connection cannot execute a statement name created in this session.
- A statement persists after the stored procedure that created it finishes.
- A statement is freed on `DEALLOCATE PREPARE` or when the session ends.
- Statement names live in the session namespace; routines reusing the same name can collide if executed on the same connection.
- If `PREPARE` reuses an existing name, MySQL automatically deallocates the old statement before preparing the new one under that name; if the new prepare fails, the old statement is no longer available under that name.

Example:

```sql
-- Session A
PREPARE stmt_session_demo FROM 'SELECT 1';
EXECUTE stmt_session_demo;
```

```sql
-- Session B: cannot use a statement created in Session A
EXECUTE stmt_session_demo;
```

Session B does not have `stmt_session_demo`, so `EXECUTE` fails. Naming a statement does not create a global object shared across connections.

### Prepared statements can outlive a procedure

Keep this in mind when writing stored procedures. `PREPARE` inside a procedure creates a statement in session scope, not local scope. If a procedure returns without deallocating, the statement remains alive on the calling connection.

Therefore:

- Always deallocate after use.
- Use distinct, easily identifiable statement names.
- Clear user variables created by the routine.
- Add handlers to clean up when `EXECUTE` raises an exception.
- Never assume procedure completion automatically frees statements.

## 7. Permitted scope of dynamic SQL in stored programs

SQL-level prepared statements are supported in stored procedures, but prohibited in stored functions and triggers. The core reason is that prepared statements and user variables are session-scoped, whereas local variables of functions/triggers have shorter lifecycles.

| Context | SQL-level `PREPARE`/`EXECUTE` |
|---|---|
| Normal SQL session | Allowed if the specific statement is supported. |
| Stored procedure | Allowed, subject to session/user-variable rules and statement support. |
| Stored function | Prohibited from using SQL-level prepared statements. |
| Trigger | Prohibited from using SQL-level prepared statements. |

A stored procedure can use dynamic SQL to pick a table or statement structure from controlled choices. That does not mean a procedure should execute arbitrary SQL strings supplied by callers.

### Which statements can be PREPAREd?

MySQL supports prepared statements for many SQL types, yet not every statement is preparable. Support depends on statement type and server version. For instance, administrative statements, session control statements, or stored routine definitions may have specific restrictions.

Safety rules:

1. Prepare only a statement belonging to MySQL's supported set.
2. Never attempt to `PREPARE` another `PREPARE`, `EXECUTE`, or `DEALLOCATE PREPARE` to nest them.
3. Never use prepared statements to submit multi-statement scripts.
4. Check documentation for your exact MySQL version when using specialized administrative statements.
5. Handle errors at both `PREPARE` and `EXECUTE`; never assume a statement is valid merely because the string was constructed.

## 8. Dynamic SQL cannot substitute identifiers with parameter markers

Suppose an application needs to query either `orders_current` or `orders_archive`. Table names are identifiers, not data values. The following does not work:

```sql
SET @table_name = 'orders_current';
PREPARE stmt_bad FROM 'SELECT COUNT(*) FROM ?';
EXECUTE stmt_bad USING @table_name;
```

When dynamic identifiers are required:

1. Accept a selection code from the caller.
2. Map that code to fixed table/column names in an allowlist.
3. Never use a caller-supplied string directly as an identifier.
4. Quote identifiers properly after allowlist validation.
5. Use parameter markers for all remaining data values.

### Table name allowlist example

```sql
DELIMITER //

CREATE PROCEDURE count_orders_from_source(
    IN p_source VARCHAR(20),
    IN p_tenant_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_table_name VARCHAR(64);

    CASE p_source
        WHEN 'current' THEN
            SET v_table_name = 'orders_current';
        WHEN 'archive' THEN
            SET v_table_name = 'orders_archive';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported order source';
    END CASE;

    SET @sp_count_orders_sql = CONCAT(
        'SELECT COUNT(*) AS order_count FROM `',
        REPLACE(v_table_name, '`', '``'),
        '` WHERE tenant_id = ?'
    );
    SET @sp_count_orders_tenant = p_tenant_id;

    PREPARE stmt_count_orders FROM @sp_count_orders_sql;
    EXECUTE stmt_count_orders USING @sp_count_orders_tenant;
    DEALLOCATE PREPARE stmt_count_orders;

    SET @sp_count_orders_sql = NULL;
    SET @sp_count_orders_tenant = NULL;
END//

DELIMITER ;
```

`p_source` accepts only two defined values. The table name in the SQL text comes from the allowlist, while `p_tenant_id` flows through a parameter marker. Quoting the identifier further protects object-name syntax, while the allowlist governs whether the caller may select that object.

This illustrative procedure assumes both tables exist and contain a `tenant_id` column. In production environments, enforce access privileges on both tables and archive data policies.

## 9. Example selecting ORDER BY from an allowlist

A common use case is letting users choose a sort order. Column names and `ASC`/`DESC` directions cannot be bound via markers. Map choices to fixed SQL fragments:

```sql
DELIMITER //

CREATE PROCEDURE find_orders_dynamic_sort(
    IN p_tenant_id BIGINT UNSIGNED,
    IN p_sort_mode VARCHAR(20),
    IN p_sort_direction VARCHAR(4),
    IN p_limit INT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_order_column VARCHAR(32);
    DECLARE v_direction VARCHAR(4);
    DECLARE v_limit INT UNSIGNED;

    CASE p_sort_mode
        WHEN 'created' THEN
            SET v_order_column = 'created_at';
        WHEN 'amount' THEN
            SET v_order_column = 'total_amount';
        WHEN 'id' THEN
            SET v_order_column = 'order_id';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort column';
    END CASE;

    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            SET v_direction = 'ASC';
        WHEN 'DESC' THEN
            SET v_direction = 'DESC';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort direction';
    END CASE;

    SET v_limit = LEAST(COALESCE(p_limit, 50), 100);

    SET @sp_find_orders_sql = CONCAT(
        'SELECT order_id, status, created_at, total_amount ',
        'FROM orders WHERE tenant_id = ? ',
        'ORDER BY `', v_order_column, '` ', v_direction,
        ', order_id DESC LIMIT ?'
    );
    SET @sp_find_orders_tenant = p_tenant_id;
    SET @sp_find_orders_limit = v_limit;

    PREPARE stmt_find_orders FROM @sp_find_orders_sql;
    EXECUTE stmt_find_orders
        USING @sp_find_orders_tenant, @sp_find_orders_limit;
    DEALLOCATE PREPARE stmt_find_orders;

    SET @sp_find_orders_sql = NULL;
    SET @sp_find_orders_tenant = NULL;
    SET @sp_find_orders_limit = NULL;
END//

DELIMITER ;
```

Only `v_order_column` and `v_direction` are concatenated into the SQL text, and both are mapped from allowlists. `p_tenant_id` and `v_limit` are values bound via `?`. `order_id DESC` provides a fixed tie-breaker so output ordering stays deterministic when rows share identical primary sort values.

The `LIMIT` cap in this example is an application policy, not a mandatory MySQL limit. Input values are bounded before binding to prevent a caller from requesting an excessively large result set.

## 10. Cleanup on errors

If `EXECUTE` fails and the procedure exits immediately, the prepared statement can remain alive in the session. Use an `EXIT HANDLER` to release the statement if created, clear user variables, and rethrow the original error with `RESIGNAL`.

Example handler skeleton:

```sql
DELIMITER //

CREATE PROCEDURE count_orders_safe(
    IN p_tenant_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_prepared BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_prepared THEN
            DEALLOCATE PREPARE stmt_count_orders_safe;
        END IF;

        SET @sp_count_orders_safe_sql = NULL;
        SET @sp_count_orders_safe_tenant = NULL;
        RESIGNAL;
    END;

    SET @sp_count_orders_safe_sql =
        'SELECT COUNT(*) AS order_count
         FROM orders
         WHERE tenant_id = ?';
    SET @sp_count_orders_safe_tenant = p_tenant_id;

    PREPARE stmt_count_orders_safe
        FROM @sp_count_orders_safe_sql;
    SET v_prepared = TRUE;

    EXECUTE stmt_count_orders_safe
        USING @sp_count_orders_safe_tenant;

    DEALLOCATE PREPARE stmt_count_orders_safe;
    SET v_prepared = FALSE;

    SET @sp_count_orders_safe_sql = NULL;
    SET @sp_count_orders_safe_tenant = NULL;
END//

DELIMITER ;
```

`v_prepared` is set to `TRUE` only after `PREPARE` succeeds. If `PREPARE` fails, the handler does not attempt to deallocate a nonexistent statement. If `EXECUTE` fails, the handler releases the statement and runs `RESIGNAL` so the caller still receives the original error.

In real procedures, assign unique statement names per routine and avoid reusing the same name for multiple purposes within a session. If a routine has multiple dynamic SQL branches, carefully track which statement was prepared so cleanup targets the right one.

## 11. Protecting against SQL injection

SQL injection occurs when untrusted data is interpreted as SQL syntax. Prepared statements prevent this in value positions because data travels separately via parameter markers.

### Unsafe pattern

```sql
-- Do not concatenate input directly into SQL literals
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders WHERE status = ''',
    @user_status,
    ''''
);
```

If `@user_status` contains quotes and SQL syntax, the statement's structure can be altered.

### Safe pattern for data values

```sql
SET @sql_text =
    'SELECT order_id FROM orders WHERE status = ?';
SET @user_status = 'PAID';

PREPARE stmt_status FROM @sql_text;
EXECUTE stmt_status USING @user_status;
DEALLOCATE PREPARE stmt_status;
```

`@user_status` is passed as data, never concatenated into SQL syntax.

### For identifiers, use an allowlist

Parameter markers cannot bind table/column names. Never accept raw identifiers from callers and concatenate them into strings. Use enums/selection codes mapped to fixed identifier lists as shown in `p_source` and `p_sort_mode` above.

Quoting identifiers with backticks protects syntax when names contain special characters; it neither grants access privileges nor replaces an allowlist. Never use `QUOTE()` as a substitute for parameter binding on values; `QUOTE()` builds a string literal representation, whereas prepared markers keep data completely separate from SQL text.

## 12. SQL SECURITY DEFINER and SQL SECURITY INVOKER

Stored procedures can declare their execution privilege context:

- `SQL SECURITY DEFINER`: the routine executes with the definer's privileges.
- `SQL SECURITY INVOKER`: the routine executes with the caller's privileges.

Dynamic SQL inside a procedure is governed by the routine's security context. Thus, an `SQL SECURITY DEFINER` procedure can execute dynamic SQL with broader privileges than the caller. If identifiers are assembled from untrusted input, the risk can escalate into accessing data outside the caller's permitted scope.

Rules:

1. Choose `DEFINER`/`INVOKER` per least-privilege requirements.
2. Allowlist tables, columns, and sort modes.
3. Parameterize every data value.
4. Never let callers supply raw SQL statements for a procedure to run.
5. Verify tenant scope and access privileges in every dynamic SQL branch.
6. Use a definer account with minimal required privileges.

`SQL SECURITY INVOKER` does not automatically make dynamic SQL safe if SQL is still concatenated from untrusted input. Parameterization and allowlists remain mandatory.

## 13. Statement names, user variables, and connection pools

Prepared statement names and user-defined variables both belong to the session. When a connection is reused from a pool, session state may remain from an earlier request.

Examples of state to clear:

```sql
DEALLOCATE PREPARE stmt_find_orders;
SET @sp_find_orders_sql = NULL;
SET @sp_find_orders_tenant = NULL;
SET @sp_find_orders_limit = NULL;
```

Do not blindly run `DEALLOCATE` without knowing whether the statement exists; doing so can raise an "unknown prepared statement handler" error. Use a handler and flag as in the cleanup example so deallocation happens only when preparation succeeded.

If two routines on the same connection share a prepared statement name, the second routine can collide with the existing statement. Pick uniquely prefixed names and ensure cleanup before returning the connection to the pool.

## 14. Resource limits and observing prepared statements

MySQL caps the total number of concurrent prepared statements via `max_prepared_stmt_count`. Un-deallocated prepared statements can accumulate and eventually cause new `PREPARE` commands to fail.

Check configuration:

```sql
SHOW VARIABLES LIKE 'max_prepared_stmt_count';
```

Check current prepared statement count:

```sql
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
```

You can inspect statements instrumented by Performance Schema:

```sql
SELECT
    STATEMENT_ID,
    STATEMENT_NAME,
    SQL_TEXT,
    OWNER_THREAD_ID
FROM performance_schema.prepared_statements_instances;
```

Visibility depends on Performance Schema and server instrumentation. Not every client-side prepared statement appears identically in this table; identify the exact prepared statement mechanism you are investigating.

If `Prepared_stmt_count` grows steadily, check whether routines omit `DEALLOCATE PREPARE`, whether connection pools hold sessions open long-term, and whether applications generate unbounded new statement names.

## 15. Are prepared statements always faster than regular SQL?

Prepared statements can reduce repeated parsing overhead when the exact same statement structure executes many times with varying values. They also separate data from syntax and help prevent SQL injection in value positions.

However, not every dynamic SQL or prepared statement is faster:

- If executed only once, `PREPARE` overhead may not pay off.
- If SQL structure changes constantly, statement-reuse benefits shrink.
- The optimizer must still pick an execution plan, and data/index read costs still apply.
- Metadata changes can force the server to re-check or re-prepare statements.
- Dynamic identifiers generate distinct SQL statements, preventing reuse of a single statement text across all identifiers.
- Concatenating SQL strings does not speed up queries; it only creates different SQL texts.

Benchmark realistic workloads and adopt prepared statements for safety, parameter handling, and reuse; do not treat them as a default performance trick.

## 16. Common mistakes

| Error | Cause | How to handle |
|---|---|---|
| Using `?` for table/column names | Markers represent data values only | Use identifier allowlists and append controlled syntax fragments. |
| Concatenating user input into SQL text | Risks SQL injection | Bind values via `EXECUTE ... USING`. |
| Passing local variables directly to `USING` | SQL-level `EXECUTE` requires user variables | Copy into `@user_variable` first. |
| `PREPARE` from a local variable | `PREPARE` source must be a string literal or user variable | Assign SQL text to `@sql` and `PREPARE` from it. |
| Missing `DEALLOCATE` | Statement persists in session after procedure ends | Always clean up on both success and exception paths. |
| Assuming statements vanish when procedure ends | Statements have session scope | Deallocate explicitly. |
| Using `PREPARE` in stored functions/triggers | SQL-level prepared statements are prohibited in these contexts | Use static SQL or move appropriate logic into a stored procedure. |
| Putting multiple SQL statements in one `PREPARE` | One prepared statement holds one statement | Prepare/execute each statement individually. |
| Mismatched marker count and `USING` arguments | Argument count/order does not match | Match each `?` with its corresponding user variable. |
| Reusing generic statement names across routines | Session namespace collisions | Use distinct names and clean up per lifecycle. |
| Choosing `SQL SECURITY DEFINER` without allowlists | Dynamic SQL may run with definer privileges | Least privilege, allowlists, and tenant scope checks. |
| Thinking `PREPARE` always makes queries faster | Ignoring parse costs, plans, and actual I/O | Benchmark before/after on identical workloads. |

## 17. Process for writing safe dynamic SQL

When a stored procedure genuinely requires dynamic SQL, follow this sequence:

1. Identify exactly which part of the SQL must vary: table, column, sort mode, or statement branch.
2. Keep all data values as `?` parameter markers.
3. Determine allowed identifiers using an allowlist or internal mapping.
4. Quote identifiers per MySQL rules after verifying allowlist membership.
5. Build a single SQL statement inside a user variable.
6. Assign user variables for parameter markers in exact order.
7. `PREPARE` with a dedicated statement name.
8. Track prepared state so handlers know whether cleanup is required.
9. Run `EXECUTE ... USING` and check results/errors.
10. Run `DEALLOCATE PREPARE` on the success path.
11. Use an exception handler to clean up and `RESIGNAL` on errors.
12. Clear user variables and ensure no session state leaks to the next request.
13. Benchmark performance and verify correctness across valid identifier choices.

If statement structure does not need to change, prefer static SQL or driver prepared statements. Dynamic SQL increases complexity around syntax control, privileges, and cleanup.

## 18. Practice exercises

### Exercise A — PREPARE/EXECUTE/DEALLOCATE lifecycle

1. Create `@sql_text` for a `SELECT` by `tenant_id`.
2. `PREPARE` the statement.
3. `EXECUTE` with two different tenants.
4. `DEALLOCATE` the statement.
5. Attempt to `EXECUTE` again after deallocation and explain the error.

### Exercise B — Parameter marker ordering

1. Prepare a `SELECT` with four markers: tenant, status, from time, and until time.
2. `EXECUTE` using four user variables.
3. Swap the order of two variables and observe the output.
4. Try omitting one variable in `USING`.
5. Explain why marker order and count must match.

### Exercise C — Identifiers cannot be bound

1. Try `SELECT * FROM ?` and explain why it does not work as a dynamic table name.
2. Write a stored procedure accepting `p_source`.
3. Map `current`/`archive` to two fixed table names.
4. Reject any choice outside the allowlist with `SIGNAL`.
5. Bind `tenant_id` via a parameter marker.

### Exercise D — Controlled ORDER BY

1. Allow sorting by `created_at`, `total_amount`, or `order_id`.
2. Allow `ASC` or `DESC` direction.
3. Allowlist both sort column and sort direction.
4. Bind tenant and limit with markers.
5. Add a tie-breaker so output ordering stays deterministic.

### Exercise E — Cleanup on exception

1. Write a procedure with `EXIT HANDLER FOR SQLEXCEPTION`.
2. Track a `v_prepared` flag.
3. Trigger a controlled error during `EXECUTE`.
4. Verify the statement was deallocated and user variables were cleared.
5. Confirm the original error is returned via `RESIGNAL`.

### Exercise F — Session scope

1. `PREPARE` a statement in Session A.
2. Try to `EXECUTE` that statement name in Session B.
3. Call a stored procedure that creates a prepared statement without deallocating it in a test environment.
4. After the procedure ends, verify the statement still exists in the session.
5. `DEALLOCATE` it and verify resources are released.

You complete this lesson when you can describe the three-statement lifecycle, distinguish session scope from routine scope, bind values properly using user variables, allowlist identifiers, and explain why SQL-level prepared statements are allowed only in stored procedures and not in stored functions/triggers.

## 19. Principles to remember

- `PREPARE` parses a single SQL statement and creates a prepared statement in the current session.
- `EXECUTE ... USING` passes values matching the exact order of `?` parameter markers.
- `DEALLOCATE PREPARE` frees the statement; never rely on procedure exit to auto-clean.
- The SQL text for `PREPARE` is a string literal or user-defined variable; inside routines, use `@variable` as the `PREPARE` source.
- SQL-level `EXECUTE ... USING` takes user-defined variables, not local variables or routine parameters directly.
- Parameter markers are for data values, not table names, column names, keywords, or syntax fragments.
- Dynamic identifiers must be chosen from an allowlist and quoted properly; all data values must still be bound.
- One prepared statement holds one preparable statement; do not concatenate multi-statement scripts.
- Prepared statements and user variables are session-scoped; connection pools can reuse leftover state.
- SQL-level prepared statements are allowed in stored procedures, not in stored functions or triggers.
- Statement support depends on SQL type and MySQL version; consult version-specific documentation.
- Use exception handlers, state flags, and `RESIGNAL` to clean up when `EXECUTE` fails.
- Choose `SQL SECURITY DEFINER`/`INVOKER` per least privilege; dynamic SQL must not exceed intended privilege scope.
- Prepared statements aid safety and reuse, but do not automatically make every query faster.

By mastering `PREPARE`, `EXECUTE`, `DEALLOCATE PREPARE`, and the permitted scope of dynamic SQL, you can build flexible stored procedures while keeping data values separate from syntax, restricting identifiers via allowlists, and releasing resources cleanly within the session lifecycle.
