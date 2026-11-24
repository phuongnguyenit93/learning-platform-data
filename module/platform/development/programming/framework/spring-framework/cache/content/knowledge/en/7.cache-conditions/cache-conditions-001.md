# Spring Cache: `condition` and Checking Before Applying the Cache

## 1. Purpose and Use Cases

A method annotated with `@Cacheable` does not necessarily have to use the cache on **every invocation**. For example, rarely changing product code data can be cached, whereas special query data, test requests, or cases requiring fresh computation should go straight into the method.

Spring Cache supports the `condition` attribute on cache annotations. This is a **Spring Expression Language (SpEL) expression returning a boolean**, used to decide whether to apply the **cache operation for the current invocation**.

After this lesson, you should understand:
- `condition` is evaluated **before cache lookup** in the `@Cacheable` context; distinguish the effect when the condition is true or false.
- Access parameters via `#p0`, `#p1`, `#root.args`; perform null-safe checks and write maintainable expressions.
- Distinguish `condition` (checking based on inputs) from `unless` (which can veto caching the result after the method runs).
- Understand how `condition` participates in `@CachePut` and `@CacheEvict`; avoid using conditions as an authorization mechanism.
- Observe cache hits/misses with a Java 17+ example running through a Spring proxy.

Running scenario throughout this lesson: only codes starting with `HOT-` are read from and written to the `items` cache. `COLD-` codes and `null` arguments still execute the business logic every time without using the cache.

## 2. How Does `@Cacheable(condition = "...")` Handle an Invocation?

Consider the following configuration inside a Spring-managed service:

```java
@Cacheable(
    cacheNames = "items",
    key = "#p0",
    condition = "#p0 != null && #p0.startsWith('HOT-')"
)
public String find(String code) {
    return loadFromSource(code);
}
```

This is a **single-method snippet**, not a standalone program. `loadFromSource` represents the work that must run when the cache is bypassed or when a cache miss occurs.

How Spring Cache processes this in standard proxy mode:

```text
Client calls find(code) through Spring proxy
           |
           v
Evaluate condition on current input
           |
      +----+-----------------------+
      |                            |
   false                          true
      |                            |
      v                            v
Skip cache operation         Select cache and build key
      |                            |
      v                            v
Call method directly         Check entry with key
      |                            |
      v                       +----+----------+
Return result                hit             miss
                               |               |
                               v               v
                         Return old value  Run method
                                               |
                                               v
                                        Cache valid result
                                        (if not vetoed by unless)
                                               |
                                               v
                                           Return value
```

**If `condition` returns `false`:** Spring skips cache lookup and cache write **for that operation**. The method still executes when called; if called three times with an argument that fails the condition, the body may run all three times. This is **not** a feature to block method execution or a validation mechanism.

**If `condition` returns `true`:** the `@Cacheable` operation is applied normally. If the key already exists and the entry is valid, Spring returns the cached data and can skip calling the method; on a cache miss, it invokes the method and stores the result according to policy.

The expression is evaluated for **each invocation**. If a key was cached previously and later the condition on the current request evaluates to `false`, that request **does not read the old cache entry**; however, the old entry **is not deleted** just because the condition is false. When the condition becomes `true` again, that entry can still be used if it has not expired or been evicted.

| `condition` | Entry state | Does `@Cacheable` read cache? | Does body run? | Is result written to cache? |
| --- | --- | --- | --- | --- |
| `false` | Present or absent | No | Yes | No |
| `true` | Hit | Yes | No | No new write needed |
| `true` | Miss | Yes | Yes | Yes, unless prevented by `unless`/provider |
| SpEL evaluation error | Undetermined | No normal cache result | Should not be assumed | Usually raises a cache handling error |

This table assumes the method returns synchronously and no other cache operations act on it at the same time. For async/reactive return types, completion timing and result storage follow rules specific to the Spring version and cache provider.

## 3. Writing Correct and Safe SpEL Conditions

### 3.1. Syntax and Available Variables

Commonly used values:

| Expression | Meaning | Example |
| --- | --- | --- |
| `#p0` / `#a0` | First argument (index 0) | `#p0 != null` |
| `#p1` / `#a1` | Second argument (index 1) | `#p1 > 0` |
| `#root.args[0]` | First argument in the args array | `#root.args[0] == 'VN'` |
| `#root.methodName` | Name of the invoked method | `#root.methodName == 'find'` |
| `#root.targetClass` | Class of the target | Used when reading metadata is needed |
| `#code` | Argument by name, if parameter name metadata is available | `#code.startsWith('HOT-')` |

Using `#p0`/`#p1` is a reliable approach when you are unsure whether the project is compiled with the `-parameters` flag to access parameter names like `#code`. Parameters are zero-indexed (**0**), and `#` is SpEL's variable reference syntax.

Some practical patterns:

```java
@Cacheable(cacheNames = "products", condition = "#p0 > 0")
public Product find(long id) { /* query */ return null; }

@Cacheable(cacheNames = "prices",
           condition = "#p0 != null && #p1 > 0")
public Price price(String region, long productId) {
    /* compute price */ return null;
}

@Cacheable(cacheNames = "documents",
           condition = "#p0 != null && #p0.startsWith('PUB-')")
public Document findDocument(String documentCode) {
    /* query */ return null;
}
```

These are **illustrative signature snippets** and do not compile standalone because data type classes and business bodies are omitted. `condition` is always placed inside a **Java string** within the annotation, while the SpEL expression itself uses operators such as `&&`, `||`, `!`, `==`, `!=` and method/property calls according to SpEL syntax.

### 3.2. Null Checks and Short-Circuiting

For example, when checking that a code only starts with `HOT-`:

```java
condition = "#p0 != null && #p0.startsWith('HOT-')"
```

The right-hand side is only evaluated when `#p0` is non-`null` thanks to short-circuiting of the AND operator. If you write `#p0.startsWith('HOT-')` when the actual value is `null`, the operation can fail due to an expression evaluation error before the business method is called.

Prefer short conditions derived purely from input data with **no side effects**. For instance, do not call external services, modify a database, increment counters, or read network data sources inside SpEL. A condition that is both slow and has side effects makes every cache hit path unpredictable and hard to test.

### 3.3. `#result` Is Not Part of `@Cacheable.condition` Input Data

In `@Cacheable`, `condition` is checked before the method result exists, so **you cannot use `#result` to decide whether to look up the cache**. If you want to inspect the size, status, or content of the result **after** the method runs, use `unless`.

Wrong timing:

```java
// Wrong idea: condition does not yet have the method result to check.
@Cacheable(cacheNames = "products", condition = "#result != null")
public Product find(String id) { /* ... */ return null; }
```

More appropriate:

```java
// condition decides whether to apply caching for valid codes.
// unless skips writing when the result has no data.
@Cacheable(
    cacheNames = "products",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Product find(String id) { /* ... */ return null; }
```

Both snippets above are illustrative; `Product` and business logic must be implemented separately. Note that `unless` does not cancel a cache hit that already occurred: if a key has a valid entry, `@Cacheable` can return the cached result immediately without running the body to evaluate a new result.

## 4. Complete Runnable Example: Observing `condition` Before Cache Lookup

This program uses **Java 17+**, Spring Framework Cache via **Spring Boot 3.3.x** libraries, and `ConcurrentMapCacheManager` to run in memory without Redis or a database. Results are generated using a counter so we can see exactly when the body executes.

Create the structure:

```text
cache-condition-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ConditionDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'cache-condition-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ConditionDemo'
}
```

File `src/main/java/demo/cache/ConditionDemo.java` (complete):

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ConditionDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        ItemService itemService() {
            return new ItemService();
        }
    }

    public static class ItemService {
        private final AtomicInteger executions = new AtomicInteger();

        @Cacheable(
            cacheNames = "items",
            key = "#p0",
            condition = "#p0 != null && #p0.startsWith('HOT-')"
        )
        public String find(String code) {
            return code + "-load-" + executions.incrementAndGet();
        }

        public int executionCount() {
            return executions.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            // Important: retrieve the bean from the Spring context so calls go through the proxy.
            ItemService service = context.getBean(ItemService.class);

            System.out.println(service.find("HOT-1"));
            System.out.println(service.find("HOT-1"));

            System.out.println(service.find("COLD-1"));
            System.out.println(service.find("COLD-1"));

            System.out.println(service.find("HOT-2"));
            System.out.println(service.find("HOT-2"));

            System.out.println(service.find(null));
            System.out.println(service.find(null));

            System.out.println("executions=" + service.executionCount());

            Cache cache = context.getBean(CacheManager.class).getCache("items");
            if (cache == null) {
                throw new IllegalStateException("Missing cache: items");
            }
            System.out.println("cacheHasHOT=" + (cache.get("HOT-1") != null));
            System.out.println("cacheHasCOLD=" + (cache.get("COLD-1") != null));
        }
    }
}
```

Run in the `cache-condition-demo` directory:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`). Output printed by the program, excluding framework/build tool logs:

```text
HOT-1-load-1
HOT-1-load-1
COLD-1-load-2
COLD-1-load-3
HOT-2-load-4
HOT-2-load-4
null-load-5
null-load-6
executions=6
cacheHasHOT=true
cacheHasCOLD=false
```

Detailed comparison:

1. `find("HOT-1")`: expression is true; lookup for key `"HOT-1"` misses, runs the method for the 1st time, and stores the result.
2. Repeated `find("HOT-1")`: condition is still true; cache hit returns `HOT-1-load-1`, counter does not increment.
3. `find("COLD-1")` twice: condition is false because the prefix is not `HOT-`; **no lookup/put**, method runs on invocations 2 and 3.
4. `find("HOT-2")` twice: first misses, second hits; method runs exactly once more (invocation 4).
5. `find(null)` twice: condition `#p0 != null` is false, does not attempt to call `startsWith` and does not use null as a key; method still runs twice (invocations 5 and 6).
6. Direct inspection of the cache manager confirms only the HOT group was written: `cacheHasHOT=true`, `cacheHasCOLD=false`.

**Why does this example reproduce caching?** `@EnableCaching` is placed on the Spring configuration, the `ItemService` bean is created and retrieved through the context, and calls originate from `ConditionDemo`, so they pass through the Spring proxy. If replaced with `new ItemService().find(...)`, caching annotations are not activated. Similarly, self-invoking `this.find(...)` from another method in the same service bypasses the proxy in default mode.

`ConcurrentMapCacheManager` is a choice for learning; for Redis/Caffeine you also need to consider TTL, key serialization, distribution, quotas, and provider cache policies. `condition` does not set TTL or create cache stores on its own.

## 5. Comparing `condition` with `unless` and `key`

A single cache operation involves three separate questions:

| Configuration | Question | Timing with `@Cacheable` | Can use `#result`? |
| --- | --- | --- | --- |
| `condition` | Should caching be used for this invocation? | Before cache lookup/method | **No** |
| `key` or `keyGenerator` | Which entry in the cache? | When the cache operation needs a key | No for normal `@Cacheable` keys |
| `unless` | Should we refuse to store the newly computed result? | After the method has run on a miss | **Yes** |

Example applying both conditions:

```java
@Cacheable(
    cacheNames = "searchResults",
    key = "#p0",
    condition = "#p0 != null && #p0.length() <= 50",
    unless = "#result == null || #result.isEmpty()"
)
public String search(String query) {
    return searchFromDatabase(query);
}
```

This is an illustrative method with `searchFromDatabase` implemented by the application.

- Query too long or null: `condition=false`, cache is not used, method still runs.
- Valid query and cache miss: method runs; if the result is null or empty, `unless=true` prevents storing the result.
- Valid query and cache hit: uses the existing entry and does not run the method to compute a new result; `unless` does not replace an invalidation mechanism.

Do not confuse **`condition=false`** with **"do not store after running"** in every sense: in the case of `@Cacheable`, it also **skips the cache read step**. Conversely, `unless=true` only vetoes the **cache put of the current result**, and has no effect of automatically invalidating a previously existing entry.

### Why Not Use the Result for `condition`?

To know the result, the method has to run. However, `@Cacheable` needs to decide whether to perform a lookup before running the method so it has the opportunity to skip computation. Therefore, inputs are used as the condition beforehand, and the result is checked afterward with `unless`. Information that is not yet available before execution, such as the total number of rows returned from a query, is usually better suited for `unless`.

## 6. `condition` on `@CachePut` and `@CacheEvict`

Both annotations also support `condition`, but you must separate the **cache operation** from **business execution**:

### 6.1. `@CachePut`

```java
@CachePut(
    cacheNames = "profiles",
    key = "#p0.id",
    condition = "#p0 != null && #p0.cacheEligible"
)
public Profile save(Profile input) {
    return repository.save(input);
}
```

This is an illustrative snippet requiring actual `Profile` and `repository` classes. `@CachePut` is intended to update the cache from the **method result**, not to use the cache to skip the method. When the condition is false, the `save` method still executes; the cache put is skipped. When the condition is true, the method still runs and Spring can write the result to the cache according to the operation. The `condition` expression in the example accesses input data, so it does not need to rely on `#result`.

### 6.2. `@CacheEvict`

```java
@CacheEvict(
    cacheNames = "profiles",
    key = "#p0",
    condition = "#p1",
    beforeInvocation = false
)
public void updateProfile(String id, boolean changed) {
    // Write source data, if changes occurred.
}
```

This example makes sense when `changed` represents a business condition **guaranteed to be accurate** at the input, and updates that change cached values always flag it accurately. With `@CacheEvict`, `condition` controls **whether to evict**, not whether to skip the `updateProfile` method.

- `beforeInvocation=false` (default): evicts when the operation qualifies and the method completes successfully.
- `beforeInvocation=true`: the eviction operation runs **before** calling the method if the condition permits, even if the method subsequently throws an exception.
- `allEntries=true` clears all entries of the selected cache and does not need a single key; `condition` can still decide whether to perform this clear operation.

**Consistency note:** If you update the database and forget to evict because the condition is false, a stale entry may be read back. Conditions on cache annotations do not automatically track all source data changes or replace an invalidation strategy.

## 7. Designing Conditions for the Right Need

### 7.1. Prefer Stable Criteria Without Side Effects

Suitable criteria usually relate directly to parameters:
- Positive ID / valid format: `#p0 > 0`.
- Classifying cacheable requests: `#p1 == 'STANDARD'`.
- Query length within an appropriate threshold: `#p0 != null && #p0.length() <= 50`.
- Non-blank input: `#p0 != null && !#p0.isBlank()`.

If all conditions relate to the same business rule across many places, consider placing the rule clearly into a testable component, or redesigning the API into separate methods. Avoid stuffing complex business logic and side-effecting calls into SpEL expressions.

### 7.2. Do Not Use `condition` as an Authorization System

Checking whether to use the cache **does not determine whether a user has permission to view data**. On a cache hit, the method body may not run; if all authorization lives only inside the body, a result can be returned from the cache before permission checks execute.

When data depends on tenant, user, scope, or region, you must ensure both:
- Authentication/authorization is performed at the appropriate layer **before returning data**, including on the cache hit path.
- Cache keys and/or cache regions properly isolate data scope. Two users must not share a key for private data.
- When permissions or data change, a clear eviction/TTL strategy is in place.

For example, `condition="#p0.role == 'ADMIN'"` is not a trustworthy security check if `role` is client-supplied input. Permission decisions must come from an authenticated security mechanism.

### 7.3. Conditions Changing Over Time Do Not Automatically Delete Old Entries

Suppose a policy initially allows caching; later a feature flag is turned off to force querying the source. Requests while the flag is off bypass the cache, but previously created entries still remain. When the flag is turned back on, stale data can become a cache hit if it is still in the store.

If a condition is dynamic like a feature flag, system policy must clearly define when to clear the cache or change the key version. `condition` itself only **skips the current operation**; it does not perform data migration or purge cache history.

### 7.4. Consider Evaluation Cost

`condition` is part of the cache invocation path. Even on a cache hit, evaluating the condition has a cost; short parameter-based expressions are usually acceptable. Do not make HTTP calls, open transactions, or query a DB just to return a boolean in `condition`: doing so defeats the benefit of caching and can introduce erratic latency.

### 7.5. Interaction with Keys and Results

If the same cache stores two different results for an identical key (for example by locale/tenant when locale/tenant is not included in the key), `condition=true` cannot fix that collision. The default key may include all parameters, whereas a custom `key="#p0"` only uses the specified value. Check **which fields determine the output**, and make sure the key includes all of them.

In update flows, `@Cacheable`, `@CachePut`, and `@CacheEvict` must agree on cache region and key. Using `condition` to choose a region to cache while forgetting to invalidate that region is a common source of stale data.

## 8. Common Errors and How to Handle Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `condition=false` yet the method still runs | This is the intended cache bypass behavior | Distinguish skipping the cache from blocking business execution. |
| `condition=true` yet the method still runs | Cache miss, expired, different key, or proxy not active | Measure call count and key/cache name. |
| SpEL error when argument is null | Accessing a method/property on null before guarding | Use `#p0 != null && ...`. |
| Writing `condition="#result != null"` | `@Cacheable.condition` is evaluated before a result exists | Move the result check to `unless`. |
| Queries not cached as expected | Condition is false or parameter type differs from expectation | Log/test inputs in the request context. |
| Method runs directly despite annotations | Bean not managed by Spring, `@EnableCaching` in wrong context, self-invocation | Check bean/proxy and configuration context. |
| Stale entries appear when feature flag re-enables | `condition=false` does not automatically delete cached entries | Evict or version keys according to policy. |
| Another user's data is returned | Cache key lacks tenant/user scope, authorization placed incorrectly | Design authorization and cache/key selection properly. |
| `@CacheEvict` does not remove old entry | Evict condition is false, key mismatch, only clearing one region | Cross-check read and evict operations. |

Start debugging with a small, measurable test: call the same key twice when `condition=true`, then try a key that fails the condition twice. If the first case hits and the second always executes the body, the condition logic is working as expected.

When you need to observe annotation processing, you can enable logging in a test environment:

```properties
logging.level.org.springframework.cache.interceptor=TRACE
```

Logger names and verbosity depend on the application's logging configuration. Do not rely solely on a single log line; verifying behavior via results and body execution counts remains essential.

## 9. Testing Checklist and Thought Exercises

1. **Condition true, cache has no entry:** call the first time, method execution count increases by 1. Call again with the same key while cache is not evicted, count does not increase.
2. **Condition false:** call twice with the same key, execution count increases by 2; verify the provider contains no new entry from these two calls.
3. **Null argument:** short-circuit expression does not error; method still handles null per contract or returns a controlled business error.
4. **Condition true but `unless` vetoes:** method runs on miss, result is not put; next call must still run again if no entry exists.
5. **Entry already exists then condition becomes false:** current call bypasses. Verify the old entry is not automatically deleted.
6. **Data changes:** test the update + evict flow with the same cache name/key to prove stale data is not reused.
7. **Multiple contexts/proxies:** retrieve the service from the Spring context in integration tests; do not prove caching by calling `new Service()` directly.

Review questions:

**Q1.** Does `condition=false` prevent the method from running?

**Answer:** No. For `@Cacheable`, it skips the cache for that invocation, so the method still executes.

**Q2.** In `@Cacheable.condition`, can you write `#result.isEmpty()`?

**Answer:** No. The result does not exist yet at the `condition` evaluation stage; use `unless="#result == null || #result.isEmpty()"` when post-method evaluation is needed.

**Q3.** Calls use the same key: one call with condition true creates a cache entry; another call has condition false. Is the entry deleted?

**Answer:** No. A call with condition false only bypasses the cache operation at that moment.

**Q4.** Does `@CachePut(condition=false)` skip saving to the database?

**Answer:** No. `@CachePut` does not prevent the method from running; writing to the database is business logic inside the method and proceeds according to method logic.

**Q5.** Can `condition` be used to check whether a tenant is authorized to access data?

**Answer:** Not sufficient. Authorization must protect both cache hits and misses; caches/keys with proper data scoping must be selected.

## 10. Takeaways

- `condition` is a **boolean SpEL expression based on the invocation context**, used to decide **whether to apply or skip the cache operation**.
- With `@Cacheable`: `condition=false` → **no cache lookup, no cache write, method still runs**; `condition=true` → check cache, hit can skip the body, miss runs and may write.
- `condition` is evaluated before the method result exists; use `unless` when you need to veto caching based on `#result`.
- Use null-safe checks, side-effect-free expressions, consistent key/region/eviction design, and authorization independent of the cache.
- Every caching annotation test must go through the **Spring proxy** and observe both execution counts and cache contents.

### References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
