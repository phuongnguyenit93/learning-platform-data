# JCache, Hazelcast, or Infinispan and Required Dependency Scopes

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes integrations via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Cache optimization is part of a broader problem: managing configuration, data contracts, transactions, errors, duplicate handling, testing, and observability across real integration flows.

Suppose the **Catalog Service** calls an HTTP Inventory API and queries PostgreSQL to build `ProductAvailability`. The data is read-heavy and changes infrequently; caching reduces latency and load. Initially, the app uses `ConcurrentMapCacheManager` inside one JVM. Once running across multiple pods, you consider a **clustered/distributed** cache such as Hazelcast or Infinispan, or a standardized API via JSR-107 (JCache) to reduce vendor lock-in.

A very common architectural mistake: the team adds `spring-boot-starter-cache`, `javax.cache:cache-api`, `hazelcast`, `hazelcast-spring`, and `infinispan` simultaneously, expecting Spring to "pick the strongest cache automatically." In reality, **Spring Cache is an abstraction**, **JCache is a specification/API**, and **Hazelcast/Infinispan are providers/technologies** with multiple deployment modes. Each layer has its own dependencies, `CacheManager`, TTL configuration, serialization, clustering, and failure modes.

This lesson belongs to the **Caching** chapter, topic **JCache, Hazelcast, or Infinispan and Required Dependency Scopes**. The focus is not picking the "fastest" product by brand name, but choosing **the right level of abstraction, the right topology, the right dependency scopes, and the right consistency contract** for Spring Boot Integration.

### After This Lesson, You Will Be Able To

1. Distinguish `org.springframework.cache.CacheManager` from `javax.cache.CacheManager`.
2. Understand that JCache/JSR-107 is an API, not an automatic provider, cluster, or Redis replacement.
3. Explain when Spring Boot prioritizes JCache and when `spring.cache.type` is needed.
4. Choose dependency scopes (`implementation`, `runtimeOnly`, `testImplementation`) accurately.
5. Configure JCache with Hazelcast or Infinispan and avoid conflicting providers.
6. Distinguish Hazelcast embedded members, client/server mode, and native Spring Cache integration.
7. Distinguish Infinispan embedded, remote Hot Rod, and JCache integration.
8. Understand cache names, keys, serialization, TTL, eviction, invalidation, and versioning.
9. Design caches aligned with transactions, update APIs, multiple replicas, and timeouts/retries.
10. Test configuration selection, clustered visibility, expiration, connection failures, and metrics.

> **Core principle:** A library named **cache API** does not mean a cache **provider** is present; having a provider does not guarantee Spring Boot selects the **right `CacheManager`**; and a distributed cache does not guarantee instantaneous consistency with the database.

---

## 1. Three Layers to Distinguish Before Adding Dependencies

~~~mermaid
flowchart TD
    A["Business Service"] --> S["Spring Cache abstraction"]
    S --> SC["@Cacheable / @CachePut / @CacheEvict"]
    SC --> CM["org.springframework.cache.CacheManager"]
    CM --> J["JCacheCacheManager adapter"]
    CM --> H["Hazelcast native Spring CacheManager"]
    CM --> I["Infinispan Spring CacheManager"]
    J --> API["JSR-107: javax.cache API"]
    API --> P["JCache CachingProvider"]
    P --> HC["Hazelcast JCache provider"]
    P --> IC["Infinispan JCache provider"]
    H --> HM["HazelcastInstance"]
    I --> IM["Infinispan embedded / Hot Rod remote"]
~~~

### 1.1. Spring Cache: Application-Layer Annotations and Abstraction

Spring Framework defines `org.springframework.cache.Cache`, `org.springframework.cache.CacheManager`, `@Cacheable`, `@CachePut`, `@CacheEvict`, and `@Caching`.

Example:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    public ProductDto findProduct(String productId) {
        return repository.findDto(productId);
    }
}
~~~

`ProductRepository` and `ProductDto` are application types. The annotation mentions neither Hazelcast, Infinispan, nor JCache. It simply asks Spring to look up a `Cache` named `productsById` via `CacheManager`.

`@EnableCaching` is required to enable annotation-driven caching if no other configuration already activates it:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CachingConfiguration {
}
~~~

**Do not confuse:** Having `spring-boot-starter-cache` on the classpath does not ensure `@Cacheable` runs if annotation caching is not enabled. Depending on existing config, Spring Boot auto-configures `CacheManager`, yet never alters proxy invocation semantics.

### 1.2. JCache/JSR-107: Specification and Programming Model

JCache's formal name is **JSR-107, Java Temporary Caching API**. The 1.x API uses the **`javax.cache.*`** namespace (such as `javax.cache.CacheManager`, `javax.cache.configuration.MutableConfiguration`). That package name remains standard even in Jakarta EE–based Spring Boot 3 ecosystems; do not blindly rewrite `javax.cache` imports to `jakarta.cache`.

JCache defines standard interfaces for cache providers: `CachingProvider`, `CacheManager`, `Cache`, expiry configuration, and annotations such as `@CacheResult`, `@CacheRemove`, `@CachePut`, and `@CacheRemoveAll`.

**JCache does not supply a cache implementation by itself.** Adding only `javax.cache:cache-api` without a `CachingProvider` gives you nowhere to store entries.

### 1.3. Hazelcast: Implementation with Multiple Integration Modes

Hazelcast is an in-memory data grid/distributed data structure platform usable via:

- Native Hazelcast APIs (`HazelcastInstance`, distributed `IMap`).
- Native Spring Cache adapter (`HazelcastCacheManager` via Hazelcast Spring integration).
- JCache provider supporting JSR-107, when matching dependencies/versions are used.
- Embedded cluster members running inside Spring Boot processes.
- Thin clients connecting to a standalone Hazelcast cluster.

Do not mix all three APIs inside one service without cause: they can have **different cache names, TTLs, serialization, topology, and lookup behavior**.

### 1.4. Infinispan: Embedded Data Grid and Remote Server

Infinispan likewise offers caching/data-grid capabilities with these integration paths:

- Embedded cache manager and clustered caches running inside the JVM.
- Remote Infinispan Server over the **Hot Rod protocol**.
- Spring Cache integration via version-appropriate adapters/starters.
- JCache provider on supported artifact/version combinations.

Do not treat `infinispan-core` or the Hot Rod client as automatically providing a JCache provider. Choose **embedded/remote/JCache** before deciding dependencies.

---

## 2. Two CacheManagers with the Same Name but Different APIs

This is a dangerous source of confusion when declaring dependencies and `@Bean`s.

| Role | Java type | Who uses it |
| --- | --- | --- |
| Spring cache abstraction | `org.springframework.cache.CacheManager` | Spring `@Cacheable`, `@CachePut`, `@CacheEvict` |
| JCache standard | `javax.cache.CacheManager` | JCache `Cache<K,V>`, provider APIs |
| Bridge between the two layers | `org.springframework.cache.jcache.JCacheCacheManager` | Spring annotations backed by a JCache provider |
| Hazelcast native adapter | `com.hazelcast.spring.cache.HazelcastCacheManager` | Spring annotations backed by `HazelcastInstance` |
| Infinispan Spring adapter | Class supplied by version-specific Spring integration | Spring annotations over embedded/remote |

When injecting:

~~~java
import org.springframework.cache.CacheManager;

@Component
public class CacheInspector {

    private final CacheManager cacheManager;

    public CacheInspector(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public boolean hasCache(String name) {
        return cacheManager.getCache(name) != null;
    }
}
~~~

This is **Spring `CacheManager`**, not the JCache manager. If you need provider-level JCache operations, import `javax.cache.CacheManager` explicitly:

~~~java
import javax.cache.CacheManager;
import javax.cache.Caching;

CacheManager jcacheManager =
        Caching.getCachingProvider().getCacheManager();
~~~

This snippet succeeds only when a **single suitable `CachingProvider`** is present and classloader/provider resolution is unambiguous. Manage manager lifecycles through Spring instead of creating ad-hoc instances across the codebase.

### 2.1. Do Not Import the Wrong `Cache`

- `org.springframework.cache.Cache`: abstraction.
- `javax.cache.Cache<K,V>`: JCache entry operations.
- `com.hazelcast.map.IMap<K,V>`: native Hazelcast distributed map.
- Infinispan `Cache`/`RemoteCache` types: provider-specific.

`IMap` has distinct distributed semantics; do not assume every `IMap` is a JCache cache with identical expiry configuration.

### 2.2. JCache in Spring Cache Is an Adapter, Not Identical Annotations

Spring supports running Spring caching annotations via `JCacheCacheManager`. Spring also supports JCache annotations in compatible versions. However:

- `@Cacheable` is `org.springframework.cache.annotation.Cacheable`.
- `@CacheResult` is `javax.cache.annotation.CacheResult`.
- They differ in key generation, exception caching, and configuration.
- Never place both on one method assuming "double caching under the same key."
- Verify proxy interception and provider-specific behavior.

Within a service, standardize on **one primary annotation programming model**; use adapters when integrating legacy JCache libraries.

---

## 3. Dependency Scopes: An Architectural Checklist

### 3.1. Common Gradle Scopes

| Scope | Use when | Example |
| --- | --- | --- |
| `implementation` | Source code compiles against types; or app requires library | `spring-boot-starter-cache` |
| `runtimeOnly` | Needed only at runtime, not imported in source code | JCache provider discovered via SPI |
| `compileOnly` | Compile against API without bundling at runtime | **Unsuitable** if app runtime needs JCache API and nothing else supplies it |
| `testImplementation` | Used only in test sources | Testcontainers, JUnit |
| `testRuntimeOnly` | Driver/provider present only during test runtime | Test-only provider when testing abstraction |
| Maven `compile` | Similar to `implementation` | Spring cache dependencies |
| Maven `runtime` | Needed only at runtime | Runtime drivers/providers |

A *minimal* dependency graph depends on **which classes your code imports**, **which provider implements the API**, and **whether Boot auto-configures it**.

### 3.2. Rules for Selecting Dependencies

1. Using `@Cacheable` and Spring Cache APIs? Add `spring-boot-starter-cache`.
2. Writing `javax.cache.*` code or using JCache annotations? Add the JCache API on the compile classpath (directly or transitively, yet explicitly controlled).
3. Requiring a JCache manager? A **provider implementation** must exist at runtime.
4. Calling `HazelcastInstance`, `Config`, `IMap`? Put Hazelcast API/implementation on the compile classpath.
5. Calling `HazelcastCacheManager`? Add the compatible Hazelcast Spring integration module.
6. Using Infinispan embedded APIs? Add embedded core + compatible Spring integration.
7. Using remote Hot Rod clients? Add the remote client/starter, standalone server, and auth/TLS.
8. Keep Testcontainers and mock HTTP/broker dependencies in `testImplementation`.
9. When multiple providers coexist, **pin** `spring.cache.type`, explicit `CacheManager` beans, or version-appropriate auto-config exclusions.
10. Never pull in every cache "just to have options": provider detection and the classpath become unpredictable.

### 3.3. Maven/Gradle BOMs and Version Alignment

With the Spring Boot Gradle plugin or dependency BOM, let the BOM resolve versions for Boot-managed libraries. Hazelcast/Infinispan Spring integrations typically require **specific compatibility matrices across provider, Spring Framework, and Spring Boot major versions**.

Never assume `org.infinispan:infinispan-spring-boot3-starter-remote` runs on Boot 4 just because it compiles. Use the exact `boot3` starter or vendor-supported Boot 4 adapter and check release notes.

**Do not blindly exclude `javax.cache` from transitive dependencies** merely because the app uses Jakarta EE: JCache 1.x officially uses `javax.cache`.

---

## 4. Quick Selection Table: Spring Cache, JCache, Hazelcast, Infinispan

| Need | Direction | Minimal role-based dependencies |
| --- | --- | --- |
| Simple single-JVM cache | Spring Cache + Caffeine/simple | Starter + one local provider |
| Swappable provider via JSR-107 | Spring Cache → `JCacheCacheManager` | Starter + `javax.cache` API + one JCache provider |
| Clustered maps and Hazelcast APIs | Native Hazelcast | Starter + Hazelcast + Hazelcast Spring integration if using annotations |
| JCache cluster on Hazelcast | Hazelcast JCache | Starter + JCache API + JCache-capable Hazelcast runtime |
| Infinispan embedded near app | Native Infinispan embedded | Starter + Infinispan embedded Spring integration |
| Shared Infinispan Server cluster | Hot Rod remote | Starter + Infinispan remote Spring integration + server |
| Infinispan JCache | JSR-107 interface over provider | JCache API + compatible Infinispan JCache module/version |
| Shared cache across pods with existing Redis ops | Spring Data Redis CacheManager | Starter + Redis starter/connection config |
| Durable business events | Outbox + Kafka/RabbitMQ | **Never use a cache in place of a message broker** |

**There is no single "best provider."** The decision depends on memory footprint, Kubernetes topology, latency, failover, serialization, security, operational cost, and consistency semantics.

---

## 5. JCache: JSR-107 API and Practical Dependencies

### 5.1. Minimal Dependencies via Spring Cache

An illustrative Gradle configuration for Spring Boot 3.x when choosing JCache:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // JCache API: use when source imports javax.cache.*.
    implementation 'javax.cache:cache-api:1.1.1'

    // Choose EXACTLY ONE provider with a JCache implementation.
    // For example, a compatible JCache-capable Hazelcast version:
    runtimeOnly 'com.hazelcast:hazelcast'
}
~~~

**Version note:** Use the Boot BOM for Boot-managed libraries, or your project's BOM/provider versions. `cache-api:1.1.1` is a widespread JSR-107 1.x API, **not a hard-coded directive for every system**. Whether Hazelcast JCache is included and whether `runtimeOnly` suffices depends on the provider version/SPI; if source code imports `com.hazelcast.*`, you must use `implementation`.

**Common mistake:** adding `javax.cache:cache-api` with no SPI provider → `Caching.getCachingProvider()` finds no provider. Conversely, adding native Hazelcast without JCache API/integration may not cause Boot to auto-create a JCache manager.

### 5.2. Ensuring Boot Selects JCache

~~~yaml
spring:
  cache:
    type: jcache
    cache-names:
      - productsById
      - stockSnapshots
~~~

`spring.cache.type=jcache` makes JCache intent explicit in Boot versions that support it. How `cache-names` are provisioned varies by provider; **do not assume** every provider dynamically creates named caches like Caffeine does. JCache managers often require caches to exist or be configured before `@Cacheable` methods run.

When multiple JCache `CachingProvider`s exist, select one explicitly where supported by your Boot version:

~~~yaml
spring:
  cache:
    type: jcache
    jcache:
      provider: com.hazelcast.cache.HazelcastCachingProvider
~~~

This is the **provider class name for Hazelcast versions that ship it**; verify the actual `CachingProvider` class in your pinned version. Never hardcode an older version's provider class expecting Boot to auto-detect anyway.

### 5.3. JCache Cache Names Must Be Provisioned

A JCache provider may return `null` from `getCache("productsById")` if the cache was never created. When Spring `@Cacheable(cacheNames="productsById")` accesses a missing cache, the call can fail instead of silently creating it.

Example illustrating the JCache API creating a named cache with expiry:

~~~java
import java.util.concurrent.TimeUnit;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.CreatedExpiryPolicy;
import javax.cache.expiry.Duration;

public class JCacheDefinitions {

    public static void ensureProductCache(CacheManager manager) {
        if (manager.getCache("productsById") != null) {
            return;
        }

        var configuration =
                new MutableConfiguration<String, ProductDto>()
                        .setTypes(String.class, ProductDto.class)
                        .setStoreByValue(true)
                        .setExpiryPolicyFactory(
                                CreatedExpiryPolicy.factoryOf(
                                        new Duration(
                                                TimeUnit.MINUTES, 5)));

        manager.createCache("productsById", configuration);
    }
}
~~~

`ProductDto` is an application class. This snippet illustrates **expiry and JCache types**, not complete cluster-safe initialization. If multiple pods create the cache concurrently, `getCache` → `createCache` can race; production should provision caches via provider configuration or Boot customizers with idempotent setup and race/conflict handling per provider API/version.

### 5.4. What Does JCache Expiry Mean?

- `CreatedExpiryPolicy`: TTL counted from entry creation.
- `AccessedExpiryPolicy`: expires based on access per provider semantics.
- `ModifiedExpiryPolicy`: expires after modification per policy.
- `EternalExpiryPolicy`: does not expire by TTL, yet can still be evicted due to memory/resource policies.
- Different providers implement distinct eviction engines, time sources, and cluster replication behaviors.

**TTL is not guaranteed freshness.** For inventory availability, a 5-minute TTL can return stale stock for up to 5 minutes without invalidation. If business logic needs authoritative stock, never rely solely on cached availability checks at reservation time without validating against the DB source-of-truth.

### 5.5. Store-by-Value vs. Store-by-Reference

The JCache specification defines store-by-value semantics depending on config and provider capabilities; `setStoreByValue(true)` typically incurs serialization/copy overhead and requires storable DTO shapes. Store-by-reference (where supported) allows threads to share mutable objects, risking race conditions.

Never cache live JPA entities/session-bound proxies or mutable transaction objects. Cache immutable DTOs/snapshots with explicit versions, TTLs, and size limits.

### 5.6. JCache Annotations Differ from Spring Annotations

Example using a JCache annotation (only when Spring/JCache annotation support is properly configured):

~~~java
import javax.cache.annotation.CacheResult;

public class PricingService {

    @CacheResult(cacheName = "pricingBySku")
    public PriceDto price(String sku) {
        return lookupPrice(sku);
    }
}
~~~

`@CacheResult` differs from `@Cacheable` in key generation/configuration and exception caching. Do not switch from Spring annotations to JCache annotations via search-and-replace without testing cache hits/misses and exceptions.

### 5.7. CacheManager Lifecycle

On application shutdown, providers/JCache managers must close/stop cleanly per Spring lifecycle. Never call `Caching.getCachingProvider().getCacheManager()` ad-hoc on every request. When using a Boot-managed manager, let Boot/Spring manage it; when creating a `@Bean` manually, specify the proper destroy method and avoid duplicate provider instances.

---

## 6. Hazelcast: Choosing Native vs. JCache First

### 6.1. Hazelcast Embedded Member

An embedded Hazelcast member runs **inside the service's JVM**. Multiple pods form a cluster, partitioning/replicating data using discovery and membership. When a pod terminates, data/membership rebalances; capacity depends on member count, backup count, and memory.

Gradle example for native Spring Cache integration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.hazelcast:hazelcast'
    implementation 'com.hazelcast:hazelcast-spring'
}
~~~

Vendors can change artifacts/compatibility across major releases; verify the Hazelcast Spring integration version against your Boot/Spring Framework version. If you only use native `HazelcastInstance` without annotation integration, `hazelcast-spring` may not be needed.

### 6.2. Configuring Native HazelcastInstance + Spring CacheManager

~~~java
import com.hazelcast.config.Config;
import com.hazelcast.config.MapConfig;
import com.hazelcast.core.Hazelcast;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.spring.cache.HazelcastCacheManager;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HazelcastNativeCacheConfiguration {

    @Bean(destroyMethod = "shutdown")
    HazelcastInstance hazelcastInstance() {
        Config config = new Config();
        config.setClusterName("catalog-cache-dev");

        MapConfig products = new MapConfig("productsById");
        products.setTimeToLiveSeconds(300);
        products.setMaxIdleSeconds(120);
        config.addMapConfig(products);

        return Hazelcast.newHazelcastInstance(config);
    }

    @Bean
    CacheManager cacheManager(HazelcastInstance instance) {
        return new HazelcastCacheManager(instance);
    }
}
~~~

This is an **embedded dev/test illustration**, not a production Kubernetes configuration: cluster discovery, ports, network ACLs, TLS, split-brain protection, backup counts, max-size/eviction, security, and rolling upgrades must be designed separately.

`new HazelcastCacheManager(instance)` is native Spring Cache integration; it is **not** `javax.cache.CacheManager`. Do not also set `spring.cache.type=jcache` while defining this native manager unless you have intentionally designed multiple managers.

### 6.3. Spring Boot Auto-Configuration and Custom Beans

When an application defines `@Bean CacheManager`, Spring Boot cache auto-configuration usually **backs off** rather than creating a second default manager. If a JCache provider, Hazelcast native manager, Infinispan, and Caffeine coexist on the classpath, write a test asserting which manager gets injected.

Never set `spring.cache.type=hazelcast` while manually constructing a `JCacheCacheManager` bean and assume configuration still follows YAML: the manual bean dictates behavior.

### 6.4. Hazelcast Client/Server Topology

In client/server mode, Spring Boot instances are not Hazelcast cluster members. Instead, `HazelcastClient` connects to a separately running cache cluster. This topology fits when scaling business pods independently from cache nodes.

~~~mermaid
flowchart LR
    A["Catalog pod A"] --> C["Hazelcast client"]
    B["Catalog pod B"] --> D["Hazelcast client"]
    C --> H["Hazelcast cluster"]
    D --> H
    H --> M1["Data member 1"]
    H --> M2["Data member 2"]
    H --> M3["Data member 3"]
~~~

Clients still depend on network connectivity, cluster membership, connection retries, and credentials. If the cluster goes down, cache reads/writes can throw/time out; decide **fail-open** to DB vs. **fail-closed** per cache semantics.

### 6.5. Hazelcast Native TTL Differs from JCache TTL Config

Hazelcast `MapConfig#setTimeToLiveSeconds` and `setMaxIdleSeconds` configure **native `IMap`**. With the JCache provider, expiry can come from `javax.cache.expiry.ExpiryPolicy` or provider-specific config. Do not assume both configuration paths interact as one unified cache.

### 6.6. Minimal Hazelcast JCache Dependencies

If you chose JCache API to reduce coupling to Hazelcast types:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'javax.cache:cache-api:1.1.1'
    runtimeOnly 'com.hazelcast:hazelcast'
}
~~~

This is an **alternative** to native Hazelcast; `hazelcast-spring` is unnecessary solely to use Spring's JCache bridge if your provider/version suffices. However, some Hazelcast classes/configurations require compile scope if source code imports them directly.

### 6.7. When to Pick Native Hazelcast API?

Pick native when you genuinely need distributed `IMap` operations, entry processors, cluster map listeners, or Hazelcast-specific semantics; in exchange, the application couples to the provider and needs migration reviews.

Pick JCache when you want a standardized cache API and the required features fit within the spec. Never try to force complex cluster transactions/events/partition awareness through JCache abstractions.

---

## 7. Infinispan: Embedded, Remote, and JCache Are Three Separate Paths

### 7.1. Embedded Cache

Embedded Infinispan runs inside the JVM, supporting local and clustered caching depending on mode/membership config. In integration setups, embedded mode can offer very low latency when the team controls cluster topology; however, each business pod acts as a data-grid member.

Gradle **illustration for Spring Boot 3**, vendor-dependent:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // Install the exact starter supported by Infinispan
    // for Spring Boot 3 and your pinned Infinispan version:
    implementation 'org.infinispan:infinispan-spring-boot3-starter-embedded'
}
~~~

Never treat that artifact name as guaranteed to run on Boot 4. Check Infinispan release/version compatibility and your project BOM. If the app uses direct Infinispan APIs without Spring Cache annotations, the provider-specific starter may not be needed.

### 7.2. Remote Hot Rod

Remote mode runs an Infinispan Server cluster and Spring Boot connects via a Hot Rod client. Advantage: decouples cache lifecycle/capacity from business pods; trade-off: introduces network hops, TLS, auth, server HA, data serialization, and protocol compatibility.

Gradle illustration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // Remote starter branch for Spring Boot 3;
    // verify compatibility for your exact release:
    implementation 'org.infinispan:infinispan-spring-boot3-starter-remote'
}
~~~

Connection credentials/server-list properties depend on the Spring Boot starter line and Hot Rod client. To avoid wrong property names, read configuration metadata for **your exact starter/version** when implementing; configure server addresses, TLS CA/hostname, SASL auth, timeouts, topology refresh, and cache names per provider docs.

### 7.3. Infinispan JCache Provider

When preferring `javax.cache` over Infinispan-specific APIs, some Infinispan releases ship a JCache module such as `org.infinispan:infinispan-jcache`, while remote mode may involve different artifacts/capabilities.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'javax.cache:cache-api:1.1.1'

    // Only if this Infinispan release actually supplies
    // a compatible JSR-107 CachingProvider:
    runtimeOnly 'org.infinispan:infinispan-jcache'
}
~~~

**Do not assume every version pair works.** Check implementation compatibility with JCache 1.x and your Spring major version; verify the provider via SPI rather than assuming `infinispan-core` or the Hot Rod client implements JCache.

### 7.4. Infinispan Topologies and Cache Modes

Cache modes such as local, distributed, replicated, or invalidation carry distinct semantics and costs:

| Mode | Concept | Risks/cost |
| --- | --- | --- |
| Local | Entries exist only in local JVM | Each pod sees a different cache |
| Replicated | Replicated across members | Network/memory scales with replicas |
| Distributed | Partitioned + owners/backups | Rebalancing, topology/partition awareness |
| Invalidation | Broadcasts invalidations across nodes | Cache misses still hit source-of-truth |
| Remote Hot Rod | Client calls server cluster | Network/auth/TLS/service availability |

**Do not confuse invalidation mode with shared distributed storage**: in an invalidation configuration, nodes do not necessarily store identical values; they merely invalidate local copies on updates per protocol.

### 7.5. Infinispan Serialization Is Not Automatically JSON

Remote Hot Rod typically requires explicit marshalling schema/protocol policies, such as ProtoStream/Protobuf in modern Infinispan versions. Java-serializable DTOs, JSON HTTP contracts, and Hot Rod ProtoStream encodings **are not automatically interchangeable**.

Especially during rolling deployments:

- Added/removed DTO fields require compatibility tests.
- Never send JPA entities with lazy proxies/session state.
- Classloader/type aliases can render cached values unreadable after deploys.
- Cache key schemas can change too—not only value schemas.
- Prepare versioned keys or explicit migrations/invalidation.

---

## 8. Avoiding Spring Boot Auto-Detection Surprises

When no `CacheManager` is manually declared, Spring Boot auto-configures one from classpath and properties. With multiple providers present, the outcome may surprise the team.

Some Boot 3.x lines prioritize **JCache integration when a provider also has a native implementation**, because JCache offers a standardized API. However, selection order, supported providers, and back-off conditions are **version-specific**; never assume a fixed order across all Boot releases.

### 8.1. Pin the Cache Type Explicitly in Configuration

~~~yaml
spring:
  cache:
    type: jcache
~~~

or a native mode supported by your Spring Boot release:

~~~yaml
spring:
  cache:
    type: hazelcast
~~~

or:

~~~yaml
spring:
  cache:
    type: infinispan
~~~

**Warning:** `spring.cache.type=infinispan`/`hazelcast` works only if auto-configuration support exists in your **Boot + starter/provider** combination. For native Spring integrations configured by third-party libraries, you may need an explicit `@Bean CacheManager` instead of relying on Boot's `spring.cache.type`.

### 8.2. Intentional Multiple CacheManagers

If different domains need different caches, define named `CacheManager` beans and select them on annotations:

~~~java
@Cacheable(
        cacheNames = "stockSnapshots",
        key = "#sku",
        cacheManager = "stockCacheManager")
public StockSnapshot getStock(String sku) {
    return inventory.readStock(sku);
}
~~~

Or declare a `CacheResolver` for complex routing. With multiple managers:

- `@Primary`/qualifiers must be unambiguous.
- Test the actual bean types per environment.
- Cache names/keys must not overlap accidentally.
- Never assume eviction on manager A affects manager B.
- If Spring Cache abstractions and JCache annotations coexist, verify which interceptor/cache manager runs.

### 8.3. Verify the Runtime Type Instead of Guessing

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class CacheManagerDiagnostics {

    public CacheManagerDiagnostics(CacheManager manager) {
        // Log only class name at startup; never log secrets/cache data.
        System.out.println("Spring CacheManager: " +
                manager.getClass().getName());
    }
}
~~~

In production, use structured logging and actuator diagnostics instead of `System.out`; also verify instance count, provider mode, and cluster membership. If you expected a Hazelcast cluster yet received `ConcurrentMapCacheManager`, data exists **only on the current pod**, causing stale reads.

---

## 9. Cache Names, Keys, and Data Scope

A Spring Cache method:

~~~java
@Cacheable(
        cacheNames = "productCatalog",
        key = "#tenantId + ':' + #productId",
        unless = "#result == null")
public ProductDto getProduct(
        String tenantId, String productId) {

    return repository.findProduct(tenantId, productId);
}
~~~

### 9.1. Keys Must Contain No Secrets and Partition Completely

Keys must include **every input affecting the business result**, such as `tenantId`, `locale`, `currency`, `catalogVersion`, and pricing tier where relevant. Omitting `tenantId` leaks tenant A's data to tenant B.

Never put access tokens, raw emails, or PII into keys because keys can surface in metrics, logs, and debug tools. Use approved opaque stable IDs and proper namespacing.

### 9.2. Cache Key/Value Schema Versioning

When schema/semantics change—e.g., v1 stores `amount` in whole units while v2 stores `amountMinor`—version keys:

~~~text
product:v1:tenant-10:sku-100
product:v2:tenant-10:sku-100
~~~

A shared network cache across pods running v1/v2 can contain both formats. Even if JSON parses cleanly, values can carry wrong business units. Versioned keys/serialization adapters and TTL rollouts matter just as much as API contract versioning.

### 9.3. Cache Keys Are Data Contracts Longer-Lived Than a Request

Cached values can survive:

- Rolling deployments and rollbacks.
- DTO package/class renames.
- Failover to another node.
- Multi-day TTLs.
- Persistent stores/passivation or disk tiers (if supported by provider).

If cached data is purely derived, invalidating an old versioned namespace is straightforward. However, invalidating millions of keys simultaneously can trigger a **cache stampede** against PostgreSQL or partner HTTP APIs. Roll out and warm gradually by cohort.

### 9.4. Never Cache Mutable JPA Entities

Cache immutable DTOs:

~~~java
public record ProductSnapshot(
        String productId,
        String displayName,
        long catalogVersion) {
}
~~~

Never cache `EntityManager`, `Connection`, `Session`, mutable transaction contexts, JPA lazy proxies, or authorization-sensitive entities shared across threads or pods.

---

## 10. TTL, Expiry, Eviction, and Consistency

### 10.1. Why "TTL=5 Minutes" Is Not a Freshness Contract

An inventory snapshot with a 5-minute TTL can be nearly 5 minutes stale. If inventory was reserved in the meantime, reading the cache to **perform a reservation** can oversell unless an atomic check runs at the source-of-truth.

Safe candidates to cache:

- Catalog descriptions, product details, versioned feature flags.
- Inventory display snapshots with freshness disclaimers.
- Remote reference data not needing strong consistency.
- Partner HTTP tokens/metadata with explicit TTL contracts and no secret logging.

Never treat stale caches as final truth for:

- Payment balance checks.
- Final inventory deduction.
- Instantaneous authorization/tenant entitlement revocations.
- Distributed locks.
- Unique idempotency records lacking proper persistence.

### 10.2. Expiry vs. Eviction vs. Invalidation Table

| Mechanism | Meaning | What it does not guarantee |
| --- | --- | --- |
| TTL/expiry | Entry expires after duration/policy | DB immediately synchronized |
| Max idle | Entry expires when unaccessed long enough | Business source-of-truth updated |
| Size-based eviction | Provider drops entries under memory pressure | Identical LRU/LFU semantics across providers |
| Explicit eviction | Application proactively deletes key | Atomic eviction with DB COMMIT |
| Event-driven invalidation | Consumer handles change event and deletes/refreshes | Zero lag, zero duplicates, or strict ordering |
| Write-through/write-behind | Provider write policy | Distributed ACID with external DB |
| Refresh-ahead | Reloads before expiry | No extra load/upstream quota usage |
| Versioned key | Switches schema namespace | Real data always fresh |

A cache provider can evict entries due to memory pressure before TTL expires. **TTL is not a minimum retention guarantee.**

### 10.3. Cluster Replication and Stale Values

Distributed caches do not make every read **linearizable** or atomic with the database. Network partitions, failovers, backup replication policies, async persistence, and read-after-write guarantees vary by provider and configuration.

Ask during design:

1. Is the cache cache-aside or authoritative state?
2. What is the maximum tolerable staleness?
3. Should a cache write failure roll back the business transaction?
4. Can node failover drop cache entries?
5. On split-brain, what conflict resolution policy does the cache use?
6. Do stale reads impact money, stock, or permissions?

When strong invariants are required, keep the source-of-truth in a database with proper transactions/constraints; caching is strictly a performance optimization.

---

## 11. Spring Cache Annotations: Understanding Hit/Miss/Update

### 11.1. @Cacheable

~~~java
@Cacheable(cacheNames = "productsById", key = "#id")
public ProductDto get(String id) {
    return database.load(id);
}
~~~

- Cache hit: bypasses method body via proxy.
- Cache miss: executes method, then caches result per policy.
- Key generator/serialization governs identity.
- Exceptions are normally not cached by Spring `@Cacheable` by default.
- `@Cacheable(sync = true)` depends on the `Cache` implementation and **is not synonymous with distributed single-flight across pods**.

### 11.2. @CachePut

~~~java
@CachePut(cacheNames = "productsById", key = "#result.id")
public ProductDto update(String id, ProductPatch patch) {
    return database.update(id, patch);
}
~~~

`@CachePut` always calls the method and updates the cache with the result rather than reading hits. Watch out for null result keys, error paths, and transactional consistency.

### 11.3. @CacheEvict

~~~java
@CacheEvict(cacheNames = "productsById", key = "#id")
public void delete(String id) {
    database.delete(id);
}
~~~

Cache eviction via Spring caching interceptor is not automatically a transaction with the database. If the method throws/rolls back or transaction callback ordering differs from expectations, stale or cold state can result.

### 11.4. Self-Invocation

~~~java
@Service
class ProductService {

    public ProductDto fetch(String id) {
        return cachedFetch(id); // self-invocation: bypasses proxy.
    }

    @Cacheable("productsById")
    public ProductDto cachedFetch(String id) {
        return repository.load(id);
    }
}
~~~

In Spring proxy-based interception, calling `this.cachedFetch` within the same bean bypasses the proxy. Move the cached method to another bean or call through a Spring-managed proxy; never treat a healthy cache provider as proof that annotations are running.

## 12. Transaction Boundary: Cache Update Is Not SQL COMMIT

A typical update:

~~~text
HTTP PUT /products/100
  -> @Transactional service
  -> PostgreSQL UPDATE products
  -> @CachePut / @CacheEvict
  -> SQL COMMIT
~~~

Key question: **Is the cache updated before or after the SQL transaction actually COMMITs?** If a cache put runs before commit, a transaction rollback leaves a cached value **that does not exist in the database**. If commit succeeds yet eviction fails, the cache keeps serving the old value.

### 12.1. Failure Windows to Identify

| Window | Database | Cache | Risk |
| --- | --- | --- | --- |
| Cache put done, SQL rolls back | Old value | New value | Reading uncommitted data |
| SQL COMMIT done, cache eviction fails | New value | Old value | Stale cache |
| App crashes after COMMIT before eviction | New value | Old value | Stale until TTL/next invalidation |
| Invalidation event arrives before COMMIT | Still old value | Cache evicted and reloads old value | Cache repopulated with old value |
| Multiple pods update same key | Final per DB/version | Different arrival order | Cache receives older update after newer |
| Cache cluster partition | DB still commits | Some nodes keep stale value | Divergent reads |

**There is no automatic distributed transaction** between PostgreSQL and Hazelcast/Infinispan just because `@Transactional` and `@CacheEvict` sit on the same method.

### 12.2. Transaction-Aware Spring Cache Decorator

Spring provides `TransactionAwareCacheManagerProxy`/`TransactionAwareCacheDecorator` to **defer certain cache put/evict/clear operations until after transaction commit** when transaction synchronization is active.

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.Bean;

// Assumes delegate is a native/JCache CacheManager you created,
// not this same Spring CacheManager bean.
@Bean
CacheManager transactionAwareCacheManager(
        @Qualifier("providerCacheManager") CacheManager delegate) {

    return new TransactionAwareCacheManagerProxy(delegate);
}
~~~

Snippets in this lesson must be placed inside configurations with complete imports, clear bean names, and **no circular dependencies**. For `@Qualifier`, import `org.springframework.beans.factory.annotation.Qualifier`.

**Limitations:** This decorator does not turn the cache and DB into an ACID transaction. Operations such as `putIfAbsent` have immediate semantics; with `beforeInvocation=true` or alternative annotation ordering, do not assume every eviction is delayed. If eviction fails after SQL COMMIT, the DB remains committed. Include TTL/reconciliation and test rollback/failure windows.

### 12.3. A Safer Path for Critical Data

- DB is the **source of truth**.
- Inside the SQL transaction, update the business row and insert an outbox event with `aggregateVersion`.
- Relay/consumer invalidates/refreshes the cache after COMMIT.
- Cache keys carry tenant/version scope.
- Consumers handle duplicate events idempotently.
- When the cache is unavailable, choose fail-open/fail-closed per semantics.
- TTL is a safety net, not proof every pod observed the update.

~~~mermaid
sequenceDiagram
    participant A as Product API
    participant D as PostgreSQL
    participant O as Outbox worker
    participant C as Cache cluster
    A->>D: BEGIN update product + INSERT outbox
    D-->>A: COMMIT
    O->>D: Claim outbox event
    O->>C: Invalidate product key
    C-->>O: ACK / timeout
    O->>D: Mark event processed or retry
~~~

During a network partition, cache invalidation can fail; the outbox preserves the invalidation intent for retry. If clients read stale caches during the delay, the contract must tolerate eventual consistency or route critical reads straight to the database.

### 12.4. Never Hold a DB Transaction Open Waiting on a Cache Cluster

A transaction can hold DB locks and Hikari connections while waiting on cache network timeouts. For non-critical cache-aside, avoid delaying SQL COMMIT solely to update cache. Keep transaction boundaries short; run retries/outbox/invalidation outside the SQL transaction where appropriate.

---

## 13. Cache Stampede and Thundering Herd

One cache entry is often very hot: `product:tenant-1:SKU-100`. When TTL expires simultaneously across 10 pods, many requests see a miss at once and slam PostgreSQL or the HTTP partner.

~~~mermaid
flowchart TD
    A["Cache key expires"] --> B["10 pods × 100 concurrent requests"]
    B --> M["Cache MISS storm"]
    M --> P["PostgreSQL Hikari pool max 12 per pod"]
    M --> H["Inventory HTTP partner quota"]
    P --> E["Connection wait / timeout"]
    H --> F["HTTP 429 / 503"]
    E --> R["Retries amplify load"]
    F --> R
~~~

### 13.1. Why Increasing Cache Size Alone Does Not Fix This?

Stampede is a **concurrent value-generation** problem, not merely capacity. A key can vanish due to size eviction, TTL expiration, deployment invalidation, or provider failover.

### 13.2. Layered Stampede Mitigation

| Tool | Protection | Notes |
| --- | --- | --- |
| TTL jitter | Spreads expiration times across keys | A single hot key can still suffer concurrent misses |
| `@Cacheable(sync=true)` | Can curb concurrent thread loads **within one cache implementation/local JVM** | Does not guarantee cluster-wide coordination |
| Local single-flight per key | Coalesces same-key requests within a pod | Other pods still fetch independently |
| Distributed lock/lease | Reduces duplicate refreshes across nodes | Complex lease/fencing/failure semantics |
| Stale-while-revalidate | Serves stale snapshot during refresh | Use only if staleness is valid |
| Refresh-ahead | Reloads before expiry | Increases upstream load |
| Bounded HTTP/DB concurrency | Shields downstream pressure | May increase wait times/rejections |
| Prewarming/canary invalidation | Softens cold-start surges | Requires capacity planning |

Never hold a distributed lock across an unbounded network call without timeouts. When a lock/lease expires, two refreshers can overlap; if refresh causes side effects, enforce fencing/idempotency.

### 13.3. @Cacheable(sync=true) Is Not a Distributed Mutex

~~~java
@Cacheable(
        cacheNames = "productCatalog",
        key = "#tenantId + ':' + #id",
        sync = true)
public ProductDto get(String tenantId, String id) {
    return database.load(tenantId, id);
}
~~~

`sync=true` asks the Spring cache abstraction to synchronize value loading where the provider supports `Cache.get(key, Callable)`. Mechanism and strength vary by adapter/provider; **never assume** multiple Hazelcast/Infinispan nodes share a global lock. Write multi-pod integration tests if that is required.

### 13.4. Negative Caching

An API frequently returning 404 for unknown SKUs can cache "not found" to save DB calls, yet needs a short TTL and invalidation semantics if the SKU is created later.

`@Cacheable(unless = "#result == null")` opts **not to cache nulls**, which is not negative caching. To cache "not found," use a sentinel/optional DTO per provider capabilities, and avoid permanently caching a 404 caused by a transient partner error.

---

## 14. Resilience: What to Do When the Cache Is Unavailable?

A Hazelcast/Infinispan cluster can become unavailable due to network partitions, rolling restarts, auth/TLS failures, or capacity exhaustion. Then `@Cacheable` can throw directly during cache read/write operations.

### 14.1. Fail-Open vs. Fail-Closed

| Cache type | Fail-open to DB/source? | Why |
| --- | --- | --- |
| Product descriptions | Usually yes | Cache is strictly a performance optimization |
| Stock UI snapshots | Possible, with bounded DB capacity | Must bound stale data |
| Auth revocation/entitlements | Not by default | Stale reads can cause security bugs |
| Idempotency ledger | **No** if cache-only | Duplicate side effects |
| Distributed locks | **No** | Loss of mutual exclusion |
| Rate-limit counters | Per threat model | Fail-open can allow quota bypass/abuse |
| Cached OAuth tokens | Requires security contract | Exact token expiry/refresh rules |

**Rule:** Fail open only when the source-of-truth is healthy and miss load is bounded. If all pods fall back directly to the DB beyond DB capacity, fail-open turns a cache outage into a full system outage.

### 14.2. Spring CacheErrorHandler: Conditional Fail-Open

By default Spring lets cache errors propagate to callers. For **read-only, optimization-only caches**, you can ignore cache **GET errors** to fall back to the source while still measuring, rate-limiting, and never masking eviction/write errors.

Example:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheErrorPolicy implements CachingConfigurer {

    @Override
    public CacheErrorHandler errorHandler() {
        return new CacheErrorHandler() {
            @Override
            public void handleCacheGetError(
                    RuntimeException exception, Cache cache, Object key) {
                // Redacted logging/metrics here.
                // Swallow GET errors only when the contract permits
                // falling back to the method body with bounded load.
            }

            @Override
            public void handleCachePutError(
                    RuntimeException exception, Cache cache,
                    Object key, Object value) {
                throw exception;
            }

            @Override
            public void handleCacheEvictError(
                    RuntimeException exception, Cache cache, Object key) {
                throw exception;
            }

            @Override
            public void handleCacheClearError(
                    RuntimeException exception, Cache cache) {
                throw exception;
            }
        };
    }
}
~~~

**Do not reuse this configuration verbatim for every cache.** If a `@Cacheable` method runs a very expensive DB query, swallowing cache GET errors can trigger a thundering herd. `CacheErrorHandler` does not fix provider connection retries, transactions, or global consistency.

### 14.3. Timeout Budgets

A request with a 2-second overall deadline cannot spend 3 seconds acquiring cache and 5 seconds querying the database. Configure:

- Cache client connection timeout.
- Socket/read timeout.
- Number of retries/reconnect attempts.
- Fallback source timeout.
- HTTP request deadline.
- Circuit breakers/bulkheads.
- Graceful degraded responses if allowed by contract.

Never retry a cache operation 10 times inside an HTTP request that is also retried 10 times; attempts multiply.

### 14.4. Cache Write Failure After DB COMMIT

If SQL COMMITs yet cache invalidation throws, the client can receive an error even though the business update succeeded. For idempotency-sensitive operations, never retry into a second business command. Use operationIds, persisted receipts, and background invalidation retries. A cache error is a **replica-sync error**, not an automatic undo of the business transaction.

---

## 15. Hazelcast and Infinispan in Kubernetes

### 15.1. Embedded Member vs. Remote Client

~~~mermaid
flowchart TD
    A["Spring Boot pods"] --> E{"Topology?"}
    E --> HM["Embedded members in each pod"]
    E --> RC["Client-server: thin clients in pods"]
    HM --> D1["Pod membership + partition/backup rebalance"]
    RC --> D2["Dedicated cache cluster/service"]
    D1 --> C["Failover, discovery, capacity, security"]
    D2 --> C
~~~

**Embedded** eliminates network hops in certain cases, yet business autoscaling adds/removes cache members simultaneously, forcing partition and backup rebalances. **Remote** separates data-grid lifecycle from business deployments, but depends on Hot Rod/Hazelcast client connectivity and a separately operated cache cluster.

### 15.2. Discovery and Cluster Name

Hazelcast/Infinispan clustering requires node discovery (Kubernetes API, DNS, static addresses, or provider-specific mechanisms). Never use local multicast defaults and expect production K8s to cluster properly.

- Cluster names and discovery configs must match across intended members.
- Isolate dev/test/staging/prod and tenants as required.
- Network policies should allow only required ports/protocols.
- Enable split-brain protection/quorum policies if cache holds unrecoverable state.
- Backup counts must fit actual cache node counts.
- Monitor rebalancing/partition migration during autoscaling.

### 15.3. Multi-Version Deployments

A shared cache cluster can hold values serialized by v1 and read by v2. If Java serialization embeds class/package names, rolling upgrades can fail with `ClassNotFoundException`, `InvalidClassException`, or codec mismatches.

Prefer provider-supported stable schema formats, versioned cache keys/values, and mixed-version upgrade compatibility tests. Never cache JPA entities or mutable classes whose fields silently shift via Lombok.

### 15.4. Resource Accounting

Data-grid members sharing the application JVM contend for heap, CPU, GC, and network. In embedded mode:

- Cache memory must fit inside the business service's heap/GC budget.
- Backup copies/replication multiply total memory.
- Serializing large payloads increases CPU pressure.
- Post-restart cache warmup can spike DB load.
- Partition migrations increase network and CPU usage.
- Max-size/eviction must be configured per provider.

Never size production solely by multiplying `number of keys × average value bytes`: key bytes, metadata, indexes, backup replicas, serialization buffers, and GC overhead matter substantially.

---

## 16. Dependency Conflicts and Classpath Hygiene

### 16.1. Dependencies Often Added Incorrectly

| Dependency | Used for | Does **not** automatically mean |
| --- | --- | --- |
| `spring-boot-starter-cache` | Spring Cache abstraction | JCache provider present |
| `javax.cache:cache-api` | JSR-107 interfaces | Implementation present |
| `com.hazelcast:hazelcast` | Hazelcast engine/API, JCache support per version | Spring native manager always picked |
| `com.hazelcast:hazelcast-spring` | Native Hazelcast Spring integration | Needed when using JCache only |
| Infinispan embedded starter | Spring/Infinispan embedded integration | Connecting to a remote Hot Rod server |
| Infinispan remote starter | Hot Rod remote Spring integration | Embedded cache member |
| `org.infinispan:infinispan-jcache` | JCache provider in supported versions | Works with every Boot/provider combination |
| `hibernate-jcache` | Hibernate second-level caching | Equivalent to Spring `@Cacheable` |
| `spring-boot-starter-data-redis` | Redis data/cache integration | Shares data/TTL with Hazelcast |
| Testcontainers | Integration test infrastructure | Production cache provider |

### 16.2. Hibernate Second-Level Cache Is a Separate Scope

If JPA/Hibernate uses second-level caching via JCache, `hibernate-jcache` may appear. However, **Hibernate L2 cache regions** are not Spring `@Cacheable` regions by default.

- Entity L2 caches have their own persistence-context/region invalidation semantics.
- Query cache is a separate feature with its own invalidation trade-offs.
- Do not turn on L2 caching just because you use Spring Cache.
- One provider cluster can host both, but configure distinct names, TTLs, and quotas.
- Entity updates and Spring business DTO caches do not automatically invalidate each other.

### 16.3. Spring Session Is Distinct from Result Caching

Spring Session has separate backend/session TTL/token isolation rules. Never mix session caches with business result caches merely because both use Hazelcast/Redis/Infinispan. Auth/session state has different security invariants and failover policies from catalog descriptions.

### 16.4. Inspecting Provider SPI When Using JCache

`Caching.getCachingProviders()` can return multiple providers if multiple implementations sit on the classpath. In that case `Caching.getCachingProvider()` lacks an unambiguous business selection; configure the Boot JCache provider property or an explicit provider bean.

~~~java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

for (CachingProvider provider : Caching.getCachingProviders()) {
    System.out.println(
            "JCache provider=" + provider.getClass().getName());
}
~~~

Use controlled startup diagnostics; **never print credentials/config secrets**. If provider count > 1, explicitly select the intended provider per your version.

### 16.5. Dependency Scopes in Tests

If production runs native Hazelcast while unit tests run `ConcurrentMapCacheManager`, run at least one test suite against the real provider:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

For embedded providers, you can spin up 1–2 isolated embedded members in tests. For remote Infinispan, use a compatible container/server instead of mocking APIs; for Hazelcast/Kubernetes multi-node networking, run an isolated integration environment sized for CI capacity.

Do not force every unit test to boot a distributed cluster; separate fast tests from integration tests.

---

## 17. Testing the Right CacheManager and Cache Provider

### 17.1. Asserting the Provider Selected by Boot

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.CacheManager;
import org.springframework.cache.jcache.JCacheCacheManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = "spring.cache.type=jcache")
class JCacheSelectionTest {

    @Autowired
    CacheManager manager;

    @Test
    void usesJCacheBridge() {
        assertInstanceOf(JCacheCacheManager.class, manager);
    }
}
~~~

This test passes only when a **real JCache provider** is on the test/runtime classpath and the manager is not wrapped by a custom bean or transaction-aware wrapper. If wrapped in `TransactionAwareCacheManagerProxy`, asserting the direct class fails even though the delegate is JCache; inspect the wrapper/delegate in that test setup.

Never mock `CacheManager` in this test since its purpose is verifying **provider selection**.

### 17.2. Testing Cache Hit/Miss Through the Spring Proxy

Tests should call the **proxied Spring bean**, not `new ProductCatalogService(repository)` expecting `@Cacheable` to run.

~~~text
Given cache productsById is provisioned
And repository holds a product DTO
When Spring bean getProduct("P-100") is called twice
Then repository is invoked once per contract
And both results are equal
~~~

If a method self-invokes, proxy interception is skipped; testing the method directly can miss that bug.

### 17.3. Testing TTL/Expiry Without Ultra-Short Sleeps

~~~text
Given cache TTL 5 seconds
When writing product P-100 at t0
Then before expiry read => HIT
And after expiry => MISS/reload
~~~

Use provider clock/test support where available; when integration tests must wait for real TTLs, set generous timeouts and margins to avoid flakiness; never use `Thread.sleep(5)` and assert expiration.

JCache `CreatedExpiryPolicy` and Hazelcast native map TTL have different semantics—test on the actual provider.

### 17.4. Testing Clustered Visibility

~~~text
Given instance A and instance B sharing cluster/namespace
When A puts cache entry K
Then B reads K per published consistency contract
When A evicts K
Then B does not serve stale data beyond allowed window
~~~

Testing one JVM with one manager does not prove distributed caching. Two JVMs/pods/clients may be needed to rule out accidental local fallbacks.

### 17.5. Testing Cross-Version Serialization

~~~text
Given v1 application writes ProductSnapshotV1 into shared cache
When v2 application reads the same key
Then decode into valid data or intentionally MISS/migrate
And preserve currency/unit/business semantics
~~~

Likewise, rolling back v2 → v1 must account for values written with the newer serializer. Do not declare rolling upgrades safe solely because v2 reads data written by v2.

### 17.6. Testing Cache Outages and DB Fallbacks

- Block cache cluster connections using a fault/network proxy.
- Send cacheable read queries.
- Verify timeout/fallback matches policy.
- Confirm no unbounded queues or retry storms.
- Ensure Hikari pending connections and partner HTTP QPS stay within budget.
- For auth/idempotency-sensitive caches, verify fail-closed.
- When the cache recovers, verify no stale-data overwrite occurs after concurrent updates.

---

## 18. Testing SQL Transactions and Invalidation

### 18.1. Rollback Scenario

~~~text
Given P-100 version=3 in PostgreSQL and cache
When transaction updates P-100 to version=4
And SQL rolls back
Then PostgreSQL remains version=3
And cache must not expose version=4 as committed
~~~

When using `TransactionAwareCacheManagerProxy`, test both commit/rollback and operations that are not deferred. Never rely solely on seeing `@Transactional` to assume transaction ordering is right.

### 18.2. Commit Then Cache Outage

~~~text
Given P-100 version=3 in cache
When SQL COMMITs version=4
And cache invalidation fails due to cluster outage
Then durable invalidation intent remains pending
And business transaction is not executed twice
When cache recovers
Then consumer invalidates/refreshes key
And stale version=3 does not exceed consistency SLA
~~~

Outbox relays should carry `aggregateVersion` and stable `eventId`; for out-of-order invalidations, enforce version guards or tombstone policies.

### 18.3. "Cache Hit" Is Not Business Success

In Spring Boot Integration, a cached `InventoryStock` **does not confirm** sufficient stock to reserve right now. Reservations require an atomic check/transaction at the authoritative DB; caching should only serve display/estimation under an explicit freshness contract.

---

## 19. Observability and Capacity Planning

Metrics may be exposed by Micrometer/Actuator, Hazelcast Management Center, or Infinispan monitoring **depending on versions and settings**. Never assume the framework exports every signal automatically.

| Metric/signal | Purpose |
| --- | --- |
| Cache hit/miss ratio per cache | Cache effectiveness |
| Cache entry count/size | Memory/capacity |
| Cache evictions/expirations | Capacity pressure/TTL behavior |
| Cache load time p95/p99 | Cache miss cost |
| Cache get/put/remove errors | Cluster availability |
| Active cluster members/topology | Health/quorum |
| Network RTT/timeouts/reconnects | Remote clients |
| Serialization errors | Schema incompatibility |
| Per-key stampede suppression count | Duplicate loads |
| Hikari connections active/pending | Downstream DB pressure |
| HTTP partner 429/503 | Cache miss overload |
| Business stale-read detections | Consistency impact |
| Outbox invalidation lag | Cache sync delay |
| Rate of fallback reads | Cache failure blast radius |

### 19.1. Avoid High-Cardinality Tags

Reasonable:

~~~text
cache=productsById
provider=hazelcast
outcome=hit|miss|error
operation=get|put|evict
service=catalog
~~~

Never put `productId`, high-cardinality `tenantId`s, emails, access tokens, or raw payloads into Prometheus labels. Correlation IDs belong in structured logs with retention/access controls.

### 19.2. Alert on System Health, Not Hit Rate Alone

A drop in hit rate may simply reflect a deployment/cold cache rather than an outage. However, if cache misses rise simultaneously with Hikari pending connections and HTTP 503s, a **cache miss storm is impacting the backend**.

Alert holistically on:

- Cache availability.
- Downstream saturation.
- Business latency p95/p99.
- Stale values exceeding SLA.
- Invalidation backlog age.
- Cluster member restarts/rebalancing.

### 19.3. Sizing

Estimate:

~~~text
Raw values:
  1 million keys × average 2 KiB ≈ ~2 GiB raw values

Real memory must include:
  key bytes + metadata + serialization overhead
  backup replicas + indexes + fragmentation/GC
  near cache copies (if enabled)
  network buffers and eviction headroom
~~~

Never use `number of keys × average value bytes` as your sole production sizing calculation. Measure with provider tools, load-test representative datasets, and budget for cluster failover on member loss.

---

## 20. Symptom-Based Runbook

| Symptom | Likely cause | Check step |
| --- | --- | --- |
| `@Cacheable` does not cache | Missing `@EnableCaching`, self-invocation | Proxy, annotation scanning |
| Bean is `ConcurrentMapCacheManager` | Auto-config fell back to local | Runtime `CacheManager` type, classpath |
| JCache provider not found | API present without provider | SPI `Caching.getCachingProviders()` |
| Multiple `CachingProvider`s | Hazelcast + Infinispan both on classpath | Explicit `spring.cache.jcache.provider` |
| `Cannot find cache named X` | JCache cache not provisioned | Cache names, provider config |
| Cache TTL differs from expectation | Native vs. JCache expiry config mismatch | Actual provider/mode |
| Hazelcast members do not discover each other | K8s discovery/network/cluster name | Cluster membership, ports |
| Cache values lost after pod restart | Local/embedded without proper backup | Topology/mode/backup |
| Infinispan remote timeout | Hot Rod server/TLS/auth/network | Remote client config |
| `ClassNotFoundException` on deserialize | Mixed schema/classloader versions | Versioned cache keys/codecs |
| Stale product after SQL COMMIT | Eviction failure/race/async invalidation lag | Outbox/TTL/version guard |
| DB overload when cache fails | Fail-open stampede | Bulkhead, stale policy, warming |
| CPU/GC spike | Serialization, huge values, members in app JVM | Heap, payloads, cache size |
| Cache holds keys from another tenant | Missing tenant in cache key | Key contract, security incident |
| Hikari pending rises when key expires | Hot-key stampede | Per-key single-flight + limits |
| Added Hibernate JCache, `@Cacheable` misses | Confused L2 cache with Spring Cache | Separate cache layers |
| Rolled-back service fails reading new cache | Wire/schema compatibility | Key namespace/versioning |
| Cluster split brain | Network partition/health | Quorum/conflict policy |

### 20.1. Investigation Order

1. Identify the use case: query cache, session, Hibernate L2, idempotency store, or distributed lock?
2. Inspect the actual **Spring `CacheManager` class** and provider SPI.
3. Verify cache names and actual JCache/native configurations.
4. Confirm topology: local, embedded clustered, or remote client/server.
5. Inspect TTL/eviction/serialization and cache key contracts.
6. Check DB/source-of-truth state and transaction commits.
7. Measure cluster networking, provider health, and SSL/authentication.
8. Correlate cache hits/misses/errors with Hikari/HTTP partner saturation.
9. Check outbox/invalidation lag and stale-read SLA.
10. Reproduce in an integration environment; never experiment on production cache clusters without authorization.

---

## 21. Anti-Patterns to Avoid

| Anti-pattern | Why is it wrong? | Alternative |
| --- | --- | --- |
| Adding only `javax.cache:cache-api` expecting a cache | API without provider | Add one JCache implementation/runtime |
| Pulling Hazelcast and Infinispan into one app needlessly | Ambiguous provider detection | Pick one explicit implementation/manager |
| Importing wrong `CacheManager` package | Two APIs share the same name | Fully qualify / use qualifiers |
| Using `runtimeOnly` while source imports Hazelcast classes | Compile cannot see types | Use `implementation` |
| `@Cacheable` without `@EnableCaching` | Interception disabled | Enable caching |
| Self-invoking a cached method | Bypasses Spring proxy | Call through another bean |
| Failing to provision JCache cache names | Missing cache at runtime | Provider config/customizer |
| Mixing native TTL with JCache `ExpiryPolicy` | Two separate APIs/configs | Standardize on one provider/mode |
| Caching attached JPA entities | Lazy proxies/mutable state | Immutable DTOs |
| Omitting tenant from keys | Cross-tenant data leak | Complete key contract |
| Using cache as sole idempotency ledger | Eviction/restarts cause duplicates | SQL UNIQUE + receipt |
| Using cache locks instead of DB invariants | Split brain/lease expiry | Fencing/DB constraints |
| Updating cache before SQL COMMIT | Rollback leaves stale new value | After-commit/outbox |
| Eviction fails yet strong consistency assumed | DB/cache divergence | TTL + reliable invalidation |
| Treating `@Cacheable(sync=true)` as a cluster mutex | Not guaranteed | Per-provider testing/bulkheads |
| Failing open on all cache exceptions | DB storms/security bugs | Per-cache failure policy |
| Identical TTLs on all hot keys | Miss storm | Jitter/prewarming/single-flight |
| Dropping v1 decoder while v1 data remains cached | Deserialization errors | Versioned keys/migration |
| Running embedded clusters on autoscaled pods ignoring rebalance | Topology churn | Remote cluster or controlled scaling |
| Testing only with local mock managers | Does not test distributed behavior | Real provider integration tests |
| Using cache as a durable queue | Wrong delivery semantics | Broker/outbox |
| Logging keys/values with PII/secrets | Data leakage | Redaction/low-cardinality metrics |

---

## 22. Dependency Selection and Deployment Checklist

### A. Before Choosing a Provider

- [ ] Determined whether the cache is purely an optimization or on a critical business path.
- [ ] Stated consistency SLA/stale window, TTL, eviction, and fail-open/fail-closed rules.
- [ ] Distinguished Spring Cache, JCache API, and concrete providers.
- [ ] Clear rationale for choosing JCache compatibility vs. native APIs.
- [ ] Topology decided: local, embedded members, or remote cluster.
- [ ] Budgeted memory/capacity/network/ops across replicas.

### B. Dependencies and Spring Configuration

- [ ] `spring-boot-starter-cache` present when using Spring Cache annotations.
- [ ] `@EnableCaching` present if not already configured elsewhere.
- [ ] If using JCache, both `javax.cache` API **and** a supported provider are present.
- [ ] If source imports provider types, appropriate compile/implementation scope used.
- [ ] Avoided pulling `hazelcast-spring` when native Spring bridge is not needed.
- [ ] Infinispan embedded/remote/JCache uses exact artifact and release compatible with Boot major version.
- [ ] Did not confuse Hibernate L2/JCache with Spring Cache.
- [ ] Verified actual `CacheManager` bean in startup tests.
- [ ] With multiple managers, bean names/qualifiers/`@Primary` are explicit.
- [ ] JCache named caches provisioned before use.
- [ ] Checked BOM, API namespaces, provider SPI, and classloaders.
- [ ] Reviewed Boot 3/Boot 4 differences against release docs.

### C. Data Contracts, Transactions, and Security

- [ ] Cache keys include tenant/locale/currency/version wherever output is affected.
- [ ] No secrets/PII in keys, logs, or metric tags.
- [ ] Cache values are immutable DTOs with tested serialization compatibility.
- [ ] TTL, expiry policy, max idle, and eviction semantics tested on the real provider.
- [ ] Source-of-truth remains in authoritative DB/service for critical invariants.
- [ ] Addressed failure windows between SQL COMMIT and cache invalidation.
- [ ] Outbox/reliable invalidation present where consistency requires it.
- [ ] Cache is never treated as a durable idempotency store/queue without provider guarantees.
- [ ] Fail-open policies prevent thundering herds and never bypass auth.
- [ ] Configured TLS, authentication, ACLs, secret rotation, and cluster isolation.

### D. Testing and Operations

- [ ] Tested cache hit/miss through Spring-managed proxies.
- [ ] Tested provider auto-selection, missing cache names, and multiple SPI providers.
- [ ] Tested expiration and serialization on real Hazelcast/Infinispan/JCache.
- [ ] Tested with at least 2 clients/pods when distributed visibility is required.
- [ ] Tested cache unavailable, timeouts, DB fallback, and stampedes.
- [ ] Tested rollback/commit followed by invalidation failure.
- [ ] Tested rolling upgrade/rollback with old/new cached values.
- [ ] Metrics cover hits/misses, evictions, errors, cluster health, Hikari, and stale age.
- [ ] Capacity plans cover failover/rebalance/cold starts.
- [ ] Runbooks distinguish cache errors from business DB errors.

**Key takeaway:** **JCache is an API standard (JSR-107), Hazelcast and Infinispan are providers/technologies, and Spring Cache is the application abstraction.** Correct dependencies cover just what is required by the programming model, provider implementation, Spring integration, and real topology. Configure `CacheManager` explicitly, contractually govern keys/TTLs/serialization, keep the source-of-truth in the business system, test invalidation after SQL COMMIT, and ensure cache failures never cascade into system-wide outages.

## References

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, cache managers, and proxies.
- [Spring Framework — JCache/JSR-107 Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html): `@CacheResult`, interoperability with Spring caching.
- [Spring Framework — TransactionAwareCacheManagerProxy](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html): transaction synchronization semantics.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): cache auto-config, supported providers, cache type selection.
- [JSR-107 — JCache Specification](https://jcp.org/en/jsr/detail?id=107): standard API and expiry/provider model.
- [JCache API](https://github.com/jsr107/jsr107spec): `javax.cache` namespace, interfaces, annotations.
- [Hazelcast — Spring Integration](https://docs.hazelcast.com/hazelcast/latest/spring/overview): Hazelcast Spring Cache adapter/usage.
- [Hazelcast — JCache](https://docs.hazelcast.com/hazelcast/latest/jcache/jcache-overview): Hazelcast JCache support, provider config.
- [Hazelcast — Kubernetes](https://docs.hazelcast.com/hazelcast/latest/kubernetes/kubernetes-auto-discovery): member discovery/topology.
- [Infinispan — Documentation](https://infinispan.org/documentation/): embedded/remote Spring integrations, supported releases.
- [Infinispan — Spring Boot Integration](https://infinispan.org/docs/stable/titles/spring/spring.html): embedded and remote Spring starters.
- [Infinispan — Hot Rod Java Client](https://infinispan.org/docs/stable/titles/hotrod_java/hotrod_java.html): remote server/client, serialization.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource/Hikari concurrency and transactions.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration and custom metrics.
- [Testcontainers — Documentation](https://java.testcontainers.org/): provider-backed integration tests.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe consumption.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): reliable invalidation intent and retries.
