# Tabular EXPLAIN, FORMAT=JSON, and FORMAT=TREE

When a MySQL query runs slowly, you need to know how the server is reading each table, which index it uses, in what order it combines tables, and how many rows are estimated to pass through each step. The **EXPLAIN** statement lets you inspect the plan the optimizer intends to use. MySQL provides several representations of an execution plan: the traditional tabular format, JSON format, and iterator tree format.

These three formats describe the same plan at different levels of detail and presentation. The tabular format is convenient for quickly checking access types and indexes; JSON represents nested structures and detailed cost information; TREE clarifies the order of iterators and how data flows through each step. In MySQL 8.0.18 and later, **EXPLAIN ANALYZE** also executes the SELECT query and adds actual runtime metrics to compare against estimates.

This lesson belongs to the **Execution Plans** chapter of the **DATABASE_MYSQL** module. Within the scope of mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, the ability to read execution plans is the foundation for identifying bottlenecks, evaluating indexes, and tuning queries based on evidence.

## 1. What does EXPLAIN tell you?

The MySQL optimizer analyzes the SQL statement, table and index statistics, filter conditions, join order, and available execution options. The optimizer estimates the cost of candidate approaches and selects one plan. EXPLAIN displays the plan chosen at analysis time.

Three types of information should be distinguished:

- **Access path**: how MySQL locates rows in each table, such as a full table scan, an index scan, or an index range lookup.
- **Join strategy**: how rows are combined across tables, the table read order, and the join algorithm.
- **Estimates**: the row count, filtering percentage, and cost projected by the optimizer.

Standard EXPLAIN does not execute the SELECT statement to measure actual runtime. It displays optimizer estimates. Therefore, a plan that looks good on paper can still be slow if statistics are stale, data is skewed, cache state differs from expectations, or the environment is under heavy load.

Commonly used formats:

~~~sql
EXPLAIN
SELECT ...;
~~~

~~~sql
EXPLAIN FORMAT=JSON
SELECT ...;
~~~

~~~sql
EXPLAIN FORMAT=TREE
SELECT ...;
~~~

MySQL also allows setting a default session format via the explain_format variable on supported versions. In documentation and investigation workflows, specifying FORMAT directly in the statement is usually easier to read and reproduce because the reader knows exactly which output format was requested.

## 2. Preparing an example to read plans

Use a simple example with customers and orders. Assume the tables already contain enough data for different access paths to be meaningful:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    region_code CHAR(2) NOT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE KEY uq_customers_email (email),
    KEY ix_customers_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    KEY ix_orders_customer_created (customer_id, created_at),
    KEY ix_orders_status_created (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
~~~

The CREATE TABLE statements above describe an illustrative structure. When applying this to a real system, use the exact data types, table names, and constraints of your actual schema.

Representative query:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

This query has filter conditions on both tables, a join on customer_id, a date range on orders, and a result ordering requirement. The plan needs to show which table is read first, which index is selected, how many rows are estimated to pass through each step, and whether MySQL must perform an additional sort.

Run the same SQL statement in all three formats to compare:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

Do not assume beforehand whether customers or orders will be read first. The optimizer can change the join order based on statistics, indexes, predicates, and the LIMIT clause. Read the returned plan rather than inferring execution order from the table order written in FROM.

## 3. Reading traditional tabular EXPLAIN

Tabular EXPLAIN output typically includes the following columns:

| Column | Meaning when reading |
|---|---|
| id | Identifier number of the SELECT block. |
| select_type | Type of SELECT block, such as SIMPLE, PRIMARY, SUBQUERY, DERIVED, or UNION. |
| table | Table or object read at this step. Can be a table name, alias, or derived table label. |
| partitions | Partitions considered or used by the optimizer, if the table is partitioned. |
| type | Data access method such as const, eq_ref, ref, range, index, or ALL. |
| possible_keys | Candidate indexes that could be used for the access step. |
| key | Index actually selected. NULL means no index was chosen for that step. |
| key_len | Length of the index prefix used. |
| ref | Value or column compared against key to locate rows. |
| rows | Estimated number of rows to read at this step per access. |
| filtered | Estimated percentage of rows remaining after additional filter conditions. |
| Extra | Additional information about filtering, index reading, joining, or sorting. |

### id and select_type

**id** helps distinguish SELECT blocks in queries with subqueries, derived tables, or UNIONs. For a simple query with only one SELECT, there is usually only one id. Do not interpret id as a strict chronological sequence or absolute execution order of every operation.

**select_type** describes the role of the SELECT block:

- **SIMPLE**: a simple query with no complex subqueries or UNIONs.
- **PRIMARY**: the outermost SELECT of a complex query.
- **SUBQUERY**: an independent subquery in the SELECT list or conditions.
- **DEPENDENT SUBQUERY**: a subquery that depends on values from an outer query and may be executed repeatedly per outer row.
- **DERIVED**: a derived table created from a subquery in FROM.
- **MATERIALIZED**: a subquery materialized into an intermediate structure in certain plans.
- **UNION** and **UNION RESULT**: UNION branches and the step combining their results.

Names and representations may vary depending on query structure and MySQL version. For the simple join query in the example above, rows typically have select_type set to SIMPLE.

### type: data access type

The **type** column is one of the most important signals, but it should not be treated as a mechanical scorecard. You need to evaluate row counts, indexes, predicates, and cost together.

Common values include:

| type | Access method | Interpretation |
|---|---|---|
| system | System table with a single row | Very small, rare case. |
| const | Matches at most one row via PRIMARY or UNIQUE key with a constant condition | Usually very efficient. |
| eq_ref | For each combination of rows from preceding tables, reads exactly one row via PRIMARY/UNIQUE | Common in joins on unique keys. |
| ref | Reads rows matching a value via a non-unique index | Can be good if the number of matching rows is small. |
| ref_or_null | Matches values and NULL via an index | Used for certain conditions with OR IS NULL. |
| range | Reads an index range | Common with BETWEEN, inequality comparisons, or IN. |
| index | Scans the entire index | Reads every index entry; does not mean only one row is read. |
| ALL | Full table scan | Can be reasonable for small tables or queries needing most rows; investigate on large tables. |

MySQL may also display types such as index_merge, fulltext, unique_subquery, or index_subquery. Consult the documentation for your exact version when encountering less common types.

A query using ALL is not automatically a bug. If a table has only a few dozen rows or the condition returns nearly the entire table, a full scan can be cheaper than traversing an index and performing many row lookups. Conversely, ALL on a large table with a condition matching only a few rows is a signal to check indexes and statistics.

### possible_keys, key, and key_len

**possible_keys** lists the indexes the optimizer considered for the access step. **key** indicates the index actually chosen. If possible_keys lists candidate indexes but key is NULL, the optimizer decided not to use those candidates based on its current cost estimates.

**key_len** represents the length of the key portion used, measured in bytes. For composite indexes, this value helps see how much of the index the optimizer used. However, you cannot determine exactly which columns were used from key_len alone without accounting for data types, nullability, character sets, and index structure. Cross-check with SHOW INDEX or FORMAT=JSON.

### rows and filtered

**rows** is the estimated number of rows MySQL needs to examine at this access step. It is neither the final number of rows returned to the application nor an actual runtime measurement.

**filtered** is the estimated percentage of rows remaining after applying additional filter conditions. You can use the product rows × filtered / 100 to roughly visualize the estimated number of rows forwarded from that step, though this is only a rough interpretive aid, not a runtime metric.

For example, if rows is 10,000 and filtered is 5, the optimizer estimates roughly 500 rows remain after that filtering step. If estimates diverge significantly from reality, inspect statistics, histograms, data skew, and predicate structure.

### Extra

Key values to recognize in Extra:

- **Using where**: a WHERE condition is applied to filter rows. This does not automatically mean the query is slow.
- **Using index**: the query can retrieve all needed columns directly from the index (covering index), without reading additional rows from the clustered index for that step.
- **Using index condition**: Index Condition Pushdown (ICP) allows evaluating part of the condition while reading the index, reducing the number of full rows fetched from the table.
- **Using temporary**: MySQL uses a temporary table for a step such as GROUP BY or DISTINCT. A temporary table is not necessarily stored on disk.
- **Using filesort**: MySQL requires an extra sorting step. The name filesort does not guarantee files were written to disk; sorting can occur in memory.
- **Using join buffer**: a join buffer is used for a join strategy; some versions/plans may display hash join.
- **Using where; Using index**: both filters predicates and reads exclusively from the index.

Do not optimize solely by trying to eliminate the words Using filesort or Using temporary. Look at the number of rows involved, data size, query type, and actual execution time. Sorting 50 rows may be negligible; sorting millions of rows is a problem worth measuring.

## 4. Reading FORMAT=JSON

FORMAT=JSON represents the plan as a nested object structure. This is useful when queries have multiple joins, subqueries, derived tables, or multi-stage operations where a flat table struggles to clearly convey parent-child relationships.

Run:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

The JSON output typically has a top-level **query_block** object. Inside, you may encounter:

- **select_id**: corresponds to the SELECT block.
- **cost_info**: estimated cost details.
- **table**: describes a single table access step.
- **nested_loop**: tables combined in a nested-loop structure.
- **ordering_operation**: step handling ORDER BY.
- **grouping_operation**: step handling GROUP BY.
- **materialized_from_subquery**: source of a materialized subquery.
- **attached_subqueries**: subqueries attached to a step in the plan.

Within a table object, important fields can include:

| JSON field | Meaning |
|---|---|
| table_name | Table or alias being read. |
| access_type | Access method corresponding to type in tabular format. |
| possible_keys | Candidate indexes. |
| key | Selected index. |
| used_key_parts | Index parts/columns used. |
| key_length | Length of the key used. |
| ref | Reference values used during index lookup. |
| rows_examined_per_scan | Estimated rows read per scan. |
| rows_produced_per_join | Estimated rows produced after the current join step. |
| filtered | Estimated percentage remaining after filtering. |
| attached_condition | Condition attached to the access step. |
| index_condition | Condition that can be evaluated during index reading, if applicable. |
| using_index | Indicates whether a covering index is used. |
| cost_info | Breakdown of read cost, evaluation cost, and cumulative prefix cost. |

A condensed JSON structure example for recognition:

~~~json
{
  "query_block": {
    "select_id": 1,
    "nested_loop": [
      {
        "table": {
          "table_name": "c",
          "access_type": "ref",
          "possible_keys": ["ix_customers_region"],
          "key": "ix_customers_region",
          "used_key_parts": ["region_code"],
          "rows_examined_per_scan": 120,
          "filtered": 100
        }
      },
      {
        "table": {
          "table_name": "o",
          "access_type": "ref",
          "possible_keys": ["ix_orders_customer_created"],
          "key": "ix_orders_customer_created",
          "used_key_parts": ["customer_id"],
          "rows_examined_per_scan": 8,
          "filtered": 10
        }
      }
    ]
  }
}
~~~

This is an illustrative structural example, not a fixed output from the schema in section 2. Actual row counts and indexes depend on data, statistics, version, and optimizer behavior.

### Understanding nested_loop

In a nested-loop join, MySQL fetches rows from the outer table and uses values from each row to look up matching rows in the inner table. Therefore, the order of elements in nested_loop matters greatly. If the outer table produces too many rows, the inner table access step can be repeated a huge number of times.

For example, suppose customers produces 100,000 rows after filtering; for each customer, MySQL looks up orders. If each lookup reads an average of 20 rows, the total work on the inner table can be massive. When reading JSON, inspect rows_examined_per_scan and rows_produced_per_join, along with the index used for the join condition.

Do not simply add rows_examined_per_scan values together as if every step runs only once. In nested joins, an inner step can be executed repeatedly for each row from the outer step. FORMAT=TREE and EXPLAIN ANALYZE make this structure clearer.

### Reading cost_info

cost_info typically contains estimates such as:

- **read_cost**: estimated cost to read data.
- **eval_cost**: estimated cost to evaluate conditions on rows.
- **prefix_cost**: cumulative cost up to the current step.
- **data_read_per_join**: estimated amount of data read for the join.

These are internal optimizer cost units, not milliseconds. Do not use query_cost or prefix_cost to claim how long a query takes in wall-clock time. Use them to compare plans in the same context, then measure runtime with appropriate tools.

## 5. Reading FORMAT=TREE

FORMAT=TREE presents the plan in terms of iterators. Each branch represents a data retrieval or processing step; lower steps feed input into the step above them.

Run:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

An illustrative output might look like this:

~~~text
-> Limit: 50 row(s)
    -> Sort: o.created_at DESC
        -> Nested loop inner join
            -> Index lookup on c using ix_customers_region
               (region_code='VN')
            -> Filter: (o.status = 'PAID')
                -> Index lookup on o using ix_orders_customer_created
                   (customer_id=c.customer_id)
~~~

This is a conceptual diagram for reading the structure, not a guaranteed output for the example query. The optimizer may choose a different join order, index, range scan, hash join, or sort strategy depending on the data.

When reading TREE:

1. Start from the root iterator at the top to understand the final output required.
2. Follow down into child iterators to see where the data comes from.
3. Identify which iterator filters rows, which joins, and which sorts or aggregates.
4. Check index lookups or table scans at the leaf branches.
5. Inspect row and cost estimates to locate steps likely to generate heavy work.

Common iterators include:

- **Table scan**: reads rows from a table.
- **Index range scan**: reads a range within an index.
- **Index lookup**: finds rows via a key value.
- **Filter**: discards rows that do not satisfy a condition.
- **Nested loop**: pulls rows from one branch and finds matching rows in another.
- **Hash join**: builds and probes a hash structure to combine two row sets.
- **Sort**: orders rows as requested.
- **Aggregate**: computes aggregated results.
- **Limit/Offset**: limits or skips rows in the output.

TREE helps visualize processing order better than the traditional table, especially for joins and nested processing steps. However, it remains an estimated plan when running only EXPLAIN FORMAT=TREE.

## 6. EXPLAIN ANALYZE: comparing estimates with reality

Starting in MySQL 8.0.18, you can use EXPLAIN ANALYZE to execute a SELECT and display actual runtime metrics per iterator. The output format is TREE.

~~~sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

An iterator in EXPLAIN ANALYZE may display information like:

~~~text
(actual time=0.050..1.200 rows=40 loops=100)
~~~

Meaning:

- **actual time**: actual execution time of the iterator from producing the first row to completing the processed rows, typically shown as an average per loop.
- **rows**: actual average number of rows produced by the iterator in a single loop.
- **loops**: number of times the iterator was invoked.

When an iterator loops many times, do not look at rows in isolation while ignoring loops. For instance, rows=40 and loops=100 means the iterator produced an average of 40 rows per call, totaling roughly 4,000 rows across all calls. For timing as well, factor in loops to understand total work. These numbers are measurements from that specific run and can vary due to caching, system load, and data.

Compare estimated rows in EXPLAIN against actual rows in EXPLAIN ANALYZE:

- If estimated is 10 rows but actual is 10,000 rows, the optimizer severely underestimated the workload.
- If estimated is 50,000 rows but actual is 100 rows, the optimizer overestimated the data to process.
- If the discrepancy appears at the first iterator, check table statistics, cardinality, histograms, and filter predicates.
- If initial iterators are accurate but row counts explode after a join, check join relationships, key uniqueness, and data distribution between tables.
- If row counts match expectations but time is high, check I/O, clustered index lookups, sorts, temporary tables, CPU, and resource contention.

EXPLAIN ANALYZE actually runs the SELECT query to completion. The query may read large volumes of data or invoke expensive expressions; limit the scope, choose an appropriate time, and consider running on a staging environment or replica. Do not run EXPLAIN ANALYZE on write statements assuming it only simulates them; this syntax is designed to measure SELECT query execution.

## 7. Reading a join plan step by step

When a query involves multiple tables, analyze it in the following sequence.

**Step 1 — Identify the first table read**

In tabular format, look at the row order and id. In JSON, inspect the nested_loop elements or query_block structure. In TREE, check which child iterator feeds input into the join.

The first table read usually dictates the input row count for subsequent steps. If the filter condition on the outer table is too broad, downstream join steps can end up repeating many times.

**Step 2 — Identify how subsequent tables are accessed**

For each table, check type/access_type, key, key_len, or used_key_parts. For foreign-key joins, check the index on the referencing column in the child table. A suitable index can turn matching row lookups into ref or eq_ref instead of scanning many rows.

**Step 3 — Check row counts through each step**

Compare rows, filtered, rows_produced_per_join, and actual rows. Pay special attention to steps where row counts jump sharply or estimates deviate widely. A join that produces excessive intermediate rows can be the primary bottleneck even if each individual lookup looks fast.

**Step 4 — Check sorts and aggregates**

ORDER BY, GROUP BY, and DISTINCT can introduce sort steps or temporary tables. Check Extra in tabular format, ordering_operation/grouping_operation in JSON, and Sort/Aggregate iterators in TREE. Evaluate whether an index with matching order can be used, while still weighing its benefit against index maintenance cost.

**Step 5 — Check LIMIT**

LIMIT can allow MySQL to stop early when the ordering and access path align. However, if it must read or sort a large set before taking the first 50 rows, LIMIT does not automatically make the query cheap. Inspect TREE to see which step Limit sits above and whether it can stop child iterators early.

## 8. From plan to optimization decision

A plan is evidence for asking questions, not an automatic instruction to create a new index. Use these signals to guide your investigation:

| Signal | Questions to check |
|---|---|
| type = ALL on a large table | Is there an index matching the WHERE or JOIN conditions? Is the condition selective? |
| key = NULL | Is an index missing, incompatible with the leftmost prefix, or higher cost than a full scan? |
| Very large estimated rows | Does the filter condition actually narrow down the data? Is a composite index needed? |
| Estimated rows diverge sharply from actual rows | Are statistics stale? Is data skewed? Would a histogram help? |
| Inner join iterator has very high loops | Is the outer table producing too many rows? Does the inner table have a suitable index lookup? |
| Using temporary or Sort | Is sorting/aggregation processing too many rows? Can an index be leveraged? |
| Using filesort | Is that output order required? Can an index support the ORDER BY? |
| Covering index not used | Is the query fetching extra columns outside the index? Is the index cost worth it? |

A practical workflow:

1. Record the SQL, parameters, latency, execution frequency, and returned row count.
2. Run tabular EXPLAIN to quickly inspect access type, key, rows, and Extra.
3. Run FORMAT=JSON to understand join structure, conditions attached to each step, and cost_info.
4. Run FORMAT=TREE to visualize the iterator pipeline.
5. Use EXPLAIN ANALYZE on an appropriate SELECT to compare estimates with actual runtime metrics.
6. Identify the step generating the most rows or consuming the most time.
7. Check indexes, statistics, histograms, join conditions, and query formulation.
8. Test one change at a time and re-measure using the same parameters and equivalent conditions.

Do not optimize a query solely by reducing rows in one iterator while ignoring loop counts. A 1 ms lookup executed 100,000 times can cost more than a 50 ms scan executed once. Always read rows and loops together.

## 9. Useful commands during investigation

### Viewing the current plan and indexes

~~~sql
EXPLAIN SELECT ...;
SHOW INDEX FROM orders;
ANALYZE TABLE orders;
~~~

ANALYZE TABLE updates statistics; it is not a command to measure query execution time. After refreshing statistics, re-run EXPLAIN and compare.

### Viewing the plan of a statement running on another connection

In some operational scenarios, you can use:

~~~sql
EXPLAIN FOR CONNECTION 123;
~~~

Replace 123 with the connection ID to inspect. Appropriate privileges are required to inspect another connection. A plan can only be retrieved while the connection is executing an explainable statement; if the statement has already finished or is no longer in a suitable state, the command may not return a useful plan. Do not confuse connection ID with Performance Schema THREAD_ID.

### Viewing warnings or extra information after EXPLAIN

You can use SHOW WARNINGS after EXPLAIN when you need to inspect extended information MySQL provides for the statement just analyzed:

~~~sql
EXPLAIN SELECT *
FROM orders
WHERE customer_id = 1001;

SHOW WARNINGS;
~~~

SHOW WARNINGS must be run in the same session immediately after the statement being inspected because it displays warnings from the most recent statements in that session.

## 10. Common mistakes when reading plans

**Seeing type = ALL and concluding the query is broken.** A full scan can be the cheapest option for small tables or queries retrieving most of the data. Consider rows, filtered, cost, and actual runtime.

**Seeing key is not NULL and concluding the query is already optimal.** An index can still scan hundreds of thousands of entries, trigger many clustered index lookups, or fail to support sorting. Check row counts and execution time.

**Confusing rows with the number of rows returned.** rows is the estimated rows read at the access step; filtered describes the remaining percentage. Final row counts depend on subsequent filtering and join steps.

**Treating cost as milliseconds.** Cost is an internal model for the optimizer to compare options. Use EXPLAIN ANALYZE or runtime profiling tools to see actual duration.

**Reading JSON as a flat list.** JSON has a nested structure; nested_loop and query_block represent relationships between steps. Preserve parent-child relationships when reading.

**Treating TREE as execution metrics.** EXPLAIN FORMAT=TREE is still an estimated plan. Only EXPLAIN ANALYZE adds actual time, rows, and loops.

**Ignoring loops in EXPLAIN ANALYZE.** An iterator returning few rows per call but invoked a huge number of times can still be the bottleneck. Evaluate rows, loops, and actual time together.

**Assuming Using filesort always writes to disk.** Filesort is the name of the extra sorting mechanism; it can run in memory. Evaluate the actual scale and execution time.

**Assuming LIMIT 50 always reads only 50 rows.** If a large set must be sorted or filtered before taking the first 50 rows, the work beneath LIMIT can still be substantial.

**Running EXPLAIN ANALYZE on an unbounded query.** The command actually executes the query. A heavy SELECT can consume production resources; understand the query before running it.

## 11. Practice exercises

Use a test schema with customers and orders as in section 2.

1. Run tabular EXPLAIN for the join query. Record table order, type, possible_keys, key, rows, filtered, and Extra.
2. Run EXPLAIN FORMAT=JSON. Locate query_block, nested_loop, table_name, access_type, key, and cost_info. Compare the join order with the tabular result.
3. Run EXPLAIN FORMAT=TREE. Trace the iterators from the data-reading branches through join, sort, and limit.
4. Add or modify experimental indexes on the orders table for the query filtering status and created_at. Re-run all three formats and record the changes.
5. Use EXPLAIN ANALYZE on a scope-limited SELECT query. Compare estimated rows with actual rows and loops at each iterator.
6. Create skewed data distribution for status, for example one dominant status and one very rare status. Compare the plans for each value.
7. Run ANALYZE TABLE and re-check EXPLAIN. Record whether estimates changed and whether the plan improved.
8. Explain why a plan with a non-null key can still be slow and why a plan with ALL is sometimes reasonable.

When finished practicing, restore the test schema or drop the indexes created solely for the exercises.

## 12. EXPLAIN reading checklist

Before proposing an optimization, ensure you have answered:

- How many SELECT blocks and tables participate in the query?
- Which table is read first and what is the join order?
- Which access type does each table use?
- Which indexes are in possible_keys and which index was actually selected?
- How much of a composite index is being used?
- What row volumes do rows and filtered estimate?
- Are conditions applied at the index step or after fetching rows?
- Are there sorts, temporary tables, groupings, or materializations?
- In JSON, what step relationships do nested_loop and query_block show?
- In TREE, which iterator generates heavy input or sits on an expensive execution path?
- Are estimated rows close to actual rows?
- Does any iterator have high loops?
- Does changing an index or statistics improve the overall workload?

Tabular EXPLAIN gives a quick overview, JSON exposes detailed structure and cost, and TREE visualizes the iterator flow. When combining all three with EXPLAIN ANALYZE, you can move from the optimizer's projected plan to actual execution evidence, pinpoint the expensive step, and make well-grounded changes.
