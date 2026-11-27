# Testing TTL Without Fragile Fixed Sleeps

In Spring Data Redis, **TTL (time to live)** is the duration Redis allows a key to exist before it expires. TTL tests frequently become flaky when written as: set a 1-second TTL, `Thread.sleep(1000)`, then assert the key is gone. Such a test may pass locally yet fail on CI because command execution time, thread scheduling, machine load, and when Redis processes key expiration do not align cleanly with the fixed wait.

The goal is to test **observable behavior**: the key has a TTL after being written, Redis still returns the value before expiration, and the key eventually becomes unreachable within a reasonable timeout window. We do not need to predict the exact millisecond a command completes.

## 1. Why do fixed `sleep` calls easily make tests fail?

Suppose an application sets a 1-second TTL:

```java
redisTemplate.opsForValue().set("otp:123", "654321", Duration.ofSeconds(1));
Thread.sleep(1000);
assertThat(redisTemplate.opsForValue().get("otp:123")).isNull();
```

This snippet has several issues:

- Writes and reads travel over the network; when the Java thread goes to sleep is not necessarily the exact instant Redis starts counting the TTL.
- On CI, the test thread may be paused or woken up late; when asserting that a key has **not** expired yet, delays produce false failures.
- If the sleep is shorter than actually needed, tests fail intermittently. If you inflate `sleep` to "play it safe," the whole test suite slows down.
- Redis uses active and passive expiration. Physical key cleanup or emitting expiration events does not necessarily occur at an exact timestamp. However, when an expired key is read, Redis processes the expiration and does not return the stale value.

In particular, do not swap `sleep(1000)` for `sleep(1200)` and treat that as a general fix. Padding reduces failure frequency while still coupling the test to assumptions about environment execution speed.

## 2. Distinguishing Redis's three TTL states

Redis provides `TTL` (seconds) and `PTTL` (milliseconds). With Spring Data Redis, you can read remaining TTL in milliseconds using:

```java
Long remainingMillis = redisTemplate.getExpire(key, TimeUnit.MILLISECONDS);
```

Return values have the following meanings:

| Value | Meaning | How to test |
| --- | --- | --- |
| Positive number | Key exists and currently has an expiration | Assert TTL is positive; optionally check an upper bound |
| `-1` | Key exists without an expiration attached | Assert `-1` when verifying a non-expiring key |
| `-2` | Key does not exist, including after expiration | Assert `-2` when verifying the final outcome of expiration |
| `0` | With millisecond measurement, can occur right on the expiration boundary | Do not confuse `0` with `-2`; avoid razor-thin timing windows |

Second-level `TTL` has coarse resolution: a key with less than one second remaining can return `0`. Therefore, **prefer `getExpire(..., TimeUnit.MILLISECONDS)`** when observing TTL in tests. Do not demand exact equality with the configured TTL: latency between write and query means remaining time has already ticked down.

Separate these questions explicitly:

1. *Was the TTL set successfully?* — Right after writing, assert TTL is positive.
2. *Is the key readable right after creation?* — Check the value immediately after writing with a sufficiently wide TTL.
3. *Does the key eventually expire?* — Poll conditionally with a maximum timeout.
4. *Did extending or removing the TTL work?* — Re-read the TTL status after the corresponding operation without waiting for the TTL to fully run down if unnecessary.

## 3. Using bounded polling instead of fixed waits

**Polling** repeatedly checks a condition with a short pause between attempts. As soon as the condition holds, the test finishes; if the timeout expires, the test fails and reports which assertion was still unmet.

```text
Write key with TTL
       │
       ▼
Verify key and initial TTL
       │
       ▼
Check if key is gone? ──── Yes ──► Pass
       │
       No
       │
       ▼
Still within timeout? ──── No ───► Fail with last assertion error
       │
      Yes
       │
       ▼
Pause briefly and retry
```

In Java/JUnit, **Awaitility** provides a clean API for this style of test:

```java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(redisTemplate.opsForValue().get(key)).isNull()
    );
```

`atMost` is an **upper bound**, not a requirement to wait a full 8 seconds. `pollInterval` throttles query frequency to avoid hammering Redis. `untilAsserted` retries the assertion until it passes or times out. The timeout should exceed the test TTL with headroom for CI; the poll interval should be short enough to notice changes promptly without creating excessive load.

## 4. Complete example: JUnit 5 + Spring Data Redis + Testcontainers

Integration tests need a real Redis server enforcing expiration times. Testcontainers spins up a dedicated Redis instance for the test suite, avoiding shared-Redis data and configuration collisions. The example below uses Spring Boot 3.x, Java 21, AssertJ, Awaitility, and JUnit 5.

If your project manages dependency versions through the Spring Boot BOM/plugin, you can declare dependencies in Gradle Groovy as follows:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
```

The test runner requires Docker (or a compatible container runtime) to launch Redis. If your project already provides an isolated Redis instance for integration tests, you can reuse that setup instead of Testcontainers.

```java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = RedisTtlIntegrationTest.TestApplication.class)
class RedisTtlIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redisTemplate;

    @Test
    void keyEventuallyExpiresWithoutFixedSleep() {
        String key = "test:ttl:" + UUID.randomUUID();

        try {
            // SET k value EX/PX: value and TTL are set in the same operation.
            redisTemplate.opsForValue().set(
                key, "payload", Duration.ofMillis(1800)
            );

            assertThat(redisTemplate.opsForValue().get(key))
                .isEqualTo("payload");

            Long initialTtl = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(initialTtl).isNotNull().isPositive();

            // Wait until Redis stops returning the key, up to 8 seconds.
            await()
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    assertThat(redisTemplate.opsForValue().get(key))
                        .isNull();
                    assertThat(redisTemplate.getExpire(
                        key, TimeUnit.MILLISECONDS
                    )).isEqualTo(-2L);
                });
        } finally {
            redisTemplate.delete(key);
        }
    }

    @Test
    void distinguishesNoExpiryFromMissingKey() {
        String persistentKey = "test:persistent:" + UUID.randomUUID();
        String missingKey = "test:missing:" + UUID.randomUUID();

        try {
            redisTemplate.opsForValue().set(persistentKey, "value");

            assertThat(redisTemplate.getExpire(
                persistentKey, TimeUnit.MILLISECONDS
            )).isEqualTo(-1L);

            assertThat(redisTemplate.getExpire(
                missingKey, TimeUnit.MILLISECONDS
            )).isEqualTo(-2L);
        } finally {
            redisTemplate.delete(persistentKey);
            redisTemplate.delete(missingKey);
        }
    }

    @Test
    void refreshingTtlIncreasesRemainingLifetime() {
        String key = "test:refresh:" + UUID.randomUUID();

        try {
            redisTemplate.opsForValue().set(
                key, "value", Duration.ofSeconds(30)
            );
            Long before = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(before).isNotNull().isPositive();

            assertThat(redisTemplate.expire(key, Duration.ofSeconds(60)))
                .isTrue();

            Long after = redisTemplate.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(after).isNotNull().isGreaterThan(before);
        } finally {
            redisTemplate.delete(key);
        }
    }
}
```

### What makes this example more reliable?

- **Isolated key names:** UUID suffixes prevent parallel tests from overwriting each other's keys.
- **Value and TTL written in one operation:** `opsForValue().set(key, value, Duration)` eliminates any gap between `SET` and `EXPIRE` when both must take effect together.
- **Condition-based checks over time counting:** the expiration test waits for `get(key) == null` and TTL `-2`; it finishes as soon as the condition passes.
- **Bounded timeout:** if TTL was never set or Redis misbehaves, the test fails within a finite budget.
- **No waiting 30/60 seconds to test renewal:** two TTL reads suffice to confirm the extension increased remaining lifetime; a test solely verifying renewal need not wait for the key to die.
- **Targeted key cleanup:** `finally` cleans up test data even if an assertion fails. Avoid `FLUSHALL` because it can affect other tests.

A Spring Boot application with its own configuration/startup class can replace `TestApplication` with its existing test configuration. The key requirement is that `StringRedisTemplate` actually points to the Redis instance launched by Testcontainers.

## 5. How to choose timeouts and resolution?

No single number fits every system. You can start with the example's parameters and adjust based on test type and infrastructure:

| Parameter | Example | Meaning |
| --- | --- | --- |
| Test TTL | 1.8 seconds | Long enough to confirm the key exists right after writing |
| Poll interval | 50 ms | Moderate check cadence without creating a busy loop |
| Timeout | 8 seconds | Budget for Redis expiration handling and CI latency |
| TTL comparison unit | Milliseconds | Avoids discrepancies from rounding down to whole seconds |

The timeout must be a **maximum budget** for the expected event. For instance, a 1.8-second TTL with `atMost(1.8 seconds)` sits right on the razor's edge; minor execution slowdown can fail the test. Conversely, a 60-second TTL with a 2-minute timeout produces a very slow integration test; use short TTLs for expiration tests and longer TTLs for tests that only verify renewal.

Do not set `pollInterval` too low, such as 1 ms, when polls send commands over the network: tight polling wastes CPU and adds Redis load. Nor should you poll only once after several seconds, which effectively reverts to a fixed `sleep`.

## 6. Common pitfalls when testing TTL

### 6.1. Confusing "Redis expired the key" with "key deletion event emitted"

Redis can return `null` for an expired key on access while keyspace notifications or background cleanup occur at a different observable time. If your goal is testing that cached data is no longer readable, assert via `GET`/`PTTL`. If your goal is testing a listener handling **expiration events**, configure notifications properly and assert event receipt separately using a latch or bounded polling. Do not infer the listener definitely received the event solely from `get(key) == null`.

For instance, `CountDownLatch.await(timeout, unit)` waits for an event and returns early as soon as it arrives. This is a conditional wait, unlike `Thread.sleep` which always waits the full duration no matter what happened. In Redis, keyspace notifications also depend on server configuration and use Pub/Sub semantics; do not rely on them for business logic requiring guaranteed event delivery.

### 6.2. Using `Clock.fixed()` and expecting Redis to freeze or fast-forward time

An injected Java `Clock` only controls application code that **reads that clock**. It does not jump the Redis container's clock into the future. Likewise, `StepVerifier.withVirtualTime()` only virtualizes Reactor schedulers within its scope; real Redis commands still run against the server's real clock.

Separate two types of tests:

- **Unit tests**: use `Clock.fixed()` or a fake clock to verify how the application computes expiration timestamps, chooses TTLs, or decides whether to renew. Unit tests do not need to wait and do not prove Redis actually deleted keys.
- **Integration tests**: use real Redis, short TTLs, and Awaitility to verify Redis commands, serialization, cache lookups, repositories, and expiration behavior working together.

With `@Cacheable`, `RedisCacheManager` configuration, or `@TimeToLive` repositories, inspect the TTL on the **actual generated key** and read behavior at the layer under test. Do not assume every cache read automatically refreshes TTL; renewal behavior depends on how the application configures and writes keys.

### 6.3. Asserting exact remaining milliseconds

This assertion is very brittle:

```java
redisTemplate.opsForValue().set(key, "value", Duration.ofSeconds(5));
assertThat(redisTemplate.getExpire(key, TimeUnit.MILLISECONDS))
    .isEqualTo(5000L); // Fragile: TTL has already begun counting down.
```

If you only need to prove a TTL was attached, check `TTL > 0` and (when useful) `TTL <= 5000`. When business logic dictates a minimum or maximum bound, pick a tolerance based on that requirement and expected execution overhead rather than pinning an assertion to one exact timestamp. With ultra-short TTLs, even a positive check right after writing can flake; pick a TTL wide enough for the assertion.

### 6.4. Drawing the wrong conclusion when a key still exists

When `PTTL = -1`, the key exists **with no expiration**; when `PTTL = -2`, the key **does not exist**. If a key fails to expire as expected, check whether code accidentally called `persist`, `SET` without a TTL, overwrote via a TTL-stripping operation, or computed TTL in the wrong unit. Some overwrite commands modify or clear old TTLs while certain in-place updates preserve them: behavior depends on the exact Redis command executed.

### 6.5. Parallel tests or shared Redis instances

Two tests sharing the key `session:test` can yield irreproducible failures even when each is individually valid. Use unique key names, isolate test Redis instances, and clean up keys after running. Avoid relying on test execution order, leftover state from prior runs, or the clock/load of a particular CI runner.

## 7. Where to look when polling times out?

If `untilAsserted` still fails after timing out, check in a logical order:

1. **Was a TTL attached at all?** Read `PTTL`; `-1` indicates no expiration, `-2` indicates the key is already missing.
2. **Was the TTL set on the right key?** Cache keys may carry prefixes, namespaces, or serializers differing from the raw string in source code.
3. **Is something rewriting the key?** A refresh job, callback, or another test may recreate the key so `GET == null` never holds.
4. **What unit was the TTL computed in?** Mixing seconds and milliseconds can make a TTL 1,000x larger or nearly zero.
5. **Are you talking to the right Redis instance?** Verify Spring Boot's host/port points to the container started for the test.
6. **Are you waiting on an event that differs from readability?** Expiration listeners, background cleanup, and `GET` are distinct signals.

When investigating, log useful diagnostics like the test key name, observed TTL, `GET` status, wait start time, and chosen timeout. You can log poll attempts at moderate intervals; avoid noisy logging that noticeably perturbs test timing.

## 8. Principles for applying this in projects

A solid TTL test generally has three phases: **clear state setup**, **condition-based observation**, and **bounded waiting**. For Spring Data Redis, combining `set(key, value, Duration)` + `getExpire(..., MILLISECONDS)` + Awaitility covers most expiration tests for caches, tokens, sessions, and temporary data.

Match your evidence to what you need to prove: positive TTL for verifying expiration attachment, `-1` for non-expiring keys, `-2` alongside `null` for expired keys, and dedicated events when verifying listeners. That way, tests express business intent clearly, finish as soon as conditions are satisfied, and remain resilient to machine speed and CI scheduling.
