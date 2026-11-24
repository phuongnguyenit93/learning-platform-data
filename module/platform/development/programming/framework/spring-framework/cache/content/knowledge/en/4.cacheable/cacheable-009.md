# Verifying @Cacheable Behavior via Method Execution Counts

> **Context:** Spring Framework Cache — `@Cacheable` group. The goal of this lesson is to **provably demonstrate through observation** that repeated calls with the same cache key can receive results back from the cache **without re-running the business method body**. The focus is on execution counting, building controlled experiments, and automated testing.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **number of client calls to a method** from the **number of times the underlying method body executes** when Spring Cache is active.
2. Build a cache miss/hit experiment using `AtomicInteger`, logs, and invocations with matching and differing keys.
3. Accurately predict counter values before and after `evict` or `clear` operations.
4. Write a JUnit test using a Spring ApplicationContext to verify caching via assertions, rather than relying solely on speed or logs.
5. Diagnose scenarios where counts differ from expectations: missing `@EnableCaching`, self-invocation, keys, providers, TTL, `condition`, `unless`, and concurrent contention.

## 2. What Exactly Are We Counting?

Suppose we have a business method:

```java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String code) {
    // Method body: simulates a query or computation
    return "item:" + code;
}
```

This is **illustrative code**, not a standalone program. In an application with caching properly configured, when another bean calls `find("A")` **through the Spring proxy**:

1. Spring's interceptor uses cache name `catalog` and key `"A"` to query the cache.
2. On a **miss**, Spring executes the body of `find` and then stores the result (if policy allows).
3. On a **hit**, the interceptor returns the existing result; the body of `find` is **not called**.

Therefore, separate these metrics:

| Metric | Meaning | Increases on a cache hit? |
| --- | --- | --- |
| **Client calls** | Number of times external callers invoke the Spring bean's API | Yes, increments by one per call |
| **Body executions** | Number of times code inside the `@Cacheable` method actually runs | No, for a successful hit |
| **Cache lookups** | Number of times the framework/provider performs a lookup operation | Depends on policy and call path; not synonymous with method body runs |
| **Data source queries** | Number of times business logic actually accesses the database or upstream API | Depends on whether the query sits in the method body, conditional branches, and other cache layers |

**Place the counter directly inside the method body.** If you increment a counter in a controller or right before calling `service.find(...)`, you measure client call counts; that metric still rises on hits and does not prove Spring skipped the expensive work.

## 3. Experiment Scenario: Same Key, Different Key, Then Invalidation

We design a sequential scenario, without concurrent calls, starting with an empty cache, no TTL, and no automatic eviction:

| Step | Action | Expected Hit/Miss | Cumulative method body executions |
| --- | --- | --- | --- |
| 0 | Create fresh cache, counter at 0 | Not yet read | 0 |
| 1 | `find("A")` | Miss: key A not present yet | 1 |
| 2 | `find("A")` | Hit: A already exists | 1 |
| 3 | `find("B")` | Miss: key B differs from A | 2 |
| 4 | `find("A")` | Hit: A is still present | 2 |
| 5 | `evict("A")`, then `find("A")` | Miss because A was evicted | 3 |
| 6 | `find("B")` | Hit if B still exists | 3 |

At step 4: **4 client calls yet the method body executed only 2 times**. At step 5: the `evict` operation itself does not run `find`; the subsequent read of A is what increments the counter.

This is a testable hypothesis. If an actual experiment yields a different result, do not immediately claim `@Cacheable` is broken: inspect the cache key, proxy call path, annotation conditions, instance count, provider, and cache state.

## 4. Runnable Example: Java 17 + Spring Boot + Simple Cache

This example uses Spring Boot **3.5.9**, JDK 17+, Maven, and Simple cache (`ConcurrentMapCacheManager`) so neither Redis nor a database is needed. Version 3.5.9 is used as a reproducible baseline for the example; when applying this to a real project, use a currently supported patch version in your project's Boot release line.

### 4.1. File structure

```text
cache-execution-proof/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/cache/
    │   │   ├── CacheProofApplication.java
    │   │   ├── CacheConfiguration.java
    │   │   └── CatalogService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/cache/
            └── CacheProofTest.java
```

### 4.2. Maven — `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-execution-proof</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-cache` provides Spring Cache integration; `spring-boot-starter-test` supplies Spring Test and JUnit Jupiter infrastructure for writing tests. Boot's parent manages dependency versions. Neither Caffeine nor Redis is needed yet since we choose Simple cache purely to verify the phenomenon.

### 4.3. Cache configuration — `CacheConfiguration.java`

```java
package example.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
```

`@EnableCaching` activates processing of `@Cacheable`. Placing it in a dedicated configuration class clarifies intent and lets other test suites choose whether or not to import caching.

### 4.4. Service with counter — `CatalogService.java`

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger bodyExecutions = new AtomicInteger();

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String sku) {
        int number = bodyExecutions.incrementAndGet();
        System.out.println("BODY " + sku + " -> " + number);
        return "item:" + sku;
    }

    public int executionCount() {
        return bodyExecutions.get();
    }
}
```

Explaining each choice:

- `bodyExecutions.incrementAndGet()` lives **inside `find`**, so it increments only when the method body actually runs; `AtomicInteger` is safer than `int++` when multiple threads share the bean.
- `@Cacheable(cacheNames = "catalog", key = "#p0")` uses the first argument as the key. `#p0` does not depend on preserving the `sku` parameter name in bytecode.
- `find` is a public method on a Spring-managed `@Service`; clients will retrieve the bean from the context so calls pass through the proxy.
- `executionCount` is an **uncached** counter-reader method. Reading it does not increase `find`'s execution count.
- `"item:" + sku` simulates a stable data-source result. A real application can replace this with a database query or API call inside `find`.

### 4.5. Main application — `CacheProofApplication.java`

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CacheProofApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(CacheProofApplication.class, args)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("A1=" + service.find("A"));
            System.out.println("A2=" + service.find("A"));
            System.out.println("B1=" + service.find("B"));
            System.out.println("A3=" + service.find("A"));
            System.out.println("count=" + service.executionCount());

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println(
                    "cacheManager=" + manager.getClass().getSimpleName()
            );
        }
    }
}
```

The most important detail is `context.getBean(CatalogService.class)`. The service is invoked externally through the Spring-managed instance; if you use `new CatalogService()`, cache annotations will not apply to that object.

### 4.6. Provider and logging — `application.properties`

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
spring.cache.type=simple
spring.cache.cache-names=catalog
```

`spring.cache.type=simple` pins the Simple provider for the experiment. The cache named `catalog` is explicitly declared; the Simple provider stores data in JVM memory and has no TTL or automatic eviction policy in this example configuration. `logging.level.root=OFF` makes it easy to observe the program's own `System.out.println` lines; it does not affect caching behavior.

### 4.7. Running and comparing results

In the `cache-execution-proof` directory (requires JDK 17+, Maven, and Maven Central access on the first run):

```bash
java -version
mvn -q spring-boot:run
```

The lines **printed by the application code** appear in exact order, excluding build-tool messages:

```text
BODY A -> 1
A1=item:A
A2=item:A
BODY B -> 2
B1=item:B
A3=item:A
count=2
cacheManager=ConcurrentMapCacheManager
```

Interpretation:

- `A1`: cache miss, executes method body, prints `BODY A -> 1`.
- `A2`: hits the same key A, no new `BODY` line.
- `B1`: misses for B, counter increments to 2.
- `A3`: still hits for A, no new `BODY` line.
- `count=2`: equals the number of distinct keys computed in this sequential experiment, **not an invariant rule** for every workload.
- `ConcurrentMapCacheManager`: proves the Simple provider was actually selected, rather than assuming it just from adding annotations.

To also observe calls **after evicting a key**, use the automated test in the next section. Each fresh program run starts with counter 0 and a fresh Simple cache; re-running the application **does not preserve caches from the previous process**.

## 5. Verifying with JUnit: Asserting Method Body Execution Counts

Using logs is easy to follow when learning, yet logs can be noisy, filtered, or hard to verify in CI. Tests should compare the counter value before and after each invocation.

Create `src/test/java/example/cache/CacheProofTest.java`:

```java
package example.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheProofTest {
    @Autowired
    private CatalogService service;

    @Autowired
    private CacheManager cacheManager;

    @Test
    void provesHitMissAndEvictionByExecutionCount() {
        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("catalog"),
                "Missing catalog cache"
        );
        cache.clear();

        int baseline = service.executionCount();

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 1, service.executionCount());

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 1, service.executionCount());

        assertEquals("item:B", service.find("B"));
        assertEquals(baseline + 2, service.executionCount());

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 2, service.executionCount());

        cache.evict("A");

        assertEquals("item:A", service.find("A"));
        assertEquals(baseline + 3, service.executionCount());

        assertEquals("item:B", service.find("B"));
        assertEquals(baseline + 3, service.executionCount());
    }
}
```

Run:

```bash
mvn -q test
```

Expected outcome: Maven exits with **exit code 0** and the JUnit test passes. With `-q`, Maven may not print a "BUILD SUCCESS" line; `BODY` lines appear only when the method actually executes. We do not rely on log line counts as the primary proof: the assertions `baseline + 1`, `baseline + 2`, `baseline + 3` are the proof.

**Why use `baseline` instead of requiring 0?** A Spring Test ApplicationContext can be reused across multiple tests; bean state may have already changed. `cache.clear()` wipes cache entries, but does not reset `AtomicInteger`. Comparing against `baseline` keeps the test focused precisely on the increment caused by each call, independent of prior state. In large projects, you must also manage parallel test execution and beans sharing caches.

**Why inject the service with `@Autowired`?** Spring creates and can proxy the bean. Writing `new CatalogService()` in a plain unit test executes regular Java code, bypassing the Spring Cache interceptor. A proper cache test must use a Spring context or configure an equivalent proxy.

**Why call `cache.evict("A")` directly?** We deliberately remove key A from the cache to verify returning to a miss state without depending on TTL or scheduler timing. This test focuses on `@Cacheable`. In a real application, `@CacheEvict` may be placed on a data-updating method.

## 6. A Wrong Way to Measure: Counting on the Caller Side

The snippet below (illustrative, no `main`) only measures client call counts:

```java
int requests = 0;
requests++;
service.find("A");
requests++;
service.find("A");

System.out.println("requests=" + requests); // requests=2
```

Assuming the first call is a miss and the second is a hit, `requests` is still 2. You **cannot conclude** the body of `find` executed twice. To measure underlying processing runs, put the counter inside `find` as in the full example. When a second cache layer exists in a repository or HTTP client, also specify clearly **which method's** executions and which data source accesses are being measured.

## 7. Cases Where Counters Deviate from Expectations

### 7.1. Missing @EnableCaching or no suitable CacheManager

Adding `spring-boot-starter-cache` alone does not prove `@Cacheable` is active. Caching must be enabled with `@EnableCaching`; the cache name must be accepted by the provider/manager; and calls must go through the Spring bean. Check the `CacheManager` type, logs, and two calls with the same key.

### 7.2. Internal calls within the same bean (self-invocation)

In default proxy mode, calls via `this` from within the same object normally bypass the interceptor:

```java
@Service
public class CatalogService {
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        // underlying processing logic
        return "item:" + sku;
    }

    public String internalCall(String sku) {
        return this.find(sku);
    }
}
```

This is an **illustrative snippet separate from the sample project above**, not a replacement file to copy over it. Calling `internalCall("A")` twice through the Spring bean can run the body of `find` both times, because each `this.find` bypasses the proxy. To verify proper caching paths, invoke from **another bean** or from a test with the injected service.

### 7.3. Different keys despite similar-looking calls

`find("A")` and `find("B")` are two different keys. If generated keys contain timestamps, objects lacking proper `equals/hashCode`, tenants, or locales, hit rates and execution counts will differ. When using SpEL keys, inspect `#p0`, `#p1`, ... and the exact arguments of each invocation.

Do not alter keys to force calls to hit if the business result actually depends on multiple parameters; under-specified keys can return **wrong data or leak across users**.

### 7.4. Cache conditions and non-caching policies

Illustrative annotation example:

```java
@Cacheable(
    cacheNames = "catalog",
    key = "#p0",
    condition = "#p0.length() > 1",
    unless = "#result == null"
)
public String find(String code) {
    return repository.lookup(code);
}
```

The snippet above requires a real `repository` bean; it is for explanation only. `condition` is evaluated before invoking the method: for codes that are too short, caching is not applied and every call can run the method body. `unless` is evaluated after a result is obtained: if the result is `null`, Spring skips storing it for that call; subsequent calls can continue executing again. Actual behavior also depends on other annotations and provider policies.

### 7.5. TTL, eviction, restarts, or another instance's cache

A key that once hit will not necessarily hit forever. Cache entries can expire, be removed by `@CacheEvict` or `clear`, or be evicted due to memory capacity. Local caches on two different instances hold separate state. In-JVM counters also reset when the application restarts.

Before asserting, establish the **initial cache state**, when entries remain valid, and **which instance** you are observing.

### 7.6. Multiple requests missing the same key concurrently

If multiple threads simultaneously request key A while the cache is empty, regular `@Cacheable` **does not promise the method body runs only once**. Multiple requests may all see a miss and recompute. That is why the scenario table in section 3 assumes sequential calls.

`@Cacheable(sync = true)` asks the cache provider to coordinate so only one value is computed for the same key under contention; this capability is provider-dependent. The `sync` mechanism carries constraints such as supporting only one cache and disallowing `unless`. Even with `sync = true`, you must understand the real provider's behavior, especially in distributed environments.

To keep tests **deterministic**, verify basic hit/miss behavior with sequential calls first. If testing cache-stampede protection, write a separate concurrency test controlling thread count, start barrier, and provider; do not introduce arbitrary thread scheduling into basic hit/miss tests.

## 8. Additional Check: Impact of @CacheEvict and @CachePut on Counting

Distinguish the annotations clearly:

- `@Cacheable`: can **skip executing** the method body on a hit.
- `@CachePut`: normally **executes the method** and uses its result to update the cache; do not use it to prove repeated work is skipped.
- `@CacheEvict`: applies a cache removal operation associated with the annotated method. Once eviction succeeds, a subsequent `@Cacheable` call can miss and re-execute the method body.

For example, an application updating a product successfully should evict the cached value under the matching key. If evicted before source data commits, another request can reload the old version; cache tests should account for transaction boundaries and invalidation timing when updates are involved.

## 9. Increasing the Reliability of Verification Tests

A convincing test should ensure:

1. **Right measurement target:** the counter sits inside the target method or uses a spy/metric capturing actual source activity.
2. **Right call path:** obtain beans from `ApplicationContext`; do not instantiate objects with `new` when testing annotations.
3. **Right cache:** confirm the actual `CacheManager` and cache name before drawing conclusions.
4. **Right initial conditions:** explicitly clear caches, capture a baseline, and avoid order-dependent tests.
5. **Right arguments:** identical keys for hits, differing keys for misses.
6. **Right scope:** single-threaded tests for basic behavior; separate tests for concurrency and multi-instance setups.
7. **Right assertions:** assert both return values and body execution counts, avoiding timing-only checks.
8. **Right expectations:** a cache hit only shows the interceptor served from cache; it does not prove the cache is always fresh, improves overall performance, or satisfies business correctness.

### Why is measuring latency alone insufficient?

A method can run faster the second time due to the JIT compiler, reused DB connections, buffer caches, or data loaded at another layer, even when Spring Cache never hit. Conversely, a hit can still vary in latency due to GC or CPU contention. A counter inside the underlying processing logic paired with assertions proves caching behavior far more directly.

In production, also use provider/cache manager metrics (hits, misses, evictions), source query counts, and p95/p99 latency. Manual counters are great for learning and debugging, but do not replace long-term observability.

## 10. Practice Exercises

**Exercise 1 — Predict the counter.** Empty cache, counter at 0, no TTL. Call sequentially: `A, A, B, A, B, C`. How many times does the method body execute? Answer: **3** assuming keys follow the code, values are stored, and no invalidation occurs — each of A, B, C needs computing on its first call.

**Exercise 2 — Add invalidation.** After the sequence above, evict key B and then call `A, B, B`. By how much does the counter increase? Answer: **1** — A still hits, the first B misses, and the second B hits.

**Exercise 3 — Diagnose.** In a test, two calls to `service.find("A")` both increment the counter. Check in order: was the bean created by Spring, is `@EnableCaching` enabled, did the call pass through the proxy, are the keys truly identical, are the cache manager and cache name valid, were results blocked by `condition`/`unless`, and was the cache cleared between calls.

**Exercise 4 — Discuss.** Twenty concurrent requests hit the same key while the cache is empty. Should we expect by default that the counter increments only by 1? Answer: **No**, because default caching does not guarantee synchronized locking on misses; consider `sync = true`, the provider, and concurrent test design.

## Official Documentation

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Understanding the Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot 3.5.9 release](https://spring.io/blog/2025/12/18/spring-boot-3-5-9-available-now/)

**Takeaway:** Client call count is not `@Cacheable` body execution count. A solid verification uses a proxied Spring bean, controlled cache state, a counter inside the method body, and assertions covering hits, misses, and eviction. Only then can you assess whether the cache genuinely eliminates duplicate work.