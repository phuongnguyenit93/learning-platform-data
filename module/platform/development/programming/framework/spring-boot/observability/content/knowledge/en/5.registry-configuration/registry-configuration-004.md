# ObservationPredicate: Deciding Which Observations Are Recorded

In the **Registry Configuration** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `ObservationPredicate` is a key control point in Micrometer Observation. It allows a Spring Boot application to **decide whether to enable an observation** right at the observation creation boundary, based on the operation's name and initial context.

In real systems, observability needs to combine **metrics, logs, and distributed tracing** to investigate errors, latency, and application behavior. However, some high-frequency repetitive activities such as heartbeats, internal tasks, or polling carry less diagnostic value than the volume of telemetry they generate. `ObservationPredicate` can exclude these observations from registry processing, provided the exclusion does not remove signals needed for operations.

> **Key idea:** `ObservationPredicate` answers the question **"Is this observation allowed to be active?"**. It is not a mechanism for renaming/retagging, fixing cardinality, deciding trace sampling, or stopping business logic from running.

## 1. Where Does ObservationPredicate Fit in the Micrometer Flow?

An observation represents a meaningful unit of work: handling a request, calling a dependency, running a job, or executing a business step. `ObservationRegistry` manages the components participating in the observation lifecycle, including predicates, conventions, filters, and handlers according to the configuration of the version in use.

Conceptual diagram:

```text
Application / framework instrumentation
         |
         v
  Create Observation (name + context)
         |
         v
  ObservationPredicate.test(name, context)
         |
         +----- false -----> Inactive observation (no-op)
         |                     | 
         |                     +--> Business code inside observe(...) still runs
         |
         +----- true ------> Active observation
                               |
                               +--> start / scope / event / error / stop
                               |
                               +--> ObservationHandler(s)
                                     |
                                     +--> Metric handler, if present
                                     +--> Tracing handler, if present
```

This diagram illustrates the **activation decision**, not the exact internal callbacks of every handler. Actual handlers and exporters also depend on Spring Boot/Micrometer dependencies and configuration.

Core interface:

```java
package io.micrometer.observation;

@FunctionalInterface
public interface ObservationPredicate {
    boolean test(String observationName, Observation.Context context);
}
```

- `observationName` is the observation name specified by instrumentation, such as `internal.heartbeat` or `payment.authorize`.
- `context` is the context attached to the observation; its concrete type depends on where the observation is created (HTTP, messaging, custom job, etc.).
- Return value `true`: the observation is allowed to be active and continues through registry components.
- Return value `false`: the observation is disabled; handlers for that observation do not produce the usual corresponding signals.

**A common misconception:** a predicate is not an `if` guard around business logic. If you call `observation.observe(() -> processOrder())` and the predicate rejects it, `processOrder()` **still executes**. Only the observation part becomes a no-op.

## 2. When Should You Use It?

First identify the **operational question** you need to answer and verify whether existing signals already suffice. A predicate is useful when *the entire observation* is unnecessary within a clear scope.

| Situation | Should use `ObservationPredicate`? | Reason |
| --- | --- | --- |
| `internal.heartbeat` observation fires constantly, other health check/availability metrics exist | **Possibly** | Reduces observations that add no new information |
| An internal cache cleanup task with no SLO impact, needing no dedicated trace or metric | **Possibly** | Avoids high span/metric volume once proven unnecessary |
| Want to exclude all observations for a known, stable name | **Well-suited** | Simple name-based decision at creation time |
| Want to remove a sensitive tag while keeping observation latency/errors | **Not suitable** | Fix tag attachment, convention/filter, or data policy instead |
| Want to keep metrics while reducing traces sent to the exporter | **Not suitable** | Use sampling/tracing configuration so metrics stay intact |
| Want to drop the metric while keeping the trace for the same operation | **Not suitable** | Control the metric handler, meter, or an appropriate `MeterFilter` |
| Want to block requests to `/actuator/health` from executing | **Not suitable** | Predicates only control telemetry, not HTTP request execution |
| Need to filter observations based on error outcome occurring after completion | **Usually not suitable** | At activation decision time, the outcome does not exist yet |

For example, a system emits one million `internal.heartbeat` events per hour that merely duplicate a reliable health metric. Excluding that observation can be reasonable. Conversely, disabling `http.server.requests` just to reduce series count can strip latency/error dashboards, SLIs, and alerts of critical data.

## 3. Registering a Predicate on ObservationRegistry in Spring Boot

In Spring Boot using Micrometer Observation, the clean way to add a rule is via `ObservationRegistryCustomizer`, letting the framework continue configuring the registry and associated handlers.

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationPolicyConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> ignoreInternalHeartbeat() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) ->
                        !"internal.heartbeat".equals(name));
    }
}
```

Explanation:

1. The configuration adds the predicate to the registry that Spring Boot uses.
2. Observations named exactly `internal.heartbeat` are rejected; other names return `true` and remain active.
3. Exact `equals` comparison keeps the exclusion scope explicit; it avoids accidentally dropping `internal.heartbeat.failed` or `internal.heartbeat.recovery` if those are distinct important operations.
4. No exporter call or network access is needed inside the predicate. The rule relies purely on local data, making it lightweight, testable, and consistent.

To test the decision in application code:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class HeartbeatService {
    private final ObservationRegistry registry;

    public HeartbeatService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void sendHeartbeat() {
        Observation.createNotStarted("internal.heartbeat", registry)
                .observe(this::actuallySendHeartbeat);
    }

    private void actuallySendHeartbeat() {
        // Heartbeat task still executes even if the observation is rejected.
    }
}
```

In a Spring Boot application, this registry must be accompanied by appropriate handlers/bridges/exporters to produce observable metrics or traces. If you create `ObservationRegistry.create()` in a standalone program without registering handlers, even allowed observations **will not automatically export metrics/traces**.

### Multiple Coexisting Predicates

An application may have predicates from application config, integrated libraries, or multiple customizers. **A single rule returning `false` is enough to reject the observation**, so review active rules together. Do not design predicate A expecting predicate B to "re-enable" an observation rejected by A.

If you write a prefix-based predicate (such as `name.startsWith("http.")`), verify its scope carefully: it could disable both client and server observations responsible for trace propagation and essential metrics.

## 4. Filtering by Context: Using Data Known at Observation Creation

`ObservationPredicate` also receives `Observation.Context`, enabling richer decisions than name matching alone. The critical condition is that **information used for filtering must already be available when the predicate is evaluated**. Do not rely on labels added after `start()`, after returning a result, or after an exception is thrown.

Suppose a system has a `job.execute` job of two types: `business` and `housekeeping`. This environment already has separate metrics for housekeeping and wants to retain observations only for business jobs:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

final class JobObservationContext extends Observation.Context {
    private final String jobType;

    JobObservationContext(String jobType) {
        this.jobType = jobType;
    }

    String jobType() {
        return jobType;
    }
}

@Configuration(proxyBeanMethods = false)
class JobObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> jobObservationPolicy() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) -> {
                    if (!"job.execute".equals(name)) {
                        return true;
                    }
                    if (context instanceof JobObservationContext jobContext) {
                        return !"housekeeping".equals(jobContext.jobType());
                    }
                    // Unrecognized context: prefer keeping telemetry.
                    return true;
                });
    }
}

class JobRunner {
    private final ObservationRegistry registry;

    JobRunner(ObservationRegistry registry) {
        this.registry = registry;
    }

    void execute(String jobType, Runnable task) {
        Observation.createNotStarted(
                "job.execute",
                () -> new JobObservationContext(jobType),
                registry)
            .observe(task);
    }
}
```

In this pattern, `jobType` is known **before running the job**, so it can be placed into the context at observation creation time. If the job type were only inferred after execution, a predicate could not decide based on that information.

**Caution with framework instrumentation:** HTTP server, HTTP client, or messaging contexts have different types and available data depending on the technology. Do not cast contexts without checking, and do not assume URLs, request bodies, or business outcomes are always present. If you want to exclude health probes by HTTP path, use the exact request context type of your framework/version, inspect normalized URIs, and test both valid and error paths. An observation named `http.server.requests` can cover many endpoints; filtering purely by name will drop *all* HTTP server observations under that name.

## 5. How Does It Differ from ObservationFilter, MeterFilter, and Trace Sampling?

These four mechanisms are easily confused because all of them can alter observable data:

| Mechanism | Decision Scope | When to Use |
| --- | --- | --- |
| **`ObservationPredicate`** | Chooses whether an observation is active at creation time | When you want to exclude a type of observation from the observation pipeline |
| **`ObservationFilter`** | Adds or modifies context/key-values of processed observations | When you want to attach standard metadata or adjust tags/context; not for enabling/disabling |
| **`MeterFilter`** | Controls meters/tags in `MeterRegistry` | When you want to deny/cap meters or adjust metric labels; tracing can keep running |
| **Trace sampling** | Decides which traces/spans are recorded or exported by a sampler | When you want to reduce tracing volume while keeping metrics and propagation behavior per config |

Examples of different decisions:

- **"We no longer need to observe this heartbeat."** Use `ObservationPredicate` if losing all signals from that observation is acceptable.
- **"Keep `payment.authorize` but add tag `service.tier=gold`."** Use a convention/filter or attach the tag at instrumentation time with a controlled value set.
- **"Metric `http.server.requests` has a label carrying order IDs causing a cardinality explosion."** Remove or normalize the label at the source; `MeterFilter` can also protect the metric registry. A predicate dropping the entire observation would lose too much signal.
- **"Only export 10% of distributed traces, but keep full metrics."** Use appropriate tracing sampling configuration; do not use a predicate as a sampler.

### Why Not Replace Trace Sampling with a Random Predicate?

A predicate returning `Math.random() < 0.1` to let only 10% of observations run may sound economical, but it distorts metrics, breaks parent/child trace chains, and makes log/trace correlation hard to explain. Distributed tracing requires **consistent sampling and propagation decisions across services**. Use the tracing system's sampler; if you want to drop an entire observation type semantically, use an explicit predicate.

## 6. Impact on Metrics, Logs, and Distributed Tracing

For an observation registered with both a metric handler and a tracing handler, a predicate returning `false` can cause **both the metric and the span produced by that observation not to appear**. This differs from a trace not being sampled or an exporter failing to deliver data.

Suppose a payment flow is:

```text
HTTP server observation: http.server.requests
  └─ Business observation: payment.authorize
       └─ HTTP client observation: http.client.requests
```

If `payment.authorize` is rejected, the business boundary disappears from the trace; the HTTP client observation may still exist, but parent/child relationships depend on whichever context remains active. If `http.server.requests` is rejected, the application may lose the root span for the request along with related HTTP metrics, impacting SLIs, alerts, and log/trace correlation. On a real system, verify the complete flow instead of guessing from a diagram.

A predicate **does not disable application logging**: normal log statements still execute. However, logs carrying `traceId`/`spanId` via tracing and MDC correlation may no longer have the same context if the observation providing the span was dropped. That is why the relationship across all three signals must be considered, especially when investigating errors and latency.

Regarding context propagation, predicates do not propagate or restore context. If an observation is kept active but work moves to another executor, an appropriate framework/Micrometer propagation mechanism is required. Filtering an observation at an entry boundary can affect spans and baggage propagated downstream; verify with downstream services.

## 7. Practices for Designing Safe, Operable Predicates

### 7.1. Start with a Narrow Exclusion List

Prefer matching the **exact names** of observations you explicitly create. For framework observations, inspect actual names, conventions, and contexts before modifying anything. Avoid broad blacklists like `contains("http")` or `startsWith("spring")` without listing every affected signal.

### 7.2. Do Not Use Predicates to Cure Cardinality

High cardinality typically comes from tags/attributes like `userId`, `orderId`, emails, unnormalized paths, exception messages, or query parameters. A predicate does not solve the root cause if you still need metrics/traces for that operation. Design low-cardinality tags with small, bounded value sets; use high-cardinality details only in traces/logs according to security policies and volume limits.

Example of a stable label set:

| Label | Typical Values | Notes |
| --- | --- | --- |
| `operation` | `authorize`, `capture`, `refund` | Fixed set of operations |
| `outcome` | `success`, `declined`, `error` | Distinguishes business outcome from system error |
| `provider` | `provider_a`, `provider_b` | Normalized to supported providers |
| `order_id` | Distinct value per order | **Do not** use as a low-cardinality metric tag |

### 7.3. Keep Predicates Lightweight and Purely Decision-Based

Predicates execute on the application's instrumentation path, potentially very frequently. Inside `test(name, context)`, avoid DB queries, network calls, external config reads, long locks, or frequent logging. Prefer cheap, side-effect-free checks. If rules need to vary by environment, initialize configuration into a stable value beforehand and control runtime updates carefully.

### 7.4. Fail Open on Unrecognized Contexts

When a predicate inspects a subtype of `Observation.Context`, return `true` if the context is not the expected subtype, unless explicitly required otherwise. This prevents silent telemetry loss when instrumentation changes after a library upgrade or when another source uses the same observation name.

### 7.5. Evaluate Impact Before Deploying

Before filtering, inventory dashboards, alerts, SLIs/SLOs, log correlation, and traces that rely on that observation. Confirm whether dropping the metric/span is acceptable and adjust alerts if those metrics will stop being emitted. In multi-instance deployments, ensure policies are consistent or configuration differences are clearly understood.

## 8. Verifying with Concrete Scenarios

Example policy: reject `internal.heartbeat` and retain `payment.authorize`. Test at least the following cases in an environment with handlers/exporters configured:

| Scenario | Expected Outcome |
| --- | --- |
| Run heartbeat named `internal.heartbeat` | Heartbeat logic still executes; no new signals generated by this observation |
| Run successful `payment.authorize` operation | Observation is active and processed by metric/tracing handlers as configured |
| `payment.authorize` throws an exception | Business exception is not swallowed by the predicate; error handler still runs if instrumentation records the error |
| `internal.heartbeat.failed` is a different observation | Still allowed if exact name matching is used as in the example |
| `housekeeping` job with `JobObservationContext` | `job.execute` observation is dropped; job still executes |
| `business` job or unrecognized context | `job.execute` observation is retained |
| Multiple predicates exist | One rejecting predicate makes the observation inactive; no later rule "re-enables" it |
| Low tracing sampling | Do not infer the predicate rejected it just because a span is missing; cross-check metrics, sampling, and exporter |

Keep verification layers separate:

1. **Application behavior:** code inside `observe(...)` runs correctly and exceptions propagate as before.
2. **Registry and handlers:** which observations are allowed and which become no-ops.
3. **Output signals:** metrics and spans appear/disappear as expected after exporter, scrape, sampling, and backend filtering.
4. **End-to-end investigation:** requests can be traced across services, log correlation works, and alerts backed by essential metrics still receive data.

If a metric is missing from a dashboard, do not immediately blame the predicate. Also inspect the metric handler, `MeterRegistry`, exporter config, scrape setup, naming conventions, and aggregation window. Likewise, missing spans can result from sampling or missing tracing bridge/context propagation.

## 9. Practical Scenario: Reducing Noisy Telemetry While Keeping Debuggability

A Spring Boot order-processing system has three observations:

```text
internal.heartbeat      (very high volume, replaced by another health metric)
order.confirm           (tied to order confirmation SLO)
payment.authorize       (tied to provider errors/latency)
```

The operations team wants to reduce overhead while still answering: *how many orders failed? is order confirmation slow? which provider is slow? what steps did a failed request trace go through?*

Appropriate design:

1. Use a predicate to reject only `internal.heartbeat` after confirming another health metric meets operational needs.
2. Keep `order.confirm` and `payment.authorize` so latency/error metrics and business spans remain available.
3. Standardize low-cardinality tags such as `outcome` and `provider`; keep order IDs out of metric labels.
4. Use trace sampling to bound distributed tracing volume while preserving propagation.
5. Compare before/after observation/span counts and metric time series, and run real failure scenarios to confirm issues remain investigable.

**Key takeaway:** `ObservationPredicate` is **a gate that allows or rejects an entire observation**. Use it for truly unnecessary signals, preserve the observations underlying SLIs, metrics, log correlation, and distributed tracing, and use purpose-built mechanisms for tag adjustments, cardinality control, or trace sampling.
