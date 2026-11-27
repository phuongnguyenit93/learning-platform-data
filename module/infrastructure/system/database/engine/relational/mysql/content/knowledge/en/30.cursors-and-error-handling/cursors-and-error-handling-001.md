# DECLARE: Declaration Order for Variables, Conditions, Cursors, and Handlers

In MySQL stored programs, `DECLARE` is used to declare local components of a `BEGIN ... END` block: variables, named conditions, cursors, and handlers. These declarations must appear at the beginning of the block, before any executable statements. Beyond placement, **the order among the groups also has rules**: declare variables and conditions first, cursors next, and handlers last.

This order lets MySQL know the data types and conditions used by the routine before compiling the cursor/handler logic. Placing `DECLARE` after `SET`, `SELECT`, `IF`, or `OPEN` will cause routine creation to fail. When you need to declare a component in the middle of execution flow, create a nested `BEGIN ... END` block and place the `DECLARE` statements at the start of the inner block.

This lesson focuses on the syntax, ordering, scope, and coordination of the four declaration types. Cursor examples are solely for illustrating the placement of `DECLARE CURSOR` and `NOT FOUND` handlers; prefer set-based SQL whenever an entire dataset can be processed in a single statement.

## 1. DECLARE Belongs to a BEGIN ... END Block

Stored procedures, functions, triggers, and events can contain compound statements:

```sql
BEGIN
    -- Local declarations go here.

    -- Executable statements come after the DECLARE group.
    SET @example_value = 1;
END
```

Each `BEGIN ... END` block has its own declaration scope. The routine body itself is a block; a nested block can declare its own variables, conditions, cursors, and handlers.

Do not place `DECLARE` after executable statements within the same block:

```sql
BEGIN
    SET @started = 1;

    -- Wrong: DECLARE cannot be placed after executable statements in this block.
    -- DECLARE v_count INT DEFAULT 0;
END
```

If you need a variable only for later processing, create a nested block at the appropriate position instead of inserting a late declaration into the current block.

## 2. Required Order of the Four Declaration Groups

Within each block, the general order is:

1. **Local variables and named conditions**: declare variables with `DECLARE variable`; declare conditions with `DECLARE condition_name CONDITION`.
2. **Cursors**: declare with `DECLARE cursor_name CURSOR FOR SELECT ...`.
3. **Handlers**: declare with `DECLARE handler_action HANDLER FOR condition ...`.
4. **Executable statements**: `SET`, `SELECT`, `OPEN`, `FETCH`, `IF`, `LOOP`, `INSERT`, `UPDATE`, `CALL`, etc.

Valid example:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE no_more_rows CONDITION FOR SQLSTATE '02000';

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR no_more_rows
        SET v_done = TRUE;

    OPEN cur_orders;
    -- Subsequent executable statements.
    CLOSE cur_orders;
END
```

In the first group, both variables and conditions must precede cursors/handlers; you may organize them in a readable order. Cursors must precede all handlers in the same block. You cannot declare a cursor after a handler or declare a variable after a cursor.

## 3. Declaring Local Variables

Syntax:

```sql
DECLARE variable_name data_type [DEFAULT value];
```

Example:

```sql
DECLARE v_customer_id BIGINT UNSIGNED;
DECLARE v_total DECIMAL(13, 2) DEFAULT 0.00;
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_message VARCHAR(200) DEFAULT 'pending';
```

Local variables without `DEFAULT` start with a value of `NULL`. Use a data type compatible with the column or expression the variable receives; avoid using `VARCHAR` for monetary amounts or quantities when exact calculations are required.

You can declare multiple variables of the same type in a single statement:

```sql
DECLARE v_min_id, v_max_id BIGINT UNSIGNED DEFAULT 0;
```

`DEFAULT` specifies the initial value. For routine variables, use simple, clear default values; if you need to compute a value with an expression or function, assign it after the declarations using `SET` or `SELECT ... INTO`.

### 3.1. Assigning Values to Variables

Use `SET`:

```sql
SET v_total = 1250.50;
SET v_done = FALSE;
```

Or use `SELECT ... INTO` when retrieving data from a table:

```sql
SELECT total_amount
INTO v_total
FROM orders
WHERE order_id = 1001;
```

`SELECT ... INTO` must return exactly one row. Zero rows raise a `NOT FOUND` condition; more than one row raises a cardinality error (typically error 1172). If a query may return multiple rows, use a cursor or write an appropriate aggregate/set-based query.

### 3.2. Local Variables vs. User-Defined Variables

Local variables are declared with `DECLARE` and exist only within the block/routine. User-defined variables have the `@` prefix, belong to the session/connection, and do not require `DECLARE`:

```sql
DECLARE v_count BIGINT DEFAULT 0;
SET v_count = 10;

SET @session_count = 10;
```

Do not use `@variable` in place of local variables in stored programs without a specific reason. User variables persist across statements within the same session and can retain values when connections are reused, causing state leakage across requests in a connection pool.

## 4. Declaring Named Conditions

Conditions let you assign a name to a MySQL error code or a SQLSTATE to make handlers easier to read.

Syntax:

```sql
DECLARE condition_name CONDITION FOR condition_value;
```

Where `condition_value` can be a MySQL error code or `SQLSTATE [VALUE] 'sqlstate_value'`.

Example:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
DECLARE no_data CONDITION FOR SQLSTATE '02000';
DECLARE invalid_order CONDITION FOR SQLSTATE '45000';
```

You can then use the condition name in a handler:

```sql
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate_found = TRUE;
```

A condition is just a name for a condition; `DECLARE ... CONDITION` itself does not handle errors. Error handling is performed by a separately declared handler.

### 4.1. MySQL Error Codes and SQLSTATE

- **MySQL error codes** are vendor-specific numbers, such as `1062` for duplicate key.
- **SQLSTATE** is a 5-character code following the SQL standard, such as `02000` for `NOT FOUND`, `23000` for integrity constraint violation, and `45000` for application-raised exceptions.
- **Condition name** is a local name mapped to an error code or SQLSTATE.

Example:

```sql
DECLARE duplicate_email CONDITION FOR 1062;
DECLARE business_rule_failed CONDITION FOR SQLSTATE '45000';
```

When distinguishing specific errors across versions/drivers, Java applications should still read the SQLSTATE and vendor error code from `SQLException` rather than only parsing the message string.

## 5. Declaring Cursors

A cursor allows reading rows sequentially one by one from a query inside a stored program.

Syntax:

```sql
DECLARE cursor_name CURSOR FOR select_statement;
```

Example:

```sql
DECLARE cur_pending_orders CURSOR FOR
    SELECT order_id, customer_id
    FROM orders
    WHERE status = 'pending'
    ORDER BY order_id;
```

Cursors must be declared after variables/conditions and before handlers in the same block. The cursor's `SELECT` statement does not include `INTO`; columns are retrieved later using `FETCH ... INTO`.

Cursors in MySQL are **asensitive**, **read-only**, and **nonscrollable**:

- Asensitive: the server may or may not create a copy of the data; do not rely on an assumption that the cursor is an independent snapshot.
- Read-only: cursors are for reading only; rows cannot be updated directly through the cursor as in some other DBMSs.
- Nonscrollable: rows can only be fetched in the forward direction; you cannot jump backward or to an arbitrary position.

Cursors typically require `OPEN`, `FETCH`, and `CLOSE` steps. Complete processing uses a `NOT FOUND` handler to detect when rows are exhausted.

## 6. Declaring Handlers

A handler specifies the action to take when a condition occurs within the block's scope.

General syntax:

```sql
DECLARE handler_action HANDLER
FOR condition_value [, condition_value] ...
statement;
```

Two primary actions:

- `CONTINUE`: runs the handler and then continues execution after the statement that raised the condition.
- `EXIT`: runs the handler and then exits the `BEGIN ... END` block where the handler is declared.

MySQL has `UNDO` syntax from historical grammar, but does not support the `UNDO` handler action; do not use it.

Example of a handler that continues after a duplicate key:

```sql
DECLARE v_duplicate_found BOOLEAN DEFAULT FALSE;
DECLARE duplicate_key CONDITION FOR 1062;

DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate_found = TRUE;
```

Example of a handler that exits the block on an exception:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_error_seen = TRUE;
    RESIGNAL;
END;
```

A handler can execute a single statement or a `BEGIN ... END` block. If the handler body is its own block, any local declarations in the handler body must appear at the start of that block and follow the same `DECLARE` ordering rules.

## 7. Condition Categories Used with Handlers

MySQL allows declaring handlers for general condition categories:

| Condition | Meaning |
| --- | --- |
| MySQL error code | A specific error, such as `1062` |
| `SQLSTATE 'xxxxx'` | A specific SQLSTATE |
| Condition name | A name declared via `DECLARE ... CONDITION` |
| `SQLWARNING` | SQLSTATE class `01` |
| `NOT FOUND` | SQLSTATE class `02`, commonly encountered when a cursor runs out of rows or `SELECT ... INTO` finds no rows |
| `SQLEXCEPTION` | SQLSTATE classes other than `00`, `01`, `02` |

Example:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

`NOT FOUND` does not only mean a cursor has run out of data. A `SELECT ... INTO` returning no rows also raises a condition in this category. When placing a broad handler in a block containing multiple read operations, distinguish the condition source so you do not confuse "a secondary lookup record was not found" with "the cursor has finished."

## 8. Precedence Order When Multiple Handlers Match

If a condition matches multiple handlers in the same scope, MySQL applies the following precedence:

1. A handler for a specific MySQL error code has the highest precedence.
2. A handler for a specific SQLSTATE has the next highest precedence.
3. Handlers for condition categories such as `SQLEXCEPTION`, `SQLWARNING`, and `NOT FOUND` have lower precedence.

For example, a duplicate key error can match a handler for error `1062`, a handler for SQLSTATE `23000`, and a general `SQLEXCEPTION` handler. The specific error code `1062` handler takes precedence.

If multiple handlers with the same precedence level match a condition, the selection may be indeterminate. Avoid declaring multiple handlers at the same precedence level for the same condition expecting MySQL to choose by line order. Design specific, clear conditions and use general handlers only as fallbacks.

## 9. Scope of Variables, Conditions, Cursors, and Handlers

Every declaration in a block is scoped to that block and its child blocks according to scoping rules. When a block ends, local variables cease to exist; cursors must be closed before leaving normal flow; handlers do not apply outside the scope in which they are declared.

Nested block example:

```sql
BEGIN
    DECLARE v_outer_count INT DEFAULT 0;

    SET v_outer_count = 1;

    BEGIN
        DECLARE v_inner_count INT DEFAULT 0;
        SET v_inner_count = v_outer_count + 1;
    END;

    -- v_outer_count is still usable here.
    -- v_inner_count is no longer in scope.
END
```

A child block can declare a variable with the same name as an outer variable, but this makes reading and maintenance error-prone. Prefer distinct names reflecting purpose (`v_outer_...`, `v_cursor_...`) rather than relying on shadowing.

### 9.1. DECLARE Inside IF, LOOP, and Handler Bodies

You cannot place `DECLARE` directly after `THEN`, `DO`, or in the middle of a sequence of statements in the same block. If you need a new scope, wrap that section in a compound statement:

```sql
IF p_use_cursor THEN
    BEGIN
        DECLARE v_local_limit INT DEFAULT 100;
        -- Statements using v_local_limit.
    END;
END IF;
```

Within this child block, all variables/conditions must still precede cursors, cursors must precede handlers, and all of them must precede executable statements.

## 10. NOT FOUND and Cursor Exhaustion

When `FETCH` has no more rows, MySQL raises a `NOT FOUND` condition (SQLSTATE class `02`). The common pattern is to declare a flag variable and a `CONTINUE` handler:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        -- Process the current row.
    END LOOP;

    CLOSE cur_orders;
END
```

The declaration order in the example is the key point: variables first, cursor next, handler last, and then `OPEN` and `FETCH`.

Because the handler is `CONTINUE`, after `FETCH` runs out of rows, execution continues at `IF v_done`. Using `EXIT` causes the handler to exit the enclosing block; that could make the routine leave the block before executing `CLOSE` in normal flow.

Here is the same pattern in a complete procedure using an `OUT` parameter to return the number of fetched rows:

```sql
DELIMITER //

CREATE PROCEDURE sp_count_orders_with_cursor(
    OUT p_processed_count BIGINT
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    SET p_processed_count = 0;
    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SET p_processed_count = p_processed_count + 1;
    END LOOP;

    CLOSE cur_orders;
END//

DELIMITER ;
```

Calling the procedure:

```sql
CALL sp_count_orders_with_cursor(@processed_count);
SELECT @processed_count;
```

This example illustrates declaration order. If the real goal is simply counting orders, `SELECT COUNT(*) INTO ... FROM orders` is simpler and more efficient than a cursor.

## 11. Avoiding a Shared NOT FOUND Handler for Multiple Purposes

A `NOT FOUND` handler in a large block can catch both cursor exhaustion and a `SELECT ... INTO` that returns no rows. The following example is prone to a logic bug:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(150);
    DECLARE cur_orders CURSOR FOR
        SELECT customer_id FROM orders;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_customer_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SELECT customer_name
        INTO v_customer_name
        FROM customers
        WHERE customer_id = v_customer_id;

        -- If the customer is not found, the same handler sets v_done = TRUE.
        -- The loop can be mistakenly treated as cursor exhaustion.
    END LOOP;

    CLOSE cur_orders;
END
```

In this example, `v_customer_id` is declared in the variable group at the top of the block to show valid syntax. The remaining issue is that a `SELECT ... INTO` not finding a customer can set `v_done`, stopping the loop for the wrong reason.

A safer design is to isolate the cursor loop in its own block, or place the secondary query in a nested block with its own `NOT FOUND` handler. Each source of `NOT FOUND` needs a clear handling intent.

Example isolating the secondary query:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(150);

    DECLARE cur_orders CURSOR FOR
        SELECT customer_id FROM orders ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_customer_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        BEGIN
            DECLARE v_customer_missing BOOLEAN DEFAULT FALSE;
            DECLARE CONTINUE HANDLER FOR NOT FOUND
                SET v_customer_missing = TRUE;

            SELECT customer_name
            INTO v_customer_name
            FROM customers
            WHERE customer_id = v_customer_id;

            IF v_customer_missing THEN
                SET v_customer_name = NULL;
            END IF;
        END;

        -- Continue processing the current row.
    END LOOP;

    CLOSE cur_orders;
END
```

The inner block's handler handles `NOT FOUND` from `SELECT ... INTO`; the outer block's handler only manages cursor exhaustion. The inner block's declarations also follow the exact order: variables first, handler after.

## 12. Named Conditions Make Handlers Easier to Read

Instead of repeating error codes in handlers, name the condition:

```sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_email CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_email
        SET v_duplicate = TRUE;

    INSERT INTO customers (customer_name, email, region_code, status)
    VALUES ('An', 'an@example.test', 'VN', 'active');

    IF v_duplicate THEN
        -- Handle the case where the email already exists.
    END IF;
END
```

The condition `duplicate_email` only has meaning in the block where it is declared and its child scopes. A condition name does not alter the underlying error code; it only makes the code easier to understand.

If you need to handle multiple distinct integrity errors, do not lump them all under a generic condition name like `data_error` if they require different behavior. Use names that reflect specific meanings and use a fallback `SQLEXCEPTION` handler to `ROLLBACK`/`RESIGNAL` when needed.

## 13. EXIT vs. CONTINUE in Handlers

These two actions differ in where execution resumes after the handler runs:

| Action | After the handler runs | Scope of impact |
| --- | --- | --- |
| `CONTINUE` | Continues at the statement immediately after the one that raised the condition | The block continues executing |
| `EXIT` | Exits the `BEGIN ... END` block containing the handler | Remaining statements in that block are skipped |

Example of `CONTINUE` using a flag to handle duplicates:

```sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_key CONDITION FOR 1062;
    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    INSERT INTO customers (customer_name, email, region_code, status)
    VALUES ('An', 'an@example.test', 'VN', 'active');

    IF v_duplicate THEN
        SELECT 'Email already exists' AS message;
    END IF;
END
```

Example of `EXIT` to roll back and rethrow an exception:

```sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- DML statements that may raise errors.
END
```

`EXIT` does not mean automatic rollback. If rollback is needed, you must explicitly write `ROLLBACK` inside the handler and only use it when the routine actually owns the transaction. If the transaction is managed by the caller, a handler inside the routine should not unilaterally roll back all of the caller's work unless the routine contract explicitly specifies it.

## 14. Declaring Multiple Cursors and Multiple Handlers

A block can declare multiple cursors. All cursors must be declared before any handler in the block:

```sql
BEGIN
    DECLARE v_done_a BOOLEAN DEFAULT FALSE;
    DECLARE v_done_b BOOLEAN DEFAULT FALSE;
    DECLARE v_id_a BIGINT UNSIGNED;
    DECLARE v_id_b BIGINT UNSIGNED;

    DECLARE cur_a CURSOR FOR
        SELECT id FROM source_a ORDER BY id;
    DECLARE cur_b CURSOR FOR
        SELECT id FROM source_b ORDER BY id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
    BEGIN
        -- A single shared handler cannot automatically tell which cursor was exhausted.
        SET v_done_a = TRUE;
        SET v_done_b = TRUE;
    END;

    -- Separate flows are needed if the two cursors have different lifecycles.
END
```

A shared handler like the above cannot distinguish whether cursor A or cursor B ran out of data; it sets both flags and can terminate a loop erroneously. For two cursors with independent lifecycles, use nested blocks so each cursor has its own `NOT FOUND` handler and flag, or design a JOIN/set-based query instead of two cursors.

If you declare multiple handlers for different conditions, place all of them after the cursor declarations. Avoid handlers at the same precedence level for the same condition because the choice may be indeterminate.

## 15. DECLARE Order in Nested Blocks

Each block has its own rules. For example, the outer block declares its variables and handlers, while the inner block declares its own cursor and handler:

```sql
BEGIN
    DECLARE v_total BIGINT DEFAULT 0;

    SET v_total = 10;

    BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_id BIGINT UNSIGNED;

        DECLARE cur_ids CURSOR FOR
            SELECT order_id FROM orders ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        OPEN cur_ids;
        -- FETCH inside the inner block.
        CLOSE cur_ids;
    END;

    -- Continue using v_total.
END
```

You do not need to declare the inner block's cursor in the outer block. Keeping declarations close to where they are used helps readers recognize scope and reduces the chance of an outer handler catching unintended conditions.

## 16. Common DECLARE Syntax Errors

| Error | Why it is wrong | How to fix |
| --- | --- | --- |
| Declaring a variable after `SET` | `DECLARE` must appear at the start of the block | Move declarations to the top or create a child block |
| Declaring a cursor before variables | Variables/conditions must be declared before cursors | Move the variable/condition group earlier |
| Declaring a handler before a cursor | Cursors must precede handlers | Move all cursors before handlers |
| Declaring a condition after a handler | Conditions belong to the first declaration group | Move the condition before cursors/handlers |
| Placing `DECLARE` directly in `IF`/`LOOP` | No new compound block to establish scope | Wrap the section needing declarations in `BEGIN ... END` |
| Using `DECLARE` in SQL outside a routine | This is stored program syntax | Use appropriate SQL/client variables or create a routine |
| Using an `UNDO` handler | MySQL does not support this action | Use `CONTINUE` or `EXIT` |
| Treating `NOT FOUND` solely as cursor end | `SELECT ... INTO` with no rows also raises this condition | Isolate scope/handlers or use separate flags |
| Making handlers overly broad | Can accidentally catch errors that require different handling | Use specific conditions and fallback handlers |

## 17. Debugging Routines and Checking Declarations

When routine creation fails, check in order:

1. Are `DECLARE` statements placed right at the top of the block after `BEGIN`?
2. Are variables and conditions declared before cursors?
3. Do all cursors precede handlers?
4. Are handlers placed before executable statements?
5. Are variable data types compatible with `FETCH`/`SELECT ... INTO` columns?
6. Does the cursor `SELECT` have the exact column count and order matching the `FETCH` variable list?
7. Are condition names declared in a scope visible to the handler?
8. Does a handler catch `NOT FOUND` or `SQLEXCEPTION` too broadly?
9. Are `BEGIN ... END` blocks closed properly and are labels/loops correct?
10. If using a command-line client, did you change `DELIMITER` so the entire routine is sent as a single statement?

View the routine definition:

```sql
SHOW CREATE PROCEDURE app_db.sp_process_orders\G
SHOW CREATE FUNCTION app_db.fn_line_total\G
```

View routine metadata:

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    SQL_DATA_ACCESS,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'app_db';
```

Metadata confirms that a routine was created and shows its declared attributes; it does not replace reading the full source or testing handler branches.

## 18. When to Use a Cursor vs. Set-Based SQL

Cursors process rows sequentially one by one. This is useful when each row requires sequential processing that is difficult to express in a single set-based SQL statement. However, cursors can generate many repeated operations, hold resources longer, and are harder to optimize than a single `UPDATE`, `INSERT ... SELECT`, `JOIN`, or aggregate query.

For example, instead of using a cursor to raise prices on all products in a category:

```sql
UPDATE products
SET price = ROUND(price * 1.05, 2)
WHERE category_id = 10;
```

is usually better than opening a cursor, fetching each product, and updating row by row.

Use cursors only when sequential processing is genuinely required, the dataset is bounded, appropriate indexes exist, and cursor open duration is controlled. Whenever possible, shift logic to set-based SQL so MySQL can optimize the entire dataset.

## 19. Practice Exercises

1. Create a procedure with two local variables; try placing a `DECLARE` after `SET` and observe the routine creation error.
2. Reorder the routine so variables and conditions precede cursors, and cursors precede handlers.
3. Declare a `duplicate_key` condition for error code `1062`; use a `CONTINUE` handler to set a flag.
4. Declare a `no_data` condition for SQLSTATE `02000`; use a `NOT FOUND` handler in a cursor loop.
5. Create a cursor reading `order_id`; write an `OPEN`/`FETCH`/`CLOSE` loop with a `v_done` flag.
6. Create an inner block inside the loop; use a separate `NOT FOUND` handler for `SELECT ... INTO` so it does not prematurely stop the cursor.
7. Create two cursors in one block; observe why a single shared `NOT FOUND` handler cannot distinguish which cursor was exhausted.
8. Compare `CONTINUE` and `EXIT` by observing which statements execute after a condition occurs.
9. Create a `SQLEXCEPTION` handler with `ROLLBACK` and `RESIGNAL`; verify that the caller receives the error.
10. Create two handlers with different precedence levels for the same error; observe the specific error code handler vs. `SQLEXCEPTION`.
11. Try placing `DECLARE` directly inside `IF` and then wrap it with `BEGIN ... END`.
12. Use `SHOW CREATE PROCEDURE` and `INFORMATION_SCHEMA.ROUTINES` to verify a routine after creation.
13. Rewrite a row-by-row cursor update into a set-based DML statement; compare statement count and execution time.

## 20. Key Takeaways

In every `BEGIN ... END` block, `DECLARE` must appear at the start of the block before executable statements. The group order is **variables and conditions first, cursors next, handlers last**. Local variables use `DECLARE variable type [DEFAULT value]`; named conditions use `DECLARE name CONDITION FOR error_code/SQLSTATE`; cursors use `DECLARE name CURSOR FOR SELECT`; handlers use `DECLARE CONTINUE|EXIT HANDLER FOR condition ...`.

Each nested block has its own scope and declaration order. `NOT FOUND` can occur when a cursor runs out of rows or when `SELECT ... INTO` finds no rows, so handlers must be isolated to match the exact condition source. `CONTINUE` resumes after the failing statement; `EXIT` leaves the enclosing block. Specific handlers take precedence over general categories; avoid multiple handlers with the same precedence for a single condition. Cursors must be declared before handlers, read using `OPEN`/`FETCH`, and closed using `CLOSE`; prefer set-based SQL whenever the entire dataset can be handled in a single statement.
