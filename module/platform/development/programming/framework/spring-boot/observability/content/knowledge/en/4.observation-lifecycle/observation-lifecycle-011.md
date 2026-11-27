# Ensuring Observations Are Stopped on Every Branch

A Spring Boot service measures payment duration using Micrometer Observation. Successful requests have clear spans and normal timers, yet when exceptions occur or clients cancel requests, some spans linger abnormally long and dashboards lack numbers for failed transactions. A common cause is **an Observation that was started yet not stopped along every execution path**.

In the **SPRING_BOOT_OBSERVABILITY** module, setting up metrics, logs, and distributed tracing with Micrometer Observation is reliable only if each operation's lifecycle is managed properly. `start()`, `openScope()`, `error()`, and `stop()` carry distinct responsibilities. In particular, failing to call `stop()` on an observation prevents `ObservationHandler` instances from processing completion events as expected: timers may not record completely, spans may remain unclosed, and latency investigation data becomes skewed.

This lesson belongs to the **Observation Lifecycle** chapter and focuses on the practical question: **how do we guarantee every started observation is stopped exactly once, at the right time, across all success, error, early-return, asynchronous, and cancellation branches?**

After this lesson, you will be able to:

1. Distinguish `stop()` from closing a `Scope`, completing an HTTP request, and exporting a trace.
2. Apply `observe(...)` or `try/finally` to manage synchronous code lifecycles.
3. Never miss `stop()` on early `return`, exceptions, fallbacks, or multi-branch conditions.
4. Place `stop()` at the **actual completion point of work** in `CompletableFuture` and Reactor `Mono`.
5. Handle retries, timeouts, cancellations, and callbacks executing multiple times without stopping observations too early or repeatedly.
6. Verify lifecycles through handlers, metrics, traces, and log correlation rather than merely checking that requests return successfully.

## 1. A Started Observation Must Have a Defined Endpoint

Micrometer Observation describes a named activity, such as `inventory.reserve` or `checkout.pay`. Each execution creates a distinct occurrence with a start time, context, key-values, and outcome.

Minimal lifecycle:

```text
                   Observation Lifetime
createNotStarted()  start()                                 stop()
       |               |=======================================|
                       |  openScope()            closeScope()  |
                       |       |----------------------|         |
                       |     work currently executing           |
                       |                                           |
                 handler.onStart(...)                    handler.onStop(...)
```

- `createNotStarted(...)` merely creates the object; it does not start measuring.
- `start()` transitions the observation into the active state and notifies matching handlers.
- `openScope()` places the observation into the current execution context; helpful for trace parent–child relationships and log correlation.
- `Scope.close()` closes the *scope*, not replacing `Observation.stop()`.
- `stop()` marks the end of the **lifetime** and allows handlers to process completion, such as updating timers or finishing spans.

Never assume completing an HTTP request automatically stops a **custom observation** you created manually. Likewise, never treat closing a scope as completing the observation.

### 1.1. Lifecycle Invariants

For every occurrence that starts successfully, design code to satisfy three invariants:

| Invariant | Meaning | If Violated |
| --- | --- | --- |
| **Clear ownership** | One piece of code owns stopping the observation | Multiple layers assume another layer will call `stop()` |
| **Termination on every path** | Success, `return`, exceptions, fallbacks, and cancellations all reach termination | Failure paths go missing from duration/traces |
| **Stopped once, at the right time** | `stop()` reflects actual completion of work | Stopping early fakes short durations; stopping repeatedly makes callbacks/meters unpredictable |

`stop()` alone does not guarantee telemetry reached the backend. Metrics still depend on registries/exporters; tracing still depends on samplers, bridges, exporters, collectors, and storage. Yet if an observation fails to complete a valid lifecycle in the application, downstream stages cannot produce accurate data.

## 2. Prefer `observe(...)` for Synchronous Operations

When work runs synchronously and finishes when the method returns or throws, using the `observe(...)` API is the simplest way to avoid forgetting to stop:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class StockService {
    private final ObservationRegistry registry;
    private final StockGateway gateway;

    public StockService(ObservationRegistry registry, StockGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public boolean reserve(String sku, int quantity) {
        return Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("operation", "reserve")
                .lowCardinalityKeyValue("dependency", "inventory")
                .observe(() -> gateway.reserve(sku, quantity));
    }
}

// Sample interface; the application provides an implementation as a Spring bean.
interface StockGateway {
    boolean reserve(String sku, int quantity);
}
```

A single `observe(...)` call wraps the work in the required lifecycle: starting the observation, opening the scope, running the lambda, recording exceptions per API rules, and closing the scope/stopping when work finishes. Whether `gateway.reserve(...)` returns `true`, returns `false`, or throws an exception, the API's cleanup runs.

Notes:

- Do not additionally call `start()` or `stop()` manually on the same observation passed to `observe(...)`.
- `false` is a business outcome; it is **not automatically an exception**. If you need reservation rejection rates, define a corresponding outcome signal.
- `observe(...)` fits when **the lambda truly represents the entire work to be measured**. If the lambda merely kicks off work and immediately returns a future, this lifetime will exclude future execution time.
- Never place unbounded data such as `sku`, `userId`, `orderId`, tokens, or dynamic URLs into low-cardinality key-values.

### 2.1. Early Returns Must Still Stop

Example of an operation that checks preconditions and may return immediately:

```java
public boolean reserveIfAvailable(String sku, int quantity) {
    return Observation.createNotStarted("inventory.reserve", registry)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> {
                if (quantity <= 0) {
                    return false;   // Observation is still stopped.
                }
                if (!gateway.exists(sku)) {
                    return false;   // Observation is still stopped.
                }
                return gateway.reserve(sku, quantity);
            });
}
```

The `return false` branches sit **inside** the lambda; the API handles stopping the observation once the lambda returns. This lowers the risk of adding a future branch and forgetting cleanup.

## 3. When Managing Manually, Put `stop()` in `finally`

Sometimes you need explicit scope control, outcome labeling before stopping, or multiple steps to separate. In those cases, use `try-with-resources` for the scope and `finally` for the observation.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry registry;
    private final ReservationGateway gateway;

    public ReservationService(ObservationRegistry registry,
                              ReservationGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public ReservationResult reserve(String sku) {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry)
                        .lowCardinalityKeyValue("dependency", "inventory")
                        .start();

        try (Observation.Scope scope = observation.openScope()) {
            ReservationResult result = gateway.reserve(sku);

            observation.lowCardinalityKeyValue(
                    "outcome", result.accepted() ? "accepted" : "rejected");

            return result; // finally still runs before returning to the caller.
        } catch (RuntimeException | Error failure) {
            observation.error(failure);
            observation.lowCardinalityKeyValue("outcome", "error");
            throw failure;
        } finally {
            observation.stop();
        }
    }
}

record ReservationResult(boolean accepted) { }

interface ReservationGateway {
    ReservationResult reserve(String sku);
}
```

This pattern uses Java 17+ and compatible Spring Boot/Micrometer Observation dependencies. The example defines a minimal `ReservationGateway` to keep focus on lifecycle handling.

Branch-by-branch breakdown:

1. **Success:** `gateway.reserve` returns a result; `outcome` tag is attached; `return` executes yet Java still runs `finally`, stopping the observation.
2. **Valid rejection:** `accepted=false` follows the normal Java return path while carrying `outcome=rejected`; the observation stops.
3. **Exception:** `catch` invokes `observation.error(failure)` so handlers receive failure details, then rethrows. `finally` still stops.
4. **Errors opening or closing scope:** if a `RuntimeException` or `Error` occurs inside the `try` scope, `catch`/`finally` still executes. This does not imply every error from a handler or exporter is safely recoverable.
5. **Scope termination:** `try-with-resources` closes the scope before `finally` calls `stop()`.

Cases where `start()` itself throws due to a misbehaving handler require separate scrutiny: never assume an observation always starts cleanly. The pattern above applies to successfully started observations; for standard operations, rely on framework/API-managed lifecycles rather than building custom recovery logic at the instrumentation layer.

### 3.1. Why Not Call `stop()` at the End of the Method?

The snippet below looks reasonable yet is buggy:

```java
Observation observation = Observation
        .createNotStarted("checkout.pay", registry).start();

if (paymentAlreadyCompleted) {
    return receipt; // Skips stop().
}

chargeCard();        // If this throws, also skips stop().
observation.stop();
return receipt;
```

Placing `stop()` on a trailing line covers only the path reaching that line. A new `return`, `throw`, timeout, or dependency error skips it completely.

Fix using `try/finally`:

```java
Observation observation = Observation
        .createNotStarted("checkout.pay", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    if (paymentAlreadyCompleted) {
        return receipt;
    }

    chargeCard();
    return receipt;
} catch (RuntimeException | Error failure) {
    observation.error(failure);
    throw failure;
} finally {
    observation.stop();
}
```

If multiple methods return different types, you do not have to cram all logic into one giant method; the core rule is that **every branch must live inside a single cleanup mechanism with clear ownership**.

### 3.2. Never Arbitrarily `return`, `throw`, or Override Results Inside `finally`

`finally` is for cleanup and must not alter business logic:

```java
try {
    return gateway.reserve(sku);
} finally {
    observation.stop();
    // Do not: return false;
    // Do not: throw new IllegalStateException("cleanup");
}
```

A `return` inside `finally` suppresses genuine exceptions; a new exception thrown during cleanup replaces the original exception. If your project has custom `ObservationHandler` instances or exporters capable of throwing during cleanup, apply a consistent telemetry error-handling policy instead of blindly swallowing exceptions.

## 4. Distinguishing Lifetime, Scope, and Error Recording

Three actions are easily lumped together:

| Action | Responsibility | Replaces `stop()`? |
| --- | --- | --- |
| `observation.error(exception)` | Attaches error to context and notifies handlers of failure | No |
| `scope.close()` | Restores the current context on the executing thread | No |
| `observation.stop()` | Ends the occurrence's lifetime and fires completion callbacks | This is the exact call you must guarantee |

Example:

```text
request received
  |
  +-- checkout observation START
  |     |
  |     +-- scope OPEN
  |     |    |
  |     |    +-- call payment API
  |     |         |
  |     |         +-- timeout -> error(timeout)
  |     |
  |     +-- scope CLOSE
  |
  +-- checkout observation STOP
  |
request returns error to client
```

In systems with a tracing handler, opening the scope exposes the active trace/span context to logs emitted during processing; closing the scope prevents stale context from affecting subsequent work on the same thread. Both actions remain distinct from ending the lifetime.

A business failure like `payment declined` may call for an `outcome=declined` tag rather than an exception. Conversely, genuine exceptions should be passed to `observation.error(...)` when managing lifecycles manually so handlers have full failure evidence.

### 4.1. Choosing When to Attach Tags

Static tags known **before start**, such as `operation=reserve`, can be set up front. Outcome tags known only **after work runs**, such as `outcome=accepted|rejected|error`, should be attached **before stop** if handlers need them on completion.

```java
Observation observation = Observation
        .createNotStarted("inventory.reserve", registry)
        .lowCardinalityKeyValue("operation", "reserve")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    boolean accepted = gateway.reserve(sku, quantity);
    observation.lowCardinalityKeyValue(
            "outcome", accepted ? "accepted" : "rejected");
    return accepted;
} catch (RuntimeException | Error e) {
    observation.error(e);
    observation.lowCardinalityKeyValue("outcome", "error");
    throw e;
} finally {
    observation.stop();
}
```

Depending on handler type, conventions, and when context is read, adding tags after `start()` can have different effects. Verify output in your target backend; avoid attaching tags after the observation has stopped and expecting already-exported timers/spans to update retroactively.

## 5. Checklist of Synchronous Branches Commonly Missed

| Branch | Easy Mistake | Fix |
| --- | --- | --- |
| Success path | Putting `stop()` at the end, then adding a new branch later | Use `observe(...)` or `finally` |
| Early `return` | Returning before cleanup executes | Keep all decisions inside `try` or the `observe` lambda |
| Exception | `throw` bypasses stop or skips recording error | `catch` → `error` → rethrow; `finally` → `stop` |
| Fallback | Catching an exception and returning defaults silently | Record explicit outcome/fallback; stop in finally |
| Invalid input preconditions | Starting too early so metrics include unnecessary validation | Define clear measurement boundaries; if started, still stop |
| Retry | Opening observations per attempt yet stopping only once at the end | Separate overall observation from per-attempt observations |
| Timeout | Method returns timeout while background work continues | Define boundary clearly: client-facing timeout vs. actual work |
| Cleanup throws | New exception masks primary exception | Standardize telemetry error handling; never `return` in `finally` |

A pragmatic design rule: **an Observation belongs to the code that created it**. Other components may add key-values or events when allowed, yet should not stop a caller's observation without owning its lifetime boundaries.

## 6. With `CompletableFuture`: Do Not Stop Right After Scheduling Work

This is a widespread bug in asynchronous code:

```java
public CompletableFuture<Receipt> payAsync() {
    return Observation.createNotStarted("checkout.pay", registry)
            .observe(() -> paymentClient.payAsync());
}
```

The snippet stops the observation the moment `payAsync()` **returns the future object**. Payment-layer work may still run for hundreds of milliseconds or several seconds afterward. As a result, `checkout.pay` timers/spans reflect only the time to *initiate* the async call, not the time until completion.

### 6.1. Tying the Stop Point to the Future's Terminal Completion

The following example assumes `PaymentClient.payAsync()` returns `CompletableFuture<Receipt>` and controls cleanup via a completion callback:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class PaymentOrchestrator {
    private final ObservationRegistry registry;
    private final PaymentClient client;

    public PaymentOrchestrator(ObservationRegistry registry,
                               PaymentClient client) {
        this.registry = registry;
        this.client = client;
    }

    public CompletableFuture<Receipt> payAsync() {
        Observation observation =
                Observation.createNotStarted("checkout.pay.async", registry)
                        .lowCardinalityKeyValue("dependency", "payment")
                        .start();

        AtomicBoolean stopped = new AtomicBoolean(false);

        Runnable stopOnce = () -> {
            if (stopped.compareAndSet(false, true)) {
                observation.stop();
            }
        };

        try {
            CompletableFuture<Receipt> source;

            // Scope for initiation phase; future continues after scope closes.
            try (Observation.Scope scope = observation.openScope()) {
                source = client.payAsync();
            }

            return source.whenComplete((receipt, failure) -> {
                try (Observation.Scope scope = observation.openScope()) {
                    if (failure != null) {
                        observation.error(failure);
                    }
                } finally {
                    stopOnce.run();
                }
            });
        } catch (RuntimeException | Error setupFailure) {
            observation.error(setupFailure);
            stopOnce.run();
            throw setupFailure;
        }
    }
}

interface PaymentClient {
    CompletableFuture<Receipt> payAsync();
}

record Receipt(String reference) { }
```

This handles two scenarios:

1. **Immediate setup failure:** `catch` records the error and stops the observation.
2. **Source future finishes:** the `whenComplete` callback records any failure and calls `stopOnce`, even if the callback throws.

`AtomicBoolean` here enforces **single-winner stop semantics**, necessary if completion paths could race. Even so, this is a lifecycle teaching pattern, not a full orchestration layer for every future system.

**Distinguish cancelling a future from stopping real work.** Cancelling a dependent `CompletableFuture` does not necessarily cancel ongoing work in a dependency. A future can transition to completed/cancelled while backend execution keeps running. If your goal is measuring time *until the user receives a result or times out*, stopping at that boundary makes sense. If your goal is measuring *actual dependency processing time*, tie stop to that work's own completion signal. For cancellations, explicitly define cancel propagation and dedicated cleanup paths.

This matters for distributed tracing: a client-call span may finish at timeout while server-side work keeps running; the two spans can legitimately have different durations.

### 6.2. Scopes Do Not Automatically Cross onto New Threads

The scope opened on the thread calling `payAsync()` closes on that thread. When the callback runs on another thread, the scope's context **is not automatically inherited in all cases**. Opening a scope inside the callback sets the current observation for the callback body, yet does not guarantee processing *inside* `PaymentClient` received the right trace context.

In Spring Boot, verify HTTP client instrumentation, header propagation (`traceparent`), executors, and Micrometer Context Propagation. Calling `stop()` at the right time solves the lifecycle; **propagating trace context** across execution boundaries is a separate responsibility.

## 7. With Reactor: Stop the Observation When the Stream Terminates or Cancels

In Spring WebFlux/Reactor applications, `Mono` and `Flux` are publishers; a cold publisher only executes upon subscription. Building a publisher does not mean work has run.

The following is a classic bug:

```java
public Mono<Receipt> payReactive() {
    return Observation.createNotStarted("checkout.pay.reactive", registry)
            .observe(() -> paymentClient.payReactive());
}
```

The observation can finish right after returning the `Mono`, before any subscriber triggers the actual call.

### 7.1. Create One Observation per Subscription, Stop in `doFinally`

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import reactor.core.publisher.Mono;

public class ReactivePaymentService {
    private final ObservationRegistry registry;
    private final ReactivePaymentClient client;

    public ReactivePaymentService(ObservationRegistry registry,
                                  ReactivePaymentClient client) {
        this.registry = registry;
        this.client = client;
    }

    public Mono<Receipt> pay() {
        return Mono.defer(() -> {
            Observation observation = Observation
                    .createNotStarted("checkout.pay.reactive", registry)
                    .lowCardinalityKeyValue("dependency", "payment")
                    .start();

            try {
                return client.pay()
                        .doOnError(observation::error)
                        .doFinally(signalType -> observation.stop());
            } catch (RuntimeException | Error setupFailure) {
                observation.error(setupFailure);
                observation.stop();
                throw setupFailure;
            }
        });
    }
}

interface ReactivePaymentClient {
    Mono<Receipt> pay();
}
```

Because the Observation is created *inside* `Mono.defer(...)`, each normal subscription gets its own occurrence. `doFinally` is a hook triggered once the publisher receives a terminal signal:

- `ON_COMPLETE`: completed successfully, including empty Monos.
- `ON_ERROR`: completed with an error, typically already recorded by `doOnError`.
- `CANCEL`: subscription cancelled; cleanup is still required.

This illustrates a simple reactive operation; additional operators (`retry`, `timeout`, `share`, `cache`) and their placement can change the *actual measured lifetime*. For example, if `retry` sits **inside** the observed chain, one observation measures all attempts combined; if `retry` sits outside and re-subscribes to `Mono.defer`, each attempt creates a new occurrence.

**Limitations of this example:** `doFinally` guarantees a cleanup hook for properly subscribed chains, yet **does not propagate scopes through Reactor Context** and does not automatically instrument downstream calls. When traces must span operators or threads, use Reactor/Micrometer context propagation integrations and measure real outputs. In complex pipelines, define clearly which portion belongs to the observation, since downstream operators may still run after `doFinally`.

### 7.2. Is Cancellation an Error?

Not by default. A client closing its connection can cancel the subscription without representing a business-logic exception. If cancellation is a signal worth tracking, define an explicit outcome like `outcome=cancelled` or a dedicated meter with bounded values. Some environments turn timeouts into `TimeoutException`, while others turn them into cancellations; never force every cancellation into `error` without defining semantics first.

In practice, when a cancel signal cannot stop real backend work, observe **two boundaries**:

- Time from client request until client receives timeout/cancellation.
- Time the actual task runs until the system finishes or aborts processing.

These are two distinct measurements and require different observation names if you want to compare them.

## 8. Retries, Timeouts, and Layered Instrumentation

### 8.1. Retries: Measuring Total Time and Individual Attempts

Example of a payment operation retrying up to three times:

```text
checkout.pay (overall observation)
    |
    +-- payment.attempt #1 -> timeout -> stop
    +-- backoff 200 ms
    +-- payment.attempt #2 -> 503     -> stop
    +-- backoff 400 ms
    +-- payment.attempt #3 -> OK      -> stop
checkout.pay -> stop
```

You can use an overall `checkout.pay` observation to measure actual user-perceived wait time, including retries and backoff. If per-attempt diagnostics are needed, create a child `payment.attempt` observation for **each attempt** using `observe(...)` or `try/finally` right inside the loop.

Do not create a single child observation before the loop and stop it after the first attempt, nor start a new one for the next attempt while forgetting to stop the prior occurrence. Retry counts can be tracked as dedicated metrics/tags with bounded values; avoid using per-request IDs as metric labels.

### 8.2. Timeouts: Identifying What Actually Ended

A gateway timeout can occur before Spring Boot finishes processing. If you stop a custom observation when the request aborts, it describes the request-bound lifetime. Yet if a task is detached to run in the background and outlives the request, measure that task with a **separate** observation that has clear ownership and stops upon true completion.

Never use `Thread.sleep(...)`, timers, or schedulers just to "helpfully stop" an observation after a fixed delay regardless of whether work finished. Doing so turns slow requests into artificially short timers.

### 8.3. Framework Instrumentation vs. Custom Code

Spring Boot Actuator, HTTP server/client instrumentation, and Micrometer integrations already create observations at standard boundaries. You do not need manual observations duplicating the exact same HTTP call unless you have a distinct business question.

Example of sensible layering:

| Boundary | Instrumentation Type | Expected Stop Point |
| --- | --- | --- |
| HTTP server request | Framework instrumentation | When request processing completes per framework boundary |
| `checkout.place-order` | Custom business observation | When the entire order-placement flow finishes |
| HTTP client payment call | HTTP client instrumentation | When the client call finishes/fails per client boundary |
| Background reconciliation job | Custom background work | When the job actually finishes or cancels |

Having multiple spans in one trace is completely normal when spans describe **distinct operations**. If you see nearly identical spans at the exact same boundary, audit for duplicate instrumentation.

## 9. How Does `stop()` Affect Metrics, Traces, and Logs?

An Observation can feed multiple handlers depending on `ObservationRegistry` configuration:

| Signal | Role of Start/Stop | Signs of Improper Termination |
| --- | --- | --- |
| **Metrics** | Metrics handlers usually measure duration from start to stop and update meters on completion | Timer counts/durations miss failures or report artificially short times |
| **Tracing** | Tracing handlers can create and finish spans, attaching errors/tags | Spans missing, closed late, or durations mismatching intended boundaries |
| **Logs** | Scope/tracing context gives logs emitted during work `traceId`/`spanId` when configured | Logs after scope close lose correlation; logs are not auto-created by stop |
| **Exporter/collector** | Receives data from registry/bridge and ships it to backends | Even with proper stop, data may be missing due to sampling, exporter errors, or backend issues |

Crucial point: **calling stop properly is necessary, yet not sufficient for telemetry to appear on dashboards**. A trace dropped by sampling can still have a spotless lifecycle; a filtered meter or unexported registry can likewise remain absent in the backend. Always separate three layers when verifying:

1. **Application code:** Are start, scope, and stop placed at the right boundaries?
2. **Instrumentation:** Does the registry have matching handlers/conventions? Are tags valid?
3. **Data pipeline:** Are metrics registries, tracing bridges, exporters, collectors, and storage healthy?

### 9.1. Spring Boot 3.x Configuration Example

With Spring Boot 3.x managing dependency versions via the Spring Boot BOM, Actuator provides core observability integrations:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Add when exporting Prometheus metrics -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>

<!-- Add when tracing via OpenTelemetry -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<!-- Export traces to collector via OTLP -->
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
```

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

In a lab environment, call an endpoint triggering `inventory.reserve` and inspect:

```bash
curl -fsS http://localhost:8080/actuator/metrics
curl -fsS http://localhost:8080/actuator/metrics/inventory.reserve
curl -fsS http://localhost:8080/actuator/prometheus
```

Meters appear only after the operation executes and a matching metrics handler is present. In production environments, never expose Actuator endpoints publicly without proper network controls and authorization.

**Version note:** Spring Boot 4.x introduces changes to starters and OTLP/tracing configuration compared to 3.x. When applying this in practice, check official documentation for your exact running version. The semantics of `start`/`scope`/`stop` and lifetime ownership remain central.

## 10. How to Prove Every Branch Stops Its Observation

Do not verify solely by "calling the API and seeing HTTP 200." Exercise controlled branches and verify both lifecycle callbacks and output signals.

### 10.1. Attaching a Probe Handler to Count Starts and Stops

In a standalone test snippet, register a handler counting callbacks:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

final class LifecycleProbe
        implements ObservationHandler<Observation.Context> {

    final AtomicInteger started = new AtomicInteger();
    final AtomicInteger stopped = new AtomicInteger();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        started.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stopped.incrementAndGet();
    }
}

// In a standalone test:
ObservationRegistry registry = ObservationRegistry.create();
LifecycleProbe probe = new LifecycleProbe();
registry.observationConfig().observationHandler(probe);

Observation.createNotStarted("demo.operation", registry)
        .observe(() -> "completed");

// After the synchronous call:
// probe.started.get() == 1
// probe.stopped.get() == 1
```

Place the snippet above inside an appropriate test class/method; it is not a complete standalone compilable Java file as written. If the framework already registers other handlers, never replace the shared production registry with a test registry just to count calls.

### 10.2. Branch Verification Matrix

| Scenario Exercised | Expected Lifecycle Behavior | Additional Checks |
| --- | --- | --- |
| Successful execution | 1 start, 1 stop | Duration/timer and sample log/trace |
| Early return on validation | 1 start, 1 stop if observation started | Outcome not conflated with exceptions |
| Dependency exception | 1 start, 1 error, 1 stop if handler records errors | Exception still propagates to caller |
| Fallback after exception | 1 start, 1 stop | Business fallback measured per definition |
| Future completes later | Stop at chosen completion, not when future is returned | Compare duration against wall-clock time |
| Future setup fails | 1 start, 1 stop | Failure recorded |
| Reactive completion | 1 start, 1 stop per subscription | Watch out for retries/re-subscriptions |
| Reactive error | 1 start, 1 stop per subscription | Error signal recorded |
| Reactive cancellation | Scope/observation cleaned up on chain cancellation | Did downstream work actually stop or keep running? |
| Race between timeout and callback | Clear single owner ends observation; never stopped twice | Use guards/synchronization when needed |

When checking lifecycles, **verify start/stop counts per individual observation occurrence** rather than only comparing global totals. Under concurrent requests, global totals can look balanced even when one observation stopped twice and another never stopped at all.

### 10.3. Signals from a Running System

- Gateway request count far exceeds custom observation timer count: requests may skip the instrumented branch, return early, or fail to stop; denominators may also differ.
- Traces have spans missing durations or terminating abnormally: inspect scopes, start/stop, completion callbacks, sampling, and exporters.
- Logs have `traceId` yet no trace is found: trace may have been dropped by sampling, backend may lack ingestion, or trace context broke; do not immediately blame missing `stop()`.
- Custom async step p99 is far smaller than client latency: check whether the observation only measures future/Mono creation time.
- Metric tag `outcome` is missing on certain branches: inspect tag ordering before stop, exception branches, and when handlers read context.

## 11. Practice Exercise: Finding Lifetime Leaks

Suppose you inherit the following code:

```java
public String fulfill(String orderId) {
    Observation observation = Observation
            .createNotStarted("order.fulfill", registry)
            .start();

    if (orderId == null) {
        return "INVALID";
    }

    try (Observation.Scope scope = observation.openScope()) {
        return fulfillmentService.fulfill(orderId);
    } catch (RuntimeException e) {
        return "FALLBACK";
    }
}
```

Identify at least four issues:

1. The observation starts yet has no `stop()` on any branch.
2. `return "INVALID"` before `try` skips cleanup on the input validation branch.
3. The exception branch returns a fallback without calling `observation.error(e)` or recording a fallback signal.
4. No clear stop ownership exists as branches grow; traces/timers will miss data.

One fix using `try/finally`:

```java
public String fulfill(String orderId) {
    Observation observation = Observation
            .createNotStarted("order.fulfill", registry)
            .lowCardinalityKeyValue("operation", "fulfill")
            .start();

    try (Observation.Scope scope = observation.openScope()) {
        if (orderId == null) {
            observation.lowCardinalityKeyValue("outcome", "invalid");
            return "INVALID";
        }

        try {
            String result = fulfillmentService.fulfill(orderId);
            observation.lowCardinalityKeyValue("outcome", "completed");
            return result;
        } catch (RuntimeException failure) {
            observation.error(failure);
            observation.lowCardinalityKeyValue("outcome", "fallback");
            return "FALLBACK";
        }
    } finally {
        observation.stop();
    }
}
```

This example only illustrates lifecycle management. In real applications, define which fallbacks are acceptable, which errors must reach clients, and which data is permitted in metrics/logs. `orderId` is dynamic data and must never be used as a metric label.

### Self-Check Questions

**Question 1.** If `Scope.close()` has run yet `Observation.stop()` has not been called, is the observation finished?

**Answer:** No. Scope closes the current context; stop ends the lifetime and notifies handlers. Both mechanisms must be managed properly.

**Question 2.** Why can `observe(() -> client.callAsync())` report inaccurate durations?

**Answer:** The lambda may immediately return a future/publisher before work finishes. The observation measures creation or scheduling time. Attach the stop point to the actual completion signal per your defined boundary.

**Question 3.** When a Reactor chain is cancelled, should the observation wait forever for natural completion?

**Answer:** No. Once the subscription ends, cleanup must run, such as via `doFinally`. Still, clarify whether you are measuring subscription lifetime or real backend work, since cancellation does not always halt backend processing.

**Question 4.** Should an `orderId` tag be attached to timers to find timed-out orders?

**Answer:** No. Dynamic IDs cause high cardinality and may expose protected data. Use bounded outcome tags; use log/trace correlation under appropriate data policies to investigate individual requests.

## 12. Principles to Take to Production

- **Define measurement boundaries before starting:** requests, business steps, individual attempts, entire retry sequences, and background jobs are distinct lifetimes.
- **Assign a single stop owner:** use `observe(...)` for synchronous code, `try/finally` under manual control, and terminal callbacks or `doFinally` for async/reactive code.
- **Cover every path:** early returns, exceptions, fallbacks, timeouts, cancellations, retries, and shutdowns; never rely on "someone else stopping it later."
- **Use close scope and stop for their proper roles:** scopes manage current context; stop manages lifetime. Reliable traces/logs also require propagation across threads, HTTP, and message brokers.
- **Record errors and outcomes meaningfully:** distinguish technical exceptions from business rejections; attach stable low-cardinality keys before handlers finalize.
- **Cross-check across multiple signals:** metrics quantify frequency/duration, traces show sample paths, logs provide events; sampling and exporters can prevent backends from storing every trace.
- **Verify per branch:** observe start/stop on the same occurrence and compare durations against real work, especially in async/reactive flows.

### References

- [Micrometer — Observation API and core concepts](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
