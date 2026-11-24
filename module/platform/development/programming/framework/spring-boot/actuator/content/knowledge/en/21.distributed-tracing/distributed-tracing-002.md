# Relationship Between Micrometer Tracing, Observation, and Tracer Libraries

## 1. Starting from an Operation to Observe

Suppose an application has a checkout operation that internally invokes a payment step. You want to answer two kinds of questions:

- How many times did the operation run, how long did it take overall, and how often did errors occur?
- Which steps did a specific checkout execution go through, and how do those steps relate to one another?

Metrics fit aggregated questions. Traces fit tracking a single execution and its related operations. The same piece of business code can supply data for both.

**Micrometer Observation describes and manages a single observation; handlers decide what data is produced from that lifecycle. Micrometer Tracing provides a unified tracing API; a bridge connects this API to a concrete tracer library such as Brave or OpenTelemetry.**

These are cooperating roles, not interchangeable names for the same component. An application can use Observation to record metrics without creating spans yet. Conversely, code using the `Tracer` API directly can create spans without creating metrics.

## 2. Component Map

```text
Code instrumented with observation logic
        |
        v
Observation + ObservationRegistry
        |
        +--> Metric handler
        |      --> MeterRegistry
        |      --> metric collection/storage system, depending on configuration
        |
        +--> Tracing handler
               --> Micrometer Tracing API
               --> Brave bridge or OpenTelemetry bridge
               --> corresponding tracer/SDK library
               --> reporter/exporter
               --> collector or trace ingestion system
               --> trace storage and query backend
```

Both the metric branch and the tracing branch receive the appropriate observation lifecycle events. You do not need to rewrite the same business measurement with two separate start-stop blocks just to collect both kinds of data. That is the goal of the handler-based design. [Micrometer: Observation components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

| Component | Responsibility | Should Not Be Confused With |
| --- | --- | --- |
| `Observation` | An observation with a name, context, tags, events, and lifecycle | A span guaranteed to be sent out |
| `ObservationRegistry` | Holds configuration and dispatches handlers for observations | A trace storage backend for querying |
| `MeterRegistry` | Manages meters such as timers and counters | A tracer |
| Micrometer Tracing API | Provides shared types such as `Tracer`, `Span`, and `TraceContext` | A trace storage system |
| Bridge | Translates calls from Micrometer Tracing to a concrete tracer's API | An exporter that sends data |
| Brave or OpenTelemetry SDK | Implements concrete tracer mechanics: spans, context, sampling, and related processing | A trace viewing UI |
| Reporter/exporter | Ships span data out of the process using the chosen protocol/configuration | A bridge API |
| Collector/trace receiver | Receives, optionally processes, and forwards data | A tracer library running inside the application |

In OpenTelemetry, the API and SDK also play different roles: the API is the calling contract, while the SDK provides the implementation and configuration. When saying "use OpenTelemetry as the tracer," keep in mind the application must have a working implementation and configuration, not just the API types.

A collector can be an intermediate step; not every setup requires a separate collector. For example, a reporter can send directly to the ingestion endpoint of a trace storage backend.

## 3. How Is an Observation Turned into a Span?

### 3.1. Handlers Are the Connection Point

Micrometer Tracing integrates with Observation via tracing `ObservationHandler` implementations. For standard local operations, `DefaultTracingObservationHandler` is a primary example.

When this handler uses a real tracer, the synchronous lifecycle can be understood as follows:

| Observation Action | Corresponding Tracing Effect |
| --- | --- |
| Start observation | Create/start a span according to the tracer and current context relationship |
| Open scope | Make the associated span the current span within that scope |
| Report error | Attach error information to the span per handler/tracer mechanics |
| Close scope | Restore the previous span context |
| Stop observation | Finish the span so span processors can receive it |

A metric handler can simultaneously start a timing sample and record a timer when the observation stops. Therefore, a single business lifecycle can produce both aggregate metrics and tracing data. [Micrometer Tracing 1.3: configuring handlers with Observation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html).

This does not mean every observation in every application becomes a span searchable in the monitoring system. You still need to consider:

- Is the observation disabled by a predicate or configuration?
- Does the registry have an appropriate tracing handler?
- Is the handler using an active tracer or a no-op implementation that records no data?
- Does the sampling policy allow recording/sending the span?
- Has the span ended and is the export path working?

An observation skipped completely and a span not exported due to sampling are two different situations. If an observation is blocked at the Observation layer, other handlers may not be called either. If only tracing chooses not to record the span, the metric branch can still work normally.

### 3.2. Not All Tracing Handlers Have the Same Job

For network communication, you need to know the sender/receiver role, destination metadata, and how to inject/extract context. Micrometer provides specialized handlers such as:

- `PropagatingSenderTracingObservationHandler` for the sender side.
- `PropagatingReceiverTracingObservationHandler` for the receiver side.
- `DefaultTracingObservationHandler` for standard local cases.

Configuration can use `FirstMatchingCompositeObservationHandler` to select the first matching tracing handler instead of creating multiple competing spans for the same observation. The metric branch still needs to be handled appropriately on its own; do not put every handler into a "first-match only" group and accidentally drop the other branch.

`TracingAwareMeterObservationHandler` needs to be understood in its proper place: it wraps a metric handler and helps the metric branch coordinate with the tracing context, such as supporting linking measurement samples to traces when the registry supports it. It does not replace the tracing handlers that create and manage spans. Do not assume that merely seeing "Tracing" in a handler's name means you already have a tracer and span export pipeline.

In Boot applications, these handler groups are usually coordinated by auto-configuration. Do not copy manual handler setup from a standalone example into Boot without checking which handlers already exist.

## 4. How Do Micrometer Tracing and Concrete Tracers Differ?

### 4.1. Same Name Tracer, Different APIs

The following three type names belong to three different contracts:

```text
io.micrometer.tracing.Tracer
brave.Tracer
io.opentelemetry.api.trace.Tracer
```

Business code that relies on Micrometer's abstraction typically injects `io.micrometer.tracing.Tracer`, or uses `ObservationRegistry` if a single observation should serve multiple signals.

Bridges provide the corresponding adapters. For instance, `BraveTracer` implements the Micrometer API and delegates calls to `brave.Tracer`. On the OpenTelemetry side, the corresponding bridge uses OpenTelemetry's tracer.

Bridges help keep business observation code from depending directly on a specific tracer's proprietary API. When switching implementations, you still must verify configuration, conventions, context propagation, sampling, and export; do not assume merely swapping dependencies produces identical output details.

### 4.2. A Tracer Library Is Not a Trace Storage System

Brave runs inside the application process to implement the tracer. OpenTelemetry is a broader ecosystem, in which the tracing API/SDK fulfills the corresponding role. They do not automatically turn into a query UI for all system traces simply because the dependency is present.

A reporter/exporter receives completed spans and ships the data to the appropriate receiver. For example:

- The OpenTelemetry bridge can be paired with an OTLP exporter.
- The OpenTelemetry bridge can also be paired with a Zipkin exporter.
- The Brave bridge can be paired with a Zipkin reporter.

Therefore, "choosing a tracer" and "choosing a trace backend" are two related yet distinct decisions. A wire protocol like OTLP is also distinct from the API that Java code uses to create spans. [Micrometer: using the Tracing API and configuring Brave/OpenTelemetry](https://docs.micrometer.io/tracing/reference/api.html).

## 5. Traces, Spans, Parent-Child Relationships, and Scope

A trace describes related operations within a single execution. A span describes one operation with start/end times and accompanying data. Spans in the same trace share a trace ID; span IDs identify individual spans.

Example within one process:

```text
trace T
└── span checkout-flow, id A
    └── span payment-check, id B, parent A
```

This relationship differs from two timers named `checkout` and `payment`:

- A timer aggregates many measurements by name and tag set.
- A span holds data for a single recorded execution.
- Having the same timer name does not mean the same trace.
- Having the same trace ID does not mean the same span.

In the synchronous call path of the example below, the outer observation opens a scope; the child observation starts while the outer context is active. The tracing handler uses that context to form the parent-child relationship.

Scope and span lifecycle are two separate things. Closing a scope stops that span from being the current span in the scope under consideration; it does not substitute for ending the span. Likewise, a fully recorded span can still exist in the storage system after `tracer.currentSpan()` on the current thread has returned `null`.

Across threads or over the network, the corresponding context propagation mechanism is still needed. Having a current span on thread A does not automatically make thread B or another service aware of it. Observed HTTP client/server code can help propagate and extract that information; a bridge does not automatically intercept every network library in the JVM. [OpenTelemetry explanation of traces and spans](https://opentelemetry.io/docs/concepts/signals/traces/).

## 6. How Do Names and Tags Flow to Metrics and Spans?

With typical default handler configuration:

| Observation Data | Metric Branch | Tracing Branch |
| --- | --- | --- |
| Observation name | Basis for the meter name | Fallback name or input to the span naming convention |
| `contextualName` | Does not automatically rename the meter | Can be used as a more readable span name |
| Low-cardinality tags (`low cardinality`) | Used as metric tags | Can be added to the span |
| High-cardinality tags (`high cardinality`) | Not turned into metric tags by the default metric handler | Can be added to the span |
| Errors/events | Representation decided by the corresponding handler | Can become error/event data on the span |

Custom conventions or handlers can change output details. Inspect the actual running configuration rather than treating this table as a rule for every user-written handler.

An order ID with many distinct values can be useful for looking up a specific span, yet it is unsuitable as a metric tag for every order. Trace IDs should also not be added to every timer tag combination: doing so explodes an aggregate metric into too many time series.

Observation/span tags also differ from baggage. Baggage serves to carry contextual data across configured boundaries; adding a tag to a span does not automatically propagate that tag to every service. Choose collected data deliberately and avoid putting sensitive information into observability data.

## 7. Choosing Observation or Using Tracer Directly?

| Need | Usually Suitable Entry Point |
| --- | --- |
| Observe an operation to produce both metrics and traces based on configuration | `ObservationRegistry` and Observation API |
| Create only a span without needing to create metrics for that operation | Micrometer `Tracer` API |
| Work with capabilities specific to an SDK/tracer not expressed by the common API | Proprietary API, with clearly scoped dependencies |
| Inspect received traces and investigate a specific execution | Trace storage/query backend |

When creating only a span directly, the basic lifecycle is start span → open scope when needed → run work → close scope → end span. Opening a scope lets inner code find the current span, yet you still must end the span to complete recording.

Do not create both an observation and a manual span wrapping the exact same operation simply thinking "both are required for tracing." If the observation handler already creates an appropriate span, adding another span can introduce redundant layers into the trace tree.

## 8. Integration in Spring Boot 3.3.x

### 8.1. Dependencies Representing Each Role

In a Boot application that already has the plugin/BOM, one option using OpenTelemetry and OTLP is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
```

This is the dependency snippet within an existing build, not a complete Gradle project. Boot manages compatible versions; do not manually mix the standalone example's versions below into a Boot application.

Several combinations supported by Boot 3.3:

| Tracer/Bridge | Trace Export Component | Receiver Configuration Group |
| --- | --- | --- |
| `micrometer-tracing-bridge-otel` | `opentelemetry-exporter-otlp` | `management.otlp.tracing.*` |
| `micrometer-tracing-bridge-otel` | `opentelemetry-exporter-zipkin` | `management.zipkin.tracing.*` |
| `micrometer-tracing-bridge-brave` | `io.zipkin.reporter2:zipkin-reporter-brave` | `management.zipkin.tracing.*` |

All rows assume appropriate Actuator infrastructure is present. Bridges are in the `io.micrometer` group; OpenTelemetry exporters are in the `io.opentelemetry` group.

Pick one clear tracing path for an implementation example. Do not add both bridges just to "be sure tracing works" and skip identifying which tracer and auto-configuration are active. [Spring Boot 3.3: tracer and exporter combinations](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 8.2. Using Boot-Configured Infrastructure

In business code, inject the application-managed registry/tracer. Calling `ObservationRegistry.create()` inside a service creates a separate registry; that registry does not automatically contain the handlers Boot registered.

For an operation that already has framework-provided observation logic, check existing data before adding observation code at the same boundary. Also do not manually register duplicate default handlers onto Boot's registry if auto-configuration already provides them.

To observe all executions in a learning environment, you can configure tracing sampling:

```yaml
management:
  tracing:
    sampling:
      probability: 1.0
```

This is sampling for tracing, not a ratio deciding how many executions a timer records. Nor does it fix receiver, protocol, or exporter connection errors. A span chosen for recording still needs a working export pipeline to appear in the query backend.

You do not need to add business endpoints solely to prove how the library layers cooperate. The in-memory experiment below is sufficient to verify the Observation → handler → tracer and metric relationships.

## 9. Experiment: Same Observation Code, With or Without a Tracing Handler

### 9.1. Goal and Environment

The experiment uses JDK 21, Micrometer Core/Observation 1.13.0, Micrometer Tracing bridge Brave 1.3.0, and Brave 6.0.3 via the bridge's dependency. This is the Boot 3.3.0 library generation, pinned for a standalone experiment folder.

The program has two modes:

- `both`: registers both the metric handler and the tracing handler.
- `metrics-only`: keeps the metric handler, does not register the tracing handler.

In both modes, the business observation code is identical. Completed spans are collected in memory by a Brave `SpanHandler`; the program does not send traces over the network and does not require a trace storage system.

### 9.2. Dependencies in pom.xml

Create `pom.xml` in a dedicated folder:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>observation-tracing-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
            <version>1.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-nop</artifactId>
            <version>1.7.36</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
```

Maven resolves the bridge's transitive dependencies, including Micrometer Tracing and Brave. The `slf4j-nop` dependency only serves to suppress SLF4J log output in the experiment; it is not a metric/span-producing component.

### 9.3. Complete ObservationTracingDemo.java

Save next to `pom.xml`, without a package declaration:

```java
import java.util.ArrayList;
import java.util.List;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

public class ObservationTracingDemo {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "both" : args[0];
        if (!mode.equals("both") && !mode.equals("metrics-only")) {
            throw new IllegalArgumentException("Use both or metrics-only");
        }
        boolean tracingEnabled = mode.equals("both");
        List<MutableSpan> finished = new ArrayList<>();

        SpanHandler collector = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                finished.add(new MutableSpan(span));
                return true;
            }
        };

        var meters = new SimpleMeterRegistry();
        try (Tracing brave = Tracing.newBuilder()
                .localServiceName("observation-demo")
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(collector)
                .build()) {
            Tracer tracer = new BraveTracer(brave.tracer(),
                    new BraveCurrentTraceContext(brave.currentTraceContext()));
            var observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));
            if (tracingEnabled) {
                observations.observationConfig()
                        .observationHandler(new DefaultTracingObservationHandler(tracer));
            }

            System.out.println("mode=" + mode);
            int result = Observation.createNotStarted("checkout", observations)
                    .contextualName("checkout-flow")
                    .lowCardinalityKeyValue("channel", "demo")
                    .highCardinalityKeyValue("order.id", "ORD-42")
                    .observe(() -> {
                        System.out.println("observation.current="
                                + (observations.getCurrentObservation() != null));
                        System.out.println("span.current=" + (tracer.currentSpan() != null));
                        return Observation.createNotStarted("payment", observations)
                                .contextualName("payment-check")
                                .observe(() -> 42);
                    });

            var checkoutTimer = meters.get("checkout").timer();
            System.out.println("result=" + result);
            System.out.println("checkout.timer.count=" + checkoutTimer.count());
            System.out.println("payment.timer.count="
                    + meters.get("payment").timer().count());
            System.out.println("metric.high.tag.absent="
                    + (checkoutTimer.getId().getTag("order.id") == null));
            System.out.println("finished.spans=" + finished.size());
            System.out.println("span.names=" + finished.stream()
                    .map(MutableSpan::name).toList());
            System.out.println("observation.cleared="
                    + (observations.getCurrentObservation() == null));
            System.out.println("span.cleared=" + (tracer.currentSpan() == null));

            if (checkoutTimer.count() != 1
                    || meters.get("payment").timer().count() != 1
                    || finished.size() != (tracingEnabled ? 2 : 0)
                    || observations.getCurrentObservation() != null
                    || tracer.currentSpan() != null) {
                throw new AssertionError("Unexpected observation results");
            }

            if (tracingEnabled) {
                MutableSpan parent = find(finished, "checkout-flow");
                MutableSpan child = find(finished, "payment-check");
                boolean sameTrace = parent.traceId().equals(child.traceId());
                boolean parentMatches = parent.id().equals(child.parentId());
                System.out.println("same.trace=" + sameTrace);
                System.out.println("parent.matches=" + parentMatches);
                System.out.println("span.low.tag=" + parent.tag("channel"));
                System.out.println("span.high.tag=" + parent.tag("order.id"));

                Span direct = tracer.nextSpan().name("span-only").start();
                try (Tracer.SpanInScope scope = tracer.withSpan(direct)) {
                    direct.tag("mode", "direct");
                } finally {
                    direct.end();
                }
                System.out.println("direct.span.finished="
                        + finished.stream().anyMatch(s -> "span-only".equals(s.name())));
                System.out.println("direct.timer.exists="
                        + (meters.find("span-only").timer() != null));
                if (!sameTrace || !parentMatches || finished.size() != 3
                        || meters.find("span-only").timer() != null) {
                    throw new AssertionError("Unexpected tracing relationship");
                }
            }
        } finally {
            meters.close();
        }
    }

    static MutableSpan find(List<MutableSpan> spans, String name) {
        return spans.stream().filter(span -> name.equals(span.name()))
                .findFirst().orElseThrow();
    }
}
```

Key points to note in the code:

- The `tracer` variable has type `io.micrometer.tracing.Tracer`; its value is `BraveTracer`, while `brave.tracer()` provides the underlying tracer.
- `DefaultTracingObservationHandler` connects the observation registry to that tracer.
- `DefaultMeterObservationHandler` records metrics into `SimpleMeterRegistry`, independent of whether a tracing handler is registered.
- `Sampler.ALWAYS_SAMPLE` makes the span count in the experiment deterministic; do not predict a random rate.
- `SpanHandler` captures copies of completed spans. This is a Brave API, different from Micrometer's `ObservationHandler`.
- The observations use `observe(...)` to manage scope and completion. The directly created span uses `finally` to end itself.
- Order ID `ORD-42` is dummy data for comparing tags in the experiment.

### 9.4. Compile and Run

Select JDK 21 for both `javac` and `java`, with Maven available, then run in PowerShell. Proceed to the next command only when the previous one succeeds:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ObservationTracingDemo.java
java -cp ".;$demoClasspath" ObservationTracingDemo both
java -cp ".;$demoClasspath" ObservationTracingDemo metrics-only
```

The first run requires Maven repository access to download dependencies. The `;` character is the Windows classpath separator; on Linux/macOS use `:`.

Stdout in `both` mode, excluding Maven messages:

```text
mode=both
observation.current=true
span.current=true
result=42
checkout.timer.count=1
payment.timer.count=1
metric.high.tag.absent=true
finished.spans=2
span.names=[payment-check, checkout-flow]
observation.cleared=true
span.cleared=true
same.trace=true
parent.matches=true
span.low.tag=demo
span.high.tag=ORD-42
direct.span.finished=true
direct.timer.exists=false
```

Stdout in `metrics-only` mode:

```text
mode=metrics-only
observation.current=true
span.current=false
result=42
checkout.timer.count=1
payment.timer.count=1
metric.high.tag.absent=true
finished.spans=0
span.names=[]
observation.cleared=true
span.cleared=true
```

The program does not print concrete trace IDs/span IDs because those values are generated at runtime. Instead, it checks relationships as booleans. Do not assume a fixed duration ahead of time for the timers.

### 9.5. What Do the Results Prove?

| Evidence | Conclusion Within the Experiment's Scope |
| --- | --- |
| Both modes have two timers, each with count 1 | Observation code and the metric handler still work without a tracing handler |
| `span.current=true` in `both` | The observation scope made the handler-created span current |
| `span.current=false` in `metrics-only` | Having a current observation does not mean there is a current span |
| `finished.spans=2` in `both` | Two observations created and completed two spans via the Brave bridge |
| `same.trace=true`, `parent.matches=true` | The payment span shares the trace and uses the checkout span as its parent |
| `span.names=[payment-check, checkout-flow]` | The child span finishes before the parent span; names come from contextual names in this configuration |
| `metric.high.tag.absent=true` yet `span.high.tag=ORD-42` | High-cardinality tags are not added to timers but are present on spans |
| Both `cleared=true` lines | After the call, the scopes returned the current context to having no active observation/span |
| `direct.span.finished=true`, `direct.timer.exists=false` | Calling Micrometer Tracer directly creates a standalone span without automatically creating a timer of the same name |

In `metrics-only`, the tracer/bridge is still initialized and present on the classpath, yet is not wired to the registry with a tracing handler. This deliberately separates two questions: "is there a tracer library?" and "are observations being turned into spans?".

`finished.spans=2` is printed before the direct span section. After that section, the in-memory list holds three spans; the program's assertion checks this exact sequence.

The experiment does not yet prove trace propagation across two services or successful export to an external system. Those two capabilities require testing the corresponding context propagation boundary and exporter.

## 10. How to Narrow Down When Metrics Exist but Traces Do Not

Check along the data path:

1. **Observation:** did the code actually run, was the observation skipped, and is the registry the application's actual registry?
2. **Handler:** does the registry have an appropriate tracing handler, or only a metric handler?
3. **Tracer/bridge:** which implementation is the application using; is a no-op tracer active?
4. **Scope and context:** inspect the current span inside the scope under test, not only after the scope has closed.
5. **Sampling and completion:** was the span sampled for recording and has it ended?
6. **Export:** do the reporter/exporter, receiver endpoint, and protocol match; has the data been processed/forwarded to the query backend?

`tracer.currentSpan() != null` alone does not prove a span was exported. Conversely, `currentSpan() == null` after closing a scope is normal and does not mean the span was lost from storage.

| Misconception | Correct Understanding |
| --- | --- |
| Having Actuator guarantees traces are sent out | You also need an appropriate tracer/bridge, handlers, and export pipeline |
| A bridge is the exporter | The bridge adapts the API; the exporter/reporter transports the data |
| Choosing Brave means writing business code with brave.Tracer | You can use the Micrometer API through the bridge |
| Using OpenTelemetry requires dropping Micrometer Observation | Observation can use the Micrometer Tracing OpenTelemetry bridge |
| Each metric corresponds to exactly one trace | Metrics aggregate many executions; traces represent individual recorded executions |
| Adding a span directly also automatically adds a timer | The standalone Tracer API does not automatically pass through Observation's metric branch |
| Span tags automatically become headers sent to other services | Context/baggage propagation requires corresponding mechanisms and configuration |
| Logs containing a trace ID guarantee the trace reached storage | Log correlation and trace export are two separate steps to verify |

## 11. Self-Check Exercises

1. Run both modes and point out the lines proving Observation does not strictly depend on span creation.
2. Change only the `contextualName` of the checkout observation. Verify that the span name changes while querying the timer still uses `checkout` under the current configuration.
3. Change `order.id` from a high-cardinality key value to a low-cardinality key value in the experiment. Observe the timer tags and explain why this approach is unsuitable when order counts grow without bound.
4. Keep the bridge/tracer while omitting the tracing handler registration. Explain why this still does not form a complete Observation → span chain.
5. Identify the component that must be replaced when switching from Brave to OpenTelemetry, and the component that must be added to send spans out of memory.
6. For a real call path, separately locate where observations are created, the tracing handler, bridge, tracer, and exporter. Inspect one step at a time to pinpoint exactly where data stops.
