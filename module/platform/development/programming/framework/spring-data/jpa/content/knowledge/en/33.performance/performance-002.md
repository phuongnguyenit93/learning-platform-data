# Observing Query Count, SQL Execution Time, and Returned Row Count in Spring Data JPA

## 1. Why Observe Queries?

A Spring Data JPA feature can be functionally correct yet slow as data grows. The cause often lies not in a single line of Java code, but in how many times the application hits the database, how long each SQL statement takes, and how much data must be read, transferred over JDBC, and mapped into objects.

Three signals to track:

- **Query count:** how many SQL queries are actually executed in a use case or request.
- **SQL execution time:** how long queries take, which query is slowest, and how duration changes under load.
- **Returned row count:** how many rows the database/JDBC returns, how many entities/DTOs the application retains, and how many duplicate rows are produced by JOINs.

These signals help detect N+1 queries, over-fetching data, missing indexes, inefficient pagination, and misconfigured caches.

Do not look solely at single-request duration. Combine query count, average and p95/p99 percentiles, row count, cache hits/misses, payload size, and connection pool state to pinpoint the root cause.

## 2. Distinguishing Observation Layers

A query passes through multiple layers:

1. **Spring Data repository:** a method such as findAll, a derived query, or @Query is invoked.
2. **Hibernate ORM:** parses JPQL/HQL, generates SQL, manages the persistence context, and maps results.
3. **JDBC:** sends statements, binds parameters, executes, and reads the ResultSet.
4. **Database:** plans execution, reads indexes/tables, joins, sorts, locks, and returns data.
5. **Application:** materializes entities/DTOs, processes associations, maps, and serializes the response.

Each tool observes a different part:

| Tool | What it measures well | Limitations to keep in mind |
|---|---|---|
| Hibernate SQL log | Generated SQL and execution order | Does not provide dashboards or latency percentiles |
| Hibernate Statistics | Query counts, aggregated timings, cache, and entity/collection counters | Mostly SessionFactory-wide metrics |
| Hibernate QueryStatistics | Execution count, timings, and ResultSet rows of a query string | Does not automatically correlate metrics to individual HTTP requests |
| JDBC/DataSource instrumentation | Execution time, ResultSet fetch time, row count, and affected rows | Requires proxy/observation setup and a metrics/tracing backend |
| Database monitoring | Execution plans, buffers/cache, locks, I/O, and server-side timings | Needs correlation with application SQL and requests |

Choose the tool based on the question you need to answer. When debugging a single query, SQL logging is often enough to start. When comparing system-wide behavior, use statistics and metrics. When identifying which request generates excessive SQL, use tracing or JDBC instrumentation correlated with requests.

## 3. Enabling SQL Logging in Hibernate

In Spring Boot, logging can be configured in application.properties:

~~~properties
# Show SQL statements Hibernate sends via JDBC
logging.level.org.hibernate.SQL=DEBUG

# Parameter values bound to PreparedStatement (Hibernate 6)
logging.level.org.hibernate.orm.jdbc.bind=TRACE

# Values extracted from JDBC ResultSet (Hibernate 6)
logging.level.org.hibernate.orm.jdbc.extract=TRACE

# Format SQL for readability
spring.jpa.properties.hibernate.format_sql=true
~~~

Some Hibernate versions also support hibernate.show_sql=true to print SQL directly to the console. In a Spring Boot application, it is generally better to use the org.hibernate.SQL logger so output flows through the logging framework, where it can be filtered by level, appender, and environment.

For example, SQL logging may show:

~~~sql
select
    o1_0.id,
    o1_0.customer_id,
    o1_0.created_at,
    o1_0.status
from purchase_order o1_0
where o1_0.customer_id=?
~~~

The bind parameter line shows the actual value bound to `?`. When investigating a query that does not return expected data, cross-check the SQL, data types, and bound parameters.

### Only Enable Detailed Logging When Needed

Bind parameter and ResultSet extraction logs can be very verbose. Bound values may contain emails, phone numbers, tokens, payment details, or personal data. Do not enable TRACE broadly in production without log protection policies, masking, access controls, and proper retention limits.

SQL logs also do not reveal the total rows consumed by the application if a query uses streaming or reads the ResultSet incrementally. Use JDBC instrumentation or query statistics when you need that count.

## 4. Adding Comments to Trace JPQL Sources

When multiple repository methods produce similar SQL, it is hard to tell where a SQL statement originated. Hibernate supports hibernate.use_sql_comments to add HQL/JPQL comments to generated SQL.

~~~properties
spring.jpa.properties.hibernate.use_sql_comments=true
~~~

Comments help link SQL back to queries at the application layer. With the Hibernate Query API, you can set a comment on a query using setComment(...) or the corresponding query hint.

Do not include sensitive data, user IDs, or request payloads in comments. Use stable use-case names, such as OrderRepository.findRecentByCustomer.

## 5. Tracking Slow Queries with Hibernate

Hibernate supports hibernate.log_slow_query: setting a minimum duration threshold, in milliseconds, to log SQL statements exceeding that threshold.

~~~properties
# Example: log queries taking longer than 250 ms
spring.jpa.properties.hibernate.log_slow_query=250
~~~

This is an illustrative threshold. Set the threshold based on your application's latency targets and database characteristics. A 150 ms query may be too slow for an endpoint requiring a 50 ms response, yet acceptable for a background report.

You can also enable:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

When enabled, Hibernate collects statistics readable via Statistics. Hibernate can also record slow queries in the statistics map when slow-query logging is enabled and supported by the version.

Slow-query logging helps find statements exceeding a threshold. It does not replace histograms or percentiles: a query averaging 30 ms with a 2-second p99 can still cause a poor user experience.

## 6. Reading Hibernate Statistics

Hibernate provides Statistics attached to SessionFactory. With Spring Boot and Hibernate, you can unwrap it from EntityManagerFactory:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateStatisticsReader {

    private final Statistics statistics;

    public HibernateStatisticsReader(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public void printSummary() {
        if (!statistics.isStatisticsEnabled()) {
            return;
        }

        System.out.println(
            "queryCount=" + statistics.getQueryExecutionCount()
        );
        System.out.println(
            "slowestQueryMs=" + statistics.getQueryExecutionMaxTime()
        );
        System.out.println(
            "slowestQuery=" + statistics.getQueryExecutionMaxTimeQueryString()
        );
        System.out.println(
            "entityFetchCount=" + statistics.getEntityFetchCount()
        );
        System.out.println(
            "collectionFetchCount=" + statistics.getCollectionFetchCount()
        );
        System.out.println(
            "secondLevelCacheHits=" + statistics.getSecondLevelCacheHitCount()
        );
        System.out.println(
            "secondLevelCacheMisses=" + statistics.getSecondLevelCacheMissCount()
        );
        System.out.println(
            "queryCacheHits=" + statistics.getQueryCacheHitCount()
        );
        System.out.println(
            "queryCacheMisses=" + statistics.getQueryCacheMissCount()
        );
    }
}
~~~

This is a component for reading Hibernate metrics. The numbers are cumulative counters for the SessionFactory, not isolated metrics for a single running request.

Some useful methods:

| Method | Meaning |
|---|---|
| getQueryExecutionCount() | Total number of executed queries |
| getQueryExecutionMaxTime() | Maximum query execution time |
| getQueryExecutionMaxTimeQueryString() | Query string corresponding to the maximum time |
| getEntityLoadCount() | Number of entities loaded |
| getEntityFetchCount() | Number of entities fetched |
| getCollectionLoadCount() | Number of collections loaded |
| getCollectionFetchCount() | Number of collections fetched |
| getPrepareStatementCount() | Number of PreparedStatements acquired |
| getSecondLevelCacheHitCount() | Second-level cache hit count |
| getSecondLevelCacheMissCount() | Second-level cache miss count |
| getQueryCacheHitCount() | Query cache hit count |
| getQueryCacheMissCount() | Query cache miss count |

Entity and collection counters help identify data loading behavior. For instance, an endpoint returning 20 orders that triggers many collection fetches may be loading each collection individually.

### Statistics Are SessionFactory-Wide Metrics

Statistics aggregates activity across all Sessions belonging to a SessionFactory. If multiple requests run concurrently, counters increment from all of those requests. Therefore:

- Do not treat getQueryExecutionCount() as the query count of a specific request.
- Do not call statistics.clear() per request to compute deltas; doing so resets shared counters and corrupts measurements for other requests.
- You may use snapshots/deltas in single-threaded integration tests or isolated test environments.
- In production, use tracing or JDBC-layer instrumentation to tie queries to specific requests/traces.

## 7. Measuring Execution Count and Timing of a Specific Query

Statistics.getQueryStatistics(queryString) returns statistics for an HQL or SQL query string. The QueryStatistics object provides execution count, average, maximum, minimum, and total duration, as well as the number of ResultSet rows processed.

Example:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.QueryStatistics;
import org.hibernate.stat.Statistics;

String hql =
    "select o from PurchaseOrder o where o.status = :status";

Statistics statistics = sessionFactory.getStatistics();

if (statistics.isStatisticsEnabled()) {
    QueryStatistics queryStats =
        statistics.getQueryStatistics(hql);

    long executions = queryStats.getExecutionCount();
    long averageMs = queryStats.getExecutionAvgTime();
    long maximumMs = queryStats.getExecutionMaxTime();
    long totalMs = queryStats.getExecutionTotalTime();
    long resultSetRows = queryStats.getExecutionRowCount();
}
~~~

The query string used for lookup must match the string Hibernate tracks. Different bind parameter values generally fall under the same query string.

getExecutionRowCount() is the cumulative number of ResultSet rows processed for that query. For queries using stream() or scroll(), Hibernate does not necessarily know the total row count at execution time, so this statistic may not be completely updated. If you need to measure the exact rows fetched over JDBC, instrument the ResultSet.

Metrics in QueryStatistics also accumulate over the SessionFactory lifecycle. They are useful for ranking frequently run queries, slow queries, or queries reading many rows; they are not per-endpoint p95/p99 latencies.

## 8. Distinguishing Query Count from Statement Count

A single repository method does not necessarily correspond to a single SQL statement.

For example, a findAll(pageable) method may execute:

1. A query to fetch the page content.
2. A count query to calculate the total number of elements.

Loading an entity with LAZY associations and accessing each association can generate multiple additional SELECTs. A query might be served from the query cache or entity cache and not produce the same number of SQL statements as a cache miss.

Also distinguish between:

- **Repository method count:** number of repository method calls.
- **Hibernate query execution count:** number of queries Hibernate records as executed.
- **JDBC statement/query count:** number of SQL operations actually passing through the DataSource.
- **Database query count:** number of statements the database records within the observation window.

These numbers can differ due to caching, lazy loading, flushing, batching, native JDBC, and internal queries. When diagnosing the number of round-trips to the database, JDBC instrumentation is a more direct measurement point than ORM-level query counters.

## 9. Measuring SQL Execution Time and Fetch Time Separately

User-perceived latency is not solely the time the database spends executing a statement. Total latency can include:

- Waiting to acquire a connection from the pool.
- Sending SQL and binding parameters.
- Database parsing/planning/executing.
- Network data transfer.
- JDBC fetching the ResultSet in batches.
- Hibernate converting SQL rows into entities/DTOs.
- Processing associations, mapping, and serializing the response.

A query with short execution time can still be slow if it returns hundreds of thousands of rows and spends significant time fetching/materializing them.

Datasource Micrometer separates JDBC observations such as CONNECTION, QUERY, FETCH, and KEYS. Thus, you can see query execution time and ResultSet reading time separately. When QUERY is fast but FETCH is long, check row count, column sizes, fetch size, network, and entity mapping.

## 10. Measuring ResultSet Row Count with JDBC Instrumentation

Hibernate Statistics is well suited for ORM observation. If you need the actual number of rows read via JDBC correlated with requests/traces, you can use Datasource Micrometer.

The project provides modules:

- datasource-micrometer: core JDBC instrumentation.
- datasource-micrometer-spring-boot: auto-configuration for Spring Boot.
- datasource-micrometer-opentelemetry: maps observations to OpenTelemetry conventions.

Example Maven dependency for Spring Boot per current documentation:

~~~xml
<dependency>
    <groupId>net.ttddyy.observation</groupId>
    <artifactId>datasource-micrometer-spring-boot</artifactId>
    <version>2.3.0</version>
</dependency>
~~~

Check the compatibility matrix with your project's Spring Boot, Micrometer, and Java versions; use the library's BOM if managing multiple modules at the same version.

The Spring Boot module automatically instruments the DataSource and registers observations into Micrometer infrastructure. When an appropriate registry/exporter is added, observations can flow to a metrics backend or tracing backend.

Datasource Micrometer distinguishes:

| Observation | Meaning |
|---|---|
| CONNECTION | Acquiring and closing a JDBC connection |
| QUERY | Executing a statement |
| FETCH | Reading data from a ResultSet |
| KEYS | Reading generated keys |

ResultSet observations can provide the number of rows read. In OpenTelemetry mapping, jdbc.row-count is the number of SQL rows of a ResultSet span; jdbc.row-affected is the number of rows affected by executeUpdate, executeLargeUpdate, or batch DML.

If building a proxy manually with datasource-proxy, you must enable ResultSet proxying to instrument row-by-row reads. With the Spring Boot module, check the jdbc.includes configuration to select which observation types to collect; current documentation defaults include CONNECTION, QUERY, KEYS, and FETCH.

## 11. Distinguishing SQL Rows, Entity Count, and Page Metadata

The following three values are not synonymous:

1. **SQL rows:** the number of rows returned by the database/JDBC.
2. **Java result size:** the number of objects in the List, Set, or projection returned by Hibernate.
3. **Page totalElements:** total elements matching the filter criteria, which may be calculated by a count query.

Example JOIN FETCH:

~~~sql
select
    o.id,
    i.id,
    i.product_name
from purchase_order o
left join order_item i on i.order_id = o.id
where o.id in (10, 11)
~~~

Suppose two orders have a total of five order lines. The database may return five SQL rows, while Hibernate maps them into two root PurchaseOrder entities with their respective items collections.

Therefore, an SQL row count greater than the root entity count is not necessarily an error. However, joining multiple collections can multiply row counts by the product of collection sizes, causing duplicate data and higher transfer costs.

For Page, getNumberOfElements() is the number of elements in the current page; getTotalElements() is the total number of matching elements. Do not treat totalElements as the SQL row count of the content query because Spring Data may run a separate count query.

## 12. Detecting N+1 Using Query Count

N+1 occurs when the application loads a list of entities with one query, then accesses a LAZY relationship and triggers an extra query for each entity.

Example:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getItems().size());
}
~~~

If there are 40 orders, you might observe:

- 1 SELECT fetching the list of orders.
- 40 SELECTs fetching the items collection for each order.

Roughly 41 queries in total, depending on mapping and caching.

Warning signs:

- Query count grows roughly linearly with the number of entities in the list.
- The same SQL executes repeatedly with different parameters.
- collectionFetchCount or entityFetchCount rises rapidly.
- The endpoint is fast with a few records but slow with a large list.

Remedies can include:

- Using JOIN FETCH for associations needed immediately.
- Using @EntityGraph to declare a fetch plan per use case.
- Using batch fetching to combine multiple lazy loads into fewer queries.
- Using DTO projections when only a subset of fields is needed.
- Avoiding accessing LAZY relationships outside transactions or inside loops without a fetch plan.

Do not turn EAGER on for every relationship to cure N+1. EAGER can cause other queries to load too much data and trigger N+1 along another access path.

## 13. Observing Caching Alongside Query Count

Spring Data JPA typically runs on Hibernate, which has multiple cache layers:

- **First-level cache:** the persistence context of one EntityManager/Session. Managed entities can be reused within the same persistence context.
- **Second-level cache:** a cache shared across Sessions, if configured and entities/collections are cache-enabled.
- **Query cache:** caches the results of cache-enabled queries; usually needs to work together with the second-level cache to reuse entity state.

Hibernate Statistics provides hit, miss, and put counters for the query cache, second-level cache, and cache regions. Use them to verify whether caching actually reduces database load.

Some principles:

- A query cache hit does not mean all entity state is served from the query cache.
- An entity second-level cache hit can reduce SELECTs fetching entity state.
- The first-level cache only lives within the current persistence context; do not treat it as a shared cache across requests.
- Cache misses can be normal behavior when data is new or the cache was recently invalidated.
- A high hit rate does not automatically prove an endpoint is fast; query plans, row counts, and fetch times still need observation.

When changing a caching strategy, compare the same workload before and after the change: query count, query time, cache hits/misses, rows read, and data reuse rate.

## 14. Finding the Cause of Slow Queries via Execution Plans

Once you find slow SQL, grab the actual SQL and sample parameters from logs/traces. Then use database tools to inspect the execution plan.

Depending on the database engine, you can use:

- PostgreSQL: EXPLAIN or EXPLAIN (ANALYZE, BUFFERS).
- MySQL: EXPLAIN or EXPLAIN ANALYZE.
- SQL Server: Actual Execution Plan and Query Store.
- Oracle: EXPLAIN PLAN and SQL Monitor.

EXPLAIN ANALYZE usually executes the real query on the database. Consider the impact when running on write queries, resource-intensive queries, or production data. Prefer an appropriate staging/replica environment or a DBA-approved plan.

Look for:

- Sequential/table scans on large tables.
- Index scans with poor selectivity.
- JOINs producing large intermediate row sets.
- Sort or hash operations consuming excessive memory/temp space.
- Estimated row counts far off from actual row counts.
- Lock waits or high I/O.
- Indexes not matching filter/sort conditions.

Do not add an index solely because a column appears in a WHERE clause. Check the execution plan, cardinality, query frequency, and write overhead introduced by the new index.

## 15. Creating Production-Ready Metrics and Traces

When exporting metrics to Micrometer/Prometheus or a tracing backend:

- Use stable query names or normalized SQL forms to group metrics.
- Keep tags low-cardinality, such as datasource, operation, query name, or repository method.
- Do not use raw SQL with literals, bound parameters, emails, user IDs, or order IDs as metric labels.
- If parameters are needed for debugging, store them in masked traces/logs with restricted access.
- Collect histograms to compute p50/p95/p99 instead of tracking averages only.
- Monitor error count, timeouts, connection acquisition, and query/fetch latency together.
- Configure trace sampling and log retention appropriate for your load.

Metrics should help compare trends without creating millions of time series. Per-request details belong in traces/spans; metrics should use low-cardinality dimensions.

## 16. A Practical Investigation Workflow

When an order search endpoint is slow:

1. Record the request, total duration, and trace ID.
2. Count JDBC QUERY spans in the trace to see the number of round-trips.
3. Inspect QUERY duration and FETCH duration separately.
4. Check jdbc.row-count to see how many ResultSet rows were read.
5. Cross-check Hibernate Statistics for entity/collection fetches and cache hits/misses.
6. Look for repeated SQL or queries exceeding the slow threshold.
7. Check whether Page triggers a count query.
8. Obtain the execution plan of slow SQL and inspect indexes/joins/sorts.
9. Test fetch plans, projections, batch sizes, or indexes in a test environment.
10. Re-run the same workload and compare query count, p95/p99, row count, cache metrics, and business results.

Example symptoms and investigation paths:

| Symptom | Possibilities to check |
|---|---|
| Many identical queries with different IDs | N+1 or LAZY access inside a loop |
| Few queries but many ResultSet rows | JOINs creating duplicate rows or query returning too much data |
| Fast query execute but slow FETCH | Large result set, fetch size, network, or mapping |
| Low query count but one very slow query | Execution plan, indexes, locks, sorting, or I/O |
| Query count spikes when cache is cold | Cache misses, un-warmed cache, or unstable cache keys |
| Page endpoint always runs an extra query | Count query to compute totalElements |
| SQL log shows many SELECTs by association | Suboptimal fetch plan or N+1 |

## 17. Common Measurement Mistakes

### 17.1. Treating Global Statistics as Single-Request Metrics

Hibernate counters belong to the SessionFactory and accumulate across multiple sessions. Taking before/after deltas on a request in production can mix in activity from other requests.

Use JDBC spans/observations with trace context when per-request metrics are needed.

### 17.2. Measuring Only Query Execution Time

A query returning hundreds of thousands of rows may spend little time starting execution yet take a long time to fetch and map. Measure QUERY and FETCH separately while tracking row counts.

### 17.3. Confusing Row Count with Entity Count

JOINs can return multiple SQL rows for one root entity. Page totalElements is also a logical total, not the row count of the content query. State clearly which layer a metric measures.

### 17.4. Enabling Bind Logging in Production Without Masking

Bind logs can expose sensitive data. Only enable them when needed, limit scope and duration, protect logs, and disable them after investigation.

### 17.5. Looking Only at Averages

Averages can hide very slow requests. Track histograms/percentiles and max query times alongside throughput.

### 17.6. Resetting Statistics in a Running Application

statistics.clear() resets SessionFactory-wide counters. Calling it from a request can disrupt continuity of metrics for other requests. Only reset in isolated tests or controlled operational procedures.

### 17.7. Assuming Cache Hits Are Always Good

Cache hits can reduce SQL, but caching carries memory, invalidation, and stale-data costs if misconfigured. Evaluate hits/misses alongside freshness, latency, and correctness.

### 17.8. Optimizing Queries Without Checking Execution Plans

Adding indexes or changing fetch strategies without inspecting SQL/plans can slow down other workloads. Validate with production-like data and workloads.

## 18. Testing Query Count and Row Count in Integration Tests

You can use Hibernate Statistics in tests to verify a use case does not emit unexpected queries. Only use snapshots in isolated tests to avoid setup/teardown operations skewing counters.

Example:

~~~java
@DataJpaTest
class OrderQueryCountTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void loadsOrdersWithoutUnexpectedCollectionQueries() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        repository.findRecentOrders();

        long queryCount = statistics.getQueryExecutionCount();
        long collectionFetches = statistics.getCollectionFetchCount();

        assertThat(queryCount).isLessThanOrEqualTo(2);
        assertThat(collectionFetches).isZero();
    }
}
~~~

This is an illustrative test. Seed data, and flush/clear the persistence context before the measured section if test setup executed queries; choose assertions matching the repository's actual fetch plan. Do not copy the threshold 2 to every use case. For paginated queries, a count query can be a valid execution.

To check ResultSet row counts, use QueryStatistics.getExecutionRowCount() for Hibernate-tracked queries or ResultSet observations from JDBC instrumentation. Do not infer SQL row counts from List.size() alone.

## 19. Observation Checklist Before Optimizing

- SQL logs show the actual statements Hibernate sends.
- Bound parameters have been verified in a safe environment.
- Query count is measured at the right layer and request/test scope.
- QUERY and FETCH times are separated.
- Both SQL row count and returned entity/DTO count are available for comparison.
- N+1 is checked via repeated queries and collection/entity fetch counts.
- Cache hits/misses are read alongside query count and data.
- Slow queries have SQL comments or traces to link back to use cases.
- Execution plans are inspected before changing indexes or rewriting queries.
- Metrics include p95/p99, errors/timeouts, and controlled cardinality.
- Tests verify query count and business results after optimization.

## 20. Takeaways

- Hibernate SQL logging reveals generated SQL and bound parameters; use TRACE carefully because logs can contain sensitive data.
- hibernate.generate_statistics=true enables Hibernate Statistics; counters belong to SessionFactory and accumulate across sessions.
- Statistics provides query count, max query time, entity/collection fetches, and cache hits/misses.
- QueryStatistics provides execution count, average/max/min/total time, and processed ResultSet rows for a query string.
- Stream/scroll may not fully update row count in Hibernate QueryStatistics.
- Hibernate Statistics does not replace per-request metrics; use JDBC instrumentation and tracing to correlate SQL with requests.
- Datasource Micrometer distinguishes CONNECTION, QUERY, FETCH, and KEYS; ResultSet observations can provide jdbc.row-count.
- jdbc.row-affected reflects rows affected by DML, distinct from rows returned by SELECT.
- SQL rows, Java entity count, Page.getNumberOfElements(), and Page.getTotalElements() are different quantities.
- Fast QUERY execution does not mean a fast endpoint if FETCH, mapping, or serialization is expensive.
- Query count growing with entity count is a sign to check for N+1.
- Evaluate caches using hits/misses together with query count, duration, row count, and correctness.
- Use execution plans and representative workloads before adding indexes or changing fetch strategies.

Observing query count, SQL time, and returned rows turns Spring Data JPA optimization from guesswork into measurement. Be clear on whether you are measuring at the ORM, JDBC, or database layer, correlate metrics with requests, and validate every change on realistic workloads.

## References

- [Hibernate ORM 6.6 — Logging the Generated SQL, Statistics and Slow Queries](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
- [Hibernate 7.4 Javadoc — Statistics](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/Statistics.html)
- [Hibernate 7.4 Javadoc — QueryStatistics](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/stat/QueryStatistics.html)
- [Datasource Micrometer — Reference Documentation](https://jdbc-observations.github.io/datasource-micrometer/docs/current/docs/html/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)