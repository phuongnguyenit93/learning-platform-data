# Unnecessary String Concatenation in Java Logging: Why It Is Slow and How to Fix It

## 1. The Anti-Pattern to Identify

**Unnecessary string concatenation** in logging occurs when a program **constructs a message or computes logging data before knowing whether the event will actually be recorded**. For example:

~~~java
// SLF4J/Log4j 2: anti-pattern.
log.debug("Order " + orderId + " state=" + state);
~~~

Even when DEBUG is disabled, Java still has to **evaluate the arguments** for the `log.debug(...)` call. The concatenation expression may convert values into `String`, call `toString()`, and perform unnecessary work. If this code runs repeatedly on a hot path, CPU and GC overhead can increase without producing any useful logs.

A better way to write it:

~~~java
// SLF4J/Log4j 2: pass the template and arguments separately.
log.debug("Order {} state={}", orderId, state);
~~~

In the second call, the framework gets the chance to skip **formatting** the message when DEBUG is not enabled. However, **the expressions producing `orderId` and `state` still have to be evaluated by Java**. This is a key distinction between *parameterized logging* and *lazy evaluation*.

A worse example:

~~~java
// expensiveSnapshot() runs BEFORE the logger call, even when DEBUG is disabled.
log.debug("snapshot={}", expensiveSnapshot());
~~~

To avoid calling an expensive method when the level is disabled, use a `Supplier` or a guard appropriate for your logging API. This article clearly distinguishes three issues: **string concatenation**, **message formatting**, and **argument evaluation**.

## 2. Java Evaluates Arguments Before Calling a Method

A fundamental rule of Java: before a method is invoked, its argument expressions must be evaluated in the specified order. Therefore:

~~~java
log.debug("status=" + buildStatus());
~~~

in terms of evaluation order, can be thought of as:

~~~java
String message = "status=" + buildStatus();
log.debug(message);
~~~

Even if `debug` checks the level internally and returns immediately, `buildStatus()` has already executed. This remains true if `buildStatus()` is CPU-intensive, queries data, has side effects, or can throw an exception.

**Things you should not assert as absolutes:**

- Not every `+` operator creates multiple `StringBuilder` instances like in older Java versions. Java 9+ optimizes string concatenation, typically using `invokedynamic`/`StringConcatFactory`; the exact details are decided by the compiler/JIT.
- For **all-constant** concatenation, the compiler may fold it into a single constant; that is usually **not** a problem.
- The JIT may optimize away some allocations, but it cannot arbitrarily eliminate computations that have observable effects such as incrementing a counter, performing I/O, or throwing an error.
- Simply "having string concatenation" does not by itself prove an application is noticeably slow. You must look at **frequency, message size, conversion cost, and the number of filtered events**.

The real anti-pattern is **creating data solely for logging when it is not needed**, rather than banning every `+` operator across all Java code.

## 3. Commonly Overlooked Cases

| Common Code | What Happens Before the Logger Checks the Level | Risk |
| --- | --- | --- |
| `log.debug("id=" + id)` | Concatenates strings and converts `id` to text | CPU/allocation when DEBUG is off |
| `log.debug("user={}", user.toString())` | Calls `toString()` | Builds a large string; may expose sensitive fields |
| `log.debug("state={}", calculateState())` | Executes `calculateState()` | Cost or side effects even if the event is dropped |
| `log.debug(String.format("n=%d", n))` | Formats the string upfront | Unnecessary locale/conversion/allocation |
| `log.debug("json=" + serialize(dto))` | Serializes the entire object | CPU, memory, exceptions, and data exposure |
| `log.trace("items=" + items.stream().map(...).toList())` | Runs the stream pipeline | Computes redundant data, causing allocations |
| `log.info("report=" + new StringBuilder().append(...))` | Builds the message eagerly | A builder does not make the logger lazy |
| `MDC.put("details", expensive())` | Computes and stores thread context immediately | Still costs when logging is off; context may leak |
| `log.debug("size={}", size)` | Just reads a simple variable | Usually lightweight; optimization is mainly in formatting |
| `log.debug("name={}", name)` | Passes an existing `String` | Appropriate use case for parameterized logging |

A common mistake during code review: seeing `{}` and concluding that everything is lazy. If the argument is still `repository.findAll()` or `objectMapper.writeValueAsString(...)`, the cost of evaluating the **argument** may still be fully incurred.

## 4. The Cost Is More Than Just a Discarded String

An unemitted log statement can still consume:

1. **CPU:** evaluating expressions, calling `toString()`, formatting dates/numbers, serializing JSON, sorting/streaming data.
2. **Temporary memory:** strings, arrays, wrapper objects, and buffers; actual allocation depends on the compiler/JIT.
3. **GC pressure:** many short-lived objects can increase garbage collection frequency.
4. **Unintended I/O:** if the message-building function reads files, calls APIs, hits a database, or queries state.
5. **Side effects:** incrementing counters, mutating caches, or altering state from a "debug-only" call.
6. **Unnecessary errors:** the message-computing function throws an exception even though the logging level is disabled.
7. **Data exposure:** converting DTOs or confidential information into text at an uncontrolled layer.

In code handling a rare request, the cost of a simple concatenation may be negligible. But in a loop processing 100,000 events/second, invoking a serializer only to discard the entire message is both an architectural and a performance issue.

**Distinguish the two phases:** converting domain data into argument values is the responsibility of Java application code; formatting the template and rendering to the sink belongs to the logging API/backend. Fixing the latter phase with placeholders does not automatically solve the former.

## 5. Before and After: SLF4J (Logback or Other Providers)

SLF4J uses `{}` syntax. Example from a typical call:

~~~java
// BAD: concatenate strings before the logger call.
log.debug("order " + orderId + " status " + status);

// BETTER: pass already-available values.
log.debug("order {} status {}", orderId, status);
~~~

If DEBUG is not enabled, the latter approach usually avoids building the full message. However:

~~~java
// STILL EAGER: queryState() still runs even when debug is off.
log.debug("order status={}", queryState(orderId));
~~~

For expensive operations, you can guard the call:

~~~java
if (log.isDebugEnabled()) {
    String state = queryState(orderId);
    log.debug("order status={}", state);
}
~~~

These are **illustrative snippets**, not standalone Java classes: `log` is an initialized `org.slf4j.Logger`, and the domain variables and methods must exist.

**Limitations of guards:** `isDebugEnabled()` primarily checks the corresponding level. The backend may still filter by marker/appender/sink and drop the event afterward; you should not claim a guard guarantees "compute only if every downstream filter accepts it." It helps avoid major costs when the level is definitely disabled.

**Do not guard every log line.** For a few cheap arguments, placeholders are usually concise, readable, and efficient enough. Guards are appropriate when the expression is very expensive or causes unwanted side effects.

## 6. SLF4J 2.x Fluent API: Supplier for Expensive Arguments

SLF4J 2.x provides `LoggingEventBuilder`. When the level is disabled, the returned builder behaves as a no-op; the API supports `Supplier` for expensive arguments:

~~~java
// SLF4J 2.x; assumes log and orderId already exist.
log.atDebug()
        .setMessage("order={} snapshot={}")
        .addArgument(orderId)
        .addArgument(() -> buildSnapshot(orderId))
        .log();
~~~

**Key point:** `buildSnapshot(orderId)` is **inside the lambda**, not invoked immediately when creating the argument. When the event is disabled, the Supplier does not need to build the snapshot.

**Do not confuse the following two snippets:**

~~~java
// BAD: method already called before passing to the builder.
log.atDebug().addArgument(buildSnapshot(orderId))
        .log("snapshot={}");

// GOOD: pass a Supplier to the builder.
log.atDebug().addArgument(() -> buildSnapshot(orderId))
        .log("snapshot={}");
~~~

The Fluent API must end with `log()`. If you only call `atDebug().addArgument(...)` and forget `log()`, the event is never emitted even when DEBUG is enabled.

Remember to check versions and providers:

- `atDebug()` and `addArgument(Supplier<?>)` require **SLF4J 2.x**; they do not apply the same way in SLF4J 1.7.
- Writing `log.debug("snapshot={}", () -> expensive())` in classic SLF4J **does not automatically** treat the argument as a lazily evaluated Supplier. Use the supported Fluent API or a guard.
- Lazy does not mean the value is security-safe. When logging is enabled, a Supplier can still produce secrets/PII; you must apply proper schema and redaction policies.

## 7. JUL (`java.util.logging`): Using `{0}` and `Supplier`

`java.util.logging.Logger` is built into the JDK. JUL **does not** use SLF4J's `{}` for message formatting; standard formatters use `java.text.MessageFormat` with `{0}`, `{1}`, ... placeholders:

~~~java
// BAD: concatenate strings before calling Logger.
LOG.fine("id=" + id + " state=" + state);

// BETTER: keep the template and parameters separate.
LOG.log(java.util.logging.Level.FINE,
        "id={0} state={1}", new Object[]{id, state});
~~~

However, if you pass a function call directly:

~~~java
// EAGER: method already ran before Logger.log receives the arguments.
LOG.log(java.util.logging.Level.FINE, "details={0}", expensiveDetails());
~~~

the computation still happens while FINE is disabled.

JUL provides overloads that accept `Supplier<String>`:

~~~java
// LAZY: only builds the string if the level is accepted.
LOG.fine(() -> "details=" + expensiveDetails());

// Also valid:
LOG.log(java.util.logging.Level.FINE,
        () -> "details=" + expensiveDetails());
~~~

These snippets assume `LOG` is of type `java.util.logging.Logger`. In addition to lazy message building, JUL also has `log(Level, Throwable, Supplier<String>)` to preserve the exception as `LogRecord.thrown`.

Do not write `LOG.log(Level.INFO, "id={}", id)` expecting JUL to substitute `{}`; use `{0}` according to JUL's rules.

## 8. Standalone Java 17 Example: Proving the Difference

The following example tests **observable behavior** rather than timing: `expensiveSnapshot()` increments a counter each time it is actually called. The test runs in two phases: with `FINE` disabled and then enabled.

Create the file **UnnecessaryConcatenationDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class UnnecessaryConcatenationDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.unnecessary.concat");
    private static final AtomicInteger SNAPSHOTS = new AtomicInteger();

    private static String expensiveSnapshot() {
        return "snapshot-" + SNAPSHOTS.incrementAndGet();
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
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);
        try {
            LOG.setLevel(Level.INFO); // FINE is disabled.
            LOG.fine("concat=" + expensiveSnapshot());
            LOG.log(Level.FINE, "param={0}", expensiveSnapshot());
            LOG.fine(() -> "lazy=" + expensiveSnapshot());
            if (LOG.isLoggable(Level.FINE)) {
                LOG.fine("guard=" + expensiveSnapshot());
            }
            System.out.println("afterDisabled=" + SNAPSHOTS.get());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "lazy=" + expensiveSnapshot());
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            System.out.println("afterEnabled=" + SNAPSHOTS.get());
        } finally {
            LOG.removeHandler(handler);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Compile and run on **JDK 17+**:

~~~bash
javac --release 17 UnnecessaryConcatenationDemo.java
java UnnecessaryConcatenationDemo
~~~

**Exact standard output (stdout):**

~~~text
afterDisabled=2
afterEnabled=3
~~~

**Exact standard error (stderr):**

~~~text
FINE lazy=snapshot-3
INFO order=ORD-42 state=PAID
~~~

**Exit code:** `0` under normal execution conditions.

Why does this output occur?

- During the `LOG.setLevel(Level.INFO)` phase: `FINE` is disabled.
- `"concat=" + expensiveSnapshot()` calls the method, incrementing the counter from 0 → 1; the message is discarded.
- `LOG.log(Level.FINE, "param={0}", expensiveSnapshot())` also calls the method upfront, incrementing the counter from 1 → 2; the message is still discarded.
- `LOG.fine(() -> "lazy=" + expensiveSnapshot())` receives a lambda; because FINE is disabled, the Supplier does not run, and the counter stays at 2.
- The `if (LOG.isLoggable(Level.FINE))` block is skipped; the counter stays at 2.
- Once FINE is enabled, the same Supplier form actually executes; the counter goes 2 → 3 and the line `FINE lazy=snapshot-3` appears on stderr.
- The line `INFO order=ORD-42 state=PAID` uses `{0}`/`{1}`, proving that JUL parameters are formatted after the message reaches the formatter.
- `ConsoleHandler` writes to stderr; the program prints counters via `System.out.println`, so they appear on stdout.

**Limitations of this experiment:** The counter verifies **how many times the method was called**; it does not measure allocated bytes, Java JIT speed, throughput, or benchmark results. `expensiveSnapshot()` in this example only increments a counter and does not intentionally query a DB or slow down the system.

## 9. What Should High-Quality Tests Prove?

A unit test for this anti-pattern should verify:

1. When DEBUG/FINE is disabled, the Supplier or guard does **not** invoke the expensive method.
2. When the level is enabled, the message contains the expected content and parameters.
3. When the level is disabled, no event reaches the sink; yet the test still verifies the sink is active using another INFO event.
4. When levels/filters are added, events route properly; do not confuse the message template with the rendered message.
5. When logging an exception, the `Throwable` remains attached structurally rather than being converted into plain text.
6. No logs containing fake secrets are emitted when debug is enabled.
7. Changing the logging level causes no business side effects.

With JUL, you can use an in-memory `Handler` to collect `LogRecord` instances; inspect `getMessage()` (template), `getParameters()` (arguments), and `Formatter.formatMessage(record)` (rendered message).

With Logback Classic, use `ListAppender<ILoggingEvent>`; with Log4j 2 Core, capture `LogEvent` or layout output. Testing both a **positive event** and a **negative event** together prevents false-positive passes caused by an unattached or inactive appender.

Do not just assert `expensiveCalls==0` without also testing with logging enabled: you might accidentally create a logger that is always disabled, leaving both tests and production blind to real errors.

## 10. Log4j 2: Parameterized Logging and `Supplier`

In the Log4j 2 API, avoid:

~~~java
// BAD: eager concatenation.
LOGGER.debug("User " + userId + " role " + lookupRole(userId));
~~~

For cheap, already-available data, use message parameters:

~~~java
LOGGER.debug("User {} role {}", userId, role);
~~~

If `lookupRole(userId)` is expensive, do not invoke it directly before the logger call:

~~~java
// BAD: lookupRole is evaluated before LOGGER.debug runs.
LOGGER.debug("User {} role {}", userId, lookupRole(userId));
~~~

Log4j 2 supports `Supplier` for arguments in the appropriate APIs:

~~~java
// Log4j 2; LOGGER is an initialized org.apache.logging.log4j.Logger.
LOGGER.debug("User {} role {}", () -> userId, () -> lookupRole(userId));
~~~

This is a **Log4j 2 library-dependent snippet**, not code that runs with the JDK alone. According to Log4j 2 documentation, `Supplier` avoids evaluating expensive arguments if the event is discarded before materialization is needed. Exact behavior can depend on filters and the `Message` type used in the running version; do not substitute SLF4J APIs without checking overloads.

For complex conditions, a guard can still be useful:

~~~java
if (LOGGER.isDebugEnabled()) {
    LOGGER.debug("Detailed snapshot={}", buildSnapshot());
}
~~~

However, guards primarily check the level. An event can still be filtered out by markers, appenders, or other policies. Do not rely on a guard to guarantee "execute only if every downstream backend accepts it."

## 11. How Does Parameterized Logging Differ from Lazy Argument Computation?

| Expression | Concatenated/Formatted Before Call? | Expensive Function Runs When Level Is Off? | Notes |
| --- | --- | --- | --- |
| `log.debug("x=" + x)` | Concatenation may happen before the call | No expensive function if `x` is already a variable | Avoid when only for logging; use placeholders |
| `log.debug("x={}", x)` | Backend can defer formatting | No expensive function if `x` is already computed | Usually the default choice |
| `log.debug("x={}", expensive())` | Template is not formatted eagerly | **Yes** | Placeholders do not defer arguments |
| `log.debug("x={}", x.toString())` | `toString()` runs eagerly | **Yes** | Pass a safely vetted object or a Supplier |
| `log.atDebug().addArgument(() -> expensive()).log("x={}")` | Per SLF4J 2 Fluent | **No** when level is off | Deferred Supplier |
| `if (log.isDebugEnabled()) log.debug("x={}", expensive())` | Enters block only when enabled | **No** when level is off | Effective guard for level, does not replace all filters |
| `LOG.fine(() -> "x=" + expensive())` | JUL builds message when enabled | **No** when FINE is off | Message Supplier |
| `LOG.log(Level.FINE, "x={0}", expensive())` | Separate JUL message template | **Yes** | Eager argument |
| `log.debug(String.format("x=%s", x))` | `String.format` runs eagerly | Can cost CPU/allocation | Unsuitable when only for logging |

**Two different goals:**

- If the argument is already available: use **parameterized logging** to avoid eager concatenation/formatting.
- If the argument is not yet computed and is expensive: use a **Supplier** or a **level guard** to avoid eager evaluation.
- If the argument contains secrets: do not pass it to the logger regardless of laziness; prefer omitting or masking fields at the source.

## 12. `String.format`, `MessageFormat`, JSON Serialization, and `toString()`

Some forms of "unnecessary string concatenation" do not contain the `+` operator:

~~~java
// BAD if used only for DEBUG.
log.debug(String.format("batch=%d size=%d", batchNo, size));
log.debug("payload=" + mapper.writeValueAsString(dto));
log.debug("graph={}", domainGraph.toString());
log.debug("report={}", expensiveReport());
~~~

The variables and methods here are illustrative and must be defined in the application. `mapper.writeValueAsString` depends on Jackson and can throw an exception; it is not a logging API.

**Impact:**

- `String.format` builds the string **before** the logger call; it incurs formatting/locale overhead different from backend patterns.
- `MessageFormat.format(...)` also runs immediately if you call it explicitly beforehand.
- Serializing a large object to JSON is usually far more expensive than concatenating a few numbers and also risks leaking PII.
- `toString()` may traverse an entire collection or domain graph, trigger unintended logic, or accidentally include credentials.
- `Arrays.toString`, `Collectors.joining`, and `StringBuilder` are all eager computations if executed outside a Supplier/guard.

Instead of serializing raw DTOs, log standardized metadata such as `eventCode`, `entityRef`, `fieldCount`, or `payloadBytes` according to policy. Enable full diagnostics only in appropriate environments with proper authorization and size limits.

## 13. Why You Should Not Use `StringBuilder` to "Fix" Logging

Sometimes a code review replaces:

~~~java
log.debug("id=" + id + " state=" + state);
~~~

with:

~~~java
log.debug(new StringBuilder()
        .append("id=").append(id)
        .append(" state=").append(state)
        .toString());
~~~

This **does not fix the anti-pattern**: `StringBuilder` is still constructed and `toString()` is still called before `debug(...)` receives its argument.

In Java 17, the compiler/JIT can optimize `+` concatenation very well; manual `StringBuilder` actually makes the code longer and more complex. Instead, write:

~~~java
log.debug("id={} state={}", id, state);
~~~

If the data requires expensive pre-computation, add a Supplier or guard appropriate for your framework. Do not benchmark with a single un-warmed loop and conclude that `StringBuilder` is faster or slower than `+` across all workloads.

## 14. Numeric Parameters, Objects, Boxing, and Minor Overhead

Although parameterized logging avoids **string formatting**, the cost is not necessarily zero.

- Some overloads may use `Object...` varargs and temporary arrays.
- Primitives may be boxed depending on the overload and how the compiler/backend implements it.
- Wrappers, markers, context, or logging events may still be created when the level is enabled.
- Async appenders have queue/ring-buffer and event-dispatch overhead.
- An object argument may be retained until the formatter/encoder processes it later.

**Do not blindly micro-optimize a line like `log.debug("count={}", count)`** if `count` is already available and a profiler shows no issue. The impactful optimizations are usually eliminating I/O, service calls, JSON serialization, or collection traversals performed only for disabled logs.

For always-on INFO/WARN logs, parameterized logging still provides benefits in message template consistency and structured processing, though the backend will generally still need to materialize the output at some point.

## 15. Asynchronous Logging and Mutable Objects

Parameterized logging may pass arguments to the backend before the message is rendered. In an async pipeline, **be careful with mutable objects**:

~~~java
// Illustration: payload may continue to be mutated after enqueueing the event.
log.debug("payload={}", mutablePayload);
mutablePayload.clear();
~~~

In some backends/layouts, the message may be formatted before enqueueing; in others, it may happen later. Do not rely on a universal assumption about **when `toString()` is called** across all backends and versions.

How to handle this:

1. If you need to log values at a specific point in time, create a **safe, immutable snapshot**.
2. If the snapshot is expensive, create it inside a Supplier/guard **when it matches the event semantics**.
3. In multithreaded code, do not use a lambda that reads a mutable object whose state may change before evaluation.
4. Do not pass an entire DTO containing sensitive data into an async logger expecting the sink to mask it later.
5. Benchmark and test with the real async backend/configuration, not just a mock logger.

**Laziness does not automatically guarantee snapshot semantics.** Deferring too late can cause the message to reflect a state different from the moment the event occurred. You must balance observability accuracy against cost.

## 16. Exceptions and Stack Traces: Do Not Concatenate `Throwable` into Text

Another anti-pattern:

~~~java
// BAD: converts Throwable into a string, potentially losing the structured stack trace.
log.error("payment failed: " + exception);
~~~

With SLF4J/Logback or Log4j 2, prefer passing the `Throwable` in the dedicated exception parameter/overload:

~~~java
// Variables log, orderId, and exception are already declared.
log.error("payment failed for order={}", orderId, exception);
~~~

Typically, the backend receives the exception in a separate `Throwable` field, allowing the renderer to format the stack trace and causes. With JUL:

~~~java
LOG.log(java.util.logging.Level.SEVERE, "payment failed", exception);
~~~

When you only need a lazily generated message alongside a `Throwable`, JUL also has an overload:

~~~java
LOG.log(java.util.logging.Level.SEVERE, exception,
        () -> "payment failed order=" + safeOrderRef);
~~~

The snippets above use the respective logger APIs with safe variables. Do **not** call `exception.getMessage()`, `exception.toString()`, or serialize the entire stack trace before knowing the level; exception messages can also contain secrets, URLs with tokens, or personal data.

**Important:** Whether to log a full exception is a security and operational decision. If general-purpose channels are not allowed to contain sensitive information, use error codes and a restricted-access investigation channel. Do not use a lazy Supplier as an excuse to log prohibited data.

## 17. Structured Logging: Do Not Lose Fields via String Concatenation

If a system uses Elasticsearch/OpenSearch, Loki, or OpenTelemetry Collector, a string like:

~~~text
"order=" + id + " state=" + state
~~~

is usually less useful than an event with explicit fields. Structured logging lets you query by **`event.code`, `order_ref`, `outcome`, `trace_id`** without brittle regexes trying to parse text.

SLF4J 2 Fluent example:

~~~java
log.atInfo()
        .addKeyValue("eventCode", "ORDER_PAID")
        .addKeyValue("orderRef", safeOrderRef)
        .addKeyValue("outcome", "SUCCESS")
        .log("order state changed");
~~~

This is an SLF4J 2.x snippet. **Whether key-value pairs are emitted as standalone JSON fields depends on the provider/layout**; verify your encoder/backend. Do not put secrets into `addKeyValue` or MDC assuming the parser will mask them.

If you need to compute an expensive object for a structured field, check the appropriate Supplier/guard API and evaluate whether it is justified. Avoid concatenating all fields into a single `message` String and assuming the Collector will parse it reliably forever.

## 18. How Are Security and Log Injection Related to String Concatenation?

A non-performance consequence occurs when concatenating **untrusted** data:

~~~java
// Risk: raw input may contain CR/LF and forge log lines.
log.info("login input=" + rawUserInput);
~~~

If `rawUserInput` contains newlines, a single text log line can be split into multiple lines and mislead readers or parsers. For other data, `toString()` may expose emails, API keys, passwords, or request bodies.

Best practices:

- Never log passwords, OTPs, session tokens, bearer tokens, API keys, or private keys.
- Use event codes and reason codes from an **allowlist** instead of raw request data.
- Use a standard JSON encoder and escape control characters.
- Limit data size to prevent log amplification.
- Mask/strip sensitive data **before** the logger call; use sink-level redaction as a secondary layer.
- Test with fake sentinel values (e.g., `TEST_SECRET_DO_NOT_LOG`) to confirm output does not leak them.
- Do not use string concatenation to "work around" serialization errors by dumping the entire DTO.

Parameterized logging reduces eager string construction, but **does not automatically make data safe**. You must control the message, args, `Throwable`, MDC, and structured fields.

## 19. Measurable Optimization: JFR, Profilers, and JMH

Prioritize optimization only when there is evidence of CPU, latency, allocation, or log volume issues.

**Practical approach:**

1. Identify hot paths with frequent DEBUG/TRACE calls when those levels are normally disabled.
2. Use a profiler/Java Flight Recorder (JFR) to inspect time spent in `toString()`, JSON serialization, formatters, string concatenation, and allocation pressure.
3. Catch unintended method calls with counter-based unit tests as in Section 8.
4. Use **JMH** for microbenchmarks, controlling warmup, forks, JDK, logger backend, filters, log levels, and sinks.
5. Compare variants **under identical conditions**: eager concatenation, placeholders, guards, Suppliers; measure both enabled and disabled cases.
6. Avoid benchmarking a loop where the JIT can eliminate the entire body or only measuring `System.nanoTime()` speed.
7. Evaluate end-to-end application throughput/latency; do not make a logger call harder to maintain if the gain is negligible.

**Benchmarking pitfalls:**

- Writing real logs to the console when comparing disabled vs. active logging unfairly.
- Skipping warmup/JIT, or failing to control GC or terminal I/O.
- Changing too many parameters at once (backend, appender, template, args).
- Measuring only elapsed time while ignoring how many times `expensive()` ran and allocations.
- Claiming "zero allocation" for all machines from a single run.

For Log4j 2, the garbage-free logging documentation recommends deep optimization only when logging is genuinely a bottleneck, and re-measuring assumptions per version and environment.

## 20. Rules for Choosing an Approach by Situation

| Situation | Appropriate Choice | Reason |
| --- | --- | --- |
| An existing `String` value, DEBUG off | `log.debug("id={}", id)` | No eager formatting |
| Multiple primitive/immutable variables | `{}` template or JUL `{0}` | Readable, consistent |
| Calling DB/HTTP just to log | Avoid calling; do so only if truly needed and permitted | Logging should not add expensive I/O |
| Dumping a large collection during debug | Guard or Supplier with a size limit | Computed only when needed |
| Building JSON just to log | Prefer structured events and backend encoders | Reduces manual serialization |
| Need lazy message in JUL | `LOG.fine(() -> ... )` | Supported directly by the JDK |
| Need lazy argument in SLF4J 2 | Fluent `addArgument(() -> ...)` | Deferred Supplier is supported |
| Need lazy argument in Log4j 2 | Appropriate Supplier overload in the API | Avoids eager expensive calls |
| `Throwable` associated with an error | Use the `Throwable` overload/parameter | Preserves structured exception |
| Mandatory audit event | Recorder/pipeline per audit policy | Does not depend on DEBUG sampling |
| Sensitive data | Omit/mask/allowlist before the logger | Optimization does not replace security |

**Prioritize simplicity first:** use placeholders for already-available data, and add Suppliers/guards for expensive expressions. Do not turn the entire codebase into complex lambdas just to save a minor concatenation.

## 21. Unit Testing and Static Analysis Checks

Useful review and code-scanning criteria:

- Does a `logger.debug/trace/fine` call have `"x=" + value` directly in its arguments?
- Is there `String.format(...)`, `MessageFormat.format(...)`, or `JsonSerializer...` inside a log call?
- Is there `.toString()` or `+` concatenation on large DTOs/collections?
- Are there database/network calls inside log arguments?
- Is there an `isDebugEnabled` check where values are still computed **before** the `if` block?
- Is a lazy Supplier misplaced, e.g., `() -> alreadyComputedExpensiveString`?
- Are JUL `{}` or SLF4J `{0}` used with an incompatible template syntax?
- Are the logger facade and provider/backend versions compatible?
- Is a `Throwable` lost because it was concatenated into text?
- Is raw PII or a secret entering the message, args, or MDC?

Tooling such as IntelliJ inspections, Sonar rules, or lint plugins can flag useless string concatenation calls, but **static analysis cannot know all side effects and business rules**. Combine code review, counter tests, and profiling.

**Well-targeted tests:** one test confirming `expensiveCalls==0` when DEBUG is off, one test confirming the right message when DEBUG is on, and one privacy test confirming a secret sentinel is absent **from both the event and the sink**.

## 22. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "JDK 17 optimizes `+`, so it is fine" | The JIT cannot eliminate side effects of argument-computing methods | Use placeholders/Supplier/guard |
| "Having `{}` makes everything lazy" | Argument expressions are still evaluated by Java | Use `Supplier` or `isDebugEnabled` |
| Only replacing `+` with `StringBuilder` | Still builds the string before the call | Pass template and args |
| Passing `expensive()` directly to SLF4J | Method runs when DEBUG is off | SLF4J 2 Fluent Supplier or guard |
| Using `{}` in JUL | JUL formatters use `{0}` | Use the right API |
| Computing snapshot before `if` | The guard does not protect computation that already ran | Move computation inside the guard |
| Capturing a mutable object in a lambda | Value may differ when the event is logged | Take an immutable snapshot when needed |
| Forgetting `.log()` in Fluent API | No event is emitted | End the chain properly |
| Using `getMessage()` to compare formatted text in JUL | `getMessage` holds the template | Use `Formatter.formatMessage` |
| Concatenating `exception` into a String | May lose stack trace / `Throwable` field | Pass exception via the proper overload |
| Dumping raw objects in DEBUG | Enabling DEBUG may expose secrets | Allowlist/mask data |
| Guarding every log line | Clutters code with little gain when args are cheap | Optimize based on a profiler |
| Comparing speed with a single unwarmed loop | JIT/GC skews results | Use JMH and end-to-end tests |
| Assuming disabled logs cost literally nothing | Level checks and argument setup still exist | Know the limits, measure when needed |
| Assuming zero-GC from placeholders | Depends on overloads, backend, and JIT | Measure allocations on the real config |
| Optimizing logs in a way that breaks business logic | Changes side effects or log timing | Do not put business logic in message expressions |

## 23. Pre-Merge Code Checklist

1. Is there any `"prefix" + value` logging solely for debug/trace?
2. Do messages use framework-compatible templates (JUL `{0}`, SLF4J/Log4j 2 `{}`)?
3. Are arguments genuinely **already computed**, or are they calling expensive methods?
4. For expensive methods, are Suppliers/guards used with the right API/version?
5. Are DB/network calls or large payload serializations avoided when only for logging?
6. Is the cost of computing domain data needed for business logic separated from data needed only for logging?
7. Are logger/filter levels verified at runtime, avoiding disabled-event side effects?
8. Is the `Throwable` overload used instead of concatenating exceptions into text?
9. In async logging, are values snapshotted at the right time without mutable race conditions?
10. Is logged data on an allowlist, without exposing credentials or PII?
11. Do tests assert the template, formatted message, args, level, and Supplier behavior?
12. Were benchmarks/profilers consulted before micro-optimizing?
13. Is "fewer string concatenations" distinguished from "optimizing total log volume and I/O"?
14. Is the code kept simple, avoiding unnecessary abstractions just to log an existing variable?

## 24. Exercises and Self-Check Questions

**Exercise A — Identification:** With `DEBUG` disabled, which snippets still call `createSnapshot()`?

~~~java
// SLF4J.
log.debug("snapshot=" + createSnapshot());       // A1
log.debug("snapshot={}", createSnapshot());       // A2
if (log.isDebugEnabled()) {
    log.debug("snapshot={}", createSnapshot());   // A3
}
log.atDebug().addArgument(() -> createSnapshot())
        .log("snapshot={}");                      // A4, SLF4J 2.x
~~~

**Answer:** A1 and A2 still call it. A3 avoids the call because the guard is false. A4 avoids the call via the Fluent Supplier when the level is disabled. Neither A3 nor A4 guarantees skipping computation if downstream filters reject the event.

**Exercise B — Fixing code:** Given `LOG.fine("users=" + users.stream().map(...).toList())`, choose a safe approach:

- If only the already-available count is needed, log `LOG.log(Level.FINE, "userCount={0}", count)`.
- If the list is genuinely needed and permitted, use `LOG.fine(() -> "users=" + safeSummary(users))` and cap the list/length.
- Do not generate full raw user records if they contain PII. In async environments, snapshot the appropriate data source before handing off to a worker.

**Exercise C — Running Java 17:** Change `LOG.setLevel(Level.INFO)` in the Section 8 program to `Level.FINE` from the start. Predict the number of `expensiveSnapshot()` calls and stderr lines. Compare with the original run to understand the difference between direct calls and `Supplier`.

**Exercise D — Measurement:** Use a profiler/JFR or JMH on an application simulating many disabled DEBUG calls; compare `expensive()` call counts, allocations, and throughput across string concatenation, placeholders, `Supplier`, and guards. Do not draw conclusions from a single machine alone.

### Quick Questions

1. Does Java check the logging level before evaluating a method call's arguments?
2. Does parameterized logging defer `expensive()` when it is passed as a regular argument?
3. Why doesn't the compiler's use of `StringConcatFactory` eliminate all costs of string concatenation in disabled logs?
4. Does JUL use `{0}` or `{}` for standard templates?
5. Where does SLF4J 2 support `Supplier` in the Fluent API?
6. Why does forgetting `.log()` cause the fluent builder to emit no event?
7. Does using `StringBuilder` automatically create lazy logging?
8. Why shouldn't you assert that every string concatenation approach produces exactly N allocations?
9. When handling exceptions, why shouldn't you concatenate `exception.toString()` into the message?
10. When logging is enabled, does a lazy `Supplier` automatically guarantee no PII leaks?
11. Does `isDebugEnabled()` guarantee that every downstream appender filter will accept the event?
12. When using `AsyncAppender`, why must you be careful with mutable arguments?

**Hints:** (1) no; (2) no; (3) methods with side effects still run before the call; (4) `{0}`; (5) `addArgument(() -> ...)`; (6) the event has not been committed; (7) no; (8) compilers, JITs, and backends differ; (9) loses the structured `Throwable` and may leak secrets; (10) no; (11) no; (12) the event may be rendered after state has been mutated.

## 25. Official Documentation for Further Reading

- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): level checks, `log(Level, Supplier<String>)`, `fine(Supplier<String>)`, parameters, and `Throwable`.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)` and `MessageFormat`.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message, arguments, `Throwable`, and metadata.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): string concatenation and implementation notes.
- [Java SE 17 — StringConcatFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): string concatenation optimization mechanism in the JVM.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, Fluent API 2.x, and `Supplier` arguments.
- [Apache Log4j 2 — Logging API](https://logging.apache.org/log4j/2.x/manual/api.html): avoiding string concatenation, `Supplier`, and semantically sound logging.
- [Apache Log4j 2 — Garbage-free logging](https://logging.apache.org/log4j/2.x/manual/garbagefree.html): allocations, GC, and advice on measured optimization.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): microbenchmarking framework for Java.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data, log injection, and security requirements.
