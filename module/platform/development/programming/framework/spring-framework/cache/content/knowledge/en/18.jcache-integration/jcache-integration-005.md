# Mapping Key and Value Parameters with JCache Annotations

> **Context:** Spring Framework Cache — **JCache (JSR-107)** group. This lesson focuses on how JCache uses `@CacheKey` to select parameters forming the **cache key** and `@CacheValue` to designate the **value written into the cache** in JCache `@CachePut`. From there, we build `@CacheResult` (read), `@CachePut` (write), and `@CacheRemove` (delete) flows sharing a single key contract.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **JCache** annotations (`javax.cache.annotation.*`) from similar **Spring Cache** annotations (`org.springframework.cache.annotation.*`).
2. Explain default key generation rules: without `@CacheKey`, all eligible parameters are used; with at least one `@CacheKey`, only annotated parameters are selected.
3. Understand `@CacheValue` as the **value-to-store** parameter of JCache `@CachePut`, and that it is excluded from the key.
4. Ensure `@CacheResult`, `@CachePut`, and `@CacheRemove` share the same cache name, key parameter set, and key generator.
5. Clearly understand that JCache `@CachePut` stores the **`@CacheValue` argument**, rather than the method return value as Spring `@CachePut` does.
6. Compile and run a Java 17 + Spring Framework 6.2.x project using JCache annotations backed by Spring's `ConcurrentMapCacheManager`.
7. Test cache hits/misses, trace parameters not affecting the key, updates and invalidation, and common pitfalls around equality, nulls, and tenant-scoped data.

## 1. Where Does JCache/JSR-107 Fit in Spring?

JCache is a standardized caching API commonly known as **JSR-107**. In Spring, developers can choose either Spring annotations or standard JCache annotations. Spring has supported JCache annotations since Spring Framework 4.1 and integrates them with the Spring caching abstraction.

Key annotations to remember:

| Intent | Spring Cache | JCache (JSR-107) |
| --- | --- | --- |
| Cache method result | `@Cacheable` | `@CacheResult` |
| Put/update cache | `@CachePut` | `@CachePut` |
| Evict a single key | `@CacheEvict` | `@CacheRemove` |
| Clear entire cache | `@CacheEvict(allEntries = true)` | `@CacheRemoveAll` |
| Class-level shared config | `@CacheConfig` | `@CacheDefaults` |
| Select parameters for key | SpEL `key = ...`, `KeyGenerator` | `@CacheKey` on parameters |
| Select data to write from a parameter | No direct `@CacheValue` equivalent | `@CacheValue` on a `@CachePut` parameter |

**Most common confusion:** both Spring and JCache have an annotation named `@CachePut`, yet they have **different packages and different stored-value semantics**.

Standard JCache imports in the examples:

```java
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheValue;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
```

For JCache 1.1.1, the namespace is **`javax.cache.annotation`**—do not change it to `jakarta.cache.annotation` just because you use Java 17 or Spring Framework 6.x. Within the same file, if both `@CachePut` annotations from the two packages are needed, avoid ambiguous imports; normally choose one style or use fully qualified names.

### Does Using JCache Annotations Require Switching to a JCache Provider?

**No.** Spring Framework provides an integration layer to process JCache annotations on top of the **Spring Cache abstraction**. You can use JCache annotations on Spring beans while the `CacheManager` remains `ConcurrentMapCacheManager` or another Spring-supported provider.

These are distinct concepts:

- **JCache annotations/API:** how caching is expressed on methods and parameters.
- **JCache caching provider:** a concrete implementation of `javax.cache.CacheManager`, i.e., a provider supporting JSR-107.
- **Spring `org.springframework.cache.CacheManager`:** Spring's abstraction that can execute both Spring annotations and JCache annotations through the corresponding integration.

Do not assume that merely adding `javax.cache:cache-api` provides a working cache store automatically. It provides the **API**, while storage and interception must still be configured and enabled.

## 2. @CacheKey — Selecting Parameters That Form the Cache Key

### 2.1. Without @CacheKey: Parameters Are Used by Default

Example book lookup method:

```java
@CacheResult(cacheName = "books")
public Book find(String isbn, boolean includeUsed, String locale) {
    return repository.load(isbn, includeUsed, locale);
}
```

This is **illustrative code**, assuming `repository` and `Book` exist. Because no parameter has `@CacheKey`, JCache considers all three parameters for the key by default:

```text
(isbn="ISBN-1", includeUsed=false, locale="vi")
(isbn="ISBN-1", includeUsed=true,  locale="vi")
(isbn="ISBN-1", includeUsed=false, locale="en")
```

Three parameter combinations produce three distinct keys. This is appropriate **if** all parameters genuinely affect the returned data.

For `@CachePut`, there is a special exception: the `@CacheValue` parameter is **never** included in the default key, even when no `@CacheKey` is declared. That rule prevents the key from changing when new data is placed into the cache.

### 2.2. With @CacheKey: Only Annotated Parameters Participate in the Key

```java
@CacheResult(cacheName = "books")
public Book find(@CacheKey String isbn, String traceId) {
    return repository.loadByIsbn(isbn);
}
```

Here `traceId` is only for request tracing; it does not alter the returned book. The sole parameter used for the cache key is `isbn`.

Therefore:

```text
find("ISBN-1", "request-A") → MISS → execute method and cache book
find("ISBN-1", "request-B") → HIT  → return the same book
find("ISBN-2", "request-C") → MISS → load another book
```

It is **not** that Spring ignores unmarked parameters by default. Rather, that is the **JCache rule when at least one `@CacheKey` is present**. Without any `@CacheKey`, all eligible parameters (except `@CacheValue` on put) participate in the key.

### 2.3. Multiple @CacheKey Parameters

If a product is identified by **tenant** and **SKU**:

```java
@CacheResult(cacheName = "tenantProducts")
public Product find(
        @CacheKey String tenantId,
        @CacheKey String sku,
        String requestId) {

    return repository.find(tenantId, sku);
}
```

Both `tenantId` and `sku` participate in the key. `requestId` does not.

This has security implications: if a cache stores multi-tenant data and the key is only `sku`, two tenants could inadvertently share each other's data. Never omit a dimension that differentiates results or access permissions merely to boost cache hit rates.

### 2.4. Unselected Parameters Must Truly Not Affect the Result

Dangerous example:

```java
@CacheResult(cacheName = "prices")
public int price(@CacheKey String sku, String currency) {
    return repository.priceInCurrency(sku, currency);
}
```

If `currency` changes the result, using only `sku` as the key is buggy. After caching a VND price, a subsequent USD request could hit the VND value.

The right fix may be annotating both:

```java
public int price(
        @CacheKey String sku,
        @CacheKey String currency) {
    return repository.priceInCurrency(sku, currency);
}
```

This is an illustrative signature snippet; in real usage, place `@CacheResult(cacheName = "prices")` on the method and provide the corresponding repository.

**Key selection criterion:** under the same key, cached data must be valid to reuse **by business semantics, tenant, and access permissions**, not merely because a few technical parameters match.

## 3. @CacheValue — Selecting the Parameter Written to Cache

`@CacheValue` is **not** a variant of `@CacheKey` and **does not apply to `@CacheResult` to select a return value**. In JCache, it marks the parameter holding **the value that `@CachePut` must write**.

Example:

```java
@CachePut(cacheName = "books")
public void save(
        @CacheKey String isbn,
        @CacheValue Book book,
        String auditId) {

    repository.save(isbn, book);
}
```

The contract is:
- **Cache name:** `books`.
- **Cache key:** generated from `isbn` because `isbn` carries `@CacheKey`.
- **Cache value:** the `book` object because this parameter carries `@CacheValue`.
- **`auditId`:** excluded from the key because another parameter carries `@CacheKey`.
- **Method body:** runs business logic `repository.save`; caching does not replace DB persistence.
- **Put timing:** JCache `@CachePut` defaults to `afterInvocation = true`, meaning it puts after the method completes successfully per the annotation's exception rules.

### @CacheValue Data Is Excluded from the Key

When using JCache `@CachePut`, the key parameter algorithm applies these rules:

| Parameter Declaration | What Forms the Key |
| --- | --- |
| `save(String isbn, @CacheValue Book book)`, no `@CacheKey` | `isbn`; excludes `book` |
| `save(@CacheKey String isbn, @CacheValue Book book, String auditId)` | Only `isbn` |
| `save(@CacheKey String tenant, @CacheKey String sku, @CacheValue Book book)` | `tenant` and `sku` |
| `save(String isbn, String locale, @CacheValue Book book)`, no `@CacheKey` | `isbn` and `locale` |

Thus, **you do not need `@CacheKey` solely to exclude `@CacheValue` from the key**, though using `@CacheKey` is good practice to make the contract explicit and keep auxiliary parameters like trace/audit IDs out of the key.

A method annotated with JCache `@CachePut` must have a valid `@CacheValue` parameter; omitting or misplacing it prevents annotation metadata from determining the value to put and can trigger annotation processing errors. Avoid putting `@CacheValue` on multiple parameters or using it on unsupported methods.

### JCache @CachePut Does Not Automatically Cache the Return Value

This is the core difference:

```java
// JCache: uses @CacheValue to know which argument to cache
@javax.cache.annotation.CachePut(cacheName = "books")
public String save(
        @CacheKey String isbn,
        @CacheValue Book book) {

    repository.save(isbn, book);
    return "saved:" + isbn;
}
```

With JCache, **`Book book` is cached**, while the String `"saved:..."` is just the return value handed to the caller.

Compare with Spring:

```java
// Spring: caches the method return value
@org.springframework.cache.annotation.CachePut(
        cacheNames = "books", key = "#p0")
public Book save(String isbn, Book book) {
    return repository.save(isbn, book);
}
```

These are two **different illustrative code patterns** in a Spring bean with a corresponding repository; you cannot mix them on one method assuming they behave identically. In Spring's version, the return value after execution becomes the cached value; in JCache's version, the `@CacheValue` parameter is the source of the cached value.

If a JCache method normalizes or transforms a record in the DB while `@CacheValue` remains the unnormalized input object, the cache may store a version **different from the DB**. Establish the canonical data source and, where necessary, use another method returning the canonical value or an appropriate invalidation/reload strategy.

## 4. How Do Read, Put, and Remove Share the Same Key?

A sound design for the `books` cache:

```java
@CacheResult(cacheName = "books")
public Book find(@CacheKey String isbn, String traceId) {
    return repository.load(isbn);
}

@CachePut(cacheName = "books")
public void save(
        @CacheKey String isbn,
        @CacheValue Book book,
        String auditId) {
    repository.save(isbn, book);
}

@CacheRemove(cacheName = "books")
public void invalidate(@CacheKey String isbn, String reason) {
    audit.log("invalidate", isbn, reason);
}
```

This is an **illustrative group of methods**; concrete `Book`, `repository`, and `audit` types are required.

All three methods select **the same key parameter set**: `isbn`. The trace and audit parameters are ignored. `@CacheResult` caches the loaded `Book` under the `isbn` key; `@CachePut` uses that same key to update the `Book`; `@CacheRemove` uses that same key to evict it.

When coexisting in an application, pay attention to the **actual key generator** as well. JCache generates a `GeneratedCacheKey` by default representing the selected parameters. If a Spring `@Cacheable(key="#p0")` method uses the raw String ISBN directly while JCache builds a `GeneratedCacheKey` from ISBN, **the two keys may differ even though the input values look identical**.

Do not blindly call `cache.get("ISBN-1")` on Spring `Cache` to inspect whether a default JCache operation cached an entry; the actual key may be a `GeneratedCacheKey` object rather than a plain String.

### Conditions That Must All Hold Simultaneously

1. Same cache region name (`cacheName="books"`).
2. Same key-forming dimensions (e.g., ISBN, plus tenant/locale if applicable).
3. Same algorithm/key generator and `equals/hashCode` rules.
4. Cached value has a type compatible with the reading method.
5. Source update succeeds; the written value matches the source state expected by reads.
6. Invoked through the Spring proxy with caching infrastructure enabled.

Changing any single piece can cause reads after puts to miss, or worse, hit the wrong data.

## 5. Key Selection Rules — Quick Reference Table

| Declaration | Key Parameter Set | Put Value |
| --- | --- | --- |
| `@CacheResult find(String sku, String locale)` | Both `sku` and `locale` | Return value of `find` |
| `@CacheResult find(@CacheKey String sku, String trace)` | Only `sku` | Return value of `find` |
| `@CacheResult find(@CacheKey String tenant, @CacheKey String sku, String trace)` | `tenant` and `sku` | Return value of `find` |
| `@CachePut save(String sku, @CacheValue Product product)` | `sku` | `product` |
| `@CachePut save(@CacheKey String sku, @CacheValue Product product, String audit)` | Only `sku` | `product` |
| `@CachePut save(String sku, String locale, @CacheValue Product product)` | `sku` and `locale` | `product` |
| `@CacheRemove remove(@CacheKey String sku, String reason)` | Only `sku` | No put; deletes entry |
| `@CacheRemoveAll clear()` | No specific key selected | No put; clears entire cache |

In this table, the annotations are **JCache**. The signatures are **rule-illustration patterns**, not complete Java programs with bodies and imports.

### GeneratedCacheKey and Equality

JSR-107 uses `CacheKeyGenerator` to produce a `GeneratedCacheKey`. Spring's default JCache key generator follows the standard design, picking parameters from `CacheKeyInvocationContext.getKeyParameters()` and creating a composite key.

For key parameters:
- Use value objects whose `equals()`/`hashCode()` match business identity.
- Java records with appropriate fields are often a great choice for immutable keys.
- Avoid mutating a mutable key object after inserting it: changing its hash/equality can make the entry unreachable.
- With arrays, collections, or nested objects, verify the key generator's deep-equality semantics and provider behavior (especially across serialization boundaries).
- Do not include tracing values, random timestamps, or request IDs in keys if they do not change the result.
- Never omit `tenantId` or security scopes if they affect which data may be returned.

A custom `CacheKeyGenerator` can be specified on a JCache operation via `cacheKeyGenerator`, typically implementing `javax.cache.annotation.CacheKeyGenerator`. It is a **different interface** from Spring Cache's `org.springframework.cache.interceptor.KeyGenerator`. When writing a custom generator, ensure the output key is stable, comparable, and compatible with the cache provider.

## 6. @CacheResult, @CachePut, and @CacheRemove: Execution Timing

### @CacheResult — Reading Through the Cache

By default, `@CacheResult` checks the cache first; a hit skips the method body, while a miss runs the method and caches its result. JCache supports extra options such as `skipGet = true` to force method execution while still caching according to annotation semantics; it does not mean "disable caching application-wide".

### @CachePut — Refreshing via Argument

The method runs business logic, and JCache takes the `@CacheValue` parameter to put into the cache. Default:

```java
@CachePut(cacheName = "books", afterInvocation = true)
public void save(@CacheKey String isbn, @CacheValue Book book) {
    repository.save(isbn, book);
}
```

`afterInvocation = true` avoids putting before the method body fails under default exception rules.

You can configure:

```java
@CachePut(cacheName = "books", afterInvocation = false)
public void save(@CacheKey String isbn, @CacheValue Book book) {
    repository.save(isbn, book);
}
```

However, **think carefully**: putting before invocation can insert a new cache entry **before the DB update actually succeeds**; if business logic fails or the transaction rolls back, the cache holds incorrect data. Never change the default just to "speed things up".

JCache supports `cacheFor` and `noCacheFor` exception class filters to decide whether to put when invocation throws an error. This is a JCache policy, not an atomicity guarantee between DB and cache.

### @CacheRemove — Deleting an Entry

`@CacheRemove` uses the selected key parameters to delete a single cache entry. By default, eviction happens after successful invocation; timing and exception handling can be adjusted via annotation attributes.

`@CacheRemoveAll` deletes all entries in the target cache, **independent of any specific `@CacheKey`**. It fits events invalidating an entire cache region, though it is expensive when entry counts are large.

## 7. Enabling JCache Annotations in Spring Framework

Using JCache annotations on a Spring bean **does not require deploying a separate JCache provider** when you already use Spring's Cache abstraction.

Components needed for the Java 17 example:
- `javax.cache:cache-api:1.1.1` — standard declarations for `@CacheResult`, `@CacheKey`, `@CacheValue`, `@CachePut`, and `@CacheRemove`.
- `org.springframework:spring-context-support` — integrates JCache annotations into Spring's caching infrastructure.
- `org.springframework:spring-context` — pulled in transitively by `spring-context-support`; contains `@EnableCaching` and `ConcurrentMapCacheManager`.
- A Spring `CacheManager` bean, such as `ConcurrentMapCacheManager("catalog")`.
- `@EnableCaching` to activate interception, plus invoking the **bean through the Spring proxy** rather than instantiating it directly with `new`.

Short configuration example:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

This is a **configuration snippet** requiring Spring Cache/Context imports inside an appropriate context. In plain Spring Framework, having `javax.cache.annotation` and `spring-context-support` on the classpath allows `@EnableCaching` to enable JCache annotation detection as well.

### Why @EnableCaching Matters

Annotations alone are merely metadata. Caching is performed by interceptors/advice set up by Spring. In default proxy mode:

- Calling a method on a bean obtained from `ApplicationContext`: advice can execute.
- Creating `new CatalogService(...)` and calling it: bypasses the proxy, so annotations have no effect.
- Calling `this.find(...)` inside the bean itself: self-invocation bypasses the proxy.
- Private/final methods or final classes can prevent proxying; examples use public, non-final service classes for clarity.

If the JCache API or `spring-context-support` is missing, `@EnableCaching` enabling Spring annotations will not automatically make JCache annotations work as expected.

## 8. Complete Example: Java 17 + Spring + JCache on ConcurrentMap

This experiment uses an in-JVM mock book store. One service uses **only JCache annotations** while the provider is Spring's `ConcurrentMapCacheManager`.

Verification steps:

1. Two reads with the same ISBN and different trace IDs call the repository **only once**.
2. Modifying the source externally causes the cache to return the **stale entry** before invalidation.
3. JCache `@CachePut` accepts a `Book` marked `@CacheValue`, updates both the source and cache with that `Book` even though the method returns a **receipt String**.
4. JCache `@CacheRemove` removes the matching key; the next read loads the fresh entry from source.
5. All three operations use cache name `catalog` and the same `isbn` key parameter.

### 8.1. Structure

```text
jcache-parameter-mapping/
├── pom.xml
└── src/
    ├── main/java/demo/jcache/JCacheMappingDemo.java
    └── test/java/demo/jcache/JCacheMappingDemoTest.java
```

### 8.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>jcache-parameter-mapping</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.jcache.JCacheMappingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The POM uses Spring Framework 6.2.16 and JCache 1.1.1 compatible with JDK 17. `spring-context-support` pulls in Spring Context. We **do not need Redis or Ehcache**: Spring's JCache annotation integration works directly with Spring's `ConcurrentMapCacheManager`.

### 8.3. src/main/java/demo/jcache/JCacheMappingDemo.java

```java
package demo.jcache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JCacheMappingDemo {

    public record Book(String isbn, String title) {}

    public static class BookRepository {
        private final Map<String, Book> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public BookRepository() {
            data.put("B1", new Book("B1", "Spring Handbook"));
        }

        public Book load(String isbn) {
            loads.incrementAndGet();
            return data.get(isbn);
        }

        public void save(String isbn, Book book) {
            data.put(isbn, book);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class CatalogService {
        private final BookRepository repository;
        private final AtomicInteger invalidations = new AtomicInteger();

        public CatalogService(BookRepository repository) {
            this.repository = repository;
        }

        @CacheResult(cacheName = "catalog")
        public Book find(@CacheKey String isbn, String traceId) {
            return repository.load(isbn);
        }

        @CachePut(cacheName = "catalog")
        public String replace(
                @CacheKey String isbn,
                @CacheValue Book book,
                String auditId) {
            repository.save(isbn, book);
            return "stored:" + isbn;
        }

        @CacheRemove(cacheName = "catalog")
        public void invalidate(@CacheKey String isbn, String reason) {
            invalidations.incrementAndGet();
        }

        public int invalidationCount() {
            return invalidations.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public BookRepository bookRepository() {
            return new BookRepository();
        }

        @Bean
        public CatalogService catalogService(BookRepository repository) {
            return new CatalogService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(CatalogService.class);
            var repository = context.getBean(BookRepository.class);
            var manager = context.getBean(CacheManager.class);

            System.out.println("manager="
                    + manager.getClass().getSimpleName());
            System.out.println("first="
                    + service.find("B1", "trace-A").title());
            System.out.println("second="
                    + service.find("B1", "trace-B").title());
            System.out.println("loads1="
                    + repository.loadCount());

            // Modify source outside the JCache annotation path:
            repository.save("B1", new Book("B1", "Changed Outside"));
            System.out.println("stale="
                    + service.find("B1", "trace-C").title());

            System.out.println("receipt="
                    + service.replace(
                            "B1",
                            new Book("B1", "Updated Via JCache Put"),
                            "audit-1"));
            System.out.println("afterPut="
                    + service.find("B1", "trace-D").title());
            System.out.println("loads2="
                    + repository.loadCount());

            // Source changes again; this time actively invalidate.
            repository.save("B1", new Book("B1", "After Invalidation"));
            service.invalidate("B1", "source-changed");

            System.out.println("afterRemove="
                    + service.find("B1", "trace-E").title());
            System.out.println("loads3="
                    + repository.loadCount());
            System.out.println("invalidations="
                    + service.invalidationCount());
        }
    }
}
```

### 8.4. Compiling and Running

Requires JDK 17+, Maven 3.9+, and network access on the first run to download dependencies. From the `jcache-parameter-mapping` directory, run:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself** (excluding Maven messages or Spring logs):

```text
manager=ConcurrentMapCacheManager
first=Spring Handbook
second=Spring Handbook
loads1=1
stale=Spring Handbook
receipt=stored:B1
afterPut=Updated Via JCache Put
loads2=1
afterRemove=After Invalidation
loads3=2
invalidations=1
```

Interpretation:

1. `first` misses; JCache `@CacheResult` invokes the repository and caches `Book` under the key generated from `@CacheKey isbn`.
2. `second` has a different `traceId` but the same `isbn`, resulting in a **hit**; `loads1=1` proves the repository was called only once.
3. Updating the repository directly to `Changed Outside` without invalidating the cache leaves `stale` as `Spring Handbook`.
4. `replace` executes business logic saving the new `Book`, while JCache `@CachePut` caches **the `Book` from the `@CacheValue` parameter**, **not** the `"stored:B1"` String returned by the method.
5. `afterPut` retrieves the new `Book` straight from cache; `loads2` stays 1. All three operations share the same key because they all mark `isbn` with `@CacheKey`.
6. After the source becomes `After Invalidation`, `@CacheRemove` deletes the entry under that key. `afterRemove` misses, reloads from source, and `loads3=2`.
7. `invalidations=1` confirms the invalidation method body ran once. The cache entry removal itself was performed by the JCache interceptor, not by manual `Cache.evict` code.

**Scope:** this demo runs only in a single JVM with `ConcurrentMapCacheManager`, and does not verify TTL, DB transactions, or distributed consistency. It illustrates Spring **processing JCache annotations with a Spring CacheManager**, rather than demonstrating a standalone `javax.cache` provider.

## 9. JUnit 5 Tests Verifying Exact Key/Value Mapping

Create `src/test/java/demo/jcache/JCacheMappingDemoTest.java`:

```java
package demo.jcache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JCacheMappingDemoTest {

    @Test
    void onlyCacheKeyParameterDeterminesReadKey() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "trace-first").title());
            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "trace-second").title());
            assertEquals(1, repository.loadCount());
        }
    }

    @Test
    void cachePutUsesCacheValueParameterNotMethodReturn() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            service.find("B1", "trace-read");
            assertEquals(1, repository.loadCount());

            var newBook = new JCacheMappingDemo.Book("B1", "New Title");
            assertEquals(
                    "stored:B1",
                    service.replace("B1", newBook, "audit-99"));

            // After JCache @CachePut, @CacheResult must read the Book,
            // NOT the receipt String "stored:B1".
            assertEquals(
                    "New Title",
                    service.find("B1", "trace-after-put").title());
            assertEquals(1, repository.loadCount());
        }
    }

    @Test
    void cacheRemoveUsesSameSelectedKey() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "first").title());
            repository.save("B1",
                    new JCacheMappingDemo.Book("B1", "Fresh"));

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "still-cached").title());
            service.invalidate("B1", "update");

            assertEquals(
                    "Fresh",
                    service.find("B1", "after-remove").title());
            assertEquals(2, repository.loadCount());
            assertEquals(1, service.invalidationCount());
        }
    }
}
```

Run:

```bash
mvn -q test
```

When all assertions pass, Maven exits with code 0. Because `-q` is passed, Maven does not necessarily print "BUILD SUCCESS" to the console.

**What makes these tests effective:** they measure source load counts and returned values rather than timing. Each test creates a fresh `ApplicationContext`, isolated from leftover cache entries in previous tests. More importantly, they prove all three JCache methods **actually point to the exact same key**, rather than merely sharing a cache region name.

## 10. Common Mistakes with @CacheKey and @CacheValue

### 10.1. Forgetting @CacheKey When Unrelated Parameters Exist

```java
@CacheResult(cacheName = "books")
public Book find(String isbn, String traceId) {
    return repository.load(isbn);
}
```

Without `@CacheKey`, JCache uses **both** parameters by default. Different trace IDs produce different keys and cause constant cache misses despite identical ISBNs.

**Fix:** `find(@CacheKey String isbn, String traceId)`, provided `traceId` truly **does not affect** the result.

### 10.2. Omitting a Parameter That Changes Data or Access Scope

If `find(String tenantId, String isbn)` annotates only `isbn`, two tenants can hit the same entry. This is not just a performance bug—it is a **data isolation bug**. Annotate both `@CacheKey tenantId` and `@CacheKey isbn` whenever results are tenant-scoped.

### 10.3. Missing @CacheValue on JCache @CachePut

```java
@CachePut(cacheName = "books")
public void save(@CacheKey String isbn, Book book) {
    repository.save(isbn, book);
}
```

**Broken snippet to recognize:** JCache has no way to know which parameter holds the value to put. It does not default to the method return value or guess `Book` from its parameter type. You must mark the value parameter with `@CacheValue`.

### 10.4. Importing Spring @CachePut by Mistake

A mistaken import:

```java
import org.springframework.cache.annotation.CachePut;
```

instead of:

```java
import javax.cache.annotation.CachePut;
```

completely changes behavior. Spring `@CachePut` stores the **return value**; JCache `@CachePut` stores the **`@CacheValue` argument**. Identical annotation names do not make them equivalent.

### 10.5. Annotating @CacheValue Yet Looking Up the Key as a Plain String

With JCache's default key generator, `cache.get("B1")` on `org.springframework.cache.Cache` will not necessarily find the entry created by `@CacheResult` from `@CacheKey String isbn`, because the actual key object may be a `GeneratedCacheKey`. To test exact keys, use the same annotation path or inspect through the actual generator rather than guessing internal key objects.

### 10.6. @CachePut Writing the Parameter Before the Source Update Succeeds

`afterInvocation = false` can put into the cache before `repository.save` completes. If the DB rolls back or errors out, the cache contains a value absent from the source. Even with the default `afterInvocation = true`, consider Spring transaction boundaries: method return does not always mean the transaction has committed.

### 10.7. Cached Value Does Not Match the Type Expected by @CacheResult

If JCache `@CachePut` writes a DTO other than `Book` while `@CacheResult` on the same cache/key expects to return `Book`, subsequent hits can fail with cast errors or return wrong data. Establish a consistent **cache value type** contract across operations.

### 10.8. Mutating a Key Object After Caching

Using a mutable object as a key and later modifying fields used in `equals/hashCode` can render the entry unretrievable. Use immutable IDs, well-defined records, or immutable key objects.

### 10.9. Assuming Cache Annotations Enable Caching Automatically

Adding `@CacheResult` or `@CachePut` without `@EnableCaching` and integration dependencies will not produce caching behavior. Calling `this.method()` or instantiating via `new` also bypasses the Spring proxy.

### 10.10. Sharing a Cache Name Across Different Key Generators

A Spring `@Cacheable(key = "#p0")` method and a JCache `@CachePut` method may receive the same ISBN parameter yet produce **non-equivalent physical keys**. Sharing a cache name is not enough. Unify the entire key strategy; when migrating from Spring annotations to JCache, test actual cache hits and readbacks.

## 11. Advanced Cases

### 11.1. Class-Level @CacheDefaults

JCache `@CacheDefaults` specifies a default cache name to avoid repetition:

```java
@CacheDefaults(cacheName = "books")
public class BookService {
    @CacheResult
    public Book find(@CacheKey String isbn) {
        return repository.load(isbn);
    }
}
```

This is an **illustrative snippet in an application with a repository**, requiring the `CacheDefaults` import. Method annotations can override class-level defaults. If `cacheName` is omitted from both the method and `@CacheDefaults`, JCache derives a name from class, method, and parameter type information, which may not match any cache registered in `CacheManager`.

When coordinating multiple operations meant to share one region, explicit cache naming is much easier to verify.

### 11.2. CacheResolverFactory

JSR-107 defines `javax.cache.annotation.CacheResolverFactory` and `CacheResolver` for selecting caches. In Spring integration, you can customize cache resolution, keeping in mind that standard JCache resolves **one cache per operation** rather than a list of caches as some Spring Cache features allow. A buggy resolver can route reads and writes to different regions despite identical business names.

### 11.3. Customizing CacheKeyGenerator

`@CacheResult` and JCache `@CachePut` expose `cacheKeyGenerator` to plug in a custom key generator class. Use this when keys require normalization—such as normalizing ISBNs, tenant scoping, or composite immutable IDs.

A custom key generator should:
- Rely on the exact selected `getKeyParameters()` set.
- Produce equal keys for logically identical inputs across all operations.
- Avoid exposing sensitive secrets in key `toString()` or logs.
- Compare keys by value rather than object identity.
- Verify serialization when using Redis, Ehcache, or cross-JVM caches.

Do not write a custom generator merely to ignore a `traceId`: `@CacheKey` is standard and much simpler.

### 11.4. Exception Caching

JCache `@CacheResult` can cache selected exceptions via `cachedExceptions` and `exceptionCacheName`. This does not change `@CacheKey` parameter selection rules, but causes subsequent calls to rethrow the cached exception instead of executing the method. Use this only for appropriate deterministic errors with clear expiration/invalidation policies.

### 11.5. Null Values and Providers

Providers vary in null key/value policies. Spring's `ConcurrentMapCacheManager` can represent cached null values via a placeholder object, whereas another JCache provider may reject null values outright. Do not assume `@CacheValue` makes null values valid everywhere. When data may be absent, verify provider behavior, key strategy, and negative-caching policy.

### 11.6. TTL, TTI, and Invalidation

JCache annotations specify operations and key/value mappings; time-to-live, idle expiration, capacity, and serialization belong to provider configuration. If the source changes without going through `@CachePut` or `@CacheRemove`, `@CacheResult` can serve stale data. TTL limits staleness duration but does not synchronize immediately when the DB changes.

## 12. Checklist When Designing Key/Value Mapping

1. **Correct package:** did you import `javax.cache.annotation.CachePut` instead of accidentally importing Spring `@CachePut`?
2. **Key dimensions:** does the `@CacheKey` set include all tenant, ID, locale/currency, and permission scopes affecting the data?
3. **Auxiliary parameters:** are non-result-affecting `traceId` and `auditId` parameters excluded from the key?
4. **Without @CacheKey:** do you understand that JCache uses all parameters by default (except `@CacheValue` on put)?
5. **CacheValue:** does JCache `@CachePut` have one parameter holding the exact value to cache?
6. **Return value:** are you mistaking the method's return value for the `@CacheValue` parameter?
7. **Consistency:** do read, put, and remove use the same cache name, key parameter set, and key generator?
8. **Value type:** does the put value match the type expected by `@CacheResult`?
9. **Source of truth:** does the cached value reflect persisted canonical data?
10. **Put timing:** does `afterInvocation` need to change, and how does it interact with transactions/rollbacks?
11. **Proxy:** are methods invoked through Spring beans with `@EnableCaching` active?
12. **Provider:** is Spring's JCache integration infrastructure present, and what is the actual `CacheManager`?
13. **Tests:** with different `traceId`s, does the same ISBN hit? After put, is the updated `Book` read? After remove, does it miss?
14. **Operations:** are TTL/invalidation and multi-tenant isolation configured appropriately?

## 13. Practice Exercises

**Exercise 1.** For `find(String isbn, String requestId)` without `@CacheKey`, will two different `requestId` values produce the same key?  
**Answer:** Under JCache's default key generator, both parameters participate and usually produce **two different keys**. If `requestId` does not affect the result, put `@CacheKey` on `isbn` only.

**Exercise 2.** What does `save(@CacheKey String isbn, @CacheValue Book book, String auditId)` use?  
**Answer:** The key uses `isbn`; the value is `book`; `auditId` is excluded from the key.

**Exercise 3.** Why doesn't `save(String isbn, @CacheValue Book book)` include `Book` in the key when `@CacheKey` is absent?  
**Answer:** JCache's rule automatically excludes `@CacheValue` from the key for `@CachePut`.

**Exercise 4.** A JCache `@CachePut` method returns `String "OK"` while `@CacheValue` is on `Book book`. What does the cache receive?  
**Answer:** `Book`, not the receipt String.

**Exercise 5.** A `@CacheResult` method uses `@CacheKey ISBN`, while a Spring `@CachePut(key = "#p0")` method uses the raw String ISBN. Why might they miss each other's entries?  
**Answer:** The two frameworks/key generators may produce different key object types despite identical ISBN text. Unify the key generation strategy.

**Exercise 6.** A service returns prices by `tenantId` and `sku` but marks only `@CacheKey sku`. What is the bug?  
**Answer:** Different tenants can share the same key; both `tenantId` and `sku` must be part of the key.

**Exercise 7.** Why can't `@CacheValue` be treated like `@CacheResult`?  
**Answer:** `@CacheValue` only marks the parameter written by JCache `@CachePut`; `@CacheResult` caches the method's **return value** on the miss path.

## Official References

- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [JSR-107 API — CacheKey](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheKey.html)
- [JSR-107 API — CacheValue](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheValue.html)
- [JSR-107 API — CachePut](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html)
- [JSR-107 API — CacheKeyInvocationContext](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheKeyInvocationContext.html)
- [Spring Boot — Caching and JCache Provider](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Takeaway:** In JCache, **`@CacheKey` selects parameters used to generate the key**, while **`@CacheValue` selects the parameter written to the cache**. JCache `@CachePut` **does not take the method's return value** as Spring `@CachePut` does. To read, update, and delete the same entry, align **cache name + key parameters + key generator + value type**, and verify through the Spring proxy and actual provider.