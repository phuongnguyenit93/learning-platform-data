# CompletableFuture and Reactive Type Support Since Spring Framework 6.1

> **Spring Framework – Cache Abstraction · Group: Asynchronous.** Starting with **Spring Framework 6.1**, the declarative caching infrastructure understands methods returning `CompletableFuture`, `Mono`, and `Flux`: caching is handled in terms of the **completed/emitted value**, rather than simply treating the future wrapper or `Publisher` object as the value to store. This lesson explains how it works, required backend capabilities, a Java 17+ example, and pitfalls when applying it to asynchronous applications.

## 1. Why Is Asynchronous Caching Different from Synchronous Caching?

With a synchronous method:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public BookView findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Spring Cache can check the cache **before invoking** the method body; on a miss, the method runs and returns `BookView`, and the value is then placed into the cache according to configuration.

With a method returning `CompletableFuture<BookView>`, the moment the Java method **returns** may simply be the moment an incomplete task is created. The `BookView` value may appear later on another thread. With Reactor `Mono<BookView>` and `Flux<BookView>`, the method may return a pipeline description; data production typically happens **upon subscription**.

If the raw `CompletableFuture` or `Mono` object is stored as an arbitrary value, the cache could accidentally share task state, depend on a subscriber, or hold a publisher with unsuitable behavior. The support mechanism introduced in 6.1 aims to provide handling based on the **published asynchronous result**.

### Visual Comparison Table

| Method Return Type | Unit of Value Targeted by Caching Infrastructure | On Cache Hit |
| --- | --- | --- |
| `BookView` | A single `BookView` | Returns `BookView` |
| `CompletableFuture<BookView>` | `BookView` after the future completes successfully | Returns a suitable `CompletableFuture` containing the cached result |
| `Mono<BookView>` | A single `BookView` emitted by `Mono` | Returns a `Mono` emitting the cached result |
| `Flux<BookView>` | **`List<BookView>`** collected from the entire `Flux` upon successful completion | Returns a `Flux` emitting the stored elements in sequence |

**Note on `Flux`:** the cache must **wait for the stream to complete** before it has a complete list to store. Do not apply this strategy unconditionally to infinite `Flux` streams, long-lived event streams, overly large datasets, or streams requiring element-level backpressure.

## 2. What Changed Starting in Spring 6.1?

Before official support for asynchronous/reactive types, placing `@Cacheable` on a method returning a Future/Publisher easily led to treating the wrapper as an ordinary object, failing to accurately reflect when the real result becomes available. Starting with **Spring Framework 6.1**, `@Cacheable` knows how to adapt to:

- **`CompletableFuture<T>`:** processes the result after the future completes; creates a suitable future on a cache hit.
- **Reactor `Mono<T>`:** caches the emitted element upon successful completion; on a hit, can convert the stored value into a `Mono`.
- **Reactor `Flux<T>`:** collects elements of a finite stream into a `List` to store upon completion; on a hit, creates a stream replaying the elements from the list.
- **Asynchronous lookup on the cache provider:** when a provider supports `Cache.retrieve`, Spring can leverage it instead of always forcing blocking reads.

This is support at the **Spring caching interceptor** layer. It **does not turn every cache backend into an asynchronous system**, nor does it cause `@Cacheable` to automatically create threads, executors, non-blocking network I/O, or schedulers. The business method and provider must still be properly designed.

Spring also has adaptive behavior for asynchronous/reactive return types for other caching operations such as `@CachePut` and `@CacheEvict`. However, **completion timing and invalidation conditions** must be evaluated based on the annotation type, `beforeInvocation`, errors, transactions, and provider; do not assume that immediately receiving a `Mono` means the side effect has already completed.

## 3. CompletableFuture: Caching the Result, Not Just the Promise

Suppose we have a service:

~~~java
@Cacheable(cacheNames = "bookDetails", key = "#p0")
public CompletableFuture<String> fetchBook(String isbn) {
    return CompletableFuture.supplyAsync(
            () -> remoteClient.fetchTitle(isbn)
    );
}
~~~

This is an **illustrative method**, requiring a Spring bean and a configured `remoteClient`; the runnable version in Section 7 uses `completedFuture` to avoid network or executor dependencies.

With `@Cacheable`:

1. Call through the **Spring-managed proxy** with a key that is not yet cached.
2. On a cache miss, Spring invokes the method and receives a `CompletableFuture` representing the task.
3. When the future **completes successfully**, Spring can store the **completed `String` value** under the ISBN key.
4. Subsequent calls with the same key that hit the cache will receive a compatible `CompletableFuture<String>`, from which the result can be obtained with `join()` or chained further.
5. If the future completes exceptionally with an exception, do not treat the exception as a **normal successful value** to cache; error policies and provider handling still need to be checked.

### Distinguishing Invocation Time and Completion Time

~~~text
t0   client calls fetchBook("BK-1")
t1   cache miss, method returns pending CompletableFuture
t2   I/O task completes with new BookView value
t3   Spring completes the corresponding cache operation
t4   another client calls same key: can receive cached result
~~~

Do not assert that every call between t1 and t3 is automatically coalesced. **Cache stampede** is a separate concern: multiple requests with the same key missing before the first future completes can all execute the source if the cache/provider does not support appropriate synchronization/async loading.

### Avoid Building a Manual "Cache of Futures" Unless Needed

A hand-written `Cache<String, CompletableFuture<BookView>>` can be useful in certain architectures, but it pushes retry, exceptional completion, cancellation, state sharing, lifecycle, and eviction of the future into the cache contract. With Spring 6.1+, prefer letting the caching infrastructure manage the value **T** if the requirement is caching normal business results.

**Do not equate `CompletableFuture` with effective asynchrony:** `CompletableFuture.completedFuture(value)` is an already-ready result and does not perform asynchronous I/O. `supplyAsync` uses an executor, but does not by itself turn a blocking call into a non-blocking network operation.

## 4. Reactor Mono: Single Result or Empty Completion

`Mono<T>` is a `Publisher` emitting **at most one element**. A `Mono` returned from a method may be *cold*: it only starts working when a subscriber subscribes.

~~~java
@Cacheable(cacheNames = "bookDetails", key = "#p0")
public Mono<String> findBook(String isbn) {
    return reactiveRepository.findTitleByIsbn(isbn);
}
~~~

This is an **illustrative method**, requiring a real `reactiveRepository`. With Spring 6.1+ support:

- A cache miss causes the business pipeline to be executed when needed; emitted data can be placed into the cache upon completion via the adaptation mechanism.
- A cache hit can return a `Mono` emitting the **cached value** without re-running the source query.
- Because `Publisher` has subscription semantics, do not infer that the cache has been populated merely because a method **returned a `Mono` object** that has never been subscribed to.
- If a `Mono` completes empty, check the backend's **null/miss policy** and domain contract; do not assume every cache provider stores empty completions the same way.
- If a `Mono` emits an error, retry/error-caching design must be consistent with business requirements; do not treat a network error signal as successful data.

### Things to Distinguish

- **Memoization in Reactor**: `Mono.cache()` retains signals scoped to **a single Mono instance** as a Reactor operator.
- **Spring method cache**: `@Cacheable` manages keys/cache regions for method invocations **going through the Spring proxy**.
- **Provider cache**: Caffeine/Redis/ConcurrentMap determines TTL, capacity, serialization, and cross-instance sharing.

`Mono.cache()` and `@Cacheable` are not different names for the same mechanism. They have different scopes, lifecycles, and ownership. Merely adding `Mono.cache()` to a pipeline does not automatically provide SKU-based invalidation; adding `@Cacheable` does not by itself make custom operators or downstream queries non-blocking.

## 5. Reactor Flux: Be Careful with Collecting the Entire Stream

`Flux<T>` emits **0 to many elements**. Spring 6.1+ handles `Flux` results for declarative caching by **collecting elements into a `List<T>`** when the stream completes, and can then replay that list via a `Flux` on a cache hit.

~~~java
@Cacheable(cacheNames = "recommendations", key = "#p0")
public Flux<String> recommendations(String category) {
    return repository.findRecommendedIds(category);
}
~~~

This is an illustrative snippet, requiring a reactive repository and a Spring-managed bean.

### What Does This Mean?

- The first stream must **complete** to produce the full result to cache.
- The list in the cache is **a snapshot** of the entire stream at completion time.
- Subsequent hits replay the cached values without necessarily re-executing the original I/O stream.
- Memory can grow rapidly if a single key produces hundreds of thousands of elements.
- Infinite streams like `Flux.interval`/SSE/live event streams **do not have normal completion** and are unsuitable for full-stream collection.
- Full-stream collection does not provide **element-by-element streaming to the cache**; do not use it if the business requirement needs unbounded processing with per-event latency.

### Decision Examples

| Use case | Should you `@Cacheable Flux`? | Reason |
| --- | --- | --- |
| List of 20 product codes for a category | Possibly | Finite stream, controllable size |
| List of 10,000 paginated orders | Consider carefully | Large result, cache key must include page/filter |
| Infinite market-tick stream | Not suitable | Never completes to collect a full list |
| SSE websocket event stream | Not suitable | Live data with subscriber-specific semantics |
| Query returning at most 1 row | Usually prefer `Mono` | No need for `Flux` and multi-element collection |
| Stream depending on permissions/user/tenant | Only when key and access control are correct | Avoid sharing data across users |

**Important note on memory:** the cache provider may retain the entire list and all its elements, increasing pressure on the heap or external store. When using a large `Flux`, limit the number of elements, partition keys by page, store compact DTOs, or cache a paginated result object instead of collecting an unbounded stream.

## 6. Requirements for Backend Asynchronous Caching Compatibility

### 6.1. Spring's Cache.retrieve API

Spring Cache has an asynchronous API such as:

~~~java
CompletableFuture<?> future = cache.retrieve("BK-1");
~~~

This is an **illustrative snippet** inside a method that already has a `cache` variable of type `org.springframework.cache.Cache`. The `retrieve` API allows a cache provider to return a future result when a lookup cannot complete immediately. Do not equate this API with automatic loader execution; lookup and compute-on-miss are two separate concerns.

Not every `Cache` implementation provides a useful asynchronous lookup. An implementation that only supports synchronous APIs may not satisfy the `sync=true` and reactive non-blocking strategies that the application expects.

### 6.2. ConcurrentMapCacheManager

Since Spring 6.1, `ConcurrentMapCacheManager` has the configuration:

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("futureBooks", "monoBooks", "fluxBooks");
manager.setAsyncCacheMode(true);
~~~

This is a standalone configuration snippet inside a method, requiring import of `org.springframework.cache.concurrent.ConcurrentMapCacheManager`. This mode enables the manager to support asynchronous lookup adaptation for the Java 17+ example below.

It remains an **in-JVM local cache**; it does not turn into Redis, has no persistence, and does not automatically guarantee TTL. Because storage is local, each application instance has its own cache.

### 6.3. CaffeineCacheManager

Spring's `CaffeineCacheManager` also supports:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager("books");
manager.setAsyncCacheMode(true);
~~~

This is an integration configuration snippet, requiring Spring `spring-context-support` and the appropriate Caffeine dependency. Asynchronous mode uses native asynchronous caches when possible. Verify how loaders, size limits, `expireAfterWrite`, serialization, and error handling combine in your actual provider.

**Distinguish two concepts:**

- `setAsyncCacheMode(true)`: configures the backend to support asynchronous retrieval/operations.
- `refreshAfterWrite`: a separate Caffeine policy to **refresh an existing entry**, requiring a suitable loader/async loader.

Enabling async cache mode **does not automatically create refresh**, TTL, prefetch, or a periodic background task.

### 6.4. @Cacheable(sync = true)

~~~java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public CompletableFuture<String> find(String isbn) {
    return remoteClient.fetch(isbn);
}
~~~

This is **illustrative method code**, requiring a real client, a supporting cache provider, and calls going through the proxy. `sync = true` lets Spring ask the provider to coordinate value computation when multiple callers miss on the same key, in order to reduce duplicate loads. For Future-returning methods, appropriate support depends on the provider's asynchronous API.

**Do not make absolute promises:** `sync=true` is not a distributed lock across all JVMs, does not eliminate DB/cache races, does not replace `@Transactional`, and has certain restrictions when combined with cache names/`unless`. Test concurrency against the real backend.

## 7. Complete Java 17+ Example: Future, Mono, and Flux in One Application

The example uses **Spring Framework 6.2.14**, **Reactor Core 3.7.12**, Java 17, and `ConcurrentMapCacheManager` in async cache mode. It is a plain Java application creating an `AnnotationConfigApplicationContext`, **without needing Spring Boot, HTTP, or a database**.

Three independent cache regions:

1. `futureBooks`: method returns `CompletableFuture<String>`.
2. `monoBooks`: method returns `Mono<String>`.
3. `fluxBooks`: method returns `Flux<String>`, with **two elements**.

Each method increments a counter at the point where it **actually computes the source value**. When calling the same key a second time, on a cache hit the counter will not increment.

**File `build.gradle`:**

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
    implementation 'io.projectreactor:reactor-core:3.7.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AsyncCacheDemo'
}
~~~

**File `src/main/java/demo/AsyncCacheDemo.java`:**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class AsyncCacheDemo {

    public static class BookService {
        private final AtomicInteger futureLoads = new AtomicInteger();
        private final AtomicInteger monoLoads = new AtomicInteger();
        private final AtomicInteger fluxLoads = new AtomicInteger();

        @Cacheable(cacheNames = "futureBooks", key = "#p0")
        public CompletableFuture<String> findFuture(String isbn) {
            int n = futureLoads.incrementAndGet();
            return CompletableFuture.completedFuture(
                    "future-" + isbn + "-load-" + n
            );
        }

        @Cacheable(cacheNames = "monoBooks", key = "#p0")
        public Mono<String> findMono(String isbn) {
            return Mono.fromSupplier(() -> {
                int n = monoLoads.incrementAndGet();
                return "mono-" + isbn + "-load-" + n;
            });
        }

        @Cacheable(cacheNames = "fluxBooks", key = "#p0")
        public Flux<String> findFlux(String isbn) {
            return Flux.defer(() -> {
                int n = fluxLoads.incrementAndGet();
                return Flux.just(
                        "flux-" + isbn + "-A-" + n,
                        "flux-" + isbn + "-B-" + n
                );
            });
        }

        public int futureLoads() {
            return futureLoads.get();
        }

        public int monoLoads() {
            return monoLoads.get();
        }

        public int fluxLoads() {
            return fluxLoads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                    new ConcurrentMapCacheManager(
                            "futureBooks", "monoBooks", "fluxBooks"
                    );
            manager.setAsyncCacheMode(true);
            return manager;
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);

            String futureFirst = service.findFuture("BK-1").join();
            String futureSecond = service.findFuture("BK-1").join();

            String monoFirst = service.findMono("BK-2").block();
            String monoSecond = service.findMono("BK-2").block();

            var fluxFirst = service.findFlux("BK-3").collectList().block();
            var fluxSecond = service.findFlux("BK-3").collectList().block();

            System.out.println("future first: " + futureFirst);
            System.out.println("future second: " + futureSecond);
            System.out.println("future loads: " + service.futureLoads());

            System.out.println("mono first: " + monoFirst);
            System.out.println("mono second: " + monoSecond);
            System.out.println("mono loads: " + service.monoLoads());

            System.out.println("flux first: " + fluxFirst);
            System.out.println("flux second: " + fluxSecond);
            System.out.println("flux loads: " + service.fluxLoads());
        }
    }
}
~~~

Run in the directory containing `build.gradle` with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout of the program** (excluding build tool logs):

~~~text
future first: future-BK-1-load-1
future second: future-BK-1-load-1
future loads: 1
mono first: mono-BK-2-load-1
mono second: mono-BK-2-load-1
mono loads: 1
flux first: [flux-BK-3-A-1, flux-BK-3-B-1]
flux second: [flux-BK-3-A-1, flux-BK-3-B-1]
flux loads: 1
~~~

### Why This Output?

**Future:** On the first call `findFuture("BK-1")` misses, the method computes the value and returns `completedFuture`. Spring processes the value `"future-BK-1-load-1"` and stores the result. On the second call there is a cache hit, and the counter remains 1. `join()` is only used for the console example to await the result; in a real application the caller can use `thenApply` or chain asynchronously.

**Mono:** `Mono.fromSupplier` represents a source that computes upon **subscription**. The first `block()` in the example actively subscribes, and the supplier produces `"mono-BK-2-load-1"`. Upon completion, the result is cached. The next `block()` on an invocation with the same key can receive the stored result, so `monoLoads` does not increment.

**Flux:** `Flux.defer` produces two elements with the same load count. The first `collectList().block()` completes the stream, and Spring collects the two-element list and caches it. Next time Spring can replay the list, so `fluxLoads = 1`.

**Boundaries of the example:** `block()` and `join()` are only for observing stdout **in the main method**. **Do not call `block()` on WebFlux request-handling threads**; return `Mono`/`Flux` so the framework manages subscriptions and the event loop. The example uses `completedFuture` and therefore does not demonstrate truly non-blocking I/O.

**Output confidence:** stdout is inferred from the logic and Spring 6.2.14 in the configuration stated above; this does not claim to be a log executed with Gradle in the current environment. If your environment manages dependencies or proxies differently, run an appropriate integration test.

## 8. Timeline: When Is the Cache Populated?

### CompletableFuture

~~~text
Caller -> Spring proxy -> cache miss
                         |
                         v
                    invoke method
                         |
                    receive Future
                         |
              Future completes successfully
                         |
                  store T result in cache
                         |
          subsequent calls can hit by key
~~~

### Mono/Flux

~~~text
Caller -> Spring proxy -> return adapted Publisher
                                   |
                            subscriber subscribes
                                   |
                          execute source on miss
                                   |
                       Mono emits T / Flux emits multiple T
                                   |
                           Publisher completes
                                   |
                      store T / List<T> in cache
                                   |
                    subsequent calls replay data
~~~

These are conceptual diagrams; exact interception timing, how lookup is deferred, and actual schedulers depend on Spring/provider/pipeline. Do not rely on **the method having returned** to assert that the cache has been written if the async process is still pending or the Publisher has not completed.

### What Happens with Multiple Subscribers?

A `Mono`/`Flux` object can be subscribed to multiple times depending on how the caller uses it. With code that has side effects on subscribe, avoid relying on a single shared Publisher instance across requests to control caching. Check **actual source invocation counts** and **subscription counts** in real tests. `@Cacheable` operates at the Spring method boundary; not every internal pipeline segment is cached separately.

## 9. Important Interactions with @CachePut and @CacheEvict

In real applications, read-only methods are not enough: invalidation is required when the source changes.

Structural example:

~~~java
@CacheEvict(cacheNames = "bookDetails", key = "#p0")
public Mono<Void> renameBook(String isbn, String title) {
    return reactiveRepository.rename(isbn, title);
}
~~~

This is an **illustrative integration method**; `reactiveRepository` and actual beans are not defined. With asynchronous/reactive return types, caching advice must interact with the **asynchronous result**, not merely the moment the method creates an empty `Mono` waiting to be subscribed to. In Spring 6.1+, the caching infrastructure supports completion adaptation for the corresponding operations.

However, do not infer that:

- Eviction is synonymous with a database commit.
- A method returning `Mono` means the update has already finished.
- All errors trigger the same eviction policy.
- `beforeInvocation = true` and the default `false` have the same timing.
- A reactive transaction automatically turns the cache provider into a transactional cache.

If updates and evictions must happen **after commit**, clearly design transaction boundaries, context, and invalidation mechanisms. For systems requiring strong consistency, avoid having a reader load stale DB data into the cache while a writer has not yet committed.

**Regarding `@CachePut`:** when a cache operation depends on the return value from a `CompletableFuture` or `Mono`, the framework must wait for the appropriate result rather than putting the raw Future/Publisher object into the cache region. Test specifically when the method returns empty, error, or a multi-element `Flux`. Do not replace `@CachePut` with `@Cacheable` because the two annotations serve different purposes: `@CachePut` generally always executes the method, whereas `@Cacheable` can skip the method on a hit.

## 10. Errors, Empty Results, Cancellation, and Personalized Data

### 10.1. Exceptional Completion and onError

A `CompletableFuture` can `completeExceptionally`; a `Mono`/`Flux` can emit `onError`. These cases must be treated as **task errors**, not as a successfully loaded domain value. Do not log "cache successfully populated" merely because the method returned a wrapper.

If there are retries, timeouts, circuit breakers, or fallbacks, the ordering of operators/interceptors determines the **final value that gets cached**. For example, a pipeline that catches an exception and converts it to `"UNAVAILABLE"` can complete successfully; if that is cached by key, the application might hold the fallback for too long. Use a separate TTL or a policy not to cache fallback data if needed.

### 10.2. Empty Mono or Flux

`Mono.empty()` does not emit a normal `T` value; `Flux.empty()` completes with an empty list of elements. How a cache entry represents an empty result depends on the Spring adapter, null policy, and provider. Write tests for empty results, cached nulls, and misses; do not assume the two concepts are identical.

### 10.3. Cancellation

If a subscriber cancels a `Mono`/`Flux` before completion, do not rely on the cache containing a complete snapshot. The task is canceled, upstream may be canceled, or the pipeline may continue running depending on the design. To verify behavior, write tests with a controlled Publisher.

### 10.4. Context and Keys

In WebFlux, data such as tenant, user, locale, and correlation ID may live in the **Reactor Context** rather than a method parameter. Spring's `key = "#p0"` does not automatically include this Context.

If content depends on tenant/user while the key only has `isbn`, two callers can accidentally share data. Include identifying/authorization components that affect output in the key, or design separate cache regions. Do not directly cache sensitive request-specific information under a shared key.

### 10.5. Threading

- `CompletableFuture` is not required to create a new thread; it depends on the pipeline/executor.
- `Mono`/`Flux` does not automatically run on a different thread; changing threads requires using appropriate operators/schedulers.
- A cache provider may support async lookup while the adapter still has blocking paths in some configurations.
- Do not use a blocking repository directly on the event loop and expect `@Cacheable` to hide all problems.
- Measure end-to-end latency, cache hit ratio, I/O time, and thread usage in the operating environment.

## 11. Debugging When Async/Reactive Caching Behaves Unexpectedly

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `Mono` calls the source again on every request | Older Spring version, method not called via proxy, changing key, not subscribed/completed | Check Spring 6.1+, bean proxy, hit/miss, and pipeline |
| `Flux` has no cache entry | Flux has not completed, was canceled, or errored | Check `onComplete`, element count, stream size |
| Backend reports async retrieval unsupported | Cache provider does not support `retrieve`/async mode for the path used | Check implementation, `setAsyncCacheMode`, and tests |
| Multiple requests with the same key all run the source | Misses occur before completion, no coordination | Consider `sync=true`, provider support, and load deduplication |
| Cache hit still leaks another tenant's data | Key is missing partitioning component | Design proper composite key/context |
| Cache holds fallback when source fails | `onErrorResume` turns error into a successful value | Separate cache policy for fallback or conditional storage |
| `Flux` consumes too much heap | Caching collects the entire list | Limit, paginate, or do not cache infinite Flux |
| Caffeine has async enabled but does not auto-reload data | Async cache mode differs from `refreshAfterWrite` | Distinguish loader, TTL, refresh, and lookup |
| `@CacheEvict` does not run | Method called via `this` inside the same bean; or publisher has not completed | Check proxy/self-invocation, subscription, and error path |
| Using `block()` degrades throughput | Blocking on the event loop | Use reactive composition and instrumentation |
| Replaced `@Cacheable` with `Mono.cache()` but eviction has no effect | The two mechanisms have different scopes/lifecycles | Choose the right cache scope or integrate explicitly |
| Stale results after update | Eviction with wrong key or race with transaction | Test update/commit/cache read with concurrency |

### 7-Step Checklist

1. Confirm runtime is **Spring Framework 6.1 or later**; check Reactor dependency if using `Mono`/`Flux`.
2. Verify the bean is Spring-managed, `@EnableCaching`, cache name, and calls go through the proxy.
3. Check the exact value type actually stored by the provider: `T` or `List<T>`, not assuming a publisher wrapper.
4. Verify the backend has appropriate async capability; use `setAsyncCacheMode(true)` when required by the example/provider.
5. Measure completion/subscription and error or empty paths via logging/tests, not relying solely on a "method returned" log line.
6. Test read/update/evict with the **same key**, transaction commit, and concurrent requests.
7. For reactive pipelines, measure memory when `Flux` is large, and ensure request handling does not block.

## 12. Self-Check Exercises

**Question 1.** Since Spring 6.1, a `@Cacheable` method returns `CompletableFuture<BookView>`. At the abstraction level, is the cached content the Future or the BookView?

**Answer:** The **successfully completed `BookView` result** is the cached business data; on a hit, the framework adapts so the caller still receives `CompletableFuture<BookView>`.

**Question 2.** Having `@Cacheable` on an infinite `Flux<String>`, expecting to continuously cache each item individually. Is that right?

**Answer:** No. Spring 6.1+ supports caching `Flux` by **collecting all elements into a list upon completion**, which is unsuitable for infinite streams.

**Question 3.** Does `@Cacheable` on a `Mono` mean any invocation that just returns a `Mono` immediately creates a cache entry?

**Answer:** No. A cold pipeline not yet subscribed to may not have emitted a result; you must consider completion and how the provider/infrastructure adapts.

**Question 4.** Why does `@Cacheable(sync = true)` not mean a distributed cache eliminates all duplicate loads?

**Answer:** It asks the provider to synchronize computation for the same key within the limits of the backend and cache scope; it does not create a distributed lock or transaction across all nodes.

**Question 5.** Does `setAsyncCacheMode(true)` on `CaffeineCacheManager` mean the cache automatically refreshes every two minutes?

**Answer:** No. Async cache mode is an asynchronous access/storage mode; `refreshAfterWrite` is a different policy requiring an appropriate loader and trigger mechanism.

**Question 6.** After an initial `Flux` emits 3 elements and completes, what does a cache hit read return?

**Answer:** A `Flux` that can replay the **three collected elements** from the cached list, without having to re-run the source query on a valid hit.

**Question 7.** A `Mono` returns tenant-specific data, but the cache key is only SKU. Is that safe?

**Answer:** No, if the result varies by tenant. You must include the tenant in the key or partition the cache to avoid data leaks.

## 13. Key Takeaways and Official Documentation

- **Since Spring 6.1**, declarative caching adapts to `CompletableFuture` and Reactor `Mono`/`Flux`.
- `CompletableFuture<T>` and `Mono<T>` target caching **T** when the result completes; `Flux<T>` targets caching **List<T>** when the entire stream completes.
- A **cache hit** restores a return type suitable for the method (`Future`, `Mono`, or `Flux`), without forcing callers to change types.
- A cold `Mono` must have a subscription to emit results; an infinite `Flux` is unsuitable for the full-stream collection strategy.
- The **backend** must support the corresponding async behavior. `ConcurrentMapCacheManager` and `CaffeineCacheManager` have async cache mode; not all providers support it equally.
- `sync=true` is a mechanism to limit duplicate loads, not TTL, refresh, transaction, or distributed lock.
- Cached data still requires **accurate keys, timely eviction, TTL, tenant isolation, and testing for completion/error/cancellation**.

**Official references:**

- [Spring Framework 6.2 – Declarative Annotation-based Caching, Reactive and CompletableFuture Return Types](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework 6.2.14 – Cache interface](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework 6.2.14 – ConcurrentMapCacheManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework 6.2.14 – CaffeineCacheManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html)
- [Project Reactor – Mono reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html)
- [Project Reactor – Flux reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html)
