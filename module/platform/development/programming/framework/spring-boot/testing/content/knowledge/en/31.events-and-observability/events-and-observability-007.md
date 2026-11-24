# @AutoConfigureObservability by Spring Boot Version Support

> **Module:** Spring Boot – testing  
> **Group:** Events and Observability  
> **Topic:** `@AutoConfigureObservability` by version support  
> **Goal:** Properly understand the role of Micrometer Observation in tests, the scope of Spring Boot 3.x's `@AutoConfigureObservability`, changes in Spring Boot 4.x, metrics/tracing configuration and test slices, and testing event observation in JUnit/JVM in-memory without depending on a real exporter. Includes a Java 17 + Spring Boot 3.5.0 + Maven sample project with standalone unit tests and integration/slice tests.

## 1. The Problem: Tests Record Events, Yet Metrics/Traces Are Missing

A service can publish an `ApplicationEvent`, a listener can process it properly, and an `ObservationRegistry` bean can be present, yet a test still fails to find the expected metric or trace.

The causes vary:

1. Spring Boot test configuration intentionally restricts **metric export/tracing reporting** so tests do not push data to real backends.
2. The test uses `@WebMvcTest` or another slice that does not load full production actuator/tracing auto-configuration.
3. `ObservationRegistry` is present, but lacks an appropriate `ObservationHandler` to produce a `Timer` or span.
4. The service does not actually call `Observation.start/stop`, or the `@Observed` aspect is not enabled.
5. The metric was created, but its name/tags are wrong, the test queries the wrong registry, or the timer has not stopped yet.
6. The `Tracer` in a slice may be a **no-op**, so the bean existing does not prove spans are exported.
7. The test observes an `ApplicationEvent` without creating an Observation around the listener; one does not automatically trigger the other.
8. The test uses an annotation import from a **different Spring Boot version** and does not even compile.
9. An external network exporter is unreachable or disabled in tests, even though business outcomes are completely correct.
10. Parallel/shared-context tests leave metrics from earlier tests in the registry, making count-equals-one assertions flaky.

**Central point of this lesson:** `@AutoConfigureObservability` **is not an immutable annotation across all Spring Boot versions**, nor does it mean “turn on all logging, metrics, tracing, and exporters”. Before applying it, check the version, artifact, package, test level, and the actual evidence you want to verify.

## 2. Version Matrix: Read Before Copying Annotations

| Version Line | Appropriate Annotation | Scope and Notes |
| --- | --- | --- |
| **Spring Boot 2.7.x** | **Does not have** Boot 3.x's `@AutoConfigureObservability` | Has older metrics test mechanisms, but Micrometer Observation/tracing models are not equivalent to Boot 3.x; do not copy 3.x packages |
| **Spring Boot 3.0–3.5.x** | `@AutoConfigureObservability` | Package `org.springframework.boot.test.autoconfigure.actuate.observability`, available since **3.0.0** |
| **Spring Boot 4.0.x** | `@AutoConfigureMetrics` and/or `@AutoConfigureTracing` | Test infrastructure split into modules by concern; the old `@AutoConfigureObservability` annotation **no longer exists in Boot 4.0** |
| **Newer Boot 4.x releases** | Check corresponding Javadoc/test modules before use | Rely on documentation matching the exact version in `pom.xml`/Gradle dependency graph, not blogs for other versions |

### 2.1. Import for Spring Boot 3.5

```java
import org.springframework.boot.test.autoconfigure.actuate.observability
        .AutoConfigureObservability;
```

**Is this a valid line break in a Java import? No.** In real Java source code, write the import on **a single line**, without breaking between package and class:

```java
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
```

A test:

```java
@SpringBootTest
@AutoConfigureObservability
class OrdersObservabilityIntegrationTest {
    // ...
}
```

`@AutoConfigureObservability` belongs to **test autoconfiguration**, not production business beans. Tests require Boot test dependencies and suitable actuator/Micrometer dependencies; the complete project below provides them.

### 2.2. Proper Direction of Imports in Spring Boot 4.0

Boot 4.0 splits metrics and tracing test support:

```java
// Spring Boot 4.0: use the corresponding test support artifacts
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.micrometer.tracing.test.autoconfigure.AutoConfigureTracing;
```

Purpose-based selection example:

```java
@AutoConfigureMetrics
class MetricsIntegrationTest {
    // verify in-memory MeterRegistry/metrics
}

@AutoConfigureTracing
class TracingIntegrationTest {
    // verify tracing setup
}
```

This is a **directional migration snippet**, not part of the Boot 3.5 project below. When targeting Boot 4, add the relevant modules—such as `org.springframework.boot:spring-boot-micrometer-metrics-test` and `org.springframework.boot:spring-boot-micrometer-tracing-test` in test scope—aligned with the exact BOM; for servlet test slices, `@WebMvcTest` imports also move under Boot 4 modules. **Never mix both 3.x and 4.x annotations in the same source set**.

Spring Boot 4 documentation states that `@AutoConfigureMetrics` on a slice provides an in-memory `MeterRegistry` and `ObservationRegistry`; `@AutoConfigureTracing` serves tracing slices. Test slices still must not be assumed to export data to external systems.

### 2.3. Why Say “by Version Support”?

Seeing an older blog post using `@AutoConfigureMetrics` does not mean everything should be replaced with `@AutoConfigureObservability`; seeing Boot 4 use `@AutoConfigureTracing` does not mean that annotation exists in Boot 3.5. Verify step by step:

1. `spring-boot-starter-parent` / Spring Boot BOM version.
2. Exact test artifact present in the dependency tree.
3. Package/class in Javadoc matching the exact version.
4. Whether the annotation is used on a full context or a slice.
5. Features auto-configured or disabled by test policy.
6. Whether assertions verify bean registration, JVM metrics, JVM spans, or external exporters.

Sample compiler errors:

```text
package org.springframework.boot.test.autoconfigure.actuate.observability does not exist

cannot find symbol: class AutoConfigureObservability

package org.springframework.boot.micrometer.metrics.test.autoconfigure does not exist
```

**Do not resolve these by randomly swapping imports**. Confirm the BOM/module version and migration path. `@AutoConfigureObservability` from 3.x is not an API you can assume always exists in 4.x.

## 3. Observability: How Logging, Metrics, Traces, and Observation Differ

### 3.1. Three Pillars

- **Logging:** events/details written to logs by the app; `@AutoConfigureObservability` does not automatically convert logs into traces/spans.
- **Metrics:** aggregate measurements like request count, latency, error rate; Micrometer `MeterRegistry` stores/publishes them.
- **Traces:** parent/child relationships and span durations in a trace; Micrometer Tracing `Tracer`/tracing handlers and backends like Zipkin/OTLP are separate components.

`Observation` (Micrometer Observation API) offers a single instrumentation abstraction that can drive both metrics and traces when matching handlers exist:

```text
Business call / ApplicationEvent
          |
          v
Observation.createNotStarted("orders.created.event", registry)
          |
       start / scope
          |
     business handler
          |
      stop / error
          |
       ObservationRegistry
          |
       ObservationHandlers
        /          \
       v            v
Meter handler    Tracing handler
       |            |
     Timer         Span
       |            |
SimpleMeterRegistry  no-op/test tracer or actual reporter
       |
assert in JVM
```

Creating an Observation **without an `ObservationHandler`** usually produces no useful timers or spans. Conversely, the presence of a `SimpleMeterRegistry` bean does not prove a custom Observation was handled and recorded a timer.

### 3.2. Types of Data to Distinguish

| API | Role | How to Test |
| --- | --- | --- |
| `ObservationRegistry` | Manages observation lifecycle/handlers/current context | Bean wiring, handler invocation |
| `Observation` | start/stop/error, name/tags/scope | Recorded events, error context |
| `MeterRegistry` | Meters like Timer, Counter, Gauge | `find(name).timer()`, count/tags |
| `SimpleMeterRegistry` | In-memory metrics | Unit/integration assertions, no exporter |
| `Tracer` | Create/current/close spans | In-memory/test span handler or fake exporter |
| `ObservationHandler` | Handles start/stop/events | Verify handlers receive exact lifecycle |
| `@Observed` | Annotation instrumentation via AOP | Requires separate annotation scanning/AOP config |
| `ApplicationEventPublisher` | Emits Spring application events | Listener invoked; does not auto-create Observation |

### 3.3. Low- vs. High-Cardinality Key Values

Micrometer distinguishes:

- **Low cardinality:** small/bounded set of values, e.g., `event.type=created`, `result=success/failure`. Safe as metric tags.
- **High cardinality:** order ID, user ID, request ID, or full URI. Usually belongs in trace context only, **not** as metric tags because it creates millions of time series and leaks identifiers.
- Never put tokens, raw PII, passwords, or sensitive data into traces/logs/tags unnecessarily.

Example:

```java
Observation.createNotStarted("orders.created.event", registry)
        .lowCardinalityKeyValue("event.type", "created")
        .highCardinalityKeyValue("order.id", orderId)
        .observe(() -> businessWork());
```

This is a snippet assuming `registry`/`orderId` variables and `businessWork()`, not a standalone file. `orders.created.event` can produce a Timer of the same name when a meter handler is registered; `order.id` should not appear in Timer ID tags.

### 3.4. Metric Name from an Observation

`DefaultMeterObservationHandler` typically creates a timer when the observation **stops**, with a meter name matching the observation name:

```text
Observation name: orders.created.event
low cardinality: event.type=created
high cardinality: order.id=O-123

Timer name: orders.created.event
Timer tag event.type: created
Timer tag order.id: [absent]
Timer count: 1 after one completed observation
```

On a registry already holding meters from earlier tests, do not assert total count equals 1. Measure `before`/`after` or create a fresh registry per test.

## 4. What Does `@AutoConfigureObservability` Do in Spring Boot 3.x?

According to the Spring Boot 3.5 reference and Javadoc:

- `@SpringBootTest` does not automatically enable reporting/exporting on all metric registries/tracers even if exporters are on the classpath. In-memory meter registries receive special handling.
- For **sliced tests** such as `@WebMvcTest`, `@AutoConfigureObservability` auto-configures an `ObservationRegistry` and an **in-memory `MeterRegistry`**; the docs also mention a **no-op `Tracer`** within tracing slices.
- **Exporting real data externally from sliced tests is not supported** solely by adding that annotation.
- When an integration test must verify a real external metrics/tracing exporter, enable the corresponding reporting in a full context, use a test-only backend, and assert actual data receipt.
- The annotation does not automatically create business observations: instrumentation code, framework instrumentation, or `@Observed` annotation scanning is still required.
- The presence of a `Tracer` bean is not evidence that a trace reached a collector.
- Context/test policies vary across versions; never interpret this annotation as an immutable “everything on” flag.

### 4.1. The `metrics` and `tracing` Attributes in Boot 3.5

Javadoc:

```java
@AutoConfigureObservability(
        metrics = true,
        tracing = true)
```

Both attributes default to `true` and relate to **reporting to external systems in tests**. Do not read them as the sole switch deciding whether an `ObservationRegistry` bean exists. Specifically on slices, the documentation specifies in-memory/no-op support and **does not support data exporting** via this annotation.

To keep tests stable, the runnable example below relies solely on in-memory meter observations without configuring an external collector. Testing a real exporter belongs in a separate integration suite with a controlled collector/container endpoint.

### 4.2. Why Is a `@WebMvcTest` Not Equal to a Full Context?

`@WebMvcTest(OrdersController.class)` loads only the MVC slice and select converters/filters/advice, skipping general `@Service` beans. To supply `OrderService` to the controller, we declare `@MockitoBean` rather than expecting the real service from component scan.

Adding `@AutoConfigureObservability` to a slice gives an in-memory registry suitable for checking lightweight JVM wiring/observations; it **does not** prove production services have identical handlers, exporters, or trace propagation as the full app.

### 4.3. When Is the Annotation Unnecessary?

- Pure unit tests of services/listeners using `ObservationRegistry.create()` and a manual `ObservationHandler`.
- Domain logic tests with no metrics/tracing requirements: no need to enable exporters.
- Integration tests checking only Spring `ApplicationEvent` publish/receive without asserting observability: verify event wiring without enabling observability reporting.
- Tests needing a concrete timer on a Boot version lacking the annotation: use an explicit **test-only in-memory setup** instead of forcing a Boot upgrade just for one annotation.
- Real OTLP/Zipkin backend tests: need a full integration context with trace/exporter config, not a slice no-op tracer.

## 5. Rules for Testing Events and Observability

An `ApplicationEvent` is a notification within the same ApplicationContext:

```text
OrderService.create(orderId)
       |
       v
ApplicationEventPublisher.publishEvent(OrderCreatedEvent)
       |
       v
@EventListener OrderCreatedListener.on(event)
       |
       v
ObservationRegistry / timers / trace handlers
```

With a standard `@EventListener` and Spring's default `ApplicationEventMulticaster`, listeners run **synchronously** on the publisher thread. If the app configures an async multicaster or `@Async` on the listener, execution moves to another thread; use bounded waits and account for context propagation.

Distinct contracts:

1. Publish call made with valid payload.
2. Listener is registered and invoked.
3. Listener's business side effect is right.
4. Listener creates an observation with proper name/tags and calls start/stop.
5. Meter handler creates a timer with accurate count.
6. Tracing handler creates a span if tracing is configured.
7. External exporter receives data if that is the test goal.
8. Cross-thread/cross-service event propagation is a separate requirement.

**Do not conclude “event processed” just because a metric count incremented** if the business method could fail; on exceptions, `observation.error()` must also be recorded. Conversely, a green event test does not prove a timer or span exists.

## 6. Sample Project: Spring Boot 3.5.0 / Java 17 / Maven

This sample illustrates a **Spring application event** received by a listener that creates a Micrometer Observation, with unit tests, full-context tests, and slice tests. No Redis, database, Docker, or external collector is required.

### 6.1. Project Structure

```text
observability-test-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/obs/
    │   ├── ObservabilityLabApplication.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderService.java
    │   ├── OrderCreatedListener.java
    │   └── OrdersController.java
    └── test/java/com/example/obs/
        ├── OrderServiceUnitTest.java
        ├── OrderCreatedListenerUnitTest.java
        ├── OrdersObservabilityIntegrationTest.java
        └── OrdersControllerSliceTest.java
```

Total of **9 JUnit `@Test` methods**: 2 `OrderService` unit, 2 listener/Micrometer unit, 3 `@SpringBootTest` integration, and 2 `@WebMvcTest` slice. All Java files live in package `com.example.obs`; public types reside in matching filenames.

### 6.2. `pom.xml`

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
    <artifactId>observability-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**Why these three dependencies?**

- `starter-web`: `@RestController` and `MockMvc`-compatible MVC stack.
- `starter-actuator`: Spring Boot observability, Micrometer Observation, and meter registry auto-configuration.
- `starter-test`: JUnit Jupiter/AssertJ/Mockito/`@WebMvcTest`/`@AutoConfigureObservability` in Boot 3.5 test support.

No Prometheus, OTLP, or Zipkin exporter is added: the test target is **in-memory instrumentation**, not network export. Pin the Spring Boot version in the example; for Boot 4, swap test annotations/modules as shown in Section 2.

### 6.3. `ObservabilityLabApplication.java`

```java
// src/main/java/com/example/obs/ObservabilityLabApplication.java
package com.example.obs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObservabilityLabApplication.class, args);
    }
}
```

`@SpringBootTest` automatically discovers `@SpringBootApplication` from the test package. No fixed server port is needed: full tests default to a mock web environment and `@WebMvcTest` also starts no embedded HTTP server.

### 6.4. `OrderCreatedEvent.java`

```java
// src/main/java/com/example/obs/OrderCreatedEvent.java
package com.example.obs;

public record OrderCreatedEvent(String orderId) {
}
```

The Java record is the event payload. It does not extend `ApplicationEvent`, yet Spring Framework allows publishing arbitrary objects via `ApplicationEventPublisher`; `@EventListener` accepts the record type directly.

This lesson requires no serialization/network; it is an **in-process Spring event**. If Kafka/RabbitMQ/inter-process buses are used, add dedicated broker integration tests.

### 6.5. `OrderService.java`

```java
// src/main/java/com/example/obs/OrderService.java
package com.example.obs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public String create(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        publisher.publishEvent(new OrderCreatedEvent(orderId));
        return "created:" + orderId;
    }
}
```

`OrderService` validates input and publishes the event. Unit tests verify the payload; integration tests prove Spring registered the listener and created the observation.

### 6.6. `OrderCreatedListener.java`

```java
// src/main/java/com/example/obs/OrderCreatedListener.java
package com.example.obs;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final ObservationRegistry observations;
    private final AtomicInteger handled = new AtomicInteger();
    private final AtomicReference<String> latestOrderId =
            new AtomicReference<>();

    public OrderCreatedListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @EventListener
    public void on(OrderCreatedEvent event) {
        Observation.createNotStarted(
                        "orders.created.event", observations)
                .lowCardinalityKeyValue("event.type", "created")
                .highCardinalityKeyValue(
                        "order.id", event.orderId())
                .observe(() -> {
                    latestOrderId.set(event.orderId());
                    handled.incrementAndGet();
                });
    }

    public int handledCount() {
        return handled.get();
    }

    public String latestOrderId() {
        return latestOrderId.get();
    }
}
```

**Detailed explanation:**

- `ObservationRegistry` is injected from Spring Boot Actuator in the full context.
- `@EventListener` receives `OrderCreatedEvent` from `OrderService`.
- `Observation.createNotStarted` creates an observation with a stable name.
- `lowCardinalityKeyValue("event.type","created")` is safe to become a metric tag.
- `highCardinalityKeyValue("order.id", event.orderId())` should not become a metric tag; it is a high-cardinality dimension, so production should apply PII/trace retention policies.
- `observe(Runnable)` manages the start/stop lifecycle and handles exceptions per the Micrometer API; the demo keeps the handler simple.
- `AtomicInteger` and `AtomicReference` act as observable markers across tests, **not** replacements for database/business persistence.
- With Spring's default synchronous multicaster, the listener completes before `publishEvent` returns; if switched to `@Async`, use bounded awaits and ensure thread context propagation.

### 6.7. `OrdersController.java`

```java
// src/main/java/com/example/obs/OrdersController.java
package com.example.obs;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderService service;

    public OrdersController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/{id}")
    public String create(@PathVariable String id) {
        return service.create(id);
    }
}
```

The controller serves the illustrative slice test. Security/authentication are omitted in this demo; production endpoints handling orders require dedicated authentication and authorization. `@AutoConfigureObservability` is not a security control.

## 7. Unit Test: Verifying Service Spring Event Publication

### 7.1. `OrderServiceUnitTest.java`

```java
// src/test/java/com/example/obs/OrderServiceUnitTest.java
package com.example.obs;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderServiceUnitTest {

    @Test
    void validOrderPublishesExpectedEvent() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        OrderService service = new OrderService(publisher);

        assertThat(service.create("O-123"))
                .isEqualTo("created:O-123");

        verify(publisher).publishEvent(
                new OrderCreatedEvent("O-123"));
    }

    @Test
    void blankOrderIdDoesNotPublish() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        OrderService service = new OrderService(publisher);

        assertThatThrownBy(() -> service.create(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId must not be blank");

        verifyNoInteractions(publisher);
    }
}
```

Both tests **load no Spring context**. They guard validation and the publish call, but do not prove the Spring listener is registered or a Meter Timer exists.

## 8. Unit Test: Completely In-Memory Micrometer Registry and Metric Handler

A strong approach, **independent of Spring Boot 3.x or 4.x annotations**, is constructing an `ObservationRegistry` + `SimpleMeterRegistry` manually for pure unit tests. Configure `DefaultMeterObservationHandler` for deterministic proof that the Observation creates a Timer.

### 8.1. `OrderCreatedListenerUnitTest.java`

```java
// src/test/java/com/example/obs/OrderCreatedListenerUnitTest.java
package com.example.obs;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderCreatedListenerUnitTest {

    @Test
    void eventCreatesTimerInManualInMemoryRegistry() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations =
                    ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(
                            new DefaultMeterObservationHandler(meters));

            OrderCreatedListener listener =
                    new OrderCreatedListener(observations);
            listener.on(new OrderCreatedEvent("O-123"));

            assertThat(listener.handledCount()).isEqualTo(1);
            assertThat(listener.latestOrderId())
                    .isEqualTo("O-123");

            Timer timer = meters.find("orders.created.event")
                    .tag("event.type", "created")
                    .timer();
            assertThat(timer).isNotNull();
            assertThat(timer.count()).isEqualTo(1);
        }
        finally {
            meters.close();
        }
    }

    @Test
    void highCardinalityOrderIdIsNotMeterTag() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations =
                    ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(
                            new DefaultMeterObservationHandler(meters));

            OrderCreatedListener listener =
                    new OrderCreatedListener(observations);
            listener.on(new OrderCreatedEvent("O-SECRET-123"));

            Timer timer = meters.find("orders.created.event")
                    .tag("event.type", "created")
                    .timer();
            assertThat(timer).isNotNull();
            assertThat(timer.getId().getTag("order.id")).isNull();
        }
        finally {
            meters.close();
        }
    }
}
```

**Why is this test reliable?**

- `ObservationRegistry.create()` and `SimpleMeterRegistry` belong to Micrometer, independent of Spring Boot test autoconfiguration.
- `DefaultMeterObservationHandler` receives `start/stop` from Observation and builds a Timer.
- `Timer.count()` equals 1 because each test creates a fresh registry, unaffected by context caching.
- `order.id` is a high-cardinality key and does not appear in meter tags.
- `SimpleMeterRegistry.close()` cleans up unit-test resources.
- These two tests do not prove Boot auto-registers handlers or exporters. That is the role of the full-context integration tests next.

**API/version note:** `DefaultMeterObservationHandler` resides in `io.micrometer.core.instrument.observation`. The project uses Micrometer versions managed by the Spring Boot 3.5 BOM. If another project uses a different Micrometer major version, check its Javadoc rather than copying blindly.

## 9. Spring Boot 3.5 Full-Context Test: `@AutoConfigureObservability`

### 9.1. `OrdersObservabilityIntegrationTest.java`

```java
// src/test/java/com/example/obs/OrdersObservabilityIntegrationTest.java
package com.example.obs;

import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureObservability
class OrdersObservabilityIntegrationTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderCreatedListener listener;

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @Test
    void fullContextProvidesObservationAndMeterRegistries() {
        assertThat(observations).isNotNull();
        assertThat(meters).isNotNull();
    }

    @Test
    void springEventProducesMetricAfterHandlerCompletes() {
        int handledBefore = listener.handledCount();
        Timer previous = meters.find("orders.created.event")
                .tag("event.type", "created").timer();
        long countBefore =
                previous == null ? 0 : previous.count();

        String orderId = "O-" + UUID.randomUUID();
        String response = service.create(orderId);

        assertThat(response).isEqualTo("created:" + orderId);
        assertThat(listener.handledCount())
                .isEqualTo(handledBefore + 1);
        assertThat(listener.latestOrderId())
                .isEqualTo(orderId);

        Timer after = meters.find("orders.created.event")
                .tag("event.type", "created").timer();
        assertThat(after).isNotNull();
        assertThat(after.count()).isEqualTo(countBefore + 1);
    }

    @Test
    void orderIdDoesNotLeakIntoTimerTags() {
        service.create("O-" + UUID.randomUUID());

        Timer timer = meters.find("orders.created.event")
                .tag("event.type", "created").timer();

        assertThat(timer).isNotNull();
        assertThat(timer.getId().getTag("order.id")).isNull();
    }
}
```

**These are 3 integration test methods**.

- The first test guards basic bean wiring.
- The second test exercises `OrderService` → Spring event system → `@EventListener` → Micrometer Observation → in-memory metric handler. It checks the **delta** timer count instead of hardcoding count=1 on a cached registry.
- The third test protects the cardinality/security contract: `order.id` never leaks into metric tags.
- `@AutoConfigureObservability` in Boot 3.5 enables testing observation metrics in-test; it **does not** prove traces were sent to Zipkin/OTLP.
- No `Thread.sleep`: the listener is synchronous under the default event multicaster. If production configures an async listener, write a dedicated async test with a timeout.
- Do not assert Timer totalTime/max against a fixed millisecond number: CI scheduling and JVM warmup vary durations.
- `@SpringBootTest` by default starts no real HTTP server; it is not an e2e test over the network.
- The sample configures no exporter; all tests run offline once Maven dependencies are resolved.

### 9.2. Why Use Count Deltas?

Spring TestContext can cache the `ApplicationContext`, so the meter registry may already contain entries from other test methods. An assertion like:

```java
assertThat(meters.get("orders.created.event")
        .timer().count()).isEqualTo(1);
```

risks failing depending on execution order. By capturing `countBefore` and asserting a delta of one event, the test isolates the effect of that specific call. If the listener runs asynchronously, use bounded polling when measuring the delta rather than asserting immediately.

## 10. Test Slice: `@WebMvcTest` and `@AutoConfigureObservability`

### 10.1. `OrdersControllerSliceTest.java`

```java
// src/test/java/com/example/obs/OrdersControllerSliceTest.java
package com.example.obs;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrdersController.class)
@AutoConfigureObservability
class OrdersControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @MockitoBean
    OrderService service;

    @Test
    void slicedContextHasTestObservationInfrastructure() {
        assertThat(observations).isNotNull();
        assertThat(meters).isNotNull();
    }

    @Test
    void controllerCallsMockWithoutLoadingRealEventListener()
            throws Exception {
        given(service.create("O-7"))
                .willReturn("created:O-7");

        mvc.perform(post("/orders/O-7"))
                .andExpect(status().isOk())
                .andExpect(content().string("created:O-7"));

        verify(service).create("O-7");
    }
}
```

**These are 2 slice test methods**.

- `@WebMvcTest` loads only the MVC slice; `OrderCreatedListener` is normally not scanned as a full application component.
- `@MockitoBean` replaces `OrderService` with a Mockito bean so the controller test does not emit a real event.
- `@AutoConfigureObservability` supplies an in-memory `MeterRegistry` and `ObservationRegistry` per Spring Boot 3.5 docs.
- Having `ObservationRegistry` in the test does not mean a tracing reporter or HTTP metrics exporter is active. Sliced tests do not support external data exporting via this annotation.
- `MockMvc` runs in a mock Servlet environment and **does not** launch an embedded server listening on a real port.
- To verify real event processing and Observations, use the full-context test in Section 9, not a controller slice with a mocked service.

## 11. Summary of Test Cases and Run Commands

| Test Class | `@Test` Methods | Spring Context? | What It Protects |
| --- | ---: | --- | --- |
| `OrderServiceUnitTest` | 2 | No | Validate/publish event call |
| `OrderCreatedListenerUnitTest` | 2 | No | Observation → Timer in JVM, high cardinality |
| `OrdersObservabilityIntegrationTest` | 3 | Full context | Event listener, metric registration, count delta |
| `OrdersControllerSliceTest` | 2 | MVC slice | Registry in slice, controller→mock service |
| **Total** | **9** | Includes unit/full/slice | Clear boundaries |

### 11.1. Running Each Group Separately

```bash
java -version
mvn -version

# Unit tests without Spring context:
mvn -B -ntp -Dtest=OrderServiceUnitTest,OrderCreatedListenerUnitTest test

# Full-context observability:
mvn -B -ntp -Dtest=OrdersObservabilityIntegrationTest test

# MVC slice with @AutoConfigureObservability:
mvn -B -ntp -Dtest=OrdersControllerSliceTest test

# All 9 tests:
mvn -B -ntp test
```

**Expected per source:** the tests run without Docker or an exporter. These are commands for you to execute; **this is not a report that the project was compiled/executed** in the authoring environment. Maven/Spring stdout logs vary; never fabricate a “BUILD SUCCESS” log as evidence.

### 11.2. Symptoms When Dependencies Are Missing

```text
error: package io.micrometer.observation does not exist
error: package org.springframework.boot.test.autoconfigure.actuate.observability does not exist
No qualifying bean of type 'io.micrometer.observation.ObservationRegistry'
No qualifying bean of type 'io.micrometer.core.instrument.MeterRegistry'
```

Diagnose step by step:

1. Are Micrometer/Actuator/starters on the classpath?
2. Do Parent/BOM match the Boot version?
3. Do test starters/modules match the version?
4. Is the annotation import targeting 3.5 or 4.x?
5. Does the test slice include the right annotation?
6. Did the test load the main app or only a slice?
7. Is there an explicit `@ImportAutoConfiguration(exclude=...)` or custom context excluding Observation auto-config?
8. Is a custom/no-op registry or handler missing?

Never “fix” errors by deleting assertions just to make the compiler pass; match the actual intended semantics.

## 12. When Is Real Tracing Testing Needed?

### 12.1. A No-Op Tracer Is Not an Export Test

In Boot 3.5, sliced tests using `@AutoConfigureObservability` can receive a no-op `Tracer`. This lets code needing a tracer run in-context without generating spans for a real collector.

If a test only needs to verify that an event handler **invokes Observation** and sets metric tags, an in-memory `MeterRegistry` is usually enough. If a test must verify **propagation and reporting**, write a dedicated full-context test with a test tracer/exporter:

- OpenTelemetry in-memory exporter or test-only collector.
- A controllable test `SpanExporter` implementation / `SpanHandler`.
- IDs, parent/child relationships, attributes, and error status.
- Controlled sampling config / test parent context.
- Never send data to production OTLP/Zipkin endpoints.
- Bounded awaits if batch export is asynchronous.
- Clean up resources and avoid sharing test registries across unrelated suites.

### 12.2. Do Not Look at Span Count 0 and Immediately Blame Code

A missing trace can stem from sampling, a no-op tracer, disabled test exporters, an unflushed async batch, lost parent context across a thread boundary, or an observation lacking a tracer handler. Check each step before changing application code.

### 12.3. Propagation When Spring Events Are Asynchronous

Spring's default `@EventListener` is synchronous. With `@Async` or a custom executor-backed `ApplicationEventMulticaster`, span context normally does not cross arbitrary ThreadLocal boundaries without explicit context propagation. Spring Boot/Micrometer provide hooks depending on the environment, yet you must test with a real task executor, `traceparent`/parent-child spans, and the exact version.

Never run a unit test calling `listener.on(event)` directly and claim trace propagation across a thread pool has been verified.

## 13. Is `@Observed` the Same as `@AutoConfigureObservability`?

**No.** They operate at two completely different layers:

- `@AutoConfigureObservability`: an annotation **configuring test auto-configuration** in Boot 3.x.
- `@Observed`: a Micrometer annotation **marking methods for instrumentation**, requiring scanning/AOP support and matching configuration.

Spring Boot 3.5 documents:

```properties
management.observations.annotations.enabled=true
```

Alongside `org.aspectj:aspectjweaver`, typically brought in via `spring-boot-starter-aop`, to support annotation scanning like `@Observed`, `@Timed`, `@Counted`, `@MeterTag`, and `@NewSpan` depending on dependencies.

**The runnable project does not use `@Observed`**; it calls `Observation.createNotStarted` directly and therefore needs no AspectJ. Adding `@Observed` to a method without enabling annotation aspects will cause metric expectations to fail.

### 13.1. Double Instrumentation

Spring MVC already provides HTTP server observations. Combining auto-instrumented controllers with `@Observed` on the same controller method can duplicate or alter metric/trace semantics. Choose one deliberate observation strategy and test metric names/counts/tags to detect duplication.

### 13.2. `@Timed`, Timer, and Observation

`@Timed` is not the only way to get a Timer; `DefaultMeterObservationHandler` creates Timers from Observation start/stop. Do not stack a manual `Timer.record(...)` alongside an Observation for the same boundary without realizing you are creating two measurements.

## 14. Controlling Exporters: Tests Should Not Send Data Externally

### 14.1. Why Does Boot Restrict Reporters in Tests?

If every test pushed metrics/traces to default collectors, the suite could:

- Depend on network connectivity or live OTLP/Zipkin servers.
- Pollute real monitoring data.
- Leak PII, test IDs, or unwanted HTTP URLs.
- Increase latency and cause flaky behavior.
- Trigger cardinality explosions from test cases and random IDs.
- Fail tests on exporter network errors even when business logic is right.

Therefore, in business tests that do not test exporting, use in-memory registries or no-op tracers. Only dedicated exporter integration tests should enable reporting to a test backend with explicit endpoints/credentials.

### 14.2. Which Tests Need an External Collector?

| Purpose | Needs Real Exporter? | Recommended Test |
| --- | --- | --- |
| Service creates Observation properly | No | Pure Micrometer registry test |
| Metric name/tags/count accurate | No | `SimpleMeterRegistry` |
| Event listener is invoked | No | SpringBootTest / event integration |
| Controller mapping/HTTP status | No | WebMvcTest + MockMvc |
| Tracer bean is autowired | No | Slice/no-op or mock |
| In-JVM parent-child spans | Not required | In-memory/test span reporter |
| Real OTLP JSON/gRPC payloads | Yes | Full integration + test collector |
| Prometheus scrape endpoint | Needs real endpoint | Full web/management integration |
| Cross-service trace propagation | Needs multiple components | Multi-service test environment |
| Production alert/dashboard accuracy | Usually staging | E2E with monitoring backend |

### 14.3. `metrics=true` / `tracing=true` Are Not Enough

Even with both annotation flags true, without exporter dependencies, endpoint configs, and enabled conditions, you cannot conclude data left the process. On sliced tests, Boot 3.5 documentation explicitly states **data exporting is not supported** by `@AutoConfigureObservability`. Evidence must come from a test receiver/collector or appropriately scoped in-memory observation assertions.

## 15. Migration Checklist When Upgrading Boot 3.5 to 4.x

1. Inspect `pom.xml`, Gradle dependency locks, and the actual Spring Boot BOM.
2. Search tests for `org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability`.
3. For Boot 4.0, remove this import/annotation; do not assume an alias exists.
4. If metrics test support is needed, add `spring-boot-micrometer-metrics-test` and use `@AutoConfigureMetrics` per Boot 4 docs.
5. If tracing test support is needed, add `spring-boot-micrometer-tracing-test` and use `@AutoConfigureTracing`.
6. Check changed imports for `@WebMvcTest`, `@AutoConfigureMockMvc`, and other test slice/module migrations.
7. Do not preserve Boot 3.5's `metrics/tracing` attributes on a different Boot 4 annotation: `@AutoConfigureMetrics` has an `export` attribute rather than the two old flags.
8. Test both `ObservationRegistry`/`MeterRegistry` provisioning and timer behavior; do not merely fix imports to compile.
9. Verify no-op tracer and test reporter semantics for the target version.
10. Audit any custom organization tracing exporter beans to ensure CI never emits to production collectors.
11. Test cardinality, observation names, HTTP client/server instrumentation, and async propagation.
12. Check the dependency tree and official Javadoc for artifacts/packages; never import 3.x and 4.x side by side.
13. Never assume Boot 4's `@AutoConfigureMetrics` is equivalent to Boot 3.x's `@AutoConfigureObservability` in every scenario.
14. In multi-module builds using different Boot BOMs, check module overrides instead of reading the parent POM alone.
15. Run test compilation and tests on each target version; never treat Gradle refresh or Maven dependency resolution alone as sufficient.

### 15.1. Dependency Migration Example (Boot 4.x Only)

```xml
<!-- Illustrative Boot 4 modules only; DO NOT add to the Boot 3.5 pom above -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-micrometer-metrics-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-micrometer-tracing-test</artifactId>
    <scope>test</scope>
</dependency>
```

Verify the Spring Boot 4 BOM manages versions and other Spring test starters before running. This is a migration **snippet**, not a second runnable project; the complete sample in this lesson is pinned to 3.5.0.

## 16. An Annotation-Independent Approach to Testing Observations

If a project spans multiple Boot versions during migration, a **Micrometer-only unit test** like `OrderCreatedListenerUnitTest` stays stable because:

- It does not care whether `@AutoConfigureObservability` exists in that Boot version.
- It uses `ObservationRegistry.create()` and `DefaultMeterObservationHandler` to test an event directly.
- It uses in-memory `SimpleMeterRegistry`, needing no collector, Docker, or network.
- Observation names and low-cardinality tags are verified directly.
- Event handler logic can be invoked independently of the Spring container.

Yet that test also has limits:

- It does not confirm Spring auto-configuration creates the `ObservationRegistry` bean.
- It does not confirm `@EventListener` is registered.
- It does not confirm Spring Boot selected the intended `MeterRegistry`.
- It does not test `@Observed` proxy/AOP instrumentation.
- It does not test asynchronous event context propagation.
- It does not verify a real trace/span exporter.

**Combine unit and integration tests**, rather than relying on one type for everything.

## 17. Common Confusions and How to Debug Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Cannot find `AutoConfigureObservability` | Boot 2.7 or 4.x / wrong import | BOM, version-exact Javadoc |
| Boot 4 test still imports Boot 3 path | Annotation was moved/replaced | Use Boot 4 Metrics/Tracing test modules |
| Missing `ObservationRegistry` bean | Missing actuator/micrometer or slice auto-config | Dependencies, test annotations/slice config |
| `MeterRegistry` exists but timer is null | Observation didn't stop, missing handler | Manual handler test and observation lifecycle |
| Timer count is not 1 | Context cache/shared meters, extra calls | Compare count delta or isolated registry |
| High-cardinality ID appears on meter | Put in low-cardinality key by mistake | Use `highCardinalityKeyValue`, inspect tags |
| `Tracer` bean exists but zero spans | No-op tracer/sampling/reporting disabled | Test reporter/tracer config |
| Lost trace parent in async listener | Thread context not propagated | Executor/context propagation tests |
| Slice green, full integration fails | Slice uses mocked components | Full context matching test scope |
| `@Observed` creates no metric | Annotation scanning/AOP disabled | `management.observations.annotations.enabled`, `aspectjweaver` |
| Metrics double-counted | Double instrumentation | Check Observation names/handlers |
| CI test tries to connect to OTLP collector | Exporter/test config side effect | In-memory registry or test-only endpoint |
| `@WebMvcTest` does not load service | Slice excludes business beans | Intentional `@MockitoBean`/`@Import` |
| No HTTP server port | Mock web environment | Use `RANDOM_PORT` if networking needed |
| Test passes yet backend has no data | Slice doesn't support export, or no exporter | Separate exporter integration test |
| `NoClassDefFoundError` for Micrometer | Maven modules/BOM mismatch | `dependency:tree`, test classpath |
| Unknown `@AutoConfigureMetrics(metrics=...)` | Attributes differ across versions | Open Javadoc of the exact annotation used |

### 17.1. `ObservationRegistry` Exists, Yet Instrumentation Is No-Op

Check which handlers are registered on `ObservationRegistry`. A pure JVM registry created with `ObservationRegistry.create()` runs the observation lifecycle, yet without `observationHandler(...)` it has no metric exporter/timer; add `DefaultMeterObservationHandler` when testing metrics.

Spring Boot Actuator autoconfig registers handlers based on dependencies/config. In `@SpringBootTest`, `@AutoConfigureObservability` allows test assertions matching test policy; in slices, verify in-memory support instead of expecting a real exporter.

### 17.2. Timer Exists in Registry, Yet Name/Tag Mismatches

`MeterRegistry.find(name)` requires the exact observation name and matching low-cardinality tags. High-cardinality `order.id` is not a metric tag. Micrometer may add `error=none` via handlers, so search by key tags or inspect `Meter.Id` rather than hardcoding the full tag set when modules add common tags.

### 17.3. No-Op Tracer Does Not Mean the App Has Zero Observability

In a slice, a no-op `Tracer` gives code requiring a tracer a valid bean without emitting spans, while the in-memory `MeterRegistry` still records metrics. Tracing and metrics reporters are distinct capabilities.

### 17.4. Event Count Does Not Always Equal Timer Count

A listener might process several events while observations are dropped by an `ObservationPredicate`, disabled name prefix, missing handler, or error handling. Compare both signals under explicit test config rather than assuming 1 event = 1 backend span across all samplers.

## 18. Security, Cardinality, and Reliability Testing

### 18.1. Never Attach userId/orderId to Low-Cardinality Metrics

A metric like:

```text
orders.created.event{event.type="created", order.id="O-123"}
```

with millions of distinct `order.id` values causes cardinality explosion. Use `highCardinalityKeyValue` for IDs only if genuinely needed in traces, and apply encryption/redaction/PII policies. In the sample project, unit and integration tests intentionally assert the timer has no `order.id` tag.

### 18.2. Never Test Exporters Using Production Secrets

OTLP/Zipkin/Prometheus tests need test-only collectors, separate credentials, or in-memory span exporters. CI must never send traces/meters containing sensitive test data to production collectors. Do not confuse an exporter environment variable present in CI with verification that the backend received valid data.

### 18.3. Async Events and Timing

When `@Async` is on an event listener:

- `ApplicationEventPublisher.publishEvent` may return before the listener finishes.
- Tests must await bounded latches/queues/conditions, never fixed sleeps.
- Observation context/parent spans must be propagated across executors.
- Never use `@Transactional` on the test method to infer rollback on a listener thread.
- Errors may be routed to an async exception handler rather than thrown back to the publisher.
- Tracing sampling can make span count differ from event count; test the specific policy.
- Context caching and test teardown must stop worker threads cleanly when tests finish.

### 18.4. Events Are Not a Message Broker

`@EventListener` in the demo receives Spring in-process events. To test Kafka/RabbitMQ or a distributed outbox, use broker services/Testcontainers and test delivery semantics, retries, dead letters, and idempotency. `@AutoConfigureObservability` only affects observability auto-configuration—it **never** turns an `ApplicationEvent` into a Kafka message.

## 19. Recommended Test Matrix for Production Services

| Goal | Unit | Full Context | Slice | Dedicated External Integration |
| --- | --- | --- | --- | --- |
| Exact event payload | Yes | Optional | Unnecessary | When via broker |
| Listener business logic | Yes | Yes | Usually no | When side effects exist |
| Observation name/tags | Manual Micrometer | Yes | Possible | Unnecessary |
| Meter Timer count | `SimpleMeterRegistry` | Yes | In-memory if needed | Unnecessary |
| End-to-end meter exporter | No | With test config | Unsupported via slice alone | **Yes** |
| Parent-child spans | Test tracer | Full tracing config | No-op insufficient | When propagation needed |
| HTTP controller mapping | Unnecessary | Optional | **Yes** | When network needed |
| Trace/exporter error handling | No | Partial | No | **Yes** |
| Boot 3→4 upgrade compatibility | Compile-time check | Context test | Slice import check | Build matrix CI |
| Privacy/cardinality | Validate tags | Yes | Yes | Backend policy test |

### 19.1. How Should CI Be Organized?

- Run fast pure unit tests without network dependencies.
- Run Boot full-context and MVC slice tests under separate test policies.
- Dedicated exporter tests may require collector containers, ports/networks, and test-only credentials.
- Do not enable exporters across all `@SpringBootTest` tests in the suite.
- Pin Boot BOM/versions on the test classpath; never let transitive imports shift versions silently.
- If CI targets multiple Boot major versions, run a build/test matrix; **do not compile a single test class importing annotation packages absent in one of the versions**.
- Report `UNIT PASS`, `FULL CONTEXT PASS`, `SLICE PASS`, `EXPORTER PASS/FAIL`, and `SKIPPED` clearly; never call external reporting `PASS` when only bean registry presence was checked.

## 20. Pre-Merge Checklist for Observability Tests

- [ ] Verified Spring Boot version in build/BOM rather than guessing from blog posts.
- [ ] Boot 3.0–3.5: imported `@AutoConfigureObservability` from the exact package.
- [ ] Boot 4.0: used `@AutoConfigureMetrics`/`@AutoConfigureTracing` and matching test modules.
- [ ] Never mixed Boot 3.x and 4.x annotation imports in the same project.
- [ ] Clear goal: registry existence, timer, span, or exporter delivery.
- [ ] Understood `ObservationRegistry`, `MeterRegistry`, and `Tracer` have distinct responsibilities.
- [ ] Slice tests expect only in-memory meters/no-op tracer per docs; never assert external export.
- [ ] Full-context tests include proper Actuator/Micrometer dependencies.
- [ ] `@Observed` annotations, if used, have matching AOP/scanning support.
- [ ] Do not expect `@AutoConfigureObservability` to auto-instrument arbitrary business methods.
- [ ] `@EventListener` and Micrometer Observation are recognized as two distinct mechanisms.
- [ ] Event tests check payload/handler and observation tests check metrics separately.
- [ ] Metric tags use low cardinality; never raw orderId/userId.
- [ ] Cached registry count checks use deltas or fresh registries per test.
- [ ] Never assert latency milliseconds against a hardcoded fixed number.
- [ ] Real external collectors in tests use test-only endpoints.
- [ ] Tracing tests do not treat a no-op tracer's presence as proof of span export.
- [ ] For async events, tests cover bounded waits and context propagation.
- [ ] No secrets/PII in metrics, logs, or traces.
- [ ] Version migrations verified via real compilation/tests and official Javadoc.
- [ ] Code samples distinguish Boot 4 snippets from the runnable Boot 3.5 project.

## 21. Practical Exercises

**Exercise 1 — Version compatibility.** Run `OrdersObservabilityIntegrationTest` on Boot 3.5. Try switching the annotation import to the Boot 4 package in a demo branch and observe the compile error. Explain why dependencies and modules must change together.

**Exercise 2 — Missing handler.** In `OrderCreatedListenerUnitTest`, remove `DefaultMeterObservationHandler` and see whether the Timer is still produced. Explain why a registry bean alone does not prove metric recording.

**Exercise 3 — High cardinality.** Change `order.id` from `highCardinalityKeyValue` to `lowCardinalityKeyValue` on a learning branch. Inspect meter ID tags and explain the cardinality explosion risk; revert before merging.

**Exercise 4 — Full vs. slice tests.** Compare `OrdersObservabilityIntegrationTest` and `OrdersControllerSliceTest`: which one loads the service/real event listener? Why does the slice test only cover the controller + Mockito service?

**Exercise 5 — Exporter.** Add an in-memory/test-only `SpanExporter` or test collector along with Spring Boot tracing dependencies. Assert directly on exported span data rather than `Tracer` bean presence alone.

**Exercise 6 — Async events.** Put `@Async` on the listener and configure an executor in the test context; switch assertions to bounded awaits and test parent-span context propagation.

**Exercise 7 — Spring Boot 4 migration.** Create a separate Boot 4 project, add `spring-boot-micrometer-metrics-test` and `spring-boot-micrometer-tracing-test`, and import the right annotations. Verify test compilation, in-memory meters, no-op tracer behavior, and external export limits.

**Exercise 8 — `@Observed`.** Enable `management.observations.annotations.enabled=true` and `spring-boot-starter-aop` in a separate sample; compare metrics from `@Observed` with manual Observations to avoid double instrumentation.

**Exercise 9 — Fault case.** Make the event listener throw an exception; use `Observation.error(...)`/try-finally per API and assert the error tag/status without relying on log strings containing secrets.

**Exercise 10 — Dependency tree.** Run `mvn dependency:tree` and point out which module supplies `@AutoConfigureObservability` in Boot 3.5 and why that module differs in Boot 4.

## 22. Self-Check Questions

**1.** Does Spring Boot 3.5 have `@AutoConfigureObservability`?  
**Answer:** Yes, in Spring Boot's test autoconfigure package, introduced in Boot 3.0.

**2.** Can `@AutoConfigureObservability` be used unchanged in Boot 4.0?  
**Answer:** No. Boot 4.0 splits test support into `@AutoConfigureMetrics` and `@AutoConfigureTracing` in separate modules/packages.

**3.** Does having `ObservationRegistry` guarantee a Timer exists?  
**Answer:** No. An Observation must be started/stopped and a matching metric handler must be registered.

**4.** Does having `MeterRegistry` mean metrics are exported to a real backend?  
**Answer:** No; `SimpleMeterRegistry` is in-memory and includes no network exporter.

**5.** Does having a `Tracer` in a sliced test mean spans are created and exported?  
**Answer:** No; Boot 3.5 can provide a no-op tracer in slices.

**6.** Does `@WebMvcTest` automatically load every `@Service`/`@EventListener`?  
**Answer:** No; slices require explicit mocks or intentional imports.

**7.** Does `@EventListener` automatically generate metrics?  
**Answer:** No. App events drive business handling; metrics/traces still require instrumentation + handlers.

**8.** Why avoid putting order IDs in metric tags?  
**Answer:** High-cardinality IDs create massive numbers of time series and can expose sensitive data.

**9.** Why does the integration test read `countBefore`?  
**Answer:** To avoid depending on state left by the Spring TestContext cache or other tests.

**10.** Why avoid asserting timer duration equals exactly 5ms?  
**Answer:** Timing depends on JVM/CPU/CI load; only check duration when there is a well-defined SLA test and controlled measurement conditions.

**11.** Does `@AutoConfigureObservability` automatically enable `@Observed` AOP in Boot 3.5?  
**Answer:** No. Annotation scanning requires `management.observations.annotations.enabled=true` and AspectJ support.

**12.** When is a real collector needed?  
**Answer:** When the test contract covers the reporter sending data to an external backend—not when merely asserting observations/timers inside the JVM.

## 23. Official Version-Specific Documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): sections on Using Observations, Using Metrics, Using Tracing; `@AutoConfigureObservability` with sliced/full tests.
- [Spring Boot 3.5 — AutoConfigureObservability Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/actuate/observability/AutoConfigureObservability.html): package, `Since 3.0.0`, `metrics` and `tracing` attributes.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, low/high cardinality, annotation scanning.
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): `@AutoConfigureMetrics` and `@AutoConfigureTracing` in separate test modules.
- [Spring Boot 4.0 — AutoConfigureMetrics Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/micrometer/metrics/test/autoconfigure/AutoConfigureMetrics.html): Boot 4 metrics test annotation.
- [Spring Boot 4.0 — AutoConfigureTracing Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/micrometer/tracing/test/autoconfigure/AutoConfigureTracing.html): Boot 4 tracing test annotation.
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): test modules/package migration.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/1.15/observation/components.html): `DefaultMeterObservationHandler` and Timer lifecycle.
- [Micrometer — Observation API](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): `ObservationRegistry`, observation handlers.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `ApplicationEventPublisher` and `@EventListener`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): framework observation instrumentation.
- [Spring Framework — MockitoBean Test Overrides](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean replacement in Spring tests.

**Conclusion:** In Spring Boot 3.0–3.5, `@AutoConfigureObservability` is valuable when tests need appropriate observability infrastructure enabled, especially in-memory support within slices. In Boot 4.0, use `@AutoConfigureMetrics` and `@AutoConfigureTracing` with their respective test modules. Across all versions, never equate having an `ObservationRegistry` bean with having a Timer, having a `Tracer` with exporting spans, or having an `ApplicationEvent` with creating an observation. Write tests that verify each boundary cleanly: event publication, handler execution, Micrometer observation lifecycle, in-memory metric tags/counts, and finally exporter delivery when needed.