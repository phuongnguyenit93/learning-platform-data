# GlobalObservationConvention: Configuring Shared Conventions in ObservationRegistry

When building Spring Boot applications, many operations can be tracked with **Micrometer Observation**: receiving HTTP requests, calling other services, querying databases, and running business logic. Each Observation has a name and key-values used for aggregating **metrics** or as attributes on **distributed tracing**. If every call site chooses its own naming and tags independently, the operations team struggles to compare latency, correlate signals, and maintain dashboards.

`GlobalObservationConvention` lets an application define **shared naming and key-value rules at the `ObservationRegistry` level for matching `Observation.Context` types**. With Spring Boot, you can register this convention as a bean or configure it directly on the registry depending on how the application is initialized. This lesson explains the convention selection mechanism, safe usage, known limitations, and how to verify results when exporting metrics, logs, and traces.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish `GlobalObservationConvention`, `ObservationConvention`, `ObservationFilter`, and other `ObservationRegistry` components.
2. Explain when a global convention is selected and how it interacts with custom/default conventions.
3. Write a global convention with an explicit `supportsContext`, stable names, and controlled key-values.
4. Register a global convention in Spring Boot or on a standalone `ObservationRegistry`.
5. Analyze how conventions affect metric labels, span attributes, cardinality, sampling, and context propagation.
6. Test runtime values, diagnose why a global convention does not take effect, and manage telemetry contract changes.

## 1. What Is ObservationConvention?

An `Observation` represents **a single execution** of an observable activity, such as a request to reserve inventory. While running, the observation carries an `Observation.Context` holding data about that activity. `ObservationConvention<T>` is the contract defining how to derive names and `KeyValues` from a context of type `T`.

A convention can provide:

| Member | Question Answered | Example |
| --- | --- | --- |
| `getName()` | What is the stable technical name of the observation? | `inventory.reserve` |
| `getContextualName(context)` | How should the activity be phrased in a trace? | `reserve inventory` |
| `getLowCardinalityKeyValues(context)` | Which bounded values are suitable for aggregating metrics? | `inventory.channel=web` |
| `getHighCardinalityKeyValues(context)` | Which high-cardinality attributes help investigate individual traces? | `inventory.attempt.id=...` |
| `supportsContext(context)` | Does this convention understand the context being processed? | `context instanceof InventoryReserveContext` |

**GlobalObservationConvention** is a variant of `ObservationConvention` registered on the registry so it can be selected **across multiple Observation creation sites** when the context matches. The word "global" describes **registration scope**, not that every observation in the application must share the same name and tags.

A global convention for HTTP server requests does not necessarily apply to business observations; a global convention that only supports `InventoryReserveContext` will not apply to JDBC, Kafka, or HTTP server contexts.

### 1.1. General Mechanism

~~~mermaid
flowchart TB
    Factory["Instrumentation code creates Observation with Context and conventions"] --> Selection{"Select convention"}
    Custom["Custom convention at call site"] --> Selection
    Global["GlobalObservationConvention in registry"] --> Selection
    Default["Instrumentation's default convention"] --> Selection
    Selection --> Obs["Observation: start / scope / event / error / stop"]
    Obs --> Registry["ObservationRegistry and ObservationHandler"]
    Registry --> Meter["Metrics: name and low-cardinality tags"]
    Registry --> Span["Traces: spans and attributes"]
    App["Application logger + correlation context"] --> Log["Logs"]
    Span -. "trace ID / span ID" .-> Log
~~~

Here, **custom**, **global**, and **default** are the rule sources evaluated when an Observation is created via a convention-aware API. Once selected, handlers in the registry process the lifecycle and may produce metrics or spans. Logs are typically emitted separately and linked via trace/span ID when tracing is configured.

## 2. When Is GlobalObservationConvention Selected?

When instrumentation creates an Observation through a factory accepting a **custom convention**, **default convention**, **context supplier**, and **registry**, the typical precedence order is:

1. **Custom convention** passed directly: highest priority.
2. **Global convention** registered on the registry that reports supporting the context: considered if no custom convention is supplied.
3. **Default convention** passed by instrumentation: used when neither of the above applies.

If no matching convention exists, behavior depends on the specific factory and instrumentation. Always supply a valid default convention for custom business instrumentation.

| Situation | Expected Convention |
| --- | --- |
| Custom convention passed directly | Custom |
| Custom is `null`, global supports the context | Global |
| Custom is `null`, no matching global | Default |
| Global only supports another context | That global is not selected |
| Called `Observation.createNotStarted("fixed.name", registry)` directly with a name | Do not assume global will override the name; this creation path differs from the convention-selecting factory |

That last point is easily misunderstood: **declaring a `GlobalObservationConvention` bean does not guarantee every Observation in the application goes through it**. Instrumentation must use the corresponding context-aware convention API. For HTTP, client, or framework integrations, check which convention API they use to create Observations and whether a specific custom convention takes precedence.

### 2.1. Distinguishing Global Convention and ObservationFilter

These two mechanisms solve different needs:

- **GlobalObservationConvention**: selects *the name and set of KeyValues based on a context type* when building an Observation. It fits when you want to change the contract for a group of operations, such as all inventory reservations sharing `inventory.channel`.
- **ObservationFilter**: intercepts `Observation.Context` during the lifecycle to add/modify data according to policy. It is commonly used to add shared key-values (such as deployment environment) and requires understanding when it runs.
- **ObservationPredicate**: decides whether an Observation should be recorded or become a no-op, such as skipping an unneeded flow.
- **ObservationHandler**: receives lifecycle callbacks and creates actual signals such as metrics or traces.

If the goal is simply tagging **all metrics** with application/environment labels, `MeterRegistry` common tags may fit better. If the goal is attaching an attribute to **all spans**, inspect the corresponding tracing/handler mechanism. Do not misuse a global convention to force the same name or key set onto unrelated contexts.

## 3. Designing an Example for Spring Boot

Suppose `order-service` calls `inventory-service` to reserve stock. There are two callers: `web` from the API and `batch` from a job. We need to observe:

- Reservation count, execution duration, and error rate by caller source.
- Duration of the `inventory-service` call step inside a trace.
- Ability to look up logs for the operation by trace ID when timeouts occur.

Expected telemetry contract:

| Field | Value | Reason |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Stable across call sites |
| Contextual name | `reserve inventory` | Readable in traces |
| Low-cardinality `inventory.channel` | `web`, `batch` | Bounded, suitable for aggregation |
| Low-cardinality `inventory.operation` | `reserve` | Operation name |
| High-cardinality `inventory.attempt.id` | Anonymized attempt identifier | Used to correlate individual calls when needed |

**Do not put** order IDs, user IDs, raw URLs, exception messages, or access tokens into metric labels. High-cardinality attributes must also obey security policies because they can be shipped to the trace backend.

### 3.1. Strongly Typed Context

By declaring a dedicated context, `supportsContext` can accurately identify which Observations a global convention is allowed to handle.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

public final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    public InventoryReserveContext(String channel, String attemptId) {
        // In a real app, normalize/validate channel at the input boundary.
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        this.channel = channel;
        this.attemptId = attemptId;
    }

    public String channel() {
        return channel;
    }

    public String attemptId() {
        return attemptId;
    }
}
~~~

The context only carries data for that invocation; these fields do not automatically become tags. The convention decides which fields are exposed, at which cardinality level, and under what names.

### 3.2. Fallback Default Convention

A default convention ensures business instrumentation keeps a stable contract even when no global convention is registered. In this example, the default shares the same name as global but only publishes two low-cardinality keys.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class DefaultInventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }
}
~~~

Here all code uses the `inventory.reserve` name and a well-defined key set. When slicing by `inventory.operation` is unnecessary, that key can be removed from **both the contract and queries**, since the metric name already identifies the operation; the choice should be driven by operational needs.

## 4. Writing GlobalObservationConvention

We create a global convention that **only supports `InventoryReserveContext`**. Beyond the existing low-cardinality keys, the example also publishes the attempt identifier at high cardinality.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;

public final class GlobalInventoryReserveConvention
        implements GlobalObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

Design decisions to note:

1. **Never return `true` unconditionally from `supportsContext`** unless you intentionally design a convention applicable to every context type. A convention casting to `InventoryReserveContext` must check the type first.
2. **Fixed technical name.** Avoid embedding SKUs, order IDs, or exception messages into `getName()`.
3. **Bounded low-cardinality values.** The context already constrains `channel`; `operation` has only one value in the example.
4. **Separate high cardinality from metrics.** `attemptId` is for analyzing a single call's trace, not a label for aggregating across requests.
5. **Do not assume every handler uses every key.** Which keys end up on metrics/spans depends on handlers and exporters; verify in the real backend.

In practice, `attemptId` might be blank or absent in some flows. When implementing, establish a normalization rule or omit invalid keys rather than passing `null` into `KeyValue.of`. To keep the example readable, this code assumes valid, non-secret inputs.

## 5. Registering the Convention on ObservationRegistry

There are two common ways. **Choose the one matching where the registry is created**, avoiding unnecessary double registration of the same instance.

### 5.1. Spring Boot: Declaring a Bean

In Spring Boot 3.x with observation auto-configuration, beans of type `GlobalObservationConvention` are picked up to configure the Boot-managed `ObservationRegistry`.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.GlobalObservationConvention;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationConfiguration {

    @Bean
    GlobalObservationConvention<?> inventoryReserveGlobalConvention() {
        return new GlobalInventoryReserveConvention();
    }
}
~~~

Do not create an extra `ObservationRegistry` with `ObservationRegistry.create()` inside a service, because that creates an isolated registry lacking the handlers/filters configured by Spring Boot. Inject the application-managed `ObservationRegistry` bean.

If the project creates its own registry or disables auto-configuration, verify how convention beans are wired into the registry actually in use.

### 5.2. Plain Java or Self-Managed Registry

If not using Spring Boot auto-configuration, you can register the convention directly:

~~~java
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationConvention(new GlobalInventoryReserveConvention());
~~~

This is only the **convention selection** part. A newly created registry does not automatically have metrics/tracing handlers, so you cannot assume Prometheus, an OTLP Collector, or a trace backend will receive data. You must register handlers, registries/exporters, and configure the pipeline for your system.

### 5.3. Using It Across Multiple Observation Creation Sites

Create the Observation using the overload accepting custom/default conventions and a context supplier:

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {
    private final ObservationRegistry registry;
    private final InventoryGateway gateway;

    public InventoryReservationService(ObservationRegistry registry,
                                       InventoryGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void reserve(String sku, int quantity, String channel, String attemptId) {
        Observation.createNotStarted(
                null, // Do not pass a custom convention.
                new DefaultInventoryReserveConvention(),
                () -> new InventoryReserveContext(channel, attemptId),
                registry)
            .observe(() -> gateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

With the global convention bean registered and `supportsContext` returning `true`, this call selects the global convention. If the global bean is removed, the call falls back to the default convention. If a custom convention is passed instead of `null`, custom takes precedence over global.

When the lambda runs, `observe(...)` manages start, scope, stop, and error recording if the lambda throws an exception. If the gateway makes an HTTP API call, an instrumented client is needed to produce a child span and propagate trace context to `inventory-service`.

**Scope of the example:** public classes should live in their own Java files following Java naming rules; `InventoryGateway` is an application interface to be implemented. This service code demonstrates convention selection and does not replace retry, timeout, validation, or business error handling.

## 6. Custom Convention, Global Convention, and Default Convention by Scenario

Suppose the stock-reservation service is called from HTTP and from a batch job. Initially it uses `DefaultInventoryReserveConvention`. Later the team wants to unify observation across callers application-wide.

| Context | Declaration | Expected Outcome |
| --- | --- | --- |
| Global not registered | `custom=null`, default passed | Uses `DefaultInventoryReserveConvention` |
| Global registered with matching `supportsContext` | `custom=null`, default passed | Uses `GlobalInventoryReserveConvention` |
| Custom passed at one call site | `custom` non-null | Uses custom, does not select global |
| Observation uses a different `Observation.Context` type | Global only supports `InventoryReserveContext` | Global does not apply; uses convention matching that context |
| Observation created with name-only API | No custom/default convention supplied | Do not assume global is consulted |

Example of a custom convention at a call site:

~~~java
// Illustrates precedence only; custom implementation must be
// defined separately and support InventoryReserveContext.
Observation.createNotStarted(
        new CustomInventoryReserveConvention(),
        new DefaultInventoryReserveConvention(),
        () -> new InventoryReserveContext("web", "attempt-42"),
        registry)
    .observe(() -> gateway.reserve("SKU-DEMO", 1));
~~~

Do not define multiple global conventions whose `supportsContext` matches the same context type and then rely on bean order or registry list order to "guess" which wins. The safe approach is to **keep supported scopes cleanly separated** and verify the contract in startup tests.

### 6.1. Global Does Not Mean Changing All HTTP Telemetry

Spring MVC, WebFlux, and HTTP clients have their own conventions for names/tags such as route, method, status, and outcome. A specialized custom convention may be configured on that instrumentation and take high precedence. If the goal is to adjust HTTP metrics/tags, check the corresponding specialized convention interface first rather than registering a global convention that casts arbitrary contexts to a custom type.

For example, putting the raw path `/orders/123` into a URI tag creates high cardinality. For HTTP servers, instrumentation typically uses route templates like `/orders/{id}` when mapping info is available; preserve that normalization rule when customizing.

## 7. Effects on Metrics, Traces, and Logs

Spring Boot can configure the integrations:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Only when shipping distributed traces via OpenTelemetry:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Used for Observation testing:
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

With the example convention, we expect:

| Signal | What Can Be Observed | Prerequisites |
| --- | --- | --- |
| **Metrics** | Timer/counts and duration of `inventory.reserve`, grouped by `inventory.channel` | Metrics handler, `MeterRegistry`, matching exporter/scrape |
| **Traces** | `reserve inventory` span inside the request trace, with relevant attributes | Tracing handler, propagation, sampling, and matching exporter |
| **Logs** | Error/timeout logs carry trace ID and span ID to locate the trace | Logging configured for correlation and active trace context |

Prometheus series names may be transformed from Observation names, e.g. a timer measured in seconds yields `_seconds_count` or `_seconds_sum` series; inspect actual names at `/actuator/prometheus` and in the backend before writing dashboard queries.

**GlobalObservationConvention is not responsible for shipping data.** Metrics depend on the registry; traces depend on the bridge, sampler, exporter, and Collector; logs depend on the logging system. If tracing samples at 10%, you cannot expect 100% of traces to be stored, even though metrics can still aggregate across all instrumented paths.

### 7.1. Propagation Across Services and Threads

If `order-service` calls `inventory-service`, the HTTP client must propagate W3C Trace Context (typically the `traceparent` header) so both spans belong to the same trace. Use HTTP clients instrumented through Spring-managed builders and verify on both sides in practice.

When processing asynchronously via `@Async`, executors, Reactor, or messaging, appropriate propagation mechanisms are needed. Registering a global convention only decides names and tags; **it does not automatically transfer trace IDs across threads or processes**.

Investigation flow:

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Otlp as Collector / backend
    User->>Order: POST /orders
    Note over Order: HTTP request Observation
    Order->>Order: inventory.reserve (global convention)
    Order->>Inventory: reserve + traceparent
    Inventory-->>Order: timeout
    Note over Order: Metrics record duration; log has trace ID
    Order-->>User: HTTP 503
    Order-->>Otlp: Spans if kept by sampling
    Inventory-->>Otlp: Receiver-side span, if present
~~~

When errors happen, use metrics to gauge scope and trend, traces to pinpoint which step was slow, and logs to inspect timeout details and error codes. A single trace represents only that request and does not by itself prove system-wide behavior across all traffic.

## 8. Controlling Cardinality and Security

For each tag value, the metrics system may create a new time series combination. If `inventory.channel` has 2 values, `inventory.region` has 4, `outcome` has 3, and the application runs 80 instances, a single metric name can produce up to **2 × 4 × 3 × 80 = 1,920** series combinations before counting other labels.

| Tag | Level | Decision |
| --- | --- | --- |
| `inventory.channel=web/batch` | Low | Use if comparing caller sources is needed |
| `inventory.operation=reserve` | Low | Use when there is a clear reason |
| `inventory.region=apac/eu/...` | Low if list is bounded | Monitor number of distinct values |
| `inventory.attempt.id=attempt-...` | High | Do not put in metric labels; consider traces |
| `inventory.order.id` | High | Avoid in metric labels; assess data risk |
| `exception.message` | High, unstable | Do not put in labels or span attributes by default |

Do not let the word "global" tempt you into attaching all data to every Observation. Only expose attributes the operations team genuinely needs to query, and only when the data is cleared for collection. Restrict personal data and secrets across low/high-cardinality tags, traces, and logs.

Rules to apply in code review:

- Stable Observation names containing no per-request data.
- Low-cardinality tags have a small, standardized, operationally meaningful value set.
- High-cardinality tags are used only when correlation is needed; no tokens, emails, payloads, or sensitive info.
- Defined conventions for naming, schema changes, and data retention policies.
- Awareness of the time series growth added by any new low-cardinality key.

## 9. Testing GlobalObservationConvention

`TestObservationRegistry` from `micrometer-observation-test` lets you verify that Observations were created and stopped with the expected names/tags. A test suite should verify **both global convention selection and fallback**.

JUnit 5 and AssertJ example:

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalInventoryReserveConventionTest {

    @Test
    void usesGlobalConventionWhenContextIsSupported() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        registry.observationConfig()
                .observationConvention(new GlobalInventoryReserveConvention());

        Observation.createNotStarted(
                null,
                new DefaultInventoryReserveConvention(),
                () -> new InventoryReserveContext("web", "attempt-demo"),
                registry)
            .observe(() -> { /* executed successfully */ });

        assertThat(registry)
            .hasSingleObservationThat()
            .hasBeenStopped()
            .hasNameEqualTo("inventory.reserve")
            .hasLowCardinalityKeyValue("inventory.channel", "web")
            .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-demo")
            .doesNotHaveError();
    }
}
~~~

In the example, **the default convention does not produce the high-cardinality key**, whereas global does. Thus the presence of `inventory.attempt.id` in the test proves global was selected. This test does not prove a span reached a backend; it only verifies Observation runtime behavior and convention selection.

Additional cases worth testing:

1. **Without global registered:** Observation still gets name `inventory.reserve` and low-cardinality keys from the default convention, without `inventory.attempt.id`.
2. **Unsupported context:** another Observation does not mistakenly get `inventory.*` tags attached.
3. **Custom convention passed directly:** custom is chosen over global.
4. **Exception thrown inside lambda:** Observation records the error and stops; assert using the test API for your Micrometer version.
5. **Spring Boot context test:** the global bean actually sits inside the application-managed registry; no accidentally created standalone registry exists.
6. **Integration test:** exporter/backend receives metrics/traces as expected, while high-cardinality tags do not appear as metric labels.

When upgrading Micrometer/Spring Boot, re-run convention selection tests, since overloads, auto-configuration, and metric/exporter representations can change across versions.

## 10. Failure Modes and Investigation

### 10.1. Bean Declared, but Global Convention Is Never Called

Check step by step:

1. Was the bean scanned and created by Spring? Is the configuration class within component scan scope?
2. Is the service using the Spring-managed `ObservationRegistry`, or did it create its own registry?
3. Does the instrumentation use a factory taking a context and conventions, or is it calling the name-only Observation creation API?
4. Is a **custom convention** being passed directly and taking precedence over global?
5. Does `supportsContext(context)` return `true` for the exact runtime context type?
6. Are multiple global conventions supporting that same context? If so, eliminate overlapping scopes.

If metrics still do not show up in the backend after confirming global is selected, continue inspecting handlers, the metrics registry, endpoints, and exporters. Convention selection errors and data export errors are two separate issues.

### 10.2. Metrics Have the Right Name, but Wrong or Missing Tags

Compare the context fields against the values returned by `getLowCardinalityKeyValues`. Check whether inputs were normalized and whether handlers ran through the full lifecycle. Extra tags added by filters, handlers, or other instrumentations can also appear on live data; inspect the entire pipeline before concluding the convention is wrong.

### 10.3. Metrics Exist, but No Traces Appear

Check the tracing bridge, sampling probability, context propagation across HTTP clients/threads, OTLP exporter address, Collector, and backend. Sampling can drop traces without changing Observation behavior in tests or metrics. Seeing a trace ID in logs does not guarantee the trace was stored in the tracing system.

### 10.4. After a Release, Dashboards Stop Showing Data

Check whether `getName()`, low-cardinality keys, tag values, metric name exposition, or exporter configuration changed. Renaming `inventory.channel` to `source` requires coordination with operations and updating queries/alerts; if needed, run a transition period supporting both old and new schemas.

## 11. Design and Operations Checklist

| Item to Verify | Evidence |
| --- | --- |
| Accurate scope of application | `supportsContext` narrows down to the exact context type |
| Default exists when needed | Custom instrumentation does not depend solely on global registry |
| No precedence conflicts | Tested custom > global > default per instrumentation API used |
| Stable metric/span names | Names agreed upon and dashboards/alerts updated |
| Safe low-cardinality tags | Bounded value set and estimated series count |
| Safe high-cardinality tags | No secrets or personal data |
| Consistently managed registry | Spring bean or manual setup, no unintended standalone registries |
| Metrics and traces actually exported | Verified at destination systems, including exporter failure cases |
| Logs and traces can correlate | Trace/span IDs present when context is active |
| Clear sampling/retention policy | Known limits on trace lookup and storage cost |

## 12. Practice Exercise

**Scenario:** `order-service` has two paths invoking stock reservation: the `POST /orders` API and a batch job. Slow request rates increased after a recent deployment. You need to measure the duration of the reservation step, break it down by caller source, and connect metrics, logs, and traces.

**Tasks:**

1. Create `InventoryReserveContext` and the two conventions as shown, ensuring `supportsContext` applies only to the reservation context.
2. Declare a `GlobalObservationConvention<?>` bean in Spring Boot and inject `ObservationRegistry` into the service.
3. Invoke the reservation operation from both `web` and `batch` sources, triggering both success and simulated timeouts.
4. Write tests proving the high-cardinality key appears when the global convention is present, and the default convention is chosen when global is absent.
5. Inspect metrics at the endpoint/backend and open a trace for a slow reservation if kept by sampling.
6. Try passing a custom convention at one call site; observe precedence and its impact on names/tags.
7. Simulate losing traces due to sampling or exporter failure and show that the issue can still be detected via metrics/logs.
8. Propose a latency dashboard/alert and describe how to investigate when only the `batch` source becomes slow.

**Expected deliverables:** code for context/conventions/service, tests verifying convention selection order, metrics/tracing outputs, and timeout investigation notes. If a tracing backend is unavailable, clearly note what evidence can be verified at runtime and the limits of those conclusions.

## 13. Summary

`GlobalObservationConvention` lets you register naming and key-value rules at the `ObservationRegistry` level for **context types supported by the convention**. It is useful when multiple instrumentation points need a unified contract, while still respecting custom/global/default convention precedence. In Spring Boot, declare it as a bean to participate in auto-configuration; with a self-managed registry, register it directly and configure handlers/exporters separately.

A convention's effectiveness should be evaluated on real data: metrics with stable names/tags and acceptable cardinality; traces preserving links across services/threads; logs helping locate traces; and sampling and exporters well understood. A solid contract helps monitor errors, latency, and application behavior consistently even as the system grows.

**References:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
