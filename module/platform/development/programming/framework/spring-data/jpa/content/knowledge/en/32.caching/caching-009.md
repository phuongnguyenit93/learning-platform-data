# Measuring Hits, Misses, and Testing Correctness When Caching Is Enabled

When enabling caching for a Spring Data JPA application, merely seeing faster responses on a few calls is not enough to conclude that caching works properly. You need to measure cache hits and misses, identify which database queries are actually avoided, monitor evictions/expirations, and test that data remains accurate after creates, updates, deletes, or rollbacks.

Spring involves several different cache layers. Spring Cache typically caches a method's return value at the application layer; the JPA persistence context, JPA second-level cache, and Hibernate query cache each have distinct lifecycles and scopes. Before measuring, identify which cache you are measuring and which operations actually pass through that cache.

## 1. Distinguishing cache layers in a JPA application

A Spring Data JPA application can have multiple cache layers:

| Cache type | Scope | Data typically held | How to observe |
|---|---|---|---|
| Persistence context (first-level cache) | One `EntityManager`/transaction context | Loaded or managed entities | Track SQL and `EntityManager` state |
| JPA second-level cache | Shared across `EntityManager`s in a persistence unit | Provider-cached entities/collections | Hibernate/JPA provider statistics |
| Hibernate query cache | Per Hibernate configuration | Query results and region sync metadata | Hibernate statistics/metrics |
| Spring Cache abstraction | Per `CacheManager` and cache name | Method results, DTOs, or application values | Micrometer/provider cache statistics |

A second entity read within the same persistence context may emit no SQL even when Spring Cache has zero hits. Conversely, calling a cached method can hit Spring Cache and bypass the `Repository` method completely.

Therefore, do not use a single hit/miss number to represent all cache layers. Name metrics and dashboards specifically by cache layer.

## 2. What do hits and misses mean?

With Spring Cache, a cache lookup typically has two outcomes:

- **Hit:** the cache finds a valid entry for the key; the method marked cacheable does not need to execute its body.
- **Miss:** the cache has no entry for the key; the method runs, fetches source data, and the result can be stored in the cache.

Example:

~~~java
@Service
public class ProductQueryService {

    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Optional<ProductDto> findById(Long id) {
        return repository.findById(id)
                .map(ProductDto::from);
    }
}
~~~

With the same ID and an unexpired entry:

1. First call: cache miss, method runs and reads the Repository.
2. Subsequent calls: cache hit, method body is skipped.
3. Once the entry is evicted or expires: the next call misses and re-reads the source data.

This is method-level cache-aside. The cache does not automatically know if database data was modified by a batch job, direct SQL, or another application. The application needs an appropriate invalidation/expiration strategy.

## 3. Calculating hit ratio and miss ratio

If the cache provider exposes hit and miss counts over the same measurement window:

~~~text
totalGets = hits + misses
hitRatio  = hits / totalGets
missRatio = misses / totalGets
~~~

Example:

| Metric | Value |
|---|---:|
| Hits | 8,000 |
| Misses | 2,000 |
| Total gets | 10,000 |
| Hit ratio | 80% |
| Miss ratio | 20% |

An 80% hit ratio means 8 out of 10 cache lookups found an entry. It does not mean 80% of requests were served faster, since one request might call the cache multiple times or not at all.

If `totalGets` equals 0, hit ratio is undefined; do not divide by 0 or display 0% as if traffic existed. Display "no samples" or omit that interval.

Time-window measurements also require care. Provider counters are typically cumulative from cache creation or statistics reset. To compute rates over an interval, take delta hits and delta misses within that exact window rather than mixing cumulative totals across different intervals.

## 4. Metrics worth tracking

Hits/misses are only part of cache health. You should also monitor:

| Metric | Question to answer |
|---|---|
| Gets / lookups | How often is the cache accessed? |
| Hits | How many times was an entry found? |
| Misses | How many times did the data source have to run? |
| Hit ratio | What share of lookups were served by the cache? |
| Puts / loads | How many entries were added or loaded? |
| Evictions | How many entries were removed due to capacity policies? |
| Expirations | How many entries reached TTL expiry? |
| Size / estimated size | Roughly how many entries is the cache holding? |
| Load duration | On a miss, how long does loading from source take? |
| DB query count/latency | Is caching actually reducing database load? |
| Memory/heap | How much memory is the cache consuming? |
| Error rate | Are there cache backend errors or timeouts? |

Exact metric names and availability depend on the cache implementation. Not every provider exposes eviction, expiration, load time, or size counters.

A high hit ratio while the database remains slow can happen if the cache covers only part of an expensive query, misses are very costly, cache hits do not avoid other queries in the request, cache serialization/networking is slow, or caching increases GC and memory pressure.

Evaluate effectiveness across latency, database load, memory, and correctness together.

## 5. Measuring cache with Micrometer and Spring Boot Actuator

Spring Boot Actuator integrates with Micrometer to export metrics for caches supported by the implementation/registry. For instrumented caches, common Spring/Micrometer metrics include:

- `cache.gets`: number of cache lookups, usually tagged with `result` to distinguish `hit` and `miss`.
- `cache.puts`: number of entry writes.
- `cache.evictions`: number of evictions.
- `cache.size`: estimated size if supported by the provider.

Actual metrics depend on the `CacheManager`, cache implementation, binder, and library versions. Some caches support only partial statistics; caches that do not expose native statistics may lack hits/misses or size. Inspect actual registered meters rather than assuming every cache exports all metrics.

Maven dependency example for Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Configuration to expose necessary endpoints in an appropriate environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Do not expose management/metrics endpoints to the public Internet without authentication and access restrictions. Endpoint exposure must follow the application's operational policy.

When Actuator's metrics endpoint is enabled, you can inspect cache metrics via the metrics endpoint, for example:

~~~text
/actuator/metrics/cache.gets
~~~

Responses can include tags like cache name and result. Exact query/tag syntax depends on the Boot/Micrometer version. If using a Prometheus registry, metric names are converted per Prometheus conventions; inspect the Prometheus endpoint to see the actual metric names and labels.

## 6. Enabling cache provider statistics

Spring Cache is an abstraction; `@Cacheable` annotations alone do not guarantee every provider records hits/misses. Statistics must be enabled in the provider's own way.

### Caffeine

With Caffeine, enable statistics using `recordStats()`:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(10_000)
                    .expireAfterWrite(Duration.ofMinutes(10))
                    .recordStats()
    );

    return manager;
}
~~~

Once enabled, the native cache provides `CacheStats`:

~~~java
CaffeineCache springCache =
        (CaffeineCache) cacheManager.getCache("products");

com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        springCache.getNativeCache();

CacheStats stats = nativeCache.stats();

long hits = stats.hitCount();
long misses = stats.missCount();
double hitRate = stats.hitRate();
~~~

This snippet uses Caffeine and Spring's `CaffeineCache`; corresponding dependencies are required. Without `recordStats()`, native hit/miss counts may not be recorded as expected.

### ConcurrentMapCache

`ConcurrentMapCache` is suitable for demos or simple applications, but is not a production cache with full TTL/size policies and statistics. Do not assume it provides native hit/miss counters like Caffeine.

### JCache, Ehcache, and other providers

JCache has an API for managing statistics, but statistics must be enabled in the cache configuration per provider. Ehcache, Hazelcast, Redis, and other implementations have their own ways of exposing metrics. Some metrics require an additional binder or integration.

General workflow:
1. Identify the `CacheManager` and cache type in use.
2. Enable stats per the provider's documentation.
3. Check whether the cache instance exposes native stats.
4. Register/enable the Micrometer binder if needed.
5. Trigger controlled hits and misses.
6. Read the metrics and verify counters increment accurately.

## 7. Distinguishing Spring Cache hits/misses from Hibernate L2 cache

If the application enables Hibernate's second-level cache, measure these metrics separately:
- Second-level cache hit count.
- Second-level cache miss count.
- Second-level cache put count.
- Query cache hit/miss/put counts if the query cache is enabled.

Hibernate statistics can be enabled via provider configuration, for example:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Then `SessionFactory` statistics can be accessed in an appropriate Hibernate configuration:

~~~java
Statistics statistics = sessionFactory.getStatistics();

long hits = statistics.getSecondLevelCacheHitCount();
long misses = statistics.getSecondLevelCacheMissCount();
long puts = statistics.getSecondLevelCachePutCount();
~~~

API names and packages may vary by Hibernate version. Enabling statistics adds overhead; enable it only in environments where observation is needed and verify the cost.

A Spring Cache hit can prevent the `Repository` from being called at all, so Hibernate's L2 cache records no lookup for that call. Conversely, a `Repository` call may be served by Hibernate's L2 cache without reading the database. Keep separate dashboards for each layer.

## 8. Basic testing: first call misses, second call hits

A good test must prove observable behavior, not merely check that an annotation exists.

You can test using a mock or spy dependency:
- Call the method with an uncached key.
- Verify the `Repository` was called once.
- Call again with the same key.
- Verify the `Repository` was not called again.
- Call with a different key.
- Verify the data source was called for the new key.

Illustrative example with Mockito and the Spring test context:

~~~java
@SpringBootTest
class ProductQueryCacheTest {

    @Autowired
    private ProductQueryService service;

    @Autowired
    private CacheManager cacheManager;

    @MockBean
    private ProductRepository repository;

    @BeforeEach
    void clearCache() {
        cacheManager.getCache("products").clear();
    }

    @Test
    void secondCallForSameKeyUsesCache() {
        Product product = new Product(10L, "Keyboard");

        when(repository.findById(10L))
                .thenReturn(Optional.of(product));

        Optional<ProductDto> first = service.findById(10L);
        Optional<ProductDto> second = service.findById(10L);

        assertEquals(first, second);
        verify(repository, times(1)).findById(10L);
    }
}
~~~

This example requires `@EnableCaching`, the `ProductQueryService` bean, `ProductRepository`, and a cache named `products`. `@MockBean` can be replaced with the corresponding mock bean mechanism for the Spring Boot version in use. If the method returns a DTO, the DTO needs proper `equals`/`hashCode` for comparison in tests.

This test confirms that the same key calls the `Repository` only once within the current cache scope. It does not yet prove invalidation, TTL, concurrency, or proper metric instrumentation.

## 9. Testing eviction after updates

A cache is only correct if stale data is removed or updated when the source changes.

Example:

~~~java
@Service
public class ProductCommandService {

    private final ProductRepository repository;

    public ProductCommandService(ProductRepository repository) {
        this.repository = repository;
    }

    @CacheEvict(cacheNames = "products", key = "#id")
    public void rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow();

        product.rename(newName);
    }
}
~~~

After calling `rename()`, the next read for the same ID must fetch the new data from the source and re-cache the new result.

A test should:
1. Read the product the first time to populate the cache entry.
2. Call the update command.
3. Re-query the same key.
4. Verify the `Repository` returns the new data.
5. Verify no stale value remains in the cache.

By default, `@CacheEvict` removes the entry after the method invocation completes successfully; `beforeInvocation = true` removes it before the method runs. If the database update fails and the transaction rolls back, evicting before the transaction finishes can cause unnecessary misses or races. Choose eviction timing according to transaction semantics and consistency requirements.

## 10. How CachePut and CacheEvict differ

| Annotation | Behavior |
|---|---|
| `Cacheable` | Checks cache first; on hit skips method, on miss runs and caches result |
| `CachePut` | Always runs method then writes result into cache |
| `CacheEvict` | Removes a single entry or the entire cache |
| `Caching` | Combines multiple cache operations on the same method |

Example using `CachePut`:

~~~java
@CachePut(cacheNames = "products", key = "#result.id")
public ProductDto update(ProductCommand command) {
    Product saved = repository.update(command);
    return ProductDto.from(saved);
}
~~~

`CachePut` is suitable when the method must always run and the new result should be placed in the cache. Do not combine `Cacheable` and `CachePut` on the same method arbitrarily, as their semantics can conflict; use separate methods and test explicitly.

For clearing the entire cache:

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void rebuildProductCatalog() {
    // Rebuild catalog.
}
~~~

Evicting everything can trigger many simultaneous misses afterward. If the cache is large or traffic is high, consider a refresh/warm-up strategy and avoid causing a thundering herd.

## 11. Testing correctness on transaction rollback

An important scenario: a cache-updating method runs inside a database transaction that later rolls back.

If the cache was already updated or evicted before the database committed, the cache may no longer reflect actual data. One approach is using a transaction-aware cache to defer put/evict/clear operations until the transaction commits successfully.

Example wrapping `CacheManager`:

~~~java
@Bean
CacheManager transactionAwareCacheManager(CacheManager delegate) {
    return new TransactionAwareCacheManagerProxy(delegate);
}
~~~

A transaction-aware decorator can defer supported cache write operations until after commit. When the transaction rolls back, pending cache operations are not executed.

This does not turn the database and Redis/Caffeine into a distributed transaction. The cache remains a separate system and can still face post-commit errors, failed evictions, or cross-node races. Design appropriate TTLs, retries, and synchronization mechanisms.

To test:
1. Populate an initial cache entry.
2. Start a transaction updating data and cache.
3. Intentionally throw an exception to trigger a rollback.
4. Re-read the database and cache.
5. Verify the cache does not hold the uncommitted value.

Do not place `@Transactional` on the test method itself in a way that causes the outer test transaction to mask the transaction boundary under test. Call the transactional service from a test without an outer transaction, then re-read in a fresh transaction.

## 12. Testing TTL and size-based eviction

Cache entries can expire based on TTL or be evicted when exceeding capacity limits.

Caffeine example:

~~~java
Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .recordStats()
        .build();
~~~

Testing TTL by waiting in real time makes tests slow and flaky. Caffeine supports a controllable ticker in tests to advance logical time without sleeping. For other providers, use clock/timer test hooks if available.

Checks to run:
- Entry exists before TTL.
- Entry is no longer returned after TTL expires.
- Eviction per `maximumSize` when cache exceeds capacity.
- Provider eviction/expiration metrics increment accurately.
- Cache does not retain data unboundedly as key cardinality grows continuously.

Do not assert that eviction occurs instantaneously if the provider uses asynchronous maintenance or eviction policies. Use the provider's appropriate test/maintenance APIs.

## 13. Cache keys must fully represent the result

An incomplete cache key can cause one request's data to be returned to another request.

Example where output depends on both product ID and tenant ID:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#tenantId + ':' + #productId"
)
public ProductDto findForTenant(Long tenantId, Long productId) {
    return repository.findForTenant(tenantId, productId)
            .map(ProductDto::from)
            .orElseThrow();
}
~~~

If only `productId` were used when the same ID can exist across multiple tenants, the cache could return data for the wrong tenant.

Keys may also need to include:
- Locale if results are translated.
- Currency if prices are converted.
- Role/permissions if results are filtered by access control.
- Version or filter parameters if results depend on them.
- Pagination/sorting parameters if caching result pages.

Do not include sensitive data in keys if keys might appear in metrics or logs. Use stable keys with bounded cardinality and avoid arbitrary very long strings.

## 14. Caching null, Optional, and not-found results

Cache behavior with `null`/`Optional` depends on Spring Cache version and provider. Explicitly decide whether to cache not-found results.

If caching negative lookups:
- Reduces repeated queries for non-existent IDs.
- However, a newly created entity can be masked by an old negative entry until eviction/TTL.
- TTL for negative results should generally be shorter than for stable data if business rules require it.

You can use an `unless` condition to prevent caching unwanted results. With `Optional`, Spring Cache supports unwrapping in current versions; verify the exact value passed into the `unless` expression for your project version. A common condition to avoid caching `null` results is:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#id",
    unless = "#result == null"
)
public ProductDto findById(Long id) {
    return repository.findDtoById(id).orElse(null);
}
~~~

The example above uses a nullable `ProductDto` return type to keep semantics clear. If a method returns `Optional`, write a test for `Optional.empty()` and verify whether the cache provider stores or skips that result as intended.

If you do not want to cache absent results, configure an explicit condition. If you do want negative caching, set an appropriate TTL and invalidation when new entities are created.

## 15. Cache stampede and concurrent load

When a key expires or is evicted, many concurrent requests can miss simultaneously and hit the database at once. This phenomenon is commonly called a cache stampede or thundering herd.

Ways to reduce the risk:
- Use per-key load synchronization if supported by the provider.
- Use `Cacheable(sync = true)` when semantics and the provider fit.
- Warm critical keys in a controlled manner.
- Use TTL with jitter to avoid many keys expiring simultaneously.
- Limit concurrency of expensive loading tasks.
- Use stale-while-revalidate if the business allows serving stale data during refresh.
- Protect the database with timeouts, rate limits, and bulkheads.

`sync = true` has provider-specific limits and is not a system-wide distributed lock. With multiple application instances, understand the cache backend's synchronization model.

Test concurrency with multiple threads accessing an uncached key simultaneously; count how many times the data source is called and verify results are not corrupted. Do not test sequentially and simply infer concurrency safety.

## 16. Multi-instance caching and invalidation

For an application running multiple instances:
- Each instance's local Caffeine cache is independent.
- Eviction on one instance does not automatically clear entries on another instance.
- Two instances can return different data over different time windows.
- Restarting an instance loses all entries in its local cache.

Redis or a distributed cache can share entries across instances, though invalidation and consistency still require design. If multiple applications write to the database, every writer must emit invalidation signals or rely on suitable TTL/freshness policies.

A common strategy is publishing a domain event/outbox after commit so instances or cache services evict affected keys. Messages can be delivered out of order or duplicated; consumers should be idempotent.

Do not assume `@CacheEvict` on a local cache synchronizes across the entire cluster. Identify the active `CacheManager` and actual broadcast mechanism.

## 17. Order-independent testing

Caches hold shared state across tests within the same `ApplicationContext`. If tests do not clear caches, outcomes can depend on execution order.

Best practices:
- Clear the specific cache before each test using `CacheManager`.
- Use distinct keys per test.
- Do not rely on leftover cache entries from previous tests.
- Do not use long `Thread.sleep()` calls to wait for TTL if the provider offers a test clock.
- Assert how many times the data source was called.
- Explicitly disable or configure caching for tests measuring uncached behavior.
- For transactional integration tests, understand the boundary between test transactions and service transactions.

Helper example:

~~~java
@BeforeEach
void clearProductCache() {
    Cache cache = cacheManager.getCache("products");
    if (cache != null) {
        cache.clear();
    }
}
~~~

Do not iterate `CacheManager.getCacheNames()` and wipe every cache if a test only owns one cache; clearing only the relevant cache avoids interfering with other test fixtures in a shared context.

## 18. Measuring caches with logs and dashboards

A useful dashboard should include:
- Hits and misses by cache name.
- Hit ratio over time.
- Puts, evictions, expirations.
- Cache size and memory usage if exposed by the provider.
- Latency of cached methods.
- Database query counts and corresponding query times.
- Cache backend error rate.
- Timeout/retry rates when using a distributed cache.

Split labels by stable cache names such as `products`, `customer-summary`, `pricing`. Do not use user IDs or dynamic keys as metric tags, as unbounded cardinality can overload the metrics system.

When comparing before and after enabling caching:
1. Use comparable workloads and datasets.
2. Record baseline database query counts and latency.
3. Warm the cache following realistic scenarios.
4. Measure hits/misses and latency in the same window.
5. Observe heap, evictions, and GC.
6. Test write workloads and invalidation latency.
7. Run cold-cache, warm-cache, and restarted-cache scenarios.

Do not look solely at average hit ratio. P95/P99 latency and database load usually reveal much more clearly whether caching improves real user experience.

## 19. Testing correctness with caching enabled: scenario matrix

| Scenario | What to verify |
|---|---|
| First read | Misses, calls data source, and stores result |
| Repeated read of same key | Hits, does not call source again |
| Read of different key | Independent miss for the new key |
| Update entity | Old entry evicted or replaced with new result |
| Delete entity | Deleted entity is not returned from cache |
| Transaction rollback | Uncommitted data is not cached |
| TTL expiration | Subsequent read reloads from source |
| Cache backend error | Fallback/error behavior matches design |
| Multiple instances | Invalidation propagates to instances per design |
| Two tenants with same ID | Keys are not shared across wrong scopes |
| Concurrent misses on same key | Does not trigger uncontrolled source load |
| Bulk/native update | Dedicated invalidation mechanism runs since callbacks do not fire automatically |

This matrix should be turned into test cases for critical caches, especially pricing, access permissions, order status, and frequently changing information.

## 20. Common pitfalls when measuring and testing caches

**Confusing first-level cache with a Spring Cache hit**

`EntityManager` can return an entity from the persistence context without running SQL. That does not prove a `@Cacheable` hit. Measure each layer separately.

**Failing to enable provider statistics**

Annotations work, yet hit/miss counters do not increment or export. Enable stats and inspect native cache/binder settings.

**Reading cumulative counters as per-minute rates**

Counters usually accumulate from startup/reset. Compute deltas over the same time window.

**High hit ratio yet database stays overloaded**

The cache may not cover heavy queries, misses may be too expensive, or requests run many other queries. Monitor DB query counts and latency.

**Forgetting to evict after update/delete**

The cache keeps serving stale data. Attach invalidation to every write path, including batches, native SQL, and external writers.

**Evicting before transaction commit**

If the transaction rolls back or a concurrent reader reloads stale data before commit, the cache becomes wrong. Consider transaction-aware caches and test races.

**Cache key missing tenant or business parameters**

Results from one user scope can leak to another scope. Design keys with every input determining the result.

**Caching entities with lazy proxies**

Detached entities or lazy associations can fail outside transactions. Caching DTOs/immutable read models is usually easier to control.

**Order-dependent tests**

Caches retain data from earlier tests. Clear caches and use distinct keys before each test.

**Assuming local eviction applies cluster-wide**

Each instance can hold its own cache. You need a distributed cache or broadcast invalidation.

**Using high-cardinality metric tags**

Tagging by user ID/cache key causes time series counts to explode. Use only labels with finite, stable value sets.

## 21. Safe cache rollout checklist

When enabling caching for a Spring Data JPA use case:

1. Identify cacheable data and the maximum staleness the business tolerates.
2. Choose the cache layer: Spring Cache, Hibernate L2, or query cache; avoid enabling unnecessary layers.
3. Choose keys containing all parameters, tenant, and context affecting results.
4. Choose a provider and configure TTL, maximum size, serialization, and statistics.
5. Place `@Cacheable` on appropriate read methods and ensure calls pass through the Spring proxy.
6. Place `@CacheEvict` or `@CachePut` on all relevant write paths.
7. Define behavior for transaction commits/rollbacks, bulk DML, and external writers.
8. Enable Micrometer/provider metrics and verify actual hits/misses.
9. Write tests for misses/hits, distinct keys, updates, deletes, rollbacks, TTL, and concurrency.
10. Verify multi-instance invalidation if running multiple nodes.
11. Compare latency, database load, memory, and evictions before/after enabling.
12. Roll out gradually, monitor stale data/error rates, and retain the ability to disable caching if discrepancies arise.

## 22. Conclusion

Measuring hits and misses begins by identifying the cache layer. Spring Cache, the persistence context, and Hibernate's second-level/query caches have separate scopes and statistics. With Spring Boot/Micrometer, supported caches can export `cache.gets` with hit/miss tags, puts, evictions, and size; actual availability depends on the provider and binder. Hit ratio is calculated as `hits / (hits + misses)`, but deltas must be measured over the same time window alongside database latency, memory, and evictions.

Correctness testing must prove first-call miss, subsequent-call hit, independent keys, update/delete invalidation, rollback, TTL, concurrency, and multi-instance behavior. Cache keys must fully represent the data, transactions must coordinate with cache mutations, and every database write path must have an invalidation strategy. Caching is only worth enabling when benefits are measurable and data remains accurate within the business's freshness requirements.
