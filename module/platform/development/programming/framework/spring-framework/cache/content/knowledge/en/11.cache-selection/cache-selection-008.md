# NoOpCacheManager When You Need to Intentionally Skip Storage

> **Context:** Spring Framework Cache — **Cache region selection** group. `NoOpCacheManager` is a `CacheManager` implementation that intentionally **does not store cache data**. It is useful when you want to keep Spring Cache structure and annotations intact while temporarily avoiding reuse of results from previous calls.

## 1. Learning objectives

After this lesson, you can:

1. Explain how `NoOpCacheManager` and `NoOpCache` work in Spring Cache.
2. Distinguish **not storing cache entries**, **not enabling Spring Cache**, and **using an in-memory cache**.
3. Predict how many times an `@Cacheable` method body executes when using the no-op manager versus `ConcurrentMapCacheManager`.
4. Choose the right configuration in Spring Boot (`spring.cache.type=none`) or plain Spring Framework (declaring a `NoOpCacheManager` bean).
5. Write a Java 17 experiment and JUnit tests confirming no-op always misses and does not retain put values, while identifying risks of accidentally using no-op in production.

## 2. What is the role of CacheManager?

Spring Cache is an abstraction layer, not tightly coupled to Redis, Caffeine, or a specific storage backend.

```text
Client → Spring-managed bean
             |
             v
       Cache interceptor
             |
             v
         CacheManager
             |
             +-- ConcurrentMapCacheManager → stores in a JVM map
             +-- CaffeineCacheManager -----→ cache in the JVM
             +-- RedisCacheManager --------→ Redis server
             +-- NoOpCacheManager ---------→ stores no values
```

- `CacheManager` provides `Cache` instances by name via `getCache(name)` and reports known cache names via `getCacheNames()`.
- `Cache` provides operations such as `get(key)`, `put(key, value)`, `evict(key)`, and `clear()`.
- The Spring Cache interceptor decides when to check the cache, execute the method, store, or remove entries based on `@Cacheable`, `@CachePut`, and `@CacheEvict`.
- The provider/adapter decides the **actual storage behavior**. Two managers share the same API yet have completely different effects.

**Main idea:** never assume an annotation means data is definitely retained. To know whether data is reused, check the actual `CacheManager`.

## 3. How does NoOpCacheManager work?

`NoOpCacheManager` resides in package:

```java
import org.springframework.cache.support.NoOpCacheManager;
```

It supplies named `NoOpCache` objects, with no underlying data store. For a no-op cache:

- `get(key)` returns a not-found state — a **cache miss**.
- `put(key, value)` does not retain the inserted value.
- `evict(key)` and `clear()` have no real data to remove.
- Every `@Cacheable` call with the same key finds no prior result to return, so normally the **method body runs again**.
- `NoOpCacheManager` still satisfies the cache-provisioning contract, so using a cache name does not imply a real data cache was created.

Typical interaction:

```text
First call: service.load("A")
  NoOpCache.get("A") → miss
  execute service.load → result A-1
  NoOpCache.put("A", A-1) → ignored
  return A-1

Subsequent call: service.load("A")
  NoOpCache.get("A") → miss (still no A-1)
  execute service.load → result A-2
  NoOpCache.put("A", A-2) → ignored
  return A-2
```

In this diagram, `A-1` and `A-2` clarify two separate executions, **not** a data bug. In a deterministic read function, two executions may return the same value while still costing twice the CPU, I/O, or source queries.

### Distinguishing “not storing” from “missing cache bean”

Using `NoOpCacheManager` is **not the same** as failing to configure a `CacheManager`. When Spring Cache is enabled, the framework still has a valid manager and a matching cache object to process annotation paths. If replaced by a misconfigured manager or one unaware of the cache name, the application may throw a cache resolution error. No-op avoids needing a storage backend, yet **does not eliminate the entire interception mechanism**.

## 4. When should you intentionally choose NoOpCacheManager?

### 4.1. Test environments that need real logic to execute

A test that measures repository call counts or verifies business logic on **every invocation** can have executions hidden by cache hits. No-op ensures every `@Cacheable` call recomputes so the test observes real logic.

For example, if a test simply verifies the service calls downstream twice when the client calls twice, using no-op prevents a cache hit from reducing downstream calls to one. However, **do not use no-op in tests aiming to prove cache hits, TTL, eviction, or concurrency**; those tests need an appropriate provider and different expectations.

### 4.2. Dev environments or bug investigation

When isolating cache effects from data-source behavior, no-op provides a useful control baseline: if a bug appears only when real caching is enabled, inspect keys, invalidation, serialization, or TTL. This is a diagnostic tool, not a permanent fix.

### 4.3. Disabling caching features by environment

An application can pick no-op for a specific environment while keeping annotations and business code unchanged. This changes configuration without editing every `@Cacheable`; in Spring Boot, the most convenient way is typically setting `spring.cache.type=none` when caches are auto-configured.

### 4.4. Fallback when intentionally accepting uncached execution

If computation cost is low and skipping storage is acceptable, no-op can be a temporary option. However, it is **not** an automatic failover mechanism from a broken cache to the data source for any provider; achieving fail-open/fail-closed when Redis fails still requires designing `CacheErrorHandler`, timeouts, and backend load protection.

## 5. Comparison with other cache management approaches

| Implementation | Stores values? | Second call with same key | Best suited for |
| --- | --- | --- | --- |
| `NoOpCacheManager` | No | Miss; typically re-runs `@Cacheable` body | Tests avoiding caching, diagnostics, intentional config |
| `ConcurrentMapCacheManager` | Yes, in a JVM map | Hit if entry still exists | Demos, simple hit/miss tests |
| `CaffeineCacheManager` | Yes, in the JVM; supports eviction/expiration | Hit if entry is still valid | Local caches with size and TTL policies |
| `RedisCacheManager` | Yes, in Redis server | Hit if entry exists and connection succeeds | Sharing caches across multiple instances |
| `@EnableCaching` not enabled | No annotation caching applied | Method called directly via normal Java flow | Systems that do not need cache annotation processing |

**Note:** a cache miss does not necessarily mean "there is no caching in the application". With no-op, Spring still runs part of the cache abstraction path; it merely **does not store values to hit next time**.

`NoOpCacheManager` is also **not the same** as `NullValue` or negative caching. Null-value caching intentionally stores a "not found" result to avoid repeated source queries. No-op retains neither normal values nor "not found" states.

## 6. Spring Boot: disabling cache storage via property

In a Spring Boot application that already has Spring Cache infrastructure, set:

```properties
spring.cache.type=none
```

Or in YAML:

```yaml
spring:
  cache:
    type: none
```

When **Spring Boot is allowed to auto-configure `CacheManager`**, choosing `none` tells Boot to use the no-op cache manager instead of an auto-detected storage provider. Official Spring Boot documentation introduces this for environments needing cache storage disabled and for tests.

Example of a service still keeping annotations:

```java
@Service
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public int calculatePrice(String sku) {
        return expensiveCalculation(sku);
    }
}
```

This is an **illustrative code snippet**, lacking the `expensiveCalculation` implementation and therefore not a standalone program. When `spring.cache.type=none` takes effect and caching is enabled, calling the same `sku` multiple times will not retrieve a previously stored result; the price calculation logic is invoked again.

### Important conditions for Boot configuration

- `spring-boot-starter-cache` provides the required integration components; `@EnableCaching` activates annotation caching.
- The `spring.cache.type=none` property works via **Boot's auto-configuration branch**. If the application already defines its own `CacheManager` or `CacheResolver` bean, auto-config may back off; adding the property alone **does not automatically replace** user-defined beans.
- If multiple providers are present, do not guess from the classpath; check the actual `CacheManager` bean by type.
- Do not treat `spring.cache.type=none` as a switch that removes all proxy/AOP activity or all key/SpEL code. It selects a non-storing provider; annotation and expression checks may still execute.
- To use no-op only in tests, place the property in dedicated test config, such as `src/test/resources/application.properties`, or pass it via `@SpringBootTest(properties = "spring.cache.type=none")` in full-context tests. Other test-slicing auto-configurations may swap managers depending on the Boot version, so verify the actual type.

Never claim a configuration has disabled cache storage before verifying that the active bean is `NoOpCacheManager`.

## 7. Plain Spring Framework: creating a NoOpCacheManager bean

When not using Spring Boot auto-configuration, create the `CacheManager` bean directly:

```java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.support.NoOpCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new NoOpCacheManager();
    }
}
```

This is a **configuration class to place in a project with a Spring ApplicationContext**, without `main`. `NoOpCacheManager` belongs to the `spring-context` module.

In plain Spring Framework, Spring does not read `spring.cache.type` to switch beans automatically; to change providers you must swap the bean, use an appropriate profile, or define a custom conditional configuration.

### Selecting a bean by Spring profile

An illustrative example:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheProfiles {

    @Bean
    @Profile("no-cache")
    CacheManager noOpCacheManager() {
        return new NoOpCacheManager();
    }

    @Bean
    @Profile("!no-cache")
    CacheManager normalCacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

This is an **illustrative configuration snippet**, requiring imports for `CacheManager`, `NoOpCacheManager`, `ConcurrentMapCacheManager`, `Bean`, `Configuration`, `Profile`, and `EnableCaching`. Only one of the two beans is registered per active profile. In real deployments, the normal provider might be Redis/Caffeine rather than Simple. Never accidentally leave both `CacheManager`s active without a clear bean selection rule.

**Operational warning:** enable the no-op profile in production only after evaluating the increased load on databases, APIs, I/O, and CPU. Zero cache hits means every repeated call may hit the source again.

## 8. Complete runnable example in Java 17

The experiment below creates **two independent ApplicationContexts** with the same service:

1. One context using `NoOpCacheManager`.
2. One context using `ConcurrentMapCacheManager`.

Both enable `@EnableCaching`; only the provider differs. This makes the difference of no-op observable via the number of times the method body executes rather than relying only on timing.

### 8.1. Project structure

```text
noop-cache-demo/
├── pom.xml
└── src/
    ├── main/java/demo/cache/NoOpCacheDemo.java
    └── test/java/demo/cache/NoOpCacheDemoTest.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>noop-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.1</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.NoOpCacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` includes Spring Cache classes and the Simple/no-op cache managers; it also pulls in the needed Spring dependencies. The example uses Java 17-compatible Spring Framework 6.2.1 for easy reproducibility. In real Spring Boot apps, manage Spring versions via the BOM/parent instead of pinning individual modules.

### 8.3. `src/main/java/demo/cache/NoOpCacheDemo.java`

```java
package demo.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.NoOpCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class NoOpCacheDemo {

    public static class CalculationService {
        private final AtomicInteger executions = new AtomicInteger();

        @Cacheable(cacheNames = "calculations", key = "#p0")
        public String calculate(String key) {
            int count = executions.incrementAndGet();
            return key + "-run" + count;
        }

        public int executionCount() {
            return executions.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class NoOpConfig {
        @Bean
        public CacheManager cacheManager() {
            return new NoOpCacheManager();
        }

        @Bean
        public CalculationService calculationService() {
            return new CalculationService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class SimpleConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("calculations");
        }

        @Bean
        public CalculationService calculationService() {
            return new CalculationService();
        }
    }

    private static void scenario(String label, Class<?> configType) {
        try (var context =
                     new AnnotationConfigApplicationContext(configType)) {

            CacheManager manager = context.getBean(CacheManager.class);
            CalculationService service =
                    context.getBean(CalculationService.class);

            System.out.println(label + " manager="
                    + manager.getClass().getSimpleName());
            System.out.println(label + " first="
                    + service.calculate("A"));
            System.out.println(label + " second="
                    + service.calculate("A"));
            System.out.println(label + " executions="
                    + service.executionCount());
        }
    }

    public static void main(String[] args) {
        scenario("no-op", NoOpConfig.class);
        scenario("simple", SimpleConfig.class);
    }
}
```

**Why is this a fair comparison?**

- Same `CalculationService.calculate("A")` method and same key `A`.
- Both contexts have `@EnableCaching`, so only the **CacheManager choice** differs.
- `@Cacheable` is placed on a public method of a Spring bean; the client fetches the bean via `context.getBean(...)` so calls pass through the proxy.
- The `AtomicInteger` counter is **inside** the method body, so it does not increment on cache hits.
- Each context has a fresh service, counter starting at 0, and an initially empty cache.
- The result string embeds the run number so client call counts cannot be confused with real execution counts.

### 8.4. Run command

In the `noop-cache-demo` directory, requires Java 17+, Maven 3.9+, and access to Maven Central on the first dependency download:

```bash
java -version
mvn -q compile exec:java
```

Lines **printed by the program itself**, excluding Maven logs or Spring startup messages:

```text
no-op manager=NoOpCacheManager
no-op first=A-run1
no-op second=A-run2
no-op executions=2
simple manager=ConcurrentMapCacheManager
simple first=A-run1
simple second=A-run1
simple executions=1
```

Explanation:

1. **No-op:** first call misses, computes `A-run1`, yet `put` stores nothing. Second call still misses, computing `A-run2`. Two client calls result in two method body executions.
2. **Simple:** first call misses, computes `A-run1`, and stores it in `ConcurrentMapCache`. Second call hits, returning `A-run1` without running the method body again.
3. With identical Java code, changing only the CacheManager produced different behavior. This is direct proof of **skipping storage**, not merely an inference from the class name.

`mvn -q compile exec:java` runs the app through the Maven plugin. If running `javac`/`java` directly, you must supply all Spring JARs on the classpath; Maven handles that here.

## 9. JUnit tests: confirming no-op does not retain values

Create `src/test/java/demo/cache/NoOpCacheDemoTest.java`:

```java
package demo.cache;

import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class NoOpCacheDemoTest {

    @Test
    void noOpAlwaysRecalculatesAndDoesNotStore() {
        try (var context = new AnnotationConfigApplicationContext(
                NoOpCacheDemo.NoOpConfig.class)) {

            var service = context.getBean(
                    NoOpCacheDemo.CalculationService.class);

            Cache cache = Objects.requireNonNull(
                    context.getBean(CacheManager.class)
                            .getCache("calculations")
            );

            assertEquals("A-run1", service.calculate("A"));
            assertNull(cache.get("A"));

            assertEquals("A-run2", service.calculate("A"));
            assertEquals(2, service.executionCount());
            assertNull(cache.get("A"));
        }
    }

    @Test
    void simpleCacheSkipsSecondExecution() {
        try (var context = new AnnotationConfigApplicationContext(
                NoOpCacheDemo.SimpleConfig.class)) {

            var service = context.getBean(
                    NoOpCacheDemo.CalculationService.class);

            assertEquals("A-run1", service.calculate("A"));
            assertEquals("A-run1", service.calculate("A"));
            assertEquals(1, service.executionCount());
        }
    }
}
```

Run:

```bash
mvn -q test
```

Expected outcome: JUnit tests pass, Maven returns exit code 0. With `-q`, "BUILD SUCCESS" is not necessarily printed to the console. The command runs without Redis or a database.

**Why are these tests valuable?**

- `assertNull(cache.get("A"))` verifies no-op still misses **after `@Cacheable` ran and tried to put the result into the cache**.
- `executionCount() == 2` verifies the method body re-executes even when the client calls with the same key.
- Comparing against Simple cache confirms real hit behavior when the provider stores data.
- Each test creates a separate context, avoiding cache state leakage from other tests.

If a test's goal is to verify TTL, invalidation, or hits/misses on Redis/Caffeine, do not replace the provider under test with no-op and treat the results as equivalent.

## 10. Other annotations when using NoOpCacheManager

### 10.1. @Cacheable

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
```

This is an illustrative method inside a bean that has a repository. When the no-op manager is active, repeated calls with the same key find no prior result, so the body executes along the miss path. If the method returns a mutable object, no-op does not preserve a copy or state of that object either.

### 10.2. @CachePut

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product refresh(String id) {
    return repository.loadFresh(id);
}
```

By `@CachePut` semantics, the method executes and the framework asks to put the result into the cache. With `NoOpCache`, the put operation stores nothing; a subsequent read via `@Cacheable` still misses. Do not use no-op to test that a result was stored successfully.

### 10.3. @CacheEvict

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void remove(String id) {
    repository.delete(id);
}
```

Business logic `repository.delete(id)` must still run if the method is called normally; eviction on a no-op cache has no real entry to remove. Hence having `@CacheEvict` does not automatically guarantee a cache on another provider or another instance was also cleared.

The three snippets above are **annotation examples inside an application that already has a repository and matching domain classes**, not standalone runnable Java files.

## 11. No-op does not mean disabling cache interception completely

This is an important misconception:

- **Using NoOpCacheManager:** the application still has a `CacheManager` bean and can still go through Spring Cache advice. `key`, `condition`, `unless` expressions, and annotation operations may still be evaluated along the processing path; thus no-op does not guarantee removing all overhead or all SpEL errors.
- **Without `@EnableCaching`:** `@Cacheable` annotations are not automatically applied by Spring in a context without caching configured. Methods are invoked via normal Java flow. This does not imply other cache libraries or manual cache calls are disabled as well.
- **Calling a method via `this.method()` inside the same bean (self-invocation):** in default proxy mode, internal calls can bypass the interceptor even when the real manager is Redis/Caffeine. That is not proof of a no-op manager.

To measure the situation accurately, log the `CacheManager` class and check method body execution counts. Do not conclude "caching is disabled" from a single miss.

### Risks of no-op fallback in CompositeCacheManager

`CompositeCacheManager` can search caches across multiple managers; depending on configuration, `setFallbackToNoOpCache(true)` provides a no-op cache for **cache names not handled by earlier managers**.

This differs from selecting `NoOpCacheManager` for the **entire** application. Fallback can mask cache name configuration bugs: instead of failing on a mistyped cache name, the system silently misses every time and reloads from source. Enable fallback only when not storing unknown caches is genuinely desired policy.

## 12. Production risks and how to control them

### 12.1. Increased traffic to the data source

Suppose there are 1,000 identical calls, the underlying task takes 50 ms, and a storing cache provider yields a 90% hit rate:

- A real cache can avoid most source executions if data and keys align.
- No-op avoids none of the repeated executions; load can spike sharply on the database, downstream systems, and CPU.

This is reasoning about execution counts; do not treat 50 ms or 90% as a performance promise for a specific system. Measure actual source loads and latency before deciding to use no-op in production.

### 12.2. Behavior divergence between tests and production

Tests using no-op will not catch bugs that surface only with real caching: key collisions, stale entries, TTL, serialization, cache stampedes, data shared across users/tenants, wrong evictions, or concurrent writes. Maintain **two test groups**: business logic with no-op when sensible, and caching behavior with the real provider or an equivalent one.

### 12.3. Surprises when using @Cacheable on methods with side effects

No-op causes the body to run every time, so a method that both reads and performs a side effect may appear to work in tests. When switching to a real cache, cache hits skip that side effect, causing business bugs. Design `@Cacheable` methods not to depend on always executing.

### 12.4. Bean initialization and configuration precedence

If `@Primary`, multiple `CacheManager` beans, a custom `CacheResolver`, or other Boot auto-configurations exist, the actual provider might not be no-op as expected. First inspect `context.getBean(CacheManager.class).getClass().getName()` when there is a single bean of that type; if multiple managers exist, inspect the actual resolver/qualifiers.

### 12.5. Do not turn no-op into an ad-hoc Redis outage handler

If Redis goes down, swapping the provider for no-op can cause a sudden surge of requests hitting the database. Plan capacity, timeouts, rate limits, circuit breakers, and degradation strategies for the source. "Not storing" is an architectural decision with a cost, not an always-safe choice.

## 13. Deployment checklist

1. **Purpose:** do you truly want to skip storage, or disable annotation interception altogether?
2. **Environment:** test/dev only, or production too? If production, is source load acceptable when hit rate drops to 0?
3. **Configuration:** Boot app using `spring.cache.type=none` under auto-config, or plain Spring Framework using `@Bean NoOpCacheManager`?
4. **Provider precedence:** does any custom `CacheManager` bean or `CacheResolver` override the configuration?
5. **Verification:** log the manager type, call the same key twice, and assert body execution count.
6. **Business safety:** read methods do not rely on side effects; write methods still update the source.
7. **Testing:** use a real cache for hit, TTL, and eviction tests; use no-op for tests that do not want results reused.
8. **Operational observability:** measure DB/API request counts and latency to avoid accidentally using no-op on heavy workloads.
9. **Scope:** avoid `CompositeCacheManager` no-op fallback hiding missing cache name errors.
10. **Environment promotion:** ensure profiles, ConfigMaps, and environment variables select the right manager upon deployment.

## 14. Self-practice questions

**Question 1:** Using `NoOpCacheManager`, `@Cacheable find("A")` is called three times sequentially, with no other cache layer. How many times does the method body usually run?  
**Answer:** **3 times**, because no entry is stored to produce a cache hit.

**Question 2:** In Boot, `spring.cache.type=none` is set, yet a custom `@Bean CacheManager` is already defined by the application. Is the provider guaranteed to switch to no-op?  
**Answer:** **No.** Check auto-configuration conditions and the actual beans/resolvers.

**Question 3:** Is no-op suitable for testing that `@CacheEvict` deletes the right key?  
**Answer:** **No**, because there is no real cache entry to delete. Use a storing provider and verify before/after eviction.

**Question 4:** Why is no-op not the same as omitting `@EnableCaching`?  
**Answer:** No-op still supplies a cache through the API and can continue passing through the Spring Cache interceptor; disabling annotation caching prevents advice from being applied in that context.

**Question 5:** Why can tests with no-op miss `@Cacheable` bugs in production?  
**Answer:** No-op produces no cache hits; bugs from hits skipping side effects, wrong keys, stale data, or failed invalidation only surface with a storing provider.

## Official references

- [Spring Framework — NoOpCacheManager JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCacheManager.html)
- [Spring Framework — NoOpCache JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCache.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching, None provider, and Testing](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Remember:** `NoOpCacheManager` lets you **intentionally skip storing any cache entries** while keeping the Spring Cache interface intact. It is a valuable configuration and testing tool, yet it does not remove annotation interception by itself and cannot be used to confirm caching actually hits. To be safe, verify the selected `CacheManager` and the method body execution count for the same key.