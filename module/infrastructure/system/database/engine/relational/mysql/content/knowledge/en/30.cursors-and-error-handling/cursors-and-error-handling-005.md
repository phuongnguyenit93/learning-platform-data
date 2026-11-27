# CONTINUE/EXIT Handlers and Applicable Block Scope

MySQL stored programs can encounter many kinds of conditions during execution: a query finds no rows, a data conversion raises a warning, a constraint is violated, or an SQL error occurs. Handlers allow a routine to react to those conditions directly within the execution flow.

The two primary handler types are:

- **CONTINUE**: executes the handler body and then resumes execution at the statement immediately following the statement that raised the condition.
- **EXIT**: executes the handler body and then exits the `BEGIN ... END` block in which the handler was declared.

A common misconception is that EXIT always exits the entire procedure. If a handler is declared inside a nested inner block, EXIT only terminates that inner block; statements following the block in the outer routine can still execute.

This article explains how to declare handlers, distinguish CONTINUE and EXIT, understand handler scope in nested blocks, classify SQL conditions, understand precedence when multiple handlers match, and design predictable handlers.

## 1. What Is a Handler?

A handler is a declaration in a stored program to handle a specific condition. The condition can be a SQLSTATE, a MySQL error code, or a named condition group.

General syntax:

~~~sql
DECLARE { CONTINUE | EXIT } HANDLER
FOR condition_value [, condition_value] ...
statement;
~~~

MySQL supports two handler types: CONTINUE and EXIT. The UNDO keyword appears in some SQL descriptions but is not supported by MySQL.

Where:

- CONTINUE or EXIT determines the execution flow after the handler runs.
- FOR specifies the condition(s) the handler accepts.
- statement is a single statement or a `BEGIN ... END` block forming the handler body.

Simple handler example:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_not_found = TRUE;
~~~

When the NOT FOUND condition occurs within the handler's scope, MySQL sets `v_not_found` to TRUE and then continues after the statement that raised the condition.

Handlers are typically used to:

- Mark end-of-data when cursor FETCH has no more rows.
- Detect when `SELECT ... INTO` finds no rows.
- Record or propagate SQL errors.
- Perform state cleanup before exiting a block.
- Turn a technical error into a result or message matching the routine's contract.

A handler is not a replacement for constraints, transactions, or input validation. It dictates how the routine reacts after a condition has occurred.

## 2. SQL Conditions a Handler Can Catch

MySQL allows declaring handlers for several condition forms:

| Condition Form | Meaning |
|---|---|
| SQLSTATE value | 5-character SQL state code, e.g. '02000' or '45000' |
| MySQL error code | Specific numeric error code, e.g. 1062 |
| SQLWARNING | SQLSTATE class 01 |
| NOT FOUND | SQLSTATE class 02 |
| SQLEXCEPTION | SQLSTATE values other than classes 00, 01, and 02 |
| Condition name | Condition name declared via DECLARE ... CONDITION |

SQLEXCEPTION does not catch SQLWARNING or NOT FOUND because those two groups have their own SQLSTATE classes. If a routine needs to handle all three groups, declare the corresponding handlers and specify clearly whether each group should continue or exit the block.

### 2.1. SQLWARNING

SQLWARNING represents warning conditions, i.e. SQLSTATE values in class 01.

~~~sql
BEGIN
    DECLARE v_warning_seen BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLWARNING
        SET v_warning_seen = TRUE;

    -- Statements that may raise a warning.
END
~~~

This handler can catch many different warnings. If you need a specific reaction to one particular warning, use the corresponding SQLSTATE or condition name instead of grouping everything under SQLWARNING.

### 2.2. NOT FOUND

NOT FOUND represents SQLSTATE class 02. Common cases:

- `SELECT ... INTO` finds no rows.
- Cursor FETCH reaches the end of the result set.

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- Statements that may raise NOT FOUND.
END
~~~

With cursors, this is the standard pattern to set a loop termination flag. With `SELECT ... INTO`, the flag helps the routine distinguish "no row found" from "a row exists with a NULL column value."

### 2.3. SQLEXCEPTION

SQLEXCEPTION represents SQLSTATE conditions not belonging to classes 00, 01, or 02. Common examples include constraint violations or SQL execution errors.

~~~sql
BEGIN
    DECLARE v_failed BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET v_failed = TRUE;
        RESIGNAL;
    END;

    -- Statements that may raise an SQL error.
END
~~~

RESIGNAL re-raises the current condition so the caller still receives the error. If a handler only sets a flag and swallows the error, the caller may assume the operation succeeded; only do that when the routine has an explicit error-handling contract.

### 2.4. Specific SQLSTATE

You can catch a specific SQLSTATE:

~~~sql
BEGIN
    DECLARE v_business_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_business_error = TRUE;

    -- Statements that may SIGNAL SQLSTATE '45000'.
END
~~~

`SQLSTATE '45000'` is commonly used with SIGNAL to raise an application-defined condition:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Invalid order status';
~~~

A handler catches this condition just like any other SQL condition. Use a specific SQLSTATE when you need to control one exact scenario; avoid catching too broadly if other errors should be propagated to the caller.

## 3. How Does a CONTINUE Handler Work?

A CONTINUE handler runs its handler body, and then execution continues at the statement immediately after the statement that raised the condition.

Example:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_continue_handler()
BEGIN
    DECLARE v_step INT DEFAULT 0;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_step = v_step + 1;

    SET v_step = 10;

    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Test condition';

    SET v_step = v_step + 100;

    SELECT v_step AS final_step;
END//

DELIMITER ;
~~~

Sequence:

1. `v_step` is assigned 10.
2. SIGNAL raises SQLSTATE '45000'.
3. The CONTINUE handler increments `v_step` by 1.
4. MySQL resumes after SIGNAL.
5. The next SET statement adds 100.
6. SELECT returns 111.

CONTINUE does not go back and re-run the failing statement. It continues after that statement.

### 3.1. When Should You Use CONTINUE?

CONTINUE is appropriate when the routine can handle the condition and safely continue its work:

- Setting a done flag when FETCH has no more rows.
- Marking that a record does not exist and taking an alternate branch.
- Recording a warning while continuing if the warning does not compromise correctness.
- Skipping a scenario identified as recoverable.

Do not mechanically use CONTINUE for every SQLEXCEPTION. If a statement fails yet subsequent statements keep running, the routine can produce partial state or inconsistent results.

### 3.2. CONTINUE Does Not Erase the Condition

A handler does not turn a failing statement into a successful one. It only dictates what happens next.

For example, if an INSERT violates a unique key and a CONTINUE handler catches error 1062, the row is not inserted. Subsequent statements still run, so the routine must explicitly decide whether to move on to the next record, update status, or return an error result.

## 4. How Does an EXIT Handler Work?

An EXIT handler runs its handler body and then terminates the `BEGIN ... END` block in which the handler is declared. Execution continues after that block, if an outer block exists.

Example:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_exit_handler()
main_block: BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT 'Start';

    DECLARE EXIT HANDLER FOR SQLSTATE '45000'
    BEGIN
        SET v_message = 'Handled error in main_block';
        SELECT v_message AS handler_result;
    END;

    SET v_message = 'Before SIGNAL';

    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Stop block';

    SET v_message = 'Does not reach here';
    SELECT v_message AS normal_result;
END main_block//

DELIMITER ;
~~~

When SIGNAL occurs, the EXIT handler runs. Then `main_block` ends; statements after SIGNAL in the same block are not executed.

Because the handler is declared in the outermost block of the procedure, exiting this block also terminates the procedure body. If the handler is inside a child block, the exit scope is smaller.

### 4.1. When Should You Use EXIT?

EXIT is appropriate when the condition makes the remainder of the block unsafe or meaningless:

- Processing cannot continue because input data is invalid.
- A mandatory statement failed.
- A sub-step needs to terminate early while still letting the outer block perform other work.
- Cleanup or error re-raising is required before leaving the block.

If a handler catches a severe error, consider RESIGNAL so the caller receives the original error. Do not swallow errors if the caller needs to know the operation failed.

## 5. Handler Scope in Nested Blocks

Every handler belongs to the `BEGIN ... END` block where it is declared. A handler can handle conditions raised within that block and its child blocks, following MySQL's handler lookup rules.

When a condition occurs, MySQL looks for a matching handler in the current block first. If the current block has no matching handler, the search continues outward through enclosing blocks.

This produces two important consequences:

- A handler in a child block can handle a condition locally without changing how the parent block handles other errors.
- An EXIT handler in a child block only exits the child block. Once the child block ends, the parent block continues at the statement following that block.

### 5.1. EXIT in a Child Block, Parent Block Continues

~~~sql
DELIMITER //

CREATE PROCEDURE demo_nested_exit()
outer_block: BEGIN
    DECLARE v_message VARCHAR(200) DEFAULT 'Start';

    inner_block: BEGIN
        DECLARE EXIT HANDLER FOR SQLSTATE '45000'
            SET v_message = 'Exited inner_block';

        SET v_message = 'Inside inner_block';

        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Error in child block';

        SET v_message = 'This statement does not run';
    END inner_block;

    SET v_message = CONCAT(v_message, '; outer_block continues');
    SELECT v_message AS final_message;
END outer_block//

DELIMITER ;
~~~

Sequence:

1. `outer_block` begins.
2. `inner_block` begins and declares its own EXIT handler.
3. SIGNAL raises SQLSTATE '45000'.
4. The handler in `inner_block` runs and updates `v_message`.
5. EXIT ends `inner_block`; the SET immediately after SIGNAL is skipped.
6. Execution returns to `outer_block` at the statement after `END inner_block`.
7. SELECT returns a message showing that the outer block continued.

This is why EXIT must not be interpreted as "exit the procedure" in every situation. The exit boundary is determined by the block containing the handler declaration.

### 5.2. CONTINUE in a Child Block

~~~sql
DELIMITER //

CREATE PROCEDURE demo_nested_continue()
outer_block: BEGIN
    DECLARE v_message VARCHAR(200) DEFAULT 'Start';

    inner_block: BEGIN
        DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
            SET v_message = 'Handled in inner_block';

        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Condition in child block';

        SET v_message = CONCAT(v_message, '; continued in inner_block');
    END inner_block;

    SET v_message = CONCAT(v_message, '; outer_block continues');
    SELECT v_message AS final_message;
END outer_block//

DELIMITER ;
~~~

Once the CONTINUE handler finishes, MySQL resumes at the SET statement immediately after SIGNAL inside `inner_block`. After the child block ends normally, the parent block continues.

### 5.3. Outer Block Handler Catching a Condition from a Child Block

If a child block has no matching handler, a handler in the parent block can catch the condition:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_outer_handler()
outer_block: BEGIN
    DECLARE v_handled BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_handled = TRUE;

    inner_block: BEGIN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Child block has no handler';
    END inner_block;

    IF v_handled THEN
        SELECT 'Outer handler handled it' AS result_message;
    END IF;
END outer_block//

DELIMITER ;
~~~

The handler is declared in `outer_block` and can handle conditions raised inside `inner_block`. Because the handler is CONTINUE, after handling the condition, execution resumes after the SIGNAL statement inside the child block; then the outer block runs the remainder of its code.

If the handler in `outer_block` were EXIT, the same unhandled condition from `inner_block` would invoke the outer handler and terminate `outer_block`. The exit boundary is always the block containing the selected handler declaration, not the block where the failing statement resides.

## 6. Placing Handlers in the Proper Declaration Position

DECLARE HANDLER must be inside a `BEGIN ... END` block and must appear in the declaration section at the top of the block, before executable statements.

Declaration order in a block:

1. Local variables and named conditions.
2. Cursors.
3. Handlers.
4. Executable statements.

Example:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE order_cursor CURSOR FOR
        SELECT order_id
        FROM sales_orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN order_cursor;
    -- Cursor processing statements go here.
    CLOSE order_cursor;
END
~~~

This example only illustrates declaration order. A complete FETCH loop needs to check `v_done` after every FETCH and close the cursor in both normal and error paths.

### 6.1. Do Not Declare Handlers Directly Inside IF or LOOP

IF, CASE, LOOP, WHILE, and REPEAT do not create their own handler declaration region. To limit a handler to a branch or loop, place a `BEGIN ... END` block inside:

Suppose the procedure already declared parameters `p_process_detail`, `p_order_id` and variables `v_detail_missing`, `v_detail_value`, `v_result` in the outer block.

~~~sql
IF p_process_detail THEN
    detail_block: BEGIN
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_detail_missing = TRUE;

        SELECT d.detail_value
          INTO v_detail_value
        FROM order_details AS d
        WHERE d.order_id = p_order_id;

        IF NOT v_detail_missing THEN
            SET v_result = v_detail_value;
        END IF;
    END detail_block;
END IF;
~~~

The handler belongs only to `detail_block`. After this block ends, it is no longer an active handler for subsequent statements in the parent block.

### 6.2. Why Use Small Blocks?

Small blocks help:

- Restrict where a handler can catch conditions.
- Prevent a cursor's NOT FOUND handler from accidentally catching unrelated `SELECT ... INTO` queries.
- Separate recoverable errors from errors that must propagate to outer routines.
- Make it obvious which portion of work an EXIT will terminate.
- Reduce the risk of a broad handler masking errors from other operations.

You do not need to create nested blocks for every statement. Create a block when you need distinct handling boundaries or want EXIT to leave only part of the work.

## 7. Precedence Order When Multiple Handlers Match

A single condition can match multiple handlers. For example, duplicate key error 1062 has SQLSTATE '23000', so it can match a handler for error code 1062, a handler for SQLSTATE '23000', and a general SQLEXCEPTION handler.

MySQL applies the following precedence order:

1. Specific MySQL error code has the highest precedence.
2. Specific SQLSTATE has the next highest precedence.
3. General condition groups such as SQLEXCEPTION, SQLWARNING, or NOT FOUND have lower precedence.

Example:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE v_integrity_error BOOLEAN DEFAULT FALSE;
    DECLARE v_other_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '23000'
        SET v_integrity_error = TRUE;

    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
        SET v_other_error = TRUE;

    -- Executable statements follow the declaration section.
END
~~~

If error 1062 occurs, the handler for the specific error code takes precedence over the SQLSTATE handler and the SQLEXCEPTION handler.

### 7.1. Avoid Multiple Handlers at the Same Precedence Level

If multiple handlers with the same precedence can handle the same condition in the same scope, selection can be indeterminate. Do not design routines that rely on declaration order to resolve such overlaps.

Recommended practices:

- Use the most specific condition that has business meaning.
- Avoid declaring multiple handlers for general groups that could match the same error.
- Use named conditions to express conditions clearly.
- Use a single general handler and branch with GET DIAGNOSTICS if multiple error codes need handling in the same block.

## 8. Naming Conditions with DECLARE ... CONDITION

Named conditions make handler statements easier to read than scattered numeric codes or SQLSTATE strings:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_order CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_order
        SET v_duplicate = TRUE;

    -- Executable statements.
END
~~~

A condition name can reference a MySQL error code or a SQLSTATE:

~~~sql
DECLARE invalid_order_state CONDITION
    FOR SQLSTATE '45000';
~~~

A condition name does not create a new error itself; it merely gives a name to an already defined condition. To raise an application-defined condition, use SIGNAL with an appropriate SQLSTATE.

The condition name must be declared in the block before being used in DECLARE HANDLER. If multiple blocks need the same condition, declare it separately in each block or place it in an outer block with appropriate scope.

## 9. NOT FOUND Handler with Cursors

A cursor reads rows one by one from a result set. When FETCH has no more rows, MySQL raises NOT FOUND. The standard pattern is a CONTINUE handler setting a done flag:

~~~sql
DELIMITER //

CREATE PROCEDURE count_orders_with_cursor()
BEGIN
    DECLARE v_count BIGINT DEFAULT 0;

    cursor_block: BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_order_id BIGINT UNSIGNED;

        DECLARE order_cursor CURSOR FOR
            SELECT order_id
            FROM sales_orders
            ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        OPEN order_cursor;

        read_loop: LOOP
            FETCH order_cursor INTO v_order_id;

            IF v_done THEN
                LEAVE read_loop;
            END IF;

            SET v_count = v_count + 1;
        END LOOP;

        CLOSE order_cursor;
    END cursor_block;

    SELECT v_count AS processed_orders;
END//

DELIMITER ;
~~~

The handler is declared inside `cursor_block`, so it exists only for the cursor-processing scope and its child blocks. When the final FETCH finds no row:

1. NOT FOUND triggers the handler.
2. The handler sets `v_done = TRUE`.
3. CONTINUE brings execution to the IF statement right after FETCH.
4. LEAVE exits `read_loop`.
5. CLOSE closes the cursor.
6. `cursor_block` ends and the handler goes out of scope.
7. The outer SELECT returns the number of processed rows.

### 9.1. Why Not Scope the NOT FOUND Handler Too Broadly?

NOT FOUND does not only occur when a cursor runs out of rows. A `SELECT ... INTO` that finds no rows also raises a class 02 condition.

If the same block contains:

- Cursor FETCH.
- A `SELECT ... INTO` that may find no rows.
- Another operation that can raise NOT FOUND.

then the same NOT FOUND handler can catch all of those situations. For instance, a `SELECT ... INTO` finding no rows can set `v_done = TRUE`; the cursor loop then mistakenly assumes the cursor has finished reading.

The solution is to restrict the cursor handler to its own block as in the example above. If `SELECT ... INTO` is needed, place it in a different block with its own handler and flag.

### 9.2. The Flag Must Be Checked Immediately After FETCH

Do not process `v_order_id` before checking `v_done`:

~~~sql
FETCH order_cursor INTO v_order_id;

IF v_done THEN
    LEAVE read_loop;
END IF;

SET v_count = v_count + 1;
~~~

When FETCH finds no row, target variables do not receive a new row. Checking the flag before using `v_order_id` prevents reprocessing the value from the previous FETCH.

## 10. CONTINUE Handler for a Recoverable Error

CONTINUE is useful when a specific error is expected and the routine has a clear handling branch.

Example table storing unique reference codes:

~~~sql
CREATE TABLE external_order_refs (
    ref_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_ref VARCHAR(100) NOT NULL,
    PRIMARY KEY (ref_id),
    UNIQUE KEY uq_external_ref (external_ref)
) ENGINE = InnoDB;
~~~

The following procedure specifically catches duplicate key errors:

~~~sql
DELIMITER //

CREATE PROCEDURE register_external_ref(
    IN p_external_ref VARCHAR(100),
    OUT p_inserted BOOLEAN
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    SET p_inserted = FALSE;

    INSERT INTO external_order_refs (external_ref)
    VALUES (p_external_ref);

    IF v_duplicate = FALSE THEN
        SET p_inserted = TRUE;
    END IF;
END//

DELIMITER ;
~~~

If `external_ref` already exists, INSERT raises error 1062, the handler sets the flag, and CONTINUE allows the routine to reach the IF check. If no error occurred, `p_inserted` becomes TRUE.

This pattern is only appropriate when a duplicate genuinely means "already registered." If the caller needs to distinguish duplicates from other errors, do not declare a general SQLEXCEPTION handler that swallows all errors.

## 11. EXIT Handler for Errors That Must Propagate to the Caller

For errors that cannot be recovered inside the routine, an EXIT handler can capture diagnostic details and then RESIGNAL:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_external_ref(
    IN p_external_ref VARCHAR(100)
)
BEGIN
    DECLARE v_sqlstate CHAR(5) DEFAULT NULL;
    DECLARE v_errno INT DEFAULT NULL;
    DECLARE v_message VARCHAR(512) DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        RESIGNAL;
    END;

    INSERT INTO external_order_refs (external_ref)
    VALUES (p_external_ref);
END//

DELIMITER ;
~~~

GET DIAGNOSTICS reads information about the current condition:

- RETURNED_SQLSTATE: SQLSTATE of the condition.
- MYSQL_ERRNO: MySQL error number.
- MESSAGE_TEXT: error message.

The example stores the values in local variables to illustrate retrieving diagnostics. Because the handler calls RESIGNAL, the original error is still propagated to the caller. If durable logging is needed, you must design an appropriate log destination and transaction boundary; do not assume a log write inside the same transaction will survive a rollback.

### 11.1. RESIGNAL and SIGNAL

These two statements serve different purposes:

| Statement | Purpose |
|---|---|
| SIGNAL | Proactively raises a new condition |
| RESIGNAL | Re-raises the condition currently being handled, optionally keeping or modifying some attributes |

Example raising a business error:

~~~sql
IF p_external_ref IS NULL OR p_external_ref = '' THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'external_ref cannot be empty';
END IF;
~~~

Example re-raising the current error:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    -- Statements that may raise an error.
END
~~~

If you replace RESIGNAL with `SIGNAL SQLSTATE '45000'`, the routine creates a brand-new condition and can lose the original error code, SQLSTATE, or diagnostic details. Only replace the error when the routine's contract intentionally requires error mapping.

## 12. Handlers Do Not Automatically Roll Back Transactions

CONTINUE and EXIT only control execution flow inside the stored program. They do not automatically COMMIT or ROLLBACK a transaction.

Example:

~~~sql
BEGIN
    DECLARE v_failed BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET v_failed = TRUE;
        RESIGNAL;
    END;

    -- Statements that may raise an error.
END
~~~

The handler snippet above does not roll back modified data. Rollback depends on the transaction and the decision of the caller or routine logic designed to own the transaction.

If the routine intentionally opens a transaction and owns that boundary, the handler can roll back before re-raising the error:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    -- Statements belonging to the transaction owned by the routine.
    COMMIT;
END
~~~

Only use this pattern when the routine truly owns the transaction. A stored procedure may be invoked inside a transaction opened by the application; calling ROLLBACK inside the procedure in that case would roll back the caller's work. Do not add ROLLBACK to a general handler without clearly determining who owns the transaction.

If an example opens a transaction with START TRANSACTION, only invoke the procedure under a contract where the caller has no open unfinished transaction; executing START TRANSACTION while another transaction is open can implicitly commit the previous transaction.

With savepoints, you can roll back to a marked point if the design allows and the savepoint still exists. Handlers cannot make DDL operations or non-transactional engines rollback-capable.

## 13. Distinguishing EXIT Handler from LEAVE

Both EXIT handler and LEAVE can cause execution to exit a block, but they are triggered differently:

| Mechanism | When it runs | Effect |
|---|---|---|
| EXIT handler | When a matching condition occurs | Runs the handler then exits the block where the handler is declared |
| CONTINUE handler | When a matching condition occurs | Runs the handler then resumes after the statement that raised the condition |
| LEAVE label | When the LEAVE statement executes | Explicitly exits the block or loop with the corresponding label |

Example of LEAVE explicitly ending a loop:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;

    read_loop: LOOP
        IF v_count >= 100 THEN
            LEAVE read_loop;
        END IF;

        SET v_count = v_count + 1;
    END LOOP;
END
~~~

Example of an EXIT handler reacting to an error:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    -- Statements that may raise an error.
END
~~~

LEAVE does not catch errors and does not run a handler body. An EXIT handler is not a LEAVE statement; it is triggered by MySQL when a condition matches.

## 14. NOT FOUND Condition from SELECT ... INTO

NOT FOUND is often mentioned alongside cursors, but `SELECT ... INTO` returning no rows also raises this condition.

Example placing a handler in a small block to handle just one query:

Suppose this snippet is inside a procedure with parameters `IN p_order_id` and `OUT p_total`.

~~~sql
BEGIN
    DECLARE v_order_total DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_order_found BOOLEAN DEFAULT TRUE;

    lookup_block: BEGIN
        DECLARE v_not_found BOOLEAN DEFAULT FALSE;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_not_found = TRUE;

        SELECT so.total
          INTO v_order_total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id;

        IF v_not_found THEN
            SET v_order_found = FALSE;
        END IF;
    END lookup_block;

    IF v_order_found THEN
        SET p_total = v_order_total;
    ELSE
        SET p_total = NULL;
    END IF;
END
~~~

The handler is active only within `lookup_block`. Once the block finishes, subsequent statements in the outer block are not caught by this handler.

If the table has a matching row whose `total` column contains NULL, NOT FOUND does not occur; `v_order_found` stays TRUE and `v_order_total` is NULL. Therefore, distinguish "no row exists" from "row exists with a NULL column value."

## 15. Condition Names and Declaration Scope

A condition name is scoped to the block where it is declared and its child blocks according to stored program scoping rules.

Example declaring a condition in an outer block for a handler in the same block:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_reference CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_reference
        SET v_duplicate = TRUE;

    -- INSERT statements that may raise a duplicate key error.
END
~~~

If a child block needs to use the same condition name, you can declare the condition in the outer block. If the condition only has meaning within one sub-operation, declare it inside the child block to limit scope and avoid unnecessary dependencies.

A condition name is only an alias. Handlers still follow the precedence level of the underlying condition referenced by that name, such as a specific error code or SQLSTATE.

## 16. Common Handler Design Mistakes

### 16.1. Catching SQLEXCEPTION and Continuing as If No Error Occurred

~~~sql
BEGIN
    DECLARE v_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
        SET v_error = TRUE;

    -- Executable statements.
END
~~~

This handler catches many different errors and then resumes at the statement after the error. If the routine does not check `v_error` before subsequent steps, it can produce partial results or write inconsistent data.

Only use CONTINUE for errors from which the routine can intentionally recover. For severe errors, typically use EXIT and RESIGNAL to stop the block and notify the caller.

### 16.2. Using One NOT FOUND Handler for Both a Cursor and SELECT INTO

If a cursor and a `SELECT ... INTO` reside in the same block, the cursor's NOT FOUND handler can also catch the case where `SELECT ... INTO` finds no row. The done flag can flip early and the cursor loop can terminate mistakenly.

Place the cursor in its own block, use a separate flag for `SELECT ... INTO`, and avoid sharing one handler across operations with different semantics.

### 16.3. Declaring EXIT on Too Broad a Block

An EXIT handler declared on an outer block can terminate the entire routine body when an error happens in a small sub-step. If you only want to skip a secondary step and continue the main step, place the EXIT handler inside a dedicated child block.

### 16.4. Using Multiple Overlapping General Handlers

Do not declare multiple handlers at the same precedence level that can match the same condition expecting MySQL to choose by declaration order. Selection can be indeterminate. Narrow the conditions or consolidate handling into a single handler.

### 16.5. Swallowing Errors with an Empty Handler

~~~sql
BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN
    END;

    -- Statements that may raise an error.
END
~~~

An empty handler lets the routine keep running without notifying the caller of the error. Unless this is an explicitly designed error-handling contract, it hides the root cause of failures and makes operational investigation difficult.

### 16.6. Logging and Losing the Original Error

If a handler logs an error without calling RESIGNAL, the caller may not know the statement failed. If the handler raises a new error while logging, the original diagnostic information can also be obscured.

Keep handlers short, read diagnostics before performing other operations, and call RESIGNAL when the caller needs the original error. Durable logging requires an appropriate separate transaction design.

### 16.7. Assuming EXIT Always Rolls Back

EXIT only leaves a block. Data already written in the transaction may still be pending and requires a COMMIT/ROLLBACK decision from whoever owns the transaction. Never infer rollback from the EXIT keyword alone.

### 16.8. Declaring a Handler After Executable Statements

DECLARE HANDLER must appear in the declaration section at the top of the block. Placing a handler after OPEN, SELECT, or SET makes the routine invalid.

## 17. Procedure for Choosing a Handler

When a stored program needs error handling, follow this sequence:

1. Identify the actual condition: SQLSTATE, error code, SQLWARNING, NOT FOUND, or SQLEXCEPTION.
2. Decide whether the routine can recover and continue or must exit the block.
3. Choose CONTINUE if execution should resume after the statement raising the condition.
4. Choose EXIT if the remainder of the block should not continue.
5. Place the handler in the smallest block that can own that handling logic.
6. If multiple handlers may match, prefer specific conditions and avoid overlapping handlers at the same precedence.
7. If the caller must be notified of the error, use RESIGNAL or map the error intentionally.
8. Clearly determine whether the caller or the routine owns the transaction; handlers do not decide rollback automatically.
9. Test cases where the condition does not occur, occurs once, and occurs in a child block.
10. For cursors, use a NOT FOUND handler in the cursor block and check the flag right after FETCH.

## 18. Pre-Completion Routine Checklist

- [ ] Every DECLARE HANDLER is in the declaration section at the start of a `BEGIN ... END` block.
- [ ] Variables and conditions are declared before cursors; cursors before handlers.
- [ ] CONTINUE and EXIT are chosen according to the desired execution flow.
- [ ] Which block EXIT terminates is verified by the handler's declaration placement.
- [ ] Child block handlers do not disrupt the parent block unexpectedly.
- [ ] Outer block handlers only catch conditions left unhandled in inner blocks.
- [ ] SQLWARNING, NOT FOUND, and SQLEXCEPTION are properly distinguished.
- [ ] Cursor's NOT FOUND does not accidentally catch unrelated `SELECT ... INTO` statements.
- [ ] The termination flag is checked immediately after FETCH.
- [ ] Specific conditions take precedence over general condition groups.
- [ ] No overlapping handlers of equal precedence rely on MySQL's tie-breaking choice.
- [ ] Handlers do not accidentally swallow errors the caller needs to know.
- [ ] RESIGNAL is used when the original error must be re-raised.
- [ ] GET DIAGNOSTICS is called before error information is overwritten by another operation.
- [ ] EXIT is not assumed to roll back transactions automatically.
- [ ] Normal flow, child-block error flow, and outer-block error flow have been tested.

## Conclusion

CONTINUE and EXIT differ in where execution resumes. CONTINUE runs the handler and continues right after the statement that raised the condition; EXIT runs the handler and exits the block where the handler is declared. Block scope therefore dictates how widely an error affects the rest of the routine.

Place handlers close to the operations they handle, use dedicated NOT FOUND scope for cursor regions, choose sufficiently specific conditions, and avoid swallowing errors unintentionally. When an error must return to the caller, read diagnostics if needed and then RESIGNAL. Finally, always identify transaction ownership because handlers only control stored program flow—they do not automatically roll back data.
