# ConcurrentMapCache and ConcurrentMapCacheManager

> **Context:** Spring Framework Cache — **In-Memory Cache** group. This lesson explains the two classes `ConcurrentMapCache` and `ConcurrentMapCacheManager`, how they create and manage local cache regions, as well as important differences regarding cache names, null values, mutability, concurrency, and data lifecycle. Examples are written for Java 17 and Spring Framework 6.2.x.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Distinguish **a cache region holding key/value entries** from **an object that manages multiple cache regions**.
2. Use `CacheManager.getCache(name)` and the `Cache.get`, `put`, `evict`, and `clear` APIs.
3. Compare `ConcurrentMapCacheManager` in **dynamic** and **static** modes.
4. Understand why `ConcurrentMapCache` allows cached null values even though `ConcurrentHashMap` does not accept null directly.
5. Recognize the default **store-by-reference**, the optional **store-by-value**, and the consequences of storing mutable data.
6. Demonstrate hit/miss/eviction and updates with `@CachePut` through a real Spring application.
7. Explain the limitations: **no built-in TTL/TTI/size-eviction**, **no cache sharing across JVMs**, and **no persistence across restarts**.
8. Know when Spring Boot uses the Simple provider and when to choose Caffeine/Redis.

## 2. Role of the Two Classes in Spring Cache

```text
Client
  |
  v
Spring-managed Service Bean / AOP Proxy
  |
  v
Spring Cache Interceptor (@Cacheable, @CachePut, @CacheEvict)
  |
  v
ConcurrentMapCacheManager
  |                          (one manager has multiple Caches)
  +--- "books"  ---> ConcurrentMapCache("books")
  |                   B1 --> Book(...)
  |                   B2 --> Book(...)
  |
  +--- "prices" ---> ConcurrentMapCache("prices")
                      P1 --> Price(...)
```

- **`Cache`** is the abstraction for a key/value storage region. It provides operations such as `get`, `put`, `evict`, and `clear`.
- **`ConcurrentMapCache`** is a simple `Cache` implementation based on JDK concurrent structures, using `ConcurrentHashMap` by default.
- **`CacheManager`** is the higher-level abstraction, providing `getCache(String name)` and `getCacheNames()`.
- **`ConcurrentMapCacheManager`** creates and manages `ConcurrentMapCache` instances by name.
- **`@Cacheable`** applies a result-reuse policy to method invocations, but only when the Spring cache interceptor is enabled and the call goes through an appropriate proxy.

A cache named `books` in **JVM A** does not automatically link to the `books` cache in **JVM B**. The same name refers to the same logical region **within a single manager/context**, not a distributed store.

## 3. ConcurrentMapCache: Basic Operations

Full class name:

```java
org.springframework.cache.concurrent.ConcurrentMapCache
```

A `ConcurrentMapCache` object provides behaviors such as:

| API | Basic Behavior |
| --- | --- |
| `get(key)` | Looks up an entry, returns `Cache.ValueWrapper` if present; null when there is no entry |
| `get(key, Class<T>)` | Reads the value with the expected type |
| `put(key, value)` | Sets or replaces the value for a key |
| `putIfAbsent(key, value)` | Only sets when the key does not exist yet via an atomic map operation |
| `evict(key)` | Removes a single key |
| `clear()` | Removes all entries in that cache |
| `get(key, Callable<T>)` | Looks up or uses a loader to compute on miss; capable of coordinating computation for the same key |

Example **illustrative code snippet** inside a method that already has `CacheManager cacheManager`:

```java
Cache cache = cacheManager.getCache("books");
if (cache == null) {
    throw new IllegalStateException("Missing books cache");
}

cache.put("B1", "Spring Framework");
System.out.println(cache.get("B1").get()); // Spring Framework

cache.evict("B1");
System.out.println(cache.get("B1"));       // null
```

With the direct cache API, the application calls `put` or `evict` itself. With `@Cacheable`, the Spring interceptor performs the lookup and result storage on your behalf based on the configured cache name/key.

**Do not confuse a thread-safe map with business-level thread safety.** The map has thread-safe concurrent access operations, but a sequence like "read DB -> modify data -> write cache" is not inherently an atomic transaction. A cached mutable object also does not automatically synchronize content modifications.

## 4. ConcurrentMapCacheManager: Two Cache Name Modes

Full class name:

```java
org.springframework.cache.concurrent.ConcurrentMapCacheManager
```

### 4.1. Dynamic — Create Cache Regions on Demand

```java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();

Cache a = manager.getCache("books");
Cache b = manager.getCache("prices");
```

The **no-arg** constructor enables dynamic mode. The first `getCache("books")` call creates a `ConcurrentMapCache`, and subsequent calls reuse the created cache. `getCacheNames()` lists the regions known to the manager at the time of inspection.

Advantage: convenient for demos or dynamically requested cache names. Disadvantage: a typo like `"bokos"` can **silently create another cache region** instead of reporting an invalid name.

### 4.2. Static — Allow Only Predefined Names

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books", "prices");

System.out.println(manager.getCache("books") != null);  // true
System.out.println(manager.getCache("unknown") != null); // false
```

The constructor with names only allows that set of caches. If a `@Cacheable(cacheNames = "unknown")` requests a cache that does not exist, a cache resolution error may occur **at the time the method is called**, rather than immediately at application startup.

Static mode is useful when cache names are a fixed contract and you want to catch configuration errors.

### 4.3. setCacheNames and Reset

```java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();
manager.setCacheNames(java.util.List.of("books", "prices"));
manager.setCacheNames(null); // switch back to dynamic mode
```

According to the JavaDoc, `setCacheNames` may replace caches with the same name and does not automatically remove all existing caches with other names. `resetCaches()` has the corresponding reset behavior. Because changing manager configuration can affect data currently held, it is best to **finalize the mode at initialization** and not switch modes repeatedly in production.

## 5. Cache Hit and Cache Miss via @Cacheable

Consider the illustrative method:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return repository.load(isbn);
}
```

The snippet requires a Spring bean, a repository, and a `Book` class to run. When the application has `@EnableCaching` enabled and calls the method through a Spring proxy:

1. Spring builds the key from the first argument (`#p0`).
2. The interceptor retrieves the `books` cache from the manager.
3. **Miss:** executes the body of `find`, calls the repository, and stores the result if the policy allows.
4. **Hit:** returns the stored value and **does not execute the method body again**.
5. With a different key or after `evict`, a miss can occur again.

| Sequential Call | Key | Expected (initially empty cache) | Total Body Executions |
| --- | --- | --- | --- |
| `find("B1")` | B1 | Miss | 1 |
| `find("B1")` | B1 | Hit | 1 |
| `find("B2")` | B2 | Miss | 2 |
| `find("B1")` | B1 | Hit | 2 |
| `evict("B1"); find("B1")` | B1 | Miss after eviction | 3 |

The table assumes the loader succeeds, there is no `condition`/`unless` excluding caching, and all calls go through the proxy. To verify, place an `AtomicInteger` inside the method body or repository; counting in a controller only measures client call counts.

### Self-Invocation Pitfall

In the default proxy mode, a method inside the same bean calling `this.find("B1")` usually bypasses the cache interceptor. Similarly, instantiating `new BookService()` outside Spring does not activate annotations. When testing, retrieve the service via `ApplicationContext.getBean(...)` or inject it into another bean.

## 6. Null Values: Difference Between Cached Null and Cache Miss

Java's `ConcurrentHashMap` does not allow the map to hold null values directly. However, `ConcurrentMapCacheManager` has `allowNullValues = true` by default: `ConcurrentMapCache` encodes user-level null using an **internal placeholder value**.

Example:

```java
Cache cache = manager.getCache("books");
cache.put("not-found", null);

Cache.ValueWrapper never = cache.get("never-created");
Cache.ValueWrapper noBook = cache.get("not-found");

System.out.println(never == null);          // true: miss
System.out.println(noBook != null);         // true: entry exists
System.out.println(noBook.get() == null);   // true: cached null
```

This is an illustrative snippet inside a method that already has the manager and imports. Key distinction:
- **Miss**: `cache.get(key) == null`, no `ValueWrapper`.
- **Hit with null**: a `ValueWrapper` is present, but `wrapper.get() == null`.

`cache.get(key, Book.class)` can return null both on a miss and when the cached value is null, so if you need to distinguish whether **an entry exists or not**, use the wrapper form.

### Disabling Null Value Storage

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
manager.setAllowNullValues(false);
```

In that case, `put(key, null)` may not be accepted. If you want **not to cache null results** via Spring annotations:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book find(String isbn) {
    return repository.load(isbn);
}
```

This is a different approach from allowing null caching by default. Note: `@Cacheable(sync = true)` does not support `unless`; do not combine them to "fix" null caching. A null **key** is also a different issue from a null **value**; allowing null values does not mean every expression that generates a null key will be accepted.

According to the JavaDoc, changing `allowNullValues` may reset already-created caches to apply the new policy. Configuration should be decided before the system serves requests.

## 7. Default Store-by-Reference and Optional Store-by-Value

The manager has a `storeByValue` property:
- `false` (default): stores **object references**, does not require `Serializable`.
- `true`: stores copies via serialization; values must be serializable, incurring CPU/memory overhead and type constraints.

### Risk of Using Mutable Objects

```java
List<String> tags = new ArrayList<>(List.of("java"));
cache.put("B1-tags", tags);

tags.add("spring");

@SuppressWarnings("unchecked")
List<String> cached =
        (List<String>) cache.get("B1-tags").get();

System.out.println(cached); // [java, spring]
```

This illustrative snippet requires importing `List` and `ArrayList`, assuming the default store-by-reference cache. The caller mutating the object after `put` causes the cached content to change **without a new put operation**. Other requests sharing the same reference can be affected, especially under concurrent threads.

**Practical options:** use immutable records/DTOs, defensive copies for collections, or store-by-value when object isolation is truly needed and all values are serializable.

```java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books");
manager.setStoreByValue(true);
```

**Store-by-value is not persistence.** Even though serialization is used to create copies, the cache remains in the memory of the current JVM. Upon restart, entries are still lost. Changing this mode on a manager that already holds data may also reset caches to reconfigure them.

## 8. Lifecycle, Capacity, and Distribution Limitations

`ConcurrentMapCache` is suitable for experimentation or simple caching, but according to Spring Framework it **does not provide a built-in expiration/eviction contract** like dedicated providers.

| Requirement | Default ConcurrentMapCache |
| --- | --- |
| TTL (expiration after a duration from write) | **Not built-in** |
| TTI (expiration due to inactivity) | **Not built-in** |
| maximumSize/size-based eviction | **Not built-in** |
| Manually remove a single key | Has `evict(key)` |
| Manually clear an entire cache | Has `clear()` |
| Persistence across JVM restarts | No |
| Share values across multiple JVM instances | No |
| Map supporting concurrent access | Yes |
| Atomic transaction between database and cache | Not automatically guaranteed |

Important consequences:
- A key may **remain indefinitely** if not updated/evicted; do not expect it to expire automatically after 10 minutes.
- Memory grows with entry count, value types, and cache names; continuously growing keys can cause heap pressure.
- If the data source is updated without cache invalidation, the cache can return **stale values**.
- Two instances A/B hold separate cache copies; evicting on A does not automatically evict on B.
- Dynamically created caches with misspelled names can create unwanted regions.

If you need TTL, size limits, or telemetry, consider **Caffeine**. If you need to share cached data across multiple instances, consider **Redis** with appropriate invalidation, key, and serialization strategies.

## 9. Spring Boot and Simple Cache

Spring Boot can auto-configure the **Simple** cache backed by `ConcurrentHashMap` when caching is enabled and no other provider is selected. You can specify explicitly:

```properties
spring.cache.type=simple
spring.cache.cache-names=books,prices
```

This is an `application.properties` example:
- `spring.cache.type=simple` requests the Simple type in Boot's cache auto-configuration branch.
- `spring.cache.cache-names=books,prices` restricts valid cache names under that configuration.
- When the application uses a name `unknown` not in the list, an error typically occurs **when the cache is requested**, not necessarily at startup.
- If a custom `CacheManager`/`CacheResolver` bean is declared, Boot's auto-config may not choose the manager from properties. Always verify the actual bean type.

Common dependency in a POM with a Spring Boot parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
```

This is a **dependency snippet**, not a full POM. For caching annotations to work, `@EnableCaching` is still required. With Boot, let the parent/BOM manage Spring module versions.

**Distinction:**
- `spring.cache.type=simple` -> stores values using the Simple cache.
- `spring.cache.type=none` -> no-op cache, **does not store**.
- `SimpleCacheManager` is a class that can manage manually registered `Cache` instances; it is **not synonymous** with Boot's "simple" option name in every design.

## 10. Standalone Java 17 Example: Hit, Stale, Evict, Put, and Cache Names

The demo uses **Spring Framework 6.2.16**, Maven, and JDK 17+, without needing a database/Redis/Caffeine. The data source is simulated by a separate `ConcurrentHashMap`; this is sufficient to demonstrate the difference between **source data** and **Spring-managed cache**.

### 10.1. Directory Structure

```text
concurrent-map-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheDemo.java
    └── test/java/demo/cache/CacheDemoTest.java
```

### 10.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>concurrent-map-cache-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the Spring Cache abstraction, annotations, and ConcurrentMap cache implementation; transitive dependencies are resolved automatically by Maven. JUnit 5 is used for direct verification. This is a plain Spring Framework program, not relying on Boot's cache auto-configuration.

### 10.3. `src/main/java/demo/cache/CacheDemo.java`

```java
package demo.cache;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheDemo {

    public record Book(String isbn, String title) {}

    public static class BookRepository {
        private final Map<String, Book> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public BookRepository() {
            data.put("B1", new Book("B1", "Spring Basics"));
        }

        public Book load(String isbn) {
            reads.incrementAndGet();
            return data.get(isbn);
        }

        public Book save(String isbn, String title) {
            Book book = new Book(isbn, title);
            data.put(isbn, book);
            return book;
        }

        public int readCount() {
            return reads.get();
        }
    }

    public static class BookService {
        private final BookRepository repository;

        public BookService(BookRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "books", key = "#p0")
        public Book find(String isbn) {
            return repository.load(isbn);
        }

        @CachePut(cacheNames = "books", key = "#p0")
        public Book rename(String isbn, String title) {
            return repository.save(isbn, title);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookRepository bookRepository() {
            return new BookRepository();
        }

        @Bean
        public BookService bookService(BookRepository repository) {
            return new BookService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(BookService.class);
            var repository = context.getBean(BookRepository.class);
            CacheManager manager = context.getBean(CacheManager.class);

            System.out.println("manager="
                    + manager.getClass().getSimpleName());
            System.out.println("staticBooks="
                    + (manager.getCache("books") != null));
            System.out.println("staticUnknown="
                    + (manager.getCache("unknown") != null));

            System.out.println("first="
                    + service.find("B1").title());
            System.out.println("second="
                    + service.find("B1").title());
            System.out.println("reads1="
                    + repository.readCount());

            // Simulate the data source being updated outside the cache advice.
            repository.save("B1", "Changed Outside Cache");
            System.out.println("stale="
                    + service.find("B1").title());

            Cache cache = Objects.requireNonNull(
                    manager.getCache("books"));
            cache.evict("B1");

            System.out.println("afterEvict="
                    + service.find("B1").title());
            System.out.println("reads2="
                    + repository.readCount());

            service.rename("B1", "Updated Through Service");
            System.out.println("afterPut="
                    + service.find("B1").title());
            System.out.println("reads3="
                    + repository.readCount());

            // Default allowNullValues=true.
            cache.put("ABSENT", null);
            Cache.ValueWrapper wrapper = cache.get("ABSENT");
            System.out.println("cachedNull="
                    + (wrapper != null && wrapper.get() == null));
            System.out.println("missingNull="
                    + (cache.get("NEVER") == null));

            var dynamic = new ConcurrentMapCacheManager();
            System.out.println("dynamicBefore="
                    + dynamic.getCacheNames().contains("adHoc"));
            dynamic.getCache("adHoc");
            System.out.println("dynamicAfter="
                    + dynamic.getCacheNames().contains("adHoc"));
        }
    }
}
```

### 10.4. Run and Compare stdout

Requires Java 17+, Maven 3.9+, and a connection to Maven Central on the first run. In the `concurrent-map-cache-demo` directory, run:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program**, excluding Maven's or Spring's own logs:

```text
manager=ConcurrentMapCacheManager
staticBooks=true
staticUnknown=false
first=Spring Basics
second=Spring Basics
reads1=1
stale=Spring Basics
afterEvict=Changed Outside Cache
reads2=2
afterPut=Updated Through Service
reads3=2
cachedNull=true
missingNull=true
dynamicBefore=false
dynamicAfter=true
```

Reading the output:
1. The static manager has `books` but does not recognize `unknown`.
2. Two `find("B1")` calls result in only **one `repository.load` invocation**, proving a cache hit.
3. The repository is modified directly; the cache has not received invalidation, so `stale` still returns the old title.
4. `cache.evict("B1")` removes the entry; the next read misses, increasing `reads2` to 2.
5. `@CachePut` on the `rename` method refreshes the cache with the newly updated `Book`; reading again does not need to load from the source, so `reads3` stays at 2.
6. A cached null has a wrapper, while a nonexistent key causes `get` to return null.
7. The dynamic manager creates the `adHoc` region on demand.

The example only verifies a single-threaded JVM. It does not prove TTL, multi-node consistency, or handled DB/cache transactions.

## 11. JUnit 5 Testing

Create `src/test/java/demo/cache/CacheDemoTest.java`:

```java
package demo.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CacheDemoTest {

    @Test
    void hitEvictionAndPutWorkWithOneCacheKey() {
        try (var context = new AnnotationConfigApplicationContext(
                CacheDemo.Config.class)) {

            var service = context.getBean(CacheDemo.BookService.class);
            var repository = context.getBean(CacheDemo.BookRepository.class);
            CacheManager manager = context.getBean(CacheManager.class);

            assertEquals("Spring Basics", service.find("B1").title());
            assertEquals("Spring Basics", service.find("B1").title());
            assertEquals(1, repository.readCount());

            repository.save("B1", "New Source Title");
            assertEquals("Spring Basics", service.find("B1").title());

            Cache cache = Objects.requireNonNull(
                    manager.getCache("books"));
            cache.evict("B1");

            assertEquals("New Source Title", service.find("B1").title());
            assertEquals(2, repository.readCount());

            service.rename("B1", "Put Title");
            assertEquals("Put Title", service.find("B1").title());
            assertEquals(2, repository.readCount());
        }
    }

    @Test
    void namesAreStaticOrCreatedDynamically() {
        var fixed = new ConcurrentMapCacheManager("books");
        assertNotNull(fixed.getCache("books"));
        assertNull(fixed.getCache("unlisted"));

        var dynamic = new ConcurrentMapCacheManager();
        assertFalse(dynamic.getCacheNames().contains("adHoc"));
        assertNotNull(dynamic.getCache("adHoc"));
        assertTrue(dynamic.getCacheNames().contains("adHoc"));
    }

    @Test
    void cachedNullIsNotTheSameAsCacheMiss() {
        var manager = new ConcurrentMapCacheManager("books");
        Cache cache = Objects.requireNonNull(manager.getCache("books"));

        assertNull(cache.get("NEVER"));
        cache.put("ABSENT", null);

        Cache.ValueWrapper wrapper = cache.get("ABSENT");
        assertNotNull(wrapper);
        assertNull(wrapper.get());
    }
}
```

Run:

```bash
mvn -q test
```

JUnit is expected to succeed with exit code 0. When running `mvn -q`, Maven may not print "BUILD SUCCESS". The assertions confirm: hits avoid loading from the source, the cache becomes stale when the source changes, eviction causes a miss, `put` refreshes the right key, static/dynamic modes behave differently, and a cached null has a wrapper. Each test has its own context/manager so it does not depend on test order.

**Note:** this tests caching with a real Spring `ApplicationContext`, not a unit test using `new BookService(...)` that bypasses annotations. If you want to test TTL or distributed caching, you must use an appropriate provider and a dedicated test suite.

## 12. ConcurrentMap, Concurrency, and @Cacheable(sync = true)

`ConcurrentMapCache` uses `ConcurrentHashMap`, so map operations are thread-safe, but **by default** multiple threads seeing a miss concurrently can all execute the method body. There is no guarantee of a single loader invocation merely by placing `@Cacheable`.

Illustrative read method example:

```java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public Book findSlowly(String isbn) {
    return repository.load(isbn);
}
```

`sync = true` asks the provider to coordinate the loader for a cache key experiencing a miss. `ConcurrentMapCache` has a `get(key, Callable)` mechanism that uses atomic per-key computation in the map, making it suitable for illustrating this within a single JVM. However, this is **not a distributed lock**. In addition, Spring restricts `sync=true`: single cache only, no `unless`, and cannot be combined with other cache operations on the same method.

Do not use this illustrative snippet to conclude that all providers or distributed environments guarantee exactly-once execution. For concurrency testing, use multiple threads/barriers and measure how many times the body executes.

## 13. When Should You Switch to Another Provider?

| Option | Where is data stored? | TTL/size policy | Multi-JVM sharing | Use when |
| --- | --- | --- | --- | --- |
| `ConcurrentMapCacheManager` | Local map in JVM | No built-in expiry/capacity policy | No | Demos, tests, small apps, or simple caching |
| `CaffeineCacheManager` | Local JVM | Has `maximumSize`, `expireAfterWrite`, `expireAfterAccess` | No | Local cache needing resource limits and freshness |
| `RedisCacheManager` | Redis server | Has key TTL, custom configuration | Yes if sharing a server | Need to share cache across multiple instances |
| `NoOpCacheManager` | Does not store | Not applicable | No | Intentionally disabling value caching in an environment |
| `SimpleCacheManager` | Application-registered `Cache` instances | Depends on each cache's provider | Depends on provider | Grouping manually configured caches |

Points to note:
- Caffeine and Redis have differences in serializers, null handling, TTL, eviction, and concurrency. Do not switch providers and assume all behaviors stay identical.
- Even with TTL, data can still be stale until expiration if there is no invalidation.
- Distributed caching does not automatically make DB and cache part of an atomic transaction. Consider commit timing and race conditions.
- Limit key cardinality and measure hit/miss rates, source access counts, and heap/Redis memory costs before choosing a policy.

## 14. Common Errors and Checklist

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Two calls with same key still run body | Not going through Spring proxy, missing `@EnableCaching`, different keys, cache evicted | Inject Spring bean, measure repository call count |
| Cache name error | Static mode does not include requested name | Check `getCacheNames`, spelling of `cacheNames` |
| Stale value after update | Missing `@CacheEvict` or `@CachePut` with matching key | Check DB commit timing and cache entry |
| Null caching behaves unexpectedly | Difference between `allowNullValues` and `unless` | Check actual manager and `Cache.ValueWrapper` |
| Cached object mutates unexpectedly | Mutable object stored by reference | Use immutable DTO/defensive copy |
| Heap grows over time | No TTL, no maximumSize, too many keys | Consider Caffeine, eviction, and metrics |
| Nodes return different data | Local cache per JVM | Use shared cache or cross-node invalidation |
| Boot properties do not take effect | User-defined manager/resolver, auto-config does not select Simple | Log actual bean, inspect classpath |

**Implementation checklist:** Define cache names and keys accurately, choose dynamic/static mode, explicitly decide null policy, prefer immutable values, verify calls go through the proxy, design invalidation after updates, bound memory usage, understand multi-instance topology, and test both hits and misses. If expiry is needed, do not try to configure TTL on `@Cacheable`; choose a provider that supports it.

## 15. Self-Check Questions

**Question 1.** Does `new ConcurrentMapCacheManager()` followed by `getCache("new")` create a cache?  
**Answer:** Yes, in dynamic mode it is created on demand.

**Question 2.** What does `new ConcurrentMapCacheManager("books")` return for `getCache("new")`?  
**Answer:** `null`, because this is static mode which only accepts declared names.

**Question 3.** Can you distinguish a cached null from a cache miss using `get(key)`?  
**Answer:** Yes: a hit containing null has a `ValueWrapper` with `get() == null`; a miss has no wrapper.

**Question 4.** Why doesn't updating the DB automatically update the cache with the new value?  
**Answer:** ConcurrentMap is an independent local store. Eviction, `put`, or an appropriate invalidation workflow is required.

**Question 5.** Does Spring Cache with ConcurrentMap automatically delete an entry after 5 minutes?  
**Answer:** No, this provider does not offer built-in TTL.

**Question 6.** Why can the default store-by-reference cause bugs with mutable objects?  
**Answer:** Callers mutating the shared reference can change the cached entry without going through `put`.

**Question 7.** Two servers both have a cache named `books`. Do they automatically synchronize data with each other?  
**Answer:** No. Each JVM has its own map; a shared cache solution or cross-node invalidation is needed.

## Official Documentation

- [Spring Framework — ConcurrentMapCacheManager JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework — ConcurrentMapCache JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Key Takeaway:** `ConcurrentMapCache` holds key/value entries in the JVM; `ConcurrentMapCacheManager` manages caches by name in either dynamic or fixed mode. It is a simple provider, convenient for learning and testing, but lacks TTL, persistence, and distributed caching. To use it properly, you must pay attention to keys, proxies, nulls, mutability, invalidation, and when to switch providers as scale increases.