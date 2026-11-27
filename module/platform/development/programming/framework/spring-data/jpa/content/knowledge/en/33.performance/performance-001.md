# Setting Up Data and Measurements Before Optimization

**Module:** Spring Data JPA  
**Knowledge Group:** Caching

## 1. Objectives

After this lesson, you will be able to:

- Explain why a representative dataset and baseline are needed before optimizing.
- Design test data that reflects the scale, distribution, and relationships of real-world data.
- Build a repeatable workload and clearly define measurement conditions.
- Collect metrics from Hibernate, Spring Cache, the application, and the database.
- Distinguish between persistence context, Hibernate second-level cache, query cache, Spring Cache, and database cache.
- Evaluate cache hits, cache misses, latency, throughput, memory, and correctness after updates.
- Compare before and after optimization using the same data, workload, and environment.

## 2. Why Prepare Data and Measurements First?

Performance optimization is an experimental process. Without a representative dataset and a baseline, it is difficult to know where the system is actually slow, which change helped, and which change merely made a single run look better.

In Spring Data JPA, performance can be affected across multiple layers:

- SQL statements, indexes, execution plans, and the number of rows the database must read.
- The number of entities and associations Hibernate must hydrate.
- N+1 queries caused by accessing lazy relationships.
- Persistence context, second-level cache, and query cache.
- Spring Cache at the Service layer.
- Connection pools, thread pools, CPU, memory, and garbage collection.
- Operating system or database buffer caches.
- Network, latency between the application and the database, as well as concurrent load.

A high cache hit rate does not guarantee a faster endpoint. The cache might be returning an overly large object graph, incurring high serialization costs, or caching a query that was already very fast. Conversely, a moderate cache hit ratio can still significantly reduce database load if the avoided queries are expensive.

Before changing mappings, queries, indexes, or cache configurations, you need to answer three questions:

1. **Where is the system slow?** The application, Hibernate, the database, the network, or another layer?
2. **What does realistic load look like?** How many records, relationships, concurrent users, and what is the read/write ratio?
3. **How is success measured?** For example, lower p95, higher throughput, fewer queries, or lower database CPU while business results remain accurate.

Do not optimize just because a configuration sounds fast. Form a hypothesis, measure first, make controlled changes, and measure again.

## 3. Defining Use Cases and Optimization Hypotheses

Start with a specific business flow instead of measuring the entire application at once. For example:

- Opening a product listing page by category.
- Viewing product details along with category and images.
- Loading a customer's order history page.
- Searching for products by code or name.
- Repeatedly reading rarely changing configuration.
- Updating price or inventory and then reading the data back.

Each use case should be clearly documented:

| Item | Example to record |
|---|---|
| Endpoint or method | GET /products?category=... |
| Input data | Category, filters, page number, page size |
| Record counts | Total products, results per page |
| Relationships read | Category, images, reviews |
| Operation type | Read-only or includes writes |
| Read/write ratio | 95% reads, 5% updates |
| Concurrency level | 20, 100, or 300 concurrent requests |
| Data freshness | Can be 30 seconds stale or must update immediately |
| Target metrics | p95, query count, database CPU, cache hit |

Then write a testable hypothesis. For example:

> The listing page currently generates one query per product when reading the category name. If we switch to a DTO projection with the necessary join, the query count per request will drop and p95 will be lower while pagination results remain unchanged.

A caching hypothesis might be:

> Category information changes infrequently and is read repeatedly by many requests. If we cache the category DTO for 60 seconds, the number of database queries will decrease. We also need to check hit ratio, memory, latency on cache miss, and delay when a category is updated.

The hypothesis must state both the expected benefit and the risks to verify. With caching, risks often include stale data, invalidation overhead, cache stampede, or excessive memory consumption.

## 4. Preparing a Representative Dataset

### 4.1. Data Scale Must Be Close to Reality

A query may run very fast with 100 records yet become noticeably slow with millions of records. Choose at least a small scale for functional testing and a scale close to expected load for performance measurement.

For example, in an e-commerce application:

- 100,000 products.
- 10,000 categories.
- 1,000,000 orders.
- An average of 3 order lines per order, but some orders containing dozens or hundreds of lines.
- A small group of products with high traffic, and the rest rarely accessed.

These numbers are only examples. Base them on your current scale, growth projections, and application load requirements.

### 4.2. Data Distribution Matters as Much as Volume

Do not generate only uniformly distributed data if the real system has significant skew. Realistic data often has:

- Some categories with a very large number of products.
- Some customers with much larger transaction histories.
- Certain products read continuously, creating a hot dataset.
- Many old records that are rarely accessed.
- Null values, varying statuses, and strings of varying lengths.
- Optional relationships or empty collections.

For caching, simulate both hot keys and cold keys. If every request accesses the exact same product, the cache hit rate may be very high without representing a workload with hundreds of thousands of distinct keys.

### 4.3. Maintain Valid Relationships and Constraints

Test data must comply with foreign keys, unique constraints, data types, and business states. For example, an OrderLine must reference an existing PurchaseOrder; a Product must have a valid category if required by the mapping.

If the data does not reflect actual relational structure, fetch plan and cache measurements can be skewed. Generate data in the proper dependency order or use the project's migration/seed data tools.

### 4.4. Use Reproducible Data

A benchmark run must be repeatable. You should:

- Use a fixed seed or deterministic data generation rules.
- Record the schema, migration, and application versions.
- Record the row count of each table.
- Record index, constraint, and database configurations.
- Have a command to reset or recreate the test environment.
- Avoid using real personal data without an authorized process; synthetic data is usually more appropriate.

You can use Testcontainers to run the same database engine in integration tests. If production uses PostgreSQL, measuring on H2 may not accurately reflect PostgreSQL indexes, planner, data types, locking, or SQL behavior.

### 4.5. Avoid Creating Overly Simplistic Data

A dataset with only sequential IDs, short names, and one-to-one relationships often fails to expose issues with selectivity, large collections, pagination, or access distribution. Simulate edge cases that affect queries and caches.

## 5. Defining the Workload to Measure

The dataset is only half of the test. The other half is how the application accesses the data.

A load scenario should define:

- Request ratio for each endpoint.
- Ratio of reads, inserts, updates, and deletes.
- Number of concurrent users or requests per second.
- Page size and sorting criteria.
- Ratio of hot keys versus rarely accessed keys.
- Ratio of new data versus existing data.
- Update frequency that triggers cache invalidation.
- Run duration long enough to observe steady-state behavior.

Example simulated workload:

| Request type | Ratio | Behavior |
|---|---:|---|
| Product list | 50% | Pagination, filtering by category |
| Product details | 30% | Reading product and related details |
| Search | 15% | Varying keywords, different results |
| Product update | 5% | Changing price or status |

Not every request should use the same key. If a load tool simply repeats one request with the same parameters, results will be biased toward a hot cache. Distribute keys according to realistic access patterns.

## 6. Recording the Measurement Environment

When comparing two runs, you need to know whether the environment was identical. Record:

- CPU, RAM, number of application instances, and container limits.
- JDK, Spring Boot, Spring Data JPA, and Hibernate versions.
- Database version, connection pool configuration, and connection count.
- Database schema, indexes, and statistics.
- Cache provider, capacity, TTL, eviction policy, and topology.
- Logging, tracing, metrics, and profiler configuration.
- Network between the application and the database.
- Concurrency level, warm-up duration, and measurement duration.

Do not compare a run on an idle machine against a run when the database has heavy background load and conclude that the code change caused the difference.

Also distinguish caches at different layers. The database buffer cache may already hold data pages in RAM even when the Hibernate second-level cache does not have the entity. Therefore, a "cold application cache" is not necessarily a "cold database".

## 7. Measuring the Baseline Before Optimization

The baseline is the result of the current version with the defined dataset and workload. Run it at least several times after warm-up, record each run's results, and use appropriate statistics.

### 7.1. Latency

Record:

- p50: half of the requests complete within this time or faster.
- p95: 95% of requests complete within this time or faster.
- p99: reflects the slow tail, useful when the system has outlier requests.
- Average: can be referenced, but is easily skewed by outliers.

Do not report only the average time. A change might lower the average while increasing p99 due to lock contention or cache stampede.

### 7.2. Throughput and Errors

Measure requests/second or transactions/second alongside error, timeout, and retry rates. Higher throughput is not an improvement if the system returns incorrect data or produces more errors.

### 7.3. Query Count

Count SQL statements per request/use case, while classifying them:

- SELECT, INSERT, UPDATE, DELETE.
- Repeated queries.
- Queries triggered by lazy associations.
- Count queries used for pagination.
- Queries loading collections.

An endpoint running only two SQL statements can still be very slow if each returns millions of rows. Therefore, query count must be paired with row counts and execution time.

### 7.4. Resources

Record application CPU, database CPU, heap, garbage collection, active/idle connection pool counts, threads waiting for connections, and network data transferred. Caching may reduce database CPU while increasing application heap and GC.

## 8. Measurement Tools in Hibernate and Spring

### 8.1. Hibernate Statistics

Hibernate provides statistics for queries, entities, collections, and the second-level cache. You can enable it in test configuration:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

In an isolated test, you can retrieve statistics via SessionFactory:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

// Execute the use case to measure here.

long queryCount = statistics.getQueryExecutionCount();
long entityFetchCount = statistics.getEntityFetchCount();
long collectionFetchCount = statistics.getCollectionFetchCount();
long cacheHits = statistics.getSecondLevelCacheHitCount();
long cacheMisses = statistics.getSecondLevelCacheMissCount();
long cachePuts = statistics.getSecondLevelCachePutCount();
~~~

The snippet above is an excerpt for use in a test or benchmark harness, not a standalone program. Statistics belong to the SessionFactory and can aggregate activity across multiple sessions. Do not run multiple concurrent benchmarks on the same SessionFactory and attribute all metrics to a single request. Isolate the scenario, reset statistics before measuring, and read the results after completion.

Hibernate Statistics has overhead. Only enable it in an appropriate measurement environment and understand the impact of statistics configuration on the results.

### 8.2. SQL Log

You can enable SQL logging in development or test environments:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

SQL logs help identify repeated queries and bound parameters. However, excessive logging can alter measurement timings. TRACE may log sensitive data; only enable it in a controlled environment and disable it after investigation.

### 8.3. Spring Boot Actuator and Micrometer

Spring Boot Actuator together with Micrometer can provide metrics for HTTP requests, the JVM, connection pools, and some instrumented caches. You can track:

- Request count and response time per endpoint.
- JVM heap, GC pauses, and threads.
- HikariCP active, idle, and pending connections.
- Cache hits, misses, puts, and evictions if the CacheManager/provider is instrumented.
- CPU and container resources via your deployment monitoring system.

Do not inspect a single metrics endpoint and draw conclusions about performance. Combine application metrics with database metrics and the workload generating the requests.

## 9. Measuring Directly at the Database

### 9.1. Inspecting Execution Plans

Use database tools to inspect the execution plan, indexes used, estimated rows, and actual rows. With PostgreSQL, for example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name, price
FROM product
WHERE category_id = 42
ORDER BY name
LIMIT 20;
~~~

ANALYZE executes the query to collect actual timings and row counts. Only use it with safe queries in an appropriate environment; for DML statements with side effects, have a clear rollback and control strategy. BUFFERS helps observe buffer read activity.

Do not add an index just because a query looks slow. Examine the planner, selectivity, index column order, sort cost, returned row count, and the impact of the index on INSERT/UPDATE/DELETE.

### 9.2. Separating Application Time from SQL Time

Endpoint time includes several parts: waiting for a connection, executing SQL, hydrating entities, mapping DTOs, business logic processing, serializing, and transmitting the response. Low SQL time does not guarantee a fast endpoint if the application builds a huge object graph or serializes too much data.

Use tracing or a profiler to identify which part consumes time. Compare total time against query time to find non-database overhead.

## 10. Distinguishing Cache Layers

Before attempting to optimize caching, you must identify which layer the cache you are measuring belongs to. Layers have different scopes and invalidation mechanisms.

| Cache layer | Scope | Typically stores | Lifecycle |
|---|---|---|---|
| First-level cache | One persistence context/EntityManager | Managed entities | Ends when the persistence context closes or is cleared |
| Second-level cache | Multiple persistence contexts in the same application/provider | Entity or collection state configured for caching | Follows provider, region, and invalidation policy |
| Query cache | Hibernate SessionFactory/provider | Cached query results, depending on query type | Follows query cache configuration and related data regions |
| Spring Cache | Application/service layer | DTOs, computed results, or objects keyed arbitrarily | Follows CacheManager, TTL, and eviction |
| Database buffer cache | Database engine | Data pages and index pages | Follows database memory and policies |
| External cache | Multiple application instances if shared | Values by key | Follows systems like Redis or Memcached |

### 10.1. First-Level Cache

The first-level cache is the EntityManager's persistence context and is built into JPA. When an entity is already managed in the persistence context, looking it up again by the same identity typically returns the same managed instance.

It is not a shared cache across all requests or all transactions. When the EntityManager closes or `clear` is called, entities are no longer in that persistence context.

Also do not assume every repeated JPQL query is bypassed entirely by the first-level cache. The query may still need to run to determine the result set; the provider then reconciles entities by identity within the persistence context.

### 10.2. Second-Level Cache

The second-level cache sits outside a single persistence context and can reuse data across Sessions/EntityManagers if the provider and cache are configured. Hibernate does not automatically enable and store every entity in the second-level cache just because the application uses Spring Data JPA.

Example entity mapping that can use caching:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "products"
)
public class Product {
    // ID and attributes
}
~~~

Configuration must include dependencies and a region factory/provider compatible with the Hibernate version in use. Example properties to enable the second-level cache:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
~~~

Region names, capacity, TTL, and synchronization policies depend on the cache provider. Do not copy a region factory configuration from another Hibernate version without verifying compatibility.

Common Hibernate concurrency strategies include:

- READ_ONLY: for data that does not change after creation.
- NONSTRICT_READ_WRITE: tolerates a window during which cached data may not be strictly synchronized.
- READ_WRITE: coordinates soft locks/invalidation via the provider to support mutable data.
- TRANSACTIONAL: requires the provider to support the corresponding transactional strategy.

Choose the strategy based on update characteristics and provider capabilities. Do not cache frequently changing entities without a clear consistency strategy.

### 10.3. Query Cache

The query cache is a Hibernate-specific feature distinct from the second-level cache. It stores the results of queries marked as cacheable. For queries returning entities, the result typically involves entity IDs; entity state still needs to be retrieved from the persistence context or second-level cache.

Example query marked cacheable using a Hibernate hint:

~~~java
@QueryHints(value = @QueryHint(
    name = "org.hibernate.cacheable",
    value = "true"
))
@Query("select p from Product p where p.category.id = :categoryId")
List<Product> findByCategoryIdCached(
        @Param("categoryId") Long categoryId);
~~~

To use the query cache, you must enable it in Hibernate:

~~~properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
~~~

The query cache is not a default solution for every query. With frequently changing data, results may be continuously invalidated. The query cache also requires monitoring regions and hit/miss counts. Measure both the cacheable query and the cost of fetching entity state.

### 10.4. Spring Cache

Spring Cache is an abstraction at the application layer. It can cache DTOs or Service method results without requiring the result to be a JPA entity.

Example caching product summary information:

~~~java
@Service
@RequiredArgsConstructor
public class ProductQueryService {

    private final ProductRepository repository;

    @Cacheable(
        cacheNames = "product-summary",
        key = "#id",
        unless = "#result == null"
    )
    @Transactional(readOnly = true)
    public ProductSummary getSummary(Long id) {
        return repository.findSummaryById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Product not found"));
    }
}
~~~

ProductSummary should be a DTO containing the data needed for display, without lazy proxies or unloaded entity collections. The CacheManager determines whether the actual cache is local in-memory or distributed, as well as expiration and eviction policies.

When updating a product, the exact key must be invalidated:

~~~java
@CacheEvict(cacheNames = "product-summary", key = "#id")
@Transactional
public void updateProduct(Long id, UpdateProductCommand command) {
    // Load and update the Product entity
}
~~~

For systems with strict consistency requirements and high concurrent traffic, eviction should be designed around commit timing. You can publish an event after commit using @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT), and then evict the cache in the listener. This avoids evicting the cache before the database change is committed and another request reading stale data back into the cache in the meantime. The exact implementation must account for interceptor ordering, transactions, and the cache provider.

Cache annotations also typically rely on Spring proxies. Calling a @Cacheable method on the same bean can bypass the proxy, similar to self-invocation with @Transactional. Call it through another Spring bean or extract the method into a separate bean.

## 11. Designing Cache Measurements

A cache measurement must clearly separate cold and warm states.

### 11.1. Cold Cache

A cold cache is a state where the application cache does not yet contain the keys of the measured workload. Start by clearing or recreating the cache in the test environment, then run the scenario once to observe:

- Cache miss latency.
- Number of database queries triggered.
- Cost of populating the cache.
- Number of concurrent calls for the same key.
- Additional memory usage.

Do not assume a cold application cache means a cold database buffer cache. The database may still hold data and indexes in RAM from the previous run.

### 11.2. Warm Cache

A warm cache is a state where frequently used keys have already been populated into the cache. Run the steady-state workload and measure:

- Hit/miss ratio.
- p50, p95, and p99.
- Remaining database queries.
- CPU, heap, GC, and network.
- Number of evictions or puts.
- Processing time when keys expire or are invalidated.

Warm-up must simulate the workload's key distribution. Calling a single key repeatedly will produce overly optimistic results if production has many distinct keys.

### 11.3. Measuring Both Read and Write Paths

If you only measure GET after warm-up, you do not know how the cache behaves when data updates. Measure:

- Reading a cached key.
- Reading an uncached key.
- Updating an entity and reading it back.
- Updating multiple entities at once.
- TTL expiration and cache repopulation.
- Multiple concurrent requests asking for a recently expired key.

For write-heavy workloads, invalidation and synchronization costs can outweigh hit benefits.

### 11.4. Hit Ratio Is Not the Only Metric

Hit ratio is typically calculated as:

Hit ratio = Cache hits / (Cache hits + Cache misses)

For example, 9,000 hits and 1,000 misses yield a 90% hit ratio. However, if each hit only avoids a very lightweight query while each miss loads a large graph and waits a long time on the database, 90% is not enough to conclude the system is performing well.

Interpret hit ratio alongside latency, query count, memory, eviction, freshness, and error rate. Break down hits by cache region or cache name if the provider supports it.

## 12. A Repeatable Benchmark Process

A practical process:

1. Recreate or restore the defined test dataset.
2. Verify schema, indexes, record counts, and application configuration.
3. Disable unnecessary logs or profilers that add overhead; keep required metrics enabled.
4. Run warm-up so the JVM, connection pool, and database reach steady state.
5. Reset statistics and prepare the cache state for the scenario.
6. Run the workload with the same request distribution, concurrency, and duration.
7. Collect latency, throughput, errors, SQL count, cache metrics, CPU, heap, and database metrics.
8. Repeat multiple times, save each run's results, and compute percentiles.
9. Change exactly one primary factor, such as enabling a cache region or changing a query.
10. Re-run the same scenario and compare results.
11. Verify correctness, invalidation, and behavior when data changes.
12. Keep the change only if measured benefits outweigh operational costs and risks.

Record the code commit/version, configuration, data seed, benchmark commands, and results. This enables others to repeat the measurement and confirm conclusions.

## 13. Example Baseline Table

Suppose a product details endpoint is measured before and after adding Spring Cache. The following table only illustrates how to record metrics, not standard numbers for every system.

| Metric | Before cache | After warm-up | Notes |
|---|---:|---:|---|
| p50 | 42 ms | 8 ms | Typical latency dropped |
| p95 | 110 ms | 18 ms | Most requests are faster |
| Requests/second | 220 | 510 | Throughput increased under the same load |
| DB queries/request | 1.0 | 0.08 | Most requests do not query DB |
| Cache hit ratio | — | 92% | Must be read alongside latency and freshness |
| Heap used | 420 MB | 610 MB | Cache increases memory usage |

When analyzing, ask:

- Did p95 drop because of cache hits or another change?
- Did cache misses become slower than before?
- Did the higher heap cause longer GC pauses?
- After updates, was data invalidated properly?
- Do results hold when increasing the number of keys and concurrent requests?
- Were other endpoints affected by sharing CPU or memory?

With only a single run, results can be skewed by background load or database caching. Run repeatedly and keep conditions identical.

## 14. Verifying Correctness After Optimization

Performance optimization must not alter business semantics. For caching and fetch plans, verify:

- Return values before and after optimization are identical for the same data state.
- Optional relationships, empty collections, and null data are handled properly.
- Pagination neither loses nor duplicates entities.
- Sorting is stable, with a tie-breaker like ID when needed.
- Updates and deletes invalidate the appropriate keys/regions.
- Concurrent requests do not receive stale data beyond acceptable limits.
- Cache misses, timeouts, or provider errors have appropriate fallbacks.
- Cache keys include all parameters affecting the result, such as tenant, locale, access permissions, filters, and data version.

In particular, do not cache user-dependent or permission-dependent data using a key that only contains the resource ID. This can cause one user's results to be returned to another user. Include tenant/user/role or necessary authorization dimensions in the cache key, or do not cache such sensitive results.

## 15. Common Pitfalls in Measurement and Optimization

### 15.1. Measuring Only with a Few Records

Data that is too small fails to expose N+1 issues, missing indexes, large collections, or pagination costs. Test at a scale close to reality.

### 15.2. Running Once and Using Averages

A single run is prone to noise. Averages can hide tail latency. Warm up, run multiple times, and track p50/p95/p99.

### 15.3. Comparing Two Different Workloads

If the first run had 10 concurrent requests and the next had 100, you cannot attribute the difference solely to caching. Keep data, parameters, concurrency, and measurement duration equivalent.

### 15.4. Looking Only at Cache Hit Ratio

A high hit rate does not guarantee fast endpoints or accurate data. Measure latency, database load, memory, eviction, and invalidation.

### 15.5. Failing to Measure Cache Miss Cost

Cache misses can trigger concurrent queries for the same key, causing a cache stampede. Test when keys expire or right after the cache is cleared.

### 15.6. Caching Overly Large Entity Graphs

Caching an entity along with large collections can consume significant memory and complicate invalidation. For screens needing only a few fields, DTO caching is often easier to control.

### 15.7. Not Verifying Consistency After Updates

If data changes without timely cache eviction or updates, users may see stale prices, inventory, or statuses. Clearly define TTL, eviction, and acceptable stale data levels before deployment.

### 15.8. Enabling Verbose Logging During Benchmarks

SQL logging and bind TRACE can introduce significant overhead. Use logs for diagnostics, then re-measure with stable, appropriate observability settings.

### 15.9. Optimizing Before Forming a Hypothesis

Adding caches, indexes, and fetch joins simultaneously makes it impossible to tell which factor caused the change. Change one primary factor at a time and keep records of each experiment.

## 16. Checklist Before Concluding an Optimization Is Effective

- [ ] Use case and target metrics are clearly described.
- [ ] Dataset has scale, distribution, and relationships close to reality.
- [ ] Data and workload are reproducible.
- [ ] Code version, database version, and configuration are recorded.
- [ ] Baseline exists before changes.
- [ ] Warm-up completed and multiple repeated runs performed.
- [ ] p50, p95, p99, throughput, and error rate recorded.
- [ ] SQL count, database CPU, and execution plans measured when needed.
- [ ] Cold cache, warm cache, and database buffer cache distinguished.
- [ ] Hits, misses, evictions, memory, and GC recorded.
- [ ] Reads, writes, invalidation, and cache misses all measured.
- [ ] Business results, pagination, and access control remain accurate.
- [ ] Measured benefits outweigh memory and operational costs.
- [ ] Benchmark can be repeated to confirm conclusions.

## 17. Conclusion

To reliably optimize caching in Spring Data JPA, you must first prepare a representative dataset and workload, define target metrics, and measure a baseline. Distinguish between the persistence context, second-level cache, query cache, Spring Cache, and database cache because each layer has its own scope, cost, and invalidation mechanism. After each change, re-measure under the same conditions, test both read and write paths, and verify data correctness. Only keep optimizations when repeatable measurements prove real benefits.