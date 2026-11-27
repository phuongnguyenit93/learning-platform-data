# Local Variables, User-Defined Variables, and IN/OUT/INOUT Parameters

## Lesson objectives

After this lesson, you will be able to:

- Distinguish between local variables declared with `DECLARE`, user-defined variables prefixed with `@`, and stored routine parameters.
- Declare variables inside `BEGIN ... END` blocks and choose appropriate data types and default values.
- Understand local variable lifetime, how nested blocks see variables, and the risk of name collisions with columns.
- Assign values using `SET` and `SELECT ... INTO`; handle cases where queries return zero rows or multiple rows.
- Use user-defined variables to pass values between statements within the same session.
- Understand why you should not both read and assign the same user-defined variable in a single SQL statement.
- Declare `IN`, `OUT`, and `INOUT` parameters in stored procedures, call procedures, and retrieve results.
- Recognize that stored functions only accept `IN` parameters and return results via `RETURN`.
- Choose the right variable type for temporary routine data, client-exchanged data, and session-scoped state.

MySQL stored programs can be stored procedures or stored functions. Routines commonly receive data from a caller, execute a sequence of operations, and return results. To accomplish this, MySQL provides three related yet distinct mechanisms: local variables, user-defined variables, and routine parameters.

Local variables exist within the scope of the `BEGIN ... END` block where they are declared. User-defined variables start with `@` and persist for the connection session. Parameters represent data crossing the boundary between caller and routine; stored procedures support `IN`, `OUT`, and `INOUT`, whereas stored functions only use `IN` parameters.

Understanding scope and data flow direction makes routines readable, prevents state leakage across requests, and avoids confusing inputs, outputs, and temporary internal variables.

## 1. Distinguishing the three mechanisms

| Mechanism | Syntax | Scope | Primary purpose |
|---|---|---|---|
| Local variable | `DECLARE v_total DECIMAL(14,2)` | Declaring `BEGIN ... END` block and nested sub-blocks | Store temporary values inside a routine |
| User-defined variable | `@session_total` | One connection/session | Exchange data between statements in the same session or between caller and procedure |
| Routine parameter | `IN p_id INT, OUT p_count INT, INOUT p_rate DECIMAL(5,2)` | Inside routine; data passes across the call boundary | Receive structured inputs and return structured outputs |

Brief example:

~~~sql
-- User-defined variable: no DECLARE required
SET @request_id = 501;

DELIMITER $$

CREATE PROCEDURE sp_example(IN p_request_id BIGINT)
BEGIN
    -- Local variable
    DECLARE v_message VARCHAR(100) DEFAULT 'Processing';

    SET v_message = CONCAT(v_message, ': ', p_request_id);

    SELECT v_message AS message;
END$$

DELIMITER ;

CALL sp_example(@request_id);
~~~

In this example:

- `@request_id` belongs to the session running the `CALL` statement.
- `p_request_id` is an `IN` parameter receiving a value from the caller.
- `v_message` is a local variable existing only during this procedure execution.

Do not treat these three as different notations for the same variable. They have different lifetimes, initialization behavior, and data-passing mechanisms.

## 2. Declaring local variables with DECLARE

Local variables can only be declared inside a structured `BEGIN ... END` program block, typically the body of a procedure or function.

Syntax:

~~~sql
DECLARE var_name [, var_name] ... type [DEFAULT value];
~~~

Example:

~~~sql
DECLARE v_order_count INT UNSIGNED DEFAULT 0;
DECLARE v_total_amount DECIMAL(14, 2) DEFAULT 0.00;
DECLARE v_customer_name VARCHAR(120);
DECLARE v_is_valid BOOLEAN DEFAULT FALSE;
~~~

Multiple variables of the same type can be declared in one statement:

~~~sql
DECLARE v_min_id, v_max_id BIGINT UNSIGNED DEFAULT 0;
~~~

Local variable data types use valid MySQL data types, similar to routine parameters. Choose types close to the actual data to avoid unexpected type conversions and overflows.

### 2.1. DECLARE must be at the top of the block

Variable declarations must appear at the beginning of the `BEGIN ... END` block, before executable statements. Inside a stored program, variables and conditions are declared before cursors or handlers.

Valid example:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_local_variable_demo()
BEGIN
    DECLARE v_count INT UNSIGNED DEFAULT 0;
    DECLARE v_note VARCHAR(100) DEFAULT 'Started';

    SET v_count = v_count + 1;

    SELECT v_count AS current_count, v_note AS note;
END$$

DELIMITER ;
~~~

Invalid example because `DECLARE` appears after `SET`:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_invalid_declare()
BEGIN
    SET @started = 1;
    DECLARE v_count INT DEFAULT 0;
END$$

DELIMITER ;
~~~

If a separate inner scope is needed, create a nested `BEGIN ... END` block and place declarations at the top of that sub-block.

### 2.2. Default values and NULL

If `DEFAULT` is provided, the variable receives the specified value. The default value can be an expression.

Without `DEFAULT`, a local variable's initial value is `NULL`.

~~~sql
DECLARE v_attempts INT UNSIGNED DEFAULT 0;
DECLARE v_started_at DATETIME DEFAULT CURRENT_TIMESTAMP;
DECLARE v_last_message VARCHAR(200);
~~~

In the example above, `v_last_message` starts as `NULL`. When using variables in expressions, account for `NULL` handling because most arithmetic operations involving `NULL` evaluate to `NULL`.

Example initializing explicitly before incrementing:

~~~sql
SET v_attempts = v_attempts + 1;
~~~

If `v_attempts` starts as `NULL`, the addition above also produces `NULL`. Therefore, set an appropriate `DEFAULT` or use `COALESCE` when receiving potentially nullable data.

### 2.3. Data types and value checks

Local variables undergo data type and overflow checks similar to stored routine parameters. Choose a type with a sufficient value range for the business logic.

~~~sql
DECLARE v_quantity INT UNSIGNED DEFAULT 0;
DECLARE v_unit_price DECIMAL(12, 2) DEFAULT 0.00;
DECLARE v_line_total DECIMAL(16, 2) DEFAULT 0.00;

SET v_line_total = v_quantity * v_unit_price;
~~~

Use `DECIMAL` for money and values requiring exact decimal precision. Avoid `FLOAT` or `DOUBLE` for monetary calculations when business rules require exact decimal results.

## 3. Local variable lifetime and scope

A local variable is valid only inside the `BEGIN ... END` block where it is declared. Nested sub-blocks can access parent block variables unless the sub-block declares a variable with the same name.

Example:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_scope_demo()
BEGIN
    DECLARE v_message VARCHAR(40) DEFAULT 'Outer block variable';

    BEGIN
        DECLARE v_inner_count INT DEFAULT 10;

        SELECT v_message AS outer_message,
               v_inner_count AS inner_count;
    END;

    SELECT v_message AS outer_message_after_block;
END$$

DELIMITER ;
~~~

`v_message` is visible inside the sub-block because it was declared in the parent block. `v_inner_count` exists only inside the sub-block; after the sub-block's `END`, it can no longer be referenced.

### 3.1. Avoid declaring names matching column names

Do not give local variables the same names as table columns. When names collide in an SQL statement, MySQL may resolve the name to the local variable instead of the column, causing filter conditions to behave unexpectedly.

Confusing example:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_bad_name_resolution()
BEGIN
    DECLARE customer_id BIGINT UNSIGNED DEFAULT 101;

    SELECT customer_id
    FROM customer
    WHERE customer_id = customer_id;
END$$

DELIMITER ;
~~~

In a stored program, both occurrences of `customer_id` may be resolved as the local variable. The condition then ceases to compare the column against the variable as originally intended.

Use clear naming conventions:

- `p_` for parameters, e.g. `p_customer_id`.
- `v_` for local variables, e.g. `v_customer_count`.
- Table aliases for columns, e.g. `c.customer_id`.

Clearer version:

~~~sql
DECLARE v_customer_id BIGINT UNSIGNED DEFAULT 101;

SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id = v_customer_id;
~~~

Naming conventions do not replace qualifying columns with aliases, but they significantly reduce mistakes in long routines involving multiple tables.

## 4. Assigning values to local variables

Two common methods are `SET` and `SELECT ... INTO`.

### 4.1. Using SET

`SET` fits when the value is computed from constants, parameters, other variables, or expressions.

~~~sql
DECLARE v_subtotal DECIMAL(14, 2) DEFAULT 0.00;
DECLARE v_tax_rate DECIMAL(5, 2) DEFAULT 8.00;
DECLARE v_tax_amount DECIMAL(14, 2) DEFAULT 0.00;

SET v_subtotal = 1250000.00;
SET v_tax_amount = ROUND(v_subtotal * v_tax_rate / 100, 2);
~~~

Multiple variables can be assigned in a single `SET` statement:

~~~sql
SET v_subtotal = 1250000.00,
    v_tax_rate = 8.00;
~~~

### 4.2. Using SELECT ... INTO

`SELECT ... INTO` retrieves query results and assigns them into local variables or routine parameters.

~~~sql
DECLARE v_order_total DECIMAL(14, 2) DEFAULT 0.00;

SELECT COALESCE(SUM(o.total_amount), 0.00)
INTO v_order_total
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

The number of variables in `INTO` must match the number of expressions in the `SELECT` list.

Example fetching multiple values:

~~~sql
DECLARE v_order_count INT UNSIGNED DEFAULT 0;
DECLARE v_total_amount DECIMAL(14, 2) DEFAULT 0.00;

SELECT
    COUNT(*),
    COALESCE(SUM(o.total_amount), 0.00)
INTO
    v_order_count,
    v_total_amount
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

Placing `INTO` at the end of the `SELECT` statement is the preferred style:

~~~sql
SELECT o.order_status
FROM sales_order AS o
WHERE o.order_id = p_order_id
INTO v_order_status;
~~~

### 4.3. SELECT ... INTO must handle row cardinality

The variable-assignment form of `SELECT ... INTO` requires exactly one row.

- If no rows match, MySQL raises warning 1329 (`No data`) and the variables retain their pre-statement values.
- If more than one row matches, MySQL raises error 1172 (`Result consisted of more than one row`).
- If multiple rows may match but only one is needed, use a deterministic `ORDER BY` and `LIMIT 1`.

Example fetching an order's status by primary key:

~~~sql
SELECT o.order_status
INTO v_order_status
FROM sales_order AS o
WHERE o.order_id = p_order_id;
~~~

If the condition does not guarantee uniqueness, explicitly limit the result:

~~~sql
SELECT o.order_status
INTO v_order_status
FROM sales_order AS o
WHERE o.customer_id = p_customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 1;
~~~

Do not blindly add `LIMIT 1` if business rules require detecting duplicate data. In that case, keep the query without a limit so MySQL raises the multi-row error, or explicitly check cardinality.

### 4.4. Using aggregates to always return one row

Aggregate functions like `COUNT(*)` return one row even when zero rows satisfy the condition. This is useful for assigning counts without triggering a `No data` warning.

~~~sql
SELECT COUNT(*)
INTO v_order_count
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

With `SUM`, `AVG`, `MIN`, and `MAX`, the result can be `NULL` if no matching rows exist. Use `COALESCE` when `NULL` should be replaced by a business default such as `0`.

## 5. User-defined variables prefixed with @

User-defined variables are written with a leading `@` symbol:

~~~sql
SET @current_customer_id = 101;
SET @report_limit = 20;

SELECT
    @current_customer_id AS customer_id,
    @report_limit AS report_limit;
~~~

User-defined variables do not need `DECLARE`. Reading an uninitialized variable yields `NULL`.

Characteristics of user-defined variables:

- Scoped to the current session/connection.
- Other sessions cannot access variables from this session.
- Released when the client terminates the session.
- Names are case-insensitive.
- Used to hold data values, not directly as table names, column names, or SQL identifiers.

### 5.1. User-defined variables persist across statements

~~~sql
SET @customer_id = 101;

SELECT
    order_id,
    total_amount
FROM sales_order
WHERE customer_id = @customer_id;

SELECT @customer_id AS customer_used;
~~~

Both `SELECT` statements can read the same variable because they run within the same session.

If a connection pool reuses a connection for another request, user-defined variables persist on that connection until reassigned or the session ends. Therefore, never rely on stale `@variable` values from a prior request. Explicitly initialize or reset needed variables at the start of a task.

### 5.2. Assigning user-defined variables

Prefer `SET`:

~~~sql
SET @tax_rate = 8.00;
SET @subtotal = 1250000.00;
SET @tax_amount = ROUND(@subtotal * @tax_rate / 100, 2);

SELECT @tax_amount AS tax_amount;
~~~

Either `=` or `:=` can be used in `SET`. In statements other than `SET`, legacy variable assignment using `:=` still exists for compatibility, but is recommended against in new SQL code.

### 5.3. SELECT ... INTO user-defined variables

`SELECT ... INTO` can assign results into user-defined variables:

~~~sql
SELECT COUNT(*)
INTO @order_count
FROM sales_order
WHERE customer_id = 101;

SELECT @order_count AS order_count;
~~~

Row count rules and handling for zero/multiple rows follow the same principles as `SELECT ... INTO` with local variables. With `COUNT(*)`, the query always returns one row.

### 5.4. Do not read and assign the same variable in one statement

The evaluation order of expressions that both read and assign the same user-defined variable is undefined.

Avoid writing:

~~~sql
SELECT @counter, @counter := @counter + 1;
~~~

There is no guarantee whether the expression reading `@counter` evaluates before or after the assignment expression.

Split into explicit statements instead:

~~~sql
SET @counter = COALESCE(@counter, 0);
SET @counter = @counter + 1;
SELECT @counter AS counter_value;
~~~

This is easier to read, easier to test, and does not depend on expression evaluation order.

### 5.5. Data types of user-defined variables

User-defined variables store scalar values such as integers, `DECIMAL`, floating-point numbers, binary/non-binary strings, or `NULL`. Certain other types are converted upon assignment: temporal and spatial values become binary strings; JSON becomes a string with the `utf8mb4` charset. Assigning `DECIMAL` or floating-point values does not preserve full original precision and scale.

Therefore, user-defined variables are convenient for session-level data exchange and `CALL` arguments, but avoid using them as intermediate storage for high-precision financial calculations. Inside routines, prefer local variables and parameters with explicit `DECIMAL` types.

The type of a user-defined variable used in a prepared statement is determined when the statement is `PREPARE`d and remains fixed across subsequent `EXECUTE` calls. Similarly, the type of a user-defined variable used inside a stored procedure statement is determined on the first invocation and retained on subsequent calls. If a variable needs to hold varying data types, redesign how data is passed or use explicit `CAST`.

### 5.6. User-defined variables hold values, not object names

User-defined variables cannot directly substitute for database names, table names, column names, or SQL keywords.

The following example is invalid:

~~~sql
SET @table_name = 'sales_order';
SELECT * FROM @table_name;
~~~

If dynamic SQL is needed inside a stored procedure, build the statement string and use `PREPARE`/`EXECUTE` per its rules. Local variables and routine parameters cannot be referenced directly inside a prepared statement created within a routine; prepared statements are session-scoped and can outlive the routine. Dynamic SQL typically uses user-defined variables to hold the statement string or bind values appropriately.

Do not use dynamic SQL solely to substitute a data value; parameter binding or standard SQL conditions are safer and simpler.

## 6. Stored procedure parameters

Parameters form the data interface between the caller and a stored procedure. MySQL supports three modes:

- `IN`: passes data into the procedure.
- `OUT`: passes data from the procedure back to the caller.
- `INOUT`: passes data in, allowing the procedure to modify and return it.

Syntax:

~~~sql
CREATE PROCEDURE procedure_name (
    [IN | OUT | INOUT] parameter_name data_type,
    ...
)
routine_body;
~~~

If no mode is specified, the parameter defaults to `IN`.

Parameter names are case-insensitive. Do not declare a local variable with the same name as a parameter in the same scope.

### 6.1. IN: input parameters

`IN` passes a value from the caller into the procedure. The procedure may reassign the parameter inside its body, but that change is not reflected back to the caller's variable when the procedure finishes.

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_show_customer(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT '';

    SET v_message = CONCAT('Customer ID = ', p_customer_id);

    SELECT
        p_customer_id AS input_customer_id,
        v_message AS message;
END$$

DELIMITER ;
~~~

Calling the procedure:

~~~sql
CALL sp_show_customer(101);
~~~

Literals, expressions, or user-defined variables can be passed as `IN` arguments:

~~~sql
SET @customer_id = 102;
CALL sp_show_customer(@customer_id);
~~~

`IN` fits customer IDs, date ranges, filter statuses, processing counts, or business control parameters.

### 6.2. OUT: output parameters

`OUT` returns a value from the procedure to the caller.

When the procedure starts, an `OUT` parameter has the value `NULL` inside the routine, regardless of what value the caller's variable previously held. The procedure must assign a value before returning if the caller expects a non-`NULL` result.

Example:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_count_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM sales_order
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;
~~~

Calling the procedure and reading the result:

~~~sql
CALL sp_count_orders(101, @order_count);

SELECT @order_count AS order_count;
~~~

At the SQL client level, pass a user-defined variable for the `OUT` parameter to receive the result. When calling from another stored procedure or function, an appropriate routine parameter or local variable can be passed.

If the procedure never assigns the `OUT` parameter, the returned value is `NULL`. Design every execution branch so `OUT` parameters are always assigned when business rules require a concrete output.

### 6.3. INOUT: both receiving and returning a value

`INOUT` combines both directions:

1. The caller initializes the value before calling.
2. The procedure receives that value.
3. The procedure can modify the value.
4. The updated value is returned to the caller after the procedure completes.

Example incrementing a counter:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_increment_counter(
    INOUT p_counter INT
)
BEGIN
    SET p_counter = COALESCE(p_counter, 0) + 1;
END$$

DELIMITER ;
~~~

Call:

~~~sql
SET @counter = 10;

CALL sp_increment_counter(@counter);

SELECT @counter AS counter_after_call;
~~~

The value of `@counter` after `CALL` is `11`.

Unlike `OUT`, `INOUT` requires the caller to provide a meaningful initial value. If the caller passes `NULL`, the routine must explicitly decide how to handle `NULL`.

### 6.4. Comparing IN, OUT, and INOUT

| Mode | Value upon entering routine | Modifiable inside routine | Caller sees changes |
|---|---|---|---|
| `IN` | Value passed by caller | Local copy modifiable | No |
| `OUT` | Initially `NULL` in routine | Yes | Yes |
| `INOUT` | Value passed by caller | Yes | Yes |

Choose the mode by data direction:

- Input only: `IN`.
- Output only: `OUT`.
- Receive initial state and return updated state: `INOUT`.

Do not use `INOUT` merely to avoid declaring an `OUT` parameter. If a routine returns multiple independent results, multiple `OUT` parameters can make the interface clearer.

## 7. Complete example: summarizing orders and applying a discount cap

This lab uses a simple table to demonstrate at once:

- An `IN` parameter receiving the customer ID.
- `OUT` parameters returning the order count and discounted total.
- An `INOUT` parameter receiving an initial discount percentage and returning the capped percentage.
- A local variable storing the pre-discount subtotal.

### 7.1. Creating sample data

~~~sql
CREATE TABLE routine_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_routine_customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO routine_order_demo (
    order_id, customer_id, total_amount
)
VALUES
    (9001, 101, 1250000.00),
    (9002, 101, 2400000.00),
    (9003, 102,  890000.00),
    (9004, 101,  450000.00),
    (9005, 103, 3400000.00);
~~~

### 7.2. Creating the procedure

The discount percentage is clamped between 0% and 30%. The original subtotal is calculated using `SUM`, then the capped discount is applied.

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_customer_order_summary(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED,
    OUT p_total_after_discount DECIMAL(14, 2),
    INOUT p_discount_percent DECIMAL(5, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(14, 2) DEFAULT 0.00;

    SELECT
        COUNT(*),
        COALESCE(SUM(o.total_amount), 0.00)
    INTO
        p_order_count,
        v_subtotal
    FROM routine_order_demo AS o
    WHERE o.customer_id = p_customer_id;

    SET p_discount_percent =
        LEAST(
            GREATEST(COALESCE(p_discount_percent, 0.00), 0.00),
            30.00
        );

    SET p_total_after_discount =
        ROUND(v_subtotal * (1 - p_discount_percent / 100), 2);
END$$

DELIMITER ;
~~~

Explanation:

- `p_customer_id` is `IN`, supplying input data only.
- `p_order_count` is `OUT`, receiving the counted number of orders.
- `p_total_after_discount` is `OUT`, receiving the total after discount.
- `p_discount_percent` is `INOUT`, receiving the initial discount and returning the capped discount.
- `v_subtotal` is a local variable, holding the raw subtotal only during the procedure call.

`COUNT(*)` and `SUM()` are aggregates, so `SELECT ... INTO` returns one row even when a customer has no orders. `COUNT(*)` returns `0`, while `SUM()` is converted via `COALESCE` to `0.00`.

### 7.3. Calling the procedure and reading results

~~~sql
SET @order_count = -1;
SET @total_after_discount = -1.00;
SET @discount_percent = 50.00;

CALL sp_customer_order_summary(
    101,
    @order_count,
    @total_after_discount,
    @discount_percent
);

SELECT
    @order_count AS order_count,
    @total_after_discount AS total_after_discount,
    @discount_percent AS applied_discount_percent;
~~~

With the sample data:

- Customer 101 has 3 orders.
- The pre-discount subtotal is 4,100,000.00.
- The initial 50% discount is capped to 30%.
- The discounted total is 2,870,000.00.

Because `@order_count` and `@total_after_discount` are `OUT`, their previous values are not used as inputs to the routine. `@discount_percent` is `INOUT`, so `50.00` is passed in and replaced with `30.00`.

### 7.4. Testing a customer with no orders

~~~sql
SET @order_count = -1;
SET @total_after_discount = -1.00;
SET @discount_percent = 10.00;

CALL sp_customer_order_summary(
    999,
    @order_count,
    @total_after_discount,
    @discount_percent
);

SELECT
    @order_count,
    @total_after_discount,
    @discount_percent;
~~~

Expected result: order count is `0`, discounted total is `0.00`, and discount percentage remains `10.00`. This example shows how aggregates allow a procedure to handle empty result sets without `SELECT ... INTO` returning 0 rows.

## 8. Stored function parameters

A stored function accepts input parameters and returns a single value using `RETURN`. In MySQL, function parameters are always treated as `IN`; do not declare `OUT` or `INOUT` for functions.

Syntax:

~~~sql
CREATE FUNCTION function_name (
    parameter_name data_type,
    ...
)
RETURNS return_type
routine_body;
~~~

Example function calculating discounted price:

~~~sql
DELIMITER $$

CREATE FUNCTION fn_price_after_discount(
    p_price DECIMAL(14, 2),
    p_discount_percent DECIMAL(5, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
BEGIN
    DECLARE v_result DECIMAL(14, 2) DEFAULT 0.00;

    SET v_result = ROUND(
        p_price * (1 - p_discount_percent / 100),
        2
    );

    RETURN v_result;
END$$

DELIMITER ;
~~~

Calling the function in an SQL expression:

~~~sql
SELECT fn_price_after_discount(1000000.00, 15.00)
    AS discounted_price;
~~~

Functions do not return results via `OUT` parameters. The returned value must match the data type declared in `RETURNS`.

### 8.1. When to use a procedure vs. a function?

| Requirement | Suitable choice |
|---|---|
| Receive data and return multiple values | Procedure with `OUT`/`INOUT` |
| Execute a sequence of business operations | Procedure |
| Compute a value for use in SQL expressions | Function |
| Only need inputs and a single return value | Function is usually suitable |
| Need to mutate input state and return it | Procedure with `INOUT` |

Do not convert a procedure into a function solely for shorter call syntax. Stored functions carry specific execution restrictions and return only one value of the `RETURNS` type.

## 9. Local variables and parameters in prepared statements

Local variables and routine parameters exist only while the routine is executing. Prepared statements created inside a stored program are session-scoped and may outlive the routine.

Therefore, a prepared statement created inside a routine cannot reference local variables or routine parameters directly. When dynamic SQL is needed in a procedure, pass values through user-defined variables or an appropriate binding mechanism supported by prepared statements.

Conceptual example:

~~~sql
SET @sql_text = 'SELECT order_id FROM routine_order_demo WHERE customer_id = ?';
PREPARE stmt FROM @sql_text;

SET @customer_id = 101;
EXECUTE stmt USING @customer_id;

DEALLOCATE PREPARE stmt;
~~~

This example illustrates using user-defined variables for a prepared statement. In real routines, manage prepared statement names, input data, and `DEALLOCATE` explicitly. Stored functions and triggers have specific restrictions regarding SQL prepared statements.

If dynamic SQL is unnecessary, use routine parameters and static SQL. That approach is easier to verify and carries less risk.

## 10. Common mistakes

| Error or misconception | Reality | How to handle |
|---|---|---|
| Using `DECLARE` anywhere in a procedure | `DECLARE` must be at the top of `BEGIN ... END` | Place all declarations before executable statements |
| Local variables without `DEFAULT` equal `0` | Initial value is `NULL` | Assign `DEFAULT` or initialize with `SET` |
| Local variables last for the whole session | Variables live only within their declaring block | Use user-defined variables if sharing across statements in the same session |
| User-defined variables are server-global | User-defined variables are session-scoped | Never use them to share state across connections |
| `IN` modifies the caller's variable | `IN` changes stay local to the routine | Use `OUT` or `INOUT` if changes must be returned |
| `OUT` receives initial value from caller | `OUT` starts as `NULL` inside the routine | Assign a value to `OUT` before finishing |
| `INOUT` needs no initialization | `INOUT` receives the caller-supplied value | Assign the user variable before `CALL` |
| Stored functions can declare `OUT` | Functions only support `IN` parameters | Use a procedure if `OUT`/`INOUT` is needed |
| `SELECT ... INTO` can return multiple rows | More than one row triggers error 1172 | Use aggregates or unique conditions; if appropriate use `ORDER BY` and `LIMIT 1` |
| `SELECT ... INTO` with zero rows assigns `NULL` | Variables keep previous values and warning 1329 is raised | Initialize explicitly and handle missing rows |
| Using identical names for variables and columns | MySQL may resolve the name to the local variable | Use `p_`/`v_` prefixes and qualify columns with aliases |
| Both reading and assigning `@var` in one `SELECT` | Evaluation order is undefined | Split into separate `SET` statements |
| User-defined variables can serve as table names | User-defined variables hold values, not direct identifiers | Use controlled dynamic SQL only when truly needed |
| Prepared statements directly reference local variables | Local variables and parameters are outside the prepared statement's session scope | Pass values via user-defined variables or proper bindings |

## 11. Process for designing routines with clear variables and parameters

When designing a new procedure or function:

1. Identify data the caller must supply; declare them as `IN` parameters.
2. Identify results the caller must receive; use `OUT` for output-only values.
3. If the caller passes initial state and needs the updated state back, use `INOUT`.
4. Declare internal temporary variables using `DECLARE` with a `v_` prefix.
5. Choose appropriate data types and `DEFAULT` values; avoid unintended `NULL`s.
6. Place `DECLARE` statements at the top of the `BEGIN ... END` block.
7. Use `SET` for expressions and `SELECT ... INTO` for query results.
8. Ensure `SELECT ... INTO` has proper cardinality; handle empty result cases.
9. Never name variables the same as columns; qualify columns with aliases.
10. When using `OUT`/`INOUT` from a client, pass user-defined variables and read results after `CALL`.
11. When using a function, declare `IN` parameters and return the value with `RETURN`.
12. Test the routine with normal data, empty sets, `NULL`s, and boundary values.

Data flow diagram:

~~~mermaid
flowchart TD
    A[Caller] --> B[IN parameters]
    A --> C[INOUT initial values]
    B --> D[Stored procedure]
    C --> D
    D --> E[Local variables DECLARE]
    E --> F[SET and SELECT INTO]
    F --> G[Business logic]
    G --> H[OUT values]
    G --> I[Updated INOUT values]
    H --> J[Caller reads results]
    I --> J
~~~

## 12. Practice exercises

### Exercise 1: Declaring and initializing local variables

Create a procedure declaring three variables: quantity, total amount, and processing status. Assign a `DEFAULT` to each, then update them with `SET` and display them with `SELECT`.

### Exercise 2: Nested block scope

Create a procedure with one variable in the outer block and one variable in a sub-block. Try accessing the sub-block variable after `END` and explain why it is invalid.

### Exercise 3: Querying into a local variable

Use `SELECT ... INTO` to fetch a customer's total order amount. Test both an existing and a non-existent `customer_id`; observe warning 1329 and that the variable retains its value.

### Exercise 4: Detecting multiple rows

Write a `SELECT ... INTO` by `customer_id` that can return multiple orders. Observe error 1172. Then fix it with `SUM` or `ORDER BY ... LIMIT 1` depending on the goal.

### Exercise 5: Session-scoped user-defined variables

Set `@customer_id`, use it in two `SELECT` statements, and open another connection to verify the variable is not shared across sessions.

### Exercise 6: Avoiding undefined evaluation order

Write a counter increment using separate `SET` statements. Compare it with reading and assigning `@counter` in the same `SELECT` and explain why the latter is unsafe.

### Exercise 7: Procedure with IN and OUT

Write a procedure taking `customer_id` via `IN` and returning order count via `OUT`. Call it with a user variable and read the result after `CALL`.

### Exercise 8: Procedure with INOUT

Write a procedure accepting a discount percentage, clamping it between 0 and 30, and returning the clamped value. Test inputs `10`, `50`, and `NULL`.

### Exercise 9: Function with IN only

Write a function taking an original price and a discount percentage, returning the discounted price via `RETURN`. Test calling the function in `SELECT`.

### Exercise 10: Designing a routine interface

Design a procedure calculating total amount by customer. Classify each data item as `IN`, `OUT`, `INOUT`, or local variable and explain your reasoning.

## Conclusion

Local variables, user-defined variables, and routine parameters serve distinct data scopes. `DECLARE` creates local variables inside `BEGIN ... END`; `@name` user-defined variables persist within a session; `IN`/`OUT`/`INOUT` parameters pass data across stored procedure calls. Stored functions use only `IN` parameters and return results via `RETURN`.

Use local variables for internal computations, parameters to define the routine interface, and user-defined variables when values must be passed between statements in the same session. Name clearly, initialize intentionally, control `SELECT ... INTO` cardinality, and inspect `OUT`/`INOUT` results after `CALL`. These practices keep stored programs readable, testable, and independent of stale connection state.

## References

- MySQL 8.4 Reference Manual — Local Variable DECLARE Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-local-variable.html
- MySQL 8.4 Reference Manual — Local Variable Scope and Resolution: https://dev.mysql.com/doc/refman/8.4/en/local-variable-scope.html
- MySQL 8.4 Reference Manual — Variables in Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-variables.html
- MySQL 8.4 Reference Manual — User-Defined Variables: https://dev.mysql.com/doc/refman/8.4/en/user-variables.html
- MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 Reference Manual — CALL Statement: https://dev.mysql.com/doc/refman/8.4/en/call.html
- MySQL 8.4 Reference Manual — SELECT ... INTO Statement: https://dev.mysql.com/doc/refman/8.4/en/select-into.html
- MySQL 8.4 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html
