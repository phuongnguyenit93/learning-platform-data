# Measuring Queries and Detecting Performance Regressions

## 1. Why Measure Queries in a Spring Data JDBC Application?

A repository method may look like a single line of Java:

~~~java
Optional<PurchaseOrder> order = orders.findById(id);
~~~

Yet to execute that call, Spring Data JDBC may need to read the aggregate root row, load referenced entities, run additional `SELECT` statements for collections or property paths, convert the `ResultSet` into objects, and invoke configured callbacks/events.

Therefore, a repository method's latency does not depend solely on the first `SELECT`. A small change in mapping, query methods, indexes, or aggregate structure can multiply SQL statements, making queries slower or consuming more connections.

Performance regressions rarely appear as functional failures. The application still returns the right answers, yet:

- A request that previously ran 3 `SELECT`s now runs 40 `SELECT`s.
- A query switches from an index scan to a full table scan.
- p95 latency jumps from tens to hundreds of milliseconds.
- A screen loading a list of aggregates fires repeated queries per row.
- The connection pool frequently runs out of connections even without a major traffic spike.
- A batch job takes much longer after adding a relationship or callback.

To catch these early, measure across multiple layers: JDBC call counts, per-query duration, database execution plans, total use-case latency, and connection pool health.

## 2. Metrics to Track

Do not look solely at the duration of one SQL query. A use case can execute many fast SQL queries yet still have high total latency due to excessive round trips.

| Metric | Meaning | What It Detects |
| --- | --- | --- |
| Query count | Number of `SELECT`/`INSERT`/`UPDATE`/`DELETE` executions | N+1 queries, redundant queries, round-trip changes |
| Query duration | Time database takes to execute each statement | Slow SQL, lock waits, or poor plans |
| Total database time | Sum of SQL execution time within a use case | Overall database cost |
| Rows returned/affected | Number of rows returned or modified | Over-fetching or unexpected `UPDATE` scope |
| Execution plan | How database scans tables, uses indexes, and joins | Full scans, large sorts, expensive joins |
| Buffer/IO metrics | Data read from cache vs. storage | High-I/O queries |
| Connection pool active/idle | Active vs. available connections | Pool contention, long-held transactions |
| End-to-end latency | Total service/API time | Real latency experienced by users |
| Throughput | Requests or items processed per second | Overall processing capacity |
| p50/p95/p99 | Response time percentiles | Typical latency and slow tail cases |

Example of a request totaling 250 ms:

~~~text
Service duration: 250 ms
  Query A: 12 ms
  Query B: 9 ms
  Query C: 11 ms
  Query D: 8 ms
  Query E: 10 ms
  Query F: 9 ms
  ...
  Mapping, callbacks, Java processing, network, and overhead: remainder
~~~

Each individual query appears fast, yet if a request executes dozens of queries, total database time and round trips become a bottleneck.

## 3. Measuring SQL Executed by Spring Data JDBC

### 3.1. Temporarily Enabling SQL Logging

Spring JDBC uses `JdbcTemplate` to execute many persistence operations. You can enable logging to observe SQL:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

`JdbcTemplate` at `DEBUG` reveals executed SQL statements. `StatementCreatorUtils` at `TRACE` can show how parameters are bound.

Enable verbose logging only in development or during controlled diagnostic windows. Parameter logs can expose emails, phone numbers, addresses, tokens, or personal data. Never write sensitive data to production logs without proper masking or redaction.

### 3.2. SQL Logs Do Not Replace Query Metrics

Logs help inspect specific SQL statements, yet poorly answer automated questions such as:

- How many `SELECT`s did a service method issue?
- Which query consumes the most total time?
- Does query count grow as the result list grows?
- Did any SQL statement exceed a latency threshold?
- How many statements were inside a JDBC batch?

To measure those metrics, wrap the `DataSource` with JDBC monitoring instrumentation.

## 4. Using datasource-proxy to Count and Time Queries

**datasource-proxy** wraps a `DataSource` and lets listeners intercept before/after JDBC statement execution. The library provides listeners supporting:

- Logging SQL statements and parameters.
- Detecting queries exceeding a latency threshold.
- Counting `SELECT`, `INSERT`, `UPDATE`, `DELETE`.
- Measuring total query time.
- Tracking batch executions and connection IDs.
- Writing custom `QueryExecutionListener`s to collect application-specific metrics.

### 4.1. Adding the Dependency

With Gradle:

~~~groovy
runtimeOnly("net.ttddyy:datasource-proxy:<version>")
~~~

With Maven:

~~~xml
<dependency>
    <groupId>net.ttddyy</groupId>
    <artifactId>datasource-proxy</artifactId>
    <version><!-- pick version compatible with JDK and app --></version>
    <scope>runtime</scope>
</dependency>
~~~

Do not blindly copy a hardcoded version from an old example into your project. Pick a version compatible with your Java version and current dependency management.

### 4.2. Wrapping the DataSource

Example creating a proxy:

~~~java
DataSource monitoredDataSource =
        ProxyDataSourceBuilder
                .create(actualDataSource)
                .name("applicationDataSource")
                .countQuery()
                .logSlowQueryBySlf4j(500, TimeUnit.MILLISECONDS)
                .build();
~~~

Provide the wrapped `DataSource` to the Spring context so `JdbcTemplate`, Spring Data JDBC, and the transaction manager all use it. If you only create a local proxy while repositories keep using the raw `DataSource`, repository queries will not be measured.

### 4.3. Reading Query Counts

After invoking a use case:

~~~java
QueryCountHolder.clear();

orderService.loadOrderSummary(orderId);

QueryCount count = QueryCountHolder.getGrandTotal();

long selectCount = count.getSelect();
long updateCount = count.getUpdate();
long totalCount = count.getTotal();
long totalQueryTime = count.getTime();

QueryCountHolder.clear();
~~~

These metrics can be asserted in integration tests or logged for comparison across runs. `QueryCountHolder` uses a thread-local strategy by default; therefore, counts are collected on the current thread. If a use case dispatches database work to another thread, choose a suitable strategy or listener so queries are not missed.

### 4.4. Counting Queries vs. Counting Statements in a Batch

A `PreparedStatement` can be executed via `executeBatch()` with many parameter sets. Monitoring tools may record one batch execution while reporting a batch size indicating how many command sets were sent.

When reading metrics, distinguish:

- Number of JDBC `execute` calls.
- Number of logical queries in the batch.
- Number of bound parameter sets.
- Number of database rows actually affected.

Do not directly compare batch execution query counts against single-statement query counts without understanding how the tool counts batches.

### 4.5. Writing a Slow Query Listener

`QueryExecutionListener` receives callbacks before and after queries run. After execution, `ExecutionInfo` provides elapsed time, result, and any exception.

Conceptual example:

~~~java
long thresholdMillis = 500;

ProxyDataSourceBuilder builder =
        ProxyDataSourceBuilder.create(actualDataSource)
                .afterQuery((execution, queries) -> {
                    if (execution.getElapsedTime() >= thresholdMillis) {
                        // Log query fingerprint, datasource, elapsed time,
                        // and success/failure status.
                    }
                });
~~~

In production, log a query fingerprint or normalized SQL along with timing info. Avoid logging raw bind values if they may contain sensitive data.

## 5. Distinguishing Connection Pool Metrics from Per-Query Metrics

Spring Boot Actuator can automatically instrument `DataSource`s and publish metrics under the `jdbc.connections` prefix. These metrics describe connection pool health:

- Active connections.
- Idle connections.
- Maximum allowed connections.
- Minimum retained connections.

When using HikariCP, dedicated metrics appear under the `hikaricp` prefix.

Pool metrics help detect:

- A connection pool frequently near capacity.
- Requests waiting for connections.
- Transactions holding connections too long.
- A pool sized too small or too large.

However, pool metrics do not tell you which `SELECT` took 800 ms or which service method fired 30 queries. To measure individual queries, you need JDBC instrumentation such as `datasource-proxy`, P6Spy, or equivalent query observability.

| Tool | Primary Measurement Scope |
| --- | --- |
| Spring Boot Actuator DataSource metrics | Pool and connection state |
| HikariCP metrics | Active/idle/pending connections, acquisition wait time, and pool stats |
| datasource-proxy | Query count, query duration, slow queries, batch metadata, and listeners |
| P6Spy | Logging executed SQL and timing per configuration |
| Database statistics | Query fingerprints, execution stats, buffer/IO, locks, and plans per engine |

Never rely solely on pool metrics to conclude database queries are fast. A pool full of active connections can be caused by requests waiting on queries, long transactions, or code holding connections too long.

## 6. Detecting N+1 and Abnormal Query Count Growth

N+1 happens when one query loads a list of roots and then issues an extra query per root or per item in the list.

For example, a screen loading 50 orders:

~~~text
SELECT purchase_orders
SELECT lines for order 1
SELECT lines for order 2
SELECT lines for order 3
...
SELECT lines for order 50
~~~

If query count grows linearly with the number of orders, investigate whether the application is loading relationships aggregate by aggregate.

Spring Data JDBC does not use lazy loading like JPA. When loading aggregates, the framework uses mappings and relational queries per aggregate/property path. Actual SQL counts depend on the operation, relationship types, and how queries are declared. Therefore, measure real use cases rather than assuming every `findAll` causes N+1 or every collection loads via a single `JOIN`.

### 6.1. Comparing Query Counts Across Dataset Sizes

One way to spot regressions is running the same use case on different dataset sizes:

| Aggregate Roots | Measured `SELECT` Count |
| ---: | ---: |
| 1 | 2 |
| 10 | 11 |
| 50 | 51 |

If query count grows by roughly one statement per aggregate, repeated per-root querying may be occurring. This is a signal to investigate, not standalone proof: some use cases intentionally load aggregates one by one and query counts naturally scale with data.

### 6.2. Asserting Query Counts in Integration Tests

Example:

~~~java
@DataJdbcTest
class OrderRepositoryQueryCountTest {

    @Autowired
    OrderRepository orders;

    @Test
    void loadingOrdersShouldStayWithinQueryBudget() {
        // Prepare fixture containing multiple orders and order lines.

        QueryCountHolder.clear();

        List<PurchaseOrder> result =
                orders.findByStatus(OrderStatus.OPEN);

        QueryCount count = QueryCountHolder.getGrandTotal();

        assertThat(result).hasSize(20);
        assertThat(count.getSelect()).isLessThanOrEqualTo(5);

        QueryCountHolder.clear();
    }
}
~~~

This example assumes the test `DataSource` is wrapped with `datasource-proxy` and the budget of 5 reflects the repository's expected behavior. Never copy an arbitrary number into real tests. Measure a baseline first, then set a reasoned budget.

Assert both result count and query count. A test asserting only query count can pass even if the query drops data or returns incomplete results.

## 7. Analyzing Execution Plans

When a query is slow, the next step is checking how the database executes it.

Execution plans show what the database estimates or actually performs:

- Full table scan vs. index usage.
- Which index was chosen.
- Nested loop, hash join, or merge join.
- Estimated vs. actual row counts.
- Large sorts, aggregations, or temporary operations.
- Heavy storage block reads.

### 7.1. EXPLAIN on PostgreSQL

Example:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC
LIMIT 50;
~~~

The plan shows scan nodes, indexes, and estimated costs. For actual execution numbers:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_order
WHERE status = 'OPEN'
ORDER BY created_at DESC
LIMIT 50;
~~~

`ANALYZE` actually executes the statement and adds actual timings and row counts per node. `BUFFERS` reports blocks hit in cache, read, written, or dirtied.

Note: `EXPLAIN ANALYZE` does not merely plan. For `SELECT`, the query actually executes; for `INSERT`/`UPDATE`/`DELETE`, data changes also execute. When testing DML on PostgreSQL without keeping changes, wrap it in a transaction and `ROLLBACK`:

~~~sql
BEGIN;
EXPLAIN ANALYZE
UPDATE purchase_order
SET status = 'ARCHIVED'
WHERE status = 'COMPLETED';
ROLLBACK;
~~~

Rollback does not undo external side effects outside the transaction, such as actions triggered externally by database triggers. Run only in test environments and understand any active triggers.

### 7.2. Reading Key Plan Signals

| Signal in Plan | What to Check |
| --- | --- |
| `Seq Scan` on large table | Is predicate selective enough, is an index missing, are planner statistics stale? |
| `Index Scan`/`Index Only Scan` | Are index columns ordered properly and covering the query? |
| `Actual Rows` far from `Plan Rows` | Stale statistics, skewed distribution, or hard-to-estimate selectivity |
| `Nested Loop` with huge loop count | Is the inner side executing repeatedly too many times? |
| `Sort`/`Hash` using lots of memory or temp | Is an index needed, can result sets be bounded, or should query change? |
| High `Buffers read` | Query is reading many pages from storage |
| High `Rows Removed by Filter` | Predicate filters out rows after scanning too many rows |

Do not conclude `Seq Scan` is always bad. On small tables or queries returning most rows, a sequential scan can be the optimal plan. The goal is checking whether the plan fits the data and workload.

### 7.3. Syntax Differs by Database

`EXPLAIN` is not a standardized SQL command with identical syntax across all engines. PostgreSQL, MySQL, SQL Server, and Oracle each have their own plan tools. Consult your production database's documentation.

## 8. Measuring Spring Data JDBC Overhead Beyond SQL Alone

A repository method has costs outside the database too:

- Waiting to acquire a connection from the pool.
- Preparing statements and binding parameters.
- Network round-trip latency.
- Data type conversion.
- Instantiating the aggregate root and child entities.
- Executing callbacks or event listeners.
- Java-side data processing.

Therefore, measure both layers:

1. **Database time:** total SQL execution time.
2. **Application time:** time from invoking the service/repository until receiving the result.

If database time is low while application time is high, inspect mapping, callbacks, Java processing, connection acquisition, and network. If query time is high, examine execution plans, lock waits, I/O, and indexes.

### 8.1. Measuring Percentiles

Suppose benchmark results show:

| Metric | Before Change | After Change |
| --- | ---: | ---: |
| p50 | 35 ms | 32 ms |
| p95 | 90 ms | 160 ms |
| p99 | 180 ms | 420 ms |
| Query count/request | 4 | 18 |

The median may look fine while p95/p99 and query count degraded badly. Inspect latency distributions rather than looking only at averages.

### 8.2. Warm-Up and Repeated Runs

A single measurement is easily skewed by:

- Uncompiled JVM JIT code.
- Freshly initialized connection pool.
- Cold database caches.
- OS page cache.
- Background jobs or other database activity.
- Overly tiny test datasets.

Run warm-up iterations, take repeated measurements under the same environment, and report percentiles. If measuring cold starts, design a separate scenario rather than mixing cold and warm runs into one number.

## 9. Testing Against a Near-Production Database

**`@DataJdbcTest`** is useful for repository tests. Spring Boot auto-configures `DataSource`, `JdbcTemplate`, and Spring Data JDBC repositories. By default, this slice uses an embedded database if present and runs each test inside a rolled-back transaction.

Embedded databases fit basic mapping checks, yet do not guarantee production-like execution plans, index behavior, collations, locking, or data types.

If production uses PostgreSQL, MySQL, or SQL Server, run integration/performance tests on the same engine and close version. Testcontainers can run a real database in a container to verify:

- SQL generated by Spring Data JDBC.
- Indexes and execution plans.
- Data types, JSON, timestamps, and collations.
- Locks, isolation, and transactions.
- Query counts with real aggregate mappings.

### 9.1. `@DataJdbcTest` and Test Transactions

**`@DataJdbcTest`** wraps tests in transactions and rolls back afterward by default. This is convenient for repository and query-count tests.

If measuring commit latency or real transaction behavior, outer test-framework transactions can skew results compared to production. Disable test transactions with appropriate propagation or write dedicated service transaction tests.

### 9.2. Using Representative Data

A table with 20 rows cannot prove an index works on 20 million rows. Test datasets should reflect:

- Realistic row counts and child row counts.
- Distributions of statuses, timestamps, and search keys.
- `NULL` and duplicate ratios.
- Number of aggregates with large collections.
- Read/write ratios.
- Common and rare parameter values.

Do not just generate uniform random rows. Data skew and selectivity can completely change execution plans.

## 10. Catching Regressions with Tests and Baselines

Performance regressions can sneak in when:

- Adding a collection property to an aggregate.
- Replacing a derived query with a custom query.
- Changing mappings or converters.
- Adding a callback that fires an extra query.
- Dropping or altering an index.
- Changing `WHERE` or `ORDER BY` predicates.
- Increasing average child data per aggregate.
- Upgrading Spring Data JDBC or the JDBC driver.

A regression-detection workflow should be multi-layered.

### 10.1. Query Count Tests

Set budgets for critical use cases:

- Loading aggregate details.
- Loading a paginated list.
- Creating an aggregate with collections.
- Updating an existing aggregate.
- Running a bulk operation.

Query counts are usually much more stable than wall-clock timings in CI. If query counts jump suddenly, tests warn immediately even if fast CI machines mask timing drift.

### 10.2. Result-Size Guard Tests

Verify:

- Page sizes are enforced.
- Queries do not fetch excessive columns or rows.
- Collections are not loaded when the use case does not need them.
- Projections genuinely select only needed fields.

A query can appear fast on a small dataset while returning hundreds of thousands of unnecessary rows later.

### 10.3. Targeted Execution Plan Checks

Do not snapshot entire execution plans as rigid strings on every CI run. Plans can change across database versions, statistics, and data. Instead:

- Confirm queries use required indexes given matching predicates and data.
- Track actual rows, loops, buffers, and execution time.
- Compare plans against a pinned database and dataset.
- Investigate major shifts rather than failing builds on minor planner variations.

### 10.4. Thresholded Performance Tests

For critical flows, define budgets:

- p95 latency stays below an agreed threshold.
- Query count stays within expected limits.
- Throughput does not drop beyond allowed tolerance.
- Connection pool does not persistently hit max capacity.

Thresholds must come from realistic baselines. Avoid overly tight thresholds that cause flaky failures due to noisy CI runners.

## 11. Monitoring Production and Slow Queries

Tests catch problems before deployment, whereas production metrics reveal real workloads.

Monitor:

- Query fingerprints and execution counts.
- Total duration and percentiles per query fingerprint.
- Error, timeout, and deadlock counts.
- Rows returned/affected if supported by instrumentation.
- Connection pool active, idle, and pending counts.
- Database CPU, I/O, buffer cache, lock waits.
- Endpoint request latency and throughput.

### 11.1. Normalizing Query Fingerprints

Two SQL statements differing only in parameter values represent the same query family:

~~~sql
SELECT id, status FROM purchase_order WHERE customer_id = 101;
SELECT id, status FROM purchase_order WHERE customer_id = 202;
~~~

Group them under a normalized form:

~~~sql
SELECT id, status
FROM purchase_order
WHERE customer_id = ?;
~~~

This identifies high-frequency or high-total-time queries without creating separate metrics per parameter value.

### 11.2. Do Not Put Arbitrary Parameters in Metric Labels

Using emails, customer IDs, or full SQL containing literals as metric labels can explode time-series cardinality. That creates high cardinality and overloads metrics backends.

Use query fingerprint, datasource, operation name, or endpoint as stable dimensions. Keep sensitive parameters out of metric labels and regular logs.

### 11.3. Slow Query Thresholds

Slow query thresholds should reflect SLAs and actual distributions. A 200 ms `SELECT` might be acceptable in a background report yet unacceptable in an endpoint with a 100 ms SLA.

Do not log only queries exceeding one global threshold. Categorize by use case, endpoint, or query fingerprint.

## 12. Common Causes of Regressions in Spring Data JDBC

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| Query count scales with aggregate count | Repeated relational queries per root or per-item processing | Count queries across varying input sizes; inspect repeated SQL fingerprints. |
| A `SELECT` slows down as table grows | Missing index, stale statistics, or plan shift | Run `EXPLAIN`/`EXPLAIN ANALYZE` on target database. |
| Repository returns huge object graphs | Aggregates have many children or queries over-fetch fields | Measure row/column counts; use projections for read-only reports. |
| p95 spikes while p50 stays flat | Certain parameters have poor selectivity or lock contention | Group by query fingerprint and normalized parameters; check plans and locks. |
| Connection pool repeatedly exhausted | Slow queries, long transactions, or unclosed streams | Monitor pool active/pending, transaction duration, and `Stream` lifecycles. |
| Aggregate save slows after adding collection | Updates perform child deletes/inserts | Count `INSERT`/`DELETE`/`UPDATE` and inspect collection sizes. |
| Queries fast in tests yet slow in production | Dataset, indexes, statistics, or database engine differ | Use real database and representative data in integration/performance tests. |
| SQL logs grow huge | Full query/parameter logging left on in production | Enable only briefly, filter queries, and mask sensitive values. |
| Query metrics spike after deploy | New code path calls repository repeatedly or retries in a loop | Compare fingerprints, request traces, query counts, and deployment timeline. |

## 13. Workflow for Investigating a Performance Regression

When an endpoint or batch job slows down after a change, follow these steps in order:

1. **Identify the use case:** which endpoint/service slowed down and when did it start?
2. **Compare latencies:** p50, p95, p99, throughput, and error rate before vs. after.
3. **Measure query counts:** did `SELECT`/`INSERT`/`UPDATE`/`DELETE` counts per call increase?
4. **Find top query fingerprints:** which SQL statements have the highest frequency or total time?
5. **Check connection pool:** are requests waiting for connections?
6. **Capture execution plans:** how is the database scanning, joining, sorting, and buffering?
7. **Compare data:** did row counts, value distributions, indexes, or statistics change?
8. **Inspect mappings:** did the aggregate gain new collections, callbacks, or converters?
9. **Add a regression test:** lock down query count or an appropriate performance budget.
10. **Re-measure after fixing:** compare using the same dataset, engine, and load scenario.

## 14. Practice Exercises

**Exercise 1 — Enable SQL logging.** Turn on `DEBUG` for `JdbcTemplate`, run a repository method, and record every SQL statement. Distinguish root queries from relationship-loading queries.

**Exercise 2 — Count queries.** Wrap the `DataSource` with `datasource-proxy`, call a service method, and read `QueryCountHolder`. Compare `SELECT` counts when loading 1 vs. 20 aggregates.

**Exercise 3 — Detect N+1.** Create a list of aggregates with child collections. Measure query counts as the list grows from 1 to 10 and 50 items.

**Exercise 4 — Slow query listener.** Set a 200 ms threshold on `datasource-proxy` and log queries exceeding it. Confirm logs capture datasource, query fingerprint, duration, and status.

**Exercise 5 — Execution plans.** Run `EXPLAIN` and `EXPLAIN ANALYZE` on a customer search query. Compare estimated rows, actual rows, scan type, and buffer usage.

**Exercise 6 — Index regression.** Run the same query before and after creating an appropriate index. Measure plan and timing on a sufficiently large dataset.

**Exercise 7 — `@DataJdbcTest` with a real database.** Run repository integration tests on Testcontainers matching the production engine. Verify queries, mappings, and index behavior.

**Exercise 8 — Query count budget.** Add a test capping `SELECT` count for a critical use case. Alter the mapping to generate extra queries and confirm the test catches the regression.

**Exercise 9 — Connection pool.** Observe active/idle/pending connections as concurrent requests increase. Correlate with query duration and transaction duration.

**Exercise 10 — End-to-end comparison.** Measure service latency alongside total database time. Introduce a slow callback or Java calculation to demonstrate why low query time alone does not guarantee a fast service.

## 15. Key Takeaways

Measuring Spring Data JDBC performance requires looking at query counts, execution durations, execution plans, returned data volume, connection pools, and end-to-end use-case latency. Individual SQL statements may look fast while repeated queries still degrade request latency.

Enable SQL logging to inspect statements, use `datasource-proxy` or equivalent tools to count queries and detect slow queries, use Spring Boot Actuator to monitor connection pools, and use the database's `EXPLAIN` to understand how queries execute.

In tests, lock down query counts for critical use cases to catch N+1 or redundant queries. Measure performance against the real database engine and representative data. Compare p50/p95/p99, throughput, and total database time instead of relying only on averages or single runs.

`EXPLAIN ANALYZE` actually executes the statement; especially for `INSERT`/`UPDATE`/`DELETE`, understand side effects and transactions before running it. SQL and parameter logs can contain sensitive data, so enable them selectively and use normalized query fingerprints for metrics.

### References

- [Spring Data Relational – Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Boot – Actuator Metrics and DataSource Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [datasource-proxy – User Guide](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/)
- [datasource-proxy – QueryCount API](https://javadoc.io/static/net.ttddyy/datasource-proxy/1.11.0/net/ttddyy/dsproxy/QueryCount.html)
- [PostgreSQL – EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
- [Spring Boot – Testing Spring Data JDBC Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
