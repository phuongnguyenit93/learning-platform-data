# Distinguishing `key` from `keyGenerator` and the Error of Declaring Both in Spring Cache

## Lesson Objectives

After this lesson, you will be able to: (1) distinguish the **key** attribute written in Spring Expression Language (SpEL) from the **keyGenerator** attribute specifying a Java bean; (2) choose the right key-generation approach for each cached method; (3) explain why declaring both on the same cache operation is an error; (4) distinguish a true conflict from a method overriding a class-level default on **@CacheConfig**; and (5) create, run, and verify a Spring Cache example using Java 17+.

This lesson focuses on annotation-based caching in the **Spring Framework**. Spring Boot also uses these annotations, though Boot's bean auto-configuration is a separate layer. The content uses only Spring Cache API names and semantics without depending on any specific cache provider.

## 1. Why Does Spring Need a Cache Key?

Every cache is a store of **key → value** pairs. When a method annotated with `@Cacheable` is called externally through an appropriate proxy, Spring must determine the **key** to check the cache before invoking the real method.

~~~text
Caller
  -> Spring Cache interceptor
      -> select cache (cacheNames / CacheResolver)
      -> generate key (SpEL key or KeyGenerator)
      -> look up entry in cache
            HIT  -> return cached value
            MISS -> run real method -> write value with computed key
~~~

**Cache name** and **cache key** are different. For example, a cache named `prices` holds keys such as `"SKU-01"` and `"SKU-02"`. Changing `cacheNames` changes where to look; changing `key` changes the entry identity inside that cache.

Annotations have three common ways to generate keys:

~~~java
// Illustrative snippet, not a complete Java program.
@Cacheable(cacheNames = "prices")
public Price findPrice(String sku) { ... } // uses the default KeyGenerator

@Cacheable(cacheNames = "prices", key = "#p0")
public Price findBySku(String sku) { ... } // SpEL selects the first parameter

@Cacheable(cacheNames = "prices", keyGenerator = "skuKeyGenerator")
public Price findNormalized(String sku) { ... } // uses a Java bean by name
~~~

All three cases store entries in the logical `prices` cache, though their key computation rules may differ. The **key** value is a **SpEL expression**; the **keyGenerator** value is the **name of a bean implementing KeyGenerator**, not a SpEL expression.

## 2. The `key` Attribute: SpEL Computes the Key for an Operation

Common syntax:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) { ... }
~~~

This is a signature illustration; `Product` and the application body must be defined. The expression **#p0** points to the first parameter (index 0). Spring evaluates the expression in the invocation context and uses the **evaluated result** as the key object. Thus, you can select parameters, parameter properties, combine multiple parts, or call normalization methods.

Several suitable expressions:

| Key Expression | Meaning | Conditions / Notes |
| --- | --- | --- |
| **#p0** or **#a0** | Gets the first argument | Independent of Java parameter names |
| **#root.args[0]** | Also gets the first argument from the root object | Useful when making the context structure explicit |
| **#p0.id** | Gets the `id` property of the first argument | Object must be non-null and property accessible |
| **#p0.trim().toUpperCase(T(java.util.Locale).ROOT)** | Normalizes code before forming key | Argument must be a non-null String; must fit domain rules |
| **#root.methodName + ':' + #p0** | Prepends the method name to the key | Useful when multiple methods share one cache with different meanings |
| **#tenant + ':' + #code** | Concatenates two parameters by name | Requires parameter-name metadata and delimiter collision avoidance |

Variables **#p0**, **#a0**, and **#root.args[0]** are generally more reliable than assuming Spring can always see names like **#tenant** or **#code**. Parameter names require compiler metadata (e.g., compiling with **-parameters**) or a compatible discovery mechanism.

### Example: Using `key` to Select Fields That Actually Determine the Result

~~~java
// Pseudo service: annotation illustration only, not standalone runnable.
@Cacheable(cacheNames = "productNames", key = "#p0")
public String productName(String productId, boolean traceEnabled) {
    // traceEnabled only controls logging; it does not change the return value.
    return repository.findName(productId);
}
~~~

Because `traceEnabled` does not affect the return value, two calls with the same `productId` are allowed to share an entry even when the logging flag differs. Conversely, if a boolean actually changes the business result, **omitting it from the key will cause wrong cache hits**.

A key expression should satisfy: **same logical input → same key; inputs that change the result → different keys**. Do not use random numbers or the current timestamp as a key if the goal is reusing results.

### SpEL Syntax Is Not Java Syntax

This is a common mistake:

~~~java
// Wrong intent: Spring treats "sku" as a SpEL expression,
// and does not automatically resolve it as a Java parameter in the method.
@Cacheable(cacheNames = "products", key = "sku")

// Correct when intending to get the first parameter:
@Cacheable(cacheNames = "products", key = "#p0")

// Correct when intentionally using a constant key string "sku":
@Cacheable(cacheNames = "products", key = "'sku'")
~~~

The three lines above are **separate illustrative** annotations, not placed consecutively on the same method. Constant keys are only appropriate when data does not depend on parameters; using one constant key across multiple inputs can return wrong results.

Note further: **#result** does not exist yet when `@Cacheable` needs to compute the key to **look up the cache before invoking the method**. Do not design `@Cacheable(key = "...#result...")` to identify lookups. `@Cacheable` provides **unless** to evaluate a post-execution condition that can inspect the result; that serves a different purpose from `key`.

## 3. The `keyGenerator` Attribute: Calling a Java Bean to Generate Keys

In Spring, **org.springframework.cache.interceptor.KeyGenerator** is a functional interface. Method to implement:

~~~java
Object generate(Object target, java.lang.reflect.Method method, Object... params);
~~~

This is an abbreviated signature declaration. Spring passes the generator the target object, the cached method, and the actual argument array. The generator returns **an object as the key**; this can be a normalized `String`, an immutable record, or a composite value with proper `equals()/hashCode()`.

Bean example:

~~~java
@Bean("skuKeyGenerator")
public KeyGenerator skuKeyGenerator() {
    return (target, method, params) ->
        ((String) params[0]).trim()
            .toUpperCase(java.util.Locale.ROOT);
}
~~~

This is a bean snippet inside a `@Configuration` class, using **org.springframework.cache.interceptor.KeyGenerator** and **org.springframework.context.annotation.Bean**. The example assumes the method's first argument is a non-null `String`; for methods with different parameter structures, validate or use a dedicated generator.

Referencing the bean by **name**:

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public Product find(String sku) { ... }
~~~

The string **"skuKeyGenerator"** is the bean name looked up in the `ApplicationContext`. It is **not** a Java method name, **not** SpEL, and not the returned key content. Whether named via `@Bean`, `@Component`, or equivalent configuration, the actual bean name must match the `keyGenerator` value.

### When Should You Use `keyGenerator`?

- Multiple methods share a complex normalization rule that should be managed in one place.
- You want to construct an **immutable value object** containing `tenantId`, `productId`, `locale`, and `version` while guaranteeing equality rules.
- You need a consistent key convention across many classes, with dedicated unit tests for the algorithm.
- You need to distinguish method names or namespaces under a unified policy.

The advantage of `keyGenerator` is that Java logic is easy to unit test, reuse, and refactor. On the downside, it adds a bean and can become confusing if the algorithm relies on implicit parameter order or types that are not clearly defined.

**Never return null** from a `KeyGenerator`. Spring Cache requires a valid key when performing operations. When using object keys in an in-memory Java cache, the object must have proper `equals()/hashCode()` and must not mutate in ways that shift key identity while stored.

## 4. Comparison Table: `key`, `keyGenerator`, and Default Configuration

| Criterion | **key** | **keyGenerator** |
| --- | --- | --- |
| Value type in annotation | **SpEL** string | **KeyGenerator bean name** string |
| Processing mechanism | Spring evaluates the expression against the invocation context | Spring fetches the bean and calls `generate(target, method, params)` |
| Best suited for | A single method selecting or transforming a few clear parameters | Complex or shared Java key-generation algorithms |
| Access to method/target? | Yes, via SpEL context variables like `#root.methodName`, `#root.target` | Yes, directly via `target`, `Method`, `params` |
| Requires defining an extra bean? | No, if the expression only uses available inputs/APIs | Yes, unless a bean is already configured in the app |
| Primary testing approach | Test expression via hits/misses with real inputs | Unit test the generator and integration test with cache |
| Declaration on method | `key = "#p0"` | `keyGenerator = "myGenerator"` |
| Declaring both on the same operation | **Invalid** | **Invalid** |

If **neither is declared**, Spring uses whichever default generator is active. In typical configurations, that is **SimpleKeyGenerator**: no arguments → `SimpleKey.EMPTY`; one non-null non-array argument → that argument itself; multiple arguments → a `SimpleKey` wrapping the arguments. Cache name and method name are not automatically added to the default key.

**Critical point:** There is no “prefer `key` over `keyGenerator`” rule when **both are set directly on the same operation**. That configuration is **invalid** and Spring reports an error; do not expect one attribute to be silently ignored.

## 5. Error When Declaring Both `key` and `keyGenerator`

**Intentionally invalid** example:

~~~java
// WRONG: example to recognize an invalid configuration; do not add to a runnable project.
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    keyGenerator = "skuKeyGenerator"
)
public String find(String sku) {
    return "value";
}
~~~

Problem: the same cache operation specifies **two ways to compute the key**. Spring cannot treat that as a valid choice. According to the Spring Framework documentation, **key and keyGenerator are mutually exclusive**; an operation setting both throws an exception during configuration/operation processing. The exact moment the error surfaces can depend on bean initialization and when Spring parses metadata; do not hardcode a single exception class or message across all versions.

Fix 1 — use SpEL only:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return "value";
}
~~~

Fix 2 — use the bean only:

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public String find(String sku) {
    return "value";
}
~~~

Fix 3 — if no special logic is needed, omit both to use the default key:

~~~java
@Cacheable(cacheNames = "products")
public String find(String sku) {
    return "value";
}
~~~

These three fixes are **three independent options**; do not place all three annotations on the same method. Pick the one that fits the business identity.

### A Closer Look at Empty Strings

In annotations, **key** and **keyGenerator** default to an empty string. The conflict condition applies to **non-empty configured attributes**, not merely both attribute names appearing in the annotation definition. For example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", keyGenerator = "")
public String find(String sku) { return "value"; }
~~~

The snippet above is illustrative: an empty `keyGenerator` **does not specify a concrete bean**; the SpEL `key` is used. Even though it does not necessarily conflict, explicitly writing `keyGenerator = ""` adds no value in real code and should be removed.

### Second Error: Missing Bean or Wrong Type

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "missingGenerator")
public String find(String sku) { return "value"; }
~~~

If no bean named `missingGenerator` of a compatible `KeyGenerator` type exists, Spring cannot resolve it when the operation executes. This is a **bean resolution error**, distinct from declaring both `key` and `keyGenerator`.

## 6. Important Exception: `@CacheConfig` Defaults and Method Overrides

`@CacheConfig` defines **class-level defaults**, including `cacheNames`, `keyGenerator`, `cacheManager`, and `cacheResolver`. A **method-level** customization takes precedence over a class-level default. This does not mean the method declared two conflicting strategies.

**Valid** example:

~~~java
@CacheConfig(keyGenerator = "skuKeyGenerator")
public class ProductReader {

    @Cacheable(cacheNames = "products", key = "#p0")
    public String findExact(String sku) {
        return findFromSource(sku);
    }

    @Cacheable(cacheNames = "productsByNormalizedSku")
    public String findNormalized(String sku) {
        return findFromSource(sku);
    }
}
~~~

This is an illustrative class requiring imports and a `findFromSource` definition in a real project. The two methods choose different cache names to avoid mixing data types and to highlight the key strategies:

- **findExact** has method-level `key = "#p0"`. Spring prioritizes this **SpEL key** and **does not apply** the `@CacheConfig`-level default `keyGenerator` to that operation.
- **findNormalized** sets neither `key` nor `keyGenerator` of its own. It can inherit `@CacheConfig`'s **skuKeyGenerator** and apply normalization logic.
- `@CacheConfig` **by itself does not enable caching** and does not create cache entries automatically. `@Cacheable`/`@CachePut`/`@CacheEvict` on appropriate operations and enabling infrastructure like `@EnableCaching` are still required.

Therefore, distinguish carefully:

| Declaration | Valid? | Active Strategy |
| --- | --- | --- |
| `@Cacheable(key = "#p0")` | Yes | SpEL |
| `@Cacheable(keyGenerator = "skuKeyGenerator")` | Yes if bean exists and matches | `KeyGenerator` bean |
| `@Cacheable(key = "#p0", keyGenerator = "skuKeyGenerator")` | **No** | Throws operation configuration error |
| `@CacheConfig(keyGenerator = "skuKeyGenerator")` + method `@Cacheable(key = "#p0")` | **Yes** | Method-level SpEL overrides class-level default |
| `@CacheConfig(keyGenerator = "skuKeyGenerator")` + method `@Cacheable` | Yes if infrastructure is complete | Inherits class-level `KeyGenerator` |
| No custom strategy | Yes | Default `KeyGenerator` |

You can also set an application-wide default generator via Spring configuration mechanisms (such as `CachingConfigurer`) and override it at the class or operation level. The general precedence rule is **global default → `@CacheConfig` class → operation annotation**, but **never use this precedence rule to justify setting both attributes simultaneously on a single operation annotation**.

## 7. Runnable Java 17+ Example: Comparing Three Key Strategies

The following example uses **Spring Framework 6.1.x, Maven, Java 17+** and `ConcurrentMapCacheManager`. It verifies three approaches:
1. SpEL normalizing SKU;
2. Java `KeyGenerator` normalizing SKU;
3. Default `KeyGenerator` keeping the raw `String` argument, so two different strings create two entries.

Directory structure:

~~~text
spring-cache-key-choice/
├── pom.xml
└── src/main/java/demo/CacheKeyChoiceDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-key-choice</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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

**src/main/java/demo/CacheKeyChoiceDemo.java**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheKeyChoiceDemo {

    public static class CatalogService {
        private final AtomicInteger spelLoads = new AtomicInteger();
        private final AtomicInteger generatorLoads = new AtomicInteger();
        private final AtomicInteger defaultLoads = new AtomicInteger();

        @Cacheable(
            cacheNames = "bySpel",
            key = "#p0.trim().toUpperCase(T(java.util.Locale).ROOT)"
        )
        public String bySpel(String sku) {
            return "spel-load-" + spelLoads.incrementAndGet();
        }

        @Cacheable(
            cacheNames = "byGenerator",
            keyGenerator = "normalizingKeyGenerator"
        )
        public String byGenerator(String sku) {
            return "generator-load-" + generatorLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "byDefault")
        public String byDefault(String sku) {
            return "default-load-" + defaultLoads.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "bySpel", "byGenerator", "byDefault"
            );
        }

        @Bean("normalizingKeyGenerator")
        public KeyGenerator normalizingKeyGenerator() {
            return (target, method, params) ->
                ((String) params[0]).trim().toUpperCase(Locale.ROOT);
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = ctx.getBean(CatalogService.class);

            System.out.println(service.bySpel(" sku-7 "));
            System.out.println(service.bySpel("SKU-7"));

            System.out.println(service.byGenerator(" sku-7 "));
            System.out.println(service.byGenerator("SKU-7"));

            System.out.println(service.byDefault(" sku-7 "));
            System.out.println(service.byDefault("SKU-7"));
        }
    }
}
~~~

Run with Maven from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyChoiceDemo
~~~

**Stdout printed by Java itself** (excluding Maven logs if your environment prints extra output):

~~~text
spel-load-1
spel-load-1
generator-load-1
generator-load-1
default-load-1
default-load-2
~~~

Result explanation:

- **bySpel(" sku-7 ")** produces key `"SKU-7"` via SpEL; the real method runs the 1st time. **bySpel("SKU-7")** produces the same key and hits, still returning `"spel-load-1"`.
- **byGenerator(...)** also produces key `"SKU-7"`, but the algorithm is executed by the `KeyGenerator` bean; the second call hits the `byGenerator` cache.
- **byDefault(...)** keeps each call's `String` argument verbatim as the key. `" sku-7 "` and `"SKU-7"` are not `equals()`, so both miss and the counter reaches 2.
- The three methods use **three different cache names** to avoid data collisions and observe each key strategy independently.
- `@EnableCaching` and fetching `CatalogService` from `ApplicationContext` ensure calls go through the Spring proxy. If you manually instantiate `new CatalogService()` outside Spring, `@Cacheable` will not work.

If you add an example declaring **both `key` and `keyGenerator` on the same method** into this application, the configuration becomes invalid. Do not add that intentional error to the runnable demo file; use the separate example in Section 5 to identify and fix it.

## 8. Building Correct Keys with Multiple Parameters

Choosing between `key` and `keyGenerator` should be driven by the **logical identity of the result**, not habit around a particular annotation. For example, product price depends on `productId` and `currency`:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0 + ':' + #p1")
public String price(String productId, String currency) {
    return lookupPrice(productId, currency);
}
~~~

This is an illustrative snippet, not a full program. String concatenation with a colon can suffer **key collisions** if components contain the delimiter:

~~~text
productId = "ab:c", currency = "d"   -> "ab:c:d"
productId = "ab",   currency = "c:d" -> "ab:c:d"
~~~

For simple expressions, you can choose a structured key object, or use a generator returning an immutable record:

~~~java
record PriceKey(String productId, String currency) {}

@Bean("priceKeyGenerator")
KeyGenerator priceKeyGenerator() {
    return (target, method, params) ->
        new PriceKey((String) params[0], (String) params[1]);
}
~~~

This example is **placed inside a configuration class**. You must declare the bean with the exact name, ensure the method has two `String` parameters in the expected order, and handle null checks/normalization if required by business rules. A record in Java 17 provides `equals()` and `hashCode()` based on its components; it fits well as a key for in-memory Java caches when components are immutable.

When using a distributed cache such as Redis, object keys must also be **serialized** into bytes. Do not assume that a record with proper `equals/hashCode` automatically yields identical key bytes across custom instances; serializer and namespace conventions must be consistent.

### Aligning Keys When Updating or Evicting the Cache

A subtle bug is using a normalizing `keyGenerator` on `@Cacheable` while using a raw `key` on `@CacheEvict`:

~~~java
// Two illustrative annotations belonging to two different operations.
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public String find(String sku) { return load(sku); }

@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String sku) { }
~~~

If `find(" sku-7 ")` stores under `"SKU-7"` while `invalidate(" sku-7 ")` deletes the key with spaces, the original entry remains untouched. This is a **key-identity mismatch bug**, even though each annotation **is valid on its own**.

Standardize on one of two approaches: use the same generator on all operations, or write an eviction `key` expression that produces the exact same stored key. `@CachePut` must follow the same convention when updating entries. If cache names differ or keys are computed in a different context, design each operation's key explicitly.

## 9. Strategy Selection and Testing Workflow

**Choose SpEL `key`** when:
- You only need to pick 1–2 parameters or a property, such as `#p0`, `#p0.id`.
- Any normalization is short and readable without duplicating across many methods.
- A maintainer can understand the entire key directly from the method annotation.

**Choose `keyGenerator`** when:
- Logic involves multiple steps, conditional checks, or shared normalization rules.
- The key is a structured object requiring tests for `equals/hashCode`, formatting, and lifecycle.
- Multiple methods must follow a unified key convention that can live in a shared internal component.

**Keep the default** when the arguments already capture the proper identity and have stable `equals/hashCode`. Do not add unnecessary custom code.

Minimum tests for each cached method:

1. **Same logical input:** call twice with equivalent inputs; the real method executes only once on a cache hit.
2. **Inputs that change the result:** vary tenant/currency/locale or relevant parameters; must produce distinct entries.
3. **Ignored fields:** explicitly verify that excluded fields genuinely do not affect returned data.
4. **Eviction and put:** use the same cache name, key rules, and normalization across read/write/delete.
5. **Configuration validation:** search for `@Cacheable`/`@CachePut`/`@CacheEvict` declaring both non-empty `key` and `keyGenerator`; fix so each operation has only one key source.
6. **Bean resolution:** if using `keyGenerator`, verify the named bean exists, implements `KeyGenerator`, and returns a non-null key.
7. **AOP proxy:** test through beans inside the Spring container, not just manually instantiated Java objects.
8. **Cache provider:** check how the provider matches keys and handles serialization when deploying a remote cache.

### Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Exception when Spring processes cache operation | Same method specifies non-empty `key` and `keyGenerator` | Choose exactly **one** strategy on the operation |
| Declared generator not found | Confusing method/class name with bean name, or bean not registered | Check bean name, component scan, `@Bean`, and `KeyGenerator` type |
| Wrong cache hit across two tenants | Expression only selects `productId`, omitting `tenantId` | Expand key identity and test data isolation |
| Two methods share cache yet return wrong data types | Colliding `cacheName` and `key` despite different semantics | Separate cache names or add controlled key namespacing |
| Cache eviction has no effect | `@Cacheable` and `@CacheEvict` compute different keys | Align key strategy across operations |
| Parameter-name `key` throws SpEL error | Missing parameter-name metadata | Use `#p0`/`#a0` or enable compilation with `-parameters` |
| `KeyGenerator` runs yet never hits | Returns unstable key, mutable object, or broken `equals/hashCode` | Use immutable keys and test equality |
| Mistaking `@CacheConfig` + method `key` for a conflict | Confusing class-level default with operation config | Method-level `key` overrides class-level default `keyGenerator` |
| `key = "'fixed'"` returns wrong data | Constant key used across parameters that actually vary results | Make key depend on parameters that determine the result |

## 10. Self-Check

**Question 1.** Are the two annotations below equivalent?

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
~~~

**Answer:** Not necessarily. The first uses the first argument directly. The second invokes the `skuKeyGenerator` bean, which may normalize or transform the key. The two lines illustrate two independent choices, not annotations stacked on one method.

**Question 2.** A method has `@Cacheable(key = "#p0", keyGenerator = "skuKeyGenerator")`. Does Spring automatically prioritize `key`?

**Answer:** No. This is an **invalid configuration** because the two attributes are mutually exclusive on the same operation. One attribute must be removed.

**Question 3.** A class has `@CacheConfig(keyGenerator = "skuKeyGenerator")`, and a method has `@Cacheable(cacheNames = "products", key = "#p0")`. Is this a simultaneous `key` and `keyGenerator` error?

**Answer:** No. Operation-level `key` overrides the class-level default `keyGenerator`. The method uses SpEL.

**Question 4.** Why is `@Cacheable(key = "#result.id")` unsuitable for lookups?

**Answer:** The key must be computed to check the cache **before** executing the method; at that time no result exists. Do not rely on `#result` in `@Cacheable` lookup keys.

**Question 5.** When a project has many operations needing the same SKU normalization, what should you choose?

**Answer:** Usually a clearly named `KeyGenerator` with dedicated tests; ensure `@Cacheable`/`@CachePut`/`@CacheEvict` all compute the same key when operating on the same entry.

## Conclusion

- **key** is a SpEL expression computing the key at the operation.
- **keyGenerator** is the name of a Java bean implementing a key-generation strategy.
- **Never declare both non-empty attributes simultaneously on the same cache operation**: Spring throws an exception rather than picking one automatically.
- **@CacheConfig(keyGenerator=...) is only a class-level default**; a method with its own **key** can validly override that default.
- Cache correctness depends on the **actual generated key**, consistency across operations, and how the provider stores and retrieves keys.

### Official Documentation

- Spring Framework – Annotation-based caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Custom key generation and mutually exclusive note: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – SpEL: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Framework – KeyGenerator interface: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework – @CacheConfig: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
