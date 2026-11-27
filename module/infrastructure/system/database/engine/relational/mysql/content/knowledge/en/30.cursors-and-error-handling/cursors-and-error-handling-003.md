# OPEN, FETCH, CLOSE and Cursor Lifecycle Management

Cursors in stored programs allow MySQL to read the results of a `SELECT` statement one row at a time. The basic lifecycle consists of declaring the cursor, `OPEN` to open the results, `FETCH` to retrieve each row into local variables, and `CLOSE` when finished. Cursors are useful when each row requires a sequential processing step that is difficult to express in a set-based SQL statement, though they typically consume more resources and run slower than set-based operations.

In the DATABASE_MYSQL module, this lesson focuses on cursor declaration order, the meaning of OPEN/FETCH/CLOSE, detecting end-of-data using NOT FOUND, handling empty cursors, closing cursors on errors, and designing handler scope so you do not accidentally catch NOT FOUND conditions from other statements.

## 1. What Is a Cursor?

A cursor is a mechanism for sequentially traversing the rows returned by a `SELECT` statement inside a stored program. Instead of processing the entire result set with a single UPDATE, INSERT, or SELECT, the routine can retrieve each row, read its columns into local variables, and execute logic for that row.

Cursors in MySQL have important characteristics:

- Read-only: you cannot use a cursor to directly modify the current row via `UPDATE ... WHERE CURRENT OF` syntax.
- Nonscrollable: `FETCH` moves sequentially forward only; you cannot jump to a previous row or an arbitrary position.
- Asensitive: the server may or may not use a copy of the results; the routine should not rely on source table changes made while the cursor is open being reflected in a particular way.
- Bound to declaration scope: a cursor can only be used inside the block where it was declared and statements within that scope.

A cursor is not a result set returned to the application. It is an internal resource of the stored program used by the routine to traverse data.

## 2. Cursor Lifecycle

A cursor is used in the following sequence:

1. DECLARE CURSOR: declare the `SELECT` query that supplies the data.
2. DECLARE handler: prepare handling for NOT FOUND when FETCH reaches the end of rows, as well as any errors requiring cleanup.
3. OPEN: execute the cursor query and open the results for reading.
4. FETCH: retrieve the next row into target variables.
5. Check the end-of-data flag before using the newly fetched variables.
6. Repeat FETCH until NOT FOUND is raised.
7. CLOSE: close the cursor and release resources.

Diagram:

~~~mermaid
flowchart TD
    A[DECLARE cursor and handler] --> B[OPEN cursor]
    B --> C[FETCH next row]
    C --> D{Row available?}
    D -->|Yes| E[Process row]
    E --> C
    D -->|No: NOT FOUND| F[CLOSE cursor]
    F --> G[End block]
~~~

OPEN and CLOSE cannot be reversed. FETCH is only valid after OPEN and before CLOSE. Calling CLOSE on an unopened or already-closed cursor will cause an error.

## 3. Declaring a Cursor with DECLARE

Basic syntax:

~~~sql
DECLARE cursor_name CURSOR FOR select_statement;
~~~

The SELECT in a cursor declaration must return a result set. Do not place INTO local variables at the end of the cursor's SELECT; receiving row values is done via FETCH.

Example:

~~~sql
DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_id;
~~~

A cursor can reference parameters or local variables declared earlier in the same scope. In the example, `p_customer_id` is a procedure parameter. This condition ensures the cursor only traverses orders for a single customer.

The cursor's SELECT definition is fixed within the routine. A cursor is not a substitute for dynamic SQL to change table names or SELECT structure arbitrarily on each FETCH.

## 4. DECLARE Order Within a Block

MySQL requires all declarations to be at the start of the block and in the exact order:

1. Local variables and named conditions.
2. Cursors.
3. Handlers.

Example:

~~~sql
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
    -- Subsequent processing statements.
END
~~~

Do not place DECLARE CURSOR after OPEN, SET, SELECT, or any other executable statement. If a cursor is needed only for part of the processing, create a nested `BEGIN ... END` block and declare the cursor at the top of that inner block.

## 5. OPEN: Opening the Cursor and Starting the Query

OPEN executes the SELECT statement declared for the cursor and prepares the results for FETCH:

~~~sql
OPEN cur_orders;
~~~

Several points to remember:

- The cursor must be declared in the current scope.
- Do not OPEN an already-open cursor again.
- OPEN does not output rows to the caller; the routine must use FETCH.
- If the query returns no rows, OPEN can still succeed; the first FETCH is what raises NOT FOUND.
- Errors during SELECT execution can occur at OPEN; an appropriate SQLEXCEPTION handler can handle and propagate the error to the caller.

OPEN does not automatically start a separate transaction. The cursor's SELECT statement is governed by the current transaction, isolation level, and storage engine just like other queries in the session.

## 6. FETCH: Retrieving One Row into Variables

Syntax:

~~~sql
FETCH cursor_name INTO variable_name [, variable_name] ...;
~~~

The number of destination variables must match the number of columns in the cursor's SELECT, in the exact corresponding order. Variable data types should match the source columns to avoid unwanted conversions.

Example cursor returning two columns:

~~~sql
DECLARE v_order_id BIGINT UNSIGNED;
DECLARE v_amount DECIMAL(12,2);

DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM orders;

FETCH cur_orders INTO v_order_id, v_amount;
~~~

After a successful FETCH, `v_order_id` receives the first column and `v_amount` receives the second column of the current row. The next FETCH advances to the following row.

MySQL cursors do not support FETCH FIRST, LAST, PRIOR, or ABSOLUTE like scrollable cursors in some other DBMSs. Design the query with ORDER BY if deterministic processing order is needed.

## 7. NOT FOUND Handler to Detect End of Data

When FETCH has no more rows, MySQL raises the NOT FOUND condition (SQLSTATE class 02). The standard approach is to declare a CONTINUE HANDLER to set a flag:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

After FETCH, check the flag before processing the variables:

~~~sql
FETCH cur_orders INTO v_order_id, v_amount;

IF v_done THEN
    LEAVE read_loop;
END IF;

-- Process the row only when FETCH succeeded.
SET v_total = v_total + v_amount;
~~~

CONTINUE means that after the handler runs, execution resumes at the statement following the one that raised the condition. Therefore, the routine must check `v_done` itself and exit the loop. Without checking, it may reprocess leftover variable values from the previous FETCH.

Do not use EXIT HANDLER FOR NOT FOUND if you want to continue running cleanup logic after the last FETCH in the same block; an EXIT handler exits the block where the handler is declared. For standard read loops, a CONTINUE HANDLER paired with a done flag is easier to control.

## 8. Standard FETCH Loop

Basic pattern:

~~~sql
read_loop: LOOP
    FETCH cur_orders INTO v_order_id, v_amount;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Process the current row.
    SET v_total = v_total + v_amount;
END LOOP;
~~~

The `v_done` condition must be checked immediately after FETCH and before using the target variables. The final FETCH returns no row; the handler sets the flag, the loop exits, and the routine proceeds to CLOSE.

Do not write:

~~~sql
FETCH cur_orders INTO v_order_id, v_amount;
SET v_total = v_total + v_amount;
IF v_done THEN
    LEAVE read_loop;
END IF;
~~~

The snippet above processes the variables before checking whether FETCH failed. When data runs out, the target variables may still contain values from the previous FETCH, causing the last row to be added twice.

## 9. CLOSE: Closing the Cursor at the Right Time

After traversal finishes, call:

~~~sql
CLOSE cur_orders;
~~~

CLOSE ends the current usage of the cursor. After CLOSE, no further FETCH is allowed until the cursor is OPENed again. Cursors are also automatically closed by MySQL when the block declaring them ends, but explicit CLOSE should be used so resource lifecycles are readable and well-controlled.

Do not call CLOSE twice. Do not call CLOSE if OPEN did not succeed. In routines with multiple exit paths, ensure every path after OPEN closes the cursor before leaving the block.

## 10. Empty Cursors and Changing Data

A cursor may return 0 rows:

- OPEN still opens the cursor.
- The first FETCH raises NOT FOUND.
- The handler sets `v_done = TRUE`.
- The loop exits without processing any rows.
- CLOSE is still called.

Do not treat an empty cursor as an application error if business rules allow zero rows. If at least one row is mandatory, check after the loop and raise an appropriate business error.

Because cursors are asensitive, MySQL does not guarantee that the routine will see concurrent modifications to the source table in any fixed manner. Avoid updating/deleting the source rows themselves while traversing the cursor if the algorithm relies on a stable order or result set. If a stable working set is needed, establish a transaction/isolation level or snapshot the row keys into an appropriate staging table.

## 11. NOT FOUND Can Come from Other Statements

NOT FOUND is not raised solely by FETCH. A SELECT ... INTO returning no rows also raises NOT FOUND. If the same handler is declared in a block containing both a cursor and a SELECT ... INTO, the handler can unintentionally set `v_done` and cause the loop to terminate early.

Error-prone logic example:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_name VARCHAR(120);
    DECLARE cur_orders CURSOR FOR
        SELECT order_id FROM orders;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = -1;

    -- SELECT INTO with no rows already set v_done.
    -- The FETCH loop can exit even while the cursor still has rows.
END
~~~

A good solution is to restrict handler scope. Place the cursor loop inside its own child block where NOT FOUND is used solely for FETCH. If a SELECT ... INTO that might return no rows is needed, handle it in a separate block with its own handler or use a query form guaranteed to return one row, such as an aggregate, when appropriate.

## 12. Complete Example: Traversing Orders and Summing Totals

Suppose we have the table:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_order (customer_id, order_id)
) ENGINE=InnoDB;
~~~

The following procedure iterates over a customer's orders, counts the orders, and sums the total amount:

~~~sql
DELIMITER //

CREATE PROCEDURE summarize_customer_orders(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_order_count BIGINT DEFAULT 0;
    DECLARE v_total_amount DECIMAL(14,2) DEFAULT 0.00;

    BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
        DECLARE v_order_id BIGINT UNSIGNED;
        DECLARE v_order_amount DECIMAL(12,2);

        DECLARE cur_orders CURSOR FOR
            SELECT order_id, total_amount
            FROM orders
            WHERE customer_id = p_customer_id
            ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            IF v_cursor_open THEN
                CLOSE cur_orders;
                SET v_cursor_open = FALSE;
            END IF;
            RESIGNAL;
        END;

        OPEN cur_orders;
        SET v_cursor_open = TRUE;

        read_loop: LOOP
            FETCH cur_orders INTO v_order_id, v_order_amount;

            IF v_done THEN
                LEAVE read_loop;
            END IF;

            SET v_order_count = v_order_count + 1;
            SET v_total_amount = v_total_amount + v_order_amount;
        END LOOP;

        CLOSE cur_orders;
        SET v_cursor_open = FALSE;
    END;

    SELECT
        p_customer_id AS customer_id,
        v_order_count AS order_count,
        v_total_amount AS total_amount;
END//

DELIMITER ;
~~~

The outer block holds `v_order_count` and `v_total_amount` because the result needs to be returned after the cursor block ends. The inner block contains the cursor, FETCH variables, done flag, and handlers. When an SQLEXCEPTION occurs after the cursor has been opened, the EXIT HANDLER closes the cursor and calls RESIGNAL so the caller still receives the original error.

If there are no orders, the first FETCH raises NOT FOUND, `v_done` turns TRUE, the loop terminates, the cursor is closed, and the procedure returns a count of 0 and a total of 0.00.

Calling the procedure:

~~~sql
CALL summarize_customer_orders(42);
~~~

This example illustrates the cursor lifecycle. In real-world applications, counting and summing should be written using a single set-based query:

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0.00) AS total_amount
FROM orders
WHERE customer_id = 42;
~~~

Set-based queries are usually shorter, reduce row-by-row transfers through stored programs, and give the optimizer more opportunities to choose an efficient plan. Only use a cursor when each row genuinely requires sequential logic or interactions that cannot be reasonably expressed in set-based SQL.

## 13. Closing the Cursor on Errors

If a statement inside the loop raises an error, execution may leave the routine before reaching CLOSE. When explicit resource management is needed, declare an EXIT HANDLER FOR SQLEXCEPTION after the cursor declaration:

~~~sql
DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
DECLARE cur_items CURSOR FOR
    SELECT item_id FROM order_items;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_items;
        SET v_cursor_open = FALSE;
    END IF;
    RESIGNAL;
END;
~~~

After OPEN, set the flag:

~~~sql
OPEN cur_items;
SET v_cursor_open = TRUE;
~~~

After normal CLOSE:

~~~sql
CLOSE cur_items;
SET v_cursor_open = FALSE;
~~~

The flag reflects only a successful OPEN state in the routine's logic. If OPEN fails, the flag remains FALSE so the handler does not attempt to CLOSE an unopened cursor. If an error occurs after OPEN, the handler closes the cursor and calls RESIGNAL so the error is not swallowed.

Do not replace RESIGNAL with a status SELECT message and continue as if processing succeeded, unless the routine has an explicitly designed error contract. The caller needs to know the operation failed to decide whether to roll back or retry.

## 14. Transactions and Locking When Using Cursors

A cursor does not automatically start a transaction and does not automatically lock all rows it reads. The cursor's SELECT obeys the current transaction, isolation level, and storage engine.

With InnoDB:

- If autocommit is enabled and the caller has not explicitly started a transaction, standalone statements follow autocommit.
- If the caller has already started a transaction, the cursor query participates in the session's transaction context.
- A standard SELECT is typically a consistent read under the current isolation level.
- A cursor does not automatically turn a SELECT into `SELECT ... FOR UPDATE`.

Do not keep a cursor open while waiting on user input, making HTTP calls, or performing long-running external work outside the database. Holding transactions/cursors open for a long time can prolong snapshots, hold resources, and increase operational pressure.

If you need to lock rows to handle concurrency, design the transaction and locking reads explicitly, narrow the row range using indexes, process quickly, and commit/roll back cleanly. Do not rely on a read-only cursor to guarantee exclusive update access.

## 15. Performance and Practical Limits

Because cursors process row by row, they typically incur overhead for every FETCH and every operation inside the loop. With hundreds of thousands or millions of records, row-by-row processing can be orders of magnitude slower than a set-based SQL statement.

Before using a cursor, ask yourself:

- Can the loop be replaced by `UPDATE ... JOIN`, `INSERT ... SELECT`, or an aggregate?
- Can CASE, CTEs, or window functions express the rule?
- Does processing really need to happen row-by-row in order, or is only the final result needed?
- Can work be batched using an incrementing key instead of holding a very long-lived cursor?
- Does the cursor SELECT have indexes supporting WHERE and ORDER BY?

In the orders example, the index `(customer_id, order_id)` supports filtering by `customer_id` and traversing by `order_id`. An index does not eliminate per-row processing overhead, but it can reduce the cost of locating and sorting the input data.

Do not add an index solely for a cursor if that index will significantly slow down the write workload. Measure with EXPLAIN on the cursor SELECT and benchmark the entire procedure on representative data.

## 16. Nested Cursors

You can declare a cursor inside a child block to traverse a second result set for each row of an outer cursor. When doing so, each cursor requires:

- Its own FETCH target variables.
- Its own done flag.
- A clearly scoped NOT FOUND handler.
- OPEN and CLOSE in the proper block.

Do not share a single done flag between two cursors if the two FETCH streams can finish independently. A NOT FOUND from the inner cursor can flip the outer cursor's flag and terminate the outer loop prematurely.

A safe organizational pattern is placing each cursor loop inside its own child block with its own NOT FOUND handler. However, nested cursors can generate a query count scaling with the number of outer rows (N+1 pattern). Whenever possible, replace them with a JOIN or set-based query.

## 17. Common Mistakes

| Mistake | Cause | Fix |
|---|---|---|
| FETCH before OPEN | Cursor has no open result set yet | Call OPEN before FETCH |
| Forgetting CLOSE | Cursor is not released promptly | CLOSE on all normal exit paths and clean up in handler |
| CLOSE on an unopened cursor | OPEN failed or cursor already closed | Track open state using a flag |
| Missing NOT FOUND handler | Exhausting rows on FETCH raises an error | Declare CONTINUE HANDLER and done flag |
| Processing variables before checking done | May reuse values from previous FETCH | Check the flag immediately after FETCH |
| NOT FOUND handler catches SELECT INTO | Same block contains a query finding no rows | Separate blocks and handler scope |
| FETCH variable count mismatches column count | Target list is incorrect | Verify column count and SELECT order |
| Using cursor for simple SUM/COUNT | Unnecessary row-by-row processing | Use set-based aggregates |
| Modifying source table while cursor is traversing | Asensitive results; behavior must not be assumed | Use staging or an explicit transaction/locking strategy |
| Not propagating errors to caller | Handler swallows SQLEXCEPTION | Clean up then RESIGNAL unless fully handled |
| Nested cursors sharing a done flag | One cursor's handler affects the other cursor | Use separate blocks, flags, and handlers |

## 18. Cursor Lifecycle Checklist

1. Confirm the problem genuinely requires row-by-row processing; prefer set-based when possible.
2. Choose a deterministic SELECT order if processing order matters.
3. Ensure WHERE and ORDER BY have indexes suitable for the workload.
4. Declare variables/conditions before cursors, and cursors before handlers.
5. Declare the NOT FOUND handler in a scope containing only the operations it should catch.
6. OPEN exactly once before FETCH.
7. FETCH into the exact number of variables in the exact column order.
8. Check the done flag immediately after FETCH.
9. CLOSE after the loop even if the cursor has 0 rows.
10. Use EXIT HANDLER to CLOSE on errors after OPEN and RESIGNAL if the error must be propagated.
11. Never CLOSE twice or FETCH after CLOSE.
12. Never hold cursors/transactions open while performing work outside the database.
13. Test behavior with an empty set, one row, multiple rows, and mid-loop errors.
14. Measure performance of the entire routine, not just the cursor's SELECT statement.

## 19. Practice Exercises

1. Create an `orders` table with `order_id`, `customer_id`, and `total_amount`; declare a cursor filtered by `customer_id`.
2. Write a procedure that OPENs the cursor, FETCHes one row, and CLOSEs it; verify the retrieved values.
3. Write a LOOP with a CONTINUE HANDLER FOR NOT FOUND and a `v_done` flag.
4. Test a `customer_id` with no orders; confirm the empty cursor still closes cleanly.
5. Intentionally place the sum calculation before checking `v_done`; observe the double-counting bug on the last row, then fix the order.
6. Add a `SELECT ... INTO` returning no rows in the same block; observe how the NOT FOUND handler can affect the cursor flag. Then isolate it in its own block.
7. Add an EXIT HANDLER FOR SQLEXCEPTION to close the cursor if a row-processing statement fails; use RESIGNAL so the caller receives the error.
8. Create two nested cursors with separate done flags and handlers; confirm the inner cursor finishing does not terminate the outer cursor early.
9. Compare a cursor-based procedure calculating COUNT/SUM with an aggregate SELECT; measure execution time on a sufficiently large dataset.
10. Run EXPLAIN on the cursor SELECT and evaluate indexes supporting the filter conditions and ORDER BY ordering.

You have completed this lesson when you correctly implement the DECLARE → OPEN → FETCH → CLOSE lifecycle, handle empty sets using NOT FOUND, ensure cursors are closed even on errors, and can explain when a cursor should be replaced with set-based SQL. Managing handler scope and resources properly is just as important as FETCH syntax.
