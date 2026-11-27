# Cost Estimation, Fetch Size, and Cross-Server Query Performance

When an application queries data residing on another PostgreSQL server, completion time depends on several factors: the execution plan on the calling server, the work performed on the server holding the data, the volume of data transferred over the network, the number of round trips, and any remaining processing on the calling server. Even a short SQL query can be slow if it ships hundreds of thousands of rows across the network before filtering or joining them.

In PostgreSQL, a common integration approach is **postgres_fdw**. This extension creates foreign tables representing tables on another server. Applications query foreign tables much like regular tables; postgres_fdw determines which parts of the query can be sent to the remote server. Concepts such as cost estimation, statistics, **fetch_size**, and pushdown help govern the performance of this model.

The options **use_remote_estimate**, **fdw_startup_cost**, **fdw_tuple_cost**, and **fetch_size** discussed here belong to postgres_fdw. Other FDWs may have different mechanisms and option names.

## 1. The Path of a Cross-Server Query

Suppose an application connects to PostgreSQL A, while order data resides on PostgreSQL B. On A, an administrator configures postgres_fdw, defines server B, maps login credentials, and creates a foreign table for the orders table on B.

When the application runs a query on the foreign table, the execution flow typically consists of the following steps:

1. PostgreSQL A parses the SQL statement and builds an execution plan.
2. The planner estimates row counts, costs, and candidate execution strategies.
3. postgres_fdw forwards the eligible parts of the query to PostgreSQL B.
4. PostgreSQL B executes the received SQL, potentially using B's own indexes and statistics.
5. Results are streamed back to A in fetch batches.
6. PostgreSQL A performs any remaining computations that could not be pushed down to B, such as joining with a local table or evaluating expressions unsupported remotely.

Thus, writing SQL on A does not mean the entire query executes on A. If filters and aggregations are pushed down to B, the network only carries the reduced result set. Otherwise, A may have to receive a massive number of rows before filtering or grouping them.

It is important to distinguish three parts of the work: **planning** based on estimates; **remote execution** on the server holding the data; and **transfer plus local processing** on the calling server.

## 2. How Does PostgreSQL Estimate Costs?

PostgreSQL uses cost to compare execution plans. Cost values in EXPLAIN are **internal cost units**, not milliseconds. A plan with a cost of 500 does not mean the query takes 500 ms. Cost is most useful when comparing alternative plans within the same environment and configuration.

Plans typically display two values:

- **startup cost:** estimated cost before the first row can be returned.
- **total cost:** estimated cost to complete the entire execution node.

For cross-server queries, startup cost can reflect the fixed overhead of initiating remote access. Per-row cost reflects the incremental work of processing and transferring data. Estimates influence whether a foreign scan is chosen, join ordering, and where computations are executed.

### 2.1. Foreign Table Statistics

When using local estimates, PostgreSQL needs statistics to predict how many rows satisfy WHERE conditions, distinct value counts, data distributions, and intermediate row counts during joins or grouping.

You can collect statistics for a foreign table using:

~~~sql
ANALYZE remote_orders;
~~~

With postgres_fdw, ANALYZE samples data from the remote server to build statistics used by the local planner. Autovacuum does not automatically analyze foreign tables the way it does regular local tables, so you should proactively schedule ANALYZE whenever the source data changes significantly.

If statistics are stale or missing, PostgreSQL can misestimate row counts. For example, the planner might estimate that a date filter returns 100 rows when it actually returns 500,000 rows. A join plan built on inaccurate estimates can cause network data transfer to spike dramatically.

### 2.2. Obtaining Estimates from the Remote Server

postgres_fdw provides the **use_remote_estimate** option:

- The default is **false**. Local PostgreSQL estimates costs using local foreign table statistics and FDW cost options.
- When set to **true**, postgres_fdw sends an EXPLAIN command to the remote server to obtain estimates from the remote planner.

Remote estimates are helpful when server B has statistics, indexes, or data distributions that A's local statistics do not fully reflect. Server B can evaluate filter conditions and access paths based on its actual data state.

On the other hand, fetching remote estimates triggers communication with B during the planning phase. This can increase planning time, especially when an application issues many short queries or accesses multiple foreign tables. Remote estimates also do not guarantee actual runtime performance, as server load and network conditions still fluctuate.

This option can be configured at the server or foreign table level. For example:

~~~sql
CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'true'
  );
~~~

If queries are long-running and remote estimates yield better plans, the added planning overhead can be worthwhile. For workloads composed of many very short queries, measure planning time before enabling this option broadly.

### 2.3. Two Cost Parameters of postgres_fdw

When **use_remote_estimate** is disabled, postgres_fdw uses two additional options to model the cost of accessing remote data:

| Option | Default Value | Meaning |
|---|---:|---|
| **fdw_startup_cost** | 100 | Fixed cost added to the startup cost of a foreign scan |
| **fdw_tuple_cost** | 0.2 | Additional cost per row transferred from the remote server |

**fdw_startup_cost** roughly represents the fixed overhead of starting a remote query, such as connection and execution initialization costs. A higher value makes plans that open a foreign scan appear more expensive to the planner. This parameter matters particularly if a plan might trigger multiple remote scans.

**fdw_tuple_cost** represents the incremental cost for each row transferred from B back to A. Slow networks, wide rows, or heavy data conversion overhead may warrant a higher value than the default. When this value increases, the planner considers pulling many rows from the remote server more expensive.

Both values are planner cost units, not milliseconds. Do not take a 20 ms network latency and set fdw_tuple_cost to 20. Adjust incrementally, observe the chosen plans, and compare execution times on a representative workload.

They can be declared at the server level:

~~~sql
CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'false',
    fdw_startup_cost '100',
    fdw_tuple_cost '0.2',
    fetch_size '500'
  );
~~~

Or set specifically on a foreign table:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fdw_tuple_cost '0.35');
~~~

If the option already exists on the foreign table, use **SET** instead of **ADD**. Table-level configuration lets you fine-tune a single table without affecting every table sharing the server.

## 3. Fetch Size and How Data Moves Across the Network

**fetch_size** specifies the number of rows postgres_fdw retrieves in each fetch from the remote server. The default value is **100 rows**. This option can be specified at the foreign server or foreign table level; a table-level setting overrides the server-level configuration.

For example, increasing the fetch size for the orders table:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fetch_size '1000');
~~~

If the table already has a fetch_size option, use:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (SET fetch_size '1000');
~~~

Fetch size only controls the batch size of each result fetch. It does not cap the total number of rows a query returns, does not replace LIMIT, and does not change the semantics of the SQL statement.

### 3.1. Why Does Fetch Size Affect Performance?

Suppose a query returns 10,000 rows:

- With a fetch size of 100, roughly 100 data-bearing fetch trips are needed.
- With a fetch size of 1,000, roughly 10 data-bearing fetch trips are needed.

Reducing round trips can speed up queries over high-latency networks. However, increasing fetch size also puts more rows into each batch, increasing the memory needed to buffer incoming data and potentially increasing latency before the first batch finishes processing.

An approximate model to visualize data transfer time:

~~~text
Data-bearing fetch trips ≈ ceil(Total rows / fetch_size)

Total time ≈ Remote processing time
           + Round trips × Network latency
           + Data size / Effective bandwidth
           + Local processing time
~~~

This is an explanatory model, not the cost formula PostgreSQL uses. Actual behavior also depends on how the server streams results, individual row sizes, concurrency, buffers, and the load on both servers. An extra fetch trip may also occur to confirm end-of-data.

### 3.2. Choosing an Appropriate Fetch Size

Small fetch size:

- Uses less memory per batch.
- Can return data in small increments.
- Generates more round trips, making it more sensitive to network latency.

Large fetch size:

- Reduces fetch round trips and often improves throughput for large result sets.
- Makes better use of high-latency links.
- Increases per-batch memory usage and may offer no benefit if queries return very few rows.

There is no single optimal number for every system. You can test values such as 100, 500, 1,000, or 2,000 on representative data, then compare execution time, memory consumption, and network load. Test both small-result queries and large-result queries.

Row width matters as well. A batch of 1,000 rows containing just a few integer columns is far lighter than 1,000 rows containing long text or binary payloads. Never increase fetch size based purely on row counts while ignoring row width.

### 3.3. Fetch Size Does Not Replace Data Reduction

If an application only needs customer ID and total amount, select just those two columns instead of fetching entire rows. If it only needs data for a specific date range, include that filter in the query so the predicate can be pushed down to the remote server.

Increasing fetch size can reduce round trips for the same result set, but it does not reduce total bytes transferred. If a query is transferring 5 GB of unnecessary data, reducing the rows or columns is far more effective before tuning fetch size.

## 4. Pushing Computation to the Remote Server (Pushdown)

**Pushdown** is postgres_fdw's ability to offload part of a query's computation to the PostgreSQL server holding the source data. The remote server executes the computation near the data and sends only the needed results back to the calling server.

For example, the following query computes total revenue by region:

~~~sql
SELECT region, sum(amount) AS total_amount
FROM remote_sales
WHERE sale_date >= DATE '2026-01-01'
GROUP BY region;
~~~

If the predicate and aggregation are eligible for pushdown, the remote PostgreSQL instance can execute both WHERE and GROUP BY. Instead of transferring every transaction back to A, the system only needs to transfer aggregated totals per region.

Parts commonly eligible for pushdown include filter conditions on remote columns, the list of columns to read, certain expressions and sorts, joins between foreign tables on the same foreign server, and certain aggregates when expressions can be safely evaluated remotely.

Not every expression can be pushed down. Functions that exist only on the local server, casts with differing semantics, incompatible collations, or expressions the FDW deems unsafe can force part of the query to execute on A. Pushdown capability also depends on the PostgreSQL version and the FDW type.

### 4.1. Joins on the Same Remote Server

If two foreign tables point to the same PostgreSQL server and use compatible user mapping configurations, postgres_fdw can push the join down to that server when the join expressions are eligible:

~~~sql
SELECT o.order_id, c.customer_name
FROM remote_orders AS o
JOIN remote_customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00';
~~~

When the join is pushed down, the remote server can utilize indexes and statistics from both tables. Only the post-join result is transferred back to A, reducing network traffic.

### 4.2. Joins Across Two Servers or with a Local Table

If remote_orders resides on B while remote_customers resides on C, postgres_fdw cannot send a single standard join to one server to read both tables. PostgreSQL A must typically fetch data from each source and perform the join locally.

A similar situation occurs when joining a foreign table with a table that exists only on A. In that case, you need to control how many rows are fetched remotely before the join. You can filter the foreign table using pushable conditions, pre-aggregate at the source, or design a suitable data ingestion step if cross-server joins happen frequently.

This is why you need to inspect the actual SQL sent remotely rather than looking only at the application's SQL.

## 5. Measuring with EXPLAIN

Start with EXPLAIN to see how the planner intends to execute the query:

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

With **VERBOSE**, the foreign scan plan typically displays a **Remote SQL** section. This is the SQL that postgres_fdw intends to send to the remote server. Check whether key WHERE conditions appear, whether only needed columns are selected, whether aggregation or joins are performed remotely, and whether estimated row counts look reasonable.

Then measure actual execution time:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

**ANALYZE** executes the SELECT statement to gather actual metrics. Compare estimated rows against actual rows at key nodes. If there is a large discrepancy, check statistics, predicate selectivity, and how the data is changing.

Some caveats when reading the output:

- Timing on the foreign scan node reflects the time observed by the local process executing that node, including waiting for remote results. It does not separate processing time on B from network transfer time.
- BUFFERS in the plan on A describes buffers tracked by process A; do not interpret those numbers as PostgreSQL B's buffer metrics.
- EXPLAIN ANALYZE on A does not automatically show the full actual execution plan on B.

To understand what runs on B, take the statement from Remote SQL and run EXPLAIN directly on B. If you need to measure timing and buffers on B, run EXPLAIN ANALYZE on the corresponding query on B in an appropriate test environment. Combining metrics from both sides helps distinguish a slow remote query from a slow network link.

## 6. Performance Tuning Workflow

Tune in order from what generates data transfer to how data is transferred. This approach keeps every change targeted and easy to measure.

1. **Identify required data.** Replace SELECT * if only a subset of columns is used. Put filter predicates into the SQL and verify whether they are pushed down.
2. **Inspect the plan and Remote SQL.** Run EXPLAIN VERBOSE to see what is sent to the remote server. If WHERE or aggregation should run at the source but appears locally, look for expressions blocking pushdown.
3. **Update statistics.** If using local estimates, run ANALYZE on the foreign table after source data changes significantly. Compare estimated and actual row counts. For critical queries, test use_remote_estimate and measure both planning time and execution time.
4. **Tune fetch_size.** Once the query returns only the necessary data yet still spends excessive time on round trips, test increasing fetch_size. Record execution time, row count, row width, and memory usage.
5. **Tune the cost model.** If the planner frequently chooses plans that pull too many rows remotely, inspect fdw_tuple_cost. If plans generate many small remote accesses, inspect fdw_startup_cost. Adjust one parameter at a time.
6. **Check both servers and the network.** Measure CPU, memory, I/O, connection counts, and network latency on both A and B. If the query is already slow when run directly on B, raising fetch_size on A will not solve the root cause.

## 7. Complete Configuration and Query Example

The following example illustrates server, user mapping, and foreign table configuration. Hostnames, accounts, and passwords are sample values; replace them with your deployment environment details.

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER warehouse_srv
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host 'warehouse-db',
    port '5432',
    dbname 'warehouse',
    use_remote_estimate 'false',
    fdw_startup_cost '100',
    fdw_tuple_cost '0.2',
    fetch_size '500'
  );

CREATE USER MAPPING FOR app_user
  SERVER warehouse_srv
  OPTIONS (
    user 'readonly_user',
    password 'replace-with-managed-secret'
  );

CREATE FOREIGN TABLE remote_orders (
  order_id bigint,
  customer_id bigint,
  created_at timestamptz,
  total numeric
)
SERVER warehouse_srv
OPTIONS (
  schema_name 'sales',
  table_name 'orders'
);

ANALYZE remote_orders;
~~~

Query retrieving data for a date range and aggregating by customer:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT customer_id, sum(total) AS total_amount
FROM remote_orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

If Remote SQL contains the date predicate and GROUP BY, filtering and aggregation were pushed down to the source. If Remote SQL simply reads many rows and the local plan groups them afterward, investigate why the aggregate was not pushed down.

After capturing baseline metrics, test a larger fetch size for that specific table:

~~~sql
ALTER FOREIGN TABLE remote_orders
  OPTIONS (ADD fetch_size '1000');
~~~

Re-run the same query on the same data and load conditions. Record execution time, rows returned, and resource utilization. If execution time does not improve or memory usage spikes significantly, revert to a better-suited value.

To test remote estimates, update the server-level option:

~~~sql
ALTER SERVER warehouse_srv
  OPTIONS (SET use_remote_estimate 'true');
~~~

Then re-run EXPLAIN and compare planning time, chosen plan, estimated row counts, and execution time. Base configuration decisions on multiple representative queries rather than a single query.

## 8. Common Optimization Pitfalls

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Foreign scan returns a huge number of rows | Filter not pushed down or predicate too broad | Check Remote SQL, narrow rows at the source |
| Join plan has low cost but runs slowly | Stale statistics or inaccurate row estimates | ANALYZE foreign table, compare estimated rows vs. actual rows |
| Query is slow even though remote server is fast | Many fetch round trips or overly large result set | Test fetch_size, reduce returned columns and rows |
| Raising fetch_size brings no improvement | Time is mostly spent in remote execution or local processing | Benchmark the query directly on the remote server |
| Cross-source join creates large intermediate data | Tables on different foreign servers force local join | Filter or aggregate at each source before joining |
| Planning time increases after enabling remote estimate | Every plan generation queries the remote server | Measure planning time, enable only where necessary |

Common design pitfalls to avoid:

- **Only increasing fetch_size:** if the query transfers unnecessary data, total bytes transferred still will not drop.
- **Looking only at total cost:** cost is a planner estimate; always cross-check against actual execution time and row counts.
- **Enabling use_remote_estimate for every query without measuring:** better estimates can come with higher planning time.
- **Ignoring Remote SQL:** the application's SQL does not tell you what actually runs on the remote server.
- **Assuming joins always run at the source:** joins across multiple foreign servers or with local tables typically require processing on the calling server.
- **Setting fetch_size too high:** wide rows and high concurrency can create significant memory pressure.

## 9. Operational Principles

To sustain stable performance, monitor critical cross-server queries after any major data or configuration change. Record EXPLAIN plans, planning time, execution time, estimated and actual row counts, fetch_size, and active cost settings. These metrics establish a baseline when workloads shift.

Also distinguish shared settings from per-table settings. Server-level options affect multiple foreign tables, whereas table-level options suit individual tables with wide rows, large data volumes, or distinct access patterns. Choose the narrowest scope that meets your objective so adjustments remain predictable.

With postgres_fdw, strong performance typically comes from combining four factors: estimates accurate enough to choose good plans, pushdown to cut remote work and transferred data, fetch_size balanced between round trips and memory, and measurements on both local and remote servers. When tuned along these dimensions, cross-server queries can leverage data across multiple PostgreSQL servers while keeping latency and resource usage under control.
