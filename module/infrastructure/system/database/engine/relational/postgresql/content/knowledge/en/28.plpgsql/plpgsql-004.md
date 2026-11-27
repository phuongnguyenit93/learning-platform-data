# IF, CASE, and Conditional Structures in PL/pgSQL

An order-processing program cannot simply execute `INSERT`, `UPDATE`, or `SELECT` statements along one fixed path. The application must decide: can an unpaid invoice be issued, must a negative amount be rejected, how should an unauthorized user be notified, and should an already-processed record be skipped when a request is retried?

In PostgreSQL, **PL/pgSQL** provides flow-control structures to make decisions directly inside functions, procedures, triggers, or `DO` blocks. The two foundational constructs are:

- **`IF ... THEN ... ELSIF ... ELSE ... END IF`:** selects branches based on Boolean expressions, well suited for checking conditions, value ranges, permissions, `NULL` data, and business invariants.
- **`CASE ... WHEN ... THEN ... ELSE ... END CASE`:** selects one of several branches. It comes in **simple CASE** (comparing one expression against a list of values) and **searched CASE** (evaluating multiple Boolean conditions).

An easy point of confusion is that PostgreSQL also has an **SQL `CASE` expression**, commonly used inside `SELECT`, `UPDATE`, `ORDER BY`, and `INSERT`. That expression returns a value and ends with `END`, whereas the **PL/pgSQL `CASE` statement controls execution flow and ends with `END CASE;`**.

```text
                        Incoming Request
                                |
                                v
                      Validate Input Data
                            IF / ELSIF
                                |
             +------------------+------------------+
             |                  |                  |
          Missing            Invalid             Valid
             |                  |                  |
             v                  v                  v
       RETURN / error     RAISE EXCEPTION     Check Status
                                                   |
                                                   v
                                              CASE status
                                                   |
                           +-----------------------+--------------------+
                           |                       |                    |
                         draft                   issued                paid
                           |                       |                    |
                         issue               keep as-is or         reject invalid
                                               mark paid            transition
```

This lesson belongs to the **PL/pgSQL** chapter of the *Database Engine Relational PostgreSQL* module. It covers everything from basic syntax to real-world business logic, including self-contained SQL examples, `NULL` handling, row lookup with `FOUND`, state checks under concurrency, and exercises with answers.

**Objectives:**

1. Write valid `IF`, `ELSIF`, `ELSE`, `END IF` structures.
2. Distinguish simple `CASE` from searched `CASE` in PL/pgSQL.
3. Distinguish PL/pgSQL `CASE` **statements** from SQL `CASE` **expressions**.
4. Understand SQL's three-valued logic: `TRUE`, `FALSE`, and `NULL`.
5. Avoid bugs from `= NULL`, `NOT IN` containing NULL, missing `ELSE` branches, and condition ordering.
6. Use `SELECT ... INTO`, `FOUND`, `RAISE EXCEPTION`, and `RETURN` to build functions with clear control flow.
7. Design invoice state transitions guarded with `SELECT ... FOR UPDATE`.
8. Know when to write set-based logic with SQL `CASE` instead of looping row-by-row in PL/pgSQL.

> **Practice Scope:** The data-setup commands use the `plpgsql_cond_lab` schema in a test database. Never run sample invoice updates on a real production system. `RAISE EXCEPTION` calls demonstrating errors are placed in separate sections or written as comments so learners can test them intentionally.

---

## 1. How PL/pgSQL Differs from SQL in Control Flow

### 1.1. SQL Describes Set-Based Data Operations

SQL typically expresses a computation across many rows:

```sql
SELECT
    amount,
    CASE
        WHEN amount >= 1000 THEN 'large'
        WHEN amount >= 100 THEN 'medium'
        ELSE 'small'
    END AS amount_group
FROM invoices;
```

`CASE` inside this `SELECT` is an **expression** returning a value per row. It does not control executing a sequence of `UPDATE`, `INSERT`, or `RAISE` statements inside a stored function.

### 1.2. PL/pgSQL Controls Executable Statements

```sql
CREATE FUNCTION example_amount_group(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'unknown';
    ELSIF p_amount >= 1000 THEN
        RETURN 'large';
    ELSIF p_amount >= 100 THEN
        RETURN 'medium';
    ELSE
        RETURN 'small';
    END IF;
END;
$function$;
```

In this example:

- `IF` decides which statement executes.
- `RETURN` exits the function and returns a value.
- Branches after a branch that already returned are never executed.
- More complex business statements can sit inside each branch.

### 1.3. PL/pgSQL Does Not Replace SQL

In general:

- Use **SQL** for bulk set-based operations on records.
- Use **PL/pgSQL** to orchestrate ordering, conditions, appropriate retry policies, validation, and multi-statement operations.

A very long PL/pgSQL function is not automatically faster than a single SQL `UPDATE ... CASE`. Often set-based SQL logic is simpler, incurs fewer round-trips, and performs better.

---

## 2. Basic PL/pgSQL Block

### 2.1. DECLARE, BEGIN, END Structure

```sql
DO $block$
DECLARE
    v_amount numeric := 125.50;
    v_label text;
BEGIN
    v_label := 'unclassified';

    IF v_amount >= 100 THEN
        v_label := 'medium or larger';
    END IF;

    RAISE NOTICE 'amount=%, label=%', v_amount, v_label;
END;
$block$;
```

`DO` runs an anonymous code block, which is useful for experiments without saving a function. `RAISE NOTICE` sends a message to the client rather than returning a result set like `SELECT`.

### 2.2. Syntactic Components

| Component | Meaning |
|---|---|
| `DO $block$ ... $block$;` | Executes an anonymous PL/pgSQL code block |
| `DECLARE` | Declares local variables if needed |
| `BEGIN` | Begins the statement section of a PL/pgSQL block |
| `END;` | Ends a PL/pgSQL block |
| `:=` | Assigns a value to a variable |
| `IF ... END IF;` | Controls conditional branching |
| `RAISE NOTICE` | Emits diagnostic messages |
| `RETURN` | Returns a result and exits the function |

### 2.3. PL/pgSQL BEGIN Is Not BEGIN TRANSACTION

Two constructs share the same keyword for different purposes:

```sql
DO $block$
BEGIN
    RAISE NOTICE 'This is a PL/pgSQL block';
END;
$block$;
```

`BEGIN ... END` in PL/pgSQL merely **groups statements** into a block. It **does not start a new transaction** like SQL's `BEGIN; ... COMMIT;`.

An ordinary PL/pgSQL function runs inside its caller's transaction. Never put arbitrary `COMMIT` statements in a normal function expecting each branch to commit independently.

### 2.4. Semicolons

Example:

```sql
IF condition THEN
    statement_1;
    statement_2;
END IF;
```

- Child statements end with `;`.
- `END IF;` also ends with `;`.
- Never write `THEN;` as a standalone statement.
- `ELSIF` is part of the same `IF` structure, not a separate `IF` requiring its own `END IF`.

---

## 3. Simple IF: A Single Conditional Branch

### 3.1. Syntax

```text
IF boolean_expression THEN
    statements;
END IF;
```

If the condition evaluates to `TRUE`, PostgreSQL executes the statements in the branch. If `FALSE` or `NULL`, the branch is skipped.

### 3.2. Example: Checking for a Negative Amount

```sql
DO $block$
DECLARE
    v_amount numeric := -5;
BEGIN
    IF v_amount < 0 THEN
        RAISE NOTICE 'Invalid amount: %', v_amount;
    END IF;

    RAISE NOTICE 'Validation block finished';
END;
$block$;
```

`RAISE NOTICE` does not halt the block; the second message is still emitted. When an invalid operation must stop completely, use `RAISE EXCEPTION` or `RETURN` per the function contract.

### 3.3. IF Does Not Require ELSE

When you only need to act if true:

```sql
IF v_amount = 0 THEN
    RAISE NOTICE 'Zero amount';
END IF;
```

There is no need to write an empty `ELSE`.

### 3.4. Conditions Must Be Boolean

Valid conditions include:

```sql
IF v_amount > 0 THEN ...
IF v_status = 'paid' THEN ...
IF v_customer_id IS NULL THEN ...
IF v_is_active THEN ...
IF EXISTS (SELECT 1 FROM ...) THEN ...
```

In PL/pgSQL, you cannot use integers as Booleans C-style:

```sql
-- Not valid if v_count is INTEGER:
-- IF v_count THEN ...

-- Correct:
-- IF v_count > 0 THEN ...
```

---

## 4. IF ... ELSE: Two Explicit Paths

### 4.1. Syntax

```text
IF condition THEN
    statements_when_true;
ELSE
    statements_when_not_true;
END IF;
```

In PL/pgSQL, "not true" covers both `FALSE` and `NULL`.

### 4.2. Practicing with a Boolean Variable

```sql
DO $block$
DECLARE
    v_verified boolean := true;
BEGIN
    IF v_verified THEN
        RAISE NOTICE 'Account verified';
    ELSE
        RAISE NOTICE 'Account not confirmed';
    END IF;
END;
$block$;
```

### 4.3. The NULL Case

```sql
DO $block$
DECLARE
    v_verified boolean := NULL;
BEGIN
    IF v_verified THEN
        RAISE NOTICE 'Verified';
    ELSE
        RAISE NOTICE 'Not verified or unknown';
    END IF;
END;
$block$;
```

Because `v_verified` is `NULL`, the `THEN` branch **is not taken**; the `ELSE` branch runs.

Do not assume `NULL` equals `FALSE` in every SQL expression. Only in `IF` branch selection does PL/pgSQL skip the `THEN` branch whenever the condition is anything other than `TRUE`.

### 4.4. Distinguishing FALSE from UNKNOWN When Needed

If business logic has three states:

```sql
DO $block$
DECLARE
    v_verified boolean := NULL;
BEGIN
    IF v_verified IS TRUE THEN
        RAISE NOTICE 'Verified';
    ELSIF v_verified IS FALSE THEN
        RAISE NOTICE 'Explicitly unverified';
    ELSE
        RAISE NOTICE 'Verification status unknown';
    END IF;
END;
$block$;
```

This is clearer when access control or approval workflows must distinguish "explicitly rejected" from "not yet provided."

---

## 5. IF ... ELSIF ... ELSE: Multiple Conditions

### 5.1. Syntax

```text
IF condition_1 THEN
    statements_1;
ELSIF condition_2 THEN
    statements_2;
ELSIF condition_3 THEN
    statements_3;
ELSE
    statements_default;
END IF;
```

PostgreSQL evaluates branches **from top to bottom**. **The first branch whose condition evaluates to TRUE executes**; subsequent branches are skipped for that `IF` pass.

### 5.2. Example: Classifying Amounts

```sql
CREATE FUNCTION plpgsql_cond_lab.classify_amount(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount < 0 THEN
        RAISE EXCEPTION 'Amount cannot be negative: %', p_amount
            USING ERRCODE = '22023';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSIF p_amount < 100 THEN
        RETURN 'SMALL';
    ELSIF p_amount < 1000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LARGE';
    END IF;
END;
$function$;
```

**Watch the order:** `IS NULL` and negative checks must precede valid amount buckets. Once we know `p_amount >= 100` and `< 1000`, there is no need to repeat the lower bound in later branches.

### 5.3. Branch Order Can Break Logic

Incorrect:

```sql
IF p_amount < 1000 THEN
    RETURN 'BELOW_1000';
ELSIF p_amount < 100 THEN
    RETURN 'BELOW_100';
END IF;
```

Since every number below 100 is also below 1000, the second branch is **never reached** for non-NULL values.

Correct when distinct buckets are required:

```sql
IF p_amount < 100 THEN
    RETURN 'BELOW_100';
ELSIF p_amount < 1000 THEN
    RETURN 'FROM_100_TO_999';
ELSE
    RETURN 'AT_LEAST_1000';
END IF;
```

### 5.4. ELSIF Is Not an Implicit IF Inside ELSE

`ELSIF` is the standard spelling. PostgreSQL also accepts `ELSEIF` in PL/pgSQL. For consistency and readability, this guide uses `ELSIF`.

If you actually nest a new `IF` inside `ELSE`, you must close **both** structures:

```sql
IF first_condition THEN
    RAISE NOTICE 'first';
ELSE
    IF second_condition THEN
        RAISE NOTICE 'second';
    END IF;
END IF;
```

Structurally this differs from a single `ELSIF` chain, even when outcomes match in simple cases.

---

## 6. Boolean NULL and Three-Valued Logic

This is the foundation of correct conditional logic in PL/pgSQL.

### 6.1. SQL Has Three Boolean States

| Expression | Result |
|---|---|
| `5 > 3` | TRUE |
| `5 < 3` | FALSE |
| `NULL::integer > 3` | NULL |
| `NULL::integer = NULL::integer` | NULL |
| `NULL::integer IS NULL` | TRUE |
| `NULL::integer IS NOT NULL` | FALSE |

`NULL` represents **unknown/absent** data, not zero or an empty string.

### 6.2. IF NULL Does Not Take THEN

```sql
DO $block$
DECLARE
    v_result boolean;
BEGIN
    v_result := NULL::integer = 10;

    IF v_result THEN
        RAISE NOTICE 'TRUE';
    ELSE
        RAISE NOTICE 'FALSE or UNKNOWN';
    END IF;
END;
$block$;
```

The output message is `FALSE or UNKNOWN`.

### 6.3. Why Is = NULL Wrong?

```sql
-- Do not use this to check for missing data:
-- IF p_customer_id = NULL THEN ...

-- Correct:
-- IF p_customer_id IS NULL THEN ...
```

The `=` operator with a NULL operand yields UNKNOWN, so the condition never becomes TRUE.

### 6.4. IS TRUE, IS FALSE, IS NOT TRUE

| Value of x | `x IS TRUE` | `x IS FALSE` | `x IS NOT TRUE` |
|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE |
| FALSE | FALSE | TRUE | TRUE |
| NULL | FALSE | FALSE | TRUE |

When the rule is "allow only when explicitly confirmed TRUE," write:

```sql
IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;
```

This rejects both FALSE and NULL, matching a **fail-closed** policy.

### 6.5. IS DISTINCT FROM Handles NULL Cleanly

```sql
SELECT
    NULL::text IS DISTINCT FROM 'paid' AS different,
    NULL::text IS NOT DISTINCT FROM NULL::text AS same_null,
    'paid'::text IS DISTINCT FROM 'paid'::text AS same_text;
```

The results are `true`, `true`, and `false`, respectively.

When comparing nullable old and new values, `IS DISTINCT FROM` is usually clearer than `<>`:

```sql
IF NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE NOTICE 'Status has changed';
END IF;
```

This snippet belongs inside an **UPDATE trigger** that defines `NEW` and `OLD`. Do not paste it into a regular function without declaring those variables.

### 6.6. AND, OR, and NULL

Key truth-table rules:

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| TRUE | NULL | NULL | TRUE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |
| TRUE | FALSE | FALSE | TRUE |

`NOT NULL` also evaluates to `NULL`, not TRUE.

### 6.7. NOT IN Containing NULL

```sql
SELECT 7 NOT IN (1, 2, NULL) AS is_other;
```

The result is **NULL**, not TRUE. When a list contains NULL, `NOT IN` can cause an `IF` to skip its `THEN` branch even when the tested value matches none of the non-NULL elements.

When using a subquery to check non-existence, `NOT EXISTS` is usually semantically safer than `NOT IN` on nullable sets.

### 6.8. COALESCE Is Not Always Appropriate

```sql
IF COALESCE(p_approved, false) THEN
    ...
END IF;
```

This implements a policy of **treating NULL as FALSE**, which may be valid. However, if you need to tell "unverified" apart from "rejected," `COALESCE` discards that distinction. Decide the policy before choosing the operator.

---

## 7. Compound Conditions and Parentheses

### 7.1. Multiple Conditions

```sql
IF p_amount > 0
   AND p_status = 'issued'
   AND p_tenant_id IS NOT NULL THEN
    RAISE NOTICE 'Eligible for payment';
END IF;
```

### 7.2. Logical Operator Precedence

In SQL, `NOT`, `AND`, and `OR` follow PostgreSQL's precedence rules. Omitting parentheses can produce unintended logic.

Example:

```sql
IF p_is_admin
   OR p_is_owner AND p_is_active THEN
    ...
END IF;
```

Because `AND` binds tighter than `OR`, this means:

```sql
IF p_is_admin
   OR (p_is_owner AND p_is_active) THEN
    ...
END IF;
```

If the requirement is that **everyone must be active**, write:

```sql
IF (p_is_admin OR p_is_owner)
   AND p_is_active THEN
    ...
END IF;
```

The two rules are **not equivalent**. Use parentheses to make policy unambiguous.

### 7.3. Redundant Conditions

```sql
IF p_amount > 0 AND p_amount <> 0 THEN
    ...
END IF;
```

For numeric values, `p_amount > 0` already implies `p_amount <> 0`. Redundant conditions clutter code without improving correctness.

### 7.4. Never Rely on Short-Circuiting to Guard Dangerous Operations

Developers often assume the right side of `AND` or `OR` will never be evaluated if the left side decides the outcome. The SQL optimizer is free to rewrite expressions, and evaluation order is not a universal contract protecting error-prone expressions.

Risk:

```sql
-- Do not rely on AND ordering as a general safeguard:
-- WHERE denominator <> 0
--   AND numerator / denominator > 10
```

For division, a safer approach defines the result when the denominator is 0:

```sql
SELECT
    numerator / NULLIF(denominator, 0)
FROM ...
```

In PL/pgSQL, you can separate **validation into an earlier `IF` statement** before dividing:

```sql
IF p_denominator = 0 OR p_denominator IS NULL THEN
    RAISE EXCEPTION 'Invalid denominator'
        USING ERRCODE = '22023';
END IF;

v_ratio := p_numerator / p_denominator;
```

This assumes `v_ratio` and the parameters are declared. Splitting into two statements clearly separates validation from calculation.

---

## 8. Simple CASE Statement in PL/pgSQL

Simple `CASE` fits cases where one expression is matched against **discrete values**.

### 8.1. Syntax

```text
CASE test_expression
    WHEN value_1 [, value_2 ...] THEN
        statements_1;
    WHEN value_3 THEN
        statements_2;
    ELSE
        statements_default;
END CASE;
```

`test_expression` is evaluated once for the simple `CASE`; each `WHEN` compares it against the listed expressions using PostgreSQL equality rules.

### 8.2. Example: Branching by Status

```sql
DO $block$
DECLARE
    v_status text := 'issued';
BEGIN
    CASE v_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Document can be edited';
        WHEN 'issued' THEN
            RAISE NOTICE 'Document is ready for payment';
        WHEN 'paid' THEN
            RAISE NOTICE 'Document has been paid';
        ELSE
            RAISE NOTICE 'Unknown or unsupported status';
    END CASE;
END;
$block$;
```

Only the `issued` branch runs; all other branches are skipped.

### 8.3. Multiple Values in One WHEN

PL/pgSQL simple `CASE` supports comma-separated values in a single `WHEN`:

```sql
DO $block$
DECLARE
    v_status text := 'draft';
BEGIN
    CASE v_status
        WHEN 'draft', 'issued' THEN
            RAISE NOTICE 'Still in pre-payment workflow';
        WHEN 'paid' THEN
            RAISE NOTICE 'Payment complete';
        WHEN 'void' THEN
            RAISE NOTICE 'Document void';
        ELSE
            RAISE NOTICE 'Other status';
    END CASE;
END;
$block$;
```

Group values into one branch when they **truly share the same business handling**, not merely to save lines.

### 8.4. Simple CASE vs. Multi-Branch IF

When dispatching on a single `status` attribute:

```sql
CASE v_status
    WHEN 'draft' THEN ...
    WHEN 'issued' THEN ...
    WHEN 'paid' THEN ...
    ELSE ...
END CASE;
```

is usually cleaner than:

```sql
IF v_status = 'draft' THEN
    ...
ELSIF v_status = 'issued' THEN
    ...
ELSIF v_status = 'paid' THEN
    ...
ELSE
    ...
END IF;
```

However, simple `CASE` **cannot directly express ranges** like "amount from 100 to under 1000" via `WHEN 100..1000`. For ranges or compound predicates, use searched `CASE` or `IF`.

---

## 9. Searched CASE Statement in PL/pgSQL

Searched `CASE` evaluates **each `WHEN` as a Boolean condition**.

### 9.1. Syntax

```text
CASE
    WHEN boolean_expression_1 THEN
        statements_1;
    WHEN boolean_expression_2 THEN
        statements_2;
    ELSE
        statements_default;
END CASE;
```

### 9.2. Example: Amount Range Classification

```sql
DO $block$
DECLARE
    v_amount numeric := 750;
BEGIN
    CASE
        WHEN v_amount IS NULL THEN
            RAISE NOTICE 'Missing amount';
        WHEN v_amount < 0 THEN
            RAISE NOTICE 'Invalid negative amount';
        WHEN v_amount < 100 THEN
            RAISE NOTICE 'Small';
        WHEN v_amount < 1000 THEN
            RAISE NOTICE 'Medium';
        ELSE
            RAISE NOTICE 'Large';
    END CASE;
END;
$block$;
```

With `v_amount=750`, the `Medium` branch executes.

### 9.3. Similar to ELSIF, Not Identical

Both searched `CASE` and `IF`/`ELSIF` evaluate conditions top-down and execute the first `TRUE` branch. However, there is a crucial difference:

- `IF` **can omit `ELSE`** without throwing an error.
- PL/pgSQL `CASE` **without `ELSE` raises `CASE_NOT_FOUND`** if no branch matches.

If having no match is valid and intentional, write `ELSE NULL;` or an explicit handler.

### 9.4. Overlapping Conditions

```sql
CASE
    WHEN v_amount >= 100 THEN
        RAISE NOTICE 'At least 100';
    WHEN v_amount >= 1000 THEN
        RAISE NOTICE 'At least 1000';
    ELSE
        RAISE NOTICE 'Below 100';
END CASE;
```

With `v_amount=1500`, **At least 100** wins because it is tested first. Fix:

```sql
CASE
    WHEN v_amount >= 1000 THEN
        RAISE NOTICE 'At least 1000';
    WHEN v_amount >= 100 THEN
        RAISE NOTICE 'From 100 to below 1000';
    ELSE
        RAISE NOTICE 'Below 100';
END CASE;
```

---

## 10. CASE_NOT_FOUND and ELSE NULL

### 10.1. Simple CASE Without ELSE

Example intentionally raising an error:

```sql
-- Run only when you want to observe the error.
-- DO $block$
-- DECLARE
--     v_status text := 'unknown';
-- BEGIN
--     CASE v_status
--         WHEN 'draft' THEN
--             RAISE NOTICE 'Draft';
--         WHEN 'paid' THEN
--             RAISE NOTICE 'Paid';
--     END CASE;
-- END;
-- $block$;
```

Because `'unknown'` does not match and there is no `ELSE`, PostgreSQL raises `CASE_NOT_FOUND`. This acts as a **missing-state trap** that can be useful in workflows.

### 10.2. Searched CASE Behaves the Same

```sql
-- Also raises CASE_NOT_FOUND if amount=5:
-- CASE
--     WHEN v_amount > 100 THEN
--         ...
--     WHEN v_amount < 0 THEN
--         ...
-- END CASE;
```

### 10.3. ELSE NULL Explicitly Does Nothing

In PL/pgSQL, `NULL;` is a valid **no-op statement**:

```sql
DO $block$
DECLARE
    v_status text := 'unknown';
BEGIN
    CASE v_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Draft';
        WHEN 'paid' THEN
            RAISE NOTICE 'Paid';
        ELSE
            NULL;
    END CASE;

    RAISE NOTICE 'Continues safely';
END;
$block$;
```

The default branch does nothing and does not raise `CASE_NOT_FOUND`. Use this only when ignoring unhandled values is an **explicit policy**, not to mask invalid inputs.

### 10.4. Using ELSE to Reject Unknown States

```sql
CASE v_status
    WHEN 'draft' THEN
        RAISE NOTICE 'Editable';
    WHEN 'paid' THEN
        RAISE NOTICE 'Completed';
    ELSE
        RAISE EXCEPTION 'Unsupported status: %', v_status
            USING ERRCODE = '22023';
END CASE;
```

This is a strong choice when out-of-catalog values **must be rejected**.

### 10.5. Catching CASE_NOT_FOUND When Truly Needed

```sql
DO $block$
DECLARE
    v_status text := 'other';
BEGIN
    BEGIN
        CASE v_status
            WHEN 'draft' THEN
                RAISE NOTICE 'Draft';
            WHEN 'paid' THEN
                RAISE NOTICE 'Paid';
        END CASE;
    EXCEPTION
        WHEN case_not_found THEN
            RAISE NOTICE 'Unexpected status: %', v_status;
    END;
END;
$block$;
```

This demonstrates recognizing the exception, **not** a recommendation to use exceptions for routine branching. Using `ELSE` is clearer, easier to read, and avoids exception overhead.

---

## 11. SQL CASE: A Value-Returning Expression, Not a PL/pgSQL Statement

### 11.1. Two Forms of SQL CASE

**Simple SQL CASE expression:**

```sql
SELECT
    CASE 'issued'
        WHEN 'draft' THEN 'Editable'
        WHEN 'issued' THEN 'Ready'
        WHEN 'paid' THEN 'Completed'
        ELSE 'Unknown'
    END AS status_label;
```

**Searched SQL CASE expression:**

```sql
SELECT
    CASE
        WHEN 750 >= 1000 THEN 'Large'
        WHEN 750 >= 100 THEN 'Medium'
        ELSE 'Small'
    END AS amount_label;
```

Identifier: **`END`** closes an SQL CASE expression.

### 11.2. PL/pgSQL CASE Statement Ends with END CASE;

```sql
DO $block$
BEGIN
    CASE
        WHEN 750 >= 1000 THEN
            RAISE NOTICE 'Large';
        WHEN 750 >= 100 THEN
            RAISE NOTICE 'Medium';
        ELSE
            RAISE NOTICE 'Small';
    END CASE;
END;
$block$;
```

Identifier: **`END CASE;`** closes the control-flow statement.

### 11.3. SQL CASE Without ELSE Returns NULL

```sql
SELECT
    CASE
        WHEN 2 > 10 THEN 'Greater than 10'
    END AS result;
```

The result is SQL `NULL`. It **does not** raise `CASE_NOT_FOUND`.

Compared with a PL/pgSQL CASE statement lacking `ELSE`, this is a critical difference.

### 11.4. SQL CASE Inside SELECT

```sql
SELECT
    status,
    CASE status
        WHEN 'draft' THEN 'DRAFT'
        WHEN 'issued' THEN 'OPEN'
        WHEN 'paid' THEN 'SETTLED'
        ELSE 'INACTIVE'
    END AS display_group
FROM plpgsql_cond_lab.invoices;
```

The `CASE` expression computes a display value for **each row** in the `SELECT`.

### 11.5. SQL CASE Inside UPDATE

```sql
-- Example illustrating set-based label updates in a single SQL command.
-- UPDATE some_table
-- SET priority = CASE
--     WHEN amount >= 1000 THEN 'high'
--     WHEN amount >= 100  THEN 'medium'
--     ELSE 'low'
-- END;
```

No PL/pgSQL function or `FOR` loop over rows is needed just to update a column conditionally.

### 11.6. CASE Is an Expression and Cannot Contain RAISE

Fundamentally invalid:

```sql
-- SQL CASE is not a place for PL/pgSQL statements:
-- SELECT CASE WHEN amount < 0
--             THEN RAISE EXCEPTION 'invalid'
--        END;
```

In SQL `CASE`, every `THEN` expects a **value-producing expression**, not a PL/pgSQL control statement like `RAISE` or `RETURN`. To abort on error, use a PL/pgSQL `IF`/`CASE` statement or an appropriate SQL constraint.

### 11.7. Type Resolution Across Branches

A `CASE` expression must resolve to **a common compatible result type** across its branches:

```sql
SELECT CASE
           WHEN true THEN 10
           ELSE 20
       END AS integer_result;
```

Do not assume you can mix arbitrary types such as JSON objects, timestamps, booleans, text, and numeric across branches without valid type-coercion rules.

---

## 12. Naming Variables to Avoid Colliding with SQL Columns

### 12.1. Helpful Naming Convention

| Symbol | Purpose |
|---|---|
| `p_amount` | Function input parameter |
| `v_status` | Local variable |
| `v_invoice` | Row/record selected from a table |
| `t` or `i` | Table alias in SQL |
| `NEW` / `OLD` | Trigger row variables |

### 12.2. Ambiguous Names

If a table has a column `status` and a local variable is also named `status`:

```sql
SELECT status INTO status FROM invoices;
```

the code can trigger ambiguous reference errors or misbehave depending on variable-conflict settings. Instead write:

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

### 12.3. Variable Assignment with :=

```sql
v_label := 'paid';
v_count := v_count + 1;
```

Do not confuse `:=` in PL/pgSQL with `SET status = 'paid'` in SQL `UPDATE`.

### 12.4. PL/pgSQL SELECT ... INTO

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

In PL/pgSQL, `SELECT ... INTO variable` assigns query results into variables. It is not SQL's `SELECT INTO new_table` table-creation command.

---

## 13. Independent Lab: Invoices and State Transitions

We create a small model to demonstrate **`IF` for validation** and **`CASE` for state-based dispatch**.

### 13.1. Initialize Schema

```sql
CREATE SCHEMA plpgsql_cond_lab;
```

Run in a test database without an existing schema of the same name. Never run `DROP SCHEMA ... CASCADE` on a shared database just to reset exercises.

### 13.2. Create the Invoices Table

```sql
CREATE TABLE plpgsql_cond_lab.invoices (
    invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL
        CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    issued_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status <> 'paid' OR paid_at IS NOT NULL)
);
```

Distinguish the constraints:

- `NOT NULL` and `CHECK` protect data in the database even if a session bypasses business functions.
- State-transition functions implement workflow rules and user-friendly errors.
- `CHECK (status <> 'paid' OR paid_at IS NOT NULL)` prevents a paid row from lacking `paid_at`, but **does not** express valid transitions between old and new states over time.

### 13.3. Load Sample Data

```sql
INSERT INTO plpgsql_cond_lab.invoices
    (tenant_id, amount, status, issued_at, paid_at)
VALUES
    (1, 120.00, 'draft',  NULL, NULL),
    (1, 200.00, 'issued', TIMESTAMPTZ '2026-11-01 08:00+00', NULL),
    (1,  90.00, 'paid',
        TIMESTAMPTZ '2026-11-01 08:00+00',
        TIMESTAMPTZ '2026-11-02 10:00+00'),
    (2,  50.00, 'void',   NULL, NULL),
    (2,   0.00, 'issued', TIMESTAMPTZ '2026-11-03 09:00+00', NULL);
```

On a fresh schema with one INSERT, `invoice_id` values run from 1 to 5. Examples referencing IDs 1, 2, 3, 4, 5 assume this lab seed was inserted once.

### 13.4. Inspect Source State

```sql
SELECT
    invoice_id,
    tenant_id,
    amount,
    status,
    issued_at,
    paid_at
FROM plpgsql_cond_lab.invoices
ORDER BY invoice_id;
```

### 13.5. Simple Business Logic

```text
draft  --issue--> issued --pay--> paid
  |                 |
  +-----void--------+

paid: terminal state in this example
void: terminal state in this example
```

This is a minimal state machine; production invoices can include `partially_paid`, `overdue`, `refunded`, `disputed`, or partial payments.

---

## 14. Function Classifying Amounts with IF

### 14.1. Full Definition

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.classify_amount(p_amount numeric)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount < 0 THEN
        RAISE EXCEPTION 'Negative amount: %', p_amount
            USING ERRCODE = '22023';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSIF p_amount < 100 THEN
        RETURN 'SMALL';
    ELSIF p_amount < 1000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LARGE';
    END IF;
END;
$function$;
```

This is the schema-qualified version for the lab, replacing the conceptual snippet in Section 5. It checks NULL and negative values first, then narrows down ranges sequentially.

### 14.2. Testing Valid Inputs

```sql
SELECT
    p.amount,
    plpgsql_cond_lab.classify_amount(p.amount) AS category
FROM (
    VALUES
        (NULL::numeric),
        (0::numeric),
        (25::numeric),
        (100::numeric),
        (999.99::numeric),
        (1000::numeric)
) AS p(amount);
```

The results in order are `UNKNOWN`, `ZERO`, `SMALL`, `MEDIUM`, `MEDIUM`, `LARGE`.

### 14.3. Intentionally Testing a Negative Value Error

```sql
-- Run separately to observe the exception:
-- SELECT plpgsql_cond_lab.classify_amount(-5);
```

The function uses `RAISE EXCEPTION` with SQLSTATE `22023` (*invalid_parameter_value*). The call fails instead of returning `SMALL`.

### 14.4. Why Put RETURN in Every Branch?

`RETURN` immediately exits the function in the chosen branch. If a scalar-returning function reaches the end along any path without executing `RETURN` or `RAISE`, PostgreSQL throws a runtime error.

An alternative is assigning `v_category` in each branch and placing a single `RETURN v_category;` at the end. Choose whichever style keeps complexity low and readability high.

---

## 15. Function Using Simple CASE for Status Labels

### 15.1. Creating Display Labels

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.invoice_status_label(p_status text)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    CASE p_status
        WHEN 'draft' THEN
            RETURN 'Draft';
        WHEN 'issued' THEN
            RETURN 'Issued';
        WHEN 'paid' THEN
            RETURN 'Paid';
        WHEN 'void' THEN
            RETURN 'Void';
        ELSE
            RETURN 'Unknown';
    END CASE;
END;
$function$;
```

### 15.2. Calling the Function

```sql
SELECT
    invoice_id,
    status,
    plpgsql_cond_lab.invoice_status_label(status)
        AS status_label
FROM plpgsql_cond_lab.invoices
ORDER BY invoice_id;
```

### 15.3. When Plain SQL CASE Is Preferable

If you only need to map status codes to labels across thousands of rows, an inline SQL `CASE` expression inside `SELECT` is simpler and avoids per-row PL/pgSQL function call overhead:

```sql
SELECT
    invoice_id,
    CASE status
        WHEN 'draft'  THEN 'Draft'
        WHEN 'issued' THEN 'Issued'
        WHEN 'paid'   THEN 'Paid'
        WHEN 'void'   THEN 'Void'
        ELSE 'Unknown'
    END AS status_label
FROM plpgsql_cond_lab.invoices;
```

The function here exists to demonstrate the **`CASE` statement**. In production, implement mapping wherever it is simplest and fastest.

---

## 16. Function issue_invoice: IF, FOUND, CASE, and Row Locking

### 16.1. Requirements

An invoice can only be issued if:

- `invoice_id` exists.
- It belongs to the request's `tenant_id`.
- Its current status is `draft`.

If already `issued`, return `ALREADY_ISSUED` instead of re-updating. If `paid` or `void`, reject transitioning back to `issued`.

### 16.2. Why Use SELECT ... FOR UPDATE?

Two concurrent transactions could invoke the function on the same invoice simultaneously. If both read the old status before updating, unguarded multi-step checks suffer from race conditions.

`SELECT ... FOR UPDATE` locks the selected row for the transaction, serializing concurrent state checks and updates on that invoice.

### 16.3. Function Definition

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.issue_invoice(
        p_invoice_id bigint,
        p_tenant_id integer
    )
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status text;
BEGIN
    IF p_invoice_id IS NULL OR p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Invoice ID and tenant ID are required'
            USING ERRCODE = '22023';
    END IF;

    SELECT i.status
    INTO v_status
    FROM plpgsql_cond_lab.invoices AS i
    WHERE i.invoice_id = p_invoice_id
      AND i.tenant_id = p_tenant_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Invoice % not found for tenant %',
            p_invoice_id, p_tenant_id
            USING ERRCODE = 'P0002';
    END IF;

    CASE v_status
        WHEN 'draft' THEN
            UPDATE plpgsql_cond_lab.invoices AS i
            SET status = 'issued',
                issued_at = transaction_timestamp()
            WHERE i.invoice_id = p_invoice_id
              AND i.tenant_id = p_tenant_id;

            RETURN 'ISSUED';

        WHEN 'issued' THEN
            RETURN 'ALREADY_ISSUED';

        WHEN 'paid' THEN
            RAISE EXCEPTION
                'Paid invoice % cannot be issued again',
                p_invoice_id
                USING ERRCODE = '22023';

        WHEN 'void' THEN
            RAISE EXCEPTION
                'Void invoice % cannot be issued',
                p_invoice_id
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unsupported invoice status: %', v_status
                USING ERRCODE = '22023';
    END CASE;
END;
$function$;
```

### 16.4. Reading Each Layer of Conditions

1. `IF p_invoice_id IS NULL OR ...`: validate parameters.
2. `SELECT ... INTO v_status ... FOR UPDATE`: fetch and lock the target row.
3. `IF NOT FOUND`: reject missing IDs or wrong tenants.
4. `CASE v_status`: apply status-specific policy.
5. `UPDATE` runs only in the `draft` branch.
6. `RETURN` terminates the function once the outcome is known.
7. `RAISE EXCEPTION` rejects invalid state transitions.

### 16.5. Practice Issuing a Draft Invoice

```sql
SELECT plpgsql_cond_lab.issue_invoice(1, 1) AS result;

SELECT invoice_id, tenant_id, status, issued_at
FROM plpgsql_cond_lab.invoices
WHERE invoice_id = 1;
```

Run once on the sample data, this returns `'ISSUED'` and transitions invoice 1 from `draft` to `issued`.

### 16.6. Resending the Request

```sql
SELECT plpgsql_cond_lab.issue_invoice(1, 1) AS result;
```

The second call returns `'ALREADY_ISSUED'` without re-issuing or changing `issued_at`.

This demonstrates **state-based idempotency** for issuing. In complex workflows, also consider external side effects, request IDs, and end-to-end exactly-once semantics.

### 16.7. Wrong Tenant

```sql
-- Call separately to observe tenant-scoped not-found error:
-- SELECT plpgsql_cond_lab.issue_invoice(1, 2);
```

The function does not reveal whether the invoice exists in another tenant; it reports `"not found for tenant"` per the lookup predicate. This helps avoid cross-tenant information leaks, though it **does not replace database RLS or grants**.

### 16.8. Already Paid

```sql
-- Call separately to observe the error:
-- SELECT plpgsql_cond_lab.issue_invoice(3, 1);
```

The function rejects `paid` per business rules. There is no silent `ELSE` flipping unexpected states to `issued`.

---

## 17. FOUND After SELECT INTO and Common Mistakes

### 17.1. FOUND Is a Special Boolean Variable

PL/pgSQL maintains `FOUND` to report the outcome of the most recent qualifying SQL statement, including `SELECT INTO`, `PERFORM`, `INSERT`, `UPDATE`, and `DELETE` under specific rules.

Example:

```sql
SELECT i.status
INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

IF NOT FOUND THEN
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

### 17.2. Check FOUND Immediately After the Relevant Statement

Do not do this:

```sql
SELECT i.status INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

PERFORM 1;

IF NOT FOUND THEN
    -- FOUND no longer reflects the SELECT above.
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

`PERFORM 1` updates `FOUND`—setting it to `TRUE` here and hiding whether the preceding SELECT found zero rows.

### 17.3. Missing Row with Non-STRICT SELECT INTO

With ordinary `SELECT ... INTO`, when no row matches, the target variable is set to NULL and `FOUND = FALSE`. When multiple rows match, the target receives one row under non-`STRICT` rules; if exactly one row is required, enforce uniqueness with constraints or use `STRICT`.

### 17.4. SELECT INTO STRICT

```sql
SELECT i.status
INTO STRICT v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;
```

With `STRICT`:

- 0 rows → raises `NO_DATA_FOUND`.
- Multiple rows → raises `TOO_MANY_ROWS`.
- Exactly 1 row → assigns the variable.

When filtering by primary key, at most one row is guaranteed by the PK, yet missing rows still raise `NO_DATA_FOUND`.

### 17.5. Choosing IF FOUND vs. EXCEPTION NO_DATA_FOUND

- `IF NOT FOUND` after non-STRICT `SELECT` fits when "no row found" is a normal expected branch.
- `INTO STRICT` fits when missing or duplicate rows represent an invariant violation.

Do not use exceptions for every empty query; exception blocks carry overhead and affect subtransaction state.

### 17.6. RETURNING and ROW_COUNT

With UPDATE:

```sql
UPDATE plpgsql_cond_lab.invoices
SET status = 'issued'
WHERE invoice_id = p_invoice_id
  AND status = 'draft';

IF FOUND THEN
    RAISE NOTICE 'One or more rows updated';
END IF;
```

To inspect the exact affected row count:

```sql
GET DIAGNOSTICS v_updated_count = ROW_COUNT;
```

`v_updated_count` must be declared with a numeric type (`bigint` recommended). `FOUND` reports whether at least one row matched, while `ROW_COUNT` verifies invariants such as "exactly one row was updated."

---

## 18. Function pay_invoice: Combining IF Guards and State CASE

### 18.1. Rules

- Only `issued` invoices can transition to `paid`.
- Retrying when already `paid` returns `ALREADY_PAID` without altering `paid_at`.
- Missing payment timestamps are rejected.
- `draft` and `void` invoices cannot be paid in this sample state machine.
- All accesses are tenant-scoped and executed under a row lock.

### 18.2. Function Definition

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.pay_invoice(
        p_invoice_id bigint,
        p_tenant_id integer,
        p_paid_at timestamptz DEFAULT transaction_timestamp()
    )
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status text;
BEGIN
    IF p_invoice_id IS NULL OR p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Invoice ID and tenant ID are required'
            USING ERRCODE = '22023';
    END IF;

    IF p_paid_at IS NULL THEN
        RAISE EXCEPTION 'Payment timestamp is required'
            USING ERRCODE = '22023';
    END IF;

    SELECT i.status
    INTO v_status
    FROM plpgsql_cond_lab.invoices AS i
    WHERE i.invoice_id = p_invoice_id
      AND i.tenant_id = p_tenant_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Invoice % not found for tenant %',
            p_invoice_id, p_tenant_id
            USING ERRCODE = 'P0002';
    END IF;

    CASE v_status
        WHEN 'issued' THEN
            UPDATE plpgsql_cond_lab.invoices AS i
            SET status = 'paid',
                paid_at = p_paid_at
            WHERE i.invoice_id = p_invoice_id
              AND i.tenant_id = p_tenant_id;

            RETURN 'PAID';

        WHEN 'paid' THEN
            RETURN 'ALREADY_PAID';

        WHEN 'draft' THEN
            RAISE EXCEPTION
                'Draft invoice % must be issued first',
                p_invoice_id
                USING ERRCODE = '22023';

        WHEN 'void' THEN
            RAISE EXCEPTION
                'Void invoice % cannot be paid',
                p_invoice_id
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unsupported invoice status: %', v_status
                USING ERRCODE = '22023';
    END CASE;
END;
$function$;
```

### 18.3. Calling on an Issued Invoice

```sql
SELECT plpgsql_cond_lab.pay_invoice(
    2,
    1,
    TIMESTAMPTZ '2026-11-04 11:00:00+00'
) AS result;

SELECT invoice_id, status, paid_at
FROM plpgsql_cond_lab.invoices
WHERE invoice_id = 2;
```

The result is `'PAID'`, with `paid_at` matching the supplied timestamp.

### 18.4. Testing a Retry Call

```sql
SELECT plpgsql_cond_lab.pay_invoice(
    2,
    1,
    TIMESTAMPTZ '2026-11-05 11:00:00+00'
) AS result;
```

Returns `'ALREADY_PAID'`. The original `paid_at` timestamp is preserved rather than overwritten by the retry.

### 18.5. Why Validate Timestamp Before Checking Status?

This is an API contract choice: a request missing `p_paid_at` is always invalid even if the invoice is already paid. Another design might return `'ALREADY_PAID'` before checking `p_paid_at`, provided the policy is explicit.

There is no universal fixed check order; **the order of `IF` guards defines API behavior**.

### 18.6. Security and Transactions

Row locks coordinate concurrent state changes on the same invoice, but:

- They do not prove the caller is authorized for that tenant.
- They do not replace RLS, grants, or application-layer authorization.
- If a function uses `SECURITY DEFINER`, carefully manage ownership, `search_path`, and execute privileges.
- If external services are called, a database transaction rollback does not roll back external side effects.

These lab functions use default settings and do not represent a complete production payment protocol.

---

## 19. CASE and IF Inside Triggers

Triggers routinely inspect transitions between `OLD` and `NEW`.

### 19.1. Example: Guarding State Transitions

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.guard_invoice_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    CASE OLD.status
        WHEN 'draft' THEN
            IF NEW.status NOT IN ('issued', 'void') THEN
                RAISE EXCEPTION
                    'Invalid transition: % -> %',
                    OLD.status, NEW.status
                    USING ERRCODE = '22023';
            END IF;

        WHEN 'issued' THEN
            IF NEW.status NOT IN ('paid', 'void') THEN
                RAISE EXCEPTION
                    'Invalid transition: % -> %',
                    OLD.status, NEW.status
                    USING ERRCODE = '22023';
            END IF;

        WHEN 'paid', 'void' THEN
            RAISE EXCEPTION
                'Terminal invoice state cannot change: % -> %',
                OLD.status, NEW.status
                USING ERRCODE = '22023';

        ELSE
            RAISE EXCEPTION
                'Unknown old status: %', OLD.status
                USING ERRCODE = '22023';
    END CASE;

    RETURN NEW;
END;
$function$;
```

### 19.2. Attaching a BEFORE UPDATE Trigger

```sql
CREATE TRIGGER invoices_guard_transition
BEFORE UPDATE OF status
ON plpgsql_cond_lab.invoices
FOR EACH ROW
EXECUTE FUNCTION
    plpgsql_cond_lab.guard_invoice_transition();
```

Because `status` is `NOT NULL` and constrained by `CHECK`, `NEW.status NOT IN (...)` will not encounter NULL on valid rows; if a source column were nullable, adjust the condition to avoid UNKNOWN.

### 19.3. Testing a Valid Transition

```sql
-- If invoice 1 was issued in Section 16:
SELECT plpgsql_cond_lab.pay_invoice(
    1, 1, TIMESTAMPTZ '2026-11-06 10:00:00+00'
);
```

The trigger permits `issued → paid`, and the function returns `'PAID'`.

### 19.4. Testing an Invalid Transition

```sql
-- Run separately to observe the error:
-- UPDATE plpgsql_cond_lab.invoices
-- SET status = 'draft'
-- WHERE invoice_id = 3;
```

The trigger blocks `paid → draft`. Because `RAISE EXCEPTION` aborts the statement, the status change is never committed.

### 19.5. Triggers and UPDATE OF

`BEFORE UPDATE OF status` fires whenever `status` appears in the **UPDATE's target column list**, regardless of whether the value actually changed. The function checks:

```sql
IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
END IF;
```

to pass through no-op updates cleanly.

### 19.6. Limitation of UPDATE OF with Multiple Triggers

If another `BEFORE` trigger modifies `NEW.status` when the SQL `SET` clause did not mention `status`, an `UPDATE OF status` trigger will not fire because PostgreSQL checks the SQL statement's column list. To guard **every status change regardless of other triggers**, define a `BEFORE UPDATE` trigger without `OF` and manage trigger ordering carefully.

### 19.7. Trigger Order Is Part of Design

Multiple triggers of the same type/event on a table run in alphabetical order by trigger name. If a later trigger normalizes or overwrites `status` after a guard trigger runs, the final state can bypass validation.

The right fix is not lucky naming—explicitly design **invariants, execution order, and a single authoritative place allowed to mutate status**.

### 19.8. Triggers Do Not Guarantee External Workflows

Triggers only protect updates passing through the table in normal firing contexts; replication/session-replication settings, bypass privileges, and external side effects require separate controls. Never treat a trigger as your entire security or workflow architecture.

---

## 20. RAISE NOTICE, WARNING, EXCEPTION, and SQLSTATE

### 20.1. Three Common Message Levels

| Syntax | Typical Behavior |
|---|---|
| `RAISE NOTICE` | Emits a diagnostic notice without aborting the statement |
| `RAISE WARNING` | Emits a warning; execution continues |
| `RAISE EXCEPTION` | Raises an error and exits normal execution flow |

Example:

```sql
DO $block$
BEGIN
    RAISE NOTICE 'Starting validation';
    RAISE WARNING 'This is a demonstration warning';
    RAISE NOTICE 'Still running';
END;
$block$;
```

### 20.2. Use Exceptions When Execution Cannot Continue

```sql
IF p_amount < 0 THEN
    RAISE EXCEPTION 'Amount must be non-negative: %', p_amount
        USING ERRCODE = '22023';
END IF;
```

`ERRCODE = '22023'` represents *invalid_parameter_value* in SQLSTATE. Applications can classify errors reliably via SQLSTATE instead of matching message text.

### 20.3. EXCEPTION Blocks Have Subtransaction Semantics

```sql
DO $block$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Controlled failure';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Caught: %, SQLSTATE=%', SQLERRM, SQLSTATE;
    END;

    RAISE NOTICE 'Outer block continues';
END;
$block$;
```

When an exception is caught, PostgreSQL rolls back persistent database changes inside the failing block via an internal subtransaction. Local PL/pgSQL variables follow separate rules when exceptions occur.

### 20.4. Do Not Use EXCEPTION as a Regular IF

If a value may be `NULL` or negative, check it with `IF`. Never let operations fail and catch exceptions for every row. Exception blocks add overhead, complicate control flow, and can hide real bugs.

### 20.5. Never Swallow All Errors

A block like:

```sql
EXCEPTION
    WHEN others THEN
        NULL;
```

is dangerous when used just to "keep the program running," because it hides permission errors, deadlocks, logic bugs, and constraint violations.

When catching errors, match specific SQLSTATEs or condition names, log appropriate context, and handle or rethrow with `RAISE;` when recovery is unsafe.

---

## 21. RETURN, RETURN NEXT, and Control Flow

### 21.1. RETURN Exits the Function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.describe_sign(p_value integer)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_value IS NULL THEN
        RETURN 'unknown';
    END IF;

    IF p_value < 0 THEN
        RETURN 'negative';
    END IF;

    IF p_value = 0 THEN
        RETURN 'zero';
    END IF;

    RETURN 'positive';
END;
$function$;
```

Once a `RETURN` executes, the rest of the function is skipped.

### 21.2. Early Return Reduces Nesting

Compare:

```sql
IF p_customer_id IS NOT NULL THEN
    IF p_amount > 0 THEN
        IF p_approved THEN
            -- Business action
        ELSE
            -- Error
        END IF;
    ELSE
        -- Error
    END IF;
ELSE
    -- Error
END IF;
```

against guard clauses:

```sql
IF p_customer_id IS NULL THEN
    RAISE EXCEPTION 'Customer ID required';
END IF;

IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Positive amount required';
END IF;

IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;

-- Business action with shallower nesting.
```

Guard clauses make the happy path much clearer, as long as they preserve the intended priority order when multiple inputs are invalid simultaneously.

### 21.3. RETURN NEXT vs. RETURN

In set-returning functions (`RETURNS SETOF ...`), `RETURN NEXT` appends a row to the output set **without immediately exiting the function** the way a scalar `RETURN value` does.

Conceptual example:

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.sample_signs()
RETURNS SETOF text
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN NEXT 'negative';
    RETURN NEXT 'zero';
    RETURN NEXT 'positive';
    RETURN;
END;
$function$;
```

The final `RETURN;` ends set generation.

### 21.4. Never Treat IF as a Loop

`IF` chooses a branch **once** when reached. If you need repetition until a condition holds, use `LOOP`/`WHILE`/`FOR`; an `END IF;` never loops back automatically.

---

## 22. Should You Use SQL CASE or PL/pgSQL for Bulk Updates?

### 22.1. Problem

Millions of invoices need priority tiers assigned based on `amount`.

An inefficient approach:

```text
FOR each invoice:
    SELECT one row
    IF ...
       UPDATE row
    ELSIF ...
       UPDATE row
    END IF
```

When the logic is a pure function of `amount`, row-by-row PL/pgSQL incurs heavy overhead.

### 22.2. A Single SELECT Using SQL CASE

```sql
SELECT
    invoice_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN 'high'
        WHEN amount >= 100 THEN 'normal'
        ELSE 'low'
    END AS priority
FROM plpgsql_cond_lab.invoices;
```

SQL `CASE` computes the label per row inside one set-based `SELECT`, with no procedural loop.

### 22.3. A Single Set-Based UPDATE

If the table had a `priority` column, you could run:

```sql
-- Example on a table that includes a priority column:
-- UPDATE some_schema.invoices
-- SET priority = CASE
--     WHEN amount >= 1000 THEN 'high'
--     WHEN amount >= 100 THEN 'normal'
--     ELSE 'low'
-- END;
```

Do not run this on the lab table because `plpgsql_cond_lab.invoices` does not have a `priority` column.

### 22.4. CASE with Aggregates

```sql
SELECT
    tenant_id,
    SUM(
        CASE
            WHEN status = 'paid' THEN amount
            ELSE 0
        END
    ) AS paid_amount
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id
ORDER BY tenant_id;
```

PostgreSQL also provides `FILTER`, which is often cleaner for conditional aggregates:

```sql
SELECT
    tenant_id,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0
    ) AS paid_amount,
    COUNT(*) FILTER (WHERE status = 'paid')
        AS paid_count
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id
ORDER BY tenant_id;
```

`SUM` over an empty set returns SQL NULL, so `COALESCE` is used when the contract expects `0`.

### 22.5. When PL/pgSQL Truly Adds Value

Use PL/pgSQL when you need:

- Multiple SQL statements coordinated by intermediate state.
- Validation and domain-specific error reporting.
- State transitions with locking/transaction semantics.
- Triggers enforcing invariants.
- Control flow depending on the result of a prior SQL query.
- Reusable procedural functions or procedures.

Do not replace every simple SQL `CASE` value-mapping expression with a PL/pgSQL `IF`/`CASE` statement.

---

## 23. CASE in ORDER BY and Priority Sorting

### 23.1. Sorting Statuses in Business Order

By default, `ORDER BY status` sorts lexicographically by collation, not by business priority.

```sql
SELECT
    invoice_id,
    status,
    amount
FROM plpgsql_cond_lab.invoices
ORDER BY
    CASE status
        WHEN 'issued' THEN 1
        WHEN 'draft' THEN 2
        WHEN 'paid' THEN 3
        WHEN 'void' THEN 4
        ELSE 5
    END,
    invoice_id;
```

### 23.2. CASE in WHERE Can Hinder Index Usage

```sql
-- Do not overcomplicate simple status filtering:
-- WHERE CASE WHEN status = 'paid' THEN true ELSE false END
```

Writing directly:

```sql
WHERE status = 'paid'
```

lets the planner recognize the column predicate and consider an index.

### 23.3. CASE for Genuinely Branching Filter Conditions

```sql
SELECT invoice_id, amount, status
FROM plpgsql_cond_lab.invoices
WHERE
    CASE
        WHEN status = 'issued' THEN amount >= 100
        WHEN status = 'draft' THEN amount >= 500
        ELSE false
    END;
```

Logically, this can be expressed as:

```sql
WHERE
    (status = 'issued' AND amount >= 100)
    OR
    (status = 'draft' AND amount >= 500)
```

In many cases, direct Boolean predicates are easier to read and give the optimizer clearer conditions. Check `EXPLAIN` when tuning.

---

## 24. Precision with Dates, Times, and Conditions

### 24.1. Use timestamptz for Real Instants

`paid_at` in the lab table is `TIMESTAMPTZ`, representing an exact point in time. Never use timezone-naive strings when comparing timestamps across business logic.

### 24.2. Overdue Classification

A function might evaluate:

```sql
IF p_paid_at IS NOT NULL THEN
    RETURN 'PAID';
ELSIF p_due_at IS NULL THEN
    RETURN 'UNKNOWN_DUE_DATE';
ELSIF p_due_at < transaction_timestamp() THEN
    RETURN 'OVERDUE';
ELSE
    RETURN 'OPEN';
END IF;
```

This is a **function body snippet**; `p_paid_at` and `p_due_at` must be declared in an actual function.

### 24.3. Handle NULL Before Comparing

If `p_due_at IS NULL`, `p_due_at < now()` evaluates to UNKNOWN. To classify "no due date," include an explicit `IS NULL` branch.

### 24.4. Transaction Timestamp vs. Wall-Clock Time

`transaction_timestamp()` returns the start timestamp of the current transaction. `clock_timestamp()` returns real wall-clock time at the moment of invocation and can advance within the same statement.

For workflows needing a consistent timestamp across a transaction, `transaction_timestamp()` is easier to reason about. For measuring elapsed execution latency, `clock_timestamp()` is appropriate. Choose deliberately rather than mixing `now()` and `clock_timestamp()`.

---

## 25. NULL in Simple CASE and Searched CASE

### 25.1. Simple CASE and NULL Values

Suppose:

```sql
CASE p_status
    WHEN 'paid' THEN ...
    WHEN NULL THEN ...
    ELSE ...
END CASE;
```

**Never** use `WHEN NULL` to match an SQL NULL `test_expression` the way `IS NULL` does. Normal equality comparison with NULL never returns TRUE.

### 25.2. Correct Approach

```sql
CASE
    WHEN p_status IS NULL THEN
        RAISE NOTICE 'Missing status';
    WHEN p_status = 'paid' THEN
        RAISE NOTICE 'Paid';
    ELSE
        RAISE NOTICE 'Other';
END CASE;
```

Or validate with `IF` before a simple `CASE`:

```sql
IF p_status IS NULL THEN
    RAISE EXCEPTION 'Status required';
END IF;

CASE p_status
    WHEN 'paid' THEN ...
    WHEN 'issued' THEN ...
    ELSE ...
END CASE;
```

### 25.3. Searched CASE WHEN NULL Is Not Selected

```sql
DO $block$
DECLARE
    v_amount numeric := NULL;
BEGIN
    CASE
        WHEN v_amount > 100 THEN
            RAISE NOTICE 'Above 100';
        WHEN v_amount <= 100 THEN
            RAISE NOTICE 'At most 100';
        ELSE
            RAISE NOTICE 'Missing amount';
    END CASE;
END;
$block$;
```

With NULL, both comparisons yield UNKNOWN, so `ELSE` runs.

### 25.4. Risk Mitigation: Fail Closed

If a Boolean `p_has_permission` is nullable:

```sql
IF p_has_permission = false THEN
    RAISE EXCEPTION 'Denied';
END IF;
```

**does not** reject NULL, because `NULL = false` is UNKNOWN. If policy requires explicit TRUE:

```sql
IF p_has_permission IS NOT TRUE THEN
    RAISE EXCEPTION 'Permission required';
END IF;
```

Real access control also requires caller authentication and database RLS/grants; a client-supplied Boolean parameter **is never proof of authorization**.

---

## 26. Conditionals in Procedures vs. Functions

### 26.1. Function

```sql
CREATE OR REPLACE FUNCTION
    plpgsql_cond_lab.is_positive(p_value numeric)
RETURNS boolean
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_value IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_value > 0;
END;
$function$;
```

Call:

```sql
SELECT plpgsql_cond_lab.is_positive(10);
```

### 26.2. Procedure

```sql
CREATE OR REPLACE PROCEDURE
    plpgsql_cond_lab.describe_invoice_status(p_status text)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    CASE p_status
        WHEN 'draft' THEN
            RAISE NOTICE 'Draft';
        WHEN 'issued' THEN
            RAISE NOTICE 'Issued';
        WHEN 'paid' THEN
            RAISE NOTICE 'Paid';
        ELSE
            RAISE NOTICE 'Other';
    END CASE;
END;
$procedure$;
```

Call:

```sql
CALL plpgsql_cond_lab.describe_invoice_status('issued');
```

### 26.3. Same IF/CASE, Different Execution Interfaces

`IF` and `CASE` are PL/pgSQL constructs usable in functions, procedures, trigger functions, and `DO` blocks. However:

- Functions declare a return type and are invoked in SQL expressions such as `SELECT function(...)`.
- Procedures are invoked with `CALL` and follow procedure parameter and transaction-control rules.
- Trigger functions access `NEW`/`OLD`/`TG_OP` in trigger context.
- `DO` is an anonymous one-off block, not a persistent callable object.

Do not copy `RETURN 'paid'` from a scalar function directly into a procedure with a different return contract.

---

## 27. Debugging Conditional Flow

### 27.1. RAISE NOTICE with Variable Values

```sql
RAISE NOTICE 'invoice=%, tenant=%, status=%',
    p_invoice_id, p_tenant_id, v_status;
```

Messages help trace which branch ran, though you should avoid logging sensitive financial details or PII unnecessarily.

### 27.2. Logging the Chosen Branch

```sql
DO $block$
DECLARE
    v_amount numeric := 150;
BEGIN
    IF v_amount < 100 THEN
        RAISE NOTICE 'branch=small';
    ELSIF v_amount < 1000 THEN
        RAISE NOTICE 'branch=medium';
    ELSE
        RAISE NOTICE 'branch=large';
    END IF;
END;
$block$;
```

### 27.3. RAISE NOTICE Is Not Full Testing

For critical code, write test assertions:

```sql
DO $test$
DECLARE
    v_category text;
BEGIN
    v_category := plpgsql_cond_lab.classify_amount(150);

    IF v_category IS DISTINCT FROM 'MEDIUM' THEN
        RAISE EXCEPTION
            'Unexpected category: %, expected MEDIUM',
            v_category;
    END IF;
END;
$test$;
```

Such a test fails loudly if the result differs from expectations. Using `IS DISTINCT FROM` handles NULL safely so unexpected NULLs never pass silently.

### 27.4. Testing Boundary Values

For `SMALL`/`MEDIUM`/`LARGE` classification, test at least:

```text
NULL
-1
0
0.01
99.99
100
999.99
1000
```

Off-by-one boundary bugs are easily missed if you only test mid-range numbers.

### 27.5. Testing Branch Precedence

A good test picks a value **satisfying two overlapping conditions** to verify branch priority:

```sql
DO $test$
DECLARE
    v_amount numeric := 1500;
    v_label text;
BEGIN
    IF v_amount >= 1000 THEN
        v_label := 'LARGE';
    ELSIF v_amount >= 100 THEN
        v_label := 'MEDIUM';
    ELSE
        v_label := 'SMALL';
    END IF;

    IF v_label <> 'LARGE' THEN
        RAISE EXCEPTION 'Wrong branch: %', v_label;
    END IF;
END;
$test$;
```

### 27.6. Testing Rollbacks and Business Errors

For `issue`/`pay` functions, test:

- Nonexistent invoice.
- Valid ID, wrong tenant.
- `draft → issued`.
- Retrying `issued`.
- `issued → paid`.
- Retrying `paid`.
- `paid → issued` rejected.
- `void → paid` rejected.
- Two concurrent sessions updating the same invoice.

Verify not only the returned string, but also **the persisted database row state** after commit or rollback.

---

## 28. Common Mistakes

**1. Missing `END IF;`.** Every `IF` structure must be explicitly closed.

**2. Writing `END;` instead of `END IF;`.** `END;` closes a PL/pgSQL block, not an `IF`.

**3. Writing `END;` instead of `END CASE;` for a PL/pgSQL CASE statement.** SQL `CASE` expressions and PL/pgSQL `CASE` statements use different closing syntax.

**4. Writing `END CASE;` inside an SQL SELECT.** SQL `CASE` expressions use `END`.

**5. Using `WHEN v_amount > 100` inside a simple CASE on `amount`.** Ranges require searched `CASE` or `IF`.

**6. Assuming every CASE without ELSE returns NULL.** Only SQL `CASE` expressions without `ELSE` return NULL; PL/pgSQL `CASE` statements raise `CASE_NOT_FOUND` when unmatched and lacking `ELSE`.

**7. Writing `IF x = NULL`.** Always use `IS NULL`.

**8. Treating Boolean NULL as FALSE in all expressions.** SQL has three-valued logic; `IF` simply skips `THEN` whenever a condition is not `TRUE`.

**9. Writing `WHEN NULL` in simple CASE to catch SQL NULL.** Use searched `CASE` with `IS NULL`, or check with `IF` beforehand.

**10. Using `NOT IN` on sets containing NULL and forgetting UNKNOWN.** Prefer `NOT EXISTS`.

**11. Ignoring UNKNOWN in security checks.** Use `IS NOT TRUE` when only explicit `TRUE` should pass.

**12. Putting broad conditions before specific ones.** Later branches become unreachable.

**13. Omitting parentheses in security-sensitive AND/OR conditions.** Easily misstates the policy.

**14. Relying on SQL AND/OR evaluation order to avoid division by zero.** Write explicit guards or `NULLIF`.

**15. Using integers as Booleans in IF.** Conditions must evaluate to Boolean.

**16. Forgetting semicolons after statements or `END IF;`.** The PL/pgSQL parser will reject the code.

**17. Confusing `ELSIF` with an `IF` nested inside `ELSE`.** True nesting requires closing both `IF`s.

**18. Writing a scalar function with a path reaching the end without RETURN.** Raises a runtime error.

**19. Using `RAISE NOTICE` when a transaction must be rejected.** `NOTICE` does not prevent an `UPDATE` from proceeding.

**20. Catching `WHEN OTHERS THEN NULL` to hide all errors.** Silently corrupts data and hides bugs.

**21. Using exceptions as routine IF branches.** Adds overhead and obscures control flow.

**22. Checking `FOUND` after a `SELECT INTO` with an intervening `PERFORM`.** `FOUND` gets overwritten.

**23. Using non-STRICT `SELECT INTO` on multi-row queries assuming deterministic "first row" order.** Enforce uniqueness or add explicit `ORDER BY`/`LIMIT`.

**24. Running a bare `SELECT` returning rows inside a function without `INTO` or `PERFORM`.** PL/pgSQL requires an explicit destination.

**25. Naming variables the same as table columns without aliases.** Leads to ambiguous references.

**26. Treating PL/pgSQL `BEGIN ... END` as a transaction boundary.** It is only a block.

**27. Using a PL/pgSQL `CASE` loop to update rows individually when an SQL `CASE` expression suffices.** Causes unnecessary overhead.

**28. Assuming SQL `CASE` always shields constant failing subexpressions.** Constant folding by the planner can evaluate expressions early; use safe arithmetic and types.

**29. Updating invoice status without locking under concurrent writers.** Multi-step checks and updates suffer race conditions.

**30. Holding `SELECT FOR UPDATE` locks across long transactions.** Increases lock contention.

**31. Filtering `tenant_id` only in `SELECT` and omitting it in `UPDATE`.** Scope consistently and enforce permissions.

**32. Treating a client-supplied `tenant_id` parameter as sufficient authorization.** Enforce authentication, authorization, and grants/RLS as appropriate.

**33. Treating `CHECK` constraints as a substitute for a state machine.** Constraints validate current row state, not old-to-new transitions.

**34. Overwriting `paid_at` on retried payment requests.** Breaks workflow idempotency.

**35. Trigger guards ignoring `OLD`/`NEW` transitions.** Allows invalid backward transitions.

**36. `UPDATE OF status` triggers missing status changes made by other triggers.** Design trigger scope and ordering carefully.

**37. Omitting `ELSE` in a `CASE` receiving out-of-range input without expecting `CASE_NOT_FOUND`.** Add `ELSE RAISE` or `ELSE NULL` per policy.

**38. Thinking SQL `CASE` and PL/pgSQL `CASE` behave identically when `ELSE` is omitted.** They do not.

**39. Using `COALESCE` to collapse `UNKNOWN` into `FALSE` in three-state workflows.** Loses state information.

**40. Optimizing multi-branch `IF` chains without boundary tests.** Off-by-one errors around 0, 100, 1000, and NULL are common.

---

## 29. Practice Exercises with Answers

### Exercise 1 — IF Without ELSE

**Task:** emit a NOTICE when quantity is negative.

**Answer:**

```sql
IF v_quantity < 0 THEN
    RAISE NOTICE 'Negative quantity';
END IF;
```

This sits inside a PL/pgSQL block where `v_quantity` is declared.

### Exercise 2 — IF ... ELSE

**Task:** distinguish numbers greater than 0 from numbers not greater than 0.

```sql
IF v_number > 0 THEN
    RAISE NOTICE 'Positive';
ELSE
    RAISE NOTICE 'Non-positive or NULL';
END IF;
```

**Explanation:** For NULL, the condition is UNKNOWN so `ELSE` runs. To separate three states, check `IS NULL` first.

### Exercise 3 — Three Boolean States

**Task:** separate TRUE, FALSE, and NULL.

```sql
IF v_flag IS TRUE THEN
    RAISE NOTICE 'TRUE';
ELSIF v_flag IS FALSE THEN
    RAISE NOTICE 'FALSE';
ELSE
    RAISE NOTICE 'UNKNOWN';
END IF;
```

### Exercise 4 — Range Classification

**Task:** negative amount is an error, 0 is ZERO, under 100 is SMALL, 100 or above is LARGE.

```sql
IF v_amount IS NULL THEN
    RAISE EXCEPTION 'Missing amount';
ELSIF v_amount < 0 THEN
    RAISE EXCEPTION 'Negative amount';
ELSIF v_amount = 0 THEN
    v_label := 'ZERO';
ELSIF v_amount < 100 THEN
    v_label := 'SMALL';
ELSE
    v_label := 'LARGE';
END IF;
```

### Exercise 5 — Branch Order

```sql
IF v_amount >= 100 THEN
    v_label := 'MEDIUM';
ELSIF v_amount >= 1000 THEN
    v_label := 'LARGE';
END IF;
```

**Question:** What does it assign for 1500?

**Answer:** `'MEDIUM'`, because the first branch is already TRUE. Move `>= 1000` first.

### Exercise 6 — Simple CASE

**Task:** map statuses `draft`/`issued`/`paid` to uppercase labels.

```sql
CASE v_status
    WHEN 'draft' THEN
        v_label := 'DRAFT';
    WHEN 'issued' THEN
        v_label := 'OPEN';
    WHEN 'paid' THEN
        v_label := 'SETTLED';
    ELSE
        v_label := 'OTHER';
END CASE;
```

### Exercise 7 — Grouping Multiple Values in Simple CASE

```sql
CASE v_status
    WHEN 'draft', 'issued' THEN
        v_label := 'UNPAID';
    WHEN 'paid' THEN
        v_label := 'SETTLED';
    ELSE
        v_label := 'OTHER';
END CASE;
```

**Answer:** A single `WHEN` can match multiple comma-separated values in PL/pgSQL simple `CASE`.

### Exercise 8 — Searched CASE

```sql
CASE
    WHEN v_score IS NULL THEN
        v_grade := 'UNKNOWN';
    WHEN v_score >= 90 THEN
        v_grade := 'A';
    WHEN v_score >= 70 THEN
        v_grade := 'B';
    ELSE
        v_grade := 'C';
END CASE;
```

### Exercise 9 — CASE_NOT_FOUND

**Question:** Does a PL/pgSQL `CASE` without `ELSE` return NULL when nothing matches?

**Answer:** No. It raises `CASE_NOT_FOUND`.

### Exercise 10 — ELSE NULL

**Task:** write a `CASE` that does nothing for unknown statuses.

```sql
CASE v_status
    WHEN 'paid' THEN
        RAISE NOTICE 'Paid';
    ELSE
        NULL;
END CASE;
```

**Explanation:** `NULL;` is a no-op statement in PL/pgSQL.

### Exercise 11 — SQL CASE Expression Without ELSE

```sql
SELECT CASE WHEN 1 > 10 THEN 'yes' END AS result;
```

**Answer:** Returns SQL `NULL`, unlike a PL/pgSQL `CASE` statement.

### Exercise 12 — END CASE or END?

**Question:** Is `SELECT CASE ... END CASE` valid?

**Answer:** Not in SQL `CASE` expression syntax. SQL expressions use `END`; PL/pgSQL `CASE` statements use `END CASE;`.

### Exercise 13 — Checking NULL

```sql
IF v_value = NULL THEN
    ...
END IF;
```

**Answer:** Wrong check. Use `IF v_value IS NULL THEN`.

### Exercise 14 — Nullable Permission

**Task:** proceed only when `p_approved = TRUE`.

```sql
IF p_approved IS NOT TRUE THEN
    RAISE EXCEPTION 'Approval required';
END IF;
```

### Exercise 15 — AND/OR

**Task:** user must be active AND must be either admin or owner.

```sql
IF p_is_active IS TRUE
   AND (p_is_admin IS TRUE OR p_is_owner IS TRUE) THEN
    RAISE NOTICE 'Authorized';
ELSE
    RAISE EXCEPTION 'Not authorized';
END IF;
```

### Exercise 16 — NOT IN with NULL

```sql
SELECT 9 NOT IN (1, 2, NULL);
```

**Answer:** Evaluates to `NULL`, not `TRUE`.

### Exercise 17 — SELECT INTO and FOUND

**Task:** fetch invoice status and raise an error if missing.

```sql
SELECT i.status INTO v_status
FROM plpgsql_cond_lab.invoices AS i
WHERE i.invoice_id = p_invoice_id;

IF NOT FOUND THEN
    RAISE EXCEPTION 'Invoice not found';
END IF;
```

**Note:** Check `FOUND` immediately after the `SELECT`.

### Exercise 18 — Why Is PERFORM Between SELECT and IF FOUND Dangerous?

**Answer:** `PERFORM` updates `FOUND`, causing `IF` to evaluate `PERFORM`'s outcome rather than the earlier `SELECT`.

### Exercise 19 — INTO STRICT

**Question:** What happens when `SELECT INTO STRICT` finds no rows?

**Answer:** Raises `NO_DATA_FOUND`. If multiple rows match, it raises `TOO_MANY_ROWS`.

### Exercise 20 — RAISE NOTICE or RAISE EXCEPTION?

**Scenario:** Negative amounts must never be written to an invoice.

**Answer:** Use `RAISE EXCEPTION` or a database constraint to reject the write; `NOTICE` only logs a message and does not stop writes.

### Exercise 21 — Early RETURN

**Task:** return `'UNKNOWN'` if input is NULL, otherwise `'POSITIVE'` or `'OTHER'`.

```sql
IF p_value IS NULL THEN
    RETURN 'UNKNOWN';
END IF;

IF p_value > 0 THEN
    RETURN 'POSITIVE';
END IF;

RETURN 'OTHER';
```

### Exercise 22 — Draft Invoice

**Scenario:** Invoice 1 starts as `'draft'` and `issue_invoice(1,1)` is called.

**Answer:** The function locks the row, enters the `draft` branch, updates status to `issued`, and returns `'ISSUED'`.

### Exercise 23 — Retry Issue

**Scenario:** Calling `issue_invoice(1,1)` a second time.

**Answer:** Returns `'ALREADY_ISSUED'` without re-issuing.

### Exercise 24 — Wrong Tenant

**Scenario:** Invoice 1 belongs to tenant 1; `issue_invoice(1,2)` is called.

**Answer:** The `SELECT` filtering on both invoice ID and tenant ID finds no row; `NOT FOUND` raises an error per contract.

### Exercise 25 — Paid → Issued

**Question:** Why does the function reject re-issuing a paid invoice?

**Answer:** The state machine forbids backward transitions from terminal state `paid` to `issued`; guarding it prevents business state corruption.

### Exercise 26 — SELECT FOR UPDATE

**Question:** Why fetch and lock the row before evaluating `CASE`?

**Answer:** It coordinates concurrent transactions modifying the same invoice, preventing race conditions between checking state and updating. It does not replace full transaction design or authorization.

### Exercise 27 — Trigger Guard

**Task:** prevent `paid → draft`.

**Answer:** A `BEFORE UPDATE` trigger can check `OLD.status='paid'` and `NEW.status IS DISTINCT FROM OLD.status`, then call `RAISE EXCEPTION` on disallowed transitions.

### Exercise 28 — When to Use SQL CASE Instead of PL/pgSQL IF?

**Answer:** When computing or updating values conditionally across many rows in one `SELECT`/`UPDATE`, set-based SQL `CASE` is simpler and faster than a procedural loop.

### Exercise 29 — CASE in ORDER BY

**Task:** sort `issued` before `draft`, then `paid`.

```sql
SELECT invoice_id, status
FROM plpgsql_cond_lab.invoices
ORDER BY
    CASE status
        WHEN 'issued' THEN 1
        WHEN 'draft' THEN 2
        WHEN 'paid' THEN 3
        ELSE 4
    END,
    invoice_id;
```

### Exercise 30 — Conditional Aggregate

**Task:** total paid amount per tenant.

```sql
SELECT
    tenant_id,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0
    ) AS paid_total
FROM plpgsql_cond_lab.invoices
GROUP BY tenant_id;
```

### Exercise 31 — Danger of EXCEPTION WHEN OTHERS THEN NULL

**Answer:** Swallowing all errors hides constraint violations or bugs, allowing execution to continue in a corrupted state. Catch only specific exceptions and handle them intentionally.

### Exercise 32 — BEGIN ... END

**Question:** Is `BEGIN ... END` in a function equivalent to `BEGIN TRANSACTION ... COMMIT`?

**Answer:** No. It is a PL/pgSQL block and does not create a transaction boundary.

### Exercise 33 — Transaction Timestamp

**Question:** Why is `transaction_timestamp()` well suited for multiple operations sharing one reference time?

**Answer:** It stays fixed at the start time of the current transaction, giving all statements in that transaction a consistent reference timestamp.

### Exercise 34 — Testing NULL with an Assertion

```sql
DO $test$
DECLARE
    v_label text;
BEGIN
    v_label := plpgsql_cond_lab.classify_amount(NULL);

    IF v_label IS DISTINCT FROM 'UNKNOWN' THEN
        RAISE EXCEPTION 'Expected UNKNOWN, got %', v_label;
    END IF;
END;
$test$;
```

**Answer:** Using `IS DISTINCT FROM` ensures the assertion catches unexpected NULL results too.

### Exercise 35 — Testing Boundary 100

```sql
SELECT plpgsql_cond_lab.classify_amount(100);
```

**Answer:** `'MEDIUM'` in the lab function, because `p_amount < 100` is false at exactly 100.

### Exercise 36 — Testing Boundary 1000

```sql
SELECT plpgsql_cond_lab.classify_amount(1000);
```

**Answer:** `'LARGE'` in the lab function.

---

## 30. Checklist When Writing IF/CASE in PL/pgSQL

### Syntax

1. Use `IF ... THEN ... END IF;` with proper semicolons.
2. Use `ELSIF` for chained alternative conditions.
3. Use `CASE test_expression ... END CASE;` when matching one state against discrete values.
4. Use `CASE WHEN condition ... END CASE;` for multiple Boolean predicates.
5. Distinguish SQL `CASE ... END` from PL/pgSQL `CASE ... END CASE;`.
6. Provide an appropriate `ELSE` for all inputs, or intentionally rely on `CASE_NOT_FOUND`.

### Correctness

7. Check `NULL` with `IS NULL`/`IS NOT NULL` instead of `= NULL`.
8. For nullable permissions/approvals, check whether policy requires `IS NOT TRUE`.
9. Order specific conditions before broad ones.
10. Use parentheses in multi-part `AND`/`OR` security rules.
11. Never rely on SQL short-circuiting as a general guard against division by zero.
12. Verify range operators `<`/`<=`/`>`/`>=`.
13. Do not mix numeric/text types in comparisons with differing semantics.
14. Never mask invalid inputs with `ELSE NULL` when they should be rejected.
15. Never confuse `NOTICE` with `EXCEPTION`.

### Queries and Concurrency

16. Use clear table aliases and `p_`/`v_` variable prefixes.
17. Use `SELECT INTO` with valid PL/pgSQL targets.
18. Inspect `FOUND` immediately after the statement that sets it.
19. Use `INTO STRICT` when exactly one row is required and exceptions are expected.
20. For racy state transitions, consider `SELECT ... FOR UPDATE` or atomic conditional `UPDATE`s.
21. Enforce real tenant scoping and authorization, not just client parameters.
22. Add DB constraints for current-row invariants.
23. When state machines require `OLD → NEW` rules, use appropriate triggers/functions.
24. Avoid holding locks in long-running transactions.

### Performance and Testing

25. Prefer set-based SQL `CASE` for simple multi-row value mapping.
26. Never use exceptions as routine `IF` branches.
27. Test `NULL`, `FALSE`, and `TRUE` separately for nullable Booleans.
28. Test boundary values 0, 100, and 1000.
29. Test out-of-catalog status values.
30. Test retries and idempotency.
31. Test concurrent sessions updating the same row where concurrency applies.
32. Verify both `RETURN` values and persisted database state after transactions.
33. Ensure every path in a scalar function executes `RETURN` or `RAISE`.
34. Log cautiously without exposing sensitive data via `NOTICE`.
35. Never run `EXPLAIN (ANALYZE)` on production DML thinking it is read-only.

---

## 31. Summary

`IF` and `CASE` are the two most important conditional constructs in PL/pgSQL:

- **`IF`** suits guard clauses, validation, and compound conditions; `ELSE` is optional. If the condition evaluates to `NULL`, the `THEN` branch is skipped.
- **Simple `CASE`** suits matching **one expression** against discrete values. Multiple comma-separated values can share a `WHEN`.
- **Searched `CASE`** suits numeric ranges, multiple Boolean predicates, and prioritized conditions.
- **PL/pgSQL `CASE` statements** end with `END CASE;` and raise `CASE_NOT_FOUND` if no branch matches and `ELSE` is omitted.
- **SQL `CASE` expressions** end with `END`, return a value, and return `NULL` when `ELSE` is omitted. They are usually better suited for set-based `SELECT`/`UPDATE` operations.

When branching on queried data, check `FOUND` immediately, distinguish missing rows from NULL values, protect state transitions with appropriate concurrency controls, and use `RAISE EXCEPTION` when invalid operations must be rejected. For retries, design "already processed" branches deliberately so repeated requests never silently overwrite timestamps or double-apply business effects.

**Self-check question:** Given a `NULL` input, an unrecognized status, and two concurrent transactions updating the same row, which branch does your code take, what value or error does it return, and do committed rows remain consistent? If you can answer concretely for all three scenarios, you understand how to use `IF` and `CASE` safely in PL/pgSQL.

### Official PostgreSQL Documentation

- [PL/pgSQL — Conditional Statements](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-CONDITIONALS).
- [PL/pgSQL — Structure of PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-structure.html).
- [PL/pgSQL — Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html).
- [PL/pgSQL — Statements Executing a Query](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-SQL-ONEROW).
- [PL/pgSQL — Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html).
- [PL/pgSQL — Trapping Errors](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING).
- [SQL Conditional Expressions — CASE, COALESCE, NULLIF](https://www.postgresql.org/docs/current/functions-conditional.html).
- [Comparison Functions and Operators — NULL](https://www.postgresql.org/docs/current/functions-comparison.html).
- [SQL Syntax — Value Expressions](https://www.postgresql.org/docs/current/sql-expressions.html).
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html).
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html).
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
