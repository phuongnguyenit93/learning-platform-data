# Writing SQL-Language Functions and Optimization in PostgreSQL

In PostgreSQL, a **user-defined function** (UDF) lets you name a calculation or query so multiple SQL statements can reuse it. When the logic is primarily a single expression or a `SELECT` query, `LANGUAGE SQL` is usually a cleaner and more natural fit than jumping straight to `PL/pgSQL`.

For example, a system needs to compute a tax-inclusive amount using an agreed-upon rule:

```sql
CREATE FUNCTION public.amount_with_tax(
    p_amount NUMERIC,
    p_rate_percent NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT ROUND(
        p_amount * (1 + p_rate_percent / 100),
        2
    );
$$;
```

Instead of duplicating the formula across the application:

```sql
SELECT
    order_id,
    public.amount_with_tax(amount, 8) AS total_after_tax
FROM orders;
```

What makes this compelling is that PostgreSQL **can optimize certain SQL-language functions by folding their logic directly into the calling query**—a technique known as **SQL function inlining**. When inlining succeeds, the planner sees the underlying expression or query and can leverage indexes, push down predicates, reorder joins, and cost execution accurately.

However, not every SQL function can be inlined. Factors such as body structure, return type, volatility, `STRICT`, security attributes, function `SET` clauses, and invocation form all play a role. Sometimes a function runs correctly yet blocks optimization; other times a tiny function incurs per-row invocation overhead across millions of rows.

This lesson explains how to **write SQL-language functions** and accurately understand PostgreSQL's **optimization capabilities**, from syntax to `EXPLAIN`, trade-offs between reuse and performance, security, semantic correctness, and deployment strategies.

---

## 1. Learning objectives

After this lesson, you can:

1. Write SQL-language functions using `CREATE FUNCTION ... LANGUAGE SQL` with explicit parameters and return types.
2. Distinguish **scalar** functions from **set-returning functions** (SRFs).
3. Create functions with `RETURNS TABLE`, `RETURNS SETOF`, and `RETURNS void`, choosing the right result shape.
4. Pass positional, named, and default arguments cleanly.
5. Distinguish `IMMUTABLE`, `STABLE`, and `VOLATILE`, understanding their impact on correctness and the optimizer.
6. Explain `STRICT` / `RETURNS NULL ON NULL INPUT` and its consequences when NULLs appear in calculations.
7. Understand `PARALLEL SAFE`, `PARALLEL RESTRICTED`, and `PARALLEL UNSAFE`.
8. Explain **scalar inlining** and **table-function inlining**, why they help, and why they are never guaranteed.
9. Identify constructs and settings that block inlining—especially `SECURITY DEFINER` and function-level `SET` clauses.
10. Use `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` to inspect how functions execute against underlying tables.
11. Interpret `COST` and `ROWS` as **planner estimates**, not runtime guarantees.
12. Use SQL functions in `SELECT`, `WHERE`, `JOIN LATERAL`, and reporting queries.
13. Recognize when a wrapper hurts index usage or triggers excessive repeated calls.
14. Distinguish SQL functions from `PROCEDURE` and `PL/pgSQL`.
15. Design safe access privileges, `search_path`, overloads, and signature changes.
16. Test results, NULL handling, permissions, and execution plans before production rollout.

**Scope:** Modern PostgreSQL. Inlining rules are version- and query-dependent optimizations, **not mandatory SQL guarantees**. Lab exercises use a dedicated schema and should only run on a database where creating and dropping test objects is permitted. This lesson focuses on instructional content; production testing follows your standard release workflow.

---

## 2. Why use SQL functions?

There are three main reasons.

### 2.1. Avoid duplicating formulas

If ten reports compute:

```sql
ROUND(amount * (1 + tax_rate / 100), 2)
```

a clearly named function ensures every report applies the exact same calculation.

### 2.2. Provide a parameterized query interface

A system needs to list orders for a tenant within a time window:

```sql
SELECT *
FROM application.orders
WHERE tenant_id = 10
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

An SQL function can encapsulate that query behind `tenant_id`, `from_time`, and `to_time` parameters. Unlike a regular view, a function accepts **caller-supplied parameters**.

### 2.3. Clarify business semantics

Names like `net_payment_amount`, `orders_in_period`, or `normalize_label` communicate intent better than a sprawling inline expression.

Still, a good name does not make the logic correct: a function named `calculate_revenue` is still wrong if it confuses "order total" with "cash collected."

### 2.4. Reuse must not sacrifice query optimization blindly

A wrapper may look clean to developers while obscuring predicates from the planner or triggering millions of repeated evaluations. For functions on hot query paths, always inspect **both the data contract and the execution plan**.

---

## 3. What is an SQL function? Comparison with PL/pgSQL and procedures

In PostgreSQL, routines can be written in multiple languages, including `LANGUAGE SQL` and `LANGUAGE plpgsql`.

| Feature | SQL function | PL/pgSQL function | Procedure |
| --- | --- | --- | --- |
| Declared with | `CREATE FUNCTION` | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Language | `LANGUAGE SQL` | `LANGUAGE plpgsql` | SQL or eligible procedural language |
| Typical call | `SELECT f(...)` or in an expression | `SELECT f(...)` | `CALL p(...)` |
| Best suited for | Expressions, single queries, `SELECT` interfaces | Branching, loops, procedural logic | Procedural tasks, multi-step orchestration |
| SQL function inlining | Eligible in certain cases | Not eligible for SQL-body inlining | Not applicable as an expression function |
| Can cause side effects | Yes, with appropriate logic and attributes | Yes | Yes |
| Transaction control | Cannot `COMMIT`/`ROLLBACK` like a procedure | Cannot manage transactions inside a function | Some `CALL` contexts permit transaction control within PostgreSQL limits |

**Do not equate SQL functions with stored procedures.** In PostgreSQL, a `FUNCTION` participates in query expressions and declares a return type; a `PROCEDURE` is invoked via `CALL` and has a distinct contract.

### 3.1. An SQL function is not a text-substitution "macro"

PostgreSQL stores the function definition and can:

- Inline certain eligible functions.
- Execute the function via standard function-call evaluation.
- Use metadata like volatility, `COST`, and `ROWS` to build execution plans.
- Apply other query-dependent optimizations.

Using `LANGUAGE SQL` **creates the opportunity** for inlining—it does not guarantee expansion.

### 3.2. When to choose PL/pgSQL

If the logic requires `IF` branches, loops, exception handling, dynamic SQL, or multi-step workflows, PL/pgSQL is usually a better fit.

Never force a complex procedural workflow into a contorted SQL expression hoping it will inline—readability and correctness come first.

---

## 4. PostgreSQL lab: customers and orders

Let us build a dataset large enough to demonstrate scalar functions, table functions, aggregations, and query plans.

> **Warning:** `DROP SCHEMA ... CASCADE` deletes every object inside a matching schema. Run it only on a **disposable practice database**, never on production or a schema containing real data.

### 4.1. Create the schema

```sql
DROP SCHEMA IF EXISTS sqlfn_lab CASCADE;
CREATE SCHEMA sqlfn_lab;
```

### 4.2. Customers table

```sql
CREATE TABLE sqlfn_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('STANDARD', 'PREMIUM')),
    PRIMARY KEY (tenant_id, customer_id)
);
```

### 4.3. Orders table

```sql
CREATE TABLE sqlfn_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED', 'REFUNDED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES sqlfn_lab.customers(tenant_id, customer_id)
);
```

**Grain:** one row in `orders` represents one order within a tenant. Every join must include `tenant_id` so customers are never matched across tenants.

### 4.4. Populate 600 customers

```sql
INSERT INTO sqlfn_lab.customers (
    tenant_id, customer_id, display_name, segment
)
SELECT
    t.tenant_id,
    g.n,
    'Customer ' || t.tenant_id || '-' || g.n,
    CASE WHEN g.n % 5 = 0
         THEN 'PREMIUM'
         ELSE 'STANDARD'
    END
FROM (VALUES (10), (20)) AS t(tenant_id)
CROSS JOIN generate_series(1, 300) AS g(n);
```

### 4.5. Populate 60,000 orders

```sql
INSERT INTO sqlfn_lab.orders (
    tenant_id, order_id, customer_id,
    ordered_at, status, amount
)
SELECT
    CASE WHEN g.n % 2 = 0 THEN 10 ELSE 20 END,
    g.n::BIGINT,
    (g.n % 300) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 120) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    CASE
        WHEN g.n % 10 = 0 THEN 'CANCELED'
        WHEN g.n % 10 = 1 THEN 'PENDING'
        WHEN g.n % 10 = 2 THEN 'REFUNDED'
        ELSE 'PAID'
    END,
    ROUND(
        10::NUMERIC + (g.n % 5000)::NUMERIC / 100,
        2
    )
FROM generate_series(1, 60000) AS g(n);
```

This dataset contains two tenants, many customers, multiple order statuses, and timestamps spanning early January through late April 2026 in UTC.

### 4.6. Create indexes for filters and joins

```sql
CREATE INDEX idx_sqlfn_orders_tenant_time
ON sqlfn_lab.orders (tenant_id, ordered_at);

CREATE INDEX idx_sqlfn_orders_tenant_status_time
ON sqlfn_lab.orders (tenant_id, status, ordered_at);

CREATE INDEX idx_sqlfn_orders_tenant_customer
ON sqlfn_lab.orders (tenant_id, customer_id);

ANALYZE sqlfn_lab.orders;
ANALYZE sqlfn_lab.customers;
```

These indexes are **illustrative candidates**. In real systems, never create overlapping indexes without weighing read gains against write amplification and storage cost.

### 4.7. Verify baseline data

```sql
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'PAID')
        AS paid_order_value
FROM sqlfn_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

We have 60,000 orders split evenly by parity: **30,000 orders per tenant**. Status counts follow the generation modulo formulas above.

---

## 5. Basic CREATE FUNCTION syntax

An SQL function typically has this structure:

```sql
CREATE FUNCTION schema_name.function_name(
    parameter_name parameter_type,
    ...
)
RETURNS return_type
LANGUAGE SQL
[volatility / null handling / parallel / cost options]
AS $$
    SELECT expression_or_query;
$$;
```

Key parts:

- **Function name and schema:** identifies the callable object.
- **Parameters:** names, types, modes, and optional defaults.
- **RETURNS:** scalar, record, table, or set result shape.
- **LANGUAGE SQL:** body is written in SQL.
- **Attributes:** `IMMUTABLE`/`STABLE`/`VOLATILE`, `STRICT`, `PARALLEL ...`, `COST`, `ROWS`, and security attributes.
- **Body:** an SQL query or statement sequence in a PostgreSQL-supported form.

### 5.1. Simple addition function

```sql
CREATE FUNCTION sqlfn_lab.add_integers(
    p_a INTEGER,
    p_b INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_a + p_b;
$$;
```

Call:

```sql
SELECT sqlfn_lab.add_integers(5, 7) AS result;
```

Result is `12`.

### 5.2. Parameters can be referenced by name

In a string-bodied SQL function, parameters can be referenced by declared name:

```sql
SELECT p_a + p_b;
```

or by position:

```sql
SELECT $1 + $2;
```

**Recommendation:** choose distinct names like `p_amount` and `p_rate` to avoid colliding with column names in complex queries. When parameter names match column names, PostgreSQL applies specific name resolution rules; never write ambiguous queries.

### 5.3. Using dollar quoting

```sql
AS $$
    SELECT p_a + p_b;
$$;
```

Dollar-quoted strings eliminate nested single-quote escaping, especially when bodies contain string literals. Tags like `$body$...$body$` can be used when nesting blocks.

Dollar quotes are definition delimiters, **not a way to parameterize user input**. Application calls from Java must still bind parameters.

---

## 6. Scalar function calculating tax-inclusive amount

Example of a pure calculation function:

```sql
CREATE FUNCTION sqlfn_lab.amount_with_tax(
    p_amount NUMERIC,
    p_rate_percent NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT ROUND(
        p_amount * (1 + p_rate_percent / 100),
        2
    );
$$;
```

### 6.1. Direct call

```sql
SELECT
    sqlfn_lab.amount_with_tax(100.00, 8) AS gross_value,
    sqlfn_lab.amount_with_tax(100.00, 0) AS no_tax;
```

Result:

| gross_value | no_tax |
| ---: | ---: |
| 108.00 | 100.00 |

### 6.2. Calling in SELECT against a table

```sql
SELECT
    tenant_id,
    order_id,
    amount,
    sqlfn_lab.amount_with_tax(amount, 8)
        AS total_after_tax
FROM sqlfn_lab.orders
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

### 6.3. Why is IMMUTABLE appropriate here?

For the same two numeric inputs, the function only performs decimal arithmetic and rounding. It never reads tables, clocks, or session settings that could alter the output.

**However:** a tax formula that depends on year, country, or current statutory rates stored in a configuration table is no longer pure like this. Never mark a function `IMMUTABLE` just because its name says "calculate tax."

### 6.4. Why STRICT?

If `p_amount` or `p_rate_percent` is NULL, the tax-inclusive amount is undefined. `STRICT` tells PostgreSQL to return NULL immediately whenever any argument is NULL, skipping body execution.

### 6.5. Rounding is part of the contract

`ROUND(...,2)` establishes the rounding policy here. If business rules require rounding per line item before summing, results can differ from summing first and rounding once. Reusing a function enforces consistency, though you must still choose the right accounting policy.

---

## 7. RETURNS NULL ON NULL INPUT and CALLED ON NULL INPUT

PostgreSQL lets you declare how a function handles NULL inputs.

### 7.1. STRICT

These two clauses are equivalent:

```sql
STRICT
```

and:

```sql
RETURNS NULL ON NULL INPUT
```

When any argument is NULL, PostgreSQL returns NULL directly without executing the body.

Example:

```sql
SELECT sqlfn_lab.amount_with_tax(
    NULL::NUMERIC,
    8::NUMERIC
);
```

Returns `NULL`.

### 7.2. CALLED ON NULL INPUT

This is the default when `STRICT` is omitted. The function body executes and defines its own NULL semantics.

Example treating NULL as 0:

```sql
CREATE FUNCTION sqlfn_lab.null_to_zero(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(p_value, 0::NUMERIC);
$$;
```

```sql
SELECT
    sqlfn_lab.null_to_zero(NULL::NUMERIC) AS a,
    sqlfn_lab.null_to_zero(15::NUMERIC) AS b;
```

Returns `a=0`, `b=15`.

### 7.3. Mislabeling STRICT changes results

If `null_to_zero` were marked `STRICT`, `null_to_zero(NULL)` would return NULL before running `COALESCE`, violating the "NULL becomes 0" contract.

**Function attributes are part of semantics**, not merely optimization hints.

---

## 8. Default parameters and named calls

SQL functions can define default parameters:

```sql
CREATE FUNCTION sqlfn_lab.add_percent(
    p_amount NUMERIC,
    p_percent NUMERIC DEFAULT 10
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_amount * (1 + p_percent / 100);
$$;
```

Positional call:

```sql
SELECT
    sqlfn_lab.add_percent(100) AS default_ten_percent,
    sqlfn_lab.add_percent(100, 5) AS five_percent;
```

Named call:

```sql
SELECT sqlfn_lab.add_percent(
    p_percent => 12,
    p_amount => 100
) AS twelve_percent;
```

### 8.1. Overloading and DEFAULT caveats

PostgreSQL supports **function overloading**: multiple functions sharing a name with different input parameter types/lists.

Combining overloads with default arguments and implicit casts can make calls ambiguous or resolve to an unexpected overload.

Never create dozens of near-identical overloads expecting PostgreSQL to guess your intent intuitively.

### 8.2. DEFAULT differs from NULL

If the caller omits `p_percent`, `DEFAULT 10` applies. If the caller **explicitly passes NULL**, that NULL is passed as the argument, and a `STRICT` function returns NULL.

```sql
SELECT
    sqlfn_lab.add_percent(100) AS omitted,
    sqlfn_lab.add_percent(100, NULL::NUMERIC)
        AS explicit_null;
```

These return `110` and `NULL`, respectively.

---

## 9. SQL functions can return multiple rows

To reuse a parameterized query, use `RETURNS TABLE`.

```sql
CREATE FUNCTION sqlfn_lab.orders_in_period(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
ROWS 100
AS $$
    SELECT
        o.tenant_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.amount
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to;
$$;
```

### 9.1. Calling a table function in FROM

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
ORDER BY ordered_at, order_id
LIMIT 20;
```

A multi-row returning function acts as a data source in `FROM`.

### 9.2. RETURNS TABLE is a column contract

Callers are guaranteed these columns:

```text
tenant_id    INTEGER
order_id     BIGINT
ordered_at   TIMESTAMPTZ
status       TEXT
amount       NUMERIC
```

Column order, names, and types matter to consumers. If the body changes column order or returns incompatible types, PostgreSQL reports an error at creation or execution depending on body form and checking mode.

### 9.3. Why STABLE?

The function queries the `orders` table. Results depend on database state and can change across statements or transactions. Therefore it **must not be marked IMMUTABLE**.

`STABLE` accurately captures a read-only table query observing a consistent snapshot under PostgreSQL's `STABLE` rules. Correctness still depends on the body and any nested functions it calls.

### 9.4. Why omit ORDER BY inside the function?

Display ordering is the caller's responsibility when a sorted output contract is required:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

Set-returning functions should not encourage clients to rely on incidental plan ordering. When using `LIMIT`, place a deterministic `ORDER BY` in the same query selecting the top-N rows.

### 9.5. Why declare ROWS 100?

`ROWS` is an **estimated return row count** for the planner on set-returning functions, not a hard cap. If a period contains 10,000 matching orders, the function still returns all 10,000; `ROWS 100` simply informs planner cost estimates where applicable.

---

## 10. RETURNS SETOF: another way to return sets

A function can return multiple values of a single type:

```sql
CREATE FUNCTION sqlfn_lab.recent_tenant_order_ids(
    p_tenant_id INTEGER,
    p_limit INTEGER DEFAULT 10
)
RETURNS SETOF BIGINT
LANGUAGE SQL
STABLE
ROWS 10
AS $$
    SELECT o.order_id
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT GREATEST(p_limit, 0);
$$;
```

Invocation:

```sql
SELECT order_id
FROM sqlfn_lab.recent_tenant_order_ids(10, 5)
    AS result(order_id);
```

### 10.1. SETOF vs. scalar

- `RETURNS BIGINT`: one `BIGINT` value (or NULL).
- `RETURNS SETOF BIGINT`: zero, one, or many `BIGINT` values.
- `RETURNS TABLE (...)`: zero, one, or many multi-column rows.

### 10.2. LIMIT is part of semantics

This function intentionally bounds its output and includes `ORDER BY` inside the inner `SELECT` to define top-N selection. Callers should still specify an outer `ORDER BY` if final presentation order must be guaranteed.

### 10.3. ROWS is not LIMIT

`ROWS 10` is a planner hint, whereas `LIMIT GREATEST(p_limit,0)` actually caps emitted rows. Never confuse the two.

### 10.4. RETURNS void

SQL functions can also return `void`. This suits operations needing no output payload, though if the goal is multi-step workflow orchestration with side effects and transaction control, compare against procedures and PL/pgSQL rather than abusing `RETURNS void` SQL functions.

---

## 11. Reporting aggregation function with RETURNS TABLE

Example reporting PAID order counts and total value per UTC day within a window for one tenant:

```sql
CREATE FUNCTION sqlfn_lab.daily_paid_order_value(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    day_utc DATE,
    paid_order_count BIGINT,
    paid_order_value NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
ROWS 120
AS $$
    SELECT
        (o.ordered_at AT TIME ZONE 'UTC')::DATE
            AS day_utc,
        COUNT(*) AS paid_order_count,
        SUM(o.amount) AS paid_order_value
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = 'PAID'
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to
    GROUP BY
        (o.ordered_at AT TIME ZONE 'UTC')::DATE;
$$;
```

Invocation:

```sql
SELECT
    day_utc,
    paid_order_count,
    paid_order_value
FROM sqlfn_lab.daily_paid_order_value(
    10,
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
)
ORDER BY day_utc;
```

### 11.1. Why does COUNT(*) return BIGINT?

In PostgreSQL, `COUNT(*)` returns `BIGINT`. Therefore `paid_order_count BIGINT` matches the result type cleanly.

### 11.2. Why does SUM(amount) return NUMERIC?

`amount` is `NUMERIC`, so its sum is `NUMERIC`. Declaring `INTEGER` or `BIGINT` inappropriately would force risky narrowing casts or design mismatches.

### 11.3. Empty results

When a date range has no PAID orders, `GROUP BY day_utc` emits no groups. This `RETURNS TABLE` function returns **0 rows**, not a summary row with 0.

If a dashboard needs every calendar day including zero-order days, generate a date series using `generate_series` and `LEFT JOIN` the daily aggregates, or design the function to emit the full date spine.

### 11.4. Revenue semantics

`paid_order_value` here is solely the sum of `amount` for orders **currently in status PAID**, grouped by **order placement date in UTC**. It is not settled cash flow, nor does it reflect payment timestamps or refunds. Function names and documentation must state these semantics precisely.

---

## 12. Using SQL functions in JOIN LATERAL

A table-returning function taking parameters from an outer row can be invoked via `LATERAL`.

Example: each customer in tenant 10 needs up to three most recent order IDs.

```sql
CREATE FUNCTION sqlfn_lab.latest_order_ids_for_customer(
    p_tenant_id INTEGER,
    p_customer_id INTEGER,
    p_limit INTEGER DEFAULT 3
)
RETURNS TABLE (
    order_id BIGINT,
    ordered_at TIMESTAMPTZ
)
LANGUAGE SQL
STABLE
ROWS 3
AS $$
    SELECT o.order_id, o.ordered_at
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.customer_id = p_customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT GREATEST(p_limit, 0);
$$;
```

Invocation:

```sql
SELECT
    c.customer_id,
    c.display_name,
    x.order_id,
    x.ordered_at
FROM sqlfn_lab.customers AS c
LEFT JOIN LATERAL
    sqlfn_lab.latest_order_ids_for_customer(
        c.tenant_id, c.customer_id, 3
    ) AS x ON TRUE
WHERE c.tenant_id = 10
  AND c.customer_id IN (1, 2, 3)
ORDER BY c.customer_id, x.ordered_at DESC NULLS LAST;
```

### 12.1. LATERAL references outer row values

The function receives `c.tenant_id` and `c.customer_id` from each outer customer row. `LEFT JOIN LATERAL` retains the customer even when the function returns 0 rows.

### 12.2. Do not assume this is optimal for all customers

For three customers, an indexed lookup per customer works well. Across millions of customers, repeated function scans can be costly. Compare against:

- `ROW_NUMBER() OVER (PARTITION BY customer_id ...)`.
- `DISTINCT ON` when only top-1 is needed.
- Direct joins optimized by the planner.
- Pre-aggregation or read models for heavy reporting paths.

**`LATERAL` + SQL functions provide reuse, not a magical "single scan."**

### 12.3. Matching indexes are needed

A candidate index for per-customer top-N lookups:

```sql
CREATE INDEX idx_sqlfn_orders_customer_latest
ON sqlfn_lab.orders (
    tenant_id, customer_id,
    ordered_at DESC, order_id DESC
);
```

This index helps retrieve a customer's latest orders quickly in descending order. Remember that extra indexes add write overhead and storage; validate against real workloads.

---

## 13. Volatility: IMMUTABLE, STABLE, and VOLATILE

PostgreSQL uses **function volatility** metadata to determine when results can be reused, how expressions optimize, and how snapshots behave.

| Attribute | Core promise | Appropriate examples |
| --- | --- | --- |
| `IMMUTABLE` | Same inputs always yield the same output under stable semantics | Pure arithmetic, pure unit conversions |
| `STABLE` | Same inputs yield the same result within a single statement; does not modify DB | Snapshot table/config reads, statement-stable functions |
| `VOLATILE` | Output can vary across calls or cause side effects; must preserve evaluation | `random()`, `clock_timestamp()`, DML writes |

**Default:** if volatility is omitted, PostgreSQL defaults to `VOLATILE`.

### 13.1. IMMUTABLE

Example:

```sql
CREATE FUNCTION sqlfn_lab.percent_of(
    p_part NUMERIC,
    p_whole NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT 100::NUMERIC
           * p_part
           / NULLIF(p_whole, 0);
$$;
```

For identical numeric inputs, the output never depends on table contents or time.

Note: if `p_whole = 0`, `NULLIF` causes the function to return NULL; never assume the output is guaranteed non-null.

### 13.2. STABLE

Example of a table-reading function:

```sql
CREATE FUNCTION sqlfn_lab.tenant_order_count(
    p_tenant_id INTEGER
)
RETURNS BIGINT
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id;
$$;
```

The output depends on table data, so it is **not IMMUTABLE**. With `STABLE`, PostgreSQL applies consistent snapshot semantics suitable for read queries.

### 13.3. VOLATILE

Example:

```sql
CREATE FUNCTION sqlfn_lab.current_wall_clock()
RETURNS TIMESTAMPTZ
LANGUAGE SQL
VOLATILE
AS $$
    SELECT clock_timestamp();
$$;
```

`clock_timestamp()` can change even within a single statement. Never label a wrapper `IMMUTABLE` or `STABLE` if callers expect fresh wall-clock readings on each evaluation.

### 13.4. CURRENT_TIMESTAMP, now(), and clock_timestamp()

In PostgreSQL:

- `CURRENT_TIMESTAMP` and `now()` reflect transaction start time, staying stable throughout a transaction.
- `statement_timestamp()` returns the start time of the current statement.
- `clock_timestamp()` reads the live wall clock and can advance between calls.

Never mark a current-time wrapper `IMMUTABLE`. For `clock_timestamp()`, `VOLATILE` is the accurate classification.

### 13.5. Never mark table reads as IMMUTABLE

Invalid promise:

```sql
-- DO NOT follow this:
-- CREATE FUNCTION current_tax_rate()
-- RETURNS numeric IMMUTABLE
-- AS $$ SELECT rate FROM tax_rates ... $$ LANGUAGE SQL;
```

If the tax table changes, identical inputs yield different results. Marking it `IMMUTABLE` allows constant folding, caching assumptions, or index corruption based on false invariants, producing wrong data and plans.

### 13.6. Volatility is the author's commitment

PostgreSQL cannot verify all side effects or dependencies inside every function and nested call, especially with dynamic behavior. Authors must classify honestly; misdeclaring volatility is far more dangerous than minor call overhead.

---

## 14. Volatility and snapshot visibility

Volatility affects not only optimization, but also how an SQL function sees database changes.

### 14.1. STABLE and IMMUTABLE

SQL statements inside these functions use the calling statement's snapshot, keeping reads consistent throughout that statement's execution.

### 14.2. VOLATILE

A `VOLATILE` function acquires a fresh snapshot for internal SQL statements under PostgreSQL's visibility rules. That is a real semantic difference from `STABLE`, not merely a planner hint.

### 14.3. Wrappers must respect inner volatility

If a wrapper calls a `VOLATILE` function, never label the wrapper `STABLE` or `IMMUTABLE` just to encourage inlining.

Example:

```sql
-- Do not mark a function relying on random() as IMMUTABLE.
SELECT random();
```

### 14.4. When is VOLATILE mandatory?

Whenever a function modifies database state, triggers side effects, or depends on per-evaluation state, `VOLATILE` is the proper classification within PostgreSQL's constraints.

### 14.5. Volatility does not make queries thread-safe or race-free

Marking a function `STABLE` or `IMMUTABLE` does not replace transaction isolation, locks, or unique constraints. It merely describes result stability and side effects to the optimizer and executor.

---

## 15. How can PostgreSQL inline functions?

**Inlining** is an optimization where the planner substitutes an eligible SQL function's expression or query body into the calling query so both optimize together.

Two categories are commonly discussed:

1. **Scalar SQL function inlining:** a scalar-returning function expands into an inline expression.
2. **Table SQL function inlining:** a set-returning function whose body is a `SELECT` expands into a subquery inside the caller.

Scalar example:

```text
SELECT amount_with_tax(amount, 8)
                 |
                 | may be inlined
                 v
SELECT ROUND(amount * (1 + 8 / 100), 2)
```

Table function example:

```text
SELECT *
FROM orders_in_period(10, from_t, to_t)
WHERE status = 'PAID'
                  |
                  | may be inlined under eligible conditions
                  v
SELECT ...
FROM orders
WHERE tenant_id = 10
  AND ordered_at >= from_t
  AND ordered_at < to_t
  AND status = 'PAID'
```

This is a **conceptual model**, not a guarantee of the exact plan or SQL rewrite PostgreSQL will produce.

### 15.1. Benefits of scalar inlining

- Eliminates per-row function-call overhead where eligible.
- Exposes the real expression to safe planner transformations.
- Enables matching against expression indexes or statistics when applicable.
- Allows constant folding when volatility permits.

### 15.2. Benefits of table-function inlining

- Allows outer predicates to be pushed down to base tables.
- Exposes base tables and indexes directly to the planner.
- Enables better join reordering and cardinality estimates.
- Avoids treating the function as an opaque black box guided only by `COST`/`ROWS`.

### 15.3. The key word: "may"

Inlining depends on numerous conditions:

- SQL-language body.
- Single vs. multiple statements.
- Return type.
- Volatility.
- `STRICT`.
- `SECURITY DEFINER` vs. `SECURITY INVOKER`.
- Function-level `SET` clauses.
- Parameter and body characteristics.
- `ORDER BY`/`LIMIT`, CTEs, side effects, and safety checks.
- PostgreSQL version and planner implementation.

Never treat "`LANGUAGE SQL` + `STABLE` = always inlined" as a law. Always **inspect the actual query plan**.

---

## 16. Scalar inlining: expression function example

Consider:

```sql
CREATE FUNCTION sqlfn_lab.plus_one(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_value + 1;
$$;
```

Query:

```sql
EXPLAIN (VERBOSE)
SELECT sqlfn_lab.plus_one(10) AS result;
```

Under compatible versions and conditions, the planner folds the call into an expression or constant rather than invoking a black-box function at runtime.

### 16.1. Constant folding does not prove every call inlines

Seeing `EXPLAIN` fold a constant argument does not prove the same function will inline in all queries—especially if the body grows complex, uses security settings, or receives volatile arguments.

### 16.2. Inlining and STRICT

`STRICT` helps in many scenarios, yet **not every `STRICT` SQL function qualifies for scalar inlining**. The planner must prove that expanding the expression preserves NULL semantics identically; some expressions fail those safety checks.

Example:

```sql
CREATE FUNCTION sqlfn_lab.maybe_zero(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
CALLED ON NULL INPUT
IMMUTABLE
AS $$
    SELECT COALESCE(p_value, 0);
$$;
```

This function intentionally omits `STRICT`. Marking it `STRICT` would change the output on NULL. A non-`STRICT` function can still be inlined when eligible; metadata and logic must agree.

### 16.3. Multi-statement scalar functions are not simple expressions

An SQL function body can contain multiple statements where permitted. Do not assume such a function can inline like a single scalar expression.

When computing one value, writing **a single expression `SELECT`** is clearer and far more likely to optimize.

---

## 17. Table-function inlining and predicate pushdown

Querying the function directly:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    ordered_at,
    amount
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 17.1. When inlined

The planner sees `sqlfn_lab.orders` directly and combines predicates:

```sql
o.tenant_id = 10
AND o.ordered_at >= ...
AND o.ordered_at < ...
AND o.status = 'PAID'
```

Making index `(tenant_id, status, ordered_at)` an immediate candidate.

### 17.2. When not inlined

The plan may show a node like:

```text
Function Scan on sqlfn_lab.orders_in_period ...
    Filter: (status = 'PAID')
```

meaning the outer query executes the function first and filters its output afterward, unable to push `status = 'PAID'` inside the body.

### 17.3. Do not treat "Function Scan" as an SQL error

`Function Scan` is a completely valid execution node. For small result sets or logic that must remain encapsulated, it can perform fine.

What matters is **actual cost and correctness**: does it meet latency targets, or is there an easier-to-optimize formulation?

### 17.4. Reading EXPLAIN to see where filters apply

Check:

- `Index Cond` on base tables.
- Whether `Filter` sits on the base table scan or on `Function Scan`.
- Actual row counts.
- Buffers hit/read.
- Total execution time and function call counts.
- Whether intermediate `Sort` or `Materialize` nodes appear.

Never look solely at `Function Scan` and conclude a query is slow; likewise, never see one `Index Scan` in a test and assume the function scales in production.

---

## 18. Factors that commonly prevent SQL function inlining

PostgreSQL's exact rules are technical and evolve across versions, yet these factors are always worth checking.

### 18.1. SECURITY DEFINER

A `SECURITY DEFINER` function runs with the owner's privileges under a strict security contract. The planner cannot inline its body into the caller's query if doing so would violate privilege boundaries.

Thus **`SECURITY DEFINER` blocks SQL function inlining**—an intentional security trade-off.

### 18.2. Function-level SET configuration

Example:

```sql
CREATE FUNCTION sqlfn_lab.plus_one_with_setting(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
SET search_path = pg_catalog, sqlfn_lab
AS $$
    SELECT p_value + 1;
$$;
```

A `SET` clause establishes a dedicated runtime setting context for the function, which prevents inlining the body into the caller's expression.

Never strip `SET search_path` from a `SECURITY DEFINER` function just to chase inlining if it is required for security.

### 18.3. Volatility and side effects

If a function is `VOLATILE` or its body contains operations unsafe for substitution, the planner must preserve exact call counts and evaluation order.

### 18.4. Multiple statements or complex structures

Multi-statement bodies do not map cleanly to a single scalar expression or simple table-function `SELECT`. Inlining becomes either restricted or impossible.

### 18.5. STRICT and NULL semantics

For scalar functions, the planner must prove that substituting the expression preserves NULL results when arguments are NULL. Some bodies fail that check even when declared `STRICT`.

For set-returning table functions, different rules apply, and declaring `STRICT` can affect inlining eligibility in its own ways.

### 18.6. Security attributes or unusual expressions

Nested set-returning expressions, volatile argument expressions, security barriers, complex return types, and constructs requiring preserved evaluation order can all block inlining.

### 18.7. The right practical workflow

Do not treat a memorized checklist as mathematical proof. Run:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT ...
FROM your_function(...);
```

and compare it against the equivalent direct query on your real data and PostgreSQL version.

---

## 19. Predicate pushdown: should filters live inside or outside the function?

Suppose a function returns **all orders in a date range** and the caller filters `PAID`:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID';
```

If the function inlines and the planner pushes the `status` predicate down into `orders`, performance can be great. If the function runs standalone, it may emit many unwanted rows before filtering.

### 19.1. A narrower function for the use case

When a workload always needs `PAID` orders, publish a dedicated function:

```sql
CREATE FUNCTION sqlfn_lab.paid_orders_in_period(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    ordered_at TIMESTAMPTZ,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
ROWS 100
AS $$
    SELECT
        o.tenant_id,
        o.order_id,
        o.ordered_at,
        o.amount
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = 'PAID'
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to;
$$;
```

Even if not inlined, the internal query already applies the `status` filter.

### 19.2. Do not create a function for every filter combination

An interface with 15 optional filters leads to an explosion of function variants. Consider:

- Parameterized SQL queries with bind variables.
- Functions accepting key stable parameters.
- Views combined with caller `WHERE` clauses.
- Dynamic SQL in the application layer or PL/pgSQL when needed.
- Dedicated read models for hot paths.

### 19.3. Result contracts matter more than brevity

Returning a broad set for callers to filter offers flexibility, yet must be measured on large tables. Returning a narrow set is faster for fixed paths, at the cost of narrower reuse.

---

## 20. Functions wrapping columns and indexes: understanding sargability

Suppose an application stores text labels and wants whitespace-trimmed, case-insensitive matching.

### 20.1. Pure normalization function

```sql
CREATE FUNCTION sqlfn_lab.normalize_label(
    p_text TEXT
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT LOWER(BTRIM(p_text));
$$;
```

Within a fixed collation and environment, `LOWER`/`BTRIM` can normalize labels. In practice, if locale, collation, or Unicode policies change, indexes and normalized values must be managed accordingly—never assume environment upgrades leave computed expression values untouched.

### 20.2. Filter expression on a column

```sql
WHERE sqlfn_lab.normalize_label(label) = 'postgresql'
```

If the table only has a B-tree index **on the raw `label` column**, that index cannot be used directly to match `LOWER(BTRIM(label))`.

### 20.3. Matching expression index

Extended lab table example:

```sql
CREATE TABLE sqlfn_lab.catalog_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO sqlfn_lab.catalog_items (label)
VALUES (' PostgreSQL '), ('postgresql'), ('JAVA'), (' SQL ');

CREATE INDEX idx_catalog_normalized_label
ON sqlfn_lab.catalog_items (
    sqlfn_lab.normalize_label(label)
);
```

Query:

```sql
SELECT item_id, label
FROM sqlfn_lab.catalog_items
WHERE sqlfn_lab.normalize_label(label) = 'postgresql';
```

now has a matching expression index available to the planner.

### 20.4. Inlining can help expression matching

If the planner inlines `normalize_label(label)` to `LOWER(BTRIM(label))`, matching against expressions can work seamlessly. Still, never depend blindly on inlining when designing a critical index.

If both the index definition and the `WHERE` clause invoke the **same function** with an explicit signature, the planner has a consistent indexed expression to match, subject to data statistics and metadata.

### 20.5. Marking IMMUTABLE for indexes requires truth

PostgreSQL requires expression indexes to use expressions and functions with true immutability. Never fake `IMMUTABLE` on a function reading tables or clocks just so `CREATE INDEX` succeeds.

**Corrupt indexes from fake metadata are a correctness hazard**, not merely poor performance.

---

## 21. Functions on timestamp columns and losing range indexes

A common pattern:

```sql
CREATE FUNCTION sqlfn_lab.utc_day(
    p_time TIMESTAMPTZ
)
RETURNS DATE
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT (p_time AT TIME ZONE 'UTC')::DATE;
$$;
```

Used for grouping by UTC day:

```sql
SELECT sqlfn_lab.utc_day(ordered_at) AS day_utc,
       COUNT(*)
FROM sqlfn_lab.orders
GROUP BY day_utc
ORDER BY day_utc;
```

However, filtering by date with:

```sql
WHERE sqlfn_lab.utc_day(ordered_at) = DATE '2026-02-01'
```

prevents a regular B-tree index on `ordered_at` from performing a range scan as expected, because the predicate wraps the column in a function.

### 21.1. Write range predicates directly on timestamps

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
```

Half-open intervals match B-tree indexes on raw timestamps cleanly and enable partition pruning on time-partitioned tables.

### 21.2. Display formatting differs from search predicates

`utc_day` is handy in `SELECT` and `GROUP BY`, yet that does not mean it belongs in `WHERE`. **Separate display expressions from search predicates** when access paths rely on B-tree ranges.

### 21.3. Expression indexes are an alternative, not always the best default

If queries overwhelmingly filter on the normalized day, an expression index on `utc_day(ordered_at)` can work. Weigh storage and write costs and verify timezone semantics.

---

## 22. IMMUTABLE functions and indexes/generated columns: advanced warning

Several PostgreSQL features rely strictly on immutability:

- Expression indexes.
- Certain index predicates and check constraints.
- Stored generated columns where supported.
- Constant folding and plan caching assumptions.

### 22.1. Misdeclaring causes unpredictable results

Consider a function reading an exchange rate from a table:

```sql
-- Counter-example: do not execute.
--
-- CREATE FUNCTION convert_currency(p_amount numeric)
-- RETURNS numeric
-- LANGUAGE SQL IMMUTABLE
-- AS $$
--   SELECT p_amount * (
--       SELECT current_rate FROM rates LIMIT 1
--   );
-- $$;
```

Rates change over time, so `IMMUTABLE` is false. PostgreSQL may bake stale assumptions into cached plans or stored index entries, corrupting results.

### 22.2. Immutability covers every dependency

Do not just glance at `round` or `lower` in the SQL body. If results depend on timezone settings, collations, lookup tables, session state, or nested functions with higher volatility, audit the full dependency chain.

### 22.3. Never "optimize" by lying to the planner

A benchmark with a falsely labeled `IMMUTABLE` function might appear faster while silently returning stale or wrong values whenever data or configuration changes.

Optimization must preserve **exact semantic equivalence**, never trick the planner.

---

## 23. PARALLEL SAFE, RESTRICTED, and UNSAFE

PostgreSQL tracks parallel query execution safety in function metadata.

| Attribute | Practical meaning |
| --- | --- |
| `PARALLEL SAFE` | Author certifies the function can run inside parallel workers under PostgreSQL rules |
| `PARALLEL RESTRICTED` | Function must run only in the leader process in eligible plans |
| `PARALLEL UNSAFE` | Function is unsafe for parallelism; presence can disable parallel plans |

**Default:** user-defined functions default to `PARALLEL UNSAFE` unless explicitly declared otherwise.

### 23.1. Pure arithmetic example

```sql
CREATE FUNCTION sqlfn_lab.double_amount(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_amount * 2;
$$;
```

Numeric multiplication neither reads nor mutates session or database state, so `PARALLEL SAFE` is completely valid.

### 23.2. Never assign PARALLEL SAFE carelessly

If a function modifies data, accesses worker-unsafe session state, controls transactions, advances sequences, uses temporary tables, or calls parallel-unsafe functions, marking it `SAFE` is wrong.

Authors must understand **every operation** and restriction for their PostgreSQL version, not just whether the body "looks like a single SELECT."

### 23.3. Parallel metadata does not force parallel execution

Even when a function is `PARALLEL SAFE`, the planner may still choose a serial plan when:

- The table is small.
- Worker startup costs outweigh gains.
- Filters are highly selective.
- Other query nodes or aggregates prevent parallelization.
- System configuration or concurrency limits apply.

### 23.4. Consider overall concurrency

A single query running faster with four workers does not mean 30 concurrent queries each spawning four workers will scale better. Measure CPU, I/O, and aggregate throughput under load.

---

## 24. COST and ROWS: impact on the cost model

PostgreSQL lets you specify:

```sql
COST 100
ROWS 1000
```

in function definitions where applicable.

### 24.1. COST estimates per-call expense

`COST` is a **relative planner cost unit**, not milliseconds or exact CPU time.

For scalar functions, `COST` scales estimated per-invocation cost. For set-returning functions, PostgreSQL's cost model scales cost across estimated returned rows; never interpret `COST 100` literally as "takes 100 ms per row."

### 24.2. ROWS applies only to set-returning functions

A function declaring:

```sql
RETURNS TABLE (...)
ROWS 100
```

uses `ROWS` to communicate expected output cardinality. It never truncates or validates emitted rows.

### 24.3. Why bad estimates hurt query plans

If a function actually emits 100,000 rows while declaring `ROWS 10`, the planner may choose an inappropriate Nested Loop or bad join order—especially when the function is not inlined and the planner cannot inspect underlying tables.

### 24.4. Adjust ROWS only from measured data

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM sqlfn_lab.orders_in_period(...);
```

and compare estimated `rows` against `actual rows`. If estimates deviate wildly on repeated workloads, adjust metadata or rewrite the query—never tune `ROWS` based on a single outlier tenant.

### 24.5. Inlining reduces the direct role of COST/ROWS

When a function is inlined, the planner costs the underlying tables and statistics directly rather than treating the function as a black box. Thus tweaking `COST`/`ROWS` may have zero effect on inlined queries.

---

## 25. Multi-statement SQL functions: possible, with limits

SQL-language functions are not strictly limited to one `SELECT` in all forms. Inside string-bodied functions, PostgreSQL supports multiple valid SQL statements, returning the result of the final statement per the return contract.

Illustrative example:

```sql
CREATE FUNCTION sqlfn_lab.two_step_value(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value;
    SELECT p_value + 2;
$$;
```

The scalar result comes from the final statement, provided statements and types match.

### 25.1. Why discourage this for simple calculations?

The function above simplifies directly to:

```sql
SELECT p_value + 2;
```

Unnecessary multi-statement bodies hurt readability and prevent inlining.

### 25.2. SQL functions lack PL/pgSQL variables and control flow

If you need temporary variables, `IF/ELSE`, loops, or exception handling, use PL/pgSQL. Chaining `SELECT` statements in an SQL function is not a substitute for procedural control flow.

### 25.3. DML inside functions

SQL-language functions can execute eligible DML statements, provided they are marked `VOLATILE` with appropriate privileges. Never label a state-modifying function `IMMUTABLE` or `STABLE` to chase optimizations.

### 25.4. Functions cannot independently COMMIT/ROLLBACK

Functions run inside the caller's transaction. When transaction control is required in eligible contexts, study `CREATE PROCEDURE`/`CALL` and PostgreSQL's restrictions rather than trying to put `COMMIT` inside a regular SQL function.

---

## 26. SQL-standard function bodies: RETURN and BEGIN ATOMIC

Alongside:

```sql
LANGUAGE SQL
AS $$ SELECT ...; $$
```

PostgreSQL versions supporting SQL-standard function bodies allow syntax such as:

```sql
CREATE FUNCTION sqlfn_lab.triple_integer(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
RETURN p_value * 3;
```

Block form example:

```sql
CREATE FUNCTION sqlfn_lab.add_five(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
BEGIN ATOMIC
    SELECT p_value + 5;
END;
```

### 26.1. Do not confuse BEGIN ATOMIC with BEGIN transaction

Here `BEGIN ATOMIC ... END` is **SQL-standard function body syntax** in supported versions, not an application-controlled `BEGIN; COMMIT;` transaction.

### 26.2. Differences in parse-time analysis

With SQL-standard bodies, PostgreSQL parses and resolves object references at definition time, recording catalog dependencies explicitly.

With string-literal bodies, parse/check timing and dependency tracking differ depending on body form, `check_function_bodies` settings, and context.

### 26.3. Do not copy newer syntax to older servers

SQL-standard function bodies were introduced in PostgreSQL 14. On older servers, use `AS $$...$$` and verify compatibility.

### 26.4. Body syntax does not bypass security rules

Syntax choice does not automatically make a function safe or parallel-safe. Volatility, permissions, and query design rules remain unchanged.

---

## 27. Why can scalar functions in WHERE be slow?

Example:

```sql
SELECT order_id
FROM sqlfn_lab.orders
WHERE sqlfn_lab.amount_with_tax(amount, 8) > 100;
```

When a predicate transforms `amount` and scans many rows, the function may evaluate across huge numbers of tuples. Without a matching index, PostgreSQL may perform a large scan.

### 27.1. Can pure math predicates be inverted automatically?

Mathematically:

```text
ROUND(amount * 1.08, 2) > 100
```

is not identically equivalent to an arbitrary algebraic rewrite once rounding, numeric types, overflow, and precision policies are factored in. Never blindly rewrite it as:

```sql
amount > 100 / 1.08
```

without proving boundary equivalence for every input value.

### 27.2. Prefer sargable predicates directly when possible

If the query actually wants `amount >= 100`, write directly:

```sql
WHERE amount >= 100
```

With a B-tree index on `amount` and sufficient selectivity, the planner can use an index scan immediately.

### 27.3. Expression indexes for matching workloads

If filtering on `amount_with_tax(amount,8)` is frequent and the expression is genuinely immutable, an expression index may help. Remember every index adds write and storage overhead and only serves its exact expression pattern.

### 27.4. Never turn cheap operations into expensive per-row calls

Simple expressions can inline, whereas functions executing subqueries or heavy work per row multiply costs rapidly. Across 1 million rows, even tiny per-row overhead adds up dramatically.

---

## 28. Scalar SQL function vs. direct expression: benchmark

Compare these two queries:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    sqlfn_lab.amount_with_tax(amount, 8)
)
FROM sqlfn_lab.orders
WHERE tenant_id = 10;
```

and:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    ROUND(amount * (1 + 8::NUMERIC / 100), 2)
)
FROM sqlfn_lab.orders
WHERE tenant_id = 10;
```

### 28.1. Compare identical semantics

Both queries must share:

- Identical `NUMERIC` types.
- Identical `WHERE` predicates.
- Identical rounding logic.
- Identical NULL handling.
- Identical data snapshot during testing.

Comparing `FLOAT` against `NUMERIC` invalidates any conclusions about inlining overhead.

### 28.2. Small datasets introduce noise

60,000 orders suffices for learning `EXPLAIN`, not for representing multi-hundred-million-row workloads. Warm vs. cold caches, CPU variance, concurrent load, and plan differences all affect timings.

### 28.3. What to look for in VERBOSE

`EXPLAIN (VERBOSE)` prints output expressions. Scalar inlining can often be spotted when the output target list shows the expanded arithmetic expression instead of the function name, though there is no guaranteed `"inlining=true"` flag in `EXPLAIN`.

Inspect both plans—costs, nodes, and timings—and verify on your exact PostgreSQL version and environment.

### 28.4. Never draw conclusions from a single run

Reliable benchmarking requires:

1. Warm-up runs.
2. Multiple iterations.
3. Stable measurements.
4. Representative data distributions.
5. Reading `Planning Time`, `Execution Time`, and `BUFFERS`.
6. Concurrency testing for hot endpoints.

---

## 29. Table function vs. direct SQL query: benchmark

Function query:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID';
```

Equivalent direct query:

```sql
SELECT
    o.tenant_id,
    o.order_id,
    o.ordered_at,
    o.status,
    o.amount
FROM sqlfn_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND o.ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND o.status = 'PAID';
```

### 29.1. Plans may converge

When the function inlines and the optimizer sees the underlying predicates, both queries often produce nearly identical plans. Still, metadata, parameter binding, or query structure can produce differences.

### 29.2. If Function Scan emits many rows before filtering

That signals the function was not folded into the outer plan as hoped. Options include:

- Moving selective filters inside the parameterized function body.
- Simplifying the function body.
- Checking volatility, `STRICT`, `SET`, and security attributes.
- Using direct SQL on hot paths.
- Retaining the function abstraction only where benefits outweigh overhead.

### 29.3. Never remove SECURITY DEFINER just for speed

If a function enforces privilege boundaries via `SECURITY DEFINER`, stripping it to enable inlining breaks authorization. Optimizations must **preserve security semantics**.

### 29.4. Check ROWS estimates

If `Function Scan` predicts `rows=100` from the hint while `actual rows=5000`, join estimates suffer. Empirical measurements tell you whether to tune `ROWS` or reshape the query.

---

## 30. Security: SECURITY INVOKER and SECURITY DEFINER

Functions run with either the caller's privileges or the owner's privileges based on declaration.

### 30.1. SECURITY INVOKER — the default

```sql
CREATE FUNCTION sqlfn_lab.identity_integer(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
SECURITY INVOKER
AS $$
    SELECT p_value;
$$;
```

With `SECURITY INVOKER`, permissions on underlying tables and objects are checked against the caller's role.

### 30.2. SECURITY DEFINER

```sql
CREATE FUNCTION sqlfn_lab.tenant_order_count_definer(
    p_tenant_id INTEGER
)
RETURNS BIGINT
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sqlfn_lab, pg_temp
AS $body$
    SELECT COUNT(*)
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id;
$body$;
```

This is a syntax example only; **never grant EXECUTE to untrusted callers** just because a function returns a `COUNT`. Without trusted tenant verification, callers can pass arbitrary `tenant_id` values and infer data belonging to other tenants.

### 30.3. Why does SECURITY DEFINER restrict inlining?

Inlining must never collapse owner privilege boundaries into the caller's query. Switching between invoker and definer changes both **security semantics and optimization behavior**.

### 30.4. search_path inside definer functions

In elevated-privilege functions, unqualified object names combined with a `search_path` containing schemas writable by untrusted users risk object-resolution hijacking.

Core rules:

- Schema-qualify all critical tables and functions.
- Pin `SET search_path` strictly to trusted schemas, placing `pg_temp` appropriately per security documentation.
- Never place schemas where untrusted users hold `CREATE` ahead of trusted schemas.
- Never let callers alter search paths to redirect executed objects.
- Review how PostgreSQL resolves function/operator names when overloads exist.

### 30.5. Security–performance trade-off

When a function requires `SECURITY DEFINER` for access control, **security is the primary requirement**. If non-inlining hurts speed, optimize the inner query, add indexes, or reduce invocation frequency—never weaken privilege boundaries for speed.

---

## 31. EXECUTE privilege and PUBLIC defaults

In PostgreSQL, functions carry an ACL and an `EXECUTE` privilege.

### 31.1. Testing privilege setup in the lab

Illustrative example when role creation is permitted:

```sql
CREATE ROLE sqlfn_lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA sqlfn_lab
TO sqlfn_lab_reader;

GRANT EXECUTE ON FUNCTION sqlfn_lab.amount_with_tax(
    NUMERIC, NUMERIC
)
TO sqlfn_lab_reader;
```

### 31.2. Newly created functions often grant EXECUTE to PUBLIC by default

In many PostgreSQL setups, default privileges grant `EXECUTE` on newly created functions to `PUBLIC`. This is critical for `SECURITY DEFINER` routines.

To restrict a sensitive function to specific roles:

```sql
REVOKE ALL ON FUNCTION
    sqlfn_lab.tenant_order_count_definer(INTEGER)
FROM PUBLIC;
```

and `GRANT` to authorized roles only. For sensitive deployments, execute `CREATE`/`REVOKE`/`GRANT` inside a single transaction to eliminate exposure windows.

### 31.3. Schema USAGE and object privileges

A role needs both schema `USAGE` and function `EXECUTE` to resolve and call a function. Holding `EXECUTE` on a `SECURITY INVOKER` function does not grant `SELECT` on underlying tables.

### 31.4. RLS and tenant identity

If a function takes `p_tenant_id` directly from callers who could supply arbitrary IDs, the function itself is not a security boundary. Especially with `SECURITY DEFINER`, enforce trusted identity checks and policies so cross-tenant data cannot leak.

### 31.5. Test with actual application roles

Running successfully as a superuser proves nothing about how production roles read/write tables or interact with RLS. Test across realistic roles, tenants, and call paths.

---

## 32. SQL functions, RLS, and table privileges

A function reading `orders` interacts with Row-Level Security according to invoker/definer and owner semantics.

### 32.1. SECURITY INVOKER

With `SECURITY INVOKER`, base table privileges and RLS policies evaluate as the caller, which fits when each role should see only its authorized rows.

### 32.2. SECURITY DEFINER

With `SECURITY DEFINER`, the function owner's privileges apply—affecting RLS especially if the owner is a table owner or holds `BYPASSRLS`. Always test thoroughly.

### 32.3. Trusted tenant context

A pattern like:

```sql
WHERE tenant_id = current_setting('app.tenant_id')::INTEGER
```

is safe only if the tenant setting is configured through a trusted channel, callers cannot spoof it, and connection pools reset session state cleanly between requests.

Never trust an arbitrary session setting as authorization proof if untrusted SQL clients can run `SET` themselves.

### 32.4. Granting EXECUTE is not equivalent to table privilege scoping

A `SECURITY DEFINER` function can open a new access path to underlying tables. Treat every function as part of your **permission surface**, not mere utility code.

---

## 33. LEAKPROOF and security_barrier: do not enable casually

PostgreSQL uses `LEAKPROOF` metadata on certain built-in functions/operators to indicate whether the optimizer can safely push expressions across security barriers or RLS boundaries.

**Never mark user-written functions `LEAKPROOF`** to force predicate pushdown unless strict security guarantees are proven. Setting `LEAKPROOF` requires superuser privileges and guarantees the function cannot leak information via error messages or side effects.

### 33.1. Why does this relate to optimization?

Around security-barrier views or RLS, PostgreSQL restricts pushing down non-leakproof predicates to prevent side-channel leaks. A non-leakproof function may stay outside the barrier even if pushing it down looks faster.

### 33.2. Never sacrifice security to fix a query plan

If queries over sensitive data are slow, prefer:

- Indexes on safe filter columns.
- Clean policy and filter design.
- Authorized summary tables.
- Reducing scanned data volume.
- Benchmarking under real application roles.

Never alter `LEAKPROOF` or security attributes just to "let the optimizer see everything."

---

## 34. Function overloading and schema names

PostgreSQL distinguishes functions by name and input argument types, enabling overloading.

### 34.1. Overload example

```sql
CREATE FUNCTION sqlfn_lab.double_value(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value * 2;
$$;

CREATE FUNCTION sqlfn_lab.double_value(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value * 2;
$$;
```

Explicitly typed calls:

```sql
SELECT
    sqlfn_lab.double_value(5::INTEGER),
    sqlfn_lab.double_value(5.5::NUMERIC);
```

### 34.2. Why can implicit casts cause confusion?

Untyped literals or default arguments force PostgreSQL through candidate resolution rules, risking ambiguous-call errors or unexpected overload choices.

For long-lived APIs, minimize overloads and cast explicitly when multiple types could match.

### 34.3. Schema qualification

```sql
SELECT sqlfn_lab.double_value(5);
```

pins the target schema. In security-sensitive code especially, never rely on a caller's mutable `search_path` to resolve same-named functions.

### 34.4. Named arguments are part of the contract

If clients invoke `p_value => ...`, renaming the parameter is a breaking change even when types stay identical. Keep parameter names stable and version public APIs cleanly.

---

## 35. CREATE OR REPLACE FUNCTION and signature changes

Any function with active consumers is a database API.

### 35.1. Replacing the body with a compatible signature

```sql
CREATE OR REPLACE FUNCTION sqlfn_lab.add_integers(
    p_a INTEGER,
    p_b INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_a + p_b;
$$;
```

This updates the definition in place when signature and return type remain compatible per PostgreSQL rules.

### 35.2. Cannot arbitrarily change RETURNS

PostgreSQL forbids `CREATE OR REPLACE FUNCTION` from arbitrarily altering an existing function's return type. Use versioned names or controlled `DROP`/`CREATE` migrations handling dependencies.

### 35.3. Adding parameters can create a new overload

Changing:

```sql
f(p_tenant_id INTEGER)
```

to:

```sql
f(p_tenant_id INTEGER, p_from TIMESTAMPTZ)
```

creates a **distinct function identity** in PostgreSQL rather than replacing the old body. Consequences:

- Two overloads coexist.
- `EXECUTE` grants diverge.
- Legacy callers keep hitting the old version.
- Calls with `DEFAULT` or implicit casts may turn ambiguous.

### 35.4. DROP FUNCTION requires exact input signatures

```sql
DROP FUNCTION sqlfn_lab.double_value(INTEGER);
```

drops the `INTEGER` overload while leaving `NUMERIC` intact. Always audit dependencies and privileges before dropping in production.

### 35.5. Never use CASCADE out of habit

`DROP FUNCTION ... CASCADE` deletes dependent views, functions, and constraints automatically. Always create a migration plan, check consumers, and prepare rollback steps.

---

## 36. SQL functions and dependency management

A function can reference tables, types, operators, and other functions.

### 36.1. Viewing function definitions

```sql
SELECT pg_get_functiondef(
    'sqlfn_lab.orders_in_period(
       INTEGER, TIMESTAMPTZ, TIMESTAMPTZ
     )'::REGPROCEDURE
);
```

With schema-qualified overloads, `REGPROCEDURE` identifies the exact signature cleanly.

### 36.2. Querying function catalog metadata

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    p.provolatile,
    p.proparallel,
    p.prosecdef
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sqlfn_lab'
ORDER BY p.proname, identity_arguments;
```

Metadata codes:

- `provolatile`: `i` immutable, `s` stable, `v` volatile.
- `proparallel`: `s` safe, `r` restricted, `u` unsafe.
- `prosecdef`: `SECURITY DEFINER` flag.

### 36.3. \df in psql

In `psql`:

```text
\df sqlfn_lab.*
\df+ sqlfn_lab.orders_in_period
```

These are `psql` meta-commands, not SQL statements for JDBC.

### 36.4. Dependency differences across body forms

SQL-standard bodies are parsed and tracked in catalog dependencies at `CREATE` time more thoroughly than string-literal bodies. Never assume every string-bodied function blocks dropping referenced tables the way a view does.

During migrations, test dependencies explicitly and remember `pg_depend` cannot see external application consumers.

---

## 37. Parameterized queries and prepared plans

SQL functions are often called with bound parameters:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    $1::INTEGER,
    $2::TIMESTAMPTZ,
    $3::TIMESTAMPTZ
);
```

PostgreSQL switches between **custom plans** and **generic plans** under prepared statement rules.

### 37.1. Parameter values affect selectivity

If Tenant A has 100 orders and Tenant B has 10 million, the same query needs different access paths. An averaged generic plan may underperform for skewed tenants.

### 37.2. Do not blame every bad plan on the function

Distinguish between:

- Non-inlined functions.
- Missing or suboptimal indexes.
- Stale or missing table statistics.
- Prepared statement generic plans.
- Non-selective time ranges.
- Parameterized partition pruning.

Multiple factors often combine.

### 37.3. Run EXPLAIN with realistic parameter sets

Benchmark production-like workloads across representative parameter combinations: small tenants, huge tenants, narrow ranges, wide ranges. Never declare an API fast after testing a single input value.

---

## 38. Calling SQL functions from Java/JDBC

Because functions are standard PostgreSQL objects, Java calls them via `PreparedStatement`.

### 38.1. Calling a scalar function

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("8.0");

String sql = """
    SELECT sqlfn_lab.amount_with_tax(?, ?) AS total
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setBigDecimal(2, rate);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal("total");
            // Process result.
        }
    }
}
```

### 38.2. Calling a table function

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;

String sql = """
    SELECT order_id, ordered_at, status, amount
    FROM sqlfn_lab.orders_in_period(?, ?, ?)
    WHERE status = 'PAID'
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 100
    """;

Instant from = Instant.parse("2026-02-01T00:00:00Z");
Instant to = Instant.parse("2026-03-01T00:00:00Z");

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 10);
    ps.setTimestamp(2, Timestamp.from(from));
    ps.setTimestamp(3, Timestamp.from(to));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Read remaining columns.
        }
    }
}
```

### 38.3. Passing tenant_id safely

`tenant_id = 10` above must come from authenticated application authorization, never untrusted client input. `PreparedStatement` prevents SQL injection via parameter binding—**it does not authorize tenant access**.

### 38.4. Avoid concatenating input into SQL strings

Never write:

```java
// Do not use.
String sql = "SELECT * FROM sqlfn_lab.orders_in_period("
        + userTenantId + ", '" + userFrom + "', '" + userTo + "')";
```

Parameter binding preserves types and prevents injection.

### 38.5. Verify timestamp types

The function expects `TIMESTAMPTZ`; standardize on UTC instants or explicit timezone contracts in Java. Never pass local date strings assuming they share the same meaning as UTC.

---

## 39. Typical optimization scenarios

### Scenario A — Scalar function summing 10 million rows

**Context:** `amount_with_tax(amount,8)` is called inside `SUM` over a huge table.

Investigate:

1. Is the function genuinely pure math with accurate volatility?
2. Does its body contain a single simple `SELECT` expression?
3. Do any attributes block inlining?
4. Does `EXPLAIN` show the expanded expression?
5. How many rows must the query still scan?
6. Can filtering or pre-aggregation occur earlier at a better grain?
7. Compare against the direct expression over the same snapshot.

Never bump `COST` or rewrite to PL/pgSQL without empirical evidence.

### Scenario B — Table function scanning everything before outer filtering

**Context:** Consumers call a function returning an entire year's orders and apply tenant/status/time filters outside.

Investigate:

1. Check `Function Scan` and `Rows Removed by Filter`.
2. Verify whether table-function inlining occurred.
3. If not inlined, push selective filters inside the parameterized body.
4. Add base-table indexes matching actual filters.
5. Re-measure buffers and actual rows.
6. Preserve all tenant and permission constraints.

### Scenario C — Author marked a table-reading function IMMUTABLE

**Context:** A function returning current exchange rates serves stale outputs after table updates.

This is a **volatility contract bug**, not a "random cache glitch." Fix the volatility metadata and audit any dependent indexes, generated columns, or cached plans.

### Scenario D — Slow SECURITY DEFINER function

**Context:** A privileged function cannot inline and is invoked repeatedly across many rows.

Never strip `SECURITY DEFINER` arbitrarily. Instead:

- Reduce invocation count via set-based queries.
- Add supporting indexes inside the underlying query.
- Compute results once in a secure query when contracts allow.
- Expose dedicated read models scoped by role.
- Tune the body, `COST`/`ROWS`, and inspect `EXPLAIN`.

### Scenario E — Per-customer LATERAL function creating a bottleneck

**Context:** 1 million customers, each calling a top-3 orders function.

Compare against a window function / deduplication query backed by `(tenant_id,customer_id,ordered_at DESC)`. The optimal plan depends on customer selectivity and order distribution; no single pattern wins universally.

---

## 40. Common mistakes and misconceptions

| Misconception | Reality |
| --- | --- |
| "LANGUAGE SQL always inlines." | Inlining occurs only when eligible and chosen by the planner |
| "SQL functions are just text macros." | Functions have metadata, privileges, return types, and runtime semantics |
| "PL/pgSQL and SQL optimize identically." | SQL functions have dedicated inlining opportunities |
| "Functions are always faster than direct expressions." | Benchmark first; call overhead may apply |
| "IMMUTABLE is just a speedup hint." | It is a strict contract governing correctness, plans, and indexes |
| "Reading tables with IMMUTABLE is harmless." | Results become stale or wrong when table data changes |
| "STABLE means data stays fixed all day." | It governs statement/snapshot semantics, not a cache TTL |
| "VOLATILE is only for random()." | Also covers side effects, DB writes, and mutable real-time reads |
| "STRICT only affects speed." | Changes behavior on NULL; skips executing the body |
| "Passing NULL triggers DEFAULT." | DEFAULT applies only when omitted; NULL is an explicit value |
| "COST is measured in milliseconds." | It is a relative planner cost unit |
| "ROWS 100 caps output at 100 rows." | It is strictly a planner estimate |
| "PARALLEL SAFE forces parallel execution." | The planner weighs many additional criteria |
| "Functions default to PARALLEL SAFE." | User functions default to `PARALLEL UNSAFE` |
| "RETURNS TABLE auto-indexes results." | Table functions neither materialize persistent tables nor indexes |
| "Function Scan means PostgreSQL failed." | It is a valid execution path, sometimes unavoidable |
| "No Function Scan guarantees inlining." | Inspect the full plan and expanded expressions carefully |
| "Outer WHERE predicates always push down." | Depends on inlining and query structure |
| "SECURITY DEFINER is just a shortcut for GRANT." | Changes execution privileges; critical security boundary |
| "Removing SET search_path speeds things up safely." | Opens name-resolution hijacking risks |
| "Invoker can read tables without SELECT." | Callers still need base-table privileges |
| "EXECUTE alone enforces tenant isolation." | Identity, authorization, and RLS are still required |
| "Naming a function calculate_revenue makes reports accurate." | Metrics, sources, and timezones must be defined accurately |
| "ORDER BY inside a function guarantees outer order." | Callers must specify outer `ORDER BY` when order matters |
| "RETURNS SETOF implies LIMIT." | No; `SETOF` simply means zero or more rows |
| "SQL functions can COMMIT arbitrarily." | Functions cannot manage transactions like procedures |
| "BEGIN ATOMIC opens a transaction." | It is SQL-standard function body syntax |
| "CREATE OR REPLACE freely alters RETURNS." | Changing return types is restricted |
| "Adding a parameter always replaces the old function." | It creates a new overload instead |
| "Parameter names don't affect clients." | Named-argument callers can break |
| "Editing the SQL body fixes bad volatility on an index." | Indexes, rebuilds, and plans may need repair |
| "Functions on timestamp columns still use raw range indexes." | Wrapping columns blocks raw B-tree range scans |
| "Every expression index is cheap." | Adds write, storage, and maintenance costs |
| "Fast on 10 lab rows means fast in production." | Data scale, cache state, and concurrency differ |
| "Having an index forces the planner to use it." | Sequential scans can be cheaper |
| "Changing COST/ROWS replaces table statistics." | Hints are only one input to the cost model |
| "Views and table functions are identical." | Functions take parameters and follow separate metadata/rules |
| "CTEs always beat SQL functions." | CTEs are statement-scoped with different trade-offs |
| "Dynamic SQL works in LANGUAGE SQL like PL/pgSQL." | Requires procedural languages/mechanisms for dynamic SQL |
| "Succeeding as superuser proves permissions work." | Always test as actual application roles |
| "Inlining fixes JOIN fan-out bugs." | Broken join logic stays broken |
| "SET search_path in SECURITY DEFINER doesn't impact optimization." | It blocks inlining, yet remains essential for security |
| "Any function works anywhere in SQL." | Scalar and set-returning functions have distinct shapes and limits |

---

## 41. Practice exercises

### Exercise 1 — Simple scalar function

Create `add_integers(integer,integer) RETURNS integer` using `LANGUAGE SQL`. Call it with two positive numbers and a negative number.

### Exercise 2 — Named parameters

Rewrite the body using `p_a` and `p_b`, then rewrite using `$1` and `$2`. Why are parameter names easier to maintain?

### Exercise 3 — IMMUTABLE and arithmetic

Create a function computing `p_amount * p_multiplier`. Explain when `IMMUTABLE` and `PARALLEL SAFE` are valid.

### Exercise 4 — NULL/STRICT

Create two functions: one `STRICT` and one `CALLED ON NULL INPUT` with `COALESCE`. Call both with NULL and explain the difference.

### Exercise 5 — DEFAULT

Create a function with a 10% default tax parameter. Compare omitting the argument versus passing explicit NULL.

### Exercise 6 — Named arguments

Call a function with named arguments `p_rate => 8, p_amount => 100`. Why can renaming parameters break APIs?

### Exercise 7 — Table-returning function

Create `orders_in_period` using `RETURNS TABLE` with three parameters (tenant, from, to) filtering on a half-open interval.

### Exercise 8 — Return types

Create a per-tenant aggregation function returning `COUNT` and `SUM`. Why does `COUNT(*)` match `BIGINT` while `SUM(NUMERIC)` matches `NUMERIC`?

### Exercise 9 — RETURNS SETOF

Write a function returning `order_id` values for a tenant. Compare row counts against a scalar `BIGINT` function.

### Exercise 10 — ROWS does not truncate

Set `ROWS 5` on a set-returning function. Query a time range containing hundreds of orders. Why doesn't the function stop at 5 rows?

### Exercise 11 — Output ordering

Create a function returning orders within a date range. Why do callers still need `ORDER BY ordered_at DESC, order_id DESC` when paginating?

### Exercise 12 — Semantic LIMIT

Design a function returning top-3 order IDs for a customer. Why does `LIMIT` inside the function alter semantics rather than merely speeding up execution?

### Exercise 13 — LATERAL

`LEFT JOIN LATERAL` a function fetching the 3 latest orders per customer over a small customer set. Why does `LEFT JOIN` retain customers with zero orders?

### Exercise 14 — Correlated function calls

Explain why a `LATERAL` function running per outer row becomes expensive across 1 million customers.

### Exercise 15 — STABLE table reads

Create `tenant_order_count` reading `orders`. Why is `IMMUTABLE` a false promise when orders can be inserted or deleted?

### Exercise 16 — VOLATILE and clocks

Write a wrapper calling `clock_timestamp()`. Why must it not be marked `STABLE` or `IMMUTABLE` if live wall-clock readings are required?

### Exercise 17 — CURRENT_TIMESTAMP vs. clock_timestamp

Compare both timestamps inside a multi-statement transaction. Explain their semantics and proper volatility classifications.

### Exercise 18 — Catalog volatility codes

Query `pg_proc` to inspect `i/s/v` flags for all functions created so far. Check whether any function omitted volatility and defaulted to `VOLATILE`.

### Exercise 19 — Scalar inlining

Run `EXPLAIN (VERBOSE) SELECT plus_one(10)`. Predict what the optimizer can do and explain why this doesn't prove every call will inline.

### Exercise 20 — Table-function inlining

Compare `EXPLAIN` of `orders_in_period(...) WHERE status='PAID'` with the equivalent direct query. Observe whether you get `Function Scan` or a base table scan.

### Exercise 21 — Predicate pushdown

Write two variants: one filtering only tenant/date, and another also filtering `status = 'PAID'`. When inlining fails, how does pushing the filter inside reduce wasted row reads?

### Exercise 22 — SECURITY DEFINER and optimization

In a lab where you have sufficient privileges, create a `SECURITY DEFINER` function, check `EXPLAIN`, and explain why privilege boundaries restrict inlining.

### Exercise 23 — SET search_path

Create a function with `SET search_path`. Why does `SET` prevent inlining, and why shouldn't you remove it from `SECURITY DEFINER` functions arbitrarily?

### Exercise 24 — Expression indexes

Create `normalize_label(TEXT)` and an expression index on that function; inspect `EXPLAIN` for a matching `WHERE`. Why doesn't a regular index on the raw column accelerate `LOWER`/`BTRIM`?

### Exercise 25 — Date filters

Write `utc_day(timestamptz)` and compare `WHERE utc_day(ordered_at)=date` against a half-open range on `ordered_at`. When is the range predicate better served by a B-tree index?

### Exercise 26 — Fake IMMUTABLE and indexes

Suppose a function reads `tax_rates` yet was marked `IMMUTABLE` to build an index. Describe the risks once rates change and which objects must be audited.

### Exercise 27 — PARALLEL SAFE

Write a pure arithmetic `PARALLEL SAFE` function. Why might the planner still choose a serial plan on a small table?

### Exercise 28 — PARALLEL UNSAFE

Should a function updating a log table on every call be marked `PARALLEL SAFE`? Why is misdeclaring it dangerous?

### Exercise 29 — COST/ROWS

A `RETURNS TABLE` function actually returns 100,000 rows while declaring `ROWS 10`. How can this distort join estimates?

### Exercise 30 — Volatility and empty results

What does `daily_paid_order_value` with `GROUP BY` return if a month has zero PAID orders? Compare with a scalar `COUNT(*)` query without `GROUP BY`.

### Exercise 31 — SQL-standard bodies

Write two equivalent functions: `AS $$ SELECT ... $$` and `LANGUAGE SQL RETURN expression`. State the minimum PostgreSQL version for SQL-standard bodies.

### Exercise 32 — BEGIN ATOMIC

Create an SQL-standard function using `BEGIN ATOMIC SELECT ...; END`. Why does this not open a standalone transaction?

### Exercise 33 — SQL vs. PL/pgSQL

A task needs loops, exception handling, and dynamic SQL. Why is PL/pgSQL clearer than forcing it into an SQL-language `SELECT` function?

### Exercise 34 — Functions vs. procedures

Compare `SELECT f(...)` with `CALL p(...)`. Under what conditions can a procedure perform transaction control within PostgreSQL limits?

### Exercise 35 — JDBC scalar functions

Write a `PreparedStatement` calling `amount_with_tax(?,?)` with `BigDecimal`. Why should you never concatenate monetary input into SQL strings?

### Exercise 36 — JDBC table functions

Write a `PreparedStatement` calling `orders_in_period(?,?,?)` with `Timestamp` from `Instant`, `ORDER BY`, and `LIMIT`. Explain how `tenant_id` should come from an authenticated context.

### Exercise 37 — Function overloading

Create two overloads: `double_value(integer)` and `double_value(numeric)`. Call them with explicit casts and with an untyped literal to observe resolution.

### Exercise 38 — CREATE OR REPLACE

Update a function body while preserving its signature. Try changing `RETURNS` from `INTEGER` to `TEXT` and explain the restriction without breaking needed lab objects.

### Exercise 39 — Permissions

In a lab allowing role creation, grant only `EXECUTE` on a function and `USAGE` on its schema. Compare how `SECURITY INVOKER` and `SECURITY DEFINER` affect base-table access.

### Exercise 40 — RLS and SECURITY DEFINER

Describe a scenario where a function accepts an arbitrary `p_tenant_id` and executes under a high-privilege owner. If a caller passes another tenant's ID, what data leak occurs? Design proper authorization.

### Exercise 41 — pg_get_functiondef

Retrieve a function definition via `pg_get_functiondef('schema.fn(args)'::regprocedure)`. Why must overloads specify exact input types?

### Exercise 42 — Optimization benchmark

Benchmark three pairs: scalar function vs. expression, table function vs. direct query, and `LATERAL` function vs. window query. Record Planning Time, Execution Time, `BUFFERS`, actual rows, and loop counts.

### Exercise 43 — Does optimization preserve semantics?

A developer rewrites `ROUND(amount * 1.08,2)>100` as `amount>100/1.08`. Test whether all boundary cases yield identical results before accepting the optimization.

### Exercise 44 — Production design

A multi-tenant system with 400 million orders needs a 30-day reader function, daily metrics, restricted access, and dashboards running hundreds of times per hour. Propose SQL functions, indexes, security policies, inlining verification, view vs. materialized view trade-offs, and a versioning/migration strategy.

---

## 42. Pre-production checklist for SQL functions

| Question | How to evaluate |
| --- | --- |
| Does the function truly need reuse? | Multiple consumers or clear domain semantics |
| SQL or PL/pgSQL? | `SELECT`/expression vs. procedural control flow |
| Function or procedure? | `SELECT`/`RETURN` contract vs. transaction control |
| Are name and schema unambiguous? | Schema-qualified names and clear conventions |
| Are signatures overloaded? | Avoid implicit cast and default-argument ambiguity |
| Is the return type accurate? | Scalar/`SETOF`/`TABLE`, `BIGINT`/`NUMERIC` |
| Are parameter names stable? | Named arguments are part of the API |
| How are NULL inputs handled? | `STRICT` vs. `CALLED ON NULL INPUT` |
| Are parameter defaults accurate? | Omitted vs. explicit NULL behavior |
| Is `IMMUTABLE` genuinely true? | Reads no mutable tables, clocks, or session state |
| Is `STABLE` accurate? | Read-only, statement-level snapshot semantics |
| Are there side effects? | Requires `VOLATILE` and proper permissions |
| Does it call more volatile functions? | Classification must respect all dependencies |
| Can `PARALLEL SAFE` be proven? | No DML or parallel-unsafe operations |
| Are `COST`/`ROWS` realistic? | Estimated against representative data |
| Is the body a single expression/SELECT? | Stronger chance of inlining |
| Uses `SECURITY DEFINER`? | Privilege boundary vs. non-inlining trade-off |
| Sets `SET search_path`? | Security protection and inlining impact |
| Vulnerable to SQL injection? | Bind parameters; no string concatenation |
| Implicit `search_path` resolution? | Schema-qualify calls in sensitive code |
| Do callers have `EXECUTE`? | Role-based grants |
| Does `PUBLIC` hold unwanted access? | Explicit `REVOKE`/`GRANT` |
| Do calling roles have base-table rights? | Invoker vs. definer semantics |
| Are RLS and tenant checks enforced? | Test with real roles and tenants |
| Does the interface match the intended grain? | Avoid accidental row multiplication in joins |
| Does a table function return huge sets? | Actual row counts, filters, and limits |
| Do outer `WHERE` predicates push down? | Inspect `EXPLAIN` and `Filter` nodes |
| Does `Function Scan` appear? | If so, verify cost and `ROWS` estimates |
| Did scalar functions inline? | Check `EXPLAIN VERBOSE` and direct comparisons |
| Do column wrappers block indexes? | Check sargability / expression indexes |
| Do time filters use half-open ranges? | Raw timestamp comparisons and accurate timezones |
| Are base-table indexes aligned? | Verify via `EXPLAIN BUFFERS` |
| Do `LATERAL` calls loop excessively? | Check loop counts and outer row counts |
| Is `ORDER BY` deterministic? | Never rely on incidental plan order |
| Would a materialized view help? | Weigh read frequency vs. freshness |
| Tested NULL and 0-row edge cases? | `COUNT` vs. `SUM` and `RETURNS TABLE` |
| Tested stale data/config risks? | Verify `IMMUTABLE` correctness |
| Checked SQL-standard body support? | Match target PostgreSQL version |
| Planned dependency migrations? | `CREATE OR REPLACE` and return-type constraints |
| Versioned breaking changes? | Coordinated consumer rollout |
| Tested privileges and concurrency? | Multiple roles and concurrent transactions |
| Benchmarked across multiple runs? | Planning/Execution/Buffers/P95 |
| Monitored query costs? | `pg_stat_statements` where available |
| Documented the full contract? | Semantics, NULLs, timezones, and types |
| Prepared a rollback plan? | Avoid accidental `DROP CASCADE` |

## Conclusion

Writing functions in `LANGUAGE SQL` is a powerful way in PostgreSQL to **reuse calculations and parameterized queries**, especially when a function is a concise expression or a set-returning `SELECT`. A key advantage is that PostgreSQL **can inline eligible SQL functions**, letting the optimizer inspect underlying expressions, base tables, predicates, and access paths.

Principles to remember:

1. **SQL functions are not "guaranteed-inlined macros."** Inlining depends on body structure, return type, volatility, security settings, configuration, and PostgreSQL version.
2. **Choose explicit return contracts.** `RETURNS type`, `RETURNS SETOF type`, and `RETURNS TABLE(...)` serve distinct interface shapes.
3. **Declare volatility honestly.** `IMMUTABLE` for state-independent math; `STABLE` for statement-consistent reads; `VOLATILE` when side effects or changing values occur during execution.
4. **`STRICT` carries concrete NULL semantics.** It is not just an optimization; it changes results if the body expects to handle NULL.
5. **`COST`/`ROWS` are estimates, not caps or milliseconds.** Use them to guide planner estimates, especially when functions do not inline.
6. **Optimize based on real execution plans.** Compare `Function Scan` against base-table scans, checking predicate pushdown, indexes, actual rows, loops, buffers, and execution time.
7. **Functions on columns can block index usage.** Use raw range predicates or dedicated expression indexes when justified by workload data.
8. **Security comes before inlining.** `SECURITY DEFINER`, `SET search_path`, `EXECUTE` grants, and RLS enforce access boundaries; never strip them solely for a faster plan.
9. **Set-returning functions and `LATERAL` can execute repeatedly.** Outer row counts and inner indexes dictate real cost.
10. **Manage functions as database APIs.** Parameter types and names, signatures, permissions, dependencies, and migrations all affect consumers.
11. **Never trade correctness for speed.** A falsely `IMMUTABLE` function or an unverified `WHERE` rewrite that alters rounding can be fast yet wrong.
12. **Keep designs simple.** When a direct `SELECT`, CTE, or view is clearer and optimizes better, do not create a function just because you can.

A well-crafted PostgreSQL SQL function meets three goals simultaneously: **accurately expresses business logic**, **enforces a clear interface and security boundary**, and **gives the optimizer fair opportunities to tune—backed by measured execution costs**. Once you understand inlining limits and `EXPLAIN`, you can harness SQL functions without turning reusable logic into an opaque performance bottleneck.
