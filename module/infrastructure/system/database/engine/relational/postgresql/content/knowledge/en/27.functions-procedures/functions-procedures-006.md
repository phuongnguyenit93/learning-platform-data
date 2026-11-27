# Volatility, STRICT, and Parallel Safety Attributes of PostgreSQL Functions

When writing a PostgreSQL function, you do not only decide **what the function computes**. You must also declare attributes that tell PostgreSQL **when it may optimize function calls, what happens when parameters are `NULL`, and whether the function is safe inside a parallel query plan**.

The three key attribute groups are:

- **Volatility:** `IMMUTABLE`, `STABLE`, `VOLATILE`.
- **NULL-input handling:** `STRICT` (equivalent to `RETURNS NULL ON NULL INPUT`) or `CALLED ON NULL INPUT`.
- **Parallel safety:** `PARALLEL SAFE`, `PARALLEL RESTRICTED`, `PARALLEL UNSAFE`.

Example of a pure math function:

```sql
CREATE FUNCTION public.calculate_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

The three declarations carry **three distinct meanings**:

1. `IMMUTABLE`: given the same two inputs, the result never changes due to time, database state, or session settings.
2. `STRICT`: if **any parameter is NULL**, PostgreSQL returns NULL without executing the function body.
3. `PARALLEL SAFE`: the function is declared safe to execute inside a parallel worker, provided its internal operations and callees actually satisfy that guarantee.

**Declaring attributes does not make a flawed function valid.** PostgreSQL largely **trusts the author's declarations** when optimizing. Mislabeling a function that reads mutable config as `IMMUTABLE`, or marking a sequence-calling function `PARALLEL SAFE`, can produce wrong plans, runtime errors, or unpredictable results.

This lesson walks through selection criteria, SQL/PLpgSQL examples, planner effects, snapshots, expression indexes, prepared statements, the `pg_proc` catalog, `EXPLAIN` experiments, Java considerations, and exercises.

## 1. Learning objectives

After this lesson, you can:

1. Accurately distinguish immutable, statement-stable, and volatile function behaviors.
2. Explain how volatility affects constant folding, index conditions, prepared execution plans, and MVCC snapshots.
3. Classify math functions, config/table lookup functions, time functions, and sequence-calling functions.
4. Use `STRICT` appropriately and understand why it does not imply `NOT NULL` return values.
5. Write functions that actively handle `NULL` via `CALLED ON NULL INPUT`.
6. Distinguish `PARALLEL SAFE`, `PARALLEL RESTRICTED`, and `PARALLEL UNSAFE`.
7. Identify operations that make a function unsafe or leader-only: data writes, sequences, temporary tables, cursors, and session/backend-local state.
8. Recognize that these three attribute groups are orthogonal dimensions **that cannot be inferred from one another**.
9. Analyze function calls in `WHERE`, `SELECT`, `ORDER BY`, and index expressions.
10. Inspect `pg_proc.provolatile`, `proisstrict`, `proparallel`, and function definitions in the catalog.
11. Use `ALTER FUNCTION` to correct metadata after accurately auditing behavior.
12. Distinguish optimizer metadata from access privileges, `SECURITY DEFINER`, and business constraints.
13. Design tests for correctness, NULLs, session/database state mutations, and parallel queries.
14. Recognize that `CREATE PROCEDURE` does not share the same attribute set as `CREATE FUNCTION`.

## 2. The big picture: three independent questions

| Attribute | Question to answer | Options |
| --- | --- | --- |
| **Volatility** | How can results or behavior vary for identical arguments? | `IMMUTABLE`, `STABLE`, `VOLATILE` |
| **Null-input behavior** | May PostgreSQL skip execution when any parameter is NULL? | `STRICT` or `CALLED ON NULL INPUT` |
| **Parallel safety** | Where is the function permitted to run inside a parallel plan? | `SAFE`, `RESTRICTED`, `UNSAFE` |

Combinations can vary widely:

```text
Function multiplying two numbers:
    IMMUTABLE + STRICT + PARALLEL SAFE

Function reading current price from a table:
    STABLE + STRICT + PARALLEL SAFE (if only reading regular tables
    and all involved operations are genuinely parallel-safe)

Function allocating sequence IDs via nextval():
    VOLATILE + PARALLEL UNSAFE
    (STRICT is irrelevant if the function takes no parameters)

Function reading backend-local state:
    May be STABLE yet PARALLEL RESTRICTED

Function converting NULL to 0:
    IMMUTABLE + CALLED ON NULL INPUT + PARALLEL SAFE
```

Key takeaway: **Volatility does not automatically dictate STRICT or parallel safety**. A function can return consistent results within an SQL statement while still depending on leader-only state.

## 3. Role of attributes in CREATE FUNCTION

Basic syntax:

```sql
CREATE FUNCTION function_name(arg1 integer, arg2 integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT arg1 + arg2
$$;
```

In PostgreSQL, the relevant declaration groups are:

```sql
-- Choose one volatility option:
IMMUTABLE
STABLE
VOLATILE

-- Choose one null-input behavior:
STRICT
RETURNS NULL ON NULL INPUT
CALLED ON NULL INPUT

-- Choose one parallel safety option:
PARALLEL SAFE
PARALLEL RESTRICTED
PARALLEL UNSAFE
```

### 3.1. Defaults when omitted

For a new function without explicit attributes:

| Group | Default |
| --- | --- |
| Volatility | `VOLATILE` |
| NULL handling | `CALLED ON NULL INPUT` |
| Parallel safety | `PARALLEL UNSAFE` |

These defaults are **conservative**: PostgreSQL does not automatically deduce from SQL code alone that a function is immutable, ignores NULLs, or is worker-safe.

### 3.2. Example of a function using defaults

```sql
CREATE FUNCTION public.add_numbers_default(a integer, b integer)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT a + b
$$;
```

Mathematically, this function qualifies for `IMMUTABLE STRICT PARALLEL SAFE`, yet omitting the clauses causes the catalog to record the conservative defaults: **VOLATILE**, **not strict**, **UNSAFE**.

That can block certain planner optimizations. **Never flip labels simply because a body looks short**: audit nested calls, data types, collations, settings, and actual side effects.

### 3.3. CREATE FUNCTION vs. CREATE PROCEDURE

This chapter is titled "Functions and Procedures," yet `IMMUTABLE`/`STABLE`/`VOLATILE`, `STRICT`, and `PARALLEL ...` are attributes of **`CREATE FUNCTION`**. **`CREATE PROCEDURE`** serves a different purpose with different options and does not offer this same attribute set.

Procedures are invoked via `CALL`; functions participate in `SELECT`, `WHERE`, `JOIN`, and index expressions, which is why the planner relies heavily on function metadata.

## 4. Practice environment

Create a dedicated schema in a learning database. The examples below require no internet access or special extensions.

### 4.1. Create the schema

```sql
CREATE SCHEMA IF NOT EXISTS function_attrs_lab;
```

### 4.2. Product prices table

```sql
CREATE TABLE function_attrs_lab.product_prices (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO function_attrs_lab.product_prices
    (product_id, sku, unit_price)
VALUES
    (10, 'BOOK-POSTGRES', 125.00),
    (20, 'BOOK-JAVA', 180.00),
    (30, 'ACCESS-ONLINE', 90.00);
```

### 4.3. Sales table

```sql
CREATE TABLE function_attrs_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL
        REFERENCES function_attrs_lab.product_prices(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    sold_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO function_attrs_lab.sales
    (product_id, quantity, unit_price, sold_at)
VALUES
    (10, 2, 125.00, '2026-11-01 09:00:00+00'),
    (20, 1, 180.00, '2026-11-01 10:00:00+00'),
    (10, 3, 125.00, '2026-11-02 09:00:00+00'),
    (30, 4, 90.00,  '2026-11-03 09:00:00+00');

ANALYZE function_attrs_lab.product_prices;
ANALYZE function_attrs_lab.sales;
```

In the sections ahead, we create standalone functions to avoid unnecessarily mutating sample rows. Exercises that intentionally error or modify data include transaction/`ROLLBACK` instructions.

## 5. VOLATILITY is a promise to the optimizer

Volatility classification answers: **given the exact same input arguments, what may PostgreSQL assume about the function's output and side effects?**

Three levels:

```text
IMMUTABLE
    Same arguments -> same result forever.
    No dependency on time, session settings, or mutable database state.

STABLE
    Same arguments -> same result within a single SQL statement.
    May differ in subsequent statements.

VOLATILE
    Same arguments -> may still return different results on every call.
    May cause side effects; optimizations reserved for STABLE/IMMUTABLE
    are forbidden.
```

### 5.1. Not automatically verified

PostgreSQL **cannot fully verify** whether a PL/pgSQL, SQL, or C function honors its volatility promise. If misdeclared:

- The planner may pre-evaluate the function too early.
- Prepared plans may cache stale values.
- Expression indexes may store values that no longer match current rules.
- Dynamic table reads may return unexpected outputs.

Always choose the **accurate and sufficiently conservative** level, never the "fastest-sounding" label at all costs.

### 5.2. Volatility applies to the entire call chain

If a function calls another function, reads configuration variables, or queries tables, **every dependency** counts. Simple multiplication is not immutable if one factor is fetched from a table or session setting.

## 6. IMMUTABLE: same inputs, same output

An immutable function promises **no dependency on mutable data or state**, returning identical outputs for identical inputs under defined semantics.

Example:

```sql
CREATE FUNCTION function_attrs_lab.net_to_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

Test:

```sql
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS gross1,
    function_attrs_lab.net_to_gross(100, 0.08) AS gross2;
```

For inputs 100 and 0.08, the result never depends on today's date, current role, `product_prices` rows, or session state.

### 6.1. Typically suitable cases

- Fixed arithmetic on input arguments.
- String normalization using transformations whose semantics and collations are verified immutable in the target environment.
- Format conversions with explicit inputs/rules that read no mutable settings.
- Deterministic checksums/transformations when the implementation truly depends on no external state.

### 6.2. Cases unsuitable for IMMUTABLE

- Fetching the latest price from a table.
- Reading the current time.
- Reading `current_setting(...)` for GUCs that can vary across sessions or statements.
- Generating random numbers.
- Advancing sequences.
- Depending on external files, server settings, timezones, or external data not passed as arguments.

### 6.3. IMMUTABLE does not mean the return value is NOT NULL

`IMMUTABLE` describes volatility, **not nullability**. An immutable function can still return NULL for specific inputs.

## 7. STABLE: consistent within a single statement

A `STABLE` function can depend on state that changes **between SQL statements**, while promising identical outputs for identical arguments **within one statement**.

Example reading unit prices from a table:

```sql
CREATE FUNCTION function_attrs_lab.lookup_price(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT unit_price
    FROM function_attrs_lab.product_prices
    WHERE product_id = p_product_id
$$;
```

Test:

```sql
SELECT
    function_attrs_lab.lookup_price(10) AS price_book_postgres,
    function_attrs_lab.lookup_price(20) AS price_book_java;
```

With the sample data, results are 125.00 and 180.00.

### 7.1. Why not IMMUTABLE?

Because `unit_price` can be updated:

```sql
BEGIN;

UPDATE function_attrs_lab.product_prices
SET unit_price = 135.00,
    updated_at = now()
WHERE product_id = 10;

SELECT function_attrs_lab.lookup_price(10);

ROLLBACK;
```

The function reads a mutable table and cannot guarantee product 10 will **forever cost 125.00**.

### 7.2. Why is STABLE valid?

Under PostgreSQL's snapshot rules, `STABLE`/`IMMUTABLE` functions use the snapshot established at the **start of the calling query**, so lookups remain consistent within that statement's snapshot. The function itself must not modify data.

A long-running statement should not expect a `STABLE` call to see concurrent commits made after the statement started.

### 7.3. STABLE does not mean "unchanged across an entire transaction"

`STABLE` only guarantees stability **within a single statement**. Under `READ COMMITTED` isolation, consecutive statements in the same transaction take fresh snapshots. A `STABLE` table-reading function can return a newer value in a later statement after another session commits.

Under `REPEATABLE READ`, transaction-level snapshots carry their own semantics. Never confuse a function's `STABLE` attribute with transaction isolation levels.

### 7.4. Table lookups inside functions can cause server-side N+1

Calling `lookup_price(product_id)` per row triggers repeated table lookups:

```sql
SELECT
    s.sale_id,
    function_attrs_lab.lookup_price(s.product_id) AS current_price
FROM function_attrs_lab.sales AS s;
```

Often, joining the price table directly is simpler and faster:

```sql
SELECT
    s.sale_id,
    p.unit_price AS current_price
FROM function_attrs_lab.sales AS s
JOIN function_attrs_lab.product_prices AS p
  ON p.product_id = s.product_id;
```

Marking a function `STABLE` does not guarantee it executes once across all rows or eliminate repeated lookup overhead.

## 8. VOLATILE: outputs may differ on every call, and side effects are allowed

`VOLATILE` is the most conservative classification. PostgreSQL cannot assume identical arguments yield identical outputs.

Example:

```sql
SELECT
    random() AS random_1,
    random() AS random_2,
    clock_timestamp() AS time_1,
    clock_timestamp() AS time_2;
```

`random()` and `clock_timestamp()` illustrate outputs that vary between calls.

### 8.1. Creating a function calling random

```sql
CREATE FUNCTION function_attrs_lab.random_discount(
    max_discount numeric
)
RETURNS numeric
LANGUAGE sql
VOLATILE
PARALLEL UNSAFE
AS $$
    SELECT random() * max_discount
$$;
```

In this lab, we conservatively set `PARALLEL UNSAFE` so we don't need to audit every dependency here. That **does not mean every function using `random()` must be `UNSAFE`**; parallel safety of any call must be checked individually, including the catalog entries of called functions.

### 8.2. An UPDATE cannot be marked STABLE

A PL/pgSQL function can modify tables:

```sql
CREATE FUNCTION function_attrs_lab.set_product_price(
    p_product_id bigint,
    p_new_price numeric
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
AS $$
BEGIN
    UPDATE function_attrs_lab.product_prices
    SET unit_price = p_new_price,
        updated_at = now()
    WHERE product_id = p_product_id;
END;
$$;
```

Because it mutates data, it must be `VOLATILE` and `PARALLEL UNSAFE`.

Test inside a transaction:

```sql
BEGIN;

SELECT function_attrs_lab.set_product_price(20, 190.00);

SELECT product_id, unit_price
FROM function_attrs_lab.product_prices
WHERE product_id = 20;

ROLLBACK;
```

### 8.3. VOLATILE does not mean "must return a different value every time"

A `VOLATILE` function may still return the same value across repeated calls. The keyword simply tells PostgreSQL **not to rely on stability assumptions** allowed for `STABLE`/`IMMUTABLE`.

For example, `add_numbers_default(2,3)` always returns 5 yet defaults to `VOLATILE`. Outputs still match; the planner is merely constrained by the conservative metadata.

## 9. Three timestamps: transaction, statement, and wall clock

PostgreSQL offers several time functions that are easy to confuse:

```sql
SELECT
    now() AS transaction_time,
    transaction_timestamp() AS transaction_timestamp_value,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;
```

Meanings:

| Function | Time reference | Typical classification |
| --- | --- | --- |
| `now()` | Transaction start time | `STABLE` |
| `transaction_timestamp()` | Equivalent transaction start time | `STABLE` |
| `statement_timestamp()` | Start of the current statement | `STABLE` |
| `clock_timestamp()` | Actual wall-clock time when called | `VOLATILE` |

### 9.1. Why isn't now() immutable?

Running a query today versus next week produces different transaction start times. Therefore, even though `now()` stays constant throughout a transaction, it **can never be IMMUTABLE**.

### 9.2. Differences in a longer transaction

```sql
BEGIN;

SELECT now(), statement_timestamp(), clock_timestamp();
SELECT pg_sleep(0.05);
SELECT now(), statement_timestamp(), clock_timestamp();

ROLLBACK;
```

Within the same transaction:

- `now()` stays anchored at transaction start.
- `statement_timestamp()` updates at the start of each statement.
- `clock_timestamp()` reads the live wall clock at the moment of each call.

For statements back-to-back, differences may be tiny. `pg_sleep` only makes the delta visible in experiments—never add artificial sleeps to production requests.

### 9.3. "STABLE" time is not the same as a data snapshot

`now()` reflects transaction time, whereas a table-reading function's `STABLE` classification governs statement-level snapshot visibility. Do not assume all `STABLE` functions return identical results across multiple statements in a transaction.

## 10. MVCC snapshots when functions execute SQL

PostgreSQL uses MVCC to control which row versions an SQL query can see.

An important distinction:

- When a **`STABLE`** or **`IMMUTABLE`** function runs an internal `SELECT`, PostgreSQL uses the snapshot acquired at the **start of the calling query**.
- When a **`VOLATILE`** function runs internal SQL, each internal query can acquire a fresh snapshot at its own start, seeing database changes made during execution.

### 10.1. Practical implication

If a `VOLATILE` function runs multiple internal `SELECT`s or modifies data, it can observe updates that a `STABLE` function in the same context would not see.

### 10.2. This is not a new lock or isolation mechanism

Declaring `STABLE` does **not**:

- Start a new transaction.
- Lock any tables read by the function.
- Upgrade `READ COMMITTED` to `REPEATABLE READ`.
- Guarantee results stay unchanged across HTTP requests.

It is strictly part of the **planner contract and function snapshot mechanism**, not a connection isolation setting.

### 10.3. Do not perform SQL writes inside STABLE/IMMUTABLE functions

If you attempt `UPDATE`/`INSERT` inside a function marked `STABLE` or `IMMUTABLE`, PostgreSQL rejects disallowed write operations inside non-volatile functions. Any function modifying the database must be classified `VOLATILE`.

Never try to "cheat" by marking a writing function `STABLE` for optimization.

## 11. Constant folding: why can IMMUTABLE be evaluated at plan time?

Suppose:

```sql
SELECT function_attrs_lab.net_to_gross(100, 0.08);
```

An `IMMUTABLE` function given **constant arguments** can be pre-evaluated by the planner during planning (*constant folding*). In many plans, the call is replaced with the resulting constant.

### 11.1. Benefits

- Eliminates runtime function-call overhead.
- Derives constant predicates for indexes and filters.
- Unlocks broader expression simplifications across the query.

### 11.2. Why is it a double-edged sword?

If an author marks a function `IMMUTABLE` when it **actually reads mutable state**, the planner can pre-evaluate it and **bake stale results into a cached execution plan**.

This bug surfaces frequently with prepared statements, server-side driver prepares, or cached PL/pgSQL plans.

### 11.3. Never assume the function body executes exactly once

The optimizer can inline, fold, re-evaluate, or skip a function depending on expressions and plans. Volatility is an optimization contract, **not a call-count counter**.

If business logic requires a side effect to happen once per operation, never hide it inside an SQL expression relying on `SELECT` evaluation counts.

## 12. Serious mistake: marking session settings as IMMUTABLE

Suppose a system stores a display multiplier in a custom GUC:

```sql
SET function_attrs_lab.demo_factor = '1.10';
```

A **wrong** function:

```sql
-- INTENTIONALLY WRONG: anti-pattern illustration, DO NOT use in production.
CREATE FUNCTION function_attrs_lab.wrong_factor(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT x * current_setting(
        'function_attrs_lab.demo_factor'
    )::numeric
$$;
```

Because `current_setting(...)` can change across sessions or statements, this function is **not truly IMMUTABLE**.

### 12.1. Risk with prepared plans

Consider:

```sql
PREPARE demo_wrong AS
SELECT function_attrs_lab.wrong_factor(100);

EXECUTE demo_wrong;

SET function_attrs_lab.demo_factor = '1.20';

EXECUTE demo_wrong;

DEALLOCATE demo_wrong;
```

If the planner constant-folded `wrong_factor(100)` into the cached plan, the second `EXECUTE` **can return the stale value** instead of reading the new GUC. Exact behavior depends on plan caching, inlining, and prepare timing; **a lucky test run never proves an invalid `IMMUTABLE` label is safe**.

### 12.2. Correct declaration

```sql
CREATE FUNCTION function_attrs_lab.factor_for_session(
    x numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT x * current_setting(
        'function_attrs_lab.demo_factor'
    )::numeric
$$;
```

Mark it `STABLE` because the factor can change across statements or sessions while remaining consistent within a single statement per PostgreSQL semantics.

Here we leave **parallel safety at default `UNSAFE`**, avoiding claiming worker safety without auditing implementation, session state, and called functions.

### 12.3. Pass configuration as an explicit argument when appropriate

When business logic needs pure, cacheable, or indexable computation, the clean solution is:

```sql
SELECT function_attrs_lab.net_to_gross(100, 0.20);
```

With the factor passed explicitly, the function is genuinely immutable, making dependencies explicit and avoiding "hidden session parameters."

## 13. Mistake: declaring table lookups as IMMUTABLE

Example:

```sql
-- DO NOT create this version on production:
-- CREATE FUNCTION product_price_immutable(p_id bigint)
-- RETURNS numeric
-- LANGUAGE sql
-- IMMUTABLE
-- AS $$
--     SELECT unit_price
--     FROM function_attrs_lab.product_prices
--     WHERE product_id = p_id
-- $$;
```

`product_prices` can be updated, so results are **not permanent**. `STABLE` is the right choice for statement-snapshot price lookups.

### 13.1. Damage goes beyond prepared statements

If a mislabeled function is used in an expression index or generated column, persisted values get tied to table state at write/index-build time and will not update when the referenced table changes.

**Function declarations must be truthful before supporting persisted derived data.**

### 13.2. Be wary of "reference tables that never change"

Even a "static configuration table" changes during migrations, hotfixes, or restores. If a function reads a table, do not call it `IMMUTABLE` simply because updates are rare.

## 14. Volatility affects index eligibility

Suppose:

```sql
CREATE INDEX idx_lab_sales_sold_at
ON function_attrs_lab.sales (sold_at);
```

Predicate:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < now();
```

`now()` is `STABLE`. PostgreSQL can treat it as a fixed boundary for the scan and consider an index plan.

By contrast:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < clock_timestamp();
```

`clock_timestamp()` is `VOLATILE`; PostgreSQL cannot freeze a single timestamp across the entire scan the way it does with `STABLE` functions. It may have to evaluate the condition per row rather than using the same index range boundary.

### 14.1. VOLATILE does not disable all indexes

Other predicates in the same `WHERE` clause can still use indexes:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE product_id = 10
  AND sold_at < clock_timestamp();
```

PostgreSQL can still use an index on `product_id` if beneficial, while applying `clock_timestamp()` as a filter.

### 14.2. Read EXPLAIN rather than guessing scan types

On a four-row table, `Seq Scan` is usually cheapest. As the lab scales up, inspect `EXPLAIN` and `EXPLAIN (ANALYZE, BUFFERS)` to check `Index Cond`, `Filter`, row counts, and buffers.

## 15. IMMUTABLE is a standard requirement for expression indexes

Example normalizing SKU codes:

```sql
CREATE FUNCTION function_attrs_lab.normalize_sku(
    raw_sku text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT lower(btrim(raw_sku))
$$;
```

Then:

```sql
CREATE INDEX idx_lab_products_normalized_sku
ON function_attrs_lab.product_prices (
    function_attrs_lab.normalize_sku(sku)
);
```

Query:

```sql
SELECT product_id, sku, unit_price
FROM function_attrs_lab.product_prices
WHERE function_attrs_lab.normalize_sku(sku)
    = function_attrs_lab.normalize_sku('  book-postgres  ');
```

### 15.1. Why do indexes require IMMUTABLE?

An expression index stores **the computed expression result at insert/index-build time**. If the same `sku` returned a different result tomorrow, index entries would no longer match lookup predicates.

Hence PostgreSQL requires functions inside index expressions (and partial index predicates) to be **`IMMUTABLE`**.

### 15.2. Watch out for collations and library upgrades

`lower(text)` depends on locale/collation case rules. If the environment upgrades its collation provider or Unicode version, computed normalization can diverge from existing index entries. Even when a function is marked immutable, operations teams must plan for **`REINDEX`** after collation upgrades.

Never assume "IMMUTABLE" guarantees invariance across **all OS, library, collation, extension, or PostgreSQL upgrades**.

### 15.3. What if a function is only STABLE?

A `STABLE` function reading a price or config table cannot back a persistent expression index. PostgreSQL rejects non-immutable functions in index definitions.

## 16. IMMUTABLE and partial indexes

A partial index stores only rows matching a predicate:

```sql
CREATE INDEX idx_lab_products_price_positive
ON function_attrs_lab.product_prices (product_id)
WHERE unit_price > 0;
```

The predicate `unit_price > 0` depends purely on row values, so the index stays valid as `unit_price` updates.

However, never use:

```sql
-- INVALID for an index predicate:
-- CREATE INDEX idx_recent_sales
-- ON function_attrs_lab.sales (sale_id)
-- WHERE sold_at >= now() - INTERVAL '7 days';
```

Because `now()` is `STABLE`, not `IMMUTABLE`. A row "within the last 7 days" drifts out of the predicate simply as time passes **without any row UPDATE**, so the index cannot stay consistent via row modifications alone.

### 16.1. Alternatives

To index recent data, consider:

- A fixed cutoff predicate managed via controlled migrations.
- Time-based partitioning with partition pruning.
- A regular B-tree on `sold_at` paired with `now() - interval ...` in queries.
- Controlled lifecycle status flags if business rules genuinely require them.

Never "fix" the error by falsely marking a time function `IMMUTABLE`.

## 17. IMMUTABLE and generated columns

PostgreSQL generated columns restrict allowed expressions, generally requiring **immutable expressions**.

Example:

```sql
CREATE TABLE function_attrs_lab.sku_inputs (
    sku_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_sku text NOT NULL,
    normalized_sku text GENERATED ALWAYS AS (
        function_attrs_lab.normalize_sku(raw_sku)
    ) STORED
);

INSERT INTO function_attrs_lab.sku_inputs (raw_sku)
VALUES (' Book-Postgres '), ('BOOK-JAVA');

SELECT sku_id, raw_sku, normalized_sku
FROM function_attrs_lab.sku_inputs
ORDER BY sku_id;
```

### 17.1. Why can't a generated column look up current prices?

If `generated_price` depended on `product_prices`, updating `product_prices` would not update stored generated columns in referencing tables.

Generated expressions must derive solely from **columns in the same row** and valid immutable operations under PostgreSQL rules.

### 17.2. Do not confuse generated columns with VIEWs

A regular view computes expressions at query time; a stored generated column persists values at write time. Immutability rules and maintenance trade-offs differ completely.

## 18. CHECK constraints and immutability

A constraint:

```sql
CREATE TABLE function_attrs_lab.tax_rules (
    rule_id integer PRIMARY KEY,
    rate numeric NOT NULL
        CHECK (rate BETWEEN 0 AND 1)
);
```

relies solely on row values and immutable comparisons.

Trying to embed time-dependent or cross-table functions in `CHECK` causes:

- Rows valid today silently turning "invalid" tomorrow without any `UPDATE`.
- Backup/restore failures due to load order or changed state.
- Constraints never being re-evaluated when external tables change.

PostgreSQL assumes `CHECK` expressions are **immutable for a given row**. It does not track dynamic external dependencies on the author's behalf.

### 18.1. When cross-table invariants are required

Use foreign keys, `UNIQUE`, exclusion constraints, transaction logic, properly locked triggers, or a better data model instead of faking an immutable lookup function inside `CHECK`.

## 19. Prepared statements: performance and stale-plan risks

Java/PostgreSQL applications routinely reuse prepared statements:

```sql
PREPARE sale_gross(numeric, numeric) AS
SELECT function_attrs_lab.net_to_gross($1, $2);

EXECUTE sale_gross(100, 0.08);
EXECUTE sale_gross(200, 0.10);

DEALLOCATE sale_gross;
```

For genuinely immutable functions, the planner can safely apply constant folding and caching.

### 19.1. Generic plans vs. custom plans

PostgreSQL chooses between generic and custom plans for prepared statements:

- **Custom plans** optimize using known parameter values.
- **Generic plans** are reused across executions with varying parameter values.

If a function is falsely marked `IMMUTABLE` and constant-folded inside a cached plan for constant arguments, underlying table or session changes will not invalidate that folded constant.

### 19.2. Not every expression is folded at PREPARE time

PostgreSQL may replan or defer optimizations depending on parameters. **Never assume** a function runs at one exact moment simply because `PREPARE` was used.

The key point is that **misclassification enables invalid optimizations**; actual plan choice and call counts must be observed in the live system.

## 20. STRICT: skip the function body when any argument is NULL

In PostgreSQL:

```sql
STRICT
```

and:

```sql
RETURNS NULL ON NULL INPUT
```

declare the same behavior for SQL functions: if **any input argument is NULL**, PostgreSQL returns **NULL immediately** without **executing the body**.

Example:

```sql
CREATE FUNCTION function_attrs_lab.double_strict(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT x * 2
$$;
```

Test:

```sql
SELECT
    function_attrs_lab.double_strict(5) AS five_doubled,
    function_attrs_lab.double_strict(NULL::numeric) AS null_doubled;
```

Result:

```text
five_doubled = 10
null_doubled = NULL
```

### 20.1. Multiple parameters: one NULL is enough

`net_to_gross(net_amount, tax_rate)` is declared `STRICT`:

```sql
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS normal,
    function_attrs_lab.net_to_gross(NULL::numeric, 0.08) AS missing_amount,
    function_attrs_lab.net_to_gross(100, NULL::numeric) AS missing_rate,
    function_attrs_lab.net_to_gross(NULL::numeric, NULL::numeric)
        AS both_missing;
```

All three calls with at least one NULL return NULL without executing the body.

### 20.2. STRICT is not shorthand for COALESCE

A function containing `COALESCE(x,0)` intending to return 0 when `x` is NULL **must not be STRICT**—otherwise PostgreSQL skips the body and returns NULL before `COALESCE` ever runs.

## 21. CALLED ON NULL INPUT: let the body decide

This is the default when `STRICT` is omitted.

Example:

```sql
CREATE FUNCTION function_attrs_lab.zero_if_null(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(x, 0)
$$;
```

Test:

```sql
SELECT
    function_attrs_lab.zero_if_null(NULL::numeric) AS null_to_zero,
    function_attrs_lab.zero_if_null(25) AS stays_25;
```

Results: 0 and 25.

### 21.1. Why not STRICT?

Because the business rule explicitly **handles NULL inputs**. Adding `STRICT` prevents `COALESCE(x,0)` from ever executing for NULL.

### 21.2. Handling NULL differently per argument

```sql
CREATE FUNCTION function_attrs_lab.line_total_with_default(
    unit_price numeric,
    quantity integer
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(unit_price, 0)
         * COALESCE(quantity, 1)
$$;
```

Here:

- `unit_price=NULL` becomes 0.
- `quantity=NULL` becomes 1.

This is **this example's policy**, not a universal billing rule. In real invoicing, a `NULL` often must be rejected rather than silently turned into 0 or 1.

### 21.3. CALLED ON NULL INPUT can be omitted

Omitting both attributes defaults to calling the body on NULL. Still, writing `CALLED ON NULL INPUT` explicitly signals intent clearly to readers.

## 22. STRICT does not guarantee NOT NULL outputs

Example:

```sql
CREATE FUNCTION function_attrs_lab.safe_ratio(
    numerator numeric,
    denominator numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT numerator / NULLIF(denominator, 0)
$$;
```

Test:

```sql
SELECT
    function_attrs_lab.safe_ratio(10, 2) AS valid_ratio,
    function_attrs_lab.safe_ratio(10, 0) AS zero_denominator,
    function_attrs_lab.safe_ratio(10, NULL::numeric)
        AS missing_denominator;
```

- `safe_ratio(10,2)` returns 5.
- `safe_ratio(10,0)` returns NULL because `NULLIF(0,0)` yields NULL, and division by NULL returns NULL.
- `safe_ratio(10,NULL)` returns NULL without running the body due to `STRICT`.

**STRICT only defines behavior on NULL inputs; it never guarantees non-null outputs for non-null inputs.**

### 22.1. NULL differs from invalid values

`0` is a non-null number. `STRICT` does not detect zero denominators, negative limits, missing IDs, or malformed JSON.

If division by zero must raise an error instead of returning NULL, implement that policy explicitly.

### 22.2. Understand SQL NULL propagation in expressions

A non-`STRICT` function containing `SELECT x*2` still returns NULL for `x=NULL` because SQL multiplication propagates NULL. That is **body evaluation**, distinct from `STRICT` bypassing the body.

## 23. STRICT and side effects

If a function causes side effects (writing tables, logging, advancing sequences) and is marked `STRICT`, passing a NULL argument skips the body, so the side effect **does not occur**.

### 23.1. Sequence example

```sql
CREATE SEQUENCE function_attrs_lab.event_sequence
START WITH 1000;

CREATE FUNCTION function_attrs_lab.reserve_event_id(
    event_type text
)
RETURNS bigint
LANGUAGE sql
VOLATILE
STRICT
PARALLEL UNSAFE
AS $$
    SELECT nextval(
        'function_attrs_lab.event_sequence'::regclass
    )
$$;
```

Test:

```sql
SELECT function_attrs_lab.reserve_event_id('ORDER') AS new_event_id;
SELECT function_attrs_lab.reserve_event_id(NULL::text)
    AS null_event_type;
```

With `event_type=NULL`, the body does not execute and no sequence number is consumed per the `STRICT` contract.

### 23.2. Why is a sequence function VOLATILE?

`nextval()` mutates sequence state and returns a new value on every call. It cannot be `STABLE` or `IMMUTABLE`.

### 23.3. Why PARALLEL UNSAFE?

Sequence access involves side effects and shared state disallowed inside parallel workers; functions calling `nextval()` must never be marked `PARALLEL SAFE`.

### 23.4. Note on ROLLBACK

Consumed sequence numbers are **never rolled back** when a transaction aborts. Never rely on sequences if business requirements demand gapless IDs.

### 23.5. Do not rely on STRICT for audit guarantees

If a business rule demands "every API call writes an audit row," a `STRICT` function skips its body on NULL input. Audit logging belongs at the proper workflow/transaction layer, never tied ambiguously to expression evaluation.

## 24. STRICT and boolean-returning functions

Example:

```sql
CREATE FUNCTION function_attrs_lab.is_positive_strict(
    x numeric
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT x > 0
$$;
```

On NULL input, the result is NULL rather than `FALSE`.

If the product wants NULL treated as **non-positive**, handle it explicitly:

```sql
CREATE FUNCTION function_attrs_lab.is_positive_or_false(
    x numeric
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(x > 0, false)
$$;
```

### 24.1. Three-valued SQL logic

A `WHERE` clause:

```sql
WHERE function_attrs_lab.is_positive_strict(x)
```

keeps only rows evaluating to `TRUE`. NULL is never treated as `TRUE`.

### 24.2. Returning NULL vs. FALSE is a domain choice

If NULL means **unknown**, returning NULL is more accurate than `false`. If NULL means **invalid**, add constraints or validation. Never coerce all NULLs to `FALSE` merely to avoid three-valued logic.

## 25. STRICT across multiple types and overloads

PostgreSQL allows **function overloading** by signature. When calling:

```sql
SELECT function_attrs_lab.double_strict(NULL);
```

an untyped NULL literal carries no explicit type. If multiple same-named overloads exist or implicit coercions overlap, PostgreSQL may require an explicit cast to select the intended function.

Write explicitly when testing:

```sql
SELECT function_attrs_lab.double_strict(NULL::numeric);
```

### 25.1. STRICT belongs to each individual signature

Given:

```sql
f(integer)
f(numeric)
f(text)
```

each signature is a distinct function in the catalog and can have its own volatility, strictness, and parallel safety labels.

### 25.2. NULL evaluation with composite/record types

Composite types and row expressions follow more subtle NULL rules than simple scalars. When dealing with composite inputs or NULL fields, test the exact signature, `IS NULL`, and `IS NOT NULL` directly instead of assuming scalar rules apply unchanged.

## 26. What is a parallel query in PostgreSQL?

PostgreSQL can select a **parallel execution plan** where worker processes execute portions of a query while a **leader** backend coordinates results.

A plan may look like:

```text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Seq Scan on large_table
```

This is an illustrative plan shape; not every `SELECT` uses `Gather` or workers.

### 26.1. What does parallel safety tell the planner?

The planner must know whether a function can run:

- Directly inside parallel workers.
- Only in the parallel group's leader process.
- Nowhere inside a parallel plan.

That is why `PARALLEL SAFE`, `PARALLEL RESTRICTED`, and `PARALLEL UNSAFE` exist.

### 26.2. Parallel safety does not mean "the function spawns threads"

Marking a function `PARALLEL SAFE` **does not spawn workers itself**. It merely permits the planner to include the function inside worker-executed plan nodes when parallel execution is chosen.

### 26.3. Parallel plans are not always faster

Worker startup cost, tuple passing through `Gather`, coordination, and CPU/memory contention can outweigh benefits on small tables. Seeing no workers in small labs is completely normal.

## 27. PARALLEL SAFE

Declaring:

```sql
PARALLEL SAFE
```

asserts that the function **is safe to execute inside parallel workers**.

Example of a pure math function:

```sql
CREATE FUNCTION function_attrs_lab.line_amount(
    quantity integer,
    unit_price numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT quantity * unit_price
$$;
```

Query:

```sql
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
) AS gross_sales
FROM function_attrs_lab.sales;
```

This function only multiplies two arguments—touching no sequences, session cursors, temporary tables, or table writes—so `PARALLEL SAFE` is valid.

### 27.1. Necessary, not sufficient for a parallel plan

Even when `line_amount` is `SAFE`, PostgreSQL still weighs:

- Table size.
- Parallel capability of scans, aggregates, and joins.
- Server configuration and worker availability.
- Parallel setup overhead.
- Other expressions and functions in the query.

### 27.2. Dependencies must also be safe

An SQL function calling an unsafe C function or extension **must not be marked SAFE** just because the wrapper itself looks simple.

PostgreSQL cannot always inspect arbitrary procedural code and external dependencies to override wrong labels for you.

## 28. PARALLEL RESTRICTED

Declaring:

```sql
PARALLEL RESTRICTED
```

means the function **cannot execute inside parallel workers**, yet may run in the **leader** process during a parallel query when the plan permits.

### 28.1. Examples of leader-only state

Functions depending on:

- Session temporary tables.
- Cursors.
- Prepared statements or backend-local state not synchronized to workers.
- Client connection state or backend-local objects.

should typically be classified **`RESTRICTED`** rather than `SAFE`.

### 28.2. Illustrative example reading backend identity

```sql
CREATE FUNCTION function_attrs_lab.backend_identity()
RETURNS integer
LANGUAGE sql
STABLE
PARALLEL RESTRICTED
AS $$
    SELECT pg_backend_pid()
$$;
```

This returns the executing backend's PID. Marking it `RESTRICTED` prevents it from running inside worker processes where backend-local identity would diverge from the leader's intended meaning.

This is an **intentionally conservative** lab example; in production, inspect exact semantics and catalog entries for all called built-ins on your server version.

### 28.3. RESTRICTED does not guarantee workers will still be used

If a `RESTRICTED` function must be evaluated per row prior to a filter or join that cannot validly or cheaply be deferred to the leader, PostgreSQL may choose **not to parallelize** that portion of the plan.

Never assume `RESTRICTED` always produces a "Parallel Scan followed by function after Gather" plan; the planner preserves semantics and costs both options.

## 29. PARALLEL UNSAFE

Declaring:

```sql
PARALLEL UNSAFE
```

means the function is unsafe for parallel mode, so **its presence in a query can force the planner into a sequential plan**.

Common examples:

- Executing `INSERT`, `UPDATE`, `DELETE`, or mutating database state.
- Calling `nextval()` and advancing sequences.
- Altering transaction state or backend configuration in ways unsafe across workers.
- Having side effects or dependencies incompatible with the parallel worker model.

### 29.1. Sequence example

Earlier we created:

```sql
SELECT function_attrs_lab.reserve_event_id('ORDER');
```

declared `VOLATILE STRICT PARALLEL UNSAFE`. If a large `SELECT` calls this function, do not expect PostgreSQL to invoke sequences inside parallel workers.

### 29.2. Data-writing function example

```sql
SELECT function_attrs_lab.set_product_price(10, 130.00);
```

Because it updates a table, it is `UNSAFE`. Even though PostgreSQL uses parallel scans for other read queries, never relabel a writing function `SAFE` just to see a `Gather` node.

### 29.3. Conservative UNSAFE default

For new functions whose dependencies haven't been audited yet, keeping the default `PARALLEL UNSAFE` is safer than guessing `SAFE`. Once verified as pure math and called across millions of rows, accurately labeling `SAFE` can unlock major speedups.

## 30. Volatility and parallel safety are independent dimensions

You cannot deduce:

```text
IMMUTABLE  => PARALLEL SAFE
STABLE     => PARALLEL RESTRICTED
VOLATILE   => PARALLEL UNSAFE
```

These inferences are **false**.

### 30.1. IMMUTABLE is not guaranteed SAFE

A function can produce deterministic outputs yet touch backend-local resources or worker-unsafe APIs. Volatility and parallel safety must be evaluated separately.

### 30.2. STABLE and PARALLEL SAFE

`lookup_price(product_id)` reads a regular table without side effects, so it is `STABLE PARALLEL SAFE` in our example. If it read a temporary table instead, its parallel label would change even though volatility stays `STABLE`.

### 30.3. VOLATILE does not automatically imply UNSAFE

A function can return varying values without accessing worker-prohibited resources. Thus volatility does not dictate parallel safety.

Still, **data-writing and sequence-advancing functions** are both `VOLATILE` and `UNSAFE` in the scenarios shown.

### 30.4. STRICT is also independent

`VOLATILE STRICT PARALLEL UNSAFE` is completely valid. `reserve_event_id(event_type)` demonstrates all three:

- `VOLATILE` due to sequence mutation.
- `STRICT` to avoid allocating an ID when `event_type` is NULL.
- `UNSAFE` due to sequence access.

## 31. Temporary tables: a classic case needing RESTRICTED

Suppose a session creates a temporary table for intermediate work:

```sql
CREATE TEMP TABLE session_discounts (
    product_id bigint PRIMARY KEY,
    discount_rate numeric NOT NULL
) ON COMMIT PRESERVE ROWS;

INSERT INTO session_discounts
VALUES (10, 0.10), (20, 0.05);
```

A function reading a temporary table depends on **session-local state**.

Example:

```sql
CREATE FUNCTION function_attrs_lab.session_discount(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
STRICT
PARALLEL RESTRICTED
AS $$
DECLARE
    result numeric;
BEGIN
    SELECT d.discount_rate
    INTO result
    FROM pg_temp.session_discounts AS d
    WHERE d.product_id = p_product_id;

    RETURN result;
END;
$$;
```

### 31.1. Why not PARALLEL SAFE?

Temporary tables are scoped to the local session/backend; parallel workers have restricted access to session-local temp state. Functions referencing temp tables must not run inside parallel workers.

### 31.2. Why is STABLE still reasonable?

The function only reads discount rows without writing. Within a single statement, its snapshot stays consistent per `STABLE` semantics, while still seeing temp table changes between statements.

### 31.3. Be careful with temporary table lifecycles

Referencing `pg_temp.session_discounts` assumes the calling session already created the temp table; otherwise execution fails at runtime. This is a lab example; production APIs must manage temporary table lifecycles and connection pooling carefully.

### 31.4. Connection pools reuse sessions

Never allow one request's temporary table to leak into a subsequent request or rely on temp state when clients switch connections. Define explicit cleanup and transaction contracts if per-request temp state is used.

## 32. Inspecting the pg_proc catalog

Attributes are stored in the PostgreSQL system catalog `pg_proc`.

Key columns:

| Catalog column | Values | Meaning |
| --- | --- | --- |
| `provolatile` | `i` / `s` / `v` | `IMMUTABLE` / `STABLE` / `VOLATILE` |
| `proisstrict` | `true` / `false` | `STRICT` vs. `CALLED ON NULL INPUT` |
| `proparallel` | `s` / `r` / `u` | `SAFE` / `RESTRICTED` / `UNSAFE` |
| `prolang` | OID | Execution language |
| `prosecdef` | boolean | `SECURITY DEFINER` vs. invoker |
| `procost` | number | Estimated call cost |
| `prorows` | number | Estimated rows for set-returning functions |
| `prokind` | char | Function/procedure/aggregate/window kind |

### 32.1. Practical query

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility,
    p.proisstrict AS is_strict,
    CASE p.proparallel
        WHEN 's' THEN 'SAFE'
        WHEN 'r' THEN 'RESTRICTED'
        WHEN 'u' THEN 'UNSAFE'
    END AS parallel_safety,
    p.procost AS estimated_cost
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'function_attrs_lab'
  AND p.prokind = 'f'
ORDER BY p.proname, function_signature::text;
```

Filtering `prokind='f'` focuses on **normal functions** created in the lab without mixing in procedures or aggregates.

### 32.2. Inspecting built-ins in the catalog

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    p.proisstrict,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid IN (
    'pg_catalog.now()'::regprocedure,
    'pg_catalog.clock_timestamp()'::regprocedure,
    'pg_catalog.random()'::regprocedure,
    'pg_catalog.pg_backend_pid()'::regprocedure
)
ORDER BY function_signature::text;
```

This reveals the **exact metadata on your running PostgreSQL version**, rather than guessing a built-in's parallel flag by name.

### 32.3. OIDs and signatures matter

Because a function name can be overloaded, specify exact signatures when inspecting or altering a function:

```sql
'function_attrs_lab.double_strict(numeric)'::regprocedure
```

to target the right overload.

## 33. Viewing function definitions

```sql
SELECT pg_get_functiondef(
    'function_attrs_lab.net_to_gross(numeric,numeric)'::regprocedure
) AS ddl;
```

`pg_get_functiondef` reconstructs the full `CREATE FUNCTION` DDL, displaying:

- Arguments and return type.
- Language.
- Volatility.
- Strictness.
- Parallel safety.
- Security, cost, and related options.
- Function body.

### 33.1. Reading the body alone is not enough

A short function might call another function, run dynamic SQL, or invoke an extension. Certifying parallel safety or volatility requires auditing **the entire execution path**, not just the top few lines.

### 33.2. information_schema

`information_schema` views expose SQL-standard routine metadata, whereas `pg_proc` directly exposes these three PostgreSQL-specific attribute groups.

## 34. ALTER FUNCTION: updating metadata on an existing function

PostgreSQL lets you alter attributes with `ALTER FUNCTION` without rewriting the body.

Example:

```sql
ALTER FUNCTION function_attrs_lab.add_numbers_default(
    integer, integer
)
IMMUTABLE
STRICT
PARALLEL SAFE;
```

After confirming addition has no state dependencies or side effects, we update all three attributes on the lab function.

### 34.1. Re-checking the catalog

```sql
SELECT
    p.oid::regprocedure,
    p.provolatile,
    p.proisstrict,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid =
    'function_attrs_lab.add_numbers_default(integer,integer)'
        ::regprocedure;
```

Expected metadata: `i`, `true`, `s`.

### 34.2. Changing labels does not alter function code

`ALTER FUNCTION` only updates metadata; it does not turn a table-reading function into pure math, eliminate side effects, or rewrite SQL. Audit correctness and dependencies before changing attributes.

### 34.3. What to check when a function backs an index

If an expression index or generated column depends on a function, changing its body, semantics, or volatility can invalidate persisted derived values. Depending on the change, you may need `REINDEX`, data recomputation, verification, and a rollout plan.

Never run `ALTER` on a label and assume existing index rows automatically recompute.

## 35. CREATE OR REPLACE FUNCTION and attribute changes

In migrations, `CREATE OR REPLACE FUNCTION` commonly updates bodies and metadata for compatible signatures.

```sql
CREATE OR REPLACE FUNCTION function_attrs_lab.net_to_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

### 35.1. Watch return types and function identity

PostgreSQL identifies functions by name and argument types. `CREATE OR REPLACE` cannot arbitrarily change return types. Incompatible signature changes require coordinated migrations, dependency updates, and privilege management.

### 35.2. Re-declare attributes explicitly on every replace

Never assume omitting attributes during a body replacement preserves previous flags as expected. Always review the deployed definition afterward to confirm volatility, strictness, and parallel flags match intent.

### 35.3. Never tweak labels just to make EXPLAIN look prettier

A fast query plan built on wrong metadata causes far worse correctness bugs than a slightly slower honest plan. Optimization must start from accurate semantics.

## 36. COST and ROWS: optimizer metadata separate from the three main attributes

PostgreSQL also provides:

```sql
COST <estimated_execution_cost>
ROWS <estimated_result_rows>
```

`COST` informs the planner of per-call expense. `ROWS` applies to set-returning functions.

Example:

```sql
CREATE FUNCTION function_attrs_lab.slowish_calculation(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
COST 10
AS $$
    SELECT x * x + sqrt(abs(x))
$$;
```

### 36.1. COST is not milliseconds

`COST` is a relative planner unit, not a promise that each call takes 10 ms.

### 36.2. COST does not fix wrong volatility

A cheap `VOLATILE` function is still `VOLATILE`. An expensive `IMMUTABLE` function is still semantically `IMMUTABLE`. The two metadata groups solve different problems.

### 36.3. Functions can be inlined

Eligible SQL-language functions can be inlined into the query by the planner. Never rely on occurrences in `EXPLAIN` to assume the body runs exactly N times.

## 37. EXPLAIN: observing impact without guessing call counts

Example:

```sql
EXPLAIN (VERBOSE)
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS constant_gross,
    function_attrs_lab.net_to_gross(
        s.quantity * s.unit_price,
        0.08
    ) AS gross_from_row
FROM function_attrs_lab.sales AS s;
```

The constant-argument call can be constant-folded, whereas the call referencing `s.quantity` and `s.unit_price` must evaluate against row data.

### 37.1. Comparing STABLE and VOLATILE conditions

```sql
EXPLAIN (VERBOSE)
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < now();

EXPLAIN (VERBOSE)
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < clock_timestamp();
```

Inspect:

- `Index Cond`.
- `Filter`.
- `Seq Scan` vs. `Index Scan`.
- Whether expressions remain function calls or fold to constants.

### 37.2. With ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.sales;
```

Inspect actual rows, loops, buffers, and execution time.

### 37.3. Never confuse EXPLAIN ANALYZE on SELECT with read-only inspection

`EXPLAIN ANALYZE` **actually executes the SQL statement**. If a `SELECT` calls a `VOLATILE` function that **writes data or advances sequences**, those side effects still happen.

Thus even `EXPLAIN ANALYZE SELECT function_attrs_lab.set_product_price(...)` is **not a harmless observation**. Never run it on production without confirming the function is side-effect-free.

## 38. Testing parallel plans

A candidate query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    SUM(function_attrs_lab.line_amount(quantity, unit_price))
FROM function_attrs_lab.sales;
```

On a four-row lab table, `Gather` will not appear. To experiment with larger volumes, create a separate larger test table.

### 38.1. Optional benchmark table creation

```sql
CREATE TABLE function_attrs_lab.large_sales AS
SELECT
    g.n AS sale_id,
    ((g.n % 5) + 1)::integer AS quantity,
    ((g.n % 1000) + 100)::numeric AS unit_price
FROM generate_series(1, 500000) AS g(n);

ANALYZE function_attrs_lab.large_sales;
```

Measure:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.large_sales;
```

This generates 500,000 rows—**run only in a test database** and account for disk, WAL, and CPU usage.

### 38.2. Suggested test settings inside a transaction

In a lab where you have permission:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 2;
SET LOCAL min_parallel_table_scan_size = '0';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.large_sales;

ROLLBACK;
```

These settings make parallel plans more likely to be picked, **without guaranteeing PostgreSQL will spawn workers**. Server limits, resource availability, query shape, and function parallel labels all matter.

### 38.3. Comparing with an UNSAFE function

Calls like `reserve_event_id()` or `set_product_price()` are unsafe. Never put side-effecting functions inside aggregate benchmarks just to demonstrate serial execution—they will **execute real side effects** and corrupt data or sequences.

To compare plans cleanly, create a separate pure-math `UNSAFE` function in the lab, noting that the label acts solely as a planner restriction:

```sql
CREATE FUNCTION function_attrs_lab.line_amount_conservative(
    quantity integer,
    unit_price numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL UNSAFE
AS $$
    SELECT quantity * unit_price
$$;
```

Test:

```sql
EXPLAIN
SELECT SUM(
    function_attrs_lab.line_amount_conservative(
        quantity,
        unit_price
    )
)
FROM function_attrs_lab.large_sales;
```

This simulates a **conservative declaration**, not a genuinely dangerous function. Once the planner sees an `UNSAFE` call in the query, parallel execution is suppressed per the contract.

### 38.4. Never force parallel settings on production

The `SET LOCAL` parameters above are strictly for lab experimentation; never tune global production cost parameters just to force more parallel nodes in plans.

## 39. Why must table-reading functions inspect the table kind?

The function:

```sql
SELECT unit_price
FROM function_attrs_lab.product_prices
WHERE product_id = p_product_id
```

reads only a regular table with no temp or session-local state, making `STABLE PARALLEL SAFE` appropriate here.

Meanwhile, another function:

```sql
SELECT discount_rate
FROM pg_temp.session_discounts
WHERE product_id = p_product_id
```

reads a session temporary table, so it must not be marked `SAFE`. Simply "only doing a `SELECT`" never proves parallel safety; **the data source and session context** are decisive.

### 39.1. Unlogged tables and foreign tables

Different relation types and external wrappers carry distinct semantics. If a function touches FDWs, extensions, or special relations, audit actual execution paths and parallel support rather than assuming `SELECT` implies `SAFE`.

### 39.2. Dynamic SQL

A PL/pgSQL function executing `EXECUTE dynamic_sql` can run arbitrary queries depending on inputs. Unless every possible execution path is strictly controlled, labeling it `IMMUTABLE` or `PARALLEL SAFE` is high risk.

## 40. Functions calling other functions: transitivity of dependencies

Suppose:

```sql
CREATE FUNCTION function_attrs_lab.gross_with_factor(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT function_attrs_lab.net_to_gross(
        net_amount, tax_rate
    )
$$;
```

Because `net_to_gross` is pure math, the wrapper legitimately inherits all three labels.

If we change the wrapper body to:

```sql
-- Idea not for production:
-- SELECT function_attrs_lab.net_to_gross(
--     net_amount,
--     current_setting('app.tax_rate')::numeric
-- );
```

the wrapper is no longer `IMMUTABLE` because `tax_rate` comes from mutable state, even though the inner function is immutable.

### 40.1. Checking child function metadata in the catalog

For identifiable dependencies, inspect:

```sql
SELECT
    p.oid::regprocedure,
    p.provolatile,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid =
    'function_attrs_lab.net_to_gross(numeric,numeric)'
        ::regprocedure;
```

For extensions or native code, consult documentation and real behavior beyond catalog flags alone.

### 40.2. PostgreSQL will not automatically "fix" a mislabeled wrapper

Never expect the planner to detect a `SAFE` wrapper calling an `UNSAFE` child and downgrade it silently. Accurate classification is the responsibility of the author and code review.

## 41. Volatility is not transaction isolation

Compare:

| Concept | What it governs |
| --- | --- |
| `IMMUTABLE`/`STABLE`/`VOLATILE` | Stability of function outputs/behavior for the optimizer and internal SQL snapshots |
| `READ COMMITTED` | Snapshot typically refreshes per statement |
| `REPEATABLE READ` | Transaction-wide snapshot stability per PostgreSQL semantics |
| `SERIALIZABLE` | Stronger isolation with potential serialization failures |
| `SELECT ... FOR UPDATE` | Row-level locking for coordinated updates |

A `STABLE` function reading a price table does not block other transactions from updating prices; an `IMMUTABLE` math function does not create stronger transaction isolation.

## 42. Volatility is not Java thread safety

In Java, "thread-safe" means safe concurrent use across threads without data races or state corruption.

In PostgreSQL:

- `PARALLEL SAFE` means safe to run inside PostgreSQL parallel worker processes when eligible.
- `IMMUTABLE` means output never depends on mutable state for identical arguments.
- `STRICT` means body execution can be skipped when any argument is NULL.

Never map Java class thread-safety definitions directly onto PostgreSQL function attributes.

### 42.1. PostgreSQL parallel workers are OS processes

Parallel queries run across separate backend worker processes with specific rules for snapshots, backend-local state, and shared memory—not Java threads sharing heap objects inside one process.

## 43. SECURITY DEFINER/INVOKER is another dimension

PostgreSQL provides:

```sql
SECURITY INVOKER
SECURITY DEFINER
```

to control which role's privileges govern execution.

These are **independent** of volatility, `STRICT`, and parallel safety.

### 43.1. SECURITY DEFINER does not imply IMMUTABLE

A function running with owner privileges can still read tables, modify rows, advance sequences, or read session settings. Classify volatility and parallel safety by actual behavior, not security mode.

### 43.2. Avoid search_path injection

For `SECURITY DEFINER` functions, enforce schema qualification, a pinned safe `search_path`, and tight `EXECUTE` grants. Marking a function `IMMUTABLE` offers zero protection against `search_path` hijacking or SQL injection.

### 43.3. Never use SECURITY DEFINER for optimization

A pure arithmetic function needs no elevated privileges via `SECURITY DEFINER`. Security mode is a separate authorization decision.

## 44. Functions in WHERE, JOIN, ORDER BY, and re-evaluation

Example SQL:

```sql
SELECT
    s.sale_id,
    function_attrs_lab.line_amount(
        s.quantity, s.unit_price
    ) AS total
FROM function_attrs_lab.sales AS s
WHERE function_attrs_lab.line_amount(
    s.quantity, s.unit_price
) > 100
ORDER BY total DESC;
```

### 44.1. Mentions in SQL do not equal body execution counts

The planner can:

- Inline eligible SQL functions.
- Eliminate unused expressions.
- Reorder evaluation per volatility and SQL semantics.
- Compute expressions at different plan stages.

Never assume "appearing twice in the SQL means the function runs exactly twice per row."

### 44.2. VOLATILE functions in ORDER BY

`ORDER BY random()` produces random ordering per evaluation, incurs sort overhead, and breaks stable pagination.

```sql
SELECT sale_id
FROM function_attrs_lab.sales
ORDER BY random()
LIMIT 2;
```

For consistent pagination, always sort by deterministic columns with a unique tiebreaker instead of a volatile random key.

### 44.3. Logical operators do not guarantee strict short-circuiting

Never write:

```sql
WHERE condition_a
  AND dangerous_function(...)
```

assuming PostgreSQL **always evaluates `condition_a` first** and skips the function otherwise. The SQL planner can reorder predicates freely when semantics permit.

To guard against errors like division by zero in expressions, use `CASE` or `NULLIF`, or handle them inside the function—never rely on `AND`/`OR` evaluation order.

## 45. Attribute selection checklist

When creating a new function:

### 45.1. Step 1 — Classify volatility

Ask:

- Does the function write data, advance sequences, or cause side effects? → **`VOLATILE`**.
- Does it read `clock_timestamp()`, `random()`, or state mutable within a statement? → **`VOLATILE`**.
- Does it read regular tables, session settings, or transaction/statement timestamps consistently within one query? → consider **`STABLE`**.
- Is it pure over its inputs with zero mutable state dependencies? → consider **`IMMUTABLE`**.

### 45.2. Step 2 — Decide STRICT

Ask:

- Whenever **any input is NULL**, should the result always be NULL without running the body? → **`STRICT`**.
- Does the function handle, default, or classify NULLs with custom logic? → **`CALLED ON NULL INPUT`**.
- Must side effects still run even on NULL inputs? → do not blindly pick `STRICT`.

### 45.3. Step 3 — Decide parallel safety

Ask:

- Does it perform `UPDATE`/`INSERT`/`DELETE`, touch sequences, or alter transaction/config state? → **`UNSAFE`**.
- Does it touch temp tables, cursors, or backend-local state not shared with workers? → **`RESTRICTED`**.
- Does it read only safe relations, call only safe functions, and cause no state mutations? → may be **`SAFE`**.
- Unsure about external extensions or native dependencies? → keep default **`UNSAFE`** until verified.

### 45.4. Step 4 — Measure, don't just guess

- Query `pg_proc` to verify stored metadata.
- Test normal and NULL inputs.
- Test state changes between statements for `STABLE` functions.
- Test prepared plans whenever constant folding applies.
- Check `EXPLAIN` for expression indexes and parallel scans.
- Verify both correctness and latency on representative data.

## 46. Summary examples table

| Function type | Volatility | Null-input | Parallel | Reason |
| --- | --- | --- | --- | --- |
| Pure arithmetic `x * y` | `IMMUTABLE` | `STRICT` if NULL → NULL | `SAFE` | Depends solely on arguments |
| `COALESCE(x,0)` | `IMMUTABLE` | `CALLED ON NULL INPUT` | `SAFE` | Must process NULL inside body |
| Lookup price from regular table | `STABLE` | `STRICT` if missing ID returns NULL | `SAFE` if dependencies are safe | Table rows can change between statements |
| Reading `now()` | `STABLE` | N/A if no args | Depends on dependencies; check catalog | Transaction timestamp |
| Reading `clock_timestamp()` | `VOLATILE` | N/A if no args | Check catalog | Live wall clock changes |
| `random()` | `VOLATILE` | N/A if no args | Check catalog | Output varies |
| `nextval()` | `VOLATILE` | Depends on wrapper | `UNSAFE` | Mutates sequence state |
| Table `UPDATE` in function | `VOLATILE` | Depends on business rules | `UNSAFE` | Modifies database state |
| Reading temporary table | `STABLE` if read-only within statement | Depends on inputs | `RESTRICTED` | Session-local state |
| Wrapper reading GUC | `STABLE` in suitable models | Depends on inputs | Evaluate separately | Depends on config/session |
| Function with no attributes specified | `VOLATILE` | `CALLED ON NULL INPUT` | `UNSAFE` | Conservative defaults |

This table serves as an **analytical guide**, never a substitute for auditing the body, relation types, nested calls, and running PostgreSQL catalog.

## 47. Common anti-patterns

| Anti-pattern | Risk | Right approach |
| --- | --- | --- |
| Marking `now()` as `IMMUTABLE` | Folded/cached stale timestamps | `STABLE` matching time semantics |
| Marking table lookups `IMMUTABLE` | Stale cached or indexed values | `STABLE` for statement-level reads |
| Marking an `UPDATE` function `STABLE` | Invalid side effects; runtime SQL errors | `VOLATILE` + `UNSAFE` |
| Leaving pure math as `VOLATILE` | Misses valid optimizations | Evaluate and mark `IMMUTABLE` |
| Using `STRICT` with `COALESCE(x,0)` | Returns NULL early instead of 0 | `CALLED ON NULL INPUT` |
| Assuming `STRICT` means `NOT NULL` output | Returning NULL on `denominator=0` still happens | Audit body and domain rules |
| Relying on `STRICT` to validate errors | Silently returns NULL instead of raising errors | Validate inputs explicitly |
| Marking a `nextval` wrapper `SAFE` | Unsafe inside parallel workers | `UNSAFE` |
| Marking temp-table reads `SAFE` | Workers lack leader's temp state | `RESTRICTED` |
| Thinking `IMMUTABLE` guarantees `SAFE` | Two independent contracts | Audit parallel safety separately |
| Thinking `VOLATILE` always means `UNSAFE` | Not universally true | Check actual side effects and dependencies |
| Thinking `SAFE` guarantees `Gather` | Parallelism depends on planner and workload | Inspect `EXPLAIN` on representative data |
| Thinking `RESTRICTED` always stays parallel | Planner may avoid parallelizing if leader deferral fails | Check actual plan |
| Faking labels to force index creation | Corrupt index semantics | Only use genuinely `IMMUTABLE` functions |
| Using `now()` in partial index predicates | Time-drifting condition | Index `sold_at` + query bounds |
| Using volatile functions in generated columns | Invalid persisted derived data | Only valid immutable expressions |
| Putting side effects in `WHERE` expecting N calls | Planner may alter evaluation | Use explicit DML workflows |
| Treating `COST` as milliseconds | Relative planner cost unit | Measure with `EXPLAIN ANALYZE` |
| Using `EXPLAIN ANALYZE` to "peek" at write functions | Executes real side effects | Plain `EXPLAIN` or lab rollback when appropriate |
| Calling sequence then `ROLLBACK` to "return ID" | Sequence stays incremented | Accept sequence gaps |
| Dropping attributes during `CREATE OR REPLACE` | Wrong flags after migration | Check `pg_proc`/`pg_get_functiondef` |
| Expecting generic plans to pick up new GUCs on fake `IMMUTABLE` | Stale folded constants | Use `STABLE` or pass explicit args |
| Using `SECURITY DEFINER` to alter plans | Unnecessary privilege escalation | Keep security separate |
| Marking unchecked dynamic SQL `SAFE` | Execution path may be unsafe | Audit every dynamic branch |
| Treating SQL NULL as `FALSE` by default | Violates three-valued logic | Define explicit policies |

## 48. PostgreSQL practice exercises

Run exercises on schema `function_attrs_lab`. For tasks modifying data, wrap in `BEGIN ... ROLLBACK` to restore sample state. Parallel/`EXPLAIN` tasks use the optional large table to produce observable plans.

1. **Concepts:** state the difference between volatility, `STRICT`, and parallel safety in three independent sentences.
2. **Defaults:** create an addition function with no attributes specified and inspect its default metadata in `pg_proc`.
3. **Classification:** can an addition function over `numeric` args be `IMMUTABLE`? Why?
4. **STABLE:** should a function reading prices from `product_prices` be `STABLE` or `IMMUTABLE`?
5. **VOLATILE:** explain why a function calling `nextval()` must be `VOLATILE`.
6. **Wall clock:** compare `now()` and `clock_timestamp()` in a single `SELECT`.
7. **Statement time:** compare `now()` with `statement_timestamp()` across two statements in one transaction.
8. **Clock demo:** use a brief `pg_sleep` in the lab to observe timestamps advancing.
9. **Pure function:** create `net_to_gross(numeric,numeric) IMMUTABLE STRICT PARALLEL SAFE`.
10. **Determinism test:** call `net_to_gross` repeatedly with identical arguments.
11. **Strict NULL:** call `net_to_gross` with NULL `net_amount` and `tax_rate = 0.08`.
12. **Second arg NULL:** call `net_to_gross` with `amount = 100` and `tax_rate = NULL`.
13. **NULL policy:** explain why `COALESCE(x,0)` should not be `STRICT`.
14. **Default on NULL:** write `zero_if_null` and verify it returns 0 for NULL.
15. **Strict boolean:** compare `is_positive_strict(NULL)` and `is_positive_or_false(NULL)`.
16. **NULL output:** analyze `safe_ratio(10,0)` and show that `STRICT` does not prevent NULL outputs.
17. **Zero denominator:** design a `safe_ratio` variant raising an error on 0 denominator—how should `STRICT` be set?
18. **Side effects:** create `reserve_event_id(event_type)` using a sequence as `VOLATILE STRICT UNSAFE`.
19. **NULL side effect:** explain why `reserve_event_id(NULL)` does not consume a sequence value.
20. **Sequence rollback:** call `nextval` inside a transaction and roll back; verify the sequence does not rewind.
21. **Table lookup:** write `lookup_price(bigint)` and test updating prices between statements inside a lab transaction.
22. **Snapshots:** compare snapshot semantics of a `STABLE` SQL function versus a `VOLATILE` function.
23. **Mislabeling IMMUTABLE:** explain the bug when a table lookup is marked `IMMUTABLE`.
24. **GUC:** create the session factor demo and explain why `current_setting` is not immutable.
25. **Prepared plans:** describe how a cached plan retains stale values if a GUC-dependent function is mislabeled `IMMUTABLE`.
26. **Explicit argument:** refactor the config dependency into an explicit `tax_rate` argument for an immutable calculation.
27. **Expression index:** create `normalize_sku` and an index on `normalize_sku(sku)`.
28. **Index semantics:** why does an expression index reject a function that is only `STABLE`?
29. **Collation drift:** when OS/ICU collation rules change, what maintenance may normalization indexes require?
30. **Partial index:** why is `WHERE sold_at >= now() - interval '7 days'` invalid in an index predicate?
31. **Alternative index:** propose a regular B-tree on `sold_at` plus a `WHERE` query using `now()` for the last 7 days.
32. **Generated column:** create `sku_inputs` with a stored generated `normalized_sku` backed by an immutable function.
33. **CHECK constraints:** why shouldn't you use table lookups or `now()` as dynamic rules inside `CHECK`?
34. **Volatile DML:** write `set_product_price`, identifying its volatility and parallel classification.
35. **Price update:** execute `set_product_price` inside a lab transaction and roll back.
36. **Parallel SAFE:** explain why `line_amount(quantity,unit_price)` qualifies as `SAFE`.
37. **Parallel RESTRICTED:** explain why reading temp tables or session state requires `RESTRICTED`.
38. **Backend identity:** create `backend_identity()` and justify its `PARALLEL RESTRICTED` label.
39. **Parallel UNSAFE:** list three operations that require `UNSAFE`.
40. **Independence:** give one example of a `STABLE SAFE` function and one of a `VOLATILE UNSAFE` function.
41. **More independence:** explain why `VOLATILE` does not automatically imply `UNSAFE` for every function.
42. **Nested calls:** if a wrapper calls an immutable child while passing a GUC value, is the wrapper still immutable?
43. **Catalog:** query `pg_proc.provolatile,proisstrict,proparallel` across the entire lab schema.
44. **Built-ins:** inspect metadata for `now`, `clock_timestamp`, `random`, and `pg_backend_pid` on your server.
45. **Signatures:** distinguish `f(integer)` and `f(numeric)`; why must you cast when testing NULL?
46. **Function DDL:** use `pg_get_functiondef` to inspect full declarations.
47. **ALTER FUNCTION:** alter `add_numbers_default` to `IMMUTABLE STRICT PARALLEL SAFE` and verify in the catalog.
48. **Migrations:** explain why `ALTER FUNCTION` does not recompute existing indexed values.
49. **EXPLAIN:** compare `net_to_gross` with constant arguments versus column references.
50. **WHERE:** compare `EXPLAIN` for `WHERE sold_at<now()` versus `WHERE sold_at<clock_timestamp()`.
51. **Index Cond/Filter:** explain the difference when a volatile expression cannot serve as a scan boundary constant.
52. **Benchmark:** populate `large_sales` with 500,000 rows in the lab and run `EXPLAIN ANALYZE BUFFERS` on `SUM(line_amount(...))`.
53. **Parallel plan:** adjust `SET LOCAL` parallel costs inside a lab transaction and observe whether `Gather` appears.
54. **Parallel conservatism:** compare `line_amount` (`SAFE`) against `line_amount_conservative` (`UNSAFE`).
55. **No Gather:** explain why a four-row table runs serially even with a `SAFE` function.
56. **COST:** add `COST` to a function and distinguish it from runtime in milliseconds.
57. **Inlining:** why doesn't an SQL function always appear as its own node in `EXPLAIN`?
58. **Concurrency:** does a `STABLE` table-lookup function lock rows against updates by concurrent transactions?
59. **Java:** explain why prepared/cached plans in JDBC drivers amplify the danger of fake `IMMUTABLE` declarations.
60. **Evaluation order:** why isn't placing a `VOLATILE` side-effecting function in `WHERE` guaranteed to run once per row?
61. **Security:** `SECURITY DEFINER` governs permissions rather than guaranteeing `IMMUTABLE`/`SAFE`—true or false?
62. **Review:** build a review checklist for volatility, strictness, and parallel safety on a PL/pgSQL function containing dynamic SQL.
63. **Edge NULL:** design a function that treats `quantity=NULL` as an error instead of defaulting to 1; choose `STRICT` or explicit validation?
64. **Temp tables:** describe temp table lifecycles under connection pooling and the risks for `RESTRICTED` functions.
65. **Regression tests:** design tests covering GUC updates, price table `UPDATE`s, NULL inputs, and `EXPLAIN` before and after metadata fixes.
66. **Comprehensive scenario:** a sales feature needs pure subtotal math, current price lookup, order ID allocation, and session discount lookup; classify all three attributes for each function and justify every choice.

## 49. Pre-production function review checklist

Before approving a `CREATE FUNCTION`/`ALTER FUNCTION` migration:

1. **Do identical inputs always yield identical outputs regardless of time or database state?**
2. **Does the function call `random`, `now`, `clock_timestamp`, `current_setting`, `nextval`, or read tables?**
3. **If reading tables, are statement snapshot semantics and concurrent updates accounted for?**
4. **Are there unaudited PL/pgSQL dynamic SQL statements, extensions, native calls, or child functions?**
5. **Is the default `VOLATILE` accurate or overly conservative?**
6. **Is `STRICT` genuinely valid whenever any single argument is NULL?**
7. **Is there a NULL→0/`FALSE`/default rule that `STRICT` would inadvertently bypass?**
8. **Can outputs still be NULL even when all inputs are non-null?**
9. **Must any side effects still execute when an argument is NULL?**
10. **Does the function write data, advance sequences, or mutate transaction/config state?**
11. **Does it read temporary tables, cursors, or backend-local state?**
12. **Are all child functions and referenced relations genuinely parallel-safe?**
13. **Was `SAFE` added just to force parallel plans without verification?**
14. **Do any expression indexes, generated columns, or partial indexes depend on this function?**
15. **If the function body changed, are `REINDEX` or recomputations required for persisted values?**
16. **Could prepared statements or cached plans hold stale results from misclassified volatility?**
17. **Do `COST`/`ROWS` reflect real workloads reasonably?**
18. **Are `SECURITY DEFINER`/`INVOKER` and `search_path` configured safely?**
19. **Do `pg_proc` and `pg_get_functiondef` match expected metadata after deployment?**
20. **Have correctness, `EXPLAIN`, NULL edge cases, concurrent mutations, and rollback plans been tested?**

## 50. Summary

These three attribute groups define **the function's contract with PostgreSQL's planner and executor**:

```text
VOLATILITY
    IMMUTABLE -> Same args, output never changes with state or time.
                 Eligible for constant folding and expression indexes.
    STABLE    -> Same args, consistent within a single SQL statement.
                 Fits statement/transaction time and read-only lookups.
    VOLATILE  -> Output may change or side effects may occur.
                 Stability-based optimizations are forbidden.

NULL-INPUT
    STRICT / RETURNS NULL ON NULL INPUT
              -> Any arg is NULL: return NULL, skip body.
    CALLED ON NULL INPUT
              -> Body executes and handles NULL explicitly if needed.

PARALLEL SAFETY
    SAFE       -> Safe to execute inside parallel workers.
    RESTRICTED -> Must run only in the parallel group leader.
    UNSAFE     -> Unsafe for parallel mode; restricts parallel plans.
```

Most important rules:

- **Never declare attributes for hoped-for performance.** Match declarations strictly to actual function behavior.
- **`IMMUTABLE`** fits pure math on arguments; **`STABLE`** fits values stable within a statement yet mutable between statements; **`VOLATILE`** fits `random()`, live clocks, sequences, and side effects.
- **`STRICT`** is a shortcut for NULL inputs—it never guarantees non-null outputs for non-null inputs.
- **`PARALLEL SAFE`/`RESTRICTED`/`UNSAFE`** are independent of volatility and strictness. Temporary tables and backend state require leader execution, while data writes and sequences are unsafe.
- **Wrong `IMMUTABLE` declarations are dangerous for prepared plans, expression indexes, generated columns, and partial indexes.** Never "fix" index creation errors with dishonest metadata.
- **Table-reading functions can be `STABLE`, not `IMMUTABLE`**; `STABLE` neither acquires locks nor upgrades isolation levels.
- **Security, `COST`, `ROWS`, and transaction isolation are separate dimensions.** Never extrapolate one attribute across unrelated dimensions.
- **Use `pg_proc` to audit metadata**, `pg_get_functiondef` to inspect DDL, and `EXPLAIN (ANALYZE, BUFFERS)` safely to observe planner behavior.
- **When `SELECT` calls a side-effecting function, `EXPLAIN ANALYZE` executes those side effects.** Never run data-writing or sequence-advancing examples on production just to inspect a plan.

When volatility, `STRICT`, and parallel safety are declared accurately, you enable PostgreSQL to **apply every safe optimization** while **never making dangerous assumptions about outputs, NULLs, or parallel worker execution**. That is the foundation for writing reliable, predictable SQL and PL/pgSQL functions at PostgreSQL scale.
