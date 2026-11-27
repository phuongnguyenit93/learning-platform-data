# ObservationHandler in Micrometer Observation: Handling the Lifecycle of an Observation

> **Chapter:** Micrometer Observation  
> **Lesson:** ObservationHandler  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. What Problem Does ObservationHandler Solve?

In Spring Boot, we want to measure a business operation, such as `orders.process`, and leverage that same measurement for multiple purposes: recording latency, opening a span for tracing, adding events, or writing diagnostic logs. If order-processing code had to call Timer, tracer, and logger APIs directly at every spot, business logic would become tightly coupled to observability tools.

**`ObservationHandler<T extends Observation.Context>`** is the component that reacts to the **lifecycle** of an `Observation`. Business code simply creates, starts, marks errors/events on, and stops an `Observation`; the handlers registered in `ObservationRegistry` perform the corresponding measurement work.

~~~mermaid
flowchart TD
    A["Business code creates Observation"] --> B["ObservationRegistry"]
    B --> C["Observation + Context"]
    C --> D["Lifecycle: start / scope / event / error / stop"]
    D --> E["ObservationHandler"]
    E --> F["Meter handler: Timer, metrics"]
    E --> G["Tracing handler: spans"]
    E --> H["Custom handler: logs, technical audit, custom stats"]
    F --> I["Metrics backend via exporter"]
    G --> J["Tracing backend via reporter/exporter"]
~~~

This is the *instrument once, observe in several ways* model: an operation is instrumented once; handlers decide which signals are produced. **A handler is not synonymous with an exporter.** A handler creates or updates measurements/spans/events; the registry, tracer, and exporters behind it determine the path to Prometheus, OTLP, or another system.

For example, creating an order takes 240 ms. A metrics handler can record the `orders.process` Timer; a tracing handler can create a corresponding span; a custom handler can emit debug logs when the operation fails. All three use the same `Observation.Context`, though they do not necessarily share the same storage or sampling policies.

## 2. Participating Components

| Component | Responsibility | Relationship to ObservationHandler |
| --- | --- | --- |
| `Observation` | Represents the tracked operation; emits `start`, `stop`, `error`, `event`, and `scope` events | Triggers handler callbacks |
| `ObservationRegistry` | Stores configuration and the lists of handlers, conventions, predicates, and filters | Where handlers are registered/dispatched |
| `Observation.Context` | Holds metadata and mutable temporary data over the lifecycle | Passed to callbacks; allows sharing state across callbacks |
| `ObservationConvention` | Defines naming, contextual name, and key-values by convention | Helps handlers receive consistent metadata |
| `ObservationPredicate` | Decides whether a real observation is created or becomes a no-op | If disabled, no useful callback chain runs |
| `ObservationFilter` | Adjusts `Context` before the observation finishes | Can supplement metadata used by handlers at `onStop` |
| `ObservationHandler` | Converts lifecycle signals into measurement or custom work | Where metrics/traces/logs logic is implemented |

Two easily confused concepts:

- **`Observation.Context` is per-execution data**, not a singleton. You can store temporary data in context so `onStop` can read what `onStart` wrote.
- **Scope** determines which observation is *current* in the execution context. A scope's lifetime **does not necessarily match** the observation's lifetime: one observation can open and close scopes multiple times.

When using Spring Boot Actuator, the application typically receives `ObservationRegistry` via dependency injection. In a Spring Boot application with observability configured, `ObservationHandler` beans are automatically registered into the registry by Spring Boot. Therefore, in Spring Boot examples, creating a handler bean is the natural integration path; there is no need to create a second registry.

## 3. Lifecycle API: When Do Callbacks Run?

`ObservationHandler` provides event-driven callbacks. The most commonly used hooks are:

| API | Trigger condition | Typical work |
| --- | --- | --- |
| `supportsContext(Observation.Context ctx)` | Registry checks whether the handler supports the context | Select which observation/context types to handle |
| `onStart(T ctx)` | `observation.start()` | Save initial state, initialize measurement work |
| `onScopeOpened(T ctx)` | `observation.openScope()` | Set active context (e.g., trace/span on thread) |
| `onEvent(Observation.Event event, T ctx)` | `observation.event(event)` | Record a milestone/event mid-operation |
| `onError(T ctx)` | `observation.error(exception)` | Read `ctx.getError()`, mark error on the signal |
| `onScopeClosed(T ctx)` | `scope.close()` | Clean up state bound to the scope/execution |
| `onScopeReset(T ctx)` | When scope management needs to reset state | Restore/clean up handler-managed context if applicable |
| `onStop(T ctx)` | `observation.stop()` | Complete timer/span, emit final figures, release resources |

Do not read the table above as a fixed call schedule for every observation. For example, `onError` **only fires when an error is reported to the Observation**. If you manage start/stop manually and catch an exception without calling `observation.error(ex)`, handlers will not know the failure cause. `onEvent` only fires when instrumented code submits an event. Scope callbacks also do not run if no scope is opened.

A typical synchronous flow:

~~~mermaid
sequenceDiagram
    participant App as OrderService
    participant Obs as Observation
    participant Handler as ObservationHandler
    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(ctx)
    App->>Obs: openScope()
    Obs->>Handler: onScopeOpened(ctx)
    App->>Obs: event(validation.completed)
    Obs->>Handler: onEvent(event, ctx)
    alt operation throws exception
        App->>Obs: error(ex)
        Obs->>Handler: onError(ctx)
    end
    App->>Obs: scope.close()
    Obs->>Handler: onScopeClosed(ctx)
    App->>Obs: stop()
    Obs->>Handler: onStop(ctx)
~~~

This sequence illustrates normal `try-with-resources` usage with `stop()` in `finally`. Do not build assumptions into business logic about how many times scopes are opened or the relative ordering across multiple handlers; each handler should own a single clear responsibility.

## 4. Writing a Custom ObservationHandler in Spring Boot

### 4.1. A handler that only cares about order processing

Suppose the goal is to emit low-level technical logs when `orders.process` starts/stops, and log the exception type when an error occurs. We do not need to rebuild a Timer or span because Micrometer already provides dedicated handlers for those.

~~~java
package example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public final class OrderLifecycleHandler
        implements ObservationHandler<Observation.Context> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderLifecycleHandler.class);

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "orders.process".equals(context.getName());
    }

    @Override
    public void onStart(Observation.Context context) {
        log.debug("Observation started: {}", context.getName());
    }

    @Override
    public void onEvent(
            Observation.Event event, Observation.Context context) {
        log.debug("Observation event: name={}, event={}",
                context.getName(), event.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        String errorType = error == null
                ? "unknown" : error.getClass().getSimpleName();

        log.warn("Observation failed: name={}, errorType={}",
                context.getName(), errorType);
    }

    @Override
    public void onStop(Observation.Context context) {
        log.debug("Observation stopped: {}", context.getName());
    }
}
~~~

**Key points to understand:**

1. `supportsContext` selects the exact observation to handle; HTTP, JDBC, or other business observations will not be logged by this handler. In large codebases, prefer strongly typed contexts when distinguishing multiple operation kinds; filtering by name works well for small examples.
2. `onStart` and `onStop` react to the lifecycle. In the example, they only log and do not create a duplicate Timer.
3. `onError` reads only the exception **type**, avoiding pushing error messages containing tokens, emails, or business data into logs.
4. The handler is registered as a `@Component` bean. With Spring Boot Actuator's observability auto-configuration, Spring Boot registers the handler into `ObservationRegistry` automatically. Do not also add that same instance via a customizer, as that easily causes duplicate callback invocations.
5. Callback code executes on the observation path; keep it **lightweight, fault-tolerant**, and free of synchronous network calls per event. Logging at DEBUG level avoids generating massive log volume under high traffic.

### 4.2. Instrumenting business code to trigger the handler

~~~java
package example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void processOrder() {
        Observation observation = Observation.createNotStarted(
                "orders.process", observationRegistry)
            .contextualName("process order")
            .lowCardinalityKeyValue("operation", "create")
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            validateOrder();
            observation.event(
                    Observation.Event.of("validation.completed"));
            persistOrder();
        } catch (RuntimeException ex) {
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private void validateOrder() {
        // Order validation logic
    }

    private void persistOrder() {
        // Order persistence logic
    }
}
~~~

If both methods succeed, the handler receives `onStart`, `onScopeOpened`, `onEvent`, `onScopeClosed`, and `onStop`. If a method throws a `RuntimeException`, `onError` is also invoked. `finally` ensures `stop()` still runs. Closing the scope is guaranteed by `try-with-resources` upon exiting the block, even on exception.

The shorthand `Observation.createNotStarted(...).observe(() -> {...})` is convenient when you do not need custom control over scopes, events, or special handling. When explicit control over steps is required, the `start()` + `openScope()` + `error()` + `stop()` pattern is clearer and easier to maintain.

## 5. `supportsContext` and Strongly Typed Contexts

`ObservationHandler<T>` is parameterized by `T extends Observation.Context`. This allows a handler to target a single context type while accessing operation-specific properties without casting to a global object.

Suppose we later need order-processing phase information; we define:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

final class OrderObservationContext extends Observation.Context {
    private String phase = "received";

    public void setPhase(String phase) {
        this.phase = phase;
    }

    public String getPhase() {
        return phase;
    }
}

final class OrderPhaseHandler
        implements ObservationHandler<OrderObservationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof OrderObservationContext;
    }

    @Override
    public void onStop(OrderObservationContext context) {
        // Example: read context.getPhase() and perform lightweight work,
        // without necessarily creating extra metrics or logs.
        String phase = context.getPhase();
    }
}
~~~

To use this handler, create the observation with a supplier for the desired context type:

~~~java
Observation observation = Observation.createNotStarted(
        "orders.process",
        OrderObservationContext::new,
        observationRegistry
).start();

try (Observation.Scope scope = observation.openScope()) {
    OrderObservationContext context =
            (OrderObservationContext) observation.getContext();
    context.setPhase("persisted");
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

The snippet above demonstrates the `Context` API; `OrderPhaseHandler` must be registered (for example, annotated with `@Component` in Spring) for callbacks to actually run. In real applications, split classes into separate Java files following project structure and restrict `phase` to a predefined set of values.

**Context is not a tag.** Data stored via getters/setters or `put/get` on `Observation.Context` is only state for the observation process. It does not automatically become a metric label or span attribute. When you genuinely need grouping by **low-cardinality** data, add key-values via the appropriate observation/convention API.

## 6. Built-in Handlers: Metrics, Tracing, and Important Limitations

### 6.1. DefaultMeterObservationHandler

`DefaultMeterObservationHandler` (in Micrometer Core) receives lifecycle signals and represents them as meters in `MeterRegistry`. In modern Micrometer versions, notable behaviors include:

- **Timer:** records duration from `start` to `stop` under the observation name, typically with low-cardinality tags and error-type information.
- **Event counter:** can count events when `Observation.event(...)` is called (naming/export behavior depends on version, configuration, and meter handler).
- **LongTaskTimer:** supports tracking in-flight observations when enabled; not every observation gets a LongTaskTimer by default.

In a standalone Java example **without Spring Boot auto-configuration**, manual registration looks like this:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));

Observation.createNotStarted("orders.process", registry)
        .lowCardinalityKeyValue("operation", "create")
        .observe(() -> {
            // Operation to measure
        });

long count = meters.get("orders.process")
        .tag("operation", "create")
        .timer()
        .count();  // After one execution: 1
~~~

In a Spring Boot application with Actuator and auto-configuration, use the registry provided by Spring. Calling `ObservationRegistry.create()` inside a service easily detaches custom observations from pre-configured handlers, metrics, and tracing.

### 6.2. Tracing ObservationHandlers

Micrometer Tracing provides handlers for tracing, such as:

- `DefaultTracingObservationHandler`: creates/manages spans for regular observations.
- `PropagatingSenderTracingObservationHandler`: handles sending trace context on outbound calls.
- `PropagatingReceiverTracingObservationHandler`: handles receiving context on the server/consumer side.

These handlers are typically combined under a **first matching** strategy to pick the right tracing mechanism for each observation type. They require a properly configured tracer and propagator; registering a custom handler does not by itself turn an application into a distributed tracing system.

**Sampling** is applied by the tracing stack's policy and does not mean Micrometer samples Timer metrics at the same rate. For instance, 100 requests can contribute to a Timer while only a subset is exported as traces. Therefore, never infer real request counts from the number of traces appearing in a backend.

## 7. Combining Multiple Handlers: All Matching vs. First Matching

An `ObservationRegistry` can hold multiple handlers. Two common composites are:

| Mechanism | Meaning | Use case |
| --- | --- | --- |
| `AllMatchingCompositeObservationHandler` | Lets every matching child handler receive events | Combining independent capabilities that all observe one operation |
| `FirstMatchingCompositeObservationHandler` | Picks the first matching child handler in configured order | Selecting exactly one handler among mutually exclusive alternatives, e.g., sender/receiver/default propagation |
| Registering multiple independent handlers | Registry dispatches to all supported handlers | Combining meter handler, tracing handler, and custom handler |

Do not lump every handler into a `FirstMatchingCompositeObservationHandler`: if a generic handler with `supportsContext() == true` comes first, later handlers may never be selected. Conversely, running multiple tracing handlers that each create a span for the same context can lead to duplicate measurements.

A common selection layout:

~~~mermaid
flowchart TD
    A["Observation"] --> B["All matching: Metrics + Custom log"]
    A --> C["Tracing composite: First matching"]
    C --> D{"Which context?"}
    D -->|Sender| E["PropagatingSender"]
    D -->|Receiver| F["PropagatingReceiver"]
    D -->|Default| G["DefaultTracing"]
~~~

This is a conceptual diagram, not a copy-paste configuration. In Spring Boot, handler ordering and composition depend on tracing auto-configuration, so verify the actual integration before adding manual composites.

## 8. Tags/Cardinality: What Handlers Read vs. What Exporters Receive

`Observation` distinguishes two important key-value groups:

| Kind | Examples | Suitable for |
| --- | --- | --- |
| **Low cardinality** | `operation=create`, `outcome=success/error`, `http.method=POST` | Metric tags and trace/span attributes |
| **High cardinality** | `order.id`, `request.id`, per-operation unique identifiers | Tracing when needed and permitted; do not put into metric labels |

Handlers are allowed to read `Context`, which does not mean you should log or export every value. In real applications, detailed data can contain personal info, tokens, or excessively distinct values.

For example, 20 URI templates × 4 methods × 5 statuses × 8 instances already create up to **3,200 label combinations** for one metric before counting histogram buckets. Using `orderId` with 100,000 values as a metric label could multiply the series count by orders of magnitude. When you need to correlate with a specific request, use trace/span IDs across logs/traces—or exemplars if your backend supports them—instead of inserting IDs into metric labels.

**Timing of adding tags also matters.** A metrics handler creating a Timer at `onStop` can see low-cardinality key-values added during execution. However, an in-flight measurement (*LongTaskTimer*) started at `onStart` only sees tags already present at that moment. Design conventions and metadata for the specific lifecycle rather than assuming every handler receives the same tag set at every callback.

## 9. Scope and Context Propagation in Asynchronous Processing

Handlers provide `onScopeOpened` / `onScopeClosed` to react when setting or restoring the active observation. Scopes usually rely on the thread's execution context. Two common scenarios:

1. **Synchronous:** `try (Observation.Scope scope = observation.openScope())` ensures the scope closes when exiting the block, even on exception. Nested scopes must be restored in proper order.
2. **Asynchronous:** running on another thread, an executor, Reactor, or across HTTP may require explicit context propagation. Creating an observation on thread A **does not guarantee** thread B automatically receives the current observation or trace context.

In Spring Boot, choose the context propagation mechanism suited to your framework and version (such as a task decorator for executors or Reactor context propagation). Tracing propagators are responsible for injecting/extracting trace context across service boundaries. An `ObservationHandler` cannot fix missing context propagation on its own simply by implementing `onScopeOpened`.

A common bug is opening a scope in a handler and forgetting to close it when done. That can leak context into another request on a reused thread. If a handler manages scope-bound resources, implement symmetric save and restore logic that covers error branches too.

## 10. When to Use a Handler, Filter, Convention, or Predicate?

| Need | Right place | Why |
| --- | --- | --- |
| Naming observations and standardizing tags | `ObservationConvention` | Unifies metadata across all instrumentation sites |
| Adding shared metadata before stop | `ObservationFilter` | Centralizes context enrichment before completion |
| Skipping an observation conditionally | `ObservationPredicate` | Reduces creation of unnecessary observations |
| Reacting to start/stop/error/event/scope | `ObservationHandler` | Attaches logic to lifecycle milestones |
| Producing standard Timers or spans | Built-in Micrometer handlers | Avoids duplicating logic and integrates cleanly with registries/exporters |
| Filtering HTTP attributes to defined values | Convention/filter or instrumentation customizations | Easier cardinality control and reuse |

A custom handler makes sense when an action must happen **because** of lifecycle events and isn't already covered by standard handlers. Avoid writing a handler just to rename a metric at every stop, or building your own Timer alongside `DefaultMeterObservationHandler` when you only want basic duration measurement.

## 11. Testing and Diagnosing Handlers

### 11.1. Empirical checklist

1. Confirm the application has an active `ObservationRegistry`; in Spring Boot, check Actuator dependencies and observability configuration.
2. Ensure the handler bean is managed by Spring or manually registered on the right registry (in standalone Java apps).
3. Create an observation matching `supportsContext`.
4. Trigger an `event`, a controlled error, and `stop` in sequence; observe the corresponding callbacks.
5. For metrics, check Timer/count/low-cardinality tags in `MeterRegistry` or the configured Actuator/exporter endpoint.
6. For tracing, inspect tracing dependencies, sampler, propagator, exporter, and span parent/child relationships; do not conclude a handler didn't run merely because no exported trace appeared.

### 11.2. Common errors

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| No callbacks fire | Handler not registered, wrong registry used, `supportsContext` returns `false`, or blocked by predicate | Check bean, injected registry, support condition, and filters |
| `onStart` runs but no `onStop` | Missing `stop()` on a branch or operation hasn't completed | Use `finally`; for async, stop when work actually completes |
| `onError` not called when code throws | Manual instrumentation forgot `observation.error(ex)` | Report the error before rethrowing in `catch` |
| Callbacks run twice or Timer/span double-counted | Same handler registered twice or multiple handlers doing the same job | Audit beans and manual registrations; configure composites properly |
| Metrics appear but traces do not | Missing tracing handler/exporter, broken propagation, or trace dropped by sampling | Check the tracing pipeline and sampler separately |
| Context lost on another thread | Scope/current observation not propagated | Check executor decorators, Reactor, and cross-service request propagators |
| Too many series or excessive logs | Low-cardinality tags abused, handler logging too verbosely | Bound tag values, use appropriate log levels, and monitor cost |
| Tags at `onStart` differ from `onStop` | Metadata added after start time | Clarify when conventions, filters, or business logic attach tags |

### 11.3. Testing with a standalone registry

When you want to verify the exact callback protocol without depending on networks or a tracing backend, spin up `ObservationRegistry.create()` and an in-memory test handler that counts callbacks. The key is checking the **correspondence between API calls and received callbacks**, for instance:

- `start()` once → `onStart` is present.
- `event(Observation.Event.of("validated"))` → `onEvent` receives name `validated`.
- `error(exception)` → `onError` reads the exception from `Context`.
- `openScope()` / `close()` → balanced scope open/close callbacks.
- `stop()` in `finally` → `onStop` is invoked even when business logic fails.

This is a targeted test of the handler; receiving callbacks **does not prove** metrics were scraped or traces reached a backend. Verify each exporter hop separately.

## 12. End-to-End Scenario: Investigating a Slow and Failing API

Suppose after a deploy, `POST /api/orders` p95 increases from 150 ms to 800 ms, and the 5xx rate rises from 0.2% to 3%, while request rate stays nearly flat.

1. **Metrics handler** records shifts in Timer latency and error counts across bounded tags such as route/status. Dashboards pinpoint when degradation started.
2. **Tracing handler** creates spans for a subset of requests (depending on the sampler). If propagation is configured, traces link server spans to database/downstream calls.
3. **Custom handler** can record technical events like `validation.completed` or exception classes; log content should be sufficient for investigation while avoiding sensitive data.
4. **Correlation:** query logs by time window and trace ID, open slow traces to break down where time went, and verify hypotheses such as DB timeouts or a slow downstream.
5. **Post-remediation verification:** confirm p95, error rate, and saturation return to target thresholds. A single span illustrates a potential cause, whereas metrics confirm service-wide trends.

Remember the relationship: **ObservationHandler is the connector between instrumented business code and observability signals**. Final diagnostic quality also depends on metric definitions, tag hygiene, context propagation, sampling, and how well logs–metrics–traces correlate in production.

## 13. Hands-on Exercise

Write a Spring Boot service with `ObservationRegistry` and a custom handler observing `inventory.reserve`. Answer the following questions by running experiments:

1. If you call `createNotStarted(...)` without calling `start()`, which callbacks are emitted?
2. If you manage the observation manually and throw an exception without calling `error(ex)`, does the handler know the error type?
3. If `supportsContext` only accepts `OrderObservationContext`, does an observation created with `new Observation.Context()` trigger the handler?
4. If an observation opens and closes a scope twice while starting and stopping once, how many scope events and stop events occur?
5. When adding `sessionId` to low-cardinality tags, how can time series cost change? If an ID is needed for investigation, which signal should hold it?
6. If metrics appear on a dev machine but traces do not, list the stages of the tracing pipeline to verify, including the sampler and exporter.

**Completion criteria:** accurately describe the role and lifecycle of `ObservationHandler`, write a handler using `supportsContext` together with `onError`/`onStop`, distinguish registry/handler/exporter, and know how to avoid double counting, manage scopes, and bound cardinality.

## Takeaways

- `Observation` emits events; `ObservationRegistry` coordinates; `ObservationHandler` turns events into behaviors such as updating a Timer, span, or technical log.
- `supportsContext` determines which context types a handler applies to; `onError` requires errors to be reported via `observation.error(ex)` during manual instrumentation.
- Scope represents the current observation; opening/closing a scope and starting/stopping an observation are two distinct responsibilities.
- In Spring Boot with Actuator, register handlers as beans and leverage the auto-configured registry.
- Use built-in meter/tracing handlers when appropriate; pay attention to composites, exporters, tracing sampling, context propagation, and tag cardinality.

## References

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
