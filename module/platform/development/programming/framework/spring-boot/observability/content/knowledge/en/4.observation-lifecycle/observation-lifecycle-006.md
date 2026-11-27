# Recording Low-Cardinality Key-Values in the Observation Lifecycle

> **Chapter:** Observation Lifecycle  
> **Lesson:** Recording Low-Cardinality Key-Values  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. Goal: Attaching Aggregatable Context to an Observation

A Spring Boot application can track an ordering operation with Micrometer Observation. Measuring the average duration of all orders tells us whether the service is fast or slow, yet operational questions are usually more specific:

- How many inventory reservations succeeded and how many failed?
- Does the latency of the `web` channel differ from the `mobile` channel?
- After a deployment, how did the error rate of each **operation type** change?

To answer these questions, we add **low-cardinality key–value** pairs to the observation. For example, `channel=web`, `outcome=success`, `operation=reserve`. These values belong to a small, bounded set, making them suitable as metric grouping dimensions.

In Micrometer Observation, the convenient API is:

~~~java
observation.lowCardinalityKeyValue("channel", "web");
~~~

This call records metadata into the observation's context. When the system has a metrics handler, matching key–values can become measurement tags/labels; if a tracing handler is present, they can also be placed on the span as attributes. **Adding a key–value itself does not create a Timer, log, or span, nor send data to a backend.** Those actions depend on the configured handlers, registry, and exporters.

### Distinguishing Two Kinds of Questions

| Question | What Is Needed? | Example |
| --- | --- | --- |
| "What is the error rate per channel?" | Low-cardinality key–value | `outcome=error`, `channel=mobile` |
| "Which step slowed down order 8f7…?" | Trace/log with specific identifier | `orderId` in spans/logs under access policy |
| "How many reservations per minute?" | Counter or Timer count | `rate()` query on exported metrics |
| "Which step of the request timed out?" | Correlated spans and logs | Trace ID, DB/downstream spans |

This lesson focuses on **how to record and manage low-cardinality key–values in the Observation lifecycle**, rather than replacing lessons on configuring the entire metrics/tracing infrastructure.

## 2. Cardinality Is the Number of Distinct Values

**The cardinality of a key** is the number of distinct values that key can take. For metrics, actual cost depends on the number of resulting **label combinations**, number of measurements, number of instances, histogram buckets, and retention period.

For example, if the same metric has:

| Key | Value Set | Value Count |
| --- | --- | ---: |
| `channel` | `web`, `mobile`, `partner` | 3 |
| `outcome` | `success`, `rejected`, `error` | 3 |
| `region` | `north`, `central`, `south` | 3 |

If all combinations appear, these three dimensions alone yield **3 × 3 × 3 = 27** combinations. With 8 instances—assuming each instance carries its own identifying label—the backend may store up to **216 time series** for each metric form sharing that label set. A Timer exporting `_count`, `_sum`, and multiple `_bucket` series multiplies the series count further.

By contrast, `order.id`, `request.id`, emails, or session IDs can generate nearly unique values on every execution. Putting them into metric tags causes series counts to grow linearly with request volume, consuming RAM, increasing storage, slowing queries, and overloading the monitoring system.

**Low cardinality does not mean "short strings."** A value like `abcdef` may be short yet have countless variants; a channel name like `mobile` is longer yet remains within a three-value set. Always evaluate the **number of possible distinct values**, not string length.

## 3. Where Do Low-Cardinality Key–Values Live in an Observation?

In Micrometer, `Observation` tracks a unit of work. It holds an `Observation.Context` containing state and key–values added over time. `ObservationRegistry` coordinates handlers reacting to this lifecycle.

~~~mermaid
flowchart TD
    A["Create Observation: orders.reserve"] --> B["Add channel=web before start"]
    B --> C["start() → onStart"]
    C --> D["openScope() → business operation"]
    D --> E{"Outcome"}
    E -->|Success| F["Add outcome=success"]
    E -->|Rejected| G["Add outcome=rejected"]
    E -->|Technical error| H["Add outcome=error; error(ex)"]
    F --> I["Close scope and stop()"]
    G --> I
    H --> I
    I --> J["Metrics handler records sample with matching tags"]
    I --> K["Tracing handler updates span/attributes"]
~~~

Key milestones:

1. **`createNotStarted`:** initializes the observation without starting measurement. Known metadata such as `channel` or `operation` can be attached here.
2. **`start()`:** triggers `onStart` on matching handlers. Some handlers require metadata at this point to create resources, such as `LongTaskTimer`.
3. **Business execution:** outcome-dependent tags such as `outcome=success/error` can be added. In synchronous flows, open a scope when current observation/trace context is needed.
4. **`error(ex)`:** notifies the Observation of an exception so handlers recognize it, in addition to setting an `outcome` tag per business rules.
5. **`stop()`:** finishes measurement. Meter handlers typically aggregate duration and the low-cardinality keys available at completion time.

**Do not add tags after `stop()` and expect historical data to update.** Values must be supplied before handlers consume them. In particular, a handler processing metadata in `onStart` may not see tags added only at the end; not every handler waits until `onStop`.

## 4. Recording via the API: Single Keys or Multiple Key–Values

### 4.1. Attaching One Pair at a Time with `lowCardinalityKeyValue`

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

// observationRegistry is provided by Spring Boot via dependency injection.
Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .lowCardinalityKeyValue("operation", "reserve")
    .start();

try {
    observation.lowCardinalityKeyValue("outcome", "success");
} finally {
    observation.stop();
}
~~~

Each pair has the form **key → value**, such as `channel → web`. Key names should follow a consistent convention across observations and not vary arbitrarily between instances.

In the example, `outcome` is added after `start` merely to illustrate the API. In production, set it **after knowing the actual outcome**. If you set `success` before running the business logic and the operation fails, the metric may record the wrong outcome.

### 4.2. Attaching Multiple Pairs with `lowCardinalityKeyValues`

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValues(
        KeyValues.of(
            "channel", "web",
            "operation", "reserve"
        )
    )
    .start();
~~~

`KeyValues` is a Micrometer Common structure representing multiple `KeyValue` pairs. Choose the API form that fits your prepared data. For keys that could collide, **establish a single owner responsible for setting the value**, avoiding conventions, filters, and business code setting conflicting values.

### 4.3. Writing Directly to `Observation.Context`

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;

Observation.Context context = observation.getContext();
context.addLowCardinalityKeyValue(
        KeyValue.of("outcome", "success")
);
~~~

This style is useful inside an `ObservationFilter`, convention, or code working directly with the context. Inside business services, `observation.lowCardinalityKeyValue(...)` is usually easier to read.

To inspect values already attached to the context, you can call `context.getLowCardinalityKeyValues()` during diagnostics. Keep in mind these are **observation metadata**; whether the backend receives them still depends on handlers and configuration.

## 5. Complete Spring Boot Example: Recording Channel and Outcome at the Right Time

Scenario: a service reserves inventory before completing an order. We want to track `orders.reserve` by originating channel (`web`, `mobile`, `partner`) and outcome (`success`, `rejected`, `error`).

### 5.1. Service Instrumenting Synchronous Work

~~~java
package example.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry observationRegistry;

    public ReservationService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T reserve(String incomingChannel, Supplier<T> operation) {
        String channel = normalizeChannel(incomingChannel);

        Observation observation = Observation.createNotStarted(
                "orders.reserve", observationRegistry)
            // Value known before starting.
            .lowCardinalityKeyValue("channel", channel)
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = operation.get();

            // Mark success only after the operation completes.
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (ReservationRejectedException ex) {
            observation.lowCardinalityKeyValue("outcome", "rejected");
            observation.error(ex);
            throw ex;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
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

    // Example exception; in a real application this may live in its own file.
    public static final class ReservationRejectedException
            extends RuntimeException {
        public ReservationRejectedException(String reason) {
            super(reason);
        }
    }
}
~~~

**Meaning of each point:**

- `channel` is normalized **before `start()`**; thus the value set is four predefined options (`web`, `mobile`, `partner`, `other`). Using the raw string sent by clients would let clients inject millions of distinct values into the label.
- `outcome` is added **before `stop()`**, once success or failure is known. Both error branches and the success branch share the same **key** with different values; this is essential for comparing rates across outcomes.
- `observation.error(ex)` lets handlers know an exception occurred; setting `outcome=error` alone **does not replace** reporting the error.
- `try-with-resources` closes the scope, while `finally` stops the observation. The scope enables context-aware components to recognize the current observation and trace.
- The example catches two `RuntimeException` categories. If code involves cancellation, checked exceptions, or async work, extend the outcome policy accordingly. Never assume every path not entering `catch` completed successfully.

Sample invocation:

~~~java
String reservationId = reservationService.reserve(
    "web",
    () -> inventory.reserve(productId, requestedQuantity)
);
~~~

In a real application, `inventory.reserve(...)` calls a business component that must be implemented separately. The returned ID is used for transaction handling, **not placed into low-cardinality key-values**.

### 5.2. Why Not Attach an `orderId` Tag?

Suppose there are 300,000 orders per day. With `orderId` as a metric label, hundreds of thousands of new label sets appear every day, even if every request shares the same operation and outcome. Across multiple instances, histogram buckets, and long retention policies, costs can skyrocket.

When you need to investigate an individual order, include the ID in controlled logs or trace attributes **subject to access control, security, and sampling policies**. Metric dashboards only need grouping dimensions like `channel`, `outcome`, `region`, or `operation` with bounded value sets.

## 6. Configuring Spring Boot to See Tags in Metrics

### 6.1. Dependencies and Endpoints

The example uses Spring Boot 3.x with Micrometer Observation. In Maven when the project uses the Spring Boot BOM/parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Illustrative configuration in `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Actuator provides `ObservationRegistry` and Micrometer integration via auto-configuration. When the registry and compatible handlers are registered, an instrumented observation can produce metrics. `micrometer-registry-prometheus` provides the Prometheus registry and scrape endpoint. Never instantiate a standalone `ObservationRegistry.create()` inside a service, as a separate registry is disconnected from Spring's configuration.

In production, restrict access to management endpoints and configure proper authentication/network controls; scrape endpoints should only be reachable by the monitoring system.

### 6.2. Inspecting the Results

After running both successful and failed reservations, try:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/orders.reserve
curl "http://localhost:8080/actuator/metrics/orders.reserve?tag=outcome:success"
curl http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics/orders.reserve` can display `availableTags` such as `channel` and `outcome`, depending on handlers and instrumentation. In Prometheus output, the `orders.reserve` Timer usually corresponds to series such as `orders_reserve_seconds_count` and `orders_reserve_seconds_sum`. Names are transformed by naming conventions, so **check the actual exporter output** before writing alert rules.

If the metric name does not appear, check whether the observation was **executed and stopped**, whether a meter handler is configured, or whether instrumentation was filtered out by a predicate. Each observation is only created at runtime when its code path runs; having dependencies alone does not automatically generate the business metric `orders.reserve`.

## 7. Low Cardinality, High Cardinality, and Context-Only Data

The three kinds of data below serve different roles even though all are attached during observation.

| Data | API or Location | Best Suited For | Example |
| --- | --- | --- | --- |
| **Low-cardinality key–value** | `observation.lowCardinalityKeyValue(k, v)` | Metrics tags and trace attributes | `outcome=success`, `channel=web` |
| **High-cardinality key–value** | `observation.highCardinalityKeyValue(k, v)` | Detailed span data when needed; never as a metric label | Request identifier, business ID after policy review |
| **Context-private state** | `Observation.Context.put/get` or specialized context fields | Passing data between callbacks/handlers | Internal state object for measurement |

Example:

~~~java
observation.lowCardinalityKeyValue("outcome", "success");
observation.highCardinalityKeyValue("order.id", orderId);
observation.getContext().put("internal.phase", "saved");
~~~

These represent three distinct behaviors:

1. `outcome` has a small value set, supporting success or error rate calculations.
2. `order.id` has very high distinctness, so it is **not converted into a metric label**. Putting IDs into traces must weigh sensitive data concerns; never assume every identifier is safe to export.
3. `internal.phase` in context does not automatically become a metric tag or span attribute. Context can hold data used internally by instrumentation or handler logic.

Low-cardinality tags are consumed by metrics handlers per configuration; high-cardinality tags generally belong to tracing handlers. **Trace sampling is not metric sampling**: many requests still contribute to Timers even if only a fraction of requests are retained as traces. Therefore, never infer system throughput from exported trace counts.

## 8. Designing Stable Keys and Values

When a metric spans multiple instances and lives long-term, tags form part of a **data contract** between the application and dashboards, alerts, and SLOs.

### 8.1. Recommended Conventions

- Use keys describing a concrete business/technical dimension, such as `channel`, `outcome`, `operation`, `region`.
- Define an allowed value list for each key and map unexpected values to `other` or `unknown` where appropriate.
- Keep semantics consistent: `outcome=error` indicates a technical failure, `outcome=rejected` indicates a valid business-rule rejection. Without separating them, reports may conflate the two.
- Ensure every recording of the same metric carries the **required consistent set of keys**. Recording some outcomes without `outcome` causes outcome-filtered queries to miss samples.
- Never put real URLs containing IDs, raw SQL, stack traces, exception messages, emails, tokens, dynamically generated hostnames, or HTTP query strings into low-cardinality values.

### 8.2. Choosing Useful Dimensions

| Need | Suitable Key | Avoid |
| --- | --- | --- |
| Compare ingress channels | `channel=web/mobile/partner/other` | Arbitrary full `userAgent` strings |
| Compare business outcomes | `outcome=success/rejected/error` | `exception.message` |
| Compare operation types | `operation=reserve/release/commit` | `orderId` |
| Analyze APIs | `uri=/api/orders/{id}` (route template) | `uri=/api/orders/123456` |
| Compare environments | `deployment.environment=dev/staging/prod` | Freeform strings with request ID or build timestamp per call |

Not every key belongs on every observation. Every dimension adds analytical power along with cost. Keep only dimensions that support concrete operational decisions.

### 8.3. When Is `unknown` Needed?

When a value is unavailable or code has multiple failure paths, `unknown` is a clearer fallback than silently omitting the tag. However, never default to `success` before knowing the result. For flows involving non-`RuntimeException` failures or cancellation, define `cancelled`/`unknown` states and apply them consistently according to actual semantics.

## 9. Setting Tags in the Service, Convention, or Filter?

There are multiple ways to attach low-cardinality metadata to an observation. Where to place it depends on the **source** of the data.

| Approach | When to Use? | Notes |
| --- | --- | --- |
| `observation.lowCardinalityKeyValue` API | Service directly knows `channel` or `outcome` | Explicit, right alongside the operation |
| `ObservationConvention` | Multiple observations share naming and tag conventions based on context type | Reduces duplication and standardizes semantics |
| `ObservationFilter` | Need to enrich/adjust metadata derivable from context before completion | Ensure the filter is registered on the right registry |
| Custom `ObservationHandler` | Need to **react** to lifecycle events and read tags to update metrics/traces/logs | Not the default choice merely to set a tag name |
| Common tags on meter registry | Want to label all exported metrics | Scoped to meters/metrics; does not replace observation or span metadata |

Direct `ObservationFilter` example (registered during `ObservationRegistry` setup):

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationRegistry;

void configureFilter(ObservationRegistry registry) {
    registry.observationConfig().observationFilter(context -> {
        if ("orders.reserve".equals(context.getName())) {
            context.addLowCardinalityKeyValue(
                    KeyValue.of("component", "inventory")
            );
        }
        return context;
    });
}
~~~

This is a **configuration snippet**, not a per-request call. Register it once at application startup against the Spring Boot-configured registry. Avoid assigning the same key in multiple places with conflicting values. `ObservationFilter` enriches the context as the lifecycle reaches completion; handlers needing a tag in `onStart` may miss values added late.

With `ObservationConvention`, you typically define the **observation name, contextual name, and low/high-cardinality key–value sets** derived from a business context. Prefer conventions when multiple classes need a shared measurement standard instead of copy-pasting key/value strings across services.

## 10. Using Low-Cardinality Tags in PromQL

Suppose the `orders.reserve` Timer exports `orders_reserve_seconds_count`. The examples below hold only when your actual exporter emits matching series names and labels.

**Reservation attempts per second, broken down by outcome:**

~~~promql
sum by (outcome) (
  rate(orders_reserve_seconds_count[5m])
)
~~~

**Technical error ratio across all attempts:**

~~~promql
sum(rate(orders_reserve_seconds_count{outcome="error"}[5m]))
/
sum(rate(orders_reserve_seconds_count[5m]))
~~~

The result is a ratio from 0 to 1. If there is no traffic in the query window, the denominator can be 0; dashboards and alerts should explicitly handle no-data cases.

**Failure rate per channel:**

~~~promql
sum by (channel) (
  rate(orders_reserve_seconds_count{outcome="error"}[5m])
)
~~~

If `outcome=rejected` means a valid business rejection, you should usually **not** lump it directly into system errors. How you pick the SLI/SLO numerator and denominator must reflect the business contract.

**Average operation latency by channel (seconds):**

~~~promql
sum by (channel) (
  rate(orders_reserve_seconds_sum[5m])
)
/
sum by (channel) (
  rate(orders_reserve_seconds_count[5m])
)
~~~

This is the **average**, not p95. Computing p95 with `histogram_quantile()` requires configured histograms producing `_bucket` series; you must then sum by `le` and the dimensions you want to preserve. Tags enable grouping, yet adding key–values **does not enable histograms by itself**.

## 11. Linking Tags with Logs and Distributed Tracing

In a multi-service system, a single request can produce metrics, logs, and traces:

~~~mermaid
flowchart LR
    A["Order API"] --> B["Observation with channel, outcome"]
    B --> C["Metrics handler"]
    B --> D["Tracing handler"]
    B --> E["Log enrichment / MDC"]
    C --> F["RPS, error rate, latency by channel"]
    D --> G["Span with attributes + trace context"]
    E --> H["Logs with traceId/spanId when configured"]
    F --> I["Detect anomaly"]
    I --> G
    G --> H
~~~

Low-cardinality tags like `channel` and `outcome` help narrow down anomalies on dashboards; trace/span IDs let you pivot into investigating a specific request. In Spring Boot, log–trace correlation depends on tracing configuration, logging patterns, and context propagation.

**Three common misconceptions:**

- Adding `orderId` as a low-cardinality tag to "quickly find logs for that order" is an anti-pattern for metrics. When identifiers are needed, use logs/traces subject to access and security policies.
- Having an observation does not mean every request exports a trace. Samplers may keep only a subset of traces; metrics and tracing are governed separately.
- Calling `observation.lowCardinalityKeyValue(...)` on thread A does not guarantee the current observation or trace context automatically follows onto thread B. Executors, Reactor, or cross-service HTTP calls require proper propagation mechanisms.

### When Work Is Asynchronous

The synchronous `try/finally` pattern in Section 5 **must not be copied verbatim** for tasks returning results later, such as an active `CompletableFuture`. Calling `stop()` right after submitting work measures only scheduling time, and `outcome` will not reflect the real result.

For async work, identify **actual completion time** to set `outcome` and call `stop()`, while safely propagating scopes/contexts using framework mechanisms. Never leave one thread's scope open indefinitely waiting for a callback on another thread; manage scope lifecycles per executing thread.

## 12. Common Mistakes When Recording Low-Cardinality Key-Values

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Dashboard lacks the `outcome` tag | Tag not set on all branches, set after `stop`, or missing metrics handler | Set tag before stop; inspect callbacks/registry |
| Failures still show `outcome=success` | Set success before running work and never updated properly | Assign based on actual outcome; account for cancellation |
| Series explode after deployment | Added unbounded tag like `userId` | Replace with bounded catalog; audit live labels |
| Low-cardinality keys set, yet no metric appears | Missing Meter `ObservationHandler` or instrumentation never ran | Check Actuator/registry, stop calls, and exporter |
| Metrics exist, yet no matching spans appear | Tracing disabled, missing exporter, trace dropped by sampler, or missing propagation | Inspect the tracing pipeline separately |
| Channel data split across variants | Same meaning tagged inconsistently (`mobile-app`, `MOBILE`, `mobile`) | Normalize values before adding tags |
| Same metric name has inconsistent label sets | Different code branches attach different tags | Define a contract for mandatory keys |
| Tag added at end missing from `LongTaskTimer` | Handler needs data at `onStart` | Record required keys before `start()` |
| Metric counts do not match trace counts | Traces are sampled | Compare using aggregated metrics; never estimate traffic from trace counts |

When diagnosing, start at `/actuator/metrics` to confirm the meter exists, then inspect labels at `/actuator/prometheus`. If metric names look transformed, verify your active registry and handler conventions instead of guessing from the observation name.

## 13. Step-by-Step Practice Exercise

An application exposes `POST /api/checkout`, accepting requests from `web`, `mobile`, or `partner`. Suppose the business logic can succeed, be rejected due to insufficient stock, or fail with a timeout.

**Task 1: Design Labels**

Propose three keys:

- `channel`: `web`, `mobile`, `partner`, `other`.
- `outcome`: `success`, `rejected`, `error`.
- `operation`: `checkout`.

Calculate the maximum label combinations for those 3 keys, excluding instances or histograms. Result: **4 × 3 × 1 = 12**. Explain why adding `orderId` is inappropriate.

**Task 2: Instrument the Lifecycle**

Write a method using `ObservationRegistry` and `Observation.createNotStarted(...)`. Set `channel` before `start()`, set `outcome` once the result is known, report exceptions via `error(ex)`, and always call `stop()` in `finally`. Verify the scope closes even when exceptions are thrown.

**Task 3: Verify the Data**

Trigger at least one call for each outcome. Verify `/actuator/metrics` and `/actuator/prometheus` expose the expected tags; write PromQL queries to compute:

- RPS per outcome over a 5-minute window.
- Ratio of `outcome=error` across all attempts.
- Average latency per `channel`.

**Task 4: Handle Tricky Cases**

Consider the case where the operation returns a `CompletableFuture`. Identify when enough information exists to set `outcome` and call `stop()`, and describe how to manage propagation when the callback executes on another thread.

### Self-Check Questions

1. How does low-cardinality differ from high-cardinality? Why can even a very short ID string still be unsuitable as a metric label?
2. If you add `outcome` after `stop()`, what can happen to the recorded Timer?
3. Why don't low-cardinality key–values attached to an Observation automatically show up in Prometheus?
4. When should keys be attached at the start of an observation, and when should you wait for the processing result?
5. Why don't `observation.error(ex)` and `outcome=error` completely replace each other?
6. Must a custom handler processing `onStart` see a tag added near `onStop` by an `ObservationFilter`?
7. If only 10 traces appear while the Timer records 1,000 requests, can you conclude metrics are wrong? Why or why not?

**Completion criteria:** record low-cardinality tags at the proper lifecycle stages; distinguish low/high/context data; control value sets and label consistency; read results from Actuator/Prometheus; and correlate signals with logs/traces without inflating metric cardinality.

## Key Takeaways

- `lowCardinalityKeyValue(key, value)` adds bounded metadata pairs to an Observation; **handlers and exporters** determine which signals are produced and where they go.
- Attach known metadata **before `start()`** when needed; attach outcome metadata **before `stop()`** after business logic completes.
- Choose bounded keys and values, normalize across instances, and enforce a consistent label contract for each metric.
- Never place per-request/order identifiers or sensitive data into metric labels. For individual investigations, use logs/traces with proper context propagation.
- Inspect actual metrics via Actuator, Prometheus series, and key-based queries; remember that trace sampling does not reduce metric counts.

## References

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
