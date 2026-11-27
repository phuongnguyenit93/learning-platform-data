# Test custom observation

A Spring Boot service has a custom Observation named inventory.reserve to measure reservation duration. The developer added low-cardinality tags for warehouse and outcome, and recorded an exception when the reservation fails. If a test only checks that the endpoint returns the right HTTP status, it does not prove that the Observation was actually created, that the handler received the right context, or that metrics/tracing signals were recorded. Testing a custom Observation requires verifying the lifecycle and telemetry data right at the instrumentation boundary.

The lesson **Test custom observation** belongs to the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. This module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; and how to understand context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Principle:** Test Observations with a dedicated test registry and handlers. Verify the operation name, context, low/high-cardinality key-values, errors, and start/stop lifecycle. If you need to verify metrics or spans, check each signal through the corresponding MeterRegistry or tracing test reporter. You do not need to send telemetry to Prometheus, an OTLP Collector, or a production backend just to prove the code is instrumented correctly.

## 1. Learning objectives

After this lesson, you can:
1. Explain why custom Observations need dedicated tests.
2. Distinguish testing the Observation lifecycle from testing metrics and tracing exporters.
3. Create an ObservationRegistry dedicated to testing.
4. Register handlers to collect Observation contexts.
5. Assert the name, contextual name, low/high-cardinality tags, and errors.
6. Verify start/stop, scope, and exception behavior.
7. Verify that MeterRegistry records Timer/Counter meters from Observation handlers.
8. Verify tracing spans using a test tracer/reporter.
9. Test ObservationPredicate, filters, and no-op behavior.
10. Test context propagation across executor/reactive boundaries.
11. Detect duplicate observations and metric cardinality regressions.
12. Avoid tests that depend on an exporter/backend or unstable timing.

## 2. Test pyramid for custom Observations

A custom Observation can be tested at multiple layers:

| Test layer | Component | What to prove |
|---|---|---|
| Unit test | ObservationRegistry + test handler | Lifecycle, context, tags, error |
| Metrics test | MeterRegistry + meter handler | Timer/Counter and tag values |
| Tracing test | Test tracer/span reporter | Span name, parent, attributes, error |
| Spring integration test | ApplicationContext + custom bean | Auto-configuration, wiring, and proxy |
| End-to-end test | App + Collector/backend test stack | Export protocol, cross-process propagation |

Most custom Observation logic should be verified with lightweight unit/integration tests. End-to-end tests are only needed when changing exporters, the Collector pipeline, or the propagation protocol; do not make every test depend on telemetry infrastructure.

~~~mermaid
flowchart TD
    A["Custom operation"] --> B["ObservationRegistry"]
    B --> C["Test ObservationHandler"]
    B --> D["MeterObservationHandler"]
    B --> E["TracingObservationHandler"]
    C --> F["Assert context and lifecycle"]
    D --> G["Assert Timer / Counter"]
    E --> H["Assert span and parent"]
~~~

## 3. Designing testable custom Observations

Example service using ObservationRegistry to instrument an operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class InventoryReservationService {

    private final ObservationRegistry registry;
    private final InventoryRepository repository;

    InventoryReservationService(
            ObservationRegistry registry,
            InventoryRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    Reservation reserve(String warehouse, String sku) {
        return Observation.createNotStarted("inventory.reserve", registry)
                .contextualName("reserve-inventory")
                .lowCardinalityKeyValue("warehouse", warehouse)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> repository.reserve(warehouse, sku));
    }
}
~~~

Illustrative example. In production, warehouse must come from a controlled set of values; do not add sku/order/user identifiers to low-cardinality tags. If the repository or framework already creates an Observation for the same database call, the custom Observation here should represent the outer business operation to avoid double counting.

The test should define the contract:
- Observation name: inventory.reserve.
- Contextual name: reserve-inventory.
- Low-cardinality key-values: warehouse, operation.
- Terminal behavior: success or exception.
- Which handlers are expected to receive the Observation.

## 4. Creating an isolated ObservationRegistry for tests

Do not share a global registry across tests because state and handlers can leak between test cases. Creating a dedicated registry makes it clear which handlers are invoked in each test.

Micrometer provides the ObservationRegistry and ObservationHandler APIs. You can register a simple handler to record lifecycle/context events. Some Micrometer versions provide test utilities such as TestObservationRegistry; check the API of the version you are using before choosing a utility.

Example of a custom-written handler:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import java.util.ArrayList;
import java.util.List;

class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    private final List<String> started = new ArrayList<>();
    private final List<String> stopped = new ArrayList<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        started.add(context.getName());
    }

    @Override
    public void onStop(Observation.Context context) {
        stopped.add(context.getName());
    }

    List<String> started() {
        return started;
    }

    List<String> stopped() {
        return stopped;
    }
}
~~~

This is a minimal illustrative handler. If tests run in parallel or Observations are recorded from multiple threads, use thread-safe collections or appropriate synchronization. For dedicated context tests, you can assert the KeyValues directly in the context instead of only storing the name.

## 5. Verifying that an Observation starts and stops

Example JUnit test:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryObservationTest {

    @Test
    void recordsObservationLifecycle() {
        ObservationRegistry registry = ObservationRegistry.create();
        RecordingObservationHandler handler =
                new RecordingObservationHandler();
        registry.observationConfig().observationHandler(handler);

        Observation.createNotStarted("inventory.reserve", registry)
                .observe(() -> "reserved");

        assertThat(handler.started())
                .containsExactly("inventory.reserve");
        assertThat(handler.stopped())
                .containsExactly("inventory.reserve");
    }
}
~~~

This test proves the Observation goes through the start/stop handlers. It does not prove that metrics or spans were created; those signals require their respective handlers.

### 5.1 Verifying lifecycle when the callback throws an exception

~~~java
@Test
void stopsObservationWhenOperationThrows() {
    ObservationRegistry registry = ObservationRegistry.create();
    RecordingObservationHandler handler =
            new RecordingObservationHandler();
    registry.observationConfig().observationHandler(handler);

    assertThatThrownBy(() ->
            Observation.createNotStarted("inventory.reserve", registry)
                    .observe(() -> {
                        throw new IllegalStateException("reservation failed");
                    }))
            .isInstanceOf(IllegalStateException.class);

    assertThat(handler.started()).containsExactly("inventory.reserve");
    assertThat(handler.stopped()).containsExactly("inventory.reserve");
}
~~~

The Observation API manages the lifecycle around the callback; the test must confirm that stop occurs on both the success and error paths. If the code calls start/stop manually instead of using observe(), ensure stop is placed in a finally block and does not leave the Observation open when an exception occurs.

## 6. Asserting context and KeyValues

A correct Observation name with wrong tags can still break dashboards or cause cardinality issues. The handler can inspect the context in onStart/onStop for assertions.

Example checking the context inside a handler:

~~~java
@Override
public void onStop(Observation.Context context) {
    assertThat(context.getName()).isEqualTo("inventory.reserve");
    assertThat(context.getContextualName()).isEqualTo("reserve-inventory");
    assertThat(context.getLowCardinalityKeyValues())
            .contains(KeyValue.of("warehouse", "north"));
}
~~~

This is an illustrative snippet; you need to import KeyValue from Micrometer and adjust assertions to match the KeyValues API of your version. When testing low-cardinality values, verify the exact key and value, not just the tag count.

### 6.1 Low-cardinality and high-cardinality assertions

- Low-cardinality values can become metric tags; verify that only allowlisted values are used.
- High-cardinality values can be used for traces; verify that no secrets/PII are placed into the context.
- Do not assert only a tag count if tag ordering or extra common tags can vary by configuration.
- Do not snapshot the entire context if fields contain unstable runtime objects.

For example, the test should assert that warehouse belongs to the set north/south/central rather than accepting arbitrary raw input.

## 7. Verifying error recording

An Observation can record an exception on the context when the callback fails. Tests should verify:
- The exception propagates according to the method contract.
- The context contains the expected error.
- The handler stop method is still called.
- The tracing handler records the error event/status according to convention.
- Metric outcome/error tags are normalized and bounded.

Example assertion in a recording handler:

~~~java
@Override
public void onStop(Observation.Context context) {
    Throwable error = context.getError();
    if (error != null) {
        recordedErrors.add(error.getClass());
    }
}
~~~

Only use the exception class/category as a metric tag if it is normalized into a finite set. Do not use the exception message because messages can contain SQL, user input, URLs, credentials, or PII.

### 7.1 A business outcome is not always an error

If the repository returns an empty result and the service translates it into a "not found" business result, the Observation can complete normally. Do not force every business rejection into an exception just to create an error span. Define a dedicated outcome instead, such as success/not_found/rejected, and only mark an error when the operation suffers a technical failure according to contract.

## 8. Verifying Timer/Counter in MeterRegistry

To verify that an Observation produces metrics, register the appropriate meter observation handler and MeterRegistry in the test. In a Spring Boot test context, Actuator/Micrometer auto-configuration can provide the registry/handlers; pure unit tests must configure the corresponding handlers explicitly.

Example of a standalone custom Timer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

class InventoryMetrics {
    private final Timer timer;

    InventoryMetrics(MeterRegistry registry) {
        timer = Timer.builder("inventory.reserve.duration")
                .tag("operation", "reserve")
                .register(registry);
    }

    void record(Runnable operation) {
        timer.record(operation);
    }
}
~~~

Test:

~~~java
@Test
void recordsTimerForReservation() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    InventoryMetrics metrics = new InventoryMetrics(registry);

    metrics.record(() -> { });

    Timer timer = registry.find("inventory.reserve.duration")
            .tag("operation", "reserve")
            .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

This example tests a custom Timer and does not prove that an Observation handler creates the timer automatically. To test Observation-to-metrics, configure DefaultMeterObservationHandler or the handler appropriate for your Spring Boot/Micrometer version, then assert that the meter is created from the Observation.

### 8.1 Do not assert duration with exact equality

Duration depends on the OS scheduler, machine load, and clock resolution. Instead of asserting exactly 10 ms, use a wide range or assert count and presence. For critical timing logic, inject a Clock or a controllable time-measurement abstraction.

## 9. Verifying tracing spans

An Observation only creates a span if a tracing observation handler and a Micrometer Tracing bridge/tracer are configured. In unit/integration tests, use the test tracer/reporter provided by the tracing bridge, or an appropriate in-memory exporter.

What to assert:
- The span name/operation name is correct.
- The parent span or trace ID is linked properly when a current context exists.
- Attributes have normalized values.
- Error events/status appear on technical failures.
- The span ends after the callback.
- No PII/secrets exist in attributes/events.

Do not assert span IDs or trace IDs with fixed literals; IDs are typically generated randomly. Assert parent-child relationships and shared trace IDs rather than comparing against a hardcoded string.

## 10. Testing ObservationPredicate and filtering

An ObservationPredicate can reject an Observation before handlers process it. If production configures a predicate, tests must verify:
- Allowed Observations are still received by handlers.
- Denied Observations do not produce metrics/spans according to policy.
- The predicate does not accidentally drop important error/slow operations.
- Name and context matching remain stable.

Example predicate:

~~~java
ObservationPredicate predicate =
        (name, context) -> !name.equals("internal.noisy.operation");
~~~

Unit tests for a predicate should cover both allow and deny cases. Avoid overly broad regexes or relying on method names that might change during refactoring if those names are not a stable contract.

## 11. Testing custom Observations in a Spring Boot context

A standalone registry unit test does not prove Spring Boot bean wiring, proxies, or auto-configuration. Use @SpringBootTest or an appropriate slice when you need to confirm:
- ObservationRegistry is injected properly.
- The custom bean uses the registry from the context.
- MeterRegistry/Observation handlers are auto-configured.
- Configuration properties and filters are applied.
- AOP annotations/proxies work if the operation uses annotation-based instrumentation.

Example context test:

~~~java
@SpringBootTest
class InventoryReservationIntegrationTest {

    @Autowired
    InventoryReservationService service;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void reservationCreatesExpectedMetric() {
        service.reserve("north", "SKU-1");

        assertThat(meterRegistry.getMeters())
                .isNotEmpty();
    }
}
~~~

This is a skeleton. In a real test, assert the exact meter name, tag set, and count rather than only checking that the registry has any meter. If the application context has multiple instrumentations, use a dedicated registry or filter meters by name.

## 12. Testing context propagation across async/reactive boundaries

An Observation context can be propagated within the same thread or across framework integrations. When code switches to an executor or reactive pipeline, tests must confirm that the context is propagated according to the mechanism the application uses.

Cases to cover:
- A thread pool task running after the request thread has finished.
- A CompletableFuture continuation on a different executor.
- A Reactor pipeline switching schedulers.
- A message consumer receiving trace context from headers.
- A custom executor configured with a TaskDecorator/context propagation setup.

Do not assume ThreadLocal automatically follows into a new thread. Use Micrometer Context Propagation or native Spring/Reactor/Tracing integrations where appropriate; verify the version and configuration.

Tests should assert the trace ID/parent relationship or observation context value inside the async callback. Use a latch/future to synchronize the test; do not use arbitrary sleep calls to wait for background work.

## 13. Testing cardinality and privacy regressions

A custom Observation may add tags based on input. Tests should feed many different values and confirm that meter IDs remain within defined limits.

Examples:
- Call the operation with many SKUs while verifying the metric tags only include warehouse and operation.
- Pass an email canary and confirm it does not appear in tags/span attributes.
- Pass an unknown warehouse and confirm it is normalized to unknown.
- Throw an exception containing a fake token and confirm the message is not copied into metric tags.

Do not test only a single request. Cardinality regressions only show up when invoking with many distinct inputs.

## 14. Testing duplicate observations

A custom business Observation may be nested inside an HTTP server Observation or a database Observation. Nesting is valid when it represents distinct operations. Duplication occurs when two instrumentations describe the same operation and cause metrics/spans to be double-counted.

Tests should verify:
- An inbound request creates the expected server observation.
- The custom operation creates one child observation if expected.
- Repository instrumentation is not duplicated by a custom wrapper with the same name/meaning.
- Timer/counter counts do not double unintentionally.
- The span tree reflects the intended boundaries.

Do not try to assert that the entire trace has exactly one span; a valid request can legitimately create multiple spans for HTTP, DB, messaging, and custom business operations.

## 15. Troubleshooting

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Handler does not receive Observation | Different registry instance or handler not registered | Check registry wiring and observationConfig |
| Start recorded but no stop | Manual lifecycle missing finally or test did not wait for async | Use observe() or ensure terminal path |
| Context name right but tags missing | Tags added after handler callback or different convention | Check lifecycle and KeyValues API |
| Timer does not appear | Meter observation handler not registered | Configure handler/Actuator metrics |
| Timer count is 0 | Callback did not run or meter query used wrong tags | Assert operation and available meter IDs |
| Span does not appear | Tracing bridge/handler not configured | Check tracer and tracing auto-configuration |
| Span has no parent | Context not propagated across thread/process | Check executor/Reactor/message headers |
| Test passes alone but fails in suite | Shared global registry/state | Use isolated registry and cleanup |
| Duplicate spans/timers | Custom Observation overlaps auto-instrumentation | Separate operation boundaries and remove redundant instrumentation |
| Flaky test duration | Exact timing assertion or fixed sleep | Assert presence/range and use synchronization |
| Metric cardinality grows | Dynamic input used as tag | Allowlist/normalize and test with multiple inputs |
| PII in context | Copying request data/exception message into tags | Source minimization and canary assertions |

## 16. Playbook: testing a custom Observation before release

**Scenario:** A team adds an Observation for inventory reservation and needs to verify the telemetry is accurate.

1. Write a unit test with an isolated ObservationRegistry.
2. Register a recording handler and assert name/contextual name.
3. Assert low-cardinality tags and high-cardinality fields per policy.
4. Test success, exception, and cancellation paths.
5. Assert start/stop runs once per operation.
6. Configure MeterObservationHandler in the test and verify Timer/count.
7. Use a test tracer/reporter to verify span name, parent, and error.
8. Test async/context propagation if the operation crosses threads or processes.
9. Send many SKU/user inputs and verify meter cardinality does not grow with identifiers.
10. Send a synthetic PII canary and verify it does not appear in metrics/traces/logs.
11. Check whether the custom observation overlaps auto-instrumentation.
12. Run a Spring Boot integration test to verify the registry/handlers are wired like production.

Once tests pass, use a staging Collector/test backend if you modified the exporter or OTLP pipeline. You do not need to make every unit test depend on a running telemetry backend.

## 17. Self-check exercises

**Exercise 1 — Lifecycle.** Why must a custom Observation test assert both onStart and onStop? What happens if the callback throws an exception?

**Exercise 2 — Registry.** Why should each test have its own ObservationRegistry instead of using a global registry?

**Exercise 3 — Tags.** What bugs can a test miss if it only asserts the Observation name without asserting tags?

**Exercise 4 — Metrics.** Why does a recording ObservationHandler alone not prove a Timer was created in MeterRegistry?

**Exercise 5 — Tracing.** Why shouldn't you assert a trace ID using a fixed literal? What relationship should you assert instead?

**Exercise 6 — Async.** Why can context be lost when a callback runs on a different executor?

**Exercise 7 — Cardinality.** What test design catches a SKU/customer ID accidentally becoming a metric tag?

**Exercise 8 — Duplicate.** When are two nested observations valid and when are they duplicate instrumentation?

### Suggested answers

1. Start/stop proves the full lifecycle completed; a failing callback must still stop the observation and preserve the error context.
2. Avoids state/handler leaks between tests and prevents test results from depending on execution order.
3. Tags may be missing/wrong, dynamic, or contain PII; checking the name alone is not enough.
4. A recording handler only observes lifecycle callbacks; a meter observation handler and MeterRegistry are required to produce Timers.
5. IDs are randomly generated. Assert the same trace ID and proper parent-child relationship.
6. Context is typically bound to execution context/ThreadLocal; another thread does not inherit it automatically.
7. Invoke the operation with many distinct IDs and assert that the number of Meter.Id/tag values remains bounded and excludes those IDs.
8. An HTTP server observation containing a business operation child is valid; two instrumentations measuring the same operation and counting twice is a duplicate.

## 18. Official references

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, registry, handlers, and conventions.
- [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/observation/testing.html): test utilities and verifying Observations.
- [Micrometer Observation — API](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html): creating custom Observations and managing lifecycle.
- [Micrometer Metrics — Testing](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter registry, meter types, and measurements.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridge, spans, and context propagation.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): application context and integration testing.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers, and auto-configuration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): context across process boundaries.
- [OpenTelemetry — Testing](https://opentelemetry.io/docs/languages/java/instrumentation/): Java instrumentation and test integration concepts.

**Takeaway:** Test custom Observations with an isolated registry and handler to verify name, context, tags, errors, and lifecycle. To prove metrics or tracing work, check MeterRegistry and a test tracer/reporter separately; a recording handler does not prove an exporter sent data. Test success/error paths, async propagation, cardinality, PII, and duplicate instrumentation. Keep unit tests independent of telemetry backends; only use end-to-end tests when changing exporters, the Collector, or cross-process propagation.
