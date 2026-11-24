# Returning Results from Cache and Skipping the Method Body with `@Cacheable`

## 1. The Exact Meaning of "Skipping the Method Body"

When a Spring method is annotated with `@Cacheable`, the call **passes through a cache interceptor**. The interceptor looks up a stored value using the **cache name** and **key**. If a valid entry is found (**cache hit**), it returns that value to the caller **directly at the interceptor**, **without entering the target method body**.

```java
@Cacheable(cacheNames = "books", key = "#p0")
public String findTitle(String isbn) {
    System.out.println("BODY EXECUTED");
    return repository.findTitle(isbn);
}
```

*This is an illustrative snippet, `repository` is not declared; a complete runnable example is in section 4.*

When the `books` cache already holds an entry for `isbn = "B-1"`, calling `findTitle("B-1")` can immediately return the stored title string. In that case, `System.out.println("BODY EXECUTED")` is **not printed**, `repository.findTitle(isbn)` is **not called**, and any `if` branches, loops, or operations inside the method body **do not execute**.

Distinctions to keep in mind:

- **Not executing the method body** does not mean "doing nothing": the caller still makes the invocation, and Spring still runs the interceptor, locates the cache, builds/computes the key, and looks up the entry.
- **Not executing the method body** does not mean the source data has been re-checked. The cache entry may still contain stale data.
- **Not executing the method body** does not mean all other interceptors are skipped; whether other advice runs depends on configuration and advice ordering. The conclusion here applies specifically to **the target method body protected by `@Cacheable`**.
- If the lookup **misses** or caching is not applied, the real method runs normally.

Caching is appropriate when a call's result is reusable and re-running the method is costly: database queries, computations, or external service calls. `@Cacheable` is different from "logging and continuing to call the function"; on a hit, it **replaces the execution of the call's result**.

## 2. Two Execution Paths: Cache Hit and Cache Miss

With a simple configuration:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public String findTitle(String isbn) {
    return expensiveLookup(isbn);
}
```

Spring operates along the standard synchronous flow:

```text
Caller -> Spring-managed bean proxy -> CacheInterceptor
                                        |
                                        v
                             cacheName = "books"
                             key = isbn (via #p0)
                                        |
                                        v
                                cache lookup
                                /          \
                             HIT            MISS
                              |               |
                    get cachedValue      invoke findTitle(...)
                              |               |
                              |          run expensiveLookup
                              |               |
                              |          receive result (if successful)
                              |               |
                              |          store in cache if eligible
                              |               |
                              v               v
                        return result     return result
```

Example over time, assuming the cache starts empty:

| Time | Call | Cache at key | Method body runs? | Returned value |
| --- | --- | --- | --- | --- |
| T1 | `findTitle("B-1")` | Miss | Yes: queries data, produces `"Java in Action"` | `"Java in Action"` |
| T2 | `findTitle("B-1")` | Hit | No | `"Java in Action"` from cache |
| T3 | `findTitle("B-2")` | Miss | Yes: processes a different ISBN | B-2's own value |
| T4 | `findTitle("B-1")` | Hit | No | `"Java in Action"` from cache |
| T5 | Evict key `"B-1"`, then call again | Miss | Yes | Fresh value read from source |

**The key determines whether a result can be reused.** In the example, `#p0` points to the first argument (the ISBN). The cache name `books` identifies the storage space. Querying the cache with `("books", "B-1")` is a different lookup from `("books", "B-2")`.

If `key` is not specified, Spring uses the default strategy based on arguments; in this single-`String`-argument example, the key is also the ISBN. However, designing keys explicitly is especially useful when the result also depends on locale, tenant, filters, or data version. Merely having the same method name is not enough to conclude two calls share the same key.

## 3. Why Can a Result Be Returned Without Calling the Method?

`@Cacheable` is Spring's **cache abstraction**. The annotation itself only declares behavior; actual execution is coordinated by Spring through cache advice, `CacheManager`, and the concrete `Cache`:

1. **`@EnableCaching`** (or equivalent configuration) enables cache annotation processing.
2. **A Spring bean proxy** receives calls from other beans and routes them to the cache interceptor.
3. **`CacheManager`** provides the cache with the requested name, e.g., `books`.
4. **The key generator or SpEL expression** creates the key, e.g., `#p0`.
5. **The cache provider** returns the lookup status. An entry may already exist from a prior call, or may have been removed/expired depending on the provider.
6. On a hit, the interceptor **returns the cached value** to the caller; on a miss, it **invokes the target method**, and may then store the result.

Therefore, the value returned from cache is **not the result of a fresh background execution**. It is a result stored at an earlier time (and may have been serialized/deserialized or transformed by the provider). With a local cache, the object sitting in memory can often be retrieved directly; with a distributed cache, storage representation and sharing semantics depend on the backend. Do not assume that a cache hit always returns the exact same object reference.

## 4. Runnable Example with Java 17+ and Spring Boot: Seeing the Method Body Skipped

This example uses **Spring Boot 3.3.5**, **Java 17+**, Maven, and `ConcurrentMapCacheManager` to demonstrate single-process in-memory lookups. The program prints a `BODY -> ...` line **every time the method body actually runs**, making it possible to verify the exact timing of hits and misses. Finally, the program evicts a key to demonstrate that the next call must re-run the method body.

Structure:

```text
cache-hit-demo/
├── pom.xml
└── src/main/java/example/cachedemo/
    ├── CacheHitDemoApplication.java
    └── BookService.java
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
    <artifactId>cache-hit-demo</artifactId>
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

**`src/main/java/example/cachedemo/BookService.java`**

```java
package example.cachedemo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findTitle(String isbn) {
        int loadNumber = loads.incrementAndGet();
        System.out.println("BODY -> isbn=" + isbn + ", load=" + loadNumber);
        return "Book[" + isbn + "]@load" + loadNumber;
    }
}
```

**`src/main/java/example/cachedemo/CacheHitDemoApplication.java`**

```java
package example.cachedemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheHitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheHitDemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    CommandLineRunner demo(BookService service, CacheManager cacheManager) {
        return args -> {
            System.out.println("CALL 1 -> " + service.findTitle("B-1"));
            System.out.println("CALL 2 -> " + service.findTitle("B-1"));
            System.out.println("CALL 3 -> " + service.findTitle("B-2"));

            Cache books = cacheManager.getCache("books");
            if (books == null) {
                throw new IllegalStateException("Missing cache: books");
            }
            books.evict("B-1");
            System.out.println("EVICT -> B-1");

            System.out.println("CALL 4 -> " + service.findTitle("B-1"));
        };
    }
}
```

In the `cache-hit-demo` directory, run:

```bash
mvn spring-boot:run
```

The lines printed by the example appear in the **exact order** below; Spring Boot also prints its own startup logs:

```text
BODY -> isbn=B-1, load=1
CALL 1 -> Book[B-1]@load1
CALL 2 -> Book[B-1]@load1
BODY -> isbn=B-2, load=2
CALL 3 -> Book[B-2]@load2
EVICT -> B-1
BODY -> isbn=B-1, load=3
CALL 4 -> Book[B-1]@load3
```

**Explaining the mechanism, not just the output:**

- **CALL 1**: key `"B-1"` does not exist yet; Spring calls `findTitle`, prints `BODY ... load=1`, receives `Book[B-1]@load1`, and stores it in the `books` cache.
- **CALL 2**: still key `"B-1"`. Spring hits and returns the exact `Book[B-1]@load1`. **No new `BODY` line appears**, and the counter does not increment.
- **CALL 3**: key `"B-2"` does not exist yet; the method body runs a second time and produces `Book[B-2]@load2`.
- **EVICT**: removes only key `"B-1"` from `books`. The entry for `"B-2"` remains intact.
- **CALL 4**: `"B-1"` again, but its cache entry was just evicted; Spring misses and runs the method body a third time, returning `Book[B-1]@load3`.

`AtomicInteger` here is an instrumentation tool to observe **how many times the target method runs**, not a real book "version." The example intentionally appends the load count to the result to make reuse visible; a business method would normally return data from a repository or external source.

**Conditions for the output above to hold:** use the exact two Java files and `pom.xml`, invoke the `BookService` bean via dependency injection, keep `@EnableCaching` active, ensure `ConcurrentMapCacheManager` holds no prior data before running, and have no other competing operations. This example is run with Maven; there is no standalone `javac BookService.java` command because the class requires Spring dependencies.

## 5. What Does "Skipping the Method Body" Affect?

Suppose a real method performs these operations:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public BookView readBook(String isbn) {
    validateIsbn(isbn);             // A
    metric.increment();             // B
    BookView book = queryDb(isbn);  // C
    auditRead(isbn);                // D
    return book;                    // E
}
```

*This snippet illustrates behavior and is not a standalone program: `BookView` and the helper methods are not declared.*

On a **hit**:

- A, B, C, D, and E **do not run**. The interceptor returns the cached result; even the `return book` expression inside the method body is not evaluated again.
- Recording metrics/audits inside the method will miss all cache hits. If you want to count total invocations or enforce access control **per request**, place that responsibility at a layer that executes on every call, and verify advice ordering if using AOP.
- Side effects such as sending emails, decrementing inventory, updating state, or emitting events are skipped on a hit. **Do not place behavior that must execute every time inside a cacheable method**.
- If `validateIsbn` enforces security constraints, do not assume validation will execute on a hit. Perform authorization checks at a boundary appropriate for every request; keys and returned data must distinguish every context that affects results or authorization.

On a miss, all method logic runs as normal code; only afterward does Spring consider storing the result. This mechanism creates a core distinction between **a cache access call** and **a business execution call**.

## 6. Cases Where a Call Still Executes the Method Body

`@Cacheable` does not promise "each key runs only once during the application's lifetime." The method body can execute in the following cases:

| Situation | Outcome |
| --- | --- |
| Key is not yet in cache | **Miss** → runs method and considers caching |
| Key was evicted, cache was cleared, TTL expired, or provider no longer has the entry | **Miss** → runs method |
| Caching is disabled, `@EnableCaching` is missing, or call does not go through proxy | Annotation cannot intercept call → method runs |
| `@Cacheable`'s `condition` evaluates to `false` | Caching is not applied to this call → method runs |
| Cache miss, but `unless` evaluates to `true` after execution | Method runs, **does not store** the new value |
| Two near-simultaneous threads miss the same key | Both may run the method if no load coordination is configured |
| Keys differ even if arguments look similar | Each key has its own lookup; a new key typically misses first |

Example of `condition` and `unless`:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != 'temporary'",
    unless = "#result == null"
)
public String findTitle(String isbn) {
    return loadTitleFromDatabase(isbn);
}
```

*The snippet above requires defining `loadTitleFromDatabase` to run.*

- `condition` is checked before Spring decides to query the cache; when the key is `"temporary"`, the method runs **every time**, with no lookup/put through that `@Cacheable`.
- `unless` only gets evaluated after the method has been called and produced a result on a miss. If `#result == null`, Spring refuses to store that result.
- On a hit, the method does not run, so `unless` is not used to re-verify cached values; do not treat it as a step guaranteeing source data freshness.
- If the method throws an exception on a miss, Spring has no normal return value to cache under default `@Cacheable` behavior. The next call can continue to miss and execute again.

**About `null` values:** whether a provider supports caching null, and how it represents that value, depends on the implementation/configuration. Do not conclude "returning `null` equals a cache miss" without checking the specific cache's capabilities.

## 7. Which Calls Actually Pass Through the Cache Interceptor?

Default annotation caching uses proxies. The two situations below produce very different outcomes:

```text
Controller/Runner -> bean proxy -> @Cacheable findTitle(..)
                                  -> HIT: returns cached value, skips method body

BookService.someOtherMethod()
    -> this.findTitle(..)       -> direct internal call on target
                                  -> proxy does not intercept self-invocation
                                  -> method body still runs
```

Example:

```java
@Service
public class BookService {
    @Cacheable("books")
    public String findTitle(String isbn) {
        return expensiveLookup(isbn);
    }

    public String findFromInside(String isbn) {
        return this.findTitle(isbn); // bypasses default cache proxy
    }
}
```

*This is an example illustrating the self-invocation mechanism; `expensiveLookup` is not declared.*

Even when `books` already holds that ISBN, calling `findFromInside` and then `this.findTitle` still executes the body of `findTitle` in the default proxy configuration. Similarly, manually instantiating `new BookService()` will not attach the Spring cache interceptor.

A maintainable way to write this: have another Spring bean receive `BookService` via constructor injection and call through that bean; ensure caching is enabled. Avoid relying on `@Cacheable` on `private` or `final` methods when the proxy mechanism cannot intercept them. Weaving configurations other than proxies have different rules; the focus here is Spring cache annotations under default proxying.

## 8. Returning Stale Data Is a Consequence to Handle Proactively

Because a hit skips the method body, **the database may have changed while subsequent reads still return the old result**:

```text
10:00  Database: B-1 = "Old Title"
10:01  findTitle(B-1) MISS -> load "Old Title" -> cache[B-1] = "Old Title"
10:02  Database: B-1 = "New Title"
10:03  findTitle(B-1) HIT  -> returns "Old Title", does not hit database
10:04  evict(B-1)
10:05  findTitle(B-1) MISS -> load "New Title" -> cache[B-1] = "New Title"
```

To make the cache reflect updates, one or more techniques are commonly used:

- **`@CacheEvict`** on successful update operations to remove the exact entry, forcing the next read to reload the data.
- **`@CachePut`** if the update operation returns the exact result to be cached: a method annotated with `@CachePut` **always executes**, and then updates the cache.
- **Provider TTL / eviction** so entries expire automatically or are evicted based on capacity policies.
- **Cross-instance invalidation** if multiple applications share or replicate data.

Example annotation to clear the cache after a successful update:

```java
@CacheEvict(cacheNames = "books", key = "#p0")
public void renameBook(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
```

*This is an illustrative snippet; `repository` must be provided.* The eviction key `#p0` must match the read key `#p0` in `@Cacheable`, and target the same `books` cache. If reads use `"B-1"` while evictions use `"B-1:vi"`, the old entry will remain. With transactions, the timing of evict/put relative to commit must be carefully designed to avoid writing uncommitted or stale data back into the cache.

## 9. Cache Hits in a Multi-Request Environment

A subtle point to observe: **two requests arriving together while the cache is empty can both miss** before either finishes storing the result. In that case, even with the same key, the method body can run twice.

```text
Thread A: lookup B-1 -> MISS ---- load() ---- put(B-1)
Thread B: lookup B-1 -> MISS ---- load() ---- put(B-1)
```

`@Cacheable(sync = true)` asks the cache to coordinate value loading for the same key **if the provider supports it**:

```java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public String findTitle(String isbn) {
    return loadTitleFromDatabase(isbn);
}
```

*Illustrative snippet; `loadTitleFromDatabase` must be defined.*

Do not interpret `sync = true` as a system-wide distributed lock or a guarantee that "the method runs only once forever." Effectiveness depends on the cache provider, coordination scope, and entry lifecycle; `sync` also has annotation constraints, such as not being usable together with `unless` and allowing only one cache per synchronized operation. When a value is evicted or expires, a new load still has to occur.

For methods returning `CompletableFuture` or reactive types, recent Spring Framework versions have caching mechanisms adapted to asynchronous results; do not blindly extrapolate the synchronous timeline of the `String` example to those types without consulting the corresponding API/provider documentation.

## 10. Common Mistakes When Analyzing "Did the Method Run or Not?"

1. **Looking only at the return value.** Returning the same string twice does not prove a hit; the method may have actually run twice and returned the same data. Observe a counter inside the method, query logs, or cache metrics.
2. **Calling `this.method()` and concluding the annotation does not work.** In proxy mode, self-invocation bypasses the interceptor.
3. **Forgetting `@EnableCaching` / bean not managed by Spring.** The annotation alone does not add caching behavior to ordinary objects.
4. **Confusing "hit" with "loaded fresh data."** A hit prefers the stored value, so database updates do not automatically cause the method to re-run.
5. **Designing keys missing context.** If the result depends on locale, tenant, or user filter while the key is only an ID, the method may be skipped when a different result should be produced. This is a correctness bug and can affect data isolation.
6. **Placing mandatory business logic inside a cacheable method.** Business logging, side effects, and per-call permission checks can be skipped on a hit.
7. **Assuming all backends behave identically.** Spring only standardizes the abstraction; TTL, null storage, serialization, hit/miss statistics, cache sharing, and concurrent loading mechanisms still depend on the provider.
8. **Treating `@CachePut` as `@Cacheable`.** `@CachePut` executes the method and writes to the cache; only `@Cacheable` can skip the method on a hit.
9. **Sharing the same cache name and key for two methods with different meanings.** One method's value can be returned to the other, leading to wrong data or type errors.

## 11. Self-Check with Scenarios

**Scenario A:** Cache `books["B-1"]` holds `"Title A"`. Method `findTitle("B-1")` has `System.out.println("DB query")` in its body. Called through the bean proxy with caching enabled, matching key, and valid entry. What happens?

**Answer:** Returns `"Title A"` from the cache; does not print `"DB query"`. The interceptor supplied the result before invoking the target method.

**Scenario B:** The database changes `"Title A"` to `"Title B"`, but entry `"B-1"` has not been evicted. What happens on the next call?

**Answer:** It may still return `"Title A"`. A cache hit does not execute the method to check the database.

**Scenario C:** `findTitle("B-1")` returns `"Title A"` three times in a row. Is it guaranteed to have executed only once?

**Answer:** You cannot conclude that from the return value alone. You need to check whether caching is enabled, whether calls pass through the proxy, whether the key is consistent, whether the entry exists, and whether any eviction/expiry occurred.

**Scenario D:** Two threads concurrently request an uncached ISBN. Is the method guaranteed to run only once?

**Answer:** There is no general guarantee with regular `@Cacheable`. An appropriate coordination mechanism is required (e.g., `sync = true` when supported by the provider), and the scope of coordination must still be verified.

**Scenario E:** A method annotated with `@Cacheable` is called via `this.findTitle(...)` from another method in the same bean. Why does it still query the database?

**Answer:** Self-invocation on the target bypasses the cache proxy in the default mechanism; the cache interceptor has no opportunity to look up and return a cached result.

## References

- Spring Framework, *Declarative Annotation-based Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, *Proxying Mechanisms*, self-invocation section: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot, *Caching*: https://docs.spring.io/spring-boot/reference/io/caching.html