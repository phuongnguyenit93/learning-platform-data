# `@CacheConfig` Does Not Automatically Enable Cache Operations

## 1. Main Point: Default Configuration Differs from Cache Actions

In Spring Framework, `@CacheConfig` is a **class-level** annotation used to declare shared configuration values for **cache operations already declared** in that class. On its own, `@CacheConfig` **does not** turn every method in the class into a cached method, does not automatically create cache read/write/delete operations, and does not automatically enable Spring cache interception.

An easily misunderstood example:

```java
@Service
@CacheConfig(cacheNames = "products")
public class ProductService {
    public String findProduct(String id) {
        System.out.println("QUERY DB");
        return repository.findTitle(id);
    }
}
```

*This is an illustrative snippet, `repository` is not yet defined; a complete runnable example is in section 6.*

If you call `findProduct("P1")` multiple times, **the method body still runs every single time**, even though the class has `@CacheConfig(cacheNames = "products")`. Reason: Spring has not been instructed to apply a `@Cacheable`, `@CachePut`, or `@CacheEvict` operation to that method.

To cache the lookup result, an operation must be declared:

```java
@Service
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0")
    public String findProduct(String id) {
        System.out.println("QUERY DB");
        return repository.findTitle(id);
    }
}
```

In the second snippet, `@Cacheable` is the annotation that **declares behavior**: before invoking the method, check the cache; on a hit, return the cached data; on a miss, invoke the method and store the result if conditions are met. `@CacheConfig` only supplies the default `cacheNames = "products"` so the method does not have to repeat it.

**There is also an independent requirement:** the cache annotation processing mechanism must be enabled, usually via `@EnableCaching` on a Spring configuration class, and an appropriate `CacheManager`/`CacheResolver` must exist. Even when a method has `@Cacheable`, without the processing infrastructure or if the call does not go through a Spring proxy, caching will not take effect.

## 2. Three Layers to Distinguish

### Layer A — Shared Configuration Declaration: `@CacheConfig`

```java
@CacheConfig(cacheNames = "products")
public class ProductService {
    // Only declares the shared cache name.
}
```

It acts like a **set of default values** for methods that have cache operations. It does not mean "every method of the class is cached." This annotation can specify:

- `cacheNames` (also aliased as `value`): default cache name or list of cache names.
- `keyGenerator`: name of the `KeyGenerator` bean used when an operation does not specify its own key or another generator.
- `cacheManager`: name of the `CacheManager` bean used for operations inheriting that default.
- `cacheResolver`: name of the `CacheResolver` bean to dynamically resolve caches per operation.

`@CacheConfig` **does not have** single-operation attributes like `key`, `condition`, or `unless`; there is no "TTL = 60 seconds", "maximumSize", "sync", or "evict all entries" directly on this annotation. Policies like TTL, serialization, capacity, and eviction policy belong to the cache provider/configuration, not implicitly provided by `@CacheConfig`.

### Layer B — Behavior Declaration: `@Cacheable`, `@CachePut`, `@CacheEvict`

Operations state clearly what must be done:

| Annotation on Method | Behavior | Does the target method execute? |
| --- | --- | --- |
| `@Cacheable` | Look up key first; on miss, execute method and potentially store result | **Yes on miss**, **no on hit** in normal cases |
| `@CachePut` | Invoke method then update cache with normal result | **Yes** when the call is intercepted |
| `@CacheEvict` | Remove entry/entries as configured, before or after invocation | Normally **yes** |
| `@Caching` | Group multiple operations on a single method | Depends on the contained operations |

`@CacheConfig` is **not equivalent** to `@Caching`: one provides class-level defaults, while the other groups specific cache operations.

### Layer C — Execution Infrastructure: `@EnableCaching` + backend

`@EnableCaching` configures cache annotation processing via Spring AOP/cache interceptor in the default proxy mode. `CacheManager` supplies the real caches that operations need, such as an in-memory cache or a properly configured Redis backend.

```text
@EnableCaching + CacheManager
           |
           v
Spring cache infrastructure/proxy
           |
           | reads method cache operation metadata
           | + default values from @CacheConfig
           v
@Cacheable / @CachePut / @CacheEvict
           |
           v
Cache lookup/put/evict by name, key, and policy
```

If you only have `@EnableCaching` with **no method-level cache operations**, no automatic caching of all methods occurs. If you only have `@CacheConfig` **without `@EnableCaching`**, no cache advice is enabled under normal setup. For caching annotations to work, **both operation declarations and appropriate infrastructure** are required, and calls must pass through the interception point.

## 3. What Happens When a Class Only Has `@CacheConfig`

Consider the class:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    public String read(String sku) {
        return database.get(sku);
    }

    public String update(String sku, String title) {
        database.put(sku, title);
        return title;
    }
}
```

*This is an illustrative example, `database` is not yet declared.*

Even if a `catalog` cache exists in `CacheManager`, both methods above still run like ordinary Java methods. There is no automatic lookup before `read`, no automatic put after `update`, and no automatic eviction. `@CacheConfig` does not monitor operations on `database` to infer when caching is needed.

This does not mean the cache cannot change: **other code can still explicitly call `Cache.put(...)` or another method with a cache annotation can still write to the cache**. The exact conclusion is: **`@CacheConfig` itself does not generate any cache operation for methods merely because they belong to that class**.

If you want to apply defaults to `read` and `update`:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String read(String sku) {
        return database.get(sku);
    }

    @CachePut(key = "#p0")
    public String update(String sku, String title) {
        database.put(sku, title);
        return title;
    }
}
```

Here, both operations use the `catalog` cache declared by `@CacheConfig`. However, they still have **different behaviors**: `read` can return from the cache without entering the method; `update` always executes the method and can then write the return value to the cache. Ensuring that `update` returns the exact data form `read` expects, and that both keys have the same meaning, is the developer's design responsibility.

## 4. Default Inheritance Mechanism and Configuration Precedence

Spring supports three configuration levels for cache operations, from general to specific:

1. **Global level:** application-wide configuration (e.g., `CachingConfigurer` or cache infrastructure).
2. **Class level:** `@CacheConfig` provides defaults for operations in that class.
3. **Operation level:** attributes directly on `@Cacheable`, `@CachePut`, or `@CacheEvict`.

**Operation-specific configuration takes precedence over class-level defaults** when the same attribute is specified. Example:

```java
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String readDefault(String id) {
        return loadDefault(id);
    }

    @Cacheable(cacheNames = "catalog-preview", key = "#p0")
    public String readPreview(String id) {
        return loadPreview(id);
    }
}
```

*The snippet above is illustrative; the two methods `loadDefault` and `loadPreview` are not yet defined.*

- `readDefault` gets the cache name from `@CacheConfig`: `catalog`.
- `readPreview` declares its own cache name directly on `@Cacheable`: `catalog-preview`; thus it does not use the class-level cache name for that operation.
- Both have the expression `key = "#p0"` declared on the methods themselves.
- Having the same arguments on two methods does not make them share an entry if the cache names differ.

### 4.1. `keyGenerator` is only a way to generate keys, not a cache operation

Example:

```java
@CacheConfig(cacheNames = "catalog", keyGenerator = "myKeyGenerator")
public class CatalogService {
    @Cacheable
    public String find(String sku) {
        return lookup(sku);
    }
}
```

If the `myKeyGenerator` bean exists and is properly configured, `@Cacheable` can use that generator to create the key. But if `@Cacheable` is removed from `find`, `@CacheConfig(keyGenerator = ...)` also **does not cause Spring to automatically compute keys** on every normal call.

A single cache operation must not specify both `key` (SpEL) **and** its own `keyGenerator` at the same level; the two key-selection mechanisms are alternatives. If key calculation depends on multiple parameters, design it consistently across read, put, and evict.

### 4.2. `cacheManager` / `cacheResolver` are ways to locate caches

`@CacheConfig` can share manager/resolver bean names. They do not replace `@Cacheable`, `@CachePut`, or `@CacheEvict`. `cacheManager` and `cacheResolver` are two ways to resolve caches and should not be specified conflictingly on the same operation. To use the intended provider, the referenced bean must actually exist in the Spring context.

**Important note:** choosing `cacheNames = "catalog"` does not automatically create a physical cache, Redis key namespace, TTL, eviction policy, or transaction. The cache name is a piece of metadata for the operation to look up a cache; the existence, initialization, and configuration of the actual cache are determined by the provider/manager.

## 5. Sufficient and Insufficient Cases for Caching

| `@EnableCaching` | `@CacheConfig` | Cache Annotation on Method | Result in Normal Proxy Mode |
| --- | --- | --- | --- |
| Yes | Yes | **None** | No cache operation created from `@CacheConfig`; method runs normally |
| Yes | Yes | `@Cacheable` | Cache hit/miss possible; inherits defaults from `@CacheConfig` |
| Yes | Yes | `@CachePut` | Method runs, puts result if conditions are met |
| Yes | Yes | `@CacheEvict` | Evicts according to operation configuration |
| Yes | No | `@Cacheable(cacheNames = "catalog")` | Works: `@CacheConfig` is optional |
| No | Yes | `@Cacheable` | Annotation is in source but typically no cache advice is activated |
| Yes | Yes | Present, but called via `this.cachedMethod()` from the same bean | Self-invocation **is not intercepted by proxy** in default mode |
| Yes | Yes | Present, but object created with `new` outside container | No Spring proxy for that object, so no cache advice |

The table assumes a suitable `CacheManager`/`CacheResolver` and properly managed beans. A cache annotation can exist with misconfiguration (cache name not found, invalid key expression, missing manager bean, etc.), causing runtime errors; never assume caching works without verification.

## 6. Runnable Spring Boot Example: Same Class, Plain Methods and Cached Methods

This standalone example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and `ConcurrentMapCacheManager` as a local cache. There is a `CatalogService` class annotated with `@CacheConfig(cacheNames = "catalog")`, yet **not every method is cached**.

What to observe:

- `plain("P1")` has **no** cache operation annotation: every call enters the method body and **adds no entry** to the cache.
- `read("P1")` has `@Cacheable`: first call misses, second call hits.
- `change("P1", "Updated")` has `@CachePut`: the method runs and writes the new result under the key.
- `evict("P1")` has `@CacheEvict`: deletes the entry for that key.
- All three operations **do not have to repeat `cacheNames` on the method**, thanks to the class-level default.

### 6.1. Directory Structure

```text
cache-config-demo/
├── pom.xml
└── src/main/java/example/cacheconfig/
    ├── CacheConfigApplication.java
    └── CatalogService.java
```

### 6.2. `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. `src/main/java/example/cacheconfig/CatalogService.java` File

```java
package example.cacheconfig;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    private final ConcurrentMap<String, String> database =
            new ConcurrentHashMap<>(Map.of("P1", "Original"));

    private final AtomicInteger plainCalls = new AtomicInteger();
    private final AtomicInteger readCalls = new AtomicInteger();
    private final AtomicInteger changeCalls = new AtomicInteger();

    // NO operation annotation: @CacheConfig does not automatically add caching.
    public String plain(String sku) {
        System.out.println("BODY plain #" + plainCalls.incrementAndGet());
        return database.get(sku);
    }

    // @Cacheable is an operation; cacheNames is inherited from @CacheConfig.
    @Cacheable(key = "#p0")
    public String read(String sku) {
        System.out.println("BODY read #" + readCalls.incrementAndGet());
        return database.get(sku);
    }

    // @CachePut always invokes the method and uses the result to update the same key.
    @CachePut(key = "#p0")
    public String change(String sku, String newTitle) {
        System.out.println("BODY change #" + changeCalls.incrementAndGet());
        database.put(sku, newTitle);
        return newTitle;
    }

    // @CacheEvict removes the entry after the method completes normally.
    @CacheEvict(key = "#p0")
    public void evict(String sku) {
        System.out.println("BODY evict " + sku);
    }
}
```

### 6.4. `src/main/java/example/cacheconfig/CacheConfigApplication.java` File

```java
package example.cacheconfig;

import java.util.Objects;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheConfigApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    @Bean
    CommandLineRunner demo(CatalogService service, CacheManager cacheManager) {
        return args -> {
            Cache catalog = Objects.requireNonNull(cacheManager.getCache("catalog"));

            System.out.println("PLAIN1 => " + service.plain("P1"));
            System.out.println("PLAIN2 => " + service.plain("P1"));
            System.out.println(
                "ENTRY_AFTER_PLAIN => " + (catalog.get("P1") != null)
            );

            System.out.println("READ1 => " + service.read("P1"));
            System.out.println("READ2 => " + service.read("P1"));
            System.out.println(
                "ENTRY_AFTER_READ => " +
                Objects.requireNonNull(catalog.get("P1")).get()
            );

            System.out.println("CHANGE => " + service.change("P1", "Updated"));
            System.out.println("READ3 => " + service.read("P1"));

            service.evict("P1");
            System.out.println(
                "ENTRY_AFTER_EVICT => " + (catalog.get("P1") != null)
            );
            System.out.println("READ4 => " + service.read("P1"));
        };
    }
}
```

### 6.5. Running the Program

Requires JDK **17 or higher**, Maven, and access to download Maven dependencies when not already in the local cache. Inside the `cache-config-demo` directory, run:

```bash
mvn spring-boot:run
```

The lines printed by the demo will appear in the **exact order** below (Spring Boot also prints its own startup logs):

```text
BODY plain #1
PLAIN1 => Original
BODY plain #2
PLAIN2 => Original
ENTRY_AFTER_PLAIN => false
BODY read #1
READ1 => Original
READ2 => Original
ENTRY_AFTER_READ => Original
BODY change #1
CHANGE => Updated
READ3 => Updated
BODY evict P1
ENTRY_AFTER_EVICT => false
BODY read #2
READ4 => Updated
```

### 6.6. Result Analysis

**PLAIN1 and PLAIN2 turns:** `CatalogService` has `@CacheConfig(cacheNames="catalog")`, but `plain` has no cache operation. Therefore, every call prints `BODY plain`. After both calls, `catalog.get("P1") == null`, giving `ENTRY_AFTER_PLAIN => false`. This is direct proof that class-level `@CacheConfig` **does not enable caching automatically**.

**READ1 turn:** `@Cacheable` on the `read` method is a cache operation. Spring selects the `catalog` cache from `@CacheConfig`, computes the key from `#p0 = "P1"`, sees a miss, and executes the method; the result `Original` is stored.

**READ2 turn:** same key `"P1"`, Spring hits and returns `Original` directly from the cache, so no additional `BODY read` is printed. `ENTRY_AFTER_READ => Original` confirms the cache holds the entry.

**CHANGE turn:** `@CachePut` **always executes** `change`, writes `Updated` to the simulated database, and writes the returned `Updated` to the `catalog["P1"]` cache. Because `READ3` uses the same cache/key, it hits `Updated`; `BODY read` is not printed.

**EVICT turn:** `@CacheEvict(key="#p0")` deletes the `P1` entry after `evict` returns. `ENTRY_AFTER_EVICT => false` indicates the key is no longer in the cache.

**READ4 turn:** the key was deleted so it misses; the `read` method runs for the second time, reads `Updated` from the simulated database, and stores it again.

**Conditions making the demo reproducible:** `CommandLineRunner` receives `CatalogService` via dependency injection, calling it from another bean through the Spring proxy. `@EnableCaching` enables annotation processing; `ConcurrentMapCacheManager("catalog")` creates the exact cache named in `@CacheConfig`. Objects and counters are initialized in a fresh process with no other threads modifying them. All output above is deterministic business flow from the code; it excludes framework logs/banners.

## 7. What if `@Cacheable` is removed while keeping `@CacheConfig`?

Imagine replacing:

```java
@Cacheable(key = "#p0")
public String read(String sku) {
    return database.get(sku);
}
```

with:

```java
public String read(String sku) {
    return database.get(sku);
}
```

If you only remove `@Cacheable`, no operation is declared on `read`. `@CacheConfig(cacheNames="catalog")` **is still on the class**, yet calls to `read` are no longer handled by the cache interceptor for lookup/put as before. Even if a cache entry already exists, the method will not automatically retrieve that entry; it executes its own logic.

This is also why you should not expect that adding `@CacheConfig` to an entire repository/service will "automatically optimize" all methods. Spring Cache is a **declarative per-operation** mechanism, not an automatic memory recording every method call on a class.

Conversely, removing `@CacheConfig` alone while keeping `@Cacheable(cacheNames="catalog")` on the method, along with `@EnableCaching` and a valid `CacheManager`, still allows caching to work. `@CacheConfig` helps avoid repeating parameters, rather than being a mandatory requirement to use caching.

## 8. What if `@Cacheable` is attached but the method still runs every time?

Seeing a method run repeatedly does not automatically mean `@CacheConfig` is "not working"; you must classify the cause:

| Symptom | Possibilities to Check |
| --- | --- |
| Class has `@CacheConfig`, method has no operation | Nothing to cache: working as designed |
| Method has `@Cacheable` but cache annotation processing is not enabled | Need `@EnableCaching` or equivalent configuration |
| Method has annotation, but object was created with `new` | Not managed/proxied by Spring |
| Cacheable method called via `this.method()` within the same bean | Self-invocation bypasses proxy in default mode |
| Method has `@Cacheable(condition=...)` evaluating to `false` | Call bypasses cache and method still executes |
| Method has `@Cacheable(unless=...)` vetoing the result | Cache does not store the new result; next call may miss |
| Cache name on method differs from class name | Method-level override; checking a different cache |
| Different keys generated between two calls | Each key has its own lookup |
| Cache entry evicted/expired or cache manager not shared across instances | May miss even if previously stored elsewhere |
| Method/annotation cannot be intercepted by proxy | Check visibility, bean/proxy structure, and mode |

In default proxy mode, only calls **going through the proxy** are cache-intercepted. Example:

```java
@Service
@CacheConfig(cacheNames = "catalog")
public class CatalogService {
    @Cacheable(key = "#p0")
    public String read(String sku) {
        return lookup(sku);
    }

    public String callInternally(String sku) {
        return this.read(sku); // self-invocation; bypasses default cache proxy
    }
}
```

*Illustrative snippet, not standalone because `lookup` is not yet defined.*

A maintainable solution is to move the cacheable method into a separate Spring bean called by another bean via dependency injection. Watch out for private or final methods, calls from constructors, and relying on AOP before a bean finishes initializing. Weaving modes other than proxies exist, but they require explicit configuration.

## 9. `@CacheConfig` does not define TTL and does not guarantee fresh data

A common misconception is using `@CacheConfig(cacheNames="catalog")` and expecting:

- cache entries to expire automatically after a fixed duration;
- results to synchronize automatically when the database changes;
- all applications/instances to share a single cache memory;
- capacity limits or appropriate serialization policies to be applied;
- database updates and cache updates to happen in an atomic transaction.

`@CacheConfig` **does not contain** these policies. They are configured on the cache provider, `CacheManager`, invalidation strategy, transaction-aware cache, and system architecture.

For instance, `ConcurrentMapCacheManager` in the demo is **single-JVM** memory and has no default TTL unlike some providers with expiration policies. Caffeine, Redis, or other cache providers have their own TTL/size/eviction mechanisms. Giving a cache the same name across multiple nodes **does not automatically create shared memory**.

Even when `@Cacheable` is genuinely working, the key must distinguish input values that affect the result (e.g., tenant, locale, price tier). You must evict/put or version properly when data changes; `@CacheConfig` does not automatically detect those business dependencies.

## 10. Using `@CacheConfig` in Practice

Use `@CacheConfig` when **multiple methods in the same class** actually have cache operations and share the same defaults. For example, a class with a cacheable `findById`, cache-put `save`, and cache-evict `delete`, all sharing the `products` cache namespace.

Benefits:

- **Reduce cache name repetition:** rename the shared cache in one place.
- **Consistency of key generator/manager/resolver:** prevent one method from using manager A while another accidentally uses manager B when they should share one.
- **Easier configuration inspection:** class-wide metadata sits in one place, while specific behavior remains explicitly declared on each method.
- **Intentional overrides possible:** special methods declare their own `cacheNames` or operation-level config.

Do not use `@CacheConfig` merely as a "marker indicating a cached class" while omitting operation declarations. If every method has different behavior, prefer specific annotations at the method level; do not force a shared default just to save a few lines.

### Example of multi-cache operations with an override

```java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0")
    public String getById(String id) {
        return loadById(id);
    }

    @Cacheable(cacheNames = "product-search", key = "#p0")
    public String search(String keyword) {
        return searchDatabase(keyword);
    }

    @CacheEvict(key = "#p0")
    public void deleteById(String id) {
        deleteFromDatabase(id);
    }
}
```

*This snippet illustrates configuration; the helper methods are not yet declared.*

In the example, `getById` and `deleteById` use the `products` default, whereas `search` intentionally uses `product-search`. A product update may need to invalidate **both the lookup cache and the search cache**, depending on how results depend on each other; `@CacheConfig` does not infer this relationship automatically.

## 11. Common Mistakes

1. **Placing `@CacheConfig` on a class and omitting `@Cacheable`.** There is no automatic read/store behavior on methods not marked with an operation.
2. **Assuming `@EnableCaching` automatically caches every method.** It only activates the processor for declared operations.
3. **Forgetting the manager/resolver bean or declaring a non-existent cache name.** Metadata cannot substitute for storage infrastructure; misconfiguration can cause runtime errors.
4. **Confusing cache defaults with cache provider policies.** `@CacheConfig` does not provide TTL, max size, or Redis serialization.
5. **Thinking method-level config gets overridden by class config.** The opposite is true: operation level takes precedence for specified attributes.
6. **Confusing `@CachePut` with `@Cacheable`.** Put executes the method then may store the result; Cacheable may skip the method on a hit.
7. **Calling a cacheable method from the same bean via `this.`.** In default proxy mode, bypassing the proxy means no cache interception.
8. **Using `@CacheConfig(keyGenerator=...)` while also specifying `key` on the method and expecting the generator to still run.** The operation's key expression is the specific choice; design one consistent key strategy.
9. **Sharing the same cache name/key for methods with different return types.** One operation may retrieve data written by another operation and encounter the wrong type or meaning.
10. **Treating class configuration as a transaction or freshness guarantee.** Data consistency depends on the backend, invalidation, and separate transaction orchestration.

## 12. Self-Check Questions

**Question 1.** A class has `@Service`, `@CacheConfig(cacheNames="books")`, and a `findBook` method with no other annotation. If you call the same ID twice, will the second call definitely be a cache hit?

**Answer:** No. `@CacheConfig` does not automatically create a cache operation. The method still executes normally both times unless caching is applied by another mechanism outside the snippet under consideration.

**Question 2.** You already have `@EnableCaching`, `CacheManager`, and `@CacheConfig(cacheNames="books")`. Is that enough to cache a method without `@Cacheable`?

**Answer:** Not yet. An operation annotation on the method (or an equivalent declarative mechanism) is required so Spring knows which calls need cache handling.

**Question 3.** A class declares `@CacheConfig(cacheNames="books")`, and a method declares `@Cacheable(cacheNames="featured")`. Which cache does the method use?

**Answer:** `featured`, because operation-level configuration overrides class-level defaults.

**Question 4.** A method has `@Cacheable` but is only called via `this.find(...)`. Why are there no cache hits/misses as expected?

**Answer:** Self-invocation in default proxy mode bypasses the Spring cache proxy. You need to call through the Spring bean proxy or configure appropriate interception.

**Question 5.** Can you write `@CacheConfig(ttl=60)` so every cache in the class expires automatically?

**Answer:** No. `@CacheConfig` has no `ttl` attribute. Configure expiration on the cache provider/`CacheManager` or an appropriate cache lifecycle management policy.

**Question 6.** A class has `@CacheConfig` and three methods: no annotation, `@Cacheable`, and `@CachePut`. Are all three handled the same way by the Spring cache interceptor?

**Answer:** No. The unannotated method has no automatic operation; `@Cacheable` performs hit/miss handling and can skip the method, while `@CachePut` executes the method and stores the result.

## References

- Spring Framework Reference — *Declarative Annotation-based Caching*, `@CacheConfig` and *Enabling Caching Annotations* sections: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@CacheConfig`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework Javadoc — `@EnableCaching`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Boot Reference — *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html
