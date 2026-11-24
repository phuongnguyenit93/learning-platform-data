# Handling Missing or Unallocated Cache Names in Spring Cache

## Lesson objective

When configuring `@Cacheable(cacheNames = "products")`, many developers assume Spring always already has a cache region named `products`. In reality, the annotation only **requests using that cache name**; whether the cache is found or created depends on **`CacheResolver`, `CacheManager`, and the cache provider**. A typo can cause a runtime exception, or silently create an unintended cache when the manager allows dynamic creation.

After this lesson, you will be able to:

- Distinguish **non-existent cache name**, **unallocated cache region**, **missing cache entry**, and **unreachable cache backend**.
- Understand the `CacheManager.getCache(name)` contract and the difference between a dynamic-creating manager and one restricting cache names.
- Diagnose a failing `@Cacheable` call caused by an unallocated cache rather than confusing it with a cache miss.
- Pre-register cache names, select the right `CacheManager`, validate configuration at startup, and write tests for valid/invalid names.
- Understand options for Spring Boot, Caffeine, Redis, and `CompositeCacheManager` at a principled level without assuming every provider behaves identically.
- Run a Java 17 + Spring Framework example demonstrating strict and dynamic modes.

**Key takeaway:** A cache name appearing in an annotation **does not guarantee the physical cache already exists**. The system may create the cache on demand, return `null`, or fail due to configuration/infrastructure. Define the allocation strategy explicitly rather than relying on guesswork.

## 1. Distinguishing four commonly confused states

### 1.1. Cache name not recognized by the manager

Example:

~~~java
@Cacheable(cacheNames = "prodcuts", key = "#p0") // typo for "products"
public Product findById(long id) {
    return repository.findById(id);
}
~~~

This is illustrative code with external `Product` and `repository`.

The annotation requests the `prodcuts` region instead of `products`. If the manager accepts only `products`, the call may fail when Spring tries to resolve cache `prodcuts`. If the manager auto-creates regions on demand, it can create **a new mistyped cache region**, and the bug only surfaces indirectly through hit ratios, memory, or inconsistent data.

### 1.2. Valid cache region that is not yet allocated

Some managers/providers manage caches **lazily**: before first use, the region does not exist in memory or in the list of created caches; when `getCache("products")` is called, the manager can initialize a cache and return it.

Therefore, `getCacheNames()` right after application startup may not include every name **permitted to be created later**. Do not conclude that any name absent from the list is invalid without checking the manager's mode.

### 1.3. Region exists, but entry for the key does not exist yet (cache miss)

This is the normal situation:

~~~text
CacheManager.getCache("products") -> Valid Cache
Cache.get(42)                   -> no entry
@Cacheable                      -> calls source method
                                   then considers storing result
~~~

Fundamental difference: **a cache miss only concerns one key inside an already successfully resolved cache region**. It does not mean `CacheManager` returned `null`.

### 1.4. Region name is right, but infrastructure fails

For example, Redis is unreachable, credentials fail, network timeouts occur, or serialization fails. This is not necessarily "cache name does not exist". `CacheManager.getCache(name)` may still return a `Cache` object, while `get`, `put`, or `evict` throws an error.

Troubleshooting must follow the **root exception and provider type**, not randomly renaming caches or wiping data.

## 2. How do CacheManager and CacheResolver resolve cache names?

### 2.1. The CacheManager contract

Spring provides the `org.springframework.cache.CacheManager` interface:

~~~java
Cache getCache(String name);
Collection<String> getCacheNames();
~~~

This is an **excerpted signature to explain the API**, not a complete Java class.

- `getCache(name)`: looks up a cache by name; depending on the implementation, may **create lazily**; may return `null` if the cache does not exist or cannot be created.
- `getCacheNames()`: returns the list of caches the manager **currently knows**. In dynamic mode, this is not by default the list of all possible future names.

Do not write `cacheManager.getCache("prodcuts").get(42)` without a `null` check; if the name is unsupported, this code easily throws `NullPointerException` and obscures the root cause.

For programmatic access, check explicitly:

~~~java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("products"),
    "Cache 'products' is unavailable"
);
~~~

This is an **illustrative snippet**; it requires importing `java.util.Objects`, `org.springframework.cache.Cache`, and having `cacheManager` available.

### 2.2. Default behavior of cache annotations

When using annotations like `@Cacheable`, Spring uses a cache resolver to determine the `Cache` objects corresponding to the cache names. A common setup is `SimpleCacheResolver`, using the configured `CacheManager`.

Typical flow:

~~~text
Call @Cacheable(cacheNames="products")
                 |
          Spring caching proxy
                 |
       CacheResolver.resolveCaches(...)
                 |
        CacheManager.getCache("products")
                 |
         +-------+--------+
         |                |
     has Cache        returns null
         |                |
  check key/hit/miss  default resolver
                      reports cache resolution error
~~~

With the default resolver, if a cache name is requested but `CacheManager` cannot return a cache for that name, the intercepted call typically throws an **`IllegalArgumentException` related to not finding the cache name**. This usually occurs **when the method is invoked**, not necessarily immediately when the Spring ApplicationContext starts up.

**Exception:** a custom `CacheResolver` may handle this differently (e.g., returning no cache, routing dynamically, or reporting a custom error). Always inspect the actual configuration before claiming a single exception type for every project.

### 2.3. Names are case-sensitive and whitespace-sensitive

Cache region names are string identifiers. Do not assume `"products"`, `"Products"`, and `"products "` are the same cache. Standardize naming, prefer constants or centrally managed name groups in code, and test against the real `CacheManager`.

## 3. Dynamic and static: the same manager can behave in two ways

`ConcurrentMapCacheManager` is an easy-to-verify example in Spring Framework.

### 3.1. Dynamic mode: instantiated with no names

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager();
}
~~~

With the no-arg constructor, `ConcurrentMapCacheManager` can **create cache regions on demand** when `getCache(name)` is called. Therefore:

- `getCacheNames()` can be empty right after initialization.
- `getCache("products")` can create and return a cache named `products`.
- If an annotation mistypes `"prodcuts"`, a mistyped region can also be created. No exception occurs merely for a typo in this case.

Pros: quick for prototyping, no need to list every region upfront. Cons: easily hides spelling mistakes and spawns unintended cache regions.

### 3.2. Static/strict mode: declaring allowed names

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager(
        "products", "productSummaries", "categoryLists"
    );
}
~~~

The constructor taking a list of names puts `ConcurrentMapCacheManager` into a mode that **manages only the declared caches**. When requesting another name:

~~~text
getCache("products")  -> Cache
getCache("prodcuts")  -> null
~~~

With `@Cacheable(cacheNames = "prodcuts")`, the default resolver finds no region and fails on the call that needs caching.

Strict mode helps **catch wrong cache names** sooner, though you must update the list when adding valid cache regions and write tests to detect misconfiguration before deployment.

### 3.3. Comparison

| Check | Dynamic ConcurrentMapCacheManager | Static ConcurrentMapCacheManager |
| --- | --- | --- |
| Initialization | `new ConcurrentMapCacheManager()` | `new ConcurrentMapCacheManager("products")` |
| Valid name, first use | Creates cache lazily | Returns declared cache |
| New undeclared name | Can create a new region | `getCache(name)` returns `null` |
| Typo risk | Easily creates wrong region | Surfaces error at resolution |
| Can `getCacheNames()` be treated as a complete allow-list? | No | In static model, it is the declared list |
| Choice | Demos / intentional open declaration | Systems wanting name control |

**Do not generalize this table to every CacheManager.** Redis, Caffeine, JCache, or custom caches have different region creation policies and also depend on each provider's configuration.

## 4. Java 17 demo: one valid annotation, one mistyped annotation

The program below creates **two independent ApplicationContexts** for comparison:

1. **StrictConfig**: declares only cache `products`. Calling `@Cacheable(cacheNames = "mistypedProducts")` is rejected before the method body runs.
2. **DynamicConfig**: uses a manager without a fixed list. The same `mistypedProducts` annotation is accepted and creates a new cache.

The program runs with Java 17+, Maven, and Spring Framework 6.2.10. Spring Boot is omitted so that distinguishing `CacheManager` policies is not affected by auto-configuration.

### 4.1. Project structure

~~~text
missing-cache-name/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MissingCacheNameDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>missing-cache-name</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
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

### 4.3. src/main/java/demo/MissingCacheNameDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MissingCacheNameDemo {

    @Configuration
    @EnableCaching
    public static class StrictConfig {
        @Bean
        public CacheManager cacheManager() {
            // Only names in this list are allocated.
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    @Configuration
    @EnableCaching
    public static class DynamicConfig {
        @Bean
        public CacheManager cacheManager() {
            // No allow-list: caches are created on demand.
            return new ConcurrentMapCacheManager();
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger productCalls = new AtomicInteger();
        private final AtomicInteger typoCalls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String findProduct(long id) {
            int n = productCalls.incrementAndGet();
            return "Product-" + id + " (load=" + n + ")";
        }

        @Cacheable(cacheNames = "mistypedProducts", key = "#p0")
        public String findWithTypo(long id) {
            int n = typoCalls.incrementAndGet();
            return "Other-" + id + " (load=" + n + ")";
        }

        public int productCalls() {
            return productCalls.get();
        }

        public int typoCalls() {
            return typoCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                new AnnotationConfigApplicationContext(StrictConfig.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            CacheManager manager = ctx.getBean(CacheManager.class);

            System.out.println("STRICT:");
            System.out.println(service.findProduct(7L));
            System.out.println(service.findProduct(7L));
            System.out.println("Product calls: " + service.productCalls());
            System.out.println(
                "Missing region: " +
                (manager.getCache("mistypedProducts") == null));

            try {
                service.findWithTypo(7L);
            } catch (IllegalArgumentException ex) {
                System.out.println(
                    "Rejected missing cache: " +
                    ex.getMessage().contains("mistypedProducts"));
            }
            System.out.println("Typo calls: " + service.typoCalls());
        }

        try (var ctx =
                new AnnotationConfigApplicationContext(DynamicConfig.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            CacheManager manager = ctx.getBean(CacheManager.class);

            System.out.println("DYNAMIC:");
            System.out.println(
                "Known before: " + manager.getCacheNames().size());
            System.out.println(service.findWithTypo(7L));
            System.out.println(service.findWithTypo(7L));
            System.out.println("Typo calls: " + service.typoCalls());
            System.out.println(
                "Missing region was created: " +
                (manager.getCache("mistypedProducts") != null));
            System.out.println(
                "Known after: " + manager.getCacheNames().size());
        }
    }
}
~~~

**Why not share one ApplicationContext?** The two contexts use two different `CacheManager`s, each with its own `ProductService` and counters. This keeps results transparent and independent of cache state from the previous run.

### 4.4. How to run

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MissingCacheNameDemo
~~~

Lines **printed by the program** (excluding Maven logs):

~~~text
STRICT:
Product-7 (load=1)
Product-7 (load=1)
Product calls: 1
Missing region: true
Rejected missing cache: true
Typo calls: 0
DYNAMIC:
Known before: 0
Other-7 (load=1)
Other-7 (load=1)
Typo calls: 1
Missing region was created: true
Known after: 1
~~~

### 4.5. Explaining the output

1. `StrictConfig` allocates the `products` region. The first `findProduct(7)` call is a normal cache miss, the second hits; the method body runs only **once**.
2. `manager.getCache("mistypedProducts") == null` is `true`: there is no mistyped cache region and the manager does not create it.
3. Calling `findWithTypo(7)` through the proxy is rejected during cache resolution, before the real method runs. Hence `Typo calls: 0`.
4. `DynamicConfig` starts with no allocated cache regions; `getCacheNames().size()` returns 0.
5. Calling `findWithTypo(7)` creates a new cache named `mistypedProducts`. The second call hits, so `Typo calls: 1`.
6. After allocation, the region exists and the total number of known regions is 1.

**Takeaway:** An invalid cache name may fail loudly **or be created as a brand-new region**, depending on the manager policy. Running without errors **does not mean the cache name matches the design**.

## 5. Practical handling when a cache name does not exist

Follow a diagnostic sequence rather than blindly editing cache names.

### Step 1: Record the name in the error message

Inspect the full exception: the requested name, the annotated method, the `CacheManager` type used, and nested causes if any.

A common error with the default resolver when a cache is not found:

~~~text
IllegalArgumentException: Cannot find cache named 'unknownName' for ...
~~~

This is an **illustrative message format** (the part after `for` also contains cache operation details); it is not a contract across all versions/providers.

### Step 2: Cross-check exact cacheNames at declaration sites

Check:

- `@Cacheable(cacheNames="...")`, `@CachePut`, `@CacheEvict`, `@Caching`.
- `@CacheConfig(cacheNames = {...})` at the class level, which may provide default cache names.
- `cacheManager` or `cacheResolver` on the annotation/class, if the application uses multiple managers.
- Cache name constants, typos, casing, singular/plural forms, whitespace, and profile environments.
- Whether the method goes through the cache proxy: self-invocation can bypass advice and hide errors.

Do not change any name before understanding the cache region creation mechanism and what data already exists in the old region.

### Step 3: Verify which CacheManager is actually selected

A system may have multiple managers, for example:

- `localCacheManager` for RAM caches.
- `distributedCacheManager` for Redis.
- A custom `CacheResolver` routing by tenant or method.

A valid name in manager A does not mean it exists in manager B.

**Illustrative example when the application has registered a bean with the matching name**:

~~~java
@Cacheable(
    cacheNames = "products",
    cacheManager = "distributedCacheManager",
    key = "#p0"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

If there is no manager bean named `distributedCacheManager`, that is a bean/resolver configuration issue, **not just** a missing region. `cacheManager` and `cacheResolver` are two alternative resolution selection mechanisms and must not be used simultaneously on one cache operation.

### Step 4: Decide whether creating a new cache region is allowed

If a new cache region is intentional, **declare/allocate it properly** according to the provider instead of switching the whole system to dynamic mode just to avoid one isolated error.

If the application needs typo protection, prefer an explicit allow-list and verification tests. Dynamic mode is appropriate only when cache names are designed to be generated flexibly with controlled region cardinality.

### Step 5: Re-verify with integration tests

Prove both things:

1. Permitted names resolve properly and cache hits actually work.
2. Unpermitted names are rejected (for strict configs), or allocated only under agreed dynamic rules.

Looking only at startup logs ("Application started") can miss errors; many cache names are only resolved **when the method is called**.

## 6. How to register/allocate cache names properly

### 6.1. Spring Framework: fixed list in Java Config

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
            "products",
            "productSummaries",
            "categoryLists"
        );
    }
}
~~~

This is **illustrative configuration code**, assuming imports for `Configuration`, `EnableCaching`, `Bean`, `CacheManager`, and `ConcurrentMapCacheManager`. When adding `@Cacheable(cacheNames = "productSearch")`, decide whether to declare `productSearch` first or switch the annotation to the region name actually intended.

### 6.2. Spring Boot with the simple cache provider

With **Spring Boot using the simple cache provider** (backed by `ConcurrentMapCacheManager`) and when Boot auto-configures the manager, you can restrict names via configuration:

~~~properties
spring.cache.type=simple
spring.cache.cache-names=products,productSummaries,categoryLists
~~~

This is an **illustrative application.properties**, not a step to apply to the Maven demo in Section 4. When using `spring.cache.type=simple`, regions outside the list are rejected at usage time; a typo may not surface at application startup. Auto-configuration details vary by Boot version, provider, and whether the application provides its own `CacheManager` bean.

**Do not treat `spring.cache.cache-names` as a strict guarantee for every provider.** Providers have differing dynamic region creation behavior; verify how the provider is configured under the real profile.

### 6.3. Caffeine

`CaffeineCacheManager` supports both on-demand region creation and pre-registering cache names, depending on how the manager and custom caches are set up. Pick the right mode to prevent typos, while also checking TTL, maximumSize, refresh, and per-region policies.

Do not copy a `ConcurrentMapCacheManager` setup verbatim to Caffeine and assume backend options are identical.

### 6.4. Redis

With Spring Data Redis, `RedisCacheManager` can be configured with initial caches and a policy **allowing or disabling creation of undeclared caches**. For instance, the builder API `disableCreateOnMissingCache()` rejects dynamic creation of Redis cache regions for names absent from configuration.

This is **provider configuration guidance**, not blind advice: check your Spring Data Redis version, cache names, key prefix, TTL, and actual Redis connectivity. Having a `RedisCache` object does not prove the Redis backend is ready to serve `GET/SET`.

### 6.5. SimpleCacheManager/JCache and explicitly allocated providers

Some managers manage a set of caches registered or allocated from a native provider. With those managers, initialize/create cache regions via the proper API rather than expecting `getCache(name)` to always auto-allocate. JCache/Ehcache/Hazelcast/Infinispan each have their own lifecycle and configuration. Always check the documentation for the implementation in use.

## 7. Startup validation: detecting missing caches earlier than runtime

Many cache name errors only appear on rarely called code paths. In strict systems, you can verify a **list of required caches** right after Spring initializes.

Example **illustrative Java code for application integration**, not part of the standalone demo:

~~~java
import java.util.List;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public final class RequiredCacheChecker
        implements SmartInitializingSingleton {

    private final CacheManager cacheManager;

    public RequiredCacheChecker(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @Override
    public void afterSingletonsInstantiated() {
        for (String name : List.of(
                "products", "productSummaries", "categoryLists")) {
            if (cacheManager.getCache(name) == null) {
                throw new IllegalStateException(
                    "Required cache is missing: " + name);
            }
        }
    }
}
~~~

Benefit: when using a **static/strict manager**, a missing required cache fails startup cleanly before receiving traffic.

**Warning:** With a dynamic manager, calling `getCache(name)` inside the checker **can create the cache itself** and report "valid", even for a mistyped name. Startup validation must therefore be paired with a canonical name list, a static policy, or a non-creating lookup mechanism (if supported by the provider). Do not treat this checker as proof that data exists in the cache or that the Redis backend is reachable.

Moreover, the checker above verifies a **fixed list you declare**, and does not automatically scan every name across all source annotations. To catch mistyped annotations, supplement it with integration tests calling cached methods against a strict resolver, or configuration validation rules in tests/CI.

## 8. Fallback options and when not to swallow errors

### 8.1. Should caching be skipped automatically if a region is missing?

Some applications prioritize availability: when cache is unavailable, they want to run business logic without caching. That is an architectural decision, **not the default behavior of `SimpleCacheResolver` when a name is missing**.

Spring's `CompositeCacheManager` has a `fallbackToNoOpCache` option to supply a non-storing cache when child managers cannot resolve a name. When enabled intentionally, a call can continue instead of failing on a missing cache; in return, it can **silently lose all caching benefits** for that region. Restrict fallback to justified environments/needs and monitor actual behavior.

Avoid using `NoOpCache` as a default workaround for production typos: it can mask disabled caching for long periods.

### 8.2. Should CacheErrorHandler be used to ignore it?

`CacheErrorHandler` handles errors arising during **cache get/put/evict/clear operations**. **Failing to resolve a cache name** through the resolver is not equivalent to a `Cache.get` error on a valid `Cache` object.

Therefore, do not treat adding a "swallow exceptions" `CacheErrorHandler` as a reliable fix for a missing cache name. Fix cache registration/resolution or apply a controlled fallback policy instead.

### 8.3. When cache names are a security and resource concern

In multi-tenancy, creating dynamic cache regions from untrusted values can grow region counts without bound or expose partitioning logic. Prefer a **fixed cache name** with a tenantId-prefixed key where suitable, or enforce allow-lists/quotas for genuinely needed dynamic regions. Do not use dynamic cache names as a substitute for authorization checks.

## 9. Common errors and their real causes

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Error “Cannot find cache named ...” when calling service | Strict manager lacks requested region | Cross-check annotation/cacheNames/manager |
| No error yet cache does not hit as expected | Dynamic manager created a mistyped region | Check getCacheNames, metrics, and canonical names |
| `getCache("products") != null` yet still times out | Provider/backend unavailable | Health, connection, credentials, timeouts |
| `cache.get(key) == null` | Entry miss or expired | Check key, TTL, eviction; do not assume missing region |
| CacheManager bean exists yet injection is unclear | Multiple managers / wrong bean picked | Qualifiers, `@Primary`, `cacheManager` on annotation |
| No error seen despite wrong annotation | Method not invoked via proxy; or dynamic manager | Integration test calling method via bean |
| Fails only in production | Profile/CacheManager/provider differs from dev | Compare configs across environments |
| `@CacheEvict` fails to delete the right entry | Key or cache name mismatch between read and write paths | Compare both annotations and key generator |
| Cache region appears yet memory grows endlessly | Unbounded dynamic cache name creation | Switch to allow-list, monitor cardinality |
| Changed cache name yet old data still occupies space | Old region/key lacks cleanup lifecycle | TTL policy, migration, or appropriate clear |

## 10. Systematic diagnosis in production

1. **Confirm from the root exception.** Separate name resolution errors, backend errors, and cache misses. Record the exception class and message fragment with the cache name (without logging sensitive data).
2. **Trace the owner of the cache name.** Locate the exact cache annotation and service cache policy, including `@CacheConfig`.
3. **Verify the actual manager.** Check the active bean/config/profile/provider; do not infer from a `cacheManager` variable name in code.
4. **Inspect regions known to the manager.** `getCacheNames()` is useful, though in dynamic mode it is not the list of all future valid names.
5. **Check region creation policy.** Does the manager create lazily or strictly? Does the provider require pre-configuring regions?
6. **Create only valid cache regions.** When adding a new cache, design keys, TTL, memory/eviction, serializer, and cross-instance consistency.
7. **Test via Spring-managed methods.** Invoke through the bean so cache advice runs, verifying hits/misses and responses to wrong names.
8. **Monitor after changes.** Track cache region count, hits/misses/puts, backend errors, latency, and memory shifts.
9. **Distinguish region checks from data checks.** A valid cache region does not mean the right entry exists for every key, nor does it prove cached data is fresh.

### Recommended logs/metrics

- `CacheManager` type and configured cache names at startup.
- Count of cache name resolution failures, separated from cache backend failures.
- Cache region count per instance or provider, when collectible.
- Cache hit ratio, source latency on cache miss, capacity/evictions.
- Cache region configuration change events and region creation errors during deploys.

Do not log keys containing tokens, session IDs, personal identifiers, or system secrets without proper sanitization.

## 11. Special scenarios to watch out for

### 11.1. One annotation using multiple cacheNames

~~~java
@Cacheable(
    cacheNames = {"products", "productBackup"},
    key = "#p0"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

This is illustrative code. If the resolver cannot find **one name** in the list and configuration does not allow creation, resolution may fail for **the entire cache operation**, rather than skipping the missing name and using the remaining one by default. Register all cache names required by the operation.

### 11.2. Applications with multiple cache managers

`cacheManager="someManager"` on an annotation can switch to another infrastructure backend. If a region is valid in manager A yet absent in manager B, the fault is usually **selecting the wrong manager**, not that the cache region was deleted from the system.

With a custom `CacheResolver`, cache names can be mapped dynamically from runtime parameters; in that case test the resolution policy of the resolver itself.

### 11.3. Cache invalidation after deploy or config changes

Config changes may stop permitting a region to be allocated, even if a previous release used it. During multi-instance rollouts, region names and key formats must be compatible or have a migration plan. Do not recreate an old region automatically just to "silence errors" if its data/serializer is no longer compatible.

### 11.4. Application uses @EnableCaching yet method is not intercepted

In default proxy mode, calling `this.findProduct(id)` inside the bean itself bypasses cache advice. This can create the **illusion that an annotation with a wrong cache name still works**, because no cache resolution actually happened. Tests should invoke methods from outside the bean via `ApplicationContext`, not just directly on an instance created with `new`.

## 12. Pre-release checklist

- [ ] Maintain a canonical list of cache names, aligned across modules.
- [ ] Cache names in `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@CacheConfig` all match.
- [ ] Know which `CacheManager` handles each annotation.
- [ ] Know whether that manager allows dynamic cache creation or accepts only registered names.
- [ ] If strict, all required names are allocated/declared and tested.
- [ ] If dynamic, a policy prevents typos or bounds region cardinality.
- [ ] Do not confuse a missing region with an entry miss or a backend outage.
- [ ] Tested through Spring proxies for both valid and invalid names.
- [ ] Config plan covers dev/test/prod; do not assume all profiles share the same provider.
- [ ] Metrics and alerts cover unexpected cache regions and name resolution failures.
- [ ] Appropriate TTL, memory, serialization, and invalidation policies exist for new cache regions.
- [ ] Do not use fallback/no-op to hide critical cache name errors.

## 13. Self-check questions

**1.** Does `@Cacheable(cacheNames="products")` automatically guarantee the `products` region is created at application startup?  
**Answer:** No. That depends on `CacheManager` and initialization/lazy allocation policies.

**2.** Does `CacheManager.getCache("products")` returning `null` mean `products[42]` is a miss?  
**Answer:** No. Failing to resolve a cache region differs from a valid region not having an entry for a key.

**3.** How does `new ConcurrentMapCacheManager()` typically behave with an annotation naming an undeclared cache?  
**Answer:** It can create the new cache region on demand.

**4.** How does `new ConcurrentMapCacheManager("products")` behave when an annotation uses `"prodcuts"`?  
**Answer:** The strict manager returns `null`; the default resolver may throw a cache resolution error when the method is called.

**5.** Why does an empty `getCacheNames()` not always prove a cache name is invalid?  
**Answer:** With a dynamic manager, the cache region may not be allocated yet and is created only when requested.

**6.** Can `CacheErrorHandler` reliably fix a missing cache name error?  
**Answer:** No. A name resolution error differs from an operation error on a valid `Cache` object.

**7.** Why must `CompositeCacheManager` with no-op fallback be used carefully?  
**Answer:** It lets business logic continue while silently disabling caching, hiding configuration bugs and increasing load.

**8.** A service uses `cacheManager="redisManager"`, yet the cache name exists only in `localManager`. What must be checked?  
**Answer:** The manager selected on the annotation/class and the list of regions managed by that respective manager.

**9.** When should cache names be checked in a startup validator?  
**Answer:** When there is a required region list and strict policy; beware the validator itself might allocate caches if the manager is in dynamic mode.

**10.** If `getCache("products")` returns a Cache object yet `get(key)` times out, what kind of error must be handled?  
**Answer:** A backend/provider/network error, not a cache name error by default.

## References

- Spring Framework 6.2 — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/store-configuration.html
- Spring Framework 6.2 — ConcurrentMapCacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework 6.2 — CacheManager API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Spring Data Redis — RedisCacheManagerBuilder: https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheManager.RedisCacheManagerBuilder.html
