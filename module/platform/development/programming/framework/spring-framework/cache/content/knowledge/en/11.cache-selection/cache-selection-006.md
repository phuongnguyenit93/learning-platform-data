# SimpleCacheManager with a Predefined List of Caches

## Learning objectives

After this lesson, you can explain the role of `SimpleCacheManager` in Spring Cache, create and register a fixed-name list of `Cache` instances, distinguish **cache object**, **cache region**, and **entry key**, understand the manager initialization lifecycle, use `@Cacheable`/`@CacheEvict` properly with registered regions, and recognize when to choose a different manager.

In the **Cache region selection** group, the core point is: `SimpleCacheManager` manages **a predefined set of provided `Cache` objects**. The application decides which regions exist and how each region is created. The manager simply indexes them so cache operations find the right region by name.

## 1. Three naming layers and commonly confused responsibilities

Suppose an application has two types of data: products and categories:

```text
Spring caching interceptor (@Cacheable / @CacheEvict)
                |
                v
          CacheManager
                |
         getCache("products") -----> Cache "products"
                |                    |-- key "42" -> Product #42
         getCache("categories") --> Cache "categories"
                                     |-- key "42" -> Category #42
```

Concepts:

- **`CacheManager`:** component that looks up or manages caches by name, notably via `getCache(String name)` and `getCacheNames()`.
- **`Cache` (region / cache region):** store holding **key → value** pairs within a namespace, identified by `getName()`, such as `products` and `categories`.
- **Cache key:** identifies a single entry **inside** a region, such as `"42"`. Two different regions can share the same key without colliding.
- **Cache value:** content retained so subsequent reads can skip expensive computation/queries.
- **Backend/provider:** how data is actually stored, expired, evicted, shared, or serialized (such as `ConcurrentMapCache`, Caffeine, Redis).

For example, `products["42"]` and `categories["42"]` do not collide because they are in different cache regions, even though the key text is identical. If two services use the same region name and the same key with different value types, they can experience data collisions. Therefore **region selection** and **key design** are two separate decisions that must align.

## 2. What is SimpleCacheManager?

`org.springframework.cache.support.SimpleCacheManager` is a Spring Framework `CacheManager` implementation extending `AbstractCacheManager`, working with a **specified collection of `Cache` objects** via:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(productsCache, categoriesCache));
```

The snippet above is illustrative only: `productsCache` and `categoriesCache` must be previously created `org.springframework.cache.Cache` objects; `java.util.List` must be imported. The difference lies in passing **Cache instances**, not just names.

Key behaviors:

1. **Static list at initialization:** `SimpleCacheManager` loads the supplied caches and builds a name → `Cache` object map. It fits a known-ahead set of regions.
2. **Does not auto-generate new regions for unregistered names:** after initialization, `getCache("unknown")` returns `null` if no such cache exists; calling an annotated method referencing a non-existent region causes cache resolution to fail.
3. **Does not dictate TTL/memory-limit policies:** the manager does not add expiry, persistence, or distributed semantics to the `Cache`s it holds. Behavior belongs to each `Cache` implementation.
4. **Can accept caches that are already beans:** two `Cache` objects can be configured independently and passed into the manager via DI, preserving their declared names and configurations.
5. **Suitable for demos, tests, and apps with a small, stable set of caches:** simple management, easy verification of valid names.

The actual region name is the `Cache` object's name—for instance, `new ConcurrentMapCache("products").getName()` returns `"products"`. A **bean name** like `productStore` lets Spring DI distinguish beans; it **does not automatically rename** the region to `productStore`.

## 3. Proper configuration: create caches first, register via setCaches

Java config example creating two memory regions. If used in an existing Spring Boot application with Gradle and Java 17+, only the Spring Cache starter is needed to practice.

**File `src/main/java/example/simplecache/CacheConfiguration.java`:**

```java
package example.simplecache;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    // Spring bean name = productStore; actual cache name = products.
    @Bean("productStore")
    Cache productCache() {
        return new ConcurrentMapCache("products");
    }

    @Bean("categoryStore")
    Cache categoryCache() {
        return new ConcurrentMapCache("categories");
    }

    @Bean
    CacheManager cacheManager(
            @Qualifier("productStore") Cache products,
            @Qualifier("categoryStore") Cache categories) {

        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(products, categories));
        return manager;
    }
}
```

Explanation:

- `@EnableCaching` enables processing of cache annotations, typically through a Spring AOP proxy.
- `@Bean("productStore")` and `@Bean("categoryStore")` create Spring-managed **`Cache` objects**. They are themselves two separate caches, already named `products` and `categories`.
- `@Qualifier` selects the exact two cache beans to pass into the manager, avoiding ambiguity since multiple beans implement `Cache`.
- `manager.setCaches(List.of(products, categories))` declares the catalog of regions provided by the manager. The argument is a collection of caches, not a collection of name strings.
- `CacheManager` is the interface injected into classes that access caches programmatically; `@Cacheable(cacheNames = "products")` looks up the region through this manager.

**Lifecycle note:** `SimpleCacheManager` implements `InitializingBean` from `AbstractCacheManager`. When returned as a Spring `@Bean`, the container invokes the appropriate initialization callbacks (including `afterPropertiesSet()`) to load the region list. You do not need to call `afterPropertiesSet()` manually inside the `@Bean` method above. If instantiating the manager with `new` **outside** the Spring container, you must complete initialization yourself (e.g., `manager.afterPropertiesSet()`) before expecting `getCache(...)` to return the configured catalog.

### Quick configuration without making each Cache a bean

If you do not need to configure/inject individual caches separately:

```java
@Bean
CacheManager cacheManager() {
    SimpleCacheManager manager = new SimpleCacheManager();
    manager.setCaches(List.of(
            new ConcurrentMapCache("products"),
            new ConcurrentMapCache("categories")
    ));
    return manager;
}
```

This is an **alternative variant** for `cacheManager` above; do not use two `@Bean`s with the same name simultaneously in one configuration. The snippet requires the `@Bean`, `CacheManager`, `SimpleCacheManager`, `List`, and `ConcurrentMapCache` imports seen in the previous example. Both approaches share the same region contract; the first fits when you want to reuse or inject existing cache instances explicitly.

## 4. Runnable Spring Boot example (Java 17+)

Use `CacheConfiguration.java` from Section 3 together with the following two classes. Every file belongs in package `example.simplecache`, so `@SpringBootApplication` component scanning discovers them.

In an existing Spring Boot Gradle project, add the following dependency if not already present (keeping your project's existing plugins/versions and other dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/simplecache/CatalogService.java`:**

```java
package example.simplecache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger productLoads = new AtomicInteger();
    private final AtomicInteger categoryLoads = new AtomicInteger();

    @Cacheable(cacheNames = "products", key = "#p0")
    public String product(String id) {
        System.out.println("LOAD_PRODUCT #" + productLoads.incrementAndGet());
        return "Product-" + id;
    }

    @Cacheable(cacheNames = "categories", key = "#p0")
    public String category(String id) {
        System.out.println("LOAD_CATEGORY #" + categoryLoads.incrementAndGet());
        return "Category-" + id;
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void evictProduct(String id) {
        // Only evicts entry in products, does not touch categories.
    }
}
```

The `AtomicInteger` counters increment only if the read method body runs—that is, on a cache miss or when caching is not applied. Returning fixed strings isolates region selection from database dependencies.

**File `src/main/java/example/simplecache/SimpleCacheDemoApplication.java`:**

```java
package example.simplecache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SimpleCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SimpleCacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CatalogService catalog, CacheManager manager) {
        return args -> {
            System.out.println("products exists = " +
                    (manager.getCache("products") != null));
            System.out.println("categories exists = " +
                    (manager.getCache("categories") != null));
            System.out.println("prices exists = " +
                    (manager.getCache("prices") != null));

            System.out.println("product-1 = " + catalog.product("42"));
            System.out.println("product-2 = " + catalog.product("42"));
            System.out.println("category-1 = " + catalog.category("42"));
            System.out.println("category-2 = " + catalog.category("42"));

            catalog.evictProduct("42");
            System.out.println("product-3 = " + catalog.product("42"));
            System.out.println("category-3 = " + catalog.category("42"));
        };
    }
}
```

Run in the project directory:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

The `System.out` lines produced by the demo in exact order, excluding Spring Boot/Gradle startup logs:

```text
products exists = true
categories exists = true
prices exists = false
LOAD_PRODUCT #1
product-1 = Product-42
product-2 = Product-42
LOAD_CATEGORY #1
category-1 = Category-42
category-2 = Category-42
LOAD_PRODUCT #2
product-3 = Product-42
category-3 = Category-42
```

Interpretation:

1. `getCache("products")` and `getCache("categories")` both find their declared objects; `getCache("prices") == null` because `prices` is not in the list.
2. `catalog.product("42")` misses the first time in `products` so it prints `LOAD_PRODUCT #1`; the second call hits so the method body does not run.
3. `catalog.category("42")` also uses key `"42"`, yet in the **`categories` region**. Because the two regions are independent, the first call still misses (printing `LOAD_CATEGORY #1`); the second call hits.
4. `catalog.evictProduct("42")` removes only `products["42"]`. The subsequent product read misses and prints `LOAD_PRODUCT #2`. Entry `categories["42"]` remains, so the last category call still hits.
5. Returning the same `Product-42` string before and after eviction is because the simulated source is constant; **the source load count** is the proof distinguishing hits from misses.

**Why is this a runnable demo?** Both region names and keys are defined consistently; `public` methods are called from the `CommandLineRunner` bean to the `CatalogService` Spring bean so calls pass through the caching proxy; there are no concurrent requests or external services. All three Java files must reside in the matching directory/package, and `bootRun` requires a Spring Boot project with the appropriate Gradle plugin. This is not a standalone Java file that can be run via `javac` without Spring.

## 5. Differences from ConcurrentMapCacheManager and CaffeineCacheManager

All three implement `CacheManager`, yet **differ in how they create and manage regions**.

| Manager | How regions are defined | Characteristics |
| --- | --- | --- |
| `SimpleCacheManager` | Pass a collection of **`Cache` instances** via `setCaches(...)`. | Useful when you already have cache objects and want exact control over which regions are exposed. |
| `ConcurrentMapCacheManager` | Can manage caches by name; in dynamic mode, can create `ConcurrentMapCache` for new names; can configure fixed names. | Concise when all regions are `ConcurrentMapCache`. |
| `CaffeineCacheManager` | Can declare cache names or create on demand; uses Caffeine as backend. | Suitable when TTL/maximum size/Caffeine features are needed. |

`SimpleCacheManager` does not mean "always better than specialized managers". If all caches are local `ConcurrentMapCache`s and per-instance configuration is unnecessary, `ConcurrentMapCacheManager` can be more concise. If expiration or size limits are needed, pick a backend with those capabilities, such as Caffeine.

### Dynamic vs. static is an important distinction

- **Static:** the region list is published upfront by the application; a region name typo surfaces at resolution time rather than creating a mistyped region.
- **Dynamic:** some managers can spawn a cache for an unseen name (if configuration allows), useful for appropriate workloads yet able to hide naming bugs.

Thus, a static region list is a good choice when you want a clear, controlled, and testable **cache name contract**. It does not mean "entries are pre-populated": the `products` region can exist while **empty**, gaining entries only after a put/miss.

### Supplied Cache instances do not have to be ConcurrentMapCache

`SimpleCacheManager.setCaches(...)` accepts objects implementing `Cache`. In principle, they can be adapters for different backends if created properly by the application; however, doing so does not automatically grant distributed invalidation, shared TTLs, or shared serializers across backends. When combining backends, verify how each cache handles `null`, concurrency, expiry, and errors.

For example, to have a region use Caffeine with a TTL, you must create a **Caffeine-backed `Cache`** with the matching Caffeine config and pass it to the manager. `SimpleCacheManager` uses that instance rather than "upgrading" a `ConcurrentMapCache` into Caffeine just because a dependency was added.

## 6. Predefined cache list and initialization lifecycle

When Spring manages the bean:

```text
@Configuration creates @Bean Cache instances
           ↓
Create SimpleCacheManager and setCaches(collection)
           ↓
Spring container initializes bean (InitializingBean)
           ↓
AbstractCacheManager loads cache catalog and maps by getName()
           ↓
@Cacheable / @CachePut / @CacheEvict resolve caches by name
```

`SimpleCacheManager` inherits `AbstractCacheManager`'s `loadCaches()`/`afterPropertiesSet()` mechanism. **In a Spring application, let the container run bean initialization**. For objects instantiated manually outside the container, explicitly call `afterPropertiesSet()` after `setCaches`.

Do not treat `setCaches(...)` as an API for updating the cache list on every request. It describes the **initial input set of caches** for the manager; the normal pattern is finishing configuration during startup. Changing cache structure at runtime requires redefining the contract/lifecycle and choosing a suitable manager.

Two useful checks at startup:

```java
// Example in a place where CacheManager has been injected:
boolean productsPresent = manager.getCache("products") != null;
boolean categoryPresent = manager.getCacheNames().contains("categories");
```

`manager` here is the `CacheManager` variable already existing from the previous example. `getCacheNames()` lists **region names**, not the entry/keys currently inside each region. Do not rely on name ordering in comparisons unless the application defines an explicit ordering requirement.

## 7. What happens if a cache name does not exist?

In the demo:

```java
Cache unknown = manager.getCache("prices"); // null
```

`prices` is not registered. If a method has `@Cacheable(cacheNames = "prices")` served only by this `SimpleCacheManager`, cache resolution usually fails when the method is called through the proxy; there is no guarantee Spring will auto-create a new region.

Naming mistake example:

```java
// Wrong for the demo configuration: "product" differs from "products".
@Cacheable(cacheNames = "product", key = "#p0")
public String wrongName(String id) {
    return "Product-" + id;
}
```

Illustrative Java syntax inside a corresponding Spring bean. Do not patch the manager by creating an extra mistyped region just to make the error disappear: confirm which name is the canonical contract and use it consistently in annotations, config, and operational observability.

There are two distinct failure/miss classes:

- **Missing region name:** `getCache(name)` returns `null`; Spring cannot find a region to execute the operation.
- **Region exists, entry missing:** `getCache(name)` returns a valid `Cache`, while `cache.get(key)` misses. This is the normal case for `@Cacheable` to compute and put the value.

Distinguishing these two cases saves significant debugging time: a **missing region** is a configuration issue; a **missing entry** is a data/TTL/invalidation state.

## 8. Intentional cache region organization

Name caches after the **data contract**, not arbitrary method names:

- `productsById`: product data by ID.
- `categoriesById`: category data by ID.
- `productSearchResults`: search results, with composite keys containing filter/sort/page.
- `exchangeRates`: exchange rate table, with an appropriate expiry policy.

Decisions to make for every region:

| Question | Implementation implication |
| --- | --- |
| What kind of data does this region hold? | Avoid identical keys with different value types or semantics. |
| Which parameters form the key? | Never merge results across different tenants/locales/permissions; keep key generation consistent. |
| Who populates the data? | `@Cacheable` after a miss, `@CachePut`, or direct `Cache.put(...)` calls. |
| When is data removed? | `@CacheEvict`, invalidation jobs, backend TTL/size policies if present. |
| Are expiration or memory limits needed? | `ConcurrentMapCache` has no default TTL/maximum size; consider Caffeine/Redis or a suitable backend. |
| Single or multiple application instances? | Local caches in each JVM do not sync automatically with other instances. |
| Must data be partitioned by tenant/user? | Keys and permission checks must align; never treat a cache as an authorization mechanism. |

A good practice is storing region names as meaningful constants if shared across services, while ensuring annotations and `SimpleCacheManager` still resolve the exact **final name string**. With `@CacheConfig(cacheNames = "products")` at the class level, you can reduce name repetition across the class's operations; it does not create cache regions by itself.

## 9. Common mistakes

1. **Passing name strings to `setCaches`:** the API requires a collection of `Cache`s, such as `List.of(new ConcurrentMapCache("products"))`, not `List.of("products")`.
2. **Confusing bean name and cache name:** bean `productStore` may hold `ConcurrentMapCache("products")`; the annotation must use `products`.
3. **Failing to initialize a manager created outside Spring:** calling `setCaches` while skipping `afterPropertiesSet` leaves no guarantee the catalog is ready for lookup.
4. **Confusing region with entry:** `getCache("products") != null` only verifies the region exists; it does not prove key `"42"` is inside.
5. **Misspelling the cache name:** `products` and `product` are two different names; a static manager does not auto-create the missing name.
6. **Forgetting `@EnableCaching` or calling `this.method()` internally:** cache annotations are not applied as expected in default proxy mode.
7. **Assuming a default TTL exists:** `SimpleCacheManager` only coordinates; `ConcurrentMapCache` does not expire entries over time automatically.
8. **Creating too many regions without a contract:** makes it hard to know which regions to evict when source data changes, leading to stale data or extra load.
9. **Using a local region across multiple replicas and expecting sync:** evicting in JVM A does not remove entries in JVM B by default.
10. **Using inconsistent names/keys across `@Cacheable` and `@CachePut`:** updating one region while reading another leaves stale cache entries behind.

## 10. Verification exercises

After running the example in Section 4:

1. Call `manager.getCacheNames()` and print each name to see the exact regions you registered. Do not assume this list contains entry keys.
2. Add a `"prices"` region via `new ConcurrentMapCache("prices")` to the `setCaches(...)` list and re-run the process. The `prices exists` line will then change from `false` to `true`.
3. Change `@Cacheable(cacheNames = "products")` to `"product"` (dropping the `s`) and try calling it: observe the region resolution error, then restore the right name.
4. Use the same key `"42"` for both service methods as in the example to prove `products` and `categories` do not affect each other.
5. Call `evictProduct("42")`, proving only `LOAD_PRODUCT` increments while `LOAD_CATEGORY` stays unchanged; explain why.
6. Create a `SimpleCacheManager` **outside** the Spring container, call `setCaches(...)` then `afterPropertiesSet()` before using `getCache`; compare with the auto-initialized Spring bean.
7. If TTL is desired, try configuring a dedicated Caffeine backend and adding that cache instance to the list; confirm TTL is handled by the cache backend, not set by `SimpleCacheManager` itself.

### Pre-project checklist

- [ ] Clearly know the cache regions to manage and pick unique names matching the data contract.
- [ ] Created all **`Cache` instances**, named via `Cache.getName()`.
- [ ] Called `setCaches(...)` with that collection of caches and let Spring initialize the manager.
- [ ] Enabled `@EnableCaching`; ensured methods are called through the bean's proxy.
- [ ] Annotations use the right region names and key schemas; put/evict share the same contract as reads.
- [ ] Clearly know which provider handles TTL/size/serialization and local/distributed scope.
- [ ] Verified unregistered regions via `getCache(name)==null` and tested independent hits/misses across regions.

## Official documentation

- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — SimpleCacheManager API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html
- Spring Framework — CacheManager API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
