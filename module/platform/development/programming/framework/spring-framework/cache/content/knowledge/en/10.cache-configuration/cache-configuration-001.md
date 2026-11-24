# @CacheConfig and Class-Level Defaults in Spring Framework Cache

## 1. Why does a class need shared cache configuration?

Suppose a product management service has read, update, and delete operations. All three operations involve the `products` cache region:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) { /* ... */ }

@CachePut(cacheNames = "products", key = "#p0.id()")
public Product save(Product product) { /* ... */ }

@CacheEvict(cacheNames = "products", key = "#p0")
public void delete(String id) { /* ... */ }
```

Repeating `cacheNames = "products"` on every method easily leads to typos in region names, makes renaming difficult, and obscures the class's shared cache contract. Spring provides `@CacheConfig` to declare **class-level defaults** for the cache operations located in that class.

```java
@CacheConfig(cacheNames = "products")
public class ProductService {

    @Cacheable(key = "#p0")
    public Product find(String id) { /* ... */ }

    @CachePut(key = "#p0.id()")
    public Product save(Product product) { /* ... */ }

    @CacheEvict(key = "#p0")
    public void delete(String id) { /* ... */ }
}
```

The three method annotations in the second example automatically pick up the `products` region name from `@CacheConfig`. The `key` expressions are still declared individually to match each method's signature and parameter values.

**Core nature:** `@CacheConfig` provides default values for cache operations declared in the same class. It **does not enable caching on its own**, does not create cache entries, does not replace `@Cacheable`/`@CachePut`/`@CacheEvict`, and does not define TTL policies, capacity limits, or physical storage locations.

The short Java snippets above illustrate the annotation on a service that already has the relevant types and dependencies. A standalone runnable example is in section 5.

## 2. Defaults supported by `@CacheConfig`

The `org.springframework.cache.annotation.CacheConfig` annotation is placed on a **type/class** and provides four main attributes:

| Attribute | Declaration Type | Default Meaning for Cached Methods |
| --- | --- | --- |
| `cacheNames` (alias `value`) | `String[]` | One or more cache names used by a method when it does not specify its own |
| `keyGenerator` | `String` | Name of the Spring bean implementing `KeyGenerator` to compute the default key |
| `cacheManager` | `String` | Name of the `CacheManager` Spring bean used when no higher-priority resolver/manager is set |
| `cacheResolver` | `String` | Name of the `CacheResolver` Spring bean that selects cache regions, possibly based on the method invocation context |

A complete configuration example (the named beans must exist):

```java
@CacheConfig(
    cacheNames = "products",
    keyGenerator = "productKeyGenerator",
    cacheManager = "catalogCacheManager"
)
public class ProductService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

Here `@Cacheable` has no attributes: the cache processor picks up the `products` region name, the `productKeyGenerator` bean, and the `catalogCacheManager` bean as defaults for this operation. The string values are Spring **bean names**, not Java class names.

You do not need to declare all four attributes. In practice, usually only `cacheNames` is set; the other options should be added when all operations in the class genuinely share the same rule.

### 2.1. `cacheNames` is a list of default regions

Equivalent syntax:

```java
@CacheConfig("products")
public class A { /* ... */ }

@CacheConfig(cacheNames = {"products"})
public class B { /* ... */ }
```

Because `cacheNames` is an array, multiple cache names can be passed. However, applying multiple regions to an operation does not mean an atomic cache transaction. For bulk eviction operations, it also expands the blast radius. Choosing a single shared region aligned with the class's responsibility is easier to follow in most examples.

A `@Cacheable` without explicit cache names inherits from the class; if a method specifies `cacheNames = "productLabels"`, it uses **productLabels instead of products** for that operation. There is no "automatic merging" of class-level and method-level region names.

### 2.2. `keyGenerator` selects a shared key generation strategy

`KeyGenerator` is suitable when multiple methods share the same identification rule, such as normalizing an SKU. If a method declares `key = "#p0"` or `key = "#p0.id()"`, the method-level SpEL key takes precedence over the class's default key generator.

You must ensure that reads/writes/evictions of the same entry use the **same key logic**. Applying a generator mechanically across all signatures can produce wrong keys, especially when `find(String id)` and `save(Product product)` accept different argument types.

### 2.3. `cacheManager` selects the cache backend/group

`CacheManager` manages caches by name. For example, an application might have one manager for the catalog and another for reporting metrics. The catalog operations class can use a default:

```java
@CacheConfig(
    cacheNames = "products",
    cacheManager = "catalogCacheManager"
)
public class CatalogService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

If the application has only one suitable `CacheManager`, you usually do not need to specify the manager name on `@CacheConfig`. The region name `products` does not by itself determine whether the cache is Redis, Caffeine, or JVM memory; that is determined by the manager and provider.

### 2.4. `cacheResolver` selects the cache according to a strategy

`CacheResolver` can select caches from names, parameters, or invocation context. A class that needs flexible cache selection can configure `cacheResolver = "catalogCacheResolver"`, provided that a bean with that name exists and implements the `CacheResolver` contract.

Do not configure both `cacheManager` and `cacheResolver` at the same time for an operation: these two ways of selecting where to obtain caches are mutually exclusive alternatives. If custom cache selection logic is needed, clearly decide which resolver owns that logic. `@CacheConfig` does not create a new cache resolver or decide how data is routed.

## 3. Precedence Order: Global Default → Class → Method

Spring Cache has three configuration layers, where the **more specific** configuration takes precedence:

1. **Global:** for example, `CachingConfigurer` and the application's default cache beans.
2. **Class-level:** `@CacheConfig` applies to operations within the class.
3. **Method/operation-level:** attributes on individual `@Cacheable`, `@CachePut`, `@CacheEvict`, or nested annotations inside `@Caching`.

Example:

```java
@CacheConfig(cacheNames = "products")
public class ProductService {

    @Cacheable
    public Product find(String id) { /* ... */ }

    @Cacheable(cacheNames = "productLabels")
    public String label(String id) { /* ... */ }
}
```

| Method | Effective Cache Name | Why |
| --- | --- | --- |
| `find("P1")` | `products` | `@Cacheable` does not specify a name, so it inherits `@CacheConfig` |
| `label("P1")` | `productLabels` | The method specifies its own region name, so it overrides the class default |

If `@CacheConfig(keyGenerator = "productKeyGenerator")` is set and a method specifies `@Cacheable(key = "#p0")`, the `#p0` expression is chosen for **that method**. `key` and `keyGenerator` must not be declared at the same time on **a single cache operation**, because they are mutually exclusive ways of determining keys.

Similarly, an operation specifying `cacheManager = "reportCacheManager"` can override the class's default manager selection. When an operation uses its own `cacheResolver`, the operation's resolver takes precedence; check the resolver bean and the cache names it actually returns.

**Defaults are not business-behavior inheritance:** `@CacheConfig` only centralizes configuration values. It does not turn `@Cacheable` into `@CachePut`, does not add transaction synchronization, and does not force operations to share the same error-handling policy.

## 4. What is NOT in `@CacheConfig`?

| Requirement | Appropriate Configuration |
| --- | --- |
| Actually enable annotation-based caching | `@EnableCaching` on Spring configuration |
| Specify which method is cached | `@Cacheable` on the method |
| Always run the method and update the cache | `@CachePut` |
| Remove an entry or clear a region | `@CacheEvict` |
| Select key via SpEL `#p0.id()` | `key` on each operation |
| Cache only when arguments meet a condition | `condition` on each operation |
| Do not cache null results | `unless = "#result == null"` on supported operations |
| Synchronize computation for cache misses on the same key | `@Cacheable(sync = true)` when meeting annotation/provider constraints |
| TTL, size limit, eviction policy, serialization | Configure the corresponding `CacheManager`/cache provider |
| Transaction commit, multi-node invalidation | Appropriate transaction and cache backend/event design |

Even if a class has `@CacheConfig(cacheNames = "products")`, a method **without a cache operation annotation** still runs normally and is not cached merely because it belongs to that class.

Nor can you use `@CacheConfig` to default `unless` or `condition` for the entire class: its four public attributes are `cacheNames`, `keyGenerator`, `cacheManager`, and `cacheResolver`.

## 5. Runnable example: class defaults and method-level overrides

The following Java 17 + Spring Framework 6.2.x example illustrates two regions:

- `products`: shared by `find`, the `@CachePut` part of `save`, and the `@CacheEvict` part of `delete` via `@CacheConfig(cacheNames = "products")`.
- `productLabels`: chosen **specifically on the `label` method** to store product names.
- When updating/deleting a product, the product name region must also be invalidated. `@Caching` allows declaring the necessary operations simultaneously.

The underlying data source is an in-memory repository to easily track read counts; a real application would replace it with an appropriate repository/database. Requires JDK 17+ and Maven.

**File structure:**

```text
cache-config-demo/
├── pom.xml
└── src/main/java/CacheConfigDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-config-demo</artifactId>
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

**`src/main/java/CacheConfigDemo.java`:**

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfigDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "productLabels");
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String id, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger loadCount = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Pen"));
        }

        public Product find(String id) {
            loadCount.incrementAndGet();
            return data.get(id);
        }

        public Product save(Product product) {
            data.put(product.id(), product);
            return product;
        }

        public void delete(String id) {
            data.remove(id);
        }

        public int reads() {
            return loadCount.get();
        }
    }

    @CacheConfig(cacheNames = "products")
    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        // Uses the class's default products region.
        @Cacheable(key = "#p0", unless = "#result == null")
        public Product find(String id) {
            return repository.find(id);
        }

        // Overrides cacheNames: stores the name in productLabels.
        @Cacheable(
            cacheNames = "productLabels",
            key = "#p0",
            unless = "#result == null"
        )
        public String label(String id) {
            Product product = repository.find(id);
            return product == null ? null : product.name();
        }

        // @CachePut omits cacheNames -> inherits products from the class.
        // Evicts productLabels separately because the name also changed.
        @Caching(
            put = @CachePut(key = "#p0.id()"),
            evict = @CacheEvict(
                cacheNames = "productLabels",
                key = "#p0.id()"
            )
        )
        public Product save(Product product) {
            return repository.save(product);
        }

        // Evicts two projections with the same key. The first evict
        // inherits cacheNames=products from @CacheConfig.
        @Caching(evict = {
            @CacheEvict(key = "#p0"),
            @CacheEvict(cacheNames = "productLabels", key = "#p0")
        })
        public void delete(String id) {
            repository.delete(id);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheConfigDemo.class)) {
            ProductService service = context.getBean(ProductService.class);
            ProductRepository repo = context.getBean(ProductRepository.class);

            System.out.println("find #1: " + service.find("P1"));
            System.out.println("find #2: " + service.find("P1"));
            System.out.println("reads: " + repo.reads());

            System.out.println("label #1: " + service.label("P1"));
            System.out.println("label #2: " + service.label("P1"));
            System.out.println("reads: " + repo.reads());

            service.save(new Product("P1", "Blue pen"));
            System.out.println("after save product: " + service.find("P1"));
            System.out.println("after save label: " + service.label("P1"));
            System.out.println("reads: " + repo.reads());

            service.delete("P1");
            System.out.println("after delete product: " + service.find("P1"));
            System.out.println("reads: " + repo.reads());
        }
    }
}
```

**Run in the directory containing `pom.xml`:**

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheConfigDemo
```

**Output printed by the program** (excluding environment-dependent Maven/Spring logs):

```text
find #1: Product[id=P1, name=Pen]
find #2: Product[id=P1, name=Pen]
reads: 1
label #1: Pen
label #2: Pen
reads: 2
after save product: Product[id=P1, name=Blue pen]
after save label: Blue pen
reads: 3
after delete product: null
reads: 4
```

**Step-by-step explanation:**

1. The first call `find("P1")` misses in `products/P1`, reading from the source once; the second call hits, so the read count remains 1.
2. `label("P1")` uses `productLabels/P1` because **the method overrides cacheNames**; the first call misses, bringing the read count to 2; the next call hits in its own region.
3. `save(P1, "Blue pen")` updates the source, then the `@CachePut` operation writes the new product value to `products/P1` (inherited from the class). The `@CacheEvict` part removes `productLabels/P1` because the name needs to be reloaded.
4. `find("P1")` after save hits the updated product. `label("P1")` misses and reads the new name, so the read count becomes 3.
5. `delete("P1")` deletes from the source and evicts the entry with the same key in both regions. `find("P1")` after delete misses, the source returns null, `unless` prevents caching null, and the read count becomes 4.

This is a single-JVM application using `ConcurrentMapCacheManager`. It demonstrates region names, key rules, annotation precedence, and invalidation; it cannot be used as proof of distributed synchronization or atomic transactions between cache and database.

## 6. Designing a shared `keyGenerator`: when to use and when not to?

If multiple methods genuinely share the same key generation rule, you can specify the generator name at the class level:

```java
@CacheConfig(
    cacheNames = "products",
    keyGenerator = "skuKeyGenerator"
)
public class SkuService {

    @Cacheable
    public Product find(String sku) { /* ... */ }

    @CacheEvict
    public void invalidate(String sku) { /* ... */ }

    // Operation-level key overrides the class's keyGenerator.
    @CachePut(key = "#p0.sku()")
    public Product save(Product product) { /* ... */ }
}
```

This is an **illustrative snippet**; the `Product` type, dependencies, and the `skuKeyGenerator` bean must be defined in a real application. `find` and `invalidate` accept the same parameter type, so the shared generator can produce the same key. `save`, however, takes a `Product` object, so the `#p0.sku()` expression selects the right key from that method's input.

An illustrative generator bean (requires importing `org.springframework.cache.interceptor.KeyGenerator` and `org.springframework.context.annotation.Bean`):

```java
@Bean("skuKeyGenerator")
KeyGenerator skuKeyGenerator() {
    return (target, method, params) -> {
        if (params.length != 1 || !(params[0] instanceof String sku)) {
            throw new IllegalArgumentException("Expected one String SKU");
        }
        return sku;
    };
}
```

This generator **is only suitable for methods taking a single `String` SKU**, because it checks the parameter type. Do not use it directly for methods taking `Product`; if you need to support multiple signatures, design a comprehensive key generator or specify a separate `key` on the method.

**Important note:** setting `keyGenerator` on `@CacheConfig` does not cause `@Cacheable` and `@CacheEvict` to automatically pick the exact same key. That remains a contract decided by the designer, which must be tested across read/update/delete paths.

### Distinguishing a bean name from a SpEL expression

- `keyGenerator = "skuKeyGenerator"` is the **bean name** of the key generation algorithm.
- `key = "#p0.sku()"` is a **SpEL expression** evaluated against the invocation arguments.
- Both forms produce a key value, but choose only **one** form per cache operation; configure precedence at the method or class level according to the rules described above.

## 7. `cacheManager` and `cacheResolver`: backend routing examples

An application might use Caffeine for catalog data and Redis for shared data. Example of configuration intent:

```java
@CacheConfig(
    cacheNames = "products",
    cacheManager = "catalogCacheManager"
)
public class CatalogService {

    @Cacheable
    public Product find(String id) { /* ... */ }

    @Cacheable(
        cacheNames = "productPrices",
        cacheManager = "pricingCacheManager"
    )
    public Price price(String id) { /* ... */ }
}
```

This is also an **illustrative snippet requiring real beans**. `find` inherits the catalog manager; `price` specifies the pricing manager for its operation. Each manager must have the corresponding region or a mechanism to create regions according to the provider's rules. Two caches with the same name under two managers can be two different physical spaces; therefore, when invalidating data, choose both the right manager and the right key.

If a dynamic cache resolver is needed:

```java
@CacheConfig(cacheResolver = "dynamicCatalogCacheResolver")
public class DynamicCatalogService {
    @Cacheable
    public Product find(String id) { /* ... */ }
}
```

The `dynamicCatalogCacheResolver` bean is responsible for selecting the appropriate cache. When using a dynamic resolver, you may not need to declare fixed region names. Do not set both `cacheManager` and `cacheResolver` for the same operation, because the resolver already determines how caches are looked up.

### Configuration lifecycle and scope of impact

`@CacheConfig` only pertains to the **annotated class** and the cache operations inside that class. It does not alter the configuration of other Spring beans, does not create an application-wide cache policy, and does not automatically attach caching to every method of the class.

`@EnableCaching` must be declared in an appropriate Spring configuration to activate the annotation mechanism. When using the default proxy mode, calls from other beans through the Spring proxy are intercepted; self-invocations like `this.find(...)` within the same instance usually bypass cache advice. For `private` or `final` methods, or objects manually created with `new` outside the Spring context, proxy behavior may not work as expected.

When moving to Spring Boot, auto-configuration can provide a manager corresponding to dependencies and properties, but `@CacheConfig` remains purely default metadata; it does not replace provider configuration.

## 8. Consistency contract across operations in a class

Sharing a region name **is not enough** to guarantee data correctness. You must keep the following consistent:

| Operation | Argument | Region | Key | Value / Behavior |
| --- | --- | --- | --- | --- |
| `find("P1")` | `String id` | `products` | `"P1"` | Read product |
| `save(Product("P1", ...))` | `Product` | `products` | `product.id()` | Put new product |
| `delete("P1")` | `String id` | `products` | `"P1"` | Evict exact entry |
| `label("P1")` | `String id` | `productLabels` | `"P1"` | Read name projection |
| `save/delete` affecting name | Product or id | `productLabels` | `"P1"` | Evict projection for reload |

If `@CachePut` uses the entire `Product` object as the key while `@Cacheable` uses the id string, the two keys will differ. `@CacheConfig(cacheNames="products")` does not detect or fix this mismatch.

Similarly, if `find` only distinguishes `id` while the actual result depends on `tenantId` or locale, requests from different contexts may share the wrong entry. The key must include all factors that determine the result, even when the region is declared at the class level.

Do not confuse **inheriting cacheNames** with **invalidation of other projections**. If the catalog also has category lists, search results, totals, and names, modifying a product may require clearing multiple related regions. This can be handled with `@Caching` or an explicit post-commit coordination mechanism.

For database writes inside transactions, eviction timing relative to commit must be explicitly designed. `@CacheConfig` does not guarantee atomic updates between cache and database. In particular, multiple instances using local caches can hold independent stale copies.

## 9. Common mistakes when using `@CacheConfig`

1. **Thinking that adding `@CacheConfig` caches every method.** Wrong: this annotation only declares defaults; `@Cacheable`, `@CachePut`, or `@CacheEvict` is still required on the target operations.
2. **Forgetting `@EnableCaching`.** Annotations on a service do not enable the cache processor on their own.
3. **Misunderstanding override as merging.** A method specifying `cacheNames = "productLabels"` selects that cache instead of the class's default `products`.
4. **Using a shared key generator for different signatures.** A generator expecting `String sku` can fail when a method receives `Product` or `DeleteCommand`; define the key contract per operation.
5. **Setting both `key` and `keyGenerator` on the same annotation.** These two key generation mechanisms are mutually exclusive; pick the appropriate configuration at a given level.
6. **Setting both `cacheManager` and `cacheResolver` on the same operation.** A resolver is an alternative to getting caches from a default manager; keep configuration consistent.
7. **Inconsistent keys across read, write, and delete.** Sharing a cache name with different keys still causes stale entries and unnecessary cache misses.
8. **Assuming `@CacheConfig` sets TTL or max size.** Those policies belong to the backend/provider, such as Caffeine or Redis, not the four attributes of `@CacheConfig`.
9. **Applying one shared `cacheNames` to incompatible data types.** The same key can return the wrong type if different methods store `Product` and `String` in the same region; separate regions or design clear key namespaces.
10. **Overlooking proxies and self-invocation.** Internal calls like `this.find(id)` may not be intercepted by advice in default proxy mode; test through a Spring bean.
11. **Using multiple `cacheNames` on a class followed by uncontrolled `allEntries=true` eviction.** That operation may wipe multiple regions resolved for the operation; review the scope before deploying.
12. **Treating class defaults as a system-wide policy.** Other classes still have their own configurations, even when using the same manager name; do not extrapolate from one class to every cache producer/consumer.

## 10. Testing checklist and configuration selection principles

When introducing `@CacheConfig` to an existing class, check:

- **Scope:** which methods actually have cache annotations, and what are the effective cache names for each method?
- **Precedence:** which methods override the region name, key generator, cache manager, or resolver?
- **Key equality:** does the same entity across `find`/`save`/`delete` produce keys equal via `equals()/hashCode()` or the representation accepted by the backend?
- **Hit/miss:** call the same key twice; does the source access count drop as expected?
- **Put/evict:** do updates/deletes modify or remove the right entries, including dependent projection caches?
- **Provider:** does the chosen manager have valid region names and proper TTL/size/serialization? Are there multiple JVMs?
- **Proxy:** do test calls go through the Spring bean with advice enabled?
- **Failure/transaction:** when the source fails or rolls back, do old entries remain valid? When eviction fails, how does the application handle it?

A practical rule of thumb: if multiple operations in a class use **the same cache name or the same key generation algorithm**, set the default in `@CacheConfig` to reduce repetition. When a method has different data or a different cache backend, **override it explicitly right at the method**, and test that the difference is intentional.

## Official References

- Spring Framework — Caching Annotations, `@CacheConfig` section: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `@CacheConfig` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework — `@Caching` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework — `KeyGenerator` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework — Cache Store Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
