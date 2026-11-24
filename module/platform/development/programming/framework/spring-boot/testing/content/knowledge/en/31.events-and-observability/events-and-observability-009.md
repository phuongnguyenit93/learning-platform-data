# Observation, Trace Context, and Avoiding External Exporter Dependencies in Spring Boot Testing

## 1. Lesson Goals

When a Spring Boot service is instrumented to produce metrics and distributed traces, testing can suffer from a design flaw: **JUnit tests only pass if an external OTLP collector, Zipkin, Tempo, Jaeger, or another telemetry backend is running**. This makes the suite slow, network-flaky, hard to isolate, and occasionally leaks test data into production services.

An application may do all three things well, yet **they are not the same check**:

1. **Creating an Observation:** the business method initializes, opens scope, records events/errors, and stops the observation properly.
2. **Carrying trace context:** parent/child spans share a trace ID, scopes do not leak across requests, and context propagates across executors/HTTP when configured.
3. **Exporting data:** an exporter/reporter serializes and transmits spans/metrics to an external endpoint or backend.

This lesson shows how to separate those layers so tests run fast, deterministically, and **without depending on a network exporter**. The core code uses **Java 17+, Spring Boot 3.5.x, Micrometer Observation, `micrometer-tracing-test`, JUnit Jupiter, AssertJ**, and an in-memory `ObservationHandler`. The test project **needs no Docker, Internet, HTTP server, or collector**. More complex HTTP propagation/exporter examples are described separately at their exact verification level, never misattributed as things proven by unit tests.

### 1.1. Reading the Exact Boundaries

```text
ShippingService.dispatch(shipmentId)
              |
              v
      Micrometer Observation
       start/scope/error/stop
              |
              v
       ObservationRegistry
              |
     +--------+-------------+
     |                      |
 test ObservationHandler   tracing handler, if registered
 (in-memory recorder)       |
                            v
                         Tracer/Span
                            |
                      exporter, if present
                            |
                        OTLP/Zipkin
                            |
                    collector/remote backend
```

Simply creating an `ObservationRegistry` **does not automatically generate a span with a traceId**. A tracing-integration `ObservationHandler` is needed, or a `Tracer` must be used directly. Likewise, having a `Tracer` does not by itself prove spans were successfully sent by an exporter.

## 2. Core Concepts

| Concept | Role | What Tests Should Verify |
|---|---|---|
| `Observation` | Lifecycle of an operation | `start`, `openScope`, `event`, `error`, `stop` |
| `ObservationRegistry` | Registry holding config, handlers, predicates/conventions | Proper handler registration and current observation in scope |
| `ObservationHandler` | Receives callbacks on lifecycle transitions | Records exact name, outcome, parent, exception |
| `Observation.Context` | Data/tags/parent linked to an observation | Low/high cardinality, name, and error |
| `Tracer` | Create/current/close spans | `currentSpan()`, parent span, IDs |
| `Span` | Individual trace unit with trace ID/span ID | Child shares trace ID yet has different span ID |
| `traceparent` | W3C HTTP distributed trace context | Actual header in outbound HTTP request |
| `ContextSnapshot` | Micrometer Context Propagation snapshot | Restores context across thread boundaries |
| `ContextPropagatingTaskDecorator` | Wraps tasks to transfer context | Worker reads parent and cleans up properly |
| `SpanExporter` | Pushes spans to another system | Fake/in-memory reporter or local protocol stub |
| `MeterRegistry` | Stores/exports metrics | Timer/counter/low-cardinality labels |
| MDC | Thread-local log correlation data | `traceId` when proper tracing integration is configured |

**Distinguish the two tool families:** `Micrometer Observation` is the unified abstraction for metrics/tracing and operation lifecycles; `Micrometer Tracing` is the `Tracer`, `Span`, scope, and propagation API. Observations can run without a tracer, and trace context tests can run without exporting spans anywhere.

### 2.1. Logging, Metrics, and Tracing Differ

Logs describe discrete events; metrics capture aggregated numbers; traces track execution paths across spans and services. A trace ID appearing in logs **is only correlation**, not proof that a span was sampled, flushed, and stored at a collector.

A successfully dispatched shipment can be instrumented with:
- Observation name: `shipment.dispatch` — stable.
- Low-card tags: `component=shipping`, `outcome=success` or `failure`.
- High-card tag: `shipment.id=SHIP-101`, if allowed in traces.
- Events: `shipment.accepted`, `inventory.ready`.
- Error: `IllegalStateException` if inventory reservation fails.

Never generate a brand new observation name per ID, such as `shipment.dispatch.SHIP-101`: that blows up metric time series and prevents aggregation.

## 3. Observation Lifecycle Must Be Closed Properly

Typical flow:

```java
Observation obs = Observation
        .createNotStarted("shipment.dispatch", registry)
        .lowCardinalityKeyValue("component", "shipping")
        .highCardinalityKeyValue("shipment.id", shipmentId)
        .start();

try (Observation.Scope scope = obs.openScope()) {
    doBusinessWork();
    obs.event(Observation.Event.of("shipment.accepted"));
} catch (RuntimeException ex) {
    obs.error(ex);
    throw ex;
} finally {
    obs.stop();
}
```

This is an **illustrative method fragment**: `registry`, `shipmentId`, and `doBusinessWork()` must be declared in a real class. The complete project is provided in Section 8.

- `createNotStarted`: creates an unstarted observation.
- `start()`: begins the lifecycle, typically triggering `ObservationHandler.onStart`.
- `openScope()`: sets the observation as current on the thread so nested observations acquire a parent.
- `event(...)`: marks a milestone inside the observation; not a Spring `@EventListener`.
- `error(ex)`: notifies handlers of an error (do not assume it happens automatically when an exception is thrown).
- `stop()`: ends the lifecycle, triggering `onStop`/timer/span processing.

**Closing the scope does not replace stop, and stop does not replace closing the scope.** Use `try-with-resources` for the scope, and `finally` for stop. Even on errors, the current observation/trace context must be cleaned up; otherwise a pooled thread can inherit a previous request's parent.

### 3.1. Parent/Child Observations

```text
shipment.dispatch.start()
  openScope() → current = shipment.dispatch
    inventory.reserve.start()
      parent = shipment.dispatch
      openScope() → current = inventory.reserve
      close child scope
    inventory.reserve.stop()
  close parent scope
shipment.dispatch.stop()
current observation = previous value, usually null
```

In a registry with suitable handlers, `Observation.Context.getParentObservation()` can be used to assert the relationship. However, a **parent Observation** relationship is not yet proof of a **real parentSpanId**; a tracing bridge/handler translates observations into tracing spans.

### 3.2. Error Events in Nested Observations

If `inventory.reserve` throws an exception:
1. Child calls `Observation.error(ex)`, then `stop()`.
2. Exception propagates to parent.
3. Parent calls `Observation.error(ex)`, sets `outcome=failure`, then `stop()`.
4. Scope is properly restored despite the exception.

If a test asserts only the business exception while ignoring the observation, it does not prove instrumentation worked. If code merely runs `finally { observation.stop(); }` without marking the error, tracing/metrics handlers will not know the span failed.

## 4. Low Cardinality and High Cardinality

Micrometer supports:
- **Low cardinality:** a controlled set of values, usable in both metrics and traces. Examples: `component=shipping`, `outcome=success|failure`, `operation=reserve`.
- **High cardinality:** a nearly unbounded set of values, normally included only in traces. Examples: shipment ID, request ID, dynamic path (subject to privacy considerations).

Illustrative snippet:

```java
Observation.createNotStarted("shipment.dispatch", registry)
        .lowCardinalityKeyValue("component", "shipping")
        .highCardinalityKeyValue("shipment.id", "SHIP-101");
```

Strictly avoid `shipment.id`, `customer.email`, `user.id`, raw IDs in URLs, or request payloads as low-cardinality metric tags. Every unique value creates additional time series, driving up memory, cardinality, and cost. High cardinality is also not a license to record PII: apply allowlists and redaction before writing to spans or logs.

### 4.1. Metric/Observation Names Have Cardinality Too

`http.server.requests`, `shipment.dispatch`, and `inventory.reserve` are stable names. Never concatenate user IDs into observation names or URI template labels. For HTTP, tag the route template `/shipments/{id}` instead of tagging each raw path `/shipments/12345` as a separate metric label.

### 4.2. Context Propagation Is Not Security Propagation

A `traceId` is an observability correlation marker, not authentication proof. Client-sent HTTP `traceparent` headers can be spoofed. Baggage is not an authorization token either. When user/tenant identity is required, validate authentication/permissions first, then attach only safe metadata.

## 5. Trace ID, Span ID, and Scope

A trace might look like:

```text
HTTP incoming request
  traceId = same-trace
  spanId  = server-A
    shipment.dispatch
      traceId = same-trace
      spanId  = internal-B
        inventory.reserve
          traceId = same-trace
          spanId  = internal-C
```

Strings in the diagram are **illustrative labels**, not valid W3C trace IDs. In a real test, **never hardcode** a randomly generated `traceId`/`spanId`.

Instead:
- `child.context().traceId()` equals `parent.context().traceId()`.
- `child.context().spanId()` differs from `parent.context().spanId()`.
- Inside the child scope, `tracer.currentSpan()` is the child.
- Upon closing the child scope, the current span reverts to the parent.
- Upon closing the parent scope, the current span reverts to its prior state (usually null).
- Upon finishing, spans call `end()` so the reporter/in-memory tracer observes the result.

### 5.1. Scope Differs from Span Lifecycle

A `Span` can be created/started yet **not be in the current scope**. To make it the current span, open a `Tracer.SpanInScope` via `tracer.withSpan(span)` (per the Micrometer Tracing API). Closing the scope does not end the span; `span.end()` is still required.

```java
Span child = tracer.nextSpan().name("inventory.reserve").start();
try (Tracer.SpanInScope scope = tracer.withSpan(child)) {
    doWork();
} finally {
    child.end();
}
```

This is a fragment assuming `tracer` and `doWork()` are provided, not a standalone file. `currentSpan()` on a new thread or after closing the scope **can be null**, and that can be the exact expected result.

### 5.2. Sampling Differs from Instrumentation

Even when code creates observations/spans:
- Sampling may choose not to export the trace.
- The exporter may be disabled.
- The collector may be unavailable.
- The batch processor may not have flushed yet.
- A span processor may filter data.
- A handler or observation predicate may skip certain observations.

Therefore, “created an observation” must never be conflated with “backend received spans”. When testing a real exporter, set controlled sampling (e.g., `management.tracing.sampling.probability=1.0`) and use a fake/in-memory exporter or mock HTTP endpoint. If `management.tracing.enabled=false`, setting sampling to 1.0 **does not turn the tracer back on**.

## 6. Choosing the Right Test Level

| What Needs to Be Proven | Appropriate Setup | External Exporter Needed? |
|---|---|---|
| Business output or exception | Plain JUnit/Mockito | No |
| Observation start/stop/error/tags | `ObservationRegistry` + in-memory handler or `TestObservationRegistry` | **No** |
| Parent/child Observation | Nested scopes + `Observation.Context` | No |
| Tracer currentSpan and parent-child IDs | `micrometer-tracing-test SimpleTracer` | **No** |
| Spring DI/ObservationHandler auto-registration | `@SpringBootTest` + Actuator + in-memory recorder | No |
| HTTP `traceparent` propagation | Boot-managed HTTP client + tracing bridge + local mock HTTP server | No remote collector needed |
| OTLP export serialization | In-memory exporter/local fake collector | No remote service needed |
| Backend actually displays traces | Dedicated smoke/operations test | Backend needed, not a unit test |
| Observability overhead/performance | Benchmark/load test | Depends on goal |

Each test should have **a focused verification scope**. Never pull every APM/tracing/export dependency into every `@SpringBootTest` just to assert a tag.

## 7. Spring Boot 3.5 Testing Defaults and Avoiding Export

According to Spring Boot 3.5 documentation:
- In `@SpringBootTest`, tracing reporting components are **not auto-configured to export externally** as in production; this reduces test side effects.
- Non-in-memory `MeterRegistry` instances are also not auto-configured to export as usual.
- In sliced tests with `@AutoConfigureObservability`, Boot can provide an `ObservationRegistry`, an in-memory `MeterRegistry`, and a **no-op `Tracer`**; data is not exported in sliced tests simply because of the annotation.
- Use `@AutoConfigureObservability` when tests genuinely need observability configuration; it **does not mean** all spans carry real trace IDs.
- Custom `SpanExporter` or reporter beans created by the application may still run in tests unless designed with appropriate conditionals or mock overrides.

### 7.1. Confirmed Properties for Spring Boot 3.5.x

```properties
# When tests do not need real tracing:
management.tracing.enabled=false

# Disable specific exporters when their dependencies are present:
management.otlp.tracing.export.enabled=false
management.zipkin.tracing.export.enabled=false

# If metrics exporters are present, choose an appropriate policy:
management.defaults.metrics.export.enabled=false
management.otlp.metrics.export.enabled=false
```

These properties eliminate exporter dependencies and clarify test boundaries. However:
- `management.tracing.enabled=false` disables **tracing auto-configuration**, not only network export; tests checking real propagation **should not** disable tracing.
- Disabling OTLP/Zipkin does not automatically disable custom publishers, Datadog/Wavefront exporters, or external SDK agents.
- If an exporter class is not on the classpath, it will not be created even without these properties.
- Spring Boot **4.x** can rename packages/properties; never copy 4.x properties into a 3.5 project assuming they apply.

### 7.2. Configuring Tests Instead of Altering Production Code

- `src/test/resources/application.properties`: shared flags for the test module.
- `@SpringBootTest(properties = "...")`: direct per-test-class overrides.
- `@ActiveProfiles("test")`: loads `application-test.properties`.
- `@TestConfiguration`: registers test-only handlers/tracers/reporters.
- `@ConditionalOnEnabledTracing`: lets custom reporting components turn off automatically when tracing is disabled.
- `@MockitoBean`: replaces a network adapter when the goal is purely call verification.
- Network policy/test sandbox: when formally enforcing “tests open zero outbound sockets”.

**Avoid** embedding production OTLP credentials in test profiles or spinning up cloud collectors just to run the suite. If using `@AutoConfigureObservability` in a full context, check the exact auto-config scope and disable real exporters if present.

## 8. Complete Java 17+ / Spring Boot 3.5.8 Project

Structure:

```text
build.gradle
src/main/java/com/example/observe/
    ObserveApplication.java
    ShipmentReceipt.java
    ShippingService.java
    RecordingObservationHandler.java
src/test/resources/application.properties
src/test/java/com/example/observe/
    ShippingObservationUnitTest.java
    ShippingObservationSpringTest.java
    TraceContextTest.java
```

### 8.1. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-tracing-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- Actuator brings in Micrometer Observation infrastructure; tests can inject `ObservationRegistry`.
- `micrometer-tracing-test` is strictly in **test scope**, providing the in-memory `SimpleTracer`.
- The project intentionally **omits** `opentelemetry-exporter-otlp`, `zipkin-reporter-brave`, or Micrometer tracing bridges at runtime.
- **Because no bridge is present**, `ShippingService` in this project is tested as an Observation without automatically producing distributed traces. `TraceContextTest` is a separate test suite exercising `SimpleTracer`.
- The Spring Boot BOM manages compatible dependency versions; never arbitrarily mix Micrometer 1.15 with off-BOM versions.
- No Servlet starter, database, or Docker.

Running the commands requires an existing Gradle wrapper (`gradlew`, `gradlew.bat`). `build.gradle` does not generate the wrapper automatically.

### 8.2. Application Class

File `src/main/java/com/example/observe/ObserveApplication.java`:

```java
package com.example.observe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObserveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObserveApplication.class, args);
    }
}
```

### 8.3. Diagnostic Result DTO

File `src/main/java/com/example/observe/ShipmentReceipt.java`:

```java
package com.example.observe;

public record ShipmentReceipt(
        String shipmentId,
        boolean parentWasCurrent,
        String threadName) {
}
```

`parentWasCurrent` is strictly a **test seam**. Ordinary production business DTOs do not need to expose internal observability flags. It lets tests verify scoping without requiring tracing/exporters to be active.

### 8.4. Real Service Using the Observation API

File `src/main/java/com/example/observe/ShippingService.java`:

```java
package com.example.observe;

import java.util.Objects;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final ObservationRegistry registry;

    public ShippingService(ObservationRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public ShipmentReceipt dispatch(
            String shipmentId,
            boolean inventoryRejected) {

        Objects.requireNonNull(shipmentId, "shipmentId");

        Observation outer =
                Observation.createNotStarted(
                        "shipment.dispatch", registry)
                    .lowCardinalityKeyValue("component", "shipping")
                    .highCardinalityKeyValue("shipment.id", shipmentId)
                    .start();

        try (Observation.Scope scope = outer.openScope()) {
            boolean correctlyScoped =
                    registry.getCurrentObservation() == outer;

            reserveInventory(inventoryRejected);

            outer.lowCardinalityKeyValue("outcome", "success");
            outer.event(
                    Observation.Event.of("shipment.accepted"));

            return new ShipmentReceipt(
                    shipmentId,
                    correctlyScoped,
                    Thread.currentThread().getName());
        } catch (RuntimeException ex) {
            outer.lowCardinalityKeyValue("outcome", "failure");
            outer.error(ex);
            throw ex;
        } finally {
            outer.stop();
        }
    }

    private void reserveInventory(boolean reject) {
        Observation child =
                Observation.createNotStarted(
                        "inventory.reserve", registry)
                    .lowCardinalityKeyValue(
                        "component", "inventory")
                    .start();

        try (Observation.Scope scope = child.openScope()) {
            if (reject) {
                throw new IllegalStateException(
                        "Inventory unavailable");
            }
            child.event(
                    Observation.Event.of("inventory.ready"));
        } catch (RuntimeException ex) {
            child.error(ex);
            throw ex;
        } finally {
            child.stop();
        }
    }
}
```

**Reading the logic carefully:**
- `shipment.dispatch` is the outer observation, given a stable name.
- `inventory.reserve` is created inside the outer scope, so it gets a parent observation.
- `shipment.id` is high-cardinality; `component/outcome` are low-cardinality.
- Success emits a `shipment.accepted` event and stops both child and parent.
- Failure marks the exception on both child and parent; `finally` always stops both.
- `registry.getCurrentObservation()` is read **inside the scope**, not after the scope closes.
- No outbound network calls, tracer bridges, or exporters exist in the service.

### 8.5. In-Memory Handler Recording Lifecycle

File `src/main/java/com/example/observe/RecordingObservationHandler.java`:

```java
package com.example.observe;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

import org.springframework.stereotype.Component;

@Component
public class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    public record Entry(
            String stage,
            String name,
            String parentName,
            String outcome,
            String shipmentId,
            String errorClass,
            String eventName) {
    }

    private final ConcurrentLinkedQueue<Entry> entries =
            new ConcurrentLinkedQueue<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        add("START", context, null);
    }

    @Override
    public void onStop(Observation.Context context) {
        add("STOP", context, null);
    }

    @Override
    public void onError(Observation.Context context) {
        add("ERROR", context, null);
    }

    @Override
    public void onEvent(
            Observation.Event event,
            Observation.Context context) {
        add("EVENT", context, event.getName());
    }

    private void add(
            String stage,
            Observation.Context context,
            String eventName) {
        KeyValue outcome =
                context.getLowCardinalityKeyValue("outcome");

        KeyValue shipment =
                context.getHighCardinalityKeyValue("shipment.id");

        String parent = context.getParentObservation() == null
                ? null
                : context.getParentObservation().getName();

        entries.add(new Entry(
                stage,
                context.getName(),
                parent,
                outcome == null ? null : outcome.getValue(),
                shipment == null ? null : shipment.getValue(),
                context.getError() == null
                        ? null
                        : context.getError()
                            .getClass().getSimpleName(),
                eventName));
    }

    public List<Entry> forName(String name) {
        return entries.stream()
                .filter(e -> name.equals(e.name()))
                .toList();
    }

    public List<Entry> forNameAndStage(
            String name, String stage) {
        return forName(name).stream()
                .filter(e -> stage.equals(e.stage()))
                .toList();
    }

    public void clear() {
        entries.clear();
    }
}
```

**Why not mock `ObservationRegistry`?** The goal is testing real `start/scope/error/stop`. A Mockito mock registry would not manage scopes and handlers with real semantics. Using a real registry + in-memory handler runs the full framework lifecycle while swapping only the **export destination** for an internal queue.

The demo marks the recorder with `@Component` so Spring auto-registers the handler via Actuator; production should never retain every observation in an unbounded queue. In a real project, place `RecordingObservationHandler` in the **test source set** or `@TestConfiguration` rather than as a runtime component. Here it sits in main sources so both plain JUnit (manual instantiation) and Spring integration tests share one implementation.

### 8.6. Test-Only Properties

File `src/test/resources/application.properties`:

```properties
management.tracing.enabled=false
management.otlp.tracing.export.enabled=false
management.zipkin.tracing.export.enabled=false
management.defaults.metrics.export.enabled=false
```

When testing **Observation lifecycles alone**, no tracer or exporter is needed. When switching to tests needing real trace propagation, **remove `management.tracing.enabled=false` in the corresponding test class/profile**, while keeping exporters disabled or using an in-memory reporter.

## 9. Plain JUnit: 5 Cases Without Spring Context

File `src/test/java/com/example/observe/ShippingObservationUnitTest.java`:

```java
package com.example.observe;

import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingObservationUnitTest {

    private ObservationRegistry registry;
    private RecordingObservationHandler recorder;
    private ShippingService shipping;

    @BeforeEach
    void setUp() {
        registry = ObservationRegistry.create();
        recorder = new RecordingObservationHandler();

        registry.observationConfig()
                .observationHandler(recorder);

        shipping = new ShippingService(registry);
    }

    @Test
    void successRecordsLifecycleAndEvent() {
        ShipmentReceipt result =
                shipping.dispatch("SHIP-A", false);

        assertThat(result.shipmentId()).isEqualTo("SHIP-A");
        assertThat(result.parentWasCurrent()).isTrue();

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "START")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "EVENT"))
            .extracting(RecordingObservationHandler.Entry::eventName)
            .containsExactly("shipment.accepted");

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "STOP")).hasSize(1);
    }

    @Test
    void parentAndChildAreRelated() {
        shipping.dispatch("SHIP-B", false);

        var child = recorder.forNameAndStage(
                "inventory.reserve", "START").get(0);

        assertThat(child.parentName())
                .isEqualTo("shipment.dispatch");

        assertThat(registry.getCurrentObservation()).isNull();
    }

    @Test
    void tagsUseIntendedCardinality() {
        shipping.dispatch("SHIP-C", false);

        var finished = recorder.forNameAndStage(
                "shipment.dispatch", "STOP").get(0);

        assertThat(finished.outcome()).isEqualTo("success");
        assertThat(finished.shipmentId()).isEqualTo("SHIP-C");
        assertThat(finished.errorClass()).isNull();

        // outcome read from low-cardinality;
        // shipmentId read from high-cardinality in recorder.
    }

    @Test
    void exceptionIsRecordedAndScopesAreClosed() {
        assertThatThrownBy(
                () -> shipping.dispatch("SHIP-D", true))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Inventory unavailable");

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "ERROR")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "ERROR")).hasSize(1);

        var parentStop = recorder.forNameAndStage(
                "shipment.dispatch", "STOP").get(0);

        assertThat(parentStop.outcome()).isEqualTo("failure");
        assertThat(parentStop.errorClass())
                .isEqualTo("IllegalStateException");

        assertThat(registry.getCurrentObservation()).isNull();
    }

    @Test
    void consecutiveInvocationsDoNotLeakScope() {
        shipping.dispatch("SHIP-E", false);

        assertThat(registry.getCurrentObservation()).isNull();

        shipping.dispatch("SHIP-F", false);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP")).hasSize(2);

        assertThat(registry.getCurrentObservation()).isNull();
    }
}
```

**Expected outcome**: 5 test methods verifying each slice of the contract: start/stop/event, parent relationship, tag category, exception, and cleanup. No `Thread.sleep`, no collector host, and no hardcoded random IDs.

### 9.1. Using TestObservationRegistry When AssertJ Helpers Are Wanted

Micrometer provides `io.micrometer:micrometer-observation-test` with `TestObservationRegistry` and fluent assertions:

```groovy
testImplementation 'io.micrometer:micrometer-observation-test'
```

```java
TestObservationRegistry registry =
        TestObservationRegistry.create();

new ShippingService(registry)
        .dispatch("SHIP-T", false);
```

This is a **fragment** (`import io.micrometer.observation.tck.TestObservationRegistry`); you can use the BOM-matched fluent assertion API to verify stopped observations, tags, and errors. The main project uses a custom handler to avoid version-specific fluent matcher coupling while still exercising real Micrometer lifecycles. A custom handler is not required for every app; it simply provides a transparent test seam here.

## 10. @SpringBootTest: Spring Wiring Without Network Export

File `src/test/java/com/example/observe/ShippingObservationSpringTest.java`:

```java
package com.example.observe;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = {
        "management.tracing.enabled=false",
        "management.otlp.tracing.export.enabled=false",
        "management.zipkin.tracing.export.enabled=false"
})
class ShippingObservationSpringTest {

    @Autowired
    ShippingService shipping;

    @Autowired
    RecordingObservationHandler recorder;

    @BeforeEach
    void clearRecorder() {
        recorder.clear();
    }

    @Test
    void springRegistryNotifiesObservationHandler() {
        ShipmentReceipt result =
                shipping.dispatch("BOOT-A", false);

        assertThat(result.parentWasCurrent()).isTrue();

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP"))
            .hasSize(1);
    }

    @Test
    void exceptionIsStillObservedInSpringContext() {
        assertThatThrownBy(
                () -> shipping.dispatch("BOOT-B", true))
            .isInstanceOf(IllegalStateException.class);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "ERROR"))
            .hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP"))
            .hasSize(1);
    }

    @Test
    void childIsVisibleWithoutRemoteCollector() {
        shipping.dispatch("BOOT-C", false);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "START"))
            .hasSize(1);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "STOP"))
            .hasSize(1);
    }
}
```

Contains **3 integration test methods**. They verify Spring injects `ObservationRegistry` into the service and auto-registers the `RecordingObservationHandler` bean into the registry via Actuator auto-config. Unlike plain JUnit, this proves **Spring configuration and wiring**.

**Do not overclaim:** Having no runtime exporter dependencies means this test needs no collector; however, passing here does not prove “an app with custom network reporters sends zero traffic”. When compliance requires zero network access, enforce network firewalls/test network namespaces or fake any socket-opening adapters.

### 10.1. What If a Slice Test Lacks ObservationRegistry?

In `@WebMvcTest`, `@DataJpaTest`, or other slices, `ObservationRegistry` may not be configured like a full Boot context. `@AutoConfigureObservability` can add a registry/no-op tracer/in-memory meter registry per Spring Boot 3.5 docs. However, a no-op `Tracer` will not supply “real span IDs” to assert. For testing business logic, inject a standalone test `ObservationRegistry` rather than enabling all of Actuator in a slice.

## 11. Testing Trace Context Without a Bridge or Exporter

`micrometer-tracing-test` supplies `SimpleTracer`, which creates spans and tracks current scopes in memory. It is separate from `ShippingService` above because the project intentionally omits a production tracing bridge.

File `src/test/java/com/example/observe/TraceContextTest.java`:

```java
package com.example.observe;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.test.simple.SimpleTracer;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TraceContextTest {

    @Test
    void childSharesTraceButHasDifferentSpanId() {
        SimpleTracer tracer = new SimpleTracer();

        Span parent = tracer.nextSpan()
                .name("shipment.dispatch").start();

        try (Tracer.SpanInScope parentScope =
                tracer.withSpan(parent)) {

            assertThat(tracer.currentSpan()).isSameAs(parent);

            Span child = tracer.nextSpan()
                    .name("inventory.reserve").start();

            try (Tracer.SpanInScope childScope =
                    tracer.withSpan(child)) {

                assertThat(child.context().traceId())
                    .isNotBlank()
                    .isEqualTo(parent.context().traceId());

                assertThat(child.context().spanId())
                    .isNotBlank()
                    .isNotEqualTo(parent.context().spanId());

                assertThat(tracer.currentSpan()).isSameAs(child);
            } finally {
                child.end();
            }

            assertThat(tracer.currentSpan()).isSameAs(parent);
        } finally {
            parent.end();
        }

        assertThat(tracer.currentSpan()).isNull();
    }

    @Test
    void explicitParentPreservesTraceContext() {
        SimpleTracer tracer = new SimpleTracer();

        Span parent = tracer.nextSpan().name("root").start();

        try {
            Span child = tracer.nextSpan(parent)
                    .name("child").start();

            try {
                assertThat(child.context().traceId())
                    .isEqualTo(parent.context().traceId());

                assertThat(child.context().spanId())
                    .isNotEqualTo(parent.context().spanId());
            } finally {
                child.end();
            }
        } finally {
            parent.end();
        }
    }

    @Test
    void plainExecutorDoesNotPropagateThreadLocalSpan()
            throws Exception {

        SimpleTracer tracer = new SimpleTracer();
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        Span root = tracer.nextSpan()
                .name("caller").start();

        try (Tracer.SpanInScope rootScope =
                tracer.withSpan(root)) {

            assertThat(tracer.currentSpan()).isSameAs(root);

            Future<Boolean> absent = executor.submit(
                    () -> tracer.currentSpan() == null);

            assertThat(absent.get(5, TimeUnit.SECONDS)).isTrue();

            Future<String> explicit = executor.submit(() -> {
                Span child = tracer.nextSpan(root)
                        .name("worker").start();

                try (Tracer.SpanInScope scope =
                        tracer.withSpan(child)) {
                    return child.context().traceId();
                } finally {
                    child.end();
                }
            });

            assertThat(explicit.get(5, TimeUnit.SECONDS))
                    .isEqualTo(root.context().traceId());
        } finally {
            root.end();
            executor.shutdownNow();
        }

        assertThat(tracer.currentSpan()).isNull();
    }

    @Test
    void closingNestedScopeRestoresPreviousSpan() {
        SimpleTracer tracer = new SimpleTracer();

        Span first = tracer.nextSpan().name("first").start();

        try (Tracer.SpanInScope firstScope =
                tracer.withSpan(first)) {

            Span second = tracer.nextSpan().name("second").start();

            try (Tracer.SpanInScope secondScope =
                    tracer.withSpan(second)) {
                assertThat(tracer.currentSpan()).isSameAs(second);
            } finally {
                second.end();
            }

            assertThat(tracer.currentSpan()).isSameAs(first);
        } finally {
            first.end();
        }

        assertThat(tracer.currentSpan()).isNull();
    }
}
```

This test suite has **4 cases**. The project total is **5 Observation unit + 3 Spring integration + 4 trace context = 12 `@Test` cases**.

**What this test can conclude:** parent/child share the same trace ID with different span IDs, `currentSpan` is restored upon closing scopes, and a plain `ExecutorService` does not propagate ThreadLocal trace context automatically. **What this test cannot conclude:** that `ShippingService` Observations produce real spans through a bridge, HTTP headers are injected, or exporters send spans. Those belong to higher test levels.

### 11.1. Do Not Hardcode Trace IDs

A test must not write:

```java
assertThat(tracer.currentSpan().context().traceId())
        .isEqualTo("0000000000000001");
```

This is an **illustrative anti-pattern**: trace IDs come from an implementation/generator and vary across runs. Assert IDs are non-blank and assert parent-child ID relationships as in the sample tests.

### 11.2. Passing Parent Span Objects in Tests Is Not Production Propagation

`plainExecutorDoesNotPropagateThreadLocalSpan` passes `nextSpan(root)` explicitly to demonstrate parent context on a child span. Production must never send mutable `Span` objects across HTTP, Kafka, or RPC. Production solutions must use:
- W3C `traceparent`/`tracestate` or a configured propagation format.
- `ContextSnapshot`/`ContextPropagatingTaskDecorator` for in-JVM executors.
- Reactor Context across reactive pipelines.
- Scope restoration/cleanup inside `finally`.

## 12. @Async and Context Propagation

### 12.1. Why Does traceId Disappear on Workers?

Micrometer Tracing normally stores the current span in a ThreadLocal in imperative code. When `@Async` or `ExecutorService.submit` hands work to a pooled worker thread, the caller's ThreadLocal context **does not move with it automatically**.

```text
Caller thread                 Worker thread
   currentSpan = A              currentSpan = null
   MDC traceId = A    ---->     MDC traceId = null
               without propagation
```

A buggy implementation can also leak MDC/traceId from a **previous** request on the same pooled worker thread if context is not properly restored/cleared.

### 12.2. ContextPropagatingTaskDecorator

Spring Framework 6.x provides `ContextPropagatingTaskDecorator`, using Micrometer Context Propagation to transfer contextual values into executor tasks.

This is a **configuration fragment**, not part of the runnable project in Section 8:

```java
@Bean
ThreadPoolTaskExecutor taskExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(40);
    executor.setThreadNamePrefix("observed-worker-");

    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());

    return executor;
}
```

Requires imports `@Bean`, `ThreadPoolTaskExecutor`, and `ContextPropagatingTaskDecorator`. When managed by Spring, the executor initializes and shuts down with the lifecycle. **Ensure `@Async` actually selects this exact executor**, e.g., `@Async("taskExecutor")`. Defining a decorated bean while the method runs on a different executor prevents propagation.

In Spring Boot 3.5, `spring.task.execution.propagate-context=true` enables propagation on Boot's auto-configured executor, yet does not automatically decorate a manually created `Executors.newFixedThreadPool()`. Check your version, auto-config, and actual executor selection.

### 12.3. Writing Meaningful Propagation Tests

A test must:
1. Open a parent span/observation scope on the caller.
2. Submit a task through the **real configured executor**.
3. Inside the worker thread, read `tracer.currentSpan()` or `registry.getCurrentObservation()`.
4. Assert traceId/context matches the parent; never hardcode random values.
5. Close the scope and await the task with `Future.get(timeout)`.
6. Submit a follow-up task and confirm no context leaked from the first run.

Never assert traceId on the caller thread alone and claim propagation works. Never use `Thread.sleep(100)` to guess the worker finished; that flakes on slow CI.

## 13. Reactor Context Differs from ThreadLocal

In WebFlux/Reactor, a publisher can switch threads via `publishOn` or `subscribeOn`, while the Reactor Context travels with the reactive sequence. That differs from an imperative JDBC service maintaining a simple ThreadLocal.

When testing tracing in WebFlux:
- Use `StepVerifier` so subscription actually happens.
- Inspect the current trace context inside executing operators, not just when assembling a `Mono`.
- If using Micrometer Context Propagation, confirm the Spring Boot/Project Reactor propagation mode for your exact version.
- Never `.block()` carelessly on event-loop threads.
- Never claim a `SimpleTracer` plain JUnit test proves WebFlux propagation across `publishOn`.
- Never mix JDBC ThreadLocal `@Transactional` with reactive `TransactionalOperator` assuming they share one context.

This is extended guidance; the runnable project tests only imperative Observation and a plain `ExecutorService` to avoid a reactive example lacking dependencies or full semantics.

## 14. HTTP traceparent and Propagation Across Service Boundaries

W3C Trace Context uses the `traceparent` header. A valid illustrative value:

```http
GET /v1/shipments/SHIP-101 HTTP/1.1
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

It encodes version, 16-byte trace ID, 8-byte parent ID, and flags. This example **is not an executed outbound request** in this lesson.

To test HTTP propagation at the right level:
- Use a Boot-managed `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder` with the app's instrumentation/tracing customizers applied.
- Enable a compatible Micrometer Tracing bridge/tracer/propagator.
- Keep tracing enabled while **disabling/mocking** the external reporter.
- Use a local `MockRestServiceServer`, `MockWebServer`, or WireMock to capture the outbound request.
- Assert the header was **generated by the real client**, rather than manually injecting `traceparent` in test code and calling it instrumented.
- Test incoming propagation via MockMvc/local HTTP server and assert the server/child context links to the parent when required.
- Verify trace flags/sampling and W3C/B3 formats per configuration.

**HTTP propagation cannot be inferred from `SimpleTracer` generating a valid traceId.** Verifying headers requires inspecting real HTTP requests in tests.

## 15. Testing Exporters Without Calling the Internet

When the requirement shifts to “did the reporter send the span properly?”, two solid approaches exist:

### 15.1. In-Memory Exporter (OpenTelemetry SDK)

An `InMemorySpanExporter` in the test-only OpenTelemetry SDK stores `SpanData` locally. The test will:
- Configure the SDK/bridge/SpanProcessor with the in-memory exporter.
- Execute instrumented code.
- Force-flush/shut down when testing exporter lifecycle.
- Assert span name, attributes, parent IDs, and error status.
- Reset the exporter between tests.

This is stronger than a recorder checking only `ObservationHandler`, yet still does not prove a real collector is reachable. Never add production `opentelemetry-exporter-otlp` alongside when only in-memory tests are needed.

### 15.2. Fake Reporter or Local HTTP Stub

When writing a custom reporter:
- Inject a fake implementation recording call arguments into a list/queue.
- Assert payloads and retry/error policies.
- Use a local mock server when verifying JSON/Protobuf/HTTP headers/timeouts.
- Block production endpoints in tests via config isolation.
- Shut down resources and background exporter threads after tests.

When verifying official exporters, a local mock collector beats a cloud endpoint: tests run offline without credentials, and you can deliberately inject timeouts, 500s, or 429s.

### 15.3. Do Not Conflate Measurement with Export Transport

Business Observation tests only need handler callbacks. Trace context tests need current spans/parents. Export tests need reporters. Production monitoring/backend readiness is an operations test, not a unit test.

## 16. Common Risks and Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Observation runs yet no traceId | No tracing bridge/handler | Distinguish Observation from Tracer |
| Tests require live Zipkin/Tempo/OTLP | Exporter enabled in tests | Fake/in-memory exporter, disable network |
| `@SpringBootTest` has no-op/missing Tracer | Test tracing reporting disabled | Use test tracer or targeted test config |
| `@AutoConfigureObservability` has no-op tracer | Slice test avoids exporters | Don't assert real span IDs on no-op |
| Missing `onStop` | Forgot `observation.stop` | Call `stop` in `finally` |
| Missing `onError` | Exception not marked | Call `observation.error(ex)` |
| Child observation lacks parent | Child not created inside parent scope | Open scope first, then create child |
| TraceId disappears on `@Async` | ThreadLocal doesn't propagate | TaskDecorator/ContextSnapshot |
| Trace/MDC leaks to next request | Scope never restored | `try-with-resources`/finally cleanup |
| Test asserts random traceId literal | Non-deterministic ID generator | Assert parent-child relationships |
| Test uses log snapshot | Timestamps/threads/order unstable | Assert semantics, not full log text |
| Using shipment ID as a metric tag | High-cardinality explosion | Bounded low-card labels |
| Sampling drops spans | Probability/processor filtering | Control sampling when testing export |
| Tracing disabled yet expecting `traceparent` | Disabled all tracing, not just exporter | Keep tracing on, export off |
| `traceparent` test passes because test injects header | Instrumentation untested | Inspect real outbound request |
| Custom reporter still hits network | Custom bean ignores Boot props | Disable/override custom bean in tests |
| Parallel tests lose records | Shared Spring context recorder | Per-test handler or test isolation |
| Boot 4 property names differ | Config copied from wrong version | Check Boot-version property appendix |
| Span created yet missing in backend | Exporter/sampling/flush/network | Test each layer separately |
| Flaky test timeout | Waiting with `Thread.sleep` | Bounded future/latch/await |
| External tokens leaked into traces | Uncontrolled high-card/PII | Redaction and allowlists |
| Sampling=1 yet zero spans | Missing tracing handler or disabled tracing | Check dependencies and handlers |
| Producer returns OK yet reporter fails in background | Asynchronous reporter | Fake reporter, flush, and log checks |

### 16.1. Short Debugging Checklist

1. Clarify whether the test aims to prove Observation, trace context, HTTP propagation, or exporter behavior.
2. Check dependencies: actuator/observation, tracing bridge, exporter.
3. Check that `ObservationRegistry` has the expected handlers.
4. Check `management.tracing.enabled` and exporter flags.
5. Verify `start`, `openScope`, `error`, and `stop` in code.
6. Audit low/high cardinality and PII.
7. Verify parent context propagates across threads/executors.
8. For HTTP, inspect requests from an instrumented client using a mock server.
9. For exporters, swap in an in-memory/local fake instead of cloud endpoints.
10. Read JUnit reports and background exporter warnings, not just build status.

## 17. Observability in Spring Boot Also Includes @Observed and @NewSpan

Spring Boot 3.5 supports opt-in annotation instrumentation when:
- `management.observations.annotations.enabled=true`.
- AspectJ/AOP dependency is declared appropriately (e.g., `spring-boot-starter-aop`).
- Methods are invoked **through a Spring proxy**, not via self-invocation.
- Annotations are not stacked onto an already auto-instrumented method causing duplicate observations.

Example **fragment**, not part of the demo:

```java
@Observed(name = "shipment.dispatch")
public Receipt dispatch(String id) {
    return doDispatch(id);
}
```

A test proving `@Observed` works requires a real Spring AOP context/proxy and configured observation registry. A plain JUnit `new ShippingService()` never triggers AOP. If you already instrument manually with `Observation.createNotStarted(...)`, do not accidentally add `@Observed` to the same method and double-count observations.

Similarly, `@NewSpan` requires proper tracing infrastructure; do not expect it to generate spans when tracing is disabled or no-op.

## 18. Expected Results and Execution Scope

The demo project contains **12 `@Test` methods**:
- 5 cases in `ShippingObservationUnitTest`: lifecycle, tags, parent, exception, cleanup.
- 3 cases in `ShippingObservationSpringTest`: Spring DI/ObservationHandler registration.
- 4 cases in `TraceContextTest`: trace/span IDs, explicit parent, executor ThreadLocal, and scope restoration.

### 18.1. Gradle Run Commands

Linux/macOS:

```bash
./gradlew test --tests "com.example.observe.ShippingObservationUnitTest"
./gradlew test --tests "com.example.observe.ShippingObservationSpringTest"
./gradlew test --tests "com.example.observe.TraceContextTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.observe.ShippingObservationUnitTest"
.\gradlew.bat test --tests "com.example.observe.ShippingObservationSpringTest"
.\gradlew.bat test --tests "com.example.observe.TraceContextTest"
```

If using a Maven wrapper with an equivalent `pom.xml`/BOM/Surefire setup:

```bash
./mvnw -Dtest=ShippingObservationUnitTest test
./mvnw -Dtest=ShippingObservationSpringTest test
./mvnw -Dtest=TraceContextTest test
```

These are **illustrative code samples and expected behavior**, **not proof that JUnit actually ran** in the current environment. Inspect `build/reports/tests/test/index.html` or `target/surefire-reports/`: discovered, executed, skipped, and failed counts, plus background log warnings. A `NO-SOURCE` task or `BUILD SUCCESSFUL` with skipped tests does not prove a runtime PASS.

The project uses Spring/Micrometer/JUnit dependencies and must run through the build tool, not standalone `javac` lacking the classpath. There is no fixed business stdout because the main class prints nothing; trace IDs, durations, and thread names can vary.

## 19. QA Checklist for This Lesson

- [ ] Distinguished Observation lifecycle, trace context, and export transport.
- [ ] Did not equate `ObservationRegistry` with a tracer generating real span IDs.
- [ ] Included an `ObservationHandler`/`TestObservationRegistry` to verify real callbacks.
- [ ] Tested `onStart`, `onStop`, `onEvent`, `onError`, including exception paths.
- [ ] Opened scope before creating child, asserting parent/child Observations.
- [ ] Closed scopes with `try-with-resources` and stopped in `finally`.
- [ ] Low-cardinality tags contain no record IDs or PII.
- [ ] High-cardinality attributes still obey privacy policy.
- [ ] Used `SimpleTracer`/in-memory SDK to test trace IDs without an exporter.
- [ ] Asserted IDs by relationship rather than snapshotting random traceIds.
- [ ] `@SpringBootTest` without external reporters requires no collector.
- [ ] Custom exporters/reporters are disabled or overridden in tests.
- [ ] `management.tracing.enabled=false` is not confused with disabling export only.
- [ ] When `traceparent`/B3 is needed, tested via real instrumented HTTP client/server.
- [ ] Did not claim `SimpleTracer` tests prove Micrometer tracing bridge wiring.
- [ ] When export semantics matter, used a fake/in-memory exporter or local stub.
- [ ] For `@Async`/Reactor, context propagation is verified on the worker/subscriber.
- [ ] Never used `Thread.sleep` for async assertions.
- [ ] Avoided tokens/PII in spans, logs, and baggage.
- [ ] Included a cleanup strategy for recorders/scopes/thread pools in parallel suites.
- [ ] Verified exact Boot 3.5 property names instead of copying Boot 4 configs blindly.
- [ ] Read real JUnit reports before reporting a runtime pass.

## 20. References

- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): ObservationRegistry, handlers, low/high cardinality.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): Micrometer Tracing, OTLP/Zipkin export.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): observability defaults and `@AutoConfigureObservability`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): tracing/exporter properties.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): `Observation`, `ObservationHandler` lifecycle.
- [Micrometer Tracing — Testing](https://docs.micrometer.io/tracing/reference/1.5/testing.html): `micrometer-tracing-test`, `SimpleTracer`.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): `Tracer`/`Span`/scope.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/purpose.html): ContextSnapshot, context restoration.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor/task context.
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): assertions and test reports.

**Conclusion:** Solid observability testing separates **Observation lifecycle**, **trace context**, and **export transport**. Having an `ObservationRegistry` does not guarantee spans are created; `SimpleTracer` suffices to verify trace ID relationships without a collector; `@SpringBootTest` with exporter isolation and an in-memory handler tests wiring. When verifying `traceparent`, test an actually instrumented HTTP client against a mock endpoint; when verifying OTLP export, test a fake/in-memory exporter separately. Never turn ordinary business tests into Internet-dependent tests, and never treat a traceId in a log line as proof an exporter delivered successfully.