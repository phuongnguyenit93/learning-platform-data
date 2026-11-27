# Test metrics with SimpleMeterRegistry in Spring Boot

When writing code using Micrometer, you need to verify that meters are registered properly, record or increment the expected values, and distinguish tag dimensions accurately. Not every test needs to start a full Spring Boot application or connect to a Prometheus/OTLP backend. Micrometer provides `SimpleMeterRegistry`, an in-memory registry well suited for unit tests because it requires no network exporter.

**`SimpleMeterRegistry` enables testing meter behavior directly and in isolation from export infrastructure.** Tests can create a registry, call business code, read Counter/Timer/Gauge meters, and verify counts, total times, or tag identities. For behaviors that depend on Spring AOP, auto-configuration, filters, or exporters, add integration tests at the appropriate layer.

The lesson **"Test metrics with SimpleMeterRegistry"** belongs to the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. What is SimpleMeterRegistry?

`SimpleMeterRegistry` is a `MeterRegistry` that stores measurements in memory. It is ideal for testing Counter, Timer, Gauge, DistributionSummary, and basic meters without an exporter/backend.

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
```

Tests should create an isolated registry per test or test fixture. Do not use a shared global registry across tests because meter state can leak from one test to another.

`SimpleMeterRegistry` does not emulate Prometheus, OTLP, or any specific backend registry in full. It verifies Micrometer meter semantics in-process; it does not prove scrape formats, network export, authentication, or backend ingestion.

## 2. Testing Counters

A `Counter` is suitable for counting how many times an event happens. Tests can verify increment amounts:

```java
@Test
void countsProcessedOrders() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Counter counter = registry.counter("orders.processed");

    counter.increment();
    counter.increment(2.0);

    assertThat(counter.count()).isEqualTo(3.0);
}
```

You should verify that business code actually uses the injected registry:

```java
class OrderMetrics {
    private final Counter processed;

    OrderMetrics(MeterRegistry registry) {
        this.processed = registry.counter("orders.processed");
    }

    void recordProcessed() {
        processed.increment();
    }
}

@Test
void serviceRecordsProcessedOrder() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    metrics.recordProcessed();
    metrics.recordProcessed();

    assertThat(registry.get("orders.processed").counter().count())
            .isEqualTo(2.0);
}
```

A `Counter` is a cumulative value. In unit tests, check `count()` directly; rate/increase queries belong to the backend query layer and are not simulated by `SimpleMeterRegistry`.

## 3. Testing tag identity

The same meter name with different tag values creates distinct meter identities.

```java
@Test
void separatesCounterByOutcomeTag() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.counter("orders.processed", "outcome", "success").increment(2);
    registry.counter("orders.processed", "outcome", "failure").increment();

    assertThat(registry.get("orders.processed")
            .tag("outcome", "success")
            .counter()
            .count()).isEqualTo(2.0);

    assertThat(registry.get("orders.processed")
            .tag("outcome", "failure")
            .counter()
            .count()).isEqualTo(1.0);

    assertThat(registry.getMeters()).hasSize(2);
}
```

This test verifies that tag values produce the expected identities. Verify required tag keys/values and ensure no dynamic identifiers slip into tags.

## 4. Testing cardinality guardrails

A test can catch instrumentation that accidentally creates a meter per entity:

```java
@Test
void usesFiniteTagValues() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    for (int i = 0; i < 1_000; i++) {
        registry.counter(
                "orders.processed",
                "outcome",
                i % 2 == 0 ? "success" : "failure"
        ).increment();
    }

    assertThat(registry.getMeters()).hasSize(2);
}
```

If code puts an order ID into a tag, the meter count grows with the number of orders. You can write regression tests asserting that the tag schema excludes user/order/request IDs. You do not need millions of identities in normal tests; a modest dataset is enough to expose the pattern.

## 5. Testing Timers

A `Timer` records count and total time. Tests should avoid depending on unstable wall-clock timing.

```java
@Test
void recordsTimerSamples() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Timer timer = registry.timer("orders.processing");

    timer.record(Duration.ofMillis(120));
    timer.record(Duration.ofMillis(80));

    assertThat(timer.count()).isEqualTo(2);
    assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(200.0);
}
```

This test is deterministic because it passes durations directly. If production code uses `Timer.Sample` or a clock, inject an appropriate `Clock` or use a mock/step clock per your Micrometer version API to control time.

Do not assert elapsed wall-clock time within a tight window; CI scheduling, GC, and CPU load can make such tests flaky.

## 6. Testing Timer.Sample

`Timer.Sample` starts timing and stops at a later point. When testing sample durations, control the clock instead of using long sleeps.

Idea:

1. Create a registry with a controllable clock.
2. Start `Timer.Sample`.
3. Advance the clock by a fixed interval.
4. Stop the sample into the `Timer`.
5. Assert count and total time.

Exact `MockClock`/`Clock` APIs depend on Micrometer version. Keep tests short and deterministic; avoid `Thread.sleep` because it slows down the suite and offers no timing accuracy guarantee.

## 7. Testing Gauges

A `Gauge` observes the current value of a referenced object. Tests can mutate object state and read the gauge:

```java
@Test
void observesQueueSize() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Queue<String> queue = new ConcurrentLinkedQueue<>();

    Gauge.builder("worker.queue.size", queue, Queue::size)
            .register(registry);

    queue.add("job-1");
    queue.add("job-2");

    assertThat(registry.get("worker.queue.size").gauge().value())
            .isEqualTo(2.0);
}
```

A `Gauge` is not a counter: it reflects a current value that can go up or down. Keep a strong reference to the target object in tests to avoid garbage collection if the gauge implementation uses weak references.

Tests should verify that a gauge is registered once for a stable resource rather than creating a new gauge per request/entity.

## 8. Testing DistributionSummary

`DistributionSummary` measures the distribution of non-time values, such as payload sizes or record counts in a batch.

```java
@Test
void recordsPayloadSizes() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    DistributionSummary summary =
            registry.summary("message.payload.bytes");

    summary.record(100);
    summary.record(300);

    assertThat(summary.count()).isEqualTo(2);
    assertThat(summary.totalAmount()).isEqualTo(400.0);
}
```

If histograms/percentiles are enabled, test distribution configuration separately and remember that `SimpleMeterRegistry` does not verify backend export formats.

## 9. Testing meter name, description, and base unit

Meter names are part of the observable contract. Tests can verify meter names and tag schemas, especially for metrics consumed by dashboards/alerts.

```java
Meter meter = registry.get("orders.processed")
        .tag("outcome", "success")
        .meter();

assertThat(meter.getId().getName()).isEqualTo("orders.processed");
assertThat(meter.getId().getTag("outcome")).isEqualTo("success");
```

Description and base unit can be inspected via `Meter.Id` metadata if code registers them. Do not assert backend-normalized names when testing a raw registry; naming conventions may transform at the exporter registry layer.

## 10. Testing MeterFilter

`MeterFilter` can deny, rename, or adjust meter configuration. `SimpleMeterRegistry` lets you verify policies on the registry configuration.

```java
@Test
void deniesLegacyMeters() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    registry.config().meterFilter(
            MeterFilter.denyNameStartsWith("legacy.")
    );

    registry.counter("orders.processed").increment();
    registry.counter("legacy.debug.calls").increment();

    assertThat(registry.find("orders.processed").counter()).isNotNull();
    assertThat(registry.find("legacy.debug.calls").counter()).isNull();
}
```

Configure filters before meters are registered. If a meter was registered earlier, a newly added filter may not remove the existing meter. Tests should create a fresh registry for each policy scenario.

## 11. Testing code using ObservationRegistry and handlers

`SimpleMeterRegistry` tests meters, whereas `Observation` also has lifecycles and handlers. You can combine `SimpleMeterRegistry` with `ObservationRegistry` and a `MeterObservationHandler` to verify an `Observation` generates the expected metric.

Test outline:

1. Create a `SimpleMeterRegistry`.
2. Create an `ObservationRegistry`.
3. Register the corresponding `MeterObservationHandler`.
4. Create an `Observation` and attach low-cardinality `KeyValues`.
5. Start/stop the `Observation`.
6. Assert the meter is recorded in `SimpleMeterRegistry`.

Constructors and handler classes may differ by Micrometer version. Use the API matching the dependency managed by Spring Boot; do not assume every project shares the same constructor.

If you only need to test a `Counter`/`Timer` directly, there is no need to construct an `ObservationRegistry`. Keep tests as narrow in scope as needed.

## 12. SimpleMeterRegistry vs. Spring Boot integration tests

These two test layers answer different questions:

| Test type | Verifies |
| --- | --- |
| Unit test + SimpleMeterRegistry | Code records meters with the right name, tags, and values |
| Spring context test | Bean wiring, `MeterRegistry` injection, customizers, filters, AOP |
| Actuator endpoint test | Endpoint exposure, security, and response |
| Exporter integration test | Format, network, authentication, and backend ingestion |

A service constructor injecting `MeterRegistry` can be unit tested with `SimpleMeterRegistry`. However, `@Counted` depends on `CountedAspect`/AOP proxies; a Spring context test is needed to prove the aspect intercepts the bean method.

Do not conclude an exporter works simply because a counter incremented in `SimpleMeterRegistry`.

## 13. Using isolated registries and cleanup

Creating a fresh registry per test avoids shared state. If a test fixture holds a registry longer, close the registry after the test:

```java
@AfterEach
void tearDown() {
    registry.close();
}
```

When a registry is created inside each test method, you can use try/finally or test fixture lifecycle hooks. Never add meters to `Metrics.globalRegistry` and expect test isolation; the global registry can retain state across test classes.

If the application uses a composite/global registry, ensure tests do not accidentally record the same event into both the test registry and the global registry.

## 14. Testing annotation-based metrics

`@Counted` and `@Timed` typically rely on AOP aspects. `SimpleMeterRegistry` is where results are read, but it does not activate AOP on its own.

In a Spring integration test:

1. Register `CountedAspect`/`TimedAspect` per application configuration.
2. Inject the service from `ApplicationContext`.
3. Call the method through the injected bean.
4. Read the counter/timer from the registry.
5. Verify self-invocation behavior if applicable.
6. Throw an exception and verify semantics.

Do not instantiate the service with `new` in a test when the goal is verifying a Spring proxy.

## 15. What SimpleMeterRegistry does NOT test

`SimpleMeterRegistry` does not prove:

- Prometheus exposition format and label naming.
- OTLP metric export, temporality, or resource attributes.
- Proper scrape endpoint exposure/security.
- Exporter retries, batching, queues, and shutdown flushes.
- TLS/authentication to the Collector/backend.
- Backend retention, indexing, and alert queries.
- Sampling or distributed trace propagation.

These behaviors require integration tests with the corresponding exporter/Collector/backend or test environment.

## 16. Diagnosing failing metric tests

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Counter does not exist | Code did not call `increment` or used another registry | Check dependency injection and execution path |
| Count higher than expected | Shared registry or tests running in parallel | Create an isolated registry for the test |
| Tag query does not find meter | Different tag key/value or missing tag | Inspect `Meter.Id` |
| Meter count grows per entity | Dynamic tag creates new identities | Check tag schema |
| Timer count right but total time wrong | Unit conversion or timing boundary | Assert correct `TimeUnit` and deterministic clock |
| Gauge returns `NaN`/no value | Object GC'd or faulty gauge registration | Keep strong reference and check supplier |
| MeterFilter has no effect | Filter added after meter registration | Create fresh registry, configure filter first |
| `@Counted` does not increment | Aspect/proxy did not run | Use a Spring integration test |
| Actuator does not show meter | Different endpoint/exposure/registry | Test the Actuator context separately |
| Backend does not receive metrics | Exporter/network/auth issue | Integration test the pipeline |

## 17. Practice: building a metric test suite

Perform locally/in tests:

1. Create a service using `MeterRegistry` to record processed orders.
2. Write a unit test with `SimpleMeterRegistry` for `Counter`.
3. Add `outcome` tags (`success`/`failure`) and verify two meter identities.
4. Write a cardinality test with 1,000 operations but only two tag values.
5. Add a `Timer` and record deterministic durations using `Duration`.
6. Add a `Gauge` for queue size and mutate queue state.
7. Add a `DistributionSummary` for payload size.
8. Add a `MeterFilter` denying a prefix and verify the meter is rejected.
9. Create a Spring integration test for the `@Counted` aspect.
10. Create an `ObservationRegistry` test if needed to check Observation handlers.
11. Check registry cleanup and avoid global shared state.
12. Write a separate exporter integration test if Prometheus/OTLP verification is needed.

Expected outcome: deterministic unit tests verifying meter behavior; integration tests verifying wiring/AOP/Actuator/exporters at the right layers.

## 18. Self-check questions

1. Which test type is `SimpleMeterRegistry` suited for?
2. Why should each test create an isolated registry?
3. How does `Counter.count()` differ from rate queries?
4. What happens when meters share a name but have different tag values?
5. How do you test cardinality using finite tag values?
6. Why should Timer tests use deterministic durations?
7. How does a Gauge differ from a Counter?
8. How can a Gauge be affected by object lifecycle?
9. What data is `DistributionSummary` suited to measure?
10. When must `MeterFilter` be configured?
11. How does `ObservationRegistry` differ from `MeterRegistry`?
12. Why does `@Counted` require a Spring integration test?
13. Does `SimpleMeterRegistry` test Prometheus/OTLP export?
14. When should you test Actuator endpoints/security?
15. How do you prevent test state from leaking through a global registry?

## References

- [Micrometer — MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): registry abstraction and `SimpleMeterRegistry`.
- [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): Counter, Timer, Gauge, DistributionSummary, and meter identity.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): filter configuration.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): `ObservationRegistry` and handlers.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `MeterRegistry` auto-configuration and Actuator metrics.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring application integration testing.

## Conclusion

**`SimpleMeterRegistry` is a lightweight tool for verifying metrics behavior in unit tests without needing an exporter or backend.** It is well suited for checking Counter, Timer, Gauge, DistributionSummary, tags, meter identities, and `MeterFilter` using in-memory state.

Create isolated registries, use deterministic timing, verify cardinality, and clean up to keep tests stable. When you need to verify AOP, Spring bean wiring, Observation handlers, Actuator security, or Prometheus/OTLP export, add the corresponding integration tests. Separating tests across the right boundaries catches metric bugs early without tying the unit suite to external telemetry infrastructure.
