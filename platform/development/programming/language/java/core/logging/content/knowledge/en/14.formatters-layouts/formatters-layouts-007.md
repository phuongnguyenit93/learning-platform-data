# Level Formatting in Java Logging: JUL, Logback, and Log4j 2

## 1. What is a level and why format it?

Each log event has a **level** indicating its level of detail or severity. In the console/file, the formatter or layout decides how the level is displayed: `INFO` or `INFO `, `WARNING` or `WARN`, with or without color, before or after the logger name.

Example text output:

```text
INFO  | OrderService | event=order_accepted orderId=ORD-7
WARN  | PaymentClient | event=retry_scheduled attempt=2
ERROR | OrderService | event=order_save_failed orderId=ORD-8
```

The lines above illustrate how output is displayed; the actual logger call syntax, level names, and patterns depend on the logging API/backend.

Three distinct tasks must be separated:

1. **Assigning a level to an event:** `logger.info(...)`, `logger.warn(...)`, `logger.error(...)`, or `java.util.logging.Logger.log(Level.WARNING, ...)`.
2. **Filtering by level:** the logger, filter, or appender/handler decides whether the event is forwarded to its destination.
3. **Formatting the level:** the `Formatter`, `PatternLayout`, or encoder decides how to display the label, padding, color, position, or JSON field for accepted events.

**Changing how `WARNING` is printed to `WARN` does not change the event's original level.** And changing the `%level` pattern cannot make a filtered-out DEBUG event reappear. This is the most important boundary in this lesson.

## 2. Comparing common levels

| Meaning | SLF4J / Logback / Log4j 2 | JUL (`java.util.logging`) |
|---|---|---|
| Very detailed tracing | `TRACE` | `FINER` or `FINEST` have roughly corresponding purposes |
| Debug information | `DEBUG` | `FINE`; `CONFIG` is for configuration information |
| Normal operation | `INFO` | `INFO` |
| Warning, degradation | `WARN` | `WARNING` |
| Serious error | `ERROR` | `SEVERE` |

This table compares **approximate meanings**, not a mandatory mapping standard. Log4j 2 also has `FATAL`; JUL can have custom `Level` values, and `OFF`/`ALL` are used for configuring filter thresholds. Specialized values must be handled intentionally when integrating multiple backends.

In particular, do not infer the level solely from business state: a transient retry might be WARN/DEBUG, whereas a final job failure might be ERROR. Pretty formatting does not replace choosing the right level.

## 3. Text-based level formatting

Level names have different lengths:

```text
INFO     : 4 characters
WARN     : 4 characters
ERROR    : 5 characters
DEBUG    : 5 characters
TRACE    : 5 characters
SEVERE   : 6 characters
WARNING  : 7 characters
```

If printed directly adjacent to a delimiter, columns can become misaligned. **Padding** gives the level a uniform minimum width.

Example of left-alignment in a 7-character-wide column:

```text
INFO    | OrderService | ...
WARNING | PaymentClient | ...
SEVERE  | OrderService | ...
```

For `INFO`, the formatter adds three spaces to reach width 7; the surrounding pattern also adds one space before `|`. For `WARNING`, the name is already 7 characters long, so no padding is added.

### Left-alignment, right-alignment, and truncation

- **Left-aligned**: `INFO␠␠␠` (three spaces after `INFO` when width=7).
- **Right-aligned**: `␠␠␠INFO` (three spaces before `INFO`).
- **Minimum width**: if the label is longer than the width, common formatters still print it in full unless another precision/truncation rule applies.
- **Do not truncate severity names by character count** to turn `SEVERE` into `SEVE` or `WARNING` into `WARNI`; that is not a meaningful level mapping.

The `␠` symbol here is only used to represent **a single space**, not a character that Java must print.

If the output is machine-read, fixed-column formatting can make parsers dependent on whitespace and brittle when patterns change. When querying by severity is needed, prefer structured fields rather than slicing strings at fixed positions.

## 4. JUL: retrieving the level from LogRecord

In JUL, when calling:

```java
LOG.log(Level.WARNING, "event=cache_degraded");
```

the logger creates or processes a `LogRecord` carrying `Level.WARNING`, and then `Handler` and `Formatter` determine the output. Inside `Formatter.format(LogRecord)`:

```java
Level level = record.getLevel();
String levelName = level.getName();
```

These two lines are only an illustration inside a formatter, assuming the `record` variable exists. For standard levels:

- `Level.INFO.getName()` returns `INFO`.
- `Level.WARNING.getName()` returns `WARNING`.
- `Level.SEVERE.getName()` returns `SEVERE`.
- `Level.FINE.getName()` returns `FINE`.

`getLocalizedName()` may return a localized label depending on the bundle/locale. If the level is used for searching, alerting, or cross-service aggregation, prefer canonical names/stable schemas over environment-translated names.

### 4.1. `SimpleFormatter` and positional argument formatting

JUL provides `java.util.logging.SimpleFormatter`. In `logging.properties`, you can customize the format string:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$-7s | %3$s | %5$s%6$s%n
```

The positional arguments of `SimpleFormatter` are:

| Argument | Content |
|---|---|
| `%1$...` | Date/time of the log record |
| `%2$s` | Source, e.g., class/method name |
| `%3$s` | Logger name |
| `%4$s` | Level name |
| `%5$s` | Formatted message |
| `%6$s` | Formatted Throwable/stack trace if present |
| `%n` | Platform-specific newline character |

`%4$-7s` is **`java.util.Formatter`** syntax: take the fourth argument, left-align, minimum width 7. It is **not** Logback PatternLayout syntax.

The application can load the file with a JVM property:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

This is an illustrative command; it requires a compiled `com.example.Main` class and the correct file path. Frameworks or containers may manage `LogManager` differently. Simply placing `logging.properties` in a project does not guarantee it will be loaded automatically.

### 4.2. Custom Formatter

You can explicitly build the string using `String.format`:

```java
@Override
public String format(LogRecord record) {
    return String.format(
            java.util.Locale.ROOT,
            "%-7s | %s | %s%n",
            record.getLevel().getName(),
            record.getLoggerName(),
            formatMessage(record));
}
```

This is an **illustrative method** inside a subclass of `Formatter`, not a complete Java file. Use `formatMessage(record)` to substitute `{0}`, `{1}` parameters according to JUL rules; `record.getMessage()` only returns the raw template.

**Important:** the formatter above does not output stack traces. When real exception diagnosis is needed, you must handle `record.getThrown()` or choose a formatter that supports Throwable and the full cause chain. Level formatting must not drop error information.

## 5. Standalone Java 17+: level formatter in JUL

This example uses only the JDK, requiring no Maven or external dependencies.

Create the file `LevelFormatDemo.java`:

```java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LevelFormatDemo {
    private static final Logger LOG =
            Logger.getLogger(LevelFormatDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return String.format(
                        Locale.ROOT,
                        "%-7s | %s | %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        formatMessage(record));
            }
        });
        LOG.addHandler(console);

        LOG.info("event=app_started");
        LOG.warning("event=cache_degraded");
        LOG.log(Level.SEVERE,
                "event=order_save_failed orderId={0}",
                new Object[]{"ORD-7"});
        LOG.fine("event=debug_probe");

        console.flush();
    }
}
```

Compile/run from the directory containing the file with JDK 17 or higher:

```bash
javac -encoding UTF-8 LevelFormatDemo.java
java LevelFormatDemo
```

Output displayed on **stderr**:

```text
INFO    | LevelFormatDemo | event=app_started
WARNING | LevelFormatDemo | event=cache_degraded
SEVERE  | LevelFormatDemo | event=order_save_failed orderId=ORD-7
FINE    | LevelFormatDemo | event=debug_probe
```

JUL's `ConsoleHandler` writes to `System.err` by default; the program does not write to stdout. Timestamps are omitted from the output for easier comparison.

### Code breakdown

1. `LOG.setLevel(Level.ALL)` allows the logger to emit events from FINE and above; `console.setLevel(Level.ALL)` ensures the handler does not drop FINE.
2. `setUseParentHandlers(false)` prevents forwarding the same event to the default parent/root handler, avoiding duplicate output.
3. `record.getLevel().getName()` prints the actual JUL name: `WARNING` and `SEVERE`, without automatically converting them to `WARN` or `ERROR`.
4. `%-7s` left-aligns: `INFO` gets three trailing spaces, `WARNING` needs none; the format string adds one space before `|`.
5. `formatMessage(record)` substitutes `{0}` with `ORD-7`.
6. `console.flush()` asks the handler to flush buffered output; this is not a durability guarantee across all systems.

If you change `LOG.setLevel(Level.ALL)` to `LOG.setLevel(Level.INFO)`, the FINE line is dropped, while the formatting of the remaining levels stays unchanged. **Level policy and level formatting are two separate responsibilities.**

### Mapping to common labels without modifying the original Level

If you need to present `WARN/ERROR` in a unified text output, you can use a helper method:

```java
// Illustration inside a custom Formatter:
private static String displayLevel(Level level) {
    if (level == Level.WARNING) return "WARN";
    if (level == Level.SEVERE) return "ERROR";
    return level.getName();
}
```

When using `displayLevel(record.getLevel())` for formatting, the event still carries `Level.WARNING` or `Level.SEVERE`. Custom levels need explicit rules; do not blindly turn them into ERROR if their semantics are unclear. If the collector wants to preserve the origin, it can also store `originalLevel`.

## 6. Logback PatternLayout: `%level`, `%p`, and padding

In Logback Classic, pattern layouts commonly support:

- `%level`: the level name, e.g., `INFO`, `WARN`, `ERROR`.
- `%p`: alias for the level conversion word.
- `%-5level` or `%-5p`: left-aligned, minimum width 5 characters.
- `%5level` or `%5p`: right-aligned, minimum width 5 characters.

Example:

```xml
<pattern>%-5level | %logger{0} | %msg%n</pattern>
```

For `INFO`, `%-5level` outputs `INFO` with **one padding space**, followed by `" | "` in the pattern. Therefore, there are **two spaces before the `|` character**. For `ERROR`, the name is exactly 5 characters long, so no padding is needed.

### 6.1. Complete `logback.xml`

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level | %logger{0} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="TRACE">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Root TRACE in this example is intended to let all five levels appear. In production, you generally should not enable TRACE system-wide, as log volume and the risk of data exposure can increase.

### 6.2. Java 17+ program using SLF4J/Logback via Maven

Structure:

```text
logback-level-format/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/logging/LevelLogbackDemo.java
        └── resources/logback.xml
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logback-level-format</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
                <configuration>
                    <mainClass>com.example.logging.LevelLogbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/com/example/logging/LevelLogbackDemo.java`:

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LevelLogbackDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LevelLogbackDemo.class);

    public static void main(String[] args) {
        LOG.trace("event=trace_probe");
        LOG.debug("event=debug_probe");
        LOG.info("event=app_started");
        LOG.warn("event=cache_degraded");
        LOG.error("event=save_failed");
    }
}
```

File `src/main/resources/logback.xml` uses the exact configuration from section 6.1. With Maven, JDK 17+, and permission to download dependencies, run:

```bash
mvn -q compile exec:java
```

Lines **written by Logback to stdout**:

```text
TRACE | LevelLogbackDemo | event=trace_probe
DEBUG | LevelLogbackDemo | event=debug_probe
INFO  | LevelLogbackDemo | event=app_started
WARN  | LevelLogbackDemo | event=cache_degraded
ERROR | LevelLogbackDemo | event=save_failed
```

The INFO/WARN lines have **two spaces before `|`**, consisting of one padding space and one space from the pattern. Maven may emit its own build/tool messages depending on the environment; this snippet only shows the lines **from the Logback appender**.

The Logback version in `pom.xml` is only a fixed value for the example, not a recommendation for the latest release. Real applications must verify dependency management, JDK compatibility, and security patches.

### Left-alignment vs. right-alignment

| Logback Pattern | Generated level part | Meaning |
|---|---|---|
| `%level` | `INFO` | No padding |
| `%-5level` | `INFO␠` | Left-aligned to width 5 |
| `%5level` | `␠INFO` | Right-aligned to width 5 |
| `%-5p` | `INFO␠` | Level alias, left-aligned |

The `␠` symbol in the table represents an illustrative space. If the level name is longer than the minimum width, it is usually still printed in full unless an additional truncation rule is added.

## 7. Log4j 2: Level converter in PatternLayout

Log4j 2 supports `%p`/`%level` in `PatternLayout`. A Log4j 2 configuration can be written as:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%-5p | %c{1} | %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Explanation:

- `%-5p` displays the level left-aligned with a minimum width of 5.
- `%c{1}` shortens the logger name for display purposes.
- `%m%n` outputs the message and a newline.
- `Root level="info"` is the **filtering threshold**, not the level column width.
- The `log4j2.xml` file uses Log4j 2's configuration format, **not** `logback.xml` or JUL `logging.properties`.

To run in practice, you need Log4j 2 API/Core and the provider matching the API the application calls. Do not add both Logback and the Log4j 2 provider at the same time if the application selects one backend via SLF4J, and do not wire reverse bridges that cause loops.

### Syntax comparison

| Intent | JUL | Logback | Log4j 2 |
|---|---|---|---|
| Display level name | `record.getLevel().getName()` or SimpleFormatter's `%4$s` | `%level` / `%p` | `%level` / `%p` |
| Left-align minimum 5 | `String.format("%-5s", name)` or `%4$-5s` | `%-5level` | `%-5p` |
| Standard warning name | `WARNING` | `WARN` | `WARN` |
| Common error name | `SEVERE` | `ERROR` | `ERROR` |
| Configuration file | `logging.properties` | `logback.xml` | `log4j2.xml` |

Some Logback and Log4j 2 token syntaxes look similar, but appender, layout, routing, and advanced conversion configurations are not compatible by default.

## 8. ANSI level coloring: for human-readable output only

Colors help spot WARN/ERROR quickly when watching the console. With Logback, an illustrative pattern:

```xml
<pattern>%highlight(%-5level) | %logger{0} | %msg%n</pattern>
```

With Log4j 2 PatternLayout:

```xml
<PatternLayout pattern="%highlight{%-5p} | %c{1} | %m%n"/>
```

These are **fragments** that depend on the backend/version and terminal support. Colors are typically encoded using **ANSI escape sequences**. When writing logs to a file, collector, or system that does not support color, ANSI codes can produce garbled characters, break regex parsers, or corrupt the severity value.

Practical rules:

- Only enable coloring for interactive consoles if the environment supports it.
- Do not store ANSI codes in a JSON `level` field.
- Do not rely solely on color to convey severity; readers may not distinguish colors.
- Changing colors does not change log thresholds and does not make filtered DEBUG events appear.
- If collecting both stdout and stderr, check the appender's target separately; color layout does not control stderr/stdout.

## 9. Level formatting in structured logging and JSON

In centralized systems, the level should be a **stable structured field**:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "logger": "com.example.orders.OrderService",
  "level": "WARN",
  "event": "dependency_degraded",
  "message": "inventory lookup slow",
  "requestId": "req-42"
}
```

This JSON is a **schema example**, not the output of the two Java programs above. To produce real JSON, you need an encoder/layout/serializer that supports JSON, and the application must supply the actual event/context.

**Do not put padding into severity data**:

```json
{"level":"WARN","message":"dependency degraded"}
```

Avoid:

```json
{"level":"WARN ","message":"dependency degraded"}
```

A field with a trailing space will usually fail to match a filter like `level == "WARN"`. Padding is for text presentation, not machine-readable values.

### 9.1. Normalizing between JUL and other backends

If the collector uses `WARN` and `ERROR` labels while JUL emits `WARNING` and `SEVERE`, you can define a mapping. You can also keep the original information:

```json
{
  "level": "WARN",
  "originalLevel": "WARNING",
  "loggingSystem": "JUL"
}
```

This is a schema choice, not a mandatory rule. For `CONFIG`, `FATAL`, or custom levels, the mapping policy must be documented explicitly; do not guess based on name length or alphabetical sorting.

Some observability standards use `severityText` and `severityNumber`; if adopted, follow the standard's severity definitions and the agreed mapping rules. Do not compare `"WARN"` and `"ERROR"` as two lexicographical strings to decide which is more severe.

### 9.2. MDC/context is not a level

An event can have `level=INFO` while also carrying `traceId`, `requestId`, or `userId` (if permitted to log). With SLF4J/Logback, **MDC** typically provides contextual fields such as `requestId`, while the level is determined by the logger event. Do not cram the request ID into the level string like `"INFO_req-42"`; doing so breaks severity filtering and aggregation.

MDC also does not automatically propagate across business threads; it must be propagated and cleared properly when using thread pools. A JSON layout cannot recover a request ID that was never attached to the event.

## 10. Levels in filters, alerts, and dashboards

An operational pipeline might look like this:

```text
Application emits JUL Level.WARNING
      |
      v
Logger/Handler applies level/filter
      |
      v
Formatter outputs "WARNING"
      |
      v
Collector normalizes to "WARN"
      |
      v
Alert on normalized severity
```

Each stage has a distinct role:

- If an event is **filtered out at the start**, there is nothing left to format.
- If the formatter maps the alias `WARNING` → `ERROR` incorrectly, the dashboard may report the wrong severity.
- If the collector parser only understands `WARN`, JUL `WARNING` events may be missed.
- If the text pattern changes from `%level - %msg` to `%level | %logger | %msg`, an old parser may fail to extract the level properly.
- If an exception is logged at multiple layers, the ERROR line count can exceed the actual number of failed requests; this is a logging strategy issue, not just level formatting.

**Do not treat the ERROR line count as an exact error rate** without controlling for duplicate logging, sampling, and event loss. Metrics should count well-defined units of work, while logs are for investigating context.

### Filter threshold vs. column width

- `<root level="INFO">` in Logback: condition for emitting events.
- `%-5level` in PatternLayout: presentation of accepted events.

Increasing the width does not enable DEBUG. Lowering the threshold from INFO to DEBUG does not require changing the format. Checking effective behavior requires looking at the logger level, appender/filter, and destination pipeline together.

## 11. Performance and safety

Formatting a short level label is usually cheaper than rendering an exception stack trace or serializing large JSON, but there are points to consider:

1. `String.format(...)` parses the format string and allocates objects; if event volume is very high, you can evaluate `StringBuilder`/simple padding after profiling.
2. Patterns containing caller class/method/line can incur the cost of capturing stack/caller data; do not attribute all overhead to `%level`.
3. ANSI colors add escape sequences and processing work, which are unhelpful to collectors when output is machine-read.
4. JSON encoders have their own serialization/escaping overhead; choose a schema that is sufficient.
5. Log messages containing user data must have an escaping/size-limit policy. `%level` does not protect against log injection from the message.
6. Do not log passwords, tokens, session cookies, or sensitive information in messages/context just for debugging. High or low level is not a masking mechanism.
7. With async appenders, some formatting steps are offloaded to a worker thread depending on the implementation; that does not make all Java argument expressions lazy.

Adding a stable structured severity field is usually more useful than crafting an overly elaborate text pattern.

## 12. Common errors and troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JUL log shows `WARNING`, dashboard only recognizes `WARN` | Level not normalized | Map aliases accurately in collector/formatter |
| JUL log shows `SEVERE`, alert undercounts `ERROR` | Different level names | Normalize severity schema or support original labels |
| Level column is misaligned | Labels have different lengths | Add width/padding in text layout |
| JUL prints literal `%-5level` | Using Logback pattern in SimpleFormatter | Use `%4$-5s` or a custom Formatter |
| Logback prints literal `%4$s` | Using JUL syntax in PatternLayout | Use `%level`/`%-5level` |
| DEBUG not appearing | Blocked by logger/filter/appender before formatter | Check effective level and destination |
| JSON field is `"WARN "` | Carrying text padding into raw value | Store `"WARN"` without whitespace |
| ANSI color codes appear in file | Highlight enabled when collector lacks support | Remove color for machine-readable output |
| Severity translated differently across machines | Using localized label as key | Use canonical name/stable JSON schema |
| False or missing alerts after format change | Parser or mapping out of sync | Test both raw events and post-collector fields |
| Stack trace disappears | Formatter only writes level and message | Write Throwable/cause chain properly |
| Duplicate logs after layout change | Parent handlers/appenders/additivity | Check record routing, do not confuse with formatting |
| Missing request ID | No MDC/context or context not propagated across threads | Pass identifier separately, do not merge into level |

### Systematic debugging workflow

1. Identify the **logging API** and **receiving backend** (JUL, Logback, Log4j 2, bridge).
2. Inspect the event's actual level before formatting, if possible.
3. Check logger level/filters and handler/appender level/filters.
4. Identify which formatter/layout/encoder and configuration file are actually loaded.
5. Verify the exact syntax: JUL `%4$s`, Logback `%-5level`, Log4j 2 `%-5p`.
6. Emit sample events at INFO, WARN/WARNING, and ERROR/SEVERE and compare output after the collector.
7. Verify that alerts, dashboards, log search, and parsers use the final schema correctly.

## 13. Practical checklist

- [ ] Choose levels based on event meaning, not message appearance.
- [ ] Clearly distinguish **level filtering** from **level formatting**.
- [ ] Use the correct API/pattern for the running backend.
- [ ] Align text using minimum width; do not truncate severity names.
- [ ] Do not carry padding or ANSI codes into the JSON `level` field.
- [ ] Define intentional `WARNING↔WARN`, `SEVERE↔ERROR` mappings if aggregating multiple logging systems.
- [ ] Have explicit policies for specialized levels like `CONFIG`, `FATAL`, or custom levels.
- [ ] Use a stable severity field for machine reading; avoid localized text as search keys.
- [ ] Ensure formatters do not drop parameters or necessary Throwable/stack traces.
- [ ] Do not base alerts/metrics on lexicographical comparison of `WARN/ERROR` strings.
- [ ] Test with the real runtime, text/JSON output, and actual collector.
- [ ] Do not expose sensitive data in messages, context, or exceptions.

**Conclusion:** formatting the level is the responsibility of the **formatter/layout/encoder**. With JUL, use `LogRecord.getLevel()` and `SimpleFormatter` or a custom `Formatter`; with Logback and Log4j 2, use `%level`/`%p` with width when needed. Filtering events by level is a separate responsibility of the logger/filter/handler/appender. When logs are centralized, use a structured, normalized severity field without padding or ANSI codes so logs remain readable while preserving meaning for search, monitoring, and alerting.
