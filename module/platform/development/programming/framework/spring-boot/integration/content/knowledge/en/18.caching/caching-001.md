# Spring Cache, CacheManager, and @EnableCaching

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot can integrate with databases, HTTP APIs, caches, message brokers, and Spring Integration adapters. When the same data is read repeatedly from a database or downstream HTTP service, caching reduces load and shortens latency. However, a cache also creates a copy of data that may be **older than the source**, so the design must account for data contracts, updates, transactions, errors, duplicate handling, testing, and observability.

This lesson belongs to the **Caching** chapter and focuses on three concepts:

- **Spring Cache:** an abstraction that marks methods requiring cache read/write/eviction using annotations.
- **`CacheManager`:** the component that manages caches by name; the bridge between the abstraction and the cache provider.
- **`@EnableCaching`:** enables processing of cache annotations via Spring AOP in the application context.

After this lesson, you will be able to set up caching in Spring Boot, choose a cache provider, distinguish the behavior of `@Cacheable`, `@CachePut`, and `@CacheEvict`, design cache keys, test cache hits/misses, and identify the limitations of caching in integration flows.

## 1. How Does Spring Cache Work?

Spring Cache is a **method-invocation-level abstraction**, not a storage server and not a mechanism that decides data time-to-live (TTL) on its own. Spring coordinates looking up results or updating the cache; a concrete **provider** such as Caffeine or Redis is responsible for storage.

When a Spring-managed bean receives a call through a **proxy**:

1. The cache interceptor analyzes the annotation and determines the cache name, cache key, and conditions.
2. The interceptor asks `CacheManager` to retrieve the cache by name; the cache implements the `org.springframework.cache.Cache` interface.
3. With `@Cacheable`, if a matching entry exists (cache hit), Spring returns the stored result without invoking the method body.
4. If it is missing (cache miss), Spring invokes the actual method and, depending on conditions, puts the result into the cache.
5. With `@CachePut`, the method still executes; with `@CacheEvict`, the corresponding entry is removed according to the annotation rules.

~~~mermaid
flowchart TD
    A["HTTP controller / use case"] --> B["Spring AOP cache proxy"]
    B --> C{"@Cacheable: key present?"}
    C -->|"Hit"| D["Cache provider returns copy"]
    D --> E["Result to caller"]
    C -->|"Miss"| F["Invoke service method"]
    F --> G["DB / downstream HTTP adapter"]
    G --> H["Store result in Cache"]
    H --> E
    I["CacheManager"] -.-> C
    I -.-> H
~~~

Business example: `ProductQueryService.findById("P-100")` calls a catalog HTTP API. The first call must reach out externally; subsequent calls can return cached data. If the product has been updated at the source while the cache has not been evicted or expired, subsequent reads may no longer be fresh.

**Boundary of responsibility:** a cache improves read performance; a cache is not the authoritative source of truth, does not automatically create distributed transactions, and does not guarantee instant consistency across systems.

## 2. Dependencies and Enabling `@EnableCaching`

Gradle (Groovy DSL) example for a Spring Boot application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

`spring-boot-starter-cache` provides the dependencies supporting Spring's cache mechanism. To use a specific provider like Caffeine, you need to add the corresponding library as shown in a later section.

Declare configuration enabling caching in a specific `@Configuration` class:

~~~java
// CacheConfiguration.java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
~~~

**Role of `@EnableCaching`:**

- Activates the infrastructure for processing cache annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`.
- In the default mode `mode = AdviceMode.PROXY`, Spring creates proxies to intercept matching calls.
- Without enabling caching, adding `@Cacheable` to a service **does not automatically make Spring cache data**.
- Spring Boot only auto-configures the cache infrastructure when caching is enabled and the auto-configuration conditions are satisfied.

It is good practice to keep this annotation in a dedicated configuration class rather than attaching it by default to the `@SpringBootApplication` class if you want certain tests or environments to be able to enable or disable caching easily.

> **Key takeaway:** `@EnableCaching` enables the AOP mechanism; `CacheManager` determines the specific caches provided; method annotations express when and under what key to cache.

## 3. CacheManager, Cache, and Spring Boot Providers

Two important interfaces:

~~~java
// Illustrating core methods only
public interface CacheManager {
    Cache getCache(String name);
    Collection<String> getCacheNames();
}
~~~

`CacheManager` is not the cache data itself; it locates or manages named cache regions such as `productsById` and `inventoryBySku`. Each cache region implements `Cache`, providing lookup/write/delete operations such as `get`, `put`, `evict`, and `clear` (the exact API may include additional methods depending on the Spring version).

Spring Boot has a mechanism to detect providers based on the classpath and configuration. If no other suitable provider is present, Boot can fall back to **Simple cache** backed by an in-process `ConcurrentHashMap`. That is convenient for quick experiments, but should not be treated as a default production configuration: memory can grow unbounded with the number of keys, there is no automatic TTL, and the cache is not shared across instances.

| Provider | Storage mechanism | Suitable use cases | What to control |
| --- | --- | --- | --- |
| Simple (`ConcurrentMapCacheManager`) | Single JVM heap | Demos, tests, quick annotation trials | No default TTL/size limit; per-instance cache only |
| Caffeine | Single JVM heap, with eviction | High-speed local lookup cache | Configure TTL/size; handle stale data across multiple instances |
| Redis | Networked cache store | Multiple instances needing a shared cache | Network latency, connections, TTL, serialization, data versioning |
| JCache and other providers | Per JSR-107/provider implementation | Organizations standardized on another provider | Eviction rules, configuration, and provider behavior |

Do not assume that every feature (TTL, atomic operations, async retrieval, distributed locking, serialization) is standardized by Spring Cache. You must understand the behavior of the chosen provider.

### Configuring Caffeine to Run Examples

Add Caffeine to the project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Declare in `application.yml`:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names:
      - productsById
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=300s
~~~

Meaning:

- `spring.cache.type: caffeine` instructs Boot to select Caffeine when the supporting dependency is present.
- `cache-names` lists pre-configured cache regions; in the example, `productsById`.
- `maximumSize=10000` limits the number of entries according to Caffeine's eviction policy; it does not mean an exact byte-size limit.
- `expireAfterWrite=300s` expires entries based on elapsed time since write; reads do not extend that deadline.

These settings illustrate a read cache policy that can tolerate up to a few minutes of stale data. **The appropriate TTL must come from business requirements**: shipping rates may differ from product descriptions; account balances or authorization decisions require much stricter consistency.

If you declare a custom `CacheManager` bean, Boot's auto-configured manager may back off in favor of your bean; in that case, you take full responsibility for configuring the provider. Do not declare a custom `CacheManager` if Boot's auto-configuration already meets your needs.

### Explicitly Selecting a Provider in Another Environment

To disable real cache storage in a test while still allowing code to use annotations:

~~~yaml
spring:
  cache:
    type: none
~~~

The value `none` uses a no-op cache manager, so every invocation executes the actual method. Note that testing cache hits/misses must run against a real provider or a mock that actually stores data; setting `type: none` will not verify caching.

## 4. A Complete Example: Caching Read Results from an HTTP Adapter

Suppose a Catalog API provides product information. The application needs to avoid repeated HTTP calls for the same ID within a short period.

Define the data contract and retrieval port:

~~~java
// ProductView.java
public record ProductView(
        String id,
        String name,
        long version) {
}
~~~

~~~java
// ProductGateway.java
public interface ProductGateway {
    ProductView fetchById(String productId);
}
~~~

`ProductGateway` can be implemented by a REST client, a database repository, or a suitable integration adapter; this lesson focuses on **the service whose results are cached**, independent of HTTP library details.

~~~java
// ProductQueryService.java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductGateway gateway;

    public ProductQueryService(ProductGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(
            cacheNames = "productsById",
            key = "#p0",
            unless = "#result == null")
    public ProductView findById(String productId) {
        return gateway.fetchById(productId);
    }
}
~~~

Analysis:

- `cacheNames = "productsById"` selects the cache region, matching the configured name.
- `key = "#p0"` uses the first argument as the key. You can write `#productId` when parameter names are preserved in bytecode and Spring can access the metadata.
- `unless = "#result == null"` prevents caching `null` results, avoiding keeping a "not found" lookup cached indefinitely.
- When `gateway.fetchById(...)` throws an exception, the call produces no successful result to store in the cache under the default mechanism.
- Spring only intercepts calls going **through the proxy**; calling the method twice from another bean to `ProductQueryService` is what demonstrates caching in action.

Example of two consecutive calls within the TTL:

~~~java
ProductView first = productQueryService.findById("P-100");  // Miss: calls gateway
ProductView second = productQueryService.findById("P-100"); // Hit: uses cache
~~~

If the HTTP side returns 404, the adapter must decide whether to convert it to `null`, an explicit "not found" object, or a business exception. Do not cache error results by default just to reduce downstream calls: **negative caching** requires its own TTL and policy to avoid masking newly created data.

### Layered Design Instead of Scattering Caches Everywhere

A maintainable integration system can follow this diagram:

~~~mermaid
flowchart LR
    A["ProductController"] --> B["ProductQueryService (@Cacheable)"]
    B --> C["ProductGateway (contract)"]
    C --> D["HTTP / DB adapter"]
    B -.-> E["CacheManager"]
    E -.-> F["Caffeine / Redis"]
~~~

Placing `@Cacheable` at a **query boundary that is stable in business meaning** keeps the rest of the application unaware of the underlying provider. Avoid caching data that depends on request identity, permissions, or tenant using a key containing only `productId`.

## 5. Distinguishing Caching Annotations

| Annotation | Is the method body called? | Impact on cache | Use case |
| --- | --- | --- | --- |
| `@Cacheable` | No on hit; yes on miss | Writes result on miss when conditions match | Expensive read operations |
| `@CachePut` | **Always called** | Writes/updates result after method succeeds | Updating a cache entry with a newly saved result |
| `@CacheEvict` | Usually yes; eviction applies at the specified timing | Deletes a key or entire region | Removing stale copies when source data changes |
| `@Caching` | Depends on nested annotations | Combines multiple cache effects | A change affecting multiple cache regions |
| `@CacheConfig` | Does not enable caching on its own | Sets default cache name/key generator/manager at class level | Reducing configuration repetition |

### Evicting Cache After Updating Data

Suppose a command service modifies a product and callers need to read fresh data:

~~~java
// ProductCommandService.java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class ProductCommandService {

    private final ProductStore store;

    public ProductCommandService(ProductStore store) {
        this.store = store;
    }

    @CacheEvict(cacheNames = "productsById", key = "#p0")
    public void updateName(String id, String newName) {
        store.updateName(id, newName);
    }
}
~~~

`ProductStore` is an assumed storage adapter interface with an `updateName` method. In the normal synchronous model, `@CacheEvict` runs by default **after the method returns successfully**. If the method throws an exception, eviction does not run by default. With `beforeInvocation = true`, eviction happens before running the method body, even if the update operation fails—use this only when that exact behavior is required.

**Very important note on transactions:** if `updateName` participates in a database transaction, the moment the method returns **is not necessarily when the transaction has committed**. An eviction occurring before commit can allow a reader to reload stale data back into the cache. For business logic requiring consistency, design post-commit invalidation or use an appropriate transaction-aware cache and explicitly test advice/transaction ordering. If the update happens on an external system over HTTP, a local database `@Transactional` does not make the remote operation participate in the same ACID transaction.

### Writing Fresh Results with `@CachePut`

If the update method returns the new data itself and the contract guarantees that representation matches what queries use, you can update the cache:

~~~java
@CachePut(cacheNames = "productsById", key = "#p0")
public ProductView updateProduct(String id, UpdateProductCommand command) {
    return store.saveAndReturn(id, command);
}
~~~

The abbreviated example above assumes `store.saveAndReturn(...)` returns the successfully saved `ProductView`. You must also verify commit boundaries and the effect of concurrent readers. Do not place both `@Cacheable` and `@CachePut` on the same method expecting it to "both skip execution and always execute": the two annotations have different purposes and combining them directly is usually hard to reason about reliably.

### Evicting an Entire Cache Region

~~~java
@CacheEvict(cacheNames = "productsById", allEntries = true)
public void refreshEntireCatalog() {
    catalogSynchronizer.refresh();
}
~~~

`allEntries = true` ignores the key and affects every entry in the selected region. This is an expensive operation if many requests miss simultaneously right after eviction. Use it only when an event genuinely invalidates the entire dataset, or when you have protection against load spikes.

## 6. Cache Key Design, Conditions, and Preventing Duplicate Loads

### Key Generation Rules

When `key` is omitted, Spring Cache uses a default key generation mechanism based on parameters: no parameters → `SimpleKey.EMPTY`; one parameter → that object itself; multiple parameters → a composite `SimpleKey`. This default is convenient, but **a technically valid key is not necessarily a business-correct key**.

| Scenario | Suggested key | Risk if information is missing |
| --- | --- | --- |
| Public product by ID | `productId` | Low risk if data is truly global |
| Product per tenant | `tenantId + ":" + productId` | Returning wrong data across tenants |
| Price by currency | `productId + ":" + currency` | Returning wrong currency or price |
| Permission-dependent data | Separate cache per role/user or do not cache | Sensitive data leakage |
| Paginated API | Canonical `filter + sort + page + size` | Key collisions or returning wrong page |

Example of a tenant-scoped key:

~~~java
@Cacheable(
        cacheNames = "tenantProducts",
        key = "#p0 + ':' + #p1")
public ProductView findForTenant(String tenantId, String productId) {
    return gateway.fetchForTenant(tenantId, productId);
}
~~~

The tenant parameter must be reliably determined by the authentication/authorization system. For complex keys, or when string delimiters could collide, use an immutable key value object or a structured `KeyGenerator`. If the provider is Redis, inspect the key serializer to avoid unreadable structures or instability after deploying a new version.

### `condition`, `unless`, and `sync`

- `condition` decides **before calling the method** whether caching applies, based on the arguments.
- `unless` decides **after having a result** whether to reject storing the result in the cache.
- `sync = true` requests synchronizing value loading for the same key where supported by the provider, to limit multiple threads computing the same result on concurrent cache misses.

Example of not caching overly broad or invalid lookup requests:

~~~java
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()",
        unless = "#result == null")
public ProductView findById(String productId) {
    return gateway.fetchById(productId);
}
~~~

If the application needs to avoid multiple threads loading the same key simultaneously, you can use:

~~~java
@Cacheable(cacheNames = "productsById", key = "#p0", sync = true)
public ProductView findByIdSingleFlight(String productId) {
    return gateway.fetchById(productId);
}
~~~

**Limitations:** synchronization support depends on `Cache`/provider and is not equivalent to a cluster-wide distributed lock. With `sync = true`, Spring Cache imposes restrictions such as not supporting `unless` and allowing only a single cache; do not blindly copy `sync = true` alongside every option from other examples. Mitigating "cache stampede" across multiple instances may also require jittered TTLs, single-flight/distributed coordination, or prewarming based on actual needs.

## 7. Consistency, TTL, Errors, and Duplicate Handling in Integration

### Cache-Aside and Stale Data

`@Cacheable`'s read-on-miss-then-populate pattern closely follows the **cache-aside** pattern:

1. Read from the cache if present.
2. On miss, call the adapter to the data source.
3. Write the result and return it to the caller.
4. When the source changes, actively invalidate/update or wait for TTL expiration.

TTL is a **general staleness-bounding policy**, not a guarantee that every reader immediately sees the new value when the source changes. Especially across multiple instances with local caches, each instance has its own data lifecycle.

### External Updates Outside the Application

If another system also modifies data in the database or remote service, `@CacheEvict` on the current application's command service will **not be triggered**. Additional options are needed:

- Short TTL if the business can tolerate stale data.
- `ProductUpdated(productId, version)` events over a broker so consumers evict or update related caches.
- CDC/outbox or version-based synchronization if you need to reduce the risk of lost events.
- A shared cache provider (e.g., Redis) lets multiple instances see the same cache region, though proper invalidation rules are still required.

Events from a broker may arrive duplicated, late, or out of order. Repeated eviction of the same key is generally safe, whereas updating cache data from events requires comparing a reliable version/timestamp to prevent an old event from overwriting a newer entry.

### Cache Does Not Replace Idempotency

Keeping a value in cache can reduce repeated HTTP read calls, but it is not an **idempotency** mechanism for order creation or payments. Cache entries can expire, be evicted, be lost on restart, or become out of sync across instances. For write requests requiring "exactly-once processing per business key", design idempotency keys, unique constraints, and deduplication workflows at the system that owns the data.

### Provider Errors Must Be Treated as a Design Branch

By default, errors arising from cache operations can propagate to the caller. When a Redis cache is unavailable, the system must decide whether to allow reading directly from the source. A custom `CacheErrorHandler` can swallow certain cache errors to allow fallback, but doing so can cause load spikes on downstream systems and is unsuitable for data where the cache acts as a safety gate.

Do not silently "ignore all cache errors" on critical flows. Control provider timeouts, bound fallback load, apply circuit breakers/rate limits as needed, emit structured logs, and alert on hits/misses/errors. Avoid recording sensitive data in cache keys and metric labels.

## 8. AOP Limitations: Cases Where Annotations Have No Effect

### Self-Invocation

A commonly confusing example:

~~~java
@Service
public class ProductFacade {

    public ProductView lookup(String id) {
        return findById(id); // internal call via this, bypasses cache proxy
    }

    @Cacheable(cacheNames = "productsById", key = "#p0")
    public ProductView findById(String id) {
        return slowLoad(id);
    }

    private ProductView slowLoad(String id) {
        // ...
        throw new UnsupportedOperationException("Illustration");
    }
}
~~~

When `lookup()` calls `findById()` on the same object, the call normally bypasses the proxy, so the annotation on `findById` is not processed. Place the cached method in a separate service bean and call it through the Spring-injected bean; do not work around this by calling your own proxy unless truly necessary.

Additional cases to check:

- Methods on objects created with `new` outside the Spring container are not managed by AOP.
- `private` methods, or internal calls to annotated methods, do not behave like public methods invoked through a proxy.
- Annotations invoked during initialization such as `@PostConstruct` may not yet have a ready proxy available.
- Depending on Java/Kotlin and proxy type, `final` methods/classes can prevent interception; check your project's proxy configuration.
- Caching and `@Transactional` can both rely on AOP; advice ordering and commit timing must be tested in update flows.

**Quick way to verify:** instrument the adapter/fake gateway with a counter; invoke the method multiple times through the injected bean. If the counter still increments when the same key is called again, check `@EnableCaching`, proxying, the key, the `unless` condition, and the provider.

## 9. Testing Caching Behavior

It is not enough to simply see the application start up and have a `CacheManager` bean. Tests should verify specifically **whether the actual method call is skipped** and **whether data is invalidated after changes**.

### Key Test Scenarios

| Scenario | How to verify |
| --- | --- |
| Cache miss then hit | Call twice with the same ID via the service bean; fake gateway is called once |
| Different keys | Call with another ID; fake gateway runs accordingly |
| Evict after successful update | Query, update via command bean, query again; query must reload fresh data |
| Failed update | Simulate store throwing an exception; verify policy does not wrongly evict/write cache |
| TTL expiration | Use a provider with a short TTL or fake clock; must reload after expiration |
| Multi-tenant | Same productId with different tenantIds must not share results |
| Provider disconnected | Ensure fallback/failure mode matches the integration contract |
| Concurrent transactions | Verify invalidation happens at the expected timing relative to commit |

Example assertions in a `@SpringBootTest` with caching enabled and a fake `ProductGateway` with a call counter:

~~~java
@Test
void sameProductIsLoadedOnlyOnce() {
    ProductView first = productQueryService.findById("P-100");
    ProductView second = productQueryService.findById("P-100");

    assertEquals(first, second);
    assertEquals(1, countingProductGateway.callsFor("P-100"));
}
~~~

The test above assumes JUnit imports and that the `countingProductGateway` fixture is injected by Spring as `ProductGateway`; the service call must go through the Spring-provided bean. Do not call `new ProductQueryService(fakeGateway)` to test AOP, because that object is not proxied by Spring. You must also clear/reset the cache between tests if sharing an `ApplicationContext` to avoid order-dependent test results.

### Ensuring Tests Use the Right Cache Type

- Unit tests for adapter mapping/DTO logic do not need Spring cache.
- Integration tests for annotations require `@EnableCaching` and a `CacheManager` that actually stores data.
- Contract tests for external APIs need a separate HTTP stub, measuring request counts to confirm caching actually reduces adapter calls.
- Tests involving Redis/transactions must reflect real provider conditions and multiple instances if that is a quality requirement.

## 10. Observability and Operations

A cache is only useful when you can observe its effectiveness and risks. With Actuator/Micrometer and an appropriately instrumented provider, you can track metrics such as cache hits, misses, entry count, evictions, source load duration, backend errors, and p95/p99 latency. Exact metric names and availability depend on the Spring Boot/provider version, so verify them in the actual runtime environment.

Suggested operational targets:

| Metric | Operational question |
| --- | --- |
| Hit ratio | Is it actually reducing request volume to downstream HTTP/DB? |
| Miss rate per cache | Is data churning, are keys overly fragmented, or is TTL too short? |
| Eviction count/size | Is the cache overly memory-constrained or holding unused entries? |
| Downstream request rate | After enabling caching, did total load on the source decrease? |
| Stale data rate | Does update lag exceed business SLAs? |
| Cache backend errors | Is Redis/the provider introducing a new failure point in the integration flow? |

`/actuator/caches` can show which caches are managed when the endpoint is enabled and accessible; do not assume this endpoint dumps all cached data. Do not expose cache management endpoints publicly without restriction. Cache names and metric tags must have bounded cardinality—avoid putting product IDs, tenant IDs, or personal information directly into labels.

## 11. When to Use Spring Cache, and When Not To?

**Consider Spring Cache** when read methods are invoked repeatedly, inputs form clear keys, results are reusable, and the business tolerates controlled staleness. Examples include slowly changing catalogs, versioned configuration metadata, exchange rates with defined validity windows, or static lookup tables.

**Do not apply it indiscriminately** to write operations, results depending on security context hard to express in a key, strongly consistent data, large streaming flows, or calls with side effects. For flows returning `Mono`/`Flux`, specifically check asynchronous caching support in your Spring Framework/provider version: since Spring Framework 6.1 there is adaptation for `CompletableFuture` and reactive types, though not all providers support async retrieval identically. For `Flux`, results may be collected into a list for caching, which is unsuitable for infinite or very large streams. If reactive caching is a core requirement, test end-to-end rather than assuming annotations simply store the publisher as-is.

## 12. Pre-Deployment Checklist

- [ ] `@EnableCaching` is placed in the right configuration scope, and services are called through Spring proxies.
- [ ] Appropriate provider chosen: Simple for testing, Caffeine for local cache, Redis when a shared cache is required.
- [ ] Cache names/keys distinguish tenant, locale, currency, or any conditions that alter results.
- [ ] Size and TTL are set appropriately based on business-acceptable staleness limits.
- [ ] Clear separation of which methods use `@Cacheable`, and when `@CacheEvict` or `@CachePut` applies.
- [ ] Transaction commits, updates from external systems, late events, and duplicate handling have been addressed.
- [ ] Tested hits/misses, distinct keys, invalidation, provider timeouts/errors, and multi-instance boundaries when needed.
- [ ] Operational metrics, downstream monitoring, and cache outage handling policies are in place.

**Technical conclusion:** `@EnableCaching` activates the mechanism, `CacheManager` provides storage regions, and `@Cacheable`/`@CachePut`/`@CacheEvict` describe behavior at method boundaries. The quality of a Spring Boot integration depends far more on **cache keys, TTL, invalidation timing, and data contracts** than on merely adding annotations.

## References

- [Spring Boot Reference — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): auto-configuration, cache providers, Caffeine, and `spring.cache.*` properties.
- [Spring Framework Reference — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): overview of the cache model and interfaces.
- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, cache keys, proxy/self-invocation, and reactive behavior.
