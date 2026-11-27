# Impact of CTEs, User-Defined Functions, and Optimization Barriers in PostgreSQL

**Common Table Expressions (CTEs)** and **user-defined functions** make SQL concise, easy to break into named parts, reuse logic, and encapsulate business rules. Yet a more readable SQL query **does not necessarily** produce a better execution plan. Depending on PostgreSQL version, reference count, function volatility, and semantic constraints, the planner may fold parts together for joint optimization or preserve an **optimization barrier**.

An optimization barrier can cause:

- Outer `WHERE` predicates not to be pushed deep into the inner query (*predicate pushdown*).
- The planner to be unable to reorder joins across an intermediate step.
- A large intermediate dataset to be computed or buffered before only a few needed rows remain.
- SQL logic inside a function to appear as a `Function Scan` or function call rather than base tables, filters, and index paths the planner can optimize directly.
- Conversely, an expensive expression to be evaluated repeatedly when a query part is folded into multiple branches, making the plan slower despite removing materialization.

Therefore, the goal is neither “always remove CTEs” nor “always use `NOT MATERIALIZED`.” The goal is to **understand when PostgreSQL may optimize across a boundary, when that boundary helps, and how to measure with `EXPLAIN`**.

This lesson belongs to the **Query Optimization** chapter in the *Database Engine Relational PostgreSQL* module. It covers CTE behavior from PostgreSQL 12 onward, older-version behavior, `MATERIALIZED` and `NOT MATERIALIZED`, recursive and data-modifying CTEs, SQL-function inlining, PL/pgSQL, volatility, `COST`/`ROWS`, predicate sargability, function execution plans, and practical performance diagnostics.

## 1. What Does the Planner Optimize?

PostgreSQL plans most ordinary queries before executing them. The planner evaluates multiple execution strategies and estimates costs based on:

- Table row counts and predicate selectivity.
- Data statistics collected by `ANALYZE`.
- Indexes and table access paths.
- Join order, join algorithms, sorting, and aggregation methods.
- CPU, I/O, and parallelism costs.
- Eligibility to rewrite SQL expressions while preserving semantics.
- Constraints that prevent or restrict freely transforming part of a query.

Example:

~~~sql
SELECT event_id, tenant_id
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

The planner can consider Seq Scan, Index Scan, Bitmap Scan, or other access paths depending on schema and statistics.

Yet if the same logic sits inside a forced-materialized CTE or a function that resists inlining, the planner may not see **all predicates together** when planning the table scan.

### 1.1. What Is an Optimization Barrier?

An *optimization barrier* is a boundary across which certain algebraic rewrites or execution-order changes **are disallowed or infeasible**. That boundary can arise from:

- Explicit materialization of a CTE.
- Recursive queries.
- Data-modifying statements inside a CTE.
- `VOLATILE` functions or functions with side effects.
- PL/pgSQL functions that cannot be inlined like plain SQL expressions.
- `SECURITY DEFINER`, function-level `SET` configuration, or security/privilege checks.
- Operators like `LIMIT`, `DISTINCT`, aggregates, and window functions, which impose semantic transformation limits.
- `security_barrier` views or specific security isolation requirements.

Not all of these share a single mechanism. What they have in common is **constraining the search space the planner can explore**.

### 1.2. Barriers Are Not Always Bad

A barrier can help:

- Avoid evaluating an expensive expression multiple times.
- Share one intermediate result across multiple branches.
- Preserve semantics of operations with side effects.
- Enforce security boundaries under elevated privileges.
- Express query structures that cannot be represented via simple flattening.

The real task is **choosing the right boundary for the right workload**.

## 2. What Is a CTE?

A CTE is declared with `WITH` before the main SQL statement:

~~~sql
WITH selected_events AS (
    SELECT event_id, tenant_id, event_type
    FROM events
    WHERE event_type = 'purchase'
)
SELECT *
FROM selected_events
WHERE tenant_id = 42;
~~~

`selected_events` names a query expression scoped to that statement.

### 2.1. A CTE Is a Named Construct, Not Automatically a Physical Temp Table

Learners often picture it as:

~~~text
Step 1: run selected_events and write everything into a temp table.
Step 2: SELECT from the temp table.
~~~

That describes how a **materialized CTE** can execute, yet it is **not the universal rule for all CTEs** in modern PostgreSQL.

The planner can fold a CTE into the outer query and optimize them as one combined query.

### 2.2. How Does a CTE Differ from a Subquery?

The same logic can be written as:

~~~sql
SELECT *
FROM (
    SELECT event_id, tenant_id, event_type
    FROM events
    WHERE event_type = 'purchase'
) AS selected_events
WHERE tenant_id = 42;
~~~

In result-set semantics, the two queries can be equivalent. Yet how the planner transforms them depends on:

- PostgreSQL version.
- How many times the CTE is referenced.
- Whether the CTE is recursive.
- Whether the CTE contains DML or volatile functions.
- `MATERIALIZED`/`NOT MATERIALIZED` directives.
- Inner SQL constructs such as aggregates, `LIMIT`, or window functions.

### 2.3. CTEs Help Structure Logic

CTEs are great for naming steps:

~~~sql
WITH filtered AS (
    SELECT ...
),
aggregated AS (
    SELECT ...
    FROM filtered
    GROUP BY ...
)
SELECT ...
FROM aggregated;
~~~

There is no reason to abandon CTEs simply out of fear that “`WITH` is slow.” Inspect **the actual plan**.

## 3. PostgreSQL Before vs. From Version 12: A Crucial Difference

A major source of confusion comes from SQL tuning articles written for older PostgreSQL versions.

### 3.1. PostgreSQL 11 and Earlier

Prior to PostgreSQL 12, standard `SELECT` CTEs acted as a stronger **optimization fence**: the planner did not automatically fold CTEs into outer queries under modern rules.

A statement like:

~~~sql
WITH x AS (
    SELECT *
    FROM big_table
)
SELECT *
FROM x
WHERE id = 42;
~~~

could end up materializing a much wider intermediate result than filtering directly, because the outer predicate was not pushed into the CTE scan.

### 3.2. PostgreSQL 12 Onward

For **non-recursive** CTEs that are side-effect-free `SELECT` statements under PostgreSQL rules, the planner can **fold/inline** them into the parent query.

Key default rules:

- Eligible CTEs **referenced once** are usually folded into the outer query by default.
- Eligible CTEs **referenced multiple times** are usually materialized by default.
- `MATERIALIZED` requests preserving a materialization boundary.
- `NOT MATERIALIZED` requests allowing folding even with multiple references, though it may repeat work.
- Recursive CTEs, data-modifying CTEs, or CTEs with properties disallowing folding **do not become inlineable simply by adding `NOT MATERIALIZED`**.

Words like “usually” and “eligible” matter. Never describe PostgreSQL 12+ as “every CTE is always inlined.”

### 3.3. Checking Server Version

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

If you must support PostgreSQL 11, do not blindly copy newer `AS MATERIALIZED` or `AS NOT MATERIALIZED` syntax without checking compatibility.

### 3.4. Do Not Apply Legacy Lore to Modern Systems

Blanket claims like “CTEs always block pushdown in PostgreSQL” are **no longer generally true**. Conversely, claiming “modern CTEs never materialize” is also wrong.

## 4. Single-Reference CTEs: Folding and Predicate Pushdown

Consider:

~~~sql
WITH events_filtered AS (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

For an eligible single-reference `SELECT` CTE on modern PostgreSQL, the planner can combine the predicates:

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
  AND tenant_id = 42
~~~

directly during the scan of `events`.

### 4.1. Why Does This Help?

Suppose you have:

~~~sql
CREATE INDEX events_tenant_time_idx
ON events (tenant_id, occurred_at);
~~~

When the planner sees both predicates while picking an access path, it can leverage that index far better than seeing only the time condition inside the CTE.

### 4.2. It Does Not Force Index Usage

The planner may still choose a Seq Scan if:

- The table is small.
- Predicates match a large share of rows.
- Pages are cached and scan cost is low.
- No index fits well enough.
- Row estimates show no advantage.

Check `EXPLAIN` rather than guessing from `WITH` syntax.

### 4.3. Folding Never Changes Logical Output

The planner only applies rewrites that preserve SQL semantics. A CTE with `LIMIT` or structures whose output changes if predicates move cannot arbitrarily be turned into a different query.

## 5. `AS MATERIALIZED`: Deliberately Keeping an Intermediate Result

Declaration:

~~~sql
WITH events_filtered AS MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

Here, the CTE enforces a materialization boundary. The `tenant_id = 42` condition stays **outside** the CTE and is not pushed directly into the inner table scan as a folded CTE predicate.

### 5.1. Mental Model

~~~text
Unmaterialized, eligible for folding:
  Scan events
    Filter occurred_at >= ...
    Filter tenant_id = 42
  -> return rows

MATERIALIZED:
  Scan events
    Filter occurred_at >= ...
  -> intermediate CTE result

  CTE Scan
    Filter tenant_id = 42
  -> return rows
~~~

### 5.2. Potential Costs of Materialization

- CPU and I/O to build the intermediate result.
- Memory and possible temp disk spills if data is large.
- Outer predicates cannot push into the CTE scan.
- Join reordering across the boundary can be restricted.
- Plans use `CTE Scan` instead of viewing base relations directly.

### 5.3. Never Claim a Materialized CTE Always Reads Every Row Immediately

In PostgreSQL, producing CTE rows can depend on **how many rows the consumer actually pulls**. For instance, if the outer query has `LIMIT` and does not require consuming everything, the CTE may not be fully evaluated before the outer query stops.

Still, `ORDER BY`, joins, aggregates, or multiple consumers can demand most or all rows. **Never treat an outer `LIMIT` as a performance guarantee** when the query shape forces most data to be read.

### 5.4. When Is `MATERIALIZED` Helpful?

An **expensive** CTE shared by multiple parts of a query may justify computing once and reusing. Materialization is also a deliberate tool to prevent unwanted plan regressions when backed by measured evidence.

Yet it is not a “safer/faster default mode” for every CTE.

## 6. `AS NOT MATERIALIZED`: Allowing Folding Into the Parent

Syntax:

~~~sql
WITH events_filtered AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

For eligible CTEs, `NOT MATERIALIZED` tells the planner to allow folding instead of creating a forced shared result.

### 6.1. Single References Rarely Need It Explicitly

On PostgreSQL 12+, an ordinary non-recursive, non-volatile `SELECT` CTE used once usually folds by default. Adding `NOT MATERIALIZED` clarifies intent yet **does not necessarily change the plan**.

### 6.2. Multiple References Are Where It Matters Most

When the same CTE appears twice, PostgreSQL normally materializes it by default. `NOT MATERIALIZED` lets each branch optimize independently with its own predicates.

### 6.3. Trade-Off: Repeated Computation

If the CTE contains CPU-heavy expressions, large joins, or expensive work, folding multiple times can duplicate that work across branches.

**Better pushdown** does not automatically mean **less total work**.

### 6.4. Not an Unconditional Directive

PostgreSQL will not fold a recursive CTE or one whose semantics forbid folding merely because `NOT MATERIALIZED` was written. See the sections on recursive, volatile, and data-modifying CTEs.

## 7. Comparing Materialization and Folding via `EXPLAIN`

Two variants:

~~~sql
WITH filtered AS MATERIALIZED (
    SELECT event_id, tenant_id, event_type, occurred_at
    FROM events
    WHERE event_type = 'purchase'
)
SELECT event_id
FROM filtered
WHERE tenant_id = 42;
~~~

and:

~~~sql
WITH filtered AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, event_type, occurred_at
    FROM events
    WHERE event_type = 'purchase'
)
SELECT event_id
FROM filtered
WHERE tenant_id = 42;
~~~

### 7.1. Plan Signatures

When materialization occurs, you typically see:

~~~text
CTE filtered
  -> ...
...
CTE Scan on filtered
  Filter: tenant_id = 42
~~~

When folding happens, you see scans/joins directly on `events` with no `CTE Scan` node for that CTE.

### 7.2. Look Beyond Node Type

Compare:

- Estimated `rows` vs. `actual rows`.
- Whether filters sit in `Index Cond`, `Filter`, or `CTE Scan`.
- `Rows Removed by Filter`.
- `Buffers`.
- Total runtime and per-node runtime.
- Iteration count per node (`loops`).
- Temporary reads/writes when intermediates are large.
- Planning time and execution time.

### 7.3. Never Conclude from a Single Run

Caching, background load, and planning overhead vary between runs. Test on representative data with matching parameters before and after.

## 8. Multi-Reference CTEs

Example:

~~~sql
WITH base AS (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

When an eligible CTE is referenced by both `a` and `b`, modern PostgreSQL usually **materializes by default** to avoid computing `base` twice.

### 8.1. Upside of Sharing Results

If `base` is very expensive and both branches need most of it, computing once can save substantial work.

### 8.2. Downside

The `a.tenant_id = 42` filter cannot push into the shared CTE because `b` also consumes it. Thus the shared CTE may build rows across many tenants unneeded by branch `a`.

### 8.3. Trying `NOT MATERIALIZED`

~~~sql
WITH base AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

Now the planner can optimize each reference separately, pushing branch filters deeper and utilizing appropriate indexes.

### 8.4. When `NOT MATERIALIZED` Backfires

If both branches still scan/compute almost all of `base` and run heavy expressions, folding doubles the work.

### 8.5. Takeaway for Multi-Reference CTEs

There is no one-size-fits-all answer:

| Workload Trait | What to Measure |
|---|---|
| Expensive shared step, branches read most rows | `MATERIALIZED` or default |
| Each branch filters down to a small distinct slice | `NOT MATERIALIZED` |
| Single reference, ordinary `SELECT` | Usually leave default |
| Contains volatile functions | Semantics must hold; `NOT MATERIALIZED` won't force unsafe folding |
| Recursive or data-modifying | Distinct mechanisms, not simple folding |

## 9. Predicate Pushdown Across CTEs

**Predicate pushdown** is pushing filter conditions down to the earliest valid data-access step without changing semantics.

Example:

~~~sql
WITH all_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
)
SELECT *
FROM all_events
WHERE tenant_id = 42;
~~~

Because the CTE is materialized, the inner scan of `events` does not receive the outer tenant filter to shrink the CTE output.

### 9.1. Put Safe Shared Filters Inside the CTE

~~~sql
WITH tenant_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE tenant_id = 42
)
SELECT *
FROM tenant_events;
~~~

Even when materialization is desired, putting a filter that is **semantically valid for every consumer** inside the CTE shrinks the intermediate buffer.

### 9.2. Beware Shared Consumers

If the CTE feeds both `tenant=42` and `tenant=77`, pushing `tenant_id=42` inside the shared CTE breaks the `tenant=77` branch.

### 9.3. Not Every Outer Predicate Can Legally Move Inside

If a CTE contains `LIMIT`, window functions, or aggregates, swapping filter order can alter results.

Example:

~~~sql
WITH top_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    ORDER BY payload DESC, event_id
    LIMIT 100
)
SELECT *
FROM top_events
WHERE tenant_id = 42;
~~~

This means: **take the global top 100 rows, then keep only tenant 42**. You cannot rewrite it into “top 100 for tenant 42,” because those are different queries.

## 10. CTEs and Join Reordering

The planner can normally choose join orders among relations when transformations are legal.

Conceptual example:

~~~sql
SELECT ...
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN items AS i
  ON i.order_id = o.order_id
WHERE c.region = 'north';
~~~

With a highly selective filter on `customers`, the planner may start from the small customer slice and join into `orders`.

Yet if `orders` and `items` sit locked inside a large materialized CTE, the planner loses freedom to reorder all relations jointly.

### 10.1. Visualization

~~~text
No barrier:
  customers(region='north')
         |
      JOIN orders
         |
      JOIN items

Materialized CTE:
  [orders JOIN items] -> large CTE result
                         |
                      JOIN customers(region='north')
~~~

This is conceptual—PostgreSQL's planner does not guarantee those exact trees.

### 10.2. Join Order Also Depends on Semantics

Outer joins, lateral references, subquery semantics, join-collapse limits, and security barriers also constrain reordering.

Never claim “`NOT MATERIALIZED` lets the planner reorder every join freely.”

## 11. CTEs with Expensive Expressions: Sometimes Materialization Pays Off

Suppose one stage calculates a heavy score per event and feeds multiple joins/checks:

~~~sql
WITH scored AS MATERIALIZED (
    SELECT
        event_id,
        tenant_id,
        (payload::numeric * payload::numeric + 17) AS score
    FROM events
)
SELECT COUNT(*)
FROM scored AS a
JOIN scored AS b
  ON a.event_id = b.event_id
WHERE a.score > 100000;
~~~

Here `MATERIALIZED` provides one shared result instead of duplicating the CTE computation for both references.

### 11.1. What Can Be Expensive?

- Expressions with heavy arithmetic or function calls.
- Multi-row aggregations.
- Multi-way joins inside the CTE.
- Sorting.
- Large scans over source relations.

### 11.2. Materialization Still Has a Price

If only a few rows survive filtering/joining, computing `scored` for everything wastes work. `NOT MATERIALIZED` can let each branch filter earlier or prune unused expressions.

### 11.3. Does Referencing a Function Twice Mean It Runs Twice?

Never deduce call counts from SQL source appearance alone. The planner may inline, prune dead expressions, share, or duplicate expressions within semantic bounds. Check `EXPLAIN (ANALYZE, VERBOSE)` and profile when invocation count matters.

### 11.4. Do Not Rely on CTEs to Enforce Side-Effect Ordering

If a function has side effects, declare volatility accurately and design explicit execution order/control. Never rely on vague assumptions about materialization to sequence business side effects.

## 12. CTEs with `VOLATILE` Functions: Why Free Folding Is Disallowed

A CTE calling a function whose value can vary per call, such as `random()`, differs from a pure expression CTE.

~~~sql
WITH sample AS (
    SELECT random() AS value
)
SELECT value, value
FROM sample;
~~~

Here PostgreSQL must preserve the semantics of a single sampled value produced by the CTE rather than turning it into two independent `random()` evaluations.

### 12.1. Volatility Is a Contract with the Planner

PostgreSQL classifies functions as:

- `VOLATILE`.
- `STABLE`.
- `IMMUTABLE`.

A `SELECT` CTE containing a **volatile function** is not treated as a simple side-effect-free CTE eligible for free folding.

### 12.2. `NOT MATERIALIZED` Does Not Override Safety Checks

~~~sql
WITH sample AS NOT MATERIALIZED (
    SELECT random() AS value
)
SELECT value FROM sample;
~~~

Do not expect `NOT MATERIALIZED` to make PostgreSQL ignore semantic protections for volatile expressions. Eligibility rules still apply.

### 12.3. Never Falsely Mark Functions `IMMUTABLE` to Force Folding

If a function depends on randomness, current time, session state, mutable table data, or side effects, lying and labeling it `IMMUTABLE` can produce wrong answers and corrupt indexes/cached plans.

Volatility correctness matters more than getting a prettier plan.

## 13. Recursive CTEs Are Different

Recursive CTEs follow the form:

~~~sql
WITH RECURSIVE tree AS (
    SELECT ...
    UNION ALL
    SELECT ...
    FROM tree ...
)
SELECT ...
FROM tree;
~~~

The recursive term consumes output from prior iterations. It cannot simply be folded into an outer query like an ordinary `SELECT` CTE.

### 13.1. Recursive Plan Nodes

In `EXPLAIN`, you may see:

- `Recursive Union`.
- `WorkTable Scan`.
- `CTE Scan`.

These show recursive/working-table execution—not proof of a “badly optimized” query.

### 13.2. Cost Scales with Depth and Branching Factor

On graphs with many nodes and edges, recursive queries can generate large intermediate sets. Key concerns include:

- Termination conditions.
- Cycle detection.
- Indexes on link keys such as `parent_id`.
- Deduplication where appropriate.
- Business depth limits.

### 13.3. `NOT MATERIALIZED` Does Not Turn Recursion Into a Regular Join

An iterative structure cannot become a single-pass scan merely by adding a keyword.

## 14. Data-Modifying CTEs Have Their Own Semantics

PostgreSQL supports data-modifying statements inside `WITH` where permitted:

~~~sql
WITH created AS (
    INSERT INTO events (
        tenant_id, event_type, occurred_at, payload
    )
    VALUES (42, 'purchase', CURRENT_TIMESTAMP, 100)
    RETURNING event_id, tenant_id
)
SELECT event_id, tenant_id
FROM created;
~~~

### 14.1. `RETURNING` Streams Rows Outward

`INSERT ... RETURNING` produces a result set for the outer query to read. Never treat a data-modifying CTE like a side-effect-free `SELECT` CTE merely because it lives inside `WITH`.

### 14.2. Side Effects and Execution Timing

Data-modifying CTEs follow PostgreSQL's dedicated DML-in-`WITH` rules; write clauses in `WITH` are not discarded arbitrarily like unused `SELECT` expressions. When multiple write CTEs exist in one `WITH`, actual execution order is not strictly guaranteed by source order; design them not to rely on implicit cross-branch ordering.

### 14.3. Avoid Uncontrolled Double Writes to the Same Row

Updating or modifying the same row across multiple data-modifying CTE branches in one statement can produce behavior the application did not intend. Write a single clear `UPDATE` or well-defined protocol when updating multiple fields of one row.

### 14.4. Folding Is Not the Main Lever Here

Here, data correctness, snapshots, `RETURNING`, and transactional behavior matter far more than whether `MATERIALIZED` is faster.

## 15. SQL Functions vs. PL/pgSQL Functions: Two Different Barriers

PostgreSQL supports writing functions in multiple languages, most commonly:

- `LANGUAGE sql`: body written directly in SQL.
- `LANGUAGE plpgsql`: procedural language with variables, control flow, loops, and multiple SQL statements.

Both can return scalars or sets of rows. Yet **how deeply the planner can see inside them** differs.

### 15.1. Simple SQL Functions Can Be Inlined

Under the right conditions, PostgreSQL can substitute a SQL function call with its underlying SQL expression or query body, enabling joint optimization.

### 15.2. PL/pgSQL Is Usually a Harder Boundary

A PL/pgSQL function executes through the function-call handler, and SQL statements inside it are planned separately via PL/pgSQL's execution engine. The outer query's planner **does not fold procedural PL/pgSQL control flow directly into the caller's plan** like a simple SQL expression.

### 15.3. Never Assume `LANGUAGE sql` Always Inlines

Even `LANGUAGE sql` has eligibility checks: body structure, volatility, return mode, `SECURITY DEFINER`, function-level `SET` clauses, parameter types, and other conditions can block inlining.

## 16. Scalar SQL Function: Example of an Inlineable Function

Create a function computing price with tax:

~~~sql
CREATE FUNCTION calculate_price_with_tax(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * 1.10, 2);
$$;
~~~

Suppose we run:

~~~sql
SELECT calculate_price_with_tax(100.00);
~~~

Expression-wise, the function does a straightforward calculation.

### 16.1. What Can the Planner Do?

An eligible scalar SQL function call can be inlined into the expression:

~~~sql
round(100.00 * 1.10, 2)
~~~

Further optimizations like constant folding may then apply depending on volatility and statement preparation.

### 16.2. Inlining Is Not a Guaranteed API Contract

Do not build correctness on forced inlining. It is an internal conditional optimization; PostgreSQL version, signature, and attributes can alter the chosen plan.

### 16.3. Functions Must Remain Semantically Accurate

If a function reads mutable data yet is labeled `IMMUTABLE`, the planner may pre-evaluate or cache stale values. Broad optimization freedom is never worth wrong results.

## 17. PL/pgSQL Functions Can Hide Filters

A set-returning query function:

~~~sql
CREATE FUNCTION get_events_plpgsql(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE plpgsql
STABLE
ROWS 2000
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
END;
$$;
~~~

Caller query:

~~~sql
SELECT *
FROM get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

The outer planner may see a `Function Scan` with an outer filter `event_type='purchase'`, rather than combining that filter into the scan inside the function.

### 17.1. Outer Predicates Can Arrive Too Late

The function may already return a huge batch of tenant-42 events before the outer query filters `event_type`. When the function emits many rows, that overhead becomes significant.

### 17.2. SQL Inside PL/pgSQL Still Uses the Planner

That does **not mean `SELECT` statements inside PL/pgSQL run unoptimized**. Inner SQL statements are still planned by PostgreSQL. The catch is that the caller's planner **cannot freely push outer predicates through a procedural function boundary**.

### 17.3. Improvement: Pass Filters as Parameters

~~~sql
CREATE FUNCTION get_events_plpgsql_filtered(
    p_tenant INTEGER,
    p_type TEXT
)
RETURNS SETOF events
LANGUAGE plpgsql
STABLE
ROWS 100
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant
      AND e.event_type = p_type;
END;
$$;
~~~

Then call:

~~~sql
SELECT *
FROM get_events_plpgsql_filtered(42, 'purchase');
~~~

Now the **inner SQL** sees both predicates from the start, even though the function itself remains a boundary.

### 17.4. Parameters Do Not Solve Everything

Join order with outer tables, returned row estimates, and `Function Scan` overhead still matter. If procedural logic isn't actually needed, writing the SQL directly or using an inlineable SQL table function may be better.

## 18. SQL Table Functions: Eligible for Folding Into the Caller

Create a SQL function returning tenant events:

~~~sql
CREATE FUNCTION get_events_sql(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE sql
STABLE
ROWS 2000
AS $$
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

Call it:

~~~sql
SELECT event_id, event_type
FROM get_events_sql(42)
WHERE event_type = 'purchase';
~~~

### 18.1. Potential Benefit of Table-Function Inlining

If eligible for inlining, the planner can expand it to:

~~~sql
SELECT event_id, event_type
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

From there it can pick indexes or join orders using both filters.

### 18.2. Signs in `EXPLAIN`

If inlined, the plan shows direct scans on `events` rather than a `Function Scan` on `get_events_sql`.

If not inlined, `Function Scan` still appears. Never guess merely from `LANGUAGE sql`.

### 18.3. Why Does `STABLE` Matter?

A read-only SQL table function reading tables is normally marked `STABLE` when semantically accurate. Volatility is one of the criteria the planner inspects to determine safe transformations.

### 18.4. Never Mark Table-Reading Functions `IMMUTABLE`

If a function fetches tenant events from `events`, output depends on table contents at query time. It is **not `IMMUTABLE`** in the sense of always returning the same result regardless of database mutations.

## 19. What Determines Inlining Eligibility?

There is no single short checklist covering every function kind and version, yet common deciding factors include:

| Factor | Potential Impact |
|---|---|
| `LANGUAGE sql` | Lets the planner inspect and transform the SQL body when valid |
| Clean single-SQL body | Much easier to inline than procedural/multi-statement bodies |
| Scalar vs. set-returning | Different inlining rules apply |
| `VOLATILE`/`STABLE`/`IMMUTABLE` | Governs reordering and pre-evaluation safety |
| `STRICT` | Affects inlining rules, especially for table functions |
| `SECURITY DEFINER` | Usually blocks inlining due to privilege semantics |
| Function-level `SET` | Can block inlining because it alters execution GUC context |
| Data types and parameter usage | Can affect eligibility |
| Output constructs (`ORDER BY`/`LIMIT`) | Restrict transforms that could alter semantics |

### 19.1. Scalar and Table-Function Inlining Rules Differ

A simple scalar SQL function may inline in scenarios where a SQL set-returning function fails eligibility checks, and vice versa because set-returning functions preserve row-set rules.

### 19.2. Never Strip Security Controls to Force Inlining

If a function requires `SECURITY DEFINER` to execute under owner privileges, that is a real security boundary. Never switch to `SECURITY INVOKER` solely for a prettier plan if doing so breaks authorization.

### 19.3. When Performance Matters, Measure Caller Plans

Compare `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` across:

1. Direct query.
2. SQL function.
3. PL/pgSQL function.

Use matching predicates and data, observing boundaries and intermediate row counts.

## 20. `VOLATILE`, `STABLE`, `IMMUTABLE` and Optimization

Volatility is a core planner contract.

### 20.1. `VOLATILE`

The function may return different outputs even within a single statement or cause side effects—such as built-in `random()` and `clock_timestamp()`.

The planner must be conservative about changing call counts or evaluation order.

### 20.2. `STABLE`

For given arguments, the function is expected to return consistent results **within a single statement** under PostgreSQL's contract. It may depend on database state or environment that changes across statements.

For example, `CURRENT_TIMESTAMP`/`now()` reflects transaction timestamp semantics—it is not “immutable forever.”

### 20.3. `IMMUTABLE`

For identical inputs, the function must durably return identical outputs regardless of database changes, time, or session state under PostgreSQL rules.

Pure arithmetic fits naturally:

~~~sql
CREATE FUNCTION double_integer(p_value INTEGER)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_value * 2;
$$;
~~~

### 20.4. Common Bug: Marking Table-Reading Functions `IMMUTABLE`

~~~sql
CREATE FUNCTION get_current_price(p_product_id BIGINT)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT price
    FROM products
    WHERE product_id = p_product_id;
$$;
~~~

This is **semantically wrong** whenever prices in `products` can change. Never copy this pattern as valid design.

### 20.5. Consequences of Mislabeling Volatility

The planner can constant-fold or reuse stale values under the `IMMUTABLE` assumption, especially with prepared statements and cached plans. It may also be accepted into expression indexes or generated columns where results drift inconsistently.

### 20.6. Volatility Is About Correctness, Not Just Speed

Correct volatility classification is a **correctness requirement**. Optimization must never sacrifice accurate results.

## 21. User-Defined Functions and `COST`

The planner cannot automatically tell whether a PL/pgSQL function takes 1 µs or 100 ms. PostgreSQL lets you supply a cost estimate via `COST`:

~~~sql
CREATE FUNCTION expensive_check(p_value INTEGER)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
COST 200
AS $$
BEGIN
    RETURN p_value > 0;
END;
$$;
~~~

This snippet illustrates `COST` syntax only; the actual body is trivial, so `COST 200` is not a real tuning recommendation here.

### 21.1. `COST` Is Not Milliseconds

`COST` is expressed in planner cost units relative to internal cost parameters like `cpu_operator_cost`—**not directly in seconds or milliseconds**.

### 21.2. Defaults Differ by Function Language

C/internal functions carry much lower default `COST` than SQL or PL/pgSQL functions. Under PostgreSQL rules, typical defaults are 1 for C/internal functions and 100 for other languages unless specified.

### 21.3. What Does `COST` Influence?

Cost estimates can affect plan choice and evaluation order when the planner has freedom to reorder checks.

Marking an expensive function appropriately can steer the planner to evaluate cheaper filters first when semantics and plan structure permit.

### 21.4. `COST` Does Not Remove Inlining Barriers

Setting `COST 1` on a PL/pgSQL function will not make the planner fold procedural PL/pgSQL logic into the caller query.

### 21.5. Do Not Guess `COST` Values Blindly

Measure actual function runtime, invocation counts, and plan effects on specific queries before tuning. Wrong `COST` values can push the planner toward worse plans.

## 22. Set-Returning Functions and `ROWS`

Set-returning functions need an estimated output cardinality. PostgreSQL provides the `ROWS` attribute:

~~~sql
CREATE FUNCTION tenant_events(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE sql
STABLE
COST 10
ROWS 2000
AS $$
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

### 22.1. What Does `ROWS` Describe?

`ROWS 2000` is an **estimated output row count hint**, not a `LIMIT`. It does not cap how many rows the function returns.

### 22.2. Default Value

A set-returning function typically defaults to `ROWS 1000` if omitted. If it actually emits 2 rows or 2 million rows, that discrepancy can distort join order whenever `Function Scan` is not inlined.

### 22.3. Combining `ROWS` and `COST`

For set-returning functions, `COST` estimates per-row cost under PostgreSQL rules while `ROWS` estimates output cardinality. Together they guide caller plan choices.

### 22.4. Do Not Expect `ROWS` to Fix Inner Query Estimates

If a SQL table function inlines, the planner estimates directly on base tables. If not inlined, `COST`/`ROWS` metadata carries more weight on the `Function Scan` node.

### 22.5. Tenants with Skewed Sizes

A single fixed `ROWS` figure is a global estimate: a tiny tenant may have 100 rows while a large tenant has 1 million. One static `ROWS` cannot fit every parameter distribution. Evaluate direct SQL, statistics, and custom vs. generic plans.

## 23. `PARALLEL SAFE`, `RESTRICTED`, `UNSAFE`

Functions also carry parallel-execution safety attributes:

- `PARALLEL SAFE`.
- `PARALLEL RESTRICTED`.
- `PARALLEL UNSAFE`.

### 23.1. This Is a Safety Contract, Not Just a Hint

If a function accesses worker-unsafe backend state, uses temporary tables, cursors, modifies data, or triggers restricted operations, falsely labeling it `PARALLEL SAFE` can cause errors or unsafe behavior.

### 23.2. Default for User-Defined Functions

User-defined functions generally default to `PARALLEL UNSAFE` unless declared otherwise. That can block parallel plans for queries calling them.

### 23.3. Pure Functions Can Be `PARALLEL SAFE`

~~~sql
CREATE FUNCTION add_one(p_value INTEGER)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT p_value + 1;
$$;
~~~

This is a simple pure function with no side effects.

### 23.4. Do Not Mark Everything `PARALLEL SAFE` Just for Speed

Without proving worker safety, keep accurate declarations and consider redesigning hot paths to avoid calling procedural functions per row.

### 23.5. Parallelism Does Not Guarantee Faster Runs

A small query returning a few rows can suffer more from parallel startup overhead than it saves. The planner weighs data size and parallel cost accordingly.

## 24. `STRICT` and Null Handling

Functions can be declared `STRICT`, equivalently `RETURNS NULL ON NULL INPUT`.

~~~sql
CREATE FUNCTION normalized_code(p_code TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_code));
$$;
~~~

When an argument is `NULL`, PostgreSQL skips executing the function and returns `NULL` under the `STRICT` contract.

### 24.1. `STRICT` Only Works When Business Logic Matches

A function converting `NULL` into a default:

~~~sql
SELECT coalesce(p_code, 'unknown');
~~~

cannot be declared `STRICT` if it must run when `p_code` is `NULL`, because `STRICT` short-circuits directly to `NULL`.

### 24.2. `STRICT` Can Affect Inlining Eligibility

In particular, inlining rules for SQL set-returning functions treat `STRICT` differently from scalar functions. Never toggle `STRICT` blindly to force a plan while breaking null semantics.

### 24.3. Function Calls Over Millions of Rows

When a query evaluates an expensive function across millions of rows, whether it skips `NULL`s, gets inlined, or gets evaluated multiple times affects CPU heavily. Verify with `EXPLAIN` and measurements.

## 25. `SECURITY DEFINER` Is a Security Boundary, Not Just Overhead

PostgreSQL allows:

~~~sql
CREATE FUNCTION get_sensitive_report()
RETURNS ...
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT ...;
$$;
~~~

This is a conceptual skeleton—not a runnable function until `RETURNS ...` and the body are filled in.

### 25.1. `SECURITY DEFINER` Changes Privilege Context

The function executes with the privileges of its owner in applicable respects—very different from inlining raw SQL into the caller running under caller privileges.

### 25.2. PostgreSQL Cannot Bypass Security Checks for Optimization

SQL function inlining restricts `SECURITY DEFINER`. This is an intentional security boundary; never drop it merely to remove `Function Scan`.

### 25.3. Watch `search_path`

A `SECURITY DEFINER` function must control `search_path` and schema-qualify object references to avoid name shadowing by untrusted schemas. Attaching `SET search_path` to the function can block inlining, yet security comes first.

### 25.4. Never Combine Elevated Privileges with Unsafe Dynamic SQL

Building SQL via string concatenation on client input risks SQL injection running with the function owner's privileges. Use bind parameters, `format('%I', ...)` for identifiers, and `USING` for values whenever dynamic SQL is needed in PL/pgSQL.

## 26. Functions in `WHERE` Can Prevent Direct Index Usage

This query:

~~~sql
SELECT *
FROM events
WHERE event_type = 'purchase';
~~~

can use a standard B-tree index on `event_type` when appropriate.

By contrast:

~~~sql
SELECT *
FROM events
WHERE lower(btrim(event_type)) = 'purchase';
~~~

filters on an **expression**, not directly on the stored column value.

### 26.1. What Is Sargability?

A predicate is **sargable** in an indexing context when the planner can turn it into a useful index condition.

Wrapping a column in a function does not always forbid indexing, yet a plain index on the raw column typically **cannot directly satisfy** the transformed expression.

### 26.2. Expression Indexes

~~~sql
CREATE INDEX events_normalized_type_idx
ON events (lower(btrim(event_type)));
~~~

When the predicate expression matches, PostgreSQL can use this index directly.

### 26.3. Indexing User-Defined Functions

If the function is genuinely `IMMUTABLE` under PostgreSQL rules:

~~~sql
CREATE INDEX events_normalized_type_fn_idx
ON events (normalized_code(event_type));
~~~

Verify proper function definition and expression alignment. Function-based B-tree indexes require true immutability—never mislabel volatility just to create an index.

### 26.4. Index Matching Is Separate from Inlining

A SQL function might inline while its predicate still fails to match an existing index. Conversely, a matching expression index can supply an index path even when a query invokes a function. **Inlining** and **index matching** are distinct mechanisms.

### 26.5. Functions Evaluated Too Many Times

If a predicate runs against a million rows, a slow PL/pgSQL function may be invoked a million times before yielding a handful of matches. Push cheap sargable filters earlier or use plain SQL/expression indexes verified via real plans.

## 27. PL/pgSQL and Cached Plans

SQL statements inside PL/pgSQL are prepared and planned via PL/pgSQL and SPI mechanisms. Repeated executions can cache and reuse plans.

### 27.1. This Does Not Mean “PL/pgSQL Has No Optimizer”

PostgreSQL still optimizes SQL inside PL/pgSQL. The limitation is that the caller's planner does not fuse the inner SQL with all outer joins/filters the way an inlined SQL table function can.

### 27.2. Generic vs. Custom Plans Can Diverge

When parameters vary dramatically across tenants, selectivity shifts too. SQL inside PL/pgSQL can be affected by generic vs. custom plan caching rules.

### 27.3. Run `EXPLAIN` in the Right Place

`EXPLAIN` on the outer caller may show only `Function Scan`, hiding the plans of SQL statements running inside PL/pgSQL.

To tune deeply, explain those inner SQL queries individually against representative data or use authorized instrumentation.

### 27.4. Never Oversimplify to “Convert Everything to SQL Functions”

PL/pgSQL is the right tool for control flow, exception handling, loops, and procedural logic. Switch languages only when semantics, security, and maintainability remain sound.

## 28. Comparing Three Ways to Organize the Same Logic

Suppose we need `purchase` events for tenant 42.

### 28.1. Direct Query

~~~sql
SELECT event_id, tenant_id, event_type, payload
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

The planner sees every predicate directly in one `SELECT`.

### 28.2. Materialized CTE

~~~sql
WITH tenant_rows AS MATERIALIZED (
    SELECT event_id, tenant_id, event_type, payload
    FROM events
    WHERE tenant_id = 42
)
SELECT *
FROM tenant_rows
WHERE event_type = 'purchase';
~~~

The `event_type` predicate sits outside the boundary; the intermediate buffer can be larger.

### 28.3. PL/pgSQL Function

~~~sql
SELECT *
FROM get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

The outer planner cannot push filters into the PL/pgSQL body, and row estimates may rely on the declared `ROWS`.

### 28.4. Inlineable SQL Table Function

~~~sql
SELECT *
FROM get_events_sql(42)
WHERE event_type = 'purchase';
~~~

If inlined, the planner sees both filters together and can choose the same scan as the direct query.

### 28.5. Do Not Rank Approaches Without Measuring

There are cases where well-placed materialized CTEs or PL/pgSQL functions perform well. Rank approaches based on:

1. Exact logical correctness.
2. Data and parameter distribution.
3. Actual execution plans.
4. Intermediate row counts and invocation counts.
5. CPU and I/O costs.
6. Maintainability and security.

## 29. CTEs and `LIMIT`: Pushing Filters Can Change Meaning

Example:

~~~sql
WITH top_purchase AS (
    SELECT *
    FROM events
    WHERE event_type = 'purchase'
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT 100
)
SELECT *
FROM top_purchase
WHERE tenant_id = 42;
~~~

The business question here is: **out of the 100 most recent purchase events system-wide, how many belong to tenant 42?**

Another query:

~~~sql
SELECT *
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 100;
~~~

asks instead for: **the 100 most recent purchase events for tenant 42**.

These two queries are **not equivalent**.

### 29.1. Why Can't the Planner Push Every Filter?

Moving the tenant filter before `LIMIT` alters which 100 rows qualify. The planner must preserve semantics, even if the alternative looks faster.

### 29.2. `ORDER BY` Inside a CTE Does Not Guarantee Outer Order

Without an explicit `ORDER BY` on the outer query, never depend on output order coming out of a sorted CTE. Outer result ordering is guaranteed only by an outer `ORDER BY`.

### 29.3. Treating `LIMIT` as “Guaranteeing Early Stop in a CTE” Is Risky

Parent operators may still pull many rows to sort, join, or aggregate. Inspect `EXPLAIN` instead of assuming `LIMIT` makes a CTE cheap.

## 30. CTEs with Aggregates and Window Functions

Consider:

~~~sql
WITH totals AS (
    SELECT tenant_id, COUNT(*) AS event_count
    FROM events
    GROUP BY tenant_id
)
SELECT *
FROM totals
WHERE event_count > 1000;
~~~

Filtering on `event_count` happens **after aggregation**. It cannot be pushed down into the base table `WHERE` without altering `COUNT(*)`.

### 30.1. Aggregation Is a Semantic Boundary

Even when a CTE folds cleanly, the planner must preserve the logical order of `GROUP BY` and `HAVING`. Not all filters can legally push below them.

### 30.2. Window Functions

~~~sql
WITH ranked AS (
    SELECT
        event_id,
        tenant_id,
        occurred_at,
        row_number() OVER (
            PARTITION BY tenant_id
            ORDER BY occurred_at DESC, event_id DESC
        ) AS rn
    FROM events
)
SELECT *
FROM ranked
WHERE rn <= 3;
~~~

This asks for the “top 3 per tenant.” While the planner has specific window optimizations, it cannot alter window inputs in ways that change partitions or rankings.

### 30.3. Takeaway

Seeing sort, aggregate, or window nodes after CTE folding does not mean the CTE stayed materialized. **SQL semantic boundaries** differ from **`AS MATERIALIZED` barriers**.

## 31. Complete Lab: Schema and Dataset

The following exercises use PostgreSQL in a **testing database**. If `optimizer_lab` already exists, pick another schema or database; never drop real project data.

### 31.1. Create Schema

~~~sql
CREATE SCHEMA optimizer_lab;
~~~

### 31.2. Events Table

~~~sql
CREATE TABLE optimizer_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload INTEGER NOT NULL
);
~~~

### 31.3. Generate 200,000 Sample Rows

~~~sql
INSERT INTO optimizer_lab.events (
    tenant_id, event_type, occurred_at, payload
)
SELECT
    (g % 100) + 1,
    CASE
        WHEN g % 10 < 6 THEN 'view'
        WHEN g % 10 < 9 THEN 'click'
        ELSE 'purchase'
    END,
    TIMESTAMPTZ '2026-01-01 00:00+00'
        + (g % 2592000) * INTERVAL '1 second',
    g % 1000
FROM generate_series(1, 200000) AS gs(g);
~~~

Explanation:

- 100 tenants distributed evenly by generator formula.
- Three event types with skewed frequencies.
- `occurred_at` spans 30 days starting early January 2026.
- `payload` is an integer used in filters and expressions.

Synthetic modulo-generated data introduces correlations uncommon in production. It demonstrates the mechanics—never expect identical speedup ratios on real data.

### 31.4. Create Indexes

~~~sql
CREATE INDEX optimizer_events_tenant_time_idx
ON optimizer_lab.events (tenant_id, occurred_at);

CREATE INDEX optimizer_events_type_idx
ON optimizer_lab.events (event_type);

CREATE INDEX optimizer_events_payload_idx
ON optimizer_lab.events (payload);

ANALYZE optimizer_lab.events;
~~~

### 31.5. Baseline Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, payload
FROM optimizer_lab.events
WHERE tenant_id = 42
  AND occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00';
~~~

Record Estimated Rows, Actual Rows, scan node type, buffers, and execution time.

## 32. Lab: CTE `MATERIALIZED` vs. `NOT MATERIALIZED`

### 32.1. Forced Boundary

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

Observe:

- Whether `CTE recent` and `CTE Scan on recent` appear.
- Where `Filter: tenant_id = 42` sits.
- How many rows the CTE produces/passes.
- Whether temp reads/writes occur.

### 32.2. Allowing Folding

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

The planner can see both tenant and time predicates and select an Index Scan or Bitmap Scan.

### 32.3. Default Behavior

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

Because this is a single-reference `SELECT` CTE with no volatile expression, PostgreSQL 12+ normally folds it by default. Compare against `NOT MATERIALIZED` on your actual server.

### 32.4. Fair Evaluation

If `NOT MATERIALIZED` runs faster, check whether it reduced rows scanned or enabled index usage. If it is no faster, data scale may be small, filters may be unselective, or both plans may pick similar access paths.

Never report fixed speedup percentages without running measurements.

## 33. Lab: Multi-Reference CTEs

### 33.1. Default

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH base AS (
    SELECT event_id, tenant_id, payload
    FROM optimizer_lab.events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

### 33.2. `NOT MATERIALIZED`

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH base AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM optimizer_lab.events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

### 33.3. Metrics to Record

| Item | Default | `NOT MATERIALIZED` |
|---|---|---|
| Does `CTE Scan` appear? | Record | Record |
| Base table scan count | Record | Record |
| Index paths | Record | Record |
| Intermediate rows | Record | Record |
| Buffers/temp | Record | Record |
| Planning/execution time | Record | Record |

### 33.4. Do Not Confuse “One Scan” with “Less Work”

One huge scan can cost far more than two tiny index scans. Conversely, two huge scans recomputing heavy expressions can cost more than one shared materialized CTE.

## 34. Lab: SQL Function vs. PL/pgSQL Function

### 34.1. SQL Function

~~~sql
CREATE FUNCTION optimizer_lab.get_events_sql(
    p_tenant INTEGER
)
RETURNS SETOF optimizer_lab.events
LANGUAGE sql
STABLE
ROWS 2000
AS $$
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

### 34.2. PL/pgSQL Function

~~~sql
CREATE FUNCTION optimizer_lab.get_events_plpgsql(
    p_tenant INTEGER
)
RETURNS SETOF optimizer_lab.events
LANGUAGE plpgsql
STABLE
ROWS 2000
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant;
END;
$$;
~~~

### 34.3. Calling the SQL Function with an Outer Filter

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.get_events_sql(42)
WHERE event_type = 'purchase';
~~~

### 34.4. Calling the PL/pgSQL Function with an Outer Filter

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

### 34.5. Comparing with Direct Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

### 34.6. What to Observe

- Did the SQL function inline into a scan on `events`?
- Did PL/pgSQL produce a `Function Scan`?
- Where was the `event_type` filter evaluated?
- How many rows came out of the function before outer filtering?
- Did `Function Scan`'s row estimate match actuals?
- Was there a meaningful difference in buffers or runtime?

### 34.7. PL/pgSQL Is Not Always Slower

If a PL/pgSQL function returns very few rows or handles work poorly suited to plain SQL, differences may be minor or justified. Judge using real workloads and complexity.

## 35. Lab: Reducing Barriers via Function Parameters

Create a PL/pgSQL function accepting both tenant and event type:

~~~sql
CREATE FUNCTION optimizer_lab.get_events_filtered(
    p_tenant INTEGER,
    p_event_type TEXT
)
RETURNS SETOF optimizer_lab.events
LANGUAGE plpgsql
STABLE
ROWS 200
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant
      AND e.event_type = p_event_type;
END;
$$;
~~~

Invoke it:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, tenant_id, event_type
FROM optimizer_lab.get_events_filtered(42, 'purchase');
~~~

### 35.1. Significance

The PL/pgSQL function still creates a function-call boundary, yet the inner SQL now sees both predicates. The planner for **the `SELECT` inside the function** can optimize using both filters.

### 35.2. Watch Plan Caching

When called repeatedly across skewed parameter sets, PL/pgSQL may reuse a cached generic plan. When tenant sizes skew heavily, inspect generic vs. custom plan behavior on your PostgreSQL version and workload.

### 35.3. Set-Returning Wrappers vs. Business Logic Functions

If a function merely wraps one small `SELECT`, moving that SQL directly into the repository/query layer is often cleanest. If the function serves as a shared database API, keep the abstraction while monitoring its execution plans.

## 36. Lab: Function Predicates and Expression Indexes

### 36.1. Normalization Function

~~~sql
CREATE FUNCTION optimizer_lab.normalize_type(
    p_type TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT lower(btrim(p_type));
$$;
~~~

### 36.2. Query Filtering with Function on Column

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM optimizer_lab.events
WHERE optimizer_lab.normalize_type(event_type) = 'purchase';
~~~

A regular index on `event_type` will not serve directly as an access path for that expression predicate.

### 36.3. Expression Index

~~~sql
CREATE INDEX optimizer_events_type_normalized_idx
ON optimizer_lab.events (
    optimizer_lab.normalize_type(event_type)
);

ANALYZE optimizer_lab.events;
~~~

Re-run `EXPLAIN`.

### 36.4. Key Takeaways

- The function must be truly `IMMUTABLE` to support an expression index.
- Every extra index adds write and storage overhead.
- The planner may still skip the index if selectivity is low.
- Expressions and collations must align consistently.
- Function inlining and expression indexing are separate mechanisms.

### 36.5. Never Fake `IMMUTABLE` Just to Build an Index

If a function reads config tables, `now()`, or session settings, tagging it `IMMUTABLE` does not change reality—it produces an index that can return stale or inconsistent results.

## 37. When Should You Refactor or Remove a CTE?

Practical cases:

### 37.1. Materialized CTE Generates Too Many Rows

Options:

- Switch to `NOT MATERIALIZED` when eligible and beneficial.
- Move common filters inside the CTE if valid for all consumers.
- Inline as a subquery or flat query when clearer and better optimized.
- Check whether multiple references are truly necessary.

### 37.2. CTE Recomputes Expensive Expressions Multiple Times

Options:

- Try `MATERIALIZED`.
- Persist/stage a managed temporary intermediate if data volume justifies it.
- Restructure logic to avoid repeating expensive expressions across branches.

### 37.3. CTE Follows `LIMIT`, Aggregate, or Window Boundaries

Check semantics first; some boundaries cannot be crossed without changing results.

### 37.4. CTEs Written for Side Effects

Do not abuse CTEs to orchestrate arbitrary side-effect ordering. Use clear transactions and explicit DML statements.

### 37.5. CTEs That Improve Readability Without Harm

If plans and latencies are healthy, there is no reason to flatten every CTE just to eliminate a barrier that causes no harm.

## 38. When Should You Refactor Function Usage?

### 38.1. PL/pgSQL Function Wrapping a Single `SELECT`

Consider:

- Writing the query directly.
- Using a `LANGUAGE sql STABLE` table function if contracts allow and `EXPLAIN` confirms inlining.
- Accepting filter conditions as parameters so the inner query avoids returning excessive rows.

### 38.2. Per-Row Function Calls in `WHERE`

Consider:

- Avoiding wrapping columns when an equivalent sargable predicate exists.
- Adding an expression index when the function is genuinely `IMMUTABLE` and workload justifies it.
- Precomputing normalized columns cleanly where appropriate.
- Measuring actual call counts and CPU cost.

### 38.3. Set-Returning Functions with Poor Row Estimates

Tune `ROWS` and `COST` while remembering they are planner hints, not output limits. Base them on representative data.

### 38.4. Privileged Functions

Keep `SECURITY DEFINER` when required; optimize the SQL and indexes inside instead of sacrificing security for inlining.

### 38.5. Parallel-Friendly Pure Functions

When safety is verified, `PARALLEL SAFE` can unlock parallel plans. Never tag functions `SAFE` if they have side effects or depend on worker-unsafe backend state.

## 39. Practical Diagnostic Workflow

Follow these steps in order:

1. **Capture the slow query in practice**, including common and outlier parameter values.
2. **Check PostgreSQL version**, since CTE behavior changed significantly in 12.
3. Run `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` in an appropriate environment.
4. Check for `CTE Scan`, `Function Scan`, `Sort`, `HashAggregate`, and `Materialize` nodes.
5. Find the first node where estimated rows diverge sharply from actual rows.
6. Inspect where filters are applied and whether they cross a barrier.
7. Check how many rows are discarded only after building a large intermediate set.
8. Inspect scan counts and `loops`.
9. Verify indexes, statistics, and `ANALYZE` recency.
10. For single-reference CTEs, compare default vs. `MATERIALIZED` if warranted.
11. For multi-reference CTEs, compare default vs. `NOT MATERIALIZED`.
12. For functions, check SQL vs. PL/pgSQL, scalar vs. set-returning, inlining, and volatility.
13. Check `COST`/`ROWS` if `Function Scan` cardinality is way off.
14. Inspect function predicates and expression-index opportunities.
15. Measure repeatedly on representative data rather than judging from one run.
16. Never compromise security or semantic correctness.
17. Deploy changes with a rollback path and monitor p95/p99 latency and database load.

### 39.1. When Slowness Has Nothing to Do with CTEs or Functions

If the plan scans 200 million rows due to an unselective filter or transfers massive payloads over the network, the real issue is indexing, pagination, or schema—not CTEs.

### 39.2. Never Use `enable_*` Flags to Mask Symptoms

Settings like `enable_nestloop` are great for debugging alternative plans, yet permanently disabling a join method in production is no substitute for proper statistics, indexes, and SQL.

### 39.3. Watch Planning Time Too

Folding a deeply nested multi-CTE query increases planner search complexity. In workloads running thousands of tiny queries per second, planning time can matter as much as execution time.

## 40. Common Misconceptions

### 40.1. “CTEs are always materialized.”

**False in PostgreSQL 12+** for eligible CTEs. Single-reference CTEs usually fold.

### 40.2. “CTEs are now always inlined.”

False. Multiple references, recursion, volatile expressions, and DML obey different rules.

### 40.3. “`NOT MATERIALIZED` is always faster.”

False. It can repeat expensive work across multiple consumers.

### 40.4. “`MATERIALIZED` is always slow.”

False. Sharing one expensive computation across consumers can be faster overall.

### 40.5. “A `MATERIALIZED` CTE always computes every row before the outer query starts.”

Not always: execution pulls rows on demand depending on consumer operators, though sorts, joins, and aggregates often require most or all rows.

### 40.6. “Adding `NOT MATERIALIZED` to a `VOLATILE` CTE forces multiple evaluations.”

False. Eligibility and semantic preservation rules still apply.

### 40.7. “A CTE is a temporary table with indexes.”

False. A materialized CTE result is not a user-managed temp table with arbitrary indexes.

### 40.8. “Subqueries are always optimized better than CTEs.”

False. Eligible single-reference CTEs fold just like subqueries.

### 40.9. “Pushing any `WHERE` into a CTE is always valid.”

False when multiple consumers read it or when `LIMIT`/aggregation/window semantics intervene.

### 40.10. “An `ORDER BY` inside a CTE guarantees final output order.”

Never rely on it unless the outermost `SELECT` explicitly carries the required `ORDER BY`.

### 40.11. “`LANGUAGE sql` functions always inline.”

False. Multiple eligibility requirements must be satisfied.

### 40.12. “PostgreSQL never optimizes PL/pgSQL functions.”

False. Inner SQL statements are planned normally; the caller simply cannot fold the entire procedural body.

### 40.13. “Raising `COST` alone makes a query faster.”

False. `COST` is only a planner estimate—it does not rewrite function code or add indexes.

### 40.14. “`ROWS` limits how many rows a function returns.”

False. It is solely a cardinality hint for the planner.

### 40.15. “`PARALLEL SAFE` is harmless hint metadata.”

False. Mislabeling an unsafe function can trigger errors or corrupt behavior.

### 40.16. “Mark table-reading functions `IMMUTABLE` so they inline.”

False. Functions depending on mutable table data must never be labeled `IMMUTABLE` just for plan convenience.

### 40.17. “`STRICT` is always right for functions taking `NULL`.”

False whenever the function must convert `NULL` into a non-null result.

### 40.18. “Drop `SECURITY DEFINER` anytime to enable inlining.”

False—that alters privilege checks and can open security holes.

### 40.19. “Functions on columns always block every index.”

Not universally. Matching expression indexes work, and some expressions simplify safely.

### 40.20. “Expression indexes work with any `VOLATILE` function.”

False. Functions in index expressions must meet immutability requirements.

### 40.21. “Seeing `CTE Scan` means the query is broken or slow.”

False. Measure actual cost and workload impact first.

### 40.22. “Not seeing `CTE Scan` means the SQL has no CTE.”

False. The CTE may simply have been folded despite `WITH` in source SQL.

### 40.23. “Every `Function Scan` must be rewritten into inline SQL.”

False. Specialized set-returning logic, security boundaries, and procedural requirements are valid reasons to keep functions.

### 40.24. “Inlining always picks a better plan because the optimizer sees more.”

Not always. It can duplicate heavy computation or inflate planning overhead—always measure.

### 40.25. “`EXPLAIN ANALYZE` does not run the query.”

False. It executes the statement. Wrap `INSERT`/`UPDATE`/`DELETE` in a test transaction with rollback or run in a safe lab.

## 41. Practice Exercises

### Exercise 1 — Single-Reference CTE

In PostgreSQL 15, a non-recursive, non-volatile `SELECT` CTE is referenced once. Does it usually fold or materialize by default?

**Hint:** Usually folds.

### Exercise 2 — Older Versions

Why might a PostgreSQL 10 tuning guide saying “CTEs are optimization fences” not apply unmodified to PostgreSQL 15?

**Hint:** CTE folding was introduced in PostgreSQL 12.

### Exercise 3 — `MATERIALIZED`

Which keyword keeps a CTE materialization boundary?

~~~sql
WITH x AS MATERIALIZED (
    SELECT *
    FROM optimizer_lab.events
)
SELECT *
FROM x
WHERE tenant_id = 42;
~~~

### Exercise 4 — Pushdown

`tenant=42` appears outside `x AS MATERIALIZED (SELECT * FROM events)`. Is it pushed into the inner base scan via folding?

**Hint:** Not across a `MATERIALIZED` boundary.

### Exercise 5 — `NOT MATERIALIZED`

A CTE is referenced twice with different selective filters. Why might `NOT MATERIALIZED` help?

**Hint:** Each branch can optimize separately and receive pushed-down filters.

### Exercise 6 — Duplicated Work

When can `NOT MATERIALIZED` perform worse than materialization?

**Hint:** When the CTE is very expensive and multiple consumers read nearly all of its output.

### Exercise 7 — `CTE Scan`

What node in `EXPLAIN` indicates a separate CTE buffer is being scanned?

**Hint:** `CTE Scan`.

### Exercise 8 — Plan Without `CTE Scan`

If `CTE Scan` does not appear, does that mean PostgreSQL ignored `WITH`?

**Hint:** No—the CTE may have been folded.

### Exercise 9 — `LIMIT` Semantics

Compare “global top 100 then filter tenant” vs. “filter tenant then top 100.” Are they equivalent?

**Answer:** No.

### Exercise 10 — `ORDER BY`

Why should `ORDER BY` sit on the outermost `SELECT` whenever final output order must be guaranteed?

**Hint:** Ordering inside intermediate steps is not a contract for the outer query.

### Exercise 11 — `VOLATILE`

Does `WITH x AS (SELECT random()) ...` qualify as a side-effect-free CTE eligible for free folding?

**Answer:** No.

### Exercise 12 — `NOT MATERIALIZED` with Volatile Expressions

Can adding `NOT MATERIALIZED` bypass safety restrictions around volatile expressions?

**Answer:** No.

### Exercise 13 — Recursive CTEs

In `EXPLAIN` of `WITH RECURSIVE`, which node names can appear?

**Hint:** `Recursive Union`, `WorkTable Scan`.

### Exercise 14 — DML CTEs

Why shouldn't `WITH inserted AS (INSERT ... RETURNING ...)` be treated like a side-effect-free `SELECT` CTE?

**Hint:** It modifies data and follows distinct execution semantics.

### Exercise 15 — SQL Functions

Can a scalar SQL function computing `x*2` and marked `IMMUTABLE` be inlined?

**Hint:** Yes, when eligible—though never rely on it as an unconditional contract.

### Exercise 16 — PL/pgSQL

Why can't outer caller predicates push freely into a `SELECT` inside a PL/pgSQL function?

**Hint:** The outer planner does not inline procedural function bodies like plain SQL.

### Exercise 17 — `Function Scan`

When `EXPLAIN` shows `Function Scan` with an outer `Filter`, what metrics should you check?

**Hint:** `ROWS` estimate, actual rows, rows discarded after the function call, and runtime.

### Exercise 18 — `STABLE` Functions

Should a SQL function reading the mutable `events` table be declared `IMMUTABLE`?

**Answer:** No.

### Exercise 19 — Volatility Classification

Classify `random()` and pure integer multiplication as `VOLATILE` vs. `IMMUTABLE`.

**Hint:** `random()` is `VOLATILE`; pure arithmetic multiplication is `IMMUTABLE`.

### Exercise 20 — `STRICT`

Should a function that turns `NULL` into `'unknown'` be declared `STRICT`?

**Answer:** No.

### Exercise 21 — `ROWS`

Does `ROWS 1000` cap the number of rows a function can emit at 1,000?

**Answer:** No.

### Exercise 22 — `COST`

Does `COST 100` mean 100 ms?

**Answer:** No—it is a relative planner cost unit.

### Exercise 23 — `PARALLEL SAFE`

Should every function be labeled `PARALLEL SAFE` to encourage parallel plans?

**Answer:** No.

### Exercise 24 — `SECURITY DEFINER`

Why must you not drop `SECURITY DEFINER` merely to trigger inlining?

**Hint:** It alters authorization and security boundaries.

### Exercise 25 — Expression Index

Write an index for `lower(btrim(event_type))` on the lab table.

~~~sql
CREATE INDEX optimizer_events_type_expr_idx
ON optimizer_lab.events (lower(btrim(event_type)));
~~~

### Exercise 26 — Sargability

With a plain index on `event_type`, will `WHERE lower(event_type)='purchase'` definitely use that index?

**Hint:** No. Check expression indexes and the execution plan.

### Exercise 27 — Per-Row Function Calls

An expensive PL/pgSQL function sits in `WHERE` across one million rows. Name two optimization approaches.

**Hint:** Filter early with sargable predicates, or move to plain SQL / expression indexes if appropriate.

### Exercise 28 — Direct Query

In the lab, write a direct query filtering `tenant=42` and `event_type='purchase'`, run `EXPLAIN`, and compare against `get_events_plpgsql`.

### Exercise 29 — Function Parameters

Why can `get_events_filtered(tenant,type)` beat a function taking only `tenant` and filtering `type` in the caller?

**Hint:** Both predicates appear directly in the SQL inside the function.

### Exercise 30 — Plan Cache

Why might one tenant having 100 rows and another having 1 million cause a generic plan to perform poorly?

**Hint:** A single shared plan may fail to fit highly skewed parameter distributions.

### Exercise 31 — `EXPLAIN ANALYZE`

Can you run `EXPLAIN ANALYZE DELETE ...` in production assuming data remains untouched?

**Answer:** No; `ANALYZE` executes the statement.

### Exercise 32 — Filters and Shared CTEs

A materialized CTE serves two consumers—one needing tenant 42, one needing tenant 77. Can you always push `tenant=42` into the shared CTE?

**Answer:** No; it breaks the other consumer's result.

### Exercise 33 — Aggregate Boundaries

Why can't `event_count>1000` after `GROUP BY` be pushed freely into row-level `WHERE`?

**Hint:** It filters groups, not raw source rows.

### Exercise 34 — Index vs. Materialization

If a query is slow because a materialized CTE processes all tenants, will adding an index on `tenant` definitely solve it?

**Hint:** Not if the tenant filter stays outside the materialized CTE without pushdown; inspect the query shape.

### Exercise 35 — Join Order

Why can wrapping a big `JOIN` in a materialized CTE stop the outer planner from picking a better join order with a highly selective table?

**Hint:** The CTE barrier prevents join reordering across it.

### Exercise 36 — Function Security

A `SECURITY DEFINER` function constructs dynamic SQL from client inputs. What must you check beyond `EXPLAIN`?

**Hint:** `search_path`, privileges, SQL injection, identifier quoting, and parameter binding.

### Exercise 37 — Fair Benchmarking

A query ran in 20 ms before and 19 ms after `NOT MATERIALIZED` in one measurement. Is that enough to declare a real speedup?

**Hint:** No—run multiple trials and compare caches, system load, buffers, and plans.

### Exercise 38 — Multi-Consumer CTEs

You have an expensive aggregate CTE referenced by 4 branches, all reading nearly every row. What should you test first?

**Hint:** Default materialized / `MATERIALIZED` compared against `NOT MATERIALIZED`.

### Exercise 39 — Security Boundaries

A function requires owner privileges and sets `SET search_path`. Should you strip those attributes to force SQL inlining?

**Answer:** No, if doing so changes security semantics.

### Exercise 40 — Decision Summary

Given three queries:

1. A pure `SELECT` CTE referenced once.
2. A pure `SELECT` CTE referenced twice where each branch filters narrowly.
3. A PL/pgSQL function returning 200,000 rows that the caller filters down to 100.

Propose a testing strategy for each.

**Hint:** (1) keep default and inspect `EXPLAIN`; (2) test `NOT MATERIALIZED`; (3) push filters into function parameters or switch to direct SQL / inlineable SQL function and measure.

## 42. Quick Reference Table

| Topic | Key Point |
|---|---|
| CTEs in PostgreSQL 11 and earlier | Typically strong optimization fences |
| CTEs in PostgreSQL 12+ | Eligible CTEs can fold |
| Single-reference CTE | Usually folds by default if side-effect-free `SELECT` |
| Multi-reference CTE | Usually materializes by default |
| `AS MATERIALIZED` | Requests preserving a separate CTE result/boundary |
| `AS NOT MATERIALIZED` | Allows folding; risks repeated work |
| Volatile CTE | Not freely folded even with `NOT MATERIALIZED` |
| Recursive CTE | Iterative execution; does not simply inline |
| Data-modifying CTE | Follows distinct DML and `RETURNING` semantics |
| `CTE Scan` | Indicates scanning a materialized CTE buffer |
| `WorkTable Scan` | Typically tied to recursive queries |
| Predicate pushdown | Moves filters down early when semantically valid |
| Materialization cost | Work to build buffer, memory/disk, delayed outer filtering |
| Materialization benefit | Computes once for multiple consumers |
| SQL function | Can inline when eligibility criteria hold |
| PL/pgSQL | Outer planner does not fold procedural body |
| `Function Scan` | Set-returning function node in execution plan |
| `VOLATILE` | Outputs/effects can vary; limits transformations |
| `STABLE` | Consistent within one statement under contract |
| `IMMUTABLE` | Identical inputs durably yield identical outputs |
| `STRICT` | `NULL` inputs return `NULL` without calling body |
| `COST` | Relative planner cost unit, not milliseconds |
| `ROWS` | Cardinality estimate for set-returning functions |
| `PARALLEL SAFE` | Must genuinely be safe inside parallel workers |
| `SECURITY DEFINER` | Security boundary; never strip to force inlining |
| `WHERE function(column)` | May need expression index or sargable rewrite |
| Expression index | Expressions/functions must satisfy immutability rules |
| `LIMIT`/aggregate/window | Semantic boundaries; cannot push filters arbitrarily |
| `EXPLAIN ANALYZE` | Executes query and reports actual rows and timing |
| Comparing plans | Inspect scans, `CTE/Function Scan`, filters, buffers, loops |
| Tuning decisions | Driven by workload and controlled measurement |

---

## Conclusion

**CTEs and user-defined functions are not inherently slow.** Their biggest impact on optimization lies in whether the planner can **see across the boundary** to push down filters, reorder joins, and select optimal access paths.

Since PostgreSQL 12, eligible single-reference `SELECT` CTEs usually fold into the parent query, making the old advice “`WITH` is always an optimization fence” outdated as a blanket rule. With multi-reference CTEs, **`MATERIALIZED`** can avoid duplicate computation while **`NOT MATERIALIZED`** lets each branch filter early and leverage indexes. Both involve trade-offs, and recursive, data-modifying, and volatile CTEs obey stricter limits.

Likewise, **SQL functions can inline** when syntax and attributes allow, whereas **PL/pgSQL** usually maintains a boundary between caller and inner SQL. Attributes such as `VOLATILE`, `STABLE`, `IMMUTABLE`, `COST`, `ROWS`, `PARALLEL`, and `SECURITY DEFINER` shape both execution plans and correctness. Never falsify volatility or weaken privilege checks solely for a nicer plan.

The dependable approach is running **`EXPLAIN (ANALYZE, BUFFERS)`** on representative data—checking `CTE Scan`/`Function Scan`, filter placement, intermediate row counts, loop/call counts, runtime, and I/O—and testing targeted adjustments. Keep clean, maintainable SQL structures when they do no harm; remove a boundary only after proving **which optimization it blocks and confirming semantics and security stay intact**.
