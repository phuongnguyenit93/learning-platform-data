# Core Terminology in Java Logging

When a Java application runs, **logging** is the practice of recording meaningful events so developers and operators can understand what happened. To read, configure, and analyze logs accurately, you need to distinguish between *events*, *records*, *loggers*, *levels*, *handlers*, and *log destinations*. Specific names vary across Java Util Logging (JUL), SLF4J, Logback, and Log4j 2, but the underlying roles remain similar.

## 1. How Does an Event Travel from Source Code to Log Storage?

```text
Application generates an event
  → calls logger via API
  → checks level and filters
  → creates/receives log record (log event)
  → handler/appender + formatter/layout/encoder
  → console, file, or log collection system
```

This is a **conceptual diagram**, not a mandatory processing order for every library. Some systems filter at multiple stages, write asynchronously, send logs over the network, or use buffering. A single logger call can also be routed to multiple destinations.

## 2. Terminology Used When Generating and Processing Logs

| Term | Meaning | Example or Distinction |
| --- | --- | --- |
| **Log / log entry** | Recorded information about an event. | `Order 42 accepted` is the message portion; a full entry may also contain a timestamp, level, and metadata. |
| **Logging** | The activity of generating, processing, and dispatching log entries. | Recording a service startup or an API call failure. |
| **Event** | Something that happened in the system and needs to be observed. | `order.accepted`, `connection.failed`. An event can be represented by a log record. |
| **Log record / log event** | A data object carrying event information for the logging system to process. | `java.util.logging.LogRecord` holds the level, logger name, message, parameters, timestamp, and other details. |
| **Message** | Human-readable content describing the event. | `Order 42 accepted`; the message alone is often insufficient to investigate an entire request. |
| **Message template / parameters** | A message pattern and the values bound to it at log time. | JUL: `"Order {0} accepted"` + `42`; placeholder syntax depends on the API. |
| **Logger** | The object/API entry point that application code uses to emit log events. | `Logger.getLogger("demo.orders")` in JUL. A logger is not synonymous with a log file. |
| **Logger name / category** | The identifier of the log source, usually tied to a package or component. | `com.example.orders.OrderService` helps filter by functional area. |
| **Log level / severity** | A label indicating the severity or purpose of an event. | JUL has `FINE`, `INFO`, `WARNING`, `SEVERE`; other APIs commonly have `DEBUG`, `INFO`, `WARN`, `ERROR`. |
| **Threshold / effective level** | The threshold that determines which events are processed. | An `INFO` threshold typically drops `FINE` events at the logger; a handler threshold acts as an additional filter. |
| **Filter** | A rule that allows or denies records, based on level or other conditions. | Blocking unnecessary events or selecting events for a dedicated destination. |
| **Handler / appender** | A component that receives records and writes/forwards them to an output; JUL calls it `Handler`, while Logback/Log4j 2 typically call it `Appender`. | `ConsoleHandler`, `FileHandler`, or an appender to a centralized system. |
| **Formatter / layout / encoder** | A component that converts an event into a display format or byte representation suitable for the destination. | Multi-line text, a timestamped pattern, or JSON with fields. |
| **Sink / destination** | The final log recipient along a processing branch. | Standard output, standard error, a file, or a log collector. |
| **Backend / implementation** | The part that executes filtering, formatting, routing, and log output. | Logback is a common backend when an application uses SLF4J. |
| **Facade / logging API** | A stable interface for business code to call logging, decoupled from how logs are output. | SLF4J is a facade; JUL provides both the API and handlers/implementations in the JDK. |
| **Configuration** | Settings for levels, handlers/appenders, formats, destinations, and related policies. | Setting package levels, configuring JSON output, or file rotation. |
| **Root logger / propagation** | The top-level logger and the mechanism by which records are forwarded through parent–child logger relationships if supported. | In JUL, parent handlers can receive logs from child loggers; misconfiguration easily causes duplicate logs. |

**Key distinction:** A logger is where application code *calls* logging; a handler/appender is where a record *is routed for output*; a formatter/layout determines what the record *looks like*; a sink is where the record *arrives*. The backend connects these roles according to configuration.

## 3. Terminology When Observing a Running Application

| Term | Meaning and Usage |
| --- | --- |
| **Timestamp** | The time an event was created/recorded. Centralized logs should have an explicit timezone (usually UTC); note that machine clocks can drift. |
| **Thread name / thread ID** | Indicates the thread emitting the log, useful when analyzing concurrency. A thread name does not replace a request identifier. |
| **Context / attributes / fields** | Structured data accompanying an event, such as `orderId`, `service`, `environment`. Field names should be consistent. |
| **Correlation ID / request ID** | An identifier that links logs belonging to the same request or processing flow. Generation strategy and scope depend on the application. |
| **Trace ID / span ID** | Distributed tracing identifiers: a trace connects related work; a span represents a single operation within a trace. Can be included in logs to correlate logs with traces. |
| **MDC / thread context** | A mechanism in *some frameworks* to attach context per thread or execution context. Not a standard MDC feature in `java.util.logging`; across executors/async threads, context may need to be propagated explicitly. |
| **Structured logging** | Recording events as typed/structured fields (usually JSON), enabling searches by `orderId` or `level` instead of only scanning raw strings. |
| **Exception / Throwable / stack trace** | A Java error and the call stack leading to it. Logging the `Throwable` itself preserves the stack trace; logging only `exception.getMessage()` often loses critical context. |
| **Centralized logging / collector** | Collecting logs from multiple processes/machines into a shared system for searching and correlating events. |
| **Rotation / retention** | Rotation swaps/closes log files by size or time; retention is the duration/policy for keeping data. These are two separate concerns. |
| **Sampling / rate limiting** | Selecting a subset of events or limiting frequency to reduce cost/load. Requires care because dropped events can affect investigations or audit requirements. |

An *illustrative* structured log record (not JUL's default output):

```json
{
  "timestamp": "2026-11-09T10:00:00Z",
  "level": "INFO",
  "logger": "demo.orders",
  "event": "order.accepted",
  "orderId": "42",
  "correlationId": "req-123"
}
```

JSON is a **data format**; it does not by itself guarantee accuracy, security, or queryability: the log ingestion system still has to collect and index the right fields. `correlationId`, `traceId`, and `spanId` serve different correlation purposes; they should not be used interchangeably.

## 4. Java 17 Example: Seeing Logger, Level, Handler, and Formatter in Action

JUL (`java.util.logging`) is built into the JDK, so the example below requires no external dependencies. Save it as **`LoggingVocabularyDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingVocabularyDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.orders");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        logger.log(Level.FINE, "Checking order {0}", 42);
        logger.log(Level.INFO, "Order {0} accepted", 42);
        logger.log(Level.WARNING, "Order {0} is delayed", 42);

        output.flush();
        logger.removeHandler(output);
    }
}
```

Compile and run:

```bash
javac LoggingVocabularyDemo.java
java LoggingVocabularyDemo
```

**Exact standard output** (excluding the command prompt):

```text
INFO | Order 42 accepted
WARNING | Order 42 is delayed
```

Explanation of each component:

1. `logger` is named `demo.orders`. `setUseParentHandlers(false)` avoids forwarding these records to parent logger handlers, preventing the example from printing duplicates under the default JUL configuration.
2. `logger.setLevel(Level.INFO)` blocks `FINE` before the record is passed to any handler. `output.setLevel(Level.ALL)` only states that the handler is willing to accept any level **that reaches the handler**; it cannot recover `FINE` events already blocked by the logger.
3. `StreamHandler` is the **handler**, receiving records and writing them to `System.out`. The anonymous `Formatter` is the **formatter**, building the `LEVEL | message` string from the `LogRecord`; `formatMessage(record)` substitutes `{0}` with `42`.
4. `flush()` pushes any buffered data to the output; buffering/flushing behavior is why you should not assume from a single logger call that data has immediately appeared at the destination.

The example intentionally creates a simple formatter because JUL's default format can include timestamps, class names, and configuration-dependent details. In real applications, handlers/appenders are typically configured once at startup rather than created on every business call.

### Inconsistent Placeholder Syntax Across APIs

- **JUL:** `logger.log(Level.INFO, "Order {0} accepted", orderId)`; an appropriate formatter can use `MessageFormat` to substitute `{0}`.
- **SLF4J:** `logger.info("Order {} accepted", orderId)`; `{}` follows SLF4J's convention.
- Do not copy placeholder syntax verbatim from one framework to another and expect the same result. Using parameters instead of arbitrary string concatenation also helps avoid expensive message construction before level checks, depending on the API and call site.

## 5. Common Misconceptions

**An event is not just a message.** A message `"Request failed"` lacks the data to identify which request failed. When appropriate, also log the event type, endpoint/operation, result code, and a controlled correlation ID.

**Levels do not reflect chronological order or message length.** `INFO` records normal progress, `WARNING` signals an anomaly that needs attention, and `SEVERE` indicates a serious error in JUL. Choose levels by operational meaning, and avoid logging everything at a single level.

**Logs are not metrics or traces.** Logs describe specific events; metrics aggregate values over time (error rates, latency); traces show the execution path and relationships between operations. They complement each other during incident investigation.

**Logging an exception message is not equivalent to logging the exception.** With JUL, when handling a `Throwable error`, you can call `logger.log(Level.SEVERE, "Operation failed", error)` to preserve the exception details and stack trace. Avoid redundantly logging the same exception at every processing layer.

**More logs are not automatically better.** Overly verbose logs cause noise and cost; too few logs hinder diagnosis. Strictly avoid putting passwords, access tokens, secrets, or unnecessary personal data into logs; also watch out for parameter values, URLs, and stack traces that may contain sensitive information. Configure appropriate rotation, retention, and access permissions.

## 6. How to Read a Log Record Methodically

When encountering a log line, answer in order: what **timestamp**, what **level**, which **logger/component** emitted it, what **event** occurred, what **context** identifies the request or entity involved, and if it is an error, where the **Throwable/stack trace** points. Then check the **handler/formatter/sink** to understand why an event is present or missing from the expected output.

Mastering this vocabulary helps you read logging documentation across many Java libraries without confusing the log-emitting code, filtering rules, record representation, and storage destination.