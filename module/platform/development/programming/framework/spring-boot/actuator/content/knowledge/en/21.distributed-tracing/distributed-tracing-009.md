# Creating Custom Spans and Recording Errors by Operation Scope

## 1. Spans Should Reflect a Meaningful Operation

An order placement request can take a long time because of stock checks, shipping fee calculation, or payment gateway calls. The HTTP span shows total handling duration; business spans help identify which step is slow and which step failed.

A **custom span** is a tracing unit proactively created by the application for an operation worth observing. Its boundary should match what an operator wants to ask: "how long did stock reservation take?", "did this inventory call fail?". You do not need to create spans for every getter, setter, or individual line of code.

Terms to distinguish:

| Term | Role in This Lesson |
| --- | --- |
| Trace | A collection of related spans describing the path of a single execution |
| Span | A named operation with start/end times and tracing data |
| Parent/child span | Relationship between an outer operation and a component operation |
| Active scope (`scope`) | The interval during which a span is set as the current span of the execution context |
| Tag (attribute) | Key-value pair describing the operation |
| Event | A point-in-time milestone occurring during the span's lifetime |
| Error recording | Attaching failure information to the right observed operation |

Example operation tree designed by the application:

```text
HTTP handling order placement
└── checkout
    ├── inventory.reserve
    └── shipping.quote
```

An error in `inventory.reserve` is not enough to conclude `checkout` failed. If the business contract allows accepting an order in a pending-stock state, the parent operation can complete validly. Therefore, before writing code, determine **what each span describes and what outcome counts as a failure of that specific unit of work**.

## 2. Choosing Observation or Tracer

In Spring Boot 3.3.x, there are two common approaches:

| Need | Appropriate API |
| --- | --- |
| Observe an operation so handlers produce metrics and spans per configuration | `Observation` and `ObservationRegistry` |
| Create and control a span directly without automatically creating extra metrics for that operation | `io.micrometer.tracing.Tracer` |
| Enrich an existing span | Access the current span, check for the possibility of no span, and respect ownership |

Spring Boot integrates Micrometer Observation with Micrometer Tracing when appropriate configuration and tracing libraries are present. Merely creating an empty `ObservationRegistry` or merely adding Actuator does not guarantee spans are sent to a collection system. See [Spring Boot 3.3: creating custom spans and Observation integration](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.creating-spans).

The service examples below are **code integrated into a Spring Boot application with tracing configured**, not programs run standalone with `javac InventoryService.java`. One library option for the application is:

- `org.springframework.boot:spring-boot-starter-actuator`.
- `io.micrometer:micrometer-tracing-bridge-otel`.
- `io.opentelemetry:opentelemetry-exporter-zipkin` if sending to Zipkin.

Use Spring Boot's version management for these dependencies and choose a bridge/exporter compatible with the existing system. The standalone practice in section 7 uses Observation and a console-printing handler, allowing lifecycle inspection without needing a trace collection system yet.

## 3. Creating Spans Directly and Managing Their Lifecycle Properly

### 3.1. Creating, Starting, Opening Scope, and Ending Are Distinct Operations

With the `Tracer` API, the usage pattern consists of:

1. Create a span for the operation and give it a stable name.
2. Start the span.
3. Put the span in scope while executing the code to observe.
4. Record tags, events, or errors onto the right span object.
5. Close the scope to restore the previous context.
6. End the span with `end()` in `finally`.

`nextSpan()` creates a child span if a current span exists; if there is no parent, it creates a span belonging to a new trace. `withSpan(...)` returns a `Tracer.SpanInScope`, so use it with `try-with-resources`. **Closing the scope does not substitute for ending the span.** These are two separate responsibilities in [Micrometer Tracing: using Tracer directly](https://docs.micrometer.io/tracing/reference/api.html).

### 3.2. Inventory Reservation Service Example

File `InventoryService.java`:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final Tracer tracer;

    public InventoryService(Tracer tracer) {
        this.tracer = tracer;
    }

    public String reserve(boolean fail) {
        Span span = tracer.nextSpan()
                .name("inventory.reserve")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            span.tag("inventory.source", "primary");
            span.event("inventory.reserve.started");

            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }

            span.tag("inventory.result", "reserved");
            span.event("inventory.reserve.completed");
            return "RESERVED";
        } catch (RuntimeException | Error error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
```

`fail` is a simulated input to deliberately exercise both branches of the example. In a real application, replace the simulation with real reservation work; do not add artificial delays to business code to "make traces clearer."

Points to read from the code:

- `inventory.reserve` is the name of the **operation type**, not containing an order ID.
- `tag` describes outcomes; `event` marks a point in time. Neither replaces `error(Throwable)`.
- If the operation fails, the code records the error and **rethrows the same error object**, preserving behavior for the caller.
- `finally` runs both on `return` and on exceptions, so both success and failure branches end the span.
- Catching `Error` here is solely to record and rethrow immediately; this is not a recovery mechanism from fatal JVM errors.

The example only has unchecked exceptions. If real operations declare checked exceptions such as `IOException`, record and rethrow that exception per the method signature; do not drop it or turn it into a success result just to simplify tracing.

Per the [Micrometer Span contract](https://raw.githubusercontent.com/micrometer-metrics/tracing/v1.3.6/micrometer-tracing/src/main/java/io/micrometer/tracing/Span.java), `error(Throwable)` records the exception and `end()` finishes the span. Data delivery also depends on sampling, bridge, exporter, and collection pipeline; `end()` is not confirmation that the server stored the span.

### 3.3. Pitfall: Recording Errors onto the Parent Span After Scope Closes

With the `try-with-resources` structure above, the scope is closed **before entering the catch block**. At that point, the current span may have already reverted to the parent span.

The following is an anti-pattern; do not use it to record errors for a child span:

```java
// Wrong target: currentSpan may be the parent span or null.
catch (RuntimeException error) {
    tracer.currentSpan().error(error);
    throw error;
}
```

Holding the created `span` reference and calling `span.error(error)` ensures the failed operation is clearly identified regardless of which span happens to be current inside the catch block.

Similarly, do not call `end()` on a span obtained from `tracer.currentSpan()` if that span was created by HTTP instrumentation or another component. The component that creates a span is responsible for ending it; a component borrowing the context must not close someone else's lifecycle.

## 4. Recording Errors According to Each Operation's Contract

### 4.1. Distinguishing Child Errors from Parent Outcomes

Suppose `checkout` is defined as "accept the order, allowing pending stock reservation when primary inventory is temporarily unavailable." Then:

| Situation | `inventory.reserve` | `checkout` |
| --- | --- | --- |
| Reservation succeeds | No error recorded | Completes with reserved order |
| Inventory fails, parent accepts valid pending state | Records the reservation's error | Records pending outcome and fallback event |
| Inventory fails, parent requires immediate reservation | Records the reservation's error | Also fails per the parent operation's contract |
| Insufficient stock is a normal business result of a check | Records appropriate business status | Decides per contract, rather than defaulting to a technical error |

This is how observation boundaries are designed for the example. Classification must be based on real operation semantics, not solely on exception class names or returned HTTP status codes. [OpenTelemetry error recording guidelines](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/) also distinguish an operation's failure from an error handled so that the operation completes validly.

### 4.2. Example Where the Parent Accepts a Fallback Path

File `CheckoutService.java`, used alongside `InventoryService` from section 3:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final Tracer tracer;
    private final InventoryService inventoryService;

    public CheckoutService(
            Tracer tracer, InventoryService inventoryService) {
        this.tracer = tracer;
        this.inventoryService = inventoryService;
    }

    public String checkout(boolean failInventory) {
        Span span = tracer.nextSpan().name("checkout").start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            try {
                String result = inventoryService.reserve(failInventory);
                span.tag("checkout.result", "reserved");
                return result;
            } catch (IllegalStateException error) {
                span.tag("checkout.result", "deferred");
                span.event("inventory.fallback.accepted");
                return "ACCEPTED_PENDING_STOCK";
            }
        } catch (RuntimeException | Error error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
```

In the example, `IllegalStateException` only represents the simulated inventory failure. Real applications should catch the specific exception type of the recoverable operation; do not use an overly broad catch block that hides programming bugs as well.

When calling `checkout(true)`:

1. `checkout` enters scope.
2. `inventory.reserve` becomes a child span.
3. The error is recorded on the child span and rethrown; the child span ends.
4. The child's scope closes, restoring the parent context.
5. The parent accepts the pending state, adds tag/event, and finishes.

The parent does not call `error(error)` for an error validly handled within its own scope. Conversely, if stock reservation is mandatory, let the error propagate out of the parent operation; then the parent's outer catch block records `checkout`'s failure.

**Do not infer that every span in a trace must share the same error status.** Nor do you need to duplicate full stack traces at every layer. If multiple layers genuinely fail, express the failure accurately at each boundary and avoid redundant duplicate exception records.

### 4.3. Error Logs, Error Tags, and Error Status Are Not Identical

`logger.error(...)` creates a log record. `span.tag("result", "failed")` adds an attribute. Neither automatically guarantees the span is marked as errored.

With the OpenTelemetry bridge in Micrometer Tracing 1.3.6, `Span.error(Throwable)` both records the exception and sets the span status to `ERROR`; see [OtelSpan implementation source](https://raw.githubusercontent.com/micrometer-metrics/tracing/v1.3.6/micrometer-tracing-bridges/micrometer-tracing-bridge-otel/src/main/java/io/micrometer/tracing/otel/bridge/OtelSpan.java). Exact error detail rendering can differ across bridges and trace collector UIs.

Similarly, recording an error on a span does not automatically turn an HTTP response into 500, roll back a transaction, or perform a retry. Those behaviors remain governed by application code and the corresponding frameworks.

## 5. Using Observation to Manage Operations

For operations that need observing via both metrics and traces, you can write an alternative class to `InventoryService` as follows. This is an **alternative to manually creating a span for the same operation**; do not layer both approaches on top of each other just to measure one unit of work.

File `ObservedInventoryService.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedInventoryService {
    private final ObservationRegistry registry;

    public ObservedInventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String reserve(boolean fail) {
        Observation observation = Observation
                .createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("inventory.source", "primary");

        return observation.observe(() -> {
            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }
            observation.lowCardinalityKeyValue(
                    "inventory.result", "reserved");
            return "RESERVED";
        });
    }
}
```

`observe(...)` wraps starting the observation, opening the scope, executing the lambda, recording any error escaping the lambda, closing the scope, and stopping the observation. When using this pattern, do not manually call `start()` beforehand or `stop()` again afterward. The behavior of recording errors, rethrowing, and stopping in `finally` can be checked in [Observation 1.13.6](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.6/micrometer-observation/src/main/java/io/micrometer/observation/Observation.java).

An important point about catch block placement:

- If an exception **escapes the lambda** of `inventory.reserve`, this operation's observation receives the error.
- If the lambda catches the exception itself and returns a valid fallback, `observe` sees a normal completion.
- If code returns a failure result object without throwing an exception, `observe` does not automatically understand the business meaning of that object. Classify the outcome and explicitly attach appropriate observation metadata.
- If observing an operation that genuinely failed yet must translate the exception into a return value, you can call `observation.error(error)` before returning. Do this only when the failure matches that specific observation's contract.

If using the manual `Observation.start(...)` and `openScope()` APIs, you must manage `error(...)`, scope closing, and `stop()` yourself. Do not treat closing `Observation.Scope` as meaning the observation has stopped.

## 6. Choosing Sensible Names, Attributes, and Boundaries

Span names should stay stable by operation type, e.g., `inventory.reserve`, `shipping.quote`, `checkout`. Do not embed order IDs into names like `checkout-ORDER-938172`, as that produces too many distinct names to aggregate.

With Observation, **low cardinality** means a reasonably bounded value set; e.g., `inventory.source=primary|backup` or `checkout.result=reserved|deferred`. Request IDs with many distinct values are unsuitable as metric tags. This distinction is explained in [Micrometer Observation 1.13: attributes and cardinality](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

One way to choose data for the problem:

| Data | How to Use |
| --- | --- |
| Primary/backup inventory source | Tag for filtering over a small value set |
| Reserved/deferred outcome | Tag expressing the business outcome |
| Reservation started | Event if this timestamp milestone aids diagnostics |
| Exception causing operation failure | `error(Throwable)` or Observation error |
| Passwords, tokens, card numbers, full payloads | Never put into exported tags, events, or exception messages |

High cardinality does not mean permission to record sensitive data. Exception messages and stack traces can also contain input data; control information both at error creation sites and along the collection pipeline per system requirements.

A retry that fails and then succeeds must be described according to chosen boundaries: spans for each attempt can record that attempt's error, while a span wrapping the entire retry sequence reflects the final outcome. Do not mark the overall operation as failed just because an inner attempt errored yet recovered per contract.

## 7. Standalone Java Practice: Seeing Child Errors and Scope Clearly

The following program runs on Java 17+ and Micrometer Observation 1.13.0. It registers an `ObservationHandler` that only prints lifecycle events to stdout. **This program does not install a tracing handler, produces no data sent to Zipkin, and does not prove the span export path works.** The goal is verifying error recording placement, stop ordering, and scope restoration.

Save as `ObservationScopeDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationScopeDemo {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(new ConsoleHandler());

        System.out.println("RESULT " + checkout(registry, false));
        System.out.println("AFTER_SCOPE_EMPTY "
                + (registry.getCurrentObservation() == null));
        System.out.println("RESULT " + checkout(registry, true));
        System.out.println("AFTER_SCOPE_EMPTY "
                + (registry.getCurrentObservation() == null));
    }

    private static String checkout(
            ObservationRegistry registry, boolean failInventory) {
        Observation observation =
                Observation.createNotStarted("checkout", registry);
        return observation.observe(() -> {
            try {
                return reserve(registry, failInventory);
            } catch (IllegalStateException error) {
                observation.lowCardinalityKeyValue("result", "deferred");
                observation.event(
                        Observation.Event.of("inventory.fallback.accepted"));
                return "ACCEPTED_PENDING_STOCK";
            }
        });
    }

    private static String reserve(
            ObservationRegistry registry, boolean fail) {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry);
        return observation.observe(() -> {
            System.out.println("IN_SCOPE inventory.reserve="
                    + (registry.getCurrentObservation() == observation));
            if (fail) {
                throw new IllegalStateException("primary unavailable");
            }
            return "RESERVED";
        });
    }

    private static final class ConsoleHandler
            implements ObservationHandler<Observation.Context> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            System.out.println("START " + context.getName());
        }

        @Override
        public void onError(Observation.Context context) {
            System.out.println("ERROR " + context.getName() + " "
                    + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onStop(Observation.Context context) {
            Throwable error = context.getError();
            System.out.println("STOP " + context.getName() + " error="
                    + (error == null ? "none"
                            : error.getClass().getSimpleName()));
        }
    }
}
```

Place the two JARs `micrometer-observation-1.13.0.jar` and `micrometer-commons-1.13.0.jar` in the same folder as the Java file, or adjust the classpath to where they were downloaded. In PowerShell:

```powershell
$cp = ".;micrometer-observation-1.13.0.jar;micrometer-commons-1.13.0.jar"
javac --release 17 -encoding UTF-8 -cp $cp ObservationScopeDemo.java
java -cp $cp ObservationScopeDemo
```

On Linux/macOS, the classpath entry separator is `:` instead of `;`.

Program stdout:

```text
START checkout
START inventory.reserve
IN_SCOPE inventory.reserve=true
STOP inventory.reserve error=none
STOP checkout error=none
RESULT RESERVED
AFTER_SCOPE_EMPTY true
START checkout
START inventory.reserve
IN_SCOPE inventory.reserve=true
ERROR inventory.reserve IllegalStateException
STOP inventory.reserve error=IllegalStateException
STOP checkout error=none
RESULT ACCEPTED_PENDING_STOCK
AFTER_SCOPE_EMPTY true
```

On the second run, the error escapes `reserve`'s lambda, so the handler sees `ERROR inventory.reserve`. It is caught inside `checkout`'s lambda, so the handler stops `checkout` with `error=none`. Both runs show `AFTER_SCOPE_EMPTY true`, proving no current observation remains after the outer operation in this program.

The console-printing handler does not implement an event-printing method, so `inventory.fallback.accepted` does not appear in stdout. That does not mean the event call in code was lost; this handler simply prints `onStart`, `onError`, and `onStop`.

## 8. Verifying in a Spring Boot Application with Tracing

After applying **one** of the two span-creation approaches to an application with tracing configured:

1. Run both the success case and the recoverable inventory failure case.
2. In the collected traces, locate operations by name, and inspect parent/child relationships, durations, and tags/events.
3. Confirm the stock-reservation span records an error in the failure case; the order-acceptance span does not have to be marked errored if the contract permits a pending state.
4. Remove the fallback path and let the error propagate to the parent operation; confirm the observed outcome changes accordingly.
5. Test a subsequent request to detect context leakage from the previous execution.

When spans are missing, check along the pipeline: is tracing configured, did the operation run, did the span end, did the sampling policy retain the trace, did the exporter send it, and are UI filters hiding data? Having a trace ID in logs does not prove spans reached the storage backend.

The scope examples in this lesson are **synchronous** code. A `try-with-resources` wrapping `CompletableFuture` or `Mono` creation can finish before the actual work completes. When switching threads or using reactive processing, tie the lifecycle to actual work completion and propagate context via the appropriate mechanism; do not hold a caller-thread scope and reuse it arbitrarily on another thread.

## 9. Common Mistakes and Self-Check Exercises

| Common Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting `end()` or `stop()` | Operation never finishes its lifecycle properly | Use `finally` or `observe(...)` |
| Closing only the scope | Restores context without completing the operation | Distinguish scope from span/observation |
| Calling `currentSpan().error(...)` after child scope closes | May attach error to parent or hit null | Keep a reference to the span that needs error recording |
| Adding only tag `error=true` | Custom metadata exists without guaranteed error status | Use the proper error-recording API for the observation type |
| Swallowing all exceptions and returning success | Corrupts both application behavior and observability data | Preserve error contracts and recover only when valid |
| Manually ending the active HTTP span | Interferes with a framework-owned lifecycle | Only end spans you created yourself |
| Creating two instrumentation layers for one operation without reason | Duplicate spans and redundant metrics | Pick Observation or Tracer based on need |

Exercises:

1. In `ObservationScopeDemo`, remove `checkout`'s fallback catch block and catch the exception in `main` so the program continues. Predict which observations receive errors before running.
2. Change the scenario so "out of stock" is a valid outcome returning `OUT_OF_STOCK` instead of throwing a technical error. Pick an outcome tag and explain why an error is or is not recorded.
3. For a service creating spans manually, mark where scope closes and where `end()` runs for both the `return` path and the exception-throwing path.
4. Design a span wrapping an entire retry process alongside child spans per attempt; explain the case where the first attempt fails yet a later attempt succeeds.

A solid solution clearly identifies the observed operation, lifecycle owner, where context is restored, and the meaning of failure at each boundary.
