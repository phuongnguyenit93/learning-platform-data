# Testing MeterRegistry and Verifying Counters, Timers, and Tags

## 1. Context in the Events and Observability Group

A Spring Boot application can execute business logic properly while emitting **wrong metrics**. For instance, a failed checkout payment gets added to a counter tagged `result=success`; a timer is never stopped on an exception; an `orderId` tag spawns millions of series; or a test uses its own `SimpleMeterRegistry` and falsely assumes it tested the registry injected by Spring Boot. These bugs do not necessarily fail business tests, yet they make dashboards, alerts, and incident investigations untrustworthy.

Under **Testing MeterRegistry and Verifying Counters, Timers, and Tags**, separate three questions:

1. **Did instrumentation run?** Does the service increment counters, record timers, and maintain accurate outcome tags on both success and failure?
2. **Was the right meter updated?** Are the name, meter type, tag names/values, time unit, and sample count right?
3. **Which registry is being used?** A unit test using a dedicated in-memory registry differs from a Spring Boot integration test using the real `MeterRegistry` bean, which in turn differs from verifying a Prometheus/Datadog exporter over the network.

This lesson uses **Java 17, Spring Boot 3.3.0, Micrometer via Actuator, and JUnit 5**. The project contains complete source and test classes: unit tests with `SimpleMeterRegistry` and `MockClock`, plus a Spring Boot test verifying wiring. JUnit results stated below are **expected**, not a claim that Gradle was executed during authoring.

## 2. Learning Objectives

After this lesson, you will be able to:

- Create a `SimpleMeterRegistry` for unit tests without relying on static `Metrics.globalRegistry`.
- Distinguish `Counter`, `Timer`, `Gauge`, `DistributionSummary`, and `ObservationRegistry`.
- Understand that Counters only increase, while Timers record sample counts and total duration.
- Use `Timer.Sample` to measure duration with a `result` tag determined after the operation finishes.
- Use `Timer.record(Duration)` and `MockClock` to assert durations deterministically.
- Look up the exact meter by name and tags via `registry.find(name).tag(key,value)`.
- Separate `outcome=success` and `outcome=error` into two independent series.
- Design tests verifying counters/timers increment on exceptions as well as successes without double-counting.
- Check tag cardinality; avoid order ID, user ID, request ID, raw URL, and exception messages.
- Isolate metrics across JUnit methods without calling `clear()` on a shared registry.
- Test Spring Boot `@SpringBootTest` with the real `MeterRegistry` bean and before/after deltas.
- Understand fallback `SimpleMeterRegistry` and differences in test auto-configuration/exporters.
- Know that `@Timed` does not auto-instrument arbitrary methods merely because the Actuator dependency is present.
- Understand Prometheus naming, time units, histograms/percentiles, and step registries.
- Know when to test exporters, HTTP Actuator endpoints, Observations, and reactive pipelines.
- Diagnose common pitfalls: wrong tag lookup, wrong registry, TestContext cache, missing timer sample stop, and broken async timing.
- Never treat a passing unit metrics test as proof that the production monitoring pipeline is operational.

## 3. Micrometer MeterRegistry Model

```text
CheckoutService
    |
    +--> checkout.requests{result="success"} : Counter
    +--> checkout.requests{result="error"}   : Counter
    +--> checkout.duration{result="success"} : Timer
    +--> checkout.duration{result="error"}   : Timer
    |
    v
MeterRegistry (Micrometer facade)
    |
    +--> SimpleMeterRegistry (memory; unit tests)
    +--> CompositeMeterRegistry (delegates)
    +--> PrometheusMeterRegistry (scrape)
    +--> Datadog/Statsd/... (push/periodic)
    |
    v
Metrics backend -> dashboards/alerts
```

**A Micrometer registry is not a monitoring backend**. `SimpleMeterRegistry` holds meter values in the JVM without sending HTTP metrics to another server. `@SpringBootTest` can supply an in-memory registry, yet does not enable external exporters by default.

For production applications, inject `MeterRegistry` into the service:

```java
@Service
public class CheckoutService {
    private final MeterRegistry registry;

    public CheckoutService(MeterRegistry registry) {
        this.registry = registry;
    }
}
```

This is a **conceptual declaration snippet** without the business method; the full class is in Section 12. Spring Boot applies meter customizers, common tags, and filters to the Spring-managed registry; that is why constructor injection is preferred over calling static `Metrics.counter(...)`.

## 4. Counter: Counting Monotonically Increasing Events

`Counter` records how many times an event occurred. It is unsuitable for “current queue depth” or “open connection count”, because state values can decrease.

```java
registry.counter(
        "checkout.requests",
        "result", "success").increment();
```

Equivalent builder with description/tag:

```java
Counter.builder("checkout.requests")
        .description("Checkout attempts")
        .tag("result", "success")
        .register(registry)
        .increment();
```

When called three times on the same meter ID:

```java
Counter c = registry.counter(
        "checkout.requests",
        "result", "success");

c.increment();
c.increment();
c.increment();

assertEquals(3.0, c.count(), 0.000001);
```

Tests must create a fresh registry or measure deltas. On a registry reused across tests, `count()` can start from a non-zero value.

### 4.1. Counter vs. Gauge

- `Counter`: total checkout attempts since the series/registry started.
- `Gauge`: current state such as in-flight requests or queue depth, which can rise and fall.
- `DistributionSummary`: distribution of values like payload size or order amount (not elapsed duration).
- `Timer`: invocation count and duration of operations; ideal for latency.

Never try to decrement a Counter with `increment(-1)`; that violates Counter semantics and may be rejected or unsupported by providers.

### 4.2. Counting Logical Requests vs. Physical Retries

One checkout might call the payment gateway three times due to retries. If your counter increments per network attempt, “3” does not mean 3 orders. Names and descriptions must be explicit:

- `checkout.requests`: per logical checkout invocation.
- `payment.gateway.attempts`: per outbound attempt.
- `checkout.retries`: number of retries.

Timer count can measure per attempt or whole request; never merge metrics of different scopes into one request count.

## 5. Timer: Count, Total Time, and Max

`Timer` specifically tracks durations. Common APIs:

- `timer.record(Duration.ofMillis(100))` records a sample.
- `timer.count()` returns the sample count.
- `timer.totalTime(TimeUnit.MILLISECONDS)` returns total duration.
- `timer.max(TimeUnit.MILLISECONDS)` returns max per implementation and time window.
- `Timer.Sample.start(registry)` starts a stopwatch and `stop(timer)` records into the target series.

Deterministic example:

```java
Timer timer = Timer.builder("checkout.synthetic.duration")
        .tag("scenario", "unit")
        .register(registry);

timer.record(Duration.ofMillis(120));
timer.record(Duration.ofMillis(80));

assertEquals(2L, timer.count());
assertEquals(
        200.0,
        timer.totalTime(TimeUnit.MILLISECONDS),
        0.000001);
```

In `TimeUnit.SECONDS`, the corresponding total is 0.2 seconds. Prometheus exporters typically export in seconds; Micrometer APIs require an explicit `TimeUnit` when reading timer values. Never compare 200 milliseconds against 200 seconds.

### 5.1. Timers Have Their Own Count

Conceptually, every `Timer` records both count and totalTime. If a checkout always records one sample, that count also reflects the number of measured invocations. A separate Counter is only worthwhile when you need an event count with distinct semantics or a dashboard/query contract requires it—not simply to duplicate total traffic.

### 5.2. max Is Not All-Time Max

Many timers use a **time-window max**: after an interval without samples, max can reset/roll over depending on the registry. A unit test can assert max right after recording durations, yet must not expect a historical max to persist indefinitely. For long-lived max or p95, design appropriate backend/queries and histograms.

### 5.3. Never Use Timer for Negative Values

Timers only accept non-negative durations. When measuring balance fluctuations, latencies cannot be negative, whereas account deltas can; pick an appropriate meter type.

## 6. Timer.Sample on Success and Error Paths

Use `Timer.Sample` when the outcome is only known after the operation finishes:

```java
Timer.Sample sample = Timer.start(registry);
String result = "success";

try {
    return gatewayCall();
}
catch (RuntimeException e) {
    result = "error";
    throw e;
}
finally {
    sample.stop(
            Timer.builder("checkout.duration")
                    .tag("result", result)
                    .register(registry));
}
```

**Snippet**: `gatewayCall()` and `registry` are defined in the runnable service below. `finally` records the count/timer on the error path while letting the business exception propagate. Stopping in both `catch` and `finally` would record the timer **twice**. Follow the pattern: start once, stop once.

### 6.1. Timer.Sample Measures Real Elapsed Time

`Timer.start(registry)` reads the registry's clock. When the gateway operation is fast, the sample duration can be tiny; asserting exact milliseconds based on runtime scheduling is flaky. To test timer semantics deterministically, use `MockClock` as in Section 7.

### 6.2. Async/Reactive Differs from Synchronous finally

If a method only *assembles* a `Mono` or `CompletableFuture`, a synchronous `finally` runs before the async work executes. To measure end-to-end publisher latency, start/stop around **subscription/termination** (`doFinally`/Observation) rather than assembly alone. The main lab uses synchronous methods so assertions stay unambiguous.

## 7. MockClock: Testing Exact Durations Without Sleep

`MockClock` is a test-friendly Micrometer API controlling a registry's `monotonicTime`. With `SimpleMeterRegistry(SimpleConfig.DEFAULT, clock)`:

```java
MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(
                SimpleConfig.DEFAULT, clock);

Timer timer = registry.timer("demo.duration");

Timer.Sample sample = Timer.start(registry);
clock.add(Duration.ofMillis(125));
sample.stop(timer);

assertEquals(1L, timer.count());
assertEquals(
        125.0,
        timer.totalTime(TimeUnit.MILLISECONDS),
        0.000001);

registry.close();
```

This is a deterministic test: the clock advances by a predetermined duration without `Thread.sleep(125)`. It does not benchmark throughput or real CPU speed; it solely proves `Timer.Sample` and the registry record durations properly.

### 7.1. Why Not Assert Real Elapsed Time in Exact Nanoseconds?

JIT, GC, schedulers, CPU quotas, system clock resolution, and CI load all vary. Anti-pattern example:

```java
long start = System.nanoTime();
service.checkout("A");
long elapsed = System.nanoTime() - start;

assertEquals(5_000_000L, elapsed); // flakey
```

Business metrics unit tests should assert meter counts and outcome tags; synthetic tests verify exact duration math; benchmarks/performance tests follow a separate methodology.

### 7.2. MockClock vs. Fake Business Clock

Micrometer `MockClock` drives `Timer.Sample` and registries, separate from `java.time.Clock` in business code. Swapping a business clock does not automatically alter Micrometer's monotonic time. When testing business deadlines/TTLs, inject the appropriate clock at that layer.

## 8. Tags: Series Identity

These two counters are distinct because their tag values differ:

```text
checkout.requests{result="success"} = 5
checkout.requests{result="error"}   = 2
```

In Micrometer, looking up by name + tags creates or retrieves a specific series. To read them:

```java
Counter success = registry.find("checkout.requests")
        .tag("result", "success")
        .counter();

Counter error = registry.find("checkout.requests")
        .tag("result", "error")
        .counter();
```

In tests, call `assertNotNull(success)` before `success.count()`. If a tag key drifts from `result` to `outcome`, the test must fail loudly instead of silently reading the wrong meter by name.

### 8.1. Tag Names and Values Must Be Stable

Standardize `result=success|error` with a fixed enum/constant set; never create both `succes` and `success`, splitting metrics into two series. If the system supports `success`, `rejected`, and `timeout` outcomes, document the contract and avoid using raw exception messages as labels.

### 8.2. Tag Ordering

Tag sets with identical key-value pairs in different orders represent the same logical identity. Do not write unit tests depending on string serialization order of tags unless it is an explicit exporter contract. Use `meter.getId().getTag("result")` to inspect specific tags.

### 8.3. Meter Name Alone Is Insufficient When Multiple Series Exist

`registry.find("checkout.requests").counter()` is ambiguous when multiple tag values exist. Always specify `.tag("result","success")` or `get(name).tags(...)`. For negative assertions, `find` returns null when no matching series is registered.

### 8.4. Common Tags

Spring Boot can add common tags like `application` and `environment` via `MeterRegistryCustomizer` and `MeterFilter`. Business tests can query by required tags rather than asserting the entire tag set never changes. If common tags are a dashboard contract, assert them separately against a Spring-managed registry.

## 9. Tag Cardinality: The Most Important Principle

Good tags draw from a bounded set of values, such as:

- `result=success|error`.
- `method=GET|POST`.
- `operation=checkout|refund`.
- `status=2xx|4xx|5xx`.
- `payment_method=card|bank_transfer|wallet` when bounded.
- HTTP `uri=/orders/{id}` as a route template.

Tags to avoid directly when they produce unbounded series:

- `orderId`, `userId`, `sessionId`, `requestId`.
- Email, phone number, raw IP, and raw user agent.
- Raw exception messages.
- Timestamps, random UUIDs, full SQL statements.
- Raw HTTP paths `/orders/1234`, full URLs with query params/IDs.

With 2 outcomes × 3 operations × 1 million order IDs, you generate millions of unique series. Registry memory and backend costs explode, yet a single-order test will miss the bug unless there is a **tag policy assertion**.

### 9.1. Unit Test Guard

In tests, inspect meter IDs:

```java
for (Meter meter : registry.getMeters()) {
    assertNull(meter.getId().getTag("orderId"));
    assertNull(meter.getId().getTag("userId"));
}
```

The runnable test suite inspects meters prefixed with `checkout.`. In large systems, audit all instrumentation and use `MeterFilter.maximumAllowableTags(...)` as an extra safeguard.

### 9.2. Logs/Traces Are for Request Identity

When tracing a specific order, use structured logs or traces carrying IDs rather than creating a separate metric series. Metrics serve aggregate signals and alerting; tracing/logging serve per-request investigation. Exemplars can bridge them without creating per-request labels.

## 10. Isolation Across JUnit Tests

A common cause of flaky tests is a registry persisting across methods:

```java
@BeforeEach
void setUp() {
    registry = new SimpleMeterRegistry();
    service = new CheckoutService(
            new DemoPaymentGateway(), registry);
}

@AfterEach
void tearDown() {
    registry.close();
}
```

Each method starts with an empty registry. `close()` releases resources without touching any global registry. Never keep a static registry in `@BeforeAll` if tests assert counts starting at 0.

### 10.1. Why Not Call clear() on the Spring Boot Registry?

`MeterRegistry.clear()` removes all registered meters. In a shared Spring-managed registry, JVM/process instrumentation or other beans may hold references to old meters. After clearing, results become unpredictable and other tests break.

Recommended practice:

- **Unit:** fresh registry per test.
- **Integration:** measure **baseline before** and assert the delta after the service runs.
- **Isolated context:** reset contexts only when truly necessary, factoring in cost and metric listeners.
- **Parallel tests:** avoid having multiple methods update the same meter series on a shared registry if asserting exact deltas.

### 10.2. Metrics.globalRegistry Is Global State

`Metrics.globalRegistry` is a static composite registry. If test A attaches a backend and test B omits removing it, counts can leak across tests. Constructor-inject `MeterRegistry` rather than calling static `Metrics.counter(...)` in the sample service.

### 10.3. @SpringBootTest Does Not Start with an Empty Registry

The Spring TestContext cache can reuse an ApplicationContext across classes. Spring Boot/Actuator registers numerous framework metrics, and custom meters may retain values from previous methods. Measure before/after deltas or isolate contexts; never blindly assume every counter starts at 0 without knowing the lifecycle.

## 11. Runnable Project — Directory Tree and Dependencies

```text
micrometer-test-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/metrics/
    │   ├── MetricsLabApplication.java
    │   ├── PaymentGateway.java
    │   ├── DemoPaymentGateway.java
    │   └── CheckoutService.java
    └── test/java/example/metrics/
        ├── CheckoutMetricsUnitTest.java
        └── CheckoutMetricsBootTest.java
```

### 11.1. settings.gradle

```groovy
rootProject.name = 'micrometer-test-lab'
```

### 11.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Actuator starter brings in Micrometer/metrics auto-configuration. JUnit, assertions, and Spring Boot test support come from `starter-test`. No Kafka, database, Docker, or Prometheus is needed for the core example.

### 11.3. MetricsLabApplication.java

**src/main/java/example/metrics/MetricsLabApplication.java**

```java
package example.metrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetricsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MetricsLabApplication.class, args);
    }
}
```

### 11.4. PaymentGateway.java

**src/main/java/example/metrics/PaymentGateway.java**

```java
package example.metrics;

public interface PaymentGateway {
    String pay(String orderId);
}
```

### 11.5. DemoPaymentGateway.java

**src/main/java/example/metrics/DemoPaymentGateway.java**

```java
package example.metrics;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {

    @Override
    public String pay(String orderId) {
        if (orderId.startsWith("FAIL")) {
            throw new IllegalStateException(
                    "Payment was rejected");
        }
        return "paid:" + orderId;
    }
}
```

The demo gateway makes no real payment API calls. Outcomes are controlled via `orderId` so unit/integration tests cover positive and negative branches. Never claim this verifies real payment processing.

## 12. CheckoutService.java — Counter and Timer.Sample

**src/main/java/example/metrics/CheckoutService.java**

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;
    private final MeterRegistry registry;

    public CheckoutService(
            PaymentGateway gateway,
            MeterRegistry registry) {
        this.gateway = gateway;
        this.registry = registry;
    }

    public String checkout(String orderId) {
        Timer.Sample sample = Timer.start(registry);
        String result = "success";

        try {
            return gateway.pay(orderId);
        }
        catch (RuntimeException ex) {
            result = "error";
            throw ex;
        }
        finally {
            registry.counter(
                    "checkout.requests",
                    "result", result)
                    .increment();

            sample.stop(
                    Timer.builder("checkout.duration")
                            .description(
                                    "Checkout processing latency")
                            .tag("result", result)
                            .register(registry));
        }
    }
}
```

### 12.1. Semantics of Both Metrics

- `checkout.requests{result=success}`: number of successful `service.checkout()` calls.
- `checkout.requests{result=error}`: number of `service.checkout()` calls throwing `RuntimeException`.
- `checkout.duration{result=success}`: durations of successful executions.
- `checkout.duration{result=error}`: durations of failed executions.

The timer starts before the gateway call and stops in `finally`, so the error branch is measured too. The `result` tag has only `success`/`error`; never an `orderId` tag. Never increment counters in both `catch` and `finally`: that double-counts errors.

### 12.2. A Point to Review for Production

If `gateway.pay` throws an `Error` (not a `RuntimeException`), the `catch` in the lab does not switch `result` to `error` even though `finally` still runs; the lesson chose that exception type for the demo. In production, define explicit outcome policies for Errors, cancellations, retries, validation errors, and unexpected exceptions without blindly catching all `Throwable`. Any metrics backend failure must also be isolated so instrumentation never alters business outcomes.

### 12.3. Should Counter/Timer Fields Be Cached?

For fixed tags, you can register a Counter once and store it in a field to avoid repeated lookups. Because the `result` tag is only known at the end of the operation, you can hold two fields (`successCounter` and `errorCounter`) or look up by bounded `result` in `finally` as in the lab. Lookups hit a registry hash map and are generally cheap; just never construct unbounded series from user-supplied tags.

## 13. CheckoutMetricsUnitTest.java — 9 Tests

**src/test/java/example/metrics/CheckoutMetricsUnitTest.java**

```java
package example.metrics;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CheckoutMetricsUnitTest {

    private SimpleMeterRegistry registry;
    private CheckoutService service;

    @BeforeEach
    void setUp() {
        registry = new SimpleMeterRegistry();
        service = new CheckoutService(
                new DemoPaymentGateway(), registry);
    }

    @AfterEach
    void tearDown() {
        registry.close();
    }

    private Counter counter(String result) {
        Counter counter = registry.find("checkout.requests")
                .tag("result", result)
                .counter();
        assertNotNull(counter);
        return counter;
    }

    private Timer timer(String result) {
        Timer timer = registry.find("checkout.duration")
                .tag("result", result)
                .timer();
        assertNotNull(timer);
        return timer;
    }

    @Test
    void successIncrementsCounterAndRecordsTimer() {
        assertEquals(
                "paid:ORDER-1",
                service.checkout("ORDER-1"));

        assertEquals(1.0,
                counter("success").count(),
                0.000001);
        assertEquals(1L, timer("success").count());

        assertTrue(
                timer("success")
                        .totalTime(TimeUnit.NANOSECONDS) >= 0);

        assertNull(registry.find("checkout.requests")
                .tag("result", "error").counter());
    }

    @Test
    void errorHasItsOwnCounterAndTimer() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("FAIL-1"));

        assertEquals(
                "Payment was rejected",
                failure.getMessage());
        assertEquals(1.0,
                counter("error").count(),
                0.000001);
        assertEquals(1L, timer("error").count());

        assertNull(registry.find("checkout.requests")
                .tag("result", "success").counter());
    }

    @Test
    void successAndErrorHaveSeparateTaggedSeries() {
        assertEquals("paid:A", service.checkout("A"));

        assertThrows(
                IllegalStateException.class,
                () -> service.checkout("FAIL-B"));

        assertEquals("paid:C", service.checkout("C"));

        assertEquals(2.0,
                counter("success").count(),
                0.000001);
        assertEquals(1.0,
                counter("error").count(),
                0.000001);
        assertEquals(2L, timer("success").count());
        assertEquals(1L, timer("error").count());
    }

    @Test
    void repeatedSuccessesAccumulateOnSameMeter() {
        service.checkout("A");
        service.checkout("B");
        service.checkout("C");

        assertEquals(3.0,
                counter("success").count(),
                0.000001);
        assertEquals(3L,
                timer("success").count());

        assertSame(
                registry.counter(
                        "checkout.requests",
                        "result", "success"),
                counter("success"));
    }

    @Test
    void timerRecordsExactSyntheticDurations() {
        Timer synthetic = Timer.builder(
                "checkout.synthetic.duration")
                .tag("scenario", "deterministic")
                .register(registry);

        synthetic.record(Duration.ofMillis(120));
        synthetic.record(Duration.ofMillis(80));

        assertEquals(2L, synthetic.count());
        assertEquals(
                200.0,
                synthetic.totalTime(TimeUnit.MILLISECONDS),
                0.000001);
        assertEquals(
                120.0,
                synthetic.max(TimeUnit.MILLISECONDS),
                0.000001);
    }

    @Test
    void mockClockTestsSampleWithoutSleeping() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry isolated =
                new SimpleMeterRegistry(
                        SimpleConfig.DEFAULT, clock);

        try {
            Timer t = isolated.timer(
                    "checkout.clock.duration",
                    "scenario", "test");

            Timer.Sample sample = Timer.start(isolated);
            clock.add(Duration.ofMillis(125));
            sample.stop(t);

            assertEquals(1L, t.count());
            assertEquals(
                    125.0,
                    t.totalTime(TimeUnit.MILLISECONDS),
                    0.000001);
        }
        finally {
            isolated.close();
        }
    }

    @Test
    void sameNameDifferentTagValueIsDifferentSeries() {
        Counter success = registry.counter(
                "checkout.manual.requests",
                "result", "success");

        Counter error = registry.counter(
                "checkout.manual.requests",
                "result", "error");

        success.increment();
        error.increment();
        error.increment();

        assertEquals(1.0,
                success.count(), 0.000001);
        assertEquals(2.0,
                error.count(), 0.000001);

        assertEquals(
                "success",
                success.getId().getTag("result"));
        assertEquals(
                "error",
                error.getId().getTag("result"));
    }

    @Test
    void missingTagDoesNotMatchAnotherSeries() {
        service.checkout("A");

        assertNull(registry.find("checkout.requests")
                .tag("result", "cancelled")
                .counter());

        assertEquals(1.0,
                counter("success").count(),
                0.000001);
    }

    @Test
    void checkoutMetersNeverUseOrderIdTag() {
        service.checkout("PRIVATE-ORDER-123");

        for (Meter meter : registry.getMeters()) {
            if (meter.getId().getName()
                    .startsWith("checkout.")) {
                assertNull(
                        meter.getId().getTag("orderId"));
                assertNull(
                        meter.getId().getTag("userId"));
            }
        }

        assertFalse(registry.getMeters().isEmpty());
    }
}
```

### 13.1. What Are the Unit Tests Verifying?

| Method | Evidence |
| --- | --- |
| `successIncrementsCounterAndRecordsTimer` | Success counter + timer count increment by 1 |
| `errorHasItsOwnCounterAndTimer` | Error still throws, metrics tagged `outcome=error` |
| `successAndErrorHaveSeparateTaggedSeries` | Two separate series, total 2 success / 1 error |
| `repeatedSuccessesAccumulateOnSameMeter` | Counts accumulate and meter lookup reuses instance |
| `timerRecordsExactSyntheticDurations` | 120+80=200ms, count=2, max=120ms right after recording |
| `mockClockTestsSampleWithoutSleeping` | 125ms sample with monotonic MockClock |
| `sameNameDifferentTagValueIsDifferentSeries` | Different tags → two independent meters |
| `missingTagDoesNotMatchAnotherSeries` | Querying `cancelled` does not match `success` |
| `checkoutMetersNeverUseOrderIdTag` | No high-cardinality `orderId`/`userId` tags |

### 13.2. Why Not Mock MeterRegistry?

Mocking `MeterRegistry` only lets you verify Java calls against a mock. It fails to verify meter ID caching, tagged series, timer durations, or real count semantics. `SimpleMeterRegistry` is lightweight and executes real Micrometer behavior without any network calls. It acts as a **fake backend implementing the real registry API**, requiring no external monitoring service.

### 13.3. Why Assert duration >= 0 for Service, Exact for Synthetic?

Execution time of `DemoPaymentGateway.pay` depends on scheduling, JVM, and CPU. We only know a timing sample exists with non-negative elapsed time. With synthetic `Timer`/`MockClock`, the test controls time and can assert 200/125ms deterministically without flakiness.

### 13.4. Why Test Same Meter with assertSame?

Inside a `SimpleMeterRegistry`, two registrations with matching name+tags+type share the same meter ID and can reuse the same meter instance. For backend/composite registries, rely on series semantics and counts rather than building dashboard logic on Java object identity. In this local unit test, `assertSame` illustrates registry caching.

## 14. CheckoutMetricsBootTest.java — 1 Integration Test

**src/test/java/example/metrics/CheckoutMetricsBootTest.java**

```java
package example.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutMetricsBootTest {

    @Autowired
    MeterRegistry registry;

    @Autowired
    CheckoutService service;

    private double currentCounterValue(String result) {
        Counter c = registry.find("checkout.requests")
                .tag("result", result)
                .counter();
        return c == null ? 0.0 : c.count();
    }

    private long currentTimerCount(String result) {
        Timer t = registry.find("checkout.duration")
                .tag("result", result)
                .timer();
        return t == null ? 0L : t.count();
    }

    @Test
    void springManagedServiceRecordsMetricsInInjectedRegistry() {
        assertNotNull(registry);
        assertNotNull(service);

        double beforeCounter =
                currentCounterValue("success");
        long beforeTimer =
                currentTimerCount("success");

        assertEquals(
                "paid:BOOT-1",
                service.checkout("BOOT-1"));

        assertEquals(
                beforeCounter + 1.0,
                currentCounterValue("success"),
                0.000001);
        assertEquals(
                beforeTimer + 1L,
                currentTimerCount("success"));

        Timer t = registry.find("checkout.duration")
                .tag("result", "success")
                .timer();
        assertNotNull(t);
        assertTrue(t.totalTime(
                java.util.concurrent.TimeUnit.NANOSECONDS)
                >= 0.0);
    }
}
```

This test starts the full Spring context, injecting `CheckoutService` and the **auto-configured `MeterRegistry` bean**. It provides stronger evidence than a unit test: the real service records into the registry supplied by the application. It **does not** prove data exported to Prometheus/Datadog.

### 14.1. Why Measure Baseline/Delta?

Spring TestContext can cache contexts, so metrics might exist before a method starts. The test measures before/after counts and expects both counter and timer to increment by one. Never call `registry.clear()` on a Spring-managed registry, because it wipes JVM metrics and meters held by framework/other beans.

### 14.2. Why Not Assert the Registry Is SimpleMeterRegistry in Boot Tests?

If a project includes Prometheus/other registry modules or a composite registry, the concrete bean type differs. When testing business instrumentation via Spring wiring, inject the `MeterRegistry` interface and query custom names/tags. When testing a provider-specific exporter, assert the concrete backend and output separately.

### 14.3. When Two Tests Run in Parallel on the Same Spring Context

Baseline/delta measurements can be skewed if another test concurrently invokes the service and updates the same series. The demo has only one Boot metrics test method. In larger suites, use separate contexts, unique test-only metric name/tag scopes, or disable parallel execution for shared metrics tests.

## 15. Running Gradle and Reading Results

Requirements: JDK 17, Gradle Wrapper compatible with Boot 3.3 (e.g., Gradle 8.7), dependencies resolvable from Maven Central or cached locally.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.metrics.CheckoutMetricsUnitTest
./gradlew test --tests example.metrics.CheckoutMetricsBootTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.metrics.CheckoutMetricsUnitTest
```

| Test Class | Methods | Spring Context | External Monitoring |
| --- | ---: | --- | --- |
| `CheckoutMetricsUnitTest` | 9 | No | No |
| `CheckoutMetricsBootTest` | 1 | Yes | No |
| **Total** | **10** | Varies by class | No |

**Expected:** 10 JUnit methods pass when code, dependencies, and environment are valid. This is not a claim that Gradle was executed. For real reports, read the Gradle XML/HTML test report to verify executed/passed/failed/skipped counts. There is no fixed business stdout; thread names, process metrics, and startup logs vary.

### 15.1. Expected Values Can Be Calculated Exactly

Synthetic durations 120ms and 80ms → count=2, total=200ms; MockClock advancing 125ms → count=1, total=125ms. These numbers derive from test-supplied inputs rather than CPU timing, making them deterministic.

### 15.2. Why Is Docker Unnecessary?

`SimpleMeterRegistry` sends no network traffic. Spring Boot Actuator's simple fallback requires no external monitoring system either. Docker/Prometheus is only required if you add exporter-specific integration tests.

## 16. Querying the Right Meter and Tag

### 16.1. find vs. get

`registry.find("checkout.requests").tag("result","success").counter()` returns null if the series does not exist—ideal for negative assertions. `registry.get("checkout.requests").tags("result","success").counter()` expects the meter to exist and throws if missing, per API semantics.

Never call `registry.get("checkout.requests").counter()` when multiple series share that name; always specify tags to avoid ambiguity.

### 16.2. Same Tag Name with Different Values

`result=success` and `result=error` have distinct identities. Registering `Counter.builder("...").tag("result","success").register(registry)` repeatedly with the same ID does not create a new series on each call. Changing a tag value, however, creates a brand new series.

### 16.3. Do Not Mix Meter Types with Identical Name and Tags

If one code path registers a Counter `checkout.duration` while another registers a Timer with the same name/tags, the registry may report a conflict or produce invalid output. Keep `checkout.requests` (Counter) and `checkout.duration` (Timer) separate.

### 16.4. Unit vs. Exporter Naming

In Micrometer code, the name may be `checkout.requests`. In Prometheus, counters are typically exported as `checkout_requests_total`. Timers are exported with `_seconds_count`/`_seconds_sum` depending on backend/naming conventions.

*Illustrative* example, not a real scrape:

```text
checkout_requests_total{result="success"} 10
checkout_duration_seconds_count{result="success"} 10
checkout_duration_seconds_sum{result="success"} 0.84
```

Do not assert text formatting on `SimpleMeterRegistry`; use a concrete exporter/scrape test when format is part of the contract.

## 17. Common Tags and MeterFilter

Spring Boot can apply `MeterRegistryCustomizer` to attach `application`, `environment`, or `region` tags, or `MeterFilter` to rename, deny, or cap tags. A manually created unit registry **does not automatically apply** Boot customizers. Therefore, if dashboards rely on common tags, write a Spring integration test.

### 17.1. Customizer Example

```java
@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags() {
    return registry -> registry.config()
            .commonTags(
                    "application", "checkout-service");
}
```

This is an illustrative snippet requiring imports and a `@Configuration` class if added to an app; **it is not part of the main runnable project**. It attaches tags for filtering dashboards/backends. Never make a common tag value equal to a request ID.

### 17.2. Policy-Based MeterFilter

`MeterFilter.maximumAllowableTags(...)` protects against unbounded series by denying or capping registrations past a threshold. It is a defense layer, not a license to use `userId` tags. Tests can detect denied meters when `registry.find(...).counter()` returns nothing; inspect filters rather than deleting assertions.

### 17.3. Risk of Late Common Tags

Configure filters/common tags **before any meters are registered**, usually through Spring Boot configurers. Adding tags/filters after instrumentation has already created meters can cause unexpected behavior; Spring Boot orders configurers during auto-configuration.

## 18. Timer, Percentiles, Histograms, and SLOs

By default, a Timer tracks count and totalTime. P95, histogram buckets, and service-level objectives require corresponding **distribution configuration** and backend support. Directional example:

```properties
management.metrics.distribution.percentiles-histogram.checkout.duration=true
management.metrics.distribution.slo.checkout.duration=50ms,100ms,250ms,1s
```

This is an illustrative config; verify against exact Boot/Micrometer/backend versions. Histograms multiply series by `buckets × tags`. When cardinality is already high, enabling histograms indiscriminately can drastically inflate observability costs.

### 18.1. Mean Is Not p95

`totalTime/count` is the average duration; p95 cannot be derived from a single sum and count. Distribution/histogram or percentile tracking is needed. Histogram quantiles are also estimates bounded by bucket resolution, not necessarily exact sample quantiles.

### 18.2. Timer.max in Unit Tests

In `timerRecordsExactSyntheticDurations`, max is asserted right after recording 120/80ms in a fresh `SimpleMeterRegistry`. Do not treat that assertion as a rule for historical max in every backend, due to time-window rollover.

### 18.3. Units in Queries

Prometheus clients usually export seconds; the Micrometer Timer API takes explicit `TimeUnit`. When writing alerts, convert a 250ms SLA to 0.25 seconds if the backend queries seconds.

## 19. ObservationRegistry, @Timed, and Manual Instrumentation

`@Timed` ships with Micrometer, yet **Spring Boot does not automatically enable timing on arbitrary methods** simply because the Actuator starter is present. A `TimedAspect`/AOP integration or proper Micrometer Observation setup may be required.

```java
@Timed(value = "checkout.annotated.duration")
public String calculate() {
    return "ok";
}
```

**Illustrative snippet**: the annotation does not guarantee a meter appears without configured instrumentation. To prove it works:

1. Invoke the method through a real Spring bean/proxy, not `new` object.
2. Register `TimedAspect`/Observation integration matching your Spring Boot/Micrometer version.
3. Query the meter after the method actually executes.
4. Write a negative test when instrumentation is missing to avoid false positives.
5. For reactive methods, measure timing at **subscription/termination**.

### 19.1. What Is ObservationRegistry?

Micrometer Observations coordinate metrics, tracing, and context propagation via ObservationHandlers. Spring Boot 3.x uses Observations for many HTTP server/client instrumentations. If custom code uses `Timer.Sample` around the same boundary that an Observation already records, you can end up with duplicate metrics or inconsistent names/tags. Define a single source of truth per semantic metric.

### 19.2. HTTP Server Metrics vs. Business Checkout Metrics

`http.server.requests` typically measures every HTTP exchange; `checkout.requests` measures each `CheckoutService` invocation. One HTTP request might invoke the service multiple times, or checkout might be triggered from a message bus. Never assume those two counters must always match.

## 20. Actuator and Exporter-Specific Tests

`spring-boot-starter-actuator` provides metrics infrastructure, yet exposing metrics over an HTTP endpoint requires a web stack and exposure configuration. Exporting Prometheus additionally requires an exporter module like `micrometer-registry-prometheus` and exposure permission under security policy.

Extended example, **not part of the original runnable project**:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Example `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Run the app with the web starter, trigger a checkout event, then scrape `/actuator/prometheus` using an HTTP client/test tool. Note: the base Boot app has no HTTP route invoking `CheckoutService`; to generate events in a live app, add a controller/runner intentionally or invoke the service in a test method before scraping the actuator endpoint. Never claim sample output written on paper was generated by a real exporter.

### 20.1. Testing External Exporters

- Prometheus: test scrape text format and labels with the exact exporter module/version.
- Datadog/OTLP/StatsD: test publishing steps, credentials, endpoints, retries, and a test collector/server per backend.
- Multi-instance: query aggregated across instance/pod tags rather than comparing one process's `Counter.count()` against cluster totals.
- Dashboards/alerts: require E2E integration or manual verification of queries and thresholds.

**Simple registry pass ≠ exporter pass**; they are two separate boundaries.

## 21. Spring Boot Testing Behavior

Spring Boot 3.3 tests usually provide an in-memory `MeterRegistry` when Actuator is present, while external exporting registries are not auto-configured by default in `@SpringBootTest`. `@AutoConfigureObservability` can be used to enable observability auto-configuration in slices or when export is intentionally tested.

If a `@WebMvcTest`/`@WebFluxTest` slice lacks a `MeterRegistry` bean, that stems from slice scope/auto-configuration, not a lack of metrics in production. Provide a test registry bean or the appropriate test annotation.

### 21.1. Metrics Disabled

If `management.metrics.enable.checkout=false` is configured or a `MeterFilter` denies the prefix, custom meters will not appear. A proper test should fail when a metric contract is disabled, unless testing an intentionally metrics-disabled environment with explicitly adjusted expectations.

### 21.2. Spring Context Reuse

The TestContext cache retains Spring beans and metrics state. Delta assertions avoid depending on exact pre-method counts. Do not overuse `@DirtiesContext` on every metrics test; it adds startup overhead and can destabilize environment startup. A fresh `SimpleMeterRegistry` per unit test is the primary strategy.

### 21.3. Never Wipe the Whole Meter Registry with clear

`MeterRegistry.clear()` deletes all registered meters, not just custom checkout series. When framework binders hold references, clearing the registry between methods can break subsequent metric updates. If reset is needed, use an isolated registry or unregister targeted test-owned meters in a controlled context.

## 22. Async/Retry Semantics

### 22.1. Reactive Publisher Assembly Is Not Execution

Wrong:

```java
Timer.Sample sample = Timer.start(registry);
Mono<String> mono = actualReactiveOperation();
sample.stop(timer);
return mono;
```

**Illustrative snippet**: `actualReactiveOperation()`, `registry`, and `timer` must be supplied. It measures publisher assembly time, not the async response. In reactive code, wrap inside `Mono.defer` and stop in `doFinally`, or use reactive-aware Observation instrumentation.

Directional approach:

```java
Mono<String> publisher = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);
    return actualReactiveOperation()
            .doFinally(signal -> {
                Timer t = Timer.builder("reactive.duration")
                        .tag("signal", signal.name())
                        .register(registry);
                sample.stop(t);
            });
});
```

This snippet lacks full dependencies/method definitions and is not in the lab. `signal` uses bounded enum values, though you still must distinguish success/error/cancel and prevent double-measurement across retries/resubscriptions.

### 22.2. Retries

One logical checkout may perform 1–N attempts. Never record logical success/error metrics on every retry attempt if dashboards count business requests. `attempts` and `logical.requests` are two independent counters; tests must assert each at its own scope.

### 22.3. Parallel Updates

Micrometer metric updates are typically thread-safe depending on implementation, yet a test measuring deltas on a shared registry can still be skewed if other requests update the same series concurrently. Test isolation is a test-design responsibility—never “fix” it with sleeps or test retries.

## 23. Diagnosing Failures

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `registry.find(...).counter()` is null | Wrong metric name/tag or code never ran | Query exact name+tags, invoke service |
| Count stays 0 | Code updates a different/global registry | Constructor-inject the same `MeterRegistry` |
| Unit test passes alone, fails in suite | Static registry or cached context | Fresh registry per test or delta |
| Timer count is 0 | Sample never stopped | `finally` + matching timer ID |
| Error counter is 0 | `catch` didn't change outcome or different throw path | Test negative paths |
| Timer total milliseconds wrong | Wrong `TimeUnit`/JVM timing | `MockClock`/`record(Duration)` |
| `Timer.max` drops | Time-window max expiration | Don't assert historical max |
| Meter exists with wrong tags | Spelling/case/key drift | Assert `getId().getTag` |
| Too many time series | `orderId`/`userId`/raw URI tag | Cardinality policy + `MeterFilter` |
| Prometheus misses counter | Missing exporter/unexposed endpoint | Test exporter/Actuator separately |
| Prometheus series name differs from Java | Naming conventions/`_total` suffix | Check backend-specific name |
| `@Timed` produces no timer | Missing `TimedAspect`/Observation | Configure instrumentation |
| Metrics missing in `@WebMvcTest` | Slice excludes metrics beans | `@AutoConfigureObservability`/test bean |
| Histogram `_bucket` missing | Histogram/SLO disabled | Distribution config |
| Mono timer is tiny | Measuring publisher assembly | Measure subscription/terminal signal |
| `Timer.count` differs from `Counter.count` | Different scopes or double recording | Review semantics |
| Request ID appears in tags | High-cardinality design bug | Use traces/logs |
| Negative test passes because metrics are denied | Null assertion only | Add positive assertion |
| Test gets 401/500 yet metric says success | Wrong outcome mapping | Paired success/error tests |

## 24. Practical Exercises

1. **Remove `Counter.increment()`** in `CheckoutService`. The success test must fail even though the gateway returns the right value.
2. **Remove `sample.stop(...)`**. The timer count assertion must fail.
3. **Remove `result = "error"` in `catch`**. The error test catches the series being mislabeled as `success`.
4. **Record metrics in both `catch` and `finally`**. Counter/timer count tests expose double-counting.
5. **Add an `orderId` tag**. The cardinality guard test must fail; remove that tag afterward.
6. **Rename the `result` tag to `outcome`**. Lookup by name+tag fails; update the contract intentionally if dashboards change.
7. **Add 3 success calls**. Expect success counter=3, timer.count=3.
8. **Advance `MockClock` by 250ms**. Change expected totalTime to 250ms without using `Thread.sleep`.
9. **Synthetic timer 120+80ms**. Read `TimeUnit.SECONDS`, expecting 0.2; avoid unit mix-ups.
10. **Share a static registry**. Observe counts from earlier tests polluting later tests; restore a fresh `@BeforeEach` registry.
11. **Use `Metrics.globalRegistry` in the service**. Unit registry lookup finds no meters, highlighting the dependency injection mistake.
12. **Add common tags**. Use a `MeterRegistryCustomizer` bean in a Spring config test; verify the `application` tag.
13. **`@Timed` on an arbitrary method**. Assert a timer without adding an Aspect and observe it does not magically appear.
14. **Prometheus exporter**. Add the module and web starter/test endpoint, scrape real output, and contrast it with `SimpleMeterRegistry`.
15. **Histogram/SLO**. Enable distribution config for `checkout.duration`; inspect bucket cost and output.
16. **Retrying gateway**. Define a logical counter and attempts counter; assert 1 logical checkout + 3 outbound attempts.
17. **Async Mono**. Compare measuring assembly time vs. subscriber completion time.
18. **Multiple outcomes**. Add `rejected`/`timeout` outcome enums and tests; avoid raw exception messages.
19. **Inspect process metrics**. When Actuator is active, the registry also holds JVM/process metrics. Never clear the entire registry just to test custom checkout metrics.
20. **Dashboard contract**. Document metric name, unit, tag keys/values, alert queries, owner, and migration plan for every change.

## 25. Pre-Merge QA Checklist

- [ ] Business instrumentation uses an injected `MeterRegistry`, not a static global.
- [ ] Counter measures the exact logical event and only increments.
- [ ] `Timer.Sample` starts/stops once across both success and error paths.
- [ ] Timer count/totalTime verified with explicit `TimeUnit`.
- [ ] Unit timings are deterministic via `Duration`/`MockClock`, never exact wall-clock assertions.
- [ ] Error paths record `result=error` series, never lumped into `success`.
- [ ] Both positive and negative metric assertions are present.
- [ ] Meter lookups match exact name and tags, never relying on list position.
- [ ] Tags contain no `orderId`/`userId`/`requestId`/raw URI/PII.
- [ ] Tag names/values are bounded, stable, and documented.
- [ ] No conflicting meter types share the same name/tags.
- [ ] Unit tests construct a new `SimpleMeterRegistry` per method.
- [ ] `@AfterEach` closes the registry without leaking global state.
- [ ] `@SpringBootTest` measures deltas against the injected registry.
- [ ] Never calls `clear()` on the whole Spring-managed registry to reset counts.
- [ ] Parallel tests do not mutate shared meter series concurrently when asserting deltas.
- [ ] `Timer.count` is accounted for; no redundant double-counting with Counter.
- [ ] Common tags/`MeterFilter` rules are tested in-context when part of the contract.
- [ ] `@Timed` on arbitrary methods has real aspect/Observation instrumentation.
- [ ] Async/reactive metrics measure subscription completion, not assembly alone.
- [ ] External exporters are tested separately when networking/export proof is needed.
- [ ] `SimpleMeterRegistry` passing is never treated as Prometheus/Datadog verification.
- [ ] Histograms/percentiles/SLOs are enabled deliberately within cardinality budgets.
- [ ] Actuator endpoint exposure has security review.
- [ ] Report executed/passed/failed/skipped counts from a real JUnit report.
- [ ] Spring Boot/Micrometer/backend versions and naming conventions are tracked on upgrades.

## 26. Testing Selection Guide

```text
What needs to be verified?
      |
      +-- Business counter / timer / tags?
      |      -> JUnit + SimpleMeterRegistry per test.
      |
      +-- Exact durations?
      |      -> Timer.record(Duration) / MockClock.
      |
      +-- Spring-managed registry?
      |      -> @SpringBootTest + delta assertions.
      |
      +-- @Timed / Observation?
      |      -> Verify aspect/handlers + Spring bean proxy.
      |
      +-- Prometheus naming/export/histograms?
      |      -> Concrete exporter + scrape integration test.
      |
      +-- Monitoring backend/scraper/alerts?
             -> Dedicated staging/deployment verification.
```

**Summary:** Counters track event occurrences, Timers track counts and elapsed times, and tags partition series. `SimpleMeterRegistry` lets unit tests verify real Micrometer behavior without networking; `MockClock` makes duration checks exact and flake-free. `@SpringBootTest` verifies Spring bean wiring using before/after deltas. Keep tags bounded, test error paths, and avoid accidental use of `Metrics.globalRegistry`. When verifying exporters, test against concrete backends rather than extrapolating from in-memory registries.

## 27. Official Documentation

- Spring Boot 3.3 — Metrics and auto-configured MeterRegistry: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Testing, observability, and @AutoConfigureObservability: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Micrometer — Registry and SimpleMeterRegistry: https://docs.micrometer.io/micrometer/reference/concepts/registry.html
- Micrometer — Counters: https://docs.micrometer.io/micrometer/reference/concepts/counters.html
- Micrometer — Timers and Timer.Sample: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Naming conventions: https://docs.micrometer.io/micrometer/reference/concepts/naming.html
- Micrometer — Histograms and percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Micrometer — Gauges: https://docs.micrometer.io/micrometer/reference/concepts/gauges.html
- Micrometer — MeterFilters and tag cardinality policy: https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html
- Micrometer — Observation components: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — API Javadoc: https://javadoc.io/doc/io.micrometer/micrometer-core/
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — User guide: https://docs.junit.org/current/user-guide/
