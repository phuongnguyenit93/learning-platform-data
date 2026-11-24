# `unless` and Vetoing Cache Storage After Receiving a Result in Spring Cache

## Learning Objectives

In Spring Cache, not every result returned by a method should be retained. After this lesson, you will know how to use `@Cacheable(unless = "...")` to **veto writing a newly computed result** to the cache; explain when `unless` is evaluated, use the `#result` SpEL variable safely with `null` and `Optional`, distinguish it from `condition`, and test hit/miss behavior. You will also recognize important limits: **`unless` does not delete old data, does not turn a result into an error, and must not be used as an authorization mechanism**.

The running example is a quote lookup service: valid results can be reused, pending results must be recomputed, and non-existent results can be actively excluded from caching.

## 1. What Problem Does `unless` Solve?

With a basic annotation:

~~~java
// Illustrative snippet on a Spring-managed service.
@Cacheable(cacheNames = "quotes", key = "#p0")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

When an invocation has a key that does not exist yet, Spring runs the method body and usually writes the result to the cache. Subsequent calls with the same key can return the stored result without running `loadQuote` again. However, there are results that **should not be reused**:

- Quotes with status `PENDING` or `TEMPORARY`, which are very likely to change right after the method returns.
- `null` or `Optional.empty()` results when business logic wants the next call to query the source one more time.
- Responses marked `cacheable = false` by data quality rules.
- Results missing required fields or belonging to a category outside the caching policy.

`unless` is the **write veto condition**. It accepts a Spring Expression Language (SpEL) expression returning a boolean:

~~~java
// Decide whether to store only after having the result.
@Cacheable(cacheNames = "quotes",
           key = "#p0",
           unless = "#result == null || !#result.cacheable()")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

If the `unless` expression evaluates to **`true`**, Spring **does not put the newly returned result** into the cache. If the expression is `false`, the result can be stored according to normal caching rules. In the example, both `null` results and results where `cacheable()` returns `false` are vetoed.

> Easy way to read it: `condition` asks **"should we use the cache for this call?"** before executing the method; `unless` asks **"should we refuse to keep the result we just got?"** after executing the method.

## 2. Execution Flow: `condition` First, `unless` After

~~~text
Call service.findQuote(code) via Spring proxy
                 |
                 v
       Check condition (if any)
          /                  \
       false                true
         |                    |
  Run method directly      Lookup cache by key
  (no lookup/put)            /             \
                           HIT            MISS
                            |               |
                      Return cached     Run method
                          value             |
                                            v
                                      Result obtained?
                                            |
                                            v
                                     Evaluate unless
                                     /           \
                                   true         false
                                     |            |
                              Do not write    Write cache
                                 cache            |
                                     \           /
                                     Return result
~~~

The steps above describe standard `@Cacheable` when `sync=false`, the method runs synchronously, and the provider supports the appropriate operations.

- **Cache hit:** the method does not run; there is no new result to pass through the `unless` veto step. The existing cached value is returned per cache hit behavior.
- **Cache miss, `unless=false`:** the method runs and Spring puts the result into the cache; subsequent calls have a chance to hit.
- **Cache miss, `unless=true`:** the method still runs and **the result is still returned to the caller**; only the cache write is blocked. The next call can continue to miss and run the method again.
- **Method throws an exception:** there is no successful return value to write under the normal flow; `unless` is not an exception catcher or converter.
- **`condition=false`:** the operation does not use the cache for that invocation, including lookup; `unless` should not be used to completely replace `condition`.

A common misconception is thinking `unless=true` will **return `null` or reject the response**. That is incorrect: it vetoes *storing the result*, not *returning the result*.

## 3. Decision Table for `condition` and `unless`

| `condition` | Cache hit? | Result from method | `unless` | Main behavior |
| --- | --- | --- | --- | --- |
| `false` | No lookup | Any value | No veto needed | Run method, skip cache for the call |
| `true` | Yes | Method does not run | No new result veto | Return cached entry |
| `true` | No | Valid `Quote` | `false` | Run method, write entry, return result |
| `true` | No | Temporary `Quote` | `true` | Run method, **do not write**, still return result |
| `true` | No | `null` | `#result == null` is `true` | Do not cache `null` result |
| `true` | No | Throws exception | No successful result | Exception propagates; no new result to cache |

If `condition` is not declared, treat cache usage as **allowed** by default. If `unless` is not declared, there is no extra post-execution veto rule.

`unless` does not manage the lifetime of an entry. Even if a returned result is valid now, it can become stale later; in that case, `@CacheEvict`, `@CachePut`, TTL, or an appropriate invalidation policy is required.

## 4. Writing `unless` Expressions with `#result`

`#result` is a variable in Spring Cache's SpEL context representing the **result value produced by the method**. In `@Cacheable`'s `unless`, it becomes available after the method executes successfully.

### Refusing to Cache `null`

~~~java
// Illustrative: method returns Product or null.
@Cacheable(cacheNames = "products",
           key = "#p0",
           unless = "#result == null")
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

This is the case of **not caching missing results** (*no negative caching*). If a product does not exist yet, every call queries the source again. Choose this policy when seeing newly created data quickly matters more than reducing miss queries.

Refusing to cache `null` is not always right: for rarely changing data with high traffic, short-lived negative caching can significantly reduce load. A Spring cache provider may or may not support representing null values depending on configuration. Decide based on business needs and provider behavior.

### Refusing Based on Result Properties

~~~java
// Illustrative: Product has accessor status().
@Cacheable(cacheNames = "products",
           key = "#p0",
           unless = "#result == null || #result.status() == 'DRAFT'")
public Product load(String id) {
    return repository.load(id);
}
~~~

The `||` expression stops evaluating when the left-hand side is already true. Therefore, if `#result == null`, Spring does not invoke `status()` on null. For a boolean property, you can write `unless = "!#result.cacheable()"` **only when you are certain the result is never null**; if null is possible, add a check first.

A Java record accessor method such as `result.cacheable()` is a method and can be called from SpEL. For a standard Java bean, you can use `#result.active` (conventional getter) or call `#result.isActive()`, as long as it is part of the object's real API and compatible with Spring Expression Language.

### Combining Inputs with the Result

~~~java
// Do not cache preview results, or results flagged as invalid.
@Cacheable(cacheNames = "reports",
           key = "#p0 + ':' + #p1",
           unless = "#p1 == 'preview' || #result == null || !#result.valid()")
public Report load(String reportId, String mode) {
    return generateReport(reportId, mode);
}
~~~

`#p0` is the first argument and `#p1` is the second; this approach does not depend on parameter name metadata at compile time. `#root.args[0]` also accesses the first argument; `#root.methodName`, `#root.targetClass`, and `#root.caches` provide invocation metadata. String concatenation with `:` is illustrative only; if arguments can contain `:`, unambiguous encoding or structured keys are needed.

When a veto criterion **depends solely on inputs** and can be decided before computing the result, you should usually use `condition` to avoid unnecessary cache lookups. When the criterion needs the state of the newly computed value, `unless` plays its own role.

## 5. Runnable Example: Valid Results Cached, Temporary Results Vetoed

This sample project uses **Java 17+, Spring Boot 3.3.5, Maven**, and `ConcurrentMapCacheManager` so you can observe how many times the method actually runs. There are four cases: `OK` is cached, `PENDING` returns without caching, `MISSING` returns `null` without caching, and `BYPASS` is excluded from caching from the start by `condition`.

Directory structure:

~~~text
unless-demo/
├── pom.xml
└── src/main/java/example/unlessdemo/
    ├── DemoApplication.java
    └── QuoteService.java
~~~

**`pom.xml`**:

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
    <artifactId>unless-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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
~~~

**`src/main/java/example/unlessdemo/DemoApplication.java`**:

~~~java
package example.unlessdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("quotes");
    }

    @Bean
    CommandLineRunner demo(QuoteService quotes) {
        return args -> {
            print(quotes.find("OK"));
            print(quotes.find("OK"));

            print(quotes.find("PENDING"));
            print(quotes.find("PENDING"));

            print(quotes.find("MISSING"));
            print(quotes.find("MISSING"));

            print(quotes.find("BYPASS"));
            print(quotes.find("BYPASS"));
        };
    }

    private static void print(QuoteService.Quote quote) {
        if (quote == null) {
            System.out.println("null");
        } else {
            System.out.println(quote.code() + " -> " + quote.payload()
                    + ", cacheable=" + quote.cacheable());
        }
    }
}
~~~

**`src/main/java/example/unlessdemo/QuoteService.java`**:

~~~java
package example.unlessdemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final AtomicInteger loads = new AtomicInteger();

    public record Quote(String code, String payload, boolean cacheable) {}

    @Cacheable(
            cacheNames = "quotes",
            key = "#p0",
            condition = "#p0 != 'BYPASS'",
            unless = "#result == null || !#result.cacheable()"
    )
    public Quote find(String code) {
        int attempt = loads.incrementAndGet();

        if ("MISSING".equals(code)) {
            return null;
        }

        boolean eligible = !"PENDING".equals(code);
        return new Quote(code, "load#" + attempt, eligible);
    }
}
~~~

Run in the `unless-demo` directory (with JDK 17+ and Maven installed):

~~~bash
mvn -q spring-boot:run
~~~

The lines **explicitly printed by the application from `CommandLineRunner`** will be (additional Spring logs may appear):

~~~text
OK -> load#1, cacheable=true
OK -> load#1, cacheable=true
PENDING -> load#2, cacheable=false
PENDING -> load#3, cacheable=false
null
null
BYPASS -> load#6, cacheable=true
BYPASS -> load#7, cacheable=true
~~~

How to read the output:

1. `OK` misses on the first call, the method runs (`load#1`); `unless` is `false` so the cache is written. The second call hits, still `load#1`.
2. `PENDING` has `cacheable=false`; `unless` is `true` so nothing is written. The second call must run the method again and increments from `load#2` to `load#3`.
3. `MISSING` returns `null` both times. The `#result == null` clause causes each call to be vetoed from writing; the method ran for the 4th and 5th times, even though the output only prints `null`.
4. `BYPASS` has `condition=false`, so Spring skips the cache from the start, producing `load#6` and `load#7` on the two calls. Even though the object has `cacheable=true`, `condition` already decided not to participate in caching.

`ConcurrentMapCacheManager("quotes")` creates a static in-memory cache region in the JVM, without built-in TTL like dedicated providers. `AtomicInteger` is only for counting executions and does not participate in key calculation. The application calls through a Spring bean: if `this.find("OK")` were called **from inside `QuoteService` itself** in default proxy mode, the cache interceptor could be bypassed.

### Proving the Cache Only Contains Accepted Entries

To observe directly, you can add the following lines **after the eight calls** inside `CommandLineRunner` (assuming you add a `CacheManager cacheManager` parameter to the bean signature):

~~~java
// Additional snippet inside the existing demo with cacheManager; not a standalone file.
var cache = cacheManager.getCache("quotes");
System.out.println("OK cached: " + (cache.get("OK") != null));
System.out.println("PENDING cached: " + (cache.get("PENDING") != null));
System.out.println("MISSING cached: " + (cache.get("MISSING") != null));
System.out.println("BYPASS cached: " + (cache.get("BYPASS") != null));
~~~

Expected output of the **four additional check lines**:

~~~text
OK cached: true
PENDING cached: false
MISSING cached: false
BYPASS cached: false
~~~

In a real application, tests should inspect cache entries by both cache name and key, as well as verify source read counts; simply logging a value string does not prove the cache was actually written.

## 6. `Optional<T>` and `#result`: A Subtle Detail Easy to Confuse

Spring Cache supports `Optional<T>` return types. In post-processing expressions like `unless`, **`#result` refers to the object inside `Optional`**, not the `Optional` wrapper itself:

- `Optional.of(book)` → `#result` points to `book`.
- `Optional.empty()` → `#result` is `null`.
- If not vetoed, Spring may store the inner value or a null representation depending on provider capability; on subsequent calls, Spring reconstructs the corresponding wrapper.

Example:

~~~java
// Illustrative snippet on a service; repository is not declared in this snippet.
@Cacheable(cacheNames = "books",
           key = "#p0",
           unless = "#result == null || #result.hardback()")
public Optional<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Suppose `Book` has a method `boolean hardback()`: hardback books or not-found results will not be cached; paperback books are allowed. **Do not write `#result.isEmpty()` here** intending to check for `Optional.empty()`, because `#result` is not an `Optional` object.

Spring documentation also gives examples of null-safe syntax `#result?.hardback`. You can use an explicit check `#result == null || ...` when you want a readable boolean expression, especially if you want to veto empty results. If an expression accesses a property on `null` without protection, you may encounter a SpEL evaluation error.

`Optional.empty()` does not always have to be refused from caching: there are queries that fail very frequently, so caching absence with a short TTL reduces load. That policy is called **negative caching**; if you want to apply it, do not place an `unless` expression that unconditionally excludes `null`.

## 7. How Does `unless` Differ from Checking `condition`?

Placing the same rule in the two attributes can lead to different execution behavior.

~~~java
// Only use the cache if input is valid: checked before the method.
@Cacheable(cacheNames = "searches",
           key = "#p0",
           condition = "#p0.length() <= 16")
public SearchResult search(String query) {
    return performSearch(query);
}
~~~

`condition` sees the input and can avoid lookup/put entirely when the input is long. If you need to inspect the result, use `unless`:

~~~java
// Need the computed result to know whether it is suitable for caching.
@Cacheable(cacheNames = "searches",
           key = "#p0",
           unless = "#result == null || #result.truncated()")
public SearchResult search(String query) {
    return performSearch(query);
}
~~~

In both snippets, `SearchResult` and `performSearch` are illustrative application types/functions, **not standalone runnable examples**.

| Criterion | `condition` | `unless` |
| --- | --- | --- |
| Timing | Before accessing/writing cache for the call | After the method returns a result to decide on writing |
| Meaning when expression is `true` | **Allow** caching | **Veto** caching |
| Uses `@Cacheable`'s `#result` | No | Yes |
| When expression is `false` | Skip cache, invoke method | May write result to cache |
| Previous cache hit | Condition can block cache usage immediately | Unless does not re-check a new result because method does not run |
| Typical use case | Filtering by parameters, invocation context | Filtering by status, quality, null, newly computed data |

Because the two conditions have opposite boolean meanings, mistaking `condition="#result..."` or `unless="#p0..."` can cause code to behave unexpectedly. `@Cacheable`'s `condition` **cannot rely on the new result**, because at evaluation time the method has not run yet.

## 8. Does `unless` Modify or Delete Values Already in the Cache?

**No.** `unless` only decides whether to **write a new value** into the cache on a miss. If the key already has an entry, Spring can return that entry immediately without re-executing the method or re-checking the result value with `unless`.

Business scenario example:

~~~text
T0: read("Q1") -> APPROVED, matches rule and gets cached.
T1: source changes "Q1" to PENDING.
T2: read("Q1") -> can still return APPROVED from a cache hit.
~~~

`unless="#result.status() == 'PENDING'"` **cannot solve T2**, because the method does not run again to produce `PENDING`. An **invalidation** mechanism is needed when the source changes:

~~~java
// Illustrative snippet; updateQuote(...) updates source data.
@CacheEvict(cacheNames = "quotes", key = "#p0")
public void updateQuoteStatus(String code, String status) {
    repository.updateStatus(code, status);
}
~~~

If you want to update the cache directly instead of evicting, use `@CachePut` according to your data policy; ensure the result and key match. A `@CachePut` method still runs to compute a new result, unlike `@Cacheable` which may skip the method. Avoid placing both `@CachePut` and `@Cacheable` on the same method in typical cases.

### Note on Sensitive Data

`unless` is **not** an access-control check. If a sensitive result was previously cached for a user and permissions are later revoked, `unless` does not guarantee that old cache hits are blocked. Permission checks must run somewhere guaranteed to execute on every request, alongside proper cache key design and invalidation/TTL. Do not use `unless` to treat unauthorized data as "safe".

## 9. Conditions Unsuitable for `unless`

Do not overuse `unless` for every kind of check:

1. **Disallowed inputs:** if you already know from the input that the call should not be cached, consider `condition`; if the input violates business rules, return an error from validation/authorization rather than just vetoing the cache.
2. **System errors or exceptions:** by default, if a method throws an error, there is no return value to cache. `unless` does not catch exceptions; use separate exception handling if you want to convert errors into business results.
3. **TTL rules:** `unless` does not set "cache this entry for only 10 seconds." TTL belongs to provider/configuration, or requires an explicit expiration strategy.
4. **Rapidly changing results:** `unless` can avoid storing temporary states, but valid cached states still need invalidation when source data changes.
5. **Side effects in SpEL:** do not call DBs, HTTP endpoints, mutate state, or run heavy functions just to decide whether to cache. Expressions should be fast, deterministic, and side-effect-free.
6. **Inputs containing secrets:** avoid putting access tokens, passwords, or sensitive data into keys/logs to build expressions; an `unless` expression does not hide data in physical keys.
7. **Per-key synchronization expectations:** `@Cacheable(sync=true)` does not support `unless`. You cannot combine both attributes to lock computation and veto the result that way.

### Why Can't `sync=true` Be Combined with `unless`?

`sync=true` is a hint for the provider to synchronize computation of the same key when multiple threads miss simultaneously, typically relying on an atomic load operation of the cache. Meanwhile, `unless` needs the finished result before deciding **not to write**. The `@Cacheable` API explicitly specifies that `unless` is not supported in synchronized caching mode.

~~~java
// Anti-pattern: invalid configuration for @Cacheable.
@Cacheable(cacheNames = "quotes",
           sync = true,
           unless = "#result == null")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

If the goal is to limit concurrent threads hitting the source while avoiding caching temporary results, design a single-flight/locking mechanism in the service layer or use an appropriate provider loader/refresh mechanism, and test it separately. Only use `@Cacheable(sync=true)` when not using `unless` and when the provider supports the expected semantics.

## 10. Asynchronous and Reactive Results

Since Spring Framework 6.1, the cache abstraction provides adaptive support for `CompletableFuture` and common reactive types: the completed value is what gets stored; the provider must support the corresponding asynchronous lookup mechanism.

~~~java
// Illustrative: method returning CompletableFuture.
@Cacheable(cacheNames = "quotes",
           key = "#p0",
           unless = "#result == null")
public CompletableFuture<Quote> asyncQuote(String code) {
    return fetchAsync(code);
}
~~~

This snippet illustrates syntax, not a standalone Java file; `fetchAsync` is defined by the application. With asynchronous processing, the time a result becomes available and is written to cache may differ from when the method returns the `CompletableFuture`. Do not assume `#result` is always the `CompletableFuture` object merely because of the Java method's return type: Spring has a mechanism to unwrap supported value types. Test post-processing SpEL and caching on the **actual Spring/provider version**.

Complex reactive chains can involve backpressure, multi-element streams, and context transformations. Annotation caching fits computed results with clear semantics; do not assume you can cache an arbitrary infinite stream or publisher object as-is. With `Flux`, Spring can collect values into a list for caching. Specialized interactions require a cache strategy designed for the pipeline.

## 11. Testing `unless` Properly

Use mocks/repository stubs or counters like in the example to verify the **difference between the returned result and the stored result**. A basic test suite should cover:

| Test case | Invocation | Expectation |
| --- | --- | --- |
| Valid result | `find("OK")` twice | Method runs once; second call hits |
| `cacheable=false` result | `find("PENDING")` twice | Method runs twice; both still return `Quote` |
| `null` result | `find("MISSING")` twice | Method runs twice; no `MISSING` entry exists |
| `condition=false` | `find("BYPASS")` twice | Cache bypassed; method runs twice |
| Wrong key/cache name | Same input but different region/key | Do not conclude `unless` is broken; check keys first |
| Pre-existing old value | Cache holds `OK`, source changes status | Can hit stale entry; test eviction |
| Multiple threads miss together | Same key, `sync=false` | Multiple computations may occur; test on actual provider |
| Returns `Optional.empty()` | Expression `#result == null` | Empty result is not cached |
| Proxy invocation | Service called from another bean | Cache advice activates |
| Self-invocation | `this.find(...)` in the same object | May bypass the default proxy |

In real integration tests, retrieve the `Cache` via `CacheManager.getCache("quotes")` and inspect `get(key)`: `null` from `Cache.get(key)` indicates no entry, whereas a `Cache.ValueWrapper` whose `get()` returns `null` can indicate **a cached entry with a null value**. Distinguishing these two cases is important when writing negative caching tests.

You can also add tests verifying SpEL expressions with `null` to prevent `EL1007E` / property-access-on-null errors. You should also test boundary conditions such as empty strings, new states, and cache names configured with different serializers.

## 12. Common Pitfalls

| Symptom | Misconception or cause | How to fix |
| --- | --- | --- |
| Result is still returned even when `unless=true` | Thinking `unless` blocks the response | `unless` only blocks **cache write**, the result is still returned |
| No change seen after adding/changing `unless` | Old key is already in cache | Evict or clear entries per plan; test from a clean cache |
| `#result.property` throws an error | Result can be null or lacks the getter/accessor | Check `#result == null` first; confirm accessor name |
| `Optional.empty()` not blocked as expected | Used `#result.isEmpty()` thinking result is Optional | Use `#result == null` for empty |
| `condition` and `unless` behave differently | Confused timing and boolean meaning | `condition=true` enables cache; `unless=true` vetoes put |
| Always queries the source again | `unless` expression is always true, or `condition` always false | Log state safely, test method execution count |
| `unless` does not run on self-invocation | Method called from same bean bypasses cache proxy | Call via another Spring-managed bean or consider AspectJ |
| Configuration error with `sync=true` | Sync mode does not support result veto | Do not combine `sync=true` with `unless` |
| Cached data becomes stale | No invalidation when source data changes | Use `@CacheEvict`, `@CachePut`, TTL, or a version policy |
| Authorization checks skipped | Relied on `unless` without checking authorization | Enforce permission checks on every request, scope keys properly |

For production, keep expressions short and easy to test. If the policy is complex enough to require DB queries, payload transformations, or multiple service dependencies, consider computing a `cacheable` flag in the business layer and checking that flag with `unless`, while ensuring no data leaks when an existing entry hits.

## 13. Self-Check Exercises

**Exercise 1.** `@Cacheable(unless="#result == null")` returns `null` on the first call. Does the next call with the same key need to run the method?  
**Answer:** Yes, provided there was no prior entry and it operates under normal `@Cacheable` behavior. `unless` vetoed storing the `null` result.

**Exercise 2.** Is `unless="#result.status() == 'DRAFT'"` safe if the method can return `null`?  
**Answer:** No. Check for null first, for example `#result == null || #result.status() == 'DRAFT'`; or choose valid null-safe syntax appropriate for the result type.

**Exercise 3.** A quote `"Q1"` was cached while in status `READY`. Later the DB changes to `DRAFT`. Why doesn't `unless` make the next read see `DRAFT`?  
**Answer:** The read can hit the cached `READY` version and the method does not run. `unless` does not re-evaluate old values; eviction/TTL/versioning is needed per business rules.

**Exercise 4.** When do you use `condition="#p0.length() <= 16"` vs. `unless="#result.truncated()"`?  
**Answer:** Conditions that depend on arguments and can be known **before running** use `condition`; conditions that depend on the newly produced result use `unless`.

**Exercise 5.** Can you put `@Cacheable(sync=true, unless="#result == null")` so only one thread computes the data and null is not stored?  
**Answer:** No, `sync=true` does not support `unless`. You need a different concurrency and veto strategy or to drop one of the two requirements.

## Official References

- Spring Framework – Declarative Annotation-based Caching, sections *Conditional Caching*, *Available Caching SpEL Evaluation Context*, and *Synchronized Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – `@Cacheable` Javadoc (Spring 6.2), contract of `condition`, `unless`, `sync`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot – Caching providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Takeaway:** `unless` is a **veto rule for storing a new result after the method completes**. `true` means do not cache, yet still return the result. Use `#result` with `null` checks, distinguish it from `condition`, and always plan invalidation for previously cached data.