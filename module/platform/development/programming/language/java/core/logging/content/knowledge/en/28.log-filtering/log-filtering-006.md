# Exception-Based Filtering in Java Logging

## 1. What is Exception-Based Filtering?

**Exception-based filtering** is a rule that decides whether a log event proceeds to one or more destinations (console, file, centralized logging system) based on the **exception attached to the event**. The condition can be the exception type, inheritance relationship, `cause` chain, log level, or business context.

For example, an application may process thousands of invalid inputs per minute. Each time it parses `"abc"` into a number, a `NumberFormatException` may be thrown. If these input errors are already handled and tracked by a dedicated metric, the system can **filter out repetitive INFO records for the expected exception**, while still keeping WARNING/ERROR records when an incident needs investigation.

An important distinction: **filtering a log event does not catch, remove, or alter the exception in the Java execution flow**. A `catch` block decides how to handle an exception in the program; a logging filter only decides whether to emit the log record. Even if a record is filtered out, the exception can still be thrown and propagated normally.

General processing flow:

~~~text
try/catch or error-handling layer
       │ logger.log(level, message, throwable)
       ▼
  Logger level / configuration
       │ if allowed to create log event
       ▼
  Log event + Throwable/proxy
       │
       ▼
  Exception filter: type + cause + level + context
       ├── DROP / DENY: do not send to the destination where the filter is attached
       └── KEEP / NEUTRAL: continue pipeline
                                 │
                                 ▼
                          Appender / Handler
                                 │
                                 ▼
                          Console / File / Remote
~~~

Filter placement varies by framework. A filter on a **logger** can affect multiple handlers/appenders; a filter on a **single sink** affects only that output. Therefore, you should determine the **intended scope** before choosing where to attach the filter.

## 2. Choosing the Right Filter Criteria: Type, Cause, Level, and Context

| Criterion | Meaning | Examples and Notes |
| --- | --- | --- |
| Direct exception type | Matches against the `Throwable` attached to the log event | `NumberFormatException`, `IOException` |
| Inheritance | Allows or denies subclasses as well | `instanceof IllegalArgumentException` also matches `NumberFormatException`; the reverse is not true |
| `cause` chain | Finds an exception wrapped by another exception | `CompletionException` may wrap `IOException` in `getCause()` |
| Log level | Preserves high-impact events | Drop only below WARNING; keep WARNING/SEVERE even if the type matches |
| Logger/sink | Reduces noise only on an observation channel | Drop on console, but keep in an investigation file |
| Business context | Distinguishes "expected" from "abnormal" | Same `IOException`, but `event=retry` differs from `event=data_loss` |

Example cause chain:

~~~text
CompletionException
    └── IOException
          └── SocketException
~~~

If the policy is "keep I/O incidents", checking only `event.getThrown() instanceof IOException` will **not match** when the outermost wrapper is `CompletionException`. You must traverse `getCause()` or the corresponding proxy API. Conversely, traversing all causes to drop `IOException` could suppress important wrapped errors; you must combine it with level and context.

A clear policy should specify:

- **When to drop:** only a well-defined set of expected exceptions, at low log levels, on the designated channel.
- **When to keep:** WARNING/ERROR, non-matching errors, records without an exception, and audit/security events.
- **When to measure:** the number of filtered records, frequency, and error-handling outcomes should still be observable via metrics or summary events.
- **What is excluded:** for example, a policy that only follows the `cause` chain without traversing `getSuppressed()`; if suppressed exceptions matter, the logic must be extended intentionally.

Do not rely on `exception.getMessage()` or a stringified stack trace to infer the error type when the system already has the `Throwable`. Messages can change across versions, locales, and inputs; user-supplied messages may also contain sensitive data.

## 3. Java Util Logging (JUL) API: Filter and LogRecord

With the built-in `java.util.logging` package in the JDK:

- `java.util.logging.Filter` is a functional interface with the method `boolean isLoggable(LogRecord record)`.
- `LogRecord.getThrown()` returns the `Throwable` attached to the event, or `null` if none is attached.
- `record.getLevel()` lets you inspect severity. `Level.WARNING` and `Level.SEVERE` are standard JUL levels.
- `Logger.setFilter(...)` attaches a filter at the emitting logger; `Handler.setFilter(...)` attaches a filter at the target handler. Handlers also have their own level, so a record must pass the relevant levels and filters to be published.
- When calling `logger.log(Level.WARNING, "message", exception)`, the three-argument overload taking a `Throwable` stores the exception in `LogRecord.thrown`. If you only concatenate `exception.toString()` into the message, `getThrown()` remains `null`.

Example of attaching a filter to a console handler:

~~~java
ConsoleHandler handler = new ConsoleHandler();
handler.setFilter(new MyExceptionFilter());
logger.addHandler(handler);
~~~

This snippet assumes `logger` and `MyExceptionFilter` are already defined. A filter on one handler does not automatically block the event from reaching other handlers. When you need to keep complete records in a file for investigation, you can apply the filter only to the console channel and leave it off the audit/file channel.

In JUL, `isLoggable(...)` returning `true` means **this filter lets the record pass the current step**; it does not guarantee the sink will write it successfully, because other level, handler, or I/O conditions can still block it.

## 4. Standalone Java 17 Example: Filtering Expected Parse Errors

Demo policy:

1. Keep **all events at WARNING or above**, regardless of exception.
2. For events **below WARNING**, drop the record when `NumberFormatException` appears directly or in the `cause` chain.
3. Keep all other records, including records with no `Throwable`.
4. Apply the rule only to the **ConsoleHandler** configured in the example.

Create **ExceptionFilterDemo.java**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.logging.ConsoleHandler;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionFilterDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionFilterDemo.class.getName());

    private static final class DropExpectedParsing implements Filter {
        @Override
        public boolean isLoggable(LogRecord record) {
            // Important warnings are always kept.
            if (record.getLevel().intValue() >= Level.WARNING.intValue()) {
                return true;
            }
            // Identity-based set avoids loops if the cause graph contains a cycle.
            Set<Throwable> seen =
                    Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cause = record.getThrown();
                 cause != null && seen.add(cause);
                 cause = cause.getCause()) {
                if (cause instanceof NumberFormatException) {
                    return false;
                }
            }
            return true;
        }
    }

    public static void main(String[] args) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFilter(new DropExpectedParsing());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO, "expected parse failure",
                    new NumberFormatException("bad value"));
            LOG.log(Level.INFO, "wrapped parse failure",
                    new IllegalStateException("outer",
                            new NumberFormatException("bad value")));
            LOG.log(Level.INFO, "network failure",
                    new IOException("timeout"));
            LOG.log(Level.WARNING, "parsing escalation",
                    new NumberFormatException("important"));
            LOG.info("application healthy");
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

With JDK 17+:

~~~bash
javac --release 17 ExceptionFilterDemo.java
java ExceptionFilterDemo
~~~

**Exact standard error (stderr):**

~~~text
INFO network failure
WARNING parsing escalation
INFO application healthy
~~~

**Standard output (stdout):** empty. `ConsoleHandler` writes to stderr by default; the example formatter intentionally prints only the level and message so the output stays deterministic. The program exits with code `0`.

**Event-by-event breakdown:**

| Event | Level | Exception | Result |
| --- | --- | --- | --- |
| `expected parse failure` | INFO | Direct `NumberFormatException` | **Drop** |
| `wrapped parse failure` | INFO | `IllegalStateException` → `NumberFormatException` | **Drop** because cause matches |
| `network failure` | INFO | `IOException` | **Keep** |
| `parsing escalation` | WARNING | `NumberFormatException` | **Keep** due to high level |
| `application healthy` | INFO | No exception | **Keep** |

`LOG.setLevel(Level.ALL)` and `handler.setLevel(Level.ALL)` ensure that the filter itself decides which records are dropped in the example. `LOG.setUseParentHandlers(false)` prevents the root handler from printing duplicates; outside a demo program, you must account for your logger hierarchy policy.

**Intentional design choices:**

- `instanceof NumberFormatException` also matches subclasses (if any), without matching every other `IllegalArgumentException`.
- `IdentityHashMap` tracks visited `Throwable` instances by object identity to prevent infinite loops if an abnormal `cause` chain has a cycle. This is a lightweight safeguard inside a filter that must run fast.
- It does not traverse `getSuppressed()`; this policy follows only the `cause` chain. If suppressed exceptions need to be inspected, traverse the graph with a `seen` set and a resource bound.
- The filter does not modify or catch exceptions in business logic. It only decides which events appear on the console.
- In a real application, dropping `NumberFormatException` solely by type may be too broad. You should add a logger name, event code, context, or specific endpoint group so only truly expected cases are dropped.

## 5. Pitfalls When Attaching a Throwable to a Log Event

### 5.1. Printing Text Is Not Attaching a Throwable

~~~java
try {
    Integer.parseInt("oops");
} catch (NumberFormatException ex) {
    LOG.info("Parse failed: " + ex); // String only.
    LOG.log(Level.INFO, "Parse failed", ex); // Includes Throwable.
}
~~~

In the first call, `LogRecord.getThrown() == null`; an exception filter will not recognize it even though the message contains the class name. The second call uses the `log(Level, String, Throwable)` overload to attach the exception object properly. Depending on your data policy, avoid logging `ex.getMessage()` verbatim if it may contain personal or secret data.

With SLF4J, the common call is:

~~~java
log.warn("Failed to process order", exception);
~~~

This snippet assumes `log` is an initialized SLF4J logger. Standard SLF4J overloads pass the trailing `Throwable` as error metadata to the backend. In contrast, `log.warn("Failure: {}", exception.getMessage())` only logs a string; the event may not carry a `Throwable`. When using varargs overloads or the fluent API, verify how the cause is passed in the version you use.

### 5.2. Wrapped Exceptions

Asynchronous example:

~~~java
Throwable outer = new java.util.concurrent.CompletionException(
        new java.io.IOException("connection reset"));
~~~

Checking only `outer instanceof IOException` fails; traversing `outer.getCause()` reveals the `IOException`. Systems may also use `ExecutionException`, `InvocationTargetException`, or framework-specific wrapper exceptions. Do not infer wrappers from the message text alone.

### 5.3. Missing Throwable

An event such as `log.error("Remote call failed")` may not carry an exception. If a filter defaults to `DENY` when `getThrown() == null`, you can accidentally lose many errors that have no stack trace. For a policy that **drops a few expected exceptions**, the default should be **keep/neutral** for all non-matching events.

### 5.4. Not Every Exception Has the Same Meaning

A `NumberFormatException` may reflect a handled input validation error, or it may indicate application code failing to parse internal data. Therefore, add conditions such as `eventId`, logger name, domain, route, or level. Do not apply a "we have seen this exception before" rule across every service or environment.

## 6. Logback Classic: Filtering by ThrowableProxy in an Appender

For applications using **SLF4J + Logback Classic**, Logback provides regular appender filters via `ch.qos.logback.core.filter.Filter<ILoggingEvent>`. The event exposes `event.getThrowableProxy()` of type `IThrowableProxy`. The proxy provides `getClassName()` and `getCause()`; it is not necessarily the original `Throwable` instance from business code.

Here is an example filter class that drops events **below WARN** only if the exception chain contains the exact class name `java.lang.NumberFormatException`. This code is intended for a **project that already uses Logback Classic** and must be placed in the package declared at the top of the file.

Create **src/main/java/com/example/logging/ExpectedParseFilter.java**:

~~~java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.IThrowableProxy;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class ExpectedParseFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event.getLevel().isGreaterOrEqual(Level.WARN)) {
            return FilterReply.NEUTRAL;
        }

        IThrowableProxy exception = event.getThrowableProxy();
        // Limit depth so the filter always has bounded cost.
        for (int depth = 0; exception != null && depth < 32; depth++) {
            if ("java.lang.NumberFormatException"
                    .equals(exception.getClassName())) {
                return FilterReply.DENY;
            }
            exception = exception.getCause();
        }
        return FilterReply.NEUTRAL;
    }
}
~~~

Attach it to an appender in **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.ExpectedParseFilter"/>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Explanation:**

- `DENY` drops the event at this appender; `NEUTRAL` defers the decision to the next filter (if no remaining filter blocks it, the appender proceeds).
- Returning `NEUTRAL` for WARN and above avoids accidentally bypassing other filters; do not return `ACCEPT` just because you want to keep the event, because `ACCEPT` can short-circuit the remaining filters in the same phase.
- Checking `IThrowableProxy.getClassName()` against the fully qualified name matches **only that exact class**, not its subclasses. If you need hierarchy matching, add explicit rules for the target types or a controlled type-matching mechanism.
- The `<filter>` element sits inside the `CONSOLE` appender, so it affects only that channel. If you also have a separate audit/file appender without the filter, the record will still appear there.
- `ILoggingEvent.getThrowableProxy()` can be `null`; this code keeps events that have no attached exception.
- `%ex` in the encoder controls **rendering the stack trace** for kept events; whether a stack trace pattern is present does not change the filter's decision.

Do not copy old examples using `JaninoEventEvaluator` without checking your version: **Logback 1.5.13 removed** that evaluator. A simple custom Java filter avoids configuration-expression dependencies and is easy to test. Make sure the `logback-classic`, `logback-core`, and SLF4J versions in your application match.

**Regular filters vs. TurboFilters:** regular filters receive a full `ILoggingEvent`, making it straightforward to inspect `ThrowableProxy`. A `TurboFilter` runs earlier—before or during event creation—and has different parameters; you cannot drop `decide(ILoggingEvent)` as-is into a `TurboFilter`. For high-throughput applications, evaluate the cost/accuracy trade-off and benchmark under realistic logging load before changing filter placement.

## 7. Log4j 2: Distinguishing Event Filters from Text Filtering

Log4j 2 Core supports filter placement at the global configuration, logger configuration, appender reference, and appender levels. Filter results are:

| Result | Meaning |
| --- | --- |
| `DENY` | Drops the event at the current filtering stage |
| `NEUTRAL` | Undecided; lets subsequent rules/levels continue processing |
| `ACCEPT` | Accepts at the current stage, potentially skipping subsequent filters/checks depending on placement |

To inspect the actual exception, use `org.apache.logging.log4j.core.LogEvent.getThrown()` in a **custom filter/plugin tailored to Log4j 2 Core**. This API returns the `Throwable` if present, so the logic can use `instanceof` and `getCause()` just like the JUL example.

Illustrative snippet showing **the core logic inside a properly declared and registered Log4j 2 filter class** (not a standalone Java class):

~~~java
@Override
public Result filter(LogEvent event) {
    if (event.getLevel().isMoreSpecificThan(Level.WARN)) {
        return Result.NEUTRAL;
    }
    for (Throwable cause = event.getThrown();
         cause != null;
         cause = cause.getCause()) {
        if (cause instanceof NumberFormatException) {
            return Result.DENY;
        }
    }
    return Result.NEUTRAL;
}
~~~

In a real implementation, this logic requires imports, a class extending the Log4j 2 `Filter` API, plugin registration, and a bound on the `cause` loop. For the classes referenced here, `Level` is `org.apache.logging.log4j.Level` and `LogEvent` is `org.apache.logging.log4j.core.LogEvent`; they are **not** the JUL or Logback equivalents. `isMoreSpecificThan(Level.WARN)` is used to keep WARN and more severe levels.

**Do not confuse filter types:**

- Log4j 2's `RegexFilter` primarily filters by formatted message/string content; it **does not inspect the `Throwable` tree with `instanceof`**.
- `ThresholdFilter` filters by level and is unaware of exception classes.
- Patterns/layouts that display stack traces only affect how a record is rendered; to drop an event, you need a filter in the pipeline.
- `DENY` at the global or logger level has a broader scope than `DENY` on a single appender; explicitly design which channels are allowed to drop logs.

In applications with async loggers/appenders, filter placement also affects cost: filtering after an event is enqueued reduces I/O, but does not eliminate the enqueueing overhead. Filtering before the queue can save more resources, provided semantics and `Throwable` visibility are preserved at that stage.

## 8. Filter in Application Code or at the Framework Level?

**At the error-handling site (source-level):**

~~~java
try {
    Integer.parseInt(rawInput);
} catch (NumberFormatException ex) {
    // Example: invalid input has already been handled by business logic.
    // Record a metric or log a stable event code if needed.
    log.debug("Invalid numeric input for field {}", fieldName);
}
~~~

This snippet illustrates application code that already has `rawInput`, `fieldName`, and an SLF4J logger `log`; it is not a standalone program. The advantage is that the author knows the context—whether the error is expected or abnormal. The downside is having to maintain this across many call sites and not being able to modify third-party libraries directly.

**At the framework level (logger/appender filter):** centralizes one policy across many log sites, which is useful when a dependency logs repetitive exceptions. However, if the rule is too broad, it can hide a new bug that throws the same exception type. It works best when the policy is validated against real log samples and backed by an alternative diagnostic channel.

Choose based on scope:

| Need | Usually Appropriate Approach |
| --- | --- |
| No log needed for handled input-validation errors | Adjust the log call at the handling site |
| Console appender is too noisy, full file must be kept | Filter on the console appender/handler |
| Third-party library logs exceptions frequently | Filter by logger name + exception + level |
| Need to correlate exceptions with requests/traces | Keep MDC/trace ID and structured logs; avoid dropping prematurely |
| Audit, security, or durability requirements | Do not rely on filters that discard evidence; use an appropriate audit channel |

## 9. Cause Chains, Suppressed Exceptions, and Multithreaded Exceptions

**Cause chain:** many frameworks wrap the root exception. You can walk the full `Throwable.getCause()` chain; add a depth limit or identity set when running against untrusted or unusual data to avoid excessive CPU usage.

**Suppressed exceptions:** `try-with-resources` can attach exceptions thrown while closing resources via `getSuppressed()`, which do not necessarily appear in `cause`. The JUL example above **does not** inspect suppressed exceptions. If your policy requires it, traverse both `cause` and `suppressed` as a graph with a visited set and a node limit, and test cases where the primary error differs from the suppressed error.

**Async and thread pools:** exceptions from `Future.get()` are typically wrapped in `ExecutionException`, while `CompletableFuture` chains may surface `CompletionException`. Inspect the `Throwable` **actually passed to the logger** rather than assuming the logger unwraps every cause.

**Error vs. Exception:** `Throwable` also includes `Error` subclasses such as `OutOfMemoryError` and `StackOverflowError`. Never write a default rule that "drops all Throwables of a broad error family" just to cut noise, especially in production. When a system is under resource pressure, a complex filter can itself add risk: avoid creating new stack traces, performing I/O, or acquiring locks inside a filter.

**Runtime context:** the same exception class in two services or two execution branches can mean very different things. Combining logger name, event code, trace ID, and level classifies incidents far better than class name alone.

## 10. Performance and Safety of Custom Filters

A filter may be invoked on **every log event**. Best practices:

1. Check cheap conditions first: level, logger name, event code; only traverse causes when necessary.
2. Prefer `instanceof` or exact class-name lookups; avoid compiling regexes or capturing new stack traces per event.
3. Write filters as pure functions of the event, avoiding unsynchronized mutable state. The JUL example uses local variables and can be called safely from multiple threads.
4. Bound cause/suppressed traversal depth when needed and guard against unexpected exceptions inside the filter. Never let a log sink fail because a filter threw an unhandled exception.
5. Do not make network requests or log back through the same filtered logger inside `isLoggable`/`decide`: this risks recursion, deadlocks, or latency spikes.
6. Count dropped events using a metric or appropriate counter if required by policy, rather than emitting a new log event through the same pipeline on every drop.
7. If filtering reduces component logs, keep error metrics, latency, status codes, and monitoring alerts; fewer logs do not mean the errors disappeared.
8. When filtering by exception class name (such as with Logback's proxy), account for the risk of class or package renames during library upgrades.

Measure actual overhead with traffic-representative benchmarks rather than judging by filter line count. At thousands of events per second, inspecting stack traces or running long regexes on every event can negate the benefits of async logging.

## 11. Minimum Test Suite

Cases to verify **before and after** enabling the filter:

| Test Case | Exception and Level | Expected Behavior for Demo Policy |
| --- | --- | --- |
| Direct | `NumberFormatException`, INFO | Dropped on console |
| Wrapped | `IllegalStateException → NumberFormatException`, INFO | Dropped on console |
| Non-matching | `IOException`, INFO | Kept |
| High severity | `NumberFormatException`, WARNING | Kept |
| No Throwable | Normal INFO | Kept |
| Message contains exception name, no `Throwable` attached | INFO | Kept |
| Exception subclass | A subclass of the policy target type | Verify match behavior via `instanceof` (or proxy name) |
| Long or cyclic chain | Unusual or deep cause chain | Does not hang; bounded traversal |
| Concurrent threads | Mixed logs with and without Throwable | No races, no cross-event leakage |
| Other appenders | Same event sent to file and console | Verify filter scope is accurate |
| Async queue/shutdown | Queued events at program exit | Drained/flushed per framework; do not confuse filtering with durability |

For Logback or Log4j 2, use a test appender or temporary sink and **initialize the exact framework version** in tests. Do not only assert that the filter returns `DENY`; verify that the record is actually absent from or present in the intended sink. If the test does not pass the `Throwable` via the proper overload, it will not exercise the exception policy.

A quick verification method can use events with stable IDs:

~~~text
exception-filter-check id=E1 type=NumberFormatException level=INFO  -> console: none
exception-filter-check id=E2 type=IOException          level=INFO  -> console: E2
exception-filter-check id=E3 type=NumberFormatException level=WARN -> console: E3
~~~

This is a **test expectation table**, not the stdout of the Java program in section 4.

## 12. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Filtering only on `exception.getMessage()` | Text-dependent, brittle, and may leak data | Use `Throwable`/proxy and exception type |
| Dropping everything when `getThrown() == null` | Loses error logs that have no stack trace | Default to keeping non-matching events |
| Checking only the outermost exception | Misses wrapped causes | Traverse `getCause()` with a depth bound/visited set |
| Ignoring level or audit channels | Suppresses critical alerts | Keep WARN/ERROR and audit channels |
| Returning `ACCEPT` for every event you want to keep | May bypass other filters in the same stage | Use `NEUTRAL` when you do not want to short-circuit the chain |
| Attaching filter at root/global without checking scope | Drops logs across unintended sinks | Attach to the specific appender/handler first |
| Using `RegexFilter` to "match exception class" | Filters message text rather than inspecting `Throwable` | Use an event-based custom filter |
| Logging only `ex.toString()` in the message | `getThrown()` is `null` | Pass the exception to a `Throwable`-accepting overload |
| Calling a logger or doing network I/O inside a filter | Recursion, contention, and deadlocks | Keep filters fast with minimal side effects |
| Filtering away all error signals | Incident investigation lacks evidence | Keep metrics and sampling or a full-detail channel |
| Copying JUL code into Logback/Log4j 2 | Different APIs, level types, and semantics | Use the backend-specific API |
| Assuming a filter equals catching the exception | Business errors still occur | Handle exceptions in code; filters only control logging |

## 13. Self-Check Questions

1. Why does `logger.log(Level.INFO, "failed: " + ex)` usually prevent a JUL filter from detecting the exception via `LogRecord.getThrown()`?
2. If `CompletionException` wraps `IOException`, is checking only the outermost `Throwable` enough?
3. Why does a filter on `ConsoleHandler` only drop console logs, whereas a filter on a logger can affect multiple handlers?
4. Why must the "drop `NumberFormatException` at INFO" policy in the example still keep WARNING/SEVERE records?
5. When using Logback's `IThrowableProxy.getClassName()` for string comparison, does it automatically match subclasses?
6. How do `DENY`, `NEUTRAL`, and `ACCEPT` differ?
7. Why must `Throwable.getSuppressed()` be handled separately when a policy requires inspecting all errors?
8. When is adjusting the log call at the exception-handling site better than a global filter?
9. How can you verify that a filter reduces noise without hiding new incidents?
10. If an async appender has accepted an event, does a sink filter guarantee the event has been durably persisted?

**Answer key:** (1) the exception is only concatenated into text; (2) you must traverse `cause`; (3) filtering scope differs; (4) to avoid hiding severe signals; (5) no, class-name comparison is an exact match; (6) drop, continue evaluation, or finish selection for the stage depending on the framework; (7) suppressed exceptions are not necessarily in the `cause` chain; (8) when the source site knows the error is expected and knows the business conditions; (9) use tests and drop/error metrics; (10) no, filtering does not imply flushing or durability.

## 14. Official Documentation

- [Java 17 — java.util.logging.Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html): `isLoggable(LogRecord)` contract.
- [Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getThrown()`, `getLevel()`.
- [Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): `Throwable` overloads, logger-level filters, parent handlers.
- [Java 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): handler-level filters and levels.
- [Logback — Filters](https://logback.qos.ch/manual/filters.html): regular filters, TurboFilters, `DENY`/`NEUTRAL`/`ACCEPT`.
- [Logback — ILoggingEvent](https://logback.qos.ch/apidocs/ch.qos.logback.classic/ch/qos/logback/classic/spi/ILoggingEvent.html): `getThrowableProxy()`.
- [Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): filter placement and semantics.
- [Log4j 2 — LogEvent](https://logging.apache.org/log4j/2.x/javadoc/log4j-core/org/apache/logging/log4j/core/LogEvent.html): event `getThrown()`.
