# `condition`, `unless`, and Decisions on Caching `null` Values in Spring Data Redis

## 1. Why are caching conditions needed?

Spring Cache separates caching logic from most business code through annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`. When Redis is chosen as the cache provider, Spring Data Redis supplies `RedisCacheManager` to read/write cache entries via Redis.

By default, with `@Cacheable`, Spring looks up a value by cache name and key before invoking the method. On a cache hit, the method may be skipped. On a cache miss, the method runs and the result is put into the cache according to policy.

However, not every invocation or every result deserves caching:

- Invalid IDs, test-only requests, or objects outside the group that should be cached.
- Nonexistent return results (`null` or `Optional.empty()`).
- Results with transient, sensitive, or overly fast-changing state.
- A system error accidentally represented by the business layer as `null`, risking caching a wrong state.
- A "not found" lookup may be worth caching briefly to reduce load on the data source (**negative caching**), yet doing so can also prevent the application from seeing a newly created record.

Two annotation attributes control this:

- **`condition`**: decides upfront whether to apply caching to the invocation at all.
- **`unless`**: decides whether to **veto writing the result to cache** after the method has run.

Beyond those two expressions, there is the **Redis cache policy on whether `null` values are stored**, configured on `RedisCacheConfiguration`, `RedisCacheManager`, or Spring Boot properties. These three mechanisms are related but have distinct responsibilities.

## 2. Execution flow of `@Cacheable`

Example:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return customerRepository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Here `#p0` is the first parameter, corresponding to `id`. Processing flow on an invocation **passing through the Spring Cache interceptor**:

§§§mermaid
flowchart TD
    A["Call findCustomer(id) through Spring proxy"] --> B{"Is condition true?"}
    B -->|No| C["Skip caching mechanism"]
    C --> D["Invoke method and return result"]
    B -->|Yes| E["Generate key and look up in Redis cache"]
    E --> F{"Cache hit?"}
    F -->|Yes| G["Return cached value, skip method invocation"]
    F -->|No| H["Invoke method"]
    H --> I["Method returns successfully"]
    I --> J{"Is unless true?"}
    J -->|Yes| K["Do not write result to cache"]
    J -->|No| L["Write result per RedisCache policy"]
    K --> M["Return result"]
    L --> M
§§§

Distinguish clearly:

1. `condition` runs at the **pre-invocation stage**; it can reference parameters, method info, and target.
2. `unless` runs at the **post-invocation stage** when deciding whether to store the result; the expression can use `#result`.
3. On a `@Cacheable` cache **hit**, the method does not run to recompute the result, so `unless` **is not used to re-filter an already cached entry**.
4. If the method throws an exception instead of returning normally, Spring Cache normally does not cache that exception as a valid value.

Thus, `unless` is a **cache put veto**: it prevents writing a new result, rather than guaranteeing every existing entry in Redis satisfies the current condition.

## 3. Getting started with Spring Boot, Redis, and Spring Cache

In a Spring Boot project using Redis as the cache backend:

§§§groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
§§§

Example development configuration:

§§§yaml
spring:
  cache:
    type: redis
    cache-names: customerById,customerLookup
  data:
    redis:
      host: localhost
      port: 6379
§§§

Enable annotation-driven caching:

§§§java
package com.example.demo;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingConfig {
}
§§§

When suitable Redis Cache auto-configuration applies and no other `CacheManager` is selected, Spring Boot can create `RedisCacheManager`. Projects with multiple cache providers should configure `spring.cache.type: redis` or an appropriate `CacheManager` explicitly.

Keep three layers in mind:

| Layer | Responsibility |
|---|---|
| Spring Cache abstraction | Defines `@Cacheable`, `condition`, `unless`, key generation, and method invocation |
| Spring Data Redis `RedisCacheManager` / `RedisCache` | Manages cache entries, TTL, serializers, and `null` policy |
| Redis server | Stores serialized keys/values, manages expiration and data recovery capabilities |

Enabling `@EnableCaching` **does not automatically make every method cached**. Methods must be invoked via an appropriate interception mechanism, and cache annotations must be placed where Spring can detect them.

## 4. `condition`: deciding before method execution

### 4.1. What does `condition` express?

`condition` is a **Spring Expression Language (SpEL)** expression returning a boolean. With `@Cacheable`, if the expression evaluates to `false`, Spring neither searches the cache, uses an existing entry, nor writes to the cache for that call; the method executes normally.

Example caching only when the ID is non-null and non-blank:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

A call to `findCustomer("42")` can go through the cache. Calls to `findCustomer(null)` or `findCustomer("   ")` bypass the cache. Whether the method accepts null remains governed by business rules; `condition` does not replace validation.

Example caching lookups only for email addresses in an allowed domain:

§§§java
@Cacheable(
    cacheNames = "customerByEmail",
    key = "#p0",
    condition = "#p0 != null && #p0.endsWith('@example.test')"
)
public CustomerDto findByEmail(String email) {
    return lookupByEmail(email);
}
§§§

Here the condition ensures emails outside that domain do not use the cache. It **does not enforce access control**: authorization checks must be executed independently before returning data, even on a cache hit.

### 4.2. SpEL variables available before method invocation

Spring Cache expressions can typically reference:

| Expression | Meaning |
|---|---|
| `#p0`, `#a0` | First method parameter |
| `#p1`, `#a1` | Second parameter |
| `#root.args[0]` | First argument via the root object |
| `#root.methodName` | Name of the intercepted method |
| `#root.target` | Target object being invoked |
| `#root.targetClass` | Class of the target |
| `#root.caches` | Collection of caches resolved for the operation |

Direct parameter names like `#id` are convenient but depend on Spring's ability to discover parameter names, e.g., bytecode compiled with `-parameters`. Using `#p0` or `#a0` keeps examples independent of parameter-name metadata.

**`#result` is unavailable inside `@Cacheable`'s `condition`** because the method has not run yet. If the decision depends solely on inputs, choose `condition`; if it depends on the return value, choose `unless`.

### 4.3. `condition` does not choose which cached value to return

Suppose the cache already holds a value under `customerById::42`, while the current call has `condition=false` via a control parameter:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p1"
)
public CustomerDto findCustomer(String id, boolean useCache) {
    return loadCustomer(id);
}
§§§

With `findCustomer("42", false)`, Spring skips reading the cache even though Redis holds an entry. `condition` is a **gate into the caching mechanism**, not a post-read data filter.

If multiple business variants share the same cache name, design conditions and keys consistently so data is never accidentally shared across tenants, languages, permissions, or response variants.

## 5. `unless`: vetoing storage once the result is known

### 5.1. Example skipping null results

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

If the repository finds no customer, the method returns `null`; `unless` evaluates to `true`, so Spring **does not write** that result into Redis Cache.

On a subsequent call with the same ID:

- Because no cache entry was written previously, the next call reaches the method again.
- If data was created between the two calls, the new call can see the newly created record.
- In return, many requests asking for a nonexistent ID will produce many reads against the canonical data source.

### 5.2. Skipping caching based on business status

Consider a record type:

§§§java
public record CustomerDto(
        String id,
        String displayName,
        boolean active
) {}
§§§

Cache only active DTOs:

§§§java
@Cacheable(
    cacheNames = "activeCustomerById",
    key = "#p0",
    unless = "#result == null || !#result.active()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Explanation:

- `#result == null` guards against missing data.
- `||` short-circuits, avoiding calling `active()` on `null`.
- `!#result.active()` evaluates to `true` for inactive customers, so those results are not cached.
- Valid customers with `active() == true` can be cached unless rejected by another policy.

Distinguish **state at cache miss time** from **state after an entry is cached**. When a customer transitions from active to inactive, a previously cached entry does not disappear automatically merely because `unless` is declared. Proper eviction, TTL, or cache update strategies are required.

### 5.3. `unless` does not prevent method execution

| Situation | Does the method run? | Is the result written to cache? |
|---|---|---|
| Cache miss, `unless=false` | Yes | Yes, if backend allows |
| Cache miss, `unless=true` | Yes | No |
| Cache hit | No (for standard `@Cacheable`) | No write needed; `unless` does not re-evaluate existing entries |
| `condition=false` | Yes | No |
| Method throws exception | Yes | No normal result to cache |

Adding `unless` to exclude `null` values **does not make the method run again if the cache already contains a `null` entry written by an earlier version**. Changing policy for existing cached data requires handling the old entries.

## 6. Combining `condition` and `unless`

A method can use both:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null || !#result.active()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Interpretation rules:

1. Invalid ID → bypasses cache, still runs method; the method itself is responsible for errors/appropriate return values.
2. Valid ID, Redis has entry → returns entry immediately; method does not run, `unless` is not re-evaluated.
3. Valid ID, Redis has no entry → runs method.
4. Method returns `null` or inactive DTO → does not write cache.
5. Method returns active DTO → writes cache per Redis Cache TTL and serializer.

Truth table for a **cache miss**:

| `condition` | Method result | `unless` | Cache action |
|---|---|---|---|
| `false` | Any normal result | Not evaluated | Skip cache |
| `true` | Active DTO | `false` | Write DTO |
| `true` | Inactive DTO | `true` | Do not write |
| `true` | `null` | `true` | Do not write |
| `true` | Exception | No result | Do not write normal result |

`condition` and `unless` are not a two-way data filter re-applied on every cache hit. They are two checkpoints controlling cache participation and acceptance of **new results**.

## 7. Caching `null` values is an intentional decision

### 7.1. "No data" can be a useful result

Consider looking up a customer by ID. If ID `404` does not exist, a lookup returns `null`. Under high traffic, if every request hits the database only to discover "not found," the data source bears unnecessary load.

Temporarily storing a "not found" outcome to respond quickly next time is called **negative caching**.

§§§text
Call 1:
findCustomer("404") -> Redis miss -> DB: not found -> store null marker

Call 2:
findCustomer("404") -> Redis hit (logical null value) -> skip DB
§§§

Yet negative caching carries a risk: if customer `404` is created in the database after the initial lookup, users may keep receiving `null` until the cache entry expires or is evicted.

### 7.2. Redis keys do not store "Java null" directly

Redis has binary value types like String, Hash, Set..., not a dedicated Redis type meaning **Java `null`**. To cache a null result, Spring Cache/`RedisCache` represents it via an implementation-managed **marker/sentinel**, then serializes that marker as Redis data.

Spring Data Redis converts `null` values in accordance with the cache abstraction (for example, internally using `NullValue`). When reading back, the cache abstraction converts that representation back to logical `null` for the caller.

Therefore:

- **Redis cache miss**: no valid cache entry exists for the key.
- **Cache hit with logical `null`**: an entry exists recording that a prior lookup found no result.
- Both cases cause a Java method to return `null`, yet method invocation behavior and canonical data-source cost differ.

Do not use `redis-cli GET` to guess independently whether a serialized payload is `null`. The serializer may be the JDK serializer or another format, and the stored value may be binary data.

### 7.3. How does the Cache API distinguish a miss from a cached null?

At the Spring Cache API level:

§§§java
org.springframework.cache.Cache cache =
        cacheManager.getCache("customerLookup");

if (cache == null) {
    throw new IllegalStateException("Cache region is missing");
}

org.springframework.cache.Cache.ValueWrapper wrapper =
        cache.get("404");

if (wrapper == null) {
    // Cache miss: no entry exists.
} else if (wrapper.get() == null) {
    // Entry exists: cached result is null.
} else {
    // Entry exists containing a non-null value.
}
§§§

This is how `Cache.ValueWrapper` distinguishes them under the `Cache.get(key)` contract. Applications using `@Cacheable` normally do not write this code themselves; the Spring Cache interceptor handles it.

## 8. Default policy and Redis Cache configuration

### 8.1. Default RedisCacheConfiguration allows caching null

In Spring Data Redis, `RedisCacheConfiguration.defaultCacheConfig()` permits caching null results via the cache abstraction by default. In addition, it applies other defaults for prefix, serializer, and TTL; depending on Spring Boot version and application configuration, the final `RedisCacheManager` may be customized further.

Note carefully: **`unless="#result == null"` still takes effect even when Redis Cache allows nulls**. `unless` blocks the result at the annotation layer before the cache backend is asked to store it.

Conversely, if `unless` does not block it while the backend forbids nulls, a `put(null)` call may be rejected according to the backend contract. Thus, when explicitly disabling null caching on methods that can return null, configure annotations cleanly rather than expecting `RedisCacheManager` to silently ignore every null without effect.

### 8.2. Application-wide configuration via Spring Boot properties

To **disallow** storing nulls in Redis Cache:

§§§yaml
spring:
  cache:
    type: redis
    redis:
      cache-null-values: false
      time-to-live: 10m
  data:
    redis:
      host: localhost
      port: 6379
§§§

`spring.cache.redis.cache-null-values: false` is a Spring Boot Redis Cache property, not a direct Redis server command. It applies the default policy to the auto-configured cache manager. `time-to-live: 10m` specifies the TTL for cache entries under this configuration.

To **enable negative caching**, you can set:

§§§yaml
spring:
  cache:
    type: redis
    redis:
      cache-null-values: true
      time-to-live: 30s
§§§

These two YAML snippets represent **two mutually exclusive alternatives**; do not copy both into the same file. Here `30s` TTL is an example limiting how long not-found results linger; if the same `CacheManager` shares one TTL across all entries, non-null results are also subject to that TTL.

### 8.3. Direct configuration with RedisCacheManager

If writing Java configuration instead of Boot properties:

§§§java
package com.example.demo.cache;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
§§§

This configuration forbids storing nulls for caches using the manager's default configuration. It fits when the entire application agrees nulls should not be cached. When declaring a custom `RedisCacheManager` bean, understand it may replace or alter Spring Boot's auto-configuration path, so pick one clear configuration approach.

### 8.4. Configuring two cache regions with different TTLs and null policies

An application frequently needs:

- `customerById`: cache valid DTOs for 10 minutes, do not cache nulls.
- `customerLookup`: allow nulls to reduce queries for nonexistent IDs, 20-second TTL.

With Spring Boot Redis auto-configuration, you can use a customizer:

§§§java
package com.example.demo.cache;

import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheRegionsConfig {

    @Bean
    public RedisCacheManagerBuilderCustomizer cacheRegions() {
        return builder -> builder
                .withCacheConfiguration(
                        "customerById",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(10))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "customerLookup",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofSeconds(20))
                );
    }
}
§§§

`customerLookup` does not call `disableCachingNullValues()`, so it relies on the default configuration allowing nulls. The example uses Spring Boot Redis Cache auto-configuration and **does not simultaneously enable the global `cache-null-values: false` setting from Section 8.2** to avoid conflicting policy layers. This Java configuration is also unnecessary if only a single cache region and a single shared TTL are needed.

Recent versions of Spring Data Redis support dynamic TTLs via `RedisCacheWriter.TtlFunction`; however, that is an advanced configuration dependent on version and value detection. Two cache regions with clear policies are usually easier to understand when starting out.

## 9. Two strategies when a method can return null

### 9.1. Strategy A: do not cache nulls

Use when records may be created shortly after lookup, absences are transient, or the underlying data layer can absorb misses:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Pairing this with `disableCachingNullValues()` on the `customerById` region makes the policy explicit in both annotations and the backend.

**Consequence:** nonexistent IDs always hit the canonical data source when invoked via the cache unless another cache layer exists. This is a good choice when immediate visibility of newly created records matters more than the cost of not-found misses.

### 9.2. Strategy B: short-term null caching

Use when many requests repeat the same missing ID, lookup cost is significant, and the application tolerates a short delay before seeing new records:

§§§java
@Cacheable(
    cacheNames = "customerLookup",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Notice `unless="#result == null"` is intentionally **omitted**. The `customerLookup` cache region must permit nulls; a short TTL (e.g., 20 seconds) limits how long stale missing results persist.

When creating or updating customers, add an eviction/update rule for the corresponding key to shorten staleness windows:

§§§java
@CacheEvict(cacheNames = "customerLookup", key = "#p0")
public void createOrReplace(String id, CreateCustomerRequest request) {
    repository.save(toEntity(id, request));
}
§§§

`CreateCustomerRequest`, `toEntity`, and `repository` are application business components, not built-in Spring Data Redis APIs. The example illustrates the pattern: after source data is successfully written, remove the cached "not found" entry if that key may have been cached earlier.

**Do not use negative caching to mask infrastructure failures.** Methods should distinguish "not found" from database connection errors. If the database fails and the service catches the exception and returns null, Spring Cache may record null as if the record genuinely did not exist, causing prolonged incorrect results.

## 10. `Optional<T>` and the meaning of `#result`

Spring Cache supports `@Cacheable` methods returning `Optional<T>`. When using `unless`, `#result` represents the **inner business value inside the Optional**, not the method's `Optional` wrapper.

Example:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    unless = "#result == null"
)
public Optional<CustomerDto> findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from);
}
§§§

When `findCustomer("42")` returns `Optional.of(customer)`, `#result` evaluates against `customer`.

When `findCustomer("999")` returns `Optional.empty()`, `#result` is treated as `null` in `unless`. Therefore `unless="#result == null"` works to skip caching "not found" for both nullable DTO methods and `Optional<DTO>` methods.

An expression that fails its intent:

§§§java
// Intent: "do not cache Optional.empty()".
// However, #result is not the Optional wrapper.
@Cacheable(
    cacheNames = "customerById",
    unless = "#result.isEmpty()"
)
public Optional<CustomerDto> findCustomer(String id) {
    return repository.findById(id).map(CustomerDto::from);
}
§§§

This expression violates Spring Cache's `#result` contract and can fail when the inner value is absent. Use `#result == null` for this case.

For `CompletableFuture`, Reactor `Mono`, or `Flux`, recent Spring Framework versions provide specific asynchronous caching adaptations. Do not assume all SpEL expressions operate on wrappers or completion timing identically to synchronous methods; check your Spring Framework version and exact return-type contract.

## 11. `@CachePut`, `@CacheEvict`, and limitations of `unless`

### 11.1. `@CachePut`: method always executes

`@CachePut` is used when you want to invoke the method and update the cache with its new result:

§§§java
@CachePut(
    cacheNames = "customerById",
    key = "#result.id()",
    condition = "#p0 != null",
    unless = "#result == null"
)
public CustomerDto updateCustomer(UpdateCustomerCommand command) {
    return performUpdate(command);
}
§§§

In the example, `UpdateCustomerCommand` is a valid application-defined request, and `performUpdate` returns `CustomerDto` or null. If `key` references `#result`, it runs in the post-execution context once a valid result is returned. For methods that may return null, keying from a stable parameter such as `key="#p0.id()"` is usually simpler and avoids dereferencing `#result.id()` when null.

Key point: `@CachePut` **never uses a cache hit to skip the method**. `condition` decides whether to perform the cache update, and `unless` can veto storing the new result. Depending on business semantics, if an update fails and returns null, an old cache entry may still remain; decide on an eviction strategy accordingly.

### 11.2. `@CacheEvict`: removing cached data

Example:

§§§java
@CacheEvict(cacheNames = "customerById", key = "#p0")
public void deleteCustomer(String id) {
    repository.deleteById(id);
}
§§§

By default, eviction runs after the method finishes successfully. You can set `beforeInvocation=true` to evict before the method regardless of outcome, but understand the consequences on business errors.

`unless` is not a mechanism for deciding whether to delete old entries in `@CacheEvict`; it belongs to vetoing a **cache put**. When rolling out a new "do not cache null" policy, existing null entries require TTL expiration or targeted eviction.

### 11.3. `sync=true` cannot be combined with `unless`

`@Cacheable(sync = true)` asks the cache provider to coordinate computing a cache miss for the same key when supported by the backend. However, Spring Cache enforces that `sync=true` **does not support `unless`**, because value caching is tied to the `get(key, Callable)` path.

Invalid configuration example:

§§§java
// Do not use this combination.
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

If you need both "cache stampede" protection and exclusion of null results, consider handling it at the cache/provider layer or building a dedicated protection mechanism with a clear contract. Do not assume enabling `sync=true` alone satisfies null-caching exclusion.

## 12. When caching null helps and when it hurts

| Scenario | Starting recommendation | Explanation |
|---|---|---|
| Repeated lookups of nonexistent IDs | Cache null with **short TTL** | Reduces load from futile requests |
| Records often created right after first read | Do not cache null, or evict proactively | Prevents "not found" from sticking |
| Expensive remote service query, stable misses | Consider negative caching | Saves network calls and upstream load |
| User/tenant-sensitive data | Include full context in key and enforce authorization | Cross-context data leakage is worse than null decisions |
| Data missing due to upstream outage | **Do not cache as null** | Avoids turning transient outages into "nonexistent" results |
| System tolerates several seconds of staleness | Short-TTL null caching acceptable | Accepts brief delay seeing new records |
| System requires immediate visibility after creation | Do not cache null, or evict on write | TTL alone may miss SLA |
| Millions of random nonexistent keys scanned | Be cautious with negative caching | Large count of negative entries can bloat Redis memory |
| Null result can become non-null solely via an event | Use event eviction/versioning or skip null | Prevents stale outcomes |
| Clear create/delete/status-change rules exist | Design eviction per operation | `unless` does not alter existing entries |

Neither "always cache null" nor "never cache null" fits every product. Weigh miss cost, state-change frequency, acceptable TTL, negative key volume, and synchronization on creation.

### 12.1. How long does stale negative cache persist?

Suppose:

§§§text
t = 0s   GET customer 42 -> absent -> cache null (30s TTL)
t = 5s   Create customer 42 in database
t = 6s   GET customer 42 -> null cache hit
t = 30s  Null entry TTL expired; next read queries database
§§§

Without eviction on customer creation, users can receive missing results until TTL expires. Short TTLs provide a simple **upper bound on staleness**, though real behavior depends on failover, key expiration, cache refresh, and other cache layers.

You can evict immediately upon successful creation, provided multi-instance deployments share the **same Redis cache**, cache names, and keys; if other instances also hold local caches, distributed eviction must be designed separately.

### 12.2. Caching null does not solve every cache stampede

If nulls are not cached, multiple requests for the same nonexistent ID can hit the database concurrently. Caching null shields requests arriving **after the first result is written**, yet does not necessarily prevent concurrent initial requests from missing within a narrow window.

Stampede protection may require load coordination, single-flight, computation locking, or context-aware rate limiting. Each brings its own overhead and failure modes. Measure duplicate key call rates and actual cost before adding complexity.

## 13. TTL configuration and policy issues across different outcomes

A simple `RedisCacheConfiguration.entryTtl(Duration)` applies its TTL to entries of that cache region. If a region caches both DTOs and nulls, both normally share the region's configured TTL.

If requirements dictate:

- Found result: cache 10 minutes.
- Missing result: cache 10 seconds.

then setting a single `time-to-live: 10m` will not give `null` a shorter TTL automatically. Options:

1. Use **separate cache regions or storage mechanisms** for present vs. absent results with explicit routing.
2. Use `RedisCacheWriter.TtlFunction` if your Spring Data Redis version supports it and fits the use case, ensuring dynamic TTL inspects the null representation accurately.
3. Do not cache null and accept re-querying the data source.
4. Implement an explicit negative-cache policy in the service if business characteristics demand full control.

Classifying nulls in a `TtlFunction` requires knowing how Spring Cache adapts values; do not assume every null representation remains Java `null` at that layer.

A separate cache for "no data" may require two lookup layers. Weigh total complexity against actual query savings.

## 14. Common configuration mistakes

| Symptom | Possible cause | Remediation |
|---|---|---|
| Method still runs every time despite `@Cacheable` | `condition=false`, repeated cache misses, `unless=true`, caching disabled, or self-invocation | Verify interceptor flow, conditions, cache name/key, and call path |
| Null gets cached despite adding `unless` | Null entry already existed before deploy, another method shares cache/key, or annotation wasn't intercepted | Check eviction, keys, and Spring proxy routing |
| Error when method returns null | Backend set `disableCachingNullValues` while annotation tries to store null | Add `unless="#result == null"` or adjust cache policy |
| `condition` tries to use `#result` | Result does not exist before method call | Move result-dependent logic to `unless` |
| `unless` invokes method on `null` | E.g., `#result.active()` without null guard | Use `#result == null || ...` |
| `unless="#result.isEmpty()"` fails with `Optional` | `#result` is the unwrapped value inside Optional | Use `#result == null` for empty |
| Cache hit returns data violating new policy | `unless` only vetoes new writes | Evict old entries or switch to a new key namespace/version |
| Still reads null right after creating record | Negative cache entry still within TTL | Evict cache key on successful create/update |
| Failure combining `sync=true` + `unless` | Spring Cache forbids the combination | Drop `unless` or use a different miss-coordination mechanism |
| Two users read wrong data | Key lacks tenant/user/security context | Design keys and access control with proper scope |
| Serializer mismatch prevents reading Redis entries | CacheManager or app changed serializer | Coordinate schema/serializer migration and purge old cache as needed |
| `@Cacheable` has no effect on internal call | Self-invocation bypasses Spring proxy | Call via appropriate Spring-managed bean/interface |
| Method errors cached as "not found" null | Service layer swallows upstream exception and returns null | Separate Not Found from Outage so real errors propagate properly |

### 14.1. Watch out for self-invocation

Example:

§§§java
@Service
public class CustomerService {

    public CustomerDto loadFromApi(String id) {
        return findCached(id); // Internal call; proxy caching may be skipped.
    }

    @Cacheable(cacheNames = "customerById", key = "#p0")
    public CustomerDto findCached(String id) {
        return loadCustomer(id);
    }
}
§§§

In standard Spring proxy mode, calling directly via `this` within the same instance bypasses the caching interceptor. For caching to apply, another Spring bean must invoke the public method on the proxied bean holding the annotation. Do not conclude `condition` or `unless` is wrong when the annotation was skipped due to the call path.

### 14.2. Do not use short cache keys for permission-dependent data

For instance, an API `findDashboard(userId, tenantId, locale)` using only `key="#p0"` can mix data across tenants or locales. Cache hits happen **before** the method, so permission checks placed solely inside the method body may never execute on a cache hit.

The design must enforce authorization in a layer invoked on every request while ensuring keys capture every data variant and never expose restricted info. `condition` can limit caching in some cases, yet **never replaces access control**.

## 15. Observing real behavior of condition, unless, and null

An intuitive learning approach is tracking how many times the method executes when calling the same key repeatedly.

Illustrative service with an execution counter:

§§§java
@Service
public class CustomerLookupService {

    private final java.util.concurrent.atomic.AtomicInteger loads =
            new java.util.concurrent.atomic.AtomicInteger();

    @Cacheable(
        cacheNames = "customerById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()",
        unless = "#result == null"
    )
    public String findName(String id) {
        loads.incrementAndGet();

        if ("404".equals(id)) {
            return null;
        }

        return "Customer-" + id;
    }

    public int loadCount() {
        return loads.get();
    }
}
§§§

Use another bean to invoke `findName` via the Spring-managed proxy (do not self-invoke inside the same class). Expected logic:

| Call | Input | Initial cache state | Result | Method execution count |
|---|---|---|---|---|
| 1 | `"42"` | Miss | `"Customer-42"` | Increments by 1 |
| 2 | `"42"` | Hit | `"Customer-42"` | Unchanged |
| 3 | `"404"` | Miss | `null` | Increments by 1 |
| 4 | `"404"` | Still miss due to `unless` | `null` | Increments by 1 |
| 5 | `""` | `condition=false` | `"Customer-"` (simulated example) | Increments by 1 |

This example only illustrates annotation behavior, not sound validation logic. In production systems, blank IDs should normally be rejected by domain rules.

If `unless` is removed and null caching is permitted, the third call creates a null entry; the fourth call can hit that entry without incrementing the counter until TTL/eviction occurs.

To observe in production, monitor at least: cache hits/misses, database calls by result category, not-found rates, cache entry counts, TTLs, evictions, latency, and record creation events after negative hits. Avoid logging full cache values if they contain sensitive data.

## 16. Decision workflow for a method to cache

§§§mermaid
flowchart TD
    A["Method returns data or null"] --> B{"Which inputs should be cached?"}
    B --> C["Write condition on parameters"]
    C --> D{"What does a null result mean?"}
    D -->|Upstream error| E["Distinguish errors; do not return null as Not Found"]
    D -->|Genuine not found| F{"Is stale Not Found acceptable?"}
    F -->|No| G["Use unless: #result == null"]
    F -->|Yes| H["Allow null + short TTL + evict when new data arrives"]
    D -->|Never happens| I["Can disallow null in RedisCacheManager"]
    G --> J["Design TTL, key, serializer, eviction"]
    H --> J
    I --> J
    E --> J
    J --> K["Measure hit/miss and test operational edge cases"]
§§§

A concise procedure to apply:

1. Define the **method contract**: valid input, found result, not-found, exception.
2. Pick `condition` based on **parameters and pre-invocation context**.
3. Pick `unless` based on **post-invocation output**; use `#result == null` when avoiding caching not-found.
4. Pick the `null` policy on the Redis cache backend, appropriate TTL, and corresponding cache region.
5. Design eviction/updates for create/update/delete operations.
6. Ensure cache keys never mix data variants or bypass authorization.
7. Observe cache hits/misses and transitions when data goes from "nonexistent" to "existent."

## 17. Summary

**`condition` decides whether a call participates in caching before the method runs; `unless` decides whether to write a new result to cache after the method returns.** With `@Cacheable`, cache hits normally skip the method and do not re-run `unless` on existing entries.

Meanwhile, **deciding whether to cache `null` values** is a separate policy. Allowing null caching reduces load for not-found lookups but risks serving stale results when records are later created; skipping nulls preserves better freshness at the cost of extra source queries. Spring Data Redis can store nulls via an internal representation managed by the cache abstraction; `RedisCacheConfiguration.disableCachingNullValues()` and Spring Boot's `spring.cache.redis.cache-null-values` property specify backend policy.

A sound configuration coordinates **`condition` on inputs, `unless` on outputs, TTLs, keys, eviction, and distinguishing not-found from system errors**. Making choices grounded in specific business characteristics lets caching reduce load without masking new data or producing prolonged incorrect results.
