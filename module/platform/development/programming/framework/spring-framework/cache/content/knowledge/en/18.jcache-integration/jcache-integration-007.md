# Standard Configuration vs. Provider-Specific Extensions

**JCache (JSR-107)** is a unified API set for working with Java caches. It solves calling caches through standard interfaces, yet **does not require every cache provider to support the same storage features, performance, eviction policies, or topologies**. When working with Spring Cache, you must distinguish three layers: **Spring Cache Abstraction**, **JCache API**, and **provider-specific configuration** such as Caffeine or Ehcache.

The key question: which parts should be written using **`javax.cache.configuration.MutableConfiguration`** for provider portability, and which parts should use vendor extensions to guarantee capacity, latency, TTL, metrics, and performance? This lesson includes Java 17 + Spring 6.1 + Caffeine JCache code, an integration test, and a provider-migration checklist.

## 1. Layering to Avoid Confusing Responsibilities

~~~text
  Business service: @Cacheable / @CacheResult
                         |
              Spring Cache Abstraction
                         |
              JCacheCacheManager adapter
                         |
 javax.cache.CacheManager / Cache / Configuration
                         |
                JCache CachingProvider
                         |
        Caffeine JCache / Ehcache / other provider
                         |
        Memory, eviction, IO, serialization
~~~

- **Spring Cache**: **`@Cacheable`**, **`@CachePut`**, **`@CacheEvict`**, `CacheResolver`, `KeyGenerator`, and proxy/interceptor determine whether the business method executes on hit/miss. Spring can use **`CaffeineCacheManager`** directly or **`JCacheCacheManager`** to go through JSR-107.
- **Standard JCache**: **`javax.cache.Caching`**, **`javax.cache.CacheManager`**, **`javax.cache.Cache`**, **`MutableConfiguration`**, **`ExpiryPolicy`**, `CacheLoader`, `CacheWriter`, listeners, etc. provide the common API contract. Adding **`cache-api`** alone does not create a real cache store.
- **Provider**: executes storage, memory limits, expiration handling, statistics, persistence, clustering, and extensions. Switching providers does not automatically carry vendor-specific properties across.

**Two concepts must be separated:** choosing the **JCache API** is an interface decision; choosing **Caffeine/Ehcache** is an implementation and operational decision. Spring annotations are yet another distinct choice.

## 2. Portable Configuration with `MutableConfiguration`

**`MutableConfiguration<K,V>`** belongs to the JCache standard. Example (illustrative snippet inside an initialization method with appropriate imports and classpath):

~~~java
import java.util.concurrent.TimeUnit;

import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.Duration;
import javax.cache.expiry.ModifiedExpiryPolicy;

CacheManager manager = Caching.getCachingProvider(
        "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider")
    .getCacheManager();

MutableConfiguration<String, String> config =
        new MutableConfiguration<String, String>()
            .setTypes(String.class, String.class)
            .setStoreByValue(false)
            .setExpiryPolicyFactory(ModifiedExpiryPolicy.factoryOf(
                    new Duration(TimeUnit.MINUTES, 5)))
            .setStatisticsEnabled(true);

Cache<String, String> cache =
        manager.createCache("productNames", config);

cache.put("P01", "Green tea");
String name = cache.get("P01");
~~~

Cache **types**, copy policy, `ExpiryPolicy`, and **`get`/`put`** operations are part of the standard. The **`Caching.getCachingProvider(...)`** call here specifies Caffeine's class to select the runtime implementation; if migrating to Ehcache, swap the dependency and provider selector while verifying the contract. Avoid calling parameterless **`Caching.getCachingProvider()`** when multiple providers coexist on the classpath, as selection may be ambiguous or fail.

**`setStoreByValue(false)`** is a standard option, not a Caffeine-only feature. By default, **`MutableConfiguration`** typically enables **store-by-value**: the cache may copy objects at the API boundary. Store-by-reference can share the same mutable object across callers, affecting thread safety and data isolation. For a specific provider, check **`OptionalFeature.STORE_BY_REFERENCE`**, serialization/copy semantics, and actual support. The demo uses **immutable `String`s** to avoid ambiguity.

### What Belongs to the JCache Contract

| API / Property | Standardization Level | Role |
| --- | --- | --- |
| `CachingProvider`, `Caching`, `CacheManager`, `Cache` | **JCache standard** | Create/look up caches, read, write, delete |
| `MutableConfiguration#setTypes` | **Standard** | Key and value types |
| `setStoreByValue` | **Standard** | Copy values or store references |
| `setExpiryPolicyFactory` | **Standard** | Expiration rules based on create/update/read |
| `setCacheLoaderFactory`, `setReadThrough` | **Standard** | Declare read-through |
| `setCacheWriterFactory`, `setWriteThrough` | **Standard** | Declare write-through |
| `CacheEntryListenerConfiguration` | **Standard** | Observe events |
| `setStatisticsEnabled`, `setManagementEnabled` | **Standard** | Control statistics/management features |
| `Cache.get`, `put`, `remove`, `invoke` | **Standard** | Operations and `EntryProcessor` |
| `maximumSize`, native weigher, cache tiers | **No common property** | Requires provider-specific options |
| Async `refreshAfterWrite`, native ticker, scheduler | **Not common JCache config** | Provider/loader specific |
| Persistence, disk, replication, cluster topology | **Not standardized at the same level** | Depends on provider design |

**Being in the standard ≠ identical performance behavior.** Two providers may support the same `MutableConfiguration` while having different serializers, clocks, synchronization levels, metrics, and trade-offs.

## 3. Especially Easy to Confuse: JCache `ExpiryPolicy` vs. Caffeine TTL

JCache defines these `ExpiryPolicy` types:

| Standard `ExpiryPolicy` | Age Starts At | Events That Reset Age |
| --- | --- | --- |
| **`CreatedExpiryPolicy`** | Entry creation | Not reset on update or read |
| **`ModifiedExpiryPolicy`** | Entry creation | Entry update |
| **`AccessedExpiryPolicy`** | Entry creation | Access/read; updates do not count as access |
| **`TouchedExpiryPolicy`** | Entry creation | Read **or** update |
| **`EternalExpiryPolicy`** | Does not expire by timer | Not applicable |

**`CreatedExpiryPolicy` is not an exact twin of `expireAfterWrite`.** In Caffeine, **`expireAfterWrite`** measures age from creation or value replacement; `CreatedExpiryPolicy` measures age from initial creation, and updates do not reset expiry. **`ModifiedExpiryPolicy`** is closer to `expireAfterWrite` because it resets the duration after updates.

Standard example:

~~~java
MutableConfiguration<String, String> config =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setExpiryPolicyFactory(
            ModifiedExpiryPolicy.factoryOf(
                new javax.cache.expiry.Duration(
                    java.util.concurrent.TimeUnit.MINUTES, 5)));
~~~

Caffeine's native API takes **`java.time.Duration`** instead:

~~~java
Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(java.time.Duration.ofMinutes(5));
~~~

**Do not mix the two `Duration` types:** JCache uses **`javax.cache.expiry.Duration`**, whereas native Caffeine uses **`java.time.Duration`**. Wrong imports cause compilation failures.

`ExpiryPolicy` only governs *expiration*; it is not an automatic background cache-reload job. When an entry expires, lookups miss and a **`@Cacheable`** method may need to run to reload data. **`refreshAfterWrite`** is a separate mechanism, not equivalent to `ModifiedExpiryPolicy`.

## 4. Caffeine JCache Provider-Specific Configuration

Caffeine provides a JCache module and **`com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration`**. This class supports JCache properties and adds Caffeine-specific options.

~~~java
import java.util.OptionalLong;
import javax.cache.configuration.MutableConfiguration;
import com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration;

MutableConfiguration<String, String> portable =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setStoreByValue(false);

CaffeineConfiguration<String, String> vendorConfig =
    new CaffeineConfiguration<>(portable)
        .setMaximumSize(OptionalLong.of(100));

manager.createCache("boundedProducts", vendorConfig);
~~~

**`setMaximumSize`** is a method on **`CaffeineConfiguration`**, absent from `MutableConfiguration`. You still read and write the cache through **`javax.cache.Cache`**: the extension appears only **where the cache is created**, not in business code.

Caffeine also provides options such as **`maximumWeight`/`weigher`**, native `expireAfterWrite`/`Access`, `ticker`, `executor`, `scheduler`, native statistics, and `refreshAfterWrite`. These options only apply with the matching provider/version; configuring refresh requires proper loader/read-through wiring and does not automatically turn Spring annotations into scheduled jobs.

**Caffeine JCache differs from native Caffeine:**

- Using **`Caffeine.newBuilder()`** directly creates a native Caffeine Cache.
- Using **`CaffeineConfiguration`** in JCache still creates caches via **`javax.cache.CacheManager`**.
- Using **Spring `CaffeineCacheManager`** adapts native Caffeine directly without a JCache provider in between.
- Using **Spring `JCacheCacheManager`** adapts JCache via the provider's `javax.cache.CacheManager`.

These paths may use the same underlying engine, yet **they do not automatically share the same cache instance**, keys, config, or entries. Do not see the word "Caffeine" and assume every `CacheManager` points to the same cache.

### Extending via Provider Configuration Files

Caffeine JCache also supports vendor-specific option names in HOCON, shown illustratively:

~~~hocon
caffeine.jcache {
  boundedProducts {
    maximum {
      size = 100
    }
  }
}
~~~

This is **not a generic JCache configuration format**. Verify exact cache names, `application.conf` location, classloader, config source, and precedence of the active provider. Avoid configuring the same cache across multiple conflicting sources and assuming a fixed override order.

## 5. Ehcache and Distributed Providers Have Extensions Too

**Ehcache** configures resource pools such as heap/off-heap/disk via XML or builders depending on version and mode. If you migrate a JCache cache from Caffeine to Ehcache, **`cache.get`**, **`cache.put`**, and `MutableConfiguration` can largely remain intact, while the 100-entry bound must be configured via Ehcache's mechanism rather than `setMaximumSize`.

**Hazelcast, Infinispan, or distributed providers** expose cluster membership, near-cache, partitioning, failover, persistence, and consistency options in their own documentation. JCache has no portable property that makes a cache run across multiple nodes or makes multi-cache updates an atomic transaction.

Distinguish **"JCache API compatibility"** from **"delivering the same load/latency/correctness SLA"**. A new provider can differ in serialization, TTL maintenance, eviction ordering, null caching, statistics, listeners, and timeouts. Compiling cleanly is not enough to prove a migration is valid.

## 6. Spring Annotations and JCache Annotations Are Not Identical

Spring Framework supports both annotation sets, though their semantics are not identical:

| Spring Annotation | JSR-107 Annotation | Important Note |
| --- | --- | --- |
| **`@Cacheable`** | **`@CacheResult`** | JCache adds `skipGet` and exception caching |
| **`@CachePut`** | **`@CachePut`** | Spring puts the **return value**; JCache uses the **`@CacheValue`** parameter |
| **`@CacheEvict`** | **`@CacheRemove`** | Pre/post-invocation eviction and error conditions differ |
| **`@CacheEvict(allEntries = true)`** | **`@CacheRemoveAll`** | Clears the whole cache |
| **`@CacheConfig`** | **`@CacheDefaults`** | Class-level default cache settings |
| **`key = "#p0"`** | **`@CacheKey` / `CacheKeyGenerator`** | Key types may differ |

Illustrative example of both styles:

~~~java
// Using Spring annotation:
@org.springframework.cache.annotation.Cacheable(
        cacheNames = "books", key = "#p0")
public String findSpring(String isbn) {
    return repository.load(isbn);
}

// Using JCache annotation:
@javax.cache.annotation.CacheResult(cacheName = "books")
public String findJcache(@javax.cache.annotation.CacheKey String isbn) {
    return repository.load(isbn);
}
~~~

These snippets are **not standalone for `javac`**, as they need beans/repositories and enclosing classes. More importantly, **Spring SpEL key `#p0` is the ISBN `String`**; the key produced by JCache's default `CacheKeyGenerator` may be a **`GeneratedCacheKey` object**. If both methods share the same cache name, they may fail to hit each other's entries or clash with **`setTypes(String.class, ...)`** constraints. To interoperate, design unified key generation and test rigorously.

Even when using Spring 6 / Jakarta in other APIs, **JSR-107 version 1.1.1 remains in `javax.cache`**, not **`jakarta.cache`**. Spring supports JCache annotations whenever the cache API, `spring-context-support`, and corresponding annotation support are on the classpath.

## 7. Java 17 + Spring Framework Demo: Standard Config and Vendor Extension

This complete example creates two caches through the same **Caffeine JCache provider**: one using pure JCache **`MutableConfiguration`**, and one using **`CaffeineConfiguration`** adding a 100-entry size limit. Spring uses **`JCacheCacheManager`** and two **`@Cacheable`** methods; the test verifies both caches operate independently and Spring + `javax.cache` observe the exact same entries.

**Tech stack:** Java 17, Spring Framework 6.1.14, Caffeine JCache 3.1.8, JCache API 1.1.1, JUnit 5.10.2.

Project structure:

~~~text
spring-jcache-standard-vendor/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/JCacheConfigDemo.java
└── src/test/java/demo/cache/JCacheConfigDemoTest.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-jcache-standard-vendor'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-context-support:6.1.14'
    implementation 'javax.cache:cache-api:1.1.1'
    implementation 'com.github.ben-manes.caffeine:jcache:3.1.8'

    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.JCacheConfigDemo'
}

test {
    useJUnitPlatform()
}
~~~

**`src/main/java/demo/cache/JCacheConfigDemo.java`**

~~~java
package demo.cache;

import java.util.OptionalLong;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.Duration;
import javax.cache.expiry.ModifiedExpiryPolicy;
import javax.cache.spi.CachingProvider;

import com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class JCacheConfigDemo {

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean(destroyMethod = "close")
        public javax.cache.CacheManager jcacheManager() {
            CachingProvider provider = Caching.getCachingProvider(
                    "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
            javax.cache.CacheManager manager = provider.getCacheManager();

            MutableConfiguration<String, String> standard =
                    new MutableConfiguration<String, String>()
                        .setTypes(String.class, String.class)
                        .setStoreByValue(false)
                        .setExpiryPolicyFactory(
                            ModifiedExpiryPolicy.factoryOf(
                                new Duration(TimeUnit.MINUTES, 5)));

            manager.createCache("standardCatalog", standard);

            CaffeineConfiguration<String, String> extended =
                    new CaffeineConfiguration<>(standard)
                        .setMaximumSize(OptionalLong.of(100));

            manager.createCache("extendedCatalog", extended);
            return manager;
        }

        @Bean
        public org.springframework.cache.CacheManager cacheManager(
                javax.cache.CacheManager jcacheManager) {
            return new JCacheCacheManager(jcacheManager);
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger standardLoads = new AtomicInteger();
        private final AtomicInteger extendedLoads = new AtomicInteger();

        @Cacheable(cacheNames = "standardCatalog", key = "#p0")
        public String standard(String id) {
            return "std:" + id + ":load"
                    + standardLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "extendedCatalog", key = "#p0")
        public String extended(String id) {
            return "ext:" + id + ":load"
                    + extendedLoads.incrementAndGet();
        }

        public String loads() {
            return "std=" + standardLoads.get()
                    + ",ext=" + extendedLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                Config.class)) {
            CatalogService service = ctx.getBean(CatalogService.class);
            javax.cache.CacheManager manager =
                    ctx.getBean(javax.cache.CacheManager.class);

            System.out.println("standardFirst="
                    + service.standard("P01"));
            System.out.println("standardHit="
                    + service.standard("P01"));

            System.out.println("extendedFirst="
                    + service.extended("P01"));
            System.out.println("extendedHit="
                    + service.extended("P01"));

            System.out.println("directStandard="
                    + manager.getCache("standardCatalog",
                        String.class, String.class).get("P01"));
            System.out.println("directExtended="
                    + manager.getCache("extendedCatalog",
                        String.class, String.class).get("P01"));

            System.out.println("beforeRemove=" + service.loads());

            manager.getCache("standardCatalog",
                    String.class, String.class).remove("P01");
            System.out.println("standardAfterRemove="
                    + service.standard("P01"));
            System.out.println("afterRemove=" + service.loads());
        }
    }
}
~~~

Run from the project directory with Gradle/JDK 17 or a compatible wrapper:

~~~bash
gradle run --quiet
~~~

Lines printed by **`System.out.println`** in exact order:

~~~text
standardFirst=std:P01:load1
standardHit=std:P01:load1
extendedFirst=ext:P01:load1
extendedHit=ext:P01:load1
directStandard=std:P01:load1
directExtended=ext:P01:load1
beforeRemove=std=1,ext=1
standardAfterRemove=std:P01:load2
afterRemove=std=2,ext=1
~~~

**Explanation:** Two consecutive reads with the same key execute the method body only on the first call. Direct reads via **`javax.cache.Cache.get("P01")`** return the exact data written by Spring's cache interceptor: both layers share the provider's underlying cache store. Calling **`remove`** via JCache deletes only the key in **`standardCatalog`**, so the next Spring call misses and increments the counter to 2; `extendedCatalog` remains independent with count 1.

**Verified scope:** caches created with both standard and extended configurations read and write through the same JCache API, and Spring's adapter uses the right region and key. The demo **does not attempt to prove eviction at exactly 100 entries, exact five-minute TTL expiration, or production performance**; those cases require dedicated tests with a fake ticker or load tests.

### JUnit 5 Integration Test

**`src/test/java/demo/cache/JCacheConfigDemoTest.java`**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(JCacheConfigDemo.Config.class)
class JCacheConfigDemoTest {

    @Autowired
    JCacheConfigDemo.CatalogService service;

    @Autowired
    javax.cache.CacheManager nativeManager;

    @Test
    void standardAndVendorCachesShareTheJCacheApi() {
        assertEquals("std:P01:load1", service.standard("P01"));
        assertEquals("std:P01:load1", service.standard("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("std=1,ext=1", service.loads());

        var standard = nativeManager.getCache(
                "standardCatalog", String.class, String.class);
        var extended = nativeManager.getCache(
                "extendedCatalog", String.class, String.class);

        assertNotNull(standard);
        assertNotNull(extended);
        assertEquals("std:P01:load1", standard.get("P01"));
        assertEquals("ext:P01:load1", extended.get("P01"));

        assertTrue(standard.remove("P01"));
        assertNull(standard.get("P01"));

        assertEquals("std:P01:load2", service.standard("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("std=2,ext=1", service.loads());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expected: the JUnit test passes when dependencies and runtime match. The test obtains the bean from `ApplicationContext`; instantiating **`new CatalogService()`** directly provides no Spring AOP proxy to apply `@Cacheable`. No TTL test is included here to avoid waiting in real time; expiration tests should use a provider ticker or mock clock whenever possible.

## 8. Risks When Switching Providers

**Replacing Caffeine with Ehcache**, code using **`javax.cache.Cache<K,V>`** can keep its signatures, yet the following areas must be revisited:

1. **`CaffeineConfiguration`** no longer works: switch to Ehcache XML or builders for resource pools, sizes, or tiers.
2. **Store by value/reference**: defaults and copy support may differ; verify isolation for mutable objects.
3. **Cache names and key types**: `String` keys vs. `GeneratedCacheKey` generated by JCache annotations may differ.
4. **Expiry semantics**: Created/Modified/Accessed/Touched must be tested across create/update/read boundaries.
5. **Statistics and JMX**: standard flags do not guarantee identical metrics or overhead.
6. **`CacheLoader`/`Writer`**: test failures, retries, and behavior when the backend errors; never enable read-through without a loader.
7. **Concurrency/transactions**: `get`/`put`/remove do not automatically form a distributed transaction.
8. **Multi-node**: local caches and shared caches have different semantics even when the method call is still `Cache.get`.
9. **Exceptions/nulls**: type restrictions and provider null support may differ; never assume nulls can be cached.
10. **Lifecycle**: once the provider/manager closes, entries/handles become unusable; manage startup and shutdown cleanly.

**Merely swapping dependencies until the app compiles is insufficient** to verify business semantics or SLAs. Re-run contract tests.

## 9. Separating Configuration Modules Along Clear Boundaries

One way to organize modules:

~~~text
domain/
  CatalogService.java             # Do not import Caffeine/Ehcache packages
cache-contract/
  CacheNames.java                 # Names and key semantics
infra-jcache/
  StandardJCacheConfig.java       # MutableConfiguration, ExpiryPolicy
infra-jcache-caffeine/
  CaffeineJCacheConfig.java       # CaffeineConfiguration, size, ticker
infra-jcache-ehcache/
  EhcacheConfig.java              # Vendor-specific configuration when switching
tests/
  CatalogCacheContractTest.java   # Runnable against supported providers
~~~

Keep **business services** vendor-independent. When native unwrapping or a highly specific policy is required, place it behind an interface or configuration adapter and document its portability limits clearly. Not all extensions are bad: if a feature like `maximumSize` prevents heap exhaustion, using a well-tested extension is far better than staying "pure JCache" with unbounded memory growth.

**Decision workflow:**

- Prefer the standard API for key/value types, basic expiry policies, events, and loader/writer when sufficient.
- Add extensions when requirements are **measurable**: memory caps, disk persistence, advanced refresh, latency, clustering.
- Document which policies apply only to the current provider and version.
- Select the provider explicitly and verify cache names at startup.
- Test TTL, store-by-value, concurrency, errors, eviction, and lifecycle against the real implementation.
- Track metrics reflecting **freshness and correctness**, not just hit ratio.

## 10. QA Checklist and Common Pitfalls

| Item to Verify | How to Check |
| --- | --- |
| Correct `CachingProvider` | Pass the class name to `Caching.getCachingProvider` and verify the runtime provider |
| Runtime provider present | Do not add only `javax.cache:cache-api` |
| Cache exists with right types | `CacheManager.getCache(name, K.class, V.class)` |
| Spring JCache adapter works | Test `@Cacheable` via Spring-managed bean and compare with `JCache.get` |
| `ExpiryPolicy` actually applies | Test create, update, access, and expired reads at boundaries |
| Size bound works | Populate enough keys, run cleanup/maintenance, and observe policy eviction |
| Copy/serialization | For mutable objects, verify store-by-value vs. store-by-reference |
| Keys on JCache annotations | Compare `GeneratedCacheKey` against Spring SpEL keys |
| Loader and writer | Test source reads/writes, errors, and retries |
| Provider swap | Run the same contract test suite against the replacement provider |

Common mistakes:

- **Confusing Spring `CacheManager` with `javax.cache.CacheManager`**: `JCacheCacheManager` is needed as the adapter when going through JSR-107.
- **Installing only the API without a provider**: there is no concrete cache implementation.
- **Having multiple providers without naming one**: difficult to predict which provider gets chosen.
- **Assuming `maximumSize` is a method on `MutableConfiguration`**: it is not part of the standard JCache API.
- **Confusing `CreatedExpiryPolicy` with `expireAfterWrite`**: `Created` does not reset on updates; `Modified` is closer.
- **Passing `java.time.Duration` to `javax.cache.expiry.Duration`**: wrong API.
- **Allowing Spring and JCache annotations to generate different keys in the same cache**: unexpected cache misses.
- **Assuming JCache API implies distributed caching**: topology and networking architecture must be chosen separately.
- **Enabling store-by-value or read-through without testing copiers/loaders**: prone to runtime errors.
- **Believing `refreshAfterWrite` always runs automatically on schedule**: it still depends on loaders and requests.
- **Testing only the happy path while skipping eviction, failures, concurrency, and transactions**.

## 11. Self-Check Questions

1. Which parts belong to the standard JCache API, and which are Caffeine-specific extensions?
2. Why does **`MutableConfiguration`** not have `setMaximumSize`?
3. How does **`CreatedExpiryPolicy`** differ from **`ModifiedExpiryPolicy`** when overwriting an entry?
4. How does **`AccessedExpiryPolicy`** differ from **`TouchedExpiryPolicy`**?
5. Why does using **Spring `@Cacheable`** with `JCacheCacheManager` not mean you are using JCache `@CacheResult`?
6. If two annotation families produce different key types, what happens when they share one cache?
7. Why must **`storeByValue(false)`** be evaluated carefully with mutable objects?
8. When migrating from Caffeine JCache to Ehcache, which parts of the code stay intact and which must change?
9. What problem occurs if you enable read-through without a valid `CacheLoader`?
10. Why are simple compilation and basic tests insufficient to validate SLAs on a distributed provider?

**Conclusion:** JCache standardizes the read/write cache contract and core policies; providers extend capabilities for memory bounds, persistence, refresh, metrics, and distributed caching. In Spring, use **`JCacheCacheManager`** to bridge the two layers when needed. Keep **business code provider-independent**, use **`MutableConfiguration`** for portable settings, isolate **vendor-specific configuration** in the infrastructure layer, and maintain contract tests when swapping implementations.

### References

- Spring Framework — JCache (JSR-107) annotations: https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html
- Spring Framework — Store configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — `JCacheCacheManager` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html
- JCache — `ExpiryPolicy` API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/expiry/ExpiryPolicy.html
- JCache — `CreatedExpiryPolicy` API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/expiry/CreatedExpiryPolicy.html
- Caffeine — JCache provider overview: https://github.com/ben-manes/caffeine/wiki/JCache
- Caffeine — `CaffeineConfiguration`: https://github.com/ben-manes/caffeine/blob/master/jcache/src/main/java/com/github/benmanes/caffeine/jcache/configuration/CaffeineConfiguration.java
- Caffeine — JCache `reference.conf`: https://github.com/ben-manes/caffeine/blob/master/jcache/src/main/resources/reference.conf
- Ehcache — JCache provider: https://www.ehcache.org/documentation/3.0/107.html
