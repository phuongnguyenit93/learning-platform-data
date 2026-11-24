# Understanding Endpoints, Health Indicators, Meters, Observations, and Traces

## 1. One Transaction, Many Different Questions

Suppose placing an order requires checking inventory and then recording the order. When operating the service, you might want to know:

- How is inventory availability currently being evaluated?
- How many orders have been accepted?
- How long did recent executions take?
- What steps did a specific order placement go through?
- Where do management tools read that information from?

These five questions relate to the same application, yet they do not ask for the same kind of data. Accordingly, Actuator and the Micrometer ecosystem use distinct concepts with separate responsibilities.

| Concept | Key role to remember | Example in an ordering service |
| --- | --- | --- |
| Management access point — endpoint | Exposes a read or management capability | `health`, `metrics`, custom endpoint |
| Status checker — health indicator | Evaluates a specific condition | Checks whether a resource can be used |
| Measuring instrument — meter | Records or reads measurements | Counter of accepted orders, timer of processing duration |
| Observed activity — observation | Models the lifecycle of an execution so handlers record signals | One order execution starts, hits an error, and finishes |
| Execution path — trace | Links related units of work across an execution | Place order → check inventory → save order |

**An endpoint is an exposure mechanism; a health indicator is a check; a meter is a measuring instrument; an observation is an integration hook for observing work; a trace is data describing an execution journey.** Do not use these terms interchangeably.

This lesson explains them using Spring Boot **3.3.13**, Micrometer **1.13.x**, and Micrometer Tracing **1.3.x** as managed by Boot. The complete runnable example uses Java **21**.

## 2. Endpoint: Exposing Management Capabilities

### 2.1. Identity and Access Mechanism Are Two Separate Parts

In Actuator, an endpoint has an ID and operations. For instance, the `health` endpoint provides status information. When exposed over HTTP with the standard prefix, its path is `/actuator/health`.

Separate three things:

~~~text
ID:        health
Operation: read status information
Exposure:  HTTP at /actuator/health or another suitable mechanism
~~~

`@Endpoint` identifies an endpoint type; annotations such as `@ReadOperation` describe operations. Actuator can adapt those operations to exposure technologies such as HTTP or JMX. [@Endpoint contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

“Endpoint” is also widely used to refer to business APIs. In this lesson, unless stated otherwise, the term refers specifically to **an Actuator management endpoint**. A `@GetMapping("/orders")` method does not automatically become an Actuator endpoint.

### 2.2. An Endpoint Does Not Necessarily Produce Data Itself

An endpoint can read data from other components:

~~~text
HealthIndicator ------> health endpoint ------> status consumer
MeterRegistry --------> metrics endpoint -----> metrics consumer
Custom data ----------> custom endpoint ------> management tool
~~~

For example, `metrics` is a query interface over managed meters. Adding a name to the web exposure list does not automatically create a business measurement with that name.

To be readable over the web, matching components must exist, the endpoint must be enabled, it must be exposed over HTTP, and the request must pass access-control rules. In Boot 3.3, only `health` is exposed over HTTP by default. [Endpoint and exposure mechanics](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Exposure and authorization serve different purposes. When applying them, determine who needs to read management data and which details are appropriate for them to see.

## 3. Health Indicator: A Scoped Evaluation

### 3.1. Input Is a Check Condition, Output Is Health

`HealthIndicator` is the interface that contributes a `Health` result to the health subsystem. Its key method is `health()`. The result contains a status and optionally extra details. [HealthIndicator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Conceptually:

~~~text
"Can resource X be used according to the defined check?"
    -> evaluate condition
    -> UP or DOWN with appropriate details
~~~

The scope of that question matters greatly. If a check only confirms connectivity to a data store, it does not prove that all ordering rules work properly.

Do not infer `UP` to mean “all business logic is guaranteed to succeed”. The status is meaningful only within the scope of conditions actually checked.

### 3.2. Indicators Contribute to the Health Endpoint

In a Boot application, multiple components can contribute health status. The health endpoint organizes and exposes the combined picture. Aggregation relies on a status policy; it is not a majority vote like “if most are UP, the whole system is UP”. [Default StatusAggregator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

Also keep these separate:

- The `Health` status in the model layer.
- Rules selecting which details are exposed.
- The HTTP status code mapped by the health exposure layer.

A `"DOWN"` string inside a custom endpoint’s payload does not automatically trigger all behavior of the health endpoint. Mapping statuses to HTTP codes is handled by a dedicated component. [HttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 3.3. Choose Meaningful Checks

When writing an indicator, state clearly which condition is being evaluated. For example:

- “The application has enough free disk space against the chosen threshold.”
- “A connectivity check to the data source succeeds.”
- “An internal component is currently marked ready to serve.”

Never make a health check perform a destructive data transaction just to see if the system is “alive”. For external resources, account for timeouts and the cost of running the check.

The runnable example in this lesson uses a simulated flag to clarify the `HealthIndicator` contract. It does not pretend to be a real warehouse connection check.

## 4. Meter: The Instrument Producing Measurements

### 4.1. A Meter Differs from a Single Metric Value

`Meter` is the interface that collects a set of measurements. When people say “metric”, they often mean an exposed measurement or time series. A single meter can yield multiple statistics; hence there is no rule that “one meter equals one number”. [Meter concepts](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

Three types to recognize early:

| Type | Usage | Example |
| --- | --- | --- |
| `Counter` | Accumulates occurrences via positive increments | Accepted orders count |
| `Timer` | Records duration and count of measured executions | Processing duration of order attempts |
| `Gauge` | Reads the value of state at observation time | Number of pending jobs |

A `Counter` is not where you put the number of pending jobs, because that quantity can go down. To compute a rate from a counter, examine change over a time interval and account for process restarts. [Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

A `Timer` already tracks count and total time. If you only want to count the exact invocations timed by the timer, you usually do not need a duplicate counter. A separate counter remains useful for representing a different business outcome—for example, “accepted orders” while the timer measures all attempts. [Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

A `Gauge` reflects the value at sampling time; intermediate changes between samples may not be retained. A current queue length does not tell you how long the queue peaked yesterday. [Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

### 4.2. MeterRegistry Manages Meters

`MeterRegistry` manages meters. Names and tags distinguish measurement groups.

Conceptual example:

~~~text
Name:     checkout.duration
Tags:     channel=web, result=success
Data:     count, total time, supported statistics
~~~

One meter is reused across many executions. By contrast, an observation in the next section represents a single specific execution. That is a lifecycle difference:

~~~text
1 meter used across many executions
        ^
        | records
        +--- execution 1
        +--- execution 2
        +--- execution 3
~~~

Once data is aggregated, you cannot reconstruct the full story of every individual run from a total alone. That is why metrics and traces answer different questions.

## 5. Observation: Connecting Work Lifecycle to Signal Handlers

### 5.1. An Observation Models One Execution

`Observation` lets you describe when an activity starts, encounters an error or event, enters the current scope, and stops. Matching `ObservationHandler` instances react to that lifecycle.

One handler can record a timer; another can create a span. **Observation does not automatically mean timer or span.** What data is actually produced depends on the active handlers and configuration. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

Simple model:

~~~text
One business execution
        |
        v
Observation + Context
        |
        +--> metrics handler --> MeterRegistry
        |
        +--> tracing handler --> span
~~~

The benefit is that business code describes an activity in one place, while how signals are recorded can be configured in the integration layer.

### 5.2. ObservationRegistry Differs from MeterRegistry

The two registries have different responsibilities:

| Component | What it manages |
| --- | --- |
| `MeterRegistry` | Meters and how they record/publish measurements |
| `ObservationRegistry` | Observation configuration, including handlers and related policies |
| `Tracer` | Creating and managing spans and tracing context |

`Observation.Context` holds data for one execution so handlers can coordinate. `ObservationConvention` standardizes names and descriptive metadata; predicates can filter out observations; filters can enrich the context. You do not need to author all of these components yet to grasp the core relationship. [Observation components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

In a Spring Boot application, inject the auto-configured registries rather than creating separate standalone registries inside individual services. Creating a new registry object can route measurements into a configuration isolated from what the rest of the system publishes.

### 5.3. Scope Identifies the Currently Active Work

The current scope tells handlers which observation or span currently wraps the work. That allows a child activity to be linked to its parent activity.

With the synchronous style in this lesson, `observe(...)` manages starting, opening the scope, running the lambda, recording any error, closing the scope, and stopping the observation. If managing manually, always ensure the scope is closed and the observation stopped even when exceptions occur.

Never share a single observation instance across all requests. Each execution needs its own context; aggregated totals go into shared meters.

## 6. Low- vs. High-Cardinality Tags: Why Distinguish Them?

The number of distinct values a tag can carry is called its cardinality.

- `channel` with a few choices like `web` or `mobile` has a small value domain.
- `order.id` keeps generating a new value for every order.
- `traceId` also has huge numbers of distinct values.

Under Boot’s Observation integration, low-cardinality data goes into metrics and traces; high-cardinality data is meant for traces and is not automatically added to metric tags by that default pipeline. [Observability key-value rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This matters because tag combinations multiply the number of measurement series. For instance, 3 channels and 4 regions yield at most 12 channel–region combinations. Adding an order ID with millions of values can cause series counts to explode as those values are used.

Attaching `order.id` via `highCardinalityKeyValue(...)` describes individual runs for tracing under matching configuration. It does not prevent you from manually registering a poorly designed meter with order IDs as tags. Code authors must still choose tags intentionally.

Data sent to traces must also be chosen carefully: supporting high cardinality is no excuse to log secrets or sensitive user data indiscriminately.

## 7. Trace: Linking Spans of a Journey

### 7.1. A Span Is a Unit of Work; a Trace Is the Combined Picture

A span describes one unit of work, typically with a name, start/end timestamps, identifiers, and associated metadata. A trace connects related spans to show an execution journey. A trace can stay within a single process or span multiple services. [OpenTelemetry: Traces and spans](https://opentelemetry.io/docs/concepts/signals/traces/).

Simple two-span model:

~~~text
Trace T
└── Span A: checkout
    └── Span B: stock.check
~~~

Both spans share the same trace ID. Each span has its own span ID. The child span references the parent span; the root span has no parent in this model.

The labels `T`, `A`, and `B` here are purely explanatory, not identifiers generated by the program.

A trace is not a chronological list of all log lines. It preserves recorded work structure. When concurrent work runs, you cannot deduce parent–child order just by looking at log line order.

### 7.2. Context Propagation Connects the Journey Across Boundaries

When calling another service, the sender must propagate context and the receiver must restore it properly to link spans. Over HTTP, a standard mechanism is the W3C Trace Context `traceparent` header. When switching threads or handing off to asynchronous processing, context must also be propagated properly. [Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

Having two observations in two services is not enough to make them part of the same trace. If context propagation breaks, the data turns into disconnected traces.

In a Boot application, use the configured integration components—such as Boot-provided HTTP client builders—when you want automatic tracing propagation. [Tracing in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 7.3. Recording Spans, Exporting Data, and Viewing Traces Are Separate Steps

A typical pipeline:

~~~text
Observed operation
    -> tracing handler / tracer
    -> span finished
    -> data export mechanism
    -> trace storage and query system
~~~

Having metrics does not guarantee tracing is configured. Having a tracer does not guarantee an external system received the data. Sampling can also cause only a fraction of journeys to be recorded/exported to bound cost.

Therefore, do not expect a built-in `/actuator/trace` endpoint to download all distributed traces by default. Verify the actual collection pipeline of the tracing stack in use.

## 8. Combining Five Concepts Without Mixing Responsibilities

Consider an order request:

1. Business logic checks inventory conditions and decides whether to accept the order.
2. Observation wraps the execution to provide lifecycle and context.
3. The meter handler updates timers; business code may increment a counter for “accepted” outcomes.
4. The tracing handler creates corresponding spans if tracing is configured.
5. An indicator can evaluate inventory conditions under its own contract when queried.
6. A management endpoint exposes appropriate information to readers.

This is an illustrative integration model, not a mandatory pipeline that every request must traverse.

In particular, none of these automatic implications hold:

- A span with an error does not automatically flip every health indicator to `DOWN`.
- A health indicator returning `DOWN` does not automatically create an error trace.
- Querying the metrics endpoint does not mean it only just started measuring operations.
- Exposing more endpoints does not automatically install a trace exporter.
- Having a timer counting all attempts does not mean all attempts succeeded.

Each signal answers its own question. To make them reflect the same business condition, you must design and verify that relationship.

## 9. Complete Example: Two Executions, One Rejected

The following program runs in the console to illustrate the relationships among the five concepts. It uses genuine Actuator/Micrometer APIs and a Brave tracer, **without starting a Spring ApplicationContext or HTTP server**.

The purpose of this setup is to let you see how objects and handlers are wired together. In a typical Boot application, much of this wiring is handled by auto-configuration.

Conditions and limits of this example:

- Uses JDK 21 and Maven; initial run requires downloading dependencies.
- Both runs execute synchronously on a single thread.
- A flag simulates inventory availability; there is no real warehouse service.
- All spans are sampled and collected into an in-memory list; nothing is sent to an external backend.
- `TrainingEndpoint` is invoked directly from Java. Its annotation does not open an HTTP port inside a console program.

### 9.1. Structure and Dependencies

~~~text
signal-concept-demo/
├── pom.xml
└── src/main/java/SignalConceptDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>signal-concept-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The parent pins compatible library versions. `micrometer-core` is declared directly because the program uses meter APIs; the Brave bridge connects Micrometer Tracing to the Brave implementation.

### 9.2. Java Code

File `src/main/java/SignalConceptDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public class SignalConceptDemo {
    record FinishedSpan(String traceId, String spanId, String parentId,
                        String operation, boolean error) {}

    @Endpoint(id = "training")
    public static final class TrainingEndpoint {
        private final HealthIndicator stockHealth;
        private final Counter accepted;

        public TrainingEndpoint(HealthIndicator stockHealth, Counter accepted) {
            this.stockHealth = stockHealth;
            this.accepted = accepted;
        }

        @ReadOperation
        public Map<String, Object> read() {
            return Map.of(
                "stock", stockHealth.health().getStatus().getCode(),
                "accepted", (long) accepted.count()
            );
        }
    }

    public static void main(String[] args) {
        List<FinishedSpan> spans = new ArrayList<>();
        SpanHandler recorder = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                spans.add(new FinishedSpan(
                    context.traceIdString(), context.spanIdString(),
                    context.parentIdString(), span.name(), span.error() != null
                ));
                return true;
            }
        };

        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try (Tracing tracing = Tracing.newBuilder()
                 .currentTraceContext(ThreadLocalCurrentTraceContext.create())
                 .sampler(Sampler.ALWAYS_SAMPLE)
                 .addSpanHandler(recorder)
                 .build()) {
            BraveTracer tracer = new BraveTracer(
                tracing.tracer(),
                new BraveCurrentTraceContext(tracing.currentTraceContext()),
                new BraveBaggageManager()
            );
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                .observationHandler(new DefaultMeterObservationHandler(meters))
                .observationHandler(new DefaultTracingObservationHandler(tracer));

            AtomicBoolean stockReady = new AtomicBoolean(true);
            HealthIndicator stockHealth = () -> stockReady.get()
                ? Health.up().build()
                : Health.down().withDetail("reason", "stock-disabled").build();
            Counter accepted = meters.counter("demo.orders.accepted", "channel", "web");
            TrainingEndpoint endpoint = new TrainingEndpoint(stockHealth, accepted);

            System.out.println("health.before=" + stockHealth.health().getStatus().getCode());
            checkout(observations, stockReady, accepted, "order-101");

            stockReady.set(false);
            boolean rejected = false;
            try {
                checkout(observations, stockReady, accepted, "order-102");
            } catch (IllegalStateException expected) {
                rejected = true;
            }

            long attempts = meters.find("demo.checkout").timers().stream()
                .mapToLong(Timer::count).sum();
            long checks = meters.find("demo.stock.check").timers().stream()
                .mapToLong(Timer::count).sum();
            long traceCount = spans.stream().map(FinishedSpan::traceId).distinct().count();
            long roots = spans.stream().filter(s -> s.parentId() == null).count();
            long children = spans.size() - roots;
            boolean parentsValid = roots == 2 && children == 2
                && spans.stream().filter(s -> s.parentId() != null).allMatch(child ->
                    spans.stream().anyMatch(parent ->
                        parent.spanId().equals(child.parentId())
                            && parent.traceId().equals(child.traceId())));
            boolean orderIdInMetricTags = meters.getMeters().stream()
                .flatMap(meter -> meter.getId().getTags().stream())
                .anyMatch(tag -> tag.getKey().equals("order.id"));

            System.out.println("rejected=" + rejected);
            System.out.println("health.after=" + stockHealth.health().getStatus().getCode());
            System.out.println("accepted=" + (long) accepted.count());
            System.out.println("checkout.timer.count=" + attempts);
            System.out.println("stock.timer.count=" + checks);
            System.out.println("trace.count=" + traceCount);
            System.out.println("span.count=" + spans.size());
            System.out.println("parents.valid=" + parentsValid);
            System.out.println("error.spans=" + spans.stream().filter(FinishedSpan::error).count());
            System.out.println("orderId.in.metric.tags=" + orderIdInMetricTags);
            System.out.println("endpoint.stock=" + endpoint.read().get("stock"));
            System.out.println("endpoint.accepted=" + endpoint.read().get("accepted"));
        } finally {
            meters.close();
        }
    }

    private static void checkout(ObservationRegistry observations,
                                 AtomicBoolean stockReady, Counter accepted,
                                 String orderId) {
        Observation.createNotStarted("demo.checkout", observations)
            .lowCardinalityKeyValue("channel", "web")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> {
                Observation.createNotStarted("demo.stock.check", observations)
                    .observe(() -> {
                        if (!stockReady.get()) {
                            throw new IllegalStateException("Stock is unavailable");
                        }
                    });
                accepted.increment();
            });
    }
}
~~~

### 9.3. Build and Run

In the directory containing `pom.xml`, using PowerShell on Windows:

~~~powershell
mvn -q dependency:copy-dependencies
New-Item -ItemType Directory -Force target/classes | Out-Null
javac --release 21 -encoding UTF-8 -cp "target/dependency/*" -d target/classes src/main/java/SignalConceptDemo.java
java -cp "target/classes;target/dependency/*" SignalConceptDemo
~~~

Maven copies dependencies into `target/dependency`; `javac` compiles the source file with that classpath; `java` runs the compiled program.

On Linux or macOS, create the directory with `mkdir -p target/classes` and change the classpath separator in the run command to a colon:

~~~bash
java -cp "target/classes:target/dependency/*" SignalConceptDemo
~~~

Standard output of the program:

~~~text
health.before=UP
rejected=true
health.after=DOWN
accepted=1
checkout.timer.count=2
stock.timer.count=2
trace.count=2
span.count=4
parents.valid=true
error.spans=2
orderId.in.metric.tags=false
endpoint.stock=DOWN
endpoint.accepted=1
~~~

Timing values and tracing IDs are not printed because they vary between runs. The program verifies relationships between IDs rather than assuming fixed IDs.

## 10. Explaining Each Group of Evidence

### 10.1. Health Evaluates the Current Condition

Initially, `stockReady` is `true`, so the indicator returns `UP`. After the flag is flipped to `false`, the indicator returns `DOWN`. This comes from a clearly defined check.

The `checkout` method reads the flag to make a business decision. The indicator also reads the flag to assess status. Both share the simulated condition; the indicator is not a hidden controller deciding on behalf of business logic.

In real systems, verify whether both evaluations share the same scope and timing requirements. A periodic check passing does not guarantee a resource will keep succeeding on every subsequent transaction.

### 10.2. Success Counter and Attempt Timer Have Different Meanings

The first run passes the inventory check and increments `demo.orders.accepted`. The second run throws an exception before incrementing the counter. Therefore:

~~~text
Accepted orders = 1
Measured checkout attempts = 2
Measured stock checks = 2
~~~

Timers do not only count successful runs. `observe(...)` still closes out the observation when the lambda throws an exception, so the failed run is also recorded.

The program sums `count` across timers with the same name because error tags or other tags may split them into multiple meters. Reading only the success group and treating it as all attempts would lead to the wrong conclusion.

### 10.3. Observation Produces Signals Through Handlers

These two handler registration lines are the crucial wiring:

~~~java
observations.observationConfig()
    .observationHandler(new DefaultMeterObservationHandler(meters))
    .observationHandler(new DefaultTracingObservationHandler(tracer));
~~~

The meter handler feeds lifecycle timing into timers. The tracing handler uses the tracer to create spans.

`ObservationRegistry` is neither a store of all metrics nor a long-term trace storage system. It manages how observation runs are processed.

In the program’s default setup, `order.id` is high-cardinality data. The output `orderId.in.metric.tags=false` confirms that tag did not enter the meters present in the example.

### 10.4. Two Traces, Each Containing Two Spans

Each call to `checkout` starts with no active parent span. Hence there are two separate traces:

~~~text
Trace for order-101
└── checkout
    └── stock.check

Trace for order-102
└── checkout
    └── stock.check
~~~

When the stock-check observation opens inside checkout’s scope, the tracing handler links the child span to the parent span. `parents.valid=true` verifies that both child spans reference their parent span’s ID and share the parent’s trace ID.

The failed run throws an exception inside the stock-check activity. The exception propagates out through the checkout lambda, so both observations in that run record an error. That is why `error.spans=2`.

Do not read this number 2 as “two failed orders”. These are **two error-marked spans belonging to the same single order attempt**. Count units must always match business semantics.

### 10.5. Endpoint Exposes One View

`TrainingEndpoint.read()` reads the indicator and counter and returns a data structure. It does not place new orders, increment counters on its own, or automatically start traces for arbitrary Java calls.

The final output shows inventory status `DOWN` and accepted orders `1`. This illustrates the endpoint’s role: exposing data from underlying sources.

To bring this kind of endpoint into a Boot application over HTTP, register it as a bean, have the appropriate web/Actuator infrastructure, and configure exposure and access permissions. Simply instantiating `new TrainingEndpoint(...)` as in the console program does not meet those requirements.

Even when exposed, a custom payload field holding `"DOWN"` does not automatically turn this endpoint into the health endpoint with all its status-mapping rules.

## 11. Common Pitfalls When Applying These Concepts

| Pitfall | How to double-check |
| --- | --- |
| “Endpoints are where all data is generated” | Locate the component producing or supplying the data behind the endpoint |
| “A health indicator is the health URL” | Separate the check contract from the exposure layer |
| “A timer only holds duration” | Inspect count, total time, and supported statistics |
| “An observation is always an exported span” | Check handlers, tracer, sampling, and data exporter |
| “One trace equals one span” | Inspect parent–child spans belonging to the same journey |
| “Counting error spans equals counting failed transactions” | Identify how many spans each transaction creates and how errors propagate |
| “Order IDs and trace IDs belong in metric tags” | Check cardinality and how many series combinations can be generated |
| “Having metrics means having long-term history” | Verify external collection and storage outside the process |

When moving to asynchronous execution, another boundary question arises. Wrapping only the call that submits work to an executor measures only what runs inside that wrapper; do not assume the lambda return time equals completion time of the entire background job. Connect the work lifecycle and its context properly.

Also avoid wrapping an activity already observed by the framework with a redundant measurement of the same meaning unless you have a clear goal. Overlapping measurements can cause readers to miscount executions or double-count duration.

## 12. Exercises to Test Your Mental Model

**Exercise 1 — Change the inventory condition after two successful runs.**

Let both checkout calls run while `stockReady=true`, and only then flip the flag to `false` before reading the indicator. Predict accepted orders, timer counts, and final health status.

Result to explain: you can have 2 accepted orders while current health is `DOWN`. Cumulative history and current evaluation describe different moments in time.

**Exercise 2 — Remove the tracing handler.**

Keep only the meter handler and rerun. Observe the timers and span list. With no tracing handler in the program linking observations to the tracer, the recorder’s span list receives nothing from those observations. Timers still record because the meter handler remains active.

This exercise checks why you must not equate an observation with a trace. It requires no changes to business logic.

**Exercise 3 — Remove the meter handler.**

Keep the tracing handler. The counter incremented directly by business code still exists; timers created by `DefaultMeterObservationHandler` will no longer be produced via that path. This distinguishes direct meter instrumentation from measurement through Observation.

**Exercise 4 — Interpret an error report.**

A single transaction creates 5 spans, 3 of which carry errors. What extra information is needed before reporting “3 transactions failed”?

You must identify how spans group into traces/transactions, parent–child relationships, and where the error originated. Span count is the number of recorded work units, not automatically the number of transactions.

When reading a system that uses Actuator, trace five questions: **Where is data exposed? What condition is checked? Which quantity is measured? Which lifecycle is observed? Which spans are linked into a journey?** Answering these helps you pick the right mechanism rather than just memorizing API names.
