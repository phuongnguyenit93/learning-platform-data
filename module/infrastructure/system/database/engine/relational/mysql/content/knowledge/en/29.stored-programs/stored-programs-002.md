# CREATE PROCEDURE, CREATE FUNCTION, and How to Call Them

A stored program is SQL code defined and stored in MySQL so it can be invoked repeatedly. The two commonly used routine types are **stored procedure** and **stored function**. A procedure is invoked with `CALL`, can accept `IN`, `OUT`, and `INOUT` parameters, and can return result sets. A function returns a value via `RETURN` and can be used in SQL expressions like built-in functions.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while practicing execution plan analysis, query tuning, privilege management, backups, and handling relational database operational issues. Within the **Stored program** chapter, this lesson focuses on `CREATE PROCEDURE`, `CREATE FUNCTION`, and how to invoke them. `SPECIAL_NOTE` is provided empty, so there are no additional special constraints for this lesson.

## 1. Stored procedures and stored functions

Procedures and functions are both stored in a database schema and can contain multiple SQL statements. The biggest difference lies in how they are called and what they return:

| Criterion | Stored procedure | Stored function |
|---|---|---|
| Created with | `CREATE PROCEDURE` | `CREATE FUNCTION` |
| How it is called | `CALL schema.procedure(...)` | Used inside expressions, e.g. `SELECT function(...)` |
| Return value | Can return via `OUT`/`INOUT` and result sets | Must return a single value using `RETURN` |
| Parameters | `IN`, `OUT`, `INOUT` | Input parameters only; `OUT`/`INOUT` modes cannot be declared |
| Use in SELECT/WHERE | Cannot call a procedure as an expression | Can use a function inside SQL expressions |
| Result set | Can emit result sets using regular `SELECT` | Cannot return result sets directly |
| Transaction control | Can use transaction statements inside a procedure, depending on call context | Cannot explicitly control transactions |
| Typical purpose | Perform a multi-step action/business workflow | Compute a value or return a reusable scalar result |

Do not treat a function as a shorthand procedure. Allowing functions inside SQL expressions causes MySQL to impose additional restrictions and side-effect rules on functions.

## 2. Where are stored routines stored and executed?

Routines are created inside a schema:

```sql
USE shop_db;

DELIMITER $$

CREATE PROCEDURE get_open_orders()
BEGIN
    SELECT order_id, customer_id, order_date
    FROM orders
    WHERE status = 'OPEN';
END$$

DELIMITER ;
```

MySQL stores the routine definition in server metadata. When a client calls the routine, the server executes the routine body under the configured security context and privileges. The application does not need to resend the full body of inner statements on every call.

A routine name can be qualified with its schema to avoid relying on the default schema:

```sql
CALL shop_db.get_open_orders();
```

`USE shop_db` only changes the session's default schema. It does not create a database and does not grant privileges to an account.

## 3. CREATE PROCEDURE syntax

General structure:

```sql
CREATE [DEFINER = user]
PROCEDURE procedure_name ([parameter_list])
[characteristic ...]
routine_body
```

A procedure parameter takes the form:

```sql
[IN | OUT | INOUT] parameter_name data_type
```

If no mode is specified, the default is `IN`.

The procedure body can be a single statement or a compound `BEGIN ... END` statement containing multiple statements. When the body has multiple statements, command-line clients must change the delimiter so inner semicolons are not interpreted as ending the entire `CREATE PROCEDURE` statement.

## 4. DELIMITER in MySQL clients

Example creating a procedure with multiple statements:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_orders(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

`DELIMITER` is a directive for certain clients such as the MySQL command-line client; it is not an SQL statement sent to the server and is not stored in the routine body. Its purpose is to tell the client to use `$$` as the statement terminator while entering the definition. After creating the routine, change the delimiter back to `;`.

In MySQL Workbench or migration tools, how statement delimiters are configured may differ. Follow the script separator syntax of the tool you are using.

## 5. IN parameters

`IN` passes data from the caller into the procedure. The procedure can read the parameter value for filtering or calculation; reassigning an `IN` parameter does not pass the new value back to the caller.

Example fetching orders by customer:

```sql
DELIMITER $$

CREATE PROCEDURE get_orders_by_customer(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

Calling the procedure:

```sql
CALL get_orders_by_customer(1001);
```

The value `1001` is passed into `p_customer_id`. The procedure executes the `SELECT` statement and returns the result set to the client.

## 6. OUT parameters

`OUT` allows a procedure to write a value back to the caller. The initial value of the argument passed in is not used as input to the procedure; the procedure must assign a value to the `OUT` parameter before returning.

Example counting a customer's orders:

```sql
DELIMITER $$

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT,
    OUT p_order_count INT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;
```

Calling the procedure with a user-defined variable:

```sql
CALL count_customer_orders(1001, @order_count);

SELECT @order_count AS order_count;
```

`@order_count` is a user-defined session variable. The `OUT` value is assigned to this variable so the caller can read it after the `CALL` statement. User-defined variables exist within the current session; another session cannot see this variable automatically.

### 6.1. OUT and SELECT ... INTO

`SELECT ... INTO` stores a query's result into local variables or `OUT` parameters instead of sending a result set to the client:

```sql
SELECT COUNT(*)
INTO p_order_count
FROM orders
WHERE customer_id = p_customer_id;
```

`COUNT(*)` always returns one row, even when no matching orders exist, in which case the result is 0. For a non-aggregate query, if no rows match, `SELECT ... INTO` raises a NOT FOUND condition and the target variable retains its previous value; if more than one row matches, an error occurs. Design the query so the returned row count matches expectations.

## 7. INOUT parameters

`INOUT` both receives an initial value from the caller and returns the value updated by the procedure.

Example capping a discount rate and calculating the discount amount:

```sql
DELIMITER $$

CREATE PROCEDURE calculate_discount(
    IN p_order_id BIGINT,
    INOUT p_discount_rate DECIMAL(5, 4),
    OUT p_discount_amount DECIMAL(12, 2)
)
BEGIN
    DECLARE v_total_amount DECIMAL(12, 2) DEFAULT 0;

    SET p_discount_rate = LEAST(
        GREATEST(p_discount_rate, 0),
        0.2500
    );

    SELECT total_amount
    INTO v_total_amount
    FROM orders
    WHERE order_id = p_order_id;

    SET p_discount_amount = ROUND(
        v_total_amount * p_discount_rate,
        2
    );
END$$

DELIMITER ;
```

Calling the procedure:

```sql
SET @rate = 0.3000;
SET @discount_amount = 0;

CALL calculate_discount(
    5001,
    @rate,
    @discount_amount
);

SELECT
    @rate AS applied_rate,
    @discount_amount AS discount_amount;
```

If the passed rate is `0.3000`, the procedure clamps it to `0.2500` and returns the updated rate and discount amount. This example assumes `order_id` exists; in production routines, handle missing orders and validate business rules.

## 8. Local variables in routines

Local variables are declared with `DECLARE` inside a `BEGIN ... END` block. A variable's scope is limited to the block in which it is declared:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_order_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(14, 2)
)
BEGIN
    DECLARE v_total DECIMAL(14, 2) DEFAULT 0;

    SELECT COALESCE(SUM(total_amount), 0)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    SET p_total = v_total;
END$$

DELIMITER ;

CALL get_customer_order_total(1001, @total);
SELECT @total AS total_amount;
```

Rules to remember:

- Declare local variables using `DECLARE` at the start of the block, before executable statements.
- Local variables must have a data type; an optional default value can be specified with `DEFAULT`.
- Assign values using `SET` or `SELECT ... INTO`.
- Local variables do not use the `@` prefix; `@` is reserved for user-defined session variables.
- Variables in an inner block have their own scope and can shadow same-named variables in outer blocks; use clear prefixes in naming to avoid confusion.

Stored programs support several other declaration types such as conditions, cursors, and handlers. Their declaration order follows specific rules; the lessons on control flow, cursors, and error handling cover these in detail.

## 9. CREATE FUNCTION syntax

A function must declare its return data type using `RETURNS`:

```sql
CREATE [DEFINER = user]
FUNCTION function_name ([parameter_list])
RETURNS data_type
[characteristic ...]
routine_body
```

Unlike procedures, function parameters do not have `IN`, `OUT`, or `INOUT` modes. Function parameters serve as inputs. A function must return a value using a `RETURN expression` statement on every possible execution path.

## 10. Computation function without table access

Example function calculating tax from an amount and rate:

```sql
DELIMITER $$

CREATE FUNCTION calculate_tax(
    p_net_amount DECIMAL(12, 2),
    p_tax_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_net_amount * p_tax_rate, 2)$$

DELIMITER ;
```

Calling the function:

```sql
SELECT calculate_tax(1000000, 0.1000) AS tax_amount;

SET @tax = calculate_tax(2500000, 0.0800);
SELECT @tax;
```

The function returns a scalar value, so it can be used inside expressions:

```sql
SELECT
    order_id,
    total_amount,
    calculate_tax(total_amount, 0.1000) AS estimated_tax
FROM orders
WHERE status = 'PAID';
```

When a function appears in a multi-row query, the server may need to evaluate the function for many rows. Avoid placing costly routines in per-row expressions if a JOIN, direct SQL expression, or set-based calculation can solve the problem better.

## 11. Function reading data from a table

A function can read data and return a single value. Example fetching total order amount by customer:

```sql
DELIMITER $$

CREATE FUNCTION customer_order_total(
    p_customer_id BIGINT
)
RETURNS DECIMAL(14, 2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(14, 2) DEFAULT 0;

    SELECT COALESCE(SUM(total_amount), 0)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    RETURN v_total;
END$$

DELIMITER ;
```

Calling the function:

```sql
SELECT customer_order_total(1001) AS total_spent;

SELECT
    customer_id,
    customer_order_total(customer_id) AS total_spent
FROM customers;
```

This function reads the `orders` table, so its result depends on the data at execution time. The same argument can yield different results as orders are inserted, updated, or deleted; therefore declaring `NOT DETERMINISTIC` is appropriate for this example.

The second query illustrates calling the function in the column list. With a large customer set, calling a function per row can trigger many lookups; consider a direct aggregate and JOIN query so the optimizer can process it in a set-based manner.

## 12. RETURN and return data types

`RETURNS data_type` specifies the data type of the function result. The return type should match the business value domain:

| Result | Data types to consider |
|---|---|
| Record count | `INT` or `BIGINT` |
| Money, tax, conversion rate | `DECIMAL(p,s)` |
| Score, factor, ratio | `DECIMAL` or suitable numeric type |
| Coded status | `TINYINT` or standardized numeric/code type |
| Identifier/label string | `VARCHAR(n)` |
| Point in time | `DATE`, `DATETIME`, or `TIMESTAMP` depending on semantics |

Example function returning a numeric status:

```sql
DELIMITER $$

CREATE FUNCTION is_large_order(
    p_total_amount DECIMAL(14, 2)
)
RETURNS TINYINT
DETERMINISTIC
NO SQL
RETURN IF(p_total_amount >= 100000000, 1, 0)$$

DELIMITER ;

SELECT
    order_id,
    is_large_order(total_amount) AS is_large
FROM orders;
```

`RETURN` terminates the function and returns the expression value. Do not confuse `RETURN` with a procedure's `OUT` parameter. A function cannot have multiple output parameters the way a procedure can; if multiple independent outputs are needed, consider a procedure with multiple `OUT` parameters or an appropriate data structure.

## 13. Routine characteristics

MySQL allows declaring characteristics that describe a routine:

| Characteristic | Meaning |
|---|---|
| `DETERMINISTIC` | Declares that the routine produces the same result for the same inputs under the same relevant conditions. |
| `NOT DETERMINISTIC` | Declares that the result may vary even with identical inputs. |
| `NO SQL` | Declares that the routine contains no SQL statements. |
| `CONTAINS SQL` | The routine contains SQL but neither reads nor writes data per this classification. |
| `READS SQL DATA` | The routine reads SQL data. |
| `MODIFIES SQL DATA` | The routine may modify SQL data. |
| `SQL SECURITY DEFINER` | Executes under the security context of the definer. |
| `SQL SECURITY INVOKER` | Executes under the security context of the caller. |
| `COMMENT '...'` | Attaches a description to the routine. |

Data-access characteristics serve as declarations to the server and administration tools. They do not replace reviewing the actual statements in the body; in particular, `DETERMINISTIC` is a declaration made by the routine author, and MySQL does not analyze the entire logic to prove the routine is truly deterministic.

### 13.1. DETERMINISTIC and NOT DETERMINISTIC

A pure computation function based on parameters:

```sql
CREATE FUNCTION add_service_fee(
    p_amount DECIMAL(12, 2),
    p_fee_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * (1 + p_fee_rate), 2);
```

For the same two inputs, the calculation always yields the same result; `DETERMINISTIC` is appropriate.

Conversely, a function using the current time or reading a mutable table:

```sql
DELIMITER $$

CREATE FUNCTION current_open_order_count()
RETURNS BIGINT
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_count BIGINT DEFAULT 0;

    SELECT COUNT(*)
    INTO v_count
    FROM orders
    WHERE status = 'OPEN';

    RETURN v_count;
END$$

DELIMITER ;
```

This example illustrates instability over time and data. Calling the same function can yield different results at different times because the `orders` table may change.

### 13.2. SQL data access characteristics

- Function performing only calculations on parameters without reading/writing tables: typically declare `NO SQL`.
- Routine containing SQL statements that do not access data: `CONTAINS SQL`.
- Function reading tables: `READS SQL DATA`.
- Procedure or function performing data-modifying operations where permitted: `MODIFIES SQL DATA`.

Do not declare `NO SQL` for a routine that actually reads tables. Do not declare `DETERMINISTIC` merely to bypass function creation checks; accurately reflect actual behavior and replication policies.

## 14. Stored function limitations

Functions can be invoked from an SQL expression that is reading or modifying data. Therefore, MySQL imposes restrictions to prevent a routine from altering how the outer statement operates:

- Functions cannot return result sets directly. `SELECT ... INTO` may be used to store data into local variables.
- Functions cannot use explicit transaction control statements such as `START TRANSACTION`, `COMMIT`, or `ROLLBACK`.
- Functions cannot use dynamic SQL prepared statements via `PREPARE`/`EXECUTE`.
- Functions cannot modify a table already being used by the statement invoking the function. For example, calling a function from `UPDATE orders ...` and having the function update `orders` again hits this restriction.
- Functions must return a single value via `RETURN`; `OUT`/`INOUT` parameters cannot be used to return multiple values.

These limitations differ from procedures. A procedure can emit result sets and contain transaction statements, though committing/rolling back inside a procedure affects the transaction opened by the caller. Agree clearly on which component owns the transaction.

### 14.1. SELECT ... INTO is allowed, SELECT returning a result set is not

Inside a function, the proper way to read data is:

```sql
BEGIN
    DECLARE v_customer_name VARCHAR(150) DEFAULT NULL;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_customer_name;
END
```

This is the body inside a function taking parameter `p_customer_id` and returning `VARCHAR(150)`. For the case where no row is found, the routine should have an appropriate NOT FOUND handling policy per business requirements.

Do not write a `SELECT customer_name FROM customers ...` statement to emit a result set from a function. If business requirements need multiple rows returned, use a procedure or a direct `SELECT` query.

### 14.2. Do not use functions to hide side effects in SELECT

Avoid designing a function called inside `SELECT` that silently performs updates, sends notifications, or alters business state. Aside from MySQL's restrictions, this practice makes a query's impact hard to predict, hard to benchmark, and unsafe to retry.

Use a procedure for operations with explicit side effects, such as creating orders, recording payments, or updating statuses. Use functions for calculated values with clear input/output contracts.

## 15. Procedures can return result sets and OUT parameters together

A procedure can return one or more result sets via regular `SELECT` statements while also returning data via `OUT`:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_summary(
    IN p_customer_id BIGINT,
    OUT p_order_count INT,
    OUT p_total_spent DECIMAL(14, 2)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO
        p_order_count,
        p_total_spent
    FROM orders
    WHERE customer_id = p_customer_id;

    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

Calling the procedure:

```sql
CALL get_customer_summary(
    1001,
    @order_count,
    @total_spent
);

SELECT
    @order_count AS order_count,
    @total_spent AS total_spent;
```

The client receives the order result set from the second `SELECT` statement and can also read the two output variables. With application drivers, all result sets returned by the procedure must be consumed before reusing the connection; the exact API depends on the driver.

## 16. Choosing PROCEDURE or FUNCTION?

| Question | Choose procedure when... | Choose function when... |
|---|---|---|
| Primary goal | Performing an action or multi-step workflow | Computing and returning a single value |
| How it is called | Caller explicitly runs `CALL` | Need to embed the result inside `SELECT` or an expression |
| Number of outputs | Need multiple `OUT`/`INOUT` values or multiple result sets | Need a single scalar value |
| Data modification | Need intentional DML operations | Only appropriate when compatible with function limits and data contract |
| Transactions | Can coordinate transactions by design | No explicit transaction control |
| Reading multiple rows | Can return result sets | Cannot return result sets directly |
| Use in WHERE/SELECT | Cannot be called directly as an expression | Can be called like an SQL function |

Examples for choosing a procedure:

- Creating an order, inserting line items, and writing an audit record.
- Running a multi-table update workflow.
- Returning a list of records along with summary statistics via `OUT`.
- Performing an administrative task granted via `EXECUTE` privilege.

Examples for choosing a function:

- Computing tax from an amount and rate.
- Normalizing or classifying an input code.
- Returning a scalar aggregate when query cost and limits are controlled.

If only a single query is needed, wrapping it in a routine is not always necessary. A routine adds value when it establishes a clear reusable contract, consolidates shared logic, or provides an appropriate privilege boundary.

## 17. SQL SECURITY and DEFINER

Stored procedures and stored functions have a security context. Two main options:

- `SQL SECURITY DEFINER`: the routine runs with the privileges of the definer account attached to the routine. This is the default if unspecified.
- `SQL SECURITY INVOKER`: the routine runs with the privileges of the account calling the routine.

Example procedure using definer privileges:

```sql
DELIMITER $$

CREATE
    DEFINER = 'routine_owner'@'localhost'
    SQL SECURITY DEFINER
PROCEDURE get_sensitive_customer_summary(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE customer_id = p_customer_id
    GROUP BY customer_id;
END$$

DELIMITER ;
```

An application account can be granted `EXECUTE` privilege on the procedure without direct read privileges on all underlying tables, provided the security model and definer privileges are designed properly.

### 17.1. When to use DEFINER or INVOKER?

**DEFINER** fits when the routine is designed as a restricted database API. The caller can only perform actions permitted by the routine. Protect the definer account, keep its privileges minimal, and manage account lifecycle carefully.

**INVOKER** fits when access to underlying tables should still depend on the caller account. The caller needs the required privileges on objects accessed by the routine.

Do not use `DEFINER` to bypass authorization procedures. A routine with overly broad definer privileges can become a privilege escalation path if inputs are not validated or the routine permits unintended actions.

## 18. Privileges to create, alter, and call routines

Common privileges:

| Privilege | Purpose |
|---|---|
| `CREATE ROUTINE` | Create stored procedures or stored functions in the granted schema. |
| `ALTER ROUTINE` | Alter characteristics or drop routines per granted privileges. |
| `EXECUTE` | Invoke the routine. |
| Privileges on base tables | Required when running under caller privileges (`INVOKER`); with `DEFINER`, the definer must hold the required privileges. |

Example privilege grants:

```sql
GRANT CREATE ROUTINE
ON shop_db.*
TO 'routine_developer'@'localhost';

GRANT EXECUTE
ON PROCEDURE shop_db.get_customer_orders
TO 'shop_app'@'localhost';

GRANT EXECUTE
ON FUNCTION shop_db.calculate_tax
TO 'shop_app'@'localhost';
```

Check privileges of the current account:

```sql
SHOW GRANTS;
```

Do not grant `CREATE ROUTINE` to a runtime application account if the application only needs to invoke routines. Separate migration/deployment accounts from application accounts and grant only required privileges.

### 18.1. Privileges with DEFINER and INVOKER

With `SQL SECURITY DEFINER`, MySQL checks object access privileges against the definer's security context when the routine runs. The caller still needs `EXECUTE` privilege on the routine. With `SQL SECURITY INVOKER`, object access privileges are checked against the caller; having `EXECUTE` alone may not be enough to read/write base tables.

The definer account must exist and hold the exact privileges required by the routine. If the definer account is dropped or loses privileges, the routine may fail at runtime. Manage definers as part of database deployment and lifecycle.

### 18.2. Binary logging and stored functions

When binary logging is enabled, creating stored functions may be subject to extra privilege and characteristic declaration requirements to ensure replication safety. The `log_bin_trust_function_creators` setting affects how the server enforces these rules.

You can check the settings:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_trust_function_creators';
```

Do not enable the trust setting merely to suppress function creation errors. Review replication policies, creator account privileges, and the accuracy of `DETERMINISTIC`/SQL data access characteristics for your server version.

## 19. Inspecting and managing routines

### 19.1. Viewing procedure/function definitions

```sql
SHOW CREATE PROCEDURE get_customer_orders;
SHOW CREATE FUNCTION calculate_tax;
```

Both statements return the stored definition along with characteristics and relevant security context details.

### 19.2. Listing routines in a schema

```sql
SHOW PROCEDURE STATUS
WHERE Db = 'shop_db';

SHOW FUNCTION STATUS
WHERE Db = 'shop_db';
```

Or query `INFORMATION_SCHEMA.ROUTINES`:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop_db'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

`ROUTINE_TYPE` distinguishes `PROCEDURE` and `FUNCTION`. `DATA_TYPE` describes the function's return type; procedures do not have a scalar return type like functions.

### 19.3. ALTER and DROP

`ALTER PROCEDURE`/`ALTER FUNCTION` is used to modify certain routine characteristics; it cannot rewrite the entire body or parameter list. When the body needs changes, the routine definition typically must be redeployed via a controlled drop/create process.

Dropping a routine:

```sql
DROP PROCEDURE IF EXISTS shop_db.get_customer_orders;
DROP FUNCTION IF EXISTS shop_db.calculate_tax;
```

Before dropping or recreating, identify callers, granted privileges, definer, dependencies, and deployment timing. If drop and create are separated, there can be a window where the application fails to invoke the routine.

## 20. Transactions when calling a procedure

A procedure can contain multiple DML statements. If business requirements dictate that the steps must succeed or fail together, define a clear transaction boundary.

A common design lets the application/caller manage the transaction. For example, assuming procedure `create_order_for_customer` has already been created:

```sql
START TRANSACTION;

CALL create_order_for_customer(
    1001,
    '2026-11-19'
);

COMMIT;
```

If the procedure raises an error, the caller must handle the error and roll back according to the designed transaction contract. The lessons on handlers/error handling cover catching errors and rolling back inside stored programs.

A procedure can also contain `START TRANSACTION`, `COMMIT`, or `ROLLBACK`. However, do not let both the caller manage the transaction and the procedure self-commit without an explicit agreement. A commit inside a procedure can terminate a transaction that the caller expected to keep controlling.

Stored functions cannot use explicit transaction control statements. If a workflow must update multiple tables or requires commit/rollback boundaries, a procedure is more suitable.

## 21. Hands-on lab: creating and calling procedures/functions

This lab uses a test schema with `customers` and `orders` tables. Run the table creation and seed data once in a fresh lab schema; if tables already exist, inspect structure and data before re-running. Do not run these sample DDLs directly on production.

### 21.1. Preparing sample tables

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY idx_orders_customer_date (customer_id, order_date)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name)
VALUES
    (1001, 'An Nguyen'),
    (1002, 'Binh Tran');

INSERT INTO orders
    (order_id, customer_id, order_date, total_amount, status)
VALUES
    (5001, 1001, '2026-11-01', 1200000, 'PAID'),
    (5002, 1001, '2026-11-05', 800000, 'OPEN'),
    (5003, 1002, '2026-11-06', 2500000, 'PAID');
```

### 21.2. Creating and calling a procedure with IN

```sql
DELIMITER $$

CREATE PROCEDURE list_customer_orders(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;

CALL list_customer_orders(1001);
```

The result includes the orders for customer `1001`.

### 21.3. Creating and calling a procedure with OUT

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_order_count(
    IN p_customer_id BIGINT,
    OUT p_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_count
    FROM orders
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;

CALL get_customer_order_count(1001, @order_count);
SELECT @order_count AS order_count;
```

### 21.4. Creating and calling a function

```sql
DELIMITER $$

CREATE FUNCTION order_amount_with_tax(
    p_amount DECIMAL(14, 2),
    p_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * (1 + p_rate), 2)$$

DELIMITER ;

SELECT
    order_id,
    total_amount,
    order_amount_with_tax(total_amount, 0.1000) AS amount_with_tax
FROM orders;
```

### 21.5. Verifying definitions and privileges

```sql
SHOW CREATE PROCEDURE list_customer_orders;
SHOW CREATE PROCEDURE get_customer_order_count;
SHOW CREATE FUNCTION order_amount_with_tax;

SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE();

SHOW GRANTS;
```

## 22. Common errors

| Error | Cause | How to handle |
|---|---|---|
| Client reports syntax error near `;` in body | Client treats the first semicolon as the end of `CREATE` | Change the client delimiter when submitting multi-statement definitions. |
| Calling a procedure with `SELECT` | A procedure is not an SQL expression | Use `CALL`. |
| Calling a function with `CALL` | Functions return scalars inside expressions | Use `SELECT function(...)` or an appropriate SQL expression. |
| Using `OUT`/`INOUT` in a function | Functions do not support these parameter modes | Use a procedure if multiple outputs are needed. |
| Function emits a result set | Stored functions cannot return result sets directly | Use `SELECT ... INTO` or switch to a procedure. |
| Function contains `COMMIT`/`ROLLBACK` | Functions cannot explicitly control transactions | Move the workflow to a procedure or caller-managed transaction. |
| `SELECT ... INTO` returns multiple rows | Query does not guarantee a single row | Use an aggregate, a unique condition, or proper business constraints. |
| Procedure has `OUT` but caller does not read it | Output is only assigned to the passed-in argument | Pass a user variable or local variable as the argument and read it after `CALL`. |
| Function declares `DETERMINISTIC` incorrectly | Declaration does not reflect actual data/time dependencies | Re-evaluate dependent data and replication rules. |
| `EXECUTE` denied | Caller lacks `EXECUTE` privilege or security context lacks object privileges | Check `GRANT`, `DEFINER`/`INVOKER`, and object privileges. |
| Routine fails after changing definer | Definer does not exist or lacks privileges | Manage definer accounts and privileges in migrations. |

## 23. Routine design checklist

- [ ] Chose procedure or function based on how the caller needs to consume the result.
- [ ] Procedure has appropriate `IN`/`OUT`/`INOUT` parameter modes for its purpose.
- [ ] Function declares the right `RETURNS` data type and every execution path executes `RETURN`.
- [ ] Local variables are `DECLARE`d in the proper position with suitable data types.
- [ ] `SELECT ... INTO` guarantees the right row count or has `NOT FOUND` handling.
- [ ] Client delimiter is configured properly when creating multi-statement bodies.
- [ ] Function does not emit result sets, use dynamic prepared statements, or control transactions.
- [ ] Function does not modify a table already used by the invoking statement.
- [ ] `DETERMINISTIC` and SQL data access characteristics accurately reflect behavior.
- [ ] `SQL SECURITY DEFINER`/`INVOKER` is chosen and the definer account holds least privilege.
- [ ] Caller holds only necessary privileges, especially `EXECUTE`.
- [ ] Binary logging/replication impact was checked when creating functions.
- [ ] Verified `SHOW CREATE` and `INFORMATION_SCHEMA.ROUTINES` after deployment.
- [ ] Clearly defined who owns the transaction and how errors are handled.
- [ ] Checked performance when a function is called repeatedly per row.

## 24. Key takeaways

`CREATE PROCEDURE` defines a routine invoked with `CALL`. Procedures support `IN`, `OUT`, and `INOUT` parameters, can return result sets, and suit multi-step business workflows.

`CREATE FUNCTION` defines a routine with a `RETURNS` type and terminates with `RETURN`. Functions take input parameters and can be called inside SQL expressions. Functions are restricted regarding result sets, dynamic prepared statements, and transaction control; use them for scalar values with clear contracts.

When deploying either routine type, pay attention to client delimiters, characteristics, `EXECUTE` privileges, `DEFINER`/`INVOKER` security context, binary logging, and transaction management. Always verify saved definitions and test invoking routines using an account with the exact privileges of the real application.
