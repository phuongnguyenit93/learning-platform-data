# SimpleCacheManager with Predeclared ConcurrentMapCache in Spring Framework

## 1. Problem and Objectives

In a Spring application, you want to use an **in-memory cache inside the JVM itself**, while managing only a fixed set of cache regions defined at startup, such as `catalog` for products and `reports` for reports. Other regions should not be accidentally created just because code misspells a name.

The right pair for this simple requirement is:

- `SimpleCacheManager`: a `CacheManager` implementation that manages a **pre-supplied set of `Cache` objects**.
- `ConcurrentMapCache`: a `Cache` implementation backed by a `ConcurrentMap` structure, defaulting to `ConcurrentHashMap`, to store entries in process memory.

Key point of this lesson: **"predeclaring caches" does not mean preloading data into the cache**. You create **cache regions** with fixed names at initialization, whereas **entries by key** are added on `@Cacheable` misses, when calling `Cache.put`, or through an active preloading mechanism implemented by the application.

After this lesson, you will be able to:

1. Create a `SimpleCacheManager` bean and supply `ConcurrentMapCache` instances via `setCaches(...)`.
2. Understand the `afterPropertiesSet/initializeCaches` initialization lifecycle and why you must not forget it when using the manager outside a Spring container.
3. Use `@EnableCaching`, `@Cacheable`, and `@CacheEvict` with fixed-name caches.
4. Distinguish an **undeclared cache** from a **key without an entry** in an existing region.
5. Understand the differences from `ConcurrentMapCacheManager`, null policy, single-JVM scope, concurrency, and TTL/size-limit constraints.
6. Run a standalone Java 17+ example without needing Redis, a database, or a web server.

## 2. Components and Class Relationships

```text
               Spring ApplicationContext
                         |
                @EnableCaching / AOP
                         |
               CacheInterceptor
                         |
                   CacheManager
                 (SimpleCacheManager)
                         |
             +-----------+------------+
             |                        |
      ConcurrentMapCache       ConcurrentMapCache
        name="catalog"          name="reports"
             |                        |
       ConcurrentMap              ConcurrentMap
         key -> value              key -> value
```

Some concepts to distinguish:

| Component | Role | Does NOT mean |
| --- | --- | --- |
| `Cache` | API to access a cache region: `get`, `put`, `evict`, `clear` | Defining the entire Spring configuration itself |
| `CacheManager` | Looks up a cache region by name via `getCache(name)`, lists names via `getCacheNames()` | Automatically caching all method results |
| `SimpleCacheManager` | Manages a collection of `Cache` instances supplied via `setCaches` | Auto-generating new regions for any unknown name |
| `ConcurrentMapCache` | Local cache backed by a concurrent map | Redis, multi-node cache, or database |
| `@EnableCaching` | Enables cache annotation processing infrastructure in the relevant context | Pre-creating caches or preloading data |
| `@Cacheable` | Reads cache, skips method on hit; calls method and stores on miss | Guaranteeing caching works if the call bypasses the Spring proxy |

When a `@Cacheable(cacheNames="catalog")` method is invoked through a Spring proxy, the cache interceptor asks `CacheManager` for the region named `catalog`. `SimpleCacheManager` returns the exact registered `ConcurrentMapCache` instance; cache logic then looks up by key. If the key is absent, the body executes and the result may be stored in that region.

## 3. Configuring SimpleCacheManager with Predeclared Caches

Minimal Java configuration in a Spring application:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(
            new ConcurrentMapCache("catalog"),
            new ConcurrentMapCache("reports")
        ));
        return manager;
    }
}
```

This is an **illustrative configuration snippet**; it requires Spring imports and `java.util.List`. Section 5 provides a **complete runnable project**.

Meaning of each step:

1. `new ConcurrentMapCache("catalog")` creates a cache instance named `catalog`, initially with no entries.
2. `new ConcurrentMapCache("reports")` creates an independent region named `reports`.
3. `manager.setCaches(List.of(...))` supplies the exact cache instances for the manager to manage. Note that it is not `setCacheNames`; this method takes **cache objects**, not a list of string names.
4. The Spring container creates the `CacheManager` bean, runs bean initialization callbacks, and registers the regions in `SimpleCacheManager`'s lookup map.
5. `@EnableCaching` allows `@Cacheable`/`@CacheEvict` to use this manager when calls pass through the proxy.

This configuration does not create a separate Spring bean for each `ConcurrentMapCache`; they are instances supplied directly to the manager. You can also declare `Cache` instances as separate beans for injection/configuration, then pass them to `SimpleCacheManager`. Be careful not to accidentally register **two managers** with an unclear default or two caches with the same name.

### 3.1. Initialization Lifecycle Is a Mandatory Detail

`SimpleCacheManager` extends `AbstractCacheManager` and implements `afterPropertiesSet()` via the `InitializingBean` interface. When managed as a normal Spring bean, **Spring automatically invokes the lifecycle callback** after properties are configured; `afterPropertiesSet()` triggers `initializeCaches()` to build the name -> cache instance mapping.

Therefore, inside the `@Bean` method above, **there is no need to call `afterPropertiesSet()` manually**.

Conversely, when instantiating manually outside a Spring container:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(new ConcurrentMapCache("catalog")));
manager.initializeCaches();  // Mandatory initialization if managing the manager manually.
Cache cache = manager.getCache("catalog");
```

This is an **illustrative code snippet**, requiring imports for `SimpleCacheManager`, `ConcurrentMapCache`, `Cache`, and `List`. When used directly, call `initializeCaches()` **after supplying the cache instances**; otherwise, `getCache("catalog")` may not know about that cache region yet. Do not modify the cache list arbitrarily after the application starts serving traffic; treat the registry as a stable startup configuration.

### 3.2. Fixed Cache Names: Unknown Differs from Cache Miss

Example after proper initialization:

```java
CacheManager manager = context.getBean(CacheManager.class);
Cache catalog = manager.getCache("catalog");  // Has instance.
Cache unknown = manager.getCache("unknown");  // null.
Cache.ValueWrapper absent = catalog.get("SKU-404"); // null if no entry yet.
```

This snippet is an illustrative fragment, assuming `context` is a valid Spring context.

- `manager.getCache("unknown") == null`: **no cache region with that name** exists in `SimpleCacheManager`.
- `manager.getCache("catalog") != null` yet `catalog.get("SKU-404") == null`: **the cache region exists**, there is just **no entry for that key yet**.
- If the cache supports null, a non-null wrapper with `wrapper.get() == null` means **an entry holding a cached null value**.

These are three distinct situations. When an annotation references a nonexistent cache name, the standard cache resolver cannot select a valid region and the annotated method call may fail at runtime. Do not rely on the manager auto-creating a new region — `SimpleCacheManager` does not operate dynamically like some other cache managers.

## 4. Structure of a Runnable Java 17+ Example

The example predeclares **two regions**: `catalog` and `reports`. The service reads data via `@Cacheable` to observe cache hits; an update operation evicts only one `catalog` key; a report-refresh operation clears the entire `reports` region. Both regions operate independently.

Create project:

```text
simple-cache-manager-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/SimpleCacheDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'simple-cache-manager-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.SimpleCacheDemo'
}
```

The program does not use `@SpringBootApplication` or an HTTP server. It uses Spring Context directly and Spring Cache provided by the starter; the BOM keeps Spring dependency versions aligned. In a real project, choose a Spring Boot/Spring Framework version actively supported by your team and compatible with your system's JDK.

## 5. Complete Java Source Code

File `src/main/java/demo/cache/SimpleCacheDemo.java`:

```java
package demo.cache;

import java.util.List;
import java.util.Objects;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SimpleCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean
        CacheManager cacheManager() {
            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(
                    new ConcurrentMapCache("catalog"),
                    new ConcurrentMapCache("reports")
            ));
            return manager;
            // Spring automatically invokes the manager init callback when managing the bean.
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final ConcurrentHashMap<String, Integer> versions =
                new ConcurrentHashMap<>();
        private final AtomicInteger catalogLoads = new AtomicInteger();
        private final AtomicInteger reportLoads = new AtomicInteger();
        private final AtomicInteger reportVersion = new AtomicInteger();

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String item(String sku) {
            int version = versions.getOrDefault(sku, 0);
            int n = catalogLoads.incrementAndGet();
            return sku + "-v" + version + "-load" + n;
        }

        @Cacheable(cacheNames = "reports", key = "#p0")
        public String report(String region) {
            int version = reportVersion.get();
            int n = reportLoads.incrementAndGet();
            return region + "-report-v" + version + "-load" + n;
        }

        @CacheEvict(cacheNames = "catalog", key = "#p0")
        public void changeItem(String sku) {
            versions.merge(sku, 1, Integer::sum);
        }

        @CacheEvict(cacheNames = "reports", allEntries = true)
        public void rebuildReports() {
            reportVersion.incrementAndGet();
        }

        public String counts() {
            return "catalog:" + catalogLoads.get()
                    + ",reports:" + reportLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            CatalogService service = context.getBean(CatalogService.class);

            // Sort only so output does not depend on set iteration order.
            System.out.println("cacheNames="
                    + new TreeSet<>(manager.getCacheNames()));
            System.out.println("unknownCache="
                    + (manager.getCache("unknown") == null));

            System.out.println("catalog-first=" + service.item("SKU-1"));
            System.out.println("catalog-hit=" + service.item("SKU-1"));
            System.out.println("reports-first=" + service.report("VN"));
            System.out.println("reports-hit=" + service.report("VN"));

            service.changeItem("SKU-1");
            System.out.println("catalog-after-evict="
                    + service.item("SKU-1"));
            System.out.println("reports-still-hit="
                    + service.report("VN"));

            service.rebuildReports();
            System.out.println("reports-after-clear="
                    + service.report("VN"));
            System.out.println("catalog-still-hit="
                    + service.item("SKU-1"));

            System.out.println("loads=" + service.counts());

            Cache catalog = Objects.requireNonNull(
                    manager.getCache("catalog"));
            System.out.println("cacheType="
                    + catalog.getClass().getSimpleName());
            System.out.println("sameInstance="
                    + (catalog == manager.getCache("catalog")));
        }
    }
}
```

Run in the `simple-cache-manager-demo` directory using JDK 17+ and a Java 17-compatible Gradle:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, you can use `./gradlew run --quiet` or on Windows `gradlew.bat run --quiet`.

**Expected output from the `System.out.println` lines**, excluding build logs:

```text
cacheNames=[catalog, reports]
unknownCache=true
catalog-first=SKU-1-v0-load1
catalog-hit=SKU-1-v0-load1
reports-first=VN-report-v0-load1
reports-hit=VN-report-v0-load1
catalog-after-evict=SKU-1-v1-load2
reports-still-hit=VN-report-v0-load1
reports-after-clear=VN-report-v1-load2
catalog-still-hit=SKU-1-v1-load2
loads=catalog:2,reports:2
cacheType=ConcurrentMapCache
sameInstance=true
```

### 5.1. Explaining Each Stage

1. `cacheNames=[catalog, reports]`: `SimpleCacheManager` has exactly the two registered regions. The example uses `TreeSet` for deterministic display order.
2. `unknownCache=true`: the name `unknown` was not declared, so `getCache("unknown") == null`; the manager does not auto-create it.
3. First `item("SKU-1")`: the `catalog` region exists, but the key has not been stored yet, so the method runs and generates `SKU-1-v0-load1`. The second call with the same key hits without incrementing the counter.
4. First `report("VN")` behaves similarly for the `reports` region; the second call hits.
5. `changeItem("SKU-1")` increments the item's version and uses `@CacheEvict(key="#p0")` to remove **one entry** in `catalog`. Reading the item again produces `SKU-1-v1-load2`. The report entry remains a hit.
6. `rebuildReports()` increments the report version and uses `allEntries=true` to clear **all entries in the specified `reports` region**, without touching `catalog`.
7. Both counters equal 2: there were two executions of the item body and two of the report body, despite more calls. `cacheType` and `sameInstance` prove the manager returns the initialized `ConcurrentMapCache` instance rather than creating a new cache on every lookup.

**Why do the annotations work?** `@EnableCaching` is placed on the configuration inside the proper Spring context. The service is created as a bean and calls in `main` are invoked on `context.getBean(CatalogService.class)`, meaning they pass through the Spring proxy. If you call `new CatalogService().item(...)` or a method inside the service calls `this.item(...)`, caching annotations may not run in the default proxy mode.

This example uses single-JVM memory and is single-threaded in the demonstration; do not use it to claim everything is atomic under concurrent requests.

## 6. Comparing SimpleCacheManager and ConcurrentMapCacheManager

The two class names are easy to confuse:

| Aspect | `SimpleCacheManager` + `ConcurrentMapCache` | `ConcurrentMapCacheManager` |
| --- | --- | --- |
| Initialization | Manually instantiate `Cache` objects and pass via `setCaches(...)` | Manager creates `ConcurrentMapCache` instances by name itself |
| Cache names | Derived from `Cache.getName()` of registered caches | Can be dynamic by default; can be configured with fixed names |
| Unregistered name | Returns null, does not auto-create a new cache | In dynamic mode, can create a cache upon `getCache(name)` |
| Cache types | Accepts a collection of `Cache` implementations | Dedicated to creating `ConcurrentMapCache` |
| Null configuration | Set on each `ConcurrentMapCache` or specific implementation | `setAllowNullValues(...)` at manager level |
| Reference/copy configuration | Depends on the cache instances you supply | Has the manager's own options |
| Suitable scenario | Want exact control over cache instances and names | Want convenient configuration of JDK concurrent-map caches |

Short example of choosing `ConcurrentMapCacheManager` instead of `SimpleCacheManager`:

```java
// Fixed-name mode:
CacheManager manager = new ConcurrentMapCacheManager("catalog", "reports");

// Dynamic mode if using the no-name constructor:
CacheManager dynamic = new ConcurrentMapCacheManager();
```

The two snippets above are **illustrative code fragments**, requiring imports. Dynamic mode can create a cache region whenever code requests an unseen name; that can be handy during experimentation, yet can also mask misspelled cache names. With `SimpleCacheManager`, cache instances are predetermined and names do not expand dynamically on lookup.

Do not mistakenly think `ConcurrentMapCacheManager("catalog","reports")` is always dynamic: the constructor taking predefined names puts it in fixed-name mode. Both options are still just simple in-memory caches without default TTL or size-based eviction.

## 7. Customizing Individual Caches and Null Policy

### 7.1. ConcurrentMapCache Supports Business Nulls by Default

Native `ConcurrentHashMap` **cannot hold null values**. However, Spring's `ConcurrentMapCache` can convert **business null** into an internal marker when null values are allowed. The simple constructor `new ConcurrentMapCache("catalog")` allows nulls by default.

To **disallow null** on a specific region:

```java
SimpleCacheManager manager = new SimpleCacheManager();
manager.setCaches(List.of(
    new ConcurrentMapCache("catalog", false),
    new ConcurrentMapCache("reports", true)
));
```

This is an **illustrative configuration fragment**, not runnable on its own because it needs imports and manager initialization lifecycle. The `ConcurrentMapCache(String name, boolean allowNullValues)` constructor sets the policy per region; there is no `SimpleCacheManager.setAllowNullValues(...)` applying globally like on `ConcurrentMapCacheManager`.

To avoid caching a method's null result even when the backend allows it:

```java
@Cacheable(
    cacheNames = "catalog",
    key = "#p0",
    unless = "#result == null"
)
public Product find(String sku) {
    return repository.findProduct(sku);
}
```

This is an illustrative method assuming real `Product` and `repository` types. `unless` is evaluated after the method returns on a cache miss and can veto putting a null result.

If you still want to cache nulls (negative caching), define a TTL/eviction strategy for when data appears later. Plain `ConcurrentMapCache` does not automatically expire entries by TTL.

### 7.2. Using a Custom Map When Needed

In addition to the one- or two-argument constructors, Spring also supports:

```java
ConcurrentMap<Object, Object> nativeMap = new ConcurrentHashMap<>();
ConcurrentMapCache catalog =
        new ConcurrentMapCache("catalog", nativeMap, true);
```

This is an illustrative code snippet with `java.util.concurrent.ConcurrentMap` and `ConcurrentHashMap`. The boolean parameter controls whether business null conversion is allowed. This lets you control the backing map or intentionally share that specific map instance, though it **does not** turn it into Redis or automatically add TTL/capacity limits.

If inspecting `cache.getNativeCache()`, remember that null may be represented by an internal marker; do not interpret business meaning directly from raw native values. Read through `Cache.get(key)`/`ValueWrapper` to respect Spring Cache semantics.

### 7.3. Store by Reference and Mutable Objects

In a simple setup, the cache keeps **object references** by default. If the cache returns an `ArrayList` or mutable DTO, multiple calls can receive the same object and mutate it; the thread safety of `ConcurrentHashMap` **does not** make value objects themselves thread-safe.

Prefer immutable records/DTOs, defensive copies where appropriate, and clearly designed value lifecycles. If you need store-by-value (copies/serialization) or memory management, look into an appropriate cache provider or deeper configuration rather than assuming `SimpleCacheManager` handles it automatically.

## 8. Managing Eviction and Consistency

`ConcurrentMapCache` has no default eviction based on TTL, LRU, or maximum entry count. **Predeclaring cache names** does not mean **memory cannot grow unbounded**: a region can keep accumulating keys throughout the JVM's lifetime.

In the section 5 example:

- `@CacheEvict(cacheNames="catalog", key="#p0")` removes the entry for the corresponding key.
- `@CacheEvict(cacheNames="reports", allEntries=true)` requests clearing the entire `reports` region.
- The two cache regions are independent. Evicting `catalog` does not implicitly evict `reports` even if they hold interdependent data.

In a real application, identify all regions that depend on the same data source. If updating a product also changes regional reports, evicting only `catalog` is **insufficient**; you must also evict `reports` or the relevant keys according to proper logic.

Some system limitations:

1. **Single JVM:** the cache lives in the process heap. Each pod/JVM has separate instances; an update or eviction in one process does not automatically propagate to other processes.
2. **Restarts:** entries are lost; this is an ephemeral cache, not a persistence layer.
3. **Concurrency:** concurrent-map guarantees map operations under its thread-safety contract, but the sequence cache miss -> compute -> put is not atomic by default; two requests can run the body simultaneously during a concurrent miss. You can consider `@Cacheable(sync=true)` when the provider supports it and constraints are met, though it is still not a distributed lock.
4. **Transactions:** `@CacheEvict` and a DB transaction do not form a combined distributed transaction by default. For critical data, verify commit timing, eviction, and races with in-flight loads.
5. **Performance:** unbounded large caches increase heap usage, GC cost, and OOM risk; production apps typically need Caffeine or Redis with appropriate eviction/TTL/metrics.

Choosing `SimpleCacheManager` only decides **how `Cache` instances are managed**; it does not automatically add expiration, observability, or distributed features.

## 9. Common Issues and Diagnostics

| Symptom | Typical Cause | How to Resolve |
| --- | --- | --- |
| `getCache("catalog") == null` despite `setCaches` | Instantiated manager manually and forgot `initializeCaches()` | Outside Spring container, call init after `setCaches`; as a bean, let Spring handle it |
| `getCache("reports") == null` | Misspelled name or instance omitted from `setCaches` | Check `Cache.getName()` and the collection |
| Annotation references an unfamiliar cache name | `SimpleCacheManager` does not auto-create new caches | Add the cache instance to config or fix the annotation name |
| `@Cacheable` does not cache | Missing `@EnableCaching` on the right context, bean created with `new`, or self-invocation | Check proxy, `ApplicationContext`, and service bean |
| First call still executes method | Cache miss is normal behavior | Call with the same key a second time and check the counter |
| Evicted a key but entry still hits | Evict and read do not use the same cache name or key | Compare exact SpEL keys and regions |
| Cleared `reports` but `catalog` still hits | Two independent caches | If data is interdependent, evict all related regions |
| Cached null causes stale non-updated results | Provider allows negative caching | Consider `unless`, TTL, or eviction when source data changes |
| Cache runs out of RAM after long uptime | `ConcurrentMapCache` has no default TTL/max-size | Use a cache provider with capacity limits and metrics |
| Multi-node system has inconsistent caches | Heap cache isolated per JVM | Use distributed caching or proper cross-node invalidation events |
| Cached value mutates unexpectedly | Store by reference with mutable objects | Use immutable DTOs or defensive copies |
| Duplicate cache names initialized | Multiple instances sharing one name make registry ambiguous | Ensure unique names and test the cache list |

When debugging, start with 4 questions: **Is Spring calling through the proxy?** -> **Does the manager return the right cache name instance?** -> **Is the key right?** -> **Was the entry evicted/invalidated?** With `SimpleCacheManager`, the list of cache names can be verified right at startup via `getCacheNames()`.

## 10. Testing Strategy and Deployment Checklist

### 10.1. Tests You Should Have

1. **Registry:** after startup, `getCacheNames()` contains exactly `catalog` and `reports`; `getCache("unknown")==null`.
2. **Cache instance:** calling `getCache("catalog")` twice returns the same instance when the registry has not changed.
3. **Cache miss/hit:** calling `@Cacheable` twice with the same key executes the body only once.
4. **Different key:** calling `item("SKU-2")` when only `SKU-1` is cached must run the method for the new key.
5. **Evict by key:** modify `SKU-1`, evict, and reading `SKU-1` again must recompute.
6. **No cross-region eviction:** evicting `catalog` does not lose hits in `reports`.
7. **Clear entire region:** `allEntries=true` on `reports` causes all `reports` keys to miss without affecting `catalog`.
8. **Lifecycle:** test manual manager creation outside Spring, call `initializeCaches()` then look up a cache; avoid relying on callbacks without a container.
9. **Null policy:** verify behavior when the method returns null, `allowNullValues`, and `unless`.
10. **Multithreading:** test concurrent hits/misses, potential double-loads, and behavior under interleaved eviction.
11. **Multi-node:** if deploying multiple instances, test each node to detect independent caches lacking cross-node invalidation.
12. **Memory management:** monitor key counts, heap/GC, and invalidation frequency; if high, switch providers.

### 10.2. Pre-Production Checklist

- Are the number of cache regions small enough and clearly defined?
- Are cache names in annotations, SpEL keys, and manager config consistent?
- Is there a single clear default `CacheManager`, or are managers explicitly specified on annotations when multiple exist?
- Do all beans with caching annotations go through Spring proxies?
- Have you decided whether to cache nulls, when to evict/clear, and what TTL is needed?
- Is heap sufficient for peak entry counts, or is a provider with capacity-based eviction required?
- Can data become stale across multiple nodes, and what are the exact consistency requirements?
- Have hits/misses, exceptions, concurrency, source updates, and restarts been tested?

Do not treat `SimpleCacheManager` as a persistence layer or use local in-memory caches as the authoritative source of truth. It is a great tool for examples, tests, and some small applications, yet must be re-evaluated as data volume, node count, or reliability requirements grow.

## 11. Self-Check Questions

**Q1.** How does `manager.setCaches(List.of(new ConcurrentMapCache("catalog")))` differ from `manager.getCache("catalog")`?

**Answer:** `setCaches` supplies the set of cache instances for the manager to manage **at initialization**; `getCache` looks up an already-registered instance by name.

**Q2.** Why don't you have to call `manager.afterPropertiesSet()` manually inside a `@Bean` method?

**Answer:** The Spring container manages the bean lifecycle, including `InitializingBean` callbacks. If using the manager manually outside the container, you must initialize the cache registry with `initializeCaches()` after `setCaches`.

**Q3.** Does `getCache("unknown") == null` mean `catalog` is experiencing a cache miss?

**Answer:** No. It means **the `unknown` region does not exist**. A cache miss is when the cache region exists and has no mapping for a key.

**Q4.** Do two cache instances in the same JVM automatically share entries?

**Answer:** No. `new ConcurrentMapCache("catalog")` and `new ConcurrentMapCache("reports")` have separate native stores by default.

**Q5.** Why can a predeclared cache still cause out-of-memory errors?

**Answer:** Fixing the number of regions does not limit the number of entries. `ConcurrentMapCache` does not provide TTL or max-size on its own.

**Q6.** Does `SimpleCacheManager` automatically generate a new cache when an annotation misspells a name?

**Answer:** No. This manager is supplied with a fixed collection of cache instances; an unregistered name does not automatically become a new region.

**Q7.** Are a Spring proxy and `@Cacheable` enough to synchronize results between two pods?

**Answer:** No. `ConcurrentMapCache` runs inside each JVM's memory; architectural invalidation/distributed caching solutions are needed when multiple instances serve data.

## 12. Key Takeaways

- `SimpleCacheManager` manages **predeclared `Cache` objects** via `setCaches(Collection<? extends Cache>)`.
- `ConcurrentMapCache` provides in-memory caching backed by a concurrent map per region; **declaring a region != prefilling entries**.
- When created by Spring as a bean, the lifecycle automatically invokes `afterPropertiesSet/initializeCaches`; when created outside the container, initialize manually.
- `getCache(name)` only looks up registered regions; nonexistent names return null. Within an existing cache, a key-level cache miss is a different state.
- `@EnableCaching` + Spring proxies activate `@Cacheable` and `@CacheEvict`; cache region names and keys must match.
- Suitable for learning, testing, and simple apps; does not inherently provide TTL, size-based eviction, persistence, or multi-JVM sharing.

### Official References

- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — SimpleCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html)
- [Spring Framework — AbstractCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/support/AbstractCacheManager.html)
- [Spring Framework — ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring Framework — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)