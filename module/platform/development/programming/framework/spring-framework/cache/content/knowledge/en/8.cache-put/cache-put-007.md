# Risks of Combining @CachePut and @Cacheable on the Same Method

> **Topic:** Spring Framework Cache — `@CachePut` group. Focus: why you should not place `@Cacheable` and `@CachePut` simultaneously on one method, scenarios that can go wrong, the mutually exclusive conditions exception, and how to replace it with two clear read/write methods.

## Learning Objectives

After this lesson, you will be able to:
1. Accurately explain the difference between a `@Cacheable` **cache hit** and a call annotated with `@CachePut`.
2. Recognize how combining both annotations makes the semantics of “whether to run the method body” contradictory.
3. Analyze the risks of skipped writes, mismatched cache keys, stale data, wrong update ordering, and transaction bugs.
4. Understand the rare exception when two `condition` expressions are mutually exclusive before calling the method; know why `#result` cannot be used to prove mutual exclusion.
5. Write and run a Java 17 Spring Framework 6.x example with proper design, along with a JUnit test verifying the hit, update, and re-read flow.

## 1. What do @Cacheable and @CachePut actually do?

Spring Cache is an abstraction consisting of `Cache`, `CacheManager`, and interceptors that handle method calls through Spring proxies. Each annotation has a **different purpose**.

### `@Cacheable` — optimizing the read path

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
```

This is an **illustrative snippet in a bean with a repository**, not a standalone runnable program. When calling the method through the proxy:

- If the cache does not yet have an entry for key `id` (miss), the method executes; the result may be put into the cache.
- If a valid entry already exists (hit), Spring can return the stored result **without running the body of `find`**.
- Therefore, `@Cacheable` should only be used for processing that **is allowed to be skipped** when cached results are still acceptable, typically side-effect-free reads/queries.

### `@CachePut` — running the method and refreshing the cache

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product update(String id, int newPrice) {
    return repository.updatePrice(id, newPrice);
}
```

This is also an illustrative snippet; it assumes `repository` has an actual update method. With `@CachePut` used **on its own**, a cache hit does not cause Spring to skip the update business logic: the method **still executes**; its return value is used to update the cache per configuration.

For example, if the price increases from 100 to 200, after `update("P1", 200)`, cache entry P1 should reflect the new returned object (assuming the update succeeded and policy allows). `@CachePut` does not replace the database write step itself.

| Aspect | `@Cacheable` | `@CachePut` |
| --- | --- | --- |
| Primary intent | Reuse results on reads | Proactively update cache from execution result |
| Cache hit | May skip method body | Still executes method body when used alone |
| Cache miss | Runs method, may populate cache | Runs method, may populate cache |
| Suitable methods | Queries / idempotent reads | Update commands, controlled refreshes |
| Risk when misused | Skipping mandatory side effects | Overwriting values or doing pointless expensive work |

**Core point:** with `@Cacheable`, **not executing the method** is a feature; with `@CachePut`, **executing the method** to produce fresh data is the goal.

## 2. Contradiction when combined on the same method

Error-prone pattern:

```java
@Cacheable(cacheNames = "products", key = "#p0")
@CachePut(cacheNames = "products", key = "#p0")
public Product loadAndRefresh(String id) {
    return repository.find(id);
}
```

This is an **anti-pattern for analysis**, not a recommended implementation.

The two annotations create two conflicting requirements:

- “If there is a cache hit, skip `loadAndRefresh`” from `@Cacheable`.
- “Must run `loadAndRefresh` to get the result and write the cache” from `@CachePut`.

Because Spring must resolve multiple cache operations on the same invocation, the author has no simple behavioral contract like “both always run the method and always skip the method on a hit”. Depending on conditions, cache keys, provider, advice, and call path, behavior may diverge from expectations. Inferring which annotation “runs first” is not a reliable programming practice.

**Spring Framework documentation strongly advises against placing these two annotations on the same method**, except in very special cases where their conditions are mutually exclusive. That advice applies even when the code compiles and the application starts cleanly.

## 3. Common risks

### 3.1. Write commands get skipped

If a method contains `repository.save(...)`, deducts inventory, sends notifications, records payments, or emits events while also carrying `@Cacheable`, a cache hit can create an execution path that skips business logic that must run. This is especially dangerous because callers may receive old data and mistakenly believe the update succeeded.

**Rule:** never use a cached result to replace executing an operation with side effects. Command methods must have explicit execution behavior; caching is only a supporting layer.

### 3.2. No savings on repeated work

A method with `@CachePut` must execute to put the fresh value into the cache; if the original goal was fast reads, combining them can negate the query- or computation-saving benefit of `@Cacheable`. You cannot measure quality simply by having the annotations present; you must measure method-body execution counts, DB query counts, and actual latency.

### 3.3. Returning stale data or overwriting the cache

If the source changes while the cache still holds an old version, a `@Cacheable` branch can return stale data instead of refreshing as the author expected. Under concurrent updates, two requests can write to the cache in a different order than the data committed to the source, leaving behind an old value. You must analyze transactions, versioning, race conditions, and providers; placing both annotations together does not guarantee consistency by itself.

### 3.4. Mismatched cache keys between read and write

Even after **splitting into two methods**, leaving default keys can introduce a bug:

```java
@Cacheable("products")
public Product find(String id) { /* query */ }

@CachePut("products")
public Product update(String id, int price) { /* write */ }
```

The methods above are **illustrative signatures**, not complete Java code. With the default `SimpleKeyGenerator`, a single-argument method like `find(id)` typically uses `id` itself as the key. The two-argument method `update(id, price)` generates a composite key, such as `SimpleKey(id, price)`. Even with the same cache name, `@CachePut` may update a different entry than the one `find` reads. Result: subsequent reads keep hitting stale data.

Solution when data is truly identified solely by ID:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) { /* query */ }

@CachePut(cacheNames = "products", key = "#p0")
public Product update(String id, int price) { /* write */ }
```

Both illustrative snippets use **the same key `id`**. In multi-tenant systems, or those varying by currency, locale, or permission level, the key must include enough context affecting the result; using only `id` can cause data leaks or wrong results.

### 3.5. Put value is not the data that needs caching

`@CachePut` puts **the value returned by the method** into the cache. If a successful update method returns `boolean`, a status DTO, or an unrefreshed object, sharing the `products` cache with a read method returning `Product` will corrupt the cached type or content. In that case, using `@CacheEvict` to delete the key and reload on read can be much clearer.

### 3.6. Differences between tests and production

Unit tests instantiating objects with `new ProductService()` do not trigger cache interceptors like beans called through Spring proxies. Self-invocation (`this.find()` or `this.update()`) from within the same bean also bypasses cache advice in default proxy mode. Multiple instances with independent local caches can behave differently even with identical annotations.

## 4. Conditional exception: two mutually exclusive branches

According to the Spring Framework, rare situations allow placing both annotations on the same method if **their two `condition`s are mutually exclusive**.

Intentional illustration:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p1 == 'READ'"
)
@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p1 == 'REFRESH'"
)
public Product load(String id, String mode) {
    return repository.find(id);
}
```

This is an illustrative snippet using an undefined `repository`; not a standalone runnable application. Assuming `mode` is only `READ` or `REFRESH`, both conditions cannot be true on a single call:

- `READ`: the cacheable operation is selected; the method may be skipped on a hit.
- `REFRESH`: the put operation is selected; the method is called to refresh the cache.
- Any other mode: both conditions are false, so no corresponding cache operation runs.

Even so, forcing callers to know a method has two modes makes the API confusing. **Separating the read method and refresh method is usually better**, and any choice to keep them together needs integration tests against the actual Spring version in use.

### Why not use `#result` to prove mutual exclusion?

Spring must evaluate the mutual exclusion of the operations **before deciding whether the method invocation can be skipped**. The method result `#result` does not exist yet at that time. Therefore, you must not rely on `#result` to separate `@Cacheable`/`@CachePut` branches in this exception case.

`unless` is a mechanism evaluated **after a result is obtained** to veto storing, not a way to guarantee upfront that both operations will not apply together. Some `@CachePut` expressions can use `#result` during the post-invocation update phase, yet that does not solve verifying mutual exclusion **pre-invocation**.

Similarly, replacing the two annotations with `@Caching(cacheable = ..., put = ...)` does not eliminate the conflict; `@Caching` merely groups multiple cache operations.

## 5. Clearer solution: separate query and write command

Standard design:

```text
Client
  |
  +--> findProduct(id)            @Cacheable
  |       HIT  -> return cached value, do not run query
  |       MISS -> run query and cache result
  |
  +--> updateProduct(id, price)   @CachePut
          run source update business logic
          obtain new Product after update
          write new Product to cache under same key id
```

This is an implementation style that **separates read and write responsibilities**:

- `findProduct` only reads and allows optimization via cache hits.
- `updateProduct` executes the update business logic without skipping merely because cached data exists.
- Both methods align on cache name, key, and value type.
- Testing/monitoring can accurately verify source read counts and source update counts.

If canonical data is unavailable to put after an update, consider evicting the cache:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, int price) {
    repository.updatePrice(id, price);
}
```

This is an example placed in a Spring bean with a repository. Under default configuration, eviction usually occurs after the method completes successfully; the next read misses and fetches fresh data. However, if a transaction is present, **method completion does not always mean commit has finished** — check transaction boundaries carefully.

## 6. Runnable Java 17 project: Spring Cache with two separate methods

The example uses **Spring Framework 6.2.1**, Maven, and `ConcurrentMapCacheManager` in a single JVM. It does not require Spring Boot, a DB, or Redis. Source data is simulated using `ConcurrentHashMap`, and products are immutable Java records.

### 6.1. Structure

```text
cache-annotation-design/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheDemo.java
    └── test/java/demo/cache/CacheDemoTest.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>cache-annotation-design</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.1</version>
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

Maven downloads `spring-context` and related Spring dependencies via Maven Central. `@EnableCaching` activates the interceptor; `ConcurrentMapCacheManager` stores data in the JVM. JUnit is the testing library. Real Spring Boot projects should manage versions via a compatible BOM/parent instead of pinning a separate Spring version manually.

### 6.3. `src/main/java/demo/cache/CacheDemo.java`

```java
package demo.cache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheDemo {
    public record Product(String id, int price) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();

        public ProductRepository() {
            data.put("P1", new Product("P1", 100));
        }

        public Product find(String id) {
            return data.get(id);
        }

        public Product save(String id, int price) {
            Product product = new Product(id, price);
            data.put(id, product);
            return product;
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger readCount = new AtomicInteger();
        private final AtomicInteger writeCount = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(String id) {
            int n = readCount.incrementAndGet();
            System.out.println("LOAD " + id + " #" + n);
            return repository.find(id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public Product update(String id, int price) {
            int n = writeCount.incrementAndGet();
            System.out.println("UPDATE " + id + " #" + n);
            return repository.save(id, price);
        }

        public int reads() {
            return readCount.get();
        }

        public int writes() {
            return writeCount.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductRepository repository() {
            return new ProductRepository();
        }

        @Bean
        public ProductService productService(ProductRepository repository) {
            return new ProductService(repository);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            System.out.println("read1=" + service.find("P1").price());
            System.out.println("read2=" + service.find("P1").price());
            System.out.println("updated=" + service.update("P1", 200).price());
            System.out.println("read3=" + service.find("P1").price());
            System.out.println("reads=" + service.reads());
            System.out.println("writes=" + service.writes());
        }
    }
}
```

Key points:
- `Product` is an immutable record; no risk of clients directly mutating fields inside cached objects.
- `ProductRepository` is the simulated data source, initially holding P1 at price 100.
- `find` has only `@Cacheable`. The `readCount` counter increments **inside the method body** when data actually has to be loaded.
- `update` has only `@CachePut`. It performs the source update logic and returns the new `Product` to store in the cache.
- Both use cache name `products` and `key = "#p0"`, targeting the exact same P1 identifier.
- Calls through `ctx.getBean(ProductService.class)` pass through the Spring proxy. Instantiating `new ProductService(...)` outside Spring bypasses caching annotations.

### 6.4. Running and predicting stdout

Requires JDK 17+, Maven 3.9+, and network access to download dependencies the first time. From the `cache-annotation-design` directory:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself**, excluding external Maven/Spring logs:

```text
LOAD P1 #1
read1=100
read2=100
UPDATE P1 #1
updated=200
read3=200
reads=1
writes=1
```

- `read1`: miss, executes `find`, gets 100, and puts it into the cache.
- `read2`: hit, no new `LOAD` line appears.
- `update`: executes once, changes source data to 200, and puts that value into cache key P1.
- `read3`: hits with result 200 without re-executing `find`.
- `reads=1` and `writes=1` confirm two clean, unambiguous execution paths.

This experiment is a single-threaded single-JVM example; it **does not prove** consistency across multiple instances, DB transactions, or race conditions.

## 7. JUnit testing to prevent regressions

Create `src/test/java/demo/cache/CacheDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheDemoTest {
    @Test
    void readHitDoesNotSkipUpdateAndPutRefreshesTheSameKey() {
        try (var ctx = new AnnotationConfigApplicationContext(
                CacheDemo.Config.class)) {

            var service = ctx.getBean(CacheDemo.ProductService.class);

            assertEquals(100, service.find("P1").price());
            assertEquals(100, service.find("P1").price());
            assertEquals(1, service.reads());

            assertEquals(200, service.update("P1", 200).price());
            assertEquals(1, service.writes());

            assertEquals(200, service.find("P1").price());
            assertEquals(1, service.reads());
        }
    }
}
```

Run:

```bash
mvn -q test
```

When all assertions pass, the JUnit test succeeds and Maven returns exit code 0. The method execution counts in the test prove:
1. Hits on the read method do not re-execute the `find` body.
2. The update method still executes.
3. The cache keys of both methods match, so re-reading sees 200 without querying the source again.

Each test creates its own ApplicationContext so it does not depend on state from the previous `main` program. In larger projects with parallel tests, manage cache state and concurrency separately.

## 8. Transactions, concurrency, and multiple instances: limits you must handle yourself

### 8.1. @Transactional does not automatically make DB and cache atomic

With a real database, `@Transactional` may commit **after** the method body finishes; transaction/cache advice ordering depends on configuration. If the cache put happens before the transaction commits and the DB rolls back, the cache can hold values that do not exist in the DB. If the cache is evicted before commit, another request can miss and load the old version.

Choose an explicit strategy: refresh or invalidate after commit when appropriate, use a transaction-aware cache where supported by the provider, `@TransactionalEventListener(phase = AFTER_COMMIT)` events, or another synchronization mechanism per system requirements. Putting two annotations on one method does not solve transactional issues.

### 8.2. Concurrent updates

Two concurrent requests writing the same key can update the DB and put into the cache in different orders; the final cache value can be stale. When strong consistency is needed, consider optimistic locking/versioning, event ordering control, eviction, or post-commit updates. `@CachePut` does not resolve all race conditions on its own.

### 8.3. Local caches across multiple instances

`ConcurrentMapCacheManager` and Caffeine are typically JVM-local caches. A `@CachePut` on instance A does not update the local cache on instance B. If sharing is required, use a distributed provider like Redis and design appropriate invalidation/TTLs. Shared Redis still does not turn operations into atomic DB + cache transactions.

### 8.4. `@Cacheable(sync = true)` does not fix design flaws

`@Cacheable(sync = true)` helps coordinate computation when multiple misses occur for the same key if the provider supports it, but it has its own restrictions (such as not combining with other cache operations and not supporting `unless`). It is not a way to reconcile `@Cacheable` with `@CachePut` on the same method.

## 9. Common errors during refactoring

| Symptom | Possible cause | Check |
| --- | --- | --- |
| After update, `find` still returns old price | Two methods use different keys, different providers, or put happened before commit | Compare cache name/key, update timing, and source state |
| `@Cacheable` does not reduce query count | `@EnableCaching` missing, called via `this.find(...)`, changing keys, or cache cleared | Call via Spring proxy, log method execution counts |
| `@CachePut` does not update cache | Self-invocation, missing manager, condition false, wrong key, provider rejects value | Check beans, advice, keys, and return value |
| Both cache hits and unusual side effects occur | Same method carries two conflicting annotations | Split read/write, add tests per path |
| Wrong value type when reading from cache | Put method returns a status response differing from `Product` type | Put canonical object or evict |
| Different customers receive the same value | Key omits tenant/role/currency/locale | Design keys with full context |
| Tests pass but production fails | Tests bypass Spring proxy, or use a different provider and transaction setup | Integration test under matching configuration |

`@Caching` only groups annotations; it does not eliminate the underlying contradiction if both `@Cacheable` and `@CachePut` are still declared for the same call path.

## 10. Checklist when encountering a method with both @CachePut and @Cacheable

1. Determine whether the method is a **read** or a **command/write**. If it must perform side effects, never let a cache hit replace the write business logic.
2. Check whether two operations are genuinely needed on the same method. If not, split `find` and `update`.
3. Verify that cache name, key, and **value type** match between read and write.
4. If using `@CachePut`, does the return value reflect the persisted canonical data?
5. If using `@CacheEvict`, after deleting the key can the next read reload the fresh version?
6. Check the proxy, `@EnableCaching`, and active `CacheManager`.
7. Check commit timing, rollback errors, and freshness requirements.
8. Write hit/miss/update tests, recording method-body execution counts and returned data.
9. In multi-instance/multi-tenant systems, verify cross-node updates and proper key isolation.
10. Keep the mutually exclusive two-condition exception only with a clear justification, conditions independent of `#result`, and comprehensive integration tests.

## 11. Self-check exercises

**Exercise 1.** Why shouldn't `@Cacheable` be used on a payment method?  
**Answer:** A cache hit can skip the method body, whereas payment is an operation with mandatory business side effects that must execute.

**Exercise 2.** `find(id)` and `update(id, newPrice)` share the same cache name but omit key configuration. Why can the cache still be stale after an update?  
**Answer:** The default key generator produces different keys for single-parameter and two-parameter signatures; keys must be aligned, e.g., `#p0` if ID uniquely identifies the data.

**Exercise 3.** An update method returns a `boolean` success flag, while the `products` cache expects `Product`. Should `@CachePut` be used?  
**Answer:** Do not put a boolean into a `Product` cache; return a canonical `Product` or use `@CacheEvict`.

**Exercise 4.** Are two mutually exclusive `condition`s based on `#result` safe for combining both annotations?  
**Answer:** No. Verifying mutual exclusion must be possible before invocation; `#result` is only available after running the method.

**Exercise 5.** Why might two separated methods with identical keys still fail to guarantee fresh data on all instances?  
**Answer:** Local caches in each JVM hold separate state; additionally, transactions, races, TTLs, and invalidation play a role.

## Official Documentation

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

**Remember:** `@Cacheable` can skip a method on a cache hit; `@CachePut` serves to run a method and write the new result to the cache. Combining both on the same method creates conflicting expectations and is discouraged by Spring documentation. Separating read/write methods, aligning keys, and testing fresh results is the clear, maintainable implementation approach.