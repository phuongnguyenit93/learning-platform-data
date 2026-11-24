# JCache: Differences in Cached Exceptions and Eviction Timing

## Learning Objectives

When working with **JCache (JSR-107)** in Spring Framework, the two easiest points of confusion compared to Spring's caching annotations are:

1. **`@CacheResult` can store selected thrown exceptions** in a separate cache so subsequent calls with the same key receive that exception again without executing the target method.
2. **`@CacheRemove` and `@CacheRemoveAll` control eviction timing** via `afterInvocation`, while also providing **`evictFor`/`noEvictFor`** to decide whether eviction occurs when a method throws an exception. Spring's **`@CacheEvict`** has `beforeInvocation` but lacks equivalent exception filters on the annotation.

JCache **`@CachePut`** also has `afterInvocation` and `cacheFor`/`noCacheFor`: this is the **cache write** branch, featuring similar before/after and failure-handling rules rather than eviction. Because all three annotation groups commonly appear together in one service, this lesson cross-references them wherever relevant.

By the end of this lesson, you will be able to:
- Distinguish **result cache**, **exception cache**, and **entry/cache eviction**.
- Explain the full roles of **`exceptionCacheName`**, **`cachedExceptions`**, **`nonCachedExceptions`**, and **`skipGet`** in `@CacheResult`.
- Determine the exact timing of `@CacheRemove`/`@CacheRemoveAll` eviction for **success, failure, `afterInvocation=true/false`, `evictFor`, and `noEvictFor`**.
- Distinguish **JCache `@CachePut` reading `@CacheValue` from a parameter** versus **Spring `@CachePut` using the return value**.
- Run a Java 17 + Spring Framework 6.2.19 + `javax.cache` API 1.1.1 example to observe method invocation counts, replayed exceptions, and cache eviction firsthand.
- Avoid assuming post-method eviction equals **post-database-commit eviction**, or that cached exceptions automatically expire when underlying source data is repaired.

**Scope:** uses JCache 1.1.x **`javax.cache.annotation`** annotations via Spring Framework 6.2.x. Spring supports these annotations directly on a **Spring `CacheManager`**; the example does not require a native JCache provider. If using a real JCache provider (Ehcache, Hazelcast, Infinispan, etc.), also account for the provider's TTL, serialization, transaction, and visibility contracts.

## 1. Distinguishing Business Exceptions from Cache Infrastructure Exceptions

Three situations to keep separate:

| Situation | Example | Should It Necessarily Be Cached? |
| --- | --- | --- |
| **Business method returns a result** | Product lookup succeeds | Usually safe to cache the result |
| **Business method throws an exception** | Invalid input ID; temporary service error | Can cache **certain deterministic errors**, should not cache transient errors |
| **Cache infrastructure fails** | Redis timeout, serialization error, missing `cacheName` | Do not treat this as a business exception managed by `@CacheResult` normally |

**Exception caching** in JCache means intentionally storing a qualifying exception object in an `@CacheResult` operation's **exception cache**. It does not mean "Spring caches every `Throwable` thrown by any bean", is not a workaround for cache provider failures, and is not **negative caching of null values**.

For instance, a malformed ID that always yields the same business validation failure may be appropriate to cache to avoid repeating expensive validation work. Conversely, an upstream service timeout is typically transient: caching that exception for too long turns a brief outage into a prolonged failure even after the upstream recovers.

For a given key, keep these three clearly separated:
- **Value cache**: successful method return values.
- **Exception cache**: exceptions explicitly permitted to be cached.
- **Source of truth**: database or business system, which does not automatically change when those two caches change.

## 2. JCache in Spring: Correct Namespace and Infrastructure

Standard JCache 1.1.1 annotations use this package:

~~~java
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheValue;
import javax.cache.annotation.CacheDefaults;
~~~

They are **distinct** from Spring's annotations:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.CacheConfig;
~~~

Specifically:
- **JCache `@CacheResult`** is close to **Spring `@Cacheable`**, but adds **exception caching** and **`skipGet`**.
- **JCache `@CacheRemove`** is close to **Spring `@CacheEvict`**, but JCache adds **`evictFor`/`noEvictFor`** for method failures.
- **JCache `@CacheRemoveAll`** is close to **Spring `@CacheEvict(allEntries=true)`**.
- **Both share the name `@CachePut`**, yet their APIs and cached values **differ**: JCache uses a `@CacheValue`-annotated parameter; Spring uses the method's return value.
- **JCache `@CacheDefaults`** matches **Spring `@CacheConfig`** conceptually for class-level defaults, rather than sharing identical attributes.

**Do not import the wrong one**: if your code tries to declare `cacheFor`, `noCacheFor`, or `afterInvocation` on JCache `@CachePut` while your IDE auto-imports `org.springframework.cache.annotation.CachePut`, those attributes will not exist.

### Enabling in Spring Framework

Per Spring documentation, **`@EnableCaching`** simultaneously activates JCache annotation support when the **JSR-107 API** and **`spring-context-support`** module are on the classpath.

~~~java
@Configuration
@EnableCaching
public class CachingConfig {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("records", "recordFailures");
    }
}
~~~

This snippet is illustrative and needs imports; the full example appears later. Here `CacheManager` is **`org.springframework.cache.CacheManager`**, and `ConcurrentMapCacheManager` belongs to Spring. **Configuring a `javax.cache.CacheManager` is not required** just to execute JCache annotations via Spring's interceptor.

Spring proxy mode still applies: methods must be invoked through a **Spring-managed proxy bean**. Calling `this.otherMethod(...)` within the same target normally bypasses caching advice, even when `otherMethod` carries `@CacheResult` or `@CacheRemove`.

## 3. `@CacheResult`: Result Cache and Exception Cache Are Separate

Basic configuration:

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class
)
public String find(@CacheKey String id) {
    return repository.find(id);
}
~~~

This is an illustrative snippet: `repository` and `InvalidIdException` are defined by the application.

- **`cacheName="records"`**: stores successful results.
- **`exceptionCacheName="recordFailures"`**: stores selected exceptions.
- **`cachedExceptions=InvalidIdException.class`**: filter specifying which exception types may be written to the exception cache.
- **`@CacheKey String id`**: designates `id` as the key component built by JCache's `CacheKeyGenerator`.

### Flow When No Cache Hit Occurs

~~~text
caller -> Spring/JCache interceptor -> compute JCache key
                                    |
                                    +-- result in value cache?
                                    |      Yes -> return result, skip method
                                    |      No  -> check exception cache (if enabled)
                                    |
                                    +-- matching exception in exception cache?
                                    |      Yes -> rethrow cached exception
                                    |      No  -> invoke target method
                                    |
                                    +-- method succeeds -> cache result
                                    |
                                    +-- method throws exception
                                           |
                                           +-- eligible for caching -> store exception
                                           +-- not eligible -> do not store
                                           +-- still propagate exception to caller
~~~

This represents the logical business flow rather than prescribing lookup order if out-of-band operations leave conflicting entries in both caches. In a healthy design, a single key should not simultaneously hold a stale result and a contradictory cached exception; when source data is modified, perform controlled invalidation.

### Without `exceptionCacheName`: Exceptions Are NOT Cached by Default

~~~java
@CacheResult(cacheName = "records")
public String find(String id) {
    if (id.isBlank()) throw new IllegalArgumentException("empty");
    return id;
}
~~~

If the call throws an exception, **exceptions are not cached by default**. This holds true even if another place uses `@Cacheable` on a cache with the same name: each annotation follows its own semantics.

**Warning:** setting `cachedExceptions` without **`exceptionCacheName`** does not enable exception caching. When `exceptionCacheName` is empty, no exception storage region is configured for the operation.

### The Exception Cache Must Exist and Be Resolvable

If you use `ConcurrentMapCacheManager` in **static mode** with only `"records"` and forget to register `"recordFailures"`, Spring may fail to resolve the exception cache, causing a configuration error. Register **both cache names**; an exception cache is not an implicit "hidden area" that always exists by default.

## 4. Exception Filters on `@CacheResult`

Three key attributes:

| Attribute | Type | Default | Meaning |
| --- | --- | --- | --- |
| **`exceptionCacheName`** | `String` | Empty string | When omitted, exception caching is disabled |
| **`cachedExceptions`** | `Class<? extends Throwable>[]` | Empty array | `Throwable` types permitted to be cached |
| **`nonCachedExceptions`** | `Class<? extends Throwable>[]` | Empty array | `Throwable` types excluded from caching |

**When `exceptionCacheName` is non-empty**, JCache 1.1.1 rules state:

| `cachedExceptions` | `nonCachedExceptions` | Which Exceptions Are Cached? |
| --- | --- | --- |
| Empty | Empty | **All** exceptions thrown by the target method qualify |
| Non-empty list | Empty | Only exceptions matching **`cachedExceptions`** |
| Empty | Non-empty list | All exceptions **except** those matching **`nonCachedExceptions`** |
| Both non-empty | Both non-empty | Must match **`cachedExceptions`** **and not match `nonCachedExceptions`** |

Type matching follows inheritance hierarchy semantics—equivalent to **`instanceof`** rather than exact `Class` equality. When an exception matches both the allowlist and the denylist, **`nonCachedExceptions` excludes it**.

Example:

~~~java
@CacheResult(
    cacheName = "profiles",
    exceptionCacheName = "profileFailures",
    cachedExceptions = RuntimeException.class,
    nonCachedExceptions = TemporaryFailureException.class
)
public Profile find(String id) {
    return repository.load(id);
}
~~~

This is an illustrative snippet; `Profile`, `TemporaryFailureException`, and `repository` are supplied by the project. Here:
- `InvalidProfileException extends RuntimeException` → eligible to be cached.
- `TemporaryFailureException extends RuntimeException` but appears in `nonCachedExceptions` → **not** cached.
- Checked `IOException` is not a `RuntimeException` → **not** cached under this filter.
- If `exceptionCacheName` is omitted, **neither filter enables exception caching**.

**Common risk:** setting only `exceptionCacheName` while leaving both lists empty causes JCache rules to **cache every exception**. That is very dangerous if the method can throw timeouts, transient `IllegalStateException`s, or external dependency failures. Intentionally whitelist stable errors instead.

### Is the Exception Rethrown or Turned into a Result?

A cached exception never turns into a `String`, `null`, or normal return value. For the same key, the interceptor **rethrows the cached exception**, so the caller still takes the error path. The difference is that **the real method does not execute again**. You can verify this with a method invocation counter.

Cached exceptions retain the stack trace and metadata from the original creation; therefore, **do not rely on a cached exception having a fresh stack trace** per invocation. Avoid embedding session-specific data, secret tokens, or PII inside cached exception objects, especially when providers serialize, store by value, or persist out-of-process.

### `skipGet=true`

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class,
    skipGet = true
)
public String refresh(String id) {
    return repository.refresh(id);
}
~~~

This is an illustrative snippet. **`skipGet=true`** forces the method to run **regardless of any result cache hit**, and the **pre-invocation exception cache lookup** is skipped as well. When the method succeeds, the result is still cached per normal rules; when it throws an exception, the exception can still be cached if it matches the filter.

**`skipGet` does not mean "disable caching completely"**: it disables the pre-execution read branch without disabling result writes or exception writes.

## 5. Cache Keys: Exceptions and Results Must Share the Same Call Identity

JCache generates cache keys from method parameters, with **`@CacheKey`** selecting exact key components. When at least one `@CacheKey` is present, those annotated parameters determine the generated key via JCache's `CacheKeyGenerator`. If no `@CacheKey` is placed, eligible parameters (excluding `@CacheValue` on JCache `@CachePut`) are used by default.

~~~java
@CacheResult(cacheName = "records",
             exceptionCacheName = "recordFailures",
             cachedExceptions = InvalidIdException.class)
public String find(@CacheKey String id, boolean validateOnly) {
    return repository.load(id, validateOnly);
}
~~~

This is an illustrative snippet. In this example the key contains only **`id`**. If `validateOnly` alters the business result or whether an exception is thrown, **do not exclude `validateOnly` from the key**, because an exception or result cached for `validateOnly=true` could be wrongly reused for `validateOnly=false`.

Design rule: **All input data capable of changing the cached result or cached exception must be included in the cache key or an appropriate cache namespace** (tenant, locale, document version, permissions, feature flags, etc., when relevant). A cached exception with an underspecified key can be even worse than a wrong cached result because it blocks recovery paths persistently.

**JCache key generation does not automatically match Spring's `KeyGenerator`.** When mixing JCache annotations and Spring annotations on the same cache store, establish and verify a unified key strategy; do not assume a hand-picked `String` key equals the `GeneratedCacheKey` created by the interceptor.

## 6. `@CacheRemove`: Single-Entry Eviction Timing

JCache **`@CacheRemove`** is similar to **Spring `@CacheEvict`** for a single key. The key attribute is:

~~~java
@CacheRemove(cacheName = "records", afterInvocation = true)
public void delete(@CacheKey String id) {
    repository.delete(id);
}
~~~

This is an illustrative snippet; `repository` is not defined here.

**`afterInvocation=true` is the default**:
- Business method executes first.
- If the method completes normally, the interceptor requests eviction of the matching entry.
- If the method throws an exception, **eviction does not happen by default**.
- Error-path behavior can be adjusted using **`evictFor`/`noEvictFor`**.

Compare with:

~~~java
@CacheRemove(cacheName = "records", afterInvocation = false)
public void deleteEarly(@CacheKey String id) {
    repository.delete(id);
}
~~~

**`afterInvocation=false`**:
- Evicts the entry **before** invoking the target method.
- If the method subsequently throws an exception, the eviction **has already been requested**; it is not rolled back by default.
- The exception filters **`evictFor` and `noEvictFor` do not participate** when `afterInvocation=false`, because no target exception has occurred yet at eviction time.

This is a major distinction between **when eviction is requested** and **the actual outcome of the business operation**. Choose `afterInvocation=false` only when eviction must occur even if the method fails, and you accept the consequences of concurrent readers missing while the data source is not yet updated.

### `@CacheRemove` Eviction Behavior Table

| `afterInvocation` | Target Method Outcome | Default Filter | Evict? |
| --- | --- | --- | --- |
| **`true`** | Succeeds | Filters irrelevant | **Yes**, after method |
| **`true`** | Throws exception | `evictFor` and `noEvictFor` both empty | **No** |
| **`true`** | Throws exception matching `evictFor` | Not excluded by `noEvictFor` | **Yes**, despite method error |
| **`true`** | Throws exception not matching filter | — | **No** |
| **`false`** | Succeeds | Filters not evaluated | **Yes**, before method |
| **`false`** | Throws exception | Filters not evaluated | **Yes**, before method |

**Do not describe `afterInvocation=true` as "evict after commit"**. It is only relative to the **interceptor's method invocation**; a transaction may commit at a different point depending on advice ordering.

## 7. `evictFor` and `noEvictFor`: Conditional Eviction by Error Type

**`evictFor`** and **`noEvictFor`** apply only when **`afterInvocation=true`**. JCache rules:

| `evictFor` | `noEvictFor` | When Target Throws an Exception, Which Cases Still Evict? |
| --- | --- | --- |
| Empty | Empty | **No exceptions**; errors preserve the entry |
| Non-empty list | Empty | Only exceptions matching **`evictFor`** |
| Empty | Non-empty list | All exceptions **except** those matching **`noEvictFor`** |
| Both non-empty | Both non-empty | Matches **`evictFor`** and **does not match `noEvictFor`** |

Example evicting when detecting a "record no longer valid" error:

~~~java
@CacheRemove(
    cacheName = "records",
    evictFor = StaleRecordException.class
)
public void verifyAndDelete(@CacheKey String id) {
    repository.verifyAndDelete(id);
}
~~~

This is an illustrative snippet. If `StaleRecordException` is thrown, the interceptor still evicts the entry while **the exception continues propagating to the caller**; evicting does not turn a failed operation into a successful one.

Example blacklisting an error that must not evict:

~~~java
@CacheRemove(
    cacheName = "records",
    noEvictFor = DatabaseUnavailableException.class
)
public void delete(@CacheKey String id) {
    repository.delete(id);
}
~~~

Here, if the method throws `DatabaseUnavailableException`, **no eviction occurs**. Under the rule when only `noEvictFor` is specified, other exceptions outside that denylist **may trigger eviction** even though the method failed. This is easily misunderstood: **`noEvictFor` does not merely add one exception to the default rule**; it defines exclusions from an otherwise permissive error-eviction mode. If you want eviction only on success, keep the default and omit both filters.

### What If an Exception Matches Both Lists?

Suppose `evictFor=RuntimeException.class` and `noEvictFor=TransientFailureException.class`. A `TransientFailureException extends RuntimeException` **does not trigger eviction** because the exclusion list takes precedence. Matching uses subclass/`instanceof` semantics, not strict `Class` equality.

## 8. `@CacheRemoveAll`: Clearing the Entire Cache Without Keys

**`@CacheRemoveAll(cacheName="records")`** has semantics to remove **all entries in the region**, conceptually matching **Spring `@CacheEvict(allEntries=true)`**.

~~~java
@CacheRemoveAll(
    cacheName = "records",
    afterInvocation = true,
    evictFor = CacheRefreshException.class
)
public void rebuildIndex() {
    repository.rebuildIndex();
}
~~~

This is an illustrative snippet. If the method succeeds, the region is cleared; if it throws `CacheRefreshException`, the region is still cleared because of `evictFor`. For any other unmatched exception, the region is not cleared.

- **`afterInvocation=true`**: clears after the method, by default only on success.
- **`afterInvocation=false`**: requests clearing the whole region before the method, regardless of whether the method later succeeds or fails.
- **`evictFor`/`noEvictFor`**: same filter logic as `@CacheRemove`, evaluated only when `afterInvocation=true`.
- `@CacheRemoveAll` has no per-entry key; do not add **`@CacheKey`** expecting it to clear only a subset of entries.
- Clearing an entire region can trigger a **thundering herd** as many concurrent requests reload the cache simultaneously.

**`@CacheRemove(cacheName="recordFailures")`** or **`@CacheRemoveAll(cacheName="recordFailures")`** targets the **exception cache** when you want to invalidate cached exceptions. **Clearing the `"records"` value cache does not automatically clear the `"recordFailures"` exception cache**: they are two separately configured regions.

## 9. JCache `@CachePut`: "Write Timing" Also Depends on Exceptions

In JCache, **`@CachePut`** takes **the value to cache from the `@CacheValue` parameter**, not the return value as Spring `@CachePut` does.

~~~java
@CachePut(cacheName = "records", afterInvocation = true)
public void update(
    @CacheKey String id,
    @CacheValue String nextValue
) {
    repository.save(id, nextValue);
}
~~~

This is illustrative.

**`afterInvocation=true`** (default):
- Method runs first, then `nextValue` is written on success.
- When the method throws an exception, nothing is put by default.
- **`cacheFor`/`noCacheFor`** allow selected exceptions to still perform the put after the method.

**`afterInvocation=false`**:
- The cache is populated **before** the method runs.
- If the method later fails, the value has already been put; **`cacheFor`/`noCacheFor`** filters do not roll it back.
- Never enable this just to update the cache "faster": other readers can observe `nextValue` before the database transaction commits or even after the database update fails.

Error-path filters:

| `cacheFor` | `noCacheFor` | When Method Throws an Exception, Does It Put? |
| --- | --- | --- |
| Empty | Empty | **No** by default |
| Non-empty list | Empty | Only exceptions matching **`cacheFor`** |
| Empty | Non-empty list | All exceptions except those matching **`noCacheFor`** |
| Both non-empty | Both non-empty | Matches `cacheFor` and does not match `noCacheFor` |

**Do not conflate the three filter pairs**:
- `@CacheResult`: **`cachedExceptions`/`nonCachedExceptions`** control caching **exceptions**.
- JCache `@CachePut`: **`cacheFor`/`noCacheFor`** control writing the **`@CacheValue` parameter** after an error.
- `@CacheRemove`/`@CacheRemoveAll`: **`evictFor`/`noEvictFor`** control **eviction** after an error.

All three can mutate cache state when a method throws an exception, yet **what gets mutated is completely different**.

## 10. Side-by-Side Comparison with Spring Annotations

| Scenario | **JCache (`javax.cache.annotation`)** | **Spring Cache Annotation** |
| --- | --- | --- |
| Cache method result | `@CacheResult` | `@Cacheable` |
| Cache selected business exceptions | `@CacheResult(exceptionCacheName, cachedExceptions, nonCachedExceptions)` | `@Cacheable` **has no** such attribute pair |
| Always run method and cache result | `@CacheResult(skipGet=true)` uses return value | Spring `@CachePut` always runs method and caches return value |
| Write parameter value to cache | JCache `@CachePut` with **`@CacheValue`** | Spring `@CachePut` **caches return value**, no `@CacheValue` |
| Write before/after method | JCache `@CachePut(afterInvocation=false/true)` | Spring `@CachePut` normally writes after method |
| Evict a single key | `@CacheRemove` | `@CacheEvict` |
| Clear all entries | `@CacheRemoveAll` | `@CacheEvict(allEntries=true)` |
| Evict before method | `afterInvocation=false` | `beforeInvocation=true` |
| Evict after method | `afterInvocation=true` (default) | `beforeInvocation=false` (default) |
| Evict when method throws selected exceptions | `evictFor`/`noEvictFor` | No equivalent annotation attributes |
| Class-level defaults | `@CacheDefaults` | `@CacheConfig` |
| Select key components | `@CacheKey` on parameter | SpEL `key` / `KeyGenerator` |
| Enable in Spring | `@EnableCaching` + `javax.cache` API + `spring-context-support` | `@EnableCaching` + Spring Cache infrastructure |

**Easily confused names:** JCache **`afterInvocation=false`** corresponds in timing to Spring **`beforeInvocation=true`**. They do not have the same name or the same boolean polarity.

**Important:** JCache API and Spring Cache abstraction can share the same store, yet **default key generation is not automatically compatible**. When mixing both annotation sets in one system, verify `cacheName`, keys, and managers/resolvers together.

## 11. Timelines for Predicting Behavior

### 11.1. `@CacheResult` Caching Exceptions

~~~text
Call 1: find("BAD")
  -> result cache miss
  -> exception cache miss
  -> target runs, throws InvalidIdException
  -> filter permits -> stores exception at recordFailures[generatedKey]
  -> caller receives InvalidIdException

Call 2: find("BAD")
  -> interceptor finds cached exception
  -> target DOES NOT run
  -> caller still receives InvalidIdException
~~~

Looking only at external error logs, you might assume both calls hit the database. In reality, **the cache may be actively replaying the error**. To verify, measure method invocation counts, inspect the exception cache, or test invalidating that exact key.

### 11.2. Default `@CacheRemove` on Failure

~~~text
Value cache currently holds records[K] = v1

remove(K) invokes target
  -> target throws IllegalStateException
  -> afterInvocation=true, evictFor/noEvictFor empty
  -> no eviction

Next get(K) -> still HITS v1
~~~

Keeping the entry may be right if the update/delete truly rolled back, or wrong if the source was partially mutated before the exception. The annotation itself has no awareness of whether your operation is transactional.

### 11.3. `@CacheRemove(evictFor=...)` on Failure

~~~text
Value cache currently holds records[K] = v1

remove(K) invokes target
  -> throws IllegalStateException
  -> exception matches evictFor
  -> evicts records[K] despite method failure
  -> exception is still rethrown to caller

Next get(K) -> MISSES, executes fresh target read
~~~

### 11.4. `@CacheRemove(afterInvocation=false)` on Failure

~~~text
Value cache holds records[K] = v1

interceptor requests eviction of records[K] FIRST
target starts delete(K)
target throws exception
caller sees exception, yet the cache entry has already been evicted
~~~

Note that **pre-eviction** does not guarantee the database reflects the new state. Another reader may miss while the delete is failing and reload the old data.

## 12. Runnable Java 17 + Maven Example with Spring Framework

The demo uses **Spring `ConcurrentMapCacheManager`** for both **`records`** and **`recordFailures`** regions. Business data is simulated with counters and strings, needing no database or native JCache provider. It clearly demonstrates:
1. Results are cached on success.
2. `InvalidIdException` is cached and replayed; `TemporaryFailure` is not cached.
3. Evicting **only the exception cache** causes the failing method to execute again.
4. Default `@CacheRemove` **retains the entry on error**, `evictFor` forces **eviction despite error**, and `afterInvocation=false` **evicts before the method**.
5. Default JCache `@CachePut` **does not write on error**, `cacheFor` can **write despite error**, and `afterInvocation=false` **writes before the method**.
6. `@CacheRemoveAll` follows the same error-filter rules when clearing the region and **does not automatically clear the separate exception cache**.

### 12.1. Directory Structure

~~~text
spring-jcache-exception-demo/
├── pom.xml
└── src/main/java/demo/JCacheExceptionDemo.java
~~~

### 12.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-jcache-exception-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
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

**There is no native JCache provider in `pom.xml`** because Spring's JCache interceptor uses Spring's `CacheManager` to process the annotations. If you want a **`javax.cache.CacheManager`** and a concrete JCache provider, add that provider's dependencies and configuration rather than swapping `CacheManager` arbitrarily in the demo.

### 12.3. `src/main/java/demo/JCacheExceptionDemo.java`

~~~java
package demo;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.atomic.AtomicInteger;

public class JCacheExceptionDemo {

    public static final class InvalidIdException
            extends IllegalArgumentException {
        public InvalidIdException() {
            super("invalid id");
        }
    }

    public static final class TemporaryFailure
            extends IllegalStateException {
        public TemporaryFailure() {
            super("temporary failure");
        }
    }

    public static class RecordService {
        private final AtomicInteger loads = new AtomicInteger();

        @CacheResult(
            cacheName = "records",
            exceptionCacheName = "recordFailures",
            cachedExceptions = InvalidIdException.class,
            nonCachedExceptions = TemporaryFailure.class
        )
        public String find(@CacheKey String id) {
            int run = loads.incrementAndGet();
            if ("BAD".equals(id)) {
                throw new InvalidIdException();
            }
            if ("TEMP".equals(id)) {
                throw new TemporaryFailure();
            }
            return "load-" + run;
        }

        public int loadCount() {
            return loads.get();
        }

        // Evict only the cached exception for the same generated key.
        @CacheRemove(cacheName = "recordFailures")
        public void invalidateFailure(@CacheKey String id) {
        }

        // Error => by default, do NOT evict the cache entry.
        @CacheRemove(cacheName = "records")
        public void failDefaultRemove(@CacheKey String id) {
            throw new IllegalStateException("delete failed");
        }

        // Error matches evictFor => still evict after the method.
        @CacheRemove(
            cacheName = "records",
            evictFor = IllegalStateException.class
        )
        public void failButRemove(@CacheKey String id) {
            throw new IllegalStateException("forced remove");
        }

        // Evict before method => evict even though target throws an exception.
        @CacheRemove(
            cacheName = "records",
            afterInvocation = false
        )
        public void removeBeforeFailure(@CacheKey String id) {
            throw new IllegalStateException("failed later");
        }

        // JCache @CachePut takes the value from the @CacheValue parameter.
        @CachePut(cacheName = "records")
        public void putDefaultFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("put failed");
        }

        @CachePut(
            cacheName = "records",
            cacheFor = IllegalStateException.class
        )
        public void putEvenIfFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("put despite failure");
        }

        @CachePut(
            cacheName = "records",
            afterInvocation = false
        )
        public void putBeforeFailure(
                @CacheKey String id, @CacheValue String value) {
            throw new IllegalStateException("failed after put");
        }

        @CacheRemoveAll(cacheName = "records")
        public void clearDefaultFailure() {
            throw new IllegalStateException("clear failed");
        }

        @CacheRemoveAll(
            cacheName = "records",
            evictFor = IllegalStateException.class
        )
        public void clearEvenIfFailure() {
            throw new IllegalStateException("clear despite failure");
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "records", "recordFailures");
        }

        @Bean
        public RecordService recordService() {
            return new RecordService();
        }
    }

    @FunctionalInterface
    public interface Operation {
        void run();
    }

    private static String errorName(Operation action) {
        try {
            action.run();
            return "NONE";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            RecordService service = ctx.getBean(RecordService.class);

            System.out.println("ok1=" + service.find("OK"));
            System.out.println("ok2=" + service.find("OK"));
            System.out.println("loads-after-ok="
                + service.loadCount());

            System.out.println("bad1="
                + errorName(() -> service.find("BAD")));
            System.out.println("bad2="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-after-bad="
                + service.loadCount());

            System.out.println("temp1="
                + errorName(() -> service.find("TEMP")));
            System.out.println("temp2="
                + errorName(() -> service.find("TEMP")));
            System.out.println("loads-after-temp="
                + service.loadCount());

            service.invalidateFailure("BAD");
            System.out.println("bad-after-evict="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-after-bad-evict="
                + service.loadCount());

            System.out.println("remove-default="
                + errorName(() -> service.failDefaultRemove("OK")));
            System.out.println("ok-retained="
                + service.find("OK"));

            System.out.println("remove-on-error="
                + errorName(() -> service.failButRemove("OK")));
            System.out.println("ok-reloaded="
                + service.find("OK"));

            System.out.println("remove-before="
                + errorName(() ->
                    service.removeBeforeFailure("OK")));
            System.out.println("ok-after-early-remove="
                + service.find("OK"));

            System.out.println("put-default="
                + errorName(() ->
                    service.putDefaultFailure("P", "P-CACHED")));
            System.out.println("p-after-failed-put="
                + service.find("P"));

            System.out.println("put-on-error="
                + errorName(() ->
                    service.putEvenIfFailure("P", "P-FORCED")));
            System.out.println("p-after-forced-put="
                + service.find("P"));

            System.out.println("put-before="
                + errorName(() ->
                    service.putBeforeFailure("Q", "Q-EARLY")));
            System.out.println("q-after-early-put="
                + service.find("Q"));

            System.out.println("clear-default="
                + errorName(service::clearDefaultFailure));
            System.out.println("p-retained-after-clear-failure="
                + service.find("P"));

            System.out.println("clear-on-error="
                + errorName(service::clearEvenIfFailure));
            System.out.println("p-after-clear="
                + service.find("P"));
            System.out.println("bad-still-cached="
                + errorName(() -> service.find("BAD")));
            System.out.println("loads-total="
                + service.loadCount());
        }
    }
}
~~~

**Why Spring can intercept the demo:** `RecordService` is a context-managed bean, every call in `main` goes through **`ctx.getBean(RecordService.class)`**, and methods are `public` and non-`final`; `@EnableCaching` activates JCache support when `cache-api` + `spring-context-support` are present. There is no self-invocation and no direct `new RecordService()` bypassing Spring.

**Why keys match across `find` and write/evict methods:** every operation selects **the exact `id`** using `@CacheKey`; `@CacheValue` does not enter the generated key. Parameters used only to trigger exceptions were avoided in the demo by splitting separate operation methods so keys would not diverge accidentally.

### 12.4. Compiling and Running

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JCacheExceptionDemo
~~~

**Expected stdout from `System.out.println`**, excluding Maven/library logs:

~~~text
ok1=load-1
ok2=load-1
loads-after-ok=1
bad1=InvalidIdException
bad2=InvalidIdException
loads-after-bad=2
temp1=TemporaryFailure
temp2=TemporaryFailure
loads-after-temp=4
bad-after-evict=InvalidIdException
loads-after-bad-evict=5
remove-default=IllegalStateException
ok-retained=load-1
remove-on-error=IllegalStateException
ok-reloaded=load-6
remove-before=IllegalStateException
ok-after-early-remove=load-7
put-default=IllegalStateException
p-after-failed-put=load-8
put-on-error=IllegalStateException
p-after-forced-put=P-FORCED
put-before=IllegalStateException
q-after-early-put=Q-EARLY
clear-default=IllegalStateException
p-retained-after-clear-failure=P-FORCED
clear-on-error=IllegalStateException
p-after-clear=load-9
bad-still-cached=InvalidIdException
loads-total=9
~~~

### 12.5. Explanation of Each Output Group

**Group 1 – Result and exception caching:**
- **`ok1`/`ok2`** are both `load-1`: the result for `"OK"` is cached after the first call, skipping the real method on the second call.
- **`bad1`/`bad2`** are both `InvalidIdException`, yet **`loads-after-bad=2`**: only one new execution occurred for `"BAD"`; the second error was served from **`recordFailures`** without calling the target method.
- **`temp1`/`temp2`** are both `TemporaryFailure` and **`loads-after-temp=4`**: `"TEMP"` runs the target method both times because the exception **does not match `cachedExceptions`** and is also excluded by `nonCachedExceptions`.
- **`invalidateFailure("BAD")`** clears only the exception cache; **`bad-after-evict`** forces `"BAD"` to run again, incrementing the count to 5 and caching a fresh exception.

**Group 2 – Eviction timing:**
- **`failDefaultRemove("OK")`** throws `IllegalStateException`, so default `afterInvocation=true` **does not evict**; `find("OK")` still reads cached `load-1`.
- **`failButRemove("OK")`** throws `IllegalStateException` matching **`evictFor`**, so it still evicts; `find("OK")` runs fresh as `load-6`.
- **`removeBeforeFailure("OK")`** evicts before the target runs; even though the target throws an error, `find("OK")` runs fresh as `load-7`.

**Group 3 – JCache `@CachePut`:**
- **`putDefaultFailure("P","P-CACHED")`** fails so nothing is put; `find("P")` loads fresh as `load-8`.
- **`putEvenIfFailure("P","P-FORCED")`** fails with an error matching **`cacheFor`**, so the **`@CacheValue`** parameter `P-FORCED` is put despite method failure.
- **`putBeforeFailure("Q","Q-EARLY")`** puts before the method runs; the subsequent error does not cancel the entry; `find("Q")` receives `Q-EARLY` without incrementing the load counter.

**Group 4 – Clearing the whole cache and independence of the exception cache:**
- **`clearDefaultFailure()`** fails under defaults so **`records` is not cleared**; `P-FORCED` remains in cache.
- **`clearEvenIfFailure()`** fails with an error matching `evictFor` so **`records` is cleared**; `find("P")` must load fresh as `load-9`.
- **`bad-still-cached`** still returns `InvalidIdException` from the exception cache because clearing targeted **`records`**, not **`recordFailures`**; total target `find` executions remain 9.

**Limitations:** this example targets Spring's JCache interceptor using `ConcurrentMapCacheManager`, running sequentially in a single process for deterministic stdout. It does not illustrate TTL, database transactions, distributed caches, serialization, or race conditions. Other cache providers may differ in visibility and exception serialization details; verify on your actual provider.

## 13. Caution: Exception Cache and Result Cache Have Separate Lifecycles

A stable cached exception today **is not guaranteed to stay valid forever**. Examples:
- A user ID did not exist yet, then is created.
- A feature flag or validation policy changes.
- A previously invalid order code becomes valid after deployment.
- Caller or tenant permissions change.
- An upstream bug is fixed while the cache still holds the old exception.

As long as the system finds a cached exception at that key, the target method **never gets a chance to evaluate the new reality**. Choose:
1. **A TTL for the exception cache**, typically short and matched to risk.
2. **Invalidation on the exact exception cache** when underlying state changes.
3. **Version/tenant/locale/permission context in the key** whenever they affect error outcomes.
4. **Never cache transient errors** (network timeouts, temporary rate limits, service overload).
5. **Monitor cached exception hit rates** so you never confuse "low method execution because the service is healthy" with "errors being replayed".

**Do not confuse exception caching with negative caching of `null`.** `@CacheResult` defaults to caching nulls (`cacheNull`), though whether `null` is stored by the provider and distinguished from a miss depends on the cache implementation. Exception caching is a separate mechanism from storing a `null` result value.

### Exceptions You Should Not Cache Indiscriminately

- **`SecurityException` / `AccessDeniedException`** can depend on caller, role, and token.
- **`TemporaryFailure` / upstream `IOException`** require controlled retry paths.
- **`IllegalStateException` carrying request state** may be valid only at a specific instant.
- **Exceptions containing request bodies, credentials, or PII** must never enter a shared cache.

If an error only holds for `(tenantId, userId, resourceId, policyVersion)`, a key containing only `resourceId` can replay the wrong error to another user. For authorization logic, prefer checking the authoritative source rather than casually caching exception outcomes.

## 14. Eviction Time Is Not Commit Time

In systems combining **`@Transactional`** and cache annotations on the same method, distinguish three milestones:

~~~text
Business method runs
  -> database changes inside transaction
  -> method returns or throws
  -> transaction commits or rolls back
  -> cache put/remove becomes observable
~~~

The actual sequence of these milestones **depends on advice ordering, transaction-aware `CacheManager`, and the provider**. **`afterInvocation=true`** does not automatically mean **"after successful commit"**. If a method returns normally inside transaction advice whose commit subsequently fails, uncoordinated cache operations may have already happened unexpectedly.

### Two Classic Bugs

**Evicting too early:**

~~~text
Writer updates DB inside transaction but has not committed yet
Cache entry is already evicted
Another reader gets a cache MISS, reads old DB version due to isolation
Reader puts stale data back into cache
Writer commits
Cache can still hold the stale snapshot
~~~

**Eviction runs, yet an older loader finishes afterward:**

~~~text
Reader R gets cache MISS, captures snapshot v1
Writer W updates DB to v2 and evicts
Reader R finishes, puts v1 after eviction
Cache contains stale data again
~~~

Thus `afterInvocation=true/false` and `evictFor`/`noEvictFor` answer **when eviction is requested relative to a single method**, not the entire cross-request consistency problem.

### Designing for Transactions

Consider transaction-aware cache operations, post-commit invalidation, outbox events, versioned keys, version checks/CAS, or per-key coordination matching your consistency needs. Every approach has trade-offs; no single annotation creates an atomic transaction across database and cache.

If a method mutates partial state and throws while the transaction rolls back, **`evictFor`** may cause unnecessary misses. If a method commits partially outside a transaction before throwing, **keeping the cache by default** may serve stale data. Base your choice on the **business semantics of the error**, not just the exception class name.

## 15. Common Pitfalls

### 15.1. Confusing `exceptionCacheName` with `cacheName`

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures",
    cachedExceptions = InvalidIdException.class
)
~~~

**`records`** holds successful results; **`recordFailures`** holds exceptions. Clearing `records` does not clear `recordFailures`. If you fix an underlying bug and users still see the old exception, check the **exception cache**, not just the result cache.

### 15.2. Forgetting `exceptionCacheName`

~~~java
@CacheResult(
    cacheName = "records",
    cachedExceptions = IllegalArgumentException.class
)
~~~

Even with a whitelist, because **`exceptionCacheName` is unconfigured**, do not expect exceptions to be cached. An exception cache name and a resolvable region are required.

### 15.3. Setting Only `exceptionCacheName` and Accidentally Caching All Errors

~~~java
@CacheResult(
    cacheName = "records",
    exceptionCacheName = "recordFailures"
)
~~~

When the exception cache is enabled and both filters are empty, JCache rules can cache **every target exception**. Whitelist stable errors explicitly via `cachedExceptions` rather than leaving this default open.

### 15.4. Thinking `afterInvocation=false` Means "Evict After Method"

In JCache, **`false` means evict before**; in Spring `@CacheEvict`, **`beforeInvocation=false` means evict after**. The two attributes have different names and opposite boolean directions.

### 15.5. Using `evictFor` Together with `afterInvocation=false`

When evicting beforehand, method exception filters **have no exception to inspect**. `evictFor`/`noEvictFor` are meaningful only on the **`afterInvocation=true`** branch.

### 15.6. Assuming `evictFor` Turns a Failing Method into a Success

`evictFor` only decides whether the cache entry is removed when the method throws. The exception **still propagates to the caller**; transactions and HTTP responses do not become successful.

### 15.7. Assuming `@CacheRemoveAll` Clears Every Region

`@CacheRemoveAll(cacheName="records")` targets only **`records`**. The `recordFailures` exception cache is a separate region. To clear both, define invalidation for both, verify ownership, and avoid overly broad clears that cause heavy reload spikes.

### 15.8. Importing the Wrong `@CachePut`

~~~java
// JCache: uses @CacheValue from javax.cache.annotation.
@CachePut(cacheName = "records", afterInvocation = false)
public void save(@CacheKey String id, @CacheValue String value) {
    // ...
}
~~~

If your IDE picks Spring `@CachePut`, attributes like `cacheName`/`afterInvocation` and JCache `@CacheValue` **are not part of Spring `@CachePut`'s API**.

### 15.9. Misusing JCache `@CacheKey` and Failing to Evict Entries

If `@CacheResult` marks `id` with `@CacheKey` while `@CacheRemove` uses a different key parameter set, the two operations can produce **two different generated keys**. Even with the same `cacheName`, eviction will miss. Verify key generators, `@CacheKey` lists, parameter types, tenant/namespace, and equality.

### 15.10. Caching Context-Dependent Exceptions

When an error depends on user, tenant, or permissions while the key omits those factors, the system can replay one caller's cached exception to another caller. Never cache authorization failures under a shared context-free key; in most cases, avoid caching them altogether.

### 15.11. Missing Proxy Interception

Java annotations do not run on their own. You need Spring `@EnableCaching`, the JCache API, and `spring-context-support`; methods must be called **through the Spring bean proxy**. Self-invocation in proxy mode can skip both exception caching and eviction.

### 15.12. Equating `CacheException` with Business Exceptions

**`javax.cache.CacheException`** is a Cache API/provider failure. Configuring business exception caching on `@CacheResult` does not swallow Redis connection errors or serialization failures. When debugging, distinguish target method exceptions from cache implementation exceptions.

## 16. Integration Testing Checklist

| Test | Setup | Verification Target |
| --- | --- | --- |
| Result hit | Call `@CacheResult` twice with the same key | Real method runs once; result is reused |
| Exception cache hit | Error in `cachedExceptions`, valid `exceptionCacheName` | Second call throws the error **without** running target |
| Excluded exception | Error in `nonCachedExceptions` | Both calls run target; exception is not cached |
| Only `exceptionCacheName` | Both filters empty | Verify awareness that all errors may be cached by default |
| Missing `exceptionCacheName` | Only `cachedExceptions` declared | Verify no exception caching occurs |
| `skipGet` | Enable `skipGet=true` | Skips pre-lookup of results/exceptions; target always runs |
| Evict on success | Default `@CacheRemove` | Entry is evicted after method |
| Default evict on failure | Method throws error, empty filters | Entry remains intact |
| Evict on failure matching `evictFor` | `afterInvocation=true` | Entry is evicted despite error |
| Skip evict matching `noEvictFor` | `afterInvocation=true` | Entry is not evicted |
| Early eviction | `afterInvocation=false` | Evicts before method regardless of subsequent exception |
| Default `RemoveAll` on failure | Method throws error | Region is not cleared |
| `RemoveAll` with `evictFor` | Method throws matching error | Region is cleared |
| Default `Put` on failure | JCache `@CachePut` `afterInvocation=true` | Does not write `@CacheValue` |
| `Put` matching `cacheFor` | JCache `@CachePut` `afterInvocation=true` | Writes `@CacheValue` despite error |
| Put before method | `afterInvocation=false` | Entry may be written even if method fails afterward |
| Exception cache lifecycle | Evict result cache without evicting exception cache | Cached exception may still replay |
| Transaction boundaries | Test rollback/commit and cache events | Verify actual timing instead of guessing from annotations |
| Concurrent readers | Reader loading concurrently during eviction | Test stale repopulation and mitigation strategy |
| Multi-instance/provider | Production provider, multiple nodes | Test TTL, serialization, visibility, and invalidation |

**Prefer integration tests with a Spring `ApplicationContext`** to confirm annotations are intercepted rather than unit tests calling the target object directly. With JCache, configure exact cache names and test both the **data region** and **exception region**. Use real method invocation counters in tests to detect when exceptions are being replayed.

## 17. Practice Exercises and Self-Check Questions

**Question 1.** `@CacheResult(cacheName="a", exceptionCacheName="b")` has both `cachedExceptions` and `nonCachedExceptions` empty. Can target exceptions be cached?

**Answer:** Yes. Once the exception cache is enabled and both filters are empty, JCache rules allow caching all target exceptions per configuration.

**Question 2.** `@CacheResult` sets `cachedExceptions=InvalidIdException.class` without setting `exceptionCacheName`. Will errors be cached?

**Answer:** Not automatically. `exceptionCacheName` is required to specify a dedicated cache for exceptions.

**Question 3.** `cachedExceptions=RuntimeException.class`, `nonCachedExceptions=TimeoutException.class`, and `TimeoutException extends RuntimeException`. Is `TimeoutException` cached?

**Answer:** No; it falls under the exclusion filter. Any exception caching also requires `exceptionCacheName`.

**Question 4.** Default JCache `@CacheRemove(afterInvocation=true)` encounters an exception inside the method. Does it evict?

**Answer:** No. By default, when a method throws an exception, eviction does not happen; configure `evictFor`/`noEvictFor` if needed.

**Question 5.** JCache `@CacheRemove(afterInvocation=false, evictFor=IllegalStateException.class)` runs and then the method throws `IOException`. Does eviction occur?

**Answer:** Eviction may have already occurred before the method ran; `evictFor` is not evaluated because `afterInvocation=false`. When the cache provider makes the deletion effective depends on the implementation.

**Question 6.** JCache `@CacheRemove(evictFor=RuntimeException.class, noEvictFor=TemporaryFailure.class)` throws `TemporaryFailure extends RuntimeException`. Does it evict?

**Answer:** No, because `noEvictFor` excludes that exception type.

**Question 7.** Which JCache setting corresponds to Spring `@CacheEvict(beforeInvocation=true)`?

**Answer:** **`@CacheRemove(afterInvocation=false)`** regarding eviction timing. The two annotations are not completely equivalent in exception-filtering capabilities.

**Question 8.** Where does JCache `@CachePut(afterInvocation=true)` obtain the value to write?

**Answer:** From **the parameter annotated with `@CacheValue`**, unlike Spring `@CachePut` which takes **the method return value**.

**Question 9.** When JCache `@CachePut` has `cacheFor=IllegalStateException.class` and the method throws `IllegalStateException`, does the method succeed?

**Answer:** No. The method still throws the error; `cacheFor` only permits writing `@CacheValue` despite invocation failure.

**Question 10.** Does clearing the data cache also clear cached exceptions for the same key?

**Answer:** No. They are two independent cache regions; handle `exceptionCacheName` explicitly, use TTL, or use versioned keys.

**Question 11.** Does `@CacheResult(skipGet=true)` still cache new exceptions after invocation?

**Answer:** Yes, if `exceptionCacheName` and the filters permit it. `skipGet` only skips the pre-invocation lookup.

**Question 12.** Why does `afterInvocation=true` not prove eviction happens after commit?

**Answer:** Because the method invocation boundary and the database transaction commit boundary can differ due to advice/provider ordering; test directly or use explicit post-commit coordination.

## Summary

- JCache **`@CacheResult`** can store **selected business exceptions** in a separate **`exceptionCacheName`**; without `exceptionCacheName`, no exception caching occurs. When exception caching is enabled with both filters empty, JCache rules can cache **all exceptions**.
- **`cachedExceptions`/`nonCachedExceptions`** filter **caching `Throwable`s**; `@CacheRemove`/`@CacheRemoveAll`'s **`evictFor`/`noEvictFor`** filter **eviction on error**; JCache `@CachePut`'s **`cacheFor`/`noCacheFor`** filter **writing `@CacheValue` on error**.
- JCache **`afterInvocation=true`** (default) requests eviction/writes after the method and skips on exception by default; filters can override error behavior. **`afterInvocation=false`** executes the cache operation before invocation, where error filters do not apply.
- Spring **`@CacheEvict(beforeInvocation=true)`** aligns in timing direction with JCache **`@CacheRemove(afterInvocation=false)`**, but Spring's annotation **lacks** `evictFor`/`noEvictFor`.
- Exception caches and result caches have **independent lifecycles**. Clearing one does not clear the other; always account for keys, TTL, invalidation, transactions, and race conditions before deploying to production.

### References

- Spring Framework 6.2 – JCache (JSR-107) annotations and differences from Spring annotations: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/jsr-107.html
- Spring Framework 6.2 – Spring `@CacheEvict` and `beforeInvocation`: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- JSR-107 `CacheResult` Javadoc 1.1.1 (`exceptionCacheName`, `cachedExceptions`, `nonCachedExceptions`, `skipGet`): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheResult.html
- JSR-107 `CacheRemove` Javadoc 1.1.1 (`afterInvocation`, `evictFor`, `noEvictFor`): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemove.html
- JSR-107 `CacheRemoveAll` Javadoc 1.1.1: https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemoveAll.html
- JSR-107 `CachePut` Javadoc 1.1.1 (`CacheValue`, `afterInvocation`, `cacheFor`, `noCacheFor`): https://javadoc.io/doc/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html
- Spring Framework – `DefaultJCacheOperationSource` and Spring `CacheManager` support: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/jcache/interceptor/DefaultJCacheOperationSource.html
