# Histograms and Skewed Data Distribution

Oracle Database uses the Cost-Based Optimizer (CBO) to choose how to execute SQL statements. The optimizer relies on statistics such as row counts, number of distinct values, number of NULLs, block counts, index statistics, and data distribution to estimate how many rows will satisfy a condition. This estimate influences the choice of access path, join method, join order, and many other decisions.

When data is uniformly distributed, summary statistics such as NUM_DISTINCT and DENSITY may be sufficient for predicate estimation. However, if data has a skewed distribution—where some values appear very frequently while others appear rarely—the uniform distribution assumption can be severely wrong. Histograms supplement value distribution information so the optimizer can estimate selectivity and cardinality more accurately.

For example, an ORDERS table has 1,000,000 rows:

- 990,000 rows have STATUS = 'OPEN'.
- 10,000 rows have STATUS = 'CANCELLED'.

If the optimizer only knows the column has two distinct values and assumes they appear equally often, it may estimate each value accounts for roughly half the table. In reality, OPEN accounts for 99% while CANCELLED accounts for only 1%. Histograms help the optimizer recognize that imbalance.

This lesson covers how to read data distributions, understand histograms, gather statistics with DBMS_STATS, inspect execution plans, and handle issues related to bind variables, column correlation, and plan stability.

## 1. Statistics and the Cost-Based Optimizer

The Oracle CBO selects an execution plan by estimating the cost of multiple alternatives. Statistics are a critical input to these estimates.

Commonly encountered statistics:

| Statistic | Meaning |
|---|---|
| NUM_ROWS | Estimated number of rows in the table |
| BLOCKS | Number of blocks recorded for the table |
| AVG_ROW_LEN | Average row length |
| NUM_DISTINCT | Number of distinct values in the column |
| NUM_NULLS | Number of rows with NULL values |
| DENSITY | Density statistic used in selectivity estimation |
| LOW_VALUE / HIGH_VALUE | Lowest/highest recorded values |
| HISTOGRAM | Histogram type for the column |
| NUM_BUCKETS | Number of histogram buckets |
| CLUSTERING_FACTOR | Degree of correlation between index order and row order in the table |
| LAST_ANALYZED | Timestamp of the most recent statistics collection |

Statistics are stored in the data dictionary and can be viewed via USER_*, ALL_*, or DBA_* views depending on privileges.

Example of viewing table statistics:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
~~~

Viewing column statistics:

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

The optimizer does not rely solely on histograms. It also considers indexes, partitions, system statistics, bind values, constraints, query transformations, and many other factors. Histograms only improve one part of data distribution information.

## 2. Uniform Distribution vs. Skewed Distribution

### 2.1 Uniform Distribution

Suppose a table has 100,000 rows and the STATUS column has 4 values, each appearing 25,000 times:

| STATUS | Row Count | Percentage |
|---|---:|---:|
| NEW | 25,000 | 25% |
| OPEN | 25,000 | 25% |
| CLOSED | 25,000 | 25% |
| CANCELLED | 25,000 | 25% |

This is a near-uniform distribution. Without a histogram, the optimizer can use a uniform distribution assumption based on the number of distinct values to estimate that one value accounts for roughly 1/4 of the rows.

### 2.2 Skewed Distribution

Another table has the same 100,000 rows and 4 values:

| STATUS | Row Count | Percentage |
|---|---:|---:|
| NEW | 2,000 | 2% |
| OPEN | 92,000 | 92% |
| CLOSED | 5,000 | 5% |
| CANCELLED | 1,000 | 1% |

If the optimizer assumes uniformity, it may estimate roughly 25,000 rows per value. The error for OPEN and CANCELLED is very large.

Skewed distributions commonly appear in:

- Business status columns: ACTIVE/INACTIVE, OPEN/CLOSED.
- Transaction type columns: one type accounts for the majority.
- Tenant/customer columns: a few tenants have overwhelmingly more data.
- Region or category columns: a few popular values.
- Boolean flag columns simulated using CHAR or NUMBER.
- Time columns grouped into days/months with uneven density.

### 2.3 Skew Is Not Just About the Number of Distinct Values

A column with thousands of values can still be skewed if a few values appear very frequently. Conversely, a column with only two values might be distributed roughly 50/50 and not need a histogram to represent any difference.

Therefore, a low NUM_DISTINCT does not automatically mean a column needs a histogram. You must examine actual frequencies and how the application filters that column.

## 3. Selectivity and Cardinality

Two concepts you must understand when reading execution plans:

- Selectivity: the fraction of rows expected to satisfy a predicate.
- Cardinality: the number of rows the optimizer expects to receive at a step in the plan.

General estimation formula:

~~~text
Cardinality ≈ Number of input rows × Selectivity
~~~

For example, a table has 100,000 rows:

- A predicate with 1% selectivity → estimated cardinality is roughly 1,000 rows.
- A predicate with 90% selectivity → estimated cardinality is roughly 90,000 rows.

Cardinality affects:

- Index range scan vs. full table scan.
- Nested loops vs. hash join.
- Join order.
- Sort and aggregation strategies.
- Expected memory for hash area/sort area.

If cardinality is far off, the optimizer may choose an expensive plan.

### 3.1 Uniform Distribution Assumption Example

Suppose:

- The table has 100,000 rows.
- The STATUS column has 4 distinct values.
- There is no histogram.

Simple estimation under a uniform distribution:

~~~text
Selectivity ≈ 1 / NUM_DISTINCT
           ≈ 1 / 4
           ≈ 25%

Cardinality ≈ 100,000 × 25%
            ≈ 25,000 rows
~~~

If the predicate STATUS = 'CANCELLED' actually has only 1,000 rows, the estimate of 25,000 is 25 times higher than reality.

### 3.2 Histograms Help Estimate by Value

Histograms store information about value frequencies or distribution boundaries. The optimizer can use this information to produce different estimates for:

- Popular values.
- Rare values.
- Equality predicates on a specific value.
- Range predicates.

As a result, two predicates on the same column can have very different cardinalities.

## 4. Density and NUM_DISTINCT

NUM_DISTINCT is the number of distinct values recorded for the column. DENSITY is a statistic the optimizer uses in selectivity estimation; you should not assume it is always equal to exactly 1/NUM_DISTINCT when a histogram exists or across all predicate types.

In a model without a histogram and with uniform distribution, a basic way to picture it is:

~~~text
Density ≈ 1 / NUM_DISTINCT
~~~

For example, with NUM_DISTINCT = 10:

~~~text
Density ≈ 0.1
~~~

However, when a histogram is present, density can reflect the estimation method for non-popular values or other cases. Read density alongside the histogram type and related statistics rather than interpreting it as the exact frequency of every value.

### 4.1 NUM_NULLS

Histograms normally describe the distribution of non-NULL values. NUM_NULLS stores the count of NULL rows separately. If the application filters with IS NULL, the optimizer can use NUM_NULLS to estimate selectivity.

Do not infer NULL frequency from histogram endpoints. Check NUM_NULLS.

### 4.2 LOW_VALUE and HIGH_VALUE

LOW_VALUE/HIGH_VALUE indicate the recorded value range. They help the optimizer estimate certain range predicates. However, just two boundary values do not fully describe the data between them when the distribution is skewed.

Histograms provide additional information about the distribution within the range.

## 5. What Is a Histogram?

A histogram is a statistical structure describing the distribution of values in a column or expression so the optimizer can estimate selectivity more accurately than a uniform assumption.

A histogram is not:

- An index.
- A business data table.
- A data sorting mechanism.
- A mechanism to force Oracle to use an index.
- A guarantee of a specific execution plan.

A histogram is a statistic. It can cause the optimizer to choose a different plan because estimated cardinalities change.

### 5.1 When Are Histograms Useful?

Histograms are typically useful when:

- The column has skewed data distribution.
- The column appears in appropriate WHERE predicates or JOIN conditions.
- Popular and rare values require different plans.
- Current cardinality misestimates are affecting plan selection.

Histograms are less useful when:

- Data is uniformly distributed.
- The column is not used in predicates/joins.
- Queries do not depend on specific column values.
- The bottleneck lies in I/O, locking, or another algorithm.
- The primary issue is correlation across multiple columns rather than single-column distribution.

### 5.2 Histograms Do Not Modify Data

Gathering a histogram does not update values in the table. It updates statistics in the data dictionary for the optimizer to use when parsing/optimizing SQL.

If data changes significantly after gathering a histogram, the statistics may no longer represent the current data.

## 6. Histogram Types in Oracle

Oracle has several types of histograms. The type created depends on the version, requested number of buckets, number of distinct values, skew, and statistics gathering algorithm.

Types commonly seen in the data dictionary:

- NONE: no histogram.
- FREQUENCY: frequency histogram.
- HEIGHT BALANCED: height-balanced histogram, commonly seen in older/legacy statistics.
- HYBRID: hybrid histogram.
- TOP-FREQUENCY: top-frequency histogram.

### 6.1 Frequency Histogram

A frequency histogram fits when the number of distinct values does not exceed the number of buckets that can be created. Each value can be represented individually, letting the optimizer know the frequency of each value.

Example STATUS column:

| Value | Row Count |
|---|---:|
| OPEN | 92,000 |
| NEW | 2,000 |
| CLOSED | 5,000 |
| CANCELLED | 1,000 |

If the histogram has enough buckets for all 4 values, it can represent each value's frequency. The optimizer has better information when filtering on each status.

Frequency histograms are typically suited for columns with a low number of distinct values and skewed distribution.

### 6.2 Height-Balanced Histogram

A height-balanced histogram is the traditional histogram representation, in which buckets are constructed to contain approximately equal numbers of rows. Repeated values across bucket boundaries can indicate popular values.

This type is commonly found in statistics created by older Oracle versions or in certain legacy scenarios. Starting with Oracle 12c, Oracle introduced new histogram types to improve estimation for skewed data.

Do not try to force creating new height-balanced histograms by relying on old assumptions. Let DBMS_STATS select the appropriate type or use a deliberate policy suited to the running version.

### 6.3 Top-Frequency Histogram

A top-frequency histogram focuses on representing the most popular values when the number of distinct values exceeds the number of buckets available for the entire domain.

For example, a column has thousands of values, but a small group accounts for nearly all rows. The histogram can allocate buckets to the popular group and summarize the less-common tail.

This helps the optimizer estimate better for frequently occurring values without needing a separate bucket for every distinct value.

### 6.4 Hybrid Histogram

A hybrid histogram combines bucket boundary information with endpoint repeat counts. It helps the optimizer identify popular values in columns with more distinct values than buckets.

Hybrid histograms were introduced by Oracle starting in the 12c family to improve estimates for skewed data, especially for equality predicates and frequently repeated values.

### 6.5 Comparing Histogram Types

| Type | General Representation | Common Scenarios |
|---|---|---|
| NONE | No histogram stored | Distribution is sufficiently uniform or column was not selected for a histogram |
| FREQUENCY | Represents frequency of each value | Low NDV, sufficient buckets |
| HEIGHT BALANCED | Buckets have approximately equal row counts | Legacy/older-style histograms |
| TOP-FREQUENCY | Focuses on the group of popular values | High NDV, a small subset dominates the data |
| HYBRID | Bucket boundaries with endpoint repeat counts | High NDV with popular/frequently repeated values |

Algorithm details and selection criteria vary by Oracle version and statistics collection method. Check the HISTOGRAM column in the data dictionary instead of guessing solely from the bucket count.

## 7. Buckets and Endpoints

A histogram divides distribution information into buckets. A bucket may describe a single value or a range of values, depending on the histogram type.

Common metadata in USER_TAB_HISTOGRAMS:

- ENDPOINT_NUMBER: sequence number/cumulative count of the endpoint according to the histogram's representation.
- ENDPOINT_VALUE: internal numeric representation of the endpoint value.
- ENDPOINT_ACTUAL_VALUE: representation of the actual endpoint value in supported versions.
- ENDPOINT_REPEAT_COUNT: number of times the endpoint value repeats, useful with hybrid histograms.

Example of viewing a histogram:

~~~sql
SELECT table_name,
       column_name,
       endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
~~~

Available metadata columns may vary by version. If a view lacks a specific column, check ALL_TAB_COLUMNS/DBA_TAB_COLUMNS or the documentation for your Oracle release.

### 7.1 Endpoints Are Not Data Rows

An endpoint is statistical metadata, not a copy of individual table rows. You cannot use USER_TAB_HISTOGRAMS to reconstruct all original data.

### 7.2 Bucket Count Does Not Have to Equal Distinct Value Count

A histogram can use fewer buckets than NUM_DISTINCT. With summary histogram types, multiple values are represented through a single bucket or statistical tail.

NUM_BUCKETS must be read alongside HISTOGRAM and endpoint metadata.

## 8. Gathering Histograms with DBMS_STATS

Oracle provides the DBMS_STATS package to gather and manage optimizer statistics.

Example of gathering table statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Meaning:

- ownname: schema owning the table.
- tabname: table name.
- estimate_percent: sampling percentage; AUTO_SAMPLE_SIZE lets Oracle choose an appropriate sampling method.
- method_opt: histogram collection policy for columns.
- cascade: gather statistics on related indexes.
- no_invalidate: controls cursor invalidation; AUTO_INVALIDATE lets Oracle decide the appropriate timing.

In production, privileges, timing, and the impact of gathering stats must be managed according to DBA procedures.

### 8.1 SIZE AUTO

SIZE AUTO instructs Oracle to automatically decide whether to create histograms based on statistics, skew, and column usage information tracked in the workload.

Example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

SIZE AUTO is the standard choice for normal operations. Oracle does not necessarily create histograms for every skewed column; usage information and policy influence the decision.

### 8.2 SIZE SKEWONLY

SIZE SKEWONLY instructs Oracle to create histograms for columns evaluated as skewed, without depending on the same workload-based column selection as AUTO.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE SKEWONLY'
    );
END;
/
~~~

SKEWONLY does not guarantee every created histogram will improve plans. It may create histograms on columns that are not queried frequently, so scope and impact should be reviewed.

### 8.3 SIZE REPEAT

SIZE REPEAT instructs Oracle to retain/re-gather histograms for columns that already had histograms previously. It can be useful in stats refresh workflows when preserving existing histogram selections.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE REPEAT'
    );
END;
/
~~~

Understand the current policy before using REPEAT; if a new histogram needs to be created for a column that never had one, REPEAT may not fulfill that goal.

### 8.4 SIZE n

SIZE n specifies the desired number of buckets for the histogram:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE 254'
    );
END;
/
~~~

The example uses 254 buckets per traditional configuration. Maximum bucket counts and histogram algorithms depend on the Oracle version; do not assume 254 is a universal limit across all modern releases.

### 8.5 SIZE 1

SIZE 1 is used to avoid creating a histogram for the specified column:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE 1'
    );
END;
/
~~~

This can be useful when a histogram causes plan instability or offers no benefit. Before removing a histogram, verify the plans and cardinalities of the affected workload.

### 8.6 Specifying a Single Column

You do not have to apply the same policy to every column:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO ' ||
                      'FOR COLUMNS STATUS SIZE 20'
    );
END;
/
~~~

When specifying a per-column policy, check the METHOD_OPT syntax and override behavior for your Oracle version. You can separate gather runs or use table preferences to manage policies clearly.

## 9. Column Usage and SIZE AUTO Decisions

Oracle tracks how columns are used in predicates, joins, and certain SQL contexts. Usage information supports automatic decisions for histograms and extended statistics.

You can view the usage report:

~~~sql
SELECT DBMS_STATS.REPORT_COL_USAGE(
    ownname => USER,
    tabname => 'ORDERS'
)
FROM dual;
~~~

The report helps identify which columns are used in:

- Equality predicates.
- Range predicates.
- Join predicates.
- GROUP BY or other contexts depending on the report/version.

### 9.1 Running the Workload Before Gathering AUTO

If a column has never appeared in tracked workloads, SIZE AUTO may not yet have enough usage information to decide to create a histogram for that column.

A testing workflow:

1. Run a representative SQL workload.
2. Check column usage.
3. Gather stats with SIZE AUTO.
4. Inspect which columns have histograms.
5. Check the plans of critical SQL statements.

Do not run a single query and conclude that AUTO has observed the entire production workload.

### 9.2 Usage Tracking Is Not a SQL Workload Repository

Column usage records column usage patterns according to Oracle's internal mechanism; it does not replace SQL monitoring, AWR, SQL tuning sets, or application logs. It does not provide full execution frequencies, bind distributions, or SLAs for every SQL statement.

## 10. Hands-On Example: Table with Skewed STATUS Distribution

Create a test table:

~~~sql
CREATE TABLE orders_skew_demo AS
SELECT LEVEL AS order_id,
       CASE
           WHEN MOD(LEVEL, 100) = 0 THEN 'CANCELLED'
           ELSE 'OPEN'
       END AS status,
       TRUNC(SYSDATE) - MOD(LEVEL, 365) AS created_date,
       MOD(LEVEL, 1000) + 1 AS customer_id
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Result:

- 100,000 rows.
- 1,000 CANCELLED rows.
- 99,000 OPEN rows.

Verify the distribution:

~~~sql
SELECT status,
       COUNT(*) AS row_count,
       ROUND(COUNT(*) * 100 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM orders_skew_demo
GROUP BY status
ORDER BY status;
~~~

Create an index to test access paths:

~~~sql
CREATE INDEX ix_orders_skew_status
ON orders_skew_demo(status);
~~~

### 10.1 Gathering Statistics Without Histograms

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS_SKEW_DEMO',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

Inspect statistics:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS';
~~~

Without a histogram, the optimizer may have to rely on uniform assumptions and summary statistics.

### 10.2 Gathering a Frequency Histogram

Since STATUS only has two distinct values, you can request enough buckets to represent them:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS_SKEW_DEMO',
        method_opt => 'FOR COLUMNS STATUS SIZE 10',
        cascade    => TRUE
    );
END;
/
~~~

Then inspect:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS';
~~~

With low NDV and sufficient buckets, Oracle can typically create a FREQUENCY histogram. Check the actual HISTOGRAM value instead of assuming.

### 10.3 Viewing Endpoints

~~~sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
~~~

Depending on histogram type and version, some metadata columns may be null or appear differently. The goal is to observe the histogram type and endpoints that Oracle actually stores.

## 11. How Do Histograms Change Estimates?

Suppose the optimizer knows:

- NUM_ROWS = 100,000.
- NUM_DISTINCT = 2.
- No histogram.

A simple uniform estimate for each value is roughly 50,000 rows.

However, the actual distribution is:

| Value | Actual rows |
|---|---:|
| OPEN | 99,000 |
| CANCELLED | 1,000 |

When a histogram captures the frequencies, the optimizer can estimate closer to:

| Predicate | Estimate with Histogram (Conceptual) | Actual |
|---|---:|---:|
| STATUS = 'OPEN' | 99,000 | 99,000 |
| STATUS = 'CANCELLED' | 1,000 | 1,000 |

This example illustrates how histograms improve distribution information. Actual estimates also depend on sampling, statistics, predicates, binds, version, and optimizer transformations.

### 11.1 Plans Can Differ Between Popular and Rare Values

For STATUS = 'CANCELLED', an index range scan may be cheap if only a small percentage of rows is needed and the clustering factor is favorable.

For STATUS = 'OPEN', the predicate returns 99% of the table. A full table scan may be cheaper than reading the index and then accessing nearly every row in the table.

Histograms help the optimizer understand differing selectivities and consider different access paths. They do not force Oracle to use an index.

### 11.2 An Index Is Not Always Better Than a Full Scan

An index on a skewed column may be beneficial for a rare value but poorly suited for a popular value. This does not mean the index is wrong; it means cost depends on the specific predicate.

When evaluating a plan, inspect:

- A-Rows and E-Rows.
- Buffers.
- Physical reads.
- Clustering factor.
- Actual number of rows to be accessed.
- Selected columns.
- Join order and join method.

## 12. Inspecting Execution Plans and Comparing Estimated/Actual Rows

Use GATHER_PLAN_STATISTICS in a test query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       status
FROM orders_skew_demo
WHERE status = 'CANCELLED';
~~~

After fetching all results, view the most recently executed cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

In the report:

- E-Rows: rows estimated by the optimizer.
- A-Rows: actual rows processed at the operation.
- Starts: number of times the operation was started.
- Buffers: logical reads.
- Reads: physical reads recorded.
- Predicate Information: predicates applied.

If E-Rows differs from A-Rows by multiple orders of magnitude, investigate statistics, histograms, correlation, binds, and predicate transformations.

### 12.1 Where Do Estimated Rows Differ from Actual Rows?

Illustrative example:

| Operation | E-Rows | A-Rows |
|---|---:|---:|
| Index range scan | 50,000 | 1,000 |
| Table access by rowid | 50,000 | 1,000 |

A 50x discrepancy can cause the optimizer to miscalculate cost. A histogram can help improve this if the cause is skewed distribution in the STATUS column.

### 12.2 EXPLAIN PLAN Does Not Replace the Actual Plan

EXPLAIN PLAN shows the estimated plan when the SQL statement is parsed in that context. It does not always reflect the actual child cursor, bind peeking, runtime row counts, and waits.

When investigating production, prefer inspecting the running cursor via DBMS_XPLAN.DISPLAY_CURSOR and authorized runtime statistics sources.

## 13. Histograms and Bind Variable Peeking

Bind variables enable SQL cursor reuse:

~~~sql
SELECT order_id
FROM orders_skew_demo
WHERE status = :status;
~~~

During a hard parse, Oracle can peek the first bind value to estimate selectivity. If the column has a histogram, bind values can lead to very different estimates.

Example:

- The first parse binds STATUS = 'CANCELLED' (rare).
- The optimizer chooses a plan suited for a small row count.
- Later, the cursor is invoked again with STATUS = 'OPEN' (popular).
- The old plan may no longer be optimal for the new value.

This is one reason plans can differ between runs or between test and production environments.

### 13.1 Bind Peeking Does Not Mean Every Execution Hard Parses

Oracle normally reuses parsed cursors. Bind peeking happens during optimization on a hard parse; not every execution re-optimizes the entire SQL statement for the new bind.

If multiple values have different selectivities, an initial child cursor may not fit all values.

### 13.2 Adaptive Cursor Sharing (ACS)

Adaptive Cursor Sharing allows Oracle to recognize that a SQL statement using binds may need different child cursors for different selectivity ranges.

Overview:

1. The initial cursor is optimized based on available information, including bind peeking when applicable.
2. Oracle monitors execution behavior and bind selectivity.
3. If it detects that bind values have significantly different selectivities, the cursor can become bind-sensitive.
4. Oracle can create child cursors tailored to different bind selectivity ranges, and the cursor can become bind-aware.

ACS does not guarantee a separate plan for every bind value and does not replace inspecting the plan.

### 13.3 Checking Bind Sensitivity

Some columns in V$SQL:

~~~sql
SELECT sql_id,
       child_number,
       is_bind_sensitive,
       is_bind_aware,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_text LIKE 'SELECT order_id%ORDERS_SKEW_DEMO%';
~~~

The example query may need adjustments for actual SQL_TEXT and access privileges. V$SQL contains cursors currently in the shared pool; it is not a permanent full history.

### 13.4 Do Not Disable Bind Peeking Just to Fix One Query

Disabling or altering bind peeking behavior system-wide can affect many workloads. Before making changes:

- Identify the SQL_ID and child cursor.
- Check bind values and selectivity.
- Inspect the actual plan and execution statistics.
- Check whether ACS is active.
- Consider SQL Plan Management or SQL-specific solutions if appropriate.

Prefer resolving issues at the SQL statement or relevant statistics level rather than changing database-wide parameters without evaluation.

## 14. Histograms and SQL with Literals

If the SQL statement uses a literal:

~~~sql
SELECT order_id
FROM orders_skew_demo
WHERE status = 'CANCELLED';
~~~

The optimizer sees the literal value during optimization and can use the histogram to estimate selectivity for that value.

With a bind:

~~~sql
WHERE status = :status
~~~

The optimizer can peek the bind during a hard parse and use the corresponding histogram. The outcome also depends on cursor sharing, bind type, child cursors, and ACS.

### 14.1 Literals Are Not Always Better Than Binds

Using different literals can generate many distinct SQL texts and increase hard parses/shared pool pressure. Bind variables are usually the right choice for OLTP applications, though skewed data requires checking bind peeking and ACS.

Do not remove bind variables just so the optimizer sees values, unless there is a specific tuning decision and system-wide impact has been weighed.

## 15. Histograms and Range Predicates

Histograms are not only useful for equality predicates. They also provide distribution information so the optimizer can estimate certain range predicates:

~~~sql
SELECT COUNT(*)
FROM orders_skew_demo
WHERE order_id BETWEEN 1000 AND 2000;
~~~

For columns with uneven distribution across the value range, a histogram can help estimate the number of rows within the interval.

For example, a CREATED_DATE column may have data concentrated on certain days or have empty gaps. Assuming uniform distribution from LOW_VALUE to HIGH_VALUE may not reflect the real data.

However:

- Estimation methods for ranges depend on histogram type and predicate.
- A histogram has a finite number of buckets, so it cannot describe every region with absolute precision.
- Expressions or implicit conversions on a column can prevent the optimizer from using statistics as expected.
- Always inspect the actual plan and real cardinality.

## 16. Histograms Do Not Solve Multi-Column Correlation

Another issue with skew is correlation between columns.

For example, in a CUSTOMERS table:

- COUNTRY_CODE = 'US' often pairs with STATE_CODE = 'CA', 'NY', ...
- STATE_CODE = 'CA' only makes sense within COUNTRY_CODE = 'US'.

Each column has its own distribution, yet the combined predicate:

~~~sql
WHERE country_code = 'US'
  AND state_code = 'CA'
~~~

may not be independent. If the optimizer multiplies individual predicate selectivities as if they were independent, cardinality can be wrong.

A single-column histogram describes the distribution of an individual column. It does not fully describe the joint distribution of the COUNTRY_CODE and STATE_CODE pair.

### 16.1 Extended Statistics: Column Groups

Oracle supports extended statistics for column groups to describe statistical relationships between columns.

Create a column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'CUSTOMERS',
    extension => '(COUNTRY_CODE, STATE_CODE)'
)
FROM dual;
~~~

Then gather stats:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Column group statistics can help the optimizer estimate combined predicates better when columns are correlated.

### 16.2 Extended Statistics Are Not Arbitrary Multi-Dimensional Histograms

Column group statistics store extended statistics for the column group, typically including the combined number of distinct values and density. It does not mean Oracle builds a complete histogram for every combination of values.

Treat this as supplemental correlation information, not a replacement for all single-column histograms.

### 16.3 Expression Statistics

If queries frequently use expressions:

~~~sql
WHERE UPPER(customer_name) = 'ALICE'
~~~

statistics on the raw CUSTOMER_NAME column may not accurately reflect the distribution of UPPER(CUSTOMER_NAME). You can consider a function-based index or extended statistics for the expression depending on the workload.

Create expression statistics:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'CUSTOMERS',
    extension => '(UPPER(CUSTOMER_NAME))'
)
FROM dual;
~~~

Then re-gather statistics and inspect the plan. Syntax and applicability depend on the version and expression type.

## 17. Histograms and Partitioned Tables

For partitioned tables, statistics can be collected at the following levels:

- Table/global.
- Partition.
- Subpartition.

Data across partitions can be distributed very differently. For example, with monthly partitions, the current month has many OPEN rows while older partitions are mostly CLOSED.

The optimizer may need both global statistics and partition statistics to estimate accurately when querying:

- A single partition.
- Multiple partitions.
- The entire table.

### 17.1 Global and Partition-Level Histograms

Per-partition histograms reflect local distribution. Global histograms reflect the distribution across the whole table. A globally rare value may be popular within a specific partition.

When partition pruning occurs, accurate partition statistics can be critical. Review how global/partition stats, incremental statistics, and granularity are collected based on the table design.

### 17.2 Incremental Statistics

For large partitioned tables, incremental statistics can reduce the cost of maintaining global stats when only some partitions change, if supported by the configuration and version.

Histograms and incremental statistics follow version-specific rules; do not assume global histograms are accurately merged merely because partition stats were gathered. Check the Oracle documentation and metadata after gathering.

## 18. Stale Statistics and Changing Data

A histogram reflects data at the time of gather. If the distribution changes significantly, an old histogram may no longer be accurate.

Example:

- Previously, 99% of orders were OPEN.
- After a processing campaign, most orders moved to CLOSED.
- The histogram still describes the old distribution.

The optimizer may continue estimating based on statistics that are no longer representative.

### 18.1 Checking Stale Statistics

You can view table statistics status:

~~~sql
SELECT table_name,
       num_rows,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

STALE_STATS can be determined based on monitoring and DBMS_STATS preferences. It is a useful indicator, not a guarantee that every histogram is accurate at every moment.

### 18.2 Periodic Stats Gathering

DBMS_STATS and automatic statistics gathering can maintain statistics. DBAs should determine:

- Rate of data change.
- Stats gather windows.
- Critical tables/columns.
- Acceptable staleness level.
- Invalidation/reoptimization impact.
- Post-gather plan verification procedures.

Do not gather stats continuously just to keep data fresh; gathering stats also consumes resources and can affect cursors/plans.

## 19. Histograms Can Cause Plans to Change

When a histogram is added or changed, estimated selectivity can change. The optimizer may choose:

- Index range scan instead of full scan.
- Full scan instead of index access.
- Nested loops instead of hash join.
- Hash join instead of nested loops.
- A different join order.

A new plan may be better for one value but worse for another, especially when using bind variables.

### 19.1 Plan Regression After Stats Gather

After gathering stats:

- SQL may hard parse again.
- Cursors may be invalidated according to policy.
- The optimizer may create new child cursors/plans.
- Histograms may alter selectivity.

Therefore, gathering stats is a change that can impact execution plans. For critical systems, monitor SQL statements whose execution time or resource usage increases after a stats refresh.

### 19.2 Pending Statistics

Oracle supports pending statistics in certain workflows to test new statistics before publishing them to the entire workload. You can use DBMS_STATS preferences and SET_TABLE_PREFS/SET_SCHEMA_PREFS depending on configuration, then test with a session using pending stats.

A pending stats workflow typically requires a DBA to set up:

1. Configure the appropriate publish preference.
2. Gather stats as pending.
3. Use a session with optimizer_use_pending_statistics to test.
4. Compare plans/results.
5. Publish or discard per procedure.

Do not enable pending statistics in production unless you understand how applications and sessions view statistics.

### 19.3 Restoring Statistics

DBMS_STATS can retain and restore statistics within a configured retention period. Before major changes, DBAs can export stats into a statistics table or use an appropriate stats restore mechanism.

Example of creating a statistics table:

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => USER,
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

Exporting stats:

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        cascade => TRUE
    );
END;
/
~~~

This is an administrative mechanism that requires privileges and does not replace data backups. Verify exact procedure signatures and retention for your Oracle version.

## 20. Histograms and Challenging Predicates

Not every predicate uses histograms in a straightforward way.

### 20.1 Functions on Columns

~~~sql
WHERE UPPER(status) = 'OPEN'
~~~

A histogram on STATUS does not necessarily reflect the expression UPPER(STATUS) directly. Expression statistics or a function-based index may be needed.

### 20.2 Implicit Conversion

~~~sql
WHERE numeric_column = '100'
~~~

Mismatched bind/literal types can cause Oracle to convert data. If a conversion function is applied to the column, indexes and statistics may not be used as expected.

Use properly typed binds and avoid implicit conversion.

### 20.3 LIKE

Histograms are not a universal solution for all LIKE predicates. Selectivity also depends on the pattern, leading wildcards, collation, and index usability.

For example:

~~~sql
WHERE customer_name LIKE 'AL%'
~~~

differs from:

~~~sql
WHERE customer_name LIKE '%AL%'
~~~

Inspect actual plans and statistics.

### 20.4 IS NULL

The count of NULLs is stored separately in NUM_NULLS. Do not assume histogram endpoints contain NULL rows.

## 21. How to Decide Which Columns Need Histograms

Do not create histograms indiscriminately on every column. Evaluate each column with these questions:

1. Is the data truly skewed?
2. Is the column used in WHERE/JOIN?
3. Do different values have significantly different selectivities?
4. Is current cardinality wrong and affecting the plan?
5. Do queries use literals or binds?
6. Is there correlation with another column?
7. Do statistics become stale frequently?
8. Will a new histogram stabilize the plan or introduce plan sensitivity?

An evaluation table:

| Column | Skew | Filtered? | Cardinality Error? | Approach |
|---|---|---|---|---|
| STATUS | High | Yes | Yes | Try a histogram |
| COUNTRY_CODE | Moderate | Yes | Yes with STATE_CODE | Check histogram and column group |
| CREATED_BY | High | No | Does not affect queries | Histogram not needed yet |
| IS_ACTIVE | Near uniform | Yes | No | Likely not needed |
| CUSTOMER_ID | High NDV, tenant skew | Yes | Yes | Try hybrid/top-frequency and check correlation |

## 22. How to Inspect Histogram Metadata

### 22.1 Column Statistics

~~~sql
SELECT column_name,
       num_distinct,
       density,
       num_nulls,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

### 22.2 Endpoints

~~~sql
SELECT column_name,
       endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS_SKEW_DEMO'
ORDER BY column_name, endpoint_number;
~~~

### 22.3 Table Statistics

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

### 22.4 Index Statistics

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

Read these statistics together. Histograms do not determine access paths alone; clustering factor, table size, selectivity, and projected columns also matter.

## 23. Comparing Plans Before and After Histograms

A controlled experiment:

1. Record current statistics.
2. Run queries with both popular and rare values.
3. Capture the actual plans and A-Rows/E-Rows.
4. Gather stats with SIZE 1 to remove histograms.
5. Re-run the same workload and save the plans.
6. Gather stats with the histogram policy.
7. Re-run the same workload.
8. Compare estimated rows, actual rows, buffers, CPU, and elapsed time.
9. Test multiple bind values, not just one value.

Do not compare plan hashes alone. Two different plans do not automatically mean one is faster; measure runtime and resource usage.

### 23.1 Do Not Flush the Shared Pool in Production for Benchmarking

Flushing the shared pool or buffer cache alters system-wide state and can impact other workloads. Only perform this in a controlled test environment with a clear reason.

## 24. Strategies for Handling Binds and Skew

When a column has both popular and rare values, a SQL statement using binds may need multiple plans.

Approaches to consider:

- Gather appropriate histograms.
- Verify bind peeking and Adaptive Cursor Sharing.
- Inspect child cursors and bind selectivity.
- Use SQL Plan Management when controlled plan governance is needed.
- Split SQL statements for business cases with vastly different selectivities if application design permits and measurements justify it.
- Avoid hardcoding literals broadly, which increases parsing.

There is no single solution that fits every system. Choose an approach based on the SQL_ID, workload, and actual plans.

## 25. Skewed Tenant Data Example

Suppose an EVENTS table has TENANT_ID:

- Tenant 1 has 5 million rows.
- Tenant 2 has 100,000 rows.
- Tenant 3 has 5,000 rows.
- Thousands of other tenants have only a few hundred rows.

Query:

~~~sql
SELECT *
FROM events
WHERE tenant_id = :tenant_id;
~~~

An index-based plan may work well for small tenants but poorly for large tenants. Histograms can help the optimizer recognize a few popular tenants.

However, if the query also filters on EVENT_TYPE and CREATED_AT, the joint distribution may matter more than the individual TENANT_ID distribution. Evaluate extended stats, partitioning, and composite indexes based on the workload.

### 25.1 One Index Cannot Optimize Every Tenant

An index:

~~~sql
CREATE INDEX ix_events_tenant
ON events(tenant_id);
~~~

may fit small tenants yet access too many rowids for large tenants. A full scan or partition access may be cheaper for large tenants.

Histograms help the optimizer estimate selectivity, while index selection depends on the cost model and other statistics.

## 26. Histograms and Date/Time Columns

Date/time columns can have uneven distributions:

- Many rows in the most recent few days.
- Fewer rows in older months.
- Certain days with large batch imports.
- Certain periods with no data.

Histograms can help estimate range predicates:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

However, date/time columns often have high NDV and grow continuously. Consider partitioning, incremental stats, high/low values, and range query patterns. Histograms do not replace partition or index design.

## 27. Risks of Creating Too Many Histograms

Creating histograms on every column can cause:

- Increased statistics gathering overhead.
- Increased statistics metadata.
- Altered selectivity estimates for many SQL statements.
- Higher plan sensitivity to bind variables.
- Plan regressions after stats refreshes.
- Harder root-cause analysis when plans change.

Histograms need a clear target: fixing cardinality misestimates that have real impact.

## 28. Operational Workflow for Statistics and Histograms

A practical workflow:

1. Monitor slow SQL or queries with cardinality misestimates.
2. Identify the relevant predicates and columns.
3. Inspect actual data, NUM_DISTINCT, density, num_nulls, and histograms.
4. Check column usage and workload.
5. Inspect the actual execution plan.
6. Determine whether the issue is single-column skew, correlation, stale stats, or bind sensitivity.
7. Test histograms/extended stats in a test environment.
8. Run the workload with both popular and rare values.
9. Measure plans, buffers, CPU, elapsed time, and results.
10. Roll out within scope and monitor plans after gathering.

## 29. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Creating histograms on every column | Complex statistics and plan sensitivity | Use SIZE AUTO or a workload-driven policy |
| Assuming low NDV always needs a histogram | Column may be uniformly distributed | Measure actual value frequencies |
| Assuming a histogram forces index usage | Optimizer still compares costs | Inspect plan and cardinality |
| Looking only at NUM_DISTINCT | Misses per-value distribution | Inspect HISTOGRAM and endpoints |
| Using SIZE SKEWONLY schema-wide without evaluation | Histograms on unimportant columns | Define scope and workload |
| Gathering stats without checking plans | May cause regressions | Compare actual plans before/after |
| Testing only one bind value | Misses popular/rare values | Test multiple selectivity regions |
| Disabling bind peeking system-wide | Impacts other workloads | Investigate SQL_ID and ACS first |
| Using histograms to handle correlation | Single-column stats are insufficient | Create extended column group stats |
| Using old histograms after data changes | Cardinality stays wrong | Monitor stale stats and gather appropriately |
| Confusing endpoints with individual rows | Misinterprets metadata | Understand buckets and histogram types |
| Treating EXPLAIN PLAN as the actual plan | Misses runtime row counts | Use DISPLAY_CURSOR with ALLSTATS LAST |
| Assuming density is always 1/NDV | Wrong with histograms/special cases | Read density in statistical context |
| Concluding a changed plan hash is a regression | A different plan is not necessarily slower | Measure runtime and resource usage |

## 30. Self-Check Practice Exercises

Exercises should be run in a test schema without modifying production statistics.

### Exercise 1 — Uniform Distribution

Create a table with 100,000 rows and four STATUS values appearing nearly equally. Gather stats without histograms, inspect NUM_DISTINCT and DENSITY. Predict the selectivity of each value.

### Exercise 2 — Skewed Distribution

Create a 100,000-row table with 99,000 OPEN and 1,000 CANCELLED. Compare actual row counts and estimates without a histogram.

### Exercise 3 — Frequency Histogram

Gather stats with SIZE 10 on a column with two values. Check HISTOGRAM, NUM_BUCKETS, and endpoints. Explain why a frequency histogram can be used.

### Exercise 4 — SIZE AUTO and SKEWONLY

Run a workload with predicates on a skewed column, inspect column usage, and gather with SIZE AUTO. Compare with SIZE SKEWONLY and explain the differences.

### Exercise 5 — SIZE 1

Remove the histogram on a column in the test schema. Compare E-Rows/A-Rows against when a histogram is present.

### Exercise 6 — Histograms and Indexes

Create an index on STATUS. Compare plans for OPEN and CANCELLED. Observe why one value may use a full scan while the other uses the index.

### Exercise 7 — Bind Peeking

Write SQL using a STATUS bind. Execute with rare and popular values in different orders. Observe child cursors and plans.

### Exercise 8 — Adaptive Cursor Sharing

Monitor IS_BIND_SENSITIVE and IS_BIND_AWARE in V$SQL after executing with multiple bind values. Note the conditions under which Oracle creates child cursors.

### Exercise 9 — Range Predicates

Create a date column with data concentrated in several intervals. Compare range estimates with and without a histogram.

### Exercise 10 — Column Group Statistics

Create a table with correlated COUNTRY_CODE and STATE_CODE. Compare estimated cardinality for a combined predicate before/after CREATE_EXTENDED_STATS.

### Exercise 11 — Stale Statistics

Gather stats, then significantly alter the data distribution. Check STALE_STATS and observe cardinality errors. Re-gather and compare.

### Exercise 12 — Before/After Benchmark

Pick a SQL query with skew. Save the plan, E-Rows/A-Rows, buffers, CPU, and elapsed time. Test a statistics change, execute multiple times with both popular and rare values, and record your conclusion.

## 31. Checklist Before Modifying Histograms

**Data**

- Has the actual distribution been measured?
- Does the column have significant skew?
- Are NUM_DISTINCT and NUM_NULLS appropriate?
- Are statistics stale?

**Workload**

- Does the column appear in predicates/joins?
- Is there a specific SQL_ID with cardinality misestimates?
- Do queries use literals or binds?
- Are there popular and rare values requiring different plans?

**Statistics**

- What is the current HISTOGRAM?
- Is SIZE AUTO/SKEWONLY/REPEAT or an explicit size appropriate?
- Has column usage been recorded?
- Is there correlation requiring extended stats?
- Are there partition-level/global stats to inspect?

**Plan**

- How much do E-Rows and A-Rows differ?
- Did buffers, CPU, and elapsed time improve?
- Is the chosen index/full scan reasonable?
- Were multiple bind values tested?
- Are there regressions in other queries?

**Operations**

- Is there a stats backup/restore plan or pending stats?
- Are invalidation and reparsing controlled?
- Is there a post-gather monitoring plan?
- Is the scope of change bounded?

## 32. Key Takeaways

| Concept | Key Point |
|---|---|
| Skew | Some values appear significantly more often than others |
| Selectivity | Fraction of rows satisfying a predicate |
| Cardinality | Number of rows estimated by the optimizer |
| NUM_DISTINCT | Number of distinct values |
| DENSITY | Statistic used in selectivity estimation, not always exact frequency |
| Histogram | Describes value distribution for the optimizer |
| Frequency | Represents each value when enough buckets exist |
| Height-balanced | Traditional histogram, commonly seen in legacy stats |
| Top-frequency | Focuses on the group of popular values |
| Hybrid | Endpoints and repeat counts help describe popular values |
| SIZE AUTO | Oracle decides based on statistics and usage |
| SIZE SKEWONLY | Chooses histograms based on skew |
| SIZE REPEAT | Preserves existing histogram selections |
| SIZE 1 | Does not create a histogram for the column |
| Bind peeking | Peeks bind values during hard parse |
| Adaptive Cursor Sharing | Can create child cursors for different selectivity ranges |
| Extended statistics | Helps estimate correlation across columns/expressions |
| Stale stats | Statistics may no longer represent current data |
| DBMS_XPLAN | View estimated/actual rows and plans |
| DBMS_STATS | Gather and manage optimizer statistics |

Histograms help Oracle recognize non-uniform data distributions, enabling more accurate selectivity and cardinality estimates for relevant predicates. Identify columns with genuine skew, inspect workloads and actual plans, select an appropriate DBMS_STATS policy, and test with both popular and rare values. If misestimates stem from multi-column correlation, look into extended statistics; if data changes, manage stale stats. Histograms are a tool to improve optimizer information, not a directive to force index usage or guarantee faster plans.
