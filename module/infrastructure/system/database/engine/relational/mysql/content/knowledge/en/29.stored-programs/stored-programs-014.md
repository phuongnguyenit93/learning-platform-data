# Stored Functions vs. Loadable Functions and Security Boundaries

MySQL has two mechanisms commonly referred to as "user-defined functions" that differ architecturally: **stored functions** are written in SQL and stored in the database; **loadable functions** (UDFs) are native functions compiled into a shared library and loaded into the `mysqld` process. Both can be invoked inside SQL expressions, yet their lifecycles, deployment methods, privileges, and security risks differ dramatically.

Stored functions fit when you want to encapsulate calculations or data rules in SQL, control privileges with `SQL SECURITY DEFINER`/`INVOKER`, and grant `EXECUTE` per routine. Loadable functions should be considered only when native code is required that neither built-in functions nor stored functions can satisfy; UDF libraries run directly inside the server process and can directly impact the stability and security of the database server.

In the `DATABASE_MYSQL` module, choose the right function type based on where code executes and trust boundaries: stored functions run inside MySQL's SQL privilege context; loadable functions introduce native code into the `mysqld` process. This lesson focuses on MySQL 8.0 and later, InnoDB, and safe deployment practices.

## Objectives

After this lesson, you will be able to:

- Distinguish stored functions from loadable functions/UDFs.
- Recognize the creation syntax of each function type and their registration scope.
- Write scalar stored functions with `RETURNS`, `RETURN`, and appropriate characteristics.
- Understand the meaning of `DETERMINISTIC`, `NO SQL`, `READS SQL DATA`, and `MODIFIES SQL DATA`.
- Distinguish `SQL SECURITY DEFINER` from `SQL SECURITY INVOKER`.
- Design `CREATE ROUTINE`, `ALTER ROUTINE`, and `EXECUTE` privileges per least privilege.
- Understand stored function restrictions when accessing data or invoked from SQL statements.
- Describe how to install, uninstall, and deploy loadable UDFs across MySQL servers.
- Evaluate the risks of native libraries running inside the `mysqld` process.
- Choose among built-in functions, stored functions, loadable functions, or application code for a given problem.
- Inspect function metadata, privileges, and behavior before deployment.

## 1. Two function types, two execution models

### 1.1. Stored function

A stored function is a routine defined in SQL and stored in a MySQL schema. It has input parameters, a return type, and terminates with `RETURN`. Stored functions can be called inside expressions in `SELECT`, `WHERE`, `ORDER BY`, assignments, or other SQL expressions.

Simple example:

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION line_total(
    p_quantity INT UNSIGNED,
    p_unit_price DECIMAL(12, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
SQL SECURITY INVOKER
BEGIN
    RETURN p_quantity * p_unit_price;
END//

DELIMITER ;

SELECT line_total(3, 12.50) AS total_amount;
```

The function receives two values, computes their product, and returns a `DECIMAL` value. Because it needs no table access, `NO SQL` is declared; identical inputs yield identical results, so `DETERMINISTIC` fits.

### 1.2. Loadable function (UDF)

A loadable function is a function written in a native language such as C/C++, compiled into a shared library, and registered for MySQL to load. On Linux these are typically `.so` libraries; on Windows typically `.dll`.

Example syntax registering a precompiled scalar UDF installed in the valid plugin directory:

```sql
SHOW VARIABLES LIKE 'plugin_dir';

CREATE FUNCTION normalize_code
RETURNS STRING
SONAME 'normalize_code.so';

SELECT normalize_code(' ab-123 ');
```

`normalize_code.so` is a prebuilt native library; the SQL statement does not compile source code. MySQL loads the function from the specified library and calls the entry point per the UDF API.

### 1.3. Both are called in SQL, yet do not share the same boundary

```text
SQL statement
   |
   +-- Stored function
   |      -> routine definition in schema
   |      -> SQL routine interpreter
   |      -> SQL SECURITY DEFINER or INVOKER
   |      -> EXECUTE privilege and object access per security context
   |
   +-- Loadable UDF
          -> function registered with MySQL server
          -> native shared library
          -> code runs inside the mysqld process
          -> server/OS and plugin directory trust boundary
```

Stored functions are managed as routines inside a database. Loadable UDFs are native code loaded by the server; they do not share the `SQL SECURITY` mechanism of stored routines.

## 2. Comparing stored functions and loadable functions

| Criterion | Stored function | Loadable function / UDF |
|---|---|---|
| Deployment method | SQL routine | Native code compiled into a shared library |
| Where definition lives | Schema/database in MySQL data dictionary | Function and library registration on the server; library resides in the MySQL installation environment |
| Naming scope | Belongs to a schema; callable as `schema.function()` | Registered at the MySQL server level, not an application schema routine |
| How it is called | Inside SQL expressions | Inside SQL expressions |
| Return types | SQL data types declared after `RETURNS` | UDF types such as `STRING`, `INTEGER`, `REAL`, `DECIMAL` |
| Privileges | `CREATE ROUTINE`, `ALTER ROUTINE`, `EXECUTE`; `DEFINER`/`INVOKER` security context | Privileges to install/remove UDFs and server ops permissions; no `SQL SECURITY DEFINER/INVOKER` like stored routines |
| Executable code | SQL routine body | Native code inside the `mysqld` process |
| Deployment dependencies | Schema migrations and definer/privileges | Matching library, OS/architecture, ABI, and plugin config on each server |
| Risks | Data exposure or over-privileged actions if `DEFINER` is misdesigned | Crash, memory corruption, or executing native actions with `mysqld`'s OS privileges |
| Default choice | Preferred when logic fits SQL | Use only with a clear native requirement and strict controls |

Do not choose a loadable UDF merely to write a complex calculation. Check first whether built-in functions, SQL expressions, generated columns, stored functions, or application-layer logic can solve the problem.

## 3. Stored function syntax and characteristics

General structure:

```sql
CREATE [DEFINER = user]
FUNCTION function_name ([parameter[,...]])
RETURNS return_type
    [characteristic ...]
routine_body
```

Common characteristics:

```sql
LANGUAGE SQL
| [NOT] DETERMINISTIC
| {CONTAINS SQL | NO SQL | READS SQL DATA | MODIFIES SQL DATA}
| SQL SECURITY {DEFINER | INVOKER}
| COMMENT 'text'
```

Stored functions only accept input parameters; do not use `OUT` or `INOUT` as in stored procedures. The result is returned via `RETURN` and must match the type declared after `RETURNS`.

### 3.1. Pure function without table reads

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION apply_discount(
    p_amount DECIMAL(12, 2),
    p_percent DECIMAL(5, 2)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
CONTAINS SQL
SQL SECURITY INVOKER
BEGIN
    IF p_amount IS NULL OR p_percent IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_percent < 0 OR p_percent > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount percent must be between 0 and 100';
    END IF;

    RETURN p_amount * (1 - p_percent / 100);
END//

DELIMITER ;

SELECT apply_discount(250.00, 10.00) AS discounted_amount;
```

The result is `225.00`. The function computes solely from parameters and does not depend on database state or call time.

### 3.2. Function that reads data

A stored function can read a table and return a scalar value:

```sql
USE appdb;

CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

DELIMITER //

CREATE FUNCTION get_customer_status(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;

SELECT get_customer_status(100) AS customer_status;
```

This function depends on current data in `customer_profile`; the same `customer_id` can return a different result after the table is updated, so it should not be declared `DETERMINISTIC`. `SELECT ... INTO` loads one value into a local variable instead of emitting a result set to the client.

If no row is found, `SELECT ... INTO` raises a `NOT FOUND` warning and the variable retains its initial value (`NULL` in this example). If the query returns more than one row, MySQL raises an error; the primary key guarantees at most one row here.

### 3.3. Functions do not return result sets

A stored function returns a single value of the `RETURNS` type. Do not write a bare `SELECT` inside a function intending to send multiple rows to the client:

```sql
-- Invalid as a way to return a result set from a stored function:
-- SELECT customer_id, customer_status FROM customer_profile;
```

To return multiple rows, use a stored procedure with a result set, a view, or a direct SQL query. If multiple rows must be processed internally inside a function, a cursor may be considered within stored program restrictions, though the function still returns only one final scalar value.

### 3.4. Cleaning up routines and updating definitions

```sql
USE appdb;

SHOW CREATE FUNCTION apply_discount\G

ALTER FUNCTION apply_discount
COMMENT 'Calculate a percentage discount';

DROP FUNCTION IF EXISTS apply_discount;
```

`ALTER FUNCTION` modifies only supported characteristics, not the routine body. When the body needs changes, the migration workflow is typically `DROP FUNCTION` followed by `CREATE FUNCTION`; plan privileges and dependencies carefully beforehand. Never assume `CREATE OR REPLACE FUNCTION` syntax from other RDBMSs is available in MySQL.

## 4. DETERMINISTIC and SQL data access characteristics

Characteristics describe the behavior a routine declares to MySQL. They matter for binary logging and administration, but they are not an automated validator of internal logic.

### 4.1. DETERMINISTIC and NOT DETERMINISTIC

- `DETERMINISTIC`: identical input parameters must always yield identical results.
- `NOT DETERMINISTIC`: results can vary even with unchanged parameters.

Appropriate example for `DETERMINISTIC`:

```sql
USE appdb;

CREATE FUNCTION tax_amount(
    p_net DECIMAL(12, 2),
    p_rate DECIMAL(5, 2)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN p_net * p_rate / 100;
```

Example that should NOT be declared deterministic:

```sql
USE appdb;

CREATE FUNCTION current_label()
RETURNS VARCHAR(40)
NOT DETERMINISTIC
NO SQL
RETURN DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s');
```

`NOW()` depends on execution time. Functions like `RAND()` or `UUID()` likewise do not produce fixed outputs for identical empty arguments.

Declaring `DETERMINISTIC` does not make a time-dependent function deterministic. MySQL does not fully analyze the body to prove the declaration is accurate; the routine author is responsible for declaring honestly.

### 4.2. SQL data access characteristics

| Characteristic | Declared meaning | Example |
|---|---|---|
| `NO SQL` | Routine contains no SQL statements | Calculations from parameters |
| `CONTAINS SQL` | Contains SQL statements but neither reads nor writes data | Certain SQL operations without table access |
| `READS SQL DATA` | May read data | `SELECT ... INTO` from a table |
| `MODIFIES SQL DATA` | May modify data | `INSERT`, `UPDATE`, `DELETE` within permitted limits |

If omitted, MySQL applies default characteristics per routine syntax; declare them explicitly so reviewers understand intent. MySQL does not verify that the body strictly adheres to these labels.

### 4.3. Do not misdeclare to bypass binary logging checks

When binary logging is enabled, creating stored functions triggers extra checks to reduce the risk of inconsistent replication. Depending on version and configuration, checks involve `log_bin_trust_function_creators`, `DETERMINISTIC`/`NO SQL`/`READS SQL DATA` characteristics, and administrative privileges.

Check configuration:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_trust_function_creators';
```

Never declare `DETERMINISTIC` or `NO SQL` just to get DDL accepted if the function actually reads data or depends on external state. Do not enable `log_bin_trust_function_creators` in production merely to skip review; evaluate binary logging policies, replication mode, and required privileges for your exact MySQL version.

## 5. SQL SECURITY DEFINER and INVOKER

Stored functions have two primary security contexts:

- `SQL SECURITY DEFINER`: the body runs with the privileges of the definer account recorded in the routine definition.
- `SQL SECURITY INVOKER`: the body runs with the privileges of the account calling the function.

If omitted, the default is `DEFINER`. This is an important security boundary: someone holding `EXECUTE` on a `DEFINER` function can perform actions not granted directly to their account on underlying tables, within the scope allowed by the function.

### 5.1. Whose privileges does DEFINER use?

Example function reading customer status with `DEFINER` security context:

```sql
USE appdb;

DELIMITER //

CREATE DEFINER = 'customer_fn_owner'@'localhost'
FUNCTION customer_status_for_app(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;
```

When an application calls the function, MySQL checks the caller's `EXECUTE` privilege. Statements inside the function run under the privileges of `'customer_fn_owner'@'localhost'`. The caller does not necessarily need direct `SELECT` on `customer_profile` if the function is designed and granted properly.

The definer must exist and hold the required privileges on objects accessed by the body. If the definer account is dropped, has privileges altered, or objects change, the function can fail at runtime. Hence the definer is an operational dependency to manage alongside the routine.

### 5.2. INVOKER uses the caller's privileges

```sql
USE appdb;

DELIMITER //

CREATE FUNCTION customer_status_for_caller(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;

    SELECT customer_status
      INTO v_status
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_status;
END//

DELIMITER ;
```

With `INVOKER`, the caller needs `EXECUTE` on the function plus privileges needed to run the SQL statements inside the body, such as `SELECT` on `customer_profile`. `INVOKER` fits when the function only encapsulates logic and is not meant to grant elevated access to base tables.

### 5.3. Comparing execution privileges

| Situation | `DEFINER` | `INVOKER` |
|---|---|---|
| Who supplies privileges for SQL inside the body? | Definer account | Calling account |
| Does caller need `EXECUTE`? | Yes | Yes |
| Does caller need direct privileges on base tables? | Usually no, if body runs with definer privileges and function needs no other access | Yes, per operations performed by the body |
| Can it expose a controlled data API? | Yes, if the body strictly bounds data and permissions | Yes, though caller still needs base-object privileges |
| Primary risk | Function can become a privilege-escalation path if it leaks data or accepts unvalidated parameters | Caller must hold base privileges; grant surface is typically wider |

## 6. Designing definers with least privilege

Never use a DBA account, `root`, or an all-privileged application account as definer. Create a dedicated account holding only the minimal privileges required by the body.

Example privilege model:

```sql
-- Executed by DBA per system account policy.
CREATE USER 'customer_fn_owner'@'localhost' ACCOUNT LOCK;

GRANT SELECT ON appdb.customer_profile
TO 'customer_fn_owner'@'localhost';

GRANT CREATE ROUTINE ON appdb.*
TO 'routine_deployer'@'localhost';

GRANT EXECUTE ON FUNCTION appdb.customer_status_for_app
TO 'app_runtime'@'%';
```

The `customer_fn_owner` account only holds read privilege on the customer table. `app_runtime` can call the exposed function without direct `SELECT` on the base table in this model. A login-locked account can serve as definer under suitable policies/versions; verify behavior and definer management processes in your deployment environment.

### 6.1. Common privileges for stored routines

- `CREATE ROUTINE`: create stored procedures or stored functions in a schema.
- `ALTER ROUTINE`: alter or manage routines per granted privileges.
- `EXECUTE`: invoke stored procedures/functions.
- Privileges on tables/views: depend on `SQL SECURITY DEFINER` vs. `INVOKER` and statements in the body.
- Special privilege to specify a different definer: depends on MySQL version and dynamic privilege policies; never grant broadly.

In some configurations, `automatic_sp_privileges` automatically grants certain routine privileges to the creator. Do not rely on that default as an authorization policy; inspect actual grants and explicitly grant privileges to runtime/deployer accounts.

### 6.2. Do not let DEFINER functions become arbitrary read APIs

A function accepting `customer_id` and returning a status can be well-scoped. However, if a function accepts arbitrary parameters and returns sensitive content or accesses data outside the caller's scope, anyone with `EXECUTE` can use it to read unauthorized data.

For multi-tenant data, never trust a client-supplied `tenant_id` if callers can spoof values. Determine the tenant from a trusted security context or verify ownership in the body using data the caller cannot forge. `SQL SECURITY DEFINER` does not automatically provide row-level security.

## 7. Security boundary of loadable UDFs

A loadable UDF is native code loaded into the `mysqld` process. When the function is invoked, C/C++ code executes inside the same server process and can exercise process capabilities under the OS privileges held by `mysqld`.

This differs fundamentally from stored functions:

- `SQL SECURITY DEFINER/INVOKER` does not apply to UDFs.
- MySQL does not sandbox UDFs into an isolated OS process.
- Memory, pointer, or concurrency bugs inside the library can corrupt or crash the server.
- Native code can access OS files or resources accessible to the OS user running `mysqld`.
- A malicious or replaced library can become an arbitrary code execution vector inside the server.

Therefore, write access to `plugin_dir` and UDF registration privileges are high-impact privileges. Never give ordinary application accounts the ability to install native libraries.

### 7.1. Library governance process

Before deploying a UDF:

1. Clearly justify why built-in functions, stored functions, or application code cannot meet the requirement.
2. Review C/C++ source code, dependencies, error handling, and memory deallocation.
3. Build from trusted sources on controlled toolchains and platforms.
4. Verify compatibility with OS, CPU architecture, ABI, and MySQL version.
5. Verify artifact hashes/signatures and write permissions on the plugin directory.
6. Test on staging with boundary data, concurrent load, and failure scenarios.
7. Install the exact same library on every node that may execute the function, including replicas/failover nodes per architecture.
8. Register the UDF, verify loading, and test rollback/uninstallation.
9. Monitor server errors, memory, CPU, and query latency post-deployment.
10. Maintain a plan to unregister and safely remove artifacts when no longer needed.

Never copy an unknown `.so`/`.dll` file into `plugin_dir`. Never permit arbitrary file uploads into this directory.

## 8. Installing and removing loadable functions

### 8.1. Checking the plugin directory

```sql
SHOW VARIABLES LIKE 'plugin_dir';
```

The library must reside in the location MySQL permits for loading functions and match the server platform. The library name in `SONAME` is a filename, not an arbitrary path passed by a client.

### 8.2. Registering a scalar UDF

```sql
CREATE FUNCTION normalize_code
RETURNS STRING
SONAME 'normalize_code.so';
```

This registers a function whose native implementation resides in the library. If the symbol, return type, or UDF API is incompatible, registration or execution fails.

### 8.3. Aggregate UDFs

MySQL also supports loadable aggregate functions. Registration syntax includes the `AGGREGATE` keyword:

```sql
CREATE AGGREGATE FUNCTION weighted_stat
RETURNS REAL
SONAME 'analytics_udf.so';
```

Use this syntax only when the library fully implements the aggregate UDF interface. You cannot turn a scalar UDF into an aggregate merely by adding the `AGGREGATE` keyword.

### 8.4. Removing a UDF

```sql
DROP FUNCTION IF EXISTS normalize_code;
```

Unregister the function before removing the library file from the server environment. Audit all queries, routines, or applications still depending on the UDF. Never directly edit system tables to register/unregister UDFs; use supported SQL statements.

### 8.5. Privileges to install UDFs

Privileges to create/drop loadable functions differ from the `CREATE ROUTINE`/`EXECUTE` model of stored functions. MySQL requires privileges on the `mysql` system schema to register/unregister loadable functions; exact details depend on version. This is a sensitive privilege—never grant it broadly to runtime accounts, and never grant arbitrary writes to system schemas as an application deployment shortcut.

Verify privileges against documentation for your exact server version. Never directly edit the UDF registry in system tables instead of using `CREATE FUNCTION ... SONAME` or `DROP FUNCTION`.

## 9. Stored functions are not stored procedures

Both routine types live in a schema, yet they expose different interfaces:

| Characteristic | Stored function | Stored procedure |
|---|---|---|
| How called | Inside SQL expressions, e.g. `SELECT f(x)` | Via `CALL p(...)` |
| Result | One value of type `RETURNS` | Can return result sets, `OUT`/`INOUT`, or mutate state |
| Parameters | Input only | `IN`, `OUT`, `INOUT` |
| Used in `WHERE`/`SELECT` expressions | Yes | Cannot call a procedure directly as an expression |
| Best suited for | Scalar calculations/lookups | Multi-step workflows, returning multiple rows, or business operations |

If the goal is returning a scalar for use inside an expression, a stored function fits. If you need to return row lists or coordinate multi-step transactions, consider a stored procedure or direct query.

## 10. Important limitations of stored functions

Stored functions run in the context of an invoking statement and face stored routine restrictions. Key limits to remember:

- Functions must return a scalar value; they cannot return result sets directly.
- Never use `START TRANSACTION`, `COMMIT`, or `ROLLBACK` to manage transactions inside a function.
- Never use dynamic SQL via `PREPARE`/`EXECUTE` inside a stored function.
- Never perform implicit-commit operations as a routine DDL workflow inside a function.
- Never modify a table already used by the statement calling the function; errors like 1442 can occur.
- Never rely on the optimizer's evaluation order or frequency of function calls to perform side effects.

For example, avoid designing a function called inside `UPDATE customer_profile ...` that itself updates `customer_profile`. If multiple tables must change, use a stored procedure or application-layer transaction with clear boundaries.

### 10.1. Do not treat functions with side effects as pure expressions

A function called in `SELECT`, `WHERE`, or `ORDER BY` may be evaluated according to the execution plan. Never assume the function executes exactly once per row, runs left-to-right, or runs only after a particular predicate.

If a function mutates data, sends notifications, or produces side effects, calling it inside expressions yields unpredictable behavior. Prefer pure functions that only compute/return values; put data-modifying operations in procedures or explicit DML statements.

### 10.2. Calling functions across many rows can be expensive

Example:

```sql
SELECT
    customer_id,
    get_customer_status(customer_id)
FROM customer_profile;
```

If the table has millions of customers, the function may run millions of times, querying the table each time. A direct `JOIN` is usually far easier to optimize:

```sql
SELECT customer_id, customer_status
FROM customer_profile;
```

Encapsulating logic does not automatically make queries faster. Measure with `EXPLAIN ANALYZE`, latency, and representative workloads; avoid per-row table-reading function calls when `JOIN` or set-based expressions work.

## 11. Stored functions and indexes/sargability

Wrapping an indexed column in a function can make the predicate non-sargable on the original index:

```sql
-- May fail to use a range lookup on email as intended:
SELECT customer_id
FROM customer_account
WHERE normalize_email(email) = 'user@example.com';
```

If you can normalize the input value before comparing, keep the indexed column bare:

```sql
SELECT customer_id
FROM customer_account
WHERE email = 'user@example.com';
```

If normalization is a mandatory storage rule, consider storing a normalized column or an indexed generated column rather than calling a function on every row at query time. Always check with `EXPLAIN`/`EXPLAIN ANALYZE` on your real schema.

## 12. Metadata and privilege auditing

### 12.1. Inspecting stored functions

```sql
SHOW FUNCTION STATUS
WHERE Db = 'appdb';

SHOW CREATE FUNCTION appdb.customer_status_for_app\G
```

`INFORMATION_SCHEMA.ROUTINES` provides metadata for stored functions and procedures:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SQL_MODE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb'
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
```

Some metadata definitions may be hidden or restricted based on the querying account's privileges. Use an auditing account with appropriate rights, and never over-privilege applications just to inspect metadata.

### 12.2. Inspecting grants

```sql
SHOW GRANTS FOR 'app_runtime'@'%';
SHOW GRANTS FOR 'customer_fn_owner'@'localhost';
```

Cross-check `EXECUTE` privileges, definer/invoker table privileges, and routine creation/alteration privileges. Check granted roles and inherited privileges in your exact MySQL version.

### 12.3. Inspecting loadable UDFs

The loadable function registry is managed by MySQL at the server level. You can inspect registry metadata using an appropriately privileged admin account:

```sql
SELECT name, ret, dl, type
FROM mysql.func
ORDER BY name;
```

Only read the registry for inspection. Never `INSERT`, `UPDATE`, or `DELETE` directly in `mysql.func`; use `CREATE FUNCTION ... SONAME` and `DROP FUNCTION` so MySQL updates state properly.

## 13. Replication and multi-server deployment

### 13.1. Stored functions

Stored functions are schema objects. When deploying via migrations or replication, ensure definitions, definers, and privileges exist consistently across involved servers. With statement-based binary logging, non-deterministic functions or misdeclared characteristics can cause divergent results between source and replica.

Before deploying, check:

- Is the function truly deterministic or dependent on time/state?
- Do declared characteristics accurately match the body?
- Which binary logging mode is active, and what routine-creator checks apply?
- Does the definer exist with matching privileges on all servers that will execute it?
- Does the migration order table creation, function creation, and privilege grants properly?

### 13.2. Loadable UDFs

Registering a UDF on one server does not ensure the shared library is present on other servers. Every node that may execute statements referencing the UDF must have the exact library, version, and compatible loading configuration.

With replication/failover, if a replica is promoted to primary or serves read queries directly, a missing library causes SQL statements invoking the UDF to fail. Include native artifacts and registration steps in node provisioning/deployment workflows rather than running DDL only on the primary.

## 14. Choosing function type by problem

| Requirement | Preferred choice | Reason |
|---|---|---|
| Scalar calculation from parameters without table access | Built-in or stored function | Easy to deploy and manage in SQL |
| SQL logic reused across multiple queries | Stored function or view/CTE depending on output shape | Managed under schema and SQL privileges |
| Returning multiple rows or multi-step workflows | Stored procedure or SQL query | Functions only return scalars |
| Specialized native computation impossible to express cleanly in SQL/app | Loadable UDF after security review | Requires native code inside `mysqld` |
| Calling HTTP APIs, message brokers, or external services | Application/service layer | Avoid turning MySQL Server into an external integration runner |
| Large-scale set-based data processing | Set-based SQL, `JOIN`, aggregates | Avoid per-row function calls |

Do not move logic into a UDF just to save a single round-trip between the application and database. The operational cost and security risk of native libraries usually outweigh that gain.

## 15. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Confusing stored functions with loadable UDFs | Applying wrong privileges and deployment steps | Identify whether the function runs as an SQL routine or native shared library |
| Declaring `DETERMINISTIC` on functions using `NOW()`/`RAND()` | Wrong metadata, binary logging/replication risk | Declare honestly and inspect the body |
| Declaring `NO SQL` when function reads tables | Characteristic misrepresents behavior | Use `READS SQL DATA` or accurate characteristic |
| Using `root` as `DEFINER` | Callers may access overly broad data/privileges through the function | Use a dedicated definer with least privilege |
| Forgetting to grant `EXECUTE` to runtime account | Callers cannot invoke the stored function | Grant routine-level privilege on the exact function |
| Dropping a definer without checking dependent routines | Functions may fail at execution time | Audit `INFORMATION_SCHEMA.ROUTINES` and migrate privileges |
| Using stored functions to return multiple rows | Violates scalar contract | Use procedures/views/queries |
| Function modifies a table also used by the caller statement | Can trigger error 1442 | Separate operations into a procedure or explicit transaction |
| Calling a table-reading function across large row counts | Repeated lookups, slow queries | Rewrite with `JOIN` or set-based processing |
| Installing UDFs from untrusted sources | Native code can crash the server or access the OS | Install only reviewed, signed, and controlled artifacts |
| Installing a UDF only on primary | Failover/replicas may lack the library | Provision and verify every node that may execute it |
| Editing `mysql.func` directly | Inconsistent registry state | Use `CREATE FUNCTION ... SONAME`/`DROP FUNCTION` |

## 16. Stored function review process

Before promoting a stored function to production:

1. Define the contract: parameters, return type, `NULL` behavior, and possible errors.
2. Verify the function is genuinely needed instead of built-ins or inline SQL expressions.
3. Determine whether the function is deterministic or depends on tables/time/state.
4. Declare SQL data access characteristics matching the body.
5. Choose `SQL SECURITY DEFINER` or `INVOKER` based on the authorization model.
6. If using `DEFINER`, create a dedicated account with minimal privileges and clear lifecycle management.
7. Grant `EXECUTE` to the exact runtime principal; avoid broad schema-level grants.
8. Check stored function limits and side effects.
9. Measure impact when invoked over large row sets.
10. Verify binary logging, replication, and definer presence across nodes.
11. Add controlled migrations for creating functions, grants, and rollback scripts.
12. Verify `SHOW CREATE FUNCTION`, `INFORMATION_SCHEMA.ROUTINES`, and `SHOW GRANTS` post-deploy.

## 17. Loadable UDF review process

Before approving a native UDF:

1. Document the technical justification why stored functions/built-ins/app code cannot satisfy the need.
2. Review native source code and dependencies; identify every API the library calls.
3. Audit memory safety, concurrency, `NULL` handling, errors, and input bounds.
4. Build trusted artifacts per OS/architecture/ABI.
5. Lock down write permissions on `plugin_dir` and UDF registration privileges.
6. Test artifacts on staging matching the exact MySQL version.
7. Test load, error paths, and failover; observe impact on the `mysqld` process.
8. Install and register on every node requiring the function.
9. Record owner, library version, checksum, and upgrade/removal procedures.
10. Prepare a rollback plan before production deployment.

## 18. Practice exercises

Perform these in a dedicated MySQL lab; never install untrusted native UDFs on production:

1. Create stored function `line_total` with `DETERMINISTIC`, `NO SQL`, and `SQL SECURITY INVOKER`; invoke it with `SELECT`.
2. Test `NULL` arguments and define the return contract.
3. Create `get_customer_status` using `SELECT ... INTO`; test both matching-row and zero-row cases.
4. Update table data and re-invoke the function; explain why a table-reading function is not deterministic purely from parameters.
5. Inspect `SHOW CREATE FUNCTION` and `INFORMATION_SCHEMA.ROUTINES` to verify characteristics.
6. Create two lab accounts: a definer holding only `SELECT` on one table and an invoker runtime user.
7. Create a `DEFINER` function; grant `EXECUTE` to the runtime user without granting `SELECT` on the base table; verify the caller can invoke the function within its exposed scope.
8. Create an `INVOKER` function; verify the runtime user needs base-table privileges and compare errors when privileges are missing.
9. Revoke `EXECUTE`; verify the caller can no longer invoke the routine.
10. Inspect `SHOW GRANTS` for both definer and runtime user; explain which privileges govern execution inside the body.
11. Inspect `log_bin` and `log_bin_trust_function_creators`; document function creation requirements under the lab configuration.
12. Run `EXPLAIN` on a query calling a function per row; rewrite with `JOIN`/SQL expressions where appropriate and compare.
13. Study `CREATE FUNCTION ... SONAME` syntax and identify the components required for a native UDF to load; do not use untrusted libraries.
14. If your environment includes an approved sample UDF, inspect `plugin_dir`, register it, invoke it, inspect the registry, and remove it with `DROP FUNCTION`.
15. Write a threat model comparing a `DEFINER` stored function against a loadable UDF: database privileges, OS privileges, deployment, and failure domains.
16. Write a deployment runbook for stored functions on source/replica and a distribution runbook for native libraries across nodes.

You complete this lesson when you can explain where the code executes, who grants permissions for the body, who can invoke the function, how functions are deployed, and the primary risk of each type.

## 19. Principles to remember

- Stored functions are SQL routines belonging to a schema; loadable UDFs are native libraries loaded by MySQL Server.
- Both can be called inside SQL expressions, yet they do not share the same privilege or deployment model.
- Stored functions return a scalar value via `RETURN`; procedures suit result sets or multi-step workflows better.
- `DETERMINISTIC` and SQL data access characteristics are declarations; MySQL does not prove the body obeys those labels.
- Functions depending on time, randomness, or mutable table state must not be arbitrarily declared deterministic.
- `SQL SECURITY DEFINER` runs the body with definer privileges; `INVOKER` uses caller privileges.
- Callers need `EXECUTE`; base-table privileges depend on the security context.
- Use dedicated definers and least privilege; never use `root` as definer.
- Stored functions are restricted on transactions, dynamic SQL, result sets, and modifying tables already used by the invoking statement.
- Never rely on the optimizer's call count or evaluation order to trigger side effects.
- Calling a table-reading stored function across millions of rows can cost more than `JOIN`/set-based SQL.
- Loadable UDFs execute inside the `mysqld` process; native code can impact the entire server and process OS privileges.
- Strictly control libraries, plugin directories, installation privileges, artifacts, and cross-node compatibility.
- Never directly edit the UDF registry in system schemas; use supported `CREATE`/`DROP` commands.
- Choose UDFs only when native execution is genuinely necessary and backed by matching security/operations processes.
