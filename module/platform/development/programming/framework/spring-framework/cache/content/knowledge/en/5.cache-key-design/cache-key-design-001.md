# SimpleKeyGenerator with Zero, One, or Multiple Arguments in Spring Cache

## 1. The Problem: From Method Invocation to Cache Key

When calling a method annotated with `@Cacheable`, Spring needs a **cache key** to look up or store the result. The cache key represents the *meaningful inputs of the invocation*, while `cacheNames`/`CacheResolver` identifies the **cache region** where the key is used.

For example:

```java
@Cacheable("products")
public String getProduct(String sku) {
    return loadProductFromDatabase(sku);
}
```

The snippet above only illustrates a method in a service configured with caching; `loadProductFromDatabase` is business logic provided by the application. Calling `getProduct("A01")` generates a key from the argument `"A01"`. If called again with the same key in the same cache while the entry is still valid, Spring can return the result without executing the method body.

When the annotation does not declare a custom `key` or `keyGenerator`, Spring defaults to using `org.springframework.cache.interceptor.SimpleKeyGenerator`. This lesson focuses on **exactly which key is generated when there are 0, 1, or multiple arguments**, the important exceptions, and how to verify them.

## 2. The Default Algorithm of SimpleKeyGenerator

`SimpleKeyGenerator` determines the key based on the **list of argument values at invocation time**, without automatically adding the method name, class, bean name, or cache name to the key. The cache name is already used separately to locate the storage region; if two methods use the **same region** with the **same key**, they can collide.

| Passed arguments | Default key | Notes |
| --- | --- | --- |
| No arguments | `SimpleKey.EMPTY` | A constant representing an empty argument list. |
| One argument **not null, not an array** | That object itself | For example `"A01"` or `Integer.valueOf(7)`; no `SimpleKey` is created. |
| One argument equal to `null` | `new SimpleKey((Object) null)` semantically | The result is still a non-`null` key object. |
| One argument that is an **array** | A `SimpleKey` containing the array | Including `int[]`, `String[]`; handles deep element comparison. |
| Two or more arguments | A `SimpleKey` containing all arguments in order | For example `("VN", 7)` differs from `(7, "VN")`. |

An equivalent way to read the algorithm:

1. If the number of elements is 0, return `SimpleKey.EMPTY`.
2. If there is exactly 1 element, return that element **directly only when** it is non-`null` and not an array.
3. In all remaining cases, create a `SimpleKey` from the argument list.

Notably, some summaries only state "one argument → returns the argument itself". This description misses two practical exceptions in the modern implementation: **`null` and arrays**. For a single `null` argument, wrapping it in `SimpleKey` avoids using null directly as a cache key; for arrays, wrapping enables element content comparison.

Standalone example of key types:

```java
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;

Object noArgs = SimpleKeyGenerator.generateKey();
Object one = SimpleKeyGenerator.generateKey("A01");
Object two = SimpleKeyGenerator.generateKey("VN", 7);
Object nullable = SimpleKeyGenerator.generateKey((Object) null);
Object array = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});

System.out.println(noArgs == SimpleKey.EMPTY);       // true
System.out.println(one.equals("A01"));              // true
System.out.println(two instanceof SimpleKey);       // true
System.out.println(nullable instanceof SimpleKey);  // true
System.out.println(array instanceof SimpleKey);     // true
```

This is an **illustrative snippet inside a Java method**, not a standalone file; Section 4 has a complete runnable program. Use the `(Object)` cast when passing a reference array to a Java `Object...` call if you need to clearly represent **a single array argument**, preventing Java from automatically expanding an `Object[]` into multiple varargs parameters in the test call.

### 2.1. Zero Arguments

```java
@Cacheable("siteConfig")
public String currentConfig() { /* ... */ return "config"; }
```

Every call to this zero-argument method, when using the default generator, will have the key `SimpleKey.EMPTY`. Therefore, caching on a zero-argument method can usually achieve a good hit rate. However, if two **zero-argument** methods point to the same cache named `siteConfig` and use the default generator, they share the **same key**, even if the methods or return types differ.

The solution is to separate cache names by purpose, or intentionally create distinct keys, for example `key = "'currentConfig'"` on an operation.

### 2.2. A Normal Single Argument

```java
@Cacheable("userProfiles")
public Profile getProfile(String userId) { /* ... */ return null; }
```

With `getProfile("u1")`, the key is the String `"u1"`. There is no extra `SimpleKey` wrapper. Two different String instances with the same content are still equivalent according to `String.equals()` and `String.hashCode()`, so a typical Map-based cache can hit.

With an immutable record or custom object argument, the key is **that object**. Thus, the object's class must implement `equals()/hashCode()` consistently with its business identity; if it still uses default identity comparison, two instances representing the same data may produce two different keys.

### 2.3. Multiple Arguments

```java
@Cacheable("prices")
public String price(String region, long productId) {
    /* ... */
    return "";
}
```

`price("VN", 42)` creates a `SimpleKey` consisting of two elements `["VN", 42L]`. `price("US", 42)` creates a different key; swapping the argument order also changes the key. `SimpleKey` uses a comparison and hashing mechanism based on **all elements in exact order**, rather than combining parameters into a single hash number and treating two identical hashes as identical keys.

For this reason, the multi-parameter default configuration is usually good enough when all parameters are stable and have proper `equals()/hashCode()`. If a parameter does not affect the result and is only for logging/tracing, the default generator still includes it in the key and can create unnecessary entries.

## 3. Easily Misunderstood Cases

### 3.1. A Single Null Argument Is Not a Null Key

`SimpleKeyGenerator.generateKey((Object) null)` creates a `SimpleKey` containing a single null element. It is **different** from `SimpleKey.EMPTY`, and does not return null directly. However, some custom expressions such as `key = "#p0"` can evaluate to null and are not accepted by the provider/cache abstraction. You need to distinguish between the **default key** and a **custom SpEL key**.

### 3.2. A Single Array Argument Is Wrapped in SimpleKey

Two `new int[] {1, 2}` arrays are two separate objects and are usually not equal under an array's `Object.equals()`. Because `SimpleKey` supports deep comparison, two calls with newly created arrays containing the same elements can use the same cache entry:

```java
Object k1 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
Object k2 = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
System.out.println(k1.equals(k2)); // true
```

With `String[]`, for Java to treat an **array as a single argument to the generator** in a direct call example, a cast is needed:

```java
Object key = SimpleKeyGenerator.generateKey(
        (Object) new String[] {"red", "blue"});
```

In a real Spring AOP call to a service, Spring takes the parameter array already provided by reflection/AOP; you do not have to cast on every business method call. Note that `SimpleKey` does not make nested objects inside the array immutable: mutating the array content after caching can alter the key's meaning, `equals()`, or `hashCode()`, causing lookup errors. Prefer immutable inputs.

### 3.3. Collections Are Not Automatically Normalized into SimpleKey

A non-null `List<String>` argument that is not an array will normally be used **directly** as the key, because `SimpleKeyGenerator` only checks `param.getClass().isArray()` for the type exception. Standard Java Lists compare by element, but a mutable List still carries the risk of an unstable key. Do not assume "any container will always be wrapped by Spring".

### 3.4. Varargs on a Cached Method

The method `find(String... tags)` receives a single Java argument of type `String[]` after compilation. When only this varargs parameter exists, Spring handles the array by default as **a single array argument**, creating a `SimpleKey` to preserve content comparison. If the method has other parameters as well, the key normally contains the parameters in order, where the varargs array is one element of the compound key. Do not assume the strings in varargs are treated as independent parameters by `KeyGenerator`.

## 4. Complete Program: Directly Observing Cache Hits and Misses

This example uses **Java 17+** with Spring Cache, `ConcurrentMapCacheManager` (an in-process memory cache), and the default `SimpleKeyGenerator`. We use four separate cache names to avoid collisions between methods in the demo. Neither `key` nor `keyGenerator` is declared on the annotations, so Spring automatically applies the algorithm above.

Create the structure:

```text
simple-key-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/keys/SimpleKeyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'simple-key-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.keys.SimpleKeyDemo'
}
```

`src/main/java/demo/keys/SimpleKeyDemo.java`:

```java
package demo.keys;

import java.util.Arrays;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SimpleKeyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "zero", "single", "multiple", "arrays");
        }

        @Bean
        DemoService demoService() {
            return new DemoService();
        }
    }

    // Spring creates a proxy for this bean thanks to @EnableCaching.
    public static class DemoService {
        private int zeroCount;
        private int singleCount;
        private int multipleCount;
        private int arraysCount;

        @Cacheable("zero")
        public String zero() {
            return "zero#" + ++zeroCount;
        }

        @Cacheable("single")
        public String single(String sku) {
            return "sku=" + sku + "#" + ++singleCount;
        }

        @Cacheable("multiple")
        public String multiple(String region, int page) {
            return region + ":" + page + "#" + ++multipleCount;
        }

        @Cacheable("arrays")
        public String arrays(int[] numbers) {
            return Arrays.toString(numbers) + "#" + ++arraysCount;
        }

        public String counts() {
            return zeroCount + "/" + singleCount + "/"
                    + multipleCount + "/" + arraysCount;
        }
    }

    public static void main(String[] args) {
        // Observe the keys generated by the default generator.
        Object k0 = SimpleKeyGenerator.generateKey();
        Object k1 = SimpleKeyGenerator.generateKey("A");
        Object k2 = SimpleKeyGenerator.generateKey("VN", 2);
        Object kn = SimpleKeyGenerator.generateKey((Object) null);
        Object ka = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});
        Object kb = SimpleKeyGenerator.generateKey((Object) new int[] {1, 2});

        System.out.println("empty=" + (k0 == SimpleKey.EMPTY));
        System.out.println("one=" + "A".equals(k1));
        System.out.println("multiple=" + (k2 instanceof SimpleKey));
        System.out.println("null=" + (kn instanceof SimpleKey));
        System.out.println("array=" + (ka instanceof SimpleKey));
        System.out.println("deepArrayEqual=" + ka.equals(kb));

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            DemoService service = context.getBean(DemoService.class);

            System.out.println(service.zero());
            System.out.println(service.zero());

            System.out.println(service.single("A"));
            System.out.println(service.single("A"));
            System.out.println(service.single("B"));

            System.out.println(service.multiple("VN", 2));
            System.out.println(service.multiple("VN", 2));
            System.out.println(service.multiple("US", 2));

            System.out.println(service.arrays(new int[] {1, 2}));
            System.out.println(service.arrays(new int[] {1, 2}));
            System.out.println(service.arrays(new int[] {2, 1}));

            System.out.println("executions=" + service.counts());
        }
    }
}
```

Inside the `simple-key-demo` directory, run `gradle run --quiet` with a Gradle version compatible with Java 17, or `./gradlew run --quiet` if the project already has a Gradle Wrapper (Windows PowerShell: `.\gradlew.bat run --quiet`).

The lines produced by `System.out.println` in order (logs from the framework/build tool, if any, are excluded here):

```text
empty=true
one=true
multiple=true
null=true
array=true
deepArrayEqual=true
zero#1
zero#1
sku=A#1
sku=A#1
sku=B#2
VN:2#1
VN:2#1
US:2#2
[1, 2]#1
[1, 2]#1
[2, 1]#2
executions=1/2/2/2
```

**Interpretation by method execution counts:**
- `zero()` has no arguments: the key is always `SimpleKey.EMPTY`, so calling it twice runs the body only once.
- `single("A")` uses the String `"A"` as the key. The second call hits; switching to `"B"` misses, so count = 2.
- `multiple("VN", 2)` uses a compound `SimpleKey`. Calling the same pair again hits; changing region to `"US"` misses, so count = 2.
- `arrays(new int[] {1, 2})` is called twice with two different array objects that have identical elements. `SimpleKey` compares contents so the second call hits; reversing the elements to `{2, 1}` misses, so count = 2.

Note that `getBean(DemoService.class)` retrieves the **bean from the Spring context**, rather than using `new DemoService()`. Calling the object directly without going through the cache proxy will not execute the annotations and you will not observe hits/misses as shown above.

## 5. When Is the Default Key a Good Choice?

Use `SimpleKeyGenerator` when the parameters are naturally suited to serve as the identifier of the cached result, specifically:

- Zero parameters: the method returns the same type of global data within a specific cache region and has a clear invalidation policy.
- One argument: the value has stable `equals()`/`hashCode()`, such as String, UUID, Long, or an immutable record with appropriate components.
- Multiple arguments: all elements participate in determining the result, order is meaningful, and there are no fluctuating useless parameters like a trace ID.
- Array input: default key generation preserves content comparison for arrays, but the input must remain stable for the lifetime of the entry.

Conversely, consider changing the key when:
- Only a subset of parameters affects the data (for example, `locale` and `id` are meaningful, while `traceId` is not).
- Two methods share one cache region, have different output types, yet share the same parameter set.
- An argument is a mutable entity, a mutable collection, or an object without proper `equals()`/`hashCode()` implementation.
- Partitioning by tenant or security is required: the cache and key choice must fully cover the data scope.
- The cache provider requires a specific key format (such as a String with a prefix/namespace), or requires compatible serialization when using a distributed cache.

## 6. Collisions Between Methods Sharing the Same Cache

Consider two methods in a service:

```java
@Cacheable("catalog")
public Product findBySku(String sku) { /* ... */ return null; }

@Cacheable("catalog")
public Product findByBarcode(String barcode) { /* ... */ return null; }
```

If both are called with the string `"123"`, the default key **is the String "123" in both cases**. The generator does not include the method name; therefore, the result from the first method can be retrieved by the second method from the same cache even though the parameter meanings differ.

This is an **illustrative snippet placed in a service that already has the `Product` type and real business logic**, not standalone code. There are three common ways to handle this:

1. Use different cache names, such as `productsBySku` and `productsByBarcode`, which fits when each key group has its own TTL/eviction policy.
2. Namespace the key by method, for example `@Cacheable(cacheNames = "catalog", key = "'sku:' + #p0")` and `key = "'barcode:' + #p0"`.
3. Use a custom `KeyGenerator` if many methods share a complex common rule requiring the method name, argument types, tenant, and/or data version.

Do not rely on different hash codes to protect logic: key equality is the distinguishing relation that must be correct.

## 7. Customizing the Key via Annotations

If you want to ignore parameters that do not affect the result:

```java
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product getProduct(String tenantId, String productId, String traceId) {
    // traceId is only for logging and does not change product data.
    return repository.load(tenantId, productId);
}
```

This is an **illustrative code snippet inside a service** with valid `Product`/`repository`, not a standalone program. Here SpEL `#p0` and `#p1` take the first two parameters, while `traceId` does not participate in the cache key. Ensure string concatenation is unambiguous if values may contain `:`; you can use an immutable key object or a clearer key structure.

If using a custom generator across multiple methods:

```java
@Configuration(proxyBeanMethods = false)
class CacheKeyConfig {
    @Bean("businessKeyGenerator")
    KeyGenerator businessKeyGenerator() {
        return (target, method, params) -> {
            // Illustrative code only: distinguishes the method and
            // preserves the parameter list using SimpleKey.
            Object[] keyParts = new Object[params.length + 1];
            keyParts[0] = method.getName();
            System.arraycopy(params, 0, keyParts, 1, params.length);
            return new SimpleKey(keyParts);
        };
    }
}
```

You need to add imports for `KeyGenerator`, `SimpleKey`, `@Bean`, and `@Configuration`. With overloaded methods or multiple classes sharing one cache, `method.getName()` alone may not be enough: consider adding the class and parameter types or a business namespace. To enable it on an operation:

```java
@Cacheable(cacheNames = "catalog", keyGenerator = "businessKeyGenerator")
public Product load(String tenantId, long id) { /* ... */ return null; }
```

**Do not declare both `key` and `keyGenerator` on the same cache operation**: these two ways of selecting a key are mutually exclusive. You can set a global default generator via `CachingConfigurer` (and control the corresponding `ApplicationContext` scope) if multiple methods need that same rule.

## 8. Synchronizing Reads, Writes, and Evictions

Suppose `@Cacheable` uses the default key `SimpleKey("VN", 42)` while `@CacheEvict` only uses `key="#p1"`; the eviction will target the key `42`, so the compound-key entry **will not be evicted**. This causes stale data even though the business logic has updated the database.

Keep the **cache name/cache resolver** and **key generation rule** consistent across related annotations:

```java
@Cacheable("prices")
public Price getPrice(String region, long productId) { /* ... */ return null; }

@CacheEvict(cacheNames = "prices")
public void invalidatePrice(String region, long productId) { /* ... */ }
```

This snippet illustrates when both methods receive the exact same two parameters in the same order; by default both produce `SimpleKey(region, productId)`. If the eviction method receives inputs with a different structure, specify SpEL or a `KeyGenerator` so they match accurately. With `allEntries=true`, clearing the entire cache does not use a specific key, making it a different policy case.

## 9. Common Errors and How to Diagnose Them

| Symptom | What to check | How to fix |
| --- | --- | --- |
| No arguments but returns the wrong result from another method | Two methods share the same cache and `SimpleKey.EMPTY` | Separate cache names or use namespaced keys. |
| Single `String[]` argument with confusing results | Calling the varargs API directly in a test expands the array into multiple parameters | Cast `(Object)` when calling `generateKey` to simulate a single array argument. |
| Same object data yet always misses | `equals/hashCode` uses identity comparison or parameters include trace/timestamp | Fix with an immutable identifier or use SpEL/custom key. |
| Array input later misses unexpectedly | Code mutated the array or nested content, making the key unstable | Copy into an immutable input before caching. |
| Eviction has no effect | `@CacheEvict` uses a different key than `@Cacheable` | Unify cache name and key, including parameter types and order. |
| Cache hits across two different methods | Default key does not include method or class | Use different caches or namespaced keys. |
| Never hits even with the right key | Call bypasses the Spring proxy; `@EnableCaching` is missing or in the wrong context | Check Spring-managed beans, self-invocation, and caching configuration. |
| Key is right but hit/miss differs from expectations | Provider TTL, eviction, serialization, or multi-instance backend | Check provider config, eviction timing, and telemetry. |

When debugging, inspect **three independent components**: which cache is selected, what the actual key is, and whether the call goes through the cache proxy. Do not equate having a `CacheManager` bean with caching annotations actually being enabled.

## 10. Self-Check Exercises

1. The method `@Cacheable("x") String status()` takes no parameters. After calling it once, what is the expected key? — **`SimpleKey.EMPTY`**.
2. The method `get(int id)` with `id=7` uses the default generator. What is the key? — **Integer 7** due to boxing, not `SimpleKey(7)`.
3. The method `get(String tenant, int id)` is called with `("VN", 7)`. What is the key? — **`SimpleKey("VN", 7)`** in the order of the two parameters.
4. A method receiving exactly **one** `int[]` is called sequentially with `new int[]{1,2}` and a new array with the same elements. Are the keys equivalent? — **Yes**, as long as the content is stable and the same default key rule applies.
5. The method `lookup(UserKey key)` creates two different instances with the same ID; `UserKey` does not override `equals/hashCode`. Is a hit guaranteed? — **No**; a single object argument is used directly and defaults to identity comparison.
6. Two different methods share cache `x` and both receive String `"A"`. Do the keys differ because of the method names? — **No**; the method name is not included in the default `SimpleKeyGenerator`.
7. When `@CacheEvict` uses only `productId`, while `@Cacheable` uses the pair `(tenantId, productId)`, does eviction hit the right key? — **No**, unless customized so both annotations use the same key structure.

## 11. Key Takeaways

- **0 parameters:** `SimpleKey.EMPTY`.
- **1 normal parameter:** the object itself; **1 null or 1 array:** wrapped in `SimpleKey`.
- **2+ parameters:** `SimpleKey` containing all arguments in exact order.
- The default generator **does not include the method or class name**; choose cache names and key namespaces carefully.
- A key with stable `equals/hashCode` and consistent rules across `@Cacheable`, `@CachePut`, and `@CacheEvict` ensures the cache works correctly.

### References

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework – SimpleKeyGenerator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html)
- [Spring Framework – SimpleKey API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
