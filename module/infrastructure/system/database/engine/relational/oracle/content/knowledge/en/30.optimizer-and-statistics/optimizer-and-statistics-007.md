# Extended Statistics in Oracle Database

## 1. Why Does the Optimizer Need Extended Statistics?

The Oracle Cost-Based Optimizer (CBO) selects an execution plan based on estimated cost. A critical input to estimation is **cardinality**: the number of rows the optimizer predicts will flow through each step of the execution plan. Cardinality affects join order, the choice between nested loops and hash join, access path selection, and required memory.

With standard statistics, Oracle stores information separately for each column, such as number of distinct values (NDV), number of NULLs, density, and histograms if needed. When a SQL statement filters on multiple columns simultaneously, the optimizer may have to estimate the probability of the combined conditions. If the columns are independent, multiplying individual selectivities is a reasonable approximation. However, real-world data often has relationships between columns.

For example, in the `CUSTOMERS` table, `COUNTRY_ID` and `CUST_STATE_PROVINCE` have a clear relationship: the value `CA` for California appears only with the country `US`. Suppose 50% of customers belong to `US`, and 5% of customers have state `CA`. If the two columns are assumed independent, the optimizer may estimate:

\[
P(COUNTRY\_ID = 'US' \land CUST\_STATE\_PROVINCE = 'CA')
\approx 0.50 \times 0.05 = 0.025
\]

The result is 2.5% of rows, whereas the actual proportion may be 5%. This discrepancy causes the optimizer to underestimate the rows to process. For large tables or long join chains, a cardinality error at one step can lead to suboptimal plan choices across many subsequent steps.

Another scenario arises when SQL filters on an expression, such as `UPPER(EMAIL)`, `TRUNC(ORDER_DATE)`, or `SUBSTR(CODE, 1, 3)`. Individual statistics on the base column do not necessarily describe the distribution of values after evaluating the expression.

**Extended statistics** supplement statistical information for a group of correlated columns or for an expression. This gives the optimizer additional data to estimate selectivity and cardinality more realistically.

## 2. What Are Extended Statistics?

Extended statistics are additional statistics managed by `DBMS_STATS` for a table. There are two primary types:

| Type | Target Being Measured | Use Case |
|---|---|---|
| Column group statistics | A group of two or more columns, examining their combined values | Multiple columns are correlated and frequently appear together in query conditions |
| Expression statistics | Result of an expression on columns | Query conditions apply functions or calculations to columns |

Extended statistics serve **optimizer estimation**. Creating them does not create an index, does not store an extra copy of table rows, and does not by itself add new access paths for queries. They also do not replace regular single-column statistics; the two types complement each other.

Oracle creates the metadata for the extension first, then collects statistical values when `DBMS_STATS` gathers statistics for the table. Therefore, merely calling `CREATE_EXTENDED_STATS` and stopping is not enough to give the optimizer new numbers: you must gather statistics according to an appropriate workflow.

## 3. Column Group Statistics for Correlated Columns

### 3.1. Identifying When a Column Group Is Needed

Consider a column group when all of the following signs are present:

- A SQL statement frequently filters or groups by multiple columns of the same table.
- Values of those columns have a real-world relationship, so the joint distribution differs significantly from an independence assumption.
- The execution plan shows `E-Rows` (estimated rows) diverging substantially from `A-Rows` (actual rows) at the table filter step.

Example:

```sql
SELECT customer_id, cust_state_province
FROM customers
WHERE country_id = 'US'
  AND cust_state_province = 'CA';
```

Both predicates appear together in one query and have a semantic relationship. Individual statistics on `COUNTRY_ID` and `CUST_STATE_PROVINCE` describe each column separately; the column group `(COUNTRY_ID, CUST_STATE_PROVINCE)` adds statistics for value combinations.

Column groups can also be useful when columns are frequently used together in the workload, such as filter predicates, join predicates, or `GROUP BY`. Rely on the actual workload and execution plans to choose column groups rather than creating every possible combination.

### 3.2. Creating Column Groups with DBMS_STATS

The `DBMS_STATS.CREATE_EXTENDED_STATS` function accepts the schema name, table name, and an expression describing the extension. For a column group, the expression is a parenthesized list of columns:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY_ID, CUST_STATE_PROVINCE)'
       ) AS extension_name
FROM dual;
```

The function returns the Oracle-generated extension name. Next, gather statistics for the table:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

When table statistics are gathered, Oracle also collects statistics for the created extension. Oracle's automatic statistics gathering job can keep it updated later; if you need to control timing or verify results immediately, call `GATHER_TABLE_STATS` as shown.

### 3.3. Creating and Gathering Column Groups via METHOD_OPT

An alternative is to declare the column group directly in the `METHOD_OPT` parameter of `GATHER_TABLE_STATS`. Oracle can create the extension and gather statistics for that group in the same operation:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt =>
      'FOR ALL COLUMNS SIZE AUTO ' ||
      'FOR COLUMNS (COUNTRY_ID, CUST_STATE_PROVINCE) SIZE AUTO'
  );
END;
/
```

`SIZE AUTO` lets Oracle decide whether a histogram is needed based on usage info and data distribution. When finer control is needed, you can create the extension separately and configure `METHOD_OPT` according to system histogram policy. There is no need to create the same column group twice using both methods.

### 3.4. How Column Groups Help the Optimizer Refine Estimates

Suppose a SQL statement has two predicates:

```sql
WHERE country_id = 'US'
  AND cust_state_province = 'CA'
```

With only individual column statistics, the optimizer may combine the selectivities of the two predicates assuming independence. A column group provides information on value combinations present in the data, such as the number of distinct combinations and group density. When matched against the query's predicates, the optimizer can use this combined information to estimate post-filter row counts more accurately.

A histogram on a column group can be helpful when value combinations are also skewed. However, a histogram is not always required: let `SIZE AUTO` decide first, then inspect plans and workloads if there is reason to tune further.

## 4. Expression Statistics for Predicates with Functions or Calculations

### 4.1. The Problem with Predicates on Expressions

Consider the SQL statement:

```sql
SELECT customer_id, cust_state_province
FROM customers
WHERE UPPER(cust_state_province) = 'CALIFORNIA';
```

The filter predicate applies `UPPER` to the column value. Standard statistics on `CUST_STATE_PROVINCE` describe raw data, whereas the optimizer needs to estimate the distribution of the result of `UPPER(CUST_STATE_PROVINCE)`. Without appropriate statistics for the expression, selectivity estimates can be inaccurate.

Other common examples:

```sql
WHERE TRUNC(order_date) = DATE '2026-11-14'
WHERE SUBSTR(product_code, 1, 3) = 'ABC'
WHERE amount + tax_amount > 1000
```

In each case, the expression can alter the value distribution that the optimizer must estimate.

### 4.2. Creating Expression Statistics

You can create an extension for an expression using `CREATE_EXTENDED_STATS`. The expression is enclosed in parentheses:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(UPPER(CUST_STATE_PROVINCE))'
       ) AS extension_name
FROM dual;
```

Then gather statistics for the table:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

Or declare the expression directly in `METHOD_OPT`:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt =>
      'FOR ALL COLUMNS SIZE AUTO ' ||
      'FOR COLUMNS (UPPER(CUST_STATE_PROVINCE)) SIZE AUTO'
  );
END;
/
```

The expression must match how queries actually write the predicate. For example, statistics for `UPPER(CUST_STATE_PROVINCE)` should not be assumed to substitute for statistics on a different expression such as `LOWER(CUST_STATE_PROVINCE)` or `SUBSTR(CUST_STATE_PROVINCE, 1, 3)`. If a query changes how the expression is written, re-check whether the optimizer can use the extension.

### 4.3. Expression Statistics vs. Function-Based Indexes

These two features solve two different parts of the problem:

| Feature | Primary Role |
|---|---|
| Expression statistics | Supply statistics so the optimizer estimates selectivity and cardinality for expression predicates |
| Function-based index | Create an access path based on expression values, allowing Oracle to locate rows via an index when the plan fits |

For example, statistics on `UPPER(EMAIL)` can help the optimizer better estimate `UPPER(EMAIL) = :email`. They do not create an index on `UPPER(EMAIL)`. If the goal also includes speeding up row retrieval, evaluate a function-based index separately along with its index maintenance cost. You can use both expression statistics and a function-based index when the workload and execution plans show both are beneficial.

## 5. Discovering Column Groups from the Workload

When it is unclear which column groups are worth creating, Oracle provides `DBMS_STATS.SEED_COL_USAGE` and `DBMS_STATS.REPORT_COL_USAGE` to record how the workload uses columns.

### 5.1. Capturing Column Usage Information

During a suitable monitoring window, run:

```sql
EXEC DBMS_STATS.SEED_COL_USAGE(USER, 'CUSTOMERS', 300);
```

This command instructs Oracle to record column usage info for the table over the specified duration (300 seconds). During that period, run a representative workload or compile representative SQL statements; running `EXPLAIN PLAN` for appropriate queries can also help Oracle record how columns are used. Choose a workload close to real activity rather than using only a single rare SQL statement.

### 5.2. Viewing the Column Usage Report

After capturing, view the report:

```sql
SELECT DBMS_STATS.REPORT_COL_USAGE(USER, 'CUSTOMERS')
FROM dual;
```

The report shows columns appearing in filter predicates, join predicates, and `GROUP BY`. Based on column groups frequently used together—combined with signs of data correlation and cardinality errors—choose helpful extensions.

Oracle also provides an overload of `CREATE_EXTENDED_STATS` accepting schema and table name without an `extension` parameter; this overload creates extensions based on recorded column usage information and returns a report. Review the output before incorporating suggested extensions into operational workflows.

Note: column usage tracking helps identify **column groups**. It does not automatically discover all needed expression statistics; expressions in predicates must be reviewed separately.

### 5.3. Automatically Creating Column Groups

The `AUTO_STAT_EXTENSIONS` preference controls automatic extension creation during optimizer statistics gathering. In Oracle versions supporting this preference, the default value is `OFF`. When set to `ON`, eligible SQL Plan Directives can trigger column group creation based on how the workload uses predicates; that does not mean Oracle will automatically create every column combination.

Example configuring at a single-table scope:

```sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => USER,
    tabname => 'CUSTOMERS',
    pname   => 'AUTO_STAT_EXTENSIONS',
    pvalue  => 'ON'
  );
END;
/
```

Enable this preference only once you understand your statistics management policy and the behavior of your running Oracle version. For environments requiring tight change control, creating extensions manually after reviewing the workload is often more predictable.

## 6. Verifying Extensions and Evaluating Effectiveness

### 6.1. Viewing Declared Extensions

The `USER_STAT_EXTENSIONS` view lists statistics extensions in the current schema:

```sql
SELECT table_name, extension, creator
FROM user_stat_extensions
WHERE table_name = 'CUSTOMERS';
```

You can use `ALL_STAT_EXTENSIONS` or `DBA_STAT_EXTENSIONS` when inspecting objects outside the current schema with sufficient privileges. This view confirms an extension is declared; to confirm values have been updated, check statistics gather timestamps and the SQL execution plan.

### 6.2. Comparing Estimated Rows with Actual Rows

Run the SQL with runtime plan statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */ COUNT(*)
FROM customers
WHERE country_id = 'US'
  AND cust_state_province = 'CA';
```

Immediately afterward, view the execution plan of the cursor just run:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE'
  )
);
```

In the output, compare `E-Rows` with `A-Rows` at the table-processing step and related steps. `E-Rows` is the optimizer's estimated row count; `A-Rows` is the actual row count observed during execution. If the two values are closer after adding extended statistics, that indicates the statistics improved estimation. Also check the entire plan and execution time: more accurate cardinality is an intermediate goal and does not by itself guarantee every query will run faster.

When comparing before and after, keep test conditions equivalent: the same SQL, bind values, data, cache state, and environment. If data or bind values differ significantly, plan differences may stem from other causes.

## 7. Lifecycle Management and Limits to Remember

### 7.1. Target Extensions Selectively

Each column group adds another statistical object to manage. Creating every column pair in a table can increase extension counts, gather time and work, and make configuration hard to track. Prioritize groups backed by workload evidence and cardinality errors.

### 7.2. Keep Statistics Fresh

Extended statistics are only useful when they reflect current data. After major data changes, ensure the statistics gathering workflow refreshes both table and extension statistics. Check gather schedules, stale status, and `LAST_ANALYZED` timestamps in the appropriate statistics views.

### 7.3. Histograms and Data Skew

Column group statistics add information about relationships between columns; histograms describe skewed value distributions. These are related but distinct dimensions. If a group has some very common combinations and many rare ones, check whether a histogram is needed. Do not mechanically increase bucket counts, because histograms also carry storage overhead and can make plans more sensitive to bind values.

### 7.4. Do Not Replace Other Tuning Measures

Extended statistics address **estimation** issues. They do not fix non-sargable predicates, replace needed indexes, eliminate a full table scan when a full scan is the cheapest choice, or fix poorly written SQL. If cardinality is already reasonable yet the query remains slow, continue investigating access paths, join methods, I/O, CPU, wait events, and SQL structure.

### 7.5. Dropping Extensions No Longer Needed

If the workload changes and an extension is no longer useful, drop it with `DBMS_STATS.DROP_EXTENDED_STATS`:

```sql
EXEC DBMS_STATS.DROP_EXTENDED_STATS(
  USER,
  'CUSTOMERS',
  '(COUNTRY_ID, CUST_STATE_PROVINCE)'
);
```

For expression statistics, pass the exact declared expression, such as `'(UPPER(CUST_STATE_PROVINCE))'`. Before dropping in production, check which SQL statements rely on estimation improvements from that extension and monitor plans after the change.

## 8. Practical Application Workflow

A workflow you can apply per table:

1. Select a representative SQL statement with multiple predicates on the same table or predicates applying functions to columns.
2. Capture the execution plan with runtime statistics; locate the step with a large discrepancy between `E-Rows` and `A-Rows`.
3. Check existing statistics, histograms, statistics freshness, and whether data has correlations or expressions have special distributions.
4. For correlated columns, use the column usage report or workload to identify column groups. For expression predicates, identify the exact expression needing statistics.
5. Create the extension with `CREATE_EXTENDED_STATS` or declare it in `METHOD_OPT`, then gather statistics.
6. Re-run the representative workload and compare cardinality, execution plans, and runtime.
7. Keep extensions when measurable improvements are explainable; monitor and remove extensions that no longer add value as the workload evolves.

Extended statistics are especially useful when the optimizer understands individual column distributions well yet still misestimates combined predicates or expression-transformed values. They provide the CBO with better evidence about real data to choose a more suitable execution plan.

## Oracle Reference Documentation

- [Oracle Database 19c SQL Tuning Guide — Managing Extended Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-extended-statistics.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html)
