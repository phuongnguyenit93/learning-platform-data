# Why Is the Method Name Not Automatically Included in Spring Cache's Default Key?

## Objectives

This lesson explains how Spring Cache builds default keys from parameters, why the method name is not automatically part of the key, the consequences when different methods share a cache region and the same key, and safe key design patterns. After this lesson, you will be able to run a Java 17 example yourself, spot wrong results caused by unintended cache hits, and fix them using `cacheNames`, SpEL `key`, or `KeyGenerator`.

## 1. Direct Answer

When using `@Cacheable` without specifying `key` or `keyGenerator`, Spring normally uses `SimpleKeyGenerator`. The algorithm **relies on the actual arguments of the invocation**. By default, it does not add the method name, class name, bean name, or return type to the key.

Example:

~~~java
@Cacheable(cacheNames = "shared")
public String findUserName(String id) {
    return "USER:" + id;
}

@Cacheable(cacheNames = "shared")
public String findProductName(String id) {
    return "PRODUCT:" + id;
}
~~~

This is an illustrative snippet, not a standalone program. The two calls `findUserName("42")` and `findProductName("42")` generate the same key `"42"`. If both use the same `"shared"` cache, they look up **the same entry**, regardless of having different method names:

~~~text
findUserName("42")       findProductName("42")
        |                         |
        +------------+------------+
                     |
          Cache name = "shared"
          Default key = "42"
                     |
                     v
             Cache("shared").get("42")
~~~

When `findUserName("42")` runs first, it can store `"USER:42"`. Afterward, `findProductName("42")` hits the cache and immediately returns `"USER:42"`; the second method's body **does not run**. This is a data corruption risk caused by two different operations sharing one logical cache address.

Three concepts must be distinguished:

- **Cache name (`cacheNames`)**: identifies the cache region, such as `"shared"`, `"users"`, or `"products"`.
- **Cache key**: identifies the entry inside that region, such as the string `"42"`.
- **Method name**: the Java method name. A custom generator can use it, but it is **not automatically a component of the default key**.

You can think of an entry's logical address as the pair **(resolved cache region, key)**. The method name does not automatically create a new storage region.

## 2. How Does the Default SimpleKeyGenerator Work?

`org.springframework.cache.interceptor.SimpleKeyGenerator` generates keys according to the number and values of parameters:

| Call parameters | Default key | Example |
| --- | --- | --- |
| No parameters | `SimpleKey.EMPTY` | `getConfig()` |
| One non-null, non-array parameter | The parameter object itself | `find("42")` → `"42"` |
| Two or more parameters | `SimpleKey` containing all parameters in order | `find("42", "vi")` |
| One null parameter or an array | `SimpleKey` wrapping the parameter list | Requires attention to edge cases |

Tutorials often simplify this into 0/1/multiple parameters; the Javadoc and implementation contain the details for a single null or array parameter. When the exact generated key matters, check the actual version you are running.

You can call the static API as follows:

~~~java
Object key0 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey();
Object key1 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey("42");
Object key2 = org.springframework.cache.interceptor
        .SimpleKeyGenerator.generateKey("42", "vi");
~~~

This is a snippet using the Spring API: `key0` is `SimpleKey.EMPTY`; `key1` is the string `"42"`; `key2` is a `SimpleKey` with two elements. No method name needs to be passed for these three key generations.

Same parameter types with different values normally produce different keys. Conversely, **two different methods with the same parameter values** can still produce equal keys.

### Why Does KeyGenerator Receive Method Yet Not Automatically Use the Method Name?

The extension interface:

~~~java
public interface KeyGenerator {
    Object generate(Object target,
                    java.lang.reflect.Method method,
                    Object... params);
}
~~~

The snippet above shows the actual interface signature for explanation, not something you need to redeclare in your application.

Spring passes both `target` and `method` so implementations **have the ability** to build custom keys. However, the default `SimpleKeyGenerator` chooses to compute keys from `params`. Therefore, **Spring knowing the running method** and **the method name being included in the key** are two separate things.

This is not a framework bug. Key generation is a customizable application policy, while `cacheNames` already helps organize storage spaces. When one cache region holds multiple distinct kinds of results, developers must explicitly define an appropriate entry identity.

## 3. Why Is Parameter-Based Key Design Still Useful?

Suppose there are two separate cache regions:

~~~java
@Cacheable(cacheNames = "users")
public User findUser(String userId) {
    return userRepository.find(userId);
}

@Cacheable(cacheNames = "products")
public Product findProduct(String productId) {
    return productRepository.find(productId);
}
~~~

This is an illustrative snippet requiring `User`, `Product`, and repositories to be defined. Both methods can use the default key `"42"` without colliding on entries, because `users` and `products` are two distinct cache regions at the abstraction level.

Parameter-based key rules have several consequences:

1. Business IDs are often natural, easy-to-follow keys: the same `userId` reads the same entry in the `users` cache.
2. Cache scope is decided explicitly by cache name or resolver, not implicitly by Java method name.
3. Refactoring to rename a method while keeping the same semantics does not automatically alter the default key based on the Java name. However, if you change the representation or meaning of the result, a versioning/invalidation strategy is still needed.
4. Methods with equivalent results **can** intentionally share entries if they genuinely align on data and freshness policies.

Worth remembering: `SimpleKeyGenerator` prevents collisions caused by how parameter combinations are represented within its algorithm; this does **not** mean it creates a separate namespace per method. When two operations intentionally or accidentally pick the same cache region and the same key, they share the same logical address. This is a key collision, not simply "two equal hash codes".

## 4. Cache Returning Wrong Data Because the Method Name Is Not in the Key

Suppose the `shared` cache is initially empty and both methods return `String`:

~~~text
1. Call findUserName("42")
   - Default key: "42"
   - Cache("shared").get("42") -> MISS
   - Method runs, returns "USER:42"
   - Cache.put("42", "USER:42")

2. Call findProductName("42")
   - Default key: "42"
   - Cache("shared").get("42") -> HIT
   - Returns "USER:42" directly
   - Method findProductName DOES NOT run
~~~

Spring behaves strictly according to `@Cacheable`: on a hit, the method body is skipped. The bug is that two methods with **different** result meanings share one entry.

If one method returns `User` and another returns `Product`, sharing an entry also risks type-casting errors. If the output depends on `tenantId`, language, or access permissions and the key omits that information, reusing the wrong entry can leak data across different contexts.

Collisions are not limited to a single class. Two different Spring beans sharing the same `CacheManager`, same cache name, and generating equivalent keys can also read each other's entries.

A special case: two zero-argument methods both annotated with `@Cacheable("settings")` both generate `SimpleKey.EMPTY`. Different names still do not separate them automatically.

## 5. Runnable Java 17 Example: Proving It with a Program

The example below uses Java 17, Maven, Spring Framework 6.2.10, and `ConcurrentMapCacheManager`. This is an in-JVM RAM cache, so no database or Redis is needed. The first two methods are intentionally misconfigured to show the collision; the next two use prefixes to fix it.

Directory structure:

~~~text
method-key-demo/
├── pom.xml
└── src/main/java/demo/MethodKeyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>method-key-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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

File `src/main/java/demo/MethodKeyDemo.java`:

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.SimpleKeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MethodKeyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("shared");
        }

        @Bean
        public NameService nameService() {
            return new NameService();
        }
    }

    public static class NameService {

        // Two different methods sharing the same cache name and default key.
        @Cacheable(cacheNames = "shared")
        public String userName(String id) {
            System.out.println("RUN userName(" + id + ")");
            return "USER(" + id + ")";
        }

        @Cacheable(cacheNames = "shared")
        public String productName(String id) {
            System.out.println("RUN productName(" + id + ")");
            return "PRODUCT(" + id + ")";
        }

        // These two methods intentionally create two different key namespaces.
        @Cacheable(cacheNames = "shared", key = "'user:' + #p0")
        public String userNamePrefixed(String id) {
            System.out.println("RUN userNamePrefixed(" + id + ")");
            return "USER(" + id + ")";
        }

        @Cacheable(cacheNames = "shared", key = "'product:' + #p0")
        public String productNamePrefixed(String id) {
            System.out.println("RUN productNamePrefixed(" + id + ")");
            return "PRODUCT(" + id + ")";
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            NameService service = context.getBean(NameService.class);
            Cache cache = Objects.requireNonNull(
                context.getBean(CacheManager.class).getCache("shared"));

            System.out.println("Default key = "
                    + SimpleKeyGenerator.generateKey("42"));

            System.out.println("User = " + service.userName("42"));
            System.out.println("Product = " + service.productName("42"));
            System.out.println("Cache[42] = "
                    + cache.get("42", String.class));

            System.out.println("Prefixed user = "
                    + service.userNamePrefixed("42"));
            System.out.println("Prefixed product = "
                    + service.productNamePrefixed("42"));

            System.out.println("Both prefixed keys exist = "
                    + (cache.get("user:42") != null
                    && cache.get("product:42") != null));
        }
    }
}
~~~

Run in the directory containing `pom.xml` (requires JDK 17 or higher and Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MethodKeyDemo
~~~

Lines printed by the program itself:

~~~text
Default key = 42
RUN userName(42)
User = USER(42)
Product = USER(42)
Cache[42] = USER(42)
RUN userNamePrefixed(42)
Prefixed user = USER(42)
RUN productNamePrefixed(42)
Prefixed product = PRODUCT(42)
Both prefixed keys exist = true
~~~

**The critical line is `Product = USER(42)`.** There is no `RUN productName(42)` line because the second call hits key `"42"` stored by the first method. Meanwhile, the two prefixed methods create keys `"user:42"` and `"product:42"`, so each method runs and stores its own result.

Note that the example calls `context.getBean(NameService.class)` to go through the Spring proxy; if you instantiate the object manually with `new NameService()` outside the container or via self-invocation `this.productName(...)` in proxy mode, the annotation may not be applied. Then the test output will differ and no longer demonstrate real cache behavior.

## 6. First Fix: Separate Cache Names by Data Type

~~~java
@Cacheable(cacheNames = "users")
public User findUser(String userId) {
    return userRepository.find(userId);
}

@Cacheable(cacheNames = "products")
public Product findProduct(String productId) {
    return productRepository.find(productId);
}
~~~

This is an illustrative snippet requiring types/repositories to be defined to compile. The `users` and `products` caches are two separate logical regions; the same default key `"42"` does not point to the same entry. This approach usually fits when data has different TTLs, size limits, or invalidation policies.

Important: merely assigning separate cache names is sufficient at the abstraction level only when `CacheManager` actually creates/resolves separate caches. If a provider configuration maps namespaces improperly, fix it at the provider layer as well.

## 7. Second Fix: Keep the Same Cache but Add a Key Prefix

~~~java
@Cacheable(cacheNames = "lookup", key = "'user:' + #p0")
public String findUserName(String id) {
    return userRepository.findName(id);
}

@Cacheable(cacheNames = "lookup", key = "'product:' + #p0")
public String findProductName(String id) {
    return productRepository.findName(id);
}
~~~

This snippet requires real repositories. `#p0` is the first parameter, avoiding reliance on compiler flags retaining parameter names. The keys are `"user:42"` and `"product:42"`. This is a simple approach when the application **intentionally shares a cache** while results need separate namespaces.

Do not merely add a method prefix and ignore factors that actually change the result. For example, if the result depends on tenant, locale, or version, the key must include those factors. Naive string concatenation risks scenarios where different inputs produce the same string when they contain delimiters; multi-tenant applications also need to avoid exposing sensitive data in keys/logs.

For a cache with multiple operations, establish a consistent convention across `@Cacheable`, `@CachePut`, and `@CacheEvict` so reads, writes, and evictions target **the same logical address**. If you update the key on the read method without updating eviction, stale data can persist unexpectedly.

## 8. Third Fix: Write a Custom Method-Aware KeyGenerator

The `KeyGenerator` interface has a `Method` parameter, so we can explicitly include the method in the key:

~~~java
@Bean("methodAwareKeyGenerator")
public org.springframework.cache.interceptor.KeyGenerator
methodAwareKeyGenerator() {
    return (target, method, params) ->
        new org.springframework.cache.interceptor.SimpleKey(
            method.getDeclaringClass().getName(),
            method.getName(),
            new org.springframework.cache.interceptor.SimpleKey(params)
        );
}
~~~

This is a configuration snippet placed inside a Spring `@Configuration`, not a standalone program. The key is constructed from the declaring class, method name, and parameter combination. When two methods have different names, the keys differ even if `params` are identical.

Usage:

~~~java
@Cacheable(
    cacheNames = "lookup",
    keyGenerator = "methodAwareKeyGenerator"
)
public String findUserName(String id) {
    return userRepository.findName(id);
}
~~~

Do not specify `key` and `keyGenerator` simultaneously on the same operation; Spring treats them as mutually exclusive ways to specify a key.

### Trade-offs of a Method-Aware Key

- Renaming or moving a method to another class changes the key; old entries may stop hitting and require TTL/clearing/migration.
- `method.getName()` alone does not guarantee distinguishing **overloads** with the same name. If needed, the generator must also inspect the signature or declared parameter types.
- Some operations may intentionally share results; automatically adding the method name removes that sharing benefit.
- `SimpleKey` is convenient for `ConcurrentMapCache`, but with Redis or other providers you must verify the serializer/key conversion.
- `@CacheEvict` and `@CachePut` must use a matching key rule; otherwise written entries will not be evicted/updated as intended.

Therefore, do not configure a method-aware generator globally just to fix a pair of methods placed in an overly broad shared cache name. Separating cache names or creating explicit key namespaces is usually easier to reason about.

## 9. Edge Cases Easily Overlooked

### Methods with No Parameters

~~~java
@Cacheable(cacheNames = "settings")
public String countryCode() { return "VN"; }

@Cacheable(cacheNames = "settings")
public String currencyCode() { return "VND"; }
~~~

Both use `SimpleKey.EMPTY` by default. If sharing the `settings` cache, calling `countryCode()` first can cause `currencyCode()` to receive `"VN"` from the cache, even though the correct result is `"VND"`. You can separate cache names or set `key = "'countryCode'"` and `key = "'currencyCode'"`.

### Overloads and Return Types

The default key does not automatically include the method name, declared parameter types, or return type. You cannot rely on one method returning `User` and another returning `Product` to assume the cache will isolate them automatically. If a wrongly typed entry is reused, a cast exception may occur; if both return `String`, the bug is even easier to hide because the returned value is still valid for the Java type.

### Bean Classes Do Not Automatically Create Namespaces

Two Spring services in different packages using the same cache name, same key, and same manager still risk sharing entries. The bean/class name is not automatically added to the default key.

### equals/hashCode and Mutable Parameters

The default key relies on parameter values/objects, so `equals` and `hashCode` must be stable and semantically accurate. Using a mutable object as a key and then mutating it after insertion into a hash map can make lookups erratic. Out-of-JVM providers may also convert/serialize the key.

### Data Versions and Logic Changes

Even a single method can encounter outdated entries after an application upgrade. Renaming a method does not automatically change the default key; changing result semantics/formats requires a versioning, TTL, invalidation, or migration plan to avoid reusing old data.

### Different Providers

The Spring Cache abstraction does not stipulate that the same key object is represented identically by Redis/Caffeine/ConcurrentMap. When debugging, inspect **the logical cache name, generated key, and physical/serialized key** of the provider together. Redis's cache name prefix mechanism does not mean Spring added the method name to `SimpleKeyGenerator`.

## 10. Checklist for Auditing Collision Risks in a Project

1. Find methods using the same `cacheNames` or the same cache resolved by `CacheResolver`; check `@Cacheable`, `@CachePut`, and `@CacheEvict`.
2. Identify the active key strategy: default, SpEL `key`, method-level `keyGenerator`, or a customized global default generator.
3. Take two real invocations with equal parameters or potential to produce equal keys, and compute the keys under the selected algorithm.
4. Compare **the meaning of the results**: if two methods return different data yet use the same cache/key, fix the namespace.
5. Test through the Spring bean proxy, not just by calling a `new` object or self-invocation. Monitor body logs and inspect `CacheManager.getCache(name).get(key)` when needed.
6. Choose a fix: separate cache names, explicit key prefixes, or a custom generator with complete identity.
7. Re-check update and eviction paths, TTL, old entries, and distributed providers. Do not fix only the read annotation.
8. Write a test proving two different methods **do not accidentally read each other's entries** when given identical inputs.

## 11. Self-Check Questions

**1.** Two methods `a(String id)` and `b(String id)` share `@Cacheable("shared")` and are both called with `"7"`. Do their default keys differ because of the method names?

**Answer:** No. Both normally produce the key `"7"`. If they resolve to the same `shared` region, they can share the entry.

**2.** Why does `KeyGenerator.generate(...)` have a `Method` parameter yet the method name is not automatically in the default key?

**Answer:** The interface provides `Method` so custom generators can use it. The default `SimpleKeyGenerator` computes the key solely from `params`.

**3.** Do two zero-parameter methods annotated with `@Cacheable("settings")` have the same default key?

**Answer:** Yes, both use `SimpleKey.EMPTY`. If their results differ, separate the cache names or use explicit keys.

**4.** Do two methods in two different cache names both using key `"7"` collide?

**Answer:** No, if the two names resolve to two independent cache regions. A key only identifies an entry within the selected cache region.

**5.** Does simply adding the method name to the key solve every problem?

**Answer:** No. You must still distinguish overloads, class/context, parameters affecting the output, serialization, and align rules across `@Cacheable`/`@CachePut`/`@CacheEvict`.

## Key Takeaways

**By default, `SimpleKeyGenerator` derives keys from parameters, not from the method name.** Two differently named methods can still collide on an entry if they use the same cache name and the same key. Safe cache design requires explicitly defining **data identity, cache region, key generation, and invalidation**, rather than relying on Java method names to isolate namespaces automatically.

## Official Documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching (default key): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — SimpleKeyGenerator: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Framework 6.2 — KeyGenerator: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
