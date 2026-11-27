# Testing conventions in Micrometer Observation

When a Spring Boot service emits metrics and distributed traces, **`ObservationConvention`** determines much of what operators see: operation names, span names, metric labels, and diagnostic attributes. A small mistake like renaming `inventory.channel` to `channel`, putting an order ID into a low-cardinality tag, or letting a convention match the wrong context type may not break the business API, yet it skews dashboards, alerts, and traces.

Therefore, **testing conventions** is part of observability quality: you must verify the **naming and key-value contract**, **custom/global/default convention selection rules**, **interaction with filters**, **Observation lifecycle**, and **actual outcomes in metrics/traces/logs**. This lesson belongs to the **Convention and filter** chapter of the **SPRING_BOOT_OBSERVABILITY** module, focusing on Spring Boot combined with Micrometer Observation, metrics, logs, distributed tracing, and decisions around context propagation, cardinality, exporters, and sampling.

## Learning objectives

After this lesson, you will be able to:

1. Identify the key properties to test for an `ObservationConvention`.
2. Write unit tests for names, contextual names, `supportsContext`, and `KeyValues`.
3. Use `TestObservationRegistry` to verify Observations are actually created, stopped, and carry expected key-values.
4. Test the **custom > global > default** precedence order on convention-aware Observation creation APIs.
5. Test how `ObservationFilter` interacts with contexts and distinguish filters from conventions.
6. Catch cardinality mistakes and sensitive data before metadata reaches metrics or traces.
7. Pick the right testing level when verifying handlers, exporters, sampling, logs, and propagation in a Spring Boot application.

## 1. What to test and why?

An `Observation` represents one execution, such as an inventory reservation operation. `Observation.Context` holds data for that execution. `ObservationConvention<T>` translates the context into the observation signal's name and metadata.

| Subject | Responsibility | Testing question |
| --- | --- | --- |
| `Observation.Context` | Carries data for a single execution | Is data normalized before becoming a tag? |
| `ObservationConvention<T>` | Selects name, contextual name, and key-values | Are names, key sets, and low/high cardinality accurate? |
| `GlobalObservationConvention<T>` | Provides a registry-registered convention for matching contexts | Is it selected at the right time without misapplying to wrong contexts? |
| `ObservationFilter` | Adjusts `Observation.Context` during the lifecycle | Does it add expected metadata while avoiding data leaks? |
| `ObservationPredicate` | Decides whether to record the observation or make it a no-op | Are critical flows accidentally dropped? |
| `ObservationRegistry` and handlers | Process lifecycle to emit metrics, spans, or other effects | Does the observation stop, record errors, and get handled? |
| Exporters and backends | Transport/store telemetry | Do metrics or traces actually reach where operators query them? |

A solid convention must satisfy core invariants:

- Stable technical name, e.g. `inventory.reserve`, free of per-request IDs.
- `supportsContext` returns `true` only for contexts the convention genuinely handles.
- Low-cardinality key sets have controlled names and bounded values that do not grow with request volume.
- High-cardinality metadata is not promoted into metric labels and contains no secrets.
- Contextual name is readable and does not drift arbitrarily across releases.
- Documentation contracts (`ObservationDocumentation` if used) match runtime key-values.

You do not need to test every implementation detail. Tests should guard **the properties that dashboards, alerts, queries, and on-call engineers rely on**.

## 2. Distinguishing test layers

~~~mermaid
flowchart TD
    A["Unit test ObservationConvention"] --> B["Runtime test with TestObservationRegistry"]
    B --> C["Metric handler test with SimpleMeterRegistry"]
    C --> D["Spring Boot integration test"]
    D --> E["Verify exporter, backend, and correlation"]
~~~

| Layer | What it proves | What it does not prove yet |
| --- | --- | --- |
| **Convention unit test** | `getName`, `getContextualName`, `supportsContext`, low/high KeyValues | Whether a registry or handler uses the convention |
| **TestObservationRegistry** | Convention selection at runtime, lifecycle, errors, context key-values | Whether metrics/spans are exported to a backend |
| **SimpleMeterRegistry** | Metric names, low-cardinality tags, recorded counts and timings | Whether OTLP/Prometheus exporters work in real environments |
| **Spring Boot integration test** | Auto-configured beans, injected registry, application flows working | Full production pipeline or real-world sampling behavior |
| **Staging/end-to-end** | Multi-service linked traces, log correlation, exporters and backends receiving signals | That every production request has a trace; sampling/retention can omit some |

Keep tests close to the logic they protect. A pure Java unit test is fast and catches accidental key renames. End-to-end testing is costlier but necessary for boundaries unit tests cannot see, such as HTTP propagation or Collector failures.

## 3. Business example: inventory reservation for orders

Suppose `order-service` (Spring Boot) calls `inventory-service`. An `inventory.reserve` operation runs from web or batch jobs. We want to track reservation duration by caller source, and inspect the trace of a single attempt on timeout.

Expected contract:

| Component | Value | Scope |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Stable for querying |
| Contextual name | `reserve inventory` | Displayed in traces |
| `inventory.channel` | `web` or `batch` | Low cardinality |
| `inventory.operation` | `reserve` | Low cardinality |
| `inventory.attempt.id` | Pseudonymous attempt ID | High cardinality |

Never use order IDs, user IDs, emails, tokens, raw URL paths, or exception messages as low-cardinality tags. If high-cardinality metadata is truly needed for investigations, ensure a safe data source and use high cardinality with strict controls.

### 3.1. Context accepting controlled inputs

In `ReserveContext.java`:

~~~java
package com.example.observability;

import io.micrometer.observation.Observation;

public final class ReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    public ReserveContext(String channel, String attemptId) {
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        if (attemptId == null || attemptId.isBlank()) {
            throw new IllegalArgumentException("Missing attemptId");
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

`attemptId` is assumed to be an internal random identifier that reveals no personal data and has a bounded length where generated. Constructor validation ensures tests fail early if a developer tries to pass an arbitrary channel value.

### 3.2. Default convention

In `ReserveConvention.java`:

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class ReserveConvention implements ObservationConvention<ReserveContext> {
    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(ReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

The convention supports only `ReserveContext`. Do not make network calls, database queries, or run business logic inside convention methods: conventions should be predictable and directly testable.

## 4. Pure unit tests for ObservationConvention

This section illustrates JUnit 5 and AssertJ. Examples use Java 17+, matching typical Spring Boot 3.x projects.

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;

class ReserveConventionTest {
    private final ReserveConvention convention = new ReserveConvention();

    private static List<KeyValue> values(KeyValues keyValues) {
        return StreamSupport.stream(keyValues.spliterator(), false).toList();
    }

    @Test
    void supportsOnlyReserveContext() {
        assertThat(convention.supportsContext(
                new ReserveContext("web", "attempt-01"))).isTrue();
        assertThat(convention.supportsContext(new Observation.Context())).isFalse();
    }

    @Test
    void keepsStableNames() {
        ReserveContext context = new ReserveContext("batch", "attempt-02");
        assertThat(convention.getName()).isEqualTo("inventory.reserve");
        assertThat(convention.getContextualName(context))
                .isEqualTo("reserve inventory");
    }

    @Test
    void placesKeysInCorrectCardinalityGroup() {
        ReserveContext context = new ReserveContext("web", "attempt-03");

        assertThat(values(convention.getLowCardinalityKeyValues(context)))
                .containsExactlyInAnyOrder(
                        KeyValue.of("inventory.channel", "web"),
                        KeyValue.of("inventory.operation", "reserve"));
        assertThat(values(convention.getHighCardinalityKeyValues(context)))
                .containsExactly(KeyValue.of("inventory.attempt.id", "attempt-03"));
    }
}
~~~

Two choices in this test matter:

1. Asserting **both key names and values**; checking only element count would miss a typo turning `inventory.channel` into `channel`.
2. Asserting **both low and high groups**; if a dynamic ID slips into low cardinality, the test must fail.

The `supportsContext` test uses a plain `Observation.Context` to catch bugs where `supportsContext` unconditionally returns `true`. It needs no Spring Boot application context.

### 4.1. Testing invalid values

Add tests for `channel` values outside `web`/`batch`, blank `attemptId`, or inputs exceeding length limits when validators exist. For example:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> new ReserveContext("user-283746", "attempt-04"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("Unsupported channel");
~~~

Accept only an operationally meaningful finite set. Never write `channel = request.getHeader("X-Channel")` and pass it directly into metric tags if the header is uncontrolled.

## 5. Runtime testing with TestObservationRegistry

Testing the convention directly does not prove instrumentation **actually uses** it. `TestObservationRegistry` from `micrometer-observation-test` lets you execute Observations and assert names, tags, and lifecycle without Prometheus or an OTLP Collector.

Example test using the default convention:

~~~java
package com.example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class ReserveObservationRuntimeTest {

    @Test
    void stopsObservationWithDocumentedMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted(
                null,                       // No custom convention passed.
                new ReserveConvention(),    // Default convention.
                () -> new ReserveContext("web", "attempt-05"),
                registry)
            .observe(() -> { /* simulate successful reservation */ });

        TestObservationRegistryAssert.assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasLowCardinalityKeyValue("inventory.operation", "reserve")
                .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-05")
                .doesNotHaveError();
    }
}
~~~

`Observation.createNotStarted(custom, default, supplier, registry)` is a **convention-resolving factory**; this is the crucial call path for testing custom/global/default selection behavior. Once created, `observe(...)` starts the Observation, opens a scope, runs the lambda, closes the scope, and stops the Observation even on exception.

This test proves metadata exists on the runtime Observation and the lifecycle completed. It **does not prove** metrics were recorded into a `MeterRegistry`, spans were shipped by an exporter, or traces were stored by a backend.

### 5.1. Testing the error path

When business logic fails, verify the exception is **not swallowed**, the Observation still stops, and the error is recorded. Pattern:

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();

assertThatThrownBy(() ->
        Observation.createNotStarted(
                null,
                new ReserveConvention(),
                () -> new ReserveContext("web", "attempt-failed"),
                registry)
            .observe(() -> {
                throw new IllegalStateException("inventory timeout");
            }))
    .isInstanceOf(IllegalStateException.class);

// Continue using TestObservationRegistryAssert to verify
// Observation stopped and carries the error per the running version's API.
~~~

In the snippet above, `assertThatThrownBy` is imported from `org.assertj.core.api.Assertions`. Error tests should use the assertion methods provided by your `micrometer-observation-test` version to verify the Throwable and stopped state without coupling to internal handler details.

## 6. Testing custom, global, and default precedence

An important testing goal is confirming **which convention actually wins**. On Observation creation APIs accepting custom, default, and context supplier parameters, precedence is typically:

1. **Custom convention** passed to the call, if present.
2. **GlobalObservationConvention** registered on the registry and supporting that context.
3. **Default convention** passed to the factory, if neither of the above applies.

### 6.1. Creating a global convention for tests

In tests, you can use a **finite-valued** low-cardinality marker to distinguish which convention won. This marker is solely for testing selection—do not add it to production metrics.

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;

public final class GlobalReserveConvention extends ReserveConvention
        implements GlobalObservationConvention<ReserveContext> {

    @Override
    public KeyValues getLowCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("convention.source", "global"));
    }
}
~~~

`GlobalReserveConvention` inherits `supportsContext` from `ReserveConvention`, so it still applies exclusively to `ReserveContext`.

### 6.2. Verifying global is selected

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();
registry.observationConfig()
        .observationConvention(new GlobalReserveConvention());

Observation.createNotStarted(
        null,
        new ReserveConvention(),
        () -> new ReserveContext("batch", "attempt-global"),
        registry)
    .observe(() -> { });

TestObservationRegistryAssert.assertThat(registry)
        .hasSingleObservationThat()
        .hasBeenStopped()
        .hasLowCardinalityKeyValue("convention.source", "global");
~~~

If you remove the global registration, the factory falls back to `ReserveConvention` (default) and `convention.source=global` disappears. That verifies **fallback**, not merely that the code runs without errors.

### 6.3. Verifying custom beats global

You can create a custom convention extending `ReserveConvention` that emits `convention.source=custom`, then pass that custom instance as the factory's first argument. When the registry also has the global convention, the test expects `custom` and not `global`. Thus the test genuinely distinguishes precedence order.

In particular, **registering a global convention does not mean it applies to every Observation**. If instrumentation creates an Observation directly by string name, or already supplies a specialized custom convention, the global selection path may not be used. Therefore tests must use **the exact factory and context type** from production code.

Never register two global conventions both returning `supportsContext=true` for the same context type and rely on bean initialization order to pick a winner. Keep scopes narrow and write tests guarding against overlap.

## 7. Testing ObservationFilter

`ObservationFilter` is not `ObservationConvention`. A convention chooses name and key-value sets from a context; a filter can modify `Observation.Context` during its lifecycle. A common use case is adding a stable environment label to appropriate Observations while avoiding unintended side effects.

Example in a test:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;

TestObservationRegistry registry = TestObservationRegistry.create();
registry.observationConfig().observationFilter(context -> {
    context.addLowCardinalityKeyValue(
            KeyValue.of("deployment.environment", "test"));
    return context;
});

Observation.createNotStarted("inventory.reserve", registry)
        .lowCardinalityKeyValue("inventory.channel", "web")
        .observe(() -> { });

TestObservationRegistryAssert.assertThat(registry)
        .hasSingleObservationThat()
        .hasBeenStopped()
        .hasLowCardinalityKeyValue("deployment.environment", "test");
~~~

Things to verify:

- The filter **does not drop** tags already set by the convention or instrumentation.
- Shared keys have finite cardinality, e.g. `deployment.environment=staging`.
- No accidental addition of user IDs, emails, or raw request paths into low-cardinality tags.
- No invalid assumptions about execution timing: metadata available only at the end of an Observation differs from metadata needed at start.
- The filter never assumes every context is `ReserveContext`; check the type before casting.

**Note:** handlers may read metadata at different lifecycle points. A filter adding a key near the end of an Observation does not guarantee every attribute appears on a span right at start time. Verify the behavior of your active handlers, especially when testing tracing and metrics together.

If the goal is simply adding common tags to **all metrics**, `MeterRegistry` common tags may be easier to manage. If the goal is dropping an unneeded Observation, look at `ObservationPredicate` and write tests confirming critical flows are not omitted.

## 8. Verifying metric labels with SimpleMeterRegistry

`TestObservationRegistry` focuses on Observations and metadata; to prove names/tags actually become metrics, pair an in-memory meter registry with the metrics handler.

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import static org.assertj.core.api.Assertions.assertThat;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));

Observation.createNotStarted(
        null,
        new ReserveConvention(),
        () -> new ReserveContext("web", "attempt-not-a-metric-label"),
        registry)
    .observe(() -> { });

Timer timer = meters.find("inventory.reserve")
        .tag("inventory.channel", "web")
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
assertThat(timer.getId().getTag("inventory.attempt.id")).isNull();
~~~

This example uses Micrometer classes matching the selected dependency version. The test verifies:

1. The handler recorded one Observation into a Timer with the expected name.
2. Low-cardinality labels were created properly.
3. `inventory.attempt.id`, being high cardinality, **does not appear** in the timer's `Meter.Id`.

Some instrumentations may add other labels or transform names per backend naming conventions; this test checks in-memory `SimpleMeterRegistry`, not exported Prometheus series names.

Never assert exact timings down to nanoseconds: actual execution time varies with machine load and scheduler jitter. Assert Timer existence, exact counts, and non-negative durations; add loose timing thresholds only when strictly verifying timing behavior.

## 9. Testing in a Spring Boot application

For a Spring Boot 3.x project with Micrometer, typical Gradle dependencies include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Only needed if the system uses OpenTelemetry tracing:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Exact versions should follow your project's dependency management/BOM. In `@SpringBootTest` or an integration test, inject **the exact `ObservationRegistry` bean used by the application** to verify:

1. `ObservationConvention` or `GlobalObservationConvention` beans were registered via auto-configuration as designed.
2. Services did not accidentally create a separate `ObservationRegistry.create()` lacking the application's handlers/filters.
3. Controller/service instrumentation uses the right context, right convention, and stable names.
4. Filters are registered without duplicating tags or unexpectedly overwriting metadata.
5. When tracing is enabled, logs carry Trace ID/Span ID along recorded paths.

Do not assume a global bean applies to every HTTP request: Spring's HTTP server/client integrations may use specialized conventions, and custom conventions take precedence. For HTTP, use the instrumentation's dedicated convention interface rather than casting all contexts to a business type.

### 9.1. Testing through exporters and backends

Broader verification requires a production-like telemetry pipeline:

~~~mermaid
flowchart LR
    A["Spring Boot + ObservationRegistry"] --> B["Metrics handler"]
    A --> C["Tracing handler"]
    A --> D["Logs + correlation"]
    B --> E["Prometheus / metrics backend"]
    C --> F["OTLP exporter / Collector"]
    F --> G["Trace backend"]
    D --> H["Log backend"]
    G -. "trace ID" .-> H
~~~

In staging, send requests covering both success paths and simulated timeouts, then verify:

- `inventory.reserve` metrics are stored, aggregated by `inventory.channel`, with no `inventory.attempt.id` in labels.
- Corresponding spans appear in traces when retained by sampling, with expected contextual names and attributes.
- Traces from `order-service` to `inventory-service` have valid parent/child relationships when HTTP clients and downstream services are instrumented.
- Logs with Trace ID help locate timeout records, free of sensitive data.
- Collectors/exporters report no errors and do not silently drop data.

Keep two facts separate: **a passing convention unit test does not mean the exporter works**; having a Trace ID in logs does not guarantee the trace was stored in the backend either.

### 9.2. Impact of sampling and context propagation

If the sampler keeps 10% of traces, a specific request may lack a trace in the backend even when the Observation ran and metrics were recorded. Tests verifying traces should use environment-appropriate sampling settings and account for head/tail sampling limits.

When crossing `@Async`, executors, Reactor, messaging, or an uninstrumented HTTP client, context can be lost. Even a convention with perfect names and tags cannot fix broken propagation. Test those boundary crossings explicitly, inspecting W3C `traceparent` headers and the context propagation mechanism for your Spring version.

## 10. Testing contract changes and cardinality

Suppose there are 3 regions, 2 channels, 4 outcomes, and 100 instances. A single metric can reach **3 × 2 × 4 × 100 = 2,400** series combinations before counting any other labels. If someone adds `orderId` with hundreds of thousands of values to low-cardinality tags, series count can grow alongside request volume.

Therefore, when reviewing convention changes, check:

| Change type | Risk | Test or safeguard |
| --- | --- | --- |
| Renaming `inventory.reserve` | Dashboards/alerts fail to query old name | Name contract test, audit existing queries |
| Renaming `inventory.channel` to `channel` | Dashboards split data across schemas | Key contract test, migration plan |
| Adding `inventory.region` | Increases time-series combinations | Bound values, estimate cardinality |
| Adding `orderId` to low cardinality | Series explosion, potential data leak | Assert tags contain no dynamic IDs, block in code review |
| Moving `attempt.id` from high to low | Degrades metrics performance | Test strict separation of low/high sets |
| Changing `supportsContext` to `true` | Global convention misapplied | Test unsupported context types |
| Adding a global filter | Key collisions or overwritten metadata | Test before/after filter behavior |
| Upgrading Spring/Micrometer | Factories and auto-configuration may change | Re-run relevant unit + integration tests |

**There is no reliable automated measure of total production cardinality from Java tests alone**, because backend labels and real-world value distributions differ. Tests should enforce constraints checkable early, while scalability must be evaluated against real traffic, registries, and dashboards.

### 10.1. Should you snapshot every tag name?

Snapshots can help when a contract is stable and the key count is small, yet large snapshots or order-sensitive assertions become brittle. For conventions, it is usually better to write assertions **specific to meaningful values and key sets**. For example, test low and high groups separately using `containsExactlyInAnyOrder` to avoid failures caused solely by internal `KeyValues` ordering.

## 11. Troubleshooting workflow when tests fail

| Symptom | Question to check | Fix |
| --- | --- | --- |
| `getName` changed unexpectedly | Was the convention modified or the operation renamed? | Confirm contract change and update dashboards intentionally |
| Global convention not selected | Did the factory receive a non-null custom convention? What does `supportsContext` return? | Use the right factory/context and avoid overlap |
| Unit test passes, `TestObservationRegistry` fails | Did instrumentation create the Observation with a string name directly? | Check creation path and registry registration |
| Low/high keys mixed up | Which method returned the key? | Move dynamic IDs to high cardinality or remove them |
| Filter drops a tag | Did the filter mutate the context unexpectedly? | Narrow filter conditions and add negative tests |
| Observation exists, no Timer | Are metrics handler and `MeterRegistry` registered? | Check handler registration and stop timing |
| Timer exists, missing in Prometheus | Endpoint, registry, or scrape/exporter error? | Inspect the metrics pipeline separately |
| Metrics exist, no traces | Sampler, bridge, propagation, exporter, backend? | Check step by step; do not blame the convention |
| Trace splits across async/service boundaries | Was context propagated? | Check HTTP client, `traceparent`, executors |
| Logs do not correlate with traces | Are MDC/correlation layouts configured? | Check logging configuration and active scope |

When runtime tests fail, inspect the **Observation creation path** and **active registry** before modifying exporters. When the backend lacks data, distinguish among uninstrumented code, no-op predicates, dropped sampling, broken propagation, and disrupted telemetry pipelines.

## 12. Checklist for pull requests changing conventions

| Criterion | Required evidence |
| --- | --- |
| Clear name and contextual name | Unit test asserting expected name strings |
| Accurate supported context scope | Positive and negative tests for `supportsContext` |
| Stable low-cardinality keys | Assert both keys and values from finite lists |
| High-cardinality keys clearly separated | Test confirming no IDs leak into low cardinality |
| Sensitive data excluded | Validators/reviews/tests for high-risk metadata |
| Custom/global/default precedence as expected | Runtime test distinguishing convention markers |
| Filters do not corrupt context | Tests for metadata before and after filters |
| Observation completes lifecycle | `hasBeenStopped` and error-path tests |
| Metrics handler records matching Timer | `SimpleMeterRegistry` test |
| Accurate Spring Boot integration | Integration test using the injected registry |
| Traces/logs/propagation verified | Staging test across service/async hops |
| Dashboards and alerts updated | Name/tag migration plan when needed |

## 13. Hands-on lab: testing inventory-service's convention

**Scenario:** the Spring Boot team just created `ReserveConvention` to instrument `web` and `batch` callers. One member wants to add `inventory.order.id` to metric tags to find failing requests faster; another proposes replacing the default convention with a global convention so it applies to every reservation call.

**Tasks:**

1. Build `ReserveContext` and `ReserveConvention` per the examples, explicitly defining names and low/high key sets.
2. Write unit tests for `supportsContext`, `getName`, contextual name, and both `KeyValues` groups.
3. Use `TestObservationRegistry` to run two Observations (success and thrown exception), verifying lifecycle and metadata.
4. Register `GlobalReserveConvention`, test that global is chosen when custom is absent and context matches, then test that custom takes precedence.
5. Add an `ObservationFilter` appending `deployment.environment=test` and verify this tag does not drop `inventory.channel`.
6. Use `SimpleMeterRegistry` to prove `inventory.attempt.id` does not appear in metric labels.
7. Propose how to correlate failing requests without placing `inventory.order.id` in low-cardinality tags.
8. In a test environment with tracing, verify a trace connecting `order-service` to `inventory-service`; explain why a sampled-out request has no trace in the backend.
9. Write a short migration guide for renaming `inventory.channel` to `channel`, covering dashboards, alerts, and historical data.

**Expected outcome:** a test suite protecting the name/tag contract, tests demonstrating convention precedence, proof that metrics contain no dynamic IDs, and notes on traces, exporters, sampling, and handling lost propagation.

## 14. Remember

Testing `ObservationConvention` should progress from **pure contract** to **live execution path**. Unit tests guard names and key classification; `TestObservationRegistry` proves the convention was applied and Observations stopped properly; `SimpleMeterRegistry` verifies metric metadata; integration tests and backend checks validate Spring Boot auto-configuration, tracing, exporters, logs, and propagation.

Sound conventions and filters make observability data consistent, yet only when paired with **well-understood sampling, controlled cardinality, functioning exporter pipelines, and metrics–logs–traces correlation** can operations teams investigate errors and latency reliably.

**References:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
