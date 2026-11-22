# What Is Logback? Architecture and Usage in Java

**Logback** is a logging framework for Java used to **receive, filter, format, and output log events** to the console, files, or other destinations. In Java applications, Logback typically serves as the **logging backend** for the **SLF4J** (*Simple Logging Facade for Java*) API. Business code calls `org.slf4j.Logger` to emit events; Logback is the component that executes the processing of those events based on configuration.

For example, when an order service calls `LOG.info("Order {} accepted", orderId)`, the call uses the SLF4J API. If the application selects `logback-classic` as its provider/backend, Logback decides whether the record is accepted based on its level, whether it is routed to the console or a file, and how it is formatted. Do not confuse SLF4J (the API/facade) with Logback (the implementation).

## 1. What Problems Does Logback Solve?

When using only `System.out.println(...)`, an application struggles to control detail levels, log routing, stack traces, formatting, and different configurations between development and production environments. Logback provides the following core capabilities:

- **Log levels**: distinguish `TRACE`, `DEBUG`, `INFO`, `WARN`, and `ERROR`, configurable per logger or package.
- **Named loggers**: name loggers by class or functional area, such as `com.example.orders.OrderService`, for filtering and searching.
- **Appenders**: output logs to the console or files; multiple destinations can be attached with different rules.
- **Encoders/layouts**: determine what each record looks like, such as timestamp, thread, level, logger name, message, and exception.
- **Configuration inheritance and additivity**: apply levels by namespace and decide whether an event is propagated to parent logger appenders.
- **Rolling files**: create file generations by time and/or size to reduce the risk of a single file growing indefinitely.
- **MDC** (*Mapped Diagnostic Context*): attach thread-scoped contextual data, such as `requestId`, to correlate logs.
- **AsyncAppender and filters**: control the writing pipeline and avoid blocking business threads in certain cases.

Logging does not inherently guarantee that every record is stored permanently: events can be filtered out, lost when a process crashes, dropped from an async queue, or replaced during retention/rotation. Critical auditing requires separate durability designs and controls.

## 2. Relationship Between SLF4J and Logback

Consider the following flow:

```text
Java application code
  |
  | org.slf4j.LoggerFactory.getLogger(...)
  | logger.info("event=order.accepted id={}", id)
  v
SLF4J API (facade)
  |
  | Provider selected at runtime
  v
Logback Classic
  |
  +--> Logger hierarchy / effective level / TurboFilter
  |
  +--> Logging event
          |
          +--> ConsoleAppender --> Encoder --> stdout/stderr
          |
          +--> RollingFileAppender --> Encoder --> rolling file
```

**Modules/components to distinguish:**

| Component | Role |
| --- | --- |
| `slf4j-api` | API for application code; contains `Logger`, `LoggerFactory`, MDC, and logging methods. |
| `logback-classic` | Logging implementation following the Logback model for SLF4J; manages logger context, levels, and events. |
| `logback-core` | Shared infrastructure for appenders, encoders, policies, and configuration components; used by Classic. |
| `logback-access` | Module related to HTTP access logging, separate from regular application logging flows; support/integration level depends on version and environment. |
| `logback.xml` | Common Logback configuration file on the classpath; declares appenders, encoders, levels, and the root logger. |

When declaring the Maven dependency `logback-classic`, required dependencies such as `logback-core` and `slf4j-api` are typically pulled in transitively. Do not add multiple competing SLF4J providers unintentionally.

### SLF4J 1.x and 2.x

With **SLF4J 2.x**, the backend is discovered via a **provider** mechanism (typically through `ServiceLoader`); Logback Classic lines compatible with SLF4J 2.x supply the corresponding provider. In older ecosystems, SLF4J 1.7 used a different binding mechanism. Therefore, when seeing warnings about providers or bindings, check the **actual version pairing** rather than adding random JARs.

A working combination on Java 17 is illustrated below using Logback Classic **1.5.18**. This is a **fixed version for the hands-on exercise, not claimed to be the latest release**. When upgrading in a real project, consult the release notes, Java baseline, SLF4J compatibility, and security advisories.

## 3. Core Concepts in Logback

| Term | Practical Meaning | Example |
| --- | --- | --- |
| **Logger** | Object that emits events with a stable name, usually by class. | `com.example.orders.OrderService` |
| **Logging event** | A single log record containing level, message, timestamp, thread, exception, and context. | `event=order.accepted orderId=42` |
| **Level** | Importance threshold for selecting which records to output. | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| **Appender** | Output destination or processing pipeline for logs. | `ConsoleAppender`, `FileAppender`, `RollingFileAppender` |
| **Encoder** | Converts a logging event into bytes for an appender to write, commonly using a pattern. | `PatternLayoutEncoder` |
| **Layout** | Produces a text representation from an event; an encoder may use a layout. | `PatternLayout` |
| **Filter** | Accepts or denies an event based on additional conditions. | `ThresholdFilter`, `LevelFilter` |
| **Root logger** | The top-level logger in the hierarchy, usually defining the default level and appenders. | `<root level="INFO">` |
| **Additivity** | Determines whether parent logger appenders continue receiving events from a child logger. | `additivity="false"` |
| **MDC** | Key/value context typically bound to the current execution thread. | `requestId=req-17` |
| **Rolling policy** | Policy for rotating files and managing history. | `SizeAndTimeBasedRollingPolicy` |

Logger names should not contain dynamic data such as request IDs or user IDs. A single logger named `com.example.orders.OrderService` can emit countless events; the specific entity being processed belongs in the message or a separate field/context.

## 4. Levels and Parent–Child Logger Relationships

Common levels in Logback Classic, from most detailed to most severe:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

An `INFO` threshold typically allows `INFO`, `WARN`, and `ERROR`, while filtering out `TRACE` and `DEBUG`. Logback also has special values such as `ALL` and `OFF` for configuration purposes. **There is no standard `fatal()` method on the common SLF4J API**; do not assume that other levels from Log4j 2 are supported identically.

Named loggers form a hierarchy separated by dots:

```text
ROOT
└── com
    └── example
        ├── orders
        │   ├── OrderService
        │   └── OrderRepository
        └── payments
            └── PaymentService
```

This is a **logger name** hierarchy, not Java class inheritance. A configuration on `com.example.orders` can control logs for child loggers such as `com.example.orders.OrderService`. A child logger without its own explicit level inherits its **effective level** from the nearest ancestor that has a defined level.

Example:

```xml
<logger name="com.example.orders" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
```

This snippet **illustrates only part** of `logback.xml`, because the `STDOUT` appender must also be declared. Loggers under `com.example.orders` can emit `DEBUG`, while `com.example.payments` inherits `INFO` from root.

**Key point:** Once an event is accepted by a child logger according to its effective level, it can propagate to ancestor appenders. Setting root to `INFO` does not automatically re-filter a `DEBUG` event already accepted by `com.example.orders` when that event propagates to the root appender. However, if the appender has its own `ThresholdFilter` set to `INFO`, it can still drop `DEBUG`.

### Additivity and Duplicate Logging

By default, child loggers have **additivity=true**: in addition to any appender attached directly to the child logger, events propagate to ancestor appenders. For example, if the same `ConsoleAppender` or multiple appenders writing to the console are attached to both a child logger and root, a single event can appear twice.

When you genuinely need to isolate output:

```xml
<logger name="com.example.audit"
        level="INFO"
        additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
</logger>
```

This is an **illustrative** configuration snippet, assuming the `AUDIT_FILE` appender is already defined. `additivity="false"` stops propagation to ancestor appenders; it **does not stop level inheritance**. Furthermore, naming a logger `audit` does not by itself guarantee durable storage, tamper resistance, or compliance with legal audit requirements.

## 5. Appenders and Encoders: Where Does Logback Output Data?

Appenders decide where events are sent. Encoders decide the byte format of each record before writing.

| Appender | Purpose | Notes |
| --- | --- | --- |
| `ConsoleAppender` | Outputs logs to the console (usually stdout; configurable to stderr). | Suitable for containers with a log collector. |
| `FileAppender` | Writes to a specified file. | Requires managing disk space, write permissions, and lifecycle. |
| `RollingFileAppender` | Writes to a file and rotates it according to a rolling policy. | Rollover/retention policies must match traffic volume. |
| `AsyncAppender` | Places events into a queue for a downstream appender to process. | May drop logs under overload or shutdown; not equivalent to durable writes. |

### PatternLayoutEncoder

A common console configuration:

```xml
<appender name="STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

Meaning of the pattern specifiers:

| Specifier | Effect |
| --- | --- |
| `%d{HH:mm:ss.SSS}` | Event timestamp formatted as hour:minute:second.millisecond; configure explicitly if UTC/timezone is needed. |
| `%-5level` | Level left-aligned with a minimum width of 5 characters, e.g., `INFO `, `WARN `, `ERROR`. |
| `%thread` | Name of the thread that generated the event. |
| `%logger{36}` | Logger name shortened when necessary according to pattern rules. |
| `%msg` or `%message` | Message formatted with SLF4J parameters. |
| `%n` | Platform-appropriate line separator. |
| `%ex` / `%exception` | Exception/stack trace details, used when explicit control over the throwable output is needed. |
| `%X{requestId}` | The `requestId` field from MDC if present; empty if not set. |

Plain text pattern logs are useful for human readers, but they **do not automatically become JSON with structured fields**. If a system requires structured logs, you must use an encoder/provider or structured field mechanism compatible with your Logback version and collection pipeline.

For exceptions, pass the `Throwable` using the proper API, e.g., `LOG.error("event=payment.failed id={}", id, ex)`. Logback formats throwables through the pattern/encoder; if you write a custom formatter that only outputs `%msg` and drops the throwable, or if your pipeline strips stack traces, you can lose diagnostic evidence. Always inspect the actual output, not just the API call.

## 6. logback.xml: Where to Place Configuration

Standard Java applications place `logback.xml` in `src/main/resources` so Maven packages it onto the classpath. Logback can also use `logback-test.xml` for tests; configuration lookup follows the priority rules of Logback and the active ecosystem.

Example of a complete basic configuration:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Explanation:

1. `STDOUT` is the name of the console appender, referenced by root via `appender-ref`.
2. The encoder prints three parts: level, logger name, and message; it omits the timestamp to make comparison easy in learning examples.
3. The `demo.orders` namespace has level `DEBUG`, and child loggers inherit it unless overridden.
4. Root is at `INFO`, so other namespaces like `demo.billing` will generally not print `DEBUG`.
5. Events from `demo.orders` reach the console through the root appender thanks to default additivity; there is no need to attach `STDOUT` again on the child logger.
6. This is a **demo configuration**, not a full production-ready pattern. Real systems typically need timestamps with timezones, thread names, correlation/trace IDs, and data-sensitivity policies.

**Environment note:** Spring Boot provides additional logging configuration utilities such as `logback-spring.xml` when using Logback. Do not blindly apply Spring Boot extensions to a plain Java application. If a framework reconfigures logging at runtime, the effective XML configuration and levels may differ from expectations.

## 7. Java 17 Hands-On: Maven Application Using SLF4J + Logback

This is a **standalone runnable example** using JDK 17 and Maven to download dependencies. For deterministic output, the program logs only events with fixed values; the console pattern omits timestamps and thread names. The `logback.xml` file is placed on the classpath.

### 7.1. Project Structure

```text
logback-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackDemo.java
        └── resources/
            └── logback.xml
```

### 7.2. pom.xml

Save the following content as `pom.xml`. Version `1.5.18` is pinned solely to make the lesson reproducible; real-world projects should choose a supported version compatible with their other dependencies.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>logback-demo</artifactId>
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
                    <mainClass>demo.LogbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` pulls in the required logging dependencies such as Logback Core and SLF4J API via the Maven dependency graph. Large projects usually manage versions through a BOM or dependency management to avoid having multiple incompatible providers/bindings on the same classpath.

### 7.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

### 7.4. src/main/java/demo/LogbackDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogbackDemo {
    private static final Logger ORDERS =
            LoggerFactory.getLogger("demo.orders.OrderService");
    private static final Logger BILLING =
            LoggerFactory.getLogger("demo.billing.PaymentService");

    public static void main(String[] args) {
        ORDERS.debug("event=order.validated orderId={}", "ord-42");
        ORDERS.info("event=order.accepted orderId={}", "ord-42");

        // BILLING inherits the root INFO level, so DEBUG is suppressed.
        BILLING.debug("event=payment.debug_suppressed");

        BILLING.warn(
                "event=payment.retry paymentId={} attempt={}",
                "pay-7",
                2
        );
    }
}
```

### 7.5. Compile and Run

Open a terminal in the directory containing `pom.xml` (requires JDK 17 and Maven installed; on the first run Maven may need network access to download dependencies):

```bash
mvn -q compile exec:java
```

**Standard output from the program** with the exact `logback.xml` above (excluding any Maven-specific messages, if any):

```text
DEBUG | demo.orders.OrderService | event=order.validated orderId=ord-42
INFO | demo.orders.OrderService | event=order.accepted orderId=ord-42
WARN | demo.billing.PaymentService | event=payment.retry paymentId=pay-7 attempt=2
```

Result explanation:

1. `ORDERS` belongs to the `demo.orders` prefix, which is configured at `DEBUG`. Therefore, both DEBUG and INFO are logged.
2. `BILLING` is on a different branch and inherits `INFO` from root; the DEBUG event from BILLING is not printed.
3. `BILLING.warn(...)` creates a WARN event, which is higher than INFO and is therefore output.
4. Both loggers propagate events to `STDOUT` on root due to default additivity. Root does not re-filter the DEBUG level already accepted by ORDERS; the appender has no `ThresholdFilter`, so it still writes it.
5. The `{}` placeholder is substituted by SLF4J with the arguments; JUL's `{0}` syntax is not used in this code.
6. The `%level | %logger | %msg%n` pattern produces deterministic output without generating random timestamps. In production, add fields that support investigation.

**Key takeaway when running:** Java code imports only `org.slf4j.*`, not Logback's internal classes. This allows switching backends without modifying every log call, even though backend configuration and advanced features still differ.

## 8. Writing Logs to Files and Rotating with RollingFileAppender

`FileAppender` writes to a file; `RollingFileAppender` combines a rolling policy to create file generations by time and/or size. The configuration example below uses `SizeAndTimeBasedRollingPolicy`, which is suitable when you need daily rotation **and** size-threshold rollover.

This is an **illustrative configuration snippet to place inside `<configuration>`**, rather than a standalone `logback.xml`. The appender must be referenced by a logger or root to receive events:

```xml
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Parameters:

- `file`: the active file being written to, e.g., `logs/application.log`.
- `fileNamePattern`: naming pattern for archived files; `%d` represents the date of the rollover period; `%i` is the file index within the same period when the size threshold is exceeded; `.gz` indicates compression of archived files.
- `maxFileSize`: threshold used for size-based rollover within a period; the limit is not a byte-exact guarantee and depends on event sizes.
- `maxHistory`: number of history periods to retain according to the rolling policy, not necessarily an exact count of individual files.
- `totalSizeCap`: total size cap for archived logs enforced by the rolling policy's cleanup; not a disk-full alerting system or an instantaneous hard quota.
- `encoder`: formats file content; can be replaced with an encoder suited to your log collection system.

This configuration assumes the log directory can be created or accessed with appropriate permissions in the deployment environment. History cleanup is typically tied to rollover or cleanup configuration; **do not assume old files are deleted strictly on a calendar schedule if no corresponding logging/rollover events occur**.

Rotation is different from legal retention, backup, and integrity. A well-configured rolling file still does not guarantee that events survive disk failure or interruptions in a centralized logging system.

## 9. MDC: Adding Request IDs Without Changing Logger Names

When a request traverses multiple layers, `requestId` or `traceId` helps correlate logs from the same flow. With SLF4J, MDC is commonly used to attach key/value pairs to the execution context:

```java
// Illustrative snippet inside a method; LOG and requestId must exist.
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    LOG.info("event=order.created orderId={}", "ord-42");
} finally {
    MDC.remove("requestId");
}
```

The snippet above is **not a standalone program**; the `import` statement must be placed at the top of the file in real code. In the Logback pattern, you can add `%X{requestId}`:

```xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
```

For a request with `requestId=req-17`, the event can be output as `INFO requestId=req-17 ...`. If no request ID is present, the field in the pattern will be empty. Only attach identifiers that are safe to store in the logging system; never use tokens or sensitive data as correlation IDs.

**Important note on concurrency:** MDC is typically bound to the current thread/context and does not automatically propagate across all `ExecutorService`, `CompletableFuture`, reactive pipelines, or virtual threads. You need an appropriate propagation mechanism when tasks switch execution contexts, and you must always clear MDC after a request to avoid leaking IDs across requests. When using an async appender, check the backend documentation on when MDC data is captured for a logging event.

## 10. AsyncAppender and Its Impact on Durability

When appenders write to files, the console, or the network with I/O, business threads can become blocked. Logback's `AsyncAppender` places events into a queue so a worker thread can forward them to the target appender.

Diagram:

```text
Request thread
  |
  | LOG.info(...)
  v
AsyncAppender (queue)
  |
  v
Worker thread
  |
  v
ConsoleAppender / FileAppender
```

Points to keep in mind:

- Async reduces I/O work on the caller thread in many scenarios, but still incurs the cost of creating the event and enqueuing it.
- When the queue is full, depending on Logback configuration, events may be discarded or the caller may block; understand `discardingThreshold`, `neverBlock`, and event priority before choosing.
- If the process crashes abruptly, events remaining in the queue can be lost. During normal shutdown, proper lifecycle shutdown and time for the worker to flush are required.
- Async does not guarantee global log ordering across multiple JVMs or different destinations.
- Do not use regular async logging as a substitute for a transaction journal or audit storage that requires durability.
- Benchmark under realistic load and calculate data volume; do not enable async simply because the name sounds faster.

## 11. How Do Logback, JUL, and Log4j 2 Differ?

| Criterion | JUL (`java.util.logging`) | Logback | Log4j 2 |
| --- | --- | --- | --- |
| Built into the JDK | Yes | No; requires dependency | No; requires dependency |
| Common calling API | `java.util.logging.Logger` | Usually `org.slf4j.Logger` | Log4j 2 API or another facade, depending on integration |
| Configuration | `logging.properties` or Java API | `logback.xml`, framework-specific integration | Log4j 2's own configuration formats |
| Output target | `Handler`, e.g., `ConsoleHandler`, `FileHandler` | `Appender`, e.g., `ConsoleAppender`, `RollingFileAppender` | Log4j 2 `Appender` |
| Common levels | `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`... | `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | Includes Log4j 2's own levels and features |
| Usage with SLF4J | Requires an appropriate backend/bridge to route through SLF4J | Logback Classic is a common backend | Can use an appropriate provider/adapter |

**Do not assume JUL loggers automatically output through Logback.** Calls to `java.util.logging.Logger.getLogger(...)` still go through JUL unless a proper bridge is configured. When integrating bridges, avoid forwarding loops (for example, using bidirectional bridges simultaneously can create infinite recursion).

Choose a tool based on existing dependencies, required control, operational policies, and integration capabilities; there is no single right choice for every application.

## 12. Good Logging Practices When Using Logback

1. **Name loggers by class:** e.g., `LoggerFactory.getLogger(OrderService.class)` instead of `getLogger("order-" + requestId)`. Stable names make package-level management possible.
2. **Choose levels by outcome:** INFO for meaningful milestones, WARN for degradations that need observation, ERROR for actual failures; DEBUG/TRACE for diagnostics. Do not log ERROR for every exception if a fallback succeeded.
3. **Use parameterized logging:** `LOG.info("orderId={}", orderId)` instead of unnecessary string concatenation. Argument expressions are still evaluated by Java before the call, so genuinely expensive computations need `isDebugEnabled()` or an appropriate lazy mechanism.
4. **Pass `Throwable` properly:** `LOG.error("event=checkout.failed orderId={}", orderId, ex)` so the backend can print the stack trace and cause.
5. **Avoid duplicate logging:** define which layer is ultimately responsible for reporting an error; check additivity and appenders to prevent the same event from appearing multiple times.
6. **Separate configuration by environment:** enable DEBUG for namespaces under investigation with clear scope and duration; do not leave TRACE enabled system-wide long-term.
7. **Protect sensitive data:** never put passwords, tokens, session cookies, private keys, or full personal data into logs. Also guard against stack traces/exception messages and inputs containing newline characters.
8. **Monitor overhead:** log levels, encoders, file rotation, async queues, retention, and disk usage all need monitoring.
9. **Optimize searchability:** standardize `event` names, error codes, `requestId`, `traceId`, `durationMs`, and units. Use proper structured logging if you need field-level queries rather than concatenating JSON strings manually.
10. **Verify actual output:** run the application with production-equivalent configuration, inspect console/file output, and test errors with a Throwable to confirm stack traces are preserved.

## 13. Common Errors and How to Troubleshoot

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| SLF4J reports no provider found | Only `slf4j-api` was added, backend missing or version mismatch. | Inspect the dependency graph and add **one** compatible provider such as `logback-classic`. |
| Warning about multiple providers/bindings | Classpath contains multiple backends for the same facade. | Remove extra dependencies; check whether SLF4J 1.x or 2.x is in use. |
| DEBUG logs not appearing | Effective level is INFO; appender has a filter; a different config was loaded. | Check logger name, level hierarchy, filters, and runtime config file. |
| Same line printed twice | Appender is referenced at multiple levels with additivity enabled; or multiple pipelines write to the same target. | Inspect root/logger appenders and `additivity`. |
| Message appears without stack trace | Only `ex.getMessage()` was logged, or encoder/pipeline stripped the throwable. | Pass the `Throwable` using the proper API and check the final output format. |
| Log file is not created | FILE appender is not referenced, invalid path/write permissions, or misconfigured rolling policy. | Check Logback internal status, write permissions, working directory, path, and config. |
| XML config has no effect | `logback.xml` is not on the classpath, overridden by framework, or malformed structure. | Check `src/main/resources`, active configuration, and Logback status. |
| App does not use Logback despite JAR | Another backend is active, or code uses JUL directly. | Check SLF4J providers, bridges, and the framework's logging stack. |
| File grows too large or history disappears early | Missing or mismatched rolling/retention config, high traffic volume. | Review rolling policy, `maxHistory`, `totalSizeCap`, file paths, and collectors. |
| Request IDs mixed up or missing | MDC not cleared or not propagated across executors/tasks. | Use `try/finally` to clear context, and add controlled propagation. |
| Logging slows down the service | Too many events, expensive message construction, synchronous I/O, or overloaded async queue. | Profile and measure, adjust levels, batching/async settings, and log volume as needed. |

### Configuration Diagnostics

When you cannot tell why a configuration has no effect, look for **Logback's internal status**, XML parsing errors, and attached appenders. You can enable additional status output during investigation (depending on version/configuration), but do not put sensitive data into configuration files just to see debug output. Some setups support scanning and reloading configuration, such as the `scan` option; test this in a realistic environment so it does not cause unexpected changes in production.

## 14. Self-Check Checklist

After completing this lesson, answer these questions for yourself:

- At what layer do SLF4J and Logback differ? If only `slf4j-api` is present, what outputs the logs?
- Why must Logback Classic be paired with a compatible version of the SLF4J API/provider?
- Why can an event from `demo.orders.OrderService` output DEBUG even when root is set to INFO?
- Does `additivity="false"` affect appender propagation or effective level?
- Why does an appender need an encoder and a pattern like `%msg%n`?
- What is the difference between `FileAppender` and `RollingFileAppender`? Does rotation equal retention?
- Should `requestId` be placed in the logger name, the message, or an MDC/structured field?
- How can you tell whether code using JUL directly actually routes through Logback?
- What information can be lost when an exception is logged using `ex.getMessage()`?
- When an `AsyncAppender` queue is full or the process crashes abruptly, are events still guaranteed to be saved?

**Conclusion:** Logback is the **logging engine** in the Java ecosystem; SLF4J is typically the **API called by business code**. Understanding loggers, levels, appenders, encoders, configuration, and context helps you produce operationally valuable logs that avoid duplication, stay free of excessive noise, and remain effective for incident investigation.
