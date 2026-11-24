# Declaring a CacheManager Bean in Spring Java Configuration

> Context: **Spring Framework – Cache / Setup**. This lesson shows how to declare a `CacheManager` with `@Bean` in a `@Configuration` class, enable cache annotations with `@EnableCaching`, verify the configuration runs properly, and choose a cache store for plain Spring Framework or Spring Boot applications.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of `CacheManager`, `Cache`, `@Configuration`, `@Bean`, and `@EnableCaching`.
2. Declare a Java-based `CacheManager` configuration yourself without XML.
3. Use `ConcurrentMapCacheManager` for experimentation, then switch to `CaffeineCacheManager` or `RedisCacheManager` when requirements change.
4. Understand how Spring locates a `CacheManager` bean when `@Cacheable` is invoked, and handle cases with multiple managers.
5. Run a complete Java 17 example, verify cache hits/misses, and identify common configuration mistakes.

## 1. What Is CacheManager, and Why Declare It as a Bean?

Spring Cache defines a common abstraction across multiple cache stores. Two key interfaces:

- `org.springframework.cache.Cache`: represents a named cache supporting operations such as `get`, `put`, `evict`, and `clear`.
- `org.springframework.cache.CacheManager`: manages and retrieves a `Cache` instance by name via `getCache(String name)` and lists available names via `getCacheNames()`.

`CacheManager` itself is not required to store data directly; actual storage behavior depends on the implementation. For example, `ConcurrentMapCacheManager` stores entries in a single JVM's memory; `CaffeineCacheManager` adds rich local caching policies; `RedisCacheManager` works with Redis via Spring Data Redis.

Execution flow when using cache annotations:

```text
Client calls Spring-managed service bean
                |
                v
      Spring caching interceptor
                |
      cache name + key from @Cacheable
                |
                v
     CacheManager.getCache(name)
                |
       +--------+--------+
       |                 |
      HIT               MISS
       |                 |
  Return value      Run original method
       |                 |
       |           Store result in cache
       +--------+--------+
                |
           Return result
```

**The role of Java configuration** is to tell Spring which implementation to use and how to configure it. Instead of instantiating `new CacheManager` directly inside a service, we declare a **Spring bean** so the caching interceptor, other services, or inspection tools can all share it.

One common point of confusion: **`@Bean` registers the manager, whereas `@EnableCaching` activates annotation processing**. Having only the manager without enabling annotations usually means `@Cacheable` performs no caching.

## 2. Minimal Configuration with @Configuration and @Bean

For a simple example, use `ConcurrentMapCacheManager` included in `spring-context`:

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices", "products");
    }
}
```

Here:

- `@Configuration` marks the class containing bean definitions for the application context.
- `@Bean` registers the returned object as a bean with default name `cacheManager` and public type `CacheManager`.
- `@EnableCaching` activates the cache annotation infrastructure in the corresponding application context.
- The `ConcurrentMapCacheManager("prices", "products")` constructor creates a fixed list of named caches; if code uses an undeclared cache name, `getCache(name)` may return `null` and annotated cache operations will fail.
- `CacheManager` is typically a singleton bean in the application context, shared across multiple calls and services.

Inside a `@Configuration` class, you can write `@Bean(name = "priceCacheManager")` to give an explicit bean name. The bean name is distinct from a cache name: `priceCacheManager` is the name of the **manager**, while `prices` is the name of a **cache managed by that manager**.

### Do Not Confuse Classes and Bean Creation

```text
Bean name: cacheManager
  Type: org.springframework.cache.CacheManager
  Implementation: org.springframework.cache.concurrent.ConcurrentMapCacheManager
  Caches managed by bean: prices, products
```

One manager can hold multiple caches. One cache can hold many distinct entries distinguished by key, such as `prices["P42"]` and `prices["P43"]`.

`ConcurrentMapCacheManager` is suitable for demos, tests, and small tasks. It **does not provide TTL, capacity limits, or cross-JVM synchronization like a dedicated cache system**. For production applications, choose a provider based on latency, capacity, consistency, and distribution goals.

## 3. Runnable Plain Spring Framework Example with Java 17

This example uses Spring Framework 6.2.0 to illustrate the long-standing API running on JDK 17+. This version is **pinned for lesson reproducibility**, not a recommendation to choose it as the latest version for production. A project that already has a Spring BOM or Spring Boot should keep Spring modules aligned with its managed version line.

### 3.1. File Structure

```text
spring-cache-manager-demo/
├── pom.xml
└── src/main/java/demo/
    ├── CacheConfig.java
    ├── PriceService.java
    └── Main.java
```

### 3.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-manager-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the simple cache API/manager and pulls in the Spring dependencies required for the example. No Spring Boot, Caffeine, Redis, or external server is needed to run this example.

### 3.3. src/main/java/demo/CacheConfig.java

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

**Detail to notice:** the name `prices` in `ConcurrentMapCacheManager` must match `cacheNames = "prices"` on the business method exactly.

### 3.4. src/main/java/demo/PriceService.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {

    private final AtomicInteger sourceCalls = new AtomicInteger();

    @Cacheable(cacheNames = "prices", key = "#p0")
    public String getPrice(String productId) {
        int count = sourceCalls.incrementAndGet();
        System.out.println("Read source " + productId + " (call " + count + ")");
        return "price-" + productId + "-100";
    }

    public int sourceCalls() {
        return sourceCalls.get();
    }
}
```

Explanation:

- `@Cacheable` instructs Spring to cache the return value under the name `prices`.
- `key = "#p0"` uses the first argument as the key; this syntax does not depend on whether Java parameter names are preserved at compile time.
- `AtomicInteger` counts how many times the method body **actually** executes, making it easy to distinguish hits from misses.
- The value `"price-" + productId + "-100"` is a stable simulated result; in reality it could be an expensive query or computation.

If `key` is omitted, Spring uses the default `KeyGenerator` based on the method arguments. In an example with a single `String`, the default key can also use that argument directly; using `#p0` makes key determination explicit for explanation.

### 3.5. src/main/java/demo/Main.java

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             CacheConfig.class, PriceService.class)) {

            PriceService service = context.getBean(PriceService.class);

            System.out.println("Call 1: " + service.getPrice("P42"));
            System.out.println("Call 2: " + service.getPrice("P42"));
            System.out.println("Call 3: " + service.getPrice("P43"));
            System.out.println("Source read count: " + service.sourceCalls());

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println("Manager: "
                    + manager.getClass().getSimpleName());
            System.out.println("Cache prices exists: "
                    + (manager.getCache("prices") != null));
        }
    }
}
```

Use `context.getBean(PriceService.class)` to obtain **the Spring-managed bean**. If you replace it with `new PriceService()`, that instance sits outside the Spring container and will not have the caching interceptor applied.

### 3.6. Compile, Run, and Verify the Output

Requirements: JDK 17+, Maven, Internet for the first dependency download. Inside `spring-cache-manager-demo/`:

```bash
mvn -q clean compile exec:java
```

The following are the **lines printed by the application code**, in exact order; any log lines emitted by Maven or Spring in your environment are not part of this output:

```text
Read source P42 (call 1)
Call 1: price-P42-100
Call 2: price-P42-100
Read source P43 (call 2)
Call 3: price-P43-100
Source read count: 2
Manager: ConcurrentMapCacheManager
Cache prices exists: true
```

There are three `getPrice` calls, yet only two executions of the underlying logic, because the second call with `P42` hits the cache. The call with `P43` uses a different key and therefore misses. Retrieving the `CacheManager` bean and checking `getCache("prices") != null` confirms the cache name has been registered.

**Right way to view this demo:** It illustrates `@Bean` declaration and cache interception in a plain Spring Framework application. It does not include HTTP endpoints, a database, TTLs, or cache sharing across multiple processes.

## 4. Configuring CaffeineCacheManager Instead of ConcurrentMap

For applications needing capacity limits and entry expiration within **a single JVM**, you can create a Caffeine bean. This requires `spring-context-support` along with the `caffeine` library (when using Spring Boot, the cache starter typically provides the Spring adapter):

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context-support</artifactId>
    <version>6.2.0</version>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
    <version>3.1.8</version>
</dependency>
```

Example configuration class **replacing the entire manager bean from the previous example**:

```java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("prices");
        manager.setCacheSpecification(
                "maximumSize=1000,expireAfterWrite=300s");
        return manager;
    }
}
```

- `new CaffeineCacheManager("prices")` preconfigures the `prices` cache and restricts the cache names created by this manager.
- `maximumSize=1000` caps the approximate number of entries under Caffeine's eviction policy.
- `expireAfterWrite=300s` expires entries 300 seconds after they are written or updated.
- In this manual Java configuration example, **this bean itself** determines the TTL and size. Setting `spring.cache.caffeine.spec` in Spring Boot's `application.properties` is not guaranteed to reconfigure a manager bean you created yourself.

When switching providers, there should be **one clear default `CacheManager` bean**. Do not simultaneously add two `@Bean CacheManager cacheManager()` methods with the same name or leave multiple managers without a selection rule.

The Caffeine code above is a Spring configuration snippet to drop into a project that already has the appropriate dependencies; the plain Maven example in Section 3 must have its dependencies updated before replacing this class. It remains a **local** cache and does not automatically synchronize across instances.

## 5. Declaring RedisCacheManager

For caches shared across multiple instances, Spring Data Redis provides `RedisCacheManager`. It requires the Spring Data Redis module/client and an active `RedisConnectionFactory`. Below is a **bean configuration pattern for a project that already integrates Redis**, not a standalone runnable program:

```java
import java.time.Duration;
import java.util.Set;

import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfig {

    @Bean
    public CacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .initialCacheNames(Set.of("prices"))
                .build();
    }
}
```

Spring injects `RedisConnectionFactory` from the application context into the `@Bean` method; the manager uses that connection to read and write cache entries. `entryTtl(Duration.ofMinutes(5))` sets a 5-minute expiration. The example assumes a reachable Redis server, appropriate serializers, and compatible Spring Data Redis dependencies and versions.

In a Spring Boot application, you can add `spring-boot-starter-data-redis` together with `spring-boot-starter-cache`, or let Boot auto-configure the Redis manager when conditions are met. If you create the `RedisCacheManager` bean manually, you are directly responsible for settings such as TTL, cache names, and serialization. Do not disable key prefixes just to "simplify": the default prefix prevents caches with different names from colliding in Redis.

### Choosing a Manager by Requirements

| Bean implementation | Storage location | Strengths | Key limitations |
| --- | --- | --- | --- |
| `ConcurrentMapCacheManager` | In-JVM RAM | Minimal setup, suited for learning and testing | No built-in TTL/entry limit, not shared across instances |
| `CaffeineCacheManager` | In-JVM RAM | Eviction/expiration and in-memory performance | Each instance maintains its own cache |
| `RedisCacheManager` | Redis server | Shared data across instances | Requires network, Redis, serializers, and infrastructure error handling |
| `JCacheCacheManager` | Per JSR-107 provider | Standard API integration with compatible providers | Requires appropriate provider and cache configuration |
| `NoOpCacheManager` | No storage | Disables cache effect for testing/troubleshooting | Every call runs the original method |

Choose and declare only the managers you actually need. Knowing how to create beans for multiple providers does not mean installing multiple providers will make things faster.

## 6. Spring Boot: When Should You Create a Manual @Bean?

Spring Boot can auto-configure a `CacheManager` based on libraries on the classpath when caching is enabled. For example, with `spring-boot-starter-cache` and Caffeine on the classpath, Boot can create a `CaffeineCacheManager`.

When you **declare a `CacheManager` bean manually**, Spring Boot generally backs off from creating another auto-configured manager for the same role. This is useful when you want to:

- Precisely control cache names, TTLs, sizes, or serializers.
- Have multiple managers, multiple providers, and explicit business routing rules.
- Initialize caches conditionally or with Java configuration more complex than application properties.
- Use different caching strategies across dev/test/prod environments.

However, manual configuration also means certain `spring.cache.*` properties or `CacheManagerCustomizer` beans only apply to Boot-created managers and **do not automatically apply to a manager you build yourself**. Inspecting the actual bean is more reliable than inferring from dependencies.

Suggested configuration in a Boot application:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

You can use `@Configuration(proxyBeanMethods = false)` when `@Bean` methods do not need CGLIB proxying for inter-bean calls. It does not "turn off" caching proxies for services: those are two separate proxy mechanisms. With Boot, it is good practice to keep `@EnableCaching` on a separate configuration class so test slices do not inadvertently force caching on.

## 7. Multiple CacheManager Beans: Choosing the Right Manager

In systems with different cache requirements, you may need two beans—for instance, a local cache for categories and a distributed cache for sessions. In that case, you must clearly define which manager is used:

```java
@Configuration
@EnableCaching
public class MultipleCacheConfig {

    @Bean("localCacheManager")
    CacheManager localCacheManager() {
        return new ConcurrentMapCacheManager("categories");
    }

    @Bean("priceCacheManager")
    CacheManager priceCacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
```

This example **only illustrates two managers** using the same implementation; in practice each bean can use a different provider. To make a method select `priceCacheManager`:

```java
@Cacheable(
    cacheNames = "prices",
    cacheManager = "priceCacheManager",
    key = "#p0"
)
public String getPrice(String id) {
    return fetchPriceFromSource(id);
}
```

The snippet above is an **illustrative method**, assuming `fetchPriceFromSource` exists in the service. It does not run standalone. If a service uses the `categories` cache, it can declare `cacheManager = "localCacheManager"` on the corresponding annotation.

Ways to select among multiple managers:

1. **Specify the name on the annotation**: `@Cacheable(cacheManager = "priceCacheManager")` where a specific manager is needed.
2. **Declare a default via `CachingConfigurer`** if you want the caching infrastructure to know the preferred manager/resolver explicitly.
3. **Ensure selection via `@Primary` or appropriate bean configuration** when injection by type is no longer unique; also check how the cache interceptor resolves the manager.
4. **Use `CacheResolver`** when routing rules are complex (dynamically selecting caches based on context), though this is an advanced layer—avoid adding it until necessary.

Do not assume `cacheNames="prices"` automatically finds the right manager between two managers. It is the cache name looked up **inside the already-selected manager**. Identical cache names in two managers can lead to completely different behavior.

### Should @Bean Return the Interface or the Implementation?

Both of the following are valid:

```java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices");
}
```

```java
@Bean
public ConcurrentMapCacheManager cacheManager() {
    return new ConcurrentMapCacheManager("prices");
}
```

Returning the interface makes clear the contract the rest of the application depends on. Returning the concrete type can be useful when autowiring by implementation or when auto-configuration conditions need to see the concrete type. In most simple Spring Cache examples, returning `CacheManager` is sufficient.

## 8. Common Changes and Their Consequences

### Adding a New Cache

If you use the fixed-list constructor:

```java
return new ConcurrentMapCacheManager(
        "prices", "products", "categories");
```

A `@Cacheable(cacheNames = "categories")` method then has a matching store. With the no-arg `new ConcurrentMapCacheManager()`, the manager can create caches dynamically by name as needed; this is flexible, but typos in `cacheNames` become harder to catch.

### Evicting an Entry After a Source Update

When a source price changes, the old cache entry may become stale. In a service, a write method can use:

```java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String productId, int newPrice) {
    repository.updatePrice(productId, newPrice);
}
```

This is an **illustration in a service with a real repository**, not standalone runnable code. By default, `@CacheEvict` runs after the method completes successfully; with database transactions, consider commit timing and cache consistency to avoid re-reading stale values or race conditions. The cache manager does not automatically know source data changed when you write to the database.

### Swapping the Manager in Tests

If you want to test the source path without retaining cache entries, `NoOpCacheManager` can be registered in an appropriate test configuration:

```java
@Bean
CacheManager cacheManager() {
    return new org.springframework.cache.support.NoOpCacheManager();
}
```

This manager satisfies the interface without storing results. Avoid having two beans with the same name in the application context if the project disallows bean overriding; use appropriate test configurations/profiles.

## 9. How to Verify the CacheManager Bean and Caching Path

When debugging, check in this order:

1. **Has the bean been loaded?** Is `CacheConfig` covered by classpath scanning, `@Import`, or registered via `AnnotationConfigApplicationContext`?
2. **Is `@EnableCaching` present?** Simply seeing `@Cacheable` does not mean the interceptor is running.
3. **Is there a matching manager?** Check `context.getBean(CacheManager.class)`; if there are multiple beans, verify bean names or qualifiers.
4. **Does the cache name match?** Does `manager.getCache("prices")` return a cache or `null`?
5. **Does the call go through the Spring proxy?** `new Service()` or `this.getPrice()` inside the same bean bypasses the cache interceptor in default proxy mode.
6. **Is the key stable?** `key="#p0"` uses the first parameter. For `key="#productId"`, Spring must be able to resolve parameter names (typically compiled with `-parameters` on modern Java).
7. **Is there invalidation, TTL expiration, or a backend error?** A miss does not necessarily indicate a wrong annotation configuration.

Inspection snippet inside a component that already has `ApplicationContext context`:

```java
CacheManager cacheManager = context.getBean(CacheManager.class);
System.out.println(cacheManager.getClass().getName());
System.out.println(cacheManager.getCacheNames());
System.out.println(cacheManager.getCache("prices") != null);
```

This is a snippet to drop into a running application; `context` must already be available. With a local cache, logging or counting actual source executions is the easiest way to verify hits/misses. Moving to production, also monitor miss rate, latency, TTL, eviction, memory, backend errors, and stale data.

### Troubleshooting Table

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| No bean of type `CacheManager` | Config class not loaded or `@Bean` not declared | Check component scan, `@Import`, context configuration |
| `NoUniqueBeanDefinitionException` when retrieving manager | Multiple managers exist, injection cannot pick one | Set bean name/`@Qualifier`, `@Primary`, or default caching config |
| `Cannot find cache named 'prices'` | Cache name is not supported by the selected manager | Check `getCacheNames()`, cache name constructor, and annotations |
| Every call runs the method body | Missing `@EnableCaching`, object created via `new`, self-invocation, changing key | Verify Spring proxy and hit/miss behavior |
| Using Spring Boot but cache properties have no effect | Manually declared `CacheManager` bean replaces auto-configuration | Apply config directly on the bean or remove the manual bean |
| `ClassNotFoundException` with Caffeine/Redis | Missing corresponding adapter/provider dependency | Check Maven/Gradle dependency tree and runtime classpath |
| Cache returns stale result after update | Entry not evicted/updated, TTL too long | Design invalidation aligned with data changes and transactions |
| Local demo works but instances return different results | Each JVM has its own cache | Choose a distributed cache or synchronized invalidation when needed |

## 10. Self-Check Questions

1. What is the difference between the bean named `cacheManager` and the cache named `prices`?
2. If you only declare `@Bean CacheManager` without `@EnableCaching`, what happens to `@Cacheable`?
3. Why does the Java example have three `getPrice` calls but only two executions of the source logic?
4. Why can't `new ConcurrentMapCacheManager("prices")` serve the `categories` cache without additional configuration?
5. In Spring Boot, how does declaring a `CacheManager` manually affect auto-configuration and `spring.cache.*`?
6. If there are two `CacheManager` beans, how do you select the right manager for a `@Cacheable` method?
7. Why does `CaffeineCacheManager` require a provider library while `ConcurrentMapCacheManager` works with basic Spring Context?
8. After source data changes, why does merely creating a cache manager bean not guarantee returned data is always fresh?

## 11. Official Documentation for Further Reading

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Enabling Caching Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)

**Key point to remember:** `@Bean CacheManager` defines the provider and caches the application is allowed to use; `@EnableCaching` turns on the annotation infrastructure; `@Cacheable` sets per-method cache lookup rules. Verify the actual bean, cache names, and hits/misses through calls from the Spring container before using in a real environment.