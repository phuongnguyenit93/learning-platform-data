# `Cache.retrieve` and Representations of Hit, Miss, and Null in Spring Cache

## Objective

When calling `Cache.get(key)` synchronously, you typically receive a `Cache.ValueWrapper` if the entry exists and `null` on a cache miss. With the asynchronous API `Cache.retrieve`, the story is more nuanced: the result can be **no future**, **a future completing with null**, or **a future containing a wrapper with a null value**. These three forms **do not mean the same thing**.

This lesson focuses on the `org.springframework.cache.Cache` contract from Spring Framework 6.1 onward, especially its two overloads:

~~~java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

The signatures above are simplified for readability; imports and nullability annotations are omitted from the example. After this lesson, you will know when each outcome is a hit or miss, how to handle cached nulls, how to use a loader to populate data, how to avoid blocking, and how to write a Java 17 program to verify with Spring Caffeine async cache.

> **Key conclusion:** With the **no-loader** overload, `retrieve(key) == null` is an immediate miss; `retrieve(key)` returning a future **completing with null** is an asynchronously determined miss; and a future containing a `Cache.ValueWrapper` with `get() == null` is **a hit with a cached null value**.

## 1. Context: Why Is `Cache.retrieve` Needed?

A cache can determine whether an entry exists immediately if it uses a local map, yet if the backend queries over a network or an asynchronous I/O layer, the call must wait. The synchronous `get` API may force the thread to block. The `retrieve` API creates a `CompletableFuture`-based retrieval path so the caller can compose subsequent processing without calling `.join()` or `.get()` on the processing path.

Flow:

~~~text
t0: caller invokes cache.retrieve(key)
          |
          +-- Immediate miss known: returns null
          |
          +-- Async result available: returns CompletableFuture<?>
                                      |
                                 at time t1
                                      |
                     +----------------+----------------+
                     |                |                |
                   value             null          exception
                     |                |                |
                  HIT             MISS_DEFERRED     ERROR
                     |
           value may be a ValueWrapper
                     |
             wrapper.get() == null
                     |
                 HIT_CACHED_NULL
~~~

The distinction lies not only in the result value, but also in **when the provider knows whether an entry exists**. You cannot equate "having a future" with "having an entry".

### Correspondence with the Synchronous API

~~~java
Cache.ValueWrapper wrapper = cache.get("item-1");
if (wrapper == null) {
    // Miss: no entry.
} else {
    Object value = wrapper.get();
    // Hit: value may be null.
}
~~~

This is an illustrative snippet assuming a `cache` variable of a constructed Spring `Cache` object. With `get(Object)`, the presence of `ValueWrapper` itself distinguishes cached null from a miss. In `retrieve`, there is an additional future layer.

## 2. The No-Loader Overload: Complete Set of Result Forms

The first contract:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);
~~~

The goal is to **look up an existing entry**, not to reload it from a repository automatically.

| Return value from `retrieve(key)` | Result when the future completes | Meaning |
| --- | --- | --- |
| `null` | No future | **MISS_IMMEDIATE** |
| Non-null future | `null` | **MISS_DEFERRED** |
| Non-null future | Non-null object | **HIT_VALUE** |
| Non-null future | `Cache.ValueWrapper` holding a non-null object | **HIT_VALUE** |
| Non-null future | `Cache.ValueWrapper` with `get() == null` | **HIT_CACHED_NULL** |
| Non-null future | Completes exceptionally | **ERROR**, not a miss |

### 2.1. Immediate Miss: Null at the Outer Layer

If the provider can determine immediately that the key does not exist, the method can return a **null reference** instead of a future:

~~~java
CompletableFuture<?> lookup = cache.retrieve("absent");

if (lookup == null) {
    // MISS_IMMEDIATE: no future to continue with.
}
~~~

Never call `lookup.join()`, `lookup.thenApply()`, or `lookup.get()` before checking outer null, as that will throw `NullPointerException`.

### 2.2. Deferred Miss: Future Containing Null at the Inner Layer

A provider needing time to look up may return a non-null future; once the lookup finishes, the future completes with null:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture(null);
~~~

This is **MISS_DEFERRED**. In real life the future may be pending rather than completing immediately. When `lookup != null`, do not assert a hit until the future completes and the result is inspected.

Example:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);

if (lookup == null) {
    // Immediate miss.
} else {
    lookup.thenAccept(result -> {
        if (result == null) {
            // Deferred miss.
        }
    });
}
~~~

This is illustrative code that belongs inside a method, not a standalone runnable Java file.

### 2.3. Hit with a Non-Null Value

A normal cache hit may return:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture("Book-A");
~~~

The future completing with `"Book-A"` indicates the entry has that value. Some implementations may complete with `Cache.ValueWrapper("Book-A")`; general-purpose code should support unwrapping wrappers instead of casting the result directly to the domain type.

### 2.4. Hit with a Stored Null Value

If the provider permits caching null, it must retain the ability to distinguish an entry that **exists** and holds null from a key that **does not exist**. Spring allows `Cache.ValueWrapper` as that signal:

~~~java
CompletableFuture<?> lookup =
    CompletableFuture.completedFuture(
        new SimpleValueWrapper(null)
    );
~~~

`SimpleValueWrapper` belongs to package `org.springframework.cache.support`.

Explanation:

~~~text
result = null
    => Cache MISS_DEFERRED

result = ValueWrapper(null)
    => Cache HIT_CACHED_NULL
       (wrapper non-null, inner value null)
~~~

**Do not strip the wrapper too early.** If an adapter turns `ValueWrapper(null)` into `null`, downstream can no longer distinguish cached null from a miss. A cached "not found" result could then be unnecessarily reloaded from the source.

### 2.5. When the Future Fails

A future terminating with an exception has no value for hit/miss classification. This is an **error path**:

~~~java
CompletableFuture<?> failed =
    CompletableFuture.failedFuture(
        new IllegalStateException("cache backend timeout")
    );
~~~

When calling `failed.join()`, Java throws `CompletionException` with the root cause. Do not collapse an exception into `null` and call it a miss: doing so hides cache provider errors and can drive heavy load onto the database.

## 3. Correct Processing Order

A non-blocking classifier function:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.cache.Cache;

public static CompletableFuture<String> classifyAsync(
        CompletableFuture<?> lookup) {

    if (lookup == null) {
        return CompletableFuture.completedFuture("MISS_IMMEDIATE");
    }

    return lookup.thenApply(result -> {
        if (result == null) {
            return "MISS_DEFERRED";
        }

        if (result instanceof Cache.ValueWrapper wrapper) {
            Object value = wrapper.get();
            return value == null
                ? "HIT_CACHED_NULL"
                : "HIT_VALUE:" + value;
        }

        return "HIT_VALUE:" + result;
    });
}
~~~

This is an **illustrative method** that must be placed inside a class. Advantages:

1. Checks **outer** null first.
2. Continues processing when the future completes, without blocking the caller.
3. Checks **inner** null.
4. Only then checks `ValueWrapper`.
5. Unwraps the wrapper only when the result is actually a wrapper.
6. Does not swallow exceptions; the returned stage completes exceptionally if the lookup fails.

Diagram:

~~~text
retrieve(key)
     |
     +-- null -----------------------> MISS_IMMEDIATE
     |
     +-- CompletableFuture
                  |
               complete
                  |
          +-------+----------------+
          |                        |
       exception                 normal
          |                        |
         ERROR                 result == null?
                                   |
                              +----+----+
                              |         |
                             yes        no
                              |         |
                         MISS_DEFERRED  ValueWrapper?
                                        |
                                 +------+------+
                                 |             |
                                yes            no
                                 |             |
                             wrapper.get()    HIT_VALUE
                                 |
                            +----+----+
                            |         |
                           null      value
                            |         |
                     HIT_CACHED_NULL HIT_VALUE
~~~

In a console example, `.join()` can be used to print stdout in order. In controllers/event loops/Reactive pipelines, avoid `join` when the goal is non-blocking execution.

## 4. How Does the Overload with `valueLoader` Work Differently?

Signature:

~~~java
<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

Example:

~~~java
CompletableFuture<Book> result = cache.retrieve(
    "book-42",
    () -> remoteRepository.findAsync("book-42")
);
~~~

This is **illustrative code**, assuming `Book` and repository exist.

Meaning:

- When the entry already exists, the cache can return a future of the stored value without invoking the loader.
- On a miss, the provider invokes the supplier to load a `CompletableFuture<T>`, handles the result, and places the valid value into the cache.
- The caller receives `CompletableFuture<T>`, not `CompletableFuture<Cache.ValueWrapper>` as a cache-miss notification interface.
- Concurrent misses for the same key can be coordinated by the provider, though **not automatically as a distributed lock across JVMs**.
- The loader's future may be wrapped/transformed by the provider; do not assert `cacheFuture == loaderFuture` as a contract.

### 4.1. The Supplier Must Return a Future

Right:

~~~java
() -> CompletableFuture.completedFuture("Book-A")
~~~

Or:

~~~java
() -> service.loadAsync(id)
~~~

Conceptually wrong for the API:

~~~java
() -> null
~~~

A supplier returning a `null` future reference is an invalid loader for normal operation. This is **different** from a supplier returning a valid future whose value is null:

~~~java
() -> CompletableFuture.completedFuture(null)
~~~

In the **loader** overload, a future returning null can be the **loaded/looked-up business value `T`**; whether null is stored depends on `allowNullValues`/the provider. Do not blindly carry over the no-loader overload's "inner null = deferred miss" rule to the loader overload.

### 4.2. Null Caching Ability Is a Provider Policy

One provider may accept cached null via an internal marker, while another rejects it. Therefore:

- Do not assume `cache.put(key, null)` is always valid.
- Do not assume a `CompletableFuture<T>` completing with null will be cached on every backend.
- Verify null policies, TTL, and invalidation if you use negative caching.
- With Caffeine async mode, Spring recommends considering `setAllowNullValues(false)` to simplify future semantics. The example in this lesson enables true **intentionally** to demonstrate cached null.

### 4.3. Failed or Canceled Futures

If the loader returns a future that completes exceptionally, there is no successfully completed business value to store. Some cache providers evict failed futures from the store so subsequent calls can retry, though the actual implementation must be tested. Cancellation must also be considered, especially when multiple callers await a shared future.

### 4.4. Do Not Use the Loader for Side Effects Required on Every Call

On a cache hit, the loader **does not run**. Therefore, do not put operations like "write an audit log on every request" or "decrement inventory" solely inside the loader. Caching is only suitable for reads or validly key-reusable results.

## 5. Comparing APIs and Common Pitfalls

| API | Returned Data | Distinguishes Miss / Cached Null? | Auto-Loads on Miss? |
| --- | --- | --- | --- |
| `get(key)` | `ValueWrapper` or null | Yes, via wrapper | No |
| `get(key, Type.class)` | Value of type `T` or null | Not necessarily | No |
| `retrieve(key)` | Null or `CompletableFuture<?>` | Yes, if both layers are handled | No |
| `retrieve(key, loader)` | `CompletableFuture<T>` | Primarily represents value `T`; does not use hit/miss wrapper like the first overload | Yes |
| `@Cacheable` | Method return type, possibly future | Spring cache interceptor handles it | Yes, by invoking the method on miss |

A few anti-patterns:

~~~java
// Wrong: the future may exist yet complete with null.
boolean hit = cache.retrieve(key) != null;

// Wrong: can NPE if retrieve returns null immediately.
Object result = cache.retrieve(key).join();

// Wrong: a null wrapper value may be a cached null hit.
boolean miss = result == null
    || (result instanceof Cache.ValueWrapper w && w.get() == null);
~~~

These are **anti-patterns**, not recommended code. Use a classifier function like in Section 3 to avoid ambiguity.

### `get(Object)` vs `retrieve(Object)`

Before optimizing asynchronously, ask whether the backend actually supports asynchronous retrieval. If using a local map with instantaneous lookup, the benefit may be tiny. If the cache is remote/another backend, a non-blocking path can help, though real latency and thread/connection mechanics must be measured.

## 6. `CacheManager` Compatibility

### 6.1. Not Every `Cache` Supports `retrieve`

The `Cache` interface defines `retrieve`, yet an unsupported implementation may throw `UnsupportedOperationException`. This is **not a cache miss**. Do not `catch` this error and treat every key as absent without an explicit fallback design and error observability.

### 6.2. `ConcurrentMapCache`

`ConcurrentMapCacheManager` uses local map-based caches in the JVM. Spring supports the future-based retrieval path in modern versions, yet returning `CompletableFuture` does not turn a local map into an asynchronous I/O backend. A future may complete immediately.

### 6.3. `CaffeineCacheManager`

To use Caffeine's native `AsyncCache` in Spring:

~~~java
CaffeineCacheManager manager =
    new CaffeineCacheManager();

manager.setAsyncCacheMode(true);
manager.setAllowNullValues(false);
manager.setCaffeine(
    Caffeine.newBuilder().maximumSize(1000)
);
manager.setCacheNames(List.of("books"));
~~~

This is an illustrative Java Config snippet with necessary imports. Requires Spring Framework 6.1+ and Caffeine 3.0+. `CaffeineCacheManager` lives in `spring-context-support`.

`setAsyncCacheMode(true)` **does not automatically turn synchronous methods into async**, does not run business code on an executor by itself, and does not make a local cache shared across multiple instances.

### 6.4. Redis, JCache, and Other Adapters

Do not infer from "the native client has an async API" that "the Spring `Cache` adapter implements `retrieve`". Check the Javadoc of the specific `Cache` version, overload support, and integration tests. If a backend only has a blocking API, wrapping `get` in `CompletableFuture.supplyAsync` merely shifts the blocking onto another thread; it is not native non-blocking I/O.

## 7. Runnable Java 17 Program with Spring and Caffeine

The example below verifies the **representation contract** and **a real cache implementation**. It uses `Cache.retrieve` directly so the lesson stays focused on the API, without needing `@EnableCaching` when annotation interception is not used.

### 7.1. File Structure

~~~text
retrieve-demo/
├── pom.xml
└── src/main/java/demo/RetrieveDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>retrieve-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.10</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 7.3. `src/main/java/demo/RetrieveDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.support.SimpleValueWrapper;

public class RetrieveDemo {

    static String classify(CompletableFuture<?> lookup) {
        if (lookup == null) {
            return "MISS_IMMEDIATE";
        }

        // join is only used at the console demo boundary.
        Object result = lookup.join();

        if (result == null) {
            return "MISS_DEFERRED";
        }

        if (result instanceof Cache.ValueWrapper wrapper) {
            Object value = wrapper.get();
            return value == null
                ? "HIT_CACHED_NULL"
                : "HIT_VALUE:" + value;
        }

        return "HIT_VALUE:" + result;
    }

    public static void main(String[] args) {
        System.out.println("Immediate: " + classify(null));

        System.out.println("Deferred: " + classify(
            CompletableFuture.completedFuture(null)));

        System.out.println("Cached null: " + classify(
            CompletableFuture.completedFuture(
                new SimpleValueWrapper(null))));

        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAsyncCacheMode(true);

        // Intentionally set to true to test cached null; production usually
        // considers false if negative caching is not needed.
        manager.setAllowNullValues(true);
        manager.setCaffeine(
            Caffeine.newBuilder().maximumSize(100));
        manager.setCacheNames(List.of("catalog"));

        Cache cache = Objects.requireNonNull(
            manager.getCache("catalog"));

        cache.put("present", "Book-A");
        cache.put("known-null", null);

        System.out.println("Present: " + classify(
            cache.retrieve("present")));
        System.out.println("Known null: " + classify(
            cache.retrieve("known-null")));

        String absent = classify(cache.retrieve("absent"));
        System.out.println("Absent is miss: " +
            absent.startsWith("MISS_"));

        AtomicInteger loads = new AtomicInteger();
        Supplier<CompletableFuture<String>> loader = () -> {
            int n = loads.incrementAndGet();
            return CompletableFuture.completedFuture(
                "Book-B(load=" + n + ")");
        };

        String first = cache.retrieve("generated", loader).join();
        String second = cache.retrieve("generated", loader).join();
        System.out.println("Loaded first: " + first);
        System.out.println("Loaded second: " + second);
        System.out.println("Source loads: " + loads.get());
    }
}
~~~

Analysis:

- **The three synthetic results** at the top of `main` illustrate immediate miss, deferred miss, and cached-null hit accurately, without depending on a specific backend.
- `CaffeineCacheManager` enables async mode before creating the `catalog` region.
- `setAllowNullValues(true)` is an **intentional choice for this test** to store a cached null.
- Entry `present` holds `"Book-A"`, so it is a normal hit.
- Entry `known-null` actually exists, hence it is a hit with null, not a miss.
- For `absent`, the code checks only that the result starts with `MISS_`, because more than one miss representation is valid under the contract.
- The loader for key `generated` returns a future completing with `Book-B(load=1)`. The two **sequential** calls have the same key, so the second is a hit and the counter does not increment.

### 7.4. Run from the Directory Containing `pom.xml`

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RetrieveDemo
~~~

The program is expected to print:

~~~text
Immediate: MISS_IMMEDIATE
Deferred: MISS_DEFERRED
Cached null: HIT_CACHED_NULL
Present: HIT_VALUE:Book-A
Known null: HIT_CACHED_NULL
Absent is miss: true
Loaded first: Book-B(load=1)
Loaded second: Book-B(load=1)
Source loads: 1
~~~

This stdout is inferred from the code flow and Spring/Caffeine contracts; Maven compilation and execution on a real JVM **were not performed while writing this article**.

### 7.5. If You Change the `allowNullValues` Configuration

If changed to:

~~~java
manager.setAllowNullValues(false);
~~~

then do not keep `cache.put("known-null", null)` as in the example, because the policy forbids cached nulls. In a real application, using `Optional<T>`, a dedicated result DTO, or not caching "not found" are options to evaluate based on domain semantics.

## 8. Integration with `@Cacheable` and Reactive Return Types

Since Spring Framework 6.1, annotation-based caching can adapt to `CompletableFuture<T>`, Reactor `Mono<T>`, and `Flux<T>`.

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> loadAsync(String isbn) {
    return repository.findByIsbnAsync(isbn);
}
~~~

This is **illustrative code** requiring a repository and `@EnableCaching`/cache manager configuration. Spring stores the `Book` result when the future succeeds and returns a future to the caller.

With `Flux<T>`, Spring collects elements into a `List<T>` to cache once the publisher completes and replays the list on hits. This is not per-element streaming caching. With `Mono.empty()`, check adaptation and provider null/empty policies. Do not assume `Mono.empty()` is always equivalent to cached null in every situation.

### `@Async` Is Not `Cache.retrieve`

`@Async` controls method execution via a `TaskExecutor`; `Cache.retrieve` describes future-based cache lookup. Enabling Caffeine async mode does not automatically run business methods on a background thread, and enabling `@Async` does not add `retrieve` support to a backend that has not implemented it.

### `sync = true`

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    sync = true
)
public CompletableFuture<Book> findBook(String id) {
    return repository.findAsync(id);
}
~~~

The snippet above shows how to ask Spring to coordinate concurrent misses for the same key if the cache provider supports it. `sync=true` has constraints regarding `unless`, the number of caches in the operation, and atomic loading capability. A local Caffeine cache does not turn it into a distributed lock across instances.

## 9. When Should You Handle Misses Manually?

If you only look up:

~~~java
CompletableFuture<?> lookup = cache.retrieve(key);
~~~

and need to load data on a miss, remember that:

- The `lookup == null` branch handles **only immediate misses**.
- The branch where the future completes with null handles **deferred misses**.
- The `ValueWrapper(null)` branch is a **hit**; do not call the loader.
- The exception branch is a separate error path.
- If you load manually via `repository.fetchAsync`, you still need to **write the result into the cache**. Merely loading and returning does not guarantee a cached value for the next call.

Therefore, when supported by the provider, the `retrieve(key, loader)` overload is usually simpler than re-implementing every branch, locking, and cache put yourself.

## 10. Races, Concurrency, Cancellation, and Stale Data

### 10.1. Two Requests with the Same Key

Two requests may call `retrieve(key, loader)` while the first future is still pending. Some implementations have a mechanism to share the future/load once per key; some backends or configurations lack those semantics. Verify with concurrency tests, not merely from the `CompletableFuture` return type.

### 10.2. Future Completing After Eviction

~~~text
t0: Load A is pending, waiting for source data.
t1: Source is updated.
t2: cache.evict(key).
t3: Load A completes with stale data.
~~~

Verify whether the provider prevents stale results from writing back after eviction. Async caches do not automatically guarantee ordering/transactions/versioning across all backends. For data requiring high consistency, you can use versioned keys, after-commit invalidation, or fencing tokens.

### 10.3. Exceptions and Cancellation

If a future completes exceptionally, preserve the error details for the caller/metrics to handle. Do not turn it into a miss via `catch (Exception) { return null; }` without an explicit policy. When multiple callers await one future, one caller canceling can affect others depending on how the provider shares handles; test cancellation separately.

### 10.4. Cache Hit Does Not Mean Fresh Data

Even if every hit/miss/null branch is handled accurately, an entry can still be stale after a database update. You still need `@CacheEvict`, `@CachePut`, TTL, or appropriate invalidation. Async retrieval does not solve freshness by itself.

## 11. Testing the Contract Properly

| Scenario | Test Input | Correct Result |
| --- | --- | --- |
| Immediate miss | `retrieve` returns `null` | Do not call methods on future; MISS |
| Deferred miss | Future completes with `null` | MISS after completion |
| Raw hit | Future completes with `"A"` | `HIT_VALUE` |
| Wrapper hit | Future completes with `ValueWrapper("A")` | `HIT_VALUE` after unwrap |
| Cached null | Future completes with `ValueWrapper(null)` | **HIT_CACHED_NULL**, not MISS |
| Exceptional future | `failedFuture(ex)` | ERROR, preserve exception |
| Loader miss | Key absent | Loader invoked, returns value |
| Loader hit | Key already loaded | Loader not called again |
| Loader returns null | Valid future containing null | Behavior per null policy |
| Backend lacks `retrieve` support | Throws `UnsupportedOperationException` | Capability error, not a miss |
| Concurrent miss | Two requests with pending future | Verify single-flight per provider |
| Eviction race | Evict while load unfinished | Check for stale write |

To avoid flaky tests, use test-controlled `CompletableFuture` instances or `CountDownLatch` instead of arbitrary `Thread.sleep`. For non-blocking tests, use `thenApply`/`thenCompose` and assert on the completed stage. Use loader counters to prove hit/miss, not just timing.

### Signs to Check When Bugs Occur

- Unexpected NPE: are you calling a method on the future when `retrieve` returned null?
- "Got a future but no data": did the future complete with null due to a deferred miss?
- Negative caching ineffective: did you unwrap `ValueWrapper(null)` into a miss?
- Misses always reload: missing cache put, failed future, or unstable key?
- `UnsupportedOperationException`: does the cache adapter implement `retrieve`?
- Multiple requests loading the same key: did you verify concurrency/atomic loader support?
- Null put rejected: does `allowNullValues` permit it?
- Large `Flux` spikes RAM: is Spring collecting the whole publisher into a list to cache?

## 12. Implementation Checklist

- [ ] Understand both overloads: `retrieve(key)` and `retrieve(key, loader)`.
- [ ] Check outer null before using the future from the no-loader overload.
- [ ] Distinguish inner null from `ValueWrapper(null)`.
- [ ] Handle wrappers for both null and non-null cached values.
- [ ] Separate exceptions/cancellation from cache misses.
- [ ] Avoid `.join()` in event loops or request paths when non-blocking is the goal.
- [ ] Ensure the provider/version supports `Cache.retrieve`.
- [ ] With Caffeine, use native async mode when needed.
- [ ] Define policies for null, `Optional`, negative caching, and invalidation.
- [ ] Ensure the loader returns a `CompletableFuture<T>`, not a null reference.
- [ ] Ensure the loader contains no side effects needed on every request.
- [ ] Test miss/hit/null, loader, exceptions, and concurrent misses.
- [ ] Test races between pending futures and updates/evictions.
- [ ] Measure hit ratio, load count, latency, and cache errors.
- [ ] Do not confuse async cache mode with `@Async` or distributed caching.

## 13. Self-Check Questions

**1.** What does `retrieve(key)` returning null directly mean?  
**Answer:** A cache miss determined immediately; there is no future.

**2.** What does `retrieve(key)` returning a future that completes with null mean?  
**Answer:** A deferred miss.

**3.** What does a future completing with `SimpleValueWrapper(null)` mean?  
**Answer:** A cached-null **hit**, not a miss.

**4.** Why does `retrieve(key) != null` not prove a hit yet?  
**Answer:** The future may complete later with null.

**5.** Why can `retrieve(key).join()` throw NPE?  
**Answer:** Because `retrieve(key)` is allowed to return null immediately.

**6.** If the result is `ValueWrapper("Book")`, what should you do?  
**Answer:** Unwrap the value and classify it as `HIT_VALUE`.

**7.** Is an exceptional future a miss?  
**Answer:** No, it is an ERROR.

**8.** What type does the `retrieve(key, loader)` overload return?  
**Answer:** `CompletableFuture<T>` of the cached or loaded value.

**9.** May the supplier of the loader overload return a null future reference?  
**Answer:** It should not; it must return a valid `CompletableFuture<T>`.

**10.** Is a loader-returned future completing with null guaranteed to be a deferred miss?  
**Answer:** No; null may be the business value `T` under the null policy.

**11.** Is `setAsyncCacheMode(true)` on the general `CacheManager` interface?  
**Answer:** No; it is an API on `CaffeineCacheManager`.

**12.** Does calling the `Cache.retrieve` API directly require `@EnableCaching`?  
**Answer:** No; `@EnableCaching` is for annotation-driven interception.

**13.** Does async retrieval turn Caffeine into a distributed cache?  
**Answer:** No; Caffeine is a local JVM cache by default.

**14.** Why avoid `Thread.sleep` when testing future completion?  
**Answer:** Tests become scheduler-dependent and flaky; use controllable futures or latches for timing.

**15.** Are a cached null and the database lacking a record identical forever?  
**Answer:** No; a cached null is a "not found" snapshot at cache time. The source can change, requiring TTL/invalidation.

## References

- Spring Framework 6.2.10 — Cache Javadoc, `retrieve(Object)`, `retrieve(Object, Supplier)`: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2.10 — CaffeineCacheManager Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2.10 — SimpleValueWrapper Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/support/SimpleValueWrapper.html
- Caffeine — Population and asynchronous loading: https://github.com/ben-manes/caffeine/wiki/Population