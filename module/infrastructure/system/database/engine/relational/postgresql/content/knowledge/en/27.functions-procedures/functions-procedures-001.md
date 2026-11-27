# CREATE FUNCTION, CREATE PROCEDURE, and Selection Criteria in PostgreSQL

PostgreSQL allows encapsulating database-side logic into a **function** or a **procedure**. Both are named objects with parameters, an execution language, and their own privileges, but **they do not share the same invocation contract or transaction handling**.

For example, when an application needs to calculate an order amount inside a `SELECT` statement, a function is the natural choice:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

When an application needs to perform a multi-step business operation, such as changing an order's status and writing an audit log in a single call, a procedure may be the appropriate choice:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

Key point: **a function does not mean "read-only," and a procedure does not mean "always auto-COMMIT."** PostgreSQL allows certain functions to cause side effects, while a procedure can control transactions only in permitted invocation contexts.

The lesson **"CREATE FUNCTION, CREATE PROCEDURE, and Selection Criteria"**, part of the **Functions and Procedures** chapter of the **Database Engine Relational PostgreSQL** module, explains syntax, return types, transactions, authorization, optimization capabilities, Java/JDBC usage scenarios, version management, and how to choose the right tool.

> **Practice scope:** all illustrative DDL/DML is intended solely for a dedicated lab database. Some examples intentionally modify data or execute `COMMIT`; do not run them on production without checking privileges, transactions, dependent objects, and rollback procedures.

---

## 1. What do functions and procedures have in common?

Both functions and procedures:

- Are schema objects with a name and parameters.
- Are defined using SQL, PL/pgSQL, or other languages supported by PostgreSQL.
- Can access data, perform work, and raise errors.
- Can be reused from multiple clients.
- Have an `EXECUTE` privilege, an owner, metadata, and dependencies.
- Can have overloads with appropriate parameter type lists.
- Can be created, replaced, renamed, and dropped using DDL.
- Are affected by `search_path`, roles, object privileges, and session configuration.

The core differences are **how they are called, their result types, and their ability to terminate transactions**.

### 1.1. Quick comparison

| Question | Function | Procedure |
|---|---|---|
| Created with | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Typical call | `SELECT f(...)` or used in an SQL expression | `CALL p(...)` |
| Usable in `WHERE`, `ORDER BY`, `JOIN` | Yes, if the type/shape is suitable | Not directly |
| Return value declaration | `RETURNS type`, `RETURNS TABLE`, `RETURNS SETOF`, ... | No `RETURNS type` like a function |
| Returns multiple typed rows | Can use a set-returning function | Not equivalent to `RETURNS TABLE` via `CALL` |
| Can modify data | Yes, with an appropriate function | Yes |
| Can `COMMIT`/`ROLLBACK` inside | No | Only in permitted `CALL` contexts and with restrictions |
| Common languages | SQL, PL/pgSQL | SQL, PL/pgSQL |
| Used for calculations in SELECT | Very suitable | Not suitable |
| Used for command-style business operations | Possible, but requires careful consideration | Usually easier to express |

PostgreSQL has supported `CREATE PROCEDURE` since version 11. Some options/parameters were expanded in subsequent versions. Always verify the server version when using newer features.

## 2. Distinguishing SQL functions from stored procedures

The term *stored routine* covers several types of programs stored in a database. In PostgreSQL:

- A **Function** has `RETURNS` and can be called as part of an expression/query.
- A **Procedure** is called with `CALL` and typically expresses an action rather than a value-returning expression for use in `SELECT`.
- A **Trigger function** is a special kind of function with `RETURNS trigger` that is invoked by the trigger mechanism.
- An **Aggregate/window function** is another specialized form of function, not identical to a procedure.

Do not use the term "stored procedure" in the generic sense from other database systems and assume all PostgreSQL routines are invoked with `EXEC` or produce identical output result sets.

## 3. Lab database for the examples

In an **empty practice database**, create the schema and order tables:

~~~sql
CREATE SCHEMA routine_lab;

CREATE TABLE routine_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE routine_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES routine_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE routine_lab.audit_log (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

INSERT INTO routine_lab.customers (
    customer_id, customer_name
)
VALUES
    (101, 'Lan'),
    (102, 'Minh');

INSERT INTO routine_lab.orders (
    order_id, customer_id, status, total_amount, placed_at
)
VALUES
    (1001, 101, 'paid', 125000.00,
     TIMESTAMPTZ '2026-11-01 09:00:00+00'),
    (1002, 102, 'new', 89000.00,
     TIMESTAMPTZ '2026-11-02 10:00:00+00'),
    (1003, 101, 'paid', 35000.00,
     TIMESTAMPTZ '2026-11-03 11:00:00+00');

ANALYZE routine_lab.orders;
~~~

The dataset contains 2 customers, 3 orders, and an initially empty audit table. `status` and `total_amount` are typed columns with constraints. The following functions and procedures are all based on this schema.

### 3.1. Why always write the schema name?

Writing `routine_lab.orders` instead of `orders` avoids name collisions across schemas and reduces reliance on `search_path`.

This is especially critical for routines with `SECURITY DEFINER`, because unsafe name resolution can create vulnerabilities if another schema in `search_path` allows untrusted users to create objects.

### 3.2. Do not reset the lab carelessly

`CREATE SCHEMA`/`CREATE TABLE` commands will fail if the objects already exist. Do not run `DROP SCHEMA ... CASCADE` on an unverified schema just to re-run examples. Use a fresh lab database or perform an intentional reset.

## 4. General CREATE FUNCTION syntax

A function is declared with the following form:

~~~sql
CREATE [ OR REPLACE ] FUNCTION schema_name.function_name(
    [ argument_name argument_type [ DEFAULT default_expr ], ... ]
)
RETURNS return_type
LANGUAGE language_name
[ function_attributes ... ]
AS $function_body$
    ...
$function_body$;
~~~

Square brackets denote optional syntax elements, **not a statement that can be executed verbatim**.

Key components:

1. `CREATE FUNCTION` creates the function.
2. `OR REPLACE` replaces the definition of a routine with the same identity, subject to signature/return type constraints.
3. `schema_name.function_name` specifies the qualified name.
4. The parameter list defines inputs and overloads.
5. `RETURNS` describes the return type.
6. `LANGUAGE sql` or `LANGUAGE plpgsql` specifies the execution language.
7. Attributes such as `VOLATILE`/`STABLE`/`IMMUTABLE`, `STRICT`, `PARALLEL`, `SECURITY`, `COST`, etc., inform PostgreSQL about the function's behavior.
8. `AS $$ ... $$` contains the routine source code.

### 4.1. Dollar quoting

`$$ ... $$` or `$tag$ ... $tag$` avoids having to escape every single quote inside the routine body:

~~~sql
CREATE FUNCTION routine_lab.hello_text()
RETURNS TEXT
LANGUAGE sql
AS $body$
    SELECT 'Hello PostgreSQL'::TEXT;
$body$;
~~~

`$body$` is a delimiter, not a variable or SQL parameter.

### 4.2. Do not confuse RETURNS with RETURN

- `RETURNS text` in the header declares the **return type**.
- `RETURN expression;` in PL/pgSQL terminates the function or returns a value according to function syntax.
- `RETURN QUERY ...;` appends rows to the result set of a set-returning PL/pgSQL function.

## 5. SQL-language function returning a scalar

Example calculating line item total:

~~~sql
CREATE FUNCTION routine_lab.line_total(
    p_price NUMERIC,
    p_quantity INTEGER
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_price * p_quantity;
$$;
~~~

Invocation:

~~~sql
SELECT routine_lab.line_total(45000.00, 2);
~~~

Result: 90000.00 in the appropriate numeric representation.

### 5.1. Why use LANGUAGE sql?

This is a single-expression calculation requiring no variables, loops, conditional branches, or exception handling. An SQL-language function is concise and has the opportunity to be optimized or inlined by the planner when eligible.

### 5.2. Why IMMUTABLE?

For the same `p_price` and `p_quantity`, pure SQL multiplication does not depend on table data or time. That property matches `IMMUTABLE` in this example.

### 5.3. Why STRICT?

If either input is SQL NULL, the multiplication returns NULL. `STRICT` allows PostgreSQL to skip executing the function and return NULL directly when any input is NULL.

### 5.4. The return type should not depend on presentation formatting

`RETURNS NUMERIC` represents a number, without forcing clients to receive a currency string with commas or symbols. Display formatting should be handled by the application/presentation layer or export layer.

## 6. Calling a function with SELECT

A scalar-returning function can appear in many places:

~~~sql
SELECT routine_lab.line_total(45000, 2)
    AS amount;
~~~

~~~sql
SELECT
    o.order_id,
    o.total_amount,
    routine_lab.line_total(o.total_amount, 2)
        AS doubled_amount
FROM routine_lab.orders AS o
ORDER BY o.order_id;
~~~

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE routine_lab.line_total(o.total_amount, 1) > 50000
ORDER BY o.order_id;
~~~

Because it is an **SQL expression**, a function can be used in `SELECT`, `WHERE`, `ORDER BY`, `JOIN`, or other appropriate contexts.

### 6.1. Do not assume a function in WHERE is automatically optimal

Wrapping a column in a function can prevent a regular index from being used if the planner cannot simplify the expression. When querying large tables, inspect `EXPLAIN` instead of assuming that encapsulating logic in a function preserves existing performance.

## 7. Named parameters, DEFAULT, and named notation

Example:

~~~sql
CREATE FUNCTION routine_lab.add_fee(
    p_amount NUMERIC,
    p_rate NUMERIC DEFAULT 0.05
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * (1 + p_rate);
$$;
~~~

Positional notation:

~~~sql
SELECT routine_lab.add_fee(100000);
SELECT routine_lab.add_fee(100000, 0.10);
~~~

Named notation:

~~~sql
SELECT routine_lab.add_fee(
    p_rate => 0.10,
    p_amount => 100000
);
~~~

With named notation, parameter names become part of the routine's call interface.

### 7.1. DEFAULT does not change the return type

If `p_rate` is omitted when calling, PostgreSQL uses the appropriate default expression. The function still returns NUMERIC.

### 7.2. Be careful with overloads combined with default parameters

Multiple overloads with default arguments or similar signatures can make function resolution unpredictable or raise an ambiguous call error. For public database APIs, prefer clear signatures and schema-qualified calls.

## 8. STRICT and handling SQL NULL

The following two clauses are semantically equivalent:

~~~sql
STRICT
~~~

and:

~~~sql
RETURNS NULL ON NULL INPUT
~~~

A `STRICT` function is not executed when any argument is SQL NULL; PostgreSQL returns SQL NULL directly.

Example:

~~~sql
SELECT routine_lab.line_total(NULL::NUMERIC, 2);
~~~

The result is SQL NULL.

### 8.1. Do not use STRICT when NULL carries specific semantics

For instance, a business rule might state "omitting discount means 0." If the function needs to handle NULL itself using `COALESCE`, do not use STRICT because the function body will not run when an input is NULL.

~~~sql
CREATE FUNCTION routine_lab.discounted_amount(
    p_amount NUMERIC,
    p_discount NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
AS $$
    SELECT
        CASE
            WHEN p_amount IS NULL THEN NULL
            ELSE p_amount - COALESCE(p_discount, 0)
        END;
$$;
~~~

Here, a NULL `p_discount` is interpreted as 0, while a NULL `p_amount` still returns NULL according to the defined rule.

## 9. Table-reading functions: choose STABLE

To fetch an order's total amount by ID:

~~~sql
CREATE FUNCTION routine_lab.get_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;
$$;
~~~

Invocation:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

Expected result: 125000.00.

### 9.1. Why not use IMMUTABLE?

The `total_amount` value in the table can be updated via UPDATE. The same `p_order_id` at two different points in time can return different results. Incorrectly marking a function that reads mutable tables as `IMMUTABLE` can cause the planner to optimize or cache under invalid assumptions, leading to stale results or surprising behavior.

### 9.2. When an order is not found

When no row matches, this SQL scalar function returns SQL NULL according to how SQL scalar functions obtain their result. That is distinct from returning 0.

Define domain semantics explicitly:

- "Does not exist" → NULL.
- "Does not exist" → RAISE EXCEPTION.
- "Does not exist" → a result structure with a status field.

Do not automatically treat a missing order as having a total of 0 unless the business specification requires it.

## 10. PL/pgSQL functions: variables, conditionals, RETURN

When conditional branching is needed, PL/pgSQL is easier to read than a convoluted SQL expression.

~~~sql
CREATE FUNCTION routine_lab.order_category(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    SELECT o.total_amount
    INTO v_amount
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    IF NOT FOUND THEN
        RETURN 'not_found';
    ELSIF v_amount >= 100000 THEN
        RETURN 'large';
    ELSE
        RETURN 'regular';
    END IF;
END;
$$;
~~~

Invocation:

~~~sql
SELECT
    routine_lab.order_category(1001) AS first_category,
    routine_lab.order_category(1002) AS second_category,
    routine_lab.order_category(9999) AS missing_category;
~~~

Logical result: `large`, `regular`, `not_found`.

### 10.1. Keywords to remember

- `DECLARE` declares variables.
- `BEGIN ... END` is a **PL/pgSQL block**, and does not automatically open a new SQL transaction.
- `SELECT ... INTO variable` stores query results into a variable in PL/pgSQL.
- `FOUND` indicates whether a preceding qualifying statement found or affected any rows.
- `IF ... ELSIF ... ELSE ... END IF` handles branching.
- `RETURN` terminates the function and returns a scalar value.

### 10.2. Avoid variable names colliding with column names

Using the `p_` prefix for parameters, `v_` for variables, and table aliases like `o` helps prevent ambiguous identifier errors in PL/pgSQL.

## 11. Returning multiple columns with RETURNS TABLE

A function can return a **set of rows** with an explicit schema:

~~~sql
CREATE FUNCTION routine_lab.orders_for_customer(
    p_customer_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    status TEXT,
    total_amount NUMERIC
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        o.order_id,
        o.status,
        o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.customer_id = p_customer_id
    ORDER BY o.order_id;
$$;
~~~

Invocation:

~~~sql
SELECT *
FROM routine_lab.orders_for_customer(101);
~~~

Result:

| order_id | status | total_amount |
|---:|---|---:|
| 1001 | paid | 125000.00 |
| 1003 | paid | 35000.00 |

### 11.1. Differences from scalar functions

- `RETURNS NUMERIC`: a single value.
- `RETURNS TABLE(...)`: multiple columns, potentially multiple rows.
- When queried with `SELECT * FROM function(...)`, the columns have names and types like a relation.
- You can `JOIN`, `FILTER`, and `ORDER BY` on the result as appropriate.

### 11.2. Do not confuse RETURNS TABLE with procedure OUT

A procedure can have output parameters, but it is not equivalent to a set-returning function used in a `FROM` clause. If you need a relational expression to JOIN against, `RETURNS TABLE` is usually the more direct choice.

## 12. PL/pgSQL with RETURN QUERY

When additional logic is needed before returning multiple rows:

~~~sql
CREATE FUNCTION routine_lab.paid_orders_for_customer(
    p_customer_id BIGINT,
    p_min_amount NUMERIC DEFAULT 0
)
RETURNS TABLE (
    order_id BIGINT,
    total_amount NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_min_amount < 0 THEN
        RAISE EXCEPTION
            'p_min_amount must be nonnegative: %',
            p_min_amount;
    END IF;

    RETURN QUERY
    SELECT
        o.order_id,
        o.total_amount
    FROM routine_lab.orders AS o
    WHERE o.customer_id = p_customer_id
      AND o.status = 'paid'
      AND o.total_amount >= p_min_amount
    ORDER BY o.order_id;
END;
$$;
~~~

Invocation:

~~~sql
SELECT *
FROM routine_lab.paid_orders_for_customer(101, 50000);
~~~

The result contains order 1001.

### 12.1. RETURN QUERY and RETURN NEXT

In PL/pgSQL set-returning functions:

- `RETURN QUERY SELECT ...` appends the rows produced by the query.
- `RETURN NEXT expression` appends a single row/value matching the return type structure.
- `RETURN;` with no expression ends a set-returning function after results have been accumulated.

Do not use `RETURN QUERY` in a function declared with `RETURNS NUMERIC`.

## 13. RETURNS SETOF type and composite types

A function can return a set of scalar values or a set of rows of a composite type.

Integer example:

~~~sql
CREATE FUNCTION routine_lab.sequence_1_to(
    p_last INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT g::INTEGER
    FROM generate_series(1, p_last) AS g;
$$;
~~~

Invocation:

~~~sql
SELECT *
FROM routine_lab.sequence_1_to(5);
~~~

The result is 1, 2, 3, 4, 5 across rows; if a guaranteed outer order is required, add `ORDER BY`.

### 13.1. When to use RETURNS SETOF?

- Returning a set of values of the same type.
- Returning a set of an existing composite type.
- When you want to define multi-column output directly in the declaration, `RETURNS TABLE` is often easier to read.

### 13.2. Using multi-row functions in LATERAL

Example:

~~~sql
SELECT
    c.customer_id,
    x.order_id,
    x.total_amount
FROM routine_lab.customers AS c
CROSS JOIN LATERAL routine_lab.orders_for_customer(
    c.customer_id
) AS x
ORDER BY c.customer_id, x.order_id;
~~~

`LATERAL` allows the function to reference the `customer_id` value from each outer row. This is why table-returning functions are useful in SQL composition; procedures cannot be invoked via `JOIN LATERAL ... CALL`.

## 14. Functions can still modify data

A common misconception is that functions are strictly for computation.

Example of a function writing an audit entry:

~~~sql
CREATE FUNCTION routine_lab.add_audit_note(
    p_order_id BIGINT,
    p_action TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_audit_id BIGINT;
BEGIN
    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (p_order_id, p_action)
    RETURNING audit_id INTO v_audit_id;

    RETURN v_audit_id;
END;
$$;
~~~

Invocation:

~~~sql
SELECT routine_lab.add_audit_note(
    1001, 'manual_review'
);
~~~

The function **INSERTs an actual row**. This is a `VOLATILE` function with side effects.

### 14.1. Why still consider a procedure for commands?

Technically, PostgreSQL allows functions to execute DML, but if a business operation primarily causes side effects and does not need to be used as an expression, a procedure invoked via `CALL` can make the API intent clearer.

Conversely, simply having an INSERT statement does not automatically require a procedure. Evaluate the invocation contract and transaction needs.

### 14.2. Avoid unexpected side effects in large SELECT queries

Calling a function that writes audit rows for every row of a large table can generate huge volumes of rows and WAL. Do not place functions with side effects in SELECT/WHERE simply because they can be invoked as expressions.

## 15. What are VOLATILE, STABLE, and IMMUTABLE?

PostgreSQL uses **volatility classification** to understand the guarantees a routine author provides to the planner and for snapshot behavior.

| Attribute | Expected guarantee | Typical example |
|---|---|---|
| `IMMUTABLE` | Same inputs always yield the same result; no dependency on mutable state | Pure mathematical computation |
| `STABLE` | With identical inputs, the result is stable within a qualifying statement | Table lookups or statement-stable values |
| `VOLATILE` | Can change across calls or has side effects | Table writes, random, clock_timestamp |

**PostgreSQL defaults to VOLATILE** if no volatility attribute is specified.

### 15.1. IMMUTABLE does not merely mean "does not modify data"

A function that reads `orders` without running UPDATE still **should not be IMMUTABLE**, because table data can change between statements.

### 15.2. STABLE does not mean the result is permanently fixed

The function `get_order_total(id)` can return a different value in a later statement after an order is updated. STABLE only promises stability within the scope of a single statement and its corresponding snapshot behavior.

### 15.3. VOLATILE does not automatically mean "slow"

It describes mutability/side effects, not a quality score. Never mislabel a function as `IMMUTABLE` to force optimizations on a routine that must read fresh data.

## 16. Typical volatility examples

~~~sql
SELECT
    now() AS transaction_timestamp,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time,
    random() AS random_value;
~~~

In PostgreSQL:

- `now()` / `transaction_timestamp()` are classified as `STABLE`.
- `statement_timestamp()` is stable as of the start of the corresponding statement and is classified accordingly.
- `clock_timestamp()` is `VOLATILE` because it can change even within the same statement.
- `random()` is `VOLATILE`.

**Do not mark functions as IMMUTABLE if they depend on time, session configuration, table data, or any mutable external source.**

### 16.1. Impact on prepared statements

The planner can rely on the strong guarantees of IMMUTABLE to fold or simplify expressions, including in cached plans. If the function is not truly immutable, declaring the wrong volatility can produce stale output in subtle ways.

## 17. Snapshots and data changes inside routines

For functions written in SQL/PL/pgSQL, volatility is tied to how internal queries observe data:

- `STABLE`/`IMMUTABLE` functions use the calling statement's snapshot according to PostgreSQL's snapshot rules.
- `VOLATILE` functions can acquire a new snapshot for individual internal queries.
- The caller's transaction isolation level still governs overall consistency.

This matters when a function reads data concurrently with other DML operations.

Do not use volatility as a substitute for designing `READ COMMITTED`/`REPEATABLE READ`/`SERIALIZABLE`, locking, and transaction boundaries. Volatility is a contract for the planner and routine semantics, not a choice of isolation level.

## 18. PARALLEL SAFE, RESTRICTED, and UNSAFE

PostgreSQL also allows classifying functions for parallel query execution:

- `PARALLEL SAFE`: can run inside parallel workers when eligible.
- `PARALLEL RESTRICTED`: must run only in the leader process in eligible plans.
- `PARALLEL UNSAFE`: presence of the function can prevent parallel plan generation.

If omitted, user-defined functions generally default to `PARALLEL UNSAFE`.

### 18.1. Declare SAFE only when genuinely safe

Functions that write data, modify session state, use sequences, or perform operations unsafe for parallel workers must not be marked SAFE just to force speedups.

For example, `line_total` is pure multiplication, so `PARALLEL SAFE` is appropriate. The `add_audit_note` function performs an INSERT, so it is not suitable.

### 18.2. Parallel classification is independent of volatility

A function can be STABLE without necessarily being safe to execute in a worker, depending on what operations it performs. Classification must reflect actual behavior, not just the routine's name.

## 19. COST and ROWS

PostgreSQL supports estimating a function's execution cost:

~~~sql
CREATE FUNCTION routine_lab.double_value(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
COST 1
AS $$
    SELECT p_value * 2;
$$;
~~~

For set-returning functions, you can declare an estimated row count using the `ROWS` attribute when applicable.

### 19.1. COST is not milliseconds

`COST` is an input to the planner's cost model, not an exact execution time in milliseconds. Setting it too low or too high can lead to suboptimal query plans.

### 19.2. ROWS is an estimate

If a function typically returns 5 rows but declares 10,000, the planner may misestimate join costs. Do not arbitrarily tweak numbers hoping to optimize; measure with `EXPLAIN (ANALYZE, BUFFERS)` on realistic workloads.

## 20. CREATE PROCEDURE syntax

A typical procedure has the following form:

~~~sql
CREATE [ OR REPLACE ] PROCEDURE schema_name.proc_name(
    [ [ IN | INOUT | OUT ] parameter_name parameter_type, ... ]
)
LANGUAGE language_name
[ procedure_attributes ... ]
AS $procedure_body$
    ...
$procedure_body$;
~~~

This is a syntax template, not directly executable SQL. Detailed support for `OUT` parameters and options can depend on the PostgreSQL version.

Unlike functions:

- Do not write `RETURNS NUMERIC` or `RETURNS TABLE` in the header.
- Call using `CALL`.
- Can use `INOUT`/`OUT` to return output values where supported by the server version.
- Can control transactions, but only in specific contexts.

## 21. First business procedure: changing order status

~~~sql
CREATE PROCEDURE routine_lab.mark_order_paid(
    IN p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE routine_lab.orders AS o
    SET status = 'paid'
    WHERE o.order_id = p_order_id
      AND o.status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % does not exist or is not new',
            p_order_id;
    END IF;

    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (
        p_order_id,
        'marked_paid'
    );
END;
$$;
~~~

Invocation:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

In the initial lab dataset, order 1002 has `status='new'`, so the procedure:

1. UPDATEs the status to `paid`.
2. Checks that a row was updated.
3. INSERTs an audit log row.

If called again, the condition `status='new'` no longer matches, so the procedure raises an exception. This policy is **not idempotent under blind retries**; real systems must define retry behavior explicitly.

### 21.1. This procedure contains no COMMIT

Although invoked via `CALL`, `mark_order_paid` does not commit on its own. If the client opens a transaction, both DML statements belong to that transaction; the caller decides whether to COMMIT or ROLLBACK.

### 21.2. Testing effects inside a lab transaction

To avoid persisting state changes during an example:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

SELECT
    order_id, status
FROM routine_lab.orders
WHERE order_id = 1002;

ROLLBACK;
~~~

After ROLLBACK, the order status and audit table return to their pre-transaction state. Run this only once on a dataset not already modified by a previous `CALL`; if you already called and committed it, reset the lab or choose an appropriate order.

## 22. How does CALL differ from SELECT?

Calling a function:

~~~sql
SELECT routine_lab.get_order_total(1001);
~~~

Calling a procedure:

~~~sql
CALL routine_lab.mark_order_paid(1002);
~~~

**Do not use:**

~~~sql
-- Incorrect call form for a procedure:
SELECT routine_lab.mark_order_paid(1002);
~~~

and:

~~~sql
-- Incorrect call form for a function:
CALL routine_lab.get_order_total(1001);
~~~

Names can collide in certain scenarios with different signatures, and PostgreSQL resolves routines by kind, name, and argument types. Do not rely on the two statements above "automatically finding the right kind."

### 22.1. A procedure is not an SQL expression

You cannot write:

~~~sql
-- Invalid as an expression:
SELECT
    order_id,
    CALL routine_lab.mark_order_paid(order_id)
FROM routine_lab.orders;
~~~

If you need to operate on a set of rows, consider a set-based SQL UPDATE, a procedure operating on a condition, or an appropriate function with controlled side effects.

## 23. IN, OUT, and INOUT parameters

In general:

- `IN`: data passed from caller into the routine.
- `OUT`: data returned from the routine to the caller (verify exact support/syntax for your PostgreSQL version).
- `INOUT`: receives an initial input and also serves as an output parameter.

**Functions** can use `OUT` and `INOUT` according to function return rules; **procedures** also support appropriate output parameters, though calling via `CALL` differs from reading a function result.

### 23.1. A procedure with INOUT returning a result

~~~sql
CREATE PROCEDURE routine_lab.describe_order(
    IN p_order_id BIGINT,
    INOUT p_message TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT format(
        'Order %s has status %s',
        o.order_id,
        o.status
    )
    INTO p_message
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    IF p_message IS NULL THEN
        p_message := format(
            'Order %s not found',
            p_order_id
        );
    END IF;
END;
$$;
~~~

Invocation:

~~~sql
CALL routine_lab.describe_order(1001, NULL);
~~~

Because the procedure has an output parameter, `CALL` can return **one result row** containing the `p_message` value via the output argument mechanism. This is **not** equivalent to a set-returning function in an SQL JOIN.

### 23.2. Why pass NULL in the INOUT position?

`INOUT` still expects an input argument. This example needs no initial input text, so NULL is passed and the procedure assigns the output value.

For `OUT`-only parameters, placeholder syntax and detailed support may vary across PostgreSQL versions; do not blindly copy procedure syntax from Oracle or SQL Server.

## 24. Function RETURNS TABLE vs. procedure OUT: which to choose?

If you need relational querying:

~~~sql
SELECT *
FROM routine_lab.orders_for_customer(101);
~~~

then a function with `RETURNS TABLE` is the natural choice.

If you need to execute a command and return a brief code/result:

~~~sql
CALL routine_lab.describe_order(1001, NULL);
~~~

then a procedure with `INOUT` may be suitable.

| Need | Typically sensible choice |
|---|---|
| JOIN routine results with other tables | Function `RETURNS TABLE` |
| Retrieve a list of data as rows | Function |
| A calculation used in WHERE | Function |
| Command changing state + audit | Procedure or VOLATILE function, prioritize clear API |
| A command that may control transactions internally | Procedure, if the CALL context permits |
| Return a status/message after a command | Procedure with appropriate INOUT/OUT |
| Called as an expression in SELECT | Function |

Do not choose a procedure merely because it sounds "enterprise"; likewise, do not choose a function just because it is shorter while sacrificing clear command semantics.

## 25. The biggest difference: transaction control

**A function cannot end a transaction using COMMIT/ROLLBACK inside its body.** Functions execute within the caller's or statement's transaction.

**A procedure can** execute `COMMIT`/`ROLLBACK` in **appropriate invocation contexts**, but not every `CALL` is permitted to do so.

Key requirements typically include:

1. The procedure is invoked via a **top-level `CALL`** in a context that supports transaction control, or an eligible nested `CALL`/`DO` chain without intervening SQL statements that disallow it.
2. The call is not inside an **explicit transaction block** where procedure transaction control is prohibited.
3. The procedure is not declared `SECURITY DEFINER`.
4. The procedure does not have a `SET` configuration clause attached to its definition that prohibits transaction control.
5. It does not attempt to `COMMIT` inside an `EXCEPTION` block, which runs in a subtransaction.
6. The session, client, or driver does not implicitly wrap `CALL` in a transaction that forbids transaction control.

This is why "a procedure can always COMMIT inside" is false.

## 26. BEGIN in PL/pgSQL does not start a transaction

Example:

~~~sql
CREATE PROCEDURE routine_lab.noop()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Hello';
END;
$$;
~~~

Here `BEGIN ... END` is a **PL/pgSQL programming block**; it is not equivalent to SQL's:

~~~sql
BEGIN;
...
COMMIT;
~~~

transaction statements.

In PL/pgSQL, do not use `BEGIN;` to "start a nested transaction" as some other database systems might allow. PostgreSQL does not support independent nested transactions in that manner; exception blocks create subtransactions with specific semantics.

## 27. A valid procedure with COMMIT in the lab

Create a procedure that inserts audit entries in batches and commits between batches:

~~~sql
CREATE PROCEDURE routine_lab.write_audit_batches(
    IN p_batch_size INTEGER,
    IN p_batch_count INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch INTEGER;
BEGIN
    IF p_batch_size <= 0
       OR p_batch_count <= 0
       OR p_batch_size > 100
       OR p_batch_count > 10
    THEN
        RAISE EXCEPTION
            'Invalid demo batch size or count';
    END IF;

    FOR v_batch IN 1..p_batch_count LOOP
        INSERT INTO routine_lab.audit_log(
            order_id, action
        )
        SELECT
            1001,
            format(
                'demo_batch_%s_item_%s',
                v_batch,
                g.item_no
            )
        FROM generate_series(
            1, p_batch_size
        ) AS g(item_no);

        COMMIT;
    END LOOP;
END;
$$;
~~~

**Call at top level with appropriate autocommit, without wrapping in BEGIN:**

~~~sql
CALL routine_lab.write_audit_batches(2, 2);
~~~

Each batch in this example inserts 2 audit rows, across 2 batches. `COMMIT` ends the current transaction and PostgreSQL starts a new transaction according to procedure transaction control rules.

### 27.1. Calling inside an explicit transaction block will fail

Do not do this:

~~~sql
-- Illustration of a prohibited transaction control scenario:
BEGIN;

CALL routine_lab.write_audit_batches(2, 2);

COMMIT;
~~~

For a procedure containing `COMMIT`, this call fails with a transaction control error because it runs inside an explicit transaction block. If your client or framework always begins a transaction before `CALL`, redesign the routine boundary.

### 27.2. Committing per batch has consequences

If batch 1 has been committed and batch 2 raises an error, batch 1 **does not automatically roll back**. Therefore:

- Design idempotency/checkpoints.
- Define safe retry semantics.
- Do not assume the entire batch procedure is atomic.
- Plan for data recovery between batches.

That is a major difference compared to procedures that do not commit internally.

## 28. Nested CALLs and transaction control limits

PostgreSQL can allow transaction control across an eligible call chain:

~~~text
CALL proc_outer()
    |
    +--> CALL proc_inner()
              |
              +--> COMMIT
~~~

However, if the call stack contains another construct—such as `SELECT function()`—between `CALL` statements in a way prohibited by PostgreSQL rules, the inner procedure may lose transaction control.

In addition:

- A `SECURITY DEFINER PROCEDURE` cannot perform transaction control.
- A procedure with a `SET` clause in its definition cannot perform transaction control.
- Transactions cannot be terminated inside an exception-handling block because it uses a subtransaction.
- An explicit transaction block opened by the caller remains a strict boundary.

**Do not design convoluted nested CALL hierarchies just to work around transaction restrictions.** Choose a clear commit unit in the application or keep a top-level procedure simple, and test it on your target server version.

## 29. Procedures without COMMIT still work in application transactions

The procedure `mark_order_paid` does not perform internal transaction control. Therefore a client can write:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

-- You can run SELECT/inspect the changes
-- within the same transaction.

COMMIT;
~~~

With this transaction, both the UPDATE and the audit INSERT form a single atomic unit.

If an exception occurs and the transaction enters an aborted state, the caller must handle rollback or savepoints appropriately.

### 29.1. Criteria for choosing the commit boundary

Ask before writing a procedure:

- Do we need **atomicity for the entire command** or per-batch commits?
- Who has enough context to decide when to commit: the DB procedure or service orchestration?
- Are there multiple SQL/HTTP side effects to coordinate at the application layer?
- Does the client use `@Transactional` or JDBC `setAutoCommit(false)`?
- Is there retry/compensation logic if part of the work already committed?

In many Java applications, **letting the service layer manage transactions** while keeping procedures free of internal `COMMIT` is easier to integrate.

## 30. Why can't functions auto-COMMIT?

A function can be invoked from:

~~~sql
SELECT
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

A single statement can invoke a function many times while evaluating rows. If each invocation could arbitrarily commit, statement and transaction atomicity would break down.

PostgreSQL forbids functions from executing transaction-ending commands under this model. Splitting commits into batches must be structured outside the statement or via a top-level procedure where permitted.

### 30.1. Functions with side effects remain inside the caller's transaction

If `add_audit_note` is called and the caller subsequently runs ROLLBACK, the audit row inserted by the function is rolled back just like normal DML. This differs from the per-batch committing procedure in the earlier example.

## 31. EXCEPTION handling in PL/pgSQL

Both functions and procedures written in PL/pgSQL can handle exceptions:

~~~sql
CREATE FUNCTION routine_lab.try_read_order(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT o.status
    INTO STRICT v_status
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;

    RETURN v_status;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN 'not_found';
END;
$$;
~~~

In PL/pgSQL, `SELECT INTO STRICT` requires exactly one row; if no row matches, it raises `NO_DATA_FOUND`. If more than one row matches (impossible for the PK in this example), it raises `TOO_MANY_ROWS`.

### 31.1. Exception blocks have subtransaction semantics

Persistent database changes made inside a block with an `EXCEPTION` handler are rolled back to the start of that block when an exception is caught, following subtransaction semantics. PL/pgSQL variables follow their own rules.

### 31.2. Do not COMMIT inside an EXCEPTION block

Do not place `COMMIT` inside a block that handles exceptions expecting PostgreSQL to terminate the transaction. This is prohibited by subtransaction semantics.

### 31.3. Do not swallow all errors

~~~sql
EXCEPTION WHEN OTHERS THEN
    RETURN 'ok';
~~~

is an anti-pattern if it hides constraint violations, permission errors, or invalid data. Catch only errors for which you have an explicit handling policy, and preserve diagnostic details for troubleshooting.

## 32. RAISE EXCEPTION and SQLSTATE

A routine can signal business errors using:

~~~sql
RAISE EXCEPTION
    'Order % cannot be processed',
    p_order_id;
~~~

Or with a custom SQLSTATE that conforms to PostgreSQL rules:

~~~sql
RAISE EXCEPTION
    USING
        ERRCODE = 'P0001',
        MESSAGE = 'Business validation failed';
~~~

The JDBC layer receives a `SQLException` containing the SQLSTATE. Using consistent codes helps the application distinguish business failures from connection or constraint errors.

### 32.1. Do not put sensitive data in exception messages

Error messages can appear in logs, traces, or API responses. Do not print tokens, secrets, sensitive customer data, or full payloads into exception text unnecessarily.

## 33. SECURITY INVOKER and SECURITY DEFINER

A routine can execute under two privilege modes:

- `SECURITY INVOKER`: uses the caller's privileges for relevant permission checks. This is the default for standard functions.
- `SECURITY DEFINER`: runs with the privileges of the routine's owner under PostgreSQL's security definer mechanism.

Example of a function reading status with owner privileges:

~~~sql
CREATE FUNCTION routine_lab.get_status_for_api(
    p_order_id BIGINT
)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = routine_lab, pg_temp
AS $$
    SELECT o.status
    FROM routine_lab.orders AS o
    WHERE o.order_id = p_order_id;
$$;
~~~

This sample illustrates the mechanism. Do not grant EXECUTE to unauthenticated users or without an authorization policy.

### 33.1. SECURITY DEFINER is not automatically better

It can let callers access data through a routine even when they lack direct SELECT privileges. That is useful in tightly designed database APIs, but it introduces **privilege escalation** risks if the routine fails to validate inputs, tenant ownership, and access paths.

### 33.2. SECURITY DEFINER procedures cannot control transactions

If a procedure is declared `SECURITY DEFINER`, it cannot use `COMMIT`/`ROLLBACK` inside. Do not combine security definer with expectations of batch self-committing.

## 34. search_path is a security concern

A `SECURITY DEFINER` function can be exploited if it uses unqualified table or function names and `search_path` includes a schema where low-privilege users can create objects.

Recommended practices:

1. Use schema-qualified object names like `routine_lab.orders` inside the routine body.
2. Set `SET search_path` to trusted schemas only, placing `pg_temp` appropriately (typically last).
3. Never include schemas where untrusted users can create objects in `search_path`.
4. Restrict `EXECUTE` to necessary roles only.
5. Never concatenate identifiers from untrusted input.

A routine running with owner privileges can touch sensitive data; therefore both the **SQL definition** and **schema object-creation permissions** must be audited.

## 35. EXECUTE privilege and default privileges

For newly created functions and procedures, PostgreSQL applies **default privileges**, under which `EXECUTE` is commonly granted to `PUBLIC` by default unless configured otherwise.

For sensitive routines, create the routine and adjust privileges within the **same transaction** to avoid a window where unintended roles could call it:

~~~sql
BEGIN;

CREATE FUNCTION routine_lab.private_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT total_amount
    FROM routine_lab.orders
    WHERE order_id = p_order_id;
$$;

REVOKE ALL
ON FUNCTION routine_lab.private_order_total(BIGINT)
FROM PUBLIC;

-- Only execute if app_reader is a role that has already been created
-- and is genuinely authorized to call the routine:
-- GRANT EXECUTE
-- ON FUNCTION routine_lab.private_order_total(BIGINT)
-- TO app_reader;

COMMIT;
~~~

### 35.1. EXECUTE privilege is not complete authorization

If a SECURITY DEFINER function returns a total amount by `order_id`, you still must verify whether the caller is authorized to view that order. Granting EXECUTE alone does not enforce tenant scoping.

### 35.2. ALTER DEFAULT PRIVILEGES

In systems with many routines, DBAs can configure default privileges for routines created by specific roles or in specific schemas. Because default privileges depend on the creating role and scope, review migration workflows carefully before altering them.

## 36. Dynamic SQL and SQL injection

PL/pgSQL provides `EXECUTE` for running dynamic SQL. This is distinct from calling a procedure via `CALL` from an SQL client.

**Unsafe:**

~~~sql
-- Illustration of string concatenation to avoid:
-- EXECUTE 'SELECT count(*) FROM ' || input_table;
~~~

If the table name comes from an untrusted source, string concatenation can cause SQL injection or reference unintended objects.

### 36.1. Quoting identifiers and binding values

Example of a function with invoker privileges:

~~~sql
CREATE FUNCTION routine_lab.count_by_status(
    p_schema NAME,
    p_table NAME,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE format(
        'SELECT count(*) FROM %I.%I WHERE status = $1',
        p_schema,
        p_table
    )
    INTO v_count
    USING p_status;

    RETURN v_count;
END;
$$;
~~~

- `format('%I', ...)` quotes identifiers safely according to PostgreSQL syntax.
- `USING` passes query values as bound parameters rather than interpolating literals.
- The calling role still requires read privileges on the target table because `SECURITY INVOKER` is used.
- This example assumes the target table has a compatible `status` column.

### 36.2. Quoting does not replace authorization

Even when table names are safely quoted, the application should still whitelist allowed schemas/tables for the specific use case. Combining SECURITY DEFINER with unchecked dynamic SQL targets is a major security risk.

## 37. Function overloading

PostgreSQL allows multiple functions with the **same name** as long as their input argument type lists differ:

~~~sql
CREATE FUNCTION routine_lab.show_value(
    p_value INTEGER
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer:' || p_value::TEXT;
$$;

CREATE FUNCTION routine_lab.show_value(
    p_value TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value;
$$;
~~~

Invocations:

~~~sql
SELECT routine_lab.show_value(10::INTEGER);
SELECT routine_lab.show_value('10'::TEXT);
~~~

PostgreSQL uses the name and parameter types to resolve the matching overload.

### 37.1. Return type cannot distinguish overloads

You cannot define two functions differing only in `RETURNS TEXT` versus `RETURNS INTEGER` when their input type lists are identical.

### 37.2. Unknown literals can cause surprises

An untyped literal like `'10'` can be resolved via type resolution rules. When overloads exist, cast explicitly:

~~~sql
SELECT routine_lab.show_value('10'::TEXT);
~~~

### 37.3. Procedures also support overloading

Identity and argument-type rules also apply to procedures under PostgreSQL resolution rules. During migrations or drops, specify exact argument signatures to avoid affecting the wrong overload.

## 38. CREATE OR REPLACE FUNCTION

When updating logic while keeping a compatible interface:

~~~sql
CREATE OR REPLACE FUNCTION routine_lab.get_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        (
            SELECT o.total_amount
            FROM routine_lab.orders AS o
            WHERE o.order_id = p_order_id
        ),
        0::NUMERIC
    );
$$;
~~~

This example changes semantics: previously, a missing order returned NULL, whereas now it returns 0. This is a business change that must be evaluated, even though PostgreSQL accepts the `OR REPLACE` syntax.

### 38.1. Limitations of OR REPLACE FUNCTION

Generally, `CREATE OR REPLACE FUNCTION` cannot be used to **change the return type** of an existing function identity. You must also respect restrictions on input parameter types and published parameter names.

For incompatible interface changes, consider:

- Creating a new function with a distinct name or signature.
- Migrating callers.
- Dropping the old function once no dependencies remain.

### 38.2. OR REPLACE does not provide semantic versioning

Keeping the same name and return type does not guarantee identical output semantics. Test functionality, permissions, side effects, performance, and expected errors.

## 39. CREATE OR REPLACE PROCEDURE

Replacing a procedure's body while keeping a compatible signature:

~~~sql
CREATE OR REPLACE PROCEDURE routine_lab.mark_order_paid(
    IN p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE routine_lab.orders AS o
    SET status = 'paid'
    WHERE o.order_id = p_order_id
      AND o.status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % is not eligible for payment',
            p_order_id;
    END IF;

    INSERT INTO routine_lab.audit_log(
        order_id, action
    )
    VALUES (p_order_id, 'paid_v2');
END;
$$;
~~~

As a result, the command logic changes while applications calling `CALL routine_lab.mark_order_paid(...)` keep the same call shape.

### 39.1. Do not treat OR REPLACE as a fix-all for signature changes

Changing parameter modes, types, or structures may require a new routine identity or a separate migration. Check your specific PostgreSQL version and caller interfaces.

### 39.2. Do not silently add COMMIT to a procedure called inside transactions

A procedure that previously did not commit internally may already be called inside `@Transactional` blocks. If an OR REPLACE update adds `COMMIT`, callers can begin failing or lose atomicity. That is a **breaking behavioral change** even when the name and signature stay identical.

## 40. Identity signatures and DROP FUNCTION/PROCEDURE

When overloads exist, dropping the intended routine requires specifying its input signature.

~~~sql
DROP FUNCTION routine_lab.show_value(INTEGER);
~~~

~~~sql
DROP FUNCTION routine_lab.show_value(TEXT);
~~~

For a procedure:

~~~sql
DROP PROCEDURE routine_lab.mark_order_paid(BIGINT);
~~~

**Note:** these DROP examples remove the lab routines created earlier; run them only when intentionally cleaning up.

### 40.1. RESTRICT and CASCADE

~~~sql
DROP FUNCTION routine_lab.get_order_total(BIGINT) RESTRICT;
~~~

PostgreSQL defaults to protecting dependent database objects with RESTRICT behavior. `CASCADE` automatically drops dependent objects tracked by PostgreSQL.

Do not add CASCADE just because DROP reports a dependency error. Inspect related database objects and external consumers first.

### 40.2. DROP PROCEDURE does not delete previously committed data

If a procedure inserted audit rows and committed them, DROP PROCEDURE only removes the routine definition. Previously committed data does not disappear.

## 41. RENAME and ALTER routine

PostgreSQL provides DDL to modify routine metadata or attributes:

~~~sql
ALTER FUNCTION routine_lab.order_category(BIGINT)
RENAME TO classify_order;
~~~

~~~sql
ALTER PROCEDURE routine_lab.mark_order_paid(BIGINT)
RENAME TO mark_order_paid_command;
~~~

These commands **actually rename the routines**; callers referencing the old names will fail.

### 41.1. SET SCHEMA and OWNER

Statements like `ALTER FUNCTION ... SET SCHEMA ...`, `ALTER PROCEDURE ... SET SCHEMA ...`, and `OWNER TO ...` are supported subject to privilege and version rules.

Do not move routines between schemas or change ownership without verifying:

- Callers using schema-qualified names.
- Grants and execution rights.
- SECURITY DEFINER behavior.
- `search_path` and referenced objects.
- Dynamic SQL strings and external application code.

## 42. Inspecting routines via pg_proc

PostgreSQL stores metadata for functions and procedures in `pg_proc`, linked to schemas via `pg_namespace`.

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(
        p.oid
    ) AS identity_arguments,
    pg_get_function_result(
        p.oid
    ) AS result_description
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine_lab'
ORDER BY p.proname, identity_arguments;
~~~

`prokind` typically distinguishes:

- `f`: normal function.
- `p`: procedure.
- `a`: aggregate.
- `w`: window function.

`pg_get_function_identity_arguments` returns the argument list used to identify the routine for DROP/ALTER, excluding default-value expressions.

### 42.1. Viewing routine definitions

Using a specific signature:

~~~sql
SELECT pg_get_functiondef(
    'routine_lab.get_order_total(bigint)'::regprocedure
);
~~~

`pg_get_functiondef` can also reconstruct the definition for a procedure when given the corresponding OID.

### 42.2. In psql

~~~text
\df+ routine_lab.*
\dfp routine_lab.*
~~~

The `\df` commands and type-filter variants help list routines. These are psql meta-commands, not SQL statements to send directly over JDBC.

## 43. information_schema.routines

When you need relatively standard metadata:

~~~sql
SELECT
    routine_schema,
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_schema = 'routine_lab'
ORDER BY routine_name;
~~~

`information_schema` enforces privilege-based visibility, so different roles may see different rows.

When you need PostgreSQL-specific attributes such as volatility, security mode, prokind, and parallel safety, `pg_proc` is usually more informative.

## 44. Checking volatility, security, and parallel flags

~~~sql
SELECT
    n.nspname AS routine_schema,
    p.proname AS routine_name,
    p.prokind,
    p.provolatile,
    p.proparallel,
    p.prosecdef,
    p.proisstrict,
    p.procost,
    p.prorows
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine_lab'
ORDER BY p.proname;
~~~

Key flag codes:

- `provolatile`: `i` immutable, `s` stable, `v` volatile.
- `proparallel`: `s` safe, `r` restricted, `u` unsafe.
- `prosecdef`: true when SECURITY DEFINER.
- `proisstrict`: true when STRICT.

This shows declared metadata, not automatic proof that the code inside the routine actually obeys the contract. Authors must declare attributes accurately.

## 45. Functions/procedures and execution plans

A simple SQL function can be optimized or inlined by PostgreSQL when it meets specific criteria, though this is **not guaranteed** for every SQL function.

A PL/pgSQL function can execute multiple internal SQL statements; inspecting `EXPLAIN` on an outer call may not reveal every internal SQL node as expected.

### 45.1. Measuring a function across multiple rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

This is a small-table demo. If a function executes a SELECT per row without being inlined/optimized, large workloads can incur overhead similar to iterative processing.

### 45.2. Prefer set-based SQL when possible

Instead of calling a function 100,000 times to execute individual SELECTs, a simple JOIN or direct query is sometimes much faster:

~~~sql
SELECT
    o.order_id,
    o.total_amount
FROM routine_lab.orders AS o;
~~~

Functions are not inherently slow in every case; the right approach is to measure `EXPLAIN (ANALYZE, BUFFERS)` and latency on a representative dataset.

### 45.3. Do not optimize by misdeclaring volatility

The planner may apply more aggressive optimizations when it sees IMMUTABLE, but assigning the wrong attribute produces wrong results. Correctness always comes before micro-optimization.

## 46. Multiple SQL statements in a procedure

A procedure often fits well when modeling a sequential multi-step command:

~~~text
CALL business_command(...)
    |
    +--> Validate input
    +--> UPDATE state
    +--> INSERT audit
    +--> Check rows affected
    +--> Return status via OUT/INOUT if needed
~~~

However, using a PL/pgSQL loop to process rows one by one is **not inherently faster** than a set-based `UPDATE ... WHERE ...` or `INSERT ... SELECT ...`.

### 46.1. Avoid unnecessary row-by-row processing

If you need to update the status for all `new` orders:

~~~sql
UPDATE routine_lab.orders
SET status = 'paid'
WHERE status = 'new';
~~~

is a set-based operation. Writing a procedure that LOOPs over each order and runs individual UPDATEs can increase overhead, lock complexity, and execution time.

A procedure is a mechanism for encapsulating logic, **not a license to replace set-based SQL with unbounded loops**.

## 47. JDBC: calling a scalar-returning function

Java with `PreparedStatement`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderLookup {
    public BigDecimal getOrderTotal(
        Connection connection,
        long orderId
    ) throws SQLException {
        String sql =
            "SELECT routine_lab.get_order_total(?)";

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, orderId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Function returned no result row"
                    );
                }
                return rs.getBigDecimal(1);
            }
        }
    }
}
~~~

When an order is not found, `get_order_total` can return SQL NULL, so `getBigDecimal(1)` returns null. The application must decide how to handle missing data rather than treating null as 0 without an explicit contract.

### 47.1. Parameter binding

Use `?` placeholders to pass values rather than concatenating `orderId` into raw SQL strings. Parameter binding makes code easier to maintain and prevents value-based SQL injection.

## 48. JDBC: calling a set-returning function

~~~java
String sql = """
    SELECT order_id, status, total_amount
    FROM routine_lab.orders_for_customer(?)
    ORDER BY order_id
    """;

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            String status = rs.getString("status");
            java.math.BigDecimal amount =
                rs.getBigDecimal("total_amount");

            // Use typed rows as needed.
        }
    }
}
~~~

A set-returning function behaves as a relation, so you can filter, JOIN, ORDER BY, and consume the ResultSet just like a regular SELECT.

## 49. JDBC: calling a procedure with CALL

A procedure that does not self-COMMIT can be invoked directly:

~~~java
String sql = "CALL routine_lab.mark_order_paid(?)";

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, 1002L);
    ps.execute();
}
~~~

For procedures with output parameters, you can use `CallableStatement` or the driver's corresponding result-handling mechanism, while verifying `CALL` syntax and behavior for your pgJDBC version.

### 49.1. JDBC escape syntax does not always map to CALL

Some drivers support JDBC escape syntax such as `{call routine(...)}`, which may translate to `SELECT` or `CALL` depending on settings like `escapeSyntaxCallMode` and routine kind. Avoid relying on habits from other databases.

When calling a PostgreSQL procedure, use explicit `CALL routine_name(?)` SQL via PreparedStatement where appropriate; for functions use `SELECT f(?)`. When using CallableStatement, consult your driver version's documentation and test actual behavior.

## 50. JDBC autocommit and procedures with COMMIT

For a procedure like `write_audit_batches` that contains internal `COMMIT`s:

- The call must be a **top-level CALL** where the server permits transaction control.
- The JDBC session must not be inside an explicit transaction block that forbids procedure COMMITs; in many cases, autocommit true is required.
- Framework transaction management like Spring `@Transactional` may open a transaction before the call, causing a procedure with COMMIT to fail.
- If the application needs to coordinate multiple atomic operations, it is better for the caller to manage COMMIT and for the procedure **not to self-commit**.

Illustrative example:

~~~java
boolean originalAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(true);

    try (PreparedStatement ps = connection.prepareStatement(
        "CALL routine_lab.write_audit_batches(?, ?)"
    )) {
        ps.setInt(1, 2);
        ps.setInt(2, 2);
        ps.execute();
    }
} finally {
    connection.setAutoCommit(originalAutoCommit);
}
~~~

**Use this code only in isolated demos.** Changing autocommit on a connection can affect active transactions and connection pool state; in real applications, obtain a dedicated managed connection configured for transaction-controlling operations rather than mutating the mode on a connection participating in a request transaction.

## 51. Spring @Transactional and routines

Scenarios:

**Function called via SELECT:**

~~~text
@Transactional service
    |
    +--> SELECT function(...)
    +--> UPDATE other_table
    +--> COMMIT/ROLLBACK decided by service
~~~

**Procedure without internal COMMIT:**

~~~text
@Transactional service
    |
    +--> CALL proc_no_commit(...)
    +--> Other SQL
    +--> COMMIT/ROLLBACK decided by service
~~~

**Procedure with internal COMMIT:**

~~~text
@Transactional service
    |
    +--> CALL proc_with_commit(...)
             |
             +--> Internal COMMIT
                   ^
                   Invalid in a prohibited
                   explicit transaction block context
~~~

### 51.1. A healthy API transaction boundary

If business logic requires atomicity across multiple repository calls and a database routine, let the service layer define the transaction and ensure the routine **does not self-COMMIT**.

Procedures with internal commits are better suited for standalone admin/batch tasks where partial commits are acceptable and retry/checkpoint logic is explicitly designed.

## 52. When to use SQL vs. PL/pgSQL?

| Scenario | Typically suitable language |
|---|---|
| Single calculation expression | `LANGUAGE sql` |
| Fixed SELECT query | `LANGUAGE sql` |
| Returning rows from a single SELECT | `LANGUAGE sql` |
| Requires IF/LOOP/variables/RAISE/exceptions | `LANGUAGE plpgsql` |
| Multi-DML command with validation | `LANGUAGE plpgsql` |
| Complex set-based logic expressible as one query | Try plain SQL first |
| Dynamic SQL with dynamic identifiers | PL/pgSQL `EXECUTE format(...) USING ...` |

PL/pgSQL excels at control flow, but it is not an automatic optimizer. When plain SQL is simple and clear, prefer it.

## 53. Criteria for choosing FUNCTION vs. PROCEDURE

Start from the **usage contract**, not the business feature name.

| Question | If "Yes" | Favored choice |
|---|---|---|
| Must the result appear in SELECT/WHERE/ORDER BY? | It is an expression | Function |
| Need to RETURN a scalar or JSONB object? | Easy to use in queries | Function |
| Need to return multiple typed rows for JOIN? | Set-returning | Function |
| Is the routine primarily a command with side effects? | Clearer semantics with CALL | Procedure |
| Need per-batch COMMIT inside the routine? | Only where top-level CALL permits | Procedure |
| Is the transaction managed by Spring/JDBC service? | Routine does not end transactions | Either; often procedure for commands |
| Need to read a table and return a value? | STABLE/appropriate SQL function | Function |
| Need multi-step validation? | PL/pgSQL | Function or procedure depending on interface |
| Need a trigger hook? | Special trigger function | Function RETURNS trigger |
| Need SQL composition/LATERAL? | Must be a relation/expression | Function |

### 53.1. When both can perform DML

Prefer a procedure when the API is designed as **an action**: processing a return, approving a transaction, changing status and logging an audit entry.

A VOLATILE function still has a place if you need to return a newly generated value via SELECT inside a transaction and all callers understand the side effects. Do not use it as if it were "side-effect-free" inside aggregate queries.

### 53.2. When the only goal is reducing network round trips

Both functions and procedures can encapsulate multiple server-side operations. Choose based on return/call semantics and transaction boundaries, not merely round-trip count.

## 54. Decision flowchart

~~~text
Does the routine need to be called in an SQL expression,
WHERE, JOIN, or SELECT FROM?
             |
         +---+---+
         |       |
        Yes      No
         |       |
      FUNCTION   Is it primarily a command with side effects?
                  |
              +---+---+
              |       |
             Yes      No
              |       |
          PROCEDURE  A FUNCTION may still work
              |
      Needs internal COMMIT/ROLLBACK?
              |
          +---+---+
          |       |
         Yes      No
          |       |
   Check top-level CALL,
   SECURITY DEFINER/SET,
   exceptions, and client transaction
          |
   If requirements aren't met:
   move commit boundary to caller
   or redesign
~~~

If a function performs pure computation, declare IMMUTABLE/STRICT/PARALLEL SAFE **only when those properties are genuinely true**.

## 55. Anti-pattern: routine with too many responsibilities

A procedure can gradually grow into:

~~~text
CALL everything(...)
  +--> authenticate user
  +--> call external service
  +--> write to 15 tables
  +--> generate invoice
  +--> send email
  +--> compute ML score
  +--> log every event
~~~

Parts of this logic may lie outside database transaction scope or require network/service orchestration.

Warning signs that splitting is needed:

- The procedure invokes multiple external systems that cannot roll back together.
- Difficult to test independently.
- Tangled permission/tenant branches.
- Operators cannot tell where the commit boundary lies.
- Every schema change forces edits to a massive procedure.
- Long-running tasks hold locks/transactions for too long.

Good design cleanly separates **transactional database invariants** from **application-level orchestration**.

## 56. Anti-pattern: using a procedure for a single SELECT

Instead of:

~~~sql
CREATE PROCEDURE routine_lab.some_lookup(...)
...
~~~

and trying to extract datasets via OUT/cursors just to fetch a customer list, consider:

~~~sql
CREATE FUNCTION routine_lab.customer_names()
RETURNS TABLE (
    customer_id BIGINT,
    customer_name TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT c.customer_id, c.customer_name
    FROM routine_lab.customers AS c;
$$;
~~~

Invocation:

~~~sql
SELECT *
FROM routine_lab.customer_names()
ORDER BY customer_id;
~~~

If logic reuse or privilege abstraction isn't needed, a direct SELECT can be simpler than a function as well.

## 57. Anti-pattern: routine enabling SQL injection

Examples to avoid:

- Concatenating raw user-supplied table names into EXECUTE.
- Concatenating payloads into SQL strings instead of parameter binding.
- SECURITY DEFINER with an untrusted search_path.
- Uncontrolled GRANT EXECUTE on sensitive routines to PUBLIC.
- Trusting a client-supplied `customer_id` as proof of ownership.

Replace with:

1. Prepared statements in Java.
2. `EXECUTE format('%I',...) USING ...` when dynamic SQL is genuinely required.
3. Identifier whitelisting.
4. Schema qualification.
5. SECURITY INVOKER when elevated privileges are unnecessary.
6. Tested auth/tenant scoping.
7. Restricting EXECUTE grants to specific roles.

## 58. Anti-pattern: function in WHERE causing N+1 queries

Example:

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE routine_lab.get_order_total(
    o.order_id
) > 100000;
~~~

If the planner cannot inline/collapse the call appropriately, the function may execute its internal query once per row.

When the data already resides in `orders`, a direct SQL query is simpler:

~~~sql
SELECT o.order_id
FROM routine_lab.orders AS o
WHERE o.total_amount > 100000;
~~~

The takeaway is not "functions are always slow," but **never hide table-access logic inside a function while ignoring EXPLAIN and invocation counts**.

## 59. Testing routines: correctness, errors, and transactions

For scalar functions:

~~~sql
SELECT
    routine_lab.line_total(100, 2) = 200
        AS positive_case,
    routine_lab.line_total(100, NULL) IS NULL
        AS strict_null_case;
~~~

For table-reading functions:

~~~sql
SELECT
    routine_lab.get_order_total(1001)
        AS actual_amount;
~~~

For row-returning functions:

~~~sql
SELECT COUNT(*)
FROM routine_lab.orders_for_customer(101);
~~~

For procedures without internal COMMIT, test inside a lab transaction:

~~~sql
BEGIN;

CALL routine_lab.mark_order_paid(1002);

SELECT status
FROM routine_lab.orders
WHERE order_id = 1002;

ROLLBACK;
~~~

### 59.1. Test expected exceptions

Test invalid `order_id`, negative amounts, duplicate operations, and permission denied cases. A routine can pass the happy path yet fail during retries or when callers lack privileges.

### 59.2. Tests must never modify production

The CALL statements and DML-performing functions in this lesson modify real data. Always use an isolated database and understand transaction boundaries.

## 60. Testing procedure transaction control

For `write_audit_batches`:

- Invoke successfully at top level.
- Invoke inside an explicit transaction and observe the expected transaction control error.
- Verify that an already-committed batch does not roll back automatically if a subsequent batch fails.
- Enforce batch size/count limits.
- Inspect audit rows before/after and verify retry policy.
- Check driver/framework autocommit settings.

Never run internal commit/rollback tests on production data just to "see what error happens."

## 61. Managing dependencies before DROP/REPLACE

Routines can be referenced by:

- Views.
- Index expressions.
- Check constraints.
- Triggers.
- Other functions/procedures.
- Generated columns or default expressions where supported.
- External Java/ORM code or BI jobs outside the database.

PostgreSQL tracks catalog dependencies, but it cannot automatically discover dynamic SQL strings or application source code.

### 61.1. A compatible replacement still requires verification

Even when `CREATE OR REPLACE FUNCTION` preserves the return type, logic semantics can change. An index expression relying on a function replaced with non-IMMUTABLE behavior may require investigation or scheduled reindexing; never judge safety by signature alone.

### 61.2. DROP CASCADE requires review

`DROP FUNCTION ... CASCADE` will drop catalog-managed dependent objects. Do not use CASCADE reflexively to clear dependency errors; inspect the full dependency closure and migration plan first.

## 62. Migration strategy for routines

A safe migration typically follows these steps:

1. Record the identity signature, owner, grants, configuration, and dependencies.
2. Maintain a test database with a representative dataset.
3. For compatible logic changes: use `CREATE OR REPLACE`.
4. For signature/return-type changes: create a new routine or new overload.
5. Migrate consumers in phases.
6. Test SQL, JDBC, permissions, and transactions.
7. Drop the old routine using `RESTRICT` once unused.
8. Monitor latency, errors, and locks/I/O after deployment.

### 62.1. Expand–migrate–contract

~~~text
EXPAND:
  CREATE FUNCTION/PROCEDURE v2 (or explicit overload)
        |
        v
MIGRATE:
  Deploy Java/SQL clients using v2, verify results
        |
        v
CONTRACT:
  Once no old callers remain,
  DROP v1 routine in a controlled manner
~~~

This is particularly useful during rolling deployments when multiple application versions run concurrently.

## 63. Rollback criteria

Before deploying, prepare:

- A script to restore the previous body and attributes.
- Return type and argument identity metadata.
- Owner and privilege definitions.
- Impact assessment on dependent objects.
- Plan to revert app code to the old routine name/signature.
- Assessment of data already modified by procedures.
- Transaction rollback or compensation plan if batches have already COMMITted.

**Rolling back a routine definition does not roll back previously committed data.** If a new procedure inserted thousands of audit or order rows, reverting the routine body will not undo those changes.

## 64. Checking routine performance

Example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    routine_lab.get_order_total(o.order_id)
FROM routine_lab.orders AS o;
~~~

In practice, you should:

- Check routine call counts.
- Measure execution time, CPU, and buffers.
- Inspect internal SQL statements with appropriate monitoring tools.
- Evaluate `pg_stat_statements` and monitoring layers.
- Compare scalar functions against JOIN/set-based queries.
- Measure procedure DML throughput, WAL generation, locks, and concurrency.
- Assess the impact of function volatility and parallel safety.
- Test prepared statements/JDBC with overloads and default parameters.

Never claim functions or procedures are inherently "faster than the other." Performance depends on internal SQL, execution plans, data volume, context, and round trips.

## 65. Common mistakes and how to handle them

### 65.1. Calling a procedure with SELECT

Wrong: `SELECT my_proc(...)`. Use `CALL my_proc(...)`.

### 65.2. Calling a function with CALL

Wrong: `CALL my_func(...)` when the object is a normal function. Use `SELECT my_func(...)` or an appropriate SQL expression context.

### 65.3. Giving a procedure RETURNS TABLE

`RETURNS TABLE` is a function interface, not valid standard syntax for `CREATE PROCEDURE`.

### 65.4. COMMIT inside a function

Functions cannot terminate transactions. Move the commit boundary to the caller or use an appropriate procedure.

### 65.5. COMMIT inside a procedure called from @Transactional

The caller's explicit transaction prohibits transaction control inside the procedure. Revisit the commit architecture.

### 65.6. COMMIT inside a SECURITY DEFINER procedure

Disallowed under PostgreSQL restrictions; do not use SECURITY DEFINER procedures for self-committing batches.

### 65.7. Marking a table-reading function as IMMUTABLE

Violates the contract and can cause stale results or invalid planner assumptions. Use STABLE or VOLATILE appropriately.

### 65.8. Marking a table-writing function as PARALLEL SAFE

Unsafe; DML-performing functions must not be arbitrarily marked SAFE.

### 65.9. Using STRICT when NULL needs COALESCE

The function will not run on NULL input, bypassing the intended NULL-handling logic.

### 65.10. Changing return type with OR REPLACE

PostgreSQL will reject this. Design a new identity or proper migration.

### 65.11. Overloading without casting literals

Can resolve unexpectedly or fail as ambiguous. Use `::INTEGER` or `::TEXT` when needed.

### 65.12. Concatenating raw table names in dynamic SQL

Creates SQL injection risks. Quote identifiers with `format('%I')` and bind values via `USING`.

### 65.13. SECURITY DEFINER with an untrusted search_path

Risks object resolution hijacking. Set a trusted search_path and schema-qualify references.

### 65.14. Forgetting REVOKE PUBLIC EXECUTE

New routines may be callable more broadly than intended depending on default privileges. Configure grants in the same transaction.

### 65.15. Using a PROCEDURE to return a table for JOINs

Far less convenient than a `RETURNS TABLE` function when SQL composition is needed.

### 65.16. Using row-by-row loops instead of set-based SQL

Introduces heavy overhead. Try `UPDATE ... WHERE` or `INSERT ... SELECT` first.

### 65.17. Dropping a routine while forgetting external callers

Java code, reports, and external dynamic SQL may still call the old routine. Audit all consumers.

### 65.18. Per-batch COMMIT procedure expecting full atomicity

Committed batches do not roll back when a later batch fails. Implement idempotency and checkpoints.

### 65.19. Using RAISE EXCEPTION without an error contract

Makes it hard for Java to distinguish business errors from system failures. Standardize SQLSTATEs and messages.

### 65.20. Confusing PL/pgSQL BEGIN with SQL BEGIN TRANSACTION

A routine's `BEGIN ... END` is a code block, not a nested transaction opener.

## 66. Decision table by business scenario

| Problem | Typically suitable solution | Reason |
|---|---|---|
| Calculate fee from quantity | SQL function IMMUTABLE | Pure computation |
| Fetch order amount | SQL function STABLE | Reads table data |
| List orders for a customer | Function RETURNS TABLE | Usable in SELECT/JOIN |
| Read function that may return null | Function with explicit return contract | SQL expression |
| Write audit row and return audit_id | VOLATILE function or INOUT procedure | Depends on interface |
| Confirm payment + audit | Procedure without internal COMMIT | Command; caller manages transaction |
| Batch data load with partial commits | Procedure with eligible transaction control | Top-level CALL |
| Aggregate totals across tables in one query | Plain SQL or function | Set-based |
| Complex operation needing IF/EXCEPTION | PL/pgSQL | Control flow |
| Verify access rights on an order | Security-aware routine/SQL/RLS | Requires auth design, not just routine type |
| Trigger on INSERT | Function RETURNS trigger | Trigger contract |
| Command sending email after COMMIT | Application/outbox pattern | DB transaction cannot span external systems |
| Return paginated data for APIs | SQL SELECT/TABLE function + paging | Do not replace every API query with procedures |

There is no rule stating "every write operation must be a procedure"; PostgreSQL supports multiple patterns. **The guiding criteria are call contract, output shape, transaction boundary, and permissions.**

## 67. Workflow for designing a new routine

**Step 1 — Define inputs.** Parameters, nullability, defaults, constraints, names, and types.

**Step 2 — Define outputs.** Scalar, TABLE/SETOF, output status, or no output.

**Step 3 — Choose Function vs. Procedure.** Needs to be called in SELECT/JOIN or primarily a CALL command?

**Step 4 — Choose transaction owner.** Caller or top-level procedure? Are partial commits needed?

**Step 5 — Choose language.** Plain single SELECT fits SQL; multi-step workflows fit PL/pgSQL when needed.

**Step 6 — Declare accurate attributes.** VOLATILE/STABLE/IMMUTABLE, STRICT, PARALLEL, SECURITY.

**Step 7 — Define permissions.** Owner role, GRANT EXECUTE, schema privileges, RLS/auth.

**Step 8 — Design errors/retries.** SQLSTATE, idempotency, exceptions, audit, and checkpoints.

**Step 9 — Measure performance.** EXPLAIN, function call count, DML WAL/locks, concurrency.

**Step 10 — Test with JDBC/frameworks.** Autocommit, prepared calls, output parameters, transaction boundaries.

**Step 11 — Manage migrations.** Source control, CREATE OR REPLACE when compatible, versioned signatures for breaking changes.

**Step 12 — Monitor post-deployment.** Errors, latency, audit consistency, and consumers.

## 68. Practice exercises

### Exercise 1 — Scalar function

Write a function calculating `price * quantity`.

**Hint:** `CREATE FUNCTION ... RETURNS NUMERIC LANGUAGE sql`.

### Exercise 2 — Calling a function

Call the function above from SELECT with inputs 10000 and 3.

**Hint:** `SELECT schema.func(10000,3);`.

### Exercise 3 — IMMUTABLE

Why can a function multiplying two numbers be IMMUTABLE?

**Hint:** the result depends solely on its inputs.

### Exercise 4 — STABLE

Why shouldn't a function reading `total_amount` from a table be IMMUTABLE?

**Hint:** table data can change.

### Exercise 5 — VOLATILE

What volatility should a function performing an audit INSERT declare?

**Hint:** VOLATILE.

### Exercise 6 — STRICT

What happens when NULL is passed to a STRICT function?

**Hint:** the function does not execute; it returns SQL NULL.

### Exercise 7 — Meaningful NULL

If a NULL `p_discount` must be treated as 0, should STRICT be used?

**Hint:** no, if you want the function body to handle NULL.

### Exercise 8 — RETURNS TABLE

Create a function returning `order_id` and `status` for a given `customer_id`.

**Hint:** RETURNS TABLE + SELECT.

### Exercise 9 — RETURN QUERY

When do you use RETURN QUERY instead of scalar RETURN?

**Hint:** in a set-returning PL/pgSQL function.

### Exercise 10 — LATERAL

Use a multi-row returning function per customer inside a JOIN.

**Hint:** `CROSS JOIN LATERAL function(c.customer_id)`.

### Exercise 11 — Basic procedure

Create a procedure that inserts a row into `audit_log`.

**Hint:** CREATE PROCEDURE ... LANGUAGE plpgsql, invoked with CALL.

### Exercise 12 — CALL

Can a procedure be called in a WHERE clause?

**Hint:** no, CALL is not an expression.

### Exercise 13 — INOUT

Given a procedure with `INOUT p_message`, how do you call it?

**Hint:** CALL proc(input, NULL) in the context of the lesson's example.

### Exercise 14 — Function transactions

Can a function execute COMMIT?

**Hint:** no.

### Exercise 15 — Procedure transactions

Can a procedure execute COMMIT in every CALL?

**Hint:** no; it requires a top-level context, no explicit transaction block, and adherence to other restrictions.

### Exercise 16 — BEGIN differences

Does PL/pgSQL BEGIN start an independent transaction?

**Hint:** no, it is a block.

### Exercise 17 — JDBC autocommit

Why can a procedure with internal COMMIT fail when called inside `@Transactional`?

**Hint:** the caller has an explicit transaction block.

### Exercise 18 — Partial commits

Batch 1 COMMITs, batch 2 fails. Does batch 1 roll back automatically?

**Hint:** no.

### Exercise 19 — SECURITY DEFINER

When must you pay special attention to `search_path`?

**Hint:** when a routine runs with owner privileges and could resolve objects in untrusted schemas.

### Exercise 20 — GRANT EXECUTE

Why check `PUBLIC` default privileges?

**Hint:** newly created functions/procedures may be callable more broadly than intended.

### Exercise 21 — Dynamic SQL

How do you construct dynamic table names from input more safely?

**Hint:** `format('%I', identifier)`, passing values via `USING`.

### Exercise 22 — Overloading

Can two functions with different input types share the same name?

**Hint:** yes.

### Exercise 23 — Return type overloading

Can two functions differing only in RETURNS type, with identical input types, coexist?

**Hint:** no.

### Exercise 24 — OR REPLACE

Why can't you arbitrarily change return types using CREATE OR REPLACE FUNCTION?

**Hint:** the return type is part of the contract protected by PostgreSQL.

### Exercise 25 — DROP signature

You have `show_value(integer)` and `show_value(text)`. How do you drop the integer overload?

**Hint:** `DROP FUNCTION schema.show_value(integer)`.

### Exercise 26 — Catalog

In `pg_proc`, what does `prokind='p'` mean?

**Hint:** procedure.

### Exercise 27 — pg_get_functiondef

How do you retrieve a routine's definition by signature?

**Hint:** `pg_get_functiondef('schema.func(bigint)'::regprocedure)`.

### Exercise 28 — Function call overhead

Why can calling a table-reading function per row perform worse than a JOIN?

**Hint:** repeated executions/internal SQL and overhead; always measure.

### Exercise 29 — Procedure loops

Should you loop 100,000 separate UPDATEs when `UPDATE ... WHERE` works?

**Hint:** prefer set-based SQL when suitable.

### Exercise 30 — Triggers

Can a trigger function be called normally from SELECT instead of via CREATE TRIGGER?

**Hint:** trigger functions have a special contract.

### Exercise 31 — Transaction owner

An application needs atomicity across 3 repository calls. Where should the commit boundary live?

**Hint:** typically in the service/transaction manager, with the procedure not self-committing.

### Exercise 32 — Idempotency

Why might `mark_order_paid` fail when a caller retries after the first attempt already committed?

**Hint:** the status already changed, so `status='new'` no longer matches.

### Exercise 33 — Exceptions

Why shouldn't you write `WHEN OTHERS THEN RETURN 'ok'`?

**Hint:** it masks critical errors.

### Exercise 34 — Parallel safe

Can a function that inserts audit rows be marked PARALLEL SAFE?

**Hint:** no.

### Exercise 35 — Versioned routines

When changing a public routine's signature, why is creating v2 usually safer than dropping v1 immediately?

**Hint:** it lets callers migrate gradually and makes rollback easier.

## 69. Frequently asked questions

### Can functions perform UPDATE/INSERT?

Yes, an eligible function—typically declared `VOLATILE`—can perform DML and cause side effects. However, a function cannot execute COMMIT/ROLLBACK on the transaction.

### Must a procedure end with COMMIT?

No. If a procedure contains no COMMIT, its changes belong to the caller's transaction just like other SQL statements. Invoking `CALL` does not automatically force a procedure to end the transaction in its body.

### Can a procedure return data?

It can via OUT/INOUT parameters in supported versions, where `CALL` returns a corresponding result row. However, it cannot replace a `RETURNS TABLE` function used as a relation in SELECT/JOIN.

### Can procedures be written in LANGUAGE sql?

Yes. PostgreSQL supports SQL-language procedures in addition to PL/pgSQL and other supported languages. For workflows requiring IF/LOOP/RAISE, PL/pgSQL is generally easier to use.

### Must a function have RETURNS?

Functions have a return type contract. If you need command-like behavior with no output value, `RETURNS void` exists, though it does not turn a function into a procedure or enable internal COMMITs.

### Can a RETURNS void function be called with CALL?

No, because it is still a function. It is normally called via `SELECT schema.func(...)`.

### When should SECURITY DEFINER be chosen?

When there is a clear requirement for a routine to perform a specific operation with elevated privileges, backed by input validation, explicit grants, a safe `search_path`, schema qualification, and permission testing. Do not use it by default.

### Does IMMUTABLE make a function faster?

It gives the planner strong guarantees that unlock optimization opportunities, but only if the function is genuinely immutable. Misdeclaring it can cause incorrect results.

### Can procedures bypass Spring transactions?

No. If Spring has opened an explicit transaction, a procedure with internal COMMITs will be rejected by PostgreSQL. Define your transaction boundaries clearly instead of trying to work around them.

### Should all business logic live in stored routines?

Not necessarily. Operations requiring tight data consistency close to the database can make sense in routines; logic spanning multiple services, presentation, or complex authorization may belong in the application layer. Clear separation of responsibilities is key.

### Does OR REPLACE automatically update Java callers?

No. Signatures, named parameters, return semantics, and application SQL strings remain managed by application code. Breaking changes require coordinated deployments.

### When should you benchmark?

When a routine runs frequently, appears in WHERE/JOIN clauses, processes heavy DML, or manages transaction control. Use EXPLAIN, load tests, and appropriate monitoring for I/O, WAL, locks, CPU, and concurrency.

## 70. Summary

- **`CREATE FUNCTION`** defines a routine with `RETURNS`, usable as an **SQL expression** or a set-returning relation.
- **`CREATE PROCEDURE`** defines a routine invoked with **`CALL`**, typically suited for commands/workflows with side effects.
- Functions can return scalars, composites, `SETOF`, or `RETURNS TABLE`; procedures can use output parameters but lack direct composition in SELECT/JOIN.
- **Functions cannot COMMIT/ROLLBACK**. Procedures can control transactions only when the invocation, attributes, and context satisfy PostgreSQL restrictions.
- **`BEGIN ... END` in PL/pgSQL is a code block**, not BEGIN TRANSACTION.
- Functions can execute DML and must be declared `VOLATILE` appropriately; never assume functions are pure.
- **`IMMUTABLE`, `STABLE`, and `VOLATILE`** form the routine's contract with the planner and snapshot behavior. Never misdeclare them to force optimizations.
- **`STRICT`** returns NULL on NULL input without executing the body, making it unsuitable when custom NULL handling is required.
- **`PARALLEL SAFE/RESTRICTED/UNSAFE`** governs parallel query safety and must not be assigned arbitrarily.
- `LANGUAGE sql` suits simple calculations/queries; `LANGUAGE plpgsql` suits variables, conditionals, loops, RAISE, and exception handling.
- **`SECURITY DEFINER`** carries risks if `search_path` and EXECUTE privileges are uncontrolled; favor schema qualification and least privilege.
- **CREATE OR REPLACE** is suitable only when preserving a compatible contract; changes to return types, signatures, or semantics may warrant a new versioned routine.
- With overloads, specify **explicit argument types** to call, ALTER, or DROP the intended routine.
- In Java/JDBC, functions are typically called with `SELECT f(?)`; procedures with `CALL p(?)`. Procedures with internal COMMITs require special attention to autocommit and `@Transactional`.
- **Set-based SQL is usually simpler than loops** over many rows; wrapping SQL in a function or procedure does not make the inner SQL faster.
- Rolling back a routine definition does not roll back data already committed by a procedure.
- The best choice rests on **result shape, invocation style, transaction owner, privileges, semantics, maintainability, and performance**.

Final diagram:

~~~text
Business requirement
       |
       v
Need a value or row set usable in SELECT?
       |
    +--+--+
    |     |
   Yes    No
    |     |
 FUNCTION  Primarily a multi-step command?
    |          |
    |       +--+--+
    |       |     |
    |      Yes    No
    |       |     |
    |   PROCEDURE  Plain SQL may suffice
    |       |
    |       v
    |  Need internal COMMIT?
    |       |
    |       v
    |  Check CALL context, client transaction,
    |  SECURITY DEFINER/SET, and error semantics
    |       |
    +-------+
            |
            v
Choose LANGUAGE, attributes, grants, error contract
            |
            v
Test correctness + transactions + performance
            |
            v
Versioned migration, deploy, and monitor
~~~

The key takeaway is not that "functions are better than procedures" or vice versa, but rather **placing the right execution contract at the right layer**. When the goal is an SQL expression or result set, think function; when the goal is a business action, consider a procedure; when the goal is splitting transactions, check **PostgreSQL's CALL restrictions and the application's transaction boundary** first.
