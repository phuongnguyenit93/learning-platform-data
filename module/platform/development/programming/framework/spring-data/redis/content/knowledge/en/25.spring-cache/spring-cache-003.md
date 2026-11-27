# Using @Cacheable, @CachePut, and @CacheEvict

Spring Cache provides an abstraction for Java applications to use caching via annotations. In a **Spring Data Redis** application, Redis can serve as a shared cache store across multiple instances, while the `@Cacheable`, `@CachePut`, and `@CacheEvict` annotations determine **when to read, write, or evict** stored results.

The three annotations have similar names, but very different behaviors:

- **`@Cacheable`:** before executing the method, looks up the cache by key; if a valid value exists, returns that value immediately and skips the method body; on a miss, invokes the method and may store the result.
- **`@CachePut`:** always invokes the method; then uses the return value to update the cache entry under the key.
- **`@CacheEvict`:** deletes one entry or multiple entries according to rules; typically used after source data is modified or deleted.

Distinguishing these three behaviors accurately enables implementing the **cache-aside** pattern for reads, synchronizing caches after writes, and preventing the cache from serving stale data.

## 1. Where does Spring Cache sit in a Redis architecture?

`@Cacheable`, `@CachePut`, and `@CacheEvict` belong to the `org.springframework.cache.annotation` package and are not Redis-specific annotations. Spring uses `CacheManager` and `Cache` to perform cache operations. When `RedisCacheManager` is selected, cached data is stored in Redis.

```text
HTTP Controller
       |
       v
Spring Service (proxied by Spring Cache)
       |
       +-- @Cacheable: check Redis before entering method
       |
       +-- Cache HIT ----------------------> Return result
       |
       +-- Cache MISS --> Method --> Source Database/API
                               |
                               v
                         Store in Redis
                               |
                               v
                           Return result
```

In this model, each layer has a distinct responsibility:

| Component | Responsibility |
|---|---|
| `@Cacheable` | Selects results eligible to be read back from cache by key |
| `@CachePut` | Writes the method result into cache after the method executes |
| `@CacheEvict` | Removes cached data by key or across an entire cache name |
| `CacheManager` | Manages caches by name |
| `RedisCacheManager` | Implements Spring Cache on Redis |
| Source Database/API | Provides and validates canonical business data |

**Redis Cache is a query-serving copy**, unless the architecture explicitly designates Redis as the primary data store. For most applications using a database as the source of truth, cache entries can be reconstructed from the database when evicted or expired.

### Distinguishing Spring Cache from Redis Repository

`@RedisHash`, `@Id`, and `@Indexed` serve entity mapping via Spring Data Redis Repository. By contrast, `@Cacheable` uses the Spring Cache abstraction to store **method return values** under keys determined by the cache resolver/key generator.

For example, `@RedisHash("products")` and `@Cacheable(cacheNames = "productById")` **do not automatically share the same dataset or serializer**. Sharing a Redis connection does not mean a cache entry can be read as a Redis Repository entity.

## 2. Preparing Spring Boot to use Redis Cache

A Spring Boot application using Spring Cache with Redis typically requires the corresponding dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example Redis connection configuration in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Production deployments require appropriate connection, authentication, TLS, and timeout settings matching your Redis deployment. Do not hardcode passwords in examples or source code.

### 2.1. Enabling caching

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class SpringCacheConfiguration {
}
```

`@EnableCaching` enables detection of Spring Cache annotations and registers the corresponding interceptors in the Spring context. With the standard proxy configuration, only calls passing **through a Spring-managed proxy** receive cache advice.

Without caching enabled or if the bean is not Spring-managed, annotations in Java code will not trigger Redis commands.

### 2.2. Configuring RedisCacheManager and per-cache TTL

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfigurationExample {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(2));

        Map<String, RedisCacheConfiguration> perCache = Map.of(
                "productById",
                defaults.entryTtl(Duration.ofMinutes(10)),

                "productAvailability",
                defaults.entryTtl(Duration.ofSeconds(15))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .transactionAware()
                .build();
    }
}
```

In this example:

- `productById` is configured with a 10-minute TTL.
- `productAvailability` has a 15-second TTL because it requires fresher data.
- Other caches created with the default configuration have a 2-minute TTL.
- `disableCachingNullValues()` skips storing `null` values in Redis for this configuration.
- `transactionAware()` allows cache `put` and `evict` operations to be deferred until the active Spring transaction commits successfully when transaction synchronization is active; this does not turn Redis and the database into a distributed transaction.

**TTL is a cache policy**, whereas annotations govern when to interact with the cache. The numbers above are illustrative; choose TTLs based on data freshness, source query cost, and the risk of displaying stale copies.

Note on serializers: the default `RedisCacheConfiguration` uses Redis Cache's default serialization rules, which may differ from the JSON format used by your API. For values shared across versions or languages, select an explicit serializer and schema contract; do not assume Redis cache contains JSON simply because controllers return JSON.

## 3. @Cacheable: execute the method only when data must be loaded

Basic syntax:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView findById(String productId) {
    return productStore.findById(productId);
}
```

Here:

- `cacheNames = "productById"`: cache name managed by `CacheManager`.
- `key = "#p0"`: SpEL expression extracting the method's first argument.
- `ProductView`: return type stored in the cache.
- `productStore.findById(...)`: source read path on a cache miss.

### 3.1. Execution flow

```text
Call findById("p-17")
           |
           v
   Generate key via #p0
           |
           v
   Redis cache productById
           |
       +---+---+
       |       |
      HIT     MISS
       |       |
       v       v
 Return value  Run findById
                  |
                  v
             Read database
                  |
                  v
           Store value in cache
                  |
                  v
              Return result
```

On the first call to `findById("p-17")`, the cache has no value, so the method runs. On subsequent calls, if the entry remains valid in Redis, Spring can return the cached copy without querying the database. Once the entry expires or is evicted, the next read becomes a cache miss and runs the method again.

### 3.2. Cache key and cache name

With `RedisCacheManager`'s common key prefix configuration, the Redis key may look like:

```text
productById::p-17
```

Distinguish between:

- `productById` is the **cache name** in Spring.
- `p-17` is the **logical key** inside the cache, taken from `#p0`.
- The physical Redis key string may have prefixes added or be transformed by the cache manager and key serializer configuration.

Do not let other applications manipulate internal keys directly before agreeing on naming conventions and serializers.

If the same method also depends on tenant, locale, currency, or permissions, the key must include all parameters that can produce **different results**. For instance, `findById(tenantId, productId)` using only `#p1` could cause two tenants sharing a product ID to share the wrong cache entry.

```java
@Cacheable(
        cacheNames = "productByTenant",
        key = "#p0 + ':' + #p1")
public ProductView findById(String tenantId, String productId) {
    return productStore.findById(tenantId, productId);
}
```

A secure design must also enforce authorization at the business layer. Never treat a cache key as an access-control mechanism.

### 3.3. Skipping null results with unless

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return productStore.findById(id);
}
```

`unless` is evaluated **after the method has executed**, so it can reference `#result`. In this example, if the database has no matching product and returns `null`, the result is not cached.

Choosing not to cache `null` fits cases where newly created products must be visible immediately on the next query. However, for repeatedly queried nonexistent keys, caching "no data" with a short TTL can reduce database load. Keep this aligned with the cache manager's `disableCachingNullValues()` policy.

### 3.4. @Cacheable is unsuitable for write operations that must run

Incorrect example:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

On a cache hit, Spring may **skip executing `update(...)`**, meaning the database is never updated. Methods with mandatory side effects should never be wrapped with `@Cacheable`.

## 4. @CachePut: always run the method, then update the cache

`@CachePut` applies when the method must execute, yet **its new result should also be written into the cache**.

```java
@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

Flow:

```text
Call update("p-17", command)
              |
              v
     Run update method
              |
              v
      Write source data
              |
              v
     Receive new ProductView
              |
              v
     Cache PUT productById
              |
              v
         Return result
```

If the database update succeeds and the method returns the new `ProductView`, Spring Cache stores the result under key `p-17`. The next `@Cacheable` call with the same cache name and key can immediately receive the fresh copy.

`@CachePut` **does not read the cache to decide whether to skip the method**. It fits update commands whose return value matches the exact type expected by the cached read method.

### 4.1. Matching cache name, key, and value type

Consider two methods:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView findById(String id) { ... }

@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) { ... }
```

With the same `productById` and `#p0`, both cache read and write target the same entry. If the update method used `key = "#p1"`, the second argument is `UpdateCommand`, so it would write under a completely different key. The `findById` cache would still hold the stale copy.

Elements that must stay consistent include **cache name, key generation, value type, serialization version, and tenant policy**. A mismatch in even one factor can lead to an out-of-sync cache or type conversion errors.

### 4.2. @CachePut and return values

`@CachePut` stores the **method return value**; it does not automatically invoke the read method to fetch a fresh copy. If an update method returns `boolean` while `@Cacheable` reads `ProductView`, sharing the same cache name and key writes the wrong data type and breaks subsequent reads.

When an update method returns `void`, it is usually better to use `@CacheEvict` to delete the stale entry and let the next read reload fresh data from the source. Do not expect `@CachePut` to look up a new entity when the method does not return one.

### 4.3. condition and unless

`@CachePut` also supports conditions:

```java
@CachePut(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null",
        unless = "#result == null")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

- `condition` decides whether to apply the cache operation based on context before running the method; it does not prevent the update method itself from running.
- `unless` can prevent storing the result after the method completes, such as a `null` result.
- Do not use cache conditions as substitutes for business validation or authorization.

If an update succeeds but `unless` blocks the put, the old entry may remain in the cache. Whenever a condition can suppress updating the cache, evaluate whether you need to **evict the old entry** rather than merely skipping the put.

## 5. @CacheEvict: delete cache entries when source data changes

Many write operations only return a status or `void`. In those cases, **deleting the cache entry by key** is usually simpler and safer than computing a new value to put.

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void delete(String id) {
    productStore.delete(id);
}
```

The default behavior of `@CacheEvict` is **evicting after the method completes successfully**. If `delete(...)` throws an exception, cache eviction normally does not run because the method did not finish.

Example of updating a price without returning a full `ProductView`:

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void changePrice(String id, BigDecimal price) {
    productStore.changePrice(id, price);
}
```

The next read will encounter a cache miss and retrieve the product with its updated price from the database.

### 5.1. Evicting a single key

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void removeProduct(String id) {
    productStore.delete(id);
}
```

Only the entry with the matching key is removed from the `productById` cache. This is typically the right choice when the exact modified ID is known.

### 5.2. Evicting the entire cache

```java
@CacheEvict(cacheNames = "productById", allEntries = true)
public void rebuildProductCatalog() {
    productStore.rebuildCatalog();
}
```

`allEntries = true` removes **all entries** belonging to this cache name. This may be necessary after a large-scale change, but can cause many simultaneous cache misses and spike database load.

Do not combine `allEntries = true` and `key = "..."` in the same `@CacheEvict` declaration: the two options are mutually exclusive in meaning.

### 5.3. Evicting before method execution

```java
@CacheEvict(
        cacheNames = "productById",
        key = "#p0",
        beforeInvocation = true)
public void invalidateThenRun(String id) {
    productStore.recompute(id);
}
```

When `beforeInvocation = true`, the cache entry is deleted **before** the method runs, even if the method subsequently fails. This is occasionally appropriate for operations requiring immediate invalidation upfront, but carries a risk: another request may miss and reload **stale data before the update finishes**.

For database updates, the default `beforeInvocation = false` is generally preferable because eviction occurs only after success. Even so, "evict after method" does not automatically mean "evict after database commit" when transactions are active; see the transaction synchronization section below.

## 6. Complete service example: reading, updating, and deleting products

We use the same `productById` cache to illustrate all three annotations. Assume the database is the canonical source and Redis serves purely as a read cache.

### 6.1. Data types and source access port

```java
import java.math.BigDecimal;

public record ProductView(
        String id,
        String name,
        BigDecimal price) {
}
```

```java
import java.math.BigDecimal;

public interface ProductStore {

    // Returns null if no product exists.
    ProductView findById(String id);

    // Updates the source and returns the new ProductView.
    ProductView update(String id, String name, BigDecimal price);

    // Deletes data in the source.
    void delete(String id);
}
```

`ProductStore` is an illustrative interface; real implementations may use Spring Data JPA, JDBC, or an upstream API. The essential requirement is that methods have clear contracts and return the exact saved state.

### 6.2. Query service using @Cacheable

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductStore store;

    public ProductQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
            cacheNames = "productById",
            key = "#p0",
            unless = "#result == null")
    public ProductView findById(String id) {
        return store.findById(id);
    }
}
```

If `productById::p-17` is absent from Redis, the method calls `store.findById("p-17")`. If Redis already holds a valid entry, Spring Cache returns that value without calling the store.

### 6.3. Write service using @CachePut and @CacheEvict

```java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductStore store;

    public ProductCommandService(ProductStore store) {
        this.store = store;
    }

    @Transactional
    @CachePut(cacheNames = "productById", key = "#p0")
    public ProductView update(
            String id, String name, BigDecimal price) {
        return store.update(id, name, price);
    }

    @Transactional
    @CacheEvict(cacheNames = "productById", key = "#p0")
    public void delete(String id) {
        store.delete(id);
    }
}
```

In this example:

1. `ProductQueryService.findById("p-17")` fetches from Redis if present, otherwise from the source.
2. `ProductCommandService.update("p-17", ...)` always writes to the database, then stores the new `ProductView` in the cache.
3. `ProductCommandService.delete("p-17")` always deletes data from the source, then removes the cache entry.
4. Methods are called from other beans, so in normal proxy configuration the cache interceptor can run.
5. `@Transactional` takes effect if the application has a transaction manager compatible with `ProductStore`. The transaction-aware Redis Cache configuration in Section 2 defers put/evict while a corresponding Spring transaction is active.

Do not create separate caches with different names for read and write paths of the same value type without good reason; update methods must target the exact key created by query methods.

### 6.4. Step-by-step data progression

Suppose the database initially stores:

```text
Product p-17:
  name = "Keyboard"
  price = 500000
```

| Step | Action | Database | Redis cache |
|---|---|---|---|
| 1 | `findById("p-17")` | Read | Miss, then stores price 500000 |
| 2 | `findById("p-17")` again | Not read again | Hit, returns price 500000 |
| 3 | `update("p-17", ..., 450000)` | Updates price to 450000 | `@CachePut` writes new copy |
| 4 | `findById("p-17")` | Not read again | Hit, returns price 450000 |
| 5 | `delete("p-17")` | Deletes product | `@CacheEvict` deletes entry |
| 6 | `findById("p-17")` | Not found | Miss; returns null and does not cache null |

This example assumes operations succeed with no concurrent access. In real systems, concurrent requests can create scenarios where the cache is overwritten by an older read.

## 7. Key expressions: what ensures annotations coordinate properly

If the same product has multiple access paths, such as:

```java
findById("p-17")
update("p-17", ...)
delete("p-17")
```

all of them must resolve to the same key `p-17` in the `productById` cache.

### 7.1. SpEL in annotations

Spring Cache supports SpEL:

| Expression | Meaning |
|---|---|
| `#p0` or `#a0` | First parameter |
| `#p1` | Second parameter |
| `#id` | Parameter named `id`, when parameter name metadata is accessible |
| `#result` | Return value, usable in post-method contexts such as `unless` or `@CachePut` keys |
| `#root.methodName` | Name of the cached method |
| `#root.targetClass` | Class of the target in the expression context |

Using `#p0` keeps examples independent of whether the application was compiled with parameter names preserved. For complex keys, a shared `KeyGenerator` can be safer than repeating long SpEL strings that risk drifting apart.

### 7.2. Incomplete keys can mix up data

Consider an API retrieving products by tenant and currency:

```java
@Cacheable(
        cacheNames = "priceByTenantAndCurrency",
        key = "#p0 + ':' + #p1 + ':' + #p2")
public BigDecimal getPrice(
        String tenantId, String productId, String currency) {
    return store.loadPrice(tenantId, productId, currency);
}
```

If cached only by product ID, Tenant A's USD price could be served to Tenant B requesting VND. Both cache name and key must reflect **every input that affects the result**.

For values legitimately shared across multiple users, define the scope accurately. For user- or permission-dependent data, never let caching bypass authorization checks.

### 7.3. Versioning keys across schema changes

When `ProductView` undergoes incompatible structural changes, old and new instances may access Redis concurrently. If the cache name and serializer match while value types differ, instances may fail to deserialize each other's entries.

You can use versioned cache namespaces such as `productByIdV2`, or coordinate deployments to avoid sharing incompatible values. Account for the lifetime of old entries and how caches are cleared during upgrades.

## 8. condition and unless: when are conditions evaluated?

Both attributes control cache application, but at different points in time.

### 8.1. condition

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null")
public ProductView findById(String id) {
    return store.findById(id);
}
```

`condition` is evaluated **before cache usage** using method context. If the condition is false, caching is skipped for that call and the method runs normally.

### 8.2. unless

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return store.findById(id);
}
```

`unless` is checked after the method runs and produces a result. If false, the result is permitted to be cached. If true, the result is withheld from the cache.

**Do not use `#result` in `condition` expecting the method to have run**, since `condition` must be evaluated before any result exists. Similarly, with `@CacheEvict(beforeInvocation = true)`, no post-method result is available.

### 8.3. Cache conditions do not replace business rules

For instance, `condition = "#p0 != null"` only decides whether caching applies; the method must still reject invalid IDs if business rules demand it. Nor should `unless` decide whether the database is written: it participates solely in the cache policy.

## 9. Clearing multiple caches after one change

A single action can affect multiple caches. For example, when updating a product price, a system may maintain:

- Detail cache `productById`.
- Category list cache `productListByCategory`.
- Currency price cache `priceByTenantAndCurrency`.

Using `@CachePut` on `productById` alone is insufficient to update aggregate or list caches containing that product.

Spring allows `@Caching` to declare multiple evictions:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Caching(evict = {
        @CacheEvict(cacheNames = "productById", key = "#p0"),
        @CacheEvict(
                cacheNames = "productListByCategory",
                allEntries = true),
        @CacheEvict(
                cacheNames = "priceByTenantAndCurrency",
                allEntries = true)
})
public void changePrice(String productId, BigDecimal newPrice) {
    store.changePrice(productId, newPrice);
}
```

This approach is conceptually valid, yet **clearing two list/price caches completely** can trigger many cache misses and concentrate load on the database. Whenever affected keys can be identified, evict selectively. Otherwise, design reverse indexes, cache key versioning, or specialized invalidation events for aggregated views.

In particular, for lists cached by filter, sort, and page criteria, a single product update can affect numerous cached pages. Guessing a single list key is never enough to guarantee accurate data.

## 10. How do TTL and active eviction work together?

TTL bounds how long a cache entry remains valid without invalidation. `@CacheEvict` removes cached entries in response to source change events.

Example:

```text
10:00  findById(p-17)   -> caches price 500000, 10-minute TTL
10:02  update(p-17)     -> database price 450000
                          @CachePut writes cached price 450000
10:03  findById(p-17)   -> cache returns price 450000
10:12  Cache expires    -> next read fetches from database again
```

A typical design combines:

1. **TTL** as a freshness guardrail when invalidations are missed or data changes infrequently.
2. **`@CachePut`** when a mutation returns the exact new value to cache.
3. **`@CacheEvict`** when a mutation does not return a suitable value or multiple read views depend on it.
4. **Event invalidation** when multiple services can modify the source data.
5. **Monitoring** to detect stale data, mass cache misses, and Redis connection failures.

TTL **does not automatically know when the database was edited**. If another application updates the database without emitting an invalidation, the cache can keep serving stale copies until expiration.

### Losing keys before TTL

Redis can evict keys due to memory pressure prior to TTL expiration depending on `maxmemory-policy`. A cache miss does not necessarily mean data expired on schedule.

Conversely, Spring Cache can repopulate an entry on a miss, so the new entry's TTL is normally counted from the most recent cache write.

## 11. Transactions and when Redis Cache updates occur

When a database-writing method carries `@Transactional`, developers naturally assume:

```java
@Transactional
@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(...) { ... }
```

definitely updates Redis **after the database has committed**. However, Spring AOP advice ordering and the cache manager mechanism determine when the cache operation actually executes.

If a cache put runs before database commit and the database rolls back, Redis may store data the database never confirmed. If cache eviction runs before commit, another request can miss and reload the old copy.

### Transaction-aware cache manager

In the `RedisCacheManager` configuration at the start of the lesson:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .transactionAware()
        .build();
```

When a matching Spring transaction and active transaction synchronization exist, normal cache puts/evicts can be deferred until **after commit succeeds**. This reduces cases where the cache is updated while the database rolls back.

Understand the limits, though:

- There is no atomic distributed transaction spanning the database and Redis.
- The database may commit successfully while the post-commit Redis operation fails.
- `beforeInvocation = true` evictions have distinct semantics and should not be expected to defer like default evictions.
- A transaction without registered synchronization or a call bypassing the Spring proxy may not receive the expected protection.
- Concurrent writers can still race with miss-and-refill reads.

For critical data, use an event/outbox mechanism and reconciliation when invalidation retries after failures are required. For ordinary caches, an appropriate TTL plus controlled invalidation is a pragmatic choice.

## 12. Stale writes when reads and updates happen concurrently

Even when `@Cacheable` and `@CacheEvict` are used properly, a race can still happen:

```text
Request A (GET)                     Request B (UPDATE)
       |                                    |
Cache MISS                                 |
       |                                    |
Read DB, gets old copy                     |
       |                              Write new DB copy
       |                              Evict cache
       |                                    |
Write old copy to Redis                    |
       |                                    |
       +----------- Cache is now stale -----+
```

Request A begins reading before Request B updates, yet writes the cached result **after B has evicted**. The cache can retain the stale copy until the next invalidation or TTL expiration.

This is why caching annotations alone do not solve every concurrent consistency problem. Options depend on strictness:

- Short TTL if brief staleness is acceptable.
- Attach a version or timestamp, replacing the cache only if the version is not older.
- Use post-commit event invalidation with retries/reconciliation when necessary.
- Coordinate reads and writes directly where strong guarantees are truly required.
- Never rely on caches for final decisions on balances, permissions, payments, or inventory without matching consistency mechanisms.

Also note that if multiple applications update the same source data, each must invalidate the proper keys or publish shared events. Annotations in one service do not monitor writes originating in another service.

## 13. Spring AOP proxies and the self-invocation pitfall

One of the most common mistakes is calling a cached method from **within the same bean** that defines it:

```java
@Service
public class ProductService {

    @Cacheable(cacheNames = "productById", key = "#p0")
    public ProductView findById(String id) {
        return store.findById(id);
    }

    public ProductView loadForExport(String id) {
        // Internal call via this:
        return findById(id);
    }
}
```

In standard Spring Cache proxy mode, `loadForExport(...)` invokes `findById(...)` directly on the same object. The call bypasses the proxy, so **`@Cacheable` may be skipped**: the database is queried every time despite the annotation.

The clean solution is moving the call into another bean and injecting it via constructor:

```java
@Service
public class ExportService {

    private final ProductQueryService productQueries;

    public ExportService(ProductQueryService productQueries) {
        this.productQueries = productQueries;
    }

    public ProductView loadForExport(String id) {
        // Call goes through Spring-managed bean/proxy.
        return productQueries.findById(id);
    }
}
```

Similarly, a method in the same class calling a `@CacheEvict` method can bypass eviction. This is a dangerous bug because the database changes while the cache keeps serving stale data. When reviewing code, verify whether call sites pass through a proxy or are merely `this.method()`.

Beyond self-invocation, methods that proxies cannot intercept due to visibility, `final` classes/methods, or incompatible proxy configurations can also prevent annotations from taking effect.

## 14. @Cacheable(sync = true) and stampedes

When a very hot key expires, many requests can miss simultaneously and run the same database query:

```text
100 requests call findById("p-hot") concurrently
                     |
                     v
                 Cache MISS
                     |
          +----------+----------+
          |                     |
       Request A             Request B ... Z
          |                     |
    Read database         Read database
          |                     |
          +----------+----------+
                     |
                 Write cache
```

Spring Cache supports:

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        sync = true)
public ProductView findById(String id) {
    return store.findById(id);
}
```

`sync = true` asks the cache provider to coordinate loading a single key to prevent multiple threads from computing the value concurrently, **when the provider supports this synchronization feature**. Do not assume it guarantees a distributed lock with exactly one source query across all instances. The guarantee level depends on the `Cache` implementation, Redis cache writer, and configuration.

Some restrictions of `sync = true`: use only a single cache name, do not use `unless`, and do not combine other cache operations on the same method in standard Spring Cache usage.

If hundreds of instances miss a key simultaneously or Redis drops out altogether, still plan database protections: concurrency limits, cache warmup, TTL jitter, controlled stale-while-revalidate, or distributed locks with explicit contracts.

## 15. Storing nulls, exceptions, and error results

With Spring Cache, method return values and exceptions behave differently:

| Scenario | `@Cacheable` | `@CachePut` | `@CacheEvict` |
|---|---|---|---|
| Method returns normal result | May store after miss | Stores return value | Evicts after success by default |
| Method throws exception | Does not store error result as normal value | No new result to put | Default does not evict if method fails to complete |
| Method returns `null` | Depends on `unless` and cache config | Depends on `unless` and cache config | Does not depend on return value to evict |
| Redis unavailable | Cache lookup/write may fail | Cache write may fail | Cache eviction may fail |

To avoid caching `null` results, combine `unless = "#result == null"` with `disableCachingNullValues()`.

For response objects having a field like `success=false` or an error status where **the method still returns a normal object**, Spring Cache may cache that object unless an exclusion condition is specified. For example, an API client returning a DTO containing an error code as a value will be cached unless the annotation distinguishes it. Define return types and `unless` policies explicitly according to business rules.

If Redis fails, whether to propagate errors to callers or fall back to the source must be deliberately designed via `CacheErrorHandler` or appropriate logic. Never silently ignore eviction failures after database changes if doing so causes the application to serve stale data indefinitely.

## 16. Observing caches in a Redis environment

Simply knowing "annotations exist" is not enough to evaluate effectiveness. Measure by **cache name**, endpoint, and time:

| Metric | Meaning |
|---|---|
| Cache hit/miss ratio | Is the cache reducing source reads? |
| p50/p95/p99 processing time | Does the cache improve latency or worsen it when Redis slows? |
| Source database/API load and latency | Is load actually reduced or do misses still spike? |
| Put/evict count | Are entries rewritten or cleared too frequently? |
| Remaining TTL | Are entries getting the configured expiration? |
| Redis command rate, memory, `evicted_keys` | Is Redis overloaded or evicting keys before TTL? |
| Serialize/deserialize errors | Are there type or payload version incompatibilities? |
| Returned data staleness | Does cached data exceed business freshness limits? |

You can inspect Redis using CLI tools in appropriate environments:

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory

# Example when the exact physical key and serializer are known:
redis-cli TTL 'productById::p-17'
redis-cli TYPE 'productById::p-17'
```

The `TYPE` of a Redis Cache entry is typically a string value, though decoding contents depends on the serializer. `INFO` reports statistics for the entire Redis instance, not broken down automatically per cache name or endpoint; add Spring/Micrometer or service-level metrics as well.

When inspecting many keys, use `SCAN` or tools bounded by load limits; avoid `KEYS *` on large production Redis instances. Do not log full cache keys or values if they contain personal information or sensitive data.

## 17. When to choose each annotation?

| Need | Preferred annotation | Reason |
|---|---|---|
| Query rarely changing product details | `@Cacheable` | Hits bypass source queries |
| Query expensive computed results | `@Cacheable` | Reuses computed results |
| Update entity and return full updated DTO | `@CachePut` | Updates cache with fresh result |
| Update entity with `void` return method | `@CacheEvict` | No reliable new value to put |
| Delete entity | `@CacheEvict` | Prevents serving deleted data |
| Change affecting multiple list/aggregate caches | `@Caching(evict = {...})` or event invalidation | Must refresh all dependent views |
| Refresh entire catalog/cache | `@CacheEvict(allEntries = true)` with caution | Clears many entries on migration or bulk change |
| Write to cache without skipping method | `@CachePut` | Method always executes |
| Data needing immediate consistency in critical decisions | Design consistent source first | Cache annotations do not replace business transactions |

There is no universal rule that "updates always use `@CachePut`." If a method returns a partial representation, computed values omit fields, or one change affects multiple read models, eviction is usually safer and easier to reason about.

## 18. Common pitfalls and how to avoid them

1. **Using `@Cacheable` on an update method:** cache hits prevent the update from running. Choose `@CachePut` or `@CacheEvict`.
2. **Mismatched keys between `@CachePut` and `@Cacheable`:** read cache retains the old copy. Use a shared key convention.
3. **`@CachePut` returning the wrong value type:** later reads fail deserialization or return wrong data. Ensure value types match.
4. **Evicting the detail cache while forgetting list caches:** list APIs still serve stale copies. Identify every affected read model.
5. **Evicting before the update method runs:** concurrent requests can reload stale data. Choose timing based on business semantics.
6. **Forgetting transaction commits:** the cache changes even though the database rolls back, or vice versa. Use a transaction-aware cache and proper recovery mechanisms.
7. **Calling an annotated method from the same bean:** Spring proxies may not intercept it. Extract into another service or restructure calls.
8. **Keys missing tenant/currency/locale:** data leaks across contexts. Include all inputs that affect output.
9. **TTL too long:** users read outdated data. Select TTL according to freshness and invalidate when necessary.
10. **TTL too short or clearing entire caches repeatedly:** creates cache miss storms. Measure source load and stagger expirations.
11. **Not versioning value serializers:** deployments on different versions sharing Redis fail. Lock down schemas or switch namespaces.
12. **Assuming `sync=true` provides a perfect distributed lock:** actual behavior depends on the provider. Verify across multiple instances.
13. **Ignoring Redis errors after updates:** stale copies may linger in cache. Monitor errors and implement remediation.
14. **Using cache as the sole store for critical data:** Redis keys can expire or be evicted. Establish the source of truth.

## 19. Decision workflow in a new application

```text
Does the method have side effects that must run?
                     |
              +------+------+
              |             |
             No            Yes
              |             |
              v             v
      Is the result      Is it creating/updating
      reusable?          or deleting source data?
              |             |
              v             +-------------------+
        @Cacheable          |                   |
              |           Update               Delete
              |             |                   |
              |             v                   v
     Key includes tenant?  Returns full value  @CacheEvict
     Appropriate TTL?      of matching type?
     Cache nulls?               |
                            +---+---+
                            |       |
                           Yes      No
                            |       |
                            v       v
                       @CachePut @CacheEvict
                            |       |
                            +---+---+
                                |
                                v
                        Must invalidate
                        related caches?
                                |
                                v
                        @Caching / event
                                |
                                v
                        Verify commit timing
                        and race protection
```

**Core point:** `@Cacheable` is for **reading and reusing results**, `@CachePut` is for when **a method must always run and its new result is reliable enough to cache**, and `@CacheEvict` is for **removing cached data that is no longer valid**. In Spring Data Redis, the three annotations only work properly when paired with `CacheManager`, consistent keys, appropriate TTLs and serializers, calls routed through Spring proxies, and explicit write/commit policies. When multiple services or concurrent requests are involved, design additional invalidation and reconciliation so Redis data never drifts from business truth.
