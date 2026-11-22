# Logback Layout: Formatting Log Records with PatternLayout

## Learning Objectives

In Logback, the same event can be output as a concise console line, a file line with full timestamp and logger information, or a format tailored for log collection tools. This lesson helps you understand **what a Layout does, the relationship between Layout and Encoder**, how to read and design **PatternLayout**, configure **logback.xml**, handle MDC, exceptions, and caller information, and verify the readability, safety, and stability of log formats.

After this lesson, you will be able to:
- Distinguish **logging event, Layout, Encoder, and Appender** and the position of each component in the pipeline.
- Use common conversion words: **%d, %level, %thread, %logger, %msg, %n, %X, %ex**.
- Explain and fix errors in patterns with extra/missing fields, padding, timestamps without timezones, or misinterpreted exception information.
- Configure a **Java 17 + SLF4J + Logback Classic** example with Maven and accurately predict the log lines.
- Adjust patterns for local and production environments; consider data structure, multiline logs, MDC, security, performance, and log collection systems.

This lesson belongs to the **Logback** group of Java Core Logging. The content focuses on **Logback Layout**, rather than turning into a general guide for all logging frameworks.

## 1. What Is a Layout?

A **Layout** is a component that converts **a logging event** into **a String** according to a specified format. In Logback Classic, the most commonly used layout is **ch.qos.logback.classic.PatternLayout**. It reads information from the event and uses a **conversion pattern** to determine the order, presentation, width, and fields that appear.

For example, suppose the application emits an event with:
- Level: INFO.
- Logger: com.example.checkout.OrderService.
- Thread: main.
- Formatted message: order.created orderId=OD-42 items=2.
- MDC requestId: req-42.

A Layout with the pattern:

~~~text
%level | requestId=%X{requestId} | %msg%n
~~~

Can produce the line:

~~~text
INFO | requestId=req-42 | order.created orderId=OD-42 items=2
~~~

The text **requestId=**, the **|** character, and the spaces are **literal text** written directly in the pattern. **%level**, **%X{requestId}**, and **%msg** retrieve the level, MDC value, and message, respectively. **%n** adds the platform-appropriate newline character.

A Layout **does not decide whether an event occurs, whether a level is allowed to be output, or which file the log should be written to**. It only describes **how to represent** the information already present in the event. Logger, level/filter, and Appender handle the other responsibilities.

## 2. Distinguishing Logging Event, Layout, Encoder, and Appender

Conceptual pipeline:

~~~mermaid
flowchart LR
    A["Java code calls Logger"] --> B["Level / Filter"]
    B --> C["ILoggingEvent"]
    C --> D["Appender"]
    D --> E["Encoder using PatternLayout"]
    E --> F["Bytes"]
    F --> G["Console or file"]
~~~

The diagram focuses on responsibilities and does not describe the entire asynchronous mechanism or internal error handling of each appender.

| Component | Receives | Produces / Responsibility |
| --- | --- | --- |
| **Logger** | Log call from code | Checks level and sends the event to the appropriate appender |
| **ILoggingEvent** | Data of the log call | Holds level, message, arguments, timestamp, logger, MDC, Throwable... |
| **Layout** | Logging event | A **String** representing the event |
| **Encoder** | Logging event, using layout/encoder logic | A byte sequence to write to an OutputStream; determines charset, header/footer if supported |
| **Appender** | Logging event | Writes to a destination such as console/file/network and manages resources |
| **PatternLayout** | Logging event + pattern | Customized string based on conversion words |
| **PatternLayoutEncoder** | Logging event | Uses PatternLayout and then encodes into bytes |

**Key characteristic of modern Logback:** when configuring **ConsoleAppender**, **FileAppender**, or **RollingFileAppender**, you typically provide an **Encoder**, rather than attaching PatternLayout directly as the byte output. **PatternLayoutEncoder** is the most convenient and common way to use PatternLayout.

Easy to remember:
- **Layout returns a String**: how is the event presented?
- **Encoder returns bytes**: how is the string encoded for output?
- **Appender writes bytes / dispatches the event to a destination**: where does the log go?

In XML configuration, an **encoder** element containing a **pattern** does not mean Layout has disappeared; PatternLayoutEncoder wraps the PatternLayout mechanism. You can use **LayoutWrappingEncoder** when you need to wrap a custom Layout, though most applications only need PatternLayoutEncoder.

## 3. How Is a Conversion Pattern Read?

PatternLayout treats **%** symbols as the start of a *conversion specifier*. A specifier can have:
- **Format modifier**: width and alignment, such as **%-5level**.
- **Conversion word**: field name, such as **level**, **logger**, **thread**, **msg**.
- **Option in curly braces**: for example **%logger{36}** or **%d{HH:mm:ss.SSS}**.
- **Literal text**: other characters kept as-is, such as spaces, square brackets, colons, hyphens.

Example:

~~~text
%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n
~~~

Meaning in order: timestamp; thread name in square brackets; level left-aligned with a minimum width of five characters; logger name abbreviated according to rules; separator; message; newline.

Do not read the names **logger**, **thread**, **msg** as fields of a JSON object. These are pattern **conversion words**; the final output is still plain text unless the encoder is designed to produce a structured format.

### Common Conversion Words

| Pattern | Role | Notes |
| --- | --- | --- |
| **%d{HH:mm:ss.SSS}** | Event timestamp according to pattern | Should specify timezone when aggregating logs across multiple systems |
| **%level** / **%p** | INFO, DEBUG, WARN, ERROR... | Logback Classic uses Logback's level names |
| **%-5level** | Level left-aligned in a minimum 5-character field | INFO has a trailing space padding; ERROR does not |
| **%thread** / **%t** | Name of the thread where the event was created | Not requestId; thread pools reuse threads |
| **%logger** / **%c** | Full logger name | Helps trace the source module or class |
| **%logger{36}** | Logger name abbreviated to a desired length | Does not guarantee the string is exactly 36 characters in all cases |
| **%msg** / **%message** / **%m** | Formatted message | Data from arguments can appear here |
| **%n** | Platform newline separator | Should be used instead of hardcoding a newline string |
| **%X{requestId}** | Value of requestId in MDC | If the key is missing, usually outputs an empty string |
| **%X{requestId:-none}** | Retrieves requestId or a fallback value when missing | Pay attention to the exact key and how MDC is propagated |
| **%ex{short}** | Top part of the Throwable's stack trace | Does not replace the entire cause chain |
| **%ex{full}** | Full stack trace according to the formatter mechanism | Log lines can become multiline |
| **%caller{1}** | One level of caller information | Incurs stack lookup cost; enable only when needed |

Example of a compact pattern:

~~~text
%-5level [%thread] %logger{36} requestId=%X{requestId:-none} - %msg%n
~~~

A record might become:

~~~text
INFO  [main] c.e.checkout.OrderService requestId=req-42 - order.created orderId=OD-42
~~~

This is an **illustration**: the length/abbreviation of the logger and thread names depends on the actual record. When you need deterministic output for testing, remove timestamps, caller info, and variable name abbreviation.

### Format Modifiers and Literal Text

**%-5level** means a **minimum** width of five characters, left-aligned. **%5level** means right-aligned in a minimum width of five characters. This is not a maximum limit or a truncation guarantee.

You can place text like **level=**, **service=checkout**, brackets, or separators anywhere in the pattern. However, if you place a sequence of letters immediately after a conversion word without a separator, the parser may misinterpret it as a longer converter name. Use spaces, separator characters, or documented syntax to avoid errors such as **%PARSER_ERROR[...]**.

The **%** sign has special meaning. If you genuinely need a literal percent sign, you must escape it according to Logback's pattern rules; in an XML file, you must also distinguish between XML escaping and pattern escaping.

## 4. PatternLayout and PatternLayoutEncoder

**PatternLayout** belongs to Logback Classic and processes an event to produce a String. **PatternLayoutEncoder** is designed to use PatternLayout and then convert the result into bytes according to a charset, such as UTF-8.

Typical console configuration:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | requestId=%X{requestId} | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Each tag in the configuration has a specific function:

1. **configuration** is the root element of the Logback configuration.
2. **appender CONSOLE** writes to the console; no FileAppender is needed if you only want to view the terminal.
3. **encoder** uses PatternLayoutEncoder to generate bytes. **charset UTF-8** ensures Vietnamese or non-ASCII data has a clear encoding.
4. **pattern** defines the log line format. **%X{requestId}** retrieves the MDC value if the application has provided it.
5. **root level=DEBUG** allows DEBUG, INFO, WARN, and ERROR according to Logback's threshold hierarchy.
6. **appender-ref** attaches the appender to the root logger.

Logback typically looks for **logback-test.xml** or **logback.xml** on the classpath, according to its configuration mechanism. In a standard Maven project, place **logback.xml** in **src/main/resources** so that this resource is placed on the classpath when running the application.

**Note:** Do not confuse Logback's **logback.xml** with `java.util.logging`'s **logging.properties**. The two systems have different syntaxes and control mechanisms. Also do not confuse **SLF4J's Logger** with **java.util.logging.Logger**.

## 5. Java 17 Hands-On: A Logback Program with a Clear Layout

This exercise produces three log lines sharing a common **requestId** via **MDC**. The pattern uses only stable fields for easy comparison. You need JDK 17 or higher, Maven, and the ability to download dependencies from Maven Central or your learning environment's Maven repository.

### Project Structure

~~~text
logback-layout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LayoutDemo.java
        └── resources/
            └── logback.xml
~~~

### pom.xml File

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>logback-layout-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The example pins **Logback Classic 1.5.18** so that the steps are consistent; this is the version used in the lesson, not a claim about the latest release. Logback Classic pulls in compatible dependencies, including the SLF4J API. In real projects, follow your project's BOM/version management and security policies, and avoid declaring multiple SLF4J providers at the same time.

### src/main/resources/logback.xml File

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | requestId=%X{requestId} | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

### src/main/java/com/example/logging/LayoutDemo.java File

~~~java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LayoutDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LayoutDemo.class);

    public static void main(String[] args) {
        MDC.put("requestId", "req-42");
        try {
            LOG.info("order.created orderId={} items={}", "OD-42", 2);
            LOG.debug("cache.lookup result={}", "miss");
            LOG.warn("payment.retry attempt={}", 2);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

### Compile and Run

In the directory containing **pom.xml**, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.logging.LayoutDemo
~~~

The log lines from the program will have the **exact** content below (excluding any Maven-specific or environment messages):

~~~text
INFO | requestId=req-42 | order.created orderId=OD-42 items=2
DEBUG | requestId=req-42 | cache.lookup result=miss
WARN | requestId=req-42 | payment.retry attempt=2
~~~

Explanation:

- **LoggerFactory.getLogger(LayoutDemo.class)** retrieves the SLF4J logger for the class. The Logback backend handles the event when bound as the provider.
- **MDC.put(...)** attaches `requestId` to the current logging context. **%X{requestId}** causes each line to be printed with the same value `req-42`.
- **LOG.info(..., arguments)** and **LOG.debug(...)** use **SLF4J's {} placeholders**, which are replaced in argument order; this is **not** `java.util.logging`'s **{0}, {1}** syntax.
- **root DEBUG** allows DEBUG to be output. If you change root to INFO and have no child logger override, the DEBUG line will be filtered out; the two INFO/WARN lines will still be output.
- **%level** does not add padding, so the output has INFO, DEBUG, WARN exactly as shown. **%msg** retrieves the formatted message; **%n** adds a newline.
- **finally** calls **MDC.remove** so `requestId` is not retained after processing. In real applications with thread pools, cleaning up the context is even more critical because threads are reused.

The program **does not intentionally throw an exception** and has no timestamp in the pattern, so the exercise lines do not depend on the date/time of execution. Actual Maven output or warnings if the environment is misconfigured should not be considered fixed demo output.

## 6. Designing Patterns for Development and Operations

**Local/development** usually prioritizes brevity, readability, and essential debugging information:

~~~text
%-5level [%thread] %logger{36} requestId=%X{requestId:-none} - %msg%n
~~~

This format shows the level, thread, logger, requestId if present, and message. It is not necessary to print every attribute of the event when reading in an IDE.

**Files or backends collecting from multiple services** need clear timestamps, service identity, and correlation IDs. Illustrative pattern:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level [%thread] %logger{36} traceId=%X{traceId:-none} - %msg%n
~~~

Information to consider:

- **Timestamp:** include an explicit timezone when merging logs from multiple machines. With a UTC convention, you can specify the timezone in `%d`'s option. Do not assume all system clocks are perfectly synchronized.
- **Logger:** the logger name helps locate the code; abbreviate just enough to reduce screen clutter while still distinguishing classes.
- **Level:** helps spot anomalies, but an INFO log might still contain an HTTP 503 completion event; log level does not replace checking business outcomes.
- **Thread:** helps debug concurrency, but thread pools reuse threads, so you need requestId/traceId to correlate by request.
- **MDC:** provides requestId, traceId, or allowed tenant ID; missing context must be handled clearly.
- **Message:** should include an event name and values with units such as `durationMs`, `attempt`, `items`; do not dump entire request objects.
- **Exception:** preserve context and the Throwable when genuinely needed for investigation.
- **Charset:** use UTF-8 to avoid garbled characters when converting to bytes, sending through a collector, or reading on another operating system.

**Text-based Layout is only one option.** If the system needs exact field filtering, aggregation, and correlation via JSON, a **structured JSON encoder** is more appropriate than manually assembling JSON with PatternLayout. Text patterns containing delimiters in user data can cause parsers to split incorrectly; with a JSON encoder, fields must be properly escaped and serialized with their correct types.

## 7. MDC in Layout: Putting requestId/traceId on Every Line

**MDC (Mapped Diagnostic Context)** allows attaching contextual data to the logging execution context so the pattern can extract it via **%X{key}**. In Logback Classic, MDC is typically thread-bound; do not assume it automatically follows all asynchronous work.

Example:

~~~java
// Illustrative snippet; LOG is an already declared SLF4J Logger.
MDC.put("requestId", "req-92");
try {
    LOG.info("event=payment.started");
    LOG.info("event=payment.completed status=success");
} finally {
    MDC.remove("requestId");
}
~~~

If the pattern contains **requestId=%X{requestId}**, both lines can display the same `requestId`. If the key is absent, **%X{requestId}** prints an empty string; to show a fallback value, use **%X{requestId:-none}** according to Logback syntax.

Avoid dumping the entire MDC indiscriminately when it may contain internal/sensitive fields. Instead of using a converter without selecting keys, explicitly list the allowed keys that have diagnostic value.

**Be careful with thread pools and async:** if task A sets `requestId` and fails to clear it, task B running on the same thread later may read the wrong context. If work moves to an `Executor`/`CompletableFuture`/message consumer, you must propagate the context using your project's mechanism and clean it up afterward. MDC does not automatically guarantee correct propagation across all threads, and a pretty pattern cannot fix context data that is already wrong.

## 8. Exceptions and Stack Traces: Avoid Mistaking One Line for One Record

When calling:

~~~java
// Illustrative snippet; assume LOG and Throwable ex already exist.
LOG.error("payment.failed orderId={}", "OD-42", ex);
~~~

Logback can attach a Throwable proxy to the event. When PatternLayout has a conversion word that handles exceptions, such as **%ex{short}** or **%ex{full}**, the layout can append the stack trace as configured.

Example of an intentional pattern:

~~~text
%level %logger{36} - %msg%n%ex{full}
~~~

With a Throwable, a single event can produce **multiple lines of text**. Do not count each stack trace line as an independent event during analysis. If the collection system ingests line by line, you must configure multiline handling or, better yet, use a structured encoder for the exception field.

**Easily overlooked detail:** in Logback PatternLayout, if the pattern does not contain an exception-handling conversion word, Logback Classic usually appends a stack trace output mechanism automatically so error information is not lost. Therefore, simply writing **%msg%n** does not guarantee exceptions will be hidden. The **%nopex** conversion word can disable automatic exception output, but it should not be used to hide errors just because logs are long; prefer adjusting logging policies and where logs are written.

**Caller information** such as **%class**, **%method**, **%file**, **%line**, or **%caller{1}** can be useful when investigating a hard-to-find call site. However, collecting caller data may require stack inspection and is **expensive**. Only add it when helpful, especially in high-load systems. Do not confuse **%logger** (logger name) with **%class** (caller class).

## 9. Layout in FileAppender and RollingFileAppender

FileAppender still uses an Encoder just like the console. A standalone configuration for a file:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>application.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

This is an **independent alternative configuration** for file logging—do not paste it into the console example file without deliberately merging the elements. The application must have write permissions in the working directory. When using FileAppender or RollingFileAppender, the **Encoder determines the byte content of each record**, while the **Appender/rolling policy** determines the file, rotation, and data management.

**RollingFileAppender** adds the ability to roll files by time or size, depending on the rolling policy. Settings like `fileNamePattern` in the rolling policy are for **naming archive files**, which is different from **PatternLayout**'s pattern for **record content**. Do not confuse the two types of patterns when editing configurations.

In production, you must also consider file read permissions, retention, backups, disk space, the risk of logs being retained too long, and collection/ingestion mechanisms. Looking good on the console does not mean the format is suitable for the backend.

## 10. Customizing Layout and Conversion Words

**PatternLayout** lets you reorder fields, add literal text, widths, and formatters without writing Java code. Most text log presentation tasks should start by adjusting the pattern.

For custom requirements, Logback supports **custom converters** to compute a new value from `ILoggingEvent` and then use a custom conversion word in the pattern. This approach is usually cleaner than replacing the entire Layout just to add one field. However, you need to register the converter in the configuration and manage version compatibility.

If the format is completely different (for example, a binary protocol or schema-validated JSON), consider an **appropriate Encoder** rather than concatenating JSON strings in PatternLayout. `LayoutWrappingEncoder` can be used to integrate a special Layout when an Appender requires an Encoder.

Some auxiliary converters:
- **%highlight(...)** colors output by level, useful in terminals that support ANSI; do not assume every file or collector understands color codes.
- **%replace(...)** can replace part of a message using a regex for formatting or masking data; control its cost and do not treat regex as a complete security measure.
- **%caller{1}** helps trace the call site but consumes more resources than built-in fields like `%logger`.
- **%X{key:-default}** sets a fallback value when MDC is missing a key, avoiding a series of empty strings that are hard to parse.

If a pattern prints the same information multiple times—for example, logging `requestId` in MDC and also concatenating `requestId` in the message—consider choosing one consistent convention to avoid duplicate data and increased storage costs.

## 11. Common Mistakes When Configuring Layout

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| Logs appear but in the wrong format | Running the wrong `logback.xml` or config overridden by a framework | Verify which config file is loaded and that the appender/encoder is active |
| Only `%PARSER_ERROR[...]` appears | Invalid conversion word, text directly adjacent to converter, invalid pattern syntax | Check pattern and escaping; refer to supported conversion words |
| `requestId` is missing | MDC not set, wrong key, or context not propagated across async | Check `MDC.put`, key name, and processing lifecycle |
| INFO appears but DEBUG does not | Root/logger level is INFO | Check effective level; Layout does not enable DEBUG on its own |
| Exception prints across multiple lines | Stack trace output by formatter | Use multiline parsing or a structured encoder; do not count each line as an event |
| No stack trace | Throwable not passed, or custom encoder/formatter strips it | Check `LOG.error` call has Throwable and appropriate converter |
| Log lines are too long and hard to read | Printing too many fields or large objects | Select key fields, limit sizes, and use structured logging when needed |
| Duplicate logs | Appender attached to both child and parent logger, inappropriate additivity | Check logger and `appender-ref` configuration; do not just edit the pattern |
| File has garbled non-ASCII characters | Charset / file reader mismatch | Configure UTF-8 and verify charset at every step |
| Color codes appear in raw file | Using color converter for non-ANSI output | Keep color patterns for terminals and clean text patterns for files |
| Log lines lack timezone | Date pattern does not specify zone or data from multiple hosts is mixed | Use an explicit UTC/zone convention and verify clocks |
| Inaccurate stats due to regex/split | Message contains delimiters, spaces, or newlines | Use a schema and structured encoder/parser |

**Security:** A pattern is only a display format; it does not guarantee input data is safe. Do not put passwords, tokens, API keys, cookies, payment details, or private payloads into MDC/messages. Untrusted data can contain newlines or control characters that cause **log injection**. Using `%replace` can assist with masking, but it cannot replace filtering/redaction policies at the source.

**Performance:** Basic timestamp, level, logger, and message are usually cheaper than capturing caller stack info. Regex replacements and complex formatters can increase CPU cost; outputting too many logs still incurs I/O, disk, and ingestion costs. Choose patterns based on reader and storage needs rather than adding every available converter.

## 12. Layout Design and Verification Workflow

When creating a new pattern, follow these steps:

1. **Identify where it will be read**: developer terminal, file on host, centralized tool, or audit pipeline. Each destination has different needs.
2. **Identify required fields**: timestamp with timezone, level, service/logger, event, requestId/traceId, message; choose the minimum needed to answer your questions.
3. **Verify the source of each field**: level/logger are already in the event; `requestId` from MDC must be populated by code or framework.
4. **Choose the Encoder**: `PatternLayoutEncoder` for pattern-based text; a structured encoder if true JSON is needed.
5. **Write a small pattern first**: level, MDC, message, and newline. Run a case with predictable output before adding timestamps or caller info.
6. **Check levels**: with the same pattern, is DEBUG filtered out when logger/root is INFO? Layout cannot recover records that were already filtered.
7. **Check missing MDC**: when `requestId` is not set, choose a default and verify the parser/backend understands it.
8. **Check Throwable**: observe how stack traces are displayed, whether they are multiline, and how the collector splits records.
9. **Check charset and multiple environments**: non-ASCII/Vietnamese characters, Windows/Linux newlines, timezone, ANSI colors, rolling files.
10. **Check cost and sensitive data**: avoid caller data and heavy regexes if they add no value; do not output secrets or personal data.
11. **Document schema conventions**: if field names are queried long-term, pattern changes must be coordinated with dependent dashboards/parsers/alerts.
12. **Re-test after changes**: one normal case, one error case, one case without MDC; avoid duplicate or missing logs across multiple appenders.

## 13. Self-Check Questions

**Question 1.** How do PatternLayout and PatternLayoutEncoder differ?

**Answer:** PatternLayout turns a logging event into a String. PatternLayoutEncoder uses PatternLayout to generate the content and then encodes it into bytes for the appender to write to a stream/file.

**Question 2.** Can you put `<pattern>%msg%n</pattern>` directly under every FileAppender instead of an encoder?

**Answer:** You should not. In modern Logback, file/console-style appenders typically require an Encoder; use `PatternLayoutEncoder` and declare `<pattern>` inside `<encoder>`.

**Question 3.** Why is `%X{requestId}` sometimes empty?

**Answer:** MDC does not have the `requestId` key in the record's execution context, the key name is different, or the context was not properly propagated across threads/async boundaries. You can use `%X{requestId:-none}` to display a fallback, while also fixing the MDC source if it is unexpectedly missing.

**Question 4.** Will changing the pattern cause DEBUG records to appear when the effective level is INFO?

**Answer:** No. The logger/filter decides which records are accepted before the Layout formats them.

**Question 5.** Why can `%caller` cause slowdowns?

**Answer:** It has to extract call-site information from the stack, which is much more expensive than reading fields already present in the event. Enable it only when needed.

**Question 6.** If a Throwable produces five lines of stack trace, are those five separate logging events?

**Answer:** No. A single event can be presented across multiple lines. Parsers/collectors need to recognize record boundaries accurately.

**Question 7.** If the backend needs to query `durationMs` as a numeric type, should you concatenate a JSON string using PatternLayout and assume it is safe?

**Answer:** No. When you need schema-compliant JSON with proper data types, use a structured encoder with proper escaping/serialization; manual concatenation easily breaks when messages contain special characters.

**Question 8.** Why can logs be duplicated even though the pattern only has one `%msg`?

**Answer:** A logger can forward the same event to multiple appenders, including appenders on parent loggers if additivity is enabled. Duplicate records are not necessarily caused by the Layout.

## 14. Technical References

- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): PatternLayout, conversion words, MDC, Throwable, custom converters.
- [Logback Manual — Encoders](https://logback.qos.ch/manual/encoders.html): Layout/Encoder boundaries and PatternLayoutEncoder.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): configuring `logback.xml`, appenders, encoders, and root logger.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): using diagnostic context and the `%X` conversion word.

**Key takeaway:** **Layout decides how a logging event is presented; Encoder converts the representation into bytes; Appender decides the output destination.** With Logback Classic, `PatternLayoutEncoder` is the standard choice for text logs. A good pattern provides just enough information for tracing, stays compatible with parsers/collectors, makes debugging easier, and avoids exposing sensitive data or adding unnecessary overhead.
