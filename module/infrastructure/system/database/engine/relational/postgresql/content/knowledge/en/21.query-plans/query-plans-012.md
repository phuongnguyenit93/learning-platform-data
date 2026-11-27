# Extended Statistics for Dependent Columns in PostgreSQL

A query can have clean SQL and proper indexes, yet PostgreSQL may still pick an unexpected execution plan. A major reason lies in **cardinality estimation**: PostgreSQL must predict how many rows satisfy predicates, how many groups emerge from `GROUP BY`, and how many rows flow through each step before actually running the query.

When filters involve multiple related columns, single-column statistics alone fall short. For example:

- `category_id = 7` virtually determines `category_code = 'CAT-007'`.
- `province_id` and `province_name` encode the same entity.
- `district_id` determines `province_id`, though the reverse does not hold.
- A combination of `country_code` and `currency_code` can occur far more frequently than predicted if both columns were treated as independent.

If the planner simply multiplies the probabilities of two predicates, it might predict only **10 rows** when **1,000 rows** actually match. That error can flip decisions on sequential scan vs. index scan, join order, hash join vs. nested loop, or aggregation strategy.

PostgreSQL provides **extended statistics**, defined with `CREATE STATISTICS`, to help the planner understand relationships **across multiple columns** within the same relation. Among them, **functional dependencies**—`dependencies`—are especially helpful for columns whose values depend on one another.

Part of the **Query Plans** chapter, this lesson focuses on understanding and applying extended statistics accurately, from selectivity theory through hands-on examples, metadata catalogs, costs, and planner limits.

## 1. The Root Problem: The Planner Must Predict Row Counts

When planning:

~~~sql
SELECT *
FROM orders
WHERE region_id = 10
  AND region_name = 'North';
~~~

PostgreSQL does not execute every candidate plan first and time them. Instead, the planner draws on available metadata:

- Estimated relation size and page count.
- Per-column value distribution statistics.
- NULL fraction.
- Most common values (MCVs).
- Histograms and estimated distinct value counts.
- Available indexes.
- Multi-column extended statistics, if created and analyzed.
- Cost constants, parallelism settings, and query structure.

A central concept is **selectivity**: the fraction of rows expected to satisfy a condition.

If a table has 100,000 rows and a condition is estimated at selectivity 0.01:

\[
\text{estimated rows} \approx 100{,}000 \times 0.01 = 1{,}000
\]

The planner carries that number into upper nodes. If reality is 1,000 rows while the planner predicts 10, that discrepancy cascades into downstream joins and aggregations.

### 1.1. EXPLAIN Shows Estimates; EXPLAIN ANALYZE Shows Actuals

~~~sql
EXPLAIN
SELECT *
FROM some_table
WHERE a = 7 AND b = 'X';
~~~

In the output, numbers like `rows=10` are **planner estimates**.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM some_table
WHERE a = 7 AND b = 'X';
~~~

With `ANALYZE`, PostgreSQL **actually executes the query** and reports observed rows in `actual rows` alongside execution iterations (`loops`).

Estimates and actuals do not have to match identically; the goal is keeping estimates close enough for the planner to choose a sound plan.

### 1.2. Reading Row Counts Properly per Node

In a complex plan, a node might report `rows=100` and `actual rows=20 loops=5`. `actual rows` is generally displayed **per execution loop** of the node, so always account for `loops` when comparing total work.

Do not compare a single child node's `actual rows` directly against the entire query's total rows without understanding the plan tree.

## 2. The Independence Assumption and Multiplying Selectivities

When PostgreSQL lacks reliable information about how predicates relate, combined selectivity estimation usually falls back on **statistical independence**.

For two predicates A and B:

\[
P(A\land B)\approx P(A)\times P(B)
\]

Example:

~~~text
Table: 100,000 rows

category_id has 100 values, uniformly distributed:
P(category_id = 7) ≈ 0.01

category_code has 100 values, uniformly distributed:
P(category_code = 'CAT-007') ≈ 0.01

Assuming independence:
P(both) ≈ 0.01 × 0.01 = 0.0001

Estimated rows ≈ 100,000 × 0.0001 = 10.
~~~

Yet if every `category_id` always maps to one `category_code`:

~~~text
category_id=7  -> category_code='CAT-007'

Out of 100,000 rows:
  category_id=7 and category_code='CAT-007'
  actually appear 1,000 times.
~~~

That is a 100× error:

\[
\frac{\text{actual rows}}{\text{estimated rows}}
=\frac{1{,}000}{10}=100
\]

### 2.1. Why Can Estimation Errors Lead to Poor Plans?

If the planner expects only 10 rows, it may choose a plan suited for tiny sets—such as a Nested Loop performing index lookups into another table. When 1,000 or 100,000 rows actually show up, another strategy could perform far better.

Still, **a wrong estimate does not automatically mean the chosen plan is bad**: plan selection also depends on indexes, table size, cache state, data layout, and per-operator costs.

### 2.2. Not Every Pair of Columns Is Independent

Common examples:

| Column A | Column B | Possible Relationship |
|---|---|---|
| `city_id` | `country_id` | City determines country |
| `department_code` | `department_name` | Department code determines name |
| `postal_code` | `city` | Often dependent, depending on country/data quality |
| `product_id` | `category_id` | Product determines category |
| `region_code` | `region_label` | May represent the same classification |
| `status` | `resolution_code` | May have dominant or impossible combinations |

Do not assume every related pair is one-to-one. For instance, `country_id` does not uniquely determine `city_id` when a country has many cities.

## 3. What Are Extended Statistics?

**Extended statistics** are extra statistics gathered by PostgreSQL across **multiple columns**—or, in supported versions, **expressions**.

Standard syntax:

~~~sql
CREATE STATISTICS statistics_name (dependencies)
ON column_a, column_b
FROM schema_name.table_name;
~~~

Followed by:

~~~sql
ANALYZE schema_name.table_name;
~~~

These steps are distinct:

1. `CREATE STATISTICS` declares the **statistics object** and which statistics kinds to collect.
2. `ANALYZE` samples/reads table data to **populate measurements** for that object.
3. The planner uses those statistics when estimating matching query patterns.

### 3.1. This Is Not an Index

`CREATE STATISTICS` **creates no physical access structure** like B-tree, GiST, or GIN. It does not reorder table reads or jump directly to matching rows.

It helps the planner **pick a better plan** through better estimates. To speed up physical row retrieval, you still need appropriate indexes and query design.

### 3.2. This Is Not a Constraint

Statistics do not enforce data dependencies. Even if `category_id=7` usually pairs with `'CAT-007'`, an `INSERT` containing `'CAT-999'` will still succeed unless blocked by constraints or write logic.

When business rules require consistent categories, rely on normalized schemas, `FOREIGN KEY`, `UNIQUE`, or check constraints—never statistics—to protect integrity.

### 3.3. Statistics Do Not Change Query Results

Adding statistics leaves a SELECT query's logical meaning and result set unchanged. What changes is the **cardinality estimate**, and consequently the **physical plan** selected.

## 4. The Three Core Extended Statistics Kinds

PostgreSQL supports three primary extended statistics kinds:

| Kind | Syntax | Primary Problem Solved |
|---|---|---|
| Functional dependencies | `dependencies` | Columns whose values determine or depend on one another |
| Multivariate distinct counts | `ndistinct` | Estimating distinct combination counts for multi-column `GROUP BY` |
| Multivariate most common values | `mcv` | Estimating skewed, uneven joint value combinations |

One object can request multiple kinds:

~~~sql
CREATE STATISTICS sales_stats (dependencies, ndistinct, mcv)
ON region_id, region_name, status
FROM sales;
~~~

This snippet illustrates syntax assuming a `sales` table with those columns exists.

### 4.1. Match the Kind to the Problem, Not Guesswork

If:

~~~sql
SELECT *
FROM catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

is underestimated because the two columns are functionally dependent, `dependencies` is the natural candidate.

If:

~~~sql
SELECT category_id, status, COUNT(*)
FROM catalog
GROUP BY category_id, status;
~~~

misestimates the **number of distinct groups**, `ndistinct` fits better.

If certain `(region, status)` pairs occur heavily while others barely exist, `mcv` captures that skew far better than marginal column frequencies.

## 5. Functional Dependency: What Does “X Determines Y” Mean?

A functional dependency is written as:

\[
X \rightarrow Y
\]

Meaning: knowing the value of \(X\) determines the value of \(Y\) within the dataset or invariant considered.

Example:

~~~text
category_id  category_code
-----------  -------------
7            CAT-007
7            CAT-007
7            CAT-007
9            CAT-009
9            CAT-009
~~~

In this dataset:

~~~text
category_id -> category_code
~~~

because every row with the same `category_id` shares the same `category_code`.

### 5.1. One-Way Dependencies

If:

~~~text
district_id -> province_id
~~~

each district belongs to one province. Yet:

~~~text
province_id -> district_id
~~~

is normally **false**, because a province contains many districts.

Dependency strength and direction both matter—not merely knowing “two columns are related.”

### 5.2. Data with Exceptions

A real table might contain:

~~~text
category_id=7, category_code=CAT-007  99.5% of rows
category_id=7, category_code=CAT-008   0.5% of rows
~~~

Here the relationship is strong without being absolute. Extended statistics capture **statistical dependence strength**, rather than enforcing a strict logical invariant like a constraint.

### 5.3. Multi-Column Determinants

Sometimes `(tenant_id, local_code)` jointly determines `display_label`, while neither column alone suffices:

\[
(\text{tenant\_id},\text{local\_code})\rightarrow\text{display\_label}
\]

PostgreSQL can gather multi-column dependency degrees depending on version and statistics configuration, though you should not assume the planner applies those coefficients to arbitrary complex expressions.

## 6. How dependencies Fixes Probability Multiplication Errors

Suppose two columns effectively encode the same category. Without extended statistics, the planner sees:

~~~text
P(category_id=7)             ≈ 0.01
P(category_code='CAT-007')   ≈ 0.01

Without dependency:
P(both) ≈ 0.0001
~~~

Once the planner knows `category_id` determines `category_code`, the second predicate **does not shrink the row count by another factor of 100** when predicates align.

Conceptual model:

~~~text
With strong dependency:
P(category_id=7 AND category_code='CAT-007')
approximately equals P(category_id=7)
≈ 0.01
~~~

In practice, PostgreSQL applies dependency degree coefficients and estimation formulas rather than crudely dropping one condition outright.

### 6.1. Even a Perfect Dependency Does Not Make a Query Fast by Itself

What changes first is the **row-count prediction**. A query may still scan 100,000 rows if no suitable index or alternative access path exists.

### 6.2. The Planner Is Not a Strict Logical Theorem Prover

Extended statistics reflect sampled `ANALYZE` data. It is not a constraint solver, cannot guarantee future inserts obey the relationship, and will not reliably catch contradictory values.

For example:

~~~sql
WHERE category_id = 7
  AND category_code = 'CAT-008'
~~~

If real data only has `category_id=7 -> CAT-007`, the true output is 0 rows. Yet **dependency statistics may still estimate a positive row count**, because dependency coefficients scale compatible/redundant conditions rather than proving a mismatch impossible.

That is an **important limitation** of `dependencies`.

## 7. When Does the Planner Use Functional Dependencies?

Extended dependencies work best for `WHERE` clauses containing **simple column-to-constant equality comparisons**.

Well-matched pattern:

~~~sql
SELECT *
FROM catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

Or constant lists where supported:

~~~sql
SELECT *
FROM catalog
WHERE category_id IN (7, 8, 9)
  AND category_code = 'CAT-007';
~~~

Do not assume both examples receive identical estimation logic; `IN` selectivity and mixed combinations behave differently from plain equalities.

### 7.1. Cases Where You Should Not Expect Direct Help from dependencies

Documented PostgreSQL limitations for functional dependencies include:

- Column-to-column conditions (`col1 = col2`) instead of column-to-constant.
- Comparing a column against non-constant expressions.
- Range predicates like `x > 10` or `x BETWEEN ...`.
- Pattern predicates like `LIKE 'ABC%'`.
- Multi-table joins where correlation lives across the join boundary.

Example:

~~~sql
SELECT *
FROM catalog
WHERE category_id > 50
  AND category_code LIKE 'CAT-0%';
~~~

Do not expect `dependencies` to automatically fix estimates here just because the two columns are related.

### 7.2. Functional Dependencies Do Not Cover Arbitrary AND/OR Combinations

An `AND` of multiple constant equalities is the canonical case. Complex expressions with `OR`, ranges, functions, or joins call for other statistics kinds, plan inspection, and real `EXPLAIN` verification.

### 7.3. Cross-Table JOINs Are a Key Boundary

~~~sql
SELECT *
FROM orders AS o
JOIN customers AS c
  ON o.customer_id = c.customer_id
WHERE o.country_code = c.country_code;
~~~

Even when columns across tables correlate logically, **single-table extended statistics do not become cross-table join statistics usable across arbitrary join predicates**.

Specifically, PostgreSQL still limits how extended statistics factor into **cross-table join selectivity estimation**. Never promise `CREATE STATISTICS` will fix every join-driven Nested Loop mismatch.

## 8. Lab: Creating Data with Two Perfectly Dependent Columns

Run this lab in a **test database** inside its own schema. If `extstats_lab` already exists, pick another schema name instead of wiping unrelated data.

### 8.1. Create Schema

~~~sql
CREATE SCHEMA extstats_lab;
~~~

### 8.2. Create Catalog Table

~~~sql
CREATE TABLE extstats_lab.catalog (
    product_id BIGINT PRIMARY KEY,
    category_id INTEGER NOT NULL,
    category_code TEXT NOT NULL,
    status TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL
);
~~~

### 8.3. Load 100,000 Rows

~~~sql
INSERT INTO extstats_lab.catalog (
    product_id,
    category_id,
    category_code,
    status,
    price
)
SELECT
    n AS product_id,
    (n % 100) + 1 AS category_id,
    'CAT-' || lpad(((n % 100) + 1)::text, 3, '0')
        AS category_code,
    CASE
        WHEN ((n / 100) % 10) < 8 THEN 'active'
        ELSE 'archived'
    END AS status,
    (10 + (n % 400))::NUMERIC(12, 2) AS price
FROM generate_series(1, 100000) AS gs(n);
~~~

In this dataset:

- There are exactly 100 distinct `category_id` values.
- Each category has 1,000 products.
- `category_id=7` always pairs with `category_code='CAT-007'`.
- `category_id=8` always pairs with `'CAT-008'`.
- `status` alternates between `'active'` and `'archived'` on a separate formula for later multi-column exercises.

This is synthetic data and does not reflect real production product distributions.

### 8.4. Verify the Data Relationship

~~~sql
SELECT
    category_id,
    COUNT(DISTINCT category_code) AS distinct_codes,
    COUNT(*) AS row_count
FROM extstats_lab.catalog
GROUP BY category_id
ORDER BY category_id
LIMIT 10;
~~~

On the unmodified lab dataset, each `category_id` has **one `category_code`** and **1,000 rows**.

### 8.5. Do Not Confuse Data Inspection with Constraints

That `SELECT` only verifies the invariant **in current rows**. It does not prevent future `INSERT`s from breaking it.

In a production schema, if `category_code` belongs solely to a category, normalizing into a `categories` table with a foreign key from `catalog.category_id` is often cleaner than duplicating codes on every product row. Extended statistics help the planner when denormalized/dependent columns exist—they do not replace schema modeling.

## 9. Baseline: ANALYZE and EXPLAIN Before Extended Statistics

First collect per-column statistics:

~~~sql
ANALYZE extstats_lab.catalog;
~~~

### 9.1. Single-Column Predicate Check

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7;
~~~

Actual rows should be 1,000. The planner will likely estimate close to 1,000 once column statistics are fresh.

### 9.2. Two-Column Predicate Check

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

Under the independence assumption:

~~~text
Selectivity category_id=7          ~1/100
Selectivity category_code=CAT-007  ~1/100
Estimated combined rows            ~10
Actual rows                        1000
~~~

Exact estimates depend on sampling, PostgreSQL version, config, and data state. This is an **illustrative expectation**, not a guarantee that every server prints `rows=10`.

### 9.3. Recording Baseline Metrics

When running the lab, capture:

| Criterion | Before Extended Statistics |
|---|---|
| Access plan | Seq Scan, Index Scan, or Bitmap Scan? |
| `rows=...` | How many rows did the planner predict? |
| `actual rows=...` | How many rows matched at runtime? |
| `loops=...` | How many times did the node execute? |
| Timing | Reference only in a lab environment |
| Buffers | Shared/cache block counts if shown |

The focus of this lesson is **cardinality error**, not chasing millisecond jitter on tiny test queries.

## 10. Creating dependencies Statistics

Create the object on the two columns of the same table:

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

Then **you must run ANALYZE** to populate the statistics:

~~~sql
ANALYZE extstats_lab.catalog;
~~~

### 10.1. Why Is Another ANALYZE Required?

`CREATE STATISTICS` merely tells PostgreSQL **what statistics to gather**. It does not scan the table and populate distributions when the DDL runs.

Running `EXPLAIN` right after `CREATE STATISTICS` without `ANALYZE` leaves the planner without the new extended statistics.

### 10.2. Re-Running the Same EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

With strongly dependent columns, the planner's row estimate should move **much closer to actuals** than the baseline without dependencies.

### 10.3. Visualizing the Difference

| Condition | Without `dependencies` | With `dependencies` | Lab Reality |
|---|---:|---:|---:|
| `category_id=7` | Around 1,000 | Around 1,000 | 1,000 |
| `category_code='CAT-007'` | Around 1,000 | Around 1,000 | 1,000 |
| Both predicates | Likely around 10 | Likely near 1,000 | 1,000 |

Numbers in this table illustrate the trend; exact estimates vary with sampling and planner internals.

### 10.4. The Plan May Still Choose Seq Scan

On a 100,000-row table without an index on `category_id`, the planner will likely pick `Seq Scan` both before and after adding statistics. That **does not mean `dependencies` failed**: inspect `rows` estimates before judging solely by plan node names.

## 11. Contradictory Predicates

Try:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-008';
~~~

In our lab dataset, zero rows satisfy both conditions.

### 11.1. Dependencies Are Not a Constraint Solver

Functional dependencies adjust selectivity estimates for correlated predicates. They do not deduce that `7` exclusively pairs with `'CAT-007'` and therefore `(7, 'CAT-008')` is impossible.

Thus the estimator **may still predict a positive row count** even though `actual rows=0`.

### 11.2. Distinguishing Valid vs. Invalid Combinations

When combinations vary sharply in frequency or many pairs barely exist, **multivariate MCV** can outperform `dependencies` for certain query patterns.

Even MCV is not an exhaustive logical guarantee for every combination—use schema constraints or proper normalization to forbid invalid rows.

## 12. Inspecting Collected Data in pg_stats_ext

PostgreSQL exposes collected extended statistics through the `pg_stats_ext` view (subject to permissions):

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    dependencies
FROM pg_stats_ext
WHERE schemaname = 'extstats_lab'
  AND tablename = 'catalog'
ORDER BY statistics_name;
~~~

Useful columns:

| Column | Content |
|---|---|
| `schemaname` | Table schema |
| `tablename` | Table name |
| `statistics_name` | Statistics object name |
| `attnames` | Included columns |
| `kinds` | Enabled statistics kinds |
| `dependencies` | Collected dependency data in human-readable text format |
| `n_distinct` | Multi-column distinctness metadata (when `ndistinct` enabled) |
| `most_common_vals` | Frequent combinations (when `mcv` enabled) |

### 12.1. Sample Dependency Representation

In output, dependency data looks similar to:

~~~text
{"2 => 3": 1.000000, "3 => 2": 1.000000}
~~~

This is **format illustration only**, not fixed lab output or fixed attribute numbers (`attnum`). Numbers identify internal column attribute numbers and dependency degrees, not column names.

Never copy a dependency string from one table to another assuming identical meaning.

### 12.2. Do Not Confuse Degree 1.0 with Absolute Prediction Certainty

A dependency degree near 1 signals a very strong relationship in the sample—it neither guarantees exact cardinality estimates on every query nor acts as a database constraint.

### 12.3. Access Permissions

`pg_stats_ext` enforces privilege checks over underlying statistics data. Less-privileged roles may not see all entries; never grant superuser privileges to application accounts solely to inspect query plans.

## 13. The pg_statistic_ext and pg_statistic_ext_data Catalogs

PostgreSQL stores extended statistics definitions and payloads in two catalogs:

- `pg_statistic_ext`: object metadata such as name, target table, enabled kinds, and columns/expressions.
- `pg_statistic_ext_data`: serialized statistical payloads, subject to access restrictions.

Inspecting object metadata:

~~~sql
SELECT
    s.oid,
    n.nspname AS statistics_schema,
    s.stxname AS statistics_name,
    s.stxrelid::regclass AS target_table,
    s.stxkind
FROM pg_statistic_ext AS s
JOIN pg_namespace AS n
  ON n.oid = s.stxnamespace
WHERE s.stxrelid = 'extstats_lab.catalog'::regclass;
~~~

### 13.1. Kind Codes

Catalog metadata encodes statistics kinds with internal characters. For day-to-day administration, `pg_stats_ext.kinds` and `CREATE STATISTICS` DDL are far clearer than relying on internal storage layouts.

### 13.2. Do Not Depend on Internal Catalogs as a Stable Application API

PostgreSQL internal catalog layouts can change across major releases. For migrations and long-lived monitoring scripts, prefer official views and documented SQL over parsing raw internal formats like `stxddependencies`.

### 13.3. Statistics Do Not Store Queryable Row Mappings

`pg_statistic_ext_data` holds statistical summaries for estimation—not a complete lookup table mapping `category_id -> category_code` for application queries.

## 14. The ndistinct Kind: When Multi-Column GROUP BY Misestimates

`dependencies` addresses a class of `WHERE` filters. Another kind, **`ndistinct`**, targets counts of distinct multi-column combinations.

Suppose a table has:

~~~text
category_id: 100 distinct values
category_code: 100 distinct values
Relationship: each category_id maps to exactly one category_code
~~~

Actual `(category_id, category_code)` combinations number **100**, not `100 × 100 = 10,000`.

### 14.1. Impact on GROUP BY

~~~sql
SELECT
    category_id,
    category_code,
    COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

If the planner overestimates group counts, aggregation strategy choice (HashAggregate vs. GroupAggregate), hash-table sizing, and memory estimates suffer.

### 14.2. Creating ndistinct

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

Then test:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    category_id,
    category_code,
    COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

Compare the estimated group count on Aggregate/HashAggregate/GroupAggregate nodes, not just the child scan estimate.

### 14.3. Why dependencies Does Not Replace ndistinct

One models filter predicate selectivity; the other estimates **distinct combination counts**. Both can target the same columns while serving entirely different planner stages.

### 14.4. Counting Actual Distinct Groups

Verify true combination counts with:

~~~sql
SELECT COUNT(*) AS actual_groups
FROM (
    SELECT category_id, category_code
    FROM extstats_lab.catalog
    GROUP BY category_id, category_code
) AS grouped;
~~~

The unmodified lab dataset yields **100 groups**.

## 15. The mcv Kind: Capturing Frequent Value Combinations

`mcv` stands for **multivariate most-common-values statistics**: it stores recurring value combinations and their observed frequencies.

Suppose:

~~~text
region='north', status='active'   very frequent
region='north', status='archived' rare
region='south', status='active'   moderate
~~~

Individual column ratios for `region` and `status` cannot capture this joint distribution.

### 15.1. Creating mcv

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_mcv
    (mcv)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

Subject to target limits and distribution shape, MCV records common pairs. With 100 uniformly distributed pairs in our lab table, skew isn't extreme; real tables with highly skewed pairs show stronger MCV benefits.

### 15.2. Inspecting MCV in the View

~~~sql
SELECT
    statistics_name,
    most_common_vals,
    most_common_freqs,
    most_common_base_freqs
FROM pg_stats_ext
WHERE schemaname = 'extstats_lab'
  AND tablename = 'catalog'
  AND statistics_name = 'catalog_category_mcv';
~~~

- `most_common_vals`: frequent multi-column combinations.
- `most_common_freqs`: estimated actual frequency of each combination.
- `most_common_base_freqs`: baseline frequency predicted under independence, making divergence immediately visible.

### 15.3. Are MCV and Dependencies the Same?

No.

- `dependencies` quantifies functional determination strength, adjusting selectivity for compatible equality predicates.
- `mcv` records **specific combinations** and their exact joint frequencies.
- `ndistinct` tracks distinct combination counts, especially useful for grouping.

### 15.4. When Should MCV Take Priority?

When queries filter specific constant combinations across heavily skewed or sparse cross-distributions, including common pairs and missing combinations. Usage still depends on predicate form, PostgreSQL version, and sample representation.

## 16. Should You Always Create All Three Kinds?

You can write:

~~~sql
CREATE STATISTICS extstats_lab.catalog_composite_stats
    (dependencies, ndistinct, mcv)
ON category_id, category_code, status
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

However, **more kinds and more columns are not always better**.

### 16.1. Overhead of Too Many Objects

- Longer `ANALYZE` duration.
- Larger statistics metadata footprint.
- Added planner overhead evaluating statistics objects.
- Maintenance burden as schemas and queries evolve.
- Collecting stats on columns that bring no real benefit.

### 16.2. One Three-Column Object Does Not Guarantee Every Three-Column Query Improves

Dependencies come from data patterns, and the planner only applies them to supported clauses. If queries mainly use ranges, `LIKE`, or joins, a broad object may still leave root errors untouched.

### 16.3. Follow the Workload

If the application only filters `category_id=... AND category_code=...`, a compact `dependencies` object suffices. If reporting runs multi-column `GROUP BY`, `ndistinct` serves a distinct need.

## 17. Lab: GROUP BY With and Without ndistinct

To observe the effect directly:

### 17.1. Before Adding ndistinct

If you have not created `catalog_category_nd` yet, run:

~~~sql
ANALYZE extstats_lab.catalog;

EXPLAIN (ANALYZE, BUFFERS)
SELECT category_id, category_code, COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

Record estimated rows at the Aggregate node vs. actual rows.

### 17.2. After Adding ndistinct

~~~sql
CREATE STATISTICS extstats_lab.catalog_pair_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;

EXPLAIN (ANALYZE, BUFFERS)
SELECT category_id, category_code, COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

**Note:** If you already created `catalog_category_nd` earlier, the new object overlaps with it. In practice, **keep only one** `ndistinct` object per column set to avoid redundant stats maintenance.

### 17.3. What Should You Evaluate?

- Did estimated group count move closer to 100?
- Did the planner pick HashAggregate or GroupAggregate?
- Memory Usage, Sort Method, or Disk spill if present.
- Did total execution time change materially?

The plan may keep the same nodes even with much better cardinality estimates. Do not label that a failure when the goal was fixing estimation accuracy.

## 18. Extended Statistics vs. Multi-Column Indexes

An index such as:

~~~sql
CREATE INDEX catalog_category_idx
ON extstats_lab.catalog (category_id, category_code);
~~~

and a statistics object such as:

~~~sql
CREATE STATISTICS extstats_lab.catalog_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

serve completely different purposes.

| Characteristic | Multi-Column Index | Extended Statistics |
|---|---|---|
| Physical data structure | Yes | No |
| Speeds up row lookups directly | Yes, for matching predicates | Not directly |
| Guides planner choices | Via access path / cost | Via cardinality estimation |
| Write overhead on INSERT/UPDATE | Yes, index maintenance per row | No per-row index maintenance |
| Requires ANALYZE for stats data | Index metadata and stats updated regularly | **Requires ANALYZE after CREATE STATISTICS** |
| Helps GROUP BY distinct combinations | May supply ordered scan path | `ndistinct` improves group-count estimate |
| Enforces UNIQUE | Only if created as UNIQUE index | Never |

### 18.1. An Index Alone Does Not Fix Cardinality Estimates

Even when an index makes lookups fast, if the planner expects 10 rows instead of 1,000, upstream join estimates can still break badly. `dependencies` complements the index.

### 18.2. Statistics Cannot Replace Access Paths

If a query pulls 1,000 rows out of hundreds of millions, adding extended statistics without an index will still scan huge data volumes.

### 18.3. Multi-Column Indexes Depend on Column Order

In a B-tree index, leading column order governs predicate usability. `CREATE STATISTICS` has no B-tree “leading column” rule—do not mechanically mirror index column-order rules into statistics definitions.

## 19. When Data Changes: Why ANALYZE Matters

Statistics are sampled snapshots taken at collection time. After substantial inserts, updates, or deletes, distributions drift.

Examples:

- Previously `status='active'` made up 90%.
- After archiving, `'active'` drops to 30%.
- A new category receives millions of products.
- A data migration alters code-to-name mappings.

Until statistics refresh, the planner continues using stale distributions.

### 19.1. Manual ANALYZE

~~~sql
ANALYZE extstats_lab.catalog;
~~~

Use after bulk loading test tables or controlled production data migrations.

### 19.2. Autovacuum Runs Autoanalyze

PostgreSQL automatically triggers `autoanalyze` via autovacuum thresholds. Still, right after a major bulk load or distribution shift, autoanalyze may lag behind immediate queries needing accurate plans.

### 19.3. CREATE STATISTICS Does Not Pre-Populate Data

Even if a table was analyzed repeatedly **before** creating extended statistics, after running a new `CREATE STATISTICS` you must run `ANALYZE` again to populate the new object.

### 19.4. Sampling Inherently Carries Variance

Because `ANALYZE` samples rather than performing a full census of every combination on large tables, rare groups, tail correlations, and rapidly shifting distributions can still exhibit estimation variance.

## 20. Statistics Target: Granularity vs. Cost

PostgreSQL uses a **statistics target** to control collection granularity. On extended statistics objects, adjust it with:

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS 500;

ANALYZE extstats_lab.catalog;
~~~

This syntax assumes `catalog_category_dep` exists.

### 20.1. When Does Raising the Target Help?

- MCV needs room for more frequent combinations.
- Distributions are complex or high-cardinality.
- Default sample size fails to represent key groups.
- Critical queries remain misestimated after a fresh `ANALYZE`.

### 20.2. Raising the Target Does Not Bypass Core Limitations

If the problem is multi-table join selectivity where PostgreSQL does not apply extended dependencies as hoped, raising the target from 100 to 1000 will not fix it.

If the query uses `LIKE` or ranges unsupported by the dependency estimator, a higher target will not make dependencies handle them either.

### 20.3. Increasing Overhead

Higher targets increase sample sizes, `ANALYZE` runtime, statistics catalog storage, and planning overhead. Never set excessive targets globally by default.

### 20.4. default_statistics_target and Column Statistics

Alongside `ALTER STATISTICS`, PostgreSQL offers `default_statistics_target` and per-column `ALTER COLUMN ... SET STATISTICS`. They target distinct layers:

- Per-column stats: single-column histograms, MCVs, `n_distinct`.
- Extended stats: cross-column dependencies, joint `ndistinct`, multivariate MCVs.

Identify **which statistic lacks detail** before tuning targets.

## 21. Workflow for Diagnosing Cardinality Misestimation

A practical runbook:

1. Isolate **one slow query** with realistic representative parameters.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` safely (remember `ANALYZE` executes the query).
3. Locate the **first node** where `rows` and `actual rows` diverge sharply.
4. Inspect predicates at that node: single-column or multi-column?
5. Verify indexes, data types, casts, and `WHERE`/`JOIN` predicates.
6. Inspect single-column statistics in `pg_stats`.
7. Check actual joint distributions and dependencies in representative data.
8. Classify the issue: **WHERE dependencies**, **GROUP BY ndistinct**, or **skewed MCV**.
9. Create the targeted `CREATE STATISTICS` object **on the table holding those columns**.
10. Run `ANALYZE`.
11. Compare estimated rows, plan shape, and execution time carefully.
12. If divergence persists, check planner limits and other factors.
13. Evaluate `ANALYZE`, memory, and catalog overhead to avoid redundant objects.
14. Deploy through migrations with a clean rollback plan.
15. Monitor as data distributions evolve.

### 21.1. Never Start by Cranking Every Statistics Target Up

If the cause is stale statistics, a plain `ANALYZE` may suffice. If the cause is a missing index or non-sargable predicate, extended stats will not solve it.

### 21.2. Always Compare Identical Parameters

A common category can show vastly different row estimates from a rare category. Never compare before/after `EXPLAIN` outputs across two different parameter values and credit the statistics change.

### 21.3. EXPLAIN ANALYZE Executes DML

On `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **actually modifies data**. Run DML tests inside a controlled transaction that rolls back or in a dedicated test environment.

## 22. How Misestimates Propagate Across JOINs

Conceptual query:

~~~sql
SELECT c.product_id, s.quantity
FROM extstats_lab.catalog AS c
JOIN extstats_lab.stock AS s
  ON s.product_id = c.product_id
WHERE c.category_id = 7
  AND c.category_code = 'CAT-007';
~~~

*(Illustrative query structure; `extstats_lab.stock` would need to be created to execute it.)*

### 22.1. If the Planner Expects Only 10 Products

It may pick a Nested Loop planning for ~10 index lookups against `stock`.

### 22.2. When Reality Has 1,000 Products

Runtime performs 1,000 lookups instead. Nested Loop may still hold up if lookups are cached and tiny, or Hash Join / Merge Join may clearly win depending on workload.

### 22.3. Dependencies Fix Estimates on the Filtered Table

Extended stats on `catalog` improve **post-WHERE row estimates within that single table**, which feeds better inputs to upstream join planning.

### 22.4. That Does Not Solve Every Join Selectivity Error

Fixing a base-table scan estimate is different from estimating **selectivity of a join condition between two tables**. PostgreSQL has strict limits on applying extended statistics directly to cross-table join clauses—never promise statistics on `catalog` understand joint selectivity against `stock` or `orders`.

## 23. Additional Example: district_id Determines province_id

Suppose an `addresses` table contains:

~~~text
district_id   province_id
-----------   -----------
1001          10
1002          10
1003          10
2001          20
2002          20
~~~

In this dataset:

~~~text
district_id -> province_id
~~~

Whereas:

~~~text
province_id -/-> district_id
~~~

A query:

~~~sql
SELECT *
FROM addresses
WHERE district_id = 1001
  AND province_id = 10;
~~~

has dependent filters. Without `dependencies`, the planner multiplies independent selectivities and underestimates rows.

### 23.1. Respect Dependency Direction

Because one province contains many districts, knowing `province_id = 10` does not narrow down a unique `district_id`.

### 23.2. Check Data Quality

A single bad row like `(district_id=1001, province_id=20)` weakens strict determinism. Statistics reflect empirical tendencies in the table; they never sanitize or reject dirty writes.

### 23.3. When Should You Normalize Instead?

If a district always belongs to one province, consider normalizing:

~~~text
districts(district_id PRIMARY KEY, province_id REFERENCES provinces)
addresses(address_id, district_id REFERENCES districts)
~~~

and joining when `province_id` is needed, eliminating redundant storage.

When denormalized columns remain intentionally for query workload reasons, extended statistics help the planner—without relieving you of enforcing consistency.

## 24. Multi-Tenant Example: Composite-Key Dependencies

A multi-tenant table stores `tenant_id`, `tenant_region`, and `service_tier`.

Relationships:

~~~text
tenant_id -> tenant_region
tenant_id -> service_tier  (if tier is solely a tenant attribute)
~~~

A query filtering all three:

~~~sql
SELECT *
FROM tenant_events
WHERE tenant_id = 42
  AND tenant_region = 'ap-southeast'
  AND service_tier = 'premium';
~~~

can be underestimated severely if treated as three independent filters.

### 24.1. Multi-Column Statistics Within the Table

~~~sql
CREATE STATISTICS tenant_events_dep
    (dependencies)
ON tenant_id, tenant_region, service_tier
FROM tenant_events;
~~~

*(Illustrative syntax requiring a matching table.)*

### 24.2. Do Dependencies Drift Over Time?

If `service_tier` records the **tier at event time** rather than the tenant's current tier, one tenant may span multiple historical tiers—weakening `tenant_id -> service_tier`.

Always inspect **column semantics** and real data rather than assuming relationships from column names.

### 24.3. Multi-Tenant Isolation Does Not Come from Statistics

Extended stats never protect tenant isolation or replace Row-Level Security, tenant scoping, or API authorization.

## 25. Strong Dependency Does Not Mean High Pearson Correlation

Learners often say “correlation” to mean any association. Keep four concepts distinct:

- **Functional dependency**: column A determines (or nearly determines) column B.
- **Linear (Pearson) correlation**: numeric variables rising/falling linearly together.
- **`pg_stats.correlation`**: alignment between a single column's value order and **physical row placement on disk**, used for access-path I/O cost estimation.
- **Multivariate MCV**: observed joint frequencies of concrete value combinations.

### 25.1. Example

`category_id=7 -> category_code='CAT-007'` is a strong functional dependency, yet `category_code` is text—there is no direct numeric Pearson correlation without defining an encoding.

### 25.2. pg_stats.correlation Is Not Extended Dependency

High `correlation` in `pg_stats` usually means rows were appended or clustered in that column's order. That is **completely unrelated** to cross-column functional dependencies.

### 25.3. Pick Statistics Based on Failure Mode, Not One Metric

If estimates break on redundant equality predicates, inspect `dependencies`; if an index scan suffers from scattered heap pages, inspect physical `correlation` and access paths; if `GROUP BY` group counts miss, inspect `ndistinct`.

## 26. Dependencies and Expressions in WHERE

Suppose a query uses:

~~~sql
SELECT *
FROM catalog
WHERE lower(category_code) = 'cat-007'
  AND category_id = 7;
~~~

Here the filter applies `lower(category_code)`, no longer a bare column equality clause.

### 26.1. Do Not Assume Base-Column Dependencies Automatically Apply

Functional dependency statistics declared on raw base columns will not necessarily apply across arbitrary function wrappers around those columns.

### 26.2. Expression Statistics on Supported Versions

Modern PostgreSQL versions support expression statistics via `CREATE STATISTICS`. Conceptual syntax:

~~~sql
CREATE STATISTICS catalog_lower_code_stats
ON (lower(category_code))
FROM catalog;
~~~

This requires a compatible version and existing table, and **differs** from declaring `(dependencies)` between two bare columns.

### 26.3. Expression Indexes Differ Too

~~~sql
CREATE INDEX catalog_lower_code_idx
ON extstats_lab.catalog (lower(category_code));
~~~

Indexes create fast physical access paths for expressions; statistics characterize distributions for planning. Choice depends on query shape and actual plan metrics.

## 27. Parameterized Queries and Generic Plans

Applications commonly bind parameters:

~~~sql
SELECT *
FROM extstats_lab.catalog
WHERE category_id = $1
  AND category_code = $2;
~~~

Depending on the driver, prepare cycle, and PostgreSQL's **custom plan** vs. **generic plan** choice, the planner may or may not see concrete parameter values to apply MCVs/selectivity optimally.

### 27.1. Why EXPLAIN with Literals Differs from Application Plans

`EXPLAIN` with hardcoded `category_id=7` and `category_code='CAT-007'` sees exact constants, whereas a cached generic plan must handle arbitrary runtime bindings.

### 27.2. Test the Actual Execution Mode

Do not declare “statistics failed” from a single literal query if production executes parameterized generic plans—nor tune solely for one rare parameter pair.

### 27.3. Diagnostic Techniques

PostgreSQL supports `PREPARE`, `EXPLAIN EXECUTE`, and `plan_cache_mode` in supported versions. Use them in test environments to compare custom vs. generic plan behavior when app plans diverge from ad-hoc SQL.

### 27.4. Do Not Force Custom Plans System-Wide for One Query

Forcing custom plans globally increases planning CPU overhead. Evaluate query patterns, parameter skew, and overall workload first.

## 28. Statistics Target, Sample Size, and Rare Distributions

Suppose a slow query filters rare combinations:

~~~sql
WHERE status = 'fraud'
  AND region = 'rare-region'
~~~

If rare combinations appear infrequently, `ANALYZE` sampling may capture too few examples for accurate estimation.

### 28.1. MCV Lists Have Finite Size

Multivariate MCV prioritizes dominant combinations; rare combinations still rely on remainder estimation logic.

### 28.2. Dependencies Capture Overall Tendencies, Not Every Exception

Strong overall dependencies with rare outliers can still misestimate uncommon filter pairs.

### 28.3. When Testing Larger Targets

Measure before and after:

- Estimated row counts.
- Frequency of poor plan choices.
- `ANALYZE` execution cost.
- Statistics storage footprint.
- Planning time.
- Representative query execution timings.

Never declare production faster simply because a dependency number in `pg_stats_ext` “looks cleaner.”

## 29. ALTER STATISTICS and DROP STATISTICS

### 29.1. Raising the Target

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS 250;

ANALYZE extstats_lab.catalog;
~~~

### 29.2. Restoring the Default Target

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS DEFAULT;

ANALYZE extstats_lab.catalog;
~~~

### 29.3. Dropping a Statistics Object

~~~sql
DROP STATISTICS extstats_lab.catalog_category_dep;
~~~

`DROP STATISTICS` removes the statistics object only—**it never deletes table rows or indexes**.

### 29.4. Migrations Should Plan Rollbacks

If creating an extended statistics object unexpectedly degrades a production plan, you can `DROP STATISTICS`, re-run `ANALYZE`, or refine the target/kinds.

Note that if multiple statistics objects exist on overlapping columns, dropping just one will not return to baseline while the others remain.

### 29.5. Be Careful Dropping Objects Needed Later

If you experiment with stats kinds earlier in a shared lab, track which objects you keep or isolate tests in separate schemas/tables. Never drop statistics casually in shared environments where active queries depend on them.

## 30. Cardinality Estimation and Execution Cost Are Separate Problems

A query can exhibit any of these behaviors:

- Accurate row estimates yet still slow due to slow disk I/O.
- Wrong row estimates yet the planner still picked the best available plan.
- Accurate estimates after `CREATE STATISTICS` yet still slow due to missing indexes.
- Accurate scan estimates yet wrong upstream `JOIN` estimates due to planner limitations.
- Optimal index present yet elevated planning time from too many candidate plans.

### 30.1. Never Benchmark Once

`EXPLAIN ANALYZE` timings fluctuate with warm/cold cache, storage load, CPU contention, autovacuum, and data churn. Run multiple trials on representative data before claiming a win.

### 30.2. Verify the Primary Goal First

When adding `dependencies` to fix a 100× filter underestimate, primary proof of success is **filter node `rows` moving close to `actual rows`**. Whether the plan switches join types is a secondary consequence.

### 30.3. Avoid Forcing Plans by Disabling Join Types Prematurely

Parameters like `enable_nestloop` are debugging switches for testing hypotheses—not global fixes to replace proper statistics, indexes, and SQL.

## 31. When Extended Statistics Will Not Help

Typical situations:

1. Queries filtering **only one column**—single-column stats already apply.
2. Columns belonging to **two different tables** when trying to fix direct cross-table join selectivity.
3. Predicates using **ranges, `LIKE`, or complex expressions** outside dependency support.
4. Contradictory filters requiring strict logical deduction rather than probabilistic scaling.
5. Rapidly changing columns whose statistics are stale.
6. Parameterized queries bound to generic plans without constant visibility.
7. Queries bottlenecked by storage I/O, network latency, or missing indexes rather than row estimates.
8. Statistics objects built on columns mismatched with actual `WHERE`/`GROUP BY` clauses.
9. Sparse rare combinations unrepresented in samples.
10. Cost settings or planner heuristics keeping the same plan despite better estimates.

### 31.1. Never Create Statistics for Every Column Pair

In a 50-column table, the number of column pairs is:

\[
\binom{50}{2} = 1{,}225
\]

Blindly creating 1,225 statistics objects bloats `ANALYZE` runtimes and catalog overhead with zero proven value.

### 31.2. Prioritize by Workload

A critical high-QPS query filtering `country_id` and `country_name` justifies a targeted `dependencies` object. Hundreds of unused column combinations do not.

## 32. Common Errors and Misconceptions

### 32.1. “Once CREATE STATISTICS finishes, the planner uses it immediately”

**False.** You must run `ANALYZE` to gather data for the new object.

### 32.2. “Extended statistics work like a composite index”

**False.** Statistics supply cardinality estimates; indexes supply physical access paths.

### 32.3. “dependencies guarantees two columns cannot contradict each other”

**False.** It is not a constraint and performs zero write-time validation.

### 32.4. “Correlated columns always imply bidirectional functional dependency”

**False.** Dependencies are often one-way: district determines province, while province does not determine district.

### 32.5. “A perfect dependency ensures contradictory WHERE filters estimate 0 rows”

**False.** Estimators are not constraint solvers and may overestimate impossible pairs.

### 32.6. “dependencies solves LIKE, range, expression, and JOIN estimates”

**False.** Clause types and cross-table join selectivity have well-defined limits.

### 32.7. “ndistinct optimizes every WHERE equality filter”

**False.** Its primary role is estimating distinct combination counts for grouping and related contexts.

### 32.8. “mcv and dependencies store the same information”

**False.** One records frequent joint combinations and frequencies; the other quantifies functional dependence degrees.

### 32.9. “Adding an index automatically fixes cardinality estimates”

**False.** Indexes alone do not teach the planner cross-column dependencies.

### 32.10. “An unchanged plan proves extended statistics failed”

**False.** Row estimates may have improved significantly while the existing access path remained optimal.

### 32.11. “ANALYZE computes exact 100% figures”

**False.** `ANALYZE` generally samples rows and produces estimates.

### 32.12. “Raising targets fixes every slow query”

**False.** It helps only when sampling granularity limits accuracy on applicable predicates.

### 32.13. “pg_stats.correlation measures correlation between two columns”

**False.** It measures alignment between one column's order and physical table placement.

### 32.14. “Extended statistics make redundant schema design clean”

**False.** Statistics never replace normalization, constraints, foreign keys, or clean data modeling.

### 32.15. “You can CREATE STATISTICS directly across columns from two tables”

**Not with standard multivariate statistics syntax.** Objects are created on a single relation and cannot model arbitrary two-table joint distributions directly.

### 32.16. “EXPLAIN ANALYZE only inspects the plan without executing”

**False.** It executes the statement—exercise extreme caution with DML.

### 32.17. “Whenever actual rows=1000 and rows=10, you must add extended statistics”

**Not necessarily.** Inspect stale stats, indexes, sampling, predicates, and real costs first.

### 32.18. “Creating statistics on everything always makes the optimizer better”

**False.** It adds `ANALYZE` and planning costs, often without practical benefit.

### 32.19. “Literal queries and generic prepared plans always pick identical plans”

**False.** Constant visibility at planning time changes selectivity estimates and plan choices.

### 32.20. “When stats go stale, good indexes always save the query”

**False.** Bad cardinality estimates can drive the planner onto poor plans even when optimal indexes exist.

## 33. Practice Exercises

### Exercise 1 — Probability Multiplication

A table has 200,000 rows. Columns A and B each have 100 uniformly distributed values. Under independence, what does the planner estimate for `A=7 AND B='X'`?

**Hint:** `200000 × 0.01 × 0.01 = 20` rows.

### Exercise 2 — Real Dependency

If `A=7` always implies `B='X'`, roughly how many rows exist in reality for Exercise 1?

**Hint:** Around 2,000 rows if A is uniformly distributed.

### Exercise 3 — Discrepancy Factor

Compute the underestimation factor across the two exercises above.

**Hint:** `2000 / 20 = 100`×.

### Exercise 4 — Picking the Right Kind

A frequent query runs:

~~~sql
WHERE category_id = 7
  AND category_code = 'CAT-007'
~~~

Which extended statistics kind should you try first?

**Answer:** `dependencies`.

### Exercise 5 — Writing CREATE STATISTICS

Write DDL creating `dependencies` between `category_id` and `category_code` on `extstats_lab.catalog`.

~~~sql
CREATE STATISTICS extstats_lab.my_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

### Exercise 6 — After CREATE

What command must run so the planner receives the new statistical data?

**Answer:** `ANALYZE extstats_lab.catalog;`.

### Exercise 7 — Checking Actual Rows

Which command displays the plan while executing the query to measure actual rows?

**Answer:** `EXPLAIN (ANALYZE, BUFFERS) SELECT ...;`.

### Exercise 8 — Contradiction

Why might `category_id=7 AND category_code='CAT-008'` still get a positive row estimate even though 0 rows exist in the lab?

**Hint:** Dependency estimators do not deduce contradictory impossible pairs like constraint solvers.

### Exercise 9 — One-Way Dependency

If `district_id -> province_id`, does `province_id -> district_id` necessarily hold?

**Answer:** No.

### Exercise 10 — ndistinct

Two columns each have 100 distinct values individually, yet only 100 valid pairs exist. A `GROUP BY` over both columns misestimates group count. Which statistics kind should you create?

**Answer:** `ndistinct`.

### Exercise 11 — Writing ndistinct

~~~sql
CREATE STATISTICS extstats_lab.my_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

### Exercise 12 — MCV

When `(region, status)` pairs have highly skewed frequencies, which statistics kind helps?

**Answer:** `mcv`.

### Exercise 13 — MCV vs. Dependency

Explain the difference between capturing “A determines B” vs. “the pair `(A=7, B='X')` occurs frequently.”

**Hint:** Functional dependence strength vs. concrete joint combination frequencies.

### Exercise 14 — Composite Index

Why doesn't `CREATE STATISTICS` automatically cut down pages read by a Seq Scan when no better access path exists?

**Hint:** It builds no index; it only refines estimates and plan selection.

### Exercise 15 — Unique Constraint

If `category_code` must always match `category_id`, is `CREATE STATISTICS` enough to enforce integrity?

**Answer:** No; proper data modeling, constraints, or write protocols are required.

### Exercise 16 — pg_stats_ext

Write a `SELECT` retrieving `statistics_name`, `attnames`, `kinds`, and `dependencies`.

**Hint:** Query `pg_stats_ext` filtered by `schemaname` and `tablename`.

### Exercise 17 — Internal Catalogs

Which two internal catalogs hold extended statistics definitions and collected data?

**Answer:** `pg_statistic_ext` and `pg_statistic_ext_data`.

### Exercise 18 — Ranges

A query filters only with `category_id BETWEEN 10 AND 20`. Can you claim `dependencies` will fix cardinality?

**Hint:** No; consider single-column context and range-clause limitations.

### Exercise 19 — JOIN

Can you guarantee extended stats automatically compute exact selectivity for `t1.a = t2.b` across two tables?

**Answer:** No; direct cross-table join selectivity support remains limited.

### Exercise 20 — Correlation

Is `pg_stats.correlation` of column A a dependency coefficient between A and B?

**Answer:** No.

### Exercise 21 — Target

If MCV retains too few pairs for a skewed distribution, what commands might you try?

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_mcv
SET STATISTICS 500;

ANALYZE extstats_lab.catalog;
~~~

### Exercise 22 — Target Cost

Why avoid setting huge statistics targets on every object?

**Hint:** Increases `ANALYZE`, storage, and planning costs without solving unrelated planner limits.

### Exercise 23 — Stale Stats

After loading 5 million rows with a new distribution, what should you inspect?

**Hint:** `ANALYZE`/autoanalyze status and updated plan estimates.

### Exercise 24 — Prepared Statements

Why can `EXPLAIN` with constants differ from a generic plan for parameterized SQL?

**Hint:** Parameter visibility at planning time differs.

### Exercise 25 — Discrepancy and Plan Shape

If estimated rows improve yet the plan remains Seq Scan, can statistics still have worked properly?

**Answer:** Yes; improved estimates do not always flip which plan wins.

### Exercise 26 — Loops

Why must you inspect `loops` when comparing `actual rows` inside a nested loop?

**Hint:** `actual rows` reports average rows per loop execution.

### Exercise 27 — DML and EXPLAIN

Should you run `EXPLAIN ANALYZE UPDATE` in production just to “check the plan”?

**Answer:** Not without strict controls; `ANALYZE` executes the `UPDATE`.

### Exercise 28 — Overly Broad Statistics Objects

Is a 20-column statistics object always better than a targeted 2-column object matching real filters?

**Hint:** No; pick only columns aligned with workload patterns and version constraints.

### Exercise 29 — DROP

Does `DROP STATISTICS` delete table rows?

**Answer:** No; it drops statistics metadata only, never table data.

### Exercise 30 — Diagnosing Root Cause

A query is slow because the network must ship 10 million rows to the client. Is `dependencies` the primary fix?

**Hint:** No; look at result size, pagination, and network transfer.

### Exercise 31 — Historical Data

Tenants change service tiers over time. Can `tenant_id -> service_tier` be treated as an absolute dependency on historical event rows?

**Hint:** Not necessarily; one tenant can have multiple tiers at different points in time.

### Exercise 32 — Two Columns from Two Tables

Can standard multivariate `CREATE STATISTICS` span `orders.country_id` and `countries.code` in one object?

**Answer:** No; `CREATE STATISTICS` syntax targets a single relation.

### Exercise 33 — Rare Distributions

If MCV omits an ultra-rare pair, can you conclude that pair does not exist in the table?

**Answer:** No; MCV does not store every combination.

### Exercise 34 — Analyzing WHERE Clauses

A query contains an equality filter on two dependent columns plus a `LIKE` clause. Should you expect `dependencies` to fix all three predicates?

**Hint:** No; verify which clauses benefit and inspect actual plans.

### Exercise 35 — Proposing a Diagnostic Workflow

A slow query estimates 20 rows yet sees 5,000 actual rows on a base scan filter. Propose an investigation sequence.

**Hint:** Check stale stats, predicates/casts, column relationships, appropriate `CREATE STATISTICS`, `ANALYZE`, re-run `EXPLAIN`, then address indexes/joins/costs if needed.

## 34. Quick Reference Table

| Question | Answer |
|---|---|
| What are extended statistics for? | Improve estimates for multi-column/expression distributions |
| Creation command | `CREATE STATISTICS ... ON ... FROM ...` |
| Required follow-up step | `ANALYZE table` |
| Equality predicates treated independently | Try `dependencies` |
| Multi-column GROUP BY group counts wrong | Try `ndistinct` |
| Heavily skewed joint combinations | Try `mcv` |
| Can dependencies be one-way? | Yes |
| Does it enforce constraints? | No |
| Does it create an index? | No |
| Does it fix every JOIN selectivity? | No |
| Does it deduce `A=7 AND B='wrong'` is 0? | Not guaranteed |
| Does it solve every LIKE/range predicate? | Not guaranteed |
| View defined objects | `pg_stats_ext`, `pg_statistic_ext` |
| View collected stats data | `pg_stats_ext` with proper privileges |
| Definition catalog | `pg_statistic_ext` |
| Data payload catalog | `pg_statistic_ext_data` |
| Adjust target | `ALTER STATISTICS ... SET STATISTICS ...` |
| Remove object | `DROP STATISTICS ...` |
| Measure before/after plans | `EXPLAIN (ANALYZE, BUFFERS)` |
| Careful with EXPLAIN ANALYZE DML? | Yes—it executes the command |
| Stale statistics? | Run `ANALYZE` / tune autoanalyze |
| Tightly dependent column pair | `dependencies` often helps equalities |
| Is a bigger target always better? | No |
| Do stats and indexes complement each other? | Yes |
| Is `pg_stats.correlation` cross-column dependency? | No |
| Can generic prepared plans differ from literals? | Yes |
| Unchanged plan after stats means failure? | No—check estimated rows |
| Single object spanning two tables? | Not via standard `CREATE STATISTICS` |
| Final tuning basis | `EXPLAIN`, real workload, controlled benchmarks |

---

## Conclusion

Extended statistics let PostgreSQL understand multi-column relationships that **per-column statistics alone** cannot capture. When two `WHERE` predicates convey essentially the same attribute, assuming independence causes the planner to over-multiply selectivities and underestimate row counts by orders of magnitude. **`dependencies`** targets those cases directly, especially for constant equality filters on strongly dependent columns.

Still, **`dependencies` is not a silver bullet for every cardinality problem**: it enforces no constraints, builds no indexes, cannot prove impossible predicate combinations return zero, and faces clear limits on ranges, `LIKE`, expressions, and joins. When `GROUP BY` group estimates fail, inspect **`ndistinct`**; when skewed value pairs dominate, inspect **`mcv`**.

The reliable discipline is to **measure estimated vs. actual rows**, find where estimates diverge in the plan, verify column relationships in real data, create the targeted statistics kind, **run `ANALYZE`**, and re-verify. A `CREATE STATISTICS` object pays off only when it matches real query patterns—more statistics objects do not automatically translate into faster queries.

Understanding how functional dependencies interact with the planner exposes the root causes behind suboptimal join, scan, and aggregate plans—replacing blind timeout increases or index hints with **more accurate data modeling for the optimizer** rather than throwing hardware at the problem.
