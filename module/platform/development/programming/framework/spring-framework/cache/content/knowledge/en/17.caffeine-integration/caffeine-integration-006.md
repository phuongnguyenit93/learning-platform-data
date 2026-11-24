# Null Policy When Using the Spring Adapter with Caffeine

## 1. The Problem: Caffeine Rejects Null, Yet Spring Cache Can Support It

Caffeine is a high-performance Java caching library. Native Caffeine caches **do not allow storing null values**. Calling the native API directly with a null value is rejected by Caffeine.

However, Spring applications rarely interact with the native cache directly. They use the `org.springframework.cache.caffeine.CaffeineCache` adapter through `CaffeineCacheManager`. This adapter can convert an application's null value into an **internal placeholder object (sentinel/holder)** before storing it in Caffeine, then convert it back to null when reading through the Spring Cache API.

Therefore, two policy layers must be distinguished:

- **Native Caffeine:** stores only non-null values.
- **Spring Caffeine adapter:** can accept null on the Spring API and store a substitute holder if configured to allow it.

In Spring Framework 6.1, `CaffeineCacheManager` **allows null by default** (`allowNullValues = true`), even though native Caffeine does not support null. This can be disabled with `setAllowNullValues(false)`. When disabled, the adapter rejects a write with a null value instead of converting it to a holder.

Key point: `allowNullValues` is a **Spring adapter** policy and does not alter the rules of the Caffeine library itself.

## 2. Two Modes of `CaffeineCacheManager`

### 2.1. Default Mode: Allowing Null

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    // Default allowNullValues = true.
    return manager;
}
```

With this configuration, when a `@Cacheable` method returns null:

1. The Spring cache interceptor receives the null result from the method.
2. `CaffeineCache` checks the `allowNullValues` policy.
3. Because null is allowed, the adapter converts null into an internal holder.
4. The holder is stored in the native Caffeine cache as a non-null value.
5. When read through `Cache.get(key)`, the adapter converts the holder back to the business null value.

Native Caffeine still never stores an actual null value. It stores the holder created by Spring.

### 2.2. Disabling Null: `setAllowNullValues(false)`

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}
```

When the null policy is disabled:

- `CaffeineCache` does not convert null into a holder.
- Calling `Cache.put(key, null)` is rejected by the adapter with `IllegalArgumentException`.
- If a `@Cacheable` method returns null and Spring attempts to write that result to the cache, the call can throw an exception from the put operation.
- When `unless = "#result == null"` is used, Spring skips the put operation, so the method can return null normally without a cache error.

This option is useful when the application wants **not to cache empty results**, or when using Caffeine async mode and wanting to avoid wrapping null values in futures.

### 2.3. Comparison Table

| Behavior | `allowNullValues=true` | `allowNullValues=false` |
| --- | --- | --- |
| Native Caffeine stores null directly | No | No |
| Spring adapter accepts null on put | Yes | No |
| Handling mechanism | Converts null to internal holder | Throws error when actually asked to put null |
| `@Cacheable` returns null, no `unless` | Can store a negative entry | Typically fails on put operation |
| `@Cacheable(unless="#result == null")` | Does not store null | Does not store null; no put-null error |
| `Cache.get(key)` after a cached null | Returns `ValueWrapper`, `wrapper.get() == null` | No entry if put was vetoed |
| Native Caffeine holds a value at key | Holds non-null holder | No entry |

**Do not confuse "allowing null" with "must always cache null".** `allowNullValues=true` merely gives the adapter the ability to represent null; annotations, `unless` conditions, and execution flow still decide whether a result gets put into the cache.

## 3. Internal Holder and Reading Properly

### 3.1. Why Is a Holder Needed?

Both `ConcurrentHashMap` and native Caffeine forbid storing null as an ordinary value. Spring uses an internal holder to distinguish:

- the cache does not contain the key;
- the cache contains the key and its business value is null.

Visualization:

```text
Spring Cache API
    |
    | cache.put("B42", null)
    v
CaffeineCache adapter
    |
    | allowNullValues = true
    | null -> internal holder
    v
Native Caffeine
    |
    '-- "B42" -> InternalNullHolder

When reading through Spring Cache:
    InternalNullHolder -> null
```

The holder's name and structure are internal Spring details. Do not cast to it, store it in domain objects, or depend on that internal class in business code.

### 3.2. Distinguishing a Cache Miss from a Cached-Null Hit

Use `Cache.ValueWrapper`:

```java
Cache.ValueWrapper wrapper = cache.get("B42");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_NULL");
} else {
    System.out.println("HIT_VALUE");
}
```

Three cases:

| `cache.get(key)` Result | Meaning |
| --- | --- |
| `null` | No mapping for the key (cache miss) |
| `ValueWrapper` exists, `wrapper.get() == null` | Mapping exists; business value is null (negative cache hit) |
| `ValueWrapper` exists, `wrapper.get() != null` | Mapping exists with normal data |

If you only call `cache.get(key, Book.class)` and receive null, the caller cannot distinguish a cache miss from an entry containing null. When the distinction matters, use `ValueWrapper`.

### 3.3. Native Cache May Contain a Holder Even When Spring Returns Null

If you need to inspect the concrete Caffeine implementation:

```java
CaffeineCache caffeineCache = (CaffeineCache) cache;

Object nativeValue =
        caffeineCache.getNativeCache().getIfPresent("B42");

System.out.println(nativeValue != null);
```

*This snippet is only suitable when `cache` is actually a `CaffeineCache` and allows nulls. It illustrates inspecting native storage, not how to read business data.*

When null is allowed and cached, native Caffeine can return a non-null holder. **Do not cast the native value to `Book`** and do not treat a non-null raw value as proof that business data exists.

When wrappers or decorators surround `CaffeineCache`, `cache instanceof CaffeineCache` may evaluate to false. Inspect the actual object returned by `CacheManager` before relying on adapter-specific APIs.

## 4. Null Policy in `@Cacheable`

### 4.1. Allowing Null and Caching Negative Results

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

*Illustrative snippet; `Book` and `repository` must be defined.*

If `CaffeineCacheManager` allows nulls, the first time a book is not found a holder representing null can be stored. Subsequent calls with the same key will hit and skip querying the repository.

Benefits:

- reduces load when the same non-existent ID is queried repeatedly;
- avoids repeating queries for negative IDs;
- can be helpful when not-found states are relatively stable.

In return, if the record is created after a negative lookup, the cache can continue returning stale null until the entry expires, is evicted, or is updated. This is **negative caching**, not auto-synchronizing data.

### 4.2. Skipping Null Caching with `unless`

`unless` is evaluated **after the method runs**, once the result is known:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

If the result is null, `unless` evaluates to true and Spring skips putting that value. The caller still receives null; the next call runs the method again because no negative entry exists.

This pairs well with a manager that disables nulls:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}
```

**Important point:** `unless` does not alter the return value. It only prevents the cache put operation. If the method returns null, the caller still gets null.

### 4.3. Do Not Use `condition` to Check the Result

`condition` is evaluated **before invoking the method**, so `#result` cannot be used to tell whether the method returned null.

```java
// WRONG timing: #result does not exist yet in condition.
@Cacheable(cacheNames = "books",
           condition = "#result == null")
public Book findBook(String id) {
    return repository.findById(id).orElse(null);
}
```

Use `unless` when the storage decision depends on the return value. Use `condition` when deciding whether to apply caching based on input arguments or metadata available before the call.

### 4.4. Methods Returning Optional

Spring Cache supports `Optional`:

- `Optional.of(book)` is unwrapped and the `Book` object is stored.
- `Optional.empty()` is treated as a null result at the cache layer.
- `#result` in an `unless` expression refers to the business object, not the `Optional` wrapper.

Example:

```java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Book> findOptional(String id) {
    return repository.findById(id);
}
```

If the repository returns `Optional.empty()`, Spring treats `#result` as null and vetoes the cache put. Do not write `#result.isEmpty()` assuming `#result` is always an Optional in cache SpEL; supported wrappers are unwrapped.

### 4.5. Exceptions Differ from Null

A method returning null is a normal completion. A method throwing an exception has no normal return value for `@Cacheable` to store. `unless` is not an exception handler and does not convert exceptions into null.

If you want to return a fallback, the method or an outer layer must actually return a normal value; the cache policy will then apply to that fallback unless vetoed by a condition.

## 5. Behavior When Null Is Disabled Without `unless`

This is a common configuration mistake:

```java
@Bean
CacheManager strictCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    return manager;
}

@Cacheable(cacheNames = "books",
           cacheManager = "strictCacheManager")
public Book find(String id) {
    return null;
}
```

When the method is called:

1. Cache lookup misses.
2. The method executes and returns null.
3. Spring attempts to put the result into the cache.
4. `CaffeineCache` rejects null because `allowNullValues=false`.
5. The adapter throws `IllegalArgumentException`.
6. The caller can receive an exception from the cache operation even though the method body completed and returned null.

Therefore, if the method contract allows "not found" and you disable null support, explicitly design how empty results are handled. For synchronous `@Cacheable`, `unless="#result == null"` is a common choice.

### 5.1. Do Not Catch All Exceptions Just to Simulate Null Skipping

Do not write a blanket cache error handler just to ignore all put errors. That can hide serialization failures, unavailable backends, bad keys, or misconfigurations. Explicitly identify the case to skip as **null results**, and veto it cleanly with `unless`.

If the cache provider fails due to network, timeouts, or operational errors, design `CacheErrorHandler` specifically for availability requirements; never conflate provider errors with null policy.

## 6. Configuring Caffeine According to Need

### 6.1. Controlled Null Allowance

```java
@Bean("nullableCacheManager")
CaffeineCacheManager nullableCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(true);
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
```

This configuration:

- allows the Spring adapter to represent null via a holder;
- bounds cache capacity via Caffeine configuration;
- sets expiration after write;
- still does not make native Caffeine accept null directly.

If using negative caching, choose a TTL matching the staleness tolerance of the business domain. You may need a shorter negative TTL than positive results, or separate negative/positive caches to configure them independently.

### 6.2. Rejecting Null

```java
@Bean("strictCacheManager")
CaffeineCacheManager strictCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAllowNullValues(false);
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
```

This configuration forces cacheable methods to avoid putting null, for instance using `unless`. It suits applications that do not want negative entries retained and want errors to surface immediately if code accidentally tries to store null.

### 6.3. Configure Before the Cache Is Used

Configure `allowNullValues` when creating the manager, before any cache is used in the application context. Avoid toggling null policy arbitrarily while the cache holds entries, as existing entries may have been stored under a different representation.

When registering custom native Caffeine caches via `registerCustomCache`, inspect the overloads and adapter settings applied during registration; do not assume a native cache automatically knows Spring's null policy.

## 7. Caffeine Async Mode in Spring Framework 6.1+

Spring Framework 6.1 added support for Caffeine `AsyncCache` via `CaffeineCacheManager.setAsyncCacheMode(true)`. This mode supports the `Cache.retrieve(...)` API and caching asynchronous results.

```java
@Bean
CaffeineCacheManager asyncCacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("books");
    manager.setAsyncCacheMode(true);
    manager.setAllowNullValues(false);
    return manager;
}
```

Spring documentation recommends **disabling null values in async cache mode**, even though nulls are still supported. The reason is that future handles provided by Caffeine can be used more directly, avoiding wrapping futures to represent nulls and simplifying asynchronous result semantics.

Points to distinguish:

- `setAsyncCacheMode(true)` does not automatically make every Java method asynchronous; it configures the native cache type created by the manager.
- `CompletableFuture`/reactive caching also depends on return types, Spring version, and provider.
- When using async mode, verify how cache misses, nulls, and errors are represented through `Cache.retrieve`; do not mechanically apply synchronous `ValueWrapper` assumptions to every future result.
- If the application does not need async caching, the default synchronous mode is simpler.

## 8. Runnable Java 17+ Example: Comparing Three Null Policies

This example uses Java 17+, Maven, Spring Boot 3.3.5, Spring Cache, and Caffeine. Three managers/cases are demonstrated:

1. `nullableManager`: allows null; the Spring adapter caches null using a holder.
2. `strictManager`: rejects null; a method without `unless` fails when putting null.
3. Same `strictManager`: a method with `unless` skips writing null; a method returning `Optional.empty()` also skips writing null.

### 8.1. Project Structure

```text
caffeine-null-policy/
├── pom.xml
└── src/main/java/example/caffeinenull/
    ├── CaffeineNullApplication.java
    └── BookService.java
```

### 8.2. `pom.xml` File

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
    <artifactId>caffeine-null-policy</artifactId>
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
```

Spring Boot parent manages compatible dependency versions; there is no need to pin the Caffeine version manually in this example.

### 8.3. `src/main/java/example/caffeinenull/BookService.java` File

```java
package example.caffeinenull;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final AtomicInteger nullableCalls = new AtomicInteger();
    private final AtomicInteger strictCalls = new AtomicInteger();
    private final AtomicInteger skipNullCalls = new AtomicInteger();
    private final AtomicInteger optionalCalls = new AtomicInteger();

    @Cacheable(
        cacheNames = "nullableBooks",
        cacheManager = "nullableManager",
        key = "#p0"
    )
    public Book findWithNullableAdapter(String id) {
        int n = nullableCalls.incrementAndGet();
        System.out.println("LOAD nullable #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "strictBooks",
        cacheManager = "strictManager",
        key = "#p0"
    )
    public Book findWithStrictAdapter(String id) {
        int n = strictCalls.incrementAndGet();
        System.out.println("LOAD strict #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "strictBooks",
        cacheManager = "strictManager",
        key = "#p0",
        unless = "#result == null"
    )
    public Book findWithoutCachingNull(String id) {
        int n = skipNullCalls.incrementAndGet();
        System.out.println("LOAD skip #" + n + " " + id);
        return null;
    }

    @Cacheable(
        cacheNames = "optionalBooks",
        cacheManager = "strictManager",
        key = "#p0",
        unless = "#result == null"
    )
    public Optional<Book> findOptional(String id) {
        int n = optionalCalls.incrementAndGet();
        System.out.println("LOAD optional #" + n + " " + id);
        return Optional.empty();
    }

    public int skipNullCalls() {
        return skipNullCalls.get();
    }

    public int optionalCalls() {
        return optionalCalls.get();
    }
}
```

### 8.4. `src/main/java/example/caffeinenull/CaffeineNullApplication.java` File

```java
package example.caffeinenull;

import java.time.Duration;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import com.github.benmanes.caffeine.cache.Caffeine;

@SpringBootApplication
@EnableCaching
public class CaffeineNullApplication {
    public static void main(String[] args) {
        SpringApplication.run(CaffeineNullApplication.class, args);
    }

    @Bean("nullableManager")
    CaffeineCacheManager nullableManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("nullableBooks");
        manager.setAllowNullValues(true);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }

    @Bean("strictManager")
    CaffeineCacheManager strictManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("strictBooks", "optionalBooks");
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5))
        );
        return manager;
    }

    @Bean
    CommandLineRunner demo(
        BookService service,
        @Qualifier("nullableManager") CacheManager nullableManager,
        @Qualifier("strictManager") CacheManager strictManager
    ) {
        return args -> {
            Cache nullable = Objects.requireNonNull(
                nullableManager.getCache("nullableBooks")
            );

            System.out.println(
                "NULLABLE1 => " +
                service.findWithNullableAdapter("MISSING")
            );
            System.out.println(
                "NULLABLE2 => " +
                service.findWithNullableAdapter("MISSING")
            );

            Cache.ValueWrapper wrapper = nullable.get("MISSING");
            System.out.println(
                "NULLABLE_HIT_NULL => " +
                (wrapper != null && wrapper.get() == null)
            );

            CaffeineCache nativeCache = (CaffeineCache) nullable;
            System.out.println(
                "NATIVE_HOLDER_PRESENT => " +
                (nativeCache.getNativeCache().getIfPresent("MISSING") != null)
            );

            Cache strict = Objects.requireNonNull(
                strictManager.getCache("strictBooks")
            );

            try {
                service.findWithStrictAdapter("STRICT_MISSING");
            } catch (IllegalArgumentException ex) {
                System.out.println(
                    "STRICT_ERROR => " + ex.getClass().getSimpleName()
                );
            }
            System.out.println(
                "STRICT_ENTRY_PRESENT => " +
                (strict.get("STRICT_MISSING") != null)
            );

            System.out.println(
                "SKIP1 => " + service.findWithoutCachingNull("SKIP_MISSING")
            );
            System.out.println(
                "SKIP2 => " + service.findWithoutCachingNull("SKIP_MISSING")
            );
            System.out.println("SKIP_CALLS => " + service.skipNullCalls());
            System.out.println(
                "SKIP_ENTRY_PRESENT => " +
                (strict.get("SKIP_MISSING") != null)
            );

            Cache optional = Objects.requireNonNull(
                strictManager.getCache("optionalBooks")
            );
            System.out.println(
                "OPTIONAL1 => " + service.findOptional("OPTIONAL_MISSING")
            );
            System.out.println(
                "OPTIONAL2 => " + service.findOptional("OPTIONAL_MISSING")
            );
            System.out.println(
                "OPTIONAL_CALLS => " + service.optionalCalls()
            );
            System.out.println(
                "OPTIONAL_ENTRY_PRESENT => " +
                (optional.get("OPTIONAL_MISSING") != null)
            );
        };
    }
}
```

### 8.5. Clean Up Imports Before Running

In `CaffeineNullApplication.java`, remove the following unused import:

```java
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
```

This import is unnecessary in the demo. The remaining imports are used for configuration, inspection, or dependency injection.

### 8.6. Run Command

In the `caffeine-null-policy` directory, requires JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Lines printed by the demo in the following order (skipping the Spring Boot banner and startup logs):

```text
LOAD nullable #1 MISSING
NULLABLE1 => null
NULLABLE2 => null
NULLABLE_HIT_NULL => true
NATIVE_HOLDER_PRESENT => true
LOAD strict #1 STRICT_MISSING
STRICT_ERROR => IllegalArgumentException
STRICT_ENTRY_PRESENT => false
LOAD skip #1 SKIP_MISSING
SKIP1 => null
LOAD skip #2 SKIP_MISSING
SKIP2 => null
SKIP_CALLS => 2
SKIP_ENTRY_PRESENT => false
LOAD optional #1 OPTIONAL_MISSING
OPTIONAL1 => Optional.empty
LOAD optional #2 OPTIONAL_MISSING
OPTIONAL2 => Optional.empty
OPTIONAL_CALLS => 2
OPTIONAL_ENTRY_PRESENT => false
```

### 8.7. Result Explanation

**Group 1 — Nullable adapter:**

- The first `findWithNullableAdapter("MISSING")` misses, runs the method, and returns null. The adapter stores a holder in native Caffeine.
- The second call hits the holder; the method does not re-run, so only one `LOAD nullable` line is printed.
- `NULLABLE_HIT_NULL=true` proves Spring's `ValueWrapper` exists while the business value is null.
- `NATIVE_HOLDER_PRESENT=true` proves native Caffeine holds a non-null value at that key. That is the adapter's holder, not a native null.

**Group 2 — Strict adapter:**

- `findWithStrictAdapter` runs and returns null.
- The cache interceptor attempts to put the result; the strict adapter rejects null and throws `IllegalArgumentException`.
- No entry exists at key `STRICT_MISSING`.

**Group 3 — Strict adapter combined with `unless`:**

- The method runs on both calls because `unless` vetoes putting null.
- No error occurs because the adapter never receives a put-null command.
- No entry exists at key `SKIP_MISSING`.

**Group 4 — `Optional.empty()`:**

- Spring unwraps Optional; `#result` represents the business value null.
- `unless="#result == null"` vetoes the put.
- The caller still receives `Optional.empty()`; both calls run the method and no entry is stored in `optionalBooks`.

The program uses a local Caffeine cache in a single JVM and calls sequentially so stdout is deterministic. The example does not test transactions, multiple nodes, or race conditions. The code and output have been reviewed along the execution path; to verify at runtime, run Maven with JDK 17+.

## 9. Common Mistakes

1. **Thinking native Caffeine stores null directly.** Native caches do not accept null; the Spring adapter uses a holder when configured to allow it.
2. **Assuming CaffeineCacheManager rejects null by default.** The Spring adapter's default is `allowNullValues=true`, even though native Caffeine does not support null.
3. **Disabling null support while forgetting `unless`.** Methods returning null can cause put operations to throw `IllegalArgumentException`.
4. **Confusing `unless` with `condition`.** `condition` runs before the method; `unless` runs after a result is produced.
5. **Thinking `unless=true` causes callers to receive an exception or different value.** Callers still receive the method's return value; only the cache put is skipped.
6. **Confusing a cache miss with a cached-null hit.** Use `Cache.ValueWrapper` to distinguish them; do not inspect only the unwrapped value.
7. **Reading the native cache and casting the holder to a domain object.** The native value may be an internal sentinel; use only the Spring abstraction in business logic.
8. **Using the raw Caffeine API to put null.** Native Caffeine rejects null; use the Spring adapter and an appropriate null policy.
9. **Treating `Optional.empty()` as a wrapper unrelated to null.** Spring unwraps supported Optionals during caching and in `#result`.
10. **Using `@Cacheable(sync=true, unless="#result == null")`.** Spring does not support combining `sync=true` with `unless` on the same operation; choose another concurrency mechanism if needed.
11. **Sharing one cache manager for caches needing different null policies.** `allowNullValues` is a manager-level setting; if two policies are needed, create separate managers/cache adapters or design separate caches with matching settings.
12. **Thinking disabling null support solves negative caching by itself.** It only rejects putting null; you must still decide whether methods return null, Optional.empty, or exceptions and pick the right policy.
13. **Overlooking async mode changes.** With Spring 6.1+ Caffeine async caches, documentation recommends disabling null to simplify future semantics.
14. **Using null as the sole business state.** For complex domains, an explicit result type (found/not-found/error) may be more maintainable; `unless` expressions should match that contract.
15. **Not testing on the actual provider.** A local cache allowing null does not prove Redis, JCache, or direct native Caffeine shares identical semantics.

## 10. How to Choose a Policy

| Requirement | Appropriate Config / Behavior |
| --- | --- |
| Want to remember not-found results to reduce load | Allow null on the adapter; set a short negative TTL and invalidate when data is created |
| Want every null lookup to re-query the source | `setAllowNullValues(false)` combined with `unless="#result == null"` |
| Want to forbid null across the entire manager | `setAllowNullValues(false)`; audit every method that might return null |
| Using `Optional.empty()` and avoiding negative caching | `unless="#result == null"` |
| Using Spring 6.1+ async Caffeine cache | Consider `setAllowNullValues(false)` per Spring's recommendation |
| Only need to check whether an entry exists | Use `Cache.get(key)` and `ValueWrapper`; do not read raw native holders |
| Need TTL or size policies | Configure Caffeine builder/manager; do not rely on null policy as a substitute |

A strict configuration is only safe once all operations have been audited. If a method can return null without `unless`, errors will only surface at runtime when a cache put executes.

## 11. Testing Checklist

- [ ] Cache miss with non-null result: method runs and result is cached.
- [ ] Cache hit with non-null result: method does not run again.
- [ ] Cached-null hit when `allowNullValues=true`: `ValueWrapper` exists and `wrapper.get()==null`.
- [ ] Native Caffeine contains a non-null holder after Spring caches null.
- [ ] `allowNullValues=false` and method returns null without `unless`: cache put is rejected.
- [ ] `allowNullValues=false` and `unless="#result == null"`: caller receives null, no entry stored, and no put error.
- [ ] Method returning `Optional.empty()`: verify `#result` is unwrapped and no entry is stored when `unless` is present.
- [ ] Method throwing an exception: distinguish from a method returning null.
- [ ] Verify the actual cache key, cache name, and manager used.
- [ ] If using async mode, test future/`retrieve` and null semantics separately.
- [ ] If using negative caching, test TTL, invalidation, and the case where a record is created after a miss.
- [ ] Run integration tests with the exact Spring and Caffeine versions used in the project.

## 12. Self-Check Questions

**Question 1.** Native Caffeine does not support null. Why can the Spring Caffeine adapter still cache null?

**Answer:** `CaffeineCache` can convert null into an internal holder when `allowNullValues=true`; native Caffeine stores the non-null holder, and the adapter unwraps it back to null on read.

**Question 2.** Does `CaffeineCacheManager` allow null by default?

**Answer:** Yes. In Spring Framework 6.1, `allowNullValues=true` is the default even though native Caffeine does not store null directly.

**Question 3.** What happens if a manager uses `setAllowNullValues(false)` and a `@Cacheable` method returns null without `unless`?

**Answer:** The cache interceptor attempts to put null; the adapter rejects it with `IllegalArgumentException`. Callers can receive an exception from the cache operation even though the method body returned null.

**Question 4.** Does using `unless="#result == null"` with a strict manager throw an error?

**Answer:** Not from putting null, because `unless` vetoes the put operation. Callers still receive null.

**Question 5.** Why can `Cache.get(key)` return a wrapper even when the inner value is null?

**Answer:** The wrapper indicates an entry exists. The business null value is stored via an internal holder so a hit-null can be distinguished from a miss.

**Question 6.** If a method returns `Optional.empty()`, what is `#result` inside `unless`?

**Answer:** Spring Cache unwraps supported Optionals; `#result` is null, not the Optional wrapper. Hence `unless="#result == null"` can veto caching empty results.

**Question 7.** Can `@Cacheable(sync=true, unless="#result == null")` be used?

**Answer:** No. Spring does not support combining `sync=true` and `unless` on the same operation.

**Question 8.** To cache negative results for 5 seconds while caching positive results for 5 minutes, is calling `setAllowNullValues(true)` alone enough?

**Answer:** No. That policy only allows representing null. Different TTLs for negative vs. positive entries require separate caches, provider policies, or an appropriate mechanism.

## Official References

- Spring Framework Javadoc — `CaffeineCacheManager`, default `allowNullValues=true` and `setAllowNullValues`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework Javadoc — `CaffeineCache`, adapter over native Caffeine and `allowNullValues` parameter: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework Javadoc — `AbstractValueAdaptingCache`, null/holder conversion: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/support/AbstractValueAdaptingCache.html
- Spring Framework Reference — Declarative Annotation-based Caching, `unless` and Optional: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `Cache` and `Cache.ValueWrapper`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/Cache.html
- Caffeine documentation — native cache API and null-value constraints: https://github.com/ben-manes/caffeine/wiki