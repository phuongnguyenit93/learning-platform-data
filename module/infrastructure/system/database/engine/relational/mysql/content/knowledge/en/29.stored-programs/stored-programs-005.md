# SET, SELECT INTO, and Result Assignment Rules

In MySQL stored programs, local variables and parameters help store intermediate state, receive query results, and control processing steps. Two common assignment mechanisms are the `SET` statement and the `SELECT ... INTO` clause.

They look similar, yet they do not share the same semantics:

- `SET` assigns an expression to an existing variable or parameter; it can assign multiple variables in one statement.
- `SELECT ... INTO` executes a query and maps the values of a single result row into a list of variables.
- `SELECT ... INTO` must explicitly handle zero rows, exactly one row, or more than one row.
- Local variables, routine parameters, and user-defined variables differ in lifetime, data type behavior, and purpose.

This article focuses on result assignment rules in MySQL stored programs: declaring variables, using `SET`, retrieving data via `SELECT ... INTO`, handling cardinality, type conversion, and avoiding bugs where variables hold stale values or undefined results.

## 1. Scope of SET and SELECT ... INTO

The following examples use an orders table:

~~~sql
CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;
~~~

A stored procedure can declare local variables, take values from parameters, query a row, and calculate results:

~~~sql
DELIMITER //

CREATE PROCEDURE calculate_order_total(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_tax DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
      INTO v_subtotal
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    SET v_tax = ROUND(v_subtotal * 0.08, 2);
    SET p_total = v_subtotal + v_tax;
END//

DELIMITER ;
~~~

`DELIMITER` is a `mysql` client directive to change the statement terminator when sending routine definitions containing inner semicolons. It is not an SQL statement sent verbatim to the server. When using a GUI, migration tool, or driver, routine definition syntax may differ; follow that tool's delimiter/script mechanism.

The example illustrates both forms:

- `SELECT ... INTO` retrieves the `total` value from the order row and assigns it to `v_subtotal`.
- `SET` computes the tax and assigns it to `v_tax`.
- `SET` then assigns the final result to the `OUT` parameter `p_total`.

This example assumes `order_id` exists. Later sections handle the zero-row case completely.

## 2. Local variables in stored programs

Local variables are declared using `DECLARE` at the top of a `BEGIN ... END` block, before executable statements in that block.

~~~sql
BEGIN
    DECLARE v_order_count BIGINT UNSIGNED DEFAULT 0;
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_note VARCHAR(200) DEFAULT '';
    DECLARE v_created_at DATETIME DEFAULT NULL;

    SET v_order_count = 0;
    SET v_total = 0;
    SET v_note = 'Pending';
END
~~~

Inside a stored routine, `DECLARE variable` must appear before executable statements. If the block also declares cursors or handlers, declaration order must follow MySQL's rule: variables and conditions first, cursors next, and handlers last.

Variable names should use a consistent prefix such as `v_` to distinguish them from:

- Table columns: `order_id`, `total`, `created_at`.
- Routine parameters: `p_order_id`, `p_total`.
- User-defined variables: `@current_order_id`.

Avoid naming a local variable the same as a column. When referencing columns in queries, always use aliases and qualifiers such as `so.total`; this reduces the risk of ambiguous names or misinterpretation as a routine variable.

### 2.1. Block scope

A local variable exists only inside the block where it is declared, and sub-blocks can access it according to scoping rules. When the block ends, the variable ceases to exist.

~~~sql
CREATE PROCEDURE show_local_scope()
BEGIN
    DECLARE v_message VARCHAR(50) DEFAULT 'outer';

    BEGIN
        DECLARE v_inner_message VARCHAR(50) DEFAULT 'inner';
        SET v_message = 'updated by inner block';
        SELECT v_message, v_inner_message;
    END;

    SELECT v_message;
END
~~~

The inner block can use variables from the outer block. Variables declared inside cannot be referenced after that inner block finishes.

### 2.2. Declaring appropriate data types

A local variable's type is fixed at declaration time:

| Data type | Common use cases |
|---|---|
| `INT`, `BIGINT` | Counts, identifier keys |
| `DECIMAL(p,s)` | Money and decimals requiring exact precision |
| `VARCHAR(n)` | Codes, names, bounded-length strings |
| `DATE`, `DATETIME`, `TIMESTAMP` | Dates or points in time |
| `BOOLEAN` | Boolean flag; in MySQL an alias for `TINYINT(1)` |
| `JSON` | JSON values when a routine must process JSON documents |

Do not use `FLOAT` or `DOUBLE` for money merely for arithmetic convenience; they are approximate numeric types. `DECIMAL` is usually more suitable when exact decimal results are required by business logic.

If a variable receives data from a `DECIMAL(13,2)` column, declare the variable with matching precision and scale to avoid unintended rounding or data loss.

## 3. IN, OUT, and INOUT parameters

Stored procedures can receive or return data through parameters:

- `IN`: input to the routine. Inside the routine, the parameter behaves like a local variable; reassigning it does not alter the caller's variable.
- `OUT`: the routine writes a value for the caller to receive after the procedure completes.
- `INOUT`: the caller passes an initial value and the routine can update that value.

Example:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_discount(
    IN p_subtotal DECIMAL(13, 2),
    IN p_discount_rate DECIMAL(5, 2),
    OUT p_final_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;

    SET v_discount =
        ROUND(p_subtotal * p_discount_rate / 100, 2);

    SET p_final_total = p_subtotal - v_discount;
END//

DELIMITER ;
~~~

Calling the procedure and reading the result via a user-defined variable:

~~~sql
CALL apply_discount(1000.00, 10.00, @final_total);
SELECT @final_total;
~~~

The user-defined variable `@final_total` here is where the caller receives the `OUT` value. It is not the local variable `v_discount` inside the routine. `OUT` parameters are initialized when the routine starts; nevertheless, explicitly assigning the output value on every branch makes the result contract clear to the caller.

### 3.1. INOUT example

~~~sql
DELIMITER //

CREATE PROCEDURE add_bonus(
    IN p_bonus DECIMAL(13, 2),
    INOUT p_running_total DECIMAL(13, 2)
)
BEGIN
    SET p_running_total = p_running_total + p_bonus;
END//

DELIMITER ;
~~~

~~~sql
SET @running_total = 500.00;
CALL add_bonus(25.00, @running_total);
SELECT @running_total;
~~~

The user variable result is `525.00`. The caller must pass an appropriate variable for `OUT` or `INOUT` parameters; do not pass a constant expression as the target receiver.

## 4. The SET statement

`SET` assigns expression values to one or more variables:

~~~sql
SET v_order_count = 10;
SET v_total = 1250.50;
SET v_note = 'Confirmed';
SET v_total = v_total + 100.00;
~~~

In stored programs, `SET` is the clear way to assign a computed value, literal, parameter, or expression result to a local variable.

### 4.1. Assigning multiple variables in one SET

~~~sql
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_tax DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_grand_total DECIMAL(13, 2) DEFAULT 0;

    SET
        v_subtotal = 1000.00,
        v_tax = 80.00,
        v_grand_total = 1080.00;
END
~~~

Multiple variables can be assigned in a single `SET` statement. However, do not rely on swapping variables inside one assignment list to perform complex exchanges. When swapping values, use a temporary variable and separate `SET` statements:

~~~sql
SET v_temp = v_left;
SET v_left = v_right;
SET v_right = v_temp;
~~~

Writing separate statements makes intent clear and avoids relying on unguaranteed expression evaluation behavior.

### 4.2. Using = and :=

Inside a `SET` statement, either `=` or `:=` can be used for assignment:

~~~sql
SET v_total = 100.00;
SET v_total := v_total + 25.00;
~~~

In expressions outside `SET`, MySQL's assignment operator is `:=`. However, for stored program logic, prefer `SET` or `SELECT ... INTO` rather than embedding assignments inside a `SELECT` expression.

Do not confuse `=` used for assignment in `SET` with equality comparison in `WHERE` or `IF` conditions. Syntactic context determines the meaning of this symbol.

### 4.3. Assigning from expressions

The right-hand expression can use variables, parameters, functions, or operators:

~~~sql
BEGIN
    DECLARE v_line_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_final_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_is_large_order BOOLEAN DEFAULT FALSE;

    SET v_line_total = p_quantity * p_unit_price;
    SET v_discount = ROUND(v_line_total * p_discount_rate / 100, 2);
    SET v_final_total = v_line_total - v_discount;
    SET v_is_large_order = (v_final_total >= 10000.00);
END
~~~

This example assumes `p_quantity`, `p_unit_price`, and `p_discount_rate` are parameters of the enclosing routine. The expression result is converted to the declared type of the target variable. For `BOOLEAN` variables in MySQL, the value is stored as a small numeric value; use explicit conditions like `v_final_total >= 10000.00` to produce readable flags.

### 4.4. Assigning NULL

Variables can hold `NULL` if type and context permit:

~~~sql
SET v_customer_note = NULL;
~~~

Afterward, check using `IS NULL` or `IS NOT NULL`:

~~~sql
IF v_customer_note IS NULL THEN
    SET v_customer_note = 'No note';
END IF;
~~~

Do not use `= NULL` because comparing with `NULL` yields `UNKNOWN`, not `TRUE` or `FALSE`.

## 5. User variables and system variables are not local variables

MySQL provides user-defined variables prefixed with `@`:

~~~sql
SET @current_order_id = 1001;
SET @running_total = 250.00;
SELECT @current_order_id, @running_total;
~~~

User variables are session/connection-scoped. Values can persist after a stored procedure finishes and be accessed by subsequent statements on the same connection. When the connection closes, that session's user variables disappear.

Comparison:

| Feature | Local variable | User variable |
|---|---|---|
| Notation | `v_total` | `@total` |
| Declaration | `DECLARE` inside block | No `DECLARE` needed |
| Data type | Statically declared in routine | Type attached to assigned value, can change |
| Scope | Block/routine | Session/connection |
| Purpose | Internal routine logic | Sharing values across statements in a session or with caller |
| Risk | Scope and shadowing | State leakage across requests sharing a pooled connection |

Do not use user variables instead of local variables inside stored routines. A connection pool may reuse the same connection across multiple requests; leftover user variables can cause a later request to read stale state if the application does not reinitialize them.

### 5.1. Do not assign user variables inside SELECT to control order

Some legacy SQL queries assign user variables directly inside `SELECT`:

~~~sql
SELECT
    @running_total := @running_total + total,
    order_id
FROM sales_orders
ORDER BY order_id;
~~~

Do not rely on expression evaluation order when reading and writing the same user variable in one `SELECT` statement. MySQL does not guarantee expression evaluation order as a state-serialization mechanism; results may change across query plans or versions.

If running totals are needed, use `SUM()` or an appropriate window function. If step-by-step state updates are needed inside a stored program, use local variables and separate `SET` statements.

### 5.2. System variables

System variables configure server or session behavior. They can be read via:

~~~sql
SELECT @@session.time_zone;
SELECT @@session.sql_mode;
~~~

Some system variables can be assigned by scope:

~~~sql
SET SESSION time_zone = '+07:00';
~~~

`SET SESSION` changes the value for the current connection. `SET GLOBAL` changes the global value subject to MySQL rules and privileges; neither is equivalent to assigning a local variable in a stored routine. Whether a change persists across restarts depends on configuration mechanism and version.

## 6. SELECT ... INTO for receiving query results

`SELECT ... INTO` takes expressions from a single result row and assigns them sequentially to a variable list:

~~~sql
SELECT
    so.customer_id,
    so.total
INTO
    v_customer_id,
    v_total
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

Mapping is positional:

- The first expression is assigned to `v_customer_id`.
- The second expression is assigned to `v_total`.

Column aliases do not determine target variables. The number of expressions in `SELECT` must match the number of variables in `INTO`.

### 6.1. INTO does not return a result set to the caller

A regular `SELECT` sends a result set back to the client:

~~~sql
SELECT so.total
FROM sales_orders AS so
WHERE so.order_id = 1001;
~~~

`SELECT ... INTO` assigns data to variables and does not send that row as a regular result set:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = 1001;
~~~

This is a critical distinction when writing stored procedures. If the caller needs to receive data, use `OUT` parameters or a separate `SELECT` after processing. Do not confuse `SELECT ... INTO` with a `SELECT` used to return rows to the application.

### 6.2. Placement of INTO

MySQL allows placing `INTO` after the select list and before `FROM`:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

or placing it after `FROM`/`WHERE`:

~~~sql
SELECT so.total
FROM sales_orders AS so
WHERE so.order_id = p_order_id
INTO v_total;
~~~

In this article, placing `INTO` right after the select list is preferred for easy visual mapping to variables. Use one consistent style across the same codebase.

## 7. SELECT ... INTO must handle returned row counts

`SELECT ... INTO` is not a way to arbitrarily pick one row from many. The result must contain exactly one row so assignment is unambiguous.

| Rows returned by query | Behavior |
|---|---|
| 0 rows | Raises `No data` warning; in stored programs the `NOT FOUND` condition can be caught by a handler. Target variables are not assigned new values. |
| 1 row | Assigns expressions to variables in order. |
| More than 1 row | Raises error 1172: `Result consisted of more than one row`. |

This is the core rule when using `SELECT ... INTO`. Always constrain cardinality using a unique key, an aggregate, filter conditions, or an ordered row-selection strategy.

### 7.1. Zero-row case: variables retain old values

Suppose a variable currently holds `99`:

~~~sql
SET v_total = 99.00;

SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = 999999999;
~~~

If no row matches, `SELECT ... INTO` does not assign `NULL` to `v_total`; the variable keeps its previous value and raises a `No data` warning. If subsequent code uses `v_total` as if the query succeeded, it may mistakenly process the previous order's value.

Therefore, initialize variables before the query and handle `NOT FOUND` explicitly. Never inspect the leftover value in a variable to infer whether the query found a row.

### 7.2. Multiple-row case: do not rely on the first row

The following query can return multiple rows:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

If a customer has multiple orders, the statement raises error 1172. MySQL does not automatically pick the first row in physical order.

If the business logic needs total revenue, use an aggregate:

~~~sql
SELECT COALESCE(SUM(so.total), 0)
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

If the business logic needs the latest order, specify ordering and a limit:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
ORDER BY so.created_at DESC, so.order_id DESC
LIMIT 1;
~~~

An `ORDER BY` with a unique key as a tie-breaker makes row selection deterministic. `LIMIT 1` is an intentional business choice: pick one row according to the stated order, not a way to hide cardinality errors when a query is expected to return a unique row.

## 8. Handling NOT FOUND in stored programs

When `SELECT ... INTO` finds no rows, MySQL raises the `NOT FOUND` condition (SQLSTATE class `02`). Inside a stored program, a handler can be declared to handle this case.

Example procedure returning both a value and a flag indicating whether the order was found:

~~~sql
DELIMITER //

CREATE PROCEDURE get_order_total(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_found BOOLEAN,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_total = NULL;

    SELECT so.total
      INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF v_not_found = FALSE THEN
        SET p_found = TRUE;
        SET p_total = v_total;
    END IF;
END//

DELIMITER ;
~~~

If `order_id` does not exist:

- The `CONTINUE` handler catches `NOT FOUND` and sets `v_not_found = TRUE`.
- Execution continues after the `SELECT ... INTO` statement.
- `p_found` remains `FALSE` and `p_total` remains `NULL` as initialized.

If exactly one row is found:

- The handler does not run.
- `v_not_found` stays `FALSE`.
- `p_found` is set to `TRUE` and `p_total` receives `total`.

Because `order_id` is the `PRIMARY KEY`, the query cannot return more than one row. If replaced by a non-unique `customer_id` condition, error 1172 still requires separate handling; a `NOT FOUND` handler does not catch multi-row errors.

### 8.1. Why variables and flags must be initialized

Target variables of `SELECT ... INTO` are not reassigned when no rows match. If a variable is reused without resetting the flag and value before querying, the result from a previous iteration could be mistaken for the current call's result.

Safe pattern:

1. Set `found = FALSE`.
2. Reset result variables to a meaningful default, usually `NULL`.
3. Execute `SELECT ... INTO`.
4. Use a `NOT FOUND` handler to flag missing rows.
5. Only consume query values when the flag indicates a row was found.

### 8.2. Limiting handler scope

Handlers are block-scoped. In a large routine, place the query needing `NOT FOUND` handling inside its own `BEGIN ... END` block if the routine performs other operations that could also trigger `NOT FOUND`.

Example:

~~~sql
BEGIN
    DECLARE v_found BOOLEAN DEFAULT TRUE;
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;

    BEGIN
        DECLARE v_not_found BOOLEAN DEFAULT FALSE;
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_not_found = TRUE;

        SELECT so.total
          INTO v_total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id;

        IF v_not_found THEN
            SET v_found = FALSE;
        END IF;
    END;

    IF v_found THEN
        SET p_total = v_total;
    ELSE
        SET p_total = NULL;
    END IF;
END
~~~

In this example, `p_total` is an `OUT` parameter of the enclosing routine. The handler in the inner block wraps only the intended operation. This avoids accidentally catching `NOT FOUND` from another operation in the larger block.

## 9. SELECT aggregate ... INTO

An aggregate query without `GROUP BY` normally returns one row even when there are no source rows:

~~~sql
SELECT
    COUNT(*),
    SUM(so.total),
    AVG(so.total)
INTO
    v_order_count,
    v_sum_total,
    v_average_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

If the customer has no orders:

- `COUNT(*)` returns `0`.
- `SUM(total)` returns `NULL`.
- `AVG(total)` returns `NULL`.

Thus, target variables are still assigned from one aggregate row, though some expressions may hold `NULL`.

If business rules require totals to be `0` when there are no orders, use `COALESCE`:

~~~sql
SELECT
    COUNT(*),
    COALESCE(SUM(so.total), 0),
    COALESCE(AVG(so.total), 0)
INTO
    v_order_count,
    v_sum_total,
    v_average_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

Do not confuse these two cases:

- `SELECT ... INTO` with zero source rows and no aggregates: `NOT FOUND` occurs; variables keep old values.
- `SELECT` aggregate without `GROUP BY`: still returns one result row; `COUNT` can be `0` and `SUM`/`AVG` can be `NULL`.

If `GROUP BY` is present, the query can return multiple rows or zero groups. Standard `SELECT ... INTO` cardinality rules must then be applied.

## 10. Comparing SELECT ... INTO with SET (SELECT ...)

A scalar subquery result can be assigned using `SET`:

~~~sql
SET v_total = (
    SELECT so.total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id
);
~~~

This is a scalar subquery inside an expression. Behavior when row count is not one differs from `SELECT ... INTO`:

| Situation | `SELECT ... INTO` | `SET v = (SELECT ...)` |
|---|---|---|
| 1 row | Assigns value | Assigns value |
| 0 rows | `NOT FOUND`/`No data`; variable keeps old value | Scalar subquery returns `NULL`; variable is assigned `NULL` |
| Multiple rows | Error 1172 | Error: scalar subquery returns more than one row |

The difference in the 0-row case is crucial. If the variable should become `NULL` when no row matches, `SET` with a scalar subquery expresses that directly. If you need to distinguish "not found" from "found with a `NULL` column value," use a found flag or a clearer query pattern.

Do not pick syntax just because it is shorter. Choose based on intended behavior on missing rows and how the routine manages state.

### 10.1. Using COALESCE when a default value is needed

~~~sql
SET v_total = COALESCE(
    (
        SELECT so.total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id
    ),
    0
);
~~~

The expression above assigns `0` if the scalar subquery returns `NULL`, covering both "row not found" and "row exists with `total` equal to `NULL`." If these two cases have different business meanings, do not merge them with `COALESCE`.

## 11. Assigning multiple columns from a single row

`SELECT ... INTO` is useful when retrieving multiple attributes from the same row:

~~~sql
SELECT
    so.customer_id,
    so.status_code,
    so.total,
    so.created_at
INTO
    v_customer_id,
    v_status_code,
    v_total,
    v_created_at
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

The number of expressions must match the number of target variables. Each expression's data type must be compatible with its corresponding variable type.

For maintainability:

- Write the `SELECT` and `INTO` lists in the exact same order.
- Place each expression/variable pair on corresponding lines.
- Use table aliases for all columns.
- Use `v_` prefixes for variables and `p_` for parameters.
- Never rely on column order from `SELECT *`.

Do not use `SELECT * INTO` multiple variables because schema changes can alter column count or order, breaking the routine or mis-mapping values.

## 12. Type conversion rules during assignment

The source expression does not have to share the exact type of the target variable. MySQL converts the value according to the variable's type and SQL context.

Example:

~~~sql
DECLARE v_order_count INT DEFAULT 0;
DECLARE v_total DECIMAL(13, 2) DEFAULT 0;
DECLARE v_label VARCHAR(30) DEFAULT '';

SET v_order_count = '12';
SET v_total = '1250.75';
SET v_label = 2026;
~~~

MySQL can convert numeric strings to numbers and numbers to strings. However, do not rely on implicit conversion when formatting or precision matters. Use explicit `CAST` or `CONVERT` when needed:

~~~sql
SET v_total = CAST(p_input_total AS DECIMAL(13, 2));
SET v_label = CAST(p_year AS CHAR(4));
~~~

### 12.1. DECIMAL and rounding

A `DECIMAL` variable has a fixed precision and scale. When assigning a value with more decimal places than the variable's scale, MySQL may round or raise warnings/errors depending on value, context, and SQL mode.

~~~sql
BEGIN
    DECLARE v_amount DECIMAL(8, 2) DEFAULT 0;
    SET v_amount = 12.3456;
END
~~~

If business logic requires a specific rounding rule, apply `ROUND()` with an explicit scale before assigning:

~~~sql
SET v_amount = ROUND(p_amount, 2);
~~~

Never assume every environment shares the same SQL mode. Check `@@SESSION.sql_mode` when investigating differences across development, test, and production environments.

### 12.2. Out-of-range values

An `INT` variable cannot store every `BIGINT` value; `DECIMAL(8,2)` cannot represent numbers whose integer part exceeds precision limits; `VARCHAR(30)` cannot preserve strings longer than 30 characters.

Conversion outcomes can be warnings or errors depending on SQL mode and the specific case. For routines handling financial or identifier data:

- Declare target types with sufficient value range.
- Validate values before assignment.
- Use explicit `CAST` when needed.
- Inspect warnings and errors in test environments.
- Never rely on silent data truncation.

### 12.3. NULL and default values

A local variable without `DEFAULT` is initialized to `NULL`. You can declare explicit default values:

~~~sql
BEGIN
    DECLARE v_retry_count INT DEFAULT 0;
    DECLARE v_result DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_message VARCHAR(100) DEFAULT 'Pending';
END
~~~

Default values give the routine clear initial state. However, `DEFAULT` does not replace checking query outcomes; `SELECT ... INTO` returning zero rows still requires `NOT FOUND` handling if the routine needs to distinguish that case.

## 13. Variable SET and column UPDATE are two different operations

`SET` in a stored program assigns a variable:

~~~sql
SET v_status = 2;
~~~

`SET` inside `UPDATE` updates a table column:

~~~sql
UPDATE sales_orders AS so
SET status_code = 2
WHERE so.order_id = p_order_id;
~~~

The two statements do not substitute for each other:

- `SET v_status = 2` only changes a variable inside the routine.
- `UPDATE ... SET status_code = 2` modifies table data and is subject to transactions, locks, triggers, and constraints.

If `SELECT ... INTO` reads the current status into a variable, updating the table still requires a separate `UPDATE` statement:

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.order_id = p_order_id;

SET v_next_status = v_status + 1;

UPDATE sales_orders AS so
SET status_code = v_next_status
WHERE so.order_id = p_order_id;
~~~

The snippet above assumes the row exists and there is no concurrent update contention. In concurrent applications, reading and updating in two separate statements can suffer from race conditions; transactions, proper locking, or atomic conditional `UPDATE` statements are needed depending on business rules. This issue is not solved by variable assignment rules alone.

## 14. Avoid variable names matching column names

Stored routines allow variable names and column names to match, but doing so hurts SQL readability and leads to mistaken references.

In stored programs, local variable names can shadow unqualified column names in certain name-resolution contexts. Therefore, do not rely on MySQL guessing whether `total` refers to a variable or a column.

Confusing example:

~~~sql
BEGIN
    DECLARE total DECIMAL(13, 2) DEFAULT 0;

    SELECT total
    INTO total
    FROM sales_orders
    WHERE order_id = p_order_id;
END
~~~

The name `total` appears on both the column side and target variable side. Clearer version:

~~~sql
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
    INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;
END
~~~

Use consistent naming conventions:

| Element | Example convention |
|---|---|
| Parameter | `p_order_id` |
| Local variable | `v_total` |
| Table alias | `so` |
| Column | `so.total` |
| User variable | `@caller_total` |

Do not give variables the same names as columns, even if the current SQL compiles. A schema change or newly added column can later make the code ambiguous.

## 15. Safe result assignment process

Before writing `SELECT ... INTO`, answer four questions:

1. How many rows can the query return?
2. If zero rows match, should the variable retain its old value, become `NULL`, or raise a business error?
3. If multiple rows match, should you aggregate, pick one ordered row, or treat it as a data error?
4. Is each expression's type compatible with its target variable?

Then choose the assignment approach:

| Need | Suitable approach |
|---|---|
| Assign a literal or expression | `SET` |
| Assign multiple variables from known expressions | Multi-variable `SET` |
| Retrieve a single unique row from a table | `SELECT ... INTO` with a unique key |
| Retrieve one row by business order | `SELECT ... INTO` with `ORDER BY` and `LIMIT 1` |
| Retrieve an aggregate | Aggregate `SELECT ... INTO` |
| Missing row must become `NULL` | `SET` with scalar subquery or explicit `NOT FOUND` handling |
| Caller needs results | `OUT`/`INOUT` or separate `SELECT` result set |
| Hold state only inside routine | Local variable |
| Share values within the same session | User variable, used under control |

## 16. Comprehensive example: fetching data and calculating

The following procedure fetches order information, calculates tax, and returns the results. The example handles missing rows using a handler:

~~~sql
DELIMITER //

CREATE PROCEDURE quote_order(
    IN p_order_id BIGINT UNSIGNED,
    IN p_tax_rate DECIMAL(5, 2),
    OUT p_found BOOLEAN,
    OUT p_subtotal DECIMAL(13, 2),
    OUT p_tax DECIMAL(13, 2),
    OUT p_grand_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_subtotal = NULL;
    SET p_tax = NULL;
    SET p_grand_total = NULL;

    SELECT so.total
      INTO v_subtotal
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF v_not_found = FALSE THEN
        SET p_found = TRUE;
        SET p_subtotal = v_subtotal;
        SET p_tax = ROUND(v_subtotal * p_tax_rate / 100, 2);
        SET p_grand_total = p_subtotal + p_tax;
    END IF;
END//

DELIMITER ;
~~~

Calling the procedure:

~~~sql
CALL quote_order(
    1001,
    8.00,
    @found,
    @subtotal,
    @tax,
    @grand_total
);

SELECT @found, @subtotal, @tax, @grand_total;
~~~

If `order_id` does not exist, `@found` is `FALSE` and monetary outputs are `NULL`. If found, the routine assigns `subtotal`, `tax`, and `grand_total` in turn.

This example illustrates variable assignment; it does not replace verifying tax rules, currency, rounding, or access privileges in production systems.

## 17. Common errors when assigning results

| Error / situation | Cause | How to handle |
|---|---|---|
| `1329 No data` | `SELECT ... INTO` found no rows | Initialize variables/flags and handle `NOT FOUND` |
| `1172 Result consisted of more than one row` | `SELECT ... INTO` returned multiple rows | Use unique key, aggregate, or `ORDER BY ... LIMIT 1` per business rules |
| `1242 Subquery returns more than 1 row` | Scalar subquery in `SET` returned multiple rows | Fix condition, aggregate, or pick one ordered row |
| `1327 Undeclared variable` | Variable not `DECLARE`d or wrong scope/name | Check declaration and block scope |
| Unexpected `NULL` value | Source expression is `NULL` or scalar subquery returned no rows | Check `NULL` handling and default rules |
| Stale value reused | `SELECT ... INTO` found no rows so variable did not change | Reset variables and flags before each query |
| Conversion warning/error | Incompatible target type, precision loss, or out of range | Declare proper types, validate, `CAST`, and inspect SQL mode |
| Undefined result | Assigning and reading the same user variable in one `SELECT` | Use separate `SET` statements or local variable logic |

### 17.1. SELECT ... INTO finds no rows

~~~sql
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
    INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    SET p_result = v_total;
END
~~~

If no order is found, `v_total` may remain `0` or whatever value it held earlier. If the code does not check `NOT FOUND`, `p_result` may receive a value that does not reflect the current query.

### 17.2. Using LIMIT 1 to mask data errors

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
LIMIT 1;
~~~

This query avoids the multi-row error, but without `ORDER BY` the chosen row has no deterministic business order. If the latest order is truly needed:

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
ORDER BY so.created_at DESC, so.order_id DESC
LIMIT 1;
~~~

If business rules require `customer_id` to have at most one active order, enforce that via constraints or data design and allow multi-row errors to expose inconsistencies. Do not add `LIMIT 1` merely to hide data rule violations.

## 18. Practice lab

### 18.1. Preparing data

~~~sql
INSERT INTO sales_orders (
    order_id,
    customer_id,
    status_code,
    total,
    created_at
)
VALUES
    (1001, 501, 1, 1200.00, '2026-01-10 09:00:00'),
    (1002, 501, 2, 800.00,  '2026-01-12 10:00:00'),
    (1003, 502, 1, 250.00,  '2026-01-13 11:00:00');
~~~

### 18.2. Practicing SET

~~~sql
DELIMITER //

CREATE PROCEDURE demo_set_assignment(
    IN p_quantity INT,
    IN p_unit_price DECIMAL(13, 2),
    OUT p_line_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_gross DECIMAL(13, 2) DEFAULT 0;

    SET v_gross = p_quantity * p_unit_price;
    SET v_discount = ROUND(v_gross * 0.05, 2);
    SET p_line_total = v_gross - v_discount;
END//

DELIMITER ;

CALL demo_set_assignment(3, 100.00, @line_total);
SELECT @line_total;
~~~

Expected result is `285.00`: gross `300.00`, discount `15.00`.

### 18.3. Practicing SELECT ... INTO with a unique key

~~~sql
DELIMITER //

CREATE PROCEDURE demo_select_into(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_customer_id BIGINT UNSIGNED,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    SELECT so.customer_id, so.total
      INTO p_customer_id, p_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;
END//

DELIMITER ;

CALL demo_select_into(1001, @customer_id, @order_total);
SELECT @customer_id, @order_total;
~~~

With the sample data, the result is `customer_id = 501` and `total = 1200.00`.

### 18.4. Practicing handling missing rows

~~~sql
DELIMITER //

CREATE PROCEDURE demo_not_found(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_found BOOLEAN,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_total = NULL;

    SELECT so.total
      INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF NOT v_not_found THEN
        SET p_found = TRUE;
        SET p_total = v_total;
    END IF;
END//

DELIMITER ;

CALL demo_not_found(999999, @found, @total);
SELECT @found, @total;
~~~

Expected result: `@found = 0` and `@total` is `NULL`. Retry with `order_id = 1001` to observe the found branch.

### 18.5. Self-check questions

1. Why is `SET` suitable for assigning expression results while `SELECT ... INTO` is suitable for receiving query data?
2. If `SELECT ... INTO` returns 0 rows, does the target variable automatically become `NULL`?
3. What happens if `SELECT ... INTO` returns 2 rows?
4. When should you use an aggregate instead of `LIMIT 1`?
5. Why does `LIMIT 1` require `ORDER BY` when picking the newest row?
6. How do user variables differ from local variables in lifetime?
7. Why should you not assign and read the same user variable in expressions of the same `SELECT`?
8. When does `SET` with a scalar subquery behave differently from `SELECT ... INTO`?

## 19. Design rules to apply

- Declare local variables at the top of the block and choose data types with sufficient range.
- Use `v_` prefixes for local variables and `p_` for parameters.
- Use table aliases when referencing columns; avoid variable names matching column names.
- Use `SET` for calculations and explicit value assignments.
- Use `SELECT ... INTO` when a query is expected to return exactly one row or one aggregate row.
- Enforce cardinality via `PRIMARY KEY`, `UNIQUE`, aggregates, or business conditions.
- When picking one row from a multi-row set, use `ORDER BY` with a tie-breaker and `LIMIT 1`.
- Initialize variables and flags before `SELECT ... INTO` if the query might return no rows.
- Use a `NOT FOUND` handler when you need to distinguish missing rows from a `NULL` column value.
- Never use `LIMIT 1` to hide uniqueness violations.
- Use `CAST`/`CONVERT` or `ROUND` when controlling type conversions and precision.
- Restrict user variables inside routine logic; never rely on `SELECT` expression evaluation order.
- Distinguish `SET` on local variables from `UPDATE` on table columns.

## 20. Checklist before finalizing a routine

- [ ] Every local variable is `DECLARE`d before executable statements.
- [ ] Variable data types, precision, and scale match incoming data.
- [ ] Variable and parameter names cannot be confused with column names.
- [ ] `SET` is used for internal assignments and calculations.
- [ ] `SELECT ... INTO` has column and target variable lists matching position by position.
- [ ] `SELECT ... INTO` queries have well-defined cardinality.
- [ ] The 0-row case is handled via `NOT FOUND` or an appropriate mechanism.
- [ ] Variables are initialized before queries that may return zero rows.
- [ ] Multi-row cases are not masked with arbitrary `LIMIT 1`.
- [ ] Aggregates and `NULL`s are handled per business rules.
- [ ] Type conversions, rounding, and SQL mode have been considered.
- [ ] Code does not depend on user-variable assignment evaluation order inside `SELECT`.
- [ ] `OUT`/`INOUT` parameters are explicitly assigned before returning.
- [ ] Tested with found, not-found, and anomalous data cases.

## Conclusion

`SET` and `SELECT ... INTO` are two foundational tools for assigning results in MySQL stored programs. `SET` suits literals, parameters, and computed expressions; `SELECT ... INTO` suits loading values from a single query row into variables.

The most critical point is controlling cardinality and variable state. `SELECT ... INTO` with no matching rows does not clear old values; multiple rows raise an error. Therefore, routines must explicitly define missing-row behavior, use `NOT FOUND` handlers when appropriate, ensure queries return exactly one row, or intentionally aggregate/select an ordered row.

Combining accurate data types, clear naming conventions, `NULL` control, and explicit type conversions keeps stored program logic readable, testable, and resilient against unexpected data errors.
