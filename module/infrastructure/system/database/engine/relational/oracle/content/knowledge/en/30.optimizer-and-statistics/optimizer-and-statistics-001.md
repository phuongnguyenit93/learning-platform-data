# Cost-Based Optimizer and Inputs for Plan Selection

In Oracle Database, a SQL statement describes **what result to retrieve**, while the optimizer decides **how to retrieve that result**. The same SQL statement can be executed using many different plans: scanning the entire table, traversing an index, changing the join order, using nested loops, hash join, or transforming subqueries.

The cost-based optimizer (CBO) estimates the amount of data to be processed and the resources each alternative may consume. It uses these estimates to choose the plan with the lowest estimated cost among the alternatives considered. Therefore, plan quality depends directly on the quality of information the optimizer receives: object statistics, system statistics, SQL structure, schema metadata, bind values, session configuration, and enabled optimizer features.

Understanding the CBO does not mean forcing Oracle to use a specific index or join method. The goal is to recognize what assumptions the optimizer is relying on, whether actual data differs from those assumptions, and which inputs need to be improved so the plan fits the workload.

## 1. Where Does the CBO Work in the SQL Lifecycle?

When an application sends SQL to Oracle, the database must parse the syntax, verify semantics and access privileges, and then find or build an executable cursor.

The main steps can be pictured as follows:

1. **Parse:** parse SQL syntax and resolve objects, columns, data types, and required privileges.
2. **Check for a reusable cursor:** if a matching child cursor already exists in the shared pool, Oracle can reuse the compiled plan. This is commonly called a soft parse.
3. **Query transformation:** the optimizer may transform the SQL statement into a semantically equivalent form to expand the plan search space.
4. **Optimization:** the optimizer evaluates access paths, join orders, join methods, transformations, and execution options; it then computes cardinality and cost for the candidate plans.
5. **Cursor execution:** the row source tree in the plan generates and passes rows between operations step by step.

If no suitable cursor exists, or an existing cursor is no longer valid, Oracle may have to perform a hard parse and re-optimize. A hard parse typically consumes more CPU than a soft parse. Changes to statistics, DDL, metadata, optimizer parameters, binds, or the execution environment can require a cursor to be recreated or cause additional child cursors to be created.

A key point to remember is that the optimizer does not rerun the entire plan search for every SQL invocation. A statement can reuse a cursor, while a single SQL text can also have multiple child cursors if Oracle determines that different executions require different plans or have incompatible environments.

## 2. What Decisions Make Up an Execution Plan?

An execution plan is a tree of operations (row sources). Each operation receives data from child operations, processes it, and returns rows to its parent operation. Key decisions generally fall into four categories:

| Decision Category | Question the Optimizer Must Answer | Examples |
|---|---|---|
| Access path | Where and how should data be read? | Full table scan, index range scan, partition scan |
| Join order | Which table should be processed first? | CUSTOMERS before ORDERS, or vice versa |
| Join method | Which algorithm should join two data sets? | Nested loops, hash join, sort merge join |
| Query transformation | Can the query be rewritten equivalently for better execution? | View merging, subquery unnesting, predicate pushdown |

In addition, the optimizer can choose partition pruning, parallel execution, ordered index access, aggregation operations, sorting operations, and many other operations.

A plan is not a top-to-bottom sequential description of the SQL statement. In an execution plan tree, a parent operation typically consumes output from its child operations. When reading a plan, examine parent-child relationships and the Id/Parent Id columns rather than interpreting the lines as a simple sequential list of instructions.

Common operations include:

- **TABLE ACCESS FULL:** reads table blocks using a full scan.
- **TABLE ACCESS BY INDEX ROWID:** retrieves a rowid from an index and accesses the corresponding row in the table.
- **INDEX UNIQUE SCAN:** looks up a single unique key in a unique index.
- **INDEX RANGE SCAN:** reads a range of keys in an index.
- **INDEX FAST FULL SCAN:** reads the entire index as a data structure capable of multiblock scans; key order is not guaranteed as in an index full scan.
- **NESTED LOOPS:** iterates through the outer data set and looks up matching rows in the inner data set.
- **HASH JOIN:** builds a hash table from one data set and probes it with the other.
- **SORT MERGE JOIN:** sorts or leverages already-sorted data sets, then merges the two sets.
- **HASH GROUP BY, SORT GROUP BY:** performs grouped aggregation using hashing or sorting.
- **SORT ORDER BY:** sorts results according to the ORDER BY requirement.

An operation's name indicates the chosen technique, but is not enough on its own to conclude whether a plan is good or bad. You need to combine estimated rows, actual rows, number of operation starts, buffer gets, physical reads, elapsed time, intermediate data volume, and workload context.

## 3. What Cost Is and What It Is Not

Cost is an internal metric used by the optimizer to compare plans. Depending on the operation type and configuration, the costing model may account for factors such as:

- Number of block reads and read type (single-block or multiblock).
- Caching characteristics and system I/O properties.
- CPU needed for comparisons, joins, sorts, hashing, filtering, and data conversion.
- Number of rows and row width to process.
- Memory available for hashing/sorting and risk of spilling to the temporary tablespace.
- Parallel execution and coordination/data-distribution overhead.
- Platform characteristics and system statistics.

**Cost is not seconds, not actual I/O count, and not a guarantee of completion time.** A cost of 100 does not mean the SQL statement runs in 100 ms. It is a relative estimate within the optimizer's model, most useful when comparing alternatives within the same context.

For example, a full table scan can have a lower cost than an index range scan if the query needs most of the table's rows. When using an index, Oracle may need to read index leaf blocks and then access many table blocks by rowid. If rows are scattered, random I/O can exceed reading table blocks sequentially.

Conversely, if a filter predicate returns only a few rows from a large table, an index can significantly reduce the number of blocks read.

The optimizer mode also influences the optimization goal:

- **ALL_ROWS** targets throughput: minimizing total estimated resources to complete the entire statement. This is the common default mode.
- **FIRST_ROWS_n** targets response time for the first n rows, suited for certain interactive queries that need early results. This mode may favor a plan that returns the first rows faster, even if total work is not the lowest.

You should not assume that FIRST_ROWS_n is always faster for an application or that ALL_ROWS always produces a better plan. The actual goal depends on how the application fetches data, how many rows it needs, and the overall workload.

## 4. Cardinality and Selectivity: The Foundation of Estimation

The two most important concepts when examining how the optimizer estimates data are **cardinality** and **selectivity**.

- **Cardinality** is the number of rows the optimizer estimates an operation will return.
- **Selectivity** is the fraction of rows satisfying a condition relative to the input data set, typically between 0 and 1.

If a table has 1,000,000 rows and the optimizer estimates that STATUS = 'PAID' has a selectivity of 0.1, the estimated cardinality is:

**1,000,000 × 0.1 = 100,000 rows**

This is an estimate, not the actual query result.

### 4.1 Filter Predicate Estimation

Suppose the ORDERS table has 1,000,000 rows and the STATUS column has 4 distinct values. Without data distribution information, a simple assumption is that values are roughly uniformly distributed. An equality condition on one value may then be estimated near:

**Selectivity ≈ 1 / NUM_DISTINCT**

With NUM_DISTINCT = 4, the optimizer may start with a selectivity of approximately 0.25, or about 250,000 rows.

However, actual data can be heavily skewed:

| STATUS | Actual Rows | Percentage |
|---|---:|---:|
| NEW | 700,000 | 70% |
| PAID | 250,000 | 25% |
| CANCELLED | 49,000 | 4.9% |
| RETURNED | 1,000 | 0.1% |

A uniform assumption significantly misestimates RETURNED. If the optimizer thinks the query returns 250,000 rows when only 1,000 rows actually match, the choice between a full scan and index access can be affected. Histograms can provide additional information about this skew.

### 4.2 Join Estimation

Consider a join:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH';
~~~

The optimizer needs to estimate:

1. How many customers satisfy REGION = 'NORTH'.
2. How many orders correspond to that group of customers.
3. The distribution of join keys in both tables.
4. The likelihood of multiple orders per customer.
5. Whether other filter predicates reduce the data before joining.

If one branch's cardinality is misestimated, the error can propagate to operations higher in the plan. A join predicted to produce a few dozen rows that actually produces millions of rows can make a nested loops plan very expensive. Conversely, predicting too many rows can cause the optimizer to choose a hash join and unnecessarily read large volumes of data.

### 4.3 Correlation Between Columns

The optimizer can misestimate when predicates on multiple columns are correlated.

For example, the CUSTOMERS table has two columns, COUNTRY and POSTAL_CODE. If POSTAL_CODE almost uniquely determines COUNTRY, the two predicates:

~~~sql
WHERE country = 'VN'
  AND postal_code = '700000'
~~~

are not independent. If the optimizer multiplies the selectivities of the two predicates as though they were independent, the cardinality can be significantly lower or higher than reality.

Extended statistics, especially column group statistics, help the optimizer describe certain correlations between columns. Expression statistics are also useful when queries frequently filter on a stable expression.

Not every correlation is modeled perfectly. Extended statistics improve specific cases, but you still need to verify estimates against actual data.

## 5. Types of Statistics Oracle Uses

The optimizer relies on multiple layers of statistics. No single number represents all characteristics of a table.

### 5.1 Table Statistics

Table statistics may include:

- **NUM_ROWS:** number of rows recorded at collection time.
- **BLOCKS:** number of blocks recorded for the table.
- **AVG_ROW_LEN:** average row length.
- Information on empty blocks and chain count in certain contexts.
- Separate statistics for each partition or subpartition if the table is partitioned.

This information helps the optimizer estimate data size, number of blocks to read, and table processing cost.

NUM_ROWS is not a real-time counter. After data changes, the dictionary value may not immediately reflect the current row count until statistics are refreshed or the optimizer uses a supplementary mechanism.

### 5.2 Column Statistics

Column statistics typically include:

- **NUM_DISTINCT:** number of distinct values recorded.
- **NUM_NULLS:** number of NULL values.
- **DENSITY:** a component in the selectivity estimation model; how it is used depends on the histogram type and version.
- **LOW_VALUE, HIGH_VALUE:** recorded value boundaries.
- Histogram: describes value distribution when needed.

Column statistics directly affect estimates for equality, range, IN, IS NULL, and other filter predicates.

Min/max values help the optimizer recognize when a condition falls outside the recorded data range. However, if data grows continuously or new values arrive after statistics collection, min/max values can become stale.

### 5.3 Index Statistics

Common metrics include:

- **BLEVEL:** depth of the B-tree index.
- **LEAF_BLOCKS:** number of leaf blocks.
- **DISTINCT_KEYS:** number of distinct keys.
- **CLUSTERING_FACTOR:** degree of correlation between the order of rowids in the index and the physical placement of rows in table blocks.

Clustering factor is critical when index access must visit the table. If rowids for adjacent keys mostly point to the same few table blocks, the clustering factor tends to be low and table access via the index can be efficient. If rowids are scattered across many blocks, the clustering factor can be high and table access cost increases.

Clustering factor does not measure index quality in an absolute sense. An index with a high clustering factor is still useful for very selective queries, though it may be less attractive when a predicate returns many rows.

### 5.4 System Statistics

System statistics describe the system's processing and I/O characteristics, such as CPU capability, single-block/multiblock read times, and I/O throughput. The optimizer uses them to compare access methods under specific hardware and workload conditions.

System statistics do not replace table, column, and index statistics. A table with perfect statistics can still yield unrealistic cost estimates if system statistics do not match the system.

Collecting or modifying system statistics should be done deliberately, based on workload characteristics and environment operating guidelines. Do not copy system statistics from another machine without evaluating differences in CPU, storage, I/O configuration, and concurrency.

### 5.5 Partition Statistics

For partitioned tables, the optimizer may need statistics at multiple levels:

- Global statistics describe the entire table.
- Partition statistics describe each individual partition.
- Subpartition statistics describe each individual subpartition.
- Index statistics may be at the global or local level depending on index type.

When a query reads only a few partitions, partition pruning and partition statistics help estimate the scope of data to process. Global statistics remain important for queries spanning multiple partitions or requiring table-wide estimates.

Updating only one partition can require global statistics to be synchronized or re-estimated. An incremental statistics strategy can be useful for very large partitioned tables, but it must be configured and tested according to Oracle version, partition type, and data loading workflow.

## 6. Histograms Handle Skewed Data Distributions

When a column has a non-uniform distribution, knowing only NUM_DISTINCT is not enough. Histograms provide additional information so the optimizer can estimate selectivity by value or value range.

For example, STATUS has four values, yet 70% of rows are NEW while RETURNED accounts for only 0.1%. Without an appropriate histogram, the optimizer may apply a near-uniform estimate across values. With a histogram, the optimizer has the opportunity to recognize that these two conditions have very different cardinalities.

Common histogram types include:

- **Frequency histogram:** stores frequency information for values when the number of values fits within the bucket limit.
- **Top-frequency histogram:** focuses on the most frequently occurring values, useful when there are many distinct values but a small subset accounts for most of the data.
- **Hybrid histogram:** represents distribution using buckets and endpoints to improve estimates for skewed data.
- **Height-balanced histogram:** a historical type still seen in older systems or legacy documentation.

The optimizer decides how to use histograms based on metadata, statistics, binds, and query context. Do not assume that simply having a histogram guarantees accurate estimates for every query.

### 6.1 Collecting Histograms

DBMS_STATS provides control over histograms via the METHOD_OPT parameter. For example:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => USER,
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => TRUE,
    degree           => DBMS_STATS.AUTO_DEGREE
  );
END;
/
~~~

SIZE AUTO lets Oracle decide which columns need histograms based on usage information and data distribution observed by the database. This is a common starting point, not a guarantee that every important column gets a histogram tailored to application needs.

You can specify a histogram for a particular column, for example:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'ORDERS',
    method_opt => 'FOR COLUMNS SIZE 254 STATUS',
    cascade    => TRUE
  );
END;
/
~~~

The actual bucket count and histogram type are determined by Oracle based on the data, version, and implementation rules. Avoid creating histograms across all columns indiscriminately without reason, as histograms can alter plans for SQL statements that depend on those columns.

## 7. Extended Statistics and Expression Statistics

Individual column statistics do not fully describe relationships between columns. Extended statistics can supplement information for a column group or expression.

For example, if an application frequently filters on both COUNTRY and POSTAL_CODE together, you can create a column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY, POSTAL_CODE)'
       )
FROM dual;
~~~

After creating the extension, you must re-gather table statistics so Oracle computes values for that extension:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
~~~

For predicates on expressions such as UPPER(email), you can consider a function-based index or expression statistics depending on query requirements. A function-based index serves as an access path; expression statistics improve estimation. These two purposes are related but not identical.

Do not create extended statistics merely because two columns appear in the same SQL statement. Verify that they are correlated and that the cardinality misestimation actually impacts the plan.

## 8. Stale, Missing, or Non-Representative Statistics

Statistics can become unsuitable in many situations:

- A table has just received a large bulk load.
- Heavy deletes or updates shifted the data distribution.
- A new partition was loaded, but global statistics do not yet reflect it accurately.
- A column receives new values outside the recorded min/max range.
- A temporary or staging table fluctuates dramatically in size across sessions.
- Data grows over time and the most recent date distribution differs sharply from historical data.
- Statistics were gathered on a sample that does not represent the actual distribution.
- Histograms do not reflect the value groups frequently queried by the workload.
- Index statistics were not updated after significant structural or data changes.

Oracle has a modification-tracking mechanism to determine when statistics may be stale. Stale thresholds and auto statistics gathering behavior depend on preferences, version, and configuration. Therefore, do not assume that changing a fixed percentage of rows immediately triggers re-gathering for every table.

DBMS_STATS is the primary API for gathering and managing optimizer statistics. In addition to GATHER_TABLE_STATS, there are procedures for schema/database-level gathering, managing preferences, locking/unlocking, exporting/importing, and publishing pending statistics.

Common operations include:

~~~sql
-- View basic table statistics columns
SELECT table_name, num_rows, blocks, avg_row_len, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';

-- View column statistics
SELECT column_name, num_distinct, num_nulls, density,
       histogram, num_buckets, last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS';

-- View index statistics
SELECT index_name, blevel, leaf_blocks, distinct_keys,
       clustering_factor, last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS';
~~~

Dictionary views may display differently depending on privileges and version. If querying USER_* views does not show objects belonging to another schema, use views appropriate to your granted privileges, such as ALL_* or DBA_*.

### 8.1 Controlled Statistics Gathering

Example of gathering statistics for a single table:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => TRUE,
    degree           => DBMS_STATS.AUTO_DEGREE,
    granularity      => 'AUTO'
  );
END;
/
~~~

Key considerations:

- AUTO_SAMPLE_SIZE lets Oracle choose an appropriate sampling method.
- CASCADE => TRUE requests gathering statistics on related indexes.
- GRANULARITY => 'AUTO' lets Oracle choose the statistics level suited to partitioning.
- DEGREE affects parallelism during gathering and must be weighed against system load.
- METHOD_OPT determines the histogram policy.
- Gathering statistics can change SQL plans; critical statements should be monitored after publishing.

Do not run a schema-wide gather command during peak hours just because one SQL statement is slow. Identify the specific object and missing statistics, assess the scope of impact, and choose an appropriate timing and rollout approach.

### 8.2 Pending Statistics

For changes that risk affecting many SQL statements, pending statistics let you test new statistics in a test session before publishing them widely.

A general workflow:

1. Set the object's PUBLISH preference to FALSE.
2. Gather new statistics; results are stored in a pending state.
3. In a test session, enable OPTIMIZER_USE_PENDING_STATISTICS = TRUE.
4. Run representative SQL statements and compare plans and performance.
5. If results are satisfactory, publish the pending statistics; otherwise, delete them and investigate further.

Example of setting the preference:

~~~sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'ORDERS',
    pname   => 'PUBLISH',
    pvalue  => 'FALSE'
  );
END;
/
~~~

In the test session:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Preference names and procedures to publish or delete pending statistics should be verified against your running Oracle version. Pending statistics are a rollout-control tool, not a substitute for testing the actual workload.

## 9. Dynamic Statistics and Estimation Support Mechanisms

When standard statistics are missing or insufficient to estimate a query, the optimizer can use supplementary mechanisms.

### 9.1 Dynamic Statistics

Dynamic statistics (formerly known as dynamic sampling) sample data during the parse/optimization phase to supplement information for certain objects or predicate combinations. This mechanism can help with tables lacking statistics, complex conditions, or queries where existing statistics are insufficient.

In return, sampling can increase parse overhead and does not always improve estimates. The dynamic statistics level is influenced by parameters such as OPTIMIZER_DYNAMIC_SAMPLING, configuration, and optimizer decisions.

Dynamic statistics are not a reason to skip gathering baseline statistics. For important tables and stable workloads, properly managed statistics usually provide a more reliable foundation.

### 9.2 Statistics Feedback and Adaptive Behavior

Oracle can compare estimates against actual execution results and use feedback to improve estimates during subsequent optimizations when eligible. Mechanisms such as statistics feedback, adaptive cursor sharing, and adaptive plans have behavior that depends on version, configuration, and query type.

Distinguish among them:

- **Statistics feedback:** uses discrepancies between estimated and actual cardinality to adjust estimates on a subsequent optimization when eligible.
- **Adaptive cursor sharing:** allows a single SQL statement to use multiple child cursors/plans suited to bind value groups with different selectivities.
- **Adaptive plans:** in certain versions/configurations, a plan may contain a secondary option decided during execution based on observed runtime information.

Do not assume these mechanisms are always enabled, always apply, or automatically fix every misestimation. When analyzing, read the Note section of the execution plan and inspect child cursors, bind sensitivity, feedback, and session optimizer parameters.

## 10. SQL Structure and Query Transformation

The optimizer does not only pick operations for the SQL as written. It can transform a query whenever semantic equivalence can be proved.

Common transformations include:

- **View merging:** merges a view into the outer query so the optimizer has more options to push predicates and choose join orders.
- **Predicate pushing:** pushes filter predicates closer to the data source to reduce the number of rows flowing through operations.
- **Subquery unnesting:** converts certain subqueries into joins or equivalent structures to expand plan choices.
- **OR expansion:** splits an OR condition into separate branches, which in some cases enables index usage.
- **Join elimination:** removes a join when constraints and semantics prove the join cannot affect the result.
- **Star transformation:** supports certain analytical queries on star schema models.
- **Partition pruning:** skips partitions that cannot contain data matching the predicate.

Not every transformation applies to every SQL statement. Constraints, nullability, join types, aggregations, analytic functions, non-deterministic functions, or query structure can restrict transformations.

### 10.1 Writing Access-Path-Friendly Predicates

A filter predicate can make an ordinary index hard to use if a function is applied directly to the column.

For example:

~~~sql
-- May prevent a regular index on ORDER_DATE from being used easily
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

It can be rewritten as a half-open range:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

This preserves the exact date-filtering semantics when ORDER_DATE stores a time component, while enabling a range scan on a regular index if other factors align.

Another option is a function-based index on TRUNC(order_date) if that expression appears frequently and fits the workload. When designing indexes, weigh storage and DML costs.

### 10.2 Avoiding Unnecessary Implicit Conversion

Bind and literal data types should match the column data type. For example, if ORDER_ID is NUMBER, bind a NUMBER value rather than sending a string and letting Oracle convert it implicitly.

~~~sql
-- ORDER_ID is NUMBER
SELECT *
FROM orders
WHERE order_id = :order_id;
~~~

If the application binds :order_id as VARCHAR2, Oracle may have to convert the data. Depending on the expression and data types, conversion can affect index usability, cardinality, and plan selection.

Date formats should be specified explicitly when converting strings to dates:

~~~sql
WHERE order_date >= TO_DATE(:from_date, 'YYYY-MM-DD')
~~~

In applications, it is better to bind properly typed DATE/TIMESTAMP values rather than passing date strings and relying on NLS_DATE_FORMAT.

### 10.3 OR, IN, and Subqueries

Multi-branch conditions can lead to multiple plan options:

~~~sql
WHERE status = 'NEW'
   OR status = 'RETURNED'
~~~

In some situations, the optimizer can OR-expand to leverage separate access paths. For IN, subqueries, and EXISTS, the optimizer can also choose semijoins, antijoins, or other transformations.

Do not blindly replace every OR with UNION ALL, or every IN with EXISTS, as an absolute rule. Preserve exact semantics regarding NULLs, duplicates, and result sets, then measure the actual plan.

## 11. Access Paths: Full Scan or Index?

An index is a structure that helps locate data quickly in certain cases. It is not always the cheapest access path.

### 11.1 Full Table Scan

A full scan reads the blocks of a table. It is often appropriate when:

- The query needs most of the rows in the table.
- The table is small.
- The filter predicate is not selective.
- Sequential multiblock reads are cheaper than many random lookups through an index.
- The query must aggregate a large volume of data.

A full scan is not automatically a sign of bad SQL. For analytical queries, a full scan may be the optimal plan.

### 11.2 Index Range Scan and Table Access by Rowid

An index range scan fits when a predicate identifies a key range with sufficient selectivity. After obtaining the rowids, Oracle can access the table blocks to fetch the remaining columns.

The cost depends on:

- Number of keys to read in the index.
- Number of leaf blocks to traverse.
- Clustering factor.
- Number of table blocks to access.
- Number of columns available directly from the index.
- Likelihood that blocks are already in the buffer cache.

An index may satisfy all columns required by a query, allowing Oracle to avoid visiting the table. This is commonly referred to as a covering index in general terminology, though the execution plan displays specific operations such as index fast full scan.

### 11.3 Common Index Access Types

| Operation | General Meaning |
|---|---|
| Index unique scan | Looks up a single unique key in a unique index |
| Index range scan | Reads keys within a range |
| Index skip scan | Leverages a composite index when the predicate omits the leading column, where appropriate |
| Index full scan | Reads the entire index in key order |
| Index fast full scan | Reads the entire index in I/O-optimized order, without guaranteeing key order |
| Bitmap index access | Uses bitmaps to combine conditions, typically suited to analytical workloads with controlled DML |

Column order matters in a composite index. If an index is on (CUSTOMER_ID, ORDER_DATE), predicates on CUSTOMER_ID typically use the leading column directly. A predicate only on ORDER_DATE may require another option, such as a skip scan if eligible, or a different index.

Do not create an index solely because a column appears in WHERE. Consider selectivity, column order, actual queries, DML overhead, index size, and maintenance cost.

## 12. Join Order and Join Method

In multi-table queries, join order can dramatically affect intermediate data volume. The optimizer generally tries to filter early and keep intermediate data sets small, though specific choices depend on cardinality and query constraints.

### 12.1 Nested Loops

Nested loops typically work well when the outer set is small and the inner set has an efficient access path.

Simple model:

1. Fetch one row from the outer set.
2. Use that row's value to find matching rows in the inner set.
3. Repeat for the next row in the outer set.

For example, fetching one customer by unique key and then finding that customer's orders via an index ORDERS(CUSTOMER_ID) can be a strong fit for nested loops.

If the optimizer estimates the outer set has only 10 rows when it actually has 500,000 rows, nested loops can trigger a massive number of inner lookups. Cardinality misestimation on the outer branch is a common cause.

### 12.2 Hash Join

Hash joins typically work well when joining two relatively large sets and the join condition supports hashing.

Simple model:

1. Select one set as the build input.
2. Read the build input and construct a hash table on the join key.
3. Read the other set (probe input), compute the hash key, and find matching entries.

Build input size, row width, PGA memory, and actual row counts affect efficiency. If the hash area is insufficient, the operation can spill to the temporary tablespace, increasing I/O and elapsed time.

A hash join does not require an index on the join key to operate. Thus, the absence of an index on a join column does not mean the query is inevitably slow.

### 12.3 Sort Merge Join

Sort merge join sorts both sets by the join key (or leverages already-sorted inputs), then merges matching rows in order. It can fit large data sets, certain join predicates, or already-sorted inputs.

There is no simplistic rule that nested loops are for small tables, hash joins are for large tables, and sort merge is only for missing indexes. The optimizer weighs cardinality, access paths, data ordering, join conditions, memory, and cost.

### 12.4 Join Order

Suppose a query joins CUSTOMERS, ORDERS, and ORDER_ITEMS. If CUSTOMERS is filtered down to 100 rows first and then joined to ORDERS, the intermediate set can be much smaller than reading all of ORDER_ITEMS first.

However, if the filter on CUSTOMERS is not selective, or if ORDERS is already restricted to a very small partition, a different order may be cheaper.

When you see an unexpected join order, check the cardinality at each branch before concluding the optimizer chose poorly. A seemingly unsuitable join method is often the downstream consequence of a misestimate at a lower operation.

## 13. Partition Pruning and Parallel Execution

Partitioning divides a logical table into physical partitions using a strategy such as RANGE, LIST, HASH, or composite. If query predicates allow identifying which partitions need to be read, Oracle can prune irrelevant partitions.

For example, an ORDERS table partitioned monthly on ORDER_DATE:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-10-01'
  AND order_date <  DATE '2026-11-01';
~~~

Clear range predicates on the partition key column help the optimizer and execution engine identify the matching partition range. Wrapping the column in an expression or using an incompatible data type can limit pruning depending on the expression and partition structure.

Parallel execution lets multiple processes share a unit of work. It can reduce elapsed time for large queries, but consumes substantial CPU, I/O, memory, and concurrency resources. Parallel is not automatically better than serial; a small query can incur extra coordination overhead.

Relevant inputs include degree of parallelism, parallel policies, Resource Manager limits, data size, I/O capacity, and number of concurrent queries. When reading a parallel plan, watch for data distribution operations such as PX SEND/PX RECEIVE, process counts, and data skew bottlenecks.

## 14. Bind Variables, Bind Peeking, and Adaptive Cursor Sharing

Bind variables enable SQL reuse and reduce hard parses caused by varying literals. However, the same SQL with different bind values can have vastly different selectivities.

For example:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE status = :status;
~~~

If :status = 'NEW' returns 70% of the table while :status = 'RETURNED' returns 0.1%, a single plan may not be optimal for both cases.

### 14.1 Bind Peeking

During certain hard parses, Oracle can peek at the current bind value to estimate selectivity and generate a plan. The initial plan may suit the peeked value well but perform poorly for subsequent values.

This is one reason a SQL statement can run fast with one bind value and slow with another, despite having identical SQL text.

### 14.2 Adaptive Cursor Sharing

Adaptive cursor sharing allows Oracle to recognize certain SQL statements as bind-sensitive/bind-aware and create separate child cursors for bind value groups with different selectivity characteristics.

This can improve performance for workloads with skewed bind distributions. Still, do not assume Oracle will always create the exact number of child cursors needed or solve every case automatically. Inspect child cursors, bind capture/peeked binds, and execution statistics.

### 14.3 What Should Applications Do?

- Bind values using the exact data type of the column.
- Do not switch every query to literals just to force plan changes.
- Test multiple executions with bind values representing distinct data groups.
- Inspect child cursors and cursor non-sharing reasons when multiple children exist.
- Evaluate histograms on bind columns if distributions are skewed and the workload truly requires them.
- Test both common cases and rare cases that have vastly different cardinalities.

## 15. Parameters and Environment Factors Affecting the Optimizer

Plans can depend on many factors outside the SQL text:

- **OPTIMIZER_MODE:** optimization goal such as ALL_ROWS or FIRST_ROWS_n.
- **OPTIMIZER_FEATURES_ENABLE:** optimizer feature compatibility level for the specified version.
- **OPTIMIZER_DYNAMIC_SAMPLING:** dynamic statistics level.
- Related adaptive parameters, depending on Oracle version.
- **CURSOR_SHARING:** handling of literals and cursor sharing.
- **STATISTICS_LEVEL:** collection level for certain runtime statistics.
- Degree of parallelism and parallel policies.
- NLS settings, bind data types, current schema, and object resolution.
- Object/system statistics and metadata such as constraints, indexes, and partitions.
- Privileges, synonyms, and object structures that affect SQL resolution.

Do not change optimizer parameters at the system level just to fix one SQL statement without proving the root cause. When experimenting, test at the session or SQL level where appropriate, then evaluate the impact on related workloads.

OPTIMIZER_FEATURES_ENABLE requires particular caution. Lowering or raising compatibility levels can change optimizer behavior across many SQL statements, not just the one under investigation.

## 16. Hints: Deliberate Control Tools

Hints allow embedding directives into SQL, such as suggesting join order, join method, access path, or parallelism.

Syntax example:

~~~sql
SELECT /*+ LEADING(c o) USE_NL(o) INDEX(o ORDERS_CUSTOMER_IX) */
       c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = :customer_id;
~~~

Hints can be useful when clear evidence shows the optimizer cannot choose a suitable plan in a specific scenario, or when testing a plan hypothesis.

However, hints carry risks:

- Data and distributions change, invalidating the original assumptions.
- Index or alias changes prevent the hint from applying as intended.
- Hints can be silently ignored if syntax is wrong, object names are wrong, or the hint is invalid in context.
- Forcing one access path can slow down another group of bind values.
- Hints increase SQL maintenance cost and make behavior harder to explain when the system evolves.

When using hints, inspect the execution plan and the Hint Report section (if supported by the version/format) to confirm whether the hint was accepted or ignored. Never assume that merely writing a hint guarantees Oracle executes your exact intent.

## 17. Stabilizing Plans with SQL Plan Management

Once a good plan has been identified and you want to reduce the risk of unintended plan changes, Oracle provides SQL Plan Management (SPM).

Key concepts to distinguish:

- **SQL Plan Baseline:** a set of accepted execution plans for a SQL statement. The optimizer can use accepted plans and manage the plan evolution process.
- **SQL Profile:** supplies auxiliary estimation/costing information so the optimizer can produce a better plan; a profile itself is not simply a command locking a single execution plan.
- **SQL Patch:** attaches specific hints to a SQL statement via an administrative mechanism, useful in controlled tuning scenarios.
- **Stored Outline:** an older mechanism that may appear in legacy systems.

SPM helps control plan changes, but does not replace understanding the root cause. A baseline preserving an old plan can protect the workload during a transition, yet that plan can still become inefficient as data or workloads evolve.

Before fixing a plan, verify that it performs well across representative bind values and data sets, monitor after deployment, and maintain a strategy to evolve the baseline when real-world conditions change.

## 18. Reading Execution Plans to Verify Assumptions

EXPLAIN PLAN generates an estimated plan without executing the SQL statement. It is helpful for seeing a possible plan, but can differ from the actual cursor's plan due to binds, child cursors, session settings, statistics, or the parse environment.

When investigating executed SQL, inspect the actual cursor using DBMS_XPLAN.DISPLAY_CURSOR.

For example, add the row-source statistics gathering hint for a test run:

~~~sql
SELECT /*+ gather_plan_statistics */
       order_id, order_date
FROM orders
WHERE status = 'RETURNED';
~~~

After execution completes, view the plan of the most recent cursor in the session:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS +NOTE'
  )
);
~~~

In systems with multiple sessions or multiple child cursors, specify the exact SQL_ID and child number rather than relying on NULL, NULL.

Notable columns and sections:

| Component | How to Read |
|---|---|
| E-Rows | Number of rows estimated by the optimizer |
| A-Rows | Actual rows recorded for the execution with statistics |
| Starts | Number of times the operation was started |
| Buffers | Recorded logical reads/buffer gets |
| Reads | Recorded physical reads |
| A-Time | Actual elapsed time of the operation from collected statistics |
| TempSpc | Temporary space usage/estimate depending on format |
| Predicate Information | Access and filter predicates |
| Peeked Binds | Bind values peeked when the cursor was parsed, if any |
| Note | Additional info such as dynamic statistics, adaptive plans, or relevant notes |

ALLSTATS LAST requires row-source statistics to have been collected for that execution. You can use /*+ gather_plan_statistics */ for test queries or configure appropriate statistics collection in a controlled environment. Collecting runtime statistics for every SQL statement in production without considering overhead is inadvisable.

### 18.1 Comparing E-Rows and A-Rows

This is a critical step in locating cardinality misestimates.

- If E-Rows is close to A-Rows, the estimate at that operation is relatively accurate.
- If E-Rows is many times smaller than A-Rows, the optimizer underestimated the data volume.
- If E-Rows is many times larger than A-Rows, the optimizer overestimated the data volume.

For operations executed multiple times, check Starts and how the format displays row counts. For instance, the inner side of a nested loop may start many times; looking only at A-Rows without considering Starts can easily lead to wrong conclusions.

Look for **the first point of misestimation** from the bottom up in the plan tree. If the earliest operation is off by a large factor, parent operations may simply be propagating that error. Investigating the first misestimated operation is usually more effective than tweaking the join method at the top.

### 18.2 Access Predicates and Filter Predicates

Predicate Information shows which conditions are used to access the index/table and which only filter rows after data is read.

- **Access predicate:** participates in locating the range of data to access.
- **Filter predicate:** filters rows after the operation has retrieved its input.

A condition appearing as a filter predicate is not necessarily wrong. However, if a very selective condition is only applied after reading large amounts of data, you may need to review indexes, predicate phrasing, or query transformation opportunities.

### 18.3 Do Not Look Only at Plan Cost

When comparing two plans, also examine:

- Actual rows and estimated rows.
- Operation Starts.
- Buffers and physical reads.
- Elapsed/CPU time under identical test conditions.
- Temporary I/O, spills, and parallel distribution.
- Parse counts, child cursor counts, and bind values.
- Impact on other SQL statements sharing the same objects or indexes.

A plan with a lower cost is not guaranteed to run faster in the real workload if statistics, caching, concurrency, or test environments differ.

## 19. Workflow for Investigating a SQL Statement with a Poor Plan

A practical workflow can follow this sequence.

### Step 1: Identify the Exact SQL and Cursor

Gather the SQL text, SQL_ID, child number, plan hash value, schema, module/action, execution timing, representative bind values, and session environment. If the SQL has multiple child cursors, do not treat them as a single plan.

### Step 2: Retrieve the Actual Execution Plan

Use DBMS_XPLAN.DISPLAY_CURSOR with runtime statistics if available. Identify the plan actually being executed, rather than relying solely on an EXPLAIN PLAN run in another session.

### Step 3: Locate the First Cardinality Misestimate

Compare E-Rows and A-Rows, inspect Starts, and find the lowest operation with a significant discrepancy. Ask: does the discrepancy stem from predicates, joins, column statistics, column correlations, binds, or changed data?

### Step 4: Check Related Statistics

Check table/partition, column, histogram, index, and system statistics. Examine LAST_ANALYZED, stale status, NDV, NULL count, histogram type, clustering factor, and actual data distribution.

Do not inspect only the largest table's statistics. A small table misestimated early in a join branch can also cause the optimizer to select an unsuitable join order.

### Step 5: Inspect SQL and Data Types

Check for implicit conversions, functions on columns, bind data types, predicate sargability, matching data types in join predicates, and whether query transformations are restricted by query structure.

### Step 6: Compare Across Different Bind Values

If the SQL uses binds, test with common, rare, and differing selectivity value groups. Check bind peeking, bind sensitivity, and child cursors. A plan good for a rare bind may be poor for a common bind.

### Step 7: Test Hypotheses in a Controlled Environment

You can test updating statistics, adding extended statistics, adding histograms, rewriting predicates, or trying a different access path. For statistics changes with broad impact, consider pending statistics. Record before/after plans and runtimes under identical conditions.

### Step 8: Choose an Appropriate Stabilization Mechanism

If a plan is verified as good and volatility needs to be controlled, evaluate SQL Plan Management. If estimation errors need fixing, focus on appropriate statistics or profiles. Use hints or SQL Patches only with clear justification and a testing and maintenance plan.

### Step 9: Monitor After Changes

Monitor elapsed time, CPU, logical/physical reads, child cursors, plan hash values, and related SQL statements. A change that improves one query while degrading many others can still be a net negative at the system level.

## 20. Comprehensive Example: Orders Query with Skewed STATUS Distribution

Suppose a system has the following table:

~~~sql
CREATE TABLE orders (
  order_id     NUMBER        NOT NULL,
  customer_id  NUMBER        NOT NULL,
  order_date   DATE          NOT NULL,
  status       VARCHAR2(20)  NOT NULL,
  total_amount NUMBER(12,2),
  CONSTRAINT orders_pk PRIMARY KEY (order_id)
);

CREATE INDEX orders_status_ix
    ON orders(status);

CREATE INDEX orders_customer_date_ix
    ON orders(customer_id, order_date);
~~~

The table contains 10 million rows. STATUS is distributed as follows:

- NEW: 70%.
- PAID: 25%.
- CANCELLED: 4.9%.
- RETURNED: 0.1%.

The application executes:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE status = :status;
~~~

### Case A: Bind Is NEW

The query needs about 7 million rows. Using the ORDERS_STATUS_IX index and revisiting the table millions of times can be expensive. A full table scan may make more sense because the database must read most of the table.

### Case B: Bind Is RETURNED

The query needs only about 10,000 rows. An index can drastically reduce the amount of data read, especially if the clustering factor and number of blocks accessed are favorable.

### Why Can One SQL Have Two Plans?

If the optimizer uses a uniform distribution assumption, it may misestimate both groups. Histograms help describe the skew. Bind peeking and adaptive cursor sharing can help Oracle recognize that bind values belong to different selectivity groups and require appropriate child cursors.

### How to Investigate

1. Check ALLSTATS LAST for each bind value in a test environment.
2. Compare E-Rows against A-Rows at the filter on STATUS.
3. Check the histogram on STATUS and when statistics were gathered.
4. Check index statistics, especially CLUSTERING_FACTOR.
5. Inspect child cursors and bind sensitivity.
6. Evaluate total resources for both common and rare binds.
7. Only then decide whether you need histograms, a statistics refresh, SQL Plan Management, or another measure.

This example shows there is no single access path that is always best for every bind value. Plans must be evaluated against data distribution and how the application actually invokes the SQL.

## 21. Common Misconceptions

| Claim | Accurate Understanding |
|---|---|
| If an index exists, Oracle must use it | An index is just one access path; a full scan can be cheaper |
| A full table scan is always a bad plan | Full scans are appropriate when many rows are needed or the table is small |
| Cost 100 means 100 ms | Cost is an internal metric, not real wall-clock time |
| Gather statistics as frequently as possible | Gather when data/metadata changes significantly and on an appropriate schedule |
| Histograms always improve performance | Histograms improve some estimates but can change plans and require careful control |
| A SQL statement has only one execution plan | A single SQL statement can have multiple child cursors and multiple plans |
| Bind variables always produce better plans | Binds enable cursor sharing; bind peeking and skew can introduce issues to manage |
| Nested loops are always for small tables | It depends on cardinality, access paths, and iteration count |
| Hash join is always faster than nested loops | Each join method suits specific data shapes and workloads |
| Hints are always applied | Hints can be ignored or invalid; always verify in the plan |
| EXPLAIN PLAN is the plan that actually ran | The actual cursor plan can differ due to binds, child cursors, and environment |
| The optimizer automatically fixes all misestimates | Adaptive/feedback mechanisms have specific scopes and eligibility conditions |

## 22. Checklist When Analyzing CBO Decisions

When a SQL statement has an unusual plan or performance changes, verify step by step:

- [ ] Captured the exact SQL_ID, child cursor, and actual execution plan.
- [ ] Recorded the bind values and data types sent by the application.
- [ ] Compared E-Rows, A-Rows, and Starts.
- [ ] Located the first operation with a significant cardinality misestimate.
- [ ] Checked table, partition, column, histogram, and index statistics.
- [ ] Checked data skew and correlations between columns.
- [ ] Inspected clustering factor and cost of accessing table blocks via index.
- [ ] Checked predicates, implicit conversions, and functions applied to columns.
- [ ] Reviewed join order, join methods, and intermediate data set sizes.
- [ ] Checked partition pruning, parallelism, and temporary I/O if applicable.
- [ ] Reviewed child cursors, bind peeking, and adaptive cursor sharing when SQL uses binds.
- [ ] Tested changes in an environment supporting before/after comparison.
- [ ] Assessed impact on other SQL statements using the same objects or statistics.

## 23. Conclusion

The cost-based optimizer selects execution plans based on estimates of data volume and resource usage. Key inputs include SQL and query transformations, table/column/index/partition statistics, histograms, extended statistics, system statistics, bind values, optimizer configuration, and execution environment.

When a plan is suboptimal, start with cardinality: pinpoint which operation is misestimated first, identify the input causing the discrepancy, and verify with execution statistics. Accurate statistics, clear predicates, and a sound understanding of data distribution generally form a stronger foundation for the optimizer. Hints and plan management serve as supplementary control mechanisms when backed by evidence and specific operational goals.
