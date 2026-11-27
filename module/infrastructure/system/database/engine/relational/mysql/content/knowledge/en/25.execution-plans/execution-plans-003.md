# Reading Execution Trees, Loops, and Branch Relationships

An execution plan describes how MySQL executes a query: which table it reads first, which index it uses, where it filters, how it joins row sets, and whether it needs to sort or materialize intermediate data. With `EXPLAIN FORMAT=TREE`, the plan is presented as an iterator tree. Each node is a processing step; a parent node pulls data from its child nodes and produces results for the step above it.

Reading an execution tree properly goes beyond spotting a line that says `Index lookup`. You need to follow the data flow from leaves to root, distinguish the outer and inner branches of a nested-loop join, recognize which branch executes repeatedly, and compare estimated row counts against actual row counts. These details help pinpoint exactly what makes a query slow: an overly wide scan, a filter discarding too many rows, an inner lookup repeating thousands of times, or a sort/materialization processing a huge dataset.

In the `DATABASE_MYSQL` module, reading execution trees is the bridge between index design and query optimization. This lesson uses `EXPLAIN FORMAT=TREE` to read structure, `EXPLAIN ANALYZE` to observe runtime metrics, and JOIN examples to explain relationships among branches in a plan.

## 1. What is an execution plan?

SQL describes **the result to retrieve**. The optimizer chooses an execution strategy to produce that result. The same SQL statement can have multiple valid execution plans, for example:

- Scanning the entire table and then filtering.
- Looking up an index and then jumping back to the clustered index.
- Reading a range of a composite index.
- Reading table A first and looking up table B row by row.
- Using a hash join to combine two datasets.
- Sorting data before applying LIMIT.
- Creating a temporary table to materialize a derived table or CTE.

An execution plan reflects the optimizer's choice based on SQL, schema, indexes, statistics, and execution rules/costs. The plan can change when data, statistics, indexes, MySQL version, or configuration changes.

### A plan is not a list of SQL clauses in written order

The table order in `FROM` is not necessarily the order in which MySQL reads tables. The optimizer can reorder joins if it estimates a lower cost. Similarly, a predicate in `WHERE` can be pushed down closer to where data is read, rather than waiting until the end of the query to filter.

Therefore, read an execution plan as a graph of iterators and data flows, not as an indented copy of the SQL statement.

## 2. Two common formats: tabular and TREE

### Tabular EXPLAIN

The illustrative commands in this section use the `customers` table created in section 5; prepare the schema and fixtures before running them.

```sql
EXPLAIN
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

The tabular format displays each table or query block as a row. Columns like `type`, `possible_keys`, `key`, `rows`, `filtered`, and `Extra` are useful for checking overall access paths, but relationships across multiple iterators or JOIN branches are not always intuitive.

### EXPLAIN FORMAT=TREE

```sql
EXPLAIN FORMAT=TREE
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

TREE displays parent-child iterators using indentation. This layout clarifies which node consumes results from which node, which join algorithm is used, and where sort/filter/aggregate steps sit.

`FORMAT=TREE` has been available since MySQL 8.0.16. Specific output details and node names can vary by version, query type, and optimizer choices.

### EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT customer_id, email
FROM customers
WHERE email = 'linh@example.test';
```

`EXPLAIN ANALYZE` executes the SELECT statement and returns an iterator tree with actual runtime metrics such as time, row counts, and loop counts. This feature has been available since MySQL 8.0.18. Because the query is genuinely executed, be cautious with SELECTs that scan large tables, JOINs with high fan-out, or queries causing load on production.

## 3. How to read tree structure: parent nodes receive data from child nodes

Conceptual tree example:

```text
-> Limit: 20 row(s)
    -> Sort: created_at DESC
        -> Filter: status = 'PAID'
            -> Index range scan on orders
```

Read by parent-child relationship:

- `Index range scan` is the leaf node: it reads entries within the index range.
- `Filter` pulls rows from its child node and emits only rows satisfying the condition.
- `Sort` takes data from Filter and sorts it by `created_at`.
- `Limit` receives the sorted data and returns at most 20 rows.

Data flows **from bottom to top**: leaf nodes produce rows, parent nodes process them, and the root of the tree returns the final result to the client.

Some nodes can be blocking operations: they must read much or all of their input data before emitting their first output row. `Sort` is a classic example; certain forms of aggregation and materialization may also need to process the input set upfront. Other nodes such as index lookups or filters can usually stream data row by row.

### Quick reading rules

1. Locate the root node on the first line.
2. Descend to the child nodes to see where data is read from tables/indexes.
3. Examine what each parent node does with the rows emitted by its child nodes.
4. For JOINs, identify the algorithm and the role of each branch.
5. With `EXPLAIN ANALYZE`, compare rows, loops, and timings from the leaf nodes up to the root.

Do not confuse a line appearing higher in the text with a step that strictly finishes earlier in time. The tree expresses iterator relationships and data flow; parent nodes typically request rows from child nodes on demand.

## 4. Recognizing common nodes

Node names can differ across versions and formats, but common operation groups include:

| Commonly seen node/label | Meaning |
|---|---|
| `Table scan` | Reads table rows sequentially. |
| `Index scan` | Scans all or part of an index in index order. |
| `Index lookup` | Locates rows using key values in an index. |
| `Index range scan` | Scans a key range in a B+tree. |
| `Covering index lookup/scan` | Retrieves all required columns from the index without reading the clustered record. |
| `Filter` | Discards rows that do not satisfy a predicate. |
| `Nested loop join` | Pulls each row from the outer branch and runs the inner branch accordingly. |
| `Hash join` | Uses a hash table to join two datasets on matching conditions. |
| `Sort` | Orders rows according to the requested sort order. |
| `Aggregate` | Groups rows to compute aggregated values. |
| `Materialize` | Creates and stores intermediate results for another node to consume. |
| `Limit` | Caps the number of rows emitted upward. |

Do not merely memorize node names. You need to understand how many rows a node receives, how many it emits, how many times it executes, and whether it is forced to consume its entire input.

## 5. Preparing JOIN practice data

Create two InnoDB tables: `customers` and `orders`. The orders table has indexes for filtering by tenant, status, and timestamp.

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_status_created (
        tenant_id,
        status,
        created_at
    ),
    KEY idx_orders_customer (customer_id)
) ENGINE=InnoDB;
```

Load a small fixture so output is easy to read:

```sql
INSERT INTO customers (customer_id, email, customer_name, city)
VALUES
    (1, 'an@example.test', 'An Nguyen', 'Da Nang'),
    (2, 'binh@example.test', 'Binh Tran', 'Ho Chi Minh City'),
    (3, 'chi@example.test', 'Chi Le', 'Ha Noi');

INSERT INTO orders (
    order_id,
    customer_id,
    tenant_id,
    status,
    created_at,
    total_amount
)
VALUES
    (101, 1, 10, 'PAID', '2026-01-03 09:00:00', 250.00),
    (102, 2, 10, 'PAID', '2026-01-04 10:00:00', 180.00),
    (103, 1, 10, 'NEW',  '2026-01-05 11:00:00', 120.00),
    (104, 3, 10, 'PAID', '2026-01-08 12:00:00', 450.00),
    (105, 2, 20, 'PAID', '2026-01-09 13:00:00',  90.00);
```

Verify the fixture:

```sql
SELECT * FROM customers ORDER BY customer_id;
SELECT * FROM orders ORDER BY order_id;
```

A small fixture is suitable for learning syntax and JOIN flow. The optimizer may choose table scans on tiny tables because the cost is low; evaluating real index performance requires data whose scale and distribution resemble the actual workload.

## 6. Reading a Nested Loop Join tree

Query retrieving PAID orders for tenant 10 within a date range along with customer details:

```sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC, o.order_id DESC;
```

An illustrative tree could take this shape:

```text
-> Nested loop inner join
    -> Index range scan on o using idx_orders_tenant_status_created
       over (tenant_id = 10, status = 'PAID', created_at in requested range)
    -> Single-row index lookup on c using PRIMARY
       (customer_id = o.customer_id)
```

This is an illustrative shape; exact node names, costs, rows, and display order may vary when run on a specific version/dataset.

### The first branch is the outer input

The first branch of the nested loop reads orders from index `idx_orders_tenant_status_created`. Equality columns `tenant_id` and `status` establish the prefix; `created_at` bounds the subsequent range.

If the index range scan emits 3 order rows, the nested loop receives 3 outer rows. Each row carries `customer_id` for use in the second branch.

### The second branch is the inner input

For each order from the outer input, the nested loop looks up customers by primary key:

```sql
WHERE customer_id = o.customer_id
```

Because `customer_id` is the primary key, each lookup can match at most one customer. The inner branch is invoked once per outer row; if the outer branch emits 3 rows, the inner lookup executes about 3 loops.

### Relationship between the two branches

```text
Outer: Index range scan orders
       rows = 3, loops = 1
                  |
                  | each order provides customer_id
                  v
Inner: PK lookup customers
       rows = 1, loops = 3
                  |
                  v
       Nested loop join output = 3 rows
```

This highlights the critical meaning of `loops`: an inner iterator may return only a single row per call yet execute a huge number of times. If the outer input emits 50,000 rows, the inner lookup may have to run 50,000 times.

## 7. Understanding `rows` and `loops` in EXPLAIN ANALYZE

`EXPLAIN FORMAT=TREE` shows estimates, usually formatted as `cost=... rows=...`. `cost` is an internal optimizer cost unit, not milliseconds and not actual execution time. `rows` is the estimated number of rows the iterator will emit. `EXPLAIN ANALYZE` adds actual runtime figures:

```sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
ORDER BY o.created_at DESC, o.order_id DESC;
```

An illustrative output snippet:

```text
-> Nested loop inner join
   (actual time=0.080..0.150 rows=3 loops=1)
    -> Index range scan on o
       (actual time=0.030..0.050 rows=3 loops=1)
    -> Single-row index lookup on c using PRIMARY
       (actual time=0.015..0.020 rows=1 loops=3)
```

The numbers above are solely to illustrate how to read the output, not measurements from your database.

| Field | Meaning |
|---|---|
| `actual time=a..b` | Actual time from when the iterator produces its first row until completion, measured in milliseconds per the iterator's instrumentation; for multi-loop iterators, timings are reported as an average per loop. |
| `rows` | Actual average number of rows emitted by the iterator per execution. |
| `loops` | Number of times the iterator was executed. |

For an iterator running multiple loops, `rows` is typically the average per loop. You can estimate total rows emitted using `rows × loops`; figures may be rounded, so this is an approximation.

In the example, the inner lookup has `rows=1 loops=3`: each lookup returns one customer and the iterator ran three times. Do not read `rows=1` and conclude the entire branch processed only one row.

### Reading timings carefully

Do not sum the times of a parent node and all its child nodes as if they were independent tasks. A parent iterator's timing is tied to the time spent consuming rows from its child iterators; measurement intervals are nested. Use timings to spot costly nodes and evaluate them alongside rows/loops, rather than summing everything into an artificial total.

## 8. Recognizing fan-out in nested loops

Fan-out is the number of rows a JOIN step produces per input row, or the row multiplication factor across JOIN steps. High fan-out can rapidly multiply inner lookup counts.

Example:

```text
Orders range scan:             20,000 rows
Customer PK lookup:            20,000 loops
Order items lookup:            20,000 loops
Average items per order:           8 rows
Rows after joining items:     160,000 rows
```

A query can start with 20,000 orders and expand to 160,000 rows after joining order items. If it continues joining further child tables, intermediate row counts can escalate dramatically.

When reading a plan, ask:

- How many rows does the outer branch emit?
- How many loops does the inner branch execute?
- How many rows does each loop return on average?
- After each JOIN, does total rows increase or decrease?
- Can we filter earlier while preserving identical semantics?
- Is there an appropriate index for the inner branch's lookup condition?

Do not tune an isolated index lookup in a vacuum. A 0.01 ms lookup sounds tiny, yet repeating it 100,000 times still builds up significant total cost.

## 9. Filter nodes and row rejection rate

A Filter pulls rows from a child iterator, evaluates a predicate, and emits only rows that pass the condition.

Example:

```text
-> Filter: status = 'PAID'
    -> Table scan on orders
```

If the table scan reads 100,000 rows yet Filter emits only 500 rows, most data was discarded after already being read. This can signal that the predicate was not pushed into the access path or that a suitable index is missing.

With `EXPLAIN ANALYZE`, compare:

- Rows of the table/index access node.
- Rows of the Filter node.
- Loops of each node.
- Iterator execution time.

If a Filter narrows 100,000 rows down to 500, evaluate whether that condition can become an index range/ref lookup or an index condition. However, not every predicate can use an index; functions on columns, leading wildcards, mismatched data types, or low selectivity can render an index ineffective.

### Filter versus access condition

An access condition determines which entries/ranges to read from an index. A filter/residual condition is checked after the iterator has read candidate rows. A single predicate may be partially used during index access with the remainder filtered afterward. Read the tree alongside index metadata and `EXPLAIN FORMAT=JSON` if you need to see exactly where each condition is applied.

## 10. Sort nodes and their impact on LIMIT

A tree may contain:

```text
-> Limit: 20 row(s)
    -> Sort: created_at DESC
        -> Table scan on orders
```

A Sort node must pull rows from its child and order them. When sorting must process the entire input set, `LIMIT 20` above it does not mean MySQL reads only 20 rows from the table. The engine may have to read and process many rows before knowing which 20 rows come first.

An index with matching order can eliminate the sort:

```sql
-- Index idx_orders_tenant_status_created was created in the data preparation section.
SHOW INDEX FROM orders;
```

With equality predicates on `tenant_id` and `status` and ordering by `created_at`, the index can support the required sort order. Because `order_id` is the primary key, InnoDB appends the clustered key to secondary index entries; you still must inspect the actual plan to confirm ordering and scan direction are satisfied.

Whenever you see `Sort` in a tree, check:

1. How many rows enter Sort?
2. Does Sort sit before or after the JOIN?
3. Can an index read rows in the requested order?
4. Can LIMIT stop reading early, or must Sort still process the entire input?
5. Does Sort spill to temporary storage when data grows large?

## 11. Aggregate and its relationship with input branches

An Aggregate node combines multiple rows to compute summary values or one row per group.

Example:

```sql
EXPLAIN FORMAT=TREE
SELECT tenant_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY tenant_id, status;
```

An illustrative tree:

```text
-> Group aggregate: count(0)
    -> Index scan on orders using idx_orders_tenant_status_created
```

If data is read in a matching group order, the engine can aggregate groups on the fly while scanning the index. In other cases, the plan may require a sort or temporary table before/after aggregation. Do not guess from the `GROUP BY` clause alone; inspect the actual nodes.

For an aggregate without GROUP BY:

```sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = 10;
```

Aggregate typically consumes many rows from the access iterator and emits a single result row. Hence the child node's rows can be huge while the aggregate node's rows is 1.

## 12. Hash Join and reading build/probe branches

MySQL 8.0.18 and later supports hash join in eligible cases, particularly when the optimizer lacks an efficient index access path for an equality join condition.

Hash join generally has two roles:

- **Build side:** reads one dataset and builds an in-memory hash table on the JOIN key.
- **Probe side:** reads the other dataset and probes the hash table for matching rows.

Illustrative tree:

```text
-> Inner hash join (a.key = b.key)
    -> Table scan on a
    -> Hash
        -> Table scan on b
```

The `Hash` node marks the step that builds the hash table on one branch. The remaining branch is used for probing. Node layout and ordering can vary by version and plan; read the JOIN condition, the `Hash` node, and actual metrics rather than assuming the first table in SQL is always the build side.

Hash join can avoid large numbers of random index lookups when two datasets must be joined on equality. However, it still must read the input sets and construct the hash structure; if the build set is large, memory and CPU overhead can be high. Hash join is not universally better than nested loop.

### Comparing Nested Loop and Hash Join

| Criterion | Nested loop | Hash join |
|---|---|---|
| Mechanism | For each outer row, performs lookup/scan on inner. | Builds a hash table from one branch and probes with the other. |
| Best suited for | Small outer input, selective index lookup on inner. | Large join inputs, suitable equality condition, unfavorable index lookups. |
| Warning signs | High inner loops, each loop slow or returning many rows. | Large build side, broad input scans, heavy hash processing. |
| Common optimizations | Shrink outer rows, add index for inner predicate. | Filter both inputs early, reduce columns/rows hashed, check statistics. |

## 13. Materialize, derived tables, and subqueries

Some queries create intermediate results before joining or filtering further. The tree may display a `Materialize` node or an equivalent step.

Derived table example:

```sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_count
FROM customers AS c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE tenant_id = 10
    GROUP BY customer_id
) AS recent
  ON recent.customer_id = c.customer_id;
```

The optimizer may materialize the derived table to compute order counts per customer and then JOIN with customers. If the derived table can be merged into the outer query block, the tree will look different and no separate materialization step will appear.

### Materialize once vs. re-execute many times

Inspect `loops` on the node that builds or reads the intermediate result:

- If materialization is built once and read afterward, the producer node typically shows `loops=1`.
- If a subquery depends on outer rows and is re-evaluated per row, inner iterators can exhibit high loop counts.
- The optimizer may transform certain subqueries into semijoins, antijoins, or materialized subqueries; the plan reflects the chosen strategy.

Do not assume every CTE materializes or every derived table materializes. MySQL may merge or materialize depending on the query block, hints, structure, and optimization rules.

## 14. Reading branch relationships in multi-table JOINs

Suppose a query joins orders, customers, and order_items:

Create the child table and illustrative data before running the query:

```sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id)
) ENGINE=InnoDB;

INSERT INTO order_items (order_item_id, order_id, product_id, quantity)
VALUES
    (1, 101, 501, 2),
    (2, 101, 502, 1),
    (3, 102, 503, 3),
    (4, 104, 504, 1),
    (5, 104, 505, 2);
```

Continue using the `orders` and `customers` tables created in the setup section:

```sql
SELECT
    o.order_id,
    c.customer_name,
    i.product_id,
    i.quantity
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.status = 'PAID';
```

A nested-loop plan can be conceptualized as:

```text
Nested loop
├── Nested loop
│   ├── Access orders (filter tenant/status)
│   └── Lookup customers by customer_id
└── Lookup order_items by order_id
```

This is a logical diagram, not a guaranteed output. If the orders branch emits 1,000 rows, the customers lookup may run 1,000 times; then the order_items lookup may also run once per row emitted by the inner nested loop. If each order averages 5 items, the result can expand to around 5,000 rows.

When reading a multi-table tree:

1. Start from the access nodes at the bottom.
2. Track row counts after each JOIN node.
3. Identify which inner nodes loop according to the output of preceding branches.
4. Locate where fan-out spikes sharply.
5. Check indexes for each join condition.
6. Verify whether the optimizer changed the join order relative to the SQL text.

## 15. Estimated rows vs. actual rows divergence

The optimizer uses statistics to predict row counts. If predictions are substantially wrong, it can pick a suboptimal join order or access path.

Example:

```text
Index range scan on orders
    estimated rows = 100
    actual rows    = 50,000
```

A huge discrepancy can cause a nested loop to perform 50,000 inner lookups instead of the 100 the optimizer expected. A plan that looks cheap in estimates can become terribly slow in actual execution.

Common causes:

- Outdated statistics that no longer reflect current distribution.
- Skewed data where one value occurs far too frequently.
- Correlated columns that the optimizer estimates as independent.
- Complex predicates or functions making selectivity hard to estimate.
- Missing histograms or histograms that fail to capture the needed distribution.
- Specific parameters/values far removed from typical values in statistics.

Investigation steps:

1. Compare estimated rows with actual rows at every node.
2. Find the first node with a large discrepancy; early estimation errors propagate upward to parent nodes.
3. Inspect indexes and `SHOW INDEX`/cardinality.
4. Consider `ANALYZE TABLE` to refresh index statistics.
5. For heavily skewed columns, evaluate adding appropriate histograms.
6. Re-run EXPLAIN/ANALYZE under identical conditions to compare.

Do not update statistics or create histograms merely to force one specific plan. First verify that the metrics and overall workload genuinely call for the change.

## 16. Why `loops` matters more than looking at rows alone

An iterator may emit few rows per invocation yet run a vast number of times. Example:

```text
Single-row index lookup on customers
    actual rows = 1
    loops       = 100,000
```

Each lookup returns just one row, yet in total it executes around 100,000 times. If each call requires a random page access and pages are not in the buffer pool, the cost can be substantial.

Conversely:

```text
Table scan on small_lookup_table
    actual rows = 500
    loops       = 1
```

Scanning 500 rows once can be cheaper than many individual lookups on a large table. Therefore, evaluate simultaneously:

- Average rows per loop.
- Number of loops.
- Approximate total rows (`rows × loops`).
- Iterator execution time.
- Access type and page locality.
- How many rows the parent node actually needs.

Never conclude "smaller rows is always better" while ignoring loops. Likewise, never conclude "table scans are always bad"; scanning a small set or reading sequentially can be the cheapest option.

## 17. End-to-end workflow for reading an execution tree

When handed a slow query, read the plan in this sequence:

1. **Confirm the query and dataset:** use the exact parameters/values, schema, indexes, and active isolation/configuration.
2. **Capture the estimated tree:** run `EXPLAIN FORMAT=TREE`.
3. **Locate the root:** determine whether the final step is Limit, Sort, Aggregate, Join, or another iterator.
4. **Descend to leaves:** identify whether each table is read via table scan, index scan, range scan, or lookup.
5. **Read join order:** identify which table/branch is outer, inner, build, or probe.
6. **Follow rows:** see how many rows each node receives and emits.
7. **Follow loops:** spot iterators executed many times, especially inner lookups and dependent subqueries.
8. **Check filters:** separate conditions used for index access from residual conditions filtered afterward.
9. **Check sort/materialize:** see how many rows these nodes process and whether an index or rewrite can avoid them.
10. **Run EXPLAIN ANALYZE safely:** capture actual time, rows, and loops if the query is safe to execute.
11. **Spot estimate errors:** start from the first node with a large estimated/actual row mismatch.
12. **Propose a small change:** index, predicate, join order via SQL structure, projection, or statistics.
13. **Re-measure:** compare the plan, result correctness, and timing on the same data and conditions.

Do not change multiple indexes or rewrite the entire query at once. Changing one factor at a time makes it clear what actually improved the plan.

## 18. Common mistakes when reading trees

| Mistake | Consequence | Correct way to read |
|---|---|---|
| Reading the tree top-down like sequential SQL execution | Misunderstanding iterator flow | Parent nodes consume data from child nodes; read data flow from leaves to root. |
| Assuming the first table in FROM always runs first | Missing optimizer join reordering | Inspect the actual access branches in the tree. |
| Seeing inner lookup with rows=1 and assuming negligible cost | Ignoring iteration count | Multiply average rows by loops to estimate total work. |
| Checking cost only without checking actuals | Missing estimate inaccuracies | Use EXPLAIN ANALYZE and compare estimated vs. actual rows. |
| Summing all node timings | Double-counting parent-child iterator time | Read timings as nested relationships, never sum mechanically. |
| Seeing Filter and assuming the index already filtered everything | Missing large candidate reads | Compare rows before and after Filter; check access conditions. |
| Seeing Limit 20 and assuming only 20 rows are read | Underlying sort/aggregate may read much more | Check nodes beneath Limit and whether early stop applies. |
| Assuming nested loop is always slow | Overlooking small outer + unique inner lookup | Evaluate outer rows, inner loops, and indexes. |
| Assuming hash join is always better than nested loop | Ignoring build/probe overhead and dataset size | Check input row counts and build-side footprint. |
| Assuming every CTE/derived table always materializes | Misreading plans when optimizer merges blocks | Rely on actual nodes, not SQL syntax assumptions. |
| Running EXPLAIN ANALYZE on dangerous queries in production | Real execution can cause heavy load | Assess safety first and use an appropriate environment. |

## 19. Practice exercises

### Exercise A — Reading parent/child iterators

1. Create `customers`, `orders`, and the fixture from the setup section.
2. Run `EXPLAIN FORMAT=TREE` for the JOIN query.
3. Identify the root node, access nodes, and join node.
4. Sketch the data flow from index range scan to final output.
5. Explain how parent nodes receive rows from child nodes.

### Exercise B — Observing Nested Loop loops

1. Run `EXPLAIN ANALYZE` for the JOIN query.
2. Record rows and loops for the outer index scan.
3. Record rows and loops for the inner primary-key lookup.
4. Expand the number of orders in the fixture to several thousand rows.
5. Explain why inner loops scale with the number of outer rows.

### Exercise C — Recognizing fan-out

1. Create `order_items` with multiple items per order.
2. JOIN orders with order_items.
3. Use EXPLAIN ANALYZE to record row counts before and after the JOIN.
4. Calculate the average fan-out.
5. Find ways to narrow the input row set while preserving exact business results.

### Exercise D — Filter, Sort, and Limit

1. Run a query with a filter and `ORDER BY ... LIMIT`.
2. Check whether the tree contains a Sort.
3. Create an index matching the equality prefix and ordering key.
4. Re-run EXPLAIN to see whether the Sort disappears.
5. Compare rows read with and without the ordering index.

### Exercise E — Nested Loop vs. Hash Join

1. Create two tables with larger datasets and an equality JOIN condition.
2. Run EXPLAIN TREE and identify the JOIN algorithm.
3. Observe the Hash/build/probe nodes if the optimizer chooses a hash join.
4. Add an appropriate index and re-measure.
5. Explain why the optimizer switches between nested loop and hash join.

### Exercise F — Estimate vs. actual

1. Run EXPLAIN and record estimated rows for each node.
2. Run EXPLAIN ANALYZE and record actual rows/loops.
3. Locate the first node with a large discrepancy.
4. Run `ANALYZE TABLE` if statistics need refreshing.
5. Re-measure and explain any optimizer changes.

You have completed this lesson when you can trace data flow from leaves to root, explain outer/inner or build/probe relationships, calculate the impact of loops/fan-out, and pinpoint the first node where estimated rows diverge from actual rows.

## 20. Principles to remember

- An execution plan is how the optimizer executes SQL; it is not a mirror of the written SQL clause order.
- In TREE, parent nodes pull data from child nodes; results flow from leaves to root.
- `EXPLAIN FORMAT=TREE` shows iterator relationships; `EXPLAIN ANALYZE` runs the SELECT and adds actual metrics.
- Nested loop takes the outer branch as input and invokes the inner iterator per outer row.
- `loops` indicates how many times an iterator ran; rows is usually the average rows per loop.
- `rows × loops` helps estimate total rows emitted by a looped iterator, subject to rounding.
- High fan-out can multiply rows across multiple JOINs and cause inner lookups to repeat heavily.
- Filter narrows rows emitted by its child iterator; compare rows before and after to spot where lots of data is discarded.
- Sort, aggregate, and materialize can be blocking steps that prevent an upstream LIMIT from stopping reads early.
- Hash join has build/probe sides; assess the size of both inputs and hash overhead.
- Divergent estimated vs. actual rows can lead the optimizer to choose a poor join order or access path.
- Never sum parent and child node times mechanically; iterator timings are nested.
- Use EXPLAIN TREE, EXPLAIN ANALYZE, statistics, and real workloads to verify changes.

When you read an execution plan as an iterator tree and track rows alongside loops on every branch, you can see where data is read, where row counts expand or shrink, and which step repeats excessively. This forms the foundation for choosing indexes, narrowing JOIN inputs, resolving sort/materialization bottlenecks, and tuning queries from execution evidence.
