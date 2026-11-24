# Defining Explicit Cache Names or Creating Them Dynamically in Spring Cache

## Objectives

After this lesson, you will be able to identify where a **cache name** comes from, declare fixed caches using `cacheNames`/`@CacheConfig`, distinguish **selecting a cache name per call** from **creating a new cache region when a name does not yet exist**, and implement a `CacheResolver` to select cache regions from runtime data. You will also know how to bound dynamic cache names, verify reads/evictions target the right region, and avoid confusing cache names with individual entry keys.

Context: an e-commerce system has `getProduct(tenantId, productId)`. Two valid designs exist: storing all tenants in a fixed cache named `"products"` with a key containing both `tenantId` and `productId`, or routing each tenant to its own cache region such as `"products.north"` and `"products.south"` and using `productId` as the key inside that region. This lesson focuses on **how cache region names are defined and resolved**, along with the conditions required for that choice to take effect.

## 1. How Does a Cache Name Differ from a Cache Key?

A cache entry is logically identified by the pair `(cacheName, key)`:

~~~text
CacheManager
    |
    +-- Cache "products.north"
    |       +-- key "P1" -> Product north/P1
    |       +-- key "P2" -> Product north/P2
    |
    +-- Cache "products.south"
            +-- key "P1" -> Product south/P1
~~~

- **Cache name** is the name of the region/namespace, e.g. `products.north`. `CacheManager` looks up the `Cache` object by name via `getCache(name)`.
- **Cache key** distinguishes individual results within **one** region, e.g. `"P1"`. `key` (SpEL) or `KeyGenerator` determines the entry key, not the region name.
- **CacheResolver** returns the set of `Cache` instances an operation will use; it can choose based on declared names or runtime arguments of the call.
- **Backend/provider** such as `ConcurrentMapCache`, Caffeine, or Redis determines how caches are actually stored and managed. `CacheManager` and the provider may restrict, dynamically create, or report missing cache names.

Therefore `(products.north, P1)` and `(products.south, P1)` are **two separate entries**, even though both keys are `"P1"`. Changing a cache name is like changing where data is looked up: entries in the old region do not automatically move to the new region.

### Responsibility Map

| Component | Primary input | Output | Does it decide the cache name? |
| --- | --- | --- | --- |
| `@Cacheable(cacheNames="products")` | Annotation declaration | Supplies explicit list of names | Yes, when using the default resolver |
| `@CacheConfig(cacheNames="products")` | Class-level declaration | Shared default for operations inside | Yes, via class configuration |
| `CacheResolver` | Operation, method, runtime arguments | One or more `Cache` objects | **Yes**, including dynamically |
| `CacheManager` | `getCache(String name)` | `Cache` object or `null` | Manages/resolves/creates regions depending on implementation |
| `key`/`KeyGenerator` | Arguments and call metadata | Key within the cache region | No |
| `condition`/`unless` | SpEL condition | Whether to cache the result | Does not change the region name |

Explicit naming and dynamic creation are **two separate axes**: a name can be fixed while `CacheManager` creates the container when needed; or a resolver can pick names dynamically while the manager allows only a pre-initialized list of regions.

## 2. Option 1: Set Explicit Cache Names Directly on the Annotation

With the simplest approach, declare `cacheNames` (or its alias `value`):

~~~java
// Illustrative signatures; Product and repository are application components.
@Cacheable(cacheNames = "productsById", key = "#p0")
public Product getById(String productId) {
    return repository.findById(productId).orElseThrow();
}

@CacheEvict(cacheNames = "productsById", key = "#p0")
public void invalidateById(String productId) {
    // Update/delete data in the appropriate place per business logic.
}
~~~

Each call to `getById("P1")` targets the cache named `"productsById"` and key `"P1"`; `invalidateById("P1")` has the same name and key and therefore targets the exact same entry. Quotes around the name are simply a Java string literal. These two forms are equivalent:

~~~java
@Cacheable("productsById")
@Cacheable(cacheNames = "productsById")
~~~

These are **two alternative ways of writing the same annotation**, not to be placed together on a single method. Fixed names make configuring TTLs, capacity limits, metrics, and region-wide eviction more predictable.

Not only `@Cacheable`, `@CachePut` and `@CacheEvict` also accept `cacheNames`. Keep names and key computation consistent across **read, update, and invalidation** paths. An update call can succeed while leaving stale data in the cache if `@CachePut` and `@Cacheable` point to two different regions.

### Using `@CacheConfig` to Reduce Repetition in the Same Class

~~~java
// Illustrative class definition; repository dependency depends on the project.
@Service
@CacheConfig(cacheNames = "productsById")
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.findById(id).orElseThrow();
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String id) {
    }
}
~~~

`@CacheConfig` provides class-level defaults for `cacheNames` (as well as several other cache attributes). It **does not enable caching on its own**: each method still needs an annotation such as `@Cacheable`, `@CachePut`, or `@CacheEvict`; the application still needs `@EnableCaching`. Specific declarations on a method override the corresponding class defaults.

Avoid using a vague generic name like `"data"` for unrelated result types. For instance, if `findBySku("42")` and `findById("42")` share the same cache and key rule, their entries can collide. Use distinct names like `"productsBySku"` and `"productsById"`, or design key identifiers that distinguish their semantics.

## 3. Declaring a Cache Name Does Not Mean Creating the Cache Region

A common pitfall: `@Cacheable(cacheNames="productsById")` describes **which name you want to use**, whereas whether that cache region exists or gets created at call time is up to the `CacheManager`/provider.

`org.springframework.cache.CacheManager` has two key methods:

~~~java
// Excerpted API signatures for explanation, not a file to create.
Cache getCache(String name);
Collection<String> getCacheNames();
~~~

`getCache("productsById")` returns a matching `Cache` or `null` if the manager does not support that name. `getCacheNames()` reports the names the manager currently knows about; this list is not necessarily fixed if the manager supports dynamic creation.

With Spring's `ConcurrentMapCacheManager`, two modes are easy to observe:

~~~java
// Static mode: accepts only the declared names.
CacheManager fixed = new ConcurrentMapCacheManager(
        "productsById", "productsBySku");

// Dynamic mode: creates a ConcurrentMapCache when a new name is requested.
CacheManager dynamic = new ConcurrentMapCacheManager();
~~~

`fixed.getCache("unknown")` returns `null`. `dynamic.getCache("unknown")` creates a region named `"unknown"` on the first lookup. This is a characteristic of **`ConcurrentMapCacheManager`**, not a universal guarantee across every `CacheManager`. With other managers/providers, region declaration, auto-created caches, serializers, TTLs, and name restrictions can differ.

If a static example is needed in an application:

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productsById", "productsBySku");
    }
}
~~~

The snippets in this section are standalone configuration illustrations; the full runnable example in Section 6 uses dynamic mode. `ConcurrentMapCacheManager` is suitable for learning and simple single-JVM scenarios; it does not provide TTL policies or sophisticated memory limits like a dedicated cache.

### Comparing Four Scenarios

| Name selected per call | How the manager handles the name | Result |
| --- | --- | --- |
| Explicit `"products"` | Already has `"products"` | Uses the existing region |
| Explicit `"products"` | Manager auto-creates when absent | Region `"products"` is created on first call even though the annotation is static |
| Resolver returns `"products.north"` or `"products.south"` | Manager accepts new names and creates dynamically | Corresponding region is created per tenant |
| Resolver returns a new name | Manager supports only a static list | `getCache` may return `null`; resolver must handle it explicitly |

This shows that **dynamic names** and **dynamically initialized caches** are two distinct things.

## 4. Why Not Put a SpEL Expression in `cacheNames`?

The example below **does not achieve selecting a cache by argument**:

~~~java
// Wrong intent: the string below is a literal cache name, not SpEL.
@Cacheable(cacheNames = "'products.' + #p0", key = "#p1")
public Product get(String tenantId, String productId) {
    return load(tenantId, productId);
}
~~~

`cacheNames` is a list of **names** taken from the annotation, not a SpEL expression attribute like `key`, `condition`, or `unless`. Spring does not interpret the string `"'products.' + #p0"` as a dynamic name at runtime. Meanwhile `key="#p1"` is SpEL and is evaluated using the second argument. For per-tenant partitioning, using a `CacheResolver` is more appropriate.

If **you do not actually need separate regions**, you can keep a static name and include the tenant in the key:

~~~java
// Illustration: one shared region; the key must consider both tenant and productId.
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product get(String tenantId, String productId) {
    return load(tenantId, productId);
}
~~~

Simple string concatenation can collide if data contains `:`; in that case use a structured key, a `KeyGenerator`, or unambiguous component encoding. A shared cache name with a composite key usually avoids creating a number of regions proportional to the number of tenants.

## 5. Option 2: Choosing a Cache Name at Runtime with `CacheResolver`

When the region name must depend on the request being processed, Spring provides this interface:

~~~java
package org.springframework.cache.interceptor;

// Abbreviated signature for learning; do not redeclare in your project.
public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
~~~

`context` exposes `getMethod()`, `getTarget()`, `getArgs()`, and `getOperation()`, allowing the resolver to decide cache regions from arguments, metadata, or an application configuration policy. It returns **`Cache` objects**, not merely a string name. A practical resolver usually calls `cacheManager.getCache(name)` to look up or create the region.

Declaration on a method:

~~~java
// Illustration: the tenantCatalogResolver bean will be defined in Section 6.
@Cacheable(cacheResolver = "tenantCatalogResolver", key = "#p1")
public String read(String tenantId, String productId) {
    return loadProduct(tenantId, productId);
}
~~~

`cacheNames` is unnecessary when the resolver determines the region itself. Spring invokes the resolver for the operation and uses the caches it returns. If it returns `null`, an empty collection, or a non-existent cache, the operation has no valid region to act on; it is best to **fail fast with a contextual exception** when a requested name is unsupported.

Configuration note: **`cacheManager` and `cacheResolver` are mutually exclusive on the same cache annotation**; declaring both causes Spring to throw an error. `cacheManager` picks the manager for the default resolver; `cacheResolver` replaces how caches are resolved. Meanwhile `key` and `keyGenerator` form another mutually exclusive pair for **entry keys**.

A resolver can return multiple caches; most use cases need only one. With multiple caches, `@Cacheable` can check for hits in order and populate the specified regions per Spring's contract, though behavior with async/reactive caches can depend on the provider. Do not use multiple regions just to simulate tenant partitioning when a single cache suffices.

## 6. Runnable Example: Each Tenant Picks a Cache, Regions Created Dynamically

This example uses **JDK 17+, Maven, Spring Boot 3.3.5**, and `spring-boot-starter-cache`. Two valid tenants are `north` and `south`. On each query, `tenantCatalogResolver` maps the tenant to an allowed name; `ConcurrentMapCacheManager()` creates the region when a new name appears. Both `@Cacheable` and `@CacheEvict` use the resolver to target the right region.

Project structure:

~~~text
dynamic-cache-name-demo/
|-- pom.xml
+-- src/main/java/example/cache/
    |-- DemoApplication.java
    +-- TenantCatalogService.java
~~~

**`pom.xml`**

~~~xml
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
    <artifactId>dynamic-cache-name-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
~~~

**`src/main/java/example/cache/DemoApplication.java`**

~~~java
package example.cache;

import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    // No predefined name list => dynamic cache creation mode.
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager();
    }

    @Bean("tenantCatalogResolver")
    CacheResolver tenantCatalogResolver(CacheManager cacheManager) {
        Map<String, String> allowedNames = Map.of(
                "north", "catalog.north",
                "south", "catalog.south");

        return context -> {
            Object[] args = context.getArgs();
            if (args.length < 2 || !(args[0] instanceof String tenant)) {
                throw new IllegalArgumentException(
                        "Expected tenant and productId");
            }

            String cacheName = allowedNames.get(tenant);
            if (cacheName == null) {
                throw new IllegalArgumentException(
                        "Unsupported tenant: " + tenant);
            }

            Cache selected = cacheManager.getCache(cacheName);
            if (selected == null) {
                throw new IllegalStateException(
                        "Cache is unavailable: " + cacheName);
            }
            return List.of(selected);
        };
    }

    @Bean
    CommandLineRunner demo(TenantCatalogService service,
                           CacheManager cacheManager) {
        return args -> {
            System.out.println(service.read("north", "P1"));
            System.out.println(service.read("north", "P1"));
            System.out.println(service.read("south", "P1"));
            System.out.println("Caches="
                    + new TreeSet<>(cacheManager.getCacheNames()));
            service.invalidate("north", "P1");
            System.out.println(service.read("north", "P1"));
        };
    }
}
~~~

**`src/main/java/example/cache/TenantCatalogService.java`**

~~~java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class TenantCatalogService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheResolver = "tenantCatalogResolver", key = "#p1")
    public String read(String tenantId, String productId) {
        int attempt = loads.incrementAndGet();
        return tenantId + "/" + productId + " -> load#" + attempt;
    }

    @CacheEvict(cacheResolver = "tenantCatalogResolver", key = "#p1")
    public void invalidate(String tenantId, String productId) {
        // In practice usually called after modifying/deleting source data.
    }
}
~~~

From the project directory, run:

~~~bash
mvn -q spring-boot:run
~~~

Lines **printed by the demo program** (excluding Spring startup logs):

~~~text
north/P1 -> load#1
north/P1 -> load#1
south/P1 -> load#2
Caches=[catalog.north, catalog.south]
north/P1 -> load#3
~~~

Explanation in sequence:

1. `read(north, P1)` picks cache `"catalog.north"`; the manager creates the region for the first time; key `"P1"` is absent so the method runs (`load#1`).
2. Reading the same tenant/id again hits the cache without incrementing the counter, so it remains `load#1`.
3. `read(south, P1)` picks region `"catalog.south"`; key `"P1"` is not in that region yet, giving `load#2`.
4. `getCacheNames()` now contains both regions, sorted for stable printing.
5. `invalidate(north, P1)` selects **the right region** `"catalog.north"` again and deletes key `"P1"`; the subsequent `read(north, P1)` misses and produces `load#3`. The value for tenant `south` is not deleted.

In the demo, the first argument `tenantId` identifies the region and the second argument `productId` identifies the key. `key="#p1"` is completely valid here **because tenants are already separated by cache name**. If you switched to **one shared cache** while still taking only `productId`, tenants would collide on keys. Hence, cache naming and key selection must be designed together.

`Map.of(...)` acts as an **allowlist**, proactively blocking unknown tenants. Only update the mapping table and configuration policy when you intentionally want to support a new tenant; do not directly concatenate arbitrary input into region names in a manager that creates caches dynamically.

## 7. Multiple Managers and the Default Resolver

An application can use multiple cache managers—for example, one manager for reference catalog data and another for expensive computed results. When names are fixed and you only need to pick a specific manager, declaring the `cacheManager` attribute suffices:

~~~java
// Illustrative signature snippet: catalogCacheManager is the name of a CacheManager bean.
@Cacheable(cacheNames = "products", cacheManager = "catalogCacheManager",
           key = "#p0")
public Product getProduct(String id) {
    return loadProduct(id);
}
~~~

When `cacheManager` is used as above, the default resolver resolves the name `"products"` through the specified manager. If you must **pick the manager or cache name based on call data**, you can write a `CacheResolver` that deliberately picks the appropriate manager/region according to business policy. Every branch must know where to read, write, and evict.

Do not assume changing the manager changes the name: **two different `CacheManager` instances can both contain a `"products"` cache**, yet their data is independent. The logical identity of an entry depends on the manager/provider, cache name, and key.

### Multiple `cacheNames` on One Operation

~~~java
// Illustrates a special requirement; unnecessary for the tenant-partitioning example.
@Cacheable(cacheNames = {"productsFast", "productsBackup"}, key = "#p0")
public Product getById(String id) {
    return loadProduct(id);
}
~~~

The default resolver returns multiple `Cache` objects, which can be checked for hits in order and populated according to annotation semantics. However, with asynchronous/reactive caches and provider miss detection, Spring warns that not every subsequent cache is always consulted. Choose this approach only when there is a clear requirement and test the actual backend's behavior. Do not list multiple names just because a canonical name for a dataset has not been decided.

## 8. Choosing Between Fixed Names, Dynamic Names, and Namespaced Keys

| Requirement | Usually sensible option | Why |
| --- | --- | --- |
| Each data kind has one clear region | `@Cacheable(cacheNames="products")` | Easy to administer, configure TTL/metrics, and control names |
| Multiple methods share one region | `@CacheConfig(cacheNames="products")` | Reduces repetition and keeps configuration readable |
| A few tenants/regions need separate policies | `CacheResolver` + normalized names/allowlist | Picks cache from runtime data |
| Unbounded or very many tenants | One stable name + key containing tenant | Avoids growing cache region count with tenant count |
| Manager has a fixed set of names | Pre-initialize name list and reject unknown names | Catches typos or misconfiguration early |
| Need different TTL/serializer per group | Select preconfigured manager/cache per policy | Avoids assuming dynamically created caches have the right config |
| Only the key needs to vary within one region | `key`/`KeyGenerator` | No `CacheResolver` needed |

A manageable naming convention is `<domain>.<purpose>.<scope>` such as `"catalog.byId.north"` when regions genuinely need scope separation. Names should be consistent in casing, whitespace, separators, and versioning. If a provider applies prefixes or transforms names into physical keys (e.g., Redis), logical and physical names may differ; verify provider configuration before relying on external tools to delete data.

Do not generate names from timestamps, random UUIDs, or per-request values; that causes constant cache misses and can spawn too many regions. For user-supplied scopes, verify the tenant/account from an authenticated identity and authorization rules; never trust a raw client-sent string alone.

## 9. Limits and Operational Consequences of Dynamic Caches

### Risk of Unbounded Region Growth

If names are built directly from `tenantId` and `CacheManager` creates a new region for every name, tens of thousands of tenants or invalid inputs can spawn tens of thousands of `Cache` instances. With an in-memory manager, this bloats JVM structures and makes enforcing TTLs/capacity limits difficult. The design needs one of: a valid-name allowlist, a managed lifecycle registry, a bounded set of scopes, or one shared cache name with partitioned keys.

### `CacheManager.getCache(name)` Can Return `null`

A `CacheResolver` should inspect the result before building the returned list. Returning `List.of(null)` throws immediately in Java; returning an empty collection leaves the cache operation with no valid region to act on. Throwing an error describing the expected name speeds debugging far more than observing anomalous cache hits/misses.

### Renaming Breaks Invalidation Targeting

If `@Cacheable` reads from `"catalog.north"` while `@CacheEvict` deletes from `"catalog"`, cached data stays behind. Likewise, when a naming policy changes from `catalog.north` to `catalog.tenant.north`, old data is not automatically migrated or cleared. Plan renaming, invalidation, or migration accordingly. With `@CacheEvict(allEntries=true)`, Spring clears **all entries in the regions returned by the resolver**, not every region managed by the manager by default.

### Spring Configuration and Real Applications

- `@EnableCaching` enables annotation caching; methods must be invoked through the Spring-managed proxy. Internal self-calls like `this.read(...)` bypass the interceptor in default proxy mode.
- The bean name in `cacheResolver = "tenantCatalogResolver"` must match; `cacheManager = "..."` and `cacheResolver = "..."` cannot be set on the same operation.
- `@CacheConfig` supplies defaults only; it does not enable caching on every method by itself.
- Dynamic values like `tenantId` should come from a verified trusted source; if using ThreadLocal/context, account for thread pools, reactive flows, and non-propagating contexts.
- Caches auto-created in `ConcurrentMapCacheManager` are **JVM-local**. When multiple instances run, each has its own memory; shared caching requires a distributed provider and appropriate synchronization/eviction.
- With Redis/Caffeine/JCache, region creation, memory, expiration, serializers, and limits differ. Do not carry demo assumptions straight into production without reading the active provider's documentation.

## 10. Testing Cache Name Selection

Tests must prove **identical keys in two regions do not collide**, the resolver picks the right name, and eviction targets the right region. For the Section 6 example, you can verify directly via `CacheManager` after calls run:

~~~java
// Additional verification snippet in a context where service and cacheManager already exist.
String first = service.read("north", "P1");
String again = service.read("north", "P1");
String other = service.read("south", "P1");

if (!first.equals(again)) {
    throw new AssertionError("Repeated call should hit north cache");
}
if (first.equals(other)) {
    throw new AssertionError("Tenant caches must be independent");
}

Cache north = cacheManager.getCache("catalog.north");
Cache south = cacheManager.getCache("catalog.south");
if (north == null || south == null) {
    throw new AssertionError("Expected cache names not found");
}
if (!first.equals(north.get("P1", String.class))) {
    throw new AssertionError("North cache entry mismatch");
}
if (!other.equals(south.get("P1", String.class))) {
    throw new AssertionError("South cache entry mismatch");
}

service.invalidate("north", "P1");
if (north.get("P1") != null || south.get("P1") == null) {
    throw new AssertionError("Eviction targeted wrong cache");
}
~~~

This is an **illustrative verification snippet**, placed inside a method/test that already has `service` and `cacheManager`; it is not a standalone Java file. In real applications, use Spring integration tests, stub repositories, or source-read counters. Beyond cache hits/misses, test invalid names, tenant permissions, cases where the cache manager does not recognize a region, concurrent behavior, and the chosen TTL/provider policies.

A test should prove the behavior of the **actual cache provider**, not just the name returned by `CacheResolver`. Redis may apply physical prefixes, key serialization, and configuration policies different from an in-memory manager.

## 11. Common Errors and How to Check Them

| Symptom | Common cause | What to check |
| --- | --- | --- |
| `cacheNames="#p0"` does not change the name by argument | `cacheNames` does not evaluate SpEL | Use `CacheResolver` for dynamic names; use `key` for entry keys |
| New cache name is not used | Static manager returns `null` for unknown names | Check `getCache(name)` and the list of valid names |
| Every request misses and many strange names appear | Names generated from unstable/random values | Normalize, bound region count, or use a shared cache |
| Two tenants receive the same data | Shared cache used but key omits tenant | Include tenant in the key or separate regions with a resolver |
| Evict does not remove data being read | Read/evict resolvers produce different names or keys | Compare manager, `cacheName`, and key on both paths |
| Resolver bean does not run | Wrong bean name, missing `@EnableCaching`, called via `this` | Check config and invoke method from another bean |
| Many regions increase memory usage | Unbounded cache creation in JVM | Control names/registry, choose a provider with explicit limits |
| Switching providers breaks cache configuration | Relied on old region-creation/serializer mechanism | Verify name setup and policies per provider |
| Error when declaring `cacheManager` alongside `cacheResolver` | Mutually exclusive attributes | Choose one resolution approach per operation |
| `@CacheEvict(allEntries=true)` clears too much | Resolver returned multiple regions | Precisely restrict the regions returned for the operation |

When investigating, log the **resolved cache name** and **sanitized keys** at an appropriate debug level. Avoid logging tokens, personal data, full payloads, or sensitive tenant identifiers publicly.

## 12. Practice Exercises

**Exercise 1.** An application has two read methods `getProduct(id)` and `getCategory(id)` that both use the name `"cache"`. How should this be designed?  
**Hint:** if both result sets can share string keys, entries risk colliding. Use two explicit names `"products"`/`"categories"` or keys with a well-designed discriminator.

**Exercise 2.** A system has millions of accounts; should you create a cache named `"profile." + accountId` for each account?  
**Hint:** usually not sensible with a dynamic-creation manager because region count grows with accounts. Consider one `"profiles"` region with keys containing `accountId`, and configure TTL/limits on the provider.

**Exercise 3.** A resolver selects `"catalog.north"` for reads and `"catalog.south"` for eviction of the same product `"P1"`. What happens?  
**Answer:** eviction does not remove the read entry because it targets a different `cacheName`. Both operations must apply the same region-selection policy for the same entity.

**Exercise 4.** What happens when `new ConcurrentMapCacheManager("a", "b")` receives a request for `"c"`? And what about `new ConcurrentMapCacheManager()`?  
**Answer:** the fixed-list variant returns `null` for `"c"`; the no-arg variant creates region `"c"` on demand. This is a rule specific to this manager.

## Official Documentation

- Spring Framework, Annotation-based caching and Custom Cache Resolution: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Javadoc `ConcurrentMapCacheManager` and static/dynamic modes: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Boot, Caching providers/configuration: https://docs.spring.io/spring-boot/reference/io/caching.html

**Core takeaway:** `cacheNames`/`@CacheConfig` fits **explicit names**; `CacheResolver` enables **runtime region selection**; `CacheManager` decides **whether that region can be retrieved or created**. Cache names and keys must be designed consistently across all read, update, and delete paths.