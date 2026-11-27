# Measuring SQL Statement Counts, Connection Usage, Latency, and Result Size

Optimizing Spring Data JDBC performance requires metrics across multiple layers. A single repository call can generate multiple SQL statements; a single transaction can borrow one connection from the pool and reuse it across multiple statements; a SELECT query can be fast on the database side yet return too many rows, causing the application to spend excessive time and memory.

Therefore, when measuring a use case, you should track at least four groups of metrics:

1. **SQL statement count:** how many statements are executed, which SELECT/INSERT/UPDATE/DELETE types they belong to, and whether the count grows with the number of aggregates.
2. **Connection usage:** how many times the application borrows/returns a connection from the pool, how many connections are active/idle in the pool, and whether threads wait for connections.
3. **Timing:** total use case duration, per-statement duration, connection acquisition wait time, and database execution time.
4. **Result size:** number of rows returned, size of materialized data, and payload size the application actually sends out.

These four groups complement one another. Measuring total duration alone does not reveal whether the bottleneck is in SQL, the pool, mapping, or serialization. Counting SQL statements alone does not tell you whether a query returns ten rows or one million rows.

## 1. Define the Measurement Boundaries

Before adding instrumentation, pick a concrete use case, such as loading an order detail page or searching for a customer list.

A typical flow looks like this:

```text
HTTP request
    |
    v
Application service
    |
    +--> Spring Data JDBC repository
    |       |
    |       +--> DataSource / connection pool
    |                 |
    |                 +--> JDBC statements
    |                           |
    |                           v
    |                        Database
    |
    +--> Mapping aggregate / DTO
    |
    +--> Serialize response
    |
    v
HTTP response
```

Each layer has a different kind of time:

| Boundary | Metrics to measure |
| --- | --- |
| HTTP/service | Total use case duration, success/error, call count. |
| Repository | Repository call count and duration per operation. |
| DataSource | Connection borrow/return counts, pool wait time. |
| JDBC statement | Statement count, SQL type, execution time, batch size. |
| ResultSet/materialization | Rows read, mapping time, and data retained in memory. |
| Response | Item count and payload bytes after serialization. |

Do not lump everything into a single metric named "database time". The duration of a repository call can include connection wait, parameter binding, sending SQL, waiting on the database, reading the ResultSet, and converting data into objects.

## 2. SQL Statement Count Does Not Equal Repository Call Count

One repository call does not necessarily correspond to one statement.

For example:

```java
PurchaseOrder order = orders.findById(orderId).orElseThrow();
```

Depending on aggregate mapping and how owned components are loaded, Spring Data JDBC may need multiple statements to read the root and collection/child rows. Similarly, saving an aggregate with multiple components can generate multiple INSERT/UPDATE/DELETE statements.

Factors that change the statement count:

- How many mapped collections the aggregate has.
- How many aggregates the query needs to load.
- Whether a query executes once or repeats inside a loop.
- Whether the repository method executes a count query or additional queries.
- Whether custom queries, auditing, callbacks, or other side operations are used.
- How the driver/database executes batches.

Therefore, to know the actual SQL count, measure at the JDBC/DataSource boundary rather than inferring it from lines of code or repository method calls.

### 2.1. Detecting N+1 Queries

N+1 typically occurs when the application loads a list of N aggregates and then executes an additional query for each aggregate.

For example:

```java
List<Customer> customers = customerRepository.findAll();

for (Customer customer : customers) {
    List<PurchaseOrder> orders =
        orderRepository.findByCustomerId(customer.id());
    // Build display content.
}
```

If the list has 50 customers, this flow can issue 1 query to load customers and 50 more queries to load orders. Total queries scale with N.

A useful measurement technique is to run the same use case with datasets of 1, 10, and 50 records and compare statement counts. If the SQL count grows roughly linearly with the number of aggregates, check for N+1 or a repeated query in application code.

Not every query count that scales with N is a bug. In some cases, business logic genuinely requires per-aggregate operations. Still, measuring the trend helps identify what needs optimization.

## 3. Measuring SQL with DataSource Instrumentation

To count statements independently of repositories, you can instrument the DataSource. A proxy at the JDBC layer observes PreparedStatement creation, execution, batching, and execution time.

Common options:

| Tool | Purpose |
| --- | --- |
| datasource-proxy | Wraps DataSource, listens to query execution, counts and times statements. |
| P6Spy | Logs SQL and timing to diagnose actual statements. |
| Micrometer | Records metrics/timers and exports data to observability systems. |
| JDBC/database telemetry | Supplements metrics from the driver, pool, and database engine. |

Using a proxy for metrics and using SQL logging for debugging serve two different purposes. Logging every statement in full is helpful during local investigation, but can produce massive log volume and expose sensitive data if enabled in production.

### 3.1. Illustrating datasource-proxy

The datasource-proxy library provides `QueryExecutionListener` to receive callbacks before and after a statement runs.

```java
public class SqlMetricsListener implements QueryExecutionListener {

    private final MeterRegistry registry;

    public SqlMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {
        // Record start timestamp if needed.
    }

    @Override
    public void afterQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {

        Timer.builder("app.jdbc.query")
            .tag("success",
                Boolean.toString(executionInfo.isSuccess()))
            .register(registry)
            .record(
                executionInfo.getElapsedTime(),
                TimeUnit.MILLISECONDS
            );

        for (QueryInfo queryInfo : queryInfoList) {
            // Classify statement and increment the corresponding counter.
            // Do not put raw parameters or full SQL into metric tags.
        }
    }
}
```

This listener illustrates how to record a Timer; you need to add the appropriate datasource-proxy and Micrometer dependencies for your application. When creating the proxy, wrap the actual DataSource and ensure Spring Data JDBC and other JDBC clients use that wrapper.

Example wrapper initialization:

```java
DataSource instrumentedDataSource =
    ProxyDataSourceBuilder
        .create(actualDataSource)
        .name("application")
        .listener(sqlMetricsListener)
        .build();
```

In Spring Boot, configure the wrapper as the DataSource used by repositories while keeping the real pool underneath. Do not create a second Hikari pool just to measure SQL. If the application already has a custom DataSource configuration, integrate the proxy into that configuration and verify that Actuator/metrics still observe the underlying pool properly.

### 3.2. Counting by Statement Type

You should maintain separate counters for each group:

- SELECT.
- INSERT.
- UPDATE.
- DELETE.
- Batch execution.
- Failed statements.

Classify SQL using a parser or instrumentation metadata when available. Simple regex on SQL strings can misclassify statements that start with comments, CTEs, or database-specific syntax.

A metric set might look like:

```text
app.jdbc.statements{operation="SELECT"}  = 120
app.jdbc.statements{operation="INSERT"}  = 8
app.jdbc.statements{operation="UPDATE"}  = 14
app.jdbc.statements{operation="DELETE"}  = 2
app.jdbc.statement.errors                = 1
```

The numbers above are examples only. Measure within a specific time window or request scope if you want to know the cost of each use case.

### 3.3. Batches and SQL Statement Counts

A JDBC batch can contain multiple parameter sets for the same statement. Therefore, distinguish between:

- Number of statement/batch executions.
- Number of parameter sets in the batch.
- Number of rows actually affected in the database.

For example, an INSERT batch of 100 parameter sets may be 1 batch execution call while inserting 100 rows. Do not use a single counter and label it generically as "SQL count" without defining how it is counted.

## 4. Measuring Time: Query, Connection, and Use Case

There are at least three kinds of time to distinguish:

1. **Use case duration:** from when the service starts until it completes.
2. **Connection acquisition time:** time spent waiting for the pool to provide a connection.
3. **Statement execution time:** time from JDBC execute until the driver returns control.

In addition, reading the entire ResultSet and materializing aggregates can continue after execute returns, depending on the driver and how the framework consumes data. Thus, statement elapsed time does not necessarily equal the entire repository call time.

### 4.1. Measuring Use Case Duration with Micrometer

Example using Timer:

```java
@Service
public class CustomerQueryService {

    private final CustomerRepository customers;
    private final Timer searchTimer;

    public CustomerQueryService(
            CustomerRepository customers,
            MeterRegistry registry) {
        this.customers = customers;
        this.searchTimer = registry.timer(
            "app.customer.search.duration"
        );
    }

    public List<Customer> findActiveCustomers() {
        return searchTimer.record(
            () -> customers.findByActiveTrue()
        );
    }
}
```

A Timer can provide count, total time, and distribution statistics depending on registry configuration. In a real application, instrument at the service/use case boundary to encompass all persistence and mapping work belonging to the use case.

If using annotations such as `@Timed`, configure the corresponding Micrometer/AOP support. Do not assume that merely adding the annotation automatically instruments every method across all Spring Boot versions.

### 4.2. Measuring Statement Duration

A DataSource proxy can record the elapsed time of each query. When reading the numbers, distinguish:

- Duration of a single statement.
- Cumulative duration of all statements in a request.
- Wall-clock time of the request.

If a request executes 20 queries in parallel, cumulative query elapsed time can exceed wall-clock time. In standard imperative Spring Data JDBC, operations usually run sequentially on the same thread, yet you should still not assume that summing query times always equals service duration.

### 4.3. Percentiles Matter More Than Averages Alone

An average can hide a group of very slow requests. Tracking p50, p95, and p99 helps reveal tail latency:

| Metric | Interpretation |
| --- | --- |
| p50 | A typical request at the median of the distribution. |
| p95 | 95% of requests complete at or below this value. |
| p99 | The slowest tier of requests, useful for spotting tail latency. |
| max | Highest observed value; sensitive to outliers. |

Combine percentiles with throughput and error rate. Rising p99 under high load can point to connection pool contention, lock contention, query plans, or database saturation.
## 5. Measuring Connection Acquisitions and Physical Connections

The phrase "connection count" can refer to different events. Define it clearly before creating metrics.

| Metric | Meaning |
| --- | --- |
| Connection acquisition | Number of times the application requests a connection from the DataSource/pool. |
| Connection release | Number of times the application returns a connection to the pool or closes the logical handle. |
| Physical connection creation | Number of times the pool opens a new physical connection to the database. |
| Active connections | Number of connections currently borrowed from the pool by the application. |
| Idle connections | Number of connections currently idle in the pool. |
| Pending borrowers | Number of threads waiting for the pool to grant a connection. |
| Acquisition duration | Time from requesting a connection until receiving one. |

One transaction can borrow a single connection and use it for many statements. Thus, 30 SQL statements inside one transaction does not mean the application opened 30 connections.

Conversely, without a transaction wrapping multiple operations, a connection may be borrowed and returned per operation depending on how the repository and transaction infrastructure execute.

### 5.1. HikariCP Connection Pool

Spring Boot commonly uses HikariCP as the connection pool when the appropriate dependency is present. The pool manages physical connections, reuses them across requests, and exposes metrics.

Common Hikari metrics:

- `hikaricp.connections.active`: connections currently borrowed.
- `hikaricp.connections.idle`: connections currently idle in the pool.
- `hikaricp.connections.pending`: threads waiting for a connection.
- `hikaricp.connections.max`: maximum connection limit.
- `hikaricp.connections.min`: configured minimum idle/pool size.
- `hikaricp.connections.acquire`: time to acquire a connection.
- `hikaricp.connections.usage`: time a connection is held in use.
- `hikaricp.connections.creation`: time to create a physical connection.

Exact metric names can depend on HikariCP version, Micrometer, and registry configuration. Use Spring Boot Actuator/Micrometer to export pool metrics when appropriate instrumentation is enabled.

An illustrative pool configuration:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
```

These values illustrate syntax only, not a recommended pool size for every system. Choose pool size based on database capacity, number of application instances, concurrency, and connection hold time.

### 5.2. Interpreting Pool Metrics

Some common patterns:

| Observation | Likely area to investigate |
| --- | --- |
| Active always near max, pending rising | Pool may lack capacity or transactions hold connections too long. |
| Low active, slow queries | Bottleneck may be in the database, locks, query plans, or result processing. |
| Rising acquire duration | Requests are waiting for the pool to grant a connection. |
| Rising usage duration | Connections are held too long inside transactions or operations. |
| Physical creation rising continuously | Connections are closing/dropping frequently, pool churn, or unstable database/network. |
| Idle always high, active low | Pool may be oversized for demand, though check peak hours before shrinking. |

Do not increase `maximum-pool-size` merely because pending threads appear. More connections can impose higher concurrency on the database, increase lock contention, and slow queries down further. First identify where connections are being held and whether the database has spare capacity.

### 5.3. Counting Acquisitions Does Not Mean Counting New Connections

If you need to count connection borrows, instrument `DataSource.getConnection()` and logical close/return. If you need to count new physical TCP/JDBC connections, inspect pool metrics such as creation/total or database telemetry.

These two numbers mean different things:

```text
A pool with 10 physical connections
        |
        +-- Request A borrows connection #3
        |       +-- SELECT
        |       +-- UPDATE
        |       +-- INSERT
        |       +-- returns connection #3
        |
        +-- Request B later re-borrows connection #3
                +-- SELECT
                +-- returns connection #3

Physical connections created: possibly just 1
Connection acquisitions: 2
SQL statements: 4
```

This is why you cannot use connection open count to infer statement count or request count.

## 6. Measuring Row Count and Result Size

A SELECT query can take only a few milliseconds on the database yet return a huge volume of data. The application then spends time reading data, materializing objects, holding heap, and serializing the response.

Distinguish three quantities:

1. **Rows returned:** number of ResultSet rows or elements returned by the repository.
2. **Materialized object size:** JVM heap memory occupied by entities/DTOs and collections.
3. **Payload size:** actual response bytes after serialization/compression.

They are not equal. A single row with large VARCHAR columns can be heavier than many rows containing only an ID and status.

### 6.1. Counting Elements at the Application Boundary

For a repository returning a List, you can record size after loading:

```java
List<Customer> result = customers.findByActiveTrue();

registry.counter(
    "app.customer.search.rows",
    "result",
    result.isEmpty() ? "empty" : "non_empty"
).increment(result.size());
```

This metric counts objects returned at the application layer. It does not measure the exact bytes received over the network by the JDBC driver or actual heap usage.

For Page/Slice, you can record `getNumberOfElements()`. If you need the total matching rows, `Page.getTotalElements()` is a separate quantity and may cause the framework to run an additional count query.

### 6.2. Counting Rows in ResultSet

To count rows read by JDBC, you can use a proxy/listener or wrapper around ResultSet to increment a counter whenever `next()` returns true. Note:

- A ResultSet may be read partially.
- Some APIs use streaming/cursors and do not materialize everything at once.
- A ResultSet may be consumed by the framework before the repository returns results.
- Row count does not tell you exact bytes transferred over the network.

If your instrumentation only observes statement execution time without wrapping ResultSet, do not label any number as "rows read" unless the tool genuinely provides row counts.

### 6.3. Estimating Data Size

You can estimate at the application layer using field sizes or serialized bytes:

```java
byte[] payload = objectMapper.writeValueAsBytes(response);

int payloadBytes = payload.length;
```

This is the JSON payload size before the server sends or compresses it, depending on where you measure. It is useful for API response size, though it does not accurately represent ResultSet wire size.

If you need bytes transferred by the database, use appropriate database, driver, or network-layer telemetry/monitoring. If you need heap estimates, use a profiler/JFR or allocation analysis tools; do not use JSON byte length as a proxy for JVM object graphs.

### 6.4. Projections Reduce Data Read

If a screen only needs ID, name, and status, do not load full aggregates along with large collections only to discard most of the data afterward.

Use an appropriate projection/DTO query:

```java
public record CustomerListItem(
    Long id,
    String name,
    boolean active
) {}
```

For complex read queries, custom queries or MyBatis can return only the needed columns. For aggregates whose domain state needs to be modified, continue loading the aggregate root through the repository. Choose projections for read use cases rather than turning DTOs into aggregate write paths.

### 6.5. Pagination and Limiting Results

Avoid returning an entire table when the UI only needs one page:

```java
Page<Customer> findByActiveTrue(Pageable pageable);
```

Example:

```java
Pageable pageRequest = PageRequest.of(
    0,
    50,
    Sort.by("id").ascending()
);

Page<Customer> page =
    customerRepository.findByActiveTrue(pageRequest);
```

Page size should consider both row count and row width. A page of 50 rows can still be large if each row contains long text/JSON columns.

Pagination also has a cost: `Page` typically needs the total row count, which can trigger a count query. If the UI only needs to know whether a next page exists, `Slice` may be more appropriate when supported by the repository method.

## 7. Combining All Four Metric Groups to Find Bottlenecks

Do not read each metric in isolation. Combine them within the same time window or the same request trace.

| SQL count | Connection wait | Query time | Result size | Investigation direction |
| --- | --- | --- | --- | --- |
| High | Low | Each query fast | Small | Likely N+1 or excessive round-trips. |
| Low | Low | High | Small | Query plan, locks, indexes, or database load. |
| Low | High | Normal | Small | Pool saturation or connections held long by other requests. |
| Low | Low | Moderate | Very large | Result transfer, mapping, heap, and serialization. |
| High | High | High | Large | Multiple issues at once; reduce queries/results and review transactions/pool. |
| Low | Low | Low | Small | Unlikely to have a bottleneck on this database path. |

Example:

- Service takes 80 ms.
- 42 SELECTs executed.
- Cumulative statement time is 25 ms.
- Connection acquisition p95 is 2 ms.
- Total result is 400 rows.

A likely suspect is round-trips/repeated queries, because individual query times and pool wait are modest while the statement count is high. Look for a repository call loop or N+1.

Another example:

- Service takes 900 ms.
- 2 SELECTs executed.
- Total statement time is 120 ms.
- ResultSet has 100,000 rows.
- Serialization takes 500 ms.

In this case, reducing SQL count is not the top priority. You need to limit results, use projections, paginate, or switch to appropriate batch/streaming processing.

## 8. Using Micrometer and Actuator

Micrometer provides Counter, Timer, Gauge, and DistributionSummary to record metrics that can be exported to Prometheus, OTLP, or other registries.

An application-level metric set might include:

| Metric | Type | Meaning |
| --- | --- | --- |
| `app.jdbc.statements` | Counter | Statement count by operation. |
| `app.jdbc.statement.duration` | Timer | Statement execution duration. |
| `app.jdbc.connection.acquire` | Timer | Connection acquisition duration. |
| `app.repository.calls` | Counter | Repository call count by use case. |
| `app.repository.duration` | Timer | Repository operation duration. |
| `app.repository.result.rows` | DistributionSummary/Counter | Distribution of rows returned. |
| `app.response.bytes` | DistributionSummary | Response payload size. |

Enable Spring Boot Actuator and the required registry. Common dependencies include Actuator and the Micrometer Prometheus registry; endpoint and export configuration depend on your Spring Boot version.

Metric tags should have low cardinality:

- operation: SELECT/INSERT/UPDATE/DELETE.
- repository: stable repository group or use case name.
- outcome: success/error.
- database: fixed datasource name.

Do not use the following values as tags:

- Full SQL with literals or parameters.
- Customer/order IDs.
- Emails, usernames, or personal data.
- Request URLs with arbitrary query strings.
- Search keyword values.

High-cardinality tags increase memory usage and cost in the metrics backend. Raw SQL and sensitive parameters should be handled in controlled logs/tracing, not placed into metric labels.

## 9. SQL Logging for Investigation

SQL logging is helpful when you need to inspect actual statements, parameter bindings, or query ordering. You can use datasource-proxy, P6Spy, or appropriate logging categories at the JDBC layer.

When enabling logs:

- Only enable verbose logging for the duration needed to investigate.
- Avoid logging passwords, tokens, emails, addresses, or sensitive data.
- Do not enable full parameter logging in production without protective policies.
- Use correlation/trace IDs to link logs to requests.
- Disable or lower log levels once the investigation finishes.

Logs do not replace metrics. Metrics reveal trends over time; logs help inspect a specific statement.

## 10. Testing SQL Counts and Connections in Integration Tests

Service unit tests usually mock repositories and therefore cannot measure actual statements. To verify query counts, run through Spring Data JDBC and an instrumented DataSource.

### 10.1. Testing Bounded Statement Counts

A test can reset counters before an operation and assert that the SELECT count stays within a threshold:

```java
@Test
void loadsCustomerListWithoutUnboundedQueries() {
    sqlMetrics.reset();

    customerService.loadCustomerSummaries();

    assertThat(sqlMetrics.selectCount())
        .isLessThanOrEqualTo(3);
}
```

`sqlMetrics` represents a collector integrated with a datasource proxy in tests. The threshold of 3 is an example; determine it from expected behavior and your project's actual schema.

Avoid asserting an exact query count if that count depends on implementation details that may change across Spring Data versions. An upper bound or dataset-scaling check is usually more resilient.

### 10.2. Testing Trends by Dataset Size

A useful way to detect N+1:

1. Seed 1 customer with orders.
2. Measure statement count when loading the list.
3. Seed 10 customers.
4. Measure the same use case again.
5. Seed 50 customers.
6. Compare statement counts.

If query count grows from 2 to 11 and then 51, there is likely an extra query per customer. If query count stays nearly constant while row count grows, the application is likely using a more effective set-based query.

Tests must reset metrics between runs and exclude SQL seeding/cleanup from the measured region.

### 10.3. Testing Connection Acquisition

To test the connection pool, observe pool metrics before and after an operation or instrument the DataSource to count checkout/return calls.

Do not assert physical connection creation equals 1 in ordinary tests, because the pool may pre-initialize, reuse, or create connections asynchronously. Instead, check:

- No connection acquisition timeouts occur.
- Active connections return to baseline after the operation.
- Pending threads do not grow persistently.
- Acquisition time stays within test environment thresholds.
- Connections are returned even when transactions roll back or throw exceptions.

### 10.4. Testing Large Results

Seed datasets of varying sizes and check:

- Number of items returned.
- Whether page limits are enforced.
- Response payload bytes.
- Materialization/serialization duration.
- Memory allocation if this is a high-volume data path.

For paginated queries, verify that page size is enforced at the database level. Do not merely call `subList` on a List loaded with all rows.

## 11. Using EXPLAIN and Database Metrics Appropriately

Application metrics tell you how much SQL the application issues, how long it takes, and how many results it receives. They do not fully explain which execution plan the database uses.

When a statement is slow, use database tools:

- PostgreSQL: `EXPLAIN` and `EXPLAIN (ANALYZE, BUFFERS)`.
- MySQL: `EXPLAIN` or `EXPLAIN ANALYZE` depending on version.
- SQL Server: actual execution plan and Query Store.
- Oracle: execution plan and appropriate SQL monitoring.

Check:

- Whether expected indexes are used.
- Whether full table scans occur on large tables.
- Whether cardinality estimates are off.
- Whether join order and join methods are reasonable.
- Whether sort/hash operations spill to disk.
- Whether the query reads too many rows before filtering.
- Whether lock waits or I/O dominate elapsed time.

Only run ANALYZE variants that execute the query when you understand their impact; some statements have side effects or heavy load. Use an appropriate staging/test environment and permissions.

## 12. Workflow for Measuring a Spring Data JDBC Use Case

You can follow this workflow when investigating a slow endpoint or service:

1. Select the use case and create a representative dataset.
2. Record total service duration, repository call counts, and outcomes.
3. Instrument DataSource to count statements by type and measure elapsed time.
4. Record connection acquisition/return counts and pool metrics.
5. Count rows at the application boundary; measure payload bytes if the API returns data.
6. Run the same use case across multiple dataset sizes to spot query counts scaling with N.
7. Use traces/logs to pinpoint time-consuming or repeated SQL statements.
8. Use EXPLAIN/database telemetry to understand query plans.
9. Adjust queries, projections, pagination, indexes, or transaction scope based on measured root causes.
10. Re-run the exact same workload and compare before/after on the same database, configuration, and data.
11. Monitor p95/p99, error rate, and pool saturation after deployment.

## 13. Common Mistakes

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Counting repository calls to infer SQL count | One repository operation can emit multiple statements. | Measure at the DataSource/JDBC boundary. |
| Counting batch executions as affected rows | One batch execution carries multiple parameter sets. | Track executions, batch size, and affected rows separately. |
| Treating connection acquisition as new connection | The pool reuses physical connections. | Separate checkout/return from physical creation. |
| Assuming query time equals service time | Mapping, transactions, connection wait, and serialization also take time. | Measure each boundary. |
| Low average yet users still see slow requests | Tail latency is hidden by the average. | Track p95/p99 and error rates. |
| Fast SELECT yet slow endpoint | Large ResultSet, heavy mapping, or heavy serialization. | Measure rows, payload, and allocations. |
| High pool pending leads to immediately raising max pool | The database may already be overloaded or connections held too long. | Find why connections are held and check database capacity first. |
| Production SQL logs expose data | Parameters/literals contain sensitive data. | Redact, limit duration, and restrict log access. |
| Metrics cardinality grows rapidly | Tagging with SQL, IDs, or request parameters. | Use stable, low-cardinality tags. |
| Brittle query count tests | Framework/implementation changes auxiliary statement counts. | Assert upper bounds or scaling trends. |
| H2 does not reflect production | Different dialect, planner, driver, and data types. | Run integration measurements against a production-equivalent database. |

## 14. Metrics Checklist

For a critical use case, a dashboard or test suite should report:

| Group | Minimum metrics |
| --- | --- |
| SQL | Total statements, SELECT/INSERT/UPDATE/DELETE, batch count, error count. |
| Query timing | p50/p95/p99, total elapsed time, slowest queries via traces/logs. |
| Connection | Active, idle, pending, max, acquire time, usage time, timeout count. |
| Result | Rows returned, page size, payload bytes, allocations if needed. |
| Use case | Request count, total duration, success/error, trace IDs in logs. |

Not every metric needs to be exported publicly. Choose observability granularity based on overhead and operational needs; low-cardinality metrics should always be available, while detailed SQL/parameter tracing should only be enabled during controlled investigations.

> **Measuring persistence performance requires separating statement counts, connection acquisitions, per-layer timing, and result sizes.** A single transaction can reuse one connection for many SQL statements; a SELECT with few statements can still return far too much data. Measure at the DataSource, connection pool, and application boundaries, then combine metrics with execution plans to pinpoint the real bottleneck.

### References

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration and metrics provided by Spring Boot.
- [Spring Boot — DataSource Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.supported.jdbc): datasource and connection pool metrics.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): pool metrics, connection acquisition, and usage.
- [datasource-proxy](https://github.com/jdbc-observations/datasource-proxy): DataSource proxy, query execution listeners, and query counting.
- [P6Spy](https://p6spy.readthedocs.io/): observing and logging JDBC activity.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): measuring duration and latency distributions.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): reading execution plans and analyzing query costs.
- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories, aggregate mapping, and persistence behavior of Spring Data JDBC.
