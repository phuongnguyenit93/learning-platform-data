# Retrieving a Cache via CacheManager.getCache in Spring Framework

## Objectives

In Spring Cache, `CacheManager` is the access point for **named cache regions**. The most basic API is:

~~~java
Cache cache = cacheManager.getCache("products");
~~~

This call requests a `Cache` object named `products`. It is **not** an operation that retrieves the value of a product from the cache. To retrieve an entry by key, you must next call `cache.get(key)`. More importantly, `getCache(name)` **can return `null`** if the cache does not exist or the provider cannot create that cache.

After this lesson, you will be able to:

- Explain the roles of `CacheManager`, `Cache`, cache names, and keys.
- Use `getCache(String name)`, check for `null`, and understand when a manager can automatically create a cache region.
- Distinguish between a non-existent cache, an existing cache with a missed entry, and an entry cached with a `null` value.
- Perform `get`, `put`, `evict`, `clear`, and know when to use `get(key, Callable)`.
- Use the programmatic API on the same cache region as `@Cacheable`/`@CacheEvict`.
- Organize injection, configuration errors, multi-tenancy, testing, and performance monitoring properly.
- Run a Java 17 + Spring Framework demo and verify stdout.

## 1. Two levels of identification: cache name and entry key

Think of the cache as a collection of storage regions:

~~~text
                CacheManager
                     |
          +----------+-----------+
          |                      |
          v                      v
 Cache "products"          Cache "prices"
    |        |                |        |
    v        v                v        v
 key "A"   key "B"          key "A"   key "B"
    |        |                |        |
    v        v                v        v
 ProductA ProductB             100      200
~~~

There are two separate steps:

1. **Select the cache:** `Cache cache = manager.getCache("products");`
2. **Select the entry:** `Cache.ValueWrapper wrapped = cache.get("A");`

The name `products` is not the key `A`. Confusing these two levels makes it easy to write code that accesses the wrong cache region without any compilation error.

| API | Question answered | Result |
| --- | --- | --- |
| `cacheManager.getCache("products")` | Does the manager provide the `products` cache? | A `Cache` or `null` |
| `cacheManager.getCacheNames()` | Which cache names does the manager currently know? | `Collection<String>` |
| `cache.get("A")` | Does this cache have a mapping for key `A`? | `Cache.ValueWrapper` or `null` |
| `cache.get("A", Product.class)` | Can a `Product`-typed value be retrieved for key `A`? | `Product` or `null` per the API contract |
| `cache.put("A", product)` | Store/replace the mapping for `A` | Returns no value |
| `cache.evict("A")` | Request removal of the mapping for `A` | Returns no value |
| `cache.clear()` | Request removal of all entries in this cache region | Returns no value |

`CacheManager` is not a database repository and does not read source data on its own. It only looks up or provides a cache region based on `name`. Calling `getCache` also does not load entries automatically, does not guarantee that data already exists in the returned region, and does not attach a TTL automatically.

## 2. API Contract: getCache can return null

The Spring Framework interface, written in abbreviated form:

~~~java
public interface CacheManager {
    Cache getCache(String name);
    Collection<String> getCacheNames();
}
~~~

This is a **conceptual signature** with annotations and imports omitted, not a standalone Java file. In the official API, `getCache(String name)` is marked nullable:

- `name` is the cache identifier; **`null` must not be passed**.
- Returns the corresponding `Cache` object if the manager can provide it.
- Returns `null` if the cache does not exist or cannot be created.
- Depending on the provider, the cache may be **created lazily right during the `getCache` call**.

Therefore, you should not write:

~~~java
cacheManager.getCache("products").put("A", value);
~~~

if you are not sure the cache always exists. This is an illustrative snippet; the `value` variable is supplied by the application. If the cache does not exist, dereferencing it will throw a `NullPointerException`.

A clearer approach for a cache that **must be configured**:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"),
        "Missing required cache: products");
cache.put("A", value);
~~~

The snippet above requires `import java.util.Objects;`, `import org.springframework.cache.Cache;`, and Spring dependencies. `Objects.requireNonNull` does not create the cache automatically: it simply catches configuration errors early with an easily diagnosable message.

### Two strategies when a cache is not found

**Fail fast:** For a required cache region, throw a meaningful exception. Silently falling back to another cache can break tenant isolation, key namespaces, or consistency.

**Graceful degradation:** When caching is genuinely an optional feature, you can choose a path that reads directly from the data source if the cache is absent. This path must be designed explicitly, rather than accidentally ignoring exceptions on every backend failure; a cache not found and a Redis access failure are two different situations.

Illustrative example:

~~~java
Cache cache = cacheManager.getCache("optional-lookup");
if (cache == null) {
    return repository.load(id); // intentionally run without cache
}
Cache.ValueWrapper wrapped = cache.get(id);
if (wrapped != null) {
    return (Product) wrapped.get();
}
Product product = repository.load(id);
if (product != null) {
    cache.put(id, product);
}
return product;
~~~

The snippet above is **not standalone** because `repository`, `id`, and `Product` belong to the application. It only expresses a bypass policy; in practice, you need to handle types, nulls, concurrency, serialization, and lifecycle consistently. Do not reimplement the entire cache-aside logic manually if `@Cacheable` already meets your needs.

## 3. getCache depends on the specific CacheManager

There is no universal rule that calling `getCache("anything")` always returns a new cache. Whether it behaves as **dynamic** or **static** is determined by the implementation and configuration.

### 3.1. ConcurrentMapCacheManager in dynamic mode

~~~java
CacheManager manager = new ConcurrentMapCacheManager();
Cache alpha = manager.getCache("alpha");
Cache beta = manager.getCache("beta");
~~~

This code is an illustrative snippet. The no-arg constructor creates the manager in **dynamic** mode: the provider can create a `ConcurrentMapCache` for the requested name on first access. In this case, `getCache("alpha")` can return non-null even if the `alpha` region did not exist beforehand.

That does **not** mean entry `"A"` already exists. The new region may still be empty.

### 3.2. ConcurrentMapCacheManager in static mode

~~~java
CacheManager manager = new ConcurrentMapCacheManager(
        "products", "prices");

Cache products = manager.getCache("products"); // non-null
Cache unknown = manager.getCache("unknown");   // null
~~~

When passing a list of cache names to the constructor, `ConcurrentMapCacheManager` is in **static** mode, managing only the specified regions. This is useful in demos/tests because it catches typos:

~~~text
"products" -> configured
"prices"   -> configured
"produts"  -> not configured (typo)
~~~

With a dynamic manager, a typo like `produts` can create **an unintended new region** and make users think `products` is permanently missing. With a static manager, the mistake can be surfaced clearly through a `null` result.

### 3.3. getCacheNames is not always a closed catalog

`getCacheNames()` reports the cache names the manager **currently knows**. In a dynamic manager, the list can grow as new caches are lazily created; in a static manager, the set of names is usually bounded by configuration. Do not rely on `getCacheNames()` to prove all names that could exist in the future or to implement authorization.

### 3.4. Real providers may differ

In a production environment, `CacheManager` may be `CaffeineCacheManager`, `RedisCacheManager`, `JCacheCacheManager`, `CompositeCacheManager`, or a custom implementation. Cache creation policies, TTL configuration, serialization, nulls, eviction, distributed consistency, and exceptions depend on the implementation. Read the corresponding provider contract; **do not treat `ConcurrentMapCacheManager` behavior as a guarantee for every cache provider**.

## 4. Getting a cache region differs from getting a value by key

An important confusion involves the two forms of `null`:

~~~java
Cache cache = cacheManager.getCache("products");
~~~

- If `cache == null`: **the cache region could not be retrieved**.
- If `cache != null` but `cache.get("A") == null`: **the cache region exists**, but no mapping was found for key `A`.

A two-step check is required:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));

Cache.ValueWrapper wrapper = cache.get("A");
if (wrapper == null) {
    System.out.println("MISS: key A");
} else {
    System.out.println("HIT: " + wrapper.get());
}
~~~

This is an illustrative snippet, not a standalone Java file. Only `wrapper == null` indicates a cache miss in the `get(Object)` variant. `wrapper.get()` **can return `null`** if the cache implementation supports storing null values.

### 4.1. An entry containing null differs from an absent entry

For example, a cache provider that allows storing `null` (such as `ConcurrentMapCache` with `allowNullValues=true`):

~~~java
cache.put("A", null);
Cache.ValueWrapper wrapper = cache.get("A");

System.out.println(wrapper == null);   // false: mapping exists
System.out.println(wrapper.get() == null); // true: value is null
~~~

The snippet above assumes the cache is configured to allow cached nulls. Do not assume every backend accepts null. If a backend does not support it, `put(key, null)` may be rejected or have its own semantics.

Comparison:

| State | `cache.get(key)` | `wrapper.get()` |
| --- | --- | --- |
| Entry does not exist | `null` | Not called because there is no wrapper |
| Entry has value `"x"` | Non-null wrapper | `"x"` |
| Entry holds a `null` value supported by the provider | Non-null wrapper | `null` |

### 4.2. Typed get

~~~java
String value = cache.get("A", String.class);
~~~

The typed variant is convenient, but **`null` can mean either a miss or a cached null**; it does not distinguish the two states like `ValueWrapper`. If the actual type is incompatible with `String.class`, the API may throw an exception. Do not use typed lookup blindly when cached data is shared across multiple object types or after schema changes.

## 5. Programmatic operations after obtaining a Cache

### 5.1. Write: put

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));
cache.put("A", "product-A-v1");
~~~

`put` creates or replaces the mapping in the current **cache region**. It does not write to the database. A system can become stale if cache data is put without staying in sync with the source data. Some implementations may perform the operation asynchronously or with latency; check the provider contract.

### 5.2. Read: get

~~~java
Cache.ValueWrapper result = cache.get("A");
if (result != null) {
    Object value = result.get();
    // process value
}
~~~

`get` looks up the exact cache/key. The presence of an entry does not guarantee it is the latest data in the database. TTL, source updates, and invalidation are decisions outside this lookup step.

### 5.3. Remove one entry: evict

~~~java
cache.evict("A");
~~~

Only requests removing the mapping corresponding to key `"A"`. The API returning `void` does not mean the entry is immediately invisible on every provider or every node. `evictIfPresent(key)` is an option whose contract requires the entry to become immediately invisible to subsequent lookups **if the implementation supports those semantics**; you still need to check backend consistency.

### 5.4. Remove all entries: clear

~~~java
cache.clear();
~~~

`clear` requests removing **all mappings in that cache region**, not the entire database or all regions managed by the manager. Avoid using it indiscriminately on caches with many keys because it can cause a burst of misses and increase load on the backend.

Like `evict`, `clear` may not guarantee immediate visibility of its effect in every implementation. `invalidate()` has semantics requiring all existing mappings to become immediately invisible, subject to the API/implementation's own contract.

### 5.5. Retrieve or compute on miss: get(key, Callable)

~~~java
String value = cache.get(
        "A",
        () -> repository.load("A"));
~~~

This is an illustrative snippet; `repository` belongs to the application. Purpose: when the key is not yet present, supply a callback to load the data and optionally cache the result. Errors inside `Callable` may be wrapped as `Cache.ValueRetrievalException`.

Note: this call does **not** mean Spring runs the `@Cacheable` annotation or guarantees only a single load across every backend/cluster. Synchronization capability and atomicity depend on the `Cache` implementation; test under load if this is a critical access path.

## 6. Complete Java 17 + Maven Demo

The demo uses Spring Framework 6.2.16 and `ConcurrentMapCacheManager` in **static** mode with a cache named `products`. A Spring bean has a `@Cacheable` method to prove that:

1. `manager.getCache("products")` returns the cache region.
2. `manager.getCache("unknown")` returns `null`.
3. `cache.get("A")` is initially a miss.
4. The first call to the `@Cacheable` method through the Spring proxy executes the method body and puts the result into the cache; the second call hits.
5. Direct `cache.put` replaces the entry; the `@Cacheable` method reads that same entry.
6. When the data source changes without invalidation, the cache can still return the old value.
7. `cache.evict("A")` causes the next read to miss and reload the data.
8. `cache.clear()` makes the cache region empty again.

### 6.1. File structure

~~~text
get-cache-demo/
├── pom.xml
└── src/main/java/demo/GetCacheDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>get-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

### 6.3. src/main/java/demo/GetCacheDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class GetCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean
        public CacheManager cacheManager() {
            // Static mode: only supports the name "products".
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        // Simulates the data source, separate from the cache.
        private final AtomicInteger sourceVersion =
                new AtomicInteger(1);
        private final AtomicInteger readCount =
                new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String sku) {
            int n = readCount.incrementAndGet();
            System.out.println("DB_READ " + sku + " #" + n);
            return "item-" + sku + "-v" + sourceVersion.get();
        }

        public void changeSourceVersion(int newVersion) {
            sourceVersion.set(newVersion);
            System.out.println("SOURCE_VERSION=" + newVersion);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {

            CacheManager manager =
                    context.getBean(CacheManager.class);
            CatalogService service =
                    context.getBean(CatalogService.class);

            Cache products = Objects.requireNonNull(
                    manager.getCache("products"),
                    "products cache is missing");

            System.out.println("unknownIsNull="
                    + (manager.getCache("unknown") == null));
            System.out.println("initialEntry="
                    + (products.get("A") != null));

            System.out.println("first=" + service.find("A"));
            System.out.println("second=" + service.find("A"));

            Cache.ValueWrapper wrapper = products.get("A");
            System.out.println("cachedValue="
                    + (wrapper == null ? "MISS" : wrapper.get()));

            // Same cache/key as @Cacheable, but operated manually.
            products.put("A", "manual-A");
            System.out.println("afterPut=" + service.find("A"));

            // Change source without evicting: the old entry still hits.
            service.changeSourceVersion(2);
            System.out.println("beforeEvict=" + service.find("A"));

            products.evict("A");
            System.out.println("entryAfterEvict="
                    + (products.get("A") != null));
            System.out.println("afterEvict=" + service.find("A"));

            products.clear();
            System.out.println("entryAfterClear="
                    + (products.get("A") != null));
        }
    }
}
~~~

### 6.4. Running and stdout

Requires JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GetCacheDemo
~~~

Lines printed explicitly by the program, excluding Maven/JVM logs:

~~~text
unknownIsNull=true
initialEntry=false
DB_READ A #1
first=item-A-v1
second=item-A-v1
cachedValue=item-A-v1
afterPut=manual-A
SOURCE_VERSION=2
beforeEvict=manual-A
entryAfterEvict=false
DB_READ A #2
afterEvict=item-A-v2
entryAfterClear=false
~~~

Step-by-step explanation:

- **`unknownIsNull=true`:** because `ConcurrentMapCacheManager("products")` is running in static mode; the name `unknown` does not exist.
- **`initialEntry=false`:** the `products` **region** was retrieved, but the entry for key `A` does not exist yet.
- **`DB_READ A #1` then `first=item-A-v1`:** on the first `@Cacheable` call, the body executes and Spring puts the result into `products`.
- **`second=item-A-v1` without DB_READ:** the call with the same key hits and does not execute the body.
- **`cachedValue=item-A-v1`:** a programmatic `Cache.get` operation sees the exact entry stored by the annotation.
- **`afterPut=manual-A`:** programmatic `Cache.put` replaces the entry value; `@Cacheable` shares the same cache/key so it returns the new value from the cache without executing the body.
- **`SOURCE_VERSION=2` but `beforeEvict=manual-A`:** changing the data source does not automatically update the cache.
- **`entryAfterEvict=false`:** `evict("A")` removes the old entry in the demo's synchronous provider.
- **`DB_READ A #2` and `afterEvict=item-A-v2`:** the next read is a true miss, the body runs, and the cache is reloaded from source version 2.
- **`entryAfterClear=false`:** `clear()` removes all remaining entries in the `products` region.

### 6.5. Key takeaways from the runnable demo

`CatalogService` is retrieved via `context.getBean(...)`, not instantiated directly with `new` in `main`. Thus calls to `service.find(...)` go through the Spring-managed bean and caching advice. If you instantiate `new CatalogService()` outside Spring, `@Cacheable` will not take effect.

The example uses an in-memory cache on a single JVM, with no real database, no TTL, and does not prove multi-node synchronization. It illustrates precisely the difference between **retrieving a region via `CacheManager.getCache`** and **accessing an entry via `Cache.get`**.

## 7. Combining the CacheManager API and caching annotations

A major benefit of the programmatic API is managing the cache manually when specific requirements arise, while routine operations continue using annotations.

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.find(sku);
}
~~~

After a price change event, another bean can invalidate it:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("products"));
cache.evict(sku);
~~~

Both are illustrative snippets, not standalone. They are compatible when:

1. The same `CacheManager` is actually used by Spring for the annotated method.
2. The same region name `products` is used.
3. The same key is used: `#p0` (SKU) in the getter, `sku` in the API.
4. The backend has consistency characteristics suited to the system.

**It is not enough** to merely share the name `products` across two different managers: one Redis, one local Caffeine. They may not share entries at all. With multiple `CacheManager` beans, use `@Qualifier` or an explicit bean name instead of ambiguous injection.

### 7.1. Caution when keys are generated by Spring by default

If the getter does not specify `key`, Spring typically uses `SimpleKeyGenerator`:

| Number of method parameters | Typical default key |
| --- | --- |
| No parameters | `SimpleKey.EMPTY` |
| One non-`null` parameter | That parameter itself |
| Multiple parameters | A `SimpleKey` containing the parameters |

If a method has two parameters (`tenant`, `sku`) and you evict manually using only `sku`, the old entry may **not be removed** because the actual key differs. The safe approach is to explicitly specify the same key expression, or use a shared `KeyGenerator`/design a key class with stable semantics.

For example, a getter with:

~~~java
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product find(String tenant, String sku) {
    return repository.find(tenant, sku);
}
~~~

This is an illustrative snippet; programmatic eviction code needs to use **the exact string `tenant + ":" + sku`** and the same manager. You must consider delimiter collisions, normalization, tenant isolation, and the provider's serializer.

### 7.2. Should you always call the API directly instead of @Cacheable?

No. If the logic is simply caching a result when the same method is called repeatedly, `@Cacheable` is usually more readable, easier to test, and avoids boilerplate duplication. The programmatic API is useful when you want to:

- Check/access an entry at an arbitrary point in time.
- Proactively warm up a known set of keys.
- Delete a key received by an event handler.
- Administer the cache or integrate flows that do not pass through annotations.
- Build a specific, controlled cache-aside mechanism.

Do not **both** manipulate the cache manually inside the body of a `@Cacheable` method **and** let the interceptor put the same entry automatically without a clear reason: it easily leads to double writes, inconsistent timing, or overwritten results.

## 8. Using getCache in a real Spring service

Simple injection when the application has only one cache manager:

~~~java
@Service
public class ProductCacheMaintenance {
    private final CacheManager cacheManager;

    public ProductCacheMaintenance(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void invalidateProduct(String sku) {
        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("products"),
                "products cache is not configured");
        cache.evict(sku);
    }
}
~~~

This is an integration snippet, **not a standalone file**: it requires importing `@Service`, `CacheManager`, `Cache`, `Objects`, and Spring configuration. Constructor injection makes dependencies explicit, eases testing, and avoids lookups before the object is ready.

If there are two managers:

~~~java
public ProductCacheMaintenance(
        @Qualifier("redisCacheManager") CacheManager cacheManager) {
    this.cacheManager = cacheManager;
}
~~~

This snippet shows how to select the right bean when `redisCacheManager` is configured. Keep the `@Cacheable(cacheManager = "redisCacheManager", ...)` annotation and the programmatic path consistent when working with that region.

### Should you call getCache once and hold the Cache forever?

There is no single answer for every provider. Some managers provide stable `Cache` objects; others may reconfigure/reset/swap wrappers over the lifecycle. If you want to hold a `Cache` field to optimize lookups, you must understand the manager/provider contract and application lifecycle. In normal management code, calling `getCache(name)` at operation time is usually simpler, and the cache name lookup cost is typically small compared to backend I/O.

### Use ApplicationContext.getBean instead of CacheManager.getCache?

Those are two different APIs: `ApplicationContext.getBean(CacheManager.class)` retrieves the **cache manager bean** from Spring; `cacheManager.getCache("products")` retrieves the **cache region** inside the manager. Do not confuse these two levels.

## 9. Common pitfalls when accessing the cache programmatically

### 9.1. Misspelled cache names or uncontrolled dynamic creation

A manager that allows creating regions for any name can accidentally turn a typo into a new cache region. When the cache name comes from request input, it can bloat the number of cache regions, consume memory/connections, and complicate operations.

**Solution:** use constant names, configure an allowlist, validate input, or route via a controlled `CacheResolver`. Never concatenate unvalidated tenant input directly into a cache name.

### 9.2. Failing to distinguish a miss from a cached null

Code like:

~~~java
if (cache.get("A", String.class) == null) {
    // Concluding there is definitely no mapping: WRONG.
}
~~~

can be wrong when the provider allows storing cached nulls. If you need to distinguish them, use `Cache.ValueWrapper` or a typed result that explicitly models absent/present states.

### 9.3. Using the wrong key compared to @Cacheable

Cache annotations can use SpEL, a `KeyGenerator`, or the default `SimpleKeyGenerator`. The direct API does not automatically apply another method's `key = "..."`. **You are responsible** for constructing the exact key object when calling `cache.get/evict/put`.

### 9.4. Assuming getCache() always returns non-null

The Javadoc allows `null`. In a static manager or a misconfigured manager, `getCache` can return `null`. Do not let a `NullPointerException` obscure a missing-cache error. Fail fast with a specific message.

### 9.5. Assuming getting a Cache means data is already present

`CacheManager.getCache("products")` returns the cache object; it does not mean `products.get("A")` hits. Both operations work at two separate namespace levels.

### 9.6. Calling clear with overly broad impact

`cache.clear()` removes every entry in that region. If the cache holds data for multiple tenants without separate namespaces, this operation can trigger a massive wave of misses. Prefer `evict(key)` when you know the exact key that changed.

### 9.7. Ignoring transactions and concurrency

If a DB transaction has not committed yet, a read request can miss after eviction and reload the old value back into the cache. `getCache` itself provides neither transactions nor locking. You need to design post-commit invalidation if required by the application, while also considering the cache provider, reader/writer races, and TTL.

### 9.8. Ignoring multi-instance behavior

`ConcurrentMapCacheManager` across two JVMs creates **two separate local caches**. Instance A calling `cache.evict("A")` does not automatically remove the corresponding entry on instance B. To share or distribute evictions, you need a properly designed shared/synchronized backend.

### 9.9. Not handling backend failures

Failing to find a cache region (`getCache == null`) is different from obtaining the cache and having the Redis backend lose connection during `get/put/evict`. Distinguish configuration errors, business errors, timeouts, and provider errors. Depending on requirements, have a clear degrade/retry/alert policy; do not silently ignore failed evictions if stale data is harmful.

## 10. Behavior verification tests

Below is a testing checklist that is more valuable than merely comparing returned strings:

| Scenario | Setup | What to verify |
| --- | --- | --- |
| Configured region | Static manager containing `products` | `getCache("products") != null` |
| Missing region | Static manager without `unknown` | `getCache("unknown") == null` |
| Dynamic cache name | Empty dynamic manager | Can create a new region on `getCache(name)` |
| Entry miss | Cache exists, key `A` absent | `cache.get("A") == null` |
| Entry containing null | Provider allows cached-null | Non-null `ValueWrapper`, but `wrapper.get()==null` |
| Manual write | `cache.put("A","v1")` | Lookup for entry A returns `v1` |
| Evict | A and B present | `evict("A")` removes only A; B remains |
| Clear | A and B present | `clear()` removes entries of that cache |
| Annotation combination | `@Cacheable` and API use same manager/key | Both paths see the same entry |
| Different managers | Annotation uses Redis, API uses local | Entries are not shared by default |
| Concurrency | Multiple threads miss simultaneously | Verify backend load, races, and provider semantics |

You can use `ConcurrentMapCacheManager("products")` in integration tests to catch typos via static mode. For testing consistency/distributed failures, run against a provider close to production, because an in-memory manager cannot prove multi-node/TTL/transactional behavior of Redis.

## 11. Self-check questions

**Question 1.** Does `cacheManager.getCache("products")` return product A's data?

**Answer:** No. It returns the `Cache` region named `products` or `null`. To retrieve entry A, use `cache.get("A")`.

**Question 2.** If `getCache("products")` returns `null`, can you conclude product A is not in the cache?

**Answer:** You should not describe it that way. The immediate issue is that **the cache region could not be retrieved**; there is no object to look up entry A. You must handle the configuration error / non-existent region first.

**Question 3.** Does a manager without `temp` pre-declared always return `null` on `getCache("temp")`?

**Answer:** No. With a dynamic `ConcurrentMapCacheManager()`, the `temp` region can be created lazily. With a static `ConcurrentMapCacheManager("products")`, names outside the list return `null`.

**Question 4.** When `cache.get("A", String.class)` returns `null`, is entry A guaranteed to be absent?

**Answer:** Not necessarily. Typed get can return `null` both when the entry is absent and when cached-null is supported; to distinguish them, use `ValueWrapper`.

**Question 5.** When `@Cacheable` uses `key="#p0"`, does the API call `cache.evict(sku)` remove the same entry?

**Answer:** Yes **if** both operation paths use the same manager, the same cache name, and the same `sku` key object. If the manager, namespace, or key generation differs, there is no guarantee.

**Question 6.** Does calling `cache.put` via the API update the database?

**Answer:** No. `Cache.put` only writes the mapping in the cache. To modify the source data, you need to call the business repository/service.

**Question 7.** Can `getCacheNames()` be used to authorize a user to access another tenant?

**Answer:** No. This is an API that lists cache names known to the manager, not an authentication/authorization mechanism. Isolation must be designed at data/tenant boundaries and access permissions.

## 12. Conclusion

`CacheManager.getCache(name)` is the entry point to a **cache region** in Spring Cache. The right mental model is always:

~~~text
CacheManager
    |
    +-- getCache(cacheName)
              |
              +-- null -> cache region does not exist / cannot be created
              |
              +-- Cache object
                    |
                    +-- get(key)   -> look up entry, may miss
                    +-- put(key)   -> write/replace entry
                    +-- evict(key) -> remove an entry
                    +-- clear()    -> request removal of all entries
~~~

Check for `null` at the **cache** level, distinguish `ValueWrapper` and cached-null at the **entry** level, select the right manager/cache/key, and understand whether the provider can auto-create caches by name. When combining the programmatic API with `@Cacheable`, operations only affect each other when they reference the same actual cache region and the same key rules.

## Official documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotation Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- `CacheManager` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/CacheManager.html
- `Cache` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- `ConcurrentMapCacheManager` Javadoc (Spring 6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
