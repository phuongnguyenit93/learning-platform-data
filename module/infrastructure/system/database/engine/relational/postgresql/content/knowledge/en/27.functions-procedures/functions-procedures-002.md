# Parameter Modes IN, OUT, INOUT, and VARIADIC

In PostgreSQL, **functions** and **procedures** are database objects that can accept parameters to process data. A function computing tax-inclusive prices may need a price and a tax rate; an analytics function may return both row count and total revenue simultaneously; a limit-checking procedure may accept a value and return an adjusted one; and a summation function may need to accept a **variable number of arguments**. The four parameter modes `IN`, `OUT`, `INOUT`, and `VARIADIC` address these needs.

Although their names resemble reference concepts in some programming languages, how they work in PostgreSQL is not identical to passing pointers or mutable Java objects. You must distinguish **the calling signature**, **incoming values**, **outgoing values**, and **how the client receives results**.

## 1. Learning objectives

After this lesson, you can:

1. Explain the meaning of `IN`, `OUT`, `INOUT`, and `VARIADIC` in routine declarations.
2. Write `LANGUAGE SQL` and `LANGUAGE plpgsql` functions with syntactically correct input/output parameters.
3. Return one or multiple results using `OUT` and compare it with `RETURNS TABLE`.
4. Write functions/procedures with `INOUT` and understand how values are received and returned.
5. Call procedures with `CALL`, functions with `SELECT`, and retrieve the corresponding return values.
6. Create functions with `VARIADIC` to accept multiple values or directly receive an SQL array.
7. Understand parameter names, default arguments, positional/named notation, and overloading limits.
8. Identify SQL NULL handling, input validation, exception/transaction behavior, and security considerations.
9. Inspect signatures, modes, and return types from `pg_proc` or catalog helper functions.
10. Write Java/JDBC/Spring code that invokes routines safely, with proper error handling and testing.

> **Environment:** Exercises use PostgreSQL with support for `CREATE PROCEDURE` (PostgreSQL 11+), `PL/pgSQL`, and JDBC. Details regarding procedure `OUT` parameters, how results are displayed, and transaction control conditions can vary across versions; check your server version before applying version-dependent examples. Example SQL runs in a lab schema, never against production data.

## 2. How functions and procedures differ

Both objects have a name, a parameter list, and a body. However:

| Criterion | Function | Procedure |
|---|---|---|
| Created with | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Typical invocation | `SELECT function(...)` or inside an SQL expression | `CALL procedure(...)` |
| Usable as an expression in SELECT, WHERE | Yes, when the return type and usage are suitable | No |
| Returning results | `RETURNS`, `OUT`, `INOUT`, `RETURNS TABLE`, `SETOF` | Output parameters of `CALL` |
| Internal transaction control | Cannot `COMMIT`/`ROLLBACK` transactions | Permitted under specific invocation conditions |
| Uses `IN` | Yes | Yes |
| Uses `OUT` | Yes | Yes, in supported PostgreSQL versions |
| Uses `INOUT` | Yes | Yes |
| Uses `VARIADIC` | Yes | Yes, when supported in the corresponding definition |

### A design principle

A **Function** fits when you need to return results that can participate in another query. A **Procedure** fits when executing a business-meaningful action via `CALL`, optionally receiving output parameters. Do not choose a procedure merely because you want to modify data: functions can also perform side effects under permitted conditions, though they lack a procedure's transaction control capabilities.

Do not confuse `CALL` with `SELECT`: PostgreSQL does not automatically treat a function as a procedure just because two objects share similar names or arguments.

## 3. Overview of the four parameter modes

| Mode | Receives value from caller? | Contributes to output result? | Idea |
|---|---|---|---|
| `IN` | Yes | Not automatically | Input-only data transfer |
| `OUT` | Not a meaningful input | Yes | Result output slot |
| `INOUT` | Yes | Yes | Receives initial value and returns final value |
| `VARIADIC` | Yes, receives multiple arguments of the same element type or an array | Not automatically | Variable-length input list |

Visual overview:

```text
IN:
  caller 7 -----> function(p_value=7)
                function RETURN ...

OUT:
  caller inputs -----> function
                        ├── OUT total
                        └── OUT average
  caller receives result columns/values

INOUT:
  caller 7 -----> routine(p_value=7) -----> caller receives new value

VARIADIC:
  caller (2, 4, 6, 8) -----> routine(p_values int[]) 
```

### Note: the default mode is IN

Declaring:

```sql
CREATE FUNCTION demo(p_number integer) ...
```

is equivalent in parameter mode to:

```sql
CREATE FUNCTION demo(IN p_number integer) ...
```

Do not write `OUT` in a signature when you actually only need an input parameter.

## 4. Preparing the learning schema

```sql
CREATE SCHEMA IF NOT EXISTS lesson_param_modes;
```

All objects in this lesson use schema-qualified names to avoid colliding with application functions or same-named functions in `search_path`.

Check the server:

```sql
SELECT
    current_database() AS database_name,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS version_num;
```

If you tried earlier lessons and created routines with the same names but different definitions, manage them via explicit migrations; do not run `DROP SCHEMA ... CASCADE` in environments containing important data.

## 5. IN: receiving input values

Function calculating rectangle area:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.rectangle_area(
    IN p_width numeric,
    IN p_height numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_width * p_height;
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.rectangle_area(4, 6) AS area;
-- area = 24

SELECT lesson_param_modes.rectangle_area(2.5, 8) AS area;
-- area = 20.0 in numeric value
```

### Meaning of IN

- `p_width` and `p_height` receive values from the caller.
- Inside an SQL function, they can be referenced by name or position using valid syntax.
- The `IN` mode **does not automatically produce a result column**.
- The return value here comes from `RETURNS numeric` and the final expression of the SQL function.

`IMMUTABLE` declares the function's purity: identical inputs always produce the same result without depending on external state. `STRICT` instructs PostgreSQL to return NULL immediately whenever any applicable input argument is SQL NULL; use these attributes only when the logic genuinely satisfies them.

## 6. IN as default; PL/pgSQL example

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.discounted_price(
    p_price numeric,
    p_percent numeric
)
RETURNS numeric
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_price IS NULL OR p_percent IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_price < 0 THEN
        RAISE EXCEPTION
            'Price must be nonnegative';
    END IF;

    IF p_percent < 0 OR p_percent > 100 THEN
        RAISE EXCEPTION
            'Percent must be between 0 and 100';
    END IF;

    RETURN round(p_price * (1 - p_percent / 100), 2);
END;
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.discounted_price(100000, 15);
-- 85000.00

SELECT lesson_param_modes.discounted_price(100000, NULL);
-- NULL
```

`STRICT` is omitted in this example to demonstrate checking `NULL` inside the body. If `STRICT` were declared, PostgreSQL would skip the body on NULL input, so checks or logging inside the body would not execute.

## 7. IN does not mean Java pass-by-reference

In PL/pgSQL, parameters can be referenced and certain parameter variables can be reassigned within the execution scope. However, **reassigning an IN variable does not automatically update a Java variable or an SQL variable on the caller side**.

Example:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.local_change(
    IN p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    p_value := p_value + 10;
    RETURN p_value;
END;
$$;

SELECT lesson_param_modes.local_change(5);
-- 15
```

The value 15 is received through **RETURN**, not because PostgreSQL mutated a variable outside the function. To express a parameter that acts as both input and output in the interface, use `INOUT`.

## 8. IN with named parameters and positional notation

A standard call passes arguments in order:

```sql
SELECT lesson_param_modes.discounted_price(200000, 10);
```

The first argument maps to `p_price`, the second to `p_percent`. This is **positional notation**.

You can also call by name:

```sql
SELECT lesson_param_modes.discounted_price(
    p_percent => 10,
    p_price => 200000
);
```

`=>` is named-argument notation, which helps prevent argument-order mistakes when multiple inputs share the same type. Parameter names become part of the routine's API; renaming them carelessly can break callers using named notation.

### OUT names do not need to be passed

For functions, `OUT`-only parameters are not input arguments supplied in `SELECT function(...)`. That is a key distinction covered in the next section.

## 9. OUT: a single result parameter

A function can declare its return type through an `OUT` parameter:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.double_value(
    IN p_value integer,
    OUT p_double integer
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    p_double := p_value * 2;
END;
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.double_value(7) AS result;
-- result = 14
```

### Key points

- The caller **only passes** `p_value`.
- `p_double` is the output variable and also determines the function's return type.
- You do not write an extra `RETURNS integer` clause when declaring the return via `OUT`.
- When the PL/pgSQL function reaches the end, the output parameter's value determines the result.

In a PL/pgSQL function with OUT parameters, `RETURN;` **without an expression** exits early and returns the current OUT values.

## 10. OUT: returning multiple fields together

Suppose you need to compute both the sum and product of two numbers:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_and_product(
    IN p_a integer,
    IN p_b integer,
    OUT o_sum bigint,
    OUT o_product bigint
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    o_sum := p_a::bigint + p_b::bigint;
    o_product := p_a::bigint * p_b::bigint;
END;
$$;
```

Call it like a table with result columns:

```sql
SELECT *
FROM lesson_param_modes.sum_and_product(7, 4);

-- o_sum | o_product
-- ------+----------
-- 11    | 28
```

Or retrieve the aggregated result as a composite value:

```sql
SELECT lesson_param_modes.sum_and_product(7, 4);
```

With **multiple OUT parameters**, the return type is represented as a composite/record containing the declared fields. Using `SELECT * FROM function(...)` expands those fields into separate columns.

### When to use multiple OUT parameters?

- A computation returns multiple tightly coupled values.
- The result has a clear structure with a small number of fields.
- The client can conveniently read SQL columns.

Do not try to squeeze an unbounded list of rows into fixed OUT parameters; when you need multiple rows, consider `RETURNS TABLE`/`SETOF`.

## 11. Returning OUT early in PL/pgSQL

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.describe_number(
    IN p_value integer,
    OUT o_label text,
    OUT o_absolute bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value IS NULL THEN
        o_label := 'missing';
        o_absolute := NULL;
        RETURN;
    END IF;

    IF p_value < 0 THEN
        o_label := 'negative';
    ELSIF p_value = 0 THEN
        o_label := 'zero';
    ELSE
        o_label := 'positive';
    END IF;

    o_absolute := abs(p_value::bigint);
END;
$$;
```

`RETURN;` does not return a new expression; it terminates with **the current values of the output parameters**.

Invocation:

```sql
SELECT *
FROM lesson_param_modes.describe_number(-9);

SELECT *
FROM lesson_param_modes.describe_number(NULL);
```

### Pitfall: forgetting to assign an OUT parameter

If an OUT parameter is left unassigned along an execution path, it remains NULL. A function that returns successfully while missing a required field is a **business logic bug** that must be caught by validation/tests—PostgreSQL will not automatically raise an error in every case.

## 12. OUT does not participate in a function's input list

The function:

```sql
lesson_param_modes.sum_and_product(
    IN p_a integer,
    IN p_b integer,
    OUT o_sum bigint,
    OUT o_product bigint
)
```

is **called** with two arguments:

```sql
SELECT *
FROM lesson_param_modes.sum_and_product(7, 4);
```

Not like this:

```sql
-- Incorrect way to call a function with OUT-only:
SELECT *
FROM lesson_param_modes.sum_and_product(
    7, 4, NULL, NULL
);
```

### Role in function identity

In PostgreSQL, the signature used to identify and overload functions is based on **input argument types**, including `IN`, `INOUT`, and `VARIADIC` element types according to resolution rules. `OUT`-only parameters do not create a distinct overload merely by returning different types.

This affects `DROP FUNCTION`, catalog entries, overloading, and how clients resolve routines.

## 13. INOUT: accepting a value and returning an updated result

`INOUT` combines input and output roles.

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.increase_counter(
    INOUT p_counter bigint,
    IN p_delta bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_counter IS NULL OR p_delta IS NULL THEN
        RAISE EXCEPTION 'Counter and delta are required';
    END IF;

    p_counter := p_counter + p_delta;
END;
$$;

SELECT lesson_param_modes.increase_counter(10, 5);
-- 15
```

The caller **passes in** 10 for `p_counter` and **receives back** 15 as the function result.

### Why not just use IN and RETURN?

Computationally, both approaches are equivalent for a single output. `INOUT` explicitly conveys an "in/out state value" contract in the signature, which is useful when working with procedures or multiple outputs. Still, it does not mean INOUT mutates a Java caller variable directly by reference as in some programming languages.

## 14. INOUT with multiple results

A routine can have multiple `INOUT` parameters:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.swap_numbers(
    INOUT p_first integer,
    INOUT p_second integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_temp integer;
BEGIN
    v_temp := p_first;
    p_first := p_second;
    p_second := v_temp;
END;
$$;

SELECT *
FROM lesson_param_modes.swap_numbers(12, 99);

-- p_first | p_second
-- --------+---------
-- 99      | 12
```

### INOUT participates in both signature and result

Unlike `OUT`-only, the two `integer` types of `p_first` and `p_second` are **input types**, so they participate in function identity and overload resolution.

The return value consists of two columns holding their final values.

### Good usage scenarios

Swapping here mainly illustrates parameter modes. In real application design, a function returning a clearly named record/JSON object may be easier to read if the inputs are purely computational rather than state variables being updated.

## 15. Combining IN, OUT, and INOUT in one function

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.apply_fee(
    IN p_fee numeric,
    INOUT p_balance numeric,
    OUT o_applied boolean
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_fee IS NULL OR p_balance IS NULL THEN
        RAISE EXCEPTION 'Fee and balance cannot be NULL';
    END IF;

    IF p_fee < 0 OR p_balance < 0 THEN
        RAISE EXCEPTION 'Values must be nonnegative';
    END IF;

    IF p_balance < p_fee THEN
        o_applied := false;
    ELSE
        p_balance := p_balance - p_fee;
        o_applied := true;
    END IF;
END;
$$;
```

Invocation:

```sql
SELECT *
FROM lesson_param_modes.apply_fee(25, 100);

-- p_balance | o_applied
-- ----------+----------
-- 75        | true

SELECT *
FROM lesson_param_modes.apply_fee(250, 100);

-- 100       | false
```

### Explanation

`p_fee`: IN-only, not emitted directly.

`p_balance`: INOUT, receives the initial balance and returns the final balance.

`o_applied`: OUT-only, indicates whether the fee was applied.

This function **only computes values** and does not debit a balance in an actual account row. A real payment system requires transactions, locking/constraints, idempotency, ledger entries, and financial rules. Never replace an atomic account-table UPDATE with this pure calculation example.

## 16. Functions with OUT and SELECT invocation forms

There are two distinct calling forms:

```sql
-- Composite value form:
SELECT lesson_param_modes.sum_and_product(3, 5);

-- Column form:
SELECT *
FROM lesson_param_modes.sum_and_product(3, 5);
```

When using the function in a `FROM` clause, the output fields become named columns that are convenient for JDBC and SQL.

If you need to reuse the results in a larger query:

```sql
SELECT
    s.o_sum,
    s.o_product,
    s.o_sum + s.o_product AS combined
FROM lesson_param_modes.sum_and_product(3, 5) AS s;
```

### Do not pass OUT-only parameters as arguments

For functions, the number of passed arguments depends strictly on input parameters, excluding OUT-only ones. Calling `sum_and_product(3,5,NULL,NULL)` looks for a different overload with four inputs and typically fails.

## 17. RETURNS TABLE vs. multiple OUT parameters

PostgreSQL supports:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.classify_values(
    p_min integer,
    p_max integer
)
RETURNS TABLE (
    value integer,
    parity text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        g,
        CASE WHEN g % 2 = 0
             THEN 'even' ELSE 'odd' END
    FROM generate_series(p_min, p_max) AS g;
$$;
```

Invocation:

```sql
SELECT *
FROM lesson_param_modes.classify_values(2, 5);
```

The result contains **multiple rows**, each with `value` and `parity`. `RETURNS TABLE` implies a set-returning result with the defined output columns.

### Differences from regular multiple OUT parameters

- `sum_and_product` with multiple OUT parameters returns **a single record** per call.
- `classify_values` with `RETURNS TABLE` can return **0, 1, or many rows**.
- `RETURNS TABLE(...)` syntax cannot be arbitrarily mixed with `OUT`/`INOUT` declarations for the same output list; pick one consistent interface style.

Do not use `OUT` for a variable-length list just to make it look tabular. When multiple rows are needed, design a proper set-returning function.

## 18. PL/pgSQL with RETURNS TABLE and RETURN QUERY

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.multiples_of(
    p_number integer,
    p_max_multiplier integer
)
RETURNS TABLE (
    multiplier integer,
    result bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_max_multiplier IS NULL OR p_max_multiplier < 0 THEN
        RAISE EXCEPTION 'Max multiplier must be nonnegative';
    END IF;

    RETURN QUERY
    SELECT
        g,
        p_number::bigint * g
    FROM generate_series(1, p_max_multiplier) AS g;
END;
$$;

SELECT *
FROM lesson_param_modes.multiples_of(7, 4);
```

`RETURN QUERY` appends rows to the result set returned by the function. `RETURN;` ends row generation according to PL/pgSQL syntax. Do not confuse `RETURN QUERY` with assigning to a scalar OUT variable.

### Behavior when p_max_multiplier = 0

`generate_series(1,0)` produces no rows with the default positive step, so the function can return **0 rows**, unlike a multi-OUT function which returns one row with NULL fields.

## 19. Procedures: calling with CALL

Functions in the previous sections were called via `SELECT`. Procedures use `CALL`.

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.log_message(
    IN p_message text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Message: %', p_message;
END;
$$;

CALL lesson_param_modes.log_message('Hello PostgreSQL');
```

`RAISE NOTICE` emits a server notice; it is not an SQL result set like `SELECT function(...)`. Do not rely on NOTICE messages as a stable business data API for applications.

### Why not write SELECT procedure?

`SELECT lesson_param_modes.log_message(...)` is not valid syntax for invoking a procedure. PostgreSQL distinguishes between functions and procedures; `CALL` likewise cannot replace `SELECT` when calling a function.

## 20. Procedures with INOUT

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.add_to_counter(
    INOUT p_counter integer,
    IN p_delta integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_counter IS NULL OR p_delta IS NULL THEN
        RAISE EXCEPTION 'Counter and delta required';
    END IF;

    p_counter := p_counter + p_delta;
END;
$$;
```

Calling from SQL:

```sql
CALL lesson_param_modes.add_to_counter(10, 7);
```

A `CALL` with output parameters returns **a single result row** containing the output values. In this example, the final `p_counter` is 17.

### CALL is not a table UPDATE

If `p_counter` is an input literal, PostgreSQL returns the new value in the output row; it does not permanently update a database column or application variable merely because they share a name.

## 21. Procedures with OUT-only

In PostgreSQL versions that support `OUT` parameters on procedures:

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.tax_quote(
    IN p_subtotal numeric,
    IN p_rate numeric,
    OUT o_tax numeric,
    OUT o_total numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_subtotal IS NULL OR p_rate IS NULL THEN
        RAISE EXCEPTION 'Subtotal and rate required';
    END IF;

    o_tax := round(p_subtotal * p_rate / 100, 2);
    o_total := p_subtotal + o_tax;
END;
$$;
```

When calling from top-level SQL, pass `NULL` as placeholders for **OUT-only** parameters:

```sql
CALL lesson_param_modes.tax_quote(
    1000::numeric,
    10::numeric,
    NULL,
    NULL
);
```

The result contains two columns, `o_tax` and `o_total`, equal to 100 and 1100 numerically.

### A very common point of confusion

With **OUT-only function parameters**, callers omit the OUT parameters in `SELECT function(...)`.

With **OUT-only procedure parameters in SQL CALL**, PostgreSQL requires a corresponding argument in the output position even though that argument is not evaluated as input by `CALL`; passing `NULL` is the documented recommendation for compatibility.

**This is a difference in call syntax**, not an indication that OUT becomes a real input value.

## 22. CALL from a PL/pgSQL block

When invoking a procedure with output parameters inside PL/pgSQL, output arguments must be **assignable variables** to receive the results rather than literal placeholders.

Example:

```sql
DO $$
DECLARE
    v_counter integer := 10;
BEGIN
    CALL lesson_param_modes.add_to_counter(v_counter, 7);
    RAISE NOTICE 'New counter: %', v_counter;
END;
$$;
```

The variable `v_counter` in the block becomes 17 after `CALL`.

For a procedure with `OUT`:

```sql
DO $$
DECLARE
    v_tax numeric;
    v_total numeric;
BEGIN
    CALL lesson_param_modes.tax_quote(
        1000::numeric,
        10::numeric,
        v_tax,
        v_total
    );
    RAISE NOTICE 'Tax: %, total: %', v_tax, v_total;
END;
$$;
```

**Do not pass literal `NULL` instead of output variables in PL/pgSQL CALL** when the procedure needs to assign results back to the caller. PL/pgSQL handles outputs through target variables.

## 23. Procedures with INOUT and constrained state updates

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.normalize_score(
    INOUT p_score numeric,
    IN p_min numeric,
    IN p_max numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_score IS NULL OR p_min IS NULL OR p_max IS NULL THEN
        RAISE EXCEPTION 'Arguments cannot be NULL';
    END IF;

    IF p_min > p_max THEN
        RAISE EXCEPTION 'Invalid score interval';
    END IF;

    p_score := greatest(p_min, least(p_score, p_max));
END;
$$;

CALL lesson_param_modes.normalize_score(
    120::numeric,
    0::numeric,
    100::numeric
);
-- p_score = 100
```

Notice: `INOUT` starts with input 120, is clamped inside the procedure, and yields final output 100. The caller receives the resulting value, though **if it needs to be persisted to a table**, a separate INSERT/UPDATE or controlled DML inside the procedure is required.

## 24. OUTPUT parameters are not an exception channel

Not every routine should look like:

```text
OUT success boolean
OUT error_code text
OUT error_message text
```

When an error must **abort the transaction or reject the operation**, PostgreSQL provides `RAISE EXCEPTION` and SQLSTATE. An OUT status parameter can be useful for **valid business outcomes** such as "not found" or "insufficient quota," but never silently return `success=false` while committing partial changes.

### Two distinct levels

- **Business result**: accepted or ineligible, predictable domain state; can be represented via OUT.
- **Database/system failure**: constraint violation, deadlock, timeout, SQL error; use SQLSTATE and proper transaction rollback.

API design must specify clearly which outcomes are normal results and which are exceptions.

## 25. VARIADIC: variable-length argument lists

`VARIADIC` allows a single parameter to accept multiple arguments of the same **element type**, presented as an SQL array inside the implementation.

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_values(
    VARIADIC p_numbers integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        SUM(v.value::bigint),
        0::bigint
    )
    FROM unnest(p_numbers) AS v(value);
$$;
```

Calling with multiple numbers:

```sql
SELECT lesson_param_modes.sum_values(1, 2, 3, 4);
-- 10

SELECT lesson_param_modes.sum_values(10, -5);
-- 5
```

### What is VARIADIC on the inside?

Inside the body, `p_numbers` is simply an **`integer[]`** value. PostgreSQL packs arguments like `1,2,3,4` into an array via the VARIADIC call mechanism.

`SUM(...)` returns NULL when there are no rows; `COALESCE(...,0)` defines the empty-array sum policy as 0.

## 26. Passing an array with the VARIADIC keyword

Suppose the application already holds an SQL array:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3, 4]::integer[]
);
-- 10
```

The **`VARIADIC` keyword at the call site** tells PostgreSQL that this entire array is the variadic argument, rather than listing individual elements as positional arguments.

With an empty array:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[]::integer[]
);
-- 0 according to the function definition in this lesson
```

### Why not write sum_values(ARRAY[1,2])?

When a function is declared `VARIADIC integer[]`, calling with an element list and passing a prebuilt array are not treated identically. To explicitly pass an existing array, write **`VARIADIC ARRAY[...]`**.

Contrast this with a regular function accepting `integer[]` without `VARIADIC`, which directly expects a single array argument.

## 27. VARIADIC combined with a fixed input

Example joining text fragments with a separator:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.join_parts(
    IN p_separator text,
    VARIADIC p_parts text[]
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        array_to_string(p_parts, p_separator),
        ''
    );
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.join_parts(
    ' / ',
    'PostgreSQL',
    'Functions',
    'Parameters'
);
-- PostgreSQL / Functions / Parameters

SELECT lesson_param_modes.join_parts(
    ',',
    VARIADIC ARRAY['IN', 'OUT', 'INOUT']::text[]
);
-- IN,OUT,INOUT
```

### Parameter ordering

`VARIADIC` must appear **last among the input parameters** according to routine declaration rules. OUT-only parameters follow their own syntactic placement rules, though you should avoid confusing interfaces that mix variadic inputs between multiple outputs unless truly necessary.

## 28. VARIADIC and NULL

There are at least three cases:

1. An array containing NULL elements.
2. The entire array itself is SQL NULL.
3. An empty array.

Examples:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, NULL, 3]::integer[]
);
-- 4 because SUM ignores NULL

SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[]::integer[]
);
-- 0

SELECT lesson_param_modes.sum_values(
    VARIADIC NULL::integer[]
);
```

With `sum_values` as defined above, `unnest(NULL::integer[])` produces no rows; `SUM` returns NULL and `COALESCE` turns it into 0. That is a **policy chosen by the function author**—not every variadic function treats a NULL array the same as an empty array.

### If you need to distinguish NULL from empty

Write a `LANGUAGE plpgsql` function that checks `p_numbers IS NULL` and returns NULL or raises an exception before calling `unnest`. Never apply `COALESCE` unconditionally if business rules require detecting missing data.

## 29. VARIADIC is not an arbitrary SQL *splat*

In PostgreSQL, `VARIADIC` is strongly typed as an array in its definition—it is not "accept an arbitrary list of mixed types and figure them out at runtime."

For example:

```sql
VARIADIC p_numbers integer[]
```

requires input elements to be compatible with `integer` under PostgreSQL's type casting rules.

Do not treat VARIADIC as a mechanism for passing arbitrary untyped mixes of JSON objects, numbers, and text. If you need mixed structured payloads, look at `jsonb`, composite types, or a cleaner routine interface.

## 30. VARIADIC and large cardinality risks

Suppose a caller passes tens of thousands of values:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY(
        SELECT g
        FROM generate_series(1, 10000) AS g
    )
);
```

The syntax above passes an array constructed by a subquery, which differs from sending an SQL statement with 10,000 individual argument tokens.

### Costs

- Constructing and passing the array.
- Function memory context usage.
- `unnest` and aggregation overhead.
- Parse/plan cost if the application generates SQL with huge placeholder lists.
- Network payload size if the list originates from JDBC.

If an ID list is very large and needs repeated joins, consider `unnest`, temporary tables, or staging rows depending on the workload rather than pushing everything through a variadic function.

Do not treat `VARIADIC` as a cure-all for passing massive datasets from the application.

## 31. Comparing VARIADIC with a regular array parameter

The following two functions share the same goal of summing numbers, yet offer **different call interfaces**:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_array(
    IN p_numbers integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(SUM(x::bigint), 0)
    FROM unnest(p_numbers) AS t(x);
$$;

-- A single array is one input argument:
SELECT lesson_param_modes.sum_array(ARRAY[1, 2, 3]::integer[]);

-- Multiple arguments directly:
SELECT lesson_param_modes.sum_values(1, 2, 3);

-- Pass the whole array to the VARIADIC function:
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3]::integer[]
);
```

### API decision

A **regular array** fits when Java or a query already holds an SQL array and you want an explicit signature expecting one collection.

**VARIADIC** is convenient when SQL authors want to pass a list of literals or expressions without building an array manually.

If the application primarily calls via JDBC using `createArrayOf`, a regular array parameter is often simpler—though that is a design preference, not a PostgreSQL limitation.

## 32. Named notation and VARIADIC

Named-argument notation lets you pass inputs by name:

```sql
SELECT lesson_param_modes.discounted_price(
    p_percent => 20,
    p_price => 50000
);
```

With VARIADIC, named notation and passing an entire array have **specific syntactic rules**. To avoid ambiguity over argument counts when passing an existing array, the clearest form is usually:

```sql
SELECT lesson_param_modes.join_parts(
    ' - ',
    VARIADIC ARRAY['A', 'B', 'C']::text[]
);
```

When an API has only a few parameters, positional notation is usually clear enough. When many same-typed inputs risk accidental transposition, use named notation for standard parameters and verify VARIADIC syntax on your PostgreSQL version.

### Why parameter names are part of the interface

If clients use `p_price => ...`, renaming the parameter to `price_value` breaks calls even though data types didn't change. Manage parameter renames like public API changes.

## 33. DEFAULT for IN parameters

Example of a rounding function:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.round_to(
    IN p_value numeric,
    IN p_scale integer DEFAULT 2
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(p_value, p_scale);
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.round_to(12.3456);
-- 12.35

SELECT lesson_param_modes.round_to(12.3456, 3);
-- 12.346

SELECT lesson_param_modes.round_to(
    p_scale => 1,
    p_value => 12.3456
);
-- 12.3
```

### What is a default?

A default expression lets the caller omit an optional input. It does not turn an `IN` parameter into `OUT`, nor does it act as a default for arbitrary PL/pgSQL variables.

In PostgreSQL input parameter lists, once a parameter has a default value, all subsequent input parameters must also have defaults according to declaration rules. Do not place a required input after a defaulted input and expect positional calls to remain unambiguous.

## 34. DEFAULT with INOUT and results

`INOUT` is an input parameter, so it can have a default according to input-parameter rules.

Example:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.bump_default(
    INOUT p_counter integer DEFAULT 0
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_counter := COALESCE(p_counter, 0) + 1;
END;
$$;
```

Invocation:

```sql
SELECT lesson_param_modes.bump_default();
-- 1

SELECT lesson_param_modes.bump_default(40);
-- 41
```

### Distinguishing default from SQL NULL

Omitting `p_counter` causes PostgreSQL to use the default 0. Passing **explicit SQL NULL** passes NULL as the input rather than substituting the default. In this example, `COALESCE` converts NULL to 0; that is a business decision inside the body.

Avoid adding defaults to every parameter just to make calls shorter when missing values ought to be treated as errors.

## 35. OUT-only is not an arbitrary default input

An `OUT` parameter only receives results; it is not an optional caller input. Therefore avoid designing interfaces like:

```sql
-- Wrong idea: caller picks OUT value via default.
-- OUT o_total numeric DEFAULT 0
```

If you want to ensure an initial output of 0, initialize it inside the body:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.safe_total(
    IN p_value numeric,
    OUT o_total numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    o_total := COALESCE(p_value, 0);
END;
$$;
```

### Default values in PL/pgSQL

Variables—including OUT parameters—hold SQL NULL until assigned. Declaring mode OUT does not automatically initialize numbers to 0, booleans to false, or text to an empty string. Always assign explicitly on every branch if your API contract forbids NULL.

## 36. Positional, named, and mixed notation

Example:

```sql
SELECT lesson_param_modes.discounted_price(
    100000,
    p_percent => 15
);
```

This is **mixed notation**: positional arguments first, named arguments after. When mixing, follow PostgreSQL's syntax rules: positional arguments cannot appear **after** named arguments.

### Benefits of named notation

- Self-documenting when multiple parameters share the same type.
- Independent of parameter order when all arguments are named.
- Allows skipping intermediate parameters that have defaults without passing every intervening argument.

### Risks

- Renaming parameters can break applications.
- When multiple overloaded routines share a name, named notation can complicate resolution.
- Never interpolate user-supplied text as parameter names directly in SQL.

## 37. Overloading: multiple functions with the same name

PostgreSQL allows functions to share a name if their input argument type lists form distinct signatures:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.describe(
    IN p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer: ' || p_value::text;
$$;

CREATE OR REPLACE FUNCTION lesson_param_modes.describe(
    IN p_value text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text: ' || p_value;
$$;
```

Explicit invocations:

```sql
SELECT lesson_param_modes.describe(42::integer);
-- integer: 42

SELECT lesson_param_modes.describe('42'::text);
-- text: 42
```

### Unknown literals

An uncast string literal is treated by PostgreSQL as type `unknown` during overload resolution. With multiple overloads, the chosen candidate may differ from what you intended or fail as ambiguous.

Cast explicitly when targeting a specific overload, especially in migrations, tests, and JDBC.

## 38. Cannot overload by OUT or return type alone

Suppose you already have:

```sql
lesson_param_modes.double_value(
    IN integer,
    OUT integer
)
```

You cannot create another function **with the same name and identical input types** differing only by `OUT text` and expect it to be a valid overload. PostgreSQL never selects a function based solely on expected result type.

Similarly:

```text
f(IN x integer, OUT y integer)
f(IN x integer, OUT y text)
```

are not distinct input signatures.

### Why?

When the parser encounters `f(10)`, it must resolve the routine from its name and input argument types before knowing how the result will be used. Differing only in output would make resolution ambiguous.

If you need an API with a completely different return type, consider **renaming** it or giving it a **genuinely distinct input signature**—never insert dummy parameters just to trick overloading.

## 39. Overloading with DEFAULT: easy to make ambiguous

Suppose the same schema contains:

```text
calculate(integer)
calculate(integer, integer DEFAULT 1)
```

A call like `calculate(7)` can match multiple definitions under default-argument and overload resolution rules.

### How to avoid this

- Do not add default parameters arbitrarily to a family of same-named overloads.
- Use distinct, descriptive names when functions serve different purposes.
- For critical APIs, audit existing call sites before migrating.
- Cast input parameters whenever needed to disambiguate overloads.
- Keep untrusted schemas out of `search_path` where calls could be hijacked.

A syntactically valid overload is not necessarily a usable or safe API.

## 40. VARIADIC and overload resolution

`VARIADIC` allows an array-style signature to accept multiple arguments of the element type. If another overload accepts a fixed number of scalar arguments, call resolution depends on precedence, type rules, and schemas.

Consider an API family:

```text
score(integer, integer)
score(VARIADIC integer[])
```

A call `score(1,2)` involves both candidates; avoid designing such overloads unless truly required. The risk increases further with `unknown` literals, default parameters, and an untrusted `search_path`.

### Recommendation

If a function accepts an SQL array as the primary Java interface, name it `score_array(integer[])`. If you want multi-argument SQL syntax, name it `score_values(VARIADIC integer[])`. Two clear names usually beat clever overloads that save a few characters.

## 41. Catalog: inspecting function/procedure definitions

PostgreSQL stores routines in `pg_catalog.pg_proc` and schemas in `pg_catalog.pg_namespace`.

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind AS routine_kind,
    p.oid::regprocedure AS identity,
    pg_get_function_arguments(p.oid) AS all_arguments,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_result(p.oid) AS function_result
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'lesson_param_modes'
ORDER BY
    p.proname,
    pg_get_function_identity_arguments(p.oid);
```

### Reading the columns

- `prokind`: routine kind; `f` is a regular function, `p` is a procedure, and other values represent aggregate/window functions.
- `pg_get_function_arguments`: displays the declaration list including modes, names, and defaults where applicable.
- `pg_get_function_identity_arguments`: the argument list identifying the routine for operations like `ALTER`/`DROP`.
- `pg_get_function_result`: the function's return type; procedures do not use `RETURNS` like functions.
- `oid::regprocedure`: displays the routine with input types to distinguish overloads.

These helper functions are much easier to read than manually decoding all internal `pg_proc` arrays.

## 42. proargtypes, proallargtypes, proargmodes

The catalog stores:

| Column | Meaning |
|---|---|
| `proargtypes` | Type OIDs of **input-bearing arguments** used for routine identity/calling |
| `proallargtypes` | Type OIDs of all arguments when stored separately in full |
| `proargmodes` | Mode codes corresponding to each argument, if present |
| `proargnames` | Argument names in order |
| `pronargdefaults` | Number of input args with default expressions |
| `proargdefaults` | Internal representation of default expressions |

Common mode codes:

- `i`: IN.
- `o`: OUT.
- `b`: INOUT.
- `v`: VARIADIC.
- `t`: a `TABLE` column in the corresponding output.

When all parameters are `IN`-only, `proargmodes` may be NULL rather than storing a populated array; use catalog helper functions when you simply want to display declarations.

### Query to inspect raw metadata

```sql
SELECT
    p.proname,
    p.proargtypes,
    p.proallargtypes,
    p.proargmodes,
    p.proargnames,
    p.pronargdefaults
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'lesson_param_modes'
ORDER BY p.proname;
```

These are system internals, not business data tables; internal types and representations may vary across PostgreSQL versions.

## 43. DROP FUNCTION and DROP PROCEDURE with exact identity

To drop `sum_and_product`, which has two `IN integer` and two `OUT bigint` parameters:

```sql
-- DDL example with delete effect; run only when intentionally cleaning up the lab:
DROP FUNCTION IF EXISTS
    lesson_param_modes.sum_and_product(integer, integer);
```

Do not include the two `OUT bigint` parameters in the input identity list when dropping the function.

For a procedure:

```sql
DROP PROCEDURE IF EXISTS
    lesson_param_modes.add_to_counter(integer, integer);
```

In production, always fetch the exact identity from the catalog/`pg_get_function_identity_arguments`, review dependencies, and execute controlled migrations. **Never run DROP just to experiment with an API.**

### Why not use a bare DROP ROUTINE name?

If overloads exist, dropping by bare name can fail as ambiguous or affect the wrong object. Always use schema-qualified names and explicit identity types.

## 44. CREATE OR REPLACE cannot arbitrarily change return types

An existing function has:

```text
sum_and_product(integer, integer)
  RETURNS record with o_sum bigint, o_product bigint
```

Changing an OUT parameter from `bigint` to `text` is not a body-only edit. PostgreSQL restricts using `CREATE OR REPLACE FUNCTION` to alter the return type or output definition. You may need to:

1. Create a new function with a different name or version suffix.
2. Migrate clients to the new signature.
3. Check dependencies, views, and permissions.
4. Drop the old function via a proper migration once no clients remain.

Never treat adding or changing an OUT parameter as an "internal change that won't affect the app": column count, column names, types, and JDBC result mappings can all break.

## 45. Schema-qualified calls and search_path

If you write:

```sql
SELECT calculate_tax(100, 10);
```

PostgreSQL must search for the function across `search_path` and resolve overloads. If the path includes a schema where untrusted users can create routines, unqualified calls risk resolving the wrong routine or falling prey to overload hijacking.

In critical server-side code, write:

```sql
SELECT lesson_param_modes.discounted_price(
    100000::numeric,
    10::numeric
);
```

and configure object creation privileges on schemas appropriately.

### SECURITY DEFINER

Functions running with owner privileges via `SECURITY DEFINER` require strict control over `search_path` and dynamic object references. Never mistake parameter modes for a security mechanism: they only describe data interfaces.

## 46. NULL in IN, OUT, and INOUT

| Mode | With NULL | Risk |
|---|---|---|
| IN | Caller can pass SQL NULL if signature/body checks allow | NULL propagation or validation failure |
| OUT | Unassigned parameter may remain SQL NULL | Caller receives missing fields without an error |
| INOUT | Can accept NULL and return NULL or another value per logic | Ambiguity between "missing" and "reset" |
| VARIADIC | Array with NULL elements, whole array NULL, or empty | Aggregation/`unnest` has specific semantics |

### Example distinguishing NULL from default

```sql
SELECT lesson_param_modes.bump_default();
-- p_counter defaults to 0 then increments to 1

SELECT lesson_param_modes.bump_default(NULL);
-- Body uses COALESCE(NULL, 0), result is still 1
```

Without `COALESCE`, NULL plus 1 evaluates to NULL. That is standard SQL NULL propagation, not a special rule where "INOUT keeps its old value."

### When to use STRICT?

`STRICT` on a function skips executing the body when applicable inputs are NULL. Use it only when **you want NULL returned** and do not need to log or validate missing inputs inside the body. For routines that must raise custom exceptions, omit STRICT.

## 47. Controlling overflow and data types

In the sum/product example:

```sql
p_a::bigint * p_b::bigint
```

casts `integer` to `bigint` before multiplying to widen the intermediate range. Even `bigint` has limits; sufficiently large inputs can still overflow.

A function handling currency should use `NUMERIC` with explicit scale and rounding rules, rather than defaulting to floating point where exact arithmetic is required.

### Do not pick OUT types casually

If a row count can exceed `integer`, use `bigint`. If division can produce fractional values, `numeric`/`decimal` is better than `integer`. Output types are part of the API contract, not merely syntax to make the function compile.

## 48. Exceptions and SQLSTATE

Example:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.positive_square(
    IN p_value numeric,
    OUT o_square numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value IS NULL OR p_value <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Positive input required';
    END IF;

    o_square := p_value * p_value;
END;
$$;
```

`22023` is the SQLSTATE code for `invalid_parameter_value`. Choose error codes that match the real condition and never expose secrets in error messages.

### Transaction state after an error

In an explicit transaction, if a statement raises an unhandled exception (without a suitable exception block or savepoint), the transaction enters an aborted state and must be rolled back. Do not keep sending calls on the same transaction and ignore SQLSTATE `25P02`.

### Do not swallow errors with OUT false when atomicity is required

When a routine writes to multiple tables and one step fails, returning `o_success=false` after partial writes without rolling back leaves data inconsistent. Use exceptions, proper transaction boundaries, or explicit rollback handling.

## 49. Function volatility, STRICT, and parallel safety

PostgreSQL allows declaring behavioral attributes alongside parameter modes:

- `IMMUTABLE`: result never depends on mutable state outside inputs; fits pure calculations.
- `STABLE`: cannot modify the database and stays consistent within a single statement; can read stable state.
- `VOLATILE`: can change across calls or cause side effects.
- `STRICT`: skips the function body on NULL input where applicable.
- `PARALLEL SAFE/RESTRICTED/UNSAFE`: indicates parallel worker safety based on routine behavior.

`IN`/`OUT`/`INOUT`/`VARIADIC` modes **do not automatically determine** any of these attributes.

### A common design mistake

Never mark a function that reads current prices from a table as `IMMUTABLE` just because it takes one `IN product_id` and returns one `OUT price`. Table prices can change; declaring the wrong volatility lets the planner optimize under false assumptions.

## 50. Procedures and transaction control

Unlike functions, procedures can execute transaction control statements (`COMMIT`/`ROLLBACK`) **under specific conditions permitted by PostgreSQL**, such as an eligible top-level `CALL`.

However, **not every procedure is allowed to COMMIT**:

- A `CALL` inside an explicit transaction block can prohibit internal transaction control.
- Nested call chains and intervening statements affect eligibility.
- `SECURITY DEFINER` procedures or procedures with a `SET` clause have restrictions.
- Client frameworks or JDBC transaction managers may control the transaction scope.

### Recommendation

If your application uses Spring `@Transactional` or JDBC `setAutoCommit(false)`, keep the transaction boundary in the application unless you have a specific need and thoroughly understand PostgreSQL's rules. Never put `COMMIT` inside a procedure just because you assume "procedures always manage their own transactions."

`OUT`/`INOUT` parameters do not grant transaction control privileges; they are completely independent features.

## 51. Procedure with DML and business OUT results

Suppose we want to update inventory and return the remaining stock. We need a table:

```sql
CREATE TABLE lesson_param_modes.inventory (
    product_id bigint PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity >= 0)
);

INSERT INTO lesson_param_modes.inventory (
    product_id, quantity
)
VALUES (1001, 15);
```

A procedure that atomically reserves stock conditionally:

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.try_reserve(
    IN p_product_id bigint,
    IN p_units integer,
    OUT o_reserved boolean,
    OUT o_remaining integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_units IS NULL OR p_units <= 0 THEN
        RAISE EXCEPTION 'Units must be positive';
    END IF;

    UPDATE lesson_param_modes.inventory
    SET quantity = quantity - p_units
    WHERE product_id = p_product_id
      AND quantity >= p_units
    RETURNING quantity INTO o_remaining;

    o_reserved := FOUND;

    IF NOT o_reserved THEN
        o_remaining := NULL;
    END IF;
END;
$$;
```

Calling from SQL (on server versions supporting OUT-only procedures):

```sql
CALL lesson_param_modes.try_reserve(
    1001::bigint,
    3,
    NULL,
    NULL
);

-- Can return o_reserved=true, o_remaining=12
```

### Why is this an atomic UPDATE?

`UPDATE ... WHERE quantity >= p_units` runs under PostgreSQL's concurrency control, so checking and decrementing happen in one atomic statement—far safer than having the application read `quantity` and write back a computed value from a stale snapshot.

### What is still missing for production?

- Tenant/ownership scope checks on the product.
- Idempotency for reservation requests.
- Coordination with order/payment transactions.
- Timeout/deadlock handling and retry policies.
- Ledger/audit logging where business rules require it.
- Distinguishing "product does not exist" from "insufficient stock" if needed.

This example intentionally focuses on **OUT parameters + DML**, not a complete checkout implementation.

## 52. Distinguishing OUT results from RETURNING

In the previous procedure:

```sql
UPDATE ... RETURNING quantity INTO o_remaining;
```

`RETURNING` is DML syntax that returns values from the modified row. `INTO o_remaining` in PL/pgSQL assigns that value to the **OUT variable**.

Once the procedure finishes, `CALL` returns `o_remaining` to the client.

There are three distinct layers:

```text
UPDATE inventory
  └── RETURNING quantity
        └── INTO o_remaining (PL/pgSQL OUT variable)
              └── CALL result row (returned to client)
```

Do not confuse `UPDATE ... RETURNING` with a function's `RETURN` or a parameter's output mode. They work together, not as replacements for one another.

## 53. Do OUT and INOUT help avoid multiple round-trips?

A procedure can return multiple results in a single `CALL`, reducing how many separate SQL statements a client must send to fetch related values.

For example, `try_reserve` both updates stock and reports success plus remaining inventory.

However:

- Returning a multi-column result row does not mean zero network round-trips.
- Returned values must be consistent with transaction visibility.
- Consider the trade-off of coupling business logic tightly to the database versus the service layer.
- Never cram external non-PostgreSQL steps into a procedure expecting one CALL to transactionally govern HTTP or payment gateways.

Choose the application/database boundary based on **atomicity, latency, reuse, maintainability, and access control**, not merely parameter count.

## 54. JDBC: functions with IN parameters

For a scalar-returning function, JDBC typically uses `PreparedStatement` with `SELECT`:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static BigDecimal discount(
        Connection conn,
        BigDecimal price,
        BigDecimal percent
) throws SQLException {
    String sql = """
        SELECT lesson_param_modes.discounted_price(?, ?)
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setBigDecimal(1, price);
        ps.setBigDecimal(2, percent);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Function returned no row");
            }
            return rs.getBigDecimal(1);
        }
    }
}
```

Java passes the two `IN` arguments via placeholders and reads the return value from `ResultSet`. There is no third parameter representing the scalar RETURN.

### Data types

Use `BigDecimal` for `NUMERIC` values requiring exact precision; avoid casting through `double` when financial logic cannot tolerate floating-point rounding.

## 55. JDBC: functions with multiple OUT parameters

`sum_and_product` returns two columns:

```java
String sql = """
    SELECT o_sum, o_product
    FROM lesson_param_modes.sum_and_product(?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, 7);
    ps.setInt(2, 4);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long sum = rs.getLong("o_sum");
            long product = rs.getLong("o_product");
            // Use the two result fields.
        }
    }
}
```

This is usually the **cleanest JDBC pattern** for functions with OUT parameters: query it as a `SELECT` returning columns. Never try to bind values for `OUT o_sum` or `OUT o_product` in `PreparedStatement`.

### JDBC getLong and NULL

If an integer/bigint output can be NULL, `ResultSet.getLong(...)` returns primitive `0`, so you must check `rs.wasNull()` to distinguish SQL NULL from zero. Alternatively, use `getObject` with appropriate driver type handling.

## 56. JDBC: calling a procedure with SQL CALL

The PostgreSQL JDBC driver supports `CALL`. The most straightforward approach is sending `CALL` directly via `PreparedStatement`:

```java
String sql = """
    CALL lesson_param_modes.add_to_counter(?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, 10);
    ps.setInt(2, 7);

    boolean hasResultSet = ps.execute();
    if (hasResultSet) {
        try (ResultSet rs = ps.getResultSet()) {
            if (rs.next()) {
                int updated = rs.getInt("p_counter");
                // updated = 17
            }
        }
    }
}
```

### Why use execute()?

`CALL` returns a result row when output parameters exist, whereas an `IN`-only procedure does not return one. Calling `execute()` lets the application check whether a `ResultSet` was returned instead of assuming every CALL behaves like a SELECT.

### SQL CALL with OUT-only

For `tax_quote`, the SQL statement can be:

```sql
CALL lesson_param_modes.tax_quote(?, ?, NULL, NULL)
```

The application binds **the two real inputs** and reads the output columns from the resulting row. This avoids registering OUT parameters through JDBC escape syntax with driver-specific settings.

## 57. JDBC CallableStatement: what you need to know

JDBC provides `CallableStatement` with `registerOutParameter`:

```java
CallableStatement call = conn.prepareCall(
    "{call lesson_param_modes.add_to_counter(?, ?)}"
);
```

However, in **PostgreSQL JDBC**, the `{call ...}` escape syntax may be translated into either `SELECT` or `CALL` depending on **`escapeSyntaxCallMode`** and driver configuration/version.

### Recommendations

- If calling a **procedure**, ensure the driver configuration causes escape syntax to emit an actual `CALL`.
- A commonly used setting is `escapeSyntaxCallMode=callIfNoReturn` per pgJDBC documentation where appropriate.
- For value-returning functions, plain `SELECT` with `ResultSet` is usually simpler.
- When using `registerOutParameter`, verify exact JDBC types and driver/connection behavior.
- Never write code assuming `{call ...}` has identical transaction semantics across all JDBC drivers.

The previous section used direct SQL `CALL` to minimize dependence on driver escape translation.

## 58. JDBC and VARIADIC arrays

In Java, if you already have an array:

```java
Integer[] values = {1, 2, 3, 4};
```

Create an SQL array and pass it to a VARIADIC function using explicit syntax:

```java
import java.sql.Array;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

Array sqlArray = conn.createArrayOf(
    "integer",
    values
);

try {
    String sql = """
        SELECT lesson_param_modes.sum_values(VARIADIC ?::integer[])
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setArray(1, sqlArray);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                long total = rs.getLong(1);
            }
        }
    }
} finally {
    sqlArray.free();
}
```

### Why not generate SQL with 1,000 question marks?

A single SQL array parameter keeps the SQL string stable, improves prepared statement reuse, and avoids interpolation bugs. For very large datasets, still measure memory and network cost and consider staging/temporary tables or batching.

For an empty SQL array, `createArrayOf("integer", new Integer[0])` passes an empty array; make sure you understand the function's defined semantics for empty inputs.

## 59. Spring JdbcTemplate and OUT functions

A function with multiple OUT parameters can be queried directly:

```java
String sql = """
    SELECT o_sum, o_product
    FROM lesson_param_modes.sum_and_product(?, ?)
    """;

var result = jdbcTemplate.queryForObject(
    sql,
    (rs, rowNum) -> new SumAndProduct(
        rs.getLong("o_sum"),
        rs.getLong("o_product")
    ),
    7,
    4
);
```

`SumAndProduct` is an application-defined record or class. Do not include the two OUT parameters in the JDBC input bindings.

### Spring transactions

When calling a procedure that modifies multiple tables, Spring's transaction manager controls commit/rollback via `@Transactional` when properly configured. Never use a procedure with internal `COMMIT` inside a Spring-managed transaction unless you have verified PostgreSQL's rules and transaction boundaries.

## 60. Difference between an OUT row and a multi-row result set

A procedure `CALL` can return **one row containing output columns**.

A `RETURNS TABLE` function can return **multiple rows**:

```sql
SELECT *
FROM lesson_param_modes.classify_values(1, 100);
```

Never design output parameters like:

```text
OUT row1
OUT row2
OUT row3
...
```

to simulate a collection. When the business case returns a dataset, a set-returning function or a normal `SELECT` query models it much more naturally.

An `OUT jsonb` parameter can return a flexible document, though it does not enforce a typed column schema contract the way a table does.

## 61. SQL functions with OUT

`OUT` is not exclusive to PL/pgSQL. An SQL-language function can also return output fields:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.text_stats(
    IN p_text text,
    OUT o_characters integer,
    OUT o_uppercase text
)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        char_length(p_text),
        upper(p_text);
$$;

SELECT *
FROM lesson_param_modes.text_stats('PostgreSQL');
```

Here, the `SELECT` query inside the body must **match the declared output structure**. There are no PL/pgSQL variables to assign field-by-field because the body is an SQL expression/query.

### When to use an SQL-language function?

If the logic is a simple expression or single SQL statement, `LANGUAGE sql` is concise. If you need branching, exception handling, loops, or procedural multi-step control, `PL/pgSQL` is usually easier to write.

## 62. Named parameters in complex SQL expressions

In an SQL function, input parameters can be referenced by name or positional markers:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.with_tax(
    p_amount numeric,
    p_tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT $1 * (1 + $2 / 100);
$$;
```

`$1` and `$2` inside an SQL function body refer to positional input arguments, **not JDBC placeholders**. Using parameter names:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.with_tax_named(
    p_amount numeric,
    p_tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_amount * (1 + p_tax_rate / 100);
$$;
```

### Note on ambiguity

If an input parameter shares its name with a column of a table referenced in the SQL function, name resolution can cause confusion or errors. Prefer `p_` prefixes for parameters, `v_` for local variables, and schema-qualified table references.

## 63. Parameter modes and security

A function:

```sql
CREATE FUNCTION admin_operation(
    IN p_user_id bigint,
    OUT o_success boolean
) ...
```

provides zero authorization protection simply by having `OUT o_success`. Callers can still attempt to pass another user's ID.

### Defense layers

1. Control `EXECUTE` privileges on the routine.
2. Control table privileges (or apply `SECURITY DEFINER` only with justification and auditing).
3. Verify user/tenant authorization from a trusted context.
4. Set a safe `search_path` in `SECURITY DEFINER` routines.
5. Never concatenate parameters into dynamic SQL to prevent injection.
6. Log audit records appropriately without leaking secrets.

### Explicit grants

Example:

```sql
-- Run only when role app_reader exists and has a privilege plan:
-- GRANT EXECUTE ON FUNCTION
--     lesson_param_modes.sum_and_product(integer, integer)
-- TO app_reader;
```

Never assume placing a function in its own schema automatically creates a security sandbox.

## 64. Dynamic SQL: parameter modes do not prevent injection

PL/pgSQL provides `EXECUTE` to run dynamic SQL, and passing data via `IN` parameters does not protect you if the body concatenates raw strings.

Example filtering by value:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.inventory_quantity(
    IN p_product_id bigint
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_quantity integer;
BEGIN
    EXECUTE
        'SELECT quantity
           FROM lesson_param_modes.inventory
          WHERE product_id = $1'
    INTO v_quantity
    USING p_product_id;

    RETURN v_quantity;
END;
$$;
```

In dynamic SQL, `USING` binds values safely instead of concatenating strings. If table or column names must be dynamic, they are SQL identifiers and require whitelisting and `format('%I', ...)`—never pass raw client input as an SQL fragment.

### When dynamic SQL is unnecessary

The example above uses dynamic SQL to illustrate `USING`, whereas a plain static `SELECT ... INTO` is simpler and safer. Only use `EXECUTE` when genuinely needed.

## 65. Parameter naming conventions to avoid confusion

A common convention:

| Role | Prefix suggestion | Example |
|---|---|---|
| Input | `p_` | `p_tenant_id`, `p_amount` |
| Output | `o_` | `o_total`, `o_success` |
| Input-output | `p_` or `io_` | `p_balance`, `io_counter` |
| Local variable | `v_` | `v_tax`, `v_count` |

This is a **naming convention**, not a PostgreSQL syntax rule. It makes PL/pgSQL code easier to read when queries reference columns with similar names.

### Do not ignore OUT column names for clients

An application reading a result set by **column index** might not notice when an OUT parameter is renamed, whereas an application calling `rs.getLong("o_total")` will break. Treat OUT column names as part of the public contract for widely consumed APIs.

## 66. Choosing modes by requirement

| Requirement | Recommendation |
|---|---|
| Compute a single value from one or more inputs | `IN` + `RETURNS type` |
| Return one value while naming the result in the signature | `IN` + one `OUT` |
| Return multiple fixed values | Multiple `OUT` or a composite type |
| Accept state and return mutated state | `INOUT` |
| Return a variable-sized set of rows | `RETURNS TABLE` / `SETOF` |
| Accept a variable number of arguments | `VARIADIC type[]` |
| Client already holds an SQL array | `IN type[]` or `VARIADIC type[]` called explicitly |
| Perform a business action returning one output row | Procedure + appropriate `OUT`/`INOUT` |
| Perform work needing no result row | Procedure with `IN` may fit |
| Standard SQL reporting/aggregation | Plain `SELECT`/view may suffice without a routine |

### A design note

Do not choose `INOUT` just to avoid writing `RETURNS`. If the caller actually passes an input and expects a **different kind of output**, `IN` + `RETURNS` or `OUT` usually expresses the intent more naturally.

## 67. Troubleshooting runbook for routine call errors

**Step 1 — Verify function vs. procedure.** `SELECT` differs from `CALL`.

**Step 2 — Print the actual signature:** query `pg_get_function_arguments` and identity arguments from the catalog.

**Step 3 — Check input count:** Function OUT-only parameters do not count toward passed arguments; procedure OUT-only parameters in SQL `CALL` require placeholders per PostgreSQL rules.

**Step 4 — Check types:** `integer` vs `bigint` vs `numeric` vs `text`; cast explicitly when overloads or NULL literals cause ambiguity.

**Step 5 — Check DEFAULTs:** are there overlapping callable overloads that create ambiguity?

**Step 6 — Check VARIADIC:** is the caller passing elements or an array? Did they write `VARIADIC ARRAY[...]` when passing an array?

**Step 7 — Check permissions/`search_path`:** use schema-qualified names and verify `EXECUTE` privileges.

**Step 8 — Check NULLs and body exceptions:** inspect SQLSTATE and transaction state.

**Step 9 — Check JDBC:** is an actual SQL `CALL` sent, or did JDBC escape syntax translate it to `SELECT`? Is the result set read properly?

**Step 10 — During migrations:** did a change to OUT shapes, return types, or parameter names break existing callers?

## 68. Common errors and what they mean

**"function ... does not exist"** may occur because of:

- Calling with the wrong argument count or types.
- Passing values for a function's OUT-only parameters as inputs.
- Missing explicit casts with overloads or `unknown` literals.
- The routine lives in another schema or `search_path` omits that schema.

**"procedure ... does not exist"** may occur because of:

- Calling a function with `CALL` by mistake.
- Wrong signature or the procedure hasn't been created yet.
- Using `CALL` with OUT forms unsupported by the server version.

**"function return type cannot be changed"** occurs when attempting to use `CREATE OR REPLACE` to change an existing function's output definition or return type.

**"current transaction is aborted"** appears after an earlier failure inside an explicit transaction; perform a rollback or restore a savepoint rather than continuing to call routines as if the transaction were healthy.

**"cannot commit while a subtransaction is active"** or transaction-control errors occur when a procedure tries to manage transactions in a disallowed context; check whether `CALL` is wrapped by a transaction or framework.

**"permission denied for function/procedure"**: parameter modes do not grant permissions; configure `EXECUTE`, schema privileges, and security definer controls.

## 69. Practice combining functions and procedures

Suppose you need a cost calculation interface and an inventory update interface. Distinguish them as:

- `discounted_price(IN price, IN percent) RETURNS numeric`: calculation function.
- `sum_and_product(IN a, IN b, OUT sum, OUT product)`: function returning multiple fields.
- `increase_counter(INOUT counter, IN delta)`: function returning updated state.
- `sum_values(VARIADIC integer[])`: function accepting a variable number of values.
- `try_reserve(IN product_id, IN units, OUT reserved, OUT remaining)`: procedure executing DML and returning one output row.

### Quick test

```sql
SELECT lesson_param_modes.discounted_price(
    100000::numeric,
    20::numeric
);

SELECT *
FROM lesson_param_modes.sum_and_product(2, 9);

SELECT lesson_param_modes.increase_counter(
    10::bigint,
    3::bigint
);

SELECT lesson_param_modes.sum_values(1, 2, 3, 4);

SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3, 4]::integer[]
);
```

### What to observe

No output-only arguments are passed when calling functions with `SELECT`. `INOUT` participates as an input, so `increase_counter` takes two inputs in the example. `VARIADIC` accepts either individual scalars or a whole array prefixed with the `VARIADIC` keyword.

## 70. Testing a DML procedure in a lab transaction

Assuming `inventory` and `try_reserve` have been created:

```sql
BEGIN;

SELECT product_id, quantity
FROM lesson_param_modes.inventory
WHERE product_id = 1001;

CALL lesson_param_modes.try_reserve(
    1001::bigint,
    2,
    NULL,
    NULL
);

SELECT product_id, quantity
FROM lesson_param_modes.inventory
WHERE product_id = 1001;

ROLLBACK;
```

### Why use ROLLBACK?

The lab wants to observe the change inside the transaction **without persisting the inventory change** for subsequent exercises. Since the example procedure does not `COMMIT`/`ROLLBACK` internally, the caller's explicit transaction controls whether changes are kept or discarded.

### What if CALL fails?

Inside an explicit transaction, an unhandled exception puts the transaction into a failed state requiring `ROLLBACK`. Do not keep issuing updates inside an aborted transaction.

## 71. Writing small assertions in PL/pgSQL

A `DO` block lets learners verify expectations about result values:

```sql
DO $$
DECLARE
    v_sum bigint;
    v_product bigint;
    v_swapped_first integer;
    v_swapped_second integer;
BEGIN
    SELECT o_sum, o_product
    INTO v_sum, v_product
    FROM lesson_param_modes.sum_and_product(7, 4);

    IF v_sum <> 11 OR v_product <> 28 THEN
        RAISE EXCEPTION 'Unexpected sum/product result';
    END IF;

    SELECT p_first, p_second
    INTO v_swapped_first, v_swapped_second
    FROM lesson_param_modes.swap_numbers(12, 99);

    IF v_swapped_first <> 99
       OR v_swapped_second <> 12 THEN
        RAISE EXCEPTION 'Unexpected swap result';
    END IF;
END;
$$;
```

### Why verify with SELECT?

For functions, output parameters become result columns when queried in `FROM`. Applications and tests can fetch them by column name.

In procedures, output parameters come from `CALL`. Inside PL/pgSQL, the caller supplies target variables for `OUT`/`INOUT`, as shown in earlier `DO` examples.

These assertion blocks are **learning examples**, not a substitute for a full test suite covering nulls, errors, concurrency, and overload resolution.

## 72. A good interface is more than the number of OUT parameters

Suppose a function must return:

```text
customer_id
order_count
total_paid
last_order_at
currency_code
```

There are at least three options:

1. Multiple fixed `OUT` columns.
2. `RETURNS TABLE` if returning a set of rows per customer.
3. A named composite type, or a regular view/query.

### When is a composite type worth considering?

If the return structure is reused across multiple routines, a named composite type expresses a clear shared contract. However, changing that type becomes a schema migration that affects dependent objects.

### When is RETURNS TABLE more appropriate?

When returning multiple rows of the same shape. If the function returns one summary record for **a single customer**, multiple OUT parameters can be clean. If it returns statistics for **all customers**, `RETURNS TABLE`/`SETOF` is the right model.

### Avoid routines with excessive parameters

A procedure with 25 IN/OUT fields easily causes:

- Argument order mistakes in `CALL`.
- Poor backward compatibility.
- Difficult NULL/default testing.
- Cumbersome JDBC mapping.
- Hard-to-maintain permission and validation consistency.

Consider splitting the interface by business responsibility, using composite inputs/outputs where appropriate, or using direct SQL `SELECT` queries if a routine adds no real value.

## 73. Documenting a routine's signature

A public routine should be documented with:

- Schema-qualified name.
- Input types and required constraints.
- Mode of each parameter.
- Default values, if any.
- Return shape: scalar, composite, result row, or set of rows.
- NULL semantics.
- SQLSTATE codes for invalid inputs.
- Side effects and transaction expectations.
- `EXECUTE` privileges and tenant scoping.
- SQL and JDBC call examples.

A simple API contract table for the example:

| Field | Value |
|---|---|
| Routine | `lesson_param_modes.try_reserve` |
| Kind | Procedure |
| `p_product_id` | `IN bigint`, product ID |
| `p_units` | `IN integer`, positive unit count |
| `o_reserved` | `OUT boolean`, true when UPDATE succeeds |
| `o_remaining` | `OUT integer`, remaining stock after reservation; NULL if not reserved |
| SQL call | `CALL ... (product_id, units, NULL, NULL)` |
| Side effect | Decrements stock when sufficient inventory exists |
| Transaction | Caller-managed; does not self-commit |

Changing `o_remaining` from `integer` to `text` must be treated as a breaking change for type-dependent clients, even if the SQL output still looks "human-readable."

## 74. Deploying routine changes safely

### Changing the body without changing the interface

If only the internal logic changes while **input identity and return shape** stay identical, `CREATE OR REPLACE` may work after reviewing volatility, permissions, and dependencies.

### Adding an input parameter with a default

This can minimize the number of call sites needing edits, but verify:

- Input defaults and parameter order.
- Existing overloads.
- Named calls from Java/SQL.
- Resolution with `unknown`/NULL arguments.
- Legacy positional calls.

### Changing OUT names, types, or column count

This alters the results read by callers. Create a new versioned routine or run an explicit migration, switch clients, and only then drop the old routine—never assume `CREATE OR REPLACE` can swap return types in place.

### Changing IN to INOUT

The input type signature may look the same, yet **the return contract changes**; SQL/JDBC invocation and result retrieval may also change. Treat it as a breaking API change.

### Changing an IN array to a VARIADIC array

Callers may have to adjust how arrays are passed, add `VARIADIC` at call sites, or face altered overload resolution. This is not always a transparent syntax change.

## 75. Syntax cheat sheet

| Goal | Syntax pattern | How to call |
|---|---|---|
| Scalar-returning function | `(IN x int) RETURNS int` | `SELECT f(5)` |
| Single-OUT function | `(IN x int, OUT y int)` | `SELECT f(5)` |
| Multi-OUT function | `(IN x int, OUT a int, OUT b text)` | `SELECT * FROM f(5)` |
| INOUT function | `(INOUT x int)` | `SELECT f(5)` |
| IN procedure | `(IN x int)` | `CALL p(5)` |
| INOUT procedure | `(INOUT x int)` | `CALL p(5)`; returns output row |
| OUT procedure | `(IN x int, OUT y int)` | `CALL p(5,NULL)` at SQL level, on supported versions |
| VARIADIC function | `(VARIADIC xs int[])` | `SELECT f(1,2,3)` |
| VARIADIC passing an array | `(VARIADIC xs int[])` | `SELECT f(VARIADIC ARRAY[1,2,3])` |
| Set-returning | `RETURNS TABLE (col type, ...)` | `SELECT * FROM f(...)` |

**Note:** The table above illustrates patterns, not pre-created routines named `f`/`p`. When running queries, use the specific routines in the lab schema.

## 76. Practice exercises

### Exercise 1 — Default IN mode

Create `rectangle_area(width numeric, height numeric) RETURNS numeric` without writing `IN` explicitly. Call it with 4 and 6 and explain why both remain `IN` parameters.

### Exercise 2 — Named input

Call `discounted_price` with `p_percent => 10` placed before `p_price => 200000`. Does it produce the same result as positional notation in the declared order?

### Exercise 3 — IN is not pass-by-reference

Write a function that increments `p_number` in its body and executes `RETURN`. Demonstrate that the caller receives the new value through the return result rather than mutating an external SQL variable.

### Exercise 4 — Single scalar OUT

Write `double_value(IN p_value integer, OUT p_double integer)`. Call it with one argument, omitting `p_double`.

### Exercise 5 — Two OUT parameters

Use `sum_and_product` to return the sum and product of 9 and 4. Explain why `SELECT * FROM function` returns two columns.

### Exercise 6 — OUT and composite values

Compare `SELECT sum_and_product(9,4)` with `SELECT * FROM sum_and_product(9,4)`. Which form is easier to read in JDBC?

### Exercise 7 — Unassigned OUT

Create a function with two OUT parameters where one branch forgets to assign the second field. What does that field return? Propose validation or explicit assignment paths.

### Exercise 8 — Expressionless RETURN

Write a function with OUT `label`/`value` and use `RETURN;` in the NULL-input branch. Why shouldn't you arbitrarily write `RETURN (label,value)` when OUT parameters are declared?

### Exercise 9 — Single INOUT

Write `increase_counter(INOUT counter bigint, IN delta bigint)` and call it with 10 and 5. Explain the dual input/output role of `counter`.

### Exercise 10 — Double INOUT

Create a function swapping two `INOUT integer` variables. Read both columns after calling with `SELECT * FROM`.

### Exercise 11 — Combining IN/OUT/INOUT

Create a function that applies a fee to an initial balance and returns the updated balance plus a boolean success flag. Write two tests for sufficient and insufficient balance.

### Exercise 12 — Function vs. procedure

Create a function returning a number and a procedure emitting a NOTICE. Call them with `SELECT` and `CALL` respectively. What happens if you mix up the commands?

### Exercise 13 — INOUT procedure

Call `add_to_counter(10,7)` using `CALL`. What value appears in the result row?

### Exercise 14 — Procedure OUT parameters

On a supported PostgreSQL version, create `tax_quote(IN subtotal, IN rate, OUT tax, OUT total)`. Call it from SQL with `NULL` placeholders and read the two output columns.

### Exercise 15 — CALL inside PL/pgSQL

Write a `DO` block with a counter variable, call `add_to_counter`, and print the result. Why must an assignable variable be passed in the INOUT position?

### Exercise 16 — Procedure OUT inside DO

Inside a `DO` block, declare `v_tax`/`v_total` and call `tax_quote`. Why don't you pass literal `NULL` as in the top-level SQL CALL example?

### Exercise 17 — Set-returning function

Create `classify_values` using `RETURNS TABLE(value integer, parity text)` returning multiple rows. Compare it with a scalar function having two OUT parameters.

### Exercise 18 — RETURN QUERY

Write a PL/pgSQL function with `RETURNS TABLE` and `RETURN QUERY SELECT FROM generate_series`. Test the case where 0 rows are returned.

### Exercise 19 — VARIADIC scalar list

Create `sum_values(VARIADIC integer[])`, call it with 1, 2, 3, 4, and explain what variable type the body sees.

### Exercise 20 — VARIADIC array

Call the function from Exercise 19 with `VARIADIC ARRAY[1,2,3,4]::integer[]`. Why is the `VARIADIC` keyword required at the call site when passing an entire array?

### Exercise 21 — Empty VARIADIC

Call `sum_values(VARIADIC ARRAY[]::integer[])`. What is the result under the `SUM`/`COALESCE` definition in this lesson?

### Exercise 22 — NULL elements

Call `sum_values(VARIADIC ARRAY[1,NULL,3]::integer[])`. Explain how `SUM` handles NULL elements.

### Exercise 23 — NULL array

Call `sum_values(VARIADIC NULL::integer[])`. Write a PL/pgSQL version if business rules require distinguishing a NULL array from an empty array.

### Exercise 24 — VARIADIC with preceding input

Create `join_parts(separator text, VARIADIC parts text[])`. Call it with three string arguments and then with an SQL array.

### Exercise 25 — Regular array vs. VARIADIC?

Compare `sum_array(IN integer[])` with `sum_values(VARIADIC integer[])` in terms of declaration and invocation. If Java always sends an SQL array, which interface would you choose?

### Exercise 26 — DEFAULT parameter

Create `round_to(value numeric, scale integer DEFAULT 2)`. Call it with and without `scale`; explain how passing explicit `NULL` differs from omitting the argument.

### Exercise 27 — INOUT default

Call `bump_default()`, `bump_default(40)`, and `bump_default(NULL)`. Determine the resulting value via `DEFAULT` and `COALESCE` in each case.

### Exercise 28 — Positional/named/mixed

Create a function with three inputs where the last two have defaults. Write valid positional, named, and mixed calls; identify a scenario prone to parameter-order errors.

### Exercise 29 — Overloading by input

Create two functions `describe(integer)` and `describe(text)`. Call them with explicit casts to guarantee the intended overload is selected.

### Exercise 30 — No overloading by OUT

Explain why you cannot create two functions with the same name and identical input types differing only in `OUT integer` and `OUT text` to dispatch by return type.

### Exercise 31 — Overload and default ambiguity

Analyze an overload family `f(integer)` and `f(integer, integer DEFAULT 1)`. Why can a single-argument call become ambiguous?

### Exercise 32 — System catalog

Query `pg_proc`, `pg_get_function_arguments`, and `pg_get_function_identity_arguments` for the lab schema. Locate at least one `i`, `o`, `b`, and `v` mode.

### Exercise 33 — DROP with exact signature

Write a `DROP FUNCTION` statement for `sum_and_product(integer,integer)` without placing OUT types in the input identity. Do not execute it if you still need the practice routines.

### Exercise 34 — Return type migration

A client currently reads an `OUT integer`; you want to change it to `text`. Propose a migration with a new version, dependency checks, and caller transition.

### Exercise 35 — SQLSTATE

Call `positive_square(-2)`. Classify the error using `SQLSTATE 22023` and explain the transaction state upon error.

### Exercise 36 — Procedure transactions

Call `try_reserve` inside `BEGIN ... ROLLBACK` and compare inventory before and after. Why shouldn't you put `COMMIT` inside the procedure when the caller manages the transaction?

### Exercise 37 — JDBC multi-OUT function

Write a `PreparedStatement` running `SELECT o_sum,o_product FROM sum_and_product(?,?)`. Why do you bind only two inputs and read two result columns?

### Exercise 38 — JDBC CALL

Use `PreparedStatement` to send `CALL add_to_counter(?, ?)`, invoke `execute()`, and read the result row. Explain how this differs from `CallableStatement` escape syntax.

### Exercise 39 — JDBC VARIADIC

Create a `java.sql.Array` from `Integer[]`, bind it into `SELECT sum_values(VARIADIC ?::integer[])`, and release resources afterward. When should you choose a non-variadic array input?

### Exercise 40 — Business system design

An order management system needs to:

- Calculate discounts from price/rate.
- Return subtotal and tax together.
- Accept a list of multiple product IDs.
- Atomically decrement inventory if stock is sufficient.
- Be called from Java/Spring.
- Block requests for unauthorized tenants.

Propose:

1. Which routines should be `IN+RETURNS` functions and which should use `OUT`?
2. When does `INOUT` genuinely express the business intent?
3. Should you use `VARIADIC` or a regular SQL array for the product ID list?
4. What DML procedure is needed for success/remaining outputs and what should its transaction scope be?
5. How will you design privileges, SQLSTATEs, idempotency, and JDBC mappings?
6. If a new OUT column is added later, how will you roll it out without breaking existing clients?

## Conclusion

**`IN`, `OUT`, `INOUT`, and `VARIADIC` are the four ways to describe data direction and shape in PostgreSQL function and procedure signatures.** `IN` passes values into the routine and is the default mode. `OUT` defines output values and is excluded from a function's input identity list. `INOUT` both accepts an initial value and returns a final value, so it counts as both input and output. `VARIADIC` allows passing multiple scalar arguments of a compatible element type or passing an SQL array using the `VARIADIC` keyword at the call site.

**Do not confuse functions with procedures:** functions are invoked via `SELECT` or inside expressions and can return scalars, composites, or sets of rows; procedures are invoked via `CALL` and can return a single output row when using `OUT`/`INOUT`. In particular, functions never take `OUT`-only arguments from the caller, whereas SQL `CALL` for procedures with `OUT`-only parameters may require `NULL` placeholders. When `CALL` runs inside PL/pgSQL, those output positions map to **target variables**.

Choose the interface to fit the business requirement: a single scalar fits `RETURNS`; a few fixed outputs fit `OUT`; a multi-row dataset requires `RETURNS TABLE`/`SETOF`; and a dynamic input list fits `VARIADIC` or a standard SQL array. Always enforce **NULL semantics, data types, overloading/default safety, argument naming, privileges, `search_path`, transaction boundaries, and SQLSTATE**, because parameter modes do not automatically provide validation or authorization.

In Java/JDBC applications, code is usually clearest when calling functions with `SELECT` and reading from `ResultSet`, and calling procedures via SQL `CALL` or properly configured `CallableStatement`. Always bind parameters, control transaction boundaries explicitly, and treat changes to `OUT` types or names as breaking contract changes. When these rules are clear, PostgreSQL functions and procedures become reusable, strongly typed, and maintainable data APIs rather than a collection of similarly spelled statements with unpredictable behavior.
