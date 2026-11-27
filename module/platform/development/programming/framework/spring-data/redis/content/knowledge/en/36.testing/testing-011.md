# Testing Reactive Streams with `StepVerifier`

In **reactive Spring Data Redis**, calls like `ReactiveStringRedisTemplate.opsForValue().get(key)` do not directly return a `String`; they construct a `Mono<String>`. Likewise, scanning a collection or reading a Stream returns a `Flux<T>`. A reactive chain only emits signals once **subscribed**; the outcome is not merely a value, but can also be **empty completion, an error, multiple values, or subscription cancellation**.

**`StepVerifier`** belongs to Project Reactor's `reactor-test` module and **subscribes to a publisher to assert emitted signals step by step**. When testing Spring Data Redis, `StepVerifier` lets you verify key writes and reads, cache misses, TTL, Redis error handling, `flatMap`/`concatMap` behavior, retries, timeouts, and async scenarios without calling `block()` or relying on `Thread.sleep(...)`.

This lesson shows how to use `StepVerifier` from unit tests to integration tests with real Redis, choose between real time and **virtual time**, distinguish what `StepVerifier` can prove from what must be verified on Redis itself, and avoid common reactive pipeline testing mistakes.

## 1. Why Synchronous Testing Approaches Fall Short

With synchronous `StringRedisTemplate`, test code can inspect the result directly:

~~~java
String value = stringRedisTemplate.opsForValue().get("demo:key");
assertThat(value).isEqualTo("hello");
~~~

In the reactive API:

~~~java
Mono<String> value =
    reactiveRedisTemplate.opsForValue().get("demo:key");
~~~

The `value` variable is a **publisher**, not the loaded Redis value. Checking `assertThat(value).isNotNull()` only proves the publisher object exists—not that `GET` succeeded or returned the right value.

Some code might write:

~~~java
String value = reactiveRedisTemplate.opsForValue()
    .get("demo:key")
    .block();
~~~

`.block()` is occasionally used in tests to grab a value, yet it discards information about the **reactive signal sequence**, hiding bugs in ordering, cancellation, empty completion, or errors. It can also be copy-pasted by mistake into WebFlux handlers, where blocking harms the event loop.

With `StepVerifier`:

~~~java
StepVerifier.create(
        reactiveRedisTemplate.opsForValue().get("demo:key")
    )
    .expectNext("hello")
    .verifyComplete();
~~~

`StepVerifier` **subscribes automatically**, awaits `onNext("hello")`, and verifies the publisher emits `onComplete()` without extra values or errors.

## 2. Understanding the Exact Signals to Verify

Per Reactive Streams, a subscriber can observe:

| Signal | Meaning | Common Assertion |
| --- | --- | --- |
| `onSubscribe` | Publisher passes subscription | `expectSubscription()` |
| `onNext(value)` | A value was emitted | `expectNext(value)`, `assertNext(...)` |
| `onComplete` | Stream completed normally | `expectComplete()` / `verifyComplete()` |
| `onError(error)` | Stream failed | `expectError(...)` / `verifyError(...)` |
| `cancel` | Subscriber stopped requesting data | `thenCancel()` |
| No events for a duration | Stream is waiting or time-driven | `expectNoEvent(Duration)` |

`Mono<T>` emits at most one `onNext`; `Flux<T>` can emit many. Redis `GET` for a non-existent key typically yields `Mono.empty()`, meaning **no `onNext`, only `onComplete`**. This is neither `Mono.just(null)` nor a Redis error.

~~~text
Mono.just("ok")         onSubscribe → onNext("ok") → onComplete
Mono.empty()            onSubscribe → onComplete
Mono.error(error)       onSubscribe → onError(error)
Flux.just("a","b")      onSubscribe → onNext("a") → onNext("b") → onComplete
Flux.never()            onSubscribe → emits no terminal signal
~~~

When testing a cache:

- **Hit:** `expectNext(value).verifyComplete()`.
- **Miss:** `verifyComplete()` with no `expectNext`.
- **Broken Redis:** `expectError...` instead of treating failures as cache misses.
- **Fallback:** assert the fallback source value and completion signal.

## 3. Dependencies and Project Skeleton

Example with Java 21, Spring Boot 3.x, and Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

`reactor-test` provides `StepVerifier`. `spring-boot-starter-test` brings in JUnit 5, AssertJ, Mockito, and standard test utilities per Spring Boot version. `testcontainers-junit-jupiter` starts real Redis in integration tests when Docker is available.

The WebFlux starter can be omitted if the project does not need a reactive HTTP server; testing `Mono`/`Flux` from Spring Data Redis does not require WebFlux controllers.

Common imports:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
~~~

Never call `publisher.subscribe()` manually before `StepVerifier.create(...)`. `StepVerifier` acts as the subscriber that subscribes and observes signals per scenario.

## 4. Simple Scenarios: Value, Empty, and Error

### 4.1. `Mono` with One Value

~~~java
@Test
void verifiesOneValueThenCompletion() {
    Mono<String> result = Mono.just("ready");

    StepVerifier.create(result)
        .expectNext("ready")
        .verifyComplete();
}
~~~

`verifyComplete()` confirms the stream emitted the declared signals and terminated with `onComplete`. It rejects `onError` or unexpected extra values.

### 4.2. Empty `Mono`

~~~java
@Test
void verifiesEmptyResult() {
    Mono<String> result = Mono.empty();

    StepVerifier.create(result)
        .verifyComplete();
}
~~~

When a pipeline uses `switchIfEmpty`:

~~~java
@Test
void verifiesFallbackOnEmpty() {
    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(Mono.just("from-source"));

    StepVerifier.create(result)
        .expectNext("from-source")
        .verifyComplete();
}
~~~

This tests cache-miss fallback: **when absent**, fall back to the authoritative source without treating absence as a Redis connection error.

### 4.3. Failing `Mono`

~~~java
@Test
void verifiesError() {
    Mono<String> result = Mono.error(
        new IllegalArgumentException("invalid key")
    );

    StepVerifier.create(result)
        .expectErrorMatches(error ->
            error instanceof IllegalArgumentException
                && "invalid key".equals(error.getMessage())
        )
        .verify();
}
~~~

Ways to assert errors:

~~~java
StepVerifier.create(Mono.error(new IllegalStateException("failed")))
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(Mono.error(new IllegalStateException("failed")))
    .expectErrorMessage("failed")
    .verify();
~~~

Pick assertions specific enough to catch wrong behavior without locking onto exact driver error strings that may change across Lettuce, Jedis, or Spring Data Redis versions. For real Redis errors, usually assert the **exception hierarchy or behavior**, not the entire stack trace.

### 4.4. Multi-Value `Flux`

~~~java
@Test
void verifiesMultipleValuesInOrder() {
    Flux<String> result = Flux.just("a", "b", "c");

    StepVerifier.create(result)
        .expectNext("a", "b", "c")
        .verifyComplete();
}
~~~

`expectNext("a", "b", "c")` enforces **emission order**. This fits `concatMap` pipelines, yet should not be applied to concurrent `flatMap` pipelines unless business semantics guarantee ordering.

## 5. Inspecting Complex Payloads with `assertNext` and `expectNextMatches`

Responses are not always plain Strings. A service might return a DTO mapped from Redis:

~~~java
public record ProductView(String id, String name, long priceCents) {
}
~~~

Test:

~~~java
@Test
void verifiesDtoFields() {
    Mono<ProductView> result =
        Mono.just(new ProductView("p-42", "Keyboard", 750000));

    StepVerifier.create(result)
        .assertNext(view -> {
            assertThat(view.id()).isEqualTo("p-42");
            assertThat(view.name()).isEqualTo("Keyboard");
            assertThat(view.priceCents()).isPositive();
        })
        .verifyComplete();
}
~~~

`assertThat` comes from AssertJ. `assertNext` shines when asserting multiple fields on an object and wanting clear per-field failure messages.

When a single boolean predicate suffices:

~~~java
StepVerifier.create(result)
    .expectNextMatches(view ->
        view.id().startsWith("p-")
            && view.priceCents() >= 0
    )
    .verifyComplete();
~~~

`expectNextMatches` takes a predicate. If it returns `false`, `StepVerifier` reports a failed expectation at that step. For multi-field DTOs, `assertNext` usually makes debugging easier.

### Naming Expectations

For multi-step tests, attach `as(...)` labels to describe steps:

~~~java
StepVerifier.create(Flux.just("STARTED", "RUNNING", "DONE"))
    .expectNext("STARTED").as("initial state")
    .expectNext("RUNNING").as("progress state")
    .expectNext("DONE").as("terminal state")
    .verifyComplete();
~~~

Step descriptions aid diagnostics when assertions fail without altering publisher behavior.

## 6. Building a Spring Data Redis Service to Test

The service below implements a product cache backed by `ReactiveStringRedisTemplate`:

- `save(...)`: writes a value with TTL and emits the ID once Redis confirms the write.
- `load(...)`: emits the product name, or completes empty if the key is absent.
- `loadRequired(...)`: turns a cache miss into a domain error with a clear message.
- `rename(...)`: loads the old name, writes the new name, and emits the new value sequentially.

~~~java
package com.example.redis.testing;

import java.time.Duration;
import java.util.Objects;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCache {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCache(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    private String key(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException(
                "productId must not be blank"
            );
        }
        return "cache:product:v1:" + productId;
    }

    public Mono<String> load(String productId) {
        return redis.opsForValue().get(key(productId));
    }

    public Mono<String> save(
            String productId, String name, Duration ttl) {
        Objects.requireNonNull(name);
        Objects.requireNonNull(ttl);

        return redis.opsForValue()
            .set(key(productId), name, ttl)
            .filter(Boolean.TRUE::equals)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Redis did not accept SET")
            ))
            .thenReturn(productId);
    }

    public Mono<String> loadRequired(String productId) {
        return load(productId)
            .switchIfEmpty(Mono.error(
                new java.util.NoSuchElementException(
                    "Product is not cached: " + productId
                )
            ));
    }

    public Mono<String> rename(
            String productId, String newName, Duration ttl) {
        Objects.requireNonNull(newName);

        return loadRequired(productId)
            .flatMap(previous ->
                save(productId, newName, ttl)
                    .thenReturn(newName)
            );
    }
}
~~~

In `save`, if `Mono<Boolean>` from `SET` emits `false`, `filter` produces empty completion and `switchIfEmpty` emits the error; `thenReturn` runs only when the preceding step succeeded. If Redis emits `onError`, the error propagates directly.

`rename` illustrates chaining publishers. Reading and then writing **is not an atomic transaction**: another worker could mutate the key in between. The goal here is testing **ordering and signals** in pipelines, not providing multi-writer compare-and-set.

## 7. Unit-Testing the Service Without a Redis Server

When testing how the service composes `Mono` chains without hitting network or drivers, mock `ReactiveStringRedisTemplate` and `ReactiveValueOperations`. This is **composition unit testing**; whether Redis actually persists data is verified in dedicated integration tests.

~~~java
package com.example.redis.testing;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ReactiveValueOperations;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ReactiveProductCacheUnitTest {

    private ReactiveStringRedisTemplate redis;
    private ReactiveValueOperations<String, String> values;
    private ReactiveProductCache cache;

    @BeforeEach
    void setUp() {
        redis = mock(ReactiveStringRedisTemplate.class);
        values = mock(ReactiveValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);
        cache = new ReactiveProductCache(redis);
    }

    @Test
    void loadReturnsAValue() {
        when(values.get("cache:product:v1:p-1"))
            .thenReturn(Mono.just("Keyboard"));

        StepVerifier.create(cache.load("p-1"))
            .expectNext("Keyboard")
            .verifyComplete();
    }

    @Test
    void missingKeyCompletesWithoutValue() {
        when(values.get("cache:product:v1:unknown"))
            .thenReturn(Mono.empty());

        StepVerifier.create(cache.load("unknown"))
            .verifyComplete();
    }

    @Test
    void requiredValueReportsMissingKey() {
        when(values.get("cache:product:v1:unknown"))
            .thenReturn(Mono.empty());

        StepVerifier.create(cache.loadRequired("unknown"))
            .expectError(java.util.NoSuchElementException.class)
            .verify();
    }

    @Test
    void saveRequiresSuccessfulRedisResponse() {
        when(values.set(
                "cache:product:v1:p-1",
                "Keyboard",
                Duration.ofMinutes(5)))
            .thenReturn(Mono.just(true));

        StepVerifier.create(cache.save(
                "p-1", "Keyboard", Duration.ofMinutes(5)))
            .expectNext("p-1")
            .verifyComplete();
    }

    @Test
    void rejectedWriteDoesNotBecomeSuccess() {
        when(values.set(
                "cache:product:v1:p-1",
                "Keyboard",
                Duration.ofMinutes(5)))
            .thenReturn(Mono.just(false));

        StepVerifier.create(cache.save(
                "p-1", "Keyboard", Duration.ofMinutes(5)))
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Here `@BeforeEach` builds fresh mocks per test so stubbing never leaks across tests. `StepVerifier` subscribes to the returned publisher and asserts emitted signals.

`ReactiveValueOperations` is a generic interface, so Mockito and Java may emit an *unchecked conversion* warning when mocking the generic type. That warning does not alter test semantics; projects can suppress it narrowly on the declaration or use version-appropriate mock helpers.

These unit tests **do not prove** Redis actually attaches TTL to keys, serializers match, or connection errors translate properly: those require integration tests against real Redis.

## 8. Integration Tests: Spring Boot, Real Redis, and Testcontainers

The unit tests above control mocked responses. To verify reactive Spring Data Redis actually connects, serializes keys, executes `SET`/`GET`, and sets TTL, run against a dedicated Redis instance.

Example test class setup:

~~~java
package com.example.redis.testing;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
    classes = ReactiveProductCacheIntegrationTest.TestApp.class
)
class ReactiveProductCacheIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(ReactiveProductCache.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Autowired
    ReactiveProductCache cache;

    @Test
    void writeThenReadWithStepVerifier() {
        String productId = "it-" + UUID.randomUUID();
        String key = "cache:product:v1:" + productId;

        Mono<String> workflow = cache.save(
                productId, "Mechanical Keyboard",
                Duration.ofMinutes(5)
            )
            .then(cache.load(productId));

        try {
            StepVerifier.create(workflow)
                .expectSubscription()
                .expectNext("Mechanical Keyboard")
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        } finally {
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        }
    }

    @Test
    void missingKeyCompletesEmpty() {
        String productId = "missing-" + UUID.randomUUID();

        StepVerifier.create(cache.load(productId))
            .expectSubscription()
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void setAttachesPositiveTtl() {
        String productId = "ttl-" + UUID.randomUUID();
        String key = "cache:product:v1:" + productId;

        Mono<Duration> workflow = cache.save(
                productId, "Monitor", Duration.ofSeconds(60)
            )
            .then(redis.getExpire(key));

        try {
            StepVerifier.create(workflow)
                .assertNext(remaining ->
                    assertThat(remaining)
                        .isGreaterThan(Duration.ZERO)
                        .isLessThanOrEqualTo(Duration.ofSeconds(60))
                )
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        } finally {
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .expectComplete()
                .verify(Duration.ofSeconds(8));
        }
    }
}
~~~

`@Testcontainers` manages the Redis container lifecycle. `@DynamicPropertySource` injects the Testcontainers-mapped host and port into the Spring Boot context. `@Import` registers our service, and `@EnableAutoConfiguration` configures the reactive Redis template per dependencies.

Each test uses a `UUID` in the key to prevent colliding with other tests. Afterward, `finally` executes `DELETE` via a dedicated publisher and verifies completion. The example uses only test Redis, avoiding `FLUSHDB`/`FLUSHALL`.

### Why Must Setup and Assertion Live in the Same Pipeline?

If you write:

~~~java
cache.save(productId, "Monitor", Duration.ofMinutes(5));

StepVerifier.create(cache.load(productId))
    .expectNext("Monitor")
    .verifyComplete();
~~~

`cache.save(...)` merely **constructs a `Mono`** that is discarded. Without a subscriber, no `SET` is sent and the read completes empty. Chain with `then(...)`:

~~~java
Mono<String> workflow = cache.save(
        productId, "Monitor", Duration.ofMinutes(5)
    )
    .then(cache.load(productId));

StepVerifier.create(workflow)
    .expectNext("Monitor")
    .verifyComplete();
~~~

`then` awaits successful completion of the write before subscribing to the read. If the write errors, the read never runs. This establishes **ordering within a single subscription**, not an atomic Redis transaction.

### Key Characteristics of Real Integration Tests

- Requires Docker or a Testcontainers-compatible runtime.
- Redis startup, networking, and CI scheduling take time; `verify(Duration.ofSeconds(8))` is an **example** deadline to tune per your test SLA.
- `GET` on a missing key differs from a Redis connection error. Never write a “missing key” test by trying to disconnect Redis.
- Remaining TTL will be slightly less than the configured duration as time passes; never assert exact `Duration.ofSeconds(60)`.
- A standalone Redis container **does not prove** Sentinel, Cluster, or failover; those topologies require dedicated integration environments.

## 9. `verifyComplete`, `verifyError`, and Bounded Wait Timeouts

`StepVerifier` provides convenient terminal shortcuts:

~~~java
StepVerifier.create(Mono.just("ok"))
    .expectNext("ok")
    .verifyComplete();

StepVerifier.create(Mono.error(
        new IllegalStateException("failure")
    ))
    .verifyError(IllegalStateException.class);
~~~

Shortcuts like `verifyComplete()` and `verifyError(...)` are concise. In integration tests with real I/O, specify a **timeout on `verify`**:

~~~java
StepVerifier.create(redis.opsForValue().get("cache:product:v1:p-1"))
    .expectSubscription()
    .expectNext("Keyboard")
    .expectComplete()
    .verify(Duration.ofSeconds(8));
~~~

`verify(Duration)` bounds **how long the test waits for the publisher to finish**. It does not configure Lettuce's Redis command timeout and does not cancel side effects already executed by Redis prior to timing out.

Comparing three deadlines:

| Deadline | Where Configured | Meaning |
| --- | --- | --- |
| Redis driver command timeout | Lettuce/Spring Redis client configuration | Driver bounds wait time for command replies |
| Reactor `timeout(Duration)` | Operator in publisher | Pipeline emits timeout if upstream stays silent past deadline |
| `StepVerifier` `verify(Duration)` | Test | Test stops waiting if the scenario fails to finish on time |

Never pick artificially tiny timeouts just to “make tests run faster” if they cause random CI failures under load. When testing timeouts intentionally, use dedicated tests with fault injection or `VirtualTimeScheduler` at the Reactor layer.

## 10. Virtual Time: Testing Reactor Time Without Waiting in Real Time

Operators like `Mono.delay`, `Flux.interval`, `delayElements`, `timeout`, and `retryWhen(Retry.backoff(...))` depend on time. Running them in real time makes unit tests slow and flaky.

`StepVerifier.withVirtualTime(...)` swaps in a virtual-time scheduler controlling operators **backed by a compatible Reactor scheduler**. A test can simulate two minutes passing almost instantaneously.

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class VirtualTimeExampleTest {

    @Test
    void verifiesDelayedSignalWithoutWaitingTwoRealMinutes() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofMinutes(2))
                    .map(number -> "READY")
            )
            .expectSubscription()
            .expectNoEvent(Duration.ofMinutes(1))
            .thenAwait(Duration.ofMinutes(1))
            .expectNext("READY")
            .verifyComplete();
    }
}
~~~

Watch out for:

1. Construct the publisher **inside the supplier** passed to `withVirtualTime`, so Reactor substitutes the virtual scheduler before time operators initialize.
2. Call `expectSubscription()` before `expectNoEvent(...)`, because subscription itself is an event observed by `StepVerifier`.
3. `expectNoEvent` asserts silence for a duration; `thenAwait` advances virtual time without asserting silence.
4. Virtual time drives Reactor's scheduler, **not the Redis server's clock**.

### Never Use Virtual Time to Simulate Real Redis TTL

Suppose an application calls:

~~~java
reactiveRedis.opsForValue()
    .set("demo:key", "value", Duration.ofMinutes(5));
~~~

That five-minute TTL is managed by the **Redis server**. Calling `thenAwait(Duration.ofMinutes(5))` in `StepVerifier` virtual time will not make Redis delete the key immediately. To test real TTL, use test Redis with a short TTL, inspect `getExpire`, or poll with a real-time deadline.

Virtual time fits testing **Reactor-level retry timing, delays, and timeouts**, not pretending the Redis server fast-forwarded five minutes.

## 11. Testing Retries and Backoff

A Redis request can encounter transient connection errors. Reactor provides `retryWhen` to retry per policy, and tests should verify **subscription count**, **post-retry outcome**, and **which error types trigger retries**.

Example unit test where a source fails twice then succeeds, with 5s and 10s backoff:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class RetryExampleTest {

    @Test
    void retriesTwiceThenSucceedsUsingVirtualTime() {
        AtomicInteger subscriptions = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                        int attempt = subscriptions.incrementAndGet();
                        if (attempt < 3) {
                            return Mono.<String>error(
                                new IOException("temporary")
                            );
                        }
                        return Mono.just("recovered");
                    })
                    .retryWhen(
                        Retry.backoff(2, Duration.ofSeconds(5))
                            .jitter(0.0)
                    )
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(16))
            .expectNext("recovered")
            .verifyComplete();

        assertThat(subscriptions.get()).isEqualTo(3);
    }
}
~~~

`Retry.backoff(2, ...)` allows up to **two retries after the initial attempt**. Here `jitter(0.0)` keeps retry timing deterministic in the unit test; in production, jitter helps prevent synchronized retry storms across instances.

### Do Not Retry Every Redis Operation

`GET` may be safely retried up to a limit per business rules, whereas `INCR` or `XADD` might already have executed on the server before the reply was lost. Retrying then runs the side effect again:

~~~text
Client sends INCR counter
          |
          v
Redis increments counter
          |
          v
Reply lost → client times out
          |
          v
retryWhen → sends INCR again
          |
          v
Counter incremented twice
~~~

`StepVerifier` proves the publisher **resubscribed** and emitted the scripted outcome. It does not prove retrying a business operation is safe; that requires idempotency, data constraints, or reconciliation.

### Testing Retry Filters

~~~java
Mono<String> invalidPayload = Mono.<String>error(
        new IllegalArgumentException("invalid payload")
    )
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(100))
            .filter(error ->
                error instanceof java.io.IOException
            )
    );

StepVerifier.create(invalidPayload)
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Because `IllegalArgumentException` fails the filter, the pipeline propagates the error immediately without retrying. With Redis, base filters on exception types/causes after verifying how Spring Data Redis translates exceptions.

## 12. Testing `Mono.timeout` Differs from Redis Command Timeouts

Suppose an async step never emits a value or completes:

~~~java
Mono<String> neverResponds = Mono.<String>never()
    .timeout(Duration.ofSeconds(3));
~~~

Testing with virtual time:

~~~java
@Test
void timeoutAfterThreeVirtualSeconds() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofSeconds(3))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify();
}
~~~

This confirms Reactor's `timeout` operator emits an error after the wait window. It is **not** a test of Lettuce's `RedisCommandTimeoutException`, because no Redis command runs in this publisher.

In real-Redis integration tests, if your goal is exercising driver command timeouts, use a controlled environment injecting network latency or connection failures rather than relying on `Mono.never()`.

## 13. Testing `Flux` Ordering and Concurrency

When a service takes a list of IDs and queries Redis for each, operator choice determines emission order:

~~~java
Flux<String> concurrent = Flux.just("a", "b", "c")
    .flatMap(id -> redis.opsForValue().get("cache:item:" + id));

Flux<String> ordered = Flux.just("a", "b", "c")
    .concatMap(id -> redis.opsForValue().get("cache:item:" + id));
~~~

`flatMap` subscribes to multiple Redis publishers concurrently and merges results as they arrive. `concatMap` awaits completion of each inner publisher before subscribing to the next, preserving **order across inner publishers in the pipeline**.

### Testing Ordered Execution

~~~java
@Test
void concatMapPreservesOrder() {
    Flux<String> result = Flux.just("first", "second")
        .concatMap(name ->
            Mono.delay(Duration.ofMillis(
                    "first".equals(name) ? 200 : 10
                ))
                .map(ignored -> name)
        );

    StepVerifier.withVirtualTime(() -> result)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("first", "second")
        .verifyComplete();
}
~~~

With virtual time, the safer practice is **building the entire pipeline inside the `withVirtualTime` supplier**, rather than referencing a pre-built publisher that may already capture a scheduler:

~~~java
@Test
void concatMapOrderWithPublisherCreatedInsideSupplier() {
    StepVerifier.withVirtualTime(() ->
            Flux.just("first", "second")
                .concatMap(name ->
                    Mono.delay(Duration.ofMillis(
                            "first".equals(name) ? 200 : 10
                        ))
                        .map(ignored -> name)
                )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("first", "second")
        .verifyComplete();
}
~~~

The second snippet is the recommended pattern for Reactor virtual-time tests. It verifies emission order within one pipeline; it does not prevent multiple service instances from concurrently writing the same Redis key.

### Testing `flatMap` Without Depending on Non-Deterministic Order

If an operation reads multiple independent Redis keys and order is not part of the contract, avoid writing:

~~~java
StepVerifier.create(unorderedValues)
    .expectNext("a", "b", "c") // Flaky if flatMap runs concurrently.
    .verifyComplete();
~~~

A better way to assert the set of values:

~~~java
import java.util.ArrayList;
import java.util.List;

Flux<String> result = Flux.just("a", "b", "c")
    .flatMap(Mono::just);

StepVerifier.create(result)
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(values ->
        assertThat(values).containsExactlyInAnyOrder("a", "b", "c")
    )
    .verifyComplete();
~~~

`recordWith` collects `onNext` items so `consumeRecordedWith` can inspect them afterward. This fits whenever **set contents**, not order, is the guarantee.

However, if a `Flux` can be very large or unbounded, do not buffer everything in memory with `recordWith`. Use `take(n)`, predicates, or bounded samples per business contract.

## 14. Integration Test with a Redis Set `Flux`: Unordered Results

A Redis Set provides no order guarantee. Reactive Spring Data Redis streams members as a `Flux`, making it ideal for demonstrating **order-agnostic assertions**.

Test method inside an integration test with `ReactiveStringRedisTemplate redis`:

~~~java
@Test
void setMembersContainExpectedValuesInAnyOrder() {
    String key = "it:tags:" + java.util.UUID.randomUUID();

    Flux<String> workflow = redis.opsForSet()
        .add(key, "redis", "reactor", "spring")
        .thenMany(redis.opsForSet().members(key));

    try {
        StepVerifier.create(workflow)
            .recordWith(java.util.ArrayList::new)
            .expectNextCount(3)
            .consumeRecordedWith(values ->
                assertThat(values).containsExactlyInAnyOrder(
                    "redis", "reactor", "spring"
                )
            )
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    } finally {
        StepVerifier.create(redis.delete(key))
            .expectNextCount(1)
            .expectComplete()
            .verify(Duration.ofSeconds(8));
    }
}
~~~

`opsForSet().add(...)` returns a `Mono<Long>` representing newly added members. `thenMany(...)` waits for the add to finish before subscribing to `members`. The test records all three items and asserts them without relying on order.

For a Redis Set, `expectNext("redis", "reactor", "spring")` violates the contract: even if repeated runs happen to emit that order, Redis makes no stability guarantee across versions or mutations.

If business logic genuinely requires order, use an ordered Redis structure and pipeline—such as a Sorted Set by score—or sort bounded results in the application.

## 15. Backpressure and `thenRequest` in `StepVerifier`

Reactive Streams lets subscribers control item flow through demand. `StepVerifier` supports starting a subscription with a configured **initial request** and requesting more items interactively.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

class DemandTest {

    @Test
    void checksRequestDemandStepByStep() {
        Flux<Integer> source = Flux.range(1, 3);

        StepVerifier.create(
                source,
                StepVerifierOptions.create().initialRequest(0)
            )
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

The test starts with demand 0, requests one item, then requests two more. It verifies the publisher emits only the requested items.

**Backpressure does not make Redis roll back commands or block all already-sent I/O.** Drivers/publishers may have already issued commands or buffered server responses before downstream requests more, depending on implementation. `StepVerifier` tests Reactive Streams semantics at the publisher boundary, not exact socket-level byte timing.

When querying many keys:

~~~java
Flux<String> values = Flux.fromIterable(productIds)
    .flatMap(id ->
        redis.opsForValue().get("cache:product:v1:" + id),
        8
    );
~~~

The `8` limits inner publisher concurrency inside `flatMap`. It throttles per-pipeline concurrency, yet is not a global cap across Redis or databases for the whole app. Under many concurrent HTTP requests, total operations can still surge.

## 16. Testing Cancellation for Long-Lived Streams

Some reactive publishers emit indefinitely—such as event streams, Pub/Sub, or polling `Flux`es. They **never complete naturally**. Writing `verifyComplete()` will hang forever.

For long-lived streams, verify a few signals and then **cancel the subscription**:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void cancellationTerminatesTheSubscription() {
    AtomicBoolean canceled = new AtomicBoolean(false);

    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofSeconds(1))
                .doOnCancel(() -> canceled.set(true))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .thenCancel()
        .verify();

    assertThat(canceled.get()).isTrue();
}
~~~

This confirms the subscriber sent a cancel signal and `doOnCancel` executed. When wired to a real Redis source, also verify the API/client frees subscriptions and connections on cancel.

For Redis Pub/Sub or Redis Streams, canceling a reactive subscription **does not change Redis delivery guarantees**:

- Pub/Sub does not save messages published while the subscriber is disconnected.
- Redis Streams may retain entries in the Stream/PEL depending on consumer group and ACK policy.
- Canceling a subscription never rolls back prior side effects.

### Testing Redis Pub/Sub Must Not Publish Too Early

If a test starts a subscriber and immediately calls `PUBLISH`, the subscriber may not have finished channel registration on Redis. Losing the first message makes tests fail randomly even when subscriber code is fine.

A test scenario can use:

1. A dedicated channel with a UUID.
2. Readiness confirmation or retrying a test probe until a callback arrives within a bounded deadline.
3. `StepVerifier` asserting the expected message payload.
4. `thenCancel()` to terminate the subscription.
5. Framework-appropriate cleanup of listeners/containers.

Never treat republishing a test probe as a retry policy for non-idempotent business events; it is strictly a **test readiness synchronization technique**, not a durable message broker replacement.

## 17. Checking Fallback Branches with `PublisherProbe`

Sometimes a test must prove **whether a fallback publisher was subscribed to**, not just that the final value matched.

`PublisherProbe` from `reactor-test` observes subscriptions, requests, and cancellations on a pipeline branch.

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class FallbackProbeTest {

    @Test
    void subscribesFallbackWhenCacheIsEmpty() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("from-database"));

        Mono<String> result = Mono.<String>empty()
            .switchIfEmpty(database.mono());

        StepVerifier.create(result)
            .expectNext("from-database")
            .verifyComplete();

        database.assertWasSubscribed();
        database.assertWasRequested();
    }

    @Test
    void doesNotSubscribeFallbackOnCacheHit() {
        PublisherProbe<String> database =
            PublisherProbe.of(Mono.just("from-database"));

        Mono<String> result = Mono.just("from-redis")
            .switchIfEmpty(database.mono());

        StepVerifier.create(result)
            .expectNext("from-redis")
            .verifyComplete();

        database.assertWasNotSubscribed();
    }
}
~~~

`PublisherProbe` excels at proving **which branch actually executed**. If Redis and the database happen to return the exact same value, `expectNext("value")` alone cannot distinguish a hit from a fallback.

### Using `TestPublisher` to Drive Signal Timing Explicitly

Operator tests may need to emit signals step by step without touching Redis networking:

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().map(String::trim))
    .then(() -> source.next("  first  "))
    .expectNext("first")
    .then(source::complete)
    .verifyComplete();
~~~

`TestPublisher` gives fine-grained control over `onNext`/`onComplete` in unit tests. It does not test how real Redis dispatches messages, routes keys, or handles network timeouts; those belong in integration/fault-injection tests.

## 18. Testing Error Policies in Redis Services

Real systems attach explicit policies to Redis failures: best-effort caches may fall back to the authoritative source; Redis Streams may leave events unACKed; distributed locks must reject work when ownership is uncertain. `StepVerifier` verifies those policies cleanly.

Example cache policy falling back only on connection failures:

~~~java
package com.example.redis.testing;

import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;

public final class CacheFallbackPolicy {

    public Mono<String> getOrFallback(
            Mono<String> redisValue,
            Mono<String> sourceValue) {
        return redisValue
            .onErrorResume(
                RedisConnectionFailureException.class,
                error -> sourceValue
            )
            .switchIfEmpty(sourceValue);
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class CacheFallbackPolicyTest {

    private final CacheFallbackPolicy policy =
        new CacheFallbackPolicy();

    @Test
    void fallsBackWhenRedisIsUnavailable() {
        PublisherProbe<String> source =
            PublisherProbe.of(Mono.just("database-value"));

        Mono<String> failed = Mono.error(
            new RedisConnectionFailureException(
                "connection unavailable"
            )
        );

        StepVerifier.create(
                policy.getOrFallback(failed, source.mono())
            )
            .expectNext("database-value")
            .verifyComplete();

        source.assertWasSubscribed();
    }

    @Test
    void propagatesBusinessErrorRatherThanMaskingIt() {
        PublisherProbe<String> source =
            PublisherProbe.of(Mono.just("database-value"));

        Mono<String> failed = Mono.error(
            new IllegalArgumentException("invalid product ID")
        );

        StepVerifier.create(
                policy.getOrFallback(failed, source.mono())
            )
            .expectError(IllegalArgumentException.class)
            .verify();

        source.assertWasNotSubscribed();
    }
}
~~~

On `RedisConnectionFailureException`, the service falls back. On `IllegalArgumentException` from bad business input, it propagates the error rather than hiding it as a fake cache miss. `PublisherProbe` confirms whether the database branch was subscribed.

In production, you may also need to catch command timeouts after Spring Data Redis exception translation. Still, **never fall back unconditionally on every exception**: when Redis holds consistency-critical data, falling back can be unsafe.

### Serializer Errors Differ from Missing Keys

A normal cache miss completes empty:

~~~java
Mono<String> absent = Mono.empty();
~~~

Deserialization failures emit `onError`:

~~~java
Mono<String> corrupted = Mono.error(
    new org.springframework.data.redis.serializer.SerializationException(
        "cannot decode cached value"
    )
);
~~~

Test both separately. If a service runs `onErrorResume(error -> Mono.empty())` on all errors, incompatible JSON payloads get hidden indefinitely behind what looks like elevated cache misses.

## 19. Testing Real Connection Errors and Timeouts with Fault Injection

Mocks prove the app's exception policy; they **cannot prove the real client emits that exact exception when the network breaks**. To exercise driver-level error paths, build a controlled integration setup:

- A real Redis Testcontainer.
- A network proxy/fault injector like Toxiproxy to inject latency, blackouts, or connection resets.
- Lettuce/Spring Data Redis timeouts tuned for the scenario.
- A finite `StepVerifier` deadline so tests never hang.
- Non-sensitive test keys and payloads.

Example flow:

~~~text
Test setup:
  Spring reactive Redis client → network proxy → Redis test container
                    |
                    v
              Healthy Redis
                    |
                    v
         StepVerifier asserts GET succeeds
                    |
                    v
        Fault injector cuts connection
                    |
                    v
           Controlled GET / SET call
                    |
                    v
         StepVerifier checks error/fallback
                    |
                    v
           Restore network proxy
                    |
                    v
       Poll/verify Redis client recovers
~~~

**Never induce Redis command timeouts on a production server just to run tests.** Fault injection requires isolated test Redis, cleanup, and bounded durations. A timed-out write may already have executed: reconcile real keys/counters before drawing side-effect conclusions rather than assuming “nothing was written” simply because `StepVerifier` observed `onError`.

### `StepVerifier` Does Not Simulate Redis

| What Needs Testing | Appropriate Tool |
| --- | --- |
| `Mono` value, empty, error, completion | `StepVerifier` + publisher unit tests |
| `Flux` ordering, cancellation, backpressure | `StepVerifier`, `TestPublisher`, `PublisherProbe` |
| Backoff/delay/timeout driven by Reactor schedulers | `StepVerifier.withVirtualTime` |
| Real server `SET`/`GET`/`SADD` and TTL | Spring Data Redis + Redis Testcontainers |
| Serializers on real Redis payloads | Integration tests with real serializers and test Redis |
| DNS errors, connection resets, driver timeouts | Fault injection over test network infrastructure |
| Redis Sentinel failover, Cluster redirects | Dedicated multi-node Redis topology tests |
| Duplicate-free business side effects on retry | Integration tests against authoritative DB with idempotency |

`StepVerifier` excels at verifying **publisher contracts**, yet it cannot by itself verify data durability, Redis Cluster consistency, or multi-system business safety.

## 20. Common Causes of Flaky Tests

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Test intermittently gets empty right after `save` | `save` created a `Mono` without subscribing | Compose `save.then(load)` in one publisher |
| Test runs long or never exits | Unbounded `Flux` with no `onComplete` | Use `thenCancel()` or bound expected count |
| `expectNext(a,b,c)` fails sporadically | `flatMap` or unordered Redis Set | Use `concatMap` if order matters; otherwise assert unordered |
| TTL test fails under virtual time | TTL runs on Redis server, not Reactor scheduler | Inspect `getExpire` or use real test Redis with short TTL |
| Test hangs when Redis is down | Missing `verify` deadline | Use `expectComplete().verify(Duration)` and driver timeouts |
| Virtual-time test still waits in real time | Publisher built outside `withVirtualTime` or non-virtual scheduler | Build pipeline inside supplier; check schedulers |
| Test runs twice and counter increments twice | Cold publisher subscribed multiple times | Subscribe intentionally once; check side effects |
| Assertion expects remaining TTL == exact original TTL | Time passed between `SET` and `getExpire` | Assert positive range with tolerance |
| Pub/Sub test drops first message | Subscriber not yet finished registering | Synchronize readiness before publishing or poll probe with timeout |
| Test fails due to key overwritten by sibling | Fixed shared key across parallel tests | Use UUID/prefix keys and per-key cleanup |
| Test occasionally times out in CI | Tight deadline vs. network/container startup | Use realistic timeouts and investigate slowness |
| `assertNext` is never called | Upstream completed empty | Use `switchIfEmpty` if fallback needed; test empty explicitly |
| Serializer error treated as miss | `onErrorResume` swallows everything | Fall back only on policy-approved exceptions |
| Mocked unit tests pass, production fails | Mocks skipped serialization, networking, real semantics | Add integration tests against real Redis |
| `then` runs next step even when `SET` returned `false` | `then` ignores `Boolean` and awaits completion | Filter/check `Boolean.TRUE` before `then` |
| Retry increments `INCR` twice | Test checked only final reply, not side effects | Design idempotency and verify final state |

### Especially Avoid `Thread.sleep` to Synchronize Tests

A test like:

~~~java
publisher.subscribe(value -> received.set(value));
Thread.sleep(200);
assertThat(received.get()).isEqualTo("value");
~~~

gives no guarantee when the callback executes. It may pass on a fast laptop and fail on loaded CI. Moreover, manual `subscribe()` with concurrent reads demands careful visibility and lifecycle handling.

When the publisher has a finite terminal signal, use:

~~~java
StepVerifier.create(publisher)
    .expectNext("value")
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

When the publisher emits with Reactor-managed delays, use virtual time. When waiting for a real Redis server to recover after a fault, poll with a timeout on an **observable condition**, never a single blind sleep.

## 21. Define Test Goals Before Writing Assertions

Good tests start by asking **what the business logic or publisher contract must guarantee**:

| Test Question | Recommended Assertion |
| --- | --- |
| Does Redis read return the right value? | `expectNext(expected).expectComplete()` |
| What happens when the key is missing? | `verifyComplete()` or `switchIfEmpty` + `expectNext(fallback)` |
| Are Redis errors masked as success? | `expectError(...)` or `expectErrorMatches(...)` |
| Did write finish before read? | Single `save().then(load())` pipeline with `StepVerifier` |
| Did Redis actually attach TTL? | Integration test `getExpire(key)` checking valid range |
| Are all Redis Set items present? | `recordWith` + `containsExactlyInAnyOrder` |
| Does cache hit avoid touching the DB? | `PublisherProbe.assertWasNotSubscribed()` |
| Does service fall back on matching Redis errors? | Signal assertions + `PublisherProbe.assertWasSubscribed()` |
| How many times did it retry? | Counter inside `Mono.defer` + virtual time |
| Can an infinite stream be canceled? | `thenCancel()` and `doOnCancel` callback |
| Does the publisher honor demand? | `StepVerifierOptions.initialRequest(0)` + `thenRequest` |
| Does client reconnect after failover? | Topology integration test, not mocked `Mono`s |

Crucially, `StepVerifier` executes nothing simply by building expectations. **You must call a verify terminator**: `verify()`, `verifyComplete()`, `verifyError(...)`, or a timeout variant.

## 22. Suggested Testing Workflow in a Spring Data Redis Project

A maintainable workflow divides into four tiers:

1. **Operator unit tests:** use `Mono.just`, `Mono.empty`, `Mono.error`, `Flux.just`, and `StepVerifier`. Verify `map`, `flatMap`, `concatMap`, `then`, empty, error, and cancellation.
2. **Service unit tests:** mock reactive Redis operations or use `PublisherProbe` to verify fallback policies, retries, subscription order, and `Boolean` command checks.
3. **Redis integration tests:** use Testcontainers, isolated keys, Spring Boot context, and `StepVerifier`; verify real values, Redis Sets, TTL, serializers, and cleanup.
4. **Resilience tests:** real network faults and failovers in isolated infrastructure, reconciling state when writes may have succeeded prior to timeouts.

Example CI flow:

~~~text
       Reactive Redis code change
                    |
                    v
             JUnit unit tests
             StepVerifier + mocks
                    |
                    v
          Reactor virtual-time tests
              Retry / timeout
                    |
                    v
           Redis integration tests
              Testcontainers
                    |
                    v
            Fault-injection tests
         (when dedicated infra exists)
                    |
                    v
          Observe and reconcile results
~~~

Not every pull request has to run an expensive multi-node failover topology if resources are constrained, yet critical reliability paths should run regularly in realistic simulation environments.

## 23. Summary

**`StepVerifier` is the core tool for testing `Mono` and `Flux` signals in reactive Spring Data Redis.** Instead of calling `block()` to extract one value and ignoring everything else, `StepVerifier` declares what a publisher must emit and how it must terminate:

- `expectNext`, `assertNext`, and `expectNextMatches` check emitted values.
- `verifyComplete` and `expectComplete` check normal completion.
- `expectError` checks errors instead of hiding them as cache misses.
- `recordWith` and `consumeRecordedWith` verify unordered `Flux` results.
- `thenRequest` and `thenCancel` verify backpressure demand and cancellation.
- `withVirtualTime` tests Reactor delays, timeouts, and backoff without waiting in real time.
- `PublisherProbe` and `TestPublisher` verify fallback subscription paths and inject deterministic test signals.

When paired with **Redis Testcontainers**, `StepVerifier` also verifies writes, reads, TTL, and reactive Spring Data Redis APIs against real data. Keep in mind that virtual time never expires keys on a Redis server, a timeout never proves a command failed to execute, and mocked unit tests never test real networking, serialization, or failover.

Most important principle: **verify the exact publisher contract without assuming ordering or timing guarantees the API never made; use real Redis when proving Redis behavior, and test idempotency separately wherever side effects occur.** That keeps reactive flows clear, stable, and faithful to business requirements.
