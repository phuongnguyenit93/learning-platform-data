# High-cardinality key value in Micrometer Observation

> **Chapter:** Cardinality and metadata  
> **Lesson:** High-cardinality key value  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tag/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Opening scenario: from an error chart to a specific execution

Consider a Spring Boot service with an inventory reservation API `POST /api/reservations`. After deploying a new version, the error rate rises from 0.2% to 3% and p95 latency jumps from 150 ms to 900 ms. The metrics dashboard shows errors occurring across the service, but the on-call engineer wants to know **which reservation attempt** failed, which services that request passed through, and which step was slow.

We typically need two different levels of metadata:

- **Low-cardinality key–value** groups many requests along finite dimensions, such as `operation=reserve`, `channel=web`, `outcome=error`. This data is suitable for metric tags.
- **High-cardinality key–value** identifies a specific event or entity, such as `reservation.attempt_id=4d8b...`. The number of distinct values can be so large that every request carries its own value. This information is better suited for a span selected for investigation, when data policy permits.

In Micrometer Observation, the API is:

~~~java
observation.highCardinalityKeyValue("reservation.attempt_id", attemptId);
~~~

This call adds a key–value pair to the **observation context**. It does not directly emit metrics, logs, or traces. For the value to appear on a span, a tracing handler and tracing pipeline must be properly configured. If the trace is not sampled or not exported, you may not find this value in the backend even though the code attached it successfully.

**Lesson goal:** know when to use high-cardinality key–values, attach them properly to an Observation in Spring Boot, understand their effect and limits with metrics/traces/logs, and avoid mistakes that cause data explosion or expose sensitive information.

## 2. What is cardinality? Why does “high” not mean “important”?

**Cardinality** is the number of distinct values that can appear for a key in an observability dataset. For example:

| Example key–value | Scale of possible values | Typical classification | Purpose |
| --- | --- | --- | --- |
| `http.method=GET` or `POST` | A small group | Low | Slice metrics by method |
| `outcome=success/error/rejected` | 3 values | Low | Measure outcome rates |
| `region=ap-southeast-1` | A few allowed regions | Low | Compare deployment geography |
| `reservation.attempt_id=...` | Nearly one ID per attempt | High | Investigate an individual operation |
| `request.id=...` | Nearly one ID per request | High | Locate a specific event |
| `user.id=...` | Potentially millions of values | High | Consider only with clear purpose, authorization, and data protection policy |

Do not judge by **string length**. `outcome=success` is longer than many short codes, yet the values of `outcome` remain bounded. A 6-character string generated randomly per request can still produce millions of values.

### Cardinality for metrics

A time series in a system like Prometheus is typically identified by **metric name + label combination**. Suppose an HTTP metric has 4 methods, 10 route templates, 5 status groups, and 8 instances. If all combinations exist, there can be up to:

~~~text
4 method × 10 route × 5 status × 8 instance = 1,600 series
~~~

If you add `request.id` with 100,000 values, the *potential* number of combinations grows dramatically. Not every Cartesian product occurs in real data, but even nearly one new series per request is enough to drive up storage, memory, and query costs. Histograms also create multiple `_bucket` series for the same label set.

### Cardinality for traces

Traces typically record **each individual execution** using spans. A span can carry attributes specific to that single execution; therefore, a key with many values **does not automatically create new time series**. Even so, high-cardinality values still consume transmission/storage bandwidth, can bloat search indexes, and pose security risks. Add only the values needed for investigation, with controlled size and retention.

**High-cardinality** describes the number of distinct values, not that the data is more important than low-cardinality data. `outcome` usually has higher operational value than `request.id` for alerting, even though its cardinality is low.

## 3. Where does high-cardinality key value sit in the Observation architecture?

Micrometer Observation separates **instrumentation** from how data is exported. Application code creates an `Observation`, attaches metadata to `Observation.Context`, and then `ObservationHandler` instances react across its lifecycle.

~~~mermaid
flowchart TD
    A["ReservationService"] --> B["Observation: orders.reserve"]
    B --> C["Context"]
    C --> D["Low cardinality: operation, outcome, channel"]
    C --> E["High cardinality: reservation.attempt_id"]
    B --> F["ObservationRegistry + handlers"]
    F --> G["Meter ObservationHandler"]
    F --> H["Tracing ObservationHandler"]
    G --> I["MeterRegistry → metrics exporter"]
    H --> J["Tracer → sampler / tracing exporter"]
    D --> I
    D --> J
    E --> J
~~~

By standard usage:

1. `Observation.lowCardinalityKeyValue(k, v)` adds metadata with a finite value set, suitable for meter handlers to use as metric tags.
2. `Observation.highCardinalityKeyValue(k, v)` adds metadata that can distinguish individual operations, typically used by tracing handlers to place into span attributes.
3. `Observation.Context` holds key–values and lifecycle state; handlers receive the context on `onStart`, `onError`, `onStop`, etc.
4. `MeterRegistry` and the tracing exporter have independent paths; tracing sampling does not mean only sampled requests contribute to a Timer.

**Note:** this is the behavior of standard handlers. A custom handler can still read high-cardinality metadata and turn it into a metric label via custom code. The API itself cannot prevent that; developers must maintain proper data boundaries.

## 4. How to use the API in Java

### 4.1. Attaching a value

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValue("operation", "reserve")
    .highCardinalityKeyValue(
        "reservation.attempt_id", "demo-attempt-001")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    performReservation();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

In this illustrative code snippet:

- `operation=reserve` has a bounded value set and can be used to group metrics.
- `reservation.attempt_id=demo-attempt-001` is the ID of a **single attempt**, so it belongs in high-cardinality.
- `start()` and `stop()` open/close the observation lifecycle; `openScope()` makes the observation current in the associated execution context.
- `error(ex)` reports the error to handlers; it must not be replaced by merely attaching metadata `status=failed`.

Both keys are added **before `start()`** because we know them upfront. Key processing by tracing handlers can occur at different callbacks depending on the implementation; providing metadata early avoids depending on completion timing to place attributes on the span.

### 4.2. Attaching a value after obtaining a result

Not all information is available at the start. For example, a task ID returned by a storage system only appears after a successful write.

~~~java
Observation observation = Observation.createNotStarted(
        "inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("operation", "reserve")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    Reservation reservation = inventory.reserve();
    observation.highCardinalityKeyValue(
        "reservation.reference", reservation.reference());
    observation.lowCardinalityKeyValue("outcome", "success");
} catch (RuntimeException ex) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Here `Reservation` and `inventory` are hypothetical domain types. There is no requirement to put every returned ID into traces: evaluate **query usefulness, data access permissions, and value length** before adding `reservation.reference`.

Metadata added after `start` may be applied to the span by some tracing handlers during the stop phase; exact behavior depends on Micrometer/bridge/version. Therefore, when building mandatory features relying on a dynamic attribute, verify it on your tracer and exporter; **do not assume every backend displays attributes attached after the span ends**.

### 4.3. How to read metadata from Context

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

Observation.Context context = observation.getContext();

KeyValues low = context.getLowCardinalityKeyValues();
KeyValues high = context.getHighCardinalityKeyValues();
~~~

The two datasets are kept separate. Reading `high` in code does not automatically pass it to logs or metrics. If using a custom handler, extract only approved fields and avoid logging the entire context, since the context may hold business objects or sensitive data.

## 5. Spring Boot example: ID of a reservation attempt

We want to track the `inventory.reserve` operation. Each attempt is tagged with an **application-generated technical ID** that differs across executions, in order to link a span with a technical log line when needed. This ID contains no email, token, order contents, or user information.

### 5.1. Dependencies

With Spring Boot 3.x, the Actuator starter provides Micrometer Observation integration:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

To **export traces** to a backend, you need to add the tracing bridge and exporter matching your stack, such as Micrometer Tracing with OpenTelemetry and OTLP. Dependency names, properties, and support levels vary by Spring Boot version; `spring-boot-starter-actuator` alone does not guarantee that a trace will automatically be sent to a remote system.

### 5.2. Service recording low and high cardinality

~~~java
package example.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final ObservationRegistry registry;

    public InventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void reserve(String incomingChannel, Runnable action) {
        String channel = normalizeChannel(incomingChannel);
        String attemptId = UUID.randomUUID().toString();

        Observation observation = Observation.createNotStarted(
                "inventory.reserve", registry)
            .contextualName("reserve inventory")
            .lowCardinalityKeyValue("channel", channel)
            .highCardinalityKeyValue(
                "inventory.reservation_attempt_id", attemptId)
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            action.run();
            observation.lowCardinalityKeyValue(
                    "outcome", "success");
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue(
                    "outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("partner".equals(value)) return "partner";
        return "other";
    }
}
~~~

Each time `reserve(...)` is called:

1. `channel` is normalized to four values `web/mobile/partner/other`, ensuring low cardinality.
2. `attemptId` is generated from a `UUID`, so it is very likely a new value on every call. It is **high cardinality** and must not be placed into metric labels.
3. An `inventory.reserve` observation is created and started. If a Meter ObservationHandler is active, a business Timer can be recorded on stop.
4. If tracing is enabled and the span is sampled/exported, the tracing handler can attach `inventory.reservation_attempt_id` to the span.
5. `outcome` is added once the result is known. `error(ex)` notifies handlers of the error status, while `finally` ensures the observation stops.
6. `try-with-resources` closes the scope properly whether the action succeeds or fails.

The example uses `Runnable` to focus on observability rather than modeling a full inventory transaction. If the system has multiple exception types, retry mechanisms, or asynchronous processing, you must adapt outcome classification and observation lifecycle to match the semantics.

**Design note:** generating an extra `attemptId` is only useful when you need to cross-reference that ID against other technical data. If the existing trace ID already suffices for investigation, there is no need to create a redundant ID because every attribute increases data volume.

## 6. High cardinality does not mean metric tag

A serious mistake is accidentally routing individual IDs into the metrics system. Look at these two snippets:

~~~java
// Wrong for high-traffic metrics:
meterRegistry.counter(
        "inventory.reservations",
        "reservation_attempt_id", attemptId
).increment();

// Right when aggregating by a finite outcome:
meterRegistry.counter(
        "inventory.reservations",
        "outcome", "success"
).increment();
~~~

In the first example, a `Counter` can generate a new label combination on nearly every attempt, causing the backend to store a huge number of time series. Each series might hold only a single data point and never be used again, yet still incurs cost.

In the second example, `outcome` has only a finite set of values. Dashboards can compute successes/errors per minute using `rate()` or `increase()` without retaining each individual ID.

| Data location | Should attempt ID be included? | Explanation |
| --- | --- | --- |
| `Observation.highCardinalityKeyValue` | Conditionally | When the ID is non-sensitive, needed for investigation, and accepted by the tracing pipeline |
| Span attribute | Conditionally | Used to locate a sampled/exported attempt span |
| `Observation.lowCardinalityKeyValue` | No | Risks becoming a metric label |
| `MeterRegistry.counter(..., "attempt_id", ...)` | No | Every ID can create a new time series |
| Prometheus common tag or histogram tag | No | Multiplies series, bucket, and instance costs |
| Controlled technical log | Conditionally | When matching logging, retention, and access-control policies are in place |

**Control principle:** classify by **final consumer**, not solely by API name. If a custom handler converts high-cardinality key-values into metric tags, the problem still exists even though the high-cardinality API was called originally.

## 7. Distinguishing high-cardinality attribute, trace ID, and baggage

These concepts can appear together in a distributed tracing system, yet serve different purposes.

| Concept | Example | Who creates or propagates it? | Effect |
| --- | --- | --- | --- |
| **High-cardinality key–value** | `inventory.reservation_attempt_id=...` | Instrumentation code; tracing handler puts it on the span if supported | Adds detail to the span |
| **Trace ID / Span ID** | Identifier issued by the tracer | Tracing stack | Identifies the trace and span, links parent–child |
| **Trace context** | `traceparent` header, optionally `tracestate` depending on config | Propagator/instrumentation | Passes tracing relationships across service boundaries |
| **Baggage** | A business key that needs to travel with context to other services | Baggage mechanism and configured propagator | Propagates selected permitted context values between services |
| **Log correlation** | `traceId`, `spanId` in logs | Logging/tracing integration | Allows finding the corresponding trace from a log |

**A high-cardinality key–value set on an observation is not sent to downstream services by default.** A span attribute describes only that span. To send metadata to another service, you need the corresponding propagation/baggage API and configuration, or pass the value through the business contract. Putting an ID into baggage is a separate decision: it increases header sizes and can share data with multiple services or third parties.

Example of a request flowing through `order-api` → `inventory-api`:

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-api
    participant Inventory as inventory-api
    participant Collector as Tracing backend
    Client->>Order: POST /orders
    Note over Order: Observation has order.attempt_id = A1
    Order->>Inventory: HTTP + traceparent if propagation enabled
    Note over Inventory: Tracer continues trace context
    Inventory-->>Order: 200 OK
    Order-->>Client: Response
    Order-->>Collector: Export span with attribute A1 if sampled
    Inventory-->>Collector: Export child span if sampled
~~~

In the diagram, `inventory-api` can join the trace even though **it does not see `order.attempt_id=A1`**. If that service needs to know A1, define the business requirement and appropriate transport channel explicitly; do not assume span attributes propagate automatically.

Sometimes an investigative question is better answered by the trace ID in logs without adding business IDs to every span. Always evaluate existing signals before adding metadata.

## 8. When to attach values during the Observation lifecycle

An observation typically passes through these phases:

~~~mermaid
flowchart LR
    A["createNotStarted"] --> B["Attach known metadata"]
    B --> C["start"]
    C --> D["openScope"]
    D --> E["Execute work"]
    E --> F["Attach emerging metadata, event/error"]
    F --> G["closeScope"]
    G --> H["stop"]
    H --> I["Handlers finish / exporter processes"]
~~~

| Timing | Information typically available | Notes |
| --- | --- | --- |
| Before `start()` | Operation name, channel, generated attempt ID | Suitable when you want the tracing handler to read attributes right at the start |
| After `start()`, before `stop()` | Downstream-returned ID, outcome, failed step category | Handlers may read data at the end phase; verify per implementation |
| After `error(ex)` | Error info reported to the observation | Does not automatically turn every exception detail into attributes |
| After `stop()` | Observation has completed | Do not rely on late key attachment to modify an already-exported span |
| When switching threads | Scope/current observation context may change | Requires proper context propagation with executors/Reactor |

Callback order **is not determined by key name**. A metrics handler and a tracing handler may consume metadata at different times. Do not build business logic on the assumption that adding a key anywhere will “instantly update every backend.”

When instrumenting manually, use `try-with-resources` for the scope and `finally` for `stop()`. If an operation returns a `CompletableFuture`, do not stop immediately after submitting, because the work may not be finished; end the observation when the result actually arrives and propagate context using the framework's mechanism.

## 9. Security and privacy: high cardinality does not mean permission to record anything

High-cardinality fields often contain identifiers; that is why you must evaluate **content** and **access control**, not just data volume.

**Values that should not be put directly into span attributes or logs:** passwords, access tokens, API keys, session cookies, payment card numbers, authorization strings, sensitive user information, request/response bodies containing private data, SQL containing sensitive data, or full URLs with query parameters.

For `user.id`, `customer.email`, `order.id`, `device.id`, and other identifiers, whether they are allowed depends on data classification, investigative purpose, legal regulations, and organizational policy. **Do not treat tracing as an unbounded data store.** Necessary values can be pseudonymized, truncated, appropriately encrypted/hashed, or replaced by an opaque correlation ID; ensure the approach stays compatible with real query requirements.

Example design following data minimization:

~~~java
// New technical ID containing no personal information:
String attemptId = UUID.randomUUID().toString();

observation.highCardinalityKeyValue(
        "inventory.reservation_attempt_id", attemptId);

// Do not put authentication data into an observation:
// observation.highCardinalityKeyValue("auth.token", bearerToken);
~~~

In production, establish consistent rules:

1. **Allowlist keys:** only specific keys are permitted for export; do not attach arbitrary attributes from HTTP headers.
2. **Size limits:** control value length and format; avoid attaching payloads or long stack traces.
3. **Access scope:** the tracing backend has appropriate access controls, retention, and audit policies.
4. **Sampling and cost:** determine volume, sampling rate, attributes per span, and storage policy.
5. **Data lifecycle:** know how to delete/redact information when required by organizational procedures.

Hashing data does not automatically render it harmless: a stable hash value can still serve as a user identifier and still has high cardinality.

## 10. Combining metrics, logs, and traces to investigate an incident

Suppose 3% of reservation requests time out. We do not need to put `reservation.attempt_id` into a metric label to find individual failed requests.

**Step 1 — detect via metrics.** The `inventory.reserve` Timer has low-cardinality tags such as `outcome=error` and `channel=mobile`. The dashboard shows when errors spiked and which channel is affected.

**Step 2 — pick a trace.** Based on timestamp, service, operation, and duration, pick a sampled trace in the backend. The span contains the high-cardinality `inventory.reservation_attempt_id` if the pipeline recorded/retained the attribute.

**Step 3 — find related logs.** Use `traceId/spanId` if log correlation is configured; you can use the attempt ID in technical logs if policy permits and the log recorded that value. Simply adding a high-cardinality key to an Observation **does not automatically write a log line**.

**Step 4 — analyze the call path.** Inspect HTTP client, database, or queue spans to pinpoint the slow step. Trace context must be propagated between services so spans have parent–child relationships.

**Step 5 — verify with metrics.** After fixing, verify that p95 latency, error rate, and throughput recover over a sufficiently long window. A single trace only provides evidence for one execution flow; metrics show system-wide impact.

~~~mermaid
flowchart TD
    A["Metrics: error rate & p95 spike"] --> B["Narrow down by low-cardinality tags"]
    B --> C["Select a sampled trace"]
    C --> D["Span high-cardinality attributes"]
    C --> E["Logs by traceId/spanId"]
    D --> F["Analyze downstream/DB"]
    E --> F
    F --> G["Fix and re-verify metrics"]
~~~

**Exemplars** are a separate mechanism that can link a metric sample to a trace ID when supported by the registry/exporter/backend. This is a way to bridge metrics and tracing without turning request IDs into metric labels. Not every version or backend enables exemplars by default.

## 11. Sampling, exporters, and context propagation: why is a high-cardinality attribute missing?

Attaching a key to an Observation is just **one stage** of the pipeline:

~~~text
Instrumented code
  -> Observation.Context (high-cardinality key)
  -> tracing ObservationHandler
  -> Tracer/Span
  -> Sampling decision
  -> Reporter/Exporter
  -> Collector/Tracing backend
  -> Index/search/UI
~~~

Common situations:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Attribute is in context but not on span | Handler does not process high keys, added after span ended, bridge/version differs from expectation | Check the active tracer/span being created and attachment timing |
| Span exists in app but trace not found in backend | Sampler did not select trace; exporter/collector failed | Check sampling, exporter, and collector configuration |
| Only some requests have the attribute | Metadata only exists on certain code paths or instances | Compare code branches and running versions |
| Spans do not link properly across two services | Missing propagation for HTTP/messaging or context lost on thread switch | Check trace headers and client/server instrumentation |
| Metadata does not appear in logs | No logging correlation mechanism or code did not log the field | Check `traceId/spanId` and separate logging configuration |
| Metric lacks the high key | Usually intended behavior of the meter handler | Check low-cardinality tags instead of putting IDs in metrics |
| Trace overloaded or attributes truncated | Too many attributes, values too long, or SDK/backend limits | Check attribute count/value limits and cost |

**Do not conclude “Observation didn't run” solely from a missing trace.** A Timer can record every request while tracing is sampled. Some spans may also be dropped due to tail sampling or collector/backend retention policies.

Conversely, **do not raise sampling to 100% in production just to find one attribute** without assessing cost. You can reproduce the bug in a test environment or use controlled sampling/diagnostics.

## 12. Verifying key-values without depending on an exporter

In a learning example, you can register a simple handler on a standalone `ObservationRegistry` and verify that the context contains the expected low/high key-values. This helps separate issues in **instrumentation code** from issues in the **tracing pipeline**.

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicReference;

public final class MetadataDemo {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();

        AtomicReference<KeyValues> capturedHigh =
                new AtomicReference<>();

        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(
                            Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStop(
                            Observation.Context context) {
                        capturedHigh.set(
                                context.getHighCardinalityKeyValues());
                    }
                }
        );

        Observation.createNotStarted("demo.reserve", registry)
                .lowCardinalityKeyValue("outcome", "success")
                .highCardinalityKeyValue(
                        "reservation.attempt_id", "demo-123")
                .observe(() -> {
                    // Simulated work
                });

        if (capturedHigh.get() == null) {
            throw new IllegalStateException(
                    "High-cardinality context was not captured");
        }

        System.out.println(capturedHigh.get());
    }
}
~~~

Expected result: the handler receives `onStop` and reads `reservation.attempt_id=demo-123` in the high-cardinality metadata set. This tests **context and callbacks**; it does not prove a span was created or that the attribute was sent to a collector.

In a real Spring Boot application, use the `ObservationRegistry` provided by the framework. Creating a new registry inside a service just for testing can detach observations from the active meter/tracing handlers, causing confusion about data export.

### Checking with Actuator and the tracing backend

When Actuator and an appropriate metrics registry are present:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/inventory.reserve
~~~

For the `inventory.reserve` metric, you can see low-cardinality `channel` and `outcome` (depending on instrumentation/handler). **Do not look for `reservation.attempt_id` in `availableTags` as a success criterion.** To inspect high attributes, open a sampled trace in the backend and locate the `inventory.reserve` span.

If the metrics endpoint lacks the meter, check the Meter ObservationHandler and ensure the observation called `stop()`; if the tracing backend lacks the span, check the tracing bridge, sampling, exporter, and propagation before concluding the bug is in the high-cardinality API.

## 13. Naming conventions and metadata limits

Key names should convey the stable meaning of an attribute and be easy to distinguish from metric labels. For example:

| Suggested name | Meaning | Notes |
| --- | --- | --- |
| `inventory.reservation_attempt_id` | Technical ID of the reservation attempt | High; control retention |
| `orders.operation` | Business operation group | Low when values are finite |
| `orders.outcome` | Logical result: success/rejected/error | Low |
| `messaging.message_id` | Individual message ID | High; evaluate sensitive data |
| `http.route` | Route template, containing no real IDs | Low |
| `http.target` with arbitrary query string | May expose data and have many values | Avoid passing verbatim into tags |

Before adding a high-cardinality key, answer:

1. **Which investigative question requires this key?** If the trace ID already solves it, do not add it.
2. **Which spans will this key appear on?** Avoid attaching it to every span if it is only meaningful for a specific business step.
3. **Is the value sensitive?** If yes, a data/control policy or an alternative ID is required.
4. **How long is the value?** Structure and length can be constrained right at the source.
5. **How many traces are retained?** Estimate cost based on traffic, sampling, and retention.
6. **Could anyone accidentally put this key into metrics?** Review custom meters and conventions.

When every key is added ad hoc from exceptions or request headers, an application can produce unmanageable span attributes. Maintain a shared metadata catalog for the service while allowing intentional extensions for specific business cases.

## 14. Hands-on lab: investigating a failure with high-cardinality key value

**Scenario:** the `booking-service` application handles booking creation. You have a business Timer `bookings.create` and working tracing. The goal is to identify which request failed without increasing metric cardinality.

**Task A — design metadata**

Choose:

- Low cardinality: `channel=web/mobile`, `outcome=success/rejected/error`.
- High cardinality: `booking.attempt_id`, a non-sensitive technical ID that changes per attempt.
- Do not use `booking.attempt_id` as a label on a Timer or Counter.

Suppose there are 2 channels, 3 outcome states, and 6 instances; calculate the maximum number of tag combinations for each measurement along these three dimensions: **2 × 3 × 6 = 36**. If you add an attempt ID across 50,000 invocations, estimate why each attempt could generate a new combination, causing series cost to scale with traffic.

**Task B — instrument code**

Write a service using `ObservationRegistry`, create `Observation.createNotStarted("bookings.create", registry)`, and attach `booking.attempt_id` via `highCardinalityKeyValue(...)`. Use `try-with-resources` for the scope, `observation.error(ex)` on error, and `finally` for `stop()`.

**Task C — verify**

Run several successful and failing requests in a test environment:

1. Inspect the `bookings.create` Timer via Actuator and verify only the expected low-cardinality tags are present.
2. Open a trace containing the booking span; find `booking.attempt_id` in span attributes if the trace was sampled and the exporter kept the attribute.
3. From a log containing the trace ID, look up the trace; identify HTTP client/database steps causing slowness or errors.
4. Disable the tracing exporter in the test environment and observe: Observation still holds context metadata, but the backend receives no traces; metrics can continue to be recorded independently.
5. Explain why high-cardinality attributes do not appear by default on spans of other services.

**Self-check questions:**

1. Is high-cardinality defined by string length or by the number of distinct values?
2. Why is `request.id` unsuitable as a metric label even though it is useful in tracing?
3. Does `highCardinalityKeyValue(...)` automatically propagate the value over HTTP headers?
4. If a high attribute exists in context but is missing on the tracing UI, which steps should you check?
5. How does sampling affect the number of traces versus the number of Timer recordings?
6. Why must security still be enforced even when a value is attached under the “high” group?
7. How do Trace ID, baggage, and high-cardinality span attributes differ in purpose and propagation?
8. What consequences can arise if a custom handler feeds high keys into `MeterRegistry`?

**Completion criteria:** able to explain high-cardinality and its costs; use the Micrometer Observation API correctly; distinguish low/high/context/trace ID/baggage; trace the path from Observation to span; avoid putting IDs into metrics; and account for security, sampling, exporters, and propagation.

## Key takeaways

- `highCardinalityKeyValue(key, value)` stores metadata that may have very many values into `Observation.Context`; tracing handlers can turn them into **span attributes**, depending on the pipeline and sampling.
- **Do not use per-request or per-entity IDs as metric tags.** Metrics serve aggregation along low-cardinality dimensions, whereas tracing serves analysis of individual execution paths.
- High-cardinality key–values are **not** trace IDs or baggage and **are not automatically propagated** to other services.
- Tracing only yields searchable results when the bridge, handler, sampler, exporter, and backend are compatibly configured; log correlation also has its own configuration path.
- Record metadata only for clear needs, avoid sensitive data, bound values, and enforce appropriate retention/access controls.
- When investigating incidents: use metrics to spot trends, traces to pinpoint slow steps, logs to supply events, and verify improvements back on metrics.

## References

- [Micrometer — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
