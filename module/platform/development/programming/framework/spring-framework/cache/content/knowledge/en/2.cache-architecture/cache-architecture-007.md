# Distinguishing Application Configuration from Cache Store Configuration in Spring Framework

## Lesson Objectives

After this lesson, you will be able to explain what **application configuration** controls, how **Spring Cache infrastructure configuration** wires components together, and how **per-cache store configuration** determines storage policies. You will also be able to identify the right place to configure TTL, capacity limits, provider selection, cache name mapping, and how to verify whether a configuration is actually taking effect.

Scope: Spring Framework Cache Abstraction (the provider-independent API layer), with separate comparisons to Spring Boot when using auto-configuration. This lesson does not assume every Spring Framework project uses Spring Boot.

## 1. Three Configuration Layers in the Architecture

An application can contain multiple named cache stores. For example, product data changes infrequently, whereas exchange rates update rapidly. Even though both use Spring annotations, the two caches require different expiration and capacity policies.

| Layer | What does it decide? | Example | Responsible party |
| --- | --- | --- | --- |
| **Application configuration** | Runtime environment, system connections, business limits, enabling or disabling caching strategies per application needs | Service endpoints, profiles, environment variables, feature flags, policy on whether sensitive information may be cached | Application and operators |
| **Spring Cache infrastructure configuration** | Enables annotation processing; selects CacheManager, CacheResolver, KeyGenerator, ErrorHandler; defines how method calls pass through proxies | @EnableCaching, CacheManager bean, @CachingConfigurer or equivalent config | Spring container and integration configuration code |
| **Cache store configuration (provider / per cache)** | Where data is held, for how long, maximum entries, when items are evicted, whether it is shared across instances, how it is serialized | products: TTL 5 minutes, max 500 entries; rates: TTL 30 seconds, max 100 entries | Caffeine, Redis, Ehcache, or other provider |

In everyday conversation, the first two layers may both be called "application configuration." When designing or troubleshooting, clearly separate **general application configuration**, **Spring Cache integration configuration**, and **cache store runtime policies** so parameters are not placed in the wrong layer.

Simplified flow when calling a `@Cacheable` method:

~~~text
Caller outside the bean
  -> Spring AOP proxy / CacheInterceptor
  -> resolve cache name + key (via CacheResolver / KeyGenerator if needed)
  -> CacheManager retrieves the corresponding Cache
      -> HIT: return stored data
      -> MISS: invoke real method then write result to Cache
  -> provider manages TTL, capacity, item eviction, and storage
~~~

**Boundary rule:** the `@Cacheable` annotation selects the operation, cache name, and key; by itself it **does not** create TTL policies, capacity limits, or a distributed storage model.

## 2. Application Configuration: Usage Intent and General Rules

Application configuration describes how the system operates in each environment. For example, the application calls a product lookup service and allows caching public lookup results briefly. Application-defined properties can be placed in config files, environment variables, or a configuration management system.

~~~yaml
# Example of application-defined properties;
# Plain Spring Framework does not automatically understand or apply the app.* group.
app:
  catalog:
    endpoint: "https://catalog.example.test"
  features:
    catalog-cache-enabled: true
~~~

For the properties above to take effect, **application code must read and use them**, such as via `Environment`, `@Value`, or a configuration bean bound by an appropriate library. Putting an arbitrary key into YAML does not automatically enable Spring Cache or change TTLs.

Examples of application-level decisions:
- Which data types to cache and which not to cache (personal information, tokens, and permission-dependent results require special caution).
- Which read operations to cache to reduce load, and what level of stale data is acceptable.
- When data changes and which business operations must invalidate or update corresponding entries.
- In each environment, whether to store locally or use a store shared across multiple instances.

These decisions **lead to** cache policy choices, but only take storage effect when mapped into concrete provider configuration.

### Enabling Spring Cache and Wiring Components

In a Spring Framework application using annotations, you typically have:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructureConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "rates");
    }
}
~~~

This is an **integration illustration**, not a standalone Java program. The corresponding imports include Spring's `@Configuration`, `@EnableCaching`, `@Bean`, `CacheManager`, and `ConcurrentMapCacheManager`.

- `@EnableCaching` activates cache annotation processing via Spring AOP (proxy-based by default).
- The `CacheManager` bean tells Spring where to look up `Cache` instances by name.
- The names `products`/`rates` here are **logical store names**, not TTLs or maximum counts.
- `ConcurrentMapCacheManager` is backed by in-process memory, suitable for testing or simple cases; it **does not provide TTLs or capacity-based eviction contracts** like a dedicated cache provider.

In plain Spring Framework, declaring an `application.yml` file is **not enough** to auto-create a `CacheManager`. Spring Boot has a separate auto-configuration layer, explained in Section 6.

## 3. Cache Store Configuration: Actual Storage Rules

A **cache store** is a space holding key/value pairs. **CacheManager** manages and supplies those stores; names on `@Cacheable` must resolve to an existing store or one that can be created according to the manager's mechanism.

Parameters typically belonging to cache store/provider configuration:

| Parameter | Meaning | Consequences to know |
| --- | --- | --- |
| **TTL / expireAfterWrite** | Lifetime of an entry since write/update | Avoids holding overly stale data; expiring does not always mean immediate physical deletion |
| **expireAfterAccess** | Expires after a period without access | Continuously accessed items may survive longer than expireAfterWrite |
| **maximumSize / capacity** | Approximate limit on entries that can be held | Provider chooses entries to evict when needed; not a request count limit |
| **Eviction policy** | How entries are chosen for removal when full | Distinct from time-based expiration; provider-dependent |
| **Serialization / key prefix** | Key/value representation, namespace identity | Must stay consistent across app versions when using a remote store |
| **Store topology** | Local per process, distributed/shared, persistence | Affects cross-instance synchronization, deployment, restarts, and latency |
| **Null values / failure behavior** | Whether null is accepted, how cache errors are handled | Depends on Cache implementation, CacheManager, and application policy |

**There is no universal set of TTL or max-size parameters shared across all CacheManagers.** Spring Cache is an abstraction; each provider has its own API and configuration scope. For instance, Caffeine manages caches in the JVM; Redis can hold data on a shared server but requires proper connection, TTL, and serialization configuration.

The same application might need:
- **products**: public data, moderate churn; expire after 5 minutes, keep at most 500 entries.
- **rates**: time-sensitive data; expire after 30 seconds, keep at most 100 entries.

These are **two policies for two different caches**. If you configure one `CaffeineCacheManager` with a single shared config (e.g., `setCaffeine` or `setCacheSpecification`), that config applies to caches created by that manager via that mechanism. To give two names different policies, create each `Cache` with its own builder and register them in `SimpleCacheManager`, or use the official per-cache mechanism of your chosen provider/manager.

### Configuring Individual Caches with Caffeine

An explicit Java pattern is:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCache products = new CaffeineCache(
        "products",
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5))
            .build()
    );

    CaffeineCache rates = new CaffeineCache(
        "rates",
        Caffeine.newBuilder()
            .maximumSize(100)
            .expireAfterWrite(Duration.ofSeconds(30))
            .build()
    );

    SimpleCacheManager manager = new SimpleCacheManager();
    manager.setCaches(List.of(products, rates));
    return manager;
}
~~~

This is a **configuration snippet**; the full standalone program is in the next section. `CaffeineCache` wraps the actual Caffeine library cache and exposes it through Spring's `Cache` interface. `SimpleCacheManager` holds the registered list of caches; `@Cacheable` names must match `products` or `rates`.

Note: Caffeine is a **local in-JVM** cache. If there are three application instances, each instance has its own cached data. Setting the same 30-second expiration does not turn three local caches into one shared cache.

## 4. Runnable Java 17 Example: One Application, Two Distinct Policies

The example below uses **plain Spring Framework without Spring Boot**, Maven, and Java 17+. It simultaneously demonstrates: Spring calls the real method only on a cache miss, two cache names point to two different policy sets, and `@CacheEvict` causes data to be recomputed.

Project structure:

~~~text
spring-cache-scope-demo/
├── pom.xml
└── src/main/java/demo/CacheDemo.java
~~~

**pom.xml** (both Spring artifacts use the same version):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-scope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.4</version>
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

**src/main/java/demo/CacheDemo.java**:

~~~java
package demo;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheDemo {
    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            CaffeineCache products = new CaffeineCache(
                "products",
                Caffeine.newBuilder()
                    .maximumSize(500)
                    .expireAfterWrite(Duration.ofMinutes(5))
                    .build()
            );
            CaffeineCache rates = new CaffeineCache(
                "rates",
                Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofSeconds(30))
                    .build()
            );

            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(products, rates));
            return manager;
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger rateLoads = new AtomicInteger();

        @Cacheable(cacheNames = "products")
        public String product(String id) {
            int n = productLoads.incrementAndGet();
            return "product-" + id + "/load-" + n;
        }

        @Cacheable(cacheNames = "rates")
        public String rate(String currency) {
            int n = rateLoads.incrementAndGet();
            return "rate-" + currency + "/fetch-" + n;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void invalidateProduct(String id) {
            // Actual data source would be updated in the appropriate place.
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.product("42"));
            System.out.println(service.product("42"));
            System.out.println(service.rate("USD"));
            System.out.println(service.rate("USD"));

            service.invalidateProduct("42");
            System.out.println(service.product("42"));
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheDemo
~~~

Five lines written by the program to **stdout** (excluding runner tool logs if any):

~~~text
product-42/load-1
product-42/load-1
rate-USD/fetch-1
rate-USD/fetch-1
product-42/load-2
~~~

Step-by-step explanation:
1. First read of product 42 is a cache miss; the real method runs and increments `productLoads` to 1.
2. Second read is a cache hit; returns the previous string without invoking the real method.
3. First read of USD exchange rate is a miss on the **independent `rates` cache**.
4. Second read of USD is a hit.
5. `invalidateProduct("42")` deletes the corresponding key in `products`, so the next read reloads and increments `productLoads` to 2.

With a single `String` parameter, Spring's default key is that parameter itself; thus `key "#p0"` in `@CacheEvict` matches the entry created by `@Cacheable`. `@Cacheable` and `@CacheEvict` are invoked **from outside through the Spring bean proxy**. The program does not wait past 30 seconds or 5 minutes; it verifies hits and invalidation, while expiration rules are declared by the two Caffeine builders.

### Extended Experiment

You can try changing **only** `maximumSize` or `expireAfterWrite` on `products`, leaving `rates` untouched, then observe behavior when waiting past expiration or generating many keys. This tests configuring **a single store**, without requiring edits to the `@Cacheable` annotation on `rate`. Do not use "after exactly N seconds the entry vanished from physical memory" as a criterion; expiration is observed via operations and the provider's maintenance policy.

## 5. Different Configuration Scopes, Different Results

### 5.1 One Provider, Shared Policy

If the goal is for all caches to share the **same** expiration and capacity, you can configure `CaffeineCacheManager` with a shared Caffeine builder:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "rates");
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
~~~

This is an **alternative approach**, not used simultaneously with the `cacheManager` bean in the full example. Here both `products` **and** `rates` share the same policy. Passing both names to the constructor only defines the two managed caches; it does not create two separate TTLs.

### 5.2 Distinguishing Cache Name, Key, and TTL

Three concepts are frequently confused:
- **cacheNames**: the logical storage location, e.g., `products`. It helps Spring locate the `Cache` via `CacheManager`.
- **key** or `KeyGenerator`: identifies a single entry inside the cache; defaults to method parameters. Can use SpEL like `"#p0"`, and must ensure keys do not mix up data across tenants/users.
- **TTL/maximumSize**: lifetime and capacity policies for entries, configured on the provider.

Changing `@Cacheable(cacheNames = "products")` to `@Cacheable(cacheNames = "rates")` switches the method to **another store**; that action does not modify an existing store's configuration. Conversely, changing the TTL of `products` on the provider usually does not require modifying annotations on each method using `products`.

### 5.3 Default, Class-Level, and Method-Level Configuration

Spring allows declaring integration defaults at the `CacheManager`/`CacheResolver`/`KeyGenerator` level; `@CacheConfig` can group common settings at the **class level**; annotations on **methods** can specify concrete `cacheNames`, `key`, `cacheManager`, or `cacheResolver`. Example:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductReader {
    @Cacheable(key = "#p0")
    public Product find(String id) {
        // business logic (illustrative snippet, not standalone runnable)
        return loadProduct(id);
    }
}
~~~

**`@CacheConfig` has no attributes for setting TTL or maximumSize**. It reduces boilerplate for *binding operations to caches*, not replacing storage configuration. The snippet above illustrates structure; `Product` and `loadProduct` must be defined by the application.

If the application has multiple `CacheManager`s, choose a manager via explicit configuration or use the `cacheManager` attribute on the operation when needed. Never configure both `cacheManager` and `cacheResolver` on the same operation because they are mutually exclusive ways to select caches.

## 6. Plain Spring Framework vs Spring Boot: Different Places to Declare

**Spring Framework** provides interfaces and annotations such as `CacheManager`, `Cache`, `@EnableCaching`, and `@Cacheable`. You explicitly register the required configuration beans.

**Spring Boot** adds auto-configuration and supports standard properties when dependencies, providers, and auto-configuration conditions match. For example, when using Boot with Caffeine and letting Boot create the `CacheManager`:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: "products,rates"
    caffeine:
      spec: "maximumSize=500,expireAfterWrite=300s"
~~~

In this Boot example, **both caches use the same Caffeine spec**. This does not configure a separate TTL for `rates`. If two different TTLs are needed, you must use an appropriate per-cache creation mechanism, such as the `SimpleCacheManager` example in Section 4, or a customizer/mechanism suited to your version/provider.

Pay special attention to the following:
- `spring.cache.*` properties are a **Spring Boot mechanism**, not an inherent feature of plain Spring Framework.
- Once the application provides its own `CacheManager` bean, Boot's default auto-configuration may no longer create or customize the manager as you expect. Check the actual bean in the `ApplicationContext` and the auto-configuration report.
- `@EnableCaching` is still the step that activates annotation processing; having a `CacheManager` or configured properties without enabling annotation caching does not guarantee `@Cacheable` will apply.
- When switching providers (Caffeine -> Redis), do not assume `expireAfterWrite` or `maximumSize` properties apply identically. Check the new provider's API.

## 7. Real-World Architectural Decision Examples

Suppose a system has three kinds of data:

| Data | Staleness tolerance | Technical recommendation | At which layer must decisions be made? |
| --- | --- | --- | --- |
| Public product catalog | Tolerates a few minutes | Cache `products`, TTL around 5 minutes, capacity limit, invalidate on product edit | Business picks acceptable staleness; provider enforces TTL |
| Display exchange rates | Very short tolerance | Cache `rates`, TTL around 30 seconds; source must withstand misses | Business defines freshness; provider enforces |
| Per-user access permissions | Highly sensitive | Generally avoid casual caching; if caching is mandatory, keys need exact context, short TTL, and reliable invalidation | Security rules in app; keys and lifecycle across both layers |

Numbers are only **exercise assumptions** and must be evaluated against real load, SLAs, data churn, and consistency requirements.

With multiple instances:
- **Caffeine** is a per-process local store. Evicting an entry on instance A does not automatically evict the matching entry on instance B.
- **Redis** is typically chosen when a shared store across instances is needed, though you must account for network latency, connection loss, key/prefix config, serializers, and data versioning. A "shared cache" does not automatically guarantee perfect business synchronization.
- Changing provider configuration (TTL, key prefix, serializer) can affect existing cached data; plan migrations and monitor after deployment.

Further distinguish: **expiration** invalidates entries based on time; **eviction** drops entries due to capacity policies; **invalidation** is intentional deletion/update when source data changes. Do not treat all three mechanisms as one.

## 8. Common Mistakes and How to Check

| Symptom / confusion | Possible cause | How to verify or fix |
| --- | --- | --- |
| `@Cacheable` attached yet method runs every time | Missing `@EnableCaching`, self-invocation, bean not going through Spring proxy, method unsupported by proxy | Fetch bean from ApplicationContext, call from another bean; verify `@EnableCaching` and call path |
| Set `cacheNames` yet see no TTL | Cache name does not define an expiration policy | Inspect Cache provider/`CacheManager` config and fetch actual cache via `getCache(name)` |
| Configured one Caffeine spec thinking each cache differs | Shared manager builder/spec applied to all caches | Create each `CaffeineCache` with its own builder or use provider's per-cache support |
| YAML `spring.cache.*` has no effect | Using plain Spring Framework, or Boot custom `CacheManager` replaced auto-configuration | Check framework, active `CacheManager` bean, and configuration report |
| Cache hit occurs yet returns stale data after DB update | Missing `@CacheEvict`/`@CachePut`, mismatched key, invalidation did not propagate across instances | Trace data write events, key, cache name, and provider invalidation capability |
| Entry disappears early or fails to appear on another instance | Cache has size limit, time expiration, or per-JVM local storage | Check eviction/TTL policies and actual topology |
| Wrong data returned across users/tenants | Key only contains data id, omitting tenant or access permissions | Design fully partitioned keys; avoid caching sensitive outputs without proper security boundaries |
| Expected cache name missing | Manager registers fixed names only, while annotation uses a different name | Compare `cacheNames` with `CacheManager.getCacheNames()` list |

Repeatable verification order:
1. **Confirm desired behavior:** which data, acceptable staleness, when invalidation is needed.
2. **Confirm Spring mechanics:** `@EnableCaching`, actual `CacheManager` bean, proxy, `cacheNames`, and key.
3. **Confirm provider and policies:** TTL, capacity, serialization, per-cache-name config, local vs distributed.
4. **Measure at runtime:** call the same key twice to verify hit; update data and verify invalidation; observe hit/miss/eviction metrics if supported by provider and metrics system.
5. **Test multiple instances when needed:** same key across different instances; never infer system-wide consistency from one JVM.

## 9. Self-Check

**Scenario A:** The `ApplicationContext` has a `CacheManager` bean managing `products` and `rates`, but both caches use the same Caffeine configuration `expireAfterWrite(5 minutes)`. Does adding `@Cacheable("rates")` make `rates` automatically expire after 30 seconds?

**No.** The annotation only specifies which cache name to use; TTL remains 5 minutes for both under the shared policy. A dedicated configuration for `rates` must be created on the provider.

**Scenario B:** Changing the `products` TTL from 5 minutes to 1 minute while the method uses `@Cacheable(cacheNames = "products")`. Must the annotation be edited?

**Usually no.** Keeping the same name and manager only changes the policy of `products`. Check how the change is reloaded and the lifecycle of existing entries during deployment.

**Scenario C:** A plain Spring Framework project has `application.yml` containing `spring.cache.caffeine.spec`. Does it automatically enable `@Cacheable` and create a `CaffeineCacheManager`?

**You cannot conclude that.** That is a Spring Boot property convention; plain Spring Framework requires explicit bean configuration and enabling cache annotations.

## 10. Takeaways

- **Application configuration** states goals, environment, and business constraints.
- **Spring Cache integration configuration** enables annotation processing and wires operations to `CacheManager`/`Cache`.
- **Per-cache store configuration** specifies actual storage policies: TTL, capacity, eviction, serializers, and topology.
- **Cache name is distinct from key and distinct from TTL.** To give each store its own policy, use the provider's proper per-cache capabilities.
- Always verify the **running bean and runtime behavior**, especially with Spring Boot auto-configuration, multiple providers, or multiple instances.

### Official Reference Documentation

- Spring Framework – Caching annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Configuring cache storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Boot – Caching auto-configuration (applies only if the project uses Boot): https://docs.spring.io/spring-boot/reference/io/caching.html
