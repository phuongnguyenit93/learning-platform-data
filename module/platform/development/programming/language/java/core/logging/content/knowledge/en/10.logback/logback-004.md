# Logback Encoders: Converting Log Events into Output Data

## 1. What is an Encoder in Logback?

In a Java application using **SLF4J + Logback**, business code typically calls `logger.info(...)`, `logger.warn(...)`, or `logger.error(...)`. Such a call does not directly produce a complete line of text in a file. Logback needs to decide where the event is written and **which bytes represent that event**.

An **Encoder** is the component that transforms a logging event into **byte data that can be written to an output** (console, file, or an appropriate output stream). In Logback Classic, the input is typically an `ILoggingEvent`: an object containing the level, logger name, message, timestamp, thread, MDC, `Throwable`, and other information.

For example, the application emits:

```java
log.info("event=order.created order_id={}", "O-17");
```

When the application uses `PatternLayoutEncoder` with the pattern `%level|%logger{0}|%msg%n`, an output line might look like:

```text
INFO|OrderService|event=order.created order_id=O-17
```

Here:

- `%level` retrieves the log level.
- `%logger{0}` retrieves the shortest part of the logger name according to pattern rules.
- `%msg` retrieves the formatted message, including the value substituted for `{}`.
- `%n` appends the platform-appropriate newline character.

**The encoder does not decide whether a logger is written.** Levels, filters, and parent–child logger relationships determine which events reach an appender. The encoder handles **how** an accepted event is **represented**.

## 2. Where Does the Encoder Sit in the Log Pipeline?

A typical pipeline:

```text
Java code
  |
  | SLF4J: logger.info("order={}", orderId)
  v
Logger / log level / filter
  |
  v
ILoggingEvent
  |
  v
Appender (ConsoleAppender, FileAppender, RollingFileAppender...)
  |
  +---- Encoder (PatternLayoutEncoder / compatible JSON encoder)
  |           |
  |           v
  |       Formatted bytes
  |
  v
Console / file / output stream
  |
  v
Collector or analytics system (if any)
```

Distinguishing the roles:

| Component | Responsibility | Example |
| --- | --- | --- |
| `Logger` | Receives logging calls and determines source and effective level | `com.example.order.OrderService` |
| `ILoggingEvent` | Carries the information of a single log event | Level, message, arguments, Throwable, MDC |
| `Filter` | Accepts or rejects events based on rules | Forward only `WARN` and above |
| `Appender` | Manages the **destination** and output mechanism | `ConsoleAppender`, `FileAppender` |
| `Encoder` | Converts an event into **output bytes** | `PatternLayoutEncoder` |
| `Layout` | Produces a text representation from an event, often used by an encoder | `PatternLayout` |
| Collector | Collects, parses, stores, and routes outside the JVM | Agent reading container stdout |

In particular, **an appender is not an encoder**. Changing `ConsoleAppender` to `FileAppender` changes the destination, while the same encoder and pattern can still produce the same format. Changing the encoder changes the format without necessarily changing the destination.

An appender may provide its own encoding or output mechanism; the table above describes the common flow for output-stream-based appenders. Not every type of appender requires the same kind of encoder configuration.

## 3. How Does an Encoder Differ from a Layout?

In Logback, a `Layout` focuses on creating a **string** from an event; an `Encoder` converts an event into **bytes** suitable for writing to a stream. In Logback Classic, `PatternLayout` uses a pattern to produce text, while `PatternLayoutEncoder` is the standard way to use that pattern in a `ConsoleAppender` or `FileAppender`.

You can visualize it as:

```text
ILoggingEvent
    |
    v
PatternLayout: "INFO|OrderService|order=O-17\n"  (String)
    |
    v
PatternLayoutEncoder: encode as UTF-8              (byte[])
    |
    v
Appender: write bytes to stdout/file
```

`PatternLayoutEncoder` is the standard choice for formatting text using Logback conversion words. For most console/file logging needs, you do not need to build a custom `Layout` and wrap it with `LayoutWrappingEncoder`. When you do need to integrate a custom layout, `LayoutWrappingEncoder` can bridge a layout to a byte stream, though you must understand its initialization lifecycle and event types.

### Why not concatenate strings in business code?

For example, you should not scatter output formatting across services:

```java
log.info("[" + Thread.currentThread().getName()
        + "] [" + System.currentTimeMillis()
        + "] order=" + orderId);
```

This is an **illustrative snippet**, assuming `log` and `orderId` are already declared. That approach duplicates formatting logic, can incur cost even when the log level is disabled, makes switching to JSON difficult, and makes it hard to standardize timestamps and thread names. A better approach is:

```java
log.info("event=order.created order_id={}", orderId);
```

Let the encoder add the level, timestamp, logger name, and thread according to configuration. Business code should focus on **event semantics and context fields**, while the encoder decides **how they are rendered**.

## 4. PatternLayoutEncoder and Key Conversion Words

Configuration example:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Explanation of commonly used components:

| Conversion word | Meaning | Notes |
| --- | --- | --- |
| `%d{HH:mm:ss.SSS}` | Event timestamp in the chosen pattern | Lacks date/time zone if only time-of-day is used. |
| `%level` or `%p` | Log level | `INFO`, `WARN`, `ERROR`, etc. |
| `%-5level` | Left-aligns the level name in a minimum width of 5 characters | Makes text lines easier to read. |
| `%thread` | Thread name | Can vary across requests or runs. |
| `%logger` | Logger name | Can be the fully qualified class name. |
| `%logger{36}` | Abbreviates the logger name toward a target length | Not a unique ID to distinguish classes. |
| `%logger{0}` | Short representation, typically the last segment of the logger name | Useful for quick reading; may lose package info. |
| `%msg` or `%message` | Message with arguments substituted | Not equivalent to structured JSON fields. |
| `%ex` | Exception/stack trace info when the event has a Throwable | Check actual output and security implications. |
| `%X{trace_id}` | Value of `trace_id` from MDC if present | MDC must be propagated properly in the context. |
| `%n` | Platform-specific newline | Omitting `%n` can cause records to run together. |
| `%kvp` | Key-value pairs attached to the logging event in supported versions | Requires compatible backend/version configuration. |

**Patterns are parsed by Logback**, not by `String.format` or `java.text.MessageFormat`. The `{}` placeholders used by the application to pass arguments belong to **SLF4J parameter substitution**; the `%msg` token is where the encoder retrieves the **already formatted message** from the event.

Example:

```java
log.warn("event=payment.retry attempt={}", 2);
```

This same event can be rendered differently:

```text
WARN|event=payment.retry attempt=2
14:22:03.112 WARN [main] com.example.PaymentService - event=payment.retry attempt=2
```

The two lines above are **illustrations of two different patterns**, not exact output from a single run; actual timestamps and threads are provided by the runtime. The business content is identical, while the representation is decided by the encoder.

### Time representation must match the goal

Short time patterns like `HH:mm:ss.SSS` are convenient in a terminal, but lack dates and time zones when searching across multiple systems. Production environments should use full timestamps with explicit offsets/time zones, or let the collection system record a canonical timestamp field. You must distinguish between **when the event occurred** and **when the collector received it**.

### `%logger{0}` and `%logger{36}` behave differently

`%logger{0}` is typically used to extract the last segment of the logger name; `%logger{36}` attempts to abbreviate the full name toward a target length according to `PatternLayout` rules. Neither conversion should be treated as an absolute source identifier. In centralized log analysis, keep the full logger name in structured data if exact source tracing is required.

## 5. Runnable Java 17 + Maven Example

This example uses `SLF4J 2.x` with `Logback Classic 1.5.x`. We configure a `ConsoleAppender` with a `PatternLayoutEncoder`, execute three logging calls, and verify the predictable output.

Project structure:

```text
logback-encoder-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── edu/
        │       └── example/
        │           └── logging/
        │               └── EncoderDemo.java
        └── resources/
            └── logback.xml
```

### Step 1: Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.example</groupId>
    <artifactId>logback-encoder-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` brings in related dependencies such as `logback-core` and a compatible SLF4J API; there is no need to add another logging mechanism for this sample. In larger projects, manage SLF4J and Logback versions together to avoid provider/binding conflicts. The versions in `pom.xml` are simply **a specific illustrative set of versions**, not a claim about the latest release.

### Step 2: Create `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Explanation:

1. `ConsoleAppender` writes data to the console (stdout by default in this configuration).
2. `PatternLayoutEncoder` determines how each event becomes a line of bytes according to the pattern.
3. `%level|%logger{0}|%msg%n` produces readable output without a timestamp so the example stays deterministic.
4. `charset=UTF-8` ensures consistent encoding for Vietnamese and other Unicode characters when needed.
5. `root level="INFO"` allows `INFO`, `WARN`, and `ERROR` events through.
6. Attaching only one appender to root and not attaching the same appender to child loggers avoids duplicate output from this configuration.

### Step 3: Create `EncoderDemo.java`

```java
package edu.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class EncoderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(EncoderDemo.class);

    private EncoderDemo() {
    }

    public static void main(String[] args) {
        LOG.info("event=order.created order_id={}", "O-17");

        LOG.warn("event=payment.retry order_id={} attempt={}",
                "O-17", 2);

        LOG.info("event=checkout.completed outcome={}", "success");
    }
}
```

### Step 4: Compile and run

From the `logback-encoder-demo` directory, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.example.logging.EncoderDemo
```

**The three log lines emitted by the application, matching the configured pattern:**

```text
INFO|EncoderDemo|event=order.created order_id=O-17
WARN|EncoderDemo|event=payment.retry order_id=O-17 attempt=2
INFO|EncoderDemo|event=checkout.completed outcome=success
```

Maven or the runtime environment may print its own informational lines; the three lines above are the expected application output when only this `logback.xml` configuration is loaded.

### Why does the output appear this way?

- `LoggerFactory.getLogger(EncoderDemo.class)` uses the logger name `edu.example.logging.EncoderDemo`.
- `%logger{0}` displays only the short name `EncoderDemo`.
- `%msg` displays the message after `"{}"` has been replaced with `"O-17"`, `2`, and `"success"` respectively.
- `%level` prints the level name `INFO` or `WARN`.
- `%n` prevents records from being concatenated onto the same line.
- Omitting the timestamp is **intentional for this learning example** to keep output deterministic, not a recommended configuration for production.

If you change `<pattern>` to `%level|%msg%n`, the `EncoderDemo` segment disappears from the output **without modifying any Java code**. This is the core benefit of an encoder: **separating display formatting from business code**.

## 6. Charset, Bytes, and Newlines: Small Details That Easily Cause Incidents

### 6.1. Why must UTF-8 be specified explicitly?

An encoder's inputs are string values and event properties. Its final output is written as **bytes**, so the character encoding affects how Vietnamese text, Unicode characters, and special characters are stored.

Example message:

```text
Đã tạo đơn hàng
```

If the encoder uses UTF-8 but the tool reading the file decodes it with a different character set, viewers will see garbled characters even though `logger.info(...)` was called correctly. Ideally, all stages—**encoder → file/stream → collector → search UI**—should standardize on UTF-8.

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

The `<charset>` tag belongs to the encoder, not to the business properties of the message. When producing JSON, the corresponding encoder must also ensure proper encoding and escaping.

### 6.2. Why is `%n` needed?

If the pattern is `%level|%msg` without a line-ending character, consecutive events can run together:

```text
INFO|order.createdWARN|payment.retry
```

`%n` appends the environment's newline sequence. In centralized systems, record boundaries are critical so parsers do not merge multiple events or split a single event incorrectly.

Some encoders or protocols have their own framing, such as one JSON object per line or individual network messages. Therefore, **do not arbitrarily insert `%n` into every binary encoder**, though for `PatternLayoutEncoder` outputting line-oriented text, it is the standard choice.

### 6.3. What if a message contains newlines?

Even when a pattern has only one `%n` at the end, a message or stack trace can contain **embedded newline characters**. One event can produce multiple lines of text. If the collector assumes "one physical line = one event", you need to configure multiline handling or use an appropriately structured/escaped format.

Do not assume `%n` automatically guarantees every event fits on a single line. For JSON Lines logs, the encoder must escape newline characters inside string values to keep each JSON object on one complete line.

## 7. Encoders and Throwables / Stack Traces

A log call with an exception:

```java
try {
    paymentGateway.charge(orderId);
} catch (GatewayException failure) {
    log.error("event=payment.failed order_id={}", orderId, failure);
    throw failure;
}
```

This snippet is **illustrative** within an application class that has `paymentGateway`, `GatewayException`, `log`, and `orderId`. It will not compile standalone without those classes and variables.

Logback captures exception information via `ThrowableProxy` inside `ILoggingEvent`. Text encoders can output stack traces using conversion words such as `%ex`, while structured encoders can store the exception in a dedicated field. Comparing only `%msg` against a `Throwable` is not enough: the message is usually just a summary, whereas root-cause analysis needs the exception type, stack trace, and cause chain.

Example pattern that explicitly renders fields and exceptions:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex</pattern>
    <charset>UTF-8</charset>
</encoder>
```

**Do not assume that simply adding `%ex` guarantees every system has complete stack traces.** Check the active formatter, any exception truncation/limits in configuration, multiline collection, access permissions, and whether exception messages might contain secrets.

In Logback Classic, pattern processing may **automatically append an exception converter** in certain cases when the pattern does not declare a `Throwable` converter. Therefore, to control output precisely, declare the pattern intentionally and **inspect the actual encoded logs**, rather than assuming that omitting `%ex` always suppresses stack traces.

### Avoid logging the same exception at every layer

An encoder only renders events that have been emitted. If the repository, service, and controller all call `log.error(...)` and then rethrow the same `Throwable`, the encoder will format each of those events in turn; it **does not know that the three records belong to the same logical failure**.

Establish a rule at the boundary responsible for handling the final failure, or use distinct event codes if each layer genuinely records a different kind of event. Preventing duplicate logs is a matter of **event, logger, and appender design**, not changing the encoder pattern.

## 8. PatternLayoutEncoder vs. JSON Encoders

`PatternLayoutEncoder` is well-suited for human-readable text, for example:

```text
ERROR 2026-01-01T10:15:30Z payment.PaymentService - event=payment.failed order=O-17
```

In text format, fields like `order_id` or `error_code` may sit inside the message, requiring the collector to parse them if you want to query them. A properly configured JSON encoder can emit structured output:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "message": "Không thể hoàn tất thanh toán",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "error_code": "GATEWAY_UNAVAILABLE",
  "trace_id": "tr-42"
}
```

This is an **example of desired output**, not the default JSON output of `PatternLayoutEncoder`. To obtain structured JSON fields, use an encoder that supports structured output, pass fields via the appropriate API/backend, and verify field mappings at the collector.

### Can you build JSON manually with a text pattern?

Technically, you can assemble a string that looks like JSON:

```text
{"level":"INFO","message":"..."}
```

However, manual text assembly easily breaks when a message contains double quotes, backslashes, control characters, newlines, or Unicode data. **Do not use `PatternLayoutEncoder` as a general-purpose JSON generator by raw string concatenation.** Use a dedicated JSON encoder with reliable escaping rules and data types.

### How to choose a JSON encoder?

Depending on the Logback version and extension modules, JSON capabilities vary. A common choice in many projects is **`logstash-logback-encoder`**, which provides `LogstashEncoder`. A configuration snippet is only valid once the application has added a **compatible dependency**:

```xml
<appender name="JSON_CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder" />
</appender>
```

This configuration snippet is **illustrative to show where a JSON encoder fits**, not a standalone configuration for the Maven example in Section 5, because the sample `pom.xml` does not declare this extension library. Do not copy `LogstashEncoder` into a project's `logback.xml` without adding a compatible dependency; the application may fail to find the class and fail logging initialization.

Whichever JSON encoder you use, test values containing quotes, Unicode, newlines, exceptions, and null fields; then parse the output with a JSON reader to confirm data integrity and expected field types.

### SLF4J 2.x key-value pairs and MDC

With `SLF4J 2.x`, code can attach key-value pairs via the fluent API:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .log("Đã tạo đơn hàng");
```

This is an illustrative snippet assuming `log` and `orderId` exist. Key-value pairs appear in the output only if the encoder/pattern supports and is configured for them; **they do not automatically turn into JSON simply because the API called `addKeyValue`**.

`MDC` (Mapped Diagnostic Context) is per-thread shared context, such as `trace_id` or `request_id`. In text patterns, Logback can read it with `%X{trace_id}`. When using async execution or switching threads, ensure the context is propagated and cleared properly; otherwise, records may miss the trace ID or accidentally retain values from a previous request.

## 9. Using Encoders in ConsoleAppender, FileAppender, and RollingFileAppender

An application can use multiple appenders, each with an encoder suited to its destination.

Example of text with timestamps written to a file:

```xml
<appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/app.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
        <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
```

This is an **appender configuration snippet**, not a complete `logback.xml`: for it to work, you must attach `<appender-ref ref="FILE" />` to the appropriate logger/root in the configuration file and ensure the process has write permissions to the directory. This example illustrates where the encoder and file properties go; it does not imply a rotation policy.

With `RollingFileAppender`, the **rolling policy** decides when and how files are renamed/rotated, while the **encoder** still decides which bytes each event becomes. Do not assume adding `PatternLayoutEncoder` will automatically create daily files or enforce size limits. Log rotation is a separate concern requiring `rollingPolicy` and the appropriate components.

### Can one encoder be reused across multiple appenders?

By design, **each appender should generally have its own encoder configuration** to keep lifecycles and output policies clear, especially if two channels need different charsets, patterns, or fields. Some API versions may allow reusing an encoder object in certain cases, but avoid relying on shared state between appenders unless you thoroughly understand its lifecycle and thread safety.

For example, a console for operators might use concise text, while a collection pipeline needs one-event-per-line JSON. You use the same **Java logging code**, but configure **two separate appenders/encoders** with their own filters and access controls.

### Common mistake: configuring an appender without attaching it to a logger

If you write an appender with a valid encoder but forget:

```xml
<root level="INFO">
    <appender-ref ref="FILE" />
</root>
```

there is no guarantee that the appender will receive any events. An encoder only runs when an event actually reaches the appender. Similarly, if a logger level or filter drops the event beforehand, changing the encoder will not make logs "reappear".

## 10. Performance and Reliability of Encoding

Encoding is not free: reading MDC, formatting dates/times, building messages, rendering exceptions, generating JSON, and converting Unicode to bytes all consume CPU and memory. The most significant cost usually comes from **log volume, large stack traces, I/O, and collection pipelines**, rather than just a few tokens in a pattern.

Key considerations:

1. **Sensible log levels:** avoid formatting millions of unnecessary `DEBUG` events in production. Logs blocked at the logger never reach the encoder.
2. **Sufficiently lean patterns:** logger name, timestamp, level, correlation ID, and a meaningful message are usually more useful than an overly long pattern packed with expensive fields.
3. **Intentional exceptions:** long stack traces have diagnostic value but increase volume; avoid logging the same exception repeatedly across every layer.
4. **Asynchrony:** `AsyncAppender` can offload downstream processing from business threads. It typically wraps a target appender; the encoder remains on the actual writing appender. Queues can fill up or drop logs on abrupt shutdown depending on policy.
5. **Flushing and buffering:** the encoder produces bytes; the appender and stream are responsible for writing, flushing, and closing according to lifecycle. The encoder itself does not guarantee durable storage.
6. **Framing:** line-delimited formats require clear record boundaries, especially when pipelines read stdout. Multiline records and unescaped JSON easily cause collector parsing errors.
7. **Concurrent logging:** multiple threads emit events simultaneously; use library-tested encoders/appenders and do not store request state in shared encoder fields.
8. **Backpressure:** slow outputs or full queues can increase latency or drop logs. Monitor appender/collector health, not just the Java code calling the logger.
9. **Storage cost:** every field added to high-frequency records increases volume. Balance detail level, retention, and query needs.
10. **Critical records:** do not treat calling `log.error` as a delivery guarantee. For audit or business events that must not be lost, design dedicated reliable storage/delivery and reconciliation mechanisms.

### Does changing the encoder change business logic?

In principle, an encoder only changes **representation** and should not alter business outcomes. However, the encoder executes on the logging path; misconfiguration, buggy converters, or serializing complex objects can impact resources and latency. Do not place side-effecting I/O or unnecessarily expensive computations inside a custom converter/encoder.

## 11. Testing Encoders in Java Applications

A good test strategy separates two goals:

### 11.1. Verifying events before encoding

You can attach Logback's `ListAppender<ILoggingEvent>` to a test logger to verify:

- Level and logger name are correct.
- `getFormattedMessage()` is accurate after `{}` substitution.
- `getThrowableProxy()` is present when a stack trace is expected.
- MDC or key-value pairs match the context.
- A terminal failure is not logged multiple times unintentionally.

`ListAppender` helps verify the event, **but does not prove the encoder's output bytes** or charset are correct.

### 11.2. Verifying the actual bytes produced by the encoder

Use a test appender backed by an in-memory output stream, attach the exact production encoder, and emit sample events. Read the bytes using the configured charset and verify:

- Order of level/logger/message and delimiters.
- Newlines according to policy.
- Vietnamese and Unicode characters are not corrupted.
- Values containing quotes or newlines are escaped as required by the format.
- For JSON: the output parses cleanly and fields have expected types.
- For Throwables: stack trace/cause are rendered according to contract.
- No secrets or sensitive mock data are leaked.

For patterns containing `%d`, `%thread`, or stack traces, avoid comparing the entire output against a brittle fixed string; assert on stable components or use an appropriate matching pattern. The example in Section 5 intentionally **omits the timestamp** so stdout can be verified easily.

### 11.3. Verifying integration with the collector

After the application emits logs, confirm that the collector actually:

1. Receives the right output stream or file path.
2. Decodes UTF-8 properly.
3. Detects record boundaries accurately and handles multiline when needed.
4. Parses `event_code`, `trace_id`, and `error_code` accurately.
5. Does not drop, duplicate, or filter out events unexpectedly.
6. Has appropriate access permissions and retention, and contains no prohibited data.

**Note:** seeing a log line in the console does not prove it reached the centralized log store. Conversely, an event appearing twice in the UI may be caused by fan-out, additivity, or pipeline retries—not the encoder "duplicating" messages on its own.

## 12. Common Configuration Errors

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| No logs appear | Logger level, filter, or unattached appender | Check logger → appender first; the encoder does not create events. |
| Logs appear in the wrong format | Incorrect pattern, or a different `logback.xml` is loaded | Identify the active configuration and the encoder on the receiving appender. |
| Logger name too long or too short | Using `%logger` or `%logger{0}` unintentionally | Adjust the conversion word; keep the full name when needed. |
| Lines run together | Missing `%n` in text pattern | Add a newline according to formatting policy. |
| Vietnamese text turns into garbled characters | Encoder and reader use different charsets | Standardize on UTF-8 across the entire collection pipeline. |
| Stack trace missing or unexpected | Throwable not passed, or pattern/encoder/collector limits | Verify the event has a Throwable, then check formatter and multiline settings. |
| Invalid JSON | Manual JSON concatenation in text pattern without escaping | Switch to a dedicated JSON encoder and test parsing. |
| `LogstashEncoder` configured but fails to run | Missing or mismatched dependency version | Check JARs, classpath, and Logback/SLF4J compatibility. |
| `%X{trace_id}` is empty | MDC not set or not propagated across execution | Check MDC propagation and cleanup. |
| Logs appear twice | Appender on both child logger and root with additivity, or collector retry | Check routing configuration and count per destination. |
| Large file does not rotate | Using `FileAppender` or missing rolling policy | Use `RollingFileAppender` with a rolling policy. |
| Missing JSON key-value fields | Fluent API attached fields, but encoder does not emit them | Check encoder/provider support and configuration. |

## 13. Practice Exercises

**Exercise 1.** Given the encoder configuration:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%level|%logger{0}|%msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

And a call:

```java
logger.warn("event=payment.retry attempt={}", 3);
```

Assuming the logger is named `com.example.payment.PaymentService`, determine the output.

**Hint:**

```text
WARN|PaymentService|event=payment.retry attempt=3
```

`%logger{0}` shortens the source name, `%msg` retrieves the message with `{}` substituted, and `%n` appends a newline.

**Exercise 2.** If `<pattern>` is changed to `%msg%n` while keeping the business code unchanged, what changes?

**Hint:** The output still contains the message with arguments substituted, but the level and logger name are removed from the start of the line. Which events are created or accepted does not change by default, because the level and appender were not altered.

**Exercise 3.** An application writes Vietnamese text to a file, but the analysis tool displays garbled characters. What should the diagnostic order be?

**Hint:** Check the source data, the encoder's charset, the actual bytes in the file, the charset used when the collector reads/parses, and how the UI displays it. Standardize on UTF-8; do not alter business messages when the issue is in decoding.

**Exercise 4.** A team wants to send JSON to a collector. Should they write `<pattern>{"message":"%msg"}</pattern>` manually or use a JSON encoder?

**Hint:** Use an appropriate JSON encoder. Messages containing quotes, newlines, or backslashes can break hand-rolled JSON, and numeric fields may be coerced into strings. Test JSON parsing and data types at the destination.

**Exercise 5.** An exception was logged properly at the `ERROR` level, but no stack trace appears in the centralized system. Can you conclude the encoder is at fault?

**Hint:** Not yet. Check whether the code passed the `Throwable` or only `getMessage()`, whether `ILoggingEvent` holds the `Throwable`, whether the pattern/encoder renders exceptions, whether the collector preserves multiline or exception fields, and whether the search UI truncates data.

**Exercise 6.** For the same event, you need concise console text for developers and JSON for the collector. Should you write two `log.info` calls in business code?

**Hint:** Usually **no**. Emit one event and configure separate appenders/encoders per destination. Check additivity and routing to avoid duplication within the same channel, and verify that sensitive fields are protected across all paths.

**Self-assessment:** You understand Logback encoders when you can explain the chain **`ILoggingEvent → Encoder → bytes → Appender output`**, read and modify `PatternLayoutEncoder`, distinguish SLF4J's `{}` from Logback's `%msg`, know why UTF-8 and `%n` are used, handle exceptions, and verify formatted output with tests rather than only looking at logger calls.
