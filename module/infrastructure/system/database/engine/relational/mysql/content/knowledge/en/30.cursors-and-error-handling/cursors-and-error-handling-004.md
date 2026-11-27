# NOT FOUND Handler and Terminating the Read Loop

## Lesson Objectives

After this lesson, you will be able to:

- Declare a cursor using DECLARE CURSOR FOR SELECT.
- Properly execute the OPEN, FETCH, and CLOSE lifecycle.
- Understand the NOT FOUND condition and SQLSTATE 02000 when FETCH reaches the end of results.
- Use CONTINUE HANDLER to set a loop termination flag.
- Write a labeled loop, check the flag immediately after FETCH, and exit using LEAVE.
- Distinguish NOT FOUND caused by cursor exhaustion from NOT FOUND from SELECT ... INTO.
- Choose an appropriate handler scope so secondary queries do not unintentionally terminate the cursor loop.
- Use EXIT HANDLER to close the cursor when an error occurs and re-raise the original error.
- Handle empty cursors, multiple cursors, and out-of-order OPEN/FETCH/CLOSE scenarios.
- Recognize MySQL cursor limitations and choose set-based processing when appropriate.

Cursors allow a stored program to read SELECT results row by row. Each FETCH retrieves one row into declared variables. When no rows remain to be read, MySQL raises a NOT FOUND condition with SQLSTATE 02000. With an appropriate CONTINUE HANDLER, the handler sets a flag so the loop knows data is exhausted and exits safely.

The most important pattern is: declare the flag, declare the cursor, declare the handler; open the cursor; FETCH in a loop; check the flag immediately after FETCH; process the row; end the loop; close the cursor. Checking the flag before processing ensures the program does not reuse values from the previous FETCH once the cursor is exhausted.

## 1. Cursors and the Data Reading Lifecycle

A cursor is a stored program object used to traverse the rows returned by a SELECT statement one by one.

A cursor in MySQL has three characteristics:

- Asensitive: the server may or may not create a copy of the results; the program should not rely on an assumption that the result set is always an independent snapshot.
- Read-only: cursors are read-only and cannot be used to directly update rows via cursor position.
- Non-scrollable: reads forward only; cannot move back to a previous row or jump to an arbitrary position.

The cursor lifecycle consists of four stages:

1. DECLARE: defines the SELECT that the cursor will read.
2. OPEN: executes opening the cursor to begin reading results.
3. FETCH: retrieves each row sequentially into variables.
4. CLOSE: releases the cursor after reading finishes or when it is no longer needed.

Diagram:

~~~mermaid
flowchart TD
    A[DECLARE CURSOR] --> B[OPEN]
    B --> C[FETCH one row]
    C --> D{Row available?}
    D -->|Yes| E[Process current row]
    E --> C
    D -->|No: NOT FOUND| F[CONTINUE HANDLER sets flag]
    F --> G[LEAVE loop]
    G --> H[CLOSE CURSOR]
~~~

A cursor does not close automatically simply because the loop ended. The stored program must call CLOSE on all normal paths; if an error occurs while reading, there should be a cleanup handler.

## 2. Declaring a Cursor

Basic syntax:

~~~sql
DECLARE cursor_name CURSOR FOR select_statement;
~~~

Example:

~~~sql
DECLARE cur_orders CURSOR FOR
    SELECT
        order_id,
        order_status,
        total_amount
    FROM sales_order
    WHERE customer_id = p_customer_id
    ORDER BY order_id;
~~~

The SELECT statement in a cursor determines:

- The number of columns returned.
- The order of columns to be fetched.
- Which rows belong to the result set.
- Read order if ORDER BY is specified.

During FETCH, the number and order of variables must match the SELECT list. Variable data types should be compatible with the corresponding columns or expressions.

For example, if a cursor returns three columns in the order `order_id`, `order_status`, `total_amount`, then FETCH must have three variables in that exact order.

~~~sql
FETCH cur_orders
INTO v_order_id, v_order_status, v_total_amount;
~~~

Do not add INTO to the SELECT statement in the cursor declaration. INTO appears only in FETCH to receive each row.

### 2.1. Declaration Order in BEGIN ... END

MySQL requires declarations within a block to follow this order:

1. Local variables and conditions.
2. Cursors.
3. Handlers.

Valid example:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_amount DECIMAL(14, 2);

    DECLARE cur_orders CURSOR FOR
        SELECT order_id, total_amount
        FROM sales_order
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- Executable statements start here
END;
~~~

An invalid example is declaring a handler before a cursor or declaring a variable after executable statements have already appeared in the same block.

If you need another local variable for an inner block, you can declare it at the top of a nested `BEGIN ... END` block. Declaration rules apply separately to each block.

### 2.2. Parameters and Variables Used in a Cursor SELECT

The SELECT statement inside a cursor can reference routine parameters and local variables declared before the cursor.

~~~sql
DECLARE v_from_date DATETIME DEFAULT '2026-01-01 00:00:00';

DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = p_customer_id
      AND ordered_at >= v_from_date
    ORDER BY ordered_at, order_id;
~~~

Variable values are evaluated when the cursor is OPENed. Therefore, assign filter parameters or variables before OPEN. If you change a filter variable after the cursor is already open, do not expect the active result set being traversed to regenerate automatically.

Cursors are not a tool for constructing dynamic SELECT statements with PREPARE. The SELECT statement must be written directly in the cursor declaration.

## 3. OPEN, FETCH, and CLOSE

### 3.1. OPEN

OPEN starts the cursor:

~~~sql
OPEN cur_orders;
~~~

Only OPEN a cursor that has been DECLAREd in the current scope. Do not reopen a cursor while it is still open.

### 3.2. FETCH

FETCH retrieves the next row:

~~~sql
FETCH cur_orders
INTO v_order_id, v_order_status, v_total_amount;
~~~

On each successful FETCH, the variables receive the values of the current row. The next FETCH moves to the following row.

When the cursor has no more rows, FETCH raises the NOT FOUND condition. This is a normal signal for the loop to stop, not evidence that the cursor's SELECT query failed.

Without a matching handler, this condition goes unhandled and can terminate the stored program with an unhandled condition.

### 3.3. CLOSE

CLOSE terminates the cursor:

~~~sql
CLOSE cur_orders;
~~~

CLOSE releases resources associated with the cursor. Do not FETCH after CLOSE and do not CLOSE a cursor that has not been OPENed.

A cursor must be CLOSEd before leaving its owning block if it has been opened.

## 4. NOT FOUND and SQLSTATE 02000

NOT FOUND is the condition class used when no data is found. For FETCH operations, MySQL raises SQLSTATE 02000 when the cursor has run out of rows.

You can declare the handler directly:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Or declare it using SQLSTATE:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLSTATE '02000'
    SET v_done = TRUE;
~~~

Both approaches catch the same SQLSTATE 02000 condition.

You can name the condition before declaring the cursor:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE no_more_rows CONDITION FOR SQLSTATE '02000';

DECLARE cur_orders CURSOR FOR
    SELECT order_id
    FROM sales_order;

DECLARE CONTINUE HANDLER FOR no_more_rows
    SET v_done = TRUE;
~~~

Using NOT FOUND is usually easier to read when the goal is detecting that the cursor has finished reading results.

### 4.1. Why Must the Handler Be CONTINUE?

CONTINUE HANDLER handles the condition and then resumes execution at the statement immediately following the one that raised the condition.

With FETCH, that means:

1. FETCH attempts to read the next row.
2. The cursor is out of rows; MySQL raises NOT FOUND.
3. The handler sets `v_done = TRUE`.
4. Execution continues at the statement after FETCH.
5. IF checks `v_done` and LEAVEs the loop.

If an EXIT HANDLER is used in the same block, the condition exits the block containing the handler. The program may leave the procedure or reading block before executing the normal CLOSE. Therefore, the standard cursor-reading pattern uses CONTINUE HANDLER to control the loop via a flag.

### 4.2. The Loop Termination Flag

The flag variable is typically BOOLEAN or TINYINT:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
~~~

The handler sets the flag:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

The flag must be initialized to FALSE before opening the cursor. Once FETCH runs out of rows, the handler flips the flag to TRUE. The loop checks the flag and stops.

Do not reset the flag to FALSE immediately after FETCH before checking it; doing so erases the end-of-data signal and can cause the loop to behave incorrectly.

## 5. Standard Cursor Read Loop Pattern

This is the pattern to remember:

~~~sql
read_loop: LOOP
    FETCH cur_orders
    INTO v_order_id, v_total_amount;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Process the current row here
END LOOP;
~~~

Explanation:

- `read_loop` is the loop label.
- FETCH attempts to retrieve one row.
- If no rows remain, the handler sets `v_done` to TRUE.
- The IF check must immediately follow FETCH.
- `LEAVE read_loop` exits the exact labeled loop.
- Row processing runs only when FETCH succeeded.

### 5.1. Why Check the Flag Before Processing?

When FETCH runs out of rows, the target variables may still retain values from the previous successful FETCH. If the program processes the variables before checking `v_done`, the last row can be processed twice.

Correct order:

~~~sql
FETCH cur_orders INTO v_order_id;

IF v_done THEN
    LEAVE read_loop;
END IF;

SET v_count = v_count + 1;
~~~

Incorrect order:

~~~sql
FETCH cur_orders INTO v_order_id;

SET v_count = v_count + 1;

IF v_done THEN
    LEAVE read_loop;
END IF;
~~~

In the incorrect version, the final FETCH raises NOT FOUND, yet `v_count` is still incremented one extra time.

### 5.2. Cursor with Zero Rows from the Start

If the cursor's SELECT returns no rows at all, the very first FETCH raises NOT FOUND. The handler sets `v_done = TRUE`. The IF immediately after FETCH terminates the loop without executing the processing block.

Therefore, there is no need to check `COUNT(*)` before OPEN just to see if the cursor has rows. Let the first FETCH and the NOT FOUND handler handle the empty result set case.

## 6. Complete Example: Reading and Summarizing Orders

This example creates a practice table, opens a cursor for a specific customer, reads each order, and aggregates order count, total amount, and paid order count.

### 6.1. Create Sample Data

~~~sql
CREATE TABLE cursor_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    ordered_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_cursor_customer_order (customer_id, order_id)
) ENGINE = InnoDB;

INSERT INTO cursor_order_demo (
    order_id,
    customer_id,
    order_status,
    total_amount,
    ordered_at
)
VALUES
    (8101, 101, 'PAID',      1250000.00, '2026-02-01 09:15:00'),
    (8102, 101, 'PENDING',   2400000.00, '2026-02-03 11:30:00'),
    (8103, 101, 'PAID',       450000.00, '2026-02-18 10:20:00'),
    (8104, 102, 'PAID',       890000.00, '2026-02-08 14:00:00'),
    (8105, 102, 'CANCELLED',  760000.00, '2026-03-05 13:25:00'),
    (8106, 103, 'PENDING',   3400000.00, '2026-02-15 16:45:00');
~~~

### 6.2. Create a Procedure with a NOT FOUND Handler

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_summarize_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED,
    OUT p_total_amount DECIMAL(16, 2),
    OUT p_paid_count INT UNSIGNED
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_order_status VARCHAR(20);
    DECLARE v_amount DECIMAL(14, 2);

    DECLARE cur_orders CURSOR FOR
        SELECT
            order_id,
            order_status,
            total_amount
        FROM cursor_order_demo
        WHERE customer_id = p_customer_id
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_cursor_open THEN
            CLOSE cur_orders;
        END IF;
        RESIGNAL;
    END;

    SET p_order_count = 0;
    SET p_total_amount = 0.00;
    SET p_paid_count = 0;

    OPEN cur_orders;
    SET v_cursor_open = TRUE;

    read_loop: LOOP
        FETCH cur_orders
        INTO v_order_id, v_order_status, v_amount;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SET p_order_count = p_order_count + 1;
        SET p_total_amount = p_total_amount + v_amount;

        IF v_order_status = 'PAID' THEN
            SET p_paid_count = p_paid_count + 1;
        END IF;
    END LOOP;

    CLOSE cur_orders;
    SET v_cursor_open = FALSE;
END$$

DELIMITER ;
~~~

Key points to note:

- Variables and flags are declared before the cursor.
- The cursor is declared before the handlers.
- CONTINUE HANDLER FOR NOT FOUND sets `v_done` to TRUE when FETCH runs out of rows.
- EXIT HANDLER FOR SQLEXCEPTION closes the cursor if it is open, then calls RESIGNAL so the caller receives the original error.
- The `v_cursor_open` flag is set to TRUE after OPEN and FALSE after CLOSE.
- OUT variables are initialized before the loop.
- `IF v_done` comes right after FETCH, before any calculations.
- `ORDER BY order_id` makes read order deterministic by primary key.

### 6.3. Call the Procedure

~~~sql
CALL sp_summarize_customer_orders(
    101,
    @order_count,
    @total_amount,
    @paid_count
);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount,
    @paid_count AS paid_count;
~~~

Expected result with sample data:

| Metric | Result |
|---|---:|
| Order count | 3 |
| Total amount | 4,100,000.00 |
| PAID orders | 2 |

### 6.4. Test a Customer with No Orders

~~~sql
CALL sp_summarize_customer_orders(
    999,
    @order_count,
    @total_amount,
    @paid_count
);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount,
    @paid_count AS paid_count;
~~~

The result is 0, 0.00, and 0. The first FETCH raises NOT FOUND; the handler sets the flag, the loop executes LEAVE, and the procedure still CLOSEs the cursor.

## 7. NOT FOUND from SELECT ... INTO Also Triggers the Handler

A common pitfall is that NOT FOUND does not only appear when a cursor runs out of rows. A `SELECT ... INTO` that returns no rows also raises a NOT FOUND condition with SQLSTATE 02000.

Suppose the same block contains both a cursor loop and a `SELECT ... INTO` statement:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

If `SELECT ... INTO` finds no data, the handler above also sets `v_done = TRUE`. The cursor loop can exit prematurely on the next check or iteration even though the cursor still has rows.

This is a subtle logic bug that is hard to spot if you only test with data that always exists.

### 7.1. Isolating SELECT ... INTO with a Nested Block

Use a child block with its own NOT FOUND handler:

~~~sql
BEGIN
    DECLARE v_customer_name VARCHAR(100) DEFAULT NULL;
    DECLARE v_lookup_missing BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_lookup_missing = TRUE;

    SELECT c.customer_name
    INTO v_customer_name
    FROM customer AS c
    WHERE c.customer_id = p_customer_id;

    IF v_lookup_missing THEN
        SET v_customer_name = 'Unknown customer';
    END IF;
END;
~~~

The handler inside the child block handles NOT FOUND from `SELECT ... INTO`. It does not modify the outer block's `v_done` flag used for the cursor.

When the child block ends, its local handler also goes out of scope. The outer block's NOT FOUND handler remains active for detecting FETCH exhaustion.

### 7.2. Initialize Target Variables Before SELECT ... INTO

If `SELECT ... INTO` returns no rows, target variables retain their values from before the statement. Therefore, initialize variables before the query:

~~~sql
SET v_customer_name = NULL;
SET v_lookup_missing = FALSE;

SELECT c.customer_name
INTO v_customer_name
FROM customer AS c
WHERE c.customer_id = p_customer_id;
~~~

If there are no rows, the handler sets `v_lookup_missing` to TRUE and `v_customer_name` remains NULL.

### 7.3. Distinguishing Zero Rows vs. Multiple Rows

`SELECT ... INTO` has three cases to distinguish:

| SELECT Result | Condition/Outcome |
|---|---|
| Exactly one row | Assigns values to variables |
| Zero rows | NOT FOUND, SQLSTATE 02000; variables remain unchanged |
| More than one row | Error 1172, Result consisted of more than one row |

A NOT FOUND handler does not handle error 1172. If a query requires a unique row, use a unique key or verify conditions. If business logic only needs one latest row, use ORDER BY with a deterministic tie-breaker and LIMIT 1.

### 7.4. Alternative: Separate Handler per Block

Handler scope is the block where it is declared. You can use a child block for secondary queries, an outer block for the cursor, or create a dedicated child routine for lookups. The goal is for each handler to process only the conditions matching its responsibility.

Do not declare a single global NOT FOUND handler and share it across unrelated operations if the cursor termination flag could be set by mistake.

## 8. NOT FOUND vs. SQLWARNING and SQLEXCEPTION

MySQL classifies conditions by SQLSTATE:

- SQLWARNING: class 01.
- NOT FOUND: class 02.
- SQLEXCEPTION: all other error classes except classes 00, 01, and 02.

Consequently, SQLEXCEPTION does not replace a NOT FOUND handler. When FETCH exhausts a cursor, an EXIT HANDLER FOR SQLEXCEPTION does not catch the SQLSTATE 02000 condition.

Example:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_orders;
    END IF;
    RESIGNAL;
END;
~~~

The two handlers serve distinct purposes:

- NOT FOUND is a normal control signal to stop the loop.
- SQLEXCEPTION is an error-handling path to clean up and propagate the error back to the caller.

If multiple handlers could apply, MySQL selects the handler with more specific precedence. A handler for a specific MySQL error code takes precedence over a specific SQLSTATE; a specific SQLSTATE takes precedence over condition classes like NOT FOUND or SQLEXCEPTION. Avoid declaring overlapping handlers unnecessarily.

## 9. CONTINUE HANDLER vs. EXIT HANDLER

Handlers have two main behaviors to distinguish:

| Handler Type | After handling the condition |
|---|---|
| CONTINUE | Continues at the statement immediately after the one that raised the condition |
| EXIT | Exits the `BEGIN ... END` block containing the handler |

The cursor loop pattern uses CONTINUE because execution must proceed to `IF v_done` after FETCH.

EXIT HANDLER is commonly used for errors requiring block exit, such as closing the cursor and re-raising the error:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_orders;
    END IF;

    RESIGNAL;
END;
~~~

RESIGNAL re-raises the condition currently being handled so the caller receives the original error. If a handler only logs or sets a flag without RESIGNAL, the error can be swallowed; only do that when it is an explicitly designed error-handling contract.

### 9.1. Place Handlers in the Proper Scope

A handler applies only to statements in the block where it is declared and its child blocks, unless a more specific handler in a child block catches the condition first.

Therefore:

- Cursor handlers should reside in the block managing the cursor.
- Lookups that might return zero rows should be placed in a child block with their own handler.
- A secondary operation's handler should never alter the main loop's control flag.

## 10. Forms of Cursor Read Loops

### 10.1. LOOP and LEAVE

This is the most common and easiest-to-control pattern:

~~~sql
OPEN cur_orders;

read_loop: LOOP
    FETCH cur_orders INTO v_order_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Process row
END LOOP;

CLOSE cur_orders;
~~~

The advantage is clear flag placement and no processing of stale values after data runs out.

### 10.2. REPEAT

You can use REPEAT if processing is guarded by IF:

~~~sql
OPEN cur_orders;

read_loop: REPEAT
    FETCH cur_orders INTO v_order_id;

    IF NOT v_done THEN
        -- Process current row
        SET v_count = v_count + 1;
    END IF;
UNTIL v_done
END REPEAT;

CLOSE cur_orders;
~~~

REPEAT checks the termination condition after running the loop body. Therefore, the processing section must use `IF NOT v_done` to avoid processing variables that still hold old values after the last FETCH.

### 10.3. Why Is WHILE Less Direct?

WHILE checks the condition before running the loop body. However, to know whether there is a next row, the program must still execute FETCH. That typically requires an initial FETCH before WHILE and another FETCH at the end of each iteration.

If using WHILE, carefully design the initial FETCH, done flag, and subsequent FETCH. For those newer to cursors, `LOOP + FETCH + IF + LEAVE` is usually less error-prone.

## 11. Reading Multiple Cursors and Resetting the Flag

A procedure can declare multiple cursors. Each cursor has its own SELECT and lifecycle. If sharing a single done flag, you must reset the flag to FALSE before opening the next cursor.

Structure example:

~~~sql
SET v_done = FALSE;
OPEN cur_customers;

customer_loop: LOOP
    FETCH cur_customers INTO v_customer_id;

    IF v_done THEN
        LEAVE customer_loop;
    END IF;

    -- Process customer
END LOOP;

CLOSE cur_customers;

SET v_done = FALSE;
OPEN cur_orders;

order_loop: LOOP
    FETCH cur_orders INTO v_order_id;

    IF v_done THEN
        LEAVE order_loop;
    END IF;

    -- Process order
END LOOP;

CLOSE cur_orders;
~~~

If you forget to reset the flag, the second cursor will exit immediately on its first check because `v_done` is still TRUE from the previous cursor.

When multiple cursors operate in nested fashion, use separate flags for each cursor and properly scoped handlers to prevent one cursor from setting the termination flag for another.

## 12. Common Mistakes

| Mistake or Misconception | Reality | How to Handle |
|---|---|---|
| Cursor closes automatically when FETCH finishes | Cursor still requires CLOSE | Call CLOSE after the loop |
| NOT FOUND is a severe SQL error | Normal condition when FETCH exhausts data | Use CONTINUE HANDLER |
| Using EXIT HANDLER to stop a cursor loop | EXIT leaves the block containing the handler | Use CONTINUE and a done flag |
| Processing variables before checking done | Last FETCH may leave previous row values | `IF done` must follow FETCH immediately |
| Empty cursor needs COUNT before OPEN | First FETCH already raises NOT FOUND | Let the handler handle empty cursors |
| SQLEXCEPTION catches NOT FOUND | Class 02 does not belong to SQLEXCEPTION | Declare NOT FOUND separately |
| `SELECT ... INTO` with no rows is unrelated to cursor handler | It also raises SQLSTATE 02000 | Isolate lookups with child blocks or dedicated handlers |
| Forgetting to reset done for a second cursor | Flag remains TRUE from the previous cursor | Set FALSE before the next OPEN |
| FETCH before cursor is OPEN | Cursor is not ready for reading | OPEN before FETCH |
| FETCH after CLOSE | Cursor lifecycle has ended | Never FETCH after CLOSE |
| Opening a cursor twice | An open cursor cannot be OPENed again | CLOSE before reopening |
| Cursor can move back to previous row | MySQL cursors are non-scrollable | Design a new SELECT if re-traversal is needed |
| Cursor can update the current row | MySQL cursors are read-only | Use UPDATE with a key condition |
| Using a cursor for simple aggregations | Set-based SQL is usually more efficient | Use SUM, COUNT, UPDATE, or INSERT ... SELECT |
| ORDER BY does not need a secondary key | Multiple rows may share the same sort value | Add a unique key for deterministic order |

## 13. Performance and Practical Limitations

Cursors process row by row and typically cause repeated control transfers between SQL statements and stored programs. For calculations expressible in a single SQL statement, the set-based approach is usually shorter and faster.

Example without a cursor to compute sums:

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0.00) AS total_amount
FROM cursor_order_demo
WHERE customer_id = 101;
~~~

Instead of FETCHing each order and adding to a variable, use COUNT and SUM so MySQL processes the set as a whole.

Cursors are useful when each row needs a conditional processing sequence that cannot be expressed cleanly in set-based SQL, or when calling other per-row routines/logic. Even so, weigh row-by-row overhead, transaction length, locks, and data volume.

Cursors in MySQL are asensitive. The server may or may not materialize the results; do not depend on whether changes to the source table while the cursor is open will or will not appear in the current result set. If consistent behavior is required, design transactions and isolation levels deliberately.

## 14. Procedure for Building a Safe Cursor Loop

When writing a cursor-reading procedure:

1. Determine whether row-by-row processing is truly necessary or if set-based SQL can be used.
2. Write the cursor SELECT and select the minimal set of columns needed.
3. Add filter conditions and a deterministic ORDER BY if processing order matters.
4. Declare target variables before the cursor.
5. Declare the cursor after variables and conditions.
6. Declare CONTINUE HANDLER FOR NOT FOUND after the cursor.
7. Initialize the done flag to FALSE and initialize result variables.
8. OPEN the cursor.
9. FETCH into the exact number and order of variables.
10. Check done immediately after FETCH; LEAVE if out of rows.
11. Process the row only when FETCH succeeded.
12. CLOSE the cursor after the loop finishes.
13. If SQL exceptions can occur, use an EXIT HANDLER to CLOSE the cursor if open, then RESIGNAL.
14. If secondary `SELECT ... INTO` queries exist, use a separate handler block to avoid mistakenly setting the done flag.
15. Test empty cursors, single-row, multi-row, and mid-processing errors.

## 15. Practice Exercises

### Exercise 1: Cursor Reading Orders

Declare a cursor reading `order_id` and `total_amount` for a customer. FETCH each row and print results with SELECT or add to a total variable.

### Exercise 2: NOT FOUND Handler

Write a CONTINUE HANDLER FOR NOT FOUND setting `v_done = TRUE`. Explain when the handler is invoked inside the loop.

### Exercise 3: Empty Cursor

Call the procedure with a `customer_id` that has no orders. Confirm the first FETCH sets the done flag and does not run the row-processing section.

### Exercise 4: Detecting Double-Processing of the Last Row

Intentionally place `IF v_done` after the sum calculation. Compare the incorrect result with checking immediately after FETCH.

### Exercise 5: SELECT INTO in the Same Block

Add a `SELECT ... INTO` looking up the customer name inside the cursor procedure. Test with a nonexistent ID and observe the done flag being set. Then move the lookup into a child block with its own handler.

### Exercise 6: Distinguishing NOT FOUND and SQLEXCEPTION

Write two separate handlers. Verify that FETCH exhaustion is handled by NOT FOUND, while genuine SQL errors are caught by the SQLEXCEPTION handler.

### Exercise 7: Closing the Cursor on Error

Add an EXIT HANDLER FOR SQLEXCEPTION, a `cursor_open` flag, and RESIGNAL. Introduce an intentional error in the processing section and verify the cursor is closed before the error is returned to the caller.

### Exercise 8: Two Cursors Sharing a Flag

Declare two cursors, reading the first cursor and then the second. Try removing the statement that resets `v_done` and explain why the second cursor exits early.

### Exercise 9: LOOP vs. REPEAT

Write two versions reading the same cursor. Ensure the REPEAT version processes only when `v_done = FALSE`. Compare readability and the risk of double-processing the last row.

### Exercise 10: Replacing a Cursor with Set-Based SQL

Write a procedure using a cursor to calculate order count and total amount. Rewrite it using `COUNT(*)` and `SUM()`. Compare statement count, complexity, and execution time on a sufficiently large dataset.

## Conclusion

NOT FOUND with SQLSTATE 02000 is the signal MySQL uses to indicate a cursor has run out of rows. CONTINUE HANDLER sets the done flag; the loop checks the flag immediately after FETCH and executes LEAVE when needed. The cursor is OPENed before reading and must be CLOSEd after completion.

Remember three principles: declare variables before cursors and handlers; check the flag before processing data after FETCH; and manage NOT FOUND handler scope so `SELECT ... INTO` does not accidentally terminate the loop. When handling other errors, EXIT HANDLER can close an open cursor and then RESIGNAL to preserve the original error.

Cursors are useful for row-by-row processing logic, but set-based SQL should be the first choice for aggregations or updates that can operate on the entire dataset at once.

## References

- MySQL 8.4 Reference Manual — Cursors: https://dev.mysql.com/doc/refman/8.4/en/cursors.html
- MySQL 8.4 Reference Manual — DECLARE ... HANDLER Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-handler.html
- MySQL 8.4 Reference Manual — DECLARE ... CONDITION Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-condition.html
- MySQL 8.4 Reference Manual — DECLARE Statement: https://dev.mysql.com/doc/refman/8.4/en/declare.html
- MySQL 8.4 Reference Manual — FETCH Statement: https://dev.mysql.com/doc/refman/8.4/en/fetch.html
- MySQL 8.4 Reference Manual — OPEN Statement: https://dev.mysql.com/doc/refman/8.4/en/open.html
- MySQL 8.4 Reference Manual — CLOSE Statement: https://dev.mysql.com/doc/refman/8.4/en/close.html
- MySQL 8.4 Reference Manual — RESIGNAL Statement: https://dev.mysql.com/doc/refman/8.4/en/resignal.html
- MySQL 8.4 Reference Manual — Condition Handling and Scope: https://dev.mysql.com/doc/refman/8.4/en/handler-scope.html
