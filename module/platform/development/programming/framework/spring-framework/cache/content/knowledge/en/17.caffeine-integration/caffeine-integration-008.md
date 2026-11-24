# Asynchronous Cache Mode and setAsyncCacheMode in Spring Cache

## Lesson Objectives

Spring Cache is commonly used synchronously: call a method, check the cache, execute the method on a miss, wait for the result, write to the cache, and return the result. However, in modern applications, methods can return `CompletableFuture<T>`, `Mono<T>`, or `Flux<T>`. In these cases, **the value is not ready at the exact moment the Java method returns**.

Since version 6.1, Spring Framework has supported caching values produced by asynchronous and reactive return types. With Caffeine, to leverage native asynchronous retrieval, enable:

~~~java
cacheManager.setAsyncCacheMode(true);
~~~

This lesson explains that mechanism, version prerequisites, how to configure `CaffeineCacheManager`, when the value is actually stored, and how to test it.

After this lesson, you will be able to:

- Distinguish **a method returning a future** from **the value inside a completed future**.
- Understand how `@Cacheable` works with `CompletableFuture`, Reactor `Mono`, and `Flux` starting in Spring 6.1.
- Explain why `CaffeineCacheManager` needs `setAsyncCacheMode(true)` to support native asynchronous retrieval.
- Configure `spring-context-support`, Caffeine 3.0+, and the cache manager properly.
- Run a Java 17 + Spring Framework 6.2.10 + Caffeine program to observe cache hits/misses with `CompletableFuture`.
- Understand the impact of `sync = true`, future failures, nulls, concurrency, back-pressure, and local cache limits.
- Know when to use asynchronous caching versus a dedicated reactive caching model.

> **Core rule:** When a `@Cacheable` method returns `CompletableFuture<T>`, Spring caches **the value T once the future completes successfully**. With Caffeine, `setAsyncCacheMode(true)` switches the manager to native `AsyncCache`, enabling `CompletableFuture`-based retrieval without blocking threads to wait for results.

## 1. Why Is Asynchronous Cache Mode Needed?

### 1.1. Traditional Synchronous Caching

For a method returning an object directly:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

This is **illustrative code**, assuming `Book` and `repository` exist.

Typical flow:

~~~text
Caller
  |
  v
Spring cache advice
  |
  +--> Cache.get(key)
          |
          +--> HIT  -> returns stored Book
          |
          +--> MISS -> calls findBook(isbn)
                         |
                         +--> waits for repository to return Book
                         |
                         +--> Cache.put(key, Book)
                         |
                         +--> returns Book to caller
~~~

The method call returns only after the `Book` object is obtained. The cache can perform `get`/`put` via synchronous APIs.

### 1.2. When a Method Returns CompletableFuture

An asynchronous method looks like:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return repository.findByIsbnAsync(isbn);
}
~~~

This is also **illustrative code**. When the method runs, it returns a `CompletableFuture<Book>` handle; the `Book` data may still be loading from a database or remote service.

Spring needs to handle two cases:

1. On a **cache miss**, receive the future from the method, observe it, and put the `Book` value into the cache once the future completes successfully.
2. On a **cache hit**, return a `CompletableFuture` representing the cached value so the caller continues using the asynchronous API.

The future object itself should not be cached as a long-lived business result. Spring adapts to store **the value produced by the future**, while the caller still receives the asynchronous return type.

~~~text
Cache MISS:

Spring -> calls findBook("ISBN-1")
                  |
                  +--> returns CompletableFuture<Book>
                                |
                         task still running
                                |
                         future completes
                                |
                            Book value
                                |
                         cache put Book
                                |
                         completes future returned to caller


Cache HIT:

Spring -> checks cache ISBN-1
                  |
             has Book value
                  |
       returns CompletableFuture<Book>
       representing cached value
                  |
               caller
~~~

**Crucial timing:** the Java method returning a future does not mean the cache already holds the final value. The value is stored only after the future completes successfully.

### 1.3. Which Spring Framework Version Added Support?

Starting with **Spring Framework 6.1**, cache annotations recognize `CompletableFuture` and reactive return types, adapting cache interactions accordingly:

- `CompletableFuture<T>`: caches the `T` object once the future completes; cache hits are returned as a `CompletableFuture`.
- Reactor `Mono<T>`: caches the object emitted by the publisher when available; cache hits are returned as a `Mono`.
- Reactor `Flux<T>`: Spring collects emitted items into a `List<T>` and caches the list once the sequence completes; cache hits are adapted back into `Flux<T>`.

This differs from older behavior that treated a `Mono` or `Flux` as a plain Java object and cached the publisher itself.

## 2. Async Return Type Does Not Equal Async Cache Provider

There are two independent parts:

1. **Method produces an asynchronous result:** the method returns `CompletableFuture` or a reactive publisher.
2. **Cache provider supports asynchronous retrieval:** the cache must offer a non-blocking lookup/load mechanism compatible with that return type.

Merely changing a method signature to `CompletableFuture<T>` does not automatically give every `CacheManager` native asynchronous retrieval.

Spring Framework offers two notable examples:

| Cache manager | Supports future-based retrieval |
| --- | --- |
| Spring's `ConcurrentMapCacheManager` | Adapts to `CompletableFuture`-based retrieval |
| `CaffeineCacheManager` | Native support when `setAsyncCacheMode(true)` is enabled |
| Other providers | Must verify implementation and version; do not infer merely from having a Spring Cache adapter |

Caffeine requires **Caffeine 3.0 or higher** for the native asynchronous cache mode used by Spring.

### 2.1. Cache API with Asynchronous Retrieval

Since Spring Framework 6.1, the `Cache` interface includes operations such as:

~~~java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key,
    Supplier<CompletableFuture<T>> valueLoader
);
~~~

These are **abbreviated API signatures for explanation**, not code you need to implement yourself.

- `retrieve(key)`: looks up by key with a non-blocking API; may determine a miss immediately, or the miss outcome may become clear once the future completes.
- `retrieve(key, valueLoader)`: looks up and loads via future if necessary.
- Compatible providers must preserve future, null, and error semantics appropriately.

Spring's caching interceptor uses this mechanism to avoid turning every operation into a synchronous `.join()` or `.get()`.

### 2.2. Why Does Caffeine Need setAsyncCacheMode(true)?

By default, `CaffeineCacheManager` creates **synchronous** native Caffeine caches. Those caches suit regular synchronous `get`/`put` operations, yet do not provide the native async retrieval Spring wants for `CompletableFuture`/reactive flows.

When calling:

~~~java
cacheManager.setAsyncCacheMode(true);
~~~

the manager switches the caches it creates to **Caffeine AsyncCache**. These caches:

- support future-based `Cache.retrieve(...)`;
- can still be accessed via synchronous APIs;
- apply to caches declared via `setCacheNames(...)` as well as on-demand caches;
- require Caffeine 3.0+.

This is a setting on **`CaffeineCacheManager`**, not an attribute on `@Cacheable` or the general `CacheManager` interface.

### 2.3. Async Cache Does Not Automatically Run Methods on a Thread Pool

`setAsyncCacheMode(true)` does not automatically turn a synchronous method asynchronous, nor does it create an executor for methods. The method itself must return an asynchronous type or use the provider's async APIs.

Example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return remoteClient.fetchAsync(isbn);
}
~~~

Here, `remoteClient.fetchAsync` is responsible for creating the future. Caffeine async mode lets the cache handle the future in a non-blocking manner.

If a method returns `Book` directly, it remains a synchronous method even when the cache manager is in async mode.

## 3. Configuring CaffeineCacheManager Properly

### 3.1. Required Dependencies

The example uses:

- Java 17+
- Spring Framework 6.2.10
- Caffeine 3.1.8 (meets Caffeine 3.0+ requirement)
- Maven

Required dependencies:

~~~xml
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
~~~

`CaffeineCacheManager` lives in Spring's cache provider support module (`spring-context-support`). Adding only `spring-context` and `caffeine` will not suffice to compile Spring's integration class.

### 3.2. Basic Java Config

~~~java
import java.util.List;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();

        manager.setAsyncCacheMode(true);
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder().maximumSize(1_000)
        );
        manager.setCacheNames(List.of("books", "authors"));

        return manager;
    }
}
~~~

This is **configuration code ready to integrate into a Spring app**; add `@EnableCaching` to the application configuration along with the dependencies from section 3.1.

Explanation:

- `new CaffeineCacheManager()`: creates a manager capable of managing cache regions.
- `setAsyncCacheMode(true)`: enables native Caffeine `AsyncCache`.
- `setAllowNullValues(false)`: disallows null values; recommended when using async mode because future semantics stay simpler and unnecessary wrapping is avoided.
- `setCaffeine(...)`: sets shared Caffeine configuration, here capped at 1,000 entries.
- `setCacheNames(...)`: pre-declares two cache regions, `books` and `authors`.

If on-demand cache creation is desired, you can use a dynamic manager without passing initial names; however, keep spelling and region counts under control. Once static names are declared, annotations must use exact names from the list.

### 3.3. Enable Async Mode Before Using Caches

Finish configuring the manager before the application starts receiving cache calls. In particular, avoid toggling `asyncCacheMode` arbitrarily after caches have been created and traffic is active.

Centralize cache manager configuration in one place so different beans do not accidentally create inconsistent sync and async caches.

### 3.4. Can Synchronous and Asynchronous APIs Be Used Together?

Yes. Per the `CaffeineCacheManager` contract, caches created in async mode can still be used through synchronous APIs. Still, standardize usage within each service and measure real latency; supporting both APIs does not mean sync and async paths share identical performance characteristics.

## 4. Runnable Java 17 Example: @Cacheable with CompletableFuture

The following example builds a service returning `CompletableFuture<String>`. The future runs on an `ExecutorService`; on completion, Spring puts the value into the Caffeine async cache. Calling again with the same key receives the cached result without re-executing the method body.

### 4.1. Project Structure

~~~text
spring-caffeine-async/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncCacheDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-caffeine-async</artifactId>
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

### 4.3. src/main/java/demo/AsyncCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class AsyncCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                new CaffeineCacheManager();

            manager.setAsyncCacheMode(true);
            manager.setAllowNullValues(false);
            manager.setCaffeine(
                Caffeine.newBuilder().maximumSize(100)
            );
            manager.setCacheNames(List.of("books"));
            return manager;
        }

        @Bean(destroyMethod = "shutdown")
        public ExecutorService cacheExecutor() {
            return Executors.newFixedThreadPool(2);
        }

        @Bean
        public BookService bookService(ExecutorService cacheExecutor) {
            return new BookService(cacheExecutor);
        }
    }

    public static class BookService {
        private final ExecutorService executor;
        private final AtomicInteger sourceLoads = new AtomicInteger();

        public BookService(ExecutorService executor) {
            this.executor = executor;
        }

        @Cacheable(
            cacheNames = "books",
            key = "#p0",
            sync = true
        )
        public CompletableFuture<String> find(String isbn) {
            int loadNumber = sourceLoads.incrementAndGet();

            return CompletableFuture.supplyAsync(
                () -> "Book-" + isbn + " (load=" + loadNumber + ")",
                executor
            );
        }

        public int sourceLoads() {
            return sourceLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);

            CompletableFuture<String> first = service.find("A");
            System.out.println("First: " + first.join());

            CompletableFuture<String> second = service.find("A");
            System.out.println("Second: " + second.join());

            System.out.println(
                "Loads after hit: " + service.sourceLoads());

            CompletableFuture<String> other = service.find("B");
            System.out.println("Other key: " + other.join());

            System.out.println(
                "Final loads: " + service.sourceLoads());
        }
    }
}
~~~

### 4.4. Running the Program

From the directory containing `pom.xml`, requires JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncCacheDemo
~~~

Lines **printed by the program** (excluding Maven logs):

~~~text
First: Book-A (load=1)
Second: Book-A (load=1)
Loads after hit: 1
Other key: Book-B (load=2)
Final loads: 2
~~~

### 4.5. Output Analysis

1. The first `find("A")` call is a cache miss. The method body increments `sourceLoads` to 1 and returns a future running on the executor.
2. The caller receives the `CompletableFuture` and calls `.join()` **in the demo program to wait** and print the result. Spring observes the future and stores the completed value in the cache.
3. The second `find("A")` call queries the same cache name/key. This is a cache hit; the caller still receives a `CompletableFuture<String>`, yet the value comes from the cache. The method body does not increment the counter.
4. Calling `find("B")` produces a new key and misses; the method body runs a second time and the result shows `load=2`.

**Do not confuse the role of `.join()`:** the example only calls `.join()` in `main` to display output in deterministic order. The service itself does not block waiting for the future before returning. In real asynchronous controllers or services, keep composing the future instead of calling `.join()`/`.get()` just to force synchronous execution.

### 4.6. Why Use sync = true?

The example declares `sync = true` to ask the cache to coordinate when multiple calls for the same key miss concurrently. Spring 6.1+ supports synchronized caching for `CompletableFuture` and reactive types when the provider supports future-based retrieval.

With Caffeine async mode, native `AsyncCache` supports the corresponding retrieval path. However:

- `sync = true` carries Spring Cache restrictions (e.g., one cache operation for that cache, cannot combine with `unless`).
- Synchronization behavior depends on how the provider executes the loading operation.
- Caffeine is an in-JVM local cache; it does not turn into a distributed lock across multiple instances.
- Without `sync = true`, do not assume every provider guarantees a single load when concurrent requests miss simultaneously.

## 5. What Happens When a Future Fails?

The cache can store **only successful result values**. A future completing exceptionally supplies no successful business object to place in the cache.

Illustrative example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return remoteClient.fetchAsync(isbn);
}
~~~

If the future completes with an exception:

- The caller receives the failure via the future (e.g., `CompletionException` on `.join()`).
- Spring has no successful `Book` result to cache.
- Subsequent calls for the same key may re-run the source.
- Do not cache exceptions by turning them into error-result objects unless negative caching is intentionally designed by the domain.

### 5.1. Distinguishing Exceptions from Error-Reporting DTOs

Suppose a method catches errors and returns:

~~~java
public record BookResult(
    boolean success,
    String title,
    String errorCode
) {}
~~~

If the future completes normally with `BookResult(success=false, ...)`, from a caching standpoint that is still **a successful completion value**. It can be cached unless vetoed by a condition such as `unless`.

If error results should not be cached, design a condition based on the return value, or let the future complete exceptionally per an appropriate contract.

### 5.2. Cancellation

A cancelled future likewise produces no successful completion value to cache. Define which callers have the authority to cancel shared work and whether cancellation affects other callers awaiting the same key; avoid designs where one request arbitrarily cancels work shared across multiple requests.

## 6. Mono and Flux: Reactive Caching Since Spring 6.1

Spring 6.1 and later recognize Reactor publishers in cache annotations. Add Reactor dependencies if the application uses these types.

### 6.1. Mono<T>

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Mono<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

This is **illustrative code**; the repository must return `Mono<Book>`.

- On miss, Spring waits for the publisher to emit a value and caches the `Book` object once ready.
- On hit, Spring returns a `Mono<Book>` backed by the cached value.
- `Mono.empty()` must be evaluated alongside the cache and provider's null/empty policy; do not assume all cache managers share identical empty-value semantics.

### 6.2. Flux<T>

~~~java
@Cacheable(cacheNames = "booksByAuthor", key = "#p0")
public Flux<Book> findBooksByAuthor(String author) {
    return repository.findByAuthor(author);
}
~~~

This is **illustrative code**; the repository must return `Flux<Book>`.

Spring collects elements emitted by `Flux` into a `List<Book>` and caches the list only when the publisher completes. On hit, the cache supplies the list, which is converted back into a `Flux` for the caller.

This means:

- Results are not served from the cache item-by-item independently.
- A very large `Flux` may have to be buffered entirely in memory.
- An infinite stream will never complete to produce a cacheable list value.
- This style of caching is **coarse-grained**; it does not replace streaming/back-pressure design.

### 6.3. Caffeine Async Mode with Reactive Types

For Caffeine, if you want Spring to handle reactive publishers using native asynchronous caching, enable:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setAsyncCacheMode(true);
~~~

Requires Caffeine 3.0+ and appropriate Reactor dependencies. If the app uses another cache provider, verify whether that provider supports the corresponding `Cache.retrieve` operations.

### 6.4. When Annotation Caching Is Unsuitable for Complex Reactive Flows

Spring documentation notes that annotation-driven caching is unsuitable for complex reactive interactions requiring fine-grained composition and back-pressure. Annotation caching operates on publisher outcomes at a coarse level:

- `Mono`: a single value.
- `Flux`: collected into a list.

If you need per-element caching, stateful streams, windowing/batching, per-item TTLs, or infinite streams, consider dedicated reactive caching mechanisms or programmatic designs tailored to your data model.

## 7. Difference Between setAsyncCacheMode and @Async

These two concepts are easily confused:

| Mechanism | Role |
| --- | --- |
| `CompletableFuture<T>` | Return type describing a result available in the future |
| `@Async` | Spring dispatches the method call onto a configured `TaskExecutor` |
| `CaffeineCacheManager.setAsyncCacheMode(true)` | Configures the Caffeine manager to create native async caches supporting `Cache.retrieve` |
| `@Cacheable` | Controls cache lookup/load/put for the invoked method |
| `@Cacheable(sync = true)` | Requests coordinated cache loading on concurrent misses, within provider limits |

### 7.1. @Async Is Not Needed Just Because a Method Returns CompletableFuture

A method can create its future directly from an HTTP client, database client, or executor:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> findBook(String isbn) {
    return webClient.get()
        .uri("/books/{isbn}", isbn)
        .retrieve()
        .bodyToMono(Book.class)
        .toFuture();
}
~~~

This is **illustrative code** requiring real WebClient/endpoint configuration. `@Cacheable` can handle future types when the cache provider is compatible; `@Async` does not need to be added just for caching to recognize the future.

### 7.2. @Async Does Not Automatically Enable Async Cache Mode

If a method has `@Async` and returns a future, the executor controls method execution. Yet Caffeine still needs `setAsyncCacheMode(true)` configured if you want native future-based cache retrieval.

Conversely, enabling Caffeine async mode does not automatically run synchronous methods on a background thread. Both parts must be configured according to their own purpose.

### 7.3. Avoid Blocking Inside Asynchronous Paths

Statements such as:

~~~java
Book book = service.findBook(isbn).join();
~~~

may be needed in synchronous boundary code, tests, or console demos. Yet inside a reactive/future pipeline, blocking occupies a thread and defeats non-blocking benefits. Compose instead:

~~~java
return service.findBook(isbn)
    .thenApply(Book::title);
~~~

This is an **illustrative snippet**; the enclosing method's return type must match.

## 8. Null Values and Async Cache Semantics

Caffeine async mode supports some of Spring's null-value wrapping mechanics, yet `CaffeineCacheManager` documentation recommends **`setAllowNullValues(false)`** when using asynchronous cache mode.

Reasons:

- Caffeine async caches use `CompletableFuture` handles.
- Disallowing nulls keeps future-based retrieval semantics simpler.
- Avoids an extra wrapping layer around the handles provided by Caffeine.

If the domain has "not found" outcomes, choose an explicit representation:

- A future completing with a result DTO carrying `found=false`.
- `Optional<T>` if the contract fits.
- An exception for genuine error cases.
- A negative-cache value with its own TTL if supported by the provider and design.

Never return null casually and assume every async cache provider handles it identically. Specifically, with `setAllowNullValues(false)`, test the branch where a future completes with null on your exact Spring/Caffeine versions.

## 9. Cache Keys, Cache Names, and Data Consistency Remain Unchanged

Switching to async mode does not alter cache entry resolution rules:

- `cacheNames` selects the cache region.
- `key` or `KeyGenerator` determines the key.
- `condition`/`unless` determine whether caching applies or stores the result per configuration.
- `@CachePut` and `@CacheEvict` still handle entry updates and removals.

Example of two methods with different signatures needing the same key:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> find(String isbn) {
    return repository.findAsync(isbn);
}

@CachePut(cacheNames = "books", key = "#p0")
public CompletableFuture<Book> update(String isbn, BookUpdate input) {
    return repository.updateAsync(isbn, input);
}
~~~

This is **illustrative code**. When using `@CachePut` to update results, ensure both methods share the same cache name/key and that the update's future yields the exact value to store.

Async mode does not solve:

- stale data after database changes;
- transaction rollbacks after cache puts;
- cross-instance invalidation;
- multi-node cache stampedes;
- wrong keys or missing tenant dimensions in keys;
- races where an older future finishes late and overwrites a newer update on the same key.

Those remain data-consistency and provider-policy concerns requiring dedicated design.

## 10. Concurrency and Simultaneous Requests for the Same Key

A common scenario:

~~~text
Request A ----> cache miss ----> load ISBN-1
Request B ----> cache miss ----> load ISBN-1
Request C ----> cache miss ----> load ISBN-1
~~~

If the cache/provider does not coordinate loading, multiple requests may hit the source simultaneously. With Caffeine async cache, native `AsyncCache` can manage in-flight futures per key; Spring also supports `@Cacheable(sync = true)` for future/reactive types when the provider supports it.

### 10.1. Using sync = true When Appropriate

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    sync = true
)
public CompletableFuture<Book> findBook(String isbn) {
    return repository.findAsync(isbn);
}
~~~

This is illustrative code. `sync=true` asks the provider to coordinate loads for the same key. Remember the limits of synchronized caching:

- applies only to a single cache operation/target cache per Spring's contract;
- cannot be combined with `unless` in unsupported ways;
- behavior depends on provider support for atomic/synchronized loading;
- local Caffeine caches coordinate only within a single JVM, not as a distributed lock.

### 10.2. Incomplete Futures and Multiple Callers

With an async cache, a value being loaded can be represented by an in-flight future. When the provider supports atomic async loading, concurrent calls for the same key can share the same load operation. However, do not generalize this property across every `CacheManager` or multi-instance deployments.

Test two distinct scenarios separately:

1. **Same JVM, same key, concurrent misses:** count source invocations with `sync=true` enabled vs. disabled.
2. **Multiple instances, same key, concurrent misses:** each local Caffeine cache can load independently; cluster-wide coordination requires a shared provider or distributed mechanism.

### 10.3. Races When Source Data Updates

An older future can complete after a newer update/evict operation. Without versioning or update ordering in the design, the stale result risks overwriting the entry after data has changed.

Handling depends on the system:

- version/fencing tokens in values or keys;
- post-commit invalidation;
- provider-supported atomic updates/versioning;
- version checks prior to put;
- avoiding unrelated tasks writing the same key without ordering rules.

`setAsyncCacheMode(true)` only provides asynchronous cache interaction, **not** versioning or transactions.

## 11. Common Errors and Fixes

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@Cacheable` returns a future, yet Caffeine reports a retrieval error | Manager does not have async mode enabled | Verify `setAsyncCacheMode(true)` |
| `CaffeineCacheManager` not found at compile time | Missing `spring-context-support` | Add matching version dependency |
| Async mode has no effect | Caffeine version too old | Use Caffeine 3.0+ |
| Method still runs on subsequent call for same key | Previous future had not completed, or key/cache name differs | Wait for future completion, then check key again |
| Caller receives future, yet cache lacks value right on return | Future is still pending | Observe after future completes; do not check cache too early |
| Future failed, yet assumed exception was cached | Method returned exceptional future | Handle completion failure; do not treat exceptions as values |
| Future hit unexpectedly returns null | Unclear null policy or empty result | Check `setAllowNullValues`, Optional/empty semantics |
| Flux consumes lots of memory | Spring buffers entire Flux into a List to cache | Do not use annotation caching on large/infinite streams |
| Reactive back-pressure behaves unexpectedly | Cache interacts at whole-value/publisher level | Use a dedicated reactive caching mechanism |
| `@Async` present, yet cache still blocks | Cache manager/provider lacks async retrieve support | Distinguish executor from cache async mode |
| Multiple misses on same key cause multiple source calls | `sync` omitted or provider does not coalesce loads | Check `sync=true` and provider semantics |
| Instance A gets cache hit while B still misses | Caffeine is a local cache | Use shared cache or accept per-node caching |
| Cache holds stale data after updates | Missing invalidation/versioning | `@CachePut`, `@CacheEvict`, after-commit |
| Method not cached on internal calls | Self-invocation in proxy mode | Extract bean or configure interception properly |

## 12. Testing Asynchronous Caching Properly

### 12.1. Do Not Assert Immediately After the Method Returns a Future

The following may assert too early:

~~~java
CompletableFuture<String> result = service.find("A");
// Future may not have completed yet and cache may not hold the String yet.
assertThat(cache.get("A")).isNotNull();
~~~

This is **illustrative code showing poorly timed testing**. Until the future completes, the final value is not yet cached.

Wait for completion in tests:

~~~java
String value = service.find("A").join();
assertThat(value).isEqualTo("expected");
~~~

After the future completes, verify the subsequent call and the source counter. In real code, `CompletableFuture` chains and async-aware test assertions can avoid arbitrary blocking.

### 12.2. Minimum Test Suite

- **Miss → future success:** method body runs once; result is cached upon completion.
- **Hit after completion:** same key returns a future with the stored result without re-running the source.
- **Different key:** triggers an independent load.
- **Exceptional future:** no successful business result is cached; subsequent call behaves per provider policy.
- **Future cancellation:** confirm no successful value is stored.
- **Concurrent misses on same key:** compare behavior with `sync=true` vs. without.
- **Null/empty:** verify `setAllowNullValues(false)` policy or empty values.
- **Provider errors:** test connection errors, timeouts, and appropriate `CacheErrorHandler`.
- **Invalidation:** update/evict while an older future is still in flight; test races.
- **Reactive:** single-value Mono, Mono.empty, and finite small Flux completing to a list; never use an infinite Flux in cache annotation tests.

### 12.3. Observing Source Execution Counts

Use `AtomicInteger` or a spy/mock repository to count executions. Do not measure response time alone: timing fluctuates with thread scheduling and does not prove a cache hit.

In the demo, the `sourceLoads` counter is direct evidence:

- first call to A: count 1;
- second call to A after completion: count remains 1;
- call to B: count 2.

### 12.4. Testing Against the Real Provider

An in-memory Caffeine test verifies the Caffeine manager setup. If production uses Redis, JCache, or another provider, write separate integration tests against that provider. Never treat a Caffeine test as proof that every backend supports native async retrieval.

## 13. When Should You Use Caffeine Async Mode?

Suitable when:

- services already use `CompletableFuture` or Reactor and want caching without blocking threads;
- local Caffeine caching fits the deployment architecture;
- results are reusable by key and have a clear invalidation policy;
- you need async cache retrieval / native future handles;
- the team has concurrency tests and observes source load counts.

Consider alternatives when:

- data must be shared across instances with consistent invalidation;
- `Flux` is huge or infinite and cannot be collected into a list;
- reactive flows need complex composition or fine-grained back-pressure;
- methods have mandatory side effects on every invocation;
- data has strict consistency/transactional requirements that the cache provider cannot satisfy;
- methods are simple synchronous operations where synchronous hit/miss suffices with no clear gain from going async.

### Quick Selection Table

| Need | Approach |
| --- | --- |
| Method returns synchronous object | Synchronous Cache API; async mode not required |
| Method returns `CompletableFuture<T>` + Caffeine | `setAsyncCacheMode(true)` |
| Method returns `Mono<T>` + Caffeine | Spring 6.1+, Caffeine async mode, test empty semantics |
| Method returns small finite `Flux<T>` | Can cache the collected list if semantics are acceptable |
| Large/infinite Flux needing back-pressure | Dedicated reactive cache; do not cache publisher via annotation |
| Need to coalesce concurrent misses on same key | Consider `sync=true` and provider support |
| Need cache shared across multiple instances | Shared provider or distributed invalidation mechanism |

## 14. Implementation Checklist

- [ ] Spring Framework 6.1 or later if `CompletableFuture`/Mono/Flux adaptation is needed.
- [ ] Caffeine 3.0+ if using native async mode.
- [ ] `spring-context-support` dependency matching the Spring Framework version.
- [ ] Compatible Caffeine dependency present.
- [ ] `@EnableCaching` enabled in the Spring context.
- [ ] Caffeine manager calls `setAsyncCacheMode(true)` before caches are used.
- [ ] Consider `setAllowNullValues(false)` per async mode recommendation.
- [ ] Cache names/keys declared accurately; no accidental creation of misspelled regions.
- [ ] Methods genuinely return futures/publishers without blocking beforehand.
- [ ] Only cache values reusable for the same key.
- [ ] Future failures/cancellations are not unintentionally turned into cached values.
- [ ] With `sync=true`, verify annotation limitations and provider capabilities.
- [ ] Do not treat local Caffeine as a distributed cache or lock.
- [ ] `Flux` size is bounded and cached lists stay within memory limits.
- [ ] Assert after future completion rather than reading the cache too early.
- [ ] Test invalidation, concurrency, provider errors, and multi-instance behavior.
- [ ] Monitor hits/misses, load durations, in-flight futures, exceptions, and memory.

## 15. Self-Check Questions

**1.** Since which Spring Framework version has caching for `CompletableFuture` been supported?  
**Answer:** Since Spring Framework 6.1.

**2.** When a `@Cacheable` method returns `CompletableFuture<Book>`, what object does Spring cache?  
**Answer:** The `Book` value produced when the future completes successfully; cache hits are returned wrapped in a future.

**3.** Why does Caffeine need `setAsyncCacheMode(true)`?  
**Answer:** So CaffeineCacheManager creates native Caffeine AsyncCache instances supporting future-based retrieval operations like `Cache.retrieve`.

**4.** Which Caffeine version is required for this native async mechanism?  
**Answer:** Caffeine 3.0 or higher.

**5.** Does `setAsyncCacheMode(true)` automatically run synchronous methods on a background thread?  
**Answer:** No. It changes the cache type created by the manager; methods must return futures/publishers or use appropriate async APIs.

**6.** Does Spring automatically cache a `Flux<T>` item-by-item as elements are emitted?  
**Answer:** Not with default annotation adaptation; Spring collects emitted items into a `List<T>` and caches it when the Flux completes.

**7.** Why is annotation caching unsuitable for an infinite Flux?  
**Answer:** The Flux never completes to produce a final list; buffering all items can also exhaust memory.

**8.** Is `@Async` required for `@Cacheable` to understand `CompletableFuture`?  
**Answer:** No. Spring recognizes future return types since 6.1; `@Async` is a separate mechanism for dispatching execution onto a TaskExecutor.

**9.** Does an exceptionally completed future produce a successful cached value?  
**Answer:** No. No successful business value exists to store.

**10.** Why should `setAllowNullValues(false)` be considered when enabling async mode?  
**Answer:** Spring recommends it to keep future semantics simpler and avoid extra handle wrapping for nulls.

**11.** Is `sync=true` a distributed lock across multiple Caffeine instances?  
**Answer:** No. Caffeine is a local cache; synchronized loading applies only within the supporting provider/JVM.

**12.** Why wait for the future to complete before asserting the cache holds the value?  
**Answer:** Because the value is stored when the future completes, not necessarily the moment the method returns the handle.

**13.** If a method returns a synchronous object, is enabling async cache mode mandatory?  
**Answer:** No. You can keep using synchronous APIs; async mode is only needed when supporting native async retrieval.

**14.** Does async cache mode automatically solve stale data after database updates?  
**Answer:** No. `@CachePut`, `@CacheEvict`, TTLs, or proper invalidation mechanisms are still needed.

## References

- Spring Framework 6.2 — Declarative Annotation-based Caching, section "Caching with CompletableFuture and Reactive Return Types": https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2.10 — CaffeineCacheManager Javadoc (`setAsyncCacheMode`): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2 — Cache Abstraction: https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html
- Spring Framework 6.2 — Cache API (`retrieve`): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/Cache.html
- Caffeine — Asynchronous computations: https://github.com/ben-manes/caffeine/wiki/Population
- Caffeine — User guide and features: https://github.com/ben-manes/caffeine/wiki