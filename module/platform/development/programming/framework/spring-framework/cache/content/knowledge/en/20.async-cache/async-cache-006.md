# Requiring Stores to Support Retrieval via CompletableFuture in Spring Cache

## 1. Why Does This Problem Matter?

In Spring Cache, a business method may return a `CompletableFuture<T>`, yet **that does not mean every cache store supports asynchronous retrieval**. Starting in Spring Framework **6.1**, the cache abstraction includes retrieval APIs using `CompletableFuture`. To leverage this mechanism properly, the `Cache` implementation must support the corresponding `retrieve(...)` methods rather than only implementing the synchronous `get(...)` methods.

Two requirements must be distinguished:

1. **Application returning asynchronous results:** a service returns `CompletableFuture<String>`; Spring can cache **the completed value** of the future and construct a future on cache hits.
2. **Cache store providing an asynchronous retrieval API:** `cache.retrieve(key)` returns a `CompletableFuture` representing the cache lookup operation; the `cache.retrieve(key, valueLoader)` form also supports loading the value on a miss.

A provider supporting synchronous `Cache.get(key)` does **not automatically** support both variants of `Cache.retrieve(...)`. Some providers support them out of the box; some require enabling async mode; and some do not implement them and throw `UnsupportedOperationException`.

### What You Will Learn

- The roles of `CacheManager`, `Cache`, `@Cacheable`, and `CompletableFuture`.
- The contracts of `Cache.retrieve(Object)` and `Cache.retrieve(Object, Supplier<CompletableFuture<T>>)`.
- How to interpret an immediate `null` return, a future completing with `null`, and cached-null.
- Practical conditions for `@Cacheable` to work with `CompletableFuture<T>` in Spring 6.1+.
- Example providers: `ConcurrentMapCacheManager` supporting future-based retrieval and `CaffeineCacheManager` requiring appropriate async cache mode configuration.
- Limitations of `@Cacheable(sync = true)`, concurrency, exceptions, null, transactions, and reactive types.
- How to write a runnable Java 17 program using Spring Framework to **verify a provider** and compare cache hits/misses.
- How to diagnose and test before swapping cache providers in production.

## 2. Seeing the Three Asynchronous Layers Clearly

Consider three distinct components:

~~~text
                          Caller
                            |
                            v
               Spring-managed proxy
                            |
                            v
              @Cacheable / CacheInterceptor
                            |
                            v
                       CacheManager
                            |
                  getCache("names")
                            |
                            v
                      Cache object
                            |
                +-----------+-----------+
                |                       |
                v                       v
       sync get(key)          retrieve(key) async API
        -> ValueWrapper       -> CompletableFuture<?>
                |                       |
                +-----------+-----------+
                            |
                      Entry value
                            |
                            v
               String / DTO / actual result
~~~

The layers:

**Layer 1 — Business method:** `CompletableFuture<String> find(String id)` represents a computation that may complete in the future. The final business value is `String`.

**Layer 2 — Cache abstraction:** `@Cacheable` is processed by Spring. Starting in Spring 6.1+, it recognizes future return types, can put **the result when the future completes** into the cache, and return a suitable future on cache hits. Do not assume the cache always retains the exact `CompletableFuture` instance from the first call.

**Layer 3 — Cache provider:** `Cache.retrieve(key)` supports entry access via a future. Only certain providers or configurations satisfy this contract. Asynchrony in the service does not substitute for capabilities of the cache implementation.

### Comparing `get` and `retrieve`

| API | Return Type | Meaning |
| --- | --- | --- |
| `cache.get(key)` | `Cache.ValueWrapper` or `null` | Look up entry via synchronous API |
| `cache.get(key, String.class)` | `String` or `null` | Look up entry and convert type via synchronous API |
| `cache.get(key, Callable<T>)` | `T` | Synchronously look up or load via loader |
| `cache.retrieve(key)` | `CompletableFuture<?>` or possibly `null` | Look up entry via future-based API |
| `cache.retrieve(key, Supplier<CompletableFuture<T>>)` | `CompletableFuture<T>` | Asynchronously look up/load value when needed |

**Do not confuse:** `CacheManager.getCache("names")` obtains the **cache region**, whereas `Cache.retrieve("A")` fetches an **entry** within that region. Cache name and key are two different levels.

## 3. Contract of `Cache.retrieve(Object key)`

In Spring Framework 6.1+, `org.springframework.cache.Cache` includes a method like:

~~~java
@Nullable
CompletableFuture<?> retrieve(Object key);
~~~

This is a **simplified API signature**, not a standalone Java file. Meaning:

- Input `key` is the entry key you want to look up.
- If the provider supports it, the result can be a `CompletableFuture<?>` that completes when the lookup result is ready.
- **The return value of `retrieve` itself can be `null`:** the provider knows immediately at call time that the key has no mapping (*immediate miss*).
- If a future is returned, the future may complete with `null` when the lookup finds no mapping (*late miss*).
- A cached-null (when the provider allows caching null business results) may be represented by a `ValueWrapper` containing null to distinguish it from a miss; details must follow the provider's contract.
- If the implementation does not support future-based retrieval, it may throw `UnsupportedOperationException`, because the interface's default method does not force legacy providers to implement this capability.

### Proper Miss-Handling Rule

Do not write directly:

~~~java
Object value = cache.retrieve("A").join();
~~~

because if `retrieve("A")` returns `null` immediately, you will hit a `NullPointerException`. A basic check looks like:

~~~java
CompletableFuture<?> future = cache.retrieve("A");

if (future == null) {
    System.out.println("MISS known immediately");
} else {
    Object result = future.join();
    if (result == null) {
        System.out.println("MISS determined asynchronously");
    } else {
        System.out.println("An entry was returned");
    }
}
~~~

This snippet is **illustrative** and assumes `cache` is an already-obtained `Cache`, not a standalone file. When a provider supports cached-null and returns a `Cache.ValueWrapper`, unwrap and inspect the wrapper/value per the API; **do not cast every non-null result to a business DTO blindly**.

### Three Important Kinds of Null

~~~text
CacheManager.getCache("names") == null
    -> could not obtain cache region.

Cache.retrieve("A") == null
    -> provider knows immediately that key A has no mapping.

Cache.retrieve("A") != null
    and returnedFuture.join() == null
    -> lookup completed without a direct value;
       usually a late-determined miss,
       check provider and cached-null contract.

Returned future completes with ValueWrapper(null)
    -> one representation of cached-null (HIT).
~~~

The synchronous `cache.get(key)` uses `ValueWrapper` to distinguish a miss from a hit with null. With the async form, read the version/provider Javadoc and test the null policy instead of extrapolating entirely from typed `get` or `join()`.

### Does `join()` Make the Call "Non-Blocking"?

No. `CompletableFuture.join()` **can block the current thread** until the future completes. In study examples `join()` can be used to print deterministic results; in real asynchronous applications prefer `thenApply`, `thenCompose`, `whenComplete`, or reactive pipeline integration instead of blocking request threads.

## 4. Contract of `retrieve(key, valueLoader)`

Spring also supports the variant:

~~~java
<T> CompletableFuture<T> retrieve(
        Object key,
        Supplier<CompletableFuture<T>> valueLoader);
~~~

This is a **shortened signature**, not a standalone Java file.

Key differences:

- `retrieve(key)` only queries the cache; the caller decides what to do on a miss.
- `retrieve(key, valueLoader)` lets the cache coordinate **lookup + loading the value on a miss**.
- `valueLoader` is a `Supplier` returning `CompletableFuture<T>`, **not** `Supplier<T>`; the loader must produce/fetch the result per the async contract.
- The return value is `CompletableFuture<T>`, which can be composed with the rest of the processing.
- The implementation/provider determines coordination of concurrent requests for the same key, atomicity, and when the loader executes; **do not promise that every provider will invoke the loader only once across the entire cluster**.
- Errors from the loader or backend can cause the future to complete exceptionally (or the method to throw an exception); calling code must handle failures deliberately.

Example:

~~~java
CompletableFuture<String> result = cache.retrieve(
    "A",
    () -> remoteClient.fetchNameAsync("A")
);
~~~

Illustrative snippet: `cache` and `remoteClient` must be defined by the application; `fetchNameAsync` returns `CompletableFuture<String>`. Do not wrap a synchronous blocking I/O task in `CompletableFuture.completedFuture(...)` and claim you have non-blocking I/O.

### Principle for Distinguishing Cache Hits and Loaders

~~~text
retrieve("A", asyncLoader)
             |
             v
       Check entry
         /       \
       HIT       MISS
        |          |
        v          v
     future     asyncLoader.get()
       value       |
                   v
                future T
                   |
                   v
               cache value
~~~

This is a **logical model**. Real providers may run lookups/loaders on their own executors or future mechanisms; timing and concurrency must be tested. In some implementations, data retrieval may run on a worker thread even though the API returns a future.

## 5. Providers Must Actually Support These Two APIs

A provider may implement the synchronous methods and work fine with `@Cacheable` returning `String`, yet when you switch the method to `CompletableFuture<String>`, the asynchronous retrieval requirement becomes different.

### 5.1. `ConcurrentMapCacheManager`

Spring Framework's `ConcurrentMapCacheManager` manages `ConcurrentMapCache` instances and supports `CompletableFuture`-based retrieval. This is a good choice for demos/tests because it requires no Redis, Caffeine, network, or heavy dependency setup.

However:

- The cache still stores data **in the current JVM's memory**.
- Returning `CompletableFuture` from the API **does not turn local memory into a distributed/asynchronous network store**.
- It has no built-in TTL, size-based eviction, or persistence.
- Do not use `ConcurrentMapCache`'s behavior to infer capabilities of all other providers.

### 5.2. `CaffeineCacheManager`

`CaffeineCacheManager` has **async cache mode**. In Spring Framework versions supporting `setAsyncCacheMode(true)`, when retrieving `CompletableFuture` through the Caffeine provider, configure the appropriate mode.

Configuration snippet (requires `spring-context-support`, Caffeine dependency, and imports):

~~~java
@Bean
public CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("names");
    manager.setAsyncCacheMode(true);
    manager.setCaffeine(
            Caffeine.newBuilder()
                    .maximumSize(1000)
                    .expireAfterWrite(Duration.ofMinutes(10))
    );
    return manager;
}
~~~

This snippet **does not run standalone**, as it requires:
- `org.springframework.cache.caffeine.CaffeineCacheManager`.
- `com.github.benmanes.caffeine.cache.Caffeine`.
- `java.time.Duration`.
- `@Bean` and compatible Spring/Caffeine dependencies.

Merely creating `CaffeineCacheManager` and assuming async mode is already on can lead to errors or unexpected behavior. Certain ways of registering a custom `AsyncCache` also have their own contracts; check the Javadoc for your version.

### 5.3. Other Providers

For Redis/JCache/in-house providers or multi-layer wrappers, **do not infer from the provider name** that `retrieve` is always ready. Support can depend on:

- Spring Framework and integration library versions.
- Actual asynchronous capabilities of the underlying client/backend.
- How `CacheManager` and `Cache` are configured.
- Whether the provider implements **both** `retrieve(key)` and `retrieve(key, valueLoader)` or only partially.
- Whether outer decorators delegate the API properly.
- Policies for serializing cached-null, backend errors, and timeouts.

An accurate check is usually an **integration test against the application's actual `Cache` bean**, not the manager's list of cache names.

### Decision Table

| Scenario | What to Do |
| --- | --- |
| Using `ConcurrentMapCacheManager` for study | Test `retrieve(...)` directly, check hit/miss |
| Using Caffeine | Enable async cache mode and test with the specific manager configuration |
| Using Redis or another provider | Read Javadoc/version, test `retrieve` methods on the running provider |
| Wrapper/decorator layer present | Verify the wrapper supports/delegates both overloads |
| Only synchronous methods needed | `@Cacheable` returning `T` and `Cache.get` are usually simpler |
| End-to-end futures needed | `CompletableFuture<T>` + async-compatible provider, avoid blocking threads |

## 6. `@Cacheable` on Methods Returning `CompletableFuture<T>`

Starting in Spring Framework 6.1, the cache abstraction knows how to handle several asynchronous return types.

~~~java
@Cacheable(cacheNames = "names", key = "#p0")
public CompletableFuture<String> findName(String id) {
    return gateway.fetchNameAsync(id);
}
~~~

This snippet is illustrative; `gateway` belongs to the application.

On a **cache miss**, the method can return an incomplete `CompletableFuture<String>`. Spring observes completion and caches **the computed `String` value** when the future completes successfully. On a **cache hit**, Spring can return a `CompletableFuture<String>` representing the cached value.

Do not assume that:
- The cache always keeps the exact original **`CompletableFuture` object** and its identity.
- The cache put happens before the computation inside the future finishes.
- Any arbitrary provider supports Spring 6.1 async cache operations.
- A `CompletableFuture` return type creates an executor or guarantees non-blocking behavior automatically.

### Timeline

~~~text
Caller invokes findName("A") via Spring proxy
                  |
                  v
          Cache lookup by key
             /              \
           HIT              MISS
            |                 |
            v                 v
      Cached value     Call target method
            |                 |
            v                 v
   Return suitable        CompletableFuture<String>
   CompletableFuture           |
                               v
                      Completes successfully
                               |
                               v
                      Put "A" -> String value
                               |
                               v
                         Caller receives value
~~~

For futures that complete exceptionally, the application must handle errors; do not treat failure as a normal value to store. If a service returns `CompletableFuture.completedFuture(null)`, the cache's null policy and `unless` must be designed explicitly.

### When Using `@CachePut` and `@CacheEvict`

Other annotations can adapt to asynchronous return types in Spring Framework 6.1+, though put/evict timing and error behavior depend on the operation/implementation. In particular, do not assume a `void` method launching fire-and-forget async work lets Spring know when that work completes. If business logic returns a future, clarify the lifecycle and test invalidation after the future completes, as well as transaction boundaries.

## 7. What More Does `@Cacheable(sync = true)` Require?

~~~java
@Cacheable(
    cacheNames = "names",
    key = "#p0",
    sync = true
)
public CompletableFuture<String> findName(String id) {
    return gateway.fetchNameAsync(id);
}
~~~

This is an illustrative snippet.

The goal of `sync = true` is to coordinate calls hitting the same miss/key so multiple loaders do not compute the same value redundantly. For async results, the provider generally needs to implement the **`retrieve(key, valueLoader)`** variant capable of coordinating data loading.

Points to remember:

- `sync=true` is a hint/contract with the cache provider; actual synchronization capability depends on the implementation.
- There is no single-flight guarantee across all nodes of a cluster merely because this annotation appears.
- Spring enforces restrictions with `sync=true`, such as using only a single cache region for the operation, no `unless`, and no combining multiple cache operations in the same annotation setup.
- If the provider does not support future-based retrieval/loading, `sync=true` does not fix that; instead it may expose the limitation more clearly.
- Do not confuse `sync=true` with `@Async`, transaction isolation, or a distributed lock.

### Why Is a Single-Threaded Test Not Enough?

A sequential unit test can prove a cache hit on the second call, yet **cannot** prove the loader runs only once when 20 concurrent requests miss the same key. You need an integration/concurrency test with a `CountDownLatch` or barrier, measuring invocation counts and verifying the real provider's policy.

## 8. Runnable Java 17 Demo: Verifying `CompletableFuture` Retrieval

Example uses **Java 17**, **Maven**, **Spring Framework 6.2.16**, and `ConcurrentMapCacheManager`. No Spring Boot, Caffeine, or database required.

The demo verifies:

1. `retrieve("A")` when no entry exists is handled under both possibilities: returning null immediately or a future completing with null.
2. `@Cacheable` on a method returning `CompletableFuture<String>` works with a manager supporting the async API.
3. A second call with the same key hits the cache and does not re-run the method body.
4. `Cache.get("A", String.class)` sees the **resolved `String`**, rather than retaining the raw `CompletableFuture`.
5. `Cache.retrieve("A")` returns a future holding the cached value.
6. `retrieve(key, valueLoader)` loads on miss and does not re-invoke the loader on hit in the sequential example.
7. `Cache.evict("A")` forces the next call to reload.

### 8.1. Directory Structure

~~~text
future-cache-demo/
├── pom.xml
└── src/main/java/demo/FutureCacheDemo.java
~~~

### 8.2. `pom.xml` File

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>future-cache-demo</artifactId>
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

### 8.3. `src/main/java/demo/FutureCacheDemo.java` File

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class FutureCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("names");
        }

        @Bean
        public NamesService namesService() {
            return new NamesService();
        }
    }

    public static class NamesService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "names", key = "#p0")
        public CompletableFuture<String> name(String id) {
            int n = calls.incrementAndGet();
            System.out.println("LOAD " + id + " #" + n);
            return CompletableFuture.completedFuture(
                    "name-" + id + "-v" + n);
        }

        public int calls() {
            return calls.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CacheManager manager =
                    context.getBean(CacheManager.class);
            NamesService service =
                    context.getBean(NamesService.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("names"));

            // Allows both immediate miss and late miss.
            CompletableFuture<?> before = cache.retrieve("A");
            System.out.println("startMiss="
                    + (before == null || before.join() == null));

            System.out.println("first="
                    + service.name("A").join());
            System.out.println("second="
                    + service.name("A").join());
            System.out.println("stored="
                    + cache.get("A", String.class));

            CompletableFuture<?> hit = cache.retrieve("A");
            System.out.println("retrieved="
                    + Objects.requireNonNull(hit).join());

            AtomicInteger supplierCalls = new AtomicInteger();
            CompletableFuture<String> manual1 = cache.retrieve(
                    "manual",
                    () -> {
                        int n = supplierCalls.incrementAndGet();
                        System.out.println("SUPPLIER #" + n);
                        return CompletableFuture.completedFuture(
                                "manual-value");
                    });
            System.out.println("manual1=" + manual1.join());

            CompletableFuture<String> manual2 = cache.retrieve(
                    "manual",
                    () -> {
                        int n = supplierCalls.incrementAndGet();
                        System.out.println("UNEXPECTED SUPPLIER #" + n);
                        return CompletableFuture.completedFuture(
                                "wrong-value");
                    });
            System.out.println("manual2=" + manual2.join());
            System.out.println("supplierCalls="
                    + supplierCalls.get());

            cache.evict("A");
            System.out.println("afterEvictMissing="
                    + (cache.get("A") == null));
            System.out.println("third="
                    + service.name("A").join());
            System.out.println("serviceCalls=" + service.calls());
        }
    }
}
~~~

### 8.4. Running the Program

Requires JDK 17+ and Maven; from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.FutureCacheDemo
~~~

Expected stdout **explicitly printed by the program**, excluding separate Maven logs:

~~~text
startMiss=true
LOAD A #1
first=name-A-v1
second=name-A-v1
stored=name-A-v1
retrieved=name-A-v1
SUPPLIER #1
manual1=manual-value
manual2=manual-value
supplierCalls=1
afterEvictMissing=true
LOAD A #2
third=name-A-v2
serviceCalls=2
~~~

### 8.5. Why Do These Output Lines Matter?

**`startMiss=true`:** the code does not assume `retrieve("A")` always returns a non-null future; it properly handles both immediate and late misses.

**`LOAD A #1` appears only before `first`:** on the first call no entry exists, so the target runs. `second` returns `name-A-v1` without printing `LOAD` — indicating a cache hit.

**`stored=name-A-v1`:** synchronous typed retrieval with `String.class` sees the completed `String` value. Lesson: do not treat a future return type as meaning the cache retains the original future object itself.

**`retrieved=name-A-v1`:** the provider returns a `CompletableFuture<?>` for the existing entry, and calling `join()` yields the value.

**`SUPPLIER #1` exactly once in the `manual` branch:** the `retrieve(key, loader)` variant runs the callback on a miss; the next call with the same key returns from cache and does not run the second callback. This demonstrates **sequential behavior in the demo**; it does not replace concurrency tests.

**`afterEvictMissing=true` then `LOAD A #2`:** evict deletes the mapping; the next call to the service must reload and return the new version.

### 8.6. Why Does the Demo Use `completedFuture`?

`CompletableFuture.completedFuture(...)` keeps stdout **deterministic and easy to verify**, without introducing thread-pool races. It proves Spring handles the `CompletableFuture` return type and the cache provider implements the `retrieve` API. The demo **does not** prove your database/network calls are non-blocking. In real applications, the future may come from an async database driver/client or executor, and tests must verify specific timeouts/errors/cancellation.

### 8.7. Spring Proxy Remains a Mandatory Prerequisite

`@EnableCaching` turns on annotation-based caching. `NamesService` is obtained from Spring's `ApplicationContext`; calls go through the proxy/interceptor. If you do:

~~~java
NamesService service = new NamesService();
service.name("A");
service.name("A");
~~~

this is an **illustrative snippet outside Spring**; two direct calls are not cached merely because the method has `@Cacheable`. Likewise, `this.name("A")` inside the same bean can bypass the proxy in proxy mode.

## 9. Errors When a Provider Does Not Support Async Retrieval

Symptom you may encounter when swapping providers or misconfiguring:

~~~text
java.lang.UnsupportedOperationException
  ...
  Cache.retrieve(...)
~~~

This illustrates the symptom and **does not claim every provider throws the exact same stack trace**. The common cause is a cache implementation supporting only synchronous `get`/`put` APIs or a wrapper failing to delegate `retrieve`.

### What Must Be Checked?

1. Do the Spring Framework versions support `Cache.retrieve` and future return types on cache annotations? (6.1+).
2. What implementation is the actual `CacheManager` bean?
3. What type of `Cache` does `getCache(cacheName)` return? It could be wrapped by a decorator.
4. Does the provider support `retrieve(key)`?
5. Does the provider support `retrieve(key, loader)`, especially when using `sync=true`?
6. For Caffeine configuration, is `setAsyncCacheMode(true)` enabled?
7. Are the cache name, key, value type, and serialization valid?
8. Is `CompletableFuture.join()` called too early, causing thread blocking or deadlocks?
9. Are there exception/timeout/cancellation/null-policy issues preventing the future from completing as expected?

### A Direct API Probe Snippet

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("names"));

try {
    CompletableFuture<?> test = cache.retrieve("probe-key");
    // test may be null if provider knows immediately the key is absent.
    System.out.println("Async retrieval method supported");
} catch (UnsupportedOperationException ex) {
    System.out.println("Async retrieval is not supported");
}
~~~

This snippet **does not run standalone**: it needs `CacheManager`, `Cache`, `Objects`, and `CompletableFuture` from the application. It only tests the `retrieve(key)` overload at probe time; it has not tested the loader overload or the real backend when an entry exists. Do not use ad-hoc probes in production as your sole check, and never generate cache names from user input.

### Is a Fallback Safe?

Do not catch every exception and fall back to blocking synchronous I/O to "patch" async errors. Better options when a provider does not satisfy the contract:

- Configure or upgrade to a supporting provider.
- Use another verified manager.
- Design a synchronous service with a synchronous cache if business requirements allow.
- Use a cache adapter designed and thoroughly tested for timeouts, concurrency, and error policies.

Wrapping synchronous `Cache.get` in `CompletableFuture.completedFuture(...)` **does not make cache operations non-blocking**; it merely changes the return type after doing synchronous work.

## 10. Null, Exceptions, and Cancellation in Futures

### 10.1. Future Completing with `null`

~~~java
return CompletableFuture.completedFuture(null);
~~~

When returned from a `@Cacheable` method, whether cached-null is stored depends on the `Cache` provider and `unless` configuration. For example:

~~~java
@Cacheable(
    cacheNames = "names",
    key = "#p0",
    unless = "#result == null"
)
public CompletableFuture<String> maybeFind(String id) {
    return CompletableFuture.completedFuture(null);
}
~~~

Illustrative snippet; when the final result is null, `unless` is intended to avoid caching null. Depending on the provider, `null` is represented by a marker or rejected. Do not use `retrieve(key).join()==null` as sole proof that no entry exists when cached-null is enabled.

### 10.2. Exceptions and Exceptionally Completed Futures

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("backend unavailable"));
~~~

If the loader/future terminates with an error, the caller must handle `CompletionException`/cause per the contract. Do not expect a cache hit to cure an ongoing business failure, nor cache exceptions as normal values unless explicitly designed to do so.

Handling example:

~~~java
service.name("A")
    .whenComplete((value, error) -> {
        if (error != null) {
            logFailure(error);
        } else {
            useValue(value);
        }
    });
~~~

This snippet needs `service`, `logFailure`, and `useValue` in the application. Not a standalone file. With `join()`, exceptions are usually wrapped in `CompletionException`.

### 10.3. Cancellation

`CompletableFuture.cancel(...)` is a cancellation state on the future; it does not automatically stop backend I/O or delete cache entries. Cancellation and cleanup semantics must be designed per client/provider. Do not assume canceling one future obtained from the cache also deletes the cache entry or cancels the same future used by all callers.

### 10.4. Timeouts

With remote backends, timeouts are needed on the client/cache alongside explicit fallback policies. When a callback supplier or backend hangs, the future can also hang without a timeout. Use mechanisms like `orTimeout` (where appropriate) and monitor pending futures, latency, and exception rates. Timing out a future at the application layer does not replace driver-level I/O timeouts.

## 11. How Do Reactive `Mono` and `Flux` Relate?

Spring Framework 6.1+ also adapts to supported reactive return types, typically through corresponding `CompletableFuture`-based retrieval support on the cache provider. However, learners should keep in mind:

- `Mono<T>` represents one asynchronous result; Spring can cache the value when the `Mono` completes and construct a matching publisher on a hit.
- `Flux<T>` can be **collected into a list** for caching and then reconstructed as a stream from that list; this is not element-by-element caching like a streaming buffer.
- Do not view Spring Cache annotations as a universal solution for large or infinite streaming workloads.
- If the cache store does not provide the asynchronous retrieval Spring requires, returning `Mono`/`Flux` from the method will not fix it on its own.
- Do not block the event loop with `join()` or expensive synchronous cache operations. Use an appropriate provider architecture and execution model.

If the application uses Reactor, test with your specific Reactor and Spring versions. The Java 17 demo in Section 8 focuses solely on `CompletableFuture` to avoid adding unnecessary dependencies.

## 12. Transactions, Context, and Multi-Instance Deployments

### 12.1. Uncommitted Transactions

A future can complete after a database transaction ends. Putting into the cache from a future result can therefore happen **at a different time** than when the method originally returned the future. If data can roll back or transactions live at another layer, test data consistency and adopt an appropriate after-commit/invalidation strategy. Do not assume `@Transactional` automatically synchronizes every cache put with the database.

### 12.2. Thread-Local Context

A `CompletableFuture` can complete on a different thread. Tenant, security principal, MDC, or transaction context bound to `ThreadLocal` is not automatically propagated across all executors. If cache routing/keys depend on context, design reliable capture/propagation and prevent cross-tenant data leaks.

### 12.3. Local Cache vs. Distributed Cache

`ConcurrentMapCacheManager` shares data only within the same JVM. Retrieving via `CompletableFuture` **does not** make two application instances share a cache region. If cross-replica consistency is needed, choose the right backend, partitioning, eviction propagation, and transaction/invalidation strategy.

### 12.4. Is the Backend Truly Non-Blocking?

A method returning `CompletableFuture` may still do synchronous work before returning the future. A provider may construct a completed future from memory very quickly. Having a future signature is **an API contract**, not proof of non-blocking I/O, throughput, or latency. Measure thread usage, blocking time, and I/O profiles separately.

## 13. Testing Providers and Concurrency

Minimum tests:

| Scenario | Setup | What Must Be Proven |
| --- | --- | --- |
| Async retrieval supported | `Cache.retrieve("absent")` | Does not throw `UnsupportedOperationException`; handles immediate/late miss |
| Loader overload | `retrieve("A", loader)` | Future completes with value and entry is cached per contract |
| Hit | Two calls with same key | Loader/body does not run again in sequential case |
| `@Cacheable` future | Method returns `CompletableFuture<String>` | Cache stores value after completion; hit builds a new/suitable future |
| Delayed completion | Loader returns pending future | Does not assume value is cached prior to completion |
| Failed completion | Future completes exceptionally | Does not wrongly return stale/partial value; error handled |
| Cached-null | Provider allows storing null | Distinguishes miss from null hit per API |
| Eviction | Evict key then call again | Reloads for the same key |
| `sync=true` | Multiple callers miss concurrently | Verifies actual single-flight semantics of the provider |
| Caffeine async mode | Toggle async mode on/off | Identifies real cache configuration and behavior |
| Multi-node | Multiple instances | Does not confuse local future retrieval with distributed |
| Transaction | Loader inside rolled-back transaction | Does not cache uncommitted data per design |
| Timeout | Slow/hanging backend | Future times out per policy; does not hold threads indefinitely |

### Concurrency Tests Must Avoid Flakiness

To test two callers on the same key, use a barrier or `CountDownLatch` to control start timing. Count actual loader executions instead of guessing from execution time. If the provider only coordinates within the local JVM, do not claim cross-instance single-flight.

### Do Not Test Only Synchronous `get`

A provider can pass every `Cache.get(key)` and `@Cacheable` `String`-returning test yet fail when using `retrieve(key, loader)` or a method returning `CompletableFuture<String>`. Add **dedicated tests for async APIs** when upgrading Spring/providers or changing cache managers.

## 14. Common Mistakes

**Mistake 1 — "The method returns CompletableFuture so the cache is automatically async."** No. The provider must support future-based retrieval per the Spring 6.1+ API.

**Mistake 2 — "Cache.get(key) works so Cache.retrieve(key) definitely works."** No. A cache implementation may not implement the async API.

**Mistake 3 — "retrieve(key) always returns a non-null CompletableFuture."** False. The contract allows returning `null` when the provider knows a miss immediately.

**Mistake 4 — "A future completing with null always means cache miss."** Not necessarily: cached-null may involve `ValueWrapper`, and representation depends on the provider.

**Mistake 5 — "Calling join() is still non-blocking."** False; `join()` can block the current thread.

**Mistake 6 — "sync=true guarantees only one request cluster-wide runs the loader."** No general guarantee; depends on the provider and coordination scope.

**Mistake 7 — "Switching to CaffeineCacheManager is all you need."** Not enough if async retrieval is required; enable async cache mode per the matching Spring/Caffeine version and test.

**Mistake 8 — "The cache stores the CompletableFuture object and returns the exact old instance next time."** Spring cache adaptation targets **the completed value**, with no commitment to preserve future identity.

**Mistake 9 — "Wrapping synchronous get in completedFuture makes the backend non-blocking."** False; the backend already queried synchronously before the future was constructed.

**Mistake 10 — "Every provider supports both retrieve and retrieve-with-loader."** Do not assume; test both overloads, especially with `sync=true`.

## 15. Self-Check Questions

**1. Why does `@Cacheable` returning `CompletableFuture` demand more than `@Cacheable` returning `String`?**

Because the framework needs to work with completed values and future-based cache retrieval; the provider must satisfy the supporting API or appropriate async configuration.

**2. How does `Cache.retrieve(key)` differ from `Cache.get(key)`?**

`retrieve` returns a future (or possibly null on an immediate miss) to express async retrieval; `get` returns a `ValueWrapper` or null directly.

**3. Why check for a null return before calling `join()`?**

Because the contract allows immediate misses where `retrieve(key)` itself returns null, leaving no future to join.

**4. When is `retrieve(key, valueLoader)` useful?**

When you want the cache provider to coordinate looking up an entry and loading from a `CompletableFuture<T>`-returning loader on a miss; it can reduce boilerplate and support provider-level concurrency coordination.

**5. Does Spring store a `CompletableFuture` object or the final value?**

With async-supporting cache annotations in Spring 6.1+, it adapts to **the completed value**; do not rely on the identity of the original future.

**6. What should be watched with Caffeine?**

Use async cache mode (`setAsyncCacheMode(true)`) and matching dependencies/versions; then test real cache behavior.

**7. Why is `sync=true` not a distributed lock?**

Because coalescing/atomic lookup belongs to the provider's capability; the annotation does not automatically create a cross-cluster locking mechanism.

**8. Why should `join()` not be used on an event loop?**

Because it can block threads, degrade throughput, and cause stalls. Compose asynchronously instead.

**9. What should you do if a provider throws `UnsupportedOperationException` on `retrieve`?**

Check provider/version/configuration, test both overloads, choose a supporting backend, or intentionally design a synchronous path. Do not silently fall back to hidden blocking.

**10. If the same key is called before the first future completes, is the loader always executed only once?**

Not by default. Check `sync=true` and provider semantics, and run real concurrency tests.

## 16. Conclusion

In modern Spring Cache, **async service return types** and **async cache retrieval support** are two distinct requirements. `CompletableFuture<T>` on the service expresses a business result available in the future; `Cache.retrieve(...)` is the cache store's capability to look up/load values via futures.

When building applications:

1. Confirm Spring Framework 6.1+ and a provider supporting `Cache.retrieve(key)`, especially `retrieve(key, valueLoader)` when synchronized loading is needed.
2. Properly handle immediate misses, late misses, cached-null, and exceptional futures.
3. Use `ConcurrentMapCacheManager` for study/testing, and configure `CaffeineCacheManager.setAsyncCacheMode(true)` when wanting async caching on Caffeine.
4. Do not mistake `join()`, completed futures, or local caches for non-blocking I/O and distributed consistency.
5. Verify cache hits, loader counts, errors, concurrency, context, and transactions on the **actual provider**.

**Rule to remember:** *A method returning `CompletableFuture` does not automatically give the cache provider `CompletableFuture`-based retrieval. Verify the contract of your `Cache` implementation.*

## Official References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Annotation-based caching, `CompletableFuture` and reactive return types: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache API Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — ConcurrentMapCache Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — CaffeineCacheManager Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cacheable annotation Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html