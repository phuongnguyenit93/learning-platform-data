# Optimizing Parameterized Queries Under Skewed Data in PostgreSQL

## 1. One SQL Query, Two Parameter Values, Very Different Execution Needs

Suppose a SaaS application serves multiple customers (*tenants*) from a shared orders table:

```sql
SELECT order_id, tenant_id, status, amount, payload
FROM orders
WHERE tenant_id = $1;
```

The SQL text stays identical; the application changes only `$1`.

- With `$1 = 1`, the largest tenant owns **225,000 orders**, roughly **90%** of the table.
- With `$1 = 999`, a small tenant owns roughly **25 orders**, about **0.01%** of the table.

When a query must retrieve most of the table for tenant 1, a **sequential scan** can beat hundreds of thousands of heap reads via an index. Yet for tenant 999, an **index scan** beats scanning 250,000 rows by orders of magnitude.

What happens when the application uses a **prepared statement** or JDBC parameter binding? PostgreSQL can choose between:

- **Custom plan**: planned specifically for the **parameter values of that execution**.
- **Generic plan**: a reusable plan shared across **arbitrary parameter values**, not tailored to any single execution's values.

When data is heavily **skewed** (*skewed distribution*), a generic plan may favor small tenants while hurting the giant tenant, or vice versa.

```text
                    Same SQL with $1
                             |
                  +----------+----------+
                  |                     |
             $1 = 1 (HOT)          $1 = 999 (COLD)
             ~90% of table         ~0.01% of table
                  |                     |
            Seq Scan may          Index Scan may
            be optimal            be optimal
                  |                     |
                  +----------+----------+
                             |
                  Shared generic plan
                     hard to optimize
                        for both
```

**Topic of this lesson:** how to diagnose, measure, and optimize parameterized queries in PostgreSQL **when parameter values have vastly different frequencies**.

> **Key takeaway:** Neither “the SQL has an index” nor “the SQL uses bind parameters” guarantees stable performance. You must understand **parameter values, distribution statistics, custom vs generic plans, and how the application executes prepared statements**.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain why **data skew** causes executions of the exact same SQL to need different access paths.
2. Distinguish **parameter binding**, **server-side prepared statements**, **custom plans**, and **generic plans**.
3. Understand how PostgreSQL decides between generic and custom plans under `plan_cache_mode = auto`.
4. Use `PREPARE` / `EXECUTE` and `EXPLAIN (ANALYZE, BUFFERS) EXECUTE` to reproduce skew issues.
5. Use `plan_cache_mode = force_custom_plan` and `force_generic_plan` for controlled comparisons.
6. Inspect `generic_plans` / `custom_plans` counters in `pg_prepared_statements` where supported.
7. Read `pg_stats`: most common values, frequencies, histograms, `n_distinct`, and correlation.
8. Improve estimates with `ANALYZE`, statistics targets, and extended statistics where appropriate.
9. Analyze standard, composite, partial, and covering indexes for parameterized queries.
10. Understand why a generic plan may **fail to use a partial index** when its predicate depends on an unknown parameter.
11. Handle optional filters (`OR $1 IS NULL`), `IN`, `ANY`, time ranges, and `LIMIT`.
12. Design and benchmark Java/JDBC apps without sacrificing parameter binding or SQL safety.
13. Recognize limits of partition pruning, `pg_stat_statements`, and plan-forcing knobs.
14. Choose practical fixes driven by measurement rather than applying one global trick to the whole database.

## 3. Four Easily Confused Concepts: SQL Parameters, `PREPARE`, Custom Plans, and Generic Plans

### 3.1. Parameterized Queries

A query with **placeholders**:

```sql
SELECT *
FROM app.orders
WHERE tenant_id = $1;
```

`$1` denotes a value supplied separately from the SQL text. In Java applications, JDBC uses `?` placeholders:

```java
PreparedStatement ps = connection.prepareStatement(
    "SELECT order_id, amount FROM app.orders WHERE tenant_id = ?"
);
ps.setInt(1, tenantId);
```

The PostgreSQL driver sends the statement and bound values via the wire protocol. This is good practice to:

- Separate data from SQL syntax.
- Prevent SQL injection compared to string concatenation.
- Convey explicit data types.
- Reuse a single SQL shape.
- Leverage server-side prepared execution under appropriate conditions.

**Parameterization does not guarantee a single cached plan.** Driver and server execution rules govern whether a server-side prepared statement is created and whether a custom or generic plan runs.

### 3.2. PostgreSQL SQL-Level `PREPARE`

```sql
PREPARE find_orders(integer) AS
SELECT order_id, amount
FROM app.orders
WHERE tenant_id = $1;
```

Then:

```sql
EXECUTE find_orders(1);
EXECUTE find_orders(999);
DEALLOCATE find_orders;
```

`PREPARE` registers a prepared statement **within the current PostgreSQL session**. It does not create a global query shared across all sessions or databases.

### 3.3. Custom Plan

A **custom plan** is built for a single execution using that execution's concrete parameter values.

Example:

```text
EXECUTE find_orders(1)
  -> planner sees tenant_id=1 when choosing access path
  -> can estimate ~225,000 rows

EXECUTE find_orders(999)
  -> planner sees tenant_id=999
  -> can estimate ~25 rows
```

Custom plans exploit per-parameter selectivity differences, at the cost of paying planning overhead on each execution.

### 3.4. Generic Plan

A **generic plan** is chosen without knowing the concrete parameter values of individual `EXECUTE` calls.

```text
PREPARE find_orders(integer)

Generic plan:
  WHERE tenant_id = $1
  based on average parameter selectivity estimates

EXECUTE find_orders(1)   -> uses the same plan shape
EXECUTE find_orders(999) -> uses the same plan shape
```

Generic plans reduce planning overhead on high-frequency SQL, yet under severe skew **a single access path struggles to fit every value well**.

### 3.5. A Generic Plan Does Not Ignore Parameters

Parameters are still passed and evaluated accurately at runtime. A generic plan never turns:

```sql
WHERE tenant_id = $1
```

into skipping the `WHERE` filter.

The difference lies in **choosing the plan shape at planning time**, not whether SQL applies the filter during execution.

## 4. What Is Skew?

A column has a skewed distribution when value frequencies **differ dramatically**.

Example:

| `tenant_id` | Order Count | Share of Table |
| ---: | ---: | ---: |
| 1 | 225,000 | 90% |
| 2 | ~25 | ~0.01% |
| 3 | ~25 | ~0.01% |
| 999 | ~25 | ~0.01% |
| Remaining tenants | ~25 per tenant | Remainder |

Knowing only “there are 1,001 tenants” and assuming an average of ~250 orders each is wildly wrong:

- Tenant 1: 225,000 rows—roughly **900×** the 250 average.
- Small tenants: ~25 rows—roughly **10× fewer** than 250.

This skew affects:

- `WHERE tenant_id = ?`.
- Joins between tenants and orders.
- `ORDER BY ... LIMIT` per tenant.
- `COUNT`/`SUM` aggregations.
- Batched updates per tenant.
- Index scan vs bitmap/seq scan choices.
- Cache utilization and CPU.
- Network payload returned to the app.

### 4.1. Skewed Frequencies Are Not Corrupt Data

Skew is usually natural business reality:

- One seller lists millions of products; most sellers list dozens.
- Status `ACTIVE` covers 99% of rows; `FAILED` covers 1%.
- One region accounts for most orders.
- An enterprise tenant emits orders of magnitude more events than individual accounts.
- Today's logs dwarf historical days.

The fix is never “artificially flatten the data,” but **designing access paths, statistics, and planning behavior to handle the real distribution**.

### 4.2. Skew Shifts Over Time

A small tenant can grow rapidly. A flash sale can push `status = 'PENDING'` from 2% to 70%.

Revisit statistics and performance periodically; conclusions from old distributions go stale.

## 5. Building a 250,000-Row Skewed Lab Dataset

All SQL examples use schema `skew_lab` in a **practice database**. Never run create/seed scripts on production.

### 5.1. Create Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS skew_lab;

CREATE TABLE skew_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('DONE', 'PENDING', 'FAILED')),
    created_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL,
    payload text NOT NULL
);
```

Design choices:

- `tenant_id` identifies the tenant.
- `status` has a distribution **correlated** with `tenant_id`, allowing multi-column statistics exploration.
- `created_at` supports latest-order queries.
- `payload` widens rows so heap fetches carry realistic cost.
- `order_id` gets a B-tree `PRIMARY KEY` index automatically.

### 5.2. Generate Heavily Skewed Data

```sql
INSERT INTO skew_lab.orders
    (tenant_id, status, created_at, amount, payload)
SELECT
    CASE
        WHEN g <= 225000 THEN 1
        ELSE 2 + ((g - 225001) % 1000)
    END AS tenant_id,
    CASE
        WHEN g <= 225000 THEN
            CASE
                WHEN g % 100 = 0 THEN 'FAILED'
                WHEN g % 50  = 0 THEN 'PENDING'
                ELSE 'DONE'
            END
        ELSE
            CASE
                WHEN g % 7 = 0 THEN 'FAILED'
                WHEN g % 3 = 0 THEN 'DONE'
                ELSE 'PENDING'
            END
    END AS status,
    timestamptz '2025-01-01 00:00:00+00'
        + g * interval '1 minute' AS created_at,
    ((g * 17) % 100000)::numeric / 100 AS amount,
    repeat('order-payload-', 8) || lpad(g::text, 7, '0')
FROM generate_series(1, 250000) AS s(g);
```

Dataset shape:

- First 225,000 rows belong to tenant 1.
- Remaining 25,000 rows split evenly across 1,000 tenants (`2` to `1001`), **25 rows each**.
- Within tenant 1, `DONE` dominates.
- Within small tenants, `PENDING` is relatively common.

This extreme skew is intentional so planner differences stand out clearly.

### 5.3. Update Statistics

```sql
ANALYZE skew_lab.orders;
```

Without fresh statistics, comparing custom vs generic plans gets muddled by stale table estimates.

### 5.4. Verify Distribution

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS hot_orders,
    COUNT(*) FILTER (WHERE tenant_id = 999) AS cold_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE tenant_id = 1)
        / NULLIF(COUNT(*), 0),
        2
    ) AS hot_percent
FROM skew_lab.orders;
```

Expected output:

| `all_orders` | `hot_orders` | `cold_orders` | `hot_percent` |
| ---: | ---: | ---: | ---: |
| 250000 | 225000 | 25 | 90.00 |

Status distribution:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count
FROM skew_lab.orders
WHERE tenant_id IN (1, 2, 999)
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

This dataset lets us study both **single-column skew** and **multi-column correlation**.

### 5.5. Create an Index on `tenant_id`

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);

ANALYZE skew_lab.orders;
```

This index gives the planner choices among:

- `Seq Scan`.
- `Index Scan`.
- `Bitmap Index Scan + Bitmap Heap Scan`.

## 6. Test Two Literals Before Introducing Parameters

Same query shape, passing values **directly as SQL literals in the lab** so the planner can estimate from concrete values.

### 6.1. Hot Tenant

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 1;
```

Because ~90% of the table matches, an illustrative plan might be:

```text
Seq Scan on orders
  Filter: (tenant_id = 1)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

Reading most of the heap sequentially can be cheaper than hundreds of thousands of index probes and heap fetches.

### 6.2. Cold Tenant

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 999;
```

Illustrative plan:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = 999)
  Buffers: shared hit=... read=...
```

Only 25 rows out of 250,000 need reading, so the index saves massive I/O.

### 6.3. These Are Illustrations, Not Guaranteed Plans

PostgreSQL **may pick different plans** depending on:

- Version.
- Cache and storage speed.
- Page count / tuple width.
- Statistics and physical correlation.
- Existing indexes.
- Cost settings.
- Visibility map state.
- `SELECT` columns and predicates.

A `Bitmap Heap Scan` on either query can also be completely sensible under some configurations.

What matters is understanding **why** the planner priced that path cheapest, not forcing output to match a screenshot.

## 7. Parameter Binding Does Not Automatically Force a Generic Plan

This is widely misunderstood in application code.

Java query:

```java
String sql = """
    SELECT order_id, tenant_id, status, amount, payload
    FROM skew_lab.orders
    WHERE tenant_id = ?
    """;

PreparedStatement ps = connection.prepareStatement(sql);
ps.setInt(1, tenantId);
```

Seeing `PreparedStatement` does **not** prove that:

1. PostgreSQL definitely created a **server-side named prepared statement**.
2. The server is definitely running a **generic plan**.
3. Every execution reuses the exact plan cached on the first call.
4. Parameter values have zero effect on planning.

JDBC is a parameter-binding API; pgJDBC has its own preparation threshold and statement-caching behavior. Server-side preparation depends on driver version, configuration, and execution counts.

### 7.1. Separate the Three Layers

```text
Java application layer
  PreparedStatement + setInt(...)

Driver / PostgreSQL wire protocol layer
  Bind parameters
  May use unnamed or named statements per configuration

PostgreSQL planner layer
  Custom plan per execution
  or reused Generic plan per server decision
```

To diagnose accurately, verify **whether the statement is actually server-prepared and which plan mode is active**.

### 7.2. Never Drop Bind Parameters Just to Avoid Generic Plans

A common buggy workaround is string concatenation:

```java
// NOT RECOMMENDED:
String sql = "SELECT * FROM skew_lab.orders " +
             "WHERE tenant_id = " + userSuppliedValue;
```

That invites SQL injection, escaping/type bugs, fragmented query logs, and extra parsing overhead. The right path is **keeping parameterization** and adjusting planning, query shape, or indexes based on evidence.

## 8. `PREPARE` / `EXECUTE` in PostgreSQL

To study custom vs generic plans independently of JDBC, use SQL-level `PREPARE`.

### 8.1. Prepare the Statement

```sql
PREPARE orders_by_tenant(integer) AS
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;
```

Parameter `$1` is declared as `integer`, matching `tenant_id`.

### 8.2. Execute with Two Values

```sql
EXECUTE orders_by_tenant(1);
EXECUTE orders_by_tenant(999);
```

These return vastly different result sizes:

- Tenant 1: 225,000 rows.
- Tenant 999: 25 rows.

Running interactively in a client, printing 225,000 rows slows down rendering/network. When analyzing plans, use `EXPLAIN (ANALYZE, BUFFERS) EXECUTE` so the server executes and measures without sending all rows to the client.

### 8.3. Inspect Plans with Real Parameters

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(999);
```

Correct syntax is **`EXPLAIN EXECUTE prepared_statement(arguments)`**.

Do not write:

```sql
-- Incorrect for running parameter $1 in standard psql:
EXPLAIN
SELECT *
FROM skew_lab.orders
WHERE tenant_id = $1;
```

without an active prepared statement or bind context.

### 8.4. Deallocate the Prepared Statement

```sql
DEALLOCATE orders_by_tenant;
```

SQL-level prepared statements belong to the session, not to disk or tables. Ending the session also drops its prepared statements.

## 9. How Are Generic vs Custom Plans Chosen?

PostgreSQL provides:

```sql
SHOW plan_cache_mode;
```

Available modes:

| Value | Meaning |
| --- | --- |
| `auto` | Server decides between custom and generic using cost heuristics |
| `force_custom_plan` | Prefers custom plans for relevant executions |
| `force_generic_plan` | Prefers generic plans for relevant executions |

### 9.1. `auto` Mode Is Not Simply “Call 6 Always Uses Generic”

For parameterized prepared statements, PostgreSQL usually builds **several initial custom plans** (typically around five) to gather average planning and execution cost estimates. Afterward, it compares a generic plan's estimated cost against the observed custom plans.

However, exact behavior depends on statement type and caching rules. Never state as dogma:

> Call it five times and the sixth call is guaranteed to switch to a generic plan.

Under heavy skew, when the generic plan's estimated cost is uncompetitive, PostgreSQL can stay on custom plans. Other statements without parameters or with specific structures follow their own rules.

### 9.2. Why Does PostgreSQL Consider Generic Plans?

Building custom plans incurs **planning cost**. For SQL executed millions of times, skipping planning overhead helps significantly.

When all parameter values have similar selectivity and share the same optimal access path, a generic plan is usually ideal.

### 9.3. Why Can Generic Plans Fail on Skewed Data?

One generic plan must handle both:

```text
tenant_id=1    -> ~225,000 rows
tenant_id=999  -> 25 rows
```

Suppose the generic plan picks `Index Scan`:

- For a small tenant, only a few dozen heap accesses.
- For the hot tenant, hundreds of thousands of heap accesses and massive data transfer.

Suppose the generic plan picks `Seq Scan`:

- For the hot tenant, reasonable.
- For a small tenant, scans the entire 250,000-row table just to return 25 rows.

Thus actual runtime swings wildly by **parameter value**, even though the generic plan never changed.

### 9.4. Custom Plans Are Not Always Faster

Custom plans pay planning cost on every call and do not always beat generic plans across all parameter values. On tiny queries, planning time can dominate execution time.

Compare **total latency, buffer accesses, call frequency, and key parameter classes**, not a single run's execution time alone.

## 10. Comparing Custom vs Generic via `plan_cache_mode`

This is the core experiment of the lesson. Run in the **same session** after preparing `orders_by_tenant`.

### 10.1. Force Custom Plan Within a Test Transaction

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(999);

ROLLBACK;
```

`SET LOCAL` applies only inside the transaction, preventing accidental leakage onto subsequent pooled uses of the connection.

With custom plans, hot and cold queries can select different access paths.

### 10.2. Force Generic Plan Within a Test Transaction

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(999);

ROLLBACK;
```

The generic plan shares the exact same **plan shape** for both calls, yet row counts, timings, and buffers **can differ dramatically**.

### 10.3. Reading Illustrative Plans

A custom plan for tenant 1 might show:

```text
Seq Scan on orders
  Filter: (tenant_id = 1)
```

A custom plan for tenant 999 might show:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = 999)
```

A generic plan might show:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = $1)
```

**These are structural examples**, not measured outputs or guaranteed plans. Seeing `$1` instead of a literal value in `EXPLAIN` is a classic sign of a generic plan; confirm alongside `plan_cache_mode` and session counters.

### 10.4. What Should You Compare?

Across all four runs (hot/cold × custom/generic), record:

| Factor | What to Observe |
| --- | --- |
| Plan nodes | `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` |
| Estimated `rows` | Does generic estimate differ from custom? |
| `actual rows` | Real 225,000 vs 25? |
| `Buffers: shared hit/read` | Pages touched and cache effect? |
| `Execution Time` | Execution cost |
| `Planning Time` | Planning overhead |
| `loops` | Did any node repeat many times? |
| `Index Cond` / `Filter` | Where does the predicate execute? |
| `SETTINGS` | Is `plan_cache_mode` shown? |

### 10.5. Cleanup After Practice

```sql
DEALLOCATE orders_by_tenant;
```

If you used another `PREPARE` name, `DEALLOCATE` that exact name. No server restart is needed.

## 11. Inspecting Prepared Statements and Plan Counters

PostgreSQL exposes:

```sql
SELECT
    name,
    statement,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements;
```

On modern versions supporting `generic_plans` and `custom_plans`, these columns count **how many times** generic vs custom plans were chosen for prepared statements in the **current session**.

### 11.1. Counters Are Session-Scoped

If you open two `psql` windows:

- Session A prepares `orders_by_tenant`.
- Session B queries `pg_prepared_statements`.

Session B **will not see Session A's statements**, because the view reports only statements prepared in the current session. Never use it to claim “nobody in the system has prepared statements.”

### 11.2. `from_sql`

`from_sql` indicates whether the prepared statement was created via SQL `PREPARE` or via the wire protocol.

In pgJDBC apps, named prepared statements are typically created over the wire protocol (`from_sql = false`) depending on driver and settings.

### 11.3. Counters Do Not Tell You Which Tenant Was Slow

Seeing `generic_plans = 100` does not say whether those 100 calls hit the hot tenant or cold tenants; the view does not retain parameter histories.

Measure by parameter class and combine with application metrics.

### 11.4. State Resets on Reconnect

Session prepared statements do not survive a disconnect/reconnect. Behind a connection pool, each physical backend connection tracks its own prepared-statement state.

Thus an application uses **many physical connections**, each potentially at a different stage of custom/generic plan selection.

## 12. `pg_stats`: How Does the Planner Know Which Values Are “Hot”?

PostgreSQL gathers statistics via `ANALYZE`. A primary input for equality selectivity estimates is **Most Common Values (MCV)**.

### 12.1. Inspecting `tenant_id` Statistics

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

Columns:

| Column | Meaning |
| --- | --- |
| `null_frac` | Fraction of `NULL`s in the sample |
| `n_distinct` | Estimated number of distinct values |
| `most_common_vals` | Most frequent values tracked |
| `most_common_freqs` | Frequencies corresponding to MCVs |
| `histogram_bounds` | Histogram bucket bounds for remaining distribution |
| `correlation` | Correlation between logical value order and physical heap order |

### 12.2. Why Do MCVs Matter?

Tenant 1 occupies 90% of the table. When statistics record tenant 1 as an MCV with frequency ~0.9, a custom plan for:

```sql
WHERE tenant_id = 1
```

estimates hundreds of thousands of rows accurately.

For another tenant absent from the MCV list, the planner uses the remaining non-MCV statistics to estimate an average frequency across uncommon values.

### 12.3. Histograms Differ from MCV Lists

MCVs serve equality lookups on frequent values. Histograms describe value spread for range predicates such as:

```sql
WHERE created_at >= $1
  AND created_at < $2
```

Do not assume every equality value gets its own exact histogram bucket like a full frequency table.

### 12.4. Statistics Are Sample-Based Estimates

`ANALYZE` samples rows rather than running an exact full-table `GROUP BY` on every column. Estimates shift slightly as data and samples change.

Even when statistics model tenant 1 accurately, a **generic plan still cannot tailor itself to `$1 = 1`** the way a custom plan does.

### 12.5. Fast-Changing Skewed Tables Need Fresh Stats

If tenant 1 doubles in size during an import while statistics remain stale, even custom plans can misestimate.

Distinguish two problems:

- **Missing or stale statistics.**
- **Generic plan unable to see the parameter value**, even with perfect stats.

They require different solutions.

## 13. Increasing Statistics Detail When Needed

PostgreSQL lets you raise a column's **statistics target**:

```sql
ALTER TABLE skew_lab.orders
ALTER COLUMN tenant_id
SET STATISTICS 1000;

ANALYZE skew_lab.orders;
```

### 13.1. When Is This Helpful?

When a column has:

- A highly complex distribution.
- Many frequent values worth tracking in MCVs.
- Coarse histograms causing poor range estimates.
- Bad row estimates even right after `ANALYZE`.
- A heavy workload where extra `ANALYZE` cost is acceptable.

### 13.2. When Is It Not Helpful?

If tenant 1 already appears in MCVs at ~0.9 frequency, raising the statistics target from default to 1000 **will not make a generic plan sensitive to tenant 1**.

The bottleneck is **not knowing `$1` at generic planning time**, not ignorance of the column's distribution.

### 13.3. Trade-Offs

Higher statistics targets increase:

- `ANALYZE` CPU/I/O and duration.
- Statistics storage size.
- Planner overhead on affected queries.

Tune based on measured estimate gaps, not as a “higher is always better” rule for every column.

### 13.4. Don't Forget `ANALYZE` After Changing Target

`ALTER COLUMN ... SET STATISTICS` affects future statistics collection. Run `ANALYZE` afterward so the planner sees the richer stats.

## 14. Multi-Column Skew: `tenant_id` and `status` Are Correlated

In the lab dataset:

- Tenant 1 is mostly `DONE`.
- Small tenants have a much higher share of `PENDING`.

So these two predicates are not independent:

```sql
WHERE tenant_id = $1
  AND status = $2
```

### 14.1. The Independence Assumption Problem

If the planner naively multiplies probabilities:

```text
P(tenant=1 AND status=PENDING)
  ≈ P(tenant=1) × P(status=PENDING)
```

the estimate can diverge sharply from reality because `PENDING` rate depends on tenant.

### 14.2. Verify with a Lab Query

```sql
SELECT
    tenant_id,
    COUNT(*) AS total,
    COUNT(*) FILTER (
        WHERE status = 'PENDING'
    ) AS pending,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'PENDING')::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS pending_ratio
FROM skew_lab.orders
WHERE tenant_id IN (1, 2, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

Results show dramatically different `PENDING` ratios between tenant 1 and small tenants.

### 14.3. Extended Statistics

You can create multi-column statistics:

```sql
CREATE STATISTICS orders_tenant_status_stats
    (mcv, dependencies)
ON tenant_id, status
FROM skew_lab.orders;

ANALYZE skew_lab.orders;
```

Multi-column MCVs help the planner recognize frequent vs rare value pairs.

### 14.4. Inspect Extended Statistics

```sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds
FROM pg_stats_ext
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
ORDER BY statistics_name;
```

View structure, detail, and supported predicate types depend on PostgreSQL version.

### 14.5. Extended Statistics Do Not Fix Every Generic Plan

Extended statistics improve **estimates** when concrete predicates are known. In a generic plan:

```sql
WHERE tenant_id = $1
  AND status = $2
```

concrete values of `$1` and `$2` are unavailable to look up **exact MCV pairs** the way a custom plan can.

Always check **custom vs generic** alongside extended statistics; creating stats does not replace plan-mode analysis.

## 15. Standard Indexes: Right Predicates and Right Scale

We already created:

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);
```

### 15.1. Cold Tenants Usually Benefit

```sql
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 999;
```

The index lets PostgreSQL read ~25 rows instead of scanning 250,000 rows.

### 15.2. Hot Tenants May Not

```sql
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 1;
```

When returning 225,000 wide rows with `payload`, traversing the index and heap can cost more than a `Seq Scan`.

### 15.3. Creating an Index Does Not Force Generic and Custom Plans to Match

Even with the index present, a generic plan chooses one access path with reasonable expected cost across **possible parameter values**.

An index can make cold tenants blazingly fast under custom planning while a generic plan still picks a poor compromise for one side.

### 15.4. Do Not Create Duplicate Indexes

If `orders_tenant_idx` already exists:

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);
```

re-running fails with a duplicate-name error. Creating an identically keyed index under a new name only adds write overhead.

In the lab, run each `CREATE INDEX` once, or use a fresh schema when comparing before vs after.

## 16. Composite Indexes for Common Query Shapes

Suppose the app frequently filters:

```sql
WHERE tenant_id = $1
  AND status = $2
```

Consider:

```sql
CREATE INDEX orders_tenant_status_idx
ON skew_lab.orders (tenant_id, status);

ANALYZE skew_lab.orders;
```

### 16.1. What Does the Composite Index Help?

A B-tree on `(tenant_id, status)` supports equality on both columns directly, usually beating a tenant index scan followed by post-filtering `status` when selective and frequent.

### 16.2. Comparing Against Two Single-Column Indexes

With two separate indexes:

```sql
CREATE INDEX orders_status_idx
ON skew_lab.orders (status);
```

PostgreSQL can choose among:

- Index Scan on `tenant_id`.
- Index Scan on `status`.
- `BitmapAnd` combining both indexes.
- Composite index.
- `Seq Scan`.

Composite indexes win when queries consistently filter both columns; single indexes help queries filtering only one column.

### 16.3. Indexes Do Not Replace Up-to-Date Statistics

If the planner misestimates `(tenant_id, status)` frequency, it can pick a poor path despite the composite index. Extended statistics can help in such cases.

### 16.4. Column Order Matters

An index on:

```sql
(tenant_id, status)
```

differs from:

```sql
(status, tenant_id)
```

in single-column prefix usage, range predicates, `ORDER BY`, and scan bounds.

Choose column order based on your **primary query workload**, not rigid slogans like “low-cardinality first” or “high-cardinality first.”

### 16.5. Too Many Indexes Slow Down Writes

Every index increases:

- `INSERT`/`UPDATE`/`DELETE` cost.
- WAL volume.
- Storage footprint.
- `VACUUM` / maintenance work.
- Risk of blocking HOT updates when indexed columns change.

Never add an index merely because you can; measure net workload impact.

## 17. Partial Indexes: Special Behavior with Parameterized Predicates

A partial index stores only rows matching a fixed predicate.

### 17.1. Create a Partial Index for `PENDING` Orders

```sql
CREATE INDEX orders_pending_tenant_time_idx
ON skew_lab.orders (tenant_id, created_at DESC)
WHERE status = 'PENDING';

ANALYZE skew_lab.orders;
```

This indexes only `status = 'PENDING'` rows, keeping it much smaller than a full index when `PENDING` is a small fraction.

### 17.2. Query with a Constant Predicate

```sql
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = 999
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

The planner proves the `WHERE` clause **implies** the partial index predicate, making the index eligible.

### 17.3. Query Parameterizing `status` Too

```sql
PREPARE pending_or_done(integer, text) AS
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC
LIMIT 20;
```

In a **generic plan**, PostgreSQL cannot assume `$2 = 'PENDING'` for every call, so it cannot use a partial index defined with `WHERE status = 'PENDING'`.

In a **custom plan** when `$2 = 'PENDING'`, the planner can consider the partial index if value-level implication and cost favor it.

### 17.4. Don't Assume No Parameterized Query Can Use a Partial Index

Consider this different shape:

```sql
PREPARE pending_for_tenant(integer) AS
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

Here **`status` is a business constant**, while only `tenant_id` is parameterized. Both generic and custom plans see `status = 'PENDING'` and can consider the partial index.

The lesson is not “drop bind parameters,” but:

> When a filter is a **true business constant** for a query shape, keep it as a SQL literal so the planner can prove partial-index eligibility while **user-supplied values** remain bound parameters.

### 17.5. Never Interpolate Untrusted Input

Never replace `$2` by concatenating HTTP request values:

```java
// Unsafe:
String sql = "SELECT * FROM skew_lab.orders WHERE status = '"
           + userStatus
           + "'";
```

If an endpoint supports multiple statuses, use predefined query variants or keep parameter binding with a suited composite index/plan strategy. Never sacrifice SQL injection safety to force a partial index.

### 17.6. Clean Up Example Prepared Statements

```sql
DEALLOCATE pending_or_done;
DEALLOCATE pending_for_tenant;
```

## 18. `ORDER BY ... LIMIT` Changes Plan Choices

Not every hot-tenant query fetches 225,000 rows.

For a “20 newest orders” UI:

```sql
SELECT order_id, created_at, amount, status
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;
```

With an index:

```sql
CREATE INDEX orders_tenant_time_idx
ON skew_lab.orders (tenant_id, created_at DESC);
```

the B-tree walks the tenant's entries in chronological order and **stops after 20 rows**.

### 18.1. Why Can a Hot Tenant Still Fit `Index Scan`?

It does not return 225,000 rows; it only needs the top 20 in sort order.

The index avoids:

- Scanning most of the table.
- Sorting hundreds of thousands of rows.
- Reading excess heap pages.

### 18.2. Verify with `EXPLAIN`

```sql
PREPARE recent_orders(integer) AS
SELECT order_id, created_at, amount, status
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(999);

DEALLOCATE recent_orders;
```

Even though the two tenants differ by 9,000× in total rows, an ordered index path can work well for both thanks to **`LIMIT`**.

### 18.3. Why You Shouldn't Tune Purely by Match Percentage

With the exact same `tenant_id = 1`:

```sql
SELECT * FROM skew_lab.orders
WHERE tenant_id = 1;
```

behaves completely differently from:

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 20;
```

The planner must evaluate the **entire query**, including projected columns, ordering, and limits.

### 18.4. Deep `OFFSET` Can Undo the Gain

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 20 OFFSET 200000;
```

The executor must walk past huge numbers of index entries before returning 20 deep rows. For deep pagination, consider **keyset pagination** on a stable tuple key like `(created_at, order_id)` when indexes and UX permit.

## 19. Covering Indexes and `Index Only Scan`

An `Index Only Scan` reduces heap fetches when:

1. All columns needed by the query live in the index.
2. The access method supports it.
3. The visibility map confirms pages are all-visible without visiting the heap.

### 19.1. Create a Query-Specific Covering Index

```sql
CREATE INDEX orders_tenant_time_cover_idx
ON skew_lab.orders (tenant_id, created_at DESC)
INCLUDE (status, amount);
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, created_at, status, amount
FROM skew_lab.orders
WHERE tenant_id = 999
ORDER BY created_at DESC
LIMIT 20;
```

The planner can choose `Index Only Scan` when cost-effective.

### 19.2. `Heap Fetches` Does Not Automatically Equal 0

Even when every column is covered, PostgreSQL must visit the heap to check MVCC visibility whenever pages aren't marked `all-visible`.

`EXPLAIN ANALYZE` may show:

```text
Index Only Scan using orders_tenant_time_cover_idx
  Index Cond: (tenant_id = 999)
  Heap Fetches: ...
```

`Heap Fetches = 0` happens when the visibility map is sufficiently clean, not as an unconditional guarantee.

### 19.3. `VACUUM` in the Lab

```sql
VACUUM (ANALYZE) skew_lab.orders;
```

`VACUUM` updates the visibility map, helping `Index Only Scan` skip heap fetches on mostly static tables. Remember `VACUUM` cannot run inside an explicit transaction block.

### 19.4. Don't Blindly `INCLUDE` Wide `payload` Columns

Adding `payload` bloats index size, raises write cost, and can even hit index tuple size limits depending on data.

A lean covering index for a narrow summary query is usually far more practical than stuffing wide text columns into an index.

### 19.5. Generic vs Custom Remains a Separate Issue

Even with a covering index, a generic plan may still be suboptimal for a query **returning most of the table**. Covering indexes help specific cases without erasing skew-driven cost differences.

## 20. Optional Predicates: `$1 IS NULL OR col = $1`

A common API pattern for an optional filter dropdown:

```sql
WHERE ($1 IS NULL OR tenant_id = $1)
```

Intent:

- `$1 = NULL`: return all tenants.
- `$1 = 999`: return only tenant 999.

### 20.1. The Problem with Generic Plans

```sql
PREPARE orders_optional_tenant(integer) AS
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders
WHERE ($1 IS NULL OR tenant_id = $1);
```

A generic plan must remain valid for **both `NULL` and non-`NULL`**. Not knowing `$1`, the planner cannot treat `tenant_id = $1` as guaranteed selective and pick an index scan assuming 25 rows.

A custom plan can fold the predicate around the real value:

- For `NULL`: simplifies to true, scanning the whole table.
- For `999`: simplifies to a selective equality filter.

### 20.2. Compare in the Lab

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(NULL);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(999);

ROLLBACK;
```

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(NULL);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(999);

ROLLBACK;
```

Clean up:

```sql
DEALLOCATE orders_optional_tenant;
```

### 20.3. A Clean Fix: Two Predefined Query Shapes

If the API genuinely has two modes, write **two separate SQL queries**:

```sql
-- System-wide view mode, no tenant filter:
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders;

-- Single-tenant mode:
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders
WHERE tenant_id = $1;
```

Branch in application code on parameter presence while **keeping bind parameters**.

This lets the planner optimize each shape cleanly and avoids unpredictable multi-branch `OR` predicates.

### 20.4. Do Not Confuse Query Splitting with Dangerous String Concatenation

Splitting query variants looks like:

```java
if (tenantId == null) {
    sql = "SELECT ... FROM skew_lab.orders";
} else {
    sql = "SELECT ... FROM skew_lab.orders WHERE tenant_id = ?";
}
```

The app still uses `PreparedStatement` and `setInt` when a parameter exists.

Never interpolate user values into SQL text.

## 21. `COALESCE` Predicates Can Also Hinder the Planner

A frequent variant:

```sql
WHERE tenant_id = COALESCE($1, tenant_id)
```

Meant so `$1 = NULL` means “don't filter by tenant,” this pattern has several drawbacks:

- It is an expression rather than a clean constant equality predicate.
- Index eligibility depends on expression simplification and plan choice.
- On nullable columns, `tenant_id = tenant_id` does **not** match `NULL` rows (`NULL = NULL` is unknown).
- A generic plan often cannot exploit a selective index path.

Even on `NOT NULL` `tenant_id` in the lab, optional-NULL behavior may look right yet still **hurt plan quality**.

**Recommendation:** when filter combinations are few and clear, use separate parameterized query variants. For dynamic multi-filter search, assemble controlled `WHERE` clauses from whitelisted predicates with bound parameters.

## 22. `IN`, `ANY`, and Short vs Long Array Parameters

An API might filter multiple tenants:

```sql
WHERE tenant_id = ANY($1::integer[])
```

Yet array length and contents vary widely:

- A single cold tenant.
- An array containing the hot tenant.
- Hundreds of tenants.
- An empty array.
- Thousands of values.

### 22.1. Prepared Statement Using an Array

```sql
PREPARE orders_for_tenants(integer[]) AS
SELECT order_id, tenant_id, amount
FROM skew_lab.orders
WHERE tenant_id = ANY($1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[999]::integer[]);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[1]::integer[]);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[1, 999]::integer[]);

DEALLOCATE orders_for_tenants;
```

### 22.2. Challenges with Generic Plans

A generic plan is not specialized to the **exact values and length of the array** in each `EXECUTE` the way a custom plan is. It relies on general default array selectivity heuristics.

Consequently, the exact same SQL can perform very differently for a 1-element array vs a 1,000-element array.

### 22.3. Empty Arrays Have Clear Semantics

```sql
WHERE tenant_id = ANY(ARRAY[]::integer[])
```

matches zero tenants under standard equality predicates.

Applications should never silently treat “empty array” as “all tenants” unless explicitly designed as a separate business rule.

### 22.4. Evaluate Different Designs for Huge Lists

When requests send thousands or tens of thousands of IDs, consider:

- A temporary table holding the IDs with `ANALYZE` statistics.
- Joining against a `VALUES` list.
- Chunked batch processing.
- Joining directly to an existing relational table/group key.
- Capping list size at the API layer.

Huge arrays behave very differently during planning and execution from tiny arrays. Pick a pattern matching **real data scale** rather than stretching one array pattern everywhere.

### 22.5. Watch Connection Pooling with Temp Tables

Temporary tables are session-scoped, so usage depends on pooling mode. Under transaction pooling, session-scoped temp tables can break or leak if not carefully isolated.

Never adopt temp tables to “fix generic plans” without checking your connection pool architecture.

## 23. Range Predicates and Time Skew

Skew isn't limited to equality on `tenant_id`. Time-series data often clusters near the present.

Example:

```sql
SELECT order_id, created_at, amount
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2;
```

One call queries 10 minutes; another queries 18 months.

### 23.1. Two Ranges of Very Different Span

```sql
PREPARE orders_in_period(timestamptz, timestamptz) AS
SELECT order_id, created_at, amount, payload
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2;
```

Query 1: one hour.

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_in_period(
    timestamptz '2025-01-02 00:00:00+00',
    timestamptz '2025-01-02 01:00:00+00'
);
```

Query 2: very long span.

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_in_period(
    timestamptz '2025-01-01 00:00:00+00',
    timestamptz '2026-01-01 00:00:00+00'
);
```

Clean up:

```sql
DEALLOCATE orders_in_period;
```

Without an index on `created_at`, both may `Seq Scan`. To test an index:

```sql
CREATE INDEX orders_created_idx
ON skew_lab.orders (created_at);

ANALYZE skew_lab.orders;
```

### 23.2. Very Short Ranges Favor `Index Scan`

Matching only a few dozen rows favors an index range scan.

### 23.3. Wide Ranges Favor `Seq Scan`

Matching most of the table favors scanning sequentially over scattered heap fetches.

### 23.4. Generic Plans Struggle to Fit Both Ranges Simultaneously

When bounds are parameterized, a generic plan cannot inspect the **interval width** of each call. Custom plans use actual bounds to estimate selectivity accurately.

### 23.5. Histograms Matter Greatly Here

For range predicates, `histogram_bounds` and time distribution statistics are critical inputs for the planner.

If fresh data was just loaded at the upper edge while stats lag behind, recent-time queries can misestimate badly. Run `ANALYZE` after significant data changes.

## 24. Range + Tenant: Multi-Dimensional Skew

A realistic SaaS query:

```sql
SELECT order_id, tenant_id, status, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND created_at >= $2
  AND created_at < $3
ORDER BY created_at DESC
LIMIT 50;
```

Optimizing this depends simultaneously on:

1. Large vs small tenant.
2. Short vs long time span.
3. Rows surviving filters.
4. Whether an index supports `ORDER BY` order.
5. Whether `LIMIT 50` stops early.
6. Physical correlation across time/tenant.
7. Generic vs custom plan.

### 24.1. A Composite Index Is Usually Worth Testing

```sql
CREATE INDEX orders_tenant_created_idx
ON skew_lab.orders (tenant_id, created_at DESC);
```

The B-tree handles tenant equality followed by chronological range and sort order.

### 24.2. A Well-Designed Index Reduces Skew Sensitivity

With `ORDER BY created_at DESC LIMIT 50`, this single composite index can perform well for both hot and cold tenants because execution stops after at most 50 rows.

This shows how **fixing the index/query shape** often beats forcing custom plans system-wide.

### 24.3. Indexes Don't Guarantee Speed If Rows Are Sparse

If a tenant has very few orders inside the chosen time range, the executor still scans that range's index entries and visibility until it finds 50 rows or hits the end.

Run `EXPLAIN ANALYZE` across both hot/cold tenants and short/long ranges—not just one best-case scenario.

### 24.4. Align Index Key Order with Real Workload

If some queries filter time globally while others filter tenant + time, separate indexes may be justified—just avoid building every permutation. Measure and keep only high-impact indexes.

## 25. Does Partitioning Solve Generic Plans?

Partitioning limits the data scanned, yet **does not automatically turn generic plans into custom plans**.

### 25.1. Example Isolating the Hot Tenant

Illustrative demo:

```sql
CREATE TABLE skew_lab.partitioned_orders_demo (
    order_id bigint NOT NULL,
    tenant_id integer NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY LIST (tenant_id);

CREATE TABLE skew_lab.partitioned_orders_hot
PARTITION OF skew_lab.partitioned_orders_demo
FOR VALUES IN (1);

CREATE TABLE skew_lab.partitioned_orders_other
PARTITION OF skew_lab.partitioned_orders_demo
DEFAULT;
```

This is a **separate illustrative table** without `skew_lab.orders` data, showing list partitioning by tenant.

### 25.2. Planner and Executor Pruning

For:

```sql
WHERE tenant_id = $1
```

PostgreSQL can prune irrelevant partitions using:

- Values known at planning time, or
- Parameter values bound at execution time via **execution-time partition pruning**.

Thus a generic plan **can still benefit** from partition pruning where supported.

### 25.3. Yet Partition Pruning Doesn't Eliminate All Skew

Even down to one partition:

- The hot tenant's partition still holds massive data.
- Inside a partition, queries still choose among `Seq Scan`, `Bitmap`, or `Index Scan`.
- Queries omitting the partition key must scan multiple partitions.
- Too many partitions inflate planning and management overhead.
- Indexes and statistics still matter inside partitions.

### 25.4. Partitioning Is Not the First Fix for a Slow Query

Before partitioning:

1. Audit query patterns.
2. Inspect `EXPLAIN` and `actual rows`.
3. Check statistics and indexes.
4. Compare generic vs custom plans.
5. Optimize `LIMIT`, filters, and projections.
6. Weigh partition management costs.

Adopt partitioning only when workload, data retention, scale, and pruning benefits justify it.

## 26. Generic Plans Still Fit Uniformly Selective Workloads

Never make a blanket rule like “always set `force_custom_plan` for parameterized SQL.”

For example, primary-key lookup on `order_id`:

```sql
PREPARE one_order(bigint) AS
SELECT order_id, tenant_id, status
FROM skew_lab.orders
WHERE order_id = $1;
```

Nearly every call returns at most one row. A generic plan probing the primary key index works great for all parameter values.

### 26.1. When Custom Planning Only Adds Planning Cost

If every parameter value picks the same access path and processes similar row counts, re-planning every call adds overhead for zero gain.

### 26.2. Factor in Call Frequency

A query run a few times per day differs from one run hundreds of thousands of times per minute. On ultra-short queries, planning time can rival execution time.

### 26.3. Judge by Total Latency

Evaluate:

```text
Total latency
  ≈ planning overhead
    + execution cost
    + waiting / I/O
    + network and application overhead
```

This is a **qualitative** model, not a literal sum of `EXPLAIN` timings.

Shaving 20% off execution time while sharply inflating planning overhead on high-QPS traffic may be a net loss. Measure on realistic load.

## 27. `plan_cache_mode`: Choose the Right Scope

A common reaction when spotting a bad generic plan:

```sql
SET plan_cache_mode = force_custom_plan;
```

This affects the session according to where it is set. With connection pools, session-level settings persist across reused connections.

### 27.1. Prefer `SET LOCAL` During Experiments

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- Execute statements to measure on this connection.

COMMIT;
```

`SET LOCAL` applies only to the current transaction and resets automatically when the transaction ends.

### 27.2. Doesn't Work as Expected Under Autocommit

Wrong expectation:

```sql
-- When each statement runs in its own autocommit transaction:
SET LOCAL plan_cache_mode = force_custom_plan;

-- The next statement may not retain that local setting:
EXECUTE orders_by_tenant(1);
```

For `SET LOCAL` to cover target statements, wrap them inside an explicit transaction or use appropriate scoped config.

### 27.3. Session-Level `SET` Requires Guaranteed Cleanup

```sql
SET plan_cache_mode = force_custom_plan;

-- Statements in this session...

RESET plan_cache_mode;
```

Fine in a lab; in pooled apps you must reset on every exit path including exceptions, or subsequent requests inherit unintended settings.

### 27.4. Cluster-Wide Overrides Need Strong Evidence

Forcing custom plans cluster-wide strips generic reuse from simple point lookups.

Forcing generic plans cluster-wide cripples skew-sensitive queries.

**`auto` is usually the right default.** Apply narrow overrides only to specific queries proven problematic.

### 27.5. `plan_cache_mode` Does Not Replace Indexes

If no index fits the predicate, both custom and generic plans fall back to `Seq Scan` or similar paths. Forcing custom plans never invents an access path.

## 28. JDBC: Proper Parameter Typing and Prepared Statement Management

Java backends typically query PostgreSQL with `PreparedStatement`.

### 28.1. Safe Bind-Parameter Example

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderQueryService {
    private final DataSource dataSource;

    public OrderQueryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printRecentOrders(int tenantId) throws SQLException {
        String sql = """
            SELECT order_id, created_at, status, amount
            FROM skew_lab.orders
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setInt(1, tenantId);
            ps.setInt(2, 20);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("order_id");
                    String status = rs.getString("status");
                    System.out.println(id + " : " + status);
                }
            }
        }
    }
}
```

Key points:

- Bind `tenantId` with `setInt` matching `integer`.
- Never concatenate `tenantId` into SQL text.
- `LIMIT` can also be parameterized when passed cleanly via JDBC.
- Returning at most 20 rows avoids shipping 225,000 rows of the hot tenant just to render a UI page.
- `PreparedStatement` and `ResultSet` are closed via try-with-resources.

### 28.2. Parameter Types Affect Planning and Semantics

In PostgreSQL, bound parameter types govern operator resolution and index eligibility.

For `tenant_id integer`:

- `setInt(1, tenantId)` is unambiguous.
- Passing everything as strings or casting carelessly causes type errors or unindexable predicates.
- `WHERE tenant_id::text = ?` differs fundamentally from `WHERE tenant_id = ?` in index applicability.

Always bind the matching SQL type instead of casting columns to text to fit UI inputs.

### 28.3. pgJDBC Server-Side Preparation Is Not Fixed Behavior

pgJDBC exposes settings for **server-side prepare**, statement caching, and prepare thresholds (commonly `prepareThreshold`). Exact behavior varies with **driver version and configuration**—never infer from Java class names alone that the server switched to a generic plan on call N.

To verify:

- Inspect your active pgJDBC configuration.
- Check session prepared statements where possible.
- Compare custom/generic plans in SQL on the exact PostgreSQL version.
- Check query types and conditions under which the driver prepares server-side.
- Measure latency across many calls, not just the first call.

### 28.4. Connection Pools Create Independent Cache Contexts

Each physical PostgreSQL backend keeps its own prepared statements. With a 20-connection pool, preparing on connection A does not prepare on connection B.

“First requests fast, later ones slow” can occur unevenly because:

- Different connections hit preparation thresholds at different times.
- Different parameter mixes route across connections.
- Custom/generic choices diverge by connection history.
- Pool churn closes and recreates connections.
- Cache warmth, load, and autovacuum fluctuate.

Diagnose at the level of **individual physical connections/sessions** when possible.

## 29. Forcing Custom Plans for One Transaction in JDBC

Educational example scoping `plan_cache_mode` to one transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class SkewAwareQuery {
    private final DataSource dataSource;

    public SkewAwareQuery(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countTenantOrders(int tenantId) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                try (Statement setting = conn.createStatement()) {
                    setting.execute(
                        "SET LOCAL plan_cache_mode = force_custom_plan"
                    );
                }

                long count;
                try (PreparedStatement ps = conn.prepareStatement(
                        "SELECT COUNT(*) " +
                        "FROM skew_lab.orders " +
                        "WHERE tenant_id = ?"
                )) {
                    ps.setInt(1, tenantId);
                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        count = rs.getLong(1);
                    }
                }

                conn.commit();
                return count;
            } catch (SQLException | RuntimeException ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
```

This demonstrates scoping:

1. `setAutoCommit(false)` starts a code-managed transaction.
2. `SET LOCAL` applies inside that transaction.
3. The prepared query executes on the **same connection**.
4. `commit()` ends the transaction and resets the local setting.
5. Errors trigger `rollback()`.

### 29.1. Why Not Apply This Pattern to Every Request Right Away?

It forces explicit transaction management and custom planning without evidence that the query needs it. For `COUNT(*) WHERE tenant_id=?`, planning overhead might be negligible or significant under extreme QPS.

Apply it only to statements proven to suffer from generic-plan regressions.

### 29.2. Respect Framework Transaction Managers

If a framework manages transactions, never call `setAutoCommit`/`commit` directly on managed connections.

Use framework-compatible transaction/session configuration so SQL executes within the intended transaction and connection.

### 29.3. `SET LOCAL` Cannot Fix a Query That Already Ran

It affects subsequent executions within its scope; it never retroactively changes plans or results of earlier statements.

### 29.4. Never Switch to Simple Query Protocol Just to Dodge Plan Caching

Changing driver query modes affects server-side preparation, type binding, binary/text wire format, streaming, and pooling. Test thoroughly against driver documentation rather than treating it as a generic shortcut.

## 30. Application Strategy: Split by Query Shape Rather Than Hardcoding Tenant IDs

A clean solution is **tailoring query shapes to distinct intents**:

- Single-tenant detail query.
- System-wide overview query.
- `PENDING`-only queue query.
- Long-range analytical report.
- Top-20 recent orders query.

### 30.1. Avoid “One Giant SQL That Does Everything”

Hard-to-optimize pattern:

```sql
SELECT order_id, tenant_id, status, created_at, amount
FROM skew_lab.orders
WHERE ($1 IS NULL OR tenant_id = $1)
  AND ($2 IS NULL OR status = $2)
  AND ($3 IS NULL OR created_at >= $3)
  AND ($4 IS NULL OR created_at < $4)
ORDER BY created_at DESC
LIMIT $5;
```

When every filter is optional, a generic plan must accommodate wildly varying selectivities at once.

### 30.2. Split Distinct Semantic Use Cases

Example:

```sql
-- API fetching 20 newest orders for a tenant:
SELECT order_id, created_at, status, amount
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;

-- API fetching 20 newest PENDING orders for a tenant:
SELECT order_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;

-- System-wide summary report over a time range:
SELECT status, COUNT(*), SUM(amount)
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2
GROUP BY status;
```

Each of the three SQLs has a clean access pattern, while tenant IDs and date bounds stay safely bound.

### 30.3. Do You Need Separate Statements for Hot vs Cold Tenants?

Occasionally, yes—but first try:

- An index that works well for both.
- Appropriate `LIMIT` / `ORDER BY`.
- Narrowly scoped custom planning.
- Better statistics and cleaner query shapes.

If two separate execution paths are genuinely required, drive classification from **regularly updated metadata**, never by hardcoding “tenant 1 is always hot.” Skew evolves over time.

### 30.4. Never Mix Tenant Classification with Access Control

Hot/cold routing is strictly a performance concern, never an authorization boundary.

Regardless of which plan runs, enforce tenant isolation via authorization logic and schema/RLS policies where used.

## 31. Row-Level Security (RLS) and Parameterized Queries

Multi-tenant deployments sometimes enforce Row-Level Security.

Conceptual flow:

```text
Application authenticates tenant.
RLS policy restricts rows visible to the role.
Query still includes tenant_id = $1 or another business filter.
```

### 31.1. RLS Does Not Automatically Solve Generic Plans

RLS injects security predicates per PostgreSQL rules, yet the planner still chooses access paths within those constraints.

Under heavy skew, custom vs generic behavior and statistics still need measurement.

### 31.2. Never Drop `WHERE` for “Speed” If It Enforces Isolation

Query rewrites or variants must preserve authorization semantics.

Never replace:

```sql
WHERE tenant_id = $1
```

with an unfiltered query simply because `Seq Scan` looked fast on a hot tenant, if that request is authorized for only one tenant.

### 31.3. Statistics Can Have Security Constraints

Access to certain statistics or plan details may be restricted, and stats distributions can reveal sensitive business patterns. Run monitoring tools under appropriately scoped roles.

## 32. A “Clean-Looking” Generic Plan in `EXPLAIN` Can Crawl on a Hot Tenant

Hypothetical plan:

```text
Index Scan using orders_tenant_idx on orders
  (cost=0.42..350.00 rows=250 width=180)
  Index Cond: (tenant_id = $1)
```

When `$1 = 1` runs at execution time:

```text
actual rows=225000
Buffers: shared hit=... read=...
Execution Time: ...
```

The generic planner estimated ~250 rows while the executor processed 225,000 rows.

**Do not treat 250 and 225,000 above as measured output from PostgreSQL.** They illustrate the classic gap between a generic estimate and actual rows on skewed data.

### 32.1. Why Can an Index Path Be Expensive for a Hot Tenant?

- Huge numbers of index entries scanned.
- Huge numbers of heap tuples fetched.
- Scattered heap pages.
- Heavy `payload` retrieval.
- Cache churn, I/O, and CPU overhead.

### 32.2. Yet Sometimes an Index Path Still Wins for a Hot Tenant

When:

- Index access has high physical correlation.
- Only covered columns are needed.
- `ORDER BY ... LIMIT` stops early.
- Relevant heap pages sit warm in cache.
- Index-only scans incur very few `Heap Fetches`.

Therefore, never adopt a dogma like “hot tenants must always `Seq Scan`.” **Measure real plans.**

### 32.3. Compare `cost` vs Actual Time

`cost` is an **arbitrary planner unit**, not milliseconds. A generic plan with a low estimated total cost can still suffer huge actual runtime on a skewed parameter value.

Evaluate all of:

- Estimated rows vs `actual rows`.
- `Buffers`.
- `Execution Time`.
- `Planning Time`.
- End-to-end request latency.
- Ratio of hot vs cold calls in production.

## 33. Observing from the Application: Never Benchmark Only One Parameter Value

Testing solely with tenant 999 easily misleads you into concluding:

```text
Fast query (~few ms) -> No issue
```

while in production, tenant 1 hits the exact same SQL, fetches 225,000 rows, and runs orders of magnitude slower.

### 33.1. Build a Test Suite Covering Data Percentiles

Test at minimum:

| Parameter Class | Example | Purpose |
| --- | --- | --- |
| Hot | `tenant_id = 1` | Dominates table share |
| Cold | `tenant_id = 999` | Tiny row count |
| Non-existent | `tenant_id = 2000` | 0-row result |
| Common status | `status = 'DONE'` | Many matches |
| Rare status | `status = 'FAILED'` | Few matches |
| Correlated tenant + status | `1/PENDING`, `999/PENDING` | Multi-column skew |
| Short range | Minutes / hours | Index-selective |
| Long range | Months | Broad scan |
| Unfiltered | Optional `NULL` parameter | Full scan risk |
| Small vs large array | `ANY([999])` vs `ANY([...])` | Parameter cardinality |

### 33.2. Test Warm-Up and Caching

The first execution may be slower due to cold caches or before switching plan modes.

Make sure to:

- Measure after appropriate warm-up runs.
- Record plan and cache state.
- Run repeated iterations and inspect the latency distribution.
- Never report only the “fastest run.”
- Monitor concurrency and overall DB load.

### 33.3. Measure p95/p99, Not Just the Mean

A generic plan might satisfy 99% of small tenants while failing the largest tenant badly. If that hot tenant is a flagship customer, p99 latency or tenant-specific SLAs breach even when overall mean latency looks healthy.

### 33.4. Measure Total Data Returned

Returning 225,000 rows consumes network bandwidth and app object-mapping time even with an ideal server-side plan.

Never tune planner settings to paper over an API lacking pagination, output caps, or column projections.

## 34. `pg_stat_statements`: Great for Spotting Slow SQL, With Caveats

When `pg_stat_statements` is installed and configured, it aggregates execution metrics by normalized query.

Example in an enabled environment:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Columns and access vary by extension version and role privileges. Never assume it is pre-installed in every database.

### 34.1. Why Can `pg_stat_statements` Hide Data Skew?

A normalized template:

```sql
SELECT ... WHERE tenant_id = $1
```

merges invocations across:

- Tenant 1: 225,000 rows.
- Tenant 999: 25 rows.
- Tenant 2: 25 rows.

Aggregate stats **do not retain per-call parameter values** for breaking out hot vs cold tenants in a single `SELECT`.

### 34.2. Mean Latency Can Mislead

If cold tenants make 99% of calls, `mean_exec_time` stays low while the few hot-tenant calls crawl.

To diagnose skew, combine with:

- Application metrics tagged by hot/cold bucket.
- Traces/logs with **redacted/bucketed selectivity classes** rather than raw secrets.
- Sampled `EXPLAIN` plans on representative parameter values.
- Session custom/generic plan counters when debugging.
- Observability split across query variants.

### 34.3. Watch Planning Time Too

Some `pg_stat_statements` versions/settings track planning time separately when enabled. Never assume `mean_exec_time` includes planning time.

When evaluating `force_custom_plan`, planning overhead is part of the trade-off.

### 34.4. Never Log Raw PII Parameter Values Indiscriminately

Tenant IDs, emails, tokens, and business keys can be sensitive. Metrics usually only need coarse buckets:

```text
hot tenant
medium tenant
cold tenant
large range
short range
```

rather than logging raw parameter values verbatim.

## 35. Using `EXPLAIN` Systematically

The workhorse command of this lesson:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);
```

It executes the prepared query and reports real metrics.

### 35.1. Fields to Inspect

| Field | Question |
| --- | --- |
| Scan node | `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, or `Index Only Scan`? |
| `Index Cond` | How did the index bound the lookup? |
| `Filter` | Which predicates still ran post-lookup? |
| `Rows Removed by Filter` | How many rows were discarded after scanning? |
| `cost` | How did the planner estimate cost? |
| `rows` | How many rows did the planner predict? |
| `actual rows` | How many rows actually flowed through? |
| `loops` | How many times did the node execute? |
| `Buffers` | Blocks hit/read/dirtied/written? |
| `Heap Fetches` | Did `Index Only Scan` visit the heap? |
| `Planning Time` | Planning overhead |
| `Execution Time` | Execution time reported by `EXPLAIN` |
| `Settings` | Non-default planner settings active? |

### 35.2. `Buffers` Does Not Equal Physical Disk Reads

`shared read` counts blocks read into `shared_buffers`. The OS may serve those reads straight from the filesystem page cache.

Compare runs under controlled cache state, concurrency, and repetition.

### 35.3. Checking Only the Scan Node Is Not Enough

An `Index Scan` may execute 100,000 times inside a `Nested Loop`. A `Seq Scan` may be optimal inside a `Hash Join` reading most of a table.

For multi-table queries, read the **entire plan tree**, especially `loops`, join selectivity, and `Sort`/`Hash`/`Aggregate` nodes.

### 35.4. `EXPLAIN ANALYZE` Adds Instrumentation Overhead

`ANALYZE` instruments per-node timings and row counts, which can noticeably inflate runtime on microsecond queries.

`TIMING OFF` trims per-node timing overhead:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE orders_by_tenant(999);
```

### 35.5. `EXPLAIN ANALYZE` on DML Executes the DML

If a prepared statement is an `UPDATE`, `EXPLAIN ANALYZE EXECUTE` **actually modifies rows**.

In a lab database, you can wrap in a transaction and roll back transactional writes, remembering non-transactional side effects (sequences, WAL, I/O). Never run risky DML on production just to “check the plan.”

## 36. Diagnostic Checklist When a Query Is Sometimes Very Slow

When the exact same SQL alternates between fast and slow:

1. **Collect the SQL and representative parameter values**, including at least one hot and one cold case.
2. **Check result sizes** (row counts for each class).
3. **Verify schema/indexes** and confirm the target database.
4. **Inspect `pg_stats`** on skewed columns.
5. **Check prepared execution behavior** in driver, config, and session.
6. **Compare custom vs generic** via `plan_cache_mode` in the lab.
7. **Inspect `EXPLAIN (ANALYZE, BUFFERS)`** for both hot and cold parameters.
8. **Check optional filters**, `OR`/`COALESCE`, arrays, and ranges.
9. **Check `LIMIT`/`ORDER BY`** to see if one index serves both classes well.
10. **Check partial indexes** when a query fixes a constant status.
11. **Evaluate composite/covering indexes** when predicates co-occur frequently.
12. **Check extended stats** for correlated columns.
13. **Measure planning overhead** before forcing custom plans long-term.
14. **Benchmark under realistic concurrency** and multiple runs.
15. **Pick the minimal effective change**: query rewrite, index, stats, or transaction-scoped custom planning.
16. **Check regression risk** on other parameter classes.
17. **Measure write overhead** after adding any index.
18. **Keep bind parameters** and tenant authorization intact.
19. **Monitor post-deployment** as data distributions evolve.
20. **Document hypotheses and metrics** instead of deciding from one plan screenshot.

## 37. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Bind parameters always produce a generic plan | Can be custom or generic depending on execution/caching |
| JDBC `PreparedStatement` prepares server-side on call 1 | Depends on driver version and configuration |
| The 6th execution always switches to generic | PostgreSQL compares cost heuristics; no rigid guarantee |
| Generic plans ignore `WHERE` because values are unknown | Executor always applies bound parameters accurately |
| Custom plans are always faster | Planning overhead and uniform workloads often favor generic |
| Hot-tenant queries must always `Seq Scan` | `LIMIT`, covering indexes, and correlation can favor indexes |
| Cold-tenant queries must always `Index Scan` | Tiny tables or mismatched indexes can make `Seq Scan` cheaper |
| Having an index forces generic plans to use it | Planner picks by estimated cost, not mere index presence |
| `ANALYZE` fixes every bad generic plan | Stats don't supply runtime parameter values at generic plan time |
| Higher statistics targets are always better | Adds overhead and doesn't fix unknown generic parameters |
| Histograms give exact frequencies for every equality value | MCVs and histograms serve different roles |
| Extended stats automatically act like a composite index | They only improve planner estimates where supported |
| A partial index on `status=PENDING` works for generic `status=$1` | Generic plans cannot assume `$1` is always `PENDING` |
| You must interpolate `status` into SQL to use partial indexes | Use dedicated query variants with constant business filters and bound inputs |
| `OR $1 IS NULL` optimizes just like direct equality | Generic plans must cover both `NULL` and non-`NULL` paths |
| `COALESCE` equals a safe optional filter | `NULL` semantics and indexability can differ |
| `ANY` arrays of 1 and 1,000 elements cost the same | Array size and element skew strongly affect cost |
| A single index on `tenant_id` suffices for all tenant queries | `ORDER BY`, `status`, time ranges, and payloads still matter |
| `INCLUDE`ing every column is always good | Bloats index size/write cost without guaranteeing zero heap fetches |
| Partitioning automatically solves plan caching | Pruning helps where supported, yet doesn't remove skew |
| `force_custom_plan` should be enabled server-wide | Use narrow, evidence-backed scopes |
| `SET LOCAL` outside a transaction persists to the next query | Needs an explicit transaction wrapping target statements |
| Prepared statements are shared across the entire pool | Each physical backend session maintains its own state |
| `pg_prepared_statements` shows every session | Reflects the current session only |
| `pg_stat_statements` splits latency by tenant automatically | Aggregates by normalized query without per-call values |
| `EXPLAIN` cost is in milliseconds | Cost is an arbitrary relative planner unit |
| `EXPLAIN ANALYZE` does not execute the query | It executes it; DML modifies data |
| Fast SQL execution means a fast API | Network, serialization, row count, and app code also count |
| Testing a small tenant suffices for the whole system | Skew demands testing hot, cold, and edge cases |
| Planner tuning matters more than pagination | Returning 225,000 rows remains hugely expensive |
| Dropping a tenant filter for speed is fine | Breaks authorization and leaks data |
| One benchmark run settles everything | Cache warmth, planning, load, and variance skew single runs |

## 38. Practice Exercises with Answers

Use the `skew_lab` schema. When comparing plans, record the **actual plan on your machine**; PostgreSQL may pick different paths as cost, version, or configuration vary.

### Exercise 1. Distinguish Hot and Cold Tenants

```sql
SELECT tenant_id, COUNT(*) AS order_count
FROM skew_lab.orders
WHERE tenant_id IN (1, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

**Answer:** tenant 1 has 225,000 orders; tenant 999 has 25 orders—extreme skew.

### Exercise 2. Why Can a Generic Plan Underperform?

**Answer:** the planner cannot specialize for individual execution values. A plan ideal for 25 rows may perform terribly when returning 225,000 rows.

### Exercise 3. Does Parameter Binding Guarantee a Generic Plan?

**Answer:** no. Driver and server choose custom vs generic depending on preparation and caching settings.

### Exercise 4. Why Avoid Interpolating `tenant_id` into SQL Text?

**Answer:** introduces SQL injection risk on user inputs, type/escaping bugs, and loses query-shape reuse. Keep bind parameters.

### Exercise 5. `PREPARE` a Per-Tenant Query

```sql
PREPARE q1(integer) AS
SELECT order_id, amount
FROM skew_lab.orders
WHERE tenant_id = $1;
```

**Answer:** `q1` is a session-level prepared statement taking one `integer` parameter. Run with `EXECUTE q1(1)` or `EXECUTE q1(999)`.

### Exercise 6. Inspect the Plan of a Prepared Execution

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE q1(999);
```

**Answer:** `EXPLAIN EXECUTE` measures an active session prepared statement. Remember `DEALLOCATE q1` afterward.

### Exercise 7. Force Custom Plan in a Transaction

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE q1(1);
EXPLAIN EXECUTE q1(999);
ROLLBACK;
```

**Answer:** both custom plans see concrete parameter values, letting the planner pick distinct access paths.

### Exercise 8. Force Generic Plan in a Transaction

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE q1(1);
EXPLAIN EXECUTE q1(999);
ROLLBACK;
```

**Answer:** the generic plan cannot tailor per value; plan shape matches across both calls while actual work still differs.

### Exercise 9. What Does `plan_cache_mode = auto` Mean?

**Answer:** PostgreSQL chooses between custom and generic using cost heuristics; it does not mean the sixth call always switches to generic.

### Exercise 10. Why Can Generic Plans Lower Latency?

**Answer:** avoids repeated planning overhead when reused, especially on simple high-frequency queries where all parameter values share the same optimal access path.

### Exercise 11. Find MCVs for `tenant_id`

```sql
SELECT most_common_vals, most_common_freqs
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

**Answer:** tenant 1 should appear as an MCV with frequency near 0.9 after `ANALYZE`.

### Exercise 12. Does a Generic Plan Use the 0.9 MCV to Know `$1` Is Always 1?

**Answer:** no. It sees the overall column distribution, yet cannot assume `$1` equals `1` on every `EXECUTE`.

### Exercise 13. When Should You Run `ANALYZE`?

**Answer:** after major data changes or when stats are stale and estimates diverge; `ANALYZE` refreshes planner statistics without forcing a specific plan.

### Exercise 14. Is a High Statistics Target Always Better?

**Answer:** no. It increases statistics overhead and cannot fix a generic plan's lack of concrete parameter values at planning time.

### Exercise 15. Why Are `tenant_id` and `status` Correlated?

**Answer:** in the dataset, `DONE`/`PENDING` ratios differ sharply between the hot tenant and small tenants, so multiplying independent single-column probabilities misestimates.

### Exercise 16. Create Extended Statistics

```sql
CREATE STATISTICS orders_tenant_status_more
    (mcv, dependencies)
ON tenant_id, status
FROM skew_lab.orders;

ANALYZE skew_lab.orders;
```

**Answer:** provides multi-column distribution info where supported by the planner; does not create an index. Skip if an equivalent statistics object already exists in the lab.

### Exercise 17. Which Composite Index Fits `tenant_id = ? AND status = ?`?

**Guided Answer:** B-tree `(tenant_id, status)` is a good candidate to test, comparing `EXPLAIN` against single-column indexes and `BitmapAnd`.

### Exercise 18. Why Might a Generic Plan Skip a Partial Index for `status = $2`?

**Answer:** a generic plan cannot assume `$2` is always `'PENDING'` and therefore cannot prove the partial predicate holds.

### Exercise 19. Write a Query Variant Using a Partial Index While Parameterizing Tenant

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

**Answer:** `status` is a business constant for the endpoint while `tenant_id` remains bound. The planner can consider the `PENDING` partial index.

### Exercise 20. Why Do Generic Plans Struggle with `OR $1 IS NULL`?

**Answer:** one plan must handle both `NULL` (all rows) and non-`NULL` (selective filter), whose optimal access paths conflict.

### Exercise 21. How Should Optional Filters Be Split?

**Answer:** one SQL for “all tenants” and another with `tenant_id = ?` for a single tenant—never interpolating user input into SQL text.

### Exercise 22. What Must You Watch For with `tenant_id = COALESCE($1, tenant_id)`?

**Answer:** the expression impedes index usage, generic plans cannot specialize, and on nullable columns `NULL = NULL` fails to match `NULL` rows.

### Exercise 23. How Can an `ANY` Array with a Hot Tenant Differ from One with Only Cold Tenants?

**Answer:** matching row counts and actual costs differ vastly; unlike custom plans, a generic plan cannot specialize for the exact array contents of each call.

### Exercise 24. Why Might Huge Arrays Require a Different Design?

**Answer:** huge lists inflate planning/execution cost; consider temp tables, `VALUES` joins, batching, or normalized join tables depending on scale and pooling.

### Exercise 25. Do Short vs Long Ranges Choose Different Plans?

**Answer:** yes. Short ranges favor indexes while wide ranges favor `Seq Scan`. Custom plans estimate from real bounds.

### Exercise 26. Why Are Histograms Useful for Range Queries?

**Answer:** they capture value density across intervals, helping estimate the fraction of rows between two bounds.

### Exercise 27. Can a Hot-Tenant Query with `LIMIT 20` Still Use an Index?

**Answer:** yes. An index on `(tenant_id, created_at DESC)` can retrieve the 20 newest orders without scanning or sorting all 225,000 rows.

### Exercise 28. Why Does `Index Only Scan` Report `Heap Fetches`?

**Answer:** PostgreSQL must verify MVCC visibility on heap pages not yet marked all-visible; covering all columns alone does not eliminate heap reads.

### Exercise 29. Why Not `INCLUDE` Wide `payload` Columns in Every Index?

**Answer:** bloats indexes and slows writes/maintenance without guaranteed proportional benefit.

### Exercise 30. Can a Generic Plan Benefit from Partition Pruning?

**Answer:** yes, via execution-time pruning where supported by PostgreSQL. Still, partitioning does not eliminate skew or index/stats needs.

### Exercise 31. Should You Enable `force_custom_plan` Server-Wide?

**Answer:** not by default. It adds planning overhead to queries running well on generic plans; reserve for narrow, evidence-backed scopes.

### Exercise 32. How Must `SET LOCAL` Be Used in a Connection Pool?

**Answer:** inside a transaction wrapping the target query on the exact same connection. The setting resets when the transaction ends; never run it under autocommit expecting it to persist.

### Exercise 33. Why Can Two Physical Connections Show Different Generic/Custom Behavior?

**Answer:** prepared statements and plan caches belong to individual backend sessions, each with its own execution history.

### Exercise 34. Can You View All System Prepared Statements via `pg_prepared_statements` on One Connection?

**Answer:** no. That view shows only prepared statements belonging to the current session.

### Exercise 35. Why Is `pg_stat_statements` Insufficient to Spot Hot Tenants?

**Answer:** it aggregates normalized SQL calls without breaking out latency per parameter value. Add bucketed app metrics or sampled parameter traces.

### Exercise 36. When Estimated `rows` and `actual rows` Differ by 1,000×, What Do You Check?

**Answer:** plan mode, hot/cold parameter class, stats freshness, MCVs/extended stats, generic vs custom behavior, and predicates before altering indexes or cost knobs.

### Exercise 37. Is a `Seq Scan` on a Hot Tenant Definitely a Bug?

**Answer:** no. When returning 90% of the table, sequential scanning is often the cheapest plan.

### Exercise 38. Is an `Index Scan` on a Hot Tenant Definitely a Bug?

**Answer:** also no. With `ORDER BY`/`LIMIT` or a covering index, an index path can be optimal; inspect actual `EXPLAIN` metrics.

### Exercise 39. Does `EXPLAIN ANALYZE` on an `UPDATE` Actually Run the `UPDATE`?

**Answer:** yes. Use it in a lab while accounting for rollbacks and side effects; never run risky production DML just to inspect a plan.

### Exercise 40. Outline an Optimization Plan for a Multi-Tenant Endpoint

**Guided Answer:**

1. Measure hot vs cold tenant call frequencies.
2. Benchmark the same SQL across both hot and cold parameters before/after warm-up.
3. Compare `force_generic_plan` vs `force_custom_plan` in the lab.
4. Inspect MCVs/stats; run `ANALYZE` if stale.
5. Review query shape, `WHERE`, `ORDER BY`, and `LIMIT`.
6. Design/adjust indexes for the real workload.
7. Consider query variants or partial indexes if appropriate.
8. Keep bind parameters and tenant authorization intact.
9. Scope `plan_cache_mode` narrowly only if proven necessary.
10. Track p95/p99, planning overhead, and write costs post-rollout.

## 39. End-to-End Lab Workflow: Reproduce, Measure, Fix

Follow this workflow in your lab database:

### Step 1. Verify Data Skew

```sql
SELECT
    tenant_id,
    COUNT(*) AS n
FROM skew_lab.orders
WHERE tenant_id IN (1, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

### Step 2. Check Indexes and Statistics

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
ORDER BY indexname;

SELECT
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

### Step 3. Prepare the Query

```sql
PREPARE skew_check(integer) AS
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;
```

### Step 4. Measure Custom Plan

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(999);

ROLLBACK;
```

### Step 5. Measure Generic Plan

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(999);

ROLLBACK;
```

### Step 6. Inspect Prepared Plan Counters

```sql
SELECT
    name,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
WHERE name = 'skew_check';
```

### Step 7. Reset and Clean Up

```sql
DEALLOCATE skew_check;
```

`SET LOCAL` already reset when the transaction ended. If you ran session-level `SET` outside this lab, run `RESET plan_cache_mode` in that session.

### Step 8. Record Results

Compare in a table:

| Parameter | Plan Mode | Scan Node | Estimated Rows | Actual Rows | Shared Reads/Hits | Planning Time | Execution Time |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| Hot: 1 | Custom | Measure | Measure | 225000 | Measure | Measure | Measure |
| Cold: 999 | Custom | Measure | Measure | 25 | Measure | Measure | Measure |
| Hot: 1 | Generic | Measure | Measure | 225000 | Measure | Measure | Measure |
| Cold: 999 | Generic | Measure | Measure | 25 | Measure | Measure | Measure |

If your run shows little difference, that is still a valid finding: **an index, data locality, cache, or cost model may already let generic plans perform fine** on that slice. Never force production config just to manufacture a dramatic “generic is slow” result.

## 40. Pre-Deployment Checklist

| Question | What to Verify |
| --- | --- |
| Which parameter values are hot/cold? | Real distribution and call share |
| Does query shape shift on large tenants? | Row count, payload, pagination |
| Is the statement server-prepared? | Actual driver, config, and session |
| Is generic or custom plan running? | `EXPLAIN`, `plan_cache_mode`, session counters |
| Are hot values captured in MCVs? | `pg_stats` after `ANALYZE` |
| Are statistics stale? | Bulk loads/updates and autovacuum |
| Are multiple columns correlated? | Appropriate extended statistics |
| Are predicates indexable? | Avoid casts/expressions blocking paths |
| Do primary queries have composite indexes? | Tenant + status/time per workload |
| Do partial index predicates fit generic plans? | Business constant vs unknown parameter |
| Are optional `OR`/`COALESCE` filters hurting? | Try separate query variants |
| Do `ANY` array sizes vary widely? | Test small, large, and hot-ID arrays |
| Do time ranges vary widely in span? | Test short vs long spans |
| Is `ORDER BY + LIMIT` present? | Matching B-tree sort order |
| Does `Index Only Scan` have high `Heap Fetches`? | Visibility map / `VACUUM` |
| Is partitioning/pruning used? | Plan-time vs execution-time pruning |
| Do queries return huge row counts? | Pagination, aggregation, streaming |
| Do p95/p99 diverge across tenant tiers? | Application-level metrics |
| Does `pg_stat_statements` hide skew? | Bucketed workload telemetry |
| Was planning time compared? | Avoid forcing custom plans needlessly |
| Do extra indexes slow down writes? | Measure DML, WAL, and storage |
| Is pool/session state clean? | No leaked `SET` or `PREPARE` state |
| Is `SET LOCAL` wrapped in a transaction? | Verify transaction boundaries |
| Were JDBC driver version/config tested? | Never guess prepare thresholds |
| Is SQL injection prevented? | Keep bind parameters |
| Is tenant authorization intact? | Never drop security filters |
| Is post-rollout monitoring planned? | Track latency and plan regressions |
| Is a rollback plan ready? | Controlled config/index rollback |
| Was real concurrency tested? | Never conclude from one idle connection |
| Is measurement provenance recorded? | Version, schema, indexes, cache state |

## 41. Summary

**Parameterized queries** are sound application design, yet under heavy data skew a single SQL structure can demand **radically different plans** across parameter values.

Key takeaways:

1. **Data skew:** one value may match 90% of a table while another matches 0.01%. A single index scan rarely fits both blindly.
2. **Parameter binding differs from plan caching:** JDBC `PreparedStatement` does not automatically mean the server uses a generic plan.
3. **Custom plans:** inspect each execution's parameter values to pick selectivity-appropriate paths, trading off planning overhead.
4. **Generic plans:** reuse one plan shape across values, saving planning overhead yet risking poor choices when selectivity varies wildly.
5. **`plan_cache_mode`:** keep `auto` as your baseline; use `force_custom_plan` and `force_generic_plan` for controlled comparisons and narrow overrides.
6. **`PREPARE`/`EXECUTE` + `EXPLAIN (ANALYZE, BUFFERS)`:** the standard way to reproduce and measure hot vs cold parameter behavior in a lab.
7. **`pg_prepared_statements`:** inspects prepared statements and generic/custom counters in the current session—not cluster-wide.
8. **`ANALYZE` / `pg_stats`:** MCVs, frequencies, histograms, and correlation inform planner estimates, yet good stats still don't tell a generic plan what `$1` will be at runtime.
9. **Extended statistics:** help correlated multi-column predicates, without replacing custom/generic plan analysis.
10. **Index design:** single, composite, partial, and covering indexes serve distinct patterns; no single index fits every query.
11. **Partial indexes:** generic queries parameterizing the predicate column cannot prove membership; **query variants with business constants** keep partial indexes usable while binding other inputs.
12. **Optional filters and arrays:** one overly generic SQL hampers generic planning. Split clean query shapes with safe bind parameters where helpful.
13. **`ORDER BY ... LIMIT`:** can let one ordered index plan serve both hot and cold tenants efficiently despite massive row-count differences.
14. **Partitioning:** helps via pruning, yet never eliminates skew or index/stats requirements on its own.
15. **Measurement:** inspect estimated vs actual rows, buffers, planning/execution time, p95/p99, returned row counts, and per-tier metrics.
16. **Application hygiene:** preserve parameter binding, manage pool/session state cleanly, and enforce tenant isolation.

Core lab template:

```sql
PREPARE q(integer) AS
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;

BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(1);
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(999);
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(1);
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(999);
ROLLBACK;

DEALLOCATE q;
```

**Core principle:** when a parameterized query is “fast sometimes, slow other times,” do not ask only **“Does the SQL have an index?”** Ask **“Which values are hot, how well does the planner know the distribution, is a custom or generic plan running, and which access path fits each parameter class?”** That gives you a safe, measurable, and durable foundation for tuning parameterized queries in PostgreSQL.
