# `@CacheResult`, `@CachePut`, `@CacheRemove`, and `@CacheRemoveAll` in Spring Framework

## Learning Objectives

Spring Framework supports standard **JCache (JSR-107)** annotations alongside Spring's own caching annotations. The four primary operations are `@CacheResult`, `@CachePut`, `@CacheRemove`, and `@CacheRemoveAll`. They have names close to Spring's annotations, yet several semantics differ—most notably, **JCache `@CachePut` takes its value from a `@CacheValue` parameter**, whereas Spring's `org.springframework.cache.annotation.CachePut` stores the method's return value.

After this lesson, you will be able to:

1. Explain JCache/JSR-107 and how Spring integrates this annotation set.
2. Choose the right operation for reading, writing, removing one entry, or clearing a region.
3. Use `@CacheKey` to select key-generating parameters and `@CacheValue` to designate the value to cache.
4. Understand `skipGet`, exception caching, `afterInvocation`, and exception-handling options.
5. Use `@CacheDefaults`, `CacheKeyGenerator`, and `CacheResolverFactory`.
6. Configure Spring to process JCache annotations even when the backend remains `ConcurrentMapCacheManager`.
7. Test with a Java 17 + Spring Boot example and avoid confusion with Spring annotations.

## 1. What Is JCache (JSR-107)?

**JCache** is the common name for Java Specification Request 107, a standard API and SPI for caching in Java. The API defines how applications interact with caches and how vendors implement cache providers. Its goal is to reduce direct coupling to a specific product such as Ehcache, Hazelcast, or Infinispan.

JCache 1.1.1 uses the `javax.cache` and `javax.cache.annotation` packages. In Java 17 applications with Spring Framework 6 / Spring Boot 3, the JCache 1.1.1 package remains `javax.cache`; do not rename it to `jakarta.cache`.

Spring has supported JCache annotations since Spring Framework 4.1. They are processed by Spring's caching infrastructure. **You do not have to switch cache storage to a JCache provider**: Spring can execute JCache annotations through its existing abstraction and `CacheManager`.

~~~text
Service method
   |
   +-- JCache: @CacheResult / @CachePut
   |           @CacheRemove / @CacheRemoveAll
   |
   v
Spring caching interceptor
   |
   v
Spring Cache abstraction
   |
   +-- ConcurrentMapCacheManager
   +-- CaffeineCacheManager
   +-- RedisCacheManager
   +-- JCacheCacheManager
~~~

Two concepts must be separated:

- **JCache annotation API:** how caching operations are declared on methods.
- **Cache provider/storage:** where keys and values are actually stored, which can be a JCache provider or another Spring Cache implementation.

This is useful when you want standard JSR-107 annotations while keeping an existing Spring Cache backend in operation.

## 2. The Four Annotations and Their Relationship to Spring Annotations

| Meaning | Spring Cache | JCache (JSR-107) | Key Difference |
| --- | --- | --- | --- |
| Read, cache method result | `@Cacheable` | `@CacheResult` | JCache supports `skipGet` and dedicated exception caching |
| Execute method then write cache | `@CachePut` | `@CachePut` | Spring caches return value; JCache caches the `@CacheValue` parameter |
| Remove a single entry | `@CacheEvict` | `@CacheRemove` | JCache has `evictFor`/`noEvictFor` for exceptions |
| Remove all entries in a cache | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` | Same semantics for clearing an entire region |
| Class-level default config | `@CacheConfig` | `@CacheDefaults` | Shares cache name, resolver/key generator |

Two annotations sharing the name `@CachePut` **do not share the same contract**. Always verify imports:

~~~java
// JCache: value comes from the @CacheValue parameter.
import javax.cache.annotation.CachePut;

// Spring Cache: value comes from the method return value.
import org.springframework.cache.annotation.CachePut;
~~~

Do not mix up these two imports. If a JCache method lacks `@CacheValue`, the operation has no designated data to write. If you use Spring `@CachePut` expecting Spring to automatically read a `@CacheValue` parameter, that behavior does not exist either.

## 3. `@CacheResult`: Check Cache First, Run Method Only on Miss

`@CacheResult` is roughly equivalent to `@Cacheable`: Spring or the provider generates a key and checks the cache before invoking the method. If an entry exists, the cached value is returned and the method body can be skipped. On a miss, the method runs and its result is placed into the cache.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheResult;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    @CacheResult(cacheName = "products")
    public Product findById(@CacheKey String productId) {
        return repository.findById(productId);
    }
}
~~~

This is an illustrative snippet in a service with application-defined `repository` and `Product`. JCache uses the singular attribute `cacheName`, whereas Spring `@Cacheable` typically uses `cacheNames`.

### Notable Attributes

| Attribute | Effect |
| --- | --- |
| `cacheName` | Cache name used for the result |
| `cacheResolverFactory` | Selects the factory creating resolvers to locate the cache |
| `cacheKeyGenerator` | Selects the key generation algorithm |
| `skipGet` | Skips the pre-lookup; method always executes and the result is still cached |
| `exceptionCacheName` | Separate cache name used to store exceptions |
| `cachedExceptions` | Exception types allowed to be cached |
| `nonCachedExceptions` | Exception types excluded from caching |

`skipGet=true` is useful when a method must **always run** while still caching its return value:

~~~java
// Illustrative: always recompute the report and update the cache.
@CacheResult(cacheName = "reports", skipGet = true)
public Report regenerate(@CacheKey String reportId) {
    return reportService.regenerate(reportId);
}
~~~

When `skipGet=true`, the pre-invocation cache lookup is skipped. If `exceptionCacheName` is configured, the pre-invocation exception lookup is skipped as well. This works for refresh/recomputation flows, though it is not identical to JCache `@CachePut`: `@CachePut` takes its value from `@CacheValue`, whereas `@CacheResult(skipGet=true)` caches the method's return value.

### Exception Caching

JCache can cache selected exceptions in a separate region. For example, if an invalid ISBN is a permanent failure, subsequent calls with the same key can rethrow the cached exception instead of running the method again:

~~~java
// Illustrative; InvalidIsbnException and repository are defined by the application.
@CacheResult(
        cacheName = "books",
        exceptionCacheName = "bookFailures",
        cachedExceptions = InvalidIsbnException.class
)
public Book findBook(@CacheKey String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Use exception caching only for genuinely deterministic, stable errors. Never indiscriminately cache network errors, timeouts, database unavailability, or transient failures: a stale cached exception could continue being thrown even after the source recovers. Set a TTL on the exception region at the provider level and test `cachedExceptions`/`nonCachedExceptions`.

## 4. JCache `@CachePut`: Using `@CacheValue` to Specify the Written Value

This is the most important difference compared to Spring `@CachePut`.

In JCache, the method executes and the parameter annotated with `@CacheValue` is the **value written into the cache**. Key parameters are determined by `@CacheKey` or the key generator rules.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheValue;

// Illustrative in a Spring-managed service.
@CachePut(cacheName = "products")
public void update(
        @CacheKey String productId,
        @CacheValue Product updatedProduct) {
    repository.update(updatedProduct);
}
~~~

After the method succeeds, `updatedProduct` is put into the cache under the key generated from `productId`. The method may return `void`, because the cached value is supplied via `@CacheValue`.

### Timing of the Put

`afterInvocation` defaults to `true`:

~~~text
Caller invokes update(P1, updatedProduct)
                 |
                 v
         Execute update method
                 |
           Method succeeds
                 |
                 v
      Read @CacheValue parameter
                 |
                 v
   Generate key from @CacheKey / generator
                 |
                 v
        Cache.put(key, value)
~~~

You can set `afterInvocation=false` to put before the method runs:

~~~java
// Illustrative: the cache is updated before the update logic runs.
@CachePut(cacheName = "products", afterInvocation = false)
public void update(
        @CacheKey String productId,
        @CacheValue Product updatedProduct) {
    repository.update(updatedProduct);
}
~~~

Use this setting cautiously: if the repository update fails, the cache may already hold the new value while the data source was never updated. The default post-invocation write is usually easier to reason about.

JCache `@CachePut` also provides `cacheFor` and `noCacheFor` to govern how the cache value parameter is handled when the method throws an exception while `afterInvocation=true`. Configure these only when business logic intentionally caches values despite invocation failure; never treat cache puts as a transaction replacement for the database.

## 5. `@CacheRemove`: Deleting a Single Entry by Key

`@CacheRemove` is the closest equivalent to `@CacheEvict` for single-entry removal. The method performs its business logic, and the corresponding cache entry is removed.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheRemove;

// Illustrative in a service with a repository.
@CacheRemove(cacheName = "products")
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

By default, `afterInvocation=true`: eviction occurs after the method completes normally. If the method throws an exception, removal does not occur by default.

You can set `afterInvocation=false` to remove before the method runs:

~~~java
@CacheRemove(cacheName = "products", afterInvocation = false)
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

With this mode, even if repository deletion fails, the cache entry has already been evicted; the next read reloads from source. This can create extra cache misses, yet avoids serving stale data when source state is uncertain.

### Exception Handling on Removal

`@CacheRemove` supports:

- `evictFor`: exception types that still trigger removal when thrown by the method.
- `noEvictFor`: exception types that prevent removal.

These attributes apply only when `afterInvocation=true`. When both are configured, an exception must match `evictFor` and not match `noEvictFor` for eviction to proceed.

~~~java
// Illustrative: remove even when delete throws ResourceNotFoundException.
@CacheRemove(
        cacheName = "products",
        evictFor = ResourceNotFoundException.class
)
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

This is a business choice, not a sensible default for every failure. For instance, an authorization error should not inadvertently mutate cache state without a clear policy.

## 6. `@CacheRemoveAll`: Clearing All Entries in a Cache

`@CacheRemoveAll` corresponds to Spring's `@CacheEvict(allEntries = true)`. It invokes `removeAll()` on the specified cache region; no key needs to be generated.

~~~java
import javax.cache.annotation.CacheRemoveAll;

// Illustrative in a Spring-managed service.
@CacheRemoveAll(cacheName = "products")
public void invalidateProductCache() {
    // Can record an event or run appropriate business logic.
}
~~~

By default, clearing occurs **after the method succeeds**. You can set `afterInvocation=false` to clear before method execution. If the method throws an exception, the cache region is not cleared by default.

`@CacheRemoveAll` clears only entries in the `"products"` cache. It **does not delete database rows**, does not automatically clear `"productDetails"` or `"searchResults"` caches, and does not broadcast invalidation to local caches in other JVMs unless the provider supports such sharing/invalidation mechanisms.

If an update affects multiple cache regions, you may need multiple invalidation methods, a coordinating service, or explicit cache API calls. Avoid overusing `@CacheRemoveAll` when evicting a single key suffices.

## 7. Key Generation: `@CacheKey` and `CacheKeyGenerator`

Default JCache rules:

- If **no** parameter carries `@CacheKey`, all method parameters are used to generate the key (excluding the `@CacheValue` parameter in put operations).
- If **at least one** parameter carries `@CacheKey`, only the annotated parameters participate in the key.
- `@CacheValue` marks the value for `@CachePut`, not the entry identifier.

Example looking up a product with an extra `traceId`:

~~~java
@CacheResult(cacheName = "products")
public Product find(
        @CacheKey String productId,
        String traceId,
        boolean includeInventory) {
    return repository.find(productId, includeInventory);
}
~~~

Only `productId` forms the key. `traceId` is ignored. However, `includeInventory` is also ignored because once `@CacheKey` is present, only annotated parameters participate. If `includeInventory` alters the returned result, the snippet above is **incorrectly designed**. Annotate that parameter too:

~~~java
@CacheResult(cacheName = "products")
public Product find(
        @CacheKey String productId,
        @CacheKey boolean includeInventory,
        String traceId) {
    return repository.find(productId, includeInventory);
}
~~~

### `CacheKeyGenerator`

`javax.cache.annotation.CacheKeyGenerator` builds a `GeneratedCacheKey` from a `CacheKeyInvocationContext`. Implementations must be thread-safe. `GeneratedCacheKey` must be immutable, serializable, and honor the `equals()`/`hashCode()` contract; two equal keys must have the same hash code.

A custom key generator is useful when identity includes tenant, projection type, or domain-specific normalization. Never return a bare `hashCode()` as the key, because collisions can cause two distinct inputs to share the same cache entry.

### Comparing Spring and JCache Key Generation

Spring's default `SimpleKeyGenerator`:
- No parameters → `SimpleKey.EMPTY`.
- One parameter → the parameter object itself.
- Multiple parameters → a `SimpleKey` wrapping all parameters.

JCache generates a `GeneratedCacheKey` by default from the selected key parameters. Consequently, `@Cacheable(cacheNames="products")` and `@CacheResult(cacheName="products")` may not find each other's entries even when both pass `"P1"`.

If both annotation systems operate on **the same cache**, you must align the exact key algorithm. The most maintainable choice is usually picking one annotation family per cache or use case instead of mixing them arbitrarily.

## 8. `@CacheDefaults`: Class-Level Shared Defaults

JCache's `@CacheDefaults` is roughly equivalent to Spring's `@CacheConfig`. It lets you set defaults for operations in a class:

- `cacheName`
- `cacheResolverFactory`
- `cacheKeyGenerator`

~~~java
import javax.cache.annotation.CacheDefaults;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheRemove;

@CacheDefaults(cacheName = "products")
public class ProductService {

    @CacheResult
    public Product find(@CacheKey String id) {
        return repository.find(id);
    }

    @CacheRemove
    public void delete(@CacheKey String id) {
        repository.delete(id);
    }
}
~~~

This is a structural illustration; a complete class needs the corresponding imports and fields. Operations can override class-level defaults.

If `cacheName` is omitted on both the method and `@CacheDefaults`, Spring's JCache support derives a default cache name from the fully qualified class name, method name, and parameter types. This can unintentionally create many separate cache regions. For caches shared across methods, specify names explicitly via `@CacheDefaults` or the `cacheName` attribute.

### `CacheResolverFactory`

JCache provides `CacheResolverFactory` to create a `CacheResolver` per operation. The resolver determines which cache is used during invocation. This option fits cases where the cache depends on tenant, context, or provider. A JCache resolver selects **one cache per operation**, whereas Spring Cache annotations can list multiple caches in a single operation.

Custom factories and generators must be thread-safe. If they depend on request context, ensure the scope comes from an authenticated context and never leaks cache entries across tenants.

## 9. Complete Example: Four JCache Annotations in Spring Boot

This example uses **Java 17, Spring Boot 3.3.5, Maven**. It includes JCache API 1.1.1 while using Spring's `ConcurrentMapCacheManager` as storage. This proves Spring can process JCache annotations without switching to Ehcache, Hazelcast, or a standalone JCache provider.

Program flow:

1. `@CacheResult` reads product P1 on the first call, then hits on the second.
2. `@CachePut` always executes the method and writes `Product` via the `@CacheValue` parameter.
3. `@CacheRemove` deletes entry P1 after deletion succeeds.
4. `@CacheRemoveAll` clears every entry in the `products` cache.
5. Source read counters prove exactly when the underlying read method runs.

### Directory Structure

~~~text
jcache-annotations-demo/
├── pom.xml
└── src/main/java/example/jcache/
    ├── DemoApplication.java
    └── CatalogService.java
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
    <artifactId>jcache-annotations-demo</artifactId>
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
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
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

`spring-boot-starter-cache` brings in `spring-context-support`; `cache-api` supplies the JSR-107 annotations. **The example has no JCache provider**: the backend is created with Spring's `ConcurrentMapCacheManager`. Spring supports JCache annotations through its caching abstraction, making this a valid setup for learning and running the demo.

### `src/main/java/example/jcache/CatalogService.java`

~~~java
package example.jcache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ConcurrentMap<String, Product> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceReads = new AtomicInteger();

    public record Product(String id, String name, int version) {}

    public CatalogService() {
        source.put("P1", new Product("P1", "Pen", 1));
        source.put("P2", new Product("P2", "Marker", 1));
    }

    @CacheResult(cacheName = "products")
    public Product find(@CacheKey String productId) {
        sourceReads.incrementAndGet();
        Product product = source.get(productId);
        if (product == null) {
            throw new IllegalArgumentException("Unknown product: " + productId);
        }
        return product;
    }

    @CachePut(cacheName = "products")
    public void rename(
            @CacheKey String productId,
            @CacheValue Product updatedProduct) {
        if (!productId.equals(updatedProduct.id())) {
            throw new IllegalArgumentException("Product ID mismatch");
        }
        source.put(productId, updatedProduct);
    }

    @CacheRemove(cacheName = "products")
    public void delete(@CacheKey String productId) {
        source.remove(productId);
    }

    @CacheRemoveAll(cacheName = "products")
    public void invalidateAll() {
        // The annotation clears the cache region after this method succeeds.
    }

    // Simulates an external system recreating the product after deletion.
    public void seedFromExternalSystem(Product product) {
        source.put(product.id(), product);
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
~~~

Notable details:

- `find` uses `@CacheResult`, so the method reads the source only on a cache miss.
- `rename` uses JCache `@CachePut`. `@CacheKey` selects the ID and `@CacheValue` selects the `Product` object to store. Returning `void` is completely valid.
- `delete` uses `@CacheRemove` to evict the entry for that ID.
- `invalidateAll` uses `@CacheRemoveAll` to clear the entire cache region after the method succeeds.
- `seedFromExternalSystem` simulates another system rewriting data after deletion. This demonstrates that the next read does not return the stale entry.

### `src/main/java/example/jcache/DemoApplication.java`

~~~java
package example.jcache;

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
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(CatalogService catalog) {
        return args -> {
            System.out.println("first=" + catalog.find("P1"));
            System.out.println("hit=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.rename(
                    "P1",
                    new CatalogService.Product("P1", "Blue Pen", 2));
            System.out.println("after-put=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.delete("P1");
            catalog.seedFromExternalSystem(
                    new CatalogService.Product("P1", "Recreated Pen", 3));
            System.out.println("after-remove=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println("second-key=" + catalog.find("P2"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.invalidateAll();
            System.out.println("after-remove-all-P1=" + catalog.find("P1"));
            System.out.println("after-remove-all-P2=" + catalog.find("P2"));
            System.out.println("sourceReads=" + catalog.sourceReads());
        };
    }
}
~~~

### Running the Program

Inside `jcache-annotations-demo`, with JDK 17+ and Maven installed, run:

~~~bash
mvn -q spring-boot:run
~~~

Excluding Spring Boot startup logs, the lines printed by `CommandLineRunner` will be:

~~~text
first=Product[id=P1, name=Pen, version=1]
hit=Product[id=P1, name=Pen, version=1]
sourceReads=1
after-put=Product[id=P1, name=Blue Pen, version=2]
sourceReads=1
after-remove=Product[id=P1, name=Recreated Pen, version=3]
sourceReads=2
second-key=Product[id=P2, name=Marker, version=1]
sourceReads=3
after-remove-all-P1=Product[id=P1, name=Recreated Pen, version=3]
after-remove-all-P2=Product[id=P2, name=Marker, version=1]
sourceReads=5
~~~

Explanation:

1. The first `find("P1")` misses, so the method runs and reads the source. The second call hits, leaving `sourceReads` at 1.
2. `rename` always executes, updates the source, and JCache `@CachePut` writes `Product(...Blue Pen, version=2)` from the `@CacheValue` parameter. The next `find` returns the updated product without incrementing `sourceReads`.
3. `delete` removes the source entry and JCache `@CacheRemove` deletes entry P1 after the method succeeds. When the external system recreates P1 as `Recreated Pen`, the next `find` misses and reads the fresh value; the counter increments to 2.
4. `find("P2")` populates a second entry; the counter becomes 3.
5. `invalidateAll` invokes `@CacheRemoveAll`, clearing both cache entries. P1 and P2 remain in the source. Both subsequent reads miss, bringing `sourceReads` to 5.

This example runs on an in-memory cache within a single JVM; it does not cover TTL, persistence, distributed invalidation, or database transactions. Its purpose is to demonstrate the semantics of the four JCache annotations in Spring.

## 10. Enabling JCache Annotations in Spring

Spring automatically enables JCache annotation support alongside standard caching annotations when all of the following are present:

1. The JSR-107 API (`javax.cache`).
2. The `spring-context-support` module.
3. `@EnableCaching` or XML `<cache:annotation-driven/>`.
4. An appropriate `CacheManager` in the Spring context.

With Spring Boot, `spring-boot-starter-cache` already includes `spring-context-support`; add the JCache API if your application uses JCache annotations. There is no separate `@EnableJCache` annotation to add.

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

This is a simple Spring `CacheManager` configuration that works with JCache annotations. If your application has an actual JCache provider such as Ehcache 3, Hazelcast, or Infinispan, Spring Boot can auto-detect the `CachingProvider` and create a `JCacheCacheManager`.

Example properties when forcing Spring Boot to use a JCache provider:

~~~properties
spring.cache.type=jcache
spring.cache.jcache.provider=org.ehcache.jsr107.EhcacheCachingProvider
spring.cache.jcache.config=classpath:ehcache.xml
~~~

This snippet applies only when the corresponding Ehcache/provider dependency and `ehcache.xml` file exist on the classpath. When multiple JCache providers are present, specify the provider explicitly. Note that declaring a custom `CacheManager` bean prevents auto-configuration from replacing it with another provider.

## 11. When to Choose JCache Annotations vs. Spring Annotations?

JCache fits projects that require the JSR-107 standard annotations, want easier portability across frameworks/providers, or integrate with existing JCache systems. Spring annotations offer SpEL expressions and options tailored closely to the Spring programming model.

| Criterion | JCache | Spring Cache |
| --- | --- | --- |
| API | JSR-107 standard | Spring API |
| Read operation | `@CacheResult` | `@Cacheable` |
| Cached value on put | `@CacheValue` parameter | Method return value |
| Key selection | `@CacheKey`, `CacheKeyGenerator` | SpEL `key`, `KeyGenerator` |
| Cache name | `cacheName` | `cacheNames`/`value` |
| Conditions | No direct SpEL `condition`/`unless` equivalent | Supports `condition`, `unless` |
| Bypass cache lookup | `skipGet=true` on `@CacheResult` | Different semantics, not a direct substitute |
| Exception caching | Dedicated exception cache support | No equivalent standard annotation mechanism |
| Evict entry | `@CacheRemove` | `@CacheEvict` |
| Clear entire cache | `@CacheRemoveAll` | `@CacheEvict(allEntries=true)` |
| Class-level defaults | `@CacheDefaults` | `@CacheConfig` |
| Caches per operation | JCache resolver selects one cache | Spring annotations can target multiple caches |

Spring Boot recommends against mixing both annotation sets arbitrarily. Spring Framework permits different services to use either set, but if both operate on **the same cache**, you must align key generation and cache identity.

Dangerous example:

~~~java
// Spring: default key for a single String parameter may be that String itself.
@org.springframework.cache.annotation.Cacheable("products")
public Product findSpring(String id) {
    return repository.find(id);
}

// JCache: default key is a GeneratedCacheKey wrapping the parameter.
@javax.cache.annotation.CacheResult(cacheName = "products")
public Product findJCache(String id) {
    return repository.find(id);
}
~~~

Despite sharing the name `"products"` and input `"P1"`, their default key representations may differ. Never assume they share the same cache entry. If interoperability is mandatory, design and test a compatible key generator for both.

## 12. Limitations and Data Considerations

### No SpEL-Based `condition`/`unless`

JCache has no direct SpEL equivalents to Spring `@Cacheable`'s `condition` and `unless`. `skipGet` only controls whether pre-lookup happens; it does not filter results. If you need complex input/result-based decisions, consider explicit cache API calls, separate business methods, or custom resolvers/generators.

### Keys Must Capture Full Data Scope

If a product ID is unique only within a tenant, the key must include both `tenantId` and `productId`. If results vary by locale, projection, or caller, include those dimensions as well. Never let a cache hit bypass authorization checks inside the method body; authorization must run on a path that always executes.

### TTL and Eviction Remain Managed by the Provider

JCache annotations do not configure TTL, maximum size, or eviction policies themselves. Those policies belong to the cache provider. `@CacheRemove` and `@CacheRemoveAll` execute only when invoked according to the configured after/before-invocation semantics.

### Exception Caching Can Retain Stale Errors

If an error is transient, exception caching causes callers to keep receiving the stale error for the lifetime of the entry. Cache only stable errors and set a dedicated expiration on the exception cache. Test both `cachedExceptions` and `nonCachedExceptions`.

### Transactions and Cache Updates

By default, `@CachePut` writes after the method completes successfully, yet does not guarantee atomicity between database and cache. With transaction rollbacks, post-commit events, multiple replicas, or concurrent updates, define exact write/evict timing and test against the real provider. Do not use `afterInvocation=false` unless you accept the risk of modifying cache state before business logic succeeds.

### Nulls and Cache Providers

Null caching depends on the abstraction and provider. Never assume every JCache provider stores nulls identically; check provider contracts and configuration. When no valid value exists, design explicit negative caching or skip caching according to a clear policy.

## 13. Testing and Diagnostics

An integration test must verify that operations are actually intercepted and keys match:

| Test Case | Action | Expected Result |
| --- | --- | --- |
| Result miss | Call `find(P1)` the first time | Method executes, source counter increments |
| Result hit | Call `find(P1)` a second time | Method skipped, counter stays unchanged |
| Put | Call `rename(P1, updatedProduct)` then find | Returns the new `@CacheValue` |
| Remove | Delete P1 then recreate source with a new value | Next read fetches new value, does not hit stale entry |
| Remove all | Cache P1 and P2, call invalidateAll | Both subsequent reads miss |
| Key selection | Add traceId without `@CacheKey` | TraceId does not affect the key |
| Key scope | Two tenants with the same ID | Entries are isolated when data differs |
| Exception | Method throws configured exception | Caching/removal obeys `cachedExceptions`, `evictFor`, and `afterInvocation` |
| Proxy | Invoke via injected bean | Interceptor is triggered |
| Self-invocation | Call `this.find(...)` | Recognize proxy bypass |
| Real provider | Run with Ehcache/Redis/Hazelcast | Serializer, TTL, key, and exception semantics behave properly |

### Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@CacheResult` never hits | Different key or different cache name | Check `@CacheKey`, key generator, and cache name |
| `@CachePut` writes the wrong value | Missing `@CacheValue` or wrong Spring annotation import | Use `javax.cache.annotation.CacheValue` and verify imports |
| Read still sees stale data after update | Put key differs from result key | Align `@CacheKey` across read, put, and remove |
| Deleted P1 but cache remains | Method threw an exception with `afterInvocation=true` | Check `evictFor`/`noEvictFor` or invocation timing |
| Cleared region but only one cache changed | Different `cacheName` or resolver | Verify cache name and resolver |
| Two annotation families do not share entries | Different default key generators | Stick to one annotation set or use compatible key generators |
| JCache annotations do nothing | Missing JCache API or `spring-context-support`, caching not enabled | Verify dependencies and `@EnableCaching` |
| Cached method is not intercepted | Self-invocation or non-Spring-managed bean | Invoke through the Spring proxy |
| Stale exception keeps getting thrown | Exception cache entry has not expired | Check `exceptionCacheName` and TTL |
| Cache cleared, so database was cleared too? | Confusing `@CacheRemoveAll` with business deletion | Annotation only clears cache; method body governs source data |

## 14. Self-Check Exercises

**Exercise 1.** `@CacheResult(cacheName="products")` is called twice with the same ID. Does the second call execute the method?  
**Answer:** If the entry exists and hits in the cache, the method does not execute; the cached value is returned.

**Exercise 2.** Does JCache `@CachePut` store the return value or a parameter?  
**Answer:** The parameter annotated with `@CacheValue`. This is a major difference from Spring's `org.springframework.cache.annotation.CachePut`.

**Exercise 3.** Method `find(String id, String traceId)` annotates only `id` with `@CacheKey`. Does trace ID participate in the key?  
**Answer:** No. Once at least one `@CacheKey` is present, only the annotated parameters are used to construct the key.

**Exercise 4.** By default, does `@CacheRemove` remove before or after the method?  
**Answer:** After the method completes successfully (`afterInvocation=true`). It can be changed to `false` to remove before invocation.

**Exercise 5.** Does `@CacheRemoveAll` delete database records?  
**Answer:** No. It removes all entries from the specified cache; source data changes only if the method body performs that change.

**Exercise 6.** Can JCache annotations be used with `ConcurrentMapCacheManager`?  
**Answer:** Yes. Spring supports JCache annotations on top of its cache abstraction without requiring a JCache provider as the backing store.

**Exercise 7.** Why might Spring `@Cacheable` and JCache `@CacheResult` fail to see each other's entries?  
**Answer:** Their default key generators differ; Spring uses `SimpleKeyGenerator`, whereas JCache builds a `GeneratedCacheKey` from the selected parameters.

**Exercise 8.** What does `skipGet=true` mean?  
**Answer:** It skips the cache lookup before running the method; the method always executes and its return value is still cached. It is not identical to JCache `@CachePut` with `@CacheValue`.

**Exercise 9.** When should exceptions be cached?  
**Answer:** Only for stable, deterministic errors reusable for the same key. Transient errors like timeouts or database unavailability should generally not be cached.

## Official References

- Spring Framework – JCache (JSR-107) Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html
- Spring Framework – Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot – Caching, JCache provider detection and configuration: https://docs.spring.io/spring-boot/reference/io/caching.html
- JCache 1.1.1 – `CacheResult`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheResult.html
- JCache 1.1.1 – `CachePut`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html
- JCache 1.1.1 – `CacheRemove`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemove.html
- JCache 1.1.1 – `CacheRemoveAll`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemoveAll.html
- JCache 1.1.1 – `CacheKey`, `CacheValue`, and package API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/package-summary.html

**Takeaway:** `@CacheResult` reads and caches the method result; JCache `@CachePut` always executes and stores the `@CacheValue` parameter; `@CacheRemove` deletes one key; `@CacheRemoveAll` clears the whole region. Spring supports these annotations when the JCache API and `spring-context-support` are present alongside `@EnableCaching`. Pay special attention to key generation differences and imports between JCache and Spring `@CachePut`.