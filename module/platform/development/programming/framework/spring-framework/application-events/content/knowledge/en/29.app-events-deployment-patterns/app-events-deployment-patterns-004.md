# Cache Eviction After Data Updates with Spring Application Events

## 1. The Problem: The Database Changed, Yet Readers Still Receive Old Data

When an application implements **cache-aside**, a service reads a record from a database or API, stores the result under a key, and returns the cached copy on subsequent queries. This improves performance, but the cached copy becomes **stale data** if the data source changes without refreshing or invalidating the cache.

For example, product `P-1` has price 100:

~~~text
t0: Database holds P-1, price=100
t1: GET P-1 -> CACHE MISS -> DB returns 100 -> cache[P-1]=100
t2: GET P-1 -> CACHE HIT  -> returns 100
t3: UPDATE P-1 -> database price=150
t4: GET P-1 -> CACHE HIT  -> returns 100 (STALE)
~~~

A clean deployment pattern in Spring:

1. The service updates the **source of truth**.
2. The service publishes a `ProductUpdated(productId)` event describing that the record changed.
3. A listener receives the event and calls a `@CacheEvict` method or `Cache.evict(...)` to remove the corresponding entry.
4. The next read misses the cache, queries the DB, and populates the cache with fresh data.

~~~text
ProductApplicationService.updatePrice("P-1", 150)
     |
     +-- repository.updatePrice("P-1", 150)
     |
     +-- publisher.publishEvent(ProductUpdated("P-1"))
                      |
                      v
             @EventListener
             ProductCacheInvalidationListener
                      |
                      v
             ProductCacheService.evict("P-1")
             @CacheEvict(cacheNames="products", key="#p0")
                      |
                      v
             Entry "P-1" is evicted
                      |
                      v
       GET P-1 -> MISS -> DB price=150
~~~

**Keep in mind:** an in-process event only **triggers the cache-eviction action**; it does not replace a database transaction and does not automatically provide message delivery guarantees, retries, or synchronization across multiple JVMs. Deciding **when to evict**, **which keys to evict**, and **on which instances** is a crucial part of the design.

## 2. Distinguish the Right Kind of Cache to Evict

| Cache Type | What Data Does It Store? | Needs Handling When Updating a Product? |
| --- | --- | --- |
| **Business/data cache** | Product details, DTOs, query results, product summaries. | Yes, if the entry is affected. |
| **Listener-selection cache** of `AbstractApplicationEventMulticaster` | List of matching listeners for an event type/source type. | No; it does not store product prices. |
| **HTTP/CDN/browser cache** | HTTP responses, network resources, and frontend state. | May be needed, but is not automatically cleared by Spring Application Events. |
| **ORM first-level cache** | JPA persistence context within a transaction/session. | Managed by the ORM lifecycle; distinct from Spring Cache. |
| **Local near-cache + distributed cache** | Copies on each pod plus a shared backend. | Must account for every layer serving the read path. |

When talking about "evicting cache after data updates," this guide focuses primarily on the **Spring Cache abstraction** and cache-aside for business data. Do not try to use reflection to clear the multicaster's listener cache to fix a stale `Product` entry.

## 3. Relevant Spring APIs

| API / Annotation | Responsibility |
| --- | --- |
| `@EnableCaching` | Enables caching annotation processing, by default via AOP proxies. |
| `@Cacheable` | Fetches value from cache on hit; on miss, invokes method and may store the result. |
| `@CacheEvict` | Evicts entries by key or clears an entire cache region. |
| `@CachePut` | Always invokes the method, then stores its return value in the cache. |
| `@Caching` | Combines multiple `@CacheEvict`/`@CachePut`/`@Cacheable` annotations on one method. |
| `CacheManager` | Provides caches by name, e.g., `products`. |
| `Cache` | Exposes `get`, `put`, `evict`, `clear`, and other APIs. |
| `ConcurrentMapCacheManager` | In-memory provider, suitable for demos, not shared across JVMs. |
| `ApplicationEventPublisher` | Publishes business events inside the Spring context. |
| `@EventListener` | Receives events and orchestrates an invalidation operation. |
| `@TransactionalEventListener` | Allows reacting to a transaction phase, e.g., `AFTER_COMMIT`. |

Caching and event dispatch are **two independent mechanisms**. A listener running does not prove a key disappeared from the cache; adding `@CacheEvict` does not automatically register a listener either. Both must be tested.

## 4. Choosing the Exact Cache Key

### 4.1. Read Path

Example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.load(productId);
}
~~~

*This is an illustrative integration snippet in a Spring bean; `Product`/`repository` must be defined. Requires `@EnableCaching` and a `CacheManager`.*

`#p0` in SpEL refers to the method's first parameter; calling `find("P-1")` yields the string key `"P-1"`.

### 4.2. Eviction Path

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evict(String productId) {
    // No cache-eviction code needed in the body; Spring advice handles it.
}
~~~

Both paths use the **same cache name and the same key**. If `find` uses a `String` while `evict` uses an event object, the keys will not match.

Anti-pattern example:

~~~java
@EventListener
@CacheEvict(cacheNames = "products", key = "#p0")
public void onProductUpdated(ProductUpdated event) {
}
~~~

Because `#p0` here is the **entire `ProductUpdated` event**, it does not equal the `String "P-1"` key stored by `find(String)`. If you want to put the cache annotation directly on the event-handling method, you must select the right property:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0.productId()")
public void onProductUpdated(ProductUpdated event) {
}
~~~

*These snippets only illustrate syntax; verify invocation through a Spring proxy when combining `@EventListener` and `@CacheEvict` on the same method. The runnable example in Section 6 separates the cache service to avoid relying on that detail.*

Beyond the product ID, a cache key may include tenant, locale, page, or price tier. An entry `tenant-A:P-1` will not be evicted by key `P-1`. Standardize a key generator or build composite keys consistently across both read and invalidation paths.

### 4.3. Role of eventId

If an event contains `eventId` and `productId`, `eventId` identifies **the event occurrence**, whereas `productId` is the **record identifier** and typically the cache key. Using the event ID to evict a product detail cache is incorrect unless your cache is actually indexed by event ID.

## 5. @CacheEvict: Before or After Method, One Key or Entire Region?

### 5.1. Default: After Method Completes Successfully

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evict(String id) {
    auditEvictionRequest(id);
}
~~~

Per Spring's contract, `beforeInvocation=false` is the default: eviction is triggered **after the method executes successfully**. If the method throws an exception beforehand, eviction does not occur by default. It does not mean "after another database transaction commits."

### 5.2. beforeInvocation=true

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true)
public void evictBefore(String id) {
    performSomething(id);
}
~~~

When `beforeInvocation=true` is enabled, cache eviction happens before the method is invoked, regardless of the method's outcome. This can be useful in certain cases, but for DB updates that might roll back, evicting beforehand is usually not the default way to keep caches consistent.

### 5.3. allEntries=true

~~~java
@CacheEvict(cacheNames = "productLists", allEntries = true)
public void clearProductLists() {
}
~~~

`allEntries=true` targets the **entire region**, not just a single product ID. Do not combine `key` with `allEntries=true` on the same annotation. Clearing the whole region on every single product update can cause simultaneous cache misses, spike DB load, and degrade the hit ratio.

### 5.4. condition and void Methods

`@CacheEvict` can be used on `void` methods since the return value is not cached. It also supports `condition` to evict only when a condition holds; do not confuse it with `unless`, which is common on `@Cacheable`. Place business conditions explicitly and test boundary cases; a condition that always evaluates to `false` leaves entries stale even while the listener runs.

## 6. Runnable Java 17+ Example: Update Emits Event, Listener Evicts Cache

This example uses **Spring Framework 6.2.9**, JDK 17+, and Maven. It uses an in-memory repository as a **simulated source of truth**, with no transactions or broker. This setup lets us verify `@Cacheable`, `@EventListener`, and `@CacheEvict` behavior cleanly without mixing in database connection errors.

### 6.1. Project Structure

~~~text
cache-event-demo/
├── pom.xml
└── src/main/java/CacheInvalidationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cache-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/CacheInvalidationDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class CacheInvalidationDemo {

    public record Product(String id, int price) {}
    public record ProductUpdated(String productId) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public ProductRepository() {
            data.put("P-1", new Product("P-1", 100));
        }

        public Product load(String id) {
            Product product = data.get(id);
            if (product == null) {
                throw new IllegalArgumentException("Unknown product: " + id);
            }
            loads.incrementAndGet();
            System.out.println("DB_LOAD " + id + "=" + product.price());
            return product;
        }

        public void updatePrice(String id, int price) {
            Product result = data.computeIfPresent(
                    id, (key, oldValue) -> new Product(id, price));
            if (result == null) {
                throw new IllegalArgumentException("Unknown product: " + id);
            }
            System.out.println("DB_UPDATE " + id + "=" + price);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class ProductCacheService {
        private final ProductRepository repository;

        public ProductCacheService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(String id) {
            return repository.load(id);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String id) {
            // Body runs before default eviction (after-invocation).
            System.out.println("EVICT_CALL " + id);
        }
    }

    public static class ProductApplicationService {
        private final ProductRepository repository;
        private final ApplicationEventPublisher publisher;

        public ProductApplicationService(
                ProductRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void updatePrice(String id, int price) {
            repository.updatePrice(id, price);
            publisher.publishEvent(new ProductUpdated(id));
        }
    }

    public static class ProductInvalidationListener {
        private final ProductCacheService cacheService;

        public ProductInvalidationListener(ProductCacheService cacheService) {
            this.cacheService = cacheService;
        }

        @EventListener
        public void onProductUpdated(ProductUpdated event) {
            System.out.println("EVENT " + event.productId());
            cacheService.evict(event.productId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductRepository productRepository() {
            return new ProductRepository();
        }

        @Bean
        public ProductCacheService productCacheService(
                ProductRepository repository) {
            return new ProductCacheService(repository);
        }

        @Bean
        public ProductApplicationService productApplicationService(
                ProductRepository repository,
                ApplicationEventPublisher publisher) {
            return new ProductApplicationService(repository, publisher);
        }

        @Bean
        public ProductInvalidationListener productInvalidationListener(
                ProductCacheService cacheService) {
            return new ProductInvalidationListener(cacheService);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            ProductCacheService cache =
                    context.getBean(ProductCacheService.class);
            ProductApplicationService app =
                    context.getBean(ProductApplicationService.class);
            ProductRepository repo =
                    context.getBean(ProductRepository.class);

            System.out.println("READ1=" + cache.find("P-1").price());
            System.out.println("READ2=" + cache.find("P-1").price());

            app.updatePrice("P-1", 150);

            System.out.println("READ3=" + cache.find("P-1").price());
            System.out.println("LOAD_COUNT=" + repo.loadCount());
        }
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=CacheInvalidationDemo
~~~

**Stdout printed by the program itself**, excluding Maven logs:

~~~text
DB_LOAD P-1=100
READ1=100
READ2=100
DB_UPDATE P-1=150
EVENT P-1
EVICT_CALL P-1
DB_LOAD P-1=150
READ3=150
LOAD_COUNT=2
~~~

### 6.2. Why Is This Result Correct?

1. `@EnableCaching` activates the cache interceptor; `ConcurrentMapCacheManager("products")` supplies the `products` region.
2. `cache.find("P-1")` is called from outside the bean via the Spring proxy. The first call misses, the repository prints `DB_LOAD ... 100`, and the result is stored in the cache.
3. The second call hits, `READ2=100`, and the repository is not called again.
4. `app.updatePrice(...)` writes `150` to the repository and publishes `ProductUpdated("P-1")`.
5. The default multicaster invokes `@EventListener` synchronously. The listener prints `EVENT P-1` and calls `cacheService.evict("P-1")` through the Spring-injected dependency.
6. Spring's `@CacheEvict` advice invokes the method body, prints `EVICT_CALL P-1`, and then evicts key `"P-1"` after the method succeeds.
7. The next read misses and loads `150`. `LOAD_COUNT=2` confirms the repository was called only on the initial read and the read after eviction.

**Demo limitations:** the in-memory repository has no transactions, no multiple servers, no network, and does not test crashes/retries. The program demonstrates **in-process event-driven cache invalidation**, not strong consistency in a distributed system.

## 7. Spring Proxies and the Self-Invocation Pitfall

Cache annotations in default mode use AOP proxies. If a method within the same bean calls `this.evict(id)`, the call usually **bypasses the proxy**, so `@CacheEvict` is ignored.

~~~java
@Service
class BadProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        return repository.load(id);
    }

    public void update(String id, int price) {
        repository.updatePrice(id, price);
        evict(id); // SELF-INVOCATION: may bypass @CacheEvict.
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void evict(String id) {}
}
~~~

*Integration anti-pattern snippet; `Product`, `repository`, and imports must be defined by the application.*

**How to fix:** extract `ProductCacheService` into a separate bean and have the listener/application service invoke that bean through an injected dependency. Alternatively, use `CacheManager` directly. Never try to "fix" this by instantiating `new ProductCacheService(...)`, because manually constructed objects are not managed by Spring proxies.

With class-based proxies, do not place caching annotations on `private`/`final` methods and assume the interceptor will run. Use `public` methods invoked from another bean, and test the application inside a real Spring context rather than calling plain Java methods directly and concluding caching works.

If you put `@EventListener` and `@CacheEvict` on the same method, verify that the event adapter invokes **the appropriate proxy**. Separating the listener and the cache service reduces risk and makes testing easier, though it is not strictly required by Spring.

## 8. When to Evict Cache: Before Commit or After Commit?

### 8.1. Risks of a Synchronous Listener Inside a Transaction

In a database-backed system, a `@Transactional` service may publish an event **before the transaction commits**:

~~~text
@Transactional updatePrice(...)
    |
    +-- UPDATE DB P-1=150 (uncommitted)
    |
    +-- publish ProductUpdated("P-1")
    |       |
    |       +-- @EventListener -> evict("P-1") immediately
    |
    +-- another step fails -> ROLLBACK
~~~

Semantically, `ProductUpdated` can be misinterpreted as "successfully updated" even though the transaction rolls back. Premature eviction also causes unnecessary cache misses and widens the race window with concurrent readers.

### 8.2. Using @TransactionalEventListener(AFTER_COMMIT)

Inside a Spring-managed transaction, a listener can run after commit:

~~~java
@Component
class ProductCacheEvictAfterCommit {
    private final ProductCacheService cache;

    ProductCacheEvictAfterCommit(ProductCacheService cache) {
        this.cache = cache;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onUpdated(ProductUpdated event) {
        cache.evict(event.productId());
    }
}
~~~

*This is an **integration snippet**, not the runnable example in Section 6; it requires Spring transaction infrastructure, `@TransactionalEventListener`, `TransactionPhase`, `@Component`, and a real transaction manager.*

Diagram:

~~~text
BEGIN TX
  UPDATE products
  publish ProductUpdated
  Spring registers transaction synchronization
COMMIT succeeds
  AFTER_COMMIT listener -> evict cache key

If ROLLBACK:
  AFTER_COMMIT listener does not perform eviction
~~~

**Note:** `@TransactionalEventListener` by default **does not run outside an appropriate transaction** because `fallbackExecution=false`. The in-memory demo has no transaction so it uses `@EventListener`; if you replace it with `@TransactionalEventListener` without adding a transaction manager, events will not trigger invalidation.

When handling at the `AFTER_COMMIT` phase, the original transaction has already committed. If the listener also needs to perform additional DB writes, design an appropriate new transaction (e.g., a service method with `REQUIRES_NEW` when using imperative transactions) rather than assuming it writes to the old transaction.

### 8.3. @CacheEvict Directly on a @Transactional Method

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void updatePrice(String productId, int price) {
    repository.updatePrice(productId, price);
}
~~~

*This is an illustrative integration snippet.*

Having both annotations can cause cache eviction near the end of the method, but **its exact timing relative to commit depends on advice ordering and configuration**. Do not assume it is equivalent to `AFTER_COMMIT`. Test the actual transaction boundaries, or use the explicit transactional event pattern.

### 8.4. Transaction-Aware Cache Manager

Spring provides `TransactionAwareCacheDecorator`/`TransactionAwareCacheManagerProxy`, which can synchronize `put`, `evict`, and `clear` with the active transaction, executing them after a successful commit. This is a **cache-layer mechanism**, not an event listener itself.

Immediate APIs such as `evictIfPresent` have different semantics and cannot be deferred like ordinary evictions. When combining cache wrappers, transaction listeners, and custom advice, verify their ordering; do not assume all configuration options behave identically.

**Crucial point:** evicting after commit solves the **rollback** problem, but does not by itself protect against the process dying right after commit or concurrent readers refilling the cache. Those limitations require separate solutions.

## 9. Multiple Instances: Local Events Do Not Evict Caches on Other Pods

`ConcurrentMapCacheManager` in the example only operates within a single JVM:

~~~text
Pod A: cache[P-1] = 100
Pod B: cache[P-1] = 100
Pod C: cache[P-1] = 100

UPDATE on Pod A:
  Database = 150
  Pod A publishes Spring ApplicationEvent
  Pod A evicts(P-1)

Reads after update:
  Pod A -> 150
  Pod B -> 100  (STALE)
  Pod C -> 100  (STALE)
~~~

Spring Application Events **do not automatically propagate over the network**. Common strategies:

- **Shared cache** (e.g., Redis) so instances share a key space; still account for replication lag and near-caches if present.
- **Broadcast invalidation events** via a broker/pub-sub: each instance evicts its local cache; requires retry/catch-up if an instance was offline.
- **Transactional outbox** writing the notification in the same database transaction and relaying it to a broker; reduces the risk of losing invalidations on process crash.
- **TTL and data versioning** to bound staleness duration; this is a safety net, not a replacement for a business consistency policy.
- **Versioned cache keys** or CAS/provider-specific behavior when higher consistency is required and a reliable version source exists.

If an application uses both a Caffeine local cache and a Redis shared cache, deleting a key in Redis does not mean every pod's near-cache is cleared of the old copy. Map out the **complete read path** before deciding invalidation scope.

## 10. Race Conditions: Stale Data Can Still Be Returned After Commit

### 10.1. A Stale Reader Refills the Cache

~~~text
Reader                            Writer
--------------------------------  -------------------------------
cache MISS
DB read old=100
                                  COMMIT DB new=150
                                  cache evict(P-1)
cache put(old=100)  [arrives late]
GET P-1 may return 100
~~~

Even when evicting after commit, a concurrent reader may have already fetched an old snapshot and written it into the cache after eviction occurred. This is a **stale repopulation race**; its exact likelihood depends on the provider and scheduling.

Mitigations depending on requirements: version/generation tokens, per-key synchronization, atomic provider operations, TTLs, read-through/write-through consistency policies, or bypassing the cache for operations requiring ultra-fresh data. No single Spring annotation eliminates all races.

### 10.2. Delayed, Duplicate, and Out-of-Order Events

Evicting the same key multiple times is generally **idempotent**: removing an already-absent entry causes no business error. However, consumers still need retry handling and failure visibility. If instead of evicting you use `@CachePut` to write a price from the payload, an older event arriving after a newer one can **overwrite** the cache with an outdated price. In that case, you need explicit version checks, ordering, or CAS.

### 10.3. Derived Caches

Updating a product's price can invalidate more than just the detail cache:

~~~text
products[P-1]                 -> product detail
productSummaries[P-1]         -> summary
productsByCategory[category]  -> lists containing prices
searchResults[query]          -> filter/search results
cartTotals[cartId]            -> shopping cart totals
~~~

If you only evict the detail key, those other caches remain stale. Build a **cache dependency map** per change type. Do not wipe every region just because key mapping isn't understood; design regions by business responsibility, key tags, or appropriate TTLs.

## 11. Evicting Multiple Regions with @Caching

When an update affects both details and summaries, you can declare:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", key = "#p0"),
    @CacheEvict(cacheNames = "productSummaries", key = "#p0"),
    @CacheEvict(cacheNames = "productLists", allEntries = true)
})
public void invalidateProduct(String productId) {
}
~~~

*Integration snippet inside a Spring-managed bean, requiring `@Caching` and configured cache names.*

There is no default atomic transaction spanning all cache providers in the list: if one cache backend fails midway, partial invalidation can occur. Metrics, retries, and reconciliation are needed when the domain is sensitive.

If every update clears all of `productLists`, the system may suffer a cache stampede. Consider versioned list caches, group invalidation, or shorter TTLs depending on actual traffic.

## 12. Eviction via CacheManager Instead of Annotations

Sometimes a listener prefers not to depend on AOP:

~~~java
@Component
class ProductEvictListener {
    private final CacheManager manager;

    ProductEvictListener(CacheManager manager) {
        this.manager = manager;
    }

    @EventListener
    public void onUpdated(ProductUpdated event) {
        Cache cache = manager.getCache("products");
        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
~~~

*Integration snippet requiring imports for `CacheManager`, `Cache`, `@Component`, and `@EventListener`; not a standalone runnable file.*

Comparison:

| Approach | Best When | Caveats |
| --- | --- | --- |
| Listener calls a `@CacheEvict` bean | You want to reuse cache policies, SpEL keys, and AOP. | Requires proxy, matching cache name, and key. |
| Listener calls `CacheManager.getCache(...).evict(...)` | You want an explicit operation with an already-built key. | Must handle null caches and provider semantics. |
| Update method has `@CacheEvict` | Small, straightforward workflow. | Advice ordering relative to commit is not self-evident. |
| `AFTER_COMMIT` listener | Must not invalidate on rollback. | Not durable across crashes. |
| Outbox + broker + multi-instance listeners | Need retries and cross-process invalidation. | Eventual consistency, ordering, and operational complexity. |

Per the Spring `Cache` API, `evict(Object key)` may be performed deferred/asynchronously depending on the cache decorator/provider. `evictIfPresent(key)` expects the key to be immediately invisible to subsequent lookups, though you still need to check the implementation. Do not assume every cache backend offers identical visibility timing or replication guarantees.

## 13. Transactional Outbox and Guaranteed Invalidation Delivery

A critical gap in multi-service systems:

~~~text
DB COMMIT price=150
    |
    X process dies before sending event to broker
    |
    +-- Another pod still caches price=100
~~~

A `@TransactionalEventListener(AFTER_COMMIT)` is only an in-memory callback; it **does not persist the event for retry after a JVM crash**.

A transactional outbox writes an outbox row **in the same DB transaction** as the update:

~~~text
BEGIN TRANSACTION
  UPDATE product price=150
  INSERT outbox(ProductUpdated, eventId, productId, version)
COMMIT
    |
    v
Outbox relay -> durable broker -> consumer
                                   |
                                   +-- evict local/shared cache
                                   +-- retry on error
                                   +-- idempotency by eventId if needed
~~~

The outbox reduces the risk of committing data while losing the notification; however, the relay can still publish duplicates and consumers can still be offline. Choose appropriate retention, dead-letter/retry policies, idempotency, and measure **time from commit to eviction**.

A production event contract might look like:

~~~java
public record ProductUpdated(
        String eventId,
        String productId,
        long productVersion,
        Instant occurredAt,
        String correlationId) {}
~~~

*Illustrative snippet; requires `java.time.Instant` and a clear policy for generating `eventId` and version.*

`eventId` identifies the occurrence, `productId` identifies the entry, and `productVersion` helps handle ordering if the cache is version-aware. Never use `correlationId` as the cache key or deduplication key across all events because multiple events in the same workflow can share a correlation ID.

## 14. What to Do When Cache Eviction Fails?

Failures can occur at many boundaries:

- **Event not published** because the service bypassed the proper update path.
- **Listener not registered** due to mismatched event type/context or a missing bean.
- **Listener runs but cache advice does not** due to self-invocation, non-public method, or a manually instantiated bean outside Spring.
- **Eviction uses wrong key/cacheName**, deleting the wrong or nonexistent entry.
- **Cache backend fails:** timeout, connection failure, rate limiting, or provider error.
- **Transaction rollback/phase:** `AFTER_COMMIT` listener never runs because there was no commit.
- **Async execution:** exception occurs on the executor, invisible to the publisher immediately.
- **Cluster:** one instance clears its local key while others retain stale values.
- **Concurrent reader:** cache gets repopulated with old data.

To handle failures safely:

1. Observe `eventId`/`productId`/`cacheName`/hashed key and outcome without logging sensitive data.
2. Separate configuration errors (wrong key) from transient errors (timeouts).
3. Emit metrics for invalidation successes/failures and cached data age.
4. If staleness is unacceptable, decide **fail-open vs. fail-closed** when the cache/invalidation backend fails.
5. For distributed invalidation, use retry/outbox and idempotency; never silently swallow errors and mark success.
6. TTL is a defense layer, not a guarantee of instant freshness.

If a synchronous listener throws an exception inside a transaction, it can cause the transaction to roll back according to applicable rules; however, when an error occurs inside an `AFTER_COMMIT` callback, the DB has already committed, so that exception alone cannot roll back the original data. You must plan separate compensation/reconciliation or retries.

## 15. Testing the Deployment Pattern

A practical test suite should cover:

| Scenario | Expectation |
| --- | --- |
| First read | Cache miss, repository loads. |
| Second read, same key | Cache hit, no reload. |
| Successful update + event | Listener evicts entry with exact key. |
| Read after update | Cache miss and returns new price. |
| Update a different product | Unrelated entries remain cached. |
| Duplicate event | Eviction is idempotent, no unintended side effects. |
| Calling cache method through proxy | `@CacheEvict` actually takes effect. |
| Calling `this.evict(...)` | Test catches proxy bypass if the code does this. |
| TX rollback | `AFTER_COMMIT` listener does not run. |
| No TX | `AFTER_COMMIT` does not run when fallback is disabled. |
| Multiple pods | Notification or shared cache required to prevent staleness. |
| Cache provider failure | Error is observed and follows retry/fallback policy. |
| Reader/writer race | Version/consistency safeguards work when required. |
| List/category updates | Derived cache regions are invalidated. |

Do not only assert "the listener was invoked"; verify that **the repository is queried again and the returned price changes**. In the demo, `LOAD_COUNT=2` is that minimal proof. For real Spring Boot/JPA/Redis apps, add integration tests with the corresponding database and cache backend.

### Guiding JUnit/Mockito Snippet

~~~java
@Test
void updateMustInvalidateCachedProduct() {
    Product before = cachedService.find("P-1");
    assertEquals(100, before.price());

    Product again = cachedService.find("P-1");
    assertEquals(before, again);
    verify(repository, times(1)).load("P-1");

    applicationService.updatePrice("P-1", 150);

    assertEquals(150, cachedService.find("P-1").price());
    verify(repository, times(2)).load("P-1");
}
~~~

*This is a **non-standalone test sample**: it requires JUnit 5, Mockito, repository mock setup with appropriate update behavior, and a Spring test context with caching + listener enabled. With the demo's real repository, you can use `repo.loadCount()` instead of Mockito.*

## 16. Diagnostic Flow When Data Remains Stale

~~~text
Does the source of truth actually hold the new price?
 |
 +-- No -> inspect transaction/update.
 +-- Yes
     |
     +-- Was the ProductUpdated event published?
     |     |
     |     +-- No -> fix mutation flow or outbox
     |     +-- Yes
     |
     +-- Did the listener receive the event with right type/context?
     |     |
     |     +-- No -> check bean, annotation, TX phase, async
     |     +-- Yes
     |
     +-- Did @CacheEvict run via proxy / CacheManager?
     |     |
     |     +-- No -> fix @EnableCaching, self-invocation, visibility
     |     +-- Yes
     |
     +-- Do CacheName and KEY match @Cacheable?
     |     |
     |     +-- No -> fix key generator/cache region
     |     +-- Yes
     |
     +-- Are there other cache layers or other pods?
     |     |
     |     +-- Yes -> check shared cache, pub/sub, near-cache
     |
     +-- Are there concurrent readers, delayed events, or replication lag?
           |
           +-- Yes -> design version/race handling
           +-- No -> measure cache provider, TTL, and actual reads
~~~

**Do not band-aid everywhere with `allEntries=true`.** It can mask key bugs, trigger thundering herds, and still fail to solve lost events or caches on other pods.

## 17. Common Mistakes

1. Confusing the multicaster's cache with the business data cache.
2. Updating the DB while forgetting to emit the event / invalidate the cache.
3. `@Cacheable` using a `String` key while `@CacheEvict` takes the whole event object as key.
4. Wrong cache name or omitting tenant/locale in a composite key.
5. Forgetting `@EnableCaching`, rendering annotations inactive.
6. Calling `this.evict(...)` and bypassing the AOP proxy.
7. Assuming `@CacheEvict` on a `@Transactional` method always runs strictly after commit.
8. Using `@TransactionalEventListener` without a transaction, causing the callback not to run by default.
9. Treating `AFTER_COMMIT` as durable delivery or automatic retry after a crash.
10. Evicting only the cache on the instance publishing the event.
11. Clearing an entire region for one small change, causing a cache stampede.
12. Forgetting list/search/summary/derived caches.
13. Overwriting the cache with a late-arriving old payload via `@CachePut`.
14. Failing to handle exceptions from the backend or an async listener.
15. Treating TTL as an instant consistency guarantee.
16. Ignoring races between stale reads, update commits, and cache refills.
17. Failing to distinguish `eventId` from `productId` when determining keys.
18. Letting an update event from an untrusted source evict another tenant's keys.
19. Having no metrics for invalidation delay and failures.
20. Testing only the listener in isolation without testing the full read path before and after updates.

## 18. Self-Check

**Question 1.** Why is `READ2=100` not accompanied by a second `DB_LOAD` line?

**Answer:** `@Cacheable` cached the result under `products["P-1"]`, so the second read hit the cache.

**Question 2.** Why shouldn't you use `key="#p0"` on a method taking `ProductUpdated event` if the cache-reading method takes `String id`?

**Answer:** `#p0` in the two methods refers to objects of different types; you need `#p0.productId()` or an `evict(String)` method.

**Question 3.** Does `beforeInvocation=false` mean eviction happens after DB commit?

**Answer:** No. It only means eviction occurs after the advised method finishes successfully, not after the transaction commits.

**Question 4.** Why is `@TransactionalEventListener(AFTER_COMMIT)` unsuitable as a direct drop-in replacement for `@EventListener` in the demo?

**Answer:** The demo has no active transaction; transactional listeners do not run when the default `fallbackExecution=false` applies.

**Question 5.** Does clearing the local cache on Pod A remove stale data from Pod B?

**Answer:** No. You need a shared cache, cross-instance invalidation, or another consistency policy.

**Question 6.** When updating P-1's price, why can category list caches still be wrong?

**Answer:** Detail entries and category lists are separate cache keys/regions; you need a dependency map.

**Question 7.** What can cause a reader to repopulate an old value after a writer has already evicted it?

**Answer:** The reader may read a pre-commit snapshot and finish its cache put after eviction. Concurrency/versioning must be considered.

**Question 8.** When is `allEntries=true` reasonable?

**Answer:** When all entries are affected or the key set cannot be enumerated, and the load/latency impact is acceptable.

**Question 9.** Should a redelivered event with the same ID be treated as a new update?

**Answer:** No. It may be the same occurrence replayed; consumers need idempotent semantics rather than creating new side effects by default.

**Question 10.** After commit, invalidation fails and the process dies. Does `@TransactionalEventListener` automatically recover after restart?

**Answer:** No. You need a durable mechanism such as a transactional outbox, broker/retries, and reconciliation.

## References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CacheEvict`, `beforeInvocation`, `allEntries`, `@Caching`, `@EnableCaching`, and AOP proxies.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT`, `fallbackExecution`, and commit boundaries.
- [Spring Framework 6.2.9 Javadoc — Cache](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/Cache.html): `evict`, `evictIfPresent`, `clear`, `invalidate`.
- [Spring Framework 6.2.9 Javadoc — CacheEvict](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): `cacheName`, `key`, `condition`, `allEntries`, `beforeInvocation`.
- [Spring Framework 6.2.9 Javadoc — TransactionAwareCacheDecorator](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): transaction-aware `put`/`evict`/`clear`.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` and `@EventListener`.
