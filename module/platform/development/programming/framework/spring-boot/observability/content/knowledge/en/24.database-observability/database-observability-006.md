# Query latency in database observability

> **Chapter:** Database observability  
> **Lesson:** Query latency  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. Why measure query latency?

An HTTP request may take 1.8 seconds even when the controller only runs a few lines of code. Most of that time might be spent in a database query, waiting for the connection pool, waiting on a lock, or reading more rows than expected. If you only measure total HTTP latency, operations teams know the request is slow, but not which part caused the delay.

**Query latency** is the time a database query operation spends within a defined measurement boundary. That boundary can be JDBC statement execution time, a database client operation's duration, connection acquisition time, or the full lifecycle of a repository call. These numbers are not interchangeable.

Database observability combines:
- Metrics to track query counts, latency distributions, error rates, and connection pools.
- Traces to show where database operations sit in a request and how much time they consume.
- Logs/slow query logs to provide SQL details, plans, or errors within security policies.
- Database-native telemetry to analyze locks, wait events, execution plans, and resource pressure.

~~~mermaid
flowchart TD
  A["HTTP request"] --> B["Controller / service"]
  B --> C["Repository operation"]
  C --> D["Connection pool acquire"]
  D --> E["Database execute / wait"]
  E --> F["Read rows / map result"]
  F --> G["Return to service"]
  B --> H["HTTP response"]
  C --> I["DB metrics + trace span"]
  E --> J["DB slow query / wait telemetry"]
~~~

The goal is not just finding the slowest SQL statement. You need to identify whether latency lives in the pool, network, database execution, lock contention, or application-side result processing.

## 2. Query latency has multiple measurement boundaries

Before comparing latencies, you must know where the timer starts and stops.

| Boundary | Includes | Does not necessarily include |
| --- | --- | --- |
| Pool acquire time | Waiting for a connection | SQL execution |
| Driver execute time | Sending statement and awaiting result per driver API | Full application-level data mapping |
| Result consumption | Reading rows and mapping data | Business steps after the repository |
| Repository call duration | Entire repository method | Work after the method returns |
| Transaction duration | Multiple statements and gaps between them | Only a single query |
| End-to-end request duration | All request activity | Cannot be attributed solely to the database |

A repository method may run three SQL statements, so repository latency is not single-statement query latency. A transaction may hold a connection while executing business logic; a long transaction duration does not mean every SQL statement is slow.

When building dashboards or SLOs, name metrics and spans after their actual boundaries. Avoid comparing driver-measured query duration against a repository timer that includes mapping and application code.

## 3. Distinguishing database latency from pool, network, and application time

A database call typically passes through several stages:

1. Acquire a connection from the pool.
2. Driver prepares the statement and sends it over the network.
3. Database parses/plans or uses a cached plan.
4. Database waits on locks, I/O, or CPU.
5. Database returns rows.
6. Driver reads data and application maps results.
7. Application closes the statement/connection or returns the connection to the pool.

Diagnostic table:

| Symptom | Suspect area | Evidence to inspect |
| --- | --- | --- |
| Pool acquire rises, SQL execute steady | Pool saturation/leak | Active/idle/pending connections |
| DB execution time increases | Query plan, indexes, locks, DB load | Slow queries, EXPLAIN, wait events |
| Low DB time but slow repository | Mapping, serialization, application processing | CPU profile, row count, code path |
| Latency rises with network RTT | Network/proxy/database endpoint | Network telemetry, driver timing |
| Only one tenant/parameter is slow | Data skew or plan sensitivity | Parameter distribution, plans |
| Many tiny queries per request | N+1 or chatty access | Trace waterfall, query count |

Do not conclude "the database is slow" from a single long HTTP span. Compare each DB operation's duration with pool metrics, downstream spans, and database-native telemetry.

## 4. JDBC query instrumentation in Spring Boot

Spring Boot Actuator and Micrometer provide integrations to observe certain database/client operations. For JDBC, DataSource instrumentation can produce observations/spans and metrics depending on dependencies, configuration, and versions.

Common options include:
- Micrometer Observation/Tracing integrated with Spring Boot.
- Appropriate DataSource or JDBC instrumentation.
- OpenTelemetry Java Agent auto-instrumentation for supported JDBC drivers.
- Database-specific metrics/slow query logs from the database itself.

Do not assume simply adding Actuator automatically turns every SQL statement into a detailed span. Verify the actual instrumentation, dependencies, and backend.

~~~java
@Repository
public class ProductRepository {
    private final JdbcTemplate jdbcTemplate;

    public ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Product findById(long id) {
        return jdbcTemplate.queryForObject(
                "select id, name from products where id = ?",
                (rs, rowNum) -> new Product(
                        rs.getLong("id"),
                        rs.getString("name")),
                id);
    }
}
~~~

When JDBC instrumentation is active, the query can appear in traces as a client/database span or corresponding operation. Exact attributes depend on the instrumentation and semantic convention version.

## 5. R2DBC and reactive database operations

R2DBC provides a reactive API for relational databases. Do not apply lifecycle assumptions from blocking JDBC calls to R2DBC publishers.

~~~java
public Mono<Product> findById(Long id) {
    return databaseClient.sql(
            "select id, name from products where id = :id")
        .bind("id", id)
        .map((row, metadata) -> new Product(
                row.get("id", Long.class),
                row.get("name", String.class)))
        .one();
}
~~~

In a reactive stack, queries execute when the publisher is subscribed to. Timing `Mono` construction is not equivalent to query duration. Instrumentation must cover subscription through completion/error signals.

Points to check:
- Context propagation across Reactor operators.
- Connection pool acquisition and release.
- Cancellation when a subscriber cancels.
- When results are consumed.
- Query errors and decode/mapping errors.
- Driver instrumentation support for your version.

Do not call `block()` just to measure latency; doing so alters the execution model and can cause thread starvation.

## 6. Database spans in distributed traces

When database instrumentation is active, DB operations can appear as child spans beneath server/business spans.

~~~text
order-service: POST /orders                 [SERVER]
  order-service: orders.create               [INTERNAL]
    order-service: SELECT products           [CLIENT / DATABASE]
    order-service: INSERT orders             [CLIENT / DATABASE]
    order-service: UPDATE inventory          [CLIENT / DATABASE]
~~~

Traces help answer:
- Which query consumes most of the request time?
- Does a single request issue too many database calls?
- In which service do slow queries occur?
- Did the DB span fail, or was it simply slow?
- Are multiple services waiting on the same database dependency?

Traces do not replace execution plans. An 800 ms span only states that the operation took 800 ms within the instrumentation boundary; it does not tell you whether the database performed a sequential scan, waited on a lock, or waited on storage. Combine with DB-native telemetry.

Do not record raw SQL with literals or sensitive parameters in span attributes. Prefer normalized operation names/statement summaries and allowlisted metadata.

## 7. Metrics for query latency

An appropriate `Timer`/histogram can track database operation durations. Depending on instrumentation, metric names differ; do not assume identical meter names across JDBC, R2DBC, and all exporters.

Illustrative custom metric:

~~~java
Timer queryTimer = Timer.builder("app.database.query")
        .tag("db.system", "postgresql")
        .tag("operation", "select")
        .tag("repository", "product")
        .register(meterRegistry);

queryTimer.record(() -> productRepository.findById(id));
~~~

This example illustrates a repository call boundary. It does not necessarily measure statement execution time alone. If JDBC instrumentation already measures statements, avoid creating another `Timer` with the same name/semantics and summing them together.

Metric dimensions should remain bounded:
- `db.system`: postgresql, mysql, oracle.
- `operation`: select, insert, update, delete.
- `repository`/query group: `product.find-by-id`, `order.create`.
- `outcome`: success, error, timeout.
- normalized datasource/pool name.

Do not use SQL text, parameter values, customer IDs, order IDs, or dynamic raw table names as metric tags.

## 8. Percentiles, histograms, and tail latency

Average latency can hide a subset of very slow requests. Suppose 990 queries take 10 ms and 10 queries take 2 seconds. The average may look low while users are visibly impacted.

Common metrics:
- p50: median; half of observations are faster than or equal to this value.
- p90/p95: tail latency for most requests.
- p99: the slowest slice, useful when traffic volume is large enough.
- max: maximum observation, sensitive to outliers.
- count/rate: number of operations in a window.

Histogram buckets let the backend compute quantiles and analyze distributions. Client-side percentiles cannot be accurately aggregated across multiple instances; choose histograms/aggregations supported by your backend.

Conceptual PromQL example if histograms are exported:

~~~text
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(app_database_query_seconds_bucket[5m])
  )
)
~~~

Metric names and bucket configurations must match actual data. A p99 computed from a window with few samples is unstable; always check sample counts and traffic volume.

## 9. Slow query logs and query fingerprints

Database slow query logs record statements exceeding a duration threshold. They are a valuable source for finding slow queries even when application traces are dropped by sampling.

A query fingerprint normalizes statement structure by removing or masking literal values to group similar executions.

Example:

~~~sql
select id, total
from orders
where customer_id = ?
  and status = ?
~~~

Fingerprints group by query shape instead of creating a separate bucket per parameter. Check whether your database exposes normalized query digests or query IDs; behavior depends on the engine.

Do not enable full SQL logging with bind parameters in production without evaluating sensitive data, storage volume, and access controls. Queries can contain emails, tokens, addresses, or transaction details.

## 10. N+1 queries and query count

An endpoint can be slow because it runs too many small queries rather than one large query. This is the classic N+1 problem with ORMs/lazy loading.

Example: fetching a list of 100 orders, then lazy-loading the customer for each order:

~~~text
1 query: select orders ...
100 queries: select customer where id = ?
Total: 101 database calls
~~~

Each query might only take 4 ms, but cumulative round trips, pool contention, and scheduling introduce substantial latency.

Symptoms:
- Traces show many repeated DB spans with the same name.
- Query count scales linearly with returned row count.
- Latency rises as page size increases.
- DB CPU is not overly high, yet network/round-trip overhead is large.

Remediation:
- Appropriate fetch joins/entity graphs.
- Batch fetching.
- Projections selecting only needed fields.
- Bulk queries or bounded `IN` clauses.
- Review pagination and query plans.

Do not replace an N+1 issue with a giant unindexed query or one returning excessive data. Measure query count, row count, latency, and memory after changes.

## 11. Connection pool acquire latency

The connection pool is a major contributor to database latency. When all connections are busy, new requests wait for a free connection or time out.

Metrics to monitor if supported by the pool:
- active connections.
- idle connections.
- maximum pool size.
- pending/waiting threads.
- acquisition time.
- usage/lease duration.
- timeout count.

If pool acquire takes 700 ms while DB execution takes 20 ms, optimizing SQL will not fix the root cause. Check for connection leaks, transactions holding connections too long, pool sizing, and concurrency.

Do not blindly raise pool size. Databases have connection limits, and larger pools can overload the DB. Balance replica count, per-replica pool size, and the system-wide connection budget.

## 12. Lock contention and transaction duration

A query can be slow because it is waiting on a lock even with a good execution plan. Long transactions or strict transaction isolation can increase wait times.

Symptoms:
- Sudden latency spikes at specific times.
- Multiple queries waiting on the same table/row.
- Database wait events showing lock waits.
- High query duration with low query CPU.
- Transactions open or connections held for long durations.

Combine:
- Database lock/wait telemetry.
- Transaction duration metrics.
- Trace spans per repository/transaction.
- Database activity/session views.
- Query plans and indexes.

Do not put sensitive data into spans just to identify locked rows. Use query fingerprints, operation groups, and controlled database diagnostics.

## 13. Query latency and cardinality

Metric tags should describe stable query groups. Example:

~~~text
db.system = postgresql
db.operation.name = SELECT
repository = product
outcome = success
~~~

Avoid tags such as:
- `sql` = full SQL text.
- `parameter` = bind values.
- `customer.id`.
- `order.id`.
- raw table or schema controlled by user input.
- `exception.message`.

If every query parameter spawns a new time series, cardinality explodes with traffic. Parameter details should be investigated in controlled environments via DB query digests or redacted traces/logs, never turned into metric dimensions.

Database attribute names in OpenTelemetry semantic conventions have evolved across versions. Check your instrumentation and backend convention versions before building dashboards on legacy keys.

## 14. Logging and trace correlation for slow queries

When slow queries are detected, logs can record the operation group, duration, DataSource, and trace context. Avoid logging raw parameter values.

~~~java
long started = System.nanoTime();
try {
    return repository.loadSummary(accountRef);
} finally {
    long elapsedMs =
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

    if (elapsedMs > 500) {
        log.warn(
                "Slow repository operation repository={} durationMs={}",
                "account-summary",
                elapsedMs);
    }
}
~~~

This example measures a repository method manually. In production, prefer standard instrumentation when available; if using custom timing, avoid duplicate measurement and choose sensible metrics/thresholds. The code above illustrates a log threshold and does not attach trace IDs itself; use logging correlation integration to pull `traceId`/`spanId` from the current context.

Useful logs can contain:
- `service.name`/version.
- repository/query group.
- duration.
- outcome/error category.
- `traceId`/`spanId` if present.
- normalized instance/DataSource metadata.

Never log passwords, tokens, raw SQL parameters, PII, or full entities.

## 15. Inspecting query latency in Spring Boot

A practical workflow:

### Step 1 — verify instrumentation

Check Actuator, Micrometer registry, tracing bridge, or OTel agent/SDK. Identify whether the database technology is JDBC or R2DBC and verify its corresponding instrumentation.

### Step 2 — inspect metrics

Check request/DB operation counts, latency distributions, pool active/idle/pending, and error rates. Match against actual metric names/tags instead of guessing.

### Step 3 — open sample traces

Find a sampled slow request. Identify which DB span consumes the most time, the number of queries, and the parent operation.

### Step 4 — check database-native diagnostics

Use slow query logs, query digests, `EXPLAIN`/`EXPLAIN ANALYZE` in an appropriate environment, lock/wait events, and DB load. `EXPLAIN ANALYZE` can actually execute the query; exercise caution with data-modifying statements or heavy queries.

### Step 5 — separate pool and execution

Compare connection acquire time, statement execution, result consumption, and repository duration. Confirm which boundary your current instrumentation measures.

### Step 6 — verify after changes

After adding indexes, fixing N+1 queries, adjusting pool config, or changing query shapes, compare p50/p95/p99, counts, error rates, DB CPU, lock waits, and pool pending. Use the same traffic pattern and measurement window.

## 16. Troubleshooting query latency patterns

| Symptom | Possible cause | Evidence / action |
| --- | --- | --- |
| DB span p95 rises while pool acquire is stable | Query plan, DB load, or locks | Slow query digest, EXPLAIN, wait events |
| Slow repository but short DB spans | Mapping, business logic, result processing | CPU profile, row count, code path |
| Pool pending rises | Pool saturation or connection leak | Active/idle/pending, transaction duration |
| Query count grows with page size | N+1/lazy loading | Trace waterfall, query count |
| Only one parameter is slow | Data skew or plan sensitivity | Query digest, parameter distribution |
| High p99 with stable p50 | Tail outliers, locks, cold cache | Analyze outlier traces and DB waits |
| Latency spikes after deploy | Query shape/index/config regression | Compare versions and plans |
| Duplicate DB spans | Duplicate instrumentation | Check agent, DataSource proxy, and custom timers |
| Missing DB spans | Missing instrumentation or sampling | Check agent/bridge/SDK and trace sampler |
| Metrics missing query dimensions | Conventions or custom tags not configured | Inspect actual meter tags |
| High slow query logs but low app timer | Different measurement boundary or async/background query | Compare clocks, operations, and database digests |
| Error rate rises without latency rise | Constraints, permissions, connection failures | Exception type, SQLState, pool metrics |

### Quick investigation workflow

1. Select the service, DataSource, and time window.
2. Compare query count, p95/p99, and pool acquire.
3. Open traces to locate the dominant query group.
4. Retrieve the fingerprint/query ID from database telemetry.
5. Inspect plans, indexes, lock waits, and row counts.
6. Determine whether latency lies in the pool, network, execution, or result mapping.
7. Change one factor and re-benchmark.
8. Monitor both DB health and application latency after deployment.

## 17. Real-world scenario: order-service endpoint p95 spike

**Scenario:** `POST /orders` p95 jumps from 120 ms to 900 ms. HTTP server metrics show slow requests without a spike in 5xx errors.

### Step 1 — trace pinpoints database operation

Traces show `orders.create` has three DB spans. One SELECT on `order_items` takes 720 ms; the others take under 20 ms.

### Step 2 — check the pool

Pool acquire time is low and pending connections are near 0. This reduces the likelihood that pool saturation is the primary cause.

### Step 3 — inspect query digest and plan

Database slow query telemetry reveals the query scans many rows. `EXPLAIN` shows the filter/join is not using an appropriate index. The team verifies with representative data and a test workload.

### Step 4 — optimize the query

Add an appropriate index or adjust the query shape after checking write overhead and plans. If traces show many repeated SELECTs per item, also evaluate N+1 patterns and batch loading.

### Step 5 — verify

After deployment, compare:
- p50/p95/p99 of the DB operation.
- HTTP server latency.
- Query count per order.
- DB CPU/IO and lock waits.
- Pool acquire and pending.
- Error rate and result correctness.

**Expected outcome:** confirm latency truly resides in database execution, make evidence-based query/index changes, and verify the end-to-end impact on the request.

## 18. Hands-on exercises and self-check questions

### Exercise A — distinguish latency boundaries

Create a repository call and measure pool acquire, statement execute (if supported by driver), result consumption, and repository duration separately. Explain why the numbers differ.

### Exercise B — trace database calls

Enable appropriate JDBC or R2DBC instrumentation. Trigger an HTTP request with two queries. Verify DB spans are children of the request trace and measure each operation's duration.

### Exercise C — simulate N+1

Create an endpoint loading 50 records with a lazy relationship. Observe query count and trace waterfall. Switch to an appropriate fetch/batch/projection, then compare query count, latency, and memory.

### Exercise D — pool saturation

Constrain the connection pool to a small size and run a concurrency test. Observe active, idle, pending, acquire latency, and timeouts. Adjust pool size deliberately without exceeding the database connection budget.

### Exercise E — slow query and plan

Create a query filtering on an unindexed column over a test dataset. Collect the query digest/slow log and `EXPLAIN`. Add an index or rewrite the query, then re-measure p95/p99 and write overhead.

### Exercise F — cardinality review

Audit metric tags and tracing attributes. Strip SQL literals, parameter values, and customer/order IDs from metric labels. Use stable query groups/fingerprints and check time series counts.

### Self-check questions

1. How does query latency differ from repository duration and transaction duration?
2. What does rising pool acquire time indicate?
3. Why is a slow HTTP request insufficient to conclude the database is slow?
4. How do JDBC and R2DBC differ in execution lifecycle?
5. What does a database span reveal, and what does it not reveal?
6. When are p95/p99 more informative than averages?
7. How do N+1 queries increase latency even when each individual query is fast?
8. How do you distinguish lock waits from a slow query plan?
9. Why should SQL text/parameters not be placed in metric tags?
10. How do slow query logs and trace sampling complement each other?
11. Does a larger connection pool always improve latency?
12. How do you determine whether a timer metric measures a statement or a repository call?
13. What risks does `EXPLAIN ANALYZE` carry for write queries?
14. How can you correlate slow query logs with traces without leaking PII?
15. Which metrics should be monitored after optimization to prevent regressions?

**Completion criteria:** explain query latency boundaries; distinguish pool/network/database/application time; instrument JDBC/R2DBC; interpret DB spans and histograms; identify N+1 queries, locks, and pool saturation; use slow queries/plans; control cardinality and security; verify improvements with metrics and traces.

## 19. Key takeaways

- Query latency must be tied to a clear measurement boundary: pool acquire, statement execution, result consumption, repository, or transaction.
- HTTP request latency does not equal database execution time.
- JDBC and R2DBC have different lifecycles; reactive queries execute upon subscription.
- DB spans place queries within a request trace, but do not replace execution plans, lock/wait telemetry, or slow query digests.
- Monitor p50/p95/p99 alongside counts; percentiles require sufficient samples and appropriate histograms.
- N+1 queries, pool saturation, lock contention, data skew, and result mapping can all slow down the database path.
- Separate pool acquire from execution time to avoid tuning SQL when the root cause is the connection pool.
- Use query fingerprints/operation groups instead of raw SQL and parameters in metrics.
- Combine metrics, traces, logs, and database-native diagnostics to find root causes.
- After optimizing, verify latency, query count, pool health, DB load, lock waits, and correctness under representative load.

## References

- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/database/)
- [OpenTelemetry Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [PostgreSQL Documentation — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
