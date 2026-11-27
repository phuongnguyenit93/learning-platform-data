# Static and Dynamic Partition Pruning in Oracle

When an Oracle table is divided into multiple partitions, queries do not necessarily have to read all partitions. **Partition pruning** is Oracle's ability to identify which partitions can contain rows satisfying the conditions and exclude the remaining partitions from access. If a query only needs data for one month, Oracle can read just that month's partition instead of scanning the entire history.

Oracle can identify the partitions to read directly from information available in the SQL statement and the partition structure (**static pruning**), or only determine them while the statement is executing, after receiving bind values, subquery results, or values from rows of another table (**dynamic pruning**). Both reduce read work; the difference lies in when Oracle knows the target set of partitions and how that information appears in the execution plan.

This lesson belongs to the **Partitioning** topic of *Database Engine Relational Oracle*. It focuses on:

- How partition pruning works and its benefits.
- How static pruning and dynamic pruning differ in when partitions are determined.
- Predicate forms that support pruning on RANGE, LIST, HASH, and INTERVAL partitions.
- The roles of bind variables, subqueries, joins, and partition keys.
- Reading PARTITION START/STOP in execution plans.
- Common pitfalls caused by functions, implicit conversions, and expressions on the partition key.
- How to verify pruning using EXPLAIN PLAN, DBMS_XPLAN, and SQL labs.

## 1. What Problem Does Partition Pruning Solve?

Partitioning divides a large table or index into smaller, independently managed parts. Partitions still belong to a single logical object in SQL; applications typically query the table by its common name without having to choose partition names manually.

Example of an orders table partitioned by month:

~~~text
ORDERS
  P_2026_01  -> January 2026 orders
  P_2026_02  -> February 2026 orders
  P_2026_03  -> March 2026 orders
  P_2026_04  -> April 2026 orders
  ...
~~~

Query:

~~~sql
SELECT order_id, order_date, customer_id, amount
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01';
~~~

If ORDER_DATE is the partition key of RANGE/INTERVAL partitioning, Oracle can eliminate partitions outside March 2026. This elimination of partitions is called partition pruning.

### Benefits

- Reduces the number of partitions and blocks that must be read.
- Reduces I/O and CPU for queries needing only a subset of data.
- Reduces work for table scans or index range scans on partitions.
- Can enable more efficient partition-wise operations and data maintenance.

Pruning alone does not guarantee a fast query. A single retained partition can still contain billions of rows; the query may need to full-scan that partition. Effectiveness depends on the number of pruned partitions, the size of remaining partitions, predicates, statistics, and access paths.

### Pruning vs. index access

Partition pruning determines **which partitions must participate**. Index access determines **how rows are located inside a partition or on an index object**.

For example:

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
  AND customer_id = 100;
~~~

Oracle can prune down to the March partition, then use a local index on CUSTOMER_ID within that partition, or full-scan the partition if the cost favors it. Pruning and indexing are two decisions that can work together rather than replace each other.

## 2. Mechanism for Determining Partitions

Oracle knows partition boundaries from table metadata: the partition key, partition bounds, and partitioning type. When optimizing a query, Oracle checks whether predicates constrain the partition key value.

With RANGE partitioning, each partition holds a range of values. For example:

~~~sql
CREATE TABLE orders (
    order_id    NUMBER,
    order_date  DATE NOT NULL,
    customer_id NUMBER,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_q1    VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2    VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3    VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4    VALUES LESS THAN (DATE '2027-01-01')
);
~~~

Oracle uses predicates on ORDER_DATE to identify which partition bounds can contain matching rows.

### Predicates must relate to the partition key

Forms that can typically prune:

~~~sql
-- Equality
WHERE order_date = DATE '2026-05-10'

-- IN list
WHERE order_date IN (
    DATE '2026-05-10',
    DATE '2026-06-15'
)

-- Range
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01'

-- One-sided comparison
WHERE order_date < DATE '2026-04-01'
~~~

With RANGE partitioning, equality typically needs only one partition; a range may need multiple partitions; predicates that do not constrain the partition key can cause Oracle to read all partitions.

### LIST and HASH partitioning

With LIST partitioning, equality or IN on the partition key allows Oracle to identify the partitions matching the enumerated values:

~~~sql
CREATE TABLE sales_by_region (
    sale_id NUMBER,
    region_code VARCHAR2(10),
    amount NUMBER
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_east  VALUES ('EAST'),
    PARTITION p_west  VALUES ('WEST')
);

SELECT *
FROM sales_by_region
WHERE region_code IN ('NORTH', 'EAST');
~~~

With HASH partitioning, Oracle maps partition key values to partitions using a hash function. An equality predicate covering the partition key generally allows identifying a specific partition; range predicates do not carry the same meaning as in RANGE partitioning and may need to read many or all hash partitions.

### INTERVAL partitioning

INTERVAL partitioning automatically creates interval partitions when data exceeds declared boundaries. Pruning still relies on the partition key and partition bounds; auto-generation of partitions does not eliminate pruning capability.

## 3. Static Pruning

**Static pruning** occurs when Oracle can determine the partitions to access from information known in the SQL statement and metadata at optimization time. Predicates typically contain literals or constant expressions that the optimizer can evaluate prior to execution.

For example:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';
~~~

Both date bounds are literals. Oracle can determine the Q2/2026 partition range while optimizing the statement. The execution plan typically displays specific partition sequence numbers in partition start/stop rather than runtime KEY.

### Equality on the partition key

~~~sql
SELECT *
FROM sales_by_region
WHERE region_code = 'NORTH';
~~~

With LIST partitioning, Oracle can identify partition P_NORTH at optimization time.

### IN list

~~~sql
SELECT *
FROM sales_by_region
WHERE region_code IN ('NORTH', 'WEST');
~~~

Oracle can identify the two corresponding partitions. Depending on partitioning type and plan, the operation may display an iterator over multiple partitions.

### Constant expressions

An expression evaluable from literals can also support static pruning:

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-01-01' + 90
  AND order_date <  DATE '2026-01-01' + 181;
~~~

The optimizer can evaluate constant bounds during optimization. In practice, prefer explicit date literals or properly typed bind variables so SQL stays readable and avoids NLS dependencies.

## 4. Dynamic Pruning

**Dynamic pruning** occurs when Oracle can only determine the partitions to read during execution. Determining values may come from bind variables, subquery results, rows from a joined table, or information available only at runtime.

Example using bind variables:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;
~~~

When optimizing the SQL, Oracle knows the bind names, while the actual values are passed at execute time. The runtime engine uses the bind values to identify the matching partitions. The execution plan typically displays KEY in PSTART/PSTOP to indicate dynamically determined partition boundaries.

### Bind variables do not mean no pruning

A common misconception is that bind variables force Oracle to scan all partitions. That is false. Oracle can still perform dynamic pruning based on bind values at execution time. Bind peeking/adaptive cursor sharing can influence plan selection, yet runtime partition pruning can still occur.

Bind variables enable cursor sharing and reduce hard parses; dynamic pruning lets the same cursor execute across different value ranges while accessing only the matching partitions.

### Dynamic pruning via subquery

For example, a CUSTOMERS table is filtered first, and then the date range to read is determined from another query's result:

~~~sql
SELECT o.order_id,
       o.order_date,
       o.customer_id,
       o.amount
FROM orders o
WHERE o.order_date >= (
          SELECT MIN(c.valid_from)
          FROM customer_campaign c
          WHERE c.campaign_id = :campaign_id
      )
  AND o.order_date < (
          SELECT MAX(c.valid_to)
          FROM customer_campaign c
          WHERE c.campaign_id = :campaign_id
      );
~~~

The date boundaries are known only after executing the subqueries. The optimizer can use the runtime results to prune partitions of ORDERS. Exact capability and plan shape depend on how the optimizer transforms the subqueries and how expressions are used.

### Dynamic pruning via join

A small dimension table can supply the partition key for a fact table:

~~~sql
SELECT f.order_id,
       f.order_date,
       f.amount
FROM selected_periods p
JOIN orders f
  ON f.order_date >= p.start_date
 AND f.order_date <  p.end_date
WHERE p.period_code = :period_code;
~~~

When START_DATE/END_DATE values come from rows of another table, Oracle can prune partitions of ORDERS at runtime. Certain nested-loop plans or query transformations can perform partition pruning for each value from the outer side of the join.

Not every join to a partitioned table automatically prunes. Join conditions must properly relate to the partition key, the optimizer must choose a supporting transformation/access path, and cardinality/statistics must be adequate.

### Dynamic pruning in star transformation

In a data warehouse, dimension filters can identify required keys at runtime. When the optimizer uses star transformation or appropriate bitmap access, the set of fact table partitions can be determined dynamically from the filtered keys. This is a form of runtime pruning; inspect the actual plan rather than inferring it solely from the presence of dimension joins.

## 5. Static vs. Dynamic Pruning: Comparison

| Criterion | Static pruning | Dynamic pruning |
| --- | --- | --- |
| Time partitions are determined | During parse/optimization when predicates are sufficiently explicit | During execution when runtime values are available |
| Common value sources | Literals, constant expressions, predetermined conditions | Bind variables, subqueries, join values, runtime expressions |
| Typical PSTART/PSTOP shown | Specific partition numbers | KEY or corresponding runtime notation |
| Can reduce partitions read? | Yes | Yes |
| Depends on bind values? | Does not need runtime bind values | Usually yes |
| Can reuse one cursor for different ranges? | Plans may be generated per literal/cursor | Can runtime-prune per bind on each execution |

The two types are not two tiers of quality. Dynamic pruning is not inferior just because it happens at runtime; in workloads using bind variables, it is usually the desired behavior. What matters is whether Oracle prunes the right partitions and whether the remaining partition volume fits the query.

### One SQL statement can have multiple pruning types

A complex query can access multiple partitioned objects. One object may be statically pruned by literals while another is dynamically pruned by binds or joins. Inspect each partition operation in the execution plan rather than assigning a single label to the entire SQL statement.

## 6. Reading PARTITION START and PARTITION STOP in Execution Plans

Execution plans typically show partition operations and two columns, PSTART/PSTOP:

- PSTART: starting partition in the accessed range.
- PSTOP: ending partition in the accessed range.
- Specific numbers generally indicate partition numbers determined in the plan.
- KEY generally indicates Oracle will determine partitions at runtime.

Illustrative plan example:

~~~text
| Id | Operation                 | Name   | Pstart | Pstop |
|----|---------------------------|--------|--------|-------|
|  0 | SELECT STATEMENT          |        |        |       |
|  1 | PARTITION RANGE SINGLE    |        |      3 |     3 |
|  2 | TABLE ACCESS FULL         | ORDERS |      3 |     3 |
~~~

This plan shows access to one specific partition. Operation names can be PARTITION RANGE SINGLE, PARTITION RANGE ITERATOR, PARTITION LIST SINGLE, PARTITION LIST ITERATOR, or corresponding variants depending on partition type and selected partition count.

Dynamic example:

~~~text
| Id | Operation                 | Name   | Pstart | Pstop |
|----|---------------------------|--------|--------|-------|
|  0 | SELECT STATEMENT          |        |        |       |
|  1 | PARTITION RANGE ITERATOR  |        | KEY    | KEY   |
|  2 | TABLE ACCESS FULL         | ORDERS | KEY    | KEY   |
~~~

KEY indicates partition boundaries depend on values known only at runtime. It does not mean scanning all partitions. Check actual rows, starts, and predicates to see how many partitions were actually accessed.

### PARTITION RANGE SINGLE and ITERATOR

- SINGLE typically appears when one partition is selected.
- ITERATOR typically appears when Oracle iterates over one or more partitions within a range.
- ALL typically indicates the operation traverses all partitions of the object in that access path.
- LIST/HASH operations have corresponding names depending on the partitioning type.

The operation name alone does not reveal total blocks read. A single partition can still be huge; inspect table access, index access, buffers, and actual rows.

### KEY is not a partition named KEY

KEY in PSTART/PSTOP is a plan symbol, not a partition name. It indicates boundaries are computed dynamically. Do not look for a partition named KEY in `USER_TAB_PARTITIONS`.

## 7. Verifying Pruning with EXPLAIN PLAN and DBMS_XPLAN

Generate a plan:

~~~sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION'));
~~~

The `+PARTITION` format displays partition start/stop information if present in the plan. A broader format can be used:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'ALL +PARTITION +PREDICATE +ALIAS'
    )
);
~~~

`EXPLAIN PLAN` produces an estimated plan, does not execute the query, and does not show the exact runtime partitions accessed. With bind variables or runtime pruning, the plan may display KEY; to verify actual execution, inspect the executed cursor and appropriate runtime statistics.

### Viewing the actual cursor

~~~sql
SELECT /*+ gather_plan_statistics */
       COUNT(*)
FROM orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +ALIAS'
    )
);
~~~

`ALLSTATS LAST` requires runtime plan statistics to be gathered, such as via the `GATHER_PLAN_STATISTICS` hint or appropriate configuration. Check:

- Whether PSTART/PSTOP show specific numbers or KEY.
- Starts for the partition/table access operations.
- E-Rows versus A-Rows.
- Buffers, reads, and elapsed execution time.
- Predicate information showing which conditions are used for access/filter.

If the SQL runs through an application with bind variables, inspect the exact child cursor and bind values of the execution under analysis. `DISPLAY_CURSOR(NULL,NULL,...)` typically shows the session's most recent cursor; environments with many SQL statements may require a specific SQL_ID/child number.

### Partition names and partition numbers

PSTART/PSTOP numbers represent partition positions in the object's metadata when the plan was generated; they are not partition key values and should not be hard-coded in applications. To view names and bounds:

~~~sql
SELECT partition_position,
       partition_name,
       high_value
FROM user_tab_partitions
WHERE table_name = 'ORDERS'
ORDER BY partition_position;
~~~

`HIGH_VALUE` is displayed as a metadata expression and its returned data type depends on the version/view. Do not parse `HIGH_VALUE` strings to build custom query logic; use the partition key and standard SQL predicates.

## 8. Predicates That Aid Pruning

For Oracle to prune effectively, predicates should directly express bounds on the partition key and use the proper data types.

### Use half-open ranges for DATE/TIMESTAMP

For date/month partitions, a half-open range is usually clearest:

~~~sql
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
~~~

This condition covers every instant in March, including time-of-day on the final day of the month, without depending on second/fractional-second precision. Compared to `BETWEEN` two dates, a half-open range avoids guessing end-of-day timestamps.

### Compare with matching data types

If the partition key is DATE, pass a DATE literal or DATE bind. If the partition key is TIMESTAMP, pass an appropriate TIMESTAMP. Avoid comparing a DATE column with a character string:

~~~sql
-- Avoid relying on implicit conversion/NLS.
WHERE order_date >= '01-MAR-2026'
~~~

Instead write:

~~~sql
WHERE order_date >= DATE '2026-03-01'
~~~

Implicit conversion can make results depend on `NLS_DATE_FORMAT` or force Oracle to wrap the expression in a way that affects access paths. Use properly typed bind variables in applications.

### Equality, IN, and range predicates

RANGE partition:

~~~sql
WHERE order_date = DATE '2026-05-10'
~~~

LIST partition:

~~~sql
WHERE region_code IN ('NORTH', 'SOUTH')
~~~

HASH partition:

~~~sql
WHERE customer_id = 12345
~~~

For HASH, equality on the partition key generally identifies a partition; range conditions do not map onto a contiguous range of hash partitions the way they do in RANGE partitioning.

### Combining multiple predicate conditions

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
  AND status = 'PAID'
  AND customer_id = 100;
~~~

The `ORDER_DATE` condition can prune partitions; `STATUS` and `CUSTOMER_ID` further filter rows within the partition or aid index selection. Not every predicate has to reference the partition key.

### OR and complex expressions

~~~sql
SELECT *
FROM orders
WHERE order_date < DATE '2026-01-01'
   OR order_date >= DATE '2026-12-01';
~~~

The optimizer can prune across both intervals if it can evaluate each branch. However, when `OR` mixes the partition key with other columns, or uses complex expressions, pruning capability depends on query transformations and version. Inspect the actual plan.

## 9. Expressions That Can Hinder Pruning

A common mistake is wrapping the partition key in a function, making it harder for the optimizer to map the predicate to partition bounds.

### Functions on the partition key

Suppose ORDERS is partitioned by ORDER_DATE:

~~~sql
-- Can reduce direct pruning capability.
WHERE TRUNC(order_date) = DATE '2026-03-15'
~~~

Replace with a range:

~~~sql
WHERE order_date >= DATE '2026-03-15'
  AND order_date <  DATE '2026-03-16'
~~~

The second condition keeps the partition key column bare and usually prunes more reliably. The optimizer can transform some common functions, but do not depend on that when a clean range predicate can be written.

### Monthly functions on the partition key

~~~sql
-- Easily makes the predicate non-sargable for the partition key.
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-03'
~~~

Write:

~~~sql
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
~~~

If the table is partitioned on an expression, such as `TRUNC(ORDER_DATE, 'MM')` or a virtual column, the predicate should match the partition key expression and corresponding data type. Do not mechanically apply a rule that "no function ever prunes"; the optimizer can support some expressions, so the execution plan is the real evidence.

### Implicit conversion

If the partition key is NUMBER but the application passes a string, or the partition key is DATE but the application passes VARCHAR2, Oracle may have to convert types. Depending on conversion direction, this can block pruning or make predicates NLS-dependent.

Example with a NUMBER partition key:

~~~sql
-- Bind should be NUMBER.
WHERE customer_id = :customer_id
~~~

In JDBC, use `setLong`/`setBigDecimal` appropriately instead of `setString` for numeric columns. For dates, use `setDate`/`setTimestamp` matching the actual datatype.

### Predicates not constraining the partition key

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

If `STATUS` is not the partition key and there is no condition related to the partition key, Oracle typically has to consider all partitions. A local index on `STATUS` can speed up access within each partition, but it does not eliminate partitions from scope on its own.

## 10. Composite Partition Keys and Pruning

A table can be partitioned on multiple columns or partitioned-subpartitioned. With composite partitioning, Oracle can prune at both the partition and subpartition levels if predicates provide sufficient information.

RANGE-HASH example:

~~~sql
CREATE TABLE sales_fact (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8
(
    PARTITION p_2026_q1 VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3 VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4 VALUES LESS THAN (DATE '2027-01-01')
);
~~~

Predicate:

~~~sql
SELECT *
FROM sales_fact
WHERE sale_date >= DATE '2026-04-01'
  AND sale_date <  DATE '2026-07-01'
  AND customer_id = 12345;
~~~

The `SALE_DATE` condition can prune down to the Q2 partition; `CUSTOMER_ID` can further prune to the matching hash subpartition. With only `SALE_DATE`, Oracle still has to read all subpartitions inside the Q2 partition.

### Multi-column partition keys

With RANGE COLUMNS or multi-column strategies depending on version, pruning capability depends on column order and combinations of partition key columns. If a predicate constrains only a subset of the key, Oracle may prune a range without necessarily isolating a single partition. Inspect PSTART/PSTOP and partition operations to understand the actual pruning level.

## 11. Partition Pruning and Local/Global Indexes

Pruning applies to partitioned tables or partitioned indexes. Index locality determines whether an index is organized per partition or across the entire table; it affects access paths and index maintenance, without changing the rule of identifying partitions via the partition key.

### Local index

A local index is partitioned in alignment with the table's partitions. Each index partition holds entries only for the corresponding table partition. When Oracle prunes table partitions, it can access only the corresponding local index partitions.

~~~sql
CREATE INDEX ix_orders_customer_local
ON orders(customer_id)
LOCAL;
~~~

For example, a query filtering by month and customer can prune the table to specific partitions and then use the local index to locate `CUSTOMER_ID` within those partitions:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01'
  AND customer_id = 100;
~~~

### Global index

A global index is organized across multiple table partitions and can be either a nonpartitioned global index or a partitioned global index. A query that prunes table partitions can still use a global index if the access path and cost favor it. Maintaining global indexes during partition maintenance (DROP, TRUNCATE, EXCHANGE, MOVE) must be managed carefully according to supported options and version.

### Pruning does not mean reading only local indexes

Oracle can:

- Prune table partitions and full-scan the remaining partitions.
- Prune partitions and use local index partitions.
- Use a global index to find rowids and then access the corresponding table partitions.
- Choose a full scan of the entire table if the query needs most of the data or has a lower cost.

Read the entire execution plan to understand the order of partition iterators, index access, and table access. Seeing an index operation alone is not enough to conclude whether partition pruning occurred.

## 12. Bind Peeking, Cursor Sharing, and Runtime Pruning

Bind variables can be passed with different values on each execution. Oracle may peek at certain bind values during hard parse to estimate selectivity and choose a plan; adaptive cursor sharing can generate separate child cursors when bind values exhibit different selectivity characteristics.

This relates to plan selection, which must be distinguished from determining partitions at runtime:

- **Bind peeking:** the optimizer inspects bind values during hard parse to estimate cardinality/selectivity.
- **Dynamic pruning:** the execution engine uses runtime values to determine which partitions actually need to be accessed.
- **Adaptive cursor sharing:** Oracle can maintain multiple child cursors for bind value groups with differing selectivity behaviors.

Do not conclude that because bind peeking occurred, pruning must be static. The plan can still display KEY for partition start/stop and perform dynamic pruning on each execution.

### Bind datatype must match the partition key

Example:

~~~sql
SELECT *
FROM orders
WHERE order_date >= :from_date
  AND order_date < :to_date;
~~~

If `ORDER_DATE` is DATE, the application should bind DATE. Passing VARCHAR2 can force Oracle into implicit conversion; aside from NLS risks, the conversion expression can reduce the ability to apply predicates directly to the partition key.

### One cursor, multiple date ranges

An application can reuse the same SQL statement across varying date ranges:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= :from_date
  AND order_date < :to_date;
~~~

The first execution might read one partition; another might read three partitions. Dynamic pruning lets the runtime partition set adapt to bind values without generating a separate literal SQL statement for each range.

## 13. Partition Pruning and Partition-Wise Joins

Partition pruning and partition-wise joins are related in large-table queries, but they are not the same technique:

- Partition pruning eliminates unnecessary partitions from a table access.
- Partition-wise join splits the JOIN operation across corresponding partitions, potentially reducing data exchange and leveraging parallel execution.

If two tables are compatibly partitioned on the join key, Oracle can perform a full or partial partition-wise join depending on structure and predicates. If a small dimension table is not compatibly partitioned, the optimizer may use a partial partition-wise join or broadcast/replicate depending on the plan.

Example of fact and dimension tables both partitioned on CUSTOMER_ID:

~~~sql
SELECT f.customer_id,
       SUM(f.amount)
FROM sales_fact f
JOIN customer_fact_partitioned d
  ON d.customer_id = f.customer_id
WHERE f.sale_date >= DATE '2026-01-01'
  AND f.sale_date <  DATE '2026-02-01'
GROUP BY f.customer_id;
~~~

The `SALE_DATE` predicate can prune partitions by date. The join on `CUSTOMER_ID` can be separately optimized according to the two tables' partitioning schemes. Inspect the plan to distinguish partition pruning operations from `PARTITION HASH/RANGE JOIN` or partition-wise operations.

## 14. Reasons Pruning May Not Behave as Expected

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Query reads all partitions | No predicate on partition key | Add a partition key condition if business logic permits. |
| Predicate uses TRUNC/TO_CHAR on key | Expression makes it hard for optimizer to derive partition range | Write half-open ranges on the base column or match partition expression. |
| Plan displays KEY | Pruning is decided at runtime | Do not treat KEY as a full scan; check runtime stats and bind values. |
| PSTART/PSTOP are numbers yet query is slow | Selected partition is still huge or access path is costly | Inspect block count, indexes, selectivity, and actual rows. |
| Bind query picks poor plan for some values | Selectivity differs across bind values | Check child cursors, bind peeking/adaptive cursor sharing, and stats. |
| Comparing DATE with string | Implicit conversion/NLS | Use DATE/TIMESTAMP literals or properly typed binds. |
| Join fails to prune fact table | Join key/predicate does not support runtime pruning or transformation not chosen | Check partition key, join order, transformations, and plan. |
| Prunes only one level in composite partition | Predicate does not constrain subpartition key | Add subpartition key predicate where appropriate. |
| Uses index yet reads many partitions | Index access does not equate to partition pruning | Inspect partition operations and PSTART/PSTOP separately. |
| Pruning differs across environments | Different partition metadata, stats, bind datatypes, or optimizer settings | Compare DDL, stats, binds, plan hash, and versions. |

## 15. Comprehensive Practice Lab

Perform this in a learning schema with `CREATE TABLE` privileges and adequate quota. DDL statements carry an implicit commit in Oracle; do not run on live business tables.

### Step 1: Create a monthly/quarterly RANGE-partitioned table

~~~sql
CREATE TABLE lab_orders (
    order_id    NUMBER,
    order_date  DATE NOT NULL,
    customer_id NUMBER,
    amount      NUMBER(12,2),
    status      VARCHAR2(20)
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_q1    VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2    VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3    VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4    VALUES LESS THAN (DATE '2027-01-01'),
    PARTITION p_future     VALUES LESS THAN (MAXVALUE)
);
~~~

### Step 2: Insert data across multiple partitions

~~~sql
INSERT INTO lab_orders VALUES
    (1, DATE '2026-01-10', 10, 100, 'PAID');
INSERT INTO lab_orders VALUES
    (2, DATE '2026-02-15', 20, 200, 'PAID');
INSERT INTO lab_orders VALUES
    (3, DATE '2026-04-05', 10, 150, 'PENDING');
INSERT INTO lab_orders VALUES
    (4, DATE '2026-05-20', 30, 300, 'PAID');
INSERT INTO lab_orders VALUES
    (5, DATE '2026-08-01', 20, 250, 'PAID');
INSERT INTO lab_orders VALUES
    (6, DATE '2026-11-12', 10, 400, 'PAID');
COMMIT;
~~~

### Step 3: Observe static pruning

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, amount
FROM lab_orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

Observe the partition operation and PSTART/PSTOP. With the Q2 literal range, Oracle can identify the specific partition during optimization.

### Step 4: Observe dynamic pruning using binds

In a SQL client supporting bind variables:

~~~sql
VARIABLE from_date DATE
VARIABLE to_date DATE

EXEC :from_date := DATE '2026-04-01';
EXEC :to_date   := DATE '2026-07-01';

SELECT /*+ gather_plan_statistics */
       order_id, amount
FROM lab_orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Different clients have different bind declaration syntax. In JDBC/applications, bind DATE using the corresponding datatype API. Observe KEY in PSTART/PSTOP if the plan shows runtime pruning.

### Step 5: Test expressions on the partition key

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE TRUNC(order_date) = DATE '2026-04-05';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

Compare with a range predicate:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE order_date >= DATE '2026-04-05'
  AND order_date <  DATE '2026-04-06';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

Observe how the optimizer handles each expression in your running version. The goal is to understand why direct predicates on the partition key usually prune more easily, without assuming every function expression always blocks pruning.

### Step 6: Inspect partition metadata

~~~sql
SELECT partition_position,
       partition_name,
       num_rows,
       blocks
FROM user_tab_partitions
WHERE table_name = 'LAB_ORDERS'
ORDER BY partition_position;
~~~

`NUM_ROWS`/`BLOCKS` reflect statistics; if ungathered or stale, values may be NULL or unrepresentative of current data. You can gather stats in the lab schema:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        granularity => 'ALL'
    );
END;
/
~~~

### Step 7: Clean up data

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Run only after completing the lab and when data no longer needs to be kept. `DROP TABLE` is DDL with an implicit commit; `PURGE` bypasses the Recycle Bin.

## 16. Self-Check Questions

1. **What is partition pruning?** Oracle's exclusion of partitions that cannot contain rows satisfying predicates from access operations.
2. **How does pruning differ from index access?** Pruning selects partitions; index access locates rows within the selected partition/object scope.
3. **What information does static pruning typically rely on?** Literals or constant expressions from which the optimizer can determine partitions at optimization time.
4. **What information does dynamic pruning typically rely on?** Bind values, subquery results, join values, or runtime expressions available only at execute time.
5. **Do bind variables prevent pruning?** No; Oracle can use bind values at runtime for dynamic pruning.
6. **What are PSTART/PSTOP?** Two columns in an execution plan indicating the starting/ending partition of a partition access operation.
7. **What does KEY in PSTART/PSTOP mean?** Partition boundaries are determined dynamically at runtime; it is not a partition name and does not mean scanning everything.
8. **What does PARTITION RANGE SINGLE usually indicate?** The access path selects a single range partition.
9. **What does PARTITION RANGE ALL usually indicate?** The operation accesses all partitions within that object's scope.
10. **Why use half-open ranges for DATE?** It covers the entire time period cleanly and avoids guessing end-of-day values.
11. **What problem can TRUNC(partition_key) cause?** Functions on the key can hinder the optimizer from deriving partition ranges; direct predicates generally prune more easily.
12. **How does implicit conversion affect pruning?** It can make predicates NLS-dependent or cause the expression to no longer operate directly on the partition key.
13. **When does dynamic pruning via join occur?** When partition key values come from outer/joined rows and Oracle can determine partitions at runtime.
14. **Do local indexes automatically create partition pruning?** No; local indexes are organized along table partitions, while pruning still depends on predicates and the partition key.
15. **Does EXPLAIN PLAN prove actual runtime pruning?** No; it shows an estimated plan. You must inspect the executed cursor and runtime statistics.
16. **Why can a pruned partition still be slow?** The remaining partition can still be huge, or the access path, selectivity, I/O, and CPU remain expensive.
17. **Are partition pruning and partition-wise joins the same?** No; pruning excludes partitions from access, whereas partition-wise join splits a join across corresponding partitions.
18. **How do you confirm pruning improved performance?** Compare actual plans, partition starts, buffers, reads, actual rows, latency, and throughput under comparable workloads.

Both static and dynamic partition pruning aim to reduce the number of partitions Oracle must access. Static pruning determines partitions from literals/expressions known during optimization; dynamic pruning waits for binds, subqueries, or join values available at runtime. Write predicates directly on the partition key with matching data types, read PSTART/PSTOP alongside operations and runtime statistics, and verify on real workloads. A plan showing KEY can still prune very effectively; a plan accessing a single partition can still be slow if that partition is massive or the access path is unsuitable.
