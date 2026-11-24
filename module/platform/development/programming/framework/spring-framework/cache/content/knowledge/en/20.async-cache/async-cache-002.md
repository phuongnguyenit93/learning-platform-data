# Caching Completed Values of `CompletableFuture` in Spring Cache

## 1. Goal and Context

In a Spring application, many services do not return a result immediately, instead returning a `CompletableFuture<T>` to represent work that will complete later. If caching is applied improperly, you might accidentally cache an **incomplete future object**, return stale data, repeatedly execute expensive tasks, or fail to handle a future that completes with an exception.

Starting with **Spring Framework 6.1**, the cache abstraction supports methods returning `CompletableFuture` in an asynchronous-result-aware manner: when the future completes successfully, **the `T` value it produces** is the meaningful result for the cache. On a cache hit, Spring can adapt the cached value back to the `CompletableFuture<T>` shape declared by the method. Exact behavior and non-blocking capabilities depend on the cache provider.

This lesson helps you:

1. Distinguish `CompletableFuture<T>` (representing the work) from `T` (the value received when the work completes).
2. Understand cache misses, asynchronous loading, successful completion, error completion, and cache hits.
3. Properly configure `@Cacheable` for methods returning `CompletableFuture<T>` with Spring 6.1+.
4. Know why the provider must support asynchronous retrieval; configure **Caffeine async cache mode**.
5. Understand `sync=true` when multiple requests miss the same key concurrently and the limits of this mechanism.
6. Handle invalidation, TTL, transactions, exceptions, and null results.
7. Run a Java 17 + Spring Boot 3.3.5 example and test cached data after future completion.

**Core point:** `@Cacheable` on a future-returning method is not a promise that the cache stores an incomplete `CompletableFuture` as business data. With appropriate Spring 6.1+ integration, the successful result of the future is used as the cache value; the backend may store an internal future to coordinate loading, but the contract callers need to understand remains the value `T`.

## 2. Refresher: What Is `CompletableFuture<T>`?

A `CompletableFuture<T>` is an object representing a computation that can complete in the future. It has three conceptual states:

~~~text
               CompletableFuture<T>
                        |
                 NOT_COMPLETED
                    /      \
                   v        v
           COMPLETED(T)   COMPLETED_EXCEPTIONALLY
                   |        |
                result    Throwable
~~~

Plain Java example:

~~~java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> "Hello");

String value = task.join();
System.out.println(value);
~~~

Output:

~~~text
Hello
~~~

`task` represents the work; `"Hello"` is the completed result. `join()` waits for the result and throws `CompletionException` if the future fails. In an application serving asynchronous requests, you should not arbitrarily call `join()` on request-handling threads because it blocks the thread; the console example in this lesson uses `join()` to make observing results straightforward.

### Why Must We Distinguish the Two Objects?

Suppose the following method loads a product:

~~~java
// Illustrative inside a Spring-managed service.
public CompletableFuture<Product> load(String productId) {
    return CompletableFuture.supplyAsync(
            () -> repository.findById(productId));
}
~~~

There are two things:

- The `CompletableFuture<Product>` object returned almost immediately.
- The `Product` object created after the query completes.

If a cache mistakenly stores the incomplete future as a normal business value, the cache can become coupled to the live state of the task, exception/cancellation state, or an `Executor` rather than a reusable `Product` snapshot. Spring 6.1+ introduces a cache-aware mechanism to work with this kind of result.

## 3. How `@Cacheable` Works with Completed Futures

~~~java
// Conceptual example; Product and repository are application-defined.
@Cacheable(cacheNames = "products", key = "#p0")
public CompletableFuture<Product> find(String id) {
    return CompletableFuture.supplyAsync(
            () -> repository.findById(id));
}
~~~

In Spring 6.1+, when the provider supports the asynchronous access path, the logical flow can be understood as follows:

~~~text
Caller: find("P1")
        |
        v
Spring Cache interceptor
        |
        +--> cache HIT
        |       |
        |       +--> create/return CompletableFuture holding cached value
        |
        +--> cache MISS
                |
                v
         run method find("P1")
                |
                v
         CompletableFuture<Product> running
                |
          +-----+------+
          |            |
       success       failure
          |            |
          v            v
     new Product    Exception
          |            |
          v            +--> not a successful Product value
     complete and         to cache as a normal hit
     update cache
          |
          v
     Caller receives Product via future
~~~

For a successfully completed future, the cache entry represents the loaded result. For a future that completes with an error, do not assume a valid `Product` has been cached; exception cleanup/retry behavior depends on the provider and integration path and must be tested on the actual backend.

### When Does the Cache Have Data?

Do not assume that **as soon as the method returns** a future, the cache already contains `Product`. The future may still be pending and the loader may not have produced a value yet. In particular, if the method returns a future from a network or DB client, the time between creating the future and completion can be significant.

For a provider using `AsyncCache`, it may store an internal pending future to share the in-flight task. Therefore, the accurate statement is: **the successfully completed value is the meaningful cache result**, while the provider's internal representation may be a future.

### Comparing Approaches

| Approach | Meaning |
| --- | --- |
| Spring 6.1+ cache-aware | Supports `CompletableFuture<T>` methods and adapts asynchronous results per provider |
| Manual `Map<String, CompletableFuture<T>>` | Stores futures directly; must manually handle exceptions, cancellation, removing failed futures, and lifecycle |
| Manual `Map<String, T>` after `thenAccept` | Manually writes values on completion; must manually handle races, concurrent misses, invalidation, and errors |
| `@Cacheable` on synchronous method returning `T` | Traditional contract, no future |

Do not roll your own `Map<String, CompletableFuture<T>>` just to avoid reading Spring Cache's feature documentation carefully; a manual future cache very easily retains failed futures permanently or returns stale results after updates.

## 4. Technical Requirements: Spring Framework and Cache Provider

The ability to handle future-returning cache methods was introduced in **Spring Framework 6.1**. For Spring Boot, a compatible Spring Framework version is required, such as Spring Boot 3.2 or later. The example in this lesson uses **Spring Boot 3.3.5**, running on **Java 17**.

Not only the Spring version matters: the cache provider must support retrieval operations compatible with asynchronous return types. The `org.springframework.cache.Cache` contract includes methods such as:

~~~java
// Simplified API signatures for explanation, not a custom class.
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
        Object key,
        Supplier<CompletableFuture<T>> valueLoader);
~~~

These methods allow the cache backend to fetch values or coordinate loading as a future. A provider might not fully support non-blocking retrieval. Do not assume every version of Redis, Ehcache, JCache, or a custom `Cache` implementation has the same behavior merely because it supports synchronous `Cache.get()`.

### Caffeine Async Cache Mode

`CaffeineCacheManager` supports `setAsyncCacheMode(true)` starting in Spring Framework 6.1 to create cache regions capable of asynchronous access. This is a suitable choice for `@Cacheable` returning `CompletableFuture<T>`:

~~~java
@Bean
CaffeineCacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("products");

    manager.setAsyncCacheMode(true);
    return manager;
}
~~~

`CaffeineCacheManager` can also configure `maximumSize`, `expireAfterWrite`, `recordStats`, and other policies to prevent unbounded cache growth. `setAsyncCacheMode(true)` **does not automatically set TTL or capacity**.

When async cache mode is not enabled, do not assume `CompletableFuture` is always stored/loaded non-blockingly with the expected semantics. Check the processing path on the actual provider, version, and real tests.

### `@EnableCaching` Is Still Required

~~~java
@SpringBootApplication
@EnableCaching
public class Application {
    // Spring Boot application
}
~~~

`@EnableCaching` activates the caching interceptor. Adding a Caffeine dependency or returning a future from a method **does not automatically enable** caching.

## 5. `sync=true` and Concurrent Cache Misses

If ten concurrent requests call `find("P1")` while the cache is empty, `@Cacheable(sync = false)` (default) can allow multiple calls to execute the loader simultaneously. That causes a cache stampede if the loader is expensive.

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public CompletableFuture<Product> find(String id) {
    return repository.findAsync(id);
}
~~~

`sync = true` asks the cache provider to coordinate the **same key** on the cache miss path. With a provider that properly supports `retrieve(key, valueLoader)`, callers can share a single in-flight computation instead of invoking the loader multiple times.

~~~text
Caller A: find(P1) -> MISS -> start future load P1
Caller B: find(P1) -> wait/share computation P1
Caller C: find(P1) -> wait/share computation P1

Future completes Product(P1)
       |
       +--> A receives Product
       +--> B receives Product
       +--> C receives Product
~~~

**Do not equate** `sync=true` with a distributed lock across multiple JVMs. If each application instance has its own local Caffeine cache, App A and App B can still each run a loader. Coordination capability depends on the backend and topology.

### Limitations of Synchronized Caching

Per the `@Cacheable` contract, when `sync=true` is enabled:

- Only a single cache region can be specified for the operation.
- Combining with `unless` is not supported.
- Cannot be combined with multiple other synchronized cache operations on the same method.
- The provider must support synchronized loading; `sync=true` is a hint rather than a cluster-wide exactly-once guarantee.

Example not to use:

~~~java
// Invalid per the sync=true + unless contract.
@Cacheable(
        cacheNames = "products",
        key = "#p0",
        sync = true,
        unless = "#result == null"
)
public CompletableFuture<Product> find(String id) {
    return repository.findAsync(id);
}
~~~

If you need both single-flight and exclusion of certain results from caching, you must design around the actual provider and data policy; you cannot simply attach `unless` to `sync=true`.

## 6. Runnable Example: Java 17 + Spring Boot + Caffeine

We build a small console application demonstrating:

1. Two callers can request the same key before the loader completes.
2. `@Cacheable(sync=true)` combined with Caffeine async mode reuses the same result.
3. The successfully completed future returns a real `Book`; subsequent calls hit the cache.
4. `@CacheEvict` removes the entry after the source changes.
5. The next read loads the new `Book` instead of keeping the old value.

Uses Spring Boot 3.3.5 and Maven, with no web server or external database required.

### Directory Structure

~~~text
future-cache-demo/
├── pom.xml
└── src/main/java/example/futurecache/
    ├── DemoApplication.java
    └── BookService.java
~~~

### `pom.xml`

~~~xml
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
    <artifactId>future-cache-demo</artifactId>
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
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
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
~~~

The Spring Boot parent manages compatible dependency versions. The Caffeine library is added explicitly because `spring-boot-starter-cache` does not automatically include every provider.

### `src/main/java/example/futurecache/BookService.java`

~~~java
package example.futurecache;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    public record Book(String id, String title, int version) {}

    private final ConcurrentMap<String, Book> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public BookService() {
        source.put("B1", new Book("B1", "First Edition", 1));
    }

    @Cacheable(cacheNames = "books", key = "#p0", sync = true)
    public CompletableFuture<Book> find(String id) {
        return CompletableFuture.supplyAsync(() -> {
            loads.incrementAndGet();

            Book book = source.get(id);
            if (book == null) {
                throw new IllegalArgumentException("Unknown book: " + id);
            }

            return book;
        });
    }

    @CacheEvict(cacheNames = "books", key = "#p0")
    public void rename(String id, String newTitle) {
        source.compute(id, (key, oldValue) -> {
            if (oldValue == null) {
                throw new IllegalArgumentException("Unknown book: " + id);
            }

            return new Book(
                    id,
                    newTitle,
                    oldValue.version() + 1);
        });
    }

    public int loads() {
        return loads.get();
    }
}
~~~

Explanation:

- `find` **immediately returns a future**; the source read runs via `CompletableFuture.supplyAsync` on the common pool.
- `loads.incrementAndGet()` is **inside** the task, so it counts actual loader executions, not the number of times a caller merely receives a future.
- `@Cacheable(sync=true)` lets the cache provider coordinate calls with the same key on a miss.
- `rename` updates the source and then `@CacheEvict` removes the cache entry for the same ID after the method completes normally.
- `Book` is an immutable record; this is a more suitable value type to cache than a mutable object being modified by multiple threads.

`CompletableFuture.supplyAsync` uses the common pool in the example, which is not representative of a production executor configuration. Real applications should use an executor with bounded threads/queues, monitor load, and avoid putting uncontrolled blocking I/O onto the common pool.

### `src/main/java/example/futurecache/DemoApplication.java`

~~~java
package example.futurecache;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("books");
        manager.setAsyncCacheMode(true);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1000)
                .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }

    @Bean
    CommandLineRunner demo(BookService books) {
        return args -> {
            CompletableFuture<BookService.Book> first = books.find("B1");
            CompletableFuture<BookService.Book> second = books.find("B1");

            System.out.println("first=" + first.join());
            System.out.println("second=" + second.join());
            System.out.println("loads-after-two=" + books.loads());

            System.out.println("hit=" + books.find("B1").join());
            System.out.println("loads-after-hit=" + books.loads());

            books.rename("B1", "Revised Edition");
            System.out.println("after-evict=" + books.find("B1").join());
            System.out.println("loads-after-evict=" + books.loads());
        };
    }
}
~~~

### Running the Program

Place the two Java files with the exact names/packages shown in the structure above. With JDK 17+ and Maven:

~~~bash
cd future-cache-demo
mvn -q spring-boot:run
~~~

Besides Spring Boot's startup logs, the lines printed by `CommandLineRunner` are:

~~~text
first=Book[id=B1, title=First Edition, version=1]
second=Book[id=B1, title=First Edition, version=1]
loads-after-two=1
hit=Book[id=B1, title=First Edition, version=1]
loads-after-hit=1
after-evict=Book[id=B1, title=Revised Edition, version=2]
loads-after-evict=2
~~~

Explanation:

1. Both `find("B1")` calls use the same cache name/key. With Caffeine async mode and `sync=true`, they share the computation for the same entry within the current cache instance.
2. Both futures complete with `Book(B1, First Edition, v1)`. `loads-after-two=1` indicates the actual loader ran once.
3. The next `find` hits the cache and does not increment `loads`.
4. `rename` updates the source to `Revised Edition/v2`, then evicts `"B1"`; the next lookup misses, runs the loader, and returns the new version. The counter becomes 2.

**Limitation notes:** the demo runs in a single JVM with a local Caffeine cache; it does not demonstrate single-flight across multiple machines. It also does not verify DB transactions, actual TTL after 5 minutes, or error handling. Those cases require separate tests. The output above is based on the Spring 6.1+/Caffeine async mode support path described.

## 7. Why Shouldn't `join()` Be Inside a Cached Method?

One way of writing the method defeats the benefit of asynchrony:

~~~java
// ANTI-PATTERN: actually blocks the thread waiting for the task to complete.
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBlocking(String id) {
    return repository.findAsync(id).join();
}
~~~

By declaration, this method returns `Book` synchronously, not `CompletableFuture<Book>`. The calling thread must wait; the cache can still store `Book`, but the API no longer represents an asynchronous operation.

Another anti-pattern:

~~~java
// ANTI-PATTERN: future is created and waited on immediately, still not non-blocking.
public CompletableFuture<Book> find(String id) {
    Book value = repository.findAsync(id).join();
    return CompletableFuture.completedFuture(value);
}
~~~

The method returns a future, but its body already blocked the thread before returning. `@Cacheable` cannot by itself turn synchronous blocking work into non-blocking I/O.

The proper approach is to return the future of the real task:

~~~java
// Illustrative; repository has a genuinely asynchronous API.
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(String id) {
    return repository.findAsync(id);
}
~~~

The application at the caller layer can use `thenApply`, `thenCompose`, `handle`, or HTTP APIs that support `CompletableFuture`, instead of blocking with `get()`/`join()`.

## 8. `CompletableFuture` Completing with an Error: What Gets Cached?

A task can end with an exception:

~~~java
public CompletableFuture<Book> load(String id) {
    return CompletableFuture.supplyAsync(() -> {
        throw new IllegalStateException("Database unavailable");
    });
}
~~~

This future **does not produce a successful `Book`**. Spring cannot treat an exception as a normal `Book` result to reuse. With cache implementations that support futures, failed load entries need to be handled appropriately so subsequent calls can retry; exact behavior must be verified on the running provider and version.

### Real-World Failures

- **Timeout**: the loader may complete with an error while the cache is holding an in-flight state.
- **Cancellation**: one caller cancels the future; canceling by one caller must not be assumed equivalent to canceling the entire shared load.
- **RejectedExecutionException**: the executor is overloaded and rejects new tasks.
- **Network/database failure**: transient errors can recover; caching exceptions long-term is usually inappropriate.
- **Circuit breaker**: need to define which error is returned and when to retry.
- **Partial side effect**: the future errors, yet the source may have changed; cache and DB need explicit consistency rules.

For example:

~~~java
CompletableFuture<Book> future = books.find("missing-id");

future.whenComplete((book, error) -> {
    if (error != null) {
        // Record the error and return an appropriate status to the caller.
    } else {
        // Only use book when the future completes successfully.
    }
});
~~~

The snippet above is caller-side handling; `books` belongs to the example. Do not directly cache `error.getMessage()` into a `Book` cache, to avoid returning the wrong type and retaining inappropriate error details.

### Should "Not Found" Results Be Cached?

If the method returns null or `Optional.empty()`, negative caching policies must be considered. Caffeine async cache and Spring Cache may have their own rules regarding null/placeholders and cache hits. With `sync=true`, `unless` cannot be used to skip caching null. You can choose an explicit `NotFound` representation, a short TTL and scoped key, or design the loader to throw an appropriate exception and test the retry policy. Do not rely on assuming all providers handle null identically.

## 9. Immutable Values, Mutation, and Cache Consistency

After a future completes, the cache may hold a reference to the `Book` object or a copy depending on the provider. If the value is a mutable object, other threads may observe changes without an explicit cache put.

~~~java
// A mutable DTO can make cached data hard to control.
public class MutableBook {
    public String title;
}
~~~

Prefer immutable values:

~~~java
public record Book(String id, String title, int version) {}
~~~

In the demo, each rename creates a new record. This avoids situations where one thread directly mutates an object that is already cached.

### When a Future Completes After Data Has Already Been Updated

A race condition requiring special care:

~~~text
T1  find(P1) miss, future A loads version 1 and is pending
T2  update(P1) writes version 2, evicts/puts cache
T3  future A completes with version 1
T4  if write ordering is uncontrolled, cache can become stale
~~~

`sync=true` primarily coordinates loads for the same key on misses. It **does not automatically create an atomic transaction** across futures, the DB, `@CachePut`/`@CacheEvict`, and all other writers. A provider may guard against specific races, but scenarios involving pending loads and invalidation must be tested against the real backend.

Common mitigations:

- Include a version/update timestamp with clear semantics from a trusted source.
- Avoid putting a result with an older version than the existing entry.
- Invalidate after transaction commit, or use a transaction-aware cache when appropriate.
- Design invalidation events and retries when multiple instances read/write concurrently.
- Accept a short TTL or stale window if business rules allow, while clearly stating the freshness SLA.

A cache hit can also bypass the `find` method body. Therefore, **do not enforce authorization checks only inside the cached method body**. Place authorization at a boundary that always executes before data retrieval, and build keys with tenant/user/role/projection if results depend on scope.

## 10. `@CachePut` with Asynchronous Results

Spring Cache has a dedicated `@CachePut` operation: the method is always executed, and the cache is updated with the return value. In the Spring 6.1+ model supporting `CompletableFuture`, the successful value produced when the future completes is the result to put, not the pending computation seen by the caller.

~~~java
// Illustrative inside a service with an asynchronous repository.
@CachePut(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> renameAsync(String id, String title) {
    return repository.renameAsync(id, title);
}
~~~

When `renameAsync` completes with the new `Book`, the cache is updated for key `id`. If the method returns `CompletableFuture<Void>` or `CompletableFuture<Boolean>`, do not attach `@CachePut` to a cache holding `Book`: the result type does not match what readers expect. In cases where only update success/failure is known, an evict path so readers reload from the source is usually easier to control.

**Note:** `@CachePut` and `@Cacheable` should not be arbitrarily placed together on the same method, especially future-returning methods; one requires running the method while the other may skip the method on a hit. Separate reads and writes with a consistent key contract.

### `@CacheEvict` and Eviction Timing

With a synchronous update method as in the demo:

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String id, String title) {
    source.update(id, title);
}
~~~

Spring removes the entry per `@CacheEvict` semantics after the method completes normally, when using the default `beforeInvocation=false`. Here `source.update` is illustrative only. When an update method itself returns a future, do not assume eviction timing matches database commit exactly: check the async behavior of the framework/provider/transaction on your deployment version, ideally with integration tests.

## 11. TTL, Entry Count, and Stampede Pitfalls

A completed future does not mean the result is stored forever or will expire automatically. TTL, capacity, and eviction are **cache provider** policies, not default properties of `CompletableFuture`.

Configuration example from the demo:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1000)
        .expireAfterWrite(Duration.ofMinutes(5)));
~~~

- `maximumSize(1000)` sets a target limit on the number of entries per cache instance, **not heap bytes**.
- `expireAfterWrite(5 minutes)` expires values measured from write time; hits do not automatically extend the expiration under this policy.
- When an entry expires, the next access may trigger a new future load.
- If many hot keys expire at the same time, backend calls can spike sharply.

`sync=true` helps coordinate the same key within the scope of a provider; it does not guarantee coordination across application instances with separate local caches. With multiple JVMs using shared Redis, storing shared entries does not by itself prove that loaders hold a distributed lock.

### Do Not Use a Raw Future as a Cache Key

~~~java
// ANTI-PATTERN: key depends on a dynamic stateful object.
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(CompletableFuture<String> idFuture) {
    // Unsuitable: idFuture is not a stable business ID.
}
~~~

Cache by an immutable business identifier, such as `String id`, while also considering tenant, projection, and locale if they affect the result. A key containing a timestamp or a new UUID per request makes the cache useless and increases cardinality.

## 12. Testing: Proving Results Are Cached After Completion

Unit tests that merely do `new BookService()` do not activate Spring's proxy. For caching annotations, test through a **Spring-managed bean**.

### Scenarios to Cover

| Scenario | Setup | Expected Outcome |
| --- | --- | --- |
| Cache miss | Key has no entry yet | Method returns future and loader runs |
| Successful completion | Future completes with `Book` | Subsequent reads use cached result |
| Cache hit | Call same key again after completion | Loader invocation count does not increase |
| Two concurrent misses | Two callers same key, `sync=true` | One loader run if provider supports it |
| Two different keys | Call `"B1"` and `"B2"` | Two independent entries |
| Eviction after update | Update source then evict | Subsequent read loads new version |
| Loader error | Future completes exceptionally | Caller receives error, no fake `Book` returned |
| Cancellation | Cancel one caller's future | Observe shared load/provider semantics |
| TTL | Expire entry via ticker/test clock | Subsequent read must reload |
| Self-invocation | Call `this.find` inside the same bean | Can bypass proxy |
| Multi-instance | Run two JVMs, local Caffeine | No default sharing of entries/coordination |
| Rollback/race | Update while old future pending | Do not return wrong version per SLA |

### Using a Manually Completable Future

To test completion timing without `Thread.sleep`, you can create an incomplete `CompletableFuture<Book>`, return it from a loader invoked via the Spring proxy, and then call `complete(book)` in the test:

~~~java
// Pseudocode illustrating the test idea, not a complete test class.
CompletableFuture<Book> pending = new CompletableFuture<>();
loader.setNextFuture(pending);

CompletableFuture<Book> first = service.find("B1");
assertFalse(first.isDone());

pending.complete(new Book("B1", "New Book", 1));
assertEquals("New Book", first.join().title());

Book again = service.find("B1").join();
assertEquals("New Book", again.title());
assertEquals(1, loader.invocations());
~~~

The snippet above is pseudocode because `loader`, `service`, and assertions/test setup are not declared. In a real test, ensure the cache has observed completion and the put has finished before asserting a hit, to avoid test races. Control executors/tickers when possible so tests are deterministic.

### How Does Testing Two JVMs Differ from Testing Multiple Threads?

Two threads sharing one `CaffeineCacheManager` can coordinate cache misses. Two JVM processes have separate cache instances and can both load key `"B1"`. If you need to prove cluster-wide coordination, run two processes/containers and measure loader counts at the shared source; do not extrapolate from a single-JVM unit test.

## 13. Common Pitfalls and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@Cacheable` has no effect | Missing `@EnableCaching`, internal call within bean, or bean created with `new` | Enable caching, call through Spring proxy |
| Hit returns wrong type | Manually storing `CompletableFuture` as business value or legacy custom provider | Use Spring 6.1+ and verify async cache contract |
| Future completed but next call still misses | Provider does not support suitable async retrieval/put, or different keys | Check `Cache.retrieve`, configuration, and integration tests |
| Both requests run the loader | `sync=false` or provider does not coordinate in-flight loads | Use `sync=true` with a supporting provider |
| `sync=true` causes configuration error | Combined with multiple caches or `unless` | Follow synchronized caching restrictions |
| Cache holds stale data | No invalidation after update | Put/evict by key and transaction |
| Future fails repeatedly | Source/executor failure not yet recovered | Add retry/backoff, bulkhead/circuit breaker per business needs |
| Cache holds failed future forever | Manual future cache without cleanup | Remove failed entries, use a proper provider |
| `join()` makes the API slow | Blocking request thread inside the method | Return future and compose asynchronously |
| `@CachePut` writes `Boolean` instead of `Book` | Update method returns status | Use eviction or return the new `Book` |
| Tenant mix-up | Key only contains an ID not unique across scopes | Use a key including trusted tenant/scope |
| Cached value changes unexpectedly | Mutable cached object, store-by-reference | Use immutable DTOs/versions |
| Assuming cache syncs across pods automatically | Local Caffeine per JVM | Use shared cache/invalidation if needed |

## 14. Self-Check Exercises

**Exercise 1.** A `@Cacheable` method returns `CompletableFuture<Book>` in Spring 6.1+. After the future completes successfully, what data does the cache represent?  
**Answer:** the `Book` value produced when the future completes, with internal representation depending on the provider; not a business contract to store a pending future forever.

**Exercise 2.** If `CompletableFuture<Book>` has not completed yet, is the cache guaranteed to already hold a reusable `Book`?  
**Answer:** no. The provider may hold a running future to share load, but the complete `Book` value does not exist until successful completion.

**Exercise 3.** Can you enable `@Cacheable(sync=true, unless="#result == null")`?  
**Answer:** no. `sync=true` does not support `unless` per Spring's contract.

**Exercise 4.** Two replicas both use local Caffeine. Does that guarantee only one loader runs for the same ID across the whole cluster?  
**Answer:** no. They have separate cache instances; synchronization within one instance does not automatically span across other JVMs.

**Exercise 5.** A future completes exceptionally. Should the exception be cached as a successful `Book`?  
**Answer:** no. Error handling and retry/fallback policies must be handled separately; test the provider's cleanup behavior.

**Exercise 6.** Is `@CachePut` on a method returning `CompletableFuture<Boolean>` appropriate for a cache storing `Book`?  
**Answer:** no. The completed value is `Boolean`; either return an appropriate `Book` or use eviction.

**Exercise 7.** Why does the example use an immutable `Book` record?  
**Answer:** to prevent one caller from mutating an object that multiple other callers read from the cache; new values are represented by a new record/version.

**Exercise 8.** Does `setAsyncCacheMode(true)` automatically set a five-minute TTL?  
**Answer:** no. It enables Caffeine's asynchronous access mode; TTL must be configured separately on the Caffeine builder.

**Exercise 9.** A test calls `service.find("B1").join()` right when the source returns a failed future, and sees an exception. Does this prove the cache is broken?  
**Answer:** no. It may simply demonstrate a failing loader; separate tests for success, failure, hit, retry, and provider behavior are needed.

**Exercise 10.** When should asynchronous caching be avoided?  
**Answer:** when results are unstable, highly sensitive to authorization/version/transactions, cache misses bring no benefit, or the backend lacks appropriate support. Prioritize consistent design before optimization.

## References

- Spring Framework – **Declarative Annotation-based Caching** (synchronized caching, CompletableFuture and reactive return types sections): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – **Cache Abstraction**: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – Javadoc `org.springframework.cache.Cache`, `retrieve` methods: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – Javadoc `CaffeineCacheManager`, `setAsyncCacheMode`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Boot – **Caching**: https://docs.spring.io/spring-boot/reference/io/caching.html
- Java 17 – `CompletableFuture` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Caffeine – **Eviction** and expiration: https://github.com/ben-manes/caffeine/wiki/Eviction

**Key takeaway:** with Spring Framework 6.1+ and a provider supporting async retrieval, `@Cacheable` can handle methods returning `CompletableFuture<T>` and cache **the `T` value when the future completes successfully**. Caffeine async mode enables using the appropriate access path; `sync=true` reduces duplicate loads for the same key within the provider's scope, not a distributed lock. Asynchronous completion does not eliminate the need for exception handling, invalidation, TTL, transactions, security, and race testing.