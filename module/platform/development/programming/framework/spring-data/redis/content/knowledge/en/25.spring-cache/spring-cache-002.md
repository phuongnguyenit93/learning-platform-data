# Configuring `@EnableCaching` and `RedisCacheManager` in Spring Data Redis

Spring Cache is an abstraction that lets an application cache method results, read back stored results, and invalidate stale data without forcing business code to call Redis everywhere manually. When combined with Spring Data Redis, **`RedisCacheManager`** manages caches stored in Redis, while **`@EnableCaching`** enables processing of annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`.

The two components serve different purposes:

- **`@EnableCaching`** activates the Spring Cache infrastructure and method call interception to apply caching rules.
- **`RedisCacheManager`** supplies the actual `Cache` instances, determining how Redis is connected, time-to-live (TTL), key naming, serializers, and other caching policies.
- **Method annotations** express when to look up the cache, invoke the original method, store the result, or clear the cache.
- **The Redis server** stores cached data as keys/values and manages TTLs, memory limits, and eviction policies.

The core takeaway: simply creating a `RedisCacheManager` does not make every method cached; simply adding `@EnableCaching` also does not automatically select Redis as the backend when an application has multiple cache providers. You need to understand how both parts connect and how proxies work in Spring.

## 1. Spring Cache processing flow with Redis

Suppose there is a method:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(String id) {
    return productStore.findById(id);
}
```

When another bean calls `findById("p-42")` through a Spring proxy, the cache infrastructure operates along this path:

```text
Client / Controller
        |
        v
Spring bean proxy enabled by @EnableCaching
        |
        v
@Cacheable(cacheNames="products", key="p-42")
        |
        v
RedisCacheManager -> Cache "products"
        |
        +---- Cache HIT ----> deserialize Redis value
        |                              |
        |                              v
        |                         return ProductDto
        |
        +---- Cache MISS ---> invoke findById("p-42")
                                      |
                                      v
                               productStore.findById(...)
                                      |
                                      v
                               serialize result
                                      |
                                      v
                               store in Redis with TTL
                                      |
                                      v
                               return ProductDto
```

Spring Cache uses **method result caching**: the cache normally stores the *computed result* of a method, not the entire state of the service.

For example, two consecutive calls with the same key:

```java
ProductDto first = productService.findById("p-42");
ProductDto second = productService.findById("p-42");
```

If the first call succeeds in creating the cache entry and the entry remains valid, the second call can use Redis without calling `productStore.findById(...)` again. However, a cache is not a guarantee that a key will always survive until the end of its TTL: users can actively delete it, the cache can be evicted, and Redis can remove keys under memory pressure.

## 2. Required dependencies

In a Spring Boot application using Redis for Spring Cache, two starters are typically required:

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

With Gradle (Groovy syntax):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

**Roles:**

| Dependency | Purpose |
|---|---|
| `spring-boot-starter-cache` | Support for Spring Cache abstraction, annotations, and related components |
| `spring-boot-starter-data-redis` | Redis connection integration via Spring Data Redis and a Redis client |
| JSON serializer (e.g., version-compatible Jackson) | Converts Java objects to Redis-storable data and back if the application chooses JSON |

The examples below use familiar APIs from Spring Boot 3.x / Spring Data Redis with Jackson 2. Newer Spring Boot/Spring Data versions may have serialization API naming changes; choose a serializer compatible with your active library stack.

The application must have a reachable Redis instance. Example configuration in `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

`localhost` is only suitable when Redis runs on the same machine or has appropriate port forwarding. When running in containers, Kubernetes, or cloud environments, configure endpoints/credentials/TLS to match the real infrastructure. Timeout values are illustrative and should fit your request latency budget.

## 3. Enabling caching with `@EnableCaching`

In a Spring Boot application, place `@EnableCaching` on a configuration class:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Or create a dedicated configuration class:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheInfrastructureConfiguration {
}
```

`@EnableCaching` enables **annotation-driven caching**. Spring detects methods annotated with `@Cacheable`, `@CacheEvict`, `@CachePut`, `@Caching`, and `@CacheConfig`, and applies the caching mechanism via Spring AOP/proxies by default.

### 3.1. Why is `@EnableCaching` needed?

An annotated method:

```java
@Cacheable("products")
public ProductDto findById(String id) {
    return productStore.findById(id);
}
```

only becomes a cache-enabled call when the Spring Cache infrastructure is activated and the object is invoked through an appropriate Spring-managed mechanism.

Without caching enabled, the annotation simply sits on the method as metadata; no interceptor exists to check the cache and store the result.

However, `@EnableCaching` **does not specifically designate Redis**. It needs a suitable `CacheManager` or `CacheResolver`. Spring Boot can auto-configure a cache manager based on dependencies and auto-configuration conditions; when explicit TTLs, serializers, and cache names are required, you can provide a `RedisCacheManager` bean.

### 3.2. Proxy mechanism and internal calls

Spring Cache's default approach is proxy-based. Therefore:

```java
@Service
public class ProductService {

    @Cacheable("products")
    public ProductDto findById(String id) {
        return loadProduct(id);
    }

    public ProductDto findAndLog(String id) {
        return this.findById(id);
    }

    private ProductDto loadProduct(String id) {
        // Fetch source data.
        return null;
    }
}
```

Calling `this.findById(id)` within the **same object** bypasses the Spring proxy and therefore can skip the `@Cacheable` mechanism. This is a common mistake when concluding that caching "doesn't work."

Usually, you should call cached methods through a bean injected by Spring into another service/controller, or extract cached read responsibilities into an independent bean.

Related points:

- Methods should be managed by Spring and called through a proxy.
- Creating objects with `new ProductService()` outside Spring will not have cache advice.
- `private` methods, certain methods that cannot be properly proxied under the active proxy mode, or self-invocation have limitations.
- The `@Cacheable` annotation alone does not route internal calls within an object through a proxy.
- When designing with `final` classes/methods, consider proxy mechanism constraints and the corresponding Spring AOP configuration.

## 4. Starting with Spring Boot auto-configuration

If the application only needs relatively simple cache policies, Spring Boot can automatically create a Redis-backed `CacheManager` when conditions are met and Redis is selected as the cache provider.

Example:

```yaml
spring:
  cache:
    type: redis
    cache-names:
      - products
      - productLists
      - customerProfiles
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
  data:
    redis:
      host: localhost
      port: 6379
```

Explanation:

| Property | Meaning |
|---|---|
| `spring.cache.type: redis` | Tells Boot to use the appropriate Redis cache provider if auto-configuration applies |
| `spring.cache.cache-names` | Declares cache names to initialize |
| `spring.cache.redis.time-to-live` | Sets default TTL for cache entries when Boot builds the Redis cache configuration |
| `spring.cache.redis.cache-null-values` | Chooses whether caching `null` results is allowed |
| `spring.cache.redis.use-key-prefix` | Uses cache-name prefixes to separate namespaces |
| `spring.data.redis.*` | Redis connection settings used by Spring Data Redis |

The properties above belong to Spring Boot auto-configuration features. When an application **declares its own `RedisCacheManager` bean**, do not assume all `spring.cache.redis.*` properties will continue applying to the custom bean in the same way Boot auto-configures it. If you create a custom manager, configure the policies in code or use a supported customizer.

### 4.1. When to use Boot auto-configuration?

Using properties configuration is a concise choice when:

- Only one shared TTL is needed.
- Per-cache-type custom serializers are not yet needed.
- Complex null-value or prefix policies are not yet needed.
- You want configuration per environment without changing Java code.

When caches require different TTLs, JSON serializers, data-versioned prefixes, or specific behaviors, creating a `RedisCacheManager` bean provides greater control.

## 5. Creating a `RedisCacheManager` bean in Java

`RedisCacheManager` uses `RedisConnectionFactory` to connect to Redis and `RedisCacheConfiguration` to control how a cache stores entries.

Complete example:

```java
package com.example.catalog.config;

import java.time.Duration;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class RedisCachingConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(10))
                    .disableCachingNullValues()
                    .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(new StringRedisSerializer())
                    )
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                            )
                    )
                    .computePrefixWith(
                        cacheName -> "catalog:v1::" + cacheName + "::"
                    );

        Map<String, RedisCacheConfiguration> perCache =
                Map.of(
                    "products",
                    defaults.entryTtl(Duration.ofMinutes(15)),

                    "productLists",
                    defaults.entryTtl(Duration.ofSeconds(45)),

                    "customerProfiles",
                    defaults.entryTtl(Duration.ofMinutes(5))
                );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .build();
    }
}
```

Here:

1. `RedisConnectionFactory` is provided by the application's Redis configuration.
2. `RedisCacheConfiguration.defaultCacheConfig()` creates an initial cache configuration.
3. `entryTtl(...)` sets the lifetime for data in Redis.
4. `disableCachingNullValues()` prevents storing null results as cache entries.
5. `serializeKeysWith(...)` converts cache keys into bytes in the desired format.
6. `serializeValuesWith(...)` converts Java objects to JSON and reads them back.
7. `computePrefixWith(...)` creates an explicit namespace for each cache.
8. `withInitialCacheConfigurations(...)` sets distinct TTL configurations for known caches.
9. `build()` creates the `RedisCacheManager` registered in the Spring container as a bean.

If there is only one suitable `CacheManager`, cache annotations can use that bean via Spring Cache's default manager lookup. When there are multiple managers, explicitly choose the manager per method or configure an appropriate resolver.

### 5.1. Understanding `RedisCacheManager` and `RedisCacheConfiguration`

`RedisCacheManager` manages caches by name, such as `"products"` or `"customerProfiles"`.

Each cache receives a `RedisCacheConfiguration` specifying:

```text
Cache "products"
  |
  +-- TTL: 15 minutes
  +-- Key serializer: StringRedisSerializer
  +-- Value serializer: JSON
  +-- Null value: not stored
  +-- Prefix: catalog:v1::products::

Cache "productLists"
  |
  +-- TTL: 45 seconds
  +-- Key serializer: StringRedisSerializer
  +-- Value serializer: JSON
  +-- Null value: not stored
  +-- Prefix: catalog:v1::productLists::
```

This configuration avoids forcing all data types to share the same TTL. Product lists may need to refresh more frequently than slowly changing profile data, while expensive aggregate caches can have TTLs matching actual business needs.

An important note: the TTL values set in `RedisCacheConfiguration` govern cache keys managed by **`RedisCacheManager`**. They **do not automatically apply** to keys written by `StringRedisTemplate`, `RedisRepository`, or other Lua scripts into the same Redis instance.

### 5.2. Configuring `disableCreateOnMissingCache`

By default, `RedisCacheManager` usually allows creating a new cache when a call references a previously undeclared cache name. If a project wants to prevent misspelled cache names from silently creating new namespaces, you can use the builder's capability to restrict dynamic cache creation in supported versions:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .disableCreateOnMissingCache()
        .build();
```

In this mode, an undefined cache name can prevent Spring Cache from resolving the cache and trigger an error when the method is invoked. That is helpful in systems with a fixed list of caches.

Exercise caution when applications generate cache names dynamically per tenant or feature, as blocking new cache creation will alter the behavior of those flows.

## 6. Default TTL and per-cache TTL

TTL (*time to live*) defines the duration from when a cache entry is written until Redis considers the key expired.

Example:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10));
```

This TTL normally applies to entries in caches using `defaults`:

```text
12:00:00   @Cacheable stores products::p-42
12:10:00   Entry lifetime expires
12:10:01   Next call detects miss and invokes original method
```

Separate configurations:

```java
RedisCacheConfiguration productCfg =
        defaults.entryTtl(Duration.ofMinutes(20));

RedisCacheConfiguration listCfg =
        defaults.entryTtl(Duration.ofSeconds(30));
```

give `products` and `productLists` two different expiration windows.

### 6.1. TTL does not mean "keep the key for at least that long"

A cache key can still disappear before its TTL if:

- The application calls `@CacheEvict` or `Cache.evict`.
- An administrative task deletes the key.
- Redis is configured for eviction to free memory and selects the key.
- The entire cache is cleared by name or namespace via a corresponding operation.

Therefore, `@Cacheable` must be designed assuming a cache miss can occur at any time; the original method must be capable of supplying the result from the true data source.

### 6.2. Default TTL is not automatically renewed on reads

With standard cache configuration, hitting an entry **does not automatically renew its TTL**. If an entry is written at 12:00 with a 10-minute TTL, reading it again at 12:08 does not normally extend the expiration to 12:18.

That is the difference between **time to live** and **time to idle**. Some versions of Spring Data Redis provide a time-to-idle option using a supported Redis command, but it must be explicitly enabled, meet Redis version requirements, and be evaluated for read/write TTL overhead. Do not assume `@Cacheable` uses sliding expiration by default.

### 6.3. Very long TTL or no TTL

Redis Cache's default configuration may allow entries to persist indefinitely if no TTL is set, depending on the environment and initialization setup. When configuring manually, proactively define a policy rather than relying on undocumented defaults.

Caches without TTL can still be removed via `@CacheEvict`, manual deletion, or Redis eviction policies. If data can change without reliable invalidation, caches without TTL easily become stale.

## 7. Serializers and reading objects back

Redis stores keys and values as bytes. Spring Cache passes Java objects into the cache, so `RedisCacheManager` must convert them to bytes and reconstruct them on reads.

### 7.1. Key serializer

With `StringRedisSerializer`, key names are represented as UTF-8 strings. For example, a cache key:

```text
catalog:v1::products::p-42
```

is easy to inspect with the Redis CLI:

```redis
TYPE "catalog:v1::products::p-42"
TTL "catalog:v1::products::p-42"
GET "catalog:v1::products::p-42"
```

However, the `GET` value may be JSON containing type metadata or another binary format depending on the serializer; you cannot assume every `GET` result is a human-readable string.

### 7.2. Value serializer

If using:

```java
.serializeValuesWith(
    RedisSerializationContext.SerializationPair
        .fromSerializer(new GenericJackson2JsonRedisSerializer())
)
```

Spring Data Redis can store objects as JSON with the information needed to deserialize the data type according to the serializer's mechanism.

Example DTO:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductDto(
        String id,
        String name,
        BigDecimal price
) {}
```

Conceptually, the cached data is a JSON representation of `ProductDto`; the actual JSON string may include type metadata depending on the serializer and configuration.

Distinguish between:

| Serializer option | Characteristics |
|---|---|
| JDK serialization | Based on Java object serialization; inconvenient to read via CLI, depends on class compatibility, and requires security considerations |
| `StringRedisSerializer` | Suitable when the value is actually a string |
| JSON serializer | Easier to exchange/observe, but requires managing object types and schema changes |
| Custom serializer | Allows exact format control; you bear responsibility for deserialization and compatibility |

The API examples here use `GenericJackson2JsonRedisSerializer` from the Spring Data Redis line using Jackson 2; when upgrading to a Jackson 3 stack, choose the corresponding JSON API supported by that version.

**Serialization security:** do not allow data from untrusted sources to dictate arbitrary Java classes during deserialization; control polymorphic typing, supported type allowlists, and Redis read/write permissions according to the application's threat model. Establish a schema evolution policy when deploying multiple application versions reading the same cache namespace.

### 7.3. Why do serializer errors often appear only after a cache hit?

First call:

```java
ProductDto p = service.findById("p-42");
```

a cache miss invokes the real method, and the result is serialized and stored. If a serialization error occurs, it may appear during the store step.

On a later call, Spring Cache reads the data from Redis and deserializes it back into an object. If the data in Redis was written with an incompatible serializer, an older format, or a class that changed incompatibly, an error may appear on the cache hit.

When changing serializers, change the cache namespace/version or plan a safe cache purge/rebuild instead of letting two incompatible formats share the same key.

## 8. Key prefixes: preventing key name collisions across caches

An application can have multiple caches using the same business key values:

```text
products         -> key "42"
customerProfiles -> key "42"
```

Without distinct prefixes, the two caches risk using the same Redis key and overwriting each other's data.

Redis Cache typically adds a prefix based on the cache name, for example:

```text
products::42
customerProfiles::42
```

When multiple applications share Redis, you can add application and version prefixes:

```java
.computePrefixWith(
    cacheName -> "catalog:v1::" + cacheName + "::"
)
```

Then:

```text
catalog:v1::products::42
catalog:v1::customerProfiles::42
```

Prefixes help:

- Separate caches by service/module.
- Simplify key inspection and scoping.
- Prevent collisions between caches sharing the same business keys.
- Support data format changes via a new versioned namespace.
- Reduce the risk of clear operations affecting unrelated keys when namespaces are properly designed.

Do not disable prefixes just to make keys shorter unless you have an equivalent namespace design. With `Cache.clear()`, cache cleanup can rely on prefixes to identify keys belonging to the cache; omitting prefixes increases the risk of accidental deletion.

### 8.1. Do not confuse Spring Cache keys with Redis Repository keys

Suppose:

```java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;
}
```

Redis Repository can use keys of the form:

```text
products:p-42
```

While `@Cacheable(cacheNames = "products", key = "#p0")` can use:

```text
products::p-42
```

These are **two different data storage mechanisms**. `RedisRepository.save(entity)` does not automatically update entries created by `@Cacheable`, and Redis Cache TTLs do not automatically apply to `@RedisHash` entities.

If you use both Redis Repository as a data source and Spring Cache, manage data lifecycle consistency carefully and avoid overlapping namespaces.

## 9. Applying `@Cacheable`, `@CachePut`, and `@CacheEvict`

Below is an example service that reads and updates products. We define a data source interface to focus on cache behavior:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

public interface ProductStore {
    ProductDto findById(String productId);

    List<ProductDto> findPage(int page, int size);

    void updatePrice(String productId, BigDecimal newPrice);
}
```

A bean implementing `ProductStore` can use JPA, a REST API, or another reliable data source. A real application needs to provide the implementation as usual.

Service:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductStore store;

    public ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "products",
        key = "#p0",
        unless = "#result == null"
    )
    public ProductDto findById(String productId) {
        return store.findById(productId);
    }

    @Cacheable(
        cacheNames = "productLists",
        key = "'page:' + #p0 + ':size:' + #p1"
    )
    public List<ProductDto> findPage(int page, int size) {
        return store.findPage(page, size);
    }

    @CacheEvict(
        cacheNames = "products",
        key = "#p0"
    )
    public void changePrice(String productId, BigDecimal newPrice) {
        store.updatePrice(productId, newPrice);
    }
}
```

### 9.1. `@Cacheable`: look up first, run method on cache miss

```java
@Cacheable(cacheNames = "products", key = "#p0")
```

- `cacheNames`: the cache the manager will obtain to store/read entries.
- `key`: SpEL expression determining the key.
- `#p0`: first positional argument, less dependent on whether the compiler retains parameter names.
- `unless`: condition checked **after the method runs**, capable of rejecting result storage such as `null`.

Distinguish `condition` and `unless`:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
```

`condition` is evaluated beforehand to decide whether to use caching for the call; `unless` is evaluated after method execution and can inspect `#result`.

Configuring `disableCachingNullValues()` on the manager also prevents storing nulls. Using `unless="#result == null"` expresses the rule explicitly on the method and avoids attempting to write nulls under configurations that forbid them.

### 9.2. `@CacheEvict`: invalidate after update

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void changePrice(String productId, BigDecimal newPrice) {
    store.updatePrice(productId, newPrice);
}
```

With `beforeInvocation` defaulting to `false`, eviction executes after the method completes successfully under Spring Cache semantics. If the method throws an exception before returning, eviction normally does not occur in this mode.

When `products:p-42` changes in the data source, deleting the `"products"` cache entry for `p-42` forces the next read to fetch fresh data. However, if `store.updatePrice(...)` runs inside an uncommitted database transaction, consider **eviction timing relative to commit**; the transaction section below explains further.

### 9.3. `@CachePut`: always run the method, then store the result

`@CachePut` differs from `@Cacheable`:

```java
@CachePut(cacheNames = "products", key = "#result.id()")
public ProductDto refreshProduct(String productId) {
    return store.findById(productId);
}
```

- `@Cacheable` can **skip method execution** on a cache hit.
- `@CachePut` **always executes the method** and uses the result to update the cache (subject to configured conditions).
- `@CacheEvict` **deletes entries** rather than storing a new result.

If `refreshProduct` can return null, handle it consistently with `disableCachingNullValues()`; you can add `unless = "#result == null"` on `@CachePut`.

When writing source data, choose `@CachePut` if a complete result is returned and the exact cache value after update is known. Choose `@CacheEvict` if freshness is easier to ensure by letting the next read reload it.

### 9.4. `@CacheConfig` for methods sharing a cache

Reduces repeating cache names:

```java
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "products")
public class ProductReader {

    private final ProductStore store;

    public ProductReader(ProductStore store) {
        this.store = store;
    }

    @Cacheable(key = "#p0", unless = "#result == null")
    public ProductDto findById(String id) {
        return store.findById(id);
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String id) {
        // Method called through a Spring proxy.
    }
}
```

`@CacheConfig` supplies default configuration for cache annotations within the class, but does not enable caching on its own without `@EnableCaching`.

## 10. Selecting a `CacheManager` when the application has multiple backends

An application may use both an in-memory cache (such as Caffeine) and Redis for caching shared across instances.

When multiple `CacheManager` instances exist, annotations can select a manager by bean name:

```java
@Cacheable(
    cacheManager = "redisCacheManager",
    cacheNames = "products",
    key = "#p0"
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

In the Java configuration example in Section 5, the bean was declared by the method:

```java
@Bean
public RedisCacheManager redisCacheManager(...) { ... }
```

so the default bean name is `redisCacheManager`, suitable for specifying in the annotation.

Do not assume Spring will always pick the right manager when multiple options exist. If complex rules per request, tenant, or method are needed, Spring Cache also supports a custom `CacheResolver`. In that case, clearly design which cache belongs to which backend.

### 10.1. Cache name and bean name are two different concepts

In:

```java
@Cacheable(
    cacheManager = "redisCacheManager",
    cacheNames = "products"
)
```

- `"redisCacheManager"` is the **Spring bean name**.
- `"products"` is the **cache name** provided by that manager.

Do not put a cache name into the `cacheManager` attribute or vice versa.

## 11. Does cached data live in the same Redis instance as `RedisTemplate`?

The same `RedisConnectionFactory` can be used for `RedisCacheManager`, `StringRedisTemplate`, Redis repositories, and other Redis APIs.

Example:

```text
RedisConnectionFactory
     |
     +-- RedisCacheManager
     |      +-- cache "products"
     |      +-- cache "customerProfiles"
     |
     +-- StringRedisTemplate
     |      +-- key "rate-limit:user:42"
     |
     +-- Redis Repository
            +-- key "sessions:session-42"
```

They can share the same server, but **do not automatically share serialization rules or namespaces**.

A `RedisCacheManager` configured to use JSON for cache values does not automatically change the serializer of `StringRedisTemplate`. Conversely, configuring a JSON serializer on `RedisTemplate` does not automatically guarantee Spring Cache uses that serializer.

Therefore, when inspecting Redis via the CLI, identify which mechanism owns the key and how each mechanism stores bytes. Do not use `StringRedisTemplate` to raw-read a cached object expecting to always receive the exact `ProductDto` from Spring Cache.

## 12. Cache keys, SpEL, and key consistency

`RedisCacheManager` can add prefixes, but the **business key** is still generated by Spring Cache.

If unspecified:

```java
@Cacheable(cacheNames = "products")
public ProductDto findById(String id) { ... }
```

Spring Cache uses the default key generator based on arguments. With a single simple parameter, the key usually corresponds to that parameter; with multiple parameters, a composite object like `SimpleKey` may be used.

Specifying the key explicitly is usually easier to observe:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(String id) { ... }
```

For searches with multiple parameters:

```java
@Cacheable(
    cacheNames = "productLists",
    key = "'page:' + #p0 + ':size:' + #p1"
)
public List<ProductDto> findPage(int page, int size) { ... }
```

The key here includes both page and size; omitting `size` could cause two requests with different page sizes to share the wrong result.

### 12.1. Be careful with parameter names

Writing:

```java
key = "#productId"
```

only works as expected when Spring can resolve the parameter name `productId`, such as via compiler-provided metadata and appropriate parameter discovery.

To keep examples independent of parameter-name compilation settings, `#p0` and `#p1` are unambiguous choices. In projects with full parameter metadata, using `#productId` can make code more readable.

### 12.2. Avoiding cross-user or cross-tenant cache mix-ups

If the result depends on user, tenant, locale, permissions, or headers while the key only contains `productId`, different requests could receive the same cache entry even though their data should differ.

Conceptual example:

```java
@Cacheable(
    cacheNames = "tenantProducts",
    key = "#p0 + ':' + #p1"
)
public ProductDto findForTenant(String tenantId, String productId) {
    return store.findForTenant(tenantId, productId);
}
```

The security layer must continue enforcing access control to both source data and cache. Do not treat cache keys as an authentication/authorization mechanism.

## 13. Handling nulls, empty collections, and exceptions

A cached method can return:

- A valid object.
- `null`.
- An empty list.
- An exception.

These cases do not carry the same meaning.

With:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

if the product is not found and `null` is returned, the cache does not record the result. The next request can continue querying the data source; this suits cases where the product might be created shortly afterward, though it can burden the source if the same nonexistent ID is queried repeatedly.

An **empty list** is still a valid result and can be cached:

```java
@Cacheable(cacheNames = "productLists")
public List<ProductDto> findPage(int page, int size) {
    return List.of();
}
```

For errors where the data source throws an exception, Spring Cache does not normally store an exception as a successful value. If you want to cache negative results or a "not found" state briefly, model that representation and corresponding TTL explicitly rather than conflating it with `null`.

## 14. Evicting one entry and clearing an entire cache

`@CacheEvict` can delete one key:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidateProduct(String productId) {
}
```

Or clear all entries of a cache:

```java
@CacheEvict(cacheNames = "productLists", allEntries = true)
public void invalidateProductLists() {
}
```

`allEntries = true` applies a clear operation to one cache name; it does not mean deleting every key on the Redis server when namespaces are properly configured. However, clearing can be costly when the cache is very large.

With Redis Cache, the clear mechanism usually needs to find and delete keys by prefix. A default cache writer configuration may scan using `KEYS` and delete in batches; on a large keyspace, this hurts performance. Spring Data Redis supports a batch strategy using `SCAN` under compatible conditions/drivers.

### 14.1. `SCAN` option for clear operations in high-key-count environments

One way to configure a cache writer with a batch strategy:

```java
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;

RedisCacheWriter writer =
        RedisCacheWriter.nonLockingRedisCacheWriter(
            connectionFactory,
            BatchStrategies.scan(1000)
        );

RedisCacheManager manager =
        RedisCacheManager.builder(writer)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
```

`BatchStrategies.scan(1000)` illustrates choosing the strategy with a batch parameter; tune this number based on key count and operating conditions.

Limitations to remember:

- `SCAN` does not make clearing an entire cache an atomic operation.
- Redis Cluster and active drivers have different limitations on how scans execute.
- Keys may be added, modified, or deleted concurrently while scanning runs.
- Do not call `FLUSHDB` or `FLUSHALL` as a substitute for `Cache.clear()`; their impact is far broader.

In many applications, it is better to invalidate **only the exact entries needed** or use a new prefix/version rather than frequently clearing a very large cache.

## 15. `transactionAware()` and timing of cache writes/evictions

A common scenario:

```text
1. Open DB transaction.
2. Update product price in PostgreSQL.
3. Delete Redis cache products::p-42.
4. DB transaction commits or rolls back.
```

If the cache is deleted in step 3 and the DB transaction later rolls back, cached data might be reloaded from the source at an undesirable point. If the cache is updated before the DB commits, inconsistent entries may be created.

Spring Data Redis `CacheManager` can be configured as transaction-aware:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .transactionAware()
        .build();
```

`transactionAware()` causes the manager to use a cache decoration mechanism compatible with Spring transactions, allowing **deferring certain cache operations such as put/evict/clear until after the Spring transaction commits successfully**, when an appropriate active transaction exists.

This is especially useful for cache invalidation following RDBMS updates.

### 15.1. Limitations of `transactionAware()`

`transactionAware()` **is not a distributed transaction between Redis and PostgreSQL**. It does not guarantee:

- Atomic commit of Redis and DB as a single resource.
- Guaranteed eviction success if the process crashes right after the DB commit.
- Turning all cache reads into transactional snapshots.
- Automatic participation of all Redis commands elsewhere in code in the same transaction.
- Deferral of every cache API operation; inspect the semantics of methods like `putIfAbsent` or `evictIfPresent` and immediate operations on the interface.

If eventual invalidation after a DB commit must be guaranteed, consider a **transactional outbox** with retry workers and TTL. When Redis is purely a cache, a simpler strategy is allowing cache misses and rebuilding from the source of truth.

### 15.2. `@CacheEvict(beforeInvocation = true)` is a special case

```java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
```

This configuration requests eviction before the method executes, which is unsuitable if the goal is deleting only after source data changes succeed. Evaluate the business intent before enabling it.

If more reliable post-commit handling is required, design an explicit source-update and invalidation-signaling workflow; do not rely solely on annotation placement for transactional guarantees.

## 16. Cache stampede and concurrent requests

Suppose 200 requests ask for `products::p-42` at the exact moment its TTL expires:

```text
200 requests -> cache MISS
              |
              +-- 200 calls to store.findById("p-42") if uncoordinated
```

This is a **cache stampede**. `RedisCacheManager` and `@Cacheable` should not by default be treated as a distributed lock guaranteeing that only a single request across all instances reloads the data.

Spring Cache provides an option:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

`sync = true` asks the cache provider to attempt coordinating value computation when multiple calls miss the same key, but actual synchronization capability and scope depend on the specific cache implementation. With Redis across multiple JVMs, **do not assume** this configuration guarantees a single request system-wide. Moreover, `sync = true` has annotation restrictions, such as combinations with `unless` or multiple cache names in Spring Cache.

If the data source is expensive or large-scale thundering-herd protection is required, consider key TTL jitter, cache warming, batch loading, bounded locks, or dedicated mechanisms. Every solution requires evaluating concurrency and failure modes.

### 16.1. TTL jitter

If thousands of keys are written simultaneously with an exact 10-minute TTL, they can expire near the same time and trigger a massive wave of cache misses.

One way to mitigate the risk is spreading expiration times with a jittered policy. With `RedisCacheManager`, per-entry TTL customization depends on the Spring Data Redis version and supported `TtlFunction` API. Do not assume a fixed `entryTtl(Duration.ofMinutes(10))` already includes jitter.

## 17. Distinguishing Redis Cache from `RedisTemplate` and Redis Repository

All belong to Spring Data Redis, yet serve different purposes:

| Component | When to use | How to operate |
|---|---|---|
| `RedisCacheManager` + `@Cacheable` | Store method results, reduce data-source queries | Spring Cache annotations |
| `StringRedisTemplate` / `RedisTemplate` | Work with Redis Strings, Hashes, Lists, Sets, counters, TTLs, Lua | `opsForValue`, `opsForHash`, `execute`... |
| Redis Repository with `@RedisHash` | Store/read entities via repository abstraction | `save`, `findById`, `deleteById` |
| Redis scripting | Atomic multi-step check-and-update on the server | `RedisScript`, Lua/Redis Functions |

For example, `@Cacheable` does not require the result class to carry `@RedisHash`:

```java
public record ExchangeRate(String currency, double value) {}

@Cacheable(cacheNames = "exchangeRates", key = "#p0")
public ExchangeRate findRate(String currency) {
    return rateProvider.load(currency);
}
```

The manager serializes the method result and stores it in Redis; this does not mean `ExchangeRate` is stored as a Redis Repository entity. Conversely, `@RedisHash` does not automatically activate method caching.

When using multiple abstractions on the same Redis deployment, define namespaces, TTLs, serializers, and roles for every key clearly to prevent accidental overwrites.

## 18. Tracking cache hit/miss and Redis metrics

Configuring caching is only the first step; you must verify whether the cache actually reduces load on the data source.

Useful metrics:

| Metric | Meaning |
|---|---|
| Cache hit ratio | Proportion of calls served from cache |
| Cache miss ratio | Proportion requiring invocation of the original method/data source |
| p95/p99 latency of cached calls | Latency when both Redis and the data source are under load |
| Redis memory usage | Cache capacity and memory pressure |
| Redis `evicted_keys` | Number of Redis keys evicted due to memory policy |
| Redis `expired_keys` | Number of keys processed by Redis due to TTL expiration |
| Redis CPU/network throughput | Operational cost and proximity to limits |
| Serializer errors | Format read/write errors, often surfacing on cache hits |
| Cache evictions/clears from app | Frequency of active invalidation |

Depending on the Spring Data Redis version, `RedisCacheManager`'s builder can enable local cache statistics:

```java
RedisCacheManager manager =
        RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .enableStatistics()
            .build();
```

These statistics are collected at the cache manager/instance level via the provided mechanism; **they do not automatically equal cluster-wide Redis statistics**. With multiple application replicas, understand which instance each metric belongs to and how your monitoring system aggregates them.

The Redis server provides inspection commands:

```redis
INFO stats
INFO memory
TTL "catalog:v1::products::p-42"
```

`TTL` returns remaining seconds if the key has an expiration, `-1` if the key exists without a TTL, and `-2` if the key no longer exists. A cache miss could result from never being written, expiration, active eviction, or memory eviction; looking at `TTL = -2` alone cannot distinguish the cause.

### 18.1. Verifying cache behavior with real data

A manual check in a development environment:

1. Call `findById("p-42")` the first time and record the number of data-source accesses.
2. Call again with the same ID before the TTL expires; normally data is returned from cache.
3. Inspect the corresponding Redis key and TTL via CLI using the active prefix/serializer.
4. Call `changePrice("p-42", ...)` through a Spring bean to perform invalidation.
5. Call `findById("p-42")` again and observe a fresh read from the source.
6. Wait for the TTL or delete the key in test and confirm the cache can repopulate.

This exercise helps distinguish proxy bugs, wrong cache keys, mismatched serializers, and invalidation failures. Observed outcomes depend on the actual Redis/server configuration and data source.

## 19. Handling Redis errors: is the cache a required component?

Redis is an out-of-process system. Even when used as a cache, it can still experience timeouts or connection drops.

With a pure cache and a reliable data source, some systems choose **fail-open**: when reading the cache fails, still call the data source to serve the request. The alternative is **fail-closed** when the cache holds data required for an invariant or limit.

Spring Cache offers `CacheErrorHandler` to customize error handling for `get`/`put`/`evict`/`clear` operations. Do not blindly swallow every exception without considering consequences:

- Cache read failures can send a surge of concurrent requests to the database.
- Cache write failures usually allow returning the result from the data source if caching is purely an optimization.
- Cache eviction failures can leave **stale data**, which is more dangerous than a simple cache miss.
- Systems need metrics, alerts, and appropriate retry/invalidation mechanisms to avoid prolonged stale caches.

Therefore, cache error handling should reflect the semantics of each cache, not a blanket `try/catch` ignoring all errors system-wide.

## 20. Common configuration mistakes

**Adding `@Cacheable` without enabling caching.** Annotations are not applied as expected without `@EnableCaching` infrastructure.

**Adding `@EnableCaching` and assuming Redis is definitely used.** Spring Cache may pick another provider if auto-configuration or multiple managers alter selection. Specify the manager clearly in configuration.

**Creating a `RedisCacheManager` bean and assuming all Boot properties still apply automatically.** When creating a manager yourself, configure TTL, serializer, and prefix directly or use a version-appropriate customizer.

**Calling `@Cacheable` via `this.method()` inside the same service.** Internal calls bypass the default caching proxy.

**Lacking proper keys for multi-parameter methods.** Results for different requests may collide on a cache entry if the key omits tenant, locale, page, or size.

**Skipping TTL and invalidation configuration.** Data may stay stale longer than business rules permit.

**Using incompatible serializers across application versions.** Cache hits may fail deserialization due to type metadata or schema changes.

**Disabling key prefixes in a shared Redis instance.** Easily causes key collisions across caches, repositories, and other services.

**Clearing entire caches frequently on large keyspaces.** Clear operations can be expensive and impact Redis; consider per-key invalidation or an appropriate `SCAN` strategy.

**Using `@CachePut` when the method result does not reflect the new data state.** The cache can be updated with incomplete or stale values.

**Believing `transactionAware()` guarantees atomic synchronization between Redis and an RDBMS.** It only coordinates the timing of certain cache operations with Spring transactions, not distributed commits.

**Believing `sync = true` always prevents every cache stampede across a cluster.** Coordination capabilities depend on the provider and topology.

**Assuming TTL guarantees a key cannot disappear early.** Redis eviction can still remove keys prematurely depending on memory policy.

## 21. Starter configuration template for a product read service

For an application using Redis to cache read results from a primary data source, a practical configuration can start with:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class ProductCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory
    ) {
        RedisCacheConfiguration base =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(10))
                    .disableCachingNullValues()
                    .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(new StringRedisSerializer())
                    )
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                            )
                    )
                    .computePrefixWith(
                        name -> "catalog:v1::" + name + "::"
                    );

        return RedisCacheManager.builder(factory)
                .cacheDefaults(base)
                .withInitialCacheConfigurations(Map.of(
                    "products",
                    base.entryTtl(Duration.ofMinutes(15)),

                    "productLists",
                    base.entryTtl(Duration.ofSeconds(45))
                ))
                .transactionAware()
                .build();
    }
}
```

Imports are omitted here for brevity; use the classes introduced in the Java configuration section. An application should declare `@EnableCaching` once in a clear configuration location and avoid accidentally creating two `CacheManager` beans of the same name/type.

Service class:

```java
@Service
public class CatalogReadService {

    private final ProductStore store;

    public CatalogReadService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "products",
        key = "#p0",
        unless = "#result == null"
    )
    public ProductDto product(String productId) {
        return store.findById(productId);
    }

    @Cacheable(
        cacheNames = "productLists",
        key = "'p:' + #p0 + ':s:' + #p1"
    )
    public List<ProductDto> page(int page, int size) {
        return store.findPage(page, size);
    }
}
```

This organization establishes a clear boundary:

```text
Spring Cache annotation
     |
     v
RedisCacheManager
     |
     +--> cache "products"       TTL 15 minutes
     |
     +--> cache "productLists"   TTL 45 seconds
     |
     v
Redis with prefix catalog:v1::<cacheName>::
```

To keep data fresh, the source write path must apply an appropriate cache eviction or update strategy after changes succeed; do not rely on TTL as the sole synchronization mechanism when data changes frequently.

## 22. When to use Spring Cache vs. direct Redis operations?

Use **Spring Cache + `RedisCacheManager`** when a method has a cacheable result keyed by arguments that can be reconstructed on a cache miss. This is a clean way to cache results of `findById`, list queries, frequently read configs, or expensive aggregations.

Use **`RedisTemplate` or Lua** when the problem demands specialized Redis operations such as `INCR`, `SET NX`, managing Redis Sets/Sorted Sets, atomic conditional updates, stream processing, or commands depending on state already in Redis.

Both approaches can coexist in one application, provided you distinguish:

- `RedisCacheManager` manages **method result caches**.
- `RedisTemplate` operates directly on Redis data structures.
- Redis Repository manages **object entities** via mapping.
- Spring Cache infrastructure does not turn Redis into the transaction manager for the entire application.

## 23. Conclusion

To configure Spring Cache with Redis, enable **`@EnableCaching`** and provide an appropriate **`RedisCacheManager`**. Spring Boot can auto-create a manager from dependencies and properties for basic cases; when per-cache TTLs, JSON serialization, prefixes, and explicit transactional behavior are needed, configure `RedisCacheManager` in Java.

Key principles:

1. `@EnableCaching` activates the annotation infrastructure, while `RedisCacheManager` determines how the Redis cache is stored and managed.
2. `@Cacheable` checks the cache before running the method; `@CachePut` runs the method and updates the cache; `@CacheEvict` invalidates data.
3. All calls needing caching must go through a Spring proxy in default mode; **self-invocation** is a common reason annotations fail to take effect.
4. TTLs and key prefixes must be designed for real data and namespaces; cache misses can occur early due to eviction.
5. Serializers and schemas must stay consistent across application versions and components reading the same cache.
6. `transactionAware()` helps coordinate certain cache operations with Spring transaction commits, but does not create distributed transactions.
7. Redis Cache suits **reconstructible data**; when atomic operations, rate limiting, or specialized Redis structures are required, use the appropriate Redis API.

By clearly separating the roles of annotations, the manager, the Redis connection, and the data lifecycle, an application can leverage Spring Cache to reduce latency and load on data sources while keeping staleness, errors, and operational costs under control.
