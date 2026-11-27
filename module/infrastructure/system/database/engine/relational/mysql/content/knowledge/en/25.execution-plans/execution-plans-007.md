# Actual Rows, Loops, Startup Time, and Completion Time

Standard EXPLAIN shows how many rows the optimizer projects a plan will process and which access path it chooses. Estimates, however, are not actual results. MySQL 8.0.18 and later provides EXPLAIN ANALYZE to execute the SELECT statement and record actual row counts, iterator invocation counts, and the time each iterator takes to produce its first row and finish returning rows.

In TREE output, an iterator may appear as follows:

    (actual time=0.120..0.450 rows=8 loops=1)

The two timestamps carry distinct meanings: the first is the time until the iterator returns its first row; the second is the time until the iterator finishes returning all rows for that execution. rows is the average number of rows returned by the iterator per execution, while loops is how many times the iterator ran. When reading these values, distinguish startup time from completion time, understand averaging across multiple loops, and avoid summing timings of nested nodes as if they were independent.

This lesson focuses on reading actual rows, loops, startup time, and completion time, identifying slow iterators, interpreting nested loops and sort/materialization steps, and understanding the limitations of EXPLAIN ANALYZE metrics when compared with application-observed latency.

## Learning objectives

After this lesson, you will be able to:

- Explain EXPLAIN ANALYZE and how it differs from standard EXPLAIN.
- Read actual time=a..b, rows, and loops in each iterator.
- Distinguish time to first row from iterator completion time.
- Understand how rows and actual time are averaged when an iterator has multiple loops.
- Estimate total rows returned across invocations via rows multiplied by loops.
- Analyze loops in nested loop joins and repeatedly invoked iterators.
- Recognize startup delays caused by sorting, materialization, or input processing before returning rows.
- Compare estimated rows against actual rows on an equal footing.
- Locate the first major discrepancy in the execution tree.
- Distinguish iterator timing from total end-to-end application latency.
- Use EXPLAIN ANALYZE safely and avoid skewed measurements from cache state, parameters, or system load.

## 1. Differences between EXPLAIN and EXPLAIN ANALYZE

Standard EXPLAIN asks the optimizer to build a plan and return estimates. It does not execute the SELECT to collect actual row counts and timings.

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

EXPLAIN ANALYZE executes the query, instruments the iterators in the plan, and returns an execution tree with actual metrics:

    EXPLAIN ANALYZE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

Key points to remember:

- EXPLAIN ANALYZE is supported starting in MySQL 8.0.18.
- EXPLAIN ANALYZE output uses TREE format.
- The query is genuinely executed to collect metrics; this is not a plan-only inspection.
- Iterators report actual row counts, loops, and timings.
- Results remain subject to data, cache state, server load, and instrumentation overhead.

Do not run EXPLAIN ANALYZE on a heavy query in production just to take a quick look. Before running it, understand the volume of data the SELECT might read and the resources the query could consume.

## 2. Structure of an actual metrics line

A node in TREE output might look like:

    -> Index lookup on o using idx_order_customer
       (customer_id=1001)
       (cost=1.20 rows=4)
       (actual time=0.020..0.035 rows=5 loops=1)

Meaning:

| Component | Meaning |
|---|---|
| cost=1.20 | Optimizer's estimated cost under its cost model |
| rows=4 in cost block | Rows the optimizer estimates the iterator will return/read in plan context |
| actual time=0.020..0.035 | Actual time to first row and iterator completion |
| rows=5 in actual block | Actual average rows returned by the iterator per loop |
| loops=1 | The iterator executed once |

In this example, the iterator ran once and returned 5 rows, whereas the optimizer estimated 4 rows. Time to first row was roughly 0.020 ms; completion time was roughly 0.035 ms. These numbers merely illustrate formatting, not a benchmark of a specific server.

### 2.1. Time units

EXPLAIN ANALYZE actual time values are displayed in milliseconds. For example:

- 0.020 equals 20 microseconds.
- 1.500 equals 1.5 milliseconds.
- 125.000 equals 125 milliseconds.

Do not confuse the decimal point with a seconds separator. The output actual time=0.120..0.450 shows two timestamps in milliseconds.

## 3. Two timestamps: first row and completion

Given:

    actual time=a..b

- a: time from when the iterator starts executing until it returns its first row.
- b: time from when the iterator starts executing until it finishes returning all rows for that execution.

b is the cumulative completion timestamp from the start, not an incremental duration after the first row. If you want to gauge the span between first row and completion, you can mentally subtract b - a, though do not treat that difference as an independent metric directly reported by MySQL.

Example:

    actual time=2.000..12.000 rows=100 loops=1

Interpretation:

- The iterator took roughly 2 ms to produce its first row.
- The iterator finished returning 100 rows roughly 12 ms after starting.
- After the first row, roughly 10 ms remained for processing and emitting the rest of the rows.

These two timestamps distinguish queries with high startup delay from queries that produce a first row quickly yet take a long time to finish.

### 3.1. A fast first row does not mean a fast query overall

An iterator can emit its first row very early yet continue reading many rows:

    actual time=0.050..800.000 rows=500000 loops=1

It begins emitting results after about 0.05 ms yet takes roughly 800 ms to complete. This may be a streaming scan over many rows.

Conversely, an iterator may have to process nearly all of its input before emitting a single row:

    actual time=450.000..470.000 rows=20 loops=1

The iterator takes about 450 ms before producing its first row, then emits 20 rows and finishes around 470 ms. This may be a sort or materialization step that must consume its input upfront.

### 3.2. Startup time is not just Init() call overhead

The term startup time is commonly used to describe latency before the first row. It is not strictly the execution time of an isolated initialization function. An iterator can invoke child iterators, read input data, build a temporary structure, or do substantial work before emitting its first row.

Therefore, when you see a large first timestamp, examine the child iterator subtree underneath and the type of operation occurring. Never assume that node alone spent all that time in an independent setup routine.

## 4. rows and loops

rows in the actual block is the average number of rows returned by the iterator per execution. loops is how many times the iterator ran.

Example:

    actual time=0.010..0.025 rows=3 loops=1

The iterator ran once and returned 3 rows.

Another example:

    actual time=0.005..0.015 rows=2 loops=10

The iterator ran 10 times, returning an average of 2 rows each time. Total rows returned across all runs is approximately:

    2 rows/loop * 10 loops = 20 rows

When the average row count is fractional, multiplying still gives only an approximate total due to display rounding.

### 4.1. rows does not equal rows examined

Actual rows is the number of rows the iterator emitted to its parent iterator per execution. It is not necessarily the total number of records the storage engine examined or read from disk.

For instance, an index range scan might inspect many index entries, apply predicates, and emit only a subset of rows. A filter iterator might receive 1,000 rows from its child yet forward only 10 rows to the node above.

To understand rows read, rows filtered out, and per-step cost, examine the entire iterator tree, access methods, filter predicates, and other diagnostic metrics. Never use a single actual rows figure as a stand-in for every notion of rows examined.

### 4.2. High loops commonly appear inside nested loops

A nested loop join executes its inner iterator for each row emitted by its outer iterator. If the outer side emits 100 rows, the inner lookup iterator may be called 100 times:

    -> Nested loop inner join
       (actual time=... rows=... loops=1)
        -> Table scan on customer
           (actual time=... rows=100 loops=1)
        -> Index lookup on orders using idx_order_customer
           (actual time=... rows=4 loops=100)

The inner lookup iterator was invoked 100 times, returning an average of 4 orders each time. Total rows it emitted is roughly 400.

This does not mean MySQL generated 100 separate SQL statements. It is the exact same iterator invoked repeatedly during nested-loop execution.

### 4.3. High loops is not automatically a problem

A primary key lookup can be very cheap even if executed thousands of times. Conversely, a few calls to an expensive iterator or lookups scanning many rows each time can cause trouble.

When evaluating loops, consider simultaneously:

- Time per loop.
- Rows per loop.
- Total invocation count.
- The iterator's access path.
- How many outer rows triggered those calls.
- The iterator's impact on its parent node's completion time.

Do not blindly target the node with the highest loops. Identify total work and what actually drives query latency.

## 5. Timings are averaged when loops > 1

When an iterator executes multiple times, actual time and rows in the output are reported as averages per loop.

Example:

    actual time=0.010..0.030 rows=4 loops=100

Interpretation:

- The iterator ran 100 times.
- On average, each call took about 0.010 ms to produce its first row.
- On average, each call completed roughly 0.030 ms after that call began.
- On average, each call returned 4 rows.
- Total rows returned across all runs is roughly 400.

Do not read actual time=0.010..0.030 as the total time for all 100 loops. It is the average time for a single iterator invocation.

You can multiply average time by loops to get a rough idea of that iterator's cumulative time across calls, but exercise caution:

- Values are rounded.
- Individual calls can have high variance.
- Parent and child timings overlap in measurement.
- Total query time is not a simple sum of every node.

Therefore, use multiplication as a mental gauge for iteration volume, not to reconstruct exact total query wall-clock time.

## 6. Reading the iterator tree bottom-up

EXPLAIN ANALYZE prints a tree-shaped plan. Child iterators supply data to parent iterators. To understand the query, read from leaf iterators (scans/lookups) up through join, filter, aggregate, and sort nodes, and finally to the root.

Illustrative example:

    -> Limit: 20 row(s)
       (actual time=0.120..0.450 rows=20 loops=1)
        -> Sort: o.order_date DESC, limit input to 20 row(s)
           (actual time=0.118..0.440 rows=20 loops=1)
            -> Filter: (o.order_status = 'PAID')
               (actual time=0.050..0.350 rows=80 loops=1)
                -> Index lookup on o using idx_order_customer
                   (customer_id=1001)
                   (actual time=0.040..0.300 rows=500 loops=1)

Interpretation:

1. Index lookup finds customer 1001's orders and emits 500 rows.
2. Filter retains 80 PAID orders.
3. Sort orders by order_date and limits input according to the LIMIT clause.
4. Limit returns 20 rows to the client iterator above.

These numbers only illustrate how to read the tree. Actual plans vary by indexes, data, and version.

### 6.1. Identifying nodes generating high row counts

In the example, the lookup emits 500 rows yet the filter keeps only 80. You might need to evaluate:

- Is the index sufficiently selective?
- Could a composite index (customer_id, order_status, order_date) be used?
- Should an index support both filtering and sort order?
- Does the query need all 500 rows before sorting, or can top-N be retrieved more efficiently?

You cannot conclude from row counts alone. Inspect actual time, estimated rows, key, Extra, and the table's write workload.

### 6.2. Do not sum timings across all nodes

A parent node's timing includes the time spent invoking and consuming data from child nodes. Hence parent and child timings are not disjoint segments you can add together.

For instance, if the root completes in 20 ms, one child reports 15 ms, and another reports 10 ms, do not conclude total query time is 45 ms. Those durations lie inside overlapping nested execution intervals.

Use the root iterator to gauge server-side iterator tree completion time, then inspect child nodes to see which pieces of work contribute to that latency.

## 7. Nested loop: analyzing loops and per-lookup time

A nested loop generally pairs an outer iterator with an inner iterator:

    for each row from outer iterator:
        execute inner iterator using values from outer row

Example query with customers and orders:

    SELECT
        c.customer_id,
        c.customer_name,
        o.order_id,
        o.total_amount
    FROM plan_customer_demo AS c
    JOIN plan_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN'
      AND o.order_status = 'PAID';

Suppose the outer iterator emits 3 customers. The inner index lookup runs 3 times, each looking up one customer's orders.

Hypothetical output:

    -> Nested loop inner join
       (actual time=0.080..0.420 rows=5 loops=1)
        -> Index lookup on c using idx_customer_country
           (country_code='VN')
           (actual time=0.025..0.040 rows=3 loops=1)
        -> Index lookup on o using idx_order_customer
           (customer_id=c.customer_id)
           (actual time=0.020..0.070 rows=2 loops=3)

The inner lookup averages 2 rows across 3 calls, roughly 6 input rows total. The final join returns 5 rows after applicable conditions are applied. Illustrative numbers do not necessarily match every plan variant because filters can reside in other iterators.

When inner loops is large:

- Check whether outer rows is higher than estimated.
- Check whether inner access uses an efficient index lookup.
- Check how many rows each lookup returns.
- Check whether the outer input can be filtered earlier.
- Check composite indexes covering join and filter conditions.
- Evaluate hash join or other strategies if supported by your version and query.

Do not try to eliminate loops at all costs. If the outer side has 100 rows and each inner lookup takes only a few microseconds, nested loop can be an ideal plan.

## 8. Sort and materialization often exhibit high startup time

Some iterators must process much or all of their input before emitting their first row.

### 8.1. Sort

If a query requires ORDER BY and no index supplies matching order, MySQL may have to sort the input set:

    SELECT order_id, total_amount
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY total_amount DESC
    LIMIT 10;

If the access path does not support this order, the sort iterator may need to read and process many rows before emitting the first result. Consequently, the first actual time timestamp on Sort can be high.

LIMIT does not guarantee MySQL reads only 10 rows. If it must find the top 10 values from a large set, the server still needs to process enough data to determine the top 10, even if it uses a top-N strategy rather than a naive full sort.

### 8.2. Materialization

A derived table or subquery may be materialized into an internal temporary table. The materialize iterator may need to consume all input before the parent iterator begins reading results.

When encountering high startup time, check:

- Is there a Materialize or temporary table iterator?
- Can the derived table be merged instead?
- Is there a GROUP BY, DISTINCT, or window operation requiring full input processing?
- Can filtering happen earlier before materializing?
- Are suitable indexes present on source tables or intermediate structures?

Not every materialization is bad. It can avoid recomputing a subquery or support a cheaper overall plan.

### 8.3. LIMIT and early termination

A suitable index can let MySQL read in order and stop once LIMIT is satisfied:

    CREATE INDEX idx_plan_order_status_date
    ON plan_order_demo (order_status, order_date);

    SELECT order_id, order_date
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY order_date DESC
    LIMIT 10;

If the index supports both the predicate and ordering, the iterator can emit 10 rows without sorting the whole result set. Inspect actual rows and the iterator tree to confirm the actual plan.

## 9. Self-contained practice example

Create two tables to observe joins, filters, and loops in a sandbox database:

    CREATE TABLE plan_customer_demo (
        customer_id BIGINT UNSIGNED NOT NULL,
        customer_name VARCHAR(100) NOT NULL,
        country_code CHAR(2) NOT NULL,
        PRIMARY KEY (customer_id),
        KEY idx_customer_country (country_code)
    ) ENGINE = InnoDB;

    CREATE TABLE plan_order_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        order_date DATETIME NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_order_customer (customer_id),
        KEY idx_order_status (order_status),
        KEY idx_order_customer_status (customer_id, order_status)
    ) ENGINE = InnoDB;

    INSERT INTO plan_customer_demo
        (customer_id, customer_name, country_code)
    VALUES
        (1001, 'An', 'VN'),
        (1002, 'Binh', 'VN'),
        (1003, 'Chi', 'VN'),
        (1004, 'Dung', 'US');

    INSERT INTO plan_order_demo
        (order_id, customer_id, order_date, order_status, total_amount)
    VALUES
        (5001, 1001, '2025-01-02 10:00:00', 'PAID',      120.00),
        (5002, 1001, '2025-01-05 11:00:00', 'PENDING',    80.00),
        (5003, 1001, '2025-01-08 12:00:00', 'PAID',      250.00),
        (5004, 1002, '2025-01-10 13:00:00', 'CANCELLED',  40.00),
        (5005, 1002, '2025-01-11 14:00:00', 'PAID',      500.00),
        (5006, 1003, '2025-01-12 15:00:00', 'PAID',       75.00),
        (5007, 1004, '2025-01-13 16:00:00', 'PAID',      300.00);

    ANALYZE TABLE plan_customer_demo, plan_order_demo;

These sample tables are tiny, so the optimizer may pick table scans. This dataset is for checking syntax and inspecting output; to study plans at scale, use datasets large enough and distributed similarly to real workloads.

### 9.1. Running EXPLAIN ANALYZE

    EXPLAIN ANALYZE
    SELECT
        c.customer_id,
        c.customer_name,
        o.order_id,
        o.total_amount
    FROM plan_customer_demo AS c
    JOIN plan_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN'
      AND o.order_status = 'PAID';

Read the output in sequence:

1. Identify the root iterator and final row count.
2. Identify which iterator filters customers by country_code.
3. Identify the iterator accessing orders by customer_id or another index.
4. Inspect loops on the inner iterator of the nested loop.
5. Compare estimated rows with actual rows at each node.
6. Locate nodes with high startup time or completion time.

### 9.2. Testing a query with ORDER BY and LIMIT

    EXPLAIN ANALYZE
    SELECT
        order_id,
        order_date,
        total_amount
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY total_amount DESC
    LIMIT 2;

With the current schema, the status index does not provide total_amount ordering. The plan may require a sort. Adding a matching index can alter the access path, though it only pays off if the workload and data distribution justify index overhead:

    CREATE INDEX idx_order_status_amount
    ON plan_order_demo (order_status, total_amount);

Re-run EXPLAIN ANALYZE and compare:

- Does the sort iterator still appear?
- Did the time-to-first-row timestamp change?
- How did actual rows read/emitted across iterators change?
- Does the new index increase write overhead?

Do not assume the new index is guaranteed to be selected on a tiny sample table.

## 10. Comparing estimated rows and actual rows

EXPLAIN ANALYZE places estimates and actuals side by side. This is how to catch cardinality errors:

    -> Index lookup on orders
       (cost=... rows=5)
       (actual time=... rows=500 loops=1)

The optimizer estimated roughly 5 rows, yet the iterator actually returned 500 rows. A 100x mismatch can skew join order and join algorithm decisions.

A simple gauge is the ratio:

    estimate_error_ratio = max(estimated_rows, actual_rows)
                         / max(1, min(estimated_rows, actual_rows))

This is merely a magnitude indicator, not an official MySQL metric. Calculate it on the same scope and remember that actual rows is reported per loop.

### 10.1. Comparing on the same basis when loops > 1

If output shows:

    rows=4 loops=100

then 4 is the average per loop, with roughly 400 total rows. When comparing against the iterator's estimated rows, verify whether the estimate describes per-access rows or cumulative rows across the plan. Do not multiply one side while forgetting the other.

In a nested loop, the inner access estimate is typically interpreted per invocation, while loops shows the invocation count. Read outer rows, inner rows, and loops together to grasp total work.

### 10.2. Errors in early nodes amplify downstream

Suppose the optimizer estimates the outer iterator returns 10 customers, whereas it actually returns 10,000. Each inner lookup costs 0.1 ms. The plan anticipated ~10 lookups, yet runtime executes ~10,000 lookups.

In this scenario, the root cause does not necessarily lie in the inner index. The initial error in outer cardinality inflated loops massively. Always locate the first node where actual rows diverges sharply from estimates instead of only patching the final node.

## 11. Reading root time vs. child node times

The root iterator is the final node producing the plan's output. The root's completion timestamp is generally a useful indicator of server-side iterator execution time in an EXPLAIN ANALYZE run.

Child nodes break down the work:

- Scan/lookup: reading input data.
- Filter: discarding rows failing conditions.
- Join: combining two row streams.
- Aggregate: grouping or computing summaries.
- Sort: ordering data.
- Materialize: creating and storing intermediate results.
- Limit: stopping after retrieving needed rows.

Parent node timing includes the time spent calling and consuming data from child nodes. Never sum completion times across all nodes to derive root time.

If the root completes quickly yet the application remains slow, check components outside the iterators:

- Connection acquisition and request dispatch time.
- Network latency.
- Protocol result serialization and transmission time.
- Client fetching and row processing.
- Wait time at the application tier.
- Queueing, connection pools, and downstream dependencies.

EXPLAIN ANALYZE does not replace distributed tracing or end-to-end application latency measurement.

## 12. Factors causing metrics to vary between runs

Even when SQL and schema stay constant, actual timing can vary:

- Whether the buffer pool and OS cache are warm.
- Whether data was recently read or must be fetched from storage.
- CPU contention and I/O contention.
- Background purge, checkpointing, flushing, and concurrent workloads.
- Lock waits or metadata locks during access.
- Different query results due to different bind parameters.
- Changes in statistics or execution plans.
- Larger or smaller result sets.
- Instrumentation overhead from EXPLAIN ANALYZE itself.

Do not conclude a change improved performance from a single run. Use identical data, parameters, and configuration across multiple runs; compare medians or appropriate percentiles rather than picking the fastest run.

### 12.1. Warm cache vs. cold cache

The first run may have to read pages from storage; subsequent runs may hit the buffer pool. Hence later runs are often faster without the plan being any better.

When comparing two plans:

- Do not clear production caches just to force a cold run.
- Document whether measurements are warm-cache or cold-cache.
- Run alternatives under equivalent conditions.
- Inspect logical work/rows/loops alongside wall-clock time.

If plan A reads fewer rows yet takes longer in a single cold-cache run, take more measurements before concluding.

### 12.2. Parameters with varying distributions

A query with a high-volume customer_id may return thousands of orders; a rare customer_id returns just a few. The exact same SQL produces different actual rows, loops, and timings.

Test multiple representative parameter groups:

- Rare values.
- Common values.
- Narrow date ranges.
- Wide date ranges.
- Low-frequency statuses.
- High-frequency statuses.

Do not tune a query for a single parameter value if the application serves widely varying distributions.

## 13. EXPLAIN ANALYZE vs. application time

Three timing concepts should be kept distinct:

| Concept | What does it measure? | Appropriate tool |
|---|---|---|
| Iterator startup time | Time from iterator start until first row | First actual time timestamp |
| Iterator completion time | Time from iterator start until all rows emitted in that run | Second actual time timestamp |
| End-to-end latency | Time observed by the application from sending request to finishing result handling | APM, tracing, or client-side timing |

Root completion time is useful for analyzing server-side iterator execution, but it is not an end-to-end SLA. An API can be slow due to connection pooling, network, serialization, or client fetching even when the root iterator runs fast.

Conversely, an application may receive initial results quickly from a streaming iterator even if root completion time is high because many trailing rows remain. This matters for streaming APIs or clients reading results in batches.

## 14. Iterators that can cause first-row delay

Operations worth checking when the first timestamp is high:

| Iterator/operation | Why it may wait before emitting the first row |
|---|---|
| Sort | Must read and process much input before determining top rows |
| Materialize | Must build the intermediate result before reading from it |
| Aggregate | May need to read a whole group or entire input before returning results |
| Hash join build side | Must build the hash table from one side before probing |
| Temporary table | May need to create/populate an intermediate structure |
| Window operation | Some window frames require processing and sorting data before emitting rows |

These are tendencies, not a rule that every iterator with that name always blocks on all input. Specifics depend on the plan, algorithm, and streaming capability.

## 15. Pinpointing bottlenecks from actual metrics

A practical analysis workflow:

1. Identify the root iterator and completion time.
2. Locate nodes with high actual time, checking whether timing is inclusive of child nodes underneath.
3. Look for high startup delay if the application needs the first row quickly.
4. Inspect nodes with high loops and multiply by average rows to gauge total row volume across calls.
5. Compare estimated rows and actual rows to spot cardinality errors.
6. Find the first node exhibiting a major discrepancy.
7. Inspect related predicates, indexes, sorts, materializations, and join order.
8. Change one factor at a time and re-measure under identical conditions.

Do not simply pick the node with the largest millisecond value. A parent node may include child timings; a high-loop node may show tiny per-call time. Always combine tree structure with metrics.

## 16. Limitations and safety notes for EXPLAIN ANALYZE

- EXPLAIN ANALYZE executes the SELECT; the query can read massive data and generate load.
- It is not a client-to-client application latency measurement.
- Instrumentation adds overhead; measured times can differ from normal query execution.
- TREE output and iterator names can change between versions.
- Actual rows is rows emitted by the iterator, not all records examined.
- Timing and rows on multi-loop iterators are averages per loop.
- Parent and child timings overlap; never sum the whole tree.
- Queries with locking reads or functions with side effects should not be test-run without understanding their impact.
- Use staging or a data replica when queries are heavy or require repeated runs.
- Bound date ranges and parameters to prevent unexpectedly broad scans.

## 17. Common mistakes

- Reading the second actual time timestamp as incremental time after the first row, instead of total completion time from iterator start.
- Treating actual time=a..b as two independent durations to add together.
- Treating rows as cumulative total rows when loops is greater than 1.
- Treating loops as row count or number of SQL statements sent by the application.
- Forgetting to multiply average rows by loops when picturing total row volume across invocations.
- Multiplying timing by loops and treating the product as exact wall-clock query time.
- Summing parent and child timings in the tree to compute a total.
- Confusing actual rows with rows examined.
- Assuming a fast first row means the entire query finishes fast.
- Assuming startup time is solely an isolated initialization function's cost, excluding child iterator work.
- Assuming LIMIT always causes MySQL to read only the LIMIT number of rows.
- Failing to recognize that sort/materialization can introduce startup delay.
- Comparing two runs with differing cache states and parameters.
- Running EXPLAIN ANALYZE on heavy production queries without assessing load.
- Using EXPLAIN ANALYZE as a substitute for end-to-end latency measurement.

## 18. Checklist for reading actual rows, loops, and timing

- Confirmed the MySQL version supports EXPLAIN ANALYZE.
- Understood the SELECT will execute and assessed load before running.
- Identified the root iterator and completion time.
- Read actual time=a..b accurately: first row and completion.
- Remembered time units are milliseconds.
- Read rows as average rows per loop.
- Read loops as the number of iterator invocations.
- Estimated total rows via rows multiplied by loops where appropriate.
- Checked loops on inner iterators of nested loops.
- Distinguished rows emitted from rows examined.
- Read the tree from leaves up to the root.
- Avoided summing parent and child timings.
- Checked for startup delays in sort, materialize, aggregate, or hash build if present.
- Compared estimated rows and actual rows on an equal basis.
- Located the first iterator with a major discrepancy.
- Measured under comparable cache, parameter, and load conditions.
- Distinguished iterator timing from end-to-end application latency.
- Saved output and noted version/schema when drawing conclusions.

EXPLAIN ANALYZE turns an estimated plan into an iterator tree annotated with actual row counts, invocation counts, and timings. The first timestamp of actual time shows latency to the first row; the second shows iterator completion time from the start. rows and timings are averaged across loops, so they must be read together, especially on the inner side of nested loops. When diagnosing, work from leaves up to the root, find the first estimate/actual mismatch, spot startup delays, and avoid summing nested node timings. Finally, treat iterator metrics as a tool for server-side execution analysis; end-to-end latency still must be measured at the application tier.
