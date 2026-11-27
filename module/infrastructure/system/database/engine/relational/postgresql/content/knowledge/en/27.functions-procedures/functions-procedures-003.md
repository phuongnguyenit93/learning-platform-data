# Default Arguments, Named Parameters, and Overloading in PostgreSQL

## 1. Why is function parameter design part of the SQL contract?

A sales system needs to calculate an order total. Initially it takes only two parameters:

```sql
SELECT calculate_total(100000, 2);
```

Later, business rules require support for discounts, rounding, and currency. If you continually shift argument positions and ordering without a clear convention, existing SQL queries become easy to misread or break outright.

PostgreSQL provides three key mechanisms:

- **Default arguments:** allow callers to omit optional parameters.
- **Named arguments:** pass values by parameter name rather than solely by position.
- **Overloading (function/procedure overloading):** multiple routines sharing the same name with **different input parameter type lists**.

Example:

```sql
CREATE FUNCTION app.calculate_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
...
```

Callers can then express invocations as:

```sql
SELECT app.calculate_total(100000);
SELECT app.calculate_total(100000, 2);
SELECT app.calculate_total(
    p_unit_price => 100000,
    p_discount_rate => 0.10
);
```

All three forms start from the same definition, yet carry different implications for optionality, readability, and backward compatibility when evolving database APIs.

### Learning objectives

After this lesson, you can:

1. Declare default arguments accurately for `CREATE FUNCTION` and `CREATE PROCEDURE`.
2. Explain the rule: **all input parameters following a parameter with a DEFAULT must also have a DEFAULT**.
3. Call routines using **positional**, **named**, and **mixed** notation.
4. Distinguish **omitting an argument** from **explicitly passing NULL**.
5. Understand the evaluation semantics of default expressions that depend on time or data.
6. Identify overloads based on **name + input parameter type list**, not return type or parameter names.
7. Interpret `function ... does not exist` and `function ... is not unique` errors.
8. Recognize ambiguity pitfalls caused by default arguments, untyped literals, and implicit casts.
9. Use explicit casts and schema-qualified calls to guide resolution.
10. Design sustainable routine APIs during refactoring, avoiding parameter renames that break named calls.
11. Distinguish calling a **function** with `SELECT` from calling a **procedure** with `CALL`.
12. Inspect overloads via `pg_proc`, `regprocedure`, `pg_get_function_arguments`, and `psql` tools.
13. Apply privilege, `search_path`, and security best practices when using routines in applications.
14. Practice and self-check using SQL examples with expected outputs.

---

## 2. How do functions and procedures differ?

Both are **routines** in PostgreSQL and can accept arguments, though their usage differs significantly.

| Criterion | Function | Procedure |
|---|---|---|
| Declaration | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Common SQL call | `SELECT schema.f(...)` | `CALL schema.p(...)` |
| Usable as an expression in SELECT/WHERE | Yes, given suitable type/attributes | Cannot be called directly in SELECT like a function |
| Returning values | `RETURNS ...`, `RETURNS TABLE`, OUT/INOUT | Can return OUT/INOUT via CALL result depending on definition |
| Executing multiple statements | Yes, via PL/pgSQL or eligible SQL | Yes |
| Internal transaction control | Cannot arbitrarily COMMIT/ROLLBACK like a procedure | Permitted under certain top-level CALL conditions |
| Named/default arguments | Yes | Yes |
| Overloading by input types | Yes | Yes |

This lesson focuses on the **parameter contract**. Do not choose a procedure merely because you want multiple parameters; a simple function with default and named arguments is usually sufficient for side-effect-free calculations.

### 2.1. A function is not a procedure "with different syntax"

Wrong:

```sql
-- For a function named calculate_total:
CALL app.calculate_total(100000);
```

Right:

```sql
SELECT app.calculate_total(100000);
```

Conversely, for a procedure `write_audit`, use `CALL`; do not assume you can call `SELECT write_audit(...)`.

### 2.2. Calling routines with schema-qualified names

This guide will use:

```sql
routine344.function_name(...)
routine344.procedure_name(...)
```

rather than relying on `search_path`. This makes it explicit which routine is selected and reduces the risk of name collisions across schemas.

## 3. Preparing the practice environment

Run these examples in a **learning PostgreSQL database**; never run routine creation or alteration DDL in a production schema without migration review.

```sql
CREATE SCHEMA IF NOT EXISTS routine344;

SHOW server_version;
SHOW search_path;
```

Examples follow modern PostgreSQL syntax. On older servers, check exact support for procedures, `CALL`, output argument semantics, and options used.

### 3.1. Avoid generic object names in the public schema

Names like `sum`, `count`, `round`, or `format` can collide with built-in functions or extension routines. Using a dedicated schema and descriptive names prevents accidental resolution.

### 3.2. Guide to expected errors

Some sections include SQL marked **"intentionally errors"** to illustrate rules. Do not execute an entire script containing intentional errors inside a single transaction expecting subsequent statements to succeed. Once a transaction errors, you must issue `ROLLBACK` or handle a savepoint.

## 4. First function with default arguments

Create a total calculation function with three parameters:

```sql
CREATE OR REPLACE FUNCTION routine344.invoice_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(
        p_unit_price * p_quantity * (1 - p_discount_rate),
        2
    );
$$;
```

**Contract meaning:**

- `p_unit_price`: required, `numeric`.
- `p_quantity`: optional, defaults to 1.
- `p_discount_rate`: optional, defaults to 0.
- Returns `numeric` rounded to two decimal places.

### 4.1. What this function does not guard against

This function only demonstrates parameters. It **does not reject** negative quantities, negative unit prices, or discount rates below 0 or above 1. Real systems must enforce corresponding constraints, domains, or validation—especially in financial calculations.

### 4.2. What does IMMUTABLE mean here?

Given the same numeric arguments, this illustrative function returns the same result and reads neither tables nor clocks. Hence `IMMUTABLE` is appropriate.

Never attach `IMMUTABLE` to a function that queries mutable tables or calls `now()` merely hoping to "boost performance."

## 5. Positional notation: passing arguments by position

Passing three arguments:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2,
    0.10::numeric
) AS total_amount;
```

Calculation:

```text
100000 × 2 × (1 - 0.10) = 180000.00
```

Passing two arguments:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2
) AS total_amount;
```

PostgreSQL applies the default `p_discount_rate = 0`; result:

```text
200000.00
```

Passing only one argument:

```sql
SELECT routine344.invoice_total(
    100000::numeric
) AS total_amount;
```

Both `p_quantity` and `p_discount_rate` use their defaults:

```text
100000.00
```

### 5.1. Right-to-left omission rule

With positional notation, any **omitted arguments** must be trailing parameters at the end of the parameter list.

Allowed:

```text
invoice_total(unit_price)
invoice_total(unit_price, quantity)
invoice_total(unit_price, quantity, discount_rate)
```

However, if you want to supply `discount_rate` while **keeping the default quantity**, you cannot write it as if the second parameter were discount:

```sql
-- Semantic mistake: the second argument is quantity, not discount.
SELECT routine344.invoice_total(100000::numeric, 0.15);
```

Since the second parameter is declared `integer`, a decimal literal here can also trigger a type mismatch or unwanted conversion. The root issue is that **the second positional argument always maps to `p_quantity`**.

To skip `quantity` and set `discount`, use **named notation**.

## 6. Named notation: binding arguments by parameter name

Recommended syntax:

```sql
parameter_name => argument_expression
```

Example:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000::numeric,
    p_discount_rate => 0.15::numeric
) AS total_amount;
```

Because `p_quantity` is omitted, its default value 1 is used.

Result:

```text
85000.00
```

### 6.1. Named arguments can appear in any order

```sql
SELECT routine344.invoice_total(
    p_discount_rate => 0.15::numeric,
    p_unit_price => 100000::numeric
);
```

Still returns 85000.00. PostgreSQL binds by name rather than position.

### 6.2. Named arguments improve readability

Compare:

```sql
SELECT routine344.invoice_total(250000, 4, 0.075);
```

with:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 250000,
    p_quantity => 4,
    p_discount_rate => 0.075
);
```

In the second form, readers do not need to memorize positional meanings. This is especially valuable for boolean flags, time thresholds, quantities, or multiple configuration options.

### 6.3. Parameter names must match exactly

The following **uses the wrong parameter name**:

```sql
-- Intentionally errors:
SELECT routine344.invoice_total(
    unit_price => 100000
);
```

The routine declared `p_unit_price`, not `unit_price`. PostgreSQL reports that no matching function signature exists for that named call.

### 6.4. Names and case sensitivity

Unquoted identifiers in PostgreSQL are folded to lowercase. If a parameter is defined with a quoted identifier such as `"DiscountRate"`, named calls must also match that exact quoted name and casing.

In SQL APIs, prefer stable unquoted `snake_case` names.

## 7. Legacy named syntax: :=

PostgreSQL also supports the legacy syntax:

```sql
SELECT routine344.invoice_total(
    p_unit_price := 100000,
    p_discount_rate := 0.15
);
```

Inside a function call, `:=` is supported for backward compatibility as named-argument syntax.

However, prefer:

```sql
p_discount_rate => 0.15
```

to avoid confusion with PL/pgSQL variable assignment `:=` and stay consistent with modern SQL.

### 7.1. Named arguments are not a JSON map

The syntax:

```sql
p_quantity => 2
```

is part of the **routine invocation** parsed against the declared parameter list. It does not construct a JSON object or document.

Do not replace named arguments with:

```sql
SELECT routine344.invoice_total(
    '{"p_quantity":2}'::jsonb
);
```

unless you explicitly define an overload accepting `jsonb` and parse the document yourself.

## 8. Mixed notation: positional first, named after

PostgreSQL supports mixed calls:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    p_discount_rate => 0.15::numeric
);
```

Meaning:

- `100000` maps by first position → `p_unit_price`.
- `p_discount_rate` is passed by name.
- `p_quantity` is omitted → uses default 1.

Result: 85000.00.

An example with two positional arguments:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    3,
    p_discount_rate => 0.10
);
```

Result: 270000.00.

### 8.1. Positional arguments cannot follow named arguments

Wrong:

```sql
-- Intentionally produces a syntax error:
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    3,
    0.10
);
```

Rule:

```text
Positional arguments come first.
Once you start using named arguments,
subsequent arguments must also be named arguments.
```

### 8.2. Do not supply the same parameter twice

Wrong:

```sql
-- Intentionally errors:
SELECT routine344.invoice_total(
    100000::numeric,
    p_unit_price => 90000::numeric
);
```

`p_unit_price` already received positional value 100000, so named `p_unit_price` cannot be supplied again.

### 8.3. Mixed notation works well with clear required parameters

A common style:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    p_quantity => 3,
    p_discount_rate => 0.05
);
```

It keeps required inputs concise while explicitly naming optional choices.

## 9. DEFAULT in function declarations: ordering rule

PostgreSQL permits default values on **input parameters** including `IN` and `INOUT`, where applicable. Once an input parameter has a default, **every input parameter following it must also have a default**.

Valid:

```sql
CREATE FUNCTION routine344.sum_with_options(
    p_a integer,
    p_b integer DEFAULT 10,
    p_c integer DEFAULT 20
)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_a + p_b + p_c;
$$;
```

Invalid:

```sql
-- Intentionally errors: p_b has no default,
-- yet follows p_a which has a default.
CREATE FUNCTION routine344.invalid_defaults(
    p_a integer DEFAULT 10,
    p_b integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_a + p_b;
$$;
```

### 9.1. Why does this rule exist?

With positional calls, if a function were declared:

```text
f(a DEFAULT 10, b required)
```

then a call `f(20)` would have no unambiguous interpretation: does 20 bind to `a` or `b`? PostgreSQL requires all input parameters after the first defaulted parameter to also have defaults so trailing omission stays unambiguous.

Even though named notation could theoretically allow skipping an earlier parameter, PostgreSQL **still enforces** this rule at declaration time.

### 9.2. DEFAULT and the equals sign

Both forms are accepted:

```sql
p_quantity integer DEFAULT 1
```

or:

```sql
p_quantity integer = 1
```

Prefer `DEFAULT` consistently because it clearly signals a default value rather than a runtime assignment.

## 10. Omitting an argument vs. explicitly passing NULL

Suppose:

```sql
CREATE FUNCTION routine344.greeting(
    p_name text,
    p_salutation text DEFAULT 'Hello'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_salutation || ', ' || p_name;
$$;
```

Call:

```sql
SELECT routine344.greeting('An');
```

returns:

```text
Hello, An
```

However:

```sql
SELECT routine344.greeting(
    'An',
    NULL::text
);
```

returns **SQL NULL**, because string concatenation `||` with a NULL operand evaluates to NULL.

### 10.1. Why?

- **Omit** `p_salutation` → PostgreSQL uses `DEFAULT 'Hello'`.
- **Pass NULL** → you explicitly supplied SQL NULL; the default **does not substitute** for it.

This distinction is critical in real applications.

### 10.2. If you want NULL to fall back as well

Write the fallback logic explicitly:

```sql
CREATE FUNCTION routine344.greeting_null_safe(
    p_name text,
    p_salutation text DEFAULT 'Hello'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        coalesce(p_salutation, 'Hello')
        || ', ' ||
        coalesce(p_name, 'friend');
$$;
```

Now:

```sql
SELECT routine344.greeting_null_safe(
    'An',
    NULL::text
);
```

returns `Hello, An`.

However, **that is a business decision** inside the function body, not an automatic behavior of `DEFAULT`.

### 10.3. Inside STRICT functions

A function declared `STRICT` / `RETURNS NULL ON NULL INPUT` returns NULL immediately whenever any **effective argument** is SQL NULL, bypassing normal body execution.

The default value applies when an argument is omitted. If the caller supplies explicit NULL for a parameter with a default, `STRICT` still applies to that NULL.

## 11. Where and when is a default expression evaluated?

A default argument does not have to be a constant. Example:

```sql
CREATE FUNCTION routine344.effective_time(
    p_time timestamptz DEFAULT CURRENT_TIMESTAMP
)
RETURNS timestamptz
LANGUAGE sql
STABLE
AS $$
    SELECT p_time;
$$;
```

Call:

```sql
SELECT routine344.effective_time();
```

The call receives the evaluated default expression `CURRENT_TIMESTAMP`. This expression **is not frozen at CREATE FUNCTION time**.

### 11.1. CURRENT_TIMESTAMP in PostgreSQL

`CURRENT_TIMESTAMP` and `now()` reflect the **start time of the current transaction** per PostgreSQL semantics, not a wall clock advancing microsecond-by-microsecond within the same transaction.

Therefore, two calls inside the same transaction can produce the exact same timestamp.

### 11.2. Default expressions must be type-compatible

If you declare:

```sql
p_quantity integer DEFAULT 'abc'
```

PostgreSQL cannot convert the invalid string to `integer` as expected. The default expression must be **coercible** to the parameter's type.

### 11.3. Avoid flawed timestamp literal tricks

In some SQL contexts you might see timestamp literals like `TIMESTAMP 'now'`, where the literal can be converted to a fixed constant at parse/DDL time. If you want dynamic time evaluated per call, use proper time functions/expressions such as `CURRENT_TIMESTAMP` and understand transaction timestamp semantics.

### 11.4. Complex defaults are dependencies

If a default calls another function, accesses a sequence, or depends on configuration, consider:

- Who owns that function/default?
- Does it have side effects?
- Does it depend on caller privileges?
- If configuration changes, will calls omitting that argument behave differently?
- Does the default expression affect performance?

Do not assume default arguments are always harmless metadata.

## 12. Required parameters, optional parameters, and API design

A well-designed routine typically orders parameters as:

1. **Required**, frequently used parameters.
2. **Common optional** parameters.
3. Advanced options at the end, with clear defaults.

Example:

```sql
CREATE FUNCTION routine344.make_label(
    p_id bigint,
    p_prefix text DEFAULT 'INV',
    p_uppercase boolean DEFAULT false
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_uppercase THEN
            upper(p_prefix || '-' || p_id::text)
        ELSE
            p_prefix || '-' || p_id::text
    END;
$$;
```

Invocations:

```sql
SELECT routine344.make_label(1001);
SELECT routine344.make_label(1001, 'ORDER');
SELECT routine344.make_label(
    1001,
    p_uppercase => true
);
```

Results respectively:

```text
INV-1001
ORDER-1001
INV-1001
```

Because the default `INV` is already uppercase, the third call does not show a visible case difference, though it illustrates skipping `p_prefix`.

Try:

```sql
SELECT routine344.make_label(
    1001,
    p_prefix => 'invoice',
    p_uppercase => true
);
```

returns `INVOICE-1001`.

### 12.1. Avoid too many positional booleans

A call like:

```sql
SELECT routine344.some_report(1001, true, false, true, false);
```

is hard to read and easy to misorder. Named arguments reduce confusion, though if the number of options grows too large, consider restructuring the API rather than endlessly extending one routine.

## 13. Named arguments and name contracts: names are part of the API

A function with parameter:

```sql
p_discount_rate numeric
```

may be called across migrations, views, scripts, and services:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.10
);
```

If you later rename `p_discount_rate` to `p_rate`, callers using named notation will no longer recognize it as the same parameter.

### 13.1. Input parameter names are a compatibility contract

PostgreSQL enforces a constraint in `CREATE OR REPLACE FUNCTION`: it does not allow arbitrarily renaming an already-named input parameter from an earlier definition, because doing so would break existing named calls.

Renaming is not just "clean refactoring"; it is an SQL-level API change.

### 13.2. Choose names that don't leak internals

Prefer:

```text
p_customer_id
p_effective_date
p_include_cancelled
p_limit
```

over:

```text
p_x
p_tmp
p_v2
p_flag1
```

At the same time, do not turn parameter names into mini-essays; detailed contract notes belong in `COMMENT ON FUNCTION` or documentation.

### 13.3. Named calls and parameter reordering

At the call site, named notation decouples callers from argument order. However, **reordering parameters in the routine definition** alters the signature, impacting overloads, identity, defaults, and positional callers. Never assume named calls make every definition change backward compatible.

## 14. What is overloading?

PostgreSQL allows multiple functions with the **same name in the same schema** provided their **input parameter type lists** differ.

Example:

```sql
CREATE FUNCTION routine344.display_value(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer:' || p_value::text;
$$;

CREATE FUNCTION routine344.display_value(
    p_value text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value;
$$;
```

Two functions share the name `display_value` with different input parameter types.

Calls:

```sql
SELECT routine344.display_value(42::integer);
SELECT routine344.display_value('42'::text);
```

Results:

```text
integer:42
text:42
```

### 14.1. Function identity

In standard usage, PostgreSQL identifies a function by:

```text
schema + function name + input argument types
```

It **does not** use the return type to distinguish two overloads.

### 14.2. Overloading is a design choice, not unbounded polymorphism

PostgreSQL has type resolution rules and some polymorphic types, yet overloading does not guarantee the system will always guess the overload a developer had in mind.

Every additional overload increases the risk of:

- Calling the wrong overload via implicit casts.
- Calls becoming ambiguous.
- Breaking changes when adding defaults.
- Confusion with untyped string literals or NULLs.
- Shadowing/hijacking via `search_path` in untrusted schemas.

## 15. What does NOT create a distinct overload

### 15.1. Renaming a parameter alone

Two declarations:

```sql
CREATE FUNCTION routine344.same_signature(
    p_a integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_a;
$$;
```

and:

```sql
-- Intentionally errors: not a new overload,
-- because the input argument type is still integer.
CREATE FUNCTION routine344.same_signature(
    p_number integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_number * 2;
$$;
```

share the exact same identity by input types. Differing only in parameter name does not create two independent functions.

### 15.2. Changing RETURNS alone

You cannot simultaneously define:

```text
f(integer) RETURNS integer
f(integer) RETURNS text
```

as two overloads in the same schema distinguished only by return type.

If you need two representations:

- Use different names, or
- Use genuinely distinct input types if semantically meaningful.

### 15.3. Changing only the default value

A function:

```sql
f(p_x integer, p_y integer DEFAULT 10)
```

and:

```sql
f(p_x integer, p_y integer DEFAULT 20)
```

still have the same input signature `(integer,integer)`. Default expressions do not create a second overload.

### 15.4. Changing only OUT arguments

For function identity, `OUT` parameters are not used to distinguish overloads when input types remain identical. OUT shapes the returned data, not the input signature used to select the routine.

## 16. OUT and INOUT in functions: signature impact

PostgreSQL supports the following parameter modes:

| Mode | Meaning |
|---|---|
| `IN` | Input only; the default mode |
| `OUT` | Output; defines returned result value/columns |
| `INOUT` | Both input and output |
| `VARIADIC` | Parameter accepting a variable number of arguments via an array |

Example of a function with two output fields:

```sql
CREATE FUNCTION routine344.sum_and_difference(
    IN p_a integer,
    IN p_b integer,
    OUT sum_value integer,
    OUT difference_value integer
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    sum_value := p_a + p_b;
    difference_value := p_a - p_b;
END;
$$;
```

Call:

```sql
SELECT *
FROM routine344.sum_and_difference(10, 3);
```

Result:

```text
sum_value | difference_value
----------+-----------------
13        | 7
```

### 16.1. Why isn't OUT counted in identity?

For the function above, the input type list is:

```text
(integer, integer)
```

not:

```text
(integer, integer, integer, integer)
```

because the two OUT parameters are not passed as input values when calling via `SELECT`.

### 16.2. INOUT differs from OUT

`INOUT` accepts an input value and can carry a modified value back after execution. Because it participates in inputs, the type of an `INOUT` parameter is included in the routine's identity.

A function with INOUT fits when a parameter genuinely passes a value in and gets updated, whereas for pure calculations, explicit `RETURNS` scalar/record forms are usually clearer.

### 16.3. Which parameters can have defaults?

In `CREATE FUNCTION`, default values apply to input parameters, including `INOUT`. Do not attach `DEFAULT` to a pure `OUT` parameter as if it were an omissible input.

## 17. Selecting an overload by input type

When calling:

```sql
SELECT routine344.display_value(42::integer);
```

PostgreSQL finds an exact match for `integer`.

When calling:

```sql
SELECT routine344.display_value('42'::text);
```

it finds an exact match for `text`.

### 17.1. Explicit casts make intent clear

Syntax like:

```sql
42::integer
'42'::text
NULL::integer
DATE '2026-11-14'
```

tells both human readers and PostgreSQL which input type the author intended.

With multiple overloads, explicit casts often matter more than writing the shortest possible SQL.

### 17.2. Do not rely on output column aliases to select an overload

Example:

```sql
SELECT routine344.display_value(42) AS value_text;
```

The alias `value_text` does not influence overload selection. Input types drive resolution.

Likewise, assigning a result into a text column does not cause PostgreSQL to pick an overload returning text—you cannot create two overloads differing solely in `RETURNS` in the first place.

## 18. Unknown-typed string literals: a subtle source of bugs

In PostgreSQL, an untyped string literal like:

```sql
'42'
```

starts out typed as `unknown` so the parser can infer an appropriate type from context.

If overloads exist for `display_value(integer)` and `display_value(text)`:

```sql
SELECT routine344.display_value('42');
```

never assume it will pick `integer` just because "42" looks numeric. PostgreSQL follows function type resolution rules in which `unknown` string literals and preferred type categories can yield a choice different from intuition.

**The safer approach:** cast explicitly according to the API contract.

```sql
SELECT routine344.display_value('42'::integer);
SELECT routine344.display_value('42'::text);
```

### 18.1. Why implicit casting is not semantic guessing

A string:

```text
00123
```

might be a product code needing leading zeros preserved, not the integer 123.

A string:

```text
2026-11-14
```

might be free-form user text, a date, or a business identifier component.

These meanings must be enforced by **explicit data types in the contract**, not left to accidental implicit casts.

## 19. Untyped NULL and ambiguous calls

`NULL` by itself does not specify whether it is `integer`, `text`, or `date`.

Create two overloads:

```sql
CREATE FUNCTION routine344.describe_optional(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer variant';
$$;

CREATE FUNCTION routine344.describe_optional(
    p_value date
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'date variant';
$$;
```

Call:

```sql
-- Can trigger an ambiguous function call error:
SELECT routine344.describe_optional(NULL);
```

Two candidates match an untyped NULL validly, so PostgreSQL lacks enough information to decide whether the caller meant `integer` or `date`.

Fix with casts:

```sql
SELECT routine344.describe_optional(NULL::integer);
SELECT routine344.describe_optional(NULL::date);
```

These return respectively:

```text
integer variant
date variant
```

### 19.1. Not every NULL call is ambiguous

If only **one overload** exists, or if type resolution rules pick a unique candidate, an uncast NULL call may succeed. The takeaway is that **untyped NULL can cause ambiguity**, especially as overloads accumulate.

### 19.2. Prepared statements and typed parameters

In applications, bind explicit parameter types through the driver/API instead of building SQL strings with untyped literals, especially when a routine name has multiple overloads.

When needed, cast in SQL:

```sql
SELECT routine344.describe_optional($1::integer);
```

Note that `$1` is PostgreSQL prepared-statement parameter syntax, not an ad-hoc query runnable without bound values.

## 20. Overloading by parameter count and default values

An important question:

> If `f(integer)` already exists, can we also create `f(integer, integer DEFAULT 10)`?

PostgreSQL **allows the declaration**, because the input type lists of the two functions differ.

However, the call:

```sql
f(5)
```

can match **both**:

- `f(integer)` taking one argument.
- `f(integer,integer DEFAULT 10)` taking one argument and defaulting the second.

The result can be an **ambiguous function call**.

### 20.1. Creating an isolated ambiguity example

```sql
CREATE FUNCTION routine344.default_clash(
    p_x integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'one argument';
$$;

CREATE FUNCTION routine344.default_clash(
    p_x integer,
    p_y integer DEFAULT 10
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'two arguments with default';
$$;
```

Call:

```sql
-- Intentionally errors due to conflict between signatures with defaults:
SELECT routine344.default_clash(5);
```

PostgreSQL explicitly warns in its documentation that two functions like those above can prevent single-argument calls from resolving due to ambiguity.

### 20.2. Passing two explicit arguments resolves cleanly

```sql
SELECT routine344.default_clash(5, 20);
```

matches only the two-input overload.

### 20.3. How to fix the design

Instead of adding overloads with overlapping callable arities:

**Option A — Keep only the routine with defaults:**

```sql
DROP FUNCTION routine344.default_clash(integer);

SELECT routine344.default_clash(5);
```

Now only the two-parameter overload with `p_y` defaulting to 10 remains.

**Option B — Use distinct names:**

```text
format_short(integer)
format_with_options(integer, integer DEFAULT 10)
```

**Option C — Drop the default on the longer overload:**

```text
f(integer)
f(integer, integer)
```

Then a one-argument call will not match the two-argument overload when `p_y` has no default.

### 20.4. Do not add overlapping overloads for backward compatibility

If a function already has defaults, never add a same-named wrapper with overlapping callable arities without auditing all existing calls. A migration adding a new overload can suddenly make previously working SQL **ambiguous** without touching those queries.

## 21. Do named arguments always resolve overload ambiguity?

Not always.

Consider two overloads:

```sql
CREATE FUNCTION routine344.named_clash(
    p_id integer,
    p_mode text DEFAULT 'short'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text mode';
$$;

CREATE FUNCTION routine344.named_clash(
    p_id integer,
    p_limit integer DEFAULT 10
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer limit';
$$;
```

A call supplying only:

```sql
-- Can be ambiguous because both overloads accept p_id and
-- allow omitting the remaining optional parameter:
SELECT routine344.named_clash(p_id => 7);
```

However, when specifying a parameter name unique to one overload:

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_mode => 'full'
);
```

or:

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_limit => 20
);
```

resolution has a clear basis.

### 21.1. Do not rely on parameter names in place of clean signatures

Named notation can disambiguate overloads in specific cases, yet **valid call sets and type resolution** must remain clean overall. Adding overloads with defaults can still break positional callers or queries with `unknown` literals.

## 22. Function call resolution flowchart

A simplified mental model:

```text
SELECT schema.f(arguments...)
             |
             v
Find routines named f visible in schema/search_path
             |
             v
Evaluate argument count, named args, defaults, VARIADIC
             |
             v
Inspect input types and coercion eligibility
             |
             v
Prefer exact matches and type resolution rules
             |
      +------+------+
      |             |
   One match    Zero or multiple matches
      |             |
      v             v
   Execute     "does not exist" / "ambiguous"
```

This is a learning diagram, not the complete parser/planner algorithm. PostgreSQL has detailed rules covering:

- Schema visibility and `search_path`.
- Exact input type matches.
- Implicit conversions.
- `unknown` literal categories.
- Preferred types.
- Variadic expansion.
- Defaults and overload conflicts.

For tricky cases, consult the *Function Type Resolution* chapter in the official documentation rather than guessing "PostgreSQL will probably pick the closest overload."

## 23. Distinguishing "routine not found" from "ambiguous"

Two common errors:

### 23.1. No matching candidate

```text
ERROR: function ... does not exist
```

Possible causes:

- Wrong schema or `search_path`.
- Misspelled routine name.
- Wrong named argument name.
- Missing required parameter.
- Invalid argument count.
- Type has no eligible implicit cast.
- Calling a procedure using `SELECT` as if it were a function.

### 23.2. Multiple matching candidates

```text
ERROR: function ... is not unique
HINT: Could not choose a best candidate function.
```

Common causes:

- Multiple overloads with untyped literals or NULL.
- Overloads with defaults creating overlapping callable arities.
- `search_path` exposing competing signatures.
- `VARIADIC` expansion creating overlapping candidates.
- Implicit coercions producing equally ranked candidates.

### 23.3. Step-by-step troubleshooting

1. Confirm whether the object is a function or a procedure.
2. Qualify the routine's schema explicitly.
3. Inspect the list of overloads in the catalog.
4. Check parameter names and defaults.
5. Cast inputs intentionally.
6. If ambiguity persists, fix the overload/default design.
7. Retest all released application queries.

Never "try random casts until it compiles" without confirming the true business data type.

## 24. Numeric overloads: integer, bigint, numeric

For monetary amounts, never pick types casually.

Example:

```sql
CREATE FUNCTION routine344.type_route(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer';
$$;

CREATE FUNCTION routine344.type_route(
    p_value bigint
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'bigint';
$$;

CREATE FUNCTION routine344.type_route(
    p_value numeric
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'numeric';
$$;
```

Explicit calls:

```sql
SELECT routine344.type_route(10::integer);
SELECT routine344.type_route(10::bigint);
SELECT routine344.type_route(10::numeric);
```

Corresponding results:

```text
integer
bigint
numeric
```

### 24.1. Why do input literals matter?

PostgreSQL assigns default types to numeric literals based on value and syntax. The literal `10` may be typed as `integer`, whereas literals with decimal points follow different rules. For long-lived routine APIs, explicit casts prevent accidental reliance on parser defaults.

### 24.2. Never overload just to "change currency rounding"

If overloads accepting `numeric` and `double precision` apply different rounding or precision semantics, callers can silently get different answers based on input type. In financial logic, enforce one clear monetary type contract and test conversions.

## 25. Should multiple overloads share the same return type?

Overloading works well when the same **conceptual operation** applies across input types, such as:

```text
normalize_code(text)
normalize_code(uuid)
```

However, if two overloads perform **completely unrelated business actions**:

```text
process(text)  -> send email
process(int)   -> delete order
```

sharing a generic name causes confusion, increases security risk, and hurts readability.

Use overloading when:

- Behavior shares the same semantic meaning across different input types.
- There is a clear ergonomic benefit to the API.
- Call sites are explicitly typed or unambiguous.
- Existing callers are unaffected.
- Documentation covers every overload thoroughly.

## 26. Default values and backward compatibility during API evolution

Suppose initially we have:

```sql
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000;
$$;
```

Now we want to add an optional "packaging fee."

There are two approaches.

### 26.1. Adding an overload with a default can cause ambiguity

```sql
-- Avoid doing this without analyzing existing calls first:
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric,
    p_packaging_fee numeric DEFAULT 5000
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000 + p_packaging_fee;
$$;
```

Because `shipping_fee(numeric)` still exists, one-argument calls can become ambiguous as shown in Section 20.

### 26.2. An alternative avoiding overlap

Keep the old function and add a **required** two-parameter overload (no DEFAULT):

```sql
-- Design alternative only after resolving the conflict
-- with the two-parameter overload with DEFAULT in the previous example.
-- If you already created that overload, drop or alter it appropriately.
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric,
    p_packaging_fee numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000 + p_packaging_fee;
$$;
```

This is an **alternative migration pattern**—do not execute it immediately after Example 26.1 because their `(numeric,numeric)` identities collide. The goal is separating one-argument and two-argument calls unambiguously by arity.

Another option is introducing a distinct name like `shipping_fee_with_packaging`.

### 26.3. When migrating fully to a routine with defaults

A controlled migration can:

1. Audit callers, views, and dependencies.
2. Prepare the new routine in an appropriate version.
3. Migrate application calls to the named API or new name.
4. Remove the old overload once safe.
5. Introduce defaults once no arity conflict remains.
6. Verify permissions, owner, `search_path`, and dependencies.
7. Prepare a rollout and rollback plan.

Never drop a routine while views, triggers, procedures, or services still depend on it.

## 27. What can CREATE OR REPLACE FUNCTION change?

`CREATE OR REPLACE FUNCTION` is typically used to modify the **function body** while preserving identity and return type.

Example:

```sql
CREATE OR REPLACE FUNCTION routine344.make_label(
    p_id bigint,
    p_prefix text DEFAULT 'INV',
    p_uppercase boolean DEFAULT false
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_uppercase THEN
            upper(p_prefix || '-' || lpad(p_id::text, 8, '0'))
        ELSE
            p_prefix || '-' || lpad(p_id::text, 8, '0')
    END;
$$;
```

The identity remains:

```text
routine344.make_label(bigint, text, boolean)
```

Yet the behavior changed: the ID is zero-padded. That alters return values for **every caller**, so business compatibility must still be evaluated.

### 27.1. Changing input types does not replace the old routine

If you change:

```text
p_id bigint
```

to:

```text
p_id text
```

the signature changes, so PostgreSQL treats it as a **separate** routine (creating an overload if allowed) rather than updating the `bigint` overload.

### 27.2. Changing the return type is not allowed via simple OR REPLACE

A function with the same input signature changed from `RETURNS text` to `RETURNS integer` is neither a new overload nor an allowed in-place return-type edit via `CREATE OR REPLACE FUNCTION`.

Plan a proper migration and review dependencies.

### 27.3. Parameter names also have restrictions

As noted in Section 13, PostgreSQL forbids arbitrarily renaming already-named input parameters during OR REPLACE; this protects named callers.

### 27.4. Ownership and grants

OR REPLACE differs from DROP + CREATE. Replacing the same identity preserves owner and grants per PostgreSQL semantics, whereas dropping and recreating loses grants and dependencies, requiring reapplication.

## 28. Function identity and DROP/ALTER statements

A function with defaults is still identified by its **complete input type list**, not by the minimum number of arguments a caller might pass.

For example, `invoice_total` has signature:

```text
routine344.invoice_total(numeric, integer, numeric)
```

To target the exact routine:

```sql
-- Syntax example only; DO NOT run if you want to keep the lab:
DROP FUNCTION routine344.invoice_total(
    numeric,
    integer,
    numeric
);
```

Do not write:

```sql
DROP FUNCTION routine344.invoice_total(numeric);
```

assuming defaults let you identify the function by one input type; DROP requires the full identity, and the single-type form will either target a different overload or fail as nonexistent.

### 28.1. ALTER FUNCTION also uses the full identity

Example:

```sql
ALTER FUNCTION routine344.invoice_total(
    numeric,
    integer,
    numeric
)
COST 50;
```

This modifies only that specific overload, not all routines sharing the name.

### 28.2. DROP FUNCTION ignores parameter names and OUT-only parameters

When identifying a routine for DROP, parameter names do not affect identity, and `OUT`-only parameters are not part of the input signature.

Always write the schema and complete input types explicitly, especially in migrations with overloaded routines.

### 28.3. Avoid uncontrolled CASCADE

`DROP FUNCTION ... CASCADE` can drop dependent objects automatically. In production, review dependencies first and never run CASCADE just to "clear errors" without knowing everything it will delete.

## 29. Procedures with default values

Create a lab audit table:

```sql
CREATE TABLE routine344.audit_events (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id bigint NOT NULL,
    event_kind text NOT NULL,
    actor_name text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
```

Create the procedure:

```sql
CREATE PROCEDURE routine344.write_audit(
    p_entity_id bigint,
    p_event_kind text DEFAULT 'CREATED',
    p_actor_name text DEFAULT 'system'
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO routine344.audit_events(
        entity_id,
        event_kind,
        actor_name
    )
    VALUES (
        p_entity_id,
        p_event_kind,
        p_actor_name
    );
END;
$$;
```

### 29.1. Invoking with CALL

```sql
CALL routine344.write_audit(1001);
```

Uses both defaults.

```sql
CALL routine344.write_audit(1002, 'UPDATED');
```

Uses default `actor_name='system'`.

```sql
CALL routine344.write_audit(
    p_entity_id => 1003,
    p_actor_name => 'operator'
);
```

Omits `p_event_kind`, receiving `'CREATED'`.

### 29.2. Inspecting inserted rows

```sql
SELECT
    entity_id,
    event_kind,
    actor_name,
    occurred_at
FROM routine344.audit_events
ORDER BY audit_id;
```

If all three CALLs run once on an empty table, expected rows:

| entity_id | event_kind | actor_name |
|---:|---|---|
| 1001 | CREATED | system |
| 1002 | UPDATED | system |
| 1003 | CREATED | operator |

There is no guarantee `occurred_at` differs across rows if the calls execute in the same transaction, because `now()` reflects transaction start time.

## 30. Procedures also support named and mixed notation

`CALL` accepts named arguments with the same syntax:

```sql
CALL routine344.write_audit(
    p_actor_name => 'batch-worker',
    p_entity_id => 1004,
    p_event_kind => 'RETRIED'
);
```

And mixed notation:

```sql
CALL routine344.write_audit(
    1005,
    p_actor_name => 'scheduler'
);
```

In the second example, `p_event_kind` defaults to `'CREATED'`.

### 30.1. Distinguish SQL CALL from PL/pgSQL CALL

When a procedure has `OUT`/`INOUT` parameters, passing and receiving outputs differs between top-level SQL `CALL` and `CALL` inside a PL/pgSQL block using variables. Furthermore, PostgreSQL versions vary in specific `OUT` parameter details.

When designing procedures that output multiple values, check the `CALL` documentation for your server version. Never assume an SQL `CALL` snippet and a PL/pgSQL `CALL` snippet are mechanically interchangeable.

### 30.2. OUT parameters do not turn a procedure into a function

A procedure with `OUT`/`INOUT` can return a result row from `CALL`, yet it still cannot be invoked as an expression via `SELECT p(...)`.

## 31. INOUT in procedures: a special case

Example of a procedure adjusting a numeric value:

```sql
CREATE PROCEDURE routine344.add_fee(
    INOUT p_amount numeric,
    IN p_fee numeric DEFAULT 0
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_amount := p_amount + p_fee;
END;
$$;
```

Calling from SQL:

```sql
CALL routine344.add_fee(
    100::numeric,
    p_fee => 15::numeric
);
```

The value returned through output parameter `p_amount` displays as:

```text
p_amount
--------
115
```

Calling:

```sql
CALL routine344.add_fee(100::numeric);
```

uses default `p_fee = 0`, returning 100.

### 31.1. INOUT is both part of identity and an output

Unlike pure `OUT`, `INOUT p_amount numeric` accepts an input value, so it is included in the input type list that defines the procedure's signature.

### 31.2. Do not overuse INOUT for pure calculations

If you only need a side-effect-free computation, an SQL function returning `numeric` is cleaner and more natural. Procedures with INOUT make sense when the `CALL` contract or procedural workflow genuinely calls for them.

## 32. Procedures and transaction control: limits to remember

One advantage of PostgreSQL procedures is their ability to perform transaction control **under certain permitted conditions**, though not every `CALL` may run `COMMIT`/`ROLLBACK` internally.

Typical limits include:

- If `CALL` executes **inside an explicit transaction block**, the procedure cannot perform transaction control the way top-level calls can.
- Procedures declared `SECURITY DEFINER` have transaction control restrictions.
- Procedures with an attached `SET` clause also have transaction control restrictions.
- Nested `CALL`/`DO` chains and intervening statements affect eligibility.
- PL/pgSQL and SQL-level `CALL` differ when using output variables.

This lesson on defaults, named parameters, and overloading **does not need** self-committing procedures to demonstrate parameters; examples rely on normal caller transactions.

### 32.1. Do not imply CALL always auto-commits

`CALL write_audit(...)` does not automatically start and commit an independent transaction regardless of caller context. If the application is inside a transaction and rolls back, the INSERT inside the procedure rolls back along with the transaction per standard PostgreSQL semantics.

## 33. How does overloading apply to procedures?

Multiple procedures can share the same name if their input type lists differ.

Example:

```sql
CREATE PROCEDURE routine344.log_message(
    p_message text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'message: %', p_message;
END;
$$;

CREATE PROCEDURE routine344.log_message(
    p_code integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'code: %', p_code;
END;
$$;
```

Calls:

```sql
CALL routine344.log_message('hello'::text);
CALL routine344.log_message(42::integer);
```

These emit the corresponding NOTICE messages. A procedure does not become an overload of a function with the **same name and input signature** in the same schema; PostgreSQL restricts colliding identities between functions and procedures.

### 33.1. Defaults can also make procedure calls ambiguous

If you have:

```text
log_event(bigint)
log_event(bigint, text DEFAULT 'CREATED')
```

then `CALL log_event(1)` hits the same signature overlap issue as functions.

Never create multiple procedures differing only in parameter count when one uses defaults without checking every caller.

## 34. VARIADIC: related to argument-count overloading, yet distinct

`VARIADIC` is neither a default argument nor an overload; it allows a single routine to accept a variable number of elements via an array parameter.

Example:

```sql
CREATE FUNCTION routine344.sum_integers(
    VARIADIC p_values integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT coalesce(sum(x), 0)::bigint
    FROM unnest(p_values) AS t(x);
$$;
```

Call:

```sql
SELECT routine344.sum_integers(1, 2, 3);
```

returns 6.

### 34.1. Calling with an array

```sql
SELECT routine344.sum_integers(
    VARIADIC ARRAY[1,2,3]::integer[]
);
```

With named notation, you can write:

```sql
SELECT routine344.sum_integers(
    VARIADIC p_values => ARRAY[1,2,3]::integer[]
);
```

### 34.2. Why does named notation with VARIADIC need care?

Individual elements expanded into a variadic array **do not have separate parameter names**. Thus you cannot write:

```sql
-- Intentionally errors / not valid variadic call syntax:
SELECT routine344.sum_integers(
    p_values => 1
);
```

To pass an array by name, use `VARIADIC p_values => ARRAY[...]` as documented.

### 34.3. VARIADIC and overloads can also collide

Candidates formed by expanding variadic arguments can compete with routines having regular fixed input types. PostgreSQL defines precedence rules, yet you should avoid using variadic just to sidestep clean overload design.

## 35. anyelement, anyarray, and polymorphic functions

PostgreSQL provides pseudo-types to support polymorphic functions. While flexible across argument types, they make **type resolution** subtler.

Conceptual example:

```sql
CREATE FUNCTION routine344.first_value(
    p_values anyarray
)
RETURNS anyelement
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_values[1];
$$;
```

Call with a concrete array:

```sql
SELECT routine344.first_value(
    ARRAY[10,20,30]::integer[]
);
```

Returns 10.

### 35.1. Explicit casts still matter when types are unclear

An array lacking a clear element type or an untyped NULL can prevent PostgreSQL from inferring the required polymorphic type.

### 35.2. Do not use polymorphism just to avoid a few sensible overloads

Polymorphic functions involve complex type inference rules. For important data-returning APIs, a small set of concretely typed overloads is often easier to understand and maintain.

## 36. SQL and PL/pgSQL functions with named parameters

For an SQL function:

```sql
CREATE FUNCTION routine344.double_value(
    p_number integer
)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_number * 2;
$$;
```

For a PL/pgSQL function:

```sql
CREATE FUNCTION routine344.double_value_pl(
    p_number integer,
    p_multiplier integer DEFAULT 2
)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_number * p_multiplier;
END;
$$;
```

Call:

```sql
SELECT routine344.double_value_pl(
    p_multiplier => 3,
    p_number => 10
);
```

Returns 30.

### 36.1. Using parameter names inside the function body

`p_number` and `p_multiplier` act as parameter variables and can be referenced directly in SQL or PL/pgSQL per language rules.

When writing SQL inside PL/pgSQL where a variable shares its name with a table column, ambiguity can occur. Common practices:

- Use the `p_` prefix for input variables.
- Use explicit table and column aliases.
- Never rely on an unqualified name that could resolve to either a column or a variable.

### 36.2. $1, $2 follow declaration order

In some function definitions, parameters can be referenced positionally as `$1`, `$2`. Even when callers pass named arguments in another order, PostgreSQL maps them to the declared positions.

The order of named arguments **at the call site** never rebinds `$1` inside the function body to whichever argument was listed first in the call.

## 37. Calling functions in SELECT, FROM, and WHERE

A scalar function can be invoked as an expression:

```sql
SELECT routine344.invoice_total(
    100000,
    p_quantity => 3
);
```

Or in the SELECT list of a table query:

```sql
WITH line_items(unit_price, quantity) AS (
    VALUES
        (100000::numeric, 2),
        (25000::numeric, 4)
)
SELECT
    unit_price,
    quantity,
    routine344.invoice_total(
        p_unit_price => unit_price,
        p_quantity => quantity
    ) AS line_total
FROM line_items;
```

Result:

| unit_price | quantity | line_total |
|---:|---:|---:|
| 100000 | 2 | 200000.00 |
| 25000 | 4 | 100000.00 |

### 37.1. Defaults apply per invocation

When a scalar function is used in a multi-row query, omitted parameters are handled per invocation within the execution context. Do not assume default values are always "substituted statically once" in a way that guarantees identical evaluation timing for volatile expressions.

### 37.2. Avoid careless use of volatile functions in filters

If a function causes side effects, placing it in `WHERE` or `ORDER BY` makes evaluation count and order dependent on the query plan. Never build business logic requiring exactly one side effect per row by stuffing a volatile function into an arbitrary query expression without safe plan and transaction design.

## 38. Querying pg_proc: seeing what overloads actually exist

PostgreSQL stores routine metadata in system catalogs. A useful query:

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_arguments(p.oid)
        AS full_arguments,
    pg_get_function_result(p.oid)
        AS result_type
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine344'
ORDER BY p.proname, identity_arguments;
```

Explanation:

- `pg_proc` stores metadata for functions, procedures, and other routines.
- `prokind='f'` indicates a function.
- `prokind='p'` indicates a procedure.
- `pg_get_function_identity_arguments` shows the argument list that identifies the routine.
- `pg_get_function_arguments` shows the declared arguments, including names, modes, and defaults.
- `pg_get_function_result` shows the function's return type.

### 38.1. Identifying an overload via OID/regprocedure

Example:

```sql
SELECT
    'routine344.display_value(integer)'::regprocedure
        AS integer_overload,
    'routine344.display_value(text)'::regprocedure
        AS text_overload;
```

`regprocedure` references a routine by name and input types, which is invaluable when inspecting catalog metadata or definitions for a specific overload.

### 38.2. Retrieving the definition

```sql
SELECT pg_get_functiondef(
    'routine344.invoice_total(numeric,integer,numeric)'
        ::regprocedure
);
```

This returns DDL representing the server's routine definition formatted by PostgreSQL. Never read `pg_proc.prosrc` directly assuming it always reconstructs every routine completely.

## 39. Using psql tools to inspect routine definitions

In `psql`, these meta-commands are helpful:

```text
\df routine344.*
\df+ routine344.*
\sf routine344.invoice_total(numeric, integer, numeric)
```

Exact syntax and output detail depend on the `psql` version. Commands starting with `\` are **psql meta-commands**, not SQL statements you can send verbatim via JDBC or clients without psql support.

### 39.1. Why inspect the catalog before editing?

If you see:

```text
invoice_total(numeric, integer, numeric)
invoice_total(numeric)
```

do not read one migration file and assume the second one is "old and safe to delete." It may be an overload still called by another service or causing ambiguity. Always cross-check definitions, grants, dependencies, and callers.

## 40. search_path can affect which overload is chosen

If a call omits the schema:

```sql
SELECT display_value(42);
```

PostgreSQL searches for routines based on visibility and `search_path`. Another schema may contain a routine with the same name and matching or implicitly convertible parameter types.

Consequently:

- Resolution can differ across connections with different `search_path` configurations.
- Overloads sharing names across multiple schemas follow specific search/precedence rules.
- Any schema allowing untrusted users to `CREATE` routines poses a security and availability risk.

### 40.1. Schema-qualified calls

Prefer:

```sql
SELECT routine344.display_value(42::integer);
```

especially in:

- Migration scripts.
- `SECURITY DEFINER` code.
- Admin commands.
- Multi-tenant services.
- Code requiring deterministic resolution by input type.

### 40.2. Schema-qualification does not eliminate all ambiguity

Even within a single schema, multiple overloads can still conflict due to defaults and implicit casts. Use explicit type casts or fix signature design.

### 40.3. Avoid untrusted schemas

Only trusted roles should hold `CREATE` privileges in schemas hosting application routines. Restrict schema `CREATE` rights, verify owners, and configure `search_path` following least privilege.

## 41. EXECUTE privileges and routine API security

A routine is a database API: anyone permitted to call a function or procedure can execute its logic and potentially read or modify data if privileges allow.

Inspect privileges:

```sql
SELECT
    p.proname,
    p.prokind,
    p.proacl
FROM pg_proc p
JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='routine344'
ORDER BY p.proname;
```

### 41.1. Never assume everyone should be allowed to call everything

PostgreSQL applies default privileges to functions and procedures, and under common defaults `EXECUTE` is granted to `PUBLIC` upon creation. For sensitive APIs, explicitly revoke and grant `EXECUTE` rights.

Example:

```sql
-- Run only when you are the owner or an authorized DBA and
-- have confirmed you are not revoking required privileges:
REVOKE ALL ON FUNCTION
    routine344.invoice_total(numeric, integer, numeric)
FROM PUBLIC;
```

Then grant `EXECUTE` only to the appropriate application roles per policy.

### 41.2. SECURITY DEFINER requires caution

A `SECURITY DEFINER` function runs with the owner's privileges under PostgreSQL security semantics. Unqualified object references or a `search_path` containing untrusted schemas can open object-shadowing attacks.

When `SECURITY DEFINER` is genuinely needed:

- Use it only when justified.
- Set a safe `search_path`.
- Schema-qualify critical object names.
- Restrict `EXECUTE` by role.
- Audit dynamic SQL and inputs.
- Test actual caller permissions.

Never mark a routine `SECURITY DEFINER` just to "make permission errors go away."

### 41.3. Defaults do not bypass permission checks

Default parameters do not grant free access. Operations inside a routine remain subject to security invoker/definer rules, grants, RLS, and transaction controls.

## 42. Named parameters, SQL injection, and dynamic SQL

Named arguments improve call readability, yet **do not prevent SQL injection**.

Use bound parameters safely:

```sql
SELECT routine344.invoice_total(
    p_unit_price => $1::numeric,
    p_quantity => $2::integer,
    p_discount_rate => $3::numeric
);
```

The application binds values through the driver. Never concatenate raw user input into SQL strings:

```text
"SELECT ... p_name => '" + userInput + "'"
```

### 42.1. Named arguments are not client placeholders

`p_unit_price => ...` is a **function parameter name**; `$1` or driver placeholders are SQL **bind parameters**. They serve completely different purposes.

### 42.2. Dynamic SQL in PL/pgSQL

If dynamic identifiers are required, use proper quoting/formatting such as `format('%I', identifier)` and pass values via `USING` where appropriate. Never turn client-supplied routine or column names into unchecked SQL.

## 43. Defaults, NULL, and handling invalid values

Parameter design must distinguish:

1. Omitted → uses default.
2. Passed as NULL → receives SQL NULL.
3. Present but out of valid range → reject per contract.
4. Valid type but invalid domain value (e.g., `quantity = 0` in a purchase) → enforce business validation.

### 43.1. Function validating unit price and quantity

Example using PL/pgSQL:

```sql
CREATE FUNCTION routine344.safe_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_unit_price IS NULL OR p_unit_price < 0 THEN
        RAISE EXCEPTION
            'unit price must be a nonnegative number'
            USING ERRCODE = '22023';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION
            'quantity must be a positive integer'
            USING ERRCODE = '22023';
    END IF;

    IF p_discount_rate IS NULL
       OR p_discount_rate < 0
       OR p_discount_rate > 1 THEN
        RAISE EXCEPTION
            'discount rate must be between 0 and 1'
            USING ERRCODE = '22023';
    END IF;

    RETURN round(
        p_unit_price * p_quantity * (1 - p_discount_rate),
        2
    );
END;
$$;
```

### 43.2. Call

```sql
SELECT routine344.safe_total(
    100000,
    p_discount_rate => 0.05
);
```

Result: 95000.00.

### 43.3. Omission vs. NULL

```sql
-- Uses default 1:
SELECT routine344.safe_total(100000);

-- Intentionally fails validation:
SELECT routine344.safe_total(
    100000,
    p_quantity => NULL::integer
);
```

The second statement does not fall back to the default; the function sees NULL and raises an error. This enforces the "quantity must be positive" contract.

## 44. Testing with a practice data table

Create a small table to combine the function with a data query:

```sql
CREATE TABLE routine344.order_lines (
    line_id integer PRIMARY KEY,
    unit_price numeric NOT NULL CHECK (unit_price >= 0),
    quantity integer NOT NULL CHECK (quantity > 0),
    discount_rate numeric NOT NULL DEFAULT 0
        CHECK (discount_rate BETWEEN 0 AND 1)
);

INSERT INTO routine344.order_lines(
    line_id, unit_price, quantity, discount_rate
)
VALUES
    (1, 100000, 2, 0.10),
    (2, 50000, 1, 0.00),
    (3, 200000, 3, 0.25);
```

Invoke the function with named arguments from table columns:

```sql
SELECT
    line_id,
    unit_price,
    quantity,
    discount_rate,
    routine344.safe_total(
        p_unit_price => unit_price,
        p_quantity => quantity,
        p_discount_rate => discount_rate
    ) AS line_total
FROM routine344.order_lines
ORDER BY line_id;
```

Expected result:

| line_id | unit_price | quantity | discount_rate | line_total |
|---:|---:|---:|---:|---:|
| 1 | 100000 | 2 | 0.10 | 180000.00 |
| 2 | 50000 | 1 | 0.00 | 50000.00 |
| 3 | 200000 | 3 | 0.25 | 450000.00 |

### 44.1. Here the default for discount is not used

Because the query passes `discount_rate` from the column for every row, PostgreSQL never uses the default `p_discount_rate = 0`. To use the default in a query, omit that argument or structure the call logic accordingly; passing NULL does not trigger the default.

## 45. Combining defaults and functions in query expressions

An example applying a fixed promotional discount across all rows:

```sql
SELECT
    line_id,
    routine344.safe_total(
        unit_price,
        p_quantity => quantity,
        p_discount_rate => 0.05
    ) AS promo_total
FROM routine344.order_lines
ORDER BY line_id;
```

### 45.1. A clean API for reports

If reports frequently apply the same 5% discount, you can create a clearly named wrapper:

```sql
CREATE FUNCTION routine344.promo_total_5_percent(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1
)
RETURNS numeric
LANGUAGE sql
AS $$
    SELECT routine344.safe_total(
        p_unit_price => p_unit_price,
        p_quantity => p_quantity,
        p_discount_rate => 0.05
    );
$$;
```

Avoid creating a same-named `safe_total` wrapper whose 1- or 2-argument forms collide with the original function's defaults, as that causes ambiguity.

### 45.2. Keep a single source of truth for business rules

If multiple overloads or wrappers duplicate the same discount formula, policy updates can leave results inconsistent. When needed, delegate through one core function with explicit validation or an appropriately authorized business service.

## 46. Default arguments and performance

Default and named arguments are primarily **API ergonomics and call resolution mechanisms**. They do not inherently make a function faster.

Actual performance factors include:

- Whether an SQL function can be inlined in the given context.
- Whether the function runs once or per row.
- Whether the function queries large tables or triggers I/O.
- Whether volatility and parallel-safety flags are declared accurately.
- Execution plans, indexes, and selectivity.
- Cost of evaluating default expressions.
- Whether many overloads complicate or break call resolution.
- PL/pgSQL/SPI overhead and internal queries.
- Concurrency and contention if a procedure writes data.

### 46.1. Never claim SQL functions are always inlined

PostgreSQL can inline SQL functions in certain contexts, depending on body structure, attributes, and query plans. Not every SQL function gets expanded into the caller's expression.

### 46.2. Use EXPLAIN meaningfully

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    routine344.safe_total(
        unit_price,
        p_quantity => quantity,
        p_discount_rate => discount_rate
    )
FROM routine344.order_lines;
```

Observe actual rows, time, and buffers, and measure on representative workloads. A three-row lab table only demonstrates syntax, not production performance.

### 46.3. Never mislabel IMMUTABLE to force speedups

If a function depends on `now()`, mutable configuration, table data, or session state, declare its volatility accurately per semantics. Lying to the planner allows it to optimize under false assumptions and return wrong results.

## 47. Compatibility checklist before adding an overload to a live system

Before migrating, gather:

```text
Routine name and schema
All existing overloads
Input names, types, modes, and default expressions
Return types
Call sites from applications, views, jobs, and triggers
Application search_path order
Untyped literals at call sites
EXECUTE privileges and owner
Related SECURITY DEFINER routines
Rollback feasibility
```

### 47.1. Changes likely to break callers

| Change | Risk |
|---|---|
| Renaming an input parameter | Breaks named callers |
| Changing an input type | Creates a distinct routine; callers may bind to another overload |
| Adding an overload with trailing DEFAULT | Breaks existing calls with ambiguity |
| Changing a default expression | Callers omitting the argument get new behavior |
| Reordering parameters | Alters positional caller semantics |
| Changing the return type | Not allowed via simple OR REPLACE; impacts dependencies |
| Changing schema / `search_path` | Routine resolves differently |
| Changing volatility / security | Changes semantics and execution privileges |
| Dropping and recreating a function | Can lose grants and dependencies |
| Adding numeric/text overloads | `unknown` literals may resolve unexpectedly |
| Renaming OUT columns | Breaks consumers expecting old result schema |

### 47.2. Safe migration workflow

1. List existing signatures from `pg_proc`.
2. Inventory existing SQL calls.
3. Classify callers as positional, named, or mixed.
4. Verify unique resolution for actual input types.
5. Test with literals, NULLs, and bound parameters.
6. Review permissions and `search_path`.
7. Deploy via versioned migrations.
8. Watch for SQLSTATE `42883` (`undefined_function`) and `42725` (`ambiguous_function`) where relevant.
9. Preserve rollback paths without accidentally dropping dependencies.
10. Clean up legacy overloads after a controlled compatibility window.

The SQLSTATE codes cited above are potential errors you may encounter; actual codes depend on the SQL statement and conflict type.

## 48. Practice exercises with answers

Exercises use schema `routine344`. Some intentionally demonstrate errors; run them only in a test environment.

### Exercise 1. Calculate one item at 100000, no discount

```sql
SELECT routine344.invoice_total(100000::numeric);
```

**Answer:** 100000.00.

### Exercise 2. Calculate three items, default discount

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    3
);
```

**Answer:** 300000.00.

### Exercise 3. Calculate two items with 10% discount

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2,
    0.10::numeric
);
```

**Answer:** 180000.00.

### Exercise 4. Omit quantity and set 20% discount

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.20
);
```

**Answer:** 80000.00.

### Exercise 5. Reverse named argument order

```sql
SELECT routine344.invoice_total(
    p_discount_rate => 0.20,
    p_unit_price => 100000
);
```

**Answer:** still 80000.00.

### Exercise 6. Mixed notation

```sql
SELECT routine344.invoice_total(
    100000,
    p_discount_rate => 0.20
);
```

**Answer:** 80000.00.

### Exercise 7. Is named before positional valid?

```sql
-- Intentionally errors:
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    2
);
```

**Answer:** no; positional arguments must precede named arguments in mixed notation.

### Exercise 8. Can p_quantity be supplied twice?

```sql
-- Intentionally errors:
SELECT routine344.invoice_total(
    100000,
    2,
    p_quantity => 3
);
```

**Answer:** no, `p_quantity` was already supplied at the second position.

### Exercise 9. Does DEFAULT apply when explicit NULL is passed?

**Answer:** no. Passing NULL supplies an argument with value SQL NULL; defaults apply only when the argument is omitted.

### Exercise 10. What happens if a STRICT function receives NULL for one parameter?

**Answer:** a `STRICT` function returns NULL directly under the `RETURNS NULL ON NULL INPUT` contract. Defaults do not replace explicit NULL.

### Exercise 11. Why must inputs after a default also have defaults?

**Answer:** PostgreSQL requires trailing default parameters so positional notation remains unambiguous.

### Exercise 12. Is this declaration valid?

```sql
-- Intentionally errors:
CREATE FUNCTION routine344.bad(
    p_a integer DEFAULT 1,
    p_b integer
)
RETURNS integer LANGUAGE sql
AS $$ SELECT p_a + p_b; $$;
```

**Answer:** no, because `p_b` is a required input following a parameter with a default.

### Exercise 13. Is a CURRENT_TIMESTAMP default frozen at CREATE time?

**Answer:** no; the default expression is evaluated when a call omits the argument. `CURRENT_TIMESTAMP` reflects transaction start time in PostgreSQL.

### Exercise 14. Create integer and text overloads

```sql
SELECT routine344.display_value(42::integer);
SELECT routine344.display_value('42'::text);
```

**Answer:** `integer:42` and `text:42`, respectively.

### Exercise 15. Can you overload by return type alone?

**Answer:** no. Function identity uses name and input types, not return type.

### Exercise 16. Can you overload by parameter name alone?

**Answer:** no. `f(p_id integer)` and `f(p_number integer)` have identical input signatures.

### Exercise 17. Why doesn't `display_value('42')` necessarily invoke the integer overload?

**Answer:** an untyped string literal starts with type `unknown`; PostgreSQL applies type resolution rules. Use `'42'::integer` if you want the integer overload.

### Exercise 18. NULL with integer/date overloads?

```sql
-- Intentionally errors/ambiguous:
SELECT routine344.describe_optional(NULL);
```

**Answer:** cast explicitly when multiple overloads can match:

```sql
SELECT routine344.describe_optional(NULL::integer);
```

### Exercise 19. Why is default_clash(5) dangerous?

**Answer:** both the one-integer overload and `(integer, integer DEFAULT 10)` match a single argument → ambiguous.

### Exercise 20. How to avoid default_clash?

**Answer:** keep only the defaulted routine, remove the default from the longer overload, or use distinct names.

### Exercise 21. Does named_clash(p_id=>7) resolve unambiguously?

**Answer:** no. Both overloads accept `p_id` and allow omitting the second parameter, making the call ambiguous.

### Exercise 22. Select the overload with p_limit

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_limit => 25
);
```

**Answer:** resolves unambiguously to the overload with `p_limit integer`.

### Exercise 23. What is the input signature of a function with OUT parameters?

```text
sum_and_difference(IN integer, IN integer, OUT integer, OUT integer)
```

**Answer:** the input signature is `(integer,integer)`.

### Exercise 24. Call write_audit using all defaults

```sql
CALL routine344.write_audit(1234);
```

**Answer:** inserts `entity_id = 1234` with `event_kind = 'CREATED'` and `actor_name = 'system'` (in the lab).

### Exercise 25. Call procedure omitting event_kind while passing actor

```sql
CALL routine344.write_audit(
    p_entity_id => 1234,
    p_actor_name => 'batch'
);
```

**Answer:** `event_kind` uses default `'CREATED'`.

### Exercise 26. Can a procedure be called with SELECT?

**Answer:** procedures use `CALL`, not `SELECT` like functions.

### Exercise 27. INOUT add_fee with default p_fee=0

```sql
CALL routine344.add_fee(100::numeric);
```

**Answer:** outputs `p_amount = 100`.

### Exercise 28. INOUT add_fee with fee 12.5

```sql
CALL routine344.add_fee(
    p_amount => 100::numeric,
    p_fee => 12.5::numeric
);
```

**Answer:** outputs `p_amount = 112.5`.

### Exercise 29. VARIADIC taking 4 numbers

```sql
SELECT routine344.sum_integers(1, 2, 3, 4);
```

**Answer:** 10.

### Exercise 30. VARIADIC called with a named array

```sql
SELECT routine344.sum_integers(
    VARIADIC p_values => ARRAY[4,5,6]::integer[]
);
```

**Answer:** 15.

### Exercise 31. What is the function identity of invoice_total?

**Answer:** `routine344.invoice_total(numeric,integer,numeric)`, regardless of whether callers omit quantity or discount via defaults.

### Exercise 32. Does DROP FUNCTION with one numeric drop invoice_total?

**Answer:** you cannot use a shortened signature as the identity instead of all three input types. Migrations must specify the complete input types of the routine to drop.

### Exercise 33. Why can't OR REPLACE change the return type?

**Answer:** PostgreSQL does not treat return type as an overload dimension. Changing it requires a migration/drop-create or a new routine name, handling dependencies properly.

### Exercise 34. Why is renaming p_discount_rate a breaking change?

**Answer:** named callers bind using that exact name, and PostgreSQL enforces a safeguard in `OR REPLACE`.

### Exercise 35. When a function is not found, what should you check?

**Answer:** name/schema, input types, named parameter names, defaults, arity, `search_path`, and routine kind (function vs. procedure).

### Exercise 36. When a function call is ambiguous, how do you fix it?

**Answer:** inspect overloads, cast inputs, eliminate overlapping defaults, or choose distinct names/signatures.

### Exercise 37. Why schema-qualify objects inside SECURITY DEFINER routines?

**Answer:** to reduce the risk of resolving wrong objects via `search_path` and untrusted schemas; also set a safe `search_path` and enforce privileges.

### Exercise 38. Do named parameters prevent SQL injection?

**Answer:** no; use bound parameters and secure dynamic SQL practices.

### Exercise 39. What does safe_total(100000,p_quantity=>NULL::integer) return?

**Answer:** the function actively raises `invalid_parameter_value` (`22023`) rather than falling back to default 1.

### Exercise 40. When should you use overloading instead of defaults?

**Answer:** when **different types or arities truly represent variants of the same operation** without creating ambiguity. If you only need optional settings, defaults on a single routine are usually clearer than multiple overloads.

## 49. Common mistakes and how to avoid them

### Mistake 1 — Thinking DEFAULT applies when NULL is passed

Defaults apply only when a parameter is omitted, never replacing an explicit NULL.

### Mistake 2 — Placing a required parameter after a defaulted parameter

PostgreSQL forbids this ordering for input parameters.

### Mistake 3 — Trying to skip a middle parameter positionally

Positional calls can only omit trailing defaults from the right; to skip a middle parameter, use named notation.

### Mistake 4 — Writing named arguments before positional arguments

Mixed notation requires positional arguments to come before named arguments.

### Mistake 5 — Passing the same parameter both positionally and by name

A parameter cannot receive two values in the same invocation.

### Mistake 6 — Misspelling a named parameter

Named calls require the exact parameter name defined in the routine contract.

### Mistake 7 — Using := as an assignment in SQL calls

`:=` is supported as legacy named notation, but `=>` is clearer and preferred.

### Mistake 8 — Confusing named arguments with bind parameters

Named arguments map inputs inside an SQL call; bind parameters safely transmit application values into the SQL statement.

### Mistake 9 — Thinking two functions with different RETURNS are overloads

You cannot overload by return type alone.

### Mistake 10 — Thinking renaming an input parameter creates a new overload

Parameter names do not change the input signature.

### Mistake 11 — Adding an overload with trailing DEFAULT that overlaps calls

Existing calls can immediately turn ambiguous.

### Mistake 12 — Assuming PostgreSQL picks numeric overloads from string contents

Untyped string literals and implicit casts follow strict rules; explicit casts clarify intent.

### Mistake 13 — Passing uncast NULL when overloads exist

This can cause ambiguity; use `NULL::desired_type`.

### Mistake 14 — Using a shortened signature when dropping a function with defaults

DROP/ALTER use the complete input type list, not the minimum argument count.

### Mistake 15 — Expecting OR REPLACE to change RETURN TYPE

In-place return-type alteration on the same routine identity is not allowed.

### Mistake 16 — Refactoring parameter names while forgetting named callers

Renaming parameters is a breaking API change.

### Mistake 17 — Calling a procedure with SELECT

Procedures require `CALL`; functions use `SELECT` or SQL expressions.

### Mistake 18 — Assuming CALL always allows COMMIT inside a procedure

Transaction control depends on top-level CALL context, explicit transaction blocks, `SECURITY DEFINER`, and other restrictions.

### Mistake 19 — Thinking OUT parameters participate in function overloading like IN

`OUT`-only parameters do not distinguish function identity; `INOUT` parameters do participate as inputs.

### Mistake 20 — Passing named scalars to VARIADIC

Expanded elements do not have individual names; use `VARIADIC name => array_expression` when passing a named array.

### Mistake 21 — Ignoring schema and search_path

Calls may resolve to an unintended overload in another schema or be affected by objects in untrusted schemas.

### Mistake 22 — Marking time- or table-dependent functions as IMMUTABLE

Allows the optimizer to make false assumptions and return stale or wrong results.

### Mistake 23 — Omitting validation and trusting callers

A default like `quantity=1` does not stop callers from passing `0`, `NULL`, or negative numbers.

### Mistake 24 — Assuming default expressions freeze at CREATE time

Dynamic expressions evaluate at call time; `CURRENT_TIMESTAMP` is not frozen when the function is created.

### Mistake 25 — Failing to test calls from drivers with typed binds

ORMs and drivers bind explicit parameter types that may resolve differently from literals tested in an SQL console.

### Mistake 26 — Dropping routines without checking dependencies and grants

Views, triggers, scripts, or services may fail operationally if a routine is dropped without a plan.

### Mistake 27 — Using SECURITY DEFINER as a quick fix for permission errors

This can introduce privilege escalation if permissions and `search_path` are not properly locked down.

### Mistake 28 — Benchmarking only on a few-row table

You cannot extrapolate real-workload routine call overhead from tiny lab fixtures.

## 50. Checklist for designing well-parameterized routines

| Question to verify | Why it matters |
|---|---|
| Is the routine a function or a procedure? | `SELECT` vs `CALL`, return shape, and transaction rules |
| Are schema and name clear? | Avoids colliding with built-ins or other routines |
| Do input types match the domain accurately? | Prevents unintended implicit casts |
| Which parameters are truly required? | Establishes a clear contract |
| Do all inputs after the first default also have defaults? | Required for valid DDL |
| Do callers need to skip middle parameters? | Enabled by named notation |
| Are named parameter names stable? | Preserves backward compatibility |
| Are omitted inputs distinguished from explicit NULL? | Protects default semantics |
| Do default expressions depend on time or side effects? | Affects volatility and consistency |
| Could input types cause overload ambiguity? | Ensures reliable parse/runtime resolution |
| Are there same-arity overloads with convertible types? | Requires explicit casts |
| Does a new overload clash with defaulted arities? | Prevents breaking existing calls with ambiguity |
| Are you relying on return type to distinguish overloads? | Invalid in PostgreSQL |
| Are OUT/INOUT/VARIADIC modes applied accurately? | Governs signatures and named invocation |
| Is out-of-range input validation implemented? | Ensures data and business correctness |
| Tested with NULLs, unknown literals, and driver binds? | Catches environment mismatches |
| Are schema-qualified calls used in sensitive code? | Clarifies resolution and strengthens security |
| Are `search_path` and `CREATE` privileges locked down? | Prevents shadowing/hijacking |
| Are `EXECUTE` permissions scoped by role? | Enforces least privilege |
| Is `SECURITY DEFINER` genuinely necessary? | Avoids unnecessary privilege escalation risk |
| Checked dependencies before DROP/REPLACE? | Prevents downstream breakage |
| Do you have catalog checks and migration rollback plans? | Enables safe operations |
| Measured workload impact for per-row function calls? | Verifies real performance |
| Does documentation show positional/named/mixed examples? | Helps callers follow the contract |

## 51. Quick reference table

| Task | Syntax | Notes |
|---|---|---|
| Default value | `p_qty integer DEFAULT 1` | Used only when argument is omitted |
| Omit trailing arguments | `f(100)` | Positional omits from right to left |
| Pass by name | `f(p_qty => 3)` | Must match exact input parameter name |
| Skip middle parameter | `f(p_a => 1, p_c => 3)` | `p_b` must have a default |
| Mix positional and named | `f(1, p_c => 3)` | Positional comes before named |
| Legacy syntax | `p_c := 3` | Prefer `=>` |
| Do not trigger default with NULL | `f(NULL::integer)` | NULL is an explicit value |
| SQL function | `SELECT schema.f(...)` | Returns a result |
| Procedure | `CALL schema.p(...)` | Can modify data |
| Overloading | `f(integer)` and `f(text)` | Distinct input types |
| Not an overload | `f(x integer)` and `f(y integer)` | Parameter names do not alter signature |
| Cannot overload by return type | `RETURNS text/integer` | Does not distinguish signatures |
| Default/overload clash | `f(int)` and `f(int,int DEFAULT 1)` | Can be ambiguous |
| Cast to select overload | `f(NULL::integer)` | Avoids `unknown` ambiguity |
| INOUT procedure | `CALL p(100, p_fee => 1)` | Returns output via `CALL` |
| Named VARIADIC | `f(VARIADIC p_arr => ARRAY[1,2])` | Individual elements are not named |
| Replace function body | `CREATE OR REPLACE FUNCTION` | Cannot change return type/input identity |
| Identify routine | `pg_get_function_identity_arguments(oid)` | Inspects input signature |
| Drop overload | `DROP FUNCTION f(type1,type2)` | Specify complete input types |
| Security | Schema-qualified + grants + safe `search_path` | Crucial for `SECURITY DEFINER` |

## 52. Official PostgreSQL documentation

Cross-check against the **PostgreSQL version you are running**, because certain procedure details, OUT arguments, and syntax options vary between versions:

- [Calling Functions](https://www.postgresql.org/docs/current/sql-syntax-calling-funcs.html): positional, named, and mixed notation.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): DEFAULT, IN/OUT/INOUT, overloading, CREATE OR REPLACE.
- [Query Language (SQL) Functions](https://www.postgresql.org/docs/current/xfunc-sql.html): SQL function examples, default arguments, VARIADIC.
- [Function Type Resolution](https://www.postgresql.org/docs/current/typeconv-func.html): overload selection, unknown literals, implicit casts, and security implications.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html): parameters, defaults, and procedure properties.
- [CALL](https://www.postgresql.org/docs/current/sql-call.html): invoking procedures, named parameters, outputs, and transaction-control conditions.
- [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html): bodies, parameter variables, RETURN, and CALL.
- [DROP FUNCTION](https://www.postgresql.org/docs/current/sql-dropfunction.html): specifying signatures to drop an overload.
- [ALTER FUNCTION](https://www.postgresql.org/docs/current/sql-alterfunction.html): altering routine properties, owner, or schema.
- [Functions and Operators](https://www.postgresql.org/docs/current/functions.html): return types and integrating functions into SQL queries.
- [Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html): CURRENT_TIMESTAMP, now(), and transaction time.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): routine metadata.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): securing functions and `search_path` in privilege contexts.

The examples in this lesson are educational guides. None of the SQL snippets here were executed against a live database while authoring this Markdown; for production, run dedicated testing and migration reviews.

## 53. Summary: three mechanisms and one design principle

**Default arguments** give an API optional parameters:

```sql
CREATE FUNCTION f(
    p_required integer,
    p_optional integer DEFAULT 10
) ...
```

**Named arguments** clarify invocations and allow skipping intermediate optional parameters:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.05
);
```

**Overloading** reuses one routine name across multiple **input parameter types**:

```sql
display_value(integer)
display_value(text)
```

Keep these rules in mind:

```text
Omitting a parameter      != passing NULL
Named argument name       != bind placeholder
Different input type      can form an overload
Different return type     does not form an overload
Different parameter name  does not form an overload
DEFAULT + overload        can cause ambiguity
Function call             SELECT
Procedure call            CALL
```

### Principles to apply

1. Place required parameters first, optional/defaulted parameters last.
2. When multiple options exist, prefer named notation `=>` for readability.
3. Never substitute defaults when callers pass explicit NULL unless the function explicitly implements a fallback.
4. Avoid adding overloads that create **overlapping callable arities** with a function that already uses `DEFAULT`.
5. Use explicit casts when working with NULL, `unknown` literals, or closely related overloads.
6. Treat input parameter names of a named API as a **compatibility commitment**.
7. Never rely on return types to distinguish function overloads.
8. Identify routines by their **complete input type list** when dropping, altering, or querying catalogs.
9. Use schema-qualified calls, restrict grants, and lock down `search_path` in sensitive code.
10. Before migrating, verify positional callers, named callers, default values, dependencies, and permissions.

**One sentence to remember:** default values let callers **omit arguments**, named arguments let callers **bind the exact argument**, and overloading lets PostgreSQL **choose the routine by input type**. These three mechanisms only pay off when routine signatures are designed to be **clear, unambiguous, and stable for callers**.
