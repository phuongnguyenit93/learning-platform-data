# Choosing What to Cache, Expiration, and Stale Data Tolerance in Spring Data JPA

Caching helps reduce database queries and shorten response times by retaining previously read data or computed results for reuse. However, caching always introduces a correctness question: how long should data be kept, when must it be refreshed, and how much stale data can users tolerate?

You should not cache something simply because a query is slow. First, determine whether the data is read repeatedly, whether the loading/computation cost is significant, how frequently the data changes, and what happens if stale results are served. A product catalog might tolerate a few minutes of lag; an account balance or inventory count used to confirm a transaction may require much fresher data.

This lesson guides you through choosing cache candidates, setting a freshness/staleness budget, choosing TTLs, designing keys and invalidation, distinguishing Spring Cache from JPA/Hibernate caches, controlling cache stampedes, and monitoring effectiveness in real applications.

## 1. What problem does caching solve?

A data read typically traverses multiple layers:

1. The application calls a service.
2. The repository builds a query.
3. The JPA provider generates SQL and sends it to the database.
4. The database reads indexes/data, executes the query, and returns results.
5. Hibernate maps the results into entities or projections.
6. The application transforms the data into a response.

Caching can skip some or all of these steps on subsequent reads. If the same data is requested many times, caching reduces database load and can lower latency.

For example, an API fetching product details by SKU is called 5,000 times per minute, whereas product descriptions change only a few times per day. Reading the same record repeatedly from the database may be unnecessary.

Conversely, if every request uses a unique filter and keys almost never repeat, caching can consume memory while achieving a very low hit rate.

Caching does not make the underlying query faster. It only lets subsequent reads bypass the corresponding query or computation. Cache-miss queries still need enough performance to handle real traffic.

## 2. Common cache types in a Spring Data JPA application

There are multiple cache layers, each with its own scope and purpose:

| Cache layer | Scope | Contents held | Typical lifetime |
|---|---|---|---|
| Persistence context / first-level cache | One `EntityManager` | Managed entities by identity | Persistence context lifecycle |
| JPA second-level cache | Shared across persistence contexts in an application/provider | Cached entity or association state | Per provider configuration |
| Hibernate query cache | Hibernate provider | Query results by query/parameters | Per region and invalidation strategy |
| Spring Cache | Application/service layer | Method results, usually DTOs or read models | Per cache manager/provider |
| Distributed cache | Multiple application instances | Shared key/value via Redis or similar system | Per TTL and invalidation |

Do not lump all of these layers into a single kind of cache. The first-level cache is part of the persistence context; Spring Cache is an application-layer abstraction; second-level/query caches belong to the JPA provider.

A single request can traverse multiple layers. For example, if a service method gets a Spring Cache hit, the repository is not called. If Spring Cache misses, the repository may run; Hibernate then checks the persistence context and second-level cache per configuration.

## 3. JPA's first-level cache

Each persistence context has an identity map for managed entities. Within the same `EntityManager`, an entity of the same type and primary key is represented by the same managed instance.

This is a method fragment inside a service with an `EntityManager` injected via `@PersistenceContext`; `Customer` is an application entity.

~~~java
@Transactional
public void demonstrateFirstLevelCache(Long id) {
    Customer first = entityManager.find(Customer.class, id);
    Customer second = entityManager.find(Customer.class, id);

    System.out.println(first == second);
}
~~~

Within the same persistence context, the output is typically:

~~~text
true
~~~

The second call can retrieve the already-managed instance without running another `SELECT` statement for the same primary key.

The first-level cache:

- Is valid only within the current persistence context.
- Is not a shared cache across requests or `EntityManager` instances.
- Tracks changes to managed entities and supports dirty checking.
- Can be emptied with `clear()`, or a single entity can be detached with `detach()`.
- Is not a mechanism for caching arbitrary JPQL query results.

Note: a JPQL query may still be sent to the database even if the corresponding entity is already in the persistence context. When results are mapped, the provider uses the corresponding managed identity. Do not rely on the first-level cache to assume all search queries are skipped.

## 4. JPA/Hibernate's second-level cache

The second-level cache is shared across multiple persistence contexts within the JPA provider's configured scope. It can avoid re-reading cached entity state on subsequent accesses.

JPA provides the `jakarta.persistence.Cacheable` annotation to mark an entity eligible to participate in the second-level cache:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;

@Entity
@Cacheable
public class Country {
    // Entity mapping
}
~~~

This annotation does not provide a cache implementation or TTL policy by itself. You must configure a provider and corresponding cache region factory. With Hibernate, cache strategies can be configured via Hibernate annotations and a suitable cache provider.

Hibernate-specific example:

~~~java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@jakarta.persistence.Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference-country"
)
public class Country {
    // Entity mapping
}
~~~

`READ_ONLY` suits reference data that genuinely does not change during the cache lifetime. If the entity is updated, choose an appropriate concurrency strategy; do not use `READ_ONLY` for frequently written data.

Hibernate strategies such as `READ_ONLY`, `NONSTRICT_READ_WRITE`, `READ_WRITE`, and `TRANSACTIONAL` carry different consistency semantics and costs. Choose based on read/write frequency, consistency needs, and provider/cache backend capabilities.

The second-level cache is helpful when multiple persistence contexts repeatedly read the same entities. However, if the database is updated directly by another application or SQL outside Hibernate, the cache may not receive invalidations. You need a synchronization mechanism or should avoid caching that data.

## 5. Hibernate query cache differs from entity cache

Hibernate's query cache holds the results of a specific query by query key and parameters. It is not synonymous with the second-level entity cache.

A query cache hit can avoid re-executing the query in the manner supported by the provider, yet returned entities may still need to obtain their state from the second-level cache or the database.

The query cache typically requires explicit configuration and suits queries with stable, repeated results best. If a query varies continuously by parameters, sort, page, or underlying data, hit rates can be low and invalidation overhead high.

Do not enable the query cache globally without measuring your workload. With Hibernate, query cache and region invalidation depend on provider/version configuration. Consult the Hibernate documentation for your version before configuring it.

## 6. Spring Cache is an application-layer cache

Spring Cache provides an abstraction over cache providers such as Caffeine, Redis, or other cache managers. Common annotations:

- `@Cacheable`: checks the cache first; runs the method only when the key is absent.
- `@CachePut`: always executes the method and updates the cache with the result.
- `@CacheEvict`: removes a key or an entire cache region.
- `@Caching`: combines multiple cache operations on the same method.

Spring Cache is usually well suited to caching service outputs such as `ProductView`, `CustomerSummary`, or a read model. The cache does not need to know whether data came from JPA, a REST API, or a computation.

Be careful to distinguish two annotations sharing the same name:

- `org.springframework.cache.annotation.Cacheable`: caches method results at the Spring layer.
- `jakarta.persistence.Cacheable`: marks an entity eligible to participate in JPA's second-level cache.

These two annotations serve different purposes and cannot substitute for one another.

## 7. Choosing which data to cache

A good cache candidate typically shares several of these traits:

- Read repeatedly with the exact same set of parameters.
- Significant database read or computation cost.
- Update frequency much lower than read frequency.
- Clearly identifiable keys and conditions affecting the result.
- Ability to tolerate a window in which data does not yet reflect the latest change.
- Bounded data size and key count.
- A suitable invalidation or refresh mechanism.

Examples:

| Data type | Typical suitability | Reason |
|---|---|---|
| Country, province/city catalogs | High | Rarely changes, shared across many requests |
| Product category lists | High | Heavy reads, infrequent updates |
| Public display settings | High if versioned/TTL-bounded | Many requests share the same settings |
| Product details, descriptions | Medium to high | Reusable; requires invalidation upon updates |
| Popular search results | Medium | Effective only if queries/keys repeat |
| Summary dashboards | Medium | Computation may be costly; acceptable freshness must be defined |
| Inventory used for order confirmation | Low if immediate accuracy required | Values change constantly and affect transactions |
| Account balances | Low if strong consistency required | Financial data should not rely on stale cached copies |
| Per-user access permissions | Needs careful evaluation | Permission changes can create security risks |
| Personalized results | Only with complete keys | Must account for user, tenant, locale, and permissions |

This table is a design guide, not an absolute rule. An internal dashboard might tolerate 30-second-old data; an audit report might require data as of query time.

## 8. Deciding whether data is worth caching

Before adding annotations, answer these questions:

1. How many requests read the same data within a given period?
2. What is the current query cost: latency, database CPU, row count, and call volume?
3. How often does the data change?
4. Who or what systems can modify the data?
5. If the cache returns stale data, what is the business impact?
6. Can invalidation target specific keys, or must an entire region be cleared?
7. What are the maximum key count and value size?
8. Will cache hits actually relieve the current bottleneck, or merely shift cost to serialization/network?

If the query is already very fast and keys rarely repeat, caching can add complexity without meaningful benefit.

Measure before caching and measure again afterward. Optimization must be grounded in actual hit ratios, latency, and database load.

## 9. Freshness and staleness budget

Freshness describes how close cached data is to the current source state. Staleness is the gap between cached data and the latest data at the source.

A staleness budget is the maximum level of staleness the business can tolerate.

Examples:

- Country lists: may tolerate hours or days.
- Product content: may tolerate a few minutes if changes do not affect transactions.
- Displayed prices: may need faster refresh depending on customer commitments.
- Displayed inventory: may be shown approximately, while the order confirmation step must verify against the authoritative data source.
- Balances used for fund transfers: must follow financial-system consistency mechanisms rather than relying on ordinary application caches.

Do not pick a TTL first and ask the business afterward whether it is acceptable. Define the staleness budget first, then pick a TTL and invalidation strategy to meet that budget.

TTL only bounds how long an entry is retained per cache policy. It does not guarantee changes appear immediately, nor does it ensure freshness if the cache is populated from a lagging replica.

## 10. Choosing TTL based on data behavior

TTL (time to live) is how long an entry is allowed to stay in the cache before expiring.

Common strategies:

| Strategy | How it works | Best suited for |
|---|---|---|
| expire-after-write | Expires after a duration since the most recent write | Data with a clear freshness budget |
| expire-after-access | Expires after a duration without any access | Infrequently used data gets evicted automatically |
| Short fixed TTL | All keys share one short interval | Moderately volatile results |
| Per-data-type TTL | Each cache region has its own expiration | Applications with varied freshness levels |
| No TTL + invalidation | Evicted only upon update events | Stable data with reliable invalidation |
| Refresh ahead | Refreshes before entry expiration | Hot keys where miss loading is very expensive |

Expire-after-access can keep a hot key alive longer than expected because every read resets its expiration timer. If you need a hard upper bound on data age, expire-after-write is usually more predictable.

TTL should balance cache hits against staleness. A TTL that is too short causes high misses and heavier database load; a TTL that is too long keeps stale data around longer and makes invalidation more critical.

You can add small random jitter to TTLs so keys written at the same time do not all expire together, avoiding abnormal load spikes. Any jitter must stay within the staleness budget.

## 11. Cache-aside: the common service-layer pattern

Cache-aside (lazy loading) is a straightforward pattern:

1. Read cache by key.
2. On a hit, return the cached result.
3. On a miss, read from the data source.
4. Put the result into the cache.
5. Return the result to the caller.

Spring's `@Cacheable` handles most of this flow:

~~~java
@Cacheable(cacheNames = "productBySku", key = "#p0")
public ProductView getBySku(String sku) {
    Product product = repository.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

    return new ProductView(
            product.getSku(),
            product.getName(),
            product.getPrice(),
            product.getUpdatedAt()
    );
}
~~~

When the key is already cached, the method body is skipped. When absent, the method runs and its return value is stored.

Cache-aside is easy to implement and caches only data that is actually read. Its drawback is that the first read after expiration/invalidation must load from the source; if many concurrent requests miss at once, a cache stampede can occur.

## 12. Product domain example used in the following sections

The examples use the `Product` entity in package `com.example.product`.

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal price;

    @Column(nullable = false)
    private Instant updatedAt;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            BigDecimal price,
            Instant updatedAt) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.updatedAt = updatedAt;
    }

    public void changePrice(BigDecimal newPrice, Instant changedAt) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        this.price = newPrice;
        this.updatedAt = changedAt;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Immutable DTO to cache:

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

public record ProductView(
        String sku,
        String name,
        BigDecimal price,
        Instant updatedAt
) {
}
~~~

Repository:

~~~java
package com.example.product;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

`sku` has a unique constraint, so `findBySku` fits `Optional`. The `ProductView` DTO contains only the values needed by the API, holding no proxies or `LAZY` associations.

## 13. Configuring Spring Cache with Caffeine

Caffeine is an in-memory local cache within a single JVM. It offers low latency and supports size bounds, expiration, and statistics.

Required dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Cache configuration:

~~~java
package com.example.product;

import java.time.Duration;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("productBySku");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(5)));

        return manager;
    }
}
~~~

In this example, the `productBySku` cache holds up to roughly 10,000 entries and each entry expires 5 minutes after write. These are illustrative values; production should choose numbers based on active SKU count, DTO size, memory budget, and staleness budget.

A local Caffeine cache does not share data across application instances. When running multiple replicas, each instance maintains its own cache. When one instance updates a product, you need an invalidation mechanism to the remaining instances, or accept that they only refresh once TTL expires.

## 14. Using @Cacheable to cache service results

Service:

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCatalogService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public ProductCatalogService(
            ProductRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional(readOnly = true)
    @Cacheable(cacheNames = "productBySku", key = "#p0")
    public ProductView getBySku(String sku) {
        Product product = repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));

        return toView(product);
    }

    @Transactional
    public void changePrice(String sku, BigDecimal newPrice) {
        Product product = repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));

        product.changePrice(newPrice, Instant.now());
        eventPublisher.publishEvent(new ProductChanged(sku));
    }

    private ProductView toView(Product product) {
        return new ProductView(
                product.getSku(),
                product.getName(),
                product.getPrice(),
                product.getUpdatedAt()
        );
    }
}
~~~

Exception:

~~~java
package com.example.product;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String sku) {
        super("Product not found: " + sku);
    }
}
~~~

When `getBySku("SKU-100")` is called the first time, the repository queries the database and the service constructs `ProductView`. Spring Cache stores the DTO under key `SKU-100`. Subsequent calls within the TTL can return the DTO from cache.

The cached method must be invoked through the Spring proxy. If another method in the same class directly calls a `@Cacheable` method on `this` (self-invocation), the default caching interceptor will not be applied.

In this example, the key uses `#p0` to refer to the first parameter, avoiding reliance on parameter names being preserved in bytecode.

## 15. Why cache DTOs/read models instead of JPA entities?

Caching entities at the application layer can create several problems:

- Entities may be proxies or hold uninitialized `LAZY` associations.
- Managed entities are bound to a persistence context; after the transaction ends they become detached.
- The same entity can be loaded with different fetch plans.
- Modifications to entities or associations may not be reflected in cached objects.
- Proxy serialization and bidirectional relationships can cause circular references or serialization errors.
- Caching entity objects exposes more fields than the API needs to return.

Immutable DTOs/read models are usually easier to cache because they contain only the data required for the use case, without carrying a persistence context or lazy proxies.

Hibernate's second-level cache is a different mechanism: it is designed to cache entity state per provider rules, which is not the same as placing arbitrary entity objects into Spring Cache.

If caching a DTO derived from multiple data sources, keys and invalidation must reflect all of those sources. A simple DTO does not automatically make data consistent.

## 16. Cache keys must represent every input affecting the output

An incorrect cache key can serve one request's data to another request.

If the output depends on the following parameters, all of them must be included in the key:

- SKU or entity ID.
- Tenant or organization.
- Language/locale.
- User or permission group if results are personalized.
- Currency or region.
- Filters, sort, and page if caching search results.
- Configuration or schema version when relevant.

Multi-tenant example:

~~~java
@Cacheable(
    cacheNames = "productByTenantAndSku",
    key = "#p0 + ':' + #p1"
)
public ProductView getByTenantAndSku(
        String tenantId,
        String sku) {
    // Load product within tenant scope.
}
~~~

Do not use SKU as the sole key if the same SKU can exist across multiple tenants.

If a key has multiple components, use an unambiguous format or a key object/`KeyGenerator`. Do not concatenate strings arbitrarily if the delimiter could appear in input data.

Do not include sensitive data in keys if the cache backend, metrics, or logs might expose keys. Use normalized identifiers or hashes when appropriate.

## 17. Using condition and unless

`@Cacheable` can decide whether or not to cache:

~~~java
@Cacheable(
    cacheNames = "productBySku",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public ProductView getBySku(String sku) {
    // Read data.
}
~~~

- `condition` is evaluated before the method runs; `false` means do not use the cache for that invocation.
- `unless` is evaluated after the method runs; `true` means do not store the returned result.

In the main service example, the method throws `ProductNotFoundException` when not found, so exceptions do not become cached values. If a method returns `null` for not-found cases, `unless` can prevent caching `null` provided the cache provider supports the corresponding policy.

Do not cache error results or missing-data states for too long if a record may have just been created. If you want negative caching (caching not-found results), design an explicit representation and a shorter TTL than for existing data.

## 18. Cache misses, negative caching, and newly created data

Cache-aside normally stores only successful results. If a key has no data, every request may keep hitting the database. When many requests ask for a non-existent SKU, the database still bears the load.

Negative caching stores a "not found" state for a brief period. It helps when repeated requests ask for non-existent keys, such as bots or clients polling invalid IDs.

However, negative caching carries a risk: a product might just have been created while the cache still holds the non-existent state. When creating a new entity, evict the corresponding negative entry; TTL should also be short.

Do not use `null` as an ambiguous state if the API needs to distinguish:
- Never queried.
- Queried and not found.
- Data exists, but a specific field is `null`.

Use an explicit result type, such as a sealed result or status DTO, if business logic needs to distinguish those cases.

## 19. Invalidation: clearing caches when data changes

Cache-aside typically uses invalidation: after source data changes successfully, delete the related key. The next read misses and loads fresh data.

Spring provides `@CacheEvict`:

~~~java
@CacheEvict(cacheNames = "productBySku", key = "#p0")
public void evictProduct(String sku) {
}
~~~

Or clear the entire region:

~~~java
@CacheEvict(cacheNames = "productBySku", allEntries = true)
public void evictAllProducts() {
}
~~~

`allEntries = true` can be useful when a change affects many keys, but reduces cache hits across the entire region. Only use it when affected keys cannot be determined or when the region is small enough.

Do not evict the cache before knowing whether the write succeeded, unless invalidation is specifically desired even on method failure. With database transactions, consider eviction timing relative to commit.

## 20. Evicting after transaction commit

If you evict the cache before the database transaction commits, another request may miss the cache and read stale data from the database while the updating transaction has not yet committed. That stale data then gets written back into the cache.

A clean approach is to publish an event inside the transaction and evict only after commit:

Event:

~~~java
package com.example.product;

public record ProductChanged(String sku) {
}
~~~

In `ProductCatalogService`, `changePrice()` already updated the managed entity and published `ProductChanged`. Listener:

~~~java
package com.example.product;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    @CacheEvict(cacheNames = "productBySku", key = "#p0.sku()")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductChanged(ProductChanged event) {
    }
}
~~~

The listener runs only after the transaction commits successfully. If the transaction rolls back, the `AFTER_COMMIT` event listener does not execute eviction.

This works well for caches inside the same application. With Redis or multiple services, ensure invalidation events reach all instances. If losing events is unacceptable, use an outbox/retry or a reliable synchronization mechanism; TTL serves only as a fallback staleness bound.

If an operation changes an entity's SKU or key, evict both the old key and the new key if the cache may hold either. When a change affects multiple views, identify every affected cache region.

## 21. Invalidation is harder than TTL

TTL handles automatic expiration of entries after an interval. Invalidation handles immediate removal when a change becomes known.

Both approaches can be combined:

- Short TTL to cap maximum staleness per policy.
- Event invalidation for fast updates on writes.
- Background refresh to reduce cache misses for hot keys.
- Versioned keys to separate old and new cached entries when data changes by version.

TTL does not replace invalidation when the business requires fast updates. Invalidation also does not replace TTL if events can be lost or an external writer does not emit events.

A race condition can still happen: request A reads old data from the database, request B commits new data and evicts the cache, and then A writes its stale result into the cache. To prevent this scenario, you need version/fencing tokens, locking, version re-checks, or stronger synchronization strategies. TTL alone only limits how long the stale value lingers; it does not eliminate the race.

## 22. How do @CachePut and @CacheEvict differ from @Cacheable?

~~~java
@Cacheable(cacheNames = "productBySku", key = "#p0")
public ProductView getBySku(String sku) {
    // Runs method only on a cache miss.
}
~~~

~~~java
@CachePut(cacheNames = "productBySku", key = "#result.sku()")
public ProductView reloadProduct(String sku) {
    // Always runs method, then writes result into cache.
}
~~~

~~~java
@CacheEvict(cacheNames = "productBySku", key = "#p0")
public void removeProductCache(String sku) {
    // Removes key.
}
~~~

Differences:

| Annotation | Runs method? | Cache action |
|---|---|---|
| `@Cacheable` | Only on miss or when condition skips cache | Reads cache, stores result when needed |
| `@CachePut` | Always runs | Overwrites value with method result |
| `@CacheEvict` | Always runs per method flow | Removes key or region |

Do not attach both `@Cacheable` and `@CachePut` to the same method without clearly understanding their order and intent; the two annotations have distinct meanings. On database-writing methods, ensure cache updates/evictions do not occur before transaction commit in a way that introduces stale data.

## 23. Cache stampede and concurrent cache misses

A cache stampede occurs when a popular key expires or is evicted, and many concurrent requests miss simultaneously and all query the database at once.

Consequences:
- The database receives a sudden traffic spike.
- Many requests perform the same expensive computation simultaneously.
- Latency rises, and timeouts and retries can amplify load.
- The cache is populated repeatedly with the same data.

Mitigations:

1. Single-flight/locking: only one request loads the key while other requests wait or share the loaded result.
2. TTL jitter: avoid having many keys expire at the exact same moment.
3. Refresh ahead: refresh hot keys before they expire.
4. Stale-while-revalidate: temporarily serve stale data within budget while refreshing in the background.
5. Rate limits or bulkheads on the cache-miss loading path.
6. Selective cache warming for popular keys after deployment.

Spring `@Cacheable` has a `sync=true` attribute to request synchronized loading per key in supported cache providers:

~~~java
@Cacheable(
    cacheNames = "productBySku",
    key = "#p0",
    sync = true
)
public ProductView getBySku(String sku) {
    // Single load is synchronized per cache provider capabilities.
}
~~~

The synchronization behavior and limits of `sync` depend on the `Cache` implementation. It is not automatically a distributed lock across JVMs for every provider. Check your cache manager's documentation before relying on this feature.

## 24. Local cache or distributed cache?

| Criterion | Local Caffeine | Redis/distributed cache |
|---|---|---|
| Latency | Very low, same JVM | Has network round-trip |
| Shared across instances | No | Yes |
| Invalidation | Must handle per instance | Can share keys or use pub/sub |
| Memory | Heap of each instance | External memory outside application |
| Serialization | Typically holds in-JVM objects | Requires suitable format/serialization |
| Operations | Simpler | Requires operating and monitoring cache system |
| Best suited for | Hot data, instance-local scope | Shared caches across replicas/services |

Caffeine suits read-heavy data where each instance refreshing independently is acceptable. Redis fits when multiple instances must share a cache or when keys must outlive JVM lifecycles.

A distributed cache does not automatically solve consistency. It merely provides a shared key/value store; the application still needs to design TTLs, invalidation, key versioning, retries, and handling when the cache backend is unavailable.

## 25. Caching pages and search results

Search results or `Page` objects can be cached, provided the key includes every factor affecting the result:

- Filters.
- Page number and page size.
- Sort field and direction.
- Tenant/organization.
- Locale/currency if content depends on it.
- Permissions if results are filtered by user/role.

For example, two requests with identical filters but different page sizes must not share a cache key. Likewise, the same page number with different sorting produces two different results.

Search results have high cardinality, low key repetition, and difficult invalidation. Do not cache every filter combination by default. Only cache popular queries with clear reuse and bounded key counts.

With `Page`, `totalElements` can also change when data is inserted or deleted. If caching content and count together, you must tolerate staleness in both. If the total count needs to be fresher than content, consider caching them separately or not caching `Page`.

Do not cache entity pages containing uninitialized lazy associations. DTO projections generally serialize more cleanly and offer clearer contracts.

## 26. Caching and data security

Cache keys must include every security context affecting the output. If results vary by tenant, user, role, locale, or permissions, never use a shared key.

Risk examples:
- User A has permission to view internal fields; User B does not.
- Two tenants have the same SKU with different product data.
- A response is personalized by currency or region.
- A user's permissions are revoked, yet the cache still serves previously granted data.

If you cannot reliably incorporate security context into keys and invalidation, do not cache personalized results. You can cache shared underlying data and apply authorization checks after reading.

Do not store secrets, tokens, or sensitive data in cache keys or values without a clear need and appropriate protections. Redis caches also require authentication, network policies, and access controls just like databases.

## 27. Caching and data modified outside the application

Spring Cache or Hibernate does not automatically know about all database changes. Data can be updated by:

- Another service.
- Batch jobs or schedulers.
- Operational SQL scripts.
- Stored procedures.
- Database administrators.
- CDC or synchronization pipelines.

If these writers do not emit invalidation events, caches can hold stale data until TTL expires or manual eviction occurs.

Before caching a table, list every writer and how it notifies changes. If writers are outside your control, choose a TTL matching the staleness budget, use CDC/event invalidation, or avoid caching data requiring maximum freshness.

Especially for the second-level cache, updating the database directly outside Hibernate can leave the provider unaware of which regions need invalidation.

## 28. Monitoring cache effectiveness and operations

A cache requires metrics and alerting. Useful metrics:

| Metric | Meaning |
|---|---|
| Hit ratio | Share of requests served from cache |
| Miss rate | Frequency of having to load from source |
| Load latency | Time taken to load a value on miss |
| Eviction count | Entries removed due to capacity/expiration |
| Cache size/weight | Memory currently in use |
| Expiration rate | Number of expired entries |
| Backend errors | Cache connection/read/write errors |
| Hot keys | Keys with very high access frequency |
| Stampede/concurrent loads | Multiple requests loading one key concurrently |
| Staleness/age | Age of data or time since last refresh |

A high hit ratio is not necessarily good if data is stale or the cache holds excessive unnecessary data. A low hit ratio is not necessarily bad if the cache serves a few extremely expensive queries.

Monitor database QPS, query latency, API latency, and heap simultaneously. The goal is improving user experience and system load while staying within the freshness budget.

You can use actuator/cache metrics and provider metrics. Exact metric names depend on the Spring Boot, Micrometer, and cache backend versions in use.

## 29. Testing the cache

Tests should verify both cache hits and invalidation, not just that a method returns the expected data.

Scenarios to test:

1. First read calls the repository and creates a cache entry.
2. Subsequent read with the same key returns the cached result.
3. A different key does not mistakenly reuse the entry.
4. Data changes emit invalidation after commit.
5. Transaction rollback does not evict the cache under `AFTER_COMMIT` events.
6. Keys by tenant/locale are not mixed.
7. Expired-TTL entries are reloaded.
8. Cache backend failures are handled per application policy.
9. Multiple concurrent miss requests do not cause uncontrolled source load.

Example test verifying the entry is stored:

~~~java
@SpringBootTest
class ProductCacheTest {

    @Autowired
    private ProductCatalogService service;

    @Autowired
    private ProductRepository repository;

    @Autowired
    private CacheManager cacheManager;

    @BeforeEach
    void prepare() {
        cacheManager.getCache("productBySku").clear();
        repository.deleteAll();
        repository.save(new Product(
                "SKU-100",
                "Keyboard",
                new BigDecimal("49.90"),
                Instant.parse("2026-01-01T00:00:00Z")
        ));
    }

    @Test
    void cachesProductViewBySku() {
        ProductView first = service.getBySku("SKU-100");

        Cache.ValueWrapper cached =
                cacheManager.getCache("productBySku").get("SKU-100");

        assertThat(first.name()).isEqualTo("Keyboard");
        assertThat(cached).isNotNull();
        assertThat(cached.get()).isEqualTo(first);
    }
}
~~~

Main imports for the test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
~~~

This test assumes `ProductCacheTest` sits in package `com.example.product`, alongside `Product`, `ProductView`, and the service. The application must have `CacheConfiguration`, a test database, and Spring Cache enabled.

To prove the repository is not called a second time, you can use a spy/mock repository in an appropriate test slice or inspect SQL statement counts via a datasource proxy. To test `AFTER_COMMIT` invalidation, actually commit a real transaction in the test; a test transaction that rolls back by default will not trigger the `AFTER_COMMIT` phase like a successfully committed transaction.

## 30. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Data stays stale too long | TTL too long or missing invalidation | Define staleness budget and evict on writes |
| Low cache hit rate | Keys too varied or TTL too short | Measure key distribution and adjust cache scope |
| Database still overloaded on expiration | Cache stampede | Single-flight, refresh ahead, or jitter |
| User receives another tenant's data | Cache key missing tenant | Include tenant in key or do not cache that result |
| API fails returning entity post-transaction | Caching JPA entity/proxy with lazy associations | Cache DTOs/read models |
| Cache cleared before commit | Invalidation runs at wrong transaction phase | Evict after commit |
| Cache unchanged after direct SQL | External writer emits no events | CDC/invalidation or suitable TTL |
| Instances return inconsistent data | Local cache per JVM has separate state | Sync invalidation or use a distributed cache |
| Cached page has wrong sort/filter | Key missing query parameters | Include every input affecting the output |
| Cache consumes too much heap | Unbounded entries/values | `maximumSize`/weight, TTL, and metrics |
| Negative cache retains non-existent state | Entity just created while miss entry has not expired | Evict on creation or use short TTL |
| `@Cacheable` does not work | Self-invocation or caching not enabled | Invoke via Spring proxy and enable `@EnableCaching` |
| `@CachePut` writes stale value | Cache updated before transaction commit | Sync cache updates after commit |
| Query cache fails to improve performance | Low query repetition or frequent invalidation | Measure workload and enable only for suitable queries |

## 31. Process for choosing caching for a use case

You can follow this process:

1. Identify the use case and returned data.
2. Measure query latency, read frequency, write frequency, and distinct key count.
3. Identify all writers and every data update path.
4. Set a staleness budget along with the consequences of stale data.
5. Choose the cache layer: Spring Cache, JPA second-level, query cache, or no cache.
6. Design DTOs/keys, including tenant and all parameters affecting results.
7. Choose TTL, maximum size/weight, and invalidation strategy.
8. Handle cache stampedes and cache backend unavailability.
9. Write tests for hits, misses, invalidation, rollback, and key isolation.
10. Monitor metrics and tune with production data.

If data requires strong consistency, caching may only fit display or reference reads. Final decision-making operations still must verify against the authoritative data source.

## 32. Self-assessment checklist

- [ ] Distinguished first-level cache, second-level cache, query cache, and Spring Cache.
- [ ] Understood that the persistence context only shares entities within an `EntityManager`'s scope.
- [ ] Knew that JPA `@Cacheable` differs from Spring `@Cacheable`.
- [ ] Selected data with high read reuse and significant load cost.
- [ ] Identified all writers and update frequencies.
- [ ] Set a freshness/staleness budget before choosing TTL.
- [ ] Distinguished expire-after-write and expire-after-access.
- [ ] Bounded cache size and memory.
- [ ] Used DTOs/read models when caching service outputs.
- [ ] Designed keys including tenant, locale, permissions, and filters when relevant.
- [ ] Used `@Cacheable`, `@CachePut`, and `@CacheEvict` for their intended purposes.
- [ ] Evicted after commit when transaction consistency requires it.
- [ ] Had a strategy for negative caching and newly created data.
- [ ] Identified cache stampedes and chose load-shedding mitigations.
- [ ] Distinguished local and distributed caches.
- [ ] Controlled invalidation from batch jobs or external writers.
- [ ] Monitored hit ratio, misses, evictions, latency, size, and backend errors.
- [ ] Tested cache hits, misses, expiry, invalidation, and transaction rollbacks.
- [ ] Avoided caching data whose freshness/authorization requirements cannot be met.

## 33. Conclusion

Choosing a cache starts from data characteristics and business requirements. Read-heavy, rarely changing, expensive-to-load data that can tolerate some lag is usually a strong candidate. Continuously changing, sensitive, or transaction-deciding data should be handled with appropriate consistency mechanisms.

Set a staleness budget before picking a TTL; combine TTL with invalidation when fast updates are needed; design complete keys; cache appropriate DTOs; and control cache stampedes. Distinguish Spring Cache from JPA/Hibernate's first-level, second-level, and query caches to choose the right layer. Finally, measure hits/misses, latency, memory, and backend errors to verify caching truly improves the system while keeping data within the staleness limits the business accepts.
