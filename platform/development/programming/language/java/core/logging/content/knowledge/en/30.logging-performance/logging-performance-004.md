# Lazy Messages in Java Logging Performance

## 1. Goal: Only Build Messages When Truly Needed

**Lazy message** (on-demand log message construction) is the practice of deferring the construction of a log string or the computation of an expensive argument until the logging system decides whether that content is actually needed. This is an important performance optimization technique when log statements sit on a *hot path*: large loops, high-throughput request handling, batch pipelines, or code with many DEBUG/FINE logs disabled in production.

For example, suppose an application is configured at level INFO. The following two JUL snippets behave differently:

```java
// Eager: expensiveDetail() is evaluated before the logger checks the FINE level.
log.fine("detail=" + expensiveDetail());

// Lazy: the lambda body only runs when the logger permits FINE.
log.fine(() -> "detail=" + expensiveDetail());
```

Here, `log` is a `java.util.logging.Logger` and `expensiveDetail()` is a hypothetical method. Section 5 provides a standalone Java 17+ program to demonstrate the difference.

Three points must be clearly understood:
- **Lazy** can avoid building the message/argument when logging is disabled by a level check, but it does not guarantee **zero cost**. Java still invokes the logging API, may allocate a lambda/capture variables, and performs level/filter checks.
- **Parameterized logging** (`"userId={}"`) can defer string formatting, but Java still evaluates the argument expressions before the method call.
- **Asynchronous logging** offloads events to a worker/sink at a later time. It does not mean messages and arguments are lazily evaluated by default.

After this lesson, you will be able to choose the right approach for JUL, `System.Logger`, traditional SLF4J, the SLF4J 2.x fluent API, and Log4j 2; write tests that count how many times a message is evaluated; and evaluate the interplay among lazy evaluation, filters, async logging, and throughput.

## 2. The Core Lies in Java's Expression Evaluation Rules

Java evaluates arguments before invoking a method. Therefore, the following calls are **not lazy** with respect to computations placed inside the arguments:

```java
// Integration snippet, not a standalone program.
logger.debug("state=" + expensiveState());
logger.debug(String.format("state=%s", expensiveState()));
logger.debug("state={}", expensiveState());
```

Even when the logger has DEBUG disabled, Java still must:
1. Call `expensiveState()` to obtain the expression's value.
2. Perform string concatenation or `String.format` if they are inside the argument.
3. Only then pass the argument to `logger.debug(...)`.

On the third line, `{}` is used by SLF4J/Log4j 2 for **formatting**; it does not change how Java evaluates `expensiveState()`. Thus, a statement with placeholders can still trigger unnecessary DB queries, JSON serialization, or collection traversals.

In contrast, the lambda `() -> "state=" + expensiveState()` is a functional value. Java may allocate/capture the lambda object at the call site, but it **does not execute the lambda body** until the receiver calls `Supplier.get()`. A logging system with a `Supplier` overload decides when to make that call.

Compare:

```java
// Computed upfront; the Supplier only returns the already-computed value:
String detail = expensiveState();
log.fine(() -> "state=" + detail);

// Computed inside the Supplier when the system needs it:
log.fine(() -> "state=" + expensiveState());
```

An operation required for business logic **must not** be placed inside a logging `Supplier`. If the level is disabled, the `Supplier` may never run.

## 3. Strategies to Reduce Message Cost

| Usage | When DEBUG/FINE is disabled | When level is enabled | Best suited for |
| --- | --- | --- | --- |
| String concatenation: `log.debug("x=" + heavy())` | `heavy()` still runs | Builds string before calling logger | Avoid when `heavy()` is expensive |
| Placeholder with existing variable: `log.debug("x={}", x)` | Evaluates variable `x`, usually skips formatting | Formats according to backend/layout | Cheap, already-available arguments |
| Placeholder with method call: `log.debug("x={}", heavy())` | `heavy()` still runs | Computes value and formats | Not properly optimized |
| Guard: `if (log.isDebugEnabled()) ...` | Skips entire computation block | Computes when guard is true | Legacy SLF4J, multi-step computations |
| JUL: `log.fine(() -> heavy())` | Supplier body does not run if FINE is disabled | Calls Supplier when level permits | JUL on Java 8+ |
| SLF4J 2: `atDebug().addArgument(() -> heavy())` | Supplier is skipped when DEBUG is disabled | Supplies argument when logging | SLF4J 2.0+ |
| Log4j 2: Supplier overloads | Can skip computation when early filtering rejects | Computes when event is accepted | Log4j 2 API |

The table describes optimization intent. Events can still be dropped by appender filters or lost in an async pipeline; a successful `Supplier` invocation **does not mean** the message was durably persisted.

### When is a guard worthwhile?

If you are only logging `LOG.debug("count={}", count)` with an existing `int` variable, adding a guard can make the code verbose for little gain. However, if you need to aggregate a large structure, perform multiple calculations, or build a diagnostic report, a guard avoids the entire block:

```java
if (LOG.isDebugEnabled()) {
    String summary = buildOrderSummary(order);
    Map<String, Long> counters = calculateCounters(order);
    LOG.debug("summary={} counters={}", summary, counters);
}
```

This is an SLF4J integration snippet (the methods, `order`, and `Map` must be defined). The level check is not an atomic transaction with event emission: the backend configuration may change immediately after the guard. Because logging serves diagnostics, do not rely on a guard to control mandatory business side effects.

## 4. Lazy by Level Does Not Mean Lazy All the Way to the Sink

General processing flow:

```text
Application thread
      |
      +--> Java evaluates regular arguments (eager)
      |
      +--> Logger checks level / early filters
                    |
                rejected ---> drop event
                    |
                accepted
                    |
                    v
          Supplier is evaluated if the API needs it
                    |
                    v
          LogEvent / LogRecord
                    |
          appender / handler filters
                    |
          format, queue, file, collector
```

The exact order depends on the backend and sync/async mode. Specifically:
- **JUL:** `Logger` checks the log level first, then creates a `LogRecord`/applies filters and dispatches to `Handler`. `Supplier<String>` is evaluated when the logger allows the corresponding level; `Handler` also has its own level/filter.
- **Logback:** has logger level checks, early `TurboFilter`s, and regular filters on appenders. If filtered at the end of the pipeline, the event may already have been created.
- **Log4j 2:** has multiple filter layers (global, logger, appender reference, appender), so you must read the contract of each layer carefully.

For example: a JUL logger is set to `FINE` while `ConsoleHandler` only accepts `WARNING`. When running `logger.fine(() -> expensiveState())`, the logger permits `FINE` so the `Supplier` may run; the handler then discards the event. When optimizing computation cost, prefer preventing unnecessary event creation at the logger or early filter rather than only raising the threshold at the destination.

Similarly, a logger may send `INFO` to a file and only `WARN` to a collector. Because the `INFO` event is still needed for the file, you cannot conclude it should be discarded completely just because the collector is set to `WARN`.

## 5. Standalone Java 17+ Program to Verify Lazy Messages

This is a JDK-only example requiring no JUnit, Logback, or SLF4J. The program creates an isolated JUL logger, attaches a handler that prints to stdout, and uses an `AtomicInteger` to count how many times the expensive payload is built.

Create **`LazyMessageDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LazyMessageDemo {
    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord event) {
                if (isLoggable(event)) {
                    System.out.println(event.getLevel().getName()
                            + " " + event.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        sink.setLevel(Level.ALL);
        log.addHandler(sink);
        AtomicInteger builds = new AtomicInteger();
        Supplier<String> detail =
                () -> "payload-" + builds.incrementAndGet();

        try {
            // FINE is disabled; the lambda body does not run.
            log.fine(() -> "debug " + detail.get());
            System.out.println("after-disabled=" + builds.get());

            // INFO is enabled; the Supplier is invoked.
            log.info(() -> "visible " + detail.get());
            System.out.println("after-enabled=" + builds.get());

            // The eager expression is still evaluated even though FINE is disabled.
            log.fine("eager " + detail.get());
            System.out.println("after-eager=" + builds.get());
        } finally {
            log.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac LazyMessageDemo.java
java LazyMessageDemo
```

**Exact stdout output of this example:**

```text
after-disabled=0
INFO visible payload-1
after-enabled=1
after-eager=2
```

Explanation:
1. The logger is at `Level.INFO`, so the `fine(Supplier<String>)` call is rejected before the lambda body runs: the counter stays at 0.
2. `info(Supplier<String>)` is permitted by the logger, so the lambda calls `detail.get()`; the handler prints `INFO visible payload-1` and the counter increments to 1.
3. `fine("eager " + detail.get())` must evaluate `detail.get()` before calling JUL, even though `FINE` is disabled; the counter becomes 2, yet no `FINE` line is printed.
4. `getAnonymousLogger()` combined with `setUseParentHandlers(false)` isolates the example and prevents the root handler from printing extra output to stderr.
5. `finally` removes the handler. For handlers backed by files or networks, close and flush according to their actual contract.

This example demonstrates **message evaluation counts**, not nanosecond benchmarks. Change `log.setLevel(Level.INFO)` to `Level.FINE` to observe behavior when both levels are enabled, then explain why the `FINE` line is printed and how the counter changes.

## 6. Using Supplier with JUL and System.Logger

### JUL `java.util.logging.Logger`

Since Java 8, JUL provides `fine(Supplier<String>)`, `info(Supplier<String>)`, `log(Level, Supplier<String>)`, and corresponding overloads. Use them as follows:

```java
// Integration snippet: these methods are defined in the application.
logger.fine(() -> "cache=" + dumpCacheSummary());
logger.log(java.util.logging.Level.FINER,
           () -> "state=" + expensiveState());
```

If `FINER`/`FINE` is disabled on the logger, JUL will not construct the message by calling those `Supplier`s. `dumpCacheSummary()` and `expensiveState()` are hypothetical, so this snippet does not run standalone.

When an exception occurs, pass the `Throwable` in its dedicated parameter instead of only concatenating `ex.getMessage()`:

```java
try {
    processOrder();
} catch (Exception ex) {
    logger.log(
        java.util.logging.Level.SEVERE,
        ex,
        () -> "order_failed orderId=" + orderId);
    throw ex;
}
```

This is also an integration snippet: `processOrder()`, `orderId`, and `logger` must exist. JUL has the overload `log(Level, Throwable, Supplier<String>)`; the exception is stored in `LogRecord.thrown` so the formatter can record the stack trace, while the message is built lazily according to the level. If you only log `ex.getMessage()`, you easily lose stack trace context.

### `System.Logger`

Since Java 9, `java.lang.System.Logger` also supports `Supplier`:

```java
System.Logger appLog = System.getLogger("demo.order");
appLog.log(System.Logger.Level.DEBUG,
           () -> "state=" + expensiveState());
```

This is an integration snippet requiring `expensiveState()`. `System.Logger.Level.DEBUG` and `java.util.logging.Level.FINE` are two different enums/classes; do not use them interchangeably. The underlying backend of `System.Logger` is determined via `LoggerFinder`/runtime configuration, not by the lambda syntax.

**General note:** do not place network calls, DB writes, or state-mutating operations inside a `Supplier`. The logger is free to skip the content when the level is disabled; any mandatory operation must execute in the business flow before logging.

## 7. Traditional SLF4J: Placeholders Differ from Suppliers

SLF4J is a facade/API; Logback, the Log4j 2 provider, or another backend handles output. Common syntax:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Inside an OrderService class with a logger and corresponding variables.
private static final Logger LOG =
        LoggerFactory.getLogger(OrderService.class);

// Good for cheap, already-available arguments:
LOG.debug("orderId={} status={}", orderId, status);
```

This is an integration snippet requiring the SLF4J API/provider and `orderId`/`status` variables. With placeholders, SLF4J typically skips message formatting if the level is disabled. However:

```java
// NOT lazy for expensiveQuery():
LOG.debug("orderId={} details={}",
          orderId, expensiveQuery());
```

Because Java evaluates arguments before the call, `expensiveQuery()` still runs even when `DEBUG` is disabled. In traditional SLF4J (especially SLF4J 1.7), a guard solves this:

```java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderId={} details={}",
              orderId, expensiveQuery());
}
```

Do not overuse guards when logging constants or cheap arguments: `LOG.debug("attempt={}", attempt)` is usually clear enough.

### Be Careful with `toString()` as Well

```java
LOG.debug("state={}", stateObject);            // Passes the reference.
LOG.debug("state={}", stateObject.toString()); // Invokes immediately.
```

The first line allows the backend to defer `toString()`/formatting when logging is disabled. The second forces `toString()` to run before the backend receives the event. Even so, `stateObject` itself must still be created or retrieved before the call, and the backend may snapshot or format it early once the event is accepted. Do not rely on a single invariant `toString()` invocation timing across all backends or async modes.

`toString()` should be simple, make no DB calls, send no HTTP requests, and have no side effects. It can also be called by an IDE/debugger, formatter, or other libraries, so it is unsuitable for business logic.

## 8. SLF4J 2.x Fluent API: Deferring Expensive Arguments

Starting in SLF4J 2.0, `atTrace()`, `atDebug()`, `atInfo()`, `atWarn()`, and `atError()` return a `LoggingEventBuilder`. When a level is disabled, the builder performs no work for the disabled event. The fluent API supports `Supplier<?>` in `addArgument`.

Integration example:

```java
LOG.atDebug()
   .setMessage("orderId={} details={}")
   .addArgument(orderId)
   .addArgument(() -> expensiveQuery())
   .log();
```

Explanation:
- `orderId` is a cheap, already-available value passed as a regular argument.
- `expensiveQuery()` is inside the **lambda body**, so it does not run if `DEBUG` is disabled according to the fluent API.
- `.log()` is **mandatory to emit the event**. Forgetting it means nothing is logged even when the level is enabled.
- If you already computed `String details = expensiveQuery();` beforehand, passing `() -> details` cannot recover the already-spent cost.

SLF4J 2.x also provides key-value pairs for structured logging:

```java
LOG.atInfo()
   .addKeyValue("orderId", orderId)
   .addKeyValue("status", status)
   .log("order_state_changed");
```

The API stores keys/values for the backend/layout to use; text/JSON output depends on the provider. Note that `addKeyValue("details", expensiveQuery())` still evaluates `expensiveQuery()` per Java's rules. To defer the cost, use the `Supplier` overloads supported by your specific version or check the level with a guard before computing.

### Choosing an API by Version

| API | Recommended pattern for expensive arguments |
| --- | --- |
| SLF4J 1.7 | `isDebugEnabled()` + `debug("{}", value)` call |
| SLF4J 2.x traditional | Still use a guard if calling a method that builds an expensive argument |
| SLF4J 2.x fluent | `atDebug().addArgument(() -> expensive()).log("x={}")` |
| JUL | `fine(() -> expensive())` or `log(Level, Supplier)` |
| Log4j 2 API | Overloads accepting `Supplier`/lambda, see Section 9 |

Do not copy `atDebug()` into an SLF4J 1.7 project: the difference is in the compile-time API, not the Logback configuration file.

## 9. Log4j 2: Suppliers for Arguments and Messages

The Log4j 2 Performance documentation recommends passing a `Supplier` when an argument is expensive to compute. Integration example with the Log4j API:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

// Inside a class with orderId and expensiveQuery().
private static final Logger LOG =
        LogManager.getLogger(OrderService.class);

// Suppliers are only evaluated when the logging pipeline needs the data.
LOG.debug("orderId={} details={}",
          () -> orderId,
          () -> expensiveQuery());
```

`OrderService` and `expensiveQuery()` are hypothetical application code; this snippet requires the Log4j API/core or a compatible backend and will not run on plain JDK. Simple arguments like `orderId` generally do not need a lambda; the goal is to defer expensive queries or data construction.

Log4j 2 also has `Supplier` types for building messages, such as `ParameterizedMessage`, depending on the overload and version. Check the actual imported API; do not assume `debug("{}", () -> expensive())` behaves identically across JUL, traditional SLF4J, and the Log4j API.

**Filters and markers:** Log4j has multiple filter layers. When an event passes early checks but is rejected by an appender filter, the `Supplier` cost may already have been incurred. Lazy messages save work at the decision point; they do not mean a message is only computed if every downstream sink succeeds in writing it.

## 10. Snapshot Values and Mutable Data

One of the more subtle bugs when optimizing logging is logging a reference to a mutable object. For example:

```java
LOG.info("order={}", mutableOrder);
mutableOrder.setStatus("SHIPPED");
```

If the backend formats the reference later or the event uses a mutable message type, the log line may reflect a different state than at the moment of the call. Many backends snapshot messages on the calling thread, but not every message type or object is immutable. Log4j 2 specifically notes `MapMessage`, `StructuredDataMessage`, and custom messages under async logging.

A clearer approach:

```java
String orderIdSnapshot = order.getId();
String statusSnapshot = order.getStatus();
LOG.info("orderId={} status={}", orderIdSnapshot, statusSnapshot);
```

This is an SLF4J/Log4j integration snippet depending on domain objects. When accurate state logging is required, immutable snapshots matter more than trying to make every piece of data lazy.

With a `Supplier`:

```java
LOG.atDebug()
   .setMessage("state={}")
   .addArgument(() -> mutableOrder.getStatus())
   .log();
```

Be sure you know **when** `getStatus()` is invoked by your API/backend. Avoid assuming the value it reads is always the state at the moment the application decided to emit the event. If state can change concurrently or consistency matters, capture the value at the right time and only make formatting or non-semantic costs lazy.

In Java, local variables captured by a lambda must be `final` or *effectively final*, but **the referenced object** can still be mutable. This often causes confusion between "capturing a reference" and "capturing a value snapshot".

## 11. Lazy and Async Logging Are Two Different Decisions

**Lazy**: *when* are the message and arguments computed?  
**Async**: *when* does a worker process/write the event, and *which thread* sends it to the sink?

```text
Application thread
    |
    +-- check level / early filters
    |
    +-- build / capture required event content
    |
    +-- enqueue if backend is async
                      |
                      +--> worker -> appender -> format -> file/collector
```

This diagram is conceptual. Some backends snapshot the message/arguments on the calling thread to preserve data integrity; some layouts/encoders may format later. **Do not assume a `Supplier` will execute on a background worker** just because the appender is asynchronous. Check your API/backend/version if you rely on this detail.

Even with `Supplier`, an async queue can still:
- Fill up, causing producers to block or drop events depending on policy.
- Increase heap/GC pressure during large backlogs.
- Delay or lose logs if the worker/appender fails or on abrupt shutdown.
- Create a gap between enqueue rate and actual sink write rate.

Logging optimization requires a holistic view: log levels, filters, message construction, encoders, appenders, queues, file/network I/O, and collectors. Lazy evaluation primarily reduces **call-site** cost when a log is not needed.

### ThreadLocal, MDC, and Request Context

A `Supplier` reads `ThreadLocal`/MDC at execution time. In multithreaded or virtual-thread applications, distinguish which thread owns the context and whether it is propagated when spawning new tasks. Many backends capture MDC into the event at the call site; still, write tests to verify behavior with your actual provider and async mode.

Keep `requestId`/`traceId` small and immutable in the request context. Do not let a `Supplier` read large or mutable request objects and attach them directly to events. Avoid using the logger as a channel for passing business context.

## 12. Side Effects, Exceptions, and Sensitive Data

A `Supplier` used solely to build a log string should be **pure, fast, and free of business-state mutations**. Bad example:

```java
logger.fine(() -> "charged=" + chargePayment());
```

If `FINE` is disabled, `chargePayment()` does not run and business logic breaks. If `FINE` is enabled, the logger triggers a payment. Run `chargePayment()` in business logic, capture the result, and then log the needed value.

A `Supplier` can throw an exception when invoked. When the level is disabled, no error occurs; when enabled, a failure during message construction may enter the backend's error-handling path or affect the logger call. Do not put HTTP calls, DB queries, or untimeouted I/O inside a `Supplier` just for log formatting; if the data is genuinely needed for business operations, compute and handle errors in the appropriate layer before logging.

Lazy messages **are not a secret-protection mechanism**:
- Do not log passwords, tokens, API keys, session cookies, card numbers, private payloads, or raw sensitive objects.
- Redact/mask at the source or where data enters the event, with appropriate testing and retention policies.
- Use event codes and request identifiers instead of personal data.
- Limit serialization/collection dump sizes; a huge message still consumes memory when the level is enabled.
- For audits requiring durability and legal evidence, design a dedicated durable pipeline; ordinary lazy/async logging does not guarantee delivery.

Sometimes a message string containing sensitive data is constructed **before** the logger call and then dropped by a downstream filter. Therefore, avoid constructing sensitive content even if you think it is "just for DEBUG".

## 13. How to Test Lazy Messages

### 13.1. Verify Exact Evaluation Counts

A good test measures clear behavior rather than nanoseconds:
1. Use a counter incremented inside the message-building function.
2. Set the logger to a higher level than the test level, e.g., `INFO` to disable `FINE`.
3. Call the `Supplier` API and assert the counter is **0**.
4. Enable the target level, call again, and verify the counter increments when the event is accepted.
5. Call the eager version and verify the counter increments even when the level is disabled.
6. If you need to verify the event reaches the destination, use a test handler/appender and check filters/queues as well.

`LazyMessageDemo` in Section 5 implements a standalone version of this check. When moving to JUnit, use an isolated logger or restore configuration in `finally`; do not mutate the JVM-wide root logger across parallel tests.

### 13.2. With SLF4J 2.x and Logback

Use `ListAppender` (or an equivalent test appender):
- With `DEBUG` disabled: call `addArgument(() -> expensive())` and verify the counter does not increment.
- With `DEBUG` enabled: verify the level, message, and evaluation count.
- Call `.log()`; omitting `log()` means the builder never emitted an event.
- Clean up appenders, levels, MDC, and context after the test.
- With async appenders, wait for events to reach the sink using a signal/timeout rather than a fixed `Thread.sleep`.

### 13.3. Test Filters Across Multiple Layers

Do not test only the `DEBUG` level. Also test:
- Logger permits `INFO` but an appender filter drops `INFO`: does the `Supplier` run?
- Two appenders with different thresholds: does each destination receive the right subset of events?
- Large events on a hot path: do allocations and latency drop after switching to a `Supplier`?
- Runtime level changes while the system is running: tests should not assume a guard guarantees an event is unconditionally written.

Answers may depend on the backend and configuration; record versions so tests do not accidentally enforce one implementation's behavior on all others.

## 14. Measuring Performance Properly

**Do not conclude "lazy is X times faster" from a tiny few-line example.** The benefit depends on whether the log level is usually disabled or enabled, message preparation cost, filter hit rates, JIT compilation, layouts, and I/O.

Measure:
- Log call-site invocations per second and the ratio of enabled/dropped events.
- Message construction time and allocated objects/bytes.
- CPU, GC pauses, request throughput, and p95/p99 latency.
- For async: enqueue rate, queue depth, written/s, dropped/s, flush/shutdown behavior.
- Load below sink capacity, short bursts, and sustained overload.

With JMH, test each pattern with the level both disabled and enabled, warm up the JIT, and run multiple iterations. For integration benchmarks, keep the same backend/provider, sink, payload, level/filter, and number of events written downstream. Do not compare eager logging written to a file against lazy events that were dropped and conclude the backend is faster.

Rough back-of-the-envelope example: a diagnostic function taking **1 ms** called 1,000 times/second while `DEBUG` is disabled spends roughly **1,000 ms of call execution time per second**. Using a `Supplier` properly avoids those computations. This illustrates total call cost; it does not automatically save an entire CPU core, because the function might be waiting on I/O and calls may run concurrently.

### Optimization Priority Order

1. Cut unnecessary logs using levels, markers, and sampling.
2. Avoid string concatenation, serialization, and DB reads at the call site when events may be disabled.
3. Use placeholders for cheap arguments; use `Supplier` or guards for expensive arguments.
4. Control layouts, stack traces, and location lookup.
5. Tune queues/async, batching, and output targets when the sink is actually the bottleneck.
6. Re-measure latency, throughput, and log loss; stop once cost and observability are balanced.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `LOG.debug("x=" + expensive())` | Evaluates immediately even when DEBUG is disabled | Use `Supplier`/guard |
| `LOG.debug("x={}", expensive())` | Placeholder does not defer `expensive()` | Use fluent `Supplier`/guard |
| `String.format(...)` before logger | Eager formatting | Let the logging API format |
| `String x = heavy(); log.fine(() -> x)` | Computation already happened | Move `heavy()` into the lambda when valid |
| `atDebug().addArgument(...);` missing `log()` | No event is emitted | End the fluent builder with `log()` |
| `Supplier` with side effects | Disabling logs alters business logic | Separate business logic from logging |
| `Supplier` reads mutable object after state change | Event reflects wrong point in time | Snapshot when consistency matters |
| Filtering late at appender while expecting no message build | `Supplier` may already have run | Filter/set level early |
| Benchmarking only with DEBUG disabled | Ignores cost when level is enabled | Measure both enabled/disabled, sink, async |
| Assuming log was persisted just because supplier ran | Filters/async/I/O can still drop or fail | Verify at the appropriate sink |

## 16. Practice Exercises

1. Run `LazyMessageDemo` and explain why `after-disabled=0`, `after-enabled=1`, `after-eager=2`.
2. Switch the logger to `Level.FINE`; predict the exact number of `Supplier` invocations and the additional log lines.
3. Keep the logger at `Level.FINE` but set the handler to `Level.WARNING`; observe how the `Supplier` runs while the event never reaches stdout.
4. With SLF4J 1.7, write an `isDebugEnabled()` guard around a CPU-heavy JSON builder. Explain the difference from `LOG.debug("{}", buildJson())`.
5. With SLF4J 2.x, test `atDebug().setMessage("detail={}").addArgument(() -> heavy()).log()` with a counter when `DEBUG` is enabled and disabled.
6. With Log4j 2, run a `Supplier` overload and compare behavior when placing a filter on the appender; record the exact API/backend version.
7. Create a mutable object, log it to an async appender, and then mutate a field; compare with logging immutable snapshot values. Do not generalize one backend's result to all backends.
8. Benchmark a hot path with 10,000 log calls per second, measuring allocations, CPU, p99 latency, and events written/s before and after using `Supplier`.

## 17. Key Takeaways

- **Lazy message** defers constructing a message or expensive argument parts when the log level may be disabled.
- The `{}` placeholder defers formatting, **not** the eager Java evaluation of `heavy()` in method arguments.
- JUL has `Supplier<String>`, SLF4J 1.x typically uses guards, SLF4J 2.x has fluent `addArgument(Supplier)`, and Log4j 2 has `Supplier` overloads.
- Lazy evaluation by level does not guarantee an event reaches the file/collector or won't be dropped by appender filters or async queues.
- Never put side effects, uncontrolled I/O, or secrets in a `Supplier`; use snapshots when exact state must be logged.
- Measure with logging both disabled and enabled, using the same backend and sink, before optimizing broadly.

### References

- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `System.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.Logger.html
- SLF4J — *User Manual*, Fluent Logging API: https://www.slf4j.org/manual.html
- SLF4J — *FAQ*: https://www.slf4j.org/faq.html
- Apache Log4j 2 — *Performance* (Supplier and async): https://logging.apache.org/log4j/2.x/manual/performance.html
- Logback — *Architecture*: https://logback.qos.ch/manual/architecture.html
