# Transaction-Aware Cache Configuration and Cross-System Atomicity Limits

In a Spring Boot application using **Spring Cache with Spring Data Redis**, a business method may simultaneously update a database and write or delete cache entries. For example: changing a product's price in PostgreSQL and then updating the cache key so subsequent reads no longer return the old price.

A frequent misconception is that Spring's `@Transactional` manages the **database transaction**, whereas Redis cache is a separate storage system. If the cache is updated too early and the SQL transaction later rolls back, data in Redis may jump ahead of or contradict the database. Spring Data Redis provides `RedisCacheManager.transactionAware()` to coordinate cache operations with Spring transaction commits, yet this mechanism **does not create an atomic transaction spanning SQL and Redis**.

This lesson explains how to configure it, execution order, which operations are deferred until after commit, failure limits, and design strategies to achieve the right level of consistency.

## 1. The problem: updating the database and cache are two separate operations

Suppose the system stores a product as follows:

```text
PostgreSQL:
  products(id=42, name="Study Desk", price=900000)

Redis cache:
  productsById::42 -> { id: 42, name: "Study Desk", price: 900000 }
```

The currency in this example is VND. A user requests changing the price to `950000`. A typical service might do:

```java
@Transactional
public void changePrice(long id, BigDecimal newPrice) {
    Product product = productRepository.findById(id).orElseThrow();
    product.setPrice(newPrice);

    cacheManager.getCache("productsById")
            .evict(id);
}
```

This snippet simply illustrates the scenario; the active transaction manager here is the database transaction manager. If `evict` hits Redis **while the SQL transaction is still open** and SQL later fails, the cache gets cleared even though the database keeps the old price. Clearing cache on rollback does not always cause lasting corruption, yet causes unnecessary re-querying and can introduce race conditions.

The risk is higher when updating the cached **value** before SQL commits:

```text
T0  SQL transaction starts
T1  SQL updates product 42 price to 950000 (uncommitted)
T2  Cache writes productsById::42 = 950000
T3  Another SQL check throws RuntimeException
T4  SQL ROLLBACK; database price remains 900000

Result:
  Database = 900000
  Redis    = 950000  <-- wrong cached price
```

Reads via cache would then serve a price that never committed. Understanding how Spring coordinates cache operations with transaction lifecycles is essential.

## 2. Distinguishing components and transaction types

| Component | Role | Automatically manages transactions of the other resource? |
|---|---|---|
| `@Transactional` | Marks transaction boundaries on a method via Spring AOP | No |
| `JpaTransactionManager` or `DataSourceTransactionManager` | Manages commit/rollback for JPA/JDBC databases | Does not commit/rollback Redis |
| `CacheManager` | Creates and supplies `Cache` instances by name | Unaware of database transactions by default |
| `RedisCacheManager` | Implements Spring Cache on Redis | No built-in simultaneous commit with database by default |
| `RedisCacheManager.transactionAware()` | Defers supported cache operations until Spring transaction commits successfully | No distributed commit |
| `RedisTemplate.setEnableTransactionSupport(true)` | Integrates `RedisTemplate` operations with Spring transactions via Redis `MULTI`/`EXEC` | Does not create atomic SQL + Redis transactions |
| Transactional outbox | Persists sync intent in the same DB transaction for async worker processing | Provides retry/recovery path; accepts eventual consistency |

Three design questions must be separated:

1. **Does the database commit or roll back?** Decided by the database transaction manager.
2. **When do cache operations execute?** Decided by the Spring Cache interceptor, cache manager, and transaction-aware configuration.
3. **What if the database commits successfully yet Redis fails?** Requires a dedicated consistency, retry, or recovery policy; `@Transactional` does not handle it automatically.

## 3. Configuring a transaction-aware RedisCacheManager

To defer eligible cache operations until after the Spring transaction commits, configure `RedisCacheManager` with `transactionAware()`.

```java
package example.cache;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfiguration {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        RedisCacheConfiguration productCache =
                defaults.entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withCacheConfiguration("productsById", productCache)
                .transactionAware()
                .build();
    }
}
```

Meaning of options:

- `@EnableCaching` enables processing of annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`.
- `cacheDefaults(defaults)` sets the default configuration for un-overridden caches.
- `entryTtl(Duration.ofMinutes(10))` sets the default lifetime for cache entries.
- `withCacheConfiguration("productsById", ...)` sets a five-minute TTL for the example product cache.
- `disableCachingNullValues()` omits storing `null` values in the cache.
- **`transactionAware()`** enables supported Spring Cache operations to wait until the current transaction finishes successfully before hitting Redis.

This configures an explicit `CacheManager` bean. In applications relying on Spring Boot auto-configuration, verify that `@Cacheable` methods actually use **this exact bean**; if multiple `CacheManager` beans exist, verify which manager is selected.

### Difference between TTL and transaction-aware

TTL and transaction-aware solve two independent questions:

| Configuration | Question addressed |
|---|---|
| `entryTtl(5 minutes)` | At most how long does an entry in Redis remain valid unless replaced or deleted? |
| `transactionAware()` | At what point relative to a Spring transaction should cache update/delete commands run? |

TTL knows nothing about SQL rollbacks; transaction-aware does not guarantee cached values stay fresh indefinitely. In practice, you typically **combine** transaction-aware deferral with TTLs, invalidation policies, and stale-data recovery mechanisms.

### Serializers and namespaces

`RedisCacheConfiguration.defaultCacheConfig()` includes a default prefix convention containing the cache name, such as `productsById::42` when the generated key is `42`. Prefixes prevent caches with different names from colliding on keys, though you should inspect the active key generator and prefix configuration before checking Redis CLI.

Default cache values traditionally use Java serialization in Spring Data Redis; production systems often use JSON serializers or explicitly managed custom formats. Serializers must stay consistent across application versions, DTO classes, security policies, and rollback/migration plans. Choosing a serializer **does not substitute** for enabling `transactionAware()`.

## 4. Usage with @Cacheable, @CachePut, and @CacheEvict

Consider a service reading and updating product prices:

```java
package example.product;

import java.math.BigDecimal;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    public ProductView getProduct(long productId) {
        Product product = products.findById(productId).orElseThrow();
        return ProductView.from(product);
    }

    @Transactional(transactionManager = "transactionManager")
    @CachePut(cacheNames = "productsById", key = "#productId")
    public ProductView changePrice(
            long productId,
            BigDecimal newPrice) {

        Product product = products.findById(productId).orElseThrow();
        product.setPrice(newPrice);

        return ProductView.from(product);
    }

    @Transactional(transactionManager = "transactionManager")
    @CacheEvict(cacheNames = "productsById", key = "#productId")
    public void deleteProduct(long productId) {
        products.deleteById(productId);
    }
}
```

In this example:

- `ProductRepository` manages the product table via JPA/JDBC in the application.
- `ProductView` is a cacheable DTO; it must be compatible with the configured serializer.
- `@Cacheable` reads the cache first; on a miss, it executes the method to load from the database and may store the result.
- `@CachePut` always runs the method and requests updating the cache with the return value.
- `@CacheEvict` requests deleting the entry; by default eviction happens upon successful method completion.
- `@Transactional` uses the database transaction manager, assuming the actual bean is named `transactionManager`.

**Important:** this example shows API organization, not an automatic guarantee across every Spring AOP advice ordering. When `@CachePut`, `@CacheEvict`, and `@Transactional` appear on the same method, **interceptor ordering** determines when cache operations are requested relative to when the transaction opens and closes. Verify your actual advisor configuration if exact timing is critical; do not assume annotation placement in source dictates callback order.

### A cache hit means no database query

With `@Cacheable`:

```text
getProduct(42)
      |
      v
Spring Cache lookup
      |
      +-- HIT --> return ProductView from Redis
      |
      +-- MISS --> invoke real method
                        |
                        v
                    SQL SELECT
                        |
                        v
                    store result in cache
```

If the cache already holds the entry, the underlying method may not run. Therefore, placing `@Transactional` on the read method itself alongside `@Cacheable` should not be assumed to open a SQL transaction on every call; it depends on advice ordering and whether the method actually executes.

## 5. What does a transaction-aware cache defer until after commit?

When an application interacts with a cache decorated to be transaction-aware, Spring Cache can register callbacks via **transaction synchronization**. For supported operations such as `put`, `evict`, and `clear`, the cache side effect is deferred until the **after-commit** phase if an eligible Spring transaction is active.

Illustrative flow for `changePrice(42, 950000)`:

```text
HTTP request
      |
      v
Spring transaction (database)
      |
      +--> SELECT product 42
      +--> UPDATE price = 950000
      |      (SQL not yet committed)
      |
      +--> Spring Cache requests PUT/UPDATE
      |      (transaction-aware cache manager defers it)
      |
      v
Database COMMIT succeeds
      |
      v
Spring afterCommit callback
      |
      v
Redis cache PUT product 42 = 950000
```

If an unchecked exception before commit triggers SQL rollback:

```text
New SQL UPDATE
      |
      v
RuntimeException
      |
      v
DB ROLLBACK
      |
      v
After-commit cache PUT is skipped
```

This is the primary value of `transactionAware()`: it prevents many cases where the cache reflects a database change that **never committed**.

### What if there is no active Spring transaction?

A transaction-aware cache is not a blanket "always defer" command. If no active transaction synchronization context exists when a cache operation is called, the operation normally executes **immediately**.

This commonly occurs when:

- The method is not called through a Spring proxy, e.g., self-invocation.
- Cache writes run on another thread spawned via `@Async` or `CompletableFuture` lacking the transaction context.
- The cache write path runs inside a flow that never opens a database transaction.
- The operation executes before the `@Transactional` interceptor starts or after the transaction has ended.
- A different `CacheManager` without `transactionAware()` is used.

Always examine the **actual runtime context of the cache call**, not merely annotations written on classes.

## 6. Not every Cache operation can be deferred

Distinguish two groups of API methods:

| Operation group | Behavior in transaction-aware cache |
|---|---|
| `put(key, value)` | Can be deferred until after commit |
| `evict(key)` | Can be deferred until after commit |
| `clear()` | Can be deferred until after commit |
| `get(key)` | Performs immediate cache lookup; does not become a SQL snapshot read |
| `putIfAbsent(key, value)` | Per Spring `TransactionAwareCacheDecorator` contract, cannot simply defer to after-commit; inspect immediate-operation semantics |
| `evictIfPresent(key)` | Cannot be assumed to defer like `evict`; immediate return value has specific semantics |
| Async APIs, loaders, and custom writers | Check individual contracts rather than extrapolating from `put`/`evict` |

Why: `putIfAbsent` must report immediately **whether a value already existed**, and `evictIfPresent` confirms immediate state at call time. Deferring completely until after commit would make it impossible to return an accurate immediate answer to the caller.

Nor does `transactionAware()` turn multiple cache-related Redis commands into a single atomic operation on the Redis server. Operations like clearing an entire cache may span multiple commands/keys; atomicity within Redis depends on the cache writer and specific commands.

## 7. Difference between RedisCacheManager.transactionAware() and RedisTemplate transaction support

Spring Data Redis has two mechanisms easily confused:

### 7.1. Transaction-aware Spring Cache

```java
RedisCacheManager.builder(connectionFactory)
        .transactionAware()
        .build();
```

Core mechanism: **defers supported cache mutations until after the Spring transaction commits successfully**.

- No Redis write/delete command is sent at the moment application code calls `cache.put(...)`.
- When the database rolls back, the after-commit callback does not run.
- Once the database commits, the callback sends the cache command to Redis.
- A Redis failure inside the callback **does not undo the already-committed SQL transaction**.

### 7.2. RedisTemplate transaction support

```java
StringRedisTemplate template =
        new StringRedisTemplate(connectionFactory);

template.setEnableTransactionSupport(true);
```

Core mechanism: when the template runs inside an eligible Spring transaction, it can bind a Redis connection using `MULTI`/`EXEC`, queuing operations and executing/discarding them in sync with the transaction lifecycle.

- Targets **`RedisTemplate` operations**.
- Can alter read semantics mid-transaction because writes are queued.
- Does not automatically configure Spring Cache on a separate `RedisCacheManager` bean.
- `MULTI`/`EXEC` does not create an atomic commit with SQL.

### 7.3. Direct comparison

| Criterion | Cache `transactionAware()` | RedisTemplate `enableTransactionSupport=true` |
|---|---|---|
| Primary API | `@Cacheable`, `@CachePut`, `@CacheEvict`, `Cache` | `RedisTemplate`, `StringRedisTemplate` |
| Core mechanism | Defers `put`/`evict`/`clear` until after-commit | Queues Redis ops via `MULTI`/`EXEC` synchronized with Spring |
| Suited for | Cache-aside, cache invalidation | Specific Redis command groups with transactional needs |
| Atomic with database? | No | No |
| Additional considerations | Cache advice order, TTLs, mid-transaction cache reads | Queued command returns, reading outside queue, Redis `DISCARD` and `EXEC` |
| Interchangeable? | No | No |

A project can use both for different purposes, provided you track **which bean and call path** uses which mechanism. Enabling transaction support on `StringRedisTemplate` does not make `RedisCacheManager` cache operations use that connection or share those semantics.

## 8. What does @Transactional guarantee and what does it not?

Suppose a Spring service manages transactions via `JpaTransactionManager`:

```java
@Transactional(transactionManager = "jpaTransactionManager")
public ProductView changePrice(long id, BigDecimal newPrice) {
    // Update JPA entity
    // and trigger cache PUT/evict.
}
```

`JpaTransactionManager` manages `EntityManager` and the corresponding database resource. It does **not** become a Redis transaction manager simply because Redis cache lives in the same Spring application.

With a transaction-aware `RedisCacheManager` registering callbacks, the ideal sequence is:

1. Spring starts the database transaction.
2. Application modifies the entity; Spring Cache schedules the cache operation if routed through the right interceptor/manager.
3. Database commits successfully.
4. Spring runs the after-commit callback to update or evict the cache.

Yet there is no shared transaction coordinator guaranteeing **either both SQL and Redis commit or neither changes**.

### Two types of consistency to distinguish

**Single-system consistency:** The database can use SQL transactions to preserve invariants across related rows. Redis provides atomic single commands and certain mechanisms across keys.

**Cross-system consistency:** Redis values must reflect committed database changes. This requires coordinating **two independent resources**. Transaction synchronization provides a favorable ordering; it does not create an atomic distributed commit.

## 9. The failure window after SQL commits and before cache updates

This is the most critical limitation:

```text
T0  @Transactional starts
T1  UPDATE products SET price = 950000 WHERE id = 42
T2  Database COMMIT succeeds
T3  [Process crash / Redis timeout / network drop]
T4  Post-commit cache PUT or EVICT fails to complete

Database:
  product 42 has price 950000

Redis:
  may still hold price 900000
  or cache was not cleared as expected
```

If Redis is a cache and the database is the source of truth, the system can still recover via TTL, a subsequent invalidation, retries, or rebuilds. During the interim window, however, users may see stale data.

What `@Transactional` cannot do:

```text
DB COMMIT succeeds
     |
     +--> Redis fails
                |
                v
     "Automatically roll back DB to old price"
```

A committed database transaction cannot be rolled back simply because a Redis callback failed. An exception thrown post-commit may even propagate an error to the caller even though SQL already committed. If the client sees an error and retries, the application must ensure the operation is safe to repeat.

### Failure scenario matrix

| Scenario | Database | Redis cache | Conclusion |
|---|---|---|---|
| Method succeeds, no infra failures | Committed | After-commit PUT/EVICT succeeds | Data reaches expected state |
| Exception forces DB rollback before commit | Rolled back | Deferred mutation skipped | Prevents caching uncommitted data |
| Redis unavailable after DB commit | Committed | Stale entry may remain | Needs recovery mechanism |
| Process dies after DB commit, before callback | Committed | No guarantee callback ran | In-memory callbacks are not durable |
| Redis updates, response lost | Committed | May have updated unknown to caller | Retries require idempotency or reconciliation |
| Concurrent transactions update same key | Commit in some order | Cache mutations may arrive out of order | Risk of old cached value overwriting newer one |
| Cache deleted, reader reads DB before other tx commits | Reader sees old committed price | May reload old price | Evaluate race conditions and re-eviction |

Enabling transaction-aware caching largely resolves **pre-commit rollback cases**, yet does not eliminate post-commit divergence or concurrent-writer races.

## 10. @CachePut vs. @CacheEvict: which should you choose?

Both approaches to updating cache after database changes serve distinct goals.

### 10.1. Updating with the new value via @CachePut

```java
@Transactional(transactionManager = "transactionManager")
@CachePut(cacheNames = "productsById", key = "#productId")
public ProductView changePrice(long productId, BigDecimal price) {
    Product product = products.findById(productId).orElseThrow();
    product.setPrice(price);
    return ProductView.from(product);
}
```

**Advantage:** once the cache put succeeds, subsequent reads hit Redis immediately without querying the database.

**Risk:** if two updates race on the same key or a callback arrives late, the cache may be overwritten with an older DTO. If database triggers or other transactions also modify fields, a DTO built before commit may not reflect the final committed database state.

### 10.2. Deleting the entry to reload canonical data via @CacheEvict

```java
@Transactional(transactionManager = "transactionManager")
@CacheEvict(cacheNames = "productsById", key = "#productId")
public void changePrice(long productId, BigDecimal price) {
    Product product = products.findById(productId).orElseThrow();
    product.setPrice(price);
}
```

**Advantage:** once eviction succeeds, the next request reads committed data from the database and repopulates the cache; no need to assemble the new payload inside the cache-writing command.

**Risk:** the eviction callback can still fail after SQL commit. A concurrent reader may read and cache stale data if reading from a lagging database replica. Systems needing strong read consistency require additional race-handling policies.

### 10.3. Choosing by business characteristics

| Characteristic | `@CachePut` | `@CacheEvict` |
|---|---|---|
| Cache state after successful operation | Value returned by method | Entry deleted |
| Next read | Usually a cache hit | Usually cache miss then reload from source |
| Stale write risk | Yes, if delayed callback writes older value | Possible if eviction fails or refill races |
| DTO/serializer dependency | Must write properly formatted payload | Only needs the exact key to delete |
| Best suited for | Authoritative new value known, fast hit desired | Cache is a DB projection, miss-and-refill is acceptable |

For cache-aside setups with a database source of truth, **evict after commit** is usually easier to maintain than keeping two value updates in sync. Neither option in the table, however, provides cross-system strong atomicity by itself.

## 11. Cache lifecycle when @Cacheable is present

Adding `@Cacheable` introduces subtle states during active transactions.

### 11.1. Reading while an update transaction is in flight

```text
Request A                         Request B
  |                                  |
  |--- BEGIN SQL transaction         |
  |--- UPDATE product=950000         |
  |--- cache EVICT deferred          |
  |                                  |--- @Cacheable getProduct(42)
  |                                  |--- cache HIT price 900000
  |--- COMMIT                        |
  |--- Redis EVICT                   |
  v                                  v
```

At the instant Request B reads before A commits, `900000` is the valid **already-committed** value. Transaction-aware caching does not force B to see A's uncommitted edits.

### 11.2. Cache misses can load data at awkward moments

```text
Request A                          Request B
  |                                   |
  |--- UPDATE product, not COMMITTED  |
  |                                   |--- cache MISS
  |                                   |--- SELECT from DB
  |                                   |--- reads old price 900000
  |                                   |--- cache PUT old price
  |--- COMMIT                         |
  |--- EVICT after-commit             |
```

If B writes the old price before A evicts, A's eviction clears the stale entry immediately afterward. However, other interleavings, async retries, or delayed callbacks can leave stale state. Examine the entire source-loading path, not just one update method.

### 11.3. Reading from a database replica with replication lag

After the primary database commits, a cache-missing request may read from an un-updated read replica and push stale data back into Redis. Redis cache's `transactionAware()` **does not control database replication lag**.

For data needing read-after-write consistency, route reads briefly to the primary or apply versions/watermarks to prevent caching stale snapshots. That falls outside Redis-SQL atomicity, yet arises frequently in real deployments.

## 12. Spring AOP interceptor ordering can alter outcomes

`@Transactional` and cache annotations execute via Spring interceptors/proxies. When placed on the same method, one common nesting is:

```text
Cache interceptor
  -> Transaction interceptor
      -> Target service method
  <- Transaction commits
<- Cache interceptor handles result
```

In this nesting, a post-method cache put may be invoked **after SQL has already committed**; at that moment, the cache operation is no longer inside an active transaction to register an after-commit callback. The reverse nesting is:

```text
Transaction interceptor
  -> Cache interceptor
      -> Target service method
  <- Cache requests PUT (inside transaction)
<- SQL commits, after-commit callback runs PUT
```

`transactionAware()` is built for cases where cache operations are invoked inside an active transaction. **Never infer interceptor ordering purely from the order annotations appear in Java source.**

Guidelines:

- Place transaction boundaries on public service methods invoked via Spring proxies; avoid self-invocation that skips annotations.
- When guaranteed post-commit cache execution is needed, structure mutation paths explicitly with an after-commit listener or orchestration layer, while respecting callback durability limits.
- If customizing `order` on `@EnableCaching` or `@EnableTransactionManagement`, understand advice precedence and test its effects.
- `@Cacheable` can short-circuit methods on cache hits; skipping the method means an inner transaction interceptor may never run.
- With `@Async`, new threads do not automatically inherit the caller thread's Spring transaction context.

Syntactically valid annotations are only step one; **where cache operations occur relative to the transaction** determines semantics.

## 13. Transaction-aware caching does not mean Redis MULTI/EXEC

Another misconception is "enabling `transactionAware()` makes Redis run `MULTI` and queue every cache command." That is not the core model of transaction-aware Spring Cache.

```text
Spring transaction (SQL)
         |
         v
Cache put(key, value)
         |
         v
Transaction-aware decorator:
  "Wait for SQL commit before executing put"
         |
         v
SQL COMMIT
         |
         v
Redis writer executes cache command
```

There is no general requirement for Redis `MULTI`/`EXEC` in this flow. Consequently, Redis cache writer limitations still apply:

- A `clear()` may need to locate and delete many keys.
- A single cache operation may issue multiple commands depending on writer, batch strategy, and API called.
- The default Redis cache writer does not lock the entire cache for all operations; concurrent clients can still miss or refill simultaneously.
- A transaction-aware cache does not bundle keys across multiple cache names into one atomic Redis transaction.
- Redis Cluster shards cache entries across multiple hash slots and primaries.

If your application needs to **update two Redis keys atomically** within one slot, use Redis transactions or Lua scripting—not `CacheManager.transactionAware()`. And if it needs **Redis and the database** to commit atomically together, Redis transactions alone cannot solve it either.

## 14. Using @TransactionalEventListener(AFTER_COMMIT) for explicit timing control

One pattern publishes a domain event inside the database transaction and updates the cache after commit:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional(transactionManager = "transactionManager")
    public void changePrice(long id, BigDecimal price) {
        Product product = products.findById(id).orElseThrow();
        product.setPrice(price);

        events.publishEvent(new ProductChanged(id));
    }
}

public record ProductChanged(long productId) {}
```

Listener:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        Cache cache = cacheManager.getCache("productsById");

        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
```

`@TransactionalEventListener(phase = AFTER_COMMIT)` invokes the handler only for events whose matching transaction committed successfully. By default it does not run outside a transaction unless `fallbackExecution` is enabled.

**However, this event lives in application memory.** If the process dies after DB commit before the listener runs, there is no durable queue by default to replay the event. Additionally, `cache.evict` itself can fail if Redis is down. This controls **timing**, not guaranteed delivery.

If invalidation requests must survive crashes or outages and replay reliably, use a more durable strategy.

## 15. Transactional outbox: persisting sync intent in the same database transaction

A **transactional outbox** is commonly used when Redis holds critical read data and update/invalidation requests after database commits must not be lost.

Workflow:

1. Within the same SQL transaction, update source data and **insert an outbox row** containing event ID, entity ID, and version.
2. Commit the database. Business change and sync intent commit or roll back together.
3. A worker polls unprocessed outbox rows.
4. The worker sends cache delete/update operations to Redis.
5. On success, the worker marks the event processed; on failure, it retains it for retry.
6. Because redelivery is possible, cache updates must be idempotent or version-checked.

```text
              Request changePrice(42)
                         |
                         v
                 Database transaction
                         |
             +-----------+-------------+
             |                         |
             v                         v
       UPDATE products             INSERT outbox
             |                         |
             +-----------+-------------+
                         |
                    DB COMMIT
                         |
                         v
                 Durable outbox row
                         |
                         v
                  Worker / Publisher
                         |
                         v
                   Redis EVICT / PUT
                         |
                success ?     retry
                         |
                         v
                  Mark event handled
```

Conceptual example:

```java
@Transactional(transactionManager = "transactionManager")
public void changePrice(long id, BigDecimal price) {
    Product product = products.findById(id).orElseThrow();
    product.setPrice(price);

    outboxRepository.save(
            OutboxEvent.productChanged(id, product.getVersion()));
}
```

Worker processing:

```text
for each pending outbox event:
    claim event so other workers do not process it concurrently
    if Redis is available:
        invalidate cache entry or write new value
        mark success in outbox
    if Redis fails:
        record error, schedule retry with backoff
```

This is pseudocode outlining the workflow, not complete production code. A real implementation must address ownership claiming, lag, outbox table transactions, retries, dead letters, event ordering, metrics, and cleanup.

### Why does an outbox handle the failure window better than an after-commit callback?

Once SQL commits, **the Redis update intent exists as a durable database row**. If the process crashes or Redis experiences a temporary outage, a worker can still pick up and complete that request.

The trade-off is **eventual consistency** rather than instantaneous millisecond synchronization. Define maximum acceptable lag and monitor outbox lag.

### At-least-once delivery and idempotency

Suppose the worker deletes the cache entry successfully, then loses connectivity before setting `processed=true` in the outbox. The event will run again later. Deleting the same key again is generally harmless, whereas an event **blindly overwriting with an older value** after a newer event can make the cache stale.

Mitigations:

- Prefer invalidation over blind overwrites whenever architecture permits.
- Use event IDs and versions to detect duplicates or out-of-order delivery.
- If writing values to Redis, accept only newer versions; implement version comparison and writes in a way compatible with Redis/Cluster constraints.
- Cap retries or move failing events for manual handling without silently dropping events.
- Monitor lag from DB commit to Redis synchronization.

## 16. When is TTL enough, and when is an outbox needed?

Not every cache needs an outbox. Start from how critical the cached data is.

| Scenario | Suitable approach | Trade-off |
|---|---|---|
| Low-sensitivity product list cached for tens of seconds | Short TTL + cache-aside | Brief stale reads possible |
| Infrequent updates, minutes of staleness acceptable | After-commit evict + TTL | Failed eviction still recovers via TTL |
| Profile attributes cached while DB remains canonical | After-commit evict + monitoring/retry | Watch staleness requirements and privacy rules |
| Order status needing bounded-time sync | Outbox + idempotent worker, monitor lag | Higher complexity, but has retry durability |
| Balances, permissions, inventory used in critical invariants | Read/verify from canonical source on critical decisions; cache is advisory | Never treat cache as sole source of truth |
| Multiple systems writing cache and data | Unified writer/protocol, versions, event ordering | Requires cross-service coordination |

For instance, checking authorization solely against a long-TTL Redis entry after permissions were revoked creates security risks. Even an outbox has lag; when revocations must take effect immediately on every request, verify against the canonical source and define consistency SLAs before introducing caching.

## 17. Common mistakes with transactional Spring Cache

### 17.1. Enabling transactionAware yet still seeing cache change on SQL rollback

Check these possibilities:

- The cache call did not run inside an active transaction synchronization.
- The `@Transactional` method was called internally via `this.method()` and bypassed the proxy.
- Multiple `CacheManager` beans exist, and the method used a different manager.
- The method ran on an asynchronous thread lacking transaction context.
- The cache interceptor executed outside the actual transaction boundaries.
- Code performed low-level Redis operations or used a separate `RedisTemplate` bypassing the configured cache manager.

Do not immediately assume Redis broke transactions. Inspect transaction boundaries and the exact cache mutation path.

### 17.2. Confusing behavior with @CacheEvict(beforeInvocation = true)

Annotation:

```java
@CacheEvict(
        cacheNames = "productsById",
        key = "#productId",
        beforeInvocation = true
)
```

instructs the cache interceptor to trigger eviction **before calling the method** per annotation semantics. However, if the cache implementation is transaction-aware and the operation is requested inside a transaction, it may still be deferred by the cache decorator contract; if no active transaction exists, it may run immediately.

Therefore, do not casually combine `beforeInvocation=true` expecting "delete only after commit." Clarify your goal: delete even if the method fails, or delete only if SQL commits? Those are two different goals.

### 17.3. @Cacheable failing on self-invocation

Example:

```java
@Service
public class ProductFacade {

    public ProductView loadTwice(long id) {
        ProductView first = this.getProduct(id);
        ProductView second = this.getProduct(id);
        return second;
    }

    @Cacheable(cacheNames = "productsById", key = "#id")
    public ProductView getProduct(long id) {
        // Read database
    }
}
```

In standard Spring proxy mode, `this.getProduct(...)` is an internal call and **can bypass the cache interceptor**. The same applies to `@Transactional`. When AOP semantics are required, organize methods across beans and call through a Spring proxy instead of calling within the same object.

### 17.4. Do cache and database share the same transaction manager?

`@Transactional(transactionManager="transactionManager")` picks the named manager, typically the database manager. `RedisCacheManager` can **observe the transaction lifecycle** via Spring synchronization, which does not mean the SQL manager has become a Redis manager.

With multiple databases or transaction managers, select the right manager per operation. Transaction-aware does not unite disparate databases into one shared commit.

### 17.5. Post-commit callback fails

If the Redis callback fails:

- The database has likely already committed.
- The caller may or may not receive an exception depending on callback/error handling.
- Never blindly retry the entire SQL update just because a cache callback failed.
- Determine whether deleting the cache by ID recovers cleanly or a dedicated reconciliation event is needed.

The core principle is **decoupling business commit outcomes from cache sync outcomes** in error handling and observability.

### 17.6. Assuming multi-key @CachePut is atomic

One method can touch multiple cache names or multiple keys. Transaction-aware defers operations, yet does not guarantee all cache entries update together in a single Redis transaction. Readers may see partial updates, particularly in Redis Cluster.

When multi-key snapshot reads are required, consider versioned keys/snapshots or reading from the canonical source rather than assuming atomicity from annotations.

### 17.7. Failing to measure cache latency and errors

A system without metrics can look "healthy" until a Redis outage leaves prolonged stale data or hammers the database with misses. Track:

- Cache hit/miss ratios per cache name.
- Redis read/write/evict errors and timeouts.
- Database transaction latency.
- Time elapsed from commit to completed invalidation.
- Pending outbox events, retry counts, and max lag if using an outbox.
- TTLs and key counts per cache namespace.

Metrics do not replace recovery mechanisms, yet expose drift and measure blast radius.

## 18. Hands-on exercise: observing rollback and cache behavior

This lab assumes a **test database and Redis** with Spring Cache and `RedisCacheManager.transactionAware()` configured.

### Setup

Create a product:

```text
products:
  id    = 42
  price = 900000
```

Call `getProduct(42)` to warm the cache first. Use Redis CLI in the lab environment to inspect:

```bash
# Scans only the connected node. In Redis Cluster, inspect every primary.
redis-cli SCAN 0 MATCH 'productsById::*' COUNT 100
```

If using the default binary serializer, do not assume `GET` returns readable JSON. Check TTL/EXISTS without decoding payloads:

```bash
redis-cli EXISTS 'productsById::42'
redis-cli TTL 'productsById::42'
```

### Scenario A — Without transaction-aware

1. Start a `@Transactional` method updating the product price.
2. Inside the method, perform `Cache.put` or an immediate cache mutation.
3. Throw a `RuntimeException` before commit.
4. Re-read both database and cache after rollback.

Observe whether the cache holds the new price even though the database rolled back. Outcomes depend on timing and cache API invoked; the goal is observing cache operations executing **pre-commit**.

### Scenario B — With transaction-aware enabled

1. Use a `CacheManager` configured with `transactionAware()`.
2. Inside an active Spring transaction, invoke `cache.put(...)`.
3. Throw a `RuntimeException` to force database rollback.
4. Read the cache **outside** the transaction.

When properly deferred, the after-commit callback does not run, so no cache update occurs from the rolled-back transaction. Ensure the cache call actually runs inside the transaction rather than bypassing proxies/advisors.

### Scenario C — SQL commits, then Redis fails

1. In a test environment, make Redis unavailable right during the post-commit callback phase.
2. Observe database state, Redis error behavior, and cache contents.
3. Restore Redis and check whether any task retries automatically.
4. Without an outbox or reconciliation, observe how stale entries linger until TTL or a later invalidation.

This scenario demonstrates **why transaction-aware alone cannot guarantee cross-system synchronization**. Never simulate Redis outages in production.

### Scenario D — Concurrent updates to the same product

1. Transaction A updates price from 900000 to 930000.
2. Transaction B updates price to 950000 near the same time.
3. Observe commit order, cache mutation order, and final prices in both stores.
4. Evaluate whether the cached DTO can end up older than the committed database state.

If business rules forbid stale writes, add versioning or explicit reload/invalidation mechanisms. Races may not reproduce on every run; the exercise highlights possible interleavings.

## 19. Self-assessment questions

**1. Does enabling `@Transactional` on a service automatically roll back Redis cache changes?**

No. The annotation governs the selected transaction manager; Redis cache uses a separate write path. To defer cache operations with transactions, enable transaction-aware caching and ensure calls execute inside an active transaction.

**2. What does `RedisCacheManager.transactionAware()` guarantee?**

It allows deferring supported cache operations (`put`, `evict`, `clear`) until after a Spring transaction commits successfully when synchronization is active. It does not create distributed transactions.

**3. Why can PostgreSQL have committed while Redis still holds an old price?**

Because post-commit cache callbacks can fail, Redis may be offline, the process may crash, or updates may be missed. The database does not roll back when Redis encounters an error.

**4. Are `RedisTemplate.setEnableTransactionSupport(true)` and `RedisCacheManager.transactionAware()` the same?**

No. `RedisTemplate`'s support uses connection-bound Redis `MULTI`/`EXEC`, whereas transaction-aware Spring Cache defers cache mutations to after-commit.

**5. Why shouldn't `Cache.putIfAbsent` be assumed to always defer until after-commit?**

It must return whether a key existed immediately at call time. Immediate-return APIs cannot defer identically to ordinary `put`.

**6. If two transactions update the same product concurrently, do after-commit callbacks eliminate all stale writes?**

No. Callbacks or events can execute or arrive out of order, and caches can still be populated by stale reads. Address versions, ordering, invalidation, and source-of-truth guarantees.

**7. When is a `@TransactionalEventListener(AFTER_COMMIT)` listener insufficient?**

When events must be replayed after a crash or retried durably during a Redis outage. Listeners do not persist events durably by default.

**8. Why is an outbox worth considering for critical caches?**

Because sync events are saved inside the same database transaction as business changes, surviving process crashes for worker retries.

**9. Does TTL completely eliminate divergence between cache and database?**

No. TTL caps how long an entry can linger, yet during that TTL window the cache can still serve stale data.

**10. Do Redis Lua or MULTI/EXEC provide atomic commits across Redis and JPA?**

No. They provide atomicity/transactional guarantees within Redis's valid scope, not a distributed coordinator spanning two systems.

## 20. Takeaways for transactional cache design

- **`@Transactional` manages the selected transaction manager**, normally the database manager in JPA/JDBC applications.
- **`RedisCacheManager.transactionAware()` defers supported cache mutations until after-commit**, preventing many stale writes from rolled-back SQL transactions.
- **There is no atomic SQL + Redis commit guarantee**. Post-commit Redis failures still leave stale or missing cache entries.
- **Spring AOP ordering and actual call paths matter**: annotations mean nothing if operations run outside transactions, via self-invocation, or on different threads.
- **Cache reads, `putIfAbsent`, and immediate APIs have distinct semantics**; never assume everything defers like `put`/`evict`.
- **Transaction-aware caching differs from RedisTemplate `MULTI`/`EXEC`**, and does not combine multiple cache keys into a single atomic Redis transaction.
- **Pick cache policies matching consistency needs**: TTL + post-commit invalidation suffices for low-criticality caches; outbox/idempotency/versioning are necessary when recovery from failures is mandatory.
- **The database is usually the source of truth** in cache-aside architectures. For critical invariants like permissions or money, never let business decisions depend solely on a potentially stale cache entry.

The critical design question to answer is: **"If the database has committed yet no subsequent cache command succeeds, how will the system recover?"** Transaction-aware configuration reduces pre-commit update hazards; TTLs, retries, outboxes, and reconciliation handle the remaining risk.

## References

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheConfiguration`, TTLs, cache writers, and `transactionAware()`.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, keys, and proxy behavior.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): deferral of `put`, `evict`, `clear` and limits of immediate operations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, managers, propagation, proxies, and rollbacks.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases, and after-commit.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `RedisTemplate` and how Redis transactions integrate with Spring.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): limits of `MULTI`/`EXEC` and atomicity in Redis.
