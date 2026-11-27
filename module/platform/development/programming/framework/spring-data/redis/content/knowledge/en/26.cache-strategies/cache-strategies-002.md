# Distinguishing Cache Update, Cache Invalidation, and Source of Truth in Spring Data Redis

## 1. The problem: data has changed, yet users still see the old value

A Spring Boot application stores product information in PostgreSQL while using Spring Data Redis as a cache to reduce database reads. When a user opens a product page, the application reads from Redis if present. When an administrator changes the price, the database record is updated. However, if Redis still holds the old price, other users may see wrong information.

Example:

~~~text
09:00  Database: product#42.price = 100
       Redis:    productById::42 = price 100

09:05  Administrator changes price to 120
       Database: product#42.price = 120

09:06  User calls GET /products/42
       Redis:    productById::42 = price 100
       API returns: price 100  <-- stale data
~~~

To handle this properly, three concepts must be distinguished:

1. **Source of truth:** the authoritative store that determines the correct business state.
2. **Cache update:** writing the new value directly into the cached copy when data changes.
3. **Cache invalidation:** deleting or marking the copy as outdated so the next read rebuilds the cache from the source of truth.

These three concepts are related but not identical. **Cache update** and **cache invalidation** are two ways to synchronize a copy; the **source of truth** defines what the copy must reflect.

> A fast-responding cache is only valuable when the system knows how stale that data is allowed to be, when it must be refreshed, and how to recover when Redis or the application fails.

## 2. What is the source of truth?

The **source of truth** is the component designed to hold authoritative state for verification, decision-making, and data recovery. In a typical ordering system, the transactional database can be the source of truth for:

- Official product prices.
- Order statuses.
- Account balances.
- Available inventory.
- User access permissions.
- Audit change history.

In that architecture, Redis Cache is only a **rebuildable copy** derived from the source of truth. If Redis loses data, the application can read the database and recreate the cache. If Redis and the database disagree, the authoritative data is the database state according to business rules.

~~~text
                           +-----------------------------+
                           | Database                    |
                           | Source of truth             |
                           | product#42.price = 120      |
                           +--------------+--------------+
                                          |
                          read data / rebuild copy
                                          |
                                          v
                           +-----------------------------+
                           | Redis Cache                 |
                           | productById::42 = price 120 |
                           +--------------+--------------+
                                          |
                                          v
                                     Spring API
~~~

### Can Redis be the source of truth?

**Yes**, if the system intentionally designs Redis to hold authoritative business state. For example, a counter or rate-limit state can be managed directly in Redis. In that case, persistence, replication, durability, failover, atomicity, and recovery must all be evaluated.

Do not assume "Redis is always just a cache" or "Redis is fast so let's store authoritative data there." **Redis's role is determined by architecture and data guarantees**, not by the technology name.

In this lesson, to illustrate Spring Cache and Spring Data Redis, we assume:

~~~text
PostgreSQL = source of truth
Redis      = cache for read data
Spring     = coordinates queries, writes, and invalidation
~~~

The consistency rule to agree upon: a business update must succeed in the source of truth before the system considers the change complete.

## 3. Distinguishing cache update and cache invalidation

Two strategies for handling the copy after the source of truth changes:

### Cache update

After writing new data successfully, the application puts the new value directly into Redis:

~~~text
Write product.price = 120 to database
           |
           v
Write productById::42 = price 120 to Redis
           |
           v
Next read can retrieve the new price from Redis
~~~

**Advantages:** subsequent reads do not necessarily query the database to rebuild the data. Suitable when the application already has the complete new value, the key is clearly known, and the cost of building the copy is significant.

**Risks:** database write succeeds while cache write fails, or copies are written out of order under concurrent contention. If one record has multiple different cache views, every related copy must be updated accurately.

### Cache invalidation

After data in the source of truth is updated, the application deletes the potentially outdated cache key:

~~~text
Write product.price = 120 to database
           |
           v
Delete productById::42 from Redis
           |
           v
Next read: cache miss
           |
           v
Read database -> create cache with price 120
~~~

**Advantages:** no need to immediately compute the contents of all copies; the next read pulls from the source of truth. Often easier to maintain when data has many different representations.

**Risks:** the first read after invalidation is slower because it must query the source of truth. Cache deletion can still fail, arrive late, or race with a thread loading the old value.

### Comparison table

| Criterion | Cache update | Cache invalidation |
| --- | --- | --- |
| Action | Write new value into Redis | Delete/mark old copy |
| Need to know new value | Yes | Not necessarily |
| Next read | Usually cache hit | Usually cache miss then rebuild |
| Write-time cost | May require serializing and writing multiple cache entries | Usually only requires deleting related keys |
| Read-time cost | Low if update succeeded | Incurs a read from source of truth after deletion |
| Risk | Old value overwriting new value, missing derived views | Lost invalidation or cache-fill race |
| Suitable cases | Clear new value, very read-heavy, simple keys | Complex read models, multiple views, reloadable |

Both strategies need a **timing rule**: when Redis is allowed to be modified relative to when the source-of-truth transaction commits.

## 4. Cache-aside: common pattern with Spring Data Redis

**Cache-aside** (lazy loading) is the pattern:

- On read, try fetching from the cache.
- On cache miss, read the source of truth and write the result to the cache.
- When data changes, the application updates or deletes the cache per the chosen rule.

Read path diagram:

~~~text
GET /products/42
        |
        v
Redis GET productById::42
        |
        +------ HIT ------> Return ProductView
        |
        +------ MISS
               |
               v
        Database SELECT product#42
               |
               v
        Redis SET productById::42 + TTL
               |
               v
        Return ProductView
~~~

The Spring Cache abstraction can implement most of the read path using `@Cacheable`. Spring Data Redis provides `RedisCacheManager` and `RedisCache` so that the actual data resides in Redis.

Important point: **`@Cacheable` does not mean Redis becomes the source of truth.** The annotation describes how method results are reused. The source of truth remains the repository/database queried by the method.

## 5. Spring Boot example: database as source of truth, Redis as cache

Suppose a `Product` entity is managed by Spring Data JPA:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Long getVersion() { return version; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        this.price = newPrice;
    }
}
~~~

A DTO containing only what the API needs to return:

~~~java
import java.math.BigDecimal;

public record ProductView(
    Long id,
    String name,
    BigDecimal price,
    Long version
) {
    public static ProductView from(Product product) {
        return new ProductView(
            product.getId(),
            product.getName(),
            product.getPrice(),
            product.getVersion()
        );
    }
}
~~~

Database repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<Product, Long> {
}
~~~

In this model:

- `ProductJpaRepository` operates on the authoritative database.
- `ProductView` is the snapshot used for API responses and cache storage.
- `Product.version` helps identify the data version, useful for diagnostics or building protection against out-of-order cache writes.

By default, avoid caching a JPA entity directly if it contains lazy relationships, Hibernate proxies, or persistence context state. A DTO is usually easier to serialize, has a stable contract, and avoids pulling excess data.

## 6. Configuring RedisCacheManager and TTL

With the appropriate dependencies such as Spring Cache, Spring Data Redis, and Spring Data JPA, you can enable caching and configure Redis:

~~~java
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

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        var json = new GenericJackson2JsonRedisSerializer();

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .serializeValuesWith(
                    RedisSerializationContext.SerializationPair
                        .fromSerializer(json)
                )
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(
                Map.of(
                    "productById",
                    defaults.entryTtl(Duration.ofMinutes(5)),
                    "productList",
                    defaults.entryTtl(Duration.ofMinutes(1))
                )
            )
            .build();
    }
}
~~~

With this configuration:

- The `productById` cache has a 5-minute TTL.
- The `productList` cache has a 1-minute TTL.
- Values are serialized using the selected JSON serializer.
- `null` results are not cached.
- Spring Cache manages keys inside a cache-name namespace, typically formatted as `productById::42` with default configuration.

**Version note:** configuration API names and JSON serializer options may differ across Spring Data Redis/Spring Boot generations. Choose dependency versions consistent with your application. Serializers that include type metadata must be configured and compatibility-checked with trusted DTOs, especially when multiple service versions read the same cache.

### What does TTL solve?

TTL limits how long Redis keeps an entry that has not been refreshed. If an invalidation step does not occur, a short TTL allows the stale copy to disappear automatically after a defined time.

However, TTL **does not guarantee data is fresh immediately when the database updates**. For example, a 5-minute TTL can leave users seeing an old price for the remainder of its lifetime if the application does not delete/rewrite the cache.

Moreover, when the cache TTL expires, the next read must have a mechanism to reload from the source of truth. TTL only controls entry lifetime; it does not decide whether business logic permits reading an old price.

## 7. Reading data with @Cacheable

Create a query service:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {

    private final ProductJpaRepository products;

    public ProductQueryService(ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView getById(Long id) {
        Product product = products.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Product not found: " + id)
            );

        return ProductView.from(product);
    }
}
~~~

Flow:

~~~text
getById(42)
    |
    +-- productById::42 exists -> fetch ProductView from Redis
    |
    +-- Not present -> run method, query DB,
                       serialize ProductView and cache
~~~

`@Cacheable` is typically implemented with a Spring AOP proxy. On a cache hit, the method body may not run; on a miss, the method runs and the result is cached if the operation succeeds.

**Do not use `@Cacheable` to guard conditions that must always be checked in real time**, such as sensitive access control or blocking overdue payments, unless the system has clearly defined acceptable staleness and how the authoritative source is re-verified.

### Self-invocation

If a method in the same bean calls `this.getById(id)`, the internal call may go directly to the object instead of passing through the Spring proxy, so the cache annotation is not applied as expected in default proxy mode.

A safe organization is to have the controller or another service invoke the public method through a Spring bean, or extract the cached query into a separate bean.

## 8. Updating the cache with @CachePut

`@CachePut` instructs Spring to **execute the method** and then place the method's result into the cache under the chosen key.

Conceptual example:

~~~java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductUpdateWithCachePutService {

    private final ProductJpaRepository products;

    public ProductUpdateWithCachePutService(
            ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional
    @CachePut(cacheNames = "productById", key = "#result.id")
    public ProductView changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        Product saved = products.saveAndFlush(product);

        return ProductView.from(saved);
    }
}
~~~

After the method returns, `@CachePut` attempts to write the new `ProductView` into entry `productById::42`. Unlike `@Cacheable`, it **does not skip the method just because the cache already has data**.

The benefit of `@CachePut` is that the caller receives the new data right away and the cache gets updated for the next read request.

### Transaction warning

The example above is for API illustration. `saveAndFlush` **is not equivalent to a committed database transaction**. Depending on advisor configuration, transaction manager, and AOP interceptor ordering, the cache operation and the commit may not occur in the order the author expects.

If the cache is updated before the transaction actually commits and the database later rolls back, the cache can contain a value **that never became authoritative data**.

For business flows requiring post-commit consistency, separate the cache update/invalidation step from the data-writing method and execute it after the transaction commits successfully. The next section illustrates that mechanism.

## 9. Invalidating the cache with @CacheEvict

`@CacheEvict` is used to delete the entry corresponding to a key:

~~~java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductUpdateWithEvictService {

    private final ProductJpaRepository products;

    public ProductUpdateWithEvictService(
            ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional
    @CacheEvict(cacheNames = "productById", key = "#id")
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        products.save(product);
    }
}
~~~

With the default `beforeInvocation = false`, the cache is evicted when the method call completes successfully according to the interceptor mechanism. If the method throws an exception before completing, eviction typically does not execute.

However, **method completion does not always equal transaction commit**, so if correctness depends on an actual commit, use an explicit post-commit mechanism.

### Should you use beforeInvocation = true?

~~~java
@CacheEvict(
    cacheNames = "productById",
    key = "#id",
    beforeInvocation = true
)
~~~

This option deletes the cache **before running the method**, even if the method later fails. It can be useful in special scenarios, but with database updates it usually introduces risk:

~~~text
Cache deleted
    |
    v
New read request loads old data from DB
    |
    v
Write transaction still has not committed
    |
    v
Cache was just rebuilt from old data
~~~

Therefore, `beforeInvocation = true` should not be chosen as a general way to "guarantee fresh data".

## 10. Invalidating after transaction commit

A design that is easier to reason about:

1. The transaction writes data to the source of truth.
2. Inside the transaction, publish a domain event describing the changed ID.
3. After successful commit, a listener deletes the corresponding cache key.
4. The next read misses the cache and loads fresh data.

Create an internal event:

~~~java
public record ProductChanged(Long productId) {
}
~~~

Write service:

~~~java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductJpaRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        products.save(product);

        events.publishEvent(new ProductChanged(id));
    }
}
~~~

Listener running after commit:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidationListener {

    private final CacheManager caches;

    public ProductCacheInvalidationListener(CacheManager caches) {
        this.caches = caches;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterProductChanged(ProductChanged event) {
        Cache cache = caches.getCache("productById");

        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
~~~

When the call path already has a Spring-managed transaction:

~~~text
changePrice()
  |
  v
Database UPDATE inside transaction
  |
  v
publish ProductChanged(id)
  |
  v
Database COMMIT succeeds
  |
  v
AFTER_COMMIT listener
  |
  v
Redis Cache.evict(id)
~~~

If the transaction rolls back, the `AFTER_COMMIT` listener does not run eviction for that transaction.

### Limitations of AFTER_COMMIT

This is a good way to order operations **while the application process remains alive**, yet it still does not turn the database and Redis into a single atomic transaction.

For example:

~~~text
DB commit succeeds
    |
    +---- JVM crashes before AFTER_COMMIT evicts
          |
          +---- Redis may continue holding the old value
~~~

If Redis is failing, the callback may fail to delete the cache. For a system that tolerates staleness within the TTL, TTL can serve as the last-resort recovery mechanism. For requirements where cache deletion must be guaranteed, a **transactional outbox**, retries, and/or data versioning are needed. These approaches are explained in later sections.

### Internal events are not a durable message queue

`ApplicationEventPublisher` and `@TransactionalEventListener` do not persist messages to the database. If the process dies right between commit and invalidation, the in-memory event can be lost. Do not call this mechanism "guaranteed delivery".

## 11. How does post-commit cache update differ from post-commit invalidation?

Once timing is properly placed after commit, you still must choose the action:

~~~text
After DB commit:
  Option A: cache.put(id, newProductView)
  Option B: cache.evict(id)
~~~

**Direct update** makes sense when:

- The new payload is reliably known.
- One ID maps to one entry or a few cache views.
- The cost of rebuilding from the database is high.
- There is a mechanism to handle write ordering when multiple requests run concurrently.

**Invalidation** makes sense when:

- One change affects many aggregated views.
- The cache holds join results, promotional pricing, or complex read models.
- The new value is not easy to compute on the write path.
- A single cache miss after a change is acceptable.

You can write a post-commit listener to call `cache.put(...)` by having the event carry the new data. However, an event snapshot taken before commit might not reflect database-generated fields, trigger changes, or other processing rules. If an exact snapshot is needed, consider reading the committed data before caching, while guarding against races with newer updates.

## 12. One value cached in multiple places: invalidation is not just deleting one key

Suppose the system has:

~~~text
productById::42
productList::category-books::page-0
featuredProducts::today
productSearch::keyword-spring::sort-price
sellerSummary::17
~~~

When product 42's price changes, related copies may become outdated together. Deleting only `productById::42` will not automatically update product lists, search results, or seller summaries.

There are three common approaches:

1. **Delete known dependent cache keys.** Requires clearly defining dependencies and key conventions.
2. **Clear the entire cache region or bump a namespace version** when it is hard to locate all related keys.
3. **Accept bounded staleness**, using short TTLs for less critical aggregated lists.

For example, detail data can be invalidated by exact ID; featured lists can have a 30-second TTL and reload periodically. The strategy must match product requirements.

### @Caching for multiple known entries

When the related caches and keys are known, they can be combined:

~~~java
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.CacheEvict;

@Caching(evict = {
    @CacheEvict(cacheNames = "productById", key = "#id"),
    @CacheEvict(
        cacheNames = "productSummaryById",
        key = "#id"
    )
})
public void refreshProductCaches(Long id) {
    // Method responsible for the appropriate business operation.
}
~~~

The snippet above illustrates multiple-invalidation syntax. It does not automatically guarantee post-commit deletion or deletion of cache keys the application has not listed. For data requiring transactional synchronization, attach the operation to the post-commit/outbox flow.

### Be cautious with allEntries

~~~java
@CacheEvict(cacheNames = "productList", allEntries = true)
~~~

`allEntries = true` requests deleting every entry in the cache region. With Redis, the cost and clearing mechanism depend on the cache writer/configuration, number of keys, and how keys are scanned. When a region is very large or multiple applications share Redis, bulk deletion can create significant load.

Prefer specific keys or an appropriate namespace/version design when possible.

## 13. Distinguishing cache update, invalidate, and write-through/write-behind

These terms are often conflated:

| Pattern | Read | Write | Key point to note |
| --- | --- | --- | --- |
| Cache-aside | App reads cache; on miss reads DB and caches | App proactively evicts/puts | Common with Spring Cache |
| Read-through | Cache component loads from source on miss | Depends on design | Capability depends on cache system |
| Write-through | Write path updates source of truth and cache per defined mechanism | Synchronous write via responsible layer | Does not automatically guarantee a DB + Redis transaction |
| Write-behind/write-back | Cache accepts writes and flushes to another source later | Asynchronous | Risk of data loss if queue/durability mechanisms are insufficient |
| Invalidate-on-write | Read via cache | Write DB then delete old copy | Next read rebuilds cache |

**`@CachePut` does not automatically turn every application into a write-through system with a transaction spanning the database and Redis.** It is simply a mechanism to put a method's result into the cache via Spring's proxy.

Similarly, using Redis as write-behind does not solve durability on its own. If mandatory writes are required, you must define the source of truth and mechanisms for guaranteed delivery, retries, event ordering, and recovery.

## 14. Wrong write ordering can create stale data in the cache

### Case A: updating Redis before the database

~~~text
T0  Redis PUT price=120
T1  Client reads Redis -> 120
T2  Database transaction rolls back -> authoritative price is still 100
T3  Redis still holds 120
~~~

The price in the cache may never have existed in the source of truth. Therefore, if the database is the source of truth, avoid treating pre-commit cache operations as evidence that a business change succeeded.

### Case B: commit finishes but evict fails

~~~text
T0  Database commits price=120
T1  Redis connection error, evict fails
T2  Client reads Redis price=100
T3  TTL expires, Redis removes old entry
T4  Client reloads price=120
~~~

This is why **stale data tolerance** must be defined. If an old price is acceptable for at most a few minutes, TTL can act as a bounding measure. If it is strictly unacceptable, TTL alone is insufficient.

### Case C: two concurrent updates write the cache out of order

~~~text
Writer A: DB commits version 7, price=110
Writer B: DB commits version 8, price=120

Writer B: cache.put(price=120, version=8)
Writer A: cache.put(price=110, version=7)  <-- runs late

Redis ends up with: version 7, even though DB is already version 8.
~~~

Just because each PUT operation is atomic in Redis does not mean **cache write order matches database commit order**. A value can be overwritten by an older event.

Options to consider:

- Invalidate instead of writing a snapshot from an old callback.
- Write to the cache with an atomic version comparison, allowing only newer versions.
- Versioned keys when the application can obtain an authoritative version.
- Use a processing flow ordered per entity.
- For data requiring strong consistency, read directly from the source of truth.

Each measure requires a specific contract and race-condition testing. Simply adding a `version` field to a DTO does not automatically solve the problem.

## 15. Races even when only invalidating after commit

A subtle scenario:

~~~text
Reader A                      Writer B                 Redis/DB
--------                      --------                 --------
Cache MISS ------------------------------------------> Key missing in Redis
Read DB version 7 -----------------------------------> DB returns version 7
                              Write version 8
                              COMMIT
                              EVICT key -------------> Redis deletes key
Reader A PUT version 7 ------------------------------> Redis contains version 7
~~~

Even though Writer B evicted **after commit**, Reader A can still load the old value into the cache **after the eviction**. This happens when Reader A's cache fill stretches across Writer B's update.

Hence, post-commit invalidation is a very useful strategy, yet **not a proof of linearizable consistency** for all concurrent reads and writes.

Options when this race matters:

- Bound the TTL and accept a stale window with a known upper limit.
- Use version as part of the key, with a reliably determined source version.
- Only cache a snapshot if its version is not older than the cache/source state checked by an appropriate atomic operation.
- Serialize access per key with a designed synchronization mechanism, paying attention to distributed behavior.
- Read the source of truth for sensitive decisions.

A design with tight guarantees must consider the entire **cache miss -> read DB -> populate Redis** lifecycle, not only the update path.

## 16. TTL, eviction, and invalidation are different

These three terms can appear together but mean different things.

| Concept | Trigger | Goal |
| --- | --- | --- |
| TTL expiration | The cache entry's lifetime has elapsed | Limit lifetime |
| Cache invalidation | The application knows underlying data has changed | Remove outdated copy |
| Redis memory eviction | Redis needs to free memory per `maxmemory-policy` | Manage memory limits |

For example, Redis automatically removing an entry due to a 5-minute TTL does not prove the database just changed. And when Redis evicts a key due to memory pressure, that is not a business event saying "the product was updated" either.

Do not design business update workflows based solely on Redis `expired` or `evicted` events. Keyspace notifications over Pub/Sub can arrive late or be missed when listeners are offline; cache misses must have a path to read the source of truth.

### TTL is a last-resort safeguard, not immediate invalidation

If the requirement is "a changed price must be visible within 1 second," a 5-minute TTL will not meet it. If the requirement is "recommended articles can be roughly 1 minute stale," a 60-second TTL may be appropriate.

TTL should reflect **staleness tolerance**, change frequency, source read cost, and traffic. Do not pick a TTL just because a configuration value looks common.

## 17. Evaluating consistency by data type

Not all data needs the same strategy.

| Data type | Correctness criticality | Implementation direction |
| --- | --- | --- |
| Product catalog | Tolerates short-term update delay | Cache-aside + invalidation + TTL |
| Recommended articles list | Can be a few minutes stale | TTL and lazy rebuild |
| Displayed price | Must define acceptable staleness | Evict/put after commit; verify at checkout |
| Inventory | Must not oversell | Reservation decisions at authoritative source/atomic op; cache only assists display |
| Account balance | High correctness required | Do not rely on cache for transfer decisions |
| Sensitive access permissions | Usually needs fast effect | Check authoritative source, version/revocation |
| Dashboard reports | Can be eventually consistent | Aggregated cache with TTL, batch refresh |
| Shipping status | Accepts a defined delay | Event-driven invalidation + fallback TTL |

An API can use a cache to display estimated stock, while `POST /reserve` must check and decrement inventory at the authoritative place atomically. Seeing "2 left" on a page does not mean the system is allowed to sell 2 items without re-checking.

## 18. When to invalidate, when to overwrite the cache?

### Prefer invalidation if data has multiple representations

For example, changing a product's price can affect:

~~~text
Product detail
Product list by category
Price-range filter results
Recommended products
Cart total value
Projected revenue stats
~~~

Recomputing every view immediately during the update request can be complex and error-prone. Invalidate the directly known views, use TTL for remaining views, or offload rebuilding to a worker based on designed dependencies.

### Prefer update if the new payload is clear and reloading is very expensive

For example, caching details of a small configuration written by the service itself. After commit, the confirmed snapshot can be placed directly into the cache, avoiding a cache miss.

However, when multiple writers update concurrently, consider versions and cache update ordering. A naive `cache.put` can let an older record overwrite a newer one if callbacks run out of order.

### Mix strategies intentionally

A real system might do:

~~~text
After updating Product#42:
  - productById::42      -> evict
  - featuredProducts     -> evict
  - productList::*       -> short TTL, refresh on demand
  - productSearch        -> sync via separate index pipeline
~~~

Every cache in the application does not have to use the exact same update method. What matters is having a **data dependency map** or clear convention for each cache region.

## 19. Redis and Spring Cache are not the same abstraction layer

Spring Data Redis has both direct Redis operation APIs and Spring Cache integration.

| API layer | Examples | Responsibility |
| --- | --- | --- |
| Spring Cache abstraction | `@Cacheable`, `@CachePut`, `@CacheEvict` | Method-level caching rules |
| Spring Cache manager | `CacheManager`, `Cache` | Accessing caches by name/key |
| Spring Data Redis cache | `RedisCacheManager`, `RedisCache` | Implementing caches using Redis |
| Spring Data Redis data operations | `StringRedisTemplate`, `RedisTemplate` | Operating on keys, hashes, sets, sorted sets... |
| Authoritative data source | `JpaRepository`/database or other authoritative system | Determining business state |

If the application caches via `@Cacheable(cacheNames="productById")`, the safe way to delete an entry is through the same abstraction:

~~~java
Cache cache = cacheManager.getCache("productById");
if (cache != null) {
    cache.evict(42L);
}
~~~

Do not guess the Redis key and call:

~~~java
stringRedisTemplate.delete("productById::42");
~~~

unless you explicitly control `RedisCacheConfiguration`, key prefixes, and key conversion. The cache manager can alter prefixes, serialization, or namespaces so that the actual key differs from what the author guessed.

### Cache keys are part of the contract

If one place caches with `key="#id"` while another evicts with `key="#product.id"`, ensure the actual values are equivalent. When keys include tenant, locale, currency, or version, it gets even trickier:

~~~java
@Cacheable(
    cacheNames = "productByTenant",
    key = "#tenantId + ':' + #productId"
)
public ProductView getProduct(String tenantId, Long productId) {
    // ...
}
~~~

During invalidation, the exact contract `tenantId:productId` must be used. Do not delete just `productId` and assume tenant-scoped entries were invalidated.

Omitting tenant from the cache key in a multi-tenant system can return data across tenants. That is a data-isolation bug, not merely a performance bug.

## 20. Serializer configuration and cache schema changes

Redis stores bytes; DTO values must be serialized and deserialized. When using `RedisCacheManager`, align on:

- Key format, cache prefix, and namespace.
- Value serializer.
- Cached DTO types and fields.
- TTL, null caching, and data size.
- How to handle an application version failing to read a value written by another version.

Example:

~~~text
App v1 cache:
  productById::42 -> { "id": 42, "price": 100 }

App v2 expects:
  productById::42 -> { "id": 42, "price": 120, "currency": "VND" }
~~~

If v2 requires `currency` and old cache entries lack it, one of the following is needed:

1. Backward-compatible DTO design or safe default values.
2. Bump the namespace/cache name: `productByIdV2`.
3. Invalidate the old cache during a controlled rollout.
4. Use appropriate TTLs and migration rollout steps.

Updating a serializer does not automatically convert old bytes. When a deserialization error occurs, the application needs a policy to fail-open on cache (read database) or fail-closed depending on risk; it should not break the entire business operation just because an optional cached copy became incompatible.

### Storing sensitive data in cache

Even though Redis is a cache, data still resides on the network and in system memory. Avoid directly caching credentials, secret tokens, or unnecessary personal data. When sensitive information must be cached, enforce access control, encryption where appropriate, TTLs, and tenant isolation rules.

## 21. When there are multiple application instances

With three Spring Boot instances sharing one Redis Cache:

~~~text
App A ----+
          |
App B ----+------ Redis Cache ------ Database
          |
App C ----+
~~~

An invalidation executed on the shared Redis causes all three instances to miss on the next request if they only use Redis cache.

However, the system might also have an **L1 local cache** (e.g., Caffeine) in each JVM:

~~~text
App A: L1 local cache
App B: L1 local cache
App C: L1 local cache
              |
              v
          Redis L2
              |
              v
          Database
~~~

If only Redis L2 is cleared, the L1 local caches can still hold old data. Invalidation rules are needed for **every cache tier**. Redis Pub/Sub can be used to broadcast notifications to instances, though Pub/Sub does not retain messages for replay when an instance is offline.

If strong guarantees are required, use TTL/versioning for L1 or durable invalidation and reconciliation, rather than assuming every notification is received.

## 22. Event-driven invalidation and transactional outbox

When a Product changes, the service can emit an event such as `ProductChanged(productId=42, version=8)`. A consumer receives the event and deletes the Redis cache or rebuilds the read model.

~~~text
Authoritative write transaction
         |
         +--> UPDATE product
         |
         +--> INSERT outbox_event
         |
         v
       COMMIT
         |
         v
Worker reads outbox with retry
         |
         v
Redis EVICT / UPDATE
         |
         v
Mark event processed
~~~

**Transactional outbox** closes the window where "the database commits successfully, but the application crashes before sending the event" by persisting the work record in **the same database transaction**.

Points to note:

- A worker may receive and process the same event multiple times; key-based invalidation is usually idempotent, whereas put requires version control.
- Outbox requires retries, backlog monitoring, and not deleting work records before processing is confirmed.
- If an entity changes multiple times, events may reach consumers out of desired order; ordering/versioning must be considered.
- Data read from a lagging replica or read model may not yet reflect the latest commit at invalidation time.
- An offline system cannot refresh the cache on time; the architecture must define allowed staleness and fallback paths.

Outbox makes the work **recoverable**, yet does not turn the database and Redis into a single distributed transaction. For operations requiring absolute correctness, still check the source of truth or use an appropriate consistency protocol.

## 23. Cache stampede after invalidation

When a hot cache key is deleted, many concurrent requests can all see a cache miss:

~~~text
Evict productById::42
         |
         +--> Request A: MISS -> query DB
         +--> Request B: MISS -> query DB
         +--> Request C: MISS -> query DB
         +--> Request D: MISS -> query DB
         +--> Request E: MISS -> query DB
~~~

This phenomenon is often called a **cache stampede/thundering herd**.

Mitigations:

- Choose sensible TTLs with jitter to prevent many keys from expiring simultaneously.
- Warm up ultra-hot keys in a controlled manner after invalidation.
- Limit how many concurrent requests can load the same key.
- Use single-flight/coalescing at an appropriate layer.
- Use a time-bounded Redis lock when truly needed, with fallback and safe lock release designed in.
- Optimize authoritative source queries, batching, and connection pools.

### Does @Cacheable(sync = true) solve everything?

~~~java
@Cacheable(
    cacheNames = "productById",
    key = "#id",
    sync = true
)
~~~

`sync = true` asks the cache layer to synchronize value computation for the same key. Exact effectiveness depends on the cache provider and configuration. **Do not assume it acts as a full distributed lock across multiple JVMs or guarantees every instance queries the DB only once.**

Verify the behavior of `RedisCacheManager` and the cache writer in your application's version before relying on this mechanism to prevent stampedes at distributed scale.

## 24. Negative caching and when data is newly created

An API looking up products by ID can return "not found". To reduce repeated database queries for non-existent IDs, negative results can be cached briefly (negative caching).

But if "not found" is cached for too long:

~~~text
T0  GET product#99 -> does not exist -> cache NOT_FOUND
T1  CREATE product#99 in DB
T2  GET product#99 -> stale NOT_FOUND cache
~~~

The new key already exists in the source of truth, yet the cache hides it from users.

Solutions:

- Set a shorter TTL for negative results than for existing results.
- When creating an entity, invalidate the corresponding key.
- Distinguish "does not exist" from "database error"; do not cache system errors as `NOT_FOUND`.
- Do not cache results from a lagging replica in a way that causes prolonged staleness.

`disableCachingNullValues()` in `RedisCacheConfiguration` avoids one class of errors when returning `null`; however, if the application returns a wrapper or `NotFoundResult` object, it can still be cached as designed. Define an explicit negative contract.

## 25. Cache updates can fail after the source of truth has committed

Example:

~~~text
1. Database COMMIT succeeds.
2. Application calls cache.put(newValue).
3. Redis times out.
4. API returns an error to the client.
~~~

The client may interpret the update as failed and resend it, even though authoritative data already changed. This is a **partial failure** between primary storage and the cache.

When cache is an optional optimization, some systems choose:

- Writing the source of truth is the primary business outcome.
- Cache invalidation/update runs best-effort, with retries/metrics.
- On cache error, read from the database.
- TTL bounds how long stale entries persist.

For data that cannot be stale, raise the guarantee level via durable invalidation, read validation/versioning, or removing cache from the decision path. Do not blindly "ignore all Redis exceptions" if the application also uses Redis to store authoritative business state separate from the cache.

### CacheErrorHandler

Spring Cache has a customizable `CacheErrorHandler` mechanism to decide how cache errors are handled across `get`, `put`, `evict`, and `clear`. You can choose appropriate responses depending on error type and the cache's role.

Even when allowing requests to proceed on cache errors, log and emit metrics to detect when Redis stops meeting expectations—especially when failed invalidation increases stale reads.

## 26. Testing the invariants of a cache strategy

Caching logic can "work fine" in single-threaded tests and still break under concurrent requests. Critical paths should be tested with real data and real Redis, separating business-logic tests from consistency tests.

| Scenario | Expected outcome |
| --- | --- |
| First cache miss | Read database and store snapshot with TTL |
| Cache hit | Return matching cached snapshot |
| Update database then evict | Next read loads the new value |
| Database transaction rollback | Uncommitted data never appears in cache |
| Redis fails during evict | Alerts/metrics recorded and fallback mechanism triggers |
| Two writers update same ID | Stale cache value is not treated as the source of decision |
| Missing reader races with writer | Strategy handles the stale window per requirements |
| Cache entry TTL expires | API reloads from source of truth |
| Cache schema changes | Compatible migration or namespace versioning exists |
| Entity created after negative cache | Negative key is invalidated or expires promptly |
| Multiple instances | Invalidation reaches all relevant cache tiers |
| Different tenants with same product ID | Cache is never cross-read between tenants |

### Basic flow test example

Pseudocode:

~~~java
// Arrange
database.save(new Product(42L, "Book", price("100")));
cache.evict(42L);

// Act: first read populates the cache
ProductView first = queryService.getById(42L);

// Update authoritative data and invalidate after commit
commandService.changePrice(42L, price("120"));

// Assert: subsequent read receives new data
ProductView latest = queryService.getById(42L);
assertThat(latest.price()).isEqualByComparingTo("120");
~~~

This is **flow-testing pseudocode**, not a copy-pasteable runnable test class: entity constructors, `price` helpers, and transaction boundaries must follow the real application.

To prove post-commit consistency, use integration tests with a real test database and Redis, coordinating two transactions/threads to reproduce races. Mocks that only verify `cache.evict` call counts do not prove values are correct after a commit.

## 27. Diagnosing when stale cache data refuses to disappear

A structured investigation sequence:

**Step 1 — Verify the source of truth.** Check whether the database truly committed the new value or rolled back. Determine whether reads are hitting a replica lagging behind the primary.

**Step 2 — Verify the cache key.** Check `cacheNames`, the `key` expression, prefix, tenant, version, and serializer. Do not assume the Redis key matches the literal Java key.

**Step 3 — Check the invalidation path.** Did the call go through the Spring AOP proxy? Is there self-invocation? Did the `AFTER_COMMIT` event run? Were there Redis connection or listener errors?

**Step 4 — Check concurrency.** Did a cache-missing request read old DB data and write cache after invalidation? Did an old event/callback overwrite the new snapshot via `cache.put`?

**Step 5 — Check other layers.** Is there Caffeine L1, a CDN, reverse proxy, browser cache, or HTTP caching outside Redis?

**Step 6 — Check TTL and schema.** Does the entry have the right TTL, are reads renewing TTL under some policy, or is the data incompatible with the serializer?

**Step 7 — Confirm business requirements.** Does the data strictly require strong consistency, or is short-lived staleness acceptable?

Useful Redis inspection commands in an appropriate environment:

~~~bash
redis-cli TTL 'productById::42'
redis-cli PTTL 'productById::42'
redis-cli EXISTS 'productById::42'
redis-cli INFO stats
redis-cli INFO memory
~~~

These commands are only useful if you know **the exact physical key** generated by `RedisCacheManager`; prefix or serializer configuration can change the actual name. Do not use `KEYS *` routinely in production with large keyspaces; if scanning is required, consider batched `SCAN`.

## 28. Metrics for a cache strategy

To know whether a strategy actually helps, don't just check that "Redis is still up."

Meaningful metrics:

| Metric | Question to answer |
| --- | --- |
| Cache hit ratio | How many reads are served from cache? |
| Cache miss rate | How often must the source of truth be queried? |
| Redis GET/SET/DEL latency | Is the cache actually lowering overall latency? |
| Database read p95/p99 | Do post-invalidation stampedes slow down the DB? |
| Cache invalidation errors | Did any cache deletions fail? |
| Entry age / data version mismatch | How many copies are stale? |
| Redis memory usage / evictions | Are memory and `maxmemory` policy causing pressure? |
| Cache refill traffic | Are deploys/bulk invalidations causing DB bursts? |
| Outbox backlog | How many invalidation events remain unprocessed? |
| Stale read incidents | Are users seeing stale data beyond allowed bounds? |

Redis `keyspace notifications` and `expired_keys` do not tell you whether all cache entries were invalidated properly in sync with database changes. Combine metrics across the application layer, source of truth, and event processing.

### Logs with correlation ID and version

A useful log entry:

~~~text
event=product_cache_evicted
product_id=42
db_version=8
cache_name=productById
cause=product_updated
trace_id=...
~~~

Do not log full sensitive cache contents just to debug invalidation. IDs and versions are usually enough to correlate events.

## 29. Designing cache for multi-region or multi-Redis systems

When the application runs across multiple regions or has multiple independent Redis clusters:

~~~text
Region A               Region B
--------               --------
Spring A               Spring B
Redis A                Redis B
       \               /
        \             /
         Central database
~~~

After the database updates, deleting cache in Redis A **does not automatically delete** Redis B. If caches are replicated across regions, you need cross-region invalidation broadcast, versioning, or appropriate TTLs.

If a region suffers a network partition and receives events late, its cache may continue holding old data. Do not assume that just because all instances use "Redis" they share a single namespace and state.

When strong cross-region consistency is required, distributed latency and coordination mechanisms are much more complex; business-critical decisions should go back to the source of truth or use a purpose-built consistency protocol.

## 30. Case study: product price change

Suppose a system has:

~~~text
Database:
  products(id, name, price, version)

Redis cache:
  productById
  productList
  recommendedProducts

Flows:
  GET /products/{id}
  GET /products?category=...
  PATCH /products/{id}/price
~~~

Requirements:

- When an admin changes a price, the database must commit the new price.
- The product detail API should reflect the new price quickly.
- Product lists may lag by at most 30 seconds.
- Checkout must calculate using the valid price from the source of truth at order confirmation time.
- The system runs multiple Spring Boot instances.

A viable design:

1. **The database is the source of truth** for product prices and versions.
2. `productById` uses `@Cacheable` with a short TTL and evicts by ID after commit.
3. `productList` has a 30-second TTL; if dependencies are clear, proactively evict related list keys.
4. During checkout, do not treat the Redis snapshot price as final authority; determine the price from the database under transactional rules.
5. If invalidation must survive crashes, store an outbox event in the update transaction.
6. When events can arrive out of order, use versions or evict-only to avoid old snapshots overwriting newer ones.
7. Monitor cache miss rate, invalidation errors, stale reads, and database impact.

Diagram:

~~~text
PATCH price
    |
    v
Database transaction
  UPDATE product / version
  INSERT outbox event (if needed)
    |
    v
COMMIT
    |
    +--> Evict productById::42
    +--> Invalidate dependent views / TTL
    |
    v
GET /products/42
    |
    +--> MISS -> DB new version -> Redis -> API

POST /checkout
    |
    v
Verify price and conditions at source of truth
~~~

### Self-assessment questions

- If the cache fails while the DB is healthy, should the API keep reading the DB or reject requests?
- If one request is loading version 7 while a writer commits version 8, how do we prevent version 7 from persisting too long?
- If Redis A is evicted while Redis B in another region hasn't received the event yet, what delay is acceptable?
- If `ProductView` changes schema between two releases, how do we avoid old-cache deserialization errors?
- If a product appears in 50 lists, should we update 50 cache entries or invalidate/use TTL by group?
- If strict balance or inventory accuracy is required, should Redis cache decide transaction success?

These questions show that caching strategy is a **data-correctness decision**, not just a speed-optimization annotation.

## 31. Frequently asked questions

**After a successful database write, should I always use `@CachePut`?**

No. `@CachePut` fits when the method's return value is the exact new snapshot to cache. If there are multiple data representations or post-commit guarantees are needed, invalidation is often simpler. Both still require evaluating concurrency and Redis failures.

**Does `@CacheEvict` automatically roll back when the database rolls back?**

You cannot assume that from the annotation alone. When cache advice runs relative to transaction advice depends on configuration. For strict needs, use post-commit mechanisms and test against your application's transaction manager.

**On a cache miss, is the data guaranteed to be the newest?**

Not absolutely. Reading from a lagging database replica, an old transaction snapshot, or another read source can still return un-updated state. A cache miss only means no entry was found in that cache tier.

**Does a 5-minute Redis TTL mean prices can be at most 5 minutes stale?**

Only assuming entries are never unexpectedly extended, data is loaded from the right source, and Redis is the only caching layer. Staleness can also come from L1, CDNs, read replicas, or cache-fill races. TTL alone does not prove an end-to-end bound.

**Why does the cache contain stale data even after eviction?**

A reader might have read old DB state before commit and written the cache after the writer evicted. Or a stale update event ran late, or another cache layer wasn't cleared. Check the timeline, versions, and all cache tiers.

**Does `@CachePut` skip the method body when the key already exists?**

No. Unlike `@Cacheable`, it executes the method and puts the result into the cache subject to annotation conditions.

**Can Redis Pub/Sub invalidate every cache instance?**

It can serve as a best-effort signal, but Pub/Sub does not replay messages to disconnected instances. For strict needs, supplement with TTL, versioning, or durable events/outbox.

**Should all of Redis be cleared when one record changes?**

Usually no. Clearing everything causes mass cache misses, spikes database load, and affects unrelated data. Prefer deleting by key or known dependency groups.

**If Redis is the source of truth, is invalidation still needed?**

Possibly yes, if other views/caches are derived from the authoritative Redis state. Clarify which Redis keys hold authoritative state and which are merely copies.

**Should discounted prices be cached for fast checkout reads?**

Prices can be cached for display, but checkout should verify prices and promotion conditions against business rules at the authoritative source. Do not let a stale cache snapshot dictate the final amount charged.

## 32. Takeaways when designing with Spring Data Redis

- **The source of truth** authoritatively decides valid state; caches must be refreshable or rebuildable from it.
- **Cache updates** write fresh snapshots and keep subsequent reads fast, but must guard against old snapshots overwriting new ones.
- **Cache invalidation** deletes outdated entries so the next read reloads, often easier when data has many variants.
- **`@Cacheable`** supports the cache-aside read path, **`@CachePut`** writes results to cache, and **`@CacheEvict`** removes entries. Annotations do not automatically create atomic transactions across Redis and the database.
- **After commit** is a critical boundary when the database is the source of truth. `@TransactionalEventListener(AFTER_COMMIT)` orders work within a JVM, while outbox enables recovery if the app crashes.
- **TTL bounds entry lifetime**; it does not replace business-change invalidation and does not guarantee absolute freshness.
- **Concurrency, multiple instances, multiple cache tiers, and multiple regions** can introduce stale data even when individual Redis commands are atomic.
- **Critical transactional decision data** must be verified at the source of truth or an authoritative consistency mechanism.

## Official references

- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Framework – Transaction-Bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Redis – Key Expiration](https://redis.io/docs/latest/commands/expire/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Cache Eviction](https://redis.io/docs/latest/develop/reference/eviction/)
