# IF, ELSIF, CASE, and Conditional Branching

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** PL/SQL Basics  
> **Objective:** Use conditional structures in PL/SQL to control execution flow: IF, ELSIF, ELSE, CASE statement, and CASE expression. Understand how Oracle evaluates TRUE/FALSE/NULL conditions, how to order branches, how to handle NULL values, choosing between IF and CASE, and applying them to data validation, business calculations, DML, and SQL queries.

## 1. Controlling Flow with Conditions

A program often needs to choose an action based on input data or current state. For example:

- If the balance is sufficient, allow withdrawal; if insufficient, reject it.
- If a score meets a high threshold, assign grade A; if it meets a lower threshold, assign grade B.
- If an order is paid, move to the shipping step; if not, wait for payment.
- If a variable has no value yet, request additional data.
- If multiple conditions can be true simultaneously, select a branch in priority order.

In PL/SQL, the two commonly used structure groups are:

1. **IF statement:** executes a block of statements when a condition is true; may include ELSIF and ELSE.
2. **CASE:** selects one branch. A CASE statement controls flow in PL/SQL; a CASE expression returns a value for use in expressions or SQL statements.

IF example:

~~~sql
DECLARE
    l_balance NUMBER := 500;
    l_withdrawal NUMBER := 200;
BEGIN
    IF l_balance >= l_withdrawal THEN
        DBMS_OUTPUT.PUT_LINE('Withdrawal allowed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Insufficient balance');
    END IF;
END;
/
~~~

CASE statement example:

~~~sql
DECLARE
    l_status VARCHAR2(20) := 'PAID';
BEGIN
    CASE l_status
        WHEN 'NEW' THEN
            DBMS_OUTPUT.PUT_LINE('Waiting for payment');
        WHEN 'PAID' THEN
            DBMS_OUTPUT.PUT_LINE('Ready for fulfillment');
        WHEN 'CANCELLED' THEN
            DBMS_OUTPUT.PUT_LINE('Order cancelled');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Unknown status');
    END CASE;
END;
/
~~~

Conditions do more than give a program multiple branches. They also clarify business rules, handle boundary data, and prevent invalid operations before executing DML.

## 2. IF Statement

General syntax:

~~~sql
IF condition THEN
    statements;
END IF;
~~~

If condition is TRUE, Oracle executes the statements between THEN and END IF. If condition is FALSE or NULL, the block is skipped.

Example:

~~~sql
DECLARE
    l_score NUMBER := 85;
BEGIN
    IF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    END IF;
END;
/
~~~

If L_SCORE is 40, the message is not printed. If L_SCORE is NULL, the expression L_SCORE >= 50 evaluates to UNKNOWN/NULL and the THEN block does not run either.

### 2.1. IF with ELSE

Use ELSE when you need to define an action for all remaining cases:

~~~sql
IF condition THEN
    statements_if_true;
ELSE
    statements_if_not_true;
END IF;
~~~

Example:

~~~sql
DECLARE
    l_quantity NUMBER := 0;
BEGIN
    IF l_quantity > 0 THEN
        DBMS_OUTPUT.PUT_LINE('In stock');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No available quantity');
    END IF;
END;
/
~~~

Note: ELSE executes whenever the condition is not TRUE, which includes both FALSE and NULL. If NULL has a distinct meaning, check for it in its own branch.

### 2.2. IF with ELSIF

When there are multiple cases, use ELSIF:

~~~sql
IF condition_1 THEN
    statements_1;
ELSIF condition_2 THEN
    statements_2;
ELSIF condition_3 THEN
    statements_3;
ELSE
    statements_default;
END IF;
~~~

Oracle evaluates conditions from top to bottom. The first branch whose condition is TRUE is executed; subsequent branches are skipped.

Grading example:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    IF l_score >= 90 THEN
        l_grade := 'A';
    ELSIF l_score >= 80 THEN
        l_grade := 'B';
    ELSIF l_score >= 70 THEN
        l_grade := 'C';
    ELSIF l_score >= 60 THEN
        l_grade := 'D';
    ELSE
        l_grade := 'F';
    END IF;

    DBMS_OUTPUT.PUT_LINE('Grade = ' || l_grade);
END;
/
~~~

With a score of 82, the first condition is FALSE, the second is TRUE, so L_GRADE receives B. Oracle does not continue checking the remaining branches.

### 2.3. ELSIF Is Spelled as a Single Word

The correct keyword in PL/SQL is **ELSIF**:

~~~sql
ELSIF l_score >= 80 THEN
~~~

Do not write ELSEIF or ELSE IF within the same IF structure. Each ELSIF adds a condition to the same IF construct, and only one END IF closes the entire construct.

### 2.4. Condition Order Determines the Outcome

Example with wrong order:

~~~sql
IF l_score >= 60 THEN
    l_grade := 'D';
ELSIF l_score >= 80 THEN
    l_grade := 'B';
ELSIF l_score >= 90 THEN
    l_grade := 'A';
END IF;
~~~

If the score is 95, the first condition is already TRUE, so the program assigns D. The 80 and 90 branches are never evaluated.

Reorder from the highest threshold downward:

~~~sql
IF l_score >= 90 THEN
    l_grade := 'A';
ELSIF l_score >= 80 THEN
    l_grade := 'B';
ELSIF l_score >= 60 THEN
    l_grade := 'D';
ELSE
    l_grade := 'F';
END IF;
~~~

When conditions have overlapping ranges, place the more specific or higher-priority branch first. Even when conditions do not overlap, the order should still reflect how the business logic reads.

## 3. BOOLEAN Conditions and NULL Values

In PL/SQL, a conditional expression can take three logical states:

- TRUE
- FALSE
- NULL (UNKNOWN)

IF executes the THEN branch only when the condition is TRUE. Both FALSE and NULL fail to satisfy the condition.

Example:

~~~sql
DECLARE
    l_score NUMBER := NULL;
BEGIN
    IF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not passed');
    END IF;
END;
/
~~~

The result is Not passed. However, if NULL means "not yet graded," that message is inaccurate from a business standpoint.

### 3.1. Handling NULL in a Separate Branch

~~~sql
DECLARE
    l_score NUMBER := NULL;
BEGIN
    IF l_score IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Score is not available');
    ELSIF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Failed');
    END IF;
END;
/
~~~

Checking for NULL before comparing helps the program distinguish missing data from low-scoring data.

### 3.2. Do Not Use Equality to Check for NULL

Wrong:

~~~sql
IF l_score = NULL THEN
    DBMS_OUTPUT.PUT_LINE('Missing');
END IF;
~~~

Right:

~~~sql
IF l_score IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Missing');
END IF;
~~~

In PL/SQL, use IS NULL and IS NOT NULL for nullable variables. This rule also applies in SQL conditions.

### 3.3. AND, OR, and NOT with NULL

Three-valued logic affects compound expressions:

| Expression | Result |
|---|---|
| TRUE AND NULL | NULL |
| FALSE AND NULL | FALSE |
| TRUE OR NULL | TRUE |
| FALSE OR NULL | NULL |
| NOT NULL | NULL |

Example:

~~~sql
DECLARE
    l_amount NUMBER := NULL;
BEGIN
    IF l_amount > 0 AND l_amount < 1000 THEN
        DBMS_OUTPUT.PUT_LINE('Within range');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not within range or missing');
    END IF;
END;
/
~~~

The condition is not TRUE, so ELSE runs. If you need to distinguish NULL from out-of-range values, write a separate NULL branch.

### 3.4. BOOLEAN Variables in PL/SQL

PL/SQL supports BOOLEAN variables:

~~~sql
DECLARE
    l_is_valid BOOLEAN;
BEGIN
    l_is_valid := TRUE;

    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not valid');
    END IF;
END;
/
~~~

A BOOLEAN variable can be TRUE, FALSE, or NULL. When unassigned, a BOOLEAN variable defaults to NULL.

Do not confuse PL/SQL BOOLEAN with the ability to store or pass BOOLEAN through SQL. Support for the BOOLEAN type in SQL depends on the Oracle Database release; older versions do not allow BOOLEAN as a regular SQL column type. When cross-version compatibility is needed, NUMBER or CHAR is commonly used to store flags in tables and explicitly converted in PL/SQL.

## 4. Nested IF

An IF can be placed inside another IF branch to handle multi-level rules.

~~~sql
DECLARE
    l_is_member BOOLEAN := TRUE;
    l_order_total NUMBER := 1200;
BEGIN
    IF l_is_member THEN
        IF l_order_total >= 1000 THEN
            DBMS_OUTPUT.PUT_LINE('Member premium discount');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Member standard discount');
        END IF;
    ELSE
        IF l_order_total >= 1000 THEN
            DBMS_OUTPUT.PUT_LINE('Guest large-order offer');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Guest standard price');
        END IF;
    END IF;
END;
/
~~~

IF l_is_member is the outer condition; IF l_order_total is the inner condition inside the chosen branch.

### 4.1. When Should You Nest IF?

Nested IF is appropriate when the inner condition only makes sense after the outer condition is satisfied. For example, checking detailed permissions only after confirming the user is logged in.

However, many levels of nesting make control flow hard to read. You can use ELSIF, CASE, or extract small procedures/functions if the logic becomes too deep.

### 4.2. Checking Conditions in a Safe Order

Example of validating a variable before using it:

~~~sql
IF l_customer_id IS NOT NULL THEN
    IF l_credit_limit > 0 THEN
        -- Perform credit processing
        NULL;
    END IF;
END IF;
~~~

PL/SQL supports short-circuit evaluation for AND/OR in Boolean expressions. However, when logic is critical or involves operations that can fail, write clear conditions and avoid hiding input checks inside hard-to-read expressions.

## 5. CASE Statement

A CASE statement selects a branch of statements in PL/SQL. There are two forms:

1. Simple CASE: compares a selector against WHEN values.
2. Searched CASE: evaluates WHEN conditions sequentially.

A CASE statement ends with END CASE; unlike a CASE expression, which ends with END.

## 6. Simple CASE Statement

Syntax:

~~~sql
CASE selector
    WHEN value_1 THEN
        statements_1;
    WHEN value_2 THEN
        statements_2;
    WHEN value_3 THEN
        statements_3;
    ELSE
        default_statements;
END CASE;
~~~

Oracle compares the selector with each WHEN value. When a matching branch is found, it executes that branch and exits CASE.

Example:

~~~sql
DECLARE
    l_payment_method VARCHAR2(20) := 'CARD';
BEGIN
    CASE l_payment_method
        WHEN 'CASH' THEN
            DBMS_OUTPUT.PUT_LINE('Collect cash');
        WHEN 'CARD' THEN
            DBMS_OUTPUT.PUT_LINE('Process card payment');
        WHEN 'BANK' THEN
            DBMS_OUTPUT.PUT_LINE('Verify bank transfer');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Unsupported payment method');
    END CASE;
END;
/
~~~

Simple CASE is suitable when multiple branches check the same variable or expression against specific values.

### 6.1. Simple CASE and NULL

Simple CASE uses equality comparison between the selector and WHEN values. NULL does not equal NULL in standard equality comparisons, so:

~~~sql
DECLARE
    l_status VARCHAR2(20) := NULL;
BEGIN
    CASE l_status
        WHEN 'OPEN' THEN
            DBMS_OUTPUT.PUT_LINE('Open');
        WHEN NULL THEN
            DBMS_OUTPUT.PUT_LINE('Missing');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Other');
    END CASE;
END;
/
~~~

The WHEN NULL branch is not selected just because the selector is NULL. Execution enters ELSE if present.

If you need to handle NULL, use a searched CASE:

~~~sql
CASE
    WHEN l_status IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Missing');
    WHEN l_status = 'OPEN' THEN
        DBMS_OUTPUT.PUT_LINE('Open');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Other');
END CASE;
~~~

## 7. Searched CASE Statement

Searched CASE has no shared selector. Each WHEN contains a Boolean condition:

~~~sql
CASE
    WHEN condition_1 THEN
        statements_1;
    WHEN condition_2 THEN
        statements_2;
    WHEN condition_3 THEN
        statements_3;
    ELSE
        default_statements;
END CASE;
~~~

Conditions are checked from top to bottom. The first branch whose condition is TRUE is executed. FALSE or NULL conditions do not select that branch.

Order classification example:

~~~sql
DECLARE
    l_total NUMBER := 2500;
    l_customer_type VARCHAR2(20) := 'VIP';
BEGIN
    CASE
        WHEN l_total IS NULL THEN
            DBMS_OUTPUT.PUT_LINE('Amount is missing');
        WHEN l_total < 0 THEN
            DBMS_OUTPUT.PUT_LINE('Invalid amount');
        WHEN l_customer_type = 'VIP' AND l_total >= 2000 THEN
            DBMS_OUTPUT.PUT_LINE('VIP high-value order');
        WHEN l_total >= 2000 THEN
            DBMS_OUTPUT.PUT_LINE('High-value order');
        WHEN l_total >= 500 THEN
            DBMS_OUTPUT.PUT_LINE('Standard order');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Small order');
    END CASE;
END;
/
~~~

The NULL and negative-value checks are placed before value-tier classification branches. Reversing the order could cause an abnormal value to be misclassified.

### 7.1. CASE Statements Do Not Fall Through Multiple Branches

Once a WHEN is selected, the CASE statement executes the corresponding block of statements and exits CASE. It does not continue running subsequent WHEN clauses like fall-through switch constructs in some other languages.

If multiple actions must run when a condition is met, place all actions in the same THEN block or call a procedure.

### 7.2. ELSE in a CASE Statement

ELSE is syntactically optional. However, if ELSE is omitted and no WHEN evaluates to TRUE, PL/SQL raises the predefined exception CASE_NOT_FOUND.

Example:

~~~sql
DECLARE
    l_code VARCHAR2(10) := 'X';
BEGIN
    CASE l_code
        WHEN 'A' THEN
            DBMS_OUTPUT.PUT_LINE('Alpha');
        WHEN 'B' THEN
            DBMS_OUTPUT.PUT_LINE('Beta');
    END CASE;
END;
/
~~~

With L_CODE equal to X, no branch matches, so CASE_NOT_FOUND is raised.

If all unmatched cases have a valid default meaning, add ELSE. If an unmatched case indicates a programming or business error, you can intentionally omit ELSE and handle the exception explicitly in the EXCEPTION block.

## 8. CASE Expression

A CASE expression produces a value. It can be used in PL/SQL assignments, SELECT, WHERE, ORDER BY, UPDATE, or INSERT.

Searched CASE expression syntax:

~~~sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
~~~

Example:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    l_grade :=
        CASE
            WHEN l_score >= 90 THEN 'A'
            WHEN l_score >= 80 THEN 'B'
            WHEN l_score >= 70 THEN 'C'
            ELSE 'F'
        END;

    DBMS_OUTPUT.PUT_LINE('Grade = ' || l_grade);
END;
/
~~~

A CASE expression returns a single value. It cannot contain multiple PL/SQL statements inside THEN like a CASE statement.

### 8.1. Simple CASE Expression

~~~sql
SELECT order_id,
       CASE status
           WHEN 'NEW' THEN 'Waiting'
           WHEN 'PAID' THEN 'Ready'
           WHEN 'CANCELLED' THEN 'Closed'
           ELSE 'Other'
       END AS status_label
FROM orders;
~~~

The selector STATUS is compared with each WHEN value; the result is a label for each row.

### 8.2. Searched CASE Expression

~~~sql
SELECT employee_id,
       salary,
       CASE
           WHEN salary IS NULL THEN 'MISSING'
           WHEN salary >= 10000 THEN 'HIGH'
           WHEN salary >= 5000 THEN 'MEDIUM'
           ELSE 'LOW'
       END AS salary_band
FROM employees;
~~~

Searched CASE is suitable when each branch has a different condition or requires explicit NULL handling.

### 8.3. CASE Expression in UPDATE

~~~sql
UPDATE orders
SET shipping_fee =
    CASE
        WHEN total_amount >= 1000 THEN 0
        WHEN customer_type = 'VIP' THEN 10
        ELSE 25
    END
WHERE order_status = 'CONFIRMED';
~~~

Each row gets its SHIPPING_FEE calculated according to the corresponding condition. This is a set-based SQL statement; there is no need to write a PL/SQL loop to update rows one by one.

### 8.4. CASE Expression in ORDER BY

~~~sql
SELECT order_id, status, created_at
FROM orders
ORDER BY
    CASE status
        WHEN 'URGENT' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'PAID' THEN 3
        ELSE 4
    END,
    created_at;
~~~

CASE generates a numeric sort key to sort in a custom business order.

### 8.5. CASE Expression in Conditional Aggregation

~~~sql
SELECT customer_id,
       SUM(
           CASE
               WHEN status = 'PAID' THEN total_amount
               ELSE 0
           END
       ) AS paid_amount,
       SUM(
           CASE
               WHEN status = 'CANCELLED' THEN total_amount
               ELSE 0
           END
       ) AS cancelled_amount
FROM orders
GROUP BY customer_id;
~~~

CASE allows aggregating different conditional subsets within the same GROUP BY. With ELSE 0, rows that do not satisfy the condition contribute 0 to the sum.

If ELSE is omitted, an unmatched CASE expression returns NULL. SUM ignores NULL, so omitting ELSE is sometimes intentional. Choose ELSE based on the desired semantics.

## 9. Differences Between CASE Statement and CASE Expression

| Criterion | CASE Statement | CASE Expression |
|---|---|---|
| Purpose | Selects a PL/SQL statement block | Returns a single value |
| Used in | PL/SQL blocks | PL/SQL and SQL expressions |
| THEN contains | One or more statements | One result expression |
| Termination | END CASE; | END |
| No matching branch and no ELSE | Raises CASE_NOT_FOUND in PL/SQL CASE statement | Returns NULL |
| Example | CASE status WHEN ... THEN DBMS_OUTPUT... | CASE WHEN score >= ... THEN 'A' END |

Statement example:

~~~sql
CASE l_status
    WHEN 'OPEN' THEN
        UPDATE orders SET status = 'PROCESSING'
        WHERE order_id = l_order_id;
    WHEN 'CLOSED' THEN
        DBMS_OUTPUT.PUT_LINE('Already closed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Other status');
END CASE;
~~~

Expression example:

~~~sql
l_label :=
    CASE l_status
        WHEN 'OPEN' THEN 'In progress'
        WHEN 'CLOSED' THEN 'Finished'
        ELSE 'Other'
    END;
~~~

Choose a statement when you need to execute different statements. Choose an expression when you need to produce a value to assign, filter, compute, or display.

## 10. IF, CASE Statement, and CASE Expression: Which Construct to Choose?

| Situation | Suggested Choice | Reason |
|---|---|---|
| Single true/false condition | IF | Short and direct |
| Multiple independent conditions or value ranges | IF/ELSIF or searched CASE | Conditions can differ |
| One variable with multiple specific values | Simple CASE | Branches compare the same selector |
| Multiple conditions needing priority | Searched CASE or IF/ELSIF | Branch order is explicit |
| Assigning a value conditionally | CASE expression | Usable directly inside expressions |
| Executing multiple statements per branch | IF or CASE statement | Each branch holds a statement block |
| Classifying rows in SELECT/UPDATE | SQL CASE expression | Processes data sets in SQL |

There is no rule that CASE is always faster than IF or vice versa. Choose the construct that makes business logic clear, avoids duplicate conditions, and is easy to test. For SQL queries, a CASE expression often processes many rows in a single statement.

## 11. Combining Conditions with DML and SELECT INTO

IF/CASE often validates data before DML is executed.

### 11.1. Checking Balance Before Withdrawal

~~~sql
DECLARE
    l_balance accounts.balance%TYPE;
    l_amount NUMBER := 100;
BEGIN
    SELECT balance
    INTO l_balance
    FROM accounts
    WHERE account_id = 10
    FOR UPDATE;

    IF l_amount IS NULL OR l_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Invalid withdrawal amount');
    ELSIF l_balance IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'Account balance is missing');
    ELSIF l_balance < l_amount THEN
        RAISE_APPLICATION_ERROR(-20003, 'Insufficient balance');
    ELSE
        UPDATE accounts
        SET balance = balance - l_amount
        WHERE account_id = 10;
    END IF;

    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ROLLBACK;
        RAISE_APPLICATION_ERROR(-20004, 'Account does not exist');
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

SELECT FOR UPDATE locks the account row during checking and updating, preventing two concurrent transactions from reading the stale balance and overdrawing. This illustrative example must be adapted to the currency rules, auditing, and transaction boundaries of a real system.

### 11.2. Using a CASE Expression to Update Multiple Tiers

~~~sql
UPDATE employees
SET bonus_rate =
    CASE
        WHEN performance_score IS NULL THEN 0
        WHEN performance_score >= 90 THEN 0.20
        WHEN performance_score >= 80 THEN 0.15
        WHEN performance_score >= 70 THEN 0.10
        ELSE 0
    END;
~~~

A single UPDATE statement can apply classification across all rows. The CASE expression is evaluated for each row based on that row's values.

### 11.3. Fetching a Flag with SELECT and Using IF

~~~sql
DECLARE
    l_open_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_open_count
    FROM orders
    WHERE customer_id = 10
      AND status = 'OPEN';

    IF l_open_count > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Customer has open orders');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No open orders');
    END IF;
END;
/
~~~

COUNT(*) always returns one row, with a value of 0 if no rows match. For SELECT INTO queries that can return 0 or multiple rows, understand and handle NO_DATA_FOUND/TOO_MANY_ROWS.

## 12. Variable Scope and Statement Blocks Within Branches

IF and CASE statements do not create an independent PL/SQL scope for each THEN block. Variables declared in the enclosing block's DECLARE section can be used inside all branches.

~~~sql
DECLARE
    l_message VARCHAR2(100);
    l_status VARCHAR2(20) := 'PAID';
BEGIN
    IF l_status = 'PAID' THEN
        l_message := 'Payment complete';
    ELSE
        l_message := 'Payment pending';
    END IF;

    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

If you need separate local variables, you can create a nested block with DECLARE/BEGIN/END inside a branch:

~~~sql
BEGIN
    IF condition THEN
        DECLARE
            l_local_value NUMBER := 10;
        BEGIN
            DBMS_OUTPUT.PUT_LINE(l_local_value);
        END;
    END IF;
END;
/
~~~

A nested block has its own scope. L_LOCAL_VALUE cannot be referenced outside that nested block.

## 13. Common Mistakes When Writing Conditional Branches

| Mistake | Consequence | Fix |
|---|---|---|
| Writing ELSEIF instead of ELSIF | Syntax error | Use ELSIF |
| Missing THEN | Syntax error | Every IF/ELSIF/WHEN requires THEN in the right place |
| Missing END IF | Unclosed IF block | Check nested structures |
| Using equals with NULL | Condition is never TRUE | Use IS NULL |
| Assuming ELSE only runs on FALSE | May misclassify NULL | Check NULL separately |
| Placing lower threshold before higher threshold | Earlier branch shadows later branches | Order conditions by priority |
| Using simple CASE for range comparisons | Incompatible syntax | Use searched CASE or IF/ELSIF |
| Using WHEN NULL in simple CASE to catch NULL | Does not match via equality | Use searched CASE with IS NULL |
| Forgetting ELSE in a CASE statement | CASE_NOT_FOUND when no branch is TRUE | Add ELSE or handle the exception intentionally |
| Confusing CASE statement with expression | Using multiple statements where only one value is expected | Choose the right CASE form |
| CASE expression returning incompatible datatypes | Data type error or unintended implicit conversion | Use a consistent result datatype |
| Repeating the same condition across branches | Hard to maintain, overlapping branches | Consolidate conditions or extract a function |
| Too many nested IF levels | Flow hard to read and test | Use searched CASE/ELSIF or extract a procedure |
| Using IF to update row by row instead of set-based SQL | Excessive context switches and complex code | Consider a CASE expression in UPDATE |

## 14. Practice Exercises

Run these exercises in a lab schema. Enable DBMS_OUTPUT in your SQL tool to view messages.

### Exercise 1 — Basic IF

Declare L_SCORE as 75. Write an IF checking for scores of 50 or above and print Passed. Change the score to 30 and NULL to observe branching.

### Exercise 2 — IF/ELSE

Declare L_QUANTITY as 0. Write an IF/ELSE to print In stock or No stock. Then set it to NULL and explain why ELSE executes.

### Exercise 3 — ELSIF Grading

Use thresholds 90, 80, 70, and 60 to assign grades A/B/C/D/F. Test scores 95, 80, 69, and NULL. Put the NULL condition in the first branch.

### Exercise 4 — Branch Order

Write a buggy version with L_SCORE >= 60 before L_SCORE >= 90. Run with score 95, explain which branch is chosen, and fix the order.

### Exercise 5 — Simple CASE

Declare L_STATUS sequentially as NEW, PAID, CANCELLED, and an unknown value. Use a simple CASE statement to print messages. Remove ELSE and observe CASE_NOT_FOUND.

### Exercise 6 — NULL in Simple CASE

Set L_STATUS := NULL and test WHEN NULL. Then switch to a searched CASE with WHEN L_STATUS IS NULL. Compare the results.

### Exercise 7 — Searched CASE

Write a CASE statement classifying orders by TOTAL_AMOUNT, CUSTOMER_TYPE, and status. Ensure NULL and negative numbers are handled before normal thresholds.

### Exercise 8 — CASE Expression

Use a CASE expression to assign HIGH/MEDIUM/LOW labels to a PL/SQL variable. Then move CASE into a SELECT to classify multiple employees.

### Exercise 9 — CASE in UPDATE

Create a lab table with SCORE and GRADE columns. Use a single UPDATE statement with a CASE expression to update GRADE for all rows.

### Exercise 10 — Conditional Aggregation

Use SUM(CASE WHEN ...) to calculate PAID and CANCELLED order totals per CUSTOMER_ID. Test both ELSE 0 and omitting ELSE to understand how SUM handles NULL.

### Exercise 11 — Balance Check

Use SELECT FOR UPDATE and IF/ELSIF to validate NULL, non-positive, over-balance, and valid withdrawal amounts. Rollback the data after testing.

### Exercise 12 — Nested IF

Write a program that checks whether a user is logged in, and only then checks the ADMIN/USER role. Try replacing it with a searched CASE and compare readability.

## 15. Checklist When Writing Conditions

- [ ] Choose IF for a few statement branches or CASE for structured multi-way choices.
- [ ] Spell ELSIF correctly and close the entire construct with one END IF.
- [ ] Put higher-priority or narrower-range conditions first.
- [ ] Check for NULL using IS NULL/IS NOT NULL.
- [ ] Distinguish FALSE from NULL if business logic requires it.
- [ ] Choose simple CASE when comparing one selector against specific values.
- [ ] Choose searched CASE when branches have different Boolean conditions.
- [ ] Distinguish CASE statements ending with END CASE from CASE expressions ending with END.
- [ ] Add ELSE when all unmatched cases need handling.
- [ ] Ensure all CASE expression branches return compatible datatypes.
- [ ] Use SQL CASE expressions for multi-row classification/updates when possible.
- [ ] Handle SELECT INTO and DML exceptions in accordance with transaction boundaries.
- [ ] Test boundary values, NULL, abnormal values, and the no-branch-matched case.

## 16. Core Takeaways

- IF executes the THEN block only when the condition is TRUE; FALSE and NULL do not select that branch.
- ELSIF adds a conditional branch to the same IF construct; it is written as one word and ends with a single END IF.
- Oracle evaluates conditions top-down; the first TRUE branch is selected, so condition order can change the outcome.
- ELSE handles the case where no prior branch was TRUE, including NULL conditions.
- PL/SQL BOOLEAN has three states: TRUE, FALSE, and NULL.
- Simple CASE compares a selector against WHEN values; WHEN NULL is not the way to catch a NULL selector.
- Searched CASE checks WHEN conditions in order and suits ranges, multiple predicates, or NULL handling.
- A CASE statement executes statements and ends with END CASE; a CASE expression returns a value and ends with END.
- A CASE statement without ELSE and no TRUE branch raises CASE_NOT_FOUND; a CASE expression without ELSE returns NULL if no branch matches.
- Use CASE expressions in SELECT, UPDATE, ORDER BY, and conditional aggregation to process data sets in SQL.
- Writing clear branches, handling NULL intentionally, testing boundaries, and avoiding deep nesting make PL/SQL easier to read and maintain.

### Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Conditional selection statements, IF statement, CASE statement, and CASE expression.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — BOOLEAN, expressions, nested blocks, and exception handling.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CASE expressions in SELECT, UPDATE, ORDER BY, and SQL conditions.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — CASE_NOT_FOUND and related syntax/data-type errors.

Syntax and support for using the BOOLEAN type in SQL depend on the Oracle version. When implementing, consult the documentation for your exact release and test TRUE, FALSE, NULL, boundary thresholds, and the ELSE branch in a lab schema.
