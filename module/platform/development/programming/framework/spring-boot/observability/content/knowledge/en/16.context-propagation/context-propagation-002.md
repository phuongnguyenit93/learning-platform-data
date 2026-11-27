# Opening a scope on the current thread with Micrometer and OpenTelemetry

In the **Context propagation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, opening a scope on the current thread is how an **Observation or Span becomes the active context** for a block of execution. As a result, child calls can obtain the parent context to create related spans, integrated components can add metadata to the right observation, and logging integration can correlate logs with the active trace.

With Spring Boot, Micrometer Observation and Micrometer Tracing provide framework-level context management APIs. OpenTelemetry has its own context/scope API. Despite the different names, the core principle is the same: **open a scope at the start of the work segment that needs context, and close the scope as soon as that segment finishes**. A scope is usually tied to the current thread; it does not automatically transfer to an executor, another thread, or a downstream service.

## 1. Context, current observation, and current span

An HTTP request can pass through a controller, service, and repository. When tracing instrumentation creates a server span, that span can become the **current span** while handling the request. A custom observation or child span opens a scope for its own code segment; when it finishes, the previous context is restored.

```text
HTTP request
    |
    v
HTTP server span (current on request thread)
    |
    +--> controller
           |
           +--> order.confirm observation (open scope)
                   |
                   +--> inventory.reserve (child span/observation)
                   |
                   +--> payment.authorize (child span/observation)
           |
           +--> after order.confirm scope closes:
                  HTTP server span is current again
```

In the diagram:

- **Context** holds the information to propagate, such as trace ID, span ID, parent relationship, and context values.
- **Current observation/span** is the observation or span currently set in the execution context at the moment.
- **Scope** is the temporary range in which that context is active. Closing the scope restores the context that was active before opening the scope.
- **Span lifecycle** is the lifetime of a span from start to end. Closing a scope does not mean ending the span.

A single thread can handle multiple requests sequentially. Opening and closing scopes properly prevents context from a previous request from "leaking" into subsequent work on the same thread.

## 2. Opening and closing a scope with Micrometer Observation

`ObservationRegistry` manages observation handlers, conventions, predicates, and filters. A custom observation can be created, started, opened in a scope to become current, and then stopped:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class InventoryService {
    private final ObservationRegistry registry;

    public InventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void reserve() {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry);

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            // Within this block, observation is current.
            checkInventory();
            reserveStock();
        } catch (RuntimeException ex) {
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private void checkInventory() {
        // Business logic.
    }

    private void reserveStock() {
        // Business logic.
    }
}
```

Sequence in the example:

1. `createNotStarted(...)` creates an observation with a stable name without starting measurement yet.
2. `start()` starts the observation.
3. `openScope()` places the observation into the active scope on the calling thread.
4. The `try` block executes the work. Built-in instrumentation can read the current observation/span according to the context supported by the registry/tracing bridge.
5. Upon exiting `try`, `Scope.close()` is called automatically via try-with-resources, restoring the previous context.
6. `stop()` ends the observation in `finally` even if the code throws an exception.

**Do not confuse `Scope.close()` with `observation.stop()`.** Closing the scope only restores the current context; `stop()` ends the lifecycle and allows handlers to finish processing the observation.

### Shorter approach with observe(...)

If you only need to run a synchronous block of work without manually managing scope, events, or dynamic outcomes, you can use:

```java
Observation.createNotStarted("inventory.reserve", registry)
        .observe(() -> {
            checkInventory();
            reserveStock();
        });
```

`observe(...)` manages the observation lifecycle and scope for the callback according to Micrometer's API, reducing the risk of forgetting to close the scope or stop. When you need to attach key-values based on the result, handle exceptions conditionally, or control exact timing, the manual API in the previous example may be more suitable.

If you want to record a business outcome, use tags with a bounded set of values such as `outcome=reserved/out_of_stock/error`. Do not use order ID, user ID, or verbatim exception messages as low-cardinality metric tags.

## 3. Opening a scope with Micrometer Tracing

When you need to work directly with a span instead of an observation, Micrometer Tracing provides `Tracer` and an API to open a span in scope:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

public class PaymentService {
    private final Tracer tracer;

    public PaymentService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void authorize() {
        Span span = tracer.nextSpan()
                .name("payment.authorize")
                .start();
        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            // The payment.authorize span is current in this block.
            callPaymentProvider();
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }

    private void callPaymentProvider() {
        // Business logic or instrumented HTTP client.
    }
}
```

`tracer.nextSpan()` typically creates a span based on the current context if present, so if the code is running inside a server/business span, the new span can be a child span. `tracer.withSpan(span)` opens a `SpanInScope` so this span becomes current; closing the scope restores the previous span. `span.end()` ends the lifecycle.

Micrometer Tracing types/APIs are backed by the corresponding bridge; the project must have a configured tracing implementation. Without an appropriate tracing bridge/provider, do not assume `Tracer` will always create recording spans or that data will appear in the backend.

### Why doesn't creating a span automatically make it current?

Separating the two steps gives the code explicit control:

- You can create a span and attach attributes before activating it.
- Only a specific block of code needs that span as the active context.
- Multiple spans can be managed with different lifecycles, while only the span in scope becomes current in the execution context.

If you call a child span when the parent span has not been made current or without passing an explicit parent context, the parent-child relationship may not turn out as expected. Therefore, open the proper scope before calling code that creates child spans.

## 4. Nested scopes and restoring parent context

A request can open scope A, and then inside A open scope B. When B closes, A must become current again; when A closes, the original context (e.g., the HTTP server span) is restored.

```java
Observation root = Observation.createNotStarted("order.confirm", registry);
root.start();
try (Observation.Scope rootScope = root.openScope()) {
    // root is current.

    Observation child =
            Observation.createNotStarted("inventory.reserve", registry);
    child.start();
    try (Observation.Scope childScope = child.openScope()) {
        // child is current; root is the parent context underneath.
        reserveStock();
    } finally {
        child.stop();
    }

    // child scope is closed: root is current again.
    validateOrder();
} finally {
    // root scope is closed: previous context returns.
    root.stop();
}
```

Restoration diagram:

```text
Initial context (e.g. HTTP span)
        |
        | open root scope
        v
    root = current
        |
        | open child scope
        v
    child = current
        |
        | close child scope
        v
    root = current
        |
        | close root scope
        v
Initial context = current
```

Closing scopes in the **reverse order of opening** is the principle of nested structures (LIFO). Try-with-resources helps enforce this when the code structure is clear. Do not store a scope and close it in another callback or after the thread has moved on to other work.

If a piece of code opens scope B without closing it, subsequent calls on the thread may keep seeing B as current, causing child spans to get the wrong parent, wrong log correlation, or request information to leak into later work.

## 5. Context when a scope closes and when a span ends

The following four operations are not interchangeable:

| Operation | Effect | When to perform |
| --- | --- | --- |
| `span.start()` / `observation.start()` | Starts the lifecycle | When measurement begins |
| `tracer.withSpan(span)` / `observation.openScope()` | Sets context as current in the active scope | Around code needing current context |
| `scope.close()` | Restores previous current context | When leaving the scope |
| `span.end()` / `observation.stop()` | Ends the lifecycle and completes telemetry processing | When the measured operation finishes |

A span can remain un-ended after its scope closes if the design keeps the lifecycle until another milestone. However, doing so requires strict management, because an un-ended span will not yet be processed/exported as a finished span.

Conversely, ending a span while its scope is still open can leave code continuing to run with an already-ended span as current. This state is hard to interpret and error-prone; close the scope before ending the span in the usual structure:

```java
Span span = tracer.nextSpan().name("inventory.reserve").start();
try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    reserveStock();
} finally {
    span.end();
}
```

With Observation:

```java
observation.start();
try (Observation.Scope scope = observation.openScope()) {
    reserveStock();
} finally {
    observation.stop();
}
```

If an exception occurs, record the error using the appropriate API (such as `observation.error(ex)` or `span.error(ex)` with the corresponding bridge), then preserve the business exception behavior. Do not swallow errors just to make a span status look clean.

## 6. How do OpenTelemetry Context and Scope differ from Micrometer?

In the OpenTelemetry API, a span can be made current with `span.makeCurrent()`. The API returns an `io.opentelemetry.context.Scope` that the code must close:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public void reserveWithOtel(Tracer tracer) {
    Span span = tracer.spanBuilder("inventory.reserve").startSpan();
    try (Scope scope = span.makeCurrent()) {
        // Span.current() returns this span in the active scope.
        reserveStock();
    } catch (RuntimeException ex) {
        span.recordException(ex);
        span.setStatus(io.opentelemetry.api.trace.StatusCode.ERROR);
        throw ex;
    } finally {
        span.end();
    }
}
```

API comparison:

| Platform | Open scope | Get current context/span | Close scope |
| --- | --- | --- | --- |
| Micrometer Observation | `observation.openScope()` | `Observation.currentObservationScope()` or version-appropriate context/handler API | `Observation.Scope.close()` |
| Micrometer Tracing | `tracer.withSpan(span)` | `tracer.currentSpan()` | `Tracer.SpanInScope.close()` |
| OpenTelemetry API | `span.makeCurrent()` | `Span.current()` or `Context.current()` | `io.opentelemetry.context.Scope.close()` |

Do not mix up `Scope` classes just because they share the same name. `io.opentelemetry.context.Scope` belongs to OpenTelemetry context, whereas `Observation.Scope` belongs to Micrometer Observation. A tracing bridge can connect them at the integration layer, but application code must use the right type and lifecycle API.

If the application already uses Spring Boot/Micrometer Tracing, prefer Observation or Micrometer Tracer in application code to avoid unsynchronized manual SDK/global context initialization. Use the OpenTelemetry API directly when the project has explicitly chosen the OTel SDK/agent and has clear pipeline ownership.

## 7. Log correlation while a scope is active

Within the scope of a span that has been set as current, logging integration can read the trace context and put `traceId`/`spanId` into MDC. Logs may look like this (illustrative):

```text
orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7 "Reservation started"
orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b8 "Reservation complete"
```

Both logs share the same Trace ID, while the Span ID can differ if they were recorded in different spans. If a log is written outside the scope, MDC may no longer hold the expected trace/span IDs or may have been restored to the parent context.

Merely opening a scope does not guarantee logs automatically get IDs. You need a tracing bridge, logging integration, MDC scope decoration, and a pattern/JSON encoder reading the right MDC keys. When handling MDC manually, you must **restore the previous value** in finally/try-with-resources; do not call `MDC.clear()` indiscriminately because it can wipe metadata set by the framework or other request filters.

Log correlation helps locate specific traces, but a Trace ID is not a credential. Do not put tokens, cookies, request bodies, or personal data into MDC/attributes; control access to log/trace backends.

## 8. Opening a scope does not automatically propagate context to another thread

This is the most common source of bugs. Scopes usually rely on context attached to the **currently executing thread**. For example:

```java
try (Observation.Scope scope = observation.openScope()) {
    // HTTP thread currently has observation as current.
    CompletableFuture.runAsync(() -> {
        // Different thread: do not assume observation is automatically present here.
        performAsyncWork();
    });
}
```

The callback of `CompletableFuture.runAsync(...)` may run on the common pool or another thread, so the HTTP thread's current context is not copied automatically. As a result, `tracer.currentSpan()` may return `null`, logs may lack a Trace ID, or downstream calls may create a new trace. The original thread's scope still closes when exiting the `try` block; it does not wait for the callback to complete.

### Using an executor with context propagation

With Spring Framework versions supporting `ContextPropagatingTaskDecorator` (such as Spring Framework 6.1+), you can configure an executor to capture/restore context when a task is submitted:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean(name = "observedExecutor")
    ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Then you must actually use the configured executor:

```java
observedExecutor.execute(() -> {
    // Context has been restored for the task by the decorator if
    // appropriate ThreadLocalAccessor/tracing integrations are registered.
    processOrderAsync();
});
```

Simply creating an executor bean **does not affect** `CompletableFuture.runAsync(task)` calls that do not pass the executor, or pools created independently by other libraries. Context propagation also requires appropriate accessors/tracing integration; test current span, log correlation, and parent-child relationships on the worker thread.

### Caution regarding when the original scope closes

If an async task runs longer than the request thread, closing the original scope does not immediately deprive a task that already captured context of that context when the decorator works properly. The decorator captures the values to propagate at submission time, restores them while the task runs, and then restores the prior context when the task finishes. However, **you must not use an already-ended Span object** as a parent for late-starting work without an explicit design. For long-running background workflows, you can start a new trace and link the earlier span using appropriate links/correlation.

## 9. Scope and HTTP/message propagation are two different boundaries

Opening a scope solves **current context within a local execution context**. Calling another service requires **injecting/extracting trace context into transport** (for example, W3C Trace Context in the `traceparent` header). The two operations work together but do not replace each other.

```text
Thread A (orders-service)                Thread B (payment-service)
------------------------                 --------------------------
server span A
  |
  +-- open scope for span B
        |
        +-- HTTP client instrumentation
              |
              +-- inject traceparent --------> extract traceparent
                                                  |
                                                  v
                                           server span C (child)
        |
  close scope
  end span B
```

If you use an uninstrumented HTTP client, opening a scope will not automatically write `traceparent` to headers. If a message consumer processes work on a worker thread, it must extract context from message headers and open a scope before processing. The W3C propagator must be compatible on both sides; proxies should not strip tracing headers outside trust-boundary policies.

A long message workflow can create a new trace with a span link to the producer context instead of stretching a single parent-child tree across a very long time span. Choose semantics based on your business model and backend tooling.

## 10. Common mistakes when opening scopes

| Symptom | Common cause | How to fix/check |
| --- | --- | --- |
| Service logs lack Trace ID | No current span or missing MDC integration | Check tracing bridge, scope, and encoder |
| Child span lacks expected parent | Span created before opening parent scope | Open parent scope around child call or pass explicit context |
| Next request on same thread carries old trace ID | Scope not closed when exception occurred | Use try-with-resources; check all return/throw branches |
| `tracer.currentSpan()` returns null in executor | Context not propagated to new thread | Use executor/decorator or context-aware API |
| Ended span is still current | Called `span.end()` before closing scope | Close scope before ending span |
| Scope closed on a different thread | Violates thread-local lifecycle/context | Close in the same execution scope where it was opened |
| Trace splits when calling downstream | Local scope opened but HTTP client does not inject context | Instrument client and inspect trace headers |
| Backend has no spans even though current span ID was read | Sampling, exporter/collector, or retention | Check each layer; do not infer solely from logs |
| Metrics exist but traces are missing | Metric handler works, tracing sampled out or bridge error | Check sampling, tracing handler/exporter |

**Do not swallow exceptions to preserve a scope.** Try-with-resources closes the scope even when code throws; record the exception/status appropriately and rethrow according to the business contract. If using a manual `finally`, ensure the scope closes before ending the span and never overwrite the original exception with an unrelated cleanup error.

## 11. Safe coding checklist

Before opening a scope, clarify:

1. **Who owns the lifecycle?** The code creating the span/observation should be responsible for starting and stopping/ending it; do not end spans owned by another instrumentation/framework.
2. **Which section needs current context?** Wrap only the code that truly needs context; do not keep a scope open longer than the transaction/request.
3. **What is the parent context?** Ensure the parent scope is already current before creating child spans or calling downstream instrumentation.
4. **Where does it close?** Use try-with-resources; avoid returning/throwing while a scope remains unclosed.
5. **Is there a thread switch?** If so, use explicit context propagation; do not expect ThreadLocal to travel on its own.
6. **Are logs correlated?** Check MDC and patterns, and restore the previous context.
7. **Are signals exported?** Check ObservationRegistry handlers, tracing bridge, sampler, exporter, and backend.
8. **Is metadata safe and low-cardinality?** Do not attach Trace ID, order ID, or sensitive information to metric tags.

### Minimum test matrix

| Scenario | Expectation |
| --- | --- |
| Open observation scope on current thread | Current observation is set for the measured code block |
| Open child span inside parent scope | Trace ID stays the same, new Span ID, right parent |
| Nested scopes A then B | Closing B restores A; closing A restores initial context |
| Exception thrown in try block | Scope still closes, span/observation ends, exception propagates |
| Early return in try block | Scope closes automatically via try-with-resources |
| No prior span/observation | Current API may return null/no current; code handles properly |
| Callback runs on new thread without decorator | Do not assume current context is retained |
| Run with context-propagating executor | Context is captured/restored if accessors/integrations are configured |
| Instrumented downstream HTTP | Trace context is injected/extracted and parent-child is valid |
| Sampling drops trace | Context may still exist; trace is not guaranteed in backend |
| Logging correlation active | Trace/span fields match active scope and restore after scope closes |

## 12. Case study exercise

A controller opens observation `order.confirm`, then executes:

```java
Observation observation =
        Observation.createNotStarted("order.confirm", registry);
observation.start();
try (Observation.Scope scope = observation.openScope()) {
    log.info("Confirming order");
    CompletableFuture.runAsync(() -> {
        log.info("Persisting order");
        repository.save(order);
    });
} finally {
    observation.stop();
}
```

In a real environment, the `Confirming order` log has a Trace ID, while `Persisting order` does not. Some database spans appear under a new trace.

**Question:** is the bug in the exporter or in the scope? Why?

**Reference analysis:**

- The first log is written inside the controller thread's scope, so it can receive the current trace context.
- `CompletableFuture.runAsync(...)` does not use a specified executor with context propagation; the callback may run on a different thread. The controller's scope is not automatically transferred to that thread.
- The controller scope closes right after submitting the callback without waiting for the callback to finish. This is right for the request lifecycle, but the callback needs context captured at submission time if it is meant to continue the trace.
- If the callback creates a database observation/span without a parent context, the tracer can start a new trace. A log missing a Trace ID is consistent with lost current context, which is not enough to conclude the exporter is misconfigured.

**Fix:** submit the callback through an executor with `ContextPropagatingTaskDecorator` and configured context accessors/tracing integration. Or design the background job as its own trace, recording business correlation/links to the request trace if the workflow calls for it. Then verify Trace ID/Span ID, parent-child relationships, and log correlation in the worker before checking the exporter/collector if spans still do not appear.

**Conclusion:** Opening a scope on the current thread is an operation that **temporarily activates context**, while closing the scope **restores the previous context**. It does not automatically end spans, inject HTTP headers, or propagate context to other threads. With Spring Boot/Micrometer/OpenTelemetry, manage scopes with try-with-resources, keep span lifecycles distinct, use explicit propagation for executors/messages/HTTP, and verify metrics–logs–traces correlation so troubleshooting errors and latency in production never loses context.
