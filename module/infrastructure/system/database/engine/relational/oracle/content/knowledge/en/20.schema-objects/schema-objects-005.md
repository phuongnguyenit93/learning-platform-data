# Query Rewrite and Compatibility, Statistics, and Feature Conditions in Oracle Database

Oracle Database can transform a SQL statement to find a more efficient execution strategy while preserving the same result under SQL semantics. This process is often referred to as **query transformation** or **query rewrite**. A particularly important case is **materialized view query rewrite**: the optimizer can replace a query against source tables by reading precomputed data in a materialized view (MV).

Rewrite eligibility does not depend merely on two SQL statements looking similar. Oracle must prove the transformation is equivalent given current data conditions and privileges. Factors such as primary/foreign keys, NOT NULL constraints, materialized view status, constraint trust levels, aggregate types, functions used, optimizer statistics, and feature compatibility versions can all influence rewrite.

A good execution plan also requires sufficiently accurate statistics. The optimizer relies on row counts, selectivity, histograms, index statistics, and system statistics to estimate cost. If statistics are stale or lack column correlation details, the optimizer can choose a suboptimal join order, join method, or fail to select an eligible materialized view.

This lesson distinguishes concepts that are often conflated:

- **Query transformation:** the optimizer restructures the query internally, such as view merging or subquery unnesting.
- **Materialized view query rewrite:** the optimizer substitutes a query with precomputed data in an MV when eligible.
- **Optimizer statistics:** metadata describing tables, columns, indexes, and the system to estimate cardinality/cost.
- **Compatibility and optimizer features:** database version compatibility settings and optimizer behavior baselines; they are not synonymous.

## 1. What Is Query Rewrite?

### 1.1. The Optimizer's Goal

A SQL statement describes **the desired result**, not necessarily the exact order of physical operations. The Oracle optimizer parses the statement, evaluates candidate alternatives, and chooses an execution plan based on estimated cost.

Example:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = 'COMPLETED'
);
```

The optimizer can transform the subquery into a semi-join if the transformation preserves semantics. The SQL text remains what the user submitted, but the execution plan may no longer retain the original subquery structure.

### 1.2. Query Transformation vs. Materialized View Rewrite

| Concept | Description | Examples |
|---|---|---|
| Query transformation | Changes internal representation of the query | View merging, predicate pushing, subquery unnesting |
| Materialized view rewrite | Uses pre-stored MV results to satisfy the query | Reading a monthly summary table instead of scanning the full fact table |

Query transformation is an internal optimizer activity during SQL optimization. Materialized view rewrite additionally depends on a specific schema object having been created and maintained.

### 1.3. Why Can Rewrite Be Faster?

Suppose the SALES_FACT table holds hundreds of millions of transactions. A recurring report requests total revenue by region and product. Scanning the fact table, joining dimensions, and grouping millions of records on every run can be expensive.

A materialized view pre-stores the aggregation:

```sql
SELECT region_id,
       product_id,
       SUM(amount) AS total_amount
FROM sales_fact
GROUP BY region_id, product_id;
```

If a query requests results compatible with that aggregation level, Oracle can read far fewer rows from the MV. The benefit depends on MV size, data freshness, indexes, partitioning, statistics, and refresh overhead.

## 2. Common Types of Query Transformation

### 2.1. View Merging

View merging is a transformation where the optimizer folds the contents of an inline view into the outer query to broaden the search space for join orders and predicates.

```sql
SELECT v.customer_id,
       v.total_amount
FROM (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'COMPLETED'
    GROUP BY customer_id
) v
WHERE v.total_amount > 10000000;
```

The optimizer evaluates whether the view can be merged. Aggregates, DISTINCT, analytic functions, row limiting, and other constructs can restrict merging because they establish semantic boundaries that must be preserved. Not every inline view is merged.

### 2.2. Predicate Pushing

Predicate pushing attempts to move filter conditions closer to the data source to reduce intermediate row counts:

```sql
SELECT *
FROM (
    SELECT order_id, customer_id, status
    FROM orders
) v
WHERE v.status = 'COMPLETED';
```

The status condition can be applied directly to the orders table. In complex views, predicate pushdown may be restricted by outer joins, aggregates, or expressions that alter semantics.

### 2.3. Subquery Unnesting

The optimizer can convert certain subqueries into joins:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'COMPLETED'
);
```

A semi-join can execute an existence check far more efficiently than naive nested subquery evaluation. Subqueries containing aggregates, ROWNUM, set operators, or special constructs may not be unnested automatically.

### 2.4. Join Elimination

In certain cases, the optimizer can eliminate a join if it does not affect the query result. For example, a child/parent table is joined only to verify a relationship and none of its columns are used; appropriate constraints can prove the relationship holds.

PK/FK constraints, uniqueness, NOT NULL, and constraint states (ENABLED/VALIDATED/RELY) can influence this proof. Never declare false constraints just to force join elimination: query results can become wrong if actual data violates those assumptions.

### 2.5. OR Expansion

OR conditions are sometimes transformed into separate query branches, often resembling UNION ALL:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id
   OR status = 'URGENT';
```

The optimizer can split branches to use appropriate indexes/access paths for each predicate. The transformation must properly handle rows satisfying both branches to avoid duplicate results.

### 2.6. Star Transformation

In a star schema data warehouse, a fact table links to multiple dimensions. Star transformation can filter fact rows using bitmap indexes and dimension predicates in suitable configurations.

This capability depends on schema structure, index types, selectivity, statistics, and optimizer settings. Not every star schema uses star transformation automatically.

### 2.7. Materialized View Query Rewrite

This is the focus of this lesson: a query against source tables can be satisfied using a precomputed MV if Oracle proves the MV contains sufficient information and yields equivalent results.

For example, the query:

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact
WHERE product_id = 10
GROUP BY region_id;
```

can be rewritten to read an MV already aggregated by region and product and then roll up further by region. The MV must store the necessary aggregates and required grouping/filtering columns.

## 3. Materialized View Query Rewrite

### 3.1. Materialized Views Differ from Standard Views

A standard view stores a SELECT definition; when queried, Oracle typically accesses the underlying objects per that definition. A materialized view stores the query results as of refresh time.

| Characteristic | View | Materialized View |
|---|---|---|
| Stores separate result data | Does not store a result copy | Stores results |
| Requires refresh | No | Yes |
| Can have indexes on results | Not directly like a table | Can create indexes |
| Data can be stale | Reflects source data at query time | Can become stale between refreshes |
| Used for query rewrite | Not an MV rewrite target | Can be used by optimizer if eligible |

MVs consume storage and refresh overhead. Balance report response time against data freshness and maintenance cost.

### 3.2. Create Sample Fact Table

Run in a lab schema:

```sql
CREATE TABLE sales_fact_demo (
    sale_id     NUMBER(12) CONSTRAINT pk_sales_fact_demo PRIMARY KEY,
    sale_date   DATE NOT NULL,
    region_id   NUMBER(6) NOT NULL,
    product_id  NUMBER(8) NOT NULL,
    amount      NUMBER(14, 2) NOT NULL,
    CONSTRAINT ck_sales_fact_demo_amount CHECK (amount >= 0)
);

INSERT INTO sales_fact_demo VALUES
    (1, DATE '2026-01-05', 10, 100, 1200);
INSERT INTO sales_fact_demo VALUES
    (2, DATE '2026-01-08', 10, 100, 800);
INSERT INTO sales_fact_demo VALUES
    (3, DATE '2026-01-10', 20, 100, 1500);
INSERT INTO sales_fact_demo VALUES
    (4, DATE '2026-02-03', 10, 200, 2000);
INSERT INTO sales_fact_demo VALUES
    (5, DATE '2026-02-12', 20, 100, 700);
COMMIT;
```

### 3.3. Create an Aggregate Materialized View

```sql
CREATE MATERIALIZED VIEW sales_region_product_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
ENABLE QUERY REWRITE
AS
SELECT region_id,
       product_id,
       SUM(amount) AS total_amount,
       COUNT(*) AS sale_count
FROM sales_fact_demo
GROUP BY region_id, product_id;
```

The MV is populated immediately (BUILD IMMEDIATE), refreshed using COMPLETE on demand, and marked to allow query rewrite. Other refresh options may fit production systems; choose based on source change patterns and operational costs.

### 3.4. Rewritable Source Query

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;
```

The MV contains aggregated data by region and product. Because the query filters for product 100 and sums amount by region, Oracle can read matching rows from the MV and aggregate them. Exact rewrite eligibility is decided by the optimizer and MV structure.

### 3.5. Enable Query Rewrite in the Session

```sql
ALTER SESSION SET query_rewrite_enabled = TRUE;
ALTER SESSION SET query_rewrite_integrity = ENFORCED;
```

QUERY_REWRITE_ENABLED allows the optimizer to consider query rewrite. TRUE enables rewrite when the optimizer deems it beneficial and eligible. FALSE disables it; FORCE instructs the optimizer to favor rewrite where possible, though it cannot make a non-equivalent rewrite valid.

### 3.6. Inspect the Execution Plan

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

If rewrite is selected, the plan may show access to the materialized view instead of the fact table. Operation names and plan shapes vary across releases, statistics, hints, and optimizer environments; do not look for one fixed operation string alone to draw conclusions.

To observe the actual cursor plan:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Privileges to read cursors and execution statistics may need to be granted by a DBA. EXPLAIN PLAN shows an estimated plan; DISPLAY_CURSOR shows the actual executed plan and runtime metrics if gathered.

## 4. Conditions Required for a Materialized View to Be Used in Rewrite

### 4.1. Query Rewrite Must Be Enabled

Check configuration:

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'query_rewrite_enabled',
    'query_rewrite_integrity',
    'optimizer_features_enable',
    'compatible'
)
ORDER BY name;
```

Accessing V$ views requires appropriate privileges. If unavailable, ask a DBA for configuration values.

### 4.2. MV Must Enable Query Rewrite

The MV is created or altered with ENABLE QUERY REWRITE. Check metadata:

```sql
SELECT mview_name,
       rewrite_enabled,
       refresh_mode,
       refresh_method,
       staleness,
       compile_state
FROM user_mviews
WHERE mview_name = 'SALES_REGION_PRODUCT_MV';
```

Metadata column names can differ across views/versions; consult dictionary views for your release. REWRITE_ENABLED indicates whether the MV is enabled for rewrite, while STALENESS helps assess data freshness.

### 4.3. MV Must Contain Sufficient Information

Oracle must be able to derive the query result from MV data. For example:

- If the query filters on product_id, the MV must store product_id or a structure from which that condition can be derived.
- If the query needs total amount, the MV must store SUM(amount) or aggregates sufficient to recompute it.
- If the query groups by region, the MV must retain region_id at an appropriate grain.
- If the query joins dimensions, the MV must contain data or relationships sufficient to reconstruct the result.

An MV aggregated by (region_id, product_id) can support a query aggregating by region after filtering product. An MV aggregated only by region cannot return individual product results if product details were aggregated away.

### 4.4. Query and MV Must Be Semantically Equivalent

The optimizer must ensure results preserve:

- Values and datatypes.
- Row counts and uniqueness.
- NULL semantics.
- Filter and join conditions.
- Aggregate, grouping, and duplicate semantics.
- Expressions that may vary by session or time.

Two visually similar SQL statements are not necessarily equivalent. For instance, moving a predicate around an outer join can alter retained rows; replacing UNION ALL with UNION removes duplicates; aggregating at a different grain may prevent reconstructing original results.

### 4.5. Freshness and Refresh State

With QUERY_REWRITE_INTEGRITY = ENFORCED, Oracle uses an MV only when it can guarantee that the data and relationships used are valid under that integrity level. A stale MV may not be used.

Refresh the MV:

```sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_REGION_PRODUCT_MV',
        method => 'C'
    );
END;
/
```

C requests a complete refresh in this example. Fast refresh can be chosen if the MV and source qualify; not every MV supports fast refresh.

### 4.6. Materialized View Logs and Query Rewrite Are Not the Same Requirement

A materialized view log is typically required for fast refresh of source table changes. It is not a universal prerequisite for query rewrite. An MV refreshed via COMPLETE ON DEMAND can still be a rewrite candidate when freshness/integrity conditions are met.

Distinguish:

- **Query rewrite:** uses data already stored in the MV to satisfy a SELECT.
- **Fast refresh:** updates the MV by applying incremental changes from the source.
- **Complete refresh:** recomputes the entire MV result.

Refresh strategy and query rewrite strategy are related, yet distinct design decisions.

## 5. QUERY_REWRITE_INTEGRITY and Trust Levels

### 5.1. ENFORCED

ENFORCED requires Oracle to rely only on enforced relationships and MV data meeting appropriate freshness rules. This is the conservative choice for business systems requiring consistent results.

### 5.2. TRUSTED

TRUSTED allows the optimizer to trust certain declared relationships/metadata that the database does not necessarily enforce as strictly as ENFORCED, such as dimension metadata or constraints marked RELY where applicable. This can broaden rewrite applicability, but is only safe when data truly obeys those declarations.

Never mark a constraint RELY just to force rewrite if actual data violates the constraint. The optimizer may rely on that assumption and produce incorrect results.

### 5.3. STALE_TOLERATED

STALE_TOLERATED allows using certain stale MVs according to Oracle policy. Results can reflect data from the previous refresh rather than the latest source table state.

Consider this only when the business accepts data staleness, such as summary reports not requiring real-time figures. Never use it for account balances, inventory, or decisions needing current data without explicit business approval.

### 5.4. Comparison Table

| Integrity | Trust Level | Risks to Understand |
|---|---|---|
| ENFORCED | Relies on enforced constraints and sufficiently fresh MVs | May miss rewrites if MV is stale or relationships are unverified |
| TRUSTED | Additionally trusts declared metadata/relationships | Data violating declared assumptions can cause wrong rewrite results |
| STALE_TOLERATED | Permits certain stale MV results | Can return older data than source tables |

Default values and specific capabilities can differ by version/configuration. Inspect actual environment parameters rather than assuming defaults.

## 6. Constraints and Metadata Affecting Rewrite

### 6.1. Primary Key and Unique Constraints

PK/UNIQUE constraints provide uniqueness guarantees. The optimizer can use this metadata to infer cardinality, eliminate redundant joins, or prove transformation equivalence.

Example:

```sql
CREATE TABLE region_dim_demo (
    region_id   NUMBER(6)
        CONSTRAINT pk_region_dim_demo PRIMARY KEY,
    region_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE sales_fact_fk_demo (
    sale_id   NUMBER(12)
        CONSTRAINT pk_sales_fact_fk_demo PRIMARY KEY,
    region_id NUMBER(6) NOT NULL,
    amount    NUMBER(14, 2) NOT NULL,
    CONSTRAINT fk_sales_region_demo
        FOREIGN KEY (region_id)
        REFERENCES region_dim_demo(region_id)
);
```

### 6.2. ENABLED, VALIDATED, and RELY

Constraints have states/attributes affecting how Oracle enforces and trusts them:

- ENABLE: the database enforces the constraint on incoming changes per constraint state.
- VALIDATE: existing data has been verified against the constraint.
- NOVALIDATE: existing historical data is not fully verified, even if new DML may still be checked depending on state.
- RELY: allows the optimizer to trust the constraint in appropriate contexts, especially when query rewrite integrity is TRUSTED.

ENABLE NOVALIDATE does not mean every existing row is valid. When relying on constraints to enable rewrite, understand legacy data and data-loading paths.

### 6.3. NOT NULL and NULL Semantics

NOT NULL helps the optimizer prove certain transformations are safe. If a column is nullable, joins, filters, and aggregates can behave differently than when a column is guaranteed non-null.

For example, COUNT(*) and COUNT(column) are not equivalent when column can be NULL:

```sql
SELECT region_id,
       COUNT(*) AS all_rows,
       COUNT(product_id) AS rows_with_product
FROM sales_fact_demo
GROUP BY region_id;
```

An MV storing COUNT(*) cannot automatically satisfy every COUNT(product_id) query. The MV must store aggregates sufficient to reconstruct accurate results, including NULL handling.

### 6.4. Dimensions and Hierarchies

In data warehouses, dimension metadata can describe hierarchies and functional dependencies such as city → state → country. Query rewrite can leverage dimension metadata to answer queries at different aggregation levels, provided relationships are accurate and declared in the proper state.

A dimension is not simply a table named *_DIM. Hierarchies, levels, and attribute relationships must be defined with appropriate Oracle dimension metadata, and actual data must strictly conform.

## 7. Factors That Prevent Query Rewrite

A query may fail to rewrite even when an MV exists:

1. QUERY_REWRITE_ENABLED = FALSE.
2. MV lacks ENABLE QUERY REWRITE.
3. MV is stale while integrity requires fresh data.
4. MV lacks required filter columns, grouping columns, or aggregates.
5. MV granularity is insufficient to reconstruct the result.
6. Join paths or constraints are insufficient to prove equivalence.
7. NULL, outer join, duplicate, or aggregate semantics differ.
8. Expressions use non-deterministic or session/time-dependent functions.
9. MV is invalid, uncompiled, or refresh failed.
10. The optimizer estimates accessing source tables is cheaper than the MV.
11. Hints or parameters restrict transformation.
12. The database version lacks support for the required feature/syntax.

Not every non-rewrite case is an error. The optimizer may deliberately choose a different plan due to lower estimated cost.

### 7.1. Deterministic Functions and Environment-Dependent Expressions

MVs or queries may invoke functions. If a function depends on time, session state, NLS settings, package state, or external database data, its output can change even when source rows remain unchanged.

Marking a PL/SQL function DETERMINISTIC is a developer promise; Oracle does not prove that the function always returns the same output for identical inputs. Do not mark a function deterministic if it reads other tables or depends on session state just to enable rewrite.

### 7.2. ROWNUM, Row Limiting, and Analytic Functions

Constructs such as ROWNUM, FETCH FIRST/OFFSET, analytic functions, hierarchical queries, or set operators carry specific ordering/grouping semantics. They can restrict transformations or force the optimizer to preserve query block boundaries.

When rewrite does not occur, inspect the specific SQL structure and diagnostic messages from explain tools; never drop predicates or alter join order merely to force a plan without proving semantic equivalence.

## 8. Explaining Why Rewrite Did Not Occur

### 8.1. DBMS_MVIEW.EXPLAIN_REWRITE

Oracle provides DBMS_MVIEW.EXPLAIN_REWRITE to analyze whether a query can be rewritten using a specific MV. Where needed, DBAs typically create the output table using the utlxrw.sql admin script in Oracle Home; the default table name is usually REWRITE_TABLE.

Example:

```sql
BEGIN
    DBMS_MVIEW.EXPLAIN_REWRITE(
        query => q'[
            SELECT region_id, SUM(amount)
            FROM sales_fact_demo
            WHERE product_id = 100
            GROUP BY region_id
        ]',
        mv => 'SALES_REGION_PRODUCT_MV',
        statement_id => 'SALES_REWRITE_TEST'
    );
END;
/

SELECT statement_id,
       message
FROM rewrite_table
WHERE statement_id = 'SALES_REWRITE_TEST'
ORDER BY sequence;
```

EXPLAIN_REWRITE provides details on rewrite feasibility and reasons per API/version. Verify exact MV name, schema, privileges, and output table structure for your release.

### 8.2. DBMS_MVIEW.EXPLAIN_MVIEW

EXPLAIN_MVIEW evaluates the refresh and rewrite capabilities of a materialized view. The capability table is typically created with Oracle's utlxmv.sql script:

```sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW(
        mv => 'SALES_REGION_PRODUCT_MV'
    );
END;
/

SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
```

Output indicates whether the MV supports capabilities such as rewrite, fast refresh, or specific query patterns. Check capability table column names against your version's script.

### 8.3. DBMS_XPLAN and Execution Plans

Use EXPLAIN PLAN to inspect the estimated plan:

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount)
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

When an actual plan is needed, execute the statement with statistics gathering enabled and inspect the cursor:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount)
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +OUTLINE +PREDICATE'
    )
);
```

Privileges to read cursors and execution statistics may require DBA grants. Compare estimated rows against actual rows. Large discrepancies often point to missing statistics, skew, correlated columns, or poor predicate estimates.

## 9. What Are Optimizer Statistics?

### 9.1. Cardinality and Selectivity

The optimizer estimates how many rows each query step returns:

- **Cardinality:** expected number of rows produced by a row source.
- **Selectivity:** fraction of rows matching a filter condition.
- **Cost:** a relative cost model used to compare plans, not actual elapsed seconds.

For example, in a 1,000,000-row table, if status = 'CLOSED' is estimated at 10% selectivity, estimated cardinality is 100,000 rows. If actual matching rows are 100 or 900,000, the optimizer may pick an unsuitable access path or join method.

### 9.2. Types of Statistics

| Type | Information | Impact |
|---|---|---|
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Estimates table size and I/O |
| Column statistics | NDV, NULL count, min/max | Estimates selectivity |
| Histograms | Non-uniform value distributions | Improves estimates for skewed data |
| Index statistics | Leaf blocks, clustering factor, distinct keys | Estimates index access cost |
| System statistics | CPU and I/O characteristics | Models CPU/I/O cost |
| Extended statistics | Multi-column correlations or expressions | Improves cardinality when columns are correlated |

Statistics are not business data; they are descriptive metadata for optimization. They can be stale, missing, or unrepresentative of current workloads.

## 10. Gathering and Inspecting Statistics with DBMS_STATS

### 10.1. Gathering Table and Index Statistics

Example:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_FACT_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

AUTO_SAMPLE_SIZE lets Oracle pick an appropriate sample size. CASCADE => TRUE gathers statistics on associated indexes per package policy. SIZE AUTO allows Oracle to create histograms based on workload/column usage and configuration.

After creating an MV, also gather statistics for the MV:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

### 10.2. Checking Statistics Status

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN (
    'SALES_FACT_DEMO',
    'SALES_REGION_PRODUCT_MV'
)
ORDER BY table_name;
```

Displayed columns depend on dictionary views and release. NUM_ROWS is an estimate as of the most recent gather, not always a real-time row count.

### 10.3. Inspecting Column Statistics

```sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'SALES_FACT_DEMO'
ORDER BY column_name;
```

NUM_DISTINCT estimates distinct values; NUM_NULLS describes NULLs; histograms capture distribution skew when present. Do not interpret DENSITY as an exact probability for every predicate when a histogram exists.

### 10.4. Histograms and Skewed Data

Suppose 90% of orders have status COMPLETED, 9% PENDING, and 1% CANCELLED. If the optimizer assumes uniform distribution, estimates can be wrong for rare or dominant statuses.

Histograms help capture skew. However, histograms can also make a SQL statement with bind variables bind-sensitive or spawn multiple child cursors depending on bind values. Evaluate plans against real workloads rather than enabling histograms mechanically on every column.

### 10.5. Extended Statistics for Column Correlation

Suppose COUNTRY_CODE and POSTAL_REGION are strongly correlated. Independent single-column estimates can be inaccurate when filtering on both together:

```sql
WHERE country_code = 'VN'
  AND postal_region = 'HCM'
```

You can create column group statistics:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMER_DEMO',
           extension => '(COUNTRY_CODE, POSTAL_REGION)'
       )
FROM dual;
```

Then gather statistics on the table. Extended stats do not create indexes or replace constraints; they supply correlation information to the optimizer.

### 10.6. Expression Statistics

If queries frequently filter on expressions, expression statistics can improve cardinality estimates:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'ORDERS',
           extension => '(TRUNC(ORDER_DATE))'
       )
FROM dual;
```

These are statistics for the expression; they do not automatically create a function-based index. If an expression-based access path is needed, evaluate an index separately and verify usage conditions.

### 10.7. Incremental Statistics for Partitioned Tables

On large partitioned tables, re-gathering full statistics after every load can be expensive. Incremental statistics manage partition/global statistics incrementally when configured appropriately:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_FACT',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

This is an example setting; evaluate partition policy, synopses, release, and gather schedules. Do not enable it across all tables without measuring costs and benefits.

## 11. Statistics, Dynamic Sampling, and Feedback

### 11.1. Dynamic Statistics

When statistics are missing or insufficient for estimation, dynamic statistics (formerly known as dynamic sampling) can sample data at parse time to improve estimates. It supplements stored statistics rather than replacing a statistics-gathering strategy.

Sampling levels and behavior depend on version, parameters, query complexity, and optimizer decisions. Dynamic statistics can increase parse overhead; do not raise it system-wide merely to fix one query without inspecting the plan.

### 11.2. Statistics Feedback and Adaptive Behavior

Oracle can compare estimates with actual runtime metrics and apply feedback/adaptive mechanisms to improve subsequent executions where appropriate. Specific behavior varies by release, patch level, and optimizer parameters.

Feedback does not guarantee every query gets fixed immediately or retains a good plan forever. Plans can change after data changes, bind shifts, or statistics gathering.

### 11.3. Pending Statistics

Some environments gather statistics in pending mode to test plans before publishing them to all sessions:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO'
    );
END;
/
```

Using pending stats requires session/test setup and an appropriate publish workflow. When PUBLISH=FALSE, new statistics do not automatically become live system-wide. Record original preferences and restore them per policy after testing.

## 12. Compatibility and Optimizer Feature Controls

### 12.1. COMPATIBLE

COMPATIBLE is an initialization parameter controlling database compatibility with corresponding features and internal formats. It governs feature availability and on-disk/internal formats, and carries major implications for database upgrades and downgrades.

Do not treat COMPATIBLE as a toggle for choosing execution plans. Changing this parameter requires DBA governance, release checks, backups, and recovery planning. In many cases, once COMPATIBLE is raised, it cannot simply be lowered like a session parameter.

### 12.2. OPTIMIZER_FEATURES_ENABLE

OPTIMIZER_FEATURES_ENABLE selects an optimizer behavior baseline corresponding to a release:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'optimizer_features_enable';
```

It can be set at the session level for testing using a supported version value:

```sql
ALTER SESSION SET optimizer_features_enable = '19.1.0';
```

The illustrative version string must be replaced with a value supported by the installed release. This parameter does not turn the database into an older release or disable all newer SQL features; it primarily controls optimizer behavior according to the specified baseline.

### 12.3. COMPATIBLE vs. OPTIMIZER_FEATURES_ENABLE

| Parameter | Scope | Purpose |
|---|---|---|
| COMPATIBLE | Database-level, managed via init parameter | Database feature/format compatibility level |
| OPTIMIZER_FEATURES_ENABLE | Can be set at session/system level per scope | Selects optimizer behavior baseline |
| QUERY_REWRITE_ENABLED | Optimizer/query rewrite | Enables or disables rewrite |
| QUERY_REWRITE_INTEGRITY | Query rewrite integrity | Defines trust/freshness level for rewrite |
| STATISTICS_LEVEL | Statistics/diagnostics collection | Controls statistics and advisor collection level |

Never change COMPATIBLE to work around a slow plan. If you suspect an optimizer regression after an upgrade, inspect plan history, SQL Plan Management, and test optimizer baselines in a controlled session first.

### 12.4. Other Related Parameters

Commonly relevant settings include:

- OPTIMIZER_MODE: optimization goal such as ALL_ROWS or FIRST_ROWS_n.
- CURSOR_SHARING: policy replacing literals with binds in some cases; does not replace proper bind usage in application code.
- OPTIMIZER_DYNAMIC_SAMPLING: dynamic statistics level per release.
- STATISTICS_LEVEL: level of statistics and diagnostic collection.
- QUERY_REWRITE_ENABLED: enable/disable/force rewrite.
- QUERY_REWRITE_INTEGRITY: integrity level for query rewrite.

Never change multiple parameters simultaneously. Record initial values, scope of impact, rationale, rollback plan, and before/after measurements.

## 13. Database Version and SQL Features

### 13.1. SQL Syntax and Optimizer Behavior Are Two Different Layers

A SQL statement may:

1. Fail to parse because syntax/features are absent in the release.
2. Parse, yet the optimizer does not apply a transformation.
3. Receive transformations, yet the final plan is not faster.

OPTIMIZER_FEATURES_ENABLE does not add SQL syntax from a newer release to an older database. Nor does COMPATIBLE replace verifying release support for syntax/APIs.

### 13.2. Checking the Database Version

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Or:

```sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Access to dictionary views depends on the environment. When authoring deployment scripts, document the minimum required release and verify before running new DDL/APIs.

### 13.3. Patch Level and Release Updates

Two databases on the same major release can still differ in patch level and behavior due to bug fixes or optimizer fixes. When investigating plan regressions:

- Record the full version and Release Update (RU).
- Record COMPATIBLE and optimizer parameters.
- Compare SQL text, bind metadata, schemas, and statistics.
- Inspect SQL plan history/baselines.
- Test in an equivalent environment before applying changes to production.

Never conclude "Oracle 19c always picks plan X" from a single system with its own patches, statistics, and data.

## 14. SQL Plan Management and Plan Stability

Query rewrite is an optimizer selection capability; SQL Plan Management (SPM) is a mechanism for managing and controlling accepted execution plans. The two can coexist, but they are not synonymous.

### 14.1. SQL Plan Baselines

SQL plan baselines help constrain which plans the optimizer accepts for a SQL statement. Across upgrades or statistics changes, baselines can reduce plan regression risk when managed properly.

Do not create baselines for every query indiscriminately. Stale baselines can prevent the optimizer from adopting better plans if they are not evolved and maintained.

### 14.2. Comparing Before and After Plans

Collect:

- SQL ID and child cursor.
- Plan hash value.
- Estimated rows and actual rows.
- Buffer gets, physical reads, CPU, elapsed time.
- Bind values/peeking context where permitted.
- Statistics timestamps and optimizer environment.

If a plan changes after gathering stats, check whether estimates improved and whether query rewrite was chosen differently. Never compare plan hashes alone while ignoring row counts and workload metrics.

### 14.3. Hints

Hints such as REWRITE, NO_REWRITE, MERGE, NO_MERGE, PUSH_PRED, NO_PUSH_PRED, UNNEST, or NO_UNNEST can influence specific optimizer choices in supported contexts.

Hints are scoped control/diagnostic tools, not guarantees that every release will use the exact desired plan. Invalid or inapplicable hints can be ignored. Prioritize fixing statistics, schemas, SQL shape, and root causes before locking plans with hints.

## 15. Optimizing Statistics for Materialized Views

### 15.1. Gather Stats for Both Source and MV

An MV is a stored result object; the optimizer needs its row count, blocks, column distributions, and index stats:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        cascade => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

If an MV refresh alters row counts significantly, update MV statistics on an appropriate schedule. Do not re-gather immediately after every minor refresh if the overhead outweighs the benefit.

### 15.2. Indexes on MVs

If queries commonly filter by product and group by region, evaluate an index:

```sql
CREATE INDEX ix_sales_mv_product_region
ON sales_region_product_mv(product_id, region_id);
```

Base index column order on predicates, selectivity, and actual queries. Indexes add refresh/maintenance overhead and storage. The optimizer may still choose a full MV scan if most rows must be read.

### 15.3. Partitioning and Partition Change Tracking

For very large fact tables/MVs, partitioning by time or dimension can aid partition pruning and refresh management. Partition Change Tracking (PCT) can support incremental refresh/rewrite in eligible configurations.

PCT does not work automatically just because a table is partitioned. Requirements around partition keys, MV definitions, constraints, and refresh capabilities must be met. Use DBMS_MVIEW.EXPLAIN_MVIEW to verify instead of assuming.

## 16. Real-World Scenarios and Diagnostic Workflow

### 16.1. MV Exists, Yet Queries Still Read Source Tables

Check in order:

1. Does the MV have ENABLE QUERY REWRITE?
2. Is QUERY_REWRITE_ENABLED turned on?
3. Is the MV fresh and valid?
4. Does QUERY_REWRITE_INTEGRITY permit using it?
5. Does the MV contain sufficient columns, grouping keys, and aggregates?
6. Are constraints/dimensions sufficient to prove equivalence?
7. What reason does EXPLAIN_REWRITE report?
8. Does the optimizer estimate reading source tables is cheaper?

### 16.2. Rewrite Occurs, Yet Query Runs Slower

MVs are not automatically faster in every scenario. Possible causes:

- MV is too large and lacks appropriate indexes.
- MV statistics are stale.
- The query needs only a tiny slice of the fact table and a source index is more efficient.
- Refreshes introduce overhead or contention.
- Subsequent joins/grouping on top of the MV remain expensive.

Compare actual plans, actual rows, buffer gets, and elapsed times on representative workloads. If the optimizer rewrites to a worse plan, improve the MV/indexes/stats or consider SQL plan control backed by evidence.

### 16.3. Plan Changes After Upgrade

Inspect:

- OPTIMIZER_FEATURES_ENABLE and optimizer environment.
- Whether statistics were re-gathered or changed.
- Bind peeking and child cursors.
- New or altered query transformations.
- Whether SQL Plan Baselines are applied/evolved.
- Patch level and Release Update.

Never downgrade COMPATIBLE just to revert to an old plan. Test optimizer baselines at the session level or use SPM per governance processes.

### 16.4. Report Results Appear Stale

If an MV is used under an integrity setting that allows stale data, reports may omit recent transactions. Inspect:

```sql
SELECT mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
WHERE mview_name = 'SALES_REGION_PRODUCT_MV';
```

Verify metadata column names for your release. Review the refresh schedule and MV status before changing integrity settings. Never switch to STALE_TOLERATED just to trigger query rewrite if users expect real-time data.

## 17. Controlled Workflow for Deploying Query Rewrite

A sound workflow for reporting systems:

1. **Measure baseline:** capture SQL, plan, elapsed time, buffer gets, actual rows, and execution frequency.
2. **Define grain:** specify detail granularity of the fact table and report outputs.
3. **Design MV:** store only truly needed keys, aggregates, and expressions.
4. **Check capability:** run EXPLAIN_MVIEW/EXPLAIN_REWRITE.
5. **Configure refresh:** select COMPLETE/FAST and ON DEMAND/ON COMMIT based on freshness needs and cost.
6. **Test rewrite in non-prod:** use appropriate integrity; never artificially relax constraints.
7. **Gather statistics:** for source tables, MVs, and indexes.
8. **Verify plans:** confirm the optimizer rewrites and the actual plan improves performance.
9. **Compare results:** run original and rewritten queries on test data, checking all rows/NULLs/duplicates.
10. **Monitor production:** track refresh lag, MV staleness, plans, storage, and workload impact.

## 18. Comprehensive Lab Exercise

Run in a dedicated lab schema. Use SALES_FACT_DEMO and MV SALES_REGION_PRODUCT_MV from Section 3.

### Step 1 — Observe Baseline Query Results

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id
ORDER BY region_id;
```

Record the output as a baseline.

### Step 2 — Enable Query Rewrite and Integrity

```sql
ALTER SESSION SET query_rewrite_enabled = TRUE;
ALTER SESSION SET query_rewrite_integrity = ENFORCED;
```

### Step 3 — Inspect the Plan

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Note which data source the plan accesses. Do not expect a fixed operation name across all Oracle releases.

### Step 4 — Gather Statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

Re-run EXPLAIN PLAN and compare.

### Step 5 — Make the MV Stale

Insert a new row into the fact table:

```sql
INSERT INTO sales_fact_demo (
    sale_id, sale_date, region_id, product_id, amount
)
VALUES (
    6, DATE '2026-02-20', 10, 100, 300
);
COMMIT;
```

Because the ON DEMAND MV has not refreshed, it may be stale. Re-run the query and observe how the optimizer behaves under current integrity settings.

### Step 6 — Refresh the MV

```sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list => 'SALES_REGION_PRODUCT_MV',
        method => 'C'
    );
END;
/
```

Re-run the query and reconcile results with the source table.

### Step 7 — Check Rewrite Capability

Prepare REWRITE_TABLE and MV_CAPABILITIES_TABLE using the Oracle Home scripts provided by a DBA. Run DBMS_MVIEW.EXPLAIN_REWRITE and DBMS_MVIEW.EXPLAIN_MVIEW; review messages/capabilities.

### Step 8 — Test an Unrewritable Query

Test a query needing a column absent from the MV or an unstored aggregate. Explain why the MV lacks sufficient information to reconstruct the result.

### Step 9 — Observe Statistics and Cardinality

Run the query with GATHER_PLAN_STATISTICS, view ALLSTATS LAST, and compare estimated rows vs. actual rows. Gather stats and see whether the plan changes.

### Step 10 — Compare Optimizer Baselines

In the lab session, test a release-supported OPTIMIZER_FEATURES_ENABLE value. Compare plans without altering COMPATIBLE or system-wide parameters. Restore the session parameter after testing.

## 19. Common Misconceptions

| Misconception | Reality |
|---|---|
| If an MV exists, Oracle always uses it | Optimizer rewrites only when eligible and cost-beneficial |
| ENABLE QUERY REWRITE is enough | Also requires query rewrite enabled, freshness/integrity, matching data and semantics |
| An MV log is mandatory for rewrite | MV logs primarily support fast refresh; not a universal rewrite prerequisite |
| FORCE guarantees every query uses the MV | Cannot force an invalid or information-deficient rewrite |
| TRUSTED is always safe | Relies on declared assumptions/metadata; violating data can produce wrong results |
| STALE_TOLERATED is purely a performance optimization | Can return data older than the source tables |
| Gathering stats once lasts forever | As data changes, statistics become stale |
| Histograms always improve plans | Histograms help skew but can make plans bind-sensitive |
| COMPATIBLE is the optimizer version | COMPATIBLE controls database compatibility level; OPTIMIZER_FEATURES_ENABLE controls optimizer baseline |
| Lowering OPTIMIZER_FEATURES_ENABLE downgrades the database | Does not downgrade database version or alter all SQL syntax |
| Query transformation always speeds up SQL | Transformations expand candidate plans; cost and data determine the final plan |
| EXPLAIN PLAN shows runtime metrics | It is an estimated plan; actual cursor statistics are needed for measurement |

## 20. Self-Check Questions

1. How does query transformation differ from materialized view query rewrite?
2. What problems do view merging, predicate pushing, and subquery unnesting solve?
3. How do semi-joins and join elimination relate to query transformation?
4. How does a materialized view store data differently from a standard view?
5. Under what conditions can query rewrite substitute a fact table with an MV?
6. Why does an MV need sufficient grouping/filter columns and aggregates?
7. How does ENABLE QUERY REWRITE differ from QUERY_REWRITE_ENABLED?
8. What do the ENFORCED, TRUSTED, and STALE_TOLERATED levels of QUERY_REWRITE_INTEGRITY mean?
9. How does an MV log's role for fast refresh differ from query rewrite?
10. How do ENABLED, VALIDATED, and RELY constraint states affect the optimizer?
11. Why can NOT NULL and NULL semantics determine whether a rewrite is safe?
12. What do DBMS_MVIEW.EXPLAIN_REWRITE and EXPLAIN_MVIEW help diagnose?
13. How do cardinality, selectivity, and cost differ?
14. What do table, column, index, and system statistics describe?
15. When are histograms useful, and what trade-off can they introduce with bind variables?
16. How do extended statistics help when two columns are correlated?
17. How do dynamic statistics and statistics feedback differ from gathering statistics?
18. How do COMPATIBLE and OPTIMIZER_FEATURES_ENABLE differ in scope and purpose?
19. Why does an optimizer feature baseline not replace checking release-level SQL syntax?
20. How does SQL Plan Management differ from query rewrite?
21. Why can a rewritten plan still run slower than a plan reading source tables?
22. Which metrics should be compared before and after deploying MV rewrite?

**Key principle:** query rewrite is safe only when Oracle proves result equivalence given data, constraints, and the configured integrity level. Materialized views can reduce repeated query costs, provided they are designed at the right grain, refreshed per policy, and backed by accurate statistics. When investigating plans, cleanly separate release SQL features, optimizer baselines, query rewrite parameters, and statistics; change one factor at a time in a controlled manner and measure actual plans.
