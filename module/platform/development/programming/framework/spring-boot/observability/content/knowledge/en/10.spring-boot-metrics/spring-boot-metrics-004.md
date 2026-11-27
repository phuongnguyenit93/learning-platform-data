# Global Registry in Spring Boot Metrics: How It Works, Configuration, and Risks

> **Chapter:** Spring Boot metrics  
> **Lesson:** Global registry  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What problem does the global registry solve?

A Java library wants to count how many messages it sends, without forcing every application using the library to pass a `MeterRegistry` object through every constructor. Micrometer provides a static entry point:

~~~java
import io.micrometer.core.instrument.Metrics;

Metrics.counter("library.messages.sent", "result", "success")
       .increment();
~~~

This call creates or retrieves a `Counter` through Micrometer's **global registry**. The library only depends on the Micrometer API; the runtime environment decides which concrete registry receives the data.

In a Spring Boot application, metrics are normally managed through a **`MeterRegistry` bean** injected via dependency injection. When supported by auto-configuration, those registries can also be linked to the global registry. Thus, two API styles can coexist:

~~~java
// Static style:
Metrics.counter("demo.events", "result", "ok").increment();

// Spring injection style:
meterRegistry.counter("demo.events", "result", "ok").increment();
~~~

Key point: these two calls **do not mean** there are two different backends. In a typical Spring Boot configuration, both can reach the same target registry. If you call `increment()` on both for **a single event**, you have measured that event twice.

**Learning objectives:** understand what `Metrics.globalRegistry` is, how it differs from the `MeterRegistry` bean, how Spring Boot connects the two, how to enable/disable global registration, when to use the static API, and how to diagnose real-world issues such as doubled counts, missing metrics, wrong registries, or state pollution in tests.

## 2. Registries and APIs to distinguish

| Concept | Nature | What is it used for? |
| --- | --- | --- |
| `MeterRegistry` | Base interface/type for managing meters | Register and use `Counter`, `Gauge`, `Timer`, `DistributionSummary`, `LongTaskTimer` |
| `Metrics.globalRegistry` | A **static, JVM-wide shared** `CompositeMeterRegistry` | Aggregation point for static APIs `Metrics.counter(...)`, `Metrics.timer(...)`... |
| `CompositeMeterRegistry` | Registry forwarding measurements to one or more child registries | Export the same measurement data to multiple compatible backends |
| `PrometheusMeterRegistry` | Registry implementation for Prometheus | Format metric output for Prometheus scraping |
| OTLP or other backend registry | Implementation for another backend | Send or expose data per that backend's mechanism |
| `ObservationRegistry` | Registry for **Micrometer Observation** | Orchestrate `Observation`, conventions, predicates, filters, and `ObservationHandler`s |
| Tracer and exporter | Distributed tracing components | Create, sample, and export spans; propagate trace context |

Some common misconceptions:

- **The global registry is not a company-wide monitoring server.** It is a static object inside **a single JVM**. Each process/instance has its own global registry; there is no direct state sharing across pods.
- **The global registry is not an exporter.** It holds meters and delegates measurements to child registries. Prometheus, OTLP, or other backends sit in subsequent layers.
- **The Metrics global registry is not a global ObservationRegistry.** `Metrics.counter(...)` is a metrics API, whereas `Observation.createNotStarted(..., observationRegistry)` uses the Observation lifecycle and handlers. Both can end up in the same `MeterRegistry`, but they are not the same API.
- **The global registry does not automatically link trace/log context.** Combining metrics, logs, and distributed tracing requires Micrometer Observation/Tracing, propagation, exporters, and suitable analysis backends.

## 3. Architecture: from the Metrics static API to the backend

~~~mermaid
flowchart TB
    subgraph APP["A Spring Boot process"]
      A["Library/legacy code using Metrics.counter(...)"]
      B["Spring service injecting MeterRegistry"]
      C["Custom Observation + Meter ObservationHandler"]
      D["Metrics.globalRegistry (static CompositeMeterRegistry)"]
      E["Spring Boot-configured MeterRegistry"]
      A --> D
      B --> E
      C --> E
      D -->|"When E is registered in global"| E
    end
    E --> F["PrometheusMeterRegistry"]
    E --> G["Other backend registry if present"]
    F --> H["/actuator/prometheus"]
    H --> I["Prometheus scrape"]
    I --> J["Dashboards and alerts"]
    G --> K["Corresponding exporter/backend"]
~~~

This diagram is a conceptual model: some applications have only one registry, while others have a composite registry combining multiple destinations; internal bean wiring is determined by auto-configuration. What matters is understanding that the **static** call path and the **injected** call path can converge on the same target registries.

When multiple backends exist, a single `counter.increment()` can be forwarded to each child registry so the data is stored in multiple systems. Exporting to two backends **does not inherently** double the count in each backend; it is one event represented in two places. Double counting happens when the same event is recorded **twice to the same measurement in the same backend**, or when data is ingested twice at the collection layer.

### An example

An application wants to record an order creation:

~~~java
meterRegistry.counter(
        "orders.created",
        "channel", "web"
).increment();
~~~

If that registry is also attached to the global registry, the following snippet will also affect the metrics system:

~~~java
Metrics.counter(
        "orders.created",
        "channel", "web"
).increment();
~~~

Putting **both** in the same execution path for one order will increment the counter by two for a single order creation. The purpose of global configuration is not to measure twice automatically; this happens because business code explicitly called it twice.

## 4. The `Metrics.globalRegistry` API

Micrometer has a utility class `io.micrometer.core.instrument.Metrics`, providing a global composite registry and static helper methods for accessing meters.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Timer;

Counter success = Metrics.counter(
        "jobs.completed",
        "outcome", "success"
);
success.increment();

Timer timer = Metrics.timer(
        "jobs.processing.duration",
        "operation", "import"
);
timer.record(() -> {
    // Perform the synchronous task to measure.
});
~~~

The calls above do not declare a destination on their own. For a metric to appear in a real backend, an appropriate registry must be attached to the composite, and that backend must be configured to export data.

### 4.1. Adding and removing child registries

In **standalone Java**, without Spring Boot auto-configuration, you can register a registry with global:

~~~java
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry local = new SimpleMeterRegistry();

Metrics.globalRegistry.add(local);
try {
    Metrics.counter("demo.jobs.done", "result", "ok")
            .increment();

    double count = local.get("demo.jobs.done")
            .tag("result", "ok")
            .counter()
            .count();

    System.out.println(count); // Example on a fresh registry: 1.0
} finally {
    Metrics.globalRegistry.remove(local);
    local.close();
}
~~~

`SimpleMeterRegistry` is suitable for small examples or in-memory tests. Here:

1. `Metrics.globalRegistry.add(local)` adds the child registry to receive subsequent measurements from the static API.
2. `Metrics.counter(...)` looks up or registers a Counter in the global composite.
3. `local.get(...).counter().count()` reads data **from the child registry**, making verification straightforward.
4. `remove(local)` detaches the child registry from global so it does not affect other code in the same JVM.
5. `close()` releases resources held by the registry created in the example.

**In Spring Boot with auto-configuration**, you usually do not need to write this manual `add(...)` block. Manually adding a registry that Boot already manages obscures ownership and can create duplicate export paths or inconsistent configuration. Identify the registry bean and default global configuration before intervening.

### 4.2. Mutating process-wide state

Because `Metrics.globalRegistry` is a static field, `add/remove` changes affect **all code in the same JVM** using the `Metrics.*` API. This is why "cleaning up the global registry" in one unit test can break another test running in parallel.

If a piece of code owns its own registry, only remove the registry it added itself. Never invoke operations that wipe the entire global registry in an application or shared test suite unless you control the entire process lifecycle.

## 5. Global registry in Spring Boot auto-configuration

In **Spring Boot 3.x** with Micrometer/Actuator, Spring Boot auto-configures `MeterRegistry` based on available dependencies and properties. Under standard Spring Boot 3.x integration, Boot auto-configured registries are **added to `Metrics`'s global static composite** by default; this behavior can be turned off via:

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

This property **controls linking Spring Boot-configured registries into global `Metrics`**. It does not disable all metrics in Spring Boot.

Important distinction to remember:

| State | `MeterRegistry` injected into bean | Static `Metrics.counter(...)` |
| --- | --- | --- |
| Global linked to Spring Boot registry | Measures via registry bean | Can write to that same target registry |
| `management.metrics.use-global-registry=false` | Still works via registry bean if metrics are configured | No longer writes automatically to that registry bean via global; only works with other registries if explicitly registered into global |
| No corresponding target registry | No target backend for export | Empty global composite exports no useful data |

**Version scope:** the property configuration above is illustrated for Spring Boot 3.x. When using a different Spring Boot version, check the configuration reference/metadata for your exact version before copying, as APIs and auto-configuration may change.

### When should you set `use-global-registry: false`?

This can be appropriate when an organization wants **all application code to record metrics through the Spring-injected `MeterRegistry`**, and intentionally avoids the global static path. Common reasons include:

- Easier test isolation because services depend only on the passed-in registry.
- Reduced reliance on JVM-wide static state across modules, libraries, and multiple application contexts.
- Clearer ownership over registry configuration, common tags, filters, and exporters.
- Avoiding unexpected metrics generated when libraries call static `Metrics.*` methods.

However, if a library relies on `Metrics.counter(...)`, disabling global without updating the library or configuring explicit registration can cause **the library's metrics to disappear from Spring Boot's registry**. Audit all static API usages before enabling this property in production.

Do not treat disabling global as a cure-all for double counting: if service code itself calls `meterRegistry.counter(...).increment()` twice, the count will still be wrong. You still have to fix the number of instrumentation calls at the business boundary.

## 6. Spring Boot practice: injected `MeterRegistry`

For Spring Boot code owned by your development team, **prefer constructor injection** so the registry is an explicit dependency that is easy to manage and test.

### 6.1. Maven dependencies

Example with Spring Boot 3.x managing dependencies via BOM/parent:

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

`spring-boot-starter-actuator` provides management and metrics integration. `micrometer-registry-prometheus` adds a Prometheus-formatted export registry. Different runtime dependencies can create different backends; this is purely an illustrative setup.

### 6.2. `application.yml` configuration

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
    use-global-registry: true
~~~

In this example:

- `metrics` is the endpoint for inspecting meters by name and tags; `prometheus` is the exporter endpoint when a compatible registry is present.
- `application=order-service` is a **common tag** to distinguish the application in a multi-service backend.
- `use-global-registry: true` is written explicitly to illustrate the relationship with the static global registry in Spring Boot 3.x. When you want to isolate the static API, change it to `false` after auditing `Metrics.*` usages.
- Restrict network/authorization access for Actuator endpoints, especially in production; do not leave management ports publicly open just for convenient scraping.

### 6.3. Service using the Spring-managed registry

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final MeterRegistry meterRegistry;

    public CheckoutService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void checkout(Runnable operation) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("orders.checkout.duration")
                    .description("Duration of checkout attempts")
                    .tag("outcome", outcome)
                    .register(meterRegistry)
            );
        }
    }
}
~~~

Each call to `checkout(...)` records **one duration sample** into the Timer matching the actual outcome. `outcome` has two bounded values, making it suitable for metrics tags. The `finally` block ensures a measurement is recorded even when business logic throws during normal execution.

A Timer already records call counts via its `count`; there is no need to add a second Counter just to count the same invocations unless it serves a distinct semantic purpose. If another business Counter is needed, define semantics clearly: `orders.created` is the count of orders **actually created successfully**, distinct from `orders.checkout.duration` which measures **checkout attempts**.

For asynchronous processing, do not stop the Timer immediately upon returning a future if the goal is to measure until the work completes; use completion callbacks and proper context propagation.

## 7. Comparing static calls vs. dependency injection

| Criterion | Global `Metrics.counter(...)` | Injected `MeterRegistry` |
| --- | --- | --- |
| How the registry is obtained | Via JVM static state | Constructor parameter or Spring bean |
| Coupling to Spring | Usable outside Spring | Explicitly depends on Spring context |
| Unit testing | Requires managing global state and cleaning up added registries | Can pass a dedicated `SimpleMeterRegistry` per test |
| Clarity of which backend receives data | Must inspect which registries are attached to global | Directly reflects the injected registry or application composite bean |
| Use in simple libraries | Convenient when unable to inject a registry | Better if library API allows passing a registry |
| Risks | Shared static state, early initialization, relies on auto-registration | Requires passing dependency through design |
| Sharing the same metric set | Possible, if global contains the injected registry | Possible, depending on global/composite config |

### Selection guidelines

- **New Spring Boot business code:** prefer injecting `MeterRegistry`, or use `ObservationRegistry` when instrumenting both metrics and tracing.
- **Libraries using Micrometer without Spring:** static `Metrics.*` can be convenient, though consider letting callers supply a registry instead of forcing reliance on global.
- **Legacy code already using static calls:** understand which backend it feeds before changing config. When refactoring to injection, remove the old static call at the same instrumentation point to avoid double counting.
- **Multiple applications/test contexts in one JVM:** minimize global state or manage lifecycle carefully.

The global registry is not inherently bad or wrong. It is a tool with **JVM scope** and specific usage conditions. What matters is knowing who owns the registry, who registers it, and ensuring each metric is recorded the exact right number of times.

## 8. What happens if the global registry has no child registries yet?

This is a common pitfall that causes silent data loss during application startup. Look at this code:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;

public final class EarlyMetrics {
    private static final Counter STARTED =
            Metrics.counter("service.start.attempts");

    public static void markStarted() {
        STARTED.increment();
    }
}
~~~

If this class initializes and `markStarted()` is called **before any child registry is added to global**, measurements performed while the global composite has no target registry have nowhere to go; they are not replayed as historical events when a registry later appears.

Once a registry is added later, new measurements can be forwarded per the composite mechanism. However, **missed values do not retroactively appear** in the backend.

In Spring Boot, static code blocks, static initializers, very early bootstrap hooks, or libraries loaded before the context is ready can encounter this situation. Never rely on early-startup counts via global as a guaranteed record of every event before the metrics system is ready.

How to handle this:

1. If an event requires strict accuracy, record it in a durable business system or appropriate event store; metrics are not a transactional event log.
2. In Spring code, instrument where services receive `MeterRegistry` and the application has initialized the required metrics infrastructure.
3. If a library must use static global, accept and document the pre-registry window or provide a controlled early registration hook.
4. Do not "patch" it by creating a new static registry inside a service and assuming Boot will automatically use it.

## 9. Global registry vs. `CompositeMeterRegistry`: how do multiple backends differ?

A `CompositeMeterRegistry` holds multiple child registries. Picture it as:

~~~mermaid
flowchart LR
    A["Counter/Timer via CompositeMeterRegistry"] --> B["Prometheus registry"]
    A --> C["OTLP or other backend registry"]
    B --> D["Prometheus scrape"]
    C --> E["Collector / monitoring backend"]
~~~

When a child registry is added, the composite links meters according to Micrometer's implementation; from then on, a new measurement call is forwarded to the child registries.

Suppose `orders.checkout.duration` has series in both backend A and backend B. The figures in **each backend** represent the same checkouts (as configured). Do not sum totals across both backends to get actual checkouts; they are two copies of the same signal in two storage systems.

### Common duplication scenarios

- **The same source is scraped twice** with different labels and a dashboard sums both targets: a collection error, not a global registry bug.
- **The application calls both static and injected APIs for the same event:** an instrumentation bug; it can double-count in the same target registry.
- **Two Observation handlers perform the same meter responsibility on one observation:** a handler registration bug.
- **Exporting the same metric to multiple backends:** usually intentional when two storage destinations are desired; not an error within each backend by itself.

If numbers look off, identify which layer is causing duplication before deleting or altering composites—fixing the wrong layer can cause monitoring data loss.

## 10. How does the global registry differ from `ObservationRegistry` and tracing?

Spring Boot observability is not just metrics. With Micrometer Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation observation = Observation.createNotStarted(
        "orders.checkout", observationRegistry)
    .lowCardinalityKeyValue("operation", "create")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    performCheckout();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

This snippet uses `ObservationRegistry`, not `Metrics.globalRegistry` directly. When a **Meter ObservationHandler** is present in the registry, the Observation can be converted into a Timer or other metric in the corresponding `MeterRegistry`. When a **Tracing ObservationHandler** is present, the same Observation can create a span, propagate context, and be exported along the tracing pipeline.

Meanwhile:

~~~java
Metrics.counter("orders.checkout.attempts").increment();
~~~

is a direct Counter measurement. It **does not automatically create a tracing span**, generate a trace ID, or carry the current observation across threads. To combine metrics, logs, and tracing, use the respective APIs and configurations for each signal.

Some OpenTelemetry stacks also have their own concept of a global tracer/provider. That is a **different mechanism** from Micrometer's `Metrics.globalRegistry`; do not let the word "global" lead you to assume the two objects are related or share state.

### Cardinality and sampling

- Meter handlers normally use low-cardinality tags to group metrics into finite buckets.
- High-cardinality metadata like `orderId` or `requestId` may belong in access-controlled spans/logs, but should **never** become metric labels via static or injected `MeterRegistry`.
- Tracing uses sampling: only a subset of requests may have exported traces. Metrics can count every request without shrinking according to trace sampling.
- The global registry **does not configure trace sampling** and does not propagate trace context between services.

## 11. Verifying with Spring Boot Actuator

To check whether the global registry is connected to Spring Boot's registry, you can create a simple test trigger in a development environment and inspect the metric in the target registry. Avoid leaving test endpoints like this publicly exposed in production.

Example Spring component:

~~~java
import io.micrometer.core.instrument.Metrics;
import org.springframework.stereotype.Component;

@Component
public class GlobalMetricsProbe {
    public void emitOneEvent() {
        Metrics.counter(
                "demo.global.events",
                "source", "static_api"
        ).increment();
    }
}
~~~

After invoking `emitOneEvent()`, check:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/demo.global.events
curl http://localhost:8080/actuator/prometheus
~~~

With a configured Prometheus registry, the Counter may be exported as a series like `demo_global_events_total`. Rely on the **actual names in the output**, because exporter conventions can alter names, suffixes, and units.

### Comparing the two modes

**Mode A — using global:**

~~~yaml
management:
  metrics:
    use-global-registry: true
~~~

Invoke `emitOneEvent()` and check whether the Counter appears in Boot's registry and exporter.

**Mode B — disabling global linking:**

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

Restart a clean process with this configuration, invoke the same method, and inspect Boot's registry. Unless another registry was manually attached to global, metrics from `Metrics.counter(...)` will **no longer flow via auto-registration** into Boot's registry.

For comparison, record another Counter via an injected `MeterRegistry`. With global disabled, the Counter through the injected registry will still export normally. This provides direct evidence to distinguish "global connection disabled" from "metrics disabled entirely".

**Practical note:** global state is JVM-scoped, so test across two separate processes or ensure thorough state cleanup; changing a property on a running instance does not necessarily detach previously registered registries.

## 12. Testing in unit tests and integration tests

### 12.1. Unit test using an isolated registry

When a service receives `MeterRegistry` via constructor injection, you can test with a standalone `SimpleMeterRegistry` without touching global:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
CheckoutService service = new CheckoutService(registry);

try {
    service.checkout(() -> {
        // Simulate a successful checkout.
    });

    double count = registry.get("orders.checkout.duration")
        .tag("outcome", "success")
        .timer()
        .count();

    if (count != 1.0) {
        throw new AssertionError("Expected exactly one checkout sample");
    }
} finally {
    registry.close();
}
~~~

This verifies **measurement semantics**: one execution records one Timer sample. No Spring startup or exporter is needed to prove that logic.

### 12.2. Tests forced to use global

If you must test a library using the static API, create a temporary registry, add it to global, and always remove it when finished:

~~~java
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
Metrics.globalRegistry.add(registry);

try {
    Metrics.counter("demo.test.operations", "outcome", "success")
            .increment();

    double actual = registry.get("demo.test.operations")
            .tag("outcome", "success")
            .counter()
            .count();

    if (actual != 1.0) {
        throw new AssertionError("Expected exactly one operation");
    }
} finally {
    Metrics.globalRegistry.remove(registry);
    registry.close();
}
~~~

Only remove the **registry added by the test itself**. In large test suites, tests sharing a JVM and running in parallel can still interact through `Metrics.globalRegistry`; in such cases, isolate processes or coordinate global state usage.

### 12.3. Integration tests in Spring Boot

With an application running a Spring context, verify both paths if your product uses them:

1. Call a service using injected `MeterRegistry` and verify the meter appears via Actuator or the test registry.
2. Call a library using `Metrics.*` and verify the meter appears in Boot's registry when `use-global-registry=true`.
3. Change the property in **a separate context/process** and verify static metrics do not enter Boot's registry when global is disabled.
4. Check sample counts after **a deterministic workload**, rather than guessing from dashboards with background traffic.
5. When tracing is needed, test Observation/Tracer separately; global registry tests do not prove trace propagation or sampling works.

Following this module's workflow, the lesson provides examples and verification methods; implementing and running tests in an actual repository belongs to hands-on practice or dedicated verification steps.

## 13. Global registry, tags, and `MeterFilter`: preventing series explosion

Using the global or an injected registry **does not change cardinality rules**. A Counter created with `userId` as a tag can still generate nearly one series per user, regardless of which path it takes.

~~~java
// Avoid: nearly unique value per request.
Metrics.counter(
        "orders.requests",
        "requestId", requestId
).increment();

// Better: a predefined set of outcome groups.
Metrics.counter(
        "orders.requests",
        "outcome", "success"
).increment();
~~~

With 5 statuses, 8 route templates, 3 methods, and 10 instances, a single metric can produce up to **5 × 8 × 3 × 10 = 1,200 label combinations** if all combinations occur. Adding a new ID per request can make series grow linearly with traffic.

Recommended practices:

- **Low-cardinality key–values** for tags like `outcome=success/error`, `http.method`, route templates, and stable environment names.
- **High-cardinality key–values** for controlled spans/logs when investigating a single request; never pass such IDs via `Metrics.counter(..., "id", ...)`.
- **Common tags** via `management.metrics.tags.*` (in Spring Boot 3.x) or compatible config. Watch out for duplicate keys across sources causing inconsistent data.
- **`MeterFilter`** to limit/rename/deny meters when appropriate, though the best policy is preventing high cardinality at the instrumentation site.
- **Selective histograms** since each label set generates multiple bucket series. Avoid enabling them on every meter without evaluating cost.

The global registry does not enforce any "global tag policy" beyond the configuration of its child registries; filter and common tag setup on each registry remains essential. Verify output at the destination rather than only looking at tag strings in Java calls.

## 14. Common errors and diagnosis

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `Metrics.counter(...)` does not appear in Prometheus | Global has no child registry; Boot disabled global; missing Prometheus registry/exporter | Check `use-global-registry`, dependencies, and endpoint output |
| Injected registry works, but static API does not | The two paths are not wired to the same target registry | Compare context config with `Metrics.globalRegistry` |
| Count doubles after refactoring | Code calls both static and injected APIs for the same event | Locate every `increment()/record()` call site |
| Metric exists in app, missing on dashboard | Wrong scrape target, path, label, or exporter; query mismatch | Check `/actuator/prometheus` and backend targets |
| Startup data missing | Static API ran before child registry was attached | Check initialization timing and first record call |
| Test A affects Test B | Both use static global registry in the same JVM | Use isolated registries, clean up added registries, avoid parallel tests |
| Changed global config, but metric still appears | Other code manually adds a registry, app didn't restart, or different context | Inspect live child registries and restart a clean process |
| Series count spikes | Tag contains real ID/URL, or many histogram buckets | Inspect actual labels and limit cardinality |
| Metrics accurate, but no traces | Tracing bridge, sampler, exporter, or propagation not ready | Check tracing pipeline; global metrics do not create spans |
| Two backends show the same metric | Intentional composite fan-out | Count per backend separately; do not sum copies |
| Counter read from new registry stays 0 | Reading a registry not receiving measurements, or recorded before attaching | Verify target registry and initialization order |

### Isolation procedure

1. **Identify where code records the meter:** static `Metrics.*`, injected `MeterRegistry`, or Observation handler.
2. **Confirm the target registry:** which bean was auto-configured, which registries are in the global composite, and which backend is used.
3. **Check lifecycle:** were metrics recorded before or after the target registry was ready; are there duplicate records at the same boundary?
4. **Check tags/names:** the same metric name with different tags can aggregate misleadingly; inspect individual label combinations.
5. **Check exporter and backend:** Actuator metrics, Prometheus scrape, and live queries.
6. **If traces/logs are involved:** inspect `ObservationRegistry`, tracing handlers, samplers, propagation, and log correlation separately.
7. **After fixing:** verify counts under a controlled workload and confirm alerts/SLOs still preserve intended semantics.

## 15. Real-world scenario: losing metrics after disabling global

**Context.** A development team wanted better testability and added:

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

Spring Boot-managed HTTP/JVM metrics continued appearing normally, but the dashboard tracking processed messages from an older Java library suddenly dropped to 0.

**Investigation.** The legacy library recorded via:

~~~java
Metrics.counter(
        "legacy.messages.processed",
        "outcome", "success"
).increment();
~~~

Before the config change, Spring Boot linked its target registry into global, so the library's Counter reached the exporter. After disabling global, the application no longer automatically linked Boot's registry to the static global registry. The library's Counter was still invoked, but had no export path to the same backend.

**Remediation.** The team chose deliberately between two options:

1. If the library is under their control, update it to accept `MeterRegistry` from the application or design an adapter supplying the registry to the library. Keep `use-global-registry=false` and re-verify.
2. If the library cannot be modified yet, keep global auto-connection enabled in that application and establish clear test isolation/registry strategies. Only register an equivalent registry manually if you can control and carefully evaluate the setup.

After the change, the team ran a message workload with a known count, compared Counter deltas, checked labels and the exporter, and confirmed the dashboard returned to normal.

**Lesson:** disabling global linking **does not mean disabling Spring Boot's `MeterRegistry`**. However, code relying on static `Metrics.*` can lose its export path, so audit usages before flipping the setting.

## 16. Practice exercises

### Exercise A — Distinguishing global and the registry bean

A Spring Boot application has a `MeterRegistry` bean exporting to Prometheus and a library using `Metrics.counter(...)`.

1. Sketch the data path when global is linked to Boot's registry.
2. Explain why two `increment()` calls from the static and injected APIs can add to the same Counter.
3. When `use-global-registry=false` is set, does recording via the injected registry still work? Why?
4. If the same metric is exported to two backends, can you conclude the count is doubled?

### Exercise B — Deterministic count experiment

Create a service with a `submitOrder()` method:

- Record an `orders.submitted` Counter from an injected `MeterRegistry` when an order is accepted successfully.
- Submit exactly 20 orders in an environment without background traffic.
- Verify the count increases by exactly 20 in the target registry.
- Temporarily add a `Metrics.counter(...).increment()` call at the same spot and explain why the result increases by an extra 20 when global is linked to the same registry.
- Remove the duplicate call and verify accurate semantics.

### Exercise C — Test isolation

Write a unit test passing a `SimpleMeterRegistry` through the constructor. Write another test forced to use `Metrics.globalRegistry`, registering its own registry via `add(...)` and removing it via `remove(...)` in `finally`. Explain why you should not clear all global state when other tests share the same JVM.

### Exercise D — Incident analysis

In production, `/actuator/metrics/demo.global.events` does not appear after a deploy, while `/actuator/metrics/jvm.memory.used` still has data.

Check step by step: whether real events occurred, whether calls are static or injected, what `use-global-registry` is set to, which registries are in global, whether the exporter uses the expected metric name, whether the scrape target is healthy, and whether metrics were recorded before the registry was ready.

### Self-check questions

1. Is `Metrics.globalRegistry` shared directly across containers/pods?
2. Does a `CompositeMeterRegistry` feeding multiple backends necessarily double the count inside each backend?
3. Why does constructor injection make unit tests easier to isolate than the static API?
4. When adding a registry to global after an earlier `increment()`, are prior measurements replayed?
5. What can happen if the same registry is added manually while Spring Boot is also configuring registries?
6. Why does `management.metrics.use-global-registry=false` not disable all HTTP/JVM metrics?
7. Does the global `MeterRegistry` automatically create spans or propagate `traceparent`?
8. When tracking a specific request, why should `requestId` not be placed in a metric label?
9. When using `ObservationRegistry`, which component typically converts an Observation into metrics?
10. When code and exporter are both correct but the dashboard is missing metrics, which pipeline stage should be checked next?

**Completion criteria:** distinguish the global composite from the registry bean and `ObservationRegistry`; explain Spring Boot's registry-linking mechanism in the 3.x examples; choose static vs. injection appropriately; handle static state in tests, avoid duplicate recording, read exporter output accurately, and protect tag cardinality.

## 17. Key takeaways

- `Metrics.globalRegistry` is a **JVM-wide static `CompositeMeterRegistry`**; it receives measurements from `Metrics.*` and delegates to registered child registries.
- Spring Boot can link auto-configured registries into global; in Spring Boot 3.x, `management.metrics.use-global-registry=false` disables this auto-connection without disabling the injected `MeterRegistry`.
- For new Spring Boot code, **constructor injection** usually makes ownership and testing clearer; the static API is convenient when a library has no way to receive dependencies.
- **An event should be recorded only once for the same semantics.** Calling both static and injected APIs on the same code path can double counts if both reach the same target registry.
- When global has no child registries yet, events recorded into the void are not replayed after a registry is added.
- Global metrics do not automatically provide tracing, propagation, or log correlation. Use `ObservationRegistry` and an appropriate tracing pipeline when signal correlation is required.
- Verify meters via live Actuator/Prometheus output, control cardinality, distinguish instrumentation errors from exporter or scrape issues, and clean up global state added by tests.

## References

- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Boot 3.x Reference — Metrics](https://docs.spring.io/spring-boot/docs/3.3.x/reference/html/actuator.html#actuator.metrics)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
