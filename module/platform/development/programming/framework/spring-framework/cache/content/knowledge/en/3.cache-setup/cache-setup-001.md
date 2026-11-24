# Required Spring Libraries and Cache Provider Dependencies

> Topic: **Spring Cache Setup**. This lesson explains which libraries must be added to use Spring's cache annotations, which libraries are supplied by the cache provider, and how to configure dependencies properly for each option. The Maven example uses **Spring Boot 4.1.2, Java 17+**; for projects on a different Spring Boot line, keep dependency versions aligned with that line's BOM/parent.

## Objectives

After this lesson, you will be able to:

1. Distinguish **Spring Cache abstraction**, **Spring Boot auto-configuration**, and **cache provider**.
2. Know the roles of `spring-context`, `spring-context-support`, `spring-boot-starter-cache`, along with Caffeine, Redis, and JCache/Ehcache dependencies.
3. Add the right dependencies with Maven or Gradle, avoiding duplicate declarations and version mismatches.
4. Enable caching, choose a provider, inspect the actual `CacheManager`, and troubleshoot common classpath/configuration errors.
5. Run a minimal Spring Boot application to verify that `@Cacheable` actually skips repeated processing.

## 1. Understand the Three Layers in a Caching System

When you see `@Cacheable`, do not assume a single annotation creates a complete cache by itself. The model has three layers:

```text
Business method
    |
    | @Cacheable / @CacheEvict / @CachePut
    v
Spring Cache abstraction
    |  org.springframework.cache.Cache
    |  org.springframework.cache.CacheManager
    v
Specific provider/adapter
    +-- ConcurrentMapCacheManager --> In-JVM Map
    +-- CaffeineCacheManager ----- > Caffeine in-JVM cache
    +-- RedisCacheManager -------- > Redis server
    +-- JCacheCacheManager ------- > JSR-107 provider (e.g., Ehcache 3)
```

- **Spring Cache abstraction** provides the `Cache`/`CacheManager` contracts and the annotation mechanism that decides when to read, populate, or evict the cache.
- **Cache provider** implements how entries are stored, evicted, expired, synchronized, and/or accessed on a cache server. Spring does not by default turn every cache into a distributed cache, give it a TTL, or enforce a capacity limit.
- **Spring Boot auto-configuration** detects existing dependencies and beans and, when conditions match, configures a `CacheManager` automatically. In a plain Spring Framework application (without Boot), you typically declare a `CacheManager` using `@Bean` or XML.

Two independent questions to answer before adding dependencies: **(1) how does the application integrate Spring Cache?** and **(2) where is the data actually cached, and by which library?**

## 2. Core Spring Dependencies

| Maven coordinates | Purpose | When needed |
| --- | --- | --- |
| `org.springframework:spring-context` | Spring Cache APIs, annotations, `ConcurrentMapCacheManager`, and cache configuration support | Core when using plain Spring Framework; usually already included via Spring Boot starters |
| `org.springframework:spring-context-support` | Additional adapters/integrations, notably `CaffeineCacheManager` and `JCacheCacheManager` | When using Caffeine/JCache with manual dependencies; `spring-boot-starter-cache` already brings it in |
| `org.springframework.boot:spring-boot-starter-cache` | Starter for conveniently deploying Spring Cache in a Spring Boot application, including Spring's cache support components | Recommended foundational declaration for Spring Boot applications |
| `org.springframework.boot:spring-boot-autoconfigure` | Boot's conditions and auto-configuration | Usually a transitive dependency from a Boot starter, no need to add manually |
| `org.springframework:spring-aop` | Proxy infrastructure required for method-call interception | Usually already a transitive dependency of Spring Context/starters; **does not mean you must add `spring-boot-starter-aop`** just to use default `@Cacheable` |

**Key takeaway:** `spring-boot-starter-cache` provides the integration infrastructure; it **does not bundle every provider**. To use Caffeine, Redis, or JCache, you must also have the corresponding provider library on the runtime classpath. Conversely, adding only `caffeine` without the Spring adapter will not make `@Cacheable` work on its own.

### Commonly Seen APIs and Classes

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.jcache.JCacheCacheManager;
```

This is a list of **imports for dependency identification**; it is not a standalone program. `CaffeineCacheManager` and `JCacheCacheManager` require `spring-context-support` along with their related API/provider; not every application needs to import both.

## 3. Option 1: Spring Boot + Simple Cache (for Learning and Experimentation)

In a Spring Boot application that already has a parent or BOM managing versions, add the Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
```

Or Gradle Kotlin DSL in a Boot project with dependency management configured:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
}
```

Add Java configuration to enable the annotation mechanism:

```java
@Configuration
@EnableCaching
public class CacheConfig {
}
```

When no dedicated provider is found and no custom `CacheManager` is declared, Spring Boot can select the **Simple provider**, which uses in-JVM `ConcurrentMap` instances. This makes it easy to observe hits/misses, but it **has no preconfigured production eviction/TTL** and does not share cache data across multiple processes. Do not treat it by default as a production solution.

Having annotations on methods alone is not enough if `@EnableCaching` has not been enabled. Furthermore, internal calls via `this.method()` within the same bean do not pass through the Spring proxy in default mode; always invoke through a Spring-managed bean.

## 4. Option 2: Spring Boot + Caffeine (In-Memory, Common for a Single Instance)

Caffeine fits when cache access is very frequent within the same JVM, entry limits and expiration policies are needed, and instances do not need to share values.

### Maven: Add Two Dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL: The Two Corresponding Dependencies

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
    implementation("com.github.ben-manes.caffeine:caffeine")
}
```

In a Boot application with a BOM, you do not need to declare versions for BOM-managed artifacts. `spring-boot-starter-cache` already brings in `spring-context-support`, which contains the `CaffeineCacheManager` adapter.

Example `src/main/resources/application.properties`:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=productPrices
spring.cache.caffeine.spec=maximumSize=200,expireAfterWrite=300s
```

- `spring.cache.type=caffeine` explicitly selects the provider, avoiding reliance on auto-detection order if multiple cache libraries are present.
- `spring.cache.cache-names=productPrices` declares the cache used in the example.
- `maximumSize=200` caps the number of entries according to Caffeine's policy.
- `expireAfterWrite=300s` is the expiration duration measured from the last cache write/update; it does **not** guarantee fresh source data immediately upon change.
- In real projects, consider TTL, eviction, hit-rate metrics, and invalidation strategy based on business requirements.

## 5. Complete, Runnable Example: Spring Boot + Caffeine

The example below creates exactly **one** provider and requires no Redis server or database. It demonstrates caching working through the Spring proxy. Project structure:

```text
cache-dependencies-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/cache/
        │       ├── CacheApplication.java
        │       ├── CacheConfiguration.java
        │       └── CatalogService.java
        └── resources/
            └── application.properties
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-dependencies-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages versions for Spring and common dependencies. The example uses Boot 4.1.2 (released October 2026), but an existing project should stay on the supported patch release of its own Boot line; do not copy a newer Boot version into an older project without checking compatibility.

### 5.2. `src/main/java/example/cache/CacheApplication.java`

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CacheApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(CacheApplication.class, args)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("L1: " + service.getPrice("P42"));
            System.out.println("L2: " + service.getPrice("P42"));
            System.out.println("L3: " + service.getPrice("P43"));

            CacheManager manager = context.getBean(CacheManager.class);
            System.out.println("Manager: "
                    + manager.getClass().getSimpleName());
        }
    }
}
```

### 5.3. `src/main/java/example/cache/CacheConfiguration.java`

```java
package example.cache;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

### 5.4. `src/main/java/example/cache/CatalogService.java`

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceCalls = new AtomicInteger();

    @Cacheable(cacheNames = "productPrices")
    public String getPrice(String productId) {
        int call = sourceCalls.incrementAndGet();
        System.out.println("Loaded from source: " + productId + " (#" + call + ")");
        return "price-" + productId + "-call-" + call;
    }
}
```

### 5.5. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
logging.level.root=OFF
spring.cache.type=caffeine
spring.cache.cache-names=productPrices
spring.cache.caffeine.spec=maximumSize=200,expireAfterWrite=300s
```

### 5.6. Running the Example

Requires JDK 17 or higher, Maven 3.9+, and Maven Central connectivity for the initial dependency download. In the project root directory:

```bash
java -version
mvn -q spring-boot:run
```

The lines **printed by the application code** (excluding any external Maven/runtime messages) appear in this order:

```text
Loaded from source: P42 (#1)
L1: price-P42-call-1
L2: price-P42-call-1
Loaded from source: P43 (#2)
L3: price-P43-call-2
Manager: CaffeineCacheManager
```

**Why is this right?** The first call with `P42` misses, so it runs the method body and writes to the cache. The second call through the Spring bean with `P42` hits, so no additional `Loaded from source` line appears. `P43` is a new key, so it must compute again. The `Manager` line is one way to confirm which provider Spring actually selected. `getPrice` here simulates a data source, not a real database access interface.

If you remove the `caffeine` dependency and the `spring.cache.type=caffeine` line, Boot can fall back to the Simple provider. If you keep `spring.cache.type=caffeine` while the required classes are missing, the configuration is no longer valid; inspect the runtime classpath and startup errors instead of assuming the provider still works.

## 6. Option 3: Spring Boot + Redis (Cache Shared Across Instances)

Redis is a separate storage system that requires a network connection. It fits when multiple application instances need to share a cache region or need centralized invalidation. With Boot, two Maven dependencies are typically used:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

Or Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-cache")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

`spring-boot-starter-data-redis` brings in Spring Data Redis and a Redis client (typically Lettuce) along with their related dependencies. The Spring Cache adapter for Redis is `org.springframework.data.redis.cache.RedisCacheManager`. It is **different from** `org.springframework.cache.caffeine.CaffeineCacheManager` and does not require adding Caffeine.

Example configuration snippet when a Redis server is already reachable:

```properties
spring.cache.type=redis
spring.cache.cache-names=productPrices
spring.cache.redis.time-to-live=5m
spring.data.redis.host=localhost
spring.data.redis.port=6379
```

This cannot be treated as a standalone example like Caffeine: a Redis server must be running and configured for networking, authentication, and TLS if the environment requires them. A Redis cache TTL does not replace deleting keys when source data changes; you must also account for serialization, schema compatibility, key prefixes, connection failures, and network overhead.

**Note:** if `spring.cache.type` is unset and the classpath contains multiple providers, do not guess the provider from the name of the newly added library. Spring Boot has a detection order—for example, JCache may be chosen ahead of Redis or Caffeine in some configurations. Always check the `CacheManager` bean and set `spring.cache.type` explicitly when needed.

## 7. Option 4: JCache (JSR-107) and Providers Like Ehcache 3

**JCache** is a Java caching API standard; it is not a concrete data store. A project that wants to use JCache needs:
1. Spring Cache abstraction + the JCache adapter (in `spring-context-support`, already included by Boot's cache starter).
2. The JCache API along with a `CachingProvider` implementation library.
3. Appropriate cache/provider configuration.

Key coordinates:

```text
org.springframework.boot:spring-boot-starter-cache
javax.cache:cache-api
org.ehcache:ehcache
```

In common JCache versions, the API package remains `javax.cache`; **do not change it to `jakarta.cache`** simply because the application uses a newer Spring version. In practice, `cache-api` is sometimes already pulled in transitively by the provider; if you need to declare it directly, let the BOM manage the version whenever possible.

Example of adding the Ehcache 3 provider in a Boot application that already has the cache starter:

```xml
<dependency>
    <groupId>org.ehcache</groupId>
    <artifactId>ehcache</artifactId>
</dependency>
```

Ehcache 3 includes a JCache provider; depending on the version, Java version, and configuration format, you may need to adjust JAXB dependencies, classifiers, or how XML files are loaded according to Ehcache's documentation. Simply adding the jar does not replace the step of configuring concrete caches. **Do not use Ehcache 2 configuration for Ehcache 3**: they are two different API generations.

Example of some Boot properties:

```properties
spring.cache.type=jcache
spring.cache.jcache.config=classpath:ehcache.xml
```

`ehcache.xml` here must be a configuration resource that **actually exists on the classpath and uses a format supported by the provider**; the property line only illustrates how to wire it up, not that the XML file is generated automatically. If more than one `CachingProvider` is present, you must specify `spring.cache.jcache.provider` with the exact class name for the library in use. Avoid mixing Spring's `@Cacheable` and JCache's `@CacheResult` annotations on the same execution path unintentionally.

### Provider Selection Table by Use Case

| Provider | Primary dependency beyond cache starter | Storage location | Best fit |
| --- | --- | --- | --- |
| Simple (`ConcurrentMap`) | No separate provider jar needed | Within a single JVM | Demos, tests, very simple tasks |
| Caffeine | `com.github.ben-manes.caffeine:caffeine` | Within a single JVM | Local cache, TTL/capacity limits, low latency |
| Redis | `spring-boot-starter-data-redis` | Shared Redis server | Multiple instances, shared cache data |
| Ehcache 3 via JCache | `org.ehcache:ehcache` (+ JCache API if missing) | Per Ehcache/provider config | Requires JSR-107, storage tiers/policies provided by Ehcache |
| Hazelcast / Infinispan / Couchbase | Appropriate vendor dependency and adapter | Per vendor architecture | System already uses that technology and needs Spring Cache integration |

This list does not mean an application should install all of them. **Each example should start from one explicit provider**, adding multiple providers only when there is a genuine multi-tier or multi-cache-type requirement.

## 8. Plain Spring Framework Projects: Manual Dependencies and CacheManager Declaration

If you are **not** using Spring Boot, do not use `spring-boot-starter-cache` or Boot's `spring.cache.*` properties. A plain Spring application can start with:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
```

The XML snippet above assumes the `spring-context` version is already managed in Maven's `dependencyManagement`/Spring Framework BOM; if there is no BOM, you must declare **a specific, consistent Spring Framework version across all modules**. To use the Simple provider, create a `CacheManager`:

```java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("productPrices");
    }
}
```

This is a **configuration class** to place inside an application with a Spring ApplicationContext, not a program with `main`. To use Caffeine manually, add:

```text
org.springframework:spring-context-support
com.github.ben-manes.caffeine:caffeine
```

And replace the cache manager bean with:

```java
@Bean
public CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("productPrices");
    manager.setCacheSpecification("maximumSize=200,expireAfterWrite=300s");
    return manager;
}
```

You need to import `org.springframework.cache.caffeine.CaffeineCacheManager`; the bean snippet belongs inside a `@Configuration` class with `@EnableCaching` enabled. This **illustrates replacing the bean**, not adding it alongside a `ConcurrentMapCacheManager` bean of the same name. When using Redis/JCache in plain Spring, add Spring Data Redis/the JCache adapter along with the provider library and create and configure the corresponding `CacheManager` bean yourself.

## 9. Version Management: Avoiding Conflicting Dependencies

Spring Framework, Spring Boot, and cache providers have a version compatibility matrix. Sustainable management practices:

- **Maven + Spring Boot:** use `spring-boot-starter-parent` or import the `spring-boot-dependencies` BOM. Declare BOM-managed dependencies **without specifying separate version numbers**.
- **Gradle + Spring Boot:** use `io.spring.dependency-management` bundled with the Boot plugin or import the Boot BOM with Gradle's `platform(...)`, matching your existing setup.
- **Plain Spring Framework:** use the Spring Framework BOM and add compatible versions for providers not managed by that BOM.
- Do not attach a newer Spring Framework version to an older Boot release, or force a newer Caffeine/Ehcache version without verifying API/Java compatibility.
- Distinguish dependencies on the **compile classpath** versus the **runtime classpath**: `@Cacheable` can compile even when the runtime lacks the required adapter/provider; many errors surface only during bean creation or cache lookup.

Practical verification commands (run in the project directory):

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework,org.springframework.boot,com.github.ben-manes.caffeine,org.ehcache,javax.cache
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency caffeine --configuration runtimeClasspath
```

On Windows you can run `gradlew.bat` instead of `./gradlew`. The output lets you verify that both adapter and provider are genuinely on the runtime classpath, spot excluded dependencies, forced versions, or multiple coexisting providers.

## 10. Proper Activation and Verifying the Right Provider

All of these conditions must hold simultaneously for caching to actually work:

1. A cache annotation is present on a method of a Spring bean.
2. Annotation processing is enabled with `@EnableCaching`.
3. The call goes through the Spring proxy in proxy mode (specifically, no self-invocation).
4. A `CacheManager` exists that matches the cache name used in the annotation.
5. The provider dependencies are present on the runtime classpath and any external infrastructure (if used) is operational.

### Inspecting the CacheManager Bean

Inside a Spring bean or startup code with access to `ApplicationContext`, you can inspect:

```java
CacheManager manager = context.getBean(CacheManager.class);
System.out.println(manager.getClass().getName());
System.out.println(manager.getCacheNames());
```

Here `context` is an initialized `ApplicationContext`, and `manager` is the bean Spring actually uses. With the Caffeine example above, you expect `CaffeineCacheManager`; with Redis, `RedisCacheManager`. When multiple `CacheManager` beans exist, lookup by type may not be unique; you need to check `@Primary`, bean names, cache resolvers, and application configuration.

### Common Errors and How to Troubleshoot

| Symptom | Possible cause | How to check / fix |
| --- | --- | --- |
| `@Cacheable` is present but the method still runs every time | Missing `@EnableCaching`, self-invocation via `this`, changing key, cache invalidation | Check the proxy, how the bean is obtained, arguments/keys, and cache configuration |
| `CaffeineCacheManager` not found at compile time | Missing `spring-context-support` or project does not use the cache starter | Check modules on the compile classpath |
| Boot picks Simple even though Caffeine is desired | Missing Caffeine jar; or provider not recognized | Check dependencies, `CacheManager`, `spring.cache.type` |
| Added Redis starter but Redis cache is not used | Another provider took precedence, custom `CacheManager` declared, or different `spring.cache.type` | Check auto-config and the actual manager bean |
| Redis application reports connection errors | Incorrect Redis server/host/port/credentials/TLS | Verify Redis connectivity and environment configuration |
| JCache reports provider or cache not found | Missing JCache implementation, multiple providers, or undeclared cache | Check service provider, provider class, config file, and cache name |
| `No cache could be resolved` / `Cannot find cache` | Cache name does not exist in the active provider | Cross-check `@Cacheable(cacheNames=...)` against `spring.cache.cache-names` or vendor config |
| Runs fine but returns stale values | Unsuitable TTL/invalidation | Identify the data source and post-write cache eviction/update mechanism |

Some `spring.cache.*` properties take effect only when Spring Boot auto-configures the corresponding provider. When you define a `CacheManager` bean manually, that provider and bean control the effective configuration; do not assume editing `spring.cache.caffeine.spec` always affects a manually defined bean.

## 11. Choosing Minimal Dependencies per Project

- **Initial demo with Spring Boot:** `spring-boot-starter-cache`, `@EnableCaching`, verify Simple provider.
- **Local cache with capacity limit and TTL:** `spring-boot-starter-cache` + `caffeine`, set `spring.cache.type=caffeine`.
- **Shared cache across multiple instances:** `spring-boot-starter-cache` + `spring-boot-starter-data-redis`, with a Redis server and `spring.cache.type=redis`.
- **JSR-107 required:** `spring-boot-starter-cache` + a JCache provider implementation, verify `javax.cache:cache-api` and provider config; consider Ehcache 3.
- **Plain Spring Framework without Boot:** `spring-context` + required adapter/provider, define `CacheManager` manually, and manage versions via BOM.

A proper dependency list is one that is **just enough for one concrete caching choice**. It should be verified via the dependency tree and the runtime `CacheManager` type, not merely by the project compiling successfully.

## 12. Self-Check Questions

1. What components does `spring-boot-starter-cache` bring in, and why does adding that starter not mean data is already stored in Redis?
2. If you use `CaffeineCacheManager` in a plain Spring Framework application, which modules must you add beyond `spring-context`?
3. Why can't `javax.cache:cache-api` alone replace `org.ehcache:ehcache`?
4. A project has both Ehcache JCache and Caffeine on the classpath: if you want to use Caffeine, what should you configure and verify?
5. Caffeine is caching well on one instance, but three instances are running behind a load balancer: are cached values automatically synchronized?
6. All required dependencies are added, yet `@Cacheable` does not work when calling `this.getPrice(...)` inside the same bean: is the issue in dependencies or in calling through the proxy?
7. Why should you let the Spring Boot BOM manage supported provider versions instead of pinning each jar manually?

## Official Documentation

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Remember:** Spring Cache decides *when* to use the cache; the provider decides *where and how* to store and manage the data; Spring Boot wires the pieces together when dependencies and configuration are right. Choose one provider, add the necessary jars, enable annotations, and verify the `CacheManager` and hit/miss behavior before putting it into service.