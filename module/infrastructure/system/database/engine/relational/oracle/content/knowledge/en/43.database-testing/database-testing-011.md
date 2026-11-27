# Load Testing with Representative Data, Warm-Up, and Execution Plans

Oracle Database performance testing is only meaningful when test loads reflect how the system is actually used. A SQL statement that runs fast on a few hundred rows on a developer laptop will not necessarily run fast when the table holds tens of millions of rows, data distribution is skewed, many sessions access it concurrently, and caches are in a different state. Conversely, a slow initial run caused by cold caches or an uninitialized connection pool is insufficient to conclude a query is always slow.

To measure accurately, prepare representative data and workloads, control the environment, warm up the system per test objectives, measure across multiple runs, and inspect execution plans alongside runtime statistics. Three questions must be answered simultaneously: **what load did the system receive, how long did it take to process that load, and which plan did Oracle use to execute the SQL?**

## 1. Objectives of load testing

### 1.1. Distinguishing performance test types

| Test type | Objective | Example |
|---|---|---|
| Load test | Measure the system under expected operational load. | 200 concurrent users, 80 requests/second for 30 minutes. |
| Stress test | Push load beyond design limits to find capacity ceilings and degradation modes. | Ramp gradually from 100 to 500 then 800 requests/second. |
| Spike test | Verify response to sudden load surges. | Jump from 20 to 300 requests/second within seconds. |
| Endurance/soak test | Verify stability over prolonged runs. | Hold 60% capacity load for 8 hours. |
| Scalability test | Measure capacity gains when adding resources or instances. | Compare 4 CPUs vs. 8 CPUs or one node vs. two-node RAC. |
| Query benchmark | Compare a SQL query or group of queries under controlled conditions. | Measure a reporting query before and after creating an index. |

Different test types may share tools, but each requires distinct goals and pass/fail criteria. A load test does not automatically prove spike resilience or full-day stability.

### 1.2. Setting quantitative targets

Before running, define the metrics to capture and acceptance thresholds:

- **Throughput:** requests or transactions completed per unit time, e.g., requests/second or transactions/second.
- **Latency:** time to process a request/transaction. Record p50, p90, p95, p99, and maximum rather than averages alone.
- **Error rate:** percentage of failed requests, timeouts, deadlocks, SQL errors, or incorrect results.
- **Concurrency:** number of simultaneously active requests/sessions.
- **Resource utilization:** CPU, memory, I/O, network, connection pools, and `TEMP`.
- **Database work:** logical reads, physical reads, redo, parses, executions, rows processed, wait time, and session counts.

Example targets for an order lookup API:

| Metric | Illustrative target |
|---|---:|
| Throughput | 150 requests/second |
| p95 latency | Under 300 ms |
| p99 latency | Under 700 ms |
| Error rate | Under 0.1% |
| Database CPU | Not sustained above 80% in steady state |
| Connection pool | Zero pool exhaustion; connection wait time within threshold |

These numbers only illustrate how to write criteria. Real targets must derive from SLAs/SLOs, user behavior, infrastructure cost, and business criticality.

### 1.3. Measuring at both application and database layers

Request latency can accumulate waiting across many places:

```text
Client
  |
  v
Load balancer / API gateway
  |
  v
Application queue / worker
  |
  v
Connection pool wait
  |
  v
JDBC + network round trip
  |
  v
Oracle parse / execute / fetch
  |
  v
Application processing / serialization
  |
  v
Response
```

If API p95 rises while SQL duration stays flat, the bottleneck may lie in connection pools, thread pools, serialization, or networking. If SQL duration rises alongside logical reads or wait time, analyze the database. Never blame Oracle for every latency issue merely because the application uses Oracle.

## 2. Preparing representative data

### 2.1. Data volume must be near-realistic

Execution plans and performance depend on row counts, row widths, block counts, partitions, indexes, LOBs, and data churn. An overly small test table can cause Oracle to pick a full table scan even though production uses an index range scan, or vice versa.

When building datasets, consider:

- Current row counts and projected growth during the test horizon.
- Number of distinct values (NDV) for filter and join columns.
- Value distribution: uniform, skewed, many rare values, or a few dominant values.
- Proportions of `NULL`, empty strings, long values, and boundary values.
- Ratio of inserts/updates/deletes relative to read queries.
- Distribution across dates, months, statuses, tenants, or partitions.
- LOB sizes and the percentage of requests that actually read LOBs.
- One-to-many relationships, foreign keys, and join fan-out ratios.

Do not merely clone one sample row millions of times. Excessive duplication distorts NDV, histograms, selectivity, and compression ratios; the optimizer may choose plans completely unlike production.

### 2.2. Data must reflect real skew and cardinality

Suppose column `STATUS` has three values:

| STATUS | Real proportion |
|---|---:|
| `CLOSED` | 92% |
| `OPEN` | 7% |
| `ESCALATED` | 1% |

A query `WHERE status = 'CLOSED'` has vastly different selectivity than `WHERE status = 'ESCALATED'`. If the test dataset splits all three statuses evenly, optimizer row estimates will diverge sharply from production. Execution plans for two bind values can also differ.

For date columns, data may cluster in the most recent 30 days; for `CUSTOMER_ID`, a handful of large customers may hold far more orders than the rest. Preserve these characteristics because they govern index access, join order, join methods, and intermediate data volumes.

### 2.3. Relational data and integrity

Datasets should preserve:

- Realistic parent-to-child row ratios.
- Average and percentile row counts per group.
- Edge cases with zero related child rows if business rules allow.
- Constraints, unique keys, foreign keys, and enabled/validated states.
- Rare yet critical business states.
- Data patterns capable of causing lock contention, such as multiple requests updating the same account or inventory SKU.

A test using only customers with a single order fails to reflect join queries when major customers have thousands of orders. A test without concurrent writes to the same key misses write-path contention.

### 2.4. Sensitive data and masking

Never copy production data containing personal information into test environments without approval and safeguards. Use data masking or synthetic generation to preserve needed distributions and relationships without exposing real data.

When masking, preserve performance-relevant characteristics:

- String lengths and length distributions.
- Number of distinct values.
- `NULL` ratios and popular value frequencies.
- Distribution across partitions and time.
- Key relationships across tables.
- LOB presence ratios and LOB sizes.

Masking every value to a single constant string collapses NDV and alters compression. When data is used to test indexes, the optimizer, or joins, masking must preserve appropriate statistical properties.

### 2.5. Representative data for write workloads

If the system performs inserts/updates/deletes, test data must reflect:

- Commit frequency and transaction sizes.
- Contention levels on hot rows or index leaf blocks.
- Update frequency on indexed columns.
- Sequence/identity growth rates.
- Redo generation and archive log volume.
- Triggers, cascades, audits, and jobs generating extra work.

Benchmarking `SELECT` alone fails to show how new indexes slow down DML or whether a table suffers hot-block contention.

## 3. Preparing the measurement environment

### 3.1. Environments must be comparable

Record and lock as many variables as possible:

- Oracle Database version, Release Update, edition, and instance settings.
- CPU count, memory, SGA/PGA, storage type, IOPS, and network.
- RAC configuration, services, connection pools, and instance count.
- `optimizer_features_enable`, optimizer parameters, and `statistics_level`.
- Character set, timezone, NLS settings, and database compatibility.
- Schemas, indexes, partitions, constraints, and statistics.
- Application, JDK, JDBC driver, Hibernate version, and pool configuration.
- Background jobs, backups, ETL, monitoring, or concurrent workloads.

If the test environment is smaller than production, document the differences explicitly and never extrapolate linearly without evidence. A database with twice the CPU does not necessarily process twice the requests; bottlenecks may sit in I/O, locks, networking, or licensing/configuration limits.

### 3.2. Avoid uncontrolled competing workloads

Measurements skew if backups, stats gathering, batch ETL, purges, or another team's workload run during the test. Record such activities and pick clean measurement windows.

If the goal is testing peak operational hours, background workloads can form part of the test. Reproduce them intentionally and document the load ratio of each component rather than letting random jobs add noise.

### 3.3. Preparing statistics

The optimizer relies on statistics to estimate cardinality and cost. Newly loaded or heavily mutated datasets with stale statistics yield unrepresentative execution plans.

Example gathering schema statistics for testing:

```sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'APP_TEST',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

`AUTO_SAMPLE_SIZE` and `SIZE AUTO` let Oracle choose appropriate collection strategies based on stats and workload. This example is for test environments; never blindly run full-schema gathering on production during peak hours. Evaluate duration, lock/resource impact, and system statistics policies.

Check statistics timestamps:

```sql
SELECT table_name, num_rows, blocks, last_analyzed
FROM dba_tables
WHERE owner = 'APP_TEST'
ORDER BY table_name;
```

For critical columns:

```sql
SELECT table_name, column_name, num_distinct,
       num_nulls, histogram, last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP_TEST'
  AND table_name IN ('ORDERS', 'CUSTOMERS')
ORDER BY table_name, column_name;
```

Statistic values can be estimates; `NUM_ROWS` is not necessarily the exact row count at query time. When comparing data counts, run count queries or dedicated reconciliation checks.

### 3.4. Inspecting indexes and partitions

Before running, record:

```sql
SELECT index_name, table_name, status, visibility,
       uniqueness, blevel, leaf_blocks, clustering_factor
FROM dba_indexes
WHERE owner = 'APP_TEST'
ORDER BY table_name, index_name;
```

For partitioned tables:

```sql
SELECT table_name, partitioning_type, partition_count,
       subpartitioning_type
FROM dba_part_tables
WHERE owner = 'APP_TEST';
```

Verify partition keys, partition counts, sizes, and data distribution across partitions. A predicate that fails to reference the partition key or wraps the partition column in an unsuitable function can prevent partition pruning.

## 4. Load models and generating concurrency

### 4.1. Closed vs. open workloads

Two common load models:

- **Closed model:** fixed number of virtual users; each user sends a request, waits for a response, pauses for think time, and sends the next request. When the system slows down, request generation slows down automatically.
- **Open model:** requests arrive at a scheduled rate regardless of whether prior responses finished. When the system slows down, queues grow and expose true arrival-rate handling capacity.

Closed models suit simulating interactive user populations with think time. Open models suit testing APIs or event streams with near-fixed arrival rates. Picking the wrong model can mask saturation: closed models often cause coordinated omission because a slow system throttles the load generator itself.

### 4.2. Ramp-up, steady state, and ramp-down

Do not slam full peak load from second zero when measuring steady state. A typical scenario includes:

1. **Ramp-up:** increase users or arrival rate in steps.
2. **Warm-up:** allow caches, pools, and runtimes to stabilize; metrics from this phase are typically excluded from steady-state stats.
3. **Steady state:** sustain target load long enough to collect reliable metrics.
4. **Ramp-down:** reduce load cleanly and observe system recovery.

Example:

```text
Time          0       5       10       40       45 min
              |-------|-------|--------|--------|
Phase         ramp-up warm-up steady   ramp-down
Load          0 -> 100% 100%   100%     100% -> 0
```

Duration must be long enough for caches, connection pools, and batch/commit cycles to reach steady behavior. A 30-second test misses checkpoints, log switches, background cleanups, or memory pressure that only emerge over longer runs.

### 4.3. Think time and transaction mix

Real users do not fire requests back-to-back continuously in every scenario. They read screens, think, type inputs, or navigate pages. Think time alters concurrency and throughput.

A composite workload should mirror a transaction mix, for example:

| Transaction type | Illustrative share |
|---|---:|
| Order lookup | 55% |
| Customer lookup | 20% |
| Order creation | 10% |
| Status update | 10% |
| Summary report | 5% |

Real proportions must come from access logs, APM, audit logs, or business requirements. Never let a single query benchmark stand in for an entire application when production serves diverse transaction mixes.

### 4.4. Load generation tools

Common tools include JMeter, Gatling, k6, or internal harnesses. Whichever tool is chosen, ensure:

- Generators have ample CPU/network so they never become the bottleneck.
- Concurrency or arrival rates are explicitly controllable.
- Percentiles and error rates are captured.
- Inputs follow realistic distributions—never hammer the same key for every user unless production does.
- Timestamps are synchronized across generators, applications, and databases.
- Passwords, tokens, and personal data are never stored in test scripts/logs.

If a load generator shares a host with Oracle, it competes for CPU, memory, and network. For end-to-end system tests, running generators on separate machines yields cleaner results.

## 5. Warm-up: warming the system before measurement

### 5.1. Why can the first run differ?

Initial runs can be slower because several layers are cold:

- Database blocks are not yet in the buffer cache, requiring physical reads from storage.
- Shared pool lacks parsed cursors/metadata, requiring hard parses.
- Data dictionary cache and library cache are cold.
- Connection pools must open physical connections and complete authentication/session setup.
- The JVM must load classes, JIT-compile hot methods, and stabilize heap/GC.
- DNS, TLS handshakes, network routes, or application caches are not populated.
- Storage caches and OS page caches lack hot blocks.

Warm-up brings the system to a state near stable operation before measuring steady state. However, decide whether the test aims to measure cold starts, warm steady state, or both; first runs should not always be discarded blindly.

### 5.2. Distinguishing cold runs and warm runs

| Measurement type | State | Question answered |
|---|---|---|
| Cold run | Caches/pools/runtimes are not warmed up for the scenario. | What latency do the first users experience after a restart or cache eviction? |
| Warm run | Workload pre-run until caches/pools/runtimes stabilize. | What is performance during normal steady operation? |
| Mixed/realistic run | Combines cold paths, hot paths, and realistic key distributions. | How does the system respond to a realistic mix of new users, hot data, and cold data? |

Measure cold-start and warm steady-state separately when both matter. Never average them together, which hides both first-user pain and steady-state capacity.

### 5.3. Application-layer warm-up

Before steady state, you can:

- Initialize connection pools and verify connections.
- Exercise critical endpoints with representative inputs.
- Load classes and let the JVM JIT-compile hot paths.
- Populate application caches with TTLs and key distributions mirroring production.
- Run sample transactions so Hibernate builds metadata, prepares queries, and initializes proxies.

Warm-up must use the same request types and key distributions as the test itself. Calling one trivial endpoint leaves other code paths cold. Caching a single key fails to reflect multi-user hit ratios.

### 5.4. Oracle-layer warm-up

Oracle needs time for the buffer cache, shared pool, library cache, and internal structures to warm up to the workload. Pre-running representative queries warms frequently accessed blocks and cursors.

Never run flush commands like `ALTER SYSTEM FLUSH BUFFER_CACHE` or `ALTER SYSTEM FLUSH SHARED_POOL` on production just to stage cold/warm tests. These are system-wide operations that spike I/O and hard parses and disrupt other users. When cold-cache measurements are needed, use an isolated test environment with explicit authorization and runbooks.

Warm-up does not mean scanning an entire table with one artificial query. Run the representative transaction mix and key distribution. If production's working set exceeds the buffer cache, physical reads will persist in steady state; artificially warming the entire table creates an unrealistic state.

### 5.5. Connection pool warm-up

If a pool uses lazy initialization or low minimum idle counts, initial requests pay connection creation costs. To separate connection latency from SQL latency:

- Measure pool connection acquisition time separately.
- Track active/idle/pending connection counts.
- Warm up the pool to near target concurrency.
- Confirm the pool does not grow endlessly due to leaks or misconfiguration.

Never bump `maximumPoolSize` solely to mask wait times without measuring Oracle capacity. Too many concurrent connections increase context switching, memory overhead, and lock contention, slowing the database down.

### 5.6. Determining when warm-up has stabilized

Do not pick an arbitrary fixed loop count for every system. Monitor:

- p50/p95 latency over rolling intervals.
- Throughput and error rate.
- Active/idle connection counts and pool waits.
- Physical reads vs. logical reads.
- Hard parse/parse counts and shared pool activity.
- CPU, I/O latency, `TEMP`, and wait events.
- JVM JIT compilation/GC and heap occupancy.

Once key metrics plateau over a sustained interval without strong upward/downward drift, begin steady-state measurement. Document warm-up duration and warm-up exclusion rules in the report.

## 6. Execution plans in Oracle

### 6.1. What is an execution plan?

An execution plan describes how Oracle intends or chose to execute SQL: index vs. full table scan, join order, join methods, filtering, grouping, sorting, and partition access.

A plan typically contains operations such as:

| Operation | High-level meaning |
|---|---|
| `TABLE ACCESS FULL` | Scans table blocks sequentially. Not inherently bad; optimal when reading large fractions of a table. |
| `INDEX UNIQUE SCAN` | Looks up a single unique key in a unique index. |
| `INDEX RANGE SCAN` | Reads a range of keys in an index. |
| `TABLE ACCESS BY INDEX ROWID` | Uses `ROWID`s from an index to fetch table rows. |
| `NESTED LOOPS` | For each row from an outer input, probes matching rows in the inner input. |
| `HASH JOIN` | Builds/probes a hash table to join two datasets. |
| `MERGE JOIN` | Joins two datasets sorted on the join key. |
| `HASH GROUP BY` | Groups rows using a hash structure. |
| `SORT GROUP BY` | Sorts then groups data. |
| `SORT ORDER BY` | Sorts results into requested order. |
| `WINDOW SORT` | Sorts data for analytic/window functions. |
| `PARTITION RANGE ITERATOR` | Iterates over matching partitions. |

Never judge a plan solely by operation names. Full scans beat indexes when reading most of a table; hash joins excel on large inputs; nested loops excel when outer row counts are tiny and inner lookups are well-indexed.

### 6.2. Inspecting estimated plans with EXPLAIN PLAN

Example:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date < :to_date;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` does not execute the SQL. It asks the optimizer for an estimated plan using bind/parse context at explain time. This plan can differ from the actual runtime cursor due to bind values, bind peeking, adaptive cursor sharing, session settings, statistics, or child cursors.

Therefore, use `EXPLAIN PLAN` for structural previews, but when analyzing actual runtime performance, inspect the executed cursor.

### 6.3. Capturing runtime statistics

Request execution statistics for a SQL statement via the `GATHER_PLAN_STATISTICS` hint:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date < :to_date;
```

After the SQL completes in the same session, inspect the last cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

`ALLSTATS LAST` shows runtime statistics from the last execution that collected stats. The hint adds minor overhead; enable it only when measuring and compare against unhinted runs if overhead matters. Alternatively, `STATISTICS_LEVEL = ALL` can be scoped carefully after assessing impact.

When running through an application/pool, the SQL executes in a different session than the DBA's `DISPLAY_CURSOR` session. In that case, supply the exact `SQL_ID` and child number; `NULL, NULL` only inspects the most recent cursor in the current session as invoked.

### 6.4. Key columns to read in DBMS_XPLAN

| Column | Meaning |
|---|---|
| `E-Rows` | Optimizer's estimated row count for the operation. |
| `A-Rows` | Actual rows returned by the operation in the recorded execution. |
| `Starts` | Number of times the operation started. Read alongside `A-Rows`, especially under nested loops. |
| `Buffers` | Recorded logical reads/buffer gets. |
| `Reads` | Recorded physical reads. |
| `A-Time` | Recorded execution time at the operation per plan display conventions. |
| `OMem`, `1Mem`, `Used-Mem` | Memory usage for work-area operations. |
| `TempSpc` | Estimated/recorded `TEMP` space used by the operation depending on format/version. |
| `Predicate Information` | Which access/filter predicates applied at each step. |
| `Partition Information` | Which partitions were accessed or pruned. |

Never sum `A-Time` across all operations as independent intervals; parent node times include child work. Use the figures to pinpoint hotspots rather than treating each plan line as disjoint elapsed time.

### 6.5. Analyzing E-Rows vs. A-Rows discrepancies

When `E-Rows` diverges sharply from `A-Rows`, optimizer cardinality estimates are inaccurate. This can flip join order, join methods, index paths, and work-area sizing.

Example:

| Operation | E-Rows | A-Rows | Notes |
|---|---:|---:|---|
| Filter `STATUS='OPEN'` | 100 | 80,000 | Severely underestimated; check histograms, skew, and binds. |
| Join customers/orders | 5,000 | 4,800 | Estimate is quite close. |
| Nested loops inner lookup | 1 | 1, `Starts=80,000` | Single lookup repeated many times; inspect total logical reads and indexes. |

Numbers are illustrative. When `Starts` is large, `A-Rows` on a child operation may represent the cumulative sum across all starts; understand `DBMS_XPLAN` display rules before inferring per-start row counts.

Causes of bad estimates include:

- Stale or missing statistics.
- Skewed data without appropriate histograms.
- Unmodeled correlation across multiple columns.
- Predicates wrapping columns in functions or implicit conversions.
- Bind variables with widely varying selectivity.
- Function expressions or user-defined functions that obscure selectivity.
- Mismatched partition/global statistics.

Never create histograms or extended statistics reflexively. First identify affected columns and workloads, choose an appropriate stats strategy, and verify plans across diverse bind values.

### 6.6. SQL_ID, child cursors, and plan hashes

A single SQL statement can have multiple child cursors and multiple execution plans due to bind sensitivity, session settings, object changes, or other reasons. Looking at only one `SQL_ID` is not always enough.

Inspect cursors in `V$SQL`:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sql
WHERE sql_text LIKE 'SELECT%FROM APP.ORDERS%'
ORDER BY last_active_time DESC;
```

In production, `SQL_TEXT LIKE` can be imprecise and expose SQL contents; use the `SQL_ID` obtained from APM, traces, or appropriate views. `V$SQL` holds cumulative stats per child cursor in the shared pool, not per-request percentile latencies.

`PLAN_HASH_VALUE` identifies overall plan shape. Identical plan hashes do not guarantee identical runtimes because bind values, cache state, concurrency, I/O, and data vary.

## 7. Reading execution plans systematically

When analyzing slow SQL, follow a systematic sequence:

### Step 1: Identify the exact SQL and execution

Record `SQL_ID`, child number, module/action, service, representative bind values, execution timestamp, and transaction context. When applications use connection pools, set module/action via `DBMS_APPLICATION_INFO` or tracing to correlate SQL with requests.

### Step 2: Read operations bottom-up

Plan trees generally show child operations feeding parent operations. Identify the initial table/index access steps, applied predicates, join order, and row volume flowing through each node.

### Step 3: Compare E-Rows against A-Rows

Find the first major divergence in the plan. An early misestimate causes upstream operators to receive unexpected row counts and select suboptimal join methods.

### Step 4: Inspect logical reads and physical reads

High `Buffers` means the database processes many logical blocks. High `Reads` indicates physical I/O, though caching and read-ahead influence it. A query with low physical reads can still be slow due to CPU, latches, locks, or network.

### Step 5: Check sort/hash operations and TEMP

Check whether `SORT ORDER BY`, `HASH JOIN`, `HASH GROUP BY`, or `WINDOW SORT` receives excessive rows or spills to `TEMP`. Under-sized work areas spill to `TEMP` and inflate I/O.

### Step 6: Verify partition pruning and predicates

Confirm filters apply close to the data source, irrelevant partitions are pruned, and columns are not wrapped in conversions/functions that block index/partition access paths.

### Step 7: Test across diverse bind values

Test common, rare, and boundary values. A plan ideal for a small customer may perform poorly for a massive customer. Inspect child cursors/adaptive cursor sharing if plans shift.

## 8. Measuring time and resources repeatably

### 8.1. Do not rely on a single run

A single run is distorted by OS scheduling, caches, network jitter, GC, background processes, and competing workloads. For each scenario:

1. Run warm-up per defined rules.
2. Measure steady state over an adequate window.
3. Repeat across multiple independent runs.
4. Record p50/p95/p99, throughput, and error rates.
5. Compare distributions and variance across runs, not just means.

If runs fluctuate wildly, identify the source of variance before concluding a change improved performance.

### 8.2. Separating latency across layers

Applications should record at least:

- Time waiting for a pool connection.
- SQL execution time.
- `ResultSet` fetch/iteration time.
- Java processing and response serialization time.
- End-to-end latency from request arrival to response delivery.

A query with a fast `execute()` but slow `ResultSet` fetching still produces slow requests. Measuring only `executeQuery()` while ignoring the `rs.next()` loop omits fetch overhead.

### 8.3. Database statistics

Views such as `V$SQL`, `V$SQLSTATS`, `V$SESSION`, `V$SESSION_EVENT`, `V$SYSTEM_EVENT`, and `V$SYSSTAT` help monitor workloads. Take before/after snapshots or use monitoring tools to compute deltas; cumulative counters do not isolate a single request.

Example inspecting wait events for the current session:

```sql
SELECT event, total_waits, time_waited
FROM v$session_event
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
ORDER BY time_waited DESC;
```

These are cumulative session statistics whose time units depend on the view/column. Correlate with measurement intervals and never draw conclusions from raw cumulative totals on long-lived sessions.

### 8.4. SQL Trace and TKPROF

When detailed parse/execute/fetch, CPU, elapsed time, reads, and waits are needed, capture SQL trace for a targeted session or module using `DBMS_MONITOR` or equivalent mechanisms, then format with TKPROF.

Traces can capture SQL text, bind values, and sensitive data while adding overhead and disk files. Enable only narrowly, briefly, with proper authorization and cleanup plans. Never turn on system-wide tracing on production as a substitute for targeted instrumentation.

### 8.5. AWR, ASH, and SQL Monitor

In properly licensed environments, AWR/ASH and SQL Monitor provide historical workload data, active sessions, wait breakdowns, and long-running SQL progress. Several features belong to Oracle Diagnostics Pack or Tuning Pack; usage rights depend on edition, contracts, and organizational licensing. Never assume these views/reports are licensed in every environment. Without licenses, use permitted views and tools such as `V$SQL`, `DBMS_XPLAN`, SQL trace, and existing monitoring.

## 9. Bind variables and plan stability during measurement

### 9.1. Use bind values like the application

Benchmarking with literals can produce different cursors and plans than an application using bind variables. To measure real workloads, match bind types, lengths, data types, and statement preparation used by JDBC/Hibernate.

Example:

```sql
SELECT order_id, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status;
```

Run across diverse representative bind values: small customers, large customers, common statuses, and rare statuses. Never test only one favorable value.

### 9.2. Bind peeking and adaptive cursor sharing

The optimizer may inspect bind values during hard parse (bind peeking) and pick a plan based on estimated selectivity. With skewed data, a plan chosen for one bind value may be suboptimal for another. Oracle provides adaptive cursor sharing to maintain multiple child cursors for different bind selectivity buckets under supported conditions.

During tests, record `SQL_ID`, child cursor, plan hash, and bind values. Running the same SQL with different hardcoded literals on every iteration no longer represents application bind behavior.

### 9.3. Never force plans with hints before understanding the root cause

Hints like `INDEX`, `FULL`, `LEADING`, `USE_NL`, or `USE_HASH` alter plans. Apply hints only after gathering evidence, evaluating impact across diverse bind values, and establishing monitoring as data evolves.

If a plan shifts unexpectedly after a deployment or stats gathering, compare plans, statistics, binds, optimizer environments, and child cursors before forcing a plan. SQL Plan Management/baselines can help stabilize plans in appropriate environments, but never replace real load testing.

## 10. Example workflow for benchmarking an Oracle query

Suppose an endpoint retrieves the 20 latest orders for a customer. The objective is comparing before and after an index change.

### 10.1. Document the workload

- Share of overall traffic hitting this endpoint.
- Distribution of orders per customer: median, p95, and large-customer tail.
- Status distribution and queried date ranges.
- Expected concurrency and think time.
- Returned row count and percentage reading LOBs if any.

### 10.2. Benchmark SQL

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Bind `customer_id` and `status` with the exact application types. Vary customers and statuses according to realistic distributions.

### 10.3. Capture the actual execution plan

After execution:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS'
    )
);
```

`+PEEKED_BINDS` displays bind values peeked by the optimizer at hard parse if available and supported by the version. Never include outputs containing sensitive bind values in broadly shared reports.

### 10.4. Measure at the application layer

Use JMeter/Gatling/k6 or equivalent tools to drive the transaction mix. Configure ramp-up, warm-up, steady state, and ramp-down. Record p50/p95/p99, throughput, error rate, pool wait, SQL duration, and fetch duration.

### 10.5. Compare both options

| Metric | Before change | After change |
|---|---:|---:|
| p95 API latency | 420 ms | 260 ms |
| p99 API latency | 900 ms | 520 ms |
| Throughput | 110 req/s | 155 req/s |
| Error rate | 0.08% | 0.05% |
| Buffers/query | 18,000 | 5,200 |
| Physical reads/query | 120 | 25 |

These numbers are illustrative, not real measurements. During real evaluations, keep dataset, workload, bind distribution, environment, and warm-up identical. Also measure DML overhead and storage size of any new index; indexes that accelerate `SELECT` can slow down `INSERT`/`UPDATE`/`DELETE`.

## 11. Avoiding bias in results

### 11.1. Coordinated omission

If a load generator only sends the next request after the previous completes, a sluggish system throttles the generator. Reports show misleadingly low latency because requests that should have arrived during stalls were never issued.

For fixed arrival-rate workloads, use an open model or tools that record scheduled start times alongside actual start times. Report both queueing delay and service latency where supported.

### 11.2. Inconsistent cache state across runs

If run A starts on cold caches and run B runs on warm caches, direct comparisons are invalid. Specify clearly:

- Every run starts from a reproducibly reset cold state; or
- Every run executes an identical warm-up before measurement; or
- Cold and warm runs are measured separately for distinct goals.

Never flush production caches to force identical states. Use a resettable test environment and document cache preparation.

### 11.3. Different datasets or bind distributions

If run A queries small customers and run B queries large customers, latency differences cannot be attributed to an index change. Use deterministic seeds or reproducible input sets and log bind proportions by bucket.

### 11.4. Uncontrolled background workloads

Backups, stats gathering, ETL, or concurrent tests inflate I/O and CPU. Log concurrent activities and repeat measurements in a quiet window when needed.

### 11.5. Looking only at averages

Averages hide long tails. For example, 99 requests at 50 ms and one request at 5 seconds yield a modest average while p99 exposes the severe outlier. Always examine percentiles and latency distributions.

## 12. Reporting test results

A reproducible report should capture:

| Section | Contents |
|---|---|
| Objective | SLA/SLO, questions to answer, pass/fail criteria. |
| Environment | Oracle version, patches, CPU, memory, storage, RAC, JDK, JDBC, pool. |
| Data | Row counts, skew, NDV, partitions, LOBs, stats timestamps, masking method. |
| Workload | Transaction mix, arrival model, concurrency, think time, ramp-up, and duration. |
| Warm-up | Duration, request mix, stabilization criteria, warm-up sample exclusion rules. |
| Application results | Throughput, p50/p95/p99/max, error rate, queueing, and pool waits. |
| Database results | `SQL_ID`, child, plan hash, `E-Rows`/`A-Rows`, buffers, reads, CPU, waits, `TEMP`. |
| Confounders | Background jobs, cache state, generator saturation, environment errors. |
| Changes | Modified SQL, indexes, statistics, parameters, or configuration. |
| Conclusion | Results vs. thresholds, extrapolation limits, and next actions. |

Attach execution plans and logs stripped of credentials/sensitive binds. Record exact timestamps and timezones to correlate with APM, alert logs, and monitoring tools.

## 13. End-to-end practical workflow

1. **Define objective:** select load, stress, spike, endurance, or SQL benchmark; set SLA/SLO and pass/fail criteria.
2. **Build workload model:** transaction mix, arrival rate/concurrency, think time, ramp-up, and steady-state duration.
3. **Prepare data:** realistic scale, skew, NDV, relationships, LOBs, and DML ratios; mask sensitive data while preserving statistical shape.
4. **Lock environment:** record versions, patches, CPU, memory, storage, network, pools, statistics, and background workloads.
5. **Prepare observability:** APM, generator metrics, Oracle session/SQL statistics, execution plans, and synchronized timestamps.
6. **Run warm-up:** use the same request mix and bind distribution; isolate warm-up samples from steady-state metrics when measuring warm performance.
7. **Apply load:** run per chosen arrival model, collecting percentiles, throughput, error rates, and resource utilization.
8. **Inspect actual execution plans:** use `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics; compare `E-Rows`/`A-Rows`, buffers, reads, `TEMP`, and predicates.
9. **Change one variable at a time:** SQL, index, statistics, or config; never change multiple variables together when isolating root causes.
10. **Repeat:** keep dataset, bind distribution, warm-up, and load identical; compare across multiple runs.
11. **Assess side effects:** DML cost, index footprint, concurrency, errors, connection pools, and neighboring workloads.
12. **Archive report:** store runbooks, configs, plans, metrics, and caveats so others can reproduce results.

## 14. Principles to remember

- Test data must reflect production scale, skew, relationships, and read/write ratios.
- Tiny or overly uniform datasets produce unrepresentative plans and performance.
- Warm-up and cold runs answer different questions; always state which is being measured.
- Never flush production caches to stage a cold run.
- Use appropriate workload mixes and arrival models; avoid coordinated omission.
- Measure p50/p95/p99, throughput, and error rates, not averages alone.
- Separate connection acquisition, SQL execution, fetch, and application processing times.
- `EXPLAIN PLAN` is an estimate; inspect runtime plans with `DBMS_XPLAN.DISPLAY_CURSOR`.
- Compare `E-Rows` against `A-Rows` alongside `Starts`, `Buffers`, `Reads`, `A-Time`, and `TEMP`.
- Match application bind values and data types; test both common and rare values.
- Never force indexes or plans with hints before understanding cardinality and workloads.
- Control statistics, background jobs, versions, and resources across runs.
- Protect bind values, traces, plans, and logs as they may contain sensitive data.

## Conclusion

Oracle load testing delivers value when datasets preserve production-like scale and distributions, workloads mirror real concurrency and transaction mixes, and environments plus warm-up states are controlled across runs. Measure cold runs separately when post-restart experience matters; run explicit warm-ups before collecting warm steady-state metrics. Execution plans reveal how Oracle processes SQL, yet estimated plans never replace runtime statistics. Combining `DBMS_XPLAN.DISPLAY_CURSOR`, `E-Rows`/`A-Rows`, logical/physical reads, `TEMP`, and application-level p95/p99 metrics enables evidence-based bottleneck analysis and reproducible comparisons across changes.
