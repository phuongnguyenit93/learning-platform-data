# Reading the Execution Tree, Processing Order, and Branch Relationships

Oracle's execution plan describes how the Optimizer intends to retrieve data, combine row sources, and return results for a SQL statement. When reading a plan, the most important thing is understanding its **tree structure**: each operation is a node, child operations supply input to their parent operation, and the parent operation processes or combines the rows it receives.

A plan is not a list of commands executed sequentially from the top row to the bottom row. The `Id` column is the operation identifier within the plan; its numeric order is not the chronological execution order. Indentation in `DBMS_XPLAN` output represents parent-child relationships. At runtime, row sources typically operate using an iterator model: a parent operation requests rows from its child operations on demand. Consequently, one branch may be read multiple times, one branch may execute only when another produces rows, and some operations can stream rows rather than waiting for all upstream data to be read.

To read an execution plan accurately, combine three perspectives:

- **Structure:** which operation is the parent, which are the children, where a branch ends, and which operation joins branches together.
- **Data flow:** where each operation gets its rows, how it filters or combines them, and which operation receives its output.
- **Actual behavior:** how many times the operation started, how many rows were estimated, and how many rows were actually produced.

## 1. An Execution Plan Is a Row-Source Tree

Oracle represents most execution plans as a tree. An upper node receives input from one or more child nodes. Leaf nodes are where data retrieval begins, such as scanning a table or an index. Upper nodes may filter, sort, join, or aggregate data before returning results.

Abbreviated example:

```text
SELECT STATEMENT
  NESTED LOOPS
    TABLE ACCESS BY INDEX ROWID ORDERS
      INDEX RANGE SCAN ORDERS_STATUS_IX
    TABLE ACCESS BY INDEX ROWID CUSTOMERS
      INDEX UNIQUE SCAN CUSTOMERS_PK
```

You can read the relationships between nodes as follows:

1. `INDEX RANGE SCAN ORDERS_STATUS_IX` retrieves keys and rowids of matching orders.
2. `TABLE ACCESS BY INDEX ROWID ORDERS` uses those rowids to fetch order rows from the table.
3. `NESTED LOOPS` receives an order row and uses the join value to look up the customer in the other branch.
4. `INDEX UNIQUE SCAN CUSTOMERS_PK` locates the customer row by unique key.
5. `TABLE ACCESS BY INDEX ROWID CUSTOMERS` retrieves the corresponding customer data.
6. `NESTED LOOPS` combines rows from both branches and passes the result up to its parent operation.

This illustrates a typical nested loops join. Real-world plans may include additional filters, projections, views, partition iterators, or other operations.

### 1.1. Parent Nodes and Child Nodes

In tree-formatted output, a node with less indentation is usually a parent node; the indented lines underneath are its child branches. For example:

```text
Id  Operation
--  ----------------------------------
 0  SELECT STATEMENT
  1   HASH JOIN
  2    TABLE ACCESS FULL CUSTOMERS
  3    TABLE ACCESS FULL ORDERS
```

`SELECT STATEMENT` is the root node. `HASH JOIN` is the direct input to the root node. The two `TABLE ACCESS FULL` operations are the two inputs to the hash join. Do not assume that `Id = 2` always executes before `Id = 3` just because its number is smaller; you must check the join type and how the operation consumes its inputs.

Another tree may have multiple levels:

```text
SELECT STATEMENT
  HASH JOIN
    NESTED LOOPS
      TABLE ACCESS BY INDEX ROWID ORDERS
        INDEX RANGE SCAN ORDERS_DATE_IX
      TABLE ACCESS BY INDEX ROWID CUSTOMERS
        INDEX UNIQUE SCAN CUSTOMERS_PK
    TABLE ACCESS FULL PRODUCTS
```

Here, `HASH JOIN` has two direct child branches. The first child is itself a `NESTED LOOPS` with two child branches of its own. The second child is a full scan of `PRODUCTS`. You can read the tree level by level:

- The `ORDERS` and `CUSTOMERS` branches produce a join result via nested loops.
- That result becomes one input to the outer hash join.
- The `PRODUCTS` branch is the other input to the outer hash join.
- The hash join produces the result for the root node.

Avoid flattening all operations into a single linear sequence. Preserving the boundaries of each branch helps you identify exactly which operation supplies data to which parent.

### 1.2. `Id` Is Not Execution Order

`Id` identifies an operation line within the plan. IDs are typically assigned via a tree traversal, so they increase as you descend into branches. They are useful for cross-referencing `Predicate Information`, `V$SQL_PLAN`, and runtime metrics.

Avoid these misinterpretations:

- `Id = 1` definitely executes before `Id = 2`.
- The highest `Id` is the first operation to run.
- The operation at the bottom of the output always finishes before all other operations.
- Simply reading from bottom to top reveals the entire runtime sequence.

Reading upward from leaf nodes helps identify data sources and input relationships. However, actual runtime order depends on operation type. Nested loops may invoke the inner branch many times; hash join typically builds a hash table from one input before probing the other; pipelined operations can pass rows as soon as they are ready.

### 1.3. Identifying Parent-Child Relationships in Metadata

In plan views such as `V$SQL_PLAN`, Oracle provides `ID`, `PARENT_ID`, `DEPTH`, and `POSITION` columns to represent tree relationships. You can query a specific cursor:

```sql
SELECT id,
       parent_id,
       depth,
       position,
       operation,
       options,
       object_owner,
       object_name
FROM v$sql_plan
WHERE sql_id = :sql_id
  AND child_number = :child_number
ORDER BY id;
```

`PARENT_ID` identifies the operation's parent node. `DEPTH` indicates depth within the tree. `POSITION` represents the input position of the operation relative to its parent. These columns are useful when analyzing plans via SQL or custom scripts rather than only reading formatted text output.

`V$SQL_PLAN` contains plans associated with cursors in the shared pool. Users need privileges to query dynamic performance views or the corresponding `GV$` views in RAC environments. If the SQL has aged out of the shared pool, or the cursor/child cursor no longer exists, the plan data may no longer be queryable this way.

## 2. Understanding Data Flow Through Operations

An operation receives input, performs its work, and supplies rows to its parent operation. Many operations work via a pull mechanism: the parent node asks a child node for the next row. The child node may in turn request data from its own child nodes.

For example, when reading a table via an index:

```text
TABLE ACCESS BY INDEX ROWID ORDERS
  INDEX RANGE SCAN ORDERS_STATUS_IX
```

`INDEX RANGE SCAN` finds matching keys and produces rowids. `TABLE ACCESS BY INDEX ROWID` uses those rowids to read rows from the table. Output from the index operation serves as input to the table access operation; the table access operation then returns the table columns up to the parent node.

When looking at a parent and child operation, ask:

1. What kind of data does the parent operation need?
2. Does the child branch supply data or rowids, or only evaluate a condition?
3. Can the parent operation process each row immediately, or must it accumulate part or all of the data?
4. Does the child branch run once, or can it be called repeatedly?
5. At which operation are rows eliminated, and at which operation are rows forwarded?

These questions help explain why a branch can consume significant resources even when the final row count returned is very small.

### 2.1. Common Data-Reading Operations

| Operation | Role in Data Flow |
|---|---|
| `TABLE ACCESS FULL` | Reads table blocks via full scan and supplies matching rows to the parent node |
| `INDEX UNIQUE SCAN` | Looks up a unique key, typically returning at most one rowid per lookup |
| `INDEX RANGE SCAN` | Searches a range of keys and returns matching keys/rowids |
| `INDEX FULL SCAN` | Reads the entire index in key order, often able to supply order to the parent node |
| `INDEX FAST FULL SCAN` | Reads all index blocks in a scan-oriented manner, not guaranteeing key order like index full scan |
| `TABLE ACCESS BY INDEX ROWID` | Uses rowids supplied by an index to fetch rows from the table |
| `TABLE ACCESS BY INDEX ROWID BATCHED` | Batches a group of rowids to improve table block access |
| `TABLE ACCESS SAMPLE` | Reads a data sample when requested by a sampling query |
| `EXTERNAL TABLE ACCESS` | Reads data from an external table according to the object's definition |

An index scan branch is often not the final step. It may only supply rowids to a table access. When you see `INDEX RANGE SCAN`, check its parent operation to see how the rowids are used and whether an additional table lookup is required.

### 2.2. Filtering, Sorting, and Transformation Operations

| Operation | Role |
|---|---|
| `FILTER` | Evaluates a condition on incoming rows and forwards only rows that match |
| `SORT ORDER BY` | Sorts rows in the order requested by the SQL statement |
| `SORT GROUP BY` | Sorts or groups data for aggregation |
| `HASH GROUP BY` | Groups rows using a hash structure |
| `SORT UNIQUE` | Eliminates duplicate rows using a sort operation |
| `HASH UNIQUE` | Eliminates duplicate rows using a hash structure |
| `VIEW` | Represents a query block/view used in the plan |
| `WINDOW SORT` | Prepares data ordering for analytic/window functions |
| `COUNT STOPKEY` | Stops reading once the required row limit is reached in certain query forms |
| `UNION-ALL` | Receives data from multiple branches and concatenates their results |
| `CONCATENATION` | Combines branches generated by certain query transformations |

An operation may not output more rows than it receives. Filters typically reduce row counts; sorts generally preserve row counts while changing order; group by typically reduces row counts; union all can sum the row counts across multiple branches.

### 2.3. Parent Operations as Data Consumers

Suppose a plan looks like:

```text
SORT ORDER BY
  FILTER
    TABLE ACCESS FULL ORDERS
```

Data flows from `TABLE ACCESS FULL` up to `FILTER`, and then to `SORT ORDER BY`. The filter evaluates conditions and forwards only matching rows. The sort receives the filtered row set and orders them.

This does not necessarily mean Oracle reads the entire table, writes all intermediate results to disk, and only then begins sorting. Depending on the operation and data volume, Oracle can use memory, temporary segments, or pipelined processing. If a sort exceeds allocated memory, the operation may spill to TEMP; check runtime statistics and workarea indicators to evaluate this.

## 3. Processing Order of JOIN Operations

Joins are where relationships between branches become especially important. A join operation has at least two input branches. The optimizer decides which table or row source participates first, how to combine them, and the order of joins across the tree.

Distinguish between:

- **Join order:** the sequence in which row sources are combined with one another.
- **Join method:** how two inputs are combined, such as nested loops, hash join, or sort merge join.
- **Access path:** how data is retrieved from each row source, such as full scan or index scan.

These three decisions are related but distinct. The same join order can use different join methods; the same join method can receive inputs from either full scans or index scans.

### 3.1. Nested Loops: The Outer Branch Drives Inner Execution Count

Nested loops is suitable when the outer branch returns relatively few rows and the inner branch has an efficient way to look up rows, typically via an index.

Example:

```text
NESTED LOOPS
  TABLE ACCESS BY INDEX ROWID ORDERS
    INDEX RANGE SCAN ORDERS_STATUS_IX
  TABLE ACCESS BY INDEX ROWID CUSTOMERS
    INDEX UNIQUE SCAN CUSTOMERS_PK
```

Conceptual execution:

1. Oracle fetches one row from the outer `ORDERS` branch.
2. Using that row's `CUSTOMER_ID`, Oracle looks up the matching row in the inner `CUSTOMERS` branch.
3. The two rows are joined and passed up to the parent operation.
4. Oracle fetches the next row from the outer branch.
5. The inner lookup repeats for each outer row that needs processing.

If the outer branch returns 100 rows, the inner branch may be started roughly 100 times. If the outer branch returns 500,000 rows, the same inner lookup may repeat hundreds of thousands of times and become expensive.

In nested loops, the first child branch in the tree is normally the **outer row source**, and the second child branch is the **inner row source**. The inner row source is invoked per row or per batch of rows from the outer row source, depending on the execution mechanism and Oracle optimizations.

When reading an actual plan, `Starts` on the inner branch is a key signal. If `Starts` is very high, check the row count from the outer branch, the cost per lookup, and index lookup efficiency. Do not look solely at the overall cost of the nested loops operation.

### 3.2. Hash Join: Build a Hash Table, Then Probe the Other Input

Hash join is generally suited for joining large datasets when the join condition is an equality predicate. Oracle builds a hash structure from one input, then reads the other input and probes the hash table for matching rows.

Example:

```text
HASH JOIN
  TABLE ACCESS FULL CUSTOMERS
  TABLE ACCESS FULL ORDERS
```

In a typical hash join:

1. Oracle reads the build input and creates a hash table keyed on the join key.
2. Oracle reads the probe input.
3. For each probe row, Oracle hashes the join key and looks up matching rows in the hash table.
4. Matching rows are joined and passed to the parent operation.

The optimizer normally considers the smaller input as the build input to minimize memory usage, though the actual choice depends on estimates, join conditions, parallel execution, and other factors. When reading the tree, identify the two direct branches of `HASH JOIN`; the build/probe roles follow the input order in the plan. Do not infer the build branch merely from table names or their order in the `FROM` clause.

Hash joins use workarea memory. If memory is insufficient, the operation can switch to multipass partitioning and use TEMP. When a large hash join is slow, inspect actual rows, input sizes, workarea usage, TEMP usage, and parallelism rather than simply concluding that a full scan is bad.

### 3.3. Sort Merge Join: Combining Two Sorted Streams

Sort merge join combines two inputs ordered by the join key. If the inputs are not already sorted appropriately, the plan may include sort operations on one or both branches.

```text
MERGE JOIN
  SORT JOIN
    TABLE ACCESS FULL CUSTOMERS
  SORT JOIN
    TABLE ACCESS FULL ORDERS
```

Conceptually:

1. Both inputs are sorted by the join key if necessary.
2. Oracle reads both streams in key order.
3. Equal keys are joined; as keys advance, the corresponding stream moves forward.
4. Results are passed up to the parent operation.

If an input already arrives in the required order from an index or an earlier operation, Oracle can avoid one or both sort steps. Conversely, large sorts can consume substantial CPU, memory, and TEMP.

### 3.4. Comparing the Three Join Methods

| Join Method | Mechanism | Usually Suitable When | Signals to Watch |
|---|---|---|---|
| Nested loops | Fetch outer rows and repeatedly look up inner | Outer is small; inner lookup is selective and efficient | Inner `Starts`, outer rows, logical reads |
| Hash join | Build hash table from one input, probe with the other | Large datasets, equality join, scans can be efficient | Build/probe inputs, memory, TEMP, actual rows |
| Sort merge join | Sort both streams then merge by key | Inputs are pre-sorted or ordered processing is beneficial | Sort operations, TEMP, input ordering |

No single join method is universally best. A nested loops join over a few rows with good index lookups can be extremely fast. A nested loops join with millions of inner starts can be very slow. Hash join can excel on large datasets but consume TEMP if workarea memory is tight. Sort merge join can fit pre-sorted inputs well, though adding new sorts increases cost.

### 3.5. Join Order with Three or More Tables

Suppose a SQL query joins `CUSTOMERS`, `ORDERS`, and `ORDER_ITEMS`. The optimizer might choose:

```text
          HASH JOIN
          /       \
     JOIN A        ORDER_ITEMS
      /  \
 CUSTOMERS ORDERS
```

Or:

```text
          HASH JOIN
          /       \
   JOIN B          CUSTOMERS
    /  \
 ORDERS ORDER_ITEMS
```

The two trees mean different things. In the first tree, `CUSTOMERS` and `ORDERS` are joined first, and that result is then joined with `ORDER_ITEMS`. In the second tree, `ORDERS` and `ORDER_ITEMS` are joined first and then joined with `CUSTOMERS`.

Join order affects intermediate result sizes. If a filter sharply reduces `ORDERS`, joining `ORDERS` with `ORDER_ITEMS` early may yield a smaller intermediate set for later steps. However, if a branch has poor selectivity or inaccurate estimates, the chosen order may be suboptimal.

Do not read join order from the table order in `FROM`. The optimizer can reorder joins within semantic limits based on cost and query constraints.

## 4. Which Operation Is a Predicate Attached To?

An execution plan usually includes a `Predicate Information` section. This section ties filter or access conditions to an operation `Id`. It is the bridge between the SQL text and each node in the tree.

Two common predicate types are:

- **Access predicate:** a condition used to locate the data region or keys to access, such as defining an index key range.
- **Filter predicate:** a condition applied to test rows after the operation has retrieved rows or candidate rows.

Example:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PENDING'
  AND o.order_date >= DATE '2026-01-01';
```

Suppose the abbreviated plan is:

```text
Id  Operation                                      Name
--  ---------------------------------------------  -------------------
 0  SELECT STATEMENT
  1   NESTED LOOPS
  2    TABLE ACCESS BY INDEX ROWID BATCHED         ORDERS
  3     INDEX RANGE SCAN                           ORDERS_STATUS_IX
  4    TABLE ACCESS BY INDEX ROWID                 CUSTOMERS
  5     INDEX UNIQUE SCAN                          CUSTOMERS_PK
```

The predicate section may appear as:

```text
Predicate Information (identified by operation id):
---------------------------------------------------
  3 - access("O"."ORDER_STATUS"='PENDING')
  2 - filter("O"."ORDER_DATE">=DATE '2026-01-01')
  5 - access("C"."CUSTOMER_ID"="O"."CUSTOMER_ID")
```

Interpretation:

- Operation 3 uses `ORDER_STATUS` to locate keys in the index.
- Operation 2 checks `ORDER_DATE` on order rows fetched from the table.
- Operation 5 uses `CUSTOMER_ID` to locate the customer in the primary-key index.
- Operation 1 combines rows from the order and customer branches.

This example shows how one `WHERE` condition can be handled at the index operation while another is applied after reading the table. Where a predicate is placed determines how many rowids must be read, how many table blocks are visited, and how many rows flow up to the join.

### 4.1. Predicates Do Not Necessarily Stay Where Written in SQL

The optimizer can push predicates deeper into the tree (*predicate pushdown*) to reduce intermediate data. A condition in an outer query block can be pushed into a view or subquery if that transformation preserves semantics.

For example, a query filtering a view can be transformed so the filter applies directly to the underlying base table. In that case, the plan may no longer show a separate `VIEW` step as someone reading the original SQL might expect.

Conversely, some conditions must be applied after a join or aggregation to preserve exact semantics. You cannot conclude a predicate is misplaced simply because its plan position differs from its textual position in the SQL.

### 4.2. Distinguishing Join Conditions from Filter Conditions

Join conditions typically compare columns from two row sources, for example:

```sql
o.customer_id = c.customer_id
```

Filter conditions typically restrict rows by a value or range of values:

```sql
o.order_status = 'PENDING'
o.order_date >= DATE '2026-01-01'
```

In `Predicate Information`, join conditions can appear under `access()` or `filter()` depending on the operation and join method. Do not assume that every `access()` is an index predicate, or that every join condition appears on a single join operation. Read the operation type, aliases, child branches, and specific predicates together.

### 4.3. Partition Pruning in the Execution Tree

For partitioned tables, a plan may contain operations such as `PARTITION RANGE ITERATOR`, `PARTITION RANGE SINGLE`, `PARTITION RANGE ALL`, or the equivalent operation for the partitioning type. The `PSTART` and `PSTOP` columns indicate the range of partitions accessed as shown in the plan.

Abbreviated example:

```text
PARTITION RANGE SINGLE
  TABLE ACCESS FULL SALES
```

The partition iterator determines which partition(s) to read; the table access reads data within the corresponding partition(s). If the plan shows `PARTITION RANGE ALL`, many or all partitions may be visited. Check predicates on the partition key and `PSTART`/`PSTOP` values to confirm whether pruning occurs as expected.

With dynamic pruning, the partition range may be determined at runtime rather than fixed completely at parse time. Some plans display values such as `KEY` in `PSTART`/`PSTOP`. That does not automatically mean pruning failed; inspect runtime behavior and actual bind conditions.

## 5. Subquery, View, and Query Transformation Branches

SQL statements can contain multiple query blocks: subqueries in `WHERE`, inline views in `FROM`, CTEs (`WITH`), scalar subqueries, and branches of set operators. The optimizer can keep query blocks separate or transform them to build a better plan.

### 5.1. Inline Views and the VIEW Operation

Example:

```sql
SELECT x.customer_id,
       x.order_count
FROM (
    SELECT customer_id,
           COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
WHERE x.order_count > 5;
```

The plan may include `VIEW`, `HASH GROUP BY`, or other operations corresponding to the inner query block. However, the optimizer can also merge views or transform query blocks to filter and aggregate more efficiently. Thus, parentheses in SQL do not guarantee a separate `VIEW` node in the plan.

`VIEW` is a logical row source in the plan, not proof that Oracle created a physical temporary table. If data materialization is required, the plan will show temporary-table or related operations. Always read the actual operations.

### 5.2. Subqueries in EXISTS or IN Conditions

Example:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

The optimizer can unnest a correlated subquery into a semi join. The plan may show `NESTED LOOPS SEMI`, `HASH JOIN SEMI`, or a similar operation. In that case, the subquery does not necessarily run as a standalone query for every customer row; it becomes a join branch in the tree.

For `NOT EXISTS` or certain forms of `NOT IN`, Oracle can use an anti join, such as `HASH JOIN ANTI` or `NESTED LOOPS ANTI`, when the transformation preserves semantics. Pay special attention to `NULL` semantics in `NOT IN`; do not mechanically rewrite it to `NOT EXISTS` without verifying equivalence.

### 5.3. Scalar Subqueries

A scalar subquery returns a single value per evaluation context. Example:

```sql
SELECT c.customer_id,
       (SELECT MAX(o.order_date)
        FROM orders o
        WHERE o.customer_id = c.customer_id) AS last_order_date
FROM customers c;
```

The plan may contain a `SCALAR SUBQUERY` operation or child operations associated with the inner query block. A correlated scalar subquery can execute many times, though Oracle may apply caching or transformations depending on the case. Check `Starts`, actual rows, and related query blocks to determine actual behavior.

If a subquery branch has `Starts` close to the outer branch's row count, evaluate the cost per execution. A subquery can be very cheap with an efficient index lookup, or become a bottleneck if each invocation scans a large amount of data.

### 5.4. UNION ALL and Independent Branches

With set operators, plans typically have a parent operation like `UNION-ALL` and multiple child branches:

```text
UNION-ALL
  TABLE ACCESS FULL CURRENT_ORDERS
  TABLE ACCESS FULL ARCHIVED_ORDERS
```

Each branch supplies a set of rows. `UNION-ALL` concatenates rows from the branches while keeping duplicates. With `UNION`, Oracle must deduplicate, so the plan may add `SORT UNIQUE` or `HASH UNIQUE`.

Do not assume branches always execute sequentially in ID order. Execution order and concurrency depend on the operation, parallel execution, and how results are consumed. Identify which branch has predicates, which branch scans a table, and which branch might be eliminated by conditions or transformations.

### 5.5. Query Blocks and Aliases

When a plan is complex, query block names and aliases help pinpoint which part of the SQL an operation belongs to. You can instruct `DBMS_XPLAN` to display alias and query block details:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALL +ALIAS +OUTLINE +PREDICATE'
    )
);
```

`ALIAS` maps objects in the plan back to aliases in the SQL statement. `OUTLINE` shows hints corresponding to the plan in certain output formats, which is helpful when investigating optimizer decisions. Do not extract an outline and blindly apply it as a permanent hint set without understanding why the original plan occurred.

## 6. Pipelined vs. Buffering Operations

Not all operations consume data the same way. Some operations can return rows early; others must read and buffer part or all of their input before returning results.

| Operation Type | Typical Behavior | Implication When Reading a Plan |
|---|---|---|
| Index lookup | Can return keys/rowids as found | May be invoked many times by nested loops |
| Filter | Tests each row as it arrives | Can discard rows early before parent operations |
| Nested loops | Fetches outer row then requests inner | Inner branch may have high `Starts` |
| Hash join | Builds hash table then probes | Build input must be processed before corresponding probe phase |
| Sort | Needs to order the dataset | May buffer data and spill to TEMP |
| Group by | Aggregates by key | May require hashing/sorting and maintaining aggregate state |
| UNION ALL | Receives rows from multiple branches | Can pass rows from multiple branches to parent node |
| COUNT STOPKEY | Stops when limit is reached | May avoid reading the entire child branch |

### 6.1. Pipelining

Pipelining means an operation can pass a row up to its parent as soon as that row is ready, rather than waiting for the entire branch to finish. This enables queries to start returning rows early.

For instance, an index range scan can produce a rowid, table access fetches the row, filter evaluates it, and an upper operation receives the row. This chain can progress row by row or in batches depending on the operation and execution mode.

Not the entire tree is pipelined. Sorts, hash join build phases, group bys, and certain transformations must buffer data. If an operation has to write intermediate data to TEMP, latency and I/O cost can increase significantly.

### 6.2. STOPKEY and Row Limits

Queries with `ROWNUM`, `FETCH FIRST n ROWS ONLY`, or similar limits can produce a `COUNT STOPKEY` or related operation. Once enough rows are collected, Oracle can stop requesting more data from the child branch.

This can allow a branch to read only a portion of the data. However, if the query specifies `ORDER BY` on a column without an access path providing that order, Oracle may still have to read and sort many rows before determining the top N. Read both the sort and stopkey operations to understand the true workload.

## 7. Reading Cost, Cardinality, and Starts

Execution plans typically show columns like `Rows`, `Bytes`, `Cost`, `%CPU`, `Time`, or runtime columns when using `ALLSTATS LAST`. These metrics have distinct meanings.

| Metric | Meaning |
|---|---|
| `Rows` / `E-Rows` | Number of rows the optimizer estimates the operation will return |
| `Bytes` | Estimated data volume |
| `Cost` | Relative cost calculated by the optimizer for the operation/subtree |
| `%CPU` | CPU component of cost in the optimizer model |
| `Time` | Estimated time displayed in the plan, not a runtime SLA |
| `Starts` | Number of times the operation started in runtime statistics |
| `A-Rows` | Actual rows returned by the operation in the profiled execution |
| `Buffers` | Recorded logical reads |
| `Reads` | Recorded physical reads, if any |
| `A-Time` | Actual time recorded for the operation in the plan output |

### 7.1. Cost Is Not Runtime

`Cost` is a relative figure within the cost-based optimizer model. You cannot read `Cost = 100` and conclude the query takes 100 milliseconds. Cost helps the optimizer compare alternatives within the same estimation context.

A parent operation's cost normally includes the cost of its child operations in the subtree. Do not sum the costs of every row in the plan to get a total cost; that double-counts costs. Read the root node's cost for the overall plan estimate, and inspect child nodes to see where cost accumulates.

### 7.2. E-Rows and A-Rows

`E-Rows` is estimated cardinality; `A-Rows` is actual row count. If the two diverge sharply, the optimizer may have misjudged selectivity, data distribution, or branch correlation.

Example:

```text
Operation                         Starts   E-Rows   A-Rows
--------------------------------  -------  -------  -------
TABLE ACCESS FULL ORDERS                1    10000   900000
INDEX UNIQUE SCAN CUSTOMERS_PK     900000        1   900000
```

If `ORDERS` actually returns 900,000 rows while the optimizer estimated only 10,000, upper join operations may be chosen based on an overly small assumption. The inner branch of nested loops can also end up being invoked hundreds of thousands of times.

For operations with `Starts` greater than 1, read `E-Rows` alongside `Starts`. Estimated cardinality typically represents rows per start, whereas `A-Rows` in runtime output is cumulative across all starts. Thus, when comparing, you often need to compare `A-Rows / Starts` against `E-Rows`, while keeping operation context and output version in mind.

For example, an inner index lookup with `E-Rows = 1`, `Starts = 50,000`, and `A-Rows = 50,000` can be completely accurate: each lookup returned one row on average. Comparing `E-Rows = 1` directly with `A-Rows = 50,000` would mistakenly suggest a severe cardinality error.

### 7.3. Starts Helps Spot Repeatedly Executed Branches

`Starts` is especially useful with nested loops, scalar subqueries, and branches invoked per row. A high `Starts` count is not inherently a problem; if each invocation is very cheap and the outer row count is appropriate, it can be a good plan choice.

Evaluate together:

- Number of operation starts.
- Actual rows per start.
- Buffers read.
- Actual elapsed time.
- Row count from the outer branch.
- Predicates and access path used in the inner branch.

If an inner operation is invoked too many times and reads many blocks per invocation, revisit join order, indexes, predicates, or cardinality estimates.

## 8. Viewing Execution Plans with DBMS_XPLAN

`DBMS_XPLAN` is the standard package for displaying execution plans in a readable format. You can display plans stored from `EXPLAIN PLAN`, cursor plans in the shared pool, or other supported plan sources.

### 8.1. EXPLAIN PLAN and DISPLAY

Example:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date
FROM app.orders
WHERE order_status = 'PENDING';
```

Display the newly explained plan:

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` asks the optimizer to generate a plan in the explain context. That plan is useful for inspecting the projected structure, but it may differ from the cursor plan that actually executes due to bind values, bind peeking, session parameters, privileges, schema resolution, adaptive cursor sharing, statistics, or runtime factors.

### 8.2. DISPLAY_CURSOR to View the Actual Cursor Plan

After the SQL statement runs, you can inspect the cursor plan in the shared pool:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALL +PREDICATE +ALIAS +NOTE'
    )
);
```

If you are in the same session and want to view the most recently executed cursor, you can run:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL'
    )
);
```

`SQL_ID` identifies the SQL statement in the shared pool; `CHILD_NUMBER` identifies the specific child cursor. One SQL statement can have multiple child cursors due to bind metadata, optimizer environment, or other factors. When investigating a plan, make sure you inspect the exact child cursor of the execution under analysis.

### 8.3. Gathering Actual Row-Source Statistics

To see actual rows and start counts, instruct Oracle to gather runtime plan statistics. You can add a hint to the SQL statement being measured:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_status = 'PENDING';
```

After the statement finishes, in the same session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +NOTE'
    )
);
```

`ALLSTATS LAST` requests displaying runtime statistics for the last recorded execution. If runtime statistics collection was not enabled, actual columns may contain no data. You can set `STATISTICS_LEVEL = ALL` in a session for investigation, though be mindful of overhead and restore the setting afterward.

### 8.4. Useful Format Options

| Format Option | Purpose |
|---|---|
| `BASIC` | Minimal output |
| `TYPICAL` | Standard output containing key plan details |
| `ALL` | Displays more comprehensive information |
| `ALLSTATS LAST` | Adds runtime statistics for the most recent execution if available |
| `+PREDICATE` | Displays access/filter predicates |
| `+ALIAS` | Displays aliases and object mapping details |
| `+NOTE` | Displays notes related to the plan |
| `+OUTLINE` | Displays outline hints associated with the plan |
| `+PARTITION` | Displays partition details when applicable |
| `+ADAPTIVE` | Adds adaptive plan details when supported |
| `+PROJECTION` | Displays projected expressions/columns per operation |

You do not need to enable every format option on every read. Start with `TYPICAL` or `ALLSTATS LAST +PREDICATE`, then add `ALIAS`, `PARTITION`, `OUTLINE`, or `ADAPTIVE` as your investigation requires.

## 9. Reading a Complete Plan Example End-to-End

Suppose an application needs pending orders along with customer names:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM app.orders o
JOIN app.customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PENDING'
  AND o.order_date >= DATE '2026-01-01';
```

Assume the abbreviated output is as follows:

```text
--------------------------------------------------------------------------------
| Id | Operation                               | Name              | E-Rows |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT                        |                   |        |
|  1 |  NESTED LOOPS                           |                   |    120 |
|  2 |   TABLE ACCESS BY INDEX ROWID BATCHED   | ORDERS            |    120 |
|  3 |    INDEX RANGE SCAN                     | ORDERS_STATUS_IX  |    800 |
|  4 |   TABLE ACCESS BY INDEX ROWID           | CUSTOMERS         |      1 |
|  5 |    INDEX UNIQUE SCAN                    | CUSTOMERS_PK      |      1 |
--------------------------------------------------------------------------------

Predicate Information:
  3 - access("O"."ORDER_STATUS"='PENDING')
  2 - filter("O"."ORDER_DATE">=DATE '2026-01-01')
  5 - access("C"."CUSTOMER_ID"="O"."CUSTOMER_ID")
```

Structural reading:

1. `SELECT STATEMENT` is the root node, receiving final output from nested loops.
2. `NESTED LOOPS` has two direct branches: the orders branch and the customers branch.
3. The orders branch consists of an index range scan and a table access. The index locates orders with status `PENDING`; the table access fetches rows and filters further by date.
4. The customers branch consists of an index unique scan and a table access. For each order to join, the index locates the customer by `CUSTOMER_ID`, and the table access fetches `CUSTOMER_NAME`.
5. Nested loops pairs order rows with customer rows and forwards the result to the root node.

Data flow reading:

- The orders branch is the outer row source in this nested loops join.
- The customers branch is the inner row source, looked up by the order row's `CUSTOMER_ID`.
- `Starts` on the customers branch should roughly align with the number of order rows actually passed to the join.
- If the date predicate discards most rows after reading the table, check how many rowids and table blocks were visited prior to filtering.

Performance reading:

- If the index range scan returns 800 rows while table access forwards only 120 rows, the date condition discards a notable share after the table visit.
- If there are actually hundreds of thousands of pending orders while `E-Rows` is only 120, nested loops may have been chosen due to a severe underestimate.
- If the customers branch has `Starts = 120`, `E-Rows = 1`, and `A-Rows = 120`, that can be normal behavior: each lookup returned one customer.
- If `Starts` on the customers branch is much higher than 120, inspect runtime details, actual executions, and related transformations.

This example illustrates how to read a plan. A real plan might use a hash join, full scan, a different index, or push predicates to other operations depending on statistics, bind values, data size, and environment.

## 10. Adaptive Plans and Alternative Branches

In certain cases, Oracle can generate an adaptive plan to defer a decision until more runtime information is available. For example, the optimizer may keep alternative join methods or execution branches, then decide which branch is appropriate based on observed data volume.

When displaying an adaptive plan, the output can show both active operations and alternative operations that were not taken during that run. Therefore, do not sum costs or assume all displayed branches executed. Use adaptive-aware formatting, read the plan notes, and compare against the cursor's runtime statistics.

An adaptive plan also does not mean Oracle automatically fixes every misestimate. Adaptive decisions apply only to supported scenarios and structures. If cardinality is wrong in another branch or the SQL picked an unsuitable child cursor, you still need to investigate statistics, bind values, and the actual plan.

## 11. Reading Branches in Parallel Execution

With parallel execution, plans can contain operations such as:

- `PX COORDINATOR`
- `PX SEND` and `PX RECEIVE`
- `PX BLOCK ITERATOR`
- `PX PARTITION RANGE`
- `PX SEND HASH`, `PX SEND BROADCAST`, or other distribution methods

These operations describe work distribution and data transfer between the query coordinator and parallel execution servers. A branch may run concurrently across multiple processes; therefore, you cannot read the whole plan as a single session running sequentially from one node to the next.

Abbreviated example:

```text
PX COORDINATOR
  PX SEND QC (RANDOM)
    HASH GROUP BY
      PX RECEIVE
        PX SEND HASH
          HASH JOIN
            PX BLOCK ITERATOR
              TABLE ACCESS FULL SALES
            PX BLOCK ITERATOR
              TABLE ACCESS FULL PRODUCTS
```

Conceptual reading:

1. Parallel servers read blocks of `SALES` and `PRODUCTS` by assigned ranges.
2. Data is distributed across processes by hash or the specified distribution method.
3. Processes perform the join and group by across parallel branches.
4. Results are sent back to the query coordinator to return to the client.

`PX SEND`/`PX RECEIVE` operations mark data exchange boundaries between process sets. `PX SEND HASH` typically distributes rows by hashing one or more keys; `PX SEND BROADCAST` sends rows to multiple processes; `PX SEND QC` sends results back to the query coordinator. Exact semantics depend on `IN-OUT`, `PQ Distrib`, and the specific plan structure.

When reading a parallel plan, determine:

- Which branch is the producer and which is the consumer.
- Whether data is distributed via hash, broadcast, or random.
- Whether there is a large data redistribution step between processes.
- Whether data skew causes one process to receive far more data than others.
- Whether sort, hash join, or group by operations spill to TEMP in individual processes.
- Whether the actual Degree of Parallelism matches expectations.

A parallel plan can reduce elapsed time for suitable workloads, but it also introduces process startup overhead, data exchange cost, and resource contention. Do not assume that seeing `PX` automatically makes a query faster.

## 12. Distinguishing Estimated Plans from Actual Plans

A plan displayed from `EXPLAIN PLAN` is an estimated plan computed in the explain context. A plan from `DISPLAY_CURSOR` is attached to an actual cursor. When troubleshooting incidents, prioritize the executed cursor's plan and runtime statistics if available.

Reasons the two plans can differ include:

- Different bind values and bind peeking.
- Adaptive cursor sharing creating multiple child cursors.
- Different session parameters or optimizer environments.
- Different schemas, privileges, synonyms, or object resolution.
- Statistics changing between explain time and execution time.
- An adaptive plan choosing a different branch once runtime information is available.
- SQL being rewritten or executed in a different context.

For a meaningful comparison, capture the SQL text, SQL ID, child number, plan hash value, relevant bind values, optimizer environment, and when statistics were gathered. Comparing two plan outputs without this context can lead to wrong conclusions.

## 13. Workflow for Reading a Complex Execution Plan

When encountering a long plan with many branches, read it in passes so you do not mix up structure, data flow, and performance.

### Step 1: Identify the Root Node and SQL Statement Type

Locate `SELECT STATEMENT`, `INSERT STATEMENT`, `UPDATE STATEMENT`, `DELETE STATEMENT`, or `MERGE STATEMENT`. The root node identifies the overall operation type. For DML, the plan can include data-reading operations, joins, and data-writing operations.

### Step 2: Divide the Tree into Direct Child Branches

Locate the major operations directly beneath the root node. For each operation, identify its direct child branches via indentation or `PARENT_ID`. Do not dive deep into every line immediately.

### Step 3: Identify Each Branch's Row Source

Find leaf operations such as table access, index access, partition iterator, remote access, or external table access. Note which table/index is read, by which access path, and with which predicates.

### Step 4: Read Operations That Combine Branches

Identify nested loops, hash joins, merge joins, union all, group by, or sort operations. For each operation, trace how data from its child branches is consumed and forwarded.

### Step 5: Map Predicates to the Right Operations

Read `Predicate Information` and identify access predicates, filter predicates, and join conditions. Match operation IDs to the tree to see where conditions reduce data volume.

### Step 6: Check Cardinality and Execution Counts

Compare `E-Rows`, `A-Rows`, and `Starts`. For operations invoked multiple times, inspect average rows per start. Spot branches with large discrepancies or high execution counts.

### Step 7: Inspect Runtime Resource Usage

Check `Buffers`, `Reads`, `A-Time`, TEMP, workareas, and parallel distribution if present. Cost is an estimate; runtime statistics reveal the actual activity of the measured run.

### Step 8: Check Factors Outside the Tree

If the plan is still hard to explain, inspect bind values, child cursors, optimizer environment, statistics, partition pruning, adaptive plans, and note/outline sections.

## 14. Common Plan Reading Mistakes

| Misconception | Correct Understanding |
|---|---|
| Reading ascending `Id` as execution order | `Id` is an identifier; you must read parent-child relationships and operation types |
| Always reading bottom-to-top gives full runtime order | Bottom-up shows data sources; nested loops, hash joins, and pipelining consume inputs differently |
| The first table in `FROM` is always read first | The optimizer can reorder joins within semantic bounds |
| Every child operation executes only once | Inner branches, scalar subqueries, or repeatedly called operations can have high `Starts` |
| `INDEX RANGE SCAN` is the final result | Usually requires a table access by rowid or parent operation to build result rows |
| Cost is milliseconds | Cost is a relative metric in the optimizer model |
| `E-Rows = 1`, `A-Rows = 100000` is definitely off by 100,000x | If `Starts = 100000`, each start may be returning exactly one row |
| Every branch shown in an adaptive plan executed | Some branches are alternatives; determine which branch was active |
| Every operation in a parallel plan runs sequentially | Branches can execute concurrently across processes and exchange data |
| Full table scans are always bad | Scans can be appropriate when reading most of a table or a small table |
| Index scans are always good | Repeated index lookups or poor clustering factors can be costly |

## 15. Practice Exercise: Reading an Execution Tree

Suppose you have three tables:

- `CUSTOMERS(customer_id, customer_name, region_id)`
- `ORDERS(order_id, customer_id, order_date, order_status)`
- `ORDER_ITEMS(order_id, product_id, quantity, unit_price)`

An application needs total order value by region for paid orders within a date range:

```sql
SELECT c.region_id,
       SUM(oi.quantity * oi.unit_price) AS total_amount
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
GROUP BY c.region_id;
```

When given a plan, determine:

1. Which branch reads `ORDERS`, which reads `ORDER_ITEMS`, and which reads `CUSTOMERS`?
2. At which operation are `ORDER_STATUS` and `ORDER_DATE` applied?
3. Did the optimizer join `ORDERS` with `ORDER_ITEMS` first, or `ORDERS` with `CUSTOMERS` first?
4. Is the join method at each level nested loops, hash join, or merge join?
5. Which branch is outer and which is inner if nested loops are used?
6. If a hash join is used, how are the build and probe branches represented in the plan?
7. Is `GROUP BY` performed using sort or hash aggregation?
8. Are any sort or hash operations at risk of spilling to TEMP?
9. At which operation do `E-Rows` and `A-Rows` diverge?
10. Does `Starts` indicate a branch being executed repeatedly?

There is no single mandatory execution plan for this SQL query. The result depends on data, statistics, indexes, bind values, optimizer settings, and system resources. The goal of the exercise is to explain the actual tree Oracle chose rather than guessing a fixed sequence of operations.

## 16. How to Present a Plan in an Investigation Document

When reporting a plan to others, structure it so readers can understand quickly:

1. **Plan identity:** SQL ID, child number, plan hash value, and capture timestamp.
2. **Overall structure:** root node, major join/union/group-by branches, and each branch's data source.
3. **Processing flow:** which branch feeds which, join order, and join methods.
4. **Predicate placement:** which operations perform access and filter conditions.
5. **Estimates vs. actuals:** E-Rows, A-Rows, Starts, and where discrepancies begin.
6. **Resource usage:** logical reads, physical reads, elapsed time, TEMP, and parallel exchanges if applicable.
7. **Root cause explanation:** pinpoint which operation or misestimate drives the main cost, backed by runtime evidence.

A good description does not merely say "the plan has a full scan" or "the plan uses nested loops." It explains why that branch was chosen, how data flows through the operations, which branch runs repeatedly, and whether runtime numbers confirm the optimizer's assumptions.

Reading execution trees properly moves you from recognizing operation names to understanding the mechanics of data processing. Once you identify parent-child relationships, data flow, join order, predicates, and runtime starts, you can pinpoint the expensive branch accurately and choose the right direction for investigation.
