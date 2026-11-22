# Bridges Between Logging APIs in Java

## 1. What is an API Bridge?

A Java application often depends on multiple independently developed libraries. The first library calls **Java Util Logging (JUL)**, the second uses **SLF4J**, and the third emits events through the **Log4j2 API**. Each library may use different level names, logger objects, and exception-passing mechanisms. Without proper configuration, logs can be written to different destinations, have inconsistent formats, or even be lost.

A **logging bridge** is a layer that **forwards** events emitted through a source logging API to a target logging API or pipeline. Bridges help unify events from legacy and modern libraries so that the application can choose a single backend to manage levels, formatting, output destinations, and retention policies.

Example:

```text
Application code  ──── SLF4J API ──────────────┐
Legacy library ── JUL API ── jul-to-slf4j ─────┼──> SLF4J provider ──> Logback ──> Console/File
Library C  ── Log4j2 API ── log4j-to-slf4j ────┘
```

This is **one architectural option** when choosing Logback as the backend. Not every application needs all of these bridges; only add bridges for the source APIs actually used, while maintaining **one clear forwarding direction**.

A bridge is **not** a distributed tracing tool. It forwards log records between APIs; it does not automatically generate spans, trace IDs, request durations, or tracing context.

### Lesson Objectives

After this lesson, you will be able to:

- Distinguish between **facade**, **source API**, **bridge**, **provider/adapter**, and **backend**.
- Correctly read the forwarding direction of common artifacts: `jul-to-slf4j`, `slf4j-jdk14`, `log4j-to-slf4j`, `log4j-slf4j2-impl`, `jcl-over-slf4j`.
- Build a Java 17+ application that receives logs from JUL and SLF4J, outputting both through Logback.
- Avoid **bridge loops**, multiple provider warnings, missing stack traces, and duplicate logs.
- Know how to decide when a bridge is needed and verify the actual pipeline.

## 2. Distinguishing Facade, Bridge, Provider, and Backend

Four concepts are easily confused and lumped together as "logging libraries":

| Concept | Question it answers | Examples |
| --- | --- | --- |
| **Logging API** | Which methods does source code call to create events? | `java.util.logging.Logger`, `org.apache.logging.log4j.Logger` |
| **Facade** | What common API keeps source code decoupled from the backend? | `org.slf4j.Logger` from `slf4j-api` |
| **Bridge** | How do events from API A get to API B? | `jul-to-slf4j`: JUL → SLF4J; `log4j-to-slf4j`: Log4j2 API → SLF4J |
| **Provider / backend adapter** | Which logging system executes the facade's calls? | `logback-classic`, `slf4j-simple`, `log4j-slf4j2-impl` |
| **Backend** | What applies levels, filters, formatters, appenders, and outputs data? | Logback, Log4j2 Core, JUL |

The **Facade** stands on the **API-calling side**: your code only knows `LOG.info(...)`. The **Bridge** stands on a **forwarding path from a source API** to a target API. The **Provider** supplies the implementation for the facade. The **Backend** processes records into actual output.

A provider can also act as an adapter to another backend: for example, `slf4j-jdk14` receives SLF4J calls and forwards them to JUL. In this case, it acts as a provider for SLF4J while also creating a forwarding direction.

The most important thing is to be able to answer **"which API does the event originate from, and which backend does it go to?"**. Artifact names often give hints, but you need to read both the direction and the role before combining dependencies.

## 3. Forwarding Direction Map of Common Bridges

| Artifact / Mechanism | Event Direction | When to Use? |
| --- | --- | --- |
| `jul-to-slf4j` | **JUL API → SLF4J API** | A library emits JUL; the application chooses Logback or another backend via SLF4J |
| `slf4j-jdk14` | **SLF4J API → JUL backend** | The application uses SLF4J but wants JUL as the execution backend |
| `log4j-to-slf4j` | **Log4j2 API → SLF4J API** | A library uses Log4j2 API; the application chooses another SLF4J backend |
| `log4j-slf4j2-impl` | **SLF4J API 2.x → Log4j2 Core** | Choosing Log4j2 as the backend for code using SLF4J 2.x |
| `log4j-slf4j-impl` | **SLF4J API 1.7.x → Log4j2** | Legacy adapter; do not confuse with the provider for SLF4J 2.x |
| `jcl-over-slf4j` | **Apache Commons Logging API → SLF4J API** | A legacy library calls JCL and the application needs to unify into SLF4J |
| `log4j-over-slf4j` | **Log4j 1.x API → SLF4J API** | A legacy library uses Log4j 1.x API; compatibility evaluation required |
| `slf4j-reload4j` | **SLF4J API → reload4j backend** | System intentionally uses a Log4j 1.x-compatible backend |

**Do not configure both directions of the same API pair.** For example:

```text
WRONG: JUL ── jul-to-slf4j ──> SLF4J
         ^                        |
         |                        |
         └───── slf4j-jdk14 ──────┘

WRONG: Log4j2 API ── log4j-to-slf4j ──> SLF4J
            ^                            |
            |                            |
            └──── log4j-slf4j2-impl ─────┘
```

Depending on the bridge and version, a loop may be detected and reported as an error, or it may lead to recursive calls, stack overflow, duplicate logs, or lost logs. Do not treat the behavior of a single test build as a general safety guarantee for other versions.

### Backend Selection Examples

**Choosing Logback as the backend:**

```text
JUL API ───────── jul-to-slf4j ─────┐
Log4j2 API ────── log4j-to-slf4j ───┼─> SLF4J API ─> Logback
New code ───────────────────────────┘
```

**Choosing Log4j2 Core as the backend:**

```text
SLF4J API ─── log4j-slf4j2-impl ───┐
Log4j2 API ────────────────────────┼─> Log4j2 Core
JUL API ─── (appropriate adapter) ─┘
```

For JUL in the second option, you must **select and configure a specific JUL→Log4j2 solution** appropriate for the version (such as Log4j2's JUL integration module), rather than assuming from the diagram alone that JUL automatically forwards to Core. Bridges may also require a JVM property or startup configuration.

**Choosing JUL as the backend:**

```text
SLF4J API code ── slf4j-jdk14 ──> JUL Logger/Handler
JUL API code ───────────────────> JUL Logger/Handler
```

In this option, do not add `jul-to-slf4j` in the reverse direction.

## 4. Specifically for SLF4J 2.x: Providers Differ from Legacy Bindings

SLF4J has two integration generations that learners often confuse:

- SLF4J **1.7.x** uses the traditional binding model, involving the `org.slf4j.impl.StaticLoggerBinder` class.
- SLF4J **2.x** discovers implementations via Java `ServiceLoader` and the `org.slf4j.spi.SLF4JServiceProvider` interface.

Therefore:

- `log4j-slf4j2-impl` is the provider for SLF4J 2.x → Log4j2.
- `log4j-slf4j-impl` is for the SLF4J 1.7.x binding model; **do not substitute** it for the 2.x provider just because the names look similar.
- `logback-classic` in a compatible generation provides a provider for SLF4J 2.x.
- `slf4j-simple` can also act as a provider; adding it alongside Logback usually triggers a **multiple providers** warning.

Without a valid SLF4J 2.x provider, the application may warn with something like `No SLF4J providers were found` and fall back to NOP, meaning calls through the facade are not written to the expected destination. This is **different** from a bridge not being installed: having a provider but missing a bridge means logs from the source API may still be emitted through its own separate system.

**Dependency principle:** identify the major version of the SLF4J API, select exactly **one** runtime provider, and only add **one-way** bridges for each source API that needs to converge.

## 5. Complete Java 17 Example: Consolidating JUL and SLF4J into Logback

The following example illustrates the difference between "code already written with SLF4J" and "a legacy library still calling JUL". We keep both APIs in the source code and use `jul-to-slf4j` to route both to **Logback**, thereby applying a unified format and level configuration.

Components:

- `slf4j-api`: the facade that the program can call.
- `jul-to-slf4j`: the bridge from the JUL API to SLF4J.
- `logback-classic`: the SLF4J 2.x provider and Logback backend.
- `logback.xml`: configuration for the application's console appender and levels.

### 5.1. Directory Structure

```text
bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── BridgeDemo.java
        └── resources/
            └── logback.xml
```

### 5.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bridge-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>jul-to-slf4j</artifactId>
            <version>2.0.16</version>
        </dependency>
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
            </plugin>
        </plugins>
    </build>
</project>
```

The versions are pinned to **illustrate a specific dependency set**, not to claim they are the latest or recommended versions for production at all times. When building a real project, align them with your dependency management, security patches, and Java/SLF4J compatibility for the backend.

Do not add `slf4j-simple` or `slf4j-jdk14` to this example; Logback is already the target provider, while `jul-to-slf4j` only acts as a bridge.

### 5.3. File src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%-5level | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This configuration allows any logger in the `demo` namespace to output down to DEBUG, while the root logger defaults to INFO. `STDOUT` is Logback's console appender. The prefix `%-5level` formats the level in a minimum width field of five characters, `%msg` is the message, and `%n` is a newline.

Do not attach a separate appender to `demo` to avoid duplicate printing through the root logger. Even though root is at INFO, DEBUG records from `demo.*` loggers can still reach the root appender when the `demo` namespace logger permits them and no other filter blocks them.

### 5.4. File src/main/java/demo/BridgeDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.bridge.SLF4JBridgeHandler;

public final class BridgeDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(BridgeDemo.class);

    public static void main(String[] args) {
        // This demo program owns the JUL configuration for this JVM.
        // Remove default JUL root handlers to avoid writing the same record twice.
        SLF4JBridgeHandler.removeHandlersForRootLogger();
        SLF4JBridgeHandler.install();

        LOG.info("SLF4J event");

        // Simulate a legacy library calling the JUL API directly.
        java.util.logging.Logger legacy =
                java.util.logging.Logger.getLogger("demo.LegacyApi");

        // JUL must allow FINE before the bridge can receive it.
        legacy.setLevel(java.util.logging.Level.FINE);
        legacy.info("JUL event");
        legacy.fine("JUL detail");

        System.out.println("business-finished");
    }
}
```

### 5.5. Compiling and Running

From the `bridge-demo` directory, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BridgeDemo
```

**Expected stdout output produced by the application + appender:**

```text
INFO  | SLF4J event
INFO  | JUL event
DEBUG | JUL detail
business-finished
```

The `JUL detail` line outputs at the DEBUG level because the bridge maps the JUL `FINE` level to the corresponding SLF4J level in the pipeline. The space after INFO comes from the pattern `%-5level |`: the level INFO has four letters, so it is padded with one space before the fixed separator.

Maven/plugins or other libraries may print additional messages beyond the lines above. This example intentionally uses output containing only the message and level for easy verification; in production, you should include timestamp, logger name, thread, and safe context.

### 5.6. Why Does the Example Need Both Filtering Levels?

The call `legacy.fine("JUL detail")` is **first** checked by JUL against the effective level of the JUL logger. If the JUL logger is still at INFO, the FINE record is already filtered out and the bridge **cannot recover** it. That is why the example sets `legacy.setLevel(Level.FINE)`.

After the bridge forwards a JUL record to SLF4J, the target provider/backend still has its own filters. If Logback only accepts INFO, the record mapped to DEBUG will not be emitted, even though JUL allowed FINE. The example configures the `demo` logger at DEBUG so this event appears.

We can summarize it as:

```text
legacy.fine(...)
  │
  ├─ JUL logger level/filter: allow FINE?
  │           │ Yes
  │           ▼
  └── SLF4JBridgeHandler (installed on JUL root)
              │ map level / forward event
              ▼
         SLF4J API
              │
              ▼
       Logback Logger: DEBUG enabled?
              │ Yes
              ▼
       STDOUT ConsoleAppender
```

To run the demo, `SLF4JBridgeHandler.removeHandlersForRootLogger()` proactively removes handlers attached to the JUL root. **This is a JVM-wide operation**, suitable for a standalone learning program before the application starts processing work; do not call it arbitrarily inside an already-running application or a container sharing logging. `SLF4JBridgeHandler.install()` should also be called once during initialization. In servers with complex lifecycles, use an appropriate bootstrap/shutdown mechanism and avoid installing the bridge repeatedly.

## 6. How Are Log Levels Mapped?

Each API has its own set of levels, so passing through a bridge requires mapping to an equivalent level so the backend can filter and format it.

For `jul-to-slf4j`, the common general mapping is:

| JUL source | Typical mapped SLF4J level | Notes |
| --- | --- | --- |
| `SEVERE` | `ERROR` | Serious error event |
| `WARNING` | `WARN` | Unusual event |
| `INFO` | `INFO` | Operational information |
| `CONFIG` | `DEBUG` | Configuration details |
| `FINE` | `DEBUG` | Diagnostics |
| `FINER` | `TRACE` | More detailed |
| `FINEST` | `TRACE` | Deepest detail |

This table shows the **typical mapping behavior of the specified bridge**, not a universal standard forcing every bridge to convert all levels identically. Custom `Level` values may be mapped based on numeric values or custom policies; check the adapter in use if the application has custom levels.

A bridge cannot guarantee preserving every data field of each API. Some points to watch:

- Logger name, message, formatting arguments, and exceptions can be converted.
- Timestamp or source location (class/method/file/line) may differ because the bridge creates an event at a different layer.
- Filters/markers and backend-specific attributes do not always have a counterpart.
- Thread context/MDC does not automatically appear from every JUL log just because a bridge is installed.
- The backend formatter/encoder still makes the final decision on whether stack traces and metadata are written out.

Do not judge success merely by "a log line appeared": test **level, Throwable, logger name, context, and destination**.

## 7. Bridges Can Be Installed in Different Ways

**There is no single bridge installation API for every framework.** Each ecosystem has its own integration approach.

### 7.1. JUL → SLF4J

The `jul-to-slf4j` module provides `SLF4JBridgeHandler`, which can be installed on the JUL root logger. This is the approach used in the Java 17 example. You need to understand JUL's handler mechanism: a child logger can propagate records to parent/root handlers. If `setUseParentHandlers(false)` is set on a child logger and no bridge handler is attached directly, records may not reach the bridge.

The bridge handler runs after the JUL logger allows the event. Therefore, if you want the target backend to decide the level of detail, you must set the source JUL level low enough for the needed logs to pass through—but **opening JUL too wide can create overhead** even when the SLF4J backend is dropping most events. Consider level-synchronization tools (if supported by the backend) or targeted logger configuration.

### 7.2. SLF4J → Log4j2

When an application uses `org.slf4j.Logger` but chooses Log4j2 Core, use an SLF4J 2.x-compatible provider such as `log4j-slf4j2-impl` and the related Log4j2 dependencies. Business code still writes `LoggerFactory.getLogger(...)`; appenders/layouts/levels are configured in Log4j2. **This is a provider**, not `log4j-to-slf4j`.

### 7.3. Log4j2 API → SLF4J

When a library calls `org.apache.logging.log4j.LogManager.getLogger(...)` but the application's backend is Logback, you can use `log4j-to-slf4j`. This adapter forwards events **from the Log4j2 API** to the SLF4J facade. Do not use it at the same time as the SLF4J→Log4j2 provider in the previous section.

### 7.4. Commons Logging (JCL) → SLF4J

Some older libraries use `org.apache.commons.logging.Log`. `jcl-over-slf4j` provides a JCL-compatible API and forwards events to SLF4J. Check runtime dependencies to avoid keeping multiple JARs providing `org.apache.commons.logging.*` classes at the same time. Some Spring environments have **spring-jcl** as their own replacement/integration; do not add `jcl-over-slf4j` just because you see the name JCL without understanding the current configuration.

### 7.5. Log4j 1.x API → SLF4J

`log4j-over-slf4j` provides a subset of the Log4j 1.x-compatible API to forward events into SLF4J. However, do not assume every Log4j 1.x-specific API and behavior is fully emulated by the bridge; projects with custom appenders or legacy configurations require actual migration.

Especially avoid using `log4j-over-slf4j` (Log4j 1.x API → SLF4J) together with the `slf4j-reload4j` provider (SLF4J → Log4j 1.x/reload4j-style backend), as this can form a loop.

## 8. How to Choose a Logging Architecture for a Project

First identify the **target backend** that fits your operations, and only then consider the source APIs that need to be forwarded.

### Case A: New application using SLF4J + Logback

```text
Application code (SLF4J API)
                    │
                    ▼
            Logback provider
                    │
                    ▼
             Console / File
```

If all dependencies already log via SLF4J and there is no other logging API to unify, **no bridge is needed**. Adding a bridge when there is no corresponding source data only increases complexity.

### Case B: Application has a legacy JUL library, but wants a unified format

```text
JUL library ── jul-to-slf4j ─┐
Application ─── SLF4J ───────┼─> Logback
```

This is the demo's exact case. To capture all JUL events, install the bridge handler at the right time, review JUL source thresholds, and remove unwanted handlers on the root logger to avoid duplicate logs.

### Case C: Application chooses Log4j2 Core as the backend

```text
SLF4J clients ── log4j-slf4j2-impl ──┐
Log4j2 API clients ──────────────────┼─> Log4j2 Core
```

In this case, do not add `log4j-to-slf4j`. If there are JUL/JCL sources, choose separate adapters **pointing in the same direction toward the target backend**, and check context propagation and level management requirements.

### Case D: Application already operates with JUL

If all code uses only JUL and JUL handlers/formatters meet your needs, introducing SLF4J is not mandatory. If a library uses SLF4J, you can consider `slf4j-jdk14` to route that source to JUL. There is no need to create a cycle forwarding JUL back to SLF4J.

### Concise Architectural Rule

**Multiple source APIs → one-way bridges (when needed) → one provider/backend → managed log destinations.**

"One backend" does not mean only one appender is allowed: a backend can output to console and file simultaneously. It means not letting APIs split into competing pipelines or hard-to-control loops.

## 9. What Can Happen to Messages, Throwable, and MDC When Bridging?

### Messages and placeholders

JUL typically allows parameterized messages using JUL/`MessageFormat` syntax. SLF4J uses `{}` placeholders. The bridge is responsible for creating an event in the target API, but **you should not expect the placeholder syntaxes of two APIs to be interchangeable in source code**.

JUL code example:

```java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("demo.LegacyApi");
jul.log(java.util.logging.Level.INFO, "User {0} signed in",
        new Object[]{"alice"});
```

This is an **illustrative snippet**. `{0}` is the common JUL parameter syntax, whereas `{}` is the SLF4J placeholder syntax. The bridge layer must process/pass source arguments appropriately; if you see literal `{0}` or misaligned variables, check the bridge version and formatter rather than simply rewriting every message to the target backend's syntax.

### Throwable and stack traces

When logging an exception in JUL:

```java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException exception) {
    jul.log(java.util.logging.Level.SEVERE,
            "Invalid numeric configuration", exception);
}
```

This snippet assumes the `jul` variable is already declared. If the bridge and backend preserve the `Throwable` reference, the Logback or Log4j2 formatter can render the stack trace; ultimately, however, you must verify **at the actual log destination**. Avoid calling only `exception.getMessage()` if you want full stack frames and the cause chain.

### Correlation ID and MDC

SLF4J supports `MDC` and Log4j2 supports `ThreadContext`. JUL does not have the same MDC API by default. Installing `jul-to-slf4j` does not automatically generate `requestId`/`traceId` for each JUL record. When correlating multiple requests, context should be set/restored properly for the thread or task, and the encoder must output it.

In thread pools, the calling thread's context is not necessarily propagated to the worker thread executing the task. Do not store request IDs in a global static variable shared across concurrent requests. Log just enough safe context; never log tokens, passwords, cookies, or sensitive personal data into messages or MDC.

## 10. Bridge Performance and Lifecycle

A bridge does extra work: receiving a source event, possibly mapping levels/formats, creating an event in the target API, and passing it to the backend. This is not zero-cost.

Factors to consider:

- **Source filtering:** a record filtered out by JUL before creation cannot be recovered by the backend.
- **Target filtering:** a record that passes through the bridge can still be dropped by the backend.
- **Wasted work:** when the source allows very verbose logging while the target only keeps WARN, the cost of creating and forwarding records may be unnecessary.
- **Where the bridge is installed:** install once during bootstrap; do not reinstall on every request.
- **Duplicate handlers/appenders:** keeping the old JUL handler and adding a bridge can cause a single event to be emitted through both the JUL console and the Logback console.
- **Classloaders and shutdown:** applications running in containers or using hot reload must avoid holding handlers/providers across the wrong lifecycle.
- **Data loss on abrupt exit:** async backends, buffers, or downstream collectors may still have unflushed events.

If using Logback, you can consider tools in the ecosystem that help synchronize JUL and SLF4J levels to reduce overhead, but they must be configured according to the exact version and deployment. Do not assume a bridge always adjusts JUL levels automatically to match Logback.

## 11. Security and Dependency Safety

Logging can pass through multiple layers, making dependency and output control even more important:

1. **Check bridge and backend versions**: keep versions that are supported and patched for security vulnerabilities; do not copy old dependencies into production without checking.
2. **Do not ship multiple SLF4J providers**: multiple-provider warnings can cause an unexpected configuration to be selected.
3. **Do not create loops**: avoid the bidirectional bridge pairs mentioned earlier; loops can cause severe outages when logs are emitted.
4. **Do not drop critical logs**: verify exceptions, WARN/ERROR, startup, and shutdown logs at the right sinks.
5. **Do not duplicate logs**: if two pipelines push events to a collector simultaneously, costs increase and alert metrics may be double-counted.
6. **Do not log secrets**: bridges do not automatically scrub passwords, tokens, secrets, PII, or stack traces containing sensitive messages.
7. **Do not expose logging reconfiguration publicly**: changing levels or reloading runtime configuration must be access-controlled.
8. **Keep target configuration explicit**: formatting can lose information if the layout only prints the message while omitting the Throwable, logger, or correlation ID.

In real systems, inspect the artifacts **actually packaged at runtime** rather than looking only at intended build files; transitive dependencies can pull in unintended providers or bridges.

## 12. Common Errors and How to Troubleshoot

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| SLF4J logs appear, but JUL still has a different format | `jul-to-slf4j` not installed; default JUL handler still writes separately | Check bridge installation and handlers on JUL root |
| JUL logs disappear after installing the bridge | JUL filters at source, `useParentHandlers=false`, or backend blocks them | Check JUL logger, handler chain, and backend level |
| JUL `FINE` does not appear via Logback DEBUG | JUL source is still INFO or backend does not enable DEBUG | Lower the JUL threshold on the right logger and configure the backend accordingly |
| A single event is emitted twice | Old JUL handler and bridge both receive it; or backend has duplicate appenders | Check the entire pipeline and additivity |
| Adding `slf4j-jdk14` causes an error/loop | `jul-to-slf4j` is already present in the reverse direction | Keep only one direction for JUL ↔ SLF4J |
| Adding `log4j-to-slf4j` causes a loop error | `log4j-slf4j2-impl` is already present | Remove one direction and choose a clear target backend |
| Warning about multiple SLF4J providers | Logback, Simple, or another adapter present simultaneously | Use dependency tree and keep one provider |
| Warning about no providers; logs vanish | Only API/bridge present, no valid runtime provider | Add a compatible provider in the right scope |
| SLF4J 2.x ignores legacy binding | `StaticLoggerBinder` JAR from the 1.7 generation | Choose an SLF4J 2.x-compatible SPI provider |
| JCL class conflict | `jcl-over-slf4j` packaged alongside JCL/`spring-jcl` inappropriately | Inspect dependency tree and how the framework integrates |
| Missing stack trace after bridge | Code only logs message, or adapter/encoder drops Throwable | Pass the exception intact and check layout |
| Missing MDC/request ID | Context not set or not propagated, or encoder does not print it | Check MDC adapter and thread boundaries |
| Only some logs appear after deploy | Different instances have different classpaths/configs | Verify runtime provider and bridge on each instance |

### Source → Target Diagnostic Workflow

1. **Identify the source API:** `java.util.logging.Logger`, `org.slf4j.Logger`, `org.apache.logging.log4j.Logger`, or JCL.
2. **Draw the arrows:** clearly note where each bridge leads and which provider is the target; look for closed loops.
3. **Check runtime dependencies:** with Maven, run `mvn dependency:tree`; verify exact SLF4J 2.x, Logback, and Log4j2 versions if present.
4. **Check the selected provider:** startup warnings, logger factory, and actual backend.
5. **Check source thresholds:** for example, `JUL FINE` must be accepted by the source before forwarding.
6. **Check target thresholds and filters:** does the backend accept the mapped level?
7. **Check handlers/appenders:** how many sinks does one record reach, and is there duplication/additivity?
8. **Test exceptions and context:** do errors include stack traces, and are correlation fields correct?
9. **Observe after fixing:** verify console/file/collector in the real runtime environment; avoid concluding based solely on a successful compile.

## 13. Practicing Gradual Migration of a Legacy Application

Suppose a project has a long-lived module using JUL and newer modules using SLF4J:

**Before consolidation:**

```text
LegacyService → JUL → ConsoleHandler → stderr
NewService    → SLF4J → Logback → stdout/file
```

This can cause two formats and two level/retention policies.

**After consolidation:**

```text
LegacyService → JUL → jul-to-slf4j ─┐
NewService    → SLF4J ─────────────┴→ Logback → stdout/file
```

A sensible migration workflow:

1. Inventory the actual APIs and backends, including transitive dependencies.
2. Choose Logback or another backend as the **single target**.
3. Keep one compatible SLF4J provider.
4. Install the JUL → SLF4J bridge once at bootstrap, and manage JUL handlers to avoid duplicate printing.
5. Verify levels in both JUL and Logback; inspect logs from legacy packages.
6. Compare INFO/WARN/ERROR output, exceptions, and context fields against monitoring requirements.
7. Monitor performance, log volume, and alert counts before and after.
8. Remove dependencies or legacy handlers that are no longer needed, but do not remove APIs that libraries still use at compile/runtime.

A bridge is a tool for **gradual migration**, not necessarily a permanent solution. When library code can be safely updated to the common API, the system can be simplified further. Conversely, if a third-party library still uses JUL, a one-way bridge can be a practical long-term solution.

## 14. Self-Check Questions

**Question 1.** Which direction does `jul-to-slf4j` forward data?  
**Answer:** From events emitted via the JUL API to the SLF4J API. A compatible SLF4J provider is required to log to a backend.

**Question 2.** What does `slf4j-jdk14` do?  
**Answer:** It provides an implementation for the SLF4J API using the JUL backend; the opposite direction of `jul-to-slf4j`.

**Question 3.** Why should you not combine `log4j-to-slf4j` and `log4j-slf4j2-impl`?  
**Answer:** The two modules forward events in opposite directions between Log4j2 API ↔ SLF4J, which can create a logging loop.

**Question 4.** `jul-to-slf4j` is installed, the JUL logger is at INFO, and Logback is at DEBUG. Will `jul.fine(...)` be emitted?  
**Answer:** No. JUL filters out FINE before the bridge receives the event.

**Question 5.** An application uses Logback as its provider; does it need `slf4j-simple` as well?  
**Answer:** No. Two providers usually cause warnings or make implementation selection uncertain.

**Question 6.** Why do JUL logs appear twice after installing a bridge?  
**Answer:** The JUL root may still retain its original console handler while the bridge also forwards events to a backend with a console appender; check both destinations.

**Question 7.** Does a bridge automatically generate request IDs or distributed traces?  
**Answer:** No. A bridge mainly forwards events between APIs. Correlation IDs, context propagation, and tracing must be integrated separately.

**Question 8.** How can a library using `org.apache.commons.logging.Log` be unified with SLF4J?  
**Answer:** You can use a solution like `jcl-over-slf4j` when compatible, while controlling JCL/`spring-jcl` at runtime to avoid class collisions.

**Takeaway:** **An API bridge is a directed log-forwarding path**. Decide on your target backend, choose one provider, add one-way bridges only for the source APIs that truly need them, check levels at both ends, and avoid loop configurations. This gives a Java system consistent, easy-to-diagnose logs without forcing every legacy library to change its API immediately.
