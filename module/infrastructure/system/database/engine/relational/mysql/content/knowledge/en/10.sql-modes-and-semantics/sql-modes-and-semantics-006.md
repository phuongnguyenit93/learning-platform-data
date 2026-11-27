# PIPES_AS_CONCAT, String Concatenation, and Differences from the OR Operator

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backups, and operations. A detail that easily causes bugs when migrating applications or using different SQL modes is the double vertical bar operator ||. In MySQL, || defaults to the logical OR operator; when the PIPES_AS_CONCAT SQL mode is enabled, it becomes the string concatenation operator.

This change affects both expression semantics and operator precedence. An SQL statement can return different results even when the query text is unchanged. This lesson explains the two interpretations of ||, how to manage the mode per session and globally, and how to write unambiguous SQL to avoid implicit configuration dependencies.

## 1. Two Meanings of the || Operator

MySQL supports two interpretations of ||, depending on the SQL mode:

| Configuration | Meaning of || | Example |
|---|---|---|
| PIPES_AS_CONCAT disabled | Logical OR, equivalent to OR | 1 || 0 evaluates to TRUE (1) |
| PIPES_AS_CONCAT enabled | String concatenation, similar to joining strings | 1 || 0 produces string '10' |

Example in a typical default configuration:

~~~sql
SELECT 1 || 0 AS result;
-- || is interpreted as OR, result is 1
~~~

When PIPES_AS_CONCAT is enabled:

~~~sql
SELECT 1 || 0 AS result;
-- || is interpreted as string concatenation, result is '10'
~~~

This is a semantic difference, not just a stylistic difference. If the same application connects to two MySQL servers with different SQL modes, a statement containing || can return different results.

### 1.1. OR Is Used to Combine Conditions

OR is a logical operator. The expression evaluates to TRUE when at least one condition is true:

~~~sql
SELECT *
FROM users
WHERE is_active = 1
   OR is_admin = 1;
~~~

The query retrieves users who are active or users who are administrators. This is condition combination, not text concatenation.

### 1.2. String Concatenation Produces a Text Value

When you want to join text parts, you can use the CONCAT function:

~~~sql
SELECT CONCAT('My', 'SQL') AS product_name;
-- Result: MySQL
~~~

If PIPES_AS_CONCAT is enabled, you could write:

~~~sql
SELECT 'My' || 'SQL' AS product_name;
-- Result: MySQL
~~~

However, CONCAT clearly expresses string concatenation intent and does not depend on whether PIPES_AS_CONCAT is enabled. For SQL code shared across multiple environments, this is generally the more maintainable choice.

## 2. PIPES_AS_CONCAT Is an SQL Mode

SQL mode is a collection of options configuring how MySQL handles syntax, invalid data, and certain SQL compatibility rules. PIPES_AS_CONCAT changes the meaning of the || operator to use it as string concatenation.

View the current session's mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

View the server-wide default mode:

~~~sql
SELECT @@GLOBAL.sql_mode;
~~~

Check specifically for this mode:

~~~sql
SELECT FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
       AS pipes_as_concat_enabled;
~~~

FIND_IN_SET returns the element's position in a comma-separated list; a result greater than 0 means the mode is enabled. Do not just search substrings with LIKE, as element-wise matching is more accurate and explicit.

### 2.1. Session-Level SQL Mode

Each MySQL connection has its own SESSION sql_mode variable. When setting a mode for a session, the change only affects statements executed on that connection:

~~~sql
SET SESSION sql_mode = 'PIPES_AS_CONCAT';
~~~

The statement above replaces the session's entire mode list with just one mode. It can accidentally turn off other critical modes such as STRICT_TRANS_TABLES or ONLY_FULL_GROUP_BY. In real applications, do not assign a stripped-down list if the goal is only to add one mode.

You can add the mode while preserving existing modes:

~~~sql
SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(
      ',',
      NULLIF(@@SESSION.sql_mode, ''),
      'PIPES_AS_CONCAT'
    )
  );
~~~

Before changing, you can save the old value for restoration:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

-- Perform experiments or work requiring the new mode.

SET SESSION sql_mode = @saved_sql_mode;
~~~

The @saved_sql_mode variable is a user variable belonging to the current session. It is not shared with other sessions and disappears when the connection closes.

### 2.2. Global-Level SQL Mode

GLOBAL sql_mode is the default value used to initialize modes for new connections. Changing global does not automatically alter the mode of existing sessions.

For example, a DBA can add the mode for new connections:

~~~sql
SET GLOBAL sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@GLOBAL.sql_mode) > 0,
    @@GLOBAL.sql_mode,
    CONCAT_WS(
      ',',
      NULLIF(@@GLOBAL.sql_mode, ''),
      'PIPES_AS_CONCAT'
    )
  );
~~~

This command requires appropriate system administration privileges, such as SYSTEM_VARIABLES_ADMIN on modern MySQL versions or corresponding administrative privileges in older versions. After the change, new connections receive the new global value; the current session retains its old @@SESSION.sql_mode.

Verify by opening a new connection and running:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Do not use SET GLOBAL as a temporary fix for a single application request. Global changes affect all new connections to the instance and must be managed in a controlled manner.

### 2.3. Configuration That Persists Across Restarts

SET GLOBAL changes the runtime value; not all runtime changes automatically survive a MySQL restart. You can configure sql_mode in the server configuration file:

~~~ini
[mysqld]
sql_mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,PIPES_AS_CONCAT
~~~

The list above is just an example. Retrieve the environment's existing mode list, identify the modes to keep, and add PIPES_AS_CONCAT according to policy. Overwriting sql_mode with an incomplete list can alter other application behaviors.

MySQL 8.0 also supports SET PERSIST to save a dynamic system variable into configuration maintained across restarts. When using it, specify the complete desired sql_mode value and ensure proper privileges; do not treat SET PERSIST as an append-only operation if the assignment expression replaces the entire list.

## 3. PIPES_AS_CONCAT Changes How SQL Statements Are Read

### 3.1. One Expression, Two Results

Consider:

~~~sql
SELECT 1 || 0 + 2 AS result;
~~~

When the mode is off, || is OR and the expression is evaluated as a logical operation combined with addition according to MySQL operator precedence. When the mode is on, || is string concatenation and has different precedence. Therefore, do not rely on mixed expressions to infer results across environments.

When an expression mixes multiple operator types, use parentheses to express the intended evaluation order and use CONCAT for string concatenation. This makes statements readable without requiring readers to know which SQL mode is active.

### 3.2. Operator Precedence Changes

When PIPES_AS_CONCAT is disabled, || is treated as OR and has the precedence of the OR operator. When enabled, || becomes the string concatenation operator and takes string concatenation precedence under MySQL rules, which is higher than logical AND/OR operators.

Consequence: an unparenthesized expression can group operands differently depending on the mode. For example, avoid writing:

~~~sql
SELECT first_name || last_name = 'AnNguyen'
FROM users;
~~~

In one environment, the expression may be parsed as a logical condition; in another, it may be string concatenation followed by comparison. Write explicitly:

~~~sql
SELECT CONCAT(first_name, last_name) = 'AnNguyen' AS matches
FROM users;
~~~

If you want to add a space:

~~~sql
SELECT CONCAT(first_name, ' ', last_name) AS full_name
FROM users;
~~~

For conditional expressions, always use the OR keyword:

~~~sql
SELECT *
FROM users
WHERE (is_active = 1)
   OR (is_admin = 1);
~~~

Do not use || as shorthand for OR in new SQL code if the statements need to run across environments with different SQL modes.

## 4. Differences Between OR, CONCAT, and ||

| Need | Recommended Syntax | Meaning |
|---|---|---|
| Combine two conditions | condition_a OR condition_b | Returns logical result |
| Concatenate two strings | CONCAT(a, b) | Returns string value |
| Concatenate strings with separator and skip NULL arguments | CONCAT_WS(separator, a, b) | Returns concatenated string |
| Use || to concatenate strings in mode-standardized systems | a || b with PIPES_AS_CONCAT | Depends on SQL mode |

### 4.1. OR Uses Three-Valued Logic

OR operates under TRUE, FALSE, and UNKNOWN logic. Example:

~~~sql
SELECT
    TRUE OR FALSE AS true_or_false,
    FALSE OR FALSE AS false_or_false,
    NULL OR TRUE AS unknown_or_true,
    NULL OR FALSE AS unknown_or_false;
~~~

The results are TRUE, FALSE, TRUE, and UNKNOWN respectively. This is conditional logic; it does not produce a new string.

### 4.2. CONCAT Handling of NULL

CONCAT returns NULL if any argument is NULL:

~~~sql
SELECT CONCAT('An', NULL, 'Nguyen') AS full_name;
-- Result: NULL
~~~

If you want to skip NULL arguments after the separator, use CONCAT_WS:

~~~sql
SELECT CONCAT_WS(' ', 'An', NULL, 'Nguyen') AS full_name;
-- Result: An Nguyen
~~~

The separator argument of CONCAT_WS must not be NULL; if separator is NULL, the result is NULL. An empty string is not the same as NULL and is not automatically skipped. For instance, CONCAT_WS(' ', 'An', '', 'Nguyen') can produce consecutive spaces.

### 4.3. Normalizing Strings Before Concatenation

If NULL, empty strings, or whitespace-only strings are all considered absent content by business rules, you can normalize them:

~~~sql
SELECT CONCAT_WS(
         ' ',
         NULLIF(TRIM(first_name), ''),
         NULLIF(TRIM(middle_name), ''),
         NULLIF(TRIM(last_name), '')
       ) AS full_name
FROM users;
~~~

TRIM strips leading/trailing whitespace according to the function's rules; NULLIF converts empty strings to NULL; CONCAT_WS skips NULL arguments. Use this only if business logic truly treats those states as equivalent. If an empty string is a meaningful value, preserve it.

## 5. Error-Prone Scenarios When Using ||

### 5.1. WHERE Conditions

Do not write:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID' || status = 'SHIPPED';
~~~

If || is interpreted as OR, the statement may run as intended. If PIPES_AS_CONCAT is enabled, || has string concatenation precedence and the expression is parsed differently; results can deviate from intent due to comparisons and type coercion. Do not rely on this expression to express an OR condition.

Write explicitly:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
   OR status = 'SHIPPED';
~~~

Or use IN for a set of values:

~~~sql
SELECT *
FROM orders
WHERE status IN ('PAID', 'SHIPPED');
~~~

### 5.2. Concatenating Identifiers or Codes

Do not rely on || to concatenate codes:

~~~sql
-- Depends on PIPES_AS_CONCAT
SELECT region_code || '-' || order_number
FROM orders;
~~~

Write:

~~~sql
SELECT CONCAT(region_code, '-', order_number) AS order_code
FROM orders;
~~~

If a component can be NULL and you want to omit it, define the rule explicitly with CONCAT_WS or COALESCE; do not replace NULL with an empty string automatically if that obscures meaning.

### 5.3. Expressions in SELECT, ORDER BY, and GROUP BY

A string concatenation expression can be used as a result column, sort key, or grouping expression. If || is used, parsing can change by SQL mode:

~~~sql
SELECT CONCAT(last_name, ', ', first_name) AS display_name
FROM customers
ORDER BY display_name;
~~~

When the expression is given an alias, that alias can be used in ORDER BY. If you need to GROUP BY the same expression, you can repeat the CONCAT expression or use the alias per MySQL syntax. Using CONCAT keeps concatenation semantics stable.

### 5.4. Dynamic SQL

When building dynamic SQL in a procedure or application, string assembly for SQL must use intentional string operations. Do not construct SQL expressions using || unless the execution session's mode is guaranteed:

~~~sql
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders WHERE status = ',
    QUOTE('PAID')
);
PREPARE stmt FROM @sql_text;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
~~~

The example above illustrates assembling an SQL statement. In applications, use prepared statements with bind parameters for values instead of concatenating input directly into statements. Dynamic identifiers cannot be bound like regular values; use an allowlist and quote properly.

## 6. Impact on Prepared Statements and Stored Programs

### 6.1. Prepared Statements

A prepared statement is parsed at prepare time. Because PIPES_AS_CONCAT changes how the parser interprets ||, the mode in effect when preparing the statement can affect how the expression is parsed.

Illustrative example in a session:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = CONCAT_WS(
    ',',
    NULLIF(@@SESSION.sql_mode, ''),
    'PIPES_AS_CONCAT'
);

PREPARE stmt FROM 'SELECT 1 || 0 AS result';
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET SESSION sql_mode = @saved_sql_mode;
~~~

When testing, check the mode beforehand to avoid duplicate additions and ensure the statement is prepared under the intended mode. If you change the mode, re-prepare the statement so test results reflect syntax parsed under the new mode.

In Java applications, the driver may use server-side or client-side prepared statements depending on configuration. Regardless of implementation, still avoid || for SQL code that requires consistent semantics across servers.

### 6.2. Stored Procedures and Stored Functions

MySQL saves the SQL mode in effect when a stored procedure or stored function is created. When the routine runs, it uses the mode recorded with the routine rather than automatically adopting the caller's current mode for parsing the entire routine body.

This means a routine containing || may continue carrying its creation-time semantics even after the server's global/session mode changes. When changing SQL mode policy, inspect existing routines and review their definitions using:

~~~sql
SHOW CREATE PROCEDURE procedure_name;
SHOW CREATE FUNCTION function_name;
~~~

If a routine needs different semantics, update and recreate the routine in an environment with the defined SQL mode. Explicitly using CONCAT and OR makes routines far less mode-dependent.

### 6.3. Triggers and Deployment Consistency

Triggers also store the SQL mode at creation time. When migrating schemas between environments, check the SQL mode used when creating procedures, functions, and triggers. A migration run across two environments with different modes can create stored programs with different semantics if they contain mode-dependent operators.

Inspect trigger definitions:

~~~sql
SHOW CREATE TRIGGER trigger_name;
~~~

Include the expected SQL mode in deployment pipelines and run migrations with identical configuration across development, staging, and production.

## 7. How to Switch or Standardize SQL Mode

### 7.1. Checking Before Making Changes

Run:

~~~sql
SELECT @@GLOBAL.sql_mode AS global_mode,
       @@SESSION.sql_mode AS session_mode,
       FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
         AS pipes_as_concat_enabled;
~~~

Save the current values and identify which connections need changes. Do not change global just to test an individual query.

### 7.2. Enabling in a Lab Session

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'PIPES_AS_CONCAT')
  );

SELECT @@SESSION.sql_mode;
SELECT 1 || 0 AS concatenated_value;

SET SESSION sql_mode = @saved_sql_mode;
~~~

After restoring, verify the mode matches the saved value. If the session already had the mode enabled initially, the append expression preserves the list unchanged.

### 7.3. Enabling for New Connections

A DBA can set the global mode once application-wide impact has been evaluated:

~~~sql
SET GLOBAL sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@GLOBAL.sql_mode) > 0,
    @@GLOBAL.sql_mode,
    CONCAT_WS(',', NULLIF(@@GLOBAL.sql_mode, ''), 'PIPES_AS_CONCAT')
  );
~~~

Open a new connection and check @@SESSION.sql_mode. Existing connections do not automatically receive the new global value. With connection pools, recycle or recreate connections according to plan so new connections pick up the configuration.

### 7.4. Controlled Disabling of the Mode

If you need to remove PIPES_AS_CONCAT, prefer restoring the saved session value on the same connection:

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
~~~

If changing global configuration or the configuration file, rebuild the desired mode list from the centrally managed baseline configuration. Do not replace the entire list with an empty string just to disable one mode; doing so can strip away critical data validation rules.

## 8. Recommendations When Writing SQL

### 8.1. Use the OR Keyword for Logic

~~~sql
SELECT *
FROM products
WHERE category = 'BOOK'
   OR category = 'MAGAZINE';
~~~

Or:

~~~sql
SELECT *
FROM products
WHERE category IN ('BOOK', 'MAGAZINE');
~~~

The OR keyword directly expresses a logical condition and is unaffected by PIPES_AS_CONCAT.

### 8.2. Use CONCAT for String Concatenation

~~~sql
SELECT CONCAT(order_prefix, '-', order_number) AS order_code
FROM orders;
~~~

CONCAT clearly indicates the arguments are joined into a string. The statement is independent of SQL mode and portable across MySQL and data access layers.

### 8.3. Use CONCAT_WS When a Separator Is Needed

~~~sql
SELECT CONCAT_WS(
    ' / ',
    NULLIF(TRIM(country), ''),
    NULLIF(TRIM(city), ''),
    NULLIF(TRIM(district), '')
) AS address_summary
FROM customer_addresses;
~~~

CONCAT_WS is appropriate when a separator is needed and NULL components should be skipped. Converting empty strings or whitespace to NULL must follow business rules.

### 8.4. Use Parentheses When Expressions Have Multiple Operators

Parentheses help readers understand evaluation order and avoid relying on operator precedence tables. Example:

~~~sql
SELECT *
FROM orders
WHERE (status = 'PAID' OR status = 'SHIPPED')
  AND created_at >= '2026-01-01';
~~~

Do not mix || with AND, OR, addition, or comparison in complex expressions. If || means string concatenation, switch to CONCAT; if it means logic, switch to OR.

## 9. Impact on Cross-Environment Compatibility

SQL mode can differ across local, test, staging, production, replicas, or server versions. Sources of divergence include:

- Different server configuration files.
- Different mysqld startup parameters.
- SET GLOBAL commands run during operations.
- Applications or connection pools altering SESSION sql_mode.
- Migrations creating stored procedures, functions, or triggers under different modes.

For each environment, record:

~~~sql
SELECT VERSION() AS mysql_version,
       @@GLOBAL.sql_mode AS global_sql_mode,
       @@SESSION.sql_mode AS session_sql_mode;
~~~

Check the mode using the actual application account, because the application's session mode can differ from the DBA's session. In systems with multiple replicas, check each necessary instance and enforce a uniform mode policy.

If legacy code uses || to represent OR, enabling PIPES_AS_CONCAT can alter results or break query intent. Conversely, if code uses || for string concatenation, running it on an instance without the mode enabled can produce unexpected logical results or type coercions. Review source code, migrations, views, routines, and dynamically generated queries before changing the mode system-wide.

## 10. Common Issues and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| 1 || 0 returns 1 instead of string 10 | Session does not have PIPES_AS_CONCAT enabled, so || is OR | Use CONCAT('1', '0') or check the mode |
| WHERE condition returns unexpected results | || is interpreted as string concatenation instead of OR | Rewrite using the OR or IN keyword |
| SQL behaves differently between local and production | The two sessions/instances have different SQL modes | Compare @@SESSION.sql_mode and @@GLOBAL.sql_mode |
| SET SESSION does not affect other connections | SQL mode is per-session state | Change on the target connection or configure global for new connections |
| SET GLOBAL ran, yet running app keeps old behavior | Existing sessions do not automatically adopt new global mode | Recreate/recycle connections per plan |
| Adding a mode dropped strict mode | Assigned a shortened sql_mode list that overwrote existing modes | Append carefully with checks or use the full standard list |
| Stored procedure still treats || with old semantics | Routine retains SQL mode from creation time | Inspect SHOW CREATE and recreate routine under standard mode |
| CONCAT returns NULL | At least one argument is NULL | Clarify NULL semantics; use COALESCE or CONCAT_WS when appropriate |

When investigating, always determine which session the statement ran in, what mode was active at prepare/parse time, and under which mode the routine was created. Do not draw conclusions from @@GLOBAL.sql_mode if the statement was executed by a session with its own mode.

## 11. Hands-on Exercise: Observing PIPES_AS_CONCAT

Perform in a MySQL lab using a dedicated connection. This exercise saves and restores the initial session mode.

**Step 1 — Record initial configuration.**

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SELECT @@SESSION.sql_mode,
       FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
         AS pipes_as_concat_enabled;
~~~

If the mode is already enabled, note that state. To observe default OR behavior, you need a test session where the mode is not enabled or a lab connection configured without this mode.

**Step 2 — Test OR behavior when the mode is off.**

~~~sql
SELECT 1 || 0 AS pipe_result,
       1 OR 0 AS explicit_or;
~~~

When the mode is off, both columns have the same logical meaning and return TRUE (1).

**Step 3 — Enable PIPES_AS_CONCAT for the session.**

~~~sql
SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'PIPES_AS_CONCAT')
  );

SELECT @@SESSION.sql_mode;
~~~

**Step 4 — Re-run the same expression.**

~~~sql
SELECT 1 || 0 AS pipe_result,
       1 OR 0 AS explicit_or,
       CONCAT('1', '0') AS explicit_concat;
~~~

When the mode is enabled, pipe_result is the string 10, explicit_or remains 1, and explicit_concat is always 10. This demonstrates that the two forms have different semantics.

**Step 5 — Practice concatenating names.**

~~~sql
SELECT CONCAT_WS(' ', 'Nguyen', NULL, 'An') AS full_name;
SELECT CONCAT('Nguyen', ' ', 'An') AS full_name;
~~~

Observe how CONCAT and CONCAT_WS handle NULL arguments.

**Step 6 — Restore the session.**

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
SELECT @@SESSION.sql_mode;
~~~

Close the lab connection after confirming restoration. If the connection closes before this step, the session mode ends with the session; no global changes are made by this exercise.

**Expected outcome:** able to explain why || has two meanings depending on SQL mode, know how to check and modify session mode, distinguish session from global, understand the impact on precedence, and rewrite SQL with OR/CONCAT to keep semantics stable.

## 12. Key Principles to Remember

- In MySQL, || defaults to OR; when PIPES_AS_CONCAT is enabled, it becomes string concatenation.
- This mode changes both how the parser interprets statements and operator precedence.
- @@SESSION.sql_mode governs the current connection's behavior; @@GLOBAL.sql_mode supplies the default for new connections.
- SET GLOBAL does not change existing sessions; connections must be recycled if they need to adopt the new mode.
- Runtime changes are not guaranteed to persist across restarts; use configuration files or SET PERSIST according to version and administrative privileges.
- Reassigning the entire sql_mode can unintentionally disable other modes; preserve the current list when only adding one mode.
- Stored procedures, functions, and triggers store SQL mode at creation time; check them when standardizing configuration.
- Use OR for logical conditions, CONCAT for string concatenation, and CONCAT_WS when a separator and NULL-skipping rules are needed.
- Use parentheses to clarify complex expressions; avoid mixing || with logical and arithmetic operators.
- Check SQL mode on the actual application session and each deployment environment.

Writing explicit SQL keeps applications independent of implicit mode configuration. Using OR for logic and CONCAT for strings ensures statements maintain consistent semantics across sessions, environments, and deployments.
