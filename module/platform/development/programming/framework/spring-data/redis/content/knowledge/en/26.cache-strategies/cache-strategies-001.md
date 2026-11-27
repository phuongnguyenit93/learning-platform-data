# Cache-Aside and the Read Data Lifecycle Through Cache

## 1. The problem: where does the data live and why is a cache needed?

Suppose a Spring Boot service provides an API to read product information. The authoritative product data resides in a relational database; Redis is used to store frequently read results in order to reduce the number of database queries and shorten response times.

A read without using a cache:

```text
Client ── GET /products/42 ──> Spring Boot ── SELECT ──> Database
Client <────── ProductView ───── Spring Boot <──── row ───── Database
```

If thousands of requests continuously ask for the same product, the database has to process many identical queries. With **cache-aside**, the application proactively checks Redis first, and only reads from the database when the cache does not have matching data.

```text
                             ┌──────────────────┐
Client ──> Spring Boot ─────> │ Redis cache      │
                 │           └──────────────────┘
                 │                   │
                 │               Hit / Miss
                 │                   │
                 ├──── Hit ──────────┘
                 │       return result from cache
                 │
                 └──── Miss ────────> Database
                                          │
                                      source data
                                          │
                               write to Redis with TTL
                                          │
                               return result to client
```

**Cache-aside** is also called *lazy loading cache*: only when an object needs to be read and is not yet in the cache does the application fetch the source data and put it into the cache. Redis acts as a **read-serving copy**; the database remains the **authoritative data source** (*source of truth*).

This lesson belongs to the **Cache Strategies** chapter in Spring Data Redis. The focus is the lifecycle of a read: **cache hit → cache miss → read source → write cache → return data**, along with situations that alter the lifecycle such as TTL, data updates, concurrent contention, and Redis failures.

## 2. The two branches of the read path: cache hit and cache miss

### 2.1. Cache hit: Redis already has the data

Suppose Redis has the key:

```text
product:detail:v1:42
```

with JSON representing the product information. The application reads the key and receives the stored data:

```text
1. Client calls GET /products/42.
2. The application builds the key "product:detail:v1:42".
3. The application calls Redis GET.
4. Redis returns the existing data.
5. The application deserializes and returns the result.
6. No database query is needed for that read.
```

Diagram:

```text
Client        ProductService           Redis                 Database
  |                  |                    |                      |
  | get(42)          |                    |                      |
  |----------------->|                    |                      |
  |                  | GET product:42     |                      |
  |                  |------------------->|                      |
  |                  | <--- ProductView --|                      |
  | <--- ProductView |                    |                      |
  |                  |                    |                      |
  |                  |     Database is not called                |
```

The benefit of a hit depends on Redis read latency, value size, deserialization cost, and the proximity of Redis to the application. Caching is not always faster than every other read path; effectiveness must be measured on real workloads.

### 2.2. Cache miss: the key is absent or expired

Redis returns `null` when a key does not exist (for example using `opsForValue().get(key)` under typical configuration). The application reads the source data, then writes it to the cache:

```text
Client        ProductService           Redis                Database
  |                  |                    |                     |
  | get(42)          |                    |                     |
  |----------------->|                    |                     |
  |                  | GET product:42     |                     |
  |                  |------------------->|                     |
  |                  | <--- null ---------|                     |
  |                  |                    |                     |
  |                  | SELECT product 42                        |
  |                  |----------------------------------------->|
  |                  | <----------------------- ProductView ----|
  |                  |                    |                     |
  |                  | SET product:42 + TTL                     |
  |                  |------------------->|                     |
  |                  | <--- OK -----------|                     |
  | <--- ProductView |                    |                     |
```

This is a **cold** read for that key. Subsequent reads, if the key still exists and has not been deleted/replaced, can become cache hits.

**Note:** `GET` returning `null` alone is not enough to conclude that the product does not exist. It only tells you that **a copy was not found in Redis**. To know whether the product exists, the application must check the data source.

### 2.3. Cache-aside does not happen automatically just by having RedisTemplate

A snippet using `RedisTemplate`:

```java
ProductView cached = redis.opsForValue().get(key);
```

only reads Redis. RedisTemplate does not automatically execute an SQL query on a miss, does not automatically write the result into Redis, and does not automatically decide the TTL. **The application must explicitly implement the cache-aside flow**, or use an appropriate cache abstraction to manage those behaviors.

## 3. Full lifecycle of a cache key

A cache key goes through multiple states:

```text
               Does not exist yet
                    │
             Data read request
                    │
             GET from Redis: miss
                    │
             Read data source
                    │
             SET into Redis + TTL
                    │
                    v
              Cache has data
                    │
        ┌───────────┼───────────────┐
        │           │               │
   Read request  TTL reaches 0  Source data
        │           │           is updated
        v           v               │
       Hit       Expired         DEL/invalidate
        │           │               │
        │           └───────┬───────┘
        │                   │
        └── Continue reading v
                     No longer cached
                            │
                       Next read
                            │
                       Miss and reload
```

Important states:

| State | System behavior |
|---|---|
| **Not cached yet** | Read the database and put the data into Redis |
| **Valid cache present** | Return data from Redis |
| **Key TTL expired** | Redis treats the key as expired; the next read misses |
| **Key explicitly deleted** | The next read misses and loads fresh data |
| **Source updated but cache not invalidated** | Cache may continue returning stale data |
| **Redis unavailable** | Can fall back to reading the database if the application designs a fallback path |
| **Multiple requests miss simultaneously** | Multiple requests may concurrently read the database and write the cache |

TTL helps bound the expected maximum age of a copy; **TTL does not guarantee that data in the cache is always the newest at every moment**.

## 4. Designing keys and values before writing code

### 4.1. Keys must be meaningful, stable, and properly scoped

A key can be named:

```text
product:detail:v1:42
```

Where:

- `product`: business domain group.
- `detail`: cached data kind, e.g., detail information.
- `v1`: version of the data structure in the cache.
- `42`: product identifier.

If data differs by tenant, language, or access permissions, the key must reflect those dimensions:

```text
tenant:acme:product:detail:v1:42:lang:vi
tenant:other:product:detail:v1:42:lang:vi
tenant:acme:product:detail:v1:42:lang:en
```

If tenant is omitted from the key in a multi-tenant system, the application can return one tenant's data to another tenant. For personalized data, a shared cache key must never be used for results that vary by user.

Do not put secrets such as tokens or passwords directly into key names; key names may appear in administration tools and logs.

### 4.2. Choosing an appropriate cache value

If an API only needs name, price, and display status, the cache should store a stable **read model**, rather than serializing an entire JPA entity containing lazy-loaded relationships and internal fields.

Java example:

```java
package com.example.cache;

import java.math.BigDecimal;

public record ProductView(
        long id,
        String name,
        BigDecimal price,
        long version
) {
}
```

A data version (`version`) is not mandatory in every cache, but is useful if stale values need to be detected during concurrent updates. It differs from `v1` in the key name: `v1` represents the **schema version**, whereas `version` inside the object can represent the **content version**.

### 4.3. TTL is a business policy

For example, a product that rarely changes can be cached for 5 minutes:

```redis
SET product:detail:v1:42 "{\"id\":42,\"name\":\"Office Desk\"}" EX 300
```

When reading:

```redis
GET product:detail:v1:42
TTL product:detail:v1:42
```

The `TTL` result can be:

| Value | Meaning |
|---|---|
| Positive integer | Remaining seconds before the key expires |
| `-1` | Key exists but has no TTL |
| `-2` | Key does not exist |

If cache-aside is used for mutable data, there should be a clear TTL policy to limit how long stale data can continue appearing if an invalidation is missed.

## 5. Implementing cache-aside with Spring Data Redis

The example below uses Spring Boot, Spring Data Redis, and a source data access component. To make it clear **who decides hit, miss, and cache writes**, the code uses `RedisTemplate` instead of the `@Cacheable` annotation.

### 5.1. Configuring RedisTemplate to use JSON

With Spring Data Redis 3.x and a suitable Jackson setup, a typed template can be created:

```java
package com.example.cache;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductCacheConfiguration {

    @Bean("productCacheRedisTemplate")
    public RedisTemplate<String, ProductView> productCacheRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductView> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(ProductView.class)
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Here:

- `keySerializer` determines how key names are represented.
- `valueSerializer` converts `ProductView` to JSON and reads JSON back into a Java object.
- `opsForValue()` uses **Redis String** as the physical data type.
- The template does not define source loading rules or TTL itself.

The example uses fields with simple types only to keep the focus on the cache lifecycle. For special Java types, nested structures, or complex schema requirements, you must configure the ObjectMapper/serializer to match your library version.

### 5.2. Separating the data source from the cache mechanism

Suppose the application has a database reader component returning `ProductView`:

```java
package com.example.cache;

import java.util.Optional;

public interface ProductSource {

    Optional<ProductView> findById(long productId);
}
```

An implementation class can use Spring Data JPA, JDBC, or another service API. In this lesson, `ProductSource` represents the **authoritative source**. It has no knowledge of Redis.

### 5.3. Read service following the exact cache-aside lifecycle

```java
package com.example.cache;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private static final String KEY_PREFIX = "product:detail:v1:";

    private final RedisTemplate<String, ProductView> redis;
    private final ProductSource source;

    public ProductQueryService(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductView> redis,
            ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public ProductView findById(long productId) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId must be positive"
            );
        }

        String key = KEY_PREFIX + productId;

        // 1. Read from cache first.
        ProductView cached = redis.opsForValue().get(key);

        if (cached != null) {
            // 2. Cache hit: no need to read the database.
            return cached;
        }

        // 3. Cache miss: query the authoritative source.
        ProductView loaded = source.findById(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));

        // 4. Set TTL according to policy. Jitter helps reduce
        //    the chance of many keys expiring simultaneously.
        long ttlSeconds = 300L
                + ThreadLocalRandom.current().nextLong(0, 61);

        redis.opsForValue().set(
                key,
                loaded,
                Duration.ofSeconds(ttlSeconds)
        );

        // 5. Return the data freshly read from the source.
        return loaded;
    }
}
```

A simple exception for the not-found case:

```java
package com.example.cache;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product not found " + id);
    }
}
```

**TTL jitter** is a small, controlled random offset. In the example, the TTL falls between 300 and 360 seconds. If a group of keys is loaded simultaneously, they are less likely to expire at the exact same moment than if all received exactly 300 seconds.

### 5.4. How does a single read request unfold?

If the key `product:detail:v1:42` is cached:

```text
ProductQueryService.findById(42)
    └── redis GET -> ProductView
        └── return ProductView
```

If Redis does not have the key:

```text
ProductQueryService.findById(42)
    ├── redis GET -> null
    ├── source.findById(42) -> ProductView
    ├── redis SET ProductView EX 300...360
    └── return ProductView
```

If the data source does not find the product, this example throws `ProductNotFoundException` and **does not cache the non-existence result**. This choice keeps the example simple; a system receiving heavy requests for non-existent IDs can consider **negative caching** in a later section.

## 6. TTL does not replace cache invalidation on updates

Cache-aside has two related flows:

- **Read:** `GET cache` → on miss, read source → `SET cache`.
- **Write:** update authoritative source → invalidate copy in cache.

Suppose product 42 currently has price 100 and Redis also stores 100. An administrator changes the price to 120 in the database. If nothing is done to Redis, subsequent requests may continue receiving 100 until the cache TTL expires.

### 6.1. Invalidation after a successful write

With the common **invalidate on write** strategy:

```text
Application               Database                   Redis
    |                         |                        |
    | UPDATE price = 120      |                        |
    |------------------------>|                        |
    | <----- COMMIT OK -------|                        |
    |                         |                        |
    | DEL product:detail:v1:42                         |
    |------------------------------------------------->|
    | <------------------------------ deleted ---------|
    |                         |                        |
    | New read request: cache miss                     |
    |------------------------------ GET -------------->|
    | <------------------------------ null ------------|
    | SELECT product 42       |                        |
    |------------------------>|                        |
    | <--------- price=120 ---|                        |
    | SET cache price=120                              |
    |------------------------------------------------->|
```

At the code level:

```java
public void evictProduct(long productId) {
    redis.delete("product:detail:v1:" + productId);
}
```

**Order matters greatly:** first write the source data successfully, then delete the old cached copy. If you delete the cache and then update the database, and the update fails, interleaved requests may reload the old data; that cached copy will then remain.

### 6.2. The issue with database transactions

If a service updates a product inside a `@Transactional` method, a Redis command called in the middle of the method **does not automatically participate in the SQL transaction**. Calling `redis.delete(...)` before the SQL transaction commits can cause another request to miss and reload the un-updated database version.

You can publish an application event inside the transaction and handle invalidation with a listener that runs **after the transaction commits**:

```java
public record ProductChanged(long productId) {
}
```

Example service writing source data:

```java
@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher publisher;

    public ProductCommandService(
            ProductJpaRepository products,
            ApplicationEventPublisher publisher) {
        this.products = products;
        this.publisher = publisher;
    }

    @Transactional
    public void changePrice(long id, BigDecimal newPrice) {
        ProductEntity entity = products.findById(id)
                .orElseThrow();

        entity.changePrice(newPrice);

        // Event is published inside the transaction.
        publisher.publishEvent(new ProductChanged(id));
    }
}
```

And a listener:

```java
@Component
public class ProductCacheInvalidator {

    private final RedisTemplate<String, ProductView> redis;

    public ProductCacheInvalidator(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductView> redis) {
        this.redis = redis;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onProductChanged(ProductChanged event) {
        redis.delete("product:detail:v1:" + event.productId());
    }
}
```

Corresponding imports from Spring Framework and the project's JPA classes are needed. These snippets illustrate **the point at which post-commit invalidation runs**.

**Important limitation:** `@TransactionalEventListener(AFTER_COMMIT)` does not turn an event into a durable message. If the process stops right after commit or Redis is unavailable, the cache deletion may not execute. For critical requirements, a durable retry mechanism such as an outbox/queue is needed, combined with TTL and error observability.

### 6.3. Why delete the cache instead of overwriting immediately with the new value?

When updating source data, the application can:

1. **Delete cache:** remove the old entry; the next read reloads from the source.
2. **Update cache:** immediately write the newly updated entry.

Deleting is usually simpler because you do not need to ensure every update code path builds the exact same cache representation. Writing the cache immediately can reduce post-update misses, but can easily leave stale state if there are concurrent updates or uncommitted transactions.

There is no rule that "delete is always better than update" for every system. The choice depends on write frequency, read-model complexity, and consistency requirements.

## 7. Concurrent races in the cache-aside lifecycle

### 7.1. Cache stampede: many requests miss at once

Suppose a very popular product's cache key has just expired. Immediately 200 read requests arrive for that product:

```text
              cache key just expired
                       |
        ┌──────────────┼──────────────┐
        |              |              |
     Request A      Request B      Request C ... 200
        |              |              |
       MISS           MISS           MISS
        |              |              |
        └──────────────┼──────────────┘
                       |
              Many SELECTs for same ID
                       |
              Database may overload
```

This is a **cache stampede** or **thundering herd**: the cache reduces queries on hits, but at the moment many requests miss together, its database-protective effect can vanish.

Risk mitigation approaches:

- TTL with jitter to avoid many keys expiring simultaneously.
- **Single-flight** within a single instance: coalesce miss requests for the same key into one load.
- Time-bounded distributed lock when multiple instances load a hot key simultaneously.
- Proactively refresh before expiration (*refresh ahead*) or serve bounded stale data (*stale-while-revalidate*).
- Limit concurrent loads and apply backpressure at the source layer.
- Use longer TTLs for infrequently changing data, combined with invalidation on updates.

**Jitter does not completely prevent a stampede on a single hot key**: all requests waiting on that exact same key can still miss simultaneously. It mainly spreads out the expiration times of **many different keys**.

### 7.2. Cache penetration: repeatedly querying non-existent IDs

With the example code above, a request for product 999999 always does:

```text
Redis MISS -> Database NOT FOUND -> nothing written to cache
```

If many requests send the same non-existent ID, the database still has to process them repeatedly.

One option is **negative caching**: briefly store a "not found" marker, such as a result type with an explicit status:

```text
product:detail:missing:v1:999999 -> "NOT_FOUND" (TTL 15 seconds)
```

When implementing this, distinguish that marker from a valid `ProductView` and from a `null` result caused by a missing Redis key. Do not store a dummy value and accidentally return it as a real product.

The TTL of a negative cache should usually be **short**, because an ID that does not exist today might be created right afterward. When creating a new object with that ID, the application must also invalidate the "not found" cache if one is used.

### 7.3. Race between cache population and source data update

A subtler case:

```text
T0: Redis does not have product:42.
T1: Request A MISSES, starts database SELECT (old price = 100).
T2: Request B updates database to new price = 120 and COMMITS.
T3: Request B DEL product:42; cache is still empty.
T4: Request A finishes processing and SETS cache to old price = 100.
T5: Request C reads cache HIT, receives old price = 100.
```

Even though B **deleted the cache after commit**, A can still repopulate stale data **after the deletion time**. This is a limitation of basic cache-aside in systems with concurrent reads and writes.

If the data permits eventual consistency (*eventual consistency*), a relatively short TTL can bound the discrepancy window. If re-writing stale values must be prevented, you can design:

- Data versioning and version checking when writing to the cache.
- Versioned keys/namespaces that change on updates; old reads writing to the old version key are no longer accessed.
- Synchronizing cache population and updates per key within the necessary scope.
- Specialized caching mechanisms with stronger consistency guarantees, or bypassing cache for critical read paths.

**Using DEL after commit and TTL alone does not provide strong consistency.** Requirements such as checking account balances, deducting inventory, or making authorization decisions need to reference the authoritative source or an appropriate transactional mechanism.

## 8. When Redis fails: can the application read from the source?

A cache serves to optimize reads. For many APIs, when Redis is temporarily unreachable, the application can **read directly from the database** to maintain service. However, this must be intentionally designed:

```text
Request
   |
Redis GET
   |
   +-- HIT -------------> return cache
   |
   +-- MISS ------------> Database -> SET cache -> return data
   |
   +-- Redis error -----> Database --------------> return data
```

An example limiting fallback scope to **Redis connection errors**:

```java
public ProductView findByIdWithCacheFallback(long id) {
    String key = "product:detail:v1:" + id;
    boolean redisReachable = true;

    try {
        ProductView cached = redis.opsForValue().get(key);

        if (cached != null) {
            return cached;
        }
    } catch (RedisConnectionFailureException ex) {
        redisReachable = false;
        // Record Redis error metric/log; avoid logging per request.
    }

    ProductView loaded = source.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));

    if (redisReachable) {
        try {
            redis.opsForValue().set(
                    key, loaded, Duration.ofMinutes(5)
            );
        } catch (RedisConnectionFailureException ex) {
            // Source data read succeeded: return to caller.
            // Record metric/log; do not treat cache write as a business write.
        }
    }

    return loaded;
}
```

Exception import: `org.springframework.data.redis.RedisConnectionFailureException`. The example is placed inside a service that already receives `redis` and `source` via its constructor as in the previous section.

Things to note:

- **Do not swallow every `Exception`** when accessing Redis. Serializer errors, programming bugs, type mismatches, or corrupted cache data must be detected and handled appropriately.
- When Redis is down, many requests hitting the database simultaneously can cause overload. Concurrency limits, proper timeouts, circuit breakers, or load-shedding policies are needed.
- For cache tasks involving sensitive data or strict consistency contracts, do not enable fallback merely because "cache is optional" without reviewing the business impact.
- Connection errors are **different** from cache misses. On dashboards, there must be a separate metric for Redis errors.

## 9. Cache-aside is not a database transaction

Some operations look transactional but behave differently in practice:

| Operation | In the same transaction as the database? |
|---|---|
| `source.findById(id)` then `redis.opsForValue().set(...)` | Not automatically |
| `@Transactional` around JPA update then `redis.delete(key)` | Redis does not automatically join the SQL transaction |
| `@TransactionalEventListener(AFTER_COMMIT)` to delete cache | Runs after commit, but does not guarantee durable delivery |
| `WATCH/MULTI/EXEC` in Redis | Redis transaction; does not automatically span external databases |
| TTL expiration | Lifecycle event of a Redis key, not an SQL transaction |

Therefore, you must clearly decide the **consistency boundary**: can cache reads tolerate lagging a few seconds/minutes behind the source? If not, basic cache-aside may not be suitable for that data.

For instance, product catalog display can tolerate a slight delay. By contrast, balance deduction or payment confirmation operations usually need to verify exact data from the authoritative source at transaction time.

## 10. Comparing cache-aside with related strategies

| Strategy | Who decides to read the cache? | When is the cache populated? | When writing source data |
|---|---|---|---|
| **Cache-aside** | Application | On read miss | Application typically invalidates the cache |
| **Read-through** | Cache layer with integrated loader | Cache calls the source itself on miss | Depends on cache/loader design |
| **Write-through** | Application through the cache layer | When writing data | Writes cache and source per cache-layer mechanism |
| **Write-behind/write-back** | Cache layer | Along the write stream | Cache accepts writes first, flushes to source later |
| **Cache refresh ahead** | Refresh mechanism | Before TTL expires | Usually paired with a dedicated invalidation strategy |

Cache-aside is easy to apply with `RedisTemplate` because service code has full control. In return, services must align on key, TTL, invalidation, error, and observability policies.

### How does the Spring Cache abstraction relate?

Spring provides `@Cacheable`, `@CachePut`, `@CacheEvict`, and the `CacheManager` mechanism. For example:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductView getProduct(long productId) {
    return source.findById(productId)
            .orElseThrow();
}
```

With a configured `RedisCacheManager`, the read path can behave similarly to cache-aside: check the cache first, invoke the source method on miss, then store the result. However, annotations do not automatically solve every scenario such as cross-instance stampedes, post-commit invalidation, system-wide consistency, or error policies.

**Two different implementation approaches:** the `RedisTemplate` example in this lesson illustrates **manual** cache-aside; the `@Cacheable` example illustrates letting the Spring Cache abstraction coordinate it. Choose one clear mechanism for a given read path to avoid accidentally caching twice with different TTLs and keys.

## 11. Choosing TTL and invalidation strategy

TTL depends on how frequently data changes and how much staleness is acceptable:

| Data type | Characteristics | Design direction |
|---|---|---|
| Nearly static catalog | Infrequently updated | Long TTL, invalidation on publish |
| Listed price | Mutable, need to limit stale prices | Medium/short TTL and post-commit invalidation |
| Expensive search results | Built from multiple records | Bounded TTL, key includes query parameters |
| Login sessions | Security and revocation implications | Business checks, appropriate TTL; do not rely solely on cache-aside |
| Real-time inventory | High update contention | Authoritative source and concurrency-controlled ops make the final decision |

Several recommendations:

1. **TTL is a fallback** when invalidation does not occur or fails. Do not treat it as notification that data has changed.
2. **Scoped invalidation:** if product 42 is updated, only delete related keys, unless business logic truly requires clearing the whole catalog.
3. **TTL with jitter:** reduces mass simultaneous expiration when keys are loaded in a batch.
4. **Schema version in the key:** when changing serialization structure, move to a new namespace to avoid incompatible old cached entries.
5. **No universal "optimal TTL":** you must measure hit ratio, database load, and acceptable staleness.

## 12. Observing and measuring cache-aside effectiveness

Having Redis running does not prove the cache is beneficial. Measure at least:

| Metric | Question to answer |
|---|---|
| **Cache hit** | How many reads found data in the cache? |
| **Cache miss** | How many reads had to query the source? |
| **Hit ratio** | What fraction of reads can be served from the cache? |
| **Load latency** | How long does reading the database take on a miss? |
| **Cache read/write latency** | Is Redis fast enough compared to the source? |
| **Redis errors** | How many timeouts, disconnections, or deserialization errors occurred? |
| **Database QPS** | Did source queries actually decrease? |
| **Stale reads** | Is stale data occurring beyond the allowed window? |
| **Evictions/expired keys** | Are keys removed due to memory pressure or TTL expiration? |
| **Heap, CPU, network** | Is serialization/caching creating a new bottleneck? |

Basic hit ratio:

```text
Hit ratio = hits / (hits + misses)
```

For example, 8,000 hits and 2,000 misses gives an 80% hit ratio. Do not ambiguously lump Redis connection errors into misses: errors and misses reflect different root causes.

Depending on goals, you can add **source read rate** and **request p95/p99 latency**. A high hit ratio where the cache returns oversized JSON payloads may still fail to deliver the desired experience.

### 12.1. Distinguishing cold cache and warm cache

- **Cold cache:** most keys are not present yet; the application must read the source heavily.
- **Warm cache:** many keys are already present; requests are likely to hit.
- **Mixed workload:** more realistic, involving TTLs, additions/deletions, and data changes.

If you only benchmark a 100%-hit warm cache, you haven't measured database load when keys expire. If you only benchmark a cold cache, you haven't seen the steady-state benefit.

### 12.2. Testing impact when Redis is unavailable

An operational scenario to test in a controlled environment:

```text
Redis healthy:
    API -> Redis hit/miss -> database when needed

Redis unavailable:
    API -> Redis error -> database fallback
                            |
                       check DB QPS/p99
```

When fallback is enabled, the database may have to absorb all the traffic that Redis previously handled. Limits, timeouts, load shedding, and recovery time must be defined.

## 13. Hands-on exercise: tracking a key's lifecycle

This can be practiced on a development Redis instance using an isolated namespace.

### Step 1: Clear old exercise cache data

```redis
DEL demo:product:42
```

Verify:

```redis
GET demo:product:42
```

Redis returns `nil`: cache miss.

### Step 2: Simulate reading source data and writing cache

```redis
SET demo:product:42 "{\"id\":42,\"name\":\"Office Desk\",\"price\":100}" EX 60
```

This command corresponds to the "write the result fetched from the database" step in the cache-aside flow.

### Step 3: Read again and observe TTL

```redis
GET demo:product:42
TTL demo:product:42
```

`GET` returns the data: cache hit. `TTL` returns remaining seconds, counting down over time.

### Step 4: Simulate a source update

In a real application, update the database first, commit successfully, then invalidate the cache:

```redis
DEL demo:product:42
```

The next read:

```redis
GET demo:product:42
```

will miss. The application fetches the new version from the source and then:

```redis
SET demo:product:42 "{\"id\":42,\"name\":\"Office Desk\",\"price\":120}" EX 60
```

### Step 5: Observe automatic expiration

Wait past the configured duration or use a test key with a very short TTL:

```redis
SET demo:short-lived "value" EX 3
TTL demo:short-lived
```

After expiration, `GET demo:short-lived` returns `nil` and `TTL` normally returns `-2`.

The goal of this exercise is to recognize the lifecycle: **no key → miss → load → hit → invalidate/expire → miss → reload**.

## 14. Common mistakes and how to think about fixing them

### Mistake 1: Treating Redis as the authoritative data source

Caches typically have TTLs and can be evicted under memory pressure. If the cache is only a copy of the database, do not use key existence to replace business constraints or source transactions.

### Mistake 2: Setting no TTL

Stale cache entries can persist for a very long time if an invalidation is missed. TTL should reflect staleness tolerance; do not store indefinitely by default.

### Mistake 3: Not deleting cache after database updates

Source data has changed while Redis continues returning the old copy until expiration. Build an invalidation flow after a successful update.

### Mistake 4: Deleting cache before the transaction commits

Another request can miss and reload the old database state. Identify the commit boundary and perform cache deletion after commit; for strict requirements, add durable and consistency-preserving mechanisms.

### Mistake 5: Assuming post-commit cache deletion prevents all stale data

An in-flight missing request can read old data and run `SET` after deletion completes. This is a separate race condition; handle it with versioning or appropriate synchronization if required.

### Mistake 6: Ignoring stampedes

A hot key expiring can cause many concurrent requests to hit the database. Consider single-flight, distributed locks, refresh ahead, or concurrency limits.

### Mistake 7: Caching non-existent data for too long

Negative caching can cause the application to keep returning "not found" after the object is newly created. Use short TTLs and invalidate upon creation if needed.

### Mistake 8: Using one key for all users or tenants

If results depend on language, tenant, permissions, or configuration, the key must include all those dimensions. Poor key design can cause data leaks.

### Mistake 9: Passing JPA entities directly to a JSON serializer

Lazy relationships, circular references, internal fields, and schema changes can cause errors or oversized payloads. Use an appropriate read model/DTO.

### Mistake 10: Swallowing all Redis errors

Connection errors may allow fallback, but serialization errors or malformed data need to be surfaced. Do not treat all Redis exceptions as cache misses.

### Mistake 11: Measuring effectiveness solely by hit ratio

A high hit ratio with huge JSON values or a distant Redis can still cause high latency. Measure p95/p99, database QPS, errors, and resource usage.

### Mistake 12: Keeping cache on data that requires immediate accuracy

Decisions like deducting inventory, processing payments, or enforcing authorization require checking the authoritative data source and proper concurrency controls. Cache-aside can assist display, but does not inherently guarantee strong consistency.

## 15. Self-check questions

**1. When Redis returns `null`, can we conclude the product does not exist?**

No. That is a cache miss; you must check the authoritative source.

**2. How does the first read of a key proceed with cache-aside?**

The application checks Redis, misses, reads the database, writes the data to cache with a TTL, and returns the data.

**3. Does a cache hit query the database?**

In the basic cache-aside flow, a cache hit allows returning data immediately without querying the source for that read.

**4. Why still set a TTL if cache is deleted after every update?**

Because invalidation can fail or be missed; TTL bounds how long stale data can survive.

**5. Should cache be deleted immediately before a database transaction commits?**

Be careful. Another request could reload stale data. Normally you should invalidate after a successful commit, while also accounting for the possibility of event/deletion failure.

**6. What happens when two requests miss the same key simultaneously?**

Both may query the database and write to the cache. With many concurrent requests, this creates a cache stampede risk.

**7. Does deleting cache after commit eliminate all race conditions?**

No. A request that read the old source can repopulate the cache after the updating request deleted it. Stronger guarantees require versioning or other synchronization mechanisms.

**8. When Redis loses connection, can the application keep reading the database?**

Yes, if the read path is designed with a fallback and the database can handle the load. Connection errors must be distinguished from data or serializer errors.

**9. Is a 90% hit ratio sufficient proof of a good cache?**

No. You must evaluate API latency, bytes transferred, serializer overhead, database load, and staleness.

**10. When should cached data not be used as the final decision condition?**

When business logic requires up-to-the-instant state or strong consistency, such as payments, balance deductions, authorization checks, or final inventory.

## 16. Key takeaways

- **Cache-aside** is a strategy where the application actively **reads cache first, reads the source on a miss, and puts the result into cache**.
- **Redis holds a read-serving copy**; the authoritative source still determines exact truth.
- The cache lifecycle is **miss → load → set TTL → hit → expire/invalidate → miss**, though concurrent requests can complicate this flow.
- When the source changes, typically **invalidate cache after commit**. TTL is a guardrail bounding data age, not an absolute synchronization mechanism.
- Handle **stampedes, negative caching, races between load and invalidate, Redis errors, and key design** according to the business-required consistency level.
- Evaluate effectiveness via **hit/miss, latency, database QPS, memory, and stale reads**, not just Redis `GET` speed.

### References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html).
- [Redis — GET](https://redis.io/docs/latest/commands/get/).
- [Redis — SET](https://redis.io/docs/latest/commands/set/).
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
