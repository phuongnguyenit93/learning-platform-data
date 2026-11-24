# CacheManager and Looking Up or Creating Caches by Name

> **Context:** Spring Framework Cache Abstraction · **Category:** Architecture. This lesson focuses on how Spring resolves a *cache region* by name, why a name may be created on demand in one implementation yet return `null` in another, and how to use that behavior safely.

## 1. What Problem Does `CacheManager` Solve?

Applications typically have multiple groups of data that need separate caching: `products`, `users`, `exchangeRates`… Each group is a **cache region**: a *key → value* mapping space with its own configuration and lifecycle. When business code or `@Cacheable` requests the `products` region, a component is needed to locate that exact region without coupling to in-memory maps, Caffeine, Redis, or JCache.

Spring defines the `org.springframework.cache.CacheManager` interface as the entry point for retrieving a **cache by name**. It **does not directly decide** how data is stored, time-to-live (TTL), eviction policies, sharing across servers, or whether new caches can be created; those responsibilities belong to the implementation and cache provider.

Distinguishing the three levels:

| Level | Example | Meaning |
| --- | --- | --- |
| `CacheManager` | Bean `cacheManager` | Looks up/coordinates named cache regions |
| `Cache` (region) | `products` | A storage region holding many entries; identified by *cache name* |
| Entry inside `Cache` | `key = sku-42`, `value = Product` | A single item inside the region, identified by *cache key* |

Therefore, `getCache("products")` is an operation to retrieve the `products` **region**, not an operation to retrieve a single product. Only after obtaining the `Cache` does calling `cache.get("sku-42")` look up an **entry** by key.

## 2. Minimal API Contract

The `CacheManager` interface has two main methods:

~~~java
public interface CacheManager {
    Cache getCache(String name);           // may return null
    Collection<String> getCacheNames();
}
~~~

These are **simplified signatures for learning**: the actual interface source may include nullability annotations and imports.

- **`getCache(String name)`**: returns a `Cache` with the requested name, or `null` if it does not exist and cannot/will not be created. Spring allows some implementations to perform **lazy creation** as soon as this method is called. The interface does not guarantee that all implementations will create new ones.
- **`getCacheNames()`**: returns the set of cache names *currently known to the manager*. With dynamically creating managers, the list may change after calls to `getCache(name)`. Do not infer that this is an exhaustive list of all names that could ever exist in the future.
- **There is no `createCache(name)` in the general `CacheManager` SPI.** Initializing cache regions is pre-configured, handled internally during `getCache`, or performed via provider-specific APIs.

The cache name is part of the configuration/contract. `products` and `product` are two different strings; a typo in a dynamic manager can accidentally create a new cache region. Do not confuse Spring's `CacheManager` with identically named interfaces in underlying caching libraries.

The `Cache` object returned by the manager provides operations such as `get(key)`, `put(key, value)`, `evict(key)`, `clear()`, and `getName()`. `Cache.get(key)` returns `Cache.ValueWrapper` or `null` (miss); for implementations supporting null value caching, `ValueWrapper` helps distinguish a *cache hit with a null value* from a *cache miss*.

## 3. Flow of a Request by Name

Example: `CacheManager.getCache("products")`.

1. The caller (Java code or Spring caching interceptor's `CacheResolver`) requests the name `products`.
2. `CacheManager` searches its known regions or queries the corresponding provider.
3. **If the region already exists:** returns the appropriate `Cache` object.
4. **If the region does not exist yet:** the implementation *may* create a new region (dynamic/lazy), or refuse and return `null` (static/preconfigured).
5. Only after obtaining a `Cache` can entries be accessed by key (`get`, `put`, `evict`...). Creating an empty region **does not mean** business data has been loaded into the cache.

~~~text
Application / @Cacheable
         |
         | requests cache name = "products"
         v
      CacheResolver (default)
         |
         v
      CacheManager.getCache("products")
         |
         +-- region exists -------------> Cache("products")
         |
         +-- does not exist
                |-- manager allows dynamic --> create region --> Cache("products")
                |
                +-- manager allows preset names only --> null
                                                          |
                                                        handle error / fix configuration
~~~

The diagram above illustrates *cache resolution*, not the entire `@Cacheable` lifecycle. When using annotations, Spring also generates the key, checks hit/miss, runs the method on a miss, and stores the result in the cache.

## 4. Implementation-Dependent Behavior

| Implementation | When requesting an unconfigured/unknown name | Key points to remember |
| --- | --- | --- |
| `new ConcurrentMapCacheManager()` | **Dynamically creates** a `ConcurrentMapCache` when `getCache(name)` is called | Suitable for demos/tests or simple in-memory caching; each new name can spawn a new region |
| `new ConcurrentMapCacheManager("products", "users")` | **Returns `null`** for names other than the two declared | Static mode helps catch typos and protect the name set |
| `SimpleCacheManager` with pre-registered `Cache`s | Returns only configured regions | Manages a pre-built list of caches |
| `CaffeineCacheManager` | By default can create by name; when `setCacheNames(...)` is set, uses only that list | TTL/size policies live in Caffeine configuration, not in the general SPI |
| `JCacheCacheManager` / external provider-based managers | Depends on regions configured in JCache/provider and lookup capabilities | Do not assume `getCache` always creates caches in the backend |
| `CompositeCacheManager` | Tries managers in order and returns the first non-`null` cache | If a dynamic manager is first, it can accept every name; order is critical |

**Note:** `NoOpCacheManager` provides caches that do not actually store data; enabling a no-op fallback in `CompositeCacheManager` can make missing names harder to detect. Do not use that behavior to assume a real cache was created.

For `ConcurrentMapCacheManager` and `CaffeineCacheManager`, a constructor with no names or `setCacheNames(null)` selects dynamic mode; specifying a list of names via constructor/setter selects static mode. Do not generalize this rule to all manager types, especially Redis/JCache regions or distributed caches.

## 5. Runnable Java 17+ Example: Dynamic vs Static

The example uses **Spring Framework 6.2.x**, requiring only `spring-context`; it does not boot Spring Boot or a database. Create a simple Gradle project with the following two files.

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.CacheManagerLookupDemo'
}
~~~

**`src/main/java/demo/CacheManagerLookupDemo.java`:**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CacheManagerLookupDemo {
    public static void main(String[] args) {
        CacheManager dynamic = new ConcurrentMapCacheManager();

        // Initially there is no "products" region.
        System.out.println(dynamic.getCacheNames().contains("products"));

        // First lookup creates the "products" region in dynamic mode.
        Cache products = Objects.requireNonNull(dynamic.getCache("products"));
        products.put("sku-42", "Keyboard");

        System.out.println(dynamic.getCacheNames().contains("products"));
        System.out.println(products.get("sku-42", String.class));
        System.out.println(products == dynamic.getCache("products"));

        // Static mode only allows declared names.
        CacheManager fixed = new ConcurrentMapCacheManager("products");
        System.out.println(fixed.getCache("unknown") == null);
    }
}
~~~

In the project directory with Gradle (or its wrapper), run:

~~~bash
gradle run --quiet
~~~

**Five stdout lines of the program** (excluding Gradle messages outside application stdout):

~~~text
false
true
Keyboard
true
true
~~~

Step-by-step explanation:

1. The dynamic manager initially does not know `products`.
2. Calling `getCache("products")` creates and registers the new region.
3. The entry with key `sku-42` reads back the value just `put`.
4. Fetching the same name again returns the exact `ConcurrentMapCache` region created in **this example's implementation**; do not infer that every provider must guarantee `==` reference equality like this.
5. The static manager returns `null` for `unknown`. It **does not** create a new region for an invalid name.

The example intentionally operates directly via the API. `@EnableCaching` is not needed to call `CacheManager.getCache(...)` or `Cache.put(...)` in this way.

## 6. Where Does the Manager Participate When Using `@Cacheable`?

With annotations, developers usually declare the cache name without calling `getCache` themselves:

~~~java
// The following snippets illustrate integration within a Spring application,
// not a standalone program to compile separately.

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}

@Service
class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public String loadProduct(String sku) {
        // In a real application, this could be a data store query.
        return "product:" + sku;
    }
}
~~~

The corresponding imports live in `org.springframework.context.annotation.*`, `org.springframework.stereotype.Service`, `org.springframework.cache.annotation.*`, `org.springframework.cache.CacheManager`, and `org.springframework.cache.concurrent.ConcurrentMapCacheManager`.

When another bean calls `ProductService.loadProduct("sku-42")` **through a Spring proxy**:

1. The cache interceptor reads the `@Cacheable(cacheNames = "products")` metadata.
2. The default `CacheResolver` uses the configured `CacheManager` to look up the `products` region.
3. The `KeyGenerator` or `key` expression generates the key; here `#p0` is the first argument `"sku-42"`.
4. If the entry exists, Spring returns the cached value; on a miss, Spring invokes the method and stores the result under the key.
5. If a static manager does not recognize the declared name, cache resolution fails to complete and the caching operation throws a contextual error instead of silently creating a region like a dynamic manager.

For annotations to work, `@EnableCaching` (or equivalent configuration) must be enabled. In the default proxy mode, **self-invocation** within the same bean bypasses the proxy and may skip `@Cacheable`. When multiple `CacheManager`s exist, specify one explicitly with `@Cacheable(cacheManager = "beanName")` or configure an appropriate `CacheResolver`; never leave Spring to pick the wrong backend by accident.

## 7. Safe Lookup in Application Code

If a region is required to exist, **handle the `null` possibility** right at the boundary:

~~~java
Cache products = Objects.requireNonNull(
    cacheManager.getCache("products"),
    "Missing configured cache: products"
);
products.put("sku-42", productName);
~~~

This is an **illustrative snippet**, requiring `cacheManager` and `productName` variables from the application. With providers that do not create dynamically, a missing name fails clearly at the point of use rather than with a `NullPointerException` on a later line.

When an application has a finite set of cache names, use name constants and statically configure that set; maintain a catalog of names, owners, purposes, and backends. Enable dynamic naming only when required and when the number of names is bounded. **Do not** concatenate user input (user ID, tenant ID, URL...) directly into cache names if doing so creates unbounded cache regions; consider keeping a fixed cache and placing those values in the *key*, along with appropriate size limits/TTL.

Example of the right distinction:

- `getCache("products").get("sku-42")`: region **products**, key **sku-42**.
- `getCache("products-sku-42")`: requests a **different region**; in dynamic mode this can create a separate cache per SKU, easily causing unintended region proliferation.

Provider settings must be checked separately: entry count limits, TTL/TTI, serialization, null handling, eviction, cross-node sharing, and metrics. The `CacheManager` SPI does not automatically provide all of these guarantees.

## 8. Common Errors and How to Check Them

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| `getCache(name) == null` | Name not declared in static manager; typo; provider has not initialized the region | Match name against config; inspect `getCacheNames()`; create/configure the region via the provider's proper mechanism |
| Unknown cache names appear in `getCacheNames()` | Dynamic manager auto-created regions due to typos or data-derived names | Use standard names/constants, reject invalid names, check logs where `getCache` is called |
| `@Cacheable` still runs the method every time | Caching not enabled; self-invocation; changing key; cache evicted; no-op provider not retaining entries | Check proxy, `@EnableCaching`, cache name/key, provider, and storage policy |
| Multiple managers present, lookup uses the wrong region | Wrong bean selected or `CompositeCacheManager` returned a cache from an earlier manager | Explicitly specify `cacheManager`/`cacheResolver`; review ordering and dynamic mode |
| Same name used, but apps on other nodes do not see the data | Local provider like `ConcurrentMapCacheManager` only stores inside the JVM process | Use a shared backend if distributed caching is needed; do not equate cache name with shared data |
| Result returns `null` without knowing if it was a miss or a null-value hit | Using `get(key, Type)` or ignoring `ValueWrapper` | When distinguishing is needed, use `Cache.get(key)` and check the wrapper; verify null-value caching policy |

**Diagnose in order:** verify the actual `CacheManager` Spring bean → requested region name → whether `getCache(name)` returns `Cache` or `null` → generated key → whether the provider stores/evicts the entry as expected. This checklist avoids blaming "cache is not working" when the actual failure lies in *cache resolution*.

## 9. Self-Check Questions

1. Why does `getCache("users")` not mean you have retrieved a user? Because it retrieves the **cache region**, whereas `get(userId)` retrieves the entry.
2. With `new ConcurrentMapCacheManager()`, what happens on two calls to `getCache("metrics")`? The first may create the region; the second looks up that same region. `getCacheNames()` will include `metrics` after the lookup.
3. With `new ConcurrentMapCacheManager("products")`, what does `getCache("product")` return? `null`, because it differs from the configured name string.
4. If `CompositeCacheManager` has a dynamic manager before a Redis manager, what can happen? The first manager accepts the name and returns a `Cache`, so the Redis manager is never tried; ordering/strategy must be controlled.
5. If there are one million SKUs, should you create one million cache names? Usually **no**; creating one `products` region and one million keys (with resource limits) is usually the right model.

## 10. Takeaways and Official References

- `CacheManager` manages **named cache regions**; `Cache` manages **entries by key**.
- `getCache(name)` may **look up or lazily create**, but this is **implementation-dependent**; never assume a missing cache will always be created.
- `getCacheNames()` returns the names currently known to the manager, not a promise of all names that could exist.
- Static naming helps catch wrong names early; dynamic naming increases flexibility but requires bounding names and resources.
- When using annotations, resolution goes through `CacheResolver`/`CacheManager`; it still obeys the provider's policies.

References:

- [Spring Framework — CacheManager API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/CacheManager.html)
- [Spring Framework — ConcurrentMapCacheManager API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — Declarative annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
