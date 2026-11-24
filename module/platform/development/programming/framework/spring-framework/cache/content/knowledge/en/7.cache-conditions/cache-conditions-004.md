# Avoiding Caching `null` Results with the Right Expression in Spring Cache

## 1. Why Control Caching of `null`?

A data-reading method often returns `null` when a record is not found:

```java
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

If the cache stores `null` for key `"A100"`, a subsequent call can receive `null` directly from the cache without querying the data source. This is **negative caching**: caching a "not found" result. It helps when non-existent lookups repeat heavily, but can violate expectations when data is created shortly afterward.

Example sequence:

1. At 09:00, `findById("A100")` finds no record and returns `null`.
2. The cache may store the `null` value under key `"A100"`, if the provider/configuration allows it.
3. At 09:01, another operation creates record `A100` in the database.
4. At 09:02, `findById("A100")` can still return `null` from the cache until the entry is evicted, expires, or is updated.

To **avoid storing `null` results**, Spring Cache supports the `unless` attribute on `@Cacheable`. Core configuration:

```java
@Cacheable(cacheNames = "accounts", key = "#p0", unless = "#result == null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

With this configuration, whenever the method actually returns `null`, Spring skips putting that result into the cache. A subsequent call with the same key still hits the data source (if no prior cached entry exists). Once the source returns a non-`null` object, Spring stores the result.

**Lesson scope:** choosing a post-result veto condition, SpEL `#result`, distinguishing `unless` from `condition`, impact on `Optional`, provider null storage, entry lifecycle, and behavior testing.

## 2. How Does `unless = "#result == null"` Work?

### 2.1. The `@Cacheable` Contract

In standard caching, Spring handles an invocation to a proxy/interceptor-managed bean in this general sequence:

```text
Call service.findById("A100")
    |
    v
Compute cache key and check condition (if any)
    |
    v
Lookup cache by key
    |
    +-- HIT -----------------------> Return cached data
    |
    +-- MISS --> Run real method --> Receive result
                                         |
                                         v
                              Evaluate unless via SpEL
                                         |
                            +------------+------------+
                            |                         |
                        true: VETO               false: ALLOW
                            |                         |
                     Do not store result       Store result in cache
                            |                         |
                            +------------+------------+
                                         |
                                         v
                                   Return result
```

With `unless = "#result == null"`:

| Actual method return value | SpEL `#result == null` value | Does Spring put the new result into the cache? |
| --- | --- | --- |
| `null` | `true` | **No** |
| `new Account("A100", "Lan")` | `false` | Yes, if the cache operation is active and the provider writes successfully |
| `""` (empty string) | `false` | Yes, because an empty string is not `null` |
| `List.of()` (empty list) | `false` | Yes, because an empty list is not `null` |
| `Optional.empty()` (Spring-supported Optional type) | `true` based on **unwrapped inner value** | No |

`unless` is a **SpEL expression returning a boolean**. When the expression returns `true`, Spring **vetoes** adding the result of the invocation that just ran to the cache. The name `unless` can be confusing: `unless = "#result == null"` means "cache the result, **unless** the result is null."

### 2.2. What Is `#result`?

`#result` is a context variable provided by Spring **after the method has returned a result**. Example:

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public Account findById(String id) {
    // An actual call may return Account or null.
    return repository.findByIdOrNull(id);
}
```

- `#p0` selects the first parameter (`id` here) as the key, independent of parameter names during Java compilation.
- `#result` references the **return value** of the method (already unwrapped by Spring for supported wrapper types).
- The `== null` operator checks directly for null, not the string literal `"null"`.
- The outer double quotes belong to Java annotation syntax; the content inside is SpEL.

`#result` does not exist at every expression evaluation point. For `@Cacheable`, use it in `unless`, **not** in `condition` or `key`, because both of those must be evaluated before the method runs to decide whether to look up the cache and under which key.

## 3. Distinguishing `condition` and `unless`

This is the most common point of confusion when trying to exclude `null` data.

| Criterion | `condition` | `unless` |
| --- | --- | --- |
| Evaluated | Before cache lookup and method invocation | After the real method returns a result |
| Knows `#result`? | **No** | **Yes** |
| When expression returns `true` | Allows caching to be applied | Vetoes storing the newly computed result |
| When expression returns `false` | Skips caching for this call; method still runs | Allows storing the new result |
| Purpose | Choose which requests/arguments get cached | Choose which **results** must not be cached |

**Correct:**

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

**Wrong intent:**

```java
// Do not use #result to inspect the result at the condition stage.
@Cacheable(cacheNames = "accounts", condition = "#result != null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

At the time `condition` runs, the return value has not been computed yet; an expression relying on `#result` makes no sense for this goal and can cause evaluation errors.

**Combining both when filtering both inputs and outputs:**

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Meaning: requests with a null/blank `id` do not participate in caching; valid requests look up the cache, and if the source query returns `null`, it is not stored. `condition` does not replace business validation: the method can still be called with invalid input; validate inputs at the appropriate layer.

## 4. Cache Hit, Cache Miss, and "Cached Null" Are Three Different Situations

Do not equate "cache has no entry" with "cache has an entry holding a null value."

| State of a key in cache | `cache.get(key)` | Consequence when `@Cacheable` looks up |
| --- | --- | --- |
| No mapping | Returns `null` (no `ValueWrapper`) | Cache miss; real method is called |
| Mapping with `null` value and provider supports it | Returns non-null `Cache.ValueWrapper`, `get()` is null | Cache hit; real method can be skipped even though returned result is null |
| Mapping with an `Account` | Returns wrapper containing `Account` | Cache hit; returns stored object |

Illustrative code given an existing `Cache cache` variable:

```java
Cache.ValueWrapper wrapper = cache.get("A100");
if (wrapper == null) {
    System.out.println("MISS: key is not in cache yet");
} else if (wrapper.get() == null) {
    System.out.println("HIT: key currently holds null");
} else {
    System.out.println("HIT: " + wrapper.get());
}
```

`cache.get(key, Account.class)` returns `null` both on a miss and on a cached-null hit, so it cannot be used to distinguish the two states.

**Note on providers:** Spring Cache is an abstraction; null storage capability depends on the backend and configuration. For instance, `ConcurrentMapCacheManager` supports null by default using an internal placeholder object because `ConcurrentHashMap` does not accept null directly. Other providers may forbid null or handle it differently. `unless` sets the policy of **not putting new null results** into the cache at the annotation level, which remains useful even when switching backends. Do not assume that disabling null support in the provider automatically behaves like `unless`: some implementations throw an error when asked to store null.

## 5. Runnable Java 17 Example: Two Policies for the Same `null` Result

The following program uses Spring Framework 6.2.x and an in-process memory cache. Two regions are separated for comparison:

- `skipNull`: method has `unless = "#result == null"`; queries with no record yet continue reading the source on subsequent calls.
- `allowNull`: method has no `unless`; null is cached because the example configuration allows it. When a new record is created, the old cached-null entry persists until evicted.

Both methods return the same `Account` type. The `Repository.find` call count verifies precisely when a cache hit or miss happens.

**Structure:**

```text
cache-null-demo/
├── pom.xml
└── src/main/java/CacheNullDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-null-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/CacheNullDemo.java`:**

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheNullDemo {

    @Bean
    CacheManager cacheManager() {
        var manager =
                new ConcurrentMapCacheManager("skipNull", "allowNull");
        manager.setAllowNullValues(true);
        return manager;
    }

    @Bean
    AccountRepository accountRepository() {
        return new AccountRepository();
    }

    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }

    public record Account(String id, String label) {}

    public static class AccountRepository {
        private final Map<String, Account> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public Account find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public void save(Account account) {
            data.put(account.id(), account);
        }

        public int reads() {
            return reads.get();
        }
    }

    public static class AccountService {
        private final AccountRepository repository;

        public AccountService(AccountRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "skipNull",
            key = "#p0",
            unless = "#result == null"
        )
        public Account findSkipNull(String id) {
            return repository.find(id);
        }

        @Cacheable(cacheNames = "allowNull", key = "#p0")
        public Account findAllowNull(String id) {
            return repository.find(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheNullDemo.class)) {
            var service = context.getBean(AccountService.class);
            var repository = context.getBean(AccountRepository.class);
            var manager = context.getBean(CacheManager.class);

            System.out.println("skip #1: " + service.findSkipNull("A100"));
            System.out.println("skip #2: " + service.findSkipNull("A100"));
            System.out.println("skip reads: " + repository.reads());

            repository.save(new Account("A100", "Lan"));
            System.out.println("skip after insert: "
                    + service.findSkipNull("A100"));
            System.out.println("skip hit: "
                    + service.findSkipNull("A100"));
            System.out.println("skip reads: " + repository.reads());

            System.out.println("allow #1: "
                    + service.findAllowNull("B200"));
            System.out.println("allow #2: "
                    + service.findAllowNull("B200"));
            System.out.println("allow reads: " + repository.reads());

            repository.save(new Account("B200", "Minh"));
            System.out.println("allow after insert: "
                    + service.findAllowNull("B200"));

            Cache allowed = manager.getCache("allowNull");
            if (allowed == null) {
                throw new IllegalStateException("Missing allowNull cache");
            }
            Cache.ValueWrapper wrapper = allowed.get("B200");
            System.out.println("cached null exists: " + (wrapper != null));
            System.out.println("cached value is null: "
                    + (wrapper != null && wrapper.get() == null));

            allowed.evict("B200");
            System.out.println("allow after evict: "
                    + service.findAllowNull("B200"));
            System.out.println("all source reads: " + repository.reads());
        }
    }
}
```

Run with JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheNullDemo
```

**Lines printed by the program** (excluding tool or Spring startup logs, if any):

```text
skip #1: null
skip #2: null
skip reads: 2
skip after insert: Account[id=A100, label=Lan]
skip hit: Account[id=A100, label=Lan]
skip reads: 3
allow #1: null
allow #2: null
allow reads: 4
allow after insert: null
cached null exists: true
cached value is null: true
allow after evict: Account[id=B200, label=Minh]
all source reads: 5
```

**Explanation by source read count:**

1. `skipNull/A100` before it exists: both lookups miss because each null return is vetoed by `unless`. Counter equals 2.
2. After `repository.save(A100)`, the next lookup reads the new record and caches it; the following one hits. Counter rises to 3 and stays there.
3. `allowNull/B200` before it exists: the first call reads the source, gets null, and caches null; the second call hits without incrementing the counter (stays at 4).
4. After inserting `B200`, calling `findAllowNull("B200")` still sees the old cached-null and returns null. `Cache.get("B200")` yields a non-null wrapper whose `wrapper.get() == null`.
5. After `allowed.evict("B200")`, the stale copy disappears; the next lookup reads and caches the new record, incrementing the counter to 5.

In this program, `repository.save` is called directly to illustrate the effect of underlying data changing. In a real application, create/update/delete operations typically need an appropriate `@CacheEvict` or `@CachePut` strategy. Skipping null **does not replace** invalidation for previously cached non-null entries.

## 6. Methods Returning `Optional<T>`: Avoid Confusing the Wrapper with Its Contents

Spring Cache supports `java.util.Optional` with special semantics: if the `Optional` has a value, the inner value is cached; if `Optional.empty()` is returned, the value passed to the cache (if not vetoed) is treated as `null`. Within `unless`, `#result` is the **object inside the Optional**, not the `Optional` wrapper.

Example:

```java
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    unless = "#result == null"
)
public java.util.Optional<Account> findOptional(String id) {
    return repository.findOptional(id);
}
```

When `repository.findOptional(id)` returns `Optional.empty()`, `#result` evaluates to null and Spring does not store a new entry. When it returns `Optional.of(account)`, `#result` is `account` and can be stored. This snippet only illustrates a method on a service that already has a matching `repository`; it is not part of the standalone `CacheNullDemo.java` program in the previous section.

**Avoid the wrong expression in `unless`:**

```java
// Error-prone: #result is Account (or null), not Optional<Account>.
@Cacheable(cacheNames = "accounts", unless = "#result.isEmpty()")
public java.util.Optional<Account> findOptional(String id) {
    return repository.findOptional(id);
}
```

This expression attempts to call `isEmpty()` on the entity or on null. Use `unless="#result == null"` to veto both `null` and `Optional.empty()`. When you want to check a property on a potentially null entity, use appropriate SpEL safe navigation, such as `unless="#result == null || #result.disabled()"` if the actual type has a `disabled()` method.

## 7. When Should the Expression Be More Complex?

`unless = "#result == null"` is the direct choice when you only want to exclude null. It can be extended according to the result's contract:

| Goal | `unless` example | Meaning |
| --- | --- | --- |
| Do not cache null | `"#result == null"` | Block missing values |
| Do not cache null or empty lists | `"#result == null || #result.isEmpty()"` | Avoid storing empty results when the source changes frequently |
| Do not cache null or invalid entities | `"#result == null || !#result.valid()"` | Relies on an actual `valid()` method on the return type |
| Do not cache null or temporary data | `"#result == null || #result.temporary()"` | Only store stabilized results |

These are **illustrative expressions**, usable only when the return type has the corresponding method; Spring does not automatically generate `valid()`/`temporary()`. The `||` operator short-circuits: if `#result == null` is true, Spring does not evaluate the method access on the right-hand side, avoiding invocation on null.

**Do not automatically treat empty as null.** An empty list can be a valid, stable result worth caching. If data rarely changes yet the query is expensive, caching an empty list can be beneficial. Only block empty results if product or update policy requires it.

If an expression becomes long or depends on many business conditions, consider shaping the result into an explicit return type and writing tests for the condition. A short, testable expression is usually more maintainable than complex SpEL inside annotations.

## 8. Important Limitations

### 8.1. `unless` Does Not Clean Up Existing Cached-Null Entries

If a key was cached as null **before** adding `unless="#result == null"`, later `@Cacheable` calls can still hit the old entry; the real method does not run, so the new `unless` condition is never applied. You must **evict the old key** (or intentionally clear the region), change the key namespace/version, or wait for the provider's TTL. This is important when rolling out an application upgrade.

### 8.2. Do Not Combine `@Cacheable(sync = true)` with `unless`

Spring Framework places a restriction on `@Cacheable(sync = true)`: the `unless` attribute is not supported in this synchronized loading mode. The following example is **invalid under the annotation contract**:

```java
// Do not use this combination: sync=true does not support unless.
@Cacheable(
    cacheNames = "accounts",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

If you need both to prevent caching null and to stop multiple requests from loading the same key simultaneously (cache stampede), choose an appropriate synchronization solution at the data/provider layer and test loading behavior, rather than assuming you can add `sync=true` to the annotation above.

### 8.3. `@CachePut` and Stale Data

`@CachePut` **always runs the real method** and also has an `unless` attribute to decide whether to write the new result. However, if the method returns null, `unless="#result == null"` **only skips the new put**; it does not delete an existing old entry. If null means "the record was deleted" or "no longer valid," you must evict according to your data-update contract.

Example snippet on an existing service:

```java
@CacheEvict(cacheNames = "accounts", key = "#p0")
public void delete(String id) {
    repository.delete(id);
}
```

By default, `@CacheEvict` runs after the method succeeds; with transactions, design invalidation timing relative to the data source commit.

### 8.4. Cost of Not Caching `null`

If a non-existent ID is queried thousands of times, `unless="#result == null"` generates thousands of source queries because every call misses. Therefore consider:

- **Highly dynamic data where records often appear right after queries:** skipping null caching makes sense to surface new data sooner.
- **Invalid/non-existent IDs queried heavily:** consider intentional negative caching with a short TTL and an eviction strategy when the record is created to reduce source load.
- **Critical data requiring high consistency:** neither skip-null nor TTL replaces proper read/write workflows and business validation.

Depending on the provider, TTL, max size, and distributed behavior are configured separately. Spring Cache annotations do not provide a universal provider-independent TTL. When moving from a local cache to Redis or a multi-node cache, re-test null returns, eviction, serialization, and data consistency.

### 8.5. Proxies and Scope of Application

`@Cacheable` only takes effect when the class is Spring-managed and the call is intercepted per caching configuration (e.g., `@EnableCaching`). In default proxy mode, calling `this.findById(...)` within the same bean typically bypasses advice; tests can mislead you because the method always runs instead of hitting the cache. Always test through a service bean retrieved from the Spring context as shown in the demo program.

The skip-null-caching policy applies to the **annotated cache operation**, not as a global policy across every region, manual `Cache.put(...)` call, or writer in other services.

## 9. Checklist and Common Mistakes

1. **Confusing `condition` with `unless`:** to inspect the computed result, use `unless`, because `condition` does not have `#result`.
2. **Inverting the boolean logic:** `unless="#result != null"` refuses to store non-null data and may allow caching null, the opposite of the goal.
3. **Comparing against the string `"null"`:** `#result == 'null'` does not check for Java null; it compares against a character string.
4. **Misjudging `Optional`:** with supported wrappers, `#result` is the inner entity; `Optional.empty()` corresponds to null for caching purposes.
5. **Looking only at return values to infer hits/misses:** both a miss returning null and a cached-null hit return null; measure repository call counts or inspect `Cache.ValueWrapper`.
6. **Forgetting to evict old entries when source data changes:** skip-null only prevents caching new nulls; it does not automatically refresh old values or previously cached nulls.
7. **Assuming the provider always stores null:** null behavior depends on `CacheManager` and the provider; verify the actual configuration.
8. **Combining `unless` with `sync=true`:** not supported by Spring; design concurrency handling elsewhere.
9. **Not testing invalidation after create/delete:** with multiple writers or multiple instances, ensure affected data regions are properly updated.
10. **Ignoring performance impact:** repeated misses for non-existent IDs can cause heavy database load; the skip-null decision must fit traffic and freshness requirements.

Recommended test cases:

| Case | How to execute | Expectation with `unless="#result == null"` |
| --- | --- | --- |
| Consecutive misses returning null | Read the same non-existent ID twice | Source is called twice |
| Miss then record appears | Read null, create record, read again | Reads the new record and can cache it |
| Hit on non-null object | Read the same valid ID twice | Source is called only once |
| `Optional.empty()` | Return empty optional then call again | Empty result is not cached |
| Config change with old cached-null | Seed cached-null then add `unless` | Must evict/invalidate old entry to receive new data |
| Source error | Method throws exception | No new result stored; exception propagates normally |

## 10. Practical Conclusion

For a synchronous method returning an object or null, the most fitting expression is usually:

```java
@Cacheable(cacheNames = "accounts", key = "#p0", unless = "#result == null")
public Account findById(String id) {
    return repository.findByIdOrNull(id);
}
```

Understand the full contract of this line: **cache hits still return existing entries; when a cache miss produces a null result, Spring does not write a new null; when the result is non-null, Spring can write it to the cache**. For long-term correctness, align keys and invalidation with create/update/delete operations.

## Official Documentation

- Spring Framework — Cache Annotations / Conditional Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `@Cacheable` Javadoc (`unless` condition and `sync` restriction): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `ConcurrentMapCacheManager` Javadoc (`allowNullValues`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
