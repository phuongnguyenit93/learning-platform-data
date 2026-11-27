# Configuring Default TTL and Per-Cache Policies in Spring Data Redis

An application may use Redis to cache many kinds of data: product catalogs, prices, inventory, rarely changing settings, or search results. Even though all share Redis, these datasets should not automatically share the same expiration window. Prices and stock levels may require frequent refreshes, whereas configuration data can be cached much longer.

In **Spring Cache** paired with **Spring Data Redis**, there are two primary TTL policy levels:

1. **Default TTL:** applies to caches without a dedicated configuration.
2. **Per-cache TTL:** applies individually per cache name, such as `products` living 5 minutes, `inventory` living 30 seconds, and `settings` living 6 hours.

Spring Data Redis uses `RedisCacheManager` to manage caches and `RedisCacheConfiguration` to describe their policies. Spring Boot can auto-configure a `RedisCacheManager` while allowing a default TTL in `application.yml` or Java customization.

An important point from the start: **TTL is attached to each individual Redis key of a cache entry**. Redis has no single shared timer for an entire Spring "cache region." Entries in the same cache written at different times expire at different times.

## 1. Spring Cache, RedisCacheManager, and Redis keys

Spring Framework provides annotations such as:

- `@Cacheable`: checks the cache before calling the method; on a miss, executes the method and stores qualifying results in the cache.
- `@CachePut`: always executes the method and updates the cache with the result.
- `@CacheEvict`: deletes an entry or cache entries according to configuration.
- `@EnableCaching`: enables processing of cache annotations.

Spring Cache is an **abstraction**: it does not dictate where data is stored. When Redis is chosen as the cache provider, the components fit together as follows:

```text
Controller
   |
   v
Service method with @Cacheable(cacheNames = "products")
   |
   v
Spring Cache interceptor
   |
   +--> RedisCacheManager
           |
           +--> RedisCache("products")
           |       TTL = 5 minutes
           |
           +--> RedisCache("inventory")
           |       TTL = 30 seconds
           |
           +--> RedisCache("settings")
           |       TTL = 6 hours
           |
           +--> Unconfigured caches
                   Default TTL = 10 minutes
   |
   v
Redis Cache Writer / RedisConnectionFactory
   |
   v
Redis key + value + expiration
```

Examples:

```text
products::p-100       -> a cache entry in cache "products"
inventory::p-100      -> a cache entry in cache "inventory"
settings::tax-rules   -> a cache entry in cache "settings"
```

By default, the Redis key prefix normally takes the form `<cacheName>::<key>`. Therefore, the same logical key `p-100` in two distinct caches will not collide on physical Redis keys.

| Component | Responsibility |
|---|---|
| `@Cacheable(cacheNames = "products")` | Selects a cache by name for a method |
| `RedisCacheManager` | Creates/manages cache regions and their configurations |
| `RedisCacheConfiguration` | TTL, key prefix, serializer, null caching, and other options |
| `RedisCacheWriter` | Writes/reads/deletes cache keys in Redis |
| Redis server | Enforces expiration on each key |

**Scope of this lesson:** cache entries managed by Spring Cache and `RedisCacheManager`. This differs from the TTL of a Redis Repository entity declared with `@RedisHash(timeToLive = ...)`, and differs from TTLs passed directly via `RedisTemplate.opsForValue().set(key, value, timeout)`.

## 2. What is Spring Data Redis's default TTL?

When calling:

```java
RedisCacheConfiguration.defaultCacheConfig()
```

directly, **no expiration time** is set on cache entries by default. If the application does not configure a TTL and no other operation sets an expiration, an entry can remain until deleted, replaced, evicted under memory policy, or flushed from Redis.

Notable defaults of `RedisCacheConfiguration` include:

| Property | Default value |
|---|---|
| Cache entry TTL | No TTL expiration |
| Key prefix | Enabled; cache name plus `::` |
| Key serializer | `StringRedisSerializer` |
| Value serializer | `JdkSerializationRedisSerializer` |
| Allow null caching | Yes |
| Time-to-idle on read | Disabled |

These are the defaults of the Spring Data Redis library. When running under Spring Boot, application properties or configuration beans may alter them.

**Never let short-lived data fall back to non-expiring defaults simply because configuration was forgotten.** Pick TTLs matching data freshness, volume, and business requirements.

## 3. Simplest approach: default TTL in application.yml

Suppose the application uses Spring Boot and a local Redis instance. Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Enable caching:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheEnableConfiguration {
}
```

Example `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  cache:
    type: redis
    cache-names:
      - products
      - inventory
      - settings
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
```

Meaning:

- `spring.cache.type: redis` instructs Spring Boot to use Redis Cache if corresponding infrastructure is available.
- `spring.cache.cache-names` lists cache names to pre-initialize; this is **not** where per-cache lifetimes are configured.
- `spring.cache.redis.time-to-live: 10m` sets a **10-minute** default lifetime for entries in the Spring Boot auto-configured Redis `CacheManager`.
- `cache-null-values: false` avoids storing null results as cache entries.
- `use-key-prefix: true` keeps each cache's namespace separate.

Spring Boot accepts `Duration` formats like `30s`, `10m`, `1h`. Use explicit units in YAML to avoid confusing milliseconds and seconds. With this configuration, **products**, **inventory**, and **settings** all receive a 10-minute TTL unless given individual policies.

Note: if the application defines a manual `CacheManager` bean, Spring Boot's automatic `CacheManager` configuration may no longer apply as shown above. In that case, configure TTL inside your application-managed bean.

### 3.1. Example service using default TTL

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#productId")
    public ProductView getProduct(String productId) {
        return repository.findById(productId);
    }
}
```

`ProductRepository` and `ProductView` are illustrative business types; they are not built-in Spring Data Redis classes.

Suppose `getProduct("p-100")` is called:

1. On the first call, the cache lacks `products::p-100`, so the method runs and fetches data from the repository.
2. Spring Cache stores the result in Redis with the default 10-minute TTL.
3. Subsequent calls within the TTL window can retrieve the value directly from Redis, skipping the repository call.
4. Once the key expires, the next call is a cache miss and runs the method again to reload fresh data.

**Do not treat `@Cacheable` as a guarantee that stale data is never read.** During the TTL window, the cache can return an outdated value if source data changes without an invalidation action.

## 4. Configuring per-cache policies

An e-commerce application might use the following lifetimes:

| Cache | Data type | Illustrative TTL |
|---|---|---|
| `products` | Product name, images, description | 5 minutes |
| `inventory` | Displayed stock count | 30 seconds |
| `settings` | Rarely changing settings | 6 hours |
| Remaining caches | General policy | 10 minutes |

These durations are practical examples, not universal defaults. In particular, **exact stock levels used to decide whether an item can be sold** should not rely solely on a 30-second cached value; verify against the source of truth with appropriate concurrency control.

There are two common ways to configure per-cache TTLs.

### 4.1. Approach A — Using Spring Boot's RedisCacheManagerBuilderCustomizer

While letting Spring Boot create `RedisCacheManager`, add a `RedisCacheManagerBuilderCustomizer` bean to attach custom configurations to specific cache names.

The following example uses the **Spring Boot 3.x** package:

```java
import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
public class PerCacheTtlConfiguration {

    @Bean
    public RedisCacheManagerBuilderCustomizer perCacheTtlCustomizer() {
        return builder -> builder
                .withCacheConfiguration(
                        "products",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(5))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "inventory",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofSeconds(30))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "settings",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofHours(6))
                                .disableCachingNullValues()
                );
    }
}
```

Keep the YAML from Section 3 with `time-to-live: 10m`. Under this setup:

- `products` cache uses a **5-minute** TTL.
- `inventory` cache uses **30 seconds**.
- `settings` cache uses **6 hours**.
- Any other cache created by `RedisCacheManager` using the default configuration gets **10 minutes**, provided the `CacheManager` allows dynamic cache creation.

**Note on inheriting other options:** every call to `RedisCacheConfiguration.defaultCacheConfig()` inside the customizer creates a fresh library configuration and does not automatically copy options Spring Boot set on the default configuration—such as custom serializers, custom key prefixes, or null policies. In the example, `disableCachingNullValues()` is explicitly specified so per-cache regions also avoid storing nulls. If your system customizes multiple properties, build from a **shared base configuration** instead of creating inconsistent standalone configurations.

In **Spring Boot 4.x**, the packages of several auto-configuration classes—including `RedisCacheManagerBuilderCustomizer`—changed. When copying examples, select imports matching your actual Spring Boot BOM rather than mixing 3.x and 4.x packages.

### 4.2. Approach B — Declaring a RedisCacheManager bean directly

If you want explicit control over all defaults and per-cache policies, declare a `RedisCacheManager` bean. This fits well when TTL policies must be read and managed alongside serializers, prefixes, null policies, and clear strategies.

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class RedisCacheConfigurationBean {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        Map<String, RedisCacheConfiguration> cachePolicies = Map.of(
                "products",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "inventory",
                defaults.entryTtl(Duration.ofSeconds(30)),
                "settings",
                defaults.entryTtl(Duration.ofHours(6))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(cachePolicies)
                .build();
    }
}
```

Configuration methods on `RedisCacheConfiguration` return **new configuration instances**; calling `defaults.entryTtl(...)` does not mutate the existing `defaults`. You can therefore construct one shared base configuration and derive variants differing only in TTL.

Builder structure:

```text
RedisCacheManager
  |
  +-- cacheDefaults(defaults)
  |     +-- entryTtl(10 minutes)
  |     +-- disableCachingNullValues()
  |     +-- default key prefix
  |
  +-- withInitialCacheConfigurations(cachePolicies)
        |
        +-- products  -> entryTtl(5 minutes)
        +-- inventory -> entryTtl(30 seconds)
        +-- settings  -> entryTtl(6 hours)
```

With Approach B, **the Java bean itself** owns `CacheManager` configuration. Do not assume `spring.cache.redis.time-to-live: 10m` will automatically override TTL inside `cacheDefaults(defaults)`. If you want values read from YAML, bind them explicitly via `@ConfigurationProperties` or `@Value` and build `RedisCacheManager` from those properties.

### 4.3. Which approach should you choose?

| Requirement | Suitable approach |
|---|---|
Need only one default TTL | YAML `spring.cache.redis.time-to-live` |
Want custom TTLs for a few caches while keeping Boot auto-configuration | `RedisCacheManagerBuilderCustomizer` |
Want one shared base configuration, per-cache policies, custom serializer, and custom writer | Application-managed `RedisCacheManager` bean |
Want different TTLs for individual **entries within the same cache** | `RedisCacheWriter.TtlFunction`, if supported by version |

Use a single primary configuration strategy to avoid confusion over which source dictates the final TTL.

## 5. @Cacheable selects a cache; it does not define TTL itself

Consider a service accessing three different cache regions:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final CatalogGateway gateway;

    public CatalogQueryService(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public ProductView findProduct(String id) {
        return gateway.loadProduct(id);
    }

    @Cacheable(cacheNames = "inventory", key = "#id")
    public InventoryView findInventory(String id) {
        return gateway.loadInventory(id);
    }

    @Cacheable(cacheNames = "settings", key = "#name")
    public SettingView findSetting(String name) {
        return gateway.loadSetting(name);
    }
}
```

`CatalogGateway`, `ProductView`, `InventoryView`, and `SettingView` are application-defined classes.

The three annotations do not declare expiration durations directly. They specify **cache names**; `CacheManager` resolves the corresponding `RedisCacheConfiguration` by name and applies its TTL:

```text
findProduct("p-100")
  --> @Cacheable("products")
  --> products::p-100
  --> TTL 5 minutes

findInventory("p-100")
  --> @Cacheable("inventory")
  --> inventory::p-100
  --> TTL 30 seconds

findSetting("tax-rules")
  --> @Cacheable("settings")
  --> settings::tax-rules
  --> TTL 6 hours
```

There is no standard `ttl` attribute on Spring Framework's `@Cacheable` allowing `@Cacheable(ttl = "30s")`. If methods require different lifetimes, you can:

- Assign methods to **different cache names** with separate policies.
- Use `TtlFunction` to compute TTL from key/value within the same cache when supported by your version.
- Use another specialized caching mechanism if policies demand complex logic.

Merely changing the SpEL key, e.g., `key = "#id"` vs. `key = "#tenantId + ':' + #id"`, **does not alter TTL** when staying inside the same cache region with a fixed configuration.

### 5.1. Self-invocation and @EnableCaching

Spring Cache typically relies on proxies/AOP to intercept method calls. If within the same class, method A directly calls `this.findProduct(...)`, that call usually bypasses the cache proxy. Consequently, a test may make it look as though TTL is broken when the method never went through the cache at all.

When verifying:

1. Ensure `@EnableCaching` or equivalent activation is present.
2. Invoke the method via a Spring bean from another object.
3. Confirm the active `CacheManager` is indeed `RedisCacheManager`.
4. Inspect the Redis key and `TTL` after a cache miss.

## 6. When is TTL set or refreshed?

In Spring Data Redis Cache, **time-to-live** is normally set when a cache entry is **created or overwritten**. Reading an existing entry with `@Cacheable` does not automatically extend its TTL under standard TTL policy.

Example for `products` cache with a 5-minute TTL:

```text
12:00:00  findProduct("p-100")  cache miss
          -> invokes method, writes products::p-100
          -> TTL approx. 300 seconds

12:02:00  findProduct("p-100")  cache hit
          -> retrieves cached value
          -> TTL remaining approx. 180 seconds

12:04:59  findProduct("p-100")  cache hit
          -> TTL remaining approx. 1 second

12:05:01  findProduct("p-100")  entry expired
          -> cache miss, method runs again
          -> writes new entry, TTL resets to approx. 300 seconds
```

These illustrative numbers ignore processing time skew and Redis's internal expiration scheduling.

### 6.1. @CachePut normally resets TTL

```java
import org.springframework.cache.annotation.CachePut;

@CachePut(cacheNames = "products", key = "#result.id")
public ProductView refreshProduct(String id) {
    return gateway.loadProduct(id);
}
```

`@CachePut` always executes the method and writes the result to cache. When rewriting the entry, TTL is set per the cache configuration. For the `products` cache, lifetime after the fresh write is approximately 5 minutes.

### 6.2. @CacheEvict deletes the entry, rather than "shortening TTL"

```java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "products", key = "#id")
public void invalidateProduct(String id) {
    // May be empty if invalidation logic lives in this method.
}
```

`@CacheEvict` removes the corresponding key. Afterward, calling `findProduct(id)` reloads the data and creates the key with a fresh TTL. `@CacheEvict` does not shorten the remaining lifetime of an existing entry.

### 6.3. Be cautious with multiple cacheNames on one method

`@Cacheable(cacheNames = {"products", "inventory"})` causes Spring to inspect multiple caches and apply abstraction semantics. Two caches with different TTLs and data types can lead to hard-to-explain behavior. Only list multiple cache names for the same data type intentionally; if caches represent different types of data, split the methods.

## 7. Verifying TTL configuration via Redis CLI

The following examples assume Spring creates keys using the default prefix:

```text
products::p-100
inventory::p-100
settings::tax-rules
```

After method calls triggering cache misses:

```redis
EXISTS products::p-100
# (integer) 1

TTL products::p-100
# (integer) 298

TTL inventory::p-100
# (integer) 28

TTL settings::tax-rules
# (integer) 21595
```

These numbers illustrate elapsed time since the writes. If millisecond precision is needed, use:

```redis
PTTL products::p-100
```

Meaning of `TTL`/`PTTL` results:

| Value | Meaning |
|---|---|
| Non-negative number | Remaining lifetime in seconds/milliseconds |
| `-1` | Key exists with no expiration set |
| `-2` | Key does not exist or has expired |

When inspecting with Redis CLI, verify you are connected to the **same Redis server, logical database, and namespace** used by the application. If key prefixes or key conversions have been customized, actual key names will differ from these examples.

### 7.1. Checking default TTL on un-overridden caches

Suppose a `recommendations` cache is created dynamically using the 10-minute default configuration:

```java
@Cacheable(cacheNames = "recommendations", key = "#userId")
public RecommendationView getRecommendations(String userId) {
    return recommendationGateway.load(userId);
}
```

After the first call:

```redis
TTL recommendations::user-42
# approx. 600
```

If the `CacheManager` is configured to **disallow creating undeclared caches**, `recommendations` must be added to the configuration list beforehand; otherwise Spring Cache may throw an error resolving the cache instead of creating it automatically. This is a cache-name governance choice, independent of TTL duration.

### 7.2. If TTL returns -1 after writing to cache

Checklist to inspect:

- Is `RedisCacheManager` actually the application's active `CacheManager`?
- Was the default TTL placed under the correct YAML hierarchy?
- Is a custom `RedisCacheManager` bean ignoring Spring Boot properties?
- Does that specific cache set `entryTtl(Duration.ZERO)` or omit TTL?
- Did a `PERSIST`, `SET` without expiration, or another writer modify the key after the cache write?
- Are you inspecting the right prefix, database, and serializer?

Do not conclude "Redis does not support TTL" from `-1`: it simply means the key has no expiration **at the time of inspection**.

## 8. Cache names, key prefixes, and TTL policies

Two caches can share the same logical key:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findProduct(String id) { ... }

@Cacheable(cacheNames = "inventory", key = "#id")
public InventoryView findInventory(String id) { ... }
```

With the default key prefix:

```text
products::p-100  -> TTL 5 minutes
inventory::p-100 -> TTL 30 seconds
```

The two physical Redis keys differ, so neither data nor expirations collide.

If you disable key prefixes with `disableKeyPrefix()` or `spring.cache.redis.use-key-prefix: false`, both entries compete for key `p-100`. Besides the risk of **values being overwritten by another cache**, clearing one cache can impact unrelated Redis data due to missing namespace isolation.

Therefore:

- Keep cache-name prefixes unless you have an explicit alternative namespace design.
- When using custom prefixes, ensure caches stay distinct under a stable convention.
- Do not change prefixes on live cached data without planning how to handle old keys.

### 8.1. Example custom prefix configuration

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .computePrefixWith(cacheName ->
                        "shop:v1:" + cacheName + "::");
```

Physical keys then look like `shop:v1:products::p-100`. TTL is still governed by `entryTtl`; the prefix alters only the **key name**, not entry lifetime.

## 9. Serializer configuration and null caching

TTL is usually the first step, yet cache policies must also address data encoding and behavior when a method returns `null`.

### 9.1. What does caching null mean?

If a `@Cacheable` method returns `null` when data is missing, Spring Data Redis by default can store a special representation for the null value. Subsequent calls receive a cache hit for "not found" instead of querying the data source.

This is **negative caching**, useful for reducing repeated queries for nonexistent IDs. Yet it carries a risk:

1. A user accesses a nonexistent product; the cache records null.
2. The product is actually created in the system.
3. During the TTL window, the cache continues returning null until the entry expires or is invalidated.

To prevent storing nulls:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();
```

You can configure this per cache: a catalog cache may disallow nulls, while an expensive lookup cache employs negative caching with a very short TTL. Clarify the policy before going to production.

**Note:** with `disableCachingNullValues()`, calling `Cache.put(key, null)` directly is not a safe key-deletion command; it can throw an error. On annotations, consider adding `unless = "#result == null"` on `@Cacheable` to proactively avoid writing nulls from the method.

```java
@Cacheable(
        cacheNames = "products",
        key = "#id",
        unless = "#result == null")
public ProductView findProduct(String id) {
    return gateway.loadProduct(id);
}
```

### 9.2. Serializers must be compatible across application versions

`RedisCacheConfiguration.defaultCacheConfig()` uses `StringRedisSerializer` for keys and `JdkSerializationRedisSerializer` for values. In multi-instance Java applications, modifying classes, changing `serialVersionUID`, or deploying mixed versions can break reading cached Java-serialized values.

You can configure a different serializer:

```java
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

RedisCacheConfiguration jsonCache =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(java.time.Duration.ofMinutes(10))
                .serializeValuesWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                        )
                );
```

This illustrates one serializer choice, not advice to switch every cache to the same encoder. Serializers must match library versions, data types, and application security policies. Consider type allowlists for deserialization, backward payload compatibility, and a purge/migration plan when changing formats.

If different caches use different serializers, manage them in per-cache `RedisCacheConfiguration` objects just like TTLs; avoid accidentally losing shared serializers when creating per-cache configs from `defaultCacheConfig()`.

## 10. Per-cache TTL vs. dynamic per-entry TTL

So far, each cache region has a fixed lifetime:

```text
products    -> every entry 5 minutes
inventory   -> every entry 30 seconds
settings    -> every entry 6 hours
```

Sometimes, however, **entries within the same cache** need different TTLs. For instance, breaking news stories live 20 seconds while regular articles live 10 minutes, even though both belong to the `news` cache.

Since **Spring Data Redis 3.2**, `RedisCacheWriter.TtlFunction` allows computing lifetimes from each entry's key or value:

```java
import java.time.Duration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheWriter;

RedisCacheWriter.TtlFunction newsTtl = (key, value) -> {
    if (value instanceof NewsView news && news.isBreaking()) {
        return Duration.ofSeconds(20);
    }
    return Duration.ofMinutes(10);
};

RedisCacheConfiguration newsConfig =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(newsTtl);
```

`NewsView` is an illustrative domain model having an `isBreaking()` method. You can pass `newsConfig` into `withCacheConfiguration("news", newsConfig)`.

Distinction:

| Policy level | Example | Tool |
|---|---|---|
| CacheManager default | All un-overridden caches: 10 minutes | `cacheDefaults(...)` or Spring Boot property |
| By cache name | `products`: 5 minutes; `inventory`: 30 seconds | `withCacheConfiguration(...)` |
| Per entry | Breaking news 20 seconds; regular news 10 minutes | `entryTtl(TtlFunction)` from Spring Data Redis 3.2 |

`TtlFunction` does not spin up a scheduler inside the JVM. It returns a `Duration` when writing the cache entry; Redis still manages expiration of the Redis key.

**Note:** if every entry in a region shares the same TTL, you do not need `TtlFunction`. `entryTtl(Duration.ofMinutes(5))` is simpler and easier to operate.

## 11. TTL and TTI: do cache reads renew expiration?

**TTL (Time To Live)** in standard Redis Cache is set on write. Reading an entry does not extend it.

**TTI (Time To Idle)** is a policy where an entry expires after a period **without access**. Redis server does not have a dedicated TTI metadata setting, but Spring Data Redis 3.2+ can emulate TTI using the Redis `GETEX` command: reading the value and resetting its expiration in one command.

Example:

```java
RedisCacheConfiguration frequentlyReadConfig =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .enableTimeToIdle();
```

When TTI is enabled:

```text
12:00  write entry       -> 5 minutes remaining
12:03  read via Cache    -> TTL reset to approx. 5 minutes
12:07  read via Cache    -> TTL reset to approx. 5 minutes
12:12  no further reads  -> entry may have expired
```

Important requirements:

- `enableTimeToIdle()` requires Redis **6.2+** because it relies on `GETEX`.
- Do not expect raw `GET` commands or other paths not using `GETEX` to refresh TTL.
- TTI stays consistent only when all relevant read/write paths obey the policy. Mixing Spring Cache operations with raw `RedisTemplate` calls on the same key can cause unexpected lifetimes.
- TTI can keep "hot" keys alive indefinitely if read continuously. Consider whether data must expire absolutely after a business deadline.

If you only need per-cache TTL policies without read-driven extension, stick with standard TTL; avoid enabling TTI merely to boost hit rates.

## 12. Source data updates and invalidation

TTL bounds maximum lifetime since the last cache write; it **does not know when source data changed**.

For example, if someone updates a product description while `products` has a 5-minute TTL:

```text
12:00  Cache products::p-100 = "Blue"
12:01  Database changes to "Red"
12:02  @Cacheable still returns "Blue" unless evicted/updated
12:05  Entry expires
12:06  Cache miss -> fetches "Red" and writes new entry
```

To narrow the staleness window, you can use:

1. **Cache-aside with invalidation:** after updating source data successfully, remove the affected entry via `@CacheEvict` or the Cache API.
2. **Application-level write-through:** use `@CachePut` to update the entry after modifying source data.
3. **Shorter TTL:** suitable for data tolerant of brief inconsistency; trades off against higher cache miss rates.
4. **Versioned keys:** include version or revision numbers in keys when isolating data generations.

Invalidation example:

```java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "products", key = "#id")
public void updateProductDescription(String id, String description) {
    productRepository.updateDescription(id, description);
}
```

Because updating the database and deleting the Redis cache involve **two different systems**, account for operation ordering, retries, and partial failures. `@Transactional` on a relational database does not make Redis operations part of a distributed atomic commit. For high-precision workflows, an outbox/event mechanism with retries and idempotency may be needed.

### 12.1. TTL does not prevent cache stampedes

When a popular key expires, many concurrent requests can miss simultaneously and invoke the data source. This is a **cache stampede**.

Mitigations include:

- Choosing sensible TTLs and avoiding having large batches of entries expire at the exact same moment.
- With Spring Cache, evaluating `@Cacheable(sync = true)` if the `Cache` implementation supports synchronizing data-loading calls. Do not assume it establishes a full distributed lock across all instances.
- Considering dynamic jittered TTLs if data and requirements permit, or proactive refresh before expiration.
- Protecting the data source with concurrency limits and timeouts.

Per-cache TTLs reduce load by tailoring lifetimes to each dataset; they do not automatically solve concurrency spikes at expiration time.

## 13. Operating Redis Cache with multiple cache names

### 13.1. Monitoring keyspace and avoiding TTL-less keys

A single system may run multiple mechanisms together:

```text
products::p-100    -> Spring Cache, 5-minute TTL
inventory::p-100   -> Spring Cache, 30-second TTL
session:abc        -> RedisTemplate, TTL set explicitly by app
orders:o-100       -> Redis Repository, TTL set via @RedisHash
```

These keys can coexist in one Redis instance, yet **`RedisCacheManager` TTL policies apply only to cache entries managed by that `CacheManager`**. Setting `spring.cache.redis.time-to-live` does not automatically assign a TTL to `session:abc` or Redis Repository entities.

Good operational practices:

- Define clear namespaces per key type.
- Configure TTLs wherever data writes are owned.
- Monitor the proportion of keys without expiration when data should be short-lived.
- Never run cleanup jobs with overly broad patterns that touch non-cache business keys.

### 13.2. Clearing an entire cache region can be costly

When calling:

```java
cacheManager.getCache("products").clear();
```

Spring Data Redis typically deletes keys matching the cache's prefix. By default, deletion may use `KEYS` followed by `DEL`; broad `KEYS` scans can degrade performance on large Redis instances.

Spring Data Redis offers a `SCAN` option via `BatchStrategies.scan(...)` when building `RedisCacheWriter`:

```java
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

RedisCacheWriter writer =
        RedisCacheWriter.nonLockingRedisCacheWriter(
                connectionFactory,
                BatchStrategies.scan(1000));

RedisCacheManager manager =
        RedisCacheManager.builder(writer)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(cachePolicies)
                .build();
```

This snippet shows **the writer replacement portion** inside the bean configuration from Section 4, not a second bean to register in parallel. According to the documentation, the `SCAN` strategy is fully supported with Lettuce, whereas Jedis has limitations on Redis Cluster. Verify your exact driver and topology before adopting it.

TTL does not replace `clear()`: entries expire individually per key, whereas `clear()` demands removing an entire cache region matching a cache name.

### 13.3. Metrics and policy verification

You can check:

```redis
TTL products::p-100
TTL inventory::p-100
TTL settings::tax-rules
INFO stats
INFO memory
```

Beyond the Redis CLI, monitor cache hits/misses, reload frequencies, source latencies, Redis memory usage, and key counts per namespace. `RedisCacheManagerBuilder.enableStatistics()` provides local-instance cache statistics in Spring Data Redis; do not mistake local figures for cluster-wide application metrics.

Changing TTL configuration in a new deployment **does not automatically alter the expiration of already stored keys**. The new TTL applies as those keys are written or updated under the new configuration. To switch policies immediately for an entire cache, design a controlled purge or migration of old keys.

## 14. Common mistakes

| Symptom | Causes to check | Resolution |
|---|---|---|
| `inventory` cache still has 10-minute TTL | Missing per-cache config or mismatched cache name | Verify `withCacheConfiguration("inventory", ...)` and `@Cacheable(cacheNames=...)` |
| `spring.cache.redis.time-to-live` seems ignored | Application defines its own `CacheManager` bean | Set TTL in the bean or use a customizer with auto-config |
| Only some caches store null | Per-cache config did not inherit default null policy | Derive configurations from a shared base configuration |
| TTL keeps dropping despite frequent reads | Using TTL, not TTI | Standard behavior; enable `enableTimeToIdle()` only if needed |
| Redis returns command error after enabling TTI | Server does not support `GETEX` | Redis 6.2+ is required |
| Entries never expire (`TTL = -1`) | No expiration set or key rewritten without TTL | Trace write paths and active configuration |
| TTL is right yet cache serves stale data | Source data changed before cache expired | Use invalidation/refresh alongside TTL |
| Two caches overwrite each other | Key prefix disabled or colliding custom prefix | Keep distinct per-cache prefixes |
| Continuous cache misses | TTL too short, keys differ across calls, or cache proxy bypassed | Check keys, lifetimes, and Spring AOP |
| Deployed new TTL yet old keys retain long lifetimes | New config does not apply retroactively to existing keys | Plan a controlled clear/refresh or wait for old keys to expire |
| Cache clear spikes Redis load | Batch strategy uses `KEYS` on a large keyspace | Evaluate `SCAN` per driver/topology, tune batch size |
| Cached values unreadable after deploy | Serializer/class changed while old keys remained | Manage compatibility or purge/migrate cache cleanly |

## 15. Complete hands-on exercise

**Goal:** configure a 10-minute default TTL and three caches with individual policies:

```text
products    5 minutes
inventory   30 seconds
settings    6 hours
other       10 minutes (default)
```

Steps:

1. Add `spring-boot-starter-cache` and `spring-boot-starter-data-redis`.
2. Enable `@EnableCaching` and configure the Redis connection.
3. In `application.yml`, set `spring.cache.type: redis` and `spring.cache.redis.time-to-live: 10m`.
4. Add a `RedisCacheManagerBuilderCustomizer` defining custom TTLs for the three caches, or replace it with a `RedisCacheManager` bean containing defaults + per-cache map.
5. Create `@Cacheable(cacheNames = "products")` and `@Cacheable(cacheNames = "inventory")` methods accepting the same `id`.
6. Call each method once, then run Redis CLI `TTL products::<id>` and `TTL inventory::<id>`. Observe roughly 300 and 30 seconds.
7. Call the methods again while cached; remaining time continues counting down under standard TTL.
8. Use `@CachePut` or update the entry to observe TTL reset; use `@CacheEvict` to observe key removal.
9. Try an un-overridden cache such as `recommendations` to verify the default TTL.
10. Change a cache's TTL in configuration, deploy to a test environment, and compare the TTL of old keys with newly created entries.

**Self-check questions:**

- If `@Cacheable(cacheNames = "inventory")` queries source data every 5 seconds with a 30-second TTL, do cache hits automatically renew the key?
- If one cache uses the 10-minute default TTL and another overrides 30 seconds, can both use the same logical key `p-100`?
- When using `RedisCacheManagerBuilderCustomizer` with separate `defaultCacheConfig()` calls, why must you pay attention to serializers and null-caching settings?
- If business rules require inventory counts to be strictly accurate at checkout time, is a 30-second TTL sufficient?
- If you want entry-specific lifetimes within the same cache, which mechanism should you use in Spring Data Redis 3.2+?

## 16. Summary

In Spring Data Redis, **`RedisCacheManager` selects a `RedisCacheConfiguration` by cache name**, while the Redis server manages expiration per key. A default TTL can be declared concisely via `spring.cache.redis.time-to-live` when using Spring Boot auto-configuration. Caches requiring individual policies should be configured via `RedisCacheManagerBuilderCustomizer` or a `RedisCacheManager` bean with `cacheDefaults(...)` and `withInitialCacheConfigurations(...)`.

Standard TTL is normally **reset on write**, while cache hits simply read data without extending lifetime. When entry-specific TTLs are needed, Spring Data Redis 3.2+ provides `RedisCacheWriter.TtlFunction`; when lifetimes must extend on reads, `enableTimeToIdle()` leverages Redis `GETEX`. These features address distinct needs and should not needlessly replace a simple per-cache policy.

In operations, keep key prefixes to isolate cache regions, align serializers and null policies, handle invalidation on source updates, and verify TTLs via the Redis CLI. **TTL is a tool for bounding cache age, not a guarantee that data stays fresh or consistent with the source.**

## References

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheConfiguration`, TTL/TTI policies, serializers, key prefixes, and cache clearing.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): `spring.cache.redis.time-to-live`, `spring.cache.cache-names`, and `RedisCacheManagerBuilderCustomizer`.
- [Spring Boot 3.4 — Caching](https://docs.spring.io/spring-boot/3.4/reference/io/caching.html): Spring Boot 3.x example with `RedisCacheManagerBuilderCustomizer` imports.
- [Spring Data Redis API — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheConfiguration.html): `entryTtl(Duration)`, `entryTtl(TtlFunction)`, `disableCachingNullValues()`, and `enableTimeToIdle()`.
- [Spring Framework — Caching](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, SpEL keys, and proxy limitations.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): expiration mechanics on Redis keys.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): reading remaining lifetime and special values `-1`/`-2`.
- [Redis — GETEX](https://redis.io/docs/latest/commands/getex/): reading and updating key expiration in a single command.
