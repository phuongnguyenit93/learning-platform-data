# Why Spring Cache Is an Abstraction Rather Than a Storage Engine

## Objectives

After this lesson, you will understand what Spring Cache actually handles during a `@Cacheable` call, where cached data resides, why you can swap providers with minimal business-code changes, and which responsibilities around TTL, consistency, concurrency, and distribution the application still has to design.

## 1. A Short but Accurate Answer

**Spring Cache is an abstraction layer for Java method-level caching behavior.** It provides the contract and orchestration mechanism to reuse computation results: determining which methods are cached, deriving keys from parameters, looking up stored results, skipping the method body on a hit, and executing then storing the result on a miss.

**The actual backing store (provider)** is the component holding key/value entries in RAM, inside a single process, or in a remote service; it determines eviction, lifetime, serialization, capacity, persistence, and sharing across instances.

A common point of confusion: Spring Framework also includes a simple storage implementation, `ConcurrentMapCache`/`ConcurrentMapCacheManager`. When you configure this manager, the cache *does* hold data inside a JVM map. However, that only demonstrates that Spring provides **one implementation** of the contract—it does not mean Spring Cache annotations or interfaces themselves are a database.

~~~text
Policy:         @Cacheable -> CacheInterceptor -> Cache / CacheManager (contract)
                                                    |
                                                    v
Implementation: ConcurrentMap, Caffeine, Redis, JCache provider... (where data lives)
~~~

Illustrative policy example:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Price findPrice(String sku) {
    return repository.loadPrice(sku);
}
~~~

The annotation declares that the result of `findPrice(sku)` may be reused under key `sku` in the cache named `prices`. It **does not specify** whether data resides in Redis or RAM, does not configure TTL, and does not create permanent storage. `Price` and `repository` are assumed business types/dependencies: this snippet is for explanation, not a standalone program.

### Boundary of Responsibilities

| Question | Spring Cache Abstraction | Provider / Application |
| --- | --- | --- |
| Which methods are cached? | Annotations such as `@Cacheable`, `@CacheEvict` | Does not decide on its own |
| Which parameters form the key? | SpEL `key` or `KeyGenerator` | Receives the generated/converted key |
| Which operations are invoked? | `Cache` interface: get/put/evict/clear | Executes against actual storage |
| What is the cache region name? | `CacheManager`, `CacheResolver` | Maps to actual region/store |
| RAM or distributed cache? | Unconstrained | Implementation decides |
| TTL, maximum size, LRU, replication? | No universal guarantee | Provider/specific configuration |
| Did database data change? | Does not track automatically | Business logic designs invalidation |
| Which data is the authoritative source? | Does not replace the source of truth | Database / service / business source |

**A cache is not a source of truth.** If every entry disappears, a valid system must be able to reload or recompute from the original data source. Storing critical data solely in a cache destroys recoverability when entries are evicted or expire.

## 2. Components of the Abstraction and Each Party's Role

- `org.springframework.cache.Cache`: interface representing a named cache, supporting retrieving, writing, evicting an entry, or clearing all entries. It does not dictate maps, network connections, eviction, or durability.
- `org.springframework.cache.CacheManager`: returns a `Cache` object by name, e.g., `cacheManager.getCache("prices")`. One manager can manage multiple caches; the name `prices` does not default to a separate database table or Redis server.
- `CacheResolver`: optional component to route operations to appropriate caches instead of always resolving via the default manager.
- `KeyGenerator`: generates default or custom keys. Annotations can specify SpEL `key = "#p0"` to select the first parameter.
- `CacheInterceptor` and Spring AOP: apply the caching policy to calls passing through a Spring proxy. The interceptor does not need to know whether Redis stores bytes or Caffeine stores objects.
- Concrete adapters/providers: `ConcurrentMapCacheManager` (JVM memory), `CaffeineCacheManager` (in-memory cache with eviction policies), Spring Data Redis's `RedisCacheManager` (external Redis), `JCacheCacheManager` (JSR-107).

~~~text
Caller -> Spring proxy / CacheInterceptor
            |
            +-- annotation policy / conditions / cache key
            |
            +-- CacheManager or CacheResolver
            |       |
            |       +-- Cache interface -> provider -> memory/Redis/...
            |
            +-- cache miss -> target method -> repository/API/computation
                                            |
                                            +-- result may be put into cache
~~~

Because business code depends on the **contract**, the application can select the backend via configuration. Even so, provider differences in TTL, serialization, cross-node sharing, and latency still matter operationally.

## 3. Actual Cache Hit and Miss Flow

Suppose a Spring bean has `@Cacheable(cacheNames = "prices", key = "#p0")` and is called by another bean **through a Spring proxy**:

1. The interceptor reads annotation metadata and evaluates `condition` if present. If `condition` is false, the call is not cached.
2. Spring resolves the `prices` cache via the resolver/manager and generates the key for the call.
3. **Hit:** the provider returns the entry for the key; the interceptor returns the stored value and **does not run the method body**.
4. **Miss:** the interceptor runs the target method. On success, if `unless` does not forbid writing, the result is stored through the cache interface and returned.
5. Subsequent calls with the same key can hit, provided the provider still retains the entry and supports that data type.

Conceptual pseudocode, not Spring source code:

~~~text
if condition is not met:
    return invokeTarget()
cache = resolve(cacheName)
key = generateKey(args)
if cache contains key:
    return cache.get(key)
result = invokeTarget()
if unless does not veto:
    cache.put(key, result)
return result
~~~

Spring Cache **does not lock all misses automatically**. If two threads miss the same key simultaneously, both may run the expensive method. `@Cacheable(sync = true)` is a hint asking the provider to coordinate a single load per key; its effectiveness depends on the provider and has restrictions (no `unless`, single cache only). It is not a business-level distributed lock.

A hit also skips any side effects inside the method body: logging, HTTP calls, database writes, charging payments, sending emails, etc. Therefore caching fits computations/reads where repeating results by key is valid; do not blindly attach it to methods that must execute on every invocation.

## 4. Runnable Example with Java 17 and Spring Framework

Minimal example using Spring Framework 6.2.19, Java 17, Maven, and `ConcurrentMapCacheManager`; no Spring Boot, Redis, or database needed. The "slow source" is simulated with a counter so cache hits/misses are visible.

Structure:

~~~text
spring-cache-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

File `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(PriceService.class);

            System.out.println("Call 1: " + service.getPrice("A"));
            System.out.println("Call 2: " + service.getPrice("A"));
            service.invalidate("A");
            System.out.println("After evict: " + service.getPrice("A"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static class PriceService {
        private int loads;

        @Cacheable(cacheNames = "prices", key = "#p0")
        public int getPrice(String sku) {
            System.out.println("Loading from slow source #" + ++loads + ": " + sku);
            return 100;
        }

        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void invalidate(String sku) {
            System.out.println("Evicting key " + sku);
        }
    }
}
~~~

Run from the `spring-cache-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Demo
~~~

Program stdout:

~~~text
Loading from slow source #1: A
Call 1: 100
Call 2: 100
Evicting key A
Loading from slow source #2: A
After evict: 100
~~~

**Walkthrough:** on the first call, key `"A"` is absent so the body executes; on the second call, it hits and the body is skipped; `invalidate("A")` removes the entry; the third call must reload. `@EnableCaching` activates the annotation infrastructure. `getBean(PriceService.class)` ensures calls go through the Spring bean/proxy, whereas `new PriceService()` outside the container would not be intercepted.

The map holding entries belongs to the `ConcurrentMapCache` implementation managed by the manager. That proves the point: annotations and interceptors describe **behavior**, while the provider stores **data**. This example contains no TTL: entries persist until evicted/cleared or the context closes (barring application changes).

## 5. Swapping the Cache Backend: What Stays the Same and What Changes?

The service still keeps `@Cacheable(cacheNames = "prices", key = "#p0")`, yet different managers produce different runtime characteristics:

| Backend | Where Entries Live | Properties to Consider |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | Map in a single JVM | Easy to use, lacks dedicated capacity limits/TTL; each instance keeps its own copy |
| Caffeine | RAM per JVM | Configurable max size, expire-after-write/access, hit/miss statistics |
| Redis | Out-of-JVM service | Shared cache across instances, connections/serializers/network, configurable TTL and eviction |
| JCache provider | Depends on JSR-107 implementation | Actual features depend on provider; Spring uses a JCache adapter |

Example of **changing only the manager configuration** to Caffeine (snippet requires `spring-context-support` and `com.github.ben-manes.caffeine:caffeine` dependencies):

~~~java
@Bean
public CacheManager cacheManager() {
    var manager = new org.springframework.cache.caffeine.CaffeineCacheManager("prices");
    manager.setCaffeine(
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(java.time.Duration.ofMinutes(5))
    );
    return manager;
}
~~~

Keep the methods on `PriceService` unchanged and **replace** the bean—do not define two manager beans for the same purpose. The five-minute TTL here is a Caffeine feature, **not a universal TTL attribute on `@Cacheable`**. If choosing Redis, the application still must configure connections, value format, key prefixes, TTL, network errors, and operations; "unchanged annotations" does not mean "identical runtime behavior".

In Spring Boot, `spring-boot-starter-cache` provides the dependency; once `@EnableCaching` is enabled, Boot can auto-configure a manager from the classpath/configuration if you do not supply your own bean. Boot helps configure the provider, but that does not turn Spring Cache abstraction into a database.

## 6. Annotations Are All About Policy

- **`@Cacheable`:** check cache first; return data on hit, invoke body and optionally write result on miss.
- **`@CachePut`:** always execute body then write the **return value** to the cache when conditions hold; never skips the body on a cache hit.
- **`@CacheEvict`:** requests deleting one key or an entire region via `allEntries = true`; by default evicts after a successful call, or before with `beforeInvocation = true`.
- **`@Caching`:** groups multiple cache operations on a single method.
- **`@CacheConfig`:** centralizes default settings such as cache names at the class level.
- **`@EnableCaching`:** enables annotation processing (proxy mode is typically the default).

Conditional usage example (business snippet requiring real `Price` and `repository`):

~~~java
@Cacheable(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public Price load(String sku) {
    return repository.findPrice(sku);
}
~~~

`condition` is evaluated **before** calling the method; `unless` is evaluated **after** and can veto caching the result. `#p0` refers to the first parameter, avoiding reliance on parameter names in bytecode. `#result` represents the result observable by the post-execution expression.

Default keys when `key` is omitted: no parameters → `SimpleKey.EMPTY`; one parameter → that parameter itself; multiple parameters → `SimpleKey` wrapping the parameters. Thus keys must be stable, have proper `equals/hashCode`, and avoid collisions between operations sharing the same cache name.

Do not unconditionally place `@Cacheable` and `@CachePut` together on the same method: one can skip the body while the other forces execution. Separating read paths and update paths avoids conflicting semantics.

## 7. Guarantees Spring Cache Does Not Make on Its Own

### 7.1. TTL, Memory-Based Eviction, and Persistence

There is no `@Cacheable(ttl = "...")` in the standard API. `Cache.evict(key)` is a request for **proactive deletion**, whereas "expire after 5 minutes", "keep at most 10,000 entries", "LRU", or disk persistence are provider policies. Without configuring TTL, never assume entries will safely expire on their own.

### 7.2. Caching Across Multiple Instances

Two JVM pods both configured with `ConcurrentMapCacheManager` have **two separate maps**. Pod A evicting a key does not clear Pod B's copy. Using Redis lets them view a single store, but you still must design namespaces, invalidation, TTL, security, and handling for slow networks. A shared cache also does not automatically make database results consistent.

### 7.3. Synchronization with the Data Source

If the database changes a price from 100 to 120, the cache can still return 100 because Spring does not know who modified the database out-of-band. You need a suitable write-then-evict or write-through strategy, or a TTL that tolerates staleness.

Illustrative read/write relationship (missing concrete domain/repository):

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Price read(String sku) {
    return repository.findPrice(sku);
}

@CacheEvict(cacheNames = "prices", key = "#p0")
public void update(String sku, Price newPrice) {
    repository.savePrice(sku, newPrice);
}
~~~

Here, the origin write executes first and then eviction runs under default settings. When transactions are involved, **commit timing** still requires attention: eviction might occur before the actual commit, allowing another caller to reload the old value. Post-commit mechanisms or a transaction-aware manager may be needed. Do not assume the cache and database share an atomic transaction by default.

### 7.4. Concurrency, Errors, and Nulls

Multiple threads can miss together, compute redundantly, and overwrite each other. `sync = true` still relies on provider support; it does not promise exactly-once execution or cross-service locking. The cache backend can fail or time out: the application needs fallback strategies and visibility into origin reloads.

`null` values, `Optional.empty()`, and object serialization differ across providers; Spring supports representing null results in some adapters, but do not assume all stores handle them identically. Exceptions thrown by the target method are not successful results cached by default.

### 7.5. Keys and Security

Keys must include all factors determining the output: product, locale, tenant, price tier, access permissions, etc., depending on the problem. Keying only by `productId` when data depends on `tenantId` can return another tenant's data. Control key namespaces, sensitive data, and avoid logging inappropriate values.

## 8. Four Common Mistakes

**(1) "Adding `@Cacheable` makes Spring automatically store in Redis."** False: the annotation does not pick Redis; annotation infrastructure and a matching manager/provider are required. An in-memory manager stores in memory.

**(2) "Calling `this.cachedMethod()` is also intercepted."** Under Spring AOP **proxy mode**, internal calls within the same object bypass the proxy so cache advice does not run. Structure calls to pass through a Spring bean proxy (e.g., extract a service) or consider another weaving mechanism when needed. Methods ineligible for proxying can also miss advice.

**(3) "A cache hit still runs all logic inside the method."** False: a hit skips the body. Do not cache a method with mandatory side effects such as charging money, sending emails, creating orders, or checking permissions against state that changes every second.

**(4) "Switching from ConcurrentMap to Redis will behave identically."** False: latency, cross-instance sharing, TTL, serialization, null handling, failure modes, and eviction are real differences. The abstraction preserves only how you **invoke** caching, not identical backend characteristics.

## 9. How to Self-Check a Real Application

1. Verify `@EnableCaching` (or equivalent configuration) exists and calls to the method pass through a **Spring proxy**.
2. Locate the actual `CacheManager` or `CacheResolver`, inspect dependencies and Boot config; explicitly identify the backend.
3. Inspect each annotation: cache name, key, condition/unless, invalidation, `allEntries`, and origin write paths.
4. Call the same key twice and observe how many times the target method runs; test a new key, and test evict then call again. Do not judge effectiveness merely from the annotation's presence.
5. Check multi-instance needs, TTL, memory bounds, stale data, backend failures, hit/miss metrics, and business-level correctness checks.

## 10. Review Questions

**Why is Spring Cache not a storage engine?** Because it defines the API/annotations/interceptors for method-result reuse behavior; storing key/value pairs is provided by the implementation.

**If two JVMs use `ConcurrentMapCacheManager` and one JVM evicts a key, does the other JVM lose it?** No, maps are local per process.

**Does switching the manager to Redis require rewriting `@Cacheable`?** Usually no; service-level policies can remain unchanged, though you must configure Redis and evaluate TTL, serialization, latency, and connection errors.

**Why did the database update while the method still returns the old value?** Because the cache entry has not been invalidated or expired. Spring Cache does not track all database updates.

**Why did calling twice execute the body both times?** Check proxy/self-invocation, whether keys actually match, `condition/unless`, cache existence, TTL, and the provider.

## Conclusion

**Spring Cache answers "when, and under what key, should a method result be reused?"; the cache provider answers "where is that data kept, for how long, how is it shared, and how does it operate?"** This separation lets you apply one declarative model across many storage technologies, while responsibility for data correctness, invalidation, and backend choice remains with application design.

## Official References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html