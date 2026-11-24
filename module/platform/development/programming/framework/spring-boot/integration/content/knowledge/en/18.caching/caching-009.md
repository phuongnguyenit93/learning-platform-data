# TTL, Stale Data, and Coordinating Post-Transaction Cache Invalidation

## 1. Why Does Caching Become a Data Consistency Problem?

In **Spring Boot Integration**, a cache often sits between an API and data sources such as PostgreSQL, MySQL, HTTP services, Redis, or a read model consuming broker events. Caching reduces query counts and response times, while simultaneously introducing **an extra copy of data**. When the primary source changes, this copy can become stale.

Suppose the Catalog service returns details for product `P-101`:

1. A client reads the product; the application stores its name and price in Redis for 60 seconds.
2. Staff updates the price from 100,000 VND to 120,000 VND inside a database transaction.
3. The database commits successfully, yet Redis still holds 100,000 VND.
4. Another client calls the API during this window and may receive the old price.

Choosing a shorter **TTL** narrows how long stale data lingers, yet does not guarantee fresh data; simply putting `@CacheEvict` at the end of a `@Transactional` method is also insufficient without understanding **commit order, advice ordering, and failure modes**.

This lesson centers on three tightly coupled decisions: **how long data may stay stale**, **when the cache must be invalidated**, and **how to prevent failures or race conditions from serving wrong data after the database commits**.

~~~mermaid
flowchart LR
    API["Client"] --> Q["Spring Boot Query Service"]
    Q --> C[("Redis cache")]
    C -->|"hit"| Q
    Q -->|"miss"| DB[("Database: source of truth")]
    DB --> Q
    Q -->|"cache result"| C
    CMD["Command Service"] -->|"transaction update"| DB
    CMD -. "after commit: evict" .-> C
~~~

In this diagram, Redis acts solely as a read cache; **the database is the source of truth**. When reads carry stricter requirements (such as payment balances, access permissions, or sellable stock), do not default to serving stale data merely because caching speeds up queries.

## 2. Concepts to Distinguish

| Concept | Meaning | Consequence to evaluate |
| --- | --- | --- |
| **TTL (time to live)** | Duration an entry is retained before expiring per cache policy. | Entries can go stale during this window unless evicted/updated. |
| **Expiration** | Mechanism marking an entry expired so eligible reads stop serving it. | Does not mean the data has been refreshed. |
| **Stale data** | Cached value that no longer matches the committed state at the primary source. | Can return outdated prices, order statuses, or permissions. |
| **Cache hit/miss** | Whether a usable entry exists for a key. | High hits do not prove data is right; high misses do not prove performance is broken. |
| **Invalidation/eviction** | Deleting or marking one or more entries invalid. | Next query must reload; failed eviction leaves stale entries served. |
| **Cache-aside** | Application reads cache, fetches from source on miss, then populates cache. | Application must coordinate loading, updates, and invalidation. |
| **Write-through** | Cache updates tied to the data write path. | DB and cache still **do not share a single ACID transaction**. |
| **Read-your-writes** | After a successful write, the writer observes its own change. | Stale caches, replica lag, or delayed invalidation can violate this. |

**TTL is not a commit-confirmation mechanism.** It is an entry lifecycle policy. In cache-aside, if an eviction after DB commit is lost, the entry typically persists until TTL ends; yet you cannot guarantee data is never older than `TTL` when factors like slow-replica reloads, multi-tier caches, sliding expiration, or race conditions exist.

### 2.1. Expiration Timing Mechanisms

- **Expire-after-write:** entry expires after a fixed duration since it was written/refreshed. Suits cases requiring a clear upper bound from load time.
- **Expire-after-access:** expiration can extend on every read. A "hot" entry can survive far longer than intended after the source changes; avoid when staleness must be bounded relative to writes.
- **Absolute expiration:** expires at a fixed wall-clock instant, useful for data with known refresh schedules.
- **Soft TTL + hard TTL:** after soft TTL, stale results may be returned while refreshing in the background; hard TTL sets the cutoff beyond which stale data is never served. This is **stale-while-revalidate**, which must be built intentionally and is not default `@Cacheable` behavior.

Redis generally uses per-key TTL; in-memory cache libraries such as Caffeine support several expiration policies. Understand the exact TTL semantics configured at each tier.

## 3. Deciding Acceptable Staleness per Business Case

Do not apply one identical TTL across every cache in a project merely for convenience. Evaluate the impact of reading stale state per data type:

| Data type | Illustrative stale tolerance | Guidance |
| --- | --- | --- |
| Marketing copy, rarely changing catalog | Several minutes acceptable. | Relatively long TTL, evict on edits, protect against cache stampede. |
| Displayed catalog price | Brief lag may be acceptable per product contract. | Short TTL + post-commit evict; **checkout price verified at authoritative source**. |
| Delivery status | Event-driven updates with last-updated timestamp shown. | Event invalidation/update, monitor lag and `PENDING` states. |
| Sellable stock count | Never allow overselling past real stock; display count may be advisory. | Stock reservation must use transactions/coordination at the Inventory owner. |
| Recently revoked access permissions | Staleness causes security bugs. | Never rely on eventual cache if contract requires immediate revocation; perform authoritative checks or dedicated revocation design. |
| Balances, payments, credit limits | Stale values carry financial impact. | Never treat cache as transactional decision source; read primary source/control with transactions. |

Durations are for discussion only; establish a **freshness SLO** from business needs rather than technology defaults. A target might read: "After a price-change commit, 99.9% of queries see the new version within 2 seconds." To verify it, measure **commit-to-visible latency**, not cache hit ratio alone.

## 4. Cache-Aside and TTL in Spring Boot

Examples use **Java 17+, Spring Boot 3.x, Spring Cache, Spring Data JPA, and Redis**. The app reads products from a database and caches `ProductView` mapped into a DTO. With Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

To connect to Redis, configure `spring.data.redis.*` (URL/host, TLS, password, timeouts) per environment; this section assumes Redis is configured and secured appropriately. Example `application.yml`:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 60s
      cache-null-values: false
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

This is a **development configuration**. In production, use DNS hostnames, TLS, proper secret provisioning, and retry policies. `time-to-live: 60s` is the default Redis cache TTL here. You can specify per-cache TTLs:

~~~java
package com.example.integration.cache;

import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    RedisCacheManagerBuilderCustomizer ttlByCache() {
        return builder -> builder.withCacheConfiguration(
                "productById",
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofSeconds(30))
                        .disableCachingNullValues());
    }
}
~~~

Here `productById` has a **30-second** TTL specific to this cache. Other caches continue using Boot's default settings; review all customizers/serializers in your project to keep shared settings consistent. **Do not choose TTLs solely to reduce load**: determine acceptable staleness limits first, then measure performance at that TTL.

### 4.1. Query Service and Cache Key

~~~java
// ProductView.java
package com.example.integration.catalog;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.UUID;

public record ProductView(
        UUID id,
        String name,
        BigDecimal price,
        long version) implements Serializable {}
~~~

~~~java
// ProductQueryService.java
package com.example.integration.catalog;

import java.util.UUID;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productById", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView byId(UUID productId) {
        ProductEntity product = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId));
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice(),
                product.getVersion());
    }
}
~~~

Assume `ProductRepository` extends `JpaRepository<ProductEntity, UUID>` and `ProductEntity` exposes corresponding getters; `version` is a JPA `@Version` field. Using `#p0` selects the first parameter as the key without depending on compiler parameter-name retention.

**Practical notes:**

- `@Cacheable` takes effect only when calls pass through a Spring proxy. Internal calls within the same class (**self-invocation**) usually bypass cache advice.
- Never cache JPA entities directly when they have lazy associations or persistence contexts tied to a transaction. Stable DTOs without credentials containing just what consumers need are far easier to manage.
- With `RedisCacheManager`, the default serialization format may be Java serialization depending on configuration/version. Making the DTO `Serializable` lets the example run; production should explicitly choose a JSON/contracted serializer and manage schema compatibility. Never Java-deserialize untrusted data.
- Cache keys must include every factor determining output: `tenantId`, locale, currency, and permissions/segment where applicable. Sharing a `productId` key across tenants risks cross-tenant data exposure.
- Never cache nulls unless **negative caching** is intentionally designed: newly created records can stay hidden if "not found" stays cached too long.

## 5. Why Is Pre-Commit Invalidation Wrong?

The most critical failure mode occurs when the database write transaction has not yet committed, yet the cache has already been evicted:

~~~mermaid
sequenceDiagram
    participant T1 as Price-change transaction
    participant DB as Database
    participant C as Redis
    participant T2 as Read client
    T1->>DB: UPDATE price 120,000 (uncommitted)
    T1->>C: Evict product P-101 too early
    T2->>C: Cache miss
    T2->>DB: SELECT price
    DB-->>T2: 100,000 (old committed price)
    T2->>C: Refill cache = 100,000
    T1->>DB: COMMIT price 120,000
    Note over DB,C: Cache now holds old price despite committed transaction
~~~

Early invalidation opens a window for concurrent requests to **reload the old price from the database**. After T1 commits, without another eviction, the cache retains the wrong price until TTL expires.

**Rollback** creates another problem: an update method evicts before commit and then rolls back; eviction usually causes only an unnecessary cache miss, yet if `@CachePut` wrote the uncommitted price, clients see **data that never became real**.

Do not blindly assume combining:

~~~java
@Transactional
@CacheEvict(cacheNames = "productById", key = "#p0")
public void changePrice(UUID productId, BigDecimal newPrice) { ... }
~~~

means `@CacheEvict` always runs **after database commit**. Both annotations register independent interceptors/advice; the outer ordering between caching and transaction advice dictates when cache operations run. Choose **an explicit commit-ordering mechanism** rather than relying on accidental proxy ordering.

## 6. Post-Commit Invalidation Using TransactionalEventListener

In an application with local Spring/JPA transactions, you can publish an internal event inside the transaction and evict only once the transaction actually commits:

~~~java
// ProductChanged.java
package com.example.integration.catalog;

import java.util.UUID;

public record ProductChanged(UUID productId) {}
~~~

~~~java
// ProductCommandService.java
package com.example.integration.catalog;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(UUID productId, BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }

        ProductEntity entity = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId));
        entity.changePrice(newPrice);

        // Register event while transaction is active.
        // AFTER_COMMIT listener runs only if commit succeeds.
        events.publishEvent(new ProductChanged(productId));
    }
}
~~~

~~~java
// ProductCacheInvalidator.java
package com.example.integration.cache;

import com.example.integration.catalog.ProductChanged;
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
    public void onProductChanged(ProductChanged event) {
        Cache cache = cacheManager.getCache("productById");
        if (cache == null) {
            throw new IllegalStateException("Cache productById not configured");
        }
        cache.evict(event.productId());
    }
}
~~~

Here `ProductEntity.changePrice(...)` mutates the managed entity; JPA dirty checking flushes and commits inside the transaction. The exact same `productId` serves as the cache key on both read and eviction. Intended sequence:

~~~mermaid
sequenceDiagram
    participant App as ProductCommandService
    participant TX as Spring Transaction
    participant DB as Database
    participant Cache as Redis
    App->>TX: @Transactional changePrice
    TX->>DB: UPDATE product
    App->>TX: publishEvent(ProductChanged)
    TX->>DB: Commit
    DB-->>TX: Success
    TX->>Cache: AFTER_COMMIT evict(productId)
    Cache-->>TX: Delete key
    TX-->>App: Complete
~~~

**Meaning of `AFTER_COMMIT`:** the listener binds to the active transaction, so it does not execute on rollback; without an active transaction, `@TransactionalEventListener` **does not process the event** by default (`fallbackExecution=false`). Ensure all write paths run inside transactions and emit events appropriately.

**Limitation of this approach:** In-app events and after-commit callbacks are not durable message queues. If the process crashes after DB commit before eviction, or Redis errors, the database has committed while the cache remains stale. Exceptions inside the callback cannot roll back an already committed DB transaction; monitor failures and classify business outcomes accurately rather than claiming "database write failed" when only cache invalidation failed.

If `@Async` is added to the listener, the callback merely dispatches work to an executor after commit; executors do not provide crash durability. Never assume "async will automatically retry" dropped invalidations.

### 6.1. How Can a Transaction-Aware Cache Manager Help?

Spring provides `TransactionAwareCacheManagerProxy` and cache managers supporting transaction-aware settings. They can defer operations like `put`, `evict`, or `clear` until **after commit** when an active synchronized transaction exists. However, exact support varies by cache manager and invocation; never assume every operation—especially `putIfAbsent` or `evictIfPresent`—is deferred.

Pick **one consistent strategy** for write paths, verify actual ordering, and test rollbacks. When cross-service notification or crash-proof delivery is needed, local after-commit listeners are only a first step—see the transactional outbox in the next section.

## 7. Transactional Outbox When Invalidations Must Not Be Lost

In flows spanning multiple Spring Boot applications, there may be multiple Redis caches, per-replica Caffeine caches, or asynchronous read models. Issuing an HTTP/broker invalidation directly **after DB commit** still leaves a crash window if the process dies before publishing.

**Transactional outbox** persists a `ProductChanged` event **inside the same database transaction** as the product update. After commit, a relay reads the outbox and publishes events to Kafka/RabbitMQ or another reliable channel. Consumers evict corresponding caches.

~~~sql
BEGIN;

UPDATE products
SET price = :newPrice, version = version + 1
WHERE id = :productId;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, schema_version, payload_json, created_at
) VALUES (
    :eventId, :productId, 'ProductChanged', 1, :payloadJson, CURRENT_TIMESTAMP
);

COMMIT;
~~~

The SQL above illustrates named parameters and expected schema rather than a complete runnable script. Real applications should maintain unique constraints, version checks, and proper transaction managers. After commit:

~~~mermaid
flowchart LR
    S["Product Service"] -->|"Transaction update + outbox"| DB[("Product DB")]
    DB --> Relay["Outbox relay"]
    Relay --> Broker[("Kafka / RabbitMQ")]
    Broker --> Consumer["Cache invalidation consumer"]
    Consumer --> RC[("Redis / local cache")]
~~~

Handle explicitly:

1. **Durable outbox records committed together** ensure events are never lost if the process dies between DB write and publish.
2. Relays can publish **duplicates** when the broker accepts a message yet the relay crashes before marking it sent. **Evicting the same key multiple times is generally idempotent**; consumers still track event IDs and errors for operations.
3. Events can arrive **late or out of order**. Evicting only is generally safer than overwriting cache from stale event payloads; if updating cache values from events, compare `version` and use conditional/atomic writes to block older versions.
4. Monitor `outbox lag`, age of unpublished events, consumer lag, retries, DLQ counts, and invalidation failures.
5. If invalidation breaks for an extended period, finite TTLs act as a **safety net** so entries eventually expire. TTL does not replace monitoring and reconciliation.

An outbox guarantees commit atomicity **within the same database**, not an ACID transaction spanning DB–Redis–broker. Across multi-tier caches, define exactly which tier consumes which event and when each tier stops serving stale entries.

## 8. Race Condition: Post-Commit Eviction Can Still Refill Stale Data

A subtler bug than a **cache miss between commit and invalidation** is an old read request **that began before commit** writing its stale value into the cache **after invalidation already completed**:

~~~mermaid
sequenceDiagram
    participant R as Reader A
    participant DB as Database
    participant W as Writer B
    participant C as Redis cache
    R->>C: GET P-101 -> miss
    R->>DB: SELECT -> old price v7
    W->>DB: UPDATE new price v8; COMMIT
    W->>C: AFTER_COMMIT evict P-101
    R->>C: SET P-101 = old price v7
    Note over C: Stale entry recreated after eviction
~~~

This is a **stale repopulation race**. Even with `@TransactionalEventListener(AFTER_COMMIT)` implemented properly, the cache can stay stale for the remainder of its TTL.

### 8.1. Mitigations by Requirement Level

| Approach | When to use | Limitations |
| --- | --- | --- |
| **Finite TTL + after-commit evict** | Slowly changing data tolerating eventual consistency. | Does not eliminate race; leaves a stale window up to TTL. |
| **Version in value/key** | Data carries owner-incremented versions; must prevent old values overwriting new ones. | Requires verifying current version and fencing/CAS on cache write; adding a field alone does not stop races. |
| **Atomic compare-and-set on populate** | Shared cache supports atomic scripts/transactions. | Requires per-product high-watermark design and concurrency testing. |
| **Per-key single-flight coalescing** | Concurrent misses overload DB and duplicate writes. | Reduces stampedes; JVM-local locks do not coordinate across replicas. |
| **Read authoritative source directly** | Critical decisions needing latest/serializable semantics. | Higher latency/load; requires proper DB transactions/locks/optimistic versions. |
| **Delayed second eviction** | Reduces stale repopulation probability in practice. | Heuristic with **no absolute guarantee** and extra traffic. |

A stricter design uses a **version fence**: when the database commits `v8`, a watermark of at least `v8` is published to shared state; cache writers only store snapshots whose version is **at least the watermark**, via atomic compare-and-set. However, keeping the watermark synchronized with the database still has failure windows without outbox/reconciliation. State SLAs and guarantees clearly instead of calling a plain cache-aside model "linearizable."

**Never rely purely on `updatedAt` timestamps for absolute ordering** across multiple writers or clocks: timestamps can collide or skew. When ordering is required, use monotonic owner-generated versions and explicit version-handling rules on events.

## 9. Multi-Level Caches, Multiple Replicas, and Cache Stampedes

Some architectures combine **L1 Caffeine per JVM** and **shared L2 Redis**:

~~~text
API -> L1 Caffeine (per instance) -> L2 Redis -> Database
~~~

Evicting Redis alone after commit **does not evict** other replicas' L1 caches. To maintain freshness:

- Broadcast invalidations to every L1 instance, or keep L1 TTLs short enough to meet the contract.
- When instances restart or miss events, plan recovery, version checks, or protective TTLs.
- If pub/sub pushes only to online subscribers, offline replicas miss invalidations; never confuse non-durable Pub/Sub with replayable queues/logs.
- Keep cache keys identical across L1 and L2, with environment/tenant prefixes and schema versioning to avoid reading prior deployment formats.

### 9.1. Cache Stampedes and Hot Keys

When a popular product's TTL expires or is evicted, thousands of concurrent requests can miss and slam the database:

1. Use **controlled TTL jitter** so many keys do not expire simultaneously; jitter alone does not stop stampedes on a single hot key.
2. Apply **single-flight/locking** so only one load runs per key while remaining callers wait boundedly or use policy-approved fallbacks.
3. `@Cacheable(sync = true)` can coalesce concurrent calls **within provider capabilities**; verify explicitly because it does not lock across replicas/Redis clusters by default.
4. Proactively refresh hot keys, ensuring refreshes read the authoritative source and cannot overwrite newer updates.
5. Bound concurrency and connection pools when caches fail en masse so DB fallbacks do not cascade into overload.

**Stale-while-revalidate** should only be used when the business permits stale reads. For finalized checkout prices, revoked permissions, or balances, never return stale data solely to cut latency.

## 10. Invalidating the Right Keys When Multiple Views Change

One product mutation can affect multiple caches:

| Change | Caches to consider | Risk if evicting only `productById` |
| --- | --- | --- |
| Rename/reprice | `productById`, `productsByCategory`, `searchResults` | Lists and search results retain old names/prices. |
| Create new product | List caches, per-category counts | Negative caches or list caches hide the newly created product. |
| Delete product | Detail, list, and derived cart caches | Deleted items keep showing up in lists. |
| Move category | Old and new category list caches | Product appears in wrong category or in both. |
| Change tenant permissions/prices | Tenant-scoped and access-policy caches | Data leakage if keys omit tenant or permissions. |

Spring Cache offers `@CacheEvict(allEntries = true)` to wipe an entire region, yet on large caches this triggers severe stampedes and Redis load. Model dependent keys/indexes, separate cache regions, and targeted invalidation. Where list variants are too numerous to evict individually, use **versioned namespaces** or explicitly budget load for whole-region clears.

`UPDATE ...` statements via bulk JPQL, native SQL, scheduled jobs, migrations, or external services **do not automatically pass through `ProductCommandService`**. If only that service's listener evicts caches, other write paths leave stale prices. Centralize write contracts at the owner, emit outbox events across **all** update paths, or use CDC with proper event translation.

## 11. Redis Failures and Degraded-Mode Policy

Redis is a cache, yet still an operational dependency. Spring Cache can throw exceptions when `get`/`put`/`evict` cannot reach Redis; never assume caches "automatically fail open":

| Failure | Consequence | Policy to define |
| --- | --- | --- |
| Redis unreachable on read | Requests may fail before querying DB. | Allow DB fallback? How is fallback load bounded? |
| Redis unreachable on `put` | DB query succeeds yet cache write fails. | Return read data or require erroring? |
| Redis unreachable after DB commit on `evict` | DB updated, Redis key stale. | Alerting, durable retries/events, TTL, and reconciliation. |
| Mass cache misses after restart/flush | Database receives sudden traffic surge. | Backpressure, bounded warm-up, single-flight, capacity planning. |
| Redis returns undeserializable value | Schema/serializer mismatch or corrupt data. | Version prefixes, drop malformed entries, never silently accept corrupt data. |

You can configure `CacheErrorHandler` to handle get/put/evict errors by policy. However, swallowing `evict` errors after commit without retries/monitoring turns transient cache outages into **silent, hard-to-detect stale data**. For business-critical data, fail closed or read the primary source when freshness cannot be guaranteed.

With Redis Cluster, account for key routing, failover windows, replication lag, and replica reads. If reading cache from replicas lagging behind the master, deleting a key on master is not immediately visible on every replica; freshness SLAs must reflect the real read path.

## 12. Testing Rollbacks, Concurrency, and Recovery

A test verifying `@Cacheable` hits on the second call does not verify correctness. Test suites should exercise **actual commit ordering and interleaving**:

| Test case | Outcome to prove |
| --- | --- |
| Cache miss, then cache hit | First reads DB; second returns cached DTO under expected key. |
| TTL expiration | Entry marked expired; next query reloads from source. |
| Successful update and commit | Invalidation runs **after commit**; subsequent read sees new version. |
| Update then rollback | `AFTER_COMMIT` listener does not evict; DB retains old version. |
| Pre-commit eviction (fault injection) | Test reproduces stale-reload risk, confirming design avoids early eviction. |
| Redis fails right after commit | DB updated; error signal, retry/outbox, or bounded freshness fallback triggered per policy. |
| Reader loads stale data while writer commits | Detects stale repopulation race; verifies version fence or documented TTL bound. |
| Two replicas with separate L1 caches | Invalidation propagates past Redis; replicas honor freshness SLA. |
| Outbox relay publishes duplicates | Invalidation consumer is idempotent and never restores stale data from delayed events. |
| Bulk SQL / external writer updates entity | All write paths tracked and emit proper invalidations. |
| Two tenants with identical `productId` | Cache keys prevent cross-tenant data leakage. |
| Cache flushed under high traffic | DB survives without stampede overload or connection exhaustion. |

With Spring Boot, integration tests can use `@SpringBootTest`, Testcontainers for database/Redis, and concurrency tests with barriers controlling execution order. For transactions:

1. Seed product v1 and warm the cache.
2. Perform an update inside an independent transaction, force a rollback; verify v1 remains intact.
3. Perform an update in another transaction and commit; verify eviction and v2.
4. Inject a Redis failure during after-commit; verify DB state and operational alerts.
5. Let reader A start reading v1 while delaying `put` until after writer B commits/evicts; observe whether race handling matches the contract.

Never wrap an entire integration test in a default auto-rollback test transaction expecting `@TransactionalEventListener(AFTER_COMMIT)` to fire: **if the test rolls back, no commit happens to trigger the listener**. Use `TransactionTemplate`, non-transactional test methods, or explicit transaction commits when verifying after-commit listeners.

## 13. Observability: Measure Freshness, Not Just Hit Ratio

A high cache hit metric can indicate strong performance **or** many clients repeatedly receiving wrong data. Track:

- **Hits/misses/evictions/errors** by cache name, operation, and outcome; avoid `productId` in metric labels due to high cardinality.
- **Age of cached values** or versions when responses are built; helps diagnose staleness.
- **Commit-to-invalidation latency** and **commit-to-visible latency**, especially across brokers.
- **Outbox backlog**, oldest unpublished event age, redeliveries, DLQs, and consumer errors.
- **Cache stampedes:** sudden miss spikes, DB QPS, query latency, Redis timeouts, and pool saturation.
- **Version skew:** compare cached `version` against the primary source via controlled sampling/reconciliation.

Tracing a price change can link `productId` in access-controlled internal logs, `transactionId`/eventId, and correlation IDs from HTTP request through outbox relay/consumer. Never send personal secrets, tokens, private user payloads, or PII-bearing cache keys into public logs or metrics.

Alerts should be actionable: "post-commit invalidation failed," "unpublished outbox events past threshold," "sync lag exceeds SLO," or "abnormal miss spike." When recovery relies solely on TTL, alert whenever expected evictions fail to happen.

## 14. TTL and Invalidation Design Checklist

Before enabling caching in production, confirm:

- [ ] Which data is the **source of truth** and which is strictly a copy? Which operations require live reads?
- [ ] Freshness SLO and measurement method defined by business needs; TTL tailored per data type rather than one arbitrary number.
- [ ] Cache keys include tenant, locale, currency, and authorization/customization factors where applicable.
- [ ] Post-commit invalidation in place; tested rollbacks, proxy/advice order, and external write paths.
- [ ] Crash window between DB commit and Redis eviction assessed; outbox used where durable events are required.
- [ ] Stale repopulation races, delayed events, multiple replicas, and L1/L2 tiers addressed per required consistency.
- [ ] TTL, cache stampedes, hot keys, negative caching, and serializers controlled.
- [ ] Redis failure policy, DB fallbacks/backpressure, and reconciliation defined for failed invalidations.
- [ ] Concurrent update/rollback tests, cache lag measurement, and error alerts implemented.

When building Spring Boot integrations, **TTL** bounds entry lifetime, **post-commit invalidation** aligns caches with committed facts, and **outbox, idempotency, versioning, and reconciliation** sustain consistency across crashes, duplicate messages, and concurrent flows. Caching speeds up systems safely only when acceptable staleness is explicitly defined and cache update failures can be detected, tested, and recovered.
