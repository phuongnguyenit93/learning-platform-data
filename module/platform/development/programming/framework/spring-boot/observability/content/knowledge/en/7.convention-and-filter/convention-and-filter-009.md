# Dropping unnecessary observations in Spring Boot

In the **Convention and filter** chapter of the **SPRING_BOOT_OBSERVABILITY** module, an important part of observability design is knowing **when not to create telemetry**. Spring Boot combines Micrometer Observation with metrics, logs, and distributed tracing to help investigate errors, latency, service dependencies, and application behavior. Yet not every operation needs its own observation: an internal heartbeat firing hundreds of times per second, a harmless polling task, or an observation duplicating the exact same boundary can add overhead and clutter dashboards and traces.

**Dropping unnecessary observations** is a deliberate choice grounded in operational value, not reducing data by turning everything off. Keep the signals that underpin SLIs/SLOs, incident investigation, and metrics–logs–traces correlation, while dropping only observations that answer no new questions.

## 1. What counts as an unnecessary observation?

An Observation is Micrometer's unit of measurement, with a name, context, `start/stop` lifecycle, and handlers that can produce metrics or spans. An observation can be considered unnecessary **for a specific system and operational goal** if:

- The exact same boundary is already reliably instrumented elsewhere, so the new observation only measures duplicate semantics.
- The operation happens at very high frequency, yet per-execution latency, errors, and causal relationships are never used.
- A more reliable signal source already exists for the question being asked, such as an aggregated health metric instead of every technical heartbeat tick.
- The resulting telemetry serves no dashboard, alert, SLI/SLO, or incident analysis, with no reasonable near-term need.

You cannot infer "unnecessary" solely from **high frequency**. A payment endpoint receiving heavy traffic remains critical for measuring p95 latency, error rate, and cross-service trace relationships. Conversely, a rare job that corrupts data may need an exact observation on every execution.

| Activity | Initial assessment | Question before dropping |
| --- | --- | --- |
| `internal.heartbeat.tick` signaling an internal loop is alive | **Candidate to drop** if another health/availability metric exists | Can we still detect if the heartbeat stalls or repeatedly fails? |
| HTTP server observation for `POST /checkout` | **Should keep** | Do RED dashboards, SLOs, and alerts depend on it? |
| Custom span wrapping the exact same already-instrumented HTTP client call | **Candidate to drop duplicate** | Does this span add an independent business boundary? |
| `inventory.reserve` representing the stock reservation step | **Usually should keep** | Does it isolate business step latency/exceptions from overall HTTP? |
| Individual "queue empty" checks of a poller | **Can be reduced** | Are there reliable queue-depth metrics, poll counts, and error alerts? |
| Consumer failing message processing and retrying | **Caution, usually should keep** | If dropped, can we still investigate retries, dead-letters, and latency? |

A good decision states clearly **which observation is dropped**, **which signal replaces it**, and **which investigative questions remain answerable**.

## 2. Why reduce noisy telemetry?

Dropping unnecessary observations can bring three benefits, though actual savings depend on handlers and exporters:

1. **Lower processing volume:** fewer callbacks/records generated from dropped observations; less data sent to tracing or metrics backends if that observation was the signal source.
2. **Lower storage/query cost:** fewer unhelpful spans and time series. Note, however, that metrics cost also depends on **tag combination counts**, not just request or observation volume.
3. **Higher signal-to-noise ratio:** traces highlight important business steps, dashboards carry fewer redundant series, and engineers locate root causes faster.

For example, suppose a poller runs 40 times/second across 20 instances: in one minute there are **40 × 20 × 60 = 48,000 polls**. If every poll emits a span even when the queue is empty, the tracing backend can receive huge span volume with low diagnostic value. A gauge showing queue depth, a counter tracking poll errors, and an observation when *work is actually processed* may deliver better signal.

This is only an operation count calculation, **not an exact estimate of exported spans**: sampling, handlers, exporters, and instrumentation itself can alter exported volume. Measure before and after in a real deployment environment.

## 3. Primary mechanism: ObservationPredicate

In Spring Boot using Micrometer Observation, `ObservationPredicate` is the right mechanism when you need to **reject an entire observation**. Predicates are registered on `ObservationRegistry` and return a decision based on observation name and context:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;

ObservationPredicate predicate =
        (String name, Observation.Context context) ->
                !"internal.heartbeat.tick".equals(name);
```

Conceptually:

```text
Instrumentation creates observation
          |
          v
ObservationPredicate.test(name, context)
          |
          +-- true  --> observation is active
          |             --> handlers can record metrics, spans, ...
          |
          +-- false --> observation becomes a no-op
                        --> no telemetry emitted from that observation
                        --> business code wrapped by observe(...) still runs
```

**A no-op observation does not skip business logic.** A predicate controls telemetry; it does not stop tasks, block HTTP requests, alter return values, or automatically suppress logs explicitly written by the application. Independent meters/spans created by other libraries can also remain.

Predicates decide whether an observation **participates in the observation lifecycle**. They do not offer a per-signal toggle such as "disable tracing only, keep metrics" or "disable metric only, keep tracing" for the same observation. To filter per signal, use each signal system's dedicated mechanism.

## 4. Spring Boot example: dropping an internal heartbeat

Suppose the application has an observation named `internal.heartbeat.tick` marking an active technical loop. This loop already has an aggregated health/availability metric and a reliable alert; per-tick duration/spans are unnecessary.

Register a predicate via `ObservationRegistryCustomizer` to add it to the Spring Boot-managed registry:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationNoiseConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> dropHeartbeatTick() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) ->
                        !"internal.heartbeat.tick".equals(name));
    }
}
```

This rule rejects **only one exact name**. It does not reject `internal.heartbeat.failure` if the application has a separate observation for failures, nor does it directly affect other observations like `payment.authorize`.

Example instrumentation in a service:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class HeartbeatService {
    private final ObservationRegistry observationRegistry;

    public HeartbeatService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void tick() {
        Observation.createNotStarted(
                "internal.heartbeat.tick", observationRegistry)
                .observe(this::runHeartbeat);
    }

    private void runHeartbeat() {
        // Actual work still runs when predicate rejects observation.
    }
}
```

Once applied, `runHeartbeat()` still runs. The `internal.heartbeat.tick` instrumentation no longer contributes metrics/spans through normal observation handlers. If the service increments a `Counter` or logs directly inside `runHeartbeat()`, those **independent** signals do not automatically disappear.

**Limitation of the example:** to verify metrics and spans actually decrease, the environment must have the corresponding observation handlers, registries, and exporters. Running code against a bare `ObservationRegistry.create()` without handlers will not demonstrate backend differences.

## 5. Filtering by context without accidentally dropping critical work

Sometimes one observation type covers both low-value background checks and critical work. Matching solely by name would be too broad; instead use a **strongly typed context** created alongside the observation.

Suppose a poller has two modes determined **before execution**:

- `HEARTBEAT`: a technical check already covered by an aggregated metric.
- `BUSINESS_SYNC`: an important data sync requiring latency, error, and trace visibility.

Define the context:

```java
import io.micrometer.observation.Observation;
import java.util.Objects;

enum PollMode {
    HEARTBEAT, BUSINESS_SYNC
}

final class PollObservationContext extends Observation.Context {
    private final PollMode mode;

    PollObservationContext(PollMode mode) {
        this.mode = Objects.requireNonNull(mode);
    }

    PollMode mode() {
        return mode;
    }
}
```

The predicate only rejects `integration.poll` if the context matches the type and `mode == HEARTBEAT`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PollObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> pollPredicate() {
        return registry -> registry.observationConfig()
                .observationPredicate((name, context) -> {
                    if (!"integration.poll".equals(name)) {
                        return true;
                    }
                    if (context instanceof PollObservationContext poll) {
                        return poll.mode() != PollMode.HEARTBEAT;
                    }
                    // Unknown context: keep observation to avoid losing signals.
                    return true;
                });
    }
}
```

Code creating the observation:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class IntegrationPoller {
    private final ObservationRegistry registry;

    public IntegrationPoller(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void poll(PollMode mode, Runnable action) {
        Observation.createNotStarted(
                "integration.poll",
                () -> new PollObservationContext(mode),
                registry)
                .observe(action);
    }
}
```

Here, `mode` is known as soon as the observation is initialized. **Do not use outcomes known only after processing** (such as "was the queue empty?" once polling completes) inside a predicate expecting it to wait until the end of the lifecycle. To analyze `outcome=empty/processed/error`, keep the observation and record outcome once known, or redesign the boundary to start an observation only when actually processing a message.

Never cast HTTP server, HTTP client, or messaging contexts blindly. Integrated contexts vary in properties across frameworks and versions. In particular, a name like `http.server.requests` is often shared across **many endpoints**: a predicate matching only that name can disable every HTTP server observation, including business endpoints.

## 6. Distinguishing predicates from conventions, filters, and sampling

These tools solve different problems:

| Mechanism | Primary effect | Good fit |
| --- | --- | --- |
| **`ObservationPredicate`** | Decides whether to enable **the entire observation** | Dropping `internal.heartbeat.tick` |
| **`ObservationConvention`** | Standardizes name, contextual name, low/high-cardinality key-values | Sharing `inventory.reserve` across call sites |
| **`ObservationFilter`** | Enriches or adjusts context/key-values during the observation lifecycle | Adding a shared finite-value tag across observations |
| **`MeterFilter`** | Controls meters and tags in `MeterRegistry` | Denying a specific metric or bounding tag cardinality |
| **Tracing sampler** | Decides which traces/spans are recorded or exported, per tracing setup | Reducing trace rate under heavy load |
| **Collector/exporter filter** | Filters or transforms telemetry downstream of instrumentation | Restricting data sent to a specific backend |

Three easily confused requirements:

1. **"We no longer need heartbeat duration/spans."** A predicate fits if you agree to drop the signals emitted by that observation.
2. **"We still need 100% of metrics, but only export a fraction of distributed traces."** Use tracing sampling, never a random predicate.
3. **"We need the observation, yet a customer ID tag is inflating time series."** Fix the tag source, convention/filter, or use an appropriate `MeterFilter`. Dropping the whole observation loses useful latency and error metrics.

### Why not use a predicate for random sampling?

The following snippet is an **anti-pattern** and must not replace a tracing sampler:

```java
// Avoid: random decision for the whole Observation.
registry.observationConfig()
        .observationPredicate((name, context) ->
                java.util.concurrent.ThreadLocalRandom.current()
                        .nextDouble() < 0.10);
```

It drops both metrics and spans from the observation, making aggregated counts incomplete while making parent/child trace relationships and propagation hard to reason about. Tracing samplers exist specifically to make trace-consistent sampling decisions alongside cross-service context propagation. Predicates should rely on **clear semantic rules** that rarely change and are easy to verify.

## 7. Special care with HTTP health checks

Health probes are a frequent target when reducing repetitive telemetry, yet decisions must account for how Spring Boot instruments HTTP:

```text
Load balancer / Kubernetes probe
         |
         v
GET /actuator/health
         |
         +--> HTTP server observation (may share the same name with other endpoints)
         |
         +--> Actuator health logic
```

Never add a predicate like `name.equals("http.server.requests") ? false : true` just to "drop health checks," because that observation name can cover **all** HTTP requests. Understand the actual context, when path information becomes available, and framework conventions before filtering by route.

Sensible options by goal:

- If you only want **quieter dashboards**, filter out health routes in queries or panels. Data remains intact when needed for investigation.
- If you want to **reduce traces**, configure endpoint-aware sampling/tracing or policies supported by your tracing stack while preserving context propagation.
- If you truly want to **drop health-route telemetry at the source**, confirm how your instrumentation/version identifies that route, inspect the normalized path, and verify business request metrics/spans remain unaffected.
- If health checks are an important availability signal, keep an appropriate aggregated metric instead of dropping everything and losing alerting visibility.

Rule: **never infer endpoint names from a generic observation name**. Route and request metadata may not even exist yet when a predicate evaluates; verify against a live application rather than assuming from an example.

## 8. Consequences for metrics, logs, and distributed tracing

When an observation feeds both metrics and spans via handlers, rejecting it can drop **both signals**. You cannot assume dropping affects only charts without impacting traceability.

Consider this flow:

```text
POST /checkout                 [HTTP server observation]
    |
    +-- inventory.reserve      [custom business observation]
    |      |
    |      +-- database call   [depends on instrumentation]
    |
    +-- payment.authorize      [custom business observation]
           |
           +-- HTTP client     [depends on instrumentation]
```

If you drop `inventory.reserve` because "there is already an SQL span," you lose visibility into the **business inventory reservation step**, whereas the SQL span only reflects raw database calls. Conversely, if a custom observation merely wraps an already-instrumented HTTP client call without adding domain semantics, dropping that redundant wrapper can clean up traces.

**Metrics:** many SLIs depend on operation duration and error rates. Before dropping an observation, check dashboards, alerts, and p95/p99 queries. Predicates do not reconstruct lost metrics; independent counters/gauges remain or vanish depending on where they are instrumented.

**Traces:** dropping a span can remove a semantic transition point. Child spans or upstream/downstream spans may still be created if independently instrumented, though parent/child linkage and trace details depend on active context, sampling, and propagation.

**Logs:** predicates do not stop `logger.info(...)` or `logger.error(...)` in business code. However, logs carrying `traceId`/`spanId` via tracing and MDC correlation may behave differently when the observation supplying the span is dropped. Verify you can still jump from an error log to its related trace.

**Async/queue propagation:** if processing runs on an executor or message consumer, an observation scope on the original thread does not automatically propagate context. Cross-service investigation requires Micrometer Context Propagation, framework instrumentation, and the right trace propagator. Never disable observations to mask propagation failures.

## 9. Designing controlled exclusion rules

### 9.1. Stable names and narrow scope

Prefer allow/deny rules on **exact application-owned names** like `internal.heartbeat.tick`. Avoid broad expressions like `startsWith("http")` or `contains("health")` unless you know every observation that might match. An overly broad rule can silently erase business endpoint telemetry during a deployment.

### 9.2. Control context and information order

Predicates should read only data guaranteed to exist at evaluation time. Use a dedicated typed context when filtering custom operations; for unrecognized contexts, normally **keep the observation** to avoid losing signals after dependency upgrades.

### 9.3. Multiple predicates

A registry may be configured by multiple customizers or libraries. If any active predicate rejects an observation, another rule cannot reliably "re-enable" it. Document the owner and purpose of every rule so two components do not impose conflicting allow/deny logic.

### 9.4. Keep the instrumentation path lightweight

Predicates can run very frequently. Keep them to fast comparisons or reading an existing context field; avoid DB calls, network requests, long locks, complex regexes, or per-call logging. A heavy predicate can add noticeable latency on hot request paths.

### 9.5. Do not use exclusion to hide cardinality issues

Low-cardinality tags must have finite value sets, such as `outcome=success/declined/error` or `provider=a/b/c`. Never put `userId`, `orderId`, emails, raw URLs, query strings, or exception messages into time-series labels. When per-request detail is required, use selective trace/log attributes governed by security policies; keep tokens and sensitive data out of telemetry.

## 10. Before-and-after evaluation and verification process

When preparing to exclude an observation, follow these steps:

1. **Define the operational question:** what must the system detect or investigate? E.g., "Is the poller stuck?" or "Did payment authorize p95 spike?"
2. **Inventory existing signals:** which metrics, logs, spans, alerts, SLOs, and dashboards consume the observation slated for removal? Does a reliable replacement signal exist?
3. **Specify the exact target:** stable observation name, context, and when data becomes available; choose a predicate or another mechanism fitting the requirement.
4. **Estimate the benefit:** before/after observation/span/time-series counts, latency/CPU overhead, retention, and exporter/backend costs.
5. **Test success and error paths:** verify business logic still runs, errors remain observable, and critical operations are not dropped by mistake.
6. **Verify correlation:** from an alert or error log, can you still find the metric/trace and identify root cause across services?
7. **Monitor during rollout:** compare telemetry volume, alerts, and investigation readiness; keep a rollback plan if signals are missing.

### Test matrix for the sample policy

Assuming the name-based predicate from section 4 and context-based predicate from section 5 are registered:

| Scenario | Business outcome | Expected signal |
| --- | --- | --- |
| `internal.heartbeat.tick` | Heartbeat loop keeps running | Observation rejected; no metrics/spans emitted **by this observation** |
| `internal.heartbeat.failure` | Error-handling logic still works | Differently named observation is kept unless excluded by another rule |
| `integration.poll`, `HEARTBEAT` | Polling task still runs | Observation rejected |
| `integration.poll`, `BUSINESS_SYNC` | Sync job runs | Observation allowed; handlers can emit metrics/spans |
| `integration.poll`, unknown context | Logic still runs | Observation kept by default |
| `payment.authorize` success/error | Behavior and exceptions preserved | Observation continues measuring duration/errors |
| Sampled-out trace | Business behavior unchanged | Span may not be exported; **not enough** to conclude predicate dropped it |

To verify in a live environment, separate three layers:

- **Instrumentation:** with which name/context was the observation created, and how did the predicate decide?
- **Handlers/registry:** when allowed, are metrics/tracing handlers configured to process it?
- **Exporter/backend:** is data scraped or exported, or is it dropped/renamed by sampling, filtering, or backend ingestion?

An empty chart can result from Prometheus not scraping yet, an unconfigured exporter, trace sampling, unexpected tag names, or backend lag—not necessarily a predicate. Conversely, if a predicate dropped the observation, raising sampling to 100% will never bring that observation back.

## 11. End-to-end scenario: an order processing system

A Spring Boot service has these operations:

```text
HTTP POST /orders
  +-- inventory.reserve        (business operation)
  +-- payment.authorize        (business operation)
  +-- publishOrderEvent        (async / message)

background:
  +-- internal.heartbeat.tick  (high frequency)
  +-- integration.poll         (HEARTBEAT or BUSINESS_SYNC)
```

The operations team wants to reduce telemetry while still answering: "Did the order fail on payment or inventory?", "Where is the request slow?", and "Was the message processed after the HTTP response completed?"

A sound design keeps the HTTP server observation and business observations `inventory.reserve` and `payment.authorize`, keeps message processing instrumentation with context propagation, and drops `internal.heartbeat.tick` once another health metric meets the goal. For `integration.poll`, reject only the upfront-known `HEARTBEAT` mode while observing `BUSINESS_SYNC`.

Remaining tags should be normalized—such as `outcome=success/declined/error` and `provider=a/b`—without creating metric tags per order ID. To reduce trace volume, configure sampling separately; to adjust names/tags, use conventions/filters; to deny a specific meter while keeping traces, use the meter registry's mechanism.

**Key takeaway:** dropping an observation **must be an evidence-backed decision**. Use `ObservationPredicate` to exclude an entire observation by name/context, preserve valuable business boundaries, use the right tool for tags/cardinality and sampling, and verify that metrics–logs–traces remain sufficient to detect and investigate production incidents.
