# RETURN, RETURN NEXT, and RETURN QUERY in PL/pgSQL

## 1. Three Statements Sharing the Keyword RETURN with Different Meanings

In PostgreSQL, PL/pgSQL lets you write functions with local variables, conditionals, loops, and SQL statements. When a function needs to return results, three forms commonly appear:

```sql
RETURN expression;
RETURN NEXT expression;
RETURN QUERY SELECT ...;
```

At first glance, all three look like "returning data." However, they differ in **function declaration type**, **number of rows returned**, and most importantly **control flow**.

Suppose you are writing an employee lookup feature:

- Need to return **one integer** representing the total active headcount → `RETURN expression`.
- Need to loop over employees and append each qualifying person to a result set → `RETURN NEXT` inside a `RETURNS SETOF ...` function.
- Need to take multiple rows directly from a `SELECT` query and emit them into the result set → `RETURN QUERY SELECT ...`.

Mechanism:

```text
FUNCTION returning a single value
    |
    +-- RETURN expression
           |
           +-- evaluate expression
           +-- terminate function immediately

FUNCTION returning a multi-row set (SETOF / RETURNS TABLE)
    |
    +-- RETURN NEXT [expression]
    |      |
    |      +-- append one row
    |      +-- continue executing next statement
    |
    +-- RETURN QUERY <query>
    |      |
    |      +-- append 0, 1, or many rows from query
    |      +-- continue executing next statement
    |
    +-- RETURN;
           |
           +-- finish building the result set
```

**Fundamental rule:** `RETURN NEXT` and `RETURN QUERY` **do not exit the function immediately**. They append rows to the result set being built. A bare `RETURN;` with no expression ends a set-returning function once all rows have been added.

### Lesson Objectives

After this lesson, you can:

1. Write `RETURN expression` for functions returning a single value.
2. Distinguish `RETURN NULL`, `RETURN;`, and returning 0 rows.
3. Use early `RETURN` inside `IF`/`CASE` branches.
4. Understand `RETURN;` in functions with `OUT`/`INOUT` parameters.
5. Write `RETURNS SETOF scalar` functions using `RETURN NEXT`.
6. Write `RETURNS TABLE(...)` functions using argumentless `RETURN NEXT;`.
7. Use `RETURN NEXT` with composite row variables.
8. Write `RETURN QUERY SELECT ...` to return multiple rows in a set-based manner.
9. Combine multiple `RETURN QUERY` statements, or mix `RETURN NEXT` and `RETURN QUERY`, in one function.
10. Write `RETURN QUERY EXECUTE ... USING ...` for safe parameterized dynamic SQL.
11. Understand `FOUND` behavior after `RETURN QUERY` and the limits of `RETURN NEXT`.
12. Resolve return-type mismatches, including `count(*)` returning `bigint`.
13. Distinguish `RETURNS TABLE`, `RETURNS SETOF composite`, and `RETURNS SETOF record`.
14. Use set-returning functions in `FROM`, `JOIN LATERAL`, and filtered queries.
15. Understand materialization in PL/pgSQL set-returning functions and its impact on `LIMIT` and memory.
16. Design volatility, security, cost, and maintainability properly when returning result sets.

---

## 2. Quick Comparison Table

| Characteristic | `RETURN expression` | `RETURN NEXT` | `RETURN QUERY` |
|---|---|---|---|
| Primarily used in | Functions returning one value/row | Set-returning functions | Set-returning functions |
| Rows contributed | Scalar/single-row function result | One element/row per call | 0 or more rows from a query |
| Exits function immediately? | **Yes** | **No** | **No** |
| Can execute multiple times per call? | No, stops on first execution | Yes | Yes |
| Used with `RETURNS SETOF`? | Do not use `RETURN expression` to end a set | Yes | Yes |
| Used with `RETURNS TABLE`? | Use bare `RETURN;` to finish | Yes, **with no expression** | Yes |
| Requires a SELECT? | Optional | Optional | Usually a SELECT or EXECUTE |
| Convenient for table queries? | No | Yes, but requires a loop | Usually most convenient |
| Typical ending statement | Ends itself | `RETURN;` after loop | `RETURN;` after query |

A concise mental model:

```text
RETURN x;       -> "Here is my single result. I am done."
RETURN NEXT x;  -> "Append x to the result set. I keep running."
RETURN QUERY q; -> "Append all rows of q to the result set. I keep running."
RETURN;         -> "Finish without supplying a new expression."
```

**Warning:** Bare `RETURN;` with no expression is valid only in specific routines such as `RETURNS void`, functions with output parameters, set-returning functions, or procedures. Never use it in place of `RETURN integer_expression` in an ordinary `RETURNS integer` function.

## 3. Preparing the PL/pgSQL Environment

These examples are intended for a learning PostgreSQL database. Never run the lesson's DDL or data updates in production.

Check version and search path:

```sql
SHOW server_version;
SHOW search_path;
```

Create a dedicated schema:

```sql
CREATE SCHEMA IF NOT EXISTS pl358;
```

PostgreSQL supports `LANGUAGE plpgsql` across all modern versions. The routines below use schema `pl358.` to avoid colliding with objects outside the lab.

### 3.1. PL/pgSQL Function: Basic Skeleton

```sql
CREATE FUNCTION schema_name.function_name(
    p_input integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_result integer;
BEGIN
    v_result := p_input * 2;
    RETURN v_result;
END;
$$;
```

- `DECLARE` declares local variables.
- `BEGIN ... END` is a PL/pgSQL block; its `BEGIN` **does not** start an SQL transaction.
- `:=` assigns to a PL/pgSQL variable.
- `RETURN` terminates the function.

## 4. Creating the Employee Dataset Used Throughout the Lesson

We will have departments and employees, some of whom are inactive.

### 4.1. Departments Table

```sql
CREATE TABLE pl358.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL UNIQUE
);
```

### 4.2. Employees Table

```sql
CREATE TABLE pl358.employees (
    employee_id integer PRIMARY KEY,
    department_id integer NOT NULL
        REFERENCES pl358.departments(department_id),
    full_name text NOT NULL,
    monthly_salary numeric(12, 2) NOT NULL
        CHECK (monthly_salary >= 0),
    is_active boolean NOT NULL DEFAULT true,
    hired_on date NOT NULL
);
```

### 4.3. Sample Data

```sql
INSERT INTO pl358.departments(
    department_id, department_name
)
VALUES
    (10, 'Engineering'),
    (20, 'Sales'),
    (30, 'Support'),
    (40, 'Research');

INSERT INTO pl358.employees(
    employee_id,
    department_id,
    full_name,
    monthly_salary,
    is_active,
    hired_on
)
VALUES
    (101, 10, 'An',    2200.00, true,  DATE '2024-01-10'),
    (102, 10, 'Binh',  2900.00, true,  DATE '2023-03-11'),
    (103, 10, 'Chi',   3100.00, false, DATE '2022-05-08'),
    (104, 20, 'Dung',  2500.00, true,  DATE '2024-06-15'),
    (105, 20, 'Ha',    1600.00, true,  DATE '2025-02-20'),
    (106, 30, 'Lan',   2100.00, true,  DATE '2024-09-01'),
    (107, 30, 'Minh',  1800.00, false, DATE '2025-01-17'),
    (108, 30, 'Phuong',1700.00, true,  DATE '2025-08-05');
```

### 4.4. Inspect the Dataset

```sql
SELECT
    d.department_name,
    e.employee_id,
    e.full_name,
    e.monthly_salary,
    e.is_active
FROM pl358.employees AS e
JOIN pl358.departments AS d
    ON d.department_id = e.department_id
ORDER BY d.department_id, e.employee_id;
```

The dataset contains:

- Engineering: 2 active, 1 inactive.
- Sales: 2 active.
- Support: 2 active, 1 inactive.
- Research: no employees yet.

These fixed counts let you predict outputs before running functions.

## 5. RETURN expression: Terminate and Return One Value

Create a doubling function:

```sql
CREATE OR REPLACE FUNCTION pl358.double_number(
    p_number integer
)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_number * 2;
END;
$$;
```

Call it:

```sql
SELECT pl358.double_number(21) AS result;
```

Expected result:

```text
result
------
42
```

When `RETURN p_number * 2;` executes:

1. PostgreSQL evaluates the expression to the declared return type.
2. Returns the value to the caller.
3. Immediately ends function execution.

### 5.1. Statements After RETURN Do Not Execute

```sql
CREATE OR REPLACE FUNCTION pl358.return_stops_execution()
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Before RETURN';
    RETURN 7;
    RAISE NOTICE 'After RETURN';
END;
$$;
```

Call it:

```sql
SELECT pl358.return_stops_execution();
```

The returned integer is `7`. The **"After RETURN"** notice is never emitted because the function has already terminated.

Never place a `RAISE NOTICE` after `RETURN` expecting post-processing to occur.

## 6. Early RETURN in IF/ELSIF/ELSE

A salary-grading function:

```sql
CREATE OR REPLACE FUNCTION pl358.salary_grade(
    p_salary numeric
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_salary IS NULL THEN
        RETURN 'UNKNOWN';
    END IF;

    IF p_salary >= 2800 THEN
        RETURN 'HIGH';
    ELSIF p_salary >= 2000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LOW';
    END IF;
END;
$$;
```

Example:

```sql
SELECT
    pl358.salary_grade(3000) AS grade_3000,
    pl358.salary_grade(2200) AS grade_2200,
    pl358.salary_grade(1500) AS grade_1500,
    pl358.salary_grade(NULL::numeric) AS grade_null;
```

Expected results:

| Input | Return Value |
|---|---|
| 3000 | HIGH |
| 2200 | MEDIUM |
| 1500 | LOW |
| NULL | UNKNOWN |

### 6.1. Early RETURN Reduces Nesting

Instead of:

```text
IF valid
  IF case A
     ...
  ELSE
     ...
  END IF
ELSE
  ...
END IF
```

you can check early-exit conditions upfront:

```sql
IF invalid_input THEN
    RETURN fallback_value;
END IF;
```

However, early return is appropriate only when you truly want to **exit the entire function immediately**, not when a set-returning function must continue adding rows.

## 7. Scalar Functions Must Have Valid Return Paths

Consider a buggy function:

```sql
-- Example intentionally missing a RETURN path:
CREATE FUNCTION pl358.missing_return(
    p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value > 0 THEN
        RETURN p_value;
    END IF;
END;
$$;
```

For positive inputs, it hits `RETURN`. For `p_value <= 0` or `NULL`, control reaches `END` without returning a value.

When that path executes, PL/pgSQL raises an error:

```text
control reached end of function without RETURN
```

### 7.1. Clear Fix

```sql
CREATE OR REPLACE FUNCTION pl358.missing_return(
    p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value > 0 THEN
        RETURN p_value;
    END IF;

    RETURN 0;
END;
$$;
```

Now every execution path ends with `RETURN expression`.

### 7.2. NULL in IF

In PL/pgSQL, an `IF expression THEN` branch runs only when `expression` evaluates to `TRUE`. `FALSE` or `NULL` skips the `THEN` branch.

Always decide explicitly what `p_value = NULL` means rather than letting it fall through to the end of the function.

## 8. RETURN NULL, RETURN 0, and RAISE EXCEPTION

These three options are not equivalent.

```sql
RETURN NULL;
```

makes the scalar function return **SQL NULL**.

```sql
RETURN 0;
```

returns the numeric value `0`.

```sql
RAISE EXCEPTION 'Invalid input';
```

raises an error and aborts execution under exception/transaction semantics unless caught by a handler.

### 8.1. Input-Validation Example

```sql
CREATE FUNCTION pl358.safe_percentage(
    p_amount numeric,
    p_total numeric
)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_total IS NULL OR p_total = 0 THEN
        RETURN NULL;
    END IF;

    IF p_amount IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN round(p_amount * 100 / p_total, 2);
END;
$$;
```

### 8.2. Do Not Return NULL Instead of Raising When Business Rules Require Rejection

If a zero total represents invalid data rather than "undefined percentage," use `RAISE EXCEPTION` with an appropriate SQLSTATE.

What matters is a clear contract: **NULL is a valid data result**, not synonymous with an exception.

## 9. RETURN in RETURNS void Functions

Some functions perform side-effecting work or logging without returning meaningful data to the caller.

Example:

```sql
CREATE FUNCTION pl358.print_department(
    p_department_id integer
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Department ID: %', p_department_id;
    RETURN;
END;
$$;
```

Call it:

```sql
SELECT pl358.print_department(10);
```

Here:

```sql
RETURN;
```

exits a `RETURNS void` function with no expression.

**Do not confuse** this with `RETURN NEXT;`, which appends a row to a set-returning function's output.

## 10. RETURN with OUT Parameters

A function with `OUT` parameters assigns results to its output variables and exits with an **expressionless `RETURN;`**.

Example counting active staff and summing salaries:

```sql
CREATE FUNCTION pl358.department_pay_summary(
    p_department_id integer,
    OUT active_count bigint,
    OUT salary_total numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    SELECT
        count(*),
        coalesce(sum(e.monthly_salary), 0)
    INTO
        active_count,
        salary_total
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.department_pay_summary(10);
```

Expected result:

| active_count | salary_total |
|---:|---:|
| 2 | 5100.00 |

### 10.1. Why Not Write RETURN (active_count, salary_total)?

In a function with `OUT` parameters, the output variables themselves hold the return values. In PL/pgSQL, `RETURN` in this form takes no expression, unlike a scalar `RETURNS numeric` function.

### 10.2. RETURN; Can Also Exit Early

For instance, after initializing `OUT` variables:

```sql
active_count := 0;
salary_total := 0;

IF p_department_id IS NULL THEN
    RETURN;
END IF;
```

The function returns whatever values the output variables hold when `RETURN;` runs. Always initialize all output variables per contract before an early `RETURN;`.

### 10.3. INOUT Is Also an Output Parameter

`INOUT` receives an input value and returns an output value. In PL/pgSQL functions using `OUT`/`INOUT`, the expressionless `RETURN;` rule also applies.

## 11. Scalar RETURN and Calling Functions in SELECT

Scalar-returning functions can be called directly in SQL expressions:

```sql
SELECT
    e.employee_id,
    e.full_name,
    pl358.salary_grade(e.monthly_salary)
        AS salary_grade
FROM pl358.employees AS e
ORDER BY e.employee_id;
```

Each row gets its corresponding salary grade.

### 11.1. When Is PL/pgSQL Unnecessary?

If the logic is just a simple expression, a `LANGUAGE sql` function or an inline `CASE` in the query can be simpler:

```sql
SELECT
    CASE
        WHEN e.monthly_salary >= 2800 THEN 'HIGH'
        WHEN e.monthly_salary >= 2000 THEN 'MEDIUM'
        ELSE 'LOW'
    END
FROM pl358.employees AS e;
```

Choose PL/pgSQL when you need conditionals, local variables, loops, or procedural logic—not because every formula requires `BEGIN`/`END`.

---

## 12. Moving to Set-Returning Functions: RETURNS SETOF

`RETURNS SETOF type` declares a function that can return **zero, one, or many values/rows** of type `type`.

Example:

```sql
CREATE FUNCTION pl358.active_employee_ids(
    p_department_id integer
)
RETURNS SETOF integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id integer;
BEGIN
    FOR v_id IN
        SELECT e.employee_id
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        RETURN NEXT v_id;
    END LOOP;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.active_employee_ids(10);
```

Expected result:

```text
active_employee_ids
-------------------
101
102
```

### 12.1. Three Steps of the Function

1. Iterate over matching `employee_id`s.
2. Each `RETURN NEXT v_id;` appends **one integer element** to the returned set.
3. `RETURN;` ends the function after the loop finishes.

### 12.2. RETURN NEXT Does Not Break Out of the Loop

This is a key difference from a scalar function's `RETURN v_id;`.

If mistakenly written as:

```sql
-- Invalid for a SETOF function in this example:
RETURN v_id;
```

that does not "return one row and continue looping." In set-returning PL/pgSQL functions, use `RETURN NEXT` or `RETURN QUERY`.

## 13. RETURN NEXT Can Emit Multiple Values from a Loop

A simple number-generating function:

```sql
CREATE FUNCTION pl358.numbers_up_to(
    p_max integer
)
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number integer;
BEGIN
    IF p_max IS NULL OR p_max < 1 THEN
        RETURN;
    END IF;

    FOR v_number IN 1..p_max LOOP
        RETURN NEXT v_number;
    END LOOP;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.numbers_up_to(4);
```

Result:

```text
numbers_up_to
-------------
1
2
3
4
```

### 13.1. Empty Set When There Are No Results

```sql
SELECT *
FROM pl358.numbers_up_to(0);
```

Returns **0 rows**, not one row containing `NULL` or `0`.

### 13.2. Use generate_series When Simpler

PostgreSQL already provides built-in series generation:

```sql
SELECT * FROM generate_series(1, 4);
```

Do not write custom PL/pgSQL loops for built-in set-based operations just to use `RETURN NEXT`. The example above is purely for learning control flow.

## 14. Returning One Row Containing NULL vs. Returning an Empty Set

A set-returning integer function can intentionally emit **one NULL element**:

```sql
CREATE FUNCTION pl358.one_nullable_integer()
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN NEXT NULL::integer;
    RETURN;
END;
$$;
```

```sql
SELECT * FROM pl358.one_nullable_integer();
```

Result: **1 row** containing SQL `NULL`.

Compare with:

```sql
CREATE FUNCTION pl358.no_integer_rows()
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN;
END;
$$;
```

```sql
SELECT * FROM pl358.no_integer_rows();
```

Result: **0 rows**.

### 14.1. Why Does This Distinction Matter?

In a report:

- **0 rows** can mean "no matching records exist."
- **1 row with a NULL column** can mean "a result exists, but its value is unknown."

Never substitute one for the other merely to make a UI render a blank row.

## 15. RETURN NEXT with Composite Row Variables

A function can return full rows matching a defined table type.

```sql
CREATE FUNCTION pl358.active_employee_rows(
    p_department_id integer
)
RETURNS SETOF pl358.employees
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_employee pl358.employees%ROWTYPE;
BEGIN
    FOR v_employee IN
        SELECT e.*
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        RETURN NEXT v_employee;
    END LOOP;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT
    x.employee_id,
    x.full_name,
    x.monthly_salary
FROM pl358.active_employee_rows(10) AS x
ORDER BY x.employee_id;
```

Expected result: employees 101 and 102.

### 15.1. What Role Does %ROWTYPE Play?

`v_employee pl358.employees%ROWTYPE;` declares a variable matching the row structure of the `employees` table:

```text
employee_id
department_id
full_name
monthly_salary
is_active
hired_on
```

Because the function declares `RETURNS SETOF pl358.employees`, each `RETURN NEXT v_employee;` emits one validly typed composite row.

### 15.2. Returning a Subset of Columns Does Not Form a Valid Table Row

Selecting only `employee_id, full_name` into an incompatible variable does not produce a complete `pl358.employees` row. Returned records must match the declared return type.

### 15.3. Be Cautious with Table Schema Changes

When a function directly returns a table's row type, altering the table affects API outputs and downstream consumers. For stable long-lived APIs, `RETURNS TABLE` naming only needed public columns is easier to maintain.

## 16. RETURNS TABLE: Declaring a Result Set with Explicit Columns

A function can return a set where every row has three defined columns:

```sql
CREATE FUNCTION pl358.find_active_employees(
    p_department_id integer,
    p_min_salary numeric DEFAULT 0
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.employee_id,
        e.full_name::text,
        e.monthly_salary::numeric
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.find_active_employees(10);
```

Expected result:

| employee_id | employee_name | salary |
|---:|---|---:|
| 101 | An | 2200.00 |
| 102 | Binh | 2900.00 |

Call with a minimum salary:

```sql
SELECT *
FROM pl358.find_active_employees(
    p_department_id => 20,
    p_min_salary => 2000
);
```

Result: Dung, ID 104, salary 2500.00.

### 16.1. RETURNS TABLE Defines Output Columns for the Set

The columns:

```text
employee_id integer
employee_name text
salary numeric
```

are treated by PostgreSQL as output parameters of the result rows and are accessible as PL/pgSQL variables inside the function body.

That is why `RETURN NEXT` syntax with `RETURNS TABLE` differs from `RETURNS SETOF integer`.

## 17. RETURN QUERY: Appending All Rows of a SELECT

The core of the previous example:

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.department_id = p_department_id
  AND e.is_active
ORDER BY e.employee_id;
```

Behavior:

- Executes the `SELECT`.
- Appends all matching rows to the function's **result set**.
- If the `SELECT` yields 0 rows, no rows are added.
- Afterward, **the function continues executing** subsequent statements.

### 17.1. RETURN QUERY Is Not RETURN (SELECT ...)

Semantically invalid:

```sql
-- Not how to return multiple rows in PL/pgSQL SETOF:
RETURN (
    SELECT e.employee_id
    FROM pl358.employees AS e
);
```

Scalar subqueries follow different rules and do not turn `RETURN expression` into a multi-row result. For set-returning PL/pgSQL, use `RETURN QUERY` or `RETURN NEXT`.

### 17.2. RETURN QUERY Needs No PL/pgSQL Loop

Writing:

```sql
RETURN QUERY SELECT ...;
```

is far more concise than iterating row-by-row with:

```sql
FOR v_row IN SELECT ... LOOP
    RETURN NEXT v_row;
END LOOP;
```

Whenever a query already defines the required rows without per-row procedural transformations, prefer the set-based form.

## 18. Argumentless RETURN NEXT; Inside RETURNS TABLE

With `RETURNS TABLE(...)`, output columns are PL/pgSQL variables.

Same logic written as a loop:

```sql
CREATE FUNCTION pl358.find_active_employees_loop(
    p_department_id integer
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_employee pl358.employees%ROWTYPE;
BEGIN
    FOR v_employee IN
        SELECT e.*
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        employee_id := v_employee.employee_id;
        employee_name := v_employee.full_name;
        salary := v_employee.monthly_salary;

        RETURN NEXT;
    END LOOP;

    RETURN;
END;
$$;
```

Notice `RETURN NEXT;` has a **semicolon immediately after NEXT**, with no expression.

### 18.1. Why Not Write RETURN NEXT v_employee?

In `RETURNS TABLE`, the output parameters define each row's structure. Under PL/pgSQL rules, when `OUT` parameters exist, `RETURN NEXT` must be written **without an expression**; it emits the current values of the output variables.

This differs from:

```sql
RETURNS SETOF pl358.employees
...
RETURN NEXT v_employee;
```

because there are no separate output parameters there, so a compatible composite row must be passed.

### 18.2. Assign All Output Variables Before Every RETURN NEXT

If you forget:

```sql
salary := v_employee.monthly_salary;
```

then `salary` retains its value from the previous iteration (or NULL), emitting corrupted data.

Assign **every required output column** on each iteration, or use `RETURN QUERY` when possible.

## 19. Comparing Two Equivalent Set-Returning Patterns

**Approach 1 — Loop + RETURN NEXT:**

```sql
FOR v_employee IN
    SELECT e.*
    FROM pl358.employees AS e
    WHERE e.is_active
LOOP
    employee_id := v_employee.employee_id;
    employee_name := v_employee.full_name;
    salary := v_employee.monthly_salary;
    RETURN NEXT;
END LOOP;
```

**Approach 2 — RETURN QUERY:**

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.is_active;
```

| Criterion | `RETURN NEXT` | `RETURN QUERY` |
|---|---|---|
| Expresses "one row per iteration" | Direct | No |
| Needs loop/output variables | Usually yes | Not required |
| Uses set-based SELECT | Only via FOR | Directly |
| Per-row PL/pgSQL transformation | Easy to express | Usually moved into SQL expressions |
| Combines multiple sources | Yes | Yes |
| Exits function itself | No | No |
| Suited for plain multi-row SQL queries | Verbose | Usually concise |

Do not claim `RETURN QUERY` is always faster without measuring. Design-wise, however, the set-based approach is preferable whenever per-row procedural control is unnecessary.

## 20. Combining Multiple RETURN QUERY Calls in One Function

Because `RETURN QUERY` does not exit the function, you can append multiple groups of results.

Example emitting active employees first, then inactive employees:

```sql
CREATE FUNCTION pl358.employees_by_activity(
    p_department_id integer
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    is_active boolean
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text, e.is_active
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN QUERY
    SELECT e.employee_id, e.full_name::text, e.is_active
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND NOT e.is_active
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

For Engineering, the two branches emit:

- Active: An (101), Binh (102).
- Inactive: Chi (103).

### 20.1. No Implicit UNION Deduplication

Two `RETURN QUERY` statements **append** rows to the result set; they do not deduplicate.

If an employee matched both queries, that row would appear twice.

If you want `DISTINCT`/`UNION`, write it directly in SQL or deduplicate explicitly.

### 20.2. Enforce Display Order at the Call Site

Internal `ORDER BY` clauses shape row production, but **never rely on a function's internal row ordering as an external SQL contract without an `ORDER BY` at the caller**.

Call explicitly:

```sql
SELECT *
FROM pl358.employees_by_activity(10)
ORDER BY is_active DESC, employee_id;
```

to guarantee the final ordering for consumers.

## 21. Combining RETURN NEXT and RETURN QUERY

You can emit a header row first, then query rows.

Example returning text labels:

```sql
CREATE FUNCTION pl358.department_messages(
    p_department_id integer
)
RETURNS SETOF text
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN NEXT
        ('Department=' || p_department_id::text);

    RETURN QUERY
    SELECT
        e.employee_id::text || ':' || e.full_name
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN NEXT 'END';

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.department_messages(10);
```

Values appended along the execution path:

```text
Department=10
101:An
102:Binh
END
```

If stable presentation order is required, include a `sort_key` column and `ORDER BY` in the caller rather than relying solely on append order.

### 21.1. Is Mixing Them Reasonable?

Yes, when the output naturally consists of heterogeneous segments. Still, if you are returning headers, footers, and rows of different shapes, squeezing them into one `text` table is rarely good API design.

Sometimes structured JSON, a separate summary row, or two separate queries is cleaner. Choose the output shape to fit callers.

## 22. RETURN QUERY with JOIN, GROUP BY, and Aggregates

`RETURN QUERY` accepts any `SELECT` returning a compatible row shape, not just single-table queries.

Department summary report example:

```sql
CREATE FUNCTION pl358.department_statistics()
RETURNS TABLE (
    department_id integer,
    department_name text,
    active_count bigint,
    total_salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.department_id,
        d.department_name::text,
        count(e.employee_id)::bigint,
        coalesce(sum(e.monthly_salary), 0)::numeric
    FROM pl358.departments AS d
    LEFT JOIN pl358.employees AS e
        ON e.department_id = d.department_id
       AND e.is_active
    GROUP BY d.department_id, d.department_name
    ORDER BY d.department_id;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.department_statistics()
ORDER BY department_id;
```

Expected result:

| department_id | department_name | active_count | total_salary |
|---:|---|---:|---:|
| 10 | Engineering | 2 | 5100.00 |
| 20 | Sales | 2 | 4100.00 |
| 30 | Support | 2 | 3800.00 |
| 40 | Research | 0 | 0 |

### 22.1. Why Put e.is_active in the ON Clause?

To preserve departments with **zero active employees**, `e.is_active` must stay in the `LEFT JOIN`'s `ON` clause. Moving it to `WHERE e.is_active` would filter out Research because its right-side columns are NULL.

### 22.2. COUNT(e.employee_id) Instead of COUNT(*)

With a `LEFT JOIN`:

- `COUNT(e.employee_id)` counts only matched employees.
- `COUNT(*)` would count the preserved NULL-extended row for Research as `1`.

Count on the right-hand non-NULL key to get `0` accurately for empty departments.

## 23. RETURN QUERY Appends Nothing When SELECT Is Empty

Call:

```sql
SELECT *
FROM pl358.find_active_employees(40);
```

Research has no employees, so `RETURN QUERY SELECT ...` appends **0 rows**.

An empty set does not raise an error. After `RETURN QUERY`, `RETURN;` finishes and returns 0 rows.

### 23.1. Do Not Confuse Empty Sets with Scalar NULL

```sql
SELECT pl358.safe_percentage(10, 0);
```

returns **1 row containing scalar NULL**.

```sql
SELECT *
FROM pl358.find_active_employees(40);
```

returns **0 rows**.

### 23.2. When a Default Status Row Is Desired

If business logic wants a row saying "no data," design an explicit status contract—such as `result_status text` plus a count column—or return a structured JSON object.

Never inject a fake row with `employee_id = NULL` into an employee set without an explicit API contract, as it breaks downstream `COUNT` and `JOIN` expectations.

## 24. The Special Variable FOUND After RETURN QUERY

PL/pgSQL maintains the boolean `FOUND` variable inside function execution.

For `RETURN QUERY`:

- `FOUND = TRUE` if `RETURN QUERY` **appended at least one row**.
- `FOUND = FALSE` if `RETURN QUERY` **appended 0 rows**.

Example:

```sql
CREATE FUNCTION pl358.active_employees_or_message(
    p_department_id integer
)
RETURNS SETOF text
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    IF NOT FOUND THEN
        RETURN NEXT '[NO_ACTIVE_EMPLOYEES]';
    END IF;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.active_employees_or_message(10);
```

returns `An` and `Binh`.

For department 40, the SELECT is empty so `FOUND` is `FALSE`, and the function appends `'[NO_ACTIVE_EMPLOYEES]'`.

### 24.1. Read FOUND Immediately After RETURN QUERY

Other statements such as `SELECT INTO`, `PERFORM`, DML, or `FOR` loop completion overwrite `FOUND`.

Flawed design:

```sql
RETURN QUERY SELECT ...;

PERFORM some_other_operation();

IF FOUND THEN
    -- FOUND now reflects PERFORM,
    -- no longer RETURN QUERY.
END IF;
```

If needed later, capture `FOUND` immediately after `RETURN QUERY`:

```sql
v_had_rows := FOUND;
```

### 24.2. Does RETURN NEXT Update FOUND?

Under PL/pgSQL semantics, `RETURN NEXT` **does not** update `FOUND` the way `RETURN QUERY` does.

Therefore, never write:

```sql
RETURN NEXT x;
IF FOUND THEN ...
```

assuming `FOUND` reports whether a row was emitted. It may still hold the status of an earlier statement.

## 25. RETURN QUERY EXECUTE for Dynamic SQL

`RETURN QUERY` can append rows from an SQL query **built at runtime**:

```sql
RETURN QUERY EXECUTE command_string USING parameter_values;
```

This fits cases where SQL structure changes, such as choosing a sort column from an **allowed whitelist**.

### 25.1. Example: Sorting by a Chosen Column

```sql
CREATE FUNCTION pl358.find_active_sorted(
    p_department_id integer,
    p_sort_column text DEFAULT 'employee_id',
    p_desc boolean DEFAULT false
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_direction text;
BEGIN
    IF p_sort_column IS NULL
       OR p_sort_column NOT IN (
           'employee_id',
           'full_name',
           'monthly_salary'
       ) THEN
        RAISE EXCEPTION 'Unsupported sort column: %',
            p_sort_column
            USING ERRCODE = '22023';
    END IF;

    IF p_desc IS NULL THEN
        RAISE EXCEPTION 'Sort direction must not be NULL'
            USING ERRCODE = '22023';
    END IF;

    v_direction := CASE
        WHEN p_desc THEN 'DESC'
        ELSE 'ASC'
    END;

    RETURN QUERY EXECUTE format(
        'SELECT
             e.employee_id,
             e.full_name::text,
             e.monthly_salary::numeric
         FROM pl358.employees AS e
         WHERE e.department_id = $1
           AND e.is_active
         ORDER BY e.%I %s, e.employee_id ASC',
        p_sort_column,
        v_direction
    )
    USING p_department_id;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.find_active_sorted(
    p_department_id => 10,
    p_sort_column => 'monthly_salary',
    p_desc => true
);
```

Returns two rows ordered from highest salary down:

| employee_id | employee_name | salary |
|---:|---|---:|
| 102 | Binh | 2900.00 |
| 101 | An | 2200.00 |

### 25.2. Why Use format('%I', identifier)?

Column names cannot be bound via `USING` like regular SQL values. `%I` safely quotes an identifier per PostgreSQL rules. Still, the column name must pass a **whitelist** before entering dynamic SQL.

### 25.3. Why Use USING p_department_id?

The `$1` placeholder receives `p_department_id` via `USING`, avoiding unsafe string concatenation of values into SQL.

### 25.4. Why Use %s for ASC/DESC?

`ASC` and `DESC` are SQL keywords, not string values or identifiers. Here `v_direction` is **derived strictly from a Boolean into one of two trusted constants**. Never interpolate unvalidated user strings directly.

## 26. SQL Injection with RETURN QUERY EXECUTE

**Unsafe** anti-pattern shown only as a warning:

```sql
-- NEVER use this pattern with untrusted input:
RETURN QUERY EXECUTE
    'SELECT ... FROM pl358.employees
     WHERE full_name = ''' || p_name || '''';
```

If `p_name` contains quotes or crafted SQL, the query can break or change behavior.

### 26.1. Use USING for Values

Safer pattern:

```sql
RETURN QUERY EXECUTE
    'SELECT
         e.employee_id,
         e.full_name::text,
         e.monthly_salary::numeric
     FROM pl358.employees AS e
     WHERE e.full_name = $1'
USING p_name;
```

### 26.2. Quote and Whitelist Identifiers

`format('%I', p_column)` quotes the identifier. Yet if business logic only permits sorting by three columns, **validate against those three values** first. Proper quoting alone does not prove callers are allowed to read or sort by arbitrary columns.

### 26.3. Security Goes Beyond SQL Injection

A `SECURITY DEFINER` function returning employees for a client-supplied `p_department_id` can still leak data if it fails to verify caller scope and roles. Use schema-qualified names, proper grants, and authorization checks even when dynamic SQL is syntactically safe.

## 27. When to Use RETURN QUERY EXECUTE Instead of RETURN QUERY?

Prefer static SQL whenever only **data values** vary:

```sql
RETURN QUERY
SELECT e.employee_id, e.full_name::text
FROM pl358.employees AS e
WHERE e.department_id = p_department_id;
```

Dynamic SQL is unnecessary for `p_department_id`; PL/pgSQL binds it automatically.

Use dynamic SQL only when **statement structure** must change:

- Sort column.
- Table/partition name chosen from trusted metadata.
- Controlled dynamic column projections.
- Rare plan-shaping cases depending on inputs.

### 27.1. Dynamic SQL Has Overhead

Dynamic `EXECUTE` builds strings, parses/plans at runtime, and is harder to validate statically. Never adopt it just for optional filter predicates.

### 27.2. Dynamic SQL Does Not Bypass Output Type Matching

Even with dynamic queries, returned rows must still **match the function's declared `RETURN` type**. A `RETURNS TABLE(id integer, name text)` function cannot dynamically return 2 columns on one call and 5 on another without a matching contract.

## 28. Set-Returning Functions Can Exit Early with RETURN;

Suppose negative salary filters are disallowed:

```sql
CREATE FUNCTION pl358.find_active_min_salary(
    p_min_salary numeric
)
RETURNS TABLE (
    employee_id integer,
    employee_name text
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_min_salary IS NULL OR p_min_salary < 0 THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.is_active
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

For negative or NULL `p_min_salary`, `RETURN;` terminates the function and yields an **empty set**.

### 28.1. Return Empty Set or Raise an Error?

Returning empty here is just an **illustrative convention**, not a universal best practice.

If negative input is a business error, raising an exception is often better:

```sql
IF p_min_salary IS NULL OR p_min_salary < 0 THEN
    RAISE EXCEPTION 'Invalid minimum salary'
        USING ERRCODE = '22023';
END IF;
```

Clearly distinguish:

- No matching records.
- Invalid input.
- Unauthorized caller.
- System failure.

Avoid collapsing all four into "0 rows," which leaves callers guessing what went wrong.

## 29. Runtime Row Type: RETURNS TABLE Requires Exact Type Matching

A common error:

```text
ERROR: structure of query does not match function result type
```

For example, if the function declares:

```sql
RETURNS TABLE (
    department_id integer,
    active_count integer
)
```

but the query runs:

```sql
SELECT
    e.department_id,
    count(*)
FROM pl358.employees AS e
GROUP BY e.department_id;
```

`count(*)` returns **`bigint`**, not `integer`.

### 29.1. Best Fix: Declare the Output Column as bigint

```sql
CREATE FUNCTION pl358.count_employees_by_department()
RETURNS TABLE (
    department_id integer,
    employee_count bigint
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.department_id, count(*)
    FROM pl358.employees AS e
    GROUP BY e.department_id
    ORDER BY e.department_id;

    RETURN;
END;
$$;
```

Now the output type matches `count(*)`.

### 29.2. If integer Is Truly Required

You can cast:

```sql
count(*)::integer
```

but remember `bigint → integer` overflows if counts exceed 32-bit integer bounds. Never cast blindly just to silence a type error without checking data bounds.

## 30. varchar, text, numeric, and Easily Confused Types

PostgreSQL has types that look similar when printed yet have distinct row descriptors.

For example, a column:

```sql
product_name varchar(100)
```

and function output:

```sql
RETURNS TABLE(product_name text)
```

With `RETURN QUERY SELECT product_name`, PL/pgSQL set-returning functions raise a structure mismatch if the query yields `character varying` while the signature expects `text`.

Explicit fix:

```sql
RETURN QUERY
SELECT p.product_name::text
FROM schema_name.products AS p;
```

### 30.1. Do Not Expect Scalar Implicit Coercion

When assigning to a single scalar variable, PostgreSQL applies assignment casts. `RETURN QUERY`, however, returns **rows with a strict row descriptor** that must match the return declaration. Never assume "similar-looking" types auto-coerce in multi-column results.

### 30.2. numeric(12,2) vs. numeric

Column `monthly_salary numeric(12,2)` has base type `numeric`. Our examples cast `::numeric` explicitly for clarity; the main lesson is to verify the exact type of every expression in the `SELECT`.

### 30.3. Matching Column Count Can Still Fail

If a function declares:

```text
(employee_id integer, employee_name text, salary numeric)
```

while `SELECT` returns:

```text
(full_name text, employee_id integer, monthly_salary numeric)
```

the **column order is wrong** even though counts and names look similar. PostgreSQL matches result columns by position and type, not by column name.

## 31. Output Variable Names Can Cause Ambiguous Column Reference Errors

In `RETURNS TABLE(employee_id integer, employee_name text)`, `employee_id` becomes a PL/pgSQL output variable.

If the query writes:

```sql
RETURN QUERY
SELECT employee_id, full_name
FROM pl358.employees;
```

PL/pgSQL cannot tell whether `employee_id` inside the `SELECT` refers to:

- Table column `employees.employee_id`.
- Output variable `employee_id` of the function.

This raises:

```text
column reference "employee_id" is ambiguous
```

### 31.1. Fix: Use Clear Table Aliases

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text
FROM pl358.employees AS e;
```

Now output parameter names never collide with `e.employee_id`.

### 31.2. Naming Convention Suggestions

- `p_`: input parameters.
- `v_`: local variables.
- `e.`, `d.`: table aliases.
- Output columns: clear business names.

Never rely on `plpgsql.variable_conflict` settings to mask ambiguity; qualifying columns with aliases is safer and easier to maintain.

## 32. RETURNS SETOF record: Flexible, but Callers Must Specify Structure

Sometimes a function returns a set of records without declaring fixed columns in `RETURNS TABLE`.

Example:

```sql
CREATE FUNCTION pl358.staff_record(
    p_department_id integer
)
RETURNS SETOF record
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Because the return type is generic `record`, callers must provide a column definition list:

```sql
SELECT *
FROM pl358.staff_record(10)
AS s(employee_id integer, full_name text);
```

### 32.1. Do Not Mistake record for "Any Schema Works"

Returned rows must still match the column list declared by the caller. If the function yields `(integer, text)` and the caller declares three columns or mismatched types, PostgreSQL raises an error.

### 32.2. When to Use record?

Suited for generic metadata or utility functions whose shape genuinely depends on caller expectations. For application APIs with stable column contracts, `RETURNS TABLE` or an explicit composite type is much easier to consume.

## 33. RETURNS TABLE, SETOF scalar, SETOF composite, and SETOF record

| Declaration | Example | Appropriate Return Syntax |
|---|---|---|
| `RETURNS integer` | A count | `RETURN 10;` |
| `RETURNS text` | A string | `RETURN 'OK';` |
| `RETURNS void` | No return payload | `RETURN;` |
| `OUT x integer, OUT y text` | One output record | Assign `x`/`y`, then `RETURN;` |
| `RETURNS SETOF integer` | Stream of integers | `RETURN NEXT x;` or `RETURN QUERY SELECT ...` |
| `RETURNS SETOF pl358.employees` | Multiple composite rows | `RETURN NEXT v_employee;` or `RETURN QUERY SELECT e.* ...` |
| `RETURNS TABLE(id int, name text)` | Fixed result table | Assign outputs then `RETURN NEXT;`, or `RETURN QUERY SELECT ...` |
| `RETURNS SETOF record` | Caller-described records | `RETURN NEXT v_record;` or `RETURN QUERY ...`; caller specifies columns |

### 33.1. RETURNS TABLE Is Not a Physical Table

A `RETURNS TABLE(...)` function does not create a physical table in the schema. It declares the **shape of the returned set**. Rows are returned dynamically on call and not persisted without separate DML.

### 33.2. Never Change Return Types Without Migration

If views, ORMs, or applications depend on three output columns, adding a fourth or changing types breaks consumers. PostgreSQL also restricts changing return types via `CREATE OR REPLACE FUNCTION`. Treat return signatures as API contracts.

## 34. Does RETURN Differ in Procedures and Triggers?

This lesson focuses on **PL/pgSQL functions**, yet `RETURN` also appears in procedures and triggers.

### 34.1. Procedures

Procedures are invoked via `CALL` and can exit early using:

```sql
RETURN;
```

Never use `RETURN QUERY` to return a table set from a procedure like a `RETURNS TABLE` function. Procedure `OUT`/`INOUT` handling follows different call and version rules.

### 34.2. Trigger Functions

A trigger function:

```sql
RETURNS trigger
```

typically returns:

```sql
RETURN NEW;
```

or:

```sql
RETURN OLD;
```

or `NULL` depending on the trigger type and intent.

In a **BEFORE ROW** trigger, the return value determines whether row processing proceeds or is skipped; other trigger types have specific return semantics.

Never write `RETURN NEXT NEW;` inside an ordinary trigger function as if triggers returned sets of records.

### 34.3. Identify the Return Declaration First

Before choosing a `RETURN` form, always check:

```text
RETURNS scalar?
RETURNS void?
RETURNS trigger?
RETURNS SETOF type?
RETURNS TABLE(...)?
PROCEDURE ...?
```

The valid `RETURN` syntax depends directly on the declared routine contract.

## 35. FOUND, SELECT INTO, and RETURN QUERY: Keep Roles Separate

A scalar function often reads:

```sql
SELECT e.full_name
INTO v_name
FROM pl358.employees AS e
WHERE e.employee_id = p_employee_id;

IF NOT FOUND THEN
    RETURN NULL;
END IF;

RETURN v_name;
```

This flow **fetches one value** via `SELECT INTO`, checks `FOUND`, and `RETURN`s.

A set-returning function might read:

```sql
RETURN QUERY
SELECT e.full_name
FROM pl358.employees AS e
WHERE e.department_id = p_department_id;

IF NOT FOUND THEN
    RETURN NEXT '[NO_EMPLOYEES]';
END IF;
```

This flow **emits a set** via `RETURN QUERY`, checks `FOUND`, and appends a fallback row per policy.

### 35.1. SELECT INTO Is Not RETURN QUERY

`SELECT ... INTO variable` assigns a row into PL/pgSQL variables; it does not append rows to a `RETURNS TABLE` output set.

### 35.2. PERFORM Is Not RETURN QUERY

`PERFORM query;` executes a query and discards its rows. To append query rows to a function's result set, use `RETURN QUERY`.

### 35.3. EXECUTE ... INTO vs. RETURN QUERY EXECUTE

`EXECUTE dynamic_sql INTO variable USING ...` stores values into variables. `RETURN QUERY EXECUTE dynamic_sql USING ...` appends dynamic query rows to the function's result set.

## 36. Materialization: RETURN NEXT Does Not Stream Row-by-Row to Clients

A crucial PL/pgSQL performance characteristic:

> In PostgreSQL's current implementation, results of PL/pgSQL set-returning functions using `RETURN NEXT` and `RETURN QUERY` are **accumulated/materialized before the function finishes**, rather than streaming each row to the caller immediately on each `RETURN NEXT`.

Diagram:

```text
Caller SELECT * FROM function()
             |
             v
PL/pgSQL function executes
   |
   +-- RETURN NEXT row A  --> appended to tuplestore
   +-- RETURN NEXT row B  --> appended to tuplestore
   +-- RETURN QUERY ...   --> appended to tuplestore
   |
   +-- RETURN; / reaches END
             |
             v
Caller receives the result set from the function
```

### 36.1. work_mem and Large Datasets

For large result sets, PostgreSQL spills the temporary tuplestore to disk once memory exceeds limits related to `work_mem`.

Never assume from the keyword `RETURN NEXT` that the client immediately receives the first row while the loop is still running.

### 36.2. An Outer LIMIT Does Not Guarantee Less Work Inside the Function

The query:

```sql
SELECT *
FROM pl358.active_employee_rows(10)
LIMIT 1;
```

does not guarantee the PL/pgSQL function fetches one employee and stops after the first `RETURN NEXT`. Due to materialization, the function can build the entire set internally before the caller applies `LIMIT`.

If you truly need bounded work, pass `p_limit` into the function and apply `LIMIT` inside its query or loop.

### 36.3. When True Streaming Is Needed

Consider:

- Plain SQL queries with `LIMIT` or keyset pagination.
- Cursors / `refcursor` where transaction and driver architecture allow.
- Batch processing.
- Set-returning SQL functions with appropriate inlining characteristics.
- Returning small pages rather than massive sets.

Never assume every SRF streams rows just because the syntax says `RETURN NEXT`.

## 37. Pushing LIMIT Inside the Function's Query

Example of a multi-row function accepting a caller-specified limit:

```sql
CREATE FUNCTION pl358.top_active_employees(
    p_department_id integer,
    p_limit integer DEFAULT 10
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 100'
            USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    SELECT
        e.employee_id,
        e.full_name::text,
        e.monthly_salary::numeric
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.monthly_salary DESC, e.employee_id
    LIMIT p_limit;

    RETURN;
END;
$$;
```

Call it:

```sql
SELECT *
FROM pl358.top_active_employees(10, 1);
```

Returns **one row**: Binh (salary 2900).

### 37.1. Inner LIMIT vs. Outer LIMIT

- `LIMIT p_limit` inside `RETURN QUERY` caps the rows the function builds.
- `LIMIT 1` in the caller only caps rows returned to the outer query without reducing internal materialization work.

### 37.2. ORDER BY Needs a Tie-Breaker

If two employees share the same salary, `ORDER BY monthly_salary DESC` alone is nondeterministic. Add `employee_id` as a tie-breaker for stable pagination.

### 37.3. Need Deep Pagination?

Large `OFFSET` values can be expensive; use keyset pagination on `(salary, employee_id)` matching the sort direction. Pass cursor/keyset arguments into the function rather than returning every row for client-side slicing.

## 38. RETURN QUERY vs. SQL Function for a Simple SELECT?

PL/pgSQL function:

```sql
CREATE FUNCTION pl358.staff_plpgsql(
    p_department_id integer
)
RETURNS TABLE(employee_id integer, employee_name text)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id;
END;
$$;
```

Conceptually equivalent SQL function:

```sql
CREATE FUNCTION pl358.staff_sql(
    p_department_id integer
)
RETURNS TABLE(employee_id integer, employee_name text)
LANGUAGE sql
STABLE
AS $$
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id;
$$;
```

### 38.1. When to Use LANGUAGE sql?

- The body is a single simple query.
- No procedural `IF`, loops, local variables, or exception handling are needed.
- Potential for planner optimization/inlining depending on the function and query.
- Keeps code concise and close to standard SQL.

### 38.2. When to Use PL/pgSQL?

- Multiple business branches.
- Complex input validation.
- Conditionally combining multiple queries.
- Controlled dynamic SQL.
- Working with temporary variables and loops.

### 38.3. Do Not Assume SQL Functions Always Inline

Inlining depends on function attributes, query shape, and the PostgreSQL planner. Measure on real workloads rather than assuming "switching languages automatically makes it faster."

## 39. Volatility: IMMUTABLE, STABLE, and VOLATILE

PostgreSQL volatility categories:

| Category | Usage Guideline |
|---|---|
| `IMMUTABLE` | Always returns the same output for the same inputs, independent of DB state or time |
| `STABLE` | May read database tables, returning consistent results within a single statement's snapshot |
| `VOLATILE` | May vary within a single statement or cause side effects; this is the default |

### 39.1. Pure Computational Functions

`pl358.double_number` or `pl358.salary_grade` can be `IMMUTABLE` when purely deterministic and independent of mutable settings.

### 39.2. Functions Reading the Employees Table

`pl358.find_active_employees` and `pl358.department_statistics` read database tables. `STABLE` fits these examples—never `IMMUTABLE`, because table contents change.

### 39.3. Functions Modifying Data

Any function performing DML or side effects requires an appropriate volatility, normally `VOLATILE`. Never mislabel a function `IMMUTABLE` or `STABLE` just to satisfy an index or coax the optimizer.

### 39.4. RETURN QUERY Alone Does Not Determine Volatility

A pure `RETURN QUERY SELECT 1` differs from `RETURN QUERY SELECT ... FROM pl358.employees`. Volatility describes the **entire routine's behavior**, not the presence of `RETURN QUERY`.

## 40. Default Parameters and Named Notation in Set-Returning Functions

`RETURNS TABLE` functions support default parameters like any other function.

Example:

```sql
CREATE FUNCTION pl358.lookup_staff(
    p_department_id integer,
    p_active_only boolean DEFAULT true,
    p_min_salary numeric DEFAULT 0
)
RETURNS TABLE (
    employee_id integer,
    employee_name text
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND (
          NOT p_active_only
          OR e.is_active
      )
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Call using named notation:

```sql
SELECT *
FROM pl358.lookup_staff(
    p_department_id => 10,
    p_min_salary => 2500
);
```

Because `p_active_only` defaults to `true`, only Binh (102) is returned; Chi (salary 3100) is excluded because she is inactive.

Call including inactive staff:

```sql
SELECT *
FROM pl358.lookup_staff(
    p_department_id => 10,
    p_active_only => false,
    p_min_salary => 2500
);
```

Returns Binh (102) and Chi (103).

### 40.1. Passing NULL Differs from Omitting an Argument

Calling `p_active_only => NULL::boolean` subjects `NOT p_active_only OR e.is_active` to SQL three-valued logic. Define explicitly whether the contract rejects NULL or treats it as a fallback.

Never assume `DEFAULT true` replaces an explicit `NULL` passed by the caller with `true`.

## 41. LATERAL JOIN with Set-Returning Functions

A set-returning function can depend on columns from an outer table via `LATERAL`.

Example listing each department and its active employees:

```sql
SELECT
    d.department_id,
    d.department_name,
    s.employee_id,
    s.employee_name,
    s.salary
FROM pl358.departments AS d
LEFT JOIN LATERAL
    pl358.find_active_employees(d.department_id) AS s
ON true
ORDER BY d.department_id, s.employee_id;
```

### 41.1. Why LEFT JOIN LATERAL?

- Engineering yields 2 rows.
- Sales yields 2 rows.
- Support yields 2 rows.
- Research yields an empty set.

`LEFT JOIN LATERAL ... ON true` preserves the Research row with NULLs in `s.*`.

### 41.2. How Does CROSS JOIN LATERAL Differ?

`CROSS JOIN LATERAL` keeps rows only when the function returns at least one row. Research would disappear.

### 41.3. Beware Hidden N+1 Execution Inside the Database

Calling a function that queries `employees` once per department is fine for a handful of departments, but across tens of thousands of parent rows, repeated per-row function/query calls become expensive.

Whenever possible, a regular set-based `JOIN`/`GROUP BY` query is faster. Verify with `EXPLAIN` on representative data.

## 42. SETOF Functions in SELECT Lists vs. FROM

You may see:

```sql
SELECT pl358.active_employee_ids(10);
```

and:

```sql
SELECT *
FROM pl358.active_employee_ids(10);
```

Set-returning functions in `SELECT` lists have historically had subtle edge cases, especially when combining multiple SRFs. For readable application code, prefer calling them in `FROM`:

```sql
SELECT x.employee_id
FROM pl358.active_employee_ids(10)
AS x(employee_id);
```

### 42.1. Benefits of Calling in FROM

- Every element/row acts as a standard relational source.
- Easy to compose with `JOIN`, `WHERE`, `ORDER BY`, and `LIMIT`.
- Easy to alias columns cleanly.
- Reduces confusion with scalar expressions.
- `LATERAL` expresses row-level correlation cleanly when combining sources.

### 42.2. Never Rely on Ordering Without ORDER BY

SQL sets have no guaranteed intrinsic order. Whenever display or pagination requires order, place `ORDER BY` on the outer query.

## 43. EXPLAIN on Set-Returning Functions

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM pl358.find_active_employees(10, 2000);
```

You will often see a `Function Scan` node. The outer `EXPLAIN` treats the PL/pgSQL function as a single unit and does not automatically display plans for SQL statements executed inside it.

### 43.1. Analyzing the Inner Query

Extract the query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.department_id = 10
  AND e.is_active
  AND e.monthly_salary >= 2000
ORDER BY e.employee_id;
```

Then compare with total function execution time to gauge PL/pgSQL overhead and tuning opportunities.

### 43.2. EXPLAIN ANALYZE Executes Side Effects

`EXPLAIN (ANALYZE)` **executes** the statement to measure it. If a function contains DML or side effects, running `EXPLAIN ANALYZE` triggers those side effects.

Never run it in production just to "inspect the plan" if the function is not strictly read-only.

### 43.3. An Eight-Row Lab Is Not a Performance Benchmark

If a tiny query chooses a Seq Scan over an index, that is normal cost-based planning. Draw performance conclusions only from real workloads or representative data volumes.

## 44. ROWS and COST Hints for Set-Returning Functions

When estimating a function in `FROM`, PostgreSQL considers:

- `COST`: estimated per-row/execution cost.
- `ROWS`: estimated number of rows returned by a set-returning function.

Example declaration:

```sql
ALTER FUNCTION pl358.find_active_employees(
    integer, numeric
)
ROWS 100
COST 100;
```

### 44.1. ROWS Is Not LIMIT

`ROWS 100` **does not limit** the function to returning 100 rows.

It is strictly a planner estimate. If 100,000 rows match, the function still returns 100,000 rows.

To restrict row counts, use `LIMIT` or conditions inside the logic.

### 44.2. Do Not Guess Estimates Blindly

Large mismatches between `ROWS` estimates and actual row counts can mislead the planner into bad join orders or strategies. Measure representative data distributions before tuning hints.

### 44.3. Lowering COST Does Not Make a Function Faster

Lowering the `COST` metadata does not reduce queries, CPU, or I/O. It only alters the optimizer's cost model assumptions when choosing plans.

## 45. Indexing Queries Used Inside RETURN QUERY

Hot query example:

```sql
SELECT
    e.employee_id,
    e.full_name,
    e.monthly_salary
FROM pl358.employees AS e
WHERE e.department_id = 10
  AND e.is_active
  AND e.monthly_salary >= 2000
ORDER BY e.employee_id;
```

On a large table, consider indexes such as:

```sql
CREATE INDEX idx_pl358_employees_active_department_salary
ON pl358.employees(
    department_id,
    monthly_salary
)
WHERE is_active;
```

Or an index tailored for sorting and a different workload:

```sql
CREATE INDEX idx_pl358_employees_department_id
ON pl358.employees(
    department_id,
    employee_id
);
```

### 45.1. Which Index Fits Best?

Consider:

- Equality predicate on `department_id`.
- Selectivity of `is_active` (true/false ratio).
- Range predicate on `monthly_salary`.
- `ORDER BY employee_id`.
- Row count per department.
- Whether queries use `LIMIT`.
- Frequency of salary `INSERT`/`UPDATE` writes.

No single index is optimal for all filter and sort combinations. Verify with `EXPLAIN (ANALYZE, BUFFERS)` and weigh write/storage trade-offs.

### 45.2. RETURN QUERY Does Not Index Its Output

The function returns a virtual table to the caller; it creates no physical index on the materialized output. Indexes exist only on underlying tables or structures you explicitly design.

## 46. Security: Set-Returning Functions Can Also Leak Data

A function:

```sql
CREATE FUNCTION pl358.all_employees()
RETURNS SETOF pl358.employees
...
```

if granted broadly and executed with elevated privileges can expose employees outside what an application intends a user to see.

### 46.1. SECURITY INVOKER vs. SECURITY DEFINER

- By default, functions run with `SECURITY INVOKER` privileges.
- `SECURITY DEFINER` runs with the function owner's privileges per PostgreSQL rules.

When using `SECURITY DEFINER`, carefully audit:

- Who holds `EXECUTE` privileges.
- What privileges the owner holds.
- Whether `search_path` is pinned safely.
- Whether schema and object names are qualified.
- Whether the function validates tenant/role scopes.
- How RLS policies and owner/bypass attributes interact.
- Whether any dynamic SQL risks injection or untrusted identifiers.

### 46.2. RETURN QUERY Does Not Automatically Enforce Business Access Scope

A query:

```sql
RETURN QUERY SELECT * FROM pl358.employees;
```

does not know a caller should see only department 10 unless enforced by RLS policies, `WHERE` predicates, and access controls.

### 46.3. Never Trust a Client-Supplied Parameter as Authorization

If `p_department_id` comes from the client, `WHERE department_id = p_department_id` does not prove the caller is authorized to view that department.

In production, tie scoping to verified authenticated roles/claims and enforce RLS and authorization properly.

### 46.4. Return Only Required Columns

If you only need names and IDs, never declare `RETURNS SETOF employee_record` exposing salaries and sensitive fields just for convenience.

`RETURNS TABLE(employee_id integer, employee_name text)` clarifies the public contract, though you must still enforce row-level access controls.

## 47. RAISE EXCEPTION, RETURN, and Error Handling

A set-returning function may need to reject invalid inputs:

```sql
IF p_department_id IS NULL THEN
    RAISE EXCEPTION 'department_id must not be NULL'
        USING ERRCODE = '22023';
END IF;

RETURN QUERY SELECT ...;
RETURN;
```

### 47.1. RETURN; Does Not Handle Exceptions

If an SQL statement inside the function fails, having `RETURN;` afterward does not suppress the error. Control jumps immediately via exception and transaction rules.

### 47.2. EXCEPTION Blocks When Needed

PL/pgSQL supports:

```sql
BEGIN
    ...
EXCEPTION
    WHEN unique_violation THEN
        ...
END;
```

However, never write `WHEN OTHERS THEN RETURN;` to swallow all errors and claim "no data found." That masks outages, schema errors, and permission bugs.

### 47.3. Distinguish Empty Sets from Errors

- No active employees → returning 0 rows is valid.
- Wrong `department_id` type or unauthorized scope → handle/reject appropriately.
- Database error → propagate error and roll back rather than pretending 0 rows matched.

## 48. Common Mistakes with RETURN NEXT / RETURN QUERY

### Mistake 1 — Using RETURN expression in RETURNS SETOF

Incorrect:

```sql
RETURNS SETOF integer
...
RETURN v_id;
```

Correct:

```sql
RETURN NEXT v_id;
RETURN;
```

### Mistake 2 — Thinking RETURN NEXT Exits the Function

It only appends a row; subsequent statements still run.

### Mistake 3 — Thinking RETURN QUERY Exits the Function

It appends a query's rows; a second `RETURN QUERY` can still execute afterward.

### Mistake 4 — Passing an Expression to RETURN NEXT in RETURNS TABLE

Because `RETURNS TABLE` creates `OUT` parameters, assign the output variables and call argumentless `RETURN NEXT;`.

### Mistake 5 — Forgetting to Assign All Output Variables Each Iteration

Leaves stale values from previous iterations or NULLs in output columns.

### Mistake 6 — Using Bare RETURN; in a Scalar Function Returning integer

Never use bare `RETURN;` in place of `RETURN expression` for an ordinary scalar function.

### Mistake 7 — Leaving an IF Branch Without RETURN in a Scalar Function

Triggers `"control reached end of function without RETURN"` at runtime.

### Mistake 8 — Assuming 0 Rows Equals 1 NULL Row

They behave differently in SQL, `JOIN`s, and `COUNT`s.

### Mistake 9 — count(*) Returns bigint While RETURNS TABLE Declares integer

Causes a runtime row-structure mismatch.

### Mistake 10 — Assuming varchar Auto-Coerces to text in Every RETURN QUERY

Check row descriptors and cast explicitly when needed.

### Mistake 11 — Reversing Output Column Order

Returned columns match by position and type, not implicitly by column name.

### Mistake 12 — Unqualified Column Matching an Output Variable Name

Causes `"column reference ... is ambiguous"`.

### Mistake 13 — Reading FOUND Too Late After RETURN QUERY

An intervening `PERFORM`, `SELECT INTO`, or loop can overwrite `FOUND`.

### Mistake 14 — Thinking RETURN NEXT Sets FOUND=true

It does not update `FOUND` the way `RETURN QUERY` does.

### Mistake 15 — Using RETURN QUERY SELECT ... Instead of SELECT INTO for Scalars

`RETURN QUERY` builds set outputs; `SELECT INTO` assigns variables.

### Mistake 16 — Using Dynamic SQL for Every Parameter Value

Unnecessary when only values vary; use static SQL inside `RETURN QUERY`.

### Mistake 17 — Concatenating Raw Input into RETURN QUERY EXECUTE

Creates SQL injection risks; use `USING` and whitelisted/quoted identifiers.

### Mistake 18 — Thinking RETURN QUERY EXECUTE Can Return Arbitrary Schemas

The returned row shape must still match the function's declared return type.

### Mistake 19 — Thinking RETURN NEXT Streams Each Row Immediately to Clients

PL/pgSQL SRFs currently materialize the result set before returning.

### Mistake 20 — Putting LIMIT Outside and Expecting the Function to Generate Only That Many Rows

Not guaranteed. Push limits into queries inside the function.

### Mistake 21 — Omitting ORDER BY at the Caller When Order Matters

SQL queries without `ORDER BY` have no guaranteed output order.

### Mistake 22 — Using SETOF record Without Specifying Column Types at the Call Site

PostgreSQL cannot determine the shape; supply `AS alias(column type, ...)`.

### Mistake 23 — Confusing Functions with Procedures or Triggers

`RETURN` semantics depend on the routine kind.

### Mistake 24 — Marking a Table-Reading Function as IMMUTABLE

Wrong volatility misleads the optimizer.

### Mistake 25 — Thinking ROWS 100 Caps Output Rows

`ROWS` is a planner estimate, not a `LIMIT`.

### Mistake 26 — Exposing SELECT * in Unscoped SECURITY DEFINER Functions

Risks data leaks; enforce `EXECUTE` grants, RLS, tenant scoping, and minimal columns.

### Mistake 27 — Swallowing Exceptions and Returning an Empty Set

Hides operational failures and degrades API reliability.

### Mistake 28 — Choosing LOOP + RETURN NEXT When a Single SELECT Works

Makes code verbose and harder to optimize; prefer `RETURN QUERY` or `LANGUAGE sql`.

## 49. Exercises with Answers

### Exercise 1. What Should an Integer-Returning Function Write?

**Prompt:** Return twice `p_x`.

```sql
CREATE FUNCTION pl358.exercise_double(p_x integer)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_x * 2;
END;
$$;
```

**Answer:** `RETURN expression;` because there is a single scalar result.

### Exercise 2. Does RETURN NEXT Stop the Function Immediately?

**Answer:** No. It appends one row to the result set and continues executing the next statement.

### Exercise 3. Does RETURN QUERY SELECT Need a LOOP?

**Answer:** No. PostgreSQL appends 0 or more rows directly from the query.

### Exercise 4. Where Does Omitting an Argument Differ from Passing NULL?

**Answer:** With default input parameters, omitting an argument uses the default value; passing explicit `NULL` passes `NULL` and can change filter or validation behavior.

### Exercise 5. What Does RETURN; Do in a RETURNS SETOF Function?

**Answer:** Ends construction of the result set without appending another row.

### Exercise 6. What Does RETURN; Do in RETURNS void?

**Answer:** Exits the void function with no expression.

### Exercise 7. How Is RETURN NEXT Written in RETURNS TABLE?

**Answer:** Assign all output variables, then execute `RETURN NEXT;` with no expression.

### Exercise 8. How Is RETURN NEXT Written in RETURNS SETOF integer?

```sql
RETURN NEXT v_id;
```

**Answer:** Pass a compatible integer expression.

### Exercise 9. Can RETURNS SETOF employees Use RETURN NEXT with a Record Variable?

**Answer:** Yes, provided the record or row variable matches the composite structure of `pl358.employees`.

### Exercise 10. Which Active Employees Exist in Department 10?

**Answer:** The fixture has two active employees: `101` and `102`.

### Exercise 11. Call active_employee_ids for Department 40

```sql
SELECT *
FROM pl358.active_employee_ids(40);
```

**Answer:** 0 rows.

### Exercise 12. How Many Rows Does RETURN NEXT NULL::integer Produce?

**Answer:** 1 row containing SQL `NULL`, not an empty set.

### Exercise 13. How Many Rows Does RETURN QUERY SELECT ... WHERE false Produce?

**Answer:** 0 rows.

### Exercise 14. Can RETURN QUERY Be Called Twice?

**Answer:** Yes; each call appends its query's rows to the result set without deduplication.

### Exercise 15. Can RETURN NEXT and RETURN QUERY Be Combined?

**Answer:** Yes, inside a matching `RETURNS SETOF` function, ensuring all rows share compatible types.

### Exercise 16. Why Is Assigning OUT Columns on Every Iteration Critical?

**Answer:** Output columns are live function variables; forgetting to assign one leaves stale values or `NULL`.

### Exercise 17. Fetch Department 20 Employees Earning >= 2000

```sql
SELECT *
FROM pl358.find_active_employees(20, 2000);
```

**Answer:** Dung (104), salary 2500.

### Exercise 18. What Is the Total Active Salary in Engineering?

**Answer:** `2200 + 2900 = 5100.00`; inactive employee Chi is excluded.

### Exercise 19. How Many Active Employees Are in Research?

**Answer:** `0`; the `LEFT JOIN` aggregate in `department_statistics` still retains the Research row.

### Exercise 20. Why Use count(e.employee_id) Instead of count(*)?

**Answer:** On an unmatched `LEFT JOIN` row, `COUNT(*)` counts the NULL-padded row as 1; `COUNT(right_side_non_null_key)` returns 0.

### Exercise 21. What Type Does count(*) Return by Default?

**Answer:** `bigint`. Declaring `integer` in `RETURNS TABLE` causes a structure mismatch.

### Exercise 22. Fix count(*) to Match a bigint Output

```sql
RETURN QUERY
SELECT e.department_id, count(*)
FROM pl358.employees AS e
GROUP BY e.department_id;
```

**Answer:** Declare the count output column as `bigint`.

### Exercise 23. Why Does "column reference is ambiguous" Occur?

**Answer:** Output parameter names of `RETURNS TABLE` are also PL/pgSQL variables. Use table aliases like `e.employee_id` to disambiguate.

### Exercise 24. RETURN QUERY Selecting VARCHAR into a TEXT Output?

**Answer:** Cast explicitly with `::text` so the query's row descriptor matches the function's return type.

### Exercise 25. Column Count Matches, Column Order Is Wrong?

**Answer:** Causes errors or corrupted types. Always select columns in the exact declared order and types.

### Exercise 26. Does RETURN QUERY Set FOUND?

**Answer:** Yes, `TRUE` if at least one row was appended; `FALSE` if zero rows were appended.

### Exercise 27. Does RETURN NEXT Set FOUND?

**Answer:** Not the way `RETURN QUERY` does. Never inspect `FOUND` to check whether `RETURN NEXT` emitted rows.

### Exercise 28. Running PERFORM After RETURN QUERY and Then Checking FOUND?

**Answer:** `FOUND` will reflect `PERFORM`, no longer `RETURN QUERY`. Capture `FOUND` right after `RETURN QUERY` if needed.

### Exercise 29. What Is USING For in Dynamic SQL?

**Answer:** Passing data values into placeholders like `$1`, avoiding unsafe string concatenation.

### Exercise 30. Dynamic ORDER BY Column Name?

**Answer:** Whitelist allowed column names, quote the identifier with `format('%I', ...)`, and map `ASC`/`DESC` strictly from trusted values.

### Exercise 31. Should p_name Be Concatenated into WHERE full_name='...'?

**Answer:** No; that risks SQL injection and quoting bugs. Use `USING`.

### Exercise 32. Function Returns 10,000 Rows, Caller Applies LIMIT 1—Does PL/pgSQL Build Only 1 Row?

**Answer:** Not guaranteed. PL/pgSQL SRFs materialize results before finishing; push `LIMIT` inside the function's query.

### Exercise 33. Does ROWS 100 Cap Output to 100 Rows?

**Answer:** No. It is only a planner estimate.

### Exercise 34. Should a Function Reading employees Be Marked IMMUTABLE?

**Answer:** No, because table data can change. Table-reading examples use `STABLE`.

### Exercise 35. What Volatility Should a Function with Side Effects Use?

**Answer:** Typically `VOLATILE`, per exact semantics. Never declare `IMMUTABLE` to force optimization.

### Exercise 36. How to JOIN While Retaining Research?

```sql
SELECT d.department_name, s.employee_id
FROM pl358.departments AS d
LEFT JOIN LATERAL
    pl358.find_active_employees(d.department_id) AS s
ON true;
```

**Answer:** `LEFT JOIN LATERAL` preserves parent rows when the function yields 0 rows.

### Exercise 37. Does CROSS JOIN LATERAL Retain Research?

**Answer:** No, if the function returns an empty set for Research.

### Exercise 38. When Should You Prefer LANGUAGE sql?

**Answer:** When the logic is a single set-based `SELECT` needing no PL/pgSQL procedural control.

### Exercise 39. When Must EXPLAIN (ANALYZE) Be Used Carefully?

**Answer:** Because it executes the statement; functions with DML or side effects will mutate real data.

### Exercise 40. What Must a SECURITY DEFINER Function Returning Employees Protect?

**Answer:** `EXECUTE` grants, `search_path`/schema qualification, tenant/role authorization, RLS interaction, sensitive columns, and strict dynamic SQL controls.

### Exercise 41. How Does RETURN QUERY Differ from SELECT INTO?

**Answer:** `RETURN QUERY` appends rows to a function's result set; `SELECT INTO` assigns values/rows into PL/pgSQL variables.

### Exercise 42. How Does RETURN QUERY EXECUTE Differ from EXECUTE INTO?

**Answer:** `RETURN QUERY EXECUTE` appends dynamic SQL rows to the result set; `EXECUTE INTO` assigns results into variables.

### Exercise 43. A Scalar Function Path Reaches END Without RETURN?

**Answer:** Raises `"control reached end of function without RETURN"`; ensure every path returns or raises.

### Exercise 44. Should a Trigger Function Execute RETURN NEXT NEW?

**Answer:** No. Triggers return `NEW`, `OLD`, or `NULL` according to trigger semantics.

### Exercise 45. If Employees Should Be Ordered by salary DESC, Is ORDER BY Inside RETURN QUERY Enough?

**Answer:** An inner `ORDER BY` supports internal `LIMIT`/logic, but callers must specify an outer `ORDER BY` to guarantee presentation order.

## 50. Checklist for Writing PL/pgSQL Functions with RETURN

| Question | What to Verify |
|---|---|
| Scalar or set-returning? | Choose the right `RETURN` syntax |
| `RETURNS void` or `OUT`/`INOUT`? | Know when expressionless `RETURN;` applies |
| Do all scalar paths return a value? | Prevent end-of-function errors |
| Explicitly distinguish NULL / 0 / error? | Preserve business semantics |
| `SETOF scalar` returns right type? | `RETURN NEXT expr` |
| `SETOF composite` returns right row type? | Complete columns and matching types |
| `RETURNS TABLE` assigns output vars before `RETURN NEXT;`? | Prevent stale/NULL values |
| Can `FOR`/`RETURN NEXT` become `RETURN QUERY`? | Simplify with set-based SQL |
| `RETURN QUERY` matches column count/order/types? | Avoid structure mismatches |
| `count(*)` output declared as `bigint`? | Avoid accidental `integer` mismatch |
| `varchar`/`text` casts needed? | Match row descriptors cleanly |
| Output names collide with column names? | Qualify columns with table aliases |
| Remember `RETURN QUERY` does not exit? | Avoid unintended duplicate appends |
| Multiple `RETURN QUERY` statements? | Check deduplication and logic |
| Read `FOUND` right after `RETURN QUERY`? | Don't read stale/overwritten `FOUND` |
| Avoid assuming `RETURN NEXT` streams? | PL/pgSQL materializes results |
| Need row cap inside the function? | Push `LIMIT` inside |
| Outer `ORDER BY` at caller when order matters? | SQL does not guarantee implicit order |
| Dynamic SQL genuinely needed? | Avoid unnecessary complexity |
| Dynamic values bound via `USING`? | Prevent SQL injection |
| Identifiers whitelisted and quoted? | Prevent query-structure tampering |
| Source queries/indexes tuned? | `EXPLAIN` on representative data |
| `ROWS`/`COST` hints realistic? | Planner estimates are not `LIMIT`s |
| Volatility declared accurately? | `IMMUTABLE`/`STABLE`/`VOLATILE` |
| Function has side effects? | Be careful with `EXPLAIN ANALYZE` and retries |
| Output contains sensitive data? | Grants, tenant scoping, RLS, `SECURITY DEFINER` |
| Return type treated as stable API? | Plan migrations and compatibility |
| Tested 0, 1, and multiple rows? | Core edge cases |
| Tested NULL, invalid inputs, duplicates, empty sets? | Data correctness |
| Tested from actual SQL client? | Bind types and caller privileges |
| Logs/metrics avoid leaking sensitive data? | Production observability |

## 51. Summary by Scenario

| Scenario | Typical Pattern |
|---|---|
| Return integer 42 | `RETURN 42;` |
| Scalar returns NULL | `RETURN NULL;` |
| Scalar validates input and exits | `IF ... THEN RETURN ...; END IF;` |
| Finish void function | `RETURN;` |
| Function with `OUT` parameters | Assign `OUT` variables → `RETURN;` |
| `SETOF integer` appends one number | `RETURN NEXT v_id;` |
| `SETOF composite` appends one record | `RETURN NEXT v_row;` |
| `RETURNS TABLE` appends one row | Assign output columns → `RETURN NEXT;` |
| `RETURNS TABLE` appends rows from `SELECT` | `RETURN QUERY SELECT ...;` |
| Concatenate multiple result sets | Multiple `RETURN QUERY` calls |
| Prepend/append special rows | Mix `RETURN NEXT ...;` and `RETURN QUERY ...;` |
| Check if `RETURN QUERY` produced rows | Read `FOUND` immediately afterward |
| Dynamic SQL with bound values | `RETURN QUERY EXECUTE ... USING p_value;` |
| Dynamic SQL with column names | Whitelist + `format('%I', identifier)` |
| Return empty set immediately | `RETURN;` in `SETOF`/`RETURNS TABLE` |
| Limit generated rows efficiently | `LIMIT` inside the function's query |
| Avoid PL/pgSQL loops | `RETURN QUERY` or `LANGUAGE sql` |
| Parameter with default | `p_min_salary numeric DEFAULT 0` |
| Correlate function per parent row | `JOIN LATERAL function(...)` |

## 52. Official Documentation for Further Reading

Cross-check against documentation for your PostgreSQL server version:

- [PL/pgSQL: Returning From a Function](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-STATEMENTS-RETURNING): `RETURN`, `RETURN NEXT`, `RETURN QUERY`, and exiting functions.
- [PL/pgSQL: Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): `IF`, `FOR`, `EXIT`, and flow control.
- [PL/pgSQL: Obtaining the Result Status](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-DIAGNOSTICS): `FOUND` and execution status.
- [PL/pgSQL: Executing Dynamic Commands](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN): `EXECUTE`, `USING`, `format`, quoting.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `RETURNS SETOF`, `RETURNS TABLE`, `COST`, `ROWS`, volatility, and security.
- [SQL Functions Returning Sets](https://www.postgresql.org/docs/current/xfunc-sql.html#XFUNC-SQL-FUNCTIONS-RETURNING-SET): comparison with `LANGUAGE sql` functions.
- [Composite Types](https://www.postgresql.org/docs/current/rowtypes.html): composite row structures.
- [LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL): joining set-returning functions with outer tables.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): inspecting query plans and execution costs.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): granting function privileges safely.
- [Function Volatility](https://www.postgresql.org/docs/current/xfunc-volatility.html): `IMMUTABLE`/`STABLE`/`VOLATILE`.

The SQL snippets in this lesson are **theoretical examples and lab exercises**. Authoring them does not imply live execution on a specific PostgreSQL instance; before applying anything in production, test DDL, privileges, output types, and representative data.

## 53. Summary

Three essential statements:

```sql
-- Scalar function:
RETURN expression;

-- SETOF / RETURNS TABLE function:
RETURN NEXT ...;

-- SETOF / RETURNS TABLE function:
RETURN QUERY SELECT ...;

-- Finish set-returning function:
RETURN;
```

Memory diagram:

```text
                 What should the routine return?
                        |
            +-----------+-----------+
            |                       |
      Single value            Set of multiple rows
            |                       |
      RETURN expr;        +---------+---------+
                          |                   |
                     Row by row          From SELECT
                          |                   |
                    RETURN NEXT           RETURN QUERY
                          |                   |
                          +---------+---------+
                                    |
                               RETURN;
                                    |
                             Finish result set
```

Key takeaways:

1. **`RETURN expression` terminates a scalar function immediately.**
2. **`RETURN NEXT` appends one element/row without exiting the function.**
3. **`RETURN QUERY` appends 0 or more query rows without exiting the function.**
4. **Expressionless `RETURN;` terminates set-returning functions and other supported routine forms.**
5. **`RETURNS TABLE` uses output variables**: with `RETURN NEXT;`, assign output variables first.
6. **`RETURNS SETOF scalar/composite` uses `RETURN NEXT expression;`** with a compatible type.
7. **`RETURN QUERY` row shapes must match** the return declaration's column count, order, and types.
8. **`count(*)` returns `bigint`**, never auto-matching `integer` just because values are small.
9. **`FOUND` after `RETURN QUERY`** indicates whether any rows were appended; `RETURN NEXT` does not update `FOUND` that way.
10. **PL/pgSQL set-returning functions materialize results**, rather than streaming row-by-row to clients.
11. **`RETURN QUERY EXECUTE` must use `USING` for values** and whitelisting/quoting for dynamic identifiers.
12. **For simple set-based queries, prefer `RETURN QUERY` or `LANGUAGE sql`** over manual loops.
13. **Callers need outer `ORDER BY` when order matters**, and `LIMIT` inside the function to cap generated rows.
14. **Volatility, grants, RLS, `SECURITY DEFINER`, and transaction semantics** still matter even when a function "only reads data."

**One sentence to remember:** `RETURN` **terminates and returns one result**, whereas `RETURN NEXT` and `RETURN QUERY` **build a result set incrementally**, which is finalized for the caller only when the function finishes.
