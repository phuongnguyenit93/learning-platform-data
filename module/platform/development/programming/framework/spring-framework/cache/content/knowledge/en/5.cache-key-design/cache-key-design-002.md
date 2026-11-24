# Null Arguments, Array Arguments, and Composite Keys in Spring Cache

> **Context:** Spring Framework → Cache → Key Design.  
> This lesson focuses on converting method parameters into cache keys correctly: distinguishing **zero parameters** from a **`null` parameter**, understanding how **arrays** are handled, and building collision-free **composite keys** when there are multiple arguments or when running with a distributed cache.

## 1. Why Does Key Design Determine Cache Correctness?

For a method annotated with `@Cacheable`, Spring computes a **cache key** from the method invocation to look up an entry in a cache region (`cacheNames`). If a matching entry exists, the method may be skipped and the cached result returned; if not, Spring executes the method and stores the result according to policy.

Therefore, a cache key must represent **all and only** the factors that change the result. Two error categories are especially dangerous:

- **False hit (wrong key collision):** two business-wise distinct invocations produce the same key, causing the system to return data from another call. For example, omitting `tenantId` from the key and sharing a cache across multiple tenants can lead to data leaks.
- **False miss (different keys despite the same meaning):** two equivalent invocations produce different keys, losing the benefit of caching. For example, using an array's memory address directly as the key instead of its contents causes `new int[]{1, 2}` on two calls to produce two different keys.

Both risks arise when parameters involve `null`, arrays, mutable lists/objects, or when multiple fields must be combined into one key. The choice of cache backend (ConcurrentMap, Caffeine, Redis, etc.) also determines which key formats are accepted and how keys are converted for storage.

## 2. Default Key Algorithm: `SimpleKeyGenerator`

When `@Cacheable` does not declare a `key` or `keyGenerator` and no custom default generator is configured, Spring uses `org.springframework.cache.interceptor.SimpleKeyGenerator`.

| Method parameters | Default key | Practical meaning |
|---|---|---|
| **0 arguments** | `SimpleKey.EMPTY` | All zero-argument calls use the same key within a given cache name. |
| **1 argument, non-`null`, not an array** | That argument object itself | Requires valid `equals()`/`hashCode()` and must not mutate while acting as a key. |
| **1 argument equal to `null`** | A `SimpleKey` containing a `null` element | Does not return `null` itself as the key; remains distinct from the zero-argument case. |
| **1 argument that is an array** | A `SimpleKey` containing that array | Compares array contents using `SimpleKey`'s deep equality mechanism. |
| **2 or more arguments** | A `SimpleKey` containing the arguments in order | Preserves both `null` and arrays inside; element position/order is significant. |

In essence, the logic corresponds to the following simplified form:

```java
// Illustrates the default logic, not code to copy to replace Spring:
if (params.length == 0) {
    return SimpleKey.EMPTY;
}
if (params.length == 1
        && params[0] != null
        && !params[0].getClass().isArray()) {
    return params[0];
}
return new SimpleKey(params);
```

Note a subtle point: documentation often says "one argument uses the argument itself", but **the source code has exceptions for `null` and arrays**. Because `null` or an array is wrapped in `SimpleKey`, the default key is safer in a map-based cache than manually setting `key="#p0"`.

### Identity Rules

- `SimpleKey.EMPTY` is **different** from `new SimpleKey((Object) null)`.
- One array `new int[]{1, 2}` and another array with the same content produce equal `SimpleKey` instances; using two Java arrays directly as keys causes `array1.equals(array2)` to return `false`, because arrays inherit reference comparison.
- `new SimpleKey("T1", "SKU7")` differs from `new SimpleKey("SKU7", "T1")` and differs from `new SimpleKey("T2", "SKU7")`.
- A single `List` or `Map` **is not an array**, so `SimpleKeyGenerator` normally returns that collection/map itself. Common Java collections compare by element, but mutability while serving as a key and convertibility to a backend key still need consideration.
- By default, `SimpleKeyGenerator` **does not add the method name, class name, or bean name to the key**. Cache names separate key spaces; if two methods with different meanings share the same `cacheNames` and the same parameter set, they can accidentally share entries.

## 3. Null Argument Cases

### 3.1. Zero Arguments and One `null` Argument Are Two Different Situations

Consider two methods:

```java
@Cacheable("settings")
public String defaultTheme() { /* ... */ }

@Cacheable("settings")
public String themeFor(String accountId) { /* ... */ }
```

These are illustrative methods, not a standalone Java file.

- Calling `defaultTheme()` has zero arguments: the key is `SimpleKey.EMPTY`.
- Calling `themeFor(null)` has **one argument with value null**: the key is a `SimpleKey` containing one `null` element.
- Calling `themeFor("A1")` has one String argument: the key is `"A1"`.

Do not confuse a single-argument null call with a zero-argument call; when inspecting keys in a debugger, check both **parameter count and values**.

### 3.2. Error When Forcing `key` to an Expression Returning `null`

This example has a problem when `customerId == null`:

```java
@Cacheable(cacheNames = "customers", key = "#p0")
public Customer find(String customerId) {
    // ...
}
```

`#p0` directly returns `null`. Spring Cache requires a valid key and does not accept a `null` key computation result for a cache operation, so it can throw an `IllegalArgumentException` like "Null key returned for cache operation". The fact that **a method accepts null** does not mean **the key is allowed to be null**.

There are three ways to handle this depending on business needs:

1. **Allow null as a meaningful input:** keep the default key (`SimpleKeyGenerator` wraps null), or create a composite key with an explicit nullable field.
2. **Do not cache calls with a null argument:** use `condition` to skip caching while still executing the method.

   ```java
   @Cacheable(cacheNames = "customers", condition = "#p0 != null")
   public Customer find(String customerId) {
       // ...
   }
   ```

3. **Map null to a sentinel:** only do this when the sentinel cannot collide with real data values. For example, `key="#p0 ?: 'UNKNOWN'"` is **unsafe** if a valid `customerId` can equal `"UNKNOWN"`. It is better to have a tag distinguishing null from actual strings, or a clearly typed key structure.

**Two kinds of null are not the same:**

- **Null in *parameters*** affects cache key generation.
- **Null as the *return value*** relates to value caching policy (`allowNullValues`, how the provider stores null, or `unless = "#result == null"`). A provider forbidding null values **does not mean** all methods with null arguments are forbidden.

With `@Cacheable`, `condition` is evaluated before calling the method to decide whether to cache; `unless` is evaluated after the method completes to decide whether to store the **result**. Do not use `unless` to fix a key expression returning null.

### 3.3. Null in Composite Keys

For the signature `lookup(String tenant, String language)`, the pair `("T1", null)` and the pair `(null, "T1")` must produce different keys. `new SimpleKey("T1", null)` and `new SimpleKey(null, "T1")` distinguish them properly by preserving both **position** and **the null value**.

If you concatenate strings like `tenant + ":" + language`, Java turns `null` into the string `"null"`: it can collide with a real literal `"null"` value. When null has business meaning, use an encoder with **type tags or length prefixes** to distinguish them.

## 4. Array Argument Cases

### 4.1. Java Arrays Use Reference `equals`

```java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(first == second);                 // false
System.out.println(first.equals(second));           // false
System.out.println(java.util.Arrays.equals(first, second)); // true
```

The Java code above is a snippet (which can be placed inside a class's `main`); the commented results are accurate for two newly created arrays.

When writing:

```java
@Cacheable(cacheNames = "recommendations", key = "#p0")
public String recommend(int[] selectedCategories) {
    // ...
}
```

`key="#p0"` returns the array object directly, so with a local `Map`-based cache, newly created arrays with the same content will **constantly miss**. Similarly, `#p0.toString()` produces a string like `[I@...` based on identity, not the numeric array contents, and is unsuitable as a business key.

Conversely, if **no `key` is declared**, `SimpleKeyGenerator` sees that the argument is an array and wraps it in `SimpleKey`; `SimpleKey` uses deep hash and equality comparison on the elements. Two arrays of the same type and content can therefore hit the same entry in a local cache.

### 4.2. One-Dimensional, Nested, Primitive, and Object Arrays

| Input | Key points to note |
|---|---|
| `int[]{1, 2}` | `Arrays.equals(int[], int[])` compares by value; default key wraps it in `SimpleKey`. |
| `String[]{"a", "b"}` | Each element is compared via `equals`; a different order means a different key. |
| `int[][]{{1, 2}, {3}}` | `SimpleKey` uses deep equality, suitable for nested arrays when elements have stable semantics. |
| `Object[]{someDto, ...}` | Nested DTOs must still have consistent `equals`/`hashCode`; they do not gain value semantics merely by being inside an array. |
| Empty array `new int[0]` | Distinct from a null argument and distinct from the zero-argument method case. |
| Array with `null` elements | Element nulls are preserved in deep comparison; null elements are not automatically stripped. |
| `List<Integer>` or `Map<...>` | These are collections, **not arrays**; a single collection is usually returned directly as the key. |

**Arrays are mutable data.** Do not modify the array or objects inside it after the key has been created and stored in the cache. `SimpleKey` holds the key structure and computes hashes from the original values; mutating referenced object contents can make `equals/hashCode` inconsistent, causing entries to become unlookupable. Safer strategies include: converting inputs into immutable values, taking a snapshot/copy when constructing the key, or normalizing into an encoded String.

### 4.3. Ordered Arrays vs. Unordered Sets

Two requests `tags = [1, 2]` and `tags = [2, 1]` can be:

- **Different in business meaning**, if order affects the result: preserve the original order in the key.
- **Equivalent**, if this represents a set filter: normalize before creating the key, for example deduplicating if business rules allow and then sorting on a **copy** of the array, avoiding mutating the object passed by the caller.

This decision must be based on real semantics. Do not automatically sort every array: for shopping carts, processing pipelines, paths, or priority-ordered queries, sorting can cause false hits.

## 5. Composite Keys with Multiple Arguments

Suppose a service has the signature:

```java
@Cacheable(cacheNames = "prices")
public Price price(String tenantId, String sku, String currency) {
    // ...
}
```

With three arguments, Spring defaults to creating `SimpleKey(tenantId, sku, currency)`. This is a reasonable choice **if all three fields affect the result**.

However, many signatures include technical arguments such as `traceId`, `debug`, `pageRequest`, or a locale used only for logging. If those fields **do not affect** the result, including them in the key causes false misses. Conversely, if `currency` or `tenantId` affects the result and is omitted, it can cause false hits.

### 5.1. Selecting Key Components Based on Business Output

| Component | Should it be in the key? | Reason |
|---|---|---|
| `tenantId` when tenant data is isolated | **Must include** | Prevents reading another tenant's data. |
| `sku`, `productId` | Usually yes | Identifies the entity being queried. |
| `currency`, `locale`, `region` | Yes if it changes the returned data | The same SKU may have different prices/formats/rules per region. |
| `page`, `size`, `sort`, filters | Yes when changing the result | Different pages/filters must have different keys. |
| `traceId` used only for tracing | Usually omit | Trace ID changes every request, causing constant misses. |
| `timeout` controlling only wait time without changing data | Depends on method contract | Not needed if output does not depend on timeout; needed if business logic actually changes. |
| `userId` or permission context | Yes if it determines results/visibility | Prevents cache from sharing permission-scoped information. |

**Separate key namespace from key body clearly.** The same key `"P42"` in `cacheNames="products"` and `cacheNames="stock"` belongs to two different caches. However, two different methods using the **same** cache name and the same key `"P42"` can collide. Scope cache names properly or include a business domain/version prefix in the key. When using Redis, a cache manager prefix can help isolate namespaces, but it does not replace defining all key fields completely.

### 5.2. Do Not Concatenate Strings Ambiguously

This is easy to write but prone to collisions:

```java
String key = tenant + ":" + sku;
```

For example:

- `tenant = "A:B"`, `sku = "C"` → `"A:B:C"`.
- `tenant = "A"`, `sku = "B:C"` → `"A:B:C"`.

Two different pairs produce the same key. Direct concatenation also confuses `null` with the literal `"null"`, or number `1` with text `"1"` if no type tag is attached.

There are three strategies:

1. **Local cache, small composite, clear value semantics:** use the default `SimpleKey` or an immutable key object/record with the appropriate fields.
2. **Only need to pick a subset of arguments:** use a SpEL `key` expression to select components, while ensuring the expression never returns `null` and never loses information.
3. **Complex keys or cross-service sharing:** use a `KeyGenerator` or a standardized encoding function with versioning, type tags, escaping/length-prefixing, and a documented format.

**Note on Java `record`:** records auto-generate `equals/hashCode` per component, but **array components still use identity comparison**, rather than automatically giving arrays deep value comparison. If a record holds an array, choose an immutable value-based structure (such as a `List<Integer>` snapshot) or implement equality/hash properly yourself.

## 6. Complete Runnable Example: `null`, Arrays, and Composites in Spring Framework

This example uses **Java 17+**, **Maven**, **Spring Framework 6.2.12**, and the in-memory `ConcurrentMapCacheManager` cache. It runs standalone without Redis or a database. Versions are pinned for reproducibility; when applying to a real project, use versions managed by and compatible with your project.

Directory tree:

```text
spring-cache-key-cases/
├── pom.xml
└── src/main/java/dev/example/cachekeys/
    ├── CacheKeyLesson.java
    └── StableSearchKey.java
```

### 6.1. Maven Dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-cache-key-cases</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.cachekeys.CacheKeyLesson</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Stable String Key Builder for a Search Accepting Null and Arrays

**`src/main/java/dev/example/cachekeys/StableSearchKey.java`**

```java
package dev.example.cachekeys;

import java.util.StringJoiner;

public final class StableSearchKey {
    private StableSearchKey() {
    }

    public static String of(String tenant, int[] filters) {
        return "search:v1|" + encodeText(tenant) + "|" + encodeInts(filters);
    }

    private static String encodeText(String text) {
        return text == null ? "N" : "S" + text.length() + ":" + text;
    }

    private static String encodeInts(int[] values) {
        if (values == null) {
            return "N";
        }
        StringJoiner joiner = new StringJoiner(",", "A" + values.length + ":", "");
        for (int value : values) {
            joiner.add(Integer.toString(value));
        }
        return joiner.toString();
    }
}
```

This encoding convention distinguishes the cases:

- `null` text → `N`; literal text `"N"` → `S1:N`.
- `null` array → `N`; empty array → `A0:`; array `[1, 2]` → `A2:1,2`.
- The prefix `search:v1` marks the domain and version of the key format; if the format changes, version/invalidation must be handled consistently.
- `String.length()` is Java's UTF-16 length. For polyglot systems, all parties must agree on a single length/encoding standard implemented identically before sharing keys.

This is a purpose-built format for the `String` + `int[]` example; it is **not** a general-purpose serializer for arbitrary object types. The filter currently preserves order assuming order affects the result. If filters behave as a set, normalize a **copy** before encoding.

### 6.3. Caching Annotation Configuration and Method Invocations

**`src/main/java/dev/example/cachekeys/CacheKeyLesson.java`**

```java
package dev.example.cachekeys;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheKeyLesson {
    public static void main(String[] args) {
        // Generate default keys directly to see the exception cases.
        Object noArgs = SimpleKeyGenerator.generateKey();
        Object oneNull = SimpleKeyGenerator.generateKey((Object) null);
        Object array1 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object array2 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object pair1 = SimpleKeyGenerator.generateKey("T1", "SKU7");
        Object pair2 = SimpleKeyGenerator.generateKey("T1", "SKU7");

        System.out.println("zeroKey=" + noArgs.equals(SimpleKey.EMPTY));
        System.out.println("nullKeyIsSimpleKey=" + (oneNull instanceof SimpleKey));
        System.out.println("arrayKeysEqual=" + array1.equals(array2));
        System.out.println("pairKeysEqual=" + pair1.equals(pair2));

        System.out.println("nullVsLiteral=" +
                !StableSearchKey.of(null, new int[] {1, 2})
                    .equals(StableSearchKey.of("N", new int[] {1, 2})));

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {
            LookupService service = context.getBean(LookupService.class);

            System.out.println("nullable1=" + service.byNullable(null));
            System.out.println("nullable2=" + service.byNullable(null));

            System.out.println("array1=" + service.byArray(new int[] {1, 2}));
            System.out.println("array2=" + service.byArray(new int[] {1, 2}));

            System.out.println("composite1=" + service.byComposite("T1", "SKU7"));
            System.out.println("composite2=" + service.byComposite("T1", "SKU7"));
            System.out.println("composite3=" + service.byComposite("T2", "SKU7"));

            System.out.println("search1=" + service.search(null, new int[] {1, 2}));
            System.out.println("search2=" + service.search(null, new int[] {1, 2}));
            System.out.println("search3=" + service.search("N", new int[] {1, 2}));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "nullable", "arrays", "composite", "search");
        }

        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger nullableLoads = new AtomicInteger();
        private final AtomicInteger arrayLoads = new AtomicInteger();
        private final AtomicInteger compositeLoads = new AtomicInteger();
        private final AtomicInteger searchLoads = new AtomicInteger();

        @Cacheable(cacheNames = "nullable")
        public String byNullable(String value) {
            return "nullable#" + nullableLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "arrays")
        public String byArray(int[] values) {
            return "sum" + Arrays.stream(values).sum()
                    + "#" + arrayLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "composite")
        public String byComposite(String tenant, String sku) {
            return "item-" + tenant + "-" + sku
                    + "#" + compositeLoads.incrementAndGet();
        }

        @Cacheable(
                cacheNames = "search",
                key = "T(dev.example.cachekeys.StableSearchKey).of(#p0, #p1)")
        public String search(String tenant, int[] filters) {
            return "search#" + searchLoads.incrementAndGet();
        }
    }
}
```

**Run the project:** place the exact two Java files and `pom.xml` as shown above, then open a terminal in the `spring-cache-key-cases` directory.

```bash
mvn -q compile exec:java
```

**Stdout of the `System.out.println` lines** from a fresh run (excluding environment/Maven logs):

```text
zeroKey=true
nullKeyIsSimpleKey=true
arrayKeysEqual=true
pairKeysEqual=true
nullVsLiteral=true
nullable1=nullable#1
nullable2=nullable#1
array1=sum3#1
array2=sum3#1
composite1=item-T1-SKU7#1
composite2=item-T1-SKU7#1
composite3=item-T2-SKU7#2
search1=search#1
search2=search#1
search3=search#2
```

### 6.4. What Is Proven?

- **Null argument:** two calls to `byNullable(null)` use the same `SimpleKey` containing null, so the method increments the counter only once.
- **Array argument:** each call creates `new int[]{1, 2}`, yet the default key wraps the array by value so the second call hits.
- **Default composite:** `("T1", "SKU7")` hits when repeated; `("T2", "SKU7")` is a different key so it misses.
- **Custom-format String composite:** `search(null, [1,2])` hits when repeated; `search("N", [1,2])` misses, because null and literal `N` are encoded differently.
- **Proxy:** the calls go from `main` through the Spring bean proxy; `@EnableCaching` takes effect. Creating the object with `new LookupService()` outside the context or self-invoking `this.byArray(...)` inside the same bean bypasses the default cache interceptor.

**Java varargs note when testing `SimpleKeyGenerator.generateKey` directly:** you must cast a single null parameter to `(Object) null` to pass **one null argument**. Writing `generateKey(null)` can be interpreted by the compiler as a **null varargs array**, which does not represent the case being tested. For a single array argument, `(Object) new int[]{...}` clearly expresses that the entire array is **one** argument.

## 7. When to Use SpEL `key` vs. `KeyGenerator`?

### 7.1. Selecting a Subset of Arguments with SpEL

Suppose the data depends on `tenant` and `sku`, while `traceId` is only for observability:

```java
@Cacheable(cacheNames = "products",
           key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public Product load(String tenant, String sku, String traceId) {
    // ...
}
```

This snippet **is illustrative on a service that already has `Product` and a repository**. SpEL invokes the `SimpleKey` constructor with two arguments, allowing null components to be preserved without string concatenation. `traceId` is excluded because it does not change the result. Similarly, you can write `key = "#p0"` when selecting a single argument **guaranteed to be non-null and to have stable equality**.

Parameter syntax:

- `#p0` or `#a0`: the first parameter.
- `#p1` or `#a1`: the second parameter.
- `#root.args[0]`: access via the invocation's argument array.
- `#tenant`: use parameter names only when parameter name metadata is available, such as when compiled with `-parameters`. Using `#p0` keeps examples independent of parameter name retention settings.

**Do not specify both `key` and `keyGenerator` on the same cache operation.** These two options are mutually exclusive.

### 7.2. Reusing Logic and Encoding for Distributed Caches

When multiple methods share the same rule, or when versioned/escaped/length-prefixed encoding is needed, declare a `KeyGenerator` bean:

```java
@Bean("searchKeyGenerator")
public KeyGenerator searchKeyGenerator() {
    return (target, method, params) ->
            StableSearchKey.of((String) params[0], (int[]) params[1]);
}
```

This is an **illustrative configuration method**, requiring the import of `org.springframework.cache.interceptor.KeyGenerator` and the `StableSearchKey` class from the previous example. Usage:

```java
@Cacheable(cacheNames = "search", keyGenerator = "searchKeyGenerator")
public SearchResult search(String tenant, int[] filters) {
    // ...
}
```

This service snippet is also **illustrative**, not a standalone runnable program. Naming the generator lets multiple places share the key rule. If there is a `@CacheEvict` or `@CachePut` for the same entry, **it must produce the exact same key** when performing update/evict operations. Do not add the method name to the key arbitrarily: read methods and eviction methods usually have different names.

With Redis or a distributed cache, the final key must usually be converted into bytes or a String; a Java object that works well in a local map **does not by default** have a stable representation across nodes/versions. When choosing keys for Redis, check the conversion service, key prefix, serializer, and encoding of the Spring Data Redis version in use. A specific String format controlled by the application is usually easier to inspect with operational tools.

## 8. Collisions and Consistency with `@CachePut` / `@CacheEvict`

An entry is identified by **cache name + key**. Read and eviction paths must align exactly.

**Dangerous example** (illustrative):

```java
@Cacheable(cacheNames = "products")
public Product find(String tenant, String sku) {
    // default key: SimpleKey(tenant, sku)
}

@CacheEvict(cacheNames = "products", key = "#p1")
public void update(String tenant, String sku, ProductUpdate update) {
    // eviction key: sku, does not match SimpleKey(tenant, sku)
}
```

If evicting only by `sku`, the entry cached under the composite key remains, so subsequent reads may return stale data.

**The consistent approach** is to use one composite rule for both operations:

```java
@Cacheable(
        cacheNames = "products",
        key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public Product find(String tenant, String sku) {
    // ...
}

@CacheEvict(
        cacheNames = "products",
        key = "new org.springframework.cache.interceptor.SimpleKey(#p0, #p1)")
public void update(String tenant, String sku, ProductUpdate update) {
    // ...
}
```

These snippets live inside a service with declared dependencies; they are not standalone files. They illustrate **the same key expression** for cache read and evict. For real data updates, you must also consider database transaction commit timing, read/write races, TTL, and other writers modifying the data.

Note that `SimpleKeyGenerator` does not automatically include the method name, so **two different methods in the same `cacheNames`** with the same parameters can point to the same cache entry. If their return contents differ, use different cache names or explicit business prefixes.

## 9. Common Errors, Detection, and Fixes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@Cacheable(key="#p0")` fails when argument is null | SpEL returns null as the key | Let the default key wrap null, skip caching null inputs via `condition`, or use a key encoder that separates null clearly. |
| Two arrays with identical elements do not hit | `key="#p0"` returns the array object, which uses identity equality | Use the default key for arrays or create a snapshot + content-based encoding. |
| Every request with the same filter misses | Using array `toString()` or an unstable DTO | Normalize the object by its required fields and use a stable key format. |
| Stored key cannot be found after modifying array/map | Key object was mutated, changing `equals/hashCode` | Use immutable data or copy before creating the key. |
| Tenant A's price appears for tenant B | `tenantId` or access permissions omitted from key | Add all partitioning/security factors affecting the result; audit cache names and sharing. |
| Two different field pairs produce the same String key | Concatenation without escaping or length-prefixing | Use components with type tags + length or an encoding tested to be injective. |
| Data updates but `@CacheEvict` does not remove the entry | Eviction key and read key use different rules | Centralize key generation and test read/evict pairs on the same inputs. |
| Local cache works, Redis throws key conversion error | Provider requires an appropriate converter/serializer | Generate a stable String key or register proper type conversion; check namespaces and byte encoding. |
| Two methods with different logic share an entry | Same cache name and same key; default excludes method | Separate cache names, add a domain prefix or namespace. |
| Different filter ordering causes unnecessary misses | Key preserves order while business treats filters as a set | Normalize by sorting/deduplicating on a copy if semantics allow. |
| Record containing an array still misses with identical content | Record-generated equality for arrays still relies on identity | Convert the array to an immutable value-based collection or implement content-based equality/hash manually. |

## 10. Testing Keys and Production Considerations

### 10.1. Minimum Test Cases

For every cacheable method with complex arguments, verify at least:

1. **Zero args, one null, one empty array:** ensure these states are never confused.
2. **Array value equality:** two array instances with identical contents hit the same entry if business-equivalent; different contents miss.
3. **Element order:** verify whether `[1, 2]` and `[2, 1]` are equivalent or distinct according to business rules.
4. **Composite pair:** same tuple hits; changing any relevant field misses. Especially test changing `tenantId` and permission fields.
5. **Null vs. literal:** `null`, `"null"`, `""`, and sentinels are all distinguished if business rules require.
6. **Delimiter characters:** fields containing `:`, `|`, spaces, Vietnamese characters, Unicode; avoid string concatenation collisions.
7. **Mutation:** modify the array/collection after creating the key and verify the system avoids depending on mutable objects or blocks mutation.
8. **Key generation vs. eviction:** read, update/evict, then read again and measure whether the loader runs as expected.
9. **Multiple cache methods:** two different methods sharing `cacheNames` do not accidentally share entries with different data types.
10. **Real provider:** run the same tests on Caffeine/Redis if the project uses them; verify key conversion, serialization, key prefixes, cache names, and multi-node deployment.
11. **Version changes:** a new key format can coexist with old data; version prefixes/invalidation must be designed before deployment.
12. **Performance and security:** keys should not contain raw tokens/passwords/PII if avoidable; consider key size, cardinality, entry count, and retention duration.

### 10.2. Principles When Defining a Custom Key Encoder

A good key encoder needs the following properties:

- **Deterministic:** the same business input produces the same key across calls, JVMs, and nodes.
- **Complete:** variables affecting the result are included; cases like tenant/permissions cannot be omitted.
- **Unambiguous:** different tuples never accidentally collapse to the same key; null, empty, and literal sentinels must be distinct.
- **Immutable/canonical:** does not depend on object addresses, random hashes, JVM locale, or mutating data.
- **Versioned and operable:** has a namespace, clear format, reasonable length, and migration/invalidation rules when schemas change.
- **Consistent across operations:** `@Cacheable`, `@CachePut`, and `@CacheEvict` all resolve the corresponding key identically.

A **hash of the data** can reduce key size, but requires choosing an appropriate algorithm and still considering collision probability, canonical representation, encoding, and debuggability. `Object.hashCode()` or an ambiguous concatenated string is **not** a stable identifier for distributed business data.

## 11. Quick Decision Checklist

When designing caching for a method, answer in order:

1. **Which parameters does the result depend on?** List all of them, including tenant, auth scope, locale, or filters.
2. **Are there `null` values?** Decide whether null has business value or caching should be skipped; avoid letting a SpEL key return null.
3. **Are there arrays/lists/maps?** Determine whether order is significant, whether objects are mutable, and whether equality is value-based.
4. **Are there multiple fields?** If using default `SimpleKey`, only rely on it when every argument maps to the output; if selecting a subset, define the key explicitly.
5. **Which backend will receive the key?** For local caches, object keys work when equality is stable; for Redis/distributed caches, define a concrete conversion/String format.
6. **How does invalidation reproduce the exact key?** Ensure update/evict methods have the required parameters and use the exact same rule.
7. **Do tests cover collisions and false misses?** At minimum test null, equal-content arrays, reordered arrays, different tenants, and delimiter characters.

### Official Documentation

- Spring Framework — Default Key Generation and SpEL keys: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- `SimpleKeyGenerator` Javadoc (Spring Framework 6.2.x): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- `SimpleKey` Javadoc (Spring Framework 6.2.x): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html
- Spring Data Redis — Cache key conversion and configuration: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
