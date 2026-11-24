# Testing Cache Keys, TTL, and Data Isolation Between Users or Tenants

> **Module:** Spring Boot – testing  
> **Group:** Additional integration  
> **Topic:** Cache keys, TTL, and data isolation between users or tenants  
> **Goal:** Design security-scoped cache keys, test cache hit/miss/invalidation, prove real provider TTL, prevent cross-tenant data leakage using Spring Cache + Redis + Testcontainers, and separate security authorization from caching. Hands-on examples use Java 17, Spring Boot 3.5, Maven, JUnit Jupiter, and Redis 7.

## 1. Why is the cache an important testing boundary?

A cache is not just a performance optimization; a wrong cache key can turn a valid request into a **data leak across users or tenants**.

Suppose two tenants both have a profile with ID `42`:

```text
Tenant "north": profileId = "42" -> "NORTH-42"
Tenant "south": profileId = "42" -> "SOUTH-42"

Correct data source:
  repository.find("north", "42") -> "NORTH-42"
  repository.find("south", "42") -> "SOUTH-42"

WRONG cache key: "profiles::42"
  request north/42 -> cache write "NORTH-42"
  request south/42 -> cache hit  "NORTH-42"   <-- LEAK!

CORRECT cache key: includes tenant + data type + profileId
  "profiles::v1:t:5:north:p:2:42" -> "NORTH-42"
  "profiles::v1:t:5:south:p:2:42" -> "SOUTH-42"
```

Even when the database query has a proper `WHERE tenant_id = ?`, a `@Cacheable(key="#profileId")` can return data from the cache **before the database query is ever executed**. That allows all repository unit tests to pass while a system sharing Redis remains unsafe.

Four contracts need to be tested separately:

1. **Identity / scope:** Which tenant, user, record, projection, locale, or role/policy version does the cache entry belong to?
2. **Freshness:** Cache hits work properly; updates/evictions and TTL prevent stale data from persisting past allowed limits.
3. **Correctness:** Misses query the right data source, return the right result, and do not collide keys across caches.
4. **Security:** Tenant identity is authenticated and authorized from a trusted context; caching does not replace authorization.

### 1.1. Spring Cache flow

```text
HTTP / message / business caller
              |
          authorization
              |
        trusted tenantId
              |
       Spring AOP cache proxy
              |
     cache name + logical key
              |
          RedisCacheManager
              |
       Redis GET / cache hit?
          /            \
         YES           NO
          |             |
      return value    service method
                          |
                    tenant-scoped repository
                          |
                     Redis SET + TTL
                          |
                       return
```

**Special warning:** When the Spring caching interceptor returns a cache hit, the body of the `@Cacheable` method is **not executed**. Therefore, checking permissions *only inside the body* of a cached method risks being skipped on a cache hit. Always perform authentication/tenant authorization **before cache interception**, such as in an API/security facade or an advice with tested ordering, and then pass the verified tenant into the cached service.

## 2. How are Spring Cache keys formed?

### 2.1. `@EnableCaching`, `@Cacheable`, and proxies

The Spring Cache abstraction only intercepts calls when cache advice is enabled, typically via `@EnableCaching`. When calling a **Spring-managed proxy bean** from outside, `@Cacheable` queries `CacheManager`:

- Entry exists for cache name/key: returns the cached value; the method body is not invoked.
- Entry does not exist: runs the method body, then writes the result to the cache subject to `condition`/`unless`/provider config.
- Cache eviction/update can use `@CacheEvict` or `@CachePut`.
- `@Caching` can group multiple operations, though each key must be clearly defined.

An object created via `new Service(...)` in a pure unit test is not wrapped by Spring AOP, so cache annotations have no effect. Similarly, **self-invocation** `this.cachedMethod(...)` typically bypasses default proxy interception.

### 2.2. Default `SimpleKeyGenerator`: convenient, not a security contract

When neither `key` nor `keyGenerator` is declared:

- No arguments: `SimpleKey.EMPTY`.
- One suitable argument: that argument itself serves as the key.
- Multiple arguments: a `SimpleKey` containing all parameters.

Example:

```java
@Cacheable("profiles")
public String find(String tenantId, String profileId) {
    //...
}
```

With these two parameters, the default key already distinguishes tenant and profile. However, if the API is refactored to `find(String profileId)` with the tenant held in a `ThreadLocal`/auth context, the default key **omits the tenant**. Or if a developer adds `key = "#profileId"`, it drops the tenant from the key even though the method still has two arguments.

For tenant-sensitive data, define an **explicit and stable key contract**; write tests proving that tenant A and tenant B with the same record ID never share a cache entry. Do not rely implicitly on the current method signature.

### 2.3. SpEL keys

You can use positional indices independent of how the Java compiler stores parameter names:

```java
@Cacheable(
    cacheNames = "profiles",
    key = "T(com.example.cachelab.CacheKeys).profile(#p0, #p1)")
public String get(String tenantId, String profileId) {
    return repository.find(tenantId, profileId);
}
```

This is a snippet inside a Spring bean, not a standalone file. `#p0` and `#p1` are the first and second arguments respectively; `T(...)` calls a static utility class. Centralizing the key builder ensures `@Cacheable`, `@CacheEvict`, and `@CachePut` share the exact same contract.

In practice, avoid building keys via unescaped string concatenation when IDs may contain delimiter characters:

```text
bad: tenant + ":" + id

tenant "a:b", id "c"    => "a:b:c"
tenant "a",   id "b:c"  => "a:b:c"
```

Better practices include: canonicalized/validated IDs, length-prefix encoding, tagged fields, or stable binary encoding. Do not hash the entire key and drop the tenant from audit context without understanding collision, security, and rotation trade-offs.

## 3. Designing security-scoped cache keys

### 3.1. Dimensions to consider

A cache key must distinguish **every factor that changes the response content**:

| Dimension | When needed? | Example |
| --- | --- | --- |
| Environment / application namespace | Multiple apps/envs share one Redis | `prod:billing` vs `test:billing` |
| Cache name / projection | Same ID with different value shapes | `profiles` vs `profileSummaries` |
| Tenant ID | Multi-tenant data | `north` vs `south` |
| User ID | Per-user values within the same tenant | `user-17` vs `user-18` |
| Record ID / natural key | Individual entity | `profile-42` |
| Permission/role/policy version | Response depends on permissions | `policy-v4` |
| Locale / currency / timezone | Personalized view | `vi-VN` vs `en-US` |
| Schema/cache version | Deploy changes serialization/semantics | `v2` |
| Filter/sort/page/projection | Query result varies by parameters | `page=2,sort=name` |

**Do not blindly add every dimension to every key.** Choose based on the *data contract*. For instance, a public catalog identical for all tenants can share keys if it contains no tenant-specific content or policy; customer profiles typically must not be shared.

### 3.2. Which tenant context is trustworthy?

A tenant ID from a query parameter or client-supplied HTTP header is **not inherently trustworthy**. In production:

1. Authenticate the principal/session/token.
2. Resolve the tenant the principal actually belongs to and verify active membership/authorization.
3. Use the verified tenant as the scope for cache lookup.
4. Query the repository with that **same** authorized tenant.
5. Cache and invalidation use the same scope.
6. If authorization changes, define how caches are invalidated or include a policy version.

**Never build a cache key from an arbitrary tenant ID and treat that as authorization.** If a user can set `tenantId = "south"`, a formally well-structured key still fails to protect south's data.

### 3.3. User-scoped vs. tenant-scoped

An admin and an end user in the same tenant may see different fields. If you cache a return value already filtered/masked by permissions, a key with only tenant+record can expose admin-only fields. Depending on design:

- Cache the **raw tenant entity** only inside a trusted backend and apply permissions/projection **after fetching from cache**; ensure downstream layers always enforce access control.
- Or cache the **authorized/view DTO** keyed by user/role/policy version, with invalidation when permissions change.
- Do not cache PII/tokens/secrets unnecessarily. Evaluate encryption, Redis ACL/TLS, access logs, retention, and data classification.
- Cache keys can also leak identifiers via metrics/logs; avoid putting tokens, passwords, or full emails into keys.

TTL does not replace authorization. A wrong-tenant entry that expires in 2 seconds can still cause an incident during those 2 seconds.

### 3.4. Cache name prefix vs. tenant prefix

Spring Data Redis prefixes Redis keys by default with the cache name, in the form:

```text
profiles::<logical-key>
```

This prefix prevents `profiles` and `profileSummaries` from colliding when using the same logical key. **It does not automatically add a tenant.** Tenant/user/record dimensions must still be in the logical key or implemented via an equivalent namespacing mechanism.

Do not casually disable `spring.cache.redis.use-key-prefix` on a shared Redis instance. If you write a custom `RedisCacheManager`, preserve prefix isolation and test the real path.

## 4. TTL: expiration belongs to the cache provider, not just the annotation

### 4.1. `@Cacheable` has no built-in TTL parameter

Spring Framework's `@Cacheable` has no universal `ttl=...` attribute. TTL depends on the provider: Redis, Caffeine, Ehcache, Hazelcast, etc.

With Spring Boot 3.5 and `RedisCacheManager` auto-configuration, you can configure:

```properties
spring.cache.type=redis
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
```

- `time-to-live=10m`: written entries expire in Redis after 10 minutes.
- `cache-null-values=false`: do not cache null values under the corresponding provider config.
- `use-key-prefix=true`: keeps the cache name prefix (usually the default).
- `spring.cache.type=redis`: requires the Redis cache provider in projects with the proper dependencies.

**The default `RedisCacheConfiguration` does not necessarily set an expiration**; if forgotten, entries can live until evicted by memory pressure or administrative action. Tests must verify the *actual TTL in Redis*, not just read the properties file.

### 4.2. Per-cache TTL via `RedisCacheManager`

If different data types require different TTLs:

```java
@Bean
RedisCacheManager cacheManager(
        RedisConnectionFactory factory) {
    RedisCacheConfiguration defaultConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(5))
                    .disableCachingNullValues();

    Map<String, RedisCacheConfiguration> perCache = Map.of(
            "profiles", defaultConfig.entryTtl(Duration.ofMinutes(10)),
            "permissions", defaultConfig.entryTtl(Duration.ofSeconds(30)));

    return RedisCacheManager.builder(factory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(perCache)
            .build();
}
```

This is an **advanced snippet** requiring `RedisCacheManager`, `RedisConnectionFactory`, `RedisCacheConfiguration`, `Duration`, `Map`, `@Bean` imports, and a Spring configuration class. Do not add this snippet to the runnable project below, as the main project uses Boot auto-configuration for a single cache to keep verification straightforward.

Note that replacing the auto-configured `RedisCacheManager` bean may cause `spring.cache.redis.*` properties to stop applying automatically as expected; test the actual configuration rather than relying on reading the properties file.

### 4.3. TTL vs. TTI

- **TTL (time-to-live):** lifetime measured from write or refresh according to the provider; a cache hit normally **does not extend TTL**.
- **TTI (time-to-idle):** expires after a period of no access; may require provider-specific support.
- Redis natively supports expiration/TTL; Spring Data Redis provides TTI emulation using commands like `GETEX` when the corresponding config and compatible Redis version are enabled.
- Do not equate a 10-minute TTL with "keep up to 10 minutes since last read" unless TTI is truly configured.
- TTL does not immediately handle stale authorizations, revoked consent, or data deletion requests. Such events may require active invalidation.

### 4.4. Redis TTL can be inspected via `PTTL`

Redis TTL/expiration semantics:

| Redis TTL result | Meaning |
| ---: | --- |
| Positive number | Remaining time to live |
| `-1` | Key exists with no expiration |
| `-2` | Key does not exist |
| `0` or near 0 | May be right at expiration; do not assert exact milliseconds |

With Spring Data Redis:

```java
Long ttlMs = redisTemplate.getExpire(
        redisKey, TimeUnit.MILLISECONDS);
```

A sound test verifies a positive TTL not exceeding the configured duration, then **waits until the key actually disappears** using bounded polling/Awaitility. Do not assert an exact 4000ms TTL because network/JVM/CI time elapses after the `SET` command.

## 5. Invalidation: TTL does not replace cache deletion on data updates

There are three mutation paths to protect:

1. **Read:** `@Cacheable` lookup; on miss, fetch from data source; on hit, skip data source.
2. **Update:** `@CacheEvict` removes the exact tenant+record key after a successful update, or `@CachePut` updates the cache accurately.
3. **Delete/revoke:** Invalidate immediately when the business contract requires it; do not leave stale entries waiting for TTL if content was deleted or access revoked.

Example:

```java
@CacheEvict(
    cacheNames = "profiles",
    key = "T(com.example.cachelab.CacheKeys).profile(#p0, #p1)")
public void update(String tenantId, String profileId, String value) {
    repository.update(tenantId, profileId, value);
}
```

If `@Cacheable` uses `tenant+id` as its key while `@CacheEvict` uses only `id`, stale data is never properly removed. And if an update uses `allEntries=true` or `cache.clear()`, it wipes data across all tenants, hurting performance and causing coordination issues; avoid it when invalidating a single record.

### 5.1. Eviction and transaction ordering

`@CacheEvict` by default executes **after a successful invocation** of the method. This does not guarantee atomicity between a database commit and Redis eviction. With transactional updates, you may need a transaction-aware cache manager or explicit after-commit events/outbox/invalidation logic.

A transaction may roll back while the cache has already been modified if advice ordering is wrong; conversely, if the DB commits and eviction fails, the cache becomes stale. Write integration tests for transaction boundaries when data is sensitive and critical.

### 5.2. Stampede, concurrent loads, stale-while-revalidate

When many requests hit a cache miss simultaneously:

- Multiple threads may hit the data source concurrently, causing a **cache stampede**.
- `@Cacheable(sync=true)` can coordinate loading with certain cache providers, but does not automatically guarantee distributed locking or exactly-once execution across all instances.
- Default `RedisCacheWriter` has its own concurrency semantics; do not assume atomicity across multi-command sequences.
- Too short a TTL causes frequent misses; too long a TTL prolongs stale data.
- Jittering TTL can reduce synchronized mass expirations when supported by the provider/config and design.
- For authorization-related data, prioritize correctness, revocation, and containment over raw hit ratio.

## 6. Cache testing: minimum matrix

| Case | Input and setup | Key assertion |
| --- | --- | --- |
| Cache miss | Tenant north/profile 42 first time | Repository loads = 1, value correct |
| Cache hit | Same tenant/profile second time | Same value, repository load count unchanged |
| Cross-tenant | north/42 then south/42 | Two distinct, accurate values |
| Cross-record | north/42 then north/43 | Entries are not shared |
| Wrong key negative | Key using only ID in simulation test | Proves collision/leakage can happen |
| TTL exists | Read Redis PTTL after cached write | Positive, bounded TTL |
| Expiry | Bounded wait until key expires | Subsequent read loads data source again |
| Tenant-specific invalidation | Update north/42 | Cached south/42 is not evicted |
| User/role-specific response | Same tenant, different permissions | Authorized views are not wrongly shared |
| Null/negative caching | Missing record / permission denied | Follows cache-null policy, avoids stale data |
| Transaction rollback | Update then roll back | Cache reflects source of truth |
| Multiple app instances | Shared Redis, separate JVM caches | Namespace and serialized value valid |

**Two complementary forms of evidence:** unit tests on `CacheKeys` protect composition/validation; Redis Testcontainers protects how Spring AOP + `CacheManager` + Redis actually handle hits, TTL, and eviction.

## 7. Java 17 + Spring Boot 3.5 + Redis Testcontainers project

This **runnable-design** project includes pure Java unit tests and integration tests with a real Redis instance (requires a Docker runtime). The data source is replaced by an in-memory repository **holding tenant-scoped data** to focus on testing the cache. This is not a full authentication/authorization example: callers of `service.get(tenantId, profileId)` assume `tenantId` was already authenticated in an upstream layer before the cache. Real systems must enforce this at the security boundary.

### 7.1. Test suite goals

There are **8 JUnit `@Test` methods**:

- **3 unit tests** verifying that the key builder never collides across tenants or records and rejects invalid IDs.
- **5 integration tests** with Redis: cache hit, tenant isolation, record isolation, single-tenant eviction, and real TTL + expiration.

All integration tests use an isolated Docker Redis container, contain no production credentials, and never flush a shared Redis instance.

### 7.2. Directory tree

```text
tenant-cache-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/cachelab/
    │   │   ├── CacheLabApplication.java
    │   │   ├── CacheKeys.java
    │   │   ├── ProfileRepository.java
    │   │   └── ProfileService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/cachelab/
            ├── CacheKeysTest.java
            └── ProfileCacheIntegrationTest.java
```

Public Java classes each have a matching filename in package `com.example.cachelab`.

### 7.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tenant-cache-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.awaitility</groupId>
            <artifactId>awaitility</artifactId>
            <scope>test</scope>
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

Purpose:

- `starter-cache`: Spring Cache abstraction/AOP infrastructure.
- `starter-data-redis`: Redis connection factory, `RedisCacheManager`/provider, `RedisTemplate`.
- `starter-test`: JUnit Jupiter, AssertJ, and Spring test.
- `spring-boot-testcontainers`: `@ServiceConnection` provides Redis connection details for the test container.
- `testcontainers` + `junit-jupiter`: Docker container lifecycle/test integration.
- `awaitility`: bounded polling for TTL expiration instead of fixed `Thread.sleep`.

Spring Boot parent manages compatible dependency versions. No HTTP starter or production Redis instance is needed.

### 7.4. `application.properties`

```properties
# src/main/resources/application.properties
spring.cache.type=redis
spring.cache.redis.time-to-live=30m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
```

This configures the Redis cache provider for the sample project. The integration test will override TTL down to 4 seconds to test expiration. Real production configurations must pick TTLs based on data type, staleness risk, and business policy; do not use 30 minutes as a blanket default for every cache.

### 7.5. `CacheLabApplication.java`

```java
// src/main/java/com/example/cachelab/CacheLabApplication.java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CacheLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }
}
```

`@EnableCaching` is essential: without cache advice enabled, `@Cacheable` annotations will not be intercepted. The hit/miss tests below will catch it if this annotation is missing.

### 7.6. `CacheKeys.java` — unambiguous tenant + record key contract

```java
// src/main/java/com/example/cachelab/CacheKeys.java
package com.example.cachelab;

public final class CacheKeys {

    private CacheKeys() {
    }

    public static String profile(
            String tenantId, String profileId) {
        requireId(tenantId, "tenantId", 32);
        requireId(profileId, "profileId", 64);

        return "v1:t:" + tenantId.length() + ":" + tenantId
                + ":p:" + profileId.length() + ":" + profileId;
    }

    private static void requireId(
            String id, String field, int maxLength) {
        if (id == null
                || id.length() > maxLength
                || !id.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException(
                    "Invalid " + field);
        }
    }
}
```

**Explanation:**

- The key includes schema version `v1` to manage semantic/serialization changes.
- Labels `t`/`p`, length prefixes, and both IDs eliminate ambiguity as the key format evolves.
- Validation blocks null, empty strings, uppercase letters, and non-whitelisted characters; do not silently trim or normalize issued identifiers without a unified policy.
- This is **input shape validation**, not tenant authorization; the user must still be verified for tenant access.
- Also never include passwords or tokens in cache keys, because Redis key names and logs can expose them.
- With default Spring `RedisCacheManager`, the physical Redis key prepends the cache name prefix `profiles::` before the logical key.

Do not use Java's `hashCode()` as a global key across versions/JVMs for collision-sensitive data; if hashing is needed to shorten keys, use proper encoding/namespacing and define collision risk and test vectors clearly.

### 7.7. `ProfileRepository.java` — test-only data source

```java
// src/main/java/com/example/cachelab/ProfileRepository.java
package com.example.cachelab;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

@Repository
public class ProfileRepository {

    private record Id(String tenant, String profile) {
    }

    private final ConcurrentMap<Id, String> values =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public ProfileRepository() {
        reset();
    }

    public String find(String tenantId, String profileId) {
        loads.incrementAndGet();
        return values.get(new Id(tenantId, profileId));
    }

    public void update(
            String tenantId, String profileId, String value) {
        values.put(new Id(tenantId, profileId), value);
    }

    public int loadCount() {
        return loads.get();
    }

    public void reset() {
        values.clear();
        values.put(new Id("north", "42"), "NORTH-42");
        values.put(new Id("north", "43"), "NORTH-43");
        values.put(new Id("south", "42"), "SOUTH-42");
        loads.set(0);
    }
}
```

The repository uses a composite `Id(tenant,profile)` so the data source is **properly scoped**; this is designed for the lesson, not production persistence. It helps simulate a critical bug: the database returns the right data, yet a cache key lacking the tenant still leaks data.

`loadCount()` measures data source calls, useful for proving real cache hits. Tests must not just compare return values, because identical values can mask a non-working cache.

### 7.8. `ProfileService.java` — key-consistent caching and eviction

```java
// src/main/java/com/example/cachelab/ProfileService.java
package com.example.cachelab;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final ProfileRepository repository;

    public ProfileService(ProfileRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "profiles",
            key = "T(com.example.cachelab.CacheKeys).profile(#p0,#p1)")
    public String get(String tenantId, String profileId) {
        return repository.find(tenantId, profileId);
    }

    @CacheEvict(
            cacheNames = "profiles",
            key = "T(com.example.cachelab.CacheKeys).profile(#p0,#p1)")
    public void update(
            String tenantId, String profileId, String value) {
        CacheKeys.profile(tenantId, profileId);
        repository.update(tenantId, profileId, value);
    }
}
```

**Key points:**

- `@Cacheable` keys include both tenant and profile; two tenants with the same `profileId` never share entries.
- `@CacheEvict` uses the **exact same key builder**; updating `north/42` does not evict `south/42`.
- Before updating, `CacheKeys.profile` validates input shape; it does not check tenant ownership.
- When `get` hits the cache, the repository does not run. Therefore, **never place an auth check only inside `get`** expecting it to run on every call.
- The test calls the Spring-injected bean so execution goes through the cache AOP proxy.
- Spring `@Cacheable` returns null when the repository finds nothing; because `cache-null-values=false`, nulls are not cached under the sample provider policy. Production must decide negative caching/missing data behavior based on business and security semantics.

### 7.9. Authorization boundary outside the cache — illustration

A production service/facade should resolve the tenant from the authenticated principal and verify membership **before** calling the cached bean:

```java
// Architectural snippet, not a file in the sample project:
public String profileForAuthenticatedUser(String profileId) {
    String tenantId = tenantResolver.requireAuthorizedTenant();
    return profileService.get(tenantId, profileId);
}
```

`tenantResolver` here represents a real application service not defined in the demo. It must determine the tenant from trusted principal/claims and verify permissions. Never let clients pass an arbitrary `X-Tenant-ID` while skipping membership checks. If permissions change and cached DTOs hold role-dependent data, adjust cache keys accordingly or evict/refresh immediately per policy.

## 8. Unit tests: CacheKeys contract without Docker

### 8.1. `CacheKeysTest.java`

```java
// src/test/java/com/example/cachelab/CacheKeysTest.java
package com.example.cachelab;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CacheKeysTest {

    @Test
    void differentTenantsNeverProduceSameKey() {
        String north = CacheKeys.profile("north", "42");
        String south = CacheKeys.profile("south", "42");

        assertThat(north).isNotEqualTo(south);
        assertThat(north).contains("north");
        assertThat(south).contains("south");
    }

    @Test
    void differentRecordsNeverProduceSameKey() {
        assertThat(CacheKeys.profile("north", "42"))
                .isNotEqualTo(
                        CacheKeys.profile("north", "43"));
    }

    @Test
    void rejectsMissingOrInvalidIdentifiers() {
        assertThatThrownBy(
                () -> CacheKeys.profile("", "42"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid tenantId");

        assertThatThrownBy(
                () -> CacheKeys.profile("north", "bad:42"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid profileId");
    }
}
```

**Three methods** test only key composition and validation. They do not prove `RedisCacheManager` uses this builder properly, do not prove TTL, and do not check authorization. Those contracts have separate integration tests.

### 8.2. Command to run unit tests

```bash
mvn -B -ntp -Dtest=CacheKeysTest test
```

Requires neither Docker nor a Redis server. This is source code for learners to run, not a claim of executed test results in this document.

## 9. Integration tests: real Redis, cache hit/miss, TTL, and tenant isolation

### 9.1. Redis container and Spring Boot 3.5 `@ServiceConnection`

Redis does not require a dedicated Testcontainers module for this example; use `GenericContainer`:

```java
@Container
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
        new GenericContainer<>("redis:7.4-alpine")
                .withExposedPorts(6379);
```

Why specify `name="redis"`?

- Spring Boot has a Redis service connection factory matching the `redis` name.
- `GenericContainer` is not a Redis-specific container subclass; `name="redis"` makes the intent explicit and also works with `@Bean` generic containers.
- `@ServiceConnection` supplies `RedisConnectionDetails` from the container, wiring the auto-configured Redis client to the mapped host and port.
- Tests never hardcode `localhost:6379`. On CI, the Docker daemon or network may use a different topology.
- `@Container` starts and stops with the JUnit class lifecycle without reusing a production Redis server.

### 9.2. `ProfileCacheIntegrationTest.java`

```java
// src/test/java/com/example/cachelab/ProfileCacheIntegrationTest.java
package com.example.cachelab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(properties = {
        "spring.cache.type=redis",
        "spring.cache.redis.time-to-live=4s",
        "spring.cache.redis.cache-null-values=false",
        "spring.cache.redis.use-key-prefix=true"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ProfileCacheIntegrationTest {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7.4-alpine")
                    .withExposedPorts(6379);

    @Autowired
    ProfileService service;

    @Autowired
    ProfileRepository repository;

    @Autowired
    CacheManager cacheManager;

    @Autowired
    StringRedisTemplate redisStrings;

    @BeforeEach
    void resetIsolatedTestData() {
        // Safe only because this Redis container is owned by the test.
        cacheManager.getCache("profiles").clear();
        repository.reset();
    }

    @Test
    void secondCallForSameTenantAndIdIsCacheHit() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");

        assertThat(repository.loadCount()).isEqualTo(1);
    }

    @Test
    void sameIdOfDifferentTenantsCannotShareValue() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");

        assertThat(repository.loadCount()).isEqualTo(2);

        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);
    }

    @Test
    void differentProfilesWithinTenantRemainSeparate() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("north", "43"))
                .isEqualTo("NORTH-43");

        assertThat(repository.loadCount()).isEqualTo(2);
    }

    @Test
    void updatingOneTenantEvictsOnlyItsEntry() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);

        service.update("north", "42", "NORTH-42-v2");

        // south is still a HIT: repository is not called again.
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);

        // north was evicted: reloads fresh data.
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42-v2");
        assertThat(repository.loadCount()).isEqualTo(3);
    }

    @Test
    void entryHasTtlAndIsLoadedAgainAfterExpiration() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(1);

        String redisKey = "profiles::"
                + CacheKeys.profile("north", "42");

        Long ttlMs = redisStrings.getExpire(
                redisKey, TimeUnit.MILLISECONDS);

        assertThat(ttlMs).isNotNull();
        assertThat(ttlMs).isPositive();
        assertThat(ttlMs).isLessThanOrEqualTo(4_000L);

        await()
                .atMost(Duration.ofSeconds(12))
                .pollInterval(Duration.ofMillis(100))
                .until(() -> Boolean.FALSE.equals(
                        redisStrings.hasKey(redisKey)));

        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);
    }
}
```

**Explanation of tests:**

- Each test resets the in-memory repository and clears the `profiles` cache in the **test-only Redis container**. Never do this on a Redis instance shared with other jobs or users.
- `secondCall...` proves Spring AOP actually intercepts: the second call does not invoke the repository.
- `sameIdOfDifferentTenants...` is the **anti-cross-tenant-leakage assertion**: same ID 42, different values.
- `differentProfiles...` protects the record ID dimension within the same tenant.
- `updatingOneTenant...` proves invalidating `north` neither deletes nor forces a reload for `south`.
- `entryHasTtl...` inspects the **physical Redis PTTL** and waits for the key to expire before reloading, rather than merely checking `spring.cache.redis.time-to-live` in a file.
- `@DirtiesContext(AFTER_CLASS)` prevents context caching from outliving the class-scoped Redis container lifecycle. With multiple test classes sharing a Spring context, consider a context-managed container bean.
- Tests do not enable parallel methods; under parallel execution, `@BeforeEach cache.clear()` can race with another method, so use per-test namespaces/caches or avoid clearing a shared scope.

### 9.3. Why not assert an exact 4000ms TTL?

Time elapses between the cache provider's Redis `SET` command and the moment the test calls `getExpire`. The result might be 3990ms, 3800ms, etc. The test checks `ttlMs > 0` and `ttlMs <= 4000`, then performs a bounded await until expiration. If the cache had no expiry, Redis would return `-1`; if the key were missing or lost, it would return `-2`, failing the assertion in both cases.

If CI is so slow that 4 seconds pass before measuring TTL, the test can become flaky; increase the test TTL to 8–15 seconds or isolate a TTL config for this test rather than adding infinite retries to hide the issue. The sample uses 4 seconds for quick observation; different CI environments require practical sizing.

### 9.4. Why test with real Redis?

Pure unit tests can prove `CacheKeys.profile` generates distinct keys, but they cannot prove:

- Spring `@Cacheable` actually runs through a proxy.
- `RedisCacheManager` was selected instead of `SimpleCacheManager`/`NoOpCacheManager`.
- The physical Redis key has the cache-name prefix and entry TTL.
- Eviction uses the same key as lookup.
- Serialization and connection details work properly.
- Cache hits skip data source calls and expiration reloads data.

When any of these fail, Redis Testcontainers integration exposes the real defect.

## 10. Running Maven and CI

### 10.1. Commands

```bash
java -version
mvn -version

# Pure unit tests:
mvn -B -ntp -Dtest=CacheKeysTest test

# Redis integration:
docker version
docker info
mvn -B -ntp -Dtest=ProfileCacheIntegrationTest test

# All 8 test methods:
mvn -B -ntp test
```

Summary from source code:

| Test class | JUnit `@Test` count | Requires Docker? |
| --- | ---: | --- |
| `CacheKeysTest` | 3 | No |
| `ProfileCacheIntegrationTest` | 5 | Yes |
| **Total** | **8** | Full suite requires Docker |

These are commands for learners to run, **not a report that the source has been compiled or executed successfully** in the authoring environment. On the first run, Docker may pull the Redis image and Maven may download dependencies.

### 10.2. Sample GitHub Actions workflow

```yaml
name: Tenant Cache Integration

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker daemon
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run all tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cache-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

- `contents: read` scopes the GitHub API token; it does **not** grant Docker socket permissions.
- The runner needs a Docker-compatible daemon, permission to start a Redis container, image registry reachability, and sufficient CPU/RAM/disk.
- `@ServiceConnection(name="redis")` binds dynamic host/port, avoiding hardcoded `localhost:6379`.
- Do not run `docker system prune --volumes` on shared runners. Do not disable Testcontainers Ryuk just to get a green pipeline.
- If Docker is unavailable, a mandatory integration job must report **ENVIRONMENT FAIL**, not silently skip or use `mvn test || true`.
- For supply-chain-sensitive repositories, pin Actions to reviewed commit SHAs rather than movable version tags alone.

### 10.3. Why must test containers be cleaned up properly?

A static `@Container` is started and stopped per class by the JUnit Testcontainers extension. Spring TestContext may cache the `RedisConnectionFactory` bean beyond a single class; if another test class reuses a cached context pointing to a stopped container, connection refused errors occur.

This demo uses a single integration class and `@DirtiesContext(AFTER_CLASS)`. In larger suites, choose a container bean scoped to the Spring context or a shared static container pattern with matching lifecycle, without reusing containers from previous CI runs when isolation is required.

## 11. Common pitfalls and self-diagnosis

### 11.1. Using only `recordId` as the key in a multi-tenant service

**Wrong:**

```java
@Cacheable(cacheNames = "profiles", key = "#profileId")
public String get(String tenantId, String profileId) { ... }
```

**Consequence:** `north/42` and `south/42` share the physical key `profiles::42`. Spring Cache can return north's value to tenant south without calling the repository, even if the underlying SQL is correct.

**Fix:** The key must contain tenant scope + record ID (plus user/policy context if the response actually varies), as in `CacheKeys.profile`.

### 11.2. Letting users pass arbitrary tenant IDs

Even with a properly scoped key, a caller can request another tenant if the security layer does not check access. Do not treat the cache key as authentication. Resolve the tenant from a trusted principal or verify membership/authorization before cache interception.

### 11.3. Checking permissions inside the `@Cacheable` method body

A cache hit skips the method body. If authorization logic lives only there, hits can bypass the check. Design an authorization facade/security advice with proper ordering, and test both authorized and unauthorized users on the same record ID.

### 11.4. Caching auth-filtered views with a key missing user/role

Two users in the same tenant may have different views. If the cached value is a permission-filtered DTO, the key also needs user/role/policy version, or the design must filter after caching raw trusted data. Invalidate when permissions or consent change.

### 11.5. Forgetting `@EnableCaching`

`@Cacheable` is present on the method, but without AOP cache advice every call hits the repository. Key unit tests still pass; the integration `loadCount` assertion catches it.

### 11.6. Self-invocation `this.get(...)`

Calling a cached method internally within the same bean typically bypasses the Spring proxy. Route the call through another Spring-injected bean or refactor the adapter/service; do not rely on annotations taking effect via `this`.

### 11.7. Disabling the cache name prefix

Sharing a Redis database across multiple caches with key prefixing disabled can cause collisions. Keep `use-key-prefix=true` unless you have an equivalent namespacing strategy verified by tests.

### 11.8. Assuming `@Cacheable` has a built-in TTL

Spring's Cache abstraction defines no universal expiration; TTL must be configured on `RedisCacheManager`, Caffeine, or Ehcache. Redis `PTTL=-1` means the entry has no expiration; never claim TTL is active just because an annotation is present.

### 11.9. TTL expired, yet the service still returns stale data

The service might be reading another cache (Caffeine/local L1), the DB source might be stale, the key might be wrong, the test might be reading the wrong key, or the provider config might not be Redis. Inspect the `CacheManager` bean, physical Redis key, TTL, and data source calls.

### 11.10. TTL too short causing flaky CI tests

With a 100ms TTL on a loaded runner, a cache hit test might expire before the second read. Use a sufficiently long TTL for hit/isolation tests, and use bounded awaits aligned with real TTLs and generous timeouts for expiration tests. Avoid fixed `Thread.sleep` assuming millisecond precision.

### 11.11. Updates fail to evict the right key

`@Cacheable` uses `tenant+id` while `@CacheEvict` uses only `id` or the wrong cache name, leaving stale data until TTL expires. Share a single key builder, test updating one tenant, and assert the other tenant is not evicted.

### 11.12. `@CacheEvict(allEntries=true)` wipes all tenants

All-entries eviction affects the entire cache, not just the active tenant. In a shared Redis, it impacts every tenant in that cache. Use it only when business logic requires a global reset and the cost/consistency trade-offs are understood.

### 11.13. Caching null, empty, or error responses without policy

Negative caching can improve performance but may cause newly created records or newly granted permissions to keep returning absent; caching unauthorized responses can retain sensitive or stale information. Choose an explicit null/empty policy, avoid arbitrarily caching exceptions, and test right after data creation or permission changes.

### 11.14. Global Redis flush in `@BeforeEach`

`FLUSHDB`/`FLUSHALL` or `cache.clear()` on a shared Redis wipes other data and races with parallel jobs. The sample clears a single cache **on a test-owned container**. Real applications should isolate databases/containers/key namespaces and perform scoped cleanup.

### 11.15. Redis keys containing PII or secrets

Cache keys can appear in CLI tools, logs, metrics, and backups. Never place access tokens, passwords, or raw email addresses into keys without strong justification and protection. Use stable opaque IDs or keyed hashes where appropriate for your security model.

### 11.16. Treating cache isolation as a substitute for database RLS

Cache scoping and database tenant filters/RLS are **two independent layers**. Test both SQL row-level authorization and cache key separation. Getting one right does not guarantee the other is safe.

### 11.17. Testing only a single tenant

If tests do not use the same record ID across two different tenants, missing tenant dimensions in keys easily slip through. Design fixtures intentionally with **same ID, different values**, and test both `north→south` and `south→north` orders in broader suites.

### 11.18. Context caching and container lifecycle

If a Spring context remains cached after a static Testcontainers Redis field stops, the cache manager/connection factory can point at an old host port. Use `@DirtiesContext` deliberately or context-managed Testcontainers beans instead of endless retries.

### 11.19. Cache stampede upon expiration

Multiple concurrent misses can hit the DB at once. `@Cacheable(sync=true)` does not automatically guarantee distributed locking across all nodes/providers. Under strict SLAs and high load, test concurrency and locking against the real provider and measure DB load.

## 12. Testing special security and lifecycle cases

### 12.1. Token/tenant switching within the same session

A user may have access to switch tenants in the UI. If the cache key uses `userId` without `tenantId`, switching tenants can return data from the previous tenant. Tests must send requests within the same authenticated session switching `tenant A → B` with the same record ID and prove the cache is not shared.

### 12.2. Role downgrade or membership revocation

Suppose an admin once viewed a full profile and then had their role revoked. If the cache still serves the old authorized view, a multi-minute TTL can violate security policy. Mitigations depend on design: authorize before caching, key cache entries by permission version, invalidate on revocation, or avoid caching sensitive views.

### 12.3. Tenant deletion/migration

When a tenant is locked, deleted, or migrated to another shard, old cache entries must not "live on" as phantom data. Purge **scoped to the tenant** or use namespaces/versions so old keys are no longer looked up. Never run a global Redis `FLUSHALL`.

### 12.4. Cache schema/version rollover

New deployments can change object serialization or key semantics. Without versioned keys or rollout invalidation, deserialization can fail or return old-format data. A `v1` schema prefix enables planned migrations; test compatibility, backfill, and eviction behavior in practice.

### 12.5. Shared cache across multiple applications

A Redis cluster may serve multiple apps or environments. The cache name prefix is only one layer. Add an environment/app namespace via cache prefix configuration if needed; ensure test and prod never share credentials or Redis DBs where they could accidentally read each other's keys.

### 12.6. TTL and event ordering

Back-to-back updates can race: an older request loads from the DB, a newer one updates the DB and evicts, and then the older request finishes and writes a stale value into Redis. TTL bounds staleness duration but does not eliminate races. For critical data, consider versioned keys, compare-and-set, eviction sequencing, DB version checks, or bypassing caching based on risk; test real concurrency when required.

### 12.7. Did Boot auto-configure the right cache provider?

Spring Boot picks a cache provider based on dependencies and configuration. When a project has multiple providers, assert the actual `CacheManager` chosen rather than guessing from dependency names. `spring.cache.type=redis` in the example makes intent explicit, and integration tests inspect physical Redis keys.

### 12.8. Spring test slices are not full caching integration

`@DataRedisTest` loads a Redis slice and may not enable `@EnableCaching`/service AOP the same way the full app does. It is great for testing repositories and Redis ops; to verify `@Cacheable` on services with the real cache manager and config, `@SpringBootTest` as shown is more transparent. When using slices, explicitly `@Import` needed beans and verify proxy/cache wiring.

## 13. Pre-merge checklist for multi-tenant cached code

- [ ] Every tenant/user-scoped cached value has a matching key scope.
- [ ] Tenant ID comes from a trusted authenticated context, not just a client header.
- [ ] Authorization executes **before a cache hit**, not solely inside the cached method body.
- [ ] Cache keys never mix tenant A and tenant B for the same record ID.
- [ ] User/role/policy/locale/filter dimensions are included whenever the value depends on them.
- [ ] Cache name prefixes and app/env namespaces are properly configured on shared Redis.
- [ ] `@Cacheable`, `@CacheEvict`, and `@CachePut` share a consistent key contract.
- [ ] `@EnableCaching` and the right `CacheManager` provider are enabled/selected.
- [ ] Spring proxy/self-invocation behavior is understood and tested.
- [ ] Redis TTL is configured on the provider and verified with `PTTL > 0`.
- [ ] Expiration tests use bounded awaits instead of fixed sleeps.
- [ ] Data updates, deletes, and permission revocations have an SLA-compliant invalidation policy.
- [ ] Null/negative caching is an explicit decision and never retains permission-denied responses.
- [ ] Cache values/keys do not expose unnecessary secrets or PII.
- [ ] Redis ACL/TLS and environment isolation are configured in production.
- [ ] Tenant-scoped database access is also tested independently.
- [ ] Integration tests include same-ID-different-tenants fixtures.
- [ ] Tests do not run `FLUSHDB`/`FLUSHALL` against shared Redis.
- [ ] CI has a Docker daemon/port mapping and does not silently skip mandatory Redis tests.
- [ ] Context caching and Redis Testcontainers lifecycles do not leave stale connections.
- [ ] Load/concurrency tests are added where stampede or cross-node consistency poses a risk.
- [ ] QA reports unit, integration, environment failure, and skipped counts accurately.

## 14. Practice exercises

**Exercise 1 — Controlled defect.** On a separate demo branch, change `ProfileService.get` to `key="#p1"`. Run the cross-tenant test to observe the failure. Restore the tenant-scoped key builder and confirm tests pass. Never ship the broken variant to production.

**Exercise 2 — Add user scope.** Give two users in the same tenant different authorized views. Design a key including user or policy version if caching permission-filtered DTOs. Write a test proving role A cannot hit role B's view.

**Exercise 3 — Change TTL.** Try `spring.cache.redis.time-to-live=8s` in a test. Read `getExpire` after a write, await bounded expiration, and verify the repository loads again. Explain why asserting an exact 8000ms TTL is flaky.

**Exercise 4 — Tenant-accurate eviction.** Update `north/42`, verify `south/42` still hits the cache, and `north/42` reloads the new value. Intentionally try an eviction key without the tenant to observe stale data.

**Exercise 5 — Security boundary.** Design an API that resolves the tenant from an authenticated principal. Test a user belonging to `north` sending `X-Tenant-ID: south`; the API must reject or ignore the untrusted header and never read `south`'s cache.

**Exercise 6 — Data deletion & privilege revocation.** Revoke permissions for a user with a cached authorized view; determine whether business rules require immediate invalidation or accept maximum TTL, and write the corresponding test.

**Exercise 7 — Cache name collision.** Create `profiles` and `summaries` caches with the same logical key. Toggle key prefixing in an isolated test broker to demonstrate namespace collisions when misconfigured.

**Exercise 8 — CI isolation.** Run two integration jobs in parallel with dedicated Redis Testcontainers; ensure no global `FLUSHALL` occurs and containers clean up properly. Verify Docker host/port mapping if Maven runs inside a Docker executor.

**Exercise 9 — Transaction rollback.** Build a test-only transactional DB update and trigger a rollback; evaluate `@CacheEvict` ordering relative to transaction commit and design after-commit invalidation if needed.

**Exercise 10 — Multi-node miss storm.** Simulate multiple concurrent requests upon expiration and measure repository load counts; evaluate `sync=true`, provider locking, and stampede mitigation strategies against your constraints.

## 15. Self-check questions

**1.** Why can `key="#profileId"` be dangerous in a multi-tenant service?  
**Answer:** Multiple tenants with the same record ID share one cache entry, causing cross-tenant data leakage on cache hits.

**2.** Does including the tenant in the cache key replace authorization?  
**Answer:** No; the tenant must be authenticated and authorized before cache lookup.

**3.** What is the risk of checking permissions only inside a `@Cacheable` method body?  
**Answer:** Cache hits skip the method body, so the check does not run.

**4.** Does the default `SimpleKeyGenerator` include method arguments?  
**Answer:** Yes; however, if the tenant is not an argument or an explicit key omits it, collisions still occur.

**5.** Does the `profiles::` cache name prefix automatically add the tenant?  
**Answer:** No. It only separates cache names; the tenant must still be in the logical key.

**6.** Does `@Cacheable` provide a built-in `ttl` attribute across all providers?  
**Answer:** No. TTL is configured on Redis, Caffeine, Ehcache, or the appropriate cache manager.

**7.** What does Redis `PTTL=-1` mean?  
**Answer:** The key exists with no expiration; `-2` means the key does not exist.

**8.** Is TTL extended on every cache GET?  
**Answer:** Not under standard TTL; time-to-idle requires different semantics and configuration.

**9.** Why shouldn't updating `north/42` clear the entire `profiles` cache?  
**Answer:** Because it evicts other tenants too; it is better to evict only the scoped key for `north/42`.

**10.** Why doesn't a pure unit test of a key builder prove Redis integration is safe?  
**Answer:** It does not exercise the Spring proxy, cache manager, or physical Redis prefixes, TTL, and eviction.

**11.** Why is `StringRedisTemplate.getExpire` better than merely reading the TTL property?  
**Answer:** It observes the actual expiration written on the provider, catching configurations that failed to apply.

**12.** Does Redis Testcontainers automatically prevent client-supplied tenant spoofing?  
**Answer:** No. Broker tests verify caching behavior; the security boundary must be verified separately.

## 16. Official references

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `CacheManager`, proxy semantics, caching advice.
- [Spring Framework — Declarative Annotation-Based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, key SpEL, `@CacheEvict`, default key generation.
- [Spring Boot 3.5 — Caching](https://docs.spring.io/spring-boot/3.5/reference/io/caching.html): Redis cache auto-configuration, `spring.cache.redis.time-to-live`, and key prefixes.
- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection(name="redis")` on `GenericContainer`.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data-redis/reference/redis/redis-cache.html): `RedisCacheManager`, TTL, serialization, key prefixes, invalidation behavior.
- [Spring Data Redis — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html): `entryTtl`, null value policy, prefixes.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers` and `@Container` lifecycle.
- [Redis — EXPIRE and TTL](https://redis.io/docs/latest/commands/ttl/): Redis expiration return codes.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): millisecond expiration.
- [Redis — GETEX](https://redis.io/docs/latest/commands/getex/): key read with expiration update, related to TTI.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): authorization boundaries, advice, and policy checking.

**Conclusion:** Multi-tenant caching is part of correctness **and** security, not just performance. Keys must include every dimension that determines the returned value, especially tenant, user, and record; tenant identity must be verified before cache lookup. TTL must be configured and **measured on the cache provider**, not just documented. Eviction must follow the exact same key contract as lookup. Combine pure key-builder unit tests with Spring AOP + Redis Testcontainers integration tests to protect cache hits, cross-tenant isolation, expiration, and invalidation, and use dedicated authorization tests for the security boundary.