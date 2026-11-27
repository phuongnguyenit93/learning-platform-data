# Caching Non-Existent Data to Reduce Repeated Queries in Spring Data Redis

When an application uses Redis to cache database data, we often think only of the **data found** case: read Redis, query the database if absent, then store the result in the cache. However, a key that **does not exist in the data source** can also be queried very frequently. If every request hits the database because Redis stores nothing for a "not found" result, repeated requests create unnecessary load.

**Negative caching** (*caching non-existence results*) solves this by storing a short-lived marker: "the data source was checked and this object was not found." Subsequent lookups for the same key can return the not-found result straight from Redis, avoiding repeated expensive queries.

In Spring Data Redis there are two common ways to implement this:

1. Use **Spring Cache** with `@Cacheable` and a `RedisCacheManager` configured to allow caching `null`/empty values under Spring Cache rules.
2. Use **`StringRedisTemplate` or `RedisTemplate`** to store a marker value (*sentinel*) such as `NOT_FOUND`, separating TTLs for real data and non-existent data.

Negative caching is especially useful for product lookups by ID, profiles, configurations, categories, external service lookups, or paths often hit with invalid IDs. Still, a "not found" cache needs **a short TTL and an invalidation mechanism** to avoid continuing to return 404 after new data is created.

## 1. The problem: repeated "cache misses"

Consider an API:

```http
GET /api/products/p-999
```

The database does not have product `p-999`. With a *cache-aside* pattern that stores only found results, execution proceeds like this:

```text
Request 1:
    GET Redis product:p-999  -> not present
    SELECT ... WHERE id=p-999 -> not present
    return 404

Request 2:
    GET Redis product:p-999  -> not present
    SELECT ... WHERE id=p-999 -> not present
    return 404

Request 3:
    GET Redis product:p-999  -> not present
    SELECT ... WHERE id=p-999 -> not present
    return 404
```

Across all requests, Redis has no entry so the database keeps getting queried. This can happen when:

- Older clients continue requesting a deleted ID.
- Users mistype a product code.
- Crawlers or bots probe many URLs.
- The application repeatedly reads a configuration that has not been created yet.
- A periodic job polls for data that has not arrived yet.
- Clients retry the same "not found" request.

With negative caching, after the first query, the application stores a marker:

```text
product:lookup:p-999 -> NOT_FOUND   (TTL: 30 seconds)
```

Subsequent reads:

```text
GET Redis product:lookup:p-999 -> NOT_FOUND
    |
    +--> return not-found result, do not query database
```

If a non-existent ID is queried hundreds of times per second, short-term caching can significantly reduce database hits. The actual reduction depends on TTL, concurrency while the cache is empty, eviction, and invalidation.

## 2. Distinguishing three states when reading Redis

The most important distinction is that **the cache lacking a key** and **the cache recording a "does not exist" result** are not the same state.

| State in Redis | Meaning | What the application must do |
|---|---|---|
| **No entry** | Never looked up, TTL expired, or key was deleted/evicted | Query the data source |
| **Data entry present** | A found value has been cached | Deserialize and return the value |
| **Non-existence marker present** | Data source was checked recently and did not find it | Return "not found" without re-querying |

Example represented with strings:

```text
product:lookup:p-101 -> VALUE:{"id":"p-101","name":"Office Desk"}
product:lookup:p-999 -> NOT_FOUND
product:lookup:p-888 -> <key does not exist>
```

Decision flow:

```text
                Read cache by productId
                           |
                           v
                    Redis GET(key)
                           |
               +-----------+-----------+
               |                       |
          Entry exists             No entry
               |                       |
       +-------+--------+              v
       |                |         Query database
     VALUE            NOT_FOUND         |
       |                |         +-----+------+
 Return object      Return 404    |            |
                                Found      Not found
                                  |            |
                            Cache VALUE   Cache NOT_FOUND
                            longer TTL     shorter TTL
                                  |            |
                            Return data    Return 404
```

**Do not treat `redis.opsForValue().get(key) == null` as proof that the database record does not exist.** A `null` from Redis here usually only means the cache does not have an entry yet or the entry disappeared. Only when the application itself stored and read back the `NOT_FOUND` marker do you have a negative cache hit.

## 3. How does negative caching differ from caching empty data?

An API can return several kinds of results:

| Data source result | Is it "non-existent"? | How to consider caching |
|---|---|---|
| `Product` found | No | Cache value with an appropriate positive TTL |
| No row for ID | Yes | Cache sentinel or `null` with a short TTL |
| Empty search list `[]` | Not necessarily | Valid query result; cache as normal data if appropriate |
| Product price equals `0` | No | Must not be confused with "no data" |
| Empty string `""` | Not necessarily | Distinguish a valid value from a missing record |
| Database timeout | Unknown | Do not cache as `NOT_FOUND` |
| Database connection error | Unknown | Do not cache as `NOT_FOUND` |
| Access permission denied | Not a global existence conclusion | Avoid caching across wrong user/tenant scopes |
| Record temporarily un-synced | Uncertain | Needs a very short TTL or wait/sync strategy |

The core point is that **negative caching stores a conclusion trustworthy for a short window**, not turning every error into "does not exist".

If the system uses `Optional<Product>`, `Optional.empty()` is a convenient way to represent not found. If an API returns `null`, explicitly specify whether `null` means "database confirmed no row" or "an error occurred." Never overload one result for both situations.

## 4. Why does a non-existence result need a short TTL?

A non-existent record **can be created later**. An overly long negative cache causes the application to return stale results even after the data source has changed.

Example:

```text
10:00:00  GET product:p-999 -> not in DB -> cache NOT_FOUND, TTL 30 seconds
10:00:10  Another request creates product p-999 successfully
10:00:12  GET product:p-999 -> Redis still holds NOT_FOUND
10:00:30  Negative cache TTL expires; next read queries DB and finds product
```

Without invalidation when the product is created, the cache lifetime is a **false-negative window**: the database has the data while the application keeps returning "not found".

Guidelines for choosing TTL:

- **Frequently created data:** use a very short negative TTL and proactively delete the sentinel upon successful write.
- **Data almost never recreated:** a longer TTL may be chosen if reflection lag is acceptable.
- **Arbitrary or bot-generated IDs:** watch negative key count; short TTLs help reclaim entries rarely asked for again.
- **Freshness-sensitive data:** consider skipping negative caching or using stronger version/exactness controls.

Illustrative policy example:

| Cache type | Example TTL | Rationale |
|---|---|---|
| Found product | 10 minutes | Reduce reads for relatively stable data |
| Non-existent product | 30 seconds | Cut repeated queries while bounding stale 404s |
| Uncreated config | 15 seconds | Detect newly added configs relatively quickly |
| Rarely changing external lookup | 1–2 minutes | Balance latency and external API calls |

These numbers **are not defaults of Spring Data Redis**. Choose them based on data creation frequency, consistency requirements, traffic volume, and staleness tolerance. Even a 30-second TTL does not guarantee staleness stays within 30 seconds if clients or other caches hold additional copies.

## 5. Approach 1: Caching `null` with `@Cacheable` and `RedisCacheManager`

The Spring Cache abstraction can cache `null` values via an internal representation (typically involving `NullValue`) when supported by the cache provider and serializer configuration. With Spring Data Redis, default Redis Cache configuration can allow caching `null` unless the application explicitly disables it via `disableCachingNullValues()`.

Business method example:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductStore store;

    public ProductQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "productLookup", key = "#p0")
    public ProductDto findOrNull(String productId) {
        return store.findById(productId).orElse(null);
    }
}
```

`ProductStore` is a component fetching source data and returning `Optional<ProductDto>`. If the database returns `Optional.empty()`, the method returns `null`. When the cache is configured to allow `null`, Spring Cache can store a null marker so subsequent calls **do not re-run the method**.

In a controller, this can be handled as:

```java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductDto> getProduct(@PathVariable String id) {
    ProductDto product = queryService.findOrNull(id);

    if (product == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok(product);
}
```

When invoked through a Spring bean proxy with caching enabled, the first not-found lookup still hits the data source; subsequent reads within the TTL can receive `null` back from cache without calling `ProductStore`.

### 5.1. Configuring `RedisCacheManager` for negative caching with null

Spring Boot / Spring Data Redis example using Jackson 2 and `GenericJackson2JsonRedisSerializer`:

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration lookupConfig =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofSeconds(30))
                    // Keep null caching enabled in configuration.
                    .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(new StringRedisSerializer())
                    )
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                            )
                    )
                    .computePrefixWith(
                        name -> "catalog:v1::" + name + "::"
                    );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(lookupConfig)
                .withInitialCacheConfigurations(
                    Map.of("productLookup", lookupConfig)
                )
                .build();
    }
}
```

In this example, both found and not-found results share a **30-second TTL** because they belong to the same `productLookup` cache. This configuration is simple, though often suboptimal when you want a **10-minute positive cache** and a **30-second negative cache**.

Notes:

1. `@EnableCaching` must be enabled and the method must be called **through a Spring proxy**. Self-invocation via `this.findOrNull(...)` bypasses `@Cacheable`.
2. In `RedisCacheConfiguration`, **do not call `disableCachingNullValues()`** if you use `null` as the negative value.
3. Do not add `unless = "#result == null"` to `@Cacheable`, because that condition means **do not store** null results and disables negative caching.
4. Pick a serializer capable of reading/writing Spring Cache's null marker. With JSON serializers, verify `NullValue` support in your library version and `ObjectMapper` setup.
5. If **disabling null caching** in the manager, `@Cacheable` attempting to write null may fail; either apply `unless` or use an explicit sentinel model.
6. If the method throws `NotFoundException` instead of returning `null`, `@Cacheable` normally does not cache exceptions as values. Convert "not found" into an explicit return value if you want negative caching.

### 5.2. How can `Optional.empty()` participate in Spring Cache?

Spring Cache supports methods returning `Optional<T>` in modern versions. When `Optional.empty()` is returned, Spring Cache can treat it as a **null value for caching**, then reconstruct an `Optional` upon reading the cache per the abstraction contract.

Conceptual example:

```java
@Cacheable(cacheNames = "productLookup", key = "#p0")
public Optional<ProductDto> find(String id) {
    return store.findById(id);
}
```

Because Spring Cache handles `Optional` unwrapping/wrapping itself, do not assume the serializer writes a plain Java `Optional` directly. Understand how your Spring version handles empty values and configure compatible null caching.

One benefit of `Optional` is that callers avoid `null` to represent results. Even so, **TTL still belongs to the cache**, without distinguishing `Optional.empty()` from real values unless dynamic TTL or another storage model is used.

### 5.3. When to choose this approach?

Using `@Cacheable` with null fits when:

- Minimal code changes are desired.
- All lookup results share an acceptable TTL.
- No custom sentinel format is needed.
- Serializer and cache provider `null` behavior are well understood.
- No special atomic update or versioning rules are required.

If negative and positive entries need different TTLs, complex invalidation policies, or separate metrics, using `RedisTemplate` with a sentinel is usually clearer.

## 6. Approach 2: Using a sentinel with `StringRedisTemplate`

A flexible pattern is storing **values that explicitly represent state**:

```text
NOT_FOUND           -> data source confirmed non-existence
VALUE:{...json...}  -> object found
<no key>            -> cache miss, must check source
```

The `VALUE:` prefix prevents valid data from accidentally colliding with the `NOT_FOUND` sentinel. If a cache can hold arbitrary user-supplied strings, a prefixed model or a wrapper object with a `status` field is clearer than an untyped string.

In the example below:

- Positive cache has a **10-minute** TTL.
- Negative cache has a **30-second** TTL.
- Redis keys distinguish **tenant** and **product ID**.
- Value and TTL are written in **the same `SET` operation**.
- Database is the source of truth; Redis is only an acceleration layer.

### 6.1. Defining the DTO and data source

```java
package com.example.catalog;

public record ProductDto(
    String id,
    String name
) {}
```

An interface abstracting the data source:

```java
package com.example.catalog;

import java.util.Optional;

public interface ProductStore {
    Optional<ProductDto> findById(String tenantId, String productId);
}
```

Implementations of `ProductStore` can call a JPA repository, internal REST API, or another query. The crucial point is that `Optional.empty()` is returned **only when the data source confirms not found**; timeouts or DB unavailability must be represented by exceptions or distinct error types.

### 6.2. Lookup service with separate positive/negative TTLs

```java
package com.example.catalog;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.Optional;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupCache {

    private static final Duration FOUND_TTL =
            Duration.ofMinutes(10);

    private static final Duration NOT_FOUND_TTL =
            Duration.ofSeconds(30);

    private static final String NOT_FOUND = "NOT_FOUND";
    private static final String VALUE_PREFIX = "VALUE:";

    private final StringRedisTemplate redis;
    private final ProductStore store;
    private final ObjectMapper objectMapper;

    public ProductLookupCache(
            StringRedisTemplate redis,
            ProductStore store,
            ObjectMapper objectMapper
    ) {
        this.redis = redis;
        this.store = store;
        this.objectMapper = objectMapper;
    }

    public Optional<ProductDto> find(
            String tenantId,
            String productId
    ) {
        String key = cacheKey(tenantId, productId);
        String cached = redis.opsForValue().get(key);

        if (NOT_FOUND.equals(cached)) {
            // Negative cache hit: no need to query database.
            return Optional.empty();
        }

        if (cached != null && cached.startsWith(VALUE_PREFIX)) {
            // Positive cache hit.
            String json = cached.substring(VALUE_PREFIX.length());
            return Optional.of(readProduct(json));
        }

        // Only query the data source when Redis has no entry.
        Optional<ProductDto> fromStore =
                store.findById(tenantId, productId);

        if (fromStore.isPresent()) {
            String json = writeProduct(fromStore.get());

            redis.opsForValue().set(
                key,
                VALUE_PREFIX + json,
                FOUND_TTL
            );
        } else {
            redis.opsForValue().set(
                key,
                NOT_FOUND,
                NOT_FOUND_TTL
            );
        }

        return fromStore;
    }

    public void invalidate(String tenantId, String productId) {
        redis.delete(cacheKey(tenantId, productId));
    }

    private String cacheKey(String tenantId, String productId) {
        return "catalog:product-lookup:v1:"
                + encode(tenantId)
                + ":"
                + encode(productId);
    }

    private String encode(String value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                    value.getBytes(StandardCharsets.UTF_8)
                );
    }

    private String writeProduct(ProductDto product) {
        try {
            return objectMapper.writeValueAsString(product);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize ProductDto",
                ex
            );
        }
    }

    private ProductDto readProduct(String json) {
        try {
            return objectMapper.readValue(json, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot deserialize ProductDto",
                ex
            );
        }
    }
}
```

**Explanation of each branch:**

| Branch | Redis data | Next action |
|---|---|---|
| `cached == NOT_FOUND` | Negative cache hit | Return `Optional.empty()` |
| `cached.startsWith("VALUE:")` | Positive cache hit | Deserialize `ProductDto`, return value |
| `cached == null` | Cache miss | Call `store.findById(...)` |
| DB has product | Positive lookup | Store `VALUE:<json>` with 10-minute TTL |
| DB lacks product | Negative lookup | Store `NOT_FOUND` with 30-second TTL |

Technical points:

- `opsForValue().set(key, value, Duration)` sets both value and TTL in one Redis operation, avoiding the gap of calling `SET` and `EXPIRE` separately.
- Because `StringRedisTemplate` uses a string serializer, cache data can be inspected easily via Redis CLI.
- Representing `NOT_FOUND` is completely distinct from `null` returned on a Redis cache miss.
- `Base64` prevents ambiguous namespaces when tenant IDs or product IDs contain `:` or delimiter characters.
- `v1` is the cache schema version; if the value format changes, increment the version to avoid misreading old entries.
- When a cached string is non-null yet matches neither `NOT_FOUND` nor `VALUE:`, this example treats it as a miss and overwrites it after checking the source. In production you can log a metric, delete the malformed entry, or fail fast depending on data policy.

### 6.3. Why not return Redis `null` as "does not exist"?

If code merely writes:

```java
String value = redis.opsForValue().get(key);

if (value == null) {
    return Optional.empty(); // WRONG: DB was never checked
}
```

then the very first lookup of **a real product that has not been cached yet** is falsely reported as non-existent.

The right pattern is:

```java
if (value == null) {
    // Redis cache miss -> check source of truth.
    return store.findById(tenantId, productId);
}
```

Only after the database returns "not found" may a time-limited negative sentinel be stored.

### 6.4. Should `setIfAbsent` be used for the sentinel?

A variation is:

```java
redis.opsForValue().setIfAbsent(
    key,
    NOT_FOUND,
    NOT_FOUND_TTL
);
```

`SET ... NX EX` writes the sentinel only if the Redis key does not exist at command execution time. It can **reduce the risk of overwriting a positive cache entry** that another request just loaded.

However, `setIfAbsent` **does not fully solve races with newly created data**. If post-commit cache deletion happens and an older request writes the sentinel afterward, the key can still hold `NOT_FOUND` for the rest of its TTL. When strong consistency guarantees are required, design a version/sequence mechanism or clear cache-write ownership.

## 7. Updating and invalidating the negative cache when data is created

Short TTLs reduce discrepancy duration, yet the system should **delete the negative cache after successfully writing new data**.

Suppose:

```text
t0: GET product:p-999 -> not in DB -> Redis stores NOT_FOUND
t1: POST /products creates p-999 successfully
t2: GET product:p-999
```

If the `NOT_FOUND` entry remains at `t2`, the API can return 404 even though the DB now has the product. Therefore, the write path must know the corresponding lookup key and invalidate it.

### 7.1. Simple flow when write has already succeeded

If the creation function guarantees the source of truth committed before returning:

```java
ProductDto created = productWriter.createCommitted(tenantId, request);

productLookupCache.invalidate(tenantId, created.id());
```

The next read sees a cache miss and loads the real data. The name `createCommitted(...)` here expresses the write layer's contract; in real programs verify the exact commit boundary.

### 7.2. When updating inside a database transaction

When data is created inside Spring `@Transactional` with a relational DB, pay attention to **commit timing**. Deleting the cache before the DB commits can let another client reload "not found" from the old snapshot.

A common Spring pattern is publishing an event and handling it after commit:

```java
public record ProductCreated(
    String tenantId,
    String productId
) {}
```

Data-writing service:

```java
@Service
public class ProductWriteService {

    private final ProductJpaStore store;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
            ProductJpaStore store,
            ApplicationEventPublisher events
    ) {
        this.store = store;
        this.events = events;
    }

    @Transactional
    public ProductDto create(String tenantId, CreateProductRequest req) {
        ProductDto created = store.create(tenantId, req);
        events.publishEvent(
            new ProductCreated(tenantId, created.id())
        );
        return created;
    }
}
```

Post-commit invalidation listener:

```java
@Component
public class ProductCacheInvalidator {

    private final ProductLookupCache cache;

    public ProductCacheInvalidator(ProductLookupCache cache) {
        this.cache = cache;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductCreated event) {
        cache.invalidate(event.tenantId(), event.productId());
    }
}
```

In this illustration, `ProductJpaStore` and `CreateProductRequest` are application-defined types requiring corresponding implementations. Spring annotations/types such as `@Service`, `@Component`, `@Transactional`, `ApplicationEventPublisher`, `@TransactionalEventListener`, and `TransactionPhase` must be imported from Spring.

**Important limitation:** `@TransactionalEventListener(AFTER_COMMIT)` runs after commit while the process is alive; it is **not a durable event queue**. If the process stops right after DB commit, invalidation may not run. A transactional outbox and retry worker can be used when more reliable invalidation is required. A short negative TTL limits how long a stale entry lingers if invalidation is missed.

## 8. Race condition: an old sentinel can still be written after invalidation

A subtle race:

```text
Request A                               Request B
---------                               ---------
Redis GET -> MISS
DB SELECT -> not found

                                        Create product p-999
                                        DB COMMIT
                                        Redis DEL negative key

Redis SET NOT_FOUND EX 30
```

Final result: **the DB already has the product, yet Redis holds `NOT_FOUND`** because Request A wrote after Request B invalidated.

This can occur in standard cache-aside even with post-commit deletion. `setIfAbsent` at the sentinel-write step will still see no key and write `NOT_FOUND`.

Mitigations chosen according to discrepancy tolerance:

1. **Accept eventual consistency within a short TTL.** For catalogs with moderate freshness needs, a 10–30 second negative TTL can be a reasonable trade-off.
2. **Write the positive cache from the creation path:** after commit, populate the entry with the new data. This reduces many stale 404 cases, though request ordering still needs consideration.
3. **Use version/generation or fencing tokens for the lookup key:** allow old requests to write only if their read version is still valid; updating versions and entries requires appropriate atomic Redis operations.
4. **Coordinate writes and cache population:** TTL-bounded locks/singleflight or source re-checks on demand, with retry and recovery designed; avoid relying on unverified locks.
5. **Do not negative-cache data with strict read-after-write requirements:** if newly created records must be visible immediately, prefer reading the data source or a stronger consistency mechanism.

Never treat post-commit `DEL` as absolute proof that stale negative caches can never happen. Where false 404s are costly, design the entire read–write–invalidate sequence, not just the TTL.

## 9. Cache penetration, hot misses, and cache stampedes

Negative caching is often discussed alongside two related problems:

### 9.1. Cache penetration

*Cache penetration* happens when requests continuously query keys **present in neither the cache nor the data source**. If every request bypasses the cache and queries the DB, database load rises.

```text
Repeated requests for same non-existent ID
    |
Redis MISS -> Database MISS
Redis MISS -> Database MISS
Redis MISS -> Database MISS
```

Negative caching creates a `NOT_FOUND` entry that turns repeated requests for the same ID into **negative cache hits**.

### 9.2. Hot misses and cache stampedes

Right when the negative cache does not have an entry yet, many concurrent requests can all see a miss:

```text
100 concurrent requests for p-999
             |
             v
100 Redis GETs -> MISS
             |
             v
Multiple DB SELECTs may run before the first request writes NOT_FOUND
```

Negative caching **reduces load after the sentinel is stored**, yet does not automatically ensure only one request queries the DB during the initial miss burst.

Consider complementary solutions:

- In-process *singleflight*: coalesce multiple requests waiting for the same key.
- `@Cacheable(sync = true)` if using Spring Cache and the provider supports the required synchronization scope. Do not assume a single loader across multiple JVMs by default.
- Short-lived distributed locks with clear ownership, timeout, and retry rules when truly needed.
- Proactive warming of negative caches for commonly mistyped IDs verified against the source.
- Rate limiting per client or endpoint if traffic shows signs of abuse.

To prevent **cache breakdown** on ultra-hot keys, combine short waiting windows, TTL jitter, and load-based fallbacks; match complexity to actual risk.

### 9.3. Large volumes of random IDs

A bot may send millions of distinct IDs, each queried only once:

```text
GET /products/random-000001
GET /products/random-000002
GET /products/random-000003
...
```

In this case, negative caching may **save very few DB queries** because keys never repeat, yet still fills Redis memory with huge numbers of sentinels.

Therefore combine:

- ID format validation before hitting the database.
- Request/tenant or IP rate limiting per operational policy.
- Short TTLs and cache capacity limits.
- Tracking unique negative key counts to detect abnormal cardinality growth.
- Where appropriate, membership structures such as Bloom filters **with proper understanding of false positives and update procedures for new data**.

A Bloom filter is not a drop-in replacement for every negative cache. If used to conclude "definitely does not exist," newly created data must be added to the filter properly; otherwise the system can return false negatives. Moreover, filters are probabilistic, unlike a sentinel recording a temporary conclusion for a specific ID.

## 10. Key design to avoid leaks across tenants and users

If products exist only within a specific tenant or permission scope, cache keys must reflect **the exact data scope**:

```text
WRONG if data is tenant-scoped:
    product:lookup:p-42

RIGHT for tenant-isolated data:
    product:lookup:<tenant-id>:p-42
```

If `p-42` does not exist in tenant A yet exists in tenant B, a shared negative entry could cause B to receive a false 404.

Similarly, a "not found" outcome can happen because:

- No record actually exists in the system.
- The record does not belong to the current tenant.
- The user lacks read permission.
- The record is hidden by schedule, status, or policy.
- The API intentionally returns 404 instead of 403 to avoid leaking resource existence.

**Do not cache an authorization-dependent conclusion as a global conclusion.** Applying negative caching before authorization checks can cause permission bugs or timing side-channel leaks.

Principles:

1. Define namespaces by tenant, resource type, and schema version.
2. Include only inputs that affect the result in the cache key.
3. Never use negative caches to skip mandatory authorization checks.
4. Separate "does not exist" from "forbidden" if business logic requires it.
5. Avoid putting tokens, sensitive details, or raw PII into Redis key names that may appear in logs/monitoring.

When IDs contain special characters, encode them into safe, unambiguous keys—for instance URL-safe Base64 or deterministic hashing—while balancing key count and observability.

## 11. What other consistency risks can negative caching introduce?

### 11.1. Deleting and recreating the same ID

Suppose a product is deleted and the application records `NOT_FOUND`; a few seconds later an operator restores the product with the same ID. Without cache invalidation, the API may keep returning 404.

Ideally, creation, restoration, import, and sync paths all know that **data reappearing** must delete negative entries.

### 11.2. Lagging replica data sources

A service reads from a read replica. After writing to the primary, the replica lags behind:

```text
Write primary: create p-42 succeeds
Read replica: does not see p-42 yet
Cache: writes NOT_FOUND
```

This is not stable "non-existence" but **replication lag**. With read replicas, consider consistency modes, lag duration, and negative TTL; sometimes primary reads are required for read-after-write flows.

### 11.3. Network errors mistaken for not-found

Dangerous code example:

```java
try {
    return database.findById(id);
} catch (Exception ignored) {
    return Optional.empty();
}
```

If the database times out, the service writes `NOT_FOUND`, causing subsequent requests to receive 404 from cache even though the record exists.

Clearly separate valid `Optional.empty()` from system failures:

```java
Optional<ProductDto> result = database.findById(id);
// If database fails, let the exception propagate to error handling.
// Only cache NOT_FOUND when result is genuinely empty.
```

### 11.4. Time-dependent lookup results

For instance, a configuration whose effective date has not arrived or a scheduled article. Currently the API may return "not found," yet seconds later the outcome changes automatically without a normal creation action.

In this case, the negative TTL should not cross the scheduled change time; or disable negative caching if freshness requirements are strict.

### 11.5. Eviction reduces effectiveness

Redis can remove sentinel keys before TTL under memory eviction policies. Requests will then hit the database sooner than expected. Negative caching is a performance optimization, not a hard guarantee on database query counts.

## 12. TTL jitter and spreading expiration times

If many requests hit non-existent IDs simultaneously, many sentinels may be written together and expire together.

One strategy is adding small *jitter* to the TTL:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

int extraSeconds = ThreadLocalRandom.current()
        .nextInt(0, 11); // from 0 to 10 seconds

Duration negativeTtl =
        Duration.ofSeconds(20 + extraSeconds);

redis.opsForValue().set(key, NOT_FOUND, negativeTtl);
```

Here TTL varies between 20 and 30 seconds. Jitter spreads out expiration waves, yet:

- Cannot replace invalidation.
- Does not fully stop cache stampedes on an ultra-hot key.
- Must choose a jitter range within freshness limits.
- An extremely frequently queried key can still suffer concurrent misses upon expiration.

For predictable test behavior, inject the TTL or random source into the configuration component so tests can control it deterministically.

## 13. Limiting memory consumed by sentinels

Every negative key consumes RAM for key, value, metadata, and TTL. Creating too many entries that are never re-accessed lets negative caching compete with positive caching for memory.

For example, when Redis holds both product caches and other important keys:

```text
catalog:positive:*    -> rebuildable data, many repeat requests
catalog:negative:*    -> hundreds of thousands of one-off IDs
```

If negative key count surges, Redis may start evicting useful positive entries or reject writes depending on `maxmemory-policy`.

Control measures:

- Use **short negative TTLs**.
- Track `used_memory`, `evicted_keys`, key counts per prefix, and negative entry reuse rate.
- Limit key lengths to prevent keys containing huge arbitrary payloads.
- Validate ID formats and block nonsensical requests before Redis/DB.
- Separate cache workloads across instances if negative traffic is large enough to affect critical data.
- Consider skipping caching for IDs whose repeat probability is near zero if a reliable signal exists.

Do not run `KEYS catalog:negative:*` routinely in production to count keys: it can scan large keyspaces and hurt performance. Prefer actively collected metrics or bounded `SCAN` during investigations.

## 14. Observing negative caching effectiveness

A system should verify whether negative caching truly saves DB load or merely wastes RAM.

Useful metrics:

| Metric | Meaning |
|---|---|
| `lookup.cache.positive_hit` | Data present in cache and returned successfully |
| `lookup.cache.negative_hit` | Sentinel present, DB call avoided |
| `lookup.cache.miss` | Redis lacked key and source lookup was required |
| `lookup.source.found` | Database found record after cache miss |
| `lookup.source.not_found` | Database confirmed no record |
| `lookup.cache.negative_write` | Count of `NOT_FOUND` entries written |
| `lookup.cache.invalidate` | Invalidations triggered when data changed |
| `lookup.cache.error` | Cache connection or serialization errors |
| `lookup.source.latency` | Data source query latency |
| `lookup.cache.keys_estimate` | Estimated cardinality and negative cache footprint |

A simple ratio to evaluate effectiveness among "not found" requests:

```text
negative_hit_ratio =
    negative_cache_hits /
    (negative_cache_hits + source_not_found_queries)
```

A high ratio shows many not-found requests are served straight from Redis; however, evaluate it alongside **stale 404 rate**, distinct key count, errors, and latency. Never inflate hit ratio by setting overly long TTLs if newly created data takes too long to appear.

### 14.1. Helpful Redis CLI commands for observation

With the sample key:

```redis
GET catalog:product-lookup:v1:<tenant>:<id>
TTL catalog:product-lookup:v1:<tenant>:<id>
PTTL catalog:product-lookup:v1:<tenant>:<id>
INFO stats
INFO memory
```

`TTL` can return:

| Value | Meaning |
|---|---|
| Non-negative number | Remaining seconds |
| `-1` | Key exists without TTL |
| `-2` | Key does not exist |

In the `ProductLookupCache` example, `<tenant>` and `<id>` are **URL-safe Base64 encoded parts**, not raw strings. When inspecting via CLI, use the exact key produced by the application.

`TTL = -2` only means Redis no longer has the key; it could be never cached, expired, explicitly evicted, or evicted under memory pressure. It does not indicate whether the database has a record.

Key counts by prefix can be inspected in test environments using `SCAN`:

```redis
SCAN 0 MATCH catalog:product-lookup:v1:* COUNT 100
```

`SCAN` uses a cursor: to traverse fully, iterate using the returned cursor until `0`; `COUNT` is a per-iteration work hint, not a promise to return exactly 100 keys. Never treat scan output as a consistent snapshot while keys change concurrently.

## 15. Handling Redis unavailable: do not turn cache errors into 404

If Redis times out, this line:

```java
String cached = redis.opsForValue().get(key);
```

can throw an exception. When cache is solely a performance optimization, you can choose a **fail-open** policy: attempt to read from the database when Redis fails.

However, separate two scenarios:

1. **Redis error**: cache value unknown; check data source if allowed.
2. **Redis holds `NOT_FOUND` sentinel**: negative hit recorded; can return not found within TTL without hitting the source.

Never write:

```java
catch (Exception ex) {
    return Optional.empty(); // WRONG: Redis failure does not prove DB lacks the record.
}
```

A clean design separates cache reads into three states `HIT_VALUE`, `HIT_NOT_FOUND`, `MISS`, plus `CACHE_ERROR` handled separately. When cache fails while the data source is healthy, the application can bypass cache and keep serving requests under a fail-open policy.

Monitor cache errors to avoid Redis outages flooding all traffic into the DB without rate limits.

## 16. Negative caching with HTTP APIs: which status codes should be cached?

Negative caching can happen in the application's Redis layer or at HTTP caches/CDNs, yet **the two layers have different rules**.

| API case | Consideration |
|---|---|
| `404 Not Found` confirmed non-existent by source | Can negative-cache with short TTL if stable over TTL |
| `410 Gone` for permanently deleted resources | Longer TTL may be considered if non-restoration is guaranteed |
| `403 Forbidden` | Authorization result; must respect caller identity/permissions, no shared sentinel |
| `401 Unauthorized` | Do not convert into a data negative cache |
| `429 Too Many Requests` | Rate limit, does not prove missing resource |
| `500` or `503` | System error, do not cache as not-found |
| Source timeout | Existence unknown, do not negative-cache |
| Empty list `200 []` | Can cache as a valid result with appropriate TTL |

An endpoint may **intentionally return 404 for unauthorized resources**. Therefore, never take any backend HTTP 404 and treat it as "ID globally non-existent". Review resource-hiding policies and cache key scoping.

## 17. Custom sentinel model or Spring Cache null caching?

| Criterion | `@Cacheable` + null | `StringRedisTemplate` + sentinel |
|---|---|---|
| Code volume | Concise, less boilerplate | More code for keys/serializers |
| Integration style | Spring Cache method interception | Explicit cache-aside in service |
| "Not found" representation | Null marker managed by cache abstraction | Sentinel like `NOT_FOUND` |
| Different positive/negative TTLs | Requires dynamic TTL or separate caches | Easy to pass distinct `Duration` per branch |
| Cache miss handling | Spring Cache invokes method on miss | Code calls source when Redis `GET` misses |
| Key control | SpEL/key generator + manager prefix | Custom key namespace design |
| Avoiding real-null collisions | Must understand null/Optional method semantics | Sentinel separates states explicitly |
| Separate negative hit metrics | Requires instrumenting cache/provider layer | Can count sentinel branch directly |
| Invalidation | `@CacheEvict`, `Cache.evict` | `redis.delete(key)` |
| Serializer | Per `RedisCacheConfiguration` | Per template, e.g., explicit String/JSON |
| Best fit | Simple lookups, shared TTL | Distinct TTLs, fine-grained invalidation and metrics |

**Do not pick an approach solely for fewer lines of code.** If you only need to cut load for missing lookups, `@Cacheable` with null may suffice. If the system needs a short not-found TTL, a long found TTL, and explicit sentinel invalidation on writes, the sentinel model is clearer.

Another option in Spring Data Redis versions supporting value-aware TTL functions is configuring dynamic TTL at the cache provider. That requires matching the actual API and cached object types—especially how Spring Cache represents `null` and `Optional.empty()`—to avoid assigning the wrong TTL.

## 18. Hands-on exercise: observing negative caching in action

Assume `ProductLookupCache` from section 6 with a `ProductStore` returning `Optional.empty()` for ID `p-999`.

**Step 1 — Call lookup the first time.**

```java
Optional<ProductDto> first =
        productLookupCache.find("tenant-A", "p-999");
```

Result: `first.isEmpty() == true`. Redis has no entry so the database is queried once, then the application writes `NOT_FOUND` with a 30-second TTL.

**Step 2 — Call the same ID again within TTL.**

```java
Optional<ProductDto> second =
        productLookupCache.find("tenant-A", "p-999");
```

Result is still empty, but this time Redis returns the sentinel. The database is not called again while the entry remains and Redis operates normally.

**Step 3 — Call an existing ID.**

```java
Optional<ProductDto> found =
        productLookupCache.find("tenant-A", "p-101");
```

The first call queries the database and caches `VALUE:{...}` with a 10-minute TTL. Subsequent calls read a positive cache hit.

**Step 4 — Create `p-999` in the data source.**

After commit, invoke:

```java
productLookupCache.invalidate("tenant-A", "p-999");
```

The next read no longer sees the old sentinel and is allowed to load the newly created product.

**Step 5 — Observe the effect of skipping invalidation.**

If the old sentinel remains, reads right after creation may keep returning not found until the negative TTL expires. This is why TTL and invalidation must be designed together.

**Step 6 — Simulate concurrent requests.**

Send multiple requests for the same ID not yet in Redis. Observe how many times the database is called before the first request writes the sentinel. If multiple concurrent queries occur, consider appropriate singleflight/synchronization rather than assuming negative caching eliminates cache stampedes by itself.

## 19. Common design mistakes

**Caching only real data.** For a non-existent ID queried continuously, every request still hits the database. Negative caching introduces a dedicated state to block repeated queries.

**Using Redis `null` to conclude the database lacks data.** Redis null is only a cache miss. Query the source at least once or read a sentinel stored by an earlier lookup.

**Using `unless = "#result == null"` while expecting Spring Cache to store not-found.** That condition suppresses caching null. For negative caching with `@Cacheable`, enable null caching with a compatible serializer.

**Enabling `disableCachingNullValues()` while the method returns null for not-found.** Incompatible with null-caching strategies. Change configuration or use an explicit wrapper/sentinel.

**Giving sentinels no TTL.** Newly created products can keep returning 404 indefinitely unless invalidation succeeds 100% of the time.

**Using the same very long TTL for positive and negative entries.** Non-existence results carry a different state-change risk profile than existing data; consider separate TTLs.

**Caching DB timeouts, network errors, or 403s as `NOT_FOUND`.** Turns transient failures or permission denials into false answers for many subsequent requests.

**Deleting cache only on data deletion, forgetting deletion on creation or restoration.** Negative caches also require invalidation when data starts existing.

**Assuming post-commit deletion eliminates all races.** An in-flight request can query the DB before commit and write a sentinel after the delete command. Use short TTLs or versioning when freshness is strict.

**Omitting tenant/user scope from the key.** Can return false negatives or wrong data across different callers.

**Caching all random IDs.** If requests do not repeat, sentinels waste RAM; validation, rate limiting, and cardinality caps are required.

**Assuming negative caching prevents stampedes by itself.** While the entry is missing, many requests can still query the DB together.

**Retrying cache writes without considering failures and ordering.** Writing a sentinel after another request populated a positive cache entry creates a stale negative. Define write ownership and synchronization rules.

## 20. Designing by required consistency level

They can be categorized as follows:

| Requirement level | Example | Recommended strategy |
|---|---|---|
| Tolerates tens of seconds of staleness | Public product lookup | Short negative TTL, delete sentinel on create |
| Faster detection of new records needed | Operational config | Very short negative TTL, active invalidation from change flow |
| Records created across multiple services | Distributed catalog | Event/outbox invalidation, TTL as fallback |
| Read-your-writes required immediately | Resource ownership or critical flows | Read consistent source, versioning, or skip negative cache on critical paths |
| Large-scale random ID scanning | Public API hit by bots | Validation, rate limiting, memory caps; negative cache only for repeating keys |
| "Not found" depends on permissions | Private resources | Scope keys by tenant/user and keep authorization checks, or avoid shared cache |

Not every application needs complex locking or versioning. For rebuildable caches, short TTLs plus invalidation may suffice. When "returning a false 404 after creation" causes severe harm, solve consistency in the system design rather than merely tweaking TTL.

## 21. Safe adoption checklist for negative caching

When adding negative caching to a lookup method:

1. **Verify the "does not exist" signal is trustworthy.** Cache only after data source confirmation; never lump system or authorization errors into the same state.
2. **Design full-context cache keys.** Include tenant/resource/version if those factors affect outcomes.
3. **Distinguish three states.** Cache miss, positive hit, and negative hit must have distinct representations.
4. **Pick negative TTL based on creation likelihood.** Start short, measure load and reflection lag.
5. **Design invalidation on all relevant write paths.** Create, restore, import, visibility change, or tenant transfer can turn not-found into found.
6. **Check load-vs-invalidation races.** When stronger than eventual consistency is required, use version/sequence or an appropriate read source.
7. **Bound invalid-ID traffic.** Negative caching does not effectively mitigate bots sending endless unique IDs.
8. **Measure negative hits separately.** Track saved database queries, memory, stale 404s, and cache errors.
9. **Prepare a fallback path on Redis errors.** Never return 404 just because the cache server failed to respond.
10. **Respect cache semantics.** Keys can expire or be evicted early; requests must handle falling back to the data source.

## 22. Conclusion

**Caching non-existent data** is part of a cache-aside strategy that prevents repeated queries for the same ID absent from the data source. Rather than letting Redis report cache misses and hitting the database every time, the application stores a **short-lived negative entry** so subsequent lookups return quickly from cache.

In Spring Data Redis:

- With **Spring Cache**, `null`/`Optional.empty()` can be cached when `RedisCacheManager` is configured to support it; do not use `unless="#result == null"` if null results should be stored.
- With **`StringRedisTemplate`**, a `NOT_FOUND` sentinel cleanly separates negative hits from cache misses and allows different TTLs for positive and negative entries.
- **Short TTLs and post-creation invalidation** are two essential parts of avoiding stale 404s for too long.
- **Race conditions, replica lag, authorization, and system failures** can invalidate a "not found" conclusion; handle them per business consistency needs.
- **Cache penetration** caused by repeating lookups of the same ID is where negative caching shines. For mass random IDs or initial cache stampedes, combine validation, rate limiting, and request coordination.

Proper design aims not just for higher hit ratios, but also ensures **non-existence results are cached within the right scope, for the right duration, and invalidated when truth changes**.
