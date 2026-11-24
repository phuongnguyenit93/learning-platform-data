# @DataRedisTest with caches, TTLs, and data structures used in Spring Boot

## 1. The problem: a "green Redis test" must actually test Redis

Spring Boot commonly uses Redis for caching, sessions, expiring tokens, rate limiting, rankings, shopping carts, or temporary result sets. A Redis bug is not always a bug in Java code: the same key may be written with the **wrong data type**, TTL may be forgotten, serializer configuration may be incompatible, caching may be disabled in tests, or leftover data from a previous test may linger.

`@DataRedisTest` is Spring Boot's **test slice** for **Spring Data Redis** components. It focuses on configuring connections, Redis templates, and scanned Redis repositories/entities rather than loading every controller, HTTP server, and business service. However, three limitations must be understood right away:

1. **`@DataRedisTest` does not start a Redis server on its own.** It configures client components conditionally; to run real Redis commands, you need a test Redis instance, such as from **Testcontainers** or a dedicated CI server.
2. **`@DataRedisTest` does not automatically enable real `@Cacheable` caching.** In Spring Boot 3.5, the test slice includes `@AutoConfigureCache`, which defaults to `NoOpCacheManager`. To verify real Redis caching, you must enable `@EnableCaching` and configure/verify a real `RedisCacheManager` in an appropriate test.
3. **Redis does not have automatic test rollback like `@DataJpaTest`.** A key written with `SET` or a member added with `SADD` to an out-of-process Redis server remains until deleted or its TTL expires, unless you actively clean it up. Spring TestContext's `@Transactional` should not be treated as a mechanism that automatically rolls back all Redis commands.

This lesson builds a Java 17+ / Spring Boot 3.5 example with **real Redis via Testcontainers**: verifying `StringRedisTemplate`, TTLs, Redis Hash/List/Set/Sorted Set, `WRONGTYPE` handling, and a separate test proving `@Cacheable` actually uses Redis with a TTL. It also clarifies how `@RedisHash` Spring Data Redis repositories differ from caching and how to upgrade to Boot 4.

## 2. Which components are included in @DataRedisTest?

On **Spring Boot 3.5.x**, import:

```java
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
```

A simple test:

```java
@DataRedisTest
class RedisRepositoryTest {
    // @Autowired RedisRepository or StringRedisTemplate;
}
```

`@DataRedisTest` uses Spring TestContext and slice-specific type filters, typically including:
- `RedisAutoConfiguration`: `RedisConnectionFactory`, `RedisTemplate`, and `StringRedisTemplate` when classpath/configuration permits.
- `RedisReactiveAutoConfiguration`: reactive components when dependencies/reactive connections are present.
- `RedisRepositoriesAutoConfiguration`: Spring Data Redis repositories and `@RedisHash` entities discovered.
- Selected SSL, cache auto-config, or Testcontainers service connection parts depending on conditions/version.

Default component-scan filters primarily pay attention to **Redis repositories and `@RedisHash` entities**; regular `@Service`, `@Component`, or `@ConfigurationProperties` beans **are not scanned as in a full application context**. A manual Redis adapter/DAO annotated with `@Repository` that is not a Spring Data repository interface needs `@Import` if the test wants the real bean.

| Bean/component | In Redis slice? | Test implication |
|---|---|---|
| `RedisConnectionFactory` | Usually auto-configured when driver is present | Connects to the specified Redis server |
| `RedisTemplate<Object,Object>` | May be created by Boot | Verifies serialization and template-appropriate Redis operations |
| `StringRedisTemplate` | Usually present when Redis auto-config is active | String-based key/value using string serializer |
| `ReactiveRedisTemplate` / `ReactiveStringRedisTemplate` | Conditional on reactive dependencies | Reactive Redis commands; requires subscribing in tests |
| `CrudRepository` for `@RedisHash` entity | Scanned by Redis repository auto-config | Aggregate mapping, ID, repository TTL/indexes |
| Hand-written `@Repository` DAO | **Not auto-scanned by default** | `@Import(Dao.class)` to keep the real implementation |
| Business `@Service` | Not auto-loaded | Import/fake specifically or write an integration test |
| Real `CacheManager` for `@Cacheable` | **Must not be assumed by default** | Explicitly declare `RedisCacheManager` and `@EnableCaching` |
| Redis server | **Not spawned by @DataRedisTest** | Testcontainers or separate test server |
| SQL `DataSource` / JPA `EntityManager` | Out of scope | Separate SQL/JPA tests |
| HTTP controller / embedded server | Out of scope | Separate MVC/WebFlux/HTTP integration tests |

An application class with custom `@ComponentScan` or a test with many `@Import`s can expand scope unexpectedly. If `ApplicationContext` fails due to a missing service bean, do not rush to switch to `@SpringBootTest`: check whether that service actually belongs to the goal of verifying the Redis slice.

**Distinguish "having a bean" from "Redis commands succeeding":** injecting `StringRedisTemplate` only proves Spring created the client; you must call `set`, `get`, `expire`, `type`, `opsForHash`, etc., to catch wrong host/port/auth/TLS or the wrong data structure.

## 3. What data types does Redis store and what should you test?

Redis is not just a `String -> String` map. Each key has a **Redis data type** and only a specific family of commands applies to that type.

| Redis type | Common commands | Spring Data API | Critical checks |
|---|---|---|---|
| String | `SET`, `GET`, `INCR`, `SET ... EX` | `opsForValue()` | Value/serialization, TTL, atomic counter |
| Hash | `HSET`, `HGET`, `HGETALL` | `opsForHash()` | Fields and values, partial update, key-level TTL |
| List | `LPUSH`, `RPUSH`, `LRANGE` | `opsForList()` | Order and duplicates, push/pop side |
| Set | `SADD`, `SMEMBERS` | `opsForSet()` | Uniqueness, **no ordering guarantee** |
| Sorted Set / ZSet | `ZADD`, `ZRANGE`, `ZREVRANGE` | `opsForZSet()` | Score, ranking, ordering/tie-breaking |
| Stream | `XADD`, `XREADGROUP` | `opsForStream()` | Event ID, consumer group, ack/retry; needs dedicated tests |
| HyperLogLog | `PFADD`, `PFCOUNT` | `opsForHyperLogLog()` | Approximate cardinality, **not exact** |
| Geo | `GEOADD`, `GEORADIUS` and variants | `opsForGeo()` | Coordinates, radius/unit, ordering/distance |

`StringRedisTemplate` uses `StringRedisSerializer` for keys/values, making keys easy to inspect with Redis CLI. A general `RedisTemplate` may use different serializers, and `RedisCacheManager` caches have their own key/value serializers. **Two keys that look visually identical may store different bytes** if serializers differ.

### 3.1. Wrong Redis type usually causes WRONGTYPE

For example, a key has been `SET` as a Redis String; if you later run `HSET` on the same key, Redis returns a **WRONGTYPE** error. When Spring Data Redis translates the error, you get an appropriate `DataAccessException` rather than an empty Hash.

```text
SET demo:stock "5"         -> key has type STRING
HSET demo:stock name "A"   -> WRONGTYPE
TYPE demo:stock            -> string
```

The fix is to establish namespace conventions (`stock:...`, `cart:...`, `ranking:...`) and ensure code uses the **right operation family**. Never fix it by deleting a live production key that holds data just to force another type.

### 3.2. Do not confuse a Hash with a JSON string

A key holding JSON `"{\"name\":\"A\"}"` written via `SET` is still a **Redis String**, not a Redis Hash. To use `HGET key name`, it must be written with Hash operations or redesigned accordingly. A JSON serializer round-trip does not prove Hash field mapping.

### 3.3. Set and Sorted Set differ from List

- **List** preserves order and allows duplicates; fits short event lists when length-bounded.
- **Set** enforces uniqueness but iteration order is unstable; do not compare directly with `List.of("a","b")`.
- **Sorted Set** pairs unique members with scores, used for leaderboards. Tests must confirm scores and sort direction; when scores are equal, Redis applies tie-breaking rules for members, so tests should reflect the contract or avoid unnecessary ties.

## 4. What is TTL and which cases make tests fail?

TTL (time to live) defines the **remaining lifetime of a Redis key**. With a `SET` command specifying expiration, Redis removes the key when it expires (expired-key cleanup has lazy and active behavior). Spring Data Redis provides:

```java
redis.opsForValue().set(
        "tokens:abc",
        "value",
        Duration.ofSeconds(60));

Long ttl = redis.getExpire(
        "tokens:abc",
        TimeUnit.SECONDS);
```

This is an **illustrative snippet** in a class with `StringRedisTemplate redis`; requires imports `Duration` and `TimeUnit`. The `ttl` result measures **remaining time at the moment of reading**, not always literally 60.

Redis TTL return values are generally interpreted as:

| TTL value | Meaning |
|---|---|
| Positive number | Key exists and has an expiration, with that many seconds/ms remaining |
| `-1` | Key exists **but has no expiration** |
| `-2` | Key **does not exist** |
| `0` | May have less than one requested TTL unit remaining, e.g., 0 seconds due to rounding; do not infer persistent |
| `null` from API | May happen due to operation/driver/pipeline context; check API contract and configuration |

To assert TTL, typically use a **range** (such as `0 < ttl <= 60`) rather than `ttl == 60`. When TTL is very short, use milliseconds or bounded polling instead of `Thread.sleep(2000)` hoping CI is fast enough.

### 4.1. TTL applies to the key, not each field by default

In common Redis Hash usage, `expire(hashKey, duration)` sets TTL on the **entire Hash key**. An `HSET` field does not carry its own separate TTL just because a Hash has multiple fields. Newer Redis versions introduced commands for individual hash field expiration, but you **must not assume** every Redis server/Spring Data Redis version exposes that API or that `opsForHash().put` sets per-field TTL.

### 4.2. Does reading a key extend its TTL?

With regular TTL, **`GET` does not automatically extend lifetime**. If the business rule is "15 minutes since last access", that is closer to **TTI (time to idle)** and requires an explicit mechanism, such as a cache implementation supporting read-and-reset expiration via `GETEX` on Redis 6.2+. TTI does not happen automatically just because TTL was configured.

A test that only checks the key exists immediately after writing **cannot** prove expiration. Tests should verify the TTL was set properly **and** an expired scenario when that is a requirement.

### 4.3. expire, persist, overwrite, and update

A key with an expiration can be:
- Overwritten by value-replacing operations that **drop TTL** depending on the command; a plain `SET key value` removes any old TTL unless an option to preserve TTL is used.
- Extended via `EXPIRE` or overwritten with a new TTL.
- Made persistent with `PERSIST` if allowed.
- Removed before TTL due to explicit `DEL`, eviction policy, or server reset; TTL is not a guarantee to keep data until the exact final second.

**Test behavior after update**, not just after the initial write, if the business logic relies on updates extending or preserving expiration.

## 5. Sample project: Java 17+, Spring Boot 3.5, and real Redis

The example below tests Redis with **Testcontainers**, so Docker or a compatible container runtime is required. Do not mock Redis with Mockito when the goal is real Redis data types and TTLs.

Structure:

```text
build.gradle
src/main/java/com/example/redisslice/
    RedisSliceApplication.java
    RedisStructuresStore.java
    CatalogueService.java
    CachedLookupService.java

src/test/java/com/example/redisslice/
    RedisStructuresStoreTest.java
    RedisCacheSliceTest.java
```

### 5.1. build.gradle (Gradle Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The configuration above uses a specific patch version **Boot 3.5.8** for reproducibility in a Maven/Gradle repository with matching dependencies. In real projects, align libraries via the Spring Boot BOM and update to a patch version verified by your team. This example needs a **Redis 7.4 container** pullable from the registry when running tests and an active container runtime.

`spring-boot-starter-data-redis` brings Spring Data Redis and the Lettuce driver onto the classpath. `spring-boot-starter-cache` supports cache abstraction/AOP when enabled. `spring-boot-starter-test` brings JUnit Jupiter/Mockito/Spring Test. `awaitility` helps test expiration with bounded polling timeouts. Testcontainers runs **real Redis**, not a fake server.

You do not need to manually install `redis-server` on host port 6379; Docker maps the container port to a dynamic host port, and `@DynamicPropertySource` passes that info to Spring Data Redis.

### 5.2. Application class

File `src/main/java/com/example/redisslice/RedisSliceApplication.java`:

```java
package com.example.redisslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisSliceApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisSliceApplication.class, args);
    }
}
```

The application class sits in the parent package of the Redis DAO and services, yet `@DataRedisTest` **does not trigger full component scanning** the way `@SpringBootTest` does. In the example, components outside Redis repository scanning are explicitly imported in tests.

### 5.3. Adapter working with multiple Redis data structures

File `src/main/java/com/example/redisslice/RedisStructuresStore.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RedisStructuresStore {

    private final StringRedisTemplate redis;

    public RedisStructuresStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStock(String key, int quantity, Duration ttl) {
        redis.opsForValue().set(
                key, Integer.toString(quantity), ttl);
    }

    public Optional<Integer> readStock(String key) {
        return Optional.ofNullable(
                redis.opsForValue().get(key))
                .map(Integer::parseInt);
    }

    public void putMetadata(
            String key, Map<String, String> fields) {
        redis.opsForHash().putAll(key, fields);
    }

    public String readMetadata(String key, String field) {
        Object value = redis.opsForHash().get(key, field);
        return value == null ? null : value.toString();
    }

    public void appendEvent(String key, String event) {
        redis.opsForList().rightPush(key, event);
    }

    public List<String> events(String key) {
        List<String> values =
                redis.opsForList().range(key, 0, -1);
        return values == null ? List.of() : values;
    }

    public void addTag(String key, String tag) {
        redis.opsForSet().add(key, tag);
    }

    public Set<String> tags(String key) {
        Set<String> values = redis.opsForSet().members(key);
        return values == null ? Set.of() : values;
    }

    public void addRanking(
            String key, String member, double score) {
        redis.opsForZSet().add(key, member, score);
    }

    public List<String> rankedDescending(String key) {
        Set<String> values =
                redis.opsForZSet().reverseRange(key, 0, -1);
        return values == null
                ? List.of()
                : new ArrayList<>(values);
    }
}
```

This is a **real adapter**, calling the Redis server via `StringRedisTemplate`. Points to observe:

- `putStock` creates a Redis **String** with TTL, not a Hash.
- `putMetadata` creates a Redis **Hash** of field/value pairs, not a JSON string.
- `appendEvent` uses `RPUSH` so **write order** is preserved in the List; duplicates are allowed.
- `addTag` uses a Redis **Set**, so duplicate members are not added twice.
- `addRanking` uses a **Sorted Set** with scores; `reverseRange` fetches highest-to-lowest score order.
- `StringRedisTemplate` is convenient when data is purely String; complex objects need a configured `RedisTemplate<K,V>` with an explicit serializer.
- There is no `@Transactional` or SQL database in the adapter; each operation sends its corresponding Redis command.

**Separate commands do not automatically form a multi-step transaction.** For example, `HSET` followed by `EXPIRE` are two separate commands; if atomicity is required, consider Redis `MULTI/EXEC`, a Lua script, or a single combined command, and test behavior separately under concurrent access or network failure.

### 5.4. Business service proving slice boundaries

File `src/main/java/com/example/redisslice/CatalogueService.java`:

```java
package com.example.redisslice;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class CatalogueService {

    private final RedisStructuresStore store;

    public CatalogueService(RedisStructuresStore store) {
        this.store = store;
    }

    public Optional<Integer> stock(String key) {
        return store.readStock(key);
    }
}
```

`@DataRedisTest` does not normally scan `CatalogueService`. We explicitly verify this in tests. If you need to test real service logic, you can `@Import` the service along with its dependencies or write an appropriate integration test, but do not accidentally pull controllers or schedulers into the Redis slice.

## 6. Real test suite for String, Hash, List, Set, ZSet, and TTL

File `src/test/java/com/example/redisslice/RedisStructuresStoreTest.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
@Import(RedisStructuresStore.class)
class RedisStructuresStoreTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    RedisStructuresStore store;

    @Autowired
    ApplicationContext context;

    private final Set<String> keysToDelete = new HashSet<>();

    private String key(String suffix) {
        String key = "learn:redis:" + UUID.randomUUID()
                + ":" + suffix;
        keysToDelete.add(key);
        return key;
    }

    @AfterEach
    void cleanOnlyThisTestsKeys() {
        if (!keysToDelete.isEmpty()) {
            redis.delete(keysToDelete);
        }
    }

    @Test
    void sliceProvidesTemplateAndImportedStoreButNotService() {
        assertNotNull(redis);
        assertNotNull(store);
        assertTrue(context.getBeansOfType(
                CatalogueService.class).isEmpty());
    }

    @Test
    void writesAndReadsStringWithExplicitType() {
        String key = key("stock");

        store.putStock(key, 17, Duration.ofSeconds(90));

        assertEquals(17, store.readStock(key).orElseThrow());
        assertEquals(DataType.STRING, redis.type(key));
    }

    @Test
    void distinguishesExpiringAndPersistentKeys() {
        String temporary = key("temporary");
        String permanent = key("permanent");

        store.putStock(
                temporary, 5, Duration.ofSeconds(60));
        redis.opsForValue().set(permanent, "keep");

        Long ttl = redis.getExpire(
                temporary, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60);

        assertEquals(
                -1L,
                redis.getExpire(
                        permanent, TimeUnit.SECONDS));
    }

    @Test
    void observesExpirationWithBoundedPolling() {
        String key = key("short-lived");
        redis.opsForValue().set(
                key, "temporary", Duration.ofMillis(300));

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(
                        () -> assertFalse(
                                Boolean.TRUE.equals(
                                        redis.hasKey(key))));
    }

    @Test
    void hashHasSeveralFieldsUnderOneRedisKey() {
        String key = key("profile");
        store.putMetadata(
                key,
                Map.of("owner", "linh", "tier", "gold"));

        assertEquals(DataType.HASH, redis.type(key));
        assertEquals("linh",
                store.readMetadata(key, "owner"));
        assertEquals("gold",
                store.readMetadata(key, "tier"));

        assertTrue(
                Boolean.TRUE.equals(
                        redis.expire(
                                key, Duration.ofSeconds(60))));

        Long ttl = redis.getExpire(
                key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60);
    }

    @Test
    void listPreservesAppendOrderAndDuplicates() {
        String key = key("events");

        store.appendEvent(key, "opened");
        store.appendEvent(key, "edited");
        store.appendEvent(key, "opened");

        assertEquals(DataType.LIST, redis.type(key));
        assertEquals(
                List.of("opened", "edited", "opened"),
                store.events(key));
    }

    @Test
    void setRemovesDuplicatesWithoutOrderingGuarantee() {
        String key = key("tags");

        store.addTag(key, "java");
        store.addTag(key, "redis");
        store.addTag(key, "java");

        assertEquals(DataType.SET, redis.type(key));
        assertEquals(
                Set.of("java", "redis"),
                store.tags(key));
    }

    @Test
    void sortedSetOrdersByScoreDescending() {
        String key = key("leaderboard");

        store.addRanking(key, "alice", 10.0);
        store.addRanking(key, "bob", 25.0);
        store.addRanking(key, "cara", 5.0);

        assertEquals(DataType.ZSET, redis.type(key));
        assertEquals(
                List.of("bob", "alice", "cara"),
                store.rankedDescending(key));

        assertEquals(
                25.0,
                redis.opsForZSet().score(key, "bob"));
    }

    @Test
    void wrongTypeFailsInsteadOfReturningAnEmptyHash() {
        String key = key("wrong-type");
        redis.opsForValue().set(key, "plain-text");

        assertThrows(
                DataAccessException.class,
                () -> redis.opsForHash().put(
                        key, "owner", "someone"));
    }

    @Test
    void deletingOneOwnedKeyDoesNotTouchAnotherKey() {
        String first = key("first");
        String second = key("second");
        redis.opsForValue().set(first, "one");
        redis.opsForValue().set(second, "two");

        assertTrue(
                Boolean.TRUE.equals(redis.delete(first)));

        assertFalse(
                Boolean.TRUE.equals(redis.hasKey(first)));
        assertEquals("two",
                redis.opsForValue().get(second));
    }
}
```

### 6.1. Why must the example use @Import?

`RedisStructuresStore` is a **hand-written** `@Repository` bean, not an interface covered by Spring Data Redis repository scanning. In the Redis slice, it may not appear automatically. `@Import(RedisStructuresStore.class)` brings the exact implementation under test into the context without opening full component scanning.

`sliceProvidesTemplateAndImportedStoreButNotService` proves that `StringRedisTemplate` and the adapter are present while `CatalogueService` is absent. If another test deliberately uses `@Import(CatalogueService.class)`, expectations for that service change accordingly; this behavior is intentional.

### 6.2. Why don't TTL tests use a fixed sleep?

TTL is **remaining** time, interacting with the scheduler, server clock, and CI load. `observesExpirationWithBoundedPolling` uses Awaitility to poll for the **condition** that the key no longer exists within up to 5 seconds at a 50 ms polling interval. It finishes early once the key disappears and fails on timeout, instead of always sleeping a fixed number of seconds.

TTL verification should split two assertions:
1. After writing, Redis reports the key **has a TTL** within a reasonable range.
2. After a short duration, the key is genuinely no longer observable.

Do not use `getExpire() == 60` as an exact expectation: a tiny amount of time elapses between write and read, and second-level TTL resolution can round down.

### 6.3. Why use per-test keys instead of FLUSHALL?

Each test generates its own prefix with `UUID`, records the keys it creates, and deletes them in `@AfterEach`. This approach:
- Prevents two tests from colliding on the same key.
- Avoids wiping another suite's keys in a shared Redis instance.
- Does not require administrative `FLUSHALL` or `FLUSHDB` commands.
- Avoids confusing `@DataRedisTest` with automatic rollback.

If a test creates secondary index keys, phantom copies, or cache prefix keys, cleanup must cover those keys as well; deleting only the main key may not be enough. For Redis repositories, prefer repository APIs and proper namespace/container isolation.

### 6.4. What each case proves

| Test case | What is actually verified | What is not yet proven |
|---|---|---|
| Slice context | Redis template, imported DAO, and exclusion of regular service | Full application context identical to production |
| String and stock | SET/GET, String serializer, `TYPE=string` | Corresponding data in a SQL database |
| TTL vs. persistent | `getExpire` distinguishes positive TTL and `-1` | TTI or all overwrite cases |
| Expiration polling | Redis key expires within a reasonable window | Expire event delivered to all subscribers |
| Hash | Fields/values, `TYPE=hash`, key-level TTL | Hash field-level TTL |
| List | Ordering and duplicates | Queue concurrency/consumer acknowledgement |
| Set | Uniqueness without depending on iteration order | Set returning items in a fixed order |
| Sorted Set | Scores and descending ranking | Tie-breaking/large leaderboard performance |
| WrongType | Redis returns an error for wrong-type command | That all Redis errors are WRONGTYPE |
| Per-key cleanup | Deletes owned key without touching another key | No extra keys left behind if another repository creates them |

**The tests call real Redis via Testcontainers.** However, a single local Redis 7.4 instance does not prove behavior of Redis Cluster, Sentinel, TLS, eviction under RAM pressure, or managed production Redis. Those risks need appropriately targeted configuration/deployment tests.

## 7. @Cacheable in @DataRedisTest: watch out for NoOpCacheManager

The data structure tests above verify Redis operations directly. They **do not automatically prove** Spring's cache abstraction works, because `@Cacheable` uses proxy interception and `CacheManager`, not just `StringRedisTemplate`.

In Spring Boot 3.5, `@DataRedisTest` uses `@AutoConfigureCache` with a **no-op** default so the test slice does not depend on business cache logic. Therefore:
- A `@Cacheable` bean may not be scanned.
- `@EnableCaching` may not be enabled in the context.
- If the cache manager is `NoOpCacheManager`, tests still run, yet nothing is **cached in Redis**.
- Only claim Redis caching works after checking both the `RedisCacheManager` bean **and** real key TTL / hit-miss behavior.

A clear approach: write a separate test importing the target service and configuring a real `RedisCacheManager`. The following example only caches **String values**, so it configures `StringRedisSerializer` instead of the cache manager's default JDK serialization. For DTOs, choose an appropriate serializer and test schema/compatibility separately.

### 7.1. Service with @Cacheable

File `src/main/java/com/example/redisslice/CachedLookupService.java`:

```java
package com.example.redisslice;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedLookupService {

    private final AtomicInteger calls = new AtomicInteger();

    @Cacheable(cacheNames = "lookups", key = "#p0")
    public String displayName(String sku) {
        return "Item-" + sku + "-" + calls.incrementAndGet();
    }

    public int callCount() {
        return calls.get();
    }
}
```

Use `key="#p0"` instead of `key="#sku"` so the example does not depend on whether the compiler retains parameter names. This is a **public method called from another bean (the test through a Spring proxy)**. If the service itself calls `this.displayName(...)`, internal self-invocation bypasses caching advice under the default proxy model.

### 7.2. Testing RedisCacheManager with real TTL and hit/miss

File `src/test/java/com/example/redisslice/RedisCacheSliceTest.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
@Import({
        CachedLookupService.class,
        RedisCacheSliceTest.TestCacheConfiguration.class
})
class RedisCacheSliceTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableCaching
    static class TestCacheConfiguration {

        @Bean
        RedisCacheManager cacheManager(
                RedisConnectionFactory factory) {

            RedisCacheConfiguration settings =
                    RedisCacheConfiguration.defaultCacheConfig()
                            .entryTtl(Duration.ofSeconds(90))
                            .disableCachingNullValues()
                            .serializeValuesWith(
                                    RedisSerializationContext
                                            .SerializationPair
                                            .fromSerializer(
                                                    new StringRedisSerializer()));

            return RedisCacheManager.builder(factory)
                    .cacheDefaults(settings)
                    .build();
        }
    }

    @Autowired
    CachedLookupService service;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    CacheManager cacheManager;

    private final Set<String> cacheKeys = new HashSet<>();

    private String sku() {
        String value = "sku-" + UUID.randomUUID();
        cacheKeys.add("lookups::" + value);
        return value;
    }

    @AfterEach
    void removeOnlyOwnedCacheEntries() {
        if (!cacheKeys.isEmpty()) {
            redis.delete(cacheKeys);
        }
    }

    @Test
    void repeatedLookupUsesRedisAndKeepsPositiveTtl() {
        assertInstanceOf(RedisCacheManager.class, cacheManager);
        String productSku = sku();
        int before = service.callCount();

        String first = service.displayName(productSku);
        String second = service.displayName(productSku);

        assertEquals(first, second);
        assertEquals(before + 1, service.callCount());

        String storedKey = "lookups::" + productSku;
        assertNotNull(redis.opsForValue().get(storedKey));

        Long remaining = redis.getExpire(
                storedKey, TimeUnit.SECONDS);
        assertNotNull(remaining);
        assertTrue(remaining > 0 && remaining <= 90);
    }

    @Test
    void differentKeysComputeDifferentEntries() {
        int before = service.callCount();
        String firstSku = sku();
        String secondSku = sku();

        String first = service.displayName(firstSku);
        String second = service.displayName(secondSku);

        assertTrue(!first.equals(second));
        assertEquals(before + 2, service.callCount());
    }
}
```

### 7.3. Why must cache configuration be explicit?

- `@TestConfiguration` scopes this config to tests, without forcing production to use this test setup.
- `@EnableCaching` turns on Spring's caching AOP infrastructure. This annotation does not guarantee a Redis `CacheManager` will appear on its own; we create the real `RedisCacheManager` bean.
- `@Import(CachedLookupService.class)` brings the **real service** into the slice to test interception. If the service were mocked with Mockito, `@Cacheable` on the implementation might not run as intended.
- `entryTtl(Duration.ofSeconds(90))` configures TTL when the **cache writes an entry**, not a promise that `GET` always resets TTL.
- `StringRedisSerializer` is used because the example caches `String`. If the service caches POJOs, the serializer must match the payload and contract.
- The default key prefix of `RedisCacheManager` is `cacheName::`; in the example it is `lookups::sku-...`. Do not hardcode this prefix in the app if the project configures custom `computePrefixWith` or `prefixCacheNameWith`.
- Two calls with the same key return the same String while `callCount` increments only once; the test also checks an actual Redis key with a real TTL to avoid **false positives from `NoOpCacheManager`**.
- `@Cacheable` is proxy-based cache-aside: an invocation from the test through the Spring bean differs from `this.displayName` self-invocation inside the service.

**Diagnostic note:** If a hit/miss test passes yet Redis has no key, check whether `ConcurrentMapCacheManager`, `NoOpCacheManager`, or another mock bean is in use. Asserting only `first.equals(second)` is insufficient, because a service can return the same value deterministically even when caching is inactive.

## 8. Cache TTL, TTI, and eviction must be tested at the right level

In `RedisCacheManager`, a cache entry is usually stored as a **Redis String key** with a prefix and TTL configured by `RedisCacheConfiguration`. This **differs** from a Spring Data Redis `@RedisHash` repository and a multi-field `opsForHash`.

### 8.1. TTL does not auto-renew on cache hit

With a 90-second TTL, calling `service.displayName(sku)` a second time before expiry is normally a **cache hit**; it does not rewrite the key or reset expiration. If the product requires **time-to-idle**, an explicit mechanism must be enabled (Spring Data Redis supports TTI options in newer versions via Redis `GETEX`, requiring Redis 6.2+) and **all read paths** must be consistent; a regular `GET` does not extend TTL.

### 8.2. Eviction has multiple meanings

- `@CacheEvict(cacheNames="lookups", key="#p0")` tells the cache manager to remove the corresponding entry when advice runs.
- `@CachePut` updates a cached value (unlike `@Cacheable`, which skips method invocation on hit).
- `TTL expiration` is Redis deleting a key after its lifetime ends.
- `Redis maxmemory eviction` is Redis dropping keys per eviction policy under memory pressure, which can happen **before TTL**.
- `RedisCacheManager`'s `cache.clear()` may scan keys by prefix; some default configurations use `KEYS`/`DEL`. For large keyspaces, evaluate performance impact and consider scan-based batch strategies.

Do not lump these behaviors into an expectation like "after 90 seconds a CacheEvict event will definitely fire". Expiration does not mean a Spring `@CacheEvict` method ran.

### 8.3. Null caching, value serializer, and prefix

`RedisCacheConfiguration` supports `disableCachingNullValues`, key prefixes, and serializers. By default, `RedisCache` may serialize values using Java native serialization, which carries security/compatibility risks if data sources are untrusted; in untrusted environments, design safe serializers such as JSON with type allowlists/schemas or String for simple payloads.

A test that reads back values using **the exact same serializer that wrote them** can pass even if other systems cannot decode those bytes. If multiple applications share Redis keys, establish a byte-level/key-name/prefix contract and test cross-version compatibility.

## 9. @RedisHash repositories, @TimeToLive, and secondary keys

`@DataRedisTest` is not just for templates. Spring Data Redis supports Redis repositories on entities annotated with `@RedisHash`.

Illustrative **model example**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 120)
public class SessionDocument {
    @Id
    private String id;
    private String owner;

    protected SessionDocument() {}

    public SessionDocument(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() { return id; }
    public String getOwner() { return owner; }
}
```

The snippet above is a standalone class **if saved at `SessionDocument.java`** in an appropriate package with Spring Data Redis dependencies, but to keep the main example free of extra repository keys, it is not included in the Section 5 source set. Its accompanying repository can be:

```java
interface SessionRepository
        extends CrudRepository<SessionDocument, String> {}
```

With `import org.springframework.data.repository.CrudRepository`, if the interface sits in the application's scanned package, Redis repository auto-configuration creates the implementation. Use `@RedisHash(timeToLive=120)` to configure TTL on the repository entity; `@TimeToLive` also enables dynamic per-property/method TTL where supported by Spring Data Redis.

**However, repository TTL is not the same as StringRedisTemplate TTL or Redis cache TTL:**
- Entities are typically stored under a Redis Hash key like `sessions:<id>`, potentially with metadata/index keys.
- Spring Data Redis repositories use a keyspace event listener and in some cases a **phantom copy/shadow copy** of the entity TTL to emit `RedisKeyExpiredEvent`.
- Expiration events rely on Redis Pub/Sub/keyspace notifications, **not a durable event log**; if the app is down or notifications are blocked, events can be lost.
- Managed Redis services may restrict the `CONFIG` command, causing enabling keyspace listeners to fail; configure per environment or disable the listener when not required.
- If the entity has secondary indexes, main key expiration and secondary index cleanup may not happen at the exact same moment; test cleanup/isolation must account for all related keys.

Therefore, repository TTL tests should not simply call `repo.save(entity); repo.findById(id)` and assume all index keys and expiration events work. Check the key TTL, post-expiration repository lookup, and event listener/secondary index behavior **in an independent test against real Redis**, with bounded timeouts and proper cleanup.

## 10. Reactive Redis and subscriptions

Spring Data Redis provides `ReactiveRedisTemplate` and `ReactiveStringRedisTemplate` when the right classpath is present. In a reactive application, an operation such as:

```java
Mono<Boolean> written =
        reactiveRedis.opsForValue().set(
                "test:key", "value");
```

is an **illustrative snippet** with `ReactiveStringRedisTemplate reactiveRedis`. It creates a reactive publisher; it does not mean the Redis command executed until the publisher is subscribed to.

A reactive unit/integration test uses Reactor Test:

```java
StepVerifier.create(written)
        .expectNext(true)
        .verifyComplete();
```

This requires imports `reactor.core.publisher.Mono` and `reactor.test.StepVerifier`, a real reactive Redis client, and cleanup. In a WebFlux application, you typically **return the publisher** for the framework to subscribe; do not manually call `.subscribe()` in a controller and assume the command belongs to the HTTP request lifecycle.

To test reactive TTL, compose `set(key,value,ttl)`, `get`, and `getExpire` into publishers and assert signals via `StepVerifier`; distinguish Redis connection errors (`onError`) from a missing key (`Mono.empty()`). `@DataRedisTest` on a reactive classpath **does not prove** reactive execution if the test merely injects the template without subscribing.

## 11. Transactions, atomicity, and test isolation in Redis

Redis has `MULTI`/`EXEC`, yet **it is not a JDBC/JPA rollback transaction**. A sequence of Redis commands:
- Can execute individually.
- Can be batched in a pipeline to reduce round trips (pipelining is **not** a transaction).
- Can use a Redis `MULTI`/`EXEC` transaction, though error/rollback semantics differ from SQL.
- Can use a Lua script to execute multiple operations atomically on the Redis instance.

Do not put `@Transactional` on a test method and conclude all Redis writes vanish at the end of the test. Even with `RedisTemplate.setEnableTransactionSupport(true)` and Spring transaction synchronization, Redis does not become a SQL database with automatic rollback for already-executed commands.

### 11.1. Safe namespaces and cleanup

- Use a per-test-class/run prefix (`learn:redis:<uuid>:`) and track the list of keys owned by each test.
- Clean up in `@AfterEach` or `finally`; when tests create cache keys or repository shadow/index keys, clean up **that entire scope**.
- Use an isolated test container/database for suites if tools generate keys that are hard to track individually.
- **Never call `FLUSHALL` on shared Redis**, especially when host/port come from production-like environment variables.
- With many keys, avoid `KEYS *` in production because scanning the entire keyspace can cause severe blocking. Use `SCAN` with a bounded prefix when scan-based cleanup is required, with appropriate permissions/warnings.
- Tests running in parallel must not use fixed keys like `cache:user:1` unless each has its own Redis instance or partitioning scheme.
- Short TTLs are no substitute for cleanup: tests can fail/abort before expiry, and other data structures may be persistent.

### 11.2. Do not depend on ordering or overly exact timing

A test asserting `ttl == 30` or calling `Thread.sleep(30000)` is easily flaky due to scheduling, network latency, and Redis expiration granularity. Use:
- Range-based TTL assertions.
- Bounded polling when verifying an expired key disappeared.
- Unique test keys so prior suites cannot modify the same key.
- Do not turn on Redis active expiration notifications and assume they provide exactly-once/durable delivery.

### 11.3. Test concurrency/races when required by business logic

For example, `GET` followed by `SET` is a two-command **read-modify-write**; concurrent clients can lose updates. For counters, use atomic `INCR`; for conditional writes, consider `SET NX EX`, Lua, optimistic `WATCH`, or appropriate Redis functions.

A sequential test on real Redis does not prove locking/concurrency under 100 simultaneous requests. Design multi-client integration tests and observe final states if that risk matters. Never add local Java `synchronized` expecting it to lock across separate application instances.

## 12. Debugging common Redis test failures

| Error/symptom | Possible cause | How to check |
|---|---|---|
| `Connection refused` localhost:6379 | `@DataRedisTest` does not start a Redis server | Start Testcontainers, check host/`mappedPort` |
| Context has `RedisTemplate` but `get` fails | Client bean exists, but network/credentials/TLS are wrong | Call real Redis, check URL/port/auth |
| `NoSuchBeanDefinitionException` for hand-written `@Repository` adapter | Component excluded by slice filter | Use `@Import(YourAdapter.class)` |
| `NoSuchBeanDefinitionException` for `@Service` | Service is outside the slice | Test Redis adapter directly or import the needed service |
| `@Cacheable` calls service twice | `NoOpCacheManager`, missing `@EnableCaching`, self-invocation, different key | Assert `RedisCacheManager` and real Redis key |
| `@Cacheable` hits, yet TTL is always -1 | Cache config lacks TTL or key was written outside cache manager | Check `entryTtl`, key prefix, and writer source |
| `getExpire` returns -2 | Key does not exist or already expired | Check key name, serializer, and read timing |
| `getExpire` returns -1 | Key is persistent, TTL unset or lost after overwrite | Check `SET`/`EXPIRE`/`PERSIST` |
| `WRONGTYPE` on `opsForHash` | Key currently holds a Redis String/List/Set/... | `TYPE key`, namespace by data type |
| Redis CLI shows strange/unreadable keys | Binary/JDK serialization | Check template key/value/hash serializers |
| Hash field does not expire individually | Expiration is key-level TTL | Test whole key; if per-field TTL is required, use explicitly supported API/server |
| List test fails ordering | Used `LPUSH` instead of `RPUSH` or read in reverse | Assert exact command direction and range |
| Set test fails on ordering | `SMEMBERS` has no ordering guarantee | Compare as `Set` instead of `List` |
| ZSet ranking test wrong | Confused `range` with `reverseRange`, score ties | Assert scores, direction, and tie contract |
| Test passes even when Redis cache is off | NoOp cache or mock service returns identical values | Assert method invocation count + real Redis key/TTL |
| Previous test's data appears | Redis has no auto-rollback, fixed keys reused | Unique keys, cleanup, isolated container |
| Flaky TTL test | Exact second assertion, fixed sleep, slow CI | Assert range / poll with deadline |
| Redis repository expired event missing | Keyspace notifications off / lost PubSub / `CONFIG` forbidden | Check event listener and Redis config |
| `@RedisHash` entity not found | Wrong package scan or Redis repositories auto-config off | Check package and Redis repositories enabled |
| Real Redis test passes, production fails | Sentinel/Cluster/TLS/serialization differences | Add integration tests close to production topology |

If the build fails during Spring context initialization, inspect the root cause under `Caused by`. If the test context starts yet commands fail, check **which server** the client connects to, key serializers, and the Redis commands issued. If a TTL assertion fails, check **whether a TTL exists at all** before blaming scheduling.

## 13. Version lines: Boot 3.5 vs. Boot 4

The complete examples in Sections 5–7 target **Spring Boot 3.5.x**, using:

```java
org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest
```

In Spring Boot **4.x**, the Redis test slice moves to a dedicated module `spring-boot-data-redis-test`, with annotation:

```java
org.springframework.boot.data.redis.test.autoconfigure.DataRedisTest
```

This is a **list of import names**, not a standalone Java program. When upgrading Boot, switch test dependencies/modules and imports to match the Boot BOM. Never mix Spring Boot 4.x test dependencies with a Spring Boot 3.x runtime to "fix" `Cannot resolve symbol DataRedisTest`.

In Spring Boot 4, the **list of imported auto-configs** for `@DataRedisTest` may differ from Boot 3.5 (Redis connections, reactive, and Redis repositories remain central). Do not carry over assumptions about Boot 3.5's no-op cache into an unverified Boot 4 context. A safer practice is to **verify the actual `CacheManager`, Redis template/serializer, Redis connection, and TTL of a created key**.

When migrating Spring Data Redis:
- Check changes in serializers, DTO schemas, and key prefixes; an object round-tripping with the same new serializer does not prove older app instances can read it.
- Check `@RedisHash` TTL/index/keyspace notifications and Redis `CONFIG` privileges.
- Check topology: standalone vs. Sentinel/Cluster vs. managed Redis, SSL/TLS, ACL username/password.
- Run contract tests for keys/TTL/cache behavior against the exact Redis server version.
- Do not treat this demo's Redis 7.4 as automatic proof for Redis 6.x, Redis 8.x, or a more restrictive managed service.

## 14. Running the test suite and reading reports

From the project root with Gradle wrapper, Linux/macOS:

```bash
./gradlew test --tests "com.example.redisslice.RedisStructuresStoreTest"
./gradlew test --tests "com.example.redisslice.RedisCacheSliceTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.redisslice.RedisStructuresStoreTest"
.\gradlew.bat test --tests "com.example.redisslice.RedisCacheSliceTest"
```

Maven wrapper with equivalent dependencies, Linux/macOS:

```bash
./mvnw -Dtest=RedisStructuresStoreTest test
./mvnw -Dtest=RedisCacheSliceTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=RedisStructuresStoreTest test
.\mvnw.cmd -Dtest=RedisCacheSliceTest test
```

These commands assume the project has a wrapper, JDK 17+, an active Docker daemon, and permissions to pull/start Redis containers. In Gradle, reports are normally at `build/reports/tests/test/index.html`, and Maven Surefire reports at `target/surefire-reports/` (within the relevant module). Verify that test classes were discovered and executed; Docker unavailable, skipped, or `NO-SOURCE` does **not** mean PASS.

The sample codebase contains **10 test methods** in `RedisStructuresStoreTest` and **2 test methods** in `RedisCacheSliceTest`. There is no fixed `System.out.println` output, so do not fabricate stdout. This is written documentation and sample code; run it in an environment with Docker and matching dependencies before claiming runtime tests passed.

## 15. Checklist when reviewing @DataRedisTest

- [ ] Clearly identified that the Redis test slice focuses on **Redis templates/repositories/entities**, not a full controller/service context.
- [ ] Aware that `@DataRedisTest` **does not start a Redis server automatically**; connected to a suitable test Redis instance.
- [ ] If testing a hand-written `@Repository` adapter/DAO, used `@Import` for the real implementation.
- [ ] Not using a mocked `RedisTemplate` to claim real SQL/Redis commands, TTLs, or data structure correctness.
- [ ] Each key group has a clear namespace; tested `TYPE` when data must be a specific String/Hash/List/Set/ZSet.
- [ ] Hash tests verify field mapping and key-level TTL; not assuming fields have individual TTLs by default.
- [ ] List tests protect order/duplicates; Set tests protect uniqueness; ZSet tests protect scores/direction.
- [ ] TTL tests distinguish positive TTL, `-1` persistent, and `-2` missing; using ranges and bounded polling.
- [ ] Redis-writing tests have their own cleanup/namespace; not relying on SQL rollback or `FLUSHALL`.
- [ ] For `@Cacheable`, verified the actual cache manager is `RedisCacheManager` and `@EnableCaching` is enabled; not silently no-op in the slice.
- [ ] Asserted cache hit/miss via method invocation count **and** actual Redis key/value/TTL inspection.
- [ ] Verified serialization, cache key prefix, and invalidation/eviction policies if the API depends on them.
- [ ] If using `@RedisHash`, accounted for secondary keys/indexes/phantom copies and limited reliability of expiry events.
- [ ] If using Reactive Redis, subscribed via `StepVerifier` or the framework to ensure commands run.
- [ ] When correctness depends on concurrent access, tested atomicity/races across multiple clients; not confusing pipelines with transactions.
- [ ] Ran the exact JUnit classes under the right Boot version, reviewing reports and Docker container logs on errors.

## 16. Official references

- [Spring Boot 3.5 — Auto-configured Data Redis Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataRedisTest` scope and `@RedisHash` scanning conditions.
- [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): Redis auto-configurations included in the slice.
- [Spring Boot 3.5 — AutoConfigureCache API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/core/AutoConfigureCache.html): default `NoOpCacheManager` in testing support.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, operations views, serializers.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, key prefix, TTL/TTI, serialization.
- [Spring Data Redis — TTL of Redis repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash`, `@TimeToLive`, keyspace notifications, and shadow copies.
- [Spring Boot 4 — Test Slices](https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html): Redis test slice packages/modules in the Boot 4 line.

**Conclusion:** `@DataRedisTest` lets you test **real Spring Data Redis** without booting the whole application, yet the annotation itself **neither creates a Redis server nor guarantees real Redis caching**. With Redis Testcontainers, test the actual data types (`String`, `Hash`, `List`, `Set`, `Sorted Set`), TTL/expiration, serializers, key prefixes, and cleanup. If the target is `@Cacheable`, explicitly enable caching and configure a real `RedisCacheManager` to avoid no-op caching; if using Redis repositories, also verify `@RedisHash`, TTL, and secondary keys/indexes. A green test is meaningful only when it goes through the **exact Redis data structure and server** the contract is meant to protect.
