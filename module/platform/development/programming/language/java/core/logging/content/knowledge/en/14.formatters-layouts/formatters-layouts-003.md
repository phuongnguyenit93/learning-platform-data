# Pattern Layout in Java Logging: Designing and Testing Log Formats

## 1. What Is a Pattern Layout?

A **pattern layout** is a mechanism that transforms a **logging event** into a **structured text string according to a pattern**. An event typically contains a timestamp, level, logger name, thread name, parameter-substituted message, MDC/context, and an exception (Throwable). The pattern defines **which fields are printed, their order of appearance, alignment, and delimiters**.

For example, consider an event containing:

- Level: `INFO`
- Logger: `demo.order.OrderService`
- Message: `event=order.created order_id=O-17`
- MDC `trace_id`: `tr-42`

With an illustrative pattern:

```text
%level|%logger{0}|trace=%X{trace_id}|%msg%n
```

The resulting line might be:

```text
INFO|OrderService|trace=tr-42|event=order.created order_id=O-17
```

The `|` characters and the text `trace=` are literal characters; `%level`, `%logger{0}`, `%X{trace_id}`, `%msg`, and `%n` are **conversion words** understood by the logging library.

A pattern layout solves **consistent presentation of information**; it does not decide which events occur and does not replace exception handling. It also does not guarantee on its own that logs are persisted, delivered to a collector, or protected against data leaks.

In Java, this concept is commonly seen in:

- **Logback Classic:** `PatternLayout` generates text; `PatternLayoutEncoder` is typically used to convert the result into bytes for the console/file.
- **Log4j 2:** `PatternLayout` is configured directly inside an appender such as `Console`, `File`, or `RollingFile`.
- **java.util.logging (JUL):** has `Formatter` and `SimpleFormatter`, and does not use the exact `PatternLayout` syntax of Logback/Log4j 2.

Because different libraries have different conversion words and configuration styles, **do not copy patterns between backends and assume the output will be identical**.

## 2. Where Does Pattern Layout Sit in a Logging System?

A typical pipeline:

```text
Java Code: logger.info("order={}", orderId)
            |
            v
Logging API: SLF4J or Log4j 2 API
            |
            v
Logger + effective level + filter
            |
            v
Logging event (level, logger, args, MDC, Throwable...)
            |
            v
Appender (manages output destination)
            |
            v
Layout / Encoder (interprets pattern into text/bytes)
            |
            v
Console / file / collection system
```

Comparison table:

| Component | Responsibility | Example |
| --- | --- | --- |
| `Logger` | Receives events from code, applies effective level | `com.example.payment.PaymentService` |
| `Log event` | Carries data for a single log call | timestamp, level, message, MDC, Throwable |
| `Filter` | Accepts or rejects events | Only WARN and above to a specific channel |
| `Appender` | Manages output destination and output lifecycle | ConsoleAppender, RollingFileAppender |
| `Layout` | Selects fields, order, and text formatting | PatternLayout |
| `Encoder` | Converts events into bytes for the appender to write | Logback's PatternLayoutEncoder |
| Collector | Collects, parses, and indexes outside the JVM | stdout/file reader or logging agent |

If a `DEBUG` line has already been blocked by the logger, editing `%msg` or `%level` in the pattern **will not make it appear**. Conversely, if the logger has accepted the event, removing `%logger` from the pattern only omits the source name **in the displayed output**; it does not mean the logger no longer has a name.

**A pattern layout is a presentation step, not a mechanism for measuring error rates.** A single request can produce multiple log records or none; the number of ERROR lines does not automatically equal the number of failed requests.

## 3. Reading a Pattern Component by Component

Example:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

It can be read from left to right:

1. `%d{HH:mm:ss.SSS}`: time in an hour-minute-second-millisecond format; this version **has no date or timezone**.
2. Space: a literal space character.
3. `%-5level`: level name, left-aligned within a minimum width of 5 characters. For example, `INFO ` has an extra space to reach the width.
4. `[%thread]`: the square brackets are literals; the value inside is the thread name.
5. `%logger{36}`: shortened logger name according to the backend's rules.
6. ` - `: literal delimiter.
7. `%msg`: the formatted message.
8. `%n`: platform-appropriate newline character.

The `%` sign typically introduces a conversion word. The curly braces `{...}` following a conversion word are **configuration parameters for the conversion**, not the same as `{}` used in Java statements for message parameter substitution.

### Common Conversion Words

| Meaning | Logback Classic (common) | Log4j 2 PatternLayout (common) | Notes |
| --- | --- | --- | --- |
| Timestamp | `%d{...}` or `%date{...}` | `%d{...}` or `%date{...}` | Format/timezone syntax may differ; check version. |
| Level | `%level`, `%p` | `%level`, `%p` | Width can be formatted with `%-5level`. |
| Logger | `%logger`, `%c` | `%logger`, `%c` | Supports abbreviation, though rules may differ. |
| Thread | `%thread`, `%t` | `%thread`, `%t` | Thread names are not fixed across runs. |
| Message | `%msg`, `%message`, `%m` | `%msg`, `%message`, `%m` | Output has message parameters substituted as appropriate. |
| MDC/context | `%X{trace_id}` | `%X{trace_id}` | Depends on setting the context properly. |
| Exception | `%ex`, `%exception` | `%ex`, `%throwable` | Multi-line output; backend-specific options exist. |
| Newline | `%n` | `%n` | In line-based text logs, usually essential. |
| Key-value event | `%kvp` (supported versions) | Depends on pattern/converter/backend | Do not assume key-value pairs appear automatically without configuration. |

This table is a guide to reading common patterns, **not a guarantee that every alias/option is available in every version**. For specialized converters, consult the exact backend documentation and verify the actual output.

## 4. Pattern, Message Template, and Structured Logging Are Three Distinct Concepts

In Java code using SLF4J:

```java
log.info("event=order.created order_id={}", orderId);
```

Here `{}` is a placeholder to substitute a value. If `orderId` is `"O-17"`, the formatted message is:

```text
event=order.created order_id=O-17
```

In `logback.xml`:

```xml
<pattern>%level|%msg%n</pattern>
```

`%msg` is a **layout** token that retrieves the prepared message from the logging event. Therefore:

```text
INFO|event=order.created order_id=O-17
```

Do not confuse the three layers:

- **Parameter substitution:** replaces `{}` in the message with arguments from the logger call.
- **Pattern layout:** selects and arranges event fields into a string.
- **Structured logging:** emits attributes such as `level`, `event_code`, `order_id`, and `duration_ms` as separate typed fields for querying.

A text pattern like `order={} amount={}` still only produces a **string**; it does not guarantee that a centralized logging system automatically understands `amount` as a number. For reliable field querying, use a trustworthy JSON encoder/layout or a collector with a verified parser.

### Why Not Print Everything Manually in Java Code?

Avoid scattering code that manually builds timestamps, thread names, and class names at every call site:

```java
log.info("[" + Thread.currentThread().getName() + "] "
        + "order=" + orderId);
```

This is an **illustrative snippet** inside a method that already has `log` and `orderId`. This approach duplicates the layout's job, makes system-wide format changes difficult, and may evaluate string concatenation before the logger checks the level.

Instead:

```java
log.info("event=order.created order_id={}", orderId);
```

Then, use the pattern to consistently add thread name, logger, level, and timestamp. Still, important business information must be passed into the event; the layout cannot guess which `order_id` is being processed.

## 5. Logback: How to Configure PatternLayoutEncoder

With a compatible **SLF4J 2.x + Logback Classic** setup, a simple console appender looks like:

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

**Explanation:**

- `<configuration>` is the root element of `logback.xml`.
- `<appender name="CONSOLE">` creates a console destination; the name `CONSOLE` is referenced below.
- `<encoder class="...PatternLayoutEncoder">` converts events into bytes based on the pattern; `PatternLayout` is the text-formatting component used by the encoder.
- `<charset>UTF-8</charset>` defines the output character encoding.
- `%level|%logger{0}|%msg%n` produces a short, predictable line for debugging.
- `<root level="INFO">` is the default level; normal DEBUG events are dropped, while INFO/WARN/ERROR are allowed.
- `<appender-ref ref="CONSOLE" />` attaches the destination to root; defining an appender without attaching it to a logger can result in no output.

**Do not treat a pattern without a timestamp as an optimal production configuration.** The example above is for predictable testing. Real systems typically need timestamps with date/timezone, service name, trace ID, event code, and a consistent exception representation.

### Logback: Differences from Log4j 2

Common Logback `ConsoleAppender`/`FileAppender` configurations usually configure an **encoder**:

```xml
<encoder>
    <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
</encoder>
```

Log4j 2 usually configures **layout** directly under the appender:

```xml
<PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n" />
```

These two snippets belong to **two different configuration formats** and must not be placed into the other backend's file by mistake. Seeing `<PatternLayout>` does not mean every system is running Log4j 2, but tag names, placement, and class names in configs help identify the active backend.

## 6. Runnable Java 17 Example: Logback PatternLayout

This example demonstrates the complete setup: Maven dependencies, `logback.xml`, Java application, MDC, and console output. To keep the lines predictable, the pattern omits timestamp and thread name.

**Prerequisites:** JDK 17 or later, Maven, and the ability to fetch Maven dependencies. Specific library versions are used in the example for reproducibility, not as a claim that they are the latest or suitable for every current project.

Directory structure:

```text
pattern-layout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── logging/
        │           └── PatternLayoutDemo.java
        └── resources/
            └── logback.xml
```

### 6.1. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pattern-layout-demo</artifactId>
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

`logback-classic` provides the backend and corresponding SLF4J provider, and pulls in the required dependencies. If an application already uses a framework that manages logging versions, follow the framework's dependency management instead of adding a second provider or mixing API versions manually.

### 6.2. Create `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|trace=%X{trace_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Notable detail: `%X{trace_id}` retrieves its value from the **MDC** (Mapped Diagnostic Context) set by the application while handling a request. If the key is absent, the conversion usually evaluates to an empty string. Thus, when a message is logged after cleanup, the `trace=` column will have no value.

### 6.3. Create `src/main/java/demo/logging/PatternLayoutDemo.java`

```java
package demo.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class PatternLayoutDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(PatternLayoutDemo.class);

    private PatternLayoutDemo() {
    }

    public static void main(String[] args) {
        MDC.put("trace_id", "tr-42");
        try {
            LOG.info("event=order.created order_id={}", "O-17");
            LOG.warn("event=stock.low sku={} remaining={}",
                    "SKU-9", 2);
            LOG.debug("event=debug.hidden");
        } finally {
            MDC.remove("trace_id");
        }

        LOG.info("event=request.finished");
    }
}
```

### 6.4. Compile and Run

From the `pattern-layout-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.logging.PatternLayoutDemo
```

**Three logging lines emitted by the application under the sample configuration:**

```text
INFO|PatternLayoutDemo|trace=tr-42|event=order.created order_id=O-17
WARN|PatternLayoutDemo|trace=tr-42|event=stock.low sku=SKU-9 remaining=2
INFO|PatternLayoutDemo|trace=|event=request.finished
```

Maven and the runtime environment may print their own messages. The output above lists **only the application's lines** when only the sample configuration is loaded; Maven's internal output is excluded.

### 6.5. Line-by-Line Explanation

1. `PatternLayoutDemo.class` creates a logger named `demo.logging.PatternLayoutDemo`; `%logger{0}` makes the output show the short name `PatternLayoutDemo`.
2. `LOG.info` and `LOG.warn` pass the root `INFO` threshold; `LOG.debug` is filtered out, so there is no `event=debug.hidden` line.
3. `MDC.put("trace_id", "tr-42")` sets context for the executing thread. The first two events have `trace=tr-42`.
4. `%msg` retrieves the message after `{}` has been replaced with `O-17`, `SKU-9`, and `2`.
5. `finally` calls `MDC.remove`, cleaning up the context after processing finishes. The final line is logged after cleanup, so `trace=` is empty. This illustrates the risk of stale MDC data when a thread is reused across multiple requests.
6. `%n` separates the three events onto individual lines.
7. This is an example of **text logging**; `trace_id` is only **printed in a string**. Whether it becomes a separate field in a collector depends on a parser or a structured encoder.

### 6.6. Try Changing the Pattern

Replace:

```xml
<pattern>%level|%logger{0}|trace=%X{trace_id}|%msg%n</pattern>
```

with:

```xml
<pattern>%level|%msg%n</pattern>
```

and run again. The first line becomes:

```text
INFO|event=order.created order_id=O-17
```

The business event itself has not changed; only the **presentation** omits the logger name and trace from the output. This is the benefit of a pattern layout: centralizing formatting in one place.

If you change `root level="INFO"` to `DEBUG`, the `LOG.debug` call can appear, because that is a **level policy** change, not a pattern change. Distinguish between these two types of edits when testing.

## 7. Log4j 2: PatternLayout in `log4j2.xml`

If the application uses **Log4j 2 Core**, the semantically equivalent syntax is:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%level|%c{1}|trace=%X{trace_id}|%msg%n"
                charset="UTF-8" />
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE" />
        </Root>
    </Loggers>
</Configuration>
```

Here `<PatternLayout>` sits **directly inside `<Console>`**; Logback's `PatternLayoutEncoder` is not used. Log4j 2 requires `log4j-api` and `log4j-core` (or the appropriate modules/providers) to use this configuration.

If the code uses the Log4j 2 API directly:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

Logger log = LogManager.getLogger("demo.payment");
ThreadContext.put("trace_id", "tr-42");
try {
    log.info("event=payment.completed order_id={}", "O-17");
} finally {
    ThreadContext.remove("trace_id");
}
```

This is an **illustrative snippet inside a method**, not a standalone Java file: the packages require the Log4j 2 library and the code must be placed inside a class/method. With `%c{1}`, the logger name `demo.payment` is shortened according to Log4j 2's logger naming rules; do not rely on this abbreviation as a unique identifier if multiple loggers share the same trailing segment.

**Key point:** SLF4J's `MDC` and Log4j 2's `ThreadContext` both serve logging context, but they are not interchangeable classes regardless of backend. When using SLF4J → Log4j 2, verify the provider and context synchronization behavior in your actual configuration.

### Do Logback and Log4j 2 Share All Converters?

No. Basic converters like `%d`, `%level`, `%logger`, `%msg`, and `%n` look similar, but:

- Logger name abbreviation rules, date/time options, and timezone syntax may differ.
- Extended converter names and parameterization syntax differ.
- Automatic appending of exceptions/Throwables to output must not be assumed to work identically.
- Some converters require specific modules or versions.
- Configuration filenames and XML element locations differ.

When switching backends, **translate the configuration and re-test the output**, rather than simply renaming `logback.xml` to `log4j2.xml`.

## 8. Alignment, Truncation, and Readability

Pattern layouts are often used to produce console lines that are easy to scan visually.

Example:

```text
%-5level [%thread] %-30logger - %msg%n
```

Symbols:

- `-` in `%-5level` means left-aligned.
- `5` is the minimum width; if the level name is shorter, the layout pads with spaces.
- `%-30logger` targets a logger column of at least 30 characters; longer names can exceed this width.
- `[`, `]`, and ` - ` are literal characters that help separate fields.

**Minimum width is not maximum length.** `%-30logger` does not automatically guarantee the logger name is capped at 30 characters. If you want abbreviation or truncation, use an option supported by your backend and test with long strings. In Logback, `%logger{36}` uses a name-shortening algorithm; in Log4j 2, logger abbreviation options may differ.

Column alignment is well-suited when reading primarily in a terminal. However, logs intended for automated processing should not rely on padding spaces for parsing. Values such as thread names or messages may contain spaces, delimiters, or newlines.

### When to Keep the Full Logger Name?

For a developer console, `%logger{0}` or an equivalent short form is clean and readable. In a centralized log store where investigations filter by package/class, consider **keeping the full logger name in a dedicated field** to distinguish two classes with the same short name in different packages.

Example:

```text
com.example.orders.Service
com.example.payments.Service
```

If only `Service` is displayed, the two sources can be confused. A logger name is also not a service/instance identity: to correlate hosts and deployments, include `service`, `environment`, and `version` fields as appropriate.

## 9. Timestamps and Timezones in Patterns

A time pattern like:

```text
%d{HH:mm:ss.SSS}
```

is useful when watching a terminal briefly, but insufficient for systems running across multiple days or regions.

In production, set clear requirements:

1. Include both **date** and time, not just time of day.
2. Include **timezone/offset**, or standardize on UTC across the entire pipeline.
3. Use appropriate precision, typically milliseconds; do not assume every backend preserves nanoseconds.
4. Distinguish **event creation time** from **collector ingestion time**.
5. Verify the exact date/time and timezone pattern syntax for the **backend and version in use**.

Example **Logback-specific configuration snippet** (using Logback's time pattern syntax):

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level %logger - %msg%n</pattern>
```

This is only the pattern element inside a valid Logback encoder/layout. In Log4j 2, passing timezone and format may use different syntax; do not copy Logback's `,UTC` syntax without checking the Log4j 2 documentation.

Whichever timezone you use, verify that a real log record has an accurate, parseable timestamp. Do not hard-code a dynamic timestamp in a unit test's expected output: the test will fail on the next run even when the configuration is correct.

## 10. MDC, Trace IDs, and Thread-Scoped Context Limits

A very useful feature of pattern layouts is adding per-request information without repeating it in every logger call:

```text
%X{trace_id} %X{request_id} %msg%n
```

With Logback + SLF4J, values are typically managed by `MDC.put` within an execution scope. A proper usage pattern is:

```java
MDC.put("trace_id", traceId);
try {
    service.handleRequest();
} finally {
    MDC.remove("trace_id");
}
```

This is an illustrative snippet assuming `traceId` and `service` already exist. Additional handling is needed if a request uses multiple MDC keys or if pre-existing context is present.

**Context does not automatically propagate across all threads.** When using `CompletableFuture`, thread pools, executors, or reactive pipelines, the following can happen:

- Loggers on child threads do not see `trace_id`.
- Reused threads retain data from old requests if cleanup is forgotten.
- Asynchronous work completes after the original request finishes, requiring an explicit context propagation mechanism.

Use a context propagation mechanism supported by your framework/backend and test the real execution path. Do not assume `MDC.put` on the request thread will automatically appear in every async task.

### Correlation IDs Are Not Event Codes

- `trace_id` links steps belonging to one processing flow, typically across many events with the same ID.
- `request_id` identifies a specific request according to system convention.
- `event_code` describes the *type of event*, e.g., `payment.failed` or `order.created`.
- `error_code` classifies the failure cause, e.g., `UPSTREAM_TIMEOUT`.

A text pattern can print them side by side, but **keeping distinct field names** in structured logging makes querying far more reliable. Do not create a unique logger name or event code per request — that makes grouping data difficult.

## 11. Throwables and Stack Traces: Patterns Must Be Tested with Real Errors

A common bug is having a clear message while the stack trace is missing or duplicated. Example in an SLF4J application:

```java
try {
    gateway.charge(orderId);
} catch (GatewayException failure) {
    log.error("event=payment.failed order_id={}", orderId, failure);
    throw failure;
}
```

This is **illustrative code** and does not compile standalone because `gateway`, `GatewayException`, `log`, and `orderId` belong to a real application.

With this call, the `Throwable` object is passed so the backend can capture the exception type, cause chain, and stack trace. If the code only uses:

```java
log.error("payment failed: {}", failure.getMessage());
```

then the message is just a string; the backend has no original exception to render a stack trace.

A text pattern can declare an exception converter:

```text
%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex
```

However, keep the following in mind:

- **Having a Throwable in the event is different from having the Throwable printed.** Layouts/encoders and collectors may limit or strip exceptions.
- Logback Classic and Log4j 2 have mechanisms that automatically append stack traces when no exception converter is declared in the pattern in certain cases/versions. Do not claim "omitting `%ex` always drops stack traces"; inspect the actual configuration.
- Stack traces typically span **multiple physical lines** even though they belong to one logical event. Text collectors need appropriate multiline or framing configuration.
- Exception messages and causes can contain URLs with tokens, SQL with sensitive values, or personal data. Do not log every Throwable indiscriminately.
- If repository, service, and controller layers all `log.error + rethrow` the same exception, the layout will format all three events; it does not deduplicate them.

**Good strategy:** inspect events in a test appender to verify the Throwable is present, then inspect the **final bytes/output** to confirm the stack trace is rendered properly. Do not treat `getThrowableProxy() != null` in a unit test as proof that the collector received the full exception.

### Exception Detail Options

Many backends support options to limit length or abbreviate exceptions. These options can reduce log noise, but should not truncate the root cause needed for diagnosis. For rare, severe errors, keep the full cause chain; for high-frequency retries, balance how often stack traces are logged with the meaning of each event.

## 12. Text Patterns, JSON Lines, and Log Injection Risks

Pattern layouts excel at producing readable text. They do not automatically guarantee valid JSON output, nor do they escape values for parsers.

Dangerous example:

```xml
<pattern>{"level":"%level","message":"%msg"}%n</pattern>
```

If the message contains quotes, backslashes, or newlines, manually assembled JSON can become **invalid**, or alter record boundaries. In some XML configurations, XML-reserved characters must also be escaped. Therefore, **do not use pattern string concatenation to hand-craft JSON in general**.

Example of desired structured JSON content:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "service": "checkout",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "trace_id": "tr-42",
  "error_code": "UPSTREAM_TIMEOUT",
  "message": "Không thể hoàn tất thanh toán"
}
```

This is a **schema example**, not the default output of `PatternLayout`. For typed data and reliable escaping, choose a JSON encoder/layout compatible with your backend and project version:

- With Logback, you can use an appropriate JSON encoder library, such as `logstash-logback-encoder` with a compatible dependency.
- With Log4j 2, JSON layout/`JsonTemplateLayout` options are available in the appropriate module.
- Whichever backend you choose, verify the emitted fields, data types, exceptions, and collector parsing results.

**Adding a JSON encoder does not invent event codes:** the application must still supply `event_code` and the necessary context fields. Depending on the API, you can use key-value pairs, MDC/ThreadContext, or a dedicated structured logging mechanism.

### Newlines and "One Line = One Event"

`%n` **terminates** a text line, but if `%msg` contains newline characters or a multi-line stack trace, a single event still produces multiple lines. A naive line-by-line parser can miscount events. With JSON Lines, the encoder must escape newlines inside strings so each object is one complete record; with text logs, configure multiline handling appropriately.

### Log Injection and Sensitive Data

An attacker can send input containing:

```text
invalid value
ERROR ADMIN LOGIN SUCCESS
```

If concatenated directly into a text message, this content can look like multiple log records. A pattern layout does not distinguish between newlines added by the logger and those coming from user data. Therefore:

1. Do not log full sensitive inputs/payloads.
2. Use typed data fields and an encoder with reliable escaping.
3. Have a policy to replace or strip control characters when needed.
4. Enforce log read permissions, retention, and security rules across all channels.
5. Test with dummy data containing tokens, quotes, Unicode, and newlines.

Do not rely solely on a regex replacement in the pattern to protect all secrets; exception fields, MDC, and other output branches can still leak data.

## 13. Performance and Operations of Pattern Layouts

Formatting events has a cost. For every accepted record, the backend may need to:

- Format the timestamp and timezone.
- Convert level, thread, logger name, and MDC to strings.
- Substitute arguments into the message.
- Format the Throwable/stack trace if present.
- Encode strings into bytes according to the charset.
- Write to console, file, socket, or queue.

Operational principles:

| Issue | Impact | Mitigation |
| --- | --- | --- |
| Pattern with too many fields | Long lines, higher formatting and storage cost | Select only information useful for investigation. |
| Stack traces repeated across layers | Noisy logs, higher cost, skewed counts | Define a boundary for logging the final error event. |
| Excessive DEBUG/TRACE logging | Increased CPU, I/O, and storage | Enable selectively by package/time window. |
| Logging messages with expensive `toString()` objects | Higher latency and serialization error risk | Pass allowed simple values; avoid heavy computation. |
| Slow synchronous appender | Business threads may block on I/O | Measure in practice; consider async with buffer/drop policy. |
| Full async queue | Logs may be dropped per policy | Monitor drop counts and shutdown procedures. |
| Wrong console/file charset | Vietnamese characters garbled | Standardize on UTF-8 from output to collector. |
| Collector misparses multiline | One event becomes multiple bogus events | Use framing/multiline or an appropriate JSON encoder. |

**A pattern is not a log level.** When DEBUG level is disabled, editing the pattern will not make DEBUG events appear. If an argument in a Java call is `expensive()`, Java still evaluates it before invoking the logger; placeholder message formatting avoids string formatting when logging is disabled, but does not defer argument evaluation on its own.

**There is no exactly-once guarantee.** A logger call can be lost in the pipeline or duplicated due to collector retries, appender/additivity configuration, or logging multiple times in code. If you need business auditing with zero data loss, use a dedicated storage/delivery mechanism rather than standard logging.

## 14. Layered Testing of Pattern Layouts

Separate testing into at least three levels.

### 14.1. Inspecting Events Before the Layout

With Logback, a `ListAppender<ILoggingEvent>` in tests can verify:

- Event `level`.
- `getLoggerName()`.
- `getFormattedMessage()`.
- `getMDCPropertyMap()`.
- `getThrowableProxy()` when an exception is present.

This test proves **the logger created the right event**; it does not prove the layout produced the right bytes.

### 14.2. Inspecting Layout/Encoder Output

Pass a sample event through an appender with the real layout/encoder, capture the bytes in a buffer, and decode them using the configured charset. Verify:

- The `|` delimiters and field order.
- Abbreviated/full logger name as expected.
- Whitespace and padding if part of the contract.
- Presence of newline where required.
- Vietnamese characters are not garbled.
- MDC keys appear properly and do not persist after cleanup.
- Exceptions/stack traces are rendered as intended.
- No dummy secrets appear in any channel.

When a pattern includes `%d` or `%thread`, do not compare the entire output against a brittle fixed string. Parse fields and assert meaningful values, or check that the timestamp falls within a reasonable range.

### 14.3. Verifying the Real Collector

In staging, emit an event with an easily searchable `event_code` and `trace_id`, then verify:

1. Did the application emit the event?
2. Which stdout/file did the appender actually write to?
3. Did the collector read the right source and decode UTF-8?
4. Was the data split incorrectly due to newlines/stack traces?
5. Were structured fields parsed and indexed?
6. Does the record count at the destination match fan-out/retry policies?
7. Does the query UI have the right permissions, environment, and time range?

Seeing an event on the console **does not prove** it reached the centralized system. Conversely, seeing two search results is not enough to conclude the layout duplicated it: it could be due to appender routing or pipeline retries.

## 15. Troubleshooting When a Pattern Does Not Work

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Editing `logback.xml` does not change output | Active backend is not Logback, another file is loaded, or process wasn't reloaded | Identify provider, classpath, and runtime config. |
| Pattern has `%logger{0}` but displays wrong name | Different backend, unexpected logger name, or different abbreviation rules | Check original logger name and actual converter. |
| DEBUG logs not appearing | Logger level or filter blocks them | Check levels and appender routing before editing pattern. |
| Logs appear but `trace_id` is missing | MDC not set, not propagated across async, or wrong key | Check MDC/ThreadContext and context lifecycle. |
| Vietnamese characters garbled | Encoder/terminal/collector charset mismatch | Verify UTF-8 bytes and decoding. |
| Two lines merged together | Missing `%n` or wrong framing | Add newline or use an encoder with proper framing. |
| One exception becomes multiple lines in collector | Multiline stack trace misparsed | Enable multiline or use proper JSON escaping. |
| Stack trace missing | Throwable not passed, or layout/collector strips exceptions | Check API call, event, converter, and collector. |
| Output contains literal `%` and strange converter | Invalid token, broken XML, or unsupported on backend/version | Check converter docs and status logs. |
| Searching by order ID fails due to missing field | ID is only inside `%msg`; parser does not extract it | Use structured logging or a tested parser. |
| Duplicate appender output | Additivity, appender attached to child and root, or collector retry | Check logger/appender routing and each destination. |
| Log file grows unusually large | Pattern has too many fields, large Throwables, or high log volume | Measure volume, levels, retention, and performance. |
| Hand-crafted "JSON pattern" has syntax errors | Message is not JSON-escaped | Use a dedicated JSON encoder/layout. |

### Pipeline Troubleshooting Flow

```text
Does the code call the logger?
   |
   +-- No --> Check code branch / exception / business outcome
   |
   +-- Yes --> Do level and filter accept it?
                |
                +-- No --> Check logger name, level, filter
                |
                +-- Yes --> Does the appender receive it?
                             |
                             +-- No --> Check AppenderRef, additivity, routing
                             |
                             +-- Yes --> Does the layout/encoder emit the right bytes?
                                          |
                                          +-- No --> Check pattern, charset, converter, Throwable
                                          |
                                          +-- Yes --> Does the collector read and parse it correctly?
                                                       |
                                                       +-- No --> Check source, multiline, index, retention
                                                       |
                                                       +-- Yes --> Check query, time range, read permissions
```

Avoid debugging by scattering `System.out.println` throughout business code. When logging configuration has issues, identify **which layer is failing** and inspect from logger down to collector.

## 16. Practice Exercises

### Exercise 1 — Reading a Pattern

Given:

```text
%level|%logger{0}|%msg%n
```

and the event:

- Logger: `com.example.orders.OrderService`
- Level: `WARN`
- Message: `event=inventory.low remaining=2`

**Expected output** in Logback:

```text
WARN|OrderService|event=inventory.low remaining=2
```

Reason: `%level` prints the level, `%logger{0}` shortens the logger name, `%msg` prints the message, and `%n` ends the line.

### Exercise 2 — Distinguishing Template and Pattern

Suppose the Java code is:

```java
log.info("order={} status={}", "O-17", "CREATED");
```

and the pattern is:

```text
[%level] %msg%n
```

**Answer:** the message is `order=O-17 status=CREATED`; the layout output is:

```text
[INFO] order=O-17 status=CREATED
```

`{}` belongs to the message template; `%level` and `%msg` belong to the layout.

### Exercise 3 — Adding a Correlation ID

Update the Logback configuration to display `trace_id` right after the level. For an event with MDC `trace_id=tr-42`, for example:

```xml
<pattern>%level|trace=%X{trace_id}|%msg%n</pattern>
```

When request processing finishes, what must you do? **Hint:** clean up MDC in `finally` or an equivalent lifecycle hook; verify context propagation across thread pools.

### Exercise 4 — Why Are Full-String Tests Brittle?

The pattern:

```text
%d{HH:mm:ss.SSS} [%thread] %msg%n
```

changes with time and thread. **Hint:** assert stable components, valid timestamp format, and logger name/event code as needed. Do not compare the whole string against a hard-coded timestamp.

### Exercise 5 — Text Logs vs. JSON

A team wants to query `error_code` as a separate field, but currently only prints `error_code=...` inside `%msg`. What should they do?

**Hint:** use structured logging/an appropriate JSON encoder and verify the collector parses the field properly. Text patterns aid readability but do not create typed fields automatically.

### Exercise 6 — Missing Stack Trace

`log.error("failed", exception)` was called, yet the centralized UI shows no stack trace. Can you conclude this is caused by omitting `%ex` from the pattern?

**Hint:** No. Check whether the event has a Throwable, the actual layout/encoder, the backend's automatic exception-appending behavior, multiline/parser settings, size limits, and collector permissions/queries.

### Exercise 7 — Security

A message contains dummy data: `token=SECRET_TEST_TOKEN_123`, and the pattern prints `%msg`. Is it automatically safe because parameter substitution was used?

**Hint:** No. Strip/mask sensitive data before emitting the event or use a verified control mechanism; test across all appenders/encoders, including exceptions and MDC. Avoid putting real tokens in tests.

## 17. Checklist for Real-World Projects

1. **Identify the backend:** Logback, Log4j 2, or JUL? Are the runtime provider and configuration filename correct?
2. **Define the purpose:** developer console, operations file, or collector? Are humans or machines the primary readers?
3. **Select fields:** timestamp with date/timezone, level, logger/service, event code, message, trace/request ID, and Throwable where appropriate.
4. **Design boundaries:** delimiters, alignment, newlines, multiline; avoid relying on spaces for automated parsing.
5. **Verify encoding:** UTF-8 from encoder through file/console to collector.
6. **Separate text and structured:** if querying many fields, choose a dedicated JSON encoder/layout and verify data types.
7. **Enforce privacy:** never log tokens, passwords, card data, or sensitive payloads in any branch.
8. **Test with sample events:** INFO/WARN/ERROR, with and without MDC, Unicode messages, exceptions, and special characters.
9. **Check performance and volume:** avoid heavy patterns, duplicate logs, excessive stack traces, and full queues.
10. **Verify operations:** appender and collector receive properly, parser does not misparse, and retention/read permissions are appropriate.

**Conclusion:** A pattern layout is how you control the **presentation** of a logging event. Distinguish **`{}` in messages**, **`%conversion` in layouts**, and **typed fields in structured logging**; then verify levels, event sources, MDC, Throwables, charsets, and final output so logs are both readable and useful during investigations.
