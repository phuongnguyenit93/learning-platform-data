# Functions in SQL Expressions and Side-Effect Limits

A stored function is a user-defined routine in MySQL that accepts input parameters and returns a single value. Unlike a stored procedure invoked via `CALL` to execute a workflow, a stored function can appear directly inside SQL expressions, such as in `SELECT`, `WHERE`, `ORDER BY`, or `UPDATE` expressions.

Being able to invoke a function directly inside an SQL statement helps encapsulate calculation formulas and reuse logic. However, a function might read or modify data, depend on time or session state, and be invoked while MySQL processes many rows. Therefore, you must understand the data characteristics, execution privileges, and restrictions of stored functions before placing them into queries.

This lesson falls within the `DATABASE_MYSQL` scope: designing stored functions with clear outputs, using functions inside SQL expressions, distinguishing pure functions from functions with side effects, understanding transaction and table restrictions, controlling `DEFINER`/`INVOKER` privileges, and avoiding performance and replication pitfalls.

## 1. How do stored functions differ from stored procedures?

Both stored functions and stored procedures are stored programs saved in the database. They can contain SQL statements, local variables, conditions, and loops. The main differences lie in how they are called and what they return.

| Criterion | Stored function | Stored procedure |
|---|---|---|
| How it is called | Inside an expression, e.g. `SELECT calculate_tax(...)` | Via `CALL procedure_name(...)` |
| Result | Must return a single value via `RETURN` | Can return data via `OUT`/`INOUT`, result sets, or parameters |
| Parameters | Function parameters are `IN` | Supports `IN`, `OUT`, `INOUT` |
| Where used | Can be used inside SQL expressions in permitted contexts | Cannot place `CALL` directly as a scalar expression |
| Side effects | Can read/write data within permitted limits, but use caution when called from expressions | Better suited for multi-step workflows with intentional side effects |
| Transactions | Cannot self-`COMMIT`/`ROLLBACK` or manage transactions like a procedure | Can coordinate transactions within stored program limits |

Example calling a function:

~~~sql
SELECT calculate_discount(1000.00, 10);
~~~

Example calling a procedure:

~~~sql
CALL recalculate_customer_balance(1001);
~~~

If the goal is computing a value for each row in a query, a function is usually more appropriate. If the goal is running a write workflow, multi-step validation, or returning multiple result sets, a procedure is usually easier to manage.

## 2. CREATE FUNCTION structure

General syntax:

~~~sql
CREATE
    [DEFINER = user]
    FUNCTION function_name ([parameter[,...]])
    RETURNS data_type
    [characteristic ...]
    routine_body
~~~

Components:

- `function_name`: name of the function in the schema.
- Parameters: each parameter has a name and data type; stored function parameters are `IN`.
- `RETURNS`: declares the data type of the return value.
- `characteristic`: describes determinism, data access level, SQL language, and execution security.
- `routine_body`: the function body, either a single statement or a `BEGIN ... END` compound block.

Example function computing the total for a line item:

~~~sql
DELIMITER //

CREATE FUNCTION calculate_line_total(
    p_quantity INT,
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
~~~

`DELIMITER` is a client directive (such as in the `mysql` command-line client) to change the statement terminator when sending definitions containing multiple semicolons. It is not an SQL statement sent to the server and is not stored inside the routine.

A function must return the declared type. At runtime, execution paths must ensure a path reaches `RETURN`. For numeric types, choose appropriate precision and scale to avoid unexpected overflow or rounding.

## 3. Using functions in SELECT expressions

A function returns a scalar, so it can be called in the `SELECT` list:

~~~sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    calculate_line_total(quantity, unit_price) AS line_total
FROM order_item;
~~~

Each result row evaluates the function call with that row's values. Functions can encapsulate calculation formulas reused across multiple queries.

They can be combined with other expressions:

~~~sql
SELECT
    order_item_id,
    calculate_line_total(quantity, unit_price) * 1.08 AS total_with_tax
FROM order_item;
~~~

Give result columns clear aliases. If the function has rounding rules, `NULL` handling, or type conversions, define them clearly inside the function and test with boundary data.

### 3.1. Functions in WHERE

Functions can be used in predicates:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE calculate_discount(total_amount, 10) >= 500;
~~~

This statement is conceptually valid but can be difficult to optimize. When a function takes each row's column as an argument, MySQL may have to evaluate the function for many rows before determining which rows qualify.

When an expression can be transformed into a direct comparison on the column, that form is usually better able to use indexes. For example, if the function simply applies a fixed percentage discount, compute the threshold in the application or as a constant expression:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount >= 555.56;
~~~

Only rewrite expressions after verifying mathematical equivalence across data types, precision, and rounding.

### 3.2. Functions in ORDER BY and GROUP BY

~~~sql
SELECT
    customer_id,
    calculate_customer_score(customer_id) AS score
FROM customer
ORDER BY score DESC;
~~~

Functions can be used in `ORDER BY` to sort by the returned value. However, the function may be computed for many rows and MySQL may require a filesort.

Similarly, functions can appear in `GROUP BY`:

~~~sql
SELECT
    normalize_phone(phone_number) AS normalized_phone,
    COUNT(*) AS customer_count
FROM customer
GROUP BY normalize_phone(phone_number);
~~~

If the function expression is complex and used frequently, consider storing the normalized value or using an appropriate generated column/index. Stored functions do not automatically create indexes on their results; whether an expression can be indexed depends on MySQL's rules for functional indexes and generated columns.

## 4. Functions in INSERT and UPDATE

Stored functions can also supply values for write operations:

~~~sql
INSERT INTO order_summary (
    order_id,
    subtotal,
    tax_amount
)
VALUES (
    1001,
    calculate_subtotal(1001),
    calculate_tax(1001)
);
~~~

Or inside an `UPDATE` expression:

~~~sql
UPDATE order_item
SET line_total = calculate_line_total(quantity, unit_price)
WHERE order_id = 1001;
~~~

Remember that the function is invoked as part of a statement that writes data. Restrictions regarding tables already used by the statement, transactions, and replication still apply.

If the function only computes from parameters, this is usually straightforward. If the function reads multiple tables or writes data, evaluate invocation count, execution order, locks, and side effects before using it in a bulk update statement.

## 5. Functions that read data: READS SQL DATA

A function can query a table to return a value. Example retrieving membership tier by `customer_id`:

~~~sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_tier VARCHAR(20) NOT NULL
) ENGINE = InnoDB;
~~~

Function:

~~~sql
DELIMITER //

CREATE FUNCTION get_customer_tier(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_tier VARCHAR(20) DEFAULT NULL;

    SELECT customer_tier
      INTO v_tier
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_tier;
END//

DELIMITER ;
~~~

Call:

~~~sql
SELECT
    order_id,
    customer_id,
    get_customer_tier(customer_id) AS customer_tier
FROM orders;
~~~

The function uses `SELECT ... INTO` to assign a value to a local variable. It does not emit a result set to the client.

### 5.1. SELECT ... INTO must return at most one row

If `SELECT ... INTO` returns more than one row, MySQL raises an error. The example above is safe because `customer_id` is the `PRIMARY KEY`.

If no row matches, MySQL raises a `NOT FOUND` warning and the target variable keeps its previous value. That is why the example initialized `v_tier` to `NULL`. For more complex logic, declare a `NOT FOUND` handler to handle missing rows:

~~~sql
DECLARE v_tier VARCHAR(20) DEFAULT NULL;
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_tier = NULL;
~~~

Declarations of variables, conditions, cursors, and handlers must obey declaration order in a compound block: variables/conditions before cursors, cursors before handlers, and executable statements last.

### 5.2. Table-reading functions can incur repeated lookup cost

In the query:

~~~sql
SELECT
    order_id,
    get_customer_tier(customer_id)
FROM orders;
~~~

If the query returns 100,000 rows, the function can be invoked many times, each querying `customer_profile`. This is a server-side form of the N+1 query cost.

It can often be written directly as a `JOIN`:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    cp.customer_tier
FROM orders AS o
LEFT JOIN customer_profile AS cp
  ON cp.customer_id = o.customer_id;
~~~

A `JOIN` lets the optimizer see data relationships and choose a holistic access path. Use a table-reading function only when encapsulation is truly needed and call volume has been measured; do not use it as a blanket replacement for `JOIN`.

## 6. Declaring function data characteristics

`CREATE FUNCTION` accepts characteristics describing how the function interacts with data.

| Characteristic | Meaning |
|---|---|
| `NO SQL` | Function contains no SQL statements |
| `CONTAINS SQL` | Function contains SQL but neither reads nor writes data |
| `READS SQL DATA` | Function reads data |
| `MODIFIES SQL DATA` | Function may modify data |
| `DETERMINISTIC` | Declared to yield the same result for identical inputs |
| `NOT DETERMINISTIC` | Result may vary even when inputs are identical |

Example of a pure computation function:

~~~sql
CREATE FUNCTION calculate_vat(
    p_amount DECIMAL(14, 2),
    p_rate DECIMAL(5, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * p_rate / 100, 2);
~~~

Example of a table-reading function:

~~~sql
CREATE FUNCTION lookup_customer_tier(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
RETURN (
    SELECT customer_tier
    FROM customer_profile
    WHERE customer_id = p_customer_id
);
~~~

The second example uses a scalar subquery in `RETURN`. The query must return at most one row; a unique key should guarantee uniqueness. If zero rows match, the result is `NULL`; if multiple rows match, the scalar subquery raises an error.

### 6.1. DETERMINISTIC is a declaration by the author

MySQL does not analyze the entire function body to prove it is genuinely deterministic. The author must declare it honestly.

Do not declare `DETERMINISTIC` for a function that depends on:
- `NOW()`, `CURRENT_TIMESTAMP`, or execution time.
- `RAND()` or random sources.
- `UUID()` or generated values that vary.
- Session variables, user variables, or connection state.
- Table data that can change between invocations.
- External state where identical parameters do not guarantee identical results.

A function computing only `p_amount * p_rate` from parameters can be `DETERMINISTIC`. A function reading current prices from a product table should normally not be declared deterministic if results depend on mutable data.

### 6.2. SQL data access characteristics must also be declared honestly

Characteristics like `READS SQL DATA` and `MODIFIES SQL DATA` describe the routine's data access category. They are not an automatic sandbox preventing a function from performing operations that contradict the declaration.

For example, declaring `READS SQL DATA` does not turn an `UPDATE` statement inside the body into a read-only operation. The author must accurately describe routine contents and test actual privileges.

## 7. What are side effects?

A side effect is a state change outside the function's return value. Examples:
- `INSERT`ing an audit row.
- `UPDATE`-ing a counter.
- Changing table state.
- Recording an access event.
- Modifying session state or interacting with other data.

A pure calculation function taking parameters and returning a result is far easier to use inside SQL expressions. A function with side effects makes calling the function inside queries unpredictable.

Example illustrating a function that writes data:

~~~sql
DELIMITER //

CREATE FUNCTION record_calculation(p_order_id BIGINT UNSIGNED)
RETURNS INT
MODIFIES SQL DATA
SQL SECURITY DEFINER
BEGIN
    INSERT INTO calculation_audit(order_id, recorded_at)
    VALUES (p_order_id, NOW(6));

    RETURN 1;
END//

DELIMITER ;
~~~

This function does not merely compute a value; it also inserts a row into `calculation_audit`. Calling it inside a `SELECT` over multiple rows can trigger side effects many times.

Do not use this kind of function as a "call once per row" mechanism to execute audit-logging workflows. SQL is a declarative language; expression evaluation order and optimizer behavior are not procedural guarantees an application should rely on.

## 8. Why avoid side effects inside SQL expressions?

Suppose:

~~~sql
SELECT
    order_id,
    record_calculation(order_id)
FROM orders
WHERE status = 'PAID';
~~~

The author might expect the function to run exactly once per displayed row. That is an unsafe assumption because:
- The optimizer may change the access plan and how expressions are evaluated.
- Filter predicates may be applied before or during row retrieval.
- Expressions may be evaluated across different intermediate steps.
- An index or plan change can alter how many times the expression is evaluated.
- Client retries can re-execute the entire statement.
- A mid-statement error may cause the statement/transaction to roll back per storage engine rules, whereas external non-database side effects cannot automatically roll back.

For side effects inside the same InnoDB transaction, data changes can commit or roll back with the statement's transaction. However, that neither turns invocation count into a stable guarantee nor makes side effects appropriate for query semantics.

When you need to log audits for updated rows, use an explicit DML workflow, an appropriate trigger, or a transaction-coordinating stored procedure. When you need to send emails or call APIs, use an outbox or application layer after transaction commit; never call external services from a function inside an SQL expression.

## 9. Important limitations of stored functions

Stored functions are more restricted than stored procedures because they are invoked as part of SQL expressions.

Key restrictions to remember:

1. A function must return a single scalar value via `RETURN`.
2. It cannot return result sets directly to the client.
3. It cannot use dynamic SQL via `PREPARE`/`EXECUTE` inside a function.
4. It cannot call stored procedures from inside a function.
5. It cannot execute `START TRANSACTION`, `COMMIT`, or `ROLLBACK` inside a function.
6. It cannot execute statements that cause an implicit commit.
7. It cannot modify a table already being used by the statement invoking the function.
8. Functions cannot be recursive.
9. Function parameters do not support `OUT` or `INOUT` modes.
10. Other prohibited statements are specified in the manual for stored functions and triggers.

### 9.1. Cannot return a result set

Do not write a bare `SELECT` to emit rows to the client:

~~~sql
-- Invalid inside a stored function:
SELECT customer_id, customer_tier
FROM customer_profile;
~~~

Use `SELECT ... INTO` to assign a single value to a local variable:

~~~sql
SELECT customer_tier
INTO v_tier
FROM customer_profile
WHERE customer_id = p_customer_id;
~~~

The function returns the value via `RETURN`:

~~~sql
RETURN v_tier;
~~~

If multiple rows must be returned, use a procedure with a `SELECT` producing a result set or query directly instead of trying to turn a function into a table-returning API.

### 9.2. Cannot use dynamic SQL

Stored functions cannot use SQL prepared statements such as `PREPARE`, `EXECUTE`, and `DEALLOCATE PREPARE`. If you need to build dynamic statements based on table/column names, use a stored procedure or the application layer and validate identifiers via an allowlist.

### 9.3. Cannot call procedures from a function

A function can call other functions within routine rules, but cannot call a stored procedure using `CALL`. If a workflow needs to invoke multiple operations or procedures, place orchestration in a procedure or the application.

### 9.4. Cannot manage transactions inside a function

A function cannot start a transaction, `COMMIT`, or `ROLLBACK`. The transaction belongs to the caller's statement or transaction.

This prevents a function from prematurely ending a transaction that an outer query is participating in. If business logic requires multi-step writes with transaction boundaries, use a procedure or application-managed transaction control.

### 9.5. Cannot modify a table already used by the invoking statement

A stored function or trigger cannot modify a table already being used (for reading or writing) by the statement invoking it. For example, if a statement is running `UPDATE` on `account` and a function called in its expression also tries to `UPDATE` `account`, MySQL can raise error 1442.

Example of a pattern to avoid:

~~~sql
UPDATE account
SET balance = balance + adjust_balance(account_id)
WHERE account_id = 10;
~~~

If `adjust_balance()` also `UPDATE`s `account`, the function is trying to modify a table already used by the outer statement. Place update logic into an explicit statement or coordinating procedure.

### 9.6. No recursion

Stored functions cannot be called recursively. If you need to traverse tree structures or iterate over datasets, consider a recursive CTE, a loop inside a stored procedure, or application logic.

## 10. SQL SECURITY DEFINER and INVOKER

Stored functions can run with the privileges of the definer (`DEFINER`) or the caller (`INVOKER`).

- `SQL SECURITY DEFINER`: the function executes with the privileges of the account specified as definer. This is the default if `SQL SECURITY` is omitted.
- `SQL SECURITY INVOKER`: the function executes with the privileges of the account calling the function.

### 10.1. DEFINER

Example:

~~~sql
CREATE DEFINER = 'routine_owner'@'localhost'
FUNCTION get_public_customer_name(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(150)
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    DECLARE v_name VARCHAR(150);

    SELECT customer_name
      INTO v_name
      FROM customer
     WHERE customer_id = p_customer_id;

    RETURN v_name;
END;
~~~

A caller with `EXECUTE` privilege on the function can invoke it without directly holding `SELECT` on the `customer` table, provided the definer has the required privileges and routine configuration permits it.

This is a useful mechanism to expose a controlled data API, yet also a risk if the function lets users pass parameters to read or alter data beyond permitted scope.

### 10.2. INVOKER

~~~sql
CREATE FUNCTION get_customer_name(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(150)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_name VARCHAR(150);

    SELECT customer_name
      INTO v_name
      FROM customer
     WHERE customer_id = p_customer_id;

    RETURN v_name;
END;
~~~

The caller needs appropriate privileges to read `customer`. `INVOKER` fits when table access privileges should be enforced per calling user.

### 10.3. Security principles

- Use a dedicated, least-privilege account as the definer.
- Avoid using `root` or administrative accounts as the definer.
- Grant `EXECUTE` only to user groups that need to invoke the function.
- Audit functions with `SQL SECURITY DEFINER` and the tables they access.
- Verify the definer still exists and holds required privileges after deployment/migration.
- Never concatenate input strings into dynamic SQL; functions do not support prepared dynamic SQL anyway.
- Do not expose sensitive data merely because the caller has `EXECUTE` privilege.

## 11. Privileges to create, alter, and call stored functions

Commonly involved privileges:
- `CREATE ROUTINE` to create routines.
- `ALTER ROUTINE` to alter or drop routines per granted privileges.
- `EXECUTE` to invoke routines.
- Privileges on objects accessed by the routine, depending on `SQL SECURITY DEFINER`/`INVOKER`.

Inspect definition:

~~~sql
SHOW CREATE FUNCTION get_customer_tier;
~~~

List routines in the schema:

~~~sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
~~~

Grant call privilege:

~~~sql
GRANT EXECUTE
ON FUNCTION app_db.get_customer_tier
TO 'report_user'@'%';
~~~

Account syntax and privilege scope must fit the target environment. Before granting `EXECUTE` on a `DEFINER` function, inspect `SHOW CREATE FUNCTION` and verify the privileges held by the definer.

## 12. Stored functions and binary logging/replication

When binary logging is enabled, MySQL applies additional rules to creating stored functions to prevent routines from causing replicas to compute different results from the source.

In configurations where routine creators are not trusted by default, creating a function may require appropriate administrative privileges and declaring determinism/data-access characteristics per version rules. The `log_bin_trust_function_creators` variable affects how the server enforces these rules.

Check:

~~~sql
SELECT
    @@GLOBAL.log_bin,
    @@GLOBAL.log_bin_trust_function_creators,
    @@GLOBAL.binlog_format;
~~~

### 12.1. Why does DETERMINISTIC matter?

With statement-based replication, replicas re-execute SQL statements. If a function depends on time, randomness, session state, or inconsistent data, results on the replica may diverge from the source.

Row-based replication logs actual row changes into the binary log, reducing reliance on re-evaluating expressions on replicas. However, that is still no reason to misdeclare `DETERMINISTIC` or ignore security and routine-creation privilege requirements.

### 12.2. Do not misdeclare to bypass checks

Never mark a function `DETERMINISTIC` merely to make `CREATE FUNCTION` succeed if actual results depend on mutable state. Misdeclaration can mislead MySQL about routine safety and cause replication divergence.

When designing:
- Pure computation function: `DETERMINISTIC` and `NO SQL` if accurate.
- Read-only table function: `READS SQL DATA`; evaluate determinism based on the data it depends on.
- Data-modifying function: `MODIFIES SQL DATA`; carefully examine replication and side effects.
- Function depending on state outside inputs: typically `NOT DETERMINISTIC`.

Exact privilege requirements and binlog behavior can vary by MySQL version. Check the manual for your deployed server version.

## 13. Performance when calling functions in queries

A stored function can be invoked many times in a single statement. Costs include:
- Routine entry/exit overhead.
- Overhead of executing expressions inside the function body.
- Overhead of reading/writing tables used by the function.
- Locking and constraint-checking costs if DML is present.
- Cost multiplied by row count and expression evaluation frequency.

### 13.1. Pure functions still have overhead

Even a function that just multiplies two numbers incurs routine call overhead compared to an inline SQL expression. If the logic is very simple and used once, writing the expression directly can be clearer and faster.

~~~sql
SELECT quantity * unit_price AS line_total
FROM order_item;
~~~

If the formula is used in many places and needs one unified definition, a function can aid maintainability. Measure performance when queries span millions of rows or run frequently.

### 13.2. Table-reading functions easily cause N lookups

Avoid:

~~~sql
SELECT
    o.order_id,
    get_customer_tier(o.customer_id)
FROM orders AS o;
~~~

when a `JOIN` is possible:

~~~sql
SELECT
    o.order_id,
    cp.customer_tier
FROM orders AS o
LEFT JOIN customer_profile AS cp
  ON cp.customer_id = o.customer_id;
~~~

`JOIN` generally gives the optimizer richer information to choose access paths and join order. A table-reading function can perform repeated lookups, scaling cost linearly with row count.

### 13.3. Functions on columns in WHERE can block indexes

Example:

~~~sql
SELECT order_id
FROM orders
WHERE normalize_code(order_code) = 'ABC';
~~~

When a function wraps a column, a standard index on `order_code` normally cannot be used directly like a sargable predicate on the raw column value.

If you can normalize the input before querying:

~~~sql
SELECT order_id
FROM orders
WHERE order_code = 'ABC';
~~~

If normalization logic must live in the database, consider a generated column or functional index within MySQL's supported rules; do not assume any arbitrary stored function can be used directly as an index expression.

### 13.4. Measure with EXPLAIN and EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT
    order_id,
    calculate_line_total(quantity, unit_price)
FROM order_item
WHERE order_id >= 100000;
~~~

On MySQL 8.0.18 and later:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    calculate_line_total(quantity, unit_price)
FROM order_item
WHERE order_id >= 100000;
~~~

`EXPLAIN ANALYZE` executes the `SELECT`. Compare timings, row counts, and iterators; when comparing a function against a direct expression, use identical data, identical predicates, and multiple runs under equivalent conditions.

## 14. NULLs, data types, and errors in functions

A function must have an explicit contract for inputs and outputs.

### 14.1. NULL propagation

In MySQL, multiplying with `NULL` normally returns `NULL`:

~~~sql
SELECT calculate_line_total(2, NULL);
~~~

The result will be `NULL` if the function simply executes `RETURN p_quantity * p_unit_price`.

If business logic treats a `NULL` price as `0`, state that explicitly:

~~~sql
RETURN p_quantity * COALESCE(p_unit_price, 0);
~~~

Do not silently convert `NULL` to `0` if `NULL` means unknown or missing data.

### 14.2. Precision and scale

If `RETURNS DECIMAL(14,2)`, verify:
- Maximum input values.
- Intermediate multiplications/additions.
- `ROUND` rules.
- Negative values or invalid quantities.
- Type conversion upon return.

Do not use `FLOAT`/`DOUBLE` for money if business rules require exact decimal arithmetic.

### 14.3. SIGNAL to raise business errors

A function can intentionally raise errors using `SIGNAL` where appropriate:

~~~sql
IF p_quantity < 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Quantity must not be negative';
END IF;
~~~

`SIGNAL` halts routine execution and returns the error to the caller. Use it only to validate input conditions the function is truly responsible for; do not turn a function into a workflow with many side effects and many error branches.

## 15. Altering and dropping functions

Inspect definition:

~~~sql
SHOW CREATE FUNCTION calculate_line_total;
~~~

Drop function:

~~~sql
DROP FUNCTION IF EXISTS calculate_line_total;
~~~

MySQL supports `ALTER FUNCTION` to modify certain routine characteristics, but `ALTER FUNCTION` cannot alter the SQL body the way you edit an `UPDATE` statement. When the body needs changes, you normally must `DROP` and re-`CREATE` it or deploy via an appropriate migration process.

Before changing a function currently called by applications:
- Check dependent queries and routines.
- Confirm parameter signatures and return type.
- Verify `EXECUTE` privileges and `DEFINER`.
- Plan deployment compatibility.
- Prepare a way to restore the old definition.

Do not drop an actively used function without first identifying application dependencies.

## 16. When to use a function, a procedure, or a JOIN?

| Problem | Typical suitable choice | Reason |
|---|---|---|
| Compute a single value from parameters | Stored function | Can be used directly inside expressions |
| Normalize or transform a value | Pure function or SQL expression | Easy-to-test output, minimal side effects |
| Read attributes from a related table across many rows | `JOIN` | Optimizer sees relationships and can optimize the whole query |
| Update multiple tables in a workflow | Procedure or application-managed transaction | Clear orchestration of steps and errors |
| Return multiple rows or multiple result sets | Direct `SELECT` or procedure | Functions only return scalars |
| Record audit for a specific operation | Trigger or intentional DML/procedure | Ties side effects clearly to write events |
| Call APIs, send emails, or external operations | Application layer / outbox | Controls retries and external side effects cleanly |

A good function has clear inputs, outputs, and data characteristics. If you find yourself adding multiple side effects to make it useful, reconsider whether a procedure or application logic fits better.

## 17. Safe stored function design process

1. Determine whether the function needs to return a scalar value or perform a workflow.
2. Choose a `RETURNS` type with sufficient precision and proper `NULL` semantics.
3. Declare `IN` parameters with matching data types.
4. Determine whether the function reads or modifies data.
5. Declare `DETERMINISTIC`/`NOT DETERMINISTIC` honestly.
6. Declare `NO SQL`, `READS SQL DATA`, or `MODIFIES SQL DATA` accurately.
7. Choose `SQL SECURITY DEFINER` or `INVOKER` per the authorization model.
8. Verify the function does not use dynamic SQL, `CALL` procedures, transaction control, or result sets.
9. Verify it does not modify a table already used by the invoking statement.
10. Evaluate invocation frequency when placed in `SELECT`/`WHERE`/`ORDER BY`.
11. Compare against `JOIN` or inline expressions if the function reads tables or processes many rows.
12. Check binary logging and replication impact.
13. Grant minimal `CREATE ROUTINE`/`EXECUTE` privileges.
14. Test `NULL`s, boundary values, zero rows, multiple rows, and business errors.
15. Measure with `EXPLAIN`/`EXPLAIN ANALYZE` on representative workloads.
16. Deploy changes via controlled migrations and verify the definition post-deploy.

## 18. Common mistakes

| Error or misconception | Cause | How to handle |
|---|---|---|
| Function lacks `RETURN` on a branch | Function must return a value matching `RETURNS` | Ensure every valid path reaches `RETURN` |
| `SELECT` inside a function returns a result set | Functions cannot emit result sets to clients | Use `SELECT ... INTO` or scalar `RETURN` |
| `SELECT ... INTO` returns multiple rows | Query does not guarantee uniqueness | Use `PRIMARY KEY`/`UNIQUE` or clear logical bounds |
| Function called millions of times | Function placed in per-row expression | Measure and consider `JOIN` or precomputation |
| Function in `WHERE` skips index | Wrapping column makes predicate non-sargable | Write direct predicate or use suitable index structure |
| Incorrect `DETERMINISTIC` declaration | Result depends on time, tables, or session | Declare true nature and verify replication |
| `READS SQL DATA` but body runs `UPDATE` | Misdeclared characteristic; not a sandbox | Fix characteristic and audit behavior |
| Function writes to table used by caller statement | Violates routine/trigger table restriction | Move logic into separate statement or procedure |
| Calling a procedure from a function | `CALL procedure` is prohibited inside functions | Move orchestration to procedure/caller |
| `COMMIT` inside a function | Functions cannot manage transactions | Let caller manage the transaction |
| `DEFINER` function exposes overly broad access | Callers indirectly leverage definer privileges | Use least-privilege definer and audit `EXECUTE` |
| Replication produces different results | Non-deterministic function or misdeclared attributes | Check binlog format, routine characteristics, and data |
| Relying on side effects inside `SELECT` | Evaluation count/order is not a procedural contract | Use explicit DML/procedure/outbox |
| Routine missing after deploy | Wrong schema, privileges, or definer | Run `SHOW CREATE FUNCTION` and check `INFORMATION_SCHEMA` |

## 19. Practice exercises

### Exercise 1: Pure function

Create `calculate_line_total(quantity, unit_price)` returning `DECIMAL`. Test positive numbers, `0`, `NULL`, negative quantities, and large values. Decide whether the function should `SIGNAL` on negative quantity.

### Exercise 2: Function in SELECT

Use the function to compute line totals for the `order_item` table. Compare results against a direct `quantity * unit_price` expression. Check accuracy and execution time on a large dataset.

### Exercise 3: Function in WHERE

Create a function that normalizes order codes and use it in `WHERE`. Compare `EXPLAIN` output against a direct column comparison after normalizing the parameter beforehand. Explain the index impact.

### Exercise 4: Table-reading function

Create `get_customer_tier(customer_id)` using `SELECT ... INTO`. Test one-row, zero-row, and multi-row cases. Then rewrite the query using a `JOIN` and compare.

### Exercise 5: SQL SECURITY

Create one table-reading function with `SQL SECURITY DEFINER` and one with `SQL SECURITY INVOKER`. Use a test user holding only `EXECUTE` to verify the difference. Do not use `root` as definer.

### Exercise 6: Determinism characteristic

Create one function computing solely from parameters and one depending on table data. Declare appropriate characteristics and explain why parameter signatures alone cannot determine determinism.

### Exercise 7: Side effects

Create an audit-logging function in a lab environment. Call it from `SELECT` over multiple rows and observe audit row counts. Try changing the predicate or query plan; note why invocation count must not be treated as a business guarantee. Then move auditing to explicit DML or an appropriate trigger.

### Exercise 8: Function restrictions

Attempt to place `PREPARE`, `CALL procedure`, `COMMIT`, and a bare `SELECT` inside a function. Record server errors returned and map them to stored function limitations.

### Exercise 9: Replication characteristics

Inspect `log_bin`, `binlog_format`, and `log_bin_trust_function_creators` in a test environment. Create functions with different characteristics and observe server privilege/declaration requirements on your version.

### Exercise 10: Performance comparison

Use `EXPLAIN ANALYZE` to compare:
- A pure computation function in `SELECT`.
- A direct SQL expression.
- A table-reading function called per row.
- A direct `JOIN` to the table read by the function.

Record row counts, timings, and plans.

## 20. Checklist before deploying a function to an application

- [ ] Function genuinely needs to return a scalar value.
- [ ] Every execution path returns a value matching `RETURNS`.
- [ ] Parameters are `IN` with appropriate data types.
- [ ] `NULL`, precision, scale, and rounding are explicitly defined.
- [ ] `SELECT ... INTO` guarantees at most one row.
- [ ] Does not emit a result set directly.
- [ ] Does not use `PREPARE`/`EXECUTE` or `CALL` procedures.
- [ ] Does not use `START TRANSACTION`, `COMMIT`, `ROLLBACK`, or DDL causing implicit commits.
- [ ] Does not modify a table already used by the invoking statement.
- [ ] Does not rely on expression evaluation order or count to perform side effects.
- [ ] `DETERMINISTIC`/`NOT DETERMINISTIC` reflects actual logic.
- [ ] SQL data access characteristic accurately reflects contents.
- [ ] `SQL SECURITY DEFINER`/`INVOKER` is chosen per least privilege.
- [ ] Definer exists and holds exact required privileges.
- [ ] `CREATE ROUTINE` and `EXECUTE` privileges are granted under control.
- [ ] Binary logging and replication have been reviewed.
- [ ] Compared against `JOIN` or direct expressions where applicable.
- [ ] Measured with `EXPLAIN`/`EXPLAIN ANALYZE` on representative data.
- [ ] Tested `NULL`, zero rows, multiple rows, and business error cases.

## 21. Conclusion

A stored function is a routine that returns a single value and can be invoked inside SQL expressions. It is well suited for encapsulating calculations or scalar-returning logic with clear inputs and outputs. When a function reads tables, consider `JOIN` to avoid repeated per-row lookups. When a function has side effects, never place it inside `SELECT`/`WHERE` as a workflow control mechanism because the optimizer makes no promise on expression evaluation order or count.

Declare `DETERMINISTIC` and SQL data access characteristics accurately, choose `SQL SECURITY` per least privilege, and respect restrictions on result sets, dynamic SQL, transactions, procedure calls, and modifying tables already used by the invoking statement. For multi-step logic or intentional data writes, procedures, explicit DML, appropriate triggers, or the application layer generally provide clearer transaction and retry control.

## Official references

- [MySQL 8.4 Reference Manual – CREATE FUNCTION Statement](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual – Stored Programs Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html)
- [MySQL 8.4 Reference Manual – Stored Function Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual – Stored Program Binary Logging](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-logging.html)
- [MySQL 8.4 Reference Manual – Stored Object Access Control](https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html)
- [MySQL 8.4 Reference Manual – Stored Routine Privileges](https://dev.mysql.com/doc/refman/8.4/en/stored-routines-privileges.html)
- [MySQL 8.4 Reference Manual – SHOW CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/show-create-function.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA ROUTINES](https://dev.mysql.com/doc/refman/8.4/en/information-schema-routines-table.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
