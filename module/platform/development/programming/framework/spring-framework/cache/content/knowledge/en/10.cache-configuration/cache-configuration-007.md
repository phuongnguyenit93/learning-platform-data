# `CachingConfigurer`: Configuring CacheManager, CacheResolver, KeyGenerator, and CacheErrorHandler

## 1. What Problem Does `CachingConfigurer` Solve?

Spring Cache provides annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`. Annotations describe **when** to read/write/delete from a cache, yet the application must also decide **where caches live**, **which cache is selected**, **what key is used for lookup**, and **how cache backend errors are handled**.

The `org.springframework.cache.annotation.CachingConfigurer` interface is the place to configure defaults for cache annotation processing when `@EnableCaching` is active. A `@Configuration` class can `implements CachingConfigurer` and override four methods:

| `CachingConfigurer` Method | Return Type | Responsibility |
| --- | --- | --- |
| `cacheManager()` | `CacheManager` | Manages/returns cache regions by name, backing the default resolver. |
| `cacheResolver()` | `CacheResolver` | Selects one or more `Cache` objects **per operation** based on annotation and invocation context. |
| `keyGenerator()` | `KeyGenerator` | Generates keys from target object, method, and arguments when the annotation lacks an explicit `key` expression. |
| `errorHandler()` | `CacheErrorHandler` | Handles exceptions thrown by `Cache.get`, `put`, `evict`, or `clear` operations. |

In Spring Framework 6.x, these methods have default implementations so you can override only what you need to customize. When not explicitly provided, typical defaults are a manager-backed `SimpleCacheResolver`, `SimpleKeyGenerator`, and `SimpleCacheErrorHandler` (which rethrows cache errors).

**Relationship between components:**

~~~text
Call through Spring proxy
          |
          v
@Cacheable / @CachePut / @CacheEvict
          |
          +--> CacheResolver --> selects Cache(s)
          |         |
          |         +--> may obtain Cache from CacheManager
          |
          +--> KeyGenerator --> generates key (if no SpEL key)
          |
          v
Read/write/evict in Cache
          |
          +--> if cache backend throws RuntimeException
                    |
                    v
                CacheErrorHandler
                (rethrows or handles per policy)
~~~

`CacheManager`, `CacheResolver`, `KeyGenerator`, and `CacheErrorHandler` address **four distinct responsibilities**. Adding `CachingConfigurer` will not make caching work unless annotation processing is enabled (`@EnableCaching` or equivalent configuration) and calls pass through an appropriate interception mechanism.

## 2. `cacheManager()`: Declaring Where Caches Are Stored

`CacheManager` is an interface with essential operations like `getCache(String name)` and `getCacheNames()`. It manages `Cache` instances rather than directly deciding the key for an invocation.

Basic example:

~~~java
@Configuration
@EnableCaching
class CacheConfig implements CachingConfigurer {
    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

This is a **configuration snippet**: when placed in a Java file, import `Configuration`, `EnableCaching`, `CachingConfigurer`, `Bean`, `CacheManager`, and `ConcurrentMapCacheManager` from Spring. A complete runnable program is in section 6.

- `books` and `authors` are **cache region names**, not keys of individual items.
- `ConcurrentMapCacheManager` keeps caches in process memory, convenient for examples/simple apps. It does not automatically provide TTL or multi-instance synchronization.
- In a real application, use a manager for Caffeine, Redis, or another provider for TTL, capacity limits, distributed support, and dedicated policies.
- `@Bean` on `cacheManager()` is important so Spring manages the bean and its lifecycle. Creating an unmanaged object ad hoc makes configuration hard to verify.

If you **only** provide `cacheManager()`, Spring can build a default resolver backed by this manager. An annotation like `@Cacheable(cacheNames = "books")` is then resolved to the cache named `books` from that manager.

`CacheManager` **does not pick keys** and does not replace `KeyGenerator`: those are two separate concerns.

## 3. `cacheResolver()`: Selecting Caches by Operation and Context

`CacheResolver` determines which `Cache` instances must be used for a `@Cacheable`, `@CachePut`, or `@CacheEvict`. The interface's main method is:

~~~java
Collection<? extends Cache> resolveCaches(
        CacheOperationInvocationContext<?> context);
~~~

This is an **illustrative API signature**, not a standalone program. `context` provides metadata for the cache operation, method, target, and arguments. `SimpleCacheResolver` uses a `CacheManager` and the annotation's cache names to return `Cache` objects.

**Important precedence rule:** If the same `CachingConfigurer` provides both `cacheManager()` and `cacheResolver()`, the resolver is chosen as the **default resolution mechanism** for annotations; the manager is not automatically used to build a second resolver. Of course, a custom resolver may **explicitly use the manager** as its cache source.

A simple resolver example:

~~~java
@Bean
@Override
public CacheResolver cacheResolver() {
    return new SimpleCacheResolver(cacheManager());
}
~~~

The snippet above assumes it lives in a `@Configuration` class providing `cacheManager()` as a `@Bean`. With default `@Configuration` settings (bean-method proxying enabled), calling `cacheManager()` inside the same class returns the Spring-managed bean. If you explicitly set `proxyBeanMethods = false`, do not rely on this bean-method call; pass the bean explicitly instead.

When is a custom resolver needed?

- Multiple cache backends: routing by tenant, geographic region, data type, or security requirements.
- Cache names that must be determined at runtime based on invocation metadata.
- An operation that needs to access a dynamically computed set of caches rather than static `cacheNames`.

If there is only one manager and cache names are already stated in annotations, **`SimpleCacheResolver` is usually sufficient**. Do not write a custom resolver class when there is no concrete selection rule. The resolver must return appropriate caches; returning no caches or wrong names is a configuration error for operations requiring caching.

### 3.1. Avoid confusing `cacheResolver` and `cacheManager` in annotations

Attributes on **a single operation** have constraints:

~~~java
@Cacheable(cacheNames = "books", cacheManager = "fastManager")
public Book find(String id) { /* ... */ }
~~~

or:

~~~java
@Cacheable(cacheNames = "books", cacheResolver = "tenantCacheResolver")
public Book find(String id) { /* ... */ }
~~~

The two standalone snippets above illustrate configuration choices. Do not declare **both** `cacheManager="fastManager"` and `cacheResolver="tenantCacheResolver"` on the same operation: these are mutually exclusive ways to pick caches, and Spring reports a configuration error.

Precedence is typically understood as: configuration **on the method** takes precedence over `@CacheConfig` **on the class**, and class-level configuration takes precedence over **global** defaults from `CachingConfigurer`. This allows shared defaults with intentional exceptions.

## 4. `keyGenerator()`: Generating Consistent Keys

After determining the cache, Spring needs a key to read or store each entry. When an annotation does not specify `key = "..."` or a dedicated `keyGenerator = "..."`, the framework uses the default key generator.

`KeyGenerator` has the signature:

~~~java
Object generate(Object target, Method method, Object... params);
~~~

`SimpleKeyGenerator` typically produces:

| Input | Default Key |
| --- | --- |
| No arguments | `SimpleKey.EMPTY` |
| One non-null, non-array argument | That argument itself |
| Multiple arguments, one null argument, or an array argument | A `SimpleKey` object wrapping the parameters |

These rules apply at the Spring layer and may be stored by the backend under different key/serialization formats. Keys must have `equals`/`hashCode` suitable for the cache in use and should remain stable across equivalent invocations.

When you need to distinguish two methods with identical parameters sharing a cache region, a custom generator can be declared:

~~~java
@Bean
@Override
public KeyGenerator keyGenerator() {
    return (target, method, params) -> {
        String suffix = Arrays.stream(params)
                .map(String::valueOf)
                .collect(Collectors.joining(":"));
        return method.getName() + ":" + suffix;
    };
}
~~~

This is a **snippet inside `CachingConfigurer`**, requiring Java's `Arrays` and `Collectors` imports. This example yields key `"find:B42"` for `find("B42")`, but **is not suitable verbatim for general data**: overloading, parameters containing `:`, objects with mutable `toString()`, sensitive data, and method renames can cause collisions or key changes. In real systems, define a clear key contract, test for collisions, and verify serialization.

**Note:** `keyGenerator()` is a **default**, so if an annotation specifies `key="#p0"`, that SpEL expression takes precedence. You must not declare both `key` and `keyGenerator` on the same cache annotation, as these two key-generation mechanisms are mutually exclusive.

When `@CacheEvict` uses a custom generator, ensure the evicted key **matches the key used by the read method**. A generator based on `method.getName()` can make `find("B42")` produce `find:B42` while `update("B42")` evicts `update:B42`, leaving stale data behind. Use a unified SpEL key or a generator with consistent rules across operations on the same entity.

## 5. `errorHandler()`: When the Cache Backend Throws Errors

`CacheErrorHandler` receives exceptions from **cache operations** (read/write/evict/clear failures) and lets you choose how to respond. Its four callbacks are:

| Callback | When Called |
| --- | --- |
| `handleCacheGetError(RuntimeException ex, Cache cache, Object key)` | Failure reading a key. |
| `handleCachePutError(RuntimeException ex, Cache cache, Object key, Object value)` | Failure writing a key/value. |
| `handleCacheEvictError(RuntimeException ex, Cache cache, Object key)` | Failure evicting a key. |
| `handleCacheClearError(RuntimeException ex, Cache cache)` | Failure clearing the entire cache. |

With the default `SimpleCacheErrorHandler`, exceptions are **rethrown** to the caller; a Redis/cache backend failure can fail the entire business call:

~~~java
@Bean
@Override
public CacheErrorHandler errorHandler() {
    return new SimpleCacheErrorHandler();
}
~~~

This *fail-fast* behavior is appropriate when consistency is critical or the application needs to know the cache backend is failing.

Another option is to **ignore cache read errors** to fall back to the underlying data source. The following snippet only replaces the body of `errorHandler()` in the configuration class:

~~~java
@Bean
@Override
public CacheErrorHandler errorHandler() {
    return new SimpleCacheErrorHandler() {
        @Override
        public void handleCacheGetError(RuntimeException ex,
                                        Cache cache, Object key) {
            System.err.println("Cache GET failed: "
                    + cache.getName() + ", key=" + key);
            // Do not rethrow: Spring can treat it as a cache miss.
        }
    };
}
~~~

When the handler allows continuing after a `get` error, the method body can run to fetch the result from the source. However, `put` errors will still be rethrown by the remaining methods of `SimpleCacheErrorHandler` if not overridden. Ignoring `evict`/`clear` errors is riskier because **stale entries can persist**; never swallow all exceptions by default out of convenience.

`CacheErrorHandler` **is not** an exception-handling mechanism for the business method body, nor a fix for invalid SpEL keys, unresolvable cache names, or transaction rollbacks. Specific cases require observing error rates, latency, freshness, and fallback needs. In distributed systems, a "cache down yet app keeps running" policy must be tested and monitored.

## 6. Complete Spring Boot 3.3 / Java 17 Example: Configuring All Four Hooks

We use `ConcurrentMapCacheManager` to avoid depending on Redis or Docker. The demo intentionally provides both a manager and a resolver: **the resolver is the entry point** for cache selection and uses the created manager internally. The generator prints keys for visibility, while the handler uses the default error-rethrowing mode.

Create a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Create `src/main/java/demo/CachingConfigurerDemoApplication.java`:

~~~java
package demo;

import java.util.Arrays;
import java.util.stream.Collectors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.cache.interceptor.SimpleCacheErrorHandler;
import org.springframework.cache.interceptor.SimpleCacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CachingConfigurerDemoApplication implements CachingConfigurer {
    public static void main(String[] args) {
        SpringApplication.run(CachingConfigurerDemoApplication.class, args);
    }

    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean
    @Override
    public CacheResolver cacheResolver() {
        CacheResolver delegate = new SimpleCacheResolver(cacheManager());
        return context -> {
            System.out.println("RESOLVE "
                    + context.getOperation().getCacheNames());
            return delegate.resolveCaches(context);
        };
    }

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return (target, method, params) -> {
            String args = Arrays.stream(params)
                    .map(String::valueOf)
                    .collect(Collectors.joining(":"));
            String key = method.getName() + ":" + args;
            System.out.println("KEY " + key);
            return key;
        };
    }

    @Bean
    @Override
    public CacheErrorHandler errorHandler() {
        return new SimpleCacheErrorHandler();
    }

    @Bean
    BookService bookService() {
        return new BookService();
    }

    @Bean
    CommandLineRunner demo(BookService service, CacheManager manager) {
        return args -> {
            System.out.println("first = " + service.find("B42"));
            System.out.println("second = " + service.find("B42"));
            System.out.println("third = " + service.find("B99"));

            Cache books = manager.getCache("books");
            if (books == null) {
                throw new IllegalStateException("Missing books cache");
            }
            System.out.println("manual = "
                    + books.get("find:B42", String.class));
        };
    }
}

class BookService {
    @Cacheable(cacheNames = "books")
    public String find(String id) {
        System.out.println("LOAD " + id);
        return "Book(" + id + ")";
    }
}
~~~

Run from the project directory using `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) if a Gradle Wrapper is present, or `gradle bootRun` with a compatible installed Gradle.

Besides Spring Boot's startup logs, the lines **explicitly printed by the demo** appear in this order:

~~~text
RESOLVE [books]
KEY find:B42
LOAD B42
first = Book(B42)
RESOLVE [books]
KEY find:B42
second = Book(B42)
RESOLVE [books]
KEY find:B99
LOAD B99
third = Book(B99)
manual = Book(B42)
~~~

Explanation:

1. `cacheManager()` creates a `ConcurrentMapCacheManager` containing the `books` cache.
2. `cacheResolver()` creates a resolver delegating to `SimpleCacheResolver`, printing `RESOLVE [books]` on every `@Cacheable` operation and resolving caches via the manager.
3. `keyGenerator()` builds keys `find:B42` or `find:B99` from the method name and arguments. Because `@Cacheable` sets no custom `key`, the global generator is used.
4. The first `B42` call misses so the method prints `LOAD B42`; the second `B42` call hits with no `LOAD` line. The `B99` call has a different key so it misses.
5. `errorHandler()` configures `SimpleCacheErrorHandler`. The demo does not intentionally trigger backend errors, so no error callback fires.
6. `books.get("find:B42", String.class)` reads the entry back under the generator-created key, confirming the resolver and generator operated on the same concrete cache.

The example uses `@SpringBootApplication`, which is also a default `@Configuration` proxying `@Bean` methods. Thus `cacheResolver()` calls `cacheManager()` to obtain the registered singleton bean. If configured with `proxyBeanMethods=false`, pass `CacheManager` via a bean/provider explicitly instead of assuming internal calls are intercepted by Spring.

## 7. Minimal Configuration and Precedence Order

**Only manager needed:** When caches are selected by names declared on annotations, simply defining a `@Bean CacheManager` and enabling `@EnableCaching` suffices; you do not have to implement all four hooks. `CachingConfigurer` is helpful when you want explicit global defaults.

**Custom resolver:** When overriding `cacheResolver()`, it becomes the default choice for locating caches. If the same configurer also overrides `cacheManager()`, the manager does not automatically drive resolution; the resolver can explicitly call the manager.

**Custom generator:** Used only if the operation does not supply a `key` expression or its own generator. `key` and `keyGenerator` on the same annotation are mutually exclusive.

**Error handler:** Defines the cache error policy at the interceptor layer. `SimpleCacheErrorHandler` rethrows errors; a custom handler can log, fall back, or alert, yet must clearly specify which operations may be skipped.

| Configuration Level | Example | Role |
| --- | --- | --- |
| Global | `CachingConfigurer` | Defaults for operations without explicit settings. |
| Class | `@CacheConfig(cacheNames=..., keyGenerator=...)` | Shares configuration for methods in the same class. |
| Method | `@Cacheable(key=..., cacheResolver=...)` | Customizes specific operation, taking precedence over class/global config. |

`@CacheConfig` **does not enable caching on its own**: methods still require corresponding annotations such as `@Cacheable` or `@CacheEvict`.

## 8. Common Mistakes When Using `CachingConfigurer`

| Symptom / Misconception | Cause | Resolution |
| --- | --- | --- |
| Configured `CacheManager` yet custom resolver picks another backend. | When both are provided, `CacheResolver` decides the operation's caches. | Inspect `resolveCaches`, the manager used by the resolver, and annotation overrides. |
| `keyGenerator()` is not called. | Annotation has its own SpEL `key` or `keyGenerator` specified on method/class. | Check precedence order; avoid setting two key strategies on the same method. |
| Second call does not hit the cache. | Different keys, cache evicted, backend didn't store, annotation not intercepted. | Log key, cache name, `LOAD` counts; inspect proxy and bean. |
| Setting both `cacheManager` and `cacheResolver` on an annotation. | These two choices are mutually exclusive. | Pick one attribute. |
| Wrong key on evict. | Generator includes method name, while write method has a different name from read method. | Align keys between `@Cacheable` and `@CacheEvict`. |
| Cache delete fails yet handler swallows exception. | `evict/clear` errors are ignored. | For freshness-sensitive data, prefer detecting and handling invalidation errors explicitly. |
| Exception from method body mistaken for cache error. | `CacheErrorHandler` only handles cache operation errors. | Handle business errors in the appropriate layer, not via the cache handler. |
| Injecting into `CachingConfigurer` causes circular dependency/early init. | Caching infrastructure may initialize the configurer early. | Avoid field injection of heavy beans; consider lazy `ObjectProvider`, bean methods, or splitting config. |
| Self-invocation `this.find(...)` does not cache. | Default proxy mode does not intercept internal calls. | Invoke from another bean through the Spring proxy, or choose an appropriate interception mechanism. |
| Deploying local cache across multiple instances expecting shared state. | `ConcurrentMapCacheManager` holds state per JVM. | Use a shared backend or coordinated invalidation per consistency needs. |

## 9. Self-Check Questions

**Question 1.** Both `cacheManager()` and `cacheResolver()` are overridden in a `CachingConfigurer`. Which component does Spring use to resolve caches by default?

**Answer:** `CacheResolver`; the resolver can explicitly use the declared `CacheManager`, yet the manager does not create a default resolver overriding the custom resolver.

**Question 2.** Does `@Cacheable(cacheNames = "books", key = "#p0")` use the global `keyGenerator()`?

**Answer:** No. The SpEL `key` already specifies how the key is generated for that operation.

**Question 3.** Should `Cache.evict` errors always be ignored so the application keeps running?

**Answer:** No. If eviction fails and is ignored, the cache may serve stale data. This decision must be based on data freshness requirements and recovery mechanisms.

**Question 4.** How does `CacheManager` differ from `CacheResolver`?

**Answer:** A manager knows/returns caches by name; a resolver selects which caches serve an operation, potentially based on method, args, and multiple managers.

**Question 5.** Why can a key generator based on method name cause `@CacheEvict` to delete the wrong entry?

**Answer:** Read and write methods usually have different names. If the key includes the method name, the two operations generate different keys for the same business entity.

**Takeaway:** `CachingConfigurer` is the default configuration point for cache annotations. `CacheManager` provides caches, `CacheResolver` selects caches, `KeyGenerator` selects keys, and `CacheErrorHandler` decides how to react when the cache fails. Designing all four properly makes caching observable, consistent, and aligned with application needs.

References:

- [Spring Framework 6.1 — `CachingConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
