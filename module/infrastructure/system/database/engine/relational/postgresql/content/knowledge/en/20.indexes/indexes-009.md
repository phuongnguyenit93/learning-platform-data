# Partial Indexes and Predicate Implication in PostgreSQL

In business databases, not every row in a table is queried with equal frequency. A jobs table might hold millions of **completed** jobs alongside just a few thousand **queued** jobs; a users table might hold many **soft-deleted** records while the application primarily queries active accounts; or a transactions table might mainly filter **unreconciled** records.

Creating a normal full-table B-tree index is valid, yet it maintains entries for millions of rows that the workload rarely touches. PostgreSQL offers **partial indexes**: an index containing only the table rows that satisfy a **predicate** (`WHERE` filter) specified at creation time.

Example:

```sql
CREATE INDEX jobs_queued_idx
ON jobs (tenant_id, run_after)
WHERE status = 'queued';
```

This index does **not** hold every row in `jobs`; it indexes only rows where `status = 'queued'`. However, a query wanting to use it must align with that filter. This is where many developers trip up:

> **PostgreSQL can only use a partial index for complete results when the query's filter implies that every needed row satisfies the index predicate** (or the planner combines separate access paths covering each branch). It is not enough for two conditions to merely “look similar” intuitively.

This lesson belongs to the **Indexes** chapter of the *Database Engine Relational PostgreSQL* module. It covers syntax, runnable SQL examples, logical **predicate implication**, planner inference limits, prepared statements, partial `UNIQUE` indexes, `NULL`s, maintenance costs, `EXPLAIN`, and hands-on exercises.

**Lesson objectives:**

- Distinguish partial indexes from full-table indexes, multi-column indexes, covering indexes, and partitioning.
- Explain **`Q ⇒ P`** implication between a query filter `Q` and an index predicate `P`.
- Identify when `AND`, `OR`, `IS NULL`, `IS NOT NULL`, and inequalities do or do not imply a predicate.
- Understand why the planner is not a general theorem prover; domain-equivalent expressions may not be recognized.
- Understand the limits of `$1` bind parameters in prepared statements and the difference between **generic plans** and **custom plans**.
- Use **partial unique indexes** to enforce uniqueness solely across “active” records, even under concurrent writes.
- Inspect plans with `EXPLAIN`, check stats, measure update costs, and roll out safely.

> **Version context:** Core examples on partial indexes, `UNIQUE`, and `EXPLAIN` use standard PostgreSQL features. `INCLUDE` requires PostgreSQL 11+; `plan_cache_mode` requires PostgreSQL 12+. Run on a compatible version or skip version-specific examples if testing on older servers.

---

## 1. What Is a Partial Index?

### 1.1. Visual Intuition

Suppose `jobs` has 100,000 rows:

```text
jobs
├── done       : 80,000 rows
├── failed     : 12,000 rows
├── running    :  3,000 rows
└── queued     :  5,000 rows
```

A full-table index:

```sql
CREATE INDEX jobs_status_run_after_idx
ON jobs (status, run_after);
```

logically maintains an entry for **every row** in the table.

A partial index:

```sql
CREATE INDEX jobs_queued_run_after_idx
ON jobs (run_after)
WHERE status = 'queued';
```

stores entries only for **queued rows**, because the trailing predicate excludes all other statuses.

```text
                                  +----------------------+
                                  |  Partial B-tree      |
jobs                              |  WHERE status=queued |
  done     --------------------X  |                      |
  failed   --------------------X  |  queued rows sorted  |
  running  --------------------X  |  by run_after        |
  queued   ---------------------> |                      |
                                  +----------------------+
```

This diagram is conceptual, not an exact B-tree page layout.

### 1.2. Predicate vs. Index Key

In:

```sql
CREATE INDEX jobs_queued_idx
ON jobs (tenant_id, run_after)
WHERE status = 'queued';
```

there are two separate parts:

| Part | Role |
|---|---|
| `(tenant_id, run_after)` | **Index key**: used to look up, sort, or filter rows inside the index |
| `WHERE status = 'queued'` | **Predicate**: determines **which rows enter the index** |

Key point: **`status` does not need to be an index key column**. For queries already constrained to `status = 'queued'`, every entry in the index shares that same status; putting `status` at the front of the key would be redundant.

Conversely, a query omitting `status = 'queued'` cannot assume the index contains `done`, `running`, and `failed` rows.

### 1.3. Predicates Evaluate Only Rows of the Indexed Table

A partial index belongs to **one table** and its predicate evaluates columns of that table alone. You cannot reference another table via a subquery:

```sql
-- NOT a valid partial index definition:
-- CREATE INDEX idx ON orders (created_at)
-- WHERE customer_id IN (
--     SELECT customer_id
--     FROM customers
--     WHERE status = 'active'
-- );
```

An index predicate cannot reference other tables via subqueries. If you need indexing conditioned on a related table's state, revisit your data model, maintain denormalized state consistently, or use materialized views, partitioning, or a different query plan.

### 1.4. Partial Indexes Never Alter SQL Query Results

An index is purely an access path. It never deletes rows outside the predicate or causes `SELECT`s to filter out rows automatically.

```sql
SELECT *
FROM jobs;
```

still returns all statuses. A partial index only expands **which access paths the planner may consider**—it never implicitly injects `WHERE status = 'queued'` into queries.

---

## 2. The Core Principle: Predicate Implication

Let:

- **`P(row)`**: the partial index predicate.
- **`Q(row)`**: the full `WHERE` condition of the query.

A partial index can serve as a complete access source for a set of rows when:

```text
Every row making Q true must also make P true.

In logic notation:

    Q => P
```

That means **the row set needed by the query is a subset of the rows covered by the index**.

### 2.1. Simple Implication Example

Partial index:

```sql
CREATE INDEX idx
ON jobs (run_after)
WHERE status = 'queued';
```

Query:

```sql
SELECT *
FROM jobs
WHERE status = 'queued'
  AND run_after < TIMESTAMPTZ '2026-11-15 00:00+00';
```

`Q` is:

```text
status = 'queued'
AND run_after < cutoff
```

Clearly every row satisfying `Q` also satisfies `P: status = 'queued'`.

**`Q ⇒ P` holds**, so the partial index **is eligible**.

### 2.2. The Reverse Direction Is Usually False

Query:

```sql
SELECT *
FROM jobs
WHERE run_after < TIMESTAMPTZ '2026-11-15 00:00+00';
```

There is no `status` filter. A `done` row can also have `run_after < cutoff`. The query requests rows **absent from the partial index**.

Hence `Q ⇒ P` is **false**. This partial index **cannot serve alone as a complete source** for the query.

### 2.3. Logic Reference Table

Suppose `P` is `status = 'queued'`.

| Query Predicate `Q` | `Q ⇒ P`? | Explanation |
|---|---|---|
| `status = 'queued'` | Yes | Matches predicate directly |
| `status = 'queued' AND tenant_id = 2` | Yes | Extra filter narrows the subset further |
| `status = 'queued' AND priority >= 8` | Yes | Still selects only queued rows |
| `status = 'running'` | No | Disjoint row set |
| `status IN ('queued', 'running')` | No | Query also needs `running` rows |
| `run_after < cutoff` | No | Unconstrained status |
| `status = 'queued' OR priority = 9` | No | The `priority = 9` branch can include `done` rows |
| `status = 'queued' AND (priority = 9 OR tenant_id = 2)` | Yes | Both branches remain constrained by `queued` |

This is **logical eligibility before cost estimation**. Even after proving eligibility, PostgreSQL may pick a sequential scan or another index if cheaper.

### 2.4. Logical Implication vs. Planner Recognition Are Two Separate Layers

Two distinct questions:

1. **Logically**, does `Q ⇒ P` hold for all rows?
2. **In implementation**, does PostgreSQL's planner recognize that implication during planning?

PostgreSQL **does not run a general-purpose theorem prover** over arbitrary equivalent expressions; it recognizes straightforward structural matches and simple inequality comparisons. Consequently:

> A domain-true logical implication **does not guarantee the planner will prove and use the partial index**.

For complex predicates, write queries using direct, easily recognized predicates instead of expecting PostgreSQL to deduce non-obvious rewrites.

---

## 3. Creating an Isolated Practice Dataset

All table commands below use `partial_idx_lab` to stay isolated from application data.

### 3.1. Checking Server Version and Privileges

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Confirm you are in a lab database with privileges to create schemas, tables, and indexes.

### 3.2. Creating the jobs Table

```sql
CREATE SCHEMA IF NOT EXISTS partial_idx_lab;

CREATE TABLE partial_idx_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'running', 'failed', 'done')),
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    run_after TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

In this table:

- `tenant_id` scopes organization ownership.
- `status` tracks queued/running/failed/done state.
- `run_after` specifies when a job becomes eligible to run.
- `priority` orders jobs scheduled at the same time.
- `completed_at` records completion timestamp if finished.
- `payload` stores job data, not needed inside the index.

### 3.3. Loading Skewed Status Data

Populate 20,000 jobs using `generate_series`:

```sql
INSERT INTO partial_idx_lab.jobs
    (tenant_id, status, priority, created_at,
     run_after, completed_at, payload)
SELECT
    1 + (g % 13) AS tenant_id,
    CASE
        WHEN g % 100 < 5 THEN 'queued'
        WHEN g % 100 < 8 THEN 'running'
        WHEN g % 100 < 20 THEN 'failed'
        ELSE 'done'
    END AS status,
    g % 10 AS priority,
    TIMESTAMPTZ '2026-11-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    TIMESTAMPTZ '2026-11-14 00:00:00+00'
        + (g % 240) * INTERVAL '1 minute' AS run_after,
    CASE
        WHEN g % 100 >= 20 THEN
            TIMESTAMPTZ '2026-11-15 00:00:00+00'
        ELSE NULL::timestamptz
    END AS completed_at,
    jsonb_build_object('seed', g) AS payload
FROM generate_series(1, 20000) AS gs(g);
```

From `g % 100`, the distribution is:

- 5% `queued`.
- 3% `running`.
- 12% `failed`.
- 80% `done`.

Since 20,000 is divisible by 100, seeded row counts are **1,000, 600, 2,400, and 16,000** respectively.

**Note:** the `INSERT` above is **not idempotent**; running it twice doubles the rows. To restart cleanly, use a new schema or intentionally truncate/reset while nothing else uses it. Never run the seed twice and expect identical statistics.

### 3.4. Verifying Distribution and Refreshing Statistics

```sql
SELECT status, COUNT(*) AS jobs
FROM partial_idx_lab.jobs
GROUP BY status
ORDER BY status;

ANALYZE partial_idx_lab.jobs;
```

`ANALYZE` updates planner row-count estimates; **it does not guarantee an index will be chosen**. Plans depend on row counts, tenant skew, predicates, cost parameters, and buffer cache state.

---

## 4. Creating the First Partial Index

Goal: fetch `queued` jobs by tenant and scheduled eligibility time.

### 4.1. CREATE INDEX Statement

```sql
CREATE INDEX jobs_queued_tenant_run_after_idx
ON partial_idx_lab.jobs
    (tenant_id, run_after, priority DESC, job_id)
WHERE status = 'queued';
```

Breakdown:

| Clause | Meaning |
|---|---|
| `jobs_queued_tenant_run_after_idx` | Index name |
| `ON partial_idx_lab.jobs` | Target table |
| `tenant_id` | Leading key, narrows per-tenant scans |
| `run_after` | Second key, supports time filtering and sorting |
| `priority DESC` | Descending key sort order |
| `job_id` | Tie-breaker key for deterministic order |
| `WHERE status = 'queued'` | Includes only queued jobs in the index |

Suppose the main workload runs:

```sql
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

Logically, the query specifies `status = 'queued'`, so **every target row falls inside the partial index**. Adding `tenant_id` and `run_after` narrows the range further.

### 4.2. The Predicate Does Not Need to Pin Tenant

This index includes **queued jobs across all tenants**; `tenant_id` is an **index key column**, not a filter restricting index membership.

Do not confuse:

```sql
ON jobs (tenant_id, run_after)
WHERE status = 'queued'
```

with:

```sql
ON jobs (run_after)
WHERE status = 'queued' AND tenant_id = 2
```

The second index **contains only tenant 2** and cannot serve other tenants. Create tenant-specific partial indexes only when extreme skew and operational governance truly warrant them.

### 4.3. Is a Partial Index Guaranteed to Be Proportionally Smaller?

If 5% of rows are `queued`, a partial index on that subset **can** be much smaller than an equivalent full-table index. Actual size still depends on:

- Number and width of key columns.
- Actual row count matching the predicate.
- Index access method, fillfactor, and page layout.
- `INCLUDE` columns, bloat, and update history.
- Other indexes on the table.

Never take “5% of rows” to mean “the index is guaranteed to be exactly 5% of a full index's disk bytes.”

---

## 5. EXPLAIN: Implication Alone Still Doesn't Guarantee Index Usage

PostgreSQL uses a cost-based optimizer. **Logical implication** is a necessary condition for using a partial index as a complete source, yet **not sufficient to guarantee the planner picks it**.

### 5.1. Inspecting with EXPLAIN

```sql
EXPLAIN
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

The plan might display:

```text
Index Scan using jobs_queued_tenant_run_after_idx ...
  Index Cond: ((tenant_id = 2) AND (run_after < ...))
```

**This is an illustrative plan shape.** Your server may choose `Index Scan`, `Bitmap Heap Scan`, `Seq Scan`, or another plan. When PostgreSQL picks the partial index because it proved `status = 'queued'`, it does not need to re-evaluate `status = 'queued'` as a separate `Filter`, since every entry already satisfies the predicate.

### 5.2. Reading EXPLAIN ANALYZE

On lab data with a read-only `SELECT`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00:00+00'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

Check:

- **`Index Scan` / `Bitmap Index Scan` / `Seq Scan`**: chosen access path.
- **`Index Cond`**: conditions evaluated directly during index lookup.
- **`Filter`**: residual conditions checked after retrieving candidate rows.
- **`Rows Removed by Filter`**: rows discarded at the filter step (when present).
- **`Actual rows` vs. estimated `rows`**: reveals whether statistics are accurate.
- **`Buffers`**: buffer page hits/reads for comparing actual I/O.
- **`Sort` / `Incremental Sort` / `Limit`**: verifies whether the index supplies the needed sort order.

`EXPLAIN ANALYZE` actually executes the `SELECT` to measure timing; on `UPDATE`/`DELETE`, it **modifies data** unless rolled back. This lesson uses it strictly on `SELECT`s.

### 5.3. The Planner Can Still Choose Seq Scan

Even when `Q ⇒ P` holds, the planner can choose a sequential scan if:

- The table is very small.
- Most rows match the query.
- Tenant/time predicates are unselective.
- Many unindexed columns must be fetched from the heap.
- Index ordering mismatches `ORDER BY`.
- Statistics and cost settings favor another plan.

Never conclude “the partial index is broken” just because `Seq Scan` appears on a small dataset. Evaluate plans, stats, and representative workloads.

---

## 6. Implication via AND: Stronger Conditions Imply the Predicate

Index predicate:

```sql
WHERE status = 'queued'
```

All queries below **imply** the predicate:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued';
```

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 3;
```

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 3
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

Why?

```text
Q = P AND R

Q is true => both P and R are true
          => P is true
```

This is the cleanest implication pattern and should be preferred when designing queries for partial indexes.

### 6.1. Not Every AND Predicate Matches Index Keys

Query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND priority = 9;
```

still implies the predicate, making the index **eligible** by row scope. However, the index key starts with `(tenant_id, run_after)`; omitting both leading columns makes searching for `priority = 9` inefficient. Predicate eligibility and **key-column ordering** are two separate checks.

### 6.2. Are Implicit Conditions via JOIN Always Proven?

Suppose domain constraints and a `JOIN` logically guarantee a status. While PostgreSQL can propagate simple equivalence classes, never assume it deduces arbitrary cross-table invariants or complex constraints.

If a query truly targets only queued jobs, write it explicitly:

```sql
WHERE j.status = 'queued'
```

rather than hoping the planner infers it from another table's column.

---

## 7. OR: One Unconstrained Branch Breaks Implication

Keep predicate `status = 'queued'`.

### 7.1. Case That Does NOT Imply the Predicate

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
   OR priority = 9;
```

A `done` row with `priority = 9` also satisfies this query. Therefore `Q ⇒ P` is **false**.

The `queued` partial index **cannot cover the entire query on its own**. The planner may choose a sequential scan or, in some scenarios, combine separate access paths per branch; do not claim the queued index is universally banned from every plan for an `OR` query, only that it cannot satisfy the whole `OR` alone.

### 7.2. Case That DOES Imply the Predicate

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND (tenant_id = 1 OR tenant_id = 2);
```

Both tenant branches sit under the common `status = 'queued'` condition.

```text
Q = P AND (A OR B)
Q => P
```

### 7.3. Parentheses Matter

Compare:

```sql
-- Does NOT imply P:
WHERE (status = 'queued' AND tenant_id = 1)
   OR tenant_id = 2
```

against:

```sql
-- Implies P:
WHERE status = 'queued'
  AND (tenant_id = 1 OR tenant_id = 2)
```

The first query matches all jobs in tenant 2 regardless of status. The second matches only queued jobs in tenant 1 or 2.

### 7.4. Splitting OR into UNION ALL

If business semantics allow and branches are **mutually exclusive**, you can split a multi-branch query into separate `SELECT`s:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 1

UNION ALL

SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'running'
  AND tenant_id = 1;
```

These two branches are disjoint because a row cannot be both `'queued'` and `'running'`. The planner can pick a tailored index path **for each branch independently**. Remember that `UNION ALL` preserves duplicates if branches overlap while `UNION` deduplicates at extra cost; never rewrite SQL carelessly without verifying set semantics.

---

## 8. Implication from Inequalities

PostgreSQL recognizes certain simple arithmetic/ordering implications during planning.

### 8.1. Example: x < 10 Implies x < 100

Partial index:

```sql
CREATE INDEX jobs_low_priority_idx
ON partial_idx_lab.jobs (tenant_id, job_id)
WHERE priority < 8;
```

Query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND priority < 4;
```

Logically:

```text
priority < 4  =>  priority < 8
```

Thus the query needs no rows outside the index. PostgreSQL can recognize simple inequality implications like this.

**Note:** the index key `(tenant_id, job_id)` lacks `priority`, so it may not be optimal for filtering tightly by priority. **Predicate implication** and **key-column usefulness** remain distinct questions.

### 8.2. Counterexample That Does NOT Imply

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE priority < 10;
```

This includes priorities 8 and 9, which are absent from `priority < 8`.

```text
priority < 10  =/=>  priority < 8
```

### 8.3. Boundary Operators <= vs. <

Given predicate:

```sql
WHERE priority <= 5
```

queries `priority < 5` or `priority <= 3` are logical subsets.

Conversely, `priority <= 6` does not imply `priority <= 5`.

**Never be sloppy with boundary operators.** `<` and `<=` differ, especially on timestamps or `numeric` values.

### 8.4. Do Not Generalize Examples into Arbitrary Algebraic Proof

PostgreSQL does not prove arbitrary algebraic rewrites of inequalities. For example:

```sql
-- Logically equivalent over integers,
-- yet do not assume the planner always recognizes it:
-- WHERE priority + 1 < 9
```

Do not expect an index with `WHERE priority < 8` to match algebraically rearranged forms. For critical queries, **write predicates cleanly in matching form and check `EXPLAIN`**.

---

## 9. NULLs and Three-Valued Logic

PostgreSQL evaluates SQL predicates under three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN` (typically from `NULL`). A partial index includes a row **only when its predicate evaluates to `TRUE`**.

### 9.1. Predicate IS NULL

Create an index for jobs **without a completion timestamp**:

```sql
CREATE INDEX jobs_not_completed_idx
ON partial_idx_lab.jobs (tenant_id, created_at, job_id)
WHERE completed_at IS NULL;
```

Matching query:

```sql
SELECT job_id, tenant_id, created_at
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND completed_at IS NULL
ORDER BY created_at, job_id;
```

`Q ⇒ P` holds because the query explicitly filters `completed_at IS NULL`.

By contrast:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued';
```

**will not automatically be proven by the planner** to imply `completed_at IS NULL`, even though our seed data happens to leave `completed_at` NULL on queued rows. Never rely on accidental data correlation as logical proof.

### 9.2. IS NOT NULL

An index for rows that have a completion timestamp:

```sql
CREATE INDEX jobs_completed_idx
ON partial_idx_lab.jobs (tenant_id, completed_at)
WHERE completed_at IS NOT NULL;
```

Filtering `WHERE completed_at IS NOT NULL` is the clearest way to imply that predicate.

A strict comparison:

```sql
WHERE completed_at <
    TIMESTAMPTZ '2026-11-16 00:00+00'
```

can only evaluate to **`TRUE`** when `completed_at` is non-NULL under SQL semantics. PostgreSQL can recognize strict operators implying `IS NOT NULL` depending on the expression and plan. Still, avoid generalizing to complex functions or expressions; verify with `EXPLAIN`.

### 9.3. Mistake: Comparing with = NULL

Never write:

```sql
-- Wrong NULL check semantics:
-- WHERE completed_at = NULL;
```

In SQL, `= NULL` yields `UNKNOWN`, never `TRUE`. Always use:

```sql
WHERE completed_at IS NULL
```

Writing `= NULL` in an index predicate produces an empty, useless index that never matches `IS NULL` queries.

### 9.4. Boolean Columns with NULL

For a nullable `is_active BOOLEAN` column:

- `WHERE is_active` selects only `TRUE`.
- `WHERE NOT is_active` selects only `FALSE`, excluding `NULL`.
- `WHERE is_active IS FALSE` selects `FALSE`.
- `WHERE is_active IS NOT TRUE` selects `FALSE` **and `NULL`**.

The last two predicates are **not equivalent** on nullable booleans. Pick the right row set first before optimizing.

### 9.5. Subset Checking Means Checking TRUE

When evaluating `Q ⇒ P`, ask: **could any row make `Q` evaluate to `TRUE` while `P` does not evaluate to `TRUE`?** If yes, the partial index does not cover the query.

The distinction between `FALSE` and `UNKNOWN` matters in three-valued SQL; never apply naive two-valued boolean intuition when `NULL`s are possible.

---

## 10. Prepared Statements: Parameters Are Not Constants in Every Plan

A well-known partial index pitfall involves parameterized queries:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = $1
  AND tenant_id = $2;
```

Given partial index predicate:

```sql
WHERE status = 'queued'
```

### 10.1. Why Can't a Generic Plan Use This Index?

When building a **generic plan**, PostgreSQL must generate a plan valid for **every possible value** of `$1`:

```text
$1 = 'queued'  -> queued partial index covers results.
$1 = 'done'    -> queued partial index misses most rows.
$1 = 'failed'  -> queued partial index also misses rows.
```

Hence `status = $1` **does not imply** `status = 'queued'` for all values of `$1`.

A generic plan cannot rely on the queued partial index as if it covered every status.

### 10.2. Custom Plans Can Differ

PostgreSQL can build a **custom plan** using the actual bind parameter value of an execution. When `$1 = 'queued'` is known at planning time, the planner **can** recognize the match with the partial index predicate.

However, **there is no guarantee every prepared statement stays on a custom plan**, and even with a custom plan, cost estimation still decides. A single prepared statement can switch plans over time as execution counts grow.

### 10.3. Experimenting with PREPARE

```sql
PREPARE find_jobs(TEXT, INTEGER) AS
SELECT job_id, tenant_id, run_after
FROM partial_idx_lab.jobs
WHERE status = $1
  AND tenant_id = $2
ORDER BY run_after, job_id
LIMIT 20;
```

Inspect custom plan behavior:

```sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE find_jobs('queued', 2);
```

Inspect generic plan behavior:

```sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE find_jobs('queued', 2);
```

Clean up:

```sql
RESET plan_cache_mode;
DEALLOCATE find_jobs;
```

**Observed plans can differ:** the custom plan can leverage the partial index for `'queued'`, whereas the generic plan cannot assume `$1` is always `'queued'`. `EXPLAIN EXECUTE` reveals the actual choice, though even a custom plan might pick a different index or `Seq Scan`.

### 10.4. auto, custom, and generic

Check setting:

```sql
SHOW plan_cache_mode;
```

The default is `auto`. PostgreSQL compares custom vs. generic plan costs after initial executions.

Do not set `force_custom_plan` application-wide just for one partial index query: **re-planning on every execution has CPU overhead**, and overall workloads vary. Use forced settings primarily for **diagnostics and testing**, then fix the SQL design properly.

### 10.5. Stable Query Design: Hardcode the Fixed Status, Bind Everything Else

If an endpoint exclusively serves **queued jobs**, write the SQL as:

```sql
PREPARE find_queued_jobs(INTEGER, TIMESTAMPTZ) AS
SELECT job_id, tenant_id, run_after, priority
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = $1
  AND run_after < $2
ORDER BY run_after, priority DESC, job_id
LIMIT 20;

EXPLAIN EXECUTE find_queued_jobs(
    2,
    TIMESTAMPTZ '2026-11-14 02:00+00'
);

DEALLOCATE find_queued_jobs;
```

Here **`status = 'queued'` is a constant** in the SQL text, so every plan—generic or custom—cleanly implies the partial index predicate while safely binding `tenant_id` and `run_after`.

This is an **intentional domain-specific query design**, not a license to concatenate arbitrary user input into SQL. If an endpoint legitimately queries multiple user-selected statuses, never secretly hardcode `'queued'`.

### 10.6. JDBC Example

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class QueuedJobRepository {
    public List<Long> findDueJobIds(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        String sql = """
            SELECT job_id
            FROM partial_idx_lab.jobs
            WHERE status = 'queued'
              AND tenant_id = ?
              AND run_after < CAST(? AS timestamptz)
            ORDER BY run_after, priority DESC, job_id
            LIMIT 20
            """;

        List<Long> ids = new ArrayList<>();
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setInt(1, tenantId);
            ps.setObject(2, cutoff);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("job_id"));
                }
            }
        }
        return ids;
    }
}
```

This uses a Java text block (Java 15+) with a JDBC driver supporting `OffsetDateTime`. The `'queued'` literal is fixed in code-controlled SQL while tenant and cutoff remain bound parameters.

**Business concurrency note:** `SELECT`ing queued jobs does not claim them for a worker; concurrent job queues still require proper locking/claiming protocols (such as transactions with `FOR UPDATE SKIP LOCKED`), as partial indexes do not prevent worker race conditions.

---

## 11. Partial UNIQUE Indexes: Conditional Uniqueness

Partial indexes are not just for read speed. Combined with `UNIQUE`, they **enforce business uniqueness invariants on a subset of rows**.

For example: within a tenant, an email cannot belong to **two active (non-soft-deleted) contacts**, while soft-deleted records stay in the table for audit history.

### 11.1. Creating the contacts Table

```sql
CREATE TABLE partial_idx_lab.contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Business rule:** within the same tenant, no two contacts with `deleted_at IS NULL` may share the same email **case-insensitively**.

### 11.2. Creating a Partial Unique Index

```sql
CREATE UNIQUE INDEX contacts_live_email_uq
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Interpretation:

- Only **non-soft-deleted contacts** enter the index.
- `tenant_id` is part of the unique key.
- `lower(email)` normalizes casing under the database's collation rules.
- Two live contacts in the same tenant with matching `lower(email)` violate uniqueness.
- Two live contacts in **different tenants** may share an email.
- Contacts with `deleted_at IS NOT NULL` sit outside the index and are unconstrained by it.

**Note:** real-world email normalization involves Unicode/collation nuances and address rules; `lower(email)` illustrates case-insensitive comparison rather than complete email canonicalization.

### 11.3. Inserting Valid Rows

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES
    (10, 'an@example.test', 'An (tenant 10)'),
    (20, 'an@example.test', 'An (tenant 20)');
```

Both rows succeed because `tenant_id` differs.

### 11.4. Duplicate Live Insert in the Same Tenant Is Rejected

```sql
-- Skip running if keeping the lab uninterrupted: fails with SQLSTATE 23505.
-- INSERT INTO partial_idx_lab.contacts
--     (tenant_id, email, display_name)
-- VALUES (10, 'AN@example.test', 'An duplicated');
```

PostgreSQL detects the unique conflict among entries matching `deleted_at IS NULL`:

```text
SQLSTATE 23505 — unique_violation
```

Because the database enforces the constraint, two concurrent transactions attempting to insert the same live key cannot both commit.

### 11.5. After Soft Delete, the Email Can Be Reused

```sql
UPDATE partial_idx_lab.contacts
SET deleted_at = TIMESTAMPTZ '2026-11-14 12:00:00+07'
WHERE tenant_id = 10
  AND lower(email) = 'an@example.test'
  AND deleted_at IS NULL;

INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'AN@example.test', 'An re-registered');
```

The old record exited the `deleted_at IS NULL` subset. The new record becomes tenant 10's sole live contact with that email.

### 11.6. Restoring an Old Contact Can Violate Uniqueness

Setting `deleted_at = NULL` back on the soft-deleted row while the new live contact exists is rejected by the partial unique index.

That preserves the invariant: **never two live contacts with the same email in one tenant**.

### 11.7. A Partial UNIQUE Index Is Not a Standard UNIQUE Table Constraint

PostgreSQL does not allow declaring a table-level `UNIQUE (...)` constraint with a partial `WHERE` predicate. What you create via:

```sql
CREATE UNIQUE INDEX ... WHERE ...;
```

is a **partial unique index**.

Do not assume its name works everywhere a **constraint name** is required. For instance, `ON CONFLICT ON CONSTRAINT contacts_live_email_uq` does not work for a partial unique index because it is not a named table constraint.

---

## 12. INSERT ... ON CONFLICT with Partial Unique Indexes

PostgreSQL lets you specify a **conflict target** consisting of columns/expressions plus an **index predicate** so it can infer the matching arbiter index.

### 12.1. Handling Conflicts Only Among Active Contacts

For example, skipping inserts only if a live contact already exists:

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'an@example.test', 'New name')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO NOTHING;
```

The clause:

```sql
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
```

triggers **index inference** matching the unique index on `(tenant_id, lower(email))` with predicate `WHERE deleted_at IS NULL`.

If a live contact already has that email, `DO NOTHING` skips the insert. If only a **soft-deleted** contact exists, it is outside the partial index so the new live contact inserts cleanly.

### 12.2. Why Not ON CONFLICT ON CONSTRAINT?

`ON CONFLICT ON CONSTRAINT constraint_name` requires a named unique or exclusion constraint. A partial unique index created via `CREATE UNIQUE INDEX ... WHERE ...` is **not** a constraint of that form.

Always specify the **columns/expressions and `WHERE` predicate** in the conflict target for partial unique indexes as shown above.

### 12.3. Don't Omit the Predicate During Inference

```sql
-- Incomplete conflict target for a partial unique index:
-- ON CONFLICT (tenant_id, lower(email)) DO NOTHING
```

If only a partial unique index exists with no full-table unique index on that key pair, omitting `WHERE deleted_at IS NULL` **fails index inference**, throwing an error that no matching unique or exclusion constraint exists.

Conversely, if a non-partial unique index also exists on those keys, PostgreSQL might infer that one instead. Always audit **all existing indexes** and uniqueness rules rather than guessing from one `ON CONFLICT` line.

### 12.4. ON CONFLICT Does Not Turn Tenant Scoped Uniqueness Global

With an index on `(tenant_id, lower(email))`, identical emails in **different tenants** do not conflict. Dropping `tenant_id` from the index or conflict target changes the business invariant.

In multi-tenant systems, uniqueness scoping and tenant authorization are separate concerns. Indexes prevent **key collisions**; they never authorize which user can view or edit another tenant's contacts.

---

## 13. Partial Indexes and Active / Soft-Delete Data

Partial indexes for active rows are a classic pattern:

```sql
CREATE INDEX contacts_live_lookup_idx
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

However, because `contacts_live_email_uq` is already a **partial unique index** with the exact same keys and predicate, it already accelerates lookups on that expression. In this lab, **do not add** a nearly duplicate index just for `SELECT`s.

### 13.1. Matching Query

```sql
SELECT contact_id, display_name
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

This query implies **`deleted_at IS NULL`** and matches the indexed expression **`lower(email)`**.

### 13.2. Query Without the Soft-Delete Guard

```sql
SELECT contact_id, display_name
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND lower(email) = 'an@example.test';
```

This query can also return **soft-deleted contacts**. The live partial index cannot cover the full result because `deleted_at IS NULL` is missing.

Never sneak in `AND deleted_at IS NULL` purely to hit an index if the endpoint is genuinely supposed to return historical soft-deleted rows; define data requirements first.

### 13.3. Query Comparing Raw email Directly

```sql
SELECT contact_id
FROM partial_idx_lab.contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND email = 'an@example.test';
```

Here the query implies the predicate, yet **`email = ...`** differs from the indexed key expression **`lower(email)`**. PostgreSQL might still scan the index using `tenant_id` and filter `email`, yet never assume a case-sensitive `email = ...` lookup leverages the `lower(email)` key directly.

**Separate two questions:** are the query's rows included by the index predicate, and do the **search columns/expressions** match the index key structure?

---

## 14. Dynamic Time Conditions: Why WHERE now() Is Invalid

A tempting idea:

> “I only query jobs from the last seven days; let's index rows newer than `now() - interval '7 days'`.”

Someone tries:

```sql
-- INVALID because the predicate calls a time-varying function:
-- CREATE INDEX jobs_last_week_idx
-- ON partial_idx_lab.jobs (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
```

### 14.1. Why Does PostgreSQL Reject It?

An index predicate must satisfy **immutability** so entries stay valid without background clock updates. `now()` changes across transactions and is `STABLE`, not `IMMUTABLE`.

If an index defined “last seven days” relative to the clock, a row valid today would stop qualifying next week **without any `UPDATE` on the row**. PostgreSQL has no mechanism to evict entries from an index simply because wall-clock time passes.

Therefore, using `now()` or `CURRENT_DATE` to build a sliding-window partial index **is invalid**.

### 14.2. Predicates with a Fixed Literal Cutoff

An index can use a fixed literal cutoff:

```sql
CREATE INDEX jobs_since_november_idx
ON partial_idx_lab.jobs (created_at)
WHERE created_at >=
    TIMESTAMPTZ '2026-11-01 00:00:00+00';
```

Every row with `created_at` from that timestamp onward enters the index. Yet **the cutoff never slides forward with the clock**. Months later, the index will cover months of historical rows unless periodically replaced.

### 14.3. Alternatives for Sliding Time Windows

Depending on workload:

- A normal full-table B-tree on `created_at` when time-range queries are common.
- Daily/monthly partitioning with partition pruning and drop/archive retention.
- BRIN on huge tables whose timestamps correlate strongly with physical heap order.
- An explicitly maintained column such as `is_recent_bucket` if your architecture handles controlled updates.
- Periodically creating a new partial index with a **fresh literal cutoff** and dropping the old one via controlled deployments, without treating the predicate as dynamic.

No single choice fits every table; evaluate scale, update frequency, retention, filters, and maintenance overhead.

### 14.4. User-Defined Functions

Never mark a function relying on clocks, sessions, other tables, or mutable settings as `IMMUTABLE` just to bypass PostgreSQL's partial index check. Doing so corrupts index semantics and yields unreliable query results.

A function's volatility must reflect **truthfully** that identical inputs always yield identical outputs under PostgreSQL rules—not act as a DDL bypass flag.

---

## 15. Complex Predicates and Inference Limits

### 15.1. Do Not Expect the Planner to Prove Arbitrary Business Logic

Suppose an app defines an “active job” using a status set and `completed_at` rule:

```sql
CREATE INDEX jobs_active_complex_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status IN ('queued', 'running')
  AND completed_at IS NULL;
```

A query:

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status = 'queued'
  AND tenant_id = 2
  AND completed_at IS NULL;
```

logically falls within the indexed subset, yet **do not assume the planner proves every complex rewrite**. On critical workloads, inspect `EXPLAIN` and write predicates in straightforward, easily matched forms.

### 15.2. Structural Matching Beats Clever Equivalence Proofs

Given partial index:

```sql
CREATE INDEX jobs_priority9_idx
ON partial_idx_lab.jobs (tenant_id, job_id)
WHERE priority = 9;
```

A query writing:

```sql
WHERE priority = 9
  AND tenant_id = 2
```

is far easier for the planner to match than writing the same logic via a custom function or algebraic manipulation.

### 15.3. Keep Predicates Consistent Between DDL and Queries

Practical guidelines:

1. Keep predicates short, clear, and stable.
2. Repeat the exact predicate conditions with explicit types in business queries.
3. Avoid burying predicates inside unnecessary expressions.
4. Check `EXPLAIN` on real production SQL using real bind parameters and plan modes.
5. Never distort SQL semantics just to force an index match.

### 15.4. Constraints and Functional Dependencies

Suppose a table has `CHECK (status = 'done' => completed_at IS NOT NULL)` written appropriately. That **enforces data integrity**, yet the planner is not a general theorem prover combining arbitrary `CHECK` constraints to deduce partial index eligibility.

Never assume “because queued rows can never have a non-NULL `completed_at`, `WHERE status = 'queued'` will definitely use an index with `WHERE completed_at IS NULL`.” Include matching predicates or test planner behavior on your exact version.

---

## 16. Multi-Tenant Partial Indexes: Scope and Security

In a multi-tenant application:

```sql
CREATE INDEX jobs_queued_tenant_run_after_idx
ON partial_idx_lab.jobs (tenant_id, run_after, priority DESC, job_id)
WHERE status = 'queued';
```

indexes queued jobs across **all tenants**. It enforces no access boundaries.

### 16.1. Queries Must Include a Tenant Guard

```sql
SELECT job_id, tenant_id, run_after
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
ORDER BY run_after;
```

`tenant_id = 2` scopes the query to the target tenant and leverages the index's leading column.

**However:** a PostgreSQL index is **not an authorization mechanism**. A role granted `SELECT` on the table without Row-Level Security can still read other tenants' rows. Enforce database privileges, RLS policies, and application checks independently of indexing.

### 16.2. Should You Create One Partial Index Per Tenant?

An idea:

```sql
-- Hyper-specialized per-tenant index example:
-- CREATE INDEX jobs_tenant2_queued_idx
-- ON partial_idx_lab.jobs (run_after)
-- WHERE tenant_id = 2 AND status = 'queued';
```

This can occasionally help for extreme data skew with one giant hot tenant, yet becomes unmanageable with thousands of tenants:

- Thousands of indexes to create, update, vacuum, reindex, and monitor.
- More index choices during query planning.
- Constant DDL churn as tenants onboard or churn.
- Every `INSERT`/`UPDATE` must evaluate many index predicates.

Most multi-tenant systems should start with **shared indexes leading with `tenant_id`**, adding tenant-specific partial indexes only for proven outlier hotspots.

### 16.3. Partial Indexes and RLS

Row-Level Security restricts visible rows per role, yet the planner will not always prove a partial index predicate solely from an RLS policy or session context.

Never rely on indexes as a security boundary. When analyzing queries under RLS, test with the **actual application role and active RLS policies**, as security barriers affect planning.

---

## 17. Partial Indexes, Covering Indexes, and Index-Only Scans

### 17.1. Using INCLUDE for Extra Read Columns

Suppose queries return `job_id, tenant_id, run_after, priority, created_at` while filtering and sorting only on the first columns:

```sql
CREATE INDEX jobs_queued_covering_idx
ON partial_idx_lab.jobs
    (tenant_id, run_after, priority DESC, job_id)
INCLUDE (created_at)
WHERE status = 'queued';
```

In this index:

- Columns inside `(...)` are **key columns**.
- `created_at` is an **`INCLUDE` payload column**, not a sort or lookup key.
- The predicate still restricts entries to queued jobs.

### 17.2. When Can Index-Only Scan Happen?

A query needing only columns stored in the index:

```sql
SELECT job_id, tenant_id, run_after, priority, created_at
FROM partial_idx_lab.jobs
WHERE tenant_id = 2
  AND status = 'queued'
ORDER BY run_after, priority DESC, job_id
LIMIT 20;
```

can use **`Index Only Scan`** when cost-effective and visibility conditions allow. PostgreSQL must still obey MVCC: it checks the **visibility map** and visits the heap whenever pages are not marked all-visible.

Never claim “having all columns in `INCLUDE` guarantees zero heap reads.” On frequently updated tables where pages are rarely all-visible, `Index Only Scan` can still incur many heap fetches.

### 17.3. Cost of INCLUDE

`INCLUDE` widens index entries, increasing disk size and write overhead. Never dump huge columns like `payload JSONB` into `INCLUDE` just to chase index-only scans; tuple size limits and write amplification make that counterproductive.

### 17.4. Avoid Redundant Overlapping Indexes

If you already have:

```sql
jobs_queued_tenant_run_after_idx
```

and create:

```sql
jobs_queued_covering_idx
```

with identical keys and predicate differing only by `INCLUDE`, evaluate **replacing** the old index with the new one in production rather than maintaining both indefinitely.

**In the lab**, keeping both temporarily to compare `EXPLAIN` is fine; in real benchmarks and production, eliminate redundant indexes.

---

## 18. INSERT, UPDATE, and DELETE Costs of Partial Indexes

Partial indexes are **not free**, even when smaller than full-table indexes.

### 18.1. INSERT

On every new row, PostgreSQL evaluates the predicate of each partial index to decide whether to insert an entry:

```text
INSERT status='done'
    -> no entry added to jobs_queued...

INSERT status='queued'
    -> entry added to jobs_queued...
```

This is conceptual. The row still updates any other table indexes such as the primary key.

### 18.2. UPDATE Moving Rows Into or Out of the Index

For example, transitioning `queued → running`:

```sql
BEGIN;

UPDATE partial_idx_lab.jobs
SET status = 'running'
WHERE job_id = 1
  AND status = 'queued';

ROLLBACK;
```

If `job_id = 1` in the seed is not `'queued'`, this reports `UPDATE 0`; it illustrates the transition logic without requiring a specific row ID.

Regarding the queued partial index:

```text
queued -> running:
    row leaves the predicate subset.

running -> queued:
    row enters the partial index.
```

These transitions generate index maintenance, WAL records, and can impact HOT updates.

### 18.3. HOT Updates and Predicate Columns

PostgreSQL's **Heap-Only Tuple (HOT)** optimization skips index updates when an `UPDATE` does not affect columns referenced by indexes and free space remains on the heap page. If an `UPDATE` modifies a column referenced in **index keys, expressions, or a partial index predicate** in a way that requires index maintenance, HOT eligibility can be blocked.

Do not assume “because a `done` row has no entry in the queued partial index, updating its `status` is always HOT.” Referencing a column in an index predicate still participates in index maintenance and HOT rules.

### 18.4. DELETE

`DELETE` marks the tuple version dead under MVCC; index entries are reclaimed later by `VACUUM`/autovacuum when no active snapshots need them. Disk files do not shrink immediately on `DELETE`.

### 18.5. When Partial Indexes Offer Little Benefit

If nearly all rows match the predicate—say 95% of rows have `status = 'active'`—a partial index `WHERE status = 'active'` ends up **nearly the same size as a full-table index**, while adding predicate-evaluation overhead and restricting which queries can use it.

Partial indexes shine when **the indexed subset is compact and hot queries focus tightly on it**, not merely whenever a `WHERE` filter exists.

---

## 19. Statistics, Sizes, and Usage Monitoring

### 19.1. Inspecting Existing Indexes

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partial_idx_lab'
ORDER BY tablename, indexname;
```

`indexdef` confirms:

- Table and key columns/expressions.
- `WHERE ...` predicate.
- Whether `UNIQUE` is set.
- Access method such as `btree`.
- `INCLUDE` columns if any.

Never rely purely on index names; always inspect actual DDL definitions.

### 19.2. Comparing Index Sizes

```sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
WHERE n.nspname = 'partial_idx_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

This reports current physical size of indexes in the schema. Size reflects page layout, row count, bloat, and update churn—it does not scale linearly with the predicate's row percentage.

### 19.3. Scan Counts and Tuples Read

```sql
SELECT
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'partial_idx_lab'
ORDER BY relname, indexrelname;
```

These are **cumulative counters** that reset on stats reset or maintenance events. Interpret them alongside:

- Observation window length.
- Workload volume and cycles.
- `EXPLAIN` plans.
- Table update frequency and maintenance cost.

Low `idx_scan` **never automatically proves an index is redundant**: a partial unique index may exist primarily to **enforce data integrity on writes**, not merely to accelerate `SELECT`s.

### 19.4. Column Statistics and Value Distribution

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'partial_idx_lab'
  AND tablename = 'jobs'
  AND attname IN ('status', 'tenant_id', 'priority');
```

This shows how the planner estimates selectivity for predicates like `status = 'queued'`.

When data distributions shift rapidly (such as jobs cycling through statuses), statistics drift. Autovacuum/autoanalyze refreshes them automatically; after bulk loads or lab experiments, run `ANALYZE` deliberately.

---

## 20. Deploying Partial Indexes on Live Tables

### 20.1. Standard CREATE INDEX Can Block Writes

```sql
CREATE INDEX jobs_queued_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status = 'queued';
```

On large active tables, standard builds acquire locks blocking concurrent writes for the build duration. Never run plain `CREATE INDEX` during peak production hours just because it finished instantly in the lab.

### 20.2. CREATE INDEX CONCURRENTLY

PostgreSQL provides:

```sql
CREATE INDEX CONCURRENTLY jobs_queued_concurrent_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status = 'queued';
```

`CONCURRENTLY` avoids blocking normal writes while building, yet:

- Takes longer and uses more resources.
- Must wait for concurrent transactions/snapshots between phases.
- **Cannot run inside an explicit transaction block** such as `BEGIN; ... COMMIT;`.
- Can leave behind an **`INVALID` index** if canceled or failed, requiring cleanup.
- Still requires capacity planning, progress monitoring, and contention checks.

Never treat `CONCURRENTLY` as zero-lock, zero-impact magic.

### 20.3. Changing a Predicate Is Not Updating a Variable

A predicate is baked into the index definition. Switching from:

```sql
WHERE status = 'queued'
```

to:

```sql
WHERE status IN ('queued', 'running')
```

requires **building a new index** with the new definition and transitioning safely. PostgreSQL never modifies an existing index automatically just because application `WHERE` clauses changed.

Specifically for partial unique indexes, expanding the predicate can cause **existing valid rows to collide on uniqueness**. Audit existing data before applying the broader rule.

### 20.4. Checking Index Validity and Build Progress

Check catalog status:

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c ON c.oid = i.indexrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'partial_idx_lab'
ORDER BY c.relname;
```

During long concurrent builds on large tables, monitor `pg_stat_progress_create_index` on supported versions. Interpret `indisvalid = false` per the documentation—never assume “the server will fix an invalid index automatically in a few seconds.”

---

## 21. Partial Indexes Are Not Partitioning

Both techniques focus access onto subsets of data, yet they operate differently:

| Criterion | Partial Index | Partitioning |
|---|---|---|
| Table storage | All rows remain in one table | Rows are physically separated across child partitions |
| Predicate | Controls **which rows enter the index** | Rules routing rows to partitions |
| Querying | Planner uses index if query implies predicate | Planner prunes partitions if query filters partition key |
| Retention | Never removes old rows from the table | Enables fast partition drop/archive in time-based setups |
| DDL & operations | Manage index and uniqueness definitions | Manage partitions, constraints, and local indexes |
| Write cost | Evaluate predicate and maintain index | Route rows to partitions and maintain partition indexes |

Partitioned tables can also define partial indexes on their partitions. Both techniques **complement each other** rather than serving as drop-in replacements.

### 21.1. When to Prefer Partitioning?

If primary requirements are:

- Storing massive multi-month or multi-year history.
- Dropping or archiving **entire time windows** cleanly.
- Most queries filter on the partition key.
- Data lifecycle management is central.

partitioning fits naturally. A partial index with a static literal cutoff cannot replace partition lifecycle management.

### 21.2. When Do Partial Indexes Shine?

When within a table or partition only a tiny percentage of rows have `status = 'queued'` or `deleted_at IS NULL`, a partial index provides a compact, targeted access path for hot reads.

Still evaluate query predicates, status update frequency, and actual execution plans.

---

## 22. Common Mistakes

**1. “A partial index has a WHERE clause, so SELECTs automatically apply that WHERE.”** False. `SELECT`s obey their own `WHERE` clauses; indexes never alter query semantics.

**2. “A queued partial index helps queries across all statuses.”** False. Done, running, and failed rows are missing from it.

**3. “If a query implies the predicate, the planner must use the index.”** False. The planner still evaluates cost and key column alignment.

**4. “PostgreSQL proves every logically equivalent expression.”** False. Only straightforward implications are recognized.

**5. “`status IN ('queued', 'running')` implies `status = 'queued'`.”** False. `'running'` is a counterexample.

**6. “`WHERE status = 'queued' OR priority = 9` implies queued.”** False. The `priority = 9` branch can match other statuses.

**7. “`WHERE status = 'queued' AND tenant_id = 2` cannot use the queued partial index.”** False. It cleanly implies `status = 'queued'`.

**8. “Checking `P ⇒ Q` is enough.”** False. You need **`Q ⇒ P`**: the query cannot need rows outside the index.

**9. “`status` must be in the index keys because it appears in the predicate.”** False. Predicate and index key serve separate roles.

**10. “As long as SQL is logically sound, the planner handles every algebraic rewrite.”** No. Verify with `EXPLAIN`.

**11. “`status = $1` lets a generic plan assume `$1 = 'queued'`.”** False. Generic plans must work for any parameter value.

**12. “Prepared statements can never use partial indexes.”** Overstated. Custom plans inspect concrete bind values and can choose partial indexes; measure them.

**13. “`force_custom_plan` is always faster.”** No. Re-planning per execution costs CPU, and another plan might win anyway.

**14. “`IS NULL` is the same as `= NULL`.”** False. `= NULL` evaluates to `UNKNOWN`, never `TRUE`.

**15. “`WHERE NOT is_active` always equals `IS NOT TRUE`.”** False on nullable booleans: `IS NOT TRUE` includes `NULL`.

**16. “An index `WHERE deleted_at IS NULL` serves every email query.”** False if the query also needs soft-deleted rows.

**17. “`UNIQUE (tenant_id, email)` equals a partial `UNIQUE` with `deleted_at IS NULL`.”** No. Partial uniqueness restricts only live rows.

**18. “A partial unique index only speeds up SELECTs, not concurrent writes.”** False. Unique indexes enforce uniqueness across concurrent transactions for matching rows.

**19. “`ON CONFLICT ON CONSTRAINT` always works with a partial unique index name.”** No. Partial unique indexes are not table constraints of that form.

**20. “Omitting the predicate in `ON CONFLICT` always infers a partial unique arbiter.”** Not guaranteed and will fail unless a matching full unique index exists.

**21. “A unique index on `lower(email)` makes every `email = ...` query case-insensitive.”** No. `email = ...` and `lower(email) = ...` have different semantics and key matching.

**22. “`now()` is valid in a predicate because time stays constant inside one transaction.”** False. Partial index predicates require `IMMUTABLE` functions; `now()` is `STABLE`.

**23. “A fixed literal date cutoff automatically slides like a 7-day window.”** False. Static predicates never move as the clock advances.

**24. “Creating one partial index per tenant is always optimal.”** No. Thousands of indexes create severe write and management overhead.

**25. “Indexes provide tenant security isolation.”** False. Always enforce roles, RLS, and query guards.

**26. “Having all columns in `INCLUDE` guarantees zero heap fetches in Index Only Scan.”** False. Visibility map state and planner costs still apply.

**27. “An index with low `idx_scan` should always be dropped.”** No. Partial unique indexes protect write integrity, and counters depend on workload cycles.

**28. “Adding more indexes always makes writes faster.”** False. `INSERT`/`UPDATE`/`DELETE` must maintain indexes.

**29. “Changing `status` doesn't touch the index since `status` isn't a key column.”** False. `status` in the predicate governs index membership.

**30. “Because a row is outside the partial index, updating it is always HOT.”** False. Predicate dependencies and other indexes affect HOT eligibility.

**31. “`CREATE INDEX CONCURRENTLY` can run inside `BEGIN`.”** False. Explicit transaction blocks are forbidden.

**32. “`CONCURRENTLY` guarantees zero load or wait impact.”** False. It has resource costs and transaction-wait phases.

**33. “Changing `WHERE` in queries updates the index predicate.”** False. You must create a new index with the new predicate.

**34. “`EXPLAIN ANALYZE` only inspects plans without running SQL.”** False. It executes DML; use lab `SELECT`s or controlled transactions.

**35. “A smaller index always makes every query faster.”** No. Key columns, selectivity, `ORDER BY`, heap fetches, and costs decide.

**36. “Partial indexes replace partitioning for all retention needs.”** No. They neither delete nor separate table data.

---

## 23. Practice Exercises with Solutions

### Exercise 1 — Identifying Keys and Predicate

Given:

```sql
CREATE INDEX jobs_queue_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status='queued';
```

**Question:** which part is the index key and which is the predicate?

**Answer:** `(tenant_id, run_after)` is the key; `status = 'queued'` is the predicate. `status` does not need to appear in the key.

### Exercise 2 — Q ⇒ P

Predicate `P: status = 'queued'`. Query `Q: status = 'queued' AND tenant_id = 3`.

**Answer:** `Q ⇒ P` holds because every row satisfying `Q` is queued; the partial index is eligible.

### Exercise 3 — OR Breaking Implication

```sql
WHERE status='queued' OR priority=9
```

**Answer:** does not imply `status = 'queued'`. A `done` row with `priority = 9` also satisfies `Q`.

### Exercise 4 — Inequality

Index predicate `priority < 8`. Query `priority < 4`.

**Answer:** the query is a subset because `priority < 4 ⇒ priority < 8`. PostgreSQL recognizes simple inequality implications like this.

### Exercise 5 — Reverse Inequality

Index predicate `priority < 8`. Query `priority < 10`.

**Answer:** does not imply, because `priority = 8` or `9` are counterexamples.

### Exercise 6 — Creating a Queued Index

**Prompt:** queries filter queued jobs by tenant and `run_after`; write a partial index.

**Answer:**

```sql
CREATE INDEX jobs_queue_lookup_ex_idx
ON partial_idx_lab.jobs (tenant_id, run_after)
WHERE status='queued';
```

The lab already has `jobs_queued_tenant_run_after_idx` serving a nearly identical purpose; this is a syntax exercise. In production, avoid keeping duplicate overlapping indexes.

### Exercise 7 — Querying with the Matching Predicate

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND status='queued'
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

**Answer:** the query implies `status = 'queued'`. Run `EXPLAIN` to see whether the planner picks the index by cost.

### Exercise 8 — Missing Status Filter

```sql
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND run_after <
      TIMESTAMPTZ '2026-11-14 02:00+00';
```

**Answer:** does not imply queued. The query needs all statuses for that tenant and time window, so the queued partial index cannot cover complete results.

### Exercise 9 — Generic Prepared Statement

```sql
PREPARE q(TEXT) AS
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status=$1;
```

**Question:** can a generic plan always use an index with `WHERE status = 'queued'`?

**Answer:** no. `$1` could be `'done'`. A generic plan must be valid for all possible parameter values.

### Exercise 10 — Custom Prepared Statement

**Question:** can a custom plan for `$1 = 'queued'` consider the queued partial index?

**Answer:** yes, when the parameter value is known at plan time and implication is recognized. Cost still governs; inspect with `EXPLAIN EXECUTE`.

### Exercise 11 — Hardcoding the Fixed Predicate in SQL

**Prompt:** design a query fetching only queued jobs while binding tenant and cutoff.

**Answer:**

```sql
PREPARE q_queued(INTEGER, TIMESTAMPTZ) AS
SELECT job_id
FROM partial_idx_lab.jobs
WHERE status='queued'
  AND tenant_id=$1
  AND run_after<$2;
```

`status = 'queued'` is a constant fixed by the endpoint contract; remaining inputs stay bound parameters.

### Exercise 12 — Partial Unique Index

**Prompt:** within a tenant, live emails must be unique under `lower(email)`, while soft-deleted emails stay for history.

**Answer:**

```sql
CREATE UNIQUE INDEX contacts_live_email_uq_ex
ON partial_idx_lab.contacts
    (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

The lab table already has `contacts_live_email_uq` with the same definition; do not keep both. This command demonstrates syntax.

### Exercise 13 — Soft Delete and Uniqueness

**Question:** if tenant 10's contact with email X has `deleted_at IS NOT NULL`, can you insert a new live contact with email X?

**Answer:** yes, because the partial unique index covers only `deleted_at IS NULL`, provided no other **live** contact shares `(tenant_id, lower(email))`.

### Exercise 14 — ON CONFLICT with Partial Unique Index

**Suggested answer:**

```sql
INSERT INTO partial_idx_lab.contacts
    (tenant_id, email, display_name)
VALUES (10, 'an@example.test', 'Test')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO NOTHING;
```

Note that the conflict target must match the arbiter index definition.

### Exercise 15 — NULL

Predicate `P: completed_at IS NULL`. Query `Q: completed_at IS NULL AND tenant_id = 3`.

**Answer:** `Q ⇒ P` holds. Conversely, `WHERE completed_at = NULL` is invalid for testing `NULL`.

### Exercise 16 — Time Functions

```sql
-- CREATE INDEX ... WHERE created_at > now()-INTERVAL '7 days';
```

**Question:** why is this invalid?

**Answer:** `now()` is not `IMMUTABLE`; an index predicate cannot update membership as time passes. Consider a full-table index on `created_at`, partitioning/BRIN, or managed literal cutoffs.

### Exercise 17 — Single-Tenant Index

Index:

```sql
CREATE INDEX jobs_tenant2_only_idx
ON partial_idx_lab.jobs (run_after)
WHERE tenant_id=2 AND status='queued';
```

**Question:** can a query for tenant 3's queued jobs use this index as a complete source?

**Answer:** no. The index holds only tenant 2.

### Exercise 18 — Why Does a Partial Index Still Have Costs?

**Answer:** PostgreSQL must evaluate the predicate and maintain entries on `INSERT`/`UPDATE`/`DELETE`; transitioning `queued → running` removes entries from the index; the index also consumes storage, WAL, and can affect HOT updates.

### Exercise 19 — Reading EXPLAIN

**Prompt:** inspect the plan for tenant 2's queued jobs query.

**Answer:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM partial_idx_lab.jobs
WHERE tenant_id=2
  AND status='queued'
ORDER BY run_after
LIMIT 20;
```

Inspect `Index Cond`, `Filter`, `actual`/`estimated` rows, and `Buffers`. Never assume the chosen plan node before observing it.

### Exercise 20 — INCLUDE and Index-Only Scans

**Question:** if an index has `INCLUDE (created_at)`, is a query selecting `created_at` guaranteed to run `Index Only Scan`?

**Answer:** no. It provides the **required columns** for an `Index Only Scan`, yet planner costs and the MVCC visibility map still determine the chosen plan and `Heap Fetches`.

### Exercise 21 — Index Unusable for Historical Queries

A query must also return soft-deleted contacts:

```sql
SELECT contact_id
FROM partial_idx_lab.contacts
WHERE tenant_id=10
  AND lower(email)='an@example.test';
```

**Answer:** the query does not imply `deleted_at IS NULL`, so the live partial index lacks historical rows.

### Exercise 22 — Where Can You Inspect Index Usage?

**Answer:** `pg_stat_user_indexes` reports `idx_scan`, `idx_tup_read`, `idx_tup_fetch`; `pg_indexes` shows definitions; `pg_relation_size` gives disk size; `EXPLAIN` shows per-query execution plans.

### Exercise 23 — Can CONCURRENTLY Run Inside a Transaction?

**Answer:** no. `CREATE INDEX CONCURRENTLY` is forbidden inside explicit transaction blocks; deploy outside transactions and inspect validity if a build fails.

### Exercise 24 — When Is a Partial Index a Poor Choice?

**Answer:** when most rows satisfy the predicate, queries omit matching conditions, status mutates constantly, or time-based retention is the real problem—where full indexes, partitioning, BRIN, or other designs fit better.

---

## 24. Checklist for Choosing and Operating Partial Indexes

Before creating a partial index in PostgreSQL, answer:

1. **What is the core workload?** Which queries run most often, with what exact `WHERE` and `ORDER BY`?
2. **How small is the hot subset?** Does the predicate cover 1%, 5%, or 95% of rows?
3. **What is predicate `P`?** Is it concise, stable, and free of time-varying functions?
4. **Does query `Q` truly imply `P`?** Try finding a counterexample where `Q` is `TRUE` and `P` is not `TRUE`.
5. **Can the planner recognize the implication?** Prefer direct comparisons and matching expressions over complex proofs.
6. **Are parameters involved?** Generic plans may fail predicate implication; test custom vs. generic plans.
7. **Are index key columns in the right order?** Leading tenant, filter/sort keys, and range-scan stop conditions?
8. **Does the query have `ORDER BY`/`LIMIT`?** Can it leverage B-tree order for early stopping?
9. **What do nullable columns mean?** Verify `IS NULL`, `IS NOT NULL`, `NOT`, and three-valued logic.
10. **Is a partial unique index needed?** For active/soft-delete invariants, verify keys and predicate carefully.
11. **Can `ON CONFLICT` infer the arbiter index?** Check conflict columns/expressions and index predicate.
12. **Is the table multi-tenant?** Indexes never replace RLS or permissions; keep tenant guards and isolation intact.
13. **Are there duplicate indexes?** A partial unique index may already serve `SELECT`s; avoid maintaining two copies.
14. **What is the write overhead?** Consider predicate/key churn, HOT eligibility, WAL, size, and bloat.
15. **Is `INCLUDE` justified?** Balance index-only scan benefits against wider index entries.
16. **Is a sliding time window needed?** Never use `now()` in an index predicate; pick an architecture with clean lifecycle management.
17. **Are statistics fresh?** Run `ANALYZE` after bulk loads and watch for estimation drift.
18. **Did you test `EXPLAIN` on real queries?** For parameterized SQL, check the actual plan mode used.
19. **Is online deployment planned?** `CREATE INDEX CONCURRENTLY` has restrictions and cannot run inside transaction blocks.
20. **Is index usage monitored?** Combine `pg_stat_user_indexes`, sizes, and workload knowledge; never drop solely for low `idx_scan`.
21. **Is there a plan to change predicates later?** Check data conflicts and transition indexes safely.
22. **Is another option better?** Full B-tree, BRIN, partitioning, materialized views, or query rewrites.

---

## 25. Summary

A **partial index** stores entries solely for rows satisfying the **index predicate**. It shines for compact hot subsets such as `queued` jobs, `deleted_at IS NULL` records, unreconciled transactions, or rare error states. Yet its effectiveness hinges strictly on the **relationship between query filters and the index predicate**.

Remember five key points:

1. **The implication direction is `Q ⇒ P`:** every row requested by the query must fall inside the partial index's subset.
2. **Logical truth is not enough:** PostgreSQL recognizes only straightforward implications, and the planner still weighs cost, key column order, and statistics afterward.
3. **`AND` usually strengthens predicates while `OR` can break them** if any branch admits rows outside the index; `NULL`s obey three-valued logic.
4. **Generic prepared plans cannot assume `$1` is always `'queued'`**, whereas custom plans can; for endpoints strictly serving queued rows, hardcode `status = 'queued'` in SQL and bind remaining parameters.
5. **Partial `UNIQUE` indexes both accelerate reads and enforce conditional data invariants** such as “active emails are unique per tenant,” yet they never replace authorization, auditing, transaction locking, or index lifecycle management.

**Final rule of thumb:** before adding a partial index, write down **`P` (index predicate)** and **`Q` (query `WHERE`)**. Try to construct a row where `Q` is `TRUE` and `P` is not `TRUE`. If such a counterexample exists, the index cannot cover the whole query. If none exists, verify that the planner recognizes it and that the index beats alternative access paths on cost.

### Official PostgreSQL Documentation

- [Partial Indexes — `11.8`](https://www.postgresql.org/docs/current/indexes-partial.html).
- [CREATE INDEX — Predicate, INCLUDE, UNIQUE, and CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html).
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html).
- [PREPARE — Generic and Custom Plans](https://www.postgresql.org/docs/current/sql-prepare.html).
- [INSERT — ON CONFLICT and Index Inference](https://www.postgresql.org/docs/current/sql-insert.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Statistics Collector and Index Usage](https://www.postgresql.org/docs/current/monitoring-stats.html).
