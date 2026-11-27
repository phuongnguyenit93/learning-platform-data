# Measuring Latency, Query Count, and Representation Size Before Optimizing

## Context

A Spring Data REST endpoint may look simple, yet each request can perform a great deal of work: authentication, repository querying, loading associations, converting entities into representations, generating HAL links, serializing JSON, and sending the response. Therefore, looking solely at lines of code or individual SQL query times is not enough to conclude whether an endpoint is fast or slow.

Before optimizing, measure at least three groups of data:

1. **Latency:** how long a request takes from the client and server perspectives.
2. **Query count:** how many SQL statements a request generates and how much time the DB accounts for.
3. **Representation size:** how many bytes the response contains, including JSON/HAL metadata and data content.

Measurements need to be tied to a specific endpoint, request type, page size, filter, projection, test dataset, and load level. A single number is not enough to represent the performance of the entire API.

The goal of a baseline is to answer: which requests are slow, at which layer they are slow, whether there are redundant queries, how large the response is, and how the results change after each adjustment.

## 1. Choose a Representative Workload

First, list the key requests of the API. For Spring Data REST, consider the following types:

| Request type | Example | What to observe |
| --- | --- | --- |
| Collection resource | `GET /orders?page=0&size=20` | Record count, pagination/count queries, payload |
| Item resource | `GET /orders/42` | Lookup query by ID, loaded associations, representation size |
| Association resource | `GET /orders/42/customer` | Query count and relationship data |
| Search resource | `GET /orders/search/by-status?status=PAID` | Filter query, sorting, pagination |
| Projection | `GET /orders/42?projection=summary` | Payload and queries compared to the default representation |
| Write request | `POST /orders`, `PUT /orders/42` | Validation, read/write count, transaction, and processing time |

You do not necessarily have to measure every endpoint right from the start. Prioritize endpoints that are called frequently, have large datasets, have complex associations, or are being reported as slow by users.

For each request, record:

- Method and URI, including query parameters.
- Authentication/role used in the measurement.
- `Accept` header and representation type.
- Page size, sort, filter, and projection.
- Number of records matching the query and actual number of records on the page.
- Dataset size and cache state.
- Expected concurrency level.

For example, `GET /orders?page=0&size=10` and `GET /orders?page=0&size=100` are two different workloads. Do not compare their timings as if the server were processing the same amount of data.

## 2. Measure Latency from the Client Side

Client-observed latency includes multiple components: network transit time, server waiting, application processing, database querying, response serialization, and body transfer. This is the metric closest to the client's experience.

You can use curl to capture the timing of a request:

    curl -sS -o response.json       -H "Accept: application/hal+json"       -w "status=%{http_code}\nstarttransfer=%{time_starttransfer}\ntotal=%{time_total}\nbytes=%{size_download}\n"       "http://localhost:8080/orders?page=0&size=20"

Useful fields:

- `time_starttransfer`: time from the start of the request to the first byte of the response (TTFB).
- `time_total`: total time to complete the request.
- `size_download`: number of body bytes recorded by curl for the download.
- `http_code`: status code, which helps detect failed requests rather than measuring only successful ones.

A single invocation is only one sample. To establish a baseline, run the same request multiple times and save the results. Separate warm-up runs from the main dataset to reduce the impact of JVM startup, JIT, connection pools, and initial caches.

When measuring over a real network, keep the request path (gateway, reverse proxy, TLS, compression) identical across comparisons. If you measure directly against localhost first and through a gateway later, the results are no longer under the same conditions.

## 3. Use Percentiles Instead of Looking Only at Averages

Latency typically has a skewed distribution: most requests are fast, while some requests are slow due to GC, DB contention, cache misses, connection pools, or anomalous queries.

At a minimum, report:

| Metric | Meaning |
| --- | --- |
| p50 | 50% of requests complete within this time or faster; close to the typical experience |
| p95 | 95% of requests complete within this time or faster; represents the slower tail group |
| p99 | 99% of requests complete within this time or faster; helps observe tail latency |
| max | Slowest request in the measured set; sensitive to outliers |
| throughput | Number of requests completed per second at the defined load level |
| error rate | Percentage of failed or timed-out requests |

Illustrative example results:

| Measurement run | p50 | p95 | p99 | Throughput | Error rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 45 ms | 180 ms | 420 ms | 120 req/s | 0.1% |
| After change | 38 ms | 95 ms | 210 ms | 145 req/s | 0.1% |

The numbers above only illustrate the presentation format and are not a Spring Data REST benchmark. When reporting actual results, always note the dataset, number of virtual users, duration, warm-up, environment, and application version.

Do not conclude an optimization succeeded just because p50 decreased. If p95/p99 or the error rate rises sharply, the change may worsen the experience for a subset of clients.

## 4. Measure Server-Side Latency with Micrometer

If the application uses Spring Boot Actuator and Micrometer, HTTP server metrics are typically published under the name `http.server.requests` (specific names/tags depend on version and configuration).

Example metrics endpoint configuration in a development environment:

    management.endpoints.web.exposure.include=health,metrics,prometheus

Do not expose all actuator endpoints publicly in production. Only expose necessary metrics over an administrative network and protect them with appropriate authentication/network policies.

You can inspect the metric via Actuator:

    GET /actuator/metrics/http.server.requests

Tag parameters can filter by method, status, URI, or outcome if the application's instrumentation provides those tags. Inspect the actual response to see which tags are available; do not assume the URI name is always recorded as the full path.

If exporting to Prometheus, you can build dashboards for:

- Request rate by endpoint.
- Duration distribution.
- Status codes and error rate.
- Latency comparison across endpoints.
- Correlation with DB connection pool and JVM metrics.

The Micrometer server timer measures application processing time according to its instrumentation; it does not include the entire time the client waits on the network. Keep both client and server measurements to distinguish application time from external latency.

## 5. Measure SQL Query Count

An endpoint reading a collection can generate more SQL queries than expected. For example:

- One query to fetch the page of data.
- One query to count the total number of records for pagination metadata.
- Multiple additional queries to load associations of each entity.
- Other queries caused by listeners, security, or application logic.

Query count must be measured on the same request and the same dataset. Do not look only at the application-wide query count over several minutes, because that number cannot be attributed to a specific endpoint.

### 5.1 Enable Hibernate Statistics in a Test Environment

With Hibernate, you can enable statistics to observe cumulative figures:

    spring.jpa.properties.hibernate.generate_statistics=true

You can retrieve `SessionFactory` statistics in code:

    @Component
    public class HibernateStatisticsProbe {

        private final EntityManagerFactory entityManagerFactory;

        public HibernateStatisticsProbe(
                EntityManagerFactory entityManagerFactory) {
            this.entityManagerFactory = entityManagerFactory;
        }

        public Statistics statistics() {
            SessionFactory sessionFactory =
                    entityManagerFactory.unwrap(SessionFactory.class);
            return sessionFactory.getStatistics();
        }
    }

The API above illustrates how to retrieve statistics; resetting and reading counters should be restricted to tests or profiling environments. Hibernate statistics are typically cumulative counters at the SessionFactory level. When multiple requests run concurrently, the difference in counters before and after a request cannot be treated as the exact query count of that request alone.

### 5.2 Record SQL Correlated by Request

To attribute queries to the right request, use one of the following approaches:

- SQL logging in a test environment with log correlation/request IDs.
- A datasource proxy or JDBC instrumentation capable of counting statements per request context.
- APM/tracing that instruments JDBC spans and attaches them to HTTP traces.
- Integration tests running a single request in isolation and counting statements.

A datasource proxy can record execution counts, duration of each statement, and operation types. Choose a tool that fits your current stack; avoid writing your own counter based on a global static counter in a multithreaded application.

Do not keep verbose SQL logging enabled for long periods in production without evaluating the performance impact, log volume, and sensitive data in parameters. Logging itself can alter the latency you are trying to measure.

### 5.3 Measure DB Time as Well

A low query count does not automatically mean a fast DB. A single query can scan a large table, perform a complex join, or wait on a lock. Conversely, many small queries can also cause overhead from round trips and N+1 issues.

For each request, try to record:

- Total number of SQL statements.
- Number of SELECT, INSERT, UPDATE, and DELETE statements.
- Total DB time and duration of each slow query.
- Query plans for important queries.
- Number of borrowed connections and connection wait time, if any.

Use the database slow query log or `EXPLAIN`/`EXPLAIN ANALYZE` according to your database engine to find execution plan issues. Only run analysis commands that execute queries in an appropriate environment; do not run them arbitrarily in production if the statement creates load or modifies data.

## 6. Identify N+1 and Association-Triggered Queries

A common ORM issue is N+1: fetching a list of N entities with one query, then issuing additional queries for each entity's association.

Conceptual example:

    SELECT * FROM orders LIMIT 20;
    SELECT * FROM customers WHERE id = 1;
    SELECT * FROM customers WHERE id = 2;
    SELECT * FROM customers WHERE id = 3;
    ...

If each Order's response needs its Customer, accessing the association during serialization can trigger multiple queries depending on the fetch strategy and persistence context configuration.

Signs:

- Query count grows nearly linearly with the number of items on the page.
- A request with size 10 executes significantly more queries than size 1.
- SQL logs repeat the same pattern, differing only by foreign key.
- Latency rises rapidly as page size increases.

Not every repeated query is an N+1 issue; you need to inspect the actual trace and mapping. Once the root cause is identified, consider:

- Projections that fetch only the required fields.
- Fetch joins or entity graphs appropriate for the use case.
- Batch fetching.
- DTO/read-model queries for aggregate endpoints.
- Avoiding serialization of unnecessary associations.

Do not mechanically apply fetch joins to collection pagination: joining a collection can duplicate rows, break pagination accuracy, or force Hibernate to paginate in memory. Verify the actual SQL and results after any change.

## 7. Measure Representation Size

Spring Data REST typically returns HAL JSON. The payload may include:

- Data in `_embedded`.
- Links in `_links`.
- Pagination metadata in `page`.
- Entity or projection fields.
- Associations and embedded resources.

Representation size affects bandwidth, serialization time, client parsing time, and memory. Measure the actual bytes of the response body rather than estimating from the field count.

You can save the response to check its size:

    curl -sS       -H "Accept: application/hal+json"       -o response.json       -w "status=%{http_code} bytes=%{size_download} total=%{time_total}\n"       "http://localhost:8080/orders?page=0&size=20"

Keep compression headers consistent across measurements. When comparing compressed and uncompressed bodies, explicitly note whether you are measuring bytes transferred over the network or JSON bytes after decompression. `Content-Length` may be absent when the response uses chunked transfer encoding; the client can still count received bytes.

For a representative set of responses, record:

| Metric | Purpose |
| --- | --- |
| Response bytes | Body size in the chosen transfer mode |
| Items returned | Number of items in the collection page |
| Bytes per item | Approximate average payload per item |
| Link count | Number of hyperlinks serialized |
| Embedded depth | Nesting level of representations/associations |
| Compressed bytes | Transfer size when compression is enabled |

`Bytes per item` is only an approximate comparison metric because HAL links and page metadata have a fixed overhead that does not scale linearly with the item count.

## 8. Compare Default Representation and Projection

One way to check payload cost is to compare the default representation with a projection:

    GET /orders?page=0&size=20
    Accept: application/hal+json

    GET /orders?page=0&size=20&projection=summary
    Accept: application/hal+json

If the projection returns fewer fields, the payload may shrink. However, do not assume that a projection always reduces query count or latency. Reading properties and associations in a projection can still trigger additional queries.

Measure all three groups of data before drawing conclusions:

- Client/server latency.
- SQL query count and DB time.
- Response bytes.

If the payload shrinks while query count increases, review how the projection accesses associations. If query count decreases while response bytes grow, the new representation may be embedding more data.

## 9. Design a Repeatable Measurement

A baseline procedure can be carried out as follows:

1. Prepare a representative dataset, including both record counts and association distribution.
2. Select a specific endpoint and request.
3. Fix the page size, sort, filter, projection, headers, and authentication.
4. Start the application and database; perform warm-up.
5. Send multiple sequential requests to measure baseline latency.
6. Run a load test with defined concurrency and duration.
7. Collect p50, p95, p99, throughput, and error rate.
8. Record query count, DB time, and response bytes.
9. Save configuration, logs/traces, and results under a single run ID.
10. Repeat the exact same procedure after each change.

You can use k6, Gatling, or JMeter to generate repeatable workloads and controlled concurrency. The load-testing tool must run on a machine with sufficient resources; if the load generator itself becomes CPU- or network-bound, the results will not reflect the server.

Do not change multiple factors at once. If you change page size, projection, fetch strategy, and database indexes simultaneously, it will be difficult to tell which factor caused an improvement or regression.

## 10. Baseline Table Template

Use a consistent table to compare before and after:

| Endpoint / scenario | Page size | p50 | p95 | p99 | SQL count | DB time | Body bytes | Error rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET /orders | 20 | — | — | — | — | — | — | — |
| GET /orders/42 | — | — | — | — | — | — | — | — |
| GET /orders?projection=summary | 20 | — | — | — | — | — | — | — |

Notes for each measurement run:

    Run ID:
    Commit/build:
    Environment:
    Dataset:
    JVM / heap:
    Database:
    Warm-up:
    Test duration:
    Virtual users:
    Cache state:
    Compression:
    Request headers:
    Observations:

Do not enter estimated numbers into the baseline table. If a measurement has not been taken yet, leave it blank and clearly note which data has not been collected.

## 11. Interpret Results to Choose an Optimization Direction

### High Latency, Low Query Count

You may need to inspect the query plan, locks, network, serialization, CPU, GC, or downstream services. A single SQL statement can still be very slow.

### High Latency, Query Count Grows with Page Size

Check for N+1 issues, lazy associations, projections, and fetch strategies. Compare sizes 1, 10, and 20 under the same conditions.

### Low Query Count, High DB Time

Check the execution plan, indexes, cardinality, sorting, and locks. Do not add indexes based solely on column names; inspect the actual queries and write costs.

### Large Payload, Fast DB

Inspect projections, embedded associations, link count, large text fields, and page size. Evaluate compression and a representation suited to the client.

### Low Server Latency, High Client Latency

Check TLS, gateway, proxy, DNS, network, response transfer, and client location. Client/server measurements help isolate time spent outside the application.

### Good p50, Poor p95/p99

Look for abnormally slow requests, unstable query plans, cache misses, connection pool waits, GC pauses, and concurrent load. Avoid optimizing solely for the median request.

## 12. Principles Before Optimizing

- **Measure first, change later:** record a baseline before adjusting fetch strategies, indexes, or serialization.
- **Keep the workload fixed:** compare the same dataset, request, page size, auth, cache state, and concurrency.
- **Measure across layers:** client, server, database, and payload.
- **Separate warm-up from main data:** JVM and caches can make the first few requests slower.
- **Do not trust a single run:** use multiple samples and report percentiles.
- **Do not optimize query count in isolation:** one query can be more expensive than several small queries.
- **Do not ignore error rate:** nice latency numbers with failing requests are not an improvement.
- **Record changes:** every optimization must have a commit/build and change description for comparison.
- **Evaluate trade-offs:** shrinking payload can increase queries; caching lowers latency but can affect freshness; fetch joins reduce queries but enlarge result sets.

Once an evidence-backed bottleneck is found, change only one primary factor, rerun the exact same workload, and compare the metrics. Keep the change when it improves the target without causing significant regressions in the remaining metrics.

## 13. Hands-On Exercise

Suppose the endpoint:

    GET /orders?page=0&size=20
    Accept: application/hal+json

returns 20 orders. Perform the following in a test environment:

1. Measure `time_starttransfer`, `time_total`, and response bytes using curl.
2. Repeat multiple times and compute p50, p95, and p99.
3. Enable HTTP server metrics and record application-side timing.
4. Collect an SQL trace tied to a single request ID to count statements.
5. Determine whether the query count grows with the number of items.
6. Record total DB time and check for slow queries.
7. Repeat with page sizes 1, 10, and 20.
8. Repeat with the summary projection.
9. Compare latency, query count, and payload bytes across scenarios.
10. Write a bottleneck conclusion based on the collected data, then propose a testable change.

Self-check questions:

- Why are p95/p99 more useful than averages?
- Why are Hibernate global statistics insufficient to attribute queries to a single request under concurrency?
- How do you recognize N+1 from a query trace?
- Why can a HAL response be large even when an entity has only a few fields?
- Does a projection always reduce the number of queries?
- When is client latency high while server latency is low?
- Which conditions must be kept identical when comparing before and after an optimization?

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Boot Reference — Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Hibernate ORM User Guide — Statistics](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [k6 Documentation](https://grafana.com/docs/k6/latest/)
