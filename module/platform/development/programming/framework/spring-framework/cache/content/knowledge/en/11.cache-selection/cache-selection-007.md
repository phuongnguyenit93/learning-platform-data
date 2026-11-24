# CompositeCacheManager and Lookup Order in Spring Framework Cache

## 1. Problem statement: an application needs multiple CacheManagers

A Spring application may use different cache regions for catalog data, reports, and shared data. For instance, the `catalog` region might live on one provider; the `reports` region might live on another provider. If all annotations use the same `CacheManager`, how caches are allocated must be clearly defined.

`CompositeCacheManager` in the `org.springframework.cache.support` package solves the problem of **finding a `Cache` object by name from a list of `CacheManager`s**. It iterates through the delegate list in the exact configured order and picks the **first non-null `Cache`**.

Conceptual example:

```text
CacheInterceptor / CacheManager.getCache("reports")
                      |
                      v
          CompositeCacheManager
                      |
            [1] catalogManager
                   getCache("reports") = null
                      |
            [2] reportManager
                   getCache("reports") = Cache("reports")
                      |
                      v
              Select Cache("reports")
```

Core condition: **a manager that does not manage the requested cache name must return `null`**, so the composite can proceed to the next delegate. Once an earlier manager returns a non-null `Cache`, the search **stops immediately**; the composite does not query the remaining managers.

This lesson covers region selection semantics, priority order, static/dynamic cache names, `NoOpCache` fallback, usage with annotations, and testing common pitfalls.

## 2. Role of CompositeCacheManager

Components to distinguish:

| Component | Responsibility |
| --- | --- |
| `CacheManager` | Looks up a cache region via `getCache(String name)`; lists known regions via `getCacheNames()` |
| `Cache` | Region holding `key → value` entries; supports `get`, `put`, `evict`, `clear`, etc. |
| `CompositeCacheManager` | Iterates multiple `CacheManager`s in order until one returns a non-null `Cache` |
| `CacheResolver` | Selects the set of Caches for a cache operation; the default resolver usually relies on cache names and one manager |
| `@Cacheable`, `@CachePut`, `@CacheEvict` | Specifies read, write, or evict operations; uses the Cache resolved in the step above |

The cache lookup method can be described by this algorithm:

```java
// Pseudocode illustrating the contract, not verbatim Spring source.
Cache getCache(String name) {
    for (CacheManager manager : delegatesInOrder) {
        Cache cache = manager.getCache(name);
        if (cache != null) {
            return cache;
        }
    }
    return null;
}
```

**Selection order is by cache region name, not by whether an entry key exists.** The composite does not read each key from manager 1 and then try manager 2 if the key is missing. It selects a `Cache` region first; key-level hits/misses happen **inside that region**.

Consequences:

- Manager 1 has cache `shared` yet `shared/K` has no entry yet: the composite still picks manager 1's `shared` cache.
- Manager 2 also has cache `shared` and already stores `shared/K`: that entry is **never tried** through the composite mechanism.
- `put` or `evict` through the selected cache does not automatically replicate the operation to all delegates.

Therefore `CompositeCacheManager` is **not an L1/L2 two-tier caching system**, not write-through between two providers, and does not automatically synchronize data. If you need L1/L2 with population from L2 back into L1, implement a `Cache` or multi-tier provider with its own read-through, invalidation, and consistency contracts.

## 3. Lookup order when cache names overlap or differ

Suppose three managers are configured:

| Order | Manager | Regions it manages |
| --- | --- | --- |
| 1 | `catalogManager` | `catalog`, `shared` |
| 2 | `reportManager` | `reports`, `shared` |
| 3 | `otherManager` | `audit` |

When calling `composite.getCache(name)`:

| Requested name | Manager 1 | Manager 2 | Manager 3 | Result |
| --- | --- | --- | --- | --- |
| `catalog` | Present | Not queried | Not queried | Cache from manager 1 |
| `reports` | Returns null | Present | Not queried | Cache from manager 2 |
| `audit` | Returns null | Returns null | Present | Cache from manager 3 |
| `shared` | Present | Not queried | Not queried | Cache from manager 1 |
| `missing` | Returns null | Returns null | Returns null | Composite returns null if fallback is disabled |

**If two managers both manage `shared`, the manager ordered earlier has absolute priority for that name.** Changing the order can cause data to be read from a different provider, even when the annotation code remains unchanged.

`getCacheNames()` on the composite aggregates known cache names from its delegates. The name list does not prove which cache handles a particular request when names overlap; inspect `getCache(name)` and the configuration order. When caches are created dynamically, returned names can also change over time.

## 4. Why does a “dynamic” manager configuration easily break ordering?

Many CacheManagers have a **create-region-on-demand** mode when asked for a non-existent name. For example, Spring's `ConcurrentMapCacheManager`:

```java
// Dynamic: creates a new cache for any undeclared name.
CacheManager dynamic = new ConcurrentMapCacheManager();

// Static: manages only catalog and shared.
CacheManager staticCatalog =
        new ConcurrentMapCacheManager("catalog", "shared");
```

Configuring with the constructor taking a fixed list of names puts `ConcurrentMapCacheManager` into **static mode**. In static mode, `getCache("reports")` returns null if `reports` is not in the declared list, allowing the composite to try the next manager.

If a dynamic manager is placed first:

```java
var first = new ConcurrentMapCacheManager(); // dynamic
var second = new ConcurrentMapCacheManager("reports"); // static
var composite = new CompositeCacheManager(first, second);

// first.getCache("reports") creates Cache("reports") itself.
// Because it is non-null, composite never reaches second.
Cache selected = composite.getCache("reports");
```

The snippet above illustrates how resolution works. Even though the second manager has `reports` pre-configured, the call selects the newly created region in the first manager. The code may run without errors while data goes to the wrong backend.

To avoid this:

1. Explicitly list cache names owned by earlier managers and configure strict known-names-only mode when supported by the provider.
2. Put managers with explicit name scopes earlier; if you genuinely need a catch-all manager supporting any name, place it last intentionally.
3. Check the `getCache(name)` behavior of **each provider**, not only `getCacheNames()`; an empty name list does not mean `getCache` always returns null.
4. Add tests for listed names, overlapping names, and non-existent names to catch the first manager "swallowing" all requests.

In systems using Caffeine, Redis, JCache, or custom adapters, dynamic cache creation and handling of unknown names depend on each implementation/configuration. Do not assume every provider shares the same constructor or properties as `ConcurrentMapCacheManager`.

## 5. Configuring CompositeCacheManager in Java Config

When an application has two cache backends/groups, you can construct the composite with delegates in **priority order**:

```java
@Bean
CacheManager cacheManager() {
    var catalog = new ConcurrentMapCacheManager("catalog", "shared");
    var reports = new ConcurrentMapCacheManager("reports", "shared");

    var composite = new CompositeCacheManager(catalog, reports);
    composite.setFallbackToNoOpCache(false);
    return composite;
}
```

This is an **illustrative configuration snippet**; import `CacheManager`, `ConcurrentMapCacheManager`, `CompositeCacheManager`, `@Bean`, and place the method in a Spring configuration class.

This configuration guarantees:

- Asking for `catalog` → selects the first `catalog` manager.
- Asking for `reports` → first manager returns null, second manager is tried.
- Asking for `shared` → selects the first manager because both manage that name.
- Asking for `unknown` → returns null because both are in static mode and fallback is disabled.

**You can change the order** by changing constructor argument order or using `setCacheManagers(Collection<CacheManager>)`. Treat that order as part of the configuration that directly affects data.

`CompositeCacheManager` also supports `afterPropertiesSet()` via `InitializingBean` to finalize fallback configuration. When it is a Spring bean, the container invokes the lifecycle callback. If instantiating with `new` outside Spring and wanting `NoOp` fallback, consider calling `afterPropertiesSet()` appropriately.

### 5.1. Avoiding multiple CacheManager beans causing ambiguous default selection

If you register multiple Spring beans of type `CacheManager` and then use `@Cacheable` without configuring a default manager, ambiguity over which bean to use can occur. The complete example in the next section registers **one `CacheManager` bean, which is the composite**, while its delegates live inside a separate configuration object.

In real applications, you can also select the default bean with `CachingConfigurer`, `@Primary`, or specify `cacheManager = "..."` on methods/`@CacheConfig` when appropriate. Keep the resolution path consistent so annotations do not go directly to another manager instead of through the composite.

## 6. Runnable Java 17 example: seeing ordered lookup clearly

The example below uses Spring Framework 6.2.x and `ConcurrentMapCacheManager` in **static mode**. There are two delegates:

- `first` manages `catalog` and `shared`.
- `second` manages `reports` and `shared`.

The application uses a single `CompositeCacheManager`, along with a `Delegates` bean holding references to the two managers to illustrate overlapping region names without registering extra `CacheManager` beans competing with the composite.

**Directory structure:**

```text
composite-cache-demo/
├── pom.xml
└── src/main/java/CompositeCacheDemo.java
```

**Contents of `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composite-cache-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Contents of `src/main/java/CompositeCacheDemo.java`:**

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.CompositeCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CompositeCacheDemo {

    // The two delegates are configuration data, not CacheManager beans.
    public record Delegates(
            ConcurrentMapCacheManager first,
            ConcurrentMapCacheManager second) {}

    @Bean
    Delegates delegates() {
        return new Delegates(
                new ConcurrentMapCacheManager("catalog", "shared"),
                new ConcurrentMapCacheManager("reports", "shared"));
    }

    @Bean
    CacheManager cacheManager(Delegates delegates) {
        var composite = new CompositeCacheManager(
                delegates.first(), delegates.second());
        composite.setFallbackToNoOpCache(false);
        return composite;
    }

    @Bean
    DataService dataService() {
        return new DataService();
    }

    public static class DataService {
        private final AtomicInteger catalogLoads = new AtomicInteger();
        private final AtomicInteger reportLoads = new AtomicInteger();

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String catalog(String sku) {
            catalogLoads.incrementAndGet();
            return "Product-" + sku;
        }

        @Cacheable(cacheNames = "reports", key = "#p0")
        public String report(String reportId) {
            reportLoads.incrementAndGet();
            return "Report-" + reportId;
        }

        public int catalogLoads() {
            return catalogLoads.get();
        }

        public int reportLoads() {
            return reportLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                CompositeCacheDemo.class)) {

            CacheManager manager = context.getBean(CacheManager.class);
            Delegates delegates = context.getBean(Delegates.class);
            DataService service = context.getBean(DataService.class);

            System.out.println("catalog exists: "
                    + (manager.getCache("catalog") != null));
            System.out.println("reports exists: "
                    + (manager.getCache("reports") != null));
            System.out.println("unknown exists: "
                    + (manager.getCache("unknown") != null));

            Cache firstShared = delegates.first().getCache("shared");
            Cache secondShared = delegates.second().getCache("shared");
            if (firstShared == null || secondShared == null) {
                throw new IllegalStateException("Missing shared cache");
            }

            secondShared.put("K", "SECOND");
            Cache selected = manager.getCache("shared");
            if (selected == null) {
                throw new IllegalStateException("Composite missing shared");
            }
            System.out.println("shared with empty first: "
                    + (selected.get("K") == null ? "MISS" : "HIT"));

            firstShared.put("K", "FIRST");
            System.out.println("shared chosen: "
                    + selected.get("K", String.class));
            System.out.println("second still: "
                    + secondShared.get("K", String.class));

            System.out.println("catalog 1: " + service.catalog("P1"));
            System.out.println("catalog 2: " + service.catalog("P1"));
            System.out.println("catalog loads: " + service.catalogLoads());

            System.out.println("reports 1: " + service.report("R1"));
            System.out.println("reports 2: " + service.report("R1"));
            System.out.println("report loads: " + service.reportLoads());
        }
    }
}
```

**Run from the directory containing `pom.xml`** (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=CompositeCacheDemo
```

**Lines printed by `main`** (excluding environment-dependent Maven/Spring logs):

```text
catalog exists: true
reports exists: true
unknown exists: false
shared with empty first: MISS
shared chosen: FIRST
second still: SECOND
catalog 1: Product-P1
catalog 2: Product-P1
catalog loads: 1
reports 1: Report-R1
reports 2: Report-R1
report loads: 1
```

Interpreting the results:

1. Because `catalog` exists only in the first delegate, `getCache("catalog")` is non-null.
2. `reports` is absent in the first delegate so it is found in the second delegate; `getCache("reports")` is non-null.
3. Neither delegate manages `unknown`, so the composite returns null.
4. `second/shared/K` already holds `"SECOND"`, while `first/shared/K` is absent. The composite still picks the first delegate's `shared` region, so reading key `K` reports `MISS`: it **does not fall back on a key miss**.
5. Putting `"FIRST"` into the first delegate's `shared` cache makes the composite read `"FIRST"`, while the second delegate still holds `"SECOND"`. This proves two same-named regions are not merged.
6. `service.catalog("P1")` and `service.report("R1")` each increment their counter only once across two calls, showing `@Cacheable` used the caches resolved by the composite.

The demo uses no database or distributed cache and makes no claims about TTL, transactions, or multi-instance synchronization. Cache-annotated calls from `main` go through Spring beans, avoiding self-invocation bypasses.

## 7. NoOpCacheManager fallback: when no manager knows the name

`CompositeCacheManager` has a `fallbackToNoOpCache` property (disabled by default). When enabled, it appends `NoOpCacheManager` to the **end of the delegate list** during initialization. That manager returns a `Cache` object for any requested name, without storing data.

Configuration:

```java
@Bean
CacheManager cacheManager() {
    var real = new ConcurrentMapCacheManager("catalog");
    var composite = new CompositeCacheManager(real);
    composite.setFallbackToNoOpCache(true);
    return composite;
}
```

This is an alternative illustrative snippet; do not copy it into the demo class in Section 6 since that would create two `cacheManager()` bean methods.

With this configuration:

- `composite.getCache("catalog")` gets the real cache from the first delegate.
- `composite.getCache("unknown")` is also non-null, but it is a **NoOpCache**.
- `@Cacheable(cacheNames="unknown")` still executes the method every time because a NoOp cache never retains entries across calls.
- No cache-not-found exception occurs, so a typo in `cacheNames` can be masked and the application silently loses caching benefits.

Enabling fallback is appropriate when certain regions may intentionally skip storage in a specific environment; if you want to catch cache misconfigurations early, **disable fallback** and test region names. Never use this fallback as a backup copy for Redis/Caffeine: `NoOpCache` skips storage, it is not a real cache.

### When is the fallback activated?

`CompositeCacheManager` implements `InitializingBean`. When it is a Spring bean, `afterPropertiesSet()` is called after configuration and appends `NoOpCacheManager` at the end if `fallbackToNoOpCache=true`. If instantiating the composite manually outside Spring without calling the lifecycle callback, fallback configuration may not yet apply. Do not toggle fallback repeatedly after bean initialization assuming the delegate list rebuilds dynamically over time.

## 8. Selecting managers in Spring Cache annotations

An `@Cacheable(cacheNames="reports", key="#p0")` operation requests a cache named `reports` from the selected manager (typically via a `CacheResolver`). **The composite only takes effect if the operation actually uses the composite itself**.

Manager selection can be configured at multiple levels:

| Level | Example | Meaning |
| --- | --- | --- |
| Default bean of caching infrastructure | One explicitly configured `CacheManager` | Operations without their own manager use the default |
| Service class | `@CacheConfig(cacheManager = "compositeCacheManager")` | Operations in the class inherit the manager name |
| Method | `@Cacheable(cacheManager = "compositeCacheManager")` | Operation specifies its own manager |
| Resolver | `cacheResolver = "customCacheResolver"` | Cache selection mechanism executed by the resolver, which may bypass the composite |

If the application has multiple `CacheManager` beans, pick a clear default via Spring configuration or specify the exact name on annotations. If a method specifies a different manager, it can bypass the composite altogether and use that backend's cache directly.

`@CacheConfig(cacheNames = "reports")` or `@Cacheable(cacheNames="reports")` specifies only the **name** of the region to resolve. The region name itself does not describe provider, storage location, or delegate order; those live in manager configuration.

Do not combine `cacheManager` and `cacheResolver` simultaneously on the same cache operation. With a custom resolver, verify which cache list the resolver uses, whether it respects expected order, and how it behaves when no cache is found.

## 9. Difference between region selection and a cache miss

This is a common confusion when trying to build "L1 + L2":

```text
CompositeCacheManager contract:
  Cache name "shared"
       -> does manager 1 have region "shared" ?
          Yes -> pick that region immediately
          No -> ask manager 2

2-tier cache contract that many apps want:
  Read key K in L1
       -> L1 miss: read key K in L2
       -> L2 hit: may write back to L1
       -> L2 miss: call source
```

The two flows operate on **different units**:

- The composite resolves **region names** once for an operation (and may be called again on other requests).
- Multi-tier caching resolves **individual keys**, requiring cross-tier consistency contracts, copy/serialization/TTL strategies, and invalidation.

If you put local `ConcurrentMapCacheManager` first and a Redis manager second while both return caches for the same name `products`, the composite will always use local, even on a local miss. Redis data is not used as a key-level fallback. Local invalidations also do not propagate automatically to Redis or other nodes.

To build true two-tier caching, choose a library/provider offering an explicit multi-tier `Cache` implementation or build a custom `Cache` implementation coordinating L1/L2 and test race conditions, write-through, stale data, TTL, and invalidation. Merely reordering `CompositeCacheManager` is not enough.

## 10. Common mistakes and how to verify

1. **First manager creates every cache name.** A dynamic manager returns a non-null `Cache` for any name, causing later managers almost never to be queried. Check static mode or move the catch-all manager last.
2. **Misunderstanding priority order.** When two managers both have `shared`, the earlier manager wins; there is no round-robin or load balancing.
3. **Treating a key miss as a signal to try the next manager.** Composite does not perform key-level lookup, only name-level lookup.
4. **Enabling `fallbackToNoOpCache` and thinking there is a real backup cache.** Unknown names are handled by NoOp and not stored; region name typos become hard to spot.
5. **Registering multiple CacheManager beans without picking a default.** Annotations may use the wrong bean or fail with ambiguity; define the default manager explicitly.
6. **Assuming same cache names across delegates share data.** Regions in different managers can be completely independent; writes/evictions via the composite affect only the selected region.
7. **Believing `getCacheNames()` shows entry hit order.** The name list only reports known cache names, not which keys exist or which manager wins on overlapping names.
8. **Failing to manage configuration differences across environments.** Provider A creates caches dynamically in dev while fixing names in production; region selection behavior may differ.
9. **Assuming built-in transactions or distributed invalidation.** Composite does not participate in atomic commits with the database and does not sync caches across JVMs.
10. **Writing tests only for unique region names.** Test overlapping regions, unknown names, and a key existing only in a later manager.

### Pre-deployment checklist

| Scenario to test | Expected behavior |
| --- | --- |
| Manager 1 has cache `catalog` | Composite returns the exact Cache from manager 1 |
| Manager 1 lacks `reports`, manager 2 has it | Composite returns Cache from manager 2 |
| Both have `shared` | Composite selects manager 1 |
| Manager 1 has `shared` but key `K` misses; manager 2 has `K` | Does not try manager 2; returns miss from selected region |
| Neither manager has `unknown`, fallback off | `getCache("unknown") == null` |
| Neither manager has `unknown`, fallback on and bean initialized | Gets `NoOpCache`, does not cache results |
| Manager 1 is dynamic | Manager 1 may accept every cache name, blocking delegation |
| Service annotation uses a manager other than the composite | Composite lookup rules are not applied |

For operational observability, record the selected region name and handling backend, hit/miss ratios **within each real cache**, source access cost, and backend errors. Re-test whenever changing the cache name list or delegate order.

## 11. Design rules to avoid picking the wrong backend

A reliable configuration can be expressed with four questions:

1. **Which manager owns each region name?** Document the region name → provider/manager mapping table explicitly.
2. **On an unknown name, does that manager return null or auto-create a cache?** This is the technical condition for the composite to move on.
3. **Are any names duplicated across managers?** If so, the earlier manager is picked; document that as an intentional decision.
4. **When nobody manages a name, should the system fail or temporarily skip caching?** This decision governs `fallbackToNoOpCache`.

Use `CompositeCacheManager` only to **coordinate finding cache regions by name**. When key-level data reuse across tiers is needed, use a dedicated multi-tier cache implementation and consistency contract.

## Official references

- Spring Framework — `CompositeCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Framework — `ConcurrentMapCacheManager` Javadoc (static/dynamic): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `CacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html
