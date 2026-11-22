# Logger Formatting in Java Logging: Logger Name, PatternLayout, and Formatter

## 1. What is logger formatting?

When a Java application calls `logger.info(...)` or `logger.error(...)`, the logging system needs to decide **how the record will be presented**. A good log line contains not only the message, but also **the source (logger name), severity level, timestamp, thread, context, and outcome**.

The same event can be displayed in multiple formats:

```text
INFO Order accepted
```

```text
2026-01-12 09:30:12.347 INFO [http-1] com.example.checkout.OrderService - event=order.accepted orderId=ord-17
```

```json
{
  "timestamp": "2026-01-12T09:30:12.347Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "http-1",
  "event": "order.accepted",
  "orderId": "ord-17"
}
```

These are **illustrative examples**; timestamps and IDs are sample data, not the default output of every backend.

In this lesson, **“logger formatting”** covers choosing how to represent the **Logger name** and the attributes of a logging event. It is important to distinguish three questions:

1. **Who emitted the log?** The Logger name is usually based on the package/class or a stable functional name.
2. **How is the event created?** Code provides the level, message, parameters, and throwable/context.
3. **How is the event output?** The backend's `Formatter`, `Layout`, and `Encoder` determine the final string.

Do not confuse formatting with filtering conditions: changing `%logger` or `%msg` does not make a Logger automatically enable DEBUG. Levels/filters and the Handler/Appender pipeline still determine whether an event reaches the output destination.

The learning goal is to be able to use **Logback PatternLayout**, understand `LoggerFactory.getLogger`, the difference between a **message placeholder** and a **layout pattern**, full/shortened logger names, UTC/timezone, MDC, throwables, structured logging, and how to compare them with **JUL SimpleFormatter**.

## 2. Data flow: from Logger to log line

In an application using SLF4J and Logback:

```text
Source code
    LoggerFactory.getLogger(PaymentService.class)
    logger.warn("event=retry attempt={}", 2)
                     |
                     v
               SLF4J API
                     |
                     v
              Logback Logger
               check level
                     |
                     v
               LoggingEvent
       logger name / level / thread / message
       timestamp / marker / MDC / throwable
                     |
                     v
          Appender + Filter
                     |
                     v
          Encoder + Layout
      PatternLayout or JSON encoder
                     |
                     v
        stdout / stderr / file / collector
```

The **Logger** provides the name and receives the event. The **Logging event** holds the event's data. The **Layout** turns event attributes into text; the **Encoder** converts text/events into data sent to the output destination. In Logback, configuring `PatternLayoutEncoder` (typically via an `<encoder><pattern>...</pattern></encoder>` block) is the common way to produce text logs.

One Appender can use a different format from another Appender. For example, the console may need a concise line, while a file/collector needs more fields. If an event goes to both, **the Logger name and level in the event do not change**, though their representation may differ.

With **`java.util.logging` (JUL)**, the corresponding components are `Logger` → `LogRecord` → `Handler` → `Formatter`. Do not put Logback's `%logger` syntax directly into JUL's `logging.properties` file: each formatting system has its own API and syntax.

## 3. Naming Loggers stably and meaningfully

A common declaration style is to name the Logger after the class:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
```

This is a **code snippet placed in the `PaymentService` class**. `getLogger(PaymentService.class)` usually uses the fully qualified class name, such as:

```text
com.example.payment.PaymentService
```

You can also name it explicitly by subsystem:

```java
private static final org.slf4j.Logger AUDIT =
        org.slf4j.LoggerFactory.getLogger("com.example.audit");
```

Both approaches are valid if there is a convention. However, a Logger name should be **stable and not change per request**. Avoid:

```java
// DO NOT create a separate Logger name for each request.
LoggerFactory.getLogger("payment.request." + requestId);
```

This snippet illustrates an anti-pattern, assuming `requestId` is available. That approach causes the number of Loggers to grow with dynamic data, makes configuring the Logger hierarchy difficult, and increases operational complexity. A request ID should be a field in the log or MDC, not part of the Logger name.

### 3.1. Logger name vs. code call site

- **Logger name**: the value chosen by `LoggerFactory.getLogger(...)`, for example `com.example.payment.PaymentService`.
- **Source class/method/line**: the actual code location that called the logger, if the backend has a mechanism to look up the caller.
- **Thread name**: the thread that emitted the event, not the class name.
- **Message**: the event content after parameters are formatted.

In particular, a `LoggingHelper` class might use a Logger named after a subsystem, so **the logger name is not necessarily the class of the line of code that just called log**. If you want accurate caller data, you must check the API/backend/wrapper and weigh the cost of stack inspection; do not infer it solely from the Logger name.

### 3.2. Full and shortened Logger names

Logback PatternLayout supports:

```text
%logger       -> Full logger name
%logger{0}    -> Name segment to the right of the last dot
%logger{36}   -> Attempts to shorten the Logger name to a character limit
```

For example, with the Logger name:

```text
com.example.payment.PaymentService
```

`%logger` outputs the full name; `%logger{0}` outputs `PaymentService`.

With `%logger{36}`, Logback uses an algorithm to abbreviate package segments to preserve the important identifying parts. **The length is not an arbitrary string truncation**; depending on the actual name, the result might not hit the exact target character count if it cannot be shortened further while still preserving the final segment. Do not assume a single fixed shortened output for every Logger name.

**Important note:** `%logger{0}` or `%logger{36}` only changes **how it is displayed**; it does not change `ILoggerFactory`, the Logger instance, level inheritance relationships, or the original Logger name in the event. When investigating large systems, overly short names can cause collisions between classes with the same name in different packages; choose an abbreviation length sufficient to distinguish the source.

## 4. Logback PatternLayout: the presentation language

**PatternLayout** is a tool for formatting log text according to a pattern string. Each conversion specifier starts with `%` and extracts a piece of data from the logging event.

Example:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

Illustrative output:

```text
09:30:12.347 INFO  [main] c.e.payment.PaymentService - event=payment.completed
```

This illustrative output depends on the Logger name and timestamp; it is not a fixed output for every application.

### 4.1. Key conversion words

| Pattern | Meaning | Notes |
| --- | --- | --- |
| `%d{pattern}`, `%date{pattern}` | Event timestamp | Timezone can be configured using Logback syntax |
| `%level`, `%p` | Event level | TRACE/DEBUG/INFO/WARN/ERROR |
| `%-5level` | Left-aligned level, minimum width 5 | INFO has one padding space |
| `%logger`, `%c` | Logger name | Full name by default |
| `%logger{0}` | Last segment of the Logger name | Easy to read, but can collide |
| `%logger{36}` | Shortened Logger name | Preserves more package information |
| `%thread`, `%t` | Name of the thread creating the event | Do not use in place of request/trace ID |
| `%msg`, `%message` | Formatted message | SLF4J arguments are substituted into the message |
| `%X{requestId}` | MDC value by key | May be empty if context has not been attached |
| `%ex`, `%exception`, `%throwable` | Throwable/stack trace | Format depends on options, can be multi-line |
| `%class`, `%method`, `%line` | Caller information | Often expensive due to stack inspection |
| `%n` | Platform-specific line separator | Prefer over hardcoded newline characters |

In `%logger{36}`, the number in curly braces is a **conversion word option**. In `%-5level`, `-5` is a **format modifier** for left alignment and width. The two types of options serve different roles.

### 4.2. Column alignment, width, and delimiters

```text
%-5level [%thread] %logger{36} - %msg%n
```

`%-5level` produces, for example:

```text
INFO  [main] ...
WARN  [main] ...
ERROR [main] ...
```

There are **two spaces** after INFO/WARN in the example because of one padding space from `%-5level` and one literal space in the pattern. ERROR is 5 characters long, so only the literal space remains.

Fixed width makes text logs easier to scan visually, but it is not a fixed schema for positional machine parsing: thread names, logger names, and messages have variable lengths. If you need automated querying/aggregation, use structured fields instead of a column-based parser.

### 4.3. Inserting literals and parsing rules

A pattern can contain literal text for labels:

```text
level=%level logger=%logger thread=%thread message=%msg%n
```

The output will include labels like `level=`, `logger=` instead of just values. This is good for human readers, but **does not automatically solve escaping** for messages containing spaces, newlines, or external data.

When a literal immediately follows a conversion word without a separator, the parser may misinterpret the literal as part of the conversion name. Use spaces/delimiters or appropriate option syntax, and test the pattern in practice. Do not put shell expressions like `$\{...\}` or SLF4J placeholders directly into a pattern without understanding the backend's variable substitution engine.

## 5. Distinguishing message formatting from log line formatting

These two layers are very easy to confuse:

**Layer 1 — Message template in source code:**

```java
logger.info("event=order.created orderId={} items={}", "ord-17", 3);
```

This is an illustrative snippet assuming an SLF4J `logger` is already available. The `{}` is SLF4J's **parameterized message placeholder**. The processed message is:

```text
event=order.created orderId=ord-17 items=3
```

**Layer 2 — Backend pattern:**

```text
%-5level %logger{0} - %msg%n
```

If the Logger is `com.example.order.OrderService` and the level is INFO, the line output according to the pattern is:

```text
INFO  OrderService - event=order.created orderId=ord-17 items=3
```

The same record can be presented differently if an Appender uses a different pattern, **but the underlying message/event remains the same event**.

Do not confuse SLF4J's `{}` with JUL/`java.text.MessageFormat`'s `{0}`, `{1}`, and do not confuse either with Logback PatternLayout's `%msg`, `%logger`. These are three syntaxes at different layers.

### 5.1. Keep messages short and event names stable

Log events in a way that is easy to categorize:

```java
logger.warn("event=payment.retry errorCode={} attempt={}",
        "GATEWAY_TIMEOUT", 2);
```

Variable values should be placed in parameters or structured fields to minimize manual string construction and preserve queryability. Do not concatenate dynamic Logger names or event names like `"event=payment.retry." + requestId`; use a separate `requestId` instead.

### 5.2. Placeholders do not make expensive computations lazy

```java
logger.debug("state={}", calculateExpensiveSnapshot());
```

This is an illustrative snippet; `calculateExpensiveSnapshot()` is still evaluated by Java **before** calling `logger.debug`, even if DEBUG is disabled. When an expression is expensive, consider:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", calculateExpensiveSnapshot());
}
```

Placeholders defer message concatenation/formatting inside the logging framework by design; they do not defer argument evaluation in the Java language.

## 6. Which fields should you format?

An operational log line should typically include:

1. **Timestamp** and an explicit timezone (UTC is recommended if logs are aggregated from multiple hosts).
2. **Level** to prioritize handling.
3. **Service/instance** from configuration if logs aggregate multiple services.
4. **Logger name** long enough to identify the class/module.
5. **Thread** when helpful for concurrency diagnostics, but not as a substitute for a correlation ID.
6. **Request/trace/span ID** when request-scoped context is available.
7. **Message/event name** that is concise and consistent.
8. **Exception** with stack trace according to policy for errors that need investigation.

A common text pattern in Logback applications:

```xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n</pattern>
```

This is an **XML snippet inside an Appender's `<encoder>` block**, not a complete configuration file. It uses the UTC timezone, aligns the level, displays the thread, shortened logger name, ID from MDC, and message.

**Illustrative output:**

```text
2026-01-12 09:30:12.347 WARN  [http-2] c.e.payment.PaymentService requestId=req-42 - event=provider.timeout
```

Clocks, thread names, and Logger names vary across runs. If you need a machine-parseable format, use a **JSON encoder** that supports typed fields instead of this text convention.

### 6.1. Timestamp: event time, not file read time

Logback's `%d` pattern represents the timestamp attached to the logging event. To correlate logs across multiple nodes, you need to standardize the timezone and format; timestamp ordering can be affected by clock skew between hosts. In distributed systems, do not rely solely on timestamps to infer causality: `traceId` and span relationships are more meaningful.

When measuring latency, use a monotonic clock such as `System.nanoTime()` or an equivalent tool; do not take the difference between two wall-clock timestamps if the environment can adjust the clock.

### 6.2. Thread name: useful, but not a request identifier

`%thread` helps you see tasks running on `main`, a thread pool, or an HTTP worker. However, one thread can process multiple requests, and one request can hop across threads. Therefore, `requestId`/`traceId` must be attached explicitly, not inferred from the thread name.

### 6.3. Logger name and event code

`%logger` indicates the source where the Logger was defined in code. `event=payment.failed` in the message or a structured field indicates the **event type**. A Logger named `PaymentService` can emit many events; the `payment.failed` event might come from multiple classes. The two pieces of information complement each other and should not completely replace one another.

## 7. MDC: bringing context into the layout

**MDC (Mapped Diagnostic Context)** is typically provided via `org.slf4j.MDC` and a supporting backend. Example:

```java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", "req-42");
    logger.info("event=request.received");
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

This is a **code snippet**; assume `logger` and `processRequest()` already exist, and the code imports `org.slf4j.MDC`. With the pattern:

```text
%level requestId=%X{requestId} %logger{0} - %msg%n
```

the event will include `requestId` pulled from MDC without the author having to manually append it to every message.

**Scope is critical:** if you do not clear/restore MDC in `finally`, a thread pool can retain the previous request's context and mistakenly attach it to the next request. MDC does not automatically propagate across all `ExecutorService`, `CompletableFuture`, or reactive pipelines; when switching threads, you must capture/propagate/restore context using an appropriate mechanism.

If `requestId` comes from an untrusted HTTP header, validate its length, character set, and origin before putting it into MDC. MDC is not a security boundary: client data containing newlines, tokens, or sensitive payloads can still break log structure or violate policy if output verbatim.

## 8. Standalone runnable Java 17 example: formatting full and shortened Logger names

We use **Java 17 + SLF4J API + Logback Classic** via Gradle. The example has two differently named Loggers:

- `demo.payments.PaymentService`, configured with its own DEBUG level.
- `demo.shipping.ShippingService`, inheriting root INFO.

The `PatternLayoutEncoder` configuration prints **both the full logger name (`%logger`) and its last segment (`%logger{0}`) on the same line**, along with level, thread, MDC `requestId`, and message. Timestamps are omitted so stdout is exactly reproducible.

### 8.1. Directory structure

```text
logger-format-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggerFormatDemo.java
        └── resources/
            └── logback.xml
```

### 8.2. File `settings.gradle`

```groovy
rootProject.name = 'logger-format-demo'
```

### 8.3. File `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LoggerFormatDemo'
}
```

The two versions above are **fixed baselines for the example**, not to be interpreted as the latest releases. In real applications, use supported versions, apply security patches, and maintain consistent dependency management; there should only be **one SLF4J provider** at runtime.

### 8.4. File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level logger=%logger short=%logger{0} thread=%thread requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.payments.PaymentService" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

**XML breakdown:**

- `STDOUT` is a ConsoleAppender writing to `System.out`, rather than relying on the backend's default console target.
- `%-5level` creates a level column with a minimum width of 5 characters.
- `%logger` retrieves the full name; `%logger{0}` retrieves the last segment.
- `%thread` retrieves the thread name when the event is created.
- `%X{requestId}` retrieves the MDC value for the processing thread.
- `%msg` retrieves the message after SLF4J `{}` parameters are resolved.
- `%n` ends the line.
- Root has only one Appender; the payment Logger has its own DEBUG level but no separate Appender. Logs from this branch still propagate to the root Appender via additivity.

### 8.5. File `src/main/java/demo/LoggerFormatDemo.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class LoggerFormatDemo {
    private static final Logger PAYMENT =
            LoggerFactory.getLogger("demo.payments.PaymentService");

    private static final Logger SHIPPING =
            LoggerFactory.getLogger("demo.shipping.ShippingService");

    public static void main(String[] args) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            PAYMENT.info("event=payment.started orderId={}", "ord-17");
            PAYMENT.debug("event=provider.request attempt={}", 2);
            SHIPPING.debug("event=shipping.diagnostic.hidden");
            SHIPPING.warn("event=inventory.low sku={}", "sku-9");
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
```

The Java code only imports SLF4J, with no direct dependency on Logback classes. Logger names are set explicitly to test `%logger` and `%logger{0}`; in real applications, they are usually declared per class using `getLogger(MyClass.class)`.

### 8.6. Compiling and running

In the `logger-format-demo` directory with JDK 17 and Gradle supporting Java 17, run:

```bash
gradle run --quiet
```

If the project includes a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. The file set above **does not include a Wrapper**; running it for the first time requires Gradle/JDK and access to download libraries from the repository.

**Exact stdout emitted by the program with this configuration:**

```text
INFO  logger=demo.payments.PaymentService short=PaymentService thread=main requestId=req-42 - event=payment.started orderId=ord-17
DEBUG logger=demo.payments.PaymentService short=PaymentService thread=main requestId=req-42 - event=provider.request attempt=2
WARN  logger=demo.shipping.ShippingService short=ShippingService thread=main requestId=req-42 - event=inventory.low sku=sku-9
```

**Output explanation:**

1. The `PAYMENT` Logger is explicitly set to DEBUG, so both INFO and DEBUG are accepted.
2. The `SHIPPING` Logger has no explicit level and inherits root INFO. The `SHIPPING.debug` event is filtered out before reaching the Appender.
3. `INFO` and `WARN` are four-letter levels, padded with one space by `%-5level`, plus the literal space in the pattern, resulting in two spaces.
4. `%logger` and `%logger{0}` pull data from **the same event**, but display it in full/shortened forms in two different ways.
5. `%thread` is `main` when the program runs sequentially from the main method.
6. `%X{requestId}` outputs `req-42` on all three lines because the program sets MDC before logging.
7. The `{}` placeholders in the message are replaced by `ord-17`, `2`, or `sku-9`; that is a message formatting feature, **not** `%logger`.
8. Without timestamps, the lines from the application code can be compared directly; any dependency download/build messages emitted by Gradle are not part of the described stdout.

### 8.7. Experiments to try on your own

- **Change `%logger{0}` to `%logger{36}`:** observe how the name is abbreviated by the package algorithm rather than just taking the last segment. Do not assume the output is a left-to-right truncation.
- **Change `<root level="INFO">` to `DEBUG`:** the `SHIPPING.debug` line starts appearing. This is a level change, not a formatting change.
- **Remove `<logger name="demo.payments.PaymentService" level="DEBUG"/>`:** the payment Logger falls back to inheriting INFO; the PAYMENT DEBUG line is dropped.
- **Remove `%X{requestId}` from the pattern:** Java still attaches MDC, but **the text line no longer displays** that ID; context and presentation are two independent layers.
- **Change `%msg` to `%message`:** this is an alias in Logback with the same goal of displaying the message.
- **Change the Logger name in Java without updating the level configuration for that name:** the level override may no longer apply because the Logger name does not match. The Layout is not where level selection rules are fixed.

## 9. Displaying exceptions and stack traces

An error log often needs a structured cause:

```java
try {
    paymentGateway.call();
} catch (RuntimeException ex) {
    logger.error("event=payment.failed orderId={}", orderId, ex);
}
```

This is an **illustrative snippet** with existing variables and `paymentGateway`. In SLF4J, the throwable is passed in the appropriate position so the backend stores it in the event rather than manually concatenating `ex.getMessage()` into the message. Different overloads behave differently, so use the exact API you are targeting.

Logback PatternLayout supports conversion words for exceptions, for example:

```text
%level %logger - %msg%n%ex
```

`%ex` can output a **multi-line** stack trace, including the exception type, message, and frames. Some patterns have options to limit depth, but cutting it too short can lose the failure location. If a pattern does not contain a throwable conversion word, Logback PatternLayout has a default mechanism to append exception information in many configurations; **do not rely on the assumption** that any custom pattern automatically drops stack traces. If an intentional suppression policy is needed, `%nopex` is a dedicated mechanism in Logback, though it should not be used in production when stack traces are still needed for investigation.

For collector systems that ingest one event per line, multi-line stack traces can be split into separate, disconnected events. A better solution is usually to use a structured JSON encoder with a dedicated exception field or configure appropriate multiline parsing. Also limit sensitive data in exception messages, as stack traces can contain URLs, usernames, or parameters included in error messages.

**Exception logging rule:** log the stack trace at an appropriate handling boundary; do not print the same exception at every layer if it adds no diagnostic value. An ERROR event missing a `Throwable` can be hard to investigate, while a pipeline printing duplicate stack traces in many places wastes resources and creates noise.

## 10. Should you print class, method, and line number?

In Logback, conversion words such as `%class`, `%method`, and `%line` can provide call-site information:

```text
%class.%method:%line - %msg%n
```

However, they may require the backend to extract caller data from the stack trace, which is more expensive than retrieving `%logger`. In high-volume, latency-sensitive applications, **avoid enabling caller data globally** unless truly necessary.

When using a wrapper/helper, caller data may point to the helper if the framework or wrapper does not supply the information properly. Do not assume that simply adding `%method` will always capture the intended business caller.

A practical configuration typically uses **logger name + event code + traceId** for tracing first; only add caller class/method/line in environments or debug scopes where needed, after benchmarking.

## 11. How does structured JSON differ from text PatternLayout?

A text pattern:

```text
level=%level logger=%logger requestId=%X{requestId} message=%msg%n
```

helps human readers see labels. However, if the message or request ID contains spaces, quotes, or newline characters, regex-based parsers can fail. A text pattern is still just **a single string**.

Structured JSON uses a schema and proper escaping:

```json
{
  "timestamp": "2026-01-12T09:30:12.347Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "thread": "http-2",
  "service": "checkout",
  "requestId": "req-42",
  "event": "payment.failed",
  "errorCode": "GATEWAY_TIMEOUT",
  "durationMs": 1200
}
```

This is an illustrative example; Logback does not automatically produce this JSON just because you wrote `<pattern>%msg</pattern>`. For observability systems, use a **JSON encoder supported by the backend/framework** that can output fields with proper data types. Depending on the version, the solution may be the framework's built-in structured logging or a third-party encoder. Do not assemble JSON via string concatenation and expect all quotes, Unicode, and control characters to be safely encoded.

### 11.1. Choosing a stable schema

Standardize `timestamp`, `level`, `logger`, `service`, `traceId`, `spanId`, `requestId`, `event`, `errorCode`, `durationMs` as needed. You do not need to include every field in every event, but **the same field must have a consistent type and meaning**.

For example, `durationMs` in JSON should be a number, not sometimes `1200` and other times the string `"1.2s"`. Some tracing systems use `trace_id`/`span_id`; if an internal standard schema already exists, follow that standard instead of inventing variants.

### 11.2. Do not use logger name as an unbounded-cardinality dimension

Package/class-based Logger names are relatively stable and well-suited for diagnosing the source. Do not create dynamic Logger names containing request IDs, user IDs, or order IDs. Those fields have high cardinality and belong in logs/tracing with proper retention and querying policies, rather than being misused as metric labels.

## 12. Comparison with JUL SimpleFormatter

In JUL (`java.util.logging`), record formatting is based on a `Formatter` attached to a `Handler`. `SimpleFormatter` has a configuration property:

```properties
java.util.logging.SimpleFormatter.format = %1$tF %1$tT %4$s logger=%3$s - %5$s%6$s%n
```

This is **a line in the `logging.properties` file**; it uses `java.util.Formatter`/`String.format` syntax, not Logback conversion words. Key arguments:

| `String.format` index | Content provided by SimpleFormatter |
| --- | --- |
| `%1$tF`, `%1$tT` | Event date/time in the system timezone |
| `%2$s` | Source class/method if known; otherwise the logger name |
| `%3$s` | Logger name |
| `%4$s` | Level |
| `%5$s` | Message after `formatMessage(LogRecord)` |
| `%6$s` | Formatted throwable/stack trace if present |
| `%n` | Platform-specific newline |

Example **JUL snippet**:

```java
java.util.logging.Logger julLogger =
        java.util.logging.Logger.getLogger("com.example.payment.PaymentService");
julLogger.log(java.util.logging.Level.INFO, "orderId={0}", "ord-17");
```

JUL uses `{0}` parameter syntax, not SLF4J's `{}`. In Logback, `%logger` retrieves the logger name from the logging event; in JUL SimpleFormatter, `%3$s` retrieves the logger name via the third argument supplied by `SimpleFormatter`. The two format languages are not equivalent, even though their presentation goals are similar.

**JUL's ConsoleHandler typically writes to stderr**. If you want consistent stdout or custom JSON, you need an appropriate Handler/Formatter; simply changing `SimpleFormatter.format` will not turn ConsoleHandler into stdout or change a Logger's level.

## 13. When switching backends, what stays and what must change?

SLF4J keeps the business API relatively independent of the backend, but formatting lives in the implementation. For example, when migrating from Logback to Log4j 2:

- `org.slf4j.Logger` code and `{}` messages can usually be kept if the new provider is compatible.
- `logback.xml` no longer controls the new backend; you must configure it using Log4j 2's system (`log4j2.xml` or an equivalent mechanism).
- Log4j 2 also has a PatternLayout, but do not assume **every conversion word, exception rule, option, and filter** is identical to Logback.
- MDC/ThreadContext and structured fields must be verified against the specific backend/provider.
- Keep only one compatible SLF4J provider on the runtime classpath; avoid bidirectional bridges that create forwarding loops.

Good logger formatting should be defined by an **output contract**: required fields, timezone, logger name length, newline/exception handling, escaping, collector schema, retention, and access control requirements—not just a copied pattern line.

## 14. Common mistakes when formatting loggers

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Log only has the message, unknown emitting class | Pattern lacks `%logger` or Logger name is too short | Add full name or an appropriate `%logger{36}` |
| Two classes in different packages show the same name | Using `%logger{0}` causes shortened names to collide | Use a longer name to avoid losing package info |
| `{ }` appears literally in the message | Wrong API/placeholder used, or arguments passed incorrectly | Check SLF4J `{}` syntax and overload |
| `requestId` is missing despite `MDC.put` | Pattern/encoder does not read MDC, or context was lost on thread switch | Check `%X{requestId}` and propagation |
| `DEBUG` does not appear after changing the pattern | Logger level or filter blocks it | Check level before Formatter/Encoder |
| Putting `%logger` in JUL `logging.properties` | Mistakenly using PatternLayout syntax | Use `SimpleFormatter.format` with `%3$s` or a custom Formatter |
| Log file is missing stack traces | Throwable not passed properly, or layout/encoder handles it improperly | Check `getThrown`/Throwable, `%ex`, and exception policy |
| Stack trace split into multiple records | Multi-line text pattern, collector does not understand multiline | Use a JSON encoder or multiline parser |
| Pattern with `%class`/`%line` slows down the application | Collecting caller data is expensive | Limit caller conversions; prefer `%logger` |
| Log timestamps differ across hosts | Inconsistent timezone/clock configuration | Log explicit timezone, usually UTC; synchronize clocks |
| Editing `logback.xml` has no effect on output | Runtime backend is not Logback, or file is not loaded | Check provider, classpath, and framework config |
| JSON logs fail to parse | Using text pattern with manual JSON concatenation, incomplete escaping | Switch to a reliable JSON encoder |
| Duplicate log lines appear | Appender attached in multiple places or additivity | Check Logger hierarchy and `appender-ref` |
| Sensitive data is leaked | Message/Throwable/MDC contains secrets | Do not log secrets in the first place; filter/allowlist and enforce access control |

### Debugging workflow

1. Verify that the logger call is actually executed and check the actual Logger name.
2. Check the Logger's level/filters to see if the event is accepted.
3. Identify the runtime backend (Logback, JUL, Log4j 2...) and the Appender/Handler receiving the event.
4. Identify the Formatter/Encoder of that specific Appender and the pattern/config file actually loaded.
5. Inspect message parameters, MDC, thread, time zone, and Throwable individually.
6. Compare the actual output against the field contract, then check stdout/stderr/file/collector.
7. If there are multiple Appenders or async logging, check for duplicate events, ordering, buffering, and flushing.

## 15. Performance, security, and operability

**Performance:** shortening logger names with `%logger{n}` is a presentation operation; it will not fix an overloaded logging pipeline. Significant costs usually lie in constructing expensive arguments, capturing caller stacks, formatting exceptions, I/O, queues, encoders, and collectors. Choose a pattern that fits your goal rather than printing as much data as possible.

**Log injection:** user-supplied values may contain newlines (`\\n`), carriage returns (`\\r`), or control characters to forge log entries. Text patterns like `message=%msg%n` do not guarantee that input is properly escaped. Before logging, validate/restrict accepted data, or use a standard JSON encoder and a control-character handling strategy suited to the target system.

**Sensitive data:** do not put passwords, bearer tokens, cookies, private keys, CVVs, sensitive payloads, or unnecessary personally identifiable information into messages/MDC/Throwables. Masking configured at the layout level does not guarantee catching every secret; it is best to exclude them at event creation time.

**Operability:** if writing to stdout in containers, the format should match the collection system. If writing to files, configure rolling/retention and write permissions. A Formatter/Encoder does not guarantee that a record is durably persisted: async queues, crashes, full filesystems, or collector failures can still drop events. Critical audit events require a dedicated storage mechanism meeting their durability requirements.

## 16. Logger formatting design checklist

- [ ] Logger name is stable, by class/package or subsystem; does not contain dynamic request IDs.
- [ ] Level and message/event code are clear; Logger/Appender filtering is configured independently of formatting.
- [ ] `%logger`, `%logger{0}`, and `%logger{n}` are chosen according to package disambiguation needs.
- [ ] SLF4J `{}` placeholders, JUL `{0}` placeholders, and Logback PatternLayout `%...` specifiers are properly distinguished.
- [ ] Timestamp has an explicit format/timezone, typically UTC across multiple hosts.
- [ ] Thread name and request/trace ID are included when needed, without treating thread name as request ID.
- [ ] MDC is propagated and restored properly across execution scopes, especially thread pools/async.
- [ ] Throwables have a stack trace output policy so investigative error details are not lost.
- [ ] If structured logs are needed, a proper JSON encoder/schema is used instead of faking JSON with string concatenation.
- [ ] Secrets are not logged; dangerous characters, retention, and access control are managed.
- [ ] Output is tested with INFO, DEBUG, WARN, ERROR, events with MDC, events with exceptions, and multiple differently named Loggers.
- [ ] The actual backend, Appender/Handler, stdout/stderr, and collector are verified.

### Official documentation

- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): `PatternLayout`, conversion words, formatter modifiers, MDC, and caller data.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): Logger hierarchy and configuration loading.
- [SLF4J Manual](https://www.slf4j.org/manual.html): API facade, parameterized logging, logger naming.
- [JDK 17 — SimpleFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html): `String.format` arguments and the `SimpleFormatter.format` property.
- [Apache Log4j — Layouts](https://logging.apache.org/log4j/2.x/manual/layouts.html): distinguishing PatternLayout and structured layout options.

**Conclusion:** Good logger formatting lets readers see **the source, severity level, timestamp, context, and nature of an event** without modifying business logic. In Logback, `%logger` displays the full name, `%logger{0}` displays the last segment, and `%logger{n}` abbreviates the name to keep logs concise. Combining them properly with `%level`, `%thread`, `%X`, `%msg`, timestamps, and Throwables produces records that are easy to investigate; when large-scale machine analysis is needed, prefer a proper JSON schema and encoder.
