# Custom CacheResolver by Argument or Context

## 1. Objective and problem statement

Spring Cache uses annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict` to declare cache operations around method invocations. The important question is not only **which key to use**, but also **which cache region to use**. In a simple application, one `CacheManager` and a fixed `cacheNames` are usually enough. However, with multiple tenants, geographic regions, data types, processing sources, or multiple cache managers, selecting the cache region may have to happen **at runtime**, based on parameters or execution context.

`CacheResolver` is Spring Cache's extension point to solve that problem. It receives information about the operation and the current invocation, and returns one or more `Cache` objects for the interceptor to use.

After this lesson, you will:

- Distinguish `CacheResolver`, `CacheManager`, `KeyGenerator`, cache name, and cache key.
- Write a resolver that selects a cache based on a method parameter, such as `region`.
- Write a resolver that selects a cache based on a trusted context, such as the current tenant.
- Configure `@Cacheable(cacheResolver = "...")` and use it consistently for `@CacheEvict`.
- Understand risks around tenant isolation, misconfiguration, memory, transactions, proxies, and concurrency.
- Run a Java 17 example that makes hits/misses, routing, and invalidation observable.

## 2. What is CacheResolver? Where does it sit in the flow?

Three concepts are often confused:

| Concept | Question answered | Example |
| --- | --- | --- |
| `CacheManager` | How do we retrieve a named cache region? | `manager.getCache("prices-north")` |
| `CacheResolver` | For **this** invocation, which cache region should be operated on? | `region = "north"` → cache `prices-north` |
| `KeyGenerator` or `key` attribute | Inside the selected cache region, which entry corresponds to the call? | `sku = "P1"` → key `"P1"` |

Think of two levels of addressing:

~~~text
CacheResolver decides which cache
           |
           v
      prices-north             prices-south
       |         |             |         |
       v         v             v         v
      "P1"      "P2"          "P1"      "P2"
       |                         |
       v                         v
      100                       200
    (north/P1)                (south/P1)
~~~

Key `"P1"` can appear **in both caches** without collision because they are two separate storage spaces. A resolver selects cache `prices-north` for north-region requests; south-region requests go to `prices-south`. If sharing a single cache, you must encode region/tenant into the key to avoid data collisions.

### General flow with @Cacheable

~~~text
Caller -> Spring proxy / CacheInterceptor
                  |
                  v
      Read @Cacheable + invocation context
                  |
                  v
       CacheResolver.resolveCaches(context)
                  |
                  v
       Collection<? extends Cache>
                  |
                  v
        Build key per key configuration
                  |
                  v
        Look up entry on selected cache
             /                \
           HIT                MISS
            |                   |
            v                   v
      Return result       Invoke original method
                                |
                                v
                       May write result into
                       the selected cache
~~~

This is a conceptual diagram of how cache hit/miss works; the detailed path may differ with `condition`, `unless`, multiple caches, async/reactive return types, or provider-specific behavior. `CacheResolver` does **not** decide the method's return value itself, does not run database queries itself, and does not define TTL itself.

## 3. The CacheResolver interface and runtime information

Spring interface:

~~~java
package org.springframework.cache.interceptor;

public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
~~~

The snippet above describes the API signature (with `import` statements omitted), **not a standalone Java file**. The resolver must return a collection of actual `org.springframework.cache.Cache` objects.

`CacheOperationInvocationContext<?>` provides useful inputs:

| API | Meaning | Use case |
| --- | --- | --- |
| `context.getArgs()` | Array of arguments for the current call | Select cache by `region`, `tenantId`, document type |
| `context.getMethod()` | The invoked `Method` | Share one resolver across multiple operations |
| `context.getTarget()` | Target bean executing the call | Distinguish service groups if genuinely needed |
| `context.getOperation()` | Cache operation metadata | Read declared `cacheNames` or metadata attributes |

Note: `context.getArgs()` returns arguments **before the method runs**. You cannot select a cache based on the final return value of the current invocation. When logic depends on the result, you need a different cache operation or business flow design.

The resolver is invoked within the scope of a cache operation, so it should be **fast and deterministic**, without business side effects and without expensive DB queries just to decide the cache. If a valid cache cannot be found, handle it explicitly (e.g., throw a meaningful exception) rather than silently returning a wrong shared cache. Do not return an empty collection or put `null` into the collection to simulate "no caching".

## 4. When to use a custom resolver?

### 4.1. Selecting by parameter

Example:

~~~java
public int getPrice(String region, String sku)
~~~

- `region="north"` → `prices-north`.
- `region="south"` → `prices-south`.
- Same SKU `"P1"` yet different prices in the two regions.
- When updating price in `north`, only the entry in `prices-north` is evicted.

The resolver reads `context.getArgs()[0]` to obtain the region. Each entry's key can simply be `sku`, i.e., `#p1`.

### 4.2. Selecting by context

A multi-tenant API may not want to repeat `tenantId` in every method:

~~~java
public String profile(String userId)
~~~

The current tenant can come from an authenticated security principal, request scope, or a tenant context established before entering the service. The resolver selects:

- Tenant `a` → cache `profiles-a`.
- Tenant `b` → cache `profiles-b`.

The business method can receive the same `userId="u1"`, yet each tenant's cache stays separate. This is a **data partitioning and isolation** decision, not merely a performance optimization.

### 4.3. Selecting among CacheManagers

When one operation needs Caffeine and another needs Redis, a resolver can hold references to both `CacheManager`s and choose the manager by data type or actual request. Use the `cacheManager` attribute directly if the choice is **fixed per method**. Use `CacheResolver` when the choice depends on **each invocation**.

### When a custom resolver is unnecessary

If all calls use the `"products"` cache, the simplest and clearest way is:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.load(sku);
}
~~~

This is an illustrative snippet, not standalone because `Product` and `repository` belong to the application. Do not add a custom resolver just to return the same `products` cache on every call: it complicates the code without adding value.

## 5. Attaching a resolver to an annotation

Given a Spring bean named `regionResolver`:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
public int getPrice(String region, String sku) {
    return database.load(region, sku);
}
~~~

`cacheResolver` is a **bean name**, not a class name. Spring looks up the matching declared bean, for example:

~~~java
@Bean("regionResolver")
public CacheResolver regionResolver(CacheManager manager) {
    return context -> {
        String region = (String) context.getArgs()[0];
        String cacheName = "prices-" + region;
        Cache cache = manager.getCache(cacheName);
        if (cache == null) {
            throw new IllegalArgumentException(
                    "Unsupported cache name: " + cacheName);
        }
        return List.of(cache);
    };
}
~~~

The two Java snippets above are illustrative, not standalone runnable programs. String concatenation `"prices-" + region` works well for explanation, but **do not pass untrusted input directly into cache names in production**. The complete demo in Section 7 uses a `switch` allowlist to select only permitted caches.

### Is cacheNames required?

Not required if the custom resolver already supplies the caches. For example:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
~~~

is a valid configuration. When returning a collection of `Cache` objects at runtime on its own, a resolver does not necessarily depend on the annotation's `cacheNames`. If you want to keep cache name as logical metadata, you can declare it and handle it intentionally in the resolver. Do not assume a custom resolver automatically honors `cacheNames`: **the implementation itself determines that**.

### Can cacheManager and cacheResolver be placed on the same operation?

No. `cacheManager` and `cacheResolver` are mutually exclusive alternatives for choosing the cache resolution mechanism; declaring **both on the same cache operation** is an invalid configuration. Similarly, `key` and `keyGenerator` cannot be used together on a single operation.

**Incorrect** example:

~~~java
@Cacheable(
    cacheNames = "prices",
    cacheManager = "redisManager",
    cacheResolver = "regionResolver"
)
public int getPrice(String region, String sku) {
    return 0;
}
~~~

The snippet above is an intentionally invalid configuration example, not meant to be run. If `regionResolver` already knows which manager to use, declare only `cacheResolver`.

### Global/class-level configuration

A default `CacheResolver` can be applied via `CachingConfigurer` or at the class level with `@CacheConfig(cacheResolver = "regionResolver")`. Configuration directly on a method takes precedence over class level, and class configuration can override the global default. Use broad scopes only when all methods within that scope genuinely share the same routing contract.

## 6. Designing consistency across read, write, and delete

A system may read via `@Cacheable`, write back via `@CachePut`, or delete via `@CacheEvict`. All three operations must agree on **the selected cache** and **the key**.

Example:

~~~java
@Cacheable(cacheResolver = "regionResolver", key = "#p1")
public int getPrice(String region, String sku) {
    return repository.findPrice(region, sku);
}

@CacheEvict(cacheResolver = "regionResolver", key = "#p1")
public void changePrice(String region, String sku, int newPrice) {
    repository.updatePrice(region, sku, newPrice);
}
~~~

This is an illustrative snippet; `repository` is not yet defined. What matters:

1. For the same region, the resolver must return the same cache for both getter and updater.
2. For the same SKU, both key expressions produce key `sku`; the new price parameter must not participate in the key.
3. After the updater finishes successfully, the old entry is evicted; only the next read loads the new data.
4. If the getter uses a per-tenant cache while the updater evicts in the default cache, the tenant entry remains and can become stale.

When selecting a cache from security/request context, the same trusted context must exist during update and evict. Never assume every method runs on a thread holding the same context, especially in `@Async`, queue listeners, or reactive flows.

## 7. Runnable demo: selecting a cache by argument and context

The following complete example uses **Java 17**, **Spring Framework 6.2.19**, and Maven. No Spring Boot or Redis is needed; the provider is an in-JVM `ConcurrentMapCacheManager`.

The demo tests both cases:

- Method `price(region, sku)` selects a cache by **region argument**.
- Method `profile(userId)` selects a cache by **tenant context**.
- `changePrice(region, sku, newValue)` uses the same resolver and key as the getter to evict only the affected region.

### 7.1. Directory structure

~~~text
dynamic-cache-resolution/
├── pom.xml
└── src/main/java/demo/CacheRoutingDemo.java
~~~

### 7.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>dynamic-cache-resolution</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File src/main/java/demo/CacheRoutingDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheRoutingDemo {

    // Simulates context in a synchronous example only.
    // Production: tenant must come from an authenticated identity.
    public static final class TenantContext {
        private static final ThreadLocal<String> CURRENT =
                new ThreadLocal<>();

        static String requireTenant() {
            String tenant = CURRENT.get();
            if (tenant == null) {
                throw new IllegalStateException("Tenant is missing");
            }
            return tenant;
        }

        static void runAs(String tenant, Runnable action) {
            String previous = CURRENT.get();
            CURRENT.set(tenant);
            try {
                action.run();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            // Only allow the declared caches.
            return new ConcurrentMapCacheManager(
                    "prices-north", "prices-south",
                    "profiles-a", "profiles-b");
        }

        @Bean("regionResolver")
        public CacheResolver regionResolver(CacheManager manager) {
            return context -> {
                Object[] args = context.getArgs();
                if (args.length == 0 ||
                        !(args[0] instanceof String region)) {
                    throw new IllegalArgumentException(
                            "Region argument is required");
                }

                String cacheName = switch (region) {
                    case "north" -> "prices-north";
                    case "south" -> "prices-south";
                    default -> throw new IllegalArgumentException(
                            "Unknown region: " + region);
                };

                return List.of(requiredCache(manager, cacheName));
            };
        }

        @Bean("tenantResolver")
        public CacheResolver tenantResolver(CacheManager manager) {
            return context -> {
                String tenant = TenantContext.requireTenant();
                String cacheName = switch (tenant) {
                    case "a" -> "profiles-a";
                    case "b" -> "profiles-b";
                    default -> throw new IllegalArgumentException(
                            "Unknown tenant: " + tenant);
                };

                return List.of(requiredCache(manager, cacheName));
            };
        }

        @Bean
        public DataService dataService() {
            return new DataService();
        }
    }

    private static Cache requiredCache(
            CacheManager manager, String name) {
        Cache cache = manager.getCache(name);
        if (cache == null) {
            throw new IllegalStateException(
                    "Cache not configured: " + name);
        }
        return cache;
    }

    public static class DataService {
        // Simulated DB; "region|sku" key is independent of the cache key.
        private final Map<String, Integer> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger priceReads = new AtomicInteger();
        private final AtomicInteger profileReads = new AtomicInteger();

        public DataService() {
            database.put("north|P1", 100);
            database.put("south|P1", 200);
        }

        @Cacheable(cacheResolver = "regionResolver", key = "#p1")
        public int price(String region, String sku) {
            Integer value = database.get(region + "|" + sku);
            if (value == null) {
                throw new IllegalArgumentException("Unknown product");
            }

            int number = priceReads.incrementAndGet();
            System.out.println(
                    "DB price " + region + "/" + sku + " #" + number);
            return value;
        }

        @CacheEvict(cacheResolver = "regionResolver", key = "#p1")
        public void changePrice(
                String region, String sku, int newPrice) {
            database.put(region + "|" + sku, newPrice);
            System.out.println(
                    "WRITE " + region + "/" + sku + "=" + newPrice);
        }

        @Cacheable(cacheResolver = "tenantResolver", key = "#p0")
        public String profile(String userId) {
            String tenant = TenantContext.requireTenant();
            int number = profileReads.incrementAndGet();
            System.out.println(
                    "DB profile " + tenant + "/" + userId
                    + " #" + number);
            return tenant + ":" + userId;
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {
            DataService service = context.getBean(DataService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            // Route by region parameter.
            System.out.println("north1=" + service.price("north", "P1"));
            System.out.println("north2=" + service.price("north", "P1"));
            System.out.println("south1=" + service.price("south", "P1"));

            Cache north = requiredCache(manager, "prices-north");
            Cache south = requiredCache(manager, "prices-south");
            System.out.println("north cached? "
                    + (north.get("P1") != null));
            System.out.println("south cached? "
                    + (south.get("P1") != null));

            service.changePrice("north", "P1", 150);
            System.out.println("north after evict? "
                    + (north.get("P1") != null));
            System.out.println("south after evict? "
                    + (south.get("P1") != null));
            System.out.println("north3=" + service.price("north", "P1"));
            System.out.println("south2=" + service.price("south", "P1"));

            // Route by current tenant context.
            TenantContext.runAs("a", () -> {
                System.out.println("a1=" + service.profile("u1"));
                System.out.println("a2=" + service.profile("u1"));
            });
            TenantContext.runAs("b", () ->
                    System.out.println(
                            "b1=" + service.profile("u1")));
            TenantContext.runAs("a", () ->
                    System.out.println(
                            "a3=" + service.profile("u1")));
        }
    }
}
~~~

### 7.4. Running the program

Requires JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheRoutingDemo
~~~

Stdout printed by the **program**, excluding Maven/environment dependency messages:

~~~text
DB price north/P1 #1
north1=100
north2=100
DB price south/P1 #2
south1=200
north cached? true
south cached? true
WRITE north/P1=150
north after evict? false
south after evict? true
DB price north/P1 #3
north3=150
south2=200
DB profile a/u1 #1
a1=a:u1
a2=a:u1
DB profile b/u1 #2
b1=b:u1
a3=a:u1
~~~

### 7.5. Reading the trace and explanation

**Routing by argument:**

- `north1`: resolver gets `region=north`, returns `prices-north`. Entry `P1` is absent → method executes → prints `DB price... #1` and stores 100.
- `north2`: still chooses `prices-north`, same key `P1` → hit, no extra `DB price` line.
- `south1`: resolver picks **another cache** `prices-south`. Even though the key is still `P1`, this is a separate miss → method executes, loads 200.
- After `changePrice("north","P1",150)`: the same resolver picks `prices-north`; `@CacheEvict` deletes only entry `P1` in that region. Cache `prices-south` still holds 200.
- `north3` misses so the method loads 150; `south2` hits so there is no new DB read.

**Routing by context:**

- With tenant context `a`, `profile("u1")` picks `profiles-a`. First call prints `DB profile a/u1 #1`; second call hits.
- With tenant context `b`, the **same key** `u1` picks `profiles-b`, so it must compute for the first time for tenant b (counter rises to 2).
- Back to tenant a, `a3` hits on `profiles-a`, printing no extra DB line.
- `TenantContext.runAs` restores the previous context or calls `remove()` in `finally` so data never leaks across sequential calls on a reused thread.

### 7.6. Why must the demo use ApplicationContext?

`@EnableCaching` activates annotation processing; calls to `DataService` through the bean obtained from `ApplicationContext` are handled by the Spring proxy/interceptor. If you call `new DataService().price(...)` outside Spring, annotations do not run automatically. In default proxy mode, self-invocation such as `this.price(...)` also bypasses caching advice. In practice, structure service boundaries so cached calls pass through a Spring-managed proxy.

The demo is in-memory on a **single JVM**, and does not verify multi-instance consistency or a real web application's security context.

## 8. Designing a context-based CacheResolver in production

The demo uses `ThreadLocal` to present the concept. When building a real system, the "current tenant" must come from a **trusted** source.

### 8.1. Sources of context

| Source | Points to watch |
| --- | --- |
| Validated parameter | Passed explicitly from the boundary into the service; never trust arbitrary input strings directly |
| Authenticated security principal | Prefer the tenant belonging to a verified identity/authorization |
| Request-scoped object | Only present during matching HTTP requests; absent in batch/worker threads |
| ThreadLocal | Must be set/cleared or restored properly; error-prone with thread pools/async |
| Reactor context / async context | Requires an appropriate context propagation mechanism; do not assume ThreadLocal follows the flow |

**Never use an unauthenticated `X-Tenant` header as the basis for partitioning sensitive data.** A resolver choosing the wrong cache can cause cross-tenant data leakage. Cache routing does not replace authorization at the business layer.

### 8.2. Fail closed when context is missing

Suppose a method requires a tenant. If the context is empty, a dangerous approach is:

~~~java
String tenant = currentTenantOrNull();
String name = tenant == null ? "profiles-shared" : "profiles-" + tenant;
~~~

The snippet above illustrates an **anti-pattern** (with a hypothetical `currentTenantOrNull` function) and must not be used as a solution. Falling back to a shared cache can cause the same key `u1` across multiple tenants to collide. Instead, throw a meaningful error or explicitly define an authorized, isolated system context.

### 8.3. Avoiding unbounded cache allocation from input

Some `CacheManager`s can auto-create a cache with a new name when `getCache(name)` is called. If cache names are concatenated from uncontrolled inputs, requests generating thousands of distinct names can inflate memory, metadata, or backend resource counts. Prevention:

1. Normalize and validate region/tenant from an authenticated source.
2. If the choice set is finite, use a `switch`/allowlist as in the demo.
3. If the tenant count is large/dynamic, consider **one shared cache with a safe tenant-prefixed key** instead of creating a dedicated cache per tenant; the choice depends on backend, quotas, and isolation requirements.
4. Monitor cache name/key cardinality, memory, eviction, hit ratio, and management overhead.

Physical partitioning by tenant and key namespacing by tenant are two distinct designs; choose based on security, operations, and scalability.

### 8.4. Consistency with invalidation

If selecting by tenant, every update path should evict/put in the right tenant. For the same logical entity, ensure:

~~~text
Read request for tenant a:
  resolver -> profiles-a -> key "u1" -> hit/miss

Update request for tenant a:
  resolver -> profiles-a -> key "u1" -> evict/put

Read request for tenant b:
  resolver -> profiles-b -> key "u1"
  -> Does NOT affect tenant a's data
~~~

If a resolver depends on context yet a background job has no context, do not "guess" the tenant. Pass the tenant into the job and establish a trusted context, or use an explicit tenant-aware invalidation API at the system boundary.

### 8.5. Transactions and eviction timing

`@CacheEvict` by default runs after the method succeeds, **without automatically guaranteeing eviction after database commit** across all AOP/transaction combinations. If the cache is evicted before commit, another reader may miss and reload stale data. Design an after-commit invalidation mechanism if consistency requires it. The resolver only selects caches; it does not resolve commit ordering or race conditions.

## 9. Selecting caches across multiple CacheManagers

Suppose a service has `localCacheManager` and `remoteCacheManager`. A resolver can route short-lived data to local and shared data to remote:

~~~java
@Bean("tierResolver")
public CacheResolver tierResolver(
        CacheManager localCacheManager,
        CacheManager remoteCacheManager) {
    return context -> {
        String kind = (String) context.getArgs()[0];
        CacheManager chosen = switch (kind) {
            case "local" -> localCacheManager;
            case "shared" -> remoteCacheManager;
            default -> throw new IllegalArgumentException(
                    "Unknown storage tier: " + kind);
        };
        Cache cache = chosen.getCache("lookup");
        if (cache == null) {
            throw new IllegalStateException("Cache lookup unavailable");
        }
        return List.of(cache);
    };
}
~~~

This is a snippet integrated into a Spring configuration that has **two clearly defined cache manager beans**; to inject accurately in an application with multiple managers, use matching bean names/`@Qualifier` (or specify explicit parameter qualifiers). It is not a standalone Java file.

Note: even with the same name `"lookup"`, caches from local and remote managers have **different semantics** (TTL, serialization, distribution, eviction). The resolver must ensure data types and keys are compatible with each backend.

If there is a clear requirement for a specific method, configuration is simpler:

~~~java
@Cacheable(cacheNames = "lookup", cacheManager = "remoteCacheManager")
public String find(String id) {
    return service.load(id);
}
~~~

This snippet is illustrative only. Use `cacheManager` when fixed per method; use `cacheResolver` when the selection **varies per invocation**.

## 10. Returning one or multiple caches?

`CacheResolver.resolveCaches` returns `Collection<? extends Cache>`, because an operation can involve multiple caches. However, do not abuse this to "cache indiscriminately".

- One cache: usually easiest to reason about hit/miss, TTL, and invalidation.
- Multiple caches: requires understanding lookup order and writes/evictions across all caches, especially when one already holds an entry while another does not.
- `@Cacheable(sync = true)` has limitations, including that synchronized operations do not handle multiple caches simultaneously.
- Some async or distributed providers have different lookup details; do not treat multiple caches as an atomic transaction guarantee or a consistent replication mechanism.

A resolver can choose caches from multiple managers, yet reading/writing across those caches is not an atomic transaction by default.

## 11. Comparing cache region selection tools

| Need | What to use | Reason |
| --- | --- | --- |
| All calls use one fixed cache | `cacheNames = "products"` | Clear, minimal code |
| Method A uses Redis, method B uses Caffeine, fixed | `cacheManager` on each method | No runtime routing needed |
| Cache by `region` parameter within the same method | Custom `CacheResolver` | Select per invocation |
| Cache by tenant from security context | Custom `CacheResolver` or namespaced key structure | Depends on isolation needs |
| Change only how entry keys are built | `key` / `KeyGenerator` | No need to change cache |
| Want different TTL per region | Configure respective provider/cache | Resolver is not a TTL policy engine |
| Cache only when condition holds | `condition` | Bypass logic, not cache selection |

Example: `key = "#p1"` changes the **entry key**, whereas `cacheResolver = "regionResolver"` changes the **cache object**. Both options can be combined on the same annotation because they solve two different problems.

## 12. Common pitfalls and debugging

### Pitfall 1 — confusing cacheName and key

Constructing key `"north:P1"` does not automatically make Spring choose cache `prices-north`. Without a custom resolver, the cache may still be `prices`. Conversely, choosing `prices-north` while forgetting the right key can also cause entry collisions between methods sharing that cache.

**How to verify:** safely log the cache name returned by the resolver and the actual key used, without logging personal data/secrets.

### Pitfall 2 — @Cacheable and @CacheEvict using different resolvers/keys

The getter selects `profiles-a`, while the updater evicts `profiles`; the result is stale data. You must define the same routing strategy, including update paths triggered by jobs, event handlers, and admin APIs.

### Pitfall 3 — mismatched bean name

Annotation `@Cacheable(cacheResolver = "regionResolver")` requires an exact bean named `regionResolver`. The class name can differ. If the bean does not exist or has the wrong type, caching will not work as expected or initialization/invocation will throw an error.

### Pitfall 4 — returning null or an empty collection

Do not use an empty result as "cache disabled". If you want to skip caching conditionally, use `condition`; if a cache cannot be selected, report a clear configuration or context error.

### Pitfall 5 — reading tenant from an unstable context

An HTTP request runs for tenant a, while an `@Async` task runs on another thread without the tenant context. The resolver may lack context or select the wrong cache. Propagate context properly; do not assume ThreadLocal follows thread pools/reactive flows.

### Pitfall 6 — selecting cache from untrusted data

If a client supplies its own tenant ID without verifying access rights, the resolver only creates a "different cache name" rather than preventing unauthorized access. Security depends on authentication, authorization, and checking ownership of the underlying data.

### Pitfall 7 — self-invocation bypassing the interceptor

If a method in a class calls `this.otherCachedMethod()`, default proxy mode usually does not process annotations on that internal call. The resolver is not called either. Design proper method boundaries or use appropriate proxies/aspects.

### Pitfall 8 — assuming in-memory cache syncs across instances

`ConcurrentMapCacheManager` in the demo only shares caches across beans in the same JVM. Different instances have separate caches; you need a shared backend or invalidation protocol if multi-node consistency is required.

### Diagnostic checklist

1. Is `@EnableCaching` present and does the call go through a Spring-managed proxy?
2. Does the annotation use the right `cacheResolver` bean? Is there a conflict with `cacheManager`?
3. Are `context.getArgs()` and the current context accurate and authenticated/validated?
4. Does the resolver return the right cache name, right manager, a non-empty collection, and no nulls?
5. Do key expressions match the parameters of both getter and updater?
6. Does `@Cacheable` have `condition`/`unless` altering caching behavior?
7. Are there differences in expiry, eviction, serialization, or backends across instances?
8. Do jobs/async tasks/transactions use the same routing rules and invalidation timing?

## 13. Self-check questions

**Question 1.** With the same key `"P1"`, can `price("north","P1")` and `price("south","P1")` accidentally read each other's price if the resolver returns two different caches? **No**, if each cache is a separate entry space and the provider configuration genuinely separates them.

**Question 2.** If `cacheNames` is omitted, is Spring unable to cache? **No**, when a custom `CacheResolver` is properly configured and returns valid caches.

**Question 3.** How must an updater taking `(region, sku, newPrice)` evict the entry of a getter taking `(region, sku)`? **Select the same cache by region and use the same key by sku**, for instance `key = "#p1"` on both.

**Question 4.** Can `cacheManager` and `cacheResolver` be declared simultaneously on a single `@Cacheable`? **No**; they are two mutually exclusive mechanisms for choosing how caches are resolved.

**Question 5.** Is a resolver using a tenant from `ThreadLocal` safe with `@Async`/reactive? **Not by default**. You need a context propagation mechanism matching the execution model, as well as a verified tenant source.

**Question 6.** Can switching from a local cache to Redis be done simply by editing the resolver with no testing? **No**. You still must evaluate TTL, key serialization, latency, error handling, memory/connections, multi-node invalidation, and consistency.

## Conclusion

`CacheResolver` provides a per-call cache "router": **based on arguments or context → select one or more Caches → Spring applies hit/miss/put/evict with the corresponding key**. When caches are fixed, choose `cacheNames` or `cacheManager` to keep configuration simple. When caches must vary at runtime, the resolver should have clear, fast, deterministic rules, validate inputs, and be applied consistently across read–write–delete paths. In multi-tenant applications, this is also a data isolation and security concern, not only a cache optimization.

## Official documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Caching / Custom Cache Resolution: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Javadoc `CacheResolver`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Javadoc `CacheOperationInvocationContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/interceptor/CacheOperationInvocationContext.html
- Javadoc `CacheManager`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/CacheManager.html
