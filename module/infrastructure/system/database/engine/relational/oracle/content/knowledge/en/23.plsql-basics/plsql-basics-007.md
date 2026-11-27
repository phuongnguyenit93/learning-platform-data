# LOOP, WHILE, FOR, EXIT, and CONTINUE in PL/SQL

PL/SQL provides loop constructs to execute a group of statements multiple times. The three basic forms are **LOOP**, **WHILE LOOP**, and **FOR LOOP**. When you need to terminate early or skip the rest of an iteration, use **EXIT** and **CONTINUE**.

Loops are useful when a procedure must process individual elements, read a cursor, retry a step a bounded number of times, or perform a sequence of conditional operations. However, for relational data, many tasks can be solved more efficiently with a single set-based SQL statement. Choose a loop when the logic is genuinely sequential or depends on the outcome of each iteration.

This lesson covers syntax, execution flow, loop index scope, nested loops, cursor FOR LOOPs, exception handling, and runnable examples for Oracle SQL Developer or SQL*Plus.

## 1. Loops in PL/SQL

A loop is a control structure that allows running a group of statements repeatedly. A loop typically has:

- Body: the statements executed during each iteration.
- Continuation condition or termination condition.
- Optionally, a step that updates a control variable.

PL/SQL has three main loop forms:

| Form | How Iteration Count Is Controlled | Commonly Used When |
|---|---|---|
| Basic LOOP | Explicitly write EXIT or EXIT WHEN | Flexible stopping points are needed |
| WHILE LOOP | Checks condition before each iteration | Continuing while a condition remains true |
| Numeric FOR LOOP | Iterates over a defined integer range | Lower and upper bounds are known |

In addition, the **cursor FOR LOOP** is a FOR LOOP form that iterates over query results. Oracle automatically manages opening the cursor, fetching each row, and closing the cursor.

### 1.1. General Flowchart

~~~text
               Start loop
                   |
                   v
        Check condition at start?
              /          \
            Yes           No
             |             |
             v             v
      Condition TRUE?   Run LOOP body
        /       \
      Yes        No
       |          |
       v          v
   Run body      End
       |
       v
  EXIT or CONTINUE?
       |
       v
 Next iteration or exit
~~~

This diagram illustrates only the general idea. Where the condition is checked differs among LOOP, WHILE, and FOR; understand each form clearly to avoid running an extra iteration or creating an infinite loop.

## 2. Basic LOOP

A basic LOOP begins running the loop body immediately. It has no stopping condition at the top of the construct; the developer must use EXIT or EXIT WHEN to terminate it.

### 2.1. Syntax

~~~sql
LOOP
    statements;
END LOOP;
~~~

Without an EXIT statement, the loop continues forever until interrupted or until an error causes execution to leave the block.

Example:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Start');
    LOOP
        DBMS_OUTPUT.PUT_LINE('This statement repeats');
        EXIT;
    END LOOP;
    DBMS_OUTPUT.PUT_LINE('End');
END;
/
~~~

An unconditional EXIT terminates the current loop immediately at the point where it executes.

### 2.2. Using EXIT WHEN

EXIT WHEN terminates the loop when the condition evaluates to TRUE:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE('Counter = ' || v_counter);
        v_counter := v_counter + 1;

        EXIT WHEN v_counter > 5;
    END LOOP;
END;
/
~~~

The output prints numbers from 1 to 5. After printing 5, the variable is incremented to 6; the condition V_COUNTER > 5 becomes TRUE, so the loop ends.

Note the placement of EXIT WHEN:

~~~sql
LOOP
    EXIT WHEN v_counter > 5;
    DBMS_OUTPUT.PUT_LINE(v_counter);
    v_counter := v_counter + 1;
END LOOP;
~~~

In the second example, the condition is checked before printing. If V_COUNTER is already greater than 5 initially, the loop body does not execute further. With a basic LOOP, the body always starts at least once; however, an EXIT placed at the very top of the body can end that first iteration immediately.

### 2.3. Using Unconditional EXIT

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);

        IF v_counter = 3 THEN
            EXIT;
        END IF;

        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

EXIT is often placed inside an IF when the stopping condition requires multiple branches or additional processing before exiting.

### 2.4. When to Use Basic LOOP?

LOOP is suitable when:

- The stopping point is only known after executing some operations.
- You need to loop until a cursor runs out of rows or there is no more work.
- You need to check multiple stopping conditions at different points.
- You need to retry an operation with a maximum attempt limit.

When the condition is clearly known before each iteration, a WHILE LOOP usually expresses the intent more readably.

## 3. WHILE LOOP

A WHILE LOOP checks the condition before each iteration. If the condition is TRUE, the loop body runs. If the condition is FALSE or NULL, the loop ends without executing the body for that iteration.

### 3.1. Syntax

~~~sql
WHILE condition LOOP
    statements;
END LOOP;
~~~

Example:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE('Counter = ' || v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

The output is 1, 2, 3, 4, 5. After printing 5, the variable increments to 6. Oracle re-evaluates 6 <= 5, gets FALSE, and exits.

### 3.2. Condition Checked Before Loop Body

~~~sql
DECLARE
    v_counter PLS_INTEGER := 10;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE('This line is not printed');
        v_counter := v_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop finished');
END;
/
~~~

Because the condition is false from the start, the loop body never runs. This is an important difference from a basic LOOP.

### 3.3. Updating the Control Variable

The WHILE condition must be able to transition from TRUE to FALSE. If the loop body does not modify variables participating in the condition and nothing else changes the condition's value, the loop can run infinitely.

Faulty example:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        -- Missing statement to increment v_counter.
    END LOOP;
END;
/
~~~

The condition V_COUNTER <= 5 remains TRUE forever because the variable never changes. This example is only for recognizing the bug; do not run it in a shared session or production environment.

### 3.4. Condition Evaluating to NULL

A PL/SQL loop condition is a BOOLEAN expression. With WHILE, the loop body runs only when the condition is TRUE. If the condition is FALSE or NULL, the body does not execute.

Example:

~~~sql
DECLARE
    v_limit PLS_INTEGER := NULL;
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= v_limit LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('No iteration');
END;
/
~~~

Comparing against NULL yields UNKNOWN/NULL, so the loop body does not run. When a control value can be NULL, check it or assign a default value before entering the loop.

## 4. Numeric FOR LOOP

A numeric FOR LOOP iterates over a sequence of integers from a lower bound to an upper bound. Oracle automatically creates the loop index variable and increments or decrements it in the chosen direction.

### 4.1. Syntax

~~~sql
FOR loop_index IN lower_bound .. upper_bound LOOP
    statements;
END LOOP;
~~~

Example:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        DBMS_OUTPUT.PUT_LINE('i = ' || i);
    END LOOP;
END;
/
~~~

The output is 1, 2, 3, 4, 5. You do not need to declare or manually increment the variable I.

### 4.2. Implicitly Declared Loop Index

In a FOR LOOP:

- Oracle implicitly declares the loop index scoped to the loop.
- The loop index can only be used inside the loop body.
- You cannot assign a value directly to the loop index.
- After END LOOP, the loop index is no longer in scope.

Invalid example:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        i := i + 1; -- Not allowed to assign to the loop index.
    END LOOP;
END;
/
~~~

FOR LOOP manages the index automatically; do not modify it inside the loop body.

### 4.3. Lower Bound and Upper Bound

The lower bound and upper bound expressions are evaluated once when the loop starts. If you need limits that change while the loop runs, use WHILE or LOOP with explicit control variables.

Example:

~~~sql
DECLARE
    v_start PLS_INTEGER := 2;
    v_end   PLS_INTEGER := 4;
BEGIN
    FOR i IN v_start .. v_end LOOP
        DBMS_OUTPUT.PUT_LINE(i);
        v_end := 10;
    END LOOP;
END;
/
~~~

The loop still uses the bounds evaluated at startup, so assigning V_END inside does not extend the loop to 10.

### 4.4. Empty Iteration Ranges

In a standard FOR LOOP, if the lower bound is greater than the upper bound, the loop body does not run:

~~~sql
BEGIN
    FOR i IN 5 .. 1 LOOP
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Finished');
END;
/
~~~

Only the line Finished is printed. To count downward, use REVERSE.

## 5. FOR REVERSE: Iterating in Descending Order

The REVERSE keyword causes the loop index to go from the upper bound down to the lower bound:

~~~sql
BEGIN
    FOR i IN REVERSE 1 .. 5 LOOP
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

Output:

~~~text
5
4
3
2
1
~~~

Note: with REVERSE, the bound order in the declaration is still lower_bound .. upper_bound. Oracle starts at the upper bound and counts down to the lower bound. Do not swap the bounds to 5 .. 1:

~~~sql
-- No iterations because lower bound 5 is greater than upper bound 1.
FOR i IN REVERSE 5 .. 1 LOOP
    NULL;
END LOOP;
~~~

### 5.1. Applications of FOR REVERSE

FOR REVERSE is suitable when:

- Traversing indices from the end to the beginning.
- Processing steps in reverse order.
- Removing elements or tasks in descending order.

Example:

~~~sql
BEGIN
    FOR step_no IN REVERSE 1 .. 4 LOOP
        DBMS_OUTPUT.PUT_LINE('Undo step ' || step_no);
    END LOOP;
END;
/
~~~

The output prints in the order 4, 3, 2, 1.

## 6. EXIT: Exiting a Loop

EXIT terminates the current loop. There are two common forms:

~~~sql
EXIT;
~~~

~~~sql
EXIT WHEN condition;
~~~

### 6.1. EXIT in LOOP

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        EXIT WHEN v_counter > 3;
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

Output: 1, 2, 3.

### 6.2. EXIT in WHILE or FOR

EXIT is not restricted to basic LOOP; it can be used in WHILE and FOR to stop early:

~~~sql
BEGIN
    FOR i IN 1 .. 10 LOOP
        IF i = 4 THEN
            EXIT;
        END IF;

        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

Output prints 1, 2, 3. When I equals 4, EXIT terminates the FOR loop immediately.

### 6.3. EXIT Only Exits the Nearest Loop

In nested loops, an unlabeled EXIT terminates only the innermost loop containing the EXIT statement:

~~~sql
BEGIN
    FOR i IN 1 .. 3 LOOP
        DBMS_OUTPUT.PUT_LINE('Outer ' || i);

        FOR j IN 1 .. 3 LOOP
            IF j = 2 THEN
                EXIT;
            END IF;

            DBMS_OUTPUT.PUT_LINE('  Inner ' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Each outer iteration prints only Inner 1 and exits the inner loop. The outer loop continues with the next value of I.

## 7. EXIT with Labels to Exit an Outer Loop

PL/SQL allows labeling a loop using << and >> delimiters. EXIT can specify the label of the loop to terminate.

### 7.1. Syntax

~~~sql
<<outer_loop>>
LOOP
    ...
    <<inner_loop>>
    LOOP
        ...
        EXIT outer_loop;
    END LOOP inner_loop;
END LOOP outer_loop;
~~~

### 7.2. Two-Level Exit Example

~~~sql
BEGIN
    <<outer_loop>>
    FOR i IN 1 .. 3 LOOP
        FOR j IN 1 .. 3 LOOP
            DBMS_OUTPUT.PUT_LINE('i=' || i || ', j=' || j);

            IF i = 2 AND j = 2 THEN
                EXIT outer_loop;
            END IF;
        END LOOP;
    END LOOP outer_loop;

    DBMS_OUTPUT.PUT_LINE('Exited outer loop');
END;
/
~~~

When I = 2 and J = 2, EXIT OUTER_LOOP terminates the outer FOR loop. The line Exited outer loop runs afterward.

### 7.3. When to Use Labels?

Labels are useful when:

- There are multiple nested loops.
- The stopping condition lies inside a deep loop, but the outer loop must terminate.
- You want to make the target loop explicit in multi-level code.

Do not overuse labels if a simpler structure can express the logic clearly using conditions and an EXIT on the nearest loop.

## 8. CONTINUE: Skipping the Remainder of an Iteration

CONTINUE does not terminate the loop. It skips the remaining statements of the current iteration and moves to the next iteration of the loop.

CONTINUE and CONTINUE WHEN are supported in PL/SQL starting from Oracle Database 11g. If you need to run on an older release, check compatibility and rewrite the equivalent logic with IF.

### 8.1. Syntax

~~~sql
CONTINUE;
~~~

~~~sql
CONTINUE WHEN condition;
~~~

### 8.2. Example Skipping Even Numbers

~~~sql
BEGIN
    FOR i IN 1 .. 10 LOOP
        CONTINUE WHEN MOD(i, 2) = 0;
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

The output is 1, 3, 5, 7, 9. When I is even, Oracle skips DBMS_OUTPUT.PUT_LINE for that iteration and moves to the next iteration.

### 8.3. CONTINUE Inside IF

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        IF i = 3 THEN
            CONTINUE;
        END IF;

        DBMS_OUTPUT.PUT_LINE('Process ' || i);
    END LOOP;
END;
/
~~~

The iteration I = 3 does not print Process 3. All other iterations run normally.

### 8.4. CONTINUE Does Not Auto-Increment WHILE Control Variables

With a FOR LOOP, Oracle automatically advances the loop index to the next value after CONTINUE. With LOOP or WHILE, the developer updates the control variable manually.

Dangerous example:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        CONTINUE WHEN v_counter = 3;
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

When V_COUNTER reaches 3, CONTINUE skips the increment statement. V_COUNTER stays 3 and the WHILE condition remains TRUE forever. This is an infinite loop.

Fix by updating the variable before CONTINUE:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        IF v_counter = 3 THEN
            v_counter := v_counter + 1;
            CONTINUE;
        END IF;

        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

With WHILE, inspect every path through the loop body to ensure the control variable progresses.

## 9. CONTINUE with Labels in Nested Loops

Like EXIT, CONTINUE can take a label to affect an outer loop.

### 9.1. Syntax

~~~sql
<<outer_loop>>
FOR i IN 1 .. 3 LOOP
    FOR j IN 1 .. 3 LOOP
        CONTINUE outer_loop WHEN j = 2;
        ...
    END LOOP;
END LOOP outer_loop;
~~~

When the condition is TRUE, CONTINUE OUTER_LOOP skips the remainder of the current outer iteration and moves to the next iteration of OUTER_LOOP. The inner loop is cut short for that iteration.

### 9.2. Example

~~~sql
BEGIN
    <<outer_loop>>
    FOR i IN 1 .. 3 LOOP
        DBMS_OUTPUT.PUT_LINE('Outer start ' || i);

        FOR j IN 1 .. 3 LOOP
            IF j = 2 THEN
                CONTINUE outer_loop;
            END IF;

            DBMS_OUTPUT.PUT_LINE('  Inner ' || j);
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('Outer end ' || i);
    END LOOP outer_loop;
END;
/
~~~

For each value of I, when J equals 2, CONTINUE OUTER_LOOP jumps directly to the next I. Thus:

- Inner 1 is printed.
- Inner 2 and Inner 3 are not printed.
- Outer end is also skipped because it sits after the inner loop within the same outer iteration.

### 9.3. Distinguishing Labeled EXIT and CONTINUE

| Statement | Effect |
|---|---|
| EXIT | Terminates the current loop |
| EXIT outer_loop | Terminates the loop labeled OUTER_LOOP |
| CONTINUE | Skips the remainder of the current iteration in the current loop |
| CONTINUE outer_loop | Skips the remainder of the outer iteration and advances to the next outer iteration |

## 10. Comparing LOOP, WHILE, and FOR

| Characteristic | LOOP | WHILE LOOP | FOR LOOP |
|---|---|---|---|
| Checks condition before body? | No automatic leading condition | Yes | Numeric range controls iterations |
| Can execute 0 times? | Body starts at least once, unless exited immediately | Yes | Yes |
| Auto-increments loop index? | No | No | Yes |
| Requires EXIT for normal termination? | Usually yes | Not required | Not required |
| Best suited for | Flexible stopping points | Clear continuation condition | Known numeric range |

Choose the structure according to intent:

- Use LOOP when the iteration count is unknown and stopping conditions are inside.
- Use WHILE when you want to check a condition before each iteration.
- Use FOR when you have clear numeric bounds or need to iterate over a cursor.

## 11. Cursor FOR LOOP

A cursor FOR LOOP iterates through each row of a query. Oracle automatically:

1. Opens the cursor.
2. Fetches one row into the loop record.
3. Executes the loop body.
4. Repeats until no rows remain.
5. Closes the cursor, whether exiting normally or via an exception leaving the loop.

### 11.1. Syntax Using an Inline Query

~~~sql
FOR rec IN (
    SELECT employee_id, employee_name
    FROM employees
    ORDER BY employee_id
) LOOP
    statements;
END LOOP;
~~~

REC is an implicitly declared record for the loop with fields corresponding to the columns in the SELECT list.

### 11.2. Example

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM lab_employee
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

The example assumes table LAB_EMPLOYEE exists with the queried columns. Substitute your actual schema's table and column names.

### 11.3. Cursor FOR LOOP with a Declared Cursor

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, employee_name
        FROM lab_employee
        ORDER BY employee_id;
BEGIN
    FOR rec IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ': ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

Cursor FOR LOOPs reduce boilerplate manual cursor management. You do not need OPEN, FETCH, or CLOSE for a cursor used directly in a FOR LOOP.

### 11.4. EXIT and CONTINUE in a Cursor FOR LOOP

You can use EXIT and CONTINUE just as in other loops:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM lab_employee
        ORDER BY employee_id
    ) LOOP
        CONTINUE WHEN rec.employee_id < 100;

        DBMS_OUTPUT.PUT_LINE(rec.employee_name);

        EXIT WHEN rec.employee_id >= 200;
    END LOOP;
END;
/
~~~

When employee_id is less than 100, that iteration is skipped. When an ID of 200 or higher is encountered after printing the name, the loop terminates. The query includes ORDER BY so processing order is deterministic by employee_id.

### 11.5. Cursor FOR LOOP and Performance

Cursor FOR LOOPs are convenient, but they still process row by row in PL/SQL. With millions of rows, switching data back and forth between the SQL engine and PL/SQL engine row by row can incur overhead.

If the goal is simply bulk updating or deleting under the same condition, consider a single set-based UPDATE/DELETE statement. If each row needs custom PL/SQL logic, consider BULK COLLECT and FORALL to reduce context switches, depending on requirements and error-handling needs.

## 12. Nested Loops

A nested loop is a loop placed inside the body of another loop. They are commonly used for matrices, combinations, or subgroups.

Example:

~~~sql
BEGIN
    FOR i IN 1 .. 3 LOOP
        FOR j IN 1 .. 2 LOOP
            DBMS_OUTPUT.PUT_LINE(
                'i=' || i || ', j=' || j
            );
        END LOOP;
    END LOOP;
END;
/
~~~

All iterations of the inner loop execute for each iteration of the outer loop. In this example, there are 3 × 2 = 6 lines printed.

### 12.1. EXIT in Nested Loops

An unlabeled EXIT exits only the nearest loop:

~~~sql
BEGIN
    FOR i IN 1 .. 2 LOOP
        FOR j IN 1 .. 4 LOOP
            EXIT WHEN j = 3;
            DBMS_OUTPUT.PUT_LINE(i || ',' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Each iteration of I prints only J = 1 and 2. When J = 3, the inner loop ends; the outer loop proceeds to the next I.

### 12.2. CONTINUE in Nested Loops

~~~sql
BEGIN
    FOR i IN 1 .. 2 LOOP
        FOR j IN 1 .. 4 LOOP
            CONTINUE WHEN j = 3;
            DBMS_OUTPUT.PUT_LINE(i || ',' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Only J = 3 is skipped in each inner loop. Iterations with J = 4 still execute.

## 13. Using Loops to Process DML

Some workflows need to execute DML step by step. Illustrative example creating a numeric processing log table:

~~~sql
CREATE TABLE lab_loop_result (
    value_no NUMBER PRIMARY KEY,
    square_value NUMBER NOT NULL,
    created_at DATE NOT NULL
);
~~~

Using a FOR LOOP to insert values:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        INSERT INTO lab_loop_result (
            value_no,
            square_value,
            created_at
        )
        VALUES (
            i,
            i * i,
            SYSDATE
        );
    END LOOP;

    COMMIT;
END;
/
~~~

Verification:

~~~sql
SELECT value_no, square_value, created_at
FROM lab_loop_result
ORDER BY value_no;
~~~

The square_value results are 1, 4, 9, 16, and 25.

For this simple example, a single INSERT ... SELECT can be more efficient:

~~~sql
INSERT INTO lab_loop_result (
    value_no,
    square_value,
    created_at
)
SELECT
    LEVEL,
    LEVEL * LEVEL,
    SYSDATE
FROM dual
CONNECT BY LEVEL <= 5;

COMMIT;
~~~

This comparison shows you should not use a loop just because you can. Set-based SQL is usually the better choice when all rows undergo the same transformation.

## 14. Using WHILE for Bounded Retries

A loop can be used to retry an operation up to N times. The following example only simulates a retry counter without making network connections or external calls:

~~~sql
DECLARE
    v_attempt PLS_INTEGER := 0;
    v_max_attempts CONSTANT PLS_INTEGER := 3;
    v_success BOOLEAN := FALSE;
BEGIN
    WHILE v_attempt < v_max_attempts
      AND NOT v_success
    LOOP
        v_attempt := v_attempt + 1;

        DBMS_OUTPUT.PUT_LINE(
            'Attempt ' || v_attempt
        );

        -- Simulate success condition on the third attempt.
        IF v_attempt = 3 THEN
            v_success := TRUE;
        END IF;
    END LOOP;

    IF v_success THEN
        DBMS_OUTPUT.PUT_LINE('Completed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Attempts exhausted');
    END IF;
END;
/
~~~

When applying to real operations:

- Cap the number of attempts.
- Only retry recoverable errors.
- Include a wait/backoff if required by the system.
- Avoid repeating non-idempotent operations without an idempotency key.
- Log enough detail for investigation.

Do not retry indefinitely when the error is a data error, permission error, or fixed constraint violation.

## 15. CONTINUE to Filter Out Unneeded Items

Suppose you need to process a list of numbers while skipping numbers not divisible by 3:

~~~sql
BEGIN
    FOR i IN 1 .. 15 LOOP
        CONTINUE WHEN MOD(i, 3) <> 0;

        DBMS_OUTPUT.PUT_LINE(
            'Process value ' || i
        );
    END LOOP;
END;
/
~~~

CONTINUE makes the "skip this iteration" intent explicit. For complex conditions, you can wrap the logic to run in an IF:

~~~sql
BEGIN
    FOR i IN 1 .. 15 LOOP
        IF MOD(i, 3) = 0 THEN
            DBMS_OUTPUT.PUT_LINE(
                'Process value ' || i
            );
        END IF;
    END LOOP;
END;
/
~~~

Both approaches can produce the same result. Choose whichever is more readable in context; avoid chaining too many CONTINUE statements that make control flow hard to follow.

## 16. Exception Handling Inside Loops

If a statement inside a loop body raises an exception and it is not handled in the current block, execution leaves that block. The loop does not automatically proceed to the next iteration.

If you want one failing row not to halt processing of the remaining rows, you can place a BEGIN...EXCEPTION...END block inside the loop.

Example:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        BEGIN
            IF i = 3 THEN
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Simulated error at value 3'
                );
            END IF;

            DBMS_OUTPUT.PUT_LINE('Processed ' || i);

        EXCEPTION
            WHEN OTHERS THEN
                DBMS_OUTPUT.PUT_LINE(
                    'Failed at ' || i || ': ' || SQLERRM
                );
        END;
    END LOOP;
END;
/
~~~

The exception is handled inside the sub-block for iteration I = 3. After the handler finishes normally, the FOR loop continues with I = 4.

### 16.1. Rollback Scope of a Failing Statement

Oracle guarantees statement-level atomicity: if a DML statement fails, the effects of that individual statement are rolled back. Prior successful DML statements in the transaction remain active until COMMIT or ROLLBACK.

If an iteration runs multiple DML statements and the second one fails, the first one may still remain in the transaction. If an entire iteration must be treated as a single unit, use a SAVEPOINT before the iteration and ROLLBACK TO in the exception handler:

~~~sql
DECLARE
BEGIN
    FOR i IN 1 .. 5 LOOP
        SAVEPOINT before_iteration;

        BEGIN
            INSERT INTO lab_loop_result (
                value_no, square_value, created_at
            )
            VALUES (100 + i, i * i, SYSDATE);

            IF i = 3 THEN
                RAISE_APPLICATION_ERROR(
                    -20003,
                    'Stop this iteration'
                );
            END IF;

        EXCEPTION
            WHEN OTHERS THEN
                ROLLBACK TO before_iteration;
                DBMS_OUTPUT.PUT_LINE(
                    'Rolled back iteration ' || i
                );
        END;
    END LOOP;
END;
/
~~~

This example illustrates a rollback boundary per iteration. In a real application, name savepoints appropriately and align them with the transaction managed by the caller; savepoints belong to the session's transaction, not as independent local variables.

### 16.2. Do Not Blindly Swallow Errors

WHEN OTHERS can help handle row-level errors, but do not merely print a message and ignore every error. Classify errors:

- Data errors that business rules allow skipping.
- Transient errors that can be retried.
- Configuration/permission errors that should stop processing.
- System errors that require rollback and propagation to the caller.

If unrecoverable, re-RAISE the exception or record the batch failure status per workflow rules.

## 17. Loops and BOOLEAN Variables

PL/SQL has the BOOLEAN type in PL/SQL with three states: TRUE, FALSE, and NULL. BOOLEAN is not a standard SQL table column type in many Oracle versions prior to 23c; do not confuse PL/SQL BOOLEAN variables with table storage types.

Example:

~~~sql
DECLARE
    v_continue BOOLEAN := TRUE;
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_continue LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);

        IF v_counter >= 3 THEN
            v_continue := FALSE;
        ELSE
            v_counter := v_counter + 1;
        END IF;
    END LOOP;
END;
/
~~~

A WHILE condition continues only while the BOOLEAN is TRUE. If the BOOLEAN variable is NULL, the body does not run. When using BOOLEAN to control a loop, initialize it and ensure every update branch is meaningful.

## 18. Loops and Performance: Row-by-Row vs. Set-Based SQL

PL/SQL loops incur loop control overhead and can cause frequent context switches between the PL/SQL engine and the SQL engine. For bulk data operations, a single SQL statement can often process them more efficiently.

### 18.1. Row-by-Row Approach

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id
        FROM lab_employee
        WHERE department_id = 10
    ) LOOP
        UPDATE lab_employee
        SET employee_status = 'INACTIVE'
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

### 18.2. Set-Based Approach

~~~sql
UPDATE lab_employee
SET employee_status = 'INACTIVE'
WHERE department_id = 10;
~~~

If every row receives the same update, the set-based UPDATE statement is shorter and usually far more efficient.

### 18.3. When Is a Loop Reasonable?

- Each row needs different processing rules that depend on previous results.
- You need to invoke a PL/SQL procedure per element.
- You need retry control or per-record error handling.
- You must traverse a cursor in order and execute sequential logic.
- The input logic cannot be expressed cleanly in a single SQL statement.

If a loop must execute thousands or millions of individual DML operations, evaluate BULK COLLECT and FORALL. Bulk processing reduces context switches while still preserving batch-level handling.

## 19. BULK COLLECT and FORALL as an Optimization Path When PL/SQL Is Needed

BULK COLLECT fetches multiple rows from SQL into a collection; FORALL sends corresponding multiple DML statements via bulk binding.

Conceptual example:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF lab_employee.employee_id%TYPE;
    v_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM lab_employee
    WHERE department_id = 10;

    FORALL i IN 1 .. v_ids.COUNT
        UPDATE lab_employee
        SET employee_status = 'INACTIVE'
        WHERE employee_id = v_ids(i);
END;
/
~~~

The example assumes LAB_EMPLOYEE exists with the corresponding columns. With large row counts, unbounded BULK COLLECT can consume significant PGA; use LIMIT with cursor fetches in batches where appropriate. FORALL supports the SAVE EXCEPTIONS option to capture per-element errors, though its handling must be designed carefully.

Do not use BULK COLLECT/FORALL if a set-based SQL statement already fulfills the business requirement; bulk PL/SQL is still more complex than pure SQL.

## 20. Common Mistakes When Writing Loops

| Symptom | Cause | Resolution |
|---|---|---|
| Infinite loop | Control variable never changes or condition can never become FALSE | Check all paths, cap iteration count |
| WHILE does not run | Condition is FALSE or NULL from the start | Check the value and type of the control variable |
| LOOP runs one extra time | EXIT placed after processing that should be skipped | Place EXIT WHEN before the relevant body or use WHILE |
| FOR LOOP does not run | Lower bound is greater than upper bound | Check bounds; use REVERSE to count down |
| Assigning to FOR index causes compile error | Loop index is implicitly declared and read-only | Use a separate variable or WHILE/LOOP |
| EXIT exits only inner loop | Unlabeled EXIT terminates only the nearest loop | Use EXIT label to exit an outer loop |
| CONTINUE causes infinite WHILE | Skips the statement updating the control variable | Update the variable before CONTINUE or restructure |
| Cursor FOR LOOP stops after an error | Unhandled exception exits the loop block | Handle exceptions inside each iteration if business rules allow |
| Slow program when processing many rows | Row-by-row DML, excessive context switches | Consider set-based SQL, BULK COLLECT/FORALL |
| Processing order differs from expected | SELECT has no ORDER BY | Add ORDER BY when order matters |

## 21. Practice Exercises

### Exercise 1 — Basic LOOP

Write a LOOP that prints numbers from 1 to 10. Use EXIT WHEN to stop after printing 10.

**Requirement:** place the increment statement in the right position and explain why 11 is not printed.

### Exercise 2 — WHILE LOOP

Write a WHILE LOOP that calculates the sum of numbers from 1 to 100.

**Hint:** use a counter variable and a sum variable; the stopping condition is when the counter exceeds 100.

### Exercise 3 — FOR LOOP

Use a FOR LOOP to print the 7 multiplication table from 7 × 1 to 7 × 10.

### Exercise 4 — FOR REVERSE

Use FOR REVERSE to count down from 20 to 1. Then try bounds REVERSE 20 .. 1 and explain why no iterations run.

### Exercise 5 — EXIT in Nested Loops

Create two FOR loops. When the outer variable is 2 and the inner variable is 3, use an unlabeled EXIT. Observe which loop terminates.

Then change it to EXIT outer_loop and compare the output.

### Exercise 6 — CONTINUE

Write a FOR LOOP from 1 to 30 that prints only numbers divisible by 5. Use CONTINUE WHEN to skip the other numbers.

### Exercise 7 — WHILE and CONTINUE

Write a WHILE LOOP with a counter from 1 to 10, skipping 5 using CONTINUE.

**Requirement:** ensure the counter still increments when 5 is skipped and explain the risk of an infinite loop if the variable is not updated.

### Exercise 8 — Cursor FOR LOOP

Use a cursor FOR LOOP to read employees by department_id and print employee_id and employee_name in ascending order.

### Exercise 9 — Per-Row Exceptions

Write a FOR LOOP from 1 to 5. Intentionally raise an error on iteration 3 and handle it in a sub-block so iterations 4 and 5 still execute.

### Exercise 10 — Choosing SQL or LOOP

A table has 100000 employees. The requirement is to update STATUS to INACTIVE for all employees in DEPARTMENT_ID = 10.

**Question:** should you use a single UPDATE statement or a cursor FOR LOOP? Explain based on set-based SQL and row-by-row processing overhead.

## 22. Process for Selecting a Loop Construct

Before writing a loop, determine:

1. Is the number of iterations known in advance?
2. Should the condition be checked before or after running the body?
3. Is the control variable managed by Oracle or updated by the developer?
4. Do you need to exit early or skip an iteration?
5. Are there nested loops where you need to affect an outer loop?
6. Are you iterating over SQL query results?
7. If one iteration fails, should the whole job stop or continue with the next row?
8. Can the loop be replaced with a single set-based SQL statement?

Suggestions:

| Need | Construct |
|---|---|
| Run until an internal stopping condition is met | LOOP + EXIT WHEN |
| Run only while an initial condition remains TRUE | WHILE LOOP |
| Iterate over a known numeric range | FOR LOOP |
| Count downward | FOR REVERSE |
| Iterate through SELECT rows | Cursor FOR LOOP |
| Terminate current loop | EXIT |
| Skip rest of current iteration | CONTINUE |
| Exit/skip iteration of an outer loop | EXIT label / CONTINUE label |
| Bulk update/delete under the same condition | Prefer set-based SQL |

Decision diagram:

~~~text
Need repetition to process work?
          |
          v
Can it be solved with one SQL statement?
       /              \
     Yes               No
      |                 |
      v                 v
Set-based SQL     Iterate cursor or count?
                        |
                  +-----+-----+
                  |           |
                Cursor    Iteration count
                  |           |
                  v           v
            Cursor FOR    Numeric bounds known?
               LOOP          /    \
                           Yes     No
                            |       |
                            v       v
                        FOR LOOP  Leading condition?
                                    /    \
                                  Yes     No
                                   |       |
                                   v       v
                                 WHILE   LOOP
                                   |
                                   v
                       Need early exit/skip?
                                   |
                                   v
                             EXIT / CONTINUE
~~~

LOOP, WHILE, and FOR address different iteration patterns in PL/SQL. LOOP gives flexible control over stopping points; WHILE checks the condition before each iteration; FOR manages a loop index over a defined range; cursor FOR LOOP automatically handles iterating over query results. EXIT ends a loop, while CONTINUE skips the remainder of the current iteration. Combining labels in nested loops lets you control the exact level to exit or continue. Make sure every loop has a termination path, handle NULL conditions explicitly, and consider set-based SQL before opting for row-by-row processing.
