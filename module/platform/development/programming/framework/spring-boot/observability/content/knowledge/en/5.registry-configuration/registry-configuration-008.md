# Handler Processing Order in ObservationRegistry Configuration

> **Chapter:** Registry Configuration  
> **Lesson:** Handler Processing Order  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. Why Does Handler Order Matter?

An operation in Spring Boot can be measured once with **Micrometer Observation**, then produce multiple signals: a Timer in metrics, a span in distributed tracing, and logs for investigation. Each capability is usually handled by a different `ObservationHandler`. These handlers receive lifecycle notifications for an `Observation` through `ObservationRegistry`.

Without understanding how the registry selects and composes handlers, it is easy to hit issues such as:

- Metric counts incrementing twice because the same measurement capability was registered twice.
- HTTP client traces being processed by the default tracing handler, losing propagation logic for outbound calls.
- A logging handler placed at high priority inside a **first-matching** group, preventing a trailing tracing handler from ever being chosen.
- One handler expecting to read metadata produced by another handler at `onStart`, whereas that metadata is only added at `onStop`.
- Dashboards showing normal metrics while traces miss parent-child links or fail to appear, leading to wrong conclusions about root cause.

**Key takeaway:** "Handler processing order" comprises **registration order**, **matching selection rules**, **lifecycle milestone sequence**, and **when data becomes available**. These are distinct concerns and must be analyzed separately.

This lesson shows how to design and verify that ordering at the Micrometer level, then apply it to a Spring Boot application with metrics, logs, and tracing. Auto-configuration details can vary across library versions, so always cross-check observed runtime behavior against the documentation for your exact version.

## 2. Four Ordering Layers to Distinguish

| Layer | Question | Example |
| --- | --- | --- |
| **Registration** | Which handlers are in the registry, and how were they added? | Handler beans auto-registered by Spring Boot; manually added handlers |
| **Selection** | For a given `Observation.Context`, which handlers qualify for callbacks? | `supportsContext(context)`; `first matching` composite |
| **Lifecycle** | Which events occurred earlier or later? | `start` → `openScope` → `event/error` → `closeScope` → `stop` in a typical flow |
| **Data** | At which callback are tags, errors, and context ready? | `channel` before `start`; `outcome` after execution but before `stop` |

The order in which handlers are declared **does not determine** the order in which `onStart`, `onError`, or `onStop` occur. Those callbacks are tied to actions on `Observation`. Likewise, the order in which a handler is registered does not guarantee the data it needs already exists when the callback arrives.

For example, handlers A and B both support a context. If business code never calls `observation.error(ex)`, neither handler receives `onError` simply because they were registered in the right order.

## 3. How Does the Registry Coordinate ObservationHandlers?

Key components:

- **`Observation`:** the unit of work being observed; exposes `start()`, `stop()`, `openScope()`, `event(...)`, `error(...)`.
- **`Observation.Context`:** holds metadata, errors, and state for a single observation. Handlers can read or store temporary state here.
- **`ObservationRegistry`:** holds observation configuration, including handlers, predicates, filters, and conventions.
- **`ObservationHandler<T>`:** decides which contexts it supports via `supportsContext`, then receives matching lifecycle callbacks.
- **`ObservationHandler.AllMatchingCompositeObservationHandler`:** groups multiple handlers, letting every matching child handler run.
- **`ObservationHandler.FirstMatchingCompositeObservationHandler`:** picks the **first** matching child handler in priority order.

~~~mermaid
flowchart TD
    A["Business code creates Observation"] --> B{"Predicate allows?"}
    B -->|No| C["No-op Observation"]
    B -->|Yes| D["Observation + mutable Context"]
    D --> E["Lifecycle: start, scope, event, error, stop"]
    E --> F["Registry and handlers"]
    F --> G["All matching: independent capabilities"]
    F --> H["First matching: first matching strategy"]
    G --> I["Metrics, technical logging"]
    H --> J["Sender / Receiver / Default tracing"]
    I --> K["MeterRegistry and exporters"]
    J --> L["Tracer, sampler, and exporters"]
~~~

`ObservationPredicate` decides whether to create a real observation or a no-op. `ObservationFilter` can adjust the context at the end of the lifecycle: Micrometer documentation states that filters are invoked **before handlers' `onStop`**. Hence a tag added by a filter can appear in `onStop` processing, but is not automatically available at `onStart`.

A handler **is not an exporter**. Metrics handlers typically interact with `MeterRegistry`; tracing handlers interact with a tracer. The registries, reporters, samplers, and exporters behind them decide whether data is aggregated, sampled, or shipped to Prometheus/OTLP and observability backends.

## 4. Lifecycle Drives Callback Order

A manual instrumentation example:

~~~java
Observation observation =
    Observation.createNotStarted("checkout.process", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("validated"));
    processCheckout();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Following this flow:

1. `start()` triggers `onStart` on matching handlers.
2. `openScope()` makes the scope current and triggers the scope-opened callback.
3. `event(...)` triggers `onEvent`.
4. `error(ex)` only fires when the error branch calls this API; handlers can read `context.getError()`.
5. `scope.close()` (via `try-with-resources`) triggers the scope-closed callback.
6. `stop()` ends the observation and runs stop handling, with filters applied prior to `onStop` callbacks in Micrometer's flow.

~~~mermaid
sequenceDiagram
    participant App as CheckoutService
    participant Obs as Observation
    participant Registry as ObservationRegistry
    participant Handler as Selected Handler
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    App->>Obs: openScope()
    Obs->>Handler: onScopeOpened(context)
    App->>Obs: event(validated)
    Obs->>Handler: onEvent(event, context)
    alt exception occurs and is recorded
        App->>Obs: error(ex)
        Obs->>Handler: onError(context)
    end
    App->>Obs: scope.close()
    Obs->>Handler: onScopeClosed(context)
    App->>Obs: stop()
    Obs->>Registry: apply ObservationFilter
    Registry-->>Obs: updated context
    Obs->>Handler: onStop(context)
~~~

This represents **phase ordering in one specific API call pattern**, not a guarantee that every observation has exactly one scope, one event, and one error. An observation may open scopes multiple times or not at all; asynchronous operations may have start/stop points on different execution threads.

Also distinguish **callback ordering between two handlers within the same phase** from ordering across phases. If you must rely on handler B reading a value written by handler A during the same `onStart`, verify the exact dispatch behavior of your Micrometer version and write contract tests. A safer design is preparing metadata before `start` or placing rules into a shared convention/context.

## 5. AllMatchingCompositeObservationHandler: All Matching Capabilities

### 5.1. Purpose

An **all-matching** group fits when multiple independent capabilities all need to observe the same observation: for instance, one handler measuring latency and another recording technical events.

Suppose `handlerA.supportsContext(context)` and `handlerB.supportsContext(context)` both return `true`. An `AllMatchingCompositeObservationHandler` containing A and B allows **both** to participate in the corresponding callbacks. If handler C returns `false`, C is not selected.

~~~java
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig().observationHandler(
    new ObservationHandler.AllMatchingCompositeObservationHandler(
        handlerA,
        handlerB
    )
);
~~~

In this snippet, `handlerA` and `handlerB` are **pre-created instances** of compatible `ObservationHandler<?>` types. The example only illustrates composition, not their full definitions.

Characteristics:

- Every child handler matching the context is invoked; selecting one handler **does not prevent** other independent handlers from participating.
- If two handlers both create a Timer for the same observation, duplicate metrics or inflated counts can occur. All-matching **does not deduplicate responsibilities automatically**.
- Avoid relying on ordered side effects across handlers. If shared data is needed, populate it in the context or convention before the relevant phase.
- Handler callbacks should be lightweight, fault-tolerant, and free of synchronous network calls on the request path.

### 5.2. When Manual Composites Are Unnecessary

Spring Boot Actuator automatically registers `ObservationHandler` beans on the configured `ObservationRegistry`. For independent capabilities, use handler beans instead of building a composite manually and inserting it into the registry a second time.

There is no reason to register a handler both via `@Component` **and** by calling `registry.observationConfig().observationHandler(sameHandler)`. Double configuration can cause duplicate callback execution. Before replacing default mechanisms, audit existing beans and auto-configurations.

## 6. FirstMatchingCompositeObservationHandler: Priority Strategy Selection

### 6.1. Core Rule

A **first-matching** group is used when multiple handlers are **mutually exclusive alternatives** and only one handler should apply to a specific context. The child list is **ordered by priority**: the first matching handler wins, and trailing handlers in that group get no chance to run.

Illustrative example:

| Position | Handler | `supportsContext` |
| --- | --- | --- |
| 1 | Handler specialized for HTTP client | `true` when context is sender |
| 2 | Handler specialized for HTTP server | `true` when context is receiver |
| 3 | Default tracing handler | `true` for regular contexts |

For a sender observation, the handler at position 1 is chosen. For a receiver, position 1 does not match, so handler 2 is chosen. For a regular context, neither specialized handler matches, so handler 3 handles it.

If you place the default handler with a broad support condition **in the first position**, it can "shadow" sender/receiver handlers. This is a common ordering misconfiguration.

### 6.2. Tracing Configuration Example from Micrometer Docs

~~~java
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingReceiverTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingSenderTracingObservationHandler;

// tracer and propagator are configured for the active tracing backend.
void configureTracing(
        ObservationRegistry registry,
        Tracer tracer,
        Propagator propagator) {

    registry.observationConfig().observationHandler(
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
            new PropagatingSenderTracingObservationHandler<>(
                tracer, propagator),
            new PropagatingReceiverTracingObservationHandler<>(
                tracer, propagator),
            new DefaultTracingObservationHandler(tracer)
        )
    );
}
~~~

This snippet applies when **configuring a registry manually**, such as in a standalone Micrometer app, and illustrates the priority idea accurately. In Spring Boot with tracing auto-configuration enabled, do not manually register this whole group again if the framework already does it: doing so can create duplicate spans or propagation conflicts.

Why the sender → receiver → default ordering:

- **Sender** needs to inject trace context into outbound calls (HTTP clients, message producers).
- **Receiver** needs to extract trace context from inbound requests or messages.
- **Default** serves as fallback for observations without sender/receiver context.

Depending on the framework, the instrumenter itself creates the appropriate context. Reordering handlers alone does not create sender/receiver contexts, nor does it turn on propagation by itself. You need matching tracer, propagator, and instrumentation together.

## 7. Combining Metrics and Tracing: One or Multiple Composites?

**The goal** is to let a single business observation produce both a Timer and a span while preventing two handlers from performing tracing work on the same context.

A standalone Micrometer configuration pattern:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingReceiverTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingSenderTracingObservationHandler;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    // Meter handler is independent of span type selection.
    .observationHandler(new DefaultMeterObservationHandler(meterRegistry))
    // Tracing group picks only the first matching handler.
    .observationHandler(
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
            new PropagatingSenderTracingObservationHandler<>(
                tracer, propagator),
            new PropagatingReceiverTracingObservationHandler<>(
                tracer, propagator),
            new DefaultTracingObservationHandler(tracer)
        )
    );
~~~

In this snippet, `meterRegistry`, `tracer`, and `propagator` are pre-created/configured variables; exact dependencies depend on the Micrometer and tracing bridge versions in use.

~~~mermaid
flowchart LR
    A["Observation on registry"] --> B["Meter handler"]
    A --> C["FirstMatching tracing"]
    C --> D{"Context type?"}
    D -->|Sender| E["PropagatingSender"]
    D -->|Receiver| F["PropagatingReceiver"]
    D -->|Other| G["DefaultTracing"]
    B --> H["Timer + low-cardinality tags"]
    E --> I["Span + inject context"]
    F --> J["Span + extract context"]
    G --> K["Standard span"]
~~~

Do not lump the meter handler and tracing handlers into **the same first-matching group** if you want **both metrics and tracing**. Once the first handler matches, subsequent handlers in that group are skipped, dropping a signal.

Conversely, do not put sender, receiver, and default tracing into an **all-matching** group when their support conditions overlap. The risk is multiple handlers manipulating spans/context simultaneously. The safe pattern is usually an **independent meter handler**, while **tracing is a first-matching group**.

### Exemplars Case

Some systems want to link metric samples to traces (*exemplars*). Micrometer Tracing provides `TracingAwareMeterObservationHandler` combining a meter handler with a tracer when supported by the pipeline. When using this variant, **replace** the plain meter handler rather than registering two handlers recording the same meter concurrently. Exemplar export also depends on the registry, exporter, and backend; handler ordering alone does not enable exemplars.

## 8. Handler Registration in Spring Boot: Mechanism and Scope of Responsibility

Spring Boot integrates Micrometer Observation via Actuator. When matching configuration is active, Spring Boot automatically registers beans of these types:

- `ObservationHandler`;
- `ObservationPredicate`;
- `ObservationFilter`;
- `GlobalObservationConvention`.

Additionally, the application can supply `ObservationRegistryCustomizer` to customize the registry during configuration. Therefore distinguish **Spring auto-configuration** from **manual handler registration in standalone Java**.

### 8.1. Standard Approach: Defining a Custom Handler Bean

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CheckoutAuditHandler
        implements ObservationHandler<Observation.Context> {

    private static final Logger log =
        LoggerFactory.getLogger(CheckoutAuditHandler.class);

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "checkout.process".equals(context.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        log.warn("Checkout observation failed: type={}",
            error == null ? "unknown" :
                error.getClass().getSimpleName());
    }

    @Override
    public void onStop(Observation.Context context) {
        log.debug("Checkout observation stopped");
    }
}
~~~

This bean is responsible for **reacting to errors and completion** of observations named `checkout.process`. It does not create a second Timer or span itself. Limit logging of sensitive data and avoid direct network access inside callbacks.

Business code:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void checkout(ObservationRegistry registry) {
    Observation.createNotStarted("checkout.process", registry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> {
            // Synchronous checkout execution.
            performCheckout();
        });
}
~~~

`observe(...)` wraps the common lifecycle and suits synchronous work. If you need manual scopes, events, or asynchronous completion, manage the lifecycle explicitly.

### 8.2. Should You Use `@Order` to "Fix" Ordering?

Spring beans can be ordered by several framework mechanisms. However, **do not treat merely adding `@Order` as a guarantee that every handler executes in your intended order**, especially when tracing composites, auto-configurations, and handlers supporting different contexts are involved.

Practical approach:

1. Verify which handlers are actually configured in the registry after Spring Boot starts up.
2. Distinguish when you need **exactly one** handler (use first-matching) from when you need **multiple capabilities** (meter + tracing + custom handler).
3. If priority is essential to correctness, design the composite group explicitly and **verify** on the chosen version.
4. Never double-register a handler bean inside a customizer or initialization code.

Be cautious when overriding Spring Boot's default tracing handler group, as changes can break context injection/extraction across HTTP clients, servers, and messaging.

## 9. Ordering Across Convention, Predicate, Filter, and Handler

Not everything with "observation" in its name is a handler. They participate at different stages:

| Component | Role | Ordering Relationship |
| --- | --- | --- |
| `ObservationPredicate` | Allows or blocks creating a real observation | Decides whether the observation is tracked before useful lifecycle callbacks occur |
| `ObservationConvention` | Defines name, contextual name, and key-values | Should supply upfront metadata so handlers see it as expected |
| `ObservationHandler.onStart` | Runs when observation starts | Some handlers require tags at this moment |
| `ObservationFilter` | Modifies context as observation completes | Micrometer applies filters before handlers' `onStop` |
| `ObservationHandler.onStop` | Finalizes Timer/span or corresponding task | Can read metadata added prior to stop |

Example:

~~~java
Observation observation = Observation.createNotStarted(
        "checkout.process", registry)
    .lowCardinalityKeyValue("channel", "web")
    .start();

try {
    doBusinessWork();
    observation.lowCardinalityKeyValue("outcome", "success");
} catch (RuntimeException ex) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

`channel` is known upfront, so it is attached before `start()`; `outcome` is only attached once the result is known and before `stop()`. A Timer recording duration at stop can use the final outcome, whereas an **in-flight `LongTaskTimer`** or a handler reading tags at start only sees tags present when it started.

Never make a handler work correctly only if another handler happens to add a key "just in time." For shared data needed early, put it into the context/convention before processing begins. For final outcomes, use a filter or business API calls before `stop`.

## 10. `supportsContext` Rule: Stable and Accurate

`supportsContext(Observation.Context)` lets a handler select the right observation type. A sound implementation usually checks the **context type** or a lifecycle-stable condition.

Example:

~~~java
final class CheckoutContext extends Observation.Context {
    // Meaningful fields for checkout instrumentation.
}

final class CheckoutContextHandler
        implements ObservationHandler<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        // Handle checkout start.
    }

    @Override
    public void onStop(CheckoutContext context) {
        // Finalize corresponding processing.
    }
}
~~~

In a pipeline with `FirstMatchingCompositeObservationHandler`, condition order matters even more:

- Place **specialized** handlers before broadly matching handlers.
- Place **fallback** handlers last.
- Avoid conditions that change based on `outcome` or metadata added after `onStart`; callbacks for the same observation risk inconsistent handler selection if support checks are re-evaluated.
- Never put a handler with `supportsContext(...) == true` at the front of a first-matching composite if trailing specialized handlers should receive the context.

**Design rule:** support checks describe the **kind of work**, whereas results/outcomes are **metadata about the work**. Do not turn outcomes into handler selectors when tags or light callback logic solve the problem cleanly.

## 11. Verifiable Practice: Recording Callback Order

When a bug depends on ordering, the reliable method is building a small in-memory registry and recording **actual callbacks** on the current Micrometer version. This needs no exporter or tracing backend.

### 11.1. Recording Handler

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import java.util.List;

final class RecordingHandler
        implements ObservationHandler<Observation.Context> {

    private final String id;
    private final List<String> calls;

    RecordingHandler(String id, List<String> calls) {
        this.id = id;
        this.calls = calls;
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "demo.work".equals(context.getName());
    }

    @Override
    public void onStart(Observation.Context context) {
        calls.add(id + ":start");
    }

    @Override
    public void onScopeOpened(Observation.Context context) {
        calls.add(id + ":scope-opened");
    }

    @Override
    public void onEvent(
            Observation.Event event, Observation.Context context) {
        calls.add(id + ":event:" + event.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        calls.add(id + ":error");
    }

    @Override
    public void onScopeClosed(Observation.Context context) {
        calls.add(id + ":scope-closed");
    }

    @Override
    public void onStop(Observation.Context context) {
        calls.add(id + ":stop");
    }
}
~~~

### 11.2. Creating the Registry and Executing

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.ArrayList;
import java.util.List;

List<String> calls = new ArrayList<>();
ObservationRegistry registry = ObservationRegistry.create();

RecordingHandler first = new RecordingHandler("A", calls);
RecordingHandler second = new RecordingHandler("B", calls);

registry.observationConfig().observationHandler(
    new ObservationHandler.AllMatchingCompositeObservationHandler(
        first, second
    )
);

Observation observation =
    Observation.createNotStarted("demo.work", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("validated"));
} finally {
    observation.stop();
}

calls.forEach(System.out::println);
~~~

**How to read the output:**

- Seeing callbacks from **both A and B** at matching phases is the defining trait of an all-matching group.
- Phases `start`, `scope-opened`, `event`, `scope-closed`, and `stop` must appear matching the APIs invoked.
- Read the **actual printed order** to understand dispatch in your exact version. Never write business logic assuming a log sequence from another version.
- Switch the composite to `FirstMatchingCompositeObservationHandler(first, second)`. Because both A and B support the observation name, only A wins. Next, make A return `false` to verify B receives callbacks.
- To test errors, insert `observation.error(new IllegalStateException("demo"))` between scope and stop; selected handlers must receive `onError`.

This is a **learning experiment**. In a real Spring Boot app, the registry is configured by the framework and includes additional handlers. Results from a standalone registry only confirm Micrometer's behavior in the example, not production auto-configuration.

### 11.3. What to Assert in Automated Tests

If you must guard an order-dependent configuration, the highest-value tests verify:

1. Sender contexts select the sender handler, receiver contexts select the receiver handler; the default handler does not "steal" either case.
2. One observation creates exactly **one** meter measurement and the expected number of spans in a suitable tracing test.
3. Start/stop callbacks are paired and scopes close; error paths still complete the observation.
4. Registering a custom handler does not produce duplicate callbacks for the same instance.
5. When metadata is added late, assert which handlers read it at `onStop` and which require it at `onStart`.

These checks catch broken **behavior** instead of pinning an internal list order not genuinely used by the application.

## 12. Investigating Handler Ordering Issues

| Symptom | Likely Cause | How to Check and Fix |
| --- | --- | --- |
| Metrics appear but tracing vanishes after adding a handler | Meter and tracing handlers put into the same first-matching group; one blocks the other | Inspect composite config; separate independent capabilities from single-winner groups |
| Span exists but trace propagation is missing on downstream calls | Default tracing sits before sender/receiver in first-matching, or propagator is missing | Check specialized → default priority, instrumenter, and propagator |
| Duplicate spans seen for one request | Duplicate tracing handler registration or multiple handlers creating spans | Audit beans, registry customizers, and composite groups |
| Counter/Timer increments more than request count | Two meter handlers process one observation, or instrumentation creates overlapping observations | Inspect registry, annotations, and default instrumentation |
| Custom handler never runs | `supportsContext` returns false, bean unregistered, or observation blocked by predicate | Check support conditions, name/context, and registry config |
| First handler gets callbacks, second gets none | Both sit in first-matching and the first matches too broadly | Use all-matching for independent capabilities or reorder specialized cases |
| `outcome` missing in handler at start | Outcome tag is only attached after business work finishes | Read tag at stop; attach only upfront values before start |
| Wrong current scope in async execution | Context not propagated across threads/reactive chains | Use Spring/Reactor context propagation and keep scopes balanced |
| Fewer traces than Timer count | Tracing uses a sampler; metrics aggregate separately | Check sampler/exporter; never infer request count from trace count |
| Unusually high dashboard latency after adding handler | Callback performs synchronous I/O, heavy logging, or duplicate instrumentation | Measure handler overhead; minimize work inside callbacks |

### Isolation Method

When encountering any of the symptoms above, proceed step by step:

1. Identify the **observation name, context type**, and whether the operation actually executes `start()/stop()` properly.
2. List all configured handlers, especially checking for duplicates between auto-configuration and manual registration.
3. Inspect `supportsContext` in the relevant group and position inside `FirstMatchingCompositeObservationHandler`.
4. Confirm callbacks with bounded technical logging or a minimal registry experiment.
5. Verify downstream signals: Timer tags/`_count` in metrics, trace/span and propagation in tracing, trace IDs in logs if enabled.
6. If metrics/traces are still missing, inspect registry/exporter/sampler, since a handler executing does not guarantee data reached the backend.

## 13. Real-World Case: HTTP Request Across Two Services

Suppose `order-api` calls `inventory-api`. After deployment, dashboards still show HTTP server latency, yet request traces only show a span in `order-api` and fail to link into `inventory-api`.

Analysis steps aligned with this lesson:

- **Step 1 — check sender/receiver:** verify whether `order-api`'s HTTP client instrumentation creates a sender context and `inventory-api`'s server creates a receiver context.
- **Step 2 — check first-matching:** if the tracing group puts the default fallback ahead of sender/receiver handlers, the default handler may win too early; fix group priority and re-verify.
- **Step 3 — check propagation:** ensure compatible tracer/propagator and that trace headers are injected on the client and extracted on the server. Correct order does not substitute for propagation setup.
- **Step 4 — check scope:** check whether request context crosses an executor or reactive chain; if threads switch, configure matching context propagation.
- **Step 5 — check sampling/exporter:** a sampled-out trace or failing exporter also hides spans in the backend even when handlers run properly.
- **Step 6 — cross-check metrics:** inspect errors, p95 latency, and RPS to see whether the issue affects the whole system or specific requests; use logs with trace IDs to trace details.

The roles of the four observability pillars are clear here: **metrics** reveal trends, **traces** reveal path structure, **logs** capture events, and **registry plus handler ordering** determine how instrumentation turns into those signals.

## 14. Practice Exercises and Self-Check Questions

An application has three handlers:

- `MetricHandler` supporting every `Observation.Context`.
- `SenderTracingHandler` supporting only sender contexts.
- `DefaultTracingHandler` supporting regular contexts.

**Exercise A — choosing configuration:**

1. If all three are placed in a first-matching composite with `MetricHandler` first, what happens to tracing?
2. If sender and default are placed in an all-matching composite, what risk arises when both support a sender context?
3. Design the registry so metrics are always recorded, while tracing picks sender when appropriate and falls back to default otherwise.

**Exercise B — checking order:**

Use `RecordingHandler` from section 11 and compare all-matching against first-matching on `demo.work`. Record callback counts for A and B. Swap the two handlers' order to explain first-matching priority. Then add handler C with `supportsContext == false` to verify C receives no callbacks.

**Exercise C — lifecycle and metadata:**

Create an `Observation` with `channel=web` before `start`, then record `outcome=error` and `observation.error(ex)` after an exception occurs, before `stop`. Explain why a handler measuring at start may miss `outcome`, while a handler measuring at stop can read it.

**Self-check questions:**

1. A registry has 5 handlers, but only 2 support the context; does "5 registered" mean "5 useful callbacks"?
2. What is the difference between lifecycle callback order and first-matching priority order?
3. Why can placing a handler with `supportsContext == true` at the front of first-matching break sender tracing?
4. When two meter handlers both create a Timer, how can dashboard numbers be affected?
5. Before which callback in the stop flow is `ObservationFilter` applied? Why does this timing matter?
6. Why does a sampled-out trace not prove the tracing handler failed to run?
7. Why should you test Spring Boot integration with auto-configuration rather than only running standalone `ObservationRegistry.create()` examples?

**Completion criteria:** able to distinguish the four ordering layers; choose all-matching vs. first-matching properly; explain sender–receiver–default tracing order; instrument full lifecycles; avoid duplicate registration; and verify metrics, traces, logs, and context propagation in a real configuration.

## Key Takeaways

- `ObservationRegistry` holds handlers; `supportsContext` selects matching handlers; lifecycle dictates which callbacks fire.
- **All-matching** suits independent capabilities observing together; **first-matching** suits prioritized alternative strategies. Inside first-matching, place specialized handlers before fallback handlers.
- Keeping an independent **meter handler** alongside a **first-matching tracing handler** is the standard pattern; never let one capability "swallow" another.
- Spring Boot auto-registers `ObservationHandler` beans. Avoid repeating manual registration when auto-configuration is active.
- `ObservationFilter` runs before `onStop`; early vs. late metadata affects what each handler can read. Keep `supportsContext` stable across the lifecycle.
- Handler ordering is only one piece of observability: you still must manage tag cardinality, sampling, exporters, and propagation to diagnose latency and errors accurately.

## References

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
