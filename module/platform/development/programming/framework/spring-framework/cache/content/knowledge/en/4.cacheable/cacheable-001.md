# Spring `@Cacheable`: Declaring `cacheNames`, `value`, and the Alias Relationship

## 1. Objectives and Key Concepts

In the Spring Framework, `@Cacheable` marks a method whose return value can be stored in a cache. When a subsequent invocation has the same cache key and a valid entry exists, Spring can return the stored result, skipping execution of the method body. To let Spring know **which cache** is used, we typically declare `cacheNames` or `value`.

The three approaches below are **equivalent in terms of the declared cache name** (these are three *alternative* options for a single method, not three annotations placed together):

~~~java
@Cacheable("products")
public Product findById(String id) { /* read data source */ }

// Or:
@Cacheable(value = "products")
public Product findById(String id) { /* read data source */ }

// Or:
@Cacheable(cacheNames = "products")
public Product findById(String id) { /* read data source */ }
~~~

- `"products"` is the **cache name** (cache region), not a variable name, a Service bean name, or the returned `Product` value.
- `value` here **does not mean "the value to be cached"**. It is another name for `cacheNames`.
- `@Cacheable("products")` uses Java's shorthand syntax for an annotation element named `value`.
- Even though the value is written as a single string, both `value()` and `cacheNames()` actually have the type **`String[]`**: one or multiple cache names can be declared.
- There is no singular `cacheName` attribute on `@Cacheable`. The exact attribute is `cacheNames`.

Therefore, when reading a codebase, do not conclude that `@Cacheable(value = "products")` behaves differently from `@Cacheable(cacheNames = "products")`. Inspect the **cache name, cache key, cache manager configuration, and how the method is invoked**.

## 2. Declaring One Cache or Multiple Caches

### A single cache name

~~~java
@Cacheable(cacheNames = "products")
public Product getProduct(String id) { /* ... */ }
~~~

Spring selects the cache named `products` through a `CacheResolver`, typically backed by the configured `CacheManager`. If there is no entry for the corresponding key, Spring invokes the method and stores the return value in the cache; if there is a hit, the method may not run.

The equivalent ways of *declaring the name* are:

| Syntax | Cache name value |
|---|---|
| `@Cacheable("products")` | `["products"]` |
| `@Cacheable(value = "products")` | `["products"]` |
| `@Cacheable(cacheNames = "products")` | `["products"]` |
| `@Cacheable(value = {"products"})` | `["products"]` |
| `@Cacheable(cacheNames = {"products"})` | `["products"]` |

Most methods should declare only **one** cache name so that TTL, key, and invalidation management remain clear. Choosing a cache name does not by itself configure TTL or eviction; those policies depend on the cache provider and `CacheManager` configuration.

### Multiple cache names

~~~java
@Cacheable(cacheNames = {"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }

// Equivalent syntax:
@Cacheable(value = {"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }

// With only value, shorthand syntax can be used:
@Cacheable({"products", "productsBackup"})
public Product getProduct(String id) { /* ... */ }
~~~

These are **two cache names**, not two cache keys, two arguments, or two different versions of the method. In the normal synchronous cache path, Spring may check the caches in order; if a hit is found, that result is used and any remaining caches missing the entry may be populated. If there is no hit, the method result is stored in the selected caches.

**Important limitation:** with asynchronous/reactive cache access and cache providers that report misses lazily, Spring may not check all cache names synchronously. Specifying multiple cache names must be verified against the actual provider. When using `ConcurrentMapCacheManager("products", "productsBackup")` in fixed-names mode, both names must be present in the configured list.

You should not declare multiple cache names merely as a "backup" without a clearly defined purpose; each additional name brings its own expiration policy, replica count, and consistent deletion/update requirements.

## 3. Why Are `cacheNames` and `value` Equivalent? The `@AliasFor` Mechanism

In Spring's `org.springframework.cache.annotation.Cacheable` annotation, the declaration of the two attributes has a structure equivalent to the following abridged Javadoc snippet:

~~~java
@AliasFor("cacheNames")
String[] value() default {};

@AliasFor("value")
String[] cacheNames() default {};
~~~

These are **reciprocal aliases** within the **same annotation**:

- `value()` is declared as an alias for `cacheNames()`.
- `cacheNames()` is declared as an alias for `value()`.
- Both elements have the **same `String[]` type and the same default value `{}`**.
- When Spring processes the annotation via its merged/synthesized annotations mechanism, a name declared on one attribute is interpreted as the value of the other aliased attribute.

Visualizing the metadata reading flow:

~~~text
@Cacheable(value = "products")
             |
             v
Spring reads @Cacheable via MergedAnnotations / annotation metadata
             |
             v
value ↔ cacheNames = ["products"]
             |
             v
CacheResolver / CacheManager selects cache "products"
             |
             v
Uses the cache key to check hit/miss, then returns or loads the result
~~~

`@AliasFor` is a **relationship between two elements of an annotation**, not a mechanism that copies cache contents. Nor is it a Java keyword that automatically takes effect for every reflection call: Spring must read/synthesize the annotation metadata using the framework's API for the alias semantics to be applied properly. Calling plain Java reflection on `value()` and `cacheNames()` does not mean the Java VM has automatically synchronized them.

### Declaring both aliases at the same time

There is no need to write both names in a single annotation. Choose one name according to your project's convention:

~~~java
// Prefer using one attribute to avoid duplication:
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String id) { /* ... */ }

// Redundant, even though both aliases carry the same value:
@Cacheable(value = "products", cacheNames = "products")
public Product findById(String id) { /* ... */ }

// Misconfigured aliases: the two attributes are given different values.
@Cacheable(value = "products", cacheNames = "orders")
public Product findById(String id) { /* ... */ }
~~~

**Note:** the three snippets above are **independent** examples; do not place three methods with the same signature in a single class. The last example may pass Java syntax checks because both are valid attribute names, but Spring detects the conflict when reading/synthesizing the annotation and may throw `AnnotationConfigurationException` (or a corresponding initialization error). There is no rule that "`value` takes precedence over `cacheNames`" or vice versa.

### Common pitfall: Java annotation shorthand

Java only allows omitting `value =` in annotation syntax when using the matching single-element form:

~~~java
@Cacheable("products") // Valid
@Cacheable(value = "products", key = "#p0") // Valid
@Cacheable(cacheNames = "products", key = "#p0") // Valid
~~~

Do not write `@Cacheable("products", key = "#p0")`: that is not a valid way to combine shorthand syntax with named elements in Java. Whenever you need to add `key`, `condition`, `unless`, or `sync`, explicitly write `value =` or `cacheNames =`.

## 4. Distinguishing Cache Name, Cache Key, and Cached Value

Example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String productId) {
    return repository.findById(productId).orElseThrow();
}
~~~

These three concepts occupy different roles:

| Component | In the example | Purpose |
|---|---|---|
| Cache name | `products` | Selects the cache region to operate on. |
| Cache key | `#p0` (value of `productId`) | Selects the entry inside that cache region. |
| Cached value | Returned `Product` object | Data/result stored at the selected entry. |

You can picture the contents as:

~~~text
CacheManager
 └─ Cache "products"
     ├─ key "p1" -> Product(id="p1", name="Keyboard")
     └─ key "p2" -> Product(id="p2", name="Mouse")
~~~

- `cacheNames`/**`value`** only selects the cache region; it **does not generate the key**.
- `key` is a SpEL expression evaluated per invocation. `#p0` or `#a0` refers to the first argument (0-indexed); `#p0` is useful when Java is not compiled with `-parameters` to preserve parameter names.
- If `key` is not declared and no custom `keyGenerator` is configured, the default `SimpleKeyGenerator` builds a key from the parameters: no parameters uses `SimpleKey.EMPTY`, one parameter usually uses the argument itself, and multiple parameters produce a `SimpleKey`.
- If two methods returning results with different semantics share the same cache name and key, their entries can collide. Choosing sufficiently clear cache names and sufficiently distinct keys is an application design responsibility.

Dangerous example: `getPrice(productId, currency)` with `key = "#p0"` ignores the currency unit. A read for `USD` could be erroneously reused for `VND`, even though `cacheNames` is declared correctly.

`cacheManager = "..."` is a different attribute used to select a specific **`CacheManager` bean**; it is **not** a cache name:

~~~java
@Cacheable(cacheNames = "products", cacheManager = "businessCacheManager",
           key = "#p0")
public Product getProduct(String id) { /* ... */ }
~~~

Here `businessCacheManager` is the name of the bean managing caches; `products` is the cache name provided by that manager/resolver.

## 5. Runnable Example with Spring Framework and Java 17+

This demo uses `spring-context` from Spring Framework **6.2.16**, Java **17+**, and Maven **3.9+**. It uses the in-memory cache from `ConcurrentMapCacheManager`, requiring no Spring Boot, HTTP server, or database. The goal is to verify that **the two aliased attribute names lead to the same cache**, not to benchmark performance.

File structure:

~~~text
cache-alias-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cache-alias-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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
~~~

**`src/main/java/demo/Demo.java`**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(CacheConfiguration.class)) {
            var service = context.getBean(ProductService.class);
            System.out.println(service.byValue("p1"));
            System.out.println(service.byCacheNames("p1"));
            System.out.println(service.byCacheNames("p2"));
            System.out.println(service.byValue("p2"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfiguration {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private int loads = 0;

        @Cacheable(value = "products", key = "#p0")
        public String byValue(String id) {
            return load(id);
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String byCacheNames(String id) {
            return load(id);
        }

        private String load(String id) {
            loads++;
            System.out.printf("LOAD %s #%d%n", id, loads);
            return "product:" + id + ":v" + loads;
        }
    }
}
~~~

In the `cache-alias-demo` directory, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Demo
~~~

**Demo stdout** (verified with a Java version capable of compiling to target `--release 17` via Maven):

~~~text
LOAD p1 #1
product:p1:v1
product:p1:v1
LOAD p2 #2
product:p2:v2
product:p2:v2
~~~

Explanation of each call:

1. `byValue("p1")`: cache `products` does not yet have key `p1` → runs `load`, prints `LOAD p1 #1`, and stores `product:p1:v1`.
2. `byCacheNames("p1")`: still uses cache `products` and key `p1` → **hit**, returns the exact previous result; prints no additional `LOAD`.
3. `byCacheNames("p2")`: different key → **miss**, runs `load` a second time.
4. `byValue("p2")`: hit on the `p2` entry loaded by the other method.

The example intentionally configures both methods to use the **same cache and same key** while returning the same kind of data, in order to demonstrate the alias. In a real application, **do not share a cache name/key between two methods returning semantically different data**; that would cause a data collision, even though the alias works properly.

`@EnableCaching` enables cache annotation processing; `@Bean CacheManager` provides the storage. The service instance is retrieved from the Spring context so calls pass through the **Spring proxy**, allowing caching advice to intercept them. If you manually instantiate `new ProductService()` and call it directly, the annotation will not automatically enable caching. Calling a `@Cacheable` method via `this.method()` from within the same object also generally bypasses the proxy in default mode.

`ConcurrentMapCacheManager` is suitable for learning; the example **does not configure TTL**, does not use Redis, and does not synchronize caches across multiple processes.

## 6. Relationship with `@CacheConfig` and Method-Level Configuration

`@CacheConfig` can set the **default cache name for cache operations within the same class**. When this default is present, a method can write `@Cacheable` without specifying `cacheNames`/`value` individually.

The snippet below is an **integration illustration**, requiring the application's `Product` and `ProductRepository`; it is not a standalone Java file:

~~~java
@CacheConfig(cacheNames = "products")
@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(key = "#p0")
    public Product get(String id) {
        return repository.findById(id).orElseThrow();
    }

    @Cacheable(cacheNames = "featuredProducts", key = "#p0")
    public Product getFeatured(String id) {
        return repository.findFeaturedById(id).orElseThrow();
    }
}
~~~

- `get()` inherits the default name `products` from `@CacheConfig`.
- `getFeatured()` declares `cacheNames = "featuredProducts"` on the method, so it **overrides the class's default cache name** for that operation.
- `@CacheConfig` alone **does not make methods cached**; `@Cacheable` or another cache operation is still required.
- A method may omit declaring a cache name if appropriate configuration supplies it via `@CacheConfig` or a custom `CacheResolver`. Conversely, `@Cacheable` with no cache name and no configuration providing a cache is an incomplete configuration for Spring to execute the operation.

Do not assume that because `@Cacheable.value` is an alias for `@Cacheable.cacheNames`, **every** Spring annotation has the exact same alias pair. Each annotation has its own declaration and API version; read the Javadoc of that specific annotation.

### If a project creates a composed annotation

Spring allows creating a custom annotation carrying `@Cacheable` as a meta-annotation and mapping attributes to it with `@AliasFor`. The example below is a **structural template**, requiring appropriate Java annotation and Spring imports; place the annotation in a separate `ProductCached.java` file if used in practice:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Cacheable
public @interface ProductCached {
    @AliasFor(annotation = Cacheable.class, attribute = "cacheNames")
    String[] value() default {"products"};
}
~~~

When using `@ProductCached`, the default cache name is `products`. You can write `@ProductCached("otherProducts")` to override the metadata mapped to `Cacheable.cacheNames`. This is an **alias from a custom annotation to an attribute of a meta-annotation**, which differs from the reciprocal alias *within* `@Cacheable` itself. Add this abstraction only when many methods need to share a convention and you have verified how Spring reads composed annotations.

## 7. Common Declaration Mistakes and How to Handle Them

| Symptom or Misconception | Cause | How to Check |
|---|---|---|
| Thinking `value = "products"` is the value stored in the cache | Confusing the attribute name with the cached value | `value` is a `String[]` of cache names; the cached value is the method result. |
| Writing `@Cacheable(cacheName = "products")` | Wrong attribute name | Use `cacheNames` (plural) or `value`. |
| Declaring `value = "a"` and `cacheNames = "b"` | Conflicting aliases | Use only one attribute or ensure identical values; prefer a single name. |
| Cache does not work despite annotation | Missing `@EnableCaching`; no manager; called via `new`/`this` | Check Spring bean, proxy, caching enabled, and manager configuration. |
| Error reporting cache named `products` not found | Current cache manager does not provide that cache | Check cache list/`CacheResolver` logic instead of renaming arbitrarily. |
| Unexpected results between two methods | Sharing cache name and key while results differ | Separate cache names or design properly namespaced keys. |
| Cannot reference SpEL `#id` | Parameter names not present in compiled metadata | Use `#p0`/`#a0` or configure `-parameters` properly. |
| Thinking cache name determines TTL | `@Cacheable` only specifies which cache to use | Configure TTL/eviction on the provider (Caffeine, Redis, etc.). |
| Using multiple cache names causes confusing behavior | Multiple copies, providers with different access characteristics | Test hit/miss, synchronization/invalidation, and async capabilities. |

**Recommended debugging order:** confirm the annotation is on a Spring bean method and caching is enabled → confirm the cache manager/resolver can locate the cache name → log keys/hits/misses → check for self-invocation → check whether underlying data changed without cache eviction. Merely varying `value`/`cacheNames` with the same name **cannot explain a difference in hit/miss behavior**.

## 8. Self-Check Questions

1. Which two explicit declarations is `@Cacheable("books")` equivalent to?
2. How many caches does `@Cacheable(value = {"a", "b"})` declare, and does it declare two keys?
3. Does `@Cacheable(value = "a", cacheNames = "b")` mean "read from a, write to b"?
4. In `@Cacheable(cacheNames = "books", key = "#p0")`, which part is the cache name, which is the cache key, and which is the cached value?
5. If two different methods share the same cache name and key but return semantically different data, what risk arises?
6. Why does a method annotated with `@Cacheable` still execute every time when called via `new Service()`?

**Suggested Answers:** (1) `@Cacheable(value = "books")` and `@Cacheable(cacheNames = "books")`. (2) Two cache names, not two keys. (3) No; that is an alias conflict. (4) `books` is the cache name, `#p0` computes the key from the first parameter, and the cached value is the method result. (5) Entry collision and returning incorrect results. (6) The method is not invoked through a Spring caching proxy.

## 9. References

- Spring Framework Javadoc — `@Cacheable` (see declarations of `value()` and `cacheNames()`): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Reference — Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@AliasFor` and annotation alias mechanism: https://docs.spring.io/spring-framework/docs/6.1.22-SNAPSHOT/javadoc-api/org/springframework/core/annotation/AliasFor.html

**Takeaway:** In `@Cacheable`, **`value` and `cacheNames` are reciprocal aliases for the same `String[]` of cache names**. Pick one style consistently; distinguish the cache name from the key and stored result; then verify `CacheManager`, `@EnableCaching`, and invocations through the Spring proxy so caching actually takes effect.