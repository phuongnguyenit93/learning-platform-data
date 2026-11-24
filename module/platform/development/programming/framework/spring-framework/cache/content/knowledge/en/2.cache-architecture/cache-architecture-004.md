# KeyGenerator and Mapping Method Calls to Keys in Spring Cache

## Learning Objectives

After this lesson, you will be able to explain why every cached invocation needs a stable key; predict the key Spring generates by default; choose between `key` (SpEL) and `keyGenerator`; write a reusable `KeyGenerator`; and ensure read, update, and evict operations point to the same cache entry. The focus is on **mapping a method invocation to a key** in the Spring Cache architecture, not configuring TTLs or choosing a cache provider.

## 1. How Does an Invocation Become a Cache Entry?

A cache entry can be visualized as the pair `(cache name, key) → value`. The cache name identifies the storage space, while the key distinguishes results within that space. For example, calls `find("tenant-A", "P1")` and `find("tenant-B", "P1")` must have different keys if each tenant has its own data. Two methods sharing the `"catalog"` cache can also accidentally collide on keys; **Spring does not automatically include the method name in the default key**.

For a call intercepted by Spring AOP through a proxy, the `@Cacheable` flow can be read as follows:

1. Spring receives the target method, arguments, and cache configuration; it evaluates `condition` if present.
2. Spring resolves the caches via `cacheNames`/`CacheResolver`, then computes the key using a `key` expression or a `KeyGenerator`.
3. Cache **hit**: Spring returns the stored result without executing the method body (for standard `@Cacheable` cases).
4. Cache **miss**: Spring executes the method; if the post-execution condition (`unless`) permits, it stores the value under that exact key.

This is a logical model to understand component responsibilities; exact ordering and asynchronous handling depend on operation type and version/provider. Specifically, `@CachePut` **always invokes the method** and then updates the cache; `@CacheEvict` removes the entry by key or clears the entire cache when `allEntries=true`.

~~~text
Call find(tenantId, productId)
          |
          v
  Cache interceptor / annotation
          |
          +-- Select cache: "catalog"
          +-- Generate key: (tenantId, productId)
                      |
                cache.get(key)
                 +----+----+
               HIT        MISS
                |           |
           Return value   Invoke method
                            |
                       cache.put(key, value)
                            |
                        Return value
~~~

`KeyGenerator` is only responsible for **choosing the key**. `CacheResolver`/`CacheManager` decides **which cache** is used; the provider (ConcurrentMap, Caffeine, Redis...) handles storage and expiration policies. A good key alone does not create TTLs, synchronize data, or prevent stale data.

## 2. Default Key: `SimpleKeyGenerator`

When an operation declares neither `key` nor `keyGenerator`, Spring uses `org.springframework.cache.interceptor.SimpleKeyGenerator`. Key cases:

| Call arguments | Default key form | Meaning |
| --- | --- | --- |
| No arguments | `SimpleKey.EMPTY` | All zero-argument calls to the same method/cache share one key. |
| Single non-`null`, non-array argument | The argument object itself | Requires proper `equals()` and `hashCode()`. |
| Two or more arguments | A `SimpleKey` holding all arguments | Argument order and values participate in equality. |
| Single argument that is `null` or an array | A `SimpleKey` | Special case, avoiding raw `null`/arrays directly as keys. |

For example, `lookup("P1")` has key `"P1"`; `lookup("A", "P1")` has a composite key equivalent to `SimpleKey("A", "P1")`. This describes the **key structure**, not a guarantee that `toString()` is used as the storage key.

The default approach is convenient when **every argument truly determines the result**, has stable equality, and the backend accepts that key type. It can cause problems:

- `findById("42")` and `findBySku("42")` sharing `cacheNames="products"`: by default both produce `"42"` even though the two methods have different semantics.
- A `tenantId` parameter omitted from a custom key: two tenants can read each other's results.
- Keys based on stateful objects, mutable arrays/collections, or classes whose `equals/hashCode` do not match business identity: unstable hit/miss behavior.
- Complex DTO arguments can still serve as keys in local caches, but distributed backends may require dedicated conversion/serializers.

Do not simply compute `hashCode()` and use that integer as the key: different objects can have hash collisions. A key still requires consistent `equals()` semantics. Modern `SimpleKey` compares its constituent elements, rather than taking a combined hash as in the legacy strategy prior to Spring 4.

## 3. Selecting Keys with SpEL When Only One Operation Needs Customization

The `key` attribute on `@Cacheable`, `@CachePut`, and `@CacheEvict` accepts a Spring Expression Language (SpEL) expression. You can pick the exact arguments affecting the result without creating a new bean:

~~~java
// Declarative illustration; Product/Report types belong to the app, not standalone runnable.
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String id) { return loadProduct(id); }

@Cacheable(cacheNames = "productsByTenant", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String id) { return loadProduct(tenantId, id); }

@Cacheable(cacheNames = "reports", key = "#root.methodName + ':' + #p0")
public Report report(String id) { return generateReport(id); }
~~~

`#p0` or `#a0` is the first argument, `#p1` is the second argument; `#root.args[0]` also accesses the first argument. `#root.methodName`, `#root.method`, and `#root.targetClass` expose invocation metadata. Names like `#tenantId` only work if Spring can resolve parameter names (for instance, compiled with `-parameters`); positional syntax `#p0` is generally less dependent on compiler flags.

The string concatenation expressions above are concise for illustration, but can suffer from **delimiter collisions**: `("a:b","c")` and `("a","b:c")` yield the same string. For identifiers that may contain `:`, choose an unambiguous encoding or an immutable structured key (such as the `record` shown later). If strings are used with Redis, consider normalization and corresponding serialization.

`key` and `keyGenerator` are **mutually exclusive on the same annotation**. Declaring both triggers a configuration error; there is no "prefer one then fall back to the other" mechanism. A `key` expression for `@Cacheable` is evaluated before running the method and thus cannot depend on `#result`; `#result` is appropriate in post-execution expressions such as `unless`.

## 4. When to Write a Custom `KeyGenerator`?

Choose `KeyGenerator` when multiple operations need the same key rule, when arguments must be normalized, or when you want a key object with explicit `equals/hashCode`. Spring's contract is:

~~~java
package org.springframework.cache.interceptor;

public interface KeyGenerator {
    Object generate(Object target, java.lang.reflect.Method method, Object... params);
}
~~~

This is an **illustrative API signature**, not a file to create in the application. `target` is the target instance, `method` is the invoked method, and `params` are the arguments; the return value becomes the cache key. You may inspect `method` to distinguish operations, but should only do so if all read/write/evict paths genuinely share the **same identity rule**.

A reliable generator should:

1. Depend on the inputs that **determine the result**: tenant, id, version, language, filter options, or pagination if they change the output.
2. Return the same key for equivalent calls, independent of current time, random numbers, object memory addresses, or unintended mutable state.
3. Use an immutable type with well-defined `equals/hashCode`; never substitute a bare hash for identity.
4. Be low-cost, perform no network/DB calls, and have no side effects.
5. Be applied uniformly across `@Cacheable`, `@CachePut`, and `@CacheEvict` when operating on the **same entry**.

Important: a generator that deliberately embeds `method.getName()` into the key for `find(...)` will produce a different key when running `evict(...)`; the eviction will then miss the stored entry unless a dedicated shared mapping mechanism is designed. Method name should be part of the key only when business requirements truly need separate result sets.

## 5. Runnable Example: Composite Tenant + Product Key and Accurate Eviction

The example below uses **Java 17, Spring Boot 3.3.5, Spring Cache**, and `ConcurrentMapCacheManager` to observe hits/misses without needing Redis. Maven structure:

~~~text
cache-key-demo/
|-- pom.xml
+-- src/main/java/example/cache/
    |-- DemoApplication.java
    +-- CatalogService.java
~~~

**`pom.xml`**

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
    <artifactId>cache-key-demo</artifactId>
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

**`src/main/java/example/cache/DemoApplication.java`**

~~~java
package example.cache;

import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }

    // Do not include method name: find and evict must use the same key.
    @Bean("catalogKeyGenerator")
    KeyGenerator catalogKeyGenerator() {
        return (target, method, params) -> {
            if (params.length != 2
                    || !(params[0] instanceof String)
                    || !(params[1] instanceof String)) {
                throw new IllegalArgumentException(
                        "Expected tenantId and productId as Strings");
            }
            return new ProductKey(
                    Objects.requireNonNull((String) params[0]),
                    Objects.requireNonNull((String) params[1]));
        };
    }

    // Java 17 Record: immutable, equals/hashCode based on both components.
    private record ProductKey(String tenantId, String productId) {}

    @Bean
    CommandLineRunner showCacheBehavior(CatalogService catalog) {
        return args -> {
            System.out.println(catalog.find("A", "P1"));
            System.out.println(catalog.find("A", "P1"));
            System.out.println(catalog.find("B", "P1"));
            catalog.evict("A", "P1");
            System.out.println(catalog.find("A", "P1"));
        };
    }
}
~~~

**`src/main/java/example/cache/CatalogService.java`**

~~~java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger databaseCalls = new AtomicInteger();

    @Cacheable(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
    public String find(String tenantId, String productId) {
        int call = databaseCalls.incrementAndGet();
        return tenantId + "/" + productId + " -> load#" + call;
    }

    @CacheEvict(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
    public void evict(String tenantId, String productId) {
        // In a real application, data mutation logic belongs in the business layer.
    }
}
~~~

Run from the `cache-key-demo` directory with JDK 17+ and Maven:

~~~bash
mvn -q spring-boot:run
~~~

Four lines printed by `CommandLineRunner` (Spring startup logs may also appear):

~~~text
A/P1 -> load#1
A/P1 -> load#1
B/P1 -> load#2
A/P1 -> load#3
~~~

**Step-by-step explanation:** the first call for `(A,P1)` misses and runs the method (`load#1`); the second call hits and still returns `load#1`. `(B,P1)` generates a different key despite the same product ID (`load#2`). `evict(A,P1)` deletes the exact key thanks to the same `KeyGenerator` and `"catalog"` cache; reading `(A,P1)` again runs the method body a third time (`load#3`). `AtomicInteger` only helps observe read counts, and is not part of the key.

`ConcurrentMapCacheManager` stores in JVM memory here, suitable for demonstration. When switching to Redis or a distributed provider, check how `ProductKey` is converted/serialized: do not assume an arbitrary `record` works as-is on every backend. You may choose a normalized string format with an unambiguous delimiter, or configure an explicit serializer/converter.

## 6. At What Scope Should the Generator Be Configured?

There are three key configuration scopes:

| Where declared | Example | Scope of application |
| --- | --- | --- |
| On the operation | `@Cacheable(cacheNames="catalog", keyGenerator="catalogKeyGenerator")` | Only that operation; highest precedence. |
| On the class | `@CacheConfig(cacheNames="catalog", keyGenerator="catalogKeyGenerator")` | Defaults for cache operations in the class; does not enable caching itself. |
| Global | Bean returned by `CachingConfigurer#keyGenerator()` | Default for operations without custom configuration. |

Example when multiple methods of a service share the same identity:

~~~java
// Configuration illustration; methods return mock data.
@CacheConfig(cacheNames = "catalog", keyGenerator = "catalogKeyGenerator")
@Service
public class AnotherCatalogService {
    @Cacheable
    public String find(String tenantId, String productId) {
        return "value";
    }

    @CacheEvict
    public void evict(String tenantId, String productId) {
    }
}
~~~

Methods still require annotations like `@Cacheable`/`@CacheEvict`; `@CacheConfig` alone does not create cache operations. Annotation support must be enabled via `@EnableCaching` and calls must go through a Spring-managed bean/proxy. With default proxy configuration, `this.find(...)` called from the same object (self-invocation) bypasses the cache interceptor, even if the `KeyGenerator` is completely correct.

## 7. Synchronizing Key Rules Across Reads, Updates, and Invalidations

Suppose `find(tenantId, id)` stores under `(tenantId, id)`, while `update(tenantId, id, data)` defaults to all three arguments as the key. `@CachePut` on `update` will write to a **different entry**; `find` will keep reading old data. Likewise, `@CacheEvict` using only `id` will fail to evict the composite key `(tenantId, id)`. The design should define a **cache identity** first, then apply it consistently across all operations.

A uniform SpEL approach could look like:

~~~java
// Illustrative signatures within a service; not a standalone program.
@Cacheable(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String id) {
    return loadProduct(tenantId, id);
}

@CachePut(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product update(String tenantId, String id, UpdateRequest request) {
    return persistChanges(tenantId, id, request);
}

@CacheEvict(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public void delete(String tenantId, String id) {
    deleteProduct(tenantId, id);
}
~~~

The expression must rely on **the exact same first two arguments** across all three methods; `UpdateRequest` does not participate in the identity key. For multi-tenant systems or strings containing delimiters, prefer a generator that builds a structured key as in the runnable example. If the update method has a different parameter order, `#p0`/`#p1` must be adjusted accordingly; identical syntax does not guarantee identical semantics.

`@CacheEvict(allEntries=true)` clears the entire designated cache and therefore does not use per-entry keys. By default eviction runs after the method completes successfully; `beforeInvocation=true` shifts the timing to before method execution. Choose timing based on business consistency, never as a workaround for mismatched keys.

## 8. Key Design Criteria in Production Projects

- **Sufficient data:** every parameter that can change the result must be considered; e.g. `(tenantId, locale, filter, page, size)` if any of them alters the returned content. Conversely, trace IDs or logger objects are usually not part of result identity.
- **Tenant/access isolation:** if data depends on tenant, account, role, or permission scope, keys/caches must partition accordingly. Omitting this component can leak another user's data.
- **Immutability and normalization:** prefer immutable IDs; make explicit decisions on case sensitivity, whitespace, timezones, locales, and list ordering. Normalize two inputs to the same key only when business rules guarantee equivalent outputs.
- **Do not leak secrets:** avoid placing tokens, passwords, sensitive personal data, or large payloads in key strings that may appear in provider logs/metrics/dashboards.
- **Low cost:** avoid serializing entire object graphs or calling external services just to build a key; keys must be cheap and computable before running business logic.
- **Backend compatibility:** in-memory caches can use objects with `equals/hashCode`; distributed caches need serializable keys that preserve stable semantics across processes and versions.
- **Invalidation strategy:** when changing key algorithms, old entries may no longer be reachable or evictable by new keys. You may need version prefixes, cache flushes, or operational migration policies.

Cache correctness depends on both the **key mapping function** and **update/invalidation rules**. Matching keys are insufficient if data changes along paths without proper eviction or TTLs.

## 9. Common Troubleshooting

| Symptom | Causes to check | Verification / fix |
| --- | --- | --- |
| Always misses even though arguments look identical | Mutable arguments, unexpected `equals/hashCode`, different cache name, or `this.method()` call bypassing proxy | Log key identity safely; test calling through a Spring bean as in the example; verify key `equals`. |
| Hits but returns data for another tenant/method | Missing `tenantId`, two methods sharing a cache and the same default key | List all components of cache identity; separate caches or add missing identifiers. |
| `@CacheEvict` ran yet old values remain | Different cache name, parameter order, generator, prefix, or method name | Compute keys of `find` and `evict` for the **same entity**, comparing both cache name and key. |
| Annotation configuration error | Both `key` and `keyGenerator` declared, or wrong generator bean name | Use one mechanism per operation; verify the bean is Spring-managed. |
| Key works in RAM but fails with Redis | Backend cannot convert/serialize custom key type | Check key serializer/converter config, use supported key types, and write integration tests. |
| `KeyGenerator` is never invoked | `@EnableCaching` missing, call does not go through proxy, bean not Spring-created | Call from another bean; inspect caching config and intercepted public methods. |
| Accidentally clears all entries | Using `allEntries=true` when intending to delete one key | Replace with key-based eviction; clear the whole cache only when required. |

When debugging, log only safe/redacted key representations. Logging hashes is insufficient to prove two keys are equal; test structure and `equals()` directly in a unit test.

## 10. Knowledge Self-Check

**Scenario A.** Two methods both use `@Cacheable("products")`: `findBySku(String sku)` and `findById(String id)`. When both receive `"42"`, what is the risk?  
**Answer:** by default both produce key `"42"` in the same cache and can mistakenly reuse each other's results. Use two distinct cache names or a key strategy that separates method semantics; if eviction is needed, ensure eviction reproduces that exact identifier.

**Scenario B.** `renderReport(String tenant, String reportId, Locale locale)` produces different output per locale. Can only `reportId` be used as the key?  
**Answer:** no, unless the business contract guarantees `tenant` and `locale` do not affect the output. Normally all of `(tenant, reportId, locale)` plus a clear locale normalization policy are required.

**Scenario C.** A generator includes the method name in the key for both `find(a,b)` and `evict(a,b)`. Will `evict` remove the entry stored by `find`?  
**Answer:** usually no, because the two method names differ. Use a shared entity identifier or a dedicated mapping mechanism designed and tested consistently.

## References

- Spring Framework — Cache annotations, default/custom key generation, `@CacheConfig`, proxy semantics: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching and cache providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Takeaway:** `KeyGenerator` turns `(target, method, arguments)` into a cache key. Start from the identity of the **business result**, then ensure every related operation produces the exact same key when targeting the same entry.
