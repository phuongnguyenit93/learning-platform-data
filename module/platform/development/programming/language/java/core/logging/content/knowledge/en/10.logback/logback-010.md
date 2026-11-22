# When Should You Use Logback in a Java Application?

## 1. Quick Answer: When to Choose Logback?

**Logback** is a logging backend for Java, commonly used behind the **SLF4J** API. When application code calls `org.slf4j.Logger`, Logback can perform level-based filtering, event formatting, routing to console/file, and management of multiple output targets. You should consider Logback when developing a **long-running Java application** that needs clear, flexible logging configuration consistent with the libraries/frameworks in use.

**Logback is a good fit if** the application:

- Has standardized logging calls using **SLF4J** and needs a full-featured backend rather than simple log printing.
- Needs to adjust log levels per package/class, for example temporarily enabling DEBUG for the payment module while keeping the rest of the application at INFO.
- Needs **Appender, Filter, Encoder/Layout**, console or file output targets, and rolling/retention policies when writing to files.
- Needs **MDC** to include `requestId`, `traceId`, `jobId` across multiple log lines of an execution flow.
- Is using **Spring Boot with its default Logback-based logging configuration**, and there is no compelling reason to switch backends.
- Wants to separate business code from output destinations and formatting: application code calls SLF4J, while Logback configuration governs operations.

**Logback is not always necessary.** A small one-off Java tool may only need the JDK's `java.util.logging` (JUL) or `slf4j-simple`; reusable Java libraries should generally depend only on the **SLF4J API**, without choosing a backend for the consuming application. For systems already running Log4j 2 with stable configuration and operations, there is no default benefit that forces a switch to Logback.

Key point to remember: **Logback is not synonymous with SLF4J**. SLF4J is an API/facade; Logback is an implementation/backend. A program can use the SLF4J API while actually logging through Logback, Log4j 2, JUL, or another provider.

## 2. Logback's Place in the Logging Architecture

A common setup:

```text
Business code
  |  LoggerFactory.getLogger(...), logger.info(...), logger.error(...)
  v
SLF4J API
  |
  |  A compatible SLF4J provider
  v
Logback Classic
  |
  +-- Logger hierarchy / effective level
  +-- Filters / TurboFilters
  +-- MDC, logging event
  |
  +--> ConsoleAppender --> Encoder --> stdout/stderr
  |
  +--> RollingFileAppender --> Encoder --> rolling file
  |
  +--> AsyncAppender --> Target appender
```

Main components:

| Component | Responsibility |
| --- | --- |
| `slf4j-api` | API for application code to emit logs without tight coupling to a backend |
| `logback-classic` | The Logback layer that integrates with SLF4J and manages Loggers/levels/events |
| `logback-core` | Foundation for Appenders, Encoders, and many Logback implementation components |
| Logger | Receives events and decides which levels are accepted according to the effective configuration |
| Appender | Delivers events to a destination: console, file, or another appender |
| Encoder/Layout | Transforms events into text or a format supported by collectors |
| Filter/TurboFilter | Filters events based on conditions |
| MDC | Context attached to the execution thread, which can be included in patterns/output |

In the common Logback model, **Loggers are named after packages/classes** and typically inherit levels from ancestors when not explicitly set; **additivity** determines whether an event is forwarded to parent logger appenders. Do not confuse level inheritance with duplicating appenders: an appender can be attached at the root so multiple loggers share it.

An event can pass through a Logger yet **not appear at the destination** if an appender has a filter, is affected by async/buffer policies, or if the storage target fails. Calling `logger.info(...)` does not guarantee that the log has been durably written to disk or a centralized system.

## 3. Decision Table: Logback or Another Solution?

| Scenario | Usually Reasonable Choice | Reason |
| --- | --- | --- |
| Small Java program needing only a few diagnostic lines, no external dependencies wanted | JDK's `java.util.logging` | Built-in, sufficient basic levels/handlers/formatters |
| Small CLI already using SLF4J, needing only simple output | `slf4j-simple` | Minimal configuration; suitable for simple needs |
| Java web service with multiple packages, environments, and log targets | **Logback** | Easy to configure logger hierarchy, appenders, filters, and encoders |
| Spring Boot application using the default logging starter | **Keep default Logback** if it meets requirements | Avoids unnecessary backend switches, leverages built-in integration |
| Project already running Log4j 2 smoothly | Usually **keep Log4j 2** | Avoid migration just for preference; compare actual requirements |
| Java library shared across multiple applications | Declare only **`slf4j-api`** | The backend should be decided by the consuming application |
| System needing special features of a specific backend/encoder/appender | Evaluate Logback and Log4j 2 against requirements | Compatibility and load-test results matter more than slogans |
| Audit logging requiring transactionality, durability, and tamper resistance | Design a dedicated **audit trail** | Standard appenders do not provide transactional/audit guarantees |

You should not assume Logback is **always faster** than Log4j 2, **always lighter** than JUL, or the only choice for production. Performance depends on workload, formatter, appender, I/O speed, synchronous/asynchronous mode, filter configuration, and how benchmarks are run.

### 3.1. Signs You Do Not Need a Full Backend Yet

If the application is just a tool performing a short task with a few log lines and no need for runtime configuration changes, JUL can suffice. Adding Logback brings along dependencies, configuration files, and management overhead. "Using a more feature-rich framework" is not an engineering goal in itself.

Conversely, as an application grows and needs to categorize events by module, attach context, coordinate multiple destinations, or swap logging backends without modifying business code, **SLF4J + Logback** is a clear design choice.

### 3.2. When Another Backend Is Already Chosen

If a system already uses Log4j 2 or a platform logging service, review any unmet capabilities: format, throughput, appender/plugin support, lifecycle, tracing, and framework integration. Any decision to switch to Logback should be based on concrete gaps, a migration plan, testing, and operational cost — not merely because Logback is popular.

## 4. When You Need Per-Module Log Configuration

In a simple backend, changing the level often affects the entire program. With Logback, you can keep root at `INFO` and open `DEBUG` specifically for one branch:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is a **complete `logback.xml` file example** for a console appender; the demo application in Section 8 uses a different configuration file for deterministic stdout. Meaning:

- Loggers without their own configuration use the effective level from their ancestor/root.
- Loggers under `com.example.payment` can emit `DEBUG` while the rest use `INFO`.
- The appender attached at root receives events propagated to root via additivity.
- `%logger{40}`, `%thread`, `%d`, `%msg`, `%n` are Logback pattern converters, not SLF4J parameter placeholders.

**Be careful:** writing `<logger name="com.example.payment" level="DEBUG"/>` does not automatically create a separate file. It only changes the policy of that branch Logger; the Appender and routing configuration determine where output goes.

### 4.1. Level and Additivity

For example, if you attach an appender to a child Logger **and** to root while leaving additivity enabled, events can pass through both appenders and produce duplicate output. If you genuinely want a module to write to a dedicated destination, you can use:

```xml
<logger name="com.example.payment" level="DEBUG" additivity="false">
    <appender-ref ref="PAYMENT_FILE"/>
</logger>
```

This is an **XML snippet inside `<configuration>`** and assumes `PAYMENT_FILE` is already declared. `additivity="false"` stops forwarding events from this branch to ancestor appenders. Misusing it when the branch Logger **has no appender of its own** will leave events with no output destination.

`additivity` concerns propagating events to parent appenders, **not** disabling level inheritance. When setting levels or additivity, test `DEBUG`, `INFO`, `WARN`, and `ERROR` rather than observing only a single log line.

## 5. When You Need MDC and Correlation IDs Across Requests

A web application handling concurrent requests often needs `requestId` or `traceId` to identify events:

```text
INFO  requestId=req-61 event=request.received
INFO  requestId=req-62 event=request.received
WARN  requestId=req-61 event=payment.retry
INFO  requestId=req-62 event=request.completed
```

**MDC (Mapped Diagnostic Context)** lets you attach fields to the current thread's logging context instead of manually concatenating `requestId` into every message. A Logback pattern can use `%X{requestId}` to print the corresponding field.

Example **code snippet** using SLF4J and an existing `logger`/`processRequest()` method:

```java
String oldRequestId = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    logger.info("event=request.received");
    processRequest();
} finally {
    if (oldRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", oldRequestId);
    }
}
```

You need to import `org.slf4j.MDC` along with a backend that supports MDC. The `finally` block restores the previous context, which works well for both nested scopes and thread pools. **Do not assume MDC automatically propagates across `ExecutorService`, `CompletableFuture`, or reactive pipelines**; if work runs on another thread, you must pass the context explicitly or use context propagation mechanisms from your framework/tracing library.

A `requestId` from an HTTP header must be validated for length, characters, and trustworthiness before being logged; never implicitly trust client-supplied values. MDC does not replace distributed tracing, though it can use `traceId`/`spanId` generated by a tracing library to correlate logs with traces.

**When Logback helps:** you want all logs for the same request to carry an ID via configuration, while business code only sets the context at processing boundaries. However, if the application only performs a simple task, you can pass the ID explicitly and skip MDC.

## 6. When You Need Multiple Output Targets, Rolling Files, and Retention

Logback supports `ConsoleAppender`, `FileAppender`, `RollingFileAppender`, and integration with other appenders in the ecosystem. You can output to:

- **Console stdout** for centralized collection by container runtimes/agents.
- **Files** when the system genuinely needs local persistence, write permissions, and a rotation process.
- **Specialized targets** via an appropriate appender, after accounting for network errors, buffering, and backpressure.

### 6.1. RollingFileAppender Example

When running an application that manages local log files, you can use this **configuration snippet inside `<configuration>`**:

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>14</maxHistory>
        <totalSizeCap>500MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

After declaring the appender, reference it from a Logger/root with `<appender-ref ref="FILE"/>` so events are routed to it. The policy above describes daily rollover, history limits, and total archive size cap; **it does not mean all filesystem and shutdown conditions guarantee zero data loss**.

Operational notes:

- The directory must be writable; disks can fill up; the application needs a monitoring strategy.
- Log files and archives should not reside on a shared volume across multiple instances unless the backend/rolling policy is designed for concurrent writes.
- In Kubernetes/containers/cloud environments, **writing to stdout/stderr and letting the platform handle collection/rotation is usually simpler** than writing rolling files on an ephemeral filesystem.
- Choose retention aligned with investigation needs and data regulations; overly long retention can retain sensitive data.
- For centralized systems, verify format parsing, clock/timestamps, trace IDs, and timezones.

**When to use Logback:** you need console/file/rolling configuration directly in the app, or want to use ecosystem-supported appenders/encoders. **Do not** force every containerized service to write local files just because Logback provides `RollingFileAppender`.

## 7. When You Need Asynchronous Logging and Controlled Performance

`AsyncAppender` is a Logback option that enqueues events and forwards them to a target appender on a worker thread. It can reduce application-thread blocking in some workloads, especially when the destination is slow. However, you must understand the risks:

- The queue has a **bounded capacity**; as it nears full, the discard policy may drop lower-level events as configured.
- When the queue is full, calls may block or drop events depending on `neverBlock` and related settings.
- A log call returning does not mean the event has been durably persisted.
- On an abrupt application shutdown, unprocessed events in the queue may be lost.
- MDC data and arguments must be captured at the right moment; mutable custom objects can change before the encoder processes them.

Example **XML snippet** wrapping an already-declared appender named `FILE`:

```xml
<appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

This is not a standalone `logback.xml`. To use it, reference `ASYNC` from a Logger/root and avoid simultaneously referencing `FILE` on the same path unless you want duplicate output. `discardingThreshold=0` disables normal threshold-based event dropping when queue space is low, but **does not guarantee zero log loss** on shutdown/crash or target appender failure; with `neverBlock=false`, application threads can block when the queue is full. Test under realistic load, and monitor queue depth and shutdown duration.

Logback also does not automatically turn logs into a reliable transactional pipeline. Audit events that require durability/immutability may need dedicated write mechanisms, transactions, access control, and separate storage.

**When not to enable async right away:** low event volume, fast-enough console output, applications needing simplicity, or when no benchmark has shown logging to be a bottleneck. Asynchrony adds complexity along with event-loss/blocking policies.

## 8. Standalone Java 17 Example Using Gradle and Logback

This hands-on example uses **Java 17, SLF4J API, and Logback Classic**. We create a small application with root level `INFO`, while enabling `DEBUG` for Logger `demo.detail`. The pattern prints level, logger name, `requestId` from MDC, and message for exact observation.

We use Logback version 1.5.18 as a **fixed baseline for this exercise**; that is not a claim that it is the latest version. In a real project, choose a supported version with security updates and centralized dependency management. `logback-classic` pulls in the required dependencies, including `logback-core` and a compatible SLF4J API version; no second provider is needed.

### 8.1. Directory Structure

```text
logback-choice-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackChoiceDemo.java
        └── resources/
            └── logback.xml
```

### 8.2. File settings.gradle

```groovy
rootProject.name = 'logback-choice-demo'
```

### 8.3. File build.gradle (Groovy DSL)

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
    implementation 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LogbackChoiceDemo'
}
```

The `application` plugin provides the `run` task. The Java toolchain requires an environment that has or can provision JDK 17. Logback is not part of the JDK, so Gradle must download dependencies from Maven Central or an organization-configured repository.

### 8.4. File src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level %logger requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.detail" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Notes:

- The resource name is `logback.xml` placed on the runtime classpath.
- `<target>System.out</target>` makes the appender write to stdout.
- `%X{requestId}` reads the MDC context.
- Root is at `INFO`, so `DEBUG` events on regular Loggers are dropped.
- Logger `demo.detail` is set to `DEBUG`; it needs no separate appender because additivity to root is enabled by default.
- `%-5level` prints the level left-aligned in a 5-character width, so `INFO` and `WARN` have one trailing padding space.

### 8.5. File src/main/java/demo/LogbackChoiceDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class LogbackChoiceDemo {
    private static final Logger APP =
            LoggerFactory.getLogger(LogbackChoiceDemo.class);
    private static final Logger DETAIL =
            LoggerFactory.getLogger("demo.detail");

    public static void main(String[] args) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            APP.info("event=order.created orderId={}", "ord-7");
            APP.debug("event=diagnostic.hidden");
            DETAIL.debug("event=cache.miss key={}", "product-8");
            APP.warn("event=payment.retry attempt={}", 2);
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

The code above uses SLF4J's `{}` placeholder, **not** `java.util.logging`'s `{0}`. Loggers are shared as `static final` fields, while per-request context lives in MDC rather than being turned into new Logger names.

### 8.6. Compiling and Running

In the `logback-choice-demo` directory, use a Gradle version compatible with Java 17:

```bash
gradle run --quiet
```

If the project already has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows instead. This example does not bundle a Gradle Wrapper; if Gradle is not pre-installed, prepare Gradle/JDK first.

**Program stdout when run with the exact configuration above:**

```text
INFO  demo.LogbackChoiceDemo requestId=req-42 - event=order.created orderId=ord-7
DEBUG demo.detail requestId=req-42 - event=cache.miss key=product-8
WARN  demo.LogbackChoiceDemo requestId=req-42 - event=payment.retry attempt=2
```

Analysis:

1. `APP.info` passes root `INFO`; `%X{requestId}` fills in `req-42`.
2. `APP.debug` does not appear because Logger `demo.LogbackChoiceDemo` has no explicit level, so its effective level is `INFO` from root.
3. `DETAIL.debug` still appears because Logger `demo.detail` has level `DEBUG`.
4. `APP.warn` prints `WARN` and the argument `2` is substituted into `{}` by SLF4J.
5. `finally` removes/restores MDC to prevent leaking request IDs if the thread is reused.
6. There is no timestamp/thread in the demo pattern so the output can be matched exactly. In production, include timestamp, service/instance, and fields required by your collection system.

If you change `<root level="INFO">` to `<root level="DEBUG">`, the `APP.debug("event=diagnostic.hidden")` call will appear. If you remove the `demo.detail` logger line, `DETAIL.debug` events will no longer appear while root remains `INFO`. This concretely illustrates the benefit of per-branch configuration without modifying application logic.

## 9. Logback in Spring Boot: When to Keep the Default?

Many Spring Boot applications use the default logging starter, which includes **Logback** as its backend, providing preconfigured logging and ecosystem integration. When a system already uses this backend stably:

- **You do not need to add `logback-classic` again** just to use `LoggerFactory.getLogger` or call `logger.info`.
- Prefer managing log levels via Spring Boot configuration for simple needs; use a custom Logback configuration only when you need specialized Appenders/Encoders/routing.
- With Logback configured through Spring Boot, formats and filenames can differ from plain Java applications. Some Spring Boot-specific features are supported via `logback-spring.xml`; do not assume you can put them into a plain `logback.xml` and expect every extension to work.
- If you choose to switch to Log4j 2, you must **exclude the default backend and add the appropriate logging starter/provider** per the documentation of your Spring Boot version, rather than simply adding Log4j 2 alongside Logback.

In plain Java, `logback.xml` on the classpath is the typical choice. In Spring Boot, configuration management adds an environment/starter layer, so check the runtime backend and framework conventions.

### 9.1. Ensuring a Single, Version-Matched SLF4J Provider

Modern Logback Classic implements a provider for **SLF4J 2.x**. If `slf4j-simple`, `slf4j-nop`, or `log4j-slf4j2-impl` are also present on the runtime classpath as providers, SLF4J may warn about **multiple providers**; if the NOP provider is selected, logs may be discarded.

In SLF4J 1.7.x, the legacy mechanism was `StaticLoggerBinder`; SLF4J 2.x uses `ServiceLoader`. Do not mix generations arbitrarily. In a production application, intentionally keep **one backend/provider** and inspect bridging dependencies.

Gradle diagnostic commands:

```bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --configuration runtimeClasspath --dependency logback-classic
```

Maven:

```bash
mvn dependency:tree
```

These are inspection commands for **existing projects**, not required steps for the demo if no errors occur. In multi-module applications, inspect `runtimeClasspath` of the startup module as well as `testRuntimeClasspath` if warnings only appear when running tests.

## 10. Structured Logging and Collection Systems

Logback can output pattern-based text, but **pattern text is not inherently structured JSON**. When you need to query by fields such as `traceId`, `requestId`, `errorCode` and reliably measure results, use an encoder that supports schema-backed JSON, safe escaping, proper numeric/boolean types, and compatibility with your collection system.

A structured event might carry:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment.failed",
  "requestId": "req-42",
  "errorCode": "GATEWAY_TIMEOUT",
  "durationMs": 450
}
```

This is an **illustrative JSON example**, not the automatic output of the `logback.xml` configuration in Section 8. Some JSON encoders require additional dependencies and dedicated configuration; choose a solution supported by your current backend/framework, and do not manually concatenate JSON strings with untrusted data.

Beyond logs, you should also have **metrics** (error rate, latency, throughput) and **traces** (paths across multiple services). Logback is a logging backend, not a replacement for the entire observability stack.

### 10.1. Securing Log Content

Regardless of backend, enforce these principles:

- Never log passwords, tokens, cookies, secret keys, card details, or payloads containing sensitive data.
- Select context fields via an allowlist; avoid calling `toString()` on DTOs that might contain secrets.
- Escape/sanitize client-supplied values to prevent **log injection** via newlines or control characters.
- Avoid logging stack traces at every layer if the same error is already logged at an appropriate handling boundary.
- Manage log read permissions, retention periods, and data transfer to collectors.
- Do not use production appenders to automatically record personal data without a valid purpose and proper access controls.

Formatters/encoders can help mask data, but the best approach is **not putting secrets into log events in the first place**. A custom layout cannot guarantee finding every secret hidden inside an exception or serialized object.

## 11. Operational Costs and Known Limitations

### 11.1. Misconfiguration Can Drop or Duplicate Logs

- Child Logger has its own appender and still has additivity to root: **duplicate logs**.
- Additivity disabled when the child Logger has no appender of its own: **logs have no destination**.
- Root set to `INFO` and Logger set to `DEBUG`, but an appender has a blocking filter: **`DEBUG` is not emitted**.
- NOP provider selected or multiple SLF4J providers present: **actual backend does not match intent**.
- Logs pushed into `AsyncAppender` but the process crashes before writing: **events may be lost**.

Verify the full pipeline from SLF4J call -> logger level/filter -> appender -> encoder -> stdout/file/collector; do not stop at checking that `logger.isDebugEnabled()` returns `true`.

### 11.2. Performance Does Not Come Automatically from the Backend Name

Logging cost includes level checks, argument/message construction, MDC snapshots, formatting, stack traces, I/O, queues, and collectors. SLF4J's `{}` placeholders defer standard string formatting, but **Java expressions passed as arguments are still evaluated before the call**.

Example:

```java
logger.debug("state={}", expensiveSnapshot());
```

This is an **illustrative snippet**, assuming `logger` and `expensiveSnapshot()` are already defined. `expensiveSnapshot()` still runs even when DEBUG is disabled. If the computation is expensive, consider:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveSnapshot());
}
```

Logback does not make every computation in a Java expression automatically lazy. Also, never place business side effects inside computations meant only for logging.

### 11.3. Deployment and Lifecycle

For long-running servers, consider flushing/stopping the logging context on graceful shutdown, handling I/O errors, storage destinations, log rotation, and retention. In containers, stdout and a collector usually reduce local file management. If changing configuration files at runtime, understand the reload mechanism and version support; **do not assume every change hot-reloads instantaneously**.

Audit requirements with legal or high-transactionality demands must be designed independently; never assume a `logger.info` line is immutable, durable evidence.

## 12. Common Mistakes When Deciding to Use Logback

| Mistake | Accurate Perspective |
| --- | --- |
| "SLF4J is Logback" | SLF4J is an API; Logback is a backend |
| "Every library must add logback-classic" | Libraries usually only need SLF4J API; applications choose the provider |
| "Logback is always faster than every backend" | Must benchmark with the actual workload, appenders, and configuration |
| "Adding Logback to Spring Boot always improves logging" | The framework may already use Logback; adding duplicates causes conflicts |
| "Having a log file is safe enough" | Retention, access control, data protection, and monitoring are required |
| "AsyncAppender guarantees logs are never lost" | Queue/crashes and discard policies can still lose events |
| "Setting DEBUG on a Logger makes all targets print DEBUG" | Appender filters and event routing still govern output |
| "Disabling additivity always fixes duplicate logs" | If the branch has no appender of its own, logs can be lost |
| "MDC automatically follows CompletableFuture" | Context usually must be passed/restored explicitly or via a framework |
| "Writing JSON with PatternLayout is structured enough" | Schema-aware encoders/serializers and proper escaping are required |
| "One logging backend replaces audit/metrics/tracing" | Each signal type has distinct responsibilities and guarantees |

## 13. Selection Workflow for a Real Project

**Step 1 — Identify the artifact's role.** If you are building a **library** for other applications to consume, generally depend only on the SLF4J API; do not force a backend. Only if it is a **runnable application** should you decide between Logback and another backend.

**Step 2 — Identify the framework in use.** For Spring Boot using Logback by default, prefer keeping it if it meets requirements. For projects already running Log4j 2 stably, identify clear reasons before switching.

**Step 3 — List operational requirements.** Need per-package levels? MDC? JSON encoder? File rolling? Async? Collection via stdout? Tracing? These requirements determine the backend and specific configuration.

**Step 4 — Choose a compatible SLF4J provider.** Inspect the dependency graph, remove extra providers, and avoid bidirectional bridges that could cause routing loops.

**Step 5 — Design the output pipeline.** Containers generally favor stdout/collectors; file-writing systems need rotation, retention, write permissions, disk-space monitoring, and shutdown handling.

**Step 6 — Test behavior.** Emit events at INFO, DEBUG, WARN, and ERROR, with `requestId` and exceptions; verify output, destinations, duplicate logs, lost context in executors, and latency under heavy logging.

**Step 7 — Evaluate security and cost.** Restrict sensitive data, control log volume, keep the backend on a supported version, and monitor discard/collector policies.

## 14. Checklist Before Choosing or Deploying

- [ ] The application genuinely needs a full backend rather than JUL/`slf4j-simple`.
- [ ] **Library** vs. **runnable application** roles have been clearly distinguished.
- [ ] Active frameworks/backends have been identified to avoid unnecessary replacement.
- [ ] Only one compatible SLF4J provider exists on the runtime classpath.
- [ ] Per-package/class levels, hierarchy, and additivity are designed consistently.
- [ ] Appropriate Appenders and Encoders exist for console/file/collector targets.
- [ ] If writing files, rolling, retention, write permissions, and low-disk handling are in place.
- [ ] If using MDC/tracing, propagation and cleanup across other threads/executors are handled.
- [ ] If using `AsyncAppender`, queue, blocking, discard, and shutdown limitations are understood.
- [ ] Policies for sensitive data, escaping, access control, and log storage are in place.
- [ ] Success, failure, exception, duplicate-log, and filtered-log flows have been tested.
- [ ] Performance has been evaluated on realistic workloads rather than relying on backend reputation.

### Technical References

- [Logback documentation](https://logback.qos.ch/documentation.html): architecture, configuration, loggers, appenders, and encoders.
- [Logback manual — Configuration](https://logback.qos.ch/manual/configuration.html): configuration placement and file-loading mechanisms.
- [Logback manual — Appenders](https://logback.qos.ch/manual/appenders.html): ConsoleAppender, RollingFileAppender, and AsyncAppender.
- [SLF4J manual](https://www.slf4j.org/manual.html): API facade, providers, and logger usage.
- [Spring Boot logging reference](https://docs.spring.io/spring-boot/reference/features/logging.html): logging integration and framework configuration options.

**Conclusion:** **Use Logback when you need a seriously configured, observable, and operable logging backend for a Java application**, especially when code already uses SLF4J or a framework that integrates Logback by default. Do not use it merely out of habit: start from actual requirements, choose a single provider, design Appenders/Encoders, and verify MDC, log retention, performance, and information protection.
