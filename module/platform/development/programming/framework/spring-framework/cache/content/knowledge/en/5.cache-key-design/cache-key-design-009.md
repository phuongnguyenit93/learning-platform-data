# Writing a Shared KeyGenerator and Registering It as a Bean in Spring Cache

## Learning Objectives

After this lesson, you will be able to:

- Understand the role of \`KeyGenerator\` in Spring Cache and when to write a shared key generator.
- Implement \`generate(Object target, Method method, Object... params)\` to produce keys matching business semantics.
- Register a \`KeyGenerator\` as a Spring bean, reference it with \`@Cacheable(keyGenerator = "...")\`, share it via \`@CacheConfig\`, and understand application-wide default configuration.
- Design the same key rule for reads, updates, and evictions; avoid collisions, tenant leaks, unstable keys, and serialization errors.
- Run a Java 17 example to observe cache hits, tenant isolation, two cache regions, and \`@CacheEvict\` reusing the exact same key.

## 1. Where Does KeyGenerator Fit in Spring Cache?

Spring Cache manages method result caching operations by the pair **cache name + cache key**. When an invocation goes through the Spring caching proxy, the framework resolves the target cache, generates the key, and looks up the entry. With \`@Cacheable\`, a cache hit can return the result without running the method body. On a cache miss, the method is executed and the result can be stored.

\`org.springframework.cache.interceptor.KeyGenerator\` is an interface that lets you **turn the context of a Java method call into a key object**. It is the extension point when default key selection does not accurately express the identity of the cached data.

Basic flow:

~~~text
Call method via Spring proxy
            |
   resolve cacheNames
            |
     KeyGenerator.generate(...)
            |
     generate key for call
            |
    Cache.get(key) / Cache.put(key, result)
~~~

For example, suppose an application has the method:

~~~java
String getTitle(String tenantId, String productId, String traceId);
~~~

If the same \`tenantId\` and \`productId\` always produce the same title, while \`traceId\` is only per-request metadata and **does not affect the value**, including traceId in the default key creates a new entry per request. A shared KeyGenerator can select only \`tenantId\` and \`productId\`.

Note: if traceId **actually affects the data** or a mandatory side effect of the method, you must not arbitrarily exclude it from the caching strategy. Caching is appropriate only when skipping the method body on a hit is safe.

## 2. Comparing Default Key Generation, SpEL, and KeyGenerator

### 2.1. Default: SimpleKeyGenerator

If neither \`key\` nor \`keyGenerator\` is specified, Spring normally uses \`SimpleKeyGenerator\`:

| Method parameters | Default key |
| --- | --- |
| No parameters | \`SimpleKey.EMPTY\` |
| One parameter | That parameter object itself |
| Two or more parameters | \`SimpleKey\` containing all parameters |

This works if **all parameters affect the result** and the key object has stable \`equals()\`/\`hashCode()\`. With \`getTitle(tenantId, productId, traceId)\`, \`traceId\` also goes into the key, even though it is only request-tracing information.

### 2.2. SpEL: Good for One Method with a Simple Rule

~~~java
@Cacheable(
    cacheNames = "productTitles",
    key = "T(org.springframework.cache.interceptor.SimpleKey).class"
)
~~~

The snippet above **is not an example key you should use**: it illustrates that you cannot derive a valid key by taking a fixed constant value, because products will collide. To select two parameters, you can use a SpEL expression or invoke a controlled key builder function. A shorter example with one business parameter:

~~~java
@Cacheable(cacheNames = "productTitles", key = "#p0")
public String titleByProductId(String productId) {
    return repository.findTitle(productId);
}
~~~

This is illustrative code with an external repository. For a few methods, SpEL is often easier to read than creating another Java class. When **many methods need the same algorithm** (rule-based ID normalization, tenant + data code composition, key versioning, parameter type validation), a shared \`KeyGenerator\` is easier to test and avoids duplicating logic.

### 2.3. KeyGenerator: Reusable Algorithm

Example referencing a bean by name:

~~~java
@Cacheable(
    cacheNames = "productTitles",
    keyGenerator = "tenantProductKeyGenerator"
)
public String getTitle(String tenantId, String productId, String traceId) {
    return repository.findTitle(tenantId, productId);
}
~~~

This illustrative code requires a bean named \`tenantProductKeyGenerator\`. **\`key\` and \`keyGenerator\` are mutually exclusive on the same cache operation**: do not put both on the same \`@Cacheable\`, \`@CachePut\`, or \`@CacheEvict\`.

## 3. Contract of the KeyGenerator Interface

The interface has one primary method:

~~~java
public interface KeyGenerator {
    Object generate(Object target, Method method, Object... params);
}
~~~

- **\`target\`**: the target object being invoked. Can be used when a namespace is needed, yet you must not turn instance identity, memory addresses, or random proxy details into a key.
- **\`method\`**: \`java.lang.reflect.Method\` metadata. Use when the algorithm needs to distinguish methods, while considering how read/evict/put operations must use **the same key**.
- **\`params\`**: the passed arguments in Java signature order; primitive parameters are boxed.
- **Return value**: the object representing the key. For local caches, \`equals()\` and \`hashCode()\` are especially important; for distributed caches, a stable serialization format must also be ensured.

KeyGenerator **does not execute data queries** and does not decide TTL, eviction, cache manager, or retention duration. Those belong to other policies and providers.

### 3.1. Criteria for a Good Key

A key should be:

1. **Consistent:** the same data identity produces equal keys across invocations.
2. **Properly distinguishing:** two different business results do not share the same key within one cache name.
3. **Durable:** does not contain mutable objects, temporary request IDs, memory-address-based hashes, or machine-format-dependent strings.
4. **Isolated:** if the result depends on tenant/user/locale/permissions/version, the key and security strategy must reflect those factors.
5. **Read/evict compatible:** an eviction operation meant to delete an entry created by \`@Cacheable\` must generate the exact same key and target the exact same cache name.
6. **Cardinality-controlled:** avoid stuffing timestamps or irrelevant traceIds into keys causing the cache to only miss.

**Do not use \`Objects.hash(tenantId, productId)\` alone as a unique key.** A 32-bit hash can collide for two different data tuples. A \`record\` holding the actual components, or a key type with proper \`equals/hashCode\`, lets components still be compared when hash collisions arise in map structures.

### 3.2. Why Use a record in Java 17?

~~~java
public record ProductKey(String tenantId, String productId) {}
~~~

A \`record\` automatically generates \`equals()\`, \`hashCode()\`, and \`toString()\` from its components; no manual string concatenation with delimiters is needed. For example, concatenating \`tenant + ":" + id\` can collide if \`tenant\` or \`id\` contains \`:\` without clear escaping. With Redis or providers using custom serializers, still verify how the record encodes into an actual key rather than assuming every serializer supports records.

## 4. Java 17 Example: Sharing One KeyGenerator Bean via @CacheConfig

This example uses Spring Framework 6.2.10 and an in-memory cache. Two read methods \`getTitle\` and \`getCategory\` share one key generation algorithm; each method has its own **separate cacheNames** to avoid collisions between the two kinds of data. \`invalidateTitle\` reuses the same KeyGenerator to evict the right entry.

\`traceId\` is passed as metadata; in the demo, it does not affect returned content. Every method applying the generator receives three \`String\` parameters in the order \`(tenantId, productId, traceId)\`. In a real project, consider separating trace context from business signatures when possible.

### 4.1. Project Structure

~~~text
spring-custom-key/
├── pom.xml
└── src/main/java/demo/CacheKeyExample.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-custom-key</artifactId>
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
        <version>3.14.0</version>
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

### 4.3. src/main/java/demo/CacheKeyExample.java

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheKeyExample {

    // An immutable value object as a key for an in-RAM cache.
    public record ProductKey(String tenantId, String productId) {}

    // Contract: (tenantId, productId, traceId), all Strings.
    public static class TenantProductKeyGenerator implements KeyGenerator {
        @Override
        public Object generate(Object target, Method method, Object... params) {
            if (params.length != 3
                    || !(params[0] instanceof String)
                    || !(params[1] instanceof String)
                    || !(params[2] instanceof String)) {
                throw new IllegalArgumentException(
                    "Invalid parameters for " + method.getName());
            }
            String tenantId = (String) params[0];
            String productId = (String) params[1];
            // params[2] is traceId, does NOT affect the business result.
            return new ProductKey(tenantId, productId);
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        // Bean name must match keyGenerator below exactly.
        @Bean("tenantProductKeyGenerator")
        public KeyGenerator tenantProductKeyGenerator() {
            return new TenantProductKeyGenerator();
        }

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "productTitles", "productCategories");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    // A single key policy applied to the class's cache operations.
    @CacheConfig(keyGenerator = "tenantProductKeyGenerator")
    public static class ProductService {
        private final AtomicInteger titleLoads = new AtomicInteger();
        private final AtomicInteger categoryLoads = new AtomicInteger();

        @Cacheable(cacheNames = "productTitles")
        public String getTitle(
                String tenantId, String productId, String traceId) {
            titleLoads.incrementAndGet();
            return "Title@" + tenantId + "/" + productId;
        }

        @Cacheable(cacheNames = "productCategories")
        public String getCategory(
                String tenantId, String productId, String traceId) {
            categoryLoads.incrementAndGet();
            return "Category@" + tenantId + "/" + productId;
        }

        @CacheEvict(cacheNames = "productTitles")
        public void invalidateTitle(
                String tenantId, String productId, String traceId) {
            // Simulate an event where source data has changed.
            // @CacheEvict removes the entry after the method completes successfully.
        }

        public int titleLoadCount() {
            return titleLoads.get();
        }

        public int categoryLoadCount() {
            return categoryLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);
            Cache titles = Objects.requireNonNull(
                context.getBean(CacheManager.class)
                       .getCache("productTitles"));

            System.out.println(service.getTitle("t1", "P-7", "req-1"));
            System.out.println(service.getTitle("t1", "P-7", "req-2"));
            System.out.println("Title loads: " + service.titleLoadCount());

            System.out.println(service.getTitle("t2", "P-7", "req-3"));
            System.out.println("Title loads: " + service.titleLoadCount());

            System.out.println(service.getCategory("t1", "P-7", "req-4"));
            System.out.println(
                "Category loads: " + service.categoryLoadCount());

            service.invalidateTitle("t1", "P-7", "admin");
            System.out.println(
                "Title entry after evict: "
                    + (titles.get(new ProductKey("t1", "P-7")) != null));

            System.out.println(service.getTitle("t1", "P-7", "req-5"));
            System.out.println("Title loads: " + service.titleLoadCount());
        }
    }
}
~~~

### 4.4. Running from the Directory Containing pom.xml

Requires JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyExample
~~~

The lines **printed by the program itself** (excluding Maven logs) are:

~~~text
Title@t1/P-7
Title@t1/P-7
Title loads: 1
Title@t2/P-7
Title loads: 2
Category@t1/P-7
Category loads: 1
Title entry after evict: false
Title@t1/P-7
Title loads: 3
~~~

### 4.5. Why Does the Output Look Like This?

1. \`getTitle("t1", "P-7", "req-1")\` generates key \`ProductKey("t1", "P-7")\`, misses, and executes the method body.
2. \`getTitle("t1", "P-7", "req-2")\` uses **the same key** despite a different traceId, since traceId does not affect the result; cache hits so \`titleLoads\` stays 1.
3. \`getTitle("t2", "P-7", "req-3")\` has a different tenant, so a different key; cache misses, \`titleLoads\` increases to 2.
4. \`getCategory("t1", "P-7", "req-4")\` uses the same key structure yet a **different cache region** (\`productCategories\`), so it does not mistakenly read the title value.
5. \`invalidateTitle("t1", "P-7", "admin")\` inherits the same generator from \`@CacheConfig\`, generates the same key as \`getTitle\`, and \`@CacheEvict\` deletes the right entry from \`productTitles\`.
6. Calling \`getTitle("t1", "P-7", "req-5")\` misses again and hits the source, bringing the title counter to 3.

**Condition for accurate observation:** the call must go through the Spring-managed bean. \`@EnableCaching\` enables Spring to create cache advice, and \`context.getBean(ProductService.class)\` retrieves the proxied bean. Calling \`this.getTitle(...)\` directly inside \`ProductService\` itself (self-invocation in default proxy mode) will bypass the cache interceptor.

**Distinguishing the demo from real systems:** \`ConcurrentMapCacheManager\` stores entries in process RAM, suitable for learning and testing. A multi-instance environment needs shared cache infrastructure, TTL, max-size, eviction, serializers, error handling, and data synchronization policies.

## 5. Three Ways to Register and Use a KeyGenerator

### 5.1. Approach 1: Select Explicitly per Method

Define the bean:

~~~java
@Bean("tenantProductKeyGenerator")
public KeyGenerator tenantProductKeyGenerator() {
    return new TenantProductKeyGenerator();
}
~~~

And select it by name:

~~~java
@Cacheable(
    cacheNames = "productTitles",
    keyGenerator = "tenantProductKeyGenerator"
)
public String getTitle(String tenantId, String productId, String traceId) {
    return repository.findTitle(tenantId, productId);
}
~~~

The snippets in this section are **illustrative code when integrating into a Spring project**, with the generator class and repository already defined. The bean name must match: for example, \`tenantProductKeyGenerator\` **is not the same as** \`tenantProductKeysGenerator\`.

This approach fits when only certain methods follow a special key contract. You can reuse the same bean name across multiple \`@Cacheable\`, \`@CachePut\`, and \`@CacheEvict\` annotations.

### 5.2. Approach 2: Share the Rule Class-Wide with @CacheConfig

~~~java
@CacheConfig(keyGenerator = "tenantProductKeyGenerator")
public class ProductService {

    @Cacheable(cacheNames = "productTitles")
    public String getTitle(String tenantId, String productId,
                           String traceId) {
        // ...
        return "example";
    }

    @CacheEvict(cacheNames = "productTitles")
    public void invalidateTitle(String tenantId, String productId,
                                String traceId) {
        // ...
    }
}
~~~

\`@CacheConfig\` only **shares defaults** among cache operations in the class; it does not automatically make every method in the class cached. Each method needs \`@Cacheable\`, \`@CachePut\`, \`@CacheEvict\`, or an appropriate combination.

A \`keyGenerator\` specified at the **method level** overrides the value in \`@CacheConfig\`. Thus, you can set a default policy on the class and intentionally override it for a method with a different parameter structure.

### 5.3. Approach 3: Set an Application-Wide Default Key Generator

Spring supports \`CachingConfigurer\` when global defaults are needed for the caching infrastructure. This is an **alternative configuration option**; do not simultaneously add the class below to the demo project above:

~~~java
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class GlobalCachingConfig implements CachingConfigurer {

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return new CacheKeyExample.TenantProductKeyGenerator();
    }
}
~~~

In the example, \`CacheKeyExample.TenantProductKeyGenerator\` is the class from the demo program; this configuration snippet is **only appropriate application-wide if every method using that default shares the matching 3-parameter contract**. A global generator used in a real application must handle all signatures it will encounter; otherwise, cache operations outside the product group will throw errors because the generator is too specific.

The actual precedence order for selecting a key generator is:

~~~text
keyGenerator specified directly on the cache operation
                  |
          class-level @CacheConfig
                  |
       default via CachingConfigurer
                  |
          SimpleKeyGenerator
~~~

If you only want one policy for a group of services, \`@CacheConfig\` is usually clearer than changing the application-wide default.

## 6. Common Key Design Mistakes

### 6.1. Omitting a Parameter That Actually Affects the Result

Suppose \`getPrice(productId, currency)\` yields different results for USD and VND; a key using only productId causes values for both currencies to collide in the same cache region. Include currency in the key or separate regions semantically. Only omit a parameter when you can prove it neither affects the result nor carries mandatory side effects.

### 6.2. Missing Tenant, User, or Access Scope

In a multi-tenant system, the same \`productId\` can represent different data. Keys must distinguish tenants when data is tenant-owned, while access control is enforced outside the cache. Never treat a cache hit as an "authorization bypass" if permissions must be checked on every request.

### 6.3. Including Method Name in the Key Without Considering Eviction

A generator can build \`method.getName() + ":" + id\` to separate \`getTitle\` and \`getCategory\` inside the same cache region. However, if \`invalidateTitle\` uses its own method name, the eviction key **does not match** the key created by \`getTitle\`. Sharing a KeyGenerator **does not automatically guarantee** matching keys: you must design the same *cache name + identity key* across read/evict/put.

In the demo, the two read methods use different cache regions so the method name is unnecessary in the key; \`invalidateTitle\` reuses the exact \`ProductKey(tenantId, productId)\`.

### 6.4. Concatenating Strings Without Delimiter Safety or Versioning

Concatenating \`tenantId + productId\` can collide, e.g., \`("ab", "c")\` and \`("a", "bc")\`. Joining with \`:\` still carries risks if data contains that character. Use a record, \`SimpleKey\`, a custom key type, or length-prefixed/properly escaped encoding. If a cache provider requires strings (especially Redis), design a clear serialization convention and version it when schemas change.

### 6.5. Keys Containing Mutable or Unstable Objects

Do not use a DTO with mutable fields as a key if \`equals/hashCode\` depends on those fields. Never use \`target.toString()\` or object addresses to generate keys, because keys can vary across calls and instances. With distributed caches, verify key serializers, region names, and the format shared across instances.

### 6.6. Treating KeyGenerator as a Cure-All

KeyGenerator only picks the key. It does not configure TTL, prevent cache stampedes, automatically evict when the database changes, provide distributed locking, or ensure transactions commit before putting entries. Those needs belong to CacheManager/providers, invalidation flows, transaction-aware caches, and concurrency tests.

### 6.7. Using the Same Cache Name for Different Result Types

If both \`getTitle\` and \`getCategory\` use \`cacheNames="products"\` and key \`ProductKey(tenant, id)\`, one call can read the wrong value from the other. Use separate cache names or intentionally include the data classification in the key. Do not rely on return types for Spring to separate keys automatically.

## 7. When Is a Shared KeyGenerator Unnecessary?

Not every \`@Cacheable\` usage needs a custom generator.

- A function taking only \`productId\` and caching strictly by ID usually works fine with the default key.
- One or two methods with a simple rule can use \`key = "#p0"\` or an equivalent SpEL expression, making the key immediately visible to readers.
- If methods have very different meanings and signatures, forcing one specialized global generator creates coupling and runtime errors.
- If a method should not be cached because results change too quickly or have side effects, a custom key will not make it a good caching candidate either.

Create a shared KeyGenerator when there is **a stable, genuinely shared data rule**: for example, services all querying resources by a tenant + resourceId pair, needing consistent isolation and reuse across both \`@Cacheable\` and \`@CacheEvict\`.

## 8. Testing and Operational Checks

### 8.1. Testing the Generator Class Directly

Since \`KeyGenerator\` is plain Java code, you can call \`generate(...)\` directly in unit tests without starting a Spring context. Essential assertions:

1. Same \`tenantId\` + \`productId\` with different traceId → **equal keys**.
2. Different tenant with same productId → **different keys**.
3. Different productId with same tenant → **different keys**.
4. Wrong parameter count/types → **explicit error**, never silently falling back to a shared key.
5. Record keys must have proper \`equals/hashCode\`; if using a serializer, test round-trip serialization.

### 8.2. Spring Cache Integration Tests

Call methods through the Spring bean/proxy and inspect the data source too:

1. First miss invokes the method body and creates a cache entry.
2. Same key with a different traceId hits without re-calling the source.
3. Different tenant misses without reusing the previous tenant's data.
4. Same key in **two different cacheNames** does not mix values.
5. \`@CacheEvict\` generates **the exact key** and the subsequent read misses.
6. If a method is refactored to a new signature, the generator must fail detectably instead of silently producing wrong keys.
7. If using Redis or multiple instances, verify serialized keys and cross-instance invalidation behavior.

Monitor hit ratios, cache cardinality, eviction events, and memory growth to catch keys with too many unstable components.

### 8.3. Pre-Production Checklist

- [ ] \`KeyGenerator\` bean has the exact name and is Spring-managed.
- [ ] \`@EnableCaching\` is enabled in the context containing the services to intercept.
- [ ] Every method using the generator satisfies its parameter contract.
- [ ] Keys include all result-identifying components; omitted parameters genuinely do not affect output.
- [ ] Tenant/user/locale/version are distinguished where required by business logic.
- [ ] Read, put, and evict operations use the same cache name and same key rule.
- [ ] \`equals/hashCode\` are stable; a serialization strategy appropriate for the provider is in place.
- [ ] \`key\` and \`keyGenerator\` are not set simultaneously on the same annotation.
- [ ] Generator unit tests and cache hit/miss/evict integration tests all pass.
- [ ] Separate TTL/invalidation/metrics strategies accompany the key generation policy.

## 9. Self-Check Questions

**1.** There is a bean named \`tenantProductKeyGenerator\`. How do you select it for a single \`@Cacheable\`?  
**Answer:** \`@Cacheable(cacheNames = "productTitles", keyGenerator = "tenantProductKeyGenerator")\`.

**2.** A KeyGenerator builds keys from \`(tenantId, productId)\`; should two requests differing only in traceId produce different keys?  
**Answer:** No, if traceId is only metadata and affects neither the result nor mandatory side effects.

**3.** Why is \`record ProductKey(String tenantId, String productId)\` better than arbitrary string concatenation?  
**Answer:** Components are structurally compared via equals/hashCode; you do not have to invent delimiter-escaping rules for local caches.

**4.** Does \`@CacheConfig(keyGenerator="...")\` automatically enable caching for every method in the class?  
**Answer:** No. Methods still need cache annotations.

**5.** If a generator adds \`method.getName()\` to the key, what must be checked when using \`@CacheEvict\`?  
**Answer:** Eviction must generate the exact key used by the read call, even though method names usually differ.

**6.** Can you put \`key="#p0"\` and \`keyGenerator="customKeyGenerator"\` on the same \`@Cacheable\`?  
**Answer:** No; the two attributes are mutually exclusive.

**7.** Does changing KeyGenerator automatically delete old entries in Redis?  
**Answer:** No. You need a migration, versioning, TTL, or corresponding cache-region clearing plan.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- KeyGenerator Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
