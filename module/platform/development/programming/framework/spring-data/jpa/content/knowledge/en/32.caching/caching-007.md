# Distinguishing JPA Cache from Spring Cache

## 1. Why are they all called "cache" yet serve different roles?

In an application using Spring Data JPA, at least three mechanisms are easily lumped together as "cache":

1. **JPA first-level cache (L1, persistence context):** the area holding entities *currently managed* by an `EntityManager`. This is an essential part of the entity lifecycle and dirty checking.
2. **JPA second-level cache (L2):** an *optional* entity/collection cache that can be shared across multiple `EntityManager` instances belonging to the same `EntityManagerFactory`, depending on the JPA provider and configuration.
3. **Spring Cache:** an application-level abstraction that primarily caches **method return values** using `@Cacheable`, `@CachePut`, and `@CacheEvict` via a `CacheManager` and backends such as Caffeine or Redis.

With Hibernate (the common JPA provider in Spring Boot), there is also an optional **query cache**. The query cache is not the same as the L2 entity cache and does not turn every JPA query into a cache hit.

Key takeaway: **JPA caches manage entities and persistence state; Spring Cache manages values the application decides to cache.** They can coexist in a single read flow, but they do not automatically manage or invalidate each other's data.

### Diagram of a single read

```text
Client
  │
  ▼
ProductReadService.get(id)
  │
  ├── Spring Cache HIT ───────────────────────────────► Return cached ProductView
  │                                                     (method body does not run)
  └── Spring Cache MISS
        │
        ▼
      Repository / EntityManager
        │
        ├── Entity already managed in L1? ─────────────► Use entity in persistence context
        │
        └── Not yet in L1
              │
              ├── L2 enabled, valid entry exists? ─────► Load entity state from L2
              │
              └── Absent / invalid hit ────────────────► Read database
        │
        ▼
      Build ProductView DTO
        │
        └── Store result in Spring Cache, return to client
```

This is a conceptual diagram for **looking up an entity by primary key**. An arbitrary JPQL/Criteria query may still generate SQL to determine the result set, even when some of the corresponding entities are already in L1. Actual query, fetch, and cache decisions depend on the execution path and the JPA provider.

## 2. JPA L1: the "cache" bound to EntityManager and transaction

Each `EntityManager` has a **persistence context**, commonly called the first-level cache. For entities of the same type and primary key, JPA guarantees there is only one managed instance within the same persistence context. L1 provides important properties:

- **Identity map:** calling `find` twice with the same id in the same persistence context can return the exact same Java reference.
- **Dirty checking:** changes on a managed entity are detected and synchronized upon `flush`/commit per JPA rules.
- **Repeatable identity within context scope:** different parts of code share the same managed entity without creating two separate managed instances for the same database identity.
- **Write-behind:** JPA can defer SQL until `flush`; L1 is not merely a read copy of queried data.

Example inside a Spring bean with an injected `EntityManager`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaIdentityDemo {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public boolean sameManagedObject(Long existingProductId) {
        Product first = entityManager.find(Product.class, existingProductId);
        Product second = entityManager.find(Product.class, existingProductId);
        return first == second; // true if the record exists and shares the same persistence context
    }
}
```

In Spring, the `EntityManager` is usually bound to the current transaction; its exact scope depends on configuration, such as Open EntityManager in View or an extended persistence context. **Do not assume by default that L1 is shared across HTTP requests or transactions.**

- `entityManager.flush()`: requests synchronizing pending changes to the database; **does not clear L1**.
- `entityManager.clear()`: detaches all managed entities from the persistence context; **does not automatically clear L2 or Spring Cache**.
- `entityManager.detach(entity)`: detaches a specific entity.
- `entityManager.refresh(entity)`: reloads the state of a managed entity per provider mechanism, suitable when an object needs refreshing; **not a command to clear all caches**.
- Ending the persistence context terminates L1's scope, though data may still remain in L2 or Spring Cache if those layers are enabled.

L1 **does not require `@EnableCaching`** and is not toggled by `org.springframework.cache.annotation.Cacheable`. It exists as a normal part of JPA.

**Limitation:** Bulk JPQL `UPDATE`/`DELETE` statements or SQL from out-of-band processes can modify the database while managed entities in L1 keep old values. In those cases, you must decide when to `flush`, `clear`, `refresh`, or open a new context. Never use caching as an excuse to ignore transactions and consistency concerns.

## 3. JPA L2: shared, optional, provider-dependent entity cache

The second-level cache lives at the `EntityManagerFactory`/Hibernate `SessionFactory` scope, so entities can be reused across multiple persistence contexts **if** the entity is cache-eligible, the provider has a cache backend, and it is configured properly.

Characteristics:

- **Optional:** JPA applications do not have an active L2 cache for all entities by default. Many Hibernate setups require a suitable region factory and backend.
- **Typically caches entity state by type + id:** associations/collections have their own cache policies; **collections and query results are not cached by default**.
- **Not guaranteed to be shared across nodes:** if the cache lives in each process's memory, every node keeps its own copy. Cross-node sharing/clustering depends on the cache provider.
- **Consistency and eviction are governed by the provider/access rules:** you must choose concurrency strategies, expiry, locking, invalidation, and concurrent write behavior.
- **Updates outside JPA:** SQL scripts, other services, and certain native/bulk DML statements can leave stale entries behind. Hibernate has invalidation mechanisms for operations it recognizes, but it cannot automatically synchronize all writers outside the ORM.

JPA provides the `jakarta.persistence.Cacheable` annotation and the `EntityManagerFactory.getCache()` API. With Hibernate, you may also see provider annotations/configs like:

```java
// Illustrating entity mapping when Hibernate L2 is fully configured:
@jakarta.persistence.Cacheable(true)
@org.hibernate.annotations.Cache(
    usage = org.hibernate.annotations.CacheConcurrencyStrategy.READ_WRITE
)
@Entity
public class Product {
    // ... id and mapped attributes ...
}
```

The snippet above **only illustrates annotations**; it is not a standalone Java file and is insufficient to run L2 on its own: you need the dependency/cache backend, region factory, region policies, and corresponding Hibernate/JPA configuration. Do not add this mapping simply because a query feels slow; measure hit rates and update patterns first.

JPA provides factory-level operations (when the provider supports that cache):

```java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

Cache cache = entityManagerFactory.getCache();
boolean cached = cache.contains(Product.class, productId);
cache.evict(Product.class, productId); // evict L2 entity by id
// cache.evictAll();                 // clear all managed L2 cache data
```

This is an illustrative snippet inside a method that already has `entityManagerFactory` and `productId`. It **does not clear Spring Cache**. Specifically, `EntityManager.clear()` only affects L1, while `EntityManagerFactory.getCache().evict(...)` affects L2; the two commands operate on different scopes.

### Hibernate query cache differs from L2 entity cache

Hibernate's query cache is a separate feature that must be enabled and opted into per query via the appropriate API/hints. It typically stores query result set metadata (such as lists of identifiers and timestamps), while entity state caching belongs to L2. For queries returning entities, **a query cache hit does not necessarily eliminate all database access** if the required entities/collections are absent from the appropriate cache.

Do not assume `repository.findAll()` or JPQL `select` queries are "cached" by default simply because L2 is enabled. The query cache has invalidation overhead and performs poorly on frequently updated tables; enable it only when supported by measurements.

## 4. Spring Cache: method-result cache, independent of the JPA lifecycle

Spring Cache is an abstraction placed at **method boundaries**. When enabled and calls pass through a Spring AOP proxy:

- `@Cacheable(cacheNames = "...", key = "...")`: checks the cache; on a hit, returns the stored result and **skips the method body**; on a miss, executes the method and caches the result per policy.
- `@CachePut`: **always executes** the method and updates the cache entry with its return value; do not casually substitute it for `@Cacheable`.
- `@CacheEvict`: removes a key or an entire region; by default executes after the method succeeds (when invoked through the proxy). **This timing does not automatically mean after database commit.**
- `@EnableCaching`: activates cache annotation processing; requires a `CacheManager` providing the cache backend.
- `CacheManager`: manages Spring caches by name; can use `ConcurrentMapCacheManager` (simple, in-memory), Caffeine (in-process), or Redis (shared if properly designed).

Easily confused name differences:

| Annotation | Package | Meaning |
| --- | --- | --- |
| `@Cacheable` | `jakarta.persistence.Cacheable` | Metadata for JPA's shared cache mechanism |
| `@Cacheable` | `org.springframework.cache.annotation.Cacheable` | Caches **method results** managed by Spring |
| `@Cache` | `org.hibernate.annotations.Cache` | Hibernate provider cache mapping/policy |
| `@CacheEvict` | `org.springframework.cache.annotation.CacheEvict` | Removes entries from **Spring Cache** |

**Common AOP pitfall:** calling `this.getProduct(id)` from another method in the **same bean** normally bypasses the Spring proxy, so `@Cacheable` does not run in default proxy mode. Place read methods in a separate bean and invoke them via an injected bean, or redesign service boundaries. Cache annotations do not automatically make private methods cacheable either.

Spring Data JPA repositories also **do not automatically have a global result cache** merely because `JpaRepository` exists. If you apply Spring Cache to a service/repository method, that is application-level caching you configured explicitly.

## 5. Quick comparison table

| Criterion | JPA L1 | JPA L2 | Spring Cache |
| --- | --- | --- | --- |
| Purpose | Entity management and persistence context | Reduce reloading entity state across contexts | Reduce computation, service calls, or result-returning queries |
| Scope | One persistence context / `EntityManager` | `EntityManagerFactory` and provider; cross-node depends on backend | `CacheManager` + backend; single-node or multi-node by choice |
| Default | Present per JPA mechanics | Optional / provider-configured | Must be enabled and configured with annotations/backend |
| Target | Managed entities and dirty-checking state | Entity state/collections per mapping | Any suitable method return value: DTOs, records, lists, aggregates... |
| Typical key | Entity type + primary key within context | Entity/region + primary key | Cache name + key derived from method args or SpEL |
| Arbitrary queries | Does not guarantee skipping SQL | Does not automatically cache arbitrary JPQL results | Hit skips the entire annotated method body |
| Clear/modify | `clear`, `detach`, `refresh` | `EntityManagerFactory.getCache().evict`, provider APIs | `@CacheEvict`, `Cache.evict`/`clear` |
| Write sync | Via managed entities/flush; bulk DML can cause staleness | Via provider mechanism; external writers need an explicit plan | **Application is responsible** for invalidation/expiry |
| TTL/size | Bound to context lifetime; not configured like a generic TTL | Provider/region-dependent | Backend-dependent (Caffeine/Redis...), not defined by `@Cacheable` itself |

**Typical lookup order:** Spring Cache at the service layer can intercept a call before reaching JPA; on a miss, L1 can serve a managed entity; if absent from L1, L2 can serve entity state; finally, the provider reads the DB. This is an explanatory model, not a promise on the exact SQL count for every query.

## 6. Java 17+ / Spring Boot 3 example: caching DTOs and evicting after commit

The example below uses:
- Spring Boot 3.x, Java 17+, `spring-boot-starter-data-jpa`, `spring-boot-starter-cache`, and runtime H2.
- Spring Cache backend `ConcurrentMapCacheManager` **for learning/testing only**; it has no TTL, capacity limits, or multi-process synchronization.
- Entities managed by JPA; Spring Cache **stores only the `ProductView` DTO record**, avoiding caching managed entities directly and avoiding proxy/lazy-loading/detached-state risks.
- When modifying an entity, an event is published inside the transaction, and Spring Cache is evicted only after a **successful commit**.

These are **files of a Spring Boot application**, not a standalone Java file runnable via `javac` alone. Create a Spring Boot 3.x project with the dependencies listed above, place the files under `src/main/java/example/cache/`, and configure H2 as shown below.

### 6.1. Entity and repository

**`Product.java`**

```java
package example.cache;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

**`ProductRepository.java`**

```java
package example.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

`@Version` supports optimistic locking when JPA updates managed entities. L1 works naturally across repository/JPA calls; L2 does not need to be enabled yet.

### 6.2. DTO and read service with Spring Cache

**`ProductView.java`**

```java
package example.cache;

import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        Long version) {
}
```

**`ProductReadService.java`**

```java
package example.cache;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductReadService {
    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productViews", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView get(Long id) {
        Product p = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        return new ProductView(
                p.getId(), p.getName(), p.getPrice(), p.getVersion());
    }
}
```

`#p0` uses the first parameter as the cache key (here the product id), avoiding dependence on parameter names being retained in bytecode. On the first miss, the repository loads the entity; on subsequent hits, the stored `ProductView` is returned directly. This **does not mean** `Product` was stored in JPA L2.

### 6.3. Modifying data and invalidating cache after commit

**`ProductChanged.java`**

```java
package example.cache;

public record ProductChanged(Long productId) {
}
```

**`ProductWriteService.java`**

```java
package example.cache;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductWriteService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.rename(newName);
        events.publishEvent(new ProductChanged(id));
    }
}
```

Because the entity is managed, JPA flushes changes at the appropriate point in the transaction. The event is registered within this transaction; if the commit fails, the `AFTER_COMMIT` listener will not execute.

**`ProductCacheInvalidator.java`**

```java
package example.cache;

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
    public void afterCommit(ProductChanged event) {
        Cache cache = cacheManager.getCache("productViews");
        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
```

`@TransactionalEventListener(AFTER_COMMIT)` runs only when the associated transaction commits successfully; by default, events without a matching transaction are not invoked. It makes invalidation ordering clearer than the default `@CacheEvict` on a `@Transactional` method, though it is **not a durable event**: if the process crashes right after DB commit and before eviction, the cache can stay stale. When high consistency or multiple nodes are required, consider outbox/CDC, distributed invalidation, and versioned cache keys.

### 6.4. Enabling Spring Cache and running the example

**`CacheDemoApplication.java`**

```java
package example.cache;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productViews");
    }

    @Bean
    CommandLineRunner demo(
            ProductRepository repository,
            ProductReadService reads,
            ProductWriteService writes) {
        return args -> {
            Product product = repository.save(
                    new Product("Before", new BigDecimal("19.00")));
            Long id = product.getId();

            System.out.println("first = " + reads.get(id).name());
            System.out.println("second = " + reads.get(id).name());

            writes.rename(id, "After");

            System.out.println("after change = " + reads.get(id).name());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:cache_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

Run using Maven/Gradle from the created Spring Boot project (for example `./mvnw spring-boot:run` if the project has Maven Wrapper). The expected `System.out.println` lines are:

```text
first = Before
second = Before
after change = After
```

Spring Boot startup logs may appear alongside them. The second read can be served from **Spring Cache**. After `writes.rename(...)`, JPA writes the change to the database, the post-commit listener evicts the key, and the final read must fetch the new data.

This example **does not configure JPA L2**. The fact that the second read is cached does not prove L2 is active.

## 7. When data changes, which cache needs to be cleared?

Suppose `Product#7` has name "Old"; the service cached `ProductView(7, "Old", ...)`. Another transaction renames it to "New". Depending on where data is held:

| Operation | Primary effect | Layers not guaranteed to synchronize |
| --- | --- | --- |
| `entityManager.clear()` | Detaches entities from the **current L1** | L2, Spring Cache |
| `entityManager.refresh(product)` | Refreshes **that managed entity** per provider | Spring Cache; other entities/contexts |
| `entityManagerFactory.getCache().evict(Product.class, 7L)` | Removes entity from **JPA L2** | Already-managed L1; Spring Cache |
| `cacheManager.getCache("productViews").evict(7L)` | Removes key from **Spring Cache** | L1, L2, and database |
| `@CacheEvict(cacheNames="productViews", key="#p0")` | Removes Spring Cache entry when call is AOP-intercepted and condition passes | JPA L1, JPA L2 |
| Bulk SQL / external system commands | Modifies the **database** | Managed entities in L1; L2/Spring Cache depending on invalidation mechanism |

A logical bug example:

```java
@Cacheable(cacheNames = "productViews", key = "#p0")
public ProductView get(Long id) { /* reads DB via repository */ }

// Elsewhere:
entityManager.clear(); // DOES NOT evict productViews
```

The next call to `get(id)` can still return the stale `ProductView` from Spring Cache. Conversely, calling only `@CacheEvict` does not cause an already-managed entity in L1 to reload.

When using bulk `@Modifying` or native SQL, handle **both the persistence context and the relevant application-level caches**. For Hibernate L2/query cache, verify the specific provider and query invalidation behavior; for external writers, establish an event/eviction contract or an acceptable staleness policy.

## 8. Consistency, transaction, and multi-instance risks

**Post-commit eviction:** Using default `@CacheEvict` on a `@Transactional` method can violate expectations about interceptor/commit order, especially when the method is called within a larger transaction. Explicitly design eviction at successful DB commit using a transaction-aware cache manager or transaction events as illustrated.

**Cache stampede/races:** A slow read can fetch old data before commit and then populate the cache after the eviction event has fired. Hence `AFTER_COMMIT` does not guarantee linearizable consistency. For critical data, consider versioned keys, cross-node invalidation, lock/CAS mechanisms, or bypassing cache for certain reads.

**Multiple nodes:** `ConcurrentMapCacheManager` and in-process Caffeine caches normally exist only within each instance. Evicting on node A does not remove data on node B. Redis shares a cache backend, yet still requires key rules, TTL, and eviction from every write path; swapping the backend alone does not solve invalidation logic.

**TTL does not guarantee always-fresh data:** TTL limits how long an entry can exist (per backend), yet during that window users can still receive stale data.

**Multi-tenancy and personalized data:** If results depend on tenant, permissions, locale, or filters, the cache key must include all those dimensions. Using only `#id` for a per-user/tenant result can return someone else's data.

**Entities inside Spring Cache:** Caching JPA entities directly easily leads to detached entities, sessionless proxies, lazy-loading exceptions, out-of-transaction mutations, and desynchronized data. Generally prefer caching immutable DTOs/records with proper versioning/expiry.

**Hibernate L2 with frequently changing data:** Analyze hit rates, cache regions, consistency strategies, and invalidation costs. Caching a continuously updated entity may yield less benefit than caching read-heavy, write-rare reference catalogs.

## 9. How to verify which cache layer you are hitting

Instead of guessing, measure each layer separately:

1. **L1:** Inside a transaction, call `entityManager.find` twice with the same id and check reference equality; use SQL logs/statement metrics to observe the second read. Switch transactions or `clear` so scopes are not confused.
2. **L2:** Enable Hibernate statistics if supported (e.g., `hibernate.generate_statistics=true`) and read `secondLevelCacheHitCount`/miss/put counters via `SessionFactory`; create two independent persistence contexts to verify real hits. An L2 cache hit does not imply a Spring Cache hit.
3. **Query cache:** Verify query cache is enabled and individual queries are marked cacheable; measure `queryCacheHitCount` and actual SQL counts rather than inferring from `findAll()`.
4. **Spring Cache:** Use provider metrics or a log/counter inside the `@Cacheable` method body; invoke twice via the **Spring bean proxy**. In our example, the method body runs only on a miss. Use Actuator/metrics if your stack supports them.
5. **Invalidation:** Read → write in another transaction → read again; repeat with bulk updates, non-JPA SQL, additional nodes, rollbacks, and concurrent races. Inspect actual returned contents, not just entry counts.

Use integration tests to prove two distinct claims: "cache hits reduce DB accesses" and "when data changes, returned results still satisfy consistency requirements". A test proving hits alone does not prove eviction works.

## 10. Choosing a solution in practice

| Scenario | Typically reasonable choice |
| --- | --- |
| Reading/modifying entities within a single JPA transaction | Use built-in **L1** and dirty checking; do not try to cache managed entities in Spring Cache |
| Infrequently modified entity, frequently read across transactions | Consider **Hibernate/JPA L2** after benchmarking, choosing a concurrency strategy |
| Service output is a DTO, config, report, or expensive aggregate | Consider **Spring Cache** with explicit keys, TTL, backend, and eviction |
| A JPQL query with highly repetitive result sets | Consider **Hibernate query cache** only when profiling proves benefit |
| Multiple applications/SQL writers and nodes updating the same data | Define **cross-system invalidation**, events/outbox/CDC/TTL, and acceptable staleness limits |
| Near-real-time data or high correctness requirements | Prioritize consistency and transactions; consider **not caching** sensitive read paths |

**Remember:** `EntityManager.clear()`, `EntityManagerFactory.getCache().evict(...)`, and `@CacheEvict` are three operations across three different scopes. Choose caches according to the data and lifecycle they serve, then design invalidation whenever the database changes. "Caching enabled" is not proof that data is always accurate.

### Official documentation

- [Jakarta Persistence — Specification](https://jakarta.ee/specifications/persistence/)
- [Hibernate ORM User Guide — Caching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#caching)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Cache Annotations and Proxy Mode](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
