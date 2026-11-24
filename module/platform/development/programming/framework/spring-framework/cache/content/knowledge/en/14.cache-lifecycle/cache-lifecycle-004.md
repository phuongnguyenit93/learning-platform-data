# Null Policies and Provider Value Adaptation in Spring Cache

## 1. Goals and design questions

When a method annotated with `@Cacheable` returns `null`, Spring must decide whether **“there is no business value”** should become a **valid cache entry**. The problem is not as simple as inserting `null` into a `Map`: many cache stores such as `ConcurrentHashMap` and native Caffeine caches **do not allow storing Java `null` directly**. Spring Cache has a value adaptation layer that represents a cached `null` using an internal marker, then converts that marker back to `null` on read.

Three questions must be kept distinct:

1. **Does an entry exist?** A cache miss means there is no mapping for the key, or the entry has expired/been evicted. A cache hit with a `null` value means **a mapping exists, but its business content is `null`**.
2. **Is caching `null` allowed?** The policy depends on the `CacheManager`/`Cache` implementation and configuration. `@Cacheable(unless = "#result == null")` is a way to **avoid writing a `null` result**, which is completely different from the provider **rejecting** `null` storage.
3. **How does the provider store the data?** Spring may substitute `null` with `NullValue.INSTANCE` or a representation supported by the provider/serializer. Applications should normally work through the `Cache` abstraction rather than assuming the native cache holds raw Java `null`.

This lesson belongs to the **Data and Lifecycle** group: it focuses on policies for accepting/storing/reading `null`, provider value adaptation, the lifecycle of cached nulls, testing approaches, and integration pitfalls. Do not use this lesson to replace full guides on key design, transactions, or TTL strategies; those topics are mentioned only where they directly affect the correctness of cached nulls.

## 2. Three distinct states: miss, hit-null, hit-value

At the API level, the following states must be distinguished for the same key `k`:

| Logical state | Key has a mapping? | `Cache.get(k)` | `Cache.ValueWrapper.get()` if present |
| --- | --- | --- | --- |
| **Miss** | No | `null` | No wrapper |
| **Hit with null** | Yes, if supported by the provider | **Non-null** `ValueWrapper` | `null` |
| **Hit with non-null value** | Yes | **Non-null** `ValueWrapper` | Business value |

This is the contract of `Cache.get(Object)`. Checking `cache.get(k) == null` means **no entry exists**; whereas `cache.get(k).get() == null` (after verifying the wrapper is non-null) means **an entry exists and stores `null`**. This resolves the ambiguity that `ConcurrentHashMap` cannot handle on its own.

Correct usage when interacting with the `Cache` API directly:

~~~java
Cache.ValueWrapper wrapper = cache.get(key);
if (wrapper == null) {
    // Cache miss: can call the source and put the new value
} else {
    Object businessValue = wrapper.get();
    // Cache hit: businessValue can be null!
}
~~~

This is a snippet requiring `Cache cache` and `Object key` to be defined beforehand, not a standalone Java file.

**Be careful with the `get(key, Class<T>)` overload:** this typed `get` returns `T` or `null` directly. According to Spring's contract, it **cannot distinguish** between a “cache miss” and a “hit-null” because both can return `null`. When your logic must distinguish them, use `get(key)` and inspect the `ValueWrapper`.

A semantic example:

~~~text
get("id-1") == null                       => no entry (miss)
get("id-2") != null
get("id-2").get() == null                 => entry stores null (hit-null)
get("id-3") != null
get("id-3").get().equals("active")        => entry stores "active" (hit-value)
~~~

The last three lines are logical representations, not complete Java statements; real code must check for null before calling `get()` or `equals()`.

## 3. Value adaptation: why does `NullValue` exist?

Spring provides `org.springframework.cache.support.AbstractValueAdaptingCache`, which serves as the base class for several implementations such as `ConcurrentMapCache`, `CaffeineCache`, and `JCacheCache`. Its role is to translate **application-level values** into **values storable in the backing store**:

- `toStoreValue(userValue)`: converts a business value into its native store representation.
- `fromStoreValue(storeValue)`: decodes a representation from the native store back into a business value.
- `toValueWrapper(storeValue)`: wraps a raw store value in a `Cache.ValueWrapper` (typically `SimpleValueWrapper`) after performing value adaptation.
- `isAllowNullValues()`: indicates whether the cache instance allows adapting `null` values.

When configured to allow cached nulls, for caches extending this class, `toStoreValue(null)` replaces `null` with the internal marker `org.springframework.cache.support.NullValue.INSTANCE`. The native cache actually stores a **non-null** object. On read, `fromStoreValue(NullValue.INSTANCE)` returns `null` to callers using the abstraction. This marker is a **Spring implementation detail**; never return `NullValue.INSTANCE` from a business method or pass that marker across APIs/domains as a special value.

~~~mermaid
flowchart LR
    A[Method returns Java null] --> B[Spring Cache put]
    B --> C{allowNullValues?}
    C -- Yes --> D[toStoreValue: NullValue marker]
    D --> E[Native store writes non-null object]
    E --> F[Native store lookup hit]
    F --> G[fromStoreValue: Java null]
    G --> H[Cache.ValueWrapper.get = null]
    C -- No --> I[Cannot put null per API/provider]
~~~

When nulls are disallowed, attempting `Cache.put(key, null)` may be rejected with an exception; **do not** infer that disabling `allowNullValues` will automatically “silently skip nulls.” If you want to skip nulls, you must decide at the cache operation level, such as by using `unless`.

### Why not store `null` directly in `ConcurrentHashMap`?

`ConcurrentHashMap` forbids null values. Aside from concurrency reasons, the native API returns `null` when no mapping is found. If values could also be `null`, callers could hardly tell “absent” apart from “a stored null.” Spring uses a marker object to store the mapping and uses a wrapper at the abstraction layer to preserve this distinction.

**Do not equate the internal marker with representations in Redis or JCache:** each provider has its own conversion and serialization mechanism. A Redis adapter may serialize a marker into bytes compatible with its codec; an implementation not extending `AbstractValueAdaptingCache` may have a completely different policy. The contract that matters is the behavior of `Cache`, not the object class visible inside the native store.

## 4. Policies across common providers

| Provider / Spring adapter | Notable null policy | How to configure |
| --- | --- | --- |
| `ConcurrentMapCache` / `ConcurrentMapCacheManager` | Manager **allows nulls by default** even though `ConcurrentHashMap` does not; uses an internal holder | `manager.setAllowNullValues(false)` to reject cached nulls |
| `CaffeineCache` / `CaffeineCacheManager` | Manager **allows nulls by default** via Spring's holder; **native Caffeine does not support Java null** | `manager.setAllowNullValues(false)`; in async mode Spring recommends disabling nulls to simplify semantics |
| Spring Data Redis `RedisCacheManager` | `RedisCacheConfiguration.defaultCacheConfig()` **caches nulls by default**; Redis representation depends on serializer | Use `RedisCacheConfiguration.defaultCacheConfig().disableCachingNullValues()` to disable |
| JCache / JSR-107 providers | Depends on adapter, provider, and configuration; do not assume ConcurrentMap behavior | Check the contract, provider-specific null policy, and run integration tests |
| `NoOpCacheManager` | Stores no entries, so there is never an actual cached-null hit | Useful for disabling caching, not as a negative-cache store |

This table describes defaults according to the respective **Spring Framework/Spring Data Redis** documentation, not universal guarantees across every framework integration or already-configured system. Spring Boot auto-configuration may create a `CacheManager` and apply other properties or customizers that alter the final behavior. Always inspect the actual bean used in the live application.

### ConcurrentMapCacheManager

~~~java
@Bean
CacheManager cacheManager() {
    var manager = new ConcurrentMapCacheManager("products", "missingProducts");
    manager.setAllowNullValues(false);
    return manager;
}
~~~

This snippet requires a Spring configuration class, imports, and corresponding bean setup. `setAllowNullValues(false)` configures the manager to **reject nulls** in the `ConcurrentMapCache` instances it manages. Do not assume Spring will silently ignore methods returning `null`: if Spring attempts `put(null)` into a cache that disallows nulls, the operation can throw `IllegalArgumentException`. You must use `unless` when avoiding putting nulls.

Note from the Javadoc: changing the null configuration after caches have already been created can **reset/recreate the caches**, rather than merely flipping a variable without affecting data. Configure it before the system begins using the cache.

### CaffeineCacheManager

~~~java
@Bean
CacheManager caffeineManager() {
    var manager = new CaffeineCacheManager("products");
    manager.setAllowNullValues(false);
    manager.setCacheSpecification("maximumSize=10000,expireAfterWrite=10m");
    return manager;
}
~~~

This snippet requires the Caffeine dependency and appropriate cache setup; the size/TTL values are merely examples. Native Caffeine does not accept `null`, whereas Spring's Caffeine adapter can use a marker if allow-null is enabled. In async cache mode, Spring notes that disallowing nulls makes future-based retrieval semantics simpler and more efficient. **Do not use these numbers as a generic production configuration** without calculating hit rate, memory, cardinality, and invalidation.

### RedisCacheConfiguration

~~~java
RedisCacheConfiguration config =
        RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(2))
            .disableCachingNullValues();

RedisCacheManager manager = RedisCacheManager
        .builder(redisConnectionFactory)
        .cacheDefaults(config)
        .build();
~~~

This snippet requires Spring Data Redis, a `RedisConnectionFactory redisConnectionFactory`, and imports. When Redis is configured **not to cache nulls**, a cache-API `put` with a `null` value will be rejected, which **does not mean automatically deleting an existing key**. In particular, the `disableCachingNullValues()` Javadoc warns: if you put `null`, the command errors, nothing is written, and **an already-existing key retains its old content**. If `null` means “the record has been deleted,” actively `evict` the old key instead of expecting a put-null in disabled mode to clear it.

By default, `RedisCacheConfiguration` caches nulls, prefixes keys with the cache name, and uses its own default serializer; migrating from a local cache to Redis can change value representations, TTL behavior, and how errors surface. Do not use a raw Redis `GET` as the sole yardstick to infer Spring cache hits or misses.

## 5. Annotation policies: allowing, skipping, and updating null

### 5.1. Allowing null results to be stored: negative caching

~~~java
@Cacheable(cacheNames = "productsById", key = "#p0")
public Product findProduct(String id) {
    return repository.findByIdOrNull(id);
}
~~~

If `findByIdOrNull(id)` returns `null`, the provider supports cached nulls, and nothing vetoes it, Spring can store the mapping `key → null`. On the next call with the same key, the cached null **is a hit**, and the method is not invoked again. This is **negative caching**: temporarily remembering a “not found” outcome.

This is useful when non-existent IDs are queried repeatedly—for example, preventing duplicate DB queries or lookups with high miss rates. However, once a new record appears, the cached `null` may keep returning `null` until the TTL expires or it is evicted.

### 5.2. Skipping null storage with `unless`

~~~java
@Cacheable(
    cacheNames = "productsById",
    key = "#p0",
    unless = "#result == null"
)
public Product findProduct(String id) {
    return repository.findByIdOrNull(id);
}
~~~

`unless` is evaluated **after the method has executed on the write path**. If `#result == null`, Spring **does not `put`**. Consequently, a cache provider configuration that forbids nulls can still safely serve that method for the null branch, provided no other operation puts `null` into the same cache.

Note: `unless` does not remove an existing entry. If the key previously held a non-null value and the method was invoked along another path, “skip putting null” does not mean deleting the old entry. When source data is deleted or transitions from present to absent, explicit invalidation with `@CacheEvict` or an equivalent mechanism is required.

### 5.3. `condition` vs. `unless`

| Attribute | When evaluated | Is `#result` available? | Example |
| --- | --- | --- | --- |
| `@Cacheable(condition = ...)` | Before cache lookup/method call, based on inputs | No | `condition="#p0 != null"` |
| `@Cacheable(unless = ...)` | After the method has produced the result to cache | Yes | `unless="#result == null"` |

Do not write `condition="#result != null"` on `@Cacheable` because the method has not executed yet at that point. `condition` can skip caching for overly dynamic inputs, but it is not the way to check for a null output.

### 5.4. `CachePut`, `CacheEvict`, and null values

`@CachePut` is used to **write the method's result** into the cache. If the method returns `null` and the provider rejects nulls, putting can fail; `unless="#result == null"` vetoes the put. Yet when `null` means the record has vanished, merely vetoing the put can leave an old cached value behind. Evict the corresponding entry instead:

~~~java
@CacheEvict(cacheNames = "productsById", key = "#p0")
public void deleteProduct(String id) {
    repository.deleteById(id);
}
~~~

This snippet is used inside a Spring bean and is not a standalone Java file. `@CacheEvict` runs by default after the method completes normally; in transactional applications, check commit timing and transaction-aware cache mechanisms.

**There is no `unless` attribute on `@CacheEvict`**. For eviction you can use `condition`. Placing both `@CachePut` and `@CacheEvict` on the same method requires clearly defining ordering and which entries are modified; it is usually better to keep simple commands and queries separate for easier testing.

## 6. `Optional.empty`, `null`, and wrapper results

Spring Cache supports Java `Optional<T>`. For a method:

~~~java
@Cacheable(cacheNames = "users", key = "#p0")
public Optional<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Spring unwraps supported wrappers for cache handling:

- `Optional.of(user)` → the business value `user` is cached.
- `Optional.empty()` → is treated as a business value of **`null`** at the cache layer.
- Inside `unless`, `#result` refers to **`User` or `null`**, **not** `Optional<User>`.
- On a cache hit with a cached `null` for a method returning `Optional<User>`, Spring adapts the result back to `Optional.empty()` for the caller.

Example when you do not want negative caching:

~~~java
@Cacheable(cacheNames = "users", key = "#p0",
           unless = "#result == null")
public Optional<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Do not write `unless="#result.isEmpty()"`: `#result` is not an `Optional` and can be `null`. When you need to inspect a property on `User`, use SpEL safe navigation `#result?.disabled() == true` and decide separately whether `null` should also be vetoed: `unless="#result == null || #result?.disabled() == true"`.

### Empty collections are not `null`

`Collections.emptyList()`, `List.of()`, empty string `""`, `0`, and `false` are **not** Java `null`. An expression `unless="#result == null"` still allows them to be cached. If business logic does not want to cache empty lists:

~~~java
@Cacheable(cacheNames = "searchResults",
           unless = "#result == null || #result.isEmpty()")
public List<Product> search(String query) {
    return repository.search(query);
}
~~~

This snippet assumes the method returns `List<Product>` (not `Optional<List<Product>>`) and will not throw on `isEmpty` thanks to short-circuiting in the first clause. If using an `Optional` wrapping a list, `#result` is the list or `null`, which should still be handled similarly.

**An exception is not a null result:** a method throwing an error has no successful result to put along the normal path. Do not “cache exceptions as null” unless your code intentionally catches the exception and returns `null`. Distinguish “not found” from “lookup backend failed” to avoid negative-caching transient system failures.

## 7. Runnable Java 17+ example: cached null, vetoed null, and marker in the native store

This Spring Framework example tests four behaviors: caching `null` when allowed by the manager; vetoing `null` with `unless`; caching `Optional.empty()` via adaptation; and using `Cache.ValueWrapper` to distinguish hit-null from miss. It also uses a separate `ConcurrentMapCache` that disallows nulls to show that **put-null is rejected**, rather than silently ignored.

Requirements: JDK 17+, Maven. It uses `spring-context` 7.0.9, a Spring Framework version with the cache abstraction. The code needs no Redis, Caffeine, or external database.

### 7.1. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-null-policy</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>7.0.9</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 7.2. `src/main/java/demo/NullPolicyDemo.java`

~~~java
package demo;

import java.util.Objects;
import java.util.Optional;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.NullValue;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class NullPolicyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        CacheManager cacheManager() {
            var manager = new ConcurrentMapCacheManager(
                    "allowed", "skipped", "optional");
            manager.setAllowNullValues(true);
            return manager;
        }

        @Bean
        LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private int allowedLoads;
        private int skippedLoads;
        private int optionalLoads;

        @Cacheable(cacheNames = "allowed", key = "#p0")
        public String allowMissing(String id) {
            System.out.println("source allowed #" + (++allowedLoads));
            return null;
        }

        @Cacheable(cacheNames = "skipped", key = "#p0",
                   unless = "#result == null")
        public String skipMissing(String id) {
            System.out.println("source skipped #" + (++skippedLoads));
            return null;
        }

        @Cacheable(cacheNames = "optional", key = "#p0")
        public Optional<String> optionalMissing(String id) {
            System.out.println("source optional #" + (++optionalLoads));
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(LookupService.class);
            System.out.println("allow1=" + service.allowMissing("x"));
            System.out.println("allow2=" + service.allowMissing("x"));
            System.out.println("skip1=" + service.skipMissing("x"));
            System.out.println("skip2=" + service.skipMissing("x"));
            System.out.println("optional1=" + service.optionalMissing("x"));
            System.out.println("optional2=" + service.optionalMissing("x"));

            CacheManager manager = context.getBean(CacheManager.class);
            ConcurrentMapCache allowed = (ConcurrentMapCache)
                    Objects.requireNonNull(manager.getCache("allowed"));

            Cache.ValueWrapper absent = allowed.get("never");
            Cache.ValueWrapper presentNull = allowed.get("x");
            System.out.println("absent wrapper=" + (absent == null));
            System.out.println("present-null wrapper=" + (presentNull != null));
            System.out.println("wrapped value null="
                    + (presentNull != null && presentNull.get() == null));
            System.out.println("typed value=" + allowed.get("x", String.class));

            // Only to observe ConcurrentMapCache's internal implementation!
            System.out.println("native uses marker="
                    + (allowed.getNativeCache().get("x") == NullValue.INSTANCE));

            ConcurrentMapCache denied = new ConcurrentMapCache("denied", false);
            try {
                denied.put("x", null);
                System.out.println("unexpected: null accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("direct null rejected=true");
            }
        }
    }
}
~~~

`LookupService` implements no interfaces, so Spring can use a class-based proxy to intercept public non-final methods. `context.getBean(LookupService.class)` is the Spring-managed bean, allowing cache annotations to take effect. Counter fields live on the target and increment only when the business method actually executes.

### 7.3. How to run and stdout

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullPolicyDemo
~~~

Lines printed by the program itself, excluding Maven/Spring secondary logs:

~~~text
source allowed #1
allow1=null
allow2=null
source skipped #1
skip1=null
source skipped #2
skip2=null
source optional #1
optional1=Optional.empty
optional2=Optional.empty
absent wrapper=true
present-null wrapper=true
wrapped value null=true
typed value=null
native uses marker=true
direct null rejected=true
~~~

**Branch-by-branch explanation:**

1. `allowMissing("x")` returns `null` on the first call; the manager allows null caching so it stores the marker; the second call hits and still returns `null`. Hence only `source allowed #1` is printed.
2. `skipMissing("x")` has `unless="#result == null"`, so neither call puts an entry; the counter increments from 1 to 2.
3. `optionalMissing("x")` returns `Optional.empty()`. The cache infrastructure unwraps it to `null` and stores it under the allowed policy; the second call hits and the caller still receives `Optional.empty()`. The counter does not increment again.
4. `allowed.get("never")` returns a `null` wrapper: miss. `allowed.get("x")` returns a non-null wrapper whose wrapped content is `null`: hit-null. `allowed.get("x", String.class)` only returns `null`, without distinguishing miss from hit-null.
5. The native map of **that specific `ConcurrentMapCache`** holds `NullValue.INSTANCE` for key `x`. This observation is for learning how the adapter works, **not a recommended integration API**.
6. The `denied` cache instance forbids nulls; `put("x", null)` throws `IllegalArgumentException` rather than acting as a cache eviction.

**Example limitations:** this is an in-JVM demonstration with `ConcurrentMapCacheManager`, with no TTL, Redis, transactions, or network serializers. The sample program was not actually executed in this document; the output is the expected result per Spring's contract. For production, run tests against your real dependencies and versions.

## 8. Changing `allowNullValues` at runtime can wipe existing caches

With `ConcurrentMapCacheManager`, `setAllowNullValues(boolean)` is generally designed as a configuration **for all caches created by the manager**. The Javadoc notes that changing this setting will **reset existing caches** to reinitialize them under the new policy.

Consequences:

- Do not treat flipping `true → false` as a harmless toggle that preserves all cached entries.
- Do not change the setting at runtime as a way to “clear cached nulls” if that also wipes valid values and causes a load spike.
- Configure the null policy **before traffic arrives**; if migrating, plan cache warm-up and monitor hit ratios.
- With distributed caches, updating Spring configuration on one instance does not automatically change other instances. During a rolling deployment, differing null policies can produce inconsistent results or put failures on some nodes.
- If the serializer or schema for cached nulls changes, version cache names or prefixes when needed. Never share a Redis region among applications decoding markers under incompatible conventions.

Changing the null caching policy can also shift traffic behavior: lookups that used to be negative-cached will begin querying the database repeatedly, or vice versa. Evaluate both correctness and system load.

## 9. Lifecycle of cached nulls and negative caching

When a system caches a “not found” outcome, that entry has the same lifecycle as any regular entry: it can expire via TTL, be evicted, be cleared, be replaced by `@CachePut`, or be refreshed per provider policy.

For example, suppose product `P42` does not exist at 09:00:

1. A `find("P42")` request reads the database and gets `null`.
2. The cache stores `P42 → cached null` for 2 minutes.
3. At 09:30, a process creates `P42`.
4. Without eviction, reads before the cached null expires may keep returning “product does not exist.”
5. After the TTL expires or `@CacheEvict` runs, new reads can see the product.

Here **09:30** is just an example if the TTL is interpreted on a minute scale; in real applications, establish consistent timing and TTLs. The goal is to recognize that cached nulls can go **stale**, rather than being inherently safe just because “they contain no data.”

A sound negative caching policy can be based on:

- **Stability of miss outcomes:** is the ID permanently invalid, or could the entity be created shortly afterward?
- **Source query cost:** do repeated requests for invalid IDs impose significant load?
- **Update/delete frequency:** when an entity is newly created, who owns evicting the exact key?
- **Dedicated TTL:** negative entries often need a TTL matched to staleness risk, potentially shorter than positive entries.
- **Multi-tenancy/authorization:** “not visible” due to missing permissions can differ from “does not exist.” Cache keys must be scoped appropriately, or permission-dependent results must not be cached.
- **Monitoring:** separate hit-null, miss, hit-value, and load success/error metrics if the implementation supports them.

**Do not turn system errors into negative cache entries:** if a downstream service times out, do not blindly catch every exception and return `null` to be cached, because “unable to fetch data” is different from “does not exist.” Error cases should be handled via retries, circuit breakers, error propagation, or an explicit domain status model.

## 10. When the provider forbids nulls: three design options

There is no single answer for every case. Explicitly choose one of three strategies:

| Strategy | Use when | Trade-offs |
| --- | --- | --- |
| **Allow caching nulls via adapter** | Frequent lookups for non-existent keys, provider supports it, and TTL/invalidation fit | Risk of stale negative entries; depends on codec/null-marker config |
| **Skip caching nulls with `unless`** | Null is only a transient miss or negative caching is unwanted | Every miss hits the source; can increase load if invalid IDs are common |
| **Explicit domain result type** such as `LookupResult.NotFound` | Need to distinguish NotFound, Forbidden, Timeout, Deleted, Pending, etc. | More complex design/serialization; must define TTL per status |

With stateful domain results, avoid using `null` to represent every kind of failure. When using sealed interfaces, enums, or records, manage serializer and backward compatibility carefully in distributed caches.

**Specifically for disallow-null configurations:** do not merely flip the manager setting and expect every `@Cacheable` method that returns `null` to keep working smoothly. Ensure they have an appropriate `unless` clause or return a non-null result per contract, and add tests for the null branch.

## 11. Serializers, native stores, and cache data compatibility

One reason to understand value adaptation is that cache providers do not necessarily store raw Java objects directly.

- **ConcurrentMap:** native store in the same JVM; `NullValue.INSTANCE` is a sentinel object. Inspecting the raw map reveals the marker, yet business code must not depend on it.
- **Caffeine:** Spring's adapter can use a similar holder. Native Caffeine itself does not accept null values. In async mode, Spring adds future-based retrieval semantics, so null policies must be tested explicitly.
- **Redis:** data on the wire is bytes; Spring Data Redis uses `RedisCacheConfiguration`/`SerializationPair` to serialize keys and values. Default serialization can behave completely differently from an in-memory cache. A null marker requires a serializer-compatible representation. Do not assume a raw Redis value is the string `"null"` or that deleting/writing null behaves like `Map.put`.
- **JCache:** the adapter follows the provider SPI and its configuration. Do not equate JCache, Spring Caffeine, and native Redis as having one unified raw data format.

Never manually `put` `NullValue.INSTANCE` as a business value, as that leaks an internal marker into the domain and risks breaking conversions. Do not mix multiple serializers or application versions within the same cache region without a compatibility plan; one node may decode a cached null incorrectly or fail deserialization.

Choosing store-by-reference vs. store-by-value also matters: `ConcurrentMapCacheManager` defaults to store-by-reference; enabling store-by-value requires serializable values. This does not make Java `null` a valid native value; cached nulls still use appropriate adaptation when permitted.

## 12. `get`, `get(key, Callable)`, and async retrieval APIs

Beyond the methods already covered, `Cache` also provides:

- `get(key, Callable<T> valueLoader)`: on a miss, invokes the loader to produce the value; the provider may synchronize concurrent loads for the same key if supported. Exceptions from the loader may be wrapped in `Cache.ValueRetrievalException`. A `null` returned by the loader must be compatible with the cache's null policy; it is not skipped by default.
- `retrieve(key)` and `retrieve(key, Supplier<CompletableFuture<T>>)` on async-capable caches: representing hit/miss/null is more complex because a `CompletableFuture`—and sometimes a nested `ValueWrapper`—is involved. The Javadoc distinguishes **early-determined miss** (which can return `null` directly), **late-determined miss** (a future completing with `null`), and nullable cached values.
- `@Cacheable(sync=true)`: asks the provider to coordinate per-key loading on concurrent misses, depending on provider capabilities. It **does not support `unless`**, so you cannot rely on `unless="#result == null"` on this synchronized operation.

Do not assume the rules of `get(key)` apply identically to `retrieve(key)` across every implementation. For async/reactive flows, write dedicated integration tests covering completed-null futures, missing entries, and cancellation/error propagation.

### Reactive/`CompletableFuture` and `null`

Starting in Spring Framework 6.1, cache annotations can adapt `CompletableFuture`, Reactor `Mono`, and `Flux`, yet these types are **not identical** to Java `Optional`. An empty `Mono.empty()` is not simply “`Optional.empty()` cached as null” across every backend or version. Verify the exact publisher semantics, cache retrieval mode, serializer, and behavior when zero elements are emitted. When absence is an important business state, write tests covering cache hits/misses, empty publishers, and exceptional completion.

## 13. Common pitfalls and fixes

**Pitfall 1 — Using typed `get` to check whether an entry exists.** `cache.get(key, Product.class) == null` does not distinguish miss from hit-null. Use `Cache.ValueWrapper wrapper = cache.get(key)`.

**Pitfall 2 — Assuming “provider does not support null” means Spring cannot cache null either.** With `ConcurrentMapCacheManager` and `CaffeineCacheManager`, Spring can adapt nulls via a holder by default. Check the actual configuration instead of looking only at the native provider.

**Pitfall 3 — Thinking `allowNullValues=false` is equivalent to `unless="#result == null"`.** Incorrect: the provider setting rejects put-null, whereas `unless` avoids doing the put. Disabling null support while still putting null can throw an exception.

**Pitfall 4 — Returning `Optional.empty()` while writing `unless="#result.isEmpty()"`.** `#result` is the inner value or `null`; use `#result == null`.

**Pitfall 5 — Failing to evict a cached null when an entity is newly created.** Readers keep seeing the negative cache. Add key-accurate invalidation and an appropriate TTL.

**Pitfall 6 — Changing `CacheManager.setAllowNullValues` at runtime and assuming existing caches stay intact.** The manager may reset caches; plan for warm-up and source load impact.

**Pitfall 7 — Allowing null caching with an incompatible serializer.** Redis/remote stores may fail encoding/decoding, causing cache hits to return wrong values. Test end-to-end and version schemas.

**Pitfall 8 — Using raw native cache APIs to judge Spring Cache correctness.** Adapter markers can make the raw map or Redis display a non-`null` value. Use the `Cache` API and follow the wrapper contract.

**Pitfall 9 — Treating empty collections, `false`, or zero as `null`.** `unless="#result == null"` does not exclude those values. Write policies matching domain semantics.

**Pitfall 10 — Turning timeouts or upstream 500s into `null` and caching them long-term.** The system would then serve fake “not found” responses. Distinguish business `NotFound` from system errors.

**Pitfall 11 — Thinking putting `null` into Redis with null caching disabled deletes the old key.** Per the `disableCachingNullValues` contract, put-null fails and the old key stays untouched. Use explicit eviction.

**Pitfall 12 — Negative caching without authorization scoping.** “No result” for User A is not necessarily true for User B. Scope cache keys/partitions by tenant and permissions whenever they affect the result.

## 14. Pre-production QA checklist

- Can the method return `null`, `Optional.empty()`, an empty collection, or throw an exception? Is each case classified accurately?
- For the running provider, is null support **enabled or disabled**? Does Spring Boot/Redis/Caffeine auto-configuration alter the default?
- On `@Cacheable`, are you using `unless` or accepting negative caching? Have `condition` and `unless` been confused anywhere?
- On a cache hit-null, do clients receive the proper `null`/`Optional.empty()` value? Does the second read truly avoid hitting the DB?
- Does code use `Cache.get(key)` when it must distinguish **miss** from **hit-null**, or does it mistakenly use typed `get`?
- When writing `null` to a cache that disallows it, how does the system handle the exception? Could it cause unintended API failures?
- When an entity is newly created or deleted, is invalidation triggered with the right key, cache name, and transaction timing?
- Do cached nulls have an appropriate TTL and size policy? Is there a cache stampede risk if negative caching is turned off?
- Are serialization and multi-node/multi-version deployments consistent? Could old and new marker formats be mixed?
- Have you tested `ConcurrentMapCache` as well as actual Caffeine/Redis if production uses them, covering null, empty, exception, and async branches?

## 15. Official documentation

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `unless`, `Optional` unwrapping, synchronous and future/reactive support.
- [Spring Framework — Cache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): `Cache.get(Object)`, `ValueWrapper`, typed get, loading, and async retrieval.
- [AbstractValueAdaptingCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/AbstractValueAdaptingCache.html): `allowNullValues`, `toStoreValue`, `fromStoreValue`, `NullValue.INSTANCE`.
- [NullValue Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NullValue.html): internal marker replacing Java null.
- [ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html): default allow-null and reset behavior when settings change.
- [CaffeineCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html): null holder, async cache mode, and configuration.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html) and [RedisCacheConfiguration Javadoc](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheConfiguration.html): defaults/null policy, TTL, serializers, and `disableCachingNullValues`.

**Summary:** In Spring Cache, `null` can be a **cached value**, not necessarily a **cache miss**. `Cache.ValueWrapper` distinguishes the two cases; `AbstractValueAdaptingCache` and provider adapters may use `NullValue` as a marker in the store; and `allowNullValues` together with `unless` govern when `null` is accepted or excluded. Design this alongside TTL/invalidation, serialization, real providers, and thorough data-lifecycle tests.