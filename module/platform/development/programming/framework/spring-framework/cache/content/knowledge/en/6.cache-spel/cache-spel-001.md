# Using `key` to Select Arguments or Argument Properties in Spring Cache (SpEL)

## 1. The Problem: Multiple Parameters, Yet Only Part Determines the Data

In the Spring Framework, `@Cacheable` typically takes the result of a method and stores it in a cache. The cache needs a **cache key** to distinguish which calls can share the same result. If two calls share the same cache region name and the same key, a subsequent call can immediately receive the stored result without executing the actual method.

For example:

```java
Product findProduct(String sku, String requestId)
```

If `sku` identifies the product while `requestId` is only for request tracing, two calls with the same `sku` but different `requestId` values should receive the same data. You can select `sku` alone as the key, avoiding creating unnecessary entries for the same product.

Conversely:

```java
Price findPrice(String sku, String currency)
```

The returned price depends on both `sku` and `currency`; selecting only `sku` as the key risks returning a USD price for a VND request. The central rule is:

> **Include in the key every factor that changes the cached result, and omit parameters that genuinely do not change the result.**

This lesson focuses on how to use the `key` attribute of Spring Cache annotations to **select arguments, read properties/fields, invoke accessors, access nested elements, and construct keys from multiple components using SpEL**.

## 2. `key` Is a SpEL Expression, Not a Plain Java Variable Name

Syntax:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) { /* ... */ }
```

In this annotation:

- `cacheNames="products"` selects the **cache region**. The region name and key value together determine the logical location of the entry.
- `key="#p0"` is a **Spring Expression Language (SpEL)** expression. The `#` symbol references a variable in the expression evaluation context; here `p0` is the first argument (0-based index).
- The key value is computed at method invocation time by the Spring caching interceptor, **not** by using the literal string `"#p0"` as the key.
- You do not need to wrap the expression with `#{...}` inside the `key` attribute. For example, `key="#p0"` is correct; `key="'#p0'"` produces the literal string `#p0` and can cause every request to collide on the same key.

If the `key` attribute is omitted, Spring uses the default `KeyGenerator`: no parameters → `SimpleKey.EMPTY`; one parameter → that parameter itself; multiple parameters → a `SimpleKey` containing all parameters. This can create unnecessary keys if extra metadata is present, or depend on how objects implement `equals()/hashCode()`.

**Key takeaway:** customizing `key` controls call equivalence. It does not change how data is fetched from the source, nor does it automatically refresh an entry when the underlying source data changes.

## 3. Selecting an Argument by Name or Position

All of the following reference styles are supported by Spring in the cache context:

| SpEL Expression | What It Selects | When to Use |
| --- | --- | --- |
| `#sku` | Argument with Java name `sku` | When parameter names are available at runtime |
| `#p0` | First argument | Reliable even when parameter names cannot be resolved at runtime |
| `#a0` | First argument | Equivalent alias for `#p0` |
| `#p1` or `#a1` | Second argument | When only the second parameter is used as the key |
| `#root.args[0]` | First element of the arguments array | Explicit expression via the root context |
| `#root.args[1]` | Second element | Useful when reading by position |

Example of two ways to point to the same parameter:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku, String requestId) {
    return repository.findBySku(sku);
}

@Cacheable(cacheNames = "products", key = "#sku")
public Product findBySku(String sku, String requestId) {
    return repository.findBySku(sku);
}
```

The two examples above are **illustrative snippets inside a service that already has `repository`**, not two methods to copy verbatim into the runnable program below. They can share entries because they use the same `products` region and the same SKU key, provided they return the same type and the same data semantics.

With `#sku`, Spring needs to know the parameter name at runtime; in Java, you should compile with the `-parameters` flag (for example, configuring `<maven.compiler.parameters>true</maven.compiler.parameters>`). If parameter names are missing, the expression may fail to evaluate properly. `#p0`/`#a0` do not depend on this flag. **Do not confuse `#p1` with the first parameter.** Indexing starts at 0.

Example of selecting the second argument accurately:

```java
@Cacheable(cacheNames = "products", key = "#p1")
public Product lookup(String requestId, String sku) {
    return repository.findBySku(sku);
}
```

With `lookup("trace-A", "P1")` and `lookup("trace-B", "P1")`, both evaluate to the key `"P1"`. If `#p0` were used, they would get two different keys (`"trace-A"` and `"trace-B"`) even though we want to cache by product.

**Condition for omitting an argument:** the omitted argument must genuinely not affect the method's return value, access permissions, tenant, locale, session state, or safety constraints. If the method also uses that metadata for logging or side effects, note that a cache hit can **skip the entire method body**, meaning those side effects will not execute either.

## 4. Selecting a Property or Accessor of an Argument

When a method accepts a request object, caching by the **entire object** may be suboptimal, especially if the object contains a trace ID, timestamp, or information that does not affect the result. SpEL can extract a property inside the object.

### 4.1. JavaBean with Getter

```java
public class ProductQuery {
    private final String sku;
    private final String requestId;

    public ProductQuery(String sku, String requestId) {
        this.sku = sku;
        this.requestId = requestId;
    }
    public String getSku() { return sku; }
    public String getRequestId() { return requestId; }
}

@Cacheable(cacheNames = "products", key = "#p0.sku")
public Product find(ProductQuery query) {
    return repository.findBySku(query.getSku());
}
```

`#p0.sku` reads the `sku` property following the JavaBean convention, via the `getSku()` getter. The field does not need to be `public`.

### 4.2. Java Record with Explicit Accessor

```java
public record ProductQuery(String sku, String requestId) {}

@Cacheable(cacheNames = "products", key = "#p0.sku()")
public Product find(ProductQuery query) {
    return repository.findBySku(query.sku());
}
```

A record generates the `sku()` method, so you can invoke the **accessor method** in SpEL using `#p0.sku()`. This notation also makes the distinction between property access and method invocation clear. Do not assume every Java structure has a `getSku()` getter.

### 4.3. Nested Properties

Suppose:

```java
record Customer(String id) {}
record OrderQuery(Customer customer, String orderId) {}
```

The key is the customer ID:

```java
@Cacheable(cacheNames = "ordersByCustomer", key = "#p0.customer().id()")
public java.util.List<Order> findOrders(OrderQuery query) {
    return repository.findByCustomerId(query.customer().id());
}
```

Access proceeds step by step: `#p0` → `customer()` → `id()`. However, if the method returns an **order list** that also depends on filters, pagination, user permissions, or a date range, customer ID alone is **not sufficient**. All factors affecting the result must be included in the key.

### 4.4. Map and Index

With an argument of type `Map<String, String>`:

```java
@Cacheable(cacheNames = "products", key = "#p0['sku']")
public Product find(Map<String, String> params) {
    return repository.findBySku(params.get("sku"));
}
```

The `['sku']` syntax accesses an entry by Map key. For a `List` or array, you can access by position: `#p0[0]`. This is an option when the input data has an appropriate structure; you must still verify key existence and data types.

### 4.5. Null and Navigation

`#p0.customer().id()` will fail when `query.customer() == null`. SpEL provides the safe navigation operator `?.`, such as `#p0.customer()?.id()`, but **returning null does not automatically become a valid key**: Spring Cache normally requires a non-null key. If the customer ID is mandatory, you should validate/ensure the validity of the argument before passing through the cache interceptor, or design the expression/condition so a fallback key does not cause data collisions. Do not use a default value like `"unknown"` that accidentally groups different customers into the same entry.

## 5. Selecting Multiple Properties to Build a Composite Key

Suppose `findPrice(PriceQuery query)` returns different prices by tenant, SKU, and currency:

```java
public record PriceQuery(String tenantId, String sku, String currency) {}

@Cacheable(
    cacheNames = "prices",
    key = "#p0.tenantId() + ':' + #p0.sku() + ':' + #p0.currency()"
)
public Price findPrice(PriceQuery query) {
    return priceRepository.find(
        query.tenantId(), query.sku(), query.currency());
}
```

This is an illustrative snippet, with `Price` and `priceRepository` provided by the actual application. The key for the request `("T1", "P1", "VND")` is `"T1:P1:VND"`. If the currency or tenant changes, the key must differ.

**Limitation of string concatenation:** if a component can contain the delimiter `:`, different tuples can sometimes produce the same key (for example, `("a:b", "c")` and `("a", "b:c")` when concatenating two parts). For uncontrolled input, you should use unambiguous encoding or a custom `KeyGenerator` that produces a structured key such as `SimpleKey(tenantId, sku, currency)`. Ensure the key has stable `equals()/hashCode()` and is compatible with the provider's serialization (especially for distributed caches).

A composite key can also combine **two different arguments**:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0 + ':' + #p1"
)
public Price findPrice(String sku, String currency) {
    return priceRepository.find(sku, currency);
}
```

If the method also accepts `tenantId`, you must add it to the key; **do not** rely solely on `sku` and `currency` when the price also depends on the tenant. The two-argument example above assumes prices are tenant-independent and the component strings are constrained so they cannot contain the delimiter.

For reference-type arguments, using the entire object as the default key can be problematic: two instances containing the same SKU without value-based `equals()/hashCode()` will become two different keys in a local cache; when the key is extracted with `#p0.sku()`, both resolve to a stable SKU key. Similarly, you should not use a mutable object directly as the key.

## 6. Runnable Example: Selecting the Second Argument and a Property of the First Argument

The Java 17 program below uses two cache regions to separate two key-selection contracts:

- `namesBySku`: `byLookup(Lookup request)` uses `#p0.sku()`. Different `traceId` values still hit the same SKU.
- `namesById`: `byId(String traceId, String sku)` uses `#p1`. Only the second argument value is the key.
- `invalidate(Lookup request)` uses **the same key expression** as `byLookup` to evict the right entry.

The two regions are separated so that source read counts and verification flow are easy to observe, not because SpEL itself requires multiple regions.

**File structure:**

```text
cache-spel-key/
├── pom.xml
└── src/main/java/CacheKeySpelDemo.java
```

**`pom.xml`** (Spring Framework 6.2.x, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-spel-key</artifactId>
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

**`src/main/java/CacheKeySpelDemo.java`:**

```java
import java.util.Map;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheKeySpelDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("namesBySku", "namesById");
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }

    public record Lookup(String sku, String traceId) {}

    public static class CatalogService {
        private final Map<String, String> names =
                Map.of("P1", "Pen", "P2", "Notebook");

        private int sourceReads = 0;

        @Cacheable(cacheNames = "namesBySku", key = "#p0.sku()")
        public String byLookup(Lookup request) {
            sourceReads++;
            return names.get(request.sku());
        }

        @Cacheable(cacheNames = "namesById", key = "#p1")
        public String byId(String traceId, String sku) {
            sourceReads++;
            return names.get(sku);
        }

        @CacheEvict(cacheNames = "namesBySku", key = "#p0.sku()")
        public void invalidate(Lookup request) {
            // Example: an operation that invalidates cached data by SKU.
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheKeySpelDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("Query trace 1: " +
                    service.byLookup(new Lookup("P1", "trace-001")));
            System.out.println("Query trace 2: " +
                    service.byLookup(new Lookup("P1", "trace-002")));
            System.out.println("Query P2: " +
                    service.byLookup(new Lookup("P2", "trace-003")));
            System.out.println("Reads query: " + service.sourceReads());

            System.out.println("Positional arg 1: " +
                    service.byId("trace-A", "P1"));
            System.out.println("Positional arg 2: " +
                    service.byId("trace-B", "P1"));
            System.out.println("Reads positional: " + service.sourceReads());

            service.invalidate(new Lookup("P1", "invalidate"));
            System.out.println("After eviction: " +
                    service.byLookup(new Lookup("P1", "trace-004")));
            System.out.println("Reads final: " + service.sourceReads());
        }
    }
}
```

Run in the `cache-spel-key` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheKeySpelDemo
```

**Lines printed by the program** (excluding Maven/Spring logs which may be configured differently per environment):

```text
Query trace 1: Pen
Query trace 2: Pen
Query P2: Notebook
Reads query: 2
Positional arg 1: Pen
Positional arg 2: Pen
Reads positional: 3
After eviction: Pen
Reads final: 4
```

Explanation:

1. `byLookup(P1, trace-001)` is the first cache miss: calls the source once, stores key `"P1"` in `namesBySku`.
2. `byLookup(P1, trace-002)` uses the same `#p0.sku()` → hit, does not increment `sourceReads` even though the request record differs.
3. `byLookup(P2, ...)` has key `"P2"` → miss, counter becomes 2.
4. `byId(trace-A, P1)` is a miss in **another region**; `#p1` points directly to SKU `"P1"`, incrementing the counter to 3. `byId(trace-B, P1)` reuses that entry.
5. `invalidate(P1)` removes key `"P1"` in `namesBySku`; `byLookup(P1, ...)` afterward misses and calls the source a 4th time.

This is a console application using `ConcurrentMapCacheManager` within a single JVM; it does not simulate TTL or distributed caching. `CatalogService` is a Spring bean; calls in `main` go through the proxy to trigger annotations. `#p0`/`#p1` are used intentionally so there is no dependency on whether compilation retains parameter names.

## 7. Combining `key` with Other Annotations

The `key` expression appears on `@Cacheable`, `@CachePut`, and `@CacheEvict`, but the timing and effect of each annotation differ:

| Annotation | Primary Timing | What Must Align |
| --- | --- | --- |
| `@Cacheable` | Evaluates the key to look up the cache before deciding whether to run the method | Calls returning the same result must have the same key |
| `@CachePut` | Method always runs; then the result is placed into the cache | Key on write must match key on read |
| `@CacheEvict` | Removes an entry; by default after the method completes successfully | Key on eviction must match the stored key; `allEntries=true` ignores `key` |
| `condition` | Condition to enable caching based on parameters/context | Condition is distinct from key selection |
| `unless` on `@Cacheable` | Checks the result after running the method to veto storing | Not part of the key |

Example of two methods with **different signatures** that share a consistent SKU key:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.findBySku(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0.sku()")
public void delete(DeleteProduct command) {
    repository.delete(command.sku());
}
```

If reading uses `key="#p0"` with `sku="P1"` while deleting uses `key="#p0"` with a **DeleteProduct object**, the two keys are not equivalent. You must access `sku()` on the command in the delete path.

The `#result` variable is only available in contexts Spring supports **after method invocation**: such as `unless`, key selection for `@CachePut`, or `@CacheEvict` with `beforeInvocation=false`. **Do not use `#result` as the key of `@Cacheable`**, because at cache lookup time the method result does not exist yet. With `@CacheEvict(beforeInvocation=true)`, `#result` is not yet available; a method failure can occur after the entry has already been evicted.

`key` and `keyGenerator` are **mutually exclusive** ways to select keys on the same annotation. Concise, immediately understandable expressions usually fit `key`; logic with complex rules, normalization, security, or serialization concerns should move to a separately tested `KeyGenerator`.

## 8. Common Mistakes and How to Check Them

### Mistake 1 — Selecting the wrong parameter index

```java
// Wrong: the key is requestId, not sku.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String requestId, String sku) { /* ... */ }

// Correct when the result depends only on sku.
@Cacheable(cacheNames = "products", key = "#p1")
public Product find(String requestId, String sku) { /* ... */ }
```

### Mistake 2 — Omitting a parameter that affects the result

If `findPrice(sku, currency, tenantId)` caches only by `sku`, currencies and tenants will unintentionally share entries. The key must include all parameters affecting price; at the same time, do not use cached data as a substitute for actual authorization checks.

### Mistake 3 — Parameter names lost during compilation

`key="#sku"` only works when the runtime knows parameter names. Use `#p0`/`#p1` or enable `-parameters`; avoid assuming every build preserves parameter names.

### Mistake 4 — Confusing a literal with an expression

`key="#p0.sku()"` evaluates the SKU from the request. `key="'#p0.sku()'"` returns the **constant string** `#p0.sku()`, causing requests to share one wrong key.

### Mistake 5 — Accessing a null property or wrong accessor

`#p0.customer().id()` fails if `customer()` is null; `#p0.sku()` requires the object to have a `sku()` method. For a standard JavaBean, use the property `#p0.sku` if a `getSku()` getter exists. Validate requests and test expressions with real data types.

### Mistake 6 — Mismatched keys across read, update, and evict

Reading `#p0.sku()` while evicting `#p0` with a different request type will fail to remove the intended entry. Create a “read/put/evict → region/key” table for the same data and write tests.

### Mistake 7 — Unstable keys or collision risks

Do not cache by mutable objects or data whose `toString()` changes over time; do not concatenate strings with unescaped delimiters. Choose immutable identifiers and consistent key normalization across call paths.

### Mistake 8 — Forgetting Spring proxy boundaries

`@EnableCaching`, a Spring-managed bean, and calling through a proxy are normal prerequisites for annotations to take effect. Self-invocation like `this.find(...)` within the same bean normally bypasses caching in default proxy mode; `private` or `final` methods also have proxy interception limitations. Place cache operations on methods that Spring can intercept.

## 9. Self-Check Exercises

**Scenario A.** Method `getProduct(String sku, String requestId)`; `requestId` is only a log identifier and does not affect the product. What key should be used?

Answer: `#p0` (or `#sku` when parameter names are retained). Two calls with the same SKU share the cache.

**Scenario B.** Method `getPrice(PriceQuery query)` with record `PriceQuery(String tenantId, String sku, String currency)`. Is `#p0.sku()` enough?

Answer: No. You must distinguish `tenantId`, `sku`, and `currency` simultaneously if all three affect the price. The key must avoid collisions and stay consistent with how the price is determined.

**Scenario C.** Method `lookup(String requestId, ProductQuery query)` where `ProductQuery` is a record with accessor `sku()`. How do you extract the SKU?

Answer: `#p1.sku()` or `#root.args[1].sku()`. `#p0.sku()` is wrong because the first argument is the `requestId` string.

**Scenario D.** Two request objects have different `traceId` values but the same `sku`; why can `key="#p0"` create two entries?

Answer: the key is the entire object. If `equals()/hashCode()` includes `traceId` (especially for records), the two requests have different keys. `key="#p0.sku()"` selects only the SKU, if SKU alone suffices to determine the result.

## 10. Pre-Production Checklist

1. List every factor affecting the result: identifiers, tenant, locale/currency, permission scope, filters, pagination, data version.
2. Define each region's key as a **sample input → expected key table**, including different tenants/locales and data with overlapping substrings.
3. Choose the access style matching the data type: `#p0`, `#p1`, `#p0.sku` for JavaBeans, `#p0.sku()` for records, `#p0['sku']` for Maps.
4. Ensure all `@Cacheable`/`@CachePut`/`@CacheEvict` paths for the same data produce the exact same key type; run hit/miss and invalidation tests.
5. Handle nulls, mutable objects, missing `-parameters` issues, string key collisions, backend serializer capabilities, and skipped side effects on cache hits.
6. Monitor hit/miss metrics per region and confirm source changes do not leave entries stale longer than the contract allows.

The best key selection is a function from **the inputs that determine the result** to **a cache identifier that is stable, unique within its region, and reproducible across read/write/evict paths**.

## Official Documentation

- Spring Framework — Custom Key Generation and Caching SpEL Context: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `Cacheable` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — SpEL Reference: https://docs.spring.io/spring-framework/reference/core/expressions.html
