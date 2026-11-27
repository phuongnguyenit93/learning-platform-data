# Designing Caches with Data Invalidation Strategies

Caching temporarily stores previously read or computed data to cut database queries, lower latency, and reduce load on upstream systems. With Spring Data R2DBC, caches typically sit at the service or read-model layer: the service checks the cache first, queries the repository on a miss, and populates the cache with the result.

The hardest part is not writing entries to a cache, but keeping cached data consistent with real state after creates, updates, or deletes. A caching strategy must explicitly define what is cached, how keys are built, how long TTLs last, when eviction occurs, and how multiple instances learn about mutations.

Foundational rule: **the database remains the system of record; the cache is a disposable or refreshable copy.** Prioritize write correctness and maintain a clear cache consistency policy.

## 1. Why Cache?

Suppose a product-read API is called many times per minute while underlying data changes only a few times a day. Querying the R2DBC database on every single request creates unnecessary round-trips.

Caching can:

- Reduce repeated read queries.
- Lower latency on cache hits.
- Reduce database and connection pool load.
- Increase resilience under heavy concurrent reads of the same data.
- Store expensive computations or assembled read models.

Caching does not automatically speed up every request. Cache lookups, serialization/deserialization, network hops to Redis, invalidation coordination, and memory management all carry costs. Rapidly mutating or write-once/read-once data is rarely worth caching.

### 1.1. A Cache Is Not the System of Record

Caches can expire, evict entries, restart, or lose data. The application must always be able to rebuild values from the database or authoritative source.

Never write a value only to a cache and treat it as durable state. If cache data disappears, business flows must fall back cleanly.

### 1.2. When to Cache?

Good caching candidates typically exhibit:

- Far more reads than writes.
- Relatively high query or computation cost.
- Tolerance for brief staleness, or a reliable invalidation path.
- Stable, deterministic keys.
- Bounded entry sizes and key counts.

Examples: product catalogs, display configurations, product details, public profiles, versioned price lists, and summary aggregates tolerant of short TTLs.

Data such as account balances, quotas, payment states, or inventory requires extreme care. When business decisions require up-to-the-moment truth, do not rely on potentially stale cache entries as the final authority.

## 2. Common Cache Topologies

### 2.1. In-Process Local Cache

A local cache resides inside a single application process's memory—Caffeine is a common example.

Advantages:

- Fast lookups with zero network hops.
- Simple setup for slowly changing data.
- No separate cache server to operate.

Limitations:

- Every instance holds its own isolated cache.
- Invalidating on instance A does not clear instance B's cache.
- Contents vanish on process restart.
- Memory must be bounded by size/weight and expiration.

Local caches fit rarely changing data or workflows tolerating short stale windows. Across multiple instances, broadcast invalidation or keep TTLs short enough to bound staleness.

### 2.2. Distributed Cache

Distributed caches typically run on Redis or another centralized cache store shared across application instances.

Advantages:

- All instances share cached entries.
- Cache survives individual application instance restarts.
- TTL and capacity scale independently from application processes.

Limitations:

- Lookups cross the network.
- The cache server can become a bottleneck or single point of failure.
- Requires managing serialization, connections, security, and operations.
- Invalidation still requires careful design.

In reactive applications, use Reactive Redis operations to keep cache access non-blocking.

### 2.3. Multi-Level Caching

Applications sometimes combine an L1 local cache with an L2 Redis cache:

~~~text
Request
  |
  v
Local cache (L1)
  | miss
  v
Redis (L2)
  | miss
  v
R2DBC database
~~~

L1 trims latency while introducing cross-instance invalidation complexity. On data updates, both Redis and every instance's L1 cache must be invalidated or refreshed. Pub/sub or messaging events can broadcast invalidations, with TTL acting as a final safety net.

Do not introduce multi-level caching without metrics proving the need. Each layer multiplies state synchronization complexity.

## 3. Cache-Aside: The Common Pattern for R2DBC

Cache-aside (lazy loading) is straightforward and easy to control:

1. Build the cache key from the request.
2. Read from the cache.
3. On a hit, return the cached value.
4. On a miss, query the database.
5. Store the result in the cache with a TTL.
6. Return the result to the caller.

~~~mermaid
flowchart TD
    A["Read request"]
    B["Lookup cache"]
    C{"Cache hit?"}
    D["Return cached data"]
    E["Query R2DBC repository"]
    F["Store in cache with TTL"]
    G["Return data from database"]

    A --> B --> C
    C -->|Yes| D
    C -->|No| E --> F --> G
~~~

This pattern works well when cache contents can be lost at any moment: the next request simply reloads from the database.

### 3.1. Cache-Aside Service Example with Reactive Redis

Assuming a configured `ReactiveRedisTemplate` with suitable key and value serializers for `ProductView`:

~~~java
public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Service:

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductQueryService {

    private static final Duration TTL = Duration.ofMinutes(5);

    private final ProductRepository repository;
    private final ReactiveRedisTemplate<String, ProductView> cache;

    public ProductQueryService(
            ProductRepository repository,
            ReactiveRedisTemplate<String, ProductView> cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public Mono<ProductView> findById(Long id) {
        String key = "product:v1:" + id;

        return cache.opsForValue()
            .get(key)
            .switchIfEmpty(
                repository.findById(id)
                    .map(ProductView::from)
                    .flatMap(view ->
                        cache.opsForValue()
                            .set(key, view, TTL)
                            .thenReturn(view)
                    )
            );
    }
}
~~~

`ProductView.from` is an application-defined factory method. Configure `ReactiveRedisTemplate` with explicit serializers; never rely blindly on defaults without verifying stored payload formats.

In this example:

- A cache hit returns `Mono<ProductView>`.
- A cache miss queries the repository.
- Database rows map into a read model.
- The cache stores the entry with a 5-minute TTL.
- The result still returns as a `Mono`.

If the cache write fails, this snippet propagates an error. Some systems choose fail-open: log/metric the cache error and still return database data. When implementing fail-open, catch only cache-operation errors—never swallow database failures into cache misses or empty results.

### 3.2. Avoid Querying the Database Twice

Never construct two independent publishers for the same request and subscribe to both. Place the miss path inside `switchIfEmpty`/`flatMap` so it runs only on a miss.

Reactive publishers are typically lazy; calling a repository method creates a publisher without running SQL yet. However, subscribing to the same publisher multiple times can run the query multiple times. Structure chains so each request triggers only the intended single execution.

## 4. Cache Keys Must Capture All Inputs

A cache key identifies which request a cached value represents. Omitting a parameter that affects output can return wrong data.

Example for a filtered, sorted, paginated product list:

~~~text
products:v2:category=books:sort=price_asc:page=0:size=20
~~~

Keys should incorporate every factor capable of changing the result:

- Entity ID or aggregate ID.
- Tenant/customer/account ID when data is tenant-scoped.
- Filters and statuses.
- Sort order.
- Page/size or cursor.
- Locale when content is localized.
- Currency or pricing context.
- Schema/serialization version when needed.

Never key solely by `productId` if results depend on tenant or access permissions. Missing tenant IDs can leak data across tenants.

### 4.1. Use Namespaces and Versions

A structured key format:

~~~text
<application>:<region>:<schema-version>:<identifier>
~~~

Examples:

~~~text
catalog:product:v2:1042
catalog:search:v3:books:price-asc:0:20
~~~

Namespaces avoid key collisions with other apps. Versions let you evolve payload schemas or cache semantics without failing to deserialize old entries.

### 4.2. Canonicalize Keys

When keys encode dynamic filters, normalize ordering and formatting before building the key. Equivalent requests must produce identical keys.

For instance, a filter map with varying iteration order but identical entries should not yield two distinct cache keys because of unstable serialization.

For long multi-parameter keys, build a canonical string and hash it while keeping a human-readable prefix for metrics and operations.

## 5. TTLs and Expiration Policies

TTL (time to live) bounds how long a cache entry survives before expiring. TTL caps staleness even when an invalidation event is missed.

Example:

~~~java
cache.opsForValue()
    .set(key, value, Duration.ofMinutes(5));
~~~

Choose TTLs based on:

- Data mutation frequency.
- Business tolerance for stale reads.
- Database query cost.
- Reliability of active invalidation.
- Cache size and memory budget.
- Request rate and cache stampede risk on simultaneous expiry.

No single TTL fits all data. Static catalogs can live longer; volatile status views need short TTLs or immediate post-commit invalidation.

### 5.1. TTL Does Not Replace Invalidation

TTL only bounds maximum staleness. If data changes seconds after being cached, callers continue reading stale data for the rest of the TTL window.

When updates must become visible quickly, evict or update the cache on successful writes and treat TTL as a safety net for missed invalidations.

### 5.2. Add Jitter to Prevent Simultaneous Expiration

If thousands of keys are populated together with an identical 5-minute TTL, they expire together and trigger a sudden wave of database queries.

Add random jitter to TTLs, such as 0 to 30 seconds. Jitter spreads out expirations and reduces coordinated reload spikes.

### 5.3. Capacity Limits and Eviction

TTL alone does not bound memory. Caches need capacity policies such as maximum size/weight or Redis eviction rules. Without limits, one-off keys can grow memory unboundedly.

Track hit ratios, eviction counts, memory usage, and key counts by namespace to tune capacities.

## 6. Invalidating Caches When Data Changes

Three common strategies when writing data:

1. **Evict:** delete the entry so the next read reloads from the database.
2. **Update:** write the new value into the cache.
3. **Bump version/namespace:** increment a version so old keys become unreachable.

Eviction is usually simpler and safer than updating because you do not have to rebuild every affected cache representation accurately.

Example when updating a product:

~~~java
return productRepository.save(product)
    .flatMap(saved ->
        cache.opsForValue()
            .delete("product:v1:" + saved.id())
            .thenReturn(saved)
    );
~~~

This illustrates the concept, yet if repository save and cache delete share a reactive database transaction, cache deletion does not roll back with the database. Carefully control invalidation timing and transaction rollback handling.

## 7. Invalidate After Database Commit

A subtle race occurs when evicting caches before the database transaction commits:

1. Transaction begins updating the product.
2. Application deletes the cache entry.
3. Another request misses the cache and queries the database before transaction 1 commits.
4. That request reads old data and repopulates the cache.
5. Transaction 1 commits the new data.
6. The cache now holds stale data.

This is a stale repopulation race. For cache-aside, the standard practice is invalidating only after the write transaction commits successfully.

### 7.1. Separating a Transactional Writer from Post-Commit Eviction

Place the transactional write in a separate bean and run cache eviction downstream once the transaction publisher completes:

~~~java
@Service
public class ProductWriter {

    private final ProductRepository repository;

    public ProductWriter(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Product> update(Product product) {
        return repository.save(product);
    }
}
~~~

Coordinating service:

~~~java
@Service
public class ProductCommandService {

    private final ProductWriter writer;
    private final ReactiveRedisTemplate<String, ProductView> cache;

    public ProductCommandService(
            ProductWriter writer,
            ReactiveRedisTemplate<String, ProductView> cache) {
        this.writer = writer;
        this.cache = cache;
    }

    public Mono<Product> update(Product product) {
        return writer.update(product)
            .flatMap(saved ->
                cache.opsForValue()
                    .delete("product:v1:" + saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

Because `writer` is a separate bean, the call crosses the transaction proxy. The reactive transaction managed by `writer` finishes before emitting its result downstream. Cache deletion executes only after the writer publisher succeeds.

Do not place both methods in the same class and invoke one directly from the other when relying on proxy-based `@Transactional`; self-invocation bypasses transaction proxies.

A narrow failure window remains: the database commits, then cache eviction fails. For short-TTL data, logging and falling back to TTL expiry may suffice. When durable invalidation is mandatory, use an outbox.

### 7.2. Why Not Update Cache Before Commit?

Updating the cache before database commit exposes uncommitted state to other readers. If the database transaction later rolls back, the cache retains phantom data that never committed.

Only publish cache updates or evictions after commit unless a specialized consistency protocol proves pre-commit handling is safe.

### 7.3. Handling Cache Eviction Failures

Two common policies:

- **Fail request:** database committed but eviction failed, so the request fails. Callers may retry even though the write already succeeded; requires idempotency.
- **Fail open:** log/metric the cache failure and return database success. The cache stays stale until TTL expiry or asynchronous retry.

Neither fits every system. For pure performance caches, fail-open is often sensible when TTLs bound staleness. Where stale reads violate business correctness, use durable invalidation and stronger read consistency.

## 8. Invalidating When One Record Affects Multiple Cache Keys

A single product update can affect many cached views:

- Detail by ID.
- Category lists.
- Keyword search results.
- Featured product lists.
- Aggregated pricing or stock pages.

Deleting `product:{id}` alone leaves stale entries in query caches.

Strategies:

### 8.1. Evict Entire Cache Regions

When query cache regions are small and region-wide eviction is supported, clear related regions:

~~~text
productById
productSearch
featuredProducts
categoryProducts
~~~

Simple to implement, though it reduces hit ratios after every write.

With Redis, never run `KEYS` across huge keyspaces in request paths. Use versioned namespaces, managed index keys, or background `SCAN` in maintenance jobs when enumerating keys.

### 8.2. Versioned Namespaces

Store a region version and embed it in keys:

~~~text
product-search:v17:<filter-hash>
~~~

When changes affect search results, bump the version to `v18`. Old keys immediately become unreachable and expire via TTL.

This invalidates broad regions without deleting individual keys. However, version increments must be atomic and all instances must read from the same version source.

### 8.3. Cache Tags or Indexes

Maintain a mapping of keys depending on a product or category so updates can delete every linked key. Flexible, yet maintaining tag indexes atomically introduces extra write amplification.

Use tags only when precise invalidation across multiple query representations is required. Simpler systems often run more reliably on short TTLs and region-level eviction.

## 9. Invalidation Across Multiple Application Instances

With local caches, each instance holds independent state:

~~~text
Instance A: local cache
Instance B: local cache
Instance C: local cache
         |
         v
      Database
~~~

If instance A updates the database and clears only A's cache, instances B and C continue serving stale values.

Options:

- Use a shared distributed cache like Redis for shared state.
- Publish invalidation events via a message broker/pub-sub so every instance clears its local entry.
- Keep TTLs short if brief staleness is acceptable.
- Use a shared version key across instances.

Redis Pub/Sub is not a durable queue: offline subscribers miss messages. When invalidations cannot be lost, use durable messaging or an outbox relay, ensuring consumers tolerate duplicates and out-of-order arrivals.

## 10. Using an Outbox to Guarantee Invalidation Delivery

A classic failure mode:

1. Database commits new data.
2. Process crashes before clearing Redis or publishing invalidation.
3. Cache continues serving stale data.

When invalidation must be durable, insert an outbox event inside the same transaction as the business update:

~~~text
Transaction Orders DB:
  UPDATE product
  INSERT outbox_message(ProductUpdated)
  COMMIT

Relay:
  read outbox
  publish ProductUpdated

Cache invalidation consumer:
  evict product detail and related query caches
~~~

The outbox guarantees the invalidation event persists atomically with the business change. Because relays may redeliver after crashes, consumers must be idempotent.

Across multiple instances with local caches, each instance must consume the invalidation or rely on a shared cache. Account for subscriber restarts, replays, and event ordering.

Outboxes improve reliability without guaranteeing instantaneous invalidation. A brief delay exists between database commit and consumer eviction. For strict read-after-write consistency, writers can bypass the cache or read directly from the database briefly.

## 11. Spring Cache Abstraction and Annotations

Spring's Cache abstraction lets applications use annotations or the `Cache` API decoupled from specific cache providers.

Common annotations:

| Annotation | Role |
|---|---|
| `@Cacheable` | Check cache first; on miss, invoke method and cache result |
| `@CachePut` | Always invoke method and update cache with result |
| `@CacheEvict` | Remove one or more cache entries |
| `@Caching` | Combine multiple cache operations |
| `@CacheConfig` | Class-level default cache/key settings |

Example:

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public Mono<ProductView> findById(Long id) {
    return repository.findById(id)
        .map(ProductView::from);
}
~~~

Starting with Spring Framework 6.1, cache annotations adapt to reactive return types such as `Mono` and `Flux`. `Mono` caches as an asynchronous value; `Flux` is collected into a `List` for caching and replayed as a `Flux`. Consequently, caching a huge `Flux` can materialize all items in memory.

Verify your Spring Framework version. Older versions lack this reactive adaptation behavior.

### 11.1. Cache Providers May Still Be Blocking

Reactive annotation adaptation does not automatically make underlying `Cache` implementations non-blocking. Synchronous providers can still perform blocking lookups or puts on calling threads.

When end-to-end non-blocking I/O is critical, verify the provider supports asynchronous cache retrieval or use a reactive API directly such as `ReactiveRedisTemplate`. Never assume a method returning `Mono` makes its entire cache path non-blocking.

### 11.2. Using `@CacheEvict` on Write Methods

Simple example:

~~~java
@CacheEvict(cacheNames = "productById", key = "#product.id")
public Mono<Product> update(Product product) {
    return repository.save(product);
}
~~~

Pay close attention to eviction timing relative to reactive transactions. Evicting before transaction commit risks stale repopulation races. For post-commit eviction, use after-invocation semantics supported by your version/framework, split the transactional writer from downstream post-commit eviction, or use an outbox for durable invalidation.

Do not rely on annotations without verifying exact interceptor ordering, transaction boundaries, and cache provider behavior for your Spring version.

### 11.3. Cache Keys with SpEL

Example:

~~~java
@Cacheable(
    cacheNames = "productByTenant",
    key = "#tenantId + ':' + #productId"
)
public Mono<ProductView> find(
        String tenantId,
        Long productId) {
    // ...
}
~~~

The key includes `tenantId` to prevent cross-tenant data leakage. Avoid putting secrets or unnecessary personal data in keys, as keys often appear in Redis monitoring and logs.

## 12. Caching Reactive Data with Reactive Redis

For non-blocking Redis operations, use `ReactiveRedisTemplate` or `ReactiveStringRedisTemplate` instead of synchronous `RedisTemplate`.

Configure serializers for keys and values on the template bean. Conceptual configuration:

~~~java
@Bean
ReactiveRedisTemplate<String, ProductView> productCacheTemplate(
        ReactiveRedisConnectionFactory connectionFactory,
        RedisSerializer<ProductView> valueSerializer) {

    RedisSerializationContext<String, ProductView> context =
        RedisSerializationContext
            .<String, ProductView>newSerializationContext(
                RedisSerializer.string()
            )
            .value(valueSerializer)
            .build();

    return new ReactiveRedisTemplate<>(
        connectionFactory,
        context
    );
}
~~~

`RedisSerializer<ProductView>` should use a JSON serializer with controlled type metadata. Exact constructor/builder APIs vary by Spring Data Redis version. Never enable broad polymorphic default typing for untrusted payloads.

Once configured:

~~~java
Mono<ProductView> cached =
    productCacheTemplate.opsForValue().get(key);

Mono<Boolean> stored =
    productCacheTemplate.opsForValue()
        .set(key, view, Duration.ofMinutes(5));

Mono<Boolean> removed =
    productCacheTemplate.opsForValue().delete(key);
~~~

All operations return reactive publishers that compose naturally via `flatMap`, `then`, and `switchIfEmpty` in services.

### 12.1. Cache Failures and Fail-Open

When Redis is unavailable, a pure performance cache can fall back to the database:

~~~java
Mono<ProductView> fromCache =
    cache.opsForValue()
        .get(key)
        .onErrorResume(error -> {
            metrics.cacheReadFailure();
            return Mono.empty();
        });
~~~

Then `switchIfEmpty` reads the database. Note that this merges cache misses and cache errors into the same empty signal; record separate metrics/logs to distinguish them.

When writing to the cache fails, you can still return the database result:

~~~java
return repository.findById(id)
    .map(ProductView::from)
    .flatMap(view ->
        cache.opsForValue()
            .set(key, view, TTL)
            .onErrorResume(error -> {
                metrics.cacheWriteFailure();
                return Mono.just(false);
            })
            .thenReturn(view)
    );
~~~

Apply fail-open only when caching is non-mandatory. Never swallow database or mapping errors inside cache fallback handlers.

## 13. Negative Caching: Caching Non-Existent Results

Some keys are requested repeatedly despite having no database row. Querying the database every time creates avoidable load.

Negative caching records that a key does not exist for a short period.

Because Reactive Streams forbid arbitrary null values, wrap presence state explicitly:

~~~java
public record ProductCacheEntry(
    boolean found,
    ProductView value
) {}
~~~

When `found=false`, the entry represents not-found. Negative entry TTLs are normally shorter than positive TTLs because a record could be created later.

When creating a new product, evict any matching negative cache key. Otherwise callers keep seeing “not found” until the TTL expires.

Negative caching suits IDs or keys that are frequently probed yet rarely created. Never cache transient technical errors such as timeouts or database unavailability as “not found”.

## 14. Cache Stampede and Concurrent Requests

A cache stampede occurs when a hot key expires or is evicted and many concurrent cache-miss requests hit the database simultaneously to rebuild the same value.

~~~mermaid
flowchart TD
    A["Cache key expires"]
    B["Request A: miss"]
    C["Request B: miss"]
    D["Request C: miss"]
    E["Three concurrent DB queries"]
    F["Database load spikes"]

    A --> B --> E
    A --> C --> E
    A --> D --> E
    E --> F
~~~

Mitigations:

- Single-flight / in-flight deduplication so concurrent misses for the same key share one load.
- Distributed locks when multiple instances can reload the same key.
- TTL jitter so keys do not expire simultaneously.
- Refresh-ahead (proactive refresh before expiration) for suitable keys.
- Concurrency limits on cache-miss paths.
- Stale-while-revalidate if the business permits serving slightly stale entries while refreshing.

### 14.1. Single-Flight Within One Instance

Within a single instance, requests can share an in-flight loading publisher keyed by cache key. Carefully manage map lifecycle so completed or failed publishers are removed; pinning them permanently replays stale values or errors forever.

Do not use a naive `ConcurrentHashMap` without cleanup, size caps, and cancellation isolation. One subscriber cancelling must not unintentionally cancel the shared load for other waiting subscribers.

### 14.2. Distributed Locks

Across multiple instances, in-memory locks in one process do not coordinate peers. Redis locks with unique tokens and TTLs can coordinate loads, provided only the token owner releases the lock. If a lease expires while a slow worker still runs, two workers can load concurrently.

Distributed locks add complexity and are not always necessary. Start with TTL jitter, concurrency limits, and sensible keys; add locks only when significant stampedes are measured.

## 15. Caching Queries, Pagination, and Aggregates

Caching an entity by ID is usually far easier to invalidate than filtered query caches.

Query cache example:

~~~text
product-search:category=books:sort=price:page=0:size=20
~~~

Updating one product's category or price can invalidate many query keys. Choose a policy:

- Short TTLs on query caches.
- Region eviction on product mutations.
- Versioned namespaces per category/search.
- Skip caching rare high-cardinality filter combinations.
- Cache size-bounded DTOs/pages.

### 15.1. Caching Paginated Data

A page cache key must include all output-affecting parameters: filters, sort, page/size, tenant, and locale. When returning page metadata, cache `content` and total count together as a single consistent entry.

Caching content and total separately lets them drift out of sync. That may be acceptable on dashboards, provided semantics are explicit.

### 15.2. Never Cache Unbounded Fluxes as a Single List

A `Flux` can represent a long or unbounded stream. Collecting an entire `Flux` into a cache risks unbounded memory growth and forces the first request to await full completion.

Cache a `Flux` only when it is a strictly bounded set with explicit size limits and TTLs. For large datasets, cache individual pages/chunks or bounded snapshots.

## 16. Caching and Transaction Consistency

Database transactions and Redis caches rarely share an atomic transaction. Define ordering and acceptable consistency guarantees explicitly.

Common options:

| Strategy | Order | Main Risk |
|---|---|---|
| Evict before DB commit | Clear cache, then write DB | Concurrent readers can reload stale data |
| Evict after DB commit | Commit DB, then clear cache | Cache remains stale if eviction fails |
| Update cache before commit | Write cache, then commit DB | Cache holds uncommitted data on rollback |
| Outbox invalidation | Commit DB + outbox; relay evicts later | Event delay; requires idempotent consumers |
| TTL-only | Wait for expiry | Stale data persists up to TTL |

For standard cache-aside, post-commit eviction is a solid default. When durable invalidation is critical, an outbox persists invalidation alongside business mutations.

### 16.1. Read-After-Write

When a caller updates a product and immediately reads it back, bypass the cache briefly or return the freshly saved representation directly.

For example, the update service returns the saved entity instead of re-reading the cache:

~~~java
return productWriter.update(command)
    .flatMap(saved ->
        evictRelatedKeys(saved.id())
            .thenReturn(ProductView.from(saved))
    );
~~~

If eviction fails under fail-open, the updater still receives fresh data. Subsequent readers might see stale data briefly; if unacceptable, require durable outbox invalidation or version-aware cache bypasses.

### 16.2. Version-Based Cache Validation

Store the entity version alongside cached payloads. When a newer version is known from the database, ignore lower-versioned cache entries.

Versioning catches stale entries when a trusted version signal exists. However, querying the database on every read just to check versions defeats caching. Use versions alongside shared version signals or invalidation events.

## 17. Caching Sensitive Data and Authorization

Never cache data solely by ID if output varies by user or permissions.

For example, an account view may differ by:

- Tenant.
- User ID.
- Role/permissions.
- Locale.
- Feature flags.
- Row-level visibility rules.

Omitting authorization context from cache keys risks leaking one user's representation to another.

Never cache passwords, access tokens, secrets, sensitive payment details, or unnecessary personal data. When sensitive data must be cached, evaluate encryption, access controls, TTLs, logging, retention, and compliance rules.

Nor should a cache serve as the final authorization check when permissions can be revoked dynamically. Revoking permissions must trigger corresponding invalidation or verify authorization against an authoritative store.

## 18. Observability and Operating Caches

Measure caches just like databases. Core metrics:

| Metric | Meaning |
|---|---|
| Hit count / miss count | How often the cache serves requests |
| Hit ratio | Cache hit proportion |
| Lookup latency | Time spent reading the cache |
| Load latency | Database query time on misses |
| Eviction count | Entries removed or expired |
| Cache write failures | Errors writing to cache |
| Cache read failures | Errors reading from cache |
| Entry count / memory usage | Cache footprint |
| Stale-read incidents | Detected stale reads |
| Stampede/load concurrency | Concurrent requests during misses |

A high hit ratio does not guarantee cache effectiveness. Serving stale data or filling memory with cold keys can hurt overall value.

Track database query counts and latency before and after enabling caching. Inspect p95/p99 to confirm real end-to-end tail-latency impact.

### 18.1. Logs and Traces

Attach cache region, redacted key namespace, hit/miss outcome, and correlation IDs to traces. Never log raw payloads or credentials.

When a cache miss triggers a database query, traces should capture both the cache lookup and the R2DBC query so time breakdown stays clear.

### 18.2. Degraded Mode During Cache Outages

If Redis is a performance optimization rather than a mandatory dependency, applications can fall back to the database during Redis outages. Ensure you have:

- Concurrency limits protecting the database from overload.
- Circuit breakers or rate limiters where needed.
- Dedicated alerts/metrics for cache unavailability.
- Alerts on prolonged cache disconnects.
- A recovery plan when Redis comes back online.

Fail-open is not free: when Redis goes down, every request floods the database. Unbounded fallback can trigger cascading failure.

## 19. Testing Caches and Invalidation

Tests must verify not only that values enter the cache, but also that invalidation fires at the right time.

Useful test cases:

- Cache miss queries repository and populates cache.
- Cache hit skips repository calls.
- Expired TTL entries reload from database.
- Committed updates evict detail keys.
- Rolled-back transactions do not emit invalidations as committed changes.
- Cache eviction failures follow the chosen fail-open or fail-closed policy.
- Mutations affecting query caches update corresponding regions/versions.
- Concurrent misses on the same key avoid flooding the database when single-flight is used.
- Multiple instances receive invalidation events.
- Duplicate invalidation events are handled idempotently.
- Different tenants/locales/filters produce distinct keys.
- Redis outages do not turn cache read errors into false “not found” responses.

For R2DBC, use integration tests with a real database or Testcontainers to test real transaction commit timing. For Redis, use a Redis Testcontainer to verify TTLs, serialization, and invalidation.

Do not mock the cache in every test. Mocks test unit logic, yet miss serializer bugs, TTL mistakes, key collisions, connection issues, and real reactive behavior.

## 20. Process for Designing a Cache for a Use Case

1. Identify repeatedly read data and current query costs.
2. Define business tolerance for stale data.
3. Choose local cache vs. distributed cache.
4. Define the cached representation: entity view, DTO, page, or summary aggregate.
5. Design keys capturing every parameter affecting output.
6. Select TTL, capacity bounds, and jitter.
7. Choose cache-aside or an alternative pattern.
8. Map every write path affecting which cache entries.
9. Evict/update after commit; use an outbox when invalidation must be durable.
10. Make invalidation consumers idempotent and coordinate across instances.
11. Bound stampedes and miss concurrency.
12. Measure hit ratio, latency, memory, and stale reads.
13. Test hits, misses, TTLs, rollbacks, invalidations, and outages.
14. Re-evaluate real gains; drop caching if operational cost outweighs benefit.

## 21. Common Mistakes

**Caching without invalidation.** Data stays stale until TTL expires. Identify all writes and impacted query caches.

**Evicting before transaction commit.** Concurrent readers repopulate stale data before the write commits. Evict after commit.

**Cache keys missing tenant or filters.** Risks leaking data across tenants, locales, or search criteria. Include full context in keys.

**Setting huge TTLs to inflate hit ratios.** Long TTLs widen staleness windows on missed invalidations. Match TTLs to business freshness needs.

**Assuming Redis Pub/Sub guarantees zero lost invalidations.** Offline subscribers miss messages. Use an outbox or durable broker when loss is unacceptable.

**Caching unbounded Fluxes.** Collecting whole streams consumes memory and pins resources. Cache bounded sets or pages.

**Using cache annotations with blocking providers.** Reactive return types do not make blocking cache I/O non-blocking. Verify async providers or use `ReactiveRedisTemplate`.

**Swallowing both cache and database errors.** Fall back only on identified cache failures; propagate database errors properly.

**Ignoring cache stampedes.** Concurrent misses spike database load. Use TTL jitter, single-flight, concurrency limits, or locks where needed.

**Updating cache before commit.** Database rollbacks leave uncommitted data in the cache. Update only after commit.

**Unbounded memory/keyspace.** One-off keys grow caches indefinitely. Enforce capacity caps, TTLs, and cleanup.

## 22. Design Principles

- Treat the database as the system of record and caches as rebuildable copies.
- Cache only when read frequency and latency targets justify operational cost.
- Choose local vs. distributed caches based on topology and consistency needs.
- Use cache-aside for straightforward read paths.
- Include tenant, filters, sort, page, locale, and all output-affecting parameters in keys.
- Use namespaces/versions for schema evolution and region invalidation.
- Pick TTLs from freshness requirements, add jitter, and cap capacity.
- Evict after database transactions commit successfully.
- Use an outbox when invalidation delivery must be durable.
- Build idempotent invalidation consumers and coordinate across instances.
- Avoid caching sensitive or permission-dependent data without proper key scoping and authorization checks.
- Never collect unbounded `Flux` streams into single cache entries.
- Verify cache providers are truly non-blocking when paired with WebFlux/R2DBC.
- Limit cache-miss concurrency to prevent stampedes and database overload.
- Measure hits/misses, latency, evictions, memory, cache errors, and stale reads.
- Test cache hits, misses, TTLs, rollbacks, invalidations, and outages.

## 23. Key Takeaways

Caching cuts repeated queries and latency, yet delivers value only when keys, TTLs, and invalidation are designed together. Cache-aside fits Spring Data R2DBC naturally: check cache first, query the repository on miss, then store the result. On writes, evict or update caches after database transactions commit; evicting before commit risks stale repopulation by concurrent readers.

Across multiple instances, coordinate invalidation via a distributed cache or durable events such as an outbox. TTLs cap staleness without replacing active invalidation. Handle duplicate events, stampedes, outages, tenant-scoped keys, and memory limits. In reactive applications, prefer reactive cache APIs such as `ReactiveRedisTemplate` to preserve non-blocking I/O, and cache `Flux` streams only when results are finite and strictly bounded.
