# Relationship Between Method Invocation, Key, and Cached Result

## 1. Three Components of a Cache Access

In Spring Framework, `@Cacheable` is bound to **a method invocation**. A cache stores a **key → value** mapping inside a named cache. You can picture a stored entry as the tuple:

```text
(cacheName, key) -> cachedValue
```

- **Method invocation** provides the context: the method called through Spring, passed arguments, cache configuration expressions, and execution timing.
- **Key (`key`)** is the identity of the entry to look up in the cache, typically derived from the arguments. The key must reflect all factors that alter the result.
- **Value (`value`)** is the result returned by the method after a successful execution and accepted by the cache for storage. On a cache hit, Spring returns this value without running the method body.

For example, if `describe("p-1", "vi")` returns the Vietnamese description of a product, a proper design is:

```text
cacheName = descriptions
key       = "p-1:vi"
value     = "Vietnamese description of p-1"
```

Calling again with the same key can retrieve the same value; calling `describe("p-1", "en")` must use a different key because the English content differs. **Method name, class name, and return type are not automatically part of the default key**. Cache names separate key spaces: `descriptions["p-1:vi"]` and `prices["p-1:vi"]` are two entries in two different caches.

## 2. How Does Spring Process a `@Cacheable` Call?

Suppose we have the declaration:

```java
@Cacheable(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
public String describe(String productId, String language) {
    return loadFromDatabase(productId, language);
}
```

This is an **illustrative snippet** where `loadFromDatabase` represents a data read operation; the complete runnable example is in section 5.

Typical flow when a call passes through Spring's cache proxy:

1. Spring identifies the cache named `descriptions` and computes the key from the arguments—here `productId + ":" + language`.
2. Spring looks up the value at that key. If it is a **hit** (a matching entry exists), the result is returned immediately; `loadFromDatabase` does not run.
3. If it is a **miss**, Spring invokes the actual method, obtains the result, and attempts to store the result under the computed key (unless a condition/veto forbids storing or the backend raises an error).
4. The result of the current call is returned to the caller. Subsequent calls with the same cache and key can hit.

```text
Caller
  |
  v
Spring cache interceptor
  |-- resolve cacheName + key
  |-- cache.get(key)
  |       |-- HIT  -> return cachedValue, skip method body
  |       '-- MISS -> run method body -> obtain result
  |                              |-- eligible -> cache.put(key, result)
  |                              '-- return result
  '-- return to Caller
```

Two calls with **equal arguments under the key-generation strategy** can share a cache entry; two calls to the same method name that produce different keys have independent entries. Conversely, **having the same key does not guarantee the value still matches current source data**: cache freshness depends on update, eviction, and expiration mechanisms.

## 3. Where Do Default Keys Come From?

When neither `key` nor a custom `keyGenerator` is specified, Spring uses `SimpleKeyGenerator`. Rules in modern Spring Framework:

| Number of Method Arguments | Default Key |
| --- | --- |
| No arguments | `SimpleKey.EMPTY` |
| One non-`null`, non-array argument | That argument itself |
| One `null` or array argument | `SimpleKey` wrapping that argument |
| Two or more arguments | A `SimpleKey` containing the arguments in order |

Examples with `@Cacheable("examples")`:

- `find()` → key `SimpleKey.EMPTY`.
- `find("A")` → key `"A"`.
- `find("A", "vi")` → key `SimpleKey["A", "vi"]`; changing argument order or values produces a different key.

Important consequences:

- **Method name is not automatically added to the key.** If `findById("A")` and `findDescription("A")` share the cache `examples` and both use the default key `"A"`, they can collide and return the wrong type or content. Use distinct cache names or construct appropriately namespaced keys.
- When an argument is an object, key stability depends on `equals()`/`hashCode()`. An object whose fields mutate after being cached can make the key unretrievable reliably, especially in hash-based caches.
- Two instances representing the same business identifier can produce two different keys if the object does not define value-based equality. Prefer immutable IDs in keys over entire entities.
- Distributed backends may serialize or convert keys; do not assume every key object type works out of the box on Redis, JCache, or other caches.

**Note:** key selection is based on **incoming arguments**, not on the method's computed result. For explicit keys, use SpEL `key = "#p0"`, `key = "#p0 + ':' + #p1"`, or a custom `KeyGenerator`. `#p0`/`#a0` is the first argument, `#p1`/`#a1` is the second; names like `#productId` work only when parameter names are preserved for Spring to read.

## 4. Designing Keys Around Result Semantics

Suppose the result has the form:

```text
description = f(productId, language, tenantId, dataVersion)
```

If `language` or `tenantId` actually affects the content, omitting them from the key can cause users to receive the wrong language or another tenant's data. If `dataVersion` is managed via cache eviction after updates, including version in the key is not strictly required; the essential point is having a consistent strategy to keep data valid.

| Design Choice | Consequence |
| --- | --- |
| `key = "#p0"` for `describe(id, language)` | Different languages for the same ID share a key: easily returns the wrong description |
| `key = "#p0 + ':' + #p1"` | Both ID and language affect the key; suitable for example data |
| `key = "#p0 + #p1"` | Ambiguous string concatenation possible: `("ab","c")` and `("a","bc")` both become `"abc"` |
| `key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)"` | Keeps both key components distinct without relying on delimiters |

In production systems, consider adding schema version, tenant, access permissions, or filters **if they affect the result**. Do not place secrets/tokens in keys or logs; avoid keys containing large or constantly mutating objects. Even with the same key, TTL, eviction, and memory policies are still governed by the cache provider.

## 5. Runnable Java 17+ Example: Observing Hit, Miss, and Return Values

This example uses Spring Boot 3.3.5, Java 17+, Maven, `@EnableCaching`, and `ConcurrentMapCacheManager` (in-process memory cache). Structure:

```text
cache-demo/
├── pom.xml
└── src/main/java/example/cache/
    ├── CacheDemoApplication.java
    └── ProductService.java
```

**`pom.xml`**

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
    <artifactId>cache-demo</artifactId>
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

**`src/main/java/example/cache/CacheDemoApplication.java`**

```java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("descriptions");
    }

    @Bean
    CommandLineRunner runDemo(ProductService service) {
        return args -> {
            System.out.println(service.describe("p-1", "vi"));
            System.out.println(service.describe("p-1", "vi"));
            System.out.println(service.describe("p-1", "en"));
            System.out.println(service.describe("p-1", "vi"));
        };
    }
}
```

**`src/main/java/example/cache/ProductService.java`**

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final AtomicInteger databaseLoads = new AtomicInteger();

    @Cacheable(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
    public String describe(String productId, String language) {
        int loadNumber = databaseLoads.incrementAndGet();
        return "load#" + loadNumber + " [" + productId + "," + language + "]";
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

The four lines printed by `CommandLineRunner` (excluding Spring Boot startup logs):

```text
load#1 [p-1,vi]
load#1 [p-1,vi]
load#2 [p-1,en]
load#1 [p-1,vi]
```

Explanation of each call:

| Call | SpEL Key | Hit/Miss | Actual Method Runs? | Result |
| --- | --- | --- | --- | --- |
| `describe("p-1","vi")` call 1 | `p-1:vi` | Miss | Yes, increments counter to 1 | `load#1 [p-1,vi]` |
| `describe("p-1","vi")` call 2 | `p-1:vi` | Hit | No | Reuses `load#1 [p-1,vi]` |
| `describe("p-1","en")` | `p-1:en` | Miss | Yes, increments counter to 2 | `load#2 [p-1,en]` |
| `describe("p-1","vi")` call 3 | `p-1:vi` | Hit | No | Reuses first result |

The example deliberately uses a counter instead of a database to distinguish **method execution** from **returning a cached result**. The value `load#1` does not mean the cache recomputes results; it is simply the stored value from the first invocation. `ConcurrentMapCacheManager` exists only in-process and loses data when the application stops; the example does not demonstrate cache sharing across multiple instances.

## 6. When Data Changes: Is the Cached Result Still Valid?

Suppose the description in the data source changes from `"Old version"` to `"New version"`. If entry `descriptions["p-1:vi"]` remains, the next read may still return `"Old version"` without invoking the method. Therefore, you must define **when to update or evict keys**.

Common annotations:

- `@Cacheable`: prefers reading from cache; invokes the method and caches the result on a miss.
- `@CachePut`: **always invokes** the method, then uses the return value to update the cache under the configured key. Suitable when the write operation also returns the exact data to cache.
- `@CacheEvict`: removes an entry by key; by default deletes **after the method completes successfully**. `allEntries = true` clears all entries in the corresponding cache; `beforeInvocation = true` performs eviction before the call.
- `@Caching`: groups multiple cache operations on a single method; check ordering and conflicts carefully.

Example declaration on a data-updating method (this is only an **illustrative snippet**; you must supply your own data store):

```java
@CacheEvict(cacheNames = "descriptions", key = "#p0 + ':' + #p1")
public void updateDescription(String productId, String language, String newText) {
    repository.save(productId, language, newText);
}
```

When `("p-1","vi")` is updated successfully, entry `p-1:vi` is removed; the next `describe("p-1","vi")` call misses and reads fresh data. **The key of the write/evict operation must match the key of the read operation** (same cache name, same argument order and components). Do not combine `@CachePut` and `@Cacheable` on the same method just hoping to force execution while skipping execution: the two goals conflict and behave unpredictably.

For data that can be modified by another service, annotation operations in one application are insufficient to ensure other nodes refresh automatically. TTL, pub/sub, distributed invalidation, or versioned keys are design decisions at the provider/system level.

## 7. Conditions and Cases Where Results Are Not Stored

Two easily confused attributes of `@Cacheable`:

```java
@Cacheable(
    cacheNames = "descriptions",
    key = "#p0 + ':' + #p1",
    condition = "#p1 != 'debug'",
    unless = "#result == null"
)
public String describe(String productId, String language) {
    // Read actual data; method body only runs when needed.
    return loadFromDatabase(productId, language);
}
```

*The snippet above illustrates annotations, not a standalone runnable program.*

- `condition` is evaluated **before looking up the cache**. When the expression is false, the call goes straight to the actual method without reading from or writing to the cache per this annotation.
- `unless` is evaluated **after the method produces a result** and can use `#result` to veto caching. It does not cause a cache hit to re-invoke the method.
- When a method throws an exception, by default that is not a result value for `@Cacheable` to store. Whether `null`/`Optional.empty()` is accepted for storage and how it is represented depends on cache type, configuration, and provider support; avoid assuming all caches behave identically.

Even a correct cache key does not guarantee a result will be stored: you must also account for `condition`, `unless`, provider state, eviction, and expiration.

## 8. Proxies, Execution Timing, and Common Misconceptions

**Proxy:** In the default mode, cache advice operates when calls go **through a Spring-managed proxy**. Calling directly from another method **in the same object** via `this.describe(...)` typically bypasses the cache interceptor. The runnable example above obtains `ProductService` via dependency injection so interception applies; instantiating `new ProductService()` manually will not activate annotations either. Prefer placing annotations on `public` methods of Spring beans and invoking them from other beans via injection. `@EnableCaching` or equivalent configuration is required.

**Concurrency:** Two requests missing the same key together may both run the query before the cache entry is populated. `@Cacheable(sync = true)` requests coordinated value loading for the same key when supported by the provider, but has restrictions (single cache, no `unless`, cannot combine with other cache operations) and does not replace distributed locks or transactions.

**Transactions and fresh data:** If a source data update has not committed yet while the cache has already put/evicted, an inconsistency window can occur. Design invalidation timing around transaction boundaries; Spring Cache does not automatically make stored results always consistent.

**Cache loss:** Restarts, TTL, capacity limits, or eviction can turn an expected hit into a miss. The result on a miss may differ because the source changed, even for the exact same key.

**Multiple methods:** Two different methods using the same cache name and generating the same key can reference the same entry. If data/return types are incompatible, that is a key/cache-name design bug. Avoid using one vague shared cache merely because methods all relate to products.

## 9. Design Review Checklist and Common Bug Signs

When reviewing a method annotated with `@Cacheable`, answer in order:

1. **Which cache?** Which storage space do `cacheNames`/`CacheManager` select?
2. **Which key?** Which arguments are used by default, or is there custom SpEL/`KeyGenerator`? Do ID, locale, tenant, filters, or version affect the value?
3. **What does a miss do?** Which expensive I/O or computation runs; is the expected result safe to reuse?
4. **What does a hit return?** Could users receive old values when source data has changed?
5. **When is it refreshed?** Do data writes have `@CachePut`/`@CacheEvict` with the **exact same key**? Is there TTL or cross-node invalidation?
6. **Does the interceptor run?** Is the method on a Spring bean, public, and called through a proxy rather than self-invocation?
7. **Are there uncached cases?** Check `condition`, `unless`, null/exceptions, and provider support.

Typical bug symptoms:

- Omitting `language`/`tenantId` from the key when results depend on them → data leaks or wrong data returned.
- Keys built by unseparated string concatenation or objects with mutating `hashCode()` → collisions or unexpected misses.
- Reads use `"p-1:vi"` while evicts use `"p-1"` → wrong key deleted, stale data keeps being returned.
- Assuming `@Cacheable` always calls the method to check for fresh data → in reality hits skip the method.
- Assuming annotations take effect when calling `this.method()` → default proxies do not intercept internal calls.
- Assuming local caches sync automatically across instances or expire on their own → depends on specific backend and configuration.

## 10. Knowledge Self-Check

**Scenario A.** `getPrice("A", "VND")` and `getPrice("A", "USD")` both use key `"A"`. If prices differ by currency, what is wrong?

Answer: Both calls share a single cache entry despite different outputs; include currency in the key or separate caches by context.

**Scenario B.** `getPrice("A", "VND")` queries the database on call 1 and does not on call 2. Then the database changes the price without evicting. What does call 3 return?

Answer: It may still return the price cached on call 1; the matching key causes a hit. To get the new price, update/evict the entry or let it expire per provider policy.

**Scenario C.** Two methods each take one `"A"` argument, share `cacheNames = "items"`, and specify no `key`. Are they always independent?

Answer: No. By default, a single argument produces `"A"` itself as the key; if two methods share a cache, they risk sharing the same entry. Method name is not automatically included in the key.

**Scenario D.** Why did the `CommandLineRunner` example output load#1, load#1, load#2, load#1?

Answer: Calls 1 and 3 missed due to two different keys; calls 2 and 4 hit key `p-1:vi` and therefore returned the stored result from call 1.

## References

- Spring Framework — Cache Abstraction, especially `@Cacheable`, Default Key Generation, and Conditional Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `@Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html