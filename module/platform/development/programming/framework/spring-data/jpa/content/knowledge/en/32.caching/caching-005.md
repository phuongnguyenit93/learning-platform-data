# Cache Invalidation When Updating from JPA and External Systems

## 1. The problem: data has changed, yet the application still reads stale values

In Spring Data JPA, a record can be read through multiple cache layers. When data is modified via Hibernate/JPA, via bulk queries, via direct JDBC, or by another application accessing the same database, **there is no single cache-clearing command that automatically covers every layer**. If you fail to identify the right layer to invalidate (*invalidate/evict*), APIs can return outdated prices, statuses, or inventory levels.

Consider a catalog service with product `Product(id=42, priceCents=100000)`:

1. The API reads the price through Spring Cache and stores `productViews[42] = 100000`. If Hibernate's second-level cache is enabled, the entity state `Product#42` may also be stored there.
2. An admin system or an external sync process updates the price in the database to `120000`.
3. The API calls `getProduct(42)` again. If Spring Cache still holds key `42`, the JPA read function is **not even invoked**. Clearing Spring Cache while Hibernate still keeps the old entity in L2 can also continue returning `100000`.
4. Only when the affected caches are invalidated or expire can the next read reload `120000` from the current data source.

Two concerns must be separated: **ensuring the write transaction has committed successfully** and **ensuring no read path still holds stale data**. An update event may arrive late, be lost, or arrive while another caller is populating the cache. Therefore, the design must state the target consistency level: strict synchronization, near-real-time, or tolerating staleness within a short TTL.

## 2. Identifying the exact caches in use

| Layer | Scope | Where stale data can live | Primary handling mechanism |
| --- | --- | --- | --- |
| **JPA first-level cache (L1/persistence context)** | Per `EntityManager`/transaction | Managed entities inside an open persistence context | `refresh(entity)`, `clear()`, or ending the context and opening a new one |
| **JPA/Hibernate second-level cache (L2)** | `EntityManagerFactory`/`SessionFactory` and configured cache provider | Entities or collections permitted to be cached across contexts | `EntityManagerFactory.getCache().evict(...)` for entities; provider API for collections/regions |
| **Hibernate query result cache** | Queries marked cacheable and cache regions | Lists of IDs/query results per parameter set | Hibernate's invalidation mechanism or proactive query-region eviction on out-of-band changes |
| **Spring Cache** | Method layer via `@Cacheable`, e.g., in-memory/Caffeine/Redis | DTOs, service results, search pages, statistics | `@CacheEvict`/`CacheManager`, matching cache name and key |
| **External caches or replicas** | Redis managed by another service, CDN, search index, client | API results/indexes/replicated values | Event contracts, invalidation/reindex APIs, or separate TTLs |

Common points of confusion:

- **L1 is always bound to one persistence context**, so `entityManager.clear()` only detaches managed entities from that context; it does not clear Spring Cache, L2, query cache, or data on other nodes. `clear()` also discards unflushed changes in that context.
- **L2 is not enabled by default for every entity.** The actual effect of `jakarta.persistence.Cacheable` depends on shared-cache mode, Hibernate configuration, and the cache provider. Calling `getCache().evict()` does not mean L2 was previously active.
- **Query cache differs from SQL/query plan caching.** Hibernate's query result cache typically requires separate activation and per-query opt-in; a query plan cache does not store business data results.
- **`@Cacheable` has two meanings depending on the import:** `org.springframework.cache.annotation.Cacheable` caches method return values; `jakarta.persistence.Cacheable` marks an entity eligible for L2. One annotation does not control the other layer's cache.
- **Spring Cache keys depend on method signatures and key generator configuration.** Key `42L` in `productViews` differs from string `"42"`, differs from filter-based search keys, and differs from keys set by an external service.

In this lesson, *invalidate* means marking/removing an old cached copy so the next read reloads it; *evict* refers to removing a specific entry or region. *Refresh* means reloading data and typically affects only the relevant entity or read path.

## 3. When JPA is the writer, what does the ORM handle automatically?

For standard managed entity updates:

```java
@Transactional
public void changePrice(Long id, long priceCents) {
    Product p = repository.findById(id).orElseThrow();
    p.changePrice(priceCents);
    // Hibernate dirty checking; transaction manager flushes/commits at the end.
}
```

This is an illustrative method inside a Spring service; the complete classes appear later. Hibernate knows the entity changed and handles synchronizing caches **that Hibernate itself manages**, according to concurrency/cache region settings. For cacheable Hibernate queries, the update-timestamp mechanism can invalidate stale query results when Hibernate detects modified tables.

However, Hibernate **cannot automatically update Spring caches** holding DTOs built from entities. For instance, `@Cacheable("productViews")` on a service can keep returning an old price even after the JPA record commits. Likewise, Hibernate does not understand gateway caches, search engines, or HTTP clients.

Important timing note: modifying an entity inside a transaction does not mean the database has committed. If caches are cleared too early, another reader thread can reload the **old** value before commit and store it back into the cache. If the transaction rolls back, early eviction is also wasted work and triggers unnecessary reloads.

### 3.1. Why is `@CacheEvict` on a `@Transactional` method not guaranteed to be "after commit"?

The following pattern looks reasonable:

```java
@Transactional
@CacheEvict(cacheNames = "productViews", key = "#p0")
public void changePrice(Long id, long priceCents) {
    // Write entity...
}
```

By default, `@CacheEvict` runs **after the method completes successfully** according to the cache advice. That moment **does not automatically guarantee the database has committed**, because AOP advice ordering and scope, nested transactions, or caller-managed transactions can differ. `beforeInvocation = true` even evicts the key before the method executes. Do not rely on these mechanisms as a post-commit consistency guarantee without verifying the exact transaction configuration.

The explicit approach for internal JPA updates is to publish an event inside the transaction and handle invalidation at `TransactionPhase.AFTER_COMMIT`; for higher reliability or cross-service flows, use a transactional outbox or a retry-capable delivery mechanism.

## 4. Spring Data JPA example: invalidating after commit

The example below uses **Java 17+, Spring Boot 3.x, Spring Data JPA, Spring Cache, and a relational database**. All files reside in the `demo.cache` package of an **already configured Spring Boot project**. `spring-boot-starter-data-jpa`, `spring-boot-starter-cache`, a JDBC driver, and a suitable `CacheManager` must be on the classpath; integration tests also use `spring-boot-starter-test` and H2. This is multi-file project code, not a standalone Java SE program compiled directly with `javac`.

Objectives:

1. `ProductQueryService` reads via JPA and caches a DTO by ID.
2. `ProductCommandService` modifies the managed entity inside a transaction and publishes `ProductChanged`.
3. `ProductCommittedListener` triggers invalidation only after a successful commit.
4. `ProductCacheInvalidator` evicts **Spring Cache** and the related **JPA L2** entry. If L2 is disabled, the JPA cache eviction call has no side effects.

**`Product.java`**

```java
package demo.cache;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    @Version
    private long version;

    protected Product() {}

    public Product(String name, long priceCents) {
        this.name = name;
        this.priceCents = priceCents;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public long getPriceCents() { return priceCents; }

    public void changePrice(long newPriceCents) {
        if (newPriceCents < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }
        this.priceCents = newPriceCents;
    }
}
```

`@Version` helps detect certain concurrent updates **when every write path respects the versioning mechanism**. Direct SQL writes from external systems that ignore the `version` column can break that protection; a later section addresses that case.

**`ProductRepository.java`**

```java
package demo.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

**`ProductView.java`**

```java
package demo.cache;

public record ProductView(Long id, String name, long priceCents) {
}
```

**`ProductQueryService.java`**

```java
package demo.cache;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productViews", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView byId(Long id) {
        Product p = repository.findById(id).orElseThrow();
        return new ProductView(p.getId(), p.getName(), p.getPriceCents());
    }
}
```

`#p0` refers to the first parameter (ID), avoiding reliance on whether parameter names are preserved after compilation. The method must be invoked **through the Spring proxy** for `@Cacheable` to work; calling `this.byId(...)` from inside the same class normally bypasses cache advice in default proxy mode.

**`ProductChanged.java`**

```java
package demo.cache;

public record ProductChanged(Long id) {
}
```

**`ProductCommandService.java`**

```java
package demo.cache;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository repository,
            ApplicationEventPublisher events
    ) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(Long id, long newPriceCents) {
        Product product = repository.findById(id).orElseThrow();
        product.changePrice(newPriceCents);
        events.publishEvent(new ProductChanged(id));
    }
}
```

The event is published **inside the transaction**, at which point data may not yet be flushed/committed. The listener registers a callback tied to the transaction lifecycle. If the transaction rolls back, the `AFTER_COMMIT` callback will not run. If there is no active transaction, `@TransactionalEventListener` does not run by default (unless `fallbackExecution = true` is used, which would not fit this example's contract).

**`ProductCacheInvalidator.java`**

```java
package demo.cache;

import jakarta.persistence.EntityManagerFactory;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class ProductCacheInvalidator {
    private final CacheManager cacheManager;
    private final EntityManagerFactory entityManagerFactory;

    public ProductCacheInvalidator(
            CacheManager cacheManager,
            EntityManagerFactory entityManagerFactory
    ) {
        this.cacheManager = cacheManager;
        this.entityManagerFactory = entityManagerFactory;
    }

    public void invalidate(Long productId) {
        Cache cache = cacheManager.getCache("productViews");
        if (cache != null) {
            cache.evict(productId);
        }
        entityManagerFactory.getCache().evict(Product.class, productId);
    }
}
```

`cache.evict(productId)` only removes the entry in Spring Cache `productViews` with that key. `entityManagerFactory.getCache().evict(Product.class, productId)` targets only the **JPA L2 entity cache**. It does not automatically clear L1 of all transactions, Hibernate's query cache, collection caches, or multi-parameter search results.

**`ProductCommittedListener.java`**

```java
package demo.cache;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCommittedListener {
    private final ProductCacheInvalidator invalidator;

    public ProductCommittedListener(ProductCacheInvalidator invalidator) {
        this.invalidator = invalidator;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(ProductChanged event) {
        invalidator.invalidate(event.id());
    }
}
```

**`CacheConfiguration.java`**

```java
package demo.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

The classes above are scanned by Spring in package `demo.cache` or subpackages of `@SpringBootApplication`. With an in-memory `CacheManager` for learning/testing, the cache is effective within a single JVM. With Redis or another provider, you must configure serializers, TTL, and appropriate sharing scope; those settings **do not appear automatically** just by adding `@EnableCaching`. If the cache name `productViews` is misconfigured, `cache != null` avoids a null error but does not ensure invalidation; in production, treat a missing expected cache as an observable configuration error.

### 4.1. Commit timeline

```text
T0  API byId(42) -> cache miss -> JPA loads Product#42 -> caches old DTO.
T1  CommandService.changePrice(42, 120000) opens transaction.
T2  Entity is modified, ProductChanged(42) event is published.
T3  JPA flushes; database COMMIT succeeds.
T4  AFTER_COMMIT listener calls invalidator.invalidate(42).
T5  Spring Cache productViews[42] and L2 Product#42 are evicted.
T6  Next API byId(42) cache miss reloads the current price.
```

This sequence assumes the callback and eviction succeed on the right node/cache with no special races. **`AFTER_COMMIT` prevents pre-commit invalidation, but it is not a durable event delivery mechanism**. If the process crashes right after commit and before the callback, or Redis fails inside the listener, the database has committed while the cache remains stale. When guaranteed delivery is required, use an outbox with retries; when a post-commit listener performs database writes, it generally needs a new transaction (`REQUIRES_NEW`), because the previous transaction's resources may still be bound to the thread without another commit occurring.

## 5. When changes come from systems outside JPA

Suppose a warehouse application, ETL batch, or DBA runs:

```sql
UPDATE products
SET price_cents = 120000,
    version = version + 1
WHERE id = 42;
```

This is illustrative SQL. Hibernate in the catalog application does not participate in this SQL statement. As a result:

- A persistence context that already loaded `Product#42` may still return the old managed entity for the rest of its lifetime.
- Hibernate's L2 across one or more nodes may continue holding the old copy.
- Hibernate's query cache may not know the table changed because the update bypassed Hibernate.
- Spring Cache returns the old DTO if the key has not expired.
- `@Version` can help detect concurrent writes if all writers increment version by convention, but it **does not broadcast invalidation**.

### 5.1. Ways to notify that a change occurred

| Approach | When to use | Pros | Limitations |
| --- | --- | --- | --- |
| **Read/write through an owning service** | All writers can be forced through one shared API | Easy to centralize transactions and event contracts | Writers accessing the DB directly can still bypass it |
| **Transactional outbox** | The writing service itself emits business events | Data record and outbox record commit in the **same transaction**; relay workers can retry delivery | Covers only writers that implement the outbox; needs relay, retry, and cleanup |
| **CDC from the transaction log** | Multiple programs/legacy jobs modify the same DB | Captures non-JPA changes if the connector tracks the right tables and commits | Latency, operational complexity, need to classify change types and handle duplicates/out-of-order events |
| **Polling version/timestamp** | No broker/CDC available and latency is acceptable | Simpler when change frequency is low | Polling interval lag; easy to miss changes if timestamps are not reliably updated |
| **Short TTL and cache bypass** | Staleness is acceptable within bounds, or fields require strong consistency | Bounds entry lifetime; avoids caching critical read paths | TTL does not ensure immediate detection; bypass increases DB load |

**Outbox does not automatically cover SQL from another application** unless that application also writes to the outbox. When you do not control the writer, the usual choices are DB CDC or a managed trigger/change-stream mechanism. Events should clearly specify entity type, ID, change type, commit/version when available, event ID, and source; do not pass managed JPA entity instances as system payloads.

A sensible CDC flow:

```text
Writer A (JPA) ----\
                    -> Database commit -> transaction log -> CDC
Writer B (SQL) ----/                            |
                                                v
                                     product-changed event
                                                |
                                                v
                                      invalidate Spring cache
                                      + L2 on relevant nodes
                                      + dependent query/list caches
```

**Events must reflect committed state**. Clearing the cache as soon as a writer starts editing or while a transaction can still roll back opens the door to repopulating the cache with old data.

### 5.2. External event receivers should call a shared invalidation function

`ProductCacheInvalidator` from section 4 also serves as the shared entry point for events received from a broker/CDC:

```java
package demo.cache;

import org.springframework.stereotype.Component;

@Component
public class ExternalProductChangeHandler {
    private final ProductCacheInvalidator invalidator;

    public ExternalProductChangeHandler(ProductCacheInvalidator invalidator) {
        this.invalidator = invalidator;
    }

    public void onCommittedExternalUpdate(Long productId) {
        invalidator.invalidate(productId);
    }
}
```

This is a **handler invoked after an adapter receives a committed event**, **not** a complete Kafka/RabbitMQ consumer. Topic subscription, schema deserialization, source verification, ack/retry, dead-letter queues, and per-node delivery rules must be configured in the actual adapter. No Java line in the example can detect SQL from another application without a notification channel.

If Redis is used as a **shared** Spring Cache, deleting a Redis key deletes it from the shared namespace. However, an event delivered to **one** instance via a consumer group only evicts that instance's local L2 if L2 is local. Other instances can remain stale. For all nodes to invalidate local L2, you need fan-out/broadcast to every node, an L2 provider with cluster coherence, or to disable L2 for entities frequently updated externally. A standard broker consumer-group configuration **does not mean broadcast to every instance**.

## 6. Distinguishing invalidation APIs by scope

### 6.1. L1: `refresh`, `clear`, and a new transaction

```java
// Illustrated inside a transaction with an EntityManager:
entityManager.refresh(product); // Reloads the current entity state.
entityManager.clear();          // Detaches all entities in this context.
```

`refresh` applies to a managed entity and can overwrite unflushed changes on that entity. `clear` detaches every entity in the context, so unflushed changes may be discarded; do not use `clear` as a "system-wide cache fix". Long-lived transactions and extended persistence contexts need an explicit refresh strategy when external systems make changes.

For queries following an update event, creating a new persistence context/transaction eliminates the possibility that L1 holds an old instance, **but does not clear stale L2 or Spring Cache**.

### 6.2. JPA L2: `EntityManagerFactory.getCache()`

```java
entityManagerFactory.getCache().evict(Product.class, 42L);
entityManagerFactory.getCache().evict(Product.class);
entityManagerFactory.getCache().evictAll();
```

These three calls target **a single entity**, **all entities of that class**, and **all entities in JPA L2**, respectively. Under the Jakarta Persistence contract, `evictAll()` only affects cached entity data; **do not treat it as "clear every cache from DB to Redis and queries"**. Eviction by ID is usually preferred to minimize impact on cache hit rates.

If the system uses a distributed L2, verify whether the cache provider synchronizes across nodes. `getCache()` from one application instance cannot automatically purge other JVMs if the provider uses local memory.

### 6.3. Hibernate query cache and collection cache

Jakarta Persistence only provides basic APIs for L2 entities. When Hibernate has query result caching or collection caching enabled, provider-specific APIs may be needed:

```java
// Hibernate-specific; only use if the project runs on Hibernate.
org.hibernate.SessionFactory sessionFactory =
        entityManagerFactory.unwrap(org.hibernate.SessionFactory.class);

sessionFactory.getCache().evictQueryRegions(); // Query result regions.
sessionFactory.getCache().evictCollectionData(); // Collection regions.
```

The snippet above **intentionally illustrates broad eviction**; avoid calling it for every small change when a specific query region or collection role is known. Hibernate also provides `evictQueryRegion("...")` and `evictCollectionData("Entity.collection", ownerId)` when exact mappings are identified. Hibernate's query cache relies on table update metadata; when the DB changes externally without updating internal timestamps, an explicit eviction mechanism is needed. Do not use `EntityManager.clear()` as a substitute.

If queries are not cacheable or the query cache is disabled, query-region operations yield no benefit. Observe Hibernate statistics and actual configuration rather than assuming a query cache exists.

### 6.4. Spring Cache: single key or entire region?

```java
// Appropriate when the key of a single product is known:
cacheManager.getCache("productViews").evict(42L);

// When it is unknown which search results depend on the product,
// you may force rebuilding the entire search region:
cacheManager.getCache("productSearch").clear();
```

This snippet assumes the cache names exist; production code should check for null from `getCache(...)` and handle misconfiguration. Evicting by ID works well when data has no complex dependencies. For cached `search(category, page, sort)` results, one product changing price or status can affect **multiple keys**, so evicting only `productViews[42]` is insufficient.

Solutions for lists/queries: explicitly track cache dependencies, use region generation/versioning, invalidate by tag/index if supported by the provider, or selectively clear regions. Calling `clear()` on a whole region can trigger a cache stampede, so evaluate traffic and warm-up behavior. `@CacheEvict(allEntries = true)` has similar semantics for a Spring Cache region.

### 6.5. Action table by write path

| Write path | Stale L1 | Hibernate L2/query | Spring Cache/Redis DTO |
| --- | --- | --- | --- |
| Managed entity + commit via JPA | Current context manages the entity; other contexts may hold old instances | Hibernate handles regions it manages per configuration; verify specific queries/collections | **Application must actively invalidate/refresh** after commit |
| JPQL/HQL bulk `UPDATE` or `DELETE` | Can become stale; clear or use a new context | Provider/query-type dependent; Hibernate generally has bulk handling, but it does not replace testing relevant caches | **Actively invalidate** |
| Native SQL/JDBC within the same service | Can become stale | Do not assume the ORM detects all modified tables/regions | **Actively invalidate** |
| SQL written by another system | Open contexts may become stale | **Does not automatically detect changes outside Hibernate** | **Does not automatically detect** without events, polling, or TTL |
| Large multi-record data imports | Open contexts may become stale | Consider region eviction or rebuild when volume is large | Consider region-generation / batch invalidation |

Do not turn the "Hibernate handles it" column into a blanket guarantee across all providers and mappings. Exact behavior still depends on version, second-level cache strategy, and how queries execute.

## 7. Bulk updates, native SQL, and `@Modifying`: easy-to-miss points

With Spring Data JPA, you can write a direct update method:

```java
// Add this method to the ProductRepository interface from section 4:
@org.springframework.data.jpa.repository.Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@org.springframework.data.jpa.repository.Query(
    "update Product p set p.priceCents = :price where p.id = :id"
)
int updatePriceBulk(
    @org.springframework.data.repository.query.Param("id") Long id,
    @org.springframework.data.repository.query.Param("price") long price
);
```

- `@Modifying` tells Spring Data to treat `@Query` as a modifying query.
- `flushAutomatically = true` requests flushing the persistence context before executing the bulk update.
- `clearAutomatically = true` clears the persistence context after the query to avoid keeping stale managed entities; it **does not clear Spring Cache or L2 on other instances**.
- Bulk JPQL updates typically **bypass per-record dirty checking, lifecycle callbacks, and entity optimistic version checks**. The example above does not increment `@Version`. If optimistic locking is needed, design explicit version conditions/updates; for a single entity, modifying a managed entity is usually simpler and safer.
- Call this method inside a write transaction, then invalidate application caches **upon successful commit** just as with managed updates; do not rely on `clearAutomatically` as a complete solution.

With `nativeQuery = true`, `JdbcTemplate`, stored procedures, or another ORM session, Hibernate may lack enough metadata to evict all related caches. If using Hibernate's query-space synchronization API for native queries, test it on the exact provider/version; a more portable and explicit approach is to emit change events for the affected aggregates.

**Example of what to avoid:** running `UPDATE products SET price_cents = ...` outside Hibernate, calling only `entityManager.clear()`, and expecting another API to see the new price. One context's L1 is empty, yet Spring Cache and L2 may still be stale.

## 8. Operation ordering and failure modes in distributed environments

### 8.1. Evicting before commit can reload stale data

```text
Writer updates product but has not COMMITTED yet.
Writer EVICTs cache (too early).
Reader sees cache miss -> reads old price from DB -> caches it again.
Writer COMMITs new price.
No further invalidation -> cache remains stale.
```

Therefore, prefer post-commit triggers. Yet even post-commit invalidation **does not completely eliminate races** with in-flight reads.

### 8.2. "Stale repopulation" race even when evicting after commit

```text
Reader R: cache miss, starts reading price 100.
Writer W: commits price 120.
Writer W: evicts key product 42.
Reader R: finishes and puts the just-read price 100 into the cache.
Subsequent read: cache may return 100 again.
```

This is a known risk of the *cache-aside* pattern under concurrent reads and writes. TTL bounds how long stale data persists, but does not create instant consistency. If business rules forbid stale reads (e.g., locked payment/inventory decisions), consider **bypassing cache on critical read/write paths**, checking versions, key-level coordination, or proper transaction/locking design. Avoid claiming "after-commit eviction always gives strong consistency".

### 8.3. Delayed, duplicated, or lost notifications

A reliable event system needs at minimum:

1. **Event identifier** (`eventId`) and entity/aggregate ID; plus version/commit sequence if available to handle ordering.
2. **Idempotency:** evicting the same key multiple times is generally safe; if consumers **overwrite cache entries with event payloads**, apply only newer versions so old events cannot revert newer data.
3. **Acknowledge after successful processing** and retry on cache/broker errors; monitor dead-letter queues, lag, and retry counts.
4. **Emit events after commit** or via an outbox/CDC with clear transaction boundaries.
5. **Proper fan-out scope:** local caches on each instance need per-instance notifications or cluster coherence; a consumer group dividing messages one-per-worker does not achieve that automatically.
6. **Staleness-bounding safeguards:** TTL, key versioning, or disabling cache where data must be fresher than event propagation latency allows.
7. **Observability:** log `productId`, event ID, change source, commit/receive/evict timestamps, region, and processing errors, avoiding unnecessary sensitive data.

When an `AFTER_COMMIT` callback fails, **the database has already committed**. Do not casually treat the thrown exception as a rolled-back transaction and retry the write command, as that can cause duplicate updates. An outbox decouples event durability from cache availability, allowing workers to retry independently.

### 8.4. Versioned cache key pattern

One technique to prevent writing stale values under the same key is embedding a generation/version into the key:

```text
product:42:v17
product:42:v18
```

When the version used to select keys increases reliably, new queries will not read entries from previous versions. However, **the mechanism determining the "latest version" must itself be consistent** (the database, an ordered generation store, or a version token with a clear contract). Changing keys using each instance's local timestamp without sharing versions does not solve the problem. TTL/cleanup is also needed so old keys do not accumulate indefinitely.

## 9. Integration scenarios and practical testing

Before choosing an invalidation strategy, build a **data-to-cache map**. For example:

| Data changed | Keys/regions to consider | Writers that can cause the change |
| --- | --- | --- |
| Price of `Product#42` | Spring `productViews[42]`; JPA L2 `Product#42` | Product service, admin batch, ETL |
| Price affecting search results or sorting | Spring `productSearch[...]`; enabled query caches | All three sources above |
| Active status affecting category listings | `categoryListings[categoryId]`, query result caches | Catalog service, external integrations |
| Order lines and total quantities | Order aggregate/collection caches and summary DTOs | Order service, SQL imports |

You do not necessarily have to wipe all caches whenever a product changes. Identify **which data dependencies are affected**, then pick ID eviction, region eviction, or generation updates appropriately. If the dependency map is too broad and you lack enough data to compute specific keys, prioritize correctness first, then optimize scope.

### 9.1. Integration test for JPA updates and external SQL

Using the `demo.cache` classes from section 4, you can write tests after configuring Spring Boot + H2 + `CacheManager`. Place the test file in `src/test/java/demo/cache/ProductCacheIntegrationTest.java`. The goal of the test is to verify written data is actually reloaded, not merely checking a Java object in RAM.

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ProductCacheIntegrationTest {
    @Autowired ProductRepository repository;
    @Autowired ProductQueryService reads;
    @Autowired ProductCommandService writes;
    @Autowired ProductCacheInvalidator invalidator;
    @Autowired JdbcTemplate jdbc;

    @Test
    void jpaUpdateInvalidatesAfterCommit() {
        Product p = repository.saveAndFlush(
                new Product("Product A", 100_000));
        Long id = p.getId();

        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        writes.changePrice(id, 120_000); // @Transactional service.
        assertThat(reads.byId(id).priceCents()).isEqualTo(120_000);
    }

    @Test
    void externalSqlNeedsNotificationAndEviction() {
        Product p = repository.saveAndFlush(
                new Product("Product B", 100_000));
        Long id = p.getId();

        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        // Simulate a writer outside JPA, already committed via JDBC.
        jdbc.update("""
            UPDATE products
            SET price_cents = ?, version = version + 1
            WHERE id = ?
            """, 150_000, id);

        // On cache hit, the JPA call does not even execute.
        assertThat(reads.byId(id).priceCents()).isEqualTo(100_000);

        // This is the step executed by a CDC/outbox/broker consumer.
        invalidator.invalidate(id);

        assertThat(reads.byId(id).priceCents()).isEqualTo(150_000);
    }
}
```

Conditions for meaningful testing: Spring Cache is genuinely enabled and `reads.byId` is invoked via the bean proxy; the test **does not** wrap the whole test method in `@Transactional` (which defaults to rollback and prevents `AFTER_COMMIT` from firing); writes target a single test database; `JdbcTemplate.update` in this test executes outside a test transaction and commits per default driver/transaction manager settings. If your project configures connections/transactions specially, ensure the SQL step commits before calling invalidation.

Run with Maven Wrapper if provided by the project:

```bash
./mvnw -Dtest=ProductCacheIntegrationTest test
```

On Windows use `mvnw.cmd -Dtest=ProductCacheIntegrationTest test`; with Gradle run the project's corresponding test task. The assertions above **do not verify** Hibernate query cache or multi-node local caches, as a basic test configuration may only enable Spring Cache. To test L2, actually enable the provider/region, warm the cache, verify hits/misses, modify the DB outside the ORM, and assert eviction. To test multi-node setups, run two real instances with the actual Redis/L2/event bus setup.

### 9.2. Test cases recommended for production readiness

| Case | Execution | Expected observation |
| --- | --- | --- |
| Commit via JPA | Read to populate cache, update price, then commit | Old cache entry is evicted and subsequent read sees the new price |
| Rollback | Modify price then throw exception to force rollback | `AFTER_COMMIT` invalidation does not fire; DB unchanged |
| Bulk JPQL | Warm cache, run bulk update, and commit | No stale L1 remains; Spring Cache and affected regions handled |
| External writer | Commit direct SQL then emit change event | Dependent caches evicted on the right nodes/namespaces |
| Missing event | Intentionally stop consumer or CDC | TTL/alerts/reconciliation behave per staleness tolerance policy |
| Duplicate delivery | Replay the same `eventId` multiple times | Consumer is idempotent, no business errors occur |
| Out-of-order events | Deliver newer version before older version | Old payload does not overwrite newer data |
| Two instances | Warm/populate cache on A and B, update DB, and broadcast | Both A and B see new data within SLA |
| Read/commit race | Run cache-miss read concurrently with write + evict | Stale repopulation detected and handled per consistency requirement |
| List/query changes | Add or delete entity changing result pages | Related query/list caches updated or cleared |

**Verification method:** inspect the DB independently, read through separate endpoints/services, check cache hit/miss counts, SQL logs, versions/timestamps, and commit-to-evict latency. Do not just look at the response of a single request that modified the entity within the same persistence context.

## 10. Common errors and how to handle them

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Called `entityManager.clear()` but API still returns old price | Spring Cache, L2, or query cache still holds data | List all cache layers; evict the right key and region |
| `@CacheEvict` ran yet old price reloads after rollback | Eviction happened before commit, under a different advice scope | Move invalidation to `AFTER_COMMIT` and test rollback |
| Evicted `productViews[42]` yet search stays stale | Search results are cached under separate filter/page keys | Invalidate dependent regions or use generation versioning |
| One node sees new price, another sees old price | Local L2/Caffeine; event reached only one consumer in group | Configure broadcast or shared/coherent cache |
| Hibernate unaware of external SQL changes | Writer bypassed Hibernate | CDC/outbox/events, TTL, or cache bypass |
| `@Modifying(clearAutomatically=true)` did not fix issue | It only clears that query's persistence context | Check L2 and application caches separately |
| Reloading cache right after evict still sees stale data | Evicted too early, stale context, replica lag, stale repopulation race | Inspect commit/read timeline, replica consistency, versions |
| After commit DB changed yet cache remains stale | Lost event, listener failure, dropped pub/sub, wrong key | Log event ID, retry, DLQ, monitoring, TTL |
| `@Cacheable` not caching or `@CacheEvict` not running | Missing `@EnableCaching`, self-invocation, wrong key, call bypassed proxy | Check configuration and invoke via Spring bean |
| Evicting all regions on every update slows down the system | Mass cache misses and stampedes | Identify dependent keys, batch evict, generation, load limits |
| Optimistic-lock conflict or lost update after native SQL | External writer did not follow `@Version` convention | Align writers/versioning/locks; test concurrency |

### Special note: multiple "sources of truth" can arise if writers are unregulated

When services A and B can write to the same table, they must agree on schema, transactions, `version` increment rules, and event emission payloads. Good cache invalidation cannot fix lost updates in the database. For high-precision fields like balances, available inventory at checkout, and access permissions, do not assume cache TTL is a transaction-locking mechanism; choose read and update paths with appropriate consistency.

## 11. Design process and implementation decisions

1. **List every write path** to the table/aggregate: managed JPA, bulk JPQL, JDBC, SQL batches, ETL, external systems, admin scripts.
2. **Draw a cache map**: L1, L2 entity/collection, Hibernate query, Spring Cache/Redis, API/search/CDN; document cache names, keys, TTLs, and instance ownership.
3. **Define data freshness SLAs**: exact at transaction time, within seconds, or minutes of lag acceptable; identify data that must bypass cache.
4. **Design post-commit invalidation**: internally, `@TransactionalEventListener(AFTER_COMMIT)` can work; when durability is required, use an outbox. For uncontrolled writers, consider CDC or managed triggers/streams.
5. **Specify event contracts**: entity ID, change type, version, event ID, source, timestamp; idempotency, retries, ordering, DLQ, and event authorization.
6. **Decide eviction scope**: entry by ID, dependent regions/queries/lists, or generations; avoid indiscriminate broad clears and avoid missing aggregated results.
7. **Evaluate multi-node behavior**: shared Redis does not mean local L2 is synchronized; each cache needs a valid coherence/broadcast channel.
8. **Test commit, rollback, external writers, consumer failures, two nodes, and read/commit races**. Verify outcomes using fresh DB reads and per-layer cache inspections.
9. **Add safeguards**: suitable TTLs, lag/event-failure monitoring, reconciliation/rebuild jobs, and fallback handling when caches are unavailable.

### Self-check questions

**1.** Why does an application update `Product` via Spring Data JPA and still read the old price from `@Cacheable`? **Answer:** Hibernate knows the entity changed, but does not automatically remove DTOs in Spring Cache. You need post-commit invalidation of the right key or a different caching strategy.

**2.** Does `entityManagerFactory.getCache().evict(Product.class, 42L)` delete Spring Redis cache `productViews[42]`? **No.** This API only targets the JPA L2 entity cache, not Spring Cache.

**3.** A batch SQL outside the ORM updates products, yet a service uses `@Modifying(clearAutomatically=true)` on another repository. Why is stale data still seen? **Answer:** `clearAutomatically` only clears the persistence context when that modifying query method runs; it does not listen to external batch SQL and does not evict L2/Spring Cache.

**4.** Can `AFTER_COMMIT` replace an outbox in all cases? **No.** The callback helps with timing, but can be lost if the process crashes or fails after commit. An outbox or CDC with checkpoints/retries is needed when notification durability is required.

**5.** With local caches across three instances and a broker using one consumer group, is delivering an event to just one instance enough? **No**, if each instance has a local L2 that needs eviction. You must fan out to all instances, use a provider with cluster coherence, or avoid caching that entity type in L2.

## 12. Conclusion and reference documentation

- **L1** lives only within the persistence context; `refresh/clear` have local scope.
- **L2/JPA cache** stores entities across contexts and can become stale when external systems modify the DB; `EntityManagerFactory.getCache().evict(...)` targets entity entries, not all caches everywhere.
- **Hibernate query/collection caches** must be identified separately and managed with provider APIs when needed.
- **Spring Cache** caches method results; DTOs and lists/queries must be invalidated by their exact keys and dependent regions.
- For **JPA updates**, avoid premature eviction; use post-commit callbacks so caches do not reload uncommitted values. For **external writers**, build post-commit event flows via outbox/CDC or apply TTL/bypass per consistency needs.
- For **multi-node setups and races**, design event distribution, retries, versioning, and observability; a single evict call does not guarantee strong consistency.

Official references:

- Spring Framework — Cache annotations (`@Cacheable`, `@CacheEvict`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction-bound events (`@TransactionalEventListener`): https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Data JPA — Modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Jakarta Persistence 3.2 — `Cache` API: https://javadoc.io/static/jakarta.persistence/jakarta.persistence-api/3.2.0/jakarta.persistence/jakarta/persistence/Cache.html
- Hibernate ORM User Guide — Caching and managing cached data: https://docs.hibernate.org/orm/7.2/userguide/html_single/#caching
- Hibernate ORM — `org.hibernate.Cache` API: https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Cache.html
