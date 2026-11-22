# Message-Based Filtering in Java Logging

## 1. What Problem Does "Message-Based Filtering" Solve?

In a Java application, not every message that passes the log level threshold (`INFO`, `WARN`, `ERROR`, etc.) needs to be written to every destination. For example, a service might produce thousands of `GET /actuator/health 200` logs per minute; they are useful when diagnosing probes, but can obscure business events during normal operation. **Message filtering** inspects the *message content* of a log event and decides whether to let the event proceed to the logger, appender, handler, or pipeline.

A practical requirement:

- Exclude **INFO** lines containing the pattern `GET /actuator/health` from the console.
- **Keep WARN/ERROR**, even when the message contains the same string, because a failed health check is operationally significant.
- Continue storing INFO events in an investigation log file if policy requires it.
- Do not filter out other business messages simply because they happen to contain the word "health".

For example:

| Emitted Event | Desired Console | Desired Application File | Why |
| --- | --- | --- | --- |
| `INFO GET /actuator/health 200` | Drop | Keep if needed | Successful probes create high noise |
| `INFO order=42 created` | Keep | Keep | Business event |
| `WARN GET /actuator/health 503` | Keep | Keep | Failed probe is an important signal |
| `ERROR payment timeout` | Keep | Keep | Business errors must not be dropped |
| `DEBUG GET /actuator/health 200` | Depends on logger level | Depends on logger level | DEBUG events may be excluded before the message filter step |

Message-based filters should be used when decisions genuinely need to rely on text. For structured data and stable events, it is usually better to filter by **event code, logger name, Marker, MDC/ThreadContext, or structured attributes**; these are less dependent on exact wording.

## 2. Distinguishing Logger Level from Message Filter

A simplified processing flow:

```text
logger.info("GET /actuator/health {}", status)
                  │
                  ▼
        Does level/logger enable INFO?
             │ No → stop
             │ Yes
             ▼
       Create logging event
             │
             ▼
      Filter (logger or appender)
             │
      ┌──────┼────────────┐
      ▼      ▼            ▼
    DENY   NEUTRAL       ACCEPT
    drop  continue/    accept within
           default       filter scope
            rules
             │
             ▼
     Layout/Encoder → sink
```

Actual filter placement varies by framework. For instance, Logback has `TurboFilter` evaluated early in the logging context and regular `Filter<ILoggingEvent>` attached to an appender after the logging event is created; Log4j 2 allows placing filters at multiple levels, including context, logger, appender, and appender-reference; JUL has `Filter` on `Logger` or `Handler`.

It is important to distinguish:

1. **Level filter** evaluates severity: `INFO`, `WARN`, `ERROR`, etc.
2. **Message filter** evaluates content: starts with, contains substring, regex match, or a custom predicate.
3. **Routing** determines which destination receives the event: console, file, remote appender, etc.
4. **Formatting** decides how the final line is rendered: message pattern, arguments, timestamp, exception, MDC, JSON, etc.

If the logger has already blocked `DEBUG`, a message filter on an appender **cannot recover** that DEBUG event. Similarly, filtering on a console appender does not necessarily exclude the event from a file appender. Avoid describing a message filter as a way to "change the log level"; it is a decision rule evaluated on an event or its message.

## 3. Raw Message and Formatted Message Are Two Different Things

Many logging APIs support message templates and arguments:

```java
logger.info("GET /actuator/health status={}", statusCode); // SLF4J
```

In this case:

- **Raw message/template** is `GET /actuator/health status={}`.
- **Formatted message** might be `GET /actuator/health status=200`.
- The final output written by the layout may also include a timestamp, level, logger name, MDC, and exception.

With JUL:

```java
logger.log(Level.INFO, "Order {0} created", 42);
```

`LogRecord.getMessage()` returns `Order {0} created`; `Formatter.formatMessage(record)` is what performs the placeholder substitution (`MessageFormat`) to produce `Order 42 created`. Therefore:

- Filters comparing stable templates are usually cheap and independent of argument values.
- Filters that must find `status=500` in the complete text need to inspect the **formatted message** or, better yet, inspect a structured status field.
- Searching for `"500"` on the raw message can miss events because that number only exists in the arguments.
- Searching on the *output line* can run into prefixes, exceptions, escaping, and varying patterns; you cannot assume a message filter sees the entire formatted text line written to a file.

**Be explicit about which level you are filtering at:** template, formatted message, or log record with attributes. Rules based on final rendered text tend to be brittle when an application changes language, format, or logging backend.

## 4. Common Matching Types

| Type | Condition Example | Suitable For | Limitations |
| --- | --- | --- | --- |
| Exact equality | `message.equals("GET /health 200")` | Strictly controlled event text | Any change in arguments or whitespace breaks it |
| Prefix | `message.startsWith("HEALTH_CHECK")` | Fixed prefixes | May collide with unrelated messages |
| Substring | `message.contains("GET /actuator/health")` | Easily identifiable noise | Any message containing the substring is affected |
| Regex | `Pattern.compile("^GET /health status=2\\d\\d$")` | Patterns with positional rules or variations | CPU-intensive and prone to false matches if overly broad |
| Combined predicate | `level < WARN && message.contains(...)` | Preserving important logs conditionally | Logic needs multi-dimensional testing |
| Structured field | `eventType == HEALTH_PROBE && status < 500` | Events with a stable schema | Requires consistent metadata in code |

A regex is not automatically better than `contains()`. If you only need to check a literal, `contains()` is clearer and typically cheaper. If you need to avoid matching `GET /healthz` when looking for `GET /health`, you can use appropriate anchors or word boundaries, but you must test thoroughly against slashes, spaces, Unicode, and escape characters.

Example in Java:

```java
import java.util.regex.Pattern;

Pattern pattern = Pattern.compile(
        "^GET /actuator/health status=2\\d{2}$");
boolean probeOk = pattern.matcher(message).matches();
```

`matches()` requires the **entire** string to match the regex; `find()` only requires **a substring** to match. These two APIs cannot be swapped while preserving the same meaning. A `Pattern` should be **compiled once** and reused, not recompiled per event under high traffic.

### 4.1. Prioritizing Error Logs

A safe rule for the health probe example:

```text
IF level >= WARN:
    keep event
ELSE IF message contains "GET /actuator/health":
    drop event
ELSE:
    keep event
```

Putting the level check first ensures you **do not accidentally swallow warnings or errors** when the health path appears in a message. In real systems, align on framework level semantics (Logback/Log4j 2 have WARN/ERROR; JUL uses WARNING/SEVERE) rather than comparing level names alphabetically.

## 5. Standalone Java 17+ Example: java.util.logging.Filter

The JDK includes `java.util.logging.Filter` with the method `boolean isLoggable(LogRecord record)`. When attached to a `Handler`, it decides whether a record is written by that handler. This example **does not require SLF4J or any external framework**.

Save as `MessageFilterDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Filter;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageFilterDemo {
    private static final class OneLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.message.filter");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new OneLineFormatter());

        Filter keepImportantLogs = record -> {
            if (record.getLevel().intValue()
                    >= Level.WARNING.intValue()) {
                return true;
            }
            String rawMessage = record.getMessage();
            return rawMessage == null
                    || !rawMessage.startsWith("[HEALTH]");
        };
        console.setFilter(keepImportantLogs);
        logger.addHandler(console);

        try {
            logger.info("[HEALTH] GET /health -> 200");
            logger.info("order=42 created");
            logger.warning("[HEALTH] GET /health -> 503");
            logger.severe("payment gateway timeout");
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac --release 17 MessageFilterDemo.java
java MessageFilterDemo
```

JUL's `ConsoleHandler` writes to **stderr** by default. Therefore, stdout of the Java command is **empty**; stderr contains exactly:

```text
INFO order=42 created
WARNING [HEALTH] GET /health -> 503
SEVERE payment gateway timeout
```

If the terminal merges stdout and stderr, you will still see the three lines above. The program deliberately uses a dedicated logger, `setUseParentHandlers(false)`, and a consistent formatter so parent handlers do not produce extra lines or different timestamps. `close()` closes the handler after use; if a filter is placed on a shared logger, the filtering scope will differ.

Result explanation:

1. `INFO [HEALTH] ... 200` is dropped because the raw message starts with `[HEALTH]` and the level is below WARNING.
2. `INFO order=42 created` is still written.
3. `WARNING [HEALTH] ... 503` is kept because the WARNING check precedes the prefix check.
4. `SEVERE payment gateway timeout` is kept.

The example inspects the raw message to avoid formatting before filtering. If the problem requires filtering on **rendered argument values**, use a dedicated attribute or a parameter-aware custom formatter/predicate.

### 5.1. Difference When Attaching the Filter to Logger

Using the same predicate, but with:

```java
logger.setFilter(keepImportantLogs);
```

When a filter is attached to a logger, it blocks records at the logger source; all handlers receiving events from this logger are affected. When the filter is only on `console.setFilter(...)`, another file handler can still receive events dropped by the console. In JUL, both logger and handler filters combine with level checks; returning `true` from a filter **does not override** a disabled level.

If you add a separate `FileHandler`, you must configure its `Formatter`, `level`, and `Filter` accordingly. Avoid attaching the same logic at both the logger level and handler level, which makes it hard to explain why logs disappear across multiple destinations.

### 5.2. JUL and Parameterized Messages

The following snippet illustrates the difference between raw text and formatted text:

```java
logger.log(Level.INFO, "Order {0} created", 42);
```

Inside the filter, `record.getMessage()` is `Order {0} created`, not `Order 42 created`. Inside `OneLineFormatter`, `formatMessage(record)` outputs `Order 42 created`. Consequently, if the filter uses `getMessage().contains("42")`, the result will not behave as intended. If you must make decisions based on an order ID, consider keeping that ID as separate structured data; filtering on templates and rendered numbers is often hard to maintain.

## 6. Logback: Custom Filter on ILoggingEvent Message

In Java applications using **SLF4J + Logback**, a regular filter can be attached directly to an appender. To exclude INFO probe lines while keeping WARN/ERROR, write an explicit filter class. The example uses Logback Classic compatible with the `ch.qos.logback.classic.spi.ILoggingEvent` API.

File `src/main/java/com/example/logging/HealthMessageFilter.java`:

```java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public final class HealthMessageFilter extends Filter<ILoggingEvent> {
    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event == null) {
            return FilterReply.NEUTRAL;
        }
        if (event.getLevel().toInt() >= Level.WARN_INT) {
            return FilterReply.NEUTRAL;
        }
        String message = event.getFormattedMessage();
        if (message != null
                && message.contains("GET /actuator/health")) {
            return FilterReply.DENY;
        }
        return FilterReply.NEUTRAL;
    }
}
```

This is a **class for a project that already has the Logback Classic dependency**; it cannot be compiled standalone with only the JDK. `getFormattedMessage()` retrieves the message after SLF4J placeholder substitution. `FilterReply.DENY` blocks the event at this appender; `NEUTRAL` delegates to remaining filters or default handling. Because the logger level is checked separately, `NEUTRAL` does not "enable" DEBUG if the logger does not enable DEBUG.

Attach the filter to the console in Spring Boot's `src/main/resources/logback-spring.xml` (or the application's corresponding Logback configuration):

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.HealthMessageFilter"/>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

**Expected result:** the console does not print INFO messages containing `GET /actuator/health`; the file still writes them because it does not have that filter. WARN/ERROR events reach both console and file if they pass the logger level. The path `logs/application.log` depends on the working directory and write permissions; this simple file appender example **does not configure rolling or retention**, so it should not be used as-is for long-running systems with high log volume.

If you want to drop INFO probes from **both** console and file, you can attach an appropriate filter to both appenders or use a logging-context-level filter mechanism after clearly defining the scope. Do not add a filter to a single appender and conclude that the event has disappeared from the entire application.

### 6.1. "Raw" and "Formatted" in Logback

`ILoggingEvent.getMessage()` returns the template before placeholder substitution; `ILoggingEvent.getFormattedMessage()` returns the message after formatting. With:

```java
log.info("GET /actuator/health status={}", statusCode);
```

- `getMessage()`: `GET /actuator/health status={}`.
- `getFormattedMessage()`: `GET /actuator/health status=200` if `statusCode=200`.

Use `getMessage()` if the policy identifies a **fixed template** and you want to avoid parameter rendering overhead. Use `getFormattedMessage()` when you must inspect the substituted content, but measure overhead and be careful with object `toString()` implementations. Avoid passing expensive objects into log calls only to filter and drop the event afterward.

### 6.2. About EvaluatorFilter and Legacy Janino Configuration

In Logback, `EvaluatorFilter` can use a dedicated `EventEvaluator`; however, some older tutorials use `JaninoEventEvaluator` with expressions embedded in XML. **According to Logback documentation, `JaninoEvaluator` was removed in version 1.5.13 for security reasons**. For modern versions, use a custom `Filter<ILoggingEvent>` as shown above or write a dedicated Java `EventEvaluator`, avoiding old Janino snippets that may no longer work.

### 6.3. Why You Should Not Return ACCEPT for Every Non-Matching Message

In Logback, `ACCEPT` skips the remaining filters in the same chain; `NEUTRAL` allows evaluation to continue. If a message filter returns `ACCEPT` for every non-matching event, a subsequent filter for sensitive data or another policy might be bypassed. Therefore, the custom filter above returns `DENY` when the exclusion condition matches, and `NEUTRAL` otherwise.

When using multiple filters, state the precedence rules explicitly: for example, a sensitive-data protection filter must not be bypassed just because an earlier message filter returned ACCEPT.

## 7. Log4j 2: StringMatchFilter and RegexFilter

Log4j 2 provides XML-configurable filters. According to current Log4j 2 documentation:

- `StringMatchFilter` matches if the **formatted message contains the specified text string**.
- `RegexFilter` uses a regular expression and **must match the entire message**; to search for a substring, include `.*` or an expression covering the rest of the text.
- `RegexFilter useRawMsg="false"` is the default, evaluating the formatted message; `useRawMsg="true"` evaluates the raw message for supported `Message` types.
- Both filters support `onMatch` and `onMismatch`, and can impact performance when they must format a message just to decide to drop it.

### 7.1. Using StringMatchFilter While Keeping WARN/ERROR

Example for an application that already uses **Log4j 2 Core** as its backend, file `src/main/resources/log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <Filters>
                <ThresholdFilter level="WARN"
                    onMatch="ACCEPT" onMismatch="NEUTRAL"/>
                <StringMatchFilter
                    text="GET /actuator/health"
                    onMatch="DENY" onMismatch="NEUTRAL"/>
            </Filters>
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>

        <File name="FILE" fileName="logs/application.log"
              append="true">
            <PatternLayout
                pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

For the console:
1. `ThresholdFilter` returns `ACCEPT` for `WARN`/`ERROR`, stopping the console appender's filter chain so important events are kept.
2. Events below WARN continue (`NEUTRAL`) to `StringMatchFilter`; if they contain `GET /actuator/health`, they are `DENY`ed, while others proceed normally.
3. The file appender has no message filter, so it receives all events enabled at the root logger.

Here, using `ACCEPT` is intentional to **prioritize WARN/ERROR over the probe-exclusion filter**; review any additional filters if you add more later. This example only illustrates message filtering and **does not include rotation, retention, or production file management**. With Spring Boot, ensure the classpath has only one compatible SLF4J backend/provider and that the application actually loads the Log4j 2 configuration.

### 7.2. When Regex Is Needed Instead of Substring

You can replace `StringMatchFilter` alone in the example with:

```xml
<RegexFilter
    regex=".*GET /actuator/health.*"
    useRawMsg="false"
    onMatch="DENY"
    onMismatch="NEUTRAL"/>
```

The leading and trailing `.*` are necessary because Log4j 2's `RegexFilter` matches the **entire message**, rather than automatically searching for a substring like `String.contains`. If the regex is `GET /actuator/health`, a message `INFO GET /actuator/health 200` will typically **not match the whole string**.

A stricter regex can accurately identify records with structured prefixes, but you should write tests against real messages instead of broadening patterns with `.*` indiscriminately. `useRawMsg="false"` incurs formatting cost; `true` can cause the regex to miss values that only appear in arguments. This choice is both a semantic and a performance decision, not merely a syntax option.

### 7.3. Filter on Appender, Logger, or AppenderRef?

Log4j 2 allows placing filters at the **context, logger, appender, or appender reference** level. A filter on the console appender affects events flowing through that console appender; a filter on an `AppenderRef` affects that specific reference path; a filter on a logger has broader scope before routing to destinations. Placing the same condition on both a logger and an appender can drop events from the file even if you only intended to clean up the console.

In particular, setting `onMismatch="DENY"` on a "deny only when matched" filter can have the opposite effect: **every non-matching message** is also dropped. When the goal is only to remove noise, choose `onMatch="DENY" onMismatch="NEUTRAL"`.

## 8. Filtering Before or After the Asynchronous Logging Queue?

When a filter is applied determines its cost. With an async appender:

```text
Caller thread
     │
     ├─ message filter before queue ──(kept)──> [Async Queue] -> Sink
     │                                       │
     └─(dropped) not enqueued                └─ Filter at sink after queue?
```

If the filter is attached **to `AsyncAppender`** and runs when receiving events, logs are dropped before enqueuing, reducing the number of items in the queue. If filtering only happens at the **destination appender behind the queue**, events may already occupy queue slots, consuming memory as well as dequeue and formatting time before being discarded. Verify the exact appender structure in use; do not assume all logging frameworks apply filters before queuing.

Logback example where `ASYNC_FILE` wraps an already-defined `FILE` appender:

```xml
<appender name="ASYNC_FILE"
          class="ch.qos.logback.classic.AsyncAppender">
    <filter class="com.example.logging.HealthMessageFilter"/>
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

If the goal is to exclude probes from the file, the filter on `ASYNC_FILE` processes events before they are placed into its queue; the root logger should reference `ASYNC_FILE` rather than referencing both `ASYNC_FILE` and `FILE` directly. This is a **configuration snippet added to a setup that already declares `FILE`**, not a complete standalone XML file.

- `queueSize` is measured in events, not bytes.
- `discardingThreshold=0` disables Logback `AsyncAppender`'s early-discard policy for lower-level logs, but does not guarantee zero loss.
- `neverBlock=false` allows producers to wait when the queue is full; changing it to `true` can drop events.
- A failing async queue or premature shutdown can still lose logs, which is **different from** intentionally dropping events based on a message policy.

Do not use message filters to hide log volume impact without measuring: you may need to reduce logging at the source, lower levels selectively, throttle/rate-limit, or configure health access logging separately.

## 9. Performance Cost of Content-Based Filtering

**Performance characteristics depend on where filtering happens and how messages are constructed**:

1. **Level check first:** when `DEBUG` is disabled, event creation and message inspection are avoided (depending on the framework). This is usually the cheapest guard.
2. **Raw/template message:** literal checks can avoid argument formatting and expensive `toString()` calls.
3. **Formatted message:** sometimes requires building the full `String` even if it is later `DENY`ed; this cost still occurs on the calling thread if the filter runs there.
4. **Regex:** compile patterns once, and avoid expressions with excessive backtracking when messages come from untrusted input. Test long worst-case inputs.
5. **I/O only after the filter allows:** dropping early reduces pressure on appenders, disk, network, and backend quotas; dropping too late only reduces final bytes written and may not reduce queue pressure.
6. **Async:** higher peak throughput can build up larger backlogs if the sink is slow; placing filters properly is part of optimization, but you also need to review the queue-full policy.

Never pass user-supplied regular expressions directly into a logger filter. Complex regexes can cause abnormal CPU spikes; log output can also contain externally controlled input. Starting with an explicit list of event codes is usually safer, more measurable, and easier to review.

An optimal filtering policy needs observability into the **filtered rate**. If millions of probe logs are dropped but production has no metrics for them, operators may not notice when probe behavior changes. You can track aggregate counters/metrics instead of keeping every INFO log.

## 10. Risks: Filtering Out Important Signals and Sensitive Data

Message filtering can lose data in subtle ways:

- **Overly broad substring:** dropping every line containing "timeout" can remove critical incident logs.
- **Language changes:** `"payment failed"` changing to `"thanh toán lỗi"` causes the filter to stop matching.
- **Template changes:** adding a prefix or placeholder breaks exact/prefix rules.
- **Changing formatted output:** object `toString()` or locale changes make the filter depend on dynamic content.
- **Exceptions/stack traces:** `getFormattedMessage()` is usually only the main message, **not the full final stack trace** printed by the encoder/layout. If you want to decide based on exception class, inspect the dedicated throwable property.
- **Log injection/newlines:** if a message contains client-supplied strings, an attacker can make logs look like multiple events. Substring filtering does not replace escaping or structured logging.
- **MDC context:** message-based filters do not automatically know `requestId`, `trace_id`, tenant, or user role unless you read metadata; do not mix sensitive identifying data into the message text just for filtering.

A fundamental rule: **filter to reduce noise, not to hide secrets**. If a message contains passwords, tokens, access keys, or personal data, avoid generating sensitive content in the first place, or apply redaction/masking across **every output path**, including console, file, OTLP, and fallbacks. Filtering only the file while the console still prints secrets leaves the system insecure.

For mandatory records such as audit and payment events, do not rely on whether a message contains a keyword. Use an event schema and a logging channel with explicit durability and retention requirements.

## 11. Testing a Message Filtering Policy

You should test **conditions and scope** using a matrix, beyond eyeballing a few sample logs:

| Case | Level | Message | Expected Console Result with Example Policy |
| --- | --- | --- | --- |
| Successful probe | INFO | `GET /actuator/health 200` | DENY |
| Failed probe | WARN | `GET /actuator/health 503` | Keep |
| Probe exception | ERROR | `GET /actuator/health timeout` | Keep |
| Normal business event | INFO | `order=42 created` | Keep |
| Message with similar word | INFO | `healthcheck cache warmed` | Keep if it does not match the exact string |
| Empty message | INFO | `""` or null where supported | Handle consistently, usually keep |
| Log from logger below threshold | DEBUG when logger is INFO | `GET /actuator/health` | Not created / does not reach appender |
| Parameterized message | INFO | template + argument containing path | Depends on whether raw or formatted was chosen |

Beyond the content matrix, you also need to:

1. **Test each appender**: ensure the console drops targeted events, the file keeps or drops them as designed, and nothing is duplicated.
2. **Test filter ordering**: verify `DENY`/`ACCEPT`/`NEUTRAL` are interpreted correctly in the chain and do not accidentally short-circuit other protections.
3. **Test WARN/ERROR**: ensure the filter does not block important logs sharing a keyword.
4. **Test template/parameters**: for `logger.info("status={}", status)`, test raw and formatted behavior against the chosen API.
5. **Test locale/encoding**: casing, Vietnamese/diacritics, Unicode, newlines, whitespace, slashes, and escaping.
6. **Test worst-case regex**: very long messages and unusual inputs do not cause dangerous latency spikes.
7. **Test throughput and load**: measure logs generated, filtered, and written to sinks; compare CPU and queue depth before and after.
8. **Test errors/incidents**: exceptions and audit logs still appear and are not dropped merely for sharing a keyword with noise.

When unit testing a custom Logback Filter, you can construct a test event with a level and message, call `decide(...)` directly, and assert `DENY` or `NEUTRAL`. Run separate integration tests with the appender/runtime configuration to confirm the XML is loaded and routing works, because correct Java logic does not guarantee production configuration actually attached the filter to the intended appender.

## 12. Choosing the Right Filtering Mechanism

Consider options in order from explicit to flexible:

1. **Adjust the log emission point or level** if the message is completely unhelpful. For example, emit probe logs at DEBUG; avoid creating millions of events only to discard them.
2. **Logger/package/Marker/event code** if you only want to filter a stably identified group of events.
3. **MDC/structured attributes** when decisions depend on request type, endpoint, status, or tenant; standardize the schema so the log pipeline handles it consistently.
4. **Substring/prefix/exact match** for stable messages with simple, tested rules.
5. **Regex/custom predicate** when handling complex variations where structured data is not yet available; measure overhead and protect error logs.
6. **Filter at the collector/backend** when raw logs are needed elsewhere but you want to reduce specific ingest/search streams; accept the incurred transmission/processing costs and each destination's data policy.

A well-designed message filter must clearly specify **which message is matched (raw or formatted), where the filter runs, which cases are prioritized to be kept, and how to detect excessive log dropping**. The right configuration reduces noise while leaving enough data for incident investigation.

## References

- [Logback manual – Filters, FilterReply, regular and turbo filters](https://logback.qos.ch/manual/filters.html).
- [Logback manual – Logging architecture, effective level and appender filters](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 – Filters: RegexFilter, StringMatchFilter, composition](https://logging.apache.org/log4j/2.x/manual/filters.html).
- [Oracle JDK 21 – java.util.logging.Filter](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Filter.html).
- [Oracle JDK 21 – LogRecord.getMessage and parameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/LogRecord.html).
- [Oracle JDK 21 – Formatter.formatMessage](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Formatter.html).