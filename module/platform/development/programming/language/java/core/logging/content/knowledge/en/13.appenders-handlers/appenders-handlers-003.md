# Console Appender — Logging to the Console with Logback in Java

## 1. What is a Console Appender?

A **console appender** is a component of a logging system responsible for **writing log events to the process output streams**, typically **stdout** or **stderr**. In **Logback**, the class used for this purpose is **ch.qos.logback.core.ConsoleAppender**.

When a Java application calls **LOG.info(...)**, it does not directly print a line of text. The event passes through the logger API, level checks, filters, and the appender system; ConsoleAppender receives eligible events, uses an encoder to convert them into data, and writes them to the selected stream.

Example of the messages you might want to see:

~~~text
INFO | event=service.started port=8080
WARN | event=dependency.slow durationMs=740
ERROR | event=payment.failed errorCode=TIMEOUT
~~~

These are **illustrative messages**, not Logback's default format. Whether the content is displayed and what it looks like depend on the configuration.

It is important to distinguish between:

- **Logger:** the log emission point in Java code; for example, **org.slf4j.Logger**.
- **Appender:** the destination that receives events for output. ConsoleAppender is the appender for the console; FileAppender is the appender for files.
- **Encoder/Layout:** formats the event, such as printing the level, logger name, message, timestamp, and stack trace.
- **Filter:** rules that block or allow an event to be output.
- **Target:** the stream that ConsoleAppender writes to: **System.out** or **System.err**.

**ConsoleAppender is not System.out.println.** Println writes directly to stdout without considering log levels. LOG.debug(...) can be discarded by the logger when the level is INFO, and can also be blocked by a filter on the appender.

## 2. Where ConsoleAppender Fits in the Logback Pipeline

~~~text
Application code: LOG.info("event=...")
                 |
                 v
           SLF4J Logger API
                 |
                 v
       Logback Logger / level
                 |
                 v
             Log event
                 |
         Logger hierarchy and
            additivity
                 |
                 v
      ConsoleAppender + filter
                 |
                 v
       Encoder (pattern/charset)
                 |
           +-----+------+
           |            |
           v            v
       System.out    System.err
           |            |
           +-----+------+
                 |
                 v
    Terminal / container collector
~~~

A Logger does not necessarily have an appender attached directly to it. It can forward events to the appender of a parent logger or the **root logger** when additivity allows.

| Component | Question to check |
| --- | --- |
| Logger/effective level | Are DEBUG, INFO, WARN, ERROR calls accepted? |
| Additivity | Do events reach appenders attached to parent loggers? |
| Appender filter | Are events that passed the logger subsequently discarded? |
| Encoder | Which pattern, charset, and exception representation does the log line use? |
| Target | Does ConsoleAppender output to stdout or stderr? |
| Collector | Does the infrastructure collect, parse, and retain the log line? |

An event can be blocked at any relevant step. **Calling LOG.error(...) does not guarantee that the record is durably persisted in a remote collection system.**

## 3. Differences Between stdout and stderr

The two standard streams of a process:

- **stdout:** typically contains primary output and regular messages.
- **stderr:** typically reserved for diagnostic and error information, separated from the primary output.

**Logback ConsoleAppender** defaults to **System.out** and allows overriding it via the target property:

~~~xml
<target>System.out</target>
~~~

or:

~~~xml
<target>System.err</target>
~~~

The two snippets above are only **XML fragments inside an appender**, not a complete logback.xml file.

A CLI that prints JSON for another program should usually avoid mixing logs into stdout, as doing so can invalidate the JSON output. If you need to keep stdout for data, you can choose stderr for diagnostic logs. Conversely, containerized services often have infrastructure collect both stdout and stderr; the choice should follow the system's deployment standards.

### Differences Between ConsoleAppender and JUL ConsoleHandler

| Criterion | Logback ConsoleAppender | JUL ConsoleHandler |
| --- | --- | --- |
| Class | ch.qos.logback.core.ConsoleAppender | java.util.logging.ConsoleHandler |
| Belongs to | Logback, usually via SLF4J | JDK's java.util.logging |
| Default stream | **System.out** | **System.err** |
| Formatting | Encoder/Layout | Formatter |
| Common levels | TRACE, DEBUG, INFO, WARN, ERROR | FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE |
| Typical configuration | logback.xml | logging.properties or Java code |

Do not write a Logback configuration and expect JUL to read it; the two systems have different APIs and configuration mechanisms.

### Output Redirection in the Shell

In bash, **>** redirects stdout while **2>** redirects stderr:

~~~bash
java -jar app.jar > stdout.log
java -jar app.jar 2> stderr.log
java -jar app.jar > combined.log 2>&1
~~~

These commands only illustrate shell redirection; an actual JAR file is required. Redirecting a stream to a file is **not a FileAppender**: one is handled by the shell, while the other is managed by the logging backend.

If stdout and stderr are collected together and merged, the observed order between the two streams **does not always accurately reflect the order in which events were emitted**. When investigating issues, use timestamps with timezones and correlation IDs.

## 4. Basic logback.xml File

A complete configuration:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

How to read it:

1. **name="CONSOLE"** sets the appender's name.
2. **class="...ConsoleAppender"** specifies the appender type.
3. **target=System.out** selects stdout.
4. **encoder** converts the log event into content written to the console.
5. **charset=UTF-8** supports Unicode when the receiver also uses a compatible encoding.
6. **%level** is the log level, **%logger** is the logger name, **%msg** is the message after formatting parameters, and **%n** is a newline.
7. **root level=INFO** sets the default level inherited by loggers.
8. **appender-ref** attaches CONSOLE to root so events are routed to the appender.

Merely declaring an appender **without referencing it from a logger/root** does not guarantee any output. **The name and ref attributes must match**. In real applications, you should add a timestamp, thread, request/trace ID, and an appropriate Throwable output policy.

## 5. Runnable Project: Java 17 + Maven + Logback

This example creates a simple Java program that emits four log events; only three events are printed when root is at INFO. The program calls the **SLF4J API**, while **ConsoleAppender** is selected in logback.xml. There is no need to write an appender class yourself.

### 5.1. Project Structure

~~~text
console-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ConsoleAppenderDemo.java
        └── resources/
            └── logback.xml
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>console-appender-demo</artifactId>
    <version>1.0.0</version>

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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConsoleAppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The versions here are **illustrative versions**, not claimed to be the latest. Maven resolves the transitive dependencies of logback-classic such as logback-core and SLF4J API. Real projects need to manage versions and security patches, and avoid putting multiple different SLF4J providers on the same classpath.

### 5.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

With Maven, files under src/main/resources are placed on the classpath at runtime; Logback can load it via its default configuration mechanism if no other framework or configuration overrides it.

### 5.4. src/main/java/demo/ConsoleAppenderDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ConsoleAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ConsoleAppenderDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=cache.lookup result=miss");

        LOG.info("event=service.started port={}", 8080);

        LOG.warn("event=dependency.slow durationMs={}", 740);

        LOG.error("event=payment.failed errorCode={}", "TIMEOUT");
    }
}
~~~

This is a **standalone program in the Maven project described above**, not an incomplete snippet missing a class. The imported class is **org.slf4j.Logger** so that the code does not depend on ConsoleAppender's specific API.

### 5.5. Compiling and Running

Requires **JDK 17+**, Maven installed, and dependencies downloadable or available in the cache. In the project directory:

~~~bash
mvn -q compile exec:java
~~~

**Exact stdout emitted by the Java program** with the logback.xml configuration above (excluding Maven's or the environment's own logs):

~~~text
INFO | demo.ConsoleAppenderDemo | event=service.started port=8080
WARN | demo.ConsoleAppenderDemo | event=dependency.slow durationMs=740
ERROR | demo.ConsoleAppenderDemo | event=payment.failed errorCode=TIMEOUT
~~~

**There is no DEBUG line** because the effective level is INFO from root. Lines end with a newline; there is no timestamp so the output does not depend on the clock.

### 5.6. Why Exactly Three Lines?

1. LoggerFactory retrieves the logger named **demo.ConsoleAppenderDemo**.
2. The logger has no explicit level of its own, so it inherits the **INFO** threshold.
3. The DEBUG event is lower than INFO and is discarded.
4. INFO, WARN, and ERROR meet the threshold.
5. The logger forwards the events to root's CONSOLE appender via normal additivity.
6. The pattern outputs **%level | %logger | %msg%n**.
7. ConsoleAppender writes to **System.out**, so the three lines belong to stdout.
8. The SLF4J **{}** placeholders are replaced by 8080, 740, and TIMEOUT respectively.

### 5.7. Enabling DEBUG Without Modifying Source Code

Change the root configuration:

~~~xml
<root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Run again, and **the program's stdout** includes the first line:

~~~text
DEBUG | demo.ConsoleAppenderDemo | event=cache.lookup result=miss
INFO | demo.ConsoleAppenderDemo | event=service.started port=8080
WARN | demo.ConsoleAppenderDemo | event=dependency.slow durationMs=740
ERROR | demo.ConsoleAppenderDemo | event=payment.failed errorCode=TIMEOUT
~~~

This demonstrates that the backend controls observability levels. You should not change LOG.debug calls to LOG.info just to force a debug line to appear in production.

### 5.8. Switching target to System.err

Change target in the XML file:

~~~xml
<target>System.err</target>
~~~

After running again with the rest of the configuration unchanged, the content of the three log lines remains the same as in section 5.5, but they are written to **stderr**; **the program's stdout does not contain those lines**. If you need to verify, in bash you can redirect:

~~~bash
mvn -q compile exec:java > stdout.log 2> stderr.log
~~~

The application log lines will be in stderr.log. Any Maven-specific output or runtime diagnostics, if present, are not part of the example's expected output.

## 6. Formatter/Encoder: Controlling How Console Logs Are Read

With Logback, **PatternLayoutEncoder** is commonly used to produce text lines. Some common conversion words:

| Token | Output |
| --- | --- |
| **%level** or **%p** | INFO, WARN, ERROR, DEBUG... |
| **%logger** or **%c** | Logger name |
| **%logger{36}** | Abbreviated logger name |
| **%thread** or **%t** | Thread name |
| **%msg** / **%message** | Message after substituting arguments |
| **%n** | Newline |
| **%d{...}** | Timestamp with a specific pattern |
| **%X{requestId}** | MDC requestId value if present |
| **%ex** / **%throwable** | Exception/stack trace information per converter |

A diagnostic pattern might look like:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n</pattern>
~~~

The snippet above is only a **pattern element inside an encoder**, not a standalone XML file. The timestamp depends on the actual timezone/configuration: a pattern like this **does not automatically guarantee UTC**.

A system that needs to query fields such as event, errorCode, and durationMs can use a corresponding **structured JSON encoder**. Manually concatenating JSON strings without escaping quotes/newlines easily produces invalid data. Having key=value text in %msg alone also does not automatically turn every field into an indexed field in the collection backend.

### Unicode and Charset

If messages contain Vietnamese or other non-ASCII characters, you should set **UTF-8** in the encoder and check the charset at the reader/collector. For example:

~~~xml
<encoder>
    <charset>UTF-8</charset>
    <pattern>%level | %msg%n</pattern>
</encoder>
~~~

Proper display cannot be guaranteed by the appender alone if the terminal or collector decodes with a different character encoding.

## 7. Appender Filters: Why Do DEBUG/INFO Not Appear?

An appender can add a **ThresholdFilter** to accept only events at or above a certain level.

Example of a ConsoleAppender that accepts only **WARN/ERROR**:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>
    <encoder>
        <pattern>%level | %msg%n</pattern>
    </encoder>
</appender>
~~~

This is an illustrative appender fragment. If the logger is at DEBUG but the appender has a ThresholdFilter for WARN, DEBUG and INFO events **still will not appear**, because they are blocked by the appender. Conversely, making a filter more permissive cannot recover events that were already discarded by the Logger.

| Logger effective level | Appender threshold | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| INFO | No filter | No | May appear | May appear | May appear |
| DEBUG | No filter | May appear | May appear | May appear | May appear |
| DEBUG | WARN | No | No | May appear | May appear |
| INFO | WARN | No | No | May appear | May appear |
| ERROR | INFO | No | No | No | May appear |

"May appear" means the appender is attached and no other filter blocks it.

### Root INFO Does Not Necessarily Drop DEBUG from a Child Logger

Consider the configuration fragment:

~~~xml
<logger name="demo.order" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

If the child logger demo.order.OrderService has effective level DEBUG and additivity=true, its DEBUG events can reach the appender on root. **Root INFO does not re-filter DEBUG events that were already accepted by a child logger**. If you want the entire console to contain only INFO and above, you need to check filters on the appender, not just look at the root level.

## 8. Additivity and Duplicate Log Entries

When **additivity=true** (the typical default behavior), a child logger's events can be propagated up to ancestors to use their appenders.

A configuration that easily produces duplicate logs:

~~~xml
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%level | %msg%n</pattern>
    </encoder>
</appender>

<logger name="demo.order" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

Because CONSOLE is attached to both demo.order and root, the same event can cause the appender to be invoked twice. This **is not sufficient to conclude that the business operation ran twice**.

A common fix is to **attach CONSOLE only to root**, while child loggers only set their level. If you truly need a dedicated console for a sub-hierarchy, you can configure:

~~~xml
<logger name="demo.order"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="ORDER_CONSOLE"/>
</logger>
~~~

Here **ORDER_CONSOLE must be declared beforehand**. When additivity=false, events from the sub-hierarchy are not forwarded up to ancestor appenders along that path. If you disable additivity without attaching any appender on the dedicated branch, logs may disappear.

**Additivity is different from level inheritance**: a logger can inherit INFO from root while still breaking the appender chain, or have its own DEBUG level while using the appender on root.

## 9. Routing INFO/WARN to stdout and ERROR to stderr

A ConsoleAppender only has **one target**. If you want to split streams by level, you can create two appenders with non-overlapping filters:

~~~xml
<configuration>
    <appender name="OUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="OUT"/>
        <appender-ref ref="ERR"/>
    </root>
</configuration>
~~~

How it works:

- **OUT** specifically denies ERROR via LevelFilter, so INFO/WARN events can be output to stdout.
- **ERR** uses ThresholdFilter ERROR so it does not accept INFO/WARN; ERROR is output to stderr.
- **Root INFO** drops DEBUG from loggers that inherit INFO before events reach the appenders.
- Both appenders coexist without intentionally duplicating ERROR.

If **OUT does not have the LevelFilter**, an ERROR event can be output to both stdout and stderr. You should verify the actual routing by redirecting both streams.

When two streams are merged by the shell/container, **line ordering across the two streams is not strictly guaranteed**. Consider keeping all logs in a single stream according to organizational standards if ordering and collection require it.

## 10. ConsoleAppender, FileAppender, and Container Environments

**ConsoleAppender** pushes events to stdout/stderr, whereas **FileAppender/RollingFileAppender** has the backend manage files directly. Choose the destination based on the environment:

| Criterion | ConsoleAppender | FileAppender / RollingFileAppender |
| --- | --- | --- |
| Destination | Process streams | Files opened by the backend |
| Common usage | CLIs, containerized services | Servers requiring local files |
| Rotation | Handled by shell/runtime/collector if any | Rotation configurable on RollingFileAppender |
| Retention | Collection system or infrastructure | File policy and infrastructure |
| Watchouts | Blocked stdout, slow collector, mixed streams | Disk space, permissions, file locks, rotation |
| Risk of log loss | Possible on I/O or collector failure | Possible on buffer/disk/process failure |

**Writing to the console does not mean logs will be saved in a file**. Docker/Kubernetes or cloud runtimes can collect stdout/stderr, but this requires configuring the collector, permissions, retention period, and quotas.

A CLI that wants to output machine-readable data on stdout may choose stderr for logs. A containerized server may choose stdout for all levels and rely on the level field in the log to classify them. There is no single rule that fits every application.

## 11. Performance, Buffering, and AsyncAppender

Console logging has overhead: constructing the message, formatting, encoding, writing to the stream, and potentially waiting on a pipe consumer or collector. Logging excessively inside loops or logging long stack traces at high frequency can increase latency.

Factors to measure:

1. **Throughput:** number of events per second and average size.
2. **Level:** DEBUG/TRACE can sharply increase event volume.
3. **Encoder:** pattern and JSON encoders have different costs.
4. **Destination:** terminal, file redirect, or container runtime write at different speeds.
5. **Buffering/flushing:** frequent flushing can incur I/O overhead; holding buffers too long risks losing logs if the process stops unexpectedly.
6. **Threads:** many threads emitting events can create contention on the shared output point.

**You cannot assume ConsoleAppender is always slower than FileAppender by a fixed ratio.** Benchmark under realistic load and infrastructure.

**AsyncAppender** can enqueue events and have a dedicated worker write to ConsoleAppender:

~~~text
Logger -> AsyncAppender -> Queue -> ConsoleAppender -> stdout
~~~

It can reduce wait time for business threads in some cases. However, when the queue is full or on sudden shutdown, events may be blocked, dropped, or left unflushed depending on configuration. You need to understand queue size, discard policy, timeouts, and shutdown behavior; **async does not guarantee zero log loss**.

### Watch Out for Argument Evaluation Cost

An SLF4J code fragment:

~~~java
LOG.debug("payload={}", expensiveSerialize(payload));
~~~

Even when DEBUG is disabled, Java still **evaluates expensiveSerialize(payload)** before calling debug(...). If building the representation is genuinely expensive:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

These snippets **require LOG, payload, and the method to be defined** in an actual class; they are not standalone. Parameterized logging with **{}** avoids part of the string-building cost, but does not defer evaluating argument expressions. Do not put mandatory business logic inside code that only runs when DEBUG is enabled.

## 12. Exceptions, Stack Traces, and MDC

When investigating errors, pass the Throwable object:

~~~java
try {
    callPaymentService();
} catch (java.io.IOException ex) {
    LOG.error("event=payment.failed requestId={}", requestId, ex);
}
~~~

This is an **illustrative fragment**, requiring LOG, requestId, and the callPaymentService method in a real context. Logback can accept the throwable so the encoder/layout renders the stack trace and cause. However, **do not assume every pattern preserves the full Throwable**; verify the converter/encoder and actual output.

Do not log only ex.getMessage() and lose the root cause, or log the same exception at every layer. Define clear boundaries for which layer is responsible for logging once an operation is known to have failed.

### Request ID via MDC

With SLF4J MDC:

~~~java
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

The snippet above **is not a standalone program**; it requires LOG to already exist in the class. In the Logback encoder you can add:

~~~xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
~~~

An illustrative line could be:

~~~text
INFO requestId=req-42 demo.OrderService - event=order.created outcome=success
~~~

This is not the output of the program in section 5. **MDC does not automatically propagate across all thread pools, CompletableFuture, and async frameworks**. You must propagate and clear the context in the proper scope so request IDs do not leak between tasks.

## 13. ANSI/Colors on the Terminal

During local development, you can use a pattern that colorizes levels:

~~~xml
<pattern>%highlight(%-5level) %logger - %msg%n</pattern>
~~~

This is only an **illustrative pattern fragment**. ANSI and color handling depend on the terminal, backend version, or supporting configuration (on some Windows environments, Jansi may be needed). When sending logs to a collector or file, color control characters can make data harder to read or parse.

Do not enable colors in production by default. If you need to classify alerts, output an explicit level field for the collection system to filter on instead of relying on terminal colors.

## 14. Security and Observability

Console logs in containers, CI, or cloud platforms can be collected, backed up, and accessed by many systems. Therefore:

- **Do not log passwords, API keys, access tokens, refresh tokens, session cookies, private keys, or card data.**
- Do not log full request/response bodies, Authorization headers, or object.toString() by default.
- For untrusted input, use an escaping encoder to prevent newlines/control characters from creating forged log lines.
- Choose safe event codes, errorCodes, and requestIds instead of sensitive data; consider access controls and retention.
- Do not treat a LOG.info call as proof that a transaction was durably recorded; logging can fail or be collected with delay.
- Metrics are suited for error rates/latency over time, logs help analyze a specific event, and tracing helps follow flows across multiple services.
- Do not turn a unique requestId into an unbounded metric label; it belongs in logs/traces.

Even a simple console appender needs logging rules and observability practices to detect issues when the collector stops receiving data.

## 15. Common Pitfalls

| Pitfall | Symptom | Resolution |
| --- | --- | --- |
| Appender defined but missing appender-ref | No logs visible | Attach the appender to a logger or root |
| Wrong ref name | Not connected to the right destination | Match name and ref |
| Root INFO while expecting DEBUG output | DEBUG is dropped | Configure the level on the appropriate logger |
| Logger DEBUG with appender ThresholdFilter WARN | No DEBUG lines | Check filters as well |
| Same CONSOLE attached to child and root | One event appears twice | Check additivity and appender-ref |
| additivity=false without its own appender | Logs disappear | Attach an appender or re-enable propagation |
| Confusing Logback stdout with JUL stderr | Wrong stream redirected | Identify the backend and target |
| Two ConsoleAppenders on different streams without filters | ERROR may appear twice | Design non-overlapping filters |
| Multiple SLF4J providers present | Unexpected backend selected | Check the dependency tree and keep one provider |
| Using logback.xml with plain JUL | Configuration is ignored | Use the configuration file for the right backend |
| Inconsistent charset | Corrupted Vietnamese/Unicode characters | Configure UTF-8 at both sender and receiver |
| Excessive logging | Console/collector overloaded | Choose appropriate levels, sampling, or metrics |
| ANSI enabled when storing centralized text | Color escape codes mixed into logs | Disable colors or handle escaping |
| Logging raw user input or tokens | Data exposure, log injection | Minimize fields, mask, and escape |
| Not clearing MDC | Old task's requestId persists | Clear by scope and propagate properly |

## 16. Checklist When Console Logs Do Not Appear

1. **Backend:** is the application actually using Logback Classic, or JUL/Log4j 2?
2. **Provider:** does the SLF4J API have a single compatible provider?
3. **Configuration:** is logback.xml on the classpath and being loaded?
4. **Logger name:** which name does the code use, and what is its effective level?
5. **Appender:** is it declared and referenced properly?
6. **Additivity:** is it disabled at some level without a receiving appender?
7. **Filter:** is ThresholdFilter, LevelFilter, or TurboFilter blocking anything?
8. **Target:** System.out or System.err? Are the terminal and redirects watching the right stream?
9. **Encoding:** do the charsets on the encoder and terminal/collector match?
10. **Collection:** are buffering, drops, latency, or retention preventing the record from being found?

If logs appear duplicated, check **appender-ref and additivity** before concluding that business logic ran twice. If errors lack stack traces, check how the Throwable is passed and how the encoder is configured.

## 17. Self-Check Questions

**Question 1.** Does Logback's ConsoleAppender default to stdout or stderr?

**Answer:** Typically **System.out**. You can set target to System.err. JUL ConsoleHandler has a different default, which is stderr.

**Question 2.** There is a ConsoleAppender in logback.xml, but no appender-ref. Is it guaranteed that logs will be printed?

**Answer:** No. A logger/root route must reference the appender, and the event must pass level and filter checks.

**Question 3.** Will a DEBUG logger with an appender ThresholdFilter WARN print DEBUG?

**Answer:** No. The appender discards events lower than WARN.

**Question 4.** Root is INFO and a child logger is DEBUG; the appender on root has no filter. Can the child's DEBUG be printed?

**Answer:** Yes. Root does not re-filter events already accepted by a child logger; additivity carries the event to root's appender.

**Question 5.** Why might a single event be printed twice?

**Answer:** The same appender may be referenced on both a child logger and root while additivity remains enabled.

**Question 6.** To send ERROR only to stderr, is it enough to create two appenders with different targets?

**Answer:** No. You must add filters to prevent ERROR from going to both stdout and stderr.

**Question 7.** Does ConsoleAppender perform file rotation itself?

**Answer:** No. It writes to a console stream; rotation is handled by FileAppender/RollingFileAppender or the stream collection infrastructure.

**Question 8.** Why can LOG.debug("x={}", expensive(x)) still consume CPU when DEBUG is disabled?

**Answer:** Java evaluates the argument expensive(x) before the call. Guard expensive computations when needed.

**Question 9.** Is it safe to log tokens at DEBUG because production runs at INFO?

**Answer:** No. Levels can be changed and logs may be collected in other environments. Never log secrets at any level.

**Key Takeaway:** **ConsoleAppender is an output destination for logging to stdout/stderr.** For an event to reach the console, look at the entire path: **Logger/effective level → additivity → appender/filter → encoder/charset → target → collector**. A simple, consistent configuration verified at runtime is usually better than an unnecessarily complex web of appenders.
