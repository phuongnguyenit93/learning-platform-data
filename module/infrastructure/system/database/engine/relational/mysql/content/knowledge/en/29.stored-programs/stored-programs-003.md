# BEGIN/END, Nested Blocks, and Variable Scope

Stored programs in MySQL use `BEGIN ... END` blocks to group statements into a program body. Inside a block, you can declare local variables, conditions, cursors, and handlers; execute SQL statements; and structure logic with `IF`, `CASE`, and loops. When one block contains another, each block creates its own declaration scope. Understanding these boundaries helps avoid misordered declarations, using the wrong variable, and leaking state across invocations.

Within the `DATABASE_MYSQL` module, this lesson focuses on block syntax, declaration ordering, local variables and routine parameters, nested block scope, labels, and the difference between `BEGIN ... END` and statements that start a transaction.

## 1. BEGIN ... END is a statement block

`BEGIN ... END` wraps a group of statements executed sequentially. It appears in procedures, functions, triggers, events, and nested blocks inside stored program bodies.

Minimal example:

~~~sql
BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT 'Hello MySQL';
    SELECT v_message AS message;
END
~~~

This illustrates a body inside a stored program; a `BEGIN ... END` compound statement is not a standalone script that runs directly like a session-level `SELECT`. A block typically has declarations at the top, followed by executable statements. A block can contain multiple SQL statements, flow-control statements, and sub-blocks. When MySQL reaches `END`, the scope of the current block ends.

`BEGIN ... END` in a stored program is block syntax, not an automatic transaction opener. To start a transaction, use `START TRANSACTION` in a permitted context. Do not assume that seeing `BEGIN` means data is already protected by a transaction.

## 2. Creating a procedure with a BEGIN ... END body

Example of a stored procedure calculating a customer's total order value:

~~~sql
DELIMITER //

CREATE PROCEDURE get_customer_order_total(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_total DECIMAL(14,2) DEFAULT 0.00;

    SELECT COALESCE(SUM(total_amount), 0.00)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    SELECT
        p_customer_id AS customer_id,
        v_total AS order_total;
END//

DELIMITER ;
~~~

The procedure receives an input parameter, declares a local variable, assigns the query result to the variable, and returns a result set. `DELIMITER` is a MySQL command-line client directive to change the statement terminator when sending the routine definition; it is not an SQL statement executed by the server.

Without changing the delimiter in the MySQL CLI, the first semicolon inside the procedure body may cause the client to send the `CREATE PROCEDURE` statement prematurely. In MySQL Workbench or other tools, how delimiters are configured may vary by editor.

## 3. General structure of a block

A compound statement block has the form:

~~~sql
[block_label:] BEGIN
    -- Declarations must be at the top of the block
    DECLARE ...;
    DECLARE ...;

    -- Executable statements
    statement_1;
    statement_2;
END [block_label]
~~~

Labels at the beginning and end are optional. If both are specified, the ending label must match the opening label. Labels are useful for identifying the exact block or loop targeted by `LEAVE`/`ITERATE`.

Elements that can appear inside a block body:

- Local variable declarations via `DECLARE`.
- Named condition, cursor, and handler declarations.
- Variable assignments via `SET`.
- Query result assignments via `SELECT ... INTO`.
- DML/DDL statements allowed in the routine type being written.
- Control structures such as `IF`, `CASE`, `LOOP`, `WHILE`, and `REPEAT`.
- Nested `BEGIN ... END` blocks.

## 4. Declaration order within each block

Declarations must precede the first executable statement in the same block. MySQL requires the following declaration group order:

1. Local variables and named conditions.
2. Cursors.
3. Handlers.

Example:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE no_row CONDITION FOR SQLSTATE '02000';
    DECLARE cur_orders CURSOR FOR
        SELECT order_id FROM orders;
    DECLARE CONTINUE HANDLER FOR no_row
        SET v_done = TRUE;

    -- Start executable statements after declarations.
    SET v_count = 0;
END
~~~

If a variable is declared after `SET`, `SELECT`, `IF`, or another executable statement in the same block, the routine will fail to compile. If you need to declare variables for a separate section of logic, create a nested `BEGIN ... END` block and declare them at the top of that sub-block.

Each nested block has its own declaration area. The declaration order rule applies independently to each block.

## 5. Declaring local variables with DECLARE

Local variables are declared with the syntax:

~~~sql
DECLARE variable_name data_type [DEFAULT value];
~~~

Example:

~~~sql
BEGIN
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(120) DEFAULT '';
    DECLARE v_order_count INT DEFAULT 0;
    DECLARE v_total_amount DECIMAL(14,2) DEFAULT 0.00;
    DECLARE v_is_valid BOOLEAN DEFAULT TRUE;

    SET v_customer_id = 42;
    SET v_customer_name = 'Nguyen An';
    SET v_order_count = 3;
    SET v_total_amount = 1250.50;
END
~~~

A variable declared without `DEFAULT` starts with `NULL`. If logic requires a defined initial value, declare `DEFAULT` or assign explicitly before reading the variable.

The variable's data type should match the column and operations:

| Need | Commonly used type |
|---|---|
| Non-negative integer ID | `BIGINT UNSIGNED` |
| Quantity / count | `INT` or `BIGINT` |
| Money and exact decimals | `DECIMAL(p,s)` |
| Name or code string | `VARCHAR(n)` |
| Date | `DATE` |
| Timestamp without timezone | `DATETIME` |
| Boolean flag | `BOOLEAN` (alias for `TINYINT(1)`) |

A local variable exists only during routine execution and within the scope of the block that declared it. It is neither a table column nor a session user variable.

## 6. Assigning values to variables

### Using SET

`SET` is the direct way to assign an expression:

~~~sql
BEGIN
    DECLARE v_subtotal DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_tax_rate DECIMAL(5,4) DEFAULT 0.1000;
    DECLARE v_tax DECIMAL(12,2) DEFAULT 0.00;

    SET v_subtotal = 250.00;
    SET v_tax = v_subtotal * v_tax_rate;
END
~~~

Multiple variables can be assigned in one `SET` statement:

~~~sql
SET v_min = 10, v_max = 100;
~~~

### Using SELECT ... INTO

`SELECT ... INTO` retrieves values from a query and assigns them into variables:

~~~sql
BEGIN
    DECLARE v_customer_name VARCHAR(120) DEFAULT NULL;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = 42;
END
~~~

The query should return exactly one row. If it returns no rows, MySQL raises a `NOT FOUND` warning and the variable retains its previous value; if it returns more than one row, MySQL raises an error. Therefore, use a unique key in the condition, an appropriate aggregate, or intentional result limiting. Do not use `LIMIT 1` to mask a query that ought to be unique if business rules require detecting duplicate data.

Example of an aggregate that always returns one row:

~~~sql
SELECT COALESCE(SUM(total_amount), 0.00)
INTO v_total
FROM orders
WHERE customer_id = p_customer_id;
~~~

When there are no orders, `SUM` returns `NULL`; `COALESCE` turns it into `0` so the variable receives a meaningful value.

## 7. Routine parameters and local variables

Procedures can accept parameters in three modes:

| Mode | Data direction | Meaning |
|---|---|---|
| `IN` | Caller -> routine | Input; the routine reads the parameter value |
| `OUT` | Routine -> caller | The routine assigns a result for the caller to receive |
| `INOUT` | Bidirectional | Caller passes an initial value; routine can modify and return it |

Example procedure using `OUT`:

~~~sql
DELIMITER //

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Calling the procedure:

~~~sql
CALL count_customer_orders(42, @order_count);
SELECT @order_count;
~~~

`@order_count` is a session user variable used to receive the `OUT` parameter in the SQL client call example. It differs from a local variable `v_total` declared with `DECLARE` inside the routine.

Stored function parameters in MySQL are inputs; do not declare `OUT` or `INOUT` modes for function parameters. `OUT`/`INOUT` modes are used with stored procedures.

Example `INOUT` receiving an initial value and returning the modified value:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_ten_percent_bonus(
    INOUT p_amount DECIMAL(14,2)
)
BEGIN
    SET p_amount = p_amount * 1.10;
END//

DELIMITER ;
~~~

Calling the procedure:

~~~sql
SET @amount = 100.00;
CALL apply_ten_percent_bonus(@amount);
SELECT @amount AS amount_after_bonus;
~~~

Parameters are scoped across the entire routine body; local variables are scoped to the block where they are declared and its sub-blocks.

## 8. Variable scope within a block

A variable can only be referenced in the block where it was declared and in sub-blocks nested inside it. When a block ends, local variables belonging to that block cease to exist.

Example:

~~~sql
BEGIN
    DECLARE v_outer_total DECIMAL(12,2) DEFAULT 100.00;

    SET v_outer_total = v_outer_total + 25.00;
    SELECT v_outer_total AS total_before_inner_block;

    BEGIN
        DECLARE v_inner_discount DECIMAL(12,2) DEFAULT 10.00;
        DECLARE v_inner_total DECIMAL(12,2) DEFAULT 0.00;

        SET v_inner_total = v_outer_total - v_inner_discount;
        SELECT v_inner_total AS total_after_discount;
    END;

    -- v_outer_total is still in scope.
    SELECT v_outer_total AS total_after_inner_block;

    -- v_inner_discount and v_inner_total are no longer accessible here.
END
~~~

A sub-block can read variables declared in its parent block. The parent block cannot read variables that exist only inside a sub-block after the sub-block ends.

## 9. Same-named variables in nested blocks

A sub-block can declare a variable with the same name as a variable in a parent block. In that case, the name inside the sub-block references the nearest declared variable; the outer variable is shadowed within the overlapping scope.

Example:

~~~sql
BEGIN
    DECLARE v_message VARCHAR(40) DEFAULT 'outer';

    BEGIN
        DECLARE v_message VARCHAR(40) DEFAULT 'inner';
        SELECT v_message AS current_message;
    END;

    SELECT v_message AS current_message;
END
~~~

Inside the sub-block, `SELECT` returns `inner`. After the sub-block's `END`, the outer `SELECT` returns `outer`. The outer variable is not overwritten; it is merely temporarily shadowed during name resolution in the sub-block.

Although MySQL allows this syntax, avoid giving nested variables the same name unless there is a clear reason. Using consistent prefixes like `p_` for parameters, `v_` for local variables, and role-descriptive names helps prevent confusion.

## 10. Nested blocks to isolate temporary variables

Sub-blocks are useful when a section of logic needs its own intermediate variables:

~~~sql
BEGIN
    DECLARE v_order_id BIGINT UNSIGNED DEFAULT 9001;
    DECLARE v_final_amount DECIMAL(12,2) DEFAULT 0.00;

    BEGIN
        DECLARE v_subtotal DECIMAL(12,2) DEFAULT 500.00;
        DECLARE v_discount DECIMAL(12,2) DEFAULT 50.00;
        DECLARE v_tax DECIMAL(12,2) DEFAULT 45.00;

        SET v_final_amount = v_subtotal - v_discount + v_tax;
    END;

    SELECT
        v_order_id AS order_id,
        v_final_amount AS final_amount;
END
~~~

`v_subtotal`, `v_discount`, and `v_tax` are only needed in the internal calculation, so they are placed inside the sub-block. `v_final_amount` is declared in the parent block because it is needed after the sub-block ends.

This is a scope-structuring technique; it does not create a transaction or savepoint. If an SQL statement in a sub-block modifies data, commit/rollback behavior still depends on the transaction/session and the table's storage engine.

## 11. Labels for BEGIN ... END

Blocks can be given labels:

~~~sql
main_block: BEGIN
    DECLARE v_count INT DEFAULT 0;

    inner_block: BEGIN
        SET v_count = v_count + 1;
    END inner_block;

    SELECT v_count;
END main_block
~~~

The opening and closing labels must match if both are specified. Labels help flow-control statements target the right block, especially when multiple loops or blocks are nested.

`LEAVE label` exits the block or loop carrying that label. Example:

~~~sql
main_block: BEGIN
    DECLARE v_amount DECIMAL(12,2) DEFAULT 0.00;

    IF v_amount <= 0 THEN
        LEAVE main_block;
    END IF;

    SELECT 'This statement is skipped';
END main_block
~~~

When the condition is true, `LEAVE main_block` terminates `main_block` and the remaining statements inside the block are skipped. If the routine has additional logic after the block, execution continues at the statement immediately following `END`.

`ITERATE label` skips the rest of the current loop iteration and begins the next one; it applies only to labeled `LOOP`, `WHILE`, or `REPEAT` constructs, not to repeat an ordinary `BEGIN` block.

## 12. BEGIN ... END blocks inside IF and loops

Control structures can contain a compound block to declare their own variables:

~~~sql
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT 'PENDING';

    IF v_status = 'PENDING' THEN
        BEGIN
            DECLARE v_message VARCHAR(100) DEFAULT 'Waiting for processing';
            SELECT v_message AS detail;
        END;
    ELSE
        SELECT 'No action required' AS detail;
    END IF;
END
~~~

The sub-block allows `v_message` to be declared right in the scope where it is needed. Trying to `DECLARE` a variable directly after an executable statement in the same block causes a MySQL error because the declaration is no longer at the top of the block.

Example with a loop:

~~~sql
BEGIN
    DECLARE v_counter INT DEFAULT 0;

    counter_loop: WHILE v_counter < 3 DO
        BEGIN
            DECLARE v_step_message VARCHAR(40);

            SET v_counter = v_counter + 1;
            SET v_step_message = CONCAT('Step ', v_counter);
            SELECT v_step_message AS progress;
        END;
    END WHILE counter_loop;
END
~~~

Each time the sub-block is entered, `v_step_message` is scoped to that iteration's block execution. `v_counter` belongs to the outer block, so it persists across loop iterations.

## 13. Local variables vs. session user variables

MySQL has two types of variables that are frequently confused:

| Characteristic | Local variable | User-defined variable |
|---|---|---|
| How declared | `DECLARE v_name TYPE` | Direct assignment `@name := value` |
| Scope | Declaring block/routine | Current connection session |
| Lifetime | While the block/routine is active | Until the session ends |
| Requires `DECLARE` | Yes | No |
| Used for | Internal routine state | Sharing values across SQL statements in the same session |

Session variable example:

~~~sql
SET @current_customer_id = 42;

SELECT *
FROM orders
WHERE customer_id = @current_customer_id;
~~~

Inside a routine, prefer local variables:

~~~sql
BEGIN
    DECLARE v_customer_id BIGINT UNSIGNED DEFAULT 42;

    SELECT *
    FROM orders
    WHERE customer_id = v_customer_id;
END
~~~

Do not use `@variable` instead of local variables in routine logic just for shorter syntax. User variables persist per connection; with connection pooling, stale values can remain on a reused connection and cause unintended state dependencies.

## 14. Avoiding variable names matching column names

Avoid giving a local variable the same name as a column in an SQL statement. When variable and column names match, name-resolution rules can give the expression a meaning different from what the author intended.

Confusing example:

~~~sql
DECLARE customer_id BIGINT UNSIGNED;

SELECT customer_id
INTO customer_id
FROM customers
WHERE customer_id = customer_id;
~~~

In stored programs, local variable names are not resolved as unqualified column names; a local variable can shadow a column of the same name. The condition above therefore risks comparing the variable with itself rather than filtering by the column. Write names explicitly:

~~~sql
DECLARE v_customer_id BIGINT UNSIGNED;

SELECT c.customer_id
INTO v_customer_id
FROM customers AS c
WHERE c.customer_id = p_customer_id;
~~~

Using `p_` for parameters, `v_` for local variables, table aliases, and qualified column names makes SQL clearer and prevents conditions from accidentally comparing a variable to itself.

## 15. Statement blocks do not mean transactions

The following three concepts serve different purposes:

| Syntax | Purpose |
|---|---|
| `BEGIN ... END` | Group statements and create variable scope inside stored programs |
| `START TRANSACTION` | Begin a transaction |
| `COMMIT / ROLLBACK` | End a transaction by confirming or discarding uncommitted changes |

Example block with multiple SQL statements:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;

    SELECT COUNT(*)
    INTO v_count
    FROM orders;

    SELECT v_count AS order_count;
END
~~~

The block above does not start a transaction automatically. If multiple data operations must belong to an atomic unit, design an explicit transaction according to stored procedure and storage engine rules. Also remember that certain stored program types such as functions and triggers have restrictions on transaction control; do not copy `START TRANSACTION`/`COMMIT` statements into every routine type.

## 16. Complete procedure example using nested blocks

Example procedure computing the net amount after discount for an order. The total variable is declared in the outer block because it is needed for returning the result; the temporary discount variable is declared only inside the sub-block.

~~~sql
DELIMITER //

CREATE PROCEDURE calculate_order_net_amount(
    IN p_order_id BIGINT UNSIGNED,
    IN p_discount_rate DECIMAL(5,4),
    OUT p_net_amount DECIMAL(14,2)
)
main_block: BEGIN
    DECLARE v_subtotal DECIMAL(14,2) DEFAULT 0.00;

    IF p_discount_rate < 0 OR p_discount_rate > 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount rate must be between 0 and 1';
    END IF;

    SELECT COALESCE(SUM(quantity * unit_price), 0.00)
    INTO v_subtotal
    FROM order_items
    WHERE order_id = p_order_id;

    BEGIN
        DECLARE v_discount_amount DECIMAL(14,2) DEFAULT 0.00;

        SET v_discount_amount = v_subtotal * p_discount_rate;
        SET p_net_amount = v_subtotal - v_discount_amount;
    END;
END main_block//

DELIMITER ;
~~~

Calling the procedure:

~~~sql
CALL calculate_order_net_amount(9001, 0.1000, @net_amount);
SELECT @net_amount;
~~~

This example assumes the `order_items` table has columns `order_id`, `quantity`, and `unit_price`. `p_discount_rate` is validated to be between 0 and 1; `v_subtotal` exists throughout `main_block`; `v_discount_amount` exists only in the sub-block. The `OUT` parameter `p_net_amount` is where the routine returns the result to the caller.

In real applications, clearly define behavior when `order_id` does not exist or the order has no items. The `SUM` aggregate with no input rows returns `NULL`; `COALESCE` in the example turns that case into `0.00`. Business rules may require raising an error instead of returning `0`, in which case appropriate checks should be added.

## 17. Common errors when working with blocks and variables

| Error | Cause | How to fix |
|---|---|---|
| `DECLARE` after `SET`/`SELECT` | Declaration is not at the start of the block | Move `DECLARE` to the top or create a sub-block |
| Using sub-block variable after `END` | Variable is out of scope | Move the variable to the parent block if still needed |
| Accidentally shadowing outer variable | Inner and outer variables share a name | Name by role and use prefixes |
| Using `@variable` as a local variable | User variables are session-scoped | Use `DECLARE` for internal state |
| `SELECT ... INTO` returns multiple rows | Query does not guarantee one row | Use a unique key, aggregate, or handle multiple rows with a cursor |
| `SELECT ... INTO` returns no rows | `NOT FOUND`; variable keeps previous value | Initialize explicitly and handle `NOT FOUND` as required |
| Confusing `BEGIN` with `START TRANSACTION` | A statement block does not open a transaction | Use transaction control in permitted contexts |
| Opening/closing labels do not match | Block label syntax error | Use the same name or omit the closing label |
| `ITERATE` on a regular block | `ITERATE` is for loops only | Use `LEAVE` to exit a block or put logic in a loop |
| Variable name matches column name | SQL struggles to resolve intended reference | Use `p_`/`v_`, table aliases, and qualified column names |

## 18. Process for designing maintainable blocks

1. Split routines into blocks by unit of responsibility, avoiding overly long procedure bodies.
2. Declare variables in the smallest scope possible while still covering where they are used.
3. Place all `DECLARE` statements at the top of each block in the exact order: variables/conditions, cursors, handlers.
4. Use consistent prefixes for parameters and local variables.
5. Avoid shadowing variable names in sub-blocks unless genuinely needed.
6. Use `SELECT ... INTO` when a query guarantees a single row or a single-row aggregate.
7. Initialize variables before reading them to avoid relying on `NULL` or stale values.
8. Use meaningful labels when `LEAVE`/`ITERATE` is needed in nested structures.
9. Clearly separate block scope from transaction boundaries.
10. Check privileges and stored program type before adding transaction control.
11. Test routines via `CALL` with representative data and edge cases.
12. Document which variables are inputs, intermediates, and outputs so maintainers can trace data flow.

## 19. Practice exercises

1. Create a procedure with one `IN` parameter, one local variable, and one `SELECT ... INTO`.
2. Create two nested `BEGIN ... END` blocks; declare separate variables in each block and observe their scope.
3. Declare the same variable name in both parent and child blocks; observe shadowing.
4. Try placing a `DECLARE` after a `SET` statement in the same block and explain the error; then move the declaration to the top of the block or into a sub-block.
5. Create a procedure with an `OUT` parameter and receive the result via a session variable.
6. Create a procedure with an `INOUT` parameter, modify its value, and verify the result received by the caller.
7. Label a block and use `LEAVE` to exit the block when a condition is invalid.
8. Create a labeled `WHILE` loop and use `ITERATE` to skip a processing iteration.
9. Compare a `DECLARE` local variable with a `@name` user variable on the same connection; inspect session state when a connection is reused.
10. Write a procedure calculating an order total with a sub-block containing a discount variable, then explain why the intermediate variable cannot be referenced after the sub-block's `END`.

You complete this lesson when you can organize stored programs into clear blocks, declare items in the proper order, explain variable scope and shadowing, use `IN`/`OUT`/`INOUT` parameters, and accurately distinguish `BEGIN ... END` from transaction control. These rules form the foundation for reading and building procedures, functions, triggers, events, cursors, and handlers in subsequent lessons.
