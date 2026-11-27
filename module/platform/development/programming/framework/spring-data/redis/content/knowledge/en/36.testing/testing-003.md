# Using Testcontainers with a Production-Aligned Redis Server in Spring Data Redis

Testing Spring Data Redis solely with a mocked `RedisTemplate`, an in-memory fake Redis, or a Redis instance pre-installed on a developer's machine often misses bugs that only appear when the application actually talks to a Redis Server: incompatible serializers, unexpected TTL expiration, Lua returning the wrong type, `WRONGTYPE` command errors, mismatched cache key prefixes, Redis ACL rejections, or Redis Cluster limitations. **Testcontainers** lets each test suite start a real Redis Server inside a Docker container and run integration tests using the exact `RedisConnectionFactory` and Spring Data Redis APIs used by the application.

However, **having a Redis container does not mean the environment matches production**. For test results to be valid, you must verify parity across **Redis version, distribution and modules, configuration, serializers, networking, security, topology, persistence, resource limits, and load characteristics**. If production uses Redis Sentinel or Cluster, a single `GenericContainer` running standalone Redis only proves standalone behavior—it cannot by itself prove failover, redirects, or hash-slot constraints.

This lesson explains how to use Testcontainers with Spring Boot, JUnit 5, and Spring Data Redis; how to simulate key production factors; practical real-Redis tests you can apply; and when to move from a single container to a multi-container topology.

## 1. Goals of Integration Testing with Real Redis

Redis testing can be divided into levels:

| Testing Level | How It Is Performed | What It Can Prove |
|---|---|---|
| Unit test | Mock repository/service, `RedisTemplate`, or custom abstraction | Method call logic, branching, result mapping |
| Single real-Redis integration test | Testcontainers running standalone Redis, Spring Data Redis connects to it | Serialization, TTL, data types, Lua, cache manager, real Redis errors |
| Topology integration test | Multiple Redis containers + Sentinel/Cluster | Failover, discovery, slot routing, reconnect, cross-slot |
| Resilience/chaos test | Toxiproxy or fault injection in an isolated environment | Timeouts, packet loss, connection cuts, recovery, unknown outcomes |
| Load/capacity test | Near-production dataset and load with memory/disk limits | Throughput, p95/p99, OOM, eviction, persistence overhead |
| Staging/end-to-end | Application and near-production infrastructure | System behavior when multiple components collaborate |

Crucial point: **do not use results at one level to claim coverage at another**. A `@SpringBootTest` connecting to real standalone Redis does not automatically test Redis Cluster, and a Testcontainers test running a few `SET`/`GET` commands is no substitute for benchmarking or data recovery testing.

### 1.1. Bugs That Mocks or Fake Redis Struggle to Catch

- `StringRedisSerializer` and `GenericJackson2JsonRedisSerializer` write/read different bytes.
- A key exists as a String, but code calls `HGET`, resulting in `WRONGTYPE`.
- `@Cacheable` returns `null`, but `RedisCacheManager` is configured not to cache nulls.
- Different cache name/prefix causes `@CacheEvict` not to delete the intended entry.
- `SET` has a TTL, yet the test only checks the value immediately after writing.
- Lua running on Redis returns a `Long`, `List`, or error contrary to assumptions.
- A script accesses multiple keys across different slots when deployed to Cluster.
- Redis `maxmemory-policy` causes data eviction or write rejections.
- AOF/snapshots incur unexpected overhead or behave differently than assumed.
- Client fails to authenticate with Redis ACL/TLS.
- An older Redis container supports a different command set than production Redis.

Mocks remain useful for unit tests. But when the goal is verifying the **real contract between Spring Data Redis and Redis Server**, you need a real Redis Server.

## 2. What Does “Production-Aligned” Mean?

You do not need to clone all of production verbatim into CI. “Aligned” means characteristics **capable of changing the outcome of the test** must be simulated closely enough.

| Aspect | Must Match Production | Why It Matters |
|---|---|---|
| Redis version | Major/minor, sometimes patch | Command set, persistence format, module behavior, bug fixes |
| Redis distribution | Redis OSS/Redis Stack, managed-compatible image | Available modules and commands |
| Topology | Standalone, Sentinel, Cluster, replicas | Routing, failover, multi-key constraints |
| Spring Data Redis/driver | Spring Boot, Spring Data Redis, Lettuce/Jedis | Serialization, connections, retries, command support |
| Persistence | RDB/AOF, `appendfsync`, auto-rewrite | Durability, disk pressure, restarts |
| Memory | `maxmemory`, eviction policy, cgroup limits | OOM, `OOM command not allowed`, eviction |
| TTL | Key expiration, cache TTL, null-cache behavior | Cache correctness |
| Security | Password, ACL, TLS, network policy | Authentication/authorization |
| Key schema | Prefix, key serializer, hash tags | Data compatibility and Cluster slots |
| Modules | JSON, Search, Bloom, or other modules | Module commands do not exist on plain Redis |
| Dataset | Key count, value sizes, data types | Memory footprint and command latency |
| Failure model | Crashes, disconnects, failover, slow network | Retry behavior and consistency |

For example, if production is standalone Redis 7.x using AOF and `noeviction`, a test container running default Redis 6.x without AOF and with `allkeys-lru` **does not accurately reflect scenarios involving persistence and memory policies**.

Conversely, a pure String serializer test might not need a multi-node topology. Organize suites by fidelity tier instead of forcing every test to spin up a complex cluster.

## 3. Choosing a Redis Image and Managing Versions

Testcontainers runs Docker images. For standard Redis Server, you can use the official Redis image:

```text
redis:7.2.5-alpine
```

This is an **example of an image with a specific version tag**, not a recommendation that production must run Redis 7.2.5. When applying this, replace it with the tag/digest matching your real system.

Do not base important tests on:

```text
redis:latest
```

because a new image can change major versions without any code/test changes, causing unexpected CI failures.

### 3.1. Pinning Tags or Digests

You can choose:

```java
DockerImageName.parse("redis:7.2.5-alpine")
```

For CI requiring strict reproducibility, consider **pinning the digest** of an approved image:

```text
redis@sha256:<verified-digest>
```

The digest must come from the registry for the right architecture/manifest—never plug in a sample hash and assume it works. Pinning digests prevents the image contents from mutating under the same tag; in return, image updates must be actively managed to receive security patches.

### 3.2. Do Not Confuse Standard Redis Server with Redis Stack

If production uses Redis Stack or Redis with JSON or Search modules:

```redis
JSON.SET ...
FT.SEARCH ...
```

a standard `redis:...` image may **not include those module commands**. In that case, use the matching image/distribution or load the same modules as production.

Testing `SET`/`GET` on plain Redis cannot verify that a repository using RediSearch indexes, JSONPath, or RedisBloom works properly.

### 3.3. Should You Run Multiple Redis Versions in CI?

If your application must support multiple Redis versions, you can use a **test matrix**:

```text
Redis version A -> integration suite
Redis version B -> integration suite
Redis version C -> integration suite
```

However, for verifying production behavior, at least one profile must closely track the exact version actually deployed. Do not let “testing every version” replace testing the **exact version** your system runs.

## 4. Testcontainers Dependencies with Spring Boot and JUnit 5

A Gradle Groovy DSL project can declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Here, Testcontainers versions are usually managed via a BOM/dependency management aligned with Spring Boot or a project BOM. Do not randomly mix Testcontainers modules from different major versions.

If using Spring WebFlux:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
```

and the test suite may also need `reactor-test`, depending on what is already pulled in by the test starter.

If you want to use Spring Boot's `@ServiceConnection` when supported by your Boot version:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

You do not need an “embedded Redis” library just to run a real server. Testcontainers requires a container environment capable of running Docker images, not a Java-based Redis simulator.

### 4.1. Requirements for the Test Execution Environment

- A Docker daemon or container runtime compatible with Testcontainers.
- CI runners with permissions to pull images and create/stop containers.
- Network routing allowing the test JVM to connect to ports mapped by Testcontainers.
- Sufficient CPU/RAM/disk for Redis and the application under test.
- Registry network/proxy configuration suited to corporate environments.
- Container cleanup policies after tests to prevent resource leaks.

**If CI cannot run Docker, tests should fail loudly with an infrastructure error** rather than silently switching to a public/production Redis or skipping critical tests.

## 5. Simple Example: `GenericContainer` Running Real Redis

A specialized `RedisContainer` class is not strictly required. `GenericContainer` works for Redis Server because we know the image, port, and startup command.

```java
package com.example.redis;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.containers.wait.strategy.Wait;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class RedisRealServerIT {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                DockerImageName.parse("redis:7.2.5-alpine")
            )
            .withExposedPorts(REDIS_PORT)
            .waitingFor(Wait.forListeningPort());

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            redis::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(REDIS_PORT)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void canWriteAndReadThroughSpringDataRedis() {
        String key = "it:redis:roundtrip";

        try {
            template.opsForValue().set(key, "hello");
            assertEquals("hello", template.opsForValue().get(key));
        } finally {
            template.delete(key);
        }
    }
}
```

This is a true integration test:

1. JUnit/Testcontainers starts the Redis container.
2. Spring Test receives the real Redis address via `@DynamicPropertySource`.
3. Spring Boot builds `RedisConnectionFactory` from those properties, unless overridden by another bean.
4. `StringRedisTemplate` connects to real Redis and runs commands.
5. The test verifies the result and deletes the key.
6. Testcontainers stops the container according to the test lifecycle.

### 5.1. Why Must You Use `getHost()` and `getMappedPort()`?

Inside the container, Redis listens on port `6379`. On the host or CI runner, Testcontainers may map it to a dynamic port:

```text
Redis inside container :6379
          |
          v
Docker mapped port on host :32781
          |
          v
Spring application test
```

Therefore, do not hardcode:

```java
registry.add("spring.data.redis.port", () -> 6379);
```

and do not assume the host is always `localhost`.

The right way:

```java
registry.add("spring.data.redis.host", redis::getHost);
registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
```

`getHost()` can differ in remote Docker environments; Testcontainers provides the endpoint suitable for the **JVM running the tests**.

### 5.2. Why Is the Container a `static` Field?

With the JUnit 5 Testcontainers extension, `@Container static` creates a container shared across the lifecycle of **one test class**. Redis does not have to restart for every test method, saving time.

This **does not automatically guarantee data isolation between test methods**. If test A writes key `user:42` without deleting it, test B can still see it. You need a namespace strategy, cleanup, or separate containers as required.

### 5.3. Why Not Call `start()` Again in `@BeforeAll`?

With `@Testcontainers` and `@Container`, the extension manages the lifecycle. Calling `redis.start()` elsewhere is unnecessary and can make lifecycle management confusing.

Another option is managing a singleton container in custom code, in which case readiness, startup, shutdown, and Spring context caching must all be handled properly. Do not mix lifecycle strategies without a reason.

## 6. `@DynamicPropertySource` and Spring Configuration Scope

`@DynamicPropertySource` overrides registered properties in the Spring test environment when the context is constructed.

```java
@DynamicPropertySource
static void overrideRedis(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port", () -> redis.getMappedPort(6379));
}
```

This is especially helpful when the project has a default `application.yml` pointing to Redis in another environment. Tests must **actively force Spring to use the container** instead of accidentally connecting to a developer's or staging's Redis.

### 6.1. Watch Out for Hand-Written `RedisConnectionFactory` Beans

If the application configuration defines a bean:

```java
@Bean
RedisConnectionFactory connectionFactory() {
    return new LettuceConnectionFactory("redis-production", 6379);
}
```

registering `spring.data.redis.host` may **not change** the endpoint that bean uses, because a custom bean does not necessarily read Boot properties.

Before trusting an integration test, ensure the actual bean used by `RedisTemplate` points to the container or is configured to accept dynamic endpoints in tests.

This is a classic way tests **pass green while actually connecting to an unintended Redis**. You should have a test observing the Redis container, use a dedicated namespace, and configure network/CI rules forbidding connections to production.

### 6.2. Spring Boot Versions and Prefixes

In Spring Boot 3.x, the standard property group is:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Older Boot versions may use a different prefix. When upgrading versions, always use the property group matching the running application version; do not blame `@DynamicPropertySource` when the test simply uses an obsolete property name.

## 7. Optional `@ServiceConnection` When Supported by Spring Boot

Spring Boot versions supporting Testcontainers service connections can auto-generate connection details from an appropriately declared container, avoiding manual host/port property wiring.

Conceptual example:

```java
@SpringBootTest
@Testcontainers
class RedisServiceConnectionIT {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2.5-alpine")
        ).withExposedPorts(6379);

    // @Autowired StringRedisTemplate template;
}
```

The snippet above requires the corresponding imports, such as `org.springframework.boot.testcontainers.service.connection.ServiceConnection`, and the `spring-boot-testcontainers` dependency.

**Do not assume this example fits every Spring Boot version or every custom Redis image.** Service connections recognize containers by image/type and the Boot version's factory mechanism. With a `GenericContainer` using a custom image, `name = "redis"` helps identify the service, but you still must verify connection details are generated properly.

If the production image uses multiple ports, special TLS/ACL, or Sentinel/Cluster topology, a simple `@ServiceConnection` may not express enough. In those cases, `@DynamicPropertySource` or dedicated test configuration provides clearer endpoint control.

### 7.1. Which Approach Should You Choose?

| Approach | Pros | Suitable Scope |
|---|---|---|
| `@DynamicPropertySource` | Explicit host/port/password, easy to inspect configuration | Across Spring Boot versions, custom Redis setups |
| `@ServiceConnection` | Less boilerplate if Boot recognizes the service | Supported Boot versions and recognized containers |
| Spring test `@Import` configuration | Reuses parameterized production beans | Complex custom configurations |
| Self-managed singleton container | Can share a container across test classes | Requires careful Spring context caching/lifecycle handling |

In this lesson, `@DynamicPropertySource` is used as the primary example to make clear **how container endpoints are injected into Spring Data Redis**.

## 8. Configuring the Redis Container Closer to Production

By default, the official Redis image runs with specific default settings. If production uses AOF, memory caps, `noeviction` policies, or keyspace notifications, enable the exact factors your tests verify.

Example test-only configuration:

```java
@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "--appendonly", "yes",
        "--appendfsync", "everysec",
        "--save", "",
        "--maxmemory", "256mb",
        "--maxmemory-policy", "noeviction",
        "--notify-keyspace-events", "Ex"
    )
    .waitingFor(Wait.forListeningPort());
```

Meaning of these settings:

| Setting | Purpose |
|---|---|
| `appendonly yes` | Enables AOF |
| `appendfsync everysec` | Selects an illustrative fsync policy |
| `save ""` | Disables automatic RDB snapshot triggers in this example |
| `maxmemory 256mb` | Logical memory limit for the lab Redis |
| `maxmemory-policy noeviction` | When hitting the limit, do not evict keys via LRU |
| `notify-keyspace-events Ex` | Enables expiration notifications according to configuration |

This is **not** a complete production configuration copy. The goal is simulating a set of settings that directly impact the tests.

### 8.1. Do Not Pick Too Small a Memory Limit for All Tests

A `maxmemory 32mb` setting may prevent Redis from loading large fixtures or cause AOF rewrites to fail, even though production has tens of GiB. Conversely, if you want to test `noeviction` and logical OOM errors, use a dedicated suite with a low threshold and matching data.

**A functional test suite and a memory-pressure test suite may need different Redis configurations.** Do not make everyday integration tests flaky by setting an ultra-low memory limit everywhere.

### 8.2. Account for Cgroup Memory as Well

`--maxmemory 256mb` is the threshold Redis uses for data/memory policies; it is **not** the Docker container memory limit. Fork/COW during RDB/AOF rewrites, allocator overhead, buffers, and page cache can push real memory higher than `maxmemory`.

To test OOM scenarios, configure container/host resource limits and monitor cgroup metrics appropriately rather than looking only at `INFO memory`.

## 9. Using a Separate `redis.conf` File When Configuration Grows

When tests need many flags, stuffing everything into `withCommand` becomes hard to read. You can store a test config file in `src/test/resources/redis/redis-test.conf`:

```conf
bind 0.0.0.0
protected-mode yes
port 6379

appendonly yes
appendfsync everysec
save ""

maxmemory 256mb
maxmemory-policy noeviction

notify-keyspace-events Ex
```

Then copy the file into the container and launch Redis with it:

```java
import org.testcontainers.utility.MountableFile;

@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withCopyFileToContainer(
        MountableFile.forClasspathResource(
            "redis/redis-test.conf"
        ),
        "/usr/local/etc/redis/redis.conf"
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "/usr/local/etc/redis/redis.conf"
    );
```

**Security scope:** if Redis binds `0.0.0.0` with `protected-mode yes`, accepting connections depends on Redis authentication/network rules. The example above needs a test verifying the JVM is actually allowed to connect. Across different network setups and Redis versions, design proper ACL/password/TLS settings. Never take an unsecured lab file straight to production.

### 9.1. Creating Profiles Aligned with Production Versions

Maintain a **Redis config profile for integration tests** cross-checked against production:

```text
Redis test config
  |
  +-- settings affecting business behavior
  +-- timeouts/limits for CI
  +-- dummy endpoints & credentials for testing
```

You do not need to copy secrets, real user data, or production hostnames. Environment values like test passwords, test certificates, and resource limits can differ, but **important Redis semantics** must be simulated.

### 9.2. Verifying the Config Was Actually Applied

An easily missed mistake: the container starts, but a flag was wrong or another config file was used. You can verify via Redis CLI inside the container:

```java
var result = redis.execInContainer(
    "redis-cli",
    "CONFIG",
    "GET",
    "appendonly"
);

assertEquals(0, result.getExitCode());
// Verify the actual output matches "yes".
```

Or:

```java
var info = redis.execInContainer(
    "redis-cli",
    "INFO",
    "server"
);

assertEquals(0, info.getExitCode());
// Read redis_version from output to verify against target image.
```

When password/TLS is enabled, Redis CLI commands must also pass appropriate authentication; tests must never put production passwords into code or logs.

## 10. Properly Testing Password/ACL Configurations

An unauthenticated default Redis cannot prove the application configured credentials properly.

Example **lab-only password**:

```java
private static final String TEST_PASSWORD = "test-only-password";

@Container
static final GenericContainer<?> redis =
    new GenericContainer<>(
        DockerImageName.parse("redis:7.2.5-alpine")
    )
    .withExposedPorts(6379)
    .withCommand(
        "redis-server",
        "--requirepass", TEST_PASSWORD
    );

@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add(
        "spring.data.redis.port",
        () -> redis.getMappedPort(6379)
    );
    registry.add(
        "spring.data.redis.password",
        () -> TEST_PASSWORD
    );
}
```

`requirepass` is a simple compatibility mechanism; it **does not replace Redis ACL testing with multiple users, command permissions, and key patterns**.

Points to remember:

- The official Redis Docker image does not enable a password just because an environment variable named `REDIS_PASSWORD` exists. You must configure the Redis server explicitly per the image used.
- Do not commit production credentials into annotations, Git repositories, or CI logs.
- If production uses ACL `user`, `~key-pattern`, `+command`, test both **allowed** and **denied** operations.
- If production uses TLS, opening a plain Redis port with a password is not TLS parity testing; configure certificates, truststores, and TLS ports matching infrastructure.
- Test Redis passwords and certificates should be disposable dummy data, never shared with real systems.

## 11. Testing String Data, TTL, and Real Expiration

A useful test does not just verify `SET` then `GET`—it also verifies the key expires automatically on the Redis Server.

Example:

```java
package com.example.redis;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class RedisTtlIT {

    // Assumes the class defines the Redis container and DynamicPropertySource
    // as in section 5, or extends a corresponding test base class.

    @Autowired
    StringRedisTemplate redis;

    @Test
    void valueExpiresOnRealRedisServer() {
        String key = "it:ttl:" + UUID.randomUUID();

        redis.opsForValue().set(
            key,
            "temporary",
            Duration.ofSeconds(2)
        );

        assertEquals(
            "temporary",
            redis.opsForValue().get(key)
        );

        Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl >= 0 && ttl <= 2);

        // Verify the key actually disappears using bounded polling,
        // rather than assuming the JVM controls Redis's clock.
        long deadline = System.nanoTime()
                + Duration.ofSeconds(10).toNanos();

        while (Boolean.TRUE.equals(redis.hasKey(key))
                && System.nanoTime() < deadline) {
            try {
                Thread.sleep(100);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                fail("Test interrupted", ex);
            }
        }

        assertFalse(Boolean.TRUE.equals(redis.hasKey(key)));
    }
}
```

This is an example of **real testing with Redis time**. In real projects you can use Awaitility for cleaner polling, yet the essential rule remains: **do not check immediately after `SET` and claim expiration works**.

### 11.1. TTL on Redis Uses Server Real Time

`StepVerifier.withVirtualTime(...)` or a mocked clock in Java **does not advance the Redis Server's clock**. When testing TTL of a real Redis key, you must:

- Wait in real time or use an appropriate test mechanism.
- Pick a TTL short enough to keep tests fast, yet not flaky due to scheduling.
- Poll with a timeout rather than calling `Thread.sleep` once and asserting.
- Understand `TTL` returns whole-second resolution and special values.
- Delete leftover keys after the test if needed.

Redis `TTL` typically returns these values:

| Result | Meaning |
|---|---|
| Non-negative number | Remaining seconds |
| `-1` | Key exists but has no TTL |
| `-2` | Key does not exist |

If you want to measure expiration timing closely, use `PTTL` with millisecond resolution via the appropriate command/API. Never write overly tight assertions based on an exact timestamp on shared CI runners.

### 11.2. Testing Expiration Events Differs from Testing TTL

If the application has a `RedisMessageListenerContainer` subscribed to keyspace/keyevent notifications, tests must enable:

```conf
notify-keyspace-events Ex
```

and the listener must subscribe to the right channel. However, Redis keyevent notifications use Pub/Sub and do not retain messages for offline subscribers. Event tests can become flaky if the listener has not finished subscribing before the key expires.

Separate:

- **TTL semantics:** the key disappears.
- **Notification semantics:** an online listener receives the appropriate event.

Do not treat an emitted event as proof that every subscriber processed it successfully.

## 12. Testing Serialization and Incompatible Values

A common issue when moving from fake Redis to a real server is keys/values being serialized differently than expected.

Example:

```java
StringRedisTemplate strings;
RedisTemplate<String, ProductDto> products;
```

The two templates may use different serializers. Redis stores bytes; if a key is written with a JSON serializer and read with JDK serialization or an incompatible String serializer, reads can fail.

### 12.1. Testing DTO Round-Trips

Suppose production defines a `RedisTemplate<String, ProductDto>` bean with a String key serializer and JSON value serializer. Integration test:

```java
record ProductDto(String id, String name) {}

@Autowired
RedisTemplate<String, ProductDto> productRedisTemplate;

@Test
void productSerializerRoundTrip() {
    String key = "it:product:" + UUID.randomUUID();

    ProductDto expected = new ProductDto("p-42", "Desk");

    try {
        productRedisTemplate.opsForValue().set(key, expected);

        ProductDto actual =
                productRedisTemplate.opsForValue().get(key);

        assertEquals(expected, actual);
    } finally {
        productRedisTemplate.delete(key);
    }
}
```

This test is only valid when `productRedisTemplate` is the exact serializer bean used by the production service. Creating a completely separate test template will not verify the real contract.

### 12.2. Inspecting Data from Redis CLI When Needed

You can inspect raw values on Redis via CLI to see whether Redis stores String, JSON, or binary formats. For serializers embedding type metadata, test cross-version reads across two application versions during rolling deployments.

Cases worth testing:

- DTO adds a new field.
- DTO removes/renames a field.
- `null` values in cache.
- `Optional.empty()` through the Spring Cache abstraction.
- Unicode keys, spaces, and special characters.
- Large values; nested structures.
- Separation between String and Hash namespaces to avoid `WRONGTYPE`.

**Do not use Java object equality from a mocked serializer as proof that raw Redis data is compatible across services.**

## 13. Testing `RedisCacheManager` with Production-Like Configuration

In applications using `@Cacheable`, `@CachePut`, or `@CacheEvict`, test the **real cache manager**: cache names, key prefixes, serializers, TTL, and null policies.

Example testing Spring Cache directly:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.cache.RedisCache;

import static org.junit.jupiter.api.Assertions.*;

class RedisCacheContractIT {

    @Autowired
    CacheManager cacheManager;

    @Test
    void cacheManagerStoresAndEvictsEntry() {
        Cache cache = cacheManager.getCache("products");
        assertNotNull(cache);
        assertInstanceOf(RedisCache.class, cache);

        String key = "it:" + UUID.randomUUID();

        cache.put(key, "cached-value");
        assertEquals(
            "cached-value",
            cache.get(key, String.class)
        );

        cache.evict(key);
        assertNull(cache.get(key));
    }
}
```

This snippet assumes it runs **inside a Spring test context** with Spring Cache enabled, a `RedisCacheManager`, and a Redis container. The test method is shown standalone to focus on the contract; to use it as a complete class, add annotations/context setup like in section 5.

### 13.1. Testing Method Caching, Not Just the `Cache` API

Interacting directly with `CacheManager` does not test Spring Cache proxies/interceptors. For `@Cacheable`, have an integration test invoking the method through a Spring bean:

```text
Call 1 -> calls repository -> writes Redis
Call 2 -> reads Redis -> skips repository
Evict  -> entry is deleted
Call 3 -> calls repository again
```

If the method is invoked via `this.cachedMethod()` inside the same object, Spring proxies may not intercept it like an external bean call. Tests must mirror the real call path in the application.

### 13.2. Testing `null` and Spring Cache Serializers

If you want to cache negative lookups with `null`, verify:

- `RedisCacheConfiguration` allows caching nulls.
- The serializer supports representing the internal null marker appropriately.
- Negative cache TTL matches requirements.
- No `unless = "#result == null"` accidentally prevents caching.
- The second call genuinely avoids querying the data source.

A `null` from `StringRedisTemplate.opsForValue().get(key)` usually means a Redis cache miss; it is **different** from the null marker that Spring Cache abstraction writes when the provider allows caching null results.

## 14. Testing Redis Data Type Groups

Real Redis helps verify the data structures your code actually uses:

| Spring Data Redis Group | Redis Commands/Types | Worthwhile Tests |
|---|---|---|
| `opsForValue()` | Strings, counters | `SET`, `GET`, `INCR`, TTL |
| `opsForHash()` | Hash | Field get/put, mapping serializer, `HGETALL` |
| `opsForList()` | List | `LPUSH`/`RPOP`, ordering, empty list |
| `opsForSet()` | Set | Membership and uniqueness |
| `opsForZSet()` | Sorted Set | Scores, rank, and ordering |
| `opsForGeo()` | Geo | Lon/lat, radius, distance |
| `opsForHyperLogLog()` | HyperLogLog | Cardinality estimation, do not test as exact count |
| `opsForStream()` | Stream | `XADD`, read offsets, groups, ACK, pending |
| Lua scripting | `EVAL`/`EVALSHA` | Atomicity and return types |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE` | Subscription lifecycle, message delivery, reconnect |

You do not need one massive test covering every data type. Write focused integration tests per service or contract so failures pinpoint the exact operation that broke.

### 14.1. Testing `WRONGTYPE`

A valuable negative test:

```java
String key = "it:wrongtype:" + UUID.randomUUID();

try {
    redis.opsForValue().set(key, "not-a-hash");

    assertThrows(
        RuntimeException.class,
        () -> redis.opsForHash().get(key, "field")
    );
} finally {
    redis.delete(key);
}
```

The exact exception type is usually translated by Spring Data Redis from the driver; in real project tests, assert the specific `DataAccessException`/Redis error your code is responsible for handling, rather than locking to an error message from one driver version.

Important: use a key owned by the test itself—do not create `profile:production-user` and corrupt real data.

## 15. Testing Lua Scripts on Real Redis Server

Lua scripts execute on the Redis server; Java mocks cannot fully verify `redis.call` semantics, return values, Lua errors, and atomicity.

Example using `DefaultRedisScript<Long>`:

```java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RedisLuaIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void incrbyScriptReturnsNewValue() {
        String key = "it:lua:" + UUID.randomUUID();

        DefaultRedisScript<Long> script =
                new DefaultRedisScript<>();

        script.setScriptText(
            "return redis.call('INCRBY', KEYS[1], tonumber(ARGV[1]))"
        );
        script.setResultType(Long.class);

        try {
            Long result = redis.execute(
                script,
                List.of(key),
                "2"
            );

            assertEquals(2L, result);
            assertEquals(
                "2",
                redis.opsForValue().get(key)
            );
        } finally {
            redis.delete(key);
        }
    }
}
```

This snippet is intended for a Spring test context where `StringRedisTemplate` connects to the real container.

### 15.1. Why Must You Test with the Right Image/Redis Version?

Redis script behavior and command sets can differ across Redis versions; Lua scripts can also depend on serialization, key types, and extended commands.

Beyond the happy path, test:

- Non-existent keys.
- Wrong key types.
- Missing or malformed `ARGV`.
- Return values exceeding the range handled by the Java type.
- Sending two concurrent requests for the same key to verify invariants.
- With Cluster, verifying all keys accessed by the script share the same hash slot.
- After failover/restart, whether `EVALSHA`/`NOSCRIPT` fallback works properly.

Testing a script on standalone Redis cannot detect `CROSSSLOT`; that belongs in a separate Cluster suite.

## 16. Testing Redis Streams and Consumer Groups

If a service uses `StreamOperations`, tests should not stop at `XADD` returning an ID. You must test read semantics, ACK, and recovery when a consumer fails.

A basic test sequence:

```text
1. Create a stream with a unique namespace.
2. Create a consumer group at the chosen offset.
3. XADD an entry with an explicit eventId.
4. XREADGROUP using a dedicated consumer name.
5. Verify the entry is delivered and pending.
6. Execute the handler.
7. XACK after the handler succeeds.
8. Verify the entry is no longer pending.
```

Another test:

```text
1. Read an entry via XREADGROUP.
2. Do not ACK (simulate consumer failure).
3. Check XPENDING.
4. Use an appropriate consumer/reclaim policy to reprocess.
5. XACK after idempotent processing.
```

These tests require a real Redis server to observe the Pending Entries List (PEL).

### 16.1. Boundaries of a Single Redis Container

A single standalone container can test `XADD`, `XREAD`, `XREADGROUP`, `XACK`, and pending state on one server. However, it does not verify:

- Data loss caused by primary failover to an out-of-sync replica.
- Consumer reconnection after Sentinel/Cluster failover.
- Stream key routing on Cluster.
- `XREAD` across multiple streams in different hash slots.
- Persistence and replay capability after a node crash.

When those properties are required, a corresponding topology test is needed.

## 17. Testing Pub/Sub: Lifecycle and Delivery Limits

`RedisMessageListenerContainer` manages subscriptions and dispatches messages to listeners. Tests against real Redis can confirm:

1. The container registers a `ChannelTopic` or `PatternTopic`.
2. Publisher `convertAndSend(...)` sends messages to the right channel.
3. The listener deserializes the payload properly.
4. Parse errors are handled via the appropriate `ErrorHandler`.
5. The subscriber reconnects according to driver/container behavior when the connection drops.

However, Pub/Sub has no durable backlog. If the publisher sends a message **before the listener finishes subscribing**, the message can be lost.

### 17.1. Avoiding Flaky Tests from Subscribe/Publish Races

A test structured as:

```text
start listener asynchronously
immediately PUBLISH message
assert listener received it
```

can fail randomly because the subscription is not yet complete.

Instead:

- Ensure the Spring context and `RedisMessageListenerContainer` are in a ready subscription state.
- Use a suitable signal/latch to wait for listener readiness.
- When needed, observe subscription status on Redis/container without relying on arbitrary timing.
- Send the message after readiness, with a timeout waiting for the callback.
- Avoid short fixed sleeps assuming CI will always be as fast as a developer laptop.

Do not treat `PUBLISH` returning a non-zero subscriber count as proof that the listener processed the business logic successfully.

## 18. `ReactiveRedisTemplate` and `StepVerifier`

If your application uses Spring WebFlux, test Redis using the actual `ReactiveRedisTemplate`/`ReactiveStringRedisTemplate`—do not substitute the synchronous template and assume reactive APIs behave identically.

Example:

```java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;

import reactor.test.StepVerifier;

class ReactiveRedisIT {

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void reactiveRoundTrip() {
        String key = "it:reactive:" + UUID.randomUUID();

        StepVerifier.create(
            redis.opsForValue()
                .set(key, "value", Duration.ofSeconds(30))
                .then(redis.opsForValue().get(key))
        )
            .expectNext("value")
            .verifyComplete();
    }
}
```

This snippet lives inside a Spring test context containing the container and reactive beans.

Bugs this helps catch:

- A publisher is created but never subscribed to.
- Calling `.block()` on a WebFlux event-loop thread.
- Confusing `Mono.empty()` with a Redis error.
- Reactive serializers incompatible with synchronous templates.
- `flatMap` processing too many keys and overloading connections.
- Timeouts/retries on non-idempotent write commands.

`StepVerifier.withVirtualTime` does not make Redis Server expire TTL faster. TTL is a real-time server mechanism and must be tested using real clocks or corresponding server control.

## 19. Data Isolation Between Tests

A static Redis container is shared across a test class. If running multiple test methods:

```text
Test A writes cache:product:p1
Test B assumes cache:product:p1 does not exist
```

then test B's outcome depends on execution order.

Isolation approaches:

### 19.1. Dedicated Namespace per Test

```java
String key = "it:" + UUID.randomUUID() + ":product:p1";
```

Pros:

- Does not collide with keys from other tests.
- Supports parallel execution when each test stays inside its own namespace.
- Avoids wiping the entire DB.

Cons:

- If application code builds fixed keys, you need an injectable key prefix or test profile.
- Requires cleanup or TTL to prevent data buildup in long-lived test containers.

### 19.2. Cleanup by Key

```java
try {
    // Test logic.
} finally {
    redis.delete(key);
}
```

Good for a small set of explicit keys. For services generating many keys/indexes, design a dedicated cleanup strategy.

### 19.3. `FLUSHDB` Only Inside an Isolated Redis

`FLUSHDB` is acceptable inside a Redis container belonging strictly to **one isolated test suite**. Never run `FLUSHDB` when the container/DB is shared by parallel tests, because one test can wipe another test's data.

**Never run keyspace-wiping commands on production or shared staging Redis just because a test class has a `@BeforeEach` method.**

### 19.4. Do Not Use `SELECT` as a Universal Solution for Cluster

Standalone Redis supports multiple logical DBs depending on config. Redis Cluster typically uses database `0` and does not support partitioning via `SELECT 1`, `SELECT 2` in the same way.

Therefore, if your code will run on Cluster, dedicated namespaces/prefixes are usually a better strategy than assigning a separate DB index per test.

## 20. Static Containers, Spring Context Caching, and Parallel Tests

Spring Test caches `ApplicationContext` instances to reduce startup time. The Testcontainers extension scopes `@Container static` to the test class lifecycle.

Watch out for this scenario:

```text
TestClassA:
  static Redis container A
  Spring context A -> A's host:port

TestClassA finishes -> container A stops

TestClassB:
  Spring may reuse the matching cached context
  but endpoint A is no longer valid
```

This is a classic source of flaky tests when reusing Spring contexts with dynamic properties and mismatched container lifecycles.

Mitigations:

- Share the container in a test base/context scope with an explicit shared lifecycle.
- When endpoint properties change across test classes, refresh the context (`@DirtiesContext`) if necessary.
- Never let a long-lived context retain a connection factory pointing to a stopped container.
- Do not blindly combine `@Testcontainers` static fields with a custom-managed singleton pattern.
- When running tests in parallel, enforce separate namespaces and isolated side effects.

Testcontainers offers container reuse for developer workstations, but using reuse in CI requires weighing **stale data, config drift, and reproducibility**. By default, prefer tests independent of previous runs.

## 21. Wait for Redis Readiness, Not Just Docker Reporting Container Running

A Redis container can be in `running` state before it is ready to serve operations—for example, while loading a large AOF or initializing modules.

Testcontainers can use a wait strategy:

```java
.waitingFor(Wait.forListeningPort())
```

This is usually enough for a small standalone Redis, but when stricter readiness is needed, add a probe:

```text
redis-cli PING -> PONG
```

or wait for specific readiness via appropriate Redis commands.

### 21.1. An Open Port Does Not Mean the Application Will Be Allowed to Connect

If Redis requires ACL/TLS, readiness checks may need authentication. A health check sending unauthenticated `PING` can get `NOAUTH`, even though the server is up and a properly configured app can connect.

For Cluster or Sentinel, readiness also includes:

- Sentinel has discovered primary and replicas.
- Cluster has all 16,384 hash slots assigned.
- Redis nodes can reach each other.
- Node endpoints advertised by Redis/Sentinel are **reachable from the JVM**.
- Client has the right credentials/TLS configured.

**Choose readiness per contract test**, rather than applying a generic "port listening" check to every topology.

## 22. When Production Uses Redis Sentinel

A standalone Redis container does not simulate Sentinel failover. If production uses Sentinel, build a dedicated suite containing:

```text
                   Spring Boot test
                         |
                   Sentinel seeds
                         |
        +----------------+----------------+
        |                |                |
     Sentinel 1       Sentinel 2       Sentinel 3
                         |
              Redis primary + replicas
```

Things to test:

1. Spring `RedisConnectionFactory` uses **Sentinel configuration**, not a single fixed Redis host.
2. `SENTINEL get-master-addr-by-name` returns the primary's address.
3. Replicas sync with the primary before fault injection.
4. When the primary is stopped in the lab, Sentinel promotes a new replica.
5. The Redis client discovers and reconnects to the new primary.
6. `SET`/`GET` commands from Spring Data Redis succeed again.
7. Writes in flight during primary switchover may have uncertain outcomes.
8. When the old primary returns, it assumes the appropriate role without keeping clients pinned to the stale endpoint.

### 22.1. Docker Addressing Trap

Inside a Docker network, Sentinel may advertise internal Redis addresses like:

```text
redis-primary:6379
```

While a Spring test running **outside the Docker network** needs host/mapped ports.

A setup that appears to work when querying Sentinel can still fail when the client receives a primary/replica address it cannot reach. Configure network aliases, announce/port settings, and client routing to fit the test environment.

You cannot solve this solely by adding `.withExposedPorts(6379)` to one container; consider the whole network/topology.

## 23. When Production Uses Redis Cluster

Redis Cluster distributes keys across **16,384 hash slots**. A default standalone Redis container cannot trigger real Redis Cluster errors such as:

```text
CROSSSLOT Keys in request don't hash to the same slot
MOVED ...
ASK ...
```

A proper Cluster suite typically requires:

- Multiple Redis primary containers.
- Replicas when testing failover.
- Cluster mode enabled, node identities, and cluster bus/network connectivity.
- Complete slot allocation.
- Spring Data Redis client using `RedisClusterConfiguration`/Boot cluster properties.
- Cluster-advertised endpoints reachable from the test JVM.

Important tests:

| Test | Purpose |
|---|---|
| `SET`/`GET` on keys in different slots | Client routes correctly |
| `MGET` with keys sharing a hash tag | Valid same-slot multi-key operation |
| `MGET` with cross-slot keys | Verifies limits or driver-specific fan-out behavior |
| Lua script with two keys in different slots | Verifies `CROSSSLOT`/key slot constraints |
| Multi-slot pipelining | Client/driver behavior and results |
| Resharding under active requests | `MOVED`, `ASK`, topology refresh |
| Primary failover | Reconnect, redirects, unknown outcomes |
| Spring Cache clear | Scope of cache clearing across multiple nodes |

**Do not use a fake single-node “cluster mode” to conclude the application works on a multi-shard Cluster.** A single node will not surface cross-slot errors in production-like flows.

### 23.1. Key Serializers Affect Hash Slots

Redis computes the hash slot from the actual key bytes. If `StringRedisSerializer` and a binary serializer differ, the physical key's slot can also differ.

When using hash tags:

```text
cart:{customer-42}:items
cart:{customer-42}:total
```

ensure both keys are serialized in a way that preserves the intended tag. Tests should run through the **real production template** and use `CLUSTER KEYSLOT` on the actual stored keys when investigating.

## 24. Testing Network Failures with Toxiproxy

A healthy Redis container does not reveal how the application behaves when Redis slows down or connections drop.

Testcontainers integrates with **Toxiproxy** in compatible versions/modules, allowing a proxy between the JVM and Redis:

```text
Spring Data Redis
       |
       v
Toxiproxy endpoint
       |
       v
Redis container
```

You can simulate:

- Connection cuts.
- Increased network latency.
- Bandwidth throttling.
- Connection resets.
- Transient communication blackouts.

### 24.1. Questions to Test

1. When `GET` times out, how does the service fall back?
2. If `SET` executed on Redis but the response was lost, how does code handle the unknown outcome?
3. Does `INCR` get retried and run twice?
4. Do Lettuce/Jedis reconnect once connectivity is restored?
5. Does `RedisMessageListenerContainer` resume receiving new Pub/Sub events?
6. Do Reactor `Mono` pipelines emit `onError` and `timeout` per policy?
7. Does the API mistakenly return 404 when a Redis error is misinterpreted as a cache miss?

### 24.2. Why Not Blindly Retry `INCR`, `LPUSH`, `XADD *`?

Example:

```text
Client sends INCR
       |
       v
Redis increments counter
       |
       X response lost
       |
Client times out
       |
Client retries INCR
       |
       v
Counter may increment a second time
```

Resilience tests should verify **idempotency and final Redis state**, not merely assert the final HTTP response returned `200`.

Toxiproxy only simulates certain network faults; it does not replace Sentinel/Cluster promotion or power-loss/durability tests.

## 25. Testing Memory Eviction and `noeviction`

Production may run:

```conf
maxmemory 256mb
maxmemory-policy noeviction
```

or:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

These two policies behave very differently when Redis nears capacity:

- `noeviction`: commands that increase memory usage may be rejected.
- `allkeys-lru`: Redis may evict keys to free memory per policy.

Cache integration tests should check:

- Keys with TTL still honor expiration.
- Under memory pressure, code tolerates cache misses.
- Redis eviction is not treated as a missing database record.
- Under `noeviction`, Spring Data Redis surfaces appropriate errors and the service handles them per policy.
- State that must not be lost is not placed on the same instance as evictable caches without risk isolation.

### 25.1. Do Not Equate `maxmemory` with Docker Memory Limit

`maxmemory` is Redis's internal data-memory threshold; the container also uses RSS, buffers, COW pages during forks, and filesystem cache.

To test OOM-kills or RDB/AOF rewrite memory peaks, use a dedicated stress suite with resource monitoring rather than just setting a tiny `maxmemory` in an ordinary test method.

## 26. Testing RDB/AOF and Durability

A `SET` followed by `GET` within the same Redis process **does not prove** data is persisted durably to disk.

If production enables AOF:

```conf
appendonly yes
appendfsync everysec
```

regular tests can verify Redis starts with AOF enabled, whereas **crash/restore testing** requires a dedicated approach:

1. Use a container with intentionally configured persistent storage.
2. Write keys with explicit IDs/sequences.
3. Record an ACK log outside Redis.
4. Trigger a controlled fault in the lab.
5. Restart Redis from the same persistent data.
6. Reconcile surviving keys/values against the ACK log.
7. Measure how many acknowledged writes were lost.

### 26.1. Pitfall: `stop()` Then `start()` on a `GenericContainer`

If Testcontainers creates a new container with an ephemeral filesystem, persistence files inside the old container **do not automatically carry over to the new container**. Therefore:

```text
container.stop()
container.start()
assert data still exists
```

is not by default a valid durability test.

Design explicitly:

- Reuse the same filesystem/container where appropriate and supported by the API.
- Or mount a Docker volume/bind mount holding persistence files.
- Or export/import persistence files properly.
- Ensure consistent file permissions, Redis 7+ AOF manifest structure, and `redis.conf` settings.

Do not boot the same Redis image against an empty filesystem and conclude Redis lost data due to an AOF bug.

### 26.2. Process Crash Differs from Power Loss

Killing the Redis process inside a container and crashing the OS/storage have different durability characteristics. Data in the OS page cache can survive a Redis process stop, while power loss can lose un-fsynced writes.

Thus, Testcontainers tests can validate many useful failure modes, **without proving absolute RPO** for production power outages.

## 27. Real-Time Execution, Concurrency, and Determinism

A real Redis Server involves scheduling, networking, expiration, and multiple clients. Tests must not assume every operation finishes on an exact millisecond schedule.

### 27.1. Avoid `Thread.sleep(100)` to “Wait for Redis”

A very short fixed sleep might pass on a laptop and fail on a CPU-contended CI runner.

Prefer:

- Polling until a real condition holds, with a timeout.
- Awaitility when the dependency is available.
- Latches/readiness signals for listeners.
- Waiting on Redis `INFO` or meaningful status.
- Setting deadlines generous enough for test infrastructure, never infinite.

### 27.2. Test Concurrency When Code Depends on Atomicity

For example, a counter-incrementing service:

```java
redis.opsForValue().increment("it:counter");
```

can be tested by multiple concurrent threads, verifying the final value equals the total number of successful increments.

Conversely, a `GET` → increment in Java → `SET` pattern causes lost updates under parallel clients. Testing against real Redis with a near-simultaneous start barrier exposes this bug.

However, concurrency tests must not rely on non-deterministic Java thread scheduling to assert a strict completion order.

## 28. Optimizing Test Speed Without Sacrificing Reliability

Testcontainers needs to pull images, start Redis, and boot Spring contexts. You can save time by:

- Sharing a static container across a test class/suite with a clear lifecycle.
- Pre-caching images in CI caches or registry mirrors.
- Avoiding `@DirtiesContext` unless a context reset is genuinely needed.
- Separating unit tests (fast) and integration tests (real Redis) via Gradle/JUnit tags.
- Using isolated namespaces instead of restarting Redis per method.
- Keeping AOF, TLS, and Cluster disabled in suites that do not test those features if speed is the priority.
- Running topology/failover suites in a separate pipeline that is still mandatory before releases when needed.

**Do not optimize by swapping real Redis for a fake inside the exact suite built to catch Redis Server discrepancies.** Unit tests can use mocks; integration tests should keep the real server.

### 28.1. Do Not Overuse Container Reuse

Testcontainers supports reuse mechanisms in properly configured environments, but reuse can retain leftover data/config from prior runs and hurt reproducibility.

In CI, prefer containers created and cleaned up per test lifecycle unless the team maintains strict data/lifecycle isolation rules.

## 29. Designing a CI Pipeline for Redis Integration Tests

A practical pipeline:

```text
Build / Compile
       |
       v
Unit tests (mocks)
       |
       v
Integration tests:
  - Standalone Redis Testcontainers
  - Production-compatible Redis image
  - Spring Boot context + RedisTemplate
       |
       v
Specialized tests:
  - auth/ACL/TLS
  - Redis Streams/PubSub
  - Cluster/Sentinel
  - failure injection
       |
       v
Performance / durability tests on staging
```

Not every tier has to run on every commit. For example:

| Frequency | Test Suite |
|---|---|
| Every pull request | Unit + core standalone Redis integration |
| When changing Redis/serializer config | Cache, TTL, key schema, ACL, scripts |
| When changing client/Boot/Redis version | Full Redis compatibility suite |
| Before release | Sentinel/Cluster, reconnect, failure injection if used |
| Periodically on staging | Load, memory pressure, persistence, RTO/RPO |

A common test command:

```bash
./gradlew test
```

If the project separates `integrationTest` into its own Gradle source set/task, run that task per project workflow. This section only describes pipeline organization; **there is no need to run Gradle to study this guide**.

### 29.1. When the Docker Daemon Is Unavailable

Infrastructure failure messages should clearly state Testcontainers cannot reach the container runtime. Do not switch to:

```yaml
spring:
  data:
    redis:
      host: some-shared-redis
```

just to “make tests green,” as it can connect to uncontrolled systems and mutate shared data.

Do not enable `disabledWithoutDocker = true` by default on integration tests that serve as **critical release gates** if it causes them to be silently skipped. If skipping is desired on developer machines lacking Docker, enforce a separate CI policy ensuring required suites actually run and report results.

## 30. Common Errors and Troubleshooting Table

| Symptom | Common Cause | Investigation |
|---|---|---|
| `Connection refused` | Using host port 6379 instead of mapped port | `getHost()`/`getMappedPort()` |
| Test hangs during context startup | Container not ready or Redis loading AOF | Wait strategy, logs, timeouts |
| Test accidentally connects to another Redis | Custom `RedisConnectionFactory` bean ignores property overrides | Bean wiring, endpoint, namespace |
| `NOAUTH Authentication required` | Redis requires password, client unconfigured | Test password/username/ACL |
| `WRONGPASS` | Wrong credentials or disabled user | Check test-only ACL |
| `WRONGTYPE` | Wrote String, read Hash (or vice versa) | Key schema and serializers |
| Deserialization error | Test serializer differs from production | `RedisSerializationContext`, DTO schema |
| `@Cacheable` not caching | Caching disabled, self-invocation, `unless`, wrong cache manager | Spring proxy/cache config |
| Flaky TTL test | Overly tight timing assertion | Polling with deadline |
| Redis OOM during test | Limit too low, large fixtures, fork/COW | `INFO memory` + cgroup |
| `CROSSSLOT` only in production | CI only runs standalone | Add Cluster suite |
| `MOVED`/`ASK` fails tests | Client not Cluster-aware or stale topology | Driver config/topology |
| Listener misses messages | Published before subscription completed | Readiness/latch |
| Streams test sees no pending entries | Auto-ACK or wrong group/offset | `XREADGROUP`, `XPENDING`, ACK policy |
| Data vanishes after restart | New container lacks persistent volume | Test storage lifecycle |
| Passes locally, fails in CI | Host/mapped port networking, CPU contention, image availability | Logs, Docker environment, timeouts |
| Flaky during parallel tests | Key collisions or shared `FLUSHDB` | Dedicated namespaces, cleanup |
| Redis cache wiped after another test | Mismatched static container lifecycle and context caching | Separate context/define lifecycle |

Do not treat every failure by bumping timeouts. Serializer mismatches, wrong key types, and cross-slot errors **never fix themselves** by waiting longer.

## 31. Full Scenario: Testing a Cache-Aside Service with Real Redis

An application typically follows this flow:

```text
Controller
    |
    v
ProductService
    |
    +-- Redis GET key
    |      |
    |      +-- hit  -> return DTO
    |      |
    |      +-- miss -> Repository
    |                    |
    |                    +-- found     -> Redis SET with TTL
    |                    +-- not found -> per negative-cache policy
    |
    v
Response
```

The integration test can use Redis Testcontainers and a test/fake data source that counts invocations. The goal is not mocking Redis, but **keeping a real Redis Server** while controlling the source data.

Example test plan:

**Test 1 — cache miss then hit**

1. Delete the test product's Redis key.
2. Configure the test repository to return a deterministic DTO.
3. Call the service the first time.
4. Verify the repository was called once.
5. Call the service a second time.
6. Verify the repository was not called again.
7. Inspect Redis and verify the entry has the expected TTL/format.

**Test 2 — update and eviction**

1. Populate the cache with old data.
2. Execute an update through the write service.
3. Check that the Redis key is deleted or updated after transaction commit per policy.
4. Read again through the service.
5. Verify the updated data is returned.

**Test 3 — negative cache**

1. Repository returns not found.
2. Service stores a negative marker if configured to allow it.
3. Subsequent requests do not call the repository.
4. After TTL or invalidation, the repository is called again.
5. Do not confuse a Redis error with a not-found result.

**Test 4 — Redis unavailable**

1. Use a proxy to cut the connection.
2. Call the service.
3. Observe the defined fallback or exception.
4. Restore connectivity.
5. Verify the application recovers and does not serve corrupt data.

**Test 5 — production-topology coverage**

If production uses Cluster, rerun multi-key/script flows on a Cluster topology. If using Sentinel, test primary switchover while the service continues handling requests.

### 31.1. Why Test Both Redis State and Business Output?

An assertion like:

```java
assertEquals(expected, service.findById(id));
```

only checks the returned value. The service might have bypassed the cache and queried the database every time.

Conversely, seeing a Redis key created does not prove the service reads from the cache properly or invalidates on updates.

A solid integration test combines **at least one end-to-end observation** with enough direct checks to confirm the intended caching mechanism actually took effect.

## 32. Approaches by Level of Production Parity

No single Testcontainers setup fits every project. You can organize three clear profiles:

### Profile A — Fast, Closely Tracking Redis Server APIs

- Real single-container Redis.
- Image version matching production.
- Real Spring Boot context.
- Same serializers and `RedisCacheManager`.
- Tests `GET`/`SET`, TTL, Hash, Lua, caching, and basic Streams.
- Runs on every pull request.

### Profile B — Production-Like Redis Configuration

- Enable AOF/RDB according to tested policies.
- Use test-only ACL/password/TLS equivalents.
- Match `maxmemory` and eviction policies.
- Test persistence behavior, negative caching, and error responses.
- Runs on config changes or before releases.

### Profile C — Topology and Resilience

- Multi-container Sentinel/Cluster.
- Test server discovery, redirects, resharding, failover.
- Fault injection with a proxy/network tool.
- Measure reconnect, errors, idempotency, and observed RTO/RPO.
- Runs in a pipeline with adequate resources and isolation.

Splitting profiles avoids making the fast suite slow and complicated by simulating all of production everywhere, while ensuring failover/Cluster behaviors still receive proper coverage.

## 33. Checklist Before Considering Tests Production-Compatible

### Redis Server

- [ ] Image matches the relevant Redis major/minor version and distribution.
- [ ] Image tag/digest is controlled, not using `latest` arbitrarily.
- [ ] Required modules are present with matching command capabilities.
- [ ] Essential Redis configuration is applied and verified.
- [ ] `maxmemory`, eviction, AOF/RDB, and notifications reflect test goals.

### Spring Data Redis

- [ ] `RedisConnectionFactory` points to the container, not shared/production Redis.
- [ ] Tests use the application's actual templates/serializers/cache managers.
- [ ] Host and port come from Testcontainers, never hardcoded.
- [ ] Cache miss, TTL, null, serializer, and wrong-type behaviors are tested.
- [ ] Lua/Streams/PubSub are tested if used by the application.
- [ ] Reactive operations are subscribed to and verified with Reactor test tools when needed.

### Test Isolation

- [ ] Each test has its own key namespace or proper cleanup.
- [ ] No `FLUSHDB` on shared Redis instances.
- [ ] No contexts left pointing to stopped containers.
- [ ] Parallel tests do not trample each other's keys or consumer groups.
- [ ] No dependence on leftover data from previous runs.
- [ ] CI fails loudly if Docker/images are unavailable.

### Production-Specific Behavior

- [ ] Sentinel/Cluster is tested separately if production uses it.
- [ ] TLS/ACL is tested if security is mandatory.
- [ ] Failover/reconnect and error policies are tested when HA is required.
- [ ] Memory/eviction and persistence are tested within appropriate scope.
- [ ] Load/resilience tests are separated from functional tests when needed.
- [ ] Assumptions about durability and retries are explicitly documented.

## 34. Common Misconceptions

**“`@SpringBootTest` automatically means an integration test with real Redis.”** Only true when the Spring context actually talks to a test-controlled Redis Server. If the Redis template is mocked or the connection factory points elsewhere, the result proves nothing about Redis.

**“Having a Redis Docker container equals production parity.”** False if version, modules, topology, ACL, persistence, or memory policy differ.

**“Using `redis:latest` keeps tests fresh and safe.”** It breaks reproducibility; versions and behavior can change unintentionally.

**“Setting `spring.data.redis.port=6379` always works.”** Wrong when Testcontainers maps dynamic ports or uses a remote Docker host.

**“`@DynamicPropertySource` overrides every Redis connection factory.”** Wrong if the application creates a hardcoded bean ignoring those properties.

**“A static container gives every test method a clean Redis DB.”** False. Data persists across the entire container lifecycle.

**“`FLUSHDB` in `@BeforeEach` is always safe.”** Only when the DB/container belongs strictly to an isolated test with no parallel siblings sharing it.

**“Mock Redis tests Lua and TTL accurately.”** It cannot replace a real Redis Server.

**“`StepVerifier.withVirtualTime` makes Redis TTL expire faster.”** False. Redis Server's clock is independent of Reactor's virtual clock.

**“One standalone Redis Testcontainer is enough to catch `CROSSSLOT`.”** False. A real Redis Cluster is required.

**“`@ServiceConnection` simulates Sentinel/Cluster automatically.”** No; it wires connection details in supported cases, without building complex topologies.

**“A passing `SET` then `GET` proves data is durable on disk.”** False. Crash/restore tests and proper persistence storage are required.

**“Stopping and starting a container is a full persistence test.”** False if ephemeral filesystems are discarded or faults are modeled poorly.

**“Increasing timeouts fixes every flaky test.”** False; you must fix readiness, key collisions, resource pressure, networking, and configuration.

**“Fast tests matter more than anything else.”** A fast test using fake Redis or the wrong version can miss the exact bug it was meant to catch. Tier your suites for both speed and confidence.

## 35. Conclusion

**Testcontainers with a real Redis Server** is an effective way to test Spring Data Redis much closer to production runtime than mocked unit tests. A single Redis `GenericContainer` paired with `@SpringBootTest`, JUnit 5, and `@DynamicPropertySource` suffices to verify many vital features: serializers, TTL, Redis data types, Lua, Spring Cache, and read/write flows.

However, the value of integration tests depends on **accurately simulating the production factors that affect the behavior under test**:

1. **Use a Redis image with an explicit version and distribution**, matching production commands and modules.
2. **Pass dynamic host/port into Spring properly**, ensuring templates actually connect to Testcontainers Redis.
3. **Align configurations affecting behavior**, such as persistence, ACL, TTL notifications, `maxmemory`, and eviction.
4. **Test real Redis logic**, including expiration, serializers, cache managers, Lua, Streams, and Pub/Sub—not just `PING`.
5. **Isolate data and manage lifecycles**, avoiding order-dependent tests or contexts holding stale connections.
6. **Use matching topologies when needed**: Sentinel for failover, Cluster for hash slots/routing, Toxiproxy for network faults.
7. **Keep performance/durability/chaos tests separate** with appropriate assertions, resources, and observability.

A well-designed Testcontainers suite does not pretend everything matches production just because Redis runs in Docker. It states clearly **which properties are verified**, **which gaps remain**, and provides reliable evidence that Spring Data Redis will operate properly in the target environment.
