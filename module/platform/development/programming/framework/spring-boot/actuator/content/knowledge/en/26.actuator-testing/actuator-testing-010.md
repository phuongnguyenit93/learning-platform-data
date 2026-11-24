# Testing Observations and Tracing with Compatible Support Tools

An invoice-processing operation can return the right result while the operations team sees missing metrics or sees the operation appear as a disconnected trace. Business-logic tests only verify the processing outcome. To test observability, you must also check which signals were produced, which attributes were attached, and how far context propagated.

## Identifying the Signals to Check

An `Observation` describes a single execution and its lifecycle, such as starting, opening a context scope, recording errors, and stopping. Registered `ObservationHandler` instances on an `ObservationRegistry` use that lifecycle to produce outputs such as metrics or spans. A span represents a unit of work within a trace. Two spans can share the same `traceId`, while a direct parent–child relationship is verified via the child span's `parentId` and the parent span's `spanId`.

| What to Prove | Suitable Tool | Recommended Assertions |
| --- | --- | --- |
| Application code creates the right Observation | `TestObservationRegistry` and `TestObservationRegistryAssert` from `micrometer-observation-test`, or an in-memory recording `ObservationHandler` | Name, key-values, success and error lifecycle, scope closed. |
| Observation produces the right metrics | `SimpleMeterRegistry` with `DefaultMeterObservationHandler` | Timer name, recording count, and allowed tags. |
| Code calls the Micrometer Tracing API properly | `SimpleTracer` and `TracerAssert` from `micrometer-tracing-test` | Span created or ended, name, tags, or error matching the code contract. |
| Real tracing bridge produces the right spans | The bridge matching your system, such as Brave with an in-memory `SpanHandler`, or OpenTelemetry with an in-memory span exporter | Trace and span relationships, tags propagated to the span, scope restored. |
| Trace crosses the network and reaches the collector | Integration test with an instrumented HTTP client and a test-controlled collector target | Context propagation headers in the expected format, server-side span in the same trace, and matching data at the collector. |

In a Spring Boot project, use the Boot-managed BOM versions for Micrometer, the tracing bridge, and the corresponding test libraries. The example below uses Spring Boot BOM `3.3.5`, Micrometer `1.13.6`, Micrometer Tracing `1.3.5`, and Brave `6.0.3`. Pick tools according to the layer under test. When you need to verify compatibility with the deployed bridge, run the test with that exact bridge.

## Java 17 Example with In-Memory Timer and Spans

`InvoiceProcessor` wraps the validation operation in `invoice.process`. `operation=validate` has a small value set and is therefore suitable as a metric tag. `invoice.id` varies per invoice and is declared as high cardinality. In the example, the invoice ID is test fixture data used to assert span tags.

Create a separate Gradle project and use JDK 17 or later. In `settings.gradle`, set `rootProject.name = 'invoice-observability-test'`.

File `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'io.micrometer:micrometer-observation'

    testImplementation 'io.micrometer:micrometer-core'
    testImplementation 'io.micrometer:micrometer-tracing-bridge-brave'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `src/main/java/demo/observability/InvoiceProcessor.java`

```java
package demo.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class InvoiceProcessor {

    private final ObservationRegistry registry;

    public InvoiceProcessor(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String process(String invoiceId, boolean valid) {
        return Observation.createNotStarted("invoice.process", registry)
                .lowCardinalityKeyValue("operation", "validate")
                .highCardinalityKeyValue("invoice.id", invoiceId)
                .observe(() -> {
                    if (!valid) {
                        throw new IllegalArgumentException("invalid invoice");
                    }
                    return "accepted";
                });
    }
}
```

File `src/test/java/demo/observability/InvoiceObservabilityTest.java`

```java
package demo.observability;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InvoiceObservabilityTest {

    @Test
    void completesObservationAndRecordsLowCardinalityMetric() {
        ObservationRegistry registry = ObservationRegistry.create();
        ObservationProbe probe = new ObservationProbe();

        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            registry.observationConfig()
                    .observationHandler(probe)
                    .observationHandler(new DefaultMeterObservationHandler(meters));

            assertEquals("accepted", new InvoiceProcessor(registry).process("inv-42", true));
            assertEquals(List.of("start", "stop"), probe.events);
            assertEquals("invoice.process", probe.finished.getName());
            assertEquals("validate", probe.finished.getLowCardinalityKeyValue("operation").getValue());
            assertEquals("inv-42", probe.finished.getHighCardinalityKeyValue("invoice.id").getValue());
            assertNull(registry.getCurrentObservation());

            Timer timer = meters.find("invoice.process").tag("operation", "validate").timer();
            assertNotNull(timer);
            assertEquals(1L, timer.count());
            assertNull(timer.getId().getTag("invoice.id"));
        } finally {
            meters.close();
        }
    }

    @Test
    void recordsFailureAndStillStopsObservation() {
        ObservationRegistry registry = ObservationRegistry.create();
        ObservationProbe probe = new ObservationProbe();
        registry.observationConfig().observationHandler(probe);

        var failure = assertThrows(IllegalArgumentException.class,
                () -> new InvoiceProcessor(registry).process("inv-42", false));

        assertEquals(List.of("start", "error", "stop"), probe.events);
        assertSame(failure, probe.finished.getError());
        assertNull(registry.getCurrentObservation());
    }

    @Test
    void createsAChildSpanInTheSameTrace() {
        ObservationRegistry registry = ObservationRegistry.create();
        List<RecordedSpan> spans = new ArrayList<>();
        var current = ThreadLocalCurrentTraceContext.newBuilder().build();

        try (Tracing tracing = Tracing.newBuilder()
                .currentTraceContext(current)
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(new SpanHandler() {
                    @Override
                    public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                        spans.add(new RecordedSpan(span.name(), context.traceIdString(),
                                context.spanIdString(), context.parentIdString(),
                                Map.copyOf(span.tags())));
                        return true;
                    }
                })
                .build()) {
            Tracer tracer = new BraveTracer(tracing.tracer(),
                    new BraveCurrentTraceContext(current), new BraveBaggageManager());
            registry.observationConfig()
                    .observationHandler(new DefaultTracingObservationHandler(tracer));

            Observation.createNotStarted("invoice.batch", registry)
                    .observe(() -> new InvoiceProcessor(registry).process("inv-42", true));

            assertEquals(2, spans.size());
            RecordedSpan parent = findSpan(spans, "invoice.batch");
            RecordedSpan child = findSpan(spans, "invoice.process");
            assertEquals(parent.traceId(), child.traceId());
            assertEquals(parent.spanId(), child.parentId());
            assertEquals("validate", child.tags().get("operation"));
            assertEquals("inv-42", child.tags().get("invoice.id"));
            assertNull(tracer.currentSpan());
            assertNull(registry.getCurrentObservation());
        }
    }

    private static RecordedSpan findSpan(List<RecordedSpan> spans, String name) {
        return spans.stream().filter(span -> span.name().equals(name)).findFirst().orElseThrow();
    }

    private record RecordedSpan(
            String name, String traceId, String spanId, String parentId, Map<String, String> tags) {
    }

    private static class ObservationProbe implements ObservationHandler<Observation.Context> {

        private final List<String> events = new ArrayList<>();
        private Observation.Context finished;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            events.add("start");
        }

        @Override
        public void onError(Observation.Context context) {
            events.add("error");
        }

        @Override
        public void onStop(Observation.Context context) {
            events.add("stop");
            finished = context;
        }
    }
}
```

Run from the project directory.

```bash
gradle test --tests demo.observability.InvoiceObservabilityTest
```

A direct JUnit Platform run on Java 17 yields **3 passed, 0 failed**.

- **The success test** verifies that the Observation carries both key-values and completes its lifecycle properly. The `invoice.process` timer increments exactly once with tag `operation=validate`. The timer's tag set excludes `invoice.id`, confirming that high-cardinality identifiers remain on the right signal type.
- **The failure test** verifies that business code still throws the exception. The Observation retains that exact exception, emits the error event, and then stops. Checking the scope afterward catches context left dangling on the current thread.
- **The tracing test** nests `invoice.process` inside the scope of the `invoice.batch` Observation. `DefaultTracingObservationHandler` bridges the Observation lifecycle to the tracer. Brave invokes `SpanHandler` when a span ends, and the collector stores a snapshot of the fields to verify. The test confirms that both spans share a trace and the child span points to the right parent span. Span names and ID relationships are the values to assert because IDs are generated at runtime.

`Sampler.ALWAYS_SAMPLE` makes the tracing test deterministic. When testing applications that use Spring Boot auto-configuration, you can set `management.tracing.sampling.probability=1.0` in test configuration to avoid flakiness where a test sometimes produces a span and sometimes drops it due to sampling. The production sampling rate is chosen separately based on traffic and ingestion needs.

## Bringing Tests into Spring Boot Actuator

In application code, inject the Spring-managed `ObservationRegistry` into the component to instrument. In unit tests, a fresh registry per test isolates data across cases. In integration tests, if you need to verify auto-configuration, obtain the registry and tracer from the context so the test exercises the actually registered handlers.

Spring Boot 3.3 skips auto-configuring tracing reporters by default in `@SpringBootTest`. If the goal is to test exporting, use `@AutoConfigureObservability` for full integration tests and configure a dedicated test receiver. For a test slice, this annotation provides an Observation registry, an in-memory meter registry, and a no-op tracer when Boot's auto-configuration applies. To test real spans in a slice, explicitly supply a recording tracer and handler, or move that case to an integration test with the configuration to verify.

### When Metrics or Spans Are Missing

1. **Isolate the Observation first.** Verify that the code uses the right registry, a handler supports the context, the operation actually executes, and the lifecycle finishes. If the code relies on `@Observed`, test through a component with the aspect configured, since calling a manually instantiated object directly bypasses that proxy path.
2. **Separate metrics from spans.** For timers, check the name, tags, and counter increment after an operation. For spans, check the tracing handler, sampler, and finished state. Reading `/actuator/metrics` can verify metrics exposed by Actuator, whereas span delivery is verified via a span collector or tracing backend.
3. **Test the exact context-propagation boundary.** The parent–child relationship in the example runs on a single thread. Across HTTP, use a client built from a Boot-configured builder such as `RestClient.Builder`, and check the header for your chosen format, such as `traceparent` for W3C Trace Context. Across executors or reactive pipelines, test at the exact asynchronous boundary where context must be carried over.
4. **Await asynchronously exported data with a condition.** Wait until the collector observes a span matching the expected name and trace, with a clear timeout. Create an isolated collector or clear data between tests. Assert on meaningful attributes rather than comparing entire payloads containing IDs and timestamps that vary per run.

## Reference Documentation

- [Micrometer 1.13 · Testing Observations with a Test Registry](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html)
- [Micrometer 1.13 · Observation Handlers and Metrics](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html)
- [Micrometer Tracing · Tracer Testing Utilities](https://docs.micrometer.io/tracing/reference/1.5/testing.html)
- [Spring Boot 3.3 · Observation, Metrics, and Tracing in Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 · Tracing Bridges, Sampling, and Context Propagation](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)