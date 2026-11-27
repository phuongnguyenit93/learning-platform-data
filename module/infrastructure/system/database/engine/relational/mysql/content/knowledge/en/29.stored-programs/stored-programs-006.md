# IF, CASE, LOOP, WHILE, REPEAT, and LEAVE/ITERATE

Stored programs let you encapsulate multiple SQL statements into a single unit stored on MySQL Server. Beyond running queries and updating data, stored programs also need to branch execution paths, loop through a sequence of steps, and exit early when a condition is met. MySQL provides the control structures `IF`, `CASE`, `LOOP`, `WHILE`, `REPEAT`, `LEAVE`, and `ITERATE` for this purpose.

Choosing the right control structure keeps routines readable, avoids infinite loops, and handles `NULL` cases explicitly. This lesson focuses on the syntax, semantics, combinations, and common mistakes when using these structures in stored procedures, stored functions, triggers, and events.

## 1. Flow control in stored programs

MySQL supports the following control structures inside stored programs:

| Structure | Role |
|---|---|
| `IF` | Branch based on one or more conditions |
| `CASE` | Branch based on a value or conditions |
| `LOOP` | Repeat with no built-in top/bottom condition check; typically exited via `LEAVE` |
| `WHILE` | Repeat while a top-tested condition remains true |
| `REPEAT` | Execute the loop body first, then check the termination condition |
| `LEAVE` | Exit a labeled block or loop |
| `ITERATE` | Skip the remainder of the current iteration and start the next iteration |

These structures can be nested. For example, an `IF` can sit inside a `WHILE`, and a `CASE` can sit inside a `LOOP`. MySQL does not support a `FOR` loop; when counter-based iteration is needed, `WHILE`, `REPEAT`, or `LOOP` is typically used.

These structures reside inside the body of a stored program, usually a `BEGIN ... END` compound statement. They are not control syntax for a plain `SELECT` query, even though SQL also has a `CASE` expression and an `IF()` function usable directly in queries.

## 2. BEGIN ... END skeleton, local variables, and DELIMITER

Example of a simple procedure:

```sql
DELIMITER //

CREATE PROCEDURE show_message(IN p_name VARCHAR(100))
BEGIN
    DECLARE v_message VARCHAR(150) DEFAULT '';

    SET v_message = CONCAT('Hello, ', p_name);
    SELECT v_message AS message;
END//

DELIMITER ;
```

`BEGIN ... END` groups multiple statements into a single compound statement. Each inner statement still ends with a semicolon (`;`).

### 2.1. Why is DELIMITER needed?

In the MySQL command-line client, a semicolon by default terminates a command sent to the server. Using semicolons inside a procedure could cause the client to send the routine body prematurely. The `DELIMITER //` directive temporarily changes the client-side command terminator; once the routine definition finishes, `DELIMITER ;` restores the default.

`DELIMITER` is a client command, not an SQL statement executed by the server. When using a driver or API to submit `CREATE PROCEDURE`, you normally send the entire definition as a single statement per driver conventions, without sending `DELIMITER` lines as SQL.

### 2.2. Variable declarations and scope

Local variables are declared with `DECLARE` at the top of a `BEGIN ... END` block, before executable statements:

```sql
BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_total DECIMAL(12,2) DEFAULT 0.00;

    SET v_count = 10;
    SET v_total = 125.50;
END
```

- Without `DEFAULT`, a local variable's initial value is `NULL`.
- A variable's scope is the block where it is declared and any nested inner blocks, unless an inner block declares a variable with the same name.
- Each nested block can declare its own variables at the top of that block.
- Use `SET` to assign values to local variables.

Prefix variable names with `v_` and parameter names with `p_` to avoid collisions with column names in SQL.

## 3. Boolean conditions and NULL values

The conditions in `IF`, `CASE`, `WHILE`, and `REPEAT` are search conditions. SQL logic has three truth states:

| Condition result | Meaning |
|---|---|
| `TRUE` | Condition holds |
| `FALSE` | Condition does not hold |
| `UNKNOWN (NULL)` | Indeterminate because `NULL` is involved |

Key point: only a condition evaluating to `TRUE` takes the `THEN` branch or keeps a loop condition satisfied. `FALSE` and `UNKNOWN` are not treated as `TRUE`.

Example:

```sql
IF p_amount > 100 THEN
    SET v_level = 'HIGH';
ELSE
    SET v_level = 'NORMAL';
END IF;
```

If `p_amount` is `NULL`, `p_amount > 100` is not `TRUE`, so the `ELSE` branch runs. If business logic must distinguish missing values from low values, check `NULL` first:

```sql
IF p_amount IS NULL THEN
    SET v_level = 'UNKNOWN';
ELSEIF p_amount > 100 THEN
    SET v_level = 'HIGH';
ELSE
    SET v_level = 'NORMAL';
END IF;
```

Comparisons against `NULL` using `=` or `<>` do not test for `NULL`. Use `IS NULL` or `IS NOT NULL`.

## 4. IF statement

`IF` selects a branch based on conditions. Syntax:

```sql
IF search_condition THEN
    statement_list
[ELSEIF search_condition THEN
    statement_list] ...
[ELSE
    statement_list]
END IF;
```

`ELSEIF` is a single keyword, not `ELSE IF`. Every branch must contain at least one statement; do not leave an empty `statement_list`.

### 4.1. IF ... THEN ... ELSE

```sql
DELIMITER //

CREATE PROCEDURE classify_payment(
    IN p_amount DECIMAL(12,2),
    OUT p_result VARCHAR(20)
)
BEGIN
    IF p_amount IS NULL THEN
        SET p_result = 'UNKNOWN';
    ELSEIF p_amount <= 0 THEN
        SET p_result = 'INVALID';
    ELSE
        SET p_result = 'VALID';
    END IF;
END//

DELIMITER ;
```

Calling the procedure:

```sql
CALL classify_payment(250.00, @result);
SELECT @result;
```

The procedure returns `VALID`. Passing `NULL` produces `UNKNOWN`; passing `0` or a negative number produces `INVALID`.

### 4.2. Multiple ELSEIF branches

When classifying by value ranges, order conditions clearly:

```sql
IF p_score IS NULL THEN
    SET p_grade = 'NOT_GRADED';
ELSEIF p_score < 0 OR p_score > 100 THEN
    SET p_grade = 'OUT_OF_RANGE';
ELSEIF p_score >= 90 THEN
    SET p_grade = 'A';
ELSEIF p_score >= 80 THEN
    SET p_grade = 'B';
ELSEIF p_score >= 65 THEN
    SET p_grade = 'C';
ELSE
    SET p_grade = 'D';
END IF;
```

MySQL evaluates from top to bottom and executes the first branch whose condition is `TRUE`. Therefore, boundary conditions and branch order matter. Putting `p_score >= 65` before `p_score >= 90` would classify a score of `95` as `C`.

### 4.3. Nested IF

An `IF` can be placed inside a branch of another `IF`:

```sql
IF p_status = 'ACTIVE' THEN
    IF p_balance > 0 THEN
        SET p_message = 'ACTIVE_WITH_BALANCE';
    ELSE
        SET p_message = 'ACTIVE_NO_BALANCE';
    END IF;
ELSE
    SET p_message = 'INACTIVE';
END IF;
```

Each `IF` requires its own `END IF`. For multiple independent conditional branches, `ELSEIF` is usually easier to read than deeply nested `IF`s.

### 4.4. When to use IF?

Use `IF` when you need to:

- Validate input conditions or `NULL` cases.
- Classify across multiple potentially differing conditions.
- Combine conditions with `AND`, `OR`, `NOT`.
- Execute one branch and continue with statements after `END IF`.

## 5. CASE statement

The `CASE` statement is a multi-way branching structure in stored programs. There are two forms: simple `CASE`, which compares one expression against values, and searched `CASE`, which evaluates individual conditions.

### 5.1. Simple CASE

Syntax:

```sql
CASE case_value
    WHEN when_value THEN
        statement_list
    [WHEN when_value THEN
        statement_list] ...
    [ELSE
        statement_list]
END CASE;
```

Example classifying order statuses:

```sql
DELIMITER //

CREATE PROCEDURE describe_order_status(
    IN p_status VARCHAR(20),
    OUT p_description VARCHAR(100)
)
BEGIN
    CASE p_status
        WHEN 'NEW' THEN
            SET p_description = 'Pending';
        WHEN 'PAID' THEN
            SET p_description = 'Paid';
        WHEN 'SHIPPED' THEN
            SET p_description = 'Shipped';
        WHEN 'CANCELLED' THEN
            SET p_description = 'Cancelled';
        ELSE
            SET p_description = 'Unknown status';
    END CASE;
END//

DELIMITER ;
```

Simple `CASE` compares `case_value` against each `when_value`. The first matching branch executes; if none match, `ELSE` executes if present.

### 5.2. Searched CASE

Searched `CASE` does not compare a single shared value; each `WHEN` can be an independent condition:

```sql
CASE
    WHEN p_total IS NULL THEN
        SET p_tier = 'UNKNOWN';
    WHEN p_total < 0 THEN
        SET p_tier = 'INVALID';
    WHEN p_total >= 10000000 THEN
        SET p_tier = 'PLATINUM';
    WHEN p_total >= 5000000 THEN
        SET p_tier = 'GOLD';
    WHEN p_total >= 1000000 THEN
        SET p_tier = 'SILVER';
    ELSE
        SET p_tier = 'STANDARD';
END CASE;
```

Conditions are evaluated in order; the first `TRUE` branch runs. Just like `IF`, place special conditions such as `IS NULL` and boundary checks before broader branches.

### 5.3. CASE without ELSE

Unlike `IF`, if no `WHEN` matches and a `CASE` statement has no `ELSE`, MySQL raises the error `Case not found for CASE statement`. Therefore, when input may contain unexpected values, write an explicit `ELSE`:

```sql
CASE p_status
    WHEN 'NEW' THEN
        SET p_message = 'New order';
    WHEN 'PAID' THEN
        SET p_message = 'Paid order';
    ELSE
        SET p_message = 'Other status';
END CASE;
```

If nothing truly needs to be done when no branch matches, `ELSE` can contain an empty compound block:

```sql
CASE p_status
    WHEN 'NEW' THEN
        SET p_message = 'New order';
    ELSE
        BEGIN
        END;
END CASE;
```

A `CASE` statement does not support `ELSE NULL` like a `CASE` expression. In most business workflows, assigning a default status is clearer.

### 5.4. Do not use simple CASE to check for NULL

Do not write:

```sql
CASE p_status
    WHEN NULL THEN
        SET p_message = 'Missing';
    ELSE
        SET p_message = 'Present';
END CASE;
```

Comparing `NULL = NULL` does not yield `TRUE`, so `WHEN NULL` never matches `NULL`. Use searched `CASE`:

```sql
CASE
    WHEN p_status IS NULL THEN
        SET p_message = 'Missing';
    WHEN p_status = 'NEW' THEN
        SET p_message = 'New';
    ELSE
        SET p_message = 'Other';
END CASE;
```

### 5.5. CASE statement vs. CASE expression

The two constructs serve different purposes:

| `CASE` statement | `CASE` expression |
|---|---|
| Controls statement execution inside stored programs | Returns a value inside SQL expressions |
| Has `statement_list` after `THEN` | Has a result expression after `THEN` |
| Ends with `END CASE` | Ends with `END` |
| Raises an error if `ELSE` is absent and nothing matches | Returns `NULL` if `ELSE` is absent and nothing matches |

Example `CASE` expression inside a query:

```sql
SELECT
    order_id,
    CASE
        WHEN total_amount >= 1000000 THEN 'HIGH'
        WHEN total_amount > 0 THEN 'NORMAL'
        ELSE 'ZERO_OR_INVALID'
    END AS amount_group
FROM orders;
```

Similarly, `IF ... END IF` is an `IF` statement in stored programs, whereas `IF(condition, value_if_true, value_if_false)` is the `IF()` function returning a value inside an SQL expression.

## 6. LOOP statement

`LOOP` repeats a statement list with no built-in condition check at the top or bottom. The loop body typically checks its own condition and uses `LEAVE` to exit.

Syntax:

```sql
[begin_label:] LOOP
    statement_list
END LOOP [end_label];
```

Without a reachable path executing `LEAVE` or another valid exit, `LOOP` can run infinitely.

### 6.1. Example summing from 1 to N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_loop(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_n IS NULL OR p_n < 1 THEN
        SET p_sum = 0;
    ELSE
        sum_loop: LOOP
            IF v_i > p_n THEN
                LEAVE sum_loop;
            END IF;

            SET v_total = v_total + v_i;
            SET v_i = v_i + 1;
        END LOOP sum_loop;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Test call:

```sql
CALL sum_to_loop(5, @total);
SELECT @total AS total; -- 15
```

Execution flow:

1. Initialize `v_i = 1`, `v_total = 0`.
2. Check `v_i > p_n`.
3. If true, `LEAVE sum_loop` exits the loop.
4. If false, add `v_i` to total and increment the counter.
5. Return to the top of `LOOP`.

Checking the exit condition before processing avoids adding an out-of-bounds value.

### 6.2. When to use LOOP?

Use `LOOP` when the exit condition sits in the middle of the body or there are multiple exit points. If the continuation condition is simple and always checked at the top, `WHILE` is usually easier to read.

## 7. WHILE statement

`WHILE` tests the condition before each iteration. The loop body runs only when the condition is `TRUE`.

Syntax:

```sql
[begin_label:] WHILE search_condition DO
    statement_list
END WHILE [end_label];
```

If the condition is `FALSE` or `UNKNOWN` initially, the loop body does not execute at all.

### 7.1. Example summing from 1 to N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_while(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    WHILE v_i <= p_n DO
        SET v_total = v_total + v_i;
        SET v_i = v_i + 1;
    END WHILE;

    SET p_sum = v_total;
END//

DELIMITER ;
```

Example:

```sql
CALL sum_to_while(5, @total);
SELECT @total AS total; -- 15
```

When `p_n` is `0` or negative, `1 <= p_n` is false and the result is `0`. When `p_n` is `NULL`, the condition is not `TRUE`, so the body does not run either; however, if business logic must distinguish `NULL` from `0`, check `NULL` explicitly instead of letting both return the same result.

### 7.2. Avoiding non-terminating loops

Every iteration must update state so the condition can eventually become `FALSE`:

```sql
WHILE v_i <= p_n DO
    -- Process work
    SET v_i = v_i + 1;
END WHILE;
```

Forgetting to increment `v_i` keeps the condition true and the procedure can run forever. For loops depending on multiple variables, verify all variables involved in the condition.

## 8. REPEAT statement

`REPEAT` executes the loop body first, then evaluates the `UNTIL` condition. Thus, the loop body always executes at least once.

Syntax:

```sql
[begin_label:] REPEAT
    statement_list
UNTIL search_condition
END REPEAT [end_label];
```

The loop terminates when `search_condition` is `TRUE`. If the condition is `FALSE` or `UNKNOWN`, the next iteration begins.

### 8.1. Example summing from 1 to N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_repeat(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_n IS NULL OR p_n < 1 THEN
        SET p_sum = 0;
    ELSE
        REPEAT
            SET v_total = v_total + v_i;
            SET v_i = v_i + 1;
        UNTIL v_i > p_n
        END REPEAT;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Test call:

```sql
CALL sum_to_repeat(5, @total);
SELECT @total AS total; -- 15
```

With `p_n = 1`, the body runs once, adds `1`, increments `v_i` to `2`, and then `2 > 1` terminates the loop.

### 8.2. Why validate inputs before REPEAT?

Without `IF p_n IS NULL OR p_n < 1`, the `REPEAT` body still runs at least once. When `p_n = 0`, the example would add `1` even though the expected result is `0`. With `NULL` input, the `UNTIL` condition might never become `TRUE` unless control variables are updated appropriately.

Check preconditions before entering `REPEAT` if executing even a single iteration is not permitted.

## 9. Comparing LOOP, WHILE, and REPEAT

| Criterion | `LOOP` | `WHILE` | `REPEAT` |
|---|---|---|---|
| Condition check | Placed manually in the body | Before body | After body |
| Minimum iterations | 1 entry into body before `LEAVE`; infinite without `LEAVE` | 0 | 1 |
| Common exit mechanism | `LEAVE label` | `WHILE` condition becomes `FALSE`/`UNKNOWN`, or `LEAVE` | `UNTIL` condition becomes `TRUE`, or `LEAVE` |
| Best suited for | Multiple exit points or mid-body exit checks | Looping while a condition stays true | Must run at least once before checking |
| Common pitfall | Forgetting `LEAVE` | Failing to update loop variable | Never reaching `UNTIL` or skipping preconditions |

The same algorithm can be written in all three forms. Choose the form that expresses condition-checking timing most clearly, not just the shortest syntax.

## 10. LEAVE statement

`LEAVE label` exits the labeled control structure:

```sql
LEAVE loop_label;
```

`LEAVE` can be used in:

- `LOOP`
- `WHILE`
- `REPEAT`
- Labeled `BEGIN ... END` blocks

If the label belongs to the outermost block of a stored program, `LEAVE` exits that program block.

Example exiting a block early:

```sql
DELIMITER //

CREATE PROCEDURE validate_code(
    IN p_code VARCHAR(20),
    OUT p_message VARCHAR(50)
)
main: BEGIN
    IF p_code IS NULL OR p_code = '' THEN
        SET p_message = 'MISSING_CODE';
        LEAVE main;
    END IF;

    SET p_message = 'VALID_CODE';
END main//

DELIMITER ;
```

When input is invalid, `LEAVE main` exits the block labeled `main`, skipping the `VALID_CODE` assignment.

`LEAVE` does not automatically exit every enclosing loop. It requires a valid label identifying the exact structure to exit.

## 11. ITERATE statement

`ITERATE label` skips the remainder of the current iteration and starts the next iteration of the labeled loop:

```sql
ITERATE loop_label;
```

`ITERATE` can only be used inside `LOOP`, `WHILE`, and `REPEAT`. Do not use `ITERATE` to jump to the start of a `BEGIN ... END` block.

### 11.1. Example summing odd numbers from 1 to N

```sql
DELIMITER //

CREATE PROCEDURE sum_odd_numbers(
    IN p_limit INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_limit IS NULL OR p_limit < 1 THEN
        SET p_sum = 0;
    ELSE
        odd_loop: LOOP
            SET v_i = v_i + 1;

            IF v_i > p_limit THEN
                LEAVE odd_loop;
            END IF;

            IF MOD(v_i, 2) = 0 THEN
                ITERATE odd_loop;
            END IF;

            SET v_total = v_total + v_i;
        END LOOP odd_loop;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Test call:

```sql
CALL sum_odd_numbers(7, @odd_total);
SELECT @odd_total AS odd_total; -- 16 (1 + 3 + 5 + 7)
```

When `v_i` is even, `ITERATE odd_loop` jumps back to the top of the loop and skips adding to the sum. The counter is incremented before `ITERATE`, so the loop continues progressing.

### 11.2. State update ordering

Here is a common mistake:

```sql
IF MOD(v_i, 2) = 0 THEN
    ITERATE odd_loop;
END IF;

SET v_i = v_i + 1;
```

If `v_i` is even, `ITERATE` skips the increment below. The next iteration hits the exact same even value and loops forever. Update counters before `ITERATE`, or place the increment where it always executes.

## 12. Labels and nested loops

Labels can be attached to `BEGIN ... END`, `LOOP`, `WHILE`, and `REPEAT`. Syntax:

```sql
label_name: LOOP
    statement_list
END LOOP label_name;
```

Label rules:

- The opening label must end with a colon (`:`).
- The closing label is optional, but if specified it must match the opening label.
- You cannot specify a closing label without an opening label.
- Labels at the same nesting level must be distinct.
- Maximum label length is 16 characters.

Nested loop example:

```sql
DELIMITER //

CREATE PROCEDURE count_pairs(
    IN p_outer_limit INT,
    IN p_inner_limit INT,
    OUT p_count BIGINT
)
BEGIN
    DECLARE v_outer INT DEFAULT 1;
    DECLARE v_inner INT DEFAULT 1;
    DECLARE v_count BIGINT DEFAULT 0;

    WHILE v_outer <= p_outer_limit DO
        SET v_inner = 1;

        inner_loop: WHILE v_inner <= p_inner_limit DO
            SET v_count = v_count + 1;
            SET v_inner = v_inner + 1;
        END WHILE inner_loop;

        SET v_outer = v_outer + 1;
    END WHILE;

    SET p_count = v_count;
END//

DELIMITER ;
```

With `p_outer_limit = 3` and `p_inner_limit = 2`, the procedure counts 6 pairs.

In nested loops:

- `LEAVE inner_loop` exits only the inner loop.
- `LEAVE outer_loop` exits the outer loop if that label is in a valid enclosing scope.
- `ITERATE inner_loop` starts only the next iteration of the inner loop.
- `ITERATE outer_loop` starts the next iteration of the outer loop; remaining statements in the current outer iteration, including processing after the inner loop, are skipped.

Keep labels short and descriptive of their role, and avoid reusing the same label name across nesting levels.

## 13. Combining IF, CASE, and loops

In practice, a routine may use multiple structures together. The example below iterates through a number sequence, skips multiples of 3, and classifies the remaining numbers:

```sql
DELIMITER //

CREATE PROCEDURE summarize_numbers(
    IN p_limit INT,
    OUT p_small_count INT,
    OUT p_large_count INT
)
BEGIN
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_small INT DEFAULT 0;
    DECLARE v_large INT DEFAULT 0;

    IF p_limit IS NULL OR p_limit < 1 THEN
        SET p_small_count = 0;
        SET p_large_count = 0;
    ELSE
        number_loop: WHILE v_i < p_limit DO
            SET v_i = v_i + 1;

            IF MOD(v_i, 3) = 0 THEN
                ITERATE number_loop;
            END IF;

            CASE
                WHEN v_i < 10 THEN
                    SET v_small = v_small + 1;
                ELSE
                    SET v_large = v_large + 1;
            END CASE;
        END WHILE number_loop;

        SET p_small_count = v_small;
        SET p_large_count = v_large;
    END IF;
END//

DELIMITER ;
```

With limit `12`, the processed numbers are `1, 2, 4, 5, 7, 8, 10, 11`. Result: `6` numbers less than 10 and `2` numbers 10 or greater.

The example shows:

1. `IF` handles invalid input.
2. `WHILE` controls iteration count.
3. `ITERATE` skips multiples of 3.
4. `CASE` classifies the remaining numbers.

When combining multiple structures, consistent indentation and label names prevent confusion over the boundaries of `END IF`, `END CASE`, `END WHILE`, and `END LOOP`.

## 14. Choosing the right control structure

| Need | Structure to consider | Reason |
|---|---|---|
| One condition or a few distinct branches | `IF` | Expresses general conditions |
| Multiple choices against the same value | Simple `CASE` | Avoids repeating the comparison expression |
| Multiple independent conditions | Searched `CASE` | Each branch has its own search condition |
| Loop while a condition holds from the start | `WHILE` | Can run 0 times |
| Must execute at least one iteration | `REPEAT` | Evaluates condition after the body |
| Multiple exit points or mid-body checks | `LOOP` + `LEAVE` | Explicit control over exit points |
| Skip the rest of an iteration | `ITERATE` | Jumps immediately to next iteration |
| Stop a labeled block | `LEAVE block_label` | Exits block without extra `IF` nesting |

Do not use a loop to replace a simple set-based SQL statement. For instance, if you need to update a value across all qualifying rows, a single `UPDATE ... WHERE` statement is usually better than looping over IDs and updating row by row. Loops fit better when each step depends on the previous step's result or when orchestrating a bounded sequence of operations.

## 15. Common errors and fixes

| Error | Cause | How to fix |
|---|---|---|
| `IF` skips the expected branch | Condition returns `FALSE` or `UNKNOWN` due to `NULL` | Check `NULL` with `IS NULL` first |
| `ELSEIF` syntax error | Written as `ELSE IF` or missing `THEN` | Use exact keyword `ELSEIF ... THEN` |
| Missing `END IF` | `IF` branch was not closed | Every `IF` needs exactly one `END IF` |
| `CASE` raises `Case not found` | No branch matched and no `ELSE` present | Add an appropriate `ELSE` branch |
| `WHEN NULL` fails to match | Equality comparison with `NULL` never returns `TRUE` | Use searched `CASE` with `IS NULL` |
| `CASE` statement errors at `END` | Mistakenly used `CASE` expression ending | Use `END CASE` for statements |
| `LOOP` runs forever | Missing `LEAVE` or control variable never changes | Define exit condition and update variables |
| `WHILE` never runs | Initial condition is `FALSE` or `UNKNOWN` | Check input values and initial conditions |
| `REPEAT` runs an extra iteration | `REPEAT` always executes body before checking `UNTIL` | Check preconditions before entering loop |
| `REPEAT` never terminates | `UNTIL` condition never becomes `TRUE` | Check control variables and stop condition |
| `ITERATE` causes an infinite loop | Variable update statement skipped after `ITERATE` | Update state before `ITERATE` |
| `LEAVE`/`ITERATE` cannot find label | Misspelled label or out of scope | Verify opening/closing labels and scope |
| Using `ITERATE` on a `BEGIN` block | `ITERATE` only works on `LOOP`/`WHILE`/`REPEAT` | Use `LEAVE` for blocks or use a labeled loop |
| Client errors mid-`CREATE PROCEDURE` | Client uses `;` to split routine body | Change client delimiter or submit routine as a whole statement via driver |
| Variable declaration error | `DECLARE` appears after an executable statement | Move `DECLARE` to the top of the corresponding block |

## 16. Safety and performance principles when using loops

### 16.1. Always define a termination condition

Before writing a loop, state clearly:

- Which variable controls the loop?
- What is its initial value?
- Which statement modifies the variable?
- Which condition terminates the loop?
- What happens when input is `NULL`, `0`, or negative?

With `LOOP`, always guarantee a reachable path to `LEAVE`. With `WHILE`, verify initial input conditions. With `REPEAT`, remember the body always runs at least once.

### 16.2. Bound iteration counts

If input controls the iteration count, validate its range before starting. Avoid allowing an anomalous parameter to trigger millions or billions of unintended iterations.

### 16.3. Prefer set-based processing

Operations like updating many rows, computing sums, or classifying rows can often be done with a single set-based SQL statement:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND created_at < CURRENT_DATE - INTERVAL 30 DAY;
```

This approach is typically far more efficient than looping row by row and executing separate `UPDATE`s per row. Use loops only when step-by-step control, batching, or coordinating dependent operations is truly required.

### 16.4. Watch variable scope and NULL data

Local variables without `DEFAULT` start as `NULL`. An addition like `v_total = v_total + v_value` produces `NULL` if either operand is `NULL`. Initialize counters and totals to `0`; validate input data or use business-appropriate `NULL`-handling functions.

### 16.5. Keep bodies easy to verify

- Each branch should perform one clear group of tasks.
- Avoid excessive nesting of `IF`/`CASE`/`LOOP`.
- Name labels by purpose rather than generic names like `l1`, `l2`.
- Place counter increments where they cannot be skipped inadvertently.
- Use comments to explain non-obvious exit conditions.

## 17. Testing process for routines with flow control

Before deploying a routine, test at least:

1. Normal true branch.
2. Boundary values right at the threshold.
3. Values just below and above thresholds.
4. `NULL` input.
5. `0` or negative input for numeric parameters.
6. `CASE` receiving values not listed in `WHEN`.
7. Loops running 0 times, 1 time, and multiple times.
8. `ITERATE` branches verifying variables are updated before jumping back.
9. `LEAVE` branches verifying the right loop/block is exited.
10. Nested loops verifying exits do not target the wrong level.

Example test suite for `sum_to_while`:

| Parameter `p_n` | Expected result | What to verify |
|---:|---:|---|
| `NULL` | `0` per current example | `WHILE` condition is `UNKNOWN`, body skipped |
| `-1` | `0` | Initial condition is `FALSE` |
| `0` | `0` | Zero iterations |
| `1` | `1` | One iteration |
| `5` | `15` | Multiple iterations |

In real business routines, you may need to return a distinct status for `NULL` rather than merging `NULL` with `0`. The test suite must reflect that policy.

## 18. Practice exercises

### Exercise 1 — Grade classification with IF

Write a procedure accepting `p_score` and returning `p_grade`:

- `NULL`: `NOT_GRADED`
- Outside `0` to `100`: `INVALID`
- `>= 90`: `A`
- `>= 80` and `< 90`: `B`
- `>= 65` and `< 80`: `C`
- Otherwise: `D`

Test sequentially with `NULL`, `-1`, `0`, `64`, `65`, `79`, `80`, `89`, `90`, `100`, and `101`.

### Exercise 2 — Status mapping with CASE

Write a procedure taking an order status code and returning a description. Use simple `CASE` for `NEW`, `PAID`, `SHIPPED`, `CANCELLED`, with `ELSE` for unknown codes. Then rewrite it using searched `CASE` to explicitly handle `NULL`.

### Exercise 3 — Summing with all three loop types

Write three equivalent procedures using `LOOP`, `WHILE`, and `REPEAT` to sum from 1 to N. Test `N` values `0`, `1`, and `10`. Compare where the stop condition is evaluated in each approach.

### Exercise 4 — Summing odd numbers with ITERATE

Write a procedure summing odd numbers from 1 to N. Use `ITERATE` to skip even numbers and `LEAVE` to stop when exceeding N. Verify the counter increments on every iteration.

### Exercise 5 — Exiting a labeled block

Write a procedure validating an input code. If the code is `NULL` or empty, assign a business error message to an `OUT` parameter and `LEAVE` the outermost block. If valid, continue processing and assign a success message.

## 19. Checklist before finalizing a stored program

- Did you properly use `IF ... END IF` and `CASE ... END CASE`?
- Did you distinguish the `IF` statement from the `IF()` function?
- Did you distinguish the `CASE` statement from the `CASE` expression?
- Are `NULL` conditions handled according to business logic?
- Does the `CASE` statement have an `ELSE` for unmatched cases?
- Are all local variables `DECLARE`d at the top of the block and properly initialized?
- Does every `LOOP` have a guaranteed path to `LEAVE`?
- Does `WHILE` have a proper initial condition?
- Does `REPEAT` account for its body always running at least once?
- Could `ITERATE` inadvertently skip a required variable update?
- Do `LEAVE`/`ITERATE` reference the right label and nesting level?
- Are label names at most 16 characters and unique within the same nesting level?
- Is every block closed with its matching `END` keyword?
- Is `DELIMITER` used properly in the client?
- Could a loop be replaced by a simpler set-based SQL statement?
- Have boundary and `NULL` cases been tested?

## 20. Official references

- [MySQL 9.7 — Flow Control Statements](https://dev.mysql.com/doc/refman/9.7/en/flow-control-statements.html)
- [MySQL 9.7 — IF Statement](https://dev.mysql.com/doc/refman/9.7/en/if.html)
- [MySQL 9.7 — CASE Statement](https://dev.mysql.com/doc/refman/9.7/en/case.html)
- [MySQL 9.7 — LOOP Statement](https://dev.mysql.com/doc/refman/9.7/en/loop.html)
- [MySQL 9.7 — WHILE Statement](https://dev.mysql.com/doc/refman/9.7/en/while.html)
- [MySQL 9.7 — REPEAT Statement](https://dev.mysql.com/doc/refman/9.7/en/repeat.html)
- [MySQL 9.7 — LEAVE Statement](https://dev.mysql.com/doc/refman/9.7/en/leave.html)
- [MySQL 9.7 — ITERATE Statement](https://dev.mysql.com/doc/refman/9.7/en/iterate.html)
- [MySQL 9.7 — Statement Labels](https://dev.mysql.com/doc/refman/9.7/en/statement-labels.html)
- [MySQL 9.7 — Local Variable DECLARE Statement](https://dev.mysql.com/doc/refman/9.7/en/declare-local-variable.html)
- [MySQL 9.7 — BEGIN ... END Compound Statement](https://dev.mysql.com/doc/refman/9.7/en/begin-end.html)
- [MySQL 8.0 — Flow Control Statements](https://dev.mysql.com/doc/refman/8.0/en/flow-control-statements.html)

## Conclusion

`IF` and `CASE` control branching; `LOOP`, `WHILE`, and `REPEAT` control iteration; `LEAVE` exits a labeled block or loop, while `ITERATE` starts the next iteration of a loop. The key distinction among loops is when the condition is tested: `WHILE` checks before the body, `REPEAT` checks after the body and always executes at least once, and `LOOP` requires an explicitly designed exit path. When writing stored programs, handle `NULL` explicitly, declare variables in the right place, use valid labels, and ensure loop control variables advance to prevent infinite loops. For bulk data operations, prefer set-based SQL when it can clearly and safely replace a loop.
