# Parameterized Logging in Java: Logging Properly and Optimizing Performance

## 1. What is Parameterized Logging?

**Parameterized logging** is the practice of passing a **message template** and **argument values** separately to a logging API. The framework decides whether to record the event first, and only then formats the message according to the API's rules. This approach typically reduces unnecessary string creation overhead when a log level is disabled, while keeping messages consistent and easy to search.

Instead of concatenating strings at the call site:

~~~java
// The string is concatenated before the debug call has a chance to check the level.
log.debug("orderId=" + orderId + ", status=" + status);
~~~

With **SLF4J** or **Log4j 2**:

~~~java
log.debug("orderId={} status={}", orderId, status);
~~~

Here, `{}` is the placeholder in these APIs. The framework receives the template and arguments separately. When DEBUG is disabled, the logger can usually skip formatting and calling `toString()` on the arguments. This optimization is only meaningful if no other expensive operations occur before calling the logger.

**Do not confuse these concepts:**

- **Parameterized message:** keeps the template and arguments separate, for example `"user={} action={}"` and `userId`, `action`.
- **Lazy/supplier logging:** defers **creating the arguments or the message**, for example `() -> expensiveCalculation()`. This is an additional level of deferral.
- **Structured logging:** records fields such as `userId`, `requestId`, `durationMs` as named attributes in a log event or JSON. A message with placeholders is not necessarily a structured event.
- **Asynchronous logging:** the producer puts the event into a queue for later processing. Async and parameterized logging can be combined, but they solve two different performance problems.

The goal is to **reduce overhead on the hot path** while keeping logs rich in context, at the right level, and without losing error information.

## 2. Why Is Eager String Concatenation Wasteful?

Java evaluates argument expressions **before** invoking a method. With the statement:

~~~java
log.debug("payload=" + serializeLargeObject(payload));
~~~

If DEBUG is disabled, `serializeLargeObject(payload)` and the string concatenation may still have already executed. The logger cannot reclaim the CPU time or memory allocated before the call.

With the parameterized form:

~~~java
log.debug("payload={}", payload);
~~~

When the level is disabled, many implementations avoid formatting and avoid calling `payload.toString()`. However, if you write:

~~~java
log.debug("payload={}", serializeLargeObject(payload));
~~~

then `serializeLargeObject(payload)` **is still called before the logger checks the level**. Parameterized logging does not automatically make every argument expression lazy.

Timeline to visualize:

~~~text
A. String concatenation / expensive call before logger:
   buildString/expensive() -> logger.debug(...) -> check level -> discard

B. Passing an existing object:
   logger.debug(template, object) -> check level -> (if enabled) format/toString -> appender

C. Supplier in supporting APIs:
   create supplier -> check level -> (if enabled) invoke supplier -> format -> appender
~~~

The three cases differ in cost:

| Scenario | Remaining Cost When DEBUG Is Disabled |
| --- | --- |
| `"id=" + id` | Still evaluates the concatenation and related expressions; the JIT may optimize part of it, but you should not rely on that |
| `"id={}", id` | Evaluates the arguments and the logger call; usually avoids message formatting |
| `"obj={}", obj` | Does not create a string from `obj.toString()` when the framework discards the event early; the `obj` instance must already exist |
| `"x={}", expensive()` | **Still calls `expensive()`**, regardless of the level |
| Supplier `() -> expensive()` | Supporting APIs can defer `expensive()` until the log level is enabled |
| `if (log.isDebugEnabled()) { ... }` | Avoids expensive expressions inside the block when DEBUG is disabled; costs one extra level check |

When the log level **is enabled**, the logger still has to create the event, format/encode it, possibly capture a stack trace, and write to the sink. Parameterized logging does not make I/O costs disappear on their own.

## 3. Syntax Differences Between JUL, SLF4J, and Log4j 2

There is **no single universal placeholder syntax across all Java logging APIs**.

| API | Parameterized Call | Template Syntax | Characteristics |
| --- | --- | --- | --- |
| JUL (`java.util.logging`) | `logger.log(Level.INFO, "user={0}", userId)` | `{0}`, `{1}` | Usually formatted using `java.text.MessageFormat` in `Formatter.formatMessage(...)` |
| `System.Logger` (Java 9+) | `logger.log(System.Logger.Level.INFO, "user={0}", userId)` | `{0}`, `{1}` | JDK system-level logging API, has Supplier overloads |
| SLF4J 1.x/2.x | `log.info("user={}", userId)` | `{}` | Facade API; the backend/provider determines the sink |
| SLF4J 2.x Fluent | `log.atInfo().addArgument(userId).log("user={}")` | `{}` | Supports Supplier, key-value pairs, and cause |
| Default Log4j 2 API | `log.info("user={}", userId)` | `{}` | Default message factory uses `ParameterizedMessage` |

**Commonly confused syntax:**

~~~java
// For JUL: {0} is the placeholder; {} is not a standard placeholder.
julLogger.log(java.util.logging.Level.INFO, "user={0}", userId);

// For SLF4J and default Log4j 2: {} is the placeholder.
slf4jLogger.info("user={}", userId);
~~~

These two lines are **API illustrations** and assume the corresponding logger variables have already been created. Do not copy the `slf4jLogger` variable into a pure JDK program without adding the SLF4J library.

Do not use `String.format("user=%s", userId)` with SLF4J expecting the framework to defer string creation: `String.format(...)` runs immediately before the logger receives the value.

## 4. Standalone Java 17 Example: Arguments and Suppliers Really Differ

This example uses **JUL**, requiring no dependencies outside the JDK. A counter tracks how many times `expensive()` is called when the `FINE` level is disabled.

Create **ParameterizedLoggingDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ParameterizedLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ParameterizedLoggingDemo.class.getName());
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String expensive() {
        CALLS.incrementAndGet();
        return "computed";
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO); // FINE is not logged.
        LOG.addHandler(handler);
        try {
            // expensive() STILL runs even though FINE is disabled.
            LOG.log(Level.FINE, "disabled arg={0}", expensive());
            // Supplier does NOT run if FINE is disabled.
            LOG.log(Level.FINE, () -> "disabled supplier=" + expensive());

            // JUL uses {0}, {1}; Formatter handles the arguments.
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[] {"A17", "paid"});
            LOG.log(Level.INFO, () -> "computed=" + expensive());
            System.out.println("expensiveCalls=" + CALLS.get());
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Compile and run with **JDK 17 or newer**:

~~~bash
javac --release 17 ParameterizedLoggingDemo.java
java ParameterizedLoggingDemo
~~~

**Exact standard error (stderr)**, because `ConsoleHandler` writes to stderr by default:

~~~text
INFO order=A17 state=paid
INFO computed=computed
~~~

**Exact standard output (stdout):**

~~~text
expensiveCalls=2
~~~

The program exits with code `0`. The value `2` comes from:

1. `LOG.log(Level.FINE, "disabled arg={0}", expensive())`: **Java evaluates the argument before** the call; the counter increments to 1 even though the event is subsequently discarded.
2. `LOG.log(Level.FINE, () -> ...)`: the Supplier is not executed because `FINE` is disabled; the counter remains unchanged.
3. `LOG.log(Level.INFO, "order={0} state={1}", ...)`: the formatter receives the two strings `"A17"` and `"paid"`. It does not call `expensive()`.
4. `LOG.log(Level.INFO, () -> ...)`: `INFO` is enabled, so the Supplier runs; the counter increments to 2.

`formatter.formatMessage(record)` formats the parameters from `LogRecord`. If a custom formatter only prints `record.getMessage()`, it may print the raw template `"order={0} state={1}"`; that is a bug or quirk of the formatter, not a failure to pass the arguments.

`LOG.setUseParentHandlers(false)` prevents the root logger from printing duplicate output. `handler.setLevel(Level.ALL)` ensures the example depends only on the logger's threshold. Although `CALLS` uses `AtomicInteger` to demonstrate safe counting, this is **not a performance benchmark**.

## 5. JUL: MessageFormat, Parameters, and Lazy Messages

JUL offers two distinct techniques:

**5.1. Positional parameterization**

~~~java
logger.log(Level.INFO, "user={0}, action={1}",
        new Object[] {userId, action});
~~~

This snippet assumes `java.util.logging.Logger logger`, `Level`, and the variables are already declared. JUL stores the message template and parameter array in `LogRecord`; a `Formatter` such as `SimpleFormatter` or a formatter that calls `formatMessage(record)` will apply `MessageFormat` rules when needed.

Key points to remember:

- `{0}` is the first position; `{1}` is the second position. `{}` generally **does not** substitute values in JUL.
- `MessageFormat` has its own escaping and formatting rules, especially around single quotes and curly braces. If a message contains special characters, verify the formatted output when the formatter runs.
- Do not concatenate strings before calling: `"user=" + userId` means concatenation has already happened.
- Passing objects as parameters does not make prior computations lazy. `new Object[]{...}` and any argument-preparation expressions still execute.

**5.2. Deferring full message construction with Supplier**

~~~java
logger.log(Level.FINE, () -> "snapshot=" + expensiveSnapshot());
~~~

JUL's `log(Level, Supplier<String>)` overload invokes the supplier only if the log level is enabled. For an existing exception, use this overload:

~~~java
logger.log(Level.WARNING, exception,
        () -> "Cannot process orderId=" + orderId);
~~~

This is an illustrative snippet: `exception` is a caught `Throwable`, and `orderId` is an available value. The `log(Level, Throwable, Supplier<String>)` overload preserves the exception in `LogRecord.thrown` so the formatter can print the stack trace. Do not manually concatenate `exception.getStackTrace()` into a string.

**5.3. Using `System.Logger` when appropriate**

Since Java 9, the `System.Logger` API also supports `MessageFormat`-style parameterized messages and Supplier overloads:

~~~java
System.Logger sysLog = System.getLogger("demo.orders");
sysLog.log(System.Logger.Level.INFO, "order={0}", orderId);
sysLog.log(System.Logger.Level.DEBUG,
        () -> "snapshot=" + expensiveSnapshot());
~~~

`System.Logger` delegates to a backend via `LoggerFinder`. It is **not** identical to `org.slf4j.Logger` or `java.util.logging.Logger`, and parameter syntax must still follow the specific API.

## 6. SLF4J: Writing Efficiently with the Classic API

SLF4J commonly uses the `{}` pattern:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void update(String orderId, String status, long durationMs) {
        LOG.debug("order={} status={} durationMs={}",
                orderId, status, durationMs);
    }
}
~~~

This Java class compiles when the project includes the **SLF4J API and a compatible provider** (such as Logback Classic). It does not run standalone on the JDK alone.

Advantages:

- Keeps templates clear and meaningful; the log event can carry arguments separately until formatting.
- When DEBUG is disabled, this approach typically skips string concatenation and converting objects to text.
- Makes it easy to standardize field names in messages, such as `orderId={} durationMs={}`.
- Aids code review and source search because all events of the same kind share one template.

However:

~~~java
// expensive() is evaluated right at the call site, even when DEBUG is disabled.
LOG.debug("report={}", renderLargeReport());
~~~

To avoid expensive computations in **classic SLF4J 1.x or 2.x**:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("report={}", renderLargeReport());
}
~~~

`isDebugEnabled()` guards the expression inside. This is a valid choice when computing the value is very expensive. You do not need to wrap **every** parameterized log statement in an `if`; cheap, already-available arguments usually do not need the extra branch.

**Argument overloads:** SLF4J provides optimized overloads for 1 or 2 standard arguments. With 3+ arguments, the varargs overload may allocate an `Object[]` array. Implementations and the JIT may optimize differently; do not claim that "parameterized logging = zero allocations." For hot paths and high throughput, measure actual allocations.

**Autoboxing:** passing `int`, `long`, or other primitives to an `Object` parameter can trigger boxing. The compiler/JIT can sometimes optimize certain cases away, but results depend on the code, JDK, and backend. Do not replace all logging with string concatenation just to avoid boxing while overlooking formatting costs.

## 7. SLF4J 2.x Fluent API: Supplier, Key-Value, and Cause

Starting in **SLF4J 2.0**, the fluent API lets you build an event step by step and supply lambdas:

~~~java
// Illustrative snippet; requires Logger LOG and method renderLargeReport().
LOG.atDebug()
        .setMessage("report={}")
        .addArgument(() -> renderLargeReport())
        .log();
~~~

When DEBUG is disabled, the builder does not emit the event and the supplier does not run. **You must end the chain with `.log()`**; omitting `.log()` means no event is created even when DEBUG is enabled.

You can also use the shorthand form:

~~~java
LOG.atDebug().log("order={} status={}", orderId, status);
~~~

However, calling `renderLargeReport()` directly inside `log("report={}", renderLargeReport())` still executes the method before the framework checks the level. To truly defer execution, use `addArgument(Supplier<?>)` or `setMessage(Supplier<String>)` as appropriate.

**Key-value pairs do not have to be inside the message text:**

~~~java
LOG.atInfo()
        .addKeyValue("orderId", orderId)
        .addKeyValue("durationMs", durationMs)
        .setMessage("order completed")
        .log();
~~~

This attaches key-value pairs to the event builder, which is useful when the backend/encoder supports structured logging. **Do not assume every layout will print all key-value pairs**: verify your encoder configuration and the actual logged output.

**Attaching a Throwable properly in the fluent API:**

~~~java
LOG.atError()
        .setCause(exception)
        .addKeyValue("orderId", orderId)
        .log("order failed");
~~~

This snippet assumes the logger and variables are already declared. `setCause(...)` informs the backend that this is an exception, allowing the layout to output the stack trace. Do not convert a stack trace into a string just to insert it into `{}`.

**Version note:** the fluent API does not exist in SLF4J 1.7. Systems using SLF4J 2.x require a compatible provider; upgrading only the API while forgetting the backend can cause the application to fall back to NOP or emit warnings.

## 8. Log4j 2: ParameterizedMessage and Suppliers

The default Log4j 2 API uses `{}` with the appropriate message factory:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class BillingService {
    private static final Logger LOG = LogManager.getLogger();

    public void paid(String invoiceId, long amountCents) {
        LOG.info("invoice={} amountCents={}", invoiceId, amountCents);
    }
}
~~~

This class requires the **Log4j 2 API and a compatible implementation/bridge**; it is not a standalone JDK example. By default, messages typically use `ParameterizedMessage`; Log4j 2 optimizes parameterized messages and can reuse certain internal structures depending on configuration.

**Supplier for expensive operations:**

~~~java
// Requires a Log4j 2 logger and a declared expensiveReport() method.
LOG.debug("report={}", () -> expensiveReport());
~~~

Log4j 2 provides overloads accepting `Supplier<?>` for arguments or the entire message, deferring execution until the level permits. Do not assume every API with a `debug(...)` method understands suppliers in the same way: for example, classic SLF4J does **not** have a Supplier overload on `debug(String, Object)`.

Log4j 2 also supports a **fluent LogBuilder** in compatible versions. If you use it, follow the API and documentation for your actual version rather than copying from SLF4J and changing imports.

**Formatters and message factories:** do not mix the default `{}` with `%s`. Log4j 2 offers `getFormatterLogger()`/`printf(...)` for `String.format`-style formatting when needed, but that formatting path has different costs and rules from `ParameterizedMessage`. Use the default `{}` on hot paths when no special formatting is required.

## 9. Arguments When the Level Is Disabled: Which Costs Remain?

Parameterized logging optimizes **message formatting**, but it does not eliminate all costs. When reading code, separate the costs of argument creation, branching, and writing to the sink.

**9.1. Already-available arguments**

~~~java
LOG.debug("userId={} retries={}", userId, retries);
~~~

If `userId` is an existing string and `retries` is an integer, the pre-logger cost is relatively small. In many systems, this is the default choice that balances readability and performance.

**9.2. Expensive computation in an argument**

~~~java
LOG.debug("requestDump={}", serialize(request));
~~~

Even with `{}`, `serialize(request)` still runs immediately. The fix is to check the level or use a supplier with a supporting API. Do not call `request.toString()` before passing it to the logger if your goal is deferral.

**9.3. Many arguments, creating maps or arrays**

~~~java
LOG.debug("a={} b={} c={}", a, b, c);
~~~

Three arguments may use varargs; the array for the call can be allocated even when DEBUG is disabled. If code builds a large `Map.of(...)` upfront just to log a DEBUG event, that map is also allocated. Do not construct complex structures solely as arguments for disabled logs.

**9.4. Lambdas are not completely free**

~~~java
LOG.atDebug().setMessage("snapshot={}")
        .addArgument(() -> snapshotOf(order)).log();
~~~

With SLF4J 2.x, the supplier avoids calling `snapshotOf(order)` when DEBUG is disabled. However, the lambda may capture `order`, which can incur creation/allocation overhead depending on the JVM and context; the backend also has its own work when logging is enabled. Use this approach for expensive computations rather than overusing it for simple values.

**9.5. Performance also depends on the sink**

Even when formatting is optimized, console I/O, synchronous file writes, flushing, JSON encoding, exception stack traces, lock contention, network queues, and collectors can be far more expensive than concatenating a short string. Optimize the entire pipeline based on measurements.

## 10. Exception Logging and Parameterization

Do not accidentally turn an exception into a string and lose its stack trace:

~~~java
// SLF4J or Log4j 2; illustrative snippet, variables already declared.
// Not ideal: loses the Throwable structure if only logging the message.
LOG.error("order={} failed: {}", orderId, ex.getMessage());

// Better: pass the Throwable using the API's overload/convention.
LOG.error("order={} failed", orderId, ex);
~~~

In supporting APIs, a trailing `Throwable` argument is recognized and routed to the event's exception field. Check the overloads and placeholder count: do not accidentally pass an exception as a parameter formatted into `{}` and lose the cause.

In JUL, the overload is different:

~~~java
julLogger.log(java.util.logging.Level.SEVERE, ex,
        () -> "order=" + orderId + " failed");
~~~

This example uses `java.util.logging.Logger` and `Throwable` `ex`. `log(Level, Throwable, Supplier<String>)` preserves the cause for the formatter.

**Do not format stack traces on every call:**

~~~java
// Avoid doing expensive work even when ERROR is not emitted:
// log.error("error=" + Arrays.toString(ex.getStackTrace()));
~~~

Full exception recording typically relies on structured data and the backend's layout/encoder. However, consider sensitive data in messages, stack traces, request payloads, and exception causes; parameterized logging does not automatically strip secrets.

## 11. Templates, Placeholders, and Structured Data

**Keeping message templates stable** helps with reading source code and categorizing events:

~~~java
LOG.info("payment failed orderId={} provider={}", orderId, providerName);
~~~

If you concatenate a long payload into the template text or construct messages with hundreds of variations, log backends and search tools may struggle to group similar records.

However, a parameterized message **does not automatically have a schema**. A JSON encoder might only output:

~~~json
{
  "level": "INFO",
  "message": "payment failed orderId=A17 provider=acme"
}
~~~

If you want to query by `orderId` or `provider` without parsing text, use MDC/context data, fluent key-value pairs, or an appropriate structured logging API, and verify the output in the sink:

~~~json
{
  "level": "INFO",
  "message": "payment failed",
  "orderId": "A17",
  "provider": "acme"
}
~~~

The two JSON snippets above are **illustrative examples**, not guaranteed output from every backend.

Do not pass an entire object containing credentials, tokens, or personal data into `{}` just for convenience. The object's `toString()` may expose unintended fields. Performance optimization must never compromise logging data policies.

## 12. Async Logging: Relationship Between Parameterized Events and Formatting Time

In async logging, the producer can enqueue an event containing a template and arguments for a worker thread to format and write later. This reduces time spent on the producer thread, but you must understand **when data is captured**.

~~~text
Producer:
  logger.debug("cart={}", cart)
       │ accepted?
       ▼
Async queue: event, arguments/context
       │
       ▼
Background consumer:
  format/toString/encode
       │
       ▼
File / console / remote sink
~~~

If `cart` is a **mutable** object and `toString()` is called later, the logged data may reflect the state **after the event was created**, depending on the framework and configuration. Some backends snapshot part of the data eagerly, while others defer it. Do not rely on specific behavior without verifying it. When accuracy matters, snapshot immutable fields (ID, status, timestamp) at event creation time.

**Do not retain references to reusable buffers** such as a `StringBuilder` in an event processed later while assuming it will not change. If a log needs the value at call time, record an immutable string/value or use the framework's standard snapshot mechanism.

Parameterized logging does not replace **draining/flushing** an async queue and does not provide data durability. Disabled log levels, dropped queue items, or a broken sink are separate reasons an event may not appear.

## 13. Common Syntax and Correctness Mistakes

| Mistake | What Happens | How to Fix |
| --- | --- | --- |
| Using `"id=" + expensive()` at DEBUG | Evaluates and concatenates strings before the level is checked | Use placeholders for existing values, supplier/guard for expensive values |
| `LOG.debug("x={}", expensive())` expecting laziness | `expensive()` still runs | Use a guard or a Supplier API |
| Using `{}` in JUL | Does not match `MessageFormat` syntax | Use `{0}`, `{1}` |
| Using `{0}` in SLF4J | Not substituted under `{}` syntax | Use `{}` |
| `String.format(...)` before the logger | Formatting already happens at the call site | Pass the message template and arguments |
| Forgetting `.log()` in SLF4J Fluent | No event is emitted | End the builder chain with `log()` |
| Passing a lambda to classic SLF4J `debug(String,Object)` | Not guaranteed to invoke the lambda to produce data; may just format the lambda object | Use SLF4J 2's fluent `addArgument(Supplier)` or a guard |
| Logging `ex.getMessage()` instead of the cause | Loses the stack trace/exception structure | Use the Throwable overload or `setCause` |
| Passing a mutable payload to an async logger | Data may change before formatting | Snapshot fields at event time |
| Creating `Map.of(...)` only for DEBUG | Still allocates before the call | Use a guard or a structured API that supports laziness |
| Assuming varargs never allocates | Array/boxing allocations may occur | Measure allocations on your actual JVM/version |
| Treating `{}` as structured logging | Backend may only output plain text | Use key-value/MDC and a schema-aware encoder |
| Logging an entire object containing secrets | Sensitive data may appear via `toString()` | Select safe fields, apply masking/redaction |
| Mismatched placeholder count | Output may retain placeholders or drop arguments depending on the API | Test the formatter, verify template/arguments |
| Using `%s` as if it were Log4j 2's default | Default message factory uses `{}` | Use the right factory or `printf/getFormatterLogger` |

## 14. Measuring Logging Performance Reliably

You should not conclude "approach A is 30x faster" from a single manual measurement, because results depend on the JDK, CPU, backend, log level, argument count, object size, encoder, async queue, and I/O.

**14.1. Distinguish the two benchmark modes**

- **Disabled level benchmark:** DEBUG/TRACE disabled; measures the cost of traversing code and the logger when **no** event is emitted. This is where the difference between concatenation, parameterized logging, and Supplier is usually clearest.
- **Enabled level benchmark:** DEBUG/INFO enabled; measures formatting, serialization, sink writes, garbage collection, I/O, and contention. In this mode, template optimization cannot eliminate the cost of writing logs.

**14.2. Measure throughput, latency, and allocations**

Useful metrics include operations/second, p95/p99 latency, bytes allocated/op, GC counts, dropped events, and sink rate. With async logging, clarify whether the measurement point is "producer enqueue succeeded" or "record reached the sink." Do not use enqueue throughput to claim sustainable write speed.

**14.3. Use an appropriate benchmark framework**

Use **JMH** for Java microbenchmarks instead of timing a `System.nanoTime()` loop in a short program and comparing results. The JVM has JIT warmup, dead-code elimination, and escape analysis; an unstable log level or a backend writing to the console can skew results.

Minimal case design:

1. `debug("x=" + id)`.
2. `debug("x={}", id)`.
3. `debug("x={}", expensive())`.
4. `if (isDebugEnabled()) { debug("x={}", expensive()); }`.
5. With SLF4J 2, `atDebug().addArgument(() -> expensive()).log("x={}")`.

Ensure each case performs the same data-source work; measure with DEBUG both enabled and disabled; pin the provider/version and aggregate results across multiple runs. With production metrics, also monitor dropped logs and collector backpressure to avoid optimizing for "fast" while losing logs.

## 15. Practical Rules for Choosing a Solution

| Condition | Recommended Choice | Reason |
| --- | --- | --- |
| 1–2 cheap values already available | Placeholder `{}` with SLF4J/Log4j 2 | Minimal code, no eager formatting |
| Value requires a DB query, JSON serialization, or algorithm | Supplier or level guard | Avoid paying the cost when the level is disabled |
| Internal library using only the JDK | JUL with `{0}`, `{1}` or `Supplier<String>` | Zero extra dependencies, matches the API |
| Application using SLF4J 1.7 | Placeholders + `isDebugEnabled()` when needed | Fluent API does not exist yet |
| Application using SLF4J 2.x | Placeholders; fluent `addArgument(Supplier)` for expensive values | Builds messages lazily, supports key-value |
| Application using Log4j 2 API | Default placeholders or Supplier overload | Supports message factories and lazy args |
| Need to query business fields in a log system | Structured key-value/MDC and JSON encoder | Provides a schema and searchable fields |
| Async event holds a mutable object | Snapshot immutable values before enqueueing | Prevents content mutation before formatting |
| Important exception | Attach Throwable/cause using the proper overload | Preserves stack trace and categorization info |
| Strict GC/throughput requirements | Benchmark the full pipeline with JMH and realistic load | Optimize based on data, not assumptions |

## 16. Code Review and Configuration Checklist

1. **Identify the API in use:** JUL, `System.Logger`, SLF4J, or Log4j 2; use the right placeholder syntax.
2. **Spot expensive work at call sites:** JSON serialization, queries, heavy `toString()` calls, collection/array creation, stack trace formatting, byte conversions.
3. **Separate disabled vs. enabled behavior:** if DEBUG is disabled, which methods still run and which objects are still allocated?
4. **Use placeholders for simple arguments:** reduce string concatenation, keep templates stable and readable.
5. **Use suppliers or guards for expensive arguments:** do not put business side effects inside a logging supplier because the supplier might not run.
6. **Check placeholder counts and pass Throwable via the right overload:** syntax mistakes are often not caught by the compiler.
7. **Preserve semantics in async logging:** snapshot when needed; do not pass mutable arguments modified by another thread without synchronization.
8. **Check data policies:** do not log credentials/tokens and do not unintentionally serialize entire domain objects.
9. **Review the sink and formatter:** call `formatMessage` in custom JUL formatters; use a compatible encoder to preserve key-value pairs when using structured APIs.
10. **Measure at production scale:** throughput/latency/allocations/drops for your actual backend and configuration.

## 17. Self-Check Questions

1. In `log.debug("value={}", expensive())`, why does `expensive()` still run if DEBUG is disabled?
2. Compare `log.debug("x=" + x)` and `log.debug("x={}", x)` when `x` is an existing object. What is usually deferred?
3. Does JUL use `{0}` or `{}`? Why might a custom `Formatter` print the raw template?
4. Why does `LOG.log(Level.FINE, () -> expensive())` not invoke the Supplier when `FINE` is disabled?
5. Which SLF4J 2.x API defers evaluating an argument? What happens if you forget to call `.log()`?
6. With SLF4J 1.7, when computing an expensive report, what should you do before calling `debug`?
7. Does parameterized logging guarantee zero array or boxing allocations across all versions and argument counts?
8. Why might the message `"orderId={}"` not produce a queryable `orderId` field like JSON?
9. What problem can arise when passing a mutable object to an async logger?
10. If an exception needs its stack trace logged, how should you pass it?
11. When benchmarking, why must you measure both DEBUG enabled and DEBUG disabled cases?
12. Does parameterized logging replace the durability, flush, or drop policies of an async logger?

**Answer hints:** (1) Java evaluates arguments before the call; (2) avoids eager formatting/`toString`, not creating the object; (3) `{0}`, the formatter must call `formatMessage`; (4) the Supplier overload is invoked conditionally; (5) `addArgument(Supplier)`, omitting `log()` emits no event; (6) `isDebugEnabled()` or an appropriate level guard; (7) no; (8) lacks a schema/encoder; (9) the value may change before formatting; (10) Throwable overload or `setCause`; (11) the bottlenecks differ; (12) no.

## 18. Official References

- [SLF4J Manual — parameterized logging and Fluent API](https://www.slf4j.org/manual.html): `{}`, `LoggingEventBuilder`, `addArgument(Supplier)`, and key-value pairs.
- [SLF4J — LoggingEventBuilder API](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): `addArgument(Supplier<?>)`, `setMessage`, `setCause`, and `log()`.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): providers, parameterization, and version compatibility.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): `log(Level, String, Object...)` and Supplier.
- [Java SE 17 — java.util.logging.Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)`, message formatting.
- [Java SE 17 — System.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.Logger.html): JDK parameterized and Supplier API.
- [Apache Log4j 2 — API](https://logging.apache.org/log4j/2.x/manual/api.html): `{}`, message factories, throwables, and formatting options.
- [Apache Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): `ParameterizedMessage`, `ReusableParameterizedMessage`, and structured messages.
- [Apache Log4j 2 — Logger javadoc](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/Logger.html): Supplier overloads, parameters, and logger.
