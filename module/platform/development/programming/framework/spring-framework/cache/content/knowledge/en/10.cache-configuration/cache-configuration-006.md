# Custom Composed Annotations for Shared Conventions in Spring Cache

## 1. Goal and Context

Spring Framework supports `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, and `@CacheConfig`. When multiple services follow the same rules, repeating cache names, key expressions, and conditions can introduce inconsistency errors. A **custom composed annotation** lets you define a meaningfully named convention once and reuse it across many methods.

After this lesson, you will know how to:

1. Create custom annotations based on the `@Cacheable`, `@CachePut`, and `@CacheEvict` meta-annotations.
2. Use `@Target` and `@Retention(RUNTIME)` properly so Spring detects the metadata.
3. Standardize cache name, key, `unless`, and manager/resolver choice where appropriate.
4. Use `@AliasFor` to allow controlled overriding of selected attributes.
5. Distinguish a composed annotation from `@CacheConfig` and `@EnableCaching` setup.
6. Write a runnable Java 17/Spring Boot example along with tests to catch proxy, key, and cache invalidation bugs.

The running example is a service that reads, renames, and deletes products. All operations must use the **same cache identity** so updates take effect for subsequent reads.

## 2. The Problem with Repeated Declarations

Suppose product read methods all declare:

~~~java
// Illustrative inside a Spring-managed service.
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

A new service might omit `unless`, accidentally change `"productsById"` to `"products"`, or use all arguments as the key. An update method might use `@CachePut` while including the `newName` argument in the key, leaving stale data readable. As the system grows, finding and fixing every annotation manually becomes error-prone.

Let's define an annotation whose name carries business meaning:

~~~java
@CachedProduct
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

`@CachedProduct` is shorthand for **a concrete convention**: use cache `"productsById"`, take the first argument as the key, and do not store null results. When rules are centralized, the annotation name lets reviewers understand the policy right at the call site.

However, the correctness of the convention still depends on method signatures and data: `#p0` is valid only if the first argument is the product identifier and uniquely distinguishes every result in that cache. The annotation does not automatically infer tenant, locale, user, projection type, or access permissions.

## 3. How Does Spring Interpret Meta-Annotations?

Java allows an annotation to be placed on another annotation. Spring Cache recognizes `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@CacheConfig` as **meta-annotations** in supported caching infrastructure.

A minimal definition:

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public @interface CachedProduct {}
~~~

Explanation:

| Component | Function |
| --- | --- |
| `public @interface CachedProduct` | Defines a custom-named Java annotation |
| `@Target(ElementType.METHOD)` | Specifies the annotation can be placed on methods |
| `@Retention(RetentionPolicy.RUNTIME)` | Retains metadata at runtime so Spring can inspect it |
| `@Documented` | Includes the annotation in Javadoc; does not enable caching on its own |
| `@Cacheable(...)` | The actual cache operation Spring executes |
| `cacheNames = "productsById"` | Shared cache region name |
| `key = "#p0"` | SpEL picking the method's first argument as the key |
| `unless = "#result == null"` | Prevents putting newly computed null results into the cache |

**Important:** creating the annotation alone is not enough. The application must enable caching, have an appropriate `CacheManager`, and go through a Spring proxy/interceptor. Composed annotations do not alter `@Cacheable`'s cache hit/miss evaluation rules.

### Execution flow

~~~text
Caller invokes bean with @CachedProduct
                 |
                 v
             Spring proxy
                 |
                 v
Read @CachedProduct metadata
  -> meta @Cacheable(cacheNames="productsById",
                     key="#p0", unless="#result == null")
                 |
                 v
CacheManager checks "productsById" cache, key by ID
             /             \
           HIT             MISS
            |                |
     Return cached      Execute method
         data                |
                             v
                       Check unless
                         /       \
                      true       false
                       |           |
                   Do not put   Put cache
                       \           /
                       Return result
~~~

On a cache hit, the method may not run. `unless` is used to decide whether to store **the new result** on the miss path; it does not re-check an already cached entry. If the data source changes, `@CachePut`, `@CacheEvict`, TTL, or a separate synchronization mechanism is needed.

## 4. A Convention Needs a Clear Contract

A shared annotation should include documentation describing its assumptions:

~~~text
Name: @CachedProduct
Behavior: @Cacheable
Cache: productsById
Key: first argument, String type, globally unique productId
Value: Product or null
Not cached: null
Use only for: methods reading Product by productId
Do not use for: list queries, unscoped multi-tenant methods, different DTO types
~~~

Decision table:

| Method | Should it use this `@CachedProduct`? | Explanation |
| --- | --- | --- |
| `find(String productId)` | Yes, if ID is unique | First argument is the exact cache identity |
| `find(String productId, String traceId)` | Possibly | Ignores traceId if it does not affect the content |
| `find(String tenantId, String productId)` | **No** | `#p0` is only tenantId; multiple products collide on the same key |
| `findSummary(String productId)` | Not by default | Summary and Detail have different projections |
| `search(String category, int page)` | No | List results need a dedicated key |
| `rename(String id, String name)` | Use matching put annotation | Updates must always run and return the new Product |
| `delete(String id)` | Use matching evict annotation | Removes entry after deleting from source |

If a product is only unique within each tenant, the cache identity must include **`tenantId` and `productId`** or the cache name must be partitioned properly. If results vary by viewer or locale, the key must reflect those factors as well. **Do not** blindly apply a single ID-based annotation to every method merely because they read the same entity.

## 5. Complete Example: Three Annotations for Read/Put/Evict

This example uses **Java 17, Spring Boot 3.3.5, Maven**, and `ConcurrentMapCacheManager`. For clarity, `productId` here is globally unique across the application; `ConcurrentHashMap` merely simulates the data source. We create three custom annotations:

- `@CachedProduct` uses meta `@Cacheable` to read and cache results.
- `@PutProductCache` uses meta `@CachePut` to update the entry after the method runs.
- `@EvictProductCache` uses meta `@CacheEvict` to delete the entry.

All three share the same **cache name** and **key**. Thus `rename(id,newName)` replaces the exact entry used by `find(id)`, even though the update signature has two arguments.

### Directory Structure

~~~text
composed-cache-demo/
├── pom.xml
└── src/main/java/example/cache/
    ├── DemoApplication.java
    ├── CachedProduct.java
    ├── PutProductCache.java
    ├── EvictProductCache.java
    └── ProductService.java
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
    <artifactId>composed-cache-demo</artifactId>
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

### `src/main/java/example/cache/CachedProduct.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        unless = "#result == null"
)
public @interface CachedProduct {}
~~~

### `src/main/java/example/cache/PutProductCache.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.CachePut;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@CachePut(
        cacheNames = "productsById",
        key = "#p0"
)
public @interface PutProductCache {}
~~~

`@CachePut` always executes the method and then caches the **return value**. It does not take the `newName` parameter as the cached value, nor does it skip the method when data is already cached.

### `src/main/java/example/cache/EvictProductCache.java`

~~~java
package example.cache;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.CacheEvict;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@CacheEvict(
        cacheNames = "productsById",
        key = "#p0"
)
public @interface EvictProductCache {}
~~~

By default, `@CacheEvict` deletes after the method completes successfully. In the demo, this removes the cache entry of a product that was deleted from the source.

### `src/main/java/example/cache/ProductService.java`

~~~java
package example.cache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ConcurrentMap<String, Product> store =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceLoads = new AtomicInteger();

    public record Product(String id, String name, int version) {}

    public ProductService() {
        store.put("P1", new Product("P1", "Pen", 1));
    }

    @CachedProduct
    public Product find(String id) {
        sourceLoads.incrementAndGet();
        return store.get(id);
    }

    @PutProductCache
    public Product rename(String id, String newName) {
        return store.compute(id, (key, oldValue) -> {
            if (oldValue == null) {
                throw new IllegalArgumentException("Unknown product");
            }
            return new Product(id, newName, oldValue.version() + 1);
        });
    }

    @EvictProductCache
    public void delete(String id) {
        store.remove(id);
    }

    public int sourceLoads() {
        return sourceLoads.get();
    }
}
~~~

### `src/main/java/example/cache/DemoApplication.java`

~~~java
package example.cache;

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
        return new ConcurrentMapCacheManager("productsById");
    }

    @Bean
    CommandLineRunner demo(ProductService products) {
        return args -> {
            System.out.println(products.find("P1"));
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());

            System.out.println(products.rename("P1", "Blue Pen"));
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());

            products.delete("P1");
            System.out.println(products.find("P1"));
            System.out.println("loads=" + products.sourceLoads());
        };
    }
}
~~~

### Run and Verify

Run from the `composed-cache-demo` directory with Java 17+ and Maven:

~~~bash
mvn -q spring-boot:run
~~~

Besides Spring startup logs, `CommandLineRunner` prints:

~~~text
Product[id=P1, name=Pen, version=1]
Product[id=P1, name=Pen, version=1]
loads=1
Product[id=P1, name=Blue Pen, version=2]
Product[id=P1, name=Blue Pen, version=2]
loads=1
null
loads=2
~~~

Explanation:

1. The first `find("P1")` misses, executes the method, and caches `Pen/v1`; the second hits, so `loads=1`.
2. `rename("P1","Blue Pen")` still executes even when `"P1"` is already cached. The meta `@CachePut` annotation writes `Blue Pen/v2` under the exact key `"P1"`; the subsequent read hits v2, and `loads` stays 1.
3. `delete("P1")` removes from the source and the meta `@CacheEvict` removes entry `"P1"`. The next read misses, executes the method returning `null`, and increments `loads=2`.
4. Because composed `@CachedProduct` has `unless="#result == null"`, this read returning `null` does **not** store a new entry.

**Demo scope:** the cache is JVM-local, without TTL, tenant authorization, database transactions, or cross-instance synchronization. When switching to Redis/Caffeine, verify cache definitions, serializers, and expiration policies.

## 6. `@AliasFor`: Creating Annotations That Are Both Standardized and Flexible

Fixed annotations make governance clear. However, a group of methods may share the same **cache name** while needing different **keys** and **unless** expressions. Spring provides `@AliasFor` for controlled customization of meta-annotation attributes.

Example creating `@CachedReport`:

~~~java
package example.reports;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.core.annotation.AliasFor;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Cacheable(cacheNames = "reportViews")
public @interface CachedReport {

    @AliasFor(annotation = Cacheable.class, attribute = "key")
    String key() default "";

    @AliasFor(annotation = Cacheable.class, attribute = "unless")
    String unless() default "";
}
~~~

Usage on a report read method:

~~~java
// Illustrative snippet: Report and repository are supplied by the application.
@CachedReport(
        key = "T(java.util.List).of(#p0, #p1)",
        unless = "#result == null"
)
public Report find(String tenantId, String reportId) {
    return repository.find(tenantId, reportId);
}
~~~

Spring reads the meta `@Cacheable(cacheNames="reportViews")` and applies the attributes overridden via `@CachedReport`. The region name stays fixed; the key expression uses `(tenantId, reportId)` to avoid collisions between two tenants having the same reportId. `List.of(...)` rejects nulls and is a structural key suitable for in-memory demos; for backends like Redis, define the serializer/key codec properly.

### Rules when using `@AliasFor`

- The aliased attribute must actually exist on the meta-annotation. For example, `Cacheable.key` and `Cacheable.unless` are both `String` with empty defaults.
- Declaring `@AliasFor(annotation = Cacheable.class, attribute = "key")` means `key()` on the custom annotation overrides `key` on the meta `@Cacheable`.
- Data types must match. `cacheNames` is `String[]`, `sync` is `boolean`, `key` is `String`; never create aliases with mismatched types.
- Defaults of aliased/overriding attributes must obey Spring's contract; using `""` for string attributes in the example is valid.
- Do not expose every attribute just because you can. If the cache name is fixed by a shared convention, keep `cacheNames` locked instead of letting callers change it arbitrarily.
- A single operation must not declare both `key` and `keyGenerator`; likewise `cacheManager` and `cacheResolver` are mutually exclusive pairs.
- Avoid duplicate aliases or conflicting values. Test that Spring synthesizes the right merged annotation metadata and reads the right cache entries.

`@AliasFor` does not automatically make keys safe, enforce permissions, or replace `CacheResolver`. If key semantics are complex, use a `KeyGenerator` with a clear contract or a dedicated annotation for that group of methods.

### When is an annotation without attributes better?

If both the region name and key rule are always fixed, `@CachedProduct` from the first example is easier to review than `@CachedProduct(key="...")` on every method. Flexibility should be added for real needs, not merely to avoid creating multiple annotation names.

## 7. Comparing Composed Annotations and `@CacheConfig`

`@CacheConfig` shares **class-level defaults** such as cache name, `KeyGenerator`, `CacheManager`, or `CacheResolver`. It **does not mark which methods will be cached**.

~~~java
// Illustrative inside a service; repository and Product belong to the application.
@Service
@CacheConfig(cacheNames = "productsById")
public class ProductLookup {
    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }
}
~~~

In contrast, `@CachedProduct` contains meta `@Cacheable`, so placing it on a method directly **marks a cache operation**.

| Tool | Application Level | Purpose |
| --- | --- | --- |
| `@EnableCaching` | Application context/configuration | Enables caching annotation processing |
| `CacheManager`/`CachingConfigurer` | Application context | Defines backend and global defaults |
| `@CacheConfig` | Class | Shares default config across methods in the class |
| `@Cacheable`/`@CachePut`/`@CacheEvict` | Operation | Marks cache read, write, and delete operations |
| Composed annotation | Multiple operations across classes | Encapsulates operations and shared conventions |
| `@AliasFor` | Composed annotation definition | Enables selective overriding of meta attributes |

When a composed annotation explicitly specifies `cacheNames`, that is operation-level configuration; do not expect `@CacheConfig(cacheNames="other")` on the class to change that name. Spring's general precedence order gives specific operation configuration priority over class and global defaults.

`@CacheConfig` can also be used as a meta-annotation per Spring documentation, yet you must distinguish **default configuration** from **marking an operation**. Start with the simplest approach that meets the need.

## 8. Maintaining Consistency Across Read, Update, and Invalidation

If you create separate annotations for read, update, and evict, ensure they all target:

~~~text
CacheManager: same backend
cacheName:    productsById
cacheKey:     productId
cachedValue:  Product with matching projection
~~~

Even when annotations encourage reuse, if a signature changes from:

~~~java
public Product rename(String id, String newName)
~~~

to:

~~~java
public Product rename(UpdateRequest request, String id)
~~~

then the `key="#p0"` convention **no longer extracts the ID**. `@PutProductCache` would write under the request object, while `@CachedProduct` by ID continues hitting the old entry.

For diverse signatures, use a tested shared `KeyGenerator` or build dedicated annotations with appropriate keys. Do not write an overly generic composed annotation and force incompatible methods to use it.

A `@CachePut` should only be used when the method returns **the exact value** expected by readers. If an update method returns `boolean`, `void`, or an ID, consider `@CacheEvict` so the next read reloads the canonical DTO. For `null` results, an `unless` on put can refuse to write but **does not remove the old entry**; business logic must decide when to evict.

If an update affects list/search/report caches, putting by ID does not refresh those regions automatically. You can use `@Caching` to group multiple evicts/puts when related keys are known, or use event-based invalidation, versioning, and suitable TTLs.

## 9. Proxy, AspectJ, and Method Visibility Limits

Spring recognizes composed cache annotations in supported **proxy** mode. That does not mean the annotation causes every call to be intercepted:

- `@EnableCaching` must be enabled in Spring configuration, with an appropriate `CacheManager`/provider.
- Placing annotations on `public` methods of concrete Spring-managed beans has the fewest surprises.
- Calls from another bean going through the proxy are intercepted. Calling `this.find(id)` inside the same bean typically **does not** go through the proxy.
- Do not rely on caching advice for calls inside constructors or `@PostConstruct`, when proxies are not yet fully active.
- When annotations are placed on interfaces or non-public methods, behavior depends on the proxy/weaving mechanism; test on the actual configuration.
- With **AspectJ weaving**, the standard cache aspects in `spring-aspects` support standard annotations. Custom annotations require configuring/writing a matching aspect to be recognized in that mode; do not assume parity with proxy mode.
- Do not also attach `@Cacheable` directly on a method that already uses a composed `@Cacheable` just "to be safe": multiple operations with the same effect can cause duplication or unpredictable semantics.

If an annotation is intended for class usage, do not blindly expand `@Target(TYPE)` without checking how cache operations apply to methods. This example intentionally permits only `METHOD`.

## 10. Data Scope, Security, and Consistency

**A composed annotation is not an authorization boundary.** If results vary by user, tenant, role, locale, or permission, the cache key must reflect all factors affecting the output; additionally, every request must be authorized in the right place.

Anti-pattern:

~~~java
// ANTI-PATTERN: never place the only permission check inside the cached method body.
@CachedProduct
public Product find(String id) {
    authorizeCurrentUser(id);
    return repository.find(id);
}
~~~

On a cache hit, Spring can skip the method body so `authorizeCurrentUser` never runs. Perform authorization in a facade/entrypoint that always executes before the cached service, or order interceptors with tested precedence. Scope identifiers must come from a trusted principal/context, never solely from client-supplied strings.

**Composed annotations also do not guarantee transactional consistency.** A `@CachePut` can write to the cache at a different moment than the database commit; on rollback or read/write races, cached entries may diverge from the data source. Apply post-commit policies, transaction-aware caches, versioning, locking, or event invalidation as required. JVM-local caches do not sync across replicas automatically.

Changing key conventions or cache names during deployment can make old entries unreachable, or leave multiple instances using two different encodings. Plan rollouts, versioning, and clearing old entries, especially with Redis.

## 11. Testing Composed Annotations

Do not merely use reflection to verify that a Java annotation carries `@Cacheable`. What must be proved is **actual runtime behavior through the Spring container**.

| Test Case | How to Execute | Expected Result |
| --- | --- | --- |
| Cache hit | Call `find("P1")` twice via injected bean | Source executes only once |
| Same-key update | `rename("P1","Blue Pen")`, then `find("P1")` | Reads new version immediately; source count unchanged |
| Evict | `delete("P1")`, then `find("P1")` | Does not return old entry |
| `unless` | Call `find("missing")` twice | Null result is not cached; source runs again |
| `@AliasFor` | Use `@CachedReport(key=...)` | Key uses the overridden expression accurately |
| Wrong signature | ID at a position other than `#p0` | Test catches wrong identifier |
| Wrong cacheName | Put and read target different regions | Test catches stale read |
| Multi-tenant | Two tenants share the same product ID | Data never leaks across differing scopes |
| Self-invocation | Call `this.find(...)` inside the same bean | Recognizes proxy is bypassed |
| Configuration | `@EnableCaching` omitted | Do not expect cache advice to run |
| Real provider | Redis/Caffeine | Serializer, TTL, key, and invalidation compatible |

Tests can be implemented using `@SpringBootTest`, injecting the service and `CacheManager`, and directly asserting counters or mock repository invocation counts. A unit test doing `new ProductService()` has no Spring proxy and therefore does not prove caching works.

### Common Error Diagnostics

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Custom annotation does not trigger caching | `@EnableCaching` not enabled, wrong bean/proxy | Check configuration and call path |
| Annotation not recognized at runtime | Wrong retention/target or meta-annotation | Use `RUNTIME`, `METHOD`, test contract |
| `@AliasFor` does not override as expected | Wrong attribute name/type or meta metadata | Check Javadoc and integration tests |
| `@CachedProduct` mixes up products | First argument is not a unique productId | Design identity covering the full scope |
| Put does not update read entry | Different key, cache name, or manager | Compare cache identity of both operations |
| Cache holds Boolean instead of Product | Placed `@CachePut` on a status-returning method | Use `@CacheEvict` or return full Product |
| Hit after source changed | Missing invalidation | Use put/evict/TTL or versioning |
| Same annotation behaves differently under AspectJ | Standard aspect ignores custom annotation | Configure custom aspect or use proxy mode |
| Tests show no cache hit | Service created with `new`, internal call | Test through injected Spring bean |
| Cache inconsistent across replicas | Using local `ConcurrentMapCacheManager` | Pick shared backend if business needs it |

## 12. Organizing Cache Conventions as a Shared API

In a multi-module codebase, annotations can live in a package like `com.example.shared.cache`. Each annotation needs Javadoc describing:

- Data scope and usage conditions: global product ID, per-tenant, per-user, or per-projection.
- Which parts of the signature form the key; whether `null` or `Optional` is handled.
- What return type the method must have so `@CachePut` writes safely.
- Whether the cache name is fixed by the annotation or overridable; if overridable, valid constraints.
- Whether it depends on specific named `KeyGenerator`, `CacheResolver`, or `CacheManager` beans.
- Related invalidation policies; especially lists, searches, and statistics dependent on updated data.
- Test suite and versioning plan when changing key schemas/namespaces.

Annotation names should express business intent like `@CachedProductById` or `@EvictProductById`, avoiding vague names like `@Fast` or `@Cached` that hide too much behavior. One annotation can reduce boilerplate, yet it can also spread configuration bugs widely; therefore, the more widely an API is used, the clearer its contract tests must be.

## 13. Practice Exercises

**Exercise 1.** Multiple services use `@Cacheable(cacheNames="productsById", key="#p0", unless="#result == null")`. What should you do?  
**Answer:** create a composed `@CachedProduct` with a meta-annotation containing those attributes; document the contract that `#p0` is a unique product ID.

**Exercise 2.** Can `find(String tenantId, String productId)` use the example's `@CachedProduct`?  
**Answer:** not safely. Key `#p0` is the tenant ID, causing different products in one tenant to collide. You need a key containing `(tenantId,productId)` or tenant-partitioned cache regions with reliable rules.

**Exercise 3.** Why is `@Retention(RUNTIME)` required?  
**Answer:** so annotation metadata is preserved at runtime, allowing Spring to discover and interpret it as a cache operation.

**Exercise 4.** Does `@CachedProduct` enable caching on its own instead of `@EnableCaching`?  
**Answer:** no. The annotation is metadata; Spring needs configuration enabling cache interception and an appropriate manager.

**Exercise 5.** When should `@AliasFor` expose a `key` override?  
**Answer:** when a group of methods shares the same cache name/rules but needs controlled variations in how keys are built. If all methods use one fixed key, an attribute-less annotation is usually simpler.

**Exercise 6.** If `rename(String id,String name)` changes to return `boolean`, is `@PutProductCache` still suitable?  
**Answer:** no if the read region stores `Product`. `@CachePut` would put a `Boolean`; either return the updated `Product` or use eviction.

**Exercise 7.** A method in the same bean calls `this.find("P1")`; does the composed annotation guarantee caching works?  
**Answer:** not in default proxy mode, because self-invocation normally bypasses the proxy. Test via a Spring-managed bean and structure calls appropriately.

**Exercise 8.** Can a composed annotation be used with AspectJ weaving without changing anything?  
**Answer:** do not assume so. Standard aspects recognize standard cache annotations; custom annotations may need a custom aspect or proxy mode.

## Official Documentation

- Spring Framework, Declarative Annotation-based Caching, **Using Custom Annotations** section: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Annotation Programming Model, `@AliasFor`: https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model
- Javadoc `@AliasFor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Boot, Caching providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Takeaway:** composed annotations turn repeated cache operations and rules into **one unified API**. They standardize cache names/keys/conditions, yet do not enable caching on their own, do not replace permission checks, do not handle source data changes, and do not bypass Spring proxy limitations. Design clear shared contracts and test actual runtime behavior before broad adoption.