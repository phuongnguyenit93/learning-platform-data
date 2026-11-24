# Single Cache, No unless, and No Combining Operations When Using sync

> **Topic:** Spring Framework Cache — **Concurrency** section. This lesson analyzes the three mandatory constraints when using `@Cacheable(sync = true)`: **only one cache per operation**, **no `unless`**, and **no combining with other cache operations on the same method**. We also examine the technical reasons, valid syntax, alternatives, and concurrency testing with Java 17.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Explain the **cache stampede** phenomenon when multiple threads encounter a cache miss for the same key.
2. Understand where `sync = true` affects result computation and why it depends on the cache provider.
3. State the exact three constraints: one cache, no `unless`, and no combining other cache operations.
4. Distinguish constraints on **a single method** from an application having multiple caches or multiple cached methods.
5. Predict valid code behavior and identify code likely to be rejected by Spring.
6. Use `ConcurrentMapCacheManager` and two concurrent calls to verify how many times the method body executes.
7. Choose an alternative design when you truly need post-method result filtering, updating multiple caches, or synchronizing across multiple instances.

## 2. Why is synchronized caching needed?

A typical read call:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String productId) {
    return repository.load(productId);
}
```

This is **illustrative code inside a Spring bean**, not a standalone program. The Spring Cache interceptor looks up the key before invoking the method body:

- **Hit:** returns the cached value, usually without running the method.
- **Miss:** invokes the method to compute the value and stores it in the cache.

In a concurrent environment, suppose 10 requests look up `P42` while the cache is empty:

```text
Time           Thread A               Thread B               Thread C
---------      --------               --------               --------
t0             GET(P42) -> miss       GET(P42) -> miss       GET(P42) -> miss
t1             call DB/API            call DB/API            call DB/API
t2             PUT(P42)               PUT(P42)               PUT(P42)
t3             return result          return result          return result
```

Without coordination on the initial load, multiple threads can execute expensive work simultaneously. This scenario is commonly called a **cache stampede** or **thundering herd**. It often occurs when the cache just started, a heavily accessed key expires simultaneously, or an entry is invalidated.

Spring supports:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String productId) {
    return repository.load(productId);
}
```

`sync = true` asks the cache provider to coordinate **computing the value for a missing key**. With a provider that supports appropriate synchronization, only one thread runs the loader for that key while the other threads wait for the result. However, this is **a request/hint sent to the provider**, not an independent guarantee that every cache technology provides distributed locking or eliminates all duplicate executions.

## 3. The three main constraints of sync = true

The official JavaDoc of `org.springframework.cache.annotation.Cacheable` defines three constraints for synchronized caching:

| Constraint | What is disallowed | Why it matters |
| --- | --- | --- |
| **Single cache only** | Declaring multiple cache names on one `@Cacheable(sync = true)` | Synchronized loading needs a single consistent target cache for the computation |
| **No unless** | Setting `unless = ...`, including `#result` checks | `unless` decides whether to skip caching after the method runs, which does not fit the cache API's synchronized loading path |
| **No combining other cache operations** | Combining synchronized `@Cacheable` with `@CachePut`, `@CacheEvict`, or another cache operation on **the same method** | A single invocation cannot both use the synchronized loading path and attach additional cache operations |

These constraints are **Spring Cache annotation rules**, not mere style guidelines. Violations can cause the configuration/operation to be rejected when the framework validates it; you should not rely on the exact timing or verbatim exception message across versions.

**Do not confuse this with an application having multiple caches:** an application can still have `products`, `prices`, and `customers` caches; only **a single `@Cacheable(sync = true)` invocation** must target exactly one cache. Having another method annotated with `@CacheEvict` to remove a key from that cache remains valid.

## 4. Constraint 1 — each synchronized operation uses only one cache

### Wrong: multiple cache names in one annotation

```java
@Cacheable(cacheNames = {"productsLocal", "productsRemote"}, sync = true)
public Product find(String id) {
    return repository.load(id);
}
```

This is an **invalid example when using synchronized caching** and should not be put into a running application. In normal mode, a `@Cacheable` can check multiple cache names. But when `sync = true`, Spring supports only **one cache per operation**. Configuring two cache names violates the constraint regardless of whether both serve the same data.

If using a custom `CacheResolver`, ensure the resolver actually returns exactly one cache for the synchronized operation; omitting names in the annotation is not a way around the rule.

### Right: one cache for one method

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.load(id);
}
```

If you want to cache `prices` separately, use another appropriate method (or a multi-level caching strategy implemented internally by the provider), rather than declaring two cache names on the same `@Cacheable(sync = true)`.

### What if you need multi-level caching?

There are two different problems:
- **One cache operation with two separate cache stores:** violates the sync constraint if the framework receives two caches.
- **One logical cache with multiple tiers inside the provider:** may be feasible if the provider implements a single `Cache` object with an appropriate synchronization contract, though exact semantics must be checked.

Do not treat `CompositeCacheManager` or a `CacheResolver` selecting multiple caches as "one cache." A logical cache for a synchronized operation must be resolved by Spring to **a single `Cache` object**.

## 5. Constraint 2 — do not use unless with sync

### Wrong: vetoing result storage after the method runs

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Product find(String id) {
    return repository.load(id);
}
```

This is an **invalid example**. `unless` is evaluated **after the method has executed**, in order to skip putting a specific result into the cache. `sync = true` uses a retrieval path with a loader attached directly to the cache, typically via the `Cache.get(key, Callable)` contract. Spring does not support attaching `unless` to that synchronized execution path.

### Do not think changing the unless expression is enough

The following variants still do not solve the issue:

```java
@Cacheable(cacheNames = "products", sync = true, unless = "false")
@Cacheable(cacheNames = "products", sync = true, unless = "#result.price < 0")
```

These are **two independent annotation lines to illustrate errors**; do not place both on one method. Both declare a non-empty `unless`, whether the condition is always false or only true for certain results. To use `sync = true`, **remove the `unless` attribute entirely** instead of just changing the SpEL expression.

### Can condition be used?

**Yes**, `condition` and `unless` are not the same. `condition` decides **before loading** whether caching applies, whereas `unless` decides **after computing the result**.

Valid example:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    condition = "#p0 != null && !#p0.isBlank()"
)
public Product find(String id) {
    return repository.load(id);
}
```

When `id` is invalid, a false condition makes Spring skip caching and invoke the method directly; **the method still needs to validate input itself**. When the ID is valid, synchronization applies according to the provider.

Do not use `condition` to replace `unless` if the policy depends on the output—for example, "only cache Products with a positive price": before calling the method, Spring does not yet have `#result` to check. These are two distinct requirements and require a redesign rather than turning a post-processing expression into a pre-processing condition.

### What if you need to avoid caching null results?

Consider:
1. **Do not use sync:** keep `@Cacheable(unless = "#result == null")` and accept or handle cache stampedes with a separate mechanism where needed.
2. **Change the output contract:** use a result type that explicitly represents the state (e.g., an appropriately valued result object); inspect the provider's storage policy rather than relying on `unless`. Avoid caching "not found" for too long.
3. **Manual caching with a controlled policy:** write a custom loader/gate or use provider APIs directly, ensuring synchronization and post-computation result filtering as required.
4. **Apply an appropriate TTL/invalidation:** if caching negative results briefly is acceptable and supported by the provider, state the consistency policy clearly; do not assume every provider supports null values.

`sync = true` does not automatically allow or forbid storing null across all providers. Storing `null` depends on the implementation and configuration. Removing `unless` means you **no longer veto the result via this annotation**, not that every null result is guaranteed to be stored.

## 6. Constraint 3 — do not combine other cache operations on the same method

### Wrong: synchronized cacheable and cache put simultaneously

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
@CachePut(cacheNames = "products", key = "#p0")
public Product loadAndRefresh(String id) {
    return repository.load(id);
}
```

This pattern violates the **no combining other operations** constraint. Moreover, `@Cacheable` and `@CachePut` already have conflicting goals: cacheable can skip the method body on a hit, whereas put normally executes the method to update the cache. Adding `sync = true` brings the additional restriction against combining operations.

### Wrong: synchronized cacheable and eviction in the same invocation

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
@CacheEvict(cacheNames = "products", key = "#p0")
public Product loadAndEvict(String id) {
    return repository.load(id);
}
```

Also invalid; `@CacheEvict` is another cache operation applied to the same method. Grouping them with `@Caching` does not remove the constraint either:

```java
@Caching(
    cacheable = @Cacheable(cacheNames = "products", sync = true),
    put = @CachePut(cacheNames = "products")
)
public Product loadAndPut(String id) {
    return repository.load(id);
}
```

The three snippets above are **intentional anti-patterns**, shown only for recognizing errors—do not copy them into a runnable project.

### Right: separate reads from updates/deletes

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product find(String id) {
    return repository.load(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String id) {
    repository.markDirty(id);
}
```

This is an illustrative snippet in a bean with a repository. Having `@CacheEvict` on **a separate method** does not violate the constraint on synchronized `@Cacheable`. Likewise, a separate update method can use `@CachePut` when it actually writes the origin and returns the canonical value to store; both must agree on the key and cache name.

Check transaction/commit timing when invalidation involves a database: evicting the cache too early can cause another request to reload stale data before the transaction commits. Synchronizing misses does not replace data consistency logic.

## 7. Why does sync = true depend on the cache provider?

Synchronized caching requires the cache to be capable of performing a **get-or-compute value bound to a key** operation. The Spring Cache API supports the `Cache.get(Object key, Callable<T> valueLoader)` contract, enabling providers to coordinate loads. However, this is an **extension contract**: locking mechanism, wait duration, error handling, JVM scope, and future-caching capability depend on the implementation.

### What can be expected when the provider supports it

- Threads with **the same key, same cache, within the provider's synchronization scope** do not run the loader concurrently when no result is cached yet.
- Once the loader succeeds and the value is placed in the cache, waiting threads receive that value according to the implementation's contract.
- Two distinct keys can usually be computed independently, though actual parallelism depends on the provider's lock granularity.
- If the loader fails, the entry is evicted, a timeout occurs, or the provider does not store the value, recomputation on the next call can certainly happen.

### What should not be promised

- **No distributed lock guarantee:** using Redis or a distributed system does not by itself imply `sync = true` locks across all application instances. You must check the implementation and, if needed, use a dedicated distributed lock/single-flight mechanism.
- **No forever exactly-once guarantee:** errors, expiration, eviction, restarts, or key changes create new misses.
- **Not a substitute for transactions or idempotency:** cache synchronization does not prevent two business commands from writing data concurrently via separate paths.
- **No guaranteed performance improvement:** contention may shift from multiple concurrent queries to requests waiting on a long-running loader; measure throughput and tail latency.

Spring Framework explicitly notes that synchronized caching is an **optional** feature per cache library and recommends checking provider documentation. The `CacheManager` implementations in Spring Framework core support this mechanism, but that does not extend into an equivalent promise for every external provider.

## 8. Runnable Java 17 example: comparing sync vs. default

The experiment runs **Spring Framework 6.2.16**, `ConcurrentMapCacheManager`, and two client threads for the same key `P1`. It needs no database, Redis, or Spring Boot. Two methods have **separate** caches inside the same bean: one method has `sync = true`, and the other uses the default unsynchronized mode. This usage is **valid** because each method has only one operation, one cache name, and no `unless`.

### 8.1. Project structure

```text
spring-cache-sync-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheSyncDemo.java
    └── test/java/demo/cache/CacheSyncDemoTest.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-sync-demo</artifactId>
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
                    <mainClass>demo.cache.CacheSyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` brings in the Spring Cache abstraction and `ConcurrentMapCacheManager`, while pulling in related Spring dependencies transitively. JUnit is used for tests. In a real Spring Boot project, use a compatible parent/BOM instead of pinning individual Spring module versions.

### 8.3. `src/main/java/demo/cache/CacheSyncDemo.java`

```java
package demo.cache;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheSyncDemo {

    public static class QueryService {
        private final AtomicInteger syncLoads = new AtomicInteger();
        private final AtomicInteger plainLoads = new AtomicInteger();

        private final CountDownLatch syncEntered = new CountDownLatch(1);
        private final CountDownLatch syncRelease = new CountDownLatch(1);
        private final CountDownLatch plainEntered = new CountDownLatch(2);
        private final CountDownLatch plainRelease = new CountDownLatch(1);

        @Cacheable(cacheNames = "synchronizedProducts",
                   key = "#p0", sync = true)
        public String loadSync(String id) {
            int n = syncLoads.incrementAndGet();
            syncEntered.countDown();
            await(syncRelease);
            return id + ":v" + n;
        }

        @Cacheable(cacheNames = "normalProducts", key = "#p0")
        public String loadPlain(String id) {
            int n = plainLoads.incrementAndGet();
            plainEntered.countDown();
            await(plainRelease);
            return id + ":v" + n;
        }

        public void awaitSyncEntered() {
            await(syncEntered);
        }

        public void awaitPlainEntered() {
            await(plainEntered);
        }

        public void releaseSync() {
            syncRelease.countDown();
        }

        public void releasePlain() {
            plainRelease.countDown();
        }

        public int syncCount() {
            return syncLoads.get();
        }

        public int plainCount() {
            return plainLoads.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "synchronizedProducts", "normalProducts");
        }

        @Bean
        public QueryService queryService() {
            return new QueryService();
        }
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
    }

    static String runTwo(
            ExecutorService executor,
            Function<String, String> call,
            Runnable waitForLoader,
            Runnable releaseLoader) throws Exception {

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<String> task = () -> {
            ready.countDown();
            await(start);
            return call.apply("P1");
        };

        Future<String> first = executor.submit(task);
        Future<String> second = executor.submit(task);

        await(ready);
        start.countDown();
        waitForLoader.run();
        releaseLoader.run();

        String a = first.get(20, TimeUnit.SECONDS);
        String b = second.get(20, TimeUnit.SECONDS);

        // Sort so output does not depend on thread order.
        return a.compareTo(b) <= 0
                ? "[" + a + "," + b + "]"
                : "[" + b + "," + a + "]";
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(QueryService.class);
            var manager = context.getBean(CacheManager.class);
            ExecutorService executor = Executors.newFixedThreadPool(2);
            try {
                System.out.println("manager="
                        + manager.getClass().getSimpleName());

                System.out.println("sync="
                        + runTwo(executor, service::loadSync,
                                service::awaitSyncEntered,
                                service::releaseSync));
                System.out.println("syncExecutions="
                        + service.syncCount());

                System.out.println("plain="
                        + runTwo(executor, service::loadPlain,
                                service::awaitPlainEntered,
                                service::releasePlain));
                System.out.println("plainExecutions="
                        + service.plainCount());
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

### 8.4. Running the application

Requires JDK 17+, Maven 3.9+, and access to Maven Central on first dependency download. From the project directory:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself** (excluding logs emitted by Maven or Spring):

```text
manager=ConcurrentMapCacheManager
sync=[P1:v1,P1:v1]
syncExecutions=1
plain=[P1:v1,P1:v2]
plainExecutions=2
```

Explanation:

1. Both tasks wait on the `start` signal and then concurrently call the same key `P1`.
2. With `loadSync`, the cache provider coordinates so only one loader has to compute. Both reads receive `P1:v1`; the method body execution count is 1.
3. With `loadPlain`, each miss can run its own loader. `CountDownLatch(2)` inside the method **intentionally holds both executions inside** before allowing them to finish, thus ensuring the experiment demonstrates two overlapping misses under default caching. The two distinct results `v1` and `v2` are sorted before printing so they do not depend on thread ordering.
4. The two caches are **two cache names on two distinct methods**, not two names passed into the same `@Cacheable(sync = true)`. Therefore, the example does not violate the single-cache constraint.
5. This example runs inside **a single JVM** with `ConcurrentMapCacheManager`. It does not prove that a Redis cluster or multiple applications on different machines coordinate loaders the same way.

An intentional timeout in the demo (20 seconds) prevents the test from hanging forever if a worker gets stuck or provider behavior changes. If the machine is overloaded, adjust the timeout for the test; do not treat that timeout as a production SLA.

## 9. Automated testing with JUnit 5

Create `src/test/java/demo/cache/CacheSyncDemoTest.java`:

```java
package demo.cache;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheSyncDemoTest {

    @Test
    void syncUsesSingleLoaderForTheSameKey() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheSyncDemo.Config.class)) {

            var service = context.getBean(
                    CacheSyncDemo.QueryService.class);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                assertEquals(
                        "[P1:v1,P1:v1]",
                        CacheSyncDemo.runTwo(
                                pool,
                                service::loadSync,
                                service::awaitSyncEntered,
                                service::releaseSync)
                );
                assertEquals(1, service.syncCount());
            } finally {
                pool.shutdownNow();
            }
        }
    }

    @Test
    void defaultModeCanComputeSameKeyTwiceConcurrently()
            throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheSyncDemo.Config.class)) {

            var service = context.getBean(
                    CacheSyncDemo.QueryService.class);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                assertEquals(
                        "[P1:v1,P1:v2]",
                        CacheSyncDemo.runTwo(
                                pool,
                                service::loadPlain,
                                service::awaitPlainEntered,
                                service::releasePlain)
                );
                assertEquals(2, service.plainCount());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Run:

```bash
mvn -q test
```

Expected result: JUnit tests pass and Maven returns exit code 0. With `-q`, the line "BUILD SUCCESS" may not be printed. The test uses a real ApplicationContext and Spring bean instead of `new QueryService()`; only then can the cache annotation be applied. The test demonstrates only a specific provider and single-process concurrency.

**Testing note:** the second test intentionally waits for both default method bodies to enter the loader; that is a concurrency harness, **not** a production business-code pattern. When writing CI tests, include timeouts and deliberate executor cleanup to avoid leaking threads if an assertion fails.

## 10. Consequences of violating each constraint

| Configuration pattern | Valid/invalid | Remediation |
| --- | --- | --- |
| `@Cacheable(cacheNames = "a", sync = true)` | Valid under the three constraints | Verify provider support and key |
| `@Cacheable(cacheNames = {"a","b"}, sync = true)` | Invalid: two caches | Choose one logical cache or design multi-tiering inside the provider |
| `@Cacheable(cacheNames = "a", sync = true, unless = "#result == null")` | Invalid: `unless` | Remove `unless` or remove `sync`; pick another mechanism if both are required |
| `@Cacheable(cacheNames = "a", sync = true, condition = "#p0 != null")` | Valid under the three constraints | Method must handle null input when condition is false |
| `@Cacheable(sync = true)` + `@CachePut` on the same method | Invalid: combined operations | Separate reads and updates |
| `@Cacheable(sync = true)` + `@CacheEvict` on the same method | Invalid: combined operations | Place eviction on a separate update method |
| `@Caching` grouping sync cacheable and put | Invalid: `@Caching` does not alter the rule | Do not combine synchronized cache operations |
| Method `find` sync cacheable; separate method `update` cache put | Valid under the three constraints | Align key, transaction, and freshness |

Even when the table marks a pattern "valid," configuration can still fail for other reasons such as an unsupported provider, null keys, wrong cache name, broken SpEL getters, or bypassing the Spring proxy.

## 11. Common misconceptions

### 11.1. "sync = true locks the entire method"

Incorrect. The goal is to **coordinate computation per cache key** within the provider's scope, not to declare a Java `synchronized` lock covering all calls for every key. Independent keys can be computed in parallel; only the same key is meant to be coordinated. Actual locking behavior depends on the implementation.

### 11.2. "sync always works identically with Redis, Caffeine, and ConcurrentMap"

No. The API may look the same, but each provider's locking differs; it might apply only within one process or have different atomicity characteristics. Read the corresponding documentation, write tests against the deployed provider, and check behavior across multiple concurrent application instances.

### 11.3. "With sync enabled, eviction or TTL is no longer needed"

Wrong. Sync addresses **contention when the same key is missing**. It does not guarantee cached data stays fresh, does not determine TTL, and does not clear caches after updates. A stale hit will still be returned without an invalidation policy.

### 11.4. "Use condition to replace unless"

Wrong if the rule depends on `#result`. `condition` evaluates before invocation; `unless` evaluates after invocation. You can only use `condition` to decide based on available inputs/metadata at entry time, not to filter a result that has not been computed yet.

### 11.5. "One cache means the entire application can only have one cache"

Wrong. A `CacheManager` can hold many caches; each `@Cacheable(sync = true)` method must simply resolve **one cache** for its operation.

### 11.6. "No combining operations means @CacheEvict cannot exist in the application"

Wrong. You must not combine other cache operations **on the same method** that has a synchronized cacheable. A separate update method with `@CacheEvict` or `@CachePut` is normal and usually recommended.

### 11.7. "With sync, every access to the same key runs the method once forever"

Wrong. A cache entry can expire, be evicted, be lost on restart, the loader can throw an exception, or two nodes may not share coordination. `sync = true` does not equate to system-wide exactly-once execution.

## 12. Checklist for using sync safely

1. **Scope:** does the method truly read a cacheable value with no mandatory side effects?
2. **One cache:** `cacheNames` has a single name; any `CacheResolver` also resolves a single cache for the operation.
3. **No unless:** do not include `unless` on a sync annotation, even an always-false expression.
4. **No combined operations:** no `@CachePut`, `@CacheEvict`, or extra cacheable on the same method; `@Caching` does not exempt this rule.
5. **Key:** identical data must produce identical keys; keys must distinguish tenant, locale, version, and permissions when they affect the output.
6. **Condition:** if present, rely only on pre-invocation data; the method itself must still handle invalid input when caching is bypassed.
7. **Provider:** identify the actual `CacheManager` and `Cache`; read the provider's guidance on `get(key, Callable)`/synchronization.
8. **Concurrency:** test with multiple threads on the same key, using barriers and body execution counts; test distinct keys too.
9. **Multi-instance:** do not assume a single-JVM test proves distributed locking.
10. **Freshness and failures:** configure appropriate TTL/eviction, and handle loader exceptions, timeouts, transactions, and post-expiration load.

## 13. Self-check exercises

**Q1.** What is wrong with `@Cacheable(cacheNames = {"a","b"}, sync = true)`, even if each cache is valid on its own?  
**Answer:** A synchronized operation can resolve only one cache; specifying two cache names violates the constraint.

**Q2.** To avoid caching `null` results, can you add `unless = "#result == null"` when `sync = true`?  
**Answer:** No. You must redesign, drop sync to use unless, or handle synchronization/result filtering via another mechanism; null-value support also depends on the provider.

**Q3.** Does `@Cacheable(sync = true, condition = "#p0 != null")` violate any of the three constraints?  
**Answer:** No, provided there is a single cache and no combined operations/`unless`; when condition is false, the method runs directly and must handle null.

**Q4.** Method `find` has a synchronized cacheable, and a separate method `update` has a cache put targeting the same cache name. Is that "combining operations"?  
**Answer:** No. The no-combining constraint applies to **the same method invocation**, not to independent methods sharing a cache.

**Q5.** Two application instances connect to Redis. Can you claim `sync = true` locks system-wide?  
**Answer:** No. You must inspect the exact provider semantics and configuration; guaranteeing cross-instance single-flight may require a distributed lock or custom design.

## Official Sources

- [Spring Framework — Cacheable JavaDoc (sync and the three constraints)](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Cache interface JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html)

**Conclusion:** `@Cacheable(sync = true)` is a tool to reduce concurrent computation load for **the same cache key** when supported by the provider. In return, Spring requires **one cache**, **no `unless`**, and **no additional cache operations on the same method**. When business requirements conflict with these three constraints, choose another design rather than trying to work around the annotation.