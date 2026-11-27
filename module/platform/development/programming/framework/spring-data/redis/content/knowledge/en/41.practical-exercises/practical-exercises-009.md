# Writing Integration Tests and Observing Failure Behavior

## 1. Objectives of This Exercise

A Spring Boot application may connect to Redis and read/write successfully in development, yet still fail in production:

- Redis stops responding temporarily or the connection drops.
- A key exists, yet its value cannot be decoded by the current serializer.
- A key expires right as the application reads it.
- A write command executed on Redis, yet the response was lost, causing the client to retry and duplicate side effects.
- A database fallback runs when Redis fails, overloading the database.
- Redis recovers, yet the client fails to reconnect or health checks remain unhealthy.
- Metrics count Redis timeouts as cache misses, skewing observability.
- Both the application and driver log the same exception across multiple layers, creating a log storm.

If you only test:

```java
assertEquals("value", redis.opsForValue().get("key"));
```

you only prove an operation works under happy conditions. **Valuable integration tests must verify the application behaves properly while Redis is healthy, while Redis is failing, and after Redis recovers.**

This lesson belongs to the **Practical Exercises** section of **Spring Data Redis**. Upon completion, you will be able to:

1. Spin up real Redis with Testcontainers to test `RedisTemplate` and serializers.
2. Write tests for cache hits, cache misses, TTLs, and undeserializable payloads.
3. Inject controlled connection and timeout faults.
4. Distinguish an empty `GET` from infrastructure failures.
5. Verify fallbacks, retries, and idempotency using concrete scenarios.
6. Emit metrics, logs, and correlation IDs, and measure recovery time.
7. Design advanced tests for Redis Streams, Pub/Sub, Sentinel, and Cluster.
8. Integrate tests into CI without accidentally wiping other environments' data.

All connection-breaking, pausing, restarting, or failover actions in this lesson run strictly against an **isolated test Redis instance**. Never inject faults into production Redis for exercises.

## 2. Understanding the Difference Between Unit Tests and Integration Tests

### 2.1. Unit Tests

A unit test can replace `RedisTemplate` with a mock:

```java
when(valueOperations.get("cache:product:42"))
        .thenReturn("READY");
```

It works well for checking:

- Key selection logic.
- Fallback rules.
- Mapping errors to responses.
- Conditional retry logic.
- Whether code invokes the right dependency.

However, mocks generally cannot prove:

- That the serializer actually encodes and decodes bytes properly.
- That TTLs are handled by Redis.
- That Spring Boot constructs `RedisConnectionFactory` properly.
- That Redis server returns `WRONGTYPE`.
- How connection timeouts and reconnects behave.
- That Lua scripts are genuinely atomic.
- That Redis Cluster routes slots properly.

### 2.2. Integration Tests

Integration tests run against **real Redis** using most of the same Spring Data Redis stack used in production:

```text
JUnit 5
   |
   v
Spring Boot ApplicationContext
   |
   v
RedisTemplate / RedisCacheManager
   |
   v
LettuceConnectionFactory
   |
   v
Real Redis container
```

Clarify scope: a standalone Redis container thoroughly tests commands, serializers, and TTLs, **but does not replace** topology tests for Redis Sentinel/Cluster or managed Redis service behavior.

### 2.3. Fault-Injection Integration Tests

When inspecting failure behavior:

```text
Test harness
    |
    +--> Send request through service
    |
    +--> Pause Redis / block network / trigger failover
    |
    +--> Observe exceptions, metrics, logs, retries
    |
    +--> Restore Redis
    |
    +--> Wait until operations genuinely work again
```

The goal is not making every request succeed during an outage. The goal is verifying the **published system contract**: errors are classified accurately, fallbacks behave as designed, recovery finishes within bounds, and side effects are neither lost nor duplicated.

## 3. Lab Architecture

We will build a small product caching service:

```text
ProductController (optional)
          |
          v
ProductCacheGateway
          |
          +--> RedisTemplate<String, ProductSnapshot>
          |             |
          |             v
          |         Real Redis
          |
          +--> Micrometer counters/timers
          |
          +--> CacheDependencyException
                        |
                        +--> original cause preserved
```

Conventions:

```text
Key prefix: demo:products:v1:
Payload:    JSON of ProductSnapshot
TTL:        caller-supplied
Metrics:    demo.redis.cache.lookup
Outcomes:   hit, miss, error
```

Sample object:

```json
{
  "id": "P-42",
  "name": "Notebook",
  "revision": 5
}
```

Data in this lesson is synthetic and contains no real user information.

### 3.1. Acceptance Criteria

| Scenario | Expected Outcome |
|---|---|
| Key does not exist | `Optional.empty()`, increment `miss` metric |
| Valid key | Return exact object, increment `hit` metric |
| TTL expired | Read returns miss; not an exception |
| Non-JSON bytes | Preserve deserialization error in cause, increment `error` metric |
| Redis unresponsive | Throw error with cause; do not turn into miss |
| Redis recovers | Reads/writes succeed again using the same app instance |
| Fallback permitted | Read authoritative source, record fallback metric |
| Non-idempotent write times out | Do not blindly retry |
| Repeated tests | Independent of test ordering or keys from other tests |

## 4. Environment Setup

Recommended for the examples:

- JDK 17 or higher.
- Spring Boot 3.x and corresponding Spring Data Redis.
- JUnit Jupiter.
- Testcontainers.
- Docker or a Testcontainers-supported container runtime.
- Redis image pinned by tag/version for testing.
- Micrometer via Spring Boot Actuator.
- Awaitility for polling conditions instead of fixed `Thread.sleep`.

Sample project structure:

```text
src/
  main/
    java/com/example/redislab/
      RedisLabApplication.java
      ProductSnapshot.java
      ProductRedisConfiguration.java
      CacheDependencyException.java
      ProductCacheGateway.java
  test/
    java/com/example/redislab/
      ProductCacheIntegrationTest.java
      RedisOutageIntegrationTest.java
```

Code snippets target Spring Boot 3.x. In real projects, use your pinned dependency versions rather than mixing Spring Data Redis and Lettuce versions outside the BOM.

### 4.1. Maven Dependencies

When using Maven with `spring-boot-starter-parent` or a configured Spring Boot BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
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
```

If the project does not use a BOM managing these dependencies, pin compatible versions per your build policy. Do not copy stale versions from random blog posts ignoring your project's compatibility matrix.

### 4.2. Spring Boot Application

```java
package com.example.redislab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisLabApplication.class, args);
    }
}
```

You can configure integration test timeouts via `@DynamicPropertySource` or a test profile file. **Never point integration tests at production Redis.**

## 5. Defining the Model and Serializer

### 5.1. ProductSnapshot

```java
package com.example.redislab;

public record ProductSnapshot(
        String id,
        String name,
        long revision
) {
}
```

A record keeps the example concise. We use JSON so tests can deliberately write malformed payloads and verify deserialization errors.

### 5.2. RedisTemplate with an Explicit Serializer

```java
package com.example.redislab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductRedisConfiguration {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        ProductSnapshot.class
                )
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

In this example:

- Keys are encoded as UTF-8 Strings.
- Values are encoded as JSON matching `ProductSnapshot`.
- Tests can use `StringRedisTemplate` to write non-JSON bytes to **the exact same physical key**.
- Both templates share the same `RedisConnectionFactory`, so tests still exercise Lettuce and real Redis.

Never use Java native deserialization on untrusted payloads. If the real application uses a different serializer, tests must use the exact production serializer.

### 5.3. Why Test the Serializer?

If an application switches from JDK serialization to JSON, `GET` in Redis CLI still finds the key, yet the new application fails to decode the value.

```text
GET key -> raw bytes exist
                  |
                  v
       JSON deserializer
                  |
          +-------+-------+
          |               |
        Valid          Invalid
          |               |
        Object    SerializationException
```

Never conclude "Redis key does not exist" simply because the serializer failed to construct an object.

## 6. Safe Exception Preserving the Original Cause

We want the service to wrap Redis errors into an application exception with a stable message while keeping the original cause.

```java
package com.example.redislab;

public final class CacheDependencyException
        extends RuntimeException {

    private final String safeOperation;

    public CacheDependencyException(
            String safeOperation,
            Throwable cause) {

        super("Product cache dependency operation failed", cause);
        this.safeOperation = safeOperation;
    }

    public String safeOperation() {
        return safeOperation;
    }
}
```

`safeOperation` receives a fixed string literal in code like `product_cache_read`, never taken directly from HTTP requests or raw Redis keys.

**Wrong:**

```java
throw new RuntimeException(ex.getMessage());
```

Because the original cause is lost and the message may expose sensitive data.

**Better:**

```java
throw new CacheDependencyException(
        "product_cache_read",
        ex
);
```

Then:

```java
wrapped.getCause() == originalException
```

The cause chain distinguishes connection, timeout, and serialization errors even when the public API returns a generic error code.

## 7. ProductCacheGateway: The Code Under Test

The gateway is responsible for:

- Constructing keys from validated IDs.
- Reading the cache.
- Writing with TTLs.
- Distinguishing hits, misses, and errors.
- Recording metrics with bounded label cardinality.
- Propagating errors with original causes.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.Optional;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheGateway {

    private static final String PREFIX = "demo:products:v1:";

    private final RedisTemplate<String, ProductSnapshot> redis;
    private final MeterRegistry metrics;

    public ProductCacheGateway(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis,
            MeterRegistry metrics) {

        this.redis = redis;
        this.metrics = metrics;
    }

    public static String keyFor(String id) {
        if (id == null ||
                !id.matches("[A-Za-z0-9._-]{1,100}")) {
            throw new IllegalArgumentException(
                    "Product ID has invalid format"
            );
        }

        return PREFIX + id;
    }

    public Optional<ProductSnapshot> find(String productId) {
        String key = keyFor(productId);

        Timer.Sample sample = Timer.start(metrics);

        try {
            ProductSnapshot result =
                    redis.opsForValue().get(key);

            if (result == null) {
                count("read", "miss");
                return Optional.empty();
            }

            count("read", "hit");
            return Optional.of(result);

        } catch (DataAccessException | SerializationException ex) {
            count("read", "error");
            throw new CacheDependencyException(
                    "product_cache_read",
                    ex
            );

        } finally {
            sample.stop(metrics.timer(
                    "demo.redis.cache.read.duration",
                    "cache", "products"
            ));
        }
    }

    public void put(
            ProductSnapshot product,
            Duration ttl) {

        if (product == null) {
            throw new IllegalArgumentException(
                    "Product must not be null"
            );
        }

        if (ttl == null || ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException(
                    "TTL must be positive"
            );
        }

        String key = keyFor(product.id());

        try {
            redis.opsForValue().set(key, product, ttl);
            count("write", "success");

        } catch (DataAccessException | SerializationException ex) {
            count("write", "error");

            throw new CacheDependencyException(
                    "product_cache_write",
                    ex
            );
        }
    }

    private void count(String operation, String outcome) {
        metrics.counter(
                "demo.redis.cache.lookup",
                "cache", "products",
                "operation", operation,
                "outcome", outcome
        ).increment();
    }
}
```

### 7.1. Key Takeaways

1. `find()` returns `Optional.empty()` **only when a valid Redis GET returns null**.
2. Redis/serializer errors are wrapped with their original cause preserved.
3. Metrics carry `cache`, `operation`, and `outcome` from a **fixed value set**, never product IDs or keys.
4. `Timer.Sample` measures both successful and failed calls.
5. `put()` validates TTL before calling Redis.
6. `put()` does not auto-retry writes on timeout.
7. Never log cached values or raw exception messages.

Redis calls can throw additional runtime exceptions depending on serializers, drivers, and usage. In real projects, classify exceptions for your specific stack; never write `catch (Exception)` and turn everything into a cache miss.

### 7.2. Why Not Use One Generic Counter for Everything?

If you only measure:

```text
redis_operation_total
```

you cannot distinguish:

```text
Read hit
Read miss
Read error
Write success
Write error
```

When Redis goes down, the system generates many `error` events, while `miss` preserves its exact meaning of absent keys.

### 7.3. Metric Names and Naming Conventions

In Java, Micrometer names are:

```text
demo.redis.cache.lookup
demo.redis.cache.read.duration
```

A Prometheus registry may export transformed names such as:

```text
demo_redis_cache_lookup_total
demo_redis_cache_read_duration_seconds
```

Exact names depend on the registry and naming conventions. Inspect your application's metrics endpoint rather than assuming every environment exports identical names.

## 8. Starting a Redis Container for Integration Tests

Use `@Testcontainers` and `@Container` so JUnit manages a dedicated Redis lifecycle for tests.

```java
package com.example.redislab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.data.redis.core.StringRedisTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class RedisConnectionSmokeTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void configureRedis(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add(
                "spring.data.redis.timeout",
                () -> "700ms"
        );
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    StringRedisTemplate rawRedis;

    @Test
    void setAndGetThroughSpring() {
        String key = "it:smoke:product-42";

        try {
            rawRedis.opsForValue().set(key, "READY");

            assertEquals(
                    "READY",
                    rawRedis.opsForValue().get(key)
            );
        } finally {
            rawRedis.delete(key);
        }
    }
}
```

Here `REDIS.getMappedPort(6379)` is used because Testcontainers assigns a random host port; tests never hardcode `localhost:6379`.

### 8.1. Why Choose Real Redis?

`SET`/`GET` exercises:

```text
Spring Boot configuration
    -> RedisConnectionFactory
    -> Lettuce
    -> Redis server
    -> Spring serializers
```

If host/port config is wrong, serializers are misconfigured, or Redis fails to start, the test catches it.

### 8.2. Why Not Use Production Redis?

Tests create keys, change TTLs, inject malformed payloads, and sever connections. Those actions belong solely in isolated test environments.

Using a Redis container for core tests ensures:

- Results do not depend on other people's data.
- No need to call `FLUSHALL`.
- All test data can be discarded cleanly afterward.
- The same stack runs locally and in CI.

### 8.3. Test Profiles

You can create:

```yaml
# application-it.yml
spring:
  data:
    redis:
      timeout: 700ms
      connect-timeout: 700ms
```

If `@DynamicPropertySource` already sets timeouts, this file is optional. Still, in large projects a dedicated `it` profile helps disable features that must not run in tests, such as background jobs or listeners.

## 9. Testing Cache Hits and Cache Misses

Create a test class using the Redis container, gateway, and a `MeterRegistry`.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class ProductCacheIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add("spring.data.redis.timeout", () -> "700ms");
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    ProductCacheGateway cache;

    @Autowired
    MeterRegistry metrics;

    @Test
    void distinguishesHitFromMiss() {
        String id = "p-" + UUID.randomUUID();

        double missBefore = count("read", "miss");
        double hitBefore = count("read", "hit");

        assertTrue(cache.find(id).isEmpty());

        ProductSnapshot product =
                new ProductSnapshot(id, "Notebook", 7);

        cache.put(product, Duration.ofMinutes(2));

        assertEquals(
                product,
                cache.find(id).orElseThrow()
        );

        assertEquals(
                missBefore + 1,
                count("read", "miss"),
                0.0001
        );

        assertEquals(
                hitBefore + 1,
                count("read", "hit"),
                0.0001
        );
    }

    private double count(String operation, String outcome) {
        return metrics.counter(
                "demo.redis.cache.lookup",
                "cache", "products",
                "operation", operation,
                "outcome", outcome
        ).count();
    }
}
```

### 9.1. Why Check Metric Deltas?

Counters may already hold counts from earlier tests sharing the `ApplicationContext`. Saving `before`, executing specific actions, and comparing `after` avoids brittle assumptions.

Never assert that a total counter equals `1` if multiple tests share the registry.

### 9.2. What Is Not Yet Proven?

The test above proves the **Redis-backed gateway** distinguishes hits from misses. It does not prove cache-aside reads from the database on misses or that API endpoints return proper responses; those belong to service/controller tests above.

## 10. Testing TTL: Redis Automatically Removes Expired Keys

A test should not rely on a fixed `Thread.sleep` and assert expiration happened at an exact instant.

Example added to `ProductCacheIntegrationTest`:

```java
@Test
void expiresAfterTtl() {
    String id = "ttl-" + UUID.randomUUID();

    ProductSnapshot product =
            new ProductSnapshot(id, "Temporary", 1);

    cache.put(product, Duration.ofSeconds(1));

    assertEquals(
            product,
            cache.find(id).orElseThrow()
    );

    org.awaitility.Awaitility.await()
            .atMost(Duration.ofSeconds(8))
            .pollInterval(Duration.ofMillis(100))
            .until(() -> cache.find(id).isEmpty());
}
```

The test requires `Duration` and `UUID` imports as before. You can use a static import for `await()` if preferred.

### 10.1. Distinguishing Expiration from Connection Errors

After the TTL expires, Redis `GET` returns `null`: a valid **miss**.

If Redis unexpectedly disconnects while waiting, `cache.find(id)` throws `CacheDependencyException` and the test must fail; **never catch it and treat it as expiration**.

### 10.2. Checking TTL Right After Write

To confirm a key actually has a TTL:

```java
Long ttl = rawRedis.getExpire(
        ProductCacheGateway.keyFor(id),
        java.util.concurrent.TimeUnit.MILLISECONDS
);

assertNotNull(ttl);
assertTrue(ttl > 0);
```

Do not assert `ttl == 1000` strictly, because time elapses between `SET` and `PTTL`. Check within a reasonable range; `-1` and `-2` carry distinct meanings:

| PTTL | Meaning |
|---|---|
| Positive number | Key still has remaining lifetime |
| `-1` | Key exists without TTL |
| `-2` | Key does not exist |

Note that `TTL`/`PTTL` and key state can change while measuring; avoid asserting right on top of deadlines.

## 11. Testing Serializer Failures with Real Redis

This is an important scenario easily missed by mocks.

We configured:

```text
ProductRedisTemplate:
    String key -> ProductSnapshot JSON
```

Yet another client might write a non-JSON string under the exact same key.

### 11.1. Preparing a Malformed Payload

Inject `StringRedisTemplate` into the test class:

```java
@Autowired
org.springframework.data.redis.core.StringRedisTemplate rawRedis;
```

Add the test:

```java
@Test
void preservesSerializationFailure() {
    String id = "corrupt-" + UUID.randomUUID();
    String key = ProductCacheGateway.keyFor(id);

    rawRedis.opsForValue().set(
            key,
            "{this-is-not-valid-json",
            Duration.ofMinutes(2)
    );

    double errorsBefore = count("read", "error");

    CacheDependencyException error = assertThrows(
            CacheDependencyException.class,
            () -> cache.find(id)
    );

    assertEquals(
            "product_cache_read",
            error.safeOperation()
    );

    assertNotNull(error.getCause());

    assertInstanceOf(
            org.springframework.data.redis.serializer
                    .SerializationException.class,
            error.getCause()
    );

    assertEquals(
            errorsBefore + 1,
            count("read", "error"),
            0.0001
    );

    assertFalse(error.getMessage().contains(id));
}
```

The snippet uses JUnit 5 `assertInstanceOf`. In an actual Java file import, `org.springframework.data.redis.serializer.SerializationException` must sit on **one complete import line**; the line wrap in the `.class` argument above is solely for formatting.

You can write it more explicitly as:

```java
assertTrue(error.getCause()
        instanceof org.springframework.data.redis.serializer.SerializationException);
```

### 11.2. What Must the Test Prove?

- The Redis key **exists**.
- The JSON reader cannot decode the payload.
- The gateway does not return `Optional.empty()`.
- The gateway preserves the original deserialization exception in `getCause()`.
- The `error` metric increments.
- The wrapper message excludes the ID and raw payload.

If a test checks only HTTP 500 without inspecting the cause, it can miss a handler accidentally swallowing serializer errors and throwing a generic cause-less exception.

### 11.3. Do Not Log Raw Payloads

In production, the following risks exposing data:

```java
log.error("Bad JSON from Redis: {}", rawValue);
```

Replace with safe fields, e.g.:

```text
event=redis_read_failed
operation=product_cache_read
category=SERIALIZATION
schemaVersion=1
traceId=<generated>
```

Never use Redis keys, usernames, access tokens, or malformed JSON as metric labels.

## 12. Testing Connection Failures with Fault Injection

A stopped or unresponsive Redis container drives the application down the error path.

Two approaches:

1. **Block traffic via Toxiproxy or a network fault injector** to drop connections, add latency, or blackhole replies while Redis keeps running.
2. **Pause/unpause the Redis container** in a Docker test environment to simulate an unresponsive Redis without changing mapped ports.

Toxiproxy is especially strong for controlled latency and network-partition tests. The snippet below demonstrates using Docker pause to test Redis client timeouts and recovery.

### 12.1. Why Not Naively Stop and Restart the Same GenericContainer?

Calling:

```java
redis.stop();
redis.start();
```

may make Testcontainers launch a new container with a **new port mapping**. Yet `LettuceConnectionFactory` inside the Spring context already points to the old host/port; restarting Redis does not ensure the context updates its endpoint.

Thus, for outage and recovery tests inside the same Spring context, keep the endpoint stable or deliberately recreate the context/connection factory.

### 12.2. Create a Separate Class for Fault Injection

Do not place Redis-pause tests in the same class as hit/miss tests so parallel execution cannot interfere across suites.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.annotation.DirtiesContext;

import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
@Tag("fault-injection")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RedisOutageIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add("spring.data.redis.timeout", () -> "700ms");
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    ProductCacheGateway cache;

    @Test
    void reportsFailureAndThenRecovers() {
        String id = "outage-" + UUID.randomUUID();
        ProductSnapshot product =
                new ProductSnapshot(id, "Recovery", 1);

        cache.put(product, Duration.ofMinutes(2));
        assertEquals(product, cache.find(id).orElseThrow());

        String containerId = REDIS.getContainerId();
        var docker = DockerClientFactory.instance().client();

        try {
            docker.pauseContainerCmd(containerId).exec();

            CacheDependencyException error = assertThrows(
                    CacheDependencyException.class,
                    () -> cache.find(id)
            );

            assertNotNull(error.getCause());

        } finally {
            docker.unpauseContainerCmd(containerId).exec();
        }

        await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(250))
                .ignoreExceptions()
                .untilAsserted(() -> {
                    cache.put(product, Duration.ofMinutes(2));
                    assertEquals(
                            product,
                            cache.find(id).orElseThrow()
                    );
                });
    }
}
```

**Example limitations:**

- Docker pause/unpause requires Docker control permissions and runtime support.
- Tests need a dedicated Redis container; never pause a shared Redis service.
- The 700 ms timeout and 20-second recovery deadline are **illustrative values**, not universal SLO recommendations.
- If the client queues commands, errors can surface as timeouts or connection failures depending on timing.
- With parallel tests or Spring context caching, isolate this class from tests sharing the same Redis endpoint/context.
- `ignoreExceptions()` belongs strictly to **recovery polling**; it never means production code should swallow Redis errors.
- If Docker/runtime lacks pause support, use a fault-injection proxy instead of patching tests with arbitrary `Thread.sleep` calls.

### 12.3. Recovery Must Be Confirmed with Real Operations

Do not merely check:

```text
Container state = running
```

because Lettuce may still be reconnecting or cluster topology may not have refreshed yet.

The `await()` block retries both `put` and `find` to prove **both write and read paths through Spring Data Redis** have recovered.

### 12.4. Why Use try/finally?

If an assertion fails while Redis is paused, `finally` still unpauses Redis. This keeps the test environment from staying wedged.

For more complex topology or network disruption tests, the test harness also needs **independent cleanup**, such as tearing down the entire test environment after each run.

## 13. Measuring RTO at the Application Layer

**Recovery Time Objective (RTO)** is the target duration for service recovery under a specific definition.

A useful measurement timeline:

```text
T0: Fault begins
T1: Redis server recovers
T2: Lettuce reconnects
T3: Spring service reads/writes succeed
T4: API p99 and error rate return within SLO
```

Do not measure `T1 - T0` alone and call it application RTO. For APIs, `T4` is usually far more meaningful.

You can measure elapsed time with a monotonic clock:

```java
long startedNanos = System.nanoTime();

triggerFault();
restoreFault();
awaitRecovery();

long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNanos
        );
```

This snippet is only a measurement structure. The test harness must define concrete `triggerFault`, `restoreFault`, and `awaitRecovery` steps and record observed events. Never report an RTO figure without actually executing fault injection.

### 13.1. Setting Business Acceptance Thresholds

For instance, a staging test may require:

```text
Redis stops responding:
    -> failed requests are classified properly

After restore:
    -> within a published deadline,
       the application can read and write again

After stabilization:
    -> error rate and p99 return within thresholds
```

Thresholds must match infrastructure, driver timeouts, traffic, and business requirements. A test running on CPU-throttled CI runners should not accidentally become a production SLA benchmark.

## 14. Observing Exception Types, Causes, and Responses

A solid integration test distinguishes:

```text
Cache MISS
    -> GET returns null
    -> no exception thrown

Redis CONNECTION ERROR
    -> Lettuce fails to connect or command times out
    -> Spring Data Redis wraps/translates exception
    -> Gateway preserves cause

Serialization ERROR
    -> key holds incompatible bytes
    -> deserializer fails
    -> Gateway preserves cause

WRONGTYPE
    -> key is a String but code calls HGETALL
    -> Redis returns command error
    -> Gateway does not turn it into a miss
```

### 14.1. Preserving Cause When Wrapping Errors

Verify:

```java
CacheDependencyException error = assertThrows(
        CacheDependencyException.class,
        () -> cache.find(id)
);

assertNotNull(error.getCause());
assertEquals(
        "Product cache dependency operation failed",
        error.getMessage()
);
```

If the project uses a cause taxonomy such as `CONNECTION`, `TIMEOUT`, `SERIALIZATION`, tests can assert that category while avoiding brittle checks on English driver error text.

### 14.2. HTTP Responses Must Not Leak Redis Messages

Example controller advice:

```java
@RestControllerAdvice
public class CacheErrorAdvice {

    @ExceptionHandler(CacheDependencyException.class)
    public ResponseEntity<ApiError> handle(
            CacheDependencyException error) {

        String errorId = java.util.UUID.randomUUID().toString();

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "CACHE_DEPENDENCY_UNAVAILABLE",
                        "Service temporarily unavailable",
                        errorId
                ));
    }

    public record ApiError(
            String code,
            String message,
            String errorId
    ) {
    }
}
```

Requires imports from `org.springframework.http.*` and `org.springframework.web.bind.annotation.*`, plus `spring-boot-starter-web` if using REST. This is an extension example, not mandatory for the core gateway tests.

Use `MockMvc` or `WebTestClient` to verify responses exclude:

- Full Redis keys.
- JSON payloads.
- Connection URIs.
- Raw `ex.getMessage()`.
- Stack traces.

Not every serializer failure must return 503. HTTP status codes depend on your API contract and data sources; what matters is **not hiding errors and not leaking internal details**.

## 15. Metrics: Never Count Errors as Misses

For `ProductCacheGateway`, we want three read outcomes:

```text
hit
miss
error
```

Suppose over 5 minutes:

```text
hits   = 800
misses = 200
errors = 50
```

There are two distinct measurements:

**Cache hit ratio over valid lookup outcomes:**

\[
\frac{800}{800+200} = 80\%
\]

**Redis lookup error ratio over total attempts:**

\[
\frac{50}{800+200+50} \approx 4.76\%
\]

Never fold `errors` into `misses`, because they represent two fundamentally different events.

### 15.1. Illustrative Prometheus Queries

Suppose the counter exports as:

```text
demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="hit"
}
```

A 5-minute hit-ratio query:

```promql
sum(rate(demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="hit"
}[5m]))
/
clamp_min(
  sum(rate(demo_redis_cache_lookup_total{
    cache="products",
    operation="read",
    outcome=~"hit|miss"
  }[5m])),
  0.001
)
```

Read error ratio:

```promql
sum(rate(demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(demo_redis_cache_lookup_total{
    cache="products",
    operation="read"
  }[5m])),
  0.001
)
```

Queries depend on the exact metric names and labels exported by your exporter. Under very low traffic, 0% or 100% hit rates may reflect just a handful of requests; require a minimum sample volume for alert evaluation.

### 15.2. Timers Must Include Errors

If you only time successful `GET` calls, dashboards can show Redis looking "fast" right while timeouts are surging.

Recording the Timer in `finally` as in the sample gateway captures:

```text
successful requests latency
timeout requests latency
serializer failure latency
```

However, when analyzing latency, you may want to tag `outcome` on a separate Timer or break metrics down by layer, as long as labels remain low cardinality.

## 16. Logging: Observe Errors Without Printing Redis Values

When Redis goes down, a system can emit thousands of errors per second. If every layer calls:

```java
log.error("Redis failed", ex);
```

you suffer:

- Log storms.
- High log-storage costs.
- The same error logged multiple times.
- Stack traces potentially containing commands, keys, or URIs.
- Difficulty counting true failures.

A safer log event:

```text
event=redis_dependency_failure
operation=product_cache_read
category=CONNECTION_OR_TIMEOUT
exceptionType=RedisConnectionFailureException
requestTraceId=<generated>
retryAttempt=1
```

Never include user IDs, raw Redis keys, session tokens, payloads, or connection passwords in these fields.

### 16.1. Log Once at the Boundary

Common rule:

```text
Redis adapter -> keep exception cause, increment metric
      |
Service -> pick retry/fallback per contract
      |
API/worker boundary -> log safe event once
```

If an error is handled by a successful fallback, the fallback handler should increment a `fallback_total` metric so operations still sees the Redis outage.

### 16.2. Testing Log Redaction

In tests, use a mock payload containing a sentinel string:

```text
DO_NOT_LOG_DEMO_SECRET_123
```

Make the serializer or a dependency throw an exception whose message contains that string, then verify the logging boundary only writes category, type, and operation—never the raw payload.

Using Logback's `ListAppender` or output capture, the test should confirm the sentinel string **never appears** in official logs emitted by your code.

Note: third-party libraries or tracing auto-instrumentation may emit additional logs or spans; review their configurations separately.

## 17. Fallback: Only When an Authoritative Data Source Exists

Suppose PostgreSQL holds the real products while Redis is only a cache:

```text
API GET /products/42
          |
          v
Redis cache
     +----+-----+----------------+
     |          |                |
    HIT        MISS             ERROR
     |          |                |
     v          v                v
  Return    Read DB         Policy decision
               |                 |
               v                 +--> DB fallback if permitted
          Warm cache
```

### 17.1. Miss Differs from Connection Error

**Cache miss:**

```java
cache.find(id) -> Optional.empty()
```

**Cache error:**

```java
cache.find(id) -> throws CacheDependencyException
```

If the service catches every exception and returns `Optional.empty()`, the database can be flooded during an outage while cache-miss metrics become completely misleading.

### 17.2. Fallback Contract

A sound policy might be:

- On cache miss: read the database.
- On Redis timeout/disconnect: read the database under load limits and record a fallback metric.
- On serializer error: fail fast or handle per migration policy; never silently treat as a miss.
- When the database also fails: return an error retaining both causes.
- When Redis recovers: warm the cache at a throttled rate.

### 17.3. Unit + Integration Tests for Fallbacks

Unit-test the service with a fake repository:

```text
Given: Redis gateway throws connection failure
And: source repository returns product
When: GET product
Then: product is returned from source
And: fallback counter increments
And: no mandatory write goes to the failing Redis
```

And integration-test with a paused Redis container:

```text
Given: source of truth is ready
When: Redis times out
Then: API returns the correct fallback result
And: does not count as a cache miss
And: response latency stays within the timeout budget
```

When using a real database, combine with a PostgreSQL Testcontainer to exercise the full path. Fakes test fallback logic, **not real database transactions or connections**.

### 17.4. Protecting the Database from a Fallback Storm

A Redis outage can shift all cache traffic onto the database:

```text
Redis down
   |
   v
10,000 cache reads/s
   |
   v
10,000 DB reads/s
```

If the database only handles 2,000 requests/s, unbounded fallback triggers a second outage.

Test:

- Concurrency limits or bulkheads.
- Circuit breakers.
- Overall timeouts.
- Rate limits.
- Database load under simultaneous cache misses.
- Recovery behavior once Redis returns.

## 18. Retries: Testing Only "Retry Succeeded" Is Not Enough

A Redis command can execute on the server while the client times out before receiving the reply.

```text
Client                      Redis
    |                          |
    | INCR counter ----------> |
    |                          | counter = 11
    |       [reply lost]       |
    | timeout                  |
    |                          |
    | Retry INCR ------------> | counter = 12
```

If an event may increment the counter only once, unconditional retries introduce bugs.

### 18.1. Classifying by Idempotency

| Command | Risk on Retry After Timeout |
|---|---|
| `GET` | Generally side-effect free; bounded retries acceptable |
| `EXISTS` | Read-only; incurs extra cost |
| `SET` same value | Value-idempotent; still affects TTL/revisions |
| `INCR` | Can increment twice |
| `LPUSH` | Can insert duplicate items |
| `XADD` | Can append duplicate events |
| `ZINCRBY` | Can add score twice |
| Side-effecting Lua script | Depends on script logic |
| Transaction `EXEC` | May have committed before reply loss |

A timeout does not mean "Redis definitely did not execute the command". A retry integration test must verify the **final state**, not just that the final call succeeded.

### 18.2. Testing Idempotency with Operation IDs

An operation payload:

```json
{
  "operationId": "demo-order-42-confirm-v1",
  "orderId": "42",
  "action": "CONFIRM"
}
```

The receiving system must record `operationId` where authoritative side effects occur. If the same request is replayed, it must be recognized per the idempotency protocol.

Test:

1. Send a request with an operation ID.
2. Induce a timeout/lost response after processing may have happened.
3. Resend the same operation ID.
4. Read the authoritative state.
5. Verify no duplicate side effects occurred.
6. Verify logs and metrics recorded the retry.

A Redis `SET NX` with TTL can assist deduplication, yet critical workflows require atomicity between the idempotency record and the business side effect. Never treat a standalone `SET NX` before a database write as a cross-system transaction.

### 18.3. Do Not Retry Permanent Errors

Some errors are never resolved by retrying the same command:

```text
NOPERM
WRONGTYPE
CROSSSLOT
Incompatible serializer
Command unsupported by engine
```

Fix permissions, schemas, or Redis usage. Infinite retries only add load and mask real defects.

## 19. Testing WRONGTYPE with Real Redis

Redis supports multiple data types: String, Hash, List, Set, Sorted Set, and Stream.

Suppose a key holds a String:

```java
rawRedis.opsForValue().set(
        "it:wrongtype:42",
        "string-value"
);
```

Yet code invokes a Hash command:

```java
rawRedis.opsForHash()
        .entries("it:wrongtype:42");
```

Redis rejects it because the type mismatches.

A test:

```java
@Test
void redisRejectsWrongType() {
    String key = "it:wrongtype:" + UUID.randomUUID();

    try {
        rawRedis.opsForValue().set(key, "not-a-hash");

        assertThrows(
                org.springframework.dao.DataAccessException.class,
                () -> rawRedis.opsForHash().entries(key)
        );

    } finally {
        rawRedis.delete(key);
    }
}
```

Depending on Spring Data Redis and the driver, the exact exception may be a specific `DataAccessException` subtype. The goal is confirming **the server error actually propagates** instead of turning into an empty Hash or cache miss.

### 19.1. Why Does This Error Often Appear After Deployments?

For example:

```text
Old version: SET profile:42 "<JSON>"
New version: HGETALL profile:42
```

Without changing namespaces or migrating data, new code receives `WRONGTYPE`.

Integration tests against real Redis expose type mismatches that mocked `HashOperations` never simulate.

## 20. Testing `@Cacheable` and `@CacheEvict` When Using Spring Cache

Not every application accesses Redis through `RedisTemplate`. Many projects use the Spring Cache abstraction.

Example:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductSnapshot findById(String id) {
    return source.findById(id);
}
```

Scenarios to test:

| Scenario | Expected Outcome |
|---|---|
| First call with ID | Source invoked; cache populated if cacheable |
| Second call with same ID | Source not invoked on cache hit |
| Call with different ID | Different key; cache miss |
| TTL expires | Source invoked again |
| `@CacheEvict(key = "#id")` | Evicts only the matching entry |
| Clear entire region | Scope and permissions controlled |
| Redis down | Matches actual `CacheErrorHandler`/fallback policy |
| Incompatible serializer | Never silently treated as miss |

### 20.1. Watch Proxy/AOP Behavior

`@Cacheable` normally applies through a Spring proxy. If a method calls another method in the same class (`self-invocation`), caching does not trigger as expected.

A test calling the Java method directly on a raw instance does not verify the Spring Cache proxy. Invoke the Spring-managed bean from the context.

### 20.2. Counting Source Invocations

A test can use `@SpyBean` or your Spring Boot version's equivalent spy mechanism to count calls to the underlying repository/service:

```text
Call findById("P-42") twice
    |
    v
Expect source called once
```

Note that mock/spy annotations vary across Spring Boot versions. Use the testing API supported by your project.

### 20.3. RedisCacheManager Statistics

Spring Data Redis `RedisCacheManager` can enable statistics:

```java
RedisCacheManager.builder(connectionFactory)
        .enableStatistics()
        .build();
```

These statistics are typically **local per application instance**, not across the entire Redis server. Across multiple instances, calculate overall hit ratio from summed hits and misses, not an unweighted average of per-instance percentages.

## 21. Testing Redis Streams When Consumers Fail

If the application uses Redis Streams, integration tests must cover failure cases absent from String caches.

Example commands:

```redis
XGROUP CREATE it:orders billing 0 MKSTREAM
XADD it:orders * type CREATED orderId O-42
XREADGROUP GROUP billing consumer-a COUNT 1 STREAMS it:orders >
```

Once a consumer receives an entry without ACKing it, the entry enters the group's **Pending Entries List (PEL)**.

### 21.1. Testing Delivered-Without-ACK

1. Create a test-specific Stream and consumer group.
2. `XADD` an entry with a unique `eventId`.
3. Consumer A reads the entry without finishing processing.
4. Inspect `XPENDING` to verify the entry is pending.
5. Crash or restart Consumer A.
6. Consumer B reclaims it after a valid idle threshold.
7. Process idempotently by event ID.
8. Call `XACK` only once business side effects complete.

Example claim command:

```redis
XAUTOCLAIM it:orders billing consumer-b 60000 0-0 COUNT 10
```

`60000` ms is illustrative. Too low, and another consumer steals work still in progress; too high, and recovery lags.

### 21.2. Why Reading Only `>` Is Insufficient

```redis
XREADGROUP GROUP billing consumer-b STREAMS it:orders >
```

`>` reads entries **never delivered to the consumer group**, not pending entries stranded by a dead Consumer A.

Integration tests must verify pending reclaim logic and that reprocessing creates no duplicate side effects.

### 21.3. Never ACK Before Business Success

Wrong:

```text
Receive -> XACK -> Process -> Error
```

If processing fails after ACK, the message is no longer in the pending queue for expected retries.

Better:

```text
Receive -> Process successfully -> XACK
              |
              +--> Error -> retry/dead-letter per policy
```

Redis Streams itself does not span a transaction across Streams and databases; pair it with idempotency or an appropriate consistency protocol.

## 22. Testing Pub/Sub and Keyspace Notifications

Standard Redis Pub/Sub does not retain message history for offline subscribers.

A realistic test:

```text
Subscriber online
    |
Publish message A
    |
Subscriber receives A
    |
Disconnect subscriber
    |
Publish message B
    |
Reconnect subscriber
    |
Publish message C
    |
Subscriber receives C
```

The test must verify:

- Connected listeners receive new messages.
- Listeners reconnect or resubscribe after disruptions.
- Message B is never expected to replay after an offline gap.
- Pub/Sub is never treated as an "exactly-once" stream without a durable backing store.

### 22.1. Keyspace Expiration Notifications

Example channel:

```text
__keyevent@0__:expired
```

Enable the appropriate notification configuration on the test Redis and subscribe accordingly. However, `expired` events fire when Redis **actually deletes the expired key**, not necessarily at the exact instant TTL hits 0.

A test should never do:

```java
Thread.sleep(1000);
assertEquals(1, receivedEvents);
```

without accounting for key-cleanup timing, reconnects, or possible event loss.

### 22.2. Notifications Are Node-Local in Redis Cluster

In Cluster mode, keyspace notifications are **node-local**. A listener subscribed to one node misses events for keys hosted on other primaries.

Full topology tests must subscribe across all nodes and check behavior after resharding/failover. Never rely on keyevent Pub/Sub for mandatory zero-loss event handling.

## 23. Testing Lua Scripts and Atomicity

A classic test is owner-checked lock release.

Script:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Create lock:

```redis
SET it:lock:42 owner-A NX PX 5000
```

Test cases:

| Scenario | Expected Outcome |
|---|---|
| Owner A releases while lock still belongs to A | Deletes lock, returns 1 |
| Owner B releases while lock belongs to A | Does not delete, returns 0 |
| Lock TTL expired | Does not delete another owner's key |
| Owner A times out, B acquires new lock | A's script does not delete B's lock |
| Redis fails during script execution | Cause preserved; outcome never assumed successful |
| Script cache flushed | Client handles `NOSCRIPT` per capabilities/permissions |

### 23.1. Why Not Use Two Separate GET and DEL Commands?

If code runs:

```text
GET lock -> owner-A
    |
Lock A expires
    |
Worker B acquires lock
    |
DEL lock
```

then A deletes B's lock. A Lua script checking and deleting inside one execution boundary prevents that race.

### 23.2. Limits of This Test

Compare-and-delete only protects **lock release**. It does not stop a worker whose lease expired from writing to a database or external system. When stronger correctness is needed, test fencing tokens at the target resource.

## 24. Testing Sentinel and Redis Cluster: Never Draw Conclusions from One Container

A standalone Redis container lacks:

- Sentinel quorum.
- Primary promotion across multiple Redis nodes.
- Replica lag during failover.
- Redis Cluster's 16,384 hash slots.
- `MOVED`/`ASK` redirects during slot ownership changes.
- `CROSSSLOT` across keys actually residing in different slots.

### 24.1. Sentinel Integration Tests

At minimum, use a topology fitting the scenario:

```text
Redis primary P
    |
    +--> Replica R1
    |
    +--> Replica R2

Sentinel S1, S2, S3
```

Test:

1. Read/write through a Sentinel-configured Spring Data Redis client.
2. Identify the current primary.
3. Trigger a failover in the test environment.
4. Wait for the new primary to be elected and announced.
5. Wait for the Spring Boot client to reconnect.
6. Verify reads and writes after failover.
7. Reconcile data against the topology's RPO.

Replication is normally asynchronous: a write recently acknowledged with `OK` by the old primary may never have reached the promoted replica. Evaluate tests against the data contract rather than assuming zero write loss.

### 24.2. Redis Cluster Integration Tests

Requires multiple primaries and replicas with network addresses reachable by the client.

Test:

- Reading/writing keys across multiple hash slots.
- Multi-key commands sharing a slot via hash tags.
- Confirming errors/handling across different slots.
- Resharding a slot in an isolated environment.
- Observing `MOVED`/`ASK` and Lettuce topology refresh.
- Failing over one shard and checking unaffected shards.
- Verifying the app recovers and p99/error rates return within bounds.

Connecting successfully to one seed endpoint **does not prove** every advertised node in the Cluster is reachable.

### 24.3. Managed Redis Staging

If production uses a managed service, run integration tests in a staging environment sharing critical traits:

```text
engine version
cluster mode
TLS/auth
ACL restrictions
allowed commands
failover behavior
quotas
```

Standalone Testcontainers are essential, yet insufficient to catch provider-specific restrictions.

## 25. Fault-Injection Matrix for a Real Project

| Code | Fault | How to Test | What to Assert |
|---|---|---|---|
| F01 | Missing key | Read fresh ID | Miss, no error |
| F02 | Corrupt value | Write malformed JSON | Serialization cause preserved |
| F03 | TTL expired | Short TTL + await | Valid miss after expiration |
| F04 | WRONGTYPE | String key + HGETALL | Error propagated |
| F05 | Redis timeout | Pause/network delay | Error, not miss |
| F06 | Redis recovery | Unpause/reconnect | GET/SET work again |
| F07 | Redis unavailable + DB healthy | Test fallback | Returns source result if policy allows |
| F08 | Redis unavailable + DB down | Test both failures | Neither cause lost |
| F09 | Lost reply after INCR | Timing fault injection | No out-of-contract duplicate effects |
| F10 | Retry storm | Many concurrent requests | Bounded retries and load |
| F11 | NOPERM | Restricted ACL user | Clear failure, no infinite retry |
| F12 | Script cache miss | `NOSCRIPT` in test | Loads/falls back or reports properly |
| F13 | Stream consumer crash | Pending + reclaim | No lost work or out-of-contract duplicates |
| F14 | Pub/Sub disconnect | Publish while offline | Do not assume replay |
| F15 | Sentinel failover | Primary change | Client reconnects within RTO/RPO |
| F16 | Cluster reshard | Slot owner change | Driver follows redirects |
| F17 | Replica lag | Read replica after write | Do not assume read-your-writes |
| F18 | Cache warm storm | Invalidate many keys | DB load stays bounded |
| F19 | Engine upgrade | Staging regression | No serialization/command regressions |
| F20 | Credentials rotation | Rotate ACL/secret | Client reconnects with new credentials |

Not every project must run all scenarios on every pull request. Partition into smoke, integration, fault-injection, and nightly suites based on cost and criticality.

## 26. Avoiding Flaky Tests

### 26.1. Use Dedicated Namespaces per Test

```java
String id = "it-" + UUID.randomUUID();
```

Never share a static key like `user:42` across tests running in parallel.

### 26.2. Never Call FLUSHALL

A test should never clean up using:

```redis
FLUSHALL
```

unless it exclusively owns the entire Redis deployment. With a dedicated ephemeral container, destroying the container wipes all data cleanly.

When reusing a Redis instance, delete **only the keys created by the test** and set defensive TTLs.

### 26.3. Avoid Test Ordering Dependencies

One test must never assume a prior test created a key:

```text
Test A creates key
Test B reads key
```

If Test B runs alone or CI reorders tests, it fails.

Every test must prepare its own data and clean up its own scope.

### 26.4. Use Awaitility Instead of Fixed Sleeps

Wrong:

```java
Thread.sleep(5000);
assertTrue(redisRecovered());
```

Better:

```java
await()
        .atMost(Duration.ofSeconds(20))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            assertTrue(redisRecovered());
        });
```

`redisRecovered()` must test a real condition, not merely return `true` because the container process is running.

### 26.5. Never Force Tests to Rely on Accidental Races

For instance, a replica may catch up to the primary very quickly. A test asserting that a replica must return stale data immediately after a write will fail intermittently.

To test stale reads, induce controlled replication lag and verify consistency contracts rather than relying on natural races occurring on demand.

## 27. CI Pipelines and Docker

A sensible pipeline looks like:

```text
Compile + unit tests
        |
        v
Redis standalone integration tests
        |
        v
Managed staging contract tests (if applicable)
        |
        v
Nightly/controlled fault injection
        |
        v
Report results and metrics
```

With Maven:

```bash
mvn test
```

With Gradle:

```bash
./gradlew test
```

These are example commands for projects using those build tools, not commands required to run during this documentation step.

### 27.1. CI Requirements

- Runners have Docker/Testcontainers runtime and necessary permissions.
- Never hardcode Redis ports; use dynamically mapped ports.
- Pin Redis image versions for reproducibility.
- Set deliberate CPU/memory limits and timeouts.
- Never share destructive test topologies across concurrent jobs.
- Never print secrets or Redis payloads to CI logs.
- Clean up containers after runs.
- Separate fault-injection tests if CI lacks Docker pause/network-control capabilities.

### 27.2. Spring Context Caching Can Break When Containers Change

JUnit/Spring may cache `ApplicationContext` instances across test classes with identical configurations. If an earlier class stopped its Redis container while the cached context still holds a `LettuceConnectionFactory` pointing at the old port, subsequent classes hit broken connections.

How to control it:

- Separate test classes using different endpoints.
- Use `@DirtiesContext` where appropriate.
- Align container lifecycles with context caching.
- Ensure tests do not run concurrently against disrupted topologies.
- Never stop/start a container while reusing the same factory unless the endpoint truly stays identical.

## 28. Gathering Evidence from Every Test Run

A useful report goes beyond writing:

```text
SUCCESS
```

It records:

```text
Scenario ID
Redis image/engine version
Spring Boot / Spring Data Redis version
Driver version
Topology
Fault start time
Fault duration
Observed exception category
Hit/miss/error counter delta
Retry attempts
Recovery duration
Data consistency outcome
Cleanup status
```

These are controlled measurements, free of raw cache values or credentials.

Illustrative report example:

```text
Scenario: F05 network pause
Redis: standalone test container
Fault: pause Redis process
Expected: read throws CacheDependencyException
Observed: cause is Redis timeout
Expected: no cache miss increment
Observed: error incremented
Restore: unpause Redis
Expected: read/write recover before test deadline
Observed: verified by probe
```

When running real tests, replace `Observed` fields with real measured numbers and states—never fabricate results.

### 28.1. Assertions More Valuable Than Ping

Check:

```text
Can read an existing key?
Can write a new key with TTL?
Does serializer decode the value?
Does an API fallback stay inside timeout budget?
Does idempotency prevent duplicate side effects?
```

`PING -> PONG` only proves Redis answered one specific command, not that the full business path recovered.

## 29. Redis Server Metrics and Application Metrics

Spring Micrometer measures service behavior, while Redis server metrics are also essential.

Inspection commands on test Redis:

```redis
INFO memory
INFO stats
INFO keyspace
```

Useful counters:

```text
used_memory
used_memory_rss
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
```

### 29.1. Redis `keyspace_hits` Is Not Specific to ProductCacheGateway

Redis keyspace counters tally lookups across all commands/activities on that Redis node. They do not distinguish `products` from `sessions` or requests from two different services.

To know how the `products` cache is performing, rely on the application's `demo.redis.cache.lookup` or well-scoped cache region metrics.

### 29.2. Cumulative Counters Must Be Converted to Rates

If:

```text
12:00 evicted_keys = 1000
12:05 evicted_keys = 1300
```

the average rate is:

\[
\frac{1300-1000}{300}=1\ \text{key/second}
\]

Do not report `1300` as the number of keys evicted in 5 minutes. Redis restarts reset counters; monitoring systems must handle counter resets.

### 29.3. Multi-Node Redis Cluster

`INFO` on a single node does not represent the entire Cluster. Inspect per primary/shard, accounting for replica roles and resharding/failover.

Specifically, one primary can evict heavily even while other nodes still have plenty of free memory.

## 30. Analyzing Failed Test Results

A symptom reference table for diagnostics:

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| Test cannot connect to Redis container | Docker not ready, wrong mapped port | Container logs, actual host/port |
| `Connection refused` | Redis not running or wrong endpoint | `getMappedPort`, port/network |
| Timeout after pause | Redis unresponsive, client waiting | Timeout configuration, client metrics |
| `NOAUTH` | Missing/incorrect authentication | Test credential configuration |
| `NOPERM` | ACL denies command/key | Test user policy and command contract |
| `SerializationException` | Data incompatible with serializer | Check raw format/prior writer in test |
| `WRONGTYPE` | Key holds a different Redis type than called | `TYPE`, namespace/schema |
| `NOSCRIPT` | Script missing on node | Script lifecycle/fallback |
| `CROSSSLOT` | Multi-key command spans slots | `CLUSTER KEYSLOT` |
| `READONLY` | Write sent to replica or demoted primary | Topology/failover |
| Cache misses jump when Redis is down | Code swallows exceptions into misses | Gateway/error handler |
| Wrong metric counts | Test reads cumulative counters or shared state | Pre/post deltas, tags |
| Flaky TTL test | Sleeping right at deadline or slow call | Awaitility, longer TTL |
| Docker pause unavailable | Runtime/permissions unsupported | Use Toxiproxy/fault proxy |
| Container restart never reconnects | Mapped port changed; stale Spring context | Stable endpoint, context lifecycle |
| Redis returns yet API keeps failing | Driver reconnecting or queued backlog | End-to-end probe and p99 |

Do not try to fix every failure by raising timeouts infinitely. Distinguish **test bugs**, **configuration errors**, **environment limits**, and **application bugs**.

## 31. Common Mistakes

### Mistake 1: Only Mocking RedisTemplate

Mocks help unit tests, yet never prove serializers, TTLs, or real server protocol behavior. Write integration tests with a real Redis server.

### Mistake 2: Calling a Standalone Redis Container a Sentinel Test

Without a Sentinel quorum and replicas, Sentinel failover has not been tested.

### Mistake 3: Returning Null on Every Redis Exception

Timeouts, `NOPERM`, and serializer errors are not cache misses.

### Mistake 4: Asserting Only the Exception Class and Ignoring Cause

Wrappers can hide root causes. Verify `getCause()` whenever wrapping exceptions.

### Mistake 5: Logging Full Payloads for Debugging

Risks leaking sensitive data; log operation aliases, categories, trace IDs, and metrics instead.

### Mistake 6: Asserting Absolute Total Metric Values

Counters may already be incremented by earlier tests. Compare deltas and use isolated keys.

### Mistake 7: Using Thread.sleep for TTLs and Recovery

Increases flakiness without proving the condition holds. Use bounded polling with deadlines.

### Mistake 8: Stopping/Starting Testcontainers Assuming the Same Port

A restarted container can receive a new mapped port, leaving the connection factory pointing to the old port.

### Mistake 9: Pausing a Shared Redis Container

Breaks concurrent tests and corrupts results. Dedicate isolated topologies to fault injection.

### Mistake 10: Retrying Every Redis Write After Timeout

The command may already have executed. Require idempotency or dedicated protocols.

### Mistake 11: Assuming Timeout Means Redis Never Wrote

Timeout outcomes are ambiguous; reconcile business state.

### Mistake 12: Calling XACK Before Stream Processing Completes

If the consumer dies after ACK, work will not be retried via pending mechanisms.

### Mistake 13: Assuming Pub/Sub Replays Offline Messages

Standard Redis Pub/Sub has no replay.

### Mistake 14: Running FLUSHALL in Test Cleanup

Can wipe out-of-scope data if an endpoint is misconfigured or Redis is shared.

### Mistake 15: Leaving the Database Unprotected During Fallbacks

A Redis outage can cascade into a database outage via a thundering herd.

### Mistake 16: Testing One Cluster Key to Prove Routing

Verify across many hash slots and reshard/failover scenarios.

### Mistake 17: Checking Only Whether the Redis Process Is Up After a Fault

The Spring client may not have recovered yet. Run end-to-end read/write probes.

### Mistake 18: Omitting Test Environment Metadata

Results are hard to reproduce without versions, topology, timeouts, and fault durations.

### Mistake 19: Putting Product IDs or Redis Keys into Metric Labels

Causes cardinality explosions and leaks sensitive data.

### Mistake 20: Increasing Timeouts to "Fix" ACL or WRONGTYPE Errors

Waiting longer never resolves permission or type errors.

### Mistake 21: Assuming Replication Never Loses Writes

Redis replication is normally asynchronous; test against RPO and use authoritative sources where needed.

### Mistake 22: Skipping Recovery Tests Across Serializer/Schema Migrations

Redis still holds keys, yet new code may fail to deserialize them.

### Mistake 23: Treating Health Check PING as Complete Verification

PING proves neither cache hit/miss logic, writes, serializers, nor idempotency.

### Mistake 24: Ignoring Post-Failover Retry Storms

A freshly recovered Redis can be overwhelmed by thousands of clients retrying simultaneously.

### Mistake 25: Judging Tests Solely by Green Assertions

Inspect latency, error categories, recovery times, and data correctness—not just "test passed".

## 32. Extension Exercises

### Exercise A: Metrics and Logs for Serializer Errors

Implement the malformed JSON test. Add a `ListAppender` in tests to confirm a mock secret string never appears in application logs.

Criteria:

```text
read_error increments by one
getCause() retains SerializationException
read_miss does not increment
raw payload is never logged
```

### Exercise B: Redis Outage Under Concurrent Requests

Run multiple concurrent cache-read requests, pause Redis, and then recover it. Measure:

- Timed-out request count.
- p95/p99 latency.
- Retry counts.
- Connection pool / pending commands.
- Time to recover after unpause.

Never run unbounded load on CI or shared Redis instances.

### Exercise C: Redis Fallback and Database Protection

Set up a fake source or PostgreSQL test container. Simulate Redis failures and cap fallback concurrency.

Verify:

```text
Redis timeout -> fallback counter increments
Database receives load strictly within budget
API returns results or errors per contract
```

### Exercise D: Retrying INCR

Build a fault injector that drops the reply after Redis executes `INCR`. Let the client retry per policy and compare behavior before and after adding an operation ID.

### Exercise E: Stream Pending Recovery

Create a test Stream and consumer group, leave an entry pending, and recover it via claiming. Assert the business side effect runs exactly once.

### Exercise F: Spring Cache Annotations

Create `@Cacheable("products")` with a fake source counting loads and test hits, misses, per-ID invalidation, TTLs, and Redis errors.

### Exercise G: Managed Redis Contract

List the commands your application actually uses, verify permissions on managed staging, and test `NOPERM`/unknown command handling without sending destructive commands to production.

### Exercise H: Redis Cluster Failover

Spread keys across multiple slots, trigger a failover on one shard in an isolated test Cluster, and measure the impact on keys in that shard versus unaffected shards.

## 33. Self-Check Questions

**1. Why are unit tests mocking RedisTemplate insufficient?**

Because mocks do not verify the Redis protocol, serializers, TTLs, connections, or real server errors.

**2. Is a `GET` returning null the same as a timeout?**

No. Null indicates an absent key; a timeout is a dependency failure requiring separate handling.

**3. Why preserve the exception cause when wrapping Redis errors?**

To keep the original error type for classification, retry/fallback decisions, and diagnostics while keeping wrapper messages safe.

**4. Should deserialization errors be treated as cache misses?**

Not by default. The key may exist with a payload incompatible with the current schema/serializer.

**5. Why avoid fixed Thread.sleep while waiting for Redis recovery?**

Recovery duration varies; sleeping does not prove the app reconnected. Use bounded polling with a deadline.

**6. Does stopping and starting a Redis Testcontainer always keep the same mapped port?**

No. If the port changes while the connection factory holds the old endpoint, the application keeps failing.

**7. Does a Redis timeout after INCR prove the counter did not increment?**

No. The command may have executed with a lost reply; retrying can increment twice.

**8. When should you fall back from Redis to the database?**

When Redis is strictly a cache and the database is authoritative, under explicit error, timeout, and load-limit policies.

**9. Why test `hit`, `miss`, and `error` metrics separately?**

To avoid counting outages as cache misses and to track both cache effectiveness and dependency reliability.

**10. Do pending Redis Streams entries automatically appear to new consumers polling with `>`?**

No. You need pending/reclaim handling such as `XAUTOCLAIM` paired with idempotent processing.

**11. Do Pub/Sub subscribers receive messages published while they were offline?**

Not under standard Redis Pub/Sub; there is no default replay.

**12. Does Redis Cluster require testing across multiple keys and slots?**

Yes. One working key does not prove multi-slot routing and topology redirects work.

**13. Why should corrupt-data tests use real Redis?**

Because they test the entire path from raw bytes in Redis through Spring Data Redis serializers to application exceptions.

**14. Once Redis is back up, why can you not immediately assume the API has recovered?**

Clients may not have reconnected yet, pools may be saturated, script caches may be empty, or retries may keep failing requests.

**15. Why avoid FLUSHALL for integration test cleanup?**

Because it can wipe out-of-scope data if endpoints are misconfigured or environments are not completely isolated.

**16. Between which milestones should RTO be measured?**

By business definition, typically from fault onset until the application serves within SLO again—not just until the Redis process starts.

**17. Why can logging full Redis exceptions be dangerous?**

Exception messages/stack traces can expose keys, values, URIs, or sensitive infrastructure details.

**18. Does a passing test after failover prove zero data loss?**

No. Reconcile write sequences/revisions and evaluate against the topology's RPO.

**19. If Redis returns NOPERM, will exponential backoff make the command succeed?**

No. That is usually a permission/configuration issue requiring contract and ACL fixes.

**20. Can standalone Testcontainers completely replace managed Redis staging?**

Not completely. Managed services can differ in TLS, ACLs, engine versions, topology, quotas, and allowed commands.

## 34. Key Takeaways

- **Redis integration tests must run against real Redis**, not solely mocked Spring Data Redis APIs.
- **Separate happy paths, failure paths, and recovery paths:** hits, misses, TTLs, malformed payloads, connection timeouts, reconnects, and post-retry correctness.
- **A cache miss is not a Redis error.** Record `hit`, `miss`, and `error` metrics separately.
- **Preserve the original cause** when wrapping errors; responses and logs must never expose keys, values, or raw exception messages.
- **Use Testcontainers with dynamic mapped ports** for standalone tests, ensuring tests never point at production Redis.
- **Use Awaitility/bounded condition polling with deadlines**, not bare `Thread.sleep`, to observe expiration and recovery.
- **Fault injection requires isolated environments.** Pause/unpause or proxies preserve endpoints; never stop/start containers assuming ports stay unchanged.
- **Timeouts after write commands have ambiguous outcomes.** Retries require idempotency/operation IDs.
- **Fall back only when an authoritative source exists and load is bounded.** Never let a Redis outage cascade into database overload.
- **Redis Streams require pending/reclaim handling and proper ACK timing; Pub/Sub has no replay.**
- **Sentinel and Cluster require dedicated topology integration tests**; a single container tests neither failover nor hash-slot routing.
- **Observe end-to-end:** exception categories, metrics, latency, retries, RTO/RPO, and post-incident data correctness.
- **Build repeatable tests:** isolated namespaces, TTLs, scoped cleanup, no `FLUSHALL`, and recorded versions, topology, and environment settings.

### References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — Connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html).
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Testcontainers Java — Documentation](https://java.testcontainers.org/).
- [Testcontainers — Redis Module](https://java.testcontainers.org/modules/redis/).
- [Awaitility — Project](https://github.com/awaitility/awaitility).
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
