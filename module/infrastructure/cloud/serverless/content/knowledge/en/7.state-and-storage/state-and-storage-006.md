# External Caches and Cache Invalidation Rules

In serverless applications, many Java function instances can be spun up and run concurrently. Each instance can have its own memory, its own lifecycle, and can be reclaimed at any time. If each instance keeps a cache solely in RAM, instances can observe inconsistent data and the cache vanishes when the execution environment terminates.

An **external cache** is a caching service living outside the function's lifecycle, typically shared over the network, such as managed Redis or Memcached. It allows multiple function instances to share frequently read or computed data. However, when the source data changes, the cache can become stale. Therefore, cache design must answer two questions: which data is permitted to be cached temporarily, and how does the system remove or refresh stale cached entries?

This lesson focuses on external caches in serverless architectures, cache read and write strategies, TTL, invalidation, consistency, concurrency hazards, and how to implement a simple cache-aside pattern in Java.

## Learning objectives

After this lesson, you will be able to:

- Explain why external caches are useful when functions scale out across multiple instances.
- Distinguish cache-aside, read-through, write-through, and write-behind.
- Choose TTL and invalidation policies according to data freshness requirements.
- Identify cache stampedes, stale writes, and race conditions during data updates.
- Design cache keys that are safe across tenants and users.
- Write a Java service using Redis as a time-bounded cache, with fallback on cache failures and invalidation after source data commits.
- Monitor cache effectiveness via hit ratio, latency, evictions, and data age.

## 1. External caches in serverless environments

A cache stores a copy of data that can be reconstructed from another source, typically a database or a business service. Its goal is to reduce read latency, offload the data source, and avoid redundant computation.

In FaaS, a function can be invoked concurrently across multiple execution environments. Static variables or in-RAM caches are shared only across certain invocations within the same execution environment; they are not shared memory for the entire function. Environments can also be reclaimed without notice.

An external cache solves that sharing problem:

~~~mermaid
flowchart TD
    A["Function instance A"] --> C["External cache"]
    B["Function instance B"] --> C
    D["Function instance C"] --> C
    C --> E["Cache hit"]
    C --> F["Cache miss"]
    F --> G["Database / Source of truth"]
    G --> C
~~~

Multiple function instances can read from the same cache service. On a cache miss, the application reads from the source of truth and can store the result in the cache for subsequent reads.

Common benefits:

- Reduces query load on the database or calls to downstream APIs.
- Lowers latency for repeatedly read data.
- Absorbs part of read traffic spikes.
- Shares computed results across multiple function instances.
- Reduces data source cost when cache hit ratio is high enough.

An external cache also adds a network service onto the request path. It has its own latency, quotas, connection limits, cost, security requirements, and failure modes. If the cache becomes unavailable, the application must know whether it can fall back to the data source or must reject the request.

**A cache is not the source of truth.** The database or business service remains the authority for correct data. Cache entries can be deleted, expire, be evicted, or be lost; the application must always be able to rebuild values from the authoritative source.

## 2. When should you use an external cache?

Caching is appropriate when data is read frequently, reading from the source carries substantial cost, and a well-defined update lag is acceptable.

Examples:

- Product details or catalog entries read by many requests.
- Infrequently changing application configuration.
- Expensive aggregated query results.
- Short-lived tokens or metadata, if permitted by security policy.
- Reference data used across multiple functions.

Caching is usually unsuitable for rapidly changing data where every request must immediately observe the latest value, or for data whose caching cost exceeds the benefit of repeated reads. Do not cache sensitive or access-controlled data unless cache keys and authorization scopes are explicitly designed.

| Scenario | Consideration |
|---|---|
| Read-heavy, rarely updated | Typically a strong candidate for caching |
| Rarely read, continuously updated | Likely low benefit; consider skipping cache |
| Near-real-time freshness required by business | Short TTL or synchronous invalidation; define acceptable staleness clearly |
| Personal or per-tenant data | Requires access-scoped cache keys and appropriate deletion policies |
| Cache outage must not disrupt business | Design fallback, source load limits, and circuit breakers |

Before adding a cache, measure latency and load at the data source. A cache does not automatically speed up a system if most requests are cache misses, payloads are oversized, or the network hop to the cache costs more than querying the source.

## 3. Cache read and write strategies

### Cache-aside (lazy loading)

The application actively checks the cache. If data is present, return the cached entry. If missing, read from the data source, store the result in the cache, and return it.

~~~mermaid
flowchart TD
    A["Request"] --> B["Read cache"]
    B --> C{"Data present?"}
    C -->|Yes| D["Return cached"]
    C -->|No| E["Read database"]
    E --> F["Write cache with TTL"]
    F --> G["Return data"]
~~~

The advantage is that only data actually read gets cached. The application explicitly controls when the cache is populated and when entries are deleted. On the flip side, the first read after a cache miss is slower, and race conditions can occur if data changes while the cache is being populated.

### Read-through

The application reads through a cache layer; that layer fetches data from the source on a cache miss. This consolidates loading logic into a cache provider or library.

Read-through simplifies consumers, but requires a cache layer capable of reaching the data source and understanding data transformations. Not every Redis or Memcached service provides native read-through; sometimes it is implemented by a library or application wrapper.

### Write-through

When writing data, the application updates the authoritative source and the cache in a synchronous flow. The goal is for the cache to reflect changes immediately.

Write-through can reduce cache staleness, yet writing to the cache and database usually does not happen inside a single distributed transaction. If one operation succeeds and the other fails, the two can diverge. Define write ordering, retries, and reconciliation rules.

### Write-behind (write-back)

The application writes to the cache first, and an asynchronous process later persists the changes to the authoritative source.

This can reduce write latency and batch updates, but risks data loss if the cache or sync worker fails before durable persistence. Use it only when synchronization lag is acceptable and durable buffering, retries, backlog monitoring, and recovery exist. Never use a standard cache as the sole repository for critical business data.

| Strategy | Read path | Write path | Key characteristics |
|---|---|---|---|
| Cache-aside | App checks cache; reads source on miss | Updates source, then invalidates or updates cache | Popular, easy to control |
| Read-through | Cache loads from source on miss | Depends on cache mechanism | Centralizes loading logic |
| Write-through | Reads cache | Writes source and cache synchronously | Cache stays fresher, but dual-write failure handling needed |
| Write-behind | Reads cache | Writes cache first, updates source later | Faster writes, higher risk and complexity |

For many Java functions handling independent requests, cache-aside is typically the clearest starting point: the database remains the authoritative source, and functions populate or delete cache keys according to business rules.

## 4. TTL and invalidation

**TTL (time to live)** is the duration a key is permitted to remain in the cache. When the TTL expires, the cache service treats the entry as expired and removes it according to the product's expiration mechanics.

**Invalidation** is the act of preventing a cached value from being used further, typically by deleting the key or advancing a key version.

The two mechanisms complement each other:

- TTL sets an upper bound on data age in case invalidation is missed.
- Invalidation evicts stale data sooner when the application knows the authoritative source just changed.

### Choosing TTL based on acceptable staleness

TTL should not be picked simply as a convenient round number. Determine how stale data can safely be and the business impact if users see outdated values.

| Data type | Sample initial TTL for testing | Notes |
|---|---:|---|
| Infrequently changing config | 5–30 minutes | Can invalidate when config is published |
| Catalog or product details | 1–10 minutes | Delete key after price or status updates |
| Expensive aggregation results | 30 seconds–5 minutes | Approximate results may be acceptable depending on dashboard |
| Temporary metadata | Few seconds–few minutes | TTL must not exceed business validity window |
| Data requiring very high freshness | No cache or very short TTL | Evaluate consistency requirements carefully |

The ranges above are starting points for measurement, not universal defaults.

### Invalidate after source data commits

With cache-aside, a common rule is:

1. Update the database.
2. Confirm the transaction has committed.
3. Delete the corresponding cache key.
4. Let the next request read the source and populate the new value.

Never delete the cache before the transaction commits. If the transaction rolls back, the cache could be repopulated from old data or a concurrent request could read uncommitted state.

There is a subtler race condition: request A reads stale data from the database; request B updates the database and deletes the cache; then request A writes the stale data into the cache. The cache ends up holding the stale value despite invalidation running. Risk can be reduced using versioned keys, version-conditional writes, cache-fill locks, or short TTLs; the choice depends on consistency requirements and load.

### Event-driven invalidation

Once the database commits, the application can emit a `ProductUpdated` event so a consumer deletes or updates related cache entries. This helps when multiple functions or services share the cache.

However, writing to the database and publishing an event are two separate operations. If the database commit succeeds but publishing fails, the cache may never be invalidated. A **transactional outbox** writes the business change and the outbox event record in the same transaction; a separate publisher forwards outbox events and retries until delivery succeeds.

Illustrative flow:

~~~mermaid
flowchart TD
    A["Update data"] --> B["DB transaction"]
    B --> C["Write outbox event"]
    C --> D["Commit"]
    D --> E["Outbox publisher"]
    E --> F["ProductUpdated event"]
    F --> G["Cache invalidation consumer"]
    G --> H["Delete or version key"]
~~~

Invalidation consumers must also be idempotent: deleting a key multiple times must be safe. If events can arrive late or out of order, a data version prevents an older event from overwriting newer cache entries.

## 5. Cache keys: scoping, versioning, and security

Cache keys determine whether two requests share a value. If a key omits a factor that affects the output, the application can return wrong data or leak data across users.

A cache key should encode:

- Data type and schema version.
- Tenant or organization if data is tenant-isolated.
- Record identifier.
- Parameters that alter output, such as locale, currency, or permissions.
- Data version if protection against stale writes is needed.

Examples:

~~~text
product:v2:tenant-42:product-1042:vi-VN
profile:v1:tenant-42:user-781
catalog:v3:tenant-42:category-18:page-2
~~~

Never include access tokens, passwords, secrets, or sensitive data in keys. Avoid embedding raw client-controlled strings if they can be overly long or contain operationally problematic characters. Normalize or hash complex parameters when needed.

In particular, never cache personalized responses under a URL-only key if the response depends on the user or role. For example, customer-tier pricing must include the customer segment in the key or be cached at an equivalent safe scope.

### Key versioning

When data structures evolve, older cached values may fail to deserialize or lack new fields. Adding a version to the key such as `product:v2` allows the application to switch to the new schema without immediately purging all old keys. Old version keys expire naturally via TTL or policy cleanup.

Versioned keys can also enable group invalidation: bumping a generation/version for a tenant or category shifts new requests to a fresh namespace. This avoids deleting thousands of individual keys, though it requires managing the generation version and avoiding races during concurrent updates.

## 6. Cache stampedes and race conditions

### Cache stampede

When a popular key expires, many concurrent requests can hit a cache miss simultaneously and query the database at once. A massive load spike hits the data source right when the cache stops helping.

Mitigations for stampedes:

- **TTL jitter:** add or subtract a small random offset so many keys do not expire simultaneously.
- **Single-flight / request coalescing:** only one request loads a given key; concurrent requests wait for that result.
- **Distributed lock:** one instance holds a short-lived lock to populate the key; others wait or serve bounded stale data if policy allows.
- **Stale-while-revalidate:** return an expired value within allowed bounds while one background/foreground request refreshes the cache.
- **Pre-warming:** proactively populate critical keys ahead of predictable traffic spikes.

Distributed locks require leases, timeouts, and handling for lock-holder crashes. Never hold a lock longer than expected processing time or leave requests waiting indefinitely.

### Stale cache due to concurrent requests

Cache-aside can encounter the following interleaving:

1. Request A reads version 10 from the database.
2. Request B writes version 11 to the database and deletes the cache.
3. Request A writes version 10 into the cache after B deleted it.

As a result, the cache becomes stale again. When strict consistency is required, store the version inside the value and allow cache writes only when the version is no older than the current value; or embed the record version in the key itself. A simpler option is combining a short TTL with invalidation, accepting a brief observable staleness window.

### Cache outage

If the external cache loses connectivity, functions can fall back to the database. However, if all concurrent invocations fall back at once, the database can be overwhelmed.

Considerations:

- Short, bounded cache connection timeouts.
- Circuit breakers to stop hammering the cache while the service is down.
- Concurrency or rate limits on the fallback path.
- Serving stale values if business logic permits.
- Alerting when cache error rates rise and monitoring source data load.

Never let a cache outage turn into an unbounded retry loop or cause functions to hold connections too long.

## 7. Java example: cache-aside with Redis

The following example uses Spring Data Redis with `StringRedisTemplate` and Jackson `ObjectMapper`. The database is the source of truth. If the cache fails, the service still reads from the database; cache write failures do not fail read requests.

The example uses Java records (Java 16+) and assumes `ProductRepository` returns a `ProductView` read from the authoritative source.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

public record ProductView(
        String productId,
        String name,
        long price,
        String currency,
        long version) {
}

public interface ProductRepository {
    ProductView findById(String tenantId, String productId);
}

public final class ProductCacheService {
    private static final Duration TTL = Duration.ofMinutes(5);

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;
    private final ProductRepository repository;

    public ProductCacheService(
            StringRedisTemplate redis,
            ObjectMapper objectMapper,
            ProductRepository repository) {
        this.redis = redis;
        this.objectMapper = objectMapper;
        this.repository = repository;
    }

    public ProductView get(String tenantId, String productId) {
        String key = key(tenantId, productId);

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return objectMapper.readValue(cached, ProductView.class);
                } catch (JsonProcessingException invalidCacheValue) {
                    redis.delete(key);
                }
            }
        } catch (DataAccessException cacheUnavailable) {
            // Log/record metric; continue reading from the authoritative source.
        }

        ProductView product = repository.findById(tenantId, productId);
        if (product == null) {
            return null;
        }

        try {
            String json = objectMapper.writeValueAsString(product);
            redis.opsForValue().set(key, json, TTL);
        } catch (DataAccessException | JsonProcessingException cacheWriteFailed) {
            // Cache is a performance optimization; authoritative data was already read.
        }

        return product;
    }

    // Call after the product update transaction has committed.
    public void invalidateAfterCommit(String tenantId, String productId) {
        redis.delete(key(tenantId, productId));
    }

    private String key(String tenantId, String productId) {
        return "product:v2:" + tenantId + ":" + productId;
    }
}
~~~

This snippet illustrates the following principles:

- Keys include tenant and schema version.
- Cache hits return deserialized data.
- Corrupted cache values are deleted so they can be repopulated next time.
- Cache unavailability or cache write errors do not break authoritative reads.
- TTL bounds cache age.
- Invalidation is a separate operation called after the source transaction commits.

In Spring applications, transaction synchronization or event listeners running in the `AFTER_COMMIT` phase can trigger invalidation. If committing without invalidating is unacceptable, write an invalidation event to a transactional outbox and retry until a consumer processes it.

This example omits distributed locks, version-conditional writes, and negative caching. Add them when load metrics and consistency requirements warrant it.

## 8. Negative caching and non-existent data

If an ID does not exist, basic cache-aside typically caches nothing. When clients repeatedly query the same nonexistent ID, every request hits the database. **Negative caching** stores a "not found" marker for a short TTL.

Distinguish a non-existent value from a cache miss. You can use a sentinel or envelope with a `found=false` field. Negative cache TTLs are usually shorter than normal data TTLs because the record may be created right after the prior check.

Never negatively cache timeouts, authorization errors, or source system errors as if the record did not exist. Doing so can turn a transient outage into a prolonged "not found" response.

When creating a new record, invalidate the corresponding negative cache entry after commit so subsequent requests see the new record.

## 9. Observing and operating external caches

A cache with a high hit ratio is not necessarily healthy if it serves overly stale data or incurs high operational cost. Track effectiveness, freshness, and service health together.

| Metric | Meaning | Signals to investigate |
|---|---|---|
| Cache hit ratio | Fraction of requests served from cache | Consistently low may indicate short TTL, fragmented keys, or low reuse |
| Cache miss rate | Fraction falling back to source | Sudden spikes may mean flush, synchronized expiry, or cache failures |
| Cache latency | Cache read/write duration | Increases may indicate network, connection pool, or cache load issues |
| Eviction rate | Keys evicted due to memory/policy pressure | Rising rate suggests insufficient capacity or poorly tuned TTLs |
| Key age / stale age | Age of returned values | High values may exceed business staleness tolerances |
| Invalidation lag | Time from DB commit to cache invalidation | High lag widens the stale data window |
| Cache error rate | Fraction of failed cache operations | Spikes risk shifting load onto the database |
| Cost per useful hit | Cache cost relative to useful hits | Helps assess whether the cache justifies maintaining |

Never log full cached values, tokens, or personal information. Logs should contain a truncated or hashed key, tenant ID per security policy, operation, outcome, and correlation ID.

### Configuration and security

An external cache is a network service. You should:

- Place the cache within an appropriate network boundary and restrict access to required functions.
- Enable TLS and supported authentication mechanisms.
- Manage secrets via a secret manager or platform identity mechanism.
- Separate read/write permissions if supported by the product.
- Bound value sizes, TTLs, and connection counts.
- Monitor memory usage, evictions, connection counts, and quotas.
- Define backup or persistence policies if needed; do not confuse cache backups with backups of the authoritative source.

In serverless, each function instance may open its own connections to the cache. When concurrency spikes suddenly, connection counts can also climb quickly. Use clients with proper connection management, reuse clients within the execution environment lifecycle when supported by the runtime, and set concurrency limits. Verify the cache service's connection limits before scaling up functions.

## 10. Cache design checklist

- [ ] Authoritative data source and regenerable data have been identified.
- [ ] A measurable reason exists for caching: latency, read load, or source cost.
- [ ] Cache-aside, read-through, write-through, or write-behind has been chosen.
- [ ] TTL reflects the maximum staleness the business tolerates.
- [ ] Invalidation occurs after commit or via an outbox with retries.
- [ ] Cache keys include tenant, locale, role, or output-affecting parameters when needed.
- [ ] Key versioning handles schema changes.
- [ ] Concurrent cache misses, stampedes, and stale writes are handled.
- [ ] Cache outages have timeouts, fallbacks, and load limits protecting the source.
- [ ] Negative caching does not confuse missing data with system failures.
- [ ] Metrics cover hit ratio, latency, evictions, invalidation lag, and error rates.
- [ ] The cache is protected with network policies, TLS, authentication, and secret management.
- [ ] Updates, deletions, expiry, cache outages, race conditions, and per-tenant isolation have been tested.

## Self-check

1. Why can't an in-RAM cache inside a single Java function instance replace an external cache when FaaS scales out to multiple instances?
2. What steps does cache-aside follow on a cache miss?
3. Why should TTL and invalidation be used to complement each other?
4. Describe the race condition where a request reading stale data overwrites the cache after another request has invalidated it.
5. What risk does a transactional outbox mitigate when invalidation is emitted via events?
6. Why must cache keys include tenant or authorization parameters?
7. When does a cache stampede occur and which techniques can mitigate it?
8. During a cache outage, what risk can falling back to the database create?

External caches let multiple Java function instances share frequently read data and offload the authoritative source. To prevent caching from breaking business correctness, engineering teams must define acceptable staleness, pick TTLs, invalidate after commit, scope keys properly, and handle concurrency hazards. When treated as a regenerable copy backed by metrics and clear fallback paths, a cache becomes a controlled performance optimization in serverless architectures.
