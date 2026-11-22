# Filter Before Format in Java Core Logging

## 1. What does "Filter before format" mean?

When a Java application logs a message, each event can go through several steps: checking the log level, creating or receiving the event data, applying a filter, formatting the message, and then writing it to the console, file, queue, or collection system. **Filter before format** is the principle of **discarding an unnecessary log event before performing expensive formatting work** for that event.

For example, in production we may only want to keep `INFO` and above and drop `DEBUG` events or heartbeat logs that have no investigative value. If the logging system formats every event into a long string before filtering, the application has already spent CPU and allocated memory for events that end up being discarded.

Goals:

- **Reduce cost:** drop events early, minimizing unnecessary formatter/layout/encoder execution and I/O.
- **Keep policies clear:** choose the log level or acceptance criteria before deciding whether to output to each destination.
- **Avoid confusion:** an event can be accepted at the logger but rejected by a handler/appender's filter.
- **Optimize in the right place:** understand that skipping formatting in the backend **does not necessarily** prevent application code from building strings or evaluating arguments before calling the logger API.

In the examples in this article, `format` refers to the `java.util.logging.Formatter.format(LogRecord)` step or an equivalent step such as a layout/encoder in a logging backend. **Do not equate backend formatting with every string concatenation or `toString()` call that already ran in application code.**

## 2. Illustrative Pipeline: Where Is an Event Rejected?

A typical path with **Java Util Logging (JUL)**:

~~~text
Call LOGGER.info(...) / LOGGER.fine(...)
                   |
                   v
        Check logger level
                   |
           Is event created?
                   |
                   v
         Logger Filter (if any)
                   |
           Is it accepted?
                   |
                   v
           Handler.publish(...)
                   |
                   v
       Handler level + Handler Filter
                   |
           Is it accepted?
                   |
                   v
             Formatter.format
                   |
                   v
           Output (console/file/...)
~~~

This diagram illustrates common **filter-before-write** points, not a promise about every internal detail of every logging framework. JUL performs a level check at the logger before passing the event downstream; a logger filter can reject a `LogRecord` before the event is forwarded to handlers. When writing a custom `Handler`, the `publish` method itself must check `isLoggable(record)` before calling the formatter.

**Both filter locations are valuable:**

1. **Logger filter:** decides whether the event continues along the source logger's processing path. If rejected, that logger's handlers do not receive the event from that call.
2. **Handler filter:** decides whether **a specific output destination** accepts the event. For example, the console only accepts `INFO` while an audit file accepts a different set; other handlers can still process the same event according to their own configuration.

In JUL, `Handler.isLoggable(record)` checks the handler's level and filter. When the level is insufficient, the handler's filter may **not need to be called**. At the logger, a level below the threshold can cause the event to be dropped before creating a `LogRecord` or running the logger filter.

**Key point:** saying "filter before format" is only true when the backend or custom handler actually **checks the filter before calling the formatter**. A filter that reads the already-formatted message itself, or an appender that formats before filtering, can defeat the intended performance benefit.

## 3. Standalone Java 17 Example: Verifying Order with Counters

We will use only the `java.util.logging` classes built into JDK 17. The program generates five log events, with four kinds of outcomes:

- `FINE`: accepted by the logger because its level is `ALL`, but rejected by the handler because the handler's threshold is `INFO`.
- `PRIVATE ...`: rejected by the logger filter before the event reaches the handler.
- `NOISE ...`: rejected by the handler filter.
- Remaining `INFO` and `WARNING`: pass all filters and are only then formatted by the formatter.

Create the file **`FilterBeforeFormatDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FilterBeforeFormatDemo {
    public static void main(String[] args) {
        AtomicInteger loggerFilterChecks = new AtomicInteger();
        AtomicInteger handlerPublishCalls = new AtomicInteger();
        AtomicInteger handlerFilterChecks = new AtomicInteger();
        AtomicInteger formatCalls = new AtomicInteger();

        Logger logger = Logger.getLogger("demo.filter.before.format");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Filter loggerFilter = record -> {
            loggerFilterChecks.incrementAndGet();
            return !record.getMessage().startsWith("PRIVATE ");
        };
        logger.setFilter(loggerFilter);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                handlerPublishCalls.incrementAndGet();

                // Custom Handler must check itself before formatting.
                if (!isLoggable(record)) {
                    return;
                }

                System.out.print(getFormatter().format(record));
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        handler.setLevel(Level.INFO);
        handler.setFilter(record -> {
            handlerFilterChecks.incrementAndGet();
            return !record.getMessage().startsWith("NOISE ");
        });
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                formatCalls.incrementAndGet();
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            logger.fine("detail skipped");
            logger.info("PRIVATE internal event");
            logger.info("NOISE heartbeat");
            logger.info("accepted order=42");
            logger.warning("retry scheduled");

            System.out.println(
                    "loggerFilterChecks=" + loggerFilterChecks.get());
            System.out.println(
                    "handlerPublishCalls=" + handlerPublishCalls.get());
            System.out.println(
                    "handlerFilterChecks=" + handlerFilterChecks.get());
            System.out.println("formatCalls=" + formatCalls.get());
        } finally {
            logger.removeHandler(handler);
            logger.setFilter(null);
            handler.close();
        }
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac FilterBeforeFormatDemo.java
java FilterBeforeFormatDemo
~~~

**Exact stdout in the single-threaded example:**

~~~text
INFO: accepted order=42
WARNING: retry scheduled
loggerFilterChecks=5
handlerPublishCalls=4
handlerFilterChecks=3
formatCalls=2
~~~

There is no stderr because the example uses a custom `Handler` that prints to `System.out`, rather than JUL's default `ConsoleHandler`.

**Explanation of each counter:**

| Log event | Logger filter | Handler `publish` | Handler filter | Formatter |
| --- | --- | --- | --- | --- |
| `FINE detail skipped` | Yes, accepted | Yes | No, blocked at handler level `INFO` | No |
| `INFO PRIVATE internal event` | Yes, rejected | No | No | No |
| `INFO NOISE heartbeat` | Yes, accepted | Yes | Yes, rejected | No |
| `INFO accepted order=42` | Yes, accepted | Yes | Yes, accepted | Yes |
| `WARNING retry scheduled` | Yes, accepted | Yes | Yes, accepted | Yes |

Therefore, there are **5** logger filter executions, **4** entries into `Handler.publish`, **3** handler filter executions, and only **2** `Formatter.format` executions. The formatting step only occurs after the event passes the handler's conditions.

**Why not just count log lines?** The line count is the final result; the counters show **at which step an event was dropped**. This is especially useful when investigating missing logs caused by levels, filters, or appenders.

**Limitations of the example:** this is a custom handler written to demonstrate the exact ordering. Another handler/appender may have different internal mechanisms, buffering, or formatters. `AtomicInteger` keeps the counters thread-safe if extended to multiple threads, though the program currently runs on a single thread so stdout ordering is deterministic.

## 4. How Do Logger Filters and Handler Filters Differ?

Consider a logger `com.example.order` with two output destinations:

~~~text
                Logger com.example.order
                          |
                  Logger Filter
                          |
               +----------+----------+
               |                     |
           ConsoleHandler         FileHandler
           level=INFO             level=FINE
           filter=...             filter=...
               |                     |
          Formatter A             Formatter B
               |                     |
            stdout                 file
~~~

An event rejected by the **logger filter** does not proceed to those handlers. An event that passes the logger filter may be written to the file but not appear on the console if each handler has a different level/filter.

Example in JUL:

~~~java
// Illustration snippet where a Logger and two Handlers already exist.
logger.setFilter(record -> record.getLevel().intValue()
        >= Level.INFO.intValue());

consoleHandler.setFilter(record -> !"healthcheck"
        .equals(record.getLoggerName()));
~~~

The snippet above is integration code, not a standalone program. Note that `record.getLoggerName()` is the **logger name**, not the message content; if you want to exclude healthcheck messages, use the appropriate criterion (such as a structured field or raw message) instead of mistakenly comparing against the logger name.

Not every filter should be placed on the logger. If you want to **exclude an event across all destinations**, a logger filter is the right place in the JUL model. If you only want to **reduce noise at a single destination**, a handler filter is usually more appropriate. However, frameworks like Logback and Log4j 2 organize filters, additivity, and appenders differently; always check their specific mechanisms rather than inferring directly from JUL's structure.

## 5. "Before Format" Does Not Mean All String Creation Is Deferred

Look at the following code:

~~~java
logger.fine("payload=" + expensiveToString());
~~~

Java evaluates method arguments **before calling** `logger.fine`. Thus `expensiveToString()` can already run even when the logger is at `INFO` and the `FINE` log is guaranteed to be dropped. The benefit of filtering before **`Formatter.format`** does not refund costs already incurred in application code.

With JUL, you can use the overload that takes a `Supplier<String>` to **defer message creation when the log level is not enabled**:

~~~java
logger.log(Level.FINE, () -> "payload=" + expensiveToString());
~~~

This is an illustrative snippet inside a method that already has `logger` and `expensiveToString()`; it is not a standalone program. With this call, if the logger does not have `FINE` enabled, the supplier does not need to be invoked to build the message. **Do not assume that the supplier will always remain unevaluated before every custom filter**: that ordering depends on the API and implementation. Once the level is enabled, the supplier may be executed even if a downstream filter still rejects the event.

If you also want to avoid preparing expensive arguments when the log level is disabled, you can guard at the call site:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("payload=" + expensiveToString());
}
~~~

Checking `isLoggable` helps reduce unnecessary overhead when the log level is off, but it does not replace backend filters. If the level configuration can change concurrently between the check and the write, treat this as a standard optimization rather than a synchronization mechanism or an invariant check.

In **SLF4J**, the common approach is to pass arguments via placeholders:

~~~java
// Integration snippet: requires SLF4J and a backend.
logger.debug("orderId={} status={}", orderId, status);
~~~

This avoids **direct string concatenation/formatting** before the call as in `"..." + value`, and the backend can defer formatting when logging is disabled. However, any Java argument expression such as `expensiveCall()` in `logger.debug("x={}", expensiveCall())` **still runs before** the logger is called. If the computation is truly expensive, consider an `isDebugEnabled()` guard or the lazy parameter mechanism of the API/backend in use (such as the fluent `Supplier` in SLF4J 2.x).

## 6. How Logging Backends Apply Filters Before Layout/Encoder

### 6.1. Java Util Logging (JUL)

- `Logger.isLoggable(Level)` checks the logger's effective level.
- `Logger.setFilter(Filter)` sets a filter that can reject a `LogRecord` on the source logger's processing path.
- `Handler.setLevel(Level)` and `Handler.setFilter(Filter)` set conditions specific to the output destination.
- `Handler.isLoggable(LogRecord)` is the step a custom handler should call **before `getFormatter().format(record)`**.
- `Formatter.formatMessage(record)` can process resource bundles and parameters when the formatter actually runs; if a filter triggers message formatting, that cost can appear earlier.

With standard handlers, do not confuse the **parent logger's level** with the **level of a handler attached to the parent**. Once a child logger has created an event and forwarded it to a parent's handler, that handler applies its own level/filter; the parent logger's level does not necessarily block the event a second time.

### 6.2. Logback with SLF4J

Logback Classic has **TurboFilter**: this is an early filtering mechanism in the logger processing path that can return `DENY`, `NEUTRAL`, or `ACCEPT` according to Logback's contract. Standard filters on an **Appender** decide whether an event is emitted at that appender, before the encoder/layout is called in the typical appender workflow.

Distinguish between:

- **Early TurboFilter:** can decide quickly based on level, marker, logger name, or provided arguments, before some event-creation work.
- **Appender filter:** already has an event and decides whether an appender processes it.
- **Layout/encoder:** converts an accepted event into strings/bytes to write to the destination.

In Logback, a filter can actively request the formatted message or other data, so not every filter avoids all formatting work. Logger/root level configuration and appender filters must still be inspected together.

### 6.3. Log4j 2

Log4j 2 supports filters at multiple positions such as context, logger, appender reference, or appender, depending on configuration. A filter can discard an event before the layout converts it to strings/bytes, but **the actual cost depends on the filter type and the message**. For example, a metadata-based filter can be cheaper than a filter using a regular expression on the **formatted message**: the latter can trigger formatting in order to match, even if the event is ultimately not written.

If using async logging, distinguish **when the acceptance decision is made**, **when formatting occurs**, **when output is written**, and **when flushing occurs**. You cannot assume all steps happen on the same thread or at the same time. Do not apply JUL's internal diagram as a detailed specification for Logback or Log4j 2.

## 7. How to Design Low-Cost Filters

When choosing filter conditions, prefer readily available, cheap data:

| Condition | Example | Notes |
| --- | --- | --- |
| Log level | Accept `INFO` and above only | Usually a very cheap check |
| Logger/package name | Drop debug logs from a package | Suitable when inspecting message content is unnecessary |
| Marker or structured attribute | Send only `AUDIT` events to a separate appender | Depends on API/backend |
| Available context info | Select environment or task type | Consider MDC/context lookup cost |
| Formatted message string | Regex/substring on final message | Can trigger formatting early, costing CPU/memory |
| Network call / DB read in filter | Look up permissions or policies from another service | Avoid on the hot path due to latency and cascading failure risk |

**Best practices:**

1. Filter by **level** early, then by simple metadata conditions. Only parse messages when truly necessary.
2. Consider **per-destination filtering** when console, file, and collection systems have different policies.
3. Avoid large string concatenations, JSON serialization, reading stack traces, or expensive `toString()` calls **before** knowing the log is likely enabled.
4. For custom handlers/appenders, check `isLoggable` or the equivalent before calling the formatter, encoder, network, or disk I/O.
5. Do not use filters with business side effects. A filter may be called multiple times, across multiple threads, or in different configurations; it should be fast and predictable.
6. Measure **event creation rate, dropped event count, format count, and I/O cost** before optimizing. Measuring only the `logger.info` call time can miss downstream async work.

**Security caution:** dropping events with a filter is no substitute for **redaction/masking at the source**. If a message already contains tokens or sensitive data, blocking it at one appender with a filter does not guarantee the information has not passed through other steps or other destinations. Ensure sensitive data is not logged in the first place, or use appropriate masking before output.

## 8. Common Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `formatCalls` still increases even when logs are dropped | Formatter is called before filter, or filter retrieves the formatted message itself | Check call order in custom handler/filter |
| An event is missing from console but appears in file | Handler/appender has its own level or filter | Check each output destination, not just logger level |
| `FINE` is missing even though logger is set to `ALL` | Handler only accepts `INFO` and above | Check both handler level and filter |
| CPU remains high when `DEBUG` level is off | Code performs string concatenation/`toString()` or serialization before calling logger | Use placeholders, suppliers, or level guards where appropriate |
| Prefix-based filter does not work as expected | `record.getMessage()` is the raw/template message, not necessarily the final string after `formatMessage` | Choose the appropriate field or backend filter mechanism |
| Duplicate log entries | Multiple handlers and inheritance/additivity | Check parent logger handlers and appender references |
| Filtered out on one destination but still appears on another | Filter policy is only applied to one appender | Place the rule in the right location or on each destination to control |
| Filter optimization drops logs needed for investigation | Condition is too broad or sampling is too aggressive | Test error scenarios and observe retained event ratio |
| Async queue full or logs arrive late | Backpressure, discard, buffering, flush/shutdown | Check backend queue and exporter configuration |

## 9. Verification Exercise

Try modifying **one condition** in `FilterBeforeFormatDemo.java` and running it again:

1. Change `handler.setLevel(Level.INFO)` to `handler.setLevel(Level.ALL)`: the `FINE detail skipped` event will pass through the handler filter and formatter. Then `handlerFilterChecks=4`, `formatCalls=3`; the logger counter remains 5 and publish remains 4.
2. Keep the handler at `INFO`, and change `startsWith("NOISE ")` to `startsWith("UNUSED ")`: the heartbeat event is no longer dropped; `formatCalls=3`, `handlerFilterChecks=3`.
3. Try moving the `getFormatter().format(record)` call **before** `isLoggable(record)` (only in a test copy of the demo): the format counter will increment even for events rejected by the handler. This is an example of an undesirable implementation; restore the original order after observing.
4. Try attaching another handler with a different level/filter: an event can produce output on one handler while being blocked on the other. Remember to remove the test handler afterward to avoid duplicate output or holding resources.

**Self-check question:** Logger level `ALL`, handler level `WARNING`, expensive formatter. Will an `INFO` event necessarily be formatted? **No**, if the handler checks the level/filter before the formatter as implemented in the example. However, if the code already called `"value=" + expensiveToString()` to pass into `LOGGER.info`, the cost of `expensiveToString()` is still incurred.

**Key takeaway:** Early filtering only saves steps that **have not happened yet**. In Java logging, distinguish between level filtering, logger filters, handler/appender filters, and formatters/encoders. Place cheap conditions before expensive formatting, avoid building messages eagerly at the caller, and verify the ordering by counting rather than just looking at log line counts.